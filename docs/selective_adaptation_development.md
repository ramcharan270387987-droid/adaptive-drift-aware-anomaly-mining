# Selective adaptation ablations on synthetic development streams

Development-stage results only — not final holdout evaluation.

The comparison used the frozen [selective adaptation protocol](selective_adaptation_protocol.md) on 250 clean/injected pairs across stationary, sudden, gradual, incremental, and recurring streams. Each arm used 500 fresh replays with seeds 0–9, a 256-observation warm-up, and 1,920,000 scored observations (3,000 injected anomalies). All four ablations used the same raw-value ADWIN configuration. Persistence-based ablations used the primary cutoff of 0.50 effective standard deviations and checkpoints at 128, 192, and 256. Filtering used only the current model's predictions and required 128 retained points. The full policy added a 128-point cooldown. Every stream had a budget of 15 refits and 3,840 refit-input uses.

## Prediction quality

Both drift-without-adaptation controls exactly reproduced the static Z-score anomaly metrics. PR-AUC is average precision with both truth classes present. The JSON summaries report unavailable metrics and their reasons, including for clean streams without positives.

| Arm | TP | FP | TN | FN | Precision | Recall | F1 | FPR | PR-AUC |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Static Z-score / either frozen drift control | 2,801 | 346,342 | 1,570,658 | 199 | 0.0080 | 0.9337 | 0.0159 | 0.1807 | 0.5865 |
| Fixed schedule | 2,901 | 38,424 | 1,878,576 | 99 | 0.0702 | 0.9670 | 0.1309 | 0.0200 | 0.7605 |
| Immediate ADWIN refit | 2,696 | 45,582 | 1,871,418 | 304 | 0.0558 | 0.8987 | 0.1052 | 0.0238 | 0.7440 |
| ADWIN + persistence | 2,884 | 28,314 | 1,888,686 | 116 | 0.0924 | 0.9613 | 0.1687 | 0.0148 | 0.7438 |
| ADWIN + persistence + filtering | 2,871 | 182,209 | 1,734,791 | 129 | 0.0155 | 0.9570 | 0.0305 | 0.0950 | 0.6142 |
| Full policy with cooldown | 2,870 | 182,638 | 1,734,362 | 130 | 0.0155 | 0.9567 | 0.0304 | 0.0953 | 0.6138 |

| Arm | Stationary FP | Pre-drift FP | Transition FP | Post-drift FP | Event-window FP | FP on full-policy matched windows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Static / either frozen drift control | 248 | 1,848 | 7,256 | 336,990 | 49,949 | 25,485 |
| Fixed schedule | 180 | 1,382 | 6,700 | 30,162 | 34,607 | 651 |
| Immediate | 248 | 1,848 | 3,091 | 40,395 | 10,841 | 3,032 |
| Persistence | 248 | 1,848 | 6,207 | 20,011 | 23,921 | 324 |
| Filtering | 248 | 1,848 | 7,273 | 172,840 | 43,162 | 4,317 |
| Full policy | 248 | 1,848 | 7,273 | 173,269 | 43,162 | 4,320 |
| Nominal observations | 76,680 | 613,650 | 61,280 | 1,165,390 | 224,680 | 122,608 |

The event window runs from transition onset through transition end plus 256 observations, clipped before the next onset. The shared post-adaptation windows start after each of the full policy's 481 matched refits and end at 256 observations, the next refit, the next true onset, or stream end, using the protocol's clipping rules. This conditional comparison covers 390 streams and omits events without a matched full-policy refit. On their *own* matched windows, immediate, persistence, filtering, full, and fixed scheduling logged 7,689/154,427, 418/159,247, 4,317/122,540, 4,320/122,608, and 312/163,004 false positives per nominal observation count, respectively. Their unmatched-refit windows recorded 89/36,311, 33/18,167, 31/3,327, 18/1,279, and 3,173/1,456,792, respectively.

Persistence alone had the lowest post-drift FP and highest recall and F1 among the four ablations. Compared with fixed scheduling, it recorded 10,151 fewer post-drift false positives (1.72% vs 2.59%) and used 711 rather than 7,500 refits. It missed 17 more anomalies across the full grid and had lower average precision. Immediate refitting had the fewest event-window false positives, with 304 anomaly misses. The full policy reduced post-drift false positives relative to static Z-score (14.87% vs 28.92%) and used the fewest refits, but had 143,107 more post-drift false positives and 31 more anomaly misses than fixed scheduling. The full policy at 0.50 remains the protocol's primary configuration.

## Alarm attribution and update cost

Post-hoc matching gives each of the 640 evaluated transitions its earliest eligible refit, with at most one match per transition and per refit. An ADWIN refit's opening alarm must be within onset through transition end plus 128, with the refit through transition end plus 384. The same refit window applies to scheduled refits. Both windows are clipped before the next onset. All 640 events were outside warm-up. Every selective arm received the same 782 ADWIN alarms (640 matched alarms and 142 false alarms). Page-Hinkley had 1,706 alarms in its frozen control, with 640 matched and 1,066 false.

