# Final untouched evaluation

## Research question

Can explicit concept-drift detection and selective model adaptation reduce false anomaly alarms after distribution changes without reducing sensitivity to genuine anomalies?

## Experimental design and frozen methods

This report uses the first and only complete execution of the frozen final specification. Before launch, `work` was clean at `7e72ccb61297d58567fb1e41c077e6b537e9d897` and matched `origin/work`. The data-free manifest check passed, and the workspace contained no primary synthetic or final NAB evaluation outputs. The evaluator checked the pinned NAB source and labels before scoring. The execution manifest records the exact revision, execution timestamp, platform, dependency versions and configuration. The archived frozen specification can be retrieved from the execution commit. [Final evaluation receipt](../configs/final_evaluation.yaml)

The primary synthetic grid crossed seeds 1000–1019 with stationary, sudden, gradual, incremental and recurring scenarios. It used onsets 1536 and 2560, shifts of 1 and 2.25 standard deviations, ramp widths 192 and 384, and independent unit-Gaussian noise. There were 500 clean/injected pairs of 4,096 observations, 6,000 isolated point injections and 1,280 true transitions, including both members of each pair. Each arm scored 3,840,000 observations after a per-stream 256-point warm-up. Models scored each point before seeing it for an update.

The primary contrast is **full selective policy versus static Z-score**. Both use absolute Z-score threshold 3.0. The full policy uses raw-value ADWIN at delta 0.002, a persistence cutoff of 0.50 effective standard deviations at checkpoints 128, 192 and 256, prediction-based filtering, and a 128-point cooldown. The secondary candidate uses the same ADWIN and persistence rule at 0.50 with unfiltered refits and no cooldown. Fixed scheduling refits every 256 observations on a trailing window of 256. Comparators also include static Isolation Forest and LOF, immediate ADWIN refitting, persistence with filtering but no cooldown, and both frozen Z-score controls paired with drift observers. The NAB specification uses the six frozen methods listed in the NAB table.

NAB was evaluated on the five pinned final CSVs only. The loader retained timestamp ties in source order, applied the frozen rule for backward rows, and mapped point labels to the first retained row at a matching timestamp. It treated benchmark windows as a separate hit metric and counted only windows containing scored data. A window hit can occur without an exact-point detection. NAB supplies no independent drift truth, so alarm, proposal and refit counts and timestamps are descriptive. [Experimental protocol](experimental_protocol.md) · [Selective adaptation protocol](selective_adaptation_protocol.md) · [NAB dataset protocol](dataset_protocol.md)

## Primary synthetic holdout
| Method | TP / FP / TN / FN | Precision | Recall | F1 | FPR | PR-AUC | Post-drift FP | Event-window FPR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Static Z-score | 5,798 / 230,483 / 3,603,517 / 202 | 0.02454 | 0.96633 | 0.04786 | 0.06012 | 0.74797 | 216,554 | 0.0892 |
| Isolation Forest | 5,994 / 1,520,361 / 2,313,639 / 6 | 0.00393 | 0.99900 | 0.00782 | 0.39655 | 0.02128 | 1,056,891 | 0.5010 |
| LOF | 5,955 / 758,257 / 3,075,743 / 45 | 0.00779 | 0.99250 | 0.01546 | 0.19777 | 0.54945 | 633,944 | 0.2784 |
| Frozen Z-score + ADWIN | 5,798 / 230,483 / 3,603,517 / 202 | 0.02454 | 0.96633 | 0.04786 | 0.06012 | 0.74797 | 216,554 | 0.0892 |
| Frozen Z-score + Page-Hinkley | 5,798 / 230,483 / 3,603,517 / 202 | 0.02454 | 0.96633 | 0.04786 | 0.06012 | 0.74797 | 216,554 | 0.0892 |
| Fixed schedule | 5,877 / 34,556 / 3,799,444 / 123 | 0.14535 | 0.97950 | 0.25314 | 0.00901 | 0.90027 | 24,872 | 0.0518 |
| Immediate ADWIN | 5,711 / 34,855 / 3,799,145 / 289 | 0.14078 | 0.95183 | 0.24529 | 0.00909 | 0.87980 | 26,631 | 0.0206 |
| ADWIN + persistence | 5,863 / 28,394 / 3,805,606 / 137 | 0.17115 | 0.97717 | 0.29128 | 0.00741 | 0.89643 | 17,205 | 0.0398 |
| Persistence + filtering | 5,935 / 65,041 / 3,768,959 / 65 | 0.08362 | 0.98917 | 0.15420 | 0.01696 | 0.82901 | 52,262 | 0.0743 |
| Full selective policy | 5,926 / 69,547 / 3,764,453 / 74 | 0.07852 | 0.98767 | 0.14547 | 0.01814 | 0.82066 | 56,768 | 0.0745 |

