"""Combine frozen anomaly scoring with independent drift alarms."""

from drift_anomaly.replay import Prediction, StreamingDetector, UpdateEvent
from drift_anomaly.zscore import StaticZScore


class FrozenZScoreWithDrift:
    def __init__(self, anomaly: StaticZScore, drift: StreamingDetector) -> None:
        self._anomaly = anomaly
        self._drift = drift
        self.identifier = f"{anomaly.identifier}+{drift.identifier}"

    def fit_initial(self, values: tuple[float, ...]) -> None:
        self._anomaly.fit_initial(values)
        self._drift.fit_initial(values)

    def score_one(self, value: float) -> Prediction:
        return self._anomaly.score_one(value)

    def update_one(self, value: float) -> UpdateEvent | None:
        """Send the raw value only to the drift detector."""
        return self._drift.update_one(value)
