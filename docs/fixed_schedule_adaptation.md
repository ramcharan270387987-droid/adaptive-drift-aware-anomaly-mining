# Control Experiment — Fixed-Schedule Adaptation

These are development-stage control results, not final holdout evaluation.

## Schedule and causal ordering

The control tests periodic retraining independently of drift alarms. It reuses the static Z-score formula, threshold **3.0**, and standard-deviation floor **1e-12**. Fit the mean and population standard deviation on the first **256 observations** of each stream. Then refit those two statistics every **256 scored observations** using the most recent **256 raw observations**.

Replay records the current score and prediction before the current observation enters the refit buffer. The current observation can contribute to a refit at its index, and the replacement statistics first affect the next prediction. The first refit is at zero-based index **511**, then 767 and every 256 indices thereafter on the protocol streams. A refit scheduled on the last observation is still recorded. The interval and window are configurable, and the development runner enforces the protocol's 256-point warm-up. This schedule was fixed before the run.

The model receives only raw values. It includes every observation in the trailing window, including any injected anomaly. The evaluator looks up injection labels only after replay to annotate whether each refit window contained an anomaly. Diagnostics record the refit index, window bounds and size, before and after statistics, and any injected indices.

## Reproduce

From the repository root in the locked environment, use the verified drift-without-adaptation outputs as the reference and write to a new directory under ignored `results/`.

```bash
OPENBLAS_NUM_THREADS=1 .venv/bin/python \
  -m drift_anomaly.experiments.fixed_schedule_baseline \
  --config configs/experiments/fixed_schedule_dev.yaml \
  --control-results results/drift-control \
  --output results/fixed-schedule \
  --plots
```

The runner compares the reference grid, warm-up, stream parameters, scored counts, and Z-score settings. The comparison used control artifacts from commit `f9161c9a4951916edb2e4d0cf5f9319c9bcfad0c`. Results include a provenance manifest, per-stream metrics and refit diagnostics, aggregate metrics, and comparison JSON. Five optional plots show the canonical injected streams with true anomalies, detector predictions, drift intervals, refit indices, and the model mean used for scoring.

## Observed development results

The same **250 clean/injected pairs** with seeds 0–9 produced **500 streams** and **1,920,000 scored observations**. Both drift-without-adaptation variants reproduced the static anomaly outputs exactly. Ratios below are rounded to six decimals. PR-AUC is average precision.

| Method | TP | FP | TN | FN | Precision | Recall | F1 | FPR | PR-AUC | Refits |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Static Z-score | 2,801 | 346,342 | 1,570,658 | 199 | 0.008023 | 0.933667 | 0.015908 | 0.180669 | 0.586486 | 0 |
| Z-score + ADWIN, no adaptation | 2,801 | 346,342 | 1,570,658 | 199 | 0.008023 | 0.933667 | 0.015908 | 0.180669 | 0.586486 | 0 |
| Z-score + Page-Hinkley, no adaptation | 2,801 | 346,342 | 1,570,658 | 199 | 0.008023 | 0.933667 | 0.015908 | 0.180669 | 0.586486 | 0 |
| Fixed schedule | 2,901 | 38,424 | 1,878,576 | 99 | 0.070200 | 0.967000 | 0.130897 | 0.020044 | 0.760487 | 7,500 |

| Phase | Nominal observations | Static or no-adaptation FP | Fixed-schedule FP |
| --- | ---: | ---: | ---: |
| Stationary | 76,680 | 248 | 180 |
| Pre-drift | 613,650 | 1,848 | 1,382 |
| Transition | 61,280 | 7,256 | 6,700 |
| Post-drift | 1,165,390 | 336,990 | 30,162 |

The post-drift false-positive rate fell from **28.92% to 2.59%**. In the protocol's shorter window from transition onset through 256 samples after transition end, clipped before the next onset, false positives fell from **49,949 to 34,607** out of **224,680** nominal observations. That shorter-window rate remained **15.40%** under the fixed schedule.

Recall rose from **93.37% to 96.70%** overall, and false negatives fell from **199 to 99**. False negatives fell in each drift family. On stationary controls with injected anomalies, they rose from zero to one out of 120.

## Refits and limitations

Each stream logged **15 refits**, including one at the last observation. That is **7,500 scheduled refits**, of which **7,000** affected at least one later prediction. There were **300 refits** on stationary streams alone. **1,949** windows contained injected anomalies, all on injected streams. Of those, **129** were terminal refits. The aggregate recall comparison does not isolate the effect of contamination on individual predictions.

Periodic refitting can spend work on stable data and react late when a shift follows a scheduled fit. The configured synthetic onset positions align with the refit interval, and paired variants share traces. The observed rates are descriptive for this grid and schedule. The experiment does not estimate holdout or NAB performance or the effect of selective adaptation.
