"""Shared runner for static detectors on the synthetic development grid."""

import csv
import json
import math
import os
import platform
from collections.abc import Callable
from contextlib import contextmanager, nullcontext
from dataclasses import asdict, dataclass, replace
from importlib.metadata import version
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from drift_anomaly.evaluation import AnomalyEvaluation
from drift_anomaly.replay import (
    DEFAULT_WARMUP,
    DevelopmentReplay,
    StreamingDetector,
    replay_synthetic_development,
    validate_development_config,
)
from drift_anomaly.synthetic import RAMP_TYPES, SyntheticConfig, load_config

DEVELOPMENT_GRID = {
    "seeds": tuple(range(10)),
    "onsets": (1024, 2048),
    "shifts": (1.5, 3.0),
    "durations": (128, 256),
}


@dataclass(frozen=True)
class Experiment[Config]:
    detector: Config
    streams: tuple[tuple[Path, SyntheticConfig], ...]
    grid: dict[str, tuple]


def load_experiment[Config](
    path: Path, parse_detector: Callable[[object], Config]
) -> Experiment[Config]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {
        "detector",
        "warmup",
        "streams",
        "grid",
    }:
        raise ValueError("experiment requires detector, warmup, streams, and grid")
    config = parse_detector(data["detector"])
    if type(data["warmup"]) is not int or data["warmup"] != DEFAULT_WARMUP:
        raise ValueError(
            f"development baseline uses the protocol warm-up of {DEFAULT_WARMUP}"
        )
    requested_grid = data["grid"]
    if not isinstance(requested_grid, dict) or set(requested_grid) != set(
        DEVELOPMENT_GRID
    ):
        raise ValueError("grid requires seeds, onsets, shifts, and durations")
    grid = {}
    for name, allowed in DEVELOPMENT_GRID.items():
        values = requested_grid[name]
        if (
            not isinstance(values, list)
            or not values
            or any(
                type(value) not in (int, float) or value not in allowed
                for value in values
            )
            or len(values) != len(set(values))
            or (name != "shifts" and any(type(value) is not int for value in values))
        ):
            raise ValueError(
                f"grid {name} must be distinct values from the development protocol"
            )
        grid[name] = tuple(values)

    paths = data["streams"]
    if (
        not isinstance(paths, list)
        or not paths
        or not all(isinstance(item, str) for item in paths)
    ):
        raise ValueError("streams must list synthetic development YAML paths")
    streams = []
    seen = set()
    for name in paths:
        source = path.parent / name
        if source.suffix.lower() not in {".yaml", ".yml"}:
            raise ValueError("streams must point to synthetic development YAML configs")
        stream = load_config(source)
        validate_development_config(stream)
        _validate_template(stream)
        if stream.drift_type in seen:
            raise ValueError(f"multiple templates for {stream.drift_type}")
        seen.add(stream.drift_type)
        streams.append((source, stream))
    return Experiment(config, tuple(streams), grid)


def _validate_template(config: SyntheticConfig) -> None:
    if (
        config.n_observations != 4096
        or config.warmup != DEFAULT_WARMUP
        or config.pre_mean != 0.0
        or config.pre_std != 1.0
        or config.injection_count != 12
        or config.anomaly_magnitude != 6.0
        or config.anomaly_placement != "protocol"
        or config.min_anomaly_separation != 16
        or config.allow_boundary_anomalies
    ):
        raise ValueError(
            "stream template does not match the synthetic development protocol"
        )
    if config.drift_type == "none":
        return
    if (
        config.drift_start not in DEVELOPMENT_GRID["onsets"]
        or config.post_mean not in DEVELOPMENT_GRID["shifts"]
        or config.post_std != 1.0
        or config.priority_anomaly_count != 3
        or (
            config.drift_type in RAMP_TYPES
            and config.drift_duration not in DEVELOPMENT_GRID["durations"]
        )
        or (
            config.drift_type in ("sudden", "recurring")
            and config.post_change_window != 64
        )
        or (config.drift_type == "recurring" and config.recurrence_period != 512)
    ):
        raise ValueError(
            "stream template uses settings outside the synthetic development protocol"
        )


def scenarios(experiment: Experiment):
    grid = experiment.grid
    for path, template in experiment.streams:
        if template.drift_type == "none":
            for seed in grid["seeds"]:
                yield path, template, replace(template, seed=seed)
            continue
        durations = grid["durations"] if template.drift_type in RAMP_TYPES else (None,)
        for seed, onset, shift, duration in product(
            grid["seeds"], grid["onsets"], grid["shifts"], durations
        ):
            yield (
                path,
                template,
                replace(
                    template,
                    seed=seed,
                    drift_start=onset,
                    post_mean=shift,
                    drift_duration=duration,
                ),
            )


def paired_variants(scenario: SyntheticConfig):
    yield "clean", replace(scenario, anomaly_count=0, anomaly_fraction=None)
    yield "injected", scenario


def stream_id_for(config: SyntheticConfig, variant: str) -> str:
    parts = [config.drift_type, f"seed{config.seed}"]
    if config.drift_type != "none":
        parts.extend((f"onset{config.drift_start}", f"shift{float(config.post_mean)}"))
    if config.drift_duration is not None:
        parts.append(f"duration{config.drift_duration}")
    return "-".join((*parts, variant))


CSV_FIELDS = (
    "stream_id",
    "index",
    "value",
    "anomaly_label",
    "drift_phase",
    "regime",
    "score",
    "predicted_anomaly",
    "threshold",
)


