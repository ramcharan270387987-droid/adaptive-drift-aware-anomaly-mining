"""Evaluate the static Isolation Forest baseline on synthetic development streams."""

import argparse
from pathlib import Path

import yaml

from drift_anomaly.experiments import static_baseline
from drift_anomaly.isolation_forest import IsolationForestConfig, StaticIsolationForest


def _parse_detector(data: object) -> IsolationForestConfig:
    required = {"type", "random_state", "n_estimators", "contamination", "max_samples"}
    if not isinstance(data, dict) or not required <= data.keys() <= required | {
        "threshold"
    }:
        raise ValueError(
            "detector requires type, random_state, n_estimators, contamination, and max_samples"
        )
    if data["type"] != StaticIsolationForest.identifier:
        raise ValueError("detector type must be isolation_forest_static")
    return IsolationForestConfig(
        **{name: value for name, value in data.items() if name != "type"}
    )


def load_experiment(path: Path) -> static_baseline.Experiment[IsolationForestConfig]:
    return static_baseline.load_experiment(path, _parse_detector)


def run_experiment(config: Path, output: Path, *, scored_csv: bool = False) -> dict:
    return static_baseline.run_baseline(
        config,
        output,
        parse_detector=_parse_detector,
        build_detector=StaticIsolationForest,
        scored_csv=scored_csv,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, required=True, help="new directory under results/"
    )
    parser.add_argument(
        "--scored-csv", action="store_true", help="export every scored observation"
    )
    args = parser.parse_args()
    try:
        aggregate = run_experiment(args.config, args.output, scored_csv=args.scored_csv)
    except (OSError, ValueError, yaml.YAMLError) as error:
        parser.exit(1, f"Isolation Forest experiment: {error}\n")
    print(
        f"Development baseline: {aggregate['stream_count']} streams, "
        f"{aggregate['pooled']['scored_count']} scored observations. Results in {args.output}."
    )


if __name__ == "__main__":
    main()
