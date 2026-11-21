# NAB dataset protocol

## Source and provenance

Use Numenta's official [Numenta Anomaly Benchmark](https://github.com/numenta/NAB), which identifies itself as NAB v1.1, at commit [`ea702d75cc2258d9d7dd35ca8e5e2539d71f3140`](https://github.com/numenta/NAB/tree/ea702d75cc2258d9d7dd35ca8e5e2539d71f3140). The repository-level [MIT-style license](https://github.com/numenta/NAB/blob/ea702d75cc2258d9d7dd35ca8e5e2539d71f3140/LICENSE.txt) permits use, including academic use, and requires retention of the copyright and permission notices in copies or substantial portions. Acquisition preserves the license. Some streams come from third parties identified in the [upstream corpus notes](https://github.com/numenta/NAB/blob/ea702d75cc2258d9d7dd35ca8e5e2539d71f3140/data/README.md). The repository license is the verified project-level license. Separate terms for redistribution of original third-party data were outside this audit.

The pinned tree contains **58 CSV series** under `data/`. All 58 headers have two fields, `timestamp,value`. Each is univariate, with a single numeric measurement and a timestamp. The categories are artificial without anomalies (5), artificial with anomalies (6), AWS CloudWatch (17), ad exchange (6), known-cause real events (7), traffic (7), and Twitter mentions (10).

Both [`combined_labels.json`](https://github.com/numenta/NAB/blob/ea702d75cc2258d9d7dd35ca8e5e2539d71f3140/labels/combined_labels.json) and [`combined_windows.json`](https://github.com/numenta/NAB/blob/ea702d75cc2258d9d7dd35ca8e5e2539d71f3140/labels/combined_windows.json) are keyed by series path relative to `data/`. Each contains exactly the 58 series keys. Point labels are lists of anomaly timestamps. Window labels are lists of start/end timestamp pairs. An empty list represents an annotated series with zero events. The selected CSVs and point labels use timezone-naive timestamps in `YYYY-MM-DD HH:MM:SS` form, and the selected windows include fractional seconds. Preserve the source wall-clock time and its ordering. A missing or irregular sampling step does not specify a missing measurement value.

## Acquisition and quality audit

From the repository root with the locked environment installed:

```bash
.venv/bin/python -m drift_anomaly.nab fetch
.venv/bin/python -m drift_anomaly.nab audit --output docs/nab_audit.json
```

The [selection manifest](../configs/nab.yaml) pins the revision, split, and SHA-256 digest of every acquired file. The acquisition command requests the ten CSVs, both label files, and the license from the official repository at the pinned revision. It verifies every digest before publishing a new cached file. It records the URL and digest for each file in `data/raw/nab/<revision>/provenance.json`. Repeated acquisition rechecks and reuses intact files. A mismatched cached file causes a failure. Move the suspect copy aside before reacquiring it. The raw tree and its provenance record are ignored by Git.

The audit reads verified raw bytes and reports timestamp bounds, observed sampling intervals in source order, missing and invalid fields, duplicates, backwards steps, and annotation coverage. The [machine-readable quality summary](nab_audit.json) contains aggregate metadata only. Sampling statistics use positive differences between consecutive rows with valid timestamps. Duplicates count occurrences after the first, and non-monotonic steps count negative differences. No rows were modified, sorted, deduplicated, or imputed.

## Fixed development and final-evaluation split

Files were selected to span different domains, observation cadences, event types, and annotation densities. Split assignment is fixed before model implementation. The final set is held out by series and includes real known events, ad traffic, and artificial controls. The corpus and this structural audit are public, so the holdout is a procedural restriction on tuning.

| Split | Path relative to `data/` | Rows | Modal seconds | Point anomalies | Selection rationale |
| --- | --- | ---: | ---: | ---: | --- |
| Development | `realAWSCloudwatch/ec2_cpu_utilization_53ea38.csv` | 4,032 | 300 | 2 | Cloud CPU signal with multiple labeled incidents |
| Development | `realAWSCloudwatch/ec2_disk_write_bytes_1ef3de.csv` | 4,730 | 300 | 1 | Cloud disk I/O with repeated observations and gaps to exercise ingestion rules |
| Development | `realTraffic/speed_6005.csv` | 2,500 | 300 | 1 | Road speed with irregular sampling |
| Development | `artificialWithAnomaly/art_daily_jumpsup.csv` | 4,032 | 300 | 1 | Artificial daily pattern with an upward jump |
| Development | `artificialNoAnomaly/art_daily_no_noise.csv` | 4,032 | 300 | 0 | Labeled-negative daily control for false alarms |
| Final evaluation | `realKnownCause/nyc_taxi.csv` | 10,320 | 1,800 | 5 | Half-hour passenger counts around known calendar and weather events |
| Final evaluation | `realKnownCause/machine_temperature_system_failure.csv` | 22,695 | 300 | 4 | Long industrial temperature stream with documented shutdown and failure events |
| Final evaluation | `realAdExchange/exchange-3_cpc_results.csv` | 1,538 | 3,600 | 3 | Cost-per-click stream with gaps and a different business domain |
| Final evaluation | `artificialWithAnomaly/art_increase_spike_density.csv` | 4,032 | 300 | 1 | Artificial spike-density change, a different annotation pattern from the development jump |
| Final evaluation | `artificialNoAnomaly/art_flatline.csv` | 4,032 | 300 | 0 | Labeled-negative constant signal that exercises zero-variance behavior |

Across **61,943 audited rows**, there were no malformed rows, missing fields, invalid timestamps, or non-finite or invalid numeric values. The CloudWatch disk series had **11 duplicate rows and timestamps**. The industrial temperature series had **12 duplicate timestamps** and **one backwards step**. Positive cadence varied in the disk, road-speed, and ad-exchange files. The largest observed gap was **302,580 seconds** in road speed. All ten series had both label keys. All **18 point labels** matched a unique observation and fell within a supplied window. All 18 windows contained observations. The JSON records the timestamp bounds and interval summaries for each series.

## Limits on interpretation

NAB labels mark benchmark anomalies and associated windows. The exact timestamps and windows encode different scoring targets. Some events have known causes, and the original labels do not exhaustively characterize the underlying process. The corpus lacks independent concept-drift ground truth, so a detector's interpretation of a regime change cannot be validated from these labels. Variable sampling and duplicate timestamps also affect row-based delay and window calculations. Report NAB anomaly results separately from controlled synthetic drift results. The subset is small and was selected for coverage of different conditions, so its scores cannot establish performance on the full NAB benchmark or on multivariate production streams. The quality audit precedes any model evaluation.
