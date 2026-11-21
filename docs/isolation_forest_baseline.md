# Development Baseline — Static Isolation Forest

These are development-stage baseline results and are not final holdout evaluation.

## Detector and replay

Fit one scikit-learn Isolation Forest per stream from its first **256** observations using a single feature. The fit sees only raw warm-up values. It receives no anomaly labels or drift metadata. After warm-up, replay scores each observation before calling the detector's no-op update. The forest and its threshold remain fixed.

| Configuration | Development value |
| --- | --- |
| `random_state` | 42 |
| `n_estimators` | 100 |
| `contamination` | `auto` |
| `max_samples` | 256 |
| `threshold` | `null`, which uses the fitted scikit-learn offset with its sign reversed |
| Effective decision | Flag when `-score_samples(x) > 0.5` with the development config |
| Workers | 1 |

The score is `-score_samples(x)`, so larger values indicate shorter isolation paths. A numeric threshold in the YAML overrides the default decision boundary. A numeric contamination value is also supported and determines the offset from the warm-up fit when the threshold is null. The development parameters were fixed before results were inspected.

For efficient pointwise inference, fit compiles the forest's constant-score intervals from the univariate tree splits. Each score is a lookup using only the incoming value and the fitted intervals. The interval boundaries follow scikit-learn's float32 input conversion and split rule. Tests compare scores and decisions directly with scikit-learn, including both sides of split boundaries.

## Reproduce the development comparison

From the repository root with the locked environment installed:

```bash
.venv/bin/python -m drift_anomaly.experiments.isolation_forest_baseline \
  --config configs/experiments/isolation_forest_dev.yaml \
  --output results/isolation-forest-development \
  --scored-csv

.venv/bin/python -m drift_anomaly.experiments.zscore_baseline \
  --config configs/experiments/zscore_dev.yaml \
  --output results/zscore-development
```

Use new output directories under Git-ignored `results/`. Both commands use the same grid, stream templates, pairing, replay, and metrics. Manifest JSON captures the Git SHA, dependency versions, detector configuration, warm-up length, templates, and seed grid. The per-stream JSON records the effective seed and stream configuration, confusion counts, metrics, and phase diagnostics. The optional CSV records each scored observation's identifier, index, value, anomaly truth, drift phase, regime, score, decision, and effective threshold.

The complete grid uses seeds 0–9 and covers stationary, sudden, gradual, incremental, and recurring streams with their configured onsets, shifts, and durations. Each detector scores **500 streams** consisting of **250 clean and injected pairs**, with **1,920,000 scored observations** in total. Config validation rejects the reserved synthetic split, reserved seeds, and NAB inputs before replay.

## Observed Isolation Forest metrics

Rows pool point-level counts and ranks within each group. PR-AUC is average precision. Values are shown to six decimal places. Exact results are in the JSON exports. An em dash denotes an undefined metric. Clean streams have no true anomalies, so recall and PR-AUC are undefined.

| Drift | Variant | Streams | Scored | Anomalies | TP | FP | TN | FN | Precision | Recall | F1 | FPR | PR-AUC |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Stationary | Clean | 10 | 38,400 | 0 | 0 | 8,735 | 29,665 | 0 | 0.000000 | — | 0.000000 | 0.227474 | — |
| Stationary | Injected | 10 | 38,400 | 120 | 120 | 8,713 | 29,567 | 0 | 0.013585 | 1.000000 | 0.026807 | 0.227612 | 0.374882 |
| Sudden | Clean | 40 | 153,600 | 0 | 0 | 93,118 | 60,482 | 0 | 0.000000 | — | 0.000000 | 0.606237 | — |
| Sudden | Injected | 40 | 153,600 | 480 | 478 | 92,817 | 60,303 | 2 | 0.005124 | 0.995833 | 0.010195 | 0.606172 | 0.016676 |
| Gradual | Clean | 80 | 307,200 | 0 | 0 | 181,796 | 125,404 | 0 | 0.000000 | — | 0.000000 | 0.591784 | — |
| Gradual | Injected | 80 | 307,200 | 960 | 954 | 181,282 | 124,958 | 6 | 0.005235 | 0.993750 | 0.010415 | 0.591961 | 0.017069 |
| Incremental | Clean | 80 | 307,200 | 0 | 0 | 181,716 | 125,484 | 0 | 0.000000 | — | 0.000000 | 0.591523 | — |
| Incremental | Injected | 80 | 307,200 | 960 | 955 | 181,208 | 125,032 | 5 | 0.005243 | 0.994792 | 0.010430 | 0.591719 | 0.017562 |
| Recurring | Clean | 40 | 153,600 | 0 | 0 | 81,380 | 72,220 | 0 | 0.000000 | — | 0.000000 | 0.529818 | — |
| Recurring | Injected | 40 | 153,600 | 480 | 477 | 81,076 | 72,044 | 3 | 0.005849 | 0.993750 | 0.011629 | 0.529493 | 0.019839 |
| All | Both | 500 | 1,920,000 | 3,000 | 2,984 | 1,091,841 | 825,159 | 16 | 0.002726 | 0.994667 | 0.005436 | 0.569557 | 0.009244 |

