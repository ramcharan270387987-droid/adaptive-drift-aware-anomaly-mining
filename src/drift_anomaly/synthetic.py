"""Generate and export deterministic, labeled univariate drift streams."""

import argparse
import csv
import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

import numpy as np
import yaml
from numpy.typing import NDArray

DriftType = Literal["none", "sudden", "gradual", "incremental", "recurring"]
Placement = Literal["protocol", "exclude_transition", "anywhere"]
DRIFT_TYPES = ("none", "sudden", "gradual", "incremental", "recurring")
RAMP_TYPES = ("gradual", "incremental")


@dataclass(frozen=True)
class SyntheticConfig:
    drift_type: DriftType
    seed: int
    split: Literal["development", "final_evaluation"] = "development"
    n_observations: int = 4096
    pre_mean: float = 0.0
    pre_std: float = 1.0
    post_mean: float = 1.5
    post_std: float = 1.0
    drift_start: int | None = None
    drift_duration: int | None = None
    recurrence_period: int = 512
    anomaly_count: int | None = None
    anomaly_fraction: float | None = None
    anomaly_magnitude: float = 6.0
    anomaly_placement: Placement = "protocol"
    warmup: int = 256
    min_anomaly_separation: int = 16
    priority_anomaly_count: int = 3
    post_change_window: int = 64
    allow_boundary_anomalies: bool = False

    def __post_init__(self) -> None:
        if self.drift_type not in DRIFT_TYPES:
            raise ValueError(f"drift_type must be one of {', '.join(DRIFT_TYPES)}")
        if self.split not in ("development", "final_evaluation"):
            raise ValueError("split must be development or final_evaluation")
        if self.anomaly_placement not in ("protocol", "exclude_transition", "anywhere"):
            raise ValueError("invalid anomaly_placement")
        if type(self.allow_boundary_anomalies) is not bool:
            raise ValueError("allow_boundary_anomalies must be a boolean")

        for name, minimum in (
            ("seed", 0),
            ("n_observations", 1),
            ("warmup", 0),
            ("min_anomaly_separation", 1),
            ("priority_anomaly_count", 0),
            ("post_change_window", 1),
            ("recurrence_period", 1),
        ):
            _require_integer(name, getattr(self, name), minimum)
        for name in (
            "pre_mean",
            "post_mean",
            "pre_std",
            "post_std",
            "anomaly_magnitude",
        ):
            _require_number(name, getattr(self, name))
        if self.pre_std <= 0 or self.post_std <= 0 or self.anomaly_magnitude <= 0:
            raise ValueError(
                "standard deviations and anomaly_magnitude must be positive"
            )
        if self.warmup >= self.n_observations:
            raise ValueError("warmup must be less than n_observations")
        if self.anomaly_count is not None:
            _require_integer("anomaly_count", self.anomaly_count, 0)
            if self.anomaly_fraction is not None:
                raise ValueError("specify anomaly_count or anomaly_fraction, not both")
        if self.anomaly_fraction is not None:
            _require_number("anomaly_fraction", self.anomaly_fraction)
            if not 0 <= self.anomaly_fraction <= 1:
                raise ValueError("anomaly_fraction must be between 0 and 1")

        if self.drift_type == "none":
            if self.drift_start is not None or self.drift_duration is not None:
                raise ValueError("stationary streams cannot specify a drift interval")
            return

        last = _require_integer("drift_start", self.drift_start, 1)
        if self.drift_duration is not None and self.drift_type not in RAMP_TYPES:
            raise ValueError(
                "drift_duration is only used for gradual or incremental drift"
            )
        if self.drift_type in RAMP_TYPES:
            last += _require_integer("drift_duration", self.drift_duration, 2) - 1
        elif self.drift_type == "recurring":
            last += 2 * self.recurrence_period
        if last >= self.n_observations - 1:
            raise ValueError(
                "drift must leave at least one observation after the last event"
            )

    @property
    def injection_count(self) -> int:
        if self.anomaly_fraction is not None:
            return math.floor(self.n_observations * self.anomaly_fraction)
        return self.anomaly_count or 0


def _require_integer(name: str, value: int | None, minimum: int) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _require_number(name: str, value: float) -> None:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")


@dataclass(frozen=True)
class Distribution:
    mean: float
    std: float
    family: str = "normal"


@dataclass(frozen=True)
class DriftEvent:
    start: int
    end: int
    from_regime: str
    to_regime: str
    pre_distribution: Distribution
    post_distribution: Distribution
    transition_rule: str


@dataclass(frozen=True)
class SyntheticStream:
    config: SyntheticConfig
    observations: NDArray[np.float64]
    index: NDArray[np.int64]
    anomaly_mask: NDArray[np.bool_]
    anomaly_positions: tuple[int, ...]
    drift_events: tuple[DriftEvent, ...]
    phase: NDArray[np.str_]
    regime: NDArray[np.str_]
    means: NDArray[np.float64]
    stds: NDArray[np.float64]


