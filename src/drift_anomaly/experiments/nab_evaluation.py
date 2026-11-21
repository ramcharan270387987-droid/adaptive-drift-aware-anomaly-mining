"""NAB point metrics and supplementary window diagnostics without drift truth."""

from bisect import bisect_left, bisect_right

from drift_anomaly.evaluation import AnomalyEvaluation
from drift_anomaly.experiments.selective_smoke import selective_diagnostics
from drift_anomaly.experiments.validation_cases import count_nominal
from drift_anomaly.experiments.validation_stats import describe
from drift_anomaly.nab_replay import replay_nab


def _windows(stream, result):
    details = []
    for left, right in stream.windows:
        lo = bisect_left(stream.timestamps, left)
        hi = bisect_right(stream.timestamps, right)
        start = max(lo, result.stats.warmup_count)
        hits = [
            row.observation.index
            for row in result.records[start:hi]
            if row.prediction.predicted_anomaly
        ]
        details.append(
            {
                "start": left.isoformat(sep=" "),
                "end": right.isoformat(sep=" "),
                "start_index": lo,
                "end_index_exclusive": hi,
                "scored_observations": max(0, hi - start),
                "hit": bool(hits) if hi > start else None,
                "first_hit": hits[0] if hits else None,
                "point_false_positives": count_nominal(result, start, hi)["fp"],
            }
        )
    return details


def _events(arm, stream, result, windows):
    def timestamp(index):
        return stream.timestamps[index].isoformat(sep=" ")

    def timing(index):
        distances = [
            max(w["start_index"] - index, index - w["end_index_exclusive"] + 1, 0)
            for w in windows
            if w["end_index_exclusive"] > w["start_index"]
        ]
        return {
            "timestamp": timestamp(index),
            "nearest_anomaly_window_distance_rows": min(distances, default=None),
        }

    if arm.selective:
        log = selective_diagnostics(result)
        for entry in log["alarms"]:
            entry.update(timing(entry["index"]))
        refits = []
        for proposal in log["proposals"]:
            proposal.update(timing(proposal["alarm_index"]))
            for check in proposal["checkpoints"]:
                check["timestamp"] = timestamp(check["index"])
                if "refit" in check:
                    refits.append(
                        {
                            **check["refit"],
                            "window_size": len(check["candidate_indices"]),
                            "retained_count": len(check["retained_indices"]),
                            "filtered_count": len(check["filtered_indices"]),
                        }
                    )
    elif arm.name == "fixed_schedule":
        log = None
        refits = [
            {
                "index": row.observation.index,
                **row.update.metadata["refit"],
                "retained_count": row.update.metadata["refit"]["window_size"],
                "filtered_count": 0,
            }
            for row in result.scored_records()
            if row.update is not None
        ]
    else:
        return None

    for n, refit in enumerate(refits):
        index = refit["index"]
        next_refit = (
            refits[n + 1]["index"] if n + 1 < len(refits) else len(result.records)
        )
        previous = refits[n - 1]["index"] + 1 if n else 0
        refit.update(timing(index))
        refit["preceding_256_nominal"] = count_nominal(
            result, max(previous, index - 255), index + 1
        )
        refit["following_256_nominal"] = count_nominal(
            result, index + 1, min(index + 257, next_refit)
        )
    return {
        "refits": refits,
        "refit_input_uses": sum(r["retained_count"] for r in refits),
        "adwin": log,
    }


def run_nab(series, arms, case_selector):
    by_arm = {arm.name: [] for arm in arms}
    accumulators = {arm.name: AnomalyEvaluation() for arm in arms}
    for stream in series:
        baseline_windows = None
        for arm in arms:
            result = replay_nab(stream, arm.factory)
            metric = AnomalyEvaluation()
            metric.add(result.scored_records())
            accumulators[arm.name].merge(metric)
            windows = _windows(stream, result)
            events = _events(arm, stream, result, windows)
            hits = sum(w["hit"] is True for w in windows)
            eligible = sum(w["hit"] is not None for w in windows)
            summary = metric.summary()
            for field in ("false_positives_by_phase", "drift_window"):
                del summary[field]
            if (
                summary["scored_count"]
                != len(stream.observations) - result.stats.warmup_count
            ):
                raise ValueError("NAB score counts do not reconcile")
            by_arm[arm.name].append(
                {
                    "series": stream.series,
                    "source": str(stream.source),
                    "sha256": stream.checksum,
                    "source_revision": stream.revision,
                    "duplicate_timestamps": stream.duplicate_timestamps,
                    "dropped_backwards": stream.dropped_backwards,
                    "unobserved_labeled_points": stream.unobserved_points,
                    "warmup_labeled_points": result.stats.warmup_anomaly_count,
                    "warmup": result.stats.warmup_count,
                    "drift_truth_available": False,
                    **summary,
                    "windows": windows,
                    "eligible_windows": eligible,
                    "window_hits": hits,
                    "window_hit_rate": hits / eligible if eligible else None,
                    "elapsed_seconds": result.stats.elapsed_seconds,
                    "adaptation": events,
                }
            )
            if arm.name == "static_zscore":
                baseline_windows = windows
            elif events and baseline_windows is not None:
                for baseline, window in zip(baseline_windows, windows, strict=True):
                    lost = baseline["hit"] is True and window["hit"] is False
                    excess_fp = (
                        window["point_false_positives"]
                        - baseline["point_false_positives"]
                    )
                    if lost or excess_fp > 0:
                        case_selector.consider(
                            "nab_window_worsened",
                            10000 * lost + excess_fp,
                            arm.name,
                            stream.series,
                            window["start_index"],
                            result,
                            alarms=[a["index"] for a in events["adwin"]["alarms"]]
                            if events["adwin"]
                            else (),
                            refits=[r["index"] for r in events["refits"]],
                            windows=[
                                (w["start_index"], w["end_index_exclusive"] - 1)
                                for w in windows
                            ],
                        )
    pooled = {}
    for arm, rows in by_arm.items():
        summary = accumulators[arm].summary()
        for field in ("false_positives_by_phase", "drift_window"):
            del summary[field]
        eligible = sum(r["eligible_windows"] for r in rows)
        hits = sum(r["window_hits"] for r in rows)
        updates = [r["adaptation"] for r in rows if r["adaptation"] is not None]
        elapsed = sum(r["elapsed_seconds"] for r in rows)
        costs = [u for u in updates if u["refits"]]
        pooled[arm] = {
            **summary,
            "eligible_windows": eligible,
            "window_hits": hits,
            "window_hit_rate": hits / eligible if eligible else None,
            "elapsed_seconds": elapsed,
            "throughput": summary["scored_count"] / elapsed,
            "refits": sum(len(u["refits"]) for u in costs),
            "refit_input_uses": sum(u["refit_input_uses"] for u in costs),
            "streams_updated": len(costs),
            "across_series": {
                key: describe([r[key] for r in rows if r[key] is not None])
                for key in (
                    "precision",
                    "recall",
                    "f1",
                    "false_positive_rate",
                    "pr_auc",
                    "window_hit_rate",
                )
            },
        }
    return {"pooled": pooled, "by_arm": by_arm, "drift_truth_available": False}
