# Development Baseline — Static Z-score

These are development-stage baseline results and are not final holdout evaluation.

## Detector and replay

For each stream, independently estimate the mean and population standard deviation from its first **256** observations. Store both and keep them fixed. At each subsequent index, score the incoming observation before the detector's no-op update. The score is `abs(x - mean) / max(std, minimum_std)`. The inclusive anomaly threshold is **3.0**. The development YAML sets the standard deviation floor to **1e-12** for constant or nearly constant warm-up prefixes. Empty or non-finite warm-up input, non-finite observations, and unrepresentable scores fail explicitly. Warm-up rows are excluded from all metrics. The detector receives only raw values, and replay retains labels and drift metadata separately.

## Reproduce the run

From the repository root in the locked environment:

```bash
.venv/bin/python -m drift_anomaly.experiments.zscore_baseline \
  --config configs/experiments/zscore_dev.yaml \
  --output results/zscore-development \
  --plots
```

The output directory must be new and under ignored `results/`. The command writes `manifest.json`, `per_stream_metrics.json`, and `aggregate.json`. Use `--scored-csv` to export scored rows with the value, index, threshold, decision, truth, drift phase, and regime. The optional plots show the five canonical injected development presets with true anomalies, predicted anomalies, transition boundaries, and threshold lines. The manifest records Git SHA, dependency and project versions, detector parameters, stream templates, seed grid, and warm-up. Per-stream metrics record the effective generator parameters for each pair member.

The run crossed the complete development grid from seeds 0–9. It evaluated 250 clean traces and their 250 injected counterparts, each with 3,840 scored observations. The command validates the synthetic input type, development split and seed, and protocol parameter grid before any replay. Holdout streams and NAB are excluded.

## Observed development metrics

Each row pools the indicated streams. PR-AUC uses average precision over all ranked point scores in that row. Ratios are shown to six decimal places. Exact counts and unrounded metric values are in the output JSON.

| Drift | Variant | Streams | Scored | Anomalies | TP | FP | TN | FN | Precision | Recall | F1 | FPR | PR-AUC |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Stationary | Clean | 10 | 38,400 | 0 | 0 | 124 | 38,276 | 0 | 0 | — | 0 | 0.003229 | — |
| Stationary | Injected | 10 | 38,400 | 120 | 120 | 124 | 38,156 | 0 | 0.491803 | 1.000000 | 0.659341 | 0.003239 | 0.996902 |
| Sudden | Clean | 40 | 153,600 | 0 | 0 | 30,839 | 122,761 | 0 | 0 | — | 0 | 0.200775 | — |
| Sudden | Injected | 40 | 153,600 | 480 | 446 | 30,729 | 122,391 | 34 | 0.014306 | 0.929167 | 0.028179 | 0.200686 | 0.617619 |
| Gradual | Clean | 80 | 307,200 | 0 | 0 | 59,423 | 247,777 | 0 | 0 | — | 0 | 0.193434 | — |
| Gradual | Injected | 80 | 307,200 | 960 | 893 | 59,270 | 246,970 | 67 | 0.014843 | 0.930208 | 0.029220 | 0.193541 | 0.635346 |
| Incremental | Clean | 80 | 307,200 | 0 | 0 | 58,337 | 248,863 | 0 | 0 | — | 0 | 0.189899 | — |
| Incremental | Injected | 80 | 307,200 | 960 | 900 | 58,194 | 248,046 | 60 | 0.015230 | 0.937500 | 0.029973 | 0.190027 | 0.641659 |
| Recurring | Clean | 40 | 153,600 | 0 | 0 | 24,700 | 128,900 | 0 | 0 | — | 0 | 0.160807 | — |
| Recurring | Injected | 40 | 153,600 | 480 | 442 | 24,602 | 128,518 | 38 | 0.017649 | 0.920833 | 0.034634 | 0.160671 | 0.626187 |
| All | Both | 500 | 1,920,000 | 3,000 | 2,801 | 346,342 | 1,570,658 | 199 | 0.008023 | 0.933667 | 0.015908 | 0.180669 | 0.586486 |

An unavailable metric is shown as — and exported as JSON null with a reason. Recall requires a true anomaly. Precision requires a predicted anomaly. F1 is unavailable when there are neither true nor predicted anomalies, and is zero when its denominator is positive but TP is zero. FPR requires nominal observations. Average precision requires both truth classes and a finite score for every scored point. In the pooled clean rows precision and F1 are zero because the detector emitted false alarms.

## False positives by drift phase

These totals pool the clean and injected variants. Each denominator counts scored nominal observations in the corresponding phase. The per-stream and aggregate JSON also separate the variants and report the protocol's transition-plus-256-point diagnostic, clipped at the next onset. For recurring drift, the post-drift phase includes the return to A as indicated by the generator's active regime.

| Drift | Stationary FP/nominal | Pre-drift FP/nominal | Transition FP/nominal | Post-drift FP/nominal |
| --- | ---: | ---: | ---: | ---: |
| Stationary | 248/76,680 | — | — | — |
| Sudden | — | 308/102,286 | 24/80 | 61,236/204,354 |
| Gradual | — | 616/204,536 | 4,672/30,480 | 113,405/378,424 |
| Incremental | — | 616/204,536 | 2,510/30,480 | 113,405/378,424 |
| Recurring | — | 308/102,292 | 50/240 | 48,944/204,188 |
| All | 248/76,680 | 1,848/613,650 | 7,256/61,280 | 336,990/1,165,390 |

These counts describe how this fixed detector behaved under the selected Gaussian shifts. The pair members share their underlying trace, the grid reuses seeds, and the metrics are descriptive pooled point estimates. The phase durations and drift families have unequal numbers of observations. There is no comparative claim about selective adaptation and no real-world or held-out performance estimate.
