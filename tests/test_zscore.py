"""Static detector behavior, including the real causal replay interface."""

from dataclasses import replace

import pytest

from drift_anomaly.replay import Observation, replay
from drift_anomaly.zscore import StaticZScore, ZScoreConfig


def test_warmup_uses_population_standard_deviation_and_absolute_score():
    detector = StaticZScore(ZScoreConfig(threshold=3.0))
    detector.fit_initial((1.0, 3.0, 5.0, 7.0))
    assert detector.mean == 4.0
    assert detector.std == pytest.approx(5**0.5)
    assert detector.score_one(0.0).score == pytest.approx(4 / 5**0.5)
    assert detector.score_one(8.0).score == pytest.approx(4 / 5**0.5)


def test_inclusive_configurable_threshold_both_tails():
    detector = StaticZScore(ZScoreConfig(threshold=3.0))
    detector.fit_initial((-1.0, 1.0))
    for value in (3.0, -3.0):
        prediction = detector.score_one(value)
        assert prediction.predicted_anomaly is True
        assert prediction.metadata == {"threshold": 3.0}
    assert detector.score_one(2.999).predicted_anomaly is False
    other = StaticZScore(ZScoreConfig(threshold=4.0))
    other.fit_initial((-1.0, 1.0))
    assert other.score_one(3.0).predicted_anomaly is False


@pytest.mark.parametrize("values", [(0.0, 0.0), (-1e-20, 1e-20)])
def test_scale_floor_handles_zero_and_near_zero_variance(values):
    detector = StaticZScore(ZScoreConfig(threshold=3.0, minimum_std=1e-12))
    detector.fit_initial(values)
    original_std = detector.std
    assert original_std < detector.config.minimum_std
    assert detector.score_one(0.0).score == 0.0
    assert detector.score_one(4e-12).score == pytest.approx(4.0)
    assert detector.score_one(4e-12).predicted_anomaly is True
    assert detector.std == original_std


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_warmup_and_scoring_fail_clearly(value):
    detector = StaticZScore(ZScoreConfig(threshold=3.0))
    with pytest.raises(ValueError, match="warm-up requires finite"):
        detector.fit_initial((1.0, value))
    detector.fit_initial((-1.0, 1.0))
    with pytest.raises(ValueError, match="observation must be finite"):
        detector.score_one(value)


def test_empty_warmup_and_unrepresentable_score_fail_clearly():
    detector = StaticZScore(ZScoreConfig(threshold=3.0))
    with pytest.raises(ValueError, match="must be fitted"):
        detector.score_one(1.0)
    with pytest.raises(ValueError, match="cannot be empty"):
        detector.fit_initial(())
    detector.fit_initial((1.0, 1.0))
    with pytest.raises(ValueError, match="Z-score is non-finite"):
        detector.score_one(1.7e308)


def test_score_is_representable_when_difference_alone_overflows():
    detector = StaticZScore(ZScoreConfig(threshold=3.0))
    detector.fit_initial((-1.7e308, 0.0))
    assert detector.score_one(1.7e308).score == pytest.approx(3.0)


def test_update_preserves_mean_scale_and_score():
    detector = StaticZScore(ZScoreConfig(threshold=3.0))
    detector.fit_initial((-1.0, 1.0))
    before = detector.score_one(-3.0)
    for value in (500.0, 9.0, -302.0):
        assert detector.update_one(value) is None
        assert (detector.mean, detector.std) == (0.0, 1.0)
    assert detector.score_one(-3.0) == before


def test_replay_uses_only_warmup_and_is_deterministic_without_labels():
    calls = []

    class ObservedStaticZScore(StaticZScore):
        def score_one(self, value):
            calls.append(("score", value))
            return super().score_one(value)

        def update_one(self, value):
            calls.append(("update", value))
            return super().update_one(value)

    rows = [Observation(index, -1.0 if index % 2 else 1.0) for index in range(256)]
    rows.extend(
        [
            Observation(256, 3.0, True, "in_transition", "B"),
            Observation(257, 10_000.0, False, "post_drift", "B"),
        ]
    )
    config = ZScoreConfig(threshold=3.0)
    first = replay(iter(rows), lambda: ObservedStaticZScore(config))
    assert calls == [
        ("score", 3.0),
        ("update", 3.0),
        ("score", 10_000.0),
        ("update", 10_000.0),
    ]
    assert [row.prediction.score for row in first.scored_records()] == [3.0, 10_000.0]
    assert first.records == replay(rows, lambda: StaticZScore(config)).records

    altered = [replace(row, anomaly_label=False, regime="A") for row in rows]
    changed = replay(altered, lambda: StaticZScore(config))
    assert [row.prediction for row in changed.records] == [
        row.prediction for row in first.records
    ]
    assert first.records[256].observation.anomaly_label is True
    assert first.records[256].observation.regime == "B"