def _drift_events(config: SyntheticConfig) -> tuple[DriftEvent, ...]:
    if config.drift_type == "none":
        return ()
    a = Distribution(config.pre_mean, config.pre_std)
    b = Distribution(config.post_mean, config.post_std)
    start = config.drift_start
    assert start is not None
    if config.drift_type == "recurring":
        period = config.recurrence_period
        return (
            DriftEvent(start, start, "A", "B", a, b, "instantaneous"),
            DriftEvent(start + period, start + period, "B", "A", b, a, "instantaneous"),
            DriftEvent(
                start + 2 * period, start + 2 * period, "A", "B", a, b, "instantaneous"
            ),
        )
    if config.drift_type in RAMP_TYPES:
        duration = config.drift_duration
        assert duration is not None
        rule = (
            "linear_mixture_probability"
            if config.drift_type == "gradual"
            else "linear_mean_and_std"
        )
        return (DriftEvent(start, start + duration - 1, "A", "B", a, b, rule),)
    return (DriftEvent(start, start, "A", "B", a, b, "instantaneous"),)


def _latest_schedule(groups, counts, separation):
    """Place each group as late as possible to leave room for its predecessors."""
    schedule = []
    limit = math.inf
    for candidates, count in reversed(list(zip(groups, counts, strict=True))):
        group = []
        for _ in range(count):
            offset = candidates.searchsorted(limit, side="right") - 1
            if offset < 0:
                return None
            position = int(candidates[offset])
            group.append(position)
            limit = position - separation
        schedule.append(group[::-1])
    return schedule[::-1]


def _try_random_positions(groups, counts, size, separation, rng):
    """Visit candidates in random order, reserving each selected point's neighbors."""
    reserved = np.zeros(size, dtype=np.bool_)
    positions = []
    for candidates, count in zip(groups, counts, strict=True):
        if count == 0:
            continue
        for candidate in rng.permutation(candidates):
            position = int(candidate)
            if not reserved[position]:
                positions.append(position)
                reserved[max(0, position - separation + 1) : position + separation] = (
                    True
                )
                count -= 1
                if count == 0:
                    break
        if count:
            return None
    return tuple(sorted(positions))


def _sample_positions(config, events, index, rng):
    count = config.injection_count
    if count == 0:
        return ()

    eligible = index >= config.warmup
    for event in events:
        if config.anomaly_placement == "exclude_transition":
            eligible[event.start : event.end + 1] = False
        elif not config.allow_boundary_anomalies:
            eligible[event.start] = eligible[event.end] = False
    candidates = index[eligible]
    separation = config.min_anomaly_separation
    if (count - 1) * separation >= config.n_observations - config.warmup:
        raise ValueError(
            "cannot place the requested anomalies with this warmup and separation"
        )

    if not events or config.anomaly_placement != "protocol":
        groups = (candidates,)
        sampled = _try_random_positions(groups, (count,), index.size, separation, rng)
        if sampled is not None:
            return sampled
        schedule = _latest_schedule(groups, (count,), separation)
    else:
        first = events[0]
        start, stop = (
            (first.start, first.end + 1)
            if config.drift_type in RAMP_TYPES
            else (first.start + 1, first.start + 1 + config.post_change_window)
        )
        quota = config.priority_anomaly_count
        if quota > count:
            raise ValueError(
                "priority_anomaly_count exceeds the requested anomaly count"
            )
        before = candidates[candidates < start]
        priority = candidates[(candidates >= start) & (candidates < stop)]
        after = candidates[candidates >= stop]
        groups = (before, priority, after)
        remaining = count - quota
        sampled = _try_random_positions(
            (priority, np.concatenate((before, after))),
            (quota, remaining),
            index.size,
            separation,
            rng,
        )
        if sampled is not None:
            return sampled
        schedule = None
        # Resolve dense placements exactly when the random pass cannot fit the quota.
        for left_count in rng.permutation(remaining + 1):
            schedule = _latest_schedule(
                groups, (left_count, quota, remaining - left_count), separation
            )
            if schedule is not None:
                break

    if schedule is None:
        raise ValueError(
            "cannot place the requested anomalies under this placement policy"
        )
    positions = []
    minimum = config.warmup
    for candidates, group in zip(groups, schedule, strict=True):
        for latest in group:
            lo = candidates.searchsorted(minimum)
            hi = candidates.searchsorted(latest, side="right")
            position = int(candidates[rng.integers(lo, hi)])
            positions.append(position)
            minimum = position + separation
    return tuple(positions)


