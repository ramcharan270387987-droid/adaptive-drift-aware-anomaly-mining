"""Check frozen post-hoc attribution and common comparison windows."""

from pathlib import Path

import pytest
import yaml

from drift_anomaly.adaptation_evaluation import (
    Refit,
    match_refits,
    post_refit_windows,
    window_alarms,
)
from drift_anomaly.experiments import selective_evaluation
from drift_anomaly.replay import (
    DevelopmentReplay,
    Observation,
    ReplayProvenance,
    replay,
)
from drift_anomaly.synthetic import Distribution, DriftEvent
from drift_anomaly.zscore import StaticZScore, ZScoreConfig

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/experiments/adwin_dev.yaml"


def event(start, end):
    return DriftEvent(
        start, end, "A", "B", Distribution(0, 1), Distribution(1, 1), "instantaneous"
    )


def test_match_earliest_eligible_refit_without_reusing_extra_or_crossing_next_onset():
    events = [event(300, 300), event(500, 530)]
    too_early_alarm = Refit(340, 299, ())
    matched = Refit(350, 320, ())
    duplicate = Refit(380, 340, ())
    after_next_onset = Refit(500, 400, ())
    late_alarm = Refit(670, 659, ())
    boundary = Refit(914, 658, ())
    result, unnecessary = match_refits(
        events,
        [boundary, duplicate, too_early_alarm, late_alarm, after_next_onset, matched],
        warmup_last=255,
    )
    assert [r.refit for r in result] == [matched, boundary]
    assert [r.onset_delay for r in result] == [50, 414]
    assert [r.alarm_delay for r in result] == [30, 256]
    assert unnecessary == [too_early_alarm, duplicate, after_next_onset, late_alarm]


def test_fixed_refit_window_and_warmup_exclusion():
    initial = Refit(270, None, ())
    final = Refit(684, None, ())
    matches, unused = match_refits(
        [event(100, 110), event(300, 300)], [initial, final], warmup_last=255
    )
    assert [r.refit for r in matches] == [final]
    assert matches[0].alarm_delay is None and unused == [initial]


def test_post_adaptation_windows_clip_at_next_refit_onset_and_stream_end():
    refits = [
        Refit(10, None, ()),
        Refit(25, None, ()),
        Refit(100, None, ()),
        Refit(110, None, ()),
    ]
    assert post_refit_windows(refits, refits, [50], 110) == [
        (11, 24),
        (26, 49),
        (101, 109),
    ]


def test_projection_counts_nominal_scored_indices_once():
    rows = [
        Observation(0, 0.0, False),
        Observation(1, 10.0, False),
        Observation(2, 10.0, True),
        Observation(3, 0.0, False),
    ]
    result = replay(rows, lambda: StaticZScore(ZScoreConfig(3.0)), warmup=1)
    provenance = ReplayProvenance(
        "test", 0, "none", "development", 1, None, None, result.detector_id, "", {}
    )
    run = DevelopmentReplay(provenance, result, ())
    assert window_alarms(run, [(1, 3), (2, 3)]) == {
        "window_count": 2,
        "observations": 3,
        "fp": 1,
        "tn": 1,
        "nominal_count": 2,
        "false_positive_rate": 0.5,
    }


def test_exact_frozen_arms_and_sensitivity_settings():
    arms = selective_evaluation._arms(None)
    assert [arm.name for arm in arms if arm.selective] == [
        "full",
        "immediate",
        "persistence",
        "filtering",
        "full_0.75",
        "full_1.00",
    ]
    assert [arm.factory().persistence_cutoff for arm in arms if arm.selective] == [
        0.5,
        0.5,
        0.5,
        0.5,
        0.75,
        1.0,
    ]
    assert [arm.name for arm in arms if not arm.selective] == [
        "static_zscore",
        "zscore_adwin_no_adaptation",
        "zscore_page_hinkley_no_adaptation",
        "fixed_schedule",
    ]


@pytest.mark.parametrize(
    ("stream", "seed", "message"),
    [
        ("configs/synthetic/sudden_holdout.yaml", 0, "development replay requires"),
        ("configs/synthetic/sudden_dev.yaml", 2000, "grid seeds"),
        ("configs/nab.yaml", 0, "invalid synthetic config fields"),
    ],
)
def test_evaluation_rejects_disallowed_data_before_replay(
    tmp_path, stream, seed, message
):
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    config["streams"] = [str(ROOT / stream)]
    config["grid"]["seeds"] = [seed]
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        selective_evaluation.run_experiment(path, tmp_path / "blocked")
    assert not (tmp_path / "blocked").exists()
