"""River Page-Hinkley on raw univariate observations."""

import math
from dataclasses import dataclass
from typing import Literal

from river.drift import PageHinkley

from drift_anomaly.river_drift import RiverDriftDetector


@dataclass(frozen=True)
class PageHinkleyConfig:
    min_instances: int
    delta: float
    threshold: float
    alpha: float
    mode: Literal["up", "down", "both"]
    signal: Literal["raw_value"]

    def __post_init__(self) -> None:
        if type(self.min_instances) is not int or self.min_instances < 1:
            raise ValueError("min_instances must be a positive integer")
        for name in ("delta", "threshold", "alpha"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
        if self.delta < 0:
            raise ValueError("delta must be non-negative")
        if self.threshold <= 0:
            raise ValueError("threshold must be positive")
        if not 0 < self.alpha <= 1:
            raise ValueError("alpha must be in (0, 1]")
        if self.mode not in ("up", "down", "both"):
            raise ValueError("mode must be up, down, or both")
        if self.signal != "raw_value":
            raise ValueError("Page-Hinkley expects signal: raw_value")


class PageHinkleyDetector(RiverDriftDetector[PageHinkleyConfig]):
    identifier = "page_hinkley"

    def _new_detector(self) -> PageHinkley:
        config = self.config
        return PageHinkley(
            min_instances=config.min_instances,
            delta=config.delta,
            threshold=config.threshold,
            alpha=config.alpha,
            mode=config.mode,
        )
