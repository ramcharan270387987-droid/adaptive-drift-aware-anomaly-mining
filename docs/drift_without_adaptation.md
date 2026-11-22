# Control Experiment — Drift Detection Without Adaptation

These are development-stage control results, not final evaluation.

This experiment isolates the effect of observing drift from the effect of adapting an anomaly model. It pairs the existing static Z-score detector with ADWIN and, in a separate replay, Page-Hinkley. Anomaly and drift state are held in separate components. The same 256 raw warm-up observations initialize both components, and the Z-score population mean and standard deviation stay fixed afterward. On each scored observation, replay records the anomaly score and prediction before passing the current raw value to the drift update hook. An alarm is recorded at that observation's index. No Z-score update hook is called and neither detector sees evaluation labels.

> Drift alarms alone should not alter anomaly predictions when the anomaly detector remains frozen.

## Run and verify

The controls use the existing Z-score, ADWIN, and Page-Hinkley YAMLs. They retain the Z-score threshold of 3.0, ADWIN's delta of 0.002 and clock of 32, and Page-Hinkley's threshold of 50.0, min-instances of 30, delta of 0.005, alpha of 0.9999, and two-sided mode. The manifest records the full configurations. The run checks the reference manifests for the same detector parameters, development grid, and warm-up. Each control uses the same 250 clean/injected pairs across stationary, sudden, gradual, incremental, and recurring streams with seeds 0–9.

Provide the three baseline result directories. The static Z-score reference must have been run with `--scored-csv`. The drift references use their standard exports. The run reported here regenerated the scored CSV from the original Z-score commit and reproduced the saved anomaly metric JSON byte for byte. It used the saved committed ADWIN and Page-Hinkley runs.

```bash
OPENBLAS_NUM_THREADS=1 .venv/bin/python \
  -m drift_anomaly.experiments.drift_control \
  --zscore-results results/zscore-reference \
  --adwin-results results/adwin-reference \
  --page-hinkley-results results/page-hinkley-reference \
  --output results/drift-control
```

Use a new output directory under ignored `results/`. The control checks each scored CSV field against the static reference, including the exact score and prediction representation and the observation's identity and truth. It independently recomputes anomaly metrics for both controls. It checks each drift alarm index, match, delay, false-alarm index, and paired diagnostic against the respective drift-only run. Drift matching retains the existing one-to-one window through 128 samples after transition end, clipped at the next onset. Any discrepancy stops the run before results are published.

The exports are `control_report.json`, `per_stream_checks.json`, and `manifest.json`. The manifest records the code revision, selected configurations, dependency versions, reference revisions, and SHA-256 digests of reference artifacts. The per-stream file retains the count of exactly verified rows and both sets of drift diagnostics.

## Observed development results

Each control processed **500 streams** and verified **1,920,000 scored rows** against static Z-score. All scores and decisions matched exactly, and both independently computed anomaly metric summaries reproduced the static reference.

| Anomaly metric | Static Z-score and each control |
| --- | ---: |
| True positives | 2,801 |
| False positives | 346,342 |
| True negatives | 1,570,658 |
| False negatives | 199 |
| Precision | 0.008023 |
| Recall | 0.933667 |
| F1 | 0.015908 |
| False-positive rate | 0.180669 |
| PR-AUC, average precision | 0.586486 |

Ratios are shown to six decimal places. Exact values, family and pair-variant breakdowns, and undefined-metric reasons are in the JSON. Clean streams have no positive truth labels, so their recall and PR-AUC are undefined.

| Control | Matched / true transitions | Misses | Mean delay | Median delay | False alarms |
| --- | ---: | ---: | ---: | ---: | ---: |
| Static Z-score | — | — | — | — | — |
| Z-score + ADWIN | 640 / 640 | 0 | 66.7 | 63 | 142 |
| Z-score + Page-Hinkley | 640 / 640 | 0 | 46.59 | 36.5 | 1,066 |

Delay is measured in observations from transition onset. Drift diagnostics and paired alarm summaries matched the drift-only references exactly. ADWIN counted 70 false alarms on clean streams and 72 on injected streams. Page-Hinkley counted 493 clean and 573 injected false alarms.

The control establishes output invariance for these fixed detectors on this synthetic development grid. It provides no evidence about adaptation performance, holdout evaluation, or NAB performance.
