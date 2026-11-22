"""Check static LOF against sklearn's novelty API and causal replay."""

from dataclasses import replace

import numpy as np
import pytest
from sklearn.neighbors import LocalOutlierFactor

from drift_anomaly.lof import DECISION_RULE, LOFConfig, StaticLOF
from drift_anomaly.replay import Observation, replay

CONFIG = LOFConfig(20, "auto", True, "euclidean", DECISION_RULE)


@pytest.mark.parametrize("contamination", ["auto", 0.05])
def test_scores_and_predictions_match_public_sklearn_novelty_api(contamination):
    warmup = np.linspace(-1.0, 1.0, 256)
    values = np.array([0.0, 0.25, warmup[5], warmup[12:14].mean(), -10.0, 10.0])
    detector = StaticLOF(replace(CONFIG, contamination=contamination))
    detector.fit_initial(tuple(warmup))
    reference = LocalOutlierFactor(
        n_neighbors=20,
        novelty=True,
        contamination=contamination,
        metric="euclidean",
        algorithm="kd_tree",
        n_jobs=1,
    ).fit(warmup.reshape(-1, 1))
    actual = [detector.score_one(float(value)) for value in values]
    queries = values.reshape(-1, 1)
    np.testing.assert_array_equal(
        [p.score for p in actual], -reference.score_samples(queries)
    )
    np.testing.assert_array_equal(
        [p.predicted_anomaly for p in actual], reference.predict(queries) == -1
    )
    np.testing.assert_array_equal(
        [p.predicted_anomaly for p in actual], reference.decision_function(queries) < 0
    )
    assert all(p.metadata["threshold"] == -reference.offset_ for p in actual)
    assert actual[-1].score > actual[0].score
    assert detector.model.novelty is True


def test_replay_fits_only_the_warmup_and_scores_before_noop_update(monkeypatch):
    calls = []
    original_fit = LocalOutlierFactor.fit

    def spy(model, values):
        calls.append(("fit", values.copy()))
        return original_fit(model, values)

    monkeypatch.setattr(LocalOutlierFactor, "fit", spy)

    class ObservedLOF(StaticLOF):
        def score_one(self, value):
            calls.append(("score", value))
            return super().score_one(value)

        def update_one(self, value):
            calls.append(("update", value))
            super().update_one(value)

    prefix = np.linspace(-1, 1, 256)
    rows = [Observation(i, float(value)) for i, value in enumerate(prefix)]
    rows += [Observation(256, 8.0, True, "in_transition", "B"), Observation(257, -4.0)]
    detector = ObservedLOF(CONFIG)
    result = replay(iter(rows), lambda: detector)
    assert calls[0][0] == "fit"
    np.testing.assert_array_equal(calls[0][1], prefix.reshape(-1, 1))
    assert calls[1:] == [
        ("score", 8.0),
        ("update", 8.0),
        ("score", -4.0),
        ("update", -4.0),
    ]
    model = detector.model
    fitted_scores = model.negative_outlier_factor_.copy()
    detector.update_one(19.0)
    assert detector.model is model
    assert sum(call[0] == "fit" for call in calls) == 1
    np.testing.assert_array_equal(model.negative_outlier_factor_, fitted_scores)
    assert result.records[256].prediction == detector.score_one(8.0)


def test_fixed_reference_is_deterministic_and_ignores_future_values_and_labels():
    rows = [
        Observation(i, float(value)) for i, value in enumerate(np.linspace(-2, 2, 260))
    ]
    first = replay(rows, lambda: StaticLOF(CONFIG))
    same = replay(iter(rows), lambda: StaticLOF(CONFIG))
    assert first.records == same.records
    altered = [replace(row, anomaly_label=True, regime="B") for row in rows]
    altered[-1] = replace(altered[-1], value=100.0)
    changed = replay(altered, lambda: StaticLOF(CONFIG))
    assert [row.prediction for row in first.records[:-1]] == [
        row.prediction for row in changed.records[:-1]
    ]
    assert first.records[-1].prediction != changed.records[-1].prediction


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"n_neighbors": 0}, "n_neighbors"),
        ({"n_neighbors": 256}, "n_neighbors"),
        ({"n_neighbors": True}, "n_neighbors"),
        ({"novelty": False}, "novelty"),
        ({"contamination": 0.6}, "contamination"),
        ({"metric": "cosine"}, "metric"),
        ({"decision_rule": "score >= 1.5"}, "decision_rule"),
    ],
)
def test_configuration_validation(kwargs, error):
    with pytest.raises(ValueError, match=error):
        replace(CONFIG, **kwargs)


def test_rejects_insufficient_and_nonfinite_fit_values():
    detector = StaticLOF(CONFIG)
    with pytest.raises(ValueError, match="must be fitted"):
        detector.score_one(0.0)
    with pytest.raises(ValueError, match="more observations than n_neighbors"):
        detector.fit_initial((0.0,) * 20)
    with pytest.raises(ValueError, match="warm-up requires finite"):
        detector.fit_initial((0.0,) * 255 + (float("nan"),))
    detector.fit_initial((0.0,) * 256)
    with pytest.raises(ValueError, match="LOF observation must be finite"):
        detector.score_one(float("inf"))
