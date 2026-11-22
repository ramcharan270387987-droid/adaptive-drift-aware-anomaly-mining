---
title: Drift-Triggered Selective Refitting for Explainable Streaming Anomaly Detection
author: "[Enter author names and affiliations]"
---

## Abstract

A fixed detector can repeatedly flag nominal points after their underlying distribution changes. This study tests an ADWIN-triggered selective Z-score refit against static, drift-only, and periodic controls. On a 1,000-stream-per-method synthetic holdout, the frozen full policy reduced paired event-window false-positive rate by 2.005 percentage points (95% CI −2.407 to −1.591) and increased isolated-anomaly recall by 2.222 points (95% CI +1.233 to +3.438) versus static Z-score. The policy used 1,326 updates compared with 15,000 for fixed scheduling. On five final NAB series it identified one more exact anomaly point and produced 11,288 more false positives than static Z-score. A development-only Spark local implementation preserves chronological scoring, verifies replay equivalence, and exposes alarm and refit evidence. The results support conditional gains on the synthetic comparison and document substantial real-benchmark trade-offs.

**Keywords** — Anomaly detection, concept drift, online model adaptation, causal replay, Structured Streaming.

## I. Introduction

An anomaly score describes deviation from a reference [1]. A distribution shift can invalidate that reference for ordinary points. Drift adaptation addresses a different decision about whether to change the model [2]. We ask whether explicit drift detection and selective adaptation reduce post-change false alarms while preserving genuine anomaly sensitivity. Our study separates three outcomes: point predictions, the ability to recognize a transition, and the cost of updating. It contributes a reproducible causal framework, a gated refit policy with matched controls, a controlled synthetic and complementary NAB evaluation, and an operational journal that explains score and update events.

## II. Related work

Isolation Forest isolates points via randomized partitions [3]. LOF measures local density relative to that of neighbors [4]. We use both as static warm-up baselines alongside Z-score. ADWIN uses an adaptive window for evolving data [5]. Page’s cumulative inspection framework [6] and Hinkley’s change-point analysis [7] provide historical context for the comparator. Online Isolation Forest [8] represents a different adaptation design with incremental tree updates. It was outside the frozen baselines, so these experiments make no performance comparison with it.

NAB evaluates anomalies in streaming timelines [9]. Broader time-series benchmarking shows the importance of data and metric choice [10]. We report exact labeled-point and window-hit metrics separately on a pinned NAB subset. This implementation exposes actual decision inputs and transitions, consistent with the need to specify what an interpretation describes [11]. Spark’s declarative Structured Streaming model [12] supports the local engineering demonstration. The contribution concerns a particular refit policy and its measured cost and failure modes; the component detectors are established methods.

## III. Problem formulation

For scalar observation $x_t$, the pre-update reference $(\mu,\sigma)$ defines $z_t=|x_t-\mu|/\max(\sigma,10^{-12})$ with threshold 3.0. Flagging an anomaly and deciding to update are distinct actions. The score and flag for $t$ must be committed before an update can affect a subsequent point. Anomaly and synthetic drift truth enter evaluation only. Event-window FPR measures flagged nominal points from drift onset through 256 observations after transition end, clipped at the next onset. Overall point recall measures recovered labeled anomalies.

## IV. Methodology

All methods use a 256-point warm-up. ADWIN ingests raw observations with frozen delta 0.002. An accepted alarm opens one post-alarm candidate with the alarm-time mean and scale. At offsets 128, 192 and 256, two nonoverlapping 64-point medians must each deviate from the mean by at least 0.50 effective standard deviations in the same direction. The full policy discards points flagged by the unchanged scoring model and needs at least 128 retained observations. A refit uses at most 256 post-alarm observations and precedes a 128-point cooldown. Each 4,096-point trace allows 15 refits and 3,840 refit-input uses. The secondary policy omits filtering and cooldown. Immediate ADWIN uses a trailing-window refit on an alarm, and the fixed-schedule control refits the trailing 256 every 256 observations. [Frozen protocol](selective_adaptation_protocol.md)

## V. Experimental setup

The primary synthetic holdout comprises stationary, sudden, gradual, incremental and recurring Gaussian streams under seeds 1000–1019. The 500 clean/injected pairs yield 3,840,000 scored points, 6,000 injected anomalies, and 1,280 planted transitions. Both members share the base signal. The separate non-aligned grid characterizes robustness. The five pinned NAB final series provide 41,326 scored points and 13 eligible point annotations and windows. NAB was analyzed descriptively.

The confirmatory contrast compares the full policy against static Z-score. A 95% event-window FPR difference interval entirely below zero and an isolated recall interval above −5 percentage points were required. Fixed-seed resampling used 10,000 seed-block replicates. Event-window FPR involved 960 paired streams and recall 480. We applied Wilcoxon signed-rank tests to seed means with Holm correction for the ten prespecified contrasts. Seed-level resampling retains dependence among scenarios sharing a seed. [Experimental protocol](experimental_protocol.md)

## VI. Results

| Method | Synthetic post-drift FP | Synthetic recall | Refits |
| --- | ---: | ---: | ---: |
| Static Z-score | 216,554 | 96.63% | 0 |
| Fixed schedule | 24,872 | 97.95% | 15,000 |
| ADWIN + persistence | 17,205 | 97.72% | 1,430 |
| Full policy | 56,768 | 98.77% | 1,326 |

Both confirmatory criteria passed. The event-window effect was −2.005 percentage points, adjusted $p=0.0000267$, with rank-biserial effect −0.990. Recall improved 2.222 percentage points, adjusted $p=0.000633$, with rank-biserial effect +1.000. The full policy used 225,242 refit inputs compared with 3,840,000 for fixed scheduling. Both drift-only controls exactly reproduced static point predictions.