Post-drift false positives and missed anomalies by family for the primary comparisons follow. The full per-stream files also include stationary controls, clean/injected metrics, alarm indices, and refit matches.

| Drift family | Static Z-score FP / FN | Fixed schedule FP / FN | ADWIN + persistence FP / FN | Full selective policy FP / FN |
| --- | --- | --- | --- | --- |
| Sudden | 41,602 / 40 | 5,347 / 25 | 3,706 / 25 | 10,032 / 19 |
| Gradual | 71,847 / 71 | 2,395 / 45 | 1,717 / 66 | 5,624 / 30 |
| Incremental | 71,847 / 59 | 2,840 / 24 | 2,500 / 20 | 12,709 / 4 |
| Recurring | 31,258 / 31 | 14,290 / 28 | 9,282 / 25 | 28,403 / 20 |

PR-AUC is average precision. A dash indicates an undefined metric. Overall FPR divides false positives by all nominal scored observations. Event-window FPR is restricted to the interval from transition onset through 256 observations after transition end, clipped before the next onset. The post-drift FP column covers all post-drift observations, which uses a wider time span than the event-window measure.

The full policy reduced post-drift false positives by 73.8% versus static Z-score and missed 74 of 6,000 isolated anomalies, compared with 202 for static Z-score. Persistence alone cut post-drift false positives further, to 17,205, while missing 137 anomalies. Compared with fixed scheduling, persistence had 7,667 fewer post-drift false positives and 14 more missed anomalies. The full policy had more than twice the post-drift false positives of fixed scheduling and 49 fewer missed anomalies. The two drift-only controls reproduced static Z-score's anomaly metrics exactly.

## Prespecified statistical comparisons

The sample unit is the seed. Each of the 20 seed blocks carries clean/injected pairs and every applicable nonstationary scenario. Event-window FPR uses 960 paired streams and recall uses the 480 paired injected streams. Differences subtract the comparator from the first method and average over eligible streams. The 95% percentile intervals use 10,000 seed-block bootstrap replicates and seed 1729. Two-sided Wilcoxon signed-rank tests use seed means with zero differences removed. Holm correction covers the ten prespecified tests. Rank-biserial correlation gives effect direction and relative signed ranks. Its sign follows the first method minus the comparator. Pooled rates and mean paired differences use different weights. NAB receives descriptive analysis because its five series and few labeled points do not provide an adequate basis for these tests.