## Side-by-side development comparison

Each of the first five rows pools injected streams of a single drift type. The last row pools both variants across the complete grid.

| Drift | Z-score precision | IF precision | Z-score recall | IF recall | Z-score F1 | IF F1 | Z-score FPR | IF FPR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Stationary | 0.491803 | 0.013585 | 1.000000 | 1.000000 | 0.659341 | 0.026807 | 0.003239 | 0.227612 |
| Sudden | 0.014306 | 0.005124 | 0.929167 | 0.995833 | 0.028179 | 0.010195 | 0.200686 | 0.606172 |
| Gradual | 0.014843 | 0.005235 | 0.930208 | 0.993750 | 0.029220 | 0.010415 | 0.193541 | 0.591961 |
| Incremental | 0.015230 | 0.005243 | 0.937500 | 0.994792 | 0.029973 | 0.010430 | 0.190027 | 0.591719 |
| Recurring | 0.017649 | 0.005849 | 0.920833 | 0.993750 | 0.034634 | 0.011629 | 0.160671 | 0.529493 |
| All, both variants | 0.008023 | 0.002726 | 0.933667 | 0.994667 | 0.015908 | 0.005436 | 0.180669 | 0.569557 |

## False positives by drift phase

Both variants are included. Each cell gives Z-score FP, then Isolation Forest FP, then the shared nominal denominator. Recurrence assigns the return to A to the post-drift phase. The JSON also retains the protocol's transition-plus-256-observation diagnostic, clipped at the next onset.

| Drift | Stationary Z / IF / nominal | Pre-drift Z / IF / nominal | Transition Z / IF / nominal | Post-drift Z / IF / nominal |
| --- | ---: | ---: | ---: | ---: |
| Stationary | 248 / 17,448 / 76,680 | — | — | — |
| Sudden | — | 308 / 22,766 / 102,286 | 24 / 62 / 80 | 61,236 / 163,107 / 204,354 |
| Gradual | — | 616 / 45,480 / 204,536 | 4,672 / 15,620 / 30,480 | 113,405 / 301,978 / 378,424 |
| Incremental | — | 616 / 45,480 / 204,536 | 2,510 / 15,466 / 30,480 | 113,405 / 301,978 / 378,424 |
| Recurring | — | 308 / 22,750 / 102,292 | 50 / 136 / 240 | 48,944 / 139,570 / 204,188 |
| All | 248 / 17,448 / 76,680 | 1,848 / 136,476 / 613,650 | 7,256 / 31,284 / 61,280 | 336,990 / 906,633 / 1,165,390 |

## Interpretation limits

The shared grid contains univariate synthetic Gaussian streams with a fixed injection design. Pair members share their underlying traces, seeds recur across scenarios, and the pooled metrics weight observations in longer phases more heavily. The two detectors use different fixed decision rules. On either tail, Isolation Forest gives all values beyond its outermost split the same score. A persistent shift and isolated injections can therefore receive tied scores. These point estimates describe the observed development behavior under this setup. The run provides no estimate of performance on NAB or holdout data. No thresholds were tuned in this comparison.
