"""Validate River ADWIN integration without supplying labels to its state."""

from dataclasses import replace

import pytest
from river.drift import ADWIN

from drift_anomaly.adwin import ADWINConfig, ADWINDetector
from drift_anomaly.replay import Observation, replay

CONFIG = ADWINConfig(0.002, 32, 5, 5, 10, "raw_value")


def alarms(result):
    return [
        record.observation.index
        for record in result.scored_records()
        if record.update is not None and record.update.drift_alarm is True
    ]


def test_replay_matches_river_after_current_value_update_and_excludes_warmup():
    values = (0.0,) * 128 + (10.0,) * 320 + (0.0,) * 256
    reference = ADWIN()
    expected = []
    for index, value in enumerate(values):
        reference.update(value)
        if reference.drift_detected:
            expected.append(index)
    assert any(index < 256 for index in expected)
    assert any(index >= 256 for index in expected)

    rows = [
        Observation(i, value, i % 5 == 0, "in_transition", "B")
        for i, value in enumerate(values)
    ]
    result = replay(iter(rows), lambda: ADWINDetector(CONFIG))
    assert alarms(result) == [index for index in expected if index >= 256]
    assert all(record.update is None for record in result.records[:256])
    assert all(
        r.prediction.score is None and r.prediction.drift_alarm is None
        for r in result.scored_records()
    )


def test_results_do_not_depend_on_labels_or_future_observations():
    values = (0.0,) * 320 + (9.0,) * 320 + (0.0,) * 320
    rows = [Observation(i, value) for i, value in enumerate(values)]
    result = replay(rows, lambda: ADWINDetector(CONFIG))
    assert result.records == replay(rows, lambda: ADWINDetector(CONFIG)).records

    altered = [
        replace(row, anomaly_label=True, drift_phase="in_transition", regime="B")
        for row in rows
    ]
    altered[700:] = [replace(row, value=9.0) for row in altered[700:]]
    edited = replay(altered, lambda: ADWINDetector(CONFIG))
    assert alarms(result)
    assert [i for i in alarms(result) if i < 700] == [
        i for i in alarms(edited) if i < 700
    ]


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        ({"delta": float("nan")}, "delta"),
        ({"delta": 1.0}, "delta"),
        ({"delta": True}, "delta"),
        ({"clock": 0}, "clock"),
        ({"max_buckets": -1}, "max_buckets"),
        ({"min_window_length": 2.5}, "min_window_length"),
        ({"grace_period": -1}, "grace_period"),
        ({"signal": "anomaly_label"}, "raw_value"),
    ],
)
def test_invalid_config(settings, message):
    with pytest.raises(ValueError, match=message):
        replace(CONFIG, **settings)
