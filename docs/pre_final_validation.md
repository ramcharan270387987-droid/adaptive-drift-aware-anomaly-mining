# Pre-final validation and evaluation freeze

## Research question

Can explicit concept-drift detection and selective model adaptation reduce false anomaly alarms after distribution changes without reducing sensitivity to genuine anomalies?

The primary synthetic holdout and final NAB series remain untouched by this milestone. The non-aligned robustness set was explicitly opened for this milestone and is reported as a separate, already-observed check. Its outcomes do not select or tune the final methods.

## Methods and evaluation boundaries

The three static anomaly baselines use a warm-up-only fit. They are absolute Z-score at 3.0, Isolation Forest with 100 trees and seed 42, and LOF in novelty mode with 20 Euclidean neighbors. Isolation Forest and LOF use the frozen auto-contamination decision rules. The no-adaptation controls use raw-value ADWIN or bidirectional Page-Hinkley with frozen Z-score. Fixed scheduling refits Z-score every 256 observations on the trailing 256. The selective ablations use immediate alarm-driven refits, persistence confirmation, persistence plus prediction-based filtering, and the full policy with filtering and a cooldown. All policies replay each stream independently and score before updating.

Synthetic anomaly labels mark only the injected observations. Synthetic drift transitions have separate generator truth for matching. The 500 aligned development streams use seeds 0–9. The 500 non-aligned robustness streams use seeds 2000–2009, onsets 1603 and 2747, shifts 1 and 2.25, and ramp widths 192 and 384. Both grids include 250 clean/injected pairs and 640 true transitions. The non-aligned grid changes seeds, shift sizes, and ramp durations as well as timing. Differences across grids do not separately identify the effect of timing.

NAB point metrics label exact timestamps, assigning an annotated timestamp to its first retained source row. Separate inclusive anomaly windows receive at most one hit and contribute only if a scored row is present. The loader verifies the selected files and both annotation files against the pinned upstream revision and SHA-256 digests. It deserializes annotations only for the selected series, validates fields and timestamps, preserves equal timestamps in source order, and counts excluded annotations. Development rows that go backwards fail immediately. The future final adapter skips a row if its timestamp goes backwards relative to the last retained row, logging the drop and any unmatched point annotations. This rule preserves causal source order and is frozen before final evaluation. No development rows were dropped, and all 11 duplicate disk timestamps remained in replay. The warm-up excluded zero labeled points.

NAB has no independent drift truth. Refit and ADWIN event indices, timestamps, distance to annotated windows, checkpoint outcomes, candidates retained and filtered, model statistics before and after fitting, and local point-FP rates are descriptive. Point false positives inside a benchmark window are still point false positives under the exact-timestamp metric. A window hit does not establish detection of the annotated point, and neither proves detection of concept drift.

## Aligned synthetic development

On the aligned grid, persistence alone had 20,011 post-drift false positives, 116 misses among 3,000 anomalies, and 711 refits. Fixed scheduling had 30,162 post-drift false positives, 99 misses, and 7,500 refits. The full policy used 486 refits but had 173,269 post-drift false positives and 130 misses. Filtering changed the retained data and delayed or prevented refits. Adding cooldown reduced refits from 494 to 486 and unmatched refits from 13 to 5, with the same 481 matched transitions. The 0.75 and 1.00 sensitivity results did not materially change the full policy's development behavior. [Aligned ablations](selective_adaptation_development.md) · [Isolation Forest](isolation_forest_baseline.md) · [LOF](lof_baseline.md)

