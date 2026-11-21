"""Compare drift runs only after verifying aligned streams and matching rules."""

import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from drift_anomaly.drift_evaluation import (
    POST_TRANSITION_WINDOW,
    DriftEvaluation,
    match_alarms,
    summarize_drift,
)
from drift_anomaly.experiments.static_baseline import Experiment
from drift_anomaly.replay import DEFAULT_WARMUP, DevelopmentReplay

MATCHING_POLICY = {
    "post_transition_window": POST_TRANSITION_WINDOW,
    "clip_before_next_onset": True,
    "policy": "first_alarm_one_to_one",
    "delay_origin": "transition_onset",
    "exclude_warmup_onsets": True,
}


@dataclass(frozen=True)
class ComparedStream:
    stream_id: str
    drift_type: str
    variant: str
    adwin: DriftEvaluation
    page_hinkley: DriftEvaluation


@dataclass(frozen=True)
class ADWINReference:
    commit: str
    streams: dict[str, dict]

    @classmethod
    def load(cls, root: Path, experiment: Experiment) -> "ADWINReference":
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        expected = {
            "schema_version": 1,
            "split": "development",
            "warmup": DEFAULT_WARMUP,
            "first_eligible_index": DEFAULT_WARMUP,
            "matching": MATCHING_POLICY,
            "grid": {key: list(values) for key, values in experiment.grid.items()},
            "variants": ["clean", "injected"],
        }
        detector = manifest.get("detector") if isinstance(manifest, dict) else None
        if (
            not isinstance(detector, dict)
            or any(manifest.get(key) != value for key, value in expected.items())
            or detector.get("type") != "adwin"
            or detector.get("signal") != "raw_value"
            or not manifest.get("git_commit")
        ):
            raise ValueError(
                "ADWIN reference must use the same development grid, signal, warm-up, and matching policy"
            )
        rows = json.loads(
            (root / "per_stream_metrics.json").read_text(encoding="utf-8")
        )
        if not isinstance(rows, list) or not all(
            isinstance(row, dict) and isinstance(row.get("stream_id"), str)
            for row in rows
        ):
            raise ValueError("ADWIN reference requires per-stream metrics")
        streams = {row["stream_id"]: row for row in rows}
        if len(rows) != len(streams) or len(rows) != manifest.get("stream_count"):
            raise ValueError("ADWIN reference has duplicate or missing streams")
        return cls(manifest["git_commit"], streams)

    def match_stream(self, row: dict, run: DevelopmentReplay) -> DriftEvaluation:
        stream_id = row["stream_id"]
        reference = self.streams.get(stream_id)
        keys = (
            "pair_id",
            "variant",
            "drift_type",
            "seed",
            "stream_parameters",
            "scored_count",
            "first_scored_index",
            "excluded_warmup_drift_events",
        )
        if reference is None or any(row[key] != reference.get(key) for key in keys):
            raise ValueError(
                f"ADWIN reference has different inputs or drift truth for {stream_id}"
            )
        stats = run.result.stats
        alarms = reference.get("alarm_indices")
        if not isinstance(alarms, list) or any(
            type(alarm) is not int
            or not stats.first_scored_index
            <= alarm
            <= run.result.records[-1].observation.index
            for alarm in alarms
        ):
            raise ValueError(
                f"ADWIN reference has invalid alarm indices for {stream_id}"
            )
        evaluation = match_alarms(
            run.drift_events,
            tuple(alarms),
            scored_count=stats.scored_count,
            warmup_last_index=stats.warmup_last_index,
        )
        expected_matches = [
            {**asdict(match), "delay": match.delay} for match in evaluation.matches
        ]
        if reference.get("event_matches") != expected_matches or reference.get(
            "false_alarm_indices"
        ) != list(evaluation.false_alarm_indices):
            raise ValueError(
                f"ADWIN reference has different drift truth or inconsistent alarms for {stream_id}"
            )
        return evaluation

    def compare(
        self, rows: list[ComparedStream], *, candidate_commit: str | None
    ) -> dict:
        if (
            len(rows) != len(self.streams)
            or {row.stream_id for row in rows} != self.streams.keys()
        ):
            raise ValueError("ADWIN reference must contain exactly the same streams")
        by_drift = defaultdict(list)
        for row in rows:
            by_drift[row.drift_type].append(row)
        return {
            "adwin_git_commit": self.commit,
            "page_hinkley_git_commit": candidate_commit,
            "by_drift": {
                drift: _compare_group(group) for drift, group in by_drift.items()
            },
            "by_variant": {
                variant: _compare_group([row for row in rows if row.variant == variant])
                for variant in ("clean", "injected")
            },
            "pooled": _compare_group(rows),
        }


def _compare_group(rows: list[ComparedStream]) -> dict:
    adwin = summarize_drift(row.adwin for row in rows)
    candidate = summarize_drift(row.page_hinkley for row in rows)
    return {
        "stream_count": len(rows),
        "true_drift_events": candidate["true_drift_events"],
        "adwin": adwin,
        "page_hinkley": candidate,
    }
