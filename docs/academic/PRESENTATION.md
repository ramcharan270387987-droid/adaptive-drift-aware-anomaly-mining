# Faculty presentation outline

## Slide 1. Problem

- A streaming detector must decide before future data arrive.
- A stale reference can turn ordinary measurements into repeated alarms.
- Every unnecessary alarm competes with genuine anomaly signals.

**Visual** — [Anomaly and drift timeline](figures/03_anomaly_drift_timeline.png).
**Speaker note** — Point to the isolated injection and the sustained change separately.

## Slide 2. Why fixed models struggle under drift

- Static Z-score retains its original location and scale.
- A shifted normal regime can repeatedly cross the old threshold.
- Updating too readily can absorb actual anomalies.

**Visual** — [Static false-positive accumulation](figures/04_static_false_positive_burst.png).
**Speaker note** — This is a development example; use the held-out table to support the aggregate effect.

## Slide 3. Research gap

- A drift alarm does not by itself justify replacing the anomaly model.
- Periodic refitting spends updates independently of detected change.
- Prediction quality, update cost, and decision traceability require separate evidence.

**Visual** — Sketch the alarm-to-refit boundary using the [state flow](figures/06_state_flow.png).
**Speaker note** — Attribute established detectors to prior work and describe our contribution as the policy and evaluation.

## Slide 4. Objective and success criteria

- Reduce nominal event-window FPR relative to static Z-score.
- Preserve isolated-anomaly recall with a −5-point non-inferiority margin.
- Compare realized refits and input use against fixed scheduling.

**Visual** — The two [confirmatory intervals](../final_evaluation.md#prespecified-statistical-comparisons).
**Speaker note** — Distinguish the confirmatory full policy from the secondary persistence candidate.

## Slide 5. Architecture

- Offline replay provides the sealed scientific results.
- Spark runs the same causal logic on development streams.
- SQLite commits state and events; Streamlit reads the journal.

**Visual** — [Architecture](figures/01_architecture.png).
**Speaker note** — Explain the two paths and why evaluation labels never enter the detector.

## Slide 6. Synthetic and NAB datasets

- Five simulated families include stationary, sudden, gradual, incremental and recurring.
- Primary synthetic holdout contains 500 clean/injected pairs across 20 seeds.
- The final NAB subset has five series, 13 labeled points, and no independent drift truth.

**Visual** — [Synthetic families](figures/02_synthetic_examples.png) and the [NAB split](../dataset_protocol.md#fixed-development-and-final-evaluation-split).
**Speaker note** — Explain what each dataset can and cannot establish.

## Slide 7. Static baselines

- Z-score gives a direct deviation from a common warm-up reference.
- Isolation Forest isolates points by randomized partitioning.
- LOF compares local densities; high recall can come with severe false positives.

**Visual** — [Table A](TABLES.md#table-a-static-anomaly-baselines).
**Speaker note** — Compare precision or FPR alongside recall.

## Slide 8. Drift detectors

- ADWIN compares behavior across adaptive window segments.
- Page–Hinkley uses cumulative evidence of a mean change.
- Both matched 640 development transitions. ADWIN made fewer unmatched alarms.

**Visual** — [Table B](TABLES.md#table-b-drift-detector-comparison).
**Speaker note** — Page–Hinkley had the shorter median delay in this development grid.

## Slide 9. Selective adaptation

- Score before updating ADWIN.
- Check persistence at offsets 128, 192 and 256.
- Require enough retained values and budget; refit then enter cooldown.

**Visual** — [Policy state flow](figures/06_state_flow.png).
**Speaker note** — Mention the full policy’s filtering and cooldown. Explain why a passed persistence check can still wait.

## Slide 10. Final synthetic results

- The full policy passed both primary criteria.
- Paired FPR changed −2.005 points and recall +2.222 points.
- Persistence had fewer post-drift flags than the full policy and lower recall.

**Visual** — [Final synthetic comparison](figures/07_final_synthetic.png).
**Speaker note** — Event-window FPR effects and broad post-drift counts use different summaries.

## Slide 11. Final NAB results

- Full policy detected 8/13 points versus 7/13 for static.
- Full policy generated 19,478 false positives versus 8,190.
- Benchmark windows and exact points produce different outcomes.

**Visual** — [Final NAB comparison](figures/08_final_nab.png) and [failure case](figures/11_nab_failure.png).
**Speaker note** — The false-positive increase is central to the conclusion. Avoid inferring drift truth.

## Slide 12. Spark and demo

- Local Spark micro-batches use per-stream state and chronological updates.
- The sudden fixture shows alarm 351, wait 479 and refit 543.
- Reconciliation and recovery confirm equivalent outputs across tested runs.

**Visual** — Open the dashboard and [demo timeline](figures/05_alarm_persistence_refit.png).
**Speaker note** — Use the saved evidence if the local run is slow.

## Slide 13. Key findings and efficiency

- Full policy used 1,326 refits versus 15,000 for fixed scheduling.
- Persistence used fewer refit inputs than the full policy.
- Highest measured local commit rate was 3,886 records/s; the higher target built backlog.

**Visual** — [Update cost](figures/09_refit_efficiency.png) and [Spark performance](figures/10_spark.png).
**Speaker note** — Lower update cost is a separate outcome from predictive performance or CPU latency.

## Slide 14. Limitations

- The generator is univariate and uses designed Gaussian regimes.
- NAB is a small subset with sparse exact annotations and no drift labels.
- Local Spark and bounded load trials do not establish cluster throughput.

**Visual** — A three-column summary titled Data, Model and Runtime.
**Speaker note** — Give one failure example per scope where evidence supports it.

## Slide 15. Conclusion

- Confirmatory synthetic evidence supports the full policy versus static Z-score.
- NAB reveals a substantial false-positive cost for selective updates.
- The tested project provides reproducible local replay and auditable decisions.

**Visual** — A final three-line comparison of synthetic effect, NAB trade-off and refit count.
**Speaker note** — End with the scope of the conclusion and direct evaluators to the sealed tables.
