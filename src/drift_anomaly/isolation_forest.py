"""Static univariate Isolation Forest with causal pointwise scoring."""

import math
from bisect import bisect_right
from dataclasses import dataclass
from typing import Literal

import numpy as np
from sklearn.ensemble import IsolationForest

from drift_anomaly.replay import Prediction

FLOAT32_MAX = float(np.finfo(np.float32).max)


@dataclass(frozen=True)
class IsolationForestConfig:
    random_state: int
    n_estimators: int
    contamination: Literal["auto"] | float
    max_samples: Literal["auto"] | int | float
    threshold: float | None = None

    def __post_init__(self) -> None:
        if type(self.random_state) is not int or not 0 <= self.random_state < 2**32:
            raise ValueError("random_state must be an integer between 0 and 2**32 - 1")
        if type(self.n_estimators) is not int or self.n_estimators < 1:
            raise ValueError("n_estimators must be a positive integer")
        if self.contamination != "auto" and (
            type(self.contamination) not in (int, float)
            or not 0 < self.contamination <= 0.5
        ):
            raise ValueError("contamination must be 'auto' or a number in (0, 0.5]")
        if not (
            self.max_samples == "auto"
            or (type(self.max_samples) is int and self.max_samples >= 1)
            or (type(self.max_samples) is float and 0 < self.max_samples <= 1)
        ):
            raise ValueError(
                "max_samples must be 'auto', a positive integer, or a fraction in (0, 1]"
            )
        if self.threshold is not None and (
            type(self.threshold) not in (int, float) or not 0 <= self.threshold <= 1
        ):
            raise ValueError("threshold must be null or a finite number in [0, 1]")


class StaticIsolationForest:
    identifier = "isolation_forest_static"

    def __init__(self, config: IsolationForestConfig) -> None:
        self.config = config
        self.model: IsolationForest | None = None
        self._boundaries: list[float] = []
        self._scores: list[float] = []
        self.threshold: float | None = None

    def fit_initial(self, values: tuple[float, ...]) -> None:
        if not values or any(
            not math.isfinite(value) or abs(value) > FLOAT32_MAX for value in values
        ):
            raise ValueError(
                "Isolation Forest warm-up requires finite float32-range observations"
            )
        samples = self.config.max_samples
        if (type(samples) is int and samples > len(values)) or (
            type(samples) is float and int(samples * len(values)) < 1
        ):
            raise ValueError(
                "max_samples must select at least one and at most the warm-up count"
            )

        model = IsolationForest(
            random_state=self.config.random_state,
            n_estimators=self.config.n_estimators,
            contamination=self.config.contamination,
            max_samples=samples,
            n_jobs=1,
        )
        model.fit(np.asarray(values, dtype=np.float32).reshape(-1, 1))
        boundaries, scores = _score_intervals(model)
        threshold = (
            -float(model.offset_)
            if self.config.threshold is None
            else self.config.threshold
        )
        self.model, self._boundaries, self._scores, self.threshold = (
            model,
            boundaries,
            scores,
            threshold,
        )

    def score_one(self, value: float) -> Prediction:
        if self.threshold is None:
            raise ValueError("Isolation Forest must be fitted before scoring")
        if not math.isfinite(value) or abs(value) > FLOAT32_MAX:
            raise ValueError(
                "Isolation Forest observation must be finite and within float32 range"
            )
        score = self._scores[bisect_right(self._boundaries, float(np.float32(value)))]
        return Prediction(
            score=score,
            predicted_anomaly=score > self.threshold,
            metadata={"threshold": self.threshold},
        )

    def update_one(self, value: float) -> None:
        """Leave the fitted forest fixed after the warm-up prefix."""


def _score_intervals(model: IsolationForest) -> tuple[list[float], list[float]]:
    """Compile constant-score intervals from the fitted one-feature trees."""
    splits = np.concatenate(
        [
            tree.tree_.threshold[tree.tree_.children_left >= 0]
            for tree in model.estimators_
        ]
    )
    boundaries = splits.astype(np.float32)
    # sklearn casts observations to float32, then goes right for value > split.
    # Pick the first representable value on the right of every split.
    rounded_left = boundaries <= splits
    boundaries[rounded_left] = np.nextafter(
        boundaries[rounded_left], np.float32(np.inf)
    )
    boundaries = np.unique(boundaries)
    representatives = np.concatenate(
        (np.array([-FLOAT32_MAX], dtype=np.float32), boundaries)
    )
    scores = -model.score_samples(representatives.reshape(-1, 1))
    if not np.all(np.isfinite(scores)):
        raise ValueError("Isolation Forest produced a non-finite score")
    return boundaries.tolist(), scores.tolist()
