"""Check deterministic construction and labels, without fitting any models."""

import csv
import json
import math
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from drift_anomaly.synthetic import (
    DRIFT_TYPES,
    SyntheticConfig,
    generate_pair,
    generate_stream,
    load_config,
)

CONFIG_DIR = Path(__file__).resolve().parents[1] / "configs/synthetic"
DRIFT_SCENARIOS = DRIFT_TYPES[1:]


def config_for(drift_type, **overrides):
    parameters = {
        "drift_type": drift_type,
        "seed": 42,
        "n_observations": 4000,
        "drift_start": 1000,
        "pre_mean": -1.0,
        "pre_std": 0.75,
        "post_mean": 3.0,
        "post_std": 1.5,
    }
    if drift_type in ("gradual", "incremental"):
        parameters["drift_duration"] = 200
    return SyntheticConfig(**(parameters | overrides))


@pytest.mark.parametrize("drift_type", DRIFT_SCENARIOS)
def test_determinism_and_pairing(drift_type):
    config = config_for(drift_type, anomaly_count=12)
    clean, injected = generate_pair(config)
    repeat = generate_stream(config)
    different = generate_stream(replace(config, seed=43))

    assert injected.observations.tobytes() == repeat.observations.tobytes()
    np.testing.assert_array_equal(injected.index, np.arange(config.n_observations))
    assert injected.anomaly_positions == repeat.anomaly_positions
    assert injected.drift_events == clean.drift_events == different.drift_events
    assert injected.anomaly_positions != different.anomaly_positions
    assert not np.array_equal(injected.observations, different.observations)
    np.testing.assert_array_equal(injected.regime, clean.regime)
    np.testing.assert_array_equal(injected.phase, clean.phase)
    np.testing.assert_array_equal(injected.means, clean.means)
    np.testing.assert_array_equal(injected.stds, clean.stds)
    assert not clean.anomaly_mask.any()
    mask = injected.anomaly_mask
    np.testing.assert_array_equal(np.flatnonzero(mask), injected.anomaly_positions)
    np.testing.assert_array_equal(
        injected.observations[~mask], clean.observations[~mask]
    )
    np.testing.assert_allclose(
        np.abs(injected.observations[mask] - clean.observations[mask]),
        config.anomaly_magnitude * config.pre_std,
    )

    assert mask.sum() == 12
    assert min(injected.anomaly_positions) >= config.warmup
    assert min(np.diff(injected.anomaly_positions)) >= config.min_anomaly_separation
    first = injected.drift_events[0]
    priority = (
        mask[first.start : first.end + 1]
        if drift_type in ("gradual", "incremental")
        else mask[first.start + 1 : first.start + 65]
    )
    assert priority.sum() == 3
    for event in injected.drift_events:
        assert not mask[event.start]
        assert not mask[event.end]


@pytest.mark.parametrize("drift_type", DRIFT_SCENARIOS)
def test_stationary_segments_match_requested_distributions(drift_type):
    config = config_for(drift_type)
    result = generate_stream(config)
    segments = (
        (result.observations[: config.drift_start], config.pre_mean, config.pre_std),
        (
            result.observations[result.drift_events[-1].end + 1 :],
            config.post_mean,
            config.post_std,
        ),
    )
    for values, mean, std in segments:
        assert math.isclose(values.mean(), mean, abs_tol=0.15)
        assert math.isclose(values.std(), std, abs_tol=0.15)


def test_sudden_boundary_uses_the_new_regime():
    result = generate_stream(config_for("sudden"))
    event = result.drift_events[0]
    assert (event.start, event.end, event.from_regime, event.to_regime) == (
        1000,
        1000,
        "A",
        "B",
    )
    assert list(result.regime[999:1002]) == ["A", "B", "B"]
    assert list(result.phase[999:1002]) == ["pre_drift", "in_transition", "post_drift"]