| First method − comparator | Outcome | Seeds / streams | Paired Δ (pp) | 95% interval (pp) | Raw p | Holm p | Rank biserial |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ADWIN + persistence − Fixed schedule | Event FPR | 20 / 960 | -1.262 | [-1.649, -0.842] | 8.2016e-05 | 0.000492096 | -0.905 |
| ADWIN + persistence − Fixed schedule | Recall | 20 / 480 | -0.243 | [-0.868, +0.417] | 0.304723 | 0.304723 | -0.275 |
| Full selective policy − Fixed schedule | Event FPR | 20 / 960 | +1.888 | [+1.402, +2.407] | 1.90735e-06 | 1.90735e-05 | 1.000 |
| Full selective policy − Fixed schedule | Recall | 20 / 480 | +0.851 | [+0.365, +1.354] | 0.00533079 | 0.0159924 | 0.743 |
| ADWIN + persistence − Full selective policy | Event FPR | 20 / 960 | -3.151 | [-3.322, -2.982] | 1.90735e-06 | 1.90735e-05 | -1.000 |
| ADWIN + persistence − Full selective policy | Recall | 20 / 480 | -1.094 | [-1.649, -0.642] | 0.000300431 | 0.00120172 | -0.914 |
| ADWIN + persistence − Static Z-score | Event FPR | 20 / 960 | -5.156 | [-5.687, -4.607] | 1.90735e-06 | 1.90735e-05 | -1.000 |
| ADWIN + persistence − Static Z-score | Recall | 20 / 480 | +1.128 | [+0.399, +1.997] | 0.00653437 | 0.0159924 | 0.745 |
| Full selective policy − Static Z-score | Event FPR | 20 / 960 | -2.005 | [-2.407, -1.591] | 3.8147e-06 | 2.67029e-05 | -0.990 |
| Full selective policy − Static Z-score | Recall | 20 / 480 | +2.222 | [+1.233, +3.438] | 0.000126535 | 0.000632673 | 1.000 |

**Confirmatory decision — both frozen criteria passed.** Against static Z-score, the full policy's paired event-window FPR changed by −2.005 percentage points, with a 95% interval of [−2.407, −1.591]. Its paired recall changed by +2.222 points, with an interval of [+1.233, +3.438]. The FPR interval was entirely below zero and the recall interval's lower bound exceeded the frozen −5.0-point margin. In this holdout the entire recall interval was also above zero.

**Secondary candidate.** Persistence alone reduced paired event-window FPR by 5.156 points versus static and increased paired recall by 1.128 points. Compared with fixed scheduling, its paired FPR was 1.262 points lower and its recall interval, [−0.868, +0.417] points, included zero. Compared with the full policy, persistence traded a lower event-window FPR for lower recall. It remains the secondary candidate.

## Final NAB

Each method scored 41,326 observations, including 13 labeled points across 13 eligible benchmark windows. No labeled point was excluded by warm-up or unmatched after timestamp handling. The machine-temperature file contributed 22,428 scored observations. The loader retained a timestamp tie in source order and dropped 11 rows whose timestamps preceded the last retained timestamp. The other four files had no skipped rows. These counts use the frozen causal cleaning rule, which differs from counting backwards adjacent steps in the quality audit.

| Method | TP / FP / TN / FN | Precision | Recall | F1 | FPR | PR-AUC | Windows hit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Static Z-score | 7 / 8,190 / 33,123 / 6 | 0.00085 | 0.53846 | 0.00171 | 0.19824 | 0.08840 | 9/13 |
| Isolation Forest | 12 / 27,163 / 14,150 / 1 | 0.00044 | 0.92308 | 0.00088 | 0.65749 | 0.08003 | 13/13 |
| LOF | 10 / 10,060 / 31,253 / 3 | 0.00099 | 0.76923 | 0.00198 | 0.24351 | 0.00706 | 13/13 |
| Fixed schedule | 7 / 4,328 / 36,985 / 6 | 0.00161 | 0.53846 | 0.00322 | 0.10476 | 0.00209 | 10/13 |
| ADWIN + persistence | 7 / 11,404 / 29,909 / 6 | 0.00061 | 0.53846 | 0.00123 | 0.27604 | 0.00260 | 9/13 |
| Full selective policy | 8 / 19,478 / 21,835 / 5 | 0.00041 | 0.61538 | 0.00082 | 0.47147 | 0.07752 | 10/13 |

### nyc_taxi

`realKnownCause/nyc_taxi.csv` · 10,064 scored observations · 5 scored labeled points · 0 warm-up labeled points · 0 unmatched annotations · 5 labeled windows (5 scored).

