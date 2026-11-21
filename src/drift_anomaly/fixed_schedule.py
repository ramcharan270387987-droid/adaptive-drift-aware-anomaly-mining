"""Periodically refit Z-score using trailing observations in replay order."""

import math
from collections import deque
from dataclasses import dataclass

from drift_anomaly.replay import DEFAULT_WARMUP, Prediction, UpdateEvent
from drift_anomaly.zscore import StaticZScore, ZScoreConfig


@dataclass(frozen=True)
class FixedScheduleConfig(ZScoreConfig):
    adaptation_interval: int = 256
    window_size: int = 256
    warmup: int = DEFAULT_WARMUP

    def __post_init__(self) -> None:
        super().__post_init__()
        for name in ("adaptation_interval", "window_size", "warmup"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.window_size > self.warmup + self.adaptation_interval:
            raise ValueError("window_size must fit by the first scheduled refit")


class FixedScheduleZScore:
    identifier = "zscore_fixed_schedule"

    def __init__(self, config: FixedScheduleConfig) -> None:
        self._model = StaticZScore(config)
        self.config = config
        self._history: deque[float] = deque(maxlen=config.window_size)
        self._since_refit = 0

    def fit_initial(self, values: tuple[float, ...]) -> None:
        if len(values) != self.config.warmup:
            raise ValueError("initial prefix must match the configured warmup")
        self._model.fit_initial(values)
        self._history.clear()
        self._history.extend(values)
        self._since_refit = 0

    def score_one(self, value: float) -> Prediction:
        return self._model.score_one(value)

    def update_one(self, value: float) -> UpdateEvent | None:
        if self._model.mean is None or self._model.std is None:
            raise ValueError("fixed-schedule Z-score must be fitted before updating")
        if not math.isfinite(value):
            raise ValueError("refit history requires finite observations")
        self._history.append(value)
        self._since_refit += 1
        if self._since_refit < self.config.adaptation_interval:
            return None

        before = {"mean": self._model.mean, "std": self._model.std}
        self._model.fit_initial(tuple(self._history))
        self._since_refit = 0
        return UpdateEvent(
            metadata={
                "refit": {
                    "before": before,
                    "after": {"mean": self._model.mean, "std": self._model.std},
                    "window_size": len(self._history),
                }
            }
        )
