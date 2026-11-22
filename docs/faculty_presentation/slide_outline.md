# Faculty presentation — 16-slide outline

Use the bullets as slide copy and the linked figures as visual material. The talk and the live demo have separate clocks. [Speaker notes](speaker_notes.md) · [Figure and evidence index](presentation_assets.md)

## 1. Adaptive Drift-Aware Explainable Streaming Anomaly Mining

- Student name [Student name]
- Roll/register number [Roll/register number]
- Department [Department] · Institution [Institution]
- Guide [Guide] · Academic year [Academic year]

## 2. When normal changes, a static detector can keep alarming

**Normal regime A → concept drift → Normal regime B**

- The detector still compares ordinary points in B with the reference learned in A.
- A sustained mismatch can create a burst of false positives.
- An isolated anomaly and a lasting change call for different decisions.

[Matched development example](../academic/figures/04_static_false_positive_burst.png)

## 3. Research question and objectives

> Can explicit concept-drift detection and selective model adaptation reduce false anomaly alarms after distribution changes without reducing sensitivity to genuine anomalies?

- Score each observation before updating the model.
- Separate point predictions, detected change, and refit decisions.
- Measure false alarms, recall, and refit cost against matched baselines.
- Check transfer to NAB and demonstrate the decision trace in Spark.

[Frozen question and protocol](../final_evaluation.md)

## 4. A drift alarm should trigger a decision about refitting

- **Anomaly detection** flags an individual point relative to a reference.
- **Drift detection** signals evidence that the stream has changed.
- **Adaptation** decides when and on which data to change the scoring reference.
- Updating continually or on every alarm can absorb anomalies, use mixed-regime data, and increase refit work.

