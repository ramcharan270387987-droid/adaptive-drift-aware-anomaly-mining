"""Run the frozen selective ablations and sensitivity checks on development only."""

import argparse
import os
import platform
import resource
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path

import yaml

from drift_anomaly.adaptation_evaluation import (
    Refit,
    delay_summary,
    match_refits,
    post_refit_windows,
    window_alarms,
)
from drift_anomaly.adwin import ADWINDetector
from drift_anomaly.drift_evaluation import evaluate_drift, summarize_drift
from drift_anomaly.evaluation import AnomalyEvaluation
from drift_anomaly.experiments import (
    adwin_baseline,
    page_hinkley_baseline,
    static_baseline,
)
from drift_anomaly.experiments.selective_smoke import (
    FROZEN_ADWIN,
    FROZEN_ZSCORE,
    stream_diagnostics,
)
from drift_anomaly.fixed_schedule import FixedScheduleConfig, FixedScheduleZScore
from drift_anomaly.frozen_control import FrozenZScoreWithDrift
from drift_anomaly.page_hinkley import PageHinkleyDetector
from drift_anomaly.replay import (
    DevelopmentReplay,
    StreamingDetector,
    replay_synthetic_development,
)
from drift_anomaly.selective_adaptation import (
    BLOCK_SIZE,
    CHECKPOINTS,
    COOLDOWN,
    MAX_FIT_INPUTS,
    MAX_REFITS,
    MIN_RETAINED,
    SENSITIVITY_CUTOFFS,
    SHIFT_CUTOFF,
    WINDOW_SIZE,
    Ablation,
    SelectiveZScore,
)
from drift_anomaly.zscore import StaticZScore


@dataclass(frozen=True)
class Arm:
    name: str
    factory: Callable[[], StreamingDetector]
    cutoff: float | None = None
    selective: bool = False
    drift: bool = False


def _selective_arm(mode: Ablation, cutoff: float = SHIFT_CUTOFF) -> Arm:
    name = mode.value if cutoff == SHIFT_CUTOFF else f"full_{cutoff:.2f}"
    return Arm(
        name,
        lambda: SelectiveZScore(
            StaticZScore(FROZEN_ZSCORE),
            ADWINDetector(FROZEN_ADWIN),
            mode,
            persistence_cutoff=cutoff,
        ),
        cutoff=cutoff if mode is not Ablation.IMMEDIATE else None,
        selective=True,
        drift=True,
    )


def _arms(page_config):
    return [
        _selective_arm(Ablation.FULL),
        *(_selective_arm(mode) for mode in Ablation if mode is not Ablation.FULL),
        *(
            _selective_arm(Ablation.FULL, cutoff)
            for cutoff in SENSITIVITY_CUTOFFS
            if cutoff != SHIFT_CUTOFF
        ),
        Arm("static_zscore", lambda: StaticZScore(FROZEN_ZSCORE)),
        Arm(
            "zscore_adwin_no_adaptation",
            lambda: FrozenZScoreWithDrift(
                StaticZScore(FROZEN_ZSCORE), ADWINDetector(FROZEN_ADWIN)
            ),
            drift=True,
        ),
        Arm(
            "zscore_page_hinkley_no_adaptation",
            lambda: FrozenZScoreWithDrift(
                StaticZScore(FROZEN_ZSCORE), PageHinkleyDetector(page_config)
            ),
            drift=True,
        ),
        Arm(
            "fixed_schedule",
            lambda: FixedScheduleZScore(FixedScheduleConfig(3.0, 1e-12, 256, 256)),
        ),
    ]


def _fixed_refits(run: DevelopmentReplay) -> list[Refit]:
    refits = []
    for position, record in enumerate(run.result.records):
        if record.update is not None:
            size = record.update.metadata["refit"]["window_size"]
            refits.append(
                Refit(
                    record.observation.index,
                    None,
                    tuple(
                        row.observation.index
                        for row in run.result.records[
                            position - size + 1 : position + 1
                        ]
                    ),
                )
            )
    return refits


def _selective_refits(log: dict) -> list[Refit]:
    return [
        Refit(check["index"], proposal["alarm_index"], tuple(check["retained_indices"]))
        for proposal in log["proposals"]
        for check in proposal["checkpoints"]
        if check["decision"] == "refit"
    ]