def generate_stream(config: SyntheticConfig) -> SyntheticStream:
    """Generate a stream and pointwise ground truth solely from its configuration."""
    noise_seed, mixture_seed, position_seed, sign_seed = np.random.SeedSequence(
        config.seed
    ).spawn(4)
    noise, mixture, positions_rng, signs = (
        np.random.Generator(np.random.PCG64(seed))
        for seed in (noise_seed, mixture_seed, position_seed, sign_seed)
    )
    index = np.arange(config.n_observations, dtype=np.int64)
    events = _drift_events(config)
    positions = _sample_positions(config, events, index, positions_rng)
    means = np.full(index.size, config.pre_mean, dtype=np.float64)
    stds = np.full(index.size, config.pre_std, dtype=np.float64)
    regime = np.full(index.size, "A", dtype="<U10")
    phase = np.full(index.size, "pre_drift" if events else "stationary", dtype="<U13")

    for event in events:
        after = slice(event.start, None)
        transition = slice(event.start, event.end + 1)
        regime[after] = event.to_regime
        means[after] = event.post_distribution.mean
        stds[after] = event.post_distribution.std
        phase[after] = "post_drift"
        phase[transition] = "in_transition"
        if config.drift_type in RAMP_TYPES:
            weights = np.linspace(0.0, 1.0, event.end - event.start + 1)
            if config.drift_type == "gradual":
                use_post = mixture.random(weights.size) < weights
                regime[transition] = np.where(use_post, "B", "A")
                means[transition] = np.where(
                    use_post, config.post_mean, config.pre_mean
                )
                stds[transition] = np.where(use_post, config.post_std, config.pre_std)
            else:
                regime[transition] = "ramp"
                means[transition] = (
                    1 - weights
                ) * config.pre_mean + weights * config.post_mean
                stds[transition] = (
                    1 - weights
                ) * config.pre_std + weights * config.post_std

    anomaly_mask = np.zeros(index.size, dtype=np.bool_)
    anomaly_mask[list(positions)] = True
    with np.errstate(over="ignore", invalid="ignore"):
        observations = means + stds * noise.standard_normal(index.size)
        observations[anomaly_mask] += (
            signs.choice((-1, 1), size=len(positions))
            * config.anomaly_magnitude
            * config.pre_std
        )
    if not np.all(np.isfinite(observations)):
        raise ValueError(
            "generation produced non-finite observations; reduce parameter magnitudes"
        )
    return SyntheticStream(
        config,
        observations,
        index,
        anomaly_mask,
        positions,
        events,
        phase,
        regime,
        means,
        stds,
    )


def generate_pair(config: SyntheticConfig) -> tuple[SyntheticStream, SyntheticStream]:
    """Return the clean trace and the corresponding trace with requested injections."""
    clean = generate_stream(replace(config, anomaly_count=0, anomaly_fraction=None))
    return clean, generate_stream(config)


def load_config(path: Path) -> SyntheticConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(isinstance(key, str) for key in data):
        raise ValueError("synthetic config must be a mapping of parameter names")
    try:
        return SyntheticConfig(**data)
    except TypeError as error:
        raise ValueError(f"invalid synthetic config fields: {error}") from error


def export_stream(stream: SyntheticStream, output: Path) -> None:
    """Publish CSV and metadata together in a new output directory."""
    if output.exists():
        raise FileExistsError(f"output directory already exists: {output}")
    metadata = {
        "schema_version": 1,
        "generator_revision": "sha256:"
        + hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "split": stream.config.split,
        "seed": stream.config.seed,
        "length": stream.config.n_observations,
        "drift_type": stream.config.drift_type,
        "parameters": asdict(stream.config),
        "drift_events": [asdict(event) for event in stream.drift_events],
        "anomaly_positions": stream.anomaly_positions,
        "rng": {
            "bit_generator": "PCG64",
            "numpy_version": np.__version__,
            "seed_sequence_children": [
                "noise",
                "mixture",
                "anomaly_positions",
                "anomaly_signs",
            ],
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as temporary:
        staged = Path(temporary) / "stream"
        staged.mkdir()
        with (staged / "stream.csv").open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file, lineterminator="\n")
            writer.writerow(
                ("index", "value", "anomaly_label", "phase", "regime", "mean", "std")
            )
            writer.writerows(
                zip(
                    stream.index,
                    stream.observations,
                    stream.anomaly_mask.astype(int),
                    stream.phase,
                    stream.regime,
                    stream.means,
                    stream.stds,
                    strict=True,
                )
            )
        (staged / "metadata.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        staged.rename(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--clean",
        action="store_true",
        help="generate the paired trace without injections",
    )
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        if args.clean:
            config = replace(config, anomaly_count=0, anomaly_fraction=None)
        stream = generate_stream(config)
        export_stream(stream, args.output)
    except (OSError, ValueError, yaml.YAMLError) as error:
        parser.exit(1, f"Synthetic stream: {error}\n")
    print(
        f"{config.split}: {config.drift_type}, seed {config.seed}, {config.n_observations} points, "
        f"{len(stream.drift_events)} drift events, {len(stream.anomaly_positions)} anomalies "
        f"-> {args.output}"
    )


if __name__ == "__main__":
    main()
