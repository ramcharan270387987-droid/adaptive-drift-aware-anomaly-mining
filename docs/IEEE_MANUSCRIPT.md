# Drift-Triggered Selective Refitting for Explainable Streaming Anomaly Detection

## Abstract

We evaluate an ADWIN-triggered Z-score refit policy against static and scheduled baselines, using synthetic streams with known drift and a fixed NAB subset. On the primary synthetic holdout, the full policy lowered paired event-window false-positive rate by 2.005 percentage points and improved isolated-anomaly recall by 2.222 points versus static Z-score. On final NAB it detected one additional labeled point and increased point false positives substantially. We also verify equivalence, update explanations and recovery in a CPU-only local Structured Streaming implementation.

**Keywords** — Concept drift, streaming anomaly detection, selective adaptation, reproducibility, Apache Spark.

## I. Introduction

A stale reference model can confuse a change in the normal process with an outlier burst. We ask whether explicit drift detection and selective adaptation reduce that error while preserving genuine anomaly sensitivity. The operating-point decision, predictive result, and cost of updating are evaluated separately.

## II. Related Work

NAB supplies a public anomaly benchmark with point and window annotations [1]. **Literature review to complete before submission** — verify primary sources for ADWIN, Page-Hinkley, Isolation Forest, LOF, streaming adaptation and explainability. Add the sources and comparative claims after verification.

## III. Problem Formulation

At index t, score a scalar observation using only the state available before t. An anomaly score may trigger a point alarm. A drift monitor can open a candidate for a reference update, which may change the model only for later points. Report nominal event-window FPR, isolated-anomaly recall, overall point metrics and update cost. Under synthetic truth, measure one-to-one alarm and refit matches. NAB offers a supplementary test of anomaly behavior.

## IV. Proposed Method

Initialize Z-score and the drift machinery from the fixed 256-point warm-up. Score by absolute standardized deviation at threshold 3.0, then stream the raw value into ADWIN. Check direction-consistent median persistence at the predefined offsets. Accept only when there are sufficient retained values and budget. The full policy excludes flagged values and observes a 128-point cooldown. The secondary policy omits those two stages. Replay outputs preserve the scoring-time model and checked candidate evidence. [Frozen method](selective_adaptation_protocol.md)

## V. Experimental Setup

Use the predetermined synthetic scenarios with 20 primary holdout seed blocks and a pinned five-series NAB final split. Compare static Z-score, Isolation Forest, LOF, frozen drift monitors, fixed scheduling, and selective ablations. Use paired bootstrap intervals and the prespecified Holm-adjusted signed-rank analyses. Separately measure local Spark behavior on development workloads.

## VI. Results

The full policy reduced synthetic post-drift FP from 216,554 to 56,768 and improved pooled recall from 96.63% to 98.77%. The paired FPR and recall intervals were [−2.407, −1.591] and [+1.233, +3.438] percentage points. The full policy used 1,326 refits versus 15,000 for fixed scheduling. On NAB it detected 8/13 exact points compared with 7/13 for static, while producing 19,478 versus 8,190 point false positives. [Final tables, intervals and diagnostics](final_evaluation.md)

## VII. Discussion

The confirmatory policy succeeded against static Z-score on controlled primary holdout. Persistence alone reduced synthetic false positives further at the cost of lower recall than the full method. Relative performance against fixed scheduling depends on the design grid. The high NAB false-positive cost places a clear limit on generalization. Stable Spark output with fewer refits is an engineering and update-cost result.

## VIII. Limitations

The experiments use scalar inputs and simple simulated regimes. NAB lacks independent drift truth and the final subset is small. The secondary method was selected on development. The update logic is specific to Z-score. The streaming benchmark is single-host and measures only the tested workload.

## IX. Conclusion

The synthetic confirmatory hypothesis is supported for the declared comparison. Predictive benefits are conditional across benchmarks and comparators. The implementation supports causal replay, recovery and explainable demonstration of both success and failure cases.

## References

[1] Numenta, *Numenta Anomaly Benchmark*, pinned revision `ea702d75cc2258d9d7dd35ca8e5e2539d71f3140`. [Verified upstream repository](https://github.com/numenta/NAB/tree/ea702d75cc2258d9d7dd35ca8e5e2539d71f3140)
