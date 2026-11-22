# Development Drift Baseline — ADWIN

These are development-stage drift-detection results and are not final holdout evaluation.

## Signal and replay

River ADWIN receives the **raw univariate value**. Its adaptive window tests for changes in the mean of this signal. The detector sees no ground-truth labels, anomaly scores, or future observations. This is a drift-only run and does not fit, score, or update any anomaly model.

| Setting | Development value |
| --- | --- |
| River | 0.27.0 |
| `delta` | 0.002 |
| `clock` | 32 |
| `max_buckets` | 5 |
| `min_window_length` | 5 |
| `grace_period` | 10 |
| Warm-up | First 256 observations, with alarms excluded from evaluation |
| First eligible alarm index | 256, zero-based |

Each stream gets a fresh detector. During warm-up the detector processes the prefix in source order. After warm-up, replay passes the current value to ADWIN, reads `drift_detected` after that update, records any alarm at the current index, and only then requests the next value. The anomaly score hook stays empty. River resets its window on the update following an alarm as part of its normal operation. These detector settings were fixed before evaluating the grid.

## Matching and reporting

Use the synthetic generator's ordered transitions for evaluation. For each eligible event, match the first alarm from onset through **128 samples after transition end**, inclusive. Clip this window at the sample before the next onset. Each event and alarm may match at most once. Recurring transitions count separately. Delay is the alarm index minus the onset, including for gradual and incremental changes. Events with onsets in warm-up are listed separately. The full development grid had none.

Each recorded alarm left unmatched counts as false under the protocol, including an extra alarm inside a window that has already matched. On stationary streams every alarm is false. Detection rate is matched events divided by true events. Mean and median delay use matched events only. Undefined rates or delays appear as JSON null with a reason.

## Reproduce the run

```bash
OPENBLAS_NUM_THREADS=1 .venv/bin/python \
  -m drift_anomaly.experiments.adwin_baseline \
  --config configs/experiments/adwin_dev.yaml \
  --output results/adwin-development \
  --plots
```

Use a new destination under ignored `results/`. The command exports a manifest with Git SHA, versions, signal, matching rules, detector settings, and grid. Per-stream JSON contains the effective config, seed, true event details, alarm indices, matches, delays, and false alarms. Paired JSON records the false-alarm differences and indices unique to each member. The aggregate JSON reports family, variant, and pooled summaries plus the matched delay distribution. The optional plots show the canonical clean and injected pair for each family on a common vertical scale.

## Observed development results

The run used the same **250 clean/injected pairs** as the static anomaly baselines, across development seeds 0–9. The 500 streams contributed **1,920,000** scored observations. Detection rate was **100% on each non-stationary group**. Stationary controls had zero events and zero false alarms across 20 streams and 76,800 scored observations.

| Drift | Variant | Matched / true | Misses | Mean delay | Median delay | False alarms |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Stationary | Clean | 0 / 0 | 0 | — | — | 0 |
| Stationary | Injected | 0 / 0 | 0 | — | — | 0 |
| Sudden | Clean | 40 / 40 | 0 | 31.0 | 31 | 0 |
| Sudden | Injected | 40 / 40 | 0 | 31.8 | 31 | 0 |
| Gradual | Clean | 80 / 80 | 0 | 102.2 | 95 | 34 |
| Gradual | Injected | 80 / 80 | 0 | 101.4 | 95 | 35 |
| Incremental | Clean | 80 / 80 | 0 | 103.4 | 95 | 36 |
| Incremental | Injected | 80 / 80 | 0 | 101.8 | 95 | 37 |
| Recurring | Clean | 120 / 120 | 0 | 31.0 | 31 | 0 |
| Recurring | Injected | 120 / 120 | 0 | 31.3 | 31 | 0 |
| All | Clean | 320 / 320 | 0 | 66.9 | 47 | 70 |
| All | Injected | 320 / 320 | 0 | 66.5 | 63 | 72 |
| All | Both | 640 / 640 | 0 | 66.7 | 63 | 142 |

Matched delays ranged from 31 to 223 observations. Abrupt and recurring changes had median delays of 31 observations, and gradual and incremental changes had median delays of 95. Pooled false alarms were **0.074 per 1,000 scored observations**, including extra alarms near matched changes. Of the 142 unmatched alarms, 110 were inside already-matched windows and 32 were outside all windows.

Injected streams produced two additional unmatched alarms on net. Of the 250 pairs, 10 injected members had more unmatched alarms, eight had fewer, and 232 had the same count. Both net increases occurred in gradual or incremental streams. The variant breakdown shows 59 clean and 51 injected extra alarms inside matched windows, and 11 clean and 21 injected alarms outside all windows. These differences describe paired traces. They do not identify any individual injected point as the cause of an alarm.

The grid uses synthetic Gaussian mean shifts and onset positions aligned to the detector's initial 32-sample check schedule. Repeated seeds and paired traces limit the independence of these observations. Detection rates depend on the matching window, which includes the duration of gradual and incremental transitions. The run does not estimate drift sensitivity on other signals, holdout streams, or NAB.
