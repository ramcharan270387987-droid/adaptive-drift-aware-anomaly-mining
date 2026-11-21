"""Verify the frozen causal controller with known alarm positions."""

from dataclasses import replace
from pathlib import Path
from statistics import median

import pytest

from drift_anomaly.experiments.selective_smoke import FROZEN_ZSCORE, stream_diagnostics
from drift_anomaly.replay import (
    DevelopmentReplay,
    Observation,
    ReplayProvenance,
    UpdateEvent,
    replay,
)
from drift_anomaly.selective_adaptation import Ablation, RefitBudget, SelectiveZScore
from drift_anomaly.zscore import StaticZScore


class ScriptedDrift:
    identifier = "scripted"

    def __init__(self, alarms):
        self.alarms = set(alarms)
        self.fit_count = 0
        self.seen = []

    def fit_initial(self, values):
        self.seen = list(values)
        self.fit_count += 1

    def update_one(self, value):
        position = len(self.seen)
        self.seen.append(value)
        if position in self.alarms:
            return UpdateEvent(drift_alarm=True)
        return None


def run(after, alarms=(256,), mode=Ablation.FULL, edited=False):
    values = [-1.0, 1.0] * 128 + [0.0] + after
    rows = [Observation(i, value) for i, value in enumerate(values)]
    if edited:
        rows = [
            replace(r, anomaly_label=True, drift_phase="in_transition", regime="B")
            for r in rows
        ]
    drift = ScriptedDrift(alarms)
    result = replay(
        rows, lambda: SelectiveZScore(StaticZScore(FROZEN_ZSCORE), drift, mode)
    )
    assert drift.fit_count == 1 and drift.seen == values
    return result


def diagnostics(result):
    provenance = ReplayProvenance(
        str(Path("test")),
        0,
        "none",
        "development",
        256,
        None,
        None,
        result.detector_id,
        "",
        {},
    )
    return stream_diagnostics(DevelopmentReplay(provenance, result, ()))


@pytest.mark.parametrize(
    ("first", "second", "passes"),
    [
        (0.50, 0.50, True),
        (-0.50, -0.50, True),
        (0.501, 0.6, True),
        (0.49, 0.6, False),
        (0.6, -0.6, False),
    ],
)
def test_two_nonoverlapping_medians_use_inclusive_signed_threshold(
    first, second, passes
):
    result = run([first] * 64 + [second] * 64)
    (proposal,) = diagnostics(result)["proposals"]
    assert proposal["alarm_index"] == 256
    assert proposal["reference_scale"] == 1
    (check,) = proposal["checkpoints"]
    assert check["index"] == 384
    assert check["block_medians"] == check["effective_shifts"] == [first, second]
    assert check["persistence_passed"] is passes
    assert check["candidate_indices"] == list(range(257, 385))
    assert proposal["status"] == ("refit" if passes else "incomplete")
    assert result.records[383].update is None


def test_filter_blocks_first_refit_then_accepts_192_checkpoint_and_scored_current_value():
    result = run([10.0] * 64 + [1.0] * 128 + [1.0], alarms=(256, 383, 384))
    log = diagnostics(result)
    assert [alarm["disposition"] for alarm in log["alarms"]] == [
        "accepted",
        "duplicate",
        "duplicate",
    ]
    (proposal,) = log["proposals"]
    early, later = proposal["checkpoints"]
    assert early["offset"] == 128 and early["persistence_passed"] is True
    assert (
        early["failures"] == ["insufficient_retained"] and early["retained_count"] == 64
    )
    assert early["filtered_indices"] == list(range(257, 321))
    assert later["offset"] == 192
    assert later["retained_count"] == 128 and later["retained_indices"][-1] == 448
    assert later["refit"]["before"] == {"mean": 0.0, "std": 1.0}
    assert later["refit"]["after"] == {"mean": 1.0, "std": 0.0}
    assert result.records[448].prediction.score == 1.0
    assert result.records[449].prediction.score == 0.0
    assert log["refit_input_uses"] == 128


def test_deadline_closes_failed_proposal_and_does_not_reuse_duplicate_alarm():
    log = diagnostics(run([3.0] * 257, alarms=(256, 512, 513)))
    first, second = log["proposals"]
    assert [c["index"] for c in first["checkpoints"]] == [384, 448, 512]
    assert all(
        c["persistence_passed"] and c["retained_count"] == 0
        for c in first["checkpoints"]
    )
    assert first["status"] == "closed" and second["status"] == "incomplete"
    assert second["alarm_index"] == 513
    assert log["alarms"][1]["disposition"] == "duplicate"


