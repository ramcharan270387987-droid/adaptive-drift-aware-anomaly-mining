# Viva preparation

The answers refer to the frozen experiment and distinguish the final data from development and runtime demonstrations.

## Foundations and method

### 1. What is concept drift in this project?

It is a sustained change in the distribution generating the scalar stream. The synthetic transitions explicitly specify changes in regime. On NAB we can report observed alarms and known anomaly windows, with no independent drift labels.

### 2. How does an anomaly differ from drift?

An anomaly is an isolated deviation for this evaluation. Drift changes the reference behavior for multiple observations. Treating every point in a changed normal regime as an anomaly is the false-alarm mechanism under study.

### 3. What is the research question?

Can explicit concept-drift detection and selective model adaptation reduce false anomaly alarms after distribution changes without reducing sensitivity to genuine anomalies?

### 4. Why start with Z-score?

It is inexpensive and directly exposes the old mean, scale, and threshold. This makes a model update easy to audit. The study can attribute changes to the refit policy without the additional decisions required by a complex model.

### 5. How do you compute a Z-score when the reference is constant?

Use the absolute deviation from the pre-score mean divided by the maximum of the population standard deviation and $10^{-12}$. The decision threshold is 3.0.

### 6. Why include Isolation Forest?

Its random partitions represent a different anomaly-scoring mechanism. The static model uses 100 trees and supplies a comparison with the scalar reference score. It remains frozen after warm-up.

### 7. Why include LOF?

LOF compares neighborhood density. It tests whether a local-density reference behaves differently from a global deviation threshold. The 20-neighbor novelty model scores later observations without fitting on them.

### 8. What does ADWIN detect?

It compares statistical behavior across parts of a changing window and can raise a change alarm. Here it receives raw scalar observations. The policy treats its alarm as a signal to collect evidence before considering a refit.

### 9. How does Page–Hinkley differ?

The baseline accumulates evidence of a change in the mean. The implementation monitors both directions. On aligned development the median delay was 36.5 observations, compared with ADWIN’s 63, and it had more unmatched alarms.

### 10. Why choose ADWIN as the trigger?

Both monitors matched 640 development transitions. ADWIN generated 142 unmatched alarms, versus Page–Hinkley’s 1,066. That supported the development choice at the configured operating points.

### 11. Why require persistence?

A single unusual value can produce detector evidence without establishing a sustained shift. The two most recent nonoverlapping 64-point medians must move by at least 0.50 effective standard deviations in the same direction.

### 12. What do the checkpoints control?

Offsets 128, 192 and 256 determine when evidence may be evaluated after an accepted alarm. The candidate can wait for sufficient evidence, and unresolved candidates expire by the last checkpoint.

### 13. Why filter predicted anomalies before refitting?

It reduces the risk of fitting obviously extreme values into the new reference. A true shift can also make valid new-regime points look extreme, so filtering may delay a refit or bias the retained sample.

### 14. What do cooldown and budget accomplish?

The full policy waits 128 observations after a refit before accepting another proposal. Caps of 15 updates and 3,840 refit-input uses on a 4,096-point stream limit how much update work it can perform.

### 15. How do the full and secondary policies differ?

Both use the same ADWIN and persistence threshold. The secondary policy uses unfiltered candidates and has no cooldown. The full policy was frozen as primary; persistence was development-selected as secondary.

### 16. Why not deep learning?

The study isolates update policy with a transparent scalar model and explicit costs. A neural model would add training, architecture, and calibration questions and was outside the frozen comparison. The result does not rank deep learning.

### 17. Can a passed persistence check still fail to refit?

Yes. In the demonstration at index 479, persistence passed and only 121 values survived filtering. At 543, 180 remained and the policy refit. The score at 543 still used the previous model.

## Data and evaluation

### 18. Why use synthetic data?

It supplies independent ground truth for both regime changes and injected anomalies. Paired traces allow comparisons while holding the underlying stream constant outside the injection indices.

### 19. Why also use NAB?

It tests external behavior on a named streaming anomaly benchmark with point and window labels. The project uses a pinned five-series final subset and reports the resulting behavior descriptively.

### 20. What prevents label leakage?

The detector receives index, timestamp, stream ID, and value as needed for input and ordering. Synthetic or NAB truth enters scoring summaries after predictions are committed. Refit filtering uses model predictions.

### 21. What prevents chronological leakage?

Warm-up uses the first 256 observations and is excluded from scored results. At time t the model predicts first, then receives the value for ADWIN and adaptation. A refit can change scoring only from t+1.

