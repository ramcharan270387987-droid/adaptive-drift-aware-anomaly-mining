"""River ADWIN on raw univariate observations."""

from dataclasses import dataclass
from typing import Literal

from river.drift import ADWIN

from drift_anomaly.river_drift import RiverDriftDetector


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


class ADWINDetector(RiverDriftDetector[ADWINConfig]):
    identifier = "adwin"

    def _new_detector(self) -> ADWIN:
        config = self.config
        return ADWIN(
            delta=config.delta,
            clock=config.clock,
            max_buckets=config.max_buckets,
            min_window_length=config.min_window_length,
            grace_period=config.grace_period,
        )
