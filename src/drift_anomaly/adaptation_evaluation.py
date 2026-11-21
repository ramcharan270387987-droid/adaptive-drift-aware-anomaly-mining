"""Post-replay refit attribution and false-alarm windows."""

from bisect import bisect_right
from collections.abc import Iterable
from dataclasses import dataclass
from statistics import mean, median

from drift_anomaly.drift_evaluation import POST_TRANSITION_WINDOW
from drift_anomaly.evaluation import NominalAlarms
from drift_anomaly.replay import DevelopmentReplay
from drift_anomaly.selective_adaptation import CHECKPOINTS
from drift_anomaly.synthetic import DriftEvent


@dataclass(frozen=True)
class Refit:
    index: int
    alarm_index: int | None
    input_indices: tuple[int, ...]


@dataclass(frozen=True)
class RefitMatch:
    onset: int
    refit: Refit | None

    @property
    def onset_delay(self) -> int | None:
        return None if self.refit is None else self.refit.index - self.onset

    @property
    def alarm_delay(self) -> int | None:
        if self.refit is None or self.refit.alarm_index is None:
            return None
        return self.refit.index - self.refit.alarm_index


def match_refits(
    events: Iterable[DriftEvent], refits: Iterable[Refit], *, warmup_last: int
) -> tuple[list[RefitMatch], list[Refit]]:
    """Assign the earliest eligible refit within each clipped drift window."""
    events = sorted(events, key=lambda event: event.start)
    available = sorted(refits, key=lambda refit: refit.index)
    matches = []
    for i, event in enumerate(events):
        if event.start <= warmup_last:
            continue
        next_onset = events[i + 1].start if i + 1 < len(events) else float("inf")
        alarm_end = min(event.end + POST_TRANSITION_WINDOW, next_onset - 1)
        refit_end = min(
            event.end + POST_TRANSITION_WINDOW + CHECKPOINTS[-1], next_onset - 1
        )
        refit = next(
            (
                item
                for item in available
                if event.start <= item.index <= refit_end
                and (
                    item.alarm_index is None
                    or event.start <= item.alarm_index <= min(alarm_end, item.index)
                )
            ),
            None,
        )
        if refit is not None:
            available.remove(refit)
        matches.append(RefitMatch(event.start, refit))
    return matches, available


def post_refit_windows(
    selected: Iterable[Refit],
    all_refits: list[Refit],
    onsets: list[int],
    stream_end: int,
) -> list[tuple[int, int]]:
    boundaries = sorted({*onsets, *(refit.index for refit in all_refits)})
    windows = []
    for refit in selected:
        next_boundary = bisect_right(boundaries, refit.index)
        end = min(refit.index + 256, stream_end)
        if next_boundary < len(boundaries):
            end = min(end, boundaries[next_boundary] - 1)
        if end > refit.index:
            windows.append((refit.index + 1, end))
    return windows


def window_alarms(run: DevelopmentReplay, windows: list[tuple[int, int]]) -> dict:
    """Count each nominal scored index once across the specified intervals."""
    alarms = NominalAlarms()
    selected = {index for lo, hi in windows for index in range(lo, hi + 1)}
    for record in run.result.scored_records():
        if (
            record.observation.index in selected
            and record.observation.anomaly_label is False
        ):
            assert (
                record.prediction is not None
                and record.prediction.predicted_anomaly is not None
            )
            alarms.add(record.prediction.predicted_anomaly)
    return {
        "window_count": len(windows),
        "observations": len(selected),
        **alarms.summary(),
    }


def delay_summary(delays: list[int]) -> dict:
    return {
        "count": len(delays),
        "mean": mean(delays) if delays else None,
        "median": median(delays) if delays else None,
        "min": min(delays) if delays else None,
        "max": max(delays) if delays else None,
    }
