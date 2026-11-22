# 60-second project introduction

> When a stream’s normal behavior changes, a static anomaly detector can keep flagging ordinary readings. My project asks whether we can reduce those false alarms without missing genuine anomalies. The system scores each reading with the current Z-score model, then uses ADWIN to look for change. Before refitting, it checks that the change persists and that enough usable observations remain. Spark runs the same logic during the development replay, and the dashboard explains each decision using the recorded model state.
>
> On the sealed synthetic holdout, the full policy lowered paired event-window false-positive rate by about two percentage points and raised recall by about 2.2 points versus static Z-score. It also used about 91% fewer refits than fixed scheduling. On final NAB, it detected one more exact anomaly point but added 11,288 point false positives. The research question is partially supported. The benefit is clear in the controlled synthetic comparison, while transfer to real streams remains limited.

[Slides and evidence](slide_outline.md) · [Sealed conclusion](../final_evaluation.md#final-conclusion)