| Method | TP / FP / TN / FN | Precision | Recall | F1 | FPR | PR-AUC | Windows hit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Static Z-score | 0 / 2 / 10,057 / 5 | 0.00000 | 0.00000 | 0.00000 | 0.00020 | 0.07704 | 1/5 |
| Isolation Forest | 4 / 4,810 / 5,249 / 1 | 0.00083 | 0.80000 | 0.00166 | 0.47818 | 0.07367 | 5/5 |
| LOF | 3 / 665 / 9,394 / 2 | 0.00449 | 0.60000 | 0.00892 | 0.06611 | 0.04394 | 5/5 |
| Fixed schedule | 1 / 6 / 10,053 / 4 | 0.14286 | 0.20000 | 0.16667 | 0.00060 | 0.20792 | 2/5 |
| ADWIN + persistence | 0 / 1 / 10,058 / 5 | 0.00000 | 0.00000 | 0.00000 | 0.00010 | 0.05339 | 1/5 |
| Full selective policy | 1 / 2 / 10,057 / 4 | 0.33333 | 0.20000 | 0.25000 | 0.00020 | 0.11628 | 2/5 |

### machine_temperature_system_failure

`realKnownCause/machine_temperature_system_failure.csv` · 22,428 scored observations · 4 scored labeled points · 0 warm-up labeled points · 0 unmatched annotations · 4 labeled windows (4 scored).

| Method | TP / FP / TN / FN | Precision | Recall | F1 | FPR | PR-AUC | Windows hit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Static Z-score | 4 / 8,104 / 14,320 / 0 | 0.00049 | 1.00000 | 0.00099 | 0.36140 | 0.28083 | 4/4 |
| Isolation Forest | 4 / 18,374 / 4,050 / 0 | 0.00022 | 1.00000 | 0.00044 | 0.81939 | 0.00032 | 4/4 |
| LOF | 4 / 9,281 / 13,143 / 0 | 0.00043 | 1.00000 | 0.00086 | 0.41389 | 0.28101 | 4/4 |
| Fixed schedule | 2 / 4,224 / 18,200 / 2 | 0.00047 | 0.50000 | 0.00095 | 0.18837 | 0.00091 | 4/4 |
| ADWIN + persistence | 4 / 11,319 / 11,105 / 0 | 0.00035 | 1.00000 | 0.00071 | 0.50477 | 0.00639 | 4/4 |
| Full selective policy | 4 / 19,392 / 3,032 / 0 | 0.00021 | 1.00000 | 0.00041 | 0.86479 | 0.25100 | 4/4 |

### exchange-3_cpc_results

`realAdExchange/exchange-3_cpc_results.csv` · 1,282 scored observations · 3 scored labeled points · 0 warm-up labeled points · 0 unmatched annotations · 3 labeled windows (3 scored).

| Method | TP / FP / TN / FN | Precision | Recall | F1 | FPR | PR-AUC | Windows hit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Static Z-score | 2 / 6 / 1,273 / 1 | 0.25000 | 0.66667 | 0.36364 | 0.00469 | 0.40000 | 3/3 |
| Isolation Forest | 3 / 125 / 1,154 / 0 | 0.02344 | 1.00000 | 0.04580 | 0.09773 | 0.24603 | 3/3 |
| LOF | 2 / 36 / 1,243 / 1 | 0.05263 | 0.66667 | 0.09756 | 0.02815 | 0.34667 | 3/3 |
| Fixed schedule | 3 / 20 / 1,259 / 0 | 0.13043 | 1.00000 | 0.23077 | 0.01564 | 0.26948 | 3/3 |
| ADWIN + persistence | 2 / 6 / 1,273 / 1 | 0.25000 | 0.66667 | 0.36364 | 0.00469 | 0.40000 | 3/3 |
| Full selective policy | 2 / 6 / 1,273 / 1 | 0.25000 | 0.66667 | 0.36364 | 0.00469 | 0.40000 | 3/3 |

### art_increase_spike_density

`artificialWithAnomaly/art_increase_spike_density.csv` · 3,776 scored observations · 1 scored labeled points · 0 warm-up labeled points · 0 unmatched annotations · 1 labeled windows (1 scored).

