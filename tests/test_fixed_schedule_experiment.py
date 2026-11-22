"""Verify shared development selection and fixed-schedule reports."""

import json
from pathlib import Path

import pytest
import yaml

from drift_anomaly.experiments import (
    adwin_baseline,
    drift_control,
    fixed_schedule_baseline,
    page_hinkley_baseline,
    static_baseline,
    zscore_baseline,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = ROOT / "configs/experiments"


def write_config(
    tmp_path, name, stream="configs/synthetic/stationary_dev.yaml", seed=0
):
    config = yaml.safe_load((CONFIGS / f"{name}_dev.yaml").read_text(encoding="utf-8"))
    config["streams"] = [str(ROOT / stream)]
    config["grid"]["seeds"] = [seed]
    path = tmp_path / f"{name}.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def test_fixed_config_uses_identical_development_grid_and_zscore_parameters():
    fixed = fixed_schedule_baseline.load_experiment(CONFIGS / "fixed_schedule_dev.yaml")
    static = zscore_baseline.load_experiment(CONFIGS / "zscore_dev.yaml")
    assert list(static_baseline.scenarios(fixed)) == list(
        static_baseline.scenarios(static)
    )
    assert (
        fixed.detector.warmup
        == fixed.detector.window_size
        == fixed.detector.adaptation_interval
        == 256
    )
    assert fixed.detector.threshold == static.detector.threshold
    assert fixed.detector.minimum_std == static.detector.minimum_std


@pytest.mark.parametrize(
    ("stream", "seed", "message"),
    [
        ("configs/synthetic/sudden_holdout.yaml", 0, "development replay requires"),
        ("configs/synthetic/sudden_dev.yaml", 1000, "grid seeds"),
        ("configs/nab.yaml", 0, "invalid synthetic config fields"),
    ],
)
def test_disallowed_configs_stop_before_evaluation(
    tmp_path, monkeypatch, stream, seed, message
):
    monkeypatch.chdir(tmp_path)
    config = write_config(tmp_path, "fixed_schedule", stream, seed)

    def fail(*args, **kwargs):
        pytest.fail("disallowed configuration reached evaluation")

    monkeypatch.setattr(static_baseline, "evaluate_baseline", fail)
    with pytest.raises(ValueError, match=message):
        fixed_schedule_baseline.run_experiment(
            config, Path("results/blocked"), control_results=Path("missing")
        )
    assert not Path("results").exists()


def test_reports_reconcile_counts_and_the_committed_control_schema(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    inputs = {}
    for name, module, kwargs in (
        ("zscore", zscore_baseline, {"scored_csv": True}),
        ("adwin", adwin_baseline, {}),
        ("page_hinkley", page_hinkley_baseline, {}),
    ):
        config = write_config(tmp_path, name)
        output = Path("results") / name
        module.run_experiment(config, output, **kwargs)
        inputs[f"{name}_config"] = config
        inputs[f"{name}_results"] = output
    control = Path("results/control")
    drift_control.run_experiment(control, **inputs)
    path = Path("results/fixed")
    config = write_config(tmp_path, "fixed_schedule")
    comparison = fixed_schedule_baseline.run_experiment(
        config, path, control_results=control
    )
    rows = json.loads((path / "per_stream_metrics.json").read_text(encoding="utf-8"))
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["warmup"] == manifest["detector"]["adaptation_interval"] == 256
    assert comparison["stream_count"] == len(rows) == 2
    assert comparison["adaptation"]["refit_count"] == 30
    assert (
        comparison["methods"]["static_zscore"]
        == comparison["methods"]["zscore_adwin_no_adaptation"]
    )
    assert (
        comparison["methods"]["static_zscore"]
        == comparison["methods"]["zscore_page_hinkley_no_adaptation"]
    )
    assert rows[0]["adaptation"]["contaminated_refit_count"] == 0
    assert rows[1]["adaptation"]["contaminated_refit_count"] > 0
    assert [r["index"] for r in rows[1]["adaptation"]["refits"]] == list(
        range(511, 4096, 256)
    )
    metrics = comparison["methods"]["fixed_schedule"]
    for key in ("tp", "fp", "tn", "fn"):
        assert metrics[key] == sum(row[key] for row in rows)
    assert sum(metrics[key] for key in ("tp", "fp", "tn", "fn")) == 7680
