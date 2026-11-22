# Development Drift Baseline — Page-Hinkley

`Development-stage results only; not final holdout evaluation.`

## Signal, configuration, and reset

River 0.27.0 Page-Hinkley uses a cumulative-sum test to detect sustained changes in the mean of the **raw univariate value**, the same input as ADWIN. The following fixed parameters are River's defaults and were selected before the development run.

| Setting | Value |
| --- | --- |
| `threshold` | 50.0 |
| `min_instances` | 30 |
| `delta` | 0.005 |
| `alpha` | 0.9999 |
| `mode` | `both`, for upward and downward changes |
| Warm-up | First 256 observations, excluded from scored alarms |
| First eligible alarm index | 256, zero-based |

Each stream starts with a fresh detector. Warm-up observations initialize its state. After warm-up, replay sends the current raw value to the update hook, reads `drift_detected` after the update, records the alarm at that observation's index, and then advances the source. The detector receives no anomaly labels, drift labels, or future observations.

River resets its running mean and cumulative sums **at the next update after an alarm**, then uses that next observation as the first sample of the new segment. The adapter adds no resets. The 30-observation minimum applies again to the restarted segment. This affects the available evidence for the next transition in recurring streams. The run does not fit, score, or update any anomaly model.

## Reproduce the comparison

From the repository root in the locked environment, reproduce the ADWIN reference and pass it to Page-Hinkley. The reported comparison used the saved ADWIN artifacts from commit `c33ae7f93d0fbd9c0f62d4fe1218f94a5cf16c0a`. The current shared runner reproduced its diagnostic JSON byte for byte.

```bash
OPENBLAS_NUM_THREADS=1 .venv/bin/python \
  -m drift_anomaly.experiments.adwin_baseline \
  --config configs/experiments/adwin_dev.yaml \
  --output results/adwin-reference

OPENBLAS_NUM_THREADS=1 .venv/bin/python \
  -m drift_anomaly.experiments.page_hinkley_baseline \
  --config configs/experiments/page_hinkley_dev.yaml \
  --adwin-results results/adwin-reference \
  --output results/page-hinkley-development \
  --plots
```

Use new destinations under ignored `results/`. The manifest records detector settings, the Git SHA, versions, grid, and matching policy. The per-stream, pair, aggregate, and comparison JSON files retain alarm indices, matches, delays, and false-alarm counts. The comparison verifies the reference signal, warm-up, stream definitions, and drift truth, then reconciles ADWIN's alarms through the same evaluator. Five optional plots overlay both detectors' alarms and true drift boundaries on the same canonical clean and injected traces.

## ADWIN vs Page-Hinkley

Both detectors processed the same **500 streams** in **250 clean/injected pairs**, with development seeds 0–9 and **1,920,000 scored observations** per detector. They use the same one-to-one match from onset through 128 samples after transition end, clipped before the next onset. Delay is measured in observations from onset and summarized across matched events only. Every unmatched alarm is counted as false.

| Drift | True transitions | ADWIN matched | Page-Hinkley matched | ADWIN median delay | Page-Hinkley median delay | ADWIN false alarms | Page-Hinkley false alarms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Stationary | 0 | 0 | 0 | — | — | 0 | 39 |
| Sudden | 80 | 80 | 80 | 31 | 14.5 | 0 | 136 |
| Gradual | 160 | 160 | 160 | 95 | 69.5 | 69 | 405 |
| Incremental | 160 | 160 | 160 | 95 | 73.5 | 73 | 386 |
| Recurring | 240 | 240 | 240 | 31 | 15 | 0 | 100 |
| **All** | **640** | **640** | **640** | **63** | **36.5** | **142** | **1,066** |

Both detectors matched 100% of true transitions in each non-stationary family and missed none under the protocol. Detection rate and delay are undefined for stationary controls. Page-Hinkley's mean delay was **46.59 observations**, versus **66.7** for ADWIN. Its matched delays ranged from 1 to 158 observations. Unmatched alarms occurred at **0.5552 per 1,000** scored observations for Page-Hinkley and **0.0740 per 1,000** for ADWIN. Of Page-Hinkley's 1,066 unmatched alarms, 267 were extra alarms inside already-matched windows and 799 were outside all windows.

Page-Hinkley matched abrupt changes sooner in this run. Gradual and incremental medians were longer than abrupt medians for both detectors. Page-Hinkley matched all recurring transitions, including returns to the previous mean, and emitted 100 false alarms in that family. ADWIN matched the same transitions with none. Page-Hinkley emitted 39 false alarms across 20 stationary streams and 76,800 observations, or 1.95 per stream.

### Paired anomaly injections

| Variant | Page-Hinkley matched / true | Page-Hinkley mean delay | Page-Hinkley median delay | Page-Hinkley false alarms | ADWIN false alarms |
| --- | ---: | ---: | ---: | ---: | ---: |
| Clean | 320 / 320 | 46.38 | 37 | 493 | 70 |
| Injected | 320 / 320 | 46.79 | 35.5 | 573 | 72 |

Page-Hinkley produced **80 additional false alarms on net** in the injected condition. Of 250 pairs, 89 injected members had more false alarms, 40 had fewer, and 121 had the same count. The net difference was three on stationary controls, 18 on sudden, 25 on gradual, 16 on incremental, and 18 on recurring streams. In the same paired comparison, ADWIN's net difference was two. Pair counts show sensitivity to the injection condition. They do not identify a specific injected point as the cause of an alarm.

## Interpretation limits

These results describe the selected fixed operating points on univariate Gaussian mean shifts. Matched-event rates depend on the matching window, which includes the duration of gradual and incremental events. ADWIN checks every 32 observations, while Page-Hinkley checks each update after its minimum sample count. Reused seeds and paired underlying traces limit the independence of the pooled observations. The results do not establish general detector superiority, holdout performance, or effects on anomaly-model adaptation.