## Non-aligned synthetic robustness
| Method | TP / FP / TN / FN | Precision | Recall | F1 | FPR | PR-AUC | Post-drift FP | Event-window FPR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Full policy | 2,958 / 35,680 / 1,881,320 / 42 | 0.0766 | 0.9860 | 0.1421 | 0.0186 | 0.8015 | 28,477 | 0.0757 |
| Immediate ADWIN | 2,871 / 17,897 / 1,899,103 / 129 | 0.1382 | 0.9570 | 0.2416 | 0.0093 | 0.8819 | 12,955 | 0.0216 |
| ADWIN + persistence | 2,947 / 14,818 / 1,902,182 / 53 | 0.1659 | 0.9823 | 0.2838 | 0.0077 | 0.9043 | 8,489 | 0.0398 |
| Persistence + filtering | 2,963 / 33,612 / 1,883,388 / 37 | 0.0810 | 0.9877 | 0.1497 | 0.0175 | 0.8126 | 26,409 | 0.0754 |
| Static Z-score | 2,903 / 110,959 / 1,806,041 / 97 | 0.0255 | 0.9677 | 0.0497 | 0.0579 | 0.7331 | 103,059 | 0.0920 |
| Fixed schedule | 2,934 / 13,267 / 1,903,733 / 66 | 0.1811 | 0.9780 | 0.3056 | 0.0069 | 0.9161 | 7,910 | 0.0328 |

| Method | Alarms / matched / false | Median alarm delay | Refits / matched / unmatched | Median refit delay | Refit input uses | Streams with unmatched refit |
| --- | --- | --- | --- | --- | --- | --- |
| Full policy | 777 / 640 / 137 | 68 | 655 / 639 / 16 | 284 | 111,615 | 3.2% |
| Immediate ADWIN | 777 / 640 / 137 | 68 | 777 / 640 / 137 | 68 | 198,912 | 27.4% |
| ADWIN + persistence | 777 / 640 / 137 | 68 | 718 / 639 / 79 | 220 | 93,568 | 15.8% |
| Persistence + filtering | 777 / 640 / 137 | 68 | 748 / 639 / 109 | 284 | 128,104 | 21.8% |
| Static Z-score | — | — | 0 / 0 / 0 | — | 0 | 0.0% |
| Fixed schedule | — | — | 7,500 / 640 / 6,860 | 128 | 1,920,000 | 100.0% |
| Frozen Z-score + ADWIN | 777 / 640 / 137 | 68 | 0 / 0 / 0 | — | 0 | 0.0% |
| Frozen Z-score + Page-Hinkley | 2,002 / 639 / 1,363 | 50 | 0 / 0 / 0 | — | 0 | 0.0% |

Both no-adaptation controls reproduced the static anomaly results. ADWIN matched all 640 transitions and had 137 unmatched alarms. Page-Hinkley matched 639 with 1,363 unmatched alarms. Median matched alarm delays were 68 and 50 observations, respectively. Fixed scheduling's median matched refit delay fell from 255 in aligned development to 128 in robustness. This gives direct evidence that the aligned grid phases constrained the scheduled update delay. Fixed scheduling still had the fewest post-drift false positives on the non-aligned grid, with 7,910 across 828,422 nominal post-drift points, compared with 8,489 for persistence and 28,477 for the full policy. In the same order, the rates were 0.95%, 1.02%, and 3.44%, versus 2.59%, 1.72%, and 14.87% on aligned development.

Persistence used 90.4% fewer refits and 95.1% fewer refit-input uses than fixed scheduling. It missed 13 fewer anomalies on the robustness grid. Immediate ADWIN refitting had the lowest event-window FPR at 2.16%, but missed 129 anomalies. The full policy reduced event-window FPR relative to static Z-score and raised point recall, while fixed scheduling achieved lower FPR with more updates. Relative to filtering alone, adding cooldown reduced unmatched refits from 109 to 16 and slightly increased post-drift FP. Compared with persistence alone, filtering kept the same matched coverage on the robustness grid but increased median matched delay from 220 to 284 and increased post-drift FP. On the aligned grid, it also lowered coverage from 640 to 481 matched refits. The grid change cannot isolate the effects of timing, shift magnitude, and ramp width on that difference.

## NAB development

