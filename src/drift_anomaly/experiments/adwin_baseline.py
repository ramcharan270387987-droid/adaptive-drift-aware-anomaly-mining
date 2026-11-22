"""Evaluate raw-value ADWIN on paired synthetic development streams."""

import argparse
from pathlib import Path

import yaml

from drift_anomaly.adwin import ADWINConfig, ADWINDetector
from drift_anomaly.experiments import drift_baseline, static_baseline


def _parse_detector(data: object) -> ADWINConfig:
    fields = {
        "type",
        "delta",
        "clock",
        "max_buckets",
        "min_window_length",
        "grace_period",
        "signal",
    }
    if not isinstance(data, dict) or set(data) != fields:
        raise ValueError(
            "detector requires type, delta, clock, max_buckets, min_window_length, grace_period, and signal"
        )
    if data["type"] != ADWINDetector.identifier:
        raise ValueError("detector type must be adwin")
    return ADWINConfig(**{key: value for key, value in data.items() if key != "type"})


def load_experiment(path: Path) -> static_baseline.Experiment[ADWINConfig]:
    return static_baseline.load_experiment(path, _parse_detector)


def run_experiment(config_path: Path, output: Path, *, plots: bool = False) -> dict:
    return drift_baseline.run_baseline(
        config_path,
        output,
        parse_detector=_parse_detector,
        build_detector=ADWINDetector,
        detector_label="ADWIN",
        plots=plots,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, required=True, help="new directory under results/"
    )
    parser.add_argument(
        "--plots", action="store_true", help="plot one canonical pair per drift type"
    )
    args = parser.parse_args()
    try:
        aggregate = run_experiment(args.config, args.output, plots=args.plots)["pooled"]
    except (OSError, ValueError, yaml.YAMLError) as error:
        parser.exit(1, f"ADWIN experiment: {error}\n")
    print(
        f"Development ADWIN: {aggregate['stream_count']} streams, "
        f"{aggregate['detected_events']}/{aggregate['true_drift_events']} events matched, "
        f"{aggregate['false_alarms']} false alarms. Results in {args.output}."
    )


if __name__ == "__main__":
    main()
