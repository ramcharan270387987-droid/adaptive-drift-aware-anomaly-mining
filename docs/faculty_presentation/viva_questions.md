# Viva preparation — 60 questions

Give the first sentence as the short answer. Use the supporting detail when an examiner asks how the project applies it. [60-second introduction](project_introduction.md) · [Difficult faculty questions](difficult_questions.md)

## Fundamentals

1. **What is data mining?** It is the systematic extraction and evaluation of useful patterns from data. Here the patterns are unusual observations and persistent distribution changes in a stream.
2. **What is anomaly detection?** It flags observations that deviate from a reference definition of normal behavior. This project evaluates isolated point anomalies.
3. **What is concept drift?** It is a change over time in the data-generating process or a relationship used for prediction. In this unsupervised study the controlled case is a shift in the distribution of the observed scalar values.
4. **How does an outlier differ from drift?** A point outlier is unusual relative to the current reference. Drift concerns a lasting change in the reference distribution. An anomalous point may still occur near a real change.
5. **What is streaming data?** It arrives in time order and is processed incrementally. The detector sees observations as they arrive and carries forward only available state.
6. **How do point anomalies differ from collective anomalies?** One unusual observation can be a point anomaly. A collective anomaly is an unusual sequence or group. The frozen synthetic scoring evaluation labels isolated point injections.
7. **What is a false positive here?** It is an anomaly prediction on a nominal synthetic observation or on a NAB point without an exact anomaly label. A NAB window can include many such points.
8. **Why compare precision and recall?** Recall measures the fraction of labeled anomalies recovered. Precision measures the fraction of flags that correspond to labeled anomalies. A very sensitive detector can still flood operators with alerts.

[Experimental definitions](../experimental_protocol.md) · [Background references](../academic/REFERENCES.md)

## Algorithms and controls

9. **How does Z-score work?** It divides the absolute distance from the fitted mean by the fitted effective standard deviation. The project flags scores at or above 3.0 and floors the scale at 10⁻¹².
10. **How was the static model fitted?** The first 256 observations supplied the population mean and scale. The static model used that same reference for every later observation.
11. **How does Isolation Forest work?** Random partition trees isolate sparse or extreme observations in relatively few splits. The project used 100 trees and a fixed warm-up fit, with no post-warm-up updates.
12. **How does LOF work?** It compares a point’s local density with its neighbors’ densities. The warm-up model used scikit-learn novelty mode with 20 neighbors and Euclidean distance for unseen points.
13. **How does ADWIN work?** It compares means across subwindows of an adaptive window. When the evidence indicates a change, it raises an alarm and discards older history from its window. The project provides raw values with delta 0.002.
14. **How does Page–Hinkley work?** It accumulates deviations from a running mean and signals when a statistic exceeds a threshold. The project uses a two-sided River configuration to detect upward or downward changes.
15. **Why was ADWIN selected as the refit trigger?** On aligned development, both monitors matched all 640 transitions. ADWIN produced 142 unmatched alarms versus 1,066 for Page–Hinkley, with a slower median delay of 63 versus 36.5 observations.
16. **What is the drift-only control?** It updates ADWIN or Page–Hinkley alongside a frozen Z-score model. Both controls exactly reproduced static Z-score anomaly predictions, isolating the effect of the adaptation step.
17. **How does the fixed schedule work?** After warm-up it refits on a trailing window of 256 every 256 observations. The current observation is scored before its scheduled update.
18. **Why include a periodic baseline?** Recent data can restore a useful reference without explicit change detection. The schedule tests whether selective triggering pays off in prediction quality or update cost.

