"""Verify a published final run and render reports from its frozen outputs."""

import argparse
import csv
import hashlib
import json
import math
import subprocess
from pathlib import Path
from statistics import median

import yaml

from drift_anomaly import nab
from drift_anomaly.drift_evaluation import evaluate_drift
from drift_anomaly.evaluation import AnomalyEvaluation
from drift_anomaly.experiments.final_evaluation import frozen_spec
from drift_anomaly.experiments.selective_evaluation import _stream_details
from drift_anomaly.experiments.static_baseline import (
    prepare_plots,
    staged_output,
    write_json,
)
from drift_anomaly.experiments.validation import (
    HOLDOUT_GRID,
    _replay_frozen,
    frozen_arms,
)
from drift_anomaly.experiments.validation_cases import FailureCases
from drift_anomaly.experiments.validation_stats import synthetic_contrasts
from drift_anomaly.nab_replay import MANIFEST, RAW_NAB, _load_series, replay_nab
from drift_anomaly.synthetic import SyntheticConfig

COUNTS = ("tp", "fp", "tn", "fn")
LABELS = {
    "static_zscore": "Static Z-score",
    "fixed_schedule": "Fixed schedule",
    "zscore_adwin_no_adaptation": "Frozen Z-score + ADWIN",
    "zscore_page_hinkley_no_adaptation": "Frozen Z-score + Page-Hinkley",
    "immediate": "Immediate ADWIN",
    "persistence": "ADWIN + persistence",
    "filtering": "Persistence + filtering",
    "full": "Full selective policy",
    "isolation_forest": "Isolation Forest",
    "lof": "LOF",
}


