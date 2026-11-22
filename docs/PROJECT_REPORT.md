# Adaptive Drift-Aware Explainable Streaming Anomaly Mining

## Abstract

An anomaly detector trained on a stable reference can misclassify a sustained distribution change as many independent anomalies. This project evaluates drift-triggered selective Z-score refitting and provides a local Spark Structured Streaming demonstration. Controlled univariate Gaussian simulations include stationary, sudden, gradual, incremental and recurring conditions with paired clean and injected streams. A separate NAB subset tests anomaly detection under real benchmark conditions. On the primary synthetic holdout, the frozen full policy reduced paired event-window false-positive rate by 2.005 percentage points and improved isolated-anomaly recall by 2.222 points versus static Z-score. Both preregistered criteria passed. On final NAB, the full policy detected one additional labeled point and generated 11,288 additional point false positives. Selective updates used about 91% fewer synthetic refits than a periodic schedule. The local implementation preserves causal scoring, provides transactional recovery and exposes refit reasons in a dashboard.

## Problem statement

An isolated outlier calls for detection. A sustained location change may require updating the detector's reference distribution. Static normalization can flag the new distribution for the rest of the stream. Updating too readily risks incorporating anomalies into the reference, and updating too conservatively can prolong false alarms. We compare these failure modes using streams with independent synthetic annotations for target anomalies and regime changes.

## Research question

Can explicit concept-drift detection and selective model adaptation reduce false anomaly alarms after distribution changes without reducing sensitivity to genuine anomalies?

## Objectives

- Evaluate static models, drift-only controls, periodic updates and selective refitting under shared chronological conditions.
- Separate paired post-drift false-positive effects from isolated-anomaly sensitivity and update cost.
- Validate the frozen method on synthetic primary holdout and assess complementary NAB behavior.
- Deliver a reproducible development-only streaming demo with checkpoint recovery and decision explanations.

## Methodology

The generator crosses predefined seeds, drift times, shift magnitudes and transition widths. Clean and injected versions share the base trace. The primary synthetic holdout contains 1,000 streams per method and 6,000 isolated anomalies, with another non-aligned robustness set characterized separately. NAB development and final series are disjoint and pinned to upstream checksums. NAB point labels and benchmark windows are distinct scoring targets. Its annotations do not establish drift truth.

All detectors use a 256-point warm-up. Baselines include static Z-score, Isolation Forest and novelty-mode LOF. Raw-value ADWIN and Page-Hinkley establish drift-only controls through a frozen anomaly model. The fixed schedule refits every 256 observations. The confirmatory selective policy uses the frozen absolute Z-score threshold 3.0. ADWIN opens a candidate followed by persistence checks at 128, 192 and 256 post-alarm observations. Filtering drops values flagged by the current model, and a 128-point cooldown follows a successful refit. The secondary development-selected policy uses persistence without filtering and cooldown. Detector state changes only after the score for the current observation has been recorded.

The original offline runner produced every scientific result. The engineering adapter uses paced Spark file micro-batches, keyed partitioning, sequential per-key model evaluation, a SQLite transaction for state and events, and a Streamlit interface. Streaming runtime measurements use development inputs only. [Protocol](experimental_protocol.md) · [Architecture](ARCHITECTURE.md)

## Experimental results

| Outcome | Static Z-score | Fixed schedule | Persistence | Full policy |
| --- | ---: | ---: | ---: | ---: |
| Final synthetic post-drift false positives | 216,554 | 24,872 | 17,205 | 56,768 |
| Final synthetic recall | 96.63% | 97.95% | 97.72% | 98.77% |
| Final synthetic refits | 0 | 15,000 | 1,430 | 1,326 |
| Final NAB point detections | 7/13 | 7/13 | 7/13 | 8/13 |
| Final NAB point false positives | 8,190 | 4,328 | 11,404 | 19,478 |

The full policy met the confirmatory comparison against static Z-score. Persistence recorded the fewest synthetic post-drift false positives while detecting fewer isolated anomalies than the full method. Static Isolation Forest and LOF hit all 13 final NAB windows and had high point false-positive counts. Both frozen drift controls reproduced static Z-score's anomaly output. [Complete sealed results](final_evaluation.md)

## Statistical analysis

The unit of inference was the seed, with 20 blocks resampled jointly over paired scenarios. FPR used 960 eligible paired streams and recall used 480. Ten thousand paired seed-block bootstrap replicates gave 95% intervals of −2.407 to −1.591 percentage points for full-policy FPR and +1.233 to +3.438 for recall. Signed-rank tests on seed means gave Holm-adjusted p-values of 0.0000267 and 0.000633. The signed rank-biserial effects were −0.990 and +1.000. Both intervals met their prespecified criteria. NAB was reported descriptively. [All prespecified comparisons](final_evaluation.md#prespecified-statistical-comparisons)

## Discussion

Selective refitting can reduce false alarms and preserve recall after designed shifts. The strength of the result depends on comparator and timing. Persistence beat fixed scheduling on aligned development and primary holdout, while the comparison reversed on non-aligned robustness. Those grids vary in seeds or shift parameters as well as timing. The full policy matched the synthetic confirmatory baseline while generating more post-drift false positives than fixed scheduling. Recurring shifts exposed periods of delayed recovery. On NAB, additional selective false positives were concentrated in the machine-temperature file. The result does not establish a general real-data benefit. Fewer model updates are a direct efficiency benefit, but time also includes scoring, monitoring and checkpoint work.

## Limitations and future work

The simulator uses scalar Gaussian regimes and scripted changes. The five-series NAB final subset has little point-level evidence and no independent drift labels. The persistence candidate was selected on development. The adaptation mechanism updates only Z-score location and scale. The deployment evidence comes from local CPU Spark and bounded arrival tests. Future experiments could study multivariate signals, graph and network streams, learned adaptation policies, richer independent drift labels, additional anomaly benchmarks, Kafka ordering and offset semantics, and distributed state-store recovery. Such work requires separate protocols.
