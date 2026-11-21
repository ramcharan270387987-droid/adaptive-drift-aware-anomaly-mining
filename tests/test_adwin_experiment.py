"""Test paired development input guards and the drift export schema."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from drift_anomaly.experiments import adwin_baseline, lof_baseline, static_baseline
from drift_anomaly.synthetic import generate_stream

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/experiments/adwin_dev.yaml"


def test_shared_grid_keeps_all_scenarios_and_pair_truth():
    adwin = adwin_baseline.load_experiment(CONFIG)
    lof = lof_baseline.load_experiment(CONFIG.with_name("lof_dev.yaml"))
    scenarios = list(static_baseline.scenarios(adwin))
    assert scenarios == list(static_baseline.scenarios(lof))
    assert len(scenarios) == 250
    _, _, scenario = next(
        case for case in scenarios if case[2].drift_type == "recurring"
    )
    pairs = [
        (name, generate_stream(config))
        for name, config in static_baseline.paired_variants(scenario)
    ]
    assert [name for name, _ in pairs] == ["clean", "injected"]
    clean, injected = [stream for _, stream in pairs]
    assert clean.drift_events == injected.drift_events
    assert clean.anomaly_positions == () and len(injected.anomaly_positions) == 12


def small_config(tmp_path, streams, seed=0):
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    config["streams"] = [str(ROOT / path) for path in streams]
    config["grid"] = {
        "seeds": [seed],
        "onsets": [1024],
        "shifts": [3.0],
        "durations": [128],
    }
    path = tmp_path / "test.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("stream", "seed", "message"),
    [
        ("configs/synthetic/sudden_holdout.yaml", 0, "development replay requires"),
        ("configs/synthetic/sudden_dev.yaml", 1000, "grid seeds"),
        ("configs/nab.yaml", 0, "invalid synthetic config fields"),
    ],
)
def test_rejected_config_does_not_reach_replay(
    tmp_path, monkeypatch, stream, seed, message
):
    def unexpected(*args, **kwargs):
        pytest.fail("guarded input reached replay")

    monkeypatch.setattr(adwin_baseline, "replay_synthetic_development", unexpected)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match=message):
        adwin_baseline.run_experiment(
            small_config(tmp_path, [stream], seed), Path("results/audit")
        )
    assert not (tmp_path / "results").exists()


def test_cli_exports_match_and_pair_reconciliation(tmp_path):
    config = small_config(
        tmp_path,
        [
            "configs/synthetic/stationary_dev.yaml",
            "configs/synthetic/recurring_dev.yaml",
        ],
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "drift_anomaly.experiments.adwin_baseline",
            "--config",
            str(config),
            "--output",
            "results/check",
        ],
        check=True,
        cwd=tmp_path,
        capture_output=True,
    )
    output = tmp_path / "results/check"

    def read(name):
        return json.loads((output / f"{name}.json").read_text(encoding="utf-8"))

    manifest = read("manifest")
    assert manifest["detector"]["signal"] == "raw_value"
    assert manifest["detector"]["delta"] == 0.002
    assert manifest["warmup"] == manifest["first_eligible_index"] == 256
    assert manifest["matching"]["post_transition_window"] == 128
    rows = read("per_stream_metrics")
    aggregate = read("aggregate")
    assert len(rows) == 4
    assert aggregate["pooled"]["true_drift_events"] == 6
    assert aggregate["pooled"]["scored_count"] == 4 * 3840
    for row in rows:
        matched = {
            match["alarm_index"]
            for match in row["event_matches"]
            if match["delay"] is not None
        }
        false = set(row["false_alarm_indices"])
        assert not matched & false
        assert matched | false == set(row["alarm_indices"])
        assert len(matched) == row["detected_events"]
        assert all(i >= 256 for i in row["alarm_indices"])
    assert aggregate["pooled"]["false_alarms"] == sum(
        row["false_alarms"] for row in rows
    )
    pairs = read("paired_false_alarms")
    assert len(pairs) == 2
    for pair in pairs:
        assert (
            pair["injected_minus_clean"]
            == pair["injected_false_alarms"] - pair["clean_false_alarms"]
        )
    assert aggregate["paired_false_alarms"]["pooled"][
        "net_additional_false_alarms"
    ] == sum(row["injected_minus_clean"] for row in pairs)