[Model specifications](../PROJECT_REPORT.md#13-anomaly-detection-baselines) · [Verified algorithm references](../academic/REFERENCES.md)

## Proposed method

19. **What happens when ADWIN raises an accepted alarm?** After the anomaly score is emitted, the policy opens a post-alarm candidate and records the alarm-time mean and effective scale.
20. **How is persistence tested?** At post-alarm offsets 128, 192, and 256, two nonoverlapping 64-point raw-value medians must each shift by at least 0.50 effective standard deviations in the same direction from the alarm-time reference.
21. **Why require persistence?** An alarm can reflect a short-lived perturbation or candidate data that still mix regimes. Waiting for two agreeing blocks gives the policy more evidence and can also delay a useful refit.
22. **What observations can enter the full refit?** At most 256 observations strictly after the alarm through the checkpoint. The checkpoint point is eligible after scoring if its original flag is clear.
23. **Why filter flagged points?** Filtering aims to keep anomalies from influencing the new mean and scale. It relies on the old model’s predictions, which can also exclude valid points after a shift.
24. **Why did filtering sometimes hurt?** In aligned development, filtering reduced matched refits to 481/640 from 640/640 for persistence alone and increased post-drift flags. A stale reference may leave fewer than 128 retained points, as the demo illustrates.
25. **What does cooldown do?** It suppresses adaptation proposals for 128 observations after a full-policy refit. Scoring and ADWIN updates continue, and alarms can still be logged.
26. **What limits the update cost?** A cap of 15 refits and 3,840 fit-input uses applies per 4,096-point trace. A qualifying update must fit within the remaining budget.
27. **How do the confirmatory and secondary policies differ?** Both use ADWIN and the same persistence test. The frozen primary full policy adds prediction filtering and cooldown. The development-selected secondary policy uses unfiltered refits without cooldown.
28. **What happens when persistence passes but too few observations survive?** The policy waits for the next checkpoint while one remains. The demo retained 121 at index 479, waited for the 128 minimum, and refit with 180 at 543.
29. **When is a refit visible to scoring?** Only on a later observation. Index 543 was scored with version 0, a refit followed, and index 544 used version 1.
30. **What does the explanation show?** It links a score or update to its scoring-time reference, threshold, alarm, persistence check, retention, and model state changes. It records the policy’s reasons for its own decisions.

[Frozen policy and state transitions](../selective_adaptation_protocol.md) · [Recorded dashboard events](../academic/demo_events.csv)

## Experimental design and statistics

31. **Why use synthetic data?** Planted changes and injected anomalies give independent truth for both false alarms and transition timing. A clean/injected pair shares the same underlying signal.
32. **What synthetic drift types were used?** Stationary is the control. Sudden switches directly, gradual changes the mixture between regimes, incremental moves distribution parameters, and recurring revisits a previous regime.
33. **Why use NAB?** It provides complementary time-series anomaly annotations and windows on pinned benchmark traces. Its final subset includes real series and artificial controls.
34. **Why separate development, robustness, and final holdout?** The chronological warm-up fits each stream’s starting reference before scoring. Development informs design, and a separate non-aligned grid probes timing sensitivity. The untouched primary holdout tests the frozen comparison with reduced selection bias.
35. **What would leakage look like?** Using a future row, using a truth label to choose refit data, or adjusting a threshold after seeing held-out scores would leak evaluation information. The replay scores before updating and joins truth separately.
36. **Why was final holdout run only once?** The complete frozen evaluation serves as a confirmatory check. Repeatedly adjusting and rechecking on the same holdout would turn it into development data. The executed receipt seals the results.
37. **Why run ablations?** They compare immediate refit, persistence, filtering, and cooldown under matched inputs. They expose trade-offs that a single end-to-end comparison cannot localize.
38. **How large was the primary synthetic holdout?** It used 20 seeds, 500 clean/injected pairs of length 4,096, and 3,840,000 scored points per arm after warm-up. It included 6,000 injections and 1,280 planted transitions across the pairs.
39. **How is event-window FPR different from post-drift FP?** Event-window FPR divides nominal flags by nominal points from onset through 256 points after transition end, clipped before the next onset. Post-drift FP is a count over the wider post-drift phase.
40. **Why resample by seed block?** Multiple settings and the clean/injected pair share a seed. Resampling 20 whole blocks preserves that dependence. The 95% intervals use 10,000 bootstrap replicates.
41. **Why use Wilcoxon signed-rank?** It uses the signs and ranks of paired seed-mean differences without a normality assumption for those differences. The tests were two-sided and removed zero differences.
42. **What does the confidence interval mean?** It quantifies uncertainty in the paired effect under seed-block resampling. The synthetic FPR interval fell below zero, and the recall interval was above the frozen −5-point margin.
43. **Why use Holm correction?** Ten prespecified tests create a family of comparisons. Holm adjusts the p-values to control the family-wise error rate.
44. **How does statistical significance differ from practical importance?** A small adjusted p-value provides evidence against the test null. Operational decisions also depend on effect size, alarm burden, recall, and refit cost. For example, the final NAB extra hit came with 11,288 additional point false positives.
45. **Why are the NAB results descriptive?** The final data cover five files and just 13 exact point labels. The study preserved the benchmark’s point and window distinctions and did not extend the synthetic paired tests to NAB.

[Final design, paired statistics and failure cases](../final_evaluation.md)

## Spark, results, and next steps

46. **Why use Spark Structured Streaming?** It provides a streaming execution and checkpointing framework. The local adapter verifies that the same ordered decisions can run in micro-batches and be inspected through the journal.
47. **What is a micro-batch?** It is a bounded group of new input records handled in one trigger. The adapter restores per-stream index order before applying sequential detector state.
48. **How is state managed?** Detector state and journal entries are keyed by stream and method. The model, ADWIN state, pending candidate, counters, positions, and committed decisions are written transactionally to SQLite.
49. **How does checkpoint recovery avoid a duplicate refit?** Spark restores source offsets. If a batch is delivered again after SQLite committed it, the sink checks its durable receipt and avoids reapplying that batch.
50. **Why isolate per-stream state?** Interleaved series can have different levels and changes. Sharing a mean or buffer would corrupt their decisions. A three-partition test kept two traces with a 30-unit offset separated.
51. **What does throughput mean in the benchmark?** Committed rows per second from producer start through the final durable commit. The highest observed rate was 3,886 rows/s on eight streams at the 4,096 target.
52. **Why does that rate leave cluster scalability open?** The measured workloads used one CPU host, local[2], and a bounded driver with SQLite. The trials were finite and the heavier load used a shorter trigger interval.
53. **Why did Isolation Forest achieve high recall and so many false positives?** Its frozen warm-up reference was sensitive to out-of-range values. On synthetic holdout it reached 99.90% recall and flagged 1,520,361 nominal points overall. The study documents that trade-off for the tested configuration.
54. **Why was fixed scheduling competitive?** A trailing-window refit can follow a sustained change without waiting for an alarm or permission to adapt. The schedule also refits during stable periods and its relative performance varies by grid.
55. **Why were there fewer selective refits?** A refit requires a drift trigger and a qualifying candidate, while the schedule refits every 256 points. On synthetic holdout the full policy used 1,326, secondary persistence used 1,430, and fixed scheduling used 15,000.
56. **What was the main NAB limitation?** Both selective methods added point false positives versus static. The excess concentrated in machine temperature. With sparse annotations and no independent drift truth, the observed flags do not reveal the true change mechanism.
57. **What is the main final conclusion?** The research question is partially supported. The full policy met both frozen synthetic criteria versus static Z-score, with substantial refit savings versus fixed scheduling, while the synthetic false-positive benefit failed to transfer to final NAB.
58. **Why do Gaussian synthetic assumptions matter?** Known location shifts with independent Gaussian noise make comparisons interpretable. Heavy tails, seasonality, dependent noise, and changes in covariance can violate that setup.
59. **How could multivariate detection extend the study?** Start with monitored vector scores or feature-specific drift signals, test covariance and missingness changes, and preserve causal scoring and independent evaluation.
60. **What would Kafka or distributed Spark add?** Kafka could provide replayable partitioned ingestion. Distributed deployment would require keyed ordering, a scalable state and sink strategy, fault-injection and load tests before making throughput claims.

[Benchmark and recovery](../SUSTAINED_STREAMING.md) · [Sealed findings and limitations](../final_evaluation.md#final-conclusion)