| Method | TP / FP / TN / FN | Precision | Recall | F1 | FPR | PR-AUC | Windows hit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Static Z-score | 1 / 78 / 3,697 / 0 | 0.01266 | 1.00000 | 0.02500 | 0.02066 | 0.01266 | 1/1 |
| Isolation Forest | 1 / 78 / 3,697 / 0 | 0.01266 | 1.00000 | 0.02500 | 0.02066 | 0.01266 | 1/1 |
| LOF | 1 / 78 / 3,697 / 0 | 0.01266 | 1.00000 | 0.02500 | 0.02066 | 0.01266 | 1/1 |
| Fixed schedule | 1 / 78 / 3,697 / 0 | 0.01266 | 1.00000 | 0.02500 | 0.02066 | 0.03030 | 1/1 |
| ADWIN + persistence | 1 / 78 / 3,697 / 0 | 0.01266 | 1.00000 | 0.02500 | 0.02066 | 0.01266 | 1/1 |
| Full selective policy | 1 / 78 / 3,697 / 0 | 0.01266 | 1.00000 | 0.02500 | 0.02066 | 0.01266 | 1/1 |

### art_flatline

`artificialNoAnomaly/art_flatline.csv` · 3,776 scored observations · 0 scored labeled points · 0 warm-up labeled points · 0 unmatched annotations · 0 labeled windows (0 scored).

| Method | TP / FP / TN / FN | Precision | Recall | F1 | FPR | PR-AUC | Windows hit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Static Z-score | 0 / 0 / 3,776 / 0 | — | — | — | 0.00000 | — | — |
| Isolation Forest | 0 / 3,776 / 0 / 0 | 0.00000 | — | 0.00000 | 1.00000 | — | — |
| LOF | 0 / 0 / 3,776 / 0 | — | — | — | 0.00000 | — | — |
| Fixed schedule | 0 / 0 / 3,776 / 0 | — | — | — | 0.00000 | — | — |
| ADWIN + persistence | 0 / 0 / 3,776 / 0 | — | — | — | 0.00000 | — | — |
| Full selective policy | 0 / 0 / 3,776 / 0 | — | — | — | 0.00000 | — | — |

| Method | ADWIN alarms | Proposals | Rejected | Incomplete | Refits | Median refits per series | Refit inputs | Replay seconds | Scored obs/s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Fixed schedule | — | — | — | — | 159 | 14 | 40704 | 0.434 | 95,247 |
| ADWIN + persistence | 382 | 52 | 32 | 1 | 19 | 0 | 2880 | 0.736 | 56,116 |
| Full selective policy | 382 | 98 | 88 | 2 | 8 | 0 | 1452 | 0.670 | 61,705 |

Both selective methods produced more point false positives than static Z-score. Persistence matched static recall at 7/13. The full policy detected 8/13 and gained one eligible window hit, but flagged 19,478 nominal observations versus 8,190 for static. Fixed scheduling cut false positives to 4,328 while retaining the same point recall as static. Isolation Forest and LOF hit all windows, with overall nominal FPRs of 65.75% and 24.35% respectively. Isolation Forest also flagged all scored points in the labeled-negative flatline control. The observations illustrate why the window metric must be read with point false positives.

NAB alarm and refit indices and timestamps, proposals and rejections, and proximity to anomaly windows are in the per-series result. The full and persistence policies saw the same 382 ADWIN alarms but acted on different subsets. Refits or alarms on these files cannot be classified as matched or unnecessary without independent drift labels.

## Generalization

The synthetic FPR in this table refers to the pooled event window. NAB FPR covers all nominal scored observations. Recall in both tables is pooled point recall.

| Synthetic split | Static Z-score FPR / recall | Fixed schedule FPR / recall | ADWIN + persistence FPR / recall | Full selective policy FPR / recall |
| --- | --- | --- | --- | --- |
| Aligned synthetic development | 22.23% / 93.37% | 15.40% / 96.70% | 10.65% / 96.13% | 19.21% / 95.67% |
| Non-aligned synthetic robustness | 9.20% / 96.77% | 3.28% / 97.80% | 3.98% / 98.23% | 7.57% / 98.60% |
| Primary synthetic holdout | 8.92% / 96.63% | 5.18% / 97.95% | 3.98% / 97.72% | 7.45% / 98.77% |

