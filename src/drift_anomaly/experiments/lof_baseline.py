"""Evaluate static LOF novelty detection on synthetic development streams."""

import argparse
from pathlib import Path

import yaml

from drift_anomaly.experiments import static_baseline
from drift_anomaly.lof import LOFConfig, StaticLOF


def _parse_detector(data: object) -> LOFConfig:
    required = {
        "type",
        "n_neighbors",
        "contamination",
        "novelty",
        "metric",
        "decision_rule",
    }
    if not isinstance(data, dict) or set(data) != required:
        raise ValueError(
            "detector requires type, n_neighbors, contamination, novelty, metric, and decision_rule"
        )
    if data["type"] != StaticLOF.identifier:
        raise ValueError("detector type must be lof_static")
    return LOFConfig(**{name: value for name, value in data.items() if name != "type"})


def load_experiment(path: Path) -> static_baseline.Experiment[LOFConfig]:
    return static_baseline.load_experiment(path, _parse_detector)


def run_experiment(config: Path, output: Path, *, scored_csv: bool = False) -> dict:
    return static_baseline.run_baseline(
        config,
        output,
        parse_detector=_parse_detector,
        build_detector=StaticLOF,
        scored_csv=scored_csv,
        record_runtime=True,
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
        parser.exit(1, f"LOF experiment: {error}\n")
    print(
        f"Development baseline: {aggregate['stream_count']} streams, "
        f"{aggregate['pooled']['scored_count']} scored observations. Results in {args.output}."
    )


if __name__ == "__main__":
    main()