### 22. What makes the primary results held out?

Development supported method selection. The primary synthetic seeds 1000–1019 and the final NAB file identities were frozen in advance. One sealed execution produced the final evidence; normal setup only exercises development fixtures.

### 23. How large is the final evaluation?

Synthetic holdout has 1,000 streams and 3,840,000 scored observations per method, with 6,000 injected anomalies and 1,280 transitions. Final NAB has five series, 41,326 scored observations and 13 eligible exact points and windows per method.

### 24. Why do post-drift counts and event-window FPR differ?

The first counts false positives in the broader post-drift phase. The second divides nominal flags by nominal points in bounded event windows through 256 observations after transition end, clipped at the next change.

### 25. What made the confirmatory result successful?

The paired FPR interval lay entirely below zero, and the lower bound of the paired recall interval exceeded the −5-point non-inferiority margin. The observed recall interval also lay above zero.

### 26. Why bootstrap seed blocks?

Streams sharing a seed or clean/injected pair are dependent. Resampling the seed block preserves those relationships and avoids treating millions of observations as independent experimental repeats.

### 27. What do the p-values tell you?

The Holm-adjusted Wilcoxon values for the primary FPR and recall contrasts were 0.0000267 and 0.000633. They supplement the effect sizes and confidence intervals, which show direction, magnitude, and the practical criteria.

### 28. Does the full policy beat fixed scheduling?

It used many fewer updates and had higher final synthetic recall. It also produced 56,768 versus 24,872 synthetic post-drift false positives. Which trade-off is preferable depends on the cost of false alarms and refits.

### 29. How efficient were selective updates?

The full method used 1,326 refits and 225,242 refit inputs versus 15,000 refits and 3,840,000 inputs for fixed scheduling. Monitoring, persistence, and journal work also consume time, so update count alone cannot predict wall-clock speed.

### 30. Why did NAB differ from synthetic data?

NAB has heterogeneous patterns, sparse labels and no independent drift truth. The full policy made 19,478 versus 8,190 static false positives for one extra exact-point detection. Excess flags concentrated in machine temperature. The design does not identify the causal source of every discrepancy.

### 31. What is the difference between an exact-point and window hit?

An exact-point hit requires a prediction at the labeled point. A window hit requires any prediction inside the eligible interval. More alarms can increase window hits and false positives at the same time.

### 32. What did the non-aligned robustness set reveal?

Persistence versus fixed scheduling reversed on the robustness set relative to the primary result. The grids differ in seeds, shift or ramp parameters and alignment. The result establishes comparator dependence, with the individual cause unresolved.

## Systems, explanation and next work

### 33. Why use Spark Structured Streaming?

It provides file ingestion, micro-batch triggering, partitioning, and source checkpointing. The local implementation demonstrates integration with the detector’s sequential state requirements.

### 34. What is a micro-batch?

It is a bounded group of observations collected for one processing trigger. The adapter validates inputs and processes them in source index order within each stream. Batch boundaries leave detector decisions unchanged in the verified comparisons.

### 35. What does checkpoint recovery preserve?

SQLite stores detector state, the cursor, events and the batch receipt transactionally. Spark stores source offsets. On retry, the adapter verifies the prior receipt and skips the already applied update. Tests cover warm-up, an open proposal and cooldown.

### 36. How do you keep simultaneous streams isolated?

Spark partitions by ID and the adapter keys detector state by stream ID and method. A test interleaved streams with distinct baseline means and checked both against independent replay.

### 37. What does the explanation panel actually explain?

It exposes the scoring-time model, score and threshold, alarm disposition, persistence, retained candidates, and before/after refit state. It describes the algorithm’s decision path. It does not diagnose the physical cause of a measurement.

### 38. What is the strongest Spark performance claim?

The highest observed commit rate was 3,886 rows/s in a finite eight-stream local trial. At 8,192 offered rows/s backlog reached 21,300 with shorter triggers. Those trials do not establish a steady-state ceiling or cluster throughput.

### 39. What limitations matter most?

Scalar Gaussian synthetic regimes and 13 NAB point labels constrain scientific generalization. The policy only adapts Z-score. Engineering evidence comes from one local driver and bounded load trials.

### 40. What is the logical next experiment?

Use a new protocol with richer ground-truth drift and multivariate data, and compare additional online baselines. Separately test a multi-host state store and long-running arrivals at fixed trigger intervals to characterize capacity.

[Final evidence](../final_evaluation.md) · [Protocol](../selective_adaptation_protocol.md) · [Figures](FIGURES.md)