Each method scored 18,046 points, including five labeled anomalies in five scored windows. The pooled window hit rate was 5/5 for every method. Point recall varied from two to four detections out of five. Both selective variants spent markedly fewer refits than fixed scheduling, detected one more labeled point, and recorded more point false positives. This small comparison supplies complementary anomaly evidence.
| Method | TP / FP / TN / FN | Precision | Recall | F1 | FPR | PR-AUC | Windows hit | Refits / input uses |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Static Z-score | 2 / 611 / 17,430 / 3 | 0.0033 | 0.4000 | 0.0065 | 0.0339 | 0.0123 | 5/5 | 0 / 0 |
| Isolation Forest | 4 / 8,257 / 9,784 / 1 | 0.0005 | 0.8000 | 0.0010 | 0.4577 | 0.0147 | 5/5 | 0 / 0 |
| LOF | 4 / 3,732 / 14,309 / 1 | 0.0011 | 0.8000 | 0.0021 | 0.2069 | 0.0098 | 5/5 | 0 / 0 |
| Fixed schedule | 2 / 281 / 17,760 / 3 | 0.0071 | 0.4000 | 0.0139 | 0.0156 | 0.0125 | 5/5 | 67 / 17,152 |
| ADWIN + persistence | 3 / 771 / 17,270 / 2 | 0.0039 | 0.6000 | 0.0077 | 0.0427 | 0.0109 | 5/5 | 2 / 256 |
| Full policy | 3 / 1,615 / 16,426 / 2 | 0.0019 | 0.6000 | 0.0037 | 0.0895 | 0.0103 | 5/5 | 5 / 760 |

Each labeled-window entry shows hits over eligible windows. A dash marks an undefined rate. Precision requires a predicted positive, recall requires a labeled positive, F1 requires a labeled or predicted positive, and average precision requires both truth classes.

### Cloud CPU

`realAWSCloudwatch/ec2_cpu_utilization_53ea38.csv` · 3,776 scored observations · 2 labeled points · 2 labeled windows

| Method | TP / FP / TN / FN | Precision | Recall | F1 | FPR | PR-AUC | Windows hit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Static Z-score | 0 / 31 / 3,743 / 2 | 0.0000 | 0.0000 | 0.0000 | 0.0082 | 0.0069 | 2/2 |
| Isolation Forest | 1 / 821 / 2,953 / 1 | 0.0012 | 0.5000 | 0.0024 | 0.2175 | 0.0037 | 2/2 |
| LOF | 1 / 681 / 3,093 / 1 | 0.0015 | 0.5000 | 0.0029 | 0.1804 | 0.0010 | 2/2 |
| Fixed schedule | 0 / 37 / 3,737 / 2 | 0.0000 | 0.0000 | 0.0000 | 0.0098 | 0.0102 | 2/2 |
| ADWIN + persistence | 0 / 31 / 3,743 / 2 | 0.0000 | 0.0000 | 0.0000 | 0.0082 | 0.0069 | 2/2 |
| Full policy | 0 / 31 / 3,743 / 2 | 0.0000 | 0.0000 | 0.0000 | 0.0082 | 0.0069 | 2/2 |

### Cloud disk

`realAWSCloudwatch/ec2_disk_write_bytes_1ef3de.csv` · 4,474 scored observations · 1 labeled points · 1 labeled windows

| Method | TP / FP / TN / FN | Precision | Recall | F1 | FPR | PR-AUC | Windows hit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Static Z-score | 1 / 480 / 3,993 / 0 | 0.0021 | 1.0000 | 0.0041 | 0.1073 | 0.0435 | 1/1 |
| Isolation Forest | 1 / 4,473 / 0 / 0 | 0.0002 | 1.0000 | 0.0004 | 1.0000 | 0.0002 | 1/1 |
| LOF | 1 / 480 / 3,993 / 0 | 0.0021 | 1.0000 | 0.0041 | 0.1073 | 0.0435 | 1/1 |
| Fixed schedule | 1 / 145 / 4,328 / 0 | 0.0068 | 1.0000 | 0.0136 | 0.0324 | 0.0227 | 1/1 |
| ADWIN + persistence | 1 / 480 / 3,993 / 0 | 0.0021 | 1.0000 | 0.0041 | 0.1073 | 0.0435 | 1/1 |
| Full policy | 1 / 480 / 3,993 / 0 | 0.0021 | 1.0000 | 0.0041 | 0.1073 | 0.0435 | 1/1 |

### Road speed

`realTraffic/speed_6005.csv` · 2,244 scored observations · 1 labeled points · 1 labeled windows