def _write_scored(writer, run: DevelopmentReplay, stream_id: str) -> None:
    for record in run.result.scored_records():
        obs = record.observation
        prediction = record.prediction
        assert prediction is not None
        writer.writerow(
            (
                stream_id,
                obs.index,
                obs.value,
                int(obs.anomaly_label),
                obs.drift_phase,
                obs.regime,
                prediction.score,
                int(prediction.predicted_anomaly),
                prediction.metadata["threshold"],
            )
        )


def write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


@contextmanager
def staged_output(output: Path):
    root = Path.cwd() / "results"
    output = output.resolve()
    if output == root or not output.is_relative_to(root):
        raise ValueError("output must be a new directory under results/")
    if output.exists():
        raise FileExistsError(f"output directory already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as temporary:
        staged = Path(temporary) / "baseline"
        staged.mkdir()
        yield staged
        staged.rename(output)


def prepare_plots(output: Path) -> Path:
    cache = Path.cwd() / ".cache"
    cache.mkdir(exist_ok=True)
    os.environ.setdefault("XDG_CACHE_HOME", str(cache))
    os.environ.setdefault("MPLCONFIGDIR", str(cache / "matplotlib"))
    import matplotlib

    matplotlib.use("Agg")
    path = output / "plots"
    path.mkdir()
    return path


def run_baseline[Config](
    config_path: Path,
    output: Path,
    *,
    parse_detector: Callable[[object], Config],
    build_detector: Callable[[Config], StreamingDetector],
    scored_csv: bool = False,
    plot: Callable[[DevelopmentReplay, Path, float], None] | None = None,
    record_runtime: bool = False,
) -> dict:
    experiment = load_experiment(config_path, parse_detector)
    with staged_output(output) as staged:
        aggregate = _evaluate(
            experiment,
            config_path,
            staged,
            build_detector,
            scored_csv=scored_csv,
            plot=plot,
            record_runtime=record_runtime,
        )
    return aggregate


def _evaluate(
    experiment, config_path, output, build_detector, *, scored_csv, plot, record_runtime
):
    if plot is not None:
        prepare_plots(output)
    per_stream = []
    runtime = []
    groups = {}
    first = None
    csv_output = (
        (output / "scored_observations.csv").open("w", newline="", encoding="utf-8")
        if scored_csv
        else nullcontext(None)
    )
    with csv_output as file:
        writer = csv.writer(file) if file is not None else None
        if writer is not None:
            writer.writerow(CSV_FIELDS)
        for path, template, scenario in scenarios(experiment):
            for variant, config in paired_variants(scenario):
                stream_id = stream_id_for(config, variant)
                run = replay_synthetic_development(
                    config,
                    lambda: build_detector(experiment.detector),
                    config_path=path,
                )
                if first is None:
                    first = run.provenance
                if record_runtime:
                    stats = run.result.stats
                    runtime.append(
                        {
                            "stream_id": stream_id,
                            "elapsed_seconds": stats.elapsed_seconds,
                            "scored_count": stats.scored_count,
                            "scored_observations_per_second": stats.scored_observations_per_second,
                        }
                    )
                prediction = next(run.result.scored_records()).prediction
                assert prediction is not None
                threshold = prediction.metadata["threshold"]
                evaluation = AnomalyEvaluation()
                evaluation.add(run.result.scored_records(), run.drift_events)
                key = (config.drift_type, variant)
                if key not in groups:
                    groups[key] = AnomalyEvaluation(), 0
                group, count = groups[key]
                group.merge(evaluation)
                groups[key] = group, count + 1
                per_stream.append(
                    {
                        "stream_id": stream_id,
                        "variant": variant,
                        "drift_type": config.drift_type,
                        "seed": config.seed,
                        "stream_config_path": str(path),
                        "stream_parameters": asdict(config),
                        "threshold": threshold,
                        "warmup": run.result.stats.warmup_count,
                        **evaluation.summary(),
                    }
                )
                if writer is not None:
                    _write_scored(writer, run, stream_id)
                if plot is not None and variant == "injected" and scenario == template:
                    plot(
                        run,
                        output / "plots" / f"{config.drift_type}.png",
                        threshold,
                    )

    assert first is not None
    overall = AnomalyEvaluation()
    by_drift = {}
    for (drift, variant), (evaluation, count) in groups.items():
        by_drift.setdefault(drift, {})[variant] = {
            "stream_count": count,
            **evaluation.summary(),
        }
        overall.merge(evaluation)
    aggregate = {
        "stream_count": len(per_stream),
        "by_drift": by_drift,
        "pooled": overall.summary(),
    }
    write_json(
        output / "manifest.json",
        {
            "schema_version": 1,
            "split": "development",
            "experiment_config": str(config_path),
            "git_commit": first.git_commit,
            "project_version": first.project_version,
            "executed_at_utc": first.executed_at_utc,
            "python_version": platform.python_version(),
            "dependencies": {
                name: version(name)
                for name in ("numpy", "scikit-learn", "PyYAML", "matplotlib")
            },
            "detector": {
                "type": first.detector_id,
                **asdict(experiment.detector),
            },
            "warmup": DEFAULT_WARMUP,
            "stream_templates": [str(path) for path, _ in experiment.streams],
            "grid": experiment.grid,
            "variants": ["clean", "injected"],
            "stream_count": len(per_stream),
            "scored_csv": scored_csv,
            "plots": plot is not None,
        },
    )
    write_json(output / "per_stream_metrics.json", per_stream)
    write_json(output / "aggregate.json", aggregate)
    if runtime:
        elapsed = math.fsum(row["elapsed_seconds"] for row in runtime)
        scored = aggregate["pooled"]["scored_count"]
        write_json(
            output / "runtime.json",
            {
                "scored_count": scored,
                "elapsed_seconds": elapsed,
                "scored_observations_per_second": scored / elapsed
                if elapsed > 0
                else None,
                "per_stream": runtime,
            },
        )
    return aggregate
