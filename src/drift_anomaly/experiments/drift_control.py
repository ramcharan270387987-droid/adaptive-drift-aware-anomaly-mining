"""Verify that observing drift alarms leaves frozen Z-score outputs invariant."""

import argparse
import csv
import json
import platform
from collections import defaultdict
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from hashlib import file_digest
from importlib.metadata import version
from pathlib import Path

import yaml

from drift_anomaly.adwin import ADWINDetector
from drift_anomaly.drift_evaluation import DriftEvaluation, evaluate_drift
from drift_anomaly.evaluation import AnomalyEvaluation
from drift_anomaly.experiments import (
    adwin_baseline,
    drift_baseline,
    page_hinkley_baseline,
    static_baseline,
    zscore_baseline,
)
from drift_anomaly.experiments.drift_comparison import MATCHING_POLICY
from drift_anomaly.frozen_control import FrozenZScoreWithDrift
from drift_anomaly.page_hinkley import PageHinkleyDetector
from drift_anomaly.replay import (
    DEFAULT_WARMUP,
    DevelopmentReplay,
    StreamingDetector,
    replay_synthetic_development,
)
from drift_anomaly.zscore import StaticZScore

CONFIG_DIR = Path("configs/experiments")


@dataclass(frozen=True)
class BaselineReference:
    manifest: dict
    streams: dict[str, dict]
    aggregate: dict
    provenance: dict

    @classmethod
    def load(
        cls, root: Path, experiment: static_baseline.Experiment, detector_id: str
    ) -> "BaselineReference":
        manifest = _read_json(root / "manifest.json")
        expected = {
            "schema_version": 1,
            "split": "development",
            "warmup": DEFAULT_WARMUP,
            "detector": {"type": detector_id, **asdict(experiment.detector)},
            "grid": {key: list(values) for key, values in experiment.grid.items()},
            "variants": ["clean", "injected"],
        }
        zscore = detector_id == StaticZScore.identifier
        if zscore:
            expected["scored_csv"] = True
        else:
            expected["matching"] = MATCHING_POLICY
            expected["first_eligible_index"] = DEFAULT_WARMUP
        if (
            not isinstance(manifest, dict)
            or any(manifest.get(key) != value for key, value in expected.items())
            or not manifest.get("git_commit")
        ):
            detail = " with scored CSV enabled" if zscore else ""
            raise ValueError(
                f"{detector_id} reference must match the committed configuration and development grid{detail}"
            )

        rows = _read_json(root / "per_stream_metrics.json")
        if not isinstance(rows, list) or not all(
            isinstance(row, dict) and isinstance(row.get("stream_id"), str)
            for row in rows
        ):
            raise ValueError(f"{detector_id} reference requires per-stream records")
        streams = {row["stream_id"]: row for row in rows}
        if len(rows) != len(streams) or len(rows) != manifest.get("stream_count"):
            raise ValueError(
                f"{detector_id} reference has duplicate or missing streams"
            )
        artifacts = ["manifest.json", "aggregate.json", "per_stream_metrics.json"]
        if zscore:
            artifacts.append("scored_observations.csv")
        else:
            artifacts.append("paired_false_alarms.json")
        provenance = {
            "directory": str(root),
            "git_commit": manifest["git_commit"],
            "sha256": {name: _sha256(root / name) for name in artifacts},
        }
        return cls(manifest, streams, _read_json(root / "aggregate.json"), provenance)


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    with path.open("rb") as file:
        return file_digest(file, "sha256").hexdigest()


def _require_equal(actual, expected, description: str) -> None:
    if json.loads(json.dumps(actual, allow_nan=False)) != expected:
        raise ValueError(f"invariance check failed for {description}")


def _require_stream_equal(row: dict, reference: BaselineReference, label: str) -> None:
    stream_id = row["stream_id"]
    expected = reference.streams.get(stream_id)
    # Paths may be rendered relative or absolute. Effective generator settings are compared.
    _require_equal(
        {key: value for key, value in row.items() if key != "stream_config_path"},
        {
            key: value
            for key, value in (expected or {}).items()
            if key != "stream_config_path"
        },
        f"{label} metrics and diagnostics for {stream_id}",
    )


