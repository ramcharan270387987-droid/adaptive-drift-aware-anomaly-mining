"""Verify the established synthetic alarm-matching policy."""

import pytest

from drift_anomaly.drift_evaluation import match_alarms, summarize_drift
from drift_anomaly.synthetic import Distribution, DriftEvent

A, B = Distribution(0.0, 1.0), Distribution(1.5, 1.0)


def event(start, end, returning=False):
    if returning:
        return DriftEvent(start, end, "B", "A", B, A, "instantaneous")
    return DriftEvent(
        start, end, "A", "B", A, B, "linear" if start != end else "instantaneous"
    )


def test_matches_first_alarm_with_inclusive_window_and_delay_from_onset():
    result = match_alarms(
        (event(300, 320), event(600, 600), event(900, 900)),
        (299, 310, 448, 728, 1029),
        scored_count=1000,
        warmup_last_index=255,
    )
    assert [m.alarm_index for m in result.matches] == [310, 728, None]
    assert [m.window_end for m in result.matches] == [448, 728, 1028]
    assert [m.delay for m in result.matches] == [10, 128, None]
    assert result.false_alarm_indices == (299, 448, 1029)
    summary = summarize_drift([result])
    assert summary["true_drift_events"] == 3 and summary["missed_events"] == 1
    assert summary["detection_rate"] == 2 / 3
    assert summary["mean_delay"] == summary["median_delay"] == 69
    assert summary["delay_histogram"] == {10: 1, 128: 1}
    assert summary["alarm_count"] == 5 and summary["false_alarms"] == 3


def test_recurring_transitions_have_separate_matches_and_windows_do_not_overlap():
    result = match_alarms(
        (event(300, 300), event(340, 340, returning=True), event(400, 400)),
        (340, 380, 399, 400),
        scored_count=1000,
    )
    assert [m.window_end for m in result.matches] == [339, 399, 528]
    assert [m.alarm_index for m in result.matches] == [None, 340, 400]
    assert result.false_alarm_indices == (380, 399)


def test_stationary_controls_and_warmup_exclusion_are_transparent():
    stationary = match_alarms((), (256, 400), scored_count=500, warmup_last_index=255)
    summary = summarize_drift([stationary])
    assert summary["false_alarms"] == summary["false_alarms_per_stream"] == 2
    assert summary["false_alarms_per_1000_observations"] == 4
    assert summary["detection_rate"] is None and summary["mean_delay"] is None
    assert summary["unavailable"]["detection_rate"]

    early = event(200, 310)
    result = match_alarms(
        (early, event(512, 512)), (300, 550), scored_count=800, warmup_last_index=255
    )
    assert result.excluded_events == (early,)
    assert result.false_alarm_indices == (300,)
    assert summarize_drift([result])["excluded_warmup_events"] == 1
    with pytest.raises(ValueError, match="post-warm-up alarms"):
        match_alarms((), (100,), scored_count=500, warmup_last_index=255)