On NAB, the full policy found 8/13 points and 10/13 windows, versus 7/13 and 9/13 for static Z-score. Its point false positives increased from 8,190 to 19,478. Fixed scheduling produced 4,328 false positives and 7/13 exact detections. False positives for selective policies concentrated in the machine-temperature stream. An illustrative persistence failure added 115 false positives in one window while retaining its hit. [Full tables and all contrasts](final_evaluation.md)

Spark 4.1.1 processed development inputs with keyed local partitioning and a transactional SQLite journal. The benchmark reconciled each workload to reference replay without dropped records. The highest measured commit rate was 3,886 rows/s at an offered 4,096 rows/s. At the 8,192 target with shorter triggers, peak queued rows reached 21,300. These finite, single-host data describe observed load behavior. [Benchmark table](academic/TABLES.md#table-g-single-host-local-spark-benchmark)

## VII. Discussion

The full policy improved the controlled confirmatory contrast and used about 91% fewer refits than fixed scheduling. Fixed scheduling still produced fewer synthetic post-drift false positives than the full policy. The secondary persistence policy recorded the lowest post-drift count, at lower recall than the full policy. Its event-window FPR comparison with fixed scheduling reversed on non-aligned robustness, where the grid also differs in seeds or shift settings. The synthetic gain did not transfer to the final NAB subset. One additional exact-point detection there came with substantial false positives. In recurring synthetic drift, the time spent confirming a change can leave a long burst of flags.

## VIII. Limitations

The generator uses scalar Gaussian regimes and scripted anomalies. The confirmation gate and adaptation budgets are specific to Z-score. The secondary policy was selected on development. NAB provides little exact-point evidence and no independent drift truth. Latency includes local scheduler and commit behavior, and the benchmark lacks long-duration and distributed trials. The dashboard’s evidence trace was verified functionally without a user study.

## IX. Conclusion

Selective updates lowered event-window FPR and preserved recall on the frozen primary synthetic holdout against static Z-score. Update savings were substantial, while predictive advantages depended on comparator and benchmark. The Spark and explanation layers demonstrate faithful local execution and make both benefits and failures inspectable. [Reproducibility](REPRODUCIBILITY.md)

## References

[1] V. Chandola, A. Banerjee, and V. Kumar, “Anomaly Detection: A Survey,” *ACM Computing Surveys*, vol. 41, no. 3, art. 15, 2009. [DOI](https://doi.org/10.1145/1541880.1541882)

[2] J. Gama, I. Žliobaitė, A. Bifet, M. Pechenizkiy, and A. Bouchachia, “A Survey on Concept Drift Adaptation,” *ACM Computing Surveys*, vol. 46, no. 4, art. 44, 2014. [DOI](https://doi.org/10.1145/2523813)

[3] F. T. Liu, K. M. Ting, and Z.-H. Zhou, “Isolation Forest,” in *2008 Eighth IEEE International Conference on Data Mining*, 2008, pp. 413–422. [DOI](https://doi.org/10.1109/ICDM.2008.17)

[4] M. M. Breunig, H.-P. Kriegel, R. T. Ng, and J. Sander, “LOF: Identifying Density-Based Local Outliers,” in *Proceedings of the 2000 ACM SIGMOD International Conference on Management of Data*, 2000, pp. 93–104. [DOI](https://doi.org/10.1145/342009.335388)

[5] A. Bifet and R. Gavaldà, “Learning from Time-Changing Data with Adaptive Windowing,” in *Proceedings of the 2007 SIAM International Conference on Data Mining*, 2007, pp. 443–448. [DOI](https://doi.org/10.1137/1.9781611972771.42)

[6] E. S. Page, “Continuous Inspection Schemes,” *Biometrika*, vol. 41, nos. 1–2, pp. 100–115, 1954. [DOI](https://doi.org/10.1093/biomet/41.1-2.100)

[7] D. V. Hinkley, “Inference About the Change-Point in a Sequence of Random Variables,” *Biometrika*, vol. 57, no. 1, pp. 1–17, 1970. [DOI](https://doi.org/10.1093/biomet/57.1.1)

[8] F. Leveni, G. Weigert Cassales, B. Pfahringer, A. Bifet, and G. Boracchi, “Online Isolation Forest,” in *Proceedings of the 41st International Conference on Machine Learning*, PMLR, vol. 235, 2024, pp. 27288–27298. [Publisher record](https://proceedings.mlr.press/v235/leveni24a.html)

[9] A. Lavin and S. Ahmad, “Evaluating Real-Time Anomaly Detection Algorithms—The Numenta Anomaly Benchmark,” in *2015 IEEE 14th International Conference on Machine Learning and Applications*, 2015, pp. 38–44. [DOI](https://doi.org/10.1109/ICMLA.2015.141)

[10] S. Schmidl, P. Wenig, and T. Papenbrock, “Anomaly Detection in Time Series: A Comprehensive Evaluation,” *Proceedings of the VLDB Endowment*, vol. 15, no. 9, pp. 1779–1797, 2022. [DOI](https://doi.org/10.14778/3538598.3538602)

[11] Z. C. Lipton, “The Mythos of Model Interpretability,” *Communications of the ACM*, vol. 61, no. 10, pp. 36–43, 2018. [DOI](https://doi.org/10.1145/3233231)

[12] M. Armbrust, T. Das, J. Torres, B. Yavuz, S. Zhu, R. Xin, A. Ghodsi, I. Stoica, and M. Zaharia, “Structured Streaming: A Declarative API for Real-Time Applications in Apache Spark,” in *Proceedings of the 2018 International Conference on Management of Data*, 2018, pp. 601–613. [DOI](https://doi.org/10.1145/3183713.3190664)
