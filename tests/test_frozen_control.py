"""Test frozen anomaly scoring with independent, causal drift alarms."""

from dataclasses import replace
from pathlib import Path

import pytest

from drift_anomaly.adwin import ADWINDetector
from drift_anomaly.experiments import (
    adwin_baseline,
    page_hinkley_baseline,
    zscore_baseline,
)
from drift_anomaly.frozen_control import FrozenZScoreWithDrift
from drift_anomaly.page_hinkley import PageHinkleyDetector
from drift_anomaly.replay import Observation, replay
from drift_anomaly.zscore import StaticZScore

CONFIG = Path(__file__).resolve().parents[1] / "configs/experiments"


def test_replay_scores_before_drift_update_and_keeps_fitted_zscore_frozen():
    calls = []

    class Anomaly(StaticZScore):
        def fit_initial(self, values):
            calls.append(("anomaly_fit", values))
            super().fit_initial(values)

        def score_one(self, value):
            calls.append(("score", value))
            return super().score_one(value)

        def update_one(self, value):
            pytest.fail("Z-score was offered a post-warm-up update")

    class Drift(ADWINDetector):
        def fit_initial(self, values):
            calls.append(("drift_fit", values))

        def update_one(self, value):
            calls.append(("drift_update", value))

    anomaly = Anomaly(
        zscore_baseline.load_experiment(CONFIG / "zscore_dev.yaml").detector
    )
    drift = Drift(adwin_baseline.load_experiment(CONFIG / "adwin_dev.yaml").detector)
    prefix = (-1.0, 1.0) * 128

    def source():
        for index, value in enumerate(prefix):
            yield Observation(index, value)
        assert calls == [("anomaly_fit", prefix), ("drift_fit", prefix)]
        yield Observation(256, 3.0, True, "in_transition", "B")
        assert calls[-2:] == [("score", 3.0), ("drift_update", 3.0)]
        yield Observation(257, -100.0)
        assert calls[-2:] == [("score", -100.0), ("drift_update", -100.0)]

    result = replay(source(), lambda: FrozenZScoreWithDrift(anomaly, drift))
    assert (anomaly.mean, anomaly.std) == (0.0, 1.0)
    assert [r.prediction.score for r in result.scored_records()] == [3.0, 100.0]
    assert all(r.prediction.predicted_anomaly for r in result.scored_records())


@pytest.mark.parametrize(
    ("baseline", "constructor", "filename"),
    [
        (adwin_baseline, ADWINDetector, "adwin_dev.yaml"),
        (page_hinkley_baseline, PageHinkleyDetector, "page_hinkley_dev.yaml"),
    ],
)
def test_combined_predictions_and_alarms_equal_both_baselines_and_ignore_truth(
    baseline, constructor, filename
):
    anomaly = zscore_baseline.load_experiment(CONFIG / "zscore_dev.yaml").detector
    drift = baseline.load_experiment(CONFIG / filename).detector
    values = (0.0, 1.0) * 192 + (6.0, 7.0) * 192 + (0.0, 1.0) * 192
    observations = [Observation(index, value) for index, value in enumerate(values)]
    labeled = [
        replace(
            row, anomaly_label=index % 2 == 0, drift_phase="in_transition", regime="B"
        )
        for index, row in enumerate(observations)
    ]
    static = replay(observations, lambda: StaticZScore(anomaly))
    drift_only = replay(observations, lambda: constructor(drift))
    assert any(r.update is not None for r in drift_only.scored_records())
    combined = replay(
        labeled,
        lambda: FrozenZScoreWithDrift(StaticZScore(anomaly), constructor(drift)),
    )
    assert [row.prediction for row in combined.records] == [
        row.prediction for row in static.records
    ]
    assert [row.update for row in combined.records] == [
        row.update for row in drift_only.records
    ]
    assert combined.records[256].observation.drift_phase == "in_transition"
