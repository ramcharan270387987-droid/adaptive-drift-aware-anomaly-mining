"""Causal static Isolation Forest behavior and exact sklearn scoring parity."""

from dataclasses import replace

import numpy as np
import pytest
from sklearn.ensemble import IsolationForest

from drift_anomaly.isolation_forest import IsolationForestConfig, StaticIsolationForest
from drift_anomaly.replay import Observation, replay

CONFIG = IsolationForestConfig(42, 12, "auto", 256)


@pytest.mark.parametrize("contamination", ["auto", 0.1])
def test_univariate_scores_and_decisions_match_sklearn_at_split_boundaries(
    contamination,
):
    rng = np.random.default_rng(4)
    values = rng.normal(size=256)
    detector = StaticIsolationForest(replace(CONFIG, contamination=contamination))
    detector.fit_initial(tuple(values))
    reference = IsolationForest(
        random_state=42, n_estimators=12, contamination=contamination, max_samples=256
    ).fit(values.reshape(-1, 1))
    splits = np.asarray(detector._boundaries, dtype=np.float32)
    inputs = np.concatenate(
        (
            [-20, 20],
            rng.normal(size=80),
            splits,
            np.nextafter(splits, np.float32(-np.inf)),
            np.nextafter(splits, np.float32(np.inf)),
        )
    )
    expected = -reference.score_samples(inputs.reshape(-1, 1))
    decisions = reference.predict(inputs.reshape(-1, 1)) == -1
    actual = [detector.score_one(float(value)) for value in inputs]
    np.testing.assert_array_equal([prediction.score for prediction in actual], expected)
    np.testing.assert_array_equal(
        [prediction.predicted_anomaly for prediction in actual], decisions
    )
    assert actual[0].metadata["threshold"] == -reference.offset_


def test_strict_configured_threshold_and_constant_warmup():
    warmup = (2.0,) * 256
    reference = IsolationForest(random_state=42, n_estimators=12, max_samples=256)
    reference.fit(np.asarray(warmup).reshape(-1, 1))
    threshold = float(-reference.score_samples([[50.0]])[0])
    detector = StaticIsolationForest(replace(CONFIG, threshold=threshold))
    detector.fit_initial(warmup)
    prediction = detector.score_one(50.0)
    assert prediction.score == threshold
    assert prediction.predicted_anomaly is False
    assert prediction.metadata == {"threshold": threshold}
    lower = StaticIsolationForest(replace(CONFIG, threshold=threshold - 0.01))
    lower.fit_initial(warmup)
    assert lower.score_one(50.0).predicted_anomaly is True


def test_replay_fits_only_the_256_point_prefix_and_keeps_model_fixed(monkeypatch):
    fitted = []
    original = IsolationForest.fit

    def spy(model, values):
        fitted.append(values.copy())
        return original(model, values)

    monkeypatch.setattr(IsolationForest, "fit", spy)
    calls = []

    class ObservedDetector(StaticIsolationForest):
        def score_one(self, value):
            calls.append(("score", value))
            return super().score_one(value)

        def update_one(self, value):
            calls.append(("update", value))
            super().update_one(value)

    detector = ObservedDetector(CONFIG)
    prefix = tuple(np.linspace(-1, 1, 256))
    rows = [Observation(index, value) for index, value in enumerate(prefix)]
    rows += [
        Observation(256, 10.0, True, "in_transition", "B"),
        Observation(257, -10.0),
    ]
    result = replay(iter(rows), lambda: detector)
    assert len(fitted) == 1
    assert fitted[0].shape == (256, 1)
    np.testing.assert_array_equal(
        fitted[0].ravel(), np.asarray(prefix, dtype=np.float32)
    )
    assert calls == [
        ("score", 10.0),
        ("update", 10.0),
        ("score", -10.0),
        ("update", -10.0),
    ]
    model = detector.model
    trees = [tree.tree_.threshold.copy() for tree in model.estimators_]
    for value in (-90.0, 100.0, 0.25):
        detector.update_one(value)
    assert detector.model is model and len(fitted) == 1
    for tree, before in zip(model.estimators_, trees, strict=True):
        np.testing.assert_array_equal(tree.tree_.threshold, before)
    assert result.records[256].prediction == detector.score_one(10.0)


def test_fixed_seed_replay_is_deterministic_and_ignores_future_values_and_labels():
    rows = [
        Observation(index, float(value))
        for index, value in enumerate(np.linspace(-2, 2, 260))
    ]
    first = replay(rows, lambda: StaticIsolationForest(CONFIG))
    assert (
        first.records
        == replay(iter(rows), lambda: StaticIsolationForest(CONFIG)).records
    )
    altered = [replace(row, anomaly_label=True, regime="B") for row in rows]
    altered[-1] = replace(altered[-1], value=10_000.0)
    changed = replay(altered, lambda: StaticIsolationForest(CONFIG))
    assert [row.prediction for row in first.records[:-1]] == [
        row.prediction for row in changed.records[:-1]
    ]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"random_state": -1}, "random_state"),
        ({"n_estimators": True}, "n_estimators"),
        ({"contamination": 0.7}, "contamination"),
        ({"max_samples": 0}, "max_samples"),
        ({"max_samples": 2.0}, "max_samples"),
        ({"threshold": float("nan")}, "threshold"),
    ],
)
def test_invalid_configuration(kwargs, message):
    with pytest.raises(ValueError, match=message):
        replace(CONFIG, **kwargs)


def test_fitting_and_scoring_fail_explicitly_on_invalid_observations():
    detector = StaticIsolationForest(CONFIG)
    with pytest.raises(ValueError, match="must be fitted"):
        detector.score_one(0)
    with pytest.raises(ValueError, match="finite float32-range"):
        detector.fit_initial((float("nan"),) * 256)
    with pytest.raises(ValueError, match="max_samples"):
        detector.fit_initial((0.0, 1.0))
    detector.fit_initial((0.0, 1.0) * 128)
    with pytest.raises(ValueError, match="within float32 range"):
        detector.score_one(1e100)
