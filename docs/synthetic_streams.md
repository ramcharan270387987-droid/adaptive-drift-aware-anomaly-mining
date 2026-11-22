# Synthetic stream generator

The generator creates controlled, univariate Gaussian streams with ground truth defined by the generation parameters. Use them to test whether a method distinguishes regime changes from injected anomalies. These streams are synthetic and must never be described as real-world validation. The [experimental protocol](experimental_protocol.md) defines the scientific design and full development and holdout grids.

## Run from the repository root

```bash
.venv/bin/python -m drift_anomaly.synthetic \
  --config configs/synthetic/sudden_dev.yaml \
  --output data/generated/sudden_dev/injected

.venv/bin/python -m drift_anomaly.synthetic \
  --config configs/synthetic/sudden_dev.yaml \
  --output data/generated/sudden_dev/clean \
  --clean
```

Use new output directories. The CLI publishes both files together and rejects an existing destination. Keep repository exports under the Git-ignored `data/generated/`. In Python, use `generate_stream(config)` for one stream, or `generate_pair(config)` to return the clean and injected streams from the same seed and drift settings.

## Drift types and labels

All indices are zero-based. Drift event start and end are inclusive. Each drifting stream has at least one observation before the first event and after the last.

| Type | Distribution and state |
| --- | --- |
| `sudden` | State A switches to B at `drift_start`. The first B observation is the entire transition. |
| `gradual` | During the specified interval, each observation selects A or B independently. The probability of B increases linearly from 0 to 1. The recorded regime is the selected mixture component. |
| `incremental` | The mean and standard deviation interpolate linearly between the endpoints. The active regime is `ramp` throughout the interval. The protocol configs keep standard deviation fixed at 1. |
| `recurring` | A → B → A → B, with three instantaneous transitions separated by `recurrence_period` observations. |
| `none` | Stationary A throughout, with no drift events. |

The YAML keys `n_observations`, `seed`, `pre_mean`, `pre_std`, `post_mean`, and `post_std` specify the stream. Specify `drift_start` for drifting streams and `drift_duration` for gradual or incremental drift. With fixed duration `d`, the last index of either transition is `drift_start + d - 1`. Recurrence uses an onset and spacing, with a protocol spacing of 512.

## Anomaly injection

Set `anomaly_count` or `anomaly_fraction`. The latter is multiplied by the stream length and rounded down. Omitting both creates a clean stream. Each injection adds or subtracts `anomaly_magnitude × pre_std` with equal probability. The default magnitude is 6. Injections respect the initial `warmup` and configured `min_anomaly_separation`. The generator rejects a count or placement quota that cannot fit.

- `protocol` reserves `priority_anomaly_count` of the injections for the transition in gradual or incremental drift, or the interval immediately following the first abrupt change for sudden and recurring drift. The canonical configs place three injections in that region and nine outside it. The abrupt region runs from onset + 1 through onset + 64 by default. Stationary streams have no priority region.
- `exclude_transition` excludes every drift interval, including instantaneous change indices.
- `anywhere` applies the warm-up and spacing rules without a priority region.

Event boundaries are excluded by default for all placement policies. `allow_boundary_anomalies: true` permits them under `protocol` and `anywhere`. The full-interval exclusion still applies under `exclude_transition`. Injection leaves the base trace and its drift annotations intact. The clean and injected streams have identical values at every unmodified index.

## Presets and reproducibility

[The preset directory](../configs/synthetic/) contains one development and one holdout YAML per drift type and for the stationary control. The development presets use seeds 0–4 and the holdout presets use 1000–1004, with onset, shift, and duration values from their respective protocol grids. These are representative presets. The protocol specifies the complete grid. Use development presets and the development grid for tuning. Reserve holdout presets and the holdout grid for final evaluation after the implementation and settings are frozen.

NumPy's PCG64 generator uses separate child seeds for noise, gradual mixture draws, injection positions, and injection signs. Repeated generation with the same code, locked environment, and configuration produces identical observations, labels, and exports. The metadata records the NumPy version and SHA-256 of the generator source. Use the locked environment when reproducing artifacts.

## Export schema

`stream.csv` has the following columns.

| Field | Meaning |
| --- | --- |
| `index` | Zero-based integer sample index |
| `value` | Observation with any configured injection applied |
| `anomaly_label` | 1 for an injected anomaly and 0 for a nominal observation |
| `phase` | `stationary`, `pre_drift`, `in_transition`, or `post_drift` |
| `regime` | A, B, or `ramp`. After the first event, this identifies the active state even when recurrence returns to A. |
| `mean`, `std` | Parameters of the normal draw before injection. In gradual drift these refer to the realized component. |

`metadata.json` contains a schema version, generator revision, split, seed, length, drift type, full parameters, RNG metadata, exact injection indices, and ordered drift events with bounds, source and destination regimes, endpoint distributions, and transition rules. The CSV and metadata include ground-truth fields for scoring. Feed only past and current observation values and permitted time information to detectors during evaluation.
