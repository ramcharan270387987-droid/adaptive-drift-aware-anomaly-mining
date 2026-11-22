# Experimental protocol

## Research question

Can explicit concept-drift detection and selective model adaptation reduce false anomaly alarms after distribution changes without reducing sensitivity to genuine anomalies?

Use controlled synthetic streams to measure drift detection and post-change behavior. Use NAB to measure anomaly detection on a fixed subset of benchmark streams. NAB has no independent drift ground truth for this purpose. A benchmark anomaly label can describe a sustained change, so it cannot establish whether the proposed system correctly recognized drift on real data. The NAB split is fixed in [the dataset protocol](dataset_protocol.md).

## Controlled synthetic streams

Generate scalar streams of 4,096 observations indexed from zero. Independently sample the baseline regimes **A** and **B** from normal distributions with means 0 and Δ, respectively, and standard deviation 1. Run each drift scenario with and without injected anomalies using a common clean trace for the pair. Include stationary controls with and without injected anomalies.

| Scenario | Baseline generation | Ground-truth transition |
| --- | --- | --- |
| Sudden | A before onset, B beginning at onset | Start and end are the first B index |
| Gradual | Each sample in a transition is drawn from A or B. The probability of choosing B rises linearly from 0 to 1. | Inclusive first and last index of the mixture transition |
| Incremental | The mean rises linearly from 0 to Δ, with variance fixed throughout. | Inclusive first and last index of the mean ramp |
| Recurring | A → B → A → B with abrupt changes. Change indices are onset, onset + 512, and onset + 1,024. | Three ordered instantaneous transitions, with explicit pre/post regime for each |

A gradual mixture can produce draws from two distinct regimes at an intermediate time. An incremental ramp instead moves the center of a single distribution. Outside the defined transitions, draws follow the active stationary regime.

| Split | Seeds | Onset | Shift Δ | Gradual or incremental width |
| --- | --- | --- | --- | --- |
| Development | 0–9 | 1,024 or 2,048 | 1.5 or 3 | 128 or 256 observations |
| Final evaluation | 1,000–1,019 | 1,536 or 2,560 | 1 or 2.25 | 192 or 384 observations |

Cross the relevant settings for each scenario, omitting width for instantaneous changes and irrelevant settings for stationary controls. For each stream with injection, choose 12 positions with a minimum separation of 16 indices and none in the initial 256 samples. For gradual and incremental drift, place three injections inside the transition and select the remaining positions outside it. For abrupt changes and recurrence, place three injections in the first 64 observations after the first change, excluding exact change points. Draw additions of +6 or −6 in baseline standard-deviation units with equal probability. Use separately seeded draws for the clean trace and the injection schedule/signs, recording the seed, RNG and version with the generated data. Reuse the same clean trace across each with/without injection pair and across methods. Injection positions are anomaly truth. Regime changes alone are normal under the synthetic design.

Save metadata for each stream with its split, seed, length, drift type (or `none`), ordered drift intervals with inclusive start and end, distribution family and parameters before and after each interval, transition rule, and injected anomaly indices. Save the generator revision and full scenario configuration alongside the metadata. See the [synthetic generator guide](synthetic_streams.md) for the CLI, presets, and output schema.

## Development and holdout

- **Development** uses only the synthetic development grid and the five NAB development files. Use these to select preprocessing, detector parameters, thresholds, and adaptation settings.
- **Final evaluation** uses the held-out synthetic grid and five NAB final-evaluation files. Freeze the code, configuration, metrics, and preprocessing rules before opening holdout values for modeling. The data quality audit reveals structural metadata for both splits. Keep holdout values, labels, and any scores out of development decisions.
- Replay each series in source order as an independent stream. Reset state across files. Use a shared causal warm-up of 256 observations and score subsequent observations. Report any annotations excluded by warm-up. For each scored observation, make the decision before updating model state using that observation. Keep labels out of preprocessing and online updates. Freeze any preprocessing or threshold policy selected during development. When a method needs a per-stream initial fit, use the warm-up observations only. Where a future invalid row or duplicate forces a cleaning decision, define the rule on development data and log its application on each series.

## Baselines and comparisons

Anomaly baselines are a Z-score detector, Isolation Forest, and Local Outlier Factor in novelty-detection mode. Fit the latter two only on past observations available under the assigned adaptation policy. Drift baselines are ADWIN and Page-Hinkley. Start with a common scalar detector input selected on development data and report which signal each drift baseline receives.

Compare these policies for the same anomaly detector, with the same per-stream warm-up, feature inputs, and initial settings:

| Policy | Behavior |
| --- | --- |
| Static anomaly detector | Hold the initial anomaly model fixed |
| Drift detector without adaptation | Emit drift alarms while holding the anomaly model fixed |
| Fixed adaptation | Update on a predetermined schedule, using a trailing window available at update time |
| Selective adaptation | Combine anomaly score, drift evidence, and persistence over a window. Classify isolated anomalies separately from sustained changes and update selectively. |

Select the fixed schedule, permitted window lengths, and drift detector parameters on development streams. Match update data budgets where applicable and report realized update counts and sizes. Record score, decision, drift and persistence evidence, and update reason to make decisions inspectable.

The [selective adaptation protocol](selective_adaptation_protocol.md) freezes the proposed policy, ablations, and separate timing-robustness set before implementation.

## Metrics and success criteria

- **Anomaly detection.** Report precision, recall, F1, and false-positive rate using scored points. Use point labels for the primary NAB analysis. Also report a separate NAB window hit rate with at most one hit per labeled window. Aggregate confusion counts across streams and show per-stream results. Report PR-AUC as average precision on ranked scores when both classes are present. Mark undefined metrics as unavailable and report the denominator. Report false-positive rate among nominal observations during and in the 256 samples after each synthetic shift, clipping at the next shift where applicable.
- **Drift detection.** On synthetic data, match the first available alarm at or after each transition onset and through 128 samples after its end, clipped before the next onset. Match alarms one-to-one. Report matched transitions divided by true transitions, alarms left unmatched per 1,000 scored observations, and delay from onset in samples for matched transitions. Report delay and detection rate together so misses stay visible. Count every scored alarm on stationary controls as false.
- **System cost.** Report end-to-end streaming replay wall time after loading, scored observations per second, and peak process RSS. Include adaptation in the timed path, document hardware, versions, and measurement procedure, and use the same resources across policies.

The primary comparison is selective adaptation versus the static detector on held-out synthetic drift streams. Use paired per-stream comparisons of post-change false-positive rate and isolated-anomaly recall. Success requires a lower false-positive rate, with the paired 95% interval for the difference below zero, and an isolated-anomaly recall difference whose lower bound is above −0.05 absolute. Resample held-out seeds as blocks to account for scenarios and pairs sharing a seed. Report the other policy comparisons and results by drift family, including effect sizes and uncertainty. Treat NAB results as complementary anomaly evidence. The small, public NAB subset limits generalization. The [static Z-score report](zscore_baseline.md) and the [Isolation Forest comparison](isolation_forest_baseline.md) cover development streams only.
