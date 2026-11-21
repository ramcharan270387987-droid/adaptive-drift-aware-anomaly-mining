"""Validate the frozen manifest and require explicit authorization to evaluate."""

import argparse
import json
import resource
from dataclasses import asdict
from pathlib import Path

import yaml

from drift_anomaly import nab
from drift_anomaly.experiments import (
    isolation_forest_baseline,
    lof_baseline,
    page_hinkley_baseline,
    static_baseline,
)
from drift_anomaly.experiments.nab_evaluation import run_nab
from drift_anomaly.experiments.selective_smoke import FROZEN_ADWIN, FROZEN_ZSCORE
from drift_anomaly.experiments.validation import (
    CONFIGS,
    HOLDOUT_GRID,
    NAB_ARMS,
    ROBUSTNESS_ARMS,
    ROBUSTNESS_GRID,
    execution_revision,
    frozen_arms,
    run_manifest,
    run_synthetic,
)
from drift_anomaly.experiments.validation_cases import FailureCases
from drift_anomaly.experiments.validation_stats import (
    BOOTSTRAP_REPLICATES,
    BOOTSTRAP_SEED,
)
from drift_anomaly.fixed_schedule import FixedScheduleConfig
from drift_anomaly.nab_replay import MANIFEST, RAW_NAB, _load_series
from drift_anomaly.replay import DEFAULT_WARMUP
from drift_anomaly.selective_adaptation import (
    BLOCK_SIZE,
    CHECKPOINTS,
    COOLDOWN,
    MAX_FIT_INPUTS,
    MAX_REFITS,
    MIN_RETAINED,
    SHIFT_CUTOFF,
    WINDOW_SIZE,
)

FINAL_ARMS = (*ROBUSTNESS_ARMS, "isolation_forest", "lof")
FINAL_CONFIG = Path("configs/final_evaluation.yaml")


def frozen_spec():
    data = nab.load_config(MANIFEST)
    return {
        "schema_version": 1,
        "status": "frozen",
        "software_revision": {
            "type": "execution_tree_sha256",
            "value": execution_revision(),
        },
        "confirmatory_method": "full",
        "development_selected_secondary": "persistence",
        "selection_evidence": "aligned_synthetic_development",
        "warmup": DEFAULT_WARMUP,
        "synthetic": {
            "split": "primary_synthetic_holdout",
            "grid": HOLDOUT_GRID,
            "templates": sorted(
                str(path) for path in Path("configs/synthetic").glob("*_holdout.yaml")
            ),
            "streams_per_arm": 1000,
            "families": ["stationary", "sudden", "gradual", "incremental", "recurring"],
            "injection": {
                "paired": True,
                "count": 12,
                "min_separation": 16,
                "magnitude": 6.0,
            },
            "length": 4096,
            "state_offset": 512,
            "standard_deviation": 1.0,
            "arms": FINAL_ARMS,
        },
        "robustness": {
            "grid": ROBUSTNESS_GRID,
            "streams_per_arm": 500,
            "arms": ROBUSTNESS_ARMS,
            "stage_status": "already_observed_separate_robustness_excluded_from_final_command",
        },
        "nab": {
            "manifest": str(MANIFEST),
            "revision": data["revision"],
            "final_sha256": data["final_evaluation"],
            "arms": NAB_ARMS,
            "point_rule": "exact_timestamp_first_source_row",
            "window_rule": "inclusive_endpoints_at_most_one_hit_per_scored_window",
            "timestamp_rule": "source_order_keep_ties_skip_backwards_without_sorting",
            "drift_truth_available": False,
        },
        "models": {
            "zscore": asdict(FROZEN_ZSCORE),
            "adwin": asdict(FROZEN_ADWIN),
            "page_hinkley": asdict(
                page_hinkley_baseline.load_experiment(
                    CONFIGS / "page_hinkley_dev.yaml"
                ).detector
            ),
            "fixed_schedule": asdict(FixedScheduleConfig(3.0, 1e-12, 256, 256)),
            "isolation_forest": asdict(
                isolation_forest_baseline.load_experiment(
                    CONFIGS / "isolation_forest_dev.yaml"
                ).detector
            ),
            "lof": asdict(
                lof_baseline.load_experiment(CONFIGS / "lof_dev.yaml").detector
            ),
            "selective": {
                "persistence_cutoff": SHIFT_CUTOFF,
                "checkpoints": CHECKPOINTS,
                "median_block_size": BLOCK_SIZE,
                "window_size": WINDOW_SIZE,
                "min_retained": MIN_RETAINED,
                "max_refits": MAX_REFITS,
                "max_input_uses": MAX_FIT_INPUTS,
                "immediate": {
                    "candidate": "trailing_window_including_alarm",
                    "persistence": False,
                    "filter": False,
                    "cooldown": 0,
                },
                "persistence": {
                    "candidate": "strictly_post_alarm",
                    "persistence": True,
                    "filter": False,
                    "cooldown": 0,
                },
                "filtering": {
                    "candidate": "strictly_post_alarm",
                    "persistence": True,
                    "filter": True,
                    "cooldown": 0,
                },
                "full": {
                    "candidate": "strictly_post_alarm",
                    "persistence": True,
                    "filter": True,
                    "cooldown": COOLDOWN,
                },
            },
        },
        "metrics": {
            "pointwise": [
                "tp",
                "fp",
                "tn",
                "fn",
                "precision",
                "recall",
                "f1",
                "fpr",
                "average_precision",
            ],
            "nab_supplement": [
                "window_hit_rate",
                "observed_alarm_refit_window_proximity",
            ],
            "synthetic_supplement": [
                "phase_false_positives",
                "event_window_fpr",
                "alarm_matching",
                "refit_matching",
            ],
            "cost": [
                "refits",
                "refit_input_uses",
                "elapsed_seconds",
                "scored_throughput",
                "peak_process_rss",
            ],
            "primary_pair": ["full", "static_zscore"],
            "event_window_after_end": 256,
            "alarm_window_after_end": 128,
            "refit_window_after_end": 384,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "fpr_ci_upper_bound_below": 0.0,
            "recall_ci_lower_bound_above": -0.05,
        },
        "stages": [
            "validate_manifest_and_authorization",
            "verify_nab_final_provenance",
            "primary_synthetic_holdout",
            "nab_final",
            "report",
        ],
        "output": "results/final_evaluation",
    }