[Research gap and prior work](../PROJECT_REPORT.md#9-research-gap)

## 5. Two execution paths share one causal policy

- **Research path** — chronological replay → score → update → evaluation with separately joined truth.
- **Online demo path** — streaming source → Spark Structured Streaming → ordered per-stream state. Within each record, anomaly scoring → ADWIN → persistence → selective adaptation.
- **Evidence path** — transactional SQLite state and event journal → explanations → Streamlit dashboard. Sealed comparison and benchmark tables load separately.

[Architecture figure](../academic/figures/01_architecture.png) · [Execution boundaries](../ARCHITECTURE.md)

## 6. Controlled changes and a separate NAB benchmark

- Synthetic families: stationary, sudden, gradual, incremental, recurring.
- Clean and injected versions share the same base signal. Anomalies are isolated, signed spikes.
- Development informed choices. Non-aligned robustness checked a separate grid. Final holdout tested the frozen setup.
- Final synthetic: **500 pairs**, **6,000 injections**, **1,280 transitions**. Final NAB: **5 pinned series**, **13 labeled points**, **13 eligible windows**.
- NAB provides anomaly annotations and has no authoritative concept-drift labels. The final NAB subset includes real traces and artificial controls.

[Regime examples](../academic/figures/02_synthetic_examples.png) · [Final split and design](../final_evaluation.md#experimental-design-and-frozen-methods)

## 7. What each baseline controls for

| Baseline | Why include it |
| --- | --- |
| Static Z-score | Interpretable location/scale reference used by the adaptive policies |
| Static Isolation Forest | Isolation by random partitions, independent of the Z-score decision rule |
| Static LOF | Neighborhood-relative density on unseen observations |
| ADWIN | Adaptive-window change monitor and the selected refit trigger |
| Page–Hinkley | Cumulative mean-change comparator |
| Fixed schedule | Tests the value of selective timing against periodic refits |

Frozen Z-score paired with either drift monitor isolates alarm logging from model change.

[Methods and configurations](../PROJECT_REPORT.md#13-anomaly-detection-baselines) · [Verified references](../academic/REFERENCES.md)

## 8. Selective adaptation waits for evidence of a sustained shift

- Score with the existing absolute Z-score model. Then update ADWIN on the raw value.
- An accepted alarm opens a post-alarm candidate and freezes its reference for the persistence check.
- At offsets **128, 192, and 256**, two recent nonoverlapping **64-point** medians must shift in the same direction by at least **0.50 effective standard deviations** each.
- **Confirmatory full policy:** filter predicted anomalies, require ≥128 retained values and available budget, refit on up to 256 post-alarm points, then apply a 128-point cooldown.
- **Secondary ADWIN + persistence:** same persistence test, unfiltered refits, no cooldown. A refit affects subsequent scores.

[Decision state diagram](../academic/figures/06_state_flow.png) · [Frozen policy](../selective_adaptation_protocol.md)

## 9. Development ablations exposed trade-offs

**Aligned synthetic development only**

- Immediate refit had the fewest event-window false positives among the four ablations but missed **304** injected anomalies.
- Persistence had the fewest post-drift false positives among the ablations and reduced unmatched refits from **142 to 71**.
- Filtering could exclude shifted nominal points flagged against the old reference. The filtered arm matched **481/640** transitions compared with **640/640** with persistence alone.
- Adding cooldown cut unmatched refits from **13 to 5** versus filtering alone. Matched refits stayed at **481**.

[Development ablation tables](../selective_adaptation_development.md)

## 10. Final synthetic holdout — gains versus static Z-score

| Method | Post-drift FP | Pooled recall | Misses | Refits |
| --- | ---: | ---: | ---: | ---: |
| Static Z-score | 216,554 | 96.63% | 202 | 0 |
| Fixed schedule | 24,872 | 97.95% | 123 | 15,000 |
| ADWIN + persistence | **17,205** | 97.72% | 137 | 1,430 |
| Full selective policy | 56,768 | **98.77%** | **74** | 1,326 |

Persistence logged the fewest post-drift false positives. Both selective policies used **about 91% fewer refits** than scheduling (**90.5%** for persistence and **91.2%** for full). The full policy passed the frozen criteria against static Z-score. The table shows the main adaptive comparisons with static Z-score.

[Final synthetic comparison](../academic/figures/07_final_synthetic.png) · [All final methods](../final_evaluation.md#primary-synthetic-holdout) · [Refit efficiency](../academic/figures/09_refit_efficiency.png)

## 11. Paired statistical evidence supports the synthetic comparison

**Full selective policy minus static Z-score**

| Outcome | Paired difference | 95% seed-block bootstrap CI | Holm-adjusted Wilcoxon p |
| --- | ---: | ---: | ---: |
| Event-window false-positive rate | −2.005 pp | [−2.407, −1.591] pp | 0.0000267 |
| Isolated-anomaly recall | +2.222 pp | [+1.233, +3.438] pp | 0.000633 |

- Both frozen criteria passed. The FPR interval is below zero. The lower recall bound exceeds the **−5.0 pp** non-inferiority margin and is above zero.
- **20 seed blocks** preserve pairs and scenarios. These mean paired changes use different weights from pooled rates.
- Event-window FPR uses nominal observations from onset through transition end plus 256, clipped before the next onset.

[Ten prespecified contrasts](../final_evaluation.md#prespecified-statistical-comparisons)

## 12. Final NAB — one extra point detection at high false-positive cost

| Method | Exact points hit | Point false positives | Windows hit |
| --- | ---: | ---: | ---: |
| Static Z-score | 7/13 | 8,190 | 9/13 |
| Fixed schedule | 7/13 | **4,328** | 10/13 |
| ADWIN + persistence | 7/13 | 11,404 | 9/13 |
| Full selective policy | 8/13 | 19,478 | 10/13 |

- Full policy gained **one exact detection** and added **11,288** point false positives versus static.
- Fixed scheduling had the fewest point false positives among the six tested methods. Excess selective-policy flags concentrated in the machine-temperature trace.
- Point and window results use different annotation rules. These five series are descriptive evidence.

[Final NAB comparison](../academic/figures/08_final_nab.png) · [Sealed NAB table](../final_evaluation.md#final-nab)

## 13. Spark Structured Streaming preserved the replay decisions

- **PySpark 4.1.1**, Java 21, CPU-only **local[2]**. Immutable files feed micro-batches.
- Keyed partitioning groups streams. The driver restores index order and applies state by stream and policy.
- Spark source offsets and the SQLite state, journal, and batch receipt jointly support recovery. A committed batch is skipped on retry.
- Exact reference reconciliation across measured workloads, with zero dropped or failed records.
- **3,886 committed rows/s** maximum observed, eight streams, 4,096 target rows/s, 0.25 s trigger, 0.50 s p95 publish-to-commit. **Single-host, finite trial.**

[Benchmark plot](../academic/figures/10_spark.png) · [Full benchmark](../SUSTAINED_STREAMING.md)

## 14. Streamlit makes the score and refit inspectable

- **256:** anomaly prediction, absolute Z ≈6.905, threshold 3.0. **351:** ADWIN candidate opens.
- **479:** persistence passed, 121 retained, waits for 128. **543:** refits with 180 retained values after scoring.
- **544:** version 1 scores the next point. Mean ≈0.0582 → 1.3163. Standard deviation ≈0.9695 → 0.8479.
- The explanation panel shows the scoring reference, refit result, and cooldown separately. This is a development demo trace.

[Verified Streamlit capture](../academic/figures/demo_synthetic.png) · [Recorded event timeline](../academic/figures/05_alarm_persistence_refit.png)

## 15. Findings and limitations

| Findings | Limitations |
| --- | --- |
| Static references produced many false positives after simulated changes. | The setup is univariate with independent Gaussian noise and scripted shifts and anomalies. |
| Selective adaptation delivered synthetic gains versus static Z-score and substantially reduced refit activity versus fixed scheduling. | Final NAB lacked drift labels and showed a false-positive cost for both selective policies versus static Z-score. |
| Local Spark reproduced the reference decisions and recovered state in tested cases. | The CPU trials were finite, used one host, and did not test distributed scaling. |

[Representative failure](../academic/figures/11_nab_failure.png) · [Discussion and limitations](../PROJECT_REPORT.md#25-discussion)

## 16. Conclusion and future work

**The research question is partially supported.**

- The controlled synthetic contrast establishes a benefit versus static Z-score under the frozen protocol. NAB shows a different trade-off.
- **Research:** multivariate streams, adaptive thresholds, richer drift truth, and additional anomaly benchmarks.
- **Engineering:** Kafka integration and distributed Spark deployment with partition and recovery benchmarks.

[Sealed conclusion](../final_evaluation.md#final-conclusion) · [Faculty demo](demo_script.md)
