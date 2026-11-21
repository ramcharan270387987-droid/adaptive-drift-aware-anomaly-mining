# Causal streaming replay

The replay harness verifies stream-processing mechanics. Its CLI uses a no-op observer that emits no detector score, anomaly decision, or drift alarm. These runs are infrastructure checks and do not constitute scientific validation.

## Run a development stream

From the repository root with the locked environment installed:

```bash
.venv/bin/python -m drift_anomaly.replay \
  --config configs/synthetic/sudden_dev.yaml \
  --output results/replay-sudden-smoke
```

Omit `--output` for a console summary only. Exports use a new directory under Git-ignored `results/` and contain `replay.json`. Use `--warmup` to override the default of **256 observations**, for example on a tiny development fixture. This setting controls replay evaluation. The generator's YAML `warmup` setting controls where anomalies may be injected.

The development entry point loads exactly one explicit YAML file. It requires `split: development` and a seed from the protocol's development range, 0–9. It rejects other configs before generation or detector creation. It has no final-evaluation switch and does not read NAB files. The generic engine accepts a caller-provided observation iterator. Callers are responsible for the provenance of that iterator.

## Detector contract and ordering

Use `replay(observations, detector_factory, warmup=256)` for an existing source or `replay_development(config_path, detector_factory)` for a development synthetic stream. The factory must return a fresh detector for every replay. The `StreamingDetector` protocol separates initialization, scoring, and updating:

1. The engine consumes the warm-up prefix in source order and calls `fit_initial` once with an immutable tuple of raw values. A zero-length warm-up passes an empty tuple. Warm-up rows are retained with no scores or update events.
2. For each subsequent observation, the engine passes only its scalar value to `score_one`. The raw scalar is the current feature. A future detector can derive additional causal features from state accumulated during fit and previous updates. Scoring must read that state without updating it.
3. The engine snapshots the score, decision, and any prediction metadata before calling `update_one` with the current value. The update may record a separate drift alarm or state event at the same index.
4. The source is advanced only after the current update returns. The engine checks for strictly increasing indices and preserves gaps. It processes source order without sorting or reading ahead.

The detector receives neither source iterators nor ground truth. Labels, drift phase, and regime are preserved for later scoring only. These guarantees apply to the inputs and call order supplied by the harness. A detector must respect the interface and cannot be given future data through external state. A source shorter than the requested warm-up is rejected. A source that ends at the warm-up boundary yields zero scored records.

## Result and metric inputs

| Export field | Contents |
| --- | --- |
| `provenance` | Config path and effective generator parameters, split, seed, drift type, replay warm-up length, project version and Git SHA when available, detector identifier, and UTC start time |
| `records[].observation` | Index, raw value, anomaly truth, drift phase, and regime |
| `records[].warmup` | Whether the row is excluded from primary metrics |
| `records[].prediction` | Score, optional anomaly decision, optional pre-update drift alarm, and detector metadata |
| `records[].update` | Optional drift alarm or state metadata produced while updating at the row's index |
| `drift_events` | Synthetic ground-truth event intervals with inclusive start and end |
| `stats` | Observation, warm-up, and scored counts, boundary indices, warm-up anomaly count, elapsed seconds, and total and scored observations per second |

Use `ReplayResult.scored_records()` to obtain eligible rows. Truth and predictions support future precision, recall, F1, and false-positive rate calculations. Truth and ranked scores support PR-AUC. Timed drift alarms and truth intervals support detection delay; if an adapter emits an alarm in either phase, retain its observation index and phase when matching events. Missing scores or labels are represented as null. The harness collects inputs for these metrics and leaves the research calculations to the evaluation stage.

The replay timer covers source iteration, initialization, scoring, updates, and record collection. Synthetic generation, metadata lookup, and export are outside the timer. The scored count tracks invocations of `score_one`, including when the observer emits no score. Console and exported timing describe the harness run only.
