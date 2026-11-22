"""Evaluate raw-value Page-Hinkley on paired synthetic development streams."""

import argparse
from pathlib import Path

import yaml

from drift_anomaly.experiments import drift_baseline, static_baseline
from drift_anomaly.page_hinkley import PageHinkleyConfig, PageHinkleyDetector


def _parse_detector(data: object) -> PageHinkleyConfig:
    fields = {"type", "min_instances", "delta", "threshold", "alpha", "mode", "signal"}
    if not isinstance(data, dict) or set(data) != fields:
        raise ValueError(
            "detector requires type, min_instances, delta, threshold, alpha, mode, and signal"
        )
    if data["type"] != PageHinkleyDetector.identifier:
        raise ValueError("detector type must be page_hinkley")
    return PageHinkleyConfig(
        **{key: value for key, value in data.items() if key != "type"}
    )


def load_experiment(path: Path) -> static_baseline.Experiment[PageHinkleyConfig]:
    return static_baseline.load_experiment(path, _parse_detector)


def run_experiment(
    config_path: Path,
    output: Path,
    *,
    plots: bool = False,
    adwin_results: Path | None = None,
) -> dict:
    return drift_baseline.run_baseline(
        config_path,
        output,
        parse_detector=_parse_detector,
        build_detector=PageHinkleyDetector,
        detector_label="Page-Hinkley",
        plots=plots,
        adwin_results=adwin_results,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, required=True, help="new directory under results/"
    )
    parser.add_argument(
        "--adwin-results", type=Path, help="reference ADWIN results for the same grid"
    )
    parser.add_argument(
        "--plots", action="store_true", help="plot one canonical pair per drift type"
    )
    args = parser.parse_args()
    try:
        aggregate = run_experiment(
            args.config, args.output, plots=args.plots, adwin_results=args.adwin_results
        )["pooled"]
    except (OSError, ValueError, yaml.YAMLError) as error:
        parser.exit(1, f"Page-Hinkley experiment: {error}\n")
    print(
        f"Development Page-Hinkley: {aggregate['stream_count']} streams, "
        f"{aggregate['detected_events']}/{aggregate['true_drift_events']} events matched, "
        f"{aggregate['false_alarms']} false alarms. Results in {args.output}."
    )


if __name__ == "__main__":
    main()
