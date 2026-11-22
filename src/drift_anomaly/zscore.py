"""Static univariate Z-score detector."""

import math
from dataclasses import dataclass
from statistics import mean, pstdev

from drift_anomaly.replay import Prediction


@dataclass(frozen=True)
class ZScoreConfig:
    threshold: float
    minimum_std: float = 1e-12

    def __post_init__(self) -> None:
        for name in ("threshold", "minimum_std"):
            value = getattr(self, name)
            if (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"{name} must be a finite positive number")


class StaticZScore:
    identifier = "zscore_static"

    def __init__(self, config: ZScoreConfig) -> None:
        self.config = config
        self.mean: float | None = None
        self.std: float | None = None

    def fit_initial(self, values: tuple[float, ...]) -> None:
        if not values or not all(math.isfinite(value) for value in values):
            raise ValueError(
                "Z-score warm-up requires finite observations and cannot be empty"
            )
        fitted_mean = mean(values)
        fitted_std = pstdev(values)
        if not math.isfinite(fitted_mean) or not math.isfinite(fitted_std):
            raise ValueError("Z-score warm-up produced non-finite statistics")
        self.mean, self.std = fitted_mean, fitted_std

    def score_one(self, value: float) -> Prediction:
        if self.mean is None or self.std is None:
            raise ValueError("Z-score detector must be fitted before scoring")
        if not math.isfinite(value):
            raise ValueError("Z-score observation must be finite")
        scale = max(self.std, self.config.minimum_std)
        difference = value - self.mean
        score = abs(
            difference / scale
            if math.isfinite(difference)
            else value / scale - self.mean / scale
        )
        if not math.isfinite(score):
            raise ValueError(
                "Z-score is non-finite for the observation and fitted scale"
            )
        return Prediction(
            score=score,
            predicted_anomaly=score >= self.config.threshold,
            metadata={"threshold": self.config.threshold},
        )

    def update_one(self, value: float) -> None:
        """Leave the fitted warm-up statistics fixed."""
