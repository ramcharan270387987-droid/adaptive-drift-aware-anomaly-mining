"""Evaluate the static Z-score baseline on the synthetic development grid."""

import argparse
import csv
import json
import os
import platform
from contextlib import nullcontext
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
    replay_synthetic_development,
    validate_development_config,
)
from drift_anomaly.synthetic import RAMP_TYPES, SyntheticConfig, load_config
from drift_anomaly.zscore import StaticZScore, ZScoreConfig

DEVELOPMENT_GRID = {
    "seeds": tuple(range(10)),
    "onsets": (1024, 2048),
    "shifts": (1.5, 3.0),
    "durations": (128, 256),
}


@dataclass(frozen=True)
class Experiment:
    detector: ZScoreConfig
    streams: tuple[tuple[Path, SyntheticConfig], ...]
    grid: dict[str, tuple]


def load_experiment(path: Path) -> Experiment:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {
        "detector",
        "warmup",
        "streams",
        "grid",
    }:
        raise ValueError("experiment requires detector, warmup, streams, and grid")
    detector = data["detector"]
    if not isinstance(detector, dict) or set(detector) != {
        "type",
        "threshold",
        "minimum_std",
    }:
        raise ValueError("detector requires type, threshold, and minimum_std")
    if detector["type"] != StaticZScore.identifier:
        raise ValueError("detector type must be zscore_static")
    config = ZScoreConfig(detector["threshold"], detector["minimum_std"])
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


def _scenarios(experiment: Experiment):
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


def _stream_id(config: SyntheticConfig, variant: str) -> str:
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


def _plot_run(run: DevelopmentReplay, output: Path, threshold: float) -> None:
    from matplotlib import pyplot as plt

    records = tuple(run.result.scored_records())
    indices = [row.observation.index for row in records]
    values = [row.observation.value for row in records]
    scores = [row.prediction.score for row in records]
    truth = [i for i, row in enumerate(records) if row.observation.anomaly_label]
    predictions = [
        i for i, row in enumerate(records) if row.prediction.predicted_anomaly
    ]
    fig, (trace, score) = plt.subplots(
        2, 1, figsize=(10, 5), sharex=True, layout="constrained"
    )
    trace.plot(indices, values, color="#334155", linewidth=0.65, label="Value")
    trace.scatter(
        [indices[i] for i in truth],
        [values[i] for i in truth],
        facecolors="none",
        edgecolors="#b91c1c",
        s=30,
        label="True anomaly",
    )
    trace.scatter(
        [indices[i] for i in predictions],
        [values[i] for i in predictions],
        marker="x",
        s=9,
        color="#1d4ed8",
        alpha=0.65,
        label="Predicted anomaly",
    )
    score.plot(indices, scores, color="#1d4ed8", linewidth=0.65)
    score.axhline(
        threshold, color="#b91c1c", linestyle="--", label=f"Threshold {threshold:g}"
    )
    for event in run.drift_events:
        for axis in (trace, score):
            if event.start == event.end:
                axis.axvline(event.start, color="#a16207", linewidth=0.9)
            else:
                axis.axvspan(event.start, event.end, color="#fde68a", alpha=0.45)
                axis.axvline(event.start, color="#a16207", linewidth=0.7)
                axis.axvline(event.end, color="#a16207", linewidth=0.7)
    trace.set(
        title=f"Development static Z-score | {run.provenance.drift_type}, seed {run.provenance.stream_seed}",
        ylabel="Value",
    )
    score.set(xlabel="Observation index", ylabel="Absolute Z-score")
    trace.legend(loc="upper right", ncols=3)
    score.legend(loc="upper right")
    fig.savefig(output, dpi=140)
    plt.close(fig)


def _write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def run_experiment(
    config_path: Path, output: Path, *, scored_csv: bool = False, plots: bool = False
) -> dict:
    experiment = load_experiment(config_path)
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
        aggregate = _evaluate(
            experiment, config_path, staged, scored_csv=scored_csv, plots=plots
        )
        staged.rename(output)
    return aggregate


def _evaluate(experiment, config_path, output, *, scored_csv, plots):
    if plots:
        cache = Path.cwd() / ".cache"
        cache.mkdir(exist_ok=True)
        os.environ.setdefault("XDG_CACHE_HOME", str(cache))
        os.environ.setdefault("MPLCONFIGDIR", str(cache / "matplotlib"))
        import matplotlib

        matplotlib.use("Agg")
        (output / "plots").mkdir()
    per_stream = []
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
        for path, template, scenario in _scenarios(experiment):
            for variant in ("clean", "injected"):
                config = (
                    replace(scenario, anomaly_count=0, anomaly_fraction=None)
                    if variant == "clean"
                    else scenario
                )
                stream_id = _stream_id(config, variant)
                run = replay_synthetic_development(
                    config, lambda: StaticZScore(experiment.detector), config_path=path
                )
                if first is None:
                    first = run.provenance
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
                        "threshold": experiment.detector.threshold,
                        "warmup": run.result.stats.warmup_count,
                        **evaluation.summary(),
                    }
                )
                if writer is not None:
                    _write_scored(writer, run, stream_id)
                if plots and variant == "injected" and scenario == template:
                    _plot_run(
                        run,
                        output / "plots" / f"{config.drift_type}.png",
                        experiment.detector.threshold,
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
    _write_json(
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
                "type": StaticZScore.identifier,
                **asdict(experiment.detector),
            },
            "warmup": DEFAULT_WARMUP,
            "stream_templates": [str(path) for path, _ in experiment.streams],
            "grid": experiment.grid,
            "variants": ["clean", "injected"],
            "stream_count": len(per_stream),
            "scored_csv": scored_csv,
            "plots": plots,
        },
    )
    _write_json(output / "per_stream_metrics.json", per_stream)
    _write_json(output / "aggregate.json", aggregate)
    return aggregate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, required=True, help="new directory under results/"
    )
    parser.add_argument(
        "--scored-csv", action="store_true", help="export every scored observation"
    )
    parser.add_argument(
        "--plots",
        action="store_true",
        help="plot the canonical injected stream per drift type",
    )
    args = parser.parse_args()
    try:
        aggregate = run_experiment(
            args.config, args.output, scored_csv=args.scored_csv, plots=args.plots
        )
    except (OSError, ValueError, yaml.YAMLError) as error:
        parser.exit(1, f"Z-score experiment: {error}\n")
    print(
        f"Development baseline: {aggregate['stream_count']} streams, "
        f"{aggregate['pooled']['scored_count']} scored observations. Results in {args.output}."
    )


if __name__ == "__main__":
    main()
