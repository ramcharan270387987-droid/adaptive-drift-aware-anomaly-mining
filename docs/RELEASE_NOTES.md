# v1.0.0-rc1 release notes

This release candidate packages the verified implementation and academic evidence for faculty review. It preserves the sealed execution at `7e72ccb61297d58567fb1e41c077e6b537e9d897`.

## Study and implementation

- The project asks whether selective adaptation can lower false anomaly alarms after distribution changes while preserving sensitivity to genuine anomalies.
- The offline study compares static Z-score, Isolation Forest, LOF, drift-only controls, fixed scheduling, and selective ADWIN variants. The full policy scores before updating, checks median persistence, filters predicted anomalies, and applies a cooldown after refit.
- The primary synthetic holdout used 1,000 traces per method. The final NAB subset consists of five checksum-pinned series with 13 scored point labels and 13 eligible windows.
- The full policy passed the two synthetic confirmatory criteria versus static Z-score. Paired event-window FPR fell 2.005 percentage points and paired recall rose 2.222 points. Final NAB gained one exact-point detection and added 11,288 false positives. NAB provides no independent drift ground truth.

## Demonstration and reproducibility

- Spark Structured Streaming processes ordered development micro-batches in CPU-only local mode. SQLite stores detector state, predictions, and retry receipts.
- The Streamlit dashboard shows the live journal, model state, and retrospective explanations. Its research views read the tracked, portable summary.
- The academic package includes the report, IEEE-style manuscript, verified bibliography, figures, exact-value tables, presentation outline, demo script, and viva guide.
- Both Python projects use their own uv lock. The release was checked from a detached worktree with fresh environments and a fresh cache. Normal setup uses development data and sealed summaries.

## Known limitations

The study uses scalar Gaussian synthetic regimes, Z-score adaptation, and a small NAB subset. Spark was exercised locally under finite load. The app may return an HTTP 500 for the favicon under the pinned Streamlit middleware; the demo and result views were verified granularly. Author details, institution-specific forms, and venue formatting remain student actions.

[Release verification](RELEASE_VERIFICATION.md) · [Submission checklist](SUBMISSION_CHECKLIST.md) · [Sealed results](final_evaluation.md)