| Method | TP / FP / TN / FN | Precision | Recall | F1 | FPR | PR-AUC | Windows hit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Static Z-score | 1 / 2 / 2,241 / 0 | 0.3333 | 1.0000 | 0.5000 | 0.0009 | 0.5000 | 1/1 |
| Isolation Forest | 1 / 321 / 1,922 / 0 | 0.0031 | 1.0000 | 0.0062 | 0.1431 | 0.3333 | 1/1 |
| LOF | 1 / 81 / 2,162 / 0 | 0.0122 | 1.0000 | 0.0241 | 0.0361 | 0.5000 | 1/1 |
| Fixed schedule | 1 / 26 / 2,217 / 0 | 0.0370 | 1.0000 | 0.0714 | 0.0116 | 0.5000 | 1/1 |
| ADWIN + persistence | 1 / 2 / 2,241 / 0 | 0.3333 | 1.0000 | 0.5000 | 0.0009 | 0.5000 | 1/1 |
| Full policy | 1 / 2 / 2,241 / 0 | 0.3333 | 1.0000 | 0.5000 | 0.0009 | 0.5000 | 1/1 |

### Daily jump

`artificialWithAnomaly/art_daily_jumpsup.csv` · 3,776 scored observations · 1 labeled points · 1 labeled windows

| Method | TP / FP / TN / FN | Precision | Recall | F1 | FPR | PR-AUC | Windows hit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Static Z-score | 0 / 98 / 3,677 / 1 | 0.0000 | 0.0000 | 0.0000 | 0.0260 | 0.0099 | 1/1 |
| Isolation Forest | 1 / 1,230 / 2,545 / 0 | 0.0008 | 1.0000 | 0.0016 | 0.3258 | 0.0058 | 1/1 |
| LOF | 1 / 430 / 3,345 / 0 | 0.0023 | 1.0000 | 0.0046 | 0.1139 | 0.0099 | 1/1 |
| Fixed schedule | 0 / 73 / 3,702 / 1 | 0.0000 | 0.0000 | 0.0000 | 0.0193 | 0.0130 | 1/1 |
| ADWIN + persistence | 1 / 258 / 3,517 / 0 | 0.0039 | 1.0000 | 0.0077 | 0.0683 | 0.0099 | 1/1 |
| Full policy | 1 / 1,102 / 2,673 / 0 | 0.0009 | 1.0000 | 0.0018 | 0.2919 | 0.0099 | 1/1 |

### Daily no-noise

`artificialNoAnomaly/art_daily_no_noise.csv` · 3,776 scored observations · 0 labeled points · 0 labeled windows

| Method | TP / FP / TN / FN | Precision | Recall | F1 | FPR | PR-AUC | Windows hit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Static Z-score | 0 / 0 / 3,776 / 0 | — | — | — | 0.0000 | — | — |
| Isolation Forest | 0 / 1,412 / 2,364 / 0 | 0.0000 | — | 0.0000 | 0.3739 | — | — |
| LOF | 0 / 2,060 / 1,716 / 0 | 0.0000 | — | 0.0000 | 0.5456 | — | — |
| Fixed schedule | 0 / 0 / 3,776 / 0 | — | — | — | 0.0000 | — | — |
| ADWIN + persistence | 0 / 0 / 3,776 / 0 | — | — | — | 0.0000 | — | — |
| Full policy | 0 / 0 / 3,776 / 0 | — | — | — | 0.0000 | — | — |

Both selective variants observed 95 ADWIN alarms. Persistence accepted two refits from 39 proposals, with 34 rejected and three incomplete. The full policy accepted five from 38 proposals, with 30 rejected and three incomplete. Both policies refitted only on the two artificial series. None of their refits fell inside a labeled window. Seven of the 67 scheduled refits fell within labeled windows. These counts have no drift-accuracy interpretation. The frozen selective budgets are at most 15 refits and 3,840 input uses per stream. The scheduled control's natural cadence on longer NAB series can exceed the 4,096-point synthetic budget, as observed on the disk series with 17 updates.

## Paired comparisons and uncertainty

