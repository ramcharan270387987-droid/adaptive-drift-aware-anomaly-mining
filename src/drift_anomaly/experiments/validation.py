"""Run the frozen pre-final robustness and NAB development comparisons."""

import argparse
import hashlib
import json
import os
import platform
import resource
from dataclasses import replace
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from drift_anomaly import nab
from drift_anomaly.experiments import (
    adwin_baseline,
    isolation_forest_baseline,
    lof_baseline,
    page_hinkley_baseline,
    static_baseline,
)
from drift_anomaly.experiments.nab_evaluation import run_nab
from drift_anomaly.experiments.selective_evaluation import Arm, _arms, _run_arm
from drift_anomaly.experiments.validation_cases import FailureCases
from drift_anomaly.experiments.validation_stats import synthetic_contrasts
from drift_anomaly.isolation_forest import StaticIsolationForest
from drift_anomaly.lof import StaticLOF
from drift_anomaly.nab_replay import MANIFEST, RAW_NAB, load_development_series
from drift_anomaly.replay import _git_commit, _replay_synthetic

CONFIGS = Path("configs/experiments")
HOLDOUT_GRID = {
    "seeds": tuple(range(1000, 1020)),
    "onsets": (1536, 2560),
    "shifts": (1, 2.25),
    "durations": (192, 384),
}
ROBUSTNESS_GRID = {
    **HOLDOUT_GRID,
    "seeds": tuple(range(2000, 2010)),
    "onsets": (1603, 2747),
}
ROBUSTNESS_ARMS = (
    "full",
    "immediate",
    "persistence",
    "filtering",
    "static_zscore",
    "fixed_schedule",
    "zscore_adwin_no_adaptation",
    "zscore_page_hinkley_no_adaptation",
)
NAB_ARMS = (
    "static_zscore",
    "isolation_forest",
    "lof",
    "fixed_schedule",
    "persistence",
    "full",
)


def frozen_arms(names):
    page = page_hinkley_baseline.load_experiment(CONFIGS / "page_hinkley_dev.yaml")
    options = {arm.name: arm for arm in _arms(page.detector)}
    isolation = isolation_forest_baseline.load_experiment(
        CONFIGS / "isolation_forest_dev.yaml"
    ).detector
    lof = lof_baseline.load_experiment(CONFIGS / "lof_dev.yaml").detector
    options.update(
        isolation_forest=Arm(
            "isolation_forest", lambda: StaticIsolationForest(isolation)
        ),
        lof=Arm("lof", lambda: StaticLOF(lof)),
    )
    return [options[name] for name in names]


def frozen_experiment(grid):
    """Reuse the checked templates and alter only the fixed scenario grid and split."""
    experiment = adwin_baseline.load_experiment(CONFIGS / "adwin_dev.yaml")
    return replace(
        experiment,
        grid=grid,
        streams=tuple(
            (path, replace(template, split="final_evaluation"))
            for path, template in experiment.streams
        ),
    )


def _replay_frozen(config, factory, *, config_path, grid, split):
    if config.split != "final_evaluation" or config.seed not in grid["seeds"]:
        raise ValueError(f"stream outside the frozen {split} grid")
    if config.drift_type != "none" and (
        config.drift_start not in grid["onsets"]
        or config.post_mean not in grid["shifts"]
        or (
            config.drift_type in static_baseline.RAMP_TYPES
            and config.drift_duration not in grid["durations"]
        )
    ):
        raise ValueError(f"scenario outside the frozen {split} grid")
    run = _replay_synthetic(config, factory, config_path=config_path)
    return replace(run, provenance=replace(run.provenance, split=split))


