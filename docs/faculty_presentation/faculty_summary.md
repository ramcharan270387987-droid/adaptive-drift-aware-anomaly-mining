# Faculty evaluation summary

**Adaptive Drift-Aware Explainable Streaming Anomaly Mining**

**Problem and gap.** A static detector can repeatedly flag ordinary values after a distribution shift. Point anomaly scoring, detecting sustained change, and deciding when to refit are separate problems. Refitting after every alarm can learn transient anomalies or consume unnecessary updates.

**Method and contribution.** The detector uses a 256-observation warm-up and scores each new point before updating. Raw-value ADWIN opens a candidate. Two recent block medians must confirm a sustained shift. The frozen full policy filters predicted anomalies, requires enough retained points and budget, then refits the Z-score mean and scale and enters cooldown. The secondary policy uses persistence without filtering or cooldown. The contribution is a reproducible evaluation of these policy choices and a journal that makes individual decisions auditable.

**Design and baselines.** Aligned development, non-aligned robustness, and final holdout serve distinct roles. The final synthetic grid contains 500 clean/injected pairs, five drift families including a stationary control, and 6,000 injections. Final NAB contains five pinned series, 13 point annotations, and 13 eligible windows. Baselines cover static Z-score, Isolation Forest, LOF, ADWIN and Page–Hinkley drift-only controls, fixed scheduling, and selective ablations.

**Strongest final result.** Against static Z-score, the full policy reduced paired synthetic event-window FPR by **2.005 percentage points** and increased recall by **2.222 points**, satisfying both frozen criteria. It used **1,326 refits** versus **15,000** with scheduling. The secondary policy had the fewest post-drift false positives, **17,205**, compared with **56,768** for the full policy.

**Negative NAB result.** The full policy detected **8/13** exact points versus **7/13** for static Z-score, while false positives increased from **8,190** to **19,478**. Fixed scheduling produced **4,328** false positives. NAB supplies anomaly annotations and lacks independent drift truth.

**Operational evidence.** PySpark **4.1.1** processed development micro-batches in order, isolated stream state, and reproduced reference decisions. The transactional journal supports checkpoint recovery and Streamlit explanations. The highest observed local commit rate was **3,886 rows/s**. Distributed performance remains open.

**Conclusion.** The research question is partially supported. The findings apply most directly to controlled univariate synthetic drift and the specified static comparator. The tested NAB subset shows a substantial false-positive trade-off.

[Project report](../PROJECT_REPORT.md) · [IEEE manuscript draft](../IEEE_MANUSCRIPT.md) · [Sealed evaluation](../final_evaluation.md) · [Spark benchmark](../SUSTAINED_STREAMING.md)
