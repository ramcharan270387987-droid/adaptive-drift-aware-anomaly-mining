"""Frozen selective-refit policy for the causal streaming replay interface."""

from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum
from statistics import median

from drift_anomaly.replay import (
    DEFAULT_WARMUP,
    JsonValue,
    Prediction,
    StreamingDetector,
    UpdateEvent,
)
from drift_anomaly.zscore import StaticZScore

CHECKPOINTS = (128, 192, 256)
BLOCK_SIZE = 64
WINDOW_SIZE = 256
MIN_RETAINED = 128
SHIFT_CUTOFF = 0.50
COOLDOWN = 128
MAX_REFITS = 15
MAX_FIT_INPUTS = 3840


class Ablation(StrEnum):
    IMMEDIATE = "immediate"
    PERSISTENCE = "persistence"
    FILTERING = "filtering"
    FULL = "full"


@dataclass(frozen=True)
class CandidatePoint:
    position: int
    value: float
    anomalous: bool


@dataclass
class Proposal:
    alarm_position: int
    mean: float
    scale: float
    points: list[CandidatePoint] = field(default_factory=list)


@dataclass
class RefitBudget:
    refits: int = 0
    input_uses: int = 0

    def allows(self, count: int) -> bool:
        return self.refits < MAX_REFITS and self.input_uses + count <= MAX_FIT_INPUTS

    def record(self, count: int) -> None:
        if not self.allows(count):
            raise ValueError("refit exceeds the frozen budget")
        self.refits += 1
        self.input_uses += count

    def as_metadata(self) -> dict[str, JsonValue]:
        return {
            "refits": self.refits,
            "refit_input_uses": self.input_uses,
            "remaining_refits": MAX_REFITS - self.refits,
            "remaining_input_uses": MAX_FIT_INPUTS - self.input_uses,
            "exhausted": not self.allows(MIN_RETAINED),
        }


