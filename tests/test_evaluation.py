"""Known small examples for point metrics and drift phase diagnostics."""

import pytest

from drift_anomaly.evaluation import AnomalyEvaluation
from drift_anomaly.replay import Observation, Prediction, ReplayRecord
from drift_anomaly.synthetic import Distribution, DriftEvent


def row(index, label, prediction, score, phase="stationary", *, warmup=False):
    return ReplayRecord(
        Observation(index, 0, label, phase), warmup, Prediction(score, prediction)
    )


def test_confusion_metrics_pr_auc_and_phase_counts_ignore_warmup():
    evaluation = AnomalyEvaluation()
    evaluation.add(
        [
            row(0, False, True, 15, "pre_drift", warmup=True),
            row(1, True, True, 9, "pre_drift"),
            row(2, False, True, 8, "in_transition"),
            row(3, True, False, 2, "post_drift"),
            row(4, False, False, 1, "post_drift"),
            row(5, False, True, 7, "post_drift"),
        ]
    )
    metric = evaluation.summary()
    assert (metric["tp"], metric["fp"], metric["tn"], metric["fn"]) == (1, 2, 1, 1)
    assert metric["precision"] == pytest.approx(1 / 3)
    assert metric["recall"] == 0.5
    assert metric["f1"] == 0.4
    assert metric["false_positive_rate"] == pytest.approx(2 / 3)
    assert metric["pr_auc"] == 0.75
    assert metric["unavailable"] == {}
    assert [
        metric["false_positives_by_phase"][key]["fp"]
        for key in ("pre_drift", "in_transition", "post_drift")
    ] == [0, 1, 1]


def test_missing_classes_predictions_and_scores_are_reported():
    clean = AnomalyEvaluation()
    clean.add([row(0, False, False, 0)])
    metric = clean.summary()
    assert metric["false_positive_rate"] == 0
    for name in ("precision", "recall", "f1", "pr_auc"):
        assert metric[name] is None and metric["unavailable"][name]
    mixed = AnomalyEvaluation()
    mixed.add([row(0, True, False, None), row(1, False, False, 1)])
    metric = mixed.summary()
    assert metric["precision"] is None
    assert metric["recall"] == metric["f1"] == 0
    assert metric["pr_auc"] is None
    assert "finite scores" in metric["unavailable"]["pr_auc"]


def test_all_positive_stream_has_no_false_positive_rate():
    only_positive = AnomalyEvaluation()
    only_positive.add([row(0, True, True, 5)])
    metric = only_positive.summary()
    assert metric["f1"] == 1
    assert metric["false_positive_rate"] is None
    assert metric["unavailable"]["false_positive_rate"] == "no nominal observations"


def test_drift_window_is_inclusive_clipped_and_counts_nominal_only():
    a, b = Distribution(0, 1), Distribution(1.5, 1)
    events = (
        DriftEvent(4, 5, "A", "B", a, b, "linear"),
        DriftEvent(6, 6, "B", "A", b, a, "instantaneous"),
    )
    evaluation = AnomalyEvaluation()
    evaluation.add(
        [
            row(3, False, True, 9, "pre_drift"),
            row(4, False, True, 8, "in_transition"),
            row(5, True, True, 10, "in_transition"),
            row(6, False, False, 1, "in_transition"),
            row(262, False, True, 5, "post_drift"),
            row(263, False, True, 5, "post_drift"),
        ],
        events,
    )
    assert evaluation.summary()["drift_window"] == {
        "fp": 2,
        "tn": 1,
        "nominal_count": 3,
        "false_positive_rate": 2 / 3,
    }


def test_merged_metrics_pool_ranked_scores_and_confusion_counts():
    a, b = AnomalyEvaluation(), AnomalyEvaluation()
    a.add([row(0, True, True, 7)])
    b.add([row(0, False, False, 1)])
    assert a.summary()["pr_auc"] is None and b.summary()["pr_auc"] is None
    a.merge(b)
    metric = a.summary()
    assert metric["pr_auc"] == metric["f1"] == 1.0
    assert metric["false_positives_by_phase"]["stationary"]["nominal_count"] == 1
