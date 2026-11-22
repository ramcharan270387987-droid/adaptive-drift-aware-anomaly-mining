"""Check that scheduled refits consume only observations already scored."""

from dataclasses import replace
from pathlib import Path
from statistics import mean, pstdev

import pytest

from drift_anomaly.experiments.fixed_schedule_baseline import adaptation_diagnostics
from drift_anomaly.fixed_schedule import FixedScheduleConfig, FixedScheduleZScore
from drift_anomaly.replay import (
    DevelopmentReplay,
    Observation,
    ReplayProvenance,
    replay,
)

CONFIG = FixedScheduleConfig(3.0, adaptation_interval=2, window_size=3, warmup=4)


def run_rows(rows):
    return replay(rows, lambda: FixedScheduleZScore(CONFIG), warmup=CONFIG.warmup)


def test_score_before_refit_schedule_and_window_boundaries():
    values = [-1.0, 1.0, -1.0, 1.0, 3.0, 5.0, 7.0, 9.0]
    rows = [Observation(2 * i, value, i in (4, 6)) for i, value in enumerate(values)]
    result = run_rows(iter(rows))
    scores = list(result.scored_records())
    assert scores[0].update is None and scores[0].prediction.score == 3.0
    assert scores[1].prediction.score == 5.0
    assert scores[2].update is None
    assert scores[2].prediction.score == pytest.approx(4 / pstdev([1, 3, 5]))
    assert scores[3].prediction.score == pytest.approx(6 / pstdev([1, 3, 5]))
    provenance = ReplayProvenance(
        str(Path("test")),
        0,
        "none",
        "development",
        4,
        None,
        None,
        result.detector_id,
        "",
        {},
    )
    diagnostics = adaptation_diagnostics(DevelopmentReplay(provenance, result, ()))
    assert diagnostics["refit_count"] == 2
    assert diagnostics["contaminated_refit_count"] == 2
    first, last = diagnostics["refits"]
    assert [first["index"], last["index"]] == [10, 14]
    assert (first["first_window_index"], first["last_window_index"]) == (6, 10)
    assert first["before"] == {"mean": 0.0, "std": 1.0}
    assert first["after"] == {
        "mean": mean([1.0, 3.0, 5.0]),
        "std": pstdev([1.0, 3.0, 5.0]),
    }
    assert last["before"] == first["after"]
    assert last["after"] == {"mean": 7.0, "std": pstdev([5.0, 7.0, 9.0])}
    assert first["injected_anomaly_indices"] == [8]
    assert last["injected_anomaly_indices"] == [12]


def test_deterministic_and_independent_of_labels_and_future_values():
    rows = [Observation(i, float(i)) for i in range(10)]
    original = run_rows(rows)
    assert original.records == run_rows(rows).records
    mutated = [
        replace(row, anomaly_label=True, drift_phase="post_drift", regime="B")
        for row in rows
    ]
    mutated[-1] = replace(mutated[-1], value=-500.0)
    edited = run_rows(mutated)
    for old, new in zip(original.records[:-1], edited.records[:-1], strict=True):
        assert old.prediction == new.prediction and old.update == new.update
    assert original.records[-1].prediction != edited.records[-1].prediction


def test_zero_variance_refit_preserves_static_numerical_floor():
    config = replace(CONFIG, minimum_std=0.25, window_size=2)
    rows = [
        Observation(i, value) for i, value in enumerate([1.0] * 4 + [3.0, 3.0, 3.5])
    ]
    first, trigger, later = replay(
        rows, lambda: FixedScheduleZScore(config), warmup=4
    ).scored_records()
    assert first.prediction.score == trigger.prediction.score == 8.0
    assert trigger.update.metadata["refit"]["after"] == {"mean": 3.0, "std": 0.0}
    assert later.prediction.score == 2.0 and later.prediction.predicted_anomaly is False


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"adaptation_interval": 0}, "adaptation_interval"),
        ({"window_size": True}, "window_size"),
        ({"window_size": 7}, "first scheduled refit"),
        ({"warmup": 0}, "warmup"),
        ({"threshold": -1}, "threshold"),
        ({"minimum_std": float("nan")}, "minimum_std"),
    ],
)
def test_invalid_configuration(fields, message):
    with pytest.raises(ValueError, match=message):
        replace(CONFIG, **fields)


def test_warmup_must_match_configuration():
    with pytest.raises(ValueError, match="configured warmup"):
        FixedScheduleZScore(CONFIG).fit_initial((0.0, 1.0))