def test_gradual_interval_contains_both_mixture_components():
    result = generate_stream(config_for("gradual"))
    event = result.drift_events[0]
    assert (event.start, event.end, event.transition_rule) == (
        1000,
        1199,
        "linear_mixture_probability",
    )
    np.testing.assert_array_equal(
        np.flatnonzero(result.phase == "in_transition"), np.arange(1000, 1200)
    )
    assert list(result.regime[[999, 1000, 1199, 1200]]) == ["A", "A", "B", "B"]
    assert set(result.regime[1010:1190]) == {"A", "B"}
    np.testing.assert_array_equal(
        result.means, np.where(result.regime == "A", -1.0, 3.0)
    )


def test_incremental_trajectory_interpolates_mean_and_std():
    config = config_for("incremental", post_std=0.25)
    result = generate_stream(config)
    event = result.drift_events[0]
    assert (event.start, event.end) == (1000, 1199)
    transition = slice(event.start, event.end + 1)
    assert set(result.regime[transition]) == {"ramp"}
    assert np.all(np.diff(result.means[transition]) > 0)
    assert np.all(np.diff(result.stds[transition]) < 0)
    np.testing.assert_allclose(result.means[transition], np.linspace(-1.0, 3.0, 200))
    np.testing.assert_allclose(result.stds[transition], np.linspace(0.75, 0.25, 200))


def test_recurring_drift_returns_to_a_and_reports_every_event():
    result = generate_stream(config_for("recurring"))
    assert [
        (e.start, e.end, e.from_regime, e.to_regime) for e in result.drift_events
    ] == [
        (1000, 1000, "A", "B"),
        (1512, 1512, "B", "A"),
        (2024, 2024, "A", "B"),
    ]
    assert set(result.regime[1512:2024]) == {"A"}
    assert (result.means[1512:2024] == -1.0).all()
    assert (result.stds[1512:2024] == 0.75).all()
    assert set(result.regime[2024:]) == {"B"}


@pytest.mark.parametrize("drift_type", DRIFT_SCENARIOS)
def test_excluding_transitions_keeps_all_drifts_free_of_injection(drift_type):
    result = generate_stream(
        config_for(drift_type, anomaly_count=50, anomaly_placement="exclude_transition")
    )
    assert result.anomaly_mask.sum() == 50
    for event in result.drift_events:
        assert not result.anomaly_mask[event.start : event.end + 1].any()


def test_stationary_controls_use_fraction_and_have_no_events():
    config = SyntheticConfig(
        "none", 4, n_observations=100, warmup=10, anomaly_fraction=0.05
    )
    clean, injected = generate_pair(config)
    assert len(injected.anomaly_positions) == 5
    assert len(clean.anomaly_positions) == 0
    assert clean.drift_events == injected.drift_events == ()
    assert set(injected.phase) == {"stationary"}
    assert set(injected.regime) == {"A"}


def test_default_boundaries_are_excluded_and_can_be_explicitly_included():
    config = SyntheticConfig(
        "sudden",
        1,
        n_observations=4,
        drift_start=2,
        warmup=0,
        min_anomaly_separation=1,
        anomaly_count=3,
        anomaly_placement="anywhere",
    )
    assert generate_stream(config).anomaly_positions == (0, 1, 3)
    enabled = replace(config, allow_boundary_anomalies=True, anomaly_count=4)
    assert generate_stream(enabled).anomaly_positions == (0, 1, 2, 3)


def test_dense_but_feasible_spacing_is_constructed():
    config = SyntheticConfig(
        "none",
        3,
        n_observations=7,
        warmup=0,
        min_anomaly_separation=3,
        anomaly_count=3,
    )
    assert generate_stream(config).anomaly_positions == (0, 3, 6)


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        ({"seed": -1}, "seed must be an integer"),
        ({"seed": True}, "seed must be an integer"),
        ({"split": "unknown"}, "split must be"),
        ({"warmup": 4000}, "warmup must be less"),
        ({"drift_start": None}, "drift_start must be an integer"),
        ({"drift_duration": 1}, "drift_duration must be an integer"),
        ({"drift_start": 3900}, "at least one observation after"),
        ({"pre_std": 0}, "must be positive"),
        ({"post_mean": float("nan")}, "must be a finite number"),
        ({"anomaly_count": 2, "anomaly_fraction": 0.1}, "specify anomaly_count or"),
        ({"anomaly_fraction": 1.1}, "must be between 0 and 1"),
        ({"anomaly_placement": "elsewhere"}, "invalid anomaly_placement"),
    ],
)
def test_invalid_config(settings, message):
    with pytest.raises(ValueError, match=message):
        config_for("gradual", **settings)


