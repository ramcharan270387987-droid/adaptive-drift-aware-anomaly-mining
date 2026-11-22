# Spark Structured Streaming integration

## Execution model

Spark 4.1.1 and PySpark 4.1.1 run in CPU-only `local[2]` mode. The adapter is a separate uv project under `streaming/`. It imports the frozen research detectors directly through an editable path dependency. The original research package, configuration, and lock retain the executable SHA-256 recorded in the final evaluation receipt.

An ordered directory of immutable JSONL chunks feeds a Spark text stream. Spark admits one file per micro-batch. The Python `foreachBatch` callback enforces a 4,096-row bound, parses the strict schema, sorts by stream ID and source index, and applies each stream's observations sequentially. A file may contain one chunk from each of several independent streams. Source producers publish completed files atomically and give consecutive files distinct increasing modification times. Spark's file source schedules the older files first. The adapter checks contiguous indices across files, so a late or missing chunk fails clearly.

The frozen methods are static Z-score, ADWIN + persistence, and the full selective policy. Each stream and method has independent state. The first 256 observations fit the original detectors. For each later row, the adapter captures the score, decision, and scoring-time model statistics before invoking the original detector update. A refit increments the model version for subsequent rows. ADWIN state, pending persistence checkpoints, candidate positions and values, cooldown and budget all live inside the original detector object. Historical alarm and refit events live in the output journal.

SQLite durably checkpoints the warm-up prefix, fitted detector, source cursor, and output journal in one transaction with the Spark batch ID and a digest of its normalized input. Spark's checkpoint records file offsets. A local filesystem lock allows a single driver per query directory. Keep the checkpoint and SQLite database together on the same host. On a retry after SQL commit but before Spark acknowledgment, the receipt digest confirms the exact batch and prevents duplicate state changes or output rows. A changed retried batch, mismatched runtime fingerprint, or missing checkpoint half fails. The checkpoint serializes Python/River objects and is intended for trusted local state with the same adapter and dependency versions.

## Input and output

The demo supports all development synthetic families and the NAB series named in the committed development split. It uses the existing generator and checksum-verified NAB loader. The benchmark sources use the same code and report their effective source configurations. A normalized input row has this schema.

```json
{"stream_id":"sensor-a","index":0,"timestamp":"2000-01-01T00:00:00.000000","value":2.4}
```

Use increasing contiguous zero-based indices for each stream and ISO 8601 wall time with six fractional digits. Synthetic timestamps are artificial seconds from the example epoch. NAB preserves source wall time. Equal timestamps are allowed with distinct increasing indices. Timestamp reversals, duplicate or skipped indices, malformed JSON, duplicate field names, extra fields, and missing or non-finite values fail the batch. Ordering inside a file is immaterial. An empty callback can acknowledge an empty batch without changing detector state. Runtime data and checkpoints live under ignored `results/`.

The output key is `(stream_id, method, index)`. Every prediction row includes timestamp, raw value, warm-up flag, continuous anomaly score, Boolean anomaly prediction, drift-alarm and adaptation-event flags, pre-update model version, mean, standard deviation, and the detector update event. Scoring fields are null during warm-up. The refit row carries the previous model version with the adaptation flag set. The next row uses the new version. Ground truth never appears in Spark input or the SQLite journal. Reconciliation adds source truth to evaluation records after scoring. Synthetic drift metrics use the original matching rule. NAB has no independent drift truth.

## Run locally

Run from the repository root with Python 3.12 and Java 21.

```bash
uv sync --project streaming --locked --python 3.12
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
streaming/.venv/bin/python -m drift_streaming.benchmark \
  --series sudden --batch-sizes 64 256 --output results/spark-demo
```

For NAB, use `--series realAWSCloudwatch/ec2_cpu_utilization_53ea38.csv`. For an existing directory of valid, immutable chunks, the following command drains available files and resumes the same query on later invocations. Publish any new files in chronological order before the next drain.

```bash
streaming/.venv/bin/python -m drift_streaming.spark \
  --source results/spark-demo/batch-64/input \
  --work results/spark-demo/batch-64/query
```

## Benchmark and replay equivalence

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 streaming/.venv/bin/python \
  -m drift_streaming.benchmark --benchmark --batch-sizes 256 64 16 1 \
  --output results/spark-benchmark
