"""Inspect selective adaptation on canonical development pairs only."""

import argparse
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

import yaml

from drift_anomaly.adwin import ADWINConfig, ADWINDetector
from drift_anomaly.experiments import adwin_baseline, static_baseline
from drift_anomaly.replay import (
    DevelopmentReplay,
    ReplayResult,
    replay_synthetic_development,
)
from drift_anomaly.selective_adaptation import (
    BLOCK_SIZE,
    CHECKPOINTS,
    COOLDOWN,
    MAX_FIT_INPUTS,
    MAX_REFITS,
    MIN_RETAINED,
    SHIFT_CUTOFF,
    WINDOW_SIZE,
    Ablation,
    RefitBudget,
    SelectiveZScore,
)
from drift_anomaly.zscore import StaticZScore, ZScoreConfig

FROZEN_ADWIN = ADWINConfig(0.002, 32, 5, 5, 10, "raw_value")
FROZEN_ZSCORE = ZScoreConfig(3.0, 1e-12)


def stream_diagnostics(run: DevelopmentReplay) -> dict:
    return selective_diagnostics(run.result)


def selective_diagnostics(result: ReplayResult) -> dict:
    indices = [record.observation.index for record in result.records]
    alarms = []
    proposals = {}
    budget = RefitBudget().as_metadata()
    for record in result.scored_records():
        if record.update is None:
            continue
        index = record.observation.index
        metadata = record.update.metadata
        budget = metadata["budget"]
        proposal = metadata.get("proposal")
        if proposal is not None:
            proposals[proposal["alarm_position"]] = {
                "alarm_index": index,
                "reference_mean": proposal["reference_mean"],
                "reference_scale": proposal["reference_scale"],
                "checkpoints": [],
                "status": "incomplete",
                "budget_at_alarm": proposal["budget_at_open"],
            }
        if record.update.drift_alarm:
            alarm = {
                "index": index,
                "disposition": metadata["alarm_disposition"],
                "budget": budget,
            }
            if "active_alarm_position" in metadata:
                alarm["active_alarm_index"] = indices[metadata["active_alarm_position"]]
            alarms.append(alarm)
        checkpoint = metadata.get("checkpoint")
        if checkpoint is None:
            continue
        proposal_record = proposals[checkpoint["alarm_position"]]
        candidate = [
            indices[position] for position in checkpoint["candidate_positions"]
        ]
        retained = [indices[position] for position in checkpoint["retained_positions"]]
        retained_set = set(retained)
        detail = {
            key: value
            for key, value in checkpoint.items()
            if key
            not in (
                "alarm_position",
                "candidate_positions",
                "retained_positions",
                "refit",
            )
        }
        detail.update(
            index=index,
            candidate_indices=candidate,
            retained_indices=retained,
            filtered_indices=[i for i in candidate if i not in retained_set],
            budget=budget,
        )
        if "refit" in checkpoint:
            refit = checkpoint["refit"]
            detail["refit"] = {
                "index": index,
                "terminal": index == indices[-1],
                "before": refit["before"],
                "after": refit["after"],
                "cooldown_positions": refit["cooldown"],
            }
        proposal_record["checkpoints"].append(detail)
        if checkpoint["decision"] != "wait":
            proposal_record["status"] = checkpoint["decision"]
    return {
        "alarms": alarms,
        "proposals": list(proposals.values()),
        "refit_count": budget["refits"],
        "refit_input_uses": budget["refit_input_uses"],
        "scored_count": result.stats.scored_count,
    }


def run_smoke(config: Path, output: Path) -> dict:
    experiment = adwin_baseline.load_experiment(config)
    if experiment.detector != FROZEN_ADWIN:
        raise ValueError("selective adaptation requires the frozen ADWIN configuration")
    rows = []
    provenance = None
    with static_baseline.staged_output(output) as staged:
        # One clean/injected pair per configured template, without expanding the grid.
        for path, template in experiment.streams:
            for variant, stream in static_baseline.paired_variants(template):
                for mode in Ablation:
                    run = replay_synthetic_development(
                        stream,
                        lambda mode=mode: SelectiveZScore(
                            StaticZScore(FROZEN_ZSCORE),
                            ADWINDetector(experiment.detector),
                            mode,
                        ),
                        config_path=path,
                    )
                    provenance = run.provenance
                    rows.append(
                        {
                            "mode": mode.value,
                            "variant": variant,
                            "stream_id": static_baseline.stream_id_for(stream, variant),
                            "stream_config_path": str(path),
                            "stream_parameters": provenance.stream_parameters,
                            **stream_diagnostics(run),
                        }
                    )
        assert provenance is not None
        summary = {
            "replays": len(rows),
            "pairs_per_mode": len(experiment.streams),
            "by_mode": {
                mode.value: {
                    "scored_count": sum(
                        row["scored_count"] for row in rows if row["mode"] == mode
                    ),
                    "alarms": sum(
                        len(row["alarms"]) for row in rows if row["mode"] == mode
                    ),
                    "refits": sum(
                        row["refit_count"] for row in rows if row["mode"] == mode
                    ),
                    "input_uses": sum(
                        row["refit_input_uses"] for row in rows if row["mode"] == mode
                    ),
                }
                for mode in Ablation
            },
        }
        static_baseline.write_json(
            staged / "manifest.json",
            {
                "git_commit": provenance.git_commit,
                "project_version": provenance.project_version,
                "dependencies": {name: version(name) for name in ("river", "numpy")},
                "split": provenance.split,
                "config": str(config),
                "warmup": provenance.warmup_length,
                "smoke_only": True,
                "adwin": asdict(experiment.detector),
                "zscore": asdict(FROZEN_ZSCORE),
                "checkpoints": CHECKPOINTS,
                "block_size": BLOCK_SIZE,
                "window_size": WINDOW_SIZE,
                "minimum_retained": MIN_RETAINED,
                "shift_cutoff": SHIFT_CUTOFF,
                "cooldown": COOLDOWN,
                "max_refits": MAX_REFITS,
                "max_refit_input_uses": MAX_FIT_INPUTS,
            },
        )
        static_baseline.write_json(staged / "per_stream_diagnostics.json", rows)
        static_baseline.write_json(staged / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/experiments/adwin_dev.yaml")
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="new directory under results/"
    )
    args = parser.parse_args()
    try:
        summary = run_smoke(args.config, args.output)
    except (OSError, ValueError, yaml.YAMLError) as error:
        parser.exit(1, f"Selective smoke: {error}\n")
    print(
        f"Ran {summary['replays']} development smoke replays. Diagnostics in {args.output}."
    )


if __name__ == "__main__":
    main()
