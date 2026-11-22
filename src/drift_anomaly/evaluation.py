"""Point-level anomaly metrics and known-drift diagnostics for replay."""

import math
from collections.abc import Iterable
from dataclasses import dataclass, field

from sklearn.metrics import average_precision_score

from drift_anomaly.replay import ReplayRecord
from drift_anomaly.synthetic import DriftEvent

PHASES = ("stationary", "pre_drift", "in_transition", "post_drift")


@dataclass
class NominalAlarms:
    fp: int = 0
    tn: int = 0

    def add(self, predicted: bool) -> None:
        self.fp += predicted
        self.tn += not predicted

    def summary(self) -> dict:
        nominal = self.fp + self.tn
        return {
            "fp": self.fp,
            "tn": self.tn,
            "nominal_count": nominal,
            "false_positive_rate": self.fp / nominal if nominal else None,
        }


@dataclass
class AnomalyEvaluation:
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0
    labels: list[bool] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)
    nominal_by_phase: dict[str, NominalAlarms] = field(
        default_factory=lambda: {phase: NominalAlarms() for phase in PHASES}
    )
    drift_window_alarms: NominalAlarms = field(default_factory=NominalAlarms)

    def add(
        self, records: Iterable[ReplayRecord], events: tuple[DriftEvent, ...] = ()
    ) -> None:
        windows = [
            (
                event.start,
                min(event.end + 256, events[i + 1].start - 1)
                if i + 1 < len(events)
                else event.end + 256,
            )
            for i, event in enumerate(events)
        ]
        for record in records:
            if record.warmup:
                continue
            obs = record.observation
            prediction = record.prediction
            if (
                obs.anomaly_label is None
                or prediction is None
                or prediction.predicted_anomaly is None
            ):
                raise ValueError(
                    f"anomaly truth and prediction are required at index {obs.index}"
                )
            label = obs.anomaly_label
            predicted = prediction.predicted_anomaly
            self.labels.append(label)
            if prediction.score is not None and math.isfinite(prediction.score):
                self.scores.append(prediction.score)
            if label:
                self.tp += predicted
                self.fn += not predicted
            else:
                self.fp += predicted
                self.tn += not predicted
                if obs.drift_phase in self.nominal_by_phase:
                    self.nominal_by_phase[obs.drift_phase].add(predicted)
                if any(start <= obs.index <= end for start, end in windows):
                    self.drift_window_alarms.add(predicted)

    def merge(self, other: "AnomalyEvaluation") -> None:
        self.tp += other.tp
        self.fp += other.fp
        self.tn += other.tn
        self.fn += other.fn
        self.labels.extend(other.labels)
        self.scores.extend(other.scores)
        for phase, alarms in self.nominal_by_phase.items():
            alarms.fp += other.nominal_by_phase[phase].fp
            alarms.tn += other.nominal_by_phase[phase].tn
        self.drift_window_alarms.fp += other.drift_window_alarms.fp
        self.drift_window_alarms.tn += other.drift_window_alarms.tn

    def summary(self) -> dict:
        unavailable = {}

        def ratio(name, numerator, denominator, reason):
            if denominator:
                return numerator / denominator
            unavailable[name] = reason
            return None

        positive = self.tp + self.fn
        negative = self.tn + self.fp
        predicted_positive = self.tp + self.fp
        precision = ratio(
            "precision", self.tp, predicted_positive, "no predicted anomalies"
        )
        recall = ratio("recall", self.tp, positive, "no true anomalies")
        f1 = ratio(
            "f1",
            2 * self.tp,
            2 * self.tp + self.fp + self.fn,
            "no true or predicted anomalies",
        )
        fpr = ratio("false_positive_rate", self.fp, negative, "no nominal observations")
        pr_auc = None
        if not positive or not negative:
            unavailable["pr_auc"] = "average precision requires both truth classes"
        elif len(self.scores) != positive + negative:
            unavailable["pr_auc"] = (
                "finite scores are required for every scored observation"
            )
        else:
            pr_auc = float(average_precision_score(self.labels, self.scores))
        return {
            "scored_count": positive + negative,
            "anomaly_count": positive,
            "tp": self.tp,
            "fp": self.fp,
            "tn": self.tn,
            "fn": self.fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "false_positive_rate": fpr,
            "pr_auc": pr_auc,
            "unavailable": unavailable,
            "false_positives_by_phase": {
                phase: alarms.summary()
                for phase, alarms in self.nominal_by_phase.items()
            },
            "drift_window": self.drift_window_alarms.summary(),
        }