The sample unit for inference is the independent seed. Each seed block carries all applicable streams and both clean/injected members. For each contrast, subtract the comparator from the first method's metric on each paired stream, then average. The event FPR metric covers onset through transition end plus 256 points, clipped at the next onset. It uses 480 nonstationary streams per contrast. Recall uses the 240 injected members of those pairs. The table reports percentage-point differences. The 95% percentile intervals resample ten seed blocks with replacement, using 10,000 draws and seed 1729. Intervals are descriptive and unadjusted.

The two-sided Wilcoxon signed-rank test uses the ten seed means. Its null is that the distribution of paired seed means is symmetric around zero. Seed blocks with zero differences are removed for the test and rank-biserial effect size. The code reports a test only with at least six nonzero blocks. Holm adjustment covers all ten tests within each grid. Signed rank-biserial correlation ranges from −1 to +1 and follows the direction of the first method minus its comparator. With ten seeds, these comparisons have limited resolution and are exploratory. On NAB, there are five intentionally selected files, only four with positive point labels. Per-series metrics and descriptive means, medians, and standard deviations are exported. No NAB inferential test was justified.
### Aligned development

| First method − comparator | Metric | Mean Δ | Median seed Δ | Seed SD | 95% interval | Raw p | Holm p | Rank biserial |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ADWIN + persistence − Fixed schedule | Event FPR | -4.56 | -5.06 | 1.74 | [-5.51, -3.49] | 0.00195 | 0.01953 | -1.00 |
| ADWIN + persistence − Fixed schedule | Recall | -0.62 | -0.52 | 0.88 | [-1.15, -0.14] | 0.06250 | 0.18750 | -0.90 |
| Full policy − Fixed schedule | Event FPR | +4.64 | +4.62 | 3.49 | [+2.83, +6.86] | 0.00195 | 0.01953 | 1.00 |
| Full policy − Fixed schedule | Recall | -1.11 | -0.87 | 1.85 | [-2.22, -0.07] | 0.10547 | 0.21094 | -0.62 |
| ADWIN + persistence − Full policy | Event FPR | -9.20 | -9.33 | 2.32 | [-10.63, -7.94] | 0.00195 | 0.01953 | -1.00 |
| ADWIN + persistence − Full policy | Recall | +0.49 | -0.17 | 1.39 | [-0.28, +1.39] | 0.41016 | 0.41016 | 0.33 |
| ADWIN + persistence − Static Z-score | Event FPR | -12.50 | -12.48 | 2.09 | [-13.73, -11.28] | 0.00195 | 0.01953 | -1.00 |
| ADWIN + persistence − Static Z-score | Recall | +2.88 | +2.60 | 2.72 | [+1.28, +4.48] | 0.01562 | 0.06250 | 0.87 |
| Full policy − Static Z-score | Event FPR | -3.30 | -3.11 | 0.75 | [-3.79, -2.91] | 0.00195 | 0.01953 | -1.00 |
| Full policy − Static Z-score | Recall | +2.40 | +2.60 | 2.11 | [+1.18, +3.65] | 0.00781 | 0.03906 | 1.00 |

### Non-aligned robustness

| First method − comparator | Metric | Mean Δ | Median seed Δ | Seed SD | 95% interval | Raw p | Holm p | Rank biserial |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ADWIN + persistence − Fixed schedule | Event FPR | +0.83 | +0.87 | 0.72 | [+0.40, +1.25] | 0.00977 | 0.03906 | 0.89 |
| ADWIN + persistence − Fixed schedule | Recall | +0.45 | +0.52 | 1.67 | [-0.62, +1.32] | 0.21680 | 0.26562 | 0.45 |
| Full policy − Fixed schedule | Event FPR | +4.09 | +4.01 | 1.05 | [+3.48, +4.70] | 0.00195 | 0.01953 | 1.00 |
| Full policy − Fixed schedule | Recall | +0.83 | +0.87 | 1.15 | [+0.10, +1.46] | 0.06250 | 0.18750 | 0.71 |
| ADWIN + persistence − Full policy | Event FPR | -3.27 | -3.27 | 0.40 | [-3.50, -3.04] | 0.00195 | 0.01953 | -1.00 |
| ADWIN + persistence − Full policy | Recall | -0.38 | -0.35 | 0.64 | [-0.80, -0.03] | 0.13281 | 0.26562 | -0.67 |
| ADWIN + persistence − Static Z-score | Event FPR | -5.40 | -5.34 | 1.16 | [-6.09, -4.75] | 0.00195 | 0.01953 | -1.00 |
| ADWIN + persistence − Static Z-score | Recall | +1.53 | +1.22 | 1.10 | [+0.94, +2.22] | 0.00195 | 0.01953 | 1.00 |
| Full policy − Static Z-score | Event FPR | -2.13 | -2.08 | 0.90 | [-2.69, -1.64] | 0.00195 | 0.01953 | -1.00 |
| Full policy − Static Z-score | Recall | +1.91 | +1.91 | 0.82 | [+1.46, +2.40] | 0.00195 | 0.01953 | 1.00 |