```

The benchmark drains four 896-row workloads in a single query per batch size. They are stationary, sudden, recurring, and a prefix of the pinned NAB CloudWatch CPU development file. The synthetic benchmark uses the existing development templates with a fixed short horizon of 896. Sudden and recurring onset is 320, and recurring transitions are spaced by 192 observations. This gives the local benchmark scored drift and refit events even at the finest micro-batch size. The final evaluation grid is separate. The benchmark does not open final synthetic or NAB inputs.

The table measures one local run per configuration in the same Spark session, in the order shown. The first query includes Spark query startup and warm cache effects differ across sizes. The JVM starts before query timing. Input throughput counts source records once, even though each feeds three methods. Per-batch processing time covers collecting the Spark batch and committing SQLite. End-to-end latency starts when the query begins with the entire backlog available and ends when SQLite commits the row. It therefore includes time queued behind earlier files. Source generation, replay reconciliation and output export are outside the timer. RSS is the sampled sum across the Python and JVM process tree at 100 ms intervals, and CPU is reported as a percentage of one core.

The reconciliation report checks all rows against the original causal replay. It requires exact scores, predictions, timestamps, raw values, drift flags, refit events and their metadata, pre-update mean/std and model version, as well as exact pointwise metrics. It also requires identical output rows across batch sizes. SQLite, prediction JSONL, reconciliation and per-batch timing JSON, benchmarks and source/runtime manifests are written to the output directory.

| Rows/stream | Batches | Drain s | Input rows/s | Batch p50 / p95 ms | Backlog latency p50 / p95 s | Peak RSS MiB | CPU % of one core |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 256 | 4 | 3.42 | 1,048.7 | 158.5 / 631.2 | 2.81 / 3.38 | 589 | 156.3% |
| 64 | 14 | 2.81 | 1,274.9 | 58.7 / 124.5 | 1.52 / 2.78 | 662 | 157.2% |
| 16 | 56 | 8.22 | 435.8 | 34.2 / 86.4 | 4.60 / 7.96 | 785 | 112.3% |
| 1 | 896 | 113.02 | 31.7 | 21.4 / 52.8 | 55.37 / 107.26 | 1011 | 85.1% |

Each configuration produced 10,752 prediction rows from 3,584 inputs, with 7,680 post-score update calls, including 5,120 scored ADWIN updates. Across both adaptive methods there were eight alarm records and five refits. In the sudden stream each adaptive method recorded one alarm and one refit. In recurring drift the methods each recorded three alarms, and persistence made three refits while the full policy made none. Both benchmark runs produced byte-identical predictions across the four sizes. The identical prediction JSONL sequence has SHA-256 `96e60471374014d2472e8199a10384493496f50d5c7246c693a46962f3005a19`. The runtime manifest records the exact adapter and dependency-lock fingerprints. The run used OpenJDK 21.0.13 and Python 3.12.14 on Linux with an AMD EPYC 9V74 and three visible logical CPUs.

A separate full-length NAB smoke run replayed all 4,032 rows of the CloudWatch CPU file. All three methods matched the reference across 12,096 output rows and evaluated the same two labeled points.

The batch-64 run had the best observed throughput in this run order. The batch-1 case spent much more wall time in trigger and checkpoint overhead despite lower median processing time per batch. This comparison is one bounded local run with different numbers of files and triggers per size. It does not establish an optimal production batch size.

## Verification and limitations

Run both suites from the repository root.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 streaming/.venv/bin/python \
  -m pytest -q tests streaming/tests
.venv/bin/ruff check .
.venv/bin/ruff format --check .
uv lock --project streaming --check
uv sync --project streaming --locked --check
```

All 256 tests passed, including 15 new Spark or adapter tests. The tests cover malformed and labeled input rejection, timestamp ties, duplicate indices, backward timestamps, rollback, empty batches, and exact reconciliation across Spark batch sizes. The restart test injects a failure after durable SQL commit during warm-up and another while an ADWIN proposal is pending. Spark retries the batches, and the journal remains duplicate-free. A separate two-JVM check resumes a sudden stream after index 383 with an outstanding proposal and reproduces refit index 543 and every reference output.

This is a single-host, univariate, file-based replay. Spark schedules input micro-batches while SQLite and sequential detector evaluation run on the driver. The callback deliberately limits batch rows and retains an output journal that grows with the input. The local checkpoint is neither a shared cluster state store nor a portable interchange format. A missing input file at the tail needs a source manifest or watermark to detect. Kafka, sustained live-arrival latency, multi-host fault tolerance, and distributed scalability were outside this milestone.
