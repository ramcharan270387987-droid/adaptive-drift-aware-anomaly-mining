# Project status

The repository is functionally complete for the specified faculty demonstration and project report. The frozen study and engineering demonstrator have separate reproducibility paths.

## Completed

- Reproducible Python environment and pinned NAB development/final splits.
- Deterministic synthetic generator, causal replay, static Z-score, Isolation Forest and LOF.
- ADWIN and Page-Hinkley drift baselines, drift-only controls, fixed-schedule adaptation and selective ablations.
- Aligned development, non-aligned robustness, NAB development and the sealed untouched primary synthetic and final NAB studies.
- Spark file replay, sustained arrival simulation, keyed partitioning, per-stream state, and checkpoint recovery.
- Explainable event and model-state views, synthetic evaluation overlays, sealed research tables and measured Spark benchmarks in Streamlit.
- Portable result summaries, final artifact packaging, architecture, faculty demo checklist, project report and IEEE-style manuscript scaffold.

## Verified

- 263 tests passed, including the original research suite and local Spark and Streamlit integration.
- Byte-exact replay reconciliation on the checked Spark workloads. An interleaved partition test kept two distinct model means separated, and checkpoint tests recovered warm-up, pending candidates and active cooldown without duplicated outputs.
- Two end-to-end Streamlit development runs completed on sudden drift and NAB. The sudden fixture reported its ADWIN alarm at 351 and refit at 543.
- Chromium verified page startup, research and benchmark tables, both replay starts, rendered plots, synthetic-overlay gating, and reset. The app tests selected the refit and checked its explanation and pause behavior.
- Original research fingerprint and SHA-256 artifact hashes match the executed receipt. Runtime results and cached data remain ignored.

## Final scientific conclusions

The frozen full policy passed both paired synthetic criteria versus static Z-score. On final NAB it gained one exact-point detection and added 11,288 point false positives. Both selective approaches cut refit counts by about 91% against the fixed schedule on synthetic holdout. The research conclusion is supported on controlled synthetic inputs, with comparator- and dataset-dependent limits. [Final evaluation](final_evaluation.md)

## Known limitations

The research is univariate, with Gaussian synthetic regimes and Z-score adaptation. The NAB subset is small and lacks independent drift truth. The Spark adapter uses a local driver and a local SQLite journal. The measured capacity is an operating point for a finite CPU test. The dashboard pauses display while Spark continues processing. The manuscript is a scaffold with a clearly marked literature-review placeholder.

## Remaining optional work

Extend the research to multivariate and graph/network streams, richer drift truth and learned policies. Evaluate Kafka and multi-host state stores under a new engineering protocol. For journal submission, verify and complete the literature review, apply the venue template, and obtain faculty approval.
