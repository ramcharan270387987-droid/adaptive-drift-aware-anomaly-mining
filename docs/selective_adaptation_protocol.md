# Proposed selective adaptation framework

This is a design freeze for later implementation and evaluation. The research question, development grid, primary holdout grid, and NAB split remain as specified in the [experimental protocol](experimental_protocol.md) and [dataset protocol](dataset_protocol.md).

## Evidence and primary trigger

Use the existing raw-value ADWIN adapter and its fixed development settings. ADWIN and Page-Hinkley both matched 640 of 640 development transitions. ADWIN produced 142 unmatched alarms versus 1,066 for Page-Hinkley. ADWIN had the longer median delay, 63 versus 36.5 observations. Fewer unmatched alarms make ADWIN the primary candidate for opening a refit proposal. The persistence gate will decide whether to act. Page-Hinkley remains a drift and no-adaptation comparison baseline. [ADWIN report](adwin_baseline.md) · [Page-Hinkley comparison](page_hinkley_baseline.md) · [ADWIN configuration](../configs/experiments/adwin_dev.yaml)

The fixed-schedule control logged 7,500 refits, 1,949 of which used windows containing an injected anomaly. This documents exposure to contaminated training data. The aggregate comparison did not measure the effect of individual injections on refit quality. Frozen Z-score produced identical anomaly scores and decisions with and without drift detection. [Fixed-schedule report](fixed_schedule_adaptation.md) · [No-adaptation control](drift_without_adaptation.md)

The proposed framework combines drift-triggered updates, persistence confirmation, prediction-based filtering, and explicit accounting for update cost. Each component has a corresponding comparison or ablation.

## Frozen policy

All indices below are zero-based on the protocol streams. Durations and lookbacks count observations in replay order.

| Setting | Primary value | Rationale |
| --- | --- | --- |
| Initial Z-score fit | First 256 observations, population mean and standard deviation | Same estimator and prefix as the static and fixed-schedule controls |
| Z-score decision and scale | Anomaly at absolute Z-score ≥ 3.0. Effective scale is max(population standard deviation, 1e-12). | Same decision rule and numerical floor as static Z-score |
| Drift input and operating point | Raw scalar, using the existing ADWIN configuration without retuning | Same signal and settings as the development ADWIN baseline |
| Confirmation checkpoints | 128, 192, and 256 observations after an accepted alarm | Two 64-point blocks fit at the first check. The other checks replace one block at a time. The final deadline bounds waiting to one fixed-schedule window. |
| Persistence gate | Each of the two most recent nonoverlapping 64-point block medians is at least 0.5 effective scales from the alarm-time model mean, in the same direction | Medians reduce sensitivity to isolated extremes. Two blocks require the shift to persist. For unit Gaussian noise, a 64-point median has an approximate standard error of 0.16, making 0.5 a meaningful scale for this design. This is a heuristic, without a statistical error guarantee. |
| Refit data limit | At most 256 observations strictly after the accepted alarm through the checkpoint, inclusive | Uses post-alarm data and applies the same maximum window as the fixed schedule |
| Minimum refit data | 128 retained observations after filtering | Requires at least half of a full refit window and prevents a small filtered subset from replacing the reference |
| Cooldown | 128 observations after a refit | Gives the new model one minimum confirmation span before another proposal can open |
| Budget | At most 15 refits and 3,840 observations passed to refits per 4,096-point stream | Same ceilings as the fixed schedule, excluding the identical warm-up fit |

At a checkpoint, the first block is the 64 observations immediately preceding the last 64, and the second block is the last 64 ending at the checkpoint. Use raw values in both blocks even if Z-score flagged them. Let their medians be `m1` and `m2`, and let `mu_a` and `scale_a` be the model mean and effective scale when the alarm opens the proposal. The gate passes if both medians are at or above `mu_a + 0.5 × scale_a`, or both are at or below `mu_a − 0.5 × scale_a`. Equality passes. Calculate the standard median with the two middle values averaged. The model mean and scale stay fixed throughout the pending proposal.

Construct the candidate from the last 256 observations in the interval `(alarm_index, checkpoint_index]`, or all observations in that interval if fewer are available. Exclude every candidate flagged by its original pre-update Z-score decision. Because the model stays fixed while a proposal is pending, these flags all come from the same reference model. The alarm observation is excluded even if it was scored as nominal. The checkpoint observation is eligible after scoring if its flag is clear. Refit population mean and standard deviation from the retained values only when the gate passes, at least 128 values remain, and both budget counters allow the entire fit. Apply the same numerical floor at the next score. There is no fallback to unfiltered data, threshold relaxation, or partial-budget fit.