def _filter_counts(run: DevelopmentReplay, log: dict) -> dict:
    anomalies = {
        record.observation.index
        for record in run.result.records
        if record.observation.anomaly_label
    }
    totals = Counter(
        dict.fromkeys(
            (
                "candidate_considerations",
                "unique_candidate_observations",
                "retained_anomalies",
                "excluded_anomalies",
                "retained_nominal",
                "excluded_nominal",
                "fit_anomaly_uses",
            ),
            0,
        )
    )
    seen = set()
    for proposal in log["proposals"]:
        for check in proposal["checkpoints"]:
            kept, excluded = check["retained_indices"], check["filtered_indices"]
            seen.update(check["candidate_indices"])
            totals["candidate_considerations"] += check["candidate_count"]
            retained_anomalies = sum(index in anomalies for index in kept)
            excluded_anomalies = sum(index in anomalies for index in excluded)
            totals["retained_anomalies"] += retained_anomalies
            totals["excluded_anomalies"] += excluded_anomalies
            totals["retained_nominal"] += len(kept) - retained_anomalies
            totals["excluded_nominal"] += len(excluded) - excluded_anomalies
            if check["decision"] == "refit":
                totals["fit_anomaly_uses"] += retained_anomalies
    totals["unique_candidate_observations"] = len(seen)
    return dict(totals)


def _stream_details(arm, run, stream_id, full_windows):
    log = stream_diagnostics(run) if arm.selective else None
    refits = (
        _selective_refits(log)
        if log is not None
        else _fixed_refits(run)
        if arm.name == "fixed_schedule"
        else []
    )
    warmup_last = run.result.stats.warmup_last_index
    assert warmup_last is not None
    matches, unmatched = match_refits(run.drift_events, refits, warmup_last=warmup_last)
    onsets = [event.start for event in run.drift_events]
    end = run.result.records[-1].observation.index
    matched = [match.refit for match in matches if match.refit is not None]
    matched_windows = post_refit_windows(matched, refits, onsets, end)
    unmatched_windows = post_refit_windows(unmatched, refits, onsets, end)
    if arm.name == "full":
        full_windows[stream_id] = matched_windows

    counts = (
        Counter(alarm["disposition"] for alarm in log["alarms"])
        if log is not None
        else Counter()
    )
    proposals = (
        Counter(proposal["status"] for proposal in log["proposals"])
        if log is not None
        else Counter()
    )
    input_sizes = [len(refit.input_indices) for refit in refits]
    if log is not None and (
        len(refits) != log["refit_count"]
        or sum(input_sizes) != log["refit_input_uses"]
        or len(refits) != proposals["refit"]
        or counts["accepted"] != sum(proposals.values())
    ):
        raise ValueError(f"selective diagnostic mismatch for {stream_id}")
    if len(refits) > MAX_REFITS or sum(input_sizes) > MAX_FIT_INPUTS:
        raise ValueError(f"refit budget exceeded for {stream_id}")

    return {
        "refits": len(refits),
        "refit_input_uses": sum(input_sizes),
        "refit_input_sizes": input_sizes,
        "unique_refit_inputs": len(
            {index for refit in refits for index in refit.input_indices}
        ),
        "terminal_refits": sum(refit.index == end for refit in refits),
        "eligible_events": len(matches),
        "excluded_warmup_events": len(run.drift_events) - len(matches),
        "matched_refits": len(matched),
        "missed_events": len(matches) - len(matched),
        "unnecessary_refits": len(unmatched),
        "unmatched_refit_indices": [refit.index for refit in unmatched],
        "refit_matches": [
            {
                "onset": match.onset,
                "index": match.refit.index if match.refit else None,
                "alarm_index": match.refit.alarm_index if match.refit else None,
                "onset_delay": match.onset_delay,
                "alarm_delay": match.alarm_delay,
            }
            for match in matches
        ],
        "proposals": sum(proposals.values()),
        "rejected_proposals": proposals["closed"],
        "incomplete_proposals": proposals["incomplete"],
        "cooldown_suppressed": counts["cooldown_suppressed"],
        "budget_suppressed": counts["budget_suppressed"],
        "duplicate_alarms": counts["duplicate"],
        "post_matched_refit": window_alarms(run, matched_windows),
        "post_unmatched_refit": window_alarms(run, unmatched_windows),
        "on_full_matched_windows": window_alarms(run, full_windows[stream_id]),
        "filter": _filter_counts(run, log) if log is not None else None,
        "diagnostics": log,
    }


COUNT_FIELDS = (
    "refits",
    "refit_input_uses",
    "unique_refit_inputs",
    "terminal_refits",
    "eligible_events",
    "excluded_warmup_events",
    "matched_refits",
    "missed_events",
    "unnecessary_refits",
    "proposals",
    "rejected_proposals",
    "incomplete_proposals",
    "cooldown_suppressed",
    "budget_suppressed",
    "duplicate_alarms",
)
WINDOW_FIELDS = (
    "post_matched_refit",
    "post_unmatched_refit",
    "on_full_matched_windows",
)


