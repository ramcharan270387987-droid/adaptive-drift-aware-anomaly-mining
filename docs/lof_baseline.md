# Development Baseline — Static LOF

These results are development-stage baseline observations and not final holdout evaluation.

## Detector and replay

Local Outlier Factor (LOF) measures local density. An observation scores as more anomalous when its estimated density is low relative to the densities of its nearest reference neighbors. Fit one univariate scikit-learn `LocalOutlierFactor` model per stream in novelty mode using only its first 256 observations. Replay scores incoming observations as unseen queries before calling a no-op update. The fitted reference stays fixed. Truth labels and drift metadata are available only to the evaluator.

| Parameter | Fixed development value |
| --- | --- |
| Warm-up | 256 observations per stream |
| `n_neighbors` | 20, validated to be below the warm-up length |
| `novelty` | `true` |
| `contamination` | `auto` |
| `metric` | Euclidean |
| Search | KD-tree, one worker |
| Score | `-score_samples(x)`, with larger values indicating more anomalous points |
| Decision | `score > -offset_`, equivalent to `decision_function(x) < 0` |

The default offset is −1.5, giving a strict threshold of 1.5. The adapter uses the fitted KD-tree and scikit-learn's local reachability-density calculation directly for efficient scalar queries. It applies the score orientation once. Tests match its scores and decisions against the public novelty API on the pinned scikit-learn version, including ties and a numeric contamination setting. The fast path relies on fitted internals of that version.

## Reproduce the run

From the repository root in the locked environment:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python \
  -m drift_anomaly.experiments.lof_baseline \
  --config configs/experiments/lof_dev.yaml \
  --output results/lof-development \
  --scored-csv
