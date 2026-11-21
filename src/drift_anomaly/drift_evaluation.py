"""Match causal drift alarms against the synthetic protocol's known transitions."""

from bisect import bisect_left
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import pairwise
from statistics import mean, median

from drift_anomaly.replay import DevelopmentReplay
from drift_anomaly.synthetic import DriftEvent

POST_TRANSITION_WINDOW = 128


@dataclass(frozen=True)
class DriftMatch:
    event: DriftEvent
    window_end: int
    alarm_index: int | None

    @property
    def delay(self) -> int | None:
        return None if self.alarm_index is None else self.alarm_index - self.event.start


@dataclass(frozen=True)
class DriftEvaluation:
    scored_count: int
    alarm_indices: tuple[int, ...]
    matches: tuple[DriftMatch, ...]
    false_alarm_indices: tuple[int, ...]
    excluded_events: tuple[DriftEvent, ...]


def evaluate_drift(run: DevelopmentReplay) -> DriftEvaluation:
    alarms = tuple(
        record.observation.index
        for record in run.result.scored_records()
        if record.update is not None and record.update.drift_alarm is True
    )
    return match_alarms(
        run.drift_events,
        alarms,
        scored_count=run.result.stats.scored_count,
        warmup_last_index=run.result.stats.warmup_last_index,
    )


def match_alarms(
    events: tuple[DriftEvent, ...],
    alarms: tuple[int, ...],
    *,
    scored_count: int,
    warmup_last_index: int | None = None,
) -> DriftEvaluation:
    """Use the first alarm in each inclusive window, clipped at the next onset."""
    if any(left.start >= right.start for left, right in pairwise(events)):
        raise ValueError("drift events must have strictly increasing onset indices")
    if any(left >= right for left, right in pairwise(alarms)):
        raise ValueError("alarm indices must be strictly increasing")
    if warmup_last_index is not None and alarms and alarms[0] <= warmup_last_index:
        raise ValueError("drift matching requires post-warm-up alarms")

    matches = []
    used = set()
    excluded = []
    for i, event in enumerate(events):
        if warmup_last_index is not None and event.start <= warmup_last_index:
            excluded.append(event)
            continue
        end = event.end + POST_TRANSITION_WINDOW
        if i + 1 < len(events):
            end = min(end, events[i + 1].start - 1)
        position = bisect_left(alarms, event.start)
        alarm = (
            alarms[position]
            if position < len(alarms) and alarms[position] <= end
            else None
        )
        matches.append(DriftMatch(event, end, alarm))
        if alarm is not None:
            used.add(alarm)
    return DriftEvaluation(
        scored_count,
        alarms,
        tuple(matches),
        tuple(alarm for alarm in alarms if alarm not in used),
        tuple(excluded),
    )


def summarize_drift(evaluations: Iterable[DriftEvaluation]) -> dict:
    streams = scored = events = excluded = false_alarms = 0
    delays = []
    for evaluation in evaluations:
        streams += 1
        scored += evaluation.scored_count
        events += len(evaluation.matches)
        excluded += len(evaluation.excluded_events)
        false_alarms += len(evaluation.false_alarm_indices)
        delays.extend(
            delay for match in evaluation.matches if (delay := match.delay) is not None
        )

    unavailable = {}
    if not events:
        unavailable["detection_rate"] = "no eligible true drift events"
    if not delays:
        unavailable["detection_delay"] = "no matched drift events"
    if not scored:
        unavailable["false_alarms_per_1000_observations"] = "no scored observations"
    if not streams:
        unavailable["false_alarms_per_stream"] = "no streams"
    return {
        "stream_count": streams,
        "scored_count": scored,
        "true_drift_events": events,
        "excluded_warmup_events": excluded,
        "detected_events": len(delays),
        "missed_events": events - len(delays),
        "alarm_count": len(delays) + false_alarms,
        "false_alarms": false_alarms,
        "detection_rate": len(delays) / events if events else None,
        "mean_delay": mean(delays) if delays else None,
        "median_delay": median(delays) if delays else None,
        "delay_histogram": dict(sorted(Counter(delays).items())),
        "false_alarms_per_stream": false_alarms / streams if streams else None,
        "false_alarms_per_1000_observations": 1000 * false_alarms / scored
        if scored
        else None,
        "unavailable": unavailable,
    }
