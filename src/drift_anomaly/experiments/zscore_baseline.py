"""Evaluate the static Z-score baseline on the synthetic development grid."""

import argparse
from pathlib import Path

import yaml

from drift_anomaly.experiments import static_baseline
from drift_anomaly.replay import DevelopmentReplay
from drift_anomaly.zscore import StaticZScore, ZScoreConfig


def _parse_detector(data: object) -> ZScoreConfig:
    if not isinstance(data, dict) or set(data) != {"type", "threshold", "minimum_std"}:
        raise ValueError("detector requires type, threshold, and minimum_std")
    if data["type"] != StaticZScore.identifier:
        raise ValueError("detector type must be zscore_static")
    return ZScoreConfig(data["threshold"], data["minimum_std"])


def load_experiment(path: Path) -> static_baseline.Experiment[ZScoreConfig]:
    return static_baseline.load_experiment(path, _parse_detector)


def run_experiment(
    config_path: Path, output: Path, *, scored_csv: bool = False, plots: bool = False
) -> dict:
    return static_baseline.run_baseline(
        config_path,
        output,
        parse_detector=_parse_detector,
        build_detector=StaticZScore,
        scored_csv=scored_csv,
        plot=_plot_run if plots else None,
    )


def _plot_run(run: DevelopmentReplay, output: Path, threshold: float) -> None:
    from matplotlib import pyplot as plt

    records = tuple(run.result.scored_records())
    indices = [row.observation.index for row in records]
    values = [row.observation.value for row in records]
    scores = [row.prediction.score for row in records]
    truth = [i for i, row in enumerate(records) if row.observation.anomaly_label]
    predictions = [
        i for i, row in enumerate(records) if row.prediction.predicted_anomaly
    ]
    fig, (trace, score) = plt.subplots(
        2, 1, figsize=(10, 5), sharex=True, layout="constrained"
    )
    trace.plot(indices, values, color="#334155", linewidth=0.65, label="Value")
    trace.scatter(
        [indices[i] for i in truth],
        [values[i] for i in truth],
        facecolors="none",
        edgecolors="#b91c1c",
        s=30,
        label="True anomaly",
    )
    trace.scatter(
        [indices[i] for i in predictions],
        [values[i] for i in predictions],
        marker="x",
        s=9,
        color="#1d4ed8",
        alpha=0.65,
        label="Predicted anomaly",
    )
    score.plot(indices, scores, color="#1d4ed8", linewidth=0.65)
    score.axhline(
        threshold, color="#b91c1c", linestyle="--", label=f"Threshold {threshold:g}"
    )
    for event in run.drift_events:
        for axis in (trace, score):
            if event.start == event.end:
                axis.axvline(event.start, color="#a16207", linewidth=0.9)
            else:
                axis.axvspan(event.start, event.end, color="#fde68a", alpha=0.45)
                axis.axvline(event.start, color="#a16207", linewidth=0.7)
                axis.axvline(event.end, color="#a16207", linewidth=0.7)
    trace.set(
        title=f"Development static Z-score | {run.provenance.drift_type}, seed {run.provenance.stream_seed}",
        ylabel="Value",
    )
    score.set(xlabel="Observation index", ylabel="Absolute Z-score")
    trace.legend(loc="upper right", ncols=3)
    score.legend(loc="upper right")
    fig.savefig(output, dpi=140)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, required=True, help="new directory under results/"
    )
    parser.add_argument(
        "--scored-csv", action="store_true", help="export every scored observation"
    )
    parser.add_argument(
        "--plots",
        action="store_true",
        help="plot the canonical injected stream per drift type",
    )
    args = parser.parse_args()
    try:
        aggregate = run_experiment(
            args.config, args.output, scored_csv=args.scored_csv, plots=args.plots
        )
    except (OSError, ValueError, yaml.YAMLError) as error:
        parser.exit(1, f"Z-score experiment: {error}\n")
    print(
        f"Development baseline: {aggregate['stream_count']} streams, "
        f"{aggregate['pooled']['scored_count']} scored observations. Results in {args.output}."
    )


if __name__ == "__main__":
    main()