```

Use a new directory under ignored `results/`. The command writes the manifest, per-stream metrics, aggregate metrics, runtime metadata, and the optional scored CSV. The manifest records the Git revision, split, dependency versions, detector configuration and exact decision rule, warm-up, templates, and seed grid. The per-stream JSON records the effective synthetic parameters for each replay.

The LOF run uses the same 500 streams as Z-score and Isolation Forest. It covers 250 clean/injected pairs across stationary, sudden, gradual, incremental, and recurring scenarios using development seeds 0–9. Config validation rejects held-out synthetic configurations, reserved seeds, and NAB input before replay.

## Observed LOF metrics

Rows pool observations within each group. PR-AUC is average precision. Ratios are displayed to six decimal places. Clean streams have no positive ground-truth labels, so recall and PR-AUC are undefined. The JSON records reasons for unavailable metrics.

| Drift | Variant | Streams | Scored | Anomalies | TP | FP | TN | FN | Precision | Recall | F1 | FPR | PR-AUC |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Stationary | Clean | 10 | 38,400 | 0 | 0 | 1,646 | 36,754 | 0 | 0.000000 | — | 0.000000 | 0.042865 | — |
| Stationary | Injected | 10 | 38,400 | 120 | 120 | 1,641 | 36,639 | 0 | 0.068143 | 1.000000 | 0.127592 | 0.042868 | 0.980517 |
| Sudden | Clean | 40 | 153,600 | 0 | 0 | 56,873 | 96,727 | 0 | 0.000000 | — | 0.000000 | 0.370267 | — |
| Sudden | Injected | 40 | 153,600 | 480 | 468 | 56,682 | 96,438 | 12 | 0.008189 | 0.975000 | 0.016242 | 0.370180 | 0.623912 |
| Gradual | Clean | 80 | 307,200 | 0 | 0 | 109,962 | 197,238 | 0 | 0.000000 | — | 0.000000 | 0.357949 | — |
| Gradual | Injected | 80 | 307,200 | 960 | 930 | 109,672 | 196,568 | 30 | 0.008409 | 0.968750 | 0.016672 | 0.358124 | 0.631723 |
| Incremental | Clean | 80 | 307,200 | 0 | 0 | 108,879 | 198,321 | 0 | 0.000000 | — | 0.000000 | 0.354424 | — |
| Incremental | Injected | 80 | 307,200 | 960 | 931 | 108,598 | 197,642 | 29 | 0.008500 | 0.969792 | 0.016852 | 0.354617 | 0.637017 |
| Recurring | Clean | 40 | 153,600 | 0 | 0 | 46,755 | 106,845 | 0 | 0.000000 | — | 0.000000 | 0.304395 | — |
| Recurring | Injected | 40 | 153,600 | 480 | 467 | 46,580 | 106,540 | 13 | 0.009926 | 0.972917 | 0.019652 | 0.304206 | 0.618866 |
| All | Both | 500 | 1,920,000 | 3,000 | 2,916 | 647,288 | 1,269,712 | 84 | 0.004485 | 0.972000 | 0.008928 | 0.337657 | 0.574626 |

## Static baseline comparison

All three rows pool the same 1,920,000 scored observations across both variants. They describe the configured operating points on this development grid.

| Detector | Precision | Recall | F1 | FPR | PR-AUC | Total FP | Total FN |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Z-score | 0.008023 | 0.933667 | 0.015908 | 0.180669 | 0.586486 | 346,342 | 199 |
| Isolation Forest | 0.002726 | 0.994667 | 0.005436 | 0.569557 | 0.009244 | 1,091,841 | 16 |
| LOF | 0.004485 | 0.972000 | 0.008928 | 0.337657 | 0.574626 | 647,288 | 84 |

### False positives by phase

Counts pool both pair variants. The denominator is the number of nominal scored observations.

| Phase | Nominal | Z-score FP | Isolation Forest FP | LOF FP |
| --- | ---: | ---: | ---: | ---: |
| Stationary | 76,680 | 248 | 17,448 | 3,287 |
| Pre-drift | 613,650 | 1,848 | 136,476 | 25,298 |
| Transition | 61,280 | 7,256 | 31,284 | 15,761 |
| Post-drift | 1,165,390 | 336,990 | 906,633 | 602,942 |

The following LOF counts break out each drift family. Each cell gives false positives over nominal observations. The aggregate JSON also records the protocol window from transition onset through 256 samples after transition end, clipped at the next onset.

| Drift | Stationary | Pre-drift | Transition | Post-drift |
| --- | ---: | ---: | ---: | ---: |
| Stationary | 3,287 / 76,680 | — | — | — |
| Sudden | — | 4,220 / 102,286 | 38 / 80 | 109,297 / 204,354 |
| Gradual | — | 8,430 / 204,536 | 8,898 / 30,480 | 202,306 / 378,424 |
| Incremental | — | 8,430 / 204,536 | 6,741 / 30,480 | 202,306 / 378,424 |
| Recurring | — | 4,218 / 102,292 | 84 / 240 | 89,033 / 204,188 |

## Runtime

The initial run scored **1,920,000 observations** in **168.34 seconds** of summed replay time, or **11,405.5 scored observations per second**. This is the replay harness timer with one worker in Codex Cloud. It covers warm-up fit, source iteration, scoring, update hooks, and record collection. Stream generation, metric aggregation, CSV writing, and manifest creation are outside the timer. The runtime is a run-specific observation.

## Observed behavior and limits

Pooled LOF false-positive rates were 4.29% on stationary controls, 4.12% before drift, 25.72% in transition, and 51.74% after drift. In the shifted regime, many nominal points were flagged relative to the fixed local-density reference. Recall on injected anomalies was 100% on stationary streams and 96.88% to 97.50% across the four drift families.

The recurring post-drift phase includes both stable states. Its nominal false positives were **1,784 of 40,844** observations during returns to A and **87,249 of 163,344** during B. This accounts for the lower pooled recurring post-drift rate relative to the permanent shifts in this grid. Those counts describe the behavior of this fixed threshold and reference distribution.

The grid is univariate synthetic data. Its clean and injected pairs share underlying traces, and seeds recur across scenarios. The detectors use different decision rules, so the comparison describes their chosen operating points. These results supply no estimate for NAB, holdout performance, or final scalability.