def _verify_scored_rows(
    reader: Iterator[list[str]], stream_id: str, runs: dict[str, DevelopmentReplay]
) -> int:
    labels = list(runs)
    checked = 0
    for records in zip(
        *(run.result.scored_records() for run in runs.values()), strict=True
    ):
        expected = next(reader, None)
        for label, record in zip(labels, records, strict=True):
            actual = static_baseline.scored_row(record, stream_id)
            if expected != [
                str(value) if value is not None else "" for value in actual
            ]:
                raise ValueError(
                    f"invariance check failed for {label} scored CSV at {stream_id} index {actual[1]}"
                )
        checked += 1
    return checked


@dataclass
class ControlEvaluation:
    anomaly: dict[tuple[str, str], tuple[AnomalyEvaluation, int]]
    drift: dict[tuple[str, str], list[DriftEvaluation]]
    pairs: list[dict]
    scored_rows_verified: int = 0

    def add(self, key, anomaly: AnomalyEvaluation, drift: DriftEvaluation) -> None:
        if key not in self.anomaly:
            self.anomaly[key] = AnomalyEvaluation(), 0
        group, count = self.anomaly[key]
        group.merge(anomaly)
        self.anomaly[key] = group, count + 1
        self.drift[key].append(drift)


def run_experiment(
    output: Path,
    *,
    zscore_results: Path,
    adwin_results: Path,
    page_hinkley_results: Path,
    zscore_config: Path = CONFIG_DIR / "zscore_dev.yaml",
    adwin_config: Path = CONFIG_DIR / "adwin_dev.yaml",
    page_hinkley_config: Path = CONFIG_DIR / "page_hinkley_dev.yaml",
) -> dict:
    anomaly = zscore_baseline.load_experiment(zscore_config)
    experiments = {
        "adwin": adwin_baseline.load_experiment(adwin_config),
        "page_hinkley": page_hinkley_baseline.load_experiment(page_hinkley_config),
    }
    for label, experiment in experiments.items():
        if (anomaly.grid, anomaly.streams) != (experiment.grid, experiment.streams):
            raise ValueError(
                f"{label} must use the same development grid and templates as Z-score"
            )
    references = {
        "zscore_static": BaselineReference.load(
            zscore_results, anomaly, "zscore_static"
        ),
        "adwin": BaselineReference.load(adwin_results, experiments["adwin"], "adwin"),
        "page_hinkley": BaselineReference.load(
            page_hinkley_results, experiments["page_hinkley"], "page_hinkley"
        ),
    }
    factories: dict[str, Callable[[], StreamingDetector]] = {
        "adwin": lambda: FrozenZScoreWithDrift(
            StaticZScore(anomaly.detector), ADWINDetector(experiments["adwin"].detector)
        ),
        "page_hinkley": lambda: FrozenZScoreWithDrift(
            StaticZScore(anomaly.detector),
            PageHinkleyDetector(experiments["page_hinkley"].detector),
        ),
    }
    with (
        (zscore_results / "scored_observations.csv").open(
            newline="", encoding="utf-8"
        ) as file,
        static_baseline.staged_output(output) as staged,
    ):
        reader = csv.reader(file)
        if next(reader, None) != list(static_baseline.CSV_FIELDS):
            raise ValueError("Z-score reference scored CSV has an unexpected schema")
        report, rows, provenance = _evaluate(anomaly, factories, references, reader)
        manifest = {
            "schema_version": 1,
            "split": "development",
            "git_commit": provenance.git_commit,
            "executed_at_utc": provenance.executed_at_utc,
            "project_version": provenance.project_version,
            "python_version": platform.python_version(),
            "dependencies": {
                name: version(name)
                for name in ("numpy", "scikit-learn", "river", "PyYAML")
            },
            "configs": {
                "zscore_static": str(zscore_config),
                "adwin": str(adwin_config),
                "page_hinkley": str(page_hinkley_config),
            },
            "detectors": {
                label: reference.manifest["detector"]
                for label, reference in references.items()
            },
            "references": {
                label: reference.provenance for label, reference in references.items()
            },
            "matching": MATCHING_POLICY,
            "warmup": DEFAULT_WARMUP,
            "grid": anomaly.grid,
            "stream_templates": [str(path) for path, _ in anomaly.streams],
            "anomaly_adaptation": False,
        }
        static_baseline.write_json(staged / "manifest.json", manifest)
        static_baseline.write_json(staged / "control_report.json", report)
        static_baseline.write_json(staged / "per_stream_checks.json", rows)
    return report