def run_synthetic(output, *, arms, grid, split, cases=None):
    experiment = frozen_experiment(grid)
    results, timing, full_windows, rows_by_arm = {}, {}, {}, {}

    def replay_stream(config, factory, *, config_path):
        return _replay_frozen(
            config, factory, config_path=config_path, grid=grid, split=split
        )

    expected = len(grid["seeds"]) * 50
    for arm in frozen_arms(arms):
        results[arm.name], timing[arm.name], _ = _run_arm(
            arm,
            experiment,
            output,
            full_windows,
            replay_stream=replay_stream,
            inspect_run=cases.synthetic if cases else None,
        )
        metrics = results[arm.name]["anomaly"]
        if (
            metrics["stream_count"] != expected
            or metrics["pooled"]["scored_count"] != 3840 * expected
        ):
            raise ValueError(f"synthetic counts do not reconcile for {arm.name}")
        rows_by_arm[arm.name] = json.loads(
            (output / f"{arm.name}_streams.json").read_text()
        )
        print(f"{split}: completed {arm.name} on {expected} streams.", flush=True)
    static_baseline.write_json(output / "comparison.json", results)
    static_baseline.write_json(output / "runtime.json", timing)
    paired = synthetic_contrasts(rows_by_arm)
    static_baseline.write_json(output / "paired_statistics.json", paired)
    return paired


def execution_revision():
    """Fingerprint exact source, detector/data configs, and lock inputs."""
    paths = sorted(
        [
            *Path("src/drift_anomaly").rglob("*.py"),
            *CONFIGS.glob("*.yaml"),
            *Path("configs/synthetic").glob("*.yaml"),
            MANIFEST,
            Path("uv.lock"),
            Path("pyproject.toml"),
        ]
    )
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def run_manifest():
    return {
        "git_commit": _git_commit(),
        "execution_tree_sha256": execution_revision(),
        "executed_at_utc": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "logical_cpus": os.cpu_count(),
        "dependencies": {
            name: version(name)
            for name in (
                "drift-anomaly",
                "numpy",
                "scipy",
                "scikit-learn",
                "river",
                "PyYAML",
            )
        },
        "thread_settings": {
            name: os.environ.get(name)
            for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS")
        },
    }


def run_pre_final(output, aligned):

    with static_baseline.staged_output(output) as staged:
        cases = FailureCases()
        dataset = nab.load_config(MANIFEST)
        names = dataset["development"]
        nab.fetch_split(dataset, RAW_NAB / dataset["revision"], "development")
        nab_run = run_nab(
            map(load_development_series, names), frozen_arms(NAB_ARMS), cases
        )
        static_baseline.write_json(staged / "nab_development.json", nab_run)
        print(
            f"NAB development: completed {len(names)} series × {len(NAB_ARMS)} arms.",
            flush=True,
        )
        robust = staged / "robustness"
        robust.mkdir()
        run_synthetic(
            robust,
            arms=ROBUSTNESS_ARMS,
            grid=ROBUSTNESS_GRID,
            split="non_aligned_robustness",
            cases=cases,
        )
        aligned_rows = {}
        for arm in ROBUSTNESS_ARMS:
            rows = json.loads((aligned / f"{arm}_streams.json").read_text())
            if len(rows) != 500 or {row["seed"] for row in rows} != set(range(10)):
                raise ValueError(
                    "aligned reference must contain the 500 development streams"
                )
            aligned_rows[arm] = rows
        static_baseline.write_json(
            staged / "aligned_paired_statistics.json", synthetic_contrasts(aligned_rows)
        )
        cases.publish(staged)
        static_baseline.write_json(
            staged / "manifest.json",
            {
                **run_manifest(),
                "robustness_grid": ROBUSTNESS_GRID,
                "robustness_arms": ROBUSTNESS_ARMS,
                "nab_arms": NAB_ARMS,
                "nab_series": list(names),
                "nab_manifest": str(MANIFEST),
                "aligned_reference": json.loads(
                    (aligned / "manifest.json").read_text()
                ),
                "peak_process_rss_kib": resource.getrusage(
                    resource.RUSAGE_SELF
                ).ru_maxrss,
            },
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--aligned-reference", required=True, type=Path)
    args = parser.parse_args()
    run_pre_final(args.output, args.aligned_reference)


if __name__ == "__main__":
    main()
