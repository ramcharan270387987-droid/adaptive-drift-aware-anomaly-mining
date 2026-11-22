"""Match the entire Spark output sequence against the frozen Python replay."""

from collections import defaultdict
from dataclasses import asdict
from statistics import mean, pstdev

from drift_anomaly.drift_evaluation import match_alarms, summarize_drift
from drift_anomaly.evaluation import AnomalyEvaluation
from drift_anomaly.replay import (
    DEFAULT_WARMUP,
    Prediction,
    ReplayRecord,
    UpdateEvent,
    replay,
)
from drift_streaming.state import encode, factory


def reconcile(streams, methods, events):
    by_key = defaultdict(list)
    for event in events:
        by_key[event["stream_id"], event["method"]].append(event)
    if by_key.keys() != {
        (source.stream_id, method) for source in streams for method in methods
    }:
        raise ValueError("unexpected stream or method in Spark output")
    summaries = {}
    for source in streams:
        for method in methods:
            key = source.stream_id, method
            reference = replay(
                source.observations, lambda method=method: factory(method)
            )
            actual = by_key[key]
            if len(actual) != len(reference.records):
                raise ValueError(f"{key}: sequence length differs from reference")
            prefix = [row.value for row in source.observations[:DEFAULT_WARMUP]]
            model_mean, model_std = mean(prefix), pstdev(prefix)
            refit_number = 0
            reconstructed = []
            for spark, expected, stamp in zip(
                actual, reference.records, source.timestamps, strict=True
            ):
                observation = expected.observation
                prediction = expected.prediction
                update = expected.update
                checkpoint = update.metadata.get("checkpoint", {}) if update else {}
                refit = checkpoint.get("refit")
                expected_output = {
                    "stream_id": source.stream_id,
                    "method": method,
                    "index": observation.index,
                    "timestamp": stamp,
                    "value": observation.value,
                    "warmup": expected.warmup,
                    "score": prediction.score if prediction else None,
                    "prediction": prediction.predicted_anomaly if prediction else None,
                    "drift_alarm": update is not None and update.drift_alarm is True,
                    "adaptation_event": refit is not None,
                    "model_version": None if expected.warmup else refit_number,
                    "mean": None if expected.warmup else model_mean,
                    "std": None if expected.warmup else model_std,
                    "update": asdict(update) if update else None,
                }
                if encode(spark) != encode(expected_output):
                    raise ValueError(
                        f"{key}: output differs at index {observation.index}"
                    )
                if refit is not None:
                    model_mean, model_std = (
                        refit["after"]["mean"],
                        refit["after"]["std"],
                    )
                    refit_number += 1
                reconstructed.append(
                    ReplayRecord(
                        observation,
                        spark["warmup"],
                        None
                        if spark["warmup"]
                        else Prediction(spark["score"], spark["prediction"]),
                        UpdateEvent(**spark["update"])
                        if spark["update"] is not None
                        else None,
                    )
                )
            spark_evaluation, reference_evaluation = (
                AnomalyEvaluation(),
                AnomalyEvaluation(),
            )
            spark_evaluation.add(reconstructed, source.drift_events)
            reference_evaluation.add(reference.scored_records(), source.drift_events)
            metrics = spark_evaluation.summary()
            if metrics != reference_evaluation.summary():
                raise ValueError(f"{key}: metrics differ from reference")
            drift = None
            if method != "static_zscore" and "effective_config" in source.provenance:
                matching = match_alarms(
                    source.drift_events,
                    tuple(row["index"] for row in actual if row["drift_alarm"]),
                    scored_count=reference.stats.scored_count,
                    warmup_last_index=reference.stats.warmup_last_index,
                )
                drift = summarize_drift([matching])
            summaries[f"{source.stream_id}:{method}"] = {
                "observations": len(actual),
                "score_before_update_sequence_exact": True,
                "predicted_anomalies": sum(row["prediction"] is True for row in actual),
                "alarms": sum(row["drift_alarm"] for row in actual),
                "refits": refit_number,
                "post_score_update_calls": reference.stats.scored_count,
                "adwin_updates_after_warmup": reference.stats.scored_count
                if method != "static_zscore"
                else 0,
                "metrics": metrics,
                "synthetic_drift_metrics": drift,
            }
    return summaries