def _evaluate(anomaly, factories, references, reader):
    results = {
        label: ControlEvaluation({}, defaultdict(list), []) for label in factories
    }
    first = None
    per_stream = []
    for path, _, scenario in static_baseline.scenarios(anomaly):
        pair_id = static_baseline.stream_id_for(scenario, "pair")
        pair_diagnostics = {label: [] for label in factories}
        for variant, config in static_baseline.paired_variants(scenario):
            stream_id = static_baseline.stream_id_for(config, variant)
            runs = {
                label: replay_synthetic_development(config, factory, config_path=path)
                for label, factory in factories.items()
            }
            if first is None:
                first = runs["adwin"].provenance
            checked = _verify_scored_rows(reader, stream_id, runs)
            row = {
                "stream_id": stream_id,
                "scored_rows_verified_per_control": checked,
                "drift": {},
            }
            for label, run in runs.items():
                drift = evaluate_drift(run)
                anomaly_metrics = AnomalyEvaluation()
                anomaly_metrics.add(run.result.scored_records(), run.drift_events)
                anomaly_row = static_baseline.anomaly_stream_record(
                    run, anomaly_metrics, stream_id, variant
                )
                drift_row = drift_baseline.drift_stream_record(
                    run, drift, stream_id, pair_id, variant
                )
                _require_stream_equal(anomaly_row, references["zscore_static"], label)
                _require_stream_equal(drift_row, references[label], label)
                results[label].add((config.drift_type, variant), anomaly_metrics, drift)
                results[label].scored_rows_verified += checked
                pair_diagnostics[label].append(drift)
                row["drift"][label] = drift_row
            per_stream.append(row)
        for label, pair in pair_diagnostics.items():
            results[label].pairs.append(
                drift_baseline.pair_record(pair_id, scenario.drift_type, *pair)
            )
    if next(reader, None) is not None:
        raise ValueError("Z-score reference scored CSV has extra rows")
    visited = {row["stream_id"] for row in per_stream}
    for label, reference in references.items():
        if visited != reference.streams.keys() or len(per_stream) != len(
            reference.streams
        ):
            raise ValueError(
                f"{label} reference must contain exactly the replayed streams"
            )

    static = references["zscore_static"].aggregate
    controls = {"static_zscore": {"anomaly": static, "drift": None}}
    for label, result in results.items():
        anomaly_metrics = static_baseline.summarize_anomaly_groups(result.anomaly)
        drift_metrics = drift_baseline.summarize_drift_groups(
            result.drift, result.pairs
        )
        _require_equal(anomaly_metrics, static, f"{label} aggregate anomaly metrics")
        _require_equal(
            drift_metrics,
            references[label].aggregate,
            f"{label} aggregate drift metrics",
        )
        _require_equal(
            result.pairs,
            _read_json(
                Path(references[label].provenance["directory"])
                / "paired_false_alarms.json"
            ),
            f"{label} paired drift diagnostics",
        )
        controls[f"zscore_{label}_no_adaptation"] = {
            "anomaly": anomaly_metrics,
            "drift": drift_metrics,
            "scored_rows_verified": result.scored_rows_verified,
            "anomaly_outputs_exact": True,
            "drift_diagnostics_exact": True,
        }
    assert first is not None
    return {"stream_count": len(per_stream), "controls": controls}, per_stream, first


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="new directory under results/"
    )
    parser.add_argument(
        "--zscore-results",
        type=Path,
        required=True,
        help="committed Z-score results including scored CSV",
    )
    parser.add_argument("--adwin-results", type=Path, required=True)
    parser.add_argument("--page-hinkley-results", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run_experiment(**vars(args))
    except (OSError, ValueError, yaml.YAMLError) as error:
        parser.exit(1, f"Drift control: {error}\n")
    print(
        f"Verified exact anomaly outputs and drift diagnostics for both controls across {report['stream_count']} development streams. Results in {args.output}."
    )


if __name__ == "__main__":
    main()
