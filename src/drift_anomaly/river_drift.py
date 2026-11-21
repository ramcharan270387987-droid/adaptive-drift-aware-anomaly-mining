"""Causal scalar adapter for raw-value River drift detectors."""

import math
from abc import ABC, abstractmethod

from river.base import DriftDetector

from drift_anomaly.replay import Prediction, UpdateEvent


class RiverDriftDetector[Config](ABC):
    def __init__(self, config: Config) -> None:
        self.config = config
        self._detector: DriftDetector | None = None

    @abstractmethod
    def _new_detector(self) -> DriftDetector: ...

    def fit_initial(self, values: tuple[float, ...]) -> None:
        self._detector = self._new_detector()
        for value in values:
            self.update_one(value)

    def score_one(self, value: float) -> Prediction:
        """Leave the anomaly prediction empty for this drift-only detector."""
        return Prediction()

    def update_one(self, value: float) -> UpdateEvent | None:
        detector = self._detector
        if detector is None:
            raise ValueError("drift detector must be initialized before updates")
        if not math.isfinite(value):
            raise ValueError("drift detector observation must be finite")
        detector.update(value)
        if detector.drift_detected:
            return UpdateEvent(drift_alarm=True)
        return None