| NAB split | Static Z-score FPR / recall | Fixed schedule FPR / recall | ADWIN + persistence FPR / recall | Full selective policy FPR / recall |
| --- | --- | --- | --- | --- |
| NAB development | 3.39% / 40.00% | 1.56% / 40.00% | 4.27% / 60.00% | 8.95% / 60.00% |
| NAB final | 19.82% / 53.85% | 10.48% / 53.85% | 27.60% / 53.85% | 47.15% / 61.54% |

Both adaptive policies replicated their event-window FPR reductions and pooled recall gains versus static Z-score from aligned development and non-aligned robustness to the primary synthetic holdout. The full policy's paired FPR advantage over static weakened from 3.30 points on aligned development to 2.13 on robustness and 2.00 on primary holdout. It had higher event-window and post-drift FPR than fixed scheduling on all three grids.

Persistence's paired FPR advantage over fixed scheduling narrowed from −4.56 points on aligned development to −1.26 on primary holdout and reversed on the separately observed non-aligned set (+0.83 points). Fixed scheduling's median matched refit delay was 255 observations on the aligned primary holdout versus 128 on non-aligned robustness. The grids also differ in shifts, ramps, or seeds, which precludes attributing the prediction differences solely to phase alignment. [Aligned development](selective_adaptation_development.md) · [Robustness and NAB development](pre_final_validation.md)

On NAB, the selective policies' higher FPR versus static and fixed scheduling replicated and grew on the final series. Persistence's exact-point recall gain over static from development disappeared. The full policy retained a one-point gain, from 7/13 to 8/13 on final. The machine-temperature series accounted for nearly all excess false positives of both selective policies over static on final NAB. The synthetic false-positive benefit therefore did not transfer to this benchmark subset.

## Adaptation costs

| Method | Refits | Median refits per stream | Refit inputs | Unmatched refits | Matched refits | Median delay | Replay seconds | Scored obs/s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Static Z-score | 0 | 0.0 | 0 | 0 | 0 | — | 84.05 | 45,685 |
| Isolation Forest | 0 | 0.0 | 0 | 0 | 0 | — | 183.50 | 20,927 |
| LOF | 0 | 0.0 | 0 | 0 | 0 | — | 355.42 | 10,804 |
| Frozen Z-score + ADWIN | 0 | 0.0 | 0 | 0 | 0 | — | 87.31 | 43,981 |
| Frozen Z-score + Page-Hinkley | 0 | 0.0 | 0 | 0 | 0 | — | 91.32 | 42,051 |
| Fixed schedule | 15,000 | 15.0 | 3,840,000 | 13,720 | 1,280 | 255.0 | 92.15 | 41,670 |
| Immediate ADWIN | 1,534 | 1.0 | 392,704 | 254 | 1,280 | 63.0 | 82.26 | 46,683 |
| ADWIN + persistence | 1,430 | 1.0 | 187,584 | 150 | 1,280 | 191.0 | 87.46 | 43,906 |
| Persistence + filtering | 1,482 | 1.0 | 253,001 | 202 | 1,280 | 287.0 | 89.38 | 42,964 |
| Full selective policy | 1,326 | 1.0 | 225,242 | 46 | 1,280 | 287.0 | 72.40 | 53,038 |

Relative to fixed scheduling, persistence used 90.5% fewer refits and 95.1% fewer refit inputs. The full policy used 91.2% fewer refits and 94.1% fewer refit inputs. Both selective methods matched all 1,280 true transitions under the frozen refit matching rule. ADWIN itself matched all 1,280 and logged 254 additional scored alarms. Unmatched refits measure alignment with the allowed windows. A scheduled update can be useful even when it does not match an event.

The NAB refit reductions persisted. Persistence and the full policy made 19 and 8 refits versus 159 for fixed scheduling, with both selective policies running more slowly on the five-file aggregate. Fewer refits are a cost advantage in model updates. Replay wall time also includes scoring, monitoring, warm-up, and update overhead. The measured synthetic replay times exclude stream generation, analysis, and export. The run used one thread for each BLAS/OpenMP library and a peak process RSS of 776.8 MiB across all stages. The machine-readable manifest records Python, platform, and dependency versions.

## Failure cases