def summarize_updates(rows: list[dict]) -> dict:
    n = len(rows)
    totals = {key: sum(row[key] for row in rows) for key in COUNT_FIELDS}
    updated = sum(row["refits"] > 0 for row in rows)
    unnecessary = sum(row["unnecessary_refits"] > 0 for row in rows)
    windows = {}
    for name in WINDOW_FIELDS:
        counts = {
            key: sum(row[name][key] for row in rows)
            for key in ("fp", "tn", "nominal_count", "window_count", "observations")
        }
        nominal = counts["nominal_count"]
        windows[name] = {
            **counts,
            "false_positive_rate": counts["fp"] / nominal if nominal else None,
            "streams_with_window": sum(row[name]["window_count"] > 0 for row in rows),
        }
    filter_totals = Counter()
    for row in rows:
        filter_totals.update(row["filter"] or {})
    return {
        **totals,
        **windows,
        "refit_coverage": totals["matched_refits"] / totals["eligible_events"]
        if totals["eligible_events"]
        else None,
        "streams_with_refit": updated,
        "share_streams_with_refit": updated / n,
        "refits_per_stream": totals["refits"] / n,
        "mean_refit_input_size": totals["refit_input_uses"] / totals["refits"]
        if totals["refits"]
        else None,
        "streams_with_unnecessary_refit": unnecessary,
        "share_streams_with_unnecessary_refit": unnecessary / n,
        "share_updated_streams_with_unnecessary_refit": unnecessary / updated
        if updated
        else None,
        "onset_delay": delay_summary(
            [
                m["onset_delay"]
                for row in rows
                for m in row["refit_matches"]
                if m["onset_delay"] is not None
            ]
        ),
        "alarm_delay": delay_summary(
            [
                m["alarm_delay"]
                for row in rows
                for m in row["refit_matches"]
                if m["alarm_delay"] is not None
            ]
        ),
        "filter": dict(filter_totals) if filter_totals else None,
    }


def _run_arm(
    arm,
    experiment,
    staged,
    full_windows,
    *,
    replay_stream=replay_synthetic_development,
    inspect_run=None,
):
    groups = {}
    drift_runs = []
    rows = []
    timings = []
    provenance = None
    for path, _, scenario in static_baseline.scenarios(experiment):
        for variant, config in static_baseline.paired_variants(scenario):
            run = replay_stream(config, arm.factory, config_path=path)
            provenance = run.provenance
            stream_id = static_baseline.stream_id_for(config, variant)
            metric = AnomalyEvaluation()
            metric.add(run.result.scored_records(), run.drift_events)
            key = (config.drift_type, variant)
            if key not in groups:
                groups[key] = AnomalyEvaluation(), 0
            group, count = groups[key]
            group.merge(metric)
            groups[key] = group, count + 1
            detail = _stream_details(arm, run, stream_id, full_windows)
            drift = evaluate_drift(run) if arm.drift else None
            if inspect_run is not None:
                inspect_run(arm.name, stream_id, run, detail, drift)
            if drift is not None:
                drift_runs.append(drift)
                if arm.selective and len(drift.alarm_indices) != (
                    detail["proposals"]
                    + detail["duplicate_alarms"]
                    + detail["cooldown_suppressed"]
                    + detail["budget_suppressed"]
                ):
                    raise ValueError(f"alarm accounting mismatch for {stream_id}")
            rows.append(
                {
                    **static_baseline.anomaly_stream_record(
                        run, metric, stream_id, variant
                    ),
                    "arm": arm.name,
                    "persistence_cutoff": arm.cutoff,
                    "alarm_indices": drift.alarm_indices if drift is not None else [],
                    "adaptation": detail,
                }
            )
            timings.append(
                {
                    "stream_id": stream_id,
                    "elapsed_seconds": run.result.stats.elapsed_seconds,
                }
            )
    assert provenance is not None
    anomaly = static_baseline.summarize_anomaly_groups(groups)
    by_variant = {}
    for (_, variant), (evaluation, count) in groups.items():
        if variant not in by_variant:
            by_variant[variant] = AnomalyEvaluation(), 0
        combined, stream_count = by_variant[variant]
        combined.merge(evaluation)
        by_variant[variant] = combined, stream_count + count
    updates = summarize_updates([row["adaptation"] for row in rows])
    if anomaly["pooled"]["scored_count"] != sum(row["scored_count"] for row in rows):
        raise ValueError("scored counts do not reconcile")
    if any(
        anomaly["pooled"][name] != sum(row[name] for row in rows)
        for name in ("tp", "fp", "tn", "fn")
    ):
        raise ValueError("confusion counts do not reconcile")
    elapsed = sum(row["elapsed_seconds"] for row in timings)
    scored = anomaly["pooled"]["scored_count"]
    static_baseline.write_json(staged / f"{arm.name}_streams.json", rows)
    return (
        {
            "persistence_cutoff": arm.cutoff,
            "anomaly": anomaly,
            "anomaly_by_injection": {
                variant: {"stream_count": count, **evaluation.summary()}
                for variant, (evaluation, count) in by_variant.items()
            },
            "adaptation": updates,
            "drift": summarize_drift(drift_runs) if arm.drift else None,
        },
        {
            "elapsed_seconds": elapsed,
            "scored_count": scored,
            "scored_observations_per_second": scored / elapsed,
            "per_stream": timings,
        },
        provenance,
    )


