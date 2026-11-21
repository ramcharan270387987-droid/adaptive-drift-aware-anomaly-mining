# Adaptive Drift-Aware Explainable Streaming Anomaly Mining

**Research question**

Can explicit concept-drift detection and selective model adaptation reduce false anomaly alarms after distribution changes without reducing sensitivity to genuine anomalies?

The NAB subset has been acquired and audited for data quality. The static Z-score, Isolation Forest, and LOF baselines have been evaluated on the same synthetic development streams. Holdout evaluation is pending.

The planned workflow uses Codex Cloud for development and quick CPU tests, GitHub for version control, and Kaggle's free CPU runtime for experiments that exceed the practical limits of Codex Cloud.

- [Environment verification](docs/environment.md)
- [NAB provenance, quality audit, and dataset split](docs/dataset_protocol.md)
- [Experimental protocol](docs/experimental_protocol.md)
- [Synthetic stream generator](docs/synthetic_streams.md)
- [Causal streaming replay](docs/replay.md)
- [Development baseline and reproduction command](docs/zscore_baseline.md)
- [Development Isolation Forest baseline and comparison](docs/isolation_forest_baseline.md)
- [Development LOF baseline and three-detector comparison](docs/lof_baseline.md)
- [Repository layout and experiment workflow](docs/execution_workflow.md)
