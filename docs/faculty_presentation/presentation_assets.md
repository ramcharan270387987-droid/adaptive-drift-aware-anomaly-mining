# Verified presentation assets

Use the original figures at their existing paths. Keep axes, legends, and scope labels visible when cropping around a panel.

| Visual | Slide or demo stage | Suggested caption and scope |
| --- | --- | --- |
| [Architecture diagram](../academic/figures/01_architecture.png) | Slide 5 | Research replay and local Spark development demo share the causal policy. |
| [Synthetic drift example](../academic/figures/02_synthetic_examples.png) | Slide 6 | Five development stream families. The markings show planted boundaries or intervals. |
| [Static false-positive burst](../academic/figures/04_static_false_positive_burst.png) | Slide 2 | Cumulative nominal flags on the same sudden development trace. This illustrates behavior on one trace. |
| [ADWIN and adaptation timeline](../academic/figures/05_alarm_persistence_refit.png) | Slide 14 and offline replay | Recorded alarm at 351, persistence wait at 479, and refit at 543. The next score uses the new reference. |
| [Selective state flow](../academic/figures/06_state_flow.png) | Slide 8 | Gates and transitions of the full policy. |
| [Final synthetic comparison](../academic/figures/07_final_synthetic.png) | Slide 10 | Sealed synthetic anomaly and post-drift outcomes. |
| [Final NAB comparison](../academic/figures/08_final_nab.png) | Slide 12 | Sealed point results and window hits. |
| [Refit-efficiency comparison](../academic/figures/09_refit_efficiency.png) | Slide 10 or questions | Refit counts and input uses on the primary synthetic holdout. |
| [Spark benchmark](../academic/figures/10_spark.png) | Slide 13 | Commit throughput and latency on the tested local CPU host. |
| [Synthetic dashboard capture](../academic/figures/demo_synthetic.png) | Slide 14 | Verified Streamlit development replay with synthetic overlay. |
| [NAB dashboard capture](../academic/figures/demo_nab.png) | Offline NAB stage | Verified CloudWatch CPU development replay. |
| [Research dashboard capture](../academic/figures/demo_research.png) | Offline results transition | Verified dashboard view of recorded results. |
| [NAB failure case](../academic/figures/11_nab_failure.png) | Slide 15 or questions | In one machine-temperature window, secondary persistence retained the window hit and added 115 point false positives relative to static Z-score. |

## Evidence map

| What to verify | Primary reference |
| --- | --- |
| Frozen question, thresholds, split, metrics, exact results and failure cases | [Sealed evaluation](../final_evaluation.md) · [Executed receipt](../../configs/final_evaluation.yaml) · [Portable sealed summary](../evidence/delivery.json) |
| Post-drift counts, point metrics, refit cost and Spark rows | [Publication tables and CSVs](../academic/TABLES.md) |
| Scope of the one explicitly development-only ablation slide | [Development ablations](../selective_adaptation_development.md) · [Robustness check](../pre_final_validation.md) |
| Research contribution and consistency with the written submission | [README](../../README.md) · [Status](../STATUS.md) · [Project report](../PROJECT_REPORT.md) · [IEEE manuscript draft](../IEEE_MANUSCRIPT.md) |
| Benchmark scope, system chronology and explanation trace | [Benchmark protocol and results](../SUSTAINED_STREAMING.md) · [Architecture](../ARCHITECTURE.md) · [Recorded event CSV](../academic/demo_events.csv) · [Dashboard guide](../DEMO.md) |
| Figure and source attribution | [Existing figure ledger](../academic/FIGURES.md) · [Verified bibliography](../academic/REFERENCES.md) · [Citation audit](../academic/CITATION_AUDIT.md) |

The paired FPR contrast on slide 11 covers an event window. The post-drift counts on slide 10 cover the wider post-drift phase. NAB point false positives are tied to exact point labels, and the window-hit metric is separate.