A true new-normal value can look anomalous under the old model. Filtering can therefore delay or prevent refits and can bias the surviving reference toward the old mean. Filtering also retains some true anomalies that the model misses. Record both effects in the evaluation. Never use anomaly or drift truth for the proposal, gate, filter, cooldown, or refit.

## Causal state machine

Initialize Z-score and ADWIN with the same first 256 raw values used by their existing adapters. Discard warm-up alarms for proposal and primary drift scoring. Reset framework state and budget counters at each new stream. Process all scored values through ADWIN even while a proposal is pending or cooling down.

1. Score the current raw observation with the existing Z-score state. Record its score and prediction before any update.
2. Update ADWIN with the same raw value and record any alarm at the current index.
3. If idle and within budget, accept an alarm as the sole pending proposal. Snapshot the current mean and effective scale. Start collecting strictly after this observation.
4. If already pending, log any new alarm as a duplicate. Preserve the original alarm index, reference statistics, and checkpoint schedule. Collect the current value and its original prediction. If already in cooldown, log any alarm as suppressed for adaptation. If the budget is exhausted, log any alarm as budget-suppressed. All alarms remain eligible for drift-detection evaluation.
5. At a pending checkpoint, evaluate the two-block persistence gate and candidate data requirement. If both pass and the full refit fits the budget, replace the Z-score statistics after the current prediction. Record the alarm index, checkpoint, block medians, window bounds, candidate and retained counts, before/after statistics, and reason. Clear the proposal and enter cooldown.
6. If persistence or the retained-count gate fails, record the failed criteria and wait for the next fixed checkpoint. After the checkpoint at alarm + 256, close any unfitted proposal and return to idle on the next observation. If an otherwise qualifying refit exceeds the budget, close the proposal at that checkpoint. Suppress future proposals once fewer than 128 fit inputs remain or the refit limit is reached. Do not carry a duplicate alarm forward. An alarm at a checkpoint is classified using the state at the start of that observation, even if the proposal closes there.
7. After a refit at index t, suppress proposal opening for observations t + 1 through t + 128, inclusive. The earliest new proposal is at t + 129. Do not reset ADWIN after a model refit. River's own reset on the update after an alarm remains in force. The same rule applies when a recurring stream returns to an earlier regime. Every new proposal uses the model fitted most recently.
8. Resume scoring with the fitted statistics on the observation after a refit. Keep past records unchanged. Record incomplete proposals at end of stream without fitting them. Log a qualifying refit scheduled at the last observation for cost accounting, including that it affects no later prediction.

## Frozen development candidates and ablations

The primary configuration above stays fixed. The only development sensitivity grid varies the persistence cutoff, including the primary run. Keep blocks, deadlines, filter, cooldown, drift settings, and budget identical. The larger cutoffs test how requiring stronger evidence affects delay and misses. None is selected using development results to replace the primary configuration.

| Candidate | Cutoff in effective-scale units | Role |
| --- | ---: | --- |
| Primary | 0.50 | Frozen comparison arm |
| Stricter | 0.75 | Development sensitivity |
| Strictest | 1.00 | Development sensitivity |

Run candidates and ablations on the existing 500 synthetic development streams only. Each ablation starts from a fresh stream state and uses the same raw signal, score threshold, and budgets. Variants with persistence use the primary cutoff of 0.50.

| Ablation | Refit trigger and data | Cooldown |
| --- | --- | --- |
| ADWIN trigger only, immediate refit | Refit after scoring the alarm observation using the most recent 256 observed raw values, including the alarm observation. Apply no persistence gate or anomaly filter. | None |
| ADWIN + persistence confirmation | Use the primary proposal, checkpoints, gate, and minimum of 128 observations. Fit the unfiltered post-alarm candidate. | None |
| ADWIN + persistence + contamination filtering | Use the same persistence gate and the primary prediction-based filter and minimum retained count. | None |
| Full selective method | Apply the primary proposal, persistence gate, and prediction-based filtering. | 128 observations |

The immediate arm necessarily uses pre-alarm data, and filtering can also affect when enough values are available. Report these timing and window differences alongside the ablation results.

## Comparison and budget accounting

Compare static Z-score, both drift-without-adaptation controls, fixed-schedule Z-score, the full selective framework, and the declared ablations. Use the same signals, seeds, clean/injected pairs, warm-up, labels, score threshold, and causal ordering. The static and drift-without-adaptation controls share identical anomaly predictions. Keep the fixed-schedule baseline unchanged. Its observed budget was 7,500 refits and 1,920,000 individual refit input uses on development data, including 500 terminal updates. Compare refit input uses, including repeated use of a value in overlapping windows, separately from unique observations. Report the unconditional primary comparison even if the selective arm consumes less of the common budget.

