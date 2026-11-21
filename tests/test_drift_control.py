"""Test exact reconciliation, established configs, and holdout guards."""

import csv
import json
from pathlib import Path

import pytest
import yaml

from drift_anomaly.experiments import (
    adwin_baseline,
    drift_control,
    page_hinkley_baseline,
    zscore_baseline,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = ROOT / "configs/experiments"


def small_config(
    tmp_path, filename, stream="configs/synthetic/recurring_dev.yaml", seed=0
):
    config = yaml.safe_load((CONFIGS / filename).read_text(encoding="utf-8"))
    config["streams"] = [str(ROOT / stream)]
    config["grid"] = {
        "seeds": [seed],
        "onsets": [1024],
        "shifts": [3.0],
        "durations": [128],
    }
    path = tmp_path / filename
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


@pytest.fixture
def references(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    inputs = {}
    for name, module, opts in (
        ("zscore", zscore_baseline, {"scored_csv": True}),
        ("adwin", adwin_baseline, {}),
        ("page_hinkley", page_hinkley_baseline, {}),
    ):
        config = small_config(tmp_path, f"{name}_dev.yaml")
        results = Path("results") / name
        module.run_experiment(config, results, **opts)
        inputs[f"{name}_config"] = config
        inputs[f"{name}_results"] = results
    return inputs


def read(root, name):
    return json.loads((root / f"{name}.json").read_text(encoding="utf-8"))


def test_complete_control_export_reconciles_all_three_references(references):
    output = Path("results/control")
    report = drift_control.run_experiment(output, **references)
    assert report["stream_count"] == 2
    assert read(output, "control_report")["stream_count"] == 2
    manifest = read(output, "manifest")
    assert manifest["warmup"] == 256
    assert manifest["anomaly_adaptation"] is False
    common = read(references["zscore_results"], "aggregate")
    assert report["controls"]["static_zscore"]["anomaly"] == common
    for label in ("adwin", "page_hinkley"):
        controls = read(output, "control_report")["controls"]
        variant = controls[f"zscore_{label}_no_adaptation"]
        assert variant["anomaly"] == common
        assert variant["drift"] == read(references[f"{label}_results"], "aggregate")
        assert variant["scored_rows_verified"] == 7680
        assert variant["anomaly_outputs_exact"] and variant["drift_diagnostics_exact"]
        assert (
            manifest["detectors"][label]
            == read(references[f"{label}_results"], "manifest")["detector"]
        )
        assert manifest["references"][label]["git_commit"]
    assert len(read(output, "per_stream_checks")) == 2


@pytest.mark.parametrize("column", [6, 7])
def test_tampered_anomaly_score_or_prediction_aborts_without_publishing(
    references, column
):
    path = references["zscore_results"] / "scored_observations.csv"
    with path.open(newline="", encoding="utf-8") as file:
        records = list(csv.reader(file))
    records[1][column] = "999"
    with path.open("w", newline="", encoding="utf-8") as file:
        csv.writer(file).writerows(records)
    with pytest.raises(ValueError, match="invariance check failed.*scored CSV"):
        drift_control.run_experiment(Path("results/failed"), **references)
    assert not Path("results/failed").exists()


def test_tampered_drift_alarms_abort_without_publishing(references):
    root = references["adwin_results"]
    metrics = read(root, "per_stream_metrics")
    metrics[0]["alarm_indices"][0] += 1
    (root / "per_stream_metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    with pytest.raises(
        ValueError, match="invariance check failed for adwin metrics and diagnostics"
    ):
        drift_control.run_experiment(Path("results/failed"), **references)
    assert not Path("results/failed").exists()


def test_detector_config_must_match_reference_manifest(references):
    path = references["page_hinkley_config"]
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    config["detector"]["threshold"] = 55.0
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(
        ValueError, match="reference must match the committed configuration"
    ):
        drift_control.run_experiment(Path("results/failed"), **references)
    assert not Path("results/failed").exists()


@pytest.mark.parametrize(
    ("stream", "seed", "message"),
    [
        ("configs/synthetic/recurring_holdout.yaml", 0, "development replay requires"),
        ("configs/synthetic/recurring_dev.yaml", 1000, "grid seeds"),
        ("configs/nab.yaml", 0, "invalid synthetic config fields"),
    ],
)
def test_forbidden_inputs_are_rejected_before_reading_any_reference(
    tmp_path, stream, seed, message
):
    config = small_config(tmp_path, "zscore_dev.yaml", stream=stream, seed=seed)
    with pytest.raises(ValueError, match=message):
        drift_control.run_experiment(
            Path("results/failed"),
            zscore_config=config,
            zscore_results=Path("does-not-exist"),
            adwin_results=Path("does-not-exist"),
            page_hinkley_results=Path("does-not-exist"),
        )
