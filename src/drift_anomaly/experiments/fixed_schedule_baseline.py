"""Evaluate fixed-schedule Z-score adaptation on paired development streams."""

import argparse
import json
from pathlib import Path

import yaml

from drift_anomaly.experiments import static_baseline
from drift_anomaly.fixed_schedule import FixedScheduleConfig, FixedScheduleZScore
from drift_anomaly.replay import DEFAULT_WARMUP, DevelopmentReplay


def _parse_detector(data: object) -> FixedScheduleConfig:
    fields = {"type", "threshold", "minimum_std", "adaptation_interval", "window_size"}
    if not isinstance(data, dict) or set(data) != fields:
        raise ValueError(
            "detector requires type, threshold, minimum_std, adaptation_interval, and window_size"
        )
    if data["type"] != FixedScheduleZScore.identifier:
        raise ValueError("detector type must be zscore_fixed_schedule")
    return FixedScheduleConfig(
        **{key: value for key, value in data.items() if key != "type"}
    )


def load_experiment(path: Path) -> static_baseline.Experiment[FixedScheduleConfig]:
    return static_baseline.load_experiment(path, _parse_detector)


def adaptation_diagnostics(run: DevelopmentReplay) -> dict:
    records = run.result.records
    refits = []
    for offset, record in enumerate(records):
        if record.update is None:
            continue
        metadata = record.update.metadata["refit"]
        window = records[offset - metadata["window_size"] + 1 : offset + 1]
        anomaly_indices = [
            row.observation.index
            for row in window
            if row.observation.anomaly_label is True
        ]
        refits.append(
            {
                "index": record.observation.index,
                "first_window_index": window[0].observation.index,
                "last_window_index": window[-1].observation.index,
                "injected_anomalies_present": bool(anomaly_indices),
                "injected_anomaly_indices": anomaly_indices,
                **metadata,
            }
        )
    return {
        "refit_count": len(refits),
        "contaminated_refit_count": sum(
            refit["injected_anomalies_present"] for refit in refits
        ),
        "refits": refits,
    }


def _plot_run(run: DevelopmentReplay, output: Path, threshold: float) -> None:
    from matplotlib import pyplot as plt

    records = tuple(run.result.scored_records())
    x = [row.observation.index for row in records]
    y = [row.observation.value for row in records]
    truth = [i for i, row in enumerate(records) if row.observation.anomaly_label]
    predicted = [i for i, row in enumerate(records) if row.prediction.predicted_anomaly]
    diagnostics = adaptation_diagnostics(run)
    refits = diagnostics["refits"]

    fig, ax = plt.subplots(figsize=(10, 4), layout="constrained")
    ax.plot(x, y, color="#334155", linewidth=0.65, label="Value")
    ax.scatter(
        [x[i] for i in truth],
        [y[i] for i in truth],
        s=28,
        facecolors="none",
        edgecolors="#b91c1c",
        label="Injected anomaly",
    )
    ax.scatter(
        [x[i] for i in predicted],
        [y[i] for i in predicted],
        s=12,
        marker="x",
        color="#1d4ed8",
        label=f"Predicted anomaly (≥ {threshold:g})",
    )
    for i, event in enumerate(run.drift_events):
        label = "True drift" if i == 0 else None
        if event.start == event.end:
            ax.axvline(event.start, color="#a16207", linewidth=0.9, label=label)
        else:
            ax.axvspan(event.start, event.end, color="#fde68a", alpha=0.5, label=label)
    for i, refit in enumerate(refits):
        ax.axvline(
            refit["index"],
            color="#7e22ce",
            alpha=0.6,
            linestyle=":",
            linewidth=0.85,
            label="Scheduled refit" if i == 0 else None,
        )
    if refits:
        changes = [(x[0], refits[0]["before"]["mean"])]
        changes.extend(
            (refit["index"] + 1, refit["after"]["mean"])
            for refit in refits
            if refit["index"] < x[-1]
        )
        changes.append((x[-1], changes[-1][1]))
        indices, means = zip(*changes, strict=True)
        ax.step(
            indices,
            means,
            where="post",
            color="#047857",
            linewidth=1.2,
            label="Mean used for scoring",
        )
    ax.set(
        title=f"Development fixed schedule | {run.provenance.drift_type}, seed {run.provenance.stream_seed}",
        xlabel="Observation index",
        ylabel="Value",
    )
    ax.legend(loc="upper right", ncols=3, fontsize="small")
    fig.savefig(output, dpi=140)
    plt.close(fig)


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _comparison_metrics(aggregate: dict, adaptation_count: int) -> dict:
    pooled = aggregate["pooled"]
    return {
        **{
            key: pooled[key]
            for key in (
                "tp",
                "fp",
                "tn",
                "fn",
                "precision",
                "recall",
                "f1",
                "false_positive_rate",
                "pr_auc",
            )
        },
        "post_drift": pooled["false_positives_by_phase"]["post_drift"],
        "adaptation_count": adaptation_count,
    }