The sign of the persistence-versus-fixed event FPR difference changed across grids. The adjusted p-values for that contrast were 0.01953 on aligned development and 0.03906 on robustness, with effects of −4.56 and +0.83 percentage points, respectively. This shows a reversal for these grids. The design does not isolate a timing-only treatment effect. Recall differences for the same contrast have Holm-adjusted p-values above 0.05 on both grids.

## Update budgets and runtime

On robustness, an unmatched refit occurred on 15.8% of streams using persistence, 3.2% using the full policy, and 100% using fixed scheduling. Unmatched means the refit had no one-to-one match under the frozen event windows. It does not establish whether the refit was useful. On NAB the corresponding quantity is unavailable because no drift ground truth exists. The outcome files instead report observed refit counts, window proximity and nominal-point FP statistics before and after each update.

| Method | Robustness replay s | Robustness scored/s | NAB replay s | NAB scored/s |
| --- | --- | --- | --- | --- |
| Static Z-score | 37.08 | 51,774 | 0.176 | 102,559 |
| Isolation Forest | — | — | 0.689 | 26,191 |
| LOF | — | — | 1.350 | 13,371 |
| Fixed schedule | 41.91 | 45,816 | 0.139 | 129,507 |
| Immediate ADWIN | 33.49 | 57,329 | — | — |
| ADWIN + persistence | 35.52 | 54,054 | 0.154 | 117,048 |
| Persistence + filtering | 38.87 | 49,390 | — | — |
| Full policy | 30.63 | 62,692 | 0.154 | 117,342 |
| Frozen Z-score + ADWIN | 40.13 | 47,843 | — | — |
| Frozen Z-score + Page-Hinkley | 42.25 | 45,442 | — | — |

The verified run used Python 3.12.14 and Linux with 3 logical CPUs visible. Peak process RSS was 464.2 MiB. The run used Git revision `4d5dd7bf47a7409bb50e9333d465918f4e01ddfe`.

Timing includes detector warm-up, scoring, drift handling, and refits. It excludes loading, generation, evaluation, and export. It measures a single local run with one thread requested for each BLAS/OpenMP library. Process peak RSS covers the whole evaluation and is reported separately in the manifest. It includes analysis and export work and cannot attribute memory to individual methods.

## Failure cases

Seven reproducible PNGs are exported with the selected series, index, positive decisions, annotations, and observed events in `failure_cases.json`. The deterministic rules take the first eligible missed anomaly, unmatched alarm, and unmatched refit in grid order, the largest matched refit delay, the highest 256-point post-transition FP count, the largest FP count after the B→A recurrence, and the worst NAB window deterioration relative to static. Ties use grid order.