The report script selected four distinct synthetic streams from the recorded full-policy outputs. The selection takes the first stream with a miss, the first with an unmatched refit, the longest matched delay, the largest event-window FP count, and the largest event-window FP count among recurring streams. It chooses the worst window degradation across the three adaptive NAB methods relative to static Z-score. It then reproduces these selected scores and refits and renders the failure plot panels.

- **Missed anomaly.** The full policy missed the injected point at index 937 in stationary seed 1011.
- **Unnecessary refit.** On clean gradual drift with seed 1000, onset 1536, shift 2.25 and width 384, ADWIN alarm 2047 was unmatched and the full policy refit at 2239 without a matching transition.
- **Delayed refit.** On injected gradual drift with seed 1001, onset 1536, shift 1 and width 384, the matched refit occurred at 2047, a delay of 511 observations. The declared matching window accommodates late refits for long transitions.
- **Recurring drift.** On clean seed 1017, onset 1536 and shift 2.25, there were 100 false positives in the 256 observations after the return to state A. The following change back to B produced 124 false positives in the 256 observations starting at 2561.
- **NAB degradation.** In the machine-temperature window beginning at replay index 16046, persistence still hit the window but produced 566 point false positives, 115 more than static Z-score. Those are flags on rows without exact point labels inside the annotated window. NAB supplies no independent drift truth to explain the change in predictions.

## Final conclusion

**Supported on the primary synthetic holdout against static Z-score, conditional across datasets and comparators.** The confirmatory full policy lowered event-window false positives and improved isolated-anomaly recall on held-out simulated drift. The secondary candidate had lower synthetic false positives and lower recall than the full policy. Fixed scheduling provided a stronger false-positive comparator than static Z-score, and its relative performance against persistence changed with the grid. On final NAB, the full policy gained one detection at a large false-positive cost, and persistence gained no exact-point detections. The update-budget savings replicated across synthetic and NAB evaluation, while a wall-time advantage depended on the workload. The data support selective adaptation as a way to reduce refitting, and support the predictive benefit specifically for the controlled primary synthetic comparison.

## Limitations

The synthetic streams are univariate and use independent Gaussian noise, location shifts, and scripted isolated anomalies. They do not establish robustness to dependent noise, other distributions, multivariate signals, or arbitrary drift timing. The secondary candidate was selected on development and is subject to selection bias. The adaptive methods update Z-score means and scales only. The result does not generalize automatically to adapting Isolation Forest, LOF, or other models.

NAB has five held-out files, benchmark-specific annotation conventions and little point-level evidence. It has no authoritative drift labels. Large FPR differences on individual files affect the pooled result. The benchmark may contain meaningful deviations outside its annotated points, so the point false-positive count is tied to the annotation policy. Systems measurements cover this local Python replay. Spark deployment and distributed scaling are outside this evaluation.

## Reproducibility and execution status

The final evaluator wrote the original machine-readable results to ignored `results/final_evaluation/`. The directory contains the final manifest, primary synthetic pooled and per-stream outputs, frozen statistical comparisons, and per-series NAB metrics, event indices and timestamps. The report step verified the final split membership, matching synthetic pairs, raw NAB and label checksums, metric arithmetic, result counts, refit budgets, statistics and confirmatory decision. It recreated only a rule-selected set of streams to verify the illustrative failure cases. It did not repeat the complete final experiment. It saved tables, verification records, source provenance and plots under `report_artifacts/`.

To reproduce just the report artifacts from the recorded outputs, choose a new destination under the ignored results directory.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python \
  scripts/final_evaluation_artifacts.py --output results/final_report_reproduced
```

The active manifest is sealed with `status: executed`, the execution timestamp and Git revision, and SHA-256 digests of key artifacts. The frozen launcher rejects this executed manifest. The historical frozen file remains in Git at the execution revision, and the execution manifest also contains the original parsed specification. The seal changes no methods, thresholds, data, or metrics. Any later experiment that changes the protocol requires a new version and a post-hoc label.

The full 241-test suite passed. Ruff lint and format, uv lock and sync, and installed dependency checks passed. The report and receipt commit leaves the executable fingerprint intact.