def read_json(path):
    return json.loads(path.read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_metrics(row):
    tp, fp, tn, fn = (row[key] for key in COUNTS)
    require(tp + fp + tn + fn == row["scored_count"], "invalid scored denominator")
    require(tp + fn == row["anomaly_count"], "invalid anomaly denominator")
    for name, num, den in (
        ("precision", tp, tp + fp),
        ("recall", tp, tp + fn),
        ("f1", 2 * tp, 2 * tp + fp + fn),
        ("false_positive_rate", fp, fp + tn),
    ):
        require(row[name] == (num / den if den else None), f"invalid {name}")
    ap = row["pr_auc"]
    require(
        0 <= ap <= 1 if tp + fn and tn + fp else ap is None,
        "invalid average precision",
    )


def check_synthetic(folder, spec):
    comparison = read_json(folder / "comparison.json")
    timing = read_json(folder / "runtime.json")
    arms = spec["synthetic"]["arms"]
    require(set(comparison) == set(timing) == set(arms), "unexpected synthetic methods")
    size = spec["synthetic"]["streams_per_arm"]
    by_arm = {}
    reference = None
    for arm in arms:
        rows = read_json(folder / f"{arm}_streams.json")
        by_arm[arm] = rows
        keys = {
            row["stream_id"]: (row["stream_parameters"], row["variant"]) for row in rows
        }
        require(len(keys) == len(rows) == size, f"invalid {arm} stream count")
        require(
            {row["seed"] for row in rows} == set(HOLDOUT_GRID["seeds"]),
            "development or robustness seed in primary holdout",
        )
        if reference is None:
            reference = keys
        require(reference == keys, "inconsistent synthetic pair membership")
        pooled = comparison[arm]["anomaly"]["pooled"]
        check_metrics(pooled)
        require(pooled["anomaly_count"] == size * 6, "incorrect injection count")
        if arm in ("full", "persistence", "filtering"):
            cutoff = spec["models"]["selective"]["persistence_cutoff"]
            require(
                comparison[arm]["persistence_cutoff"] == cutoff
                and all(row["persistence_cutoff"] == cutoff for row in rows),
                "persistence cutoff differs from the freeze",
            )
        for key in (*COUNTS, "scored_count"):
            require(
                pooled[key] == sum(row[key] for row in rows), f"{arm} {key} mismatch"
            )
        for row in rows:
            check_metrics(row)
            require(
                row["warmup"] == spec["warmup"] and row["scored_count"] == 3840,
                "invalid synthetic warm-up or horizon",
            )
            require(
                row["anomaly_count"] == (12 if row["variant"] == "injected" else 0),
                "invalid paired anomaly count",
            )
            require(
                sum(part["fp"] for part in row["false_positives_by_phase"].values())
                == row["fp"],
                "synthetic phase FP counts do not sum to point FP",
            )
            configure = row["stream_parameters"]
            if row["drift_type"] != "none":
                require(
                    configure["drift_start"] in HOLDOUT_GRID["onsets"]
                    and configure["post_mean"] in HOLDOUT_GRID["shifts"],
                    "unexpected primary holdout scenario",
                )
            if row["drift_type"] in ("gradual", "incremental"):
                require(
                    configure["drift_duration"] in HOLDOUT_GRID["durations"],
                    "unexpected ramp duration",
                )
            require(configure["split"] == "final_evaluation", "incorrect source split")
            detail = row["adaptation"]
            require(
                detail["refits"]
                == detail["matched_refits"] + detail["unnecessary_refits"],
                "refit mismatch",
            )
            require(
                detail["refits"] == len(detail["refit_input_sizes"]) <= 15
                and detail["refit_input_uses"]
                == sum(detail["refit_input_sizes"])
                <= 3840,
                "invalid synthetic refit budget",
            )
        updates = comparison[arm]["adaptation"]
        for key in (
            "eligible_events",
            "refits",
            "refit_input_uses",
            "unnecessary_refits",
        ):
            require(
                updates[key] == sum(row["adaptation"][key] for row in rows),
                f"{arm} {key} mismatch",
            )
        require(updates["eligible_events"] == 1280, "unexpected true event count")
        require(
            timing[arm]["scored_count"] == size * 3840
            and math.isclose(
                timing[arm]["elapsed_seconds"],
                sum(item["elapsed_seconds"] for item in timing[arm]["per_stream"]),
            ),
            "synthetic timing counts do not reconcile",
        )

    for control in ("zscore_adwin_no_adaptation", "zscore_page_hinkley_no_adaptation"):
        require(
            comparison[control]["anomaly"] == comparison["static_zscore"]["anomaly"],
            "no-adaptation control differs from static Z-score",
        )
    contrast_rows = read_json(folder / "paired_statistics.json")
    require(contrast_rows == synthetic_contrasts(by_arm), "paired statistics mismatch")
    return comparison, timing, by_arm, contrast_rows


def check_nab(output, spec, dataset):
    data = read_json(output / "nab_final.json")
    targets = spec["nab"]["final_sha256"]
    require(
        targets == dataset["final_evaluation"]
        and targets.keys().isdisjoint(dataset["development"]),
        "NAB split mismatch",
    )
    require(
        set(data["by_arm"]) == set(data["pooled"]) == set(spec["nab"]["arms"]),
        "unexpected NAB methods",
    )
    require(data["drift_truth_available"] is False, "NAB has no drift truth")
    provenance = read_json(
        RAW_NAB / dataset["revision"] / "provenance_final_evaluation.json"
    )
    required = {*dataset["metadata"], *(f"data/{name}" for name in targets)}
    require(provenance["files"].keys() == required, "unexpected NAB provenance files")
    metadata = nab.provenance(dataset)
    require(
        provenance["revision"] == dataset["revision"]
        and all(
            provenance["files"][name] == metadata["files"][name] for name in required
        ),
        "inconsistent NAB pin",
    )
    for name, entry in provenance["files"].items():
        path = RAW_NAB / provenance["revision"] / name
        require(
            hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"],
            f"NAB checksum mismatch for {name}",
        )
    for arm, rows in data["by_arm"].items():
        require(
            len(rows) == len(targets)
            and {row["series"]: row["sha256"] for row in rows} == targets,
            "NAB source membership mismatch",
        )
        pooled = data["pooled"][arm]
        check_metrics(pooled)
        for row in rows:
            check_metrics(row)
            require(
                row["source_revision"] == dataset["revision"]
                and row["drift_truth_available"] is False
                and "drift_window" not in row,
                "NAB provenance or metrics mismatch",
            )
            require(
                row["window_hits"]
                == sum(window["hit"] is True for window in row["windows"])
                and row["eligible_windows"]
                == sum(window["hit"] is not None for window in row["windows"]),
                "NAB window counts do not reconcile",
            )
        for key in (*COUNTS, "scored_count", "window_hits", "eligible_windows"):
            require(
                pooled[key] == sum(row[key] for row in rows),
                f"NAB {arm} {key} mismatch",
            )
    return data, provenance


def representative_synthetic(rows, cases):
    candidates = (
        next((r for r in rows if r["fn"]), None),
        next((r for r in rows if r["adaptation"]["unnecessary_refits"]), None),
        max(
            rows,
            key=lambda r: max(
                (m["onset_delay"] or 0 for m in r["adaptation"]["refit_matches"]),
                default=0,
            ),
        ),
        max(rows, key=lambda r: r["drift_window"]["fp"]),
        max(
            (r for r in rows if r["drift_type"] == "recurring"),
            key=lambda r: r["drift_window"]["fp"],
        ),
    )
    (arm,) = frozen_arms(["full"])
    selected = {row["stream_id"]: row for row in candidates if row is not None}
    for stream_id, row in selected.items():
        config = SyntheticConfig(**row["stream_parameters"])
        run = _replay_frozen(
            config,
            arm.factory,
            config_path=Path(row["stream_config_path"]),
            grid=HOLDOUT_GRID,
            split="primary_synthetic_holdout",
        )
        evaluation = AnomalyEvaluation()
        evaluation.add(run.result.scored_records(), run.drift_events)
        summary = evaluation.summary()
        require(
            all(row[key] == value for key, value in summary.items()),
            "targeted synthetic case failed to reproduce",
        )
        details = _stream_details(arm, run, stream_id, {})
        drift = evaluate_drift(run)
        require(
            json.loads(json.dumps(details)) == row["adaptation"]
            and list(drift.alarm_indices) == row["alarm_indices"],
            "targeted case refits or alarms failed to reproduce",
        )
        cases.synthetic(arm.name, stream_id, run, details, drift)
    return list(selected)


def representative_nab(data, dataset, cases):
    baseline = {row["series"]: row for row in data["by_arm"]["static_zscore"]}
    selected = None
    for arm in ("fixed_schedule", "persistence", "full"):
        for row in data["by_arm"][arm]:
            control = baseline[row["series"]]
            for window, other in zip(row["windows"], control["windows"], strict=True):
                lost = other["hit"] is True and window["hit"] is False
                delta = window["point_false_positives"] - other["point_false_positives"]
                if lost or delta > 0:
                    rank = 10000 * lost + delta
                    if selected is None or rank > selected[0]:
                        selected = rank, arm, row, window
    if selected is None:
        return None
    rank, method, row, window = selected
    stream = _load_series(row["series"], dataset, RAW_NAB, split="final_evaluation")
    (arm,) = frozen_arms([method])
    result = replay_nab(stream, arm.factory)
    metric = AnomalyEvaluation()
    metric.add(result.scored_records())
    require(
        all(row[key] == metric.summary()[key] for key in COUNTS),
        "targeted NAB case failed to reproduce",
    )
    events = row["adaptation"]
    cases.consider(
        "nab_window_worsened",
        rank,
        method,
        row["series"],
        window["start_index"],
        result,
        alarms=[a["index"] for a in events["adwin"]["alarms"]]
        if events["adwin"]
        else (),
        refits=[r["index"] for r in events["refits"]],
        windows=[
            (w["start_index"], w["end_index_exclusive"] - 1) for w in row["windows"]
        ],
    )
    return {"method": method, "series": row["series"], "window": window, "rank": rank}


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def results_plot(folder, name, rows, panels):
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter

    fig, axes = plt.subplots(1, len(panels), figsize=(12, 4.6), layout="constrained")
    fig.suptitle(
        "Primary synthetic holdout"
        if name.startswith("synthetic")
        else "Final NAB series",
        fontsize=14,
        fontweight="semibold",
    )
    for ax, (key, title) in zip(axes, panels, strict=True):
        bars = ax.barh(
            [LABELS[method] for method in rows],
            [row[key] for row in rows.values()],
            color=[
                "#06766d"
                if method == "full"
                else "#417ec1"
                if method == "persistence"
                else "#8c9aac"
                for method in rows
            ],
        )
        if key == "recall":
            ax.xaxis.set_major_formatter(PercentFormatter(1.0))
            ax.bar_label(
                bars,
                labels=[f"{row[key]:.1%}" for row in rows.values()],
                padding=4,
                fontsize=8,
            )
        else:
            ax.bar_label(
                bars,
                labels=[f"{row[key]:,}" for row in rows.values()],
                padding=4,
                fontsize=8,
            )
        ax.set_title(title, loc="left")
        ax.margins(x=0.20)
        ax.invert_yaxis()
    fig.savefig(folder / name, dpi=160)
    plt.close(fig)


def publish(output, target):
    manifest = read_json(output / "manifest.json")
    spec = manifest["freeze"]
    recorded = yaml.safe_load(
        subprocess.check_output(
            ["git", "show", f"{manifest['git_commit']}:configs/final_evaluation.yaml"],
            text=True,
        )
    )
    require(
        recorded == spec
        and json.dumps(spec, sort_keys=True)
        == json.dumps(frozen_spec(), sort_keys=True),
        "execution source or frozen specification mismatch",
    )
    require(
        manifest["execution_tree_sha256"] == spec["software_revision"]["value"],
        "execution fingerprint mismatch",
    )
    synthetic, timing, rows, contrasts = check_synthetic(
        output / "primary_synthetic", spec
    )
    dataset = nab.load_config(MANIFEST)
    real, provenance = check_nab(output, spec, dataset)
    primary = read_json(output / "confirmatory_result.json")
    require(
        primary["comparison"]
        == {
            row["metric"]: row
            for row in contrasts
            if (row["left"], row["right"]) == tuple(spec["metrics"]["primary_pair"])
        },
        "confirmatory contrasts mismatch",
    )
    effects = primary["comparison"]
    require(
        primary["meets_both_frozen_criteria"]
        == (
            effects["event_window_fpr"]["ci95"][1]
            < spec["metrics"]["fpr_ci_upper_bound_below"]
            and effects["recall"]["ci95"][0]
            > spec["metrics"]["recall_ci_lower_bound_above"]
        ),
        "confirmatory decision mismatch",
    )

    cases = FailureCases()
    synthetic_cases = representative_synthetic(rows["full"], cases)
    nab_case = representative_nab(real, dataset, cases)
    with staged_output(target) as staged:
        cost = [
            {
                "method": arm,
                "refits": item["adaptation"]["refits"],
                "median_refits_per_stream": median(
                    r["adaptation"]["refits"] for r in rows[arm]
                ),
                "refit_inputs": item["adaptation"]["refit_input_uses"],
                "unnecessary_refits": item["adaptation"]["unnecessary_refits"],
                "matched_refits": item["adaptation"]["matched_refits"],
                "median_refit_delay": item["adaptation"]["onset_delay"]["median"],
                "seconds": timing[arm]["elapsed_seconds"],
                "scored_per_second": timing[arm]["scored_observations_per_second"],
            }
            for arm, item in synthetic.items()
        ]
        write_csv(staged / "adaptation_cost.csv", cost)
        write_csv(staged / "paired_statistics.csv", contrasts)
        write_json(
            staged / "dataset_provenance.json",
            {
                "nab": provenance,
                "synthetic": spec["synthetic"],
                "execution_git_sha": manifest["git_commit"],
            },
        )
        write_json(
            staged / "verification.json",
            {
                "execution_git_sha": manifest["git_commit"],
                "synthetic_replays": sum(len(items) for items in rows.values()),
                "nab_replays": sum(len(items) for items in real["by_arm"].values()),
                "targeted_synthetic_case_replays": synthetic_cases,
                "targeted_nab_case_replay": nab_case,
                "prespecified_paired_comparisons": len(contrasts),
            },
        )
        cases.publish(staged)
        plots = staged / "plots" if cases.cases else prepare_plots(staged)
        results_plot(
            plots,
            "synthetic_comparison.png",
            {
                arm: {
                    **item["anomaly"]["pooled"],
                    "post_drift_fp": item["anomaly"]["pooled"][
                        "false_positives_by_phase"
                    ]["post_drift"]["fp"],
                }
                for arm, item in synthetic.items()
            },
            (
                ("post_drift_fp", "Post-drift false positives"),
                ("recall", "Point recall"),
            ),
        )
        results_plot(
            plots,
            "nab_comparison.png",
            real["pooled"],
            (("fp", "Point false positives"), ("recall", "Point recall")),
        )
    print(f"Verified all frozen final outputs and exported {target}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=Path("results/final_evaluation"))
    parser.add_argument(
        "--output", type=Path, default=Path("results/final_evaluation/report_artifacts")
    )
    args = parser.parse_args()
    publish(args.run, args.output)


if __name__ == "__main__":
    main()