- **Prediction quality.** Report confusion counts, precision, recall, F1, false-positive rate, and PR-AUC as average precision where both truth classes are present. Use post-warm-up scores. Report denominators and reasons for unavailable metrics. Include phase-wise false positives, especially post-drift counts and rates, and the existing onset-through-end-plus-256 window clipped before the next onset. Publish pooled, per-stream, per-family, and clean/injected summaries.
- **Alarm and refit delay.** Keep the existing one-to-one ADWIN alarm matching definitions and measure delay from onset. Match refits separately. A refit's opening alarm must fall inside the event's original alarm window, from onset through 128 after transition end, clipped before the next onset. Its refit must fall no later than transition end + 384, also clipped before the next onset. The extra 256 observations allow the maximum confirmation wait. For fixed-schedule refits with no opening alarm, require the refit index alone to lie from onset through the same clipped end + 384. Assign the earliest eligible refit to each transition and assign every refit at most once. For matched refits report onset-to-refit delay and, where applicable, opening-alarm-to-refit delay. Report misses, coverage, and the matched-delay distributions. Warm-up onsets are excluded and reported separately.
- **Update budget.** Report total refits, refits per stream, terminal refits, candidate observations examined, and observations used per refit and in total. Count a refit without an eligible one-to-one match as operationally unnecessary, including all stationary refits and any duplicate refits for a matched transition. Report the number and proportion of streams with at least one such refit across all streams and among streams with any refit. This definition measures protocol alignment and makes no claim about the usefulness of an individual update.
- **Post-adaptation false positives.** For each matched refit, count nominal observations and false positives in the 256 observations starting immediately after the refit. Clip before the next refit or true onset and at stream end. Report coverage, and report unmatched-refit windows separately. Compare methods on the identical indices selected by matched selective refits as a conditional diagnostic. Report that alongside the event-anchored comparison, which includes streams where selective refitting never occurs.
- **Filtering and cost.** Log candidate and filter indices at all checkpoints, including failures. Use truth post hoc to count injected anomalies and nominal observations retained, excluded, and actually used in a fit. Identify repeated consideration of the same observation across checkpoints, and distinguish the checkpoint counts from actual fit input counts. Log suppression and failure reasons. Measure replay wall time after loading and scored observations per second with fit, gate, and update work included. Report peak process RSS, dependency versions, hardware, run settings, and refit budget on the same resources across methods.

Retain the primary holdout success criteria in the experimental protocol. For each eligible stream compute the selective-minus-static difference in false-positive rate within the protocol's transition-through-end-plus-256 window, and separately the difference in isolated-anomaly recall. Average the paired differences over streams with the respective metric defined, and report eligibility counts. For each outcome take the 2.5th and 97.5th percentiles of 10,000 seed-block bootstrap replicates using a fixed bootstrap seed of 1729. Each sampled seed carries all its scenarios and pair members. Apply the existing success criteria once final evaluation is authorized. A smaller update count alone gives no evidence of better predictive performance.

## Schedule-alignment robustness

The existing development onsets 1,024 and 2,048 and primary holdout onsets 1,536 and 2,560 are all multiples of 256. The checked-in holdout presets match those documented settings, and recurring increments of 512 preserve alignment. An abrupt change at one of these indices arrives immediately after a periodic refit. It takes one full period to fit a wholly post-change window. This alignment also constrains onset relative to the initial ADWIN check cadence. It limits what the results say about arbitrary timing.

Predefine a **separate final robustness set**, held back from all implementation decisions and development runs. Use seeds **2,000–2,009** and onsets **1,603 and 2,747**, with residues 67 and 187 modulo 256. Keep the primary holdout shift sizes 1 and 2.25, gradual/incremental widths 192 and 384, recurrence offsets +512 and +1,024, 4,096-point duration, warm-up, Gaussian regimes, and clean/injected pairing and injection rules. Cross the applicable values within each family and include the same stationary controls for these seeds, for 250 pairs total. The existing holdout split stays intact. Freeze the code and decision rules first, then run all primary comparisons on this robustness set only during separately authorized final evaluation and report it separately. Neither robustness nor primary holdout outcomes may change this design.

## Limitations

The gate is designed to notice sustained location shifts in univariate data. Changes in scale or shape can evade it. Slow or transient changes can fail to confirm within the deadline, and cooldown can suppress evidence for a nearby recurrence. Filtering and the minimum retained count can jointly reject a genuine shift, especially when the old model assigns high scores to most new-normal values. Dependence between observations and reused seeds matters for interpretation. NAB has anomaly annotations without the independent drift ground truth needed to score matched adaptation events.
