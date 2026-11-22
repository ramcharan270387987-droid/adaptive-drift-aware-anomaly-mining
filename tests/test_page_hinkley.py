"""Check causal Page-Hinkley alarms and River reset behavior."""

from dataclasses import replace

import pytest
from river.drift import PageHinkley

from drift_anomaly.page_hinkley import PageHinkleyConfig, PageHinkleyDetector
from drift_anomaly.replay import Observation, replay

CONFIG = PageHinkleyConfig(30, 0.005, 50.0, 0.9999, "both", "raw_value")


def alarms(result):
    return [
        record.observation.index
        for record in result.scored_records()
        if record.update is not None and record.update.drift_alarm is True
    ]


def test_initialization_and_river_owned_reset_are_separate_from_alarm_step():
    detector = PageHinkleyDetector(CONFIG)
    detector.fit_initial((0.0,) * 256)
    model = detector._detector
    assert isinstance(model, PageHinkley)
    assert model.min_instances == 30 and model.mode == "both"
    assert model._x_mean.n == 256

    for _ in range(64):
        event = detector.update_one(4.0)
        if event is not None:
            break
    assert event is not None and event.drift_alarm is True
    assert model._x_mean.n > 256
    assert detector.update_one(4.0) is None
    assert detector._detector is model
    assert model._x_mean.n == 1


def test_recurring_alarms_match_river_and_warmup_alarms_are_excluded():
    values = (0.0,) * 128 + (4.0,) * 256 + (0.0,) * 256 + (4.0,) * 256
    reference = PageHinkley()
    expected = []
    for index, value in enumerate(values):
        reference.update(value)
        if reference.drift_detected:
            expected.append(index)
    assert any(i < 256 for i in expected)

    rows = [
        Observation(i, value, True, "in_transition", "B")
        for i, value in enumerate(values)
    ]
    result = replay(rows, lambda: PageHinkleyDetector(CONFIG))
    observed = alarms(result)
    assert observed == [i for i in expected if i >= 256]
    assert len(observed) == 2
    assert 384 <= observed[0] < 512
    assert 640 <= observed[1] < 768
    assert all(record.update is None for record in result.records[:256])
    assert all(
        record.prediction.drift_alarm is None for record in result.scored_records()
    )


def test_determinism_ground_truth_independence_and_causality():
    values = (0.0,) * 320 + (4.0,) * 320 + (0.0,) * 320
    observations = [Observation(i, value) for i, value in enumerate(values)]
    before = replay(observations, lambda: PageHinkleyDetector(CONFIG))
    assert (
        before.records
        == replay(observations, lambda: PageHinkleyDetector(CONFIG)).records
    )
    changed = [
        replace(row, anomaly_label=True, drift_phase="post_drift", regime="B")
        for row in observations
    ]
    assert alarms(before) == alarms(
        replay(changed, lambda: PageHinkleyDetector(CONFIG))
    )
    changed[600:] = [replace(row, value=4.0) for row in changed[600:]]
    after = alarms(replay(changed, lambda: PageHinkleyDetector(CONFIG)))
    assert [i for i in alarms(before) if i < 600] == [i for i in after if i < 600]


def test_stationary_constant_signal_with_isolated_injections_does_not_trigger():
    clean = [Observation(i, 0.0, False) for i in range(640)]
    injected = clean.copy()
    injected[320] = Observation(320, 6.0, True)
    injected[512] = Observation(512, -6.0, True)
    assert alarms(replay(clean, lambda: PageHinkleyDetector(CONFIG))) == []
    assert alarms(replay(injected, lambda: PageHinkleyDetector(CONFIG))) == []


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"min_instances": 0}, "min_instances"),
        ({"min_instances": True}, "min_instances"),
        ({"delta": -0.01}, "delta"),
        ({"threshold": 0.0}, "threshold"),
        ({"threshold": float("nan")}, "threshold"),
        ({"alpha": 1.1}, "alpha"),
        ({"mode": "none"}, "mode"),
        ({"signal": "anomaly_label"}, "raw_value"),
    ],
)
def test_configuration_validation(fields, message):
    with pytest.raises(ValueError, match=message):
        replace(CONFIG, **fields)
