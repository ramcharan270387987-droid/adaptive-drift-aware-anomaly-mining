"""Verify the shared development command and Isolation Forest exports."""

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from drift_anomaly.experiments import (
    isolation_forest_baseline,
    static_baseline,
    zscore_baseline,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/experiments/isolation_forest_dev.yaml"


def test_config_uses_exact_zscore_scenarios():
    forest = isolation_forest_baseline.load_experiment(CONFIG)
    zscore = zscore_baseline.load_experiment(CONFIG.with_name("zscore_dev.yaml"))
    assert list(static_baseline.scenarios(forest)) == list(
        static_baseline.scenarios(zscore)
    )
    assert forest.detector.random_state == 42
    assert forest.detector.n_estimators == 100
    assert forest.detector.contamination == "auto"
    assert forest.detector.max_samples == 256
    assert forest.detector.threshold is None


def experiment_config(tmp_path, stream, seed=0):
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    config["streams"] = [str(ROOT / stream)]
    config["grid"]["seeds"] = [seed]
    config["detector"]["n_estimators"] = 4
    path = tmp_path / "test.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("stream", "seed", "message"),
    [
        ("configs/synthetic/gradual_holdout.yaml", 0, "development replay requires"),
        ("configs/synthetic/gradual_dev.yaml", 1000, "grid seeds"),
        ("configs/nab.yaml", 0, "invalid synthetic config fields"),
    ],
)
def test_invalid_inputs_stop_before_replay(
    tmp_path, monkeypatch, stream, seed, message
):
    def unexpected(*args, **kwargs):
        pytest.fail("invalid configuration reached replay")

    monkeypatch.setattr(static_baseline, "replay_synthetic_development", unexpected)
    monkeypatch.chdir(tmp_path)
    config = experiment_config(tmp_path, stream, seed)
    with pytest.raises(ValueError, match=message):
        isolation_forest_baseline.run_experiment(config, Path("results/check"))
    assert not (tmp_path / "results").exists()


def test_cli_uses_shared_metric_and_output_schema(tmp_path):
    config = experiment_config(tmp_path, "configs/synthetic/stationary_dev.yaml")
    command = [
        sys.executable,
        "-m",
        "drift_anomaly.experiments.isolation_forest_baseline",
        "--config",
        str(config),
        "--output",
        "results/check",
        "--scored-csv",
    ]
    subprocess.run(command, cwd=tmp_path, check=True, capture_output=True)
    output = tmp_path / "results/check"
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["split"] == "development" and manifest["warmup"] == 256
    assert manifest["detector"]["random_state"] == 42
    aggregate = json.loads((output / "aggregate.json").read_text())
    assert aggregate["stream_count"] == 2
    assert aggregate["pooled"]["scored_count"] == 7680
    metrics = json.loads((output / "per_stream_metrics.json").read_text())
    assert metrics[0]["pr_auc"] is None
    assert metrics[1]["pr_auc"] is not None
    assert all(row["threshold"] == 0.5 for row in metrics)
    with (output / "scored_observations.csv").open(
        newline="", encoding="utf-8"
    ) as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 7680
    assert rows[0]["index"] == rows[3840]["index"] == "256"
    assert rows[0]["regime"] == "A"
    assert all(
        int(row["predicted_anomaly"]) == (float(row["score"]) > float(row["threshold"]))
        for row in rows
    )
    assert sum(int(row["anomaly_label"]) for row in rows) == 12
