"""River ADWIN on raw univariate observations."""

import math
from dataclasses import dataclass
from typing import Literal

from river.drift import ADWIN

from drift_anomaly.replay import Prediction, UpdateEvent


@dataclass(frozen=True)
class ADWINConfig:
    delta: float
    clock: int
    max_buckets: int
    min_window_length: int
    grace_period: int
    signal: Literal["raw_value"]

    def __post_init__(self) -> None:
        if type(self.delta) not in (int, float) or not 0 < self.delta < 1:
            raise ValueError("delta must be a finite number in (0, 1)")
        for name, minimum in (
            ("clock", 1),
            ("max_buckets", 1),
            ("min_window_length", 1),
            ("grace_period", 0),
        ):
            value = getattr(self, name)
            if type(value) is not int or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        if self.signal != "raw_value":
            raise ValueError("ADWIN expects signal: raw_value")


class ADWINDetector:
    identifier = "adwin"

    def __init__(self, config: ADWINConfig) -> None:
        self.config = config
        self._detector: ADWIN | None = None

    def fit_initial(self, values: tuple[float, ...]) -> None:
        config = self.config
        self._detector = ADWIN(
            delta=config.delta,
            clock=config.clock,
            max_buckets=config.max_buckets,
            min_window_length=config.min_window_length,
            grace_period=config.grace_period,
        )
        for value in values:
            self.update_one(value)

    def score_one(self, value: float) -> Prediction:
        """Leave the anomaly prediction empty for this drift-only detector."""
        return Prediction()

    def update_one(self, value: float) -> UpdateEvent | None:
        detector = self._detector
        if detector is None:
            raise ValueError("ADWIN must be initialized before updates")
        if not math.isfinite(value):
            raise ValueError("ADWIN observation must be finite")
        detector.update(value)
        if detector.drift_detected:
            return UpdateEvent(drift_alarm=True)
        return None
