"""Package verified results without executing research experiments."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
from shutil import copy2

import yaml

from drift_anomaly.experiments.validation import execution_revision


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def figures(path, workload):
    path.mkdir(exist_ok=True)
    for source in Path("results/final_evaluation/report_artifacts/plots").glob("*.png"):
        copy2(source, path / source.name)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(8.5, 3.6), layout="constrained")
    for count in (1, 4, 8):
        rows = [row for row in workload if row["source_count"] == count]
        rates = [row["observed_arrival_records_sec"] for row in rows]
        axes[0].plot(
            rates,
            [r["sustained_records_sec"] for r in rows],
            "-o",
            label=f"{count} streams",
        )
        axes[1].plot(
            rates, [r["producer_to_commit_latency_seconds"]["p95"] for r in rows], "-o"
        )
    axes[0].set_ylabel("Committed records/s")
    axes[1].set_ylabel("p95 publish-to-commit (s)")
    for ax in axes:
        ax.set_xlabel("Observed arrival records/s")
        ax.grid(alpha=0.2)
    axes[0].legend(frameon=False)
    fig.suptitle("Single-host local Spark benchmark")
    fig.savefig(path / "spark_sustained.png", dpi=220)
    fig.savefig(path / "spark_sustained.pdf")
    plt.close(fig)


def package(output, matrix):
    spec = yaml.safe_load(Path("configs/final_evaluation.yaml").read_text())
    receipt = spec["execution_receipt"]
    if (
        spec["status"] != "executed"
        or execution_revision() != spec["software_revision"]["value"]
    ):
        raise ValueError("research source does not match the sealed receipt")
    for path, checksum in receipt["sha256"].items():
        if digest(path) != checksum:
            raise ValueError(f"sealed artifact checksum mismatch: {path}")
    base = Path("results/final_evaluation")
    synthetic = read(base / "primary_synthetic/comparison.json")
    nab = read(base / "nab_final.json")["pooled"]
    ablation = read("results/selective-eval-verified.4utR15qc/full/comparison.json")
    cases = read(base / "report_artifacts/failure_cases.json")
    workload = read(matrix / "matrix.json")
    summary = {
        "research_revision": receipt["frozen_git_commit"],
        "research_fingerprint": spec["software_revision"]["value"],
        "sealed_artifact_hashes": receipt["sha256"],
        "synthetic": {k: v["anomaly"]["pooled"] for k, v in synthetic.items()},
        "nab": {
            k: {field: value for field, value in v.items() if field != "across_series"}
            for k, v in nab.items()
        },
        "update_efficiency": {
            k: {
                f: v["adaptation"][f]
                for f in (
                    "refits",
                    "refit_input_uses",
                    "unnecessary_refits",
                    "onset_delay",
                )
            }
            for k, v in synthetic.items()
        },
        "statistics": read(base / "primary_synthetic/paired_statistics.json"),
        "confirmatory": read(base / "confirmatory_result.json"),
        "failures": [
            {**{f: c[f] for f in ("arm", "series", "index", "rank")}, "case": k}
            for k, c in cases.items()
        ],
        "development_drift": {
            "ADWIN": read("results/adwin-verified.Yefdh7sZ/full/aggregate.json")[
                "pooled"
            ],
            "Page-Hinkley": read(
                "results/page-hinkley-verified.glGDaztY/full/aggregate.json"
            )["pooled"],
        },
        "development_ablation": {
            k: {
                "post_drift_fp": v["anomaly"]["pooled"]["false_positives_by_phase"][
                    "post_drift"
                ]["fp"],
                "recall": v["anomaly"]["pooled"]["recall"],
                "refits": v["adaptation"]["refits"],
            }
            for k, v in ablation.items()
        },
        "spark_sustained": workload,
        "spark_backlog": read("results/spark-streaming-verified/benchmark.json"),
        "spark_runtime": read(matrix / "s1-r512/manifest.json"),
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "delivery.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n"
    )
    if output.resolve().is_relative_to(Path("results").resolve()):
        for name in (
            "synthetic",
            "nab",
            "development_drift",
            "development_ablation",
            "update_efficiency",
            "statistics",
            "spark_sustained",
        ):
            data = summary[name]
            rows = (
                [{"method": key, **row} for key, row in data.items()]
                if isinstance(data, dict)
                else data
            )
            if name == "synthetic":
                rows = [
                    {
                        **row,
                        "post_drift_fp": row["false_positives_by_phase"]["post_drift"][
                            "fp"
                        ],
                    }
                    for row in rows
                ]
            if name == "spark_sustained":
                rows = [
                    {
                        **row,
                        "p50_batch_seconds": row["batch_processing_seconds"]["p50"],
                        "p95_batch_seconds": row["batch_processing_seconds"]["p95"],
                        "p95_commit_seconds": row["producer_to_commit_latency_seconds"][
                            "p95"
                        ],
                    }
                    for row in rows
                ]
            fields = list(
                dict.fromkeys(
                    key for row in rows for key in row if not isinstance(row[key], dict)
                )
            )
            with (output / f"{name}.csv").open(
                "w", newline="", encoding="utf-8"
            ) as stream:
                writer = csv.DictWriter(
                    stream, fieldnames=fields, extrasaction="ignore"
                )
                writer.writeheader()
                writer.writerows(rows)
        figures(output / "plots", workload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/delivery"))
    parser.add_argument("--matrix", type=Path, default=Path("results/spark-sustained"))
    args = parser.parse_args()
    package(args.output, args.matrix)


if __name__ == "__main__":
    main()