def run_experiment(config: Path, output: Path) -> None:
    experiment = adwin_baseline.load_experiment(config)
    if (
        experiment.detector != FROZEN_ADWIN
        or experiment.grid != static_baseline.DEVELOPMENT_GRID
        or {template.drift_type for _, template in experiment.streams}
        != {"none", "sudden", "gradual", "incremental", "recurring"}
    ):
        raise ValueError(
            "evaluation requires the complete frozen development grid and ADWIN configuration"
        )
    page_path = config.with_name("page_hinkley_dev.yaml")
    page = page_hinkley_baseline.load_experiment(page_path)
    if page.grid != experiment.grid or page.streams != experiment.streams:
        raise ValueError("control grids must match")
    full_windows = {}
    metrics = {}
    timings = {}
    with static_baseline.staged_output(output) as staged:
        for arm in _arms(page.detector):
            metrics[arm.name], timings[arm.name], provenance = _run_arm(
                arm, experiment, staged, full_windows
            )
            print(
                f"Completed {arm.name} on {metrics[arm.name]['anomaly']['stream_count']} development streams.",
                flush=True,
            )
        if len(full_windows) != 500 or any(
            row["anomaly"]["stream_count"] != 500 for row in metrics.values()
        ):
            raise ValueError("development stream count mismatch")
        static_baseline.write_json(staged / "comparison.json", metrics)
        static_baseline.write_json(
            staged / "runtime.json",
            {
                "arms": timings,
                "peak_process_rss_kib": resource.getrusage(
                    resource.RUSAGE_SELF
                ).ru_maxrss,
                "timer": "replay after generation, including warm-up and updates, before post-hoc evaluation",
            },
        )
        static_baseline.write_json(
            staged / "manifest.json",
            {
                "git_commit": provenance.git_commit,
                "project_version": provenance.project_version,
                "executed_at_utc": provenance.executed_at_utc,
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "logical_cpus": os.cpu_count(),
                "thread_settings": {
                    key: os.environ.get(key)
                    for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS")
                },
                "dependencies": {
                    name: version(name)
                    for name in ("river", "numpy", "scikit-learn", "PyYAML")
                },
                "split": "development",
                "config": str(config),
                "page_hinkley_config": str(page_path),
                "grid": experiment.grid,
                "templates": [str(path) for path, _ in experiment.streams],
                "warmup": provenance.warmup_length,
                "adwin": asdict(FROZEN_ADWIN),
                "page_hinkley": asdict(page.detector),
                "zscore": asdict(FROZEN_ZSCORE),
                "primary_cutoff": SHIFT_CUTOFF,
                "sensitivity_cutoffs": SENSITIVITY_CUTOFFS,
                "checkpoints": CHECKPOINTS,
                "block_size": BLOCK_SIZE,
                "window_size": WINDOW_SIZE,
                "minimum_retained": MIN_RETAINED,
                "cooldown": COOLDOWN,
                "max_refits": MAX_REFITS,
                "max_refit_input_uses": MAX_FIT_INPUTS,
                "fixed_schedule": asdict(FixedScheduleConfig(3.0, 1e-12, 256, 256)),
            },
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/experiments/adwin_dev.yaml")
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="new directory under results/"
    )
    args = parser.parse_args()
    try:
        run_experiment(args.config, args.output)
    except (OSError, ValueError, yaml.YAMLError) as error:
        parser.exit(1, f"Selective evaluation: {error}\n")


if __name__ == "__main__":
    main()