def test_infeasible_protocol_quota_has_clear_error():
    config = config_for("gradual", drift_duration=3, anomaly_count=12)
    with pytest.raises(ValueError, match="cannot place the requested anomalies under"):
        generate_stream(config)


@pytest.mark.parametrize(
    "name", ("sudden", "gradual", "incremental", "recurring", "stationary")
)
def test_protocol_configs_have_separated_seeds_and_settings(name):
    dev = load_config(CONFIG_DIR / f"{name}_dev.yaml")
    holdout = load_config(CONFIG_DIR / f"{name}_holdout.yaml")
    assert dev.split == "development"
    assert holdout.split == "final_evaluation"
    assert dev.seed in range(10)
    assert holdout.seed in range(1000, 1020)
    if name != "stationary":
        assert dev.drift_start in (1024, 2048)
        assert holdout.drift_start in (1536, 2560)
        assert dev.post_mean in (1.5, 3.0)
        assert holdout.post_mean in (1.0, 2.25)
    if name in ("gradual", "incremental"):
        assert dev.drift_duration in (128, 256)
        assert holdout.drift_duration in (192, 384)
    assert dev.injection_count == holdout.injection_count == 12
    assert len(generate_stream(dev).anomaly_positions) == 12


def test_cli_exports_reproducible_csv_and_metadata(tmp_path):
    config = tmp_path / "example.yaml"
    config.write_text(
        "drift_type: sudden\nseed: 0\nn_observations: 24\ndrift_start: 10\n"
        "warmup: 4\nmin_anomaly_separation: 2\nanomaly_count: 2\n"
        "priority_anomaly_count: 1\npost_change_window: 4\n",
        encoding="utf-8",
    )
    command = [
        sys.executable,
        "-m",
        "drift_anomaly.synthetic",
        "--config",
        str(config),
        "--output",
    ]
    first = tmp_path / "first"
    second = tmp_path / "second"
    clean = tmp_path / "clean"
    completed = subprocess.run(
        [*command, str(first)], check=True, capture_output=True, text=True
    )
    subprocess.run([*command, str(second)], check=True, capture_output=True)
    subprocess.run([*command, str(clean), "--clean"], check=True, capture_output=True)
    assert "24 points, 1 drift events, 2 anomalies" in completed.stdout
    for filename in ("stream.csv", "metadata.json"):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()

    metadata = json.loads((first / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["rng"]["bit_generator"] == "PCG64"
    assert metadata["generator_revision"].startswith("sha256:")
    assert metadata["drift_events"][0]["start"] == 10
    assert metadata["parameters"]["drift_start"] == 10
    with (first / "stream.csv").open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert [int(row["index"]) for row in rows] == list(range(24))
    assert [
        int(row["index"]) for row in rows if row["anomaly_label"] == "1"
    ] == metadata["anomaly_positions"]
    clean_meta = json.loads((clean / "metadata.json").read_text(encoding="utf-8"))
    assert clean_meta["anomaly_positions"] == []
    assert clean_meta["drift_events"] == metadata["drift_events"]
    repeat = subprocess.run(
        [*command, str(first)], check=False, capture_output=True, text=True
    )
    assert repeat.returncode == 1
    assert "already exists" in repeat.stderr


def test_yaml_requires_known_fields(tmp_path):
    path = tmp_path / "invalid.yaml"
    path.write_text("drift_type: none\nseed: 1\nn_observatons: 32\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid synthetic config fields"):
        load_config(path)
