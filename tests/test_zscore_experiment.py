"""Development grid, held-out input safeguards, and command output."""

import csv
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest
import yaml

from drift_anomaly.experiments import static_baseline
from drift_anomaly.experiments import zscore_baseline as experiment

ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT = ROOT / "configs/experiments/zscore_dev.yaml"


def test_development_config_covers_the_protocol_grid():
    config = experiment.load_experiment(DEVELOPMENT)
    assert config.detector.threshold == 3.0
    assert config.grid["seeds"] == tuple(range(10))
    assert Counter(
        case.drift_type for _, _, case in static_baseline.scenarios(config)
    ) == {
        "none": 10,
        "sudden": 40,
        "gradual": 80,
        "incremental": 80,
        "recurring": 40,
    }


def write_config(tmp_path, paths, *, seed=0):
    data = yaml.safe_load(DEVELOPMENT.read_text(encoding="utf-8"))
    data["streams"] = [str(path) for path in paths]
    data["grid"]["seeds"] = [seed]
    path = tmp_path / "experiment.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("path", "seed", "error"),
    [
        ("configs/synthetic/sudden_holdout.yaml", 0, "development replay requires"),
        ("configs/synthetic/sudden_dev.yaml", 1000, "grid seeds"),
        ("configs/nab.yaml", 0, "invalid synthetic config fields"),
        ("data/raw/nab/final/nyc_taxi.csv", 0, "synthetic development YAML configs"),
    ],
)
def test_disallowed_inputs_stop_before_any_replay(
    tmp_path, monkeypatch, path, seed, error
):
    def unexpected(*args, **kwargs):
        pytest.fail("replay was called before inputs were fully validated")

    monkeypatch.setattr(static_baseline, "replay_synthetic_development", unexpected)
    monkeypatch.chdir(tmp_path)
    config = write_config(
        tmp_path,
        [ROOT / "configs/synthetic/stationary_dev.yaml", ROOT / path],
        seed=seed,
    )
    with pytest.raises(ValueError, match=error):
        experiment.run_experiment(config, Path("results/check"))
    assert not (tmp_path / "results").exists()


def test_cli_exports_configuration_metrics_and_scored_rows(tmp_path):
    config = write_config(tmp_path, [ROOT / "configs/synthetic/stationary_dev.yaml"])
    command = [
        sys.executable,
        "-m",
        "drift_anomaly.experiments.zscore_baseline",
        "--config",
        str(config),
        "--output",
        "results/check",
        "--scored-csv",
    ]
    completed = subprocess.run(
        command, cwd=tmp_path, capture_output=True, text=True, check=True
    )
    assert "2 streams, 7680 scored observations" in completed.stdout
    output = tmp_path / "results/check"
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["detector"] == {
        "type": "zscore_static",
        "threshold": 3.0,
        "minimum_std": 1e-12,
    }
    assert manifest["split"] == "development" and manifest["warmup"] == 256
    assert manifest["grid"]["seeds"] == [0]
    assert "git_commit" in manifest and manifest["project_version"]
    per_stream = json.loads(
        (output / "per_stream_metrics.json").read_text(encoding="utf-8")
    )
    assert [(row["anomaly_count"], row["scored_count"]) for row in per_stream] == [
        (0, 3840),
        (12, 3840),
    ]
    assert per_stream[0]["pr_auc"] is None and per_stream[0]["unavailable"]["pr_auc"]
    aggregate = json.loads((output / "aggregate.json").read_text(encoding="utf-8"))
    assert aggregate["pooled"]["scored_count"] == 7680
    with (output / "scored_observations.csv").open(
        encoding="utf-8", newline=""
    ) as file:
        scored = list(csv.DictReader(file))
    assert len(scored) == 7680
    assert scored[0]["index"] == scored[3840]["index"] == "256"
    assert scored[0]["threshold"] == "3.0"
    assert scored[0]["regime"] == "A"
    assert sum(int(row["anomaly_label"]) for row in scored) == 12