- The full policy missed the injected anomaly at 2803 on sudden drift, seed 2004, onset 2747 and shift 1.0.
- On clean gradual drift, seed 2000, onset 1603, shift 1.0 and width 384, ADWIN alarm 2239 was outside the frozen alarm-matching window. Another gradual scenario at the same onset, shift 2.25 with width 192 and injection, had an unmatched full-policy refit at 2847.
- The maximum matched refit delay was 644 observations, ending at 3391 on clean gradual drift, seed 2008, onset 2747, shift 1.0 and width 384. The late refit still fell in the frozen window for that long transition.
- The largest burst followed the recurring return to state A on clean seed 2004, onset 2747 and shift 2.25. The full policy flagged 124 nominal points in the 256 observations starting at 3260.
- On NAB daily jump, the full policy retained the window hit but produced 54 more point false positives inside that window than static Z-score. Across the file it flagged 1,102 nominal points versus 98 for static. Its last refit, at index 1503, occurred 1,284 rows before the annotated window. Point FP increased from 0/256 immediately before that update to 120/256 immediately after. The pattern is descriptive, since the data cannot label the refit as a correct or incorrect drift response.

## Final method freeze

- **Confirmatory primary** is the originally frozen full policy at 0.50, compared with static Z-score on primary synthetic holdout. It retains filtering and a 128-observation cooldown. The success rule is unchanged. The paired event-window FPR interval must be entirely below zero and the lower bound of the isolated-point recall difference must exceed −0.05.
- **Development-selected secondary** is ADWIN + persistence at 0.50, with unfiltered fits and no cooldown. Aligned development selected it because it reduced post-drift FP versus the other selective variants, maintained strong point recall, and used substantially fewer updates than fixed scheduling. Non-aligned robustness and NAB show where that trade-off weakens, and neither changed the choice or any parameter.

Both methods use univariate population Z-score, anomaly threshold `abs(z) >= 3.0`, a 1e-12 effective-scale floor and a 256-point warm-up. ADWIN uses raw values, delta 0.002, clock 32, five buckets, minimum window length five and grace period ten. At 128, 192 and 256 observations after an accepted alarm, both medians of the two most recent nonoverlapping 64-point blocks must cross the alarm-time mean by at least 0.50 effective deviations on the same side. Only observations strictly after the alarm can enter these refits, with a 256-point maximum window and at least 128 retained. Filtering in the full policy excludes only points flagged by the pre-update model. Each selective run has caps of 15 refits and 3,840 input uses. The manifest captures simulator seeds, Isolation Forest seed 42, and bootstrap seed 1729 alongside every comparator and predefined stage. [Frozen manifest](../configs/final_evaluation.yaml)

## Reproduction and verification

Reproduce the aligned reference and the permitted pre-final stages from the repository root in the locked environment. Both output paths below must be new. Only development NAB files and the shared pinned metadata are acquired by the second command.

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
.venv/bin/python -m drift_anomaly.experiments.selective_evaluation \
  --output results/aligned_reference
.venv/bin/python -m drift_anomaly.experiments.validation \
  --aligned-reference results/aligned_reference --output results/pre_final
.venv/bin/python -m drift_anomaly.experiments.final_evaluation \
  --config configs/final_evaluation.yaml --check
```

The pinned-source rerun reproduced all 4,000 synthetic replay summaries, 30 NAB replay summaries, both statistical comparisons, and seven byte-identical plots. Runtime and execution timestamps vary across runs. All 241 tests passed, along with Ruff lint and formatting, uv lock and sync verification, and the installed dependency check.

The pre-final run records its exact Git commit, execution-tree SHA-256, platform, versions, and datasets. The manifest validation compares the full declared configuration and executable input fingerprint. The executable input fingerprint is independent of documentation-only changes. The future command below requires explicit authorization. It runs the primary synthetic and final NAB stages and leaves the already-observed robustness set separate. No final stage was executed in this validation milestone.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python \
  -m drift_anomaly.experiments.final_evaluation \
  --config configs/final_evaluation.yaml --authorize-final
```

## Limitations

Synthetic data have Gaussian regimes, independent noise, a fixed injection mechanism, and designed location changes. The non-aligned set changes several design dimensions at once. NAB has no authoritative drift ground truth, few labeled points, and benchmark-specific sampling and window effects. Its five development files are a purposeful subset, with two artificial series driving all selective refits. Univariate Z-score adaptation changes only the mean and scale and can misread seasonal behavior or contaminated windows. The secondary method was selected on development, so its favorable aligned results are subject to selection bias. The present evidence does not support a universal advantage, a claim about multivariate streams, or a production performance conclusion.
