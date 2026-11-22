"""Static univariate Local Outlier Factor in novelty mode."""

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
from sklearn.neighbors import LocalOutlierFactor

from drift_anomaly.replay import DEFAULT_WARMUP, Prediction

DECISION_RULE = "score > -offset_"


@dataclass(frozen=True)
class LOFConfig:
    n_neighbors: int
    contamination: Literal["auto"] | float
    novelty: Literal[True]
    metric: Literal["euclidean"]
    decision_rule: Literal["score > -offset_"]

    def __post_init__(self) -> None:
        if (
            type(self.n_neighbors) is not int
            or not 1 <= self.n_neighbors < DEFAULT_WARMUP
        ):
            raise ValueError(
                f"n_neighbors must be an integer in [1, {DEFAULT_WARMUP - 1}]"
            )
        if self.contamination != "auto" and (
            type(self.contamination) not in (int, float)
            or not 0 < self.contamination <= 0.5
        ):
            raise ValueError("contamination must be 'auto' or a number in (0, 0.5]")
        if self.novelty is not True:
            raise ValueError("LOF requires novelty: true")
        if self.metric != "euclidean":
            raise ValueError(
                "the static univariate LOF baseline requires metric: euclidean"
            )
        if self.decision_rule != DECISION_RULE:
            raise ValueError(f"LOF requires decision_rule: {DECISION_RULE}")


class StaticLOF:
    identifier = "lof_static"

    def __init__(self, config: LOFConfig) -> None:
        self.config = config
        self.model: LocalOutlierFactor | None = None

    def fit_initial(self, values: tuple[float, ...]) -> None:
        if len(values) <= self.config.n_neighbors:
            raise ValueError(
                "LOF warm-up must contain more observations than n_neighbors"
            )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("LOF warm-up requires finite observations")
        model = LocalOutlierFactor(
            n_neighbors=self.config.n_neighbors,
            contamination=self.config.contamination,
            novelty=self.config.novelty,
            metric=self.config.metric,
            algorithm="kd_tree",
            n_jobs=1,
        )
        model.fit(np.asarray(values, dtype=np.float64).reshape(-1, 1))
        self.model = model

    def score_one(self, value: float) -> Prediction:
        model = self.model
        if model is None:
            raise ValueError("LOF must be fitted before scoring")
        if not math.isfinite(value):
            raise ValueError("LOF observation must be finite")
        # The replay validates the scalar. Query the fitted KD-tree directly and
        # use the locked sklearn novelty-score calculation without array validation.
        distances, neighbors = model._tree.query(
            np.asarray([[value]], dtype=np.float64), k=model.n_neighbors_
        )
        density = model._local_reachability_density(distances, neighbors)
        score = float(np.mean(model._lrd[neighbors] / density[:, np.newaxis]))
        if not math.isfinite(score):
            raise ValueError("LOF produced a non-finite novelty score")
        threshold = -float(model.offset_)
        return Prediction(
            score=score,
            predicted_anomaly=score > threshold,
            metadata={"threshold": threshold},
        )

    def update_one(self, value: float) -> None:
        """Keep the warm-up reference model fixed."""