def load_frozen(path):
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    if json.dumps(spec, sort_keys=True) != json.dumps(frozen_spec(), sort_keys=True):
        raise ValueError("incomplete, modified, or unfrozen final evaluation manifest")
    return spec


def run_final(spec):
    dataset = nab.load_config(MANIFEST)
    with static_baseline.staged_output(Path(spec["output"])) as staged:
        nab.fetch_split(dataset, RAW_NAB / dataset["revision"], "final_evaluation")
        streams = [
            _load_series(name, dataset, RAW_NAB, split="final_evaluation")
            for name in spec["nab"]["final_sha256"]
        ]
        synthetic = staged / "primary_synthetic"
        synthetic.mkdir()
        paired = run_synthetic(
            synthetic,
            arms=FINAL_ARMS,
            grid=HOLDOUT_GRID,
            split="primary_synthetic_holdout",
        )
        primary = {
            row["metric"]: row
            for row in paired
            if row["left"] == "full" and row["right"] == "static_zscore"
        }
        fpr = primary["event_window_fpr"]["ci95"]
        recall = primary["recall"]["ci95"]
        static_baseline.write_json(
            staged / "confirmatory_result.json",
            {
                "comparison": primary,
                "meets_both_frozen_criteria": bool(
                    fpr and recall and fpr[1] < 0 and recall[0] > -0.05
                ),
            },
        )
        static_baseline.write_json(
            staged / "nab_final.json",
            run_nab(streams, frozen_arms(NAB_ARMS), FailureCases()),
        )
        static_baseline.write_json(
            staged / "manifest.json",
            {
                **run_manifest(),
                "freeze": spec,
                "peak_process_rss_kib": resource.getrusage(
                    resource.RUSAGE_SELF
                ).ru_maxrss,
            },
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=FINAL_CONFIG)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the freeze without opening evaluation data",
    )
    parser.add_argument(
        "--authorize-final", action="store_true", help="explicitly open final outcomes"
    )
    args = parser.parse_args()
    try:
        spec = load_frozen(args.config)
        if args.check:
            print("Frozen final evaluation manifest verified.")
        elif args.authorize_final:
            run_final(spec)
        else:
            raise ValueError("final evaluation requires --authorize-final")
    except (ValueError, OSError, yaml.YAMLError) as error:
        parser.exit(1, f"Final evaluation: {error}\n")


if __name__ == "__main__":
    main()
