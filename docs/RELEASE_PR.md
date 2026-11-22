# Release candidate v1.0.0-rc1 for faculty review

## Summary

- Deliver the reproducible causal streaming anomaly study, including static, drift-only, fixed-schedule and selective adaptation controls.
- Preserve the sealed synthetic holdout and NAB execution at `7e72ccb61297d58567fb1e41c077e6b537e9d897`. The full policy met both synthetic criteria against static Z-score. On final NAB it detected one more exact anomaly and made 11,288 additional point false positives.
- Deliver the CPU-only local Spark adapter with chronological per-stream scoring, transactional SQLite state and retry receipts, plus the Streamlit dashboard and explanations.
- Deliver the report, complete IEEE-style draft with verified references, exact-value tables, figures, faculty outline, timed demo, offline fallback and viva guide.
- Add release notes, a clean-environment verification record, and the faculty submission checklist.

## Verification

A fresh detached worktree installed both locks with an empty cache, downloaded only the five pinned NAB development files and their metadata, ran the core example, reconciled the four-stream Spark demo, and served the portable sealed summary. The full suite passed with 263 tests. Ruff, dependency consistency, sealed checksums, citation and link checks, indexed credential/file audits, and Git whitespace checks passed. The timed Chromium rehearsal and offline evidence are recorded in `docs/RELEASE_VERIFICATION.md`.

## Scope and review

The predictive conclusions apply to controlled synthetic streams and the small NAB subset. NAB lacks independent drift truth. Spark measurements describe finite local workloads. Streamlit’s favicon response can fail without affecting the demo. Student/institution metadata and venue formatting await completion. Review this PR before merging. The protected holdout was not rerun, and no sealed research behavior, source configuration, or metrics changed.
