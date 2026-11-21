"""Run drift-only baselines on the same paired development grid."""

import platform
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

from drift_anomaly.drift_evaluation import (
    DriftEvaluation,
    evaluate_drift,
    summarize_drift,
)
from drift_anomaly.experiments import static_baseline
from drift_anomaly.experiments.drift_comparison import (
    MATCHING_POLICY,
    ADWINReference,
    ComparedStream,
)
from drift_anomaly.replay import (
    DEFAULT_WARMUP,
    DevelopmentReplay,
    StreamingDetector,
    replay_synthetic_development,
)


def _pair_record(
    pair_id: str, drift_type: str, clean: DriftEvaluation, injected: DriftEvaluation
) -> dict:
    clean_false = set(clean.false_alarm_indices)
    injected_false = set(injected.false_alarm_indices)
    return {
        "pair_id": pair_id,
        "drift_type": drift_type,
        "clean_false_alarms": len(clean_false),
        "injected_false_alarms": len(injected_false),
        "injected_minus_clean": len(injected_false) - len(clean_false),
        "injected_only_false_alarm_indices": sorted(injected_false - clean_false),
        "clean_only_false_alarm_indices": sorted(clean_false - injected_false),
    }


def _paired_summary(pairs: list[dict]) -> dict:
    differences = [pair["injected_minus_clean"] for pair in pairs]
    return {
        "pair_count": len(pairs),
        "pairs_with_more_false_alarms": sum(diff > 0 for diff in differences),
        "pairs_with_fewer_false_alarms": sum(diff < 0 for diff in differences),
        "pairs_with_equal_false_alarms": differences.count(0),
        "net_additional_false_alarms": sum(differences),
    }


def _plot_pair(
    runs: list[tuple[str, DevelopmentReplay, DriftEvaluation]],
    path: Path,
    detector_label: str,
    reference_alarms: dict[str, tuple[int, ...]],
) -> None:
    from matplotlib import pyplot as plt

    fig, axes = plt.subplots(
        2, 1, sharex=True, sharey=True, figsize=(10, 5), layout="constrained"
    )
    for ax, (variant, run, evaluation) in zip(axes, runs, strict=True):
        values = {r.observation.index: r.observation.value for r in run.result.records}
        indices = [
            r.observation.index
            for r in run.result.records
            if r.observation.anomaly_label
        ]
        ax.plot(
            list(values),
            list(values.values()),
            color="#334155",
            linewidth=0.6,
            label="Value",
        )
        if indices:
            ax.scatter(
                indices,
                [values[i] for i in indices],
                color="#b91c1c",
                s=15,
                label="Injected anomaly",
            )
        for i, event in enumerate(run.drift_events):
            if event.start != event.end:
                ax.axvspan(event.start, event.end, color="#fde68a", alpha=0.5)
            ax.axvline(
                event.start,
                color="#a16207",
                linewidth=1,
                label="True drift" if i == 0 else None,
            )
            if event.start != event.end:
                ax.axvline(event.end, color="#a16207", linewidth=0.7)
        for label, alarms, color, linestyle in (
            ("ADWIN", reference_alarms.get(variant, ()), "#7e22ce", ":"),
            (detector_label, evaluation.alarm_indices, "#1d4ed8", "--"),
        ):
            for i, alarm in enumerate(alarms):
                ax.axvline(
                    alarm,
                    color=color,
                    linewidth=1,
                    linestyle=linestyle,
                    label=f"{label} alarm" if i == 0 else None,
                )
        ax.axvspan(0, DEFAULT_WARMUP - 1, color="#64748b", alpha=0.13, label="Warm-up")
        ax.set(title=variant.capitalize(), ylabel="Value")
        ax.legend(loc="upper right", ncols=3, fontsize="small")
    axes[-1].set_xlabel("Observation index")
    provenance = runs[0][1].provenance
    fig.suptitle(
        f"Development {'ADWIN vs ' if reference_alarms else ''}{detector_label}"
        f" | {provenance.drift_type}, seed {provenance.stream_seed}"
    )
    fig.savefig(path, dpi=140)
    plt.close(fig)


def run_baseline[Config](
    config_path: Path,
    output: Path,
    *,
    parse_detector: Callable[[object], Config],
    build_detector: Callable[[Config], StreamingDetector],
    detector_label: str,
    plots: bool = False,
    adwin_results: Path | None = None,
) -> dict:
    experiment = static_baseline.load_experiment(config_path, parse_detector)
    reference = (
        ADWINReference.load(adwin_results, experiment)
        if adwin_results is not None
        else None
    )
    with static_baseline.staged_output(output) as staged:
        return _evaluate(
            experiment,
            config_path,
            staged,
            build_detector,
            detector_label,
            plots=plots,
            reference=reference,
        )