class SelectiveZScore:
    """Record the original prediction, then update drift and consider a refit."""

    def __init__(
        self,
        anomaly: StaticZScore,
        drift: StreamingDetector,
        mode: Ablation = Ablation.FULL,
    ) -> None:
        self._anomaly = anomaly
        self._drift = drift
        self.mode = Ablation(mode)
        self.identifier = f"zscore_selective_{self.mode}"
        self._clear_state()

    def _clear_state(self) -> None:
        self._position = DEFAULT_WARMUP - 1
        self._cooldown_end = self._position
        self._proposal: Proposal | None = None
        self._pending_score: tuple[float, bool] | None = None
        self._history: deque[CandidatePoint] = deque(maxlen=WINDOW_SIZE)
        self._budget = RefitBudget()

    def fit_initial(self, values: tuple[float, ...]) -> None:
        if len(values) != DEFAULT_WARMUP:
            raise ValueError("selective adaptation requires a 256-observation warm-up")
        self._clear_state()
        self._anomaly.fit_initial(values)
        self._drift.fit_initial(values)
        if self.mode is Ablation.IMMEDIATE:
            self._history.extend(
                CandidatePoint(i, value, False) for i, value in enumerate(values)
            )

    def score_one(self, value: float) -> Prediction:
        if self._pending_score is not None:
            raise ValueError("update the previous observation before scoring again")
        prediction = self._anomaly.score_one(value)
        assert prediction.predicted_anomaly is not None
        self._pending_score = (value, prediction.predicted_anomaly)
        return prediction

    def update_one(self, value: float) -> UpdateEvent | None:
        if self._pending_score is None or self._pending_score[0] != value:
            raise ValueError(
                "score the current value before updating selective adaptation"
            )
        _, flagged = self._pending_score
        self._pending_score = None
        self._position += 1
        position = self._position
        signal = self._drift.update_one(value)
        alarm = signal is not None and signal.drift_alarm is True
        point = CandidatePoint(position, value, flagged)
        if self.mode is Ablation.IMMEDIATE:
            self._history.append(point)

        metadata: dict[str, JsonValue] = {}
        if self._proposal is not None:
            proposal = self._proposal
            if alarm:
                metadata["alarm_disposition"] = "duplicate"
                metadata["active_alarm_position"] = proposal.alarm_position
            proposal.points.append(point)
            offset = position - proposal.alarm_position
            if offset in CHECKPOINTS:
                metadata["checkpoint"] = self._checkpoint(proposal, offset)
        elif alarm:
            self._handle_alarm(metadata)

        if not metadata:
            return None
        metadata["budget"] = self._budget.as_metadata()
        return UpdateEvent(drift_alarm=True if alarm else None, metadata=metadata)

    def _handle_alarm(self, metadata: dict[str, JsonValue]) -> None:
        if self._position <= self._cooldown_end:
            metadata["alarm_disposition"] = "cooldown_suppressed"
        elif not self._budget.allows(MIN_RETAINED):
            metadata["alarm_disposition"] = "budget_suppressed"
        else:
            metadata["alarm_disposition"] = "accepted"
            current_mean, std = self._anomaly.mean, self._anomaly.std
            assert current_mean is not None and std is not None
            proposal = Proposal(
                self._position, current_mean, max(std, self._anomaly.config.minimum_std)
            )
            metadata["proposal"] = {
                "alarm_position": proposal.alarm_position,
                "reference_mean": proposal.mean,
                "reference_scale": proposal.scale,
                "budget_at_open": self._budget.as_metadata(),
            }
            if self.mode is Ablation.IMMEDIATE:
                metadata["checkpoint"] = self._decide(
                    proposal, 0, list(self._history), None
                )
            else:
                self._proposal = proposal

    def _checkpoint(self, proposal: Proposal, offset: int) -> dict[str, JsonValue]:
        first = median(
            point.value for point in proposal.points[-2 * BLOCK_SIZE : -BLOCK_SIZE]
        )
        second = median(point.value for point in proposal.points[-BLOCK_SIZE:])
        return self._decide(proposal, offset, proposal.points, (first, second))

    def _decide(
        self,
        proposal: Proposal,
        offset: int,
        points: list[CandidatePoint],
        medians: tuple[float, float] | None,
    ) -> dict[str, JsonValue]:
        retained = [
            point
            for point in points
            if self.mode not in (Ablation.FILTERING, Ablation.FULL)
            or not point.anomalous
        ]
        shifts = None
        persistence = None
        failures = []
        if medians is not None:
            shifts = [(value - proposal.mean) / proposal.scale for value in medians]
            edge = SHIFT_CUTOFF * proposal.scale
            persistence = all(
                value >= proposal.mean + edge for value in medians
            ) or all(value <= proposal.mean - edge for value in medians)
            if not persistence:
                failures.append("persistence_failed")
        if len(retained) < MIN_RETAINED:
            failures.append("insufficient_retained")
        if not failures and not self._budget.allows(len(retained)):
            failures.append("budget_blocked")

        checkpoint: dict[str, JsonValue] = {
            "alarm_position": proposal.alarm_position,
            "offset": offset,
            "block_medians": list(medians) if medians is not None else None,
            "effective_shifts": shifts,
            "persistence_passed": persistence,
            "candidate_count": len(points),
            "retained_count": len(retained),
            "filtered_count": len(points) - len(retained),
            "candidate_positions": [point.position for point in points],
            "retained_positions": [point.position for point in retained],
            "failures": failures,
        }
        if failures:
            close = offset in (0, CHECKPOINTS[-1]) or "budget_blocked" in failures
            if close:
                self._proposal = None
            checkpoint["decision"] = "closed" if close else "wait"
        else:
            checkpoint["decision"] = "refit"
            checkpoint["refit"] = self._refit(retained)
        return checkpoint

    def _refit(self, retained: list[CandidatePoint]) -> dict[str, JsonValue]:
        before = {"mean": self._anomaly.mean, "std": self._anomaly.std}
        self._anomaly.fit_initial(tuple(point.value for point in retained))
        self._budget.record(len(retained))
        self._proposal = None
        cooldown = None
        if self.mode is Ablation.FULL:
            self._cooldown_end = self._position + COOLDOWN
            cooldown = {
                "first_position": self._position + 1,
                "last_position": self._cooldown_end,
            }
        return {
            "position": self._position,
            "before": before,
            "after": {"mean": self._anomaly.mean, "std": self._anomaly.std},
            "cooldown": cooldown,
        }