| Arm | Proposals | Rejected | Suppressed / duplicate alarms | Refits | Matched / missed events | Unmatched refits | Median onset / alarm delay (points) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Immediate | 782 | 0 | 0 / 0 | 782 | 640 / 0 | 142 | 63 / 0 |
| Persistence | 763 | 52 | 0 / 19 | 711 | 640 / 0 | 71 | 191 / 128 |
| Filtering | 673 | 179 | 0 / 109 | 494 | 481 / 159 | 13 | 287 / 192 |
| Full policy | 658 | 172 | 15 / 109 | 486 | 481 / 159 | 5 | 287 / 192 |
| Fixed schedule | — | — | — | 7,500 | 640 / 0 | 6,860 | 255 / — |

No primary proposals were incomplete and no alarms were suppressed by the budget. The full policy matched 50/80 sudden, 134/160 gradual, 149/160 incremental, and 148/240 recurring transitions. Its mean matched onset-to-refit delay was 282.1 observations (range 223–415). All 640 matched fixed-schedule refits had a 255-observation delay. Unmatched refits measure alignment with this matching policy. They may still affect predictions.

| Arm | Refit inputs used | Mean inputs/refit | Refits/stream | Streams updated | Replay seconds | Scored obs/s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Static Z-score | 0 | — | 0 | 0% | 27.5 | 69,836 |
| Z-score + frozen ADWIN | 0 | — | 0 | 0% | 27.6 | 69,554 |
| Z-score + frozen Page-Hinkley | 0 | — | 0 | 0% | 29.1 | 65,923 |
| Fixed schedule | 1,920,000 | 256.0 | 15.000 | 100% | 31.5 | 60,982 |
| Immediate | 200,192 | 256.0 | 1.564 | 96% | 33.6 | 57,099 |
| Persistence | 92,416 | 130.0 | 1.422 | 96% | 30.6 | 62,709 |
| Filtering | 81,931 | 165.9 | 0.988 | 78% | 31.3 | 61,383 |
| Full policy | 80,379 | 165.4 | 0.972 | 78% | 29.2 | 65,831 |

Input uses count repeated inputs if any. Fixed scheduling included 500 terminal refits; the full policy had none. Five full-policy streams had an unmatched refit (1.0% of all streams and 1.28% of updated streams). At the full policy's checkpoints, the filter excluded 958 labeled-anomaly considerations and 81,565 nominal considerations, then used 33 labeled anomaly inputs in actual fits. Its 282,816 candidate considerations included repeated consideration across checkpoints (144,384 unique stream/observation pairs). Persistence alone used 411 labeled anomaly inputs, and matched 159 more transitions. The comparison shows a trade-off from filtering on this grid, where the old model can flag shifted nominal values and leave too few retained points for a refit.

## Full-policy sensitivity

| Persistence cutoff | Recall (FN) | F1 | Post-drift FP | Event-window FP | Refits | Matched / missed | Unmatched | Refit inputs | Median onset delay | Replay seconds / obs per second |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.50 (primary) | 0.9567 (130) | 0.03045 | 173,269 | 43,162 | 486 | 481 / 159 | 5 | 80,379 | 287 | 29.2 / 65,831 |
| 0.75 | 0.9567 (130) | 0.03045 | 173,283 | 43,162 | 484 | 481 / 159 | 3 | 80,062 | 287 | 31.7 / 60,582 |
| 1.00 | 0.9567 (130) | 0.03044 | 173,304 | 43,178 | 484 | 481 / 159 | 3 | 80,273 | 287 | 30.8 / 62,368 |

The higher cutoffs reduced unmatched refits by two each while leaving pooled recall and matched coverage unchanged. Both produced slightly more post-drift false positives. The 0.50 cutoff stays frozen.

## Reproduction and limitations

Run from the repository root with the locked project environment.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python \
  -m drift_anomaly.experiments.selective_evaluation \
  --output results/selective_dev
```

The output directory must be new and under ignored `results/`. The manifest records the Git SHA, configuration, grid, Python/project/dependency versions, and machine and thread settings. The per-arm files record stream seeds, configuration, anomaly metrics, alarms, proposal decisions, filter indices, and refit matches. `comparison.json` includes pooled and family/injection summaries. `runtime.json` holds per-run timings and the evaluation process's peak resident memory. The timing table is from the initial grid replay on Linux with three logical CPUs (AMD EPYC 9V74) and Python 3.12.14. Its process peak was approximately 378 MiB. Replay timing includes warm-up, scoring and updates, and excludes generation, post-hoc scoring and export. It is a local measurement.

Synthetic streams share seeds within groups, and clean/injected streams are paired. Onsets align with the 256-point fixed schedule and initial ADWIN check cadence. Counts on full-policy post-refit windows describe a selected subset. These data do not establish behavior for arbitrary onset timing, other forms of distribution change, or production-scale throughput. The next step is to freeze the verified development revision for the prespecified evaluation and seek separate authorization before running the primary or robustness holdout.