def _evaluate(
    experiment,
    config_path: Path,
    output: Path,
    build_detector,
    detector_label: str,
    *,
    plots: bool,
    reference: ADWINReference | None,
) -> dict:
    plot_dir = static_baseline.prepare_plots(output) if plots else None
    per_stream = []
    comparisons: list[ComparedStream] = []
    pair_records = []
    groups = defaultdict(list)
    first = None
    for path, template, scenario in static_baseline.scenarios(experiment):
        pair_id = static_baseline.stream_id_for(scenario, "pair")
        pair = []
        reference_alarms = {}
        for variant, config in static_baseline.paired_variants(scenario):
            run = replay_synthetic_development(
                config, lambda: build_detector(experiment.detector), config_path=path
            )
            if first is None:
                first = run.provenance
            evaluation = evaluate_drift(run)
            groups[config.drift_type, variant].append(evaluation)
            pair.append((variant, run, evaluation))
            row = {
                "stream_id": static_baseline.stream_id_for(config, variant),
                "pair_id": pair_id,
                "variant": variant,
                "drift_type": config.drift_type,
                "seed": config.seed,
                "stream_config_path": str(path),
                "stream_parameters": run.provenance.stream_parameters,
                "first_scored_index": run.result.stats.first_scored_index,
                "alarm_indices": evaluation.alarm_indices,
                "event_matches": [
                    {**asdict(match), "delay": match.delay}
                    for match in evaluation.matches
                ],
                "false_alarm_indices": evaluation.false_alarm_indices,
                "excluded_warmup_drift_events": [
                    asdict(event) for event in evaluation.excluded_events
                ],
                **summarize_drift([evaluation]),
            }
            per_stream.append(row)
            if reference is not None:
                adwin = reference.match_stream(row, run)
                reference_alarms[variant] = adwin.alarm_indices
                comparisons.append(
                    ComparedStream(
                        row["stream_id"], config.drift_type, variant, adwin, evaluation
                    )
                )
        pair_records.append(
            _pair_record(pair_id, scenario.drift_type, pair[0][2], pair[1][2])
        )
        if plot_dir is not None and scenario == template:
            _plot_pair(
                pair,
                plot_dir / f"{scenario.drift_type}.png",
                detector_label,
                reference_alarms,
            )

    assert first is not None
    by_drift = {}
    by_variant = defaultdict(list)
    for (drift_type, variant), evaluations in groups.items():
        by_drift.setdefault(drift_type, {})[variant] = summarize_drift(evaluations)
        by_variant[variant].extend(evaluations)
    aggregate = {
        "pooled": summarize_drift(
            evaluation for group in groups.values() for evaluation in group
        ),
        "by_variant": {
            variant: summarize_drift(evaluations)
            for variant, evaluations in by_variant.items()
        },
        "by_drift": by_drift,
        "paired_false_alarms": {
            "pooled": _paired_summary(pair_records),
            "by_drift": {
                drift: _paired_summary(
                    [pair for pair in pair_records if pair["drift_type"] == drift]
                )
                for drift in by_drift
            },
        },
    }
    manifest = {
        "schema_version": 1,
        "split": first.split,
        "experiment_config": str(config_path),
        "git_commit": first.git_commit,
        "project_version": first.project_version,
        "executed_at_utc": first.executed_at_utc,
        "python_version": platform.python_version(),
        "dependencies": {
            name: version(name) for name in ("river", "numpy", "PyYAML", "matplotlib")
        },
        "detector": {"type": first.detector_id, **asdict(experiment.detector)},
        "warmup": DEFAULT_WARMUP,
        "first_eligible_index": DEFAULT_WARMUP,
        "matching": MATCHING_POLICY,
        "stream_templates": [str(path) for path, _ in experiment.streams],
        "grid": experiment.grid,
        "variants": ["clean", "injected"],
        "stream_count": len(per_stream),
        "plots": plots,
    }
    for name, payload in (
        ("manifest", manifest),
        ("per_stream_metrics", per_stream),
        ("paired_false_alarms", pair_records),
        ("aggregate", aggregate),
    ):
        static_baseline.write_json(output / f"{name}.json", payload)
    if reference is not None:
        static_baseline.write_json(
            output / "comparison.json",
            reference.compare(comparisons, candidate_commit=first.git_commit),
        )
    return aggregate
