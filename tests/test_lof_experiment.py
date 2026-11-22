"""Validate shared inputs, runtime, and metric outputs for LOF."""

import csv
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest
import yaml

from drift_anomaly.experiments import (
    isolation_forest_baseline,
    lof_baseline,
    static_baseline,
    zscore_baseline,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/experiments/lof_dev.yaml"


def test_lof_uses_the_same_scenarios_as_existing_baselines():
    scenarios = list(static_baseline.scenarios(lof_baseline.load_experiment(CONFIG)))
    for filename, module in (
        ("zscore_dev.yaml", zscore_baseline),
        ("isolation_forest_dev.yaml", isolation_forest_baseline),
    ):
        existing = module.load_experiment(CONFIG.with_name(filename))
        assert scenarios == list(static_baseline.scenarios(existing))
    assert len(scenarios) == 250


def write_experiment(tmp_path, stream, seed=0):
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    config["streams"] = [str(ROOT / stream)]
    config["grid"]["seeds"] = [seed]
    path = tmp_path / "experiment.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("stream", "seed", "error"),
    [
        ("configs/synthetic/recurring_holdout.yaml", 0, "development replay requires"),
        ("configs/synthetic/recurring_dev.yaml", 1000, "grid seeds"),
        ("configs/nab.yaml", 0, "invalid synthetic config fields"),
    ],
)
def test_invalid_sources_stop_before_replay(tmp_path, monkeypatch, stream, seed, error):
    def unexpected(*args, **kwargs):
        pytest.fail("invalid input reached replay")

    monkeypatch.setattr(static_baseline, "replay_synthetic_development", unexpected)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match=error):
        lof_baseline.run_experiment(
            write_experiment(tmp_path, stream, seed), Path("results/check")
        )
    assert not (tmp_path / "results").exists()


def test_cli_exports_metrics_predictions_runtime_and_rule(tmp_path):
    config = write_experiment(tmp_path, "configs/synthetic/stationary_dev.yaml")
    command = [
        sys.executable,
        "-m",
        "drift_anomaly.experiments.lof_baseline",
        "--config",
        str(config),
        "--output",
        "results/check",
        "--scored-csv",
    ]
    subprocess.run(command, cwd=tmp_path, check=True, capture_output=True)
    output = tmp_path / "results/check"
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["detector"] == {
        "type": "lof_static",
        "n_neighbors": 20,
        "contamination": "auto",
        "novelty": True,
        "metric": "euclidean",
        "decision_rule": "score > -offset_",
    }
    assert manifest["warmup"] == 256 and manifest["split"] == "development"

    runtime = json.loads((output / "runtime.json").read_text())
    assert runtime["scored_count"] == 7680
    assert len(runtime["per_stream"]) == 2
    assert runtime["elapsed_seconds"] > 0
    assert runtime["scored_observations_per_second"] == pytest.approx(
        7680 / runtime["elapsed_seconds"]
    )

    expected = json.loads((output / "per_stream_metrics.json").read_text())
    assert expected[0]["pr_auc"] is None and expected[1]["pr_auc"] is not None
    observed = {row["stream_id"]: Counter() for row in expected}
    with (output / "scored_observations.csv").open(
        newline="", encoding="utf-8"
    ) as file:
        for row in csv.DictReader(file):
            truth, predicted = (
                bool(int(row["anomaly_label"])),
                bool(int(row["predicted_anomaly"])),
            )
            assert predicted == (float(row["score"]) > 1.5)
            assert row["threshold"] == "1.5" and row["regime"] == "A"
            key = ("t" if truth == predicted else "f") + ("p" if predicted else "n")
            counts = observed[row["stream_id"]]
            assert int(row["index"]) == 256 + sum(counts.values())
            counts[key] += 1
    aggregate = json.loads((output / "aggregate.json").read_text())
    assert aggregate["pooled"]["scored_count"] == 7680
    for key in ("tp", "fp", "tn", "fn"):
        assert all(row[key] == observed[row["stream_id"]][key] for row in expected)
        assert aggregate["pooled"][key] == sum(
            counts[key] for counts in observed.values()
        )
