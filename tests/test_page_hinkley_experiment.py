"""Validate the paired grid, exported comparison, and data safeguards."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from drift_anomaly.experiments import (
    adwin_baseline,
    drift_baseline,
    page_hinkley_baseline,
    static_baseline,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/experiments/page_hinkley_dev.yaml"
ADWIN = CONFIG.with_name("adwin_dev.yaml")


def test_configuration_uses_identical_scenarios():
    candidate = page_hinkley_baseline.load_experiment(CONFIG)
    reference = adwin_baseline.load_experiment(ADWIN)
    assert list(static_baseline.scenarios(candidate)) == list(
        static_baseline.scenarios(reference)
    )
    assert candidate.detector.min_instances == 30
    assert candidate.detector.delta == 0.005
    assert candidate.detector.threshold == 50.0
    assert candidate.detector.alpha == 0.9999
    assert candidate.detector.mode == "both"


def write_config(tmp_path, template, streams, seed=0):
    config = yaml.safe_load(template.read_text(encoding="utf-8"))
    config["streams"] = [str(ROOT / stream) for stream in streams]
    config["grid"] = {
        "seeds": [seed],
        "onsets": [1024],
        "shifts": [3.0],
        "durations": [128],
    }
    path = tmp_path / template.name
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
def test_invalid_data_stops_before_replay(tmp_path, monkeypatch, stream, seed, error):
    def unexpected(*args, **kwargs):
        pytest.fail("replay reached with a prohibited input")

    monkeypatch.setattr(drift_baseline, "replay_synthetic_development", unexpected)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match=error):
        page_hinkley_baseline.run_experiment(
            write_config(tmp_path, CONFIG, [stream], seed), Path("results/check")
        )
    assert not (tmp_path / "results").exists()


def test_cli_reuses_matching_policy_and_exports_comparison(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    streams = [
        "configs/synthetic/stationary_dev.yaml",
        "configs/synthetic/recurring_dev.yaml",
    ]
    reference_output = Path("results/adwin")
    adwin_baseline.run_experiment(
        write_config(tmp_path, ADWIN, streams), reference_output
    )
    candidate_config = write_config(tmp_path, CONFIG, streams)
    candidate_output = Path("results/comparison")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "drift_anomaly.experiments.page_hinkley_baseline",
            "--config",
            str(candidate_config),
            "--output",
            str(candidate_output),
            "--adwin-results",
            str(reference_output),
        ],
        check=True,
        capture_output=True,
    )

    def read(root, name):
        return json.loads((root / f"{name}.json").read_text(encoding="utf-8"))

    manifest = read(candidate_output, "manifest")
    reference_manifest = read(reference_output, "manifest")
    assert manifest["matching"] == reference_manifest["matching"]
    assert (
        manifest["detector"]["mode"] == "both"
        and manifest["detector"]["signal"] == "raw_value"
    )
    assert manifest["warmup"] == 256
    comparison = read(candidate_output, "comparison")
    assert comparison["adwin_git_commit"] == reference_manifest["git_commit"]
    assert comparison["page_hinkley_git_commit"] == manifest["git_commit"]
    assert comparison["pooled"]["true_drift_events"] == 6
    assert comparison["by_drift"]["none"]["true_drift_events"] == 0
    assert comparison["by_drift"]["recurring"]["stream_count"] == 2
    assert (
        comparison["pooled"]["adwin"] == read(reference_output, "aggregate")["pooled"]
    )
    assert (
        comparison["pooled"]["page_hinkley"]
        == read(candidate_output, "aggregate")["pooled"]
    )
    artifact = reference_output / "per_stream_metrics.json"
    rows = read(reference_output, "per_stream_metrics")
    recurring = next(row for row in rows if row["drift_type"] == "recurring")
    recurring["event_matches"][0]["window_end"] += 1
    artifact.write_text(json.dumps(rows), encoding="utf-8")
    with pytest.raises(
        ValueError, match="different drift truth or inconsistent alarms"
    ):
        page_hinkley_baseline.run_experiment(
            candidate_config, Path("results/rejected"), adwin_results=reference_output
        )
    assert not Path("results/rejected").exists()
