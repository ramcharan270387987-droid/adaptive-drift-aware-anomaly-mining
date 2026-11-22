# Single-host local Spark benchmark

Spark and PySpark 4.1.1 ran on Java 21 in CPU-only `local[2]` mode. The producer paced immutable files and Spark shuffled input by stream ID into two local partitions. The driver sequenced state updates and durably committed one transaction per file. The matrix used the frozen full policy with replicated development sudden streams under separate IDs. The 512 and 2,048 input rows/s conditions used 896 observations per stream. The 4,096 and 8,192 conditions used eight full 4,096-row traces for a longer load comparison.

Publication latency measures from starting a file publication through the corresponding durable commit, including any backlog. Batch processing covers the callback, shuffle and SQLite work. Committed throughput counts all rows over the elapsed time from producer start to last durable commit. CPU is sampled process-tree time as a percentage of one core. RSS sums sampled process memory. SQLite size includes the event journal and any active sidecars. Serialized detector state alone was 2.0–19.2 KiB depending on workload. All runs reconciled exactly to independent reference replay, with zero failed or dropped records.

| Streams | Target / arrival rows/s | Interval s | Committed rows/s | Batch p50 / p95 ms | Commit p95 s | Peak backlog rows | Peak RSS MiB | CPU % | SQLite MiB | Refits |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 512 / 446 | 0.50 | 213 | 184 / 1042 | 2.41 | 896 | 648 | 128 | 0.34 | 1 |
| 1 | 2,048 / 1,755 | 0.25 | 952 | 202 / 263 | 0.44 | 896 | 687 | 125 | 0.34 | 1 |
| 4 | 512 / 512 | 0.50 | 485 | 86 / 173 | 0.50 | 256 | 770 | 70 | 1.30 | 4 |
| 4 | 2,048 / 2,042 | 0.25 | 1,793 | 85 / 137 | 0.33 | 1,024 | 803 | 111 | 1.30 | 4 |
| 8 | 512 / 512 | 0.50 | 505 | 65 / 147 | 0.32 | 256 | 860 | 49 | 2.58 | 8 |
| 8 | 2,048 / 2,046 | 0.25 | 1,804 | 64 / 147 | 0.54 | 1,024 | 846 | 86 | 2.58 | 8 |
| 8 | 4,096 / 4,087 | 0.25 | 3,886 | 101 / 214 | 0.50 | 3,072 | 939 | 100 | 11.61 | 8 |
| 8 | 8,192 / 8,176 | 0.10 | 3,304 | 96 / 264 | 5.79 | 21,300 | 954 | 91 | 11.58 | 8 |

The highest measured commit rate was 3,886 rows/s at the 4,096 target. That run had 2,048 queued rows when publishing ended and drained them in 0.41 seconds. At 8,192 offered rows/s, the 0.10-second triggers increased scheduling pressure. The backlog reached 21,300 rows and took 5.91 seconds to drain after publishing ended. The 4,096 and 8,192 runs use different trigger intervals, so these trials locate overload in the tested workload/interval settings without isolating the effects of rate and interval. A longer soak test is needed to determine a steady-state ceiling. The first short one-stream run includes cold startup overhead. The comparison does not establish cluster performance.

A separate three-partition test interleaved a normal trace and a copy offset by 30. Their scoring means remained 30 units apart, and both outputs matched independent replay. Recovery tests interrupt after durable SQL commit during warm-up, a pending proposal and active cooldown. The same input receipt is checked and skipped before resuming output. Local SQLite corruption and multi-host recovery are outside this benchmark. [Architecture](ARCHITECTURE.md) · [Reproduction](REPRODUCIBILITY.md)