def test_cooldown_is_inclusive_and_recurring_proposal_uses_refitted_reference():
    values = [1.0] * 257 + [-1.0] * 128
    log = diagnostics(run(values, alarms=(256, 385, 512, 513)))
    first, second = log["proposals"]
    assert first["checkpoints"][0]["refit"]["cooldown_positions"] == {
        "first_position": 385,
        "last_position": 512,
    }
    assert [row["disposition"] for row in log["alarms"]] == [
        "accepted",
        "cooldown_suppressed",
        "cooldown_suppressed",
        "accepted",
    ]
    assert second["reference_mean"] == 1.0
    # Old zero-variance statistics reject the returned level despite passing persistence.
    assert second["checkpoints"][0]["persistence_passed"] is True
    assert second["checkpoints"][0]["failures"] == ["insufficient_retained"]


@pytest.mark.parametrize(
    ("mode", "offset", "expected_filtered"),
    [
        (Ablation.IMMEDIATE, 0, 0),
        (Ablation.PERSISTENCE, 128, 0),
        (Ablation.FILTERING, 192, 64),
        (Ablation.FULL, 192, 64),
    ],
)
def test_frozen_ablation_differences(mode, offset, expected_filtered):
    log = diagnostics(run([10.0] * 64 + [1.0] * 128, mode=mode))
    last = log["proposals"][0]["checkpoints"][-1]
    assert last["offset"] == offset and last["filtered_count"] == expected_filtered
    assert last["decision"] == "refit"
    assert last["refit"]["terminal"] is (offset == 192)
    if mode is Ablation.IMMEDIATE:
        assert last["candidate_indices"] == list(range(1, 257))
    else:
        assert last["candidate_indices"][0] == 257
    assert (last["refit"]["cooldown_positions"] is not None) is (mode is Ablation.FULL)


def test_refit_budget_suppresses_alarms_but_continues_scoring():
    result = run([1.0] * 20, alarms=range(256, 277), mode=Ablation.IMMEDIATE)
    log = diagnostics(result)
    assert log["refit_count"] == 15 and log["refit_input_uses"] == 3840
    assert [a["disposition"] for a in log["alarms"][15:]] == ["budget_suppressed"] * 6
    assert log["alarms"][-1]["budget"]["exhausted"] is True
    assert result.records[-1].prediction is not None


def test_input_budget_gate_blocks_whole_candidate_independently_of_refit_count():
    budget = RefitBudget(refits=4, input_uses=3640)
    assert budget.allows(200) and not budget.allows(201)
    with pytest.raises(ValueError, match="frozen budget"):
        budget.record(201)
    budget.record(200)
    assert budget.refits == 5 and budget.as_metadata()["exhausted"] is True


def test_replay_is_deterministic_and_does_not_pass_ground_truth_or_future_values():
    after = [1.0] * 193
    original = run(after)
    assert original.records == run(after).records
    edited = run(after[:-1] + [25.0], edited=True)
    assert all(
        a.prediction == b.prediction and a.update == b.update
        for a, b in zip(original.records[:-1], edited.records[:-1], strict=True)
    )
    assert original.records[-1].prediction != edited.records[-1].prediction
    assert median(after[:128]) == 1.0


def test_update_requires_original_score_and_warmup_is_fixed():
    controller = SelectiveZScore(StaticZScore(FROZEN_ZSCORE), ScriptedDrift(()))
    with pytest.raises(ValueError, match="256-observation"):
        controller.fit_initial((0.0,))
    controller.fit_initial((0.0,) * 256)
    with pytest.raises(ValueError, match="score the current"):
        controller.update_one(1.0)
    controller.score_one(1.0)
    with pytest.raises(ValueError, match="score the current"):
        controller.update_one(2.0)


def test_budget_block_closes_qualifying_proposal_without_partial_fit():
    drift = ScriptedDrift((256,))
    controller = SelectiveZScore(StaticZScore(FROZEN_ZSCORE), drift)

    def source():
        for i, value in enumerate([-1.0, 1.0] * 128):
            yield Observation(i, value)
        # Exercise the input guard without exhausting the independent refit counter.
        controller._budget = RefitBudget(refits=4, input_uses=3700)
        for i, value in enumerate([0.0] * 65 + [1.0] * 128, start=256):
            yield Observation(i, value)

    (proposal,) = diagnostics(replay(source(), lambda: controller))["proposals"]
    early, late = proposal["checkpoints"]
    assert early["failures"] == ["persistence_failed"]
    assert late["persistence_passed"] is True
    assert late["retained_count"] == 192
    assert late["failures"] == ["budget_blocked"]
    assert late["budget"]["remaining_input_uses"] == 140
    assert late["budget"]["refits"] == 4
    assert proposal["status"] == "closed"