def _compare(output: Path, control_results: Path, experiment, aggregate: dict) -> dict:
    manifest = _read_json(control_results / "manifest.json")
    zscore = {
        "type": "zscore_static",
        "threshold": experiment.detector.threshold,
        "minimum_std": experiment.detector.minimum_std,
    }
    if (
        manifest.get("split") != "development"
        or manifest.get("warmup") != DEFAULT_WARMUP
        or manifest.get("grid")
        != {key: list(values) for key, values in experiment.grid.items()}
        or manifest.get("anomaly_adaptation") is not False
        or manifest.get("detectors", {}).get("zscore_static") != zscore
        or not manifest.get("git_commit")
    ):
        raise ValueError(
            "control reference must use the same development grid, warm-up, and Z-score parameters"
        )

    rows = _read_json(output / "per_stream_metrics.json")
    reference_rows = _read_json(control_results / "per_stream_checks.json")
    streams = {row["stream_id"]: row for row in reference_rows}
    if len(streams) != len(reference_rows) or len(rows) != len(streams):
        raise ValueError("control reference must cover exactly the same streams")
    totals = {"refit_count": 0, "contaminated_refit_count": 0}
    by_drift = {}
    for row in rows:
        reference = streams.pop(row["stream_id"], {}).get("drift", {}).get("adwin", {})
        if row["stream_parameters"] != reference.get("stream_parameters") or row[
            "scored_count"
        ] != reference.get("scored_count"):
            raise ValueError(
                f"control reference has different inputs for {row['stream_id']}"
            )
        group = by_drift.setdefault(row["drift_type"], {}).setdefault(
            row["variant"], dict.fromkeys(totals, 0)
        )
        for name in totals:
            count = row["adaptation"][name]
            totals[name] += count
            group[name] += count

    controls = _read_json(control_results / "control_report.json")["controls"]
    static = controls["static_zscore"]["anomaly"]
    comparisons = {"static_zscore": _comparison_metrics(static, 0)}
    for name in ("zscore_adwin_no_adaptation", "zscore_page_hinkley_no_adaptation"):
        control = controls[name]
        if control["anomaly_outputs_exact"] is not True or control["anomaly"] != static:
            raise ValueError(
                f"control reference did not establish anomaly invariance for {name}"
            )
        comparisons[name] = _comparison_metrics(control["anomaly"], 0)
    comparisons["fixed_schedule"] = _comparison_metrics(
        aggregate, totals["refit_count"]
    )
    return {
        "control_reference": {
            "directory": str(control_results),
            "git_commit": manifest["git_commit"],
        },
        "stream_count": len(rows),
        "methods": comparisons,
        "adaptation": {**totals, "by_drift": by_drift},
    }


def run_experiment(
    config: Path, output: Path, *, control_results: Path, plots: bool = False
) -> dict:
    experiment = load_experiment(config)
    with static_baseline.staged_output(output) as staged:
        aggregate = static_baseline.evaluate_baseline(
            experiment,
            config,
            staged,
            FixedScheduleZScore,
            plot=_plot_run if plots else None,
            diagnose=adaptation_diagnostics,
        )
        comparison = _compare(staged, control_results, experiment, aggregate)
        static_baseline.write_json(staged / "comparison.json", comparison)
    return comparison


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, required=True, help="new directory under results/"
    )
    parser.add_argument(
        "--control-results",
        type=Path,
        required=True,
        help="verified drift-without-adaptation control outputs",
    )
    parser.add_argument(
        "--plots",
        action="store_true",
        help="plot the canonical injected stream per drift type",
    )
    args = parser.parse_args()
    try:
        result = run_experiment(**vars(args))
    except (OSError, ValueError, yaml.YAMLError) as error:
        parser.exit(1, f"Fixed schedule: {error}\n")
    print(
        f"Development fixed schedule: {result['stream_count']} streams, "
        f"{result['adaptation']['refit_count']} scheduled refits. Results in {args.output}."
    )


if __name__ == "__main__":
    main()
