# Academic delivery audit

The final evaluation receipt records execution revision `7e72ccb61297d58567fb1e41c077e6b537e9d897` and research tree SHA-256 `a75d7c3c968a8263c1e2047cde34a603d3fb4bb7ea026c8eb68737b374f9a723`. The six sealed artifact digests and the executable fingerprint were checked again for this delivery. The academic package reuses final results without re-executing holdout.

| Check | Outcome |
| --- | --- |
| Numerical reconciliation | All 40 rows in Tables A–G checked against the sealed final outputs or the archived development drift and Spark results. CSV contains the recorded values. |
| Figures | Eleven numbered figures and three demo fallback screenshots. Four reporting PNGs were copied byte-for-byte. New example visuals use development data or the published update counts. |
| Bibliography | Twelve references checked against publisher, proceedings, or author-hosted publication metadata. Report and manuscript use the same cited numbering and bibliography. |
| Terminology and scope | Research question, threshold, warm-up, checkpoints, split counts, final effects, benchmark conditions, and execution revision were cross-checked. Event-window FPR, post-drift FP totals, exact NAB points, and window hits remain separate. |
| Tests | 263 passed across research, Spark and Streamlit. |
| Document checks | Pandoc parsed the delivered Markdown, local link and anchor checks passed, and both PDFs rendered with extractable evidence and references. |
| Repository checks | Git whitespace check and a targeted indexed-file scan for common credentials passed. Raw data, caches, and generated delivery exports stay ignored. |

[Academic delivery index](README.md) · [Executed receipt](../../configs/final_evaluation.yaml)
