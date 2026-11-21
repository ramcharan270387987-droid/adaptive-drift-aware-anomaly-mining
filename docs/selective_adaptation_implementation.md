# Selective adaptation implementation

The frozen protocol defines the policy and later evaluation. This milestone implements the controller and verifies its mechanics on development streams. Comparative development metrics, sensitivity runs, and final evaluation are separate stages. [Frozen selective adaptation protocol](selective_adaptation_protocol.md)

## Online path

**ADWIN alarm → persistence checkpoints → filtering → refit → cooldown**

`SelectiveZScore` composes the existing Z-score model and ADWIN adapter. Replay gives the controller raw values only. It initializes both components with the same 256-observation prefix and keeps River's native ADWIN reset behavior. The controller scores with the current Z-score statistics and keeps the original decision. Replay records that prediction before calling the update hook. The hook feeds the current raw value to ADWIN, then processes any proposal or refit. Updated statistics first affect the next observation. [Controller source](../src/drift_anomaly/selective_adaptation.py)

An accepted alarm opens one proposal and snapshots the current mean and effective standard deviation. For the persistence modes, the alarm observation is excluded. Checkpoints at offsets 128, 192, and 256 use the medians of the last two adjacent 64-point raw blocks. The two shifts must point in the same direction and have magnitude at least 0.50 effective standard deviations. Candidate values come from the post-alarm interval through the current scored observation, up to 256 points. The filtering modes exclude originally flagged observations and require 128 survivors. The controller logs failed checks, closes unfitted proposals at the deadline, and never carries an overlapping proposal forward.

The full policy suppresses new proposals for the next 128 observations after a refit. ADWIN still processes every observation and every alarm remains visible. Accepted, duplicate, cooldown-suppressed, and budget-suppressed alarms are individually recorded. The budget permits at most 15 refits and 3,840 refit input uses per stream. Whole fits that exceed the remaining budget are blocked.

| Mode | Path |
| --- | --- |
| `immediate` | Refit at the alarm using the trailing 256 raw observations, including the current scored value |
| `persistence` | Wait for confirmation and fit the unfiltered post-alarm candidate |
| `filtering` | Confirm persistence, then apply the original-prediction filter |
| `full` | Confirm, filter, refit, and apply cooldown |

## Smoke checks

After running the implementation tests, use the locked environment from the repository root:

```bash
OPENBLAS_NUM_THREADS=1 .venv/bin/python \
  -m drift_anomaly.experiments.selective_smoke \
  --output results/selective-smoke
```

Use a new output directory under ignored `results/`. The command loads the checked-in ADWIN development configuration and replays only its five canonical template pairs, once in each mode. It does not expand the development grid. The shared loader rejects holdout templates, reserved seeds, and NAB configurations. [Smoke entry point](../src/drift_anomaly/experiments/selective_smoke.py)

The manifest records the revision, detector settings, and frozen constants. Per-stream diagnostics list every alarm disposition and the proposal it opened or joined. Each checkpoint includes its observation index, block medians, effective shifts, candidate and retained indices, rejection reasons, outcome, budget, and any before/after refit statistics. Offsets and cooldown bounds are zero-based replay positions. The export maps observed positions to source indices for alarms and candidates and retains the prospective cooldown bounds even beyond the stream end. Open proposals at stream end are marked incomplete. Refit records indicate whether the last observation triggered a terminal refit. The summary reports replay and event counts for reconciliation.

These diagnostics verify the implementation boundary. They do not estimate prediction quality or decide which candidate configuration to use in later evaluation.
