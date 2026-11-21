"""Replay development streams causally and collect evaluation-ready records."""

import argparse
import json
import math
import subprocess
from collections.abc import Callable, Iterable, Iterator
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from itertools import islice
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Protocol

import yaml

from drift_anomaly.synthetic import (
    DriftEvent,
    SyntheticConfig,
    generate_stream,
    load_config,
)

DEFAULT_WARMUP = 256

type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
)


@dataclass(frozen=True)
class Observation:
    index: int
    value: float
    anomaly_label: bool | None = None
    drift_phase: str | None = None
    regime: str | None = None


@dataclass(frozen=True)
class Prediction:
    score: float | None = None
    predicted_anomaly: bool | None = None
    drift_alarm: bool | None = None
    metadata: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True)
class UpdateEvent:
    drift_alarm: bool | None = None
    metadata: dict[str, JsonValue] = field(default_factory=dict)


class StreamingDetector(Protocol):
    """Use raw scalar input and retain causal feature state in fit and update."""

    identifier: str

    def fit_initial(self, values: tuple[float, ...]) -> None:
        """Initialize from the warm-up prefix, which may be empty."""
        ...

    def score_one(self, value: float) -> Prediction:
        """Read the previous state without training or updating it."""
        ...

    def update_one(self, value: float) -> UpdateEvent | None:
        """Consume the scored observation and optionally report an event."""
        ...


@dataclass(frozen=True)
class ReplayRecord:
    observation: Observation
    warmup: bool
    prediction: Prediction | None
    update: UpdateEvent | None = None


@dataclass(frozen=True)
class ReplayStats:
    observation_count: int
    warmup_count: int
    scored_count: int
    warmup_last_index: int | None
    first_scored_index: int | None
    warmup_anomaly_count: int
    elapsed_seconds: float
    observations_per_second: float | None
    scored_observations_per_second: float | None


@dataclass(frozen=True)
class ReplayResult:
    detector_id: str
    records: tuple[ReplayRecord, ...]
    stats: ReplayStats

    def scored_records(self) -> Iterator[ReplayRecord]:
        """Iterate only records eligible for primary metrics."""
        return islice(self.records, self.stats.warmup_count, None)


def replay(
    observations: Iterable[Observation],
    detector_factory: Callable[[], StreamingDetector],
    *,
    warmup: int = DEFAULT_WARMUP,
) -> ReplayResult:
    """Consume the source once and finish each update before pulling the next row."""
    if type(warmup) is not int or warmup < 0:
        raise ValueError("warmup must be a non-negative integer")

    detector = detector_factory()
    records: list[ReplayRecord] = []
    prefix: list[float] = []
    previous_index = None
    started = perf_counter()

    if warmup == 0:
        detector.fit_initial(())
    for observation in observations:
        if previous_index is not None and observation.index <= previous_index:
            raise ValueError(
                "observation indices must be strictly increasing in source order"
            )
        if not math.isfinite(observation.value):
            raise ValueError(f"non-finite observation at index {observation.index}")

        value = float(observation.value)
        if len(prefix) < warmup:
            prefix.append(value)
            records.append(ReplayRecord(observation, warmup=True, prediction=None))
            if len(prefix) == warmup:
                detector.fit_initial(tuple(prefix))
        else:
            prediction = deepcopy(detector.score_one(value))
            if prediction.score is not None and not math.isfinite(prediction.score):
                raise ValueError(f"non-finite score at index {observation.index}")
            # Snapshot the prediction before the detector learns from this point.
            records.append(
                ReplayRecord(observation, warmup=False, prediction=prediction)
            )
            update = detector.update_one(value)
            if update is not None:
                records[-1] = ReplayRecord(
                    observation, False, prediction, deepcopy(update)
                )

        previous_index = observation.index

    elapsed = perf_counter() - started
    if not records:
        raise ValueError("replay requires at least one observation")
    if len(prefix) < warmup:
        raise ValueError(
            f"received {len(prefix)} observations for a warm-up of {warmup}"
        )

    count = len(records)
    scored = count - warmup
    stats = ReplayStats(
        observation_count=count,
        warmup_count=warmup,
        scored_count=scored,
        warmup_last_index=records[warmup - 1].observation.index if warmup else None,
        first_scored_index=records[warmup].observation.index if scored else None,
        warmup_anomaly_count=sum(
            record.observation.anomaly_label is True for record in records[:warmup]
        ),
        elapsed_seconds=elapsed,
        observations_per_second=count / elapsed if elapsed > 0 else None,
        scored_observations_per_second=scored / elapsed if elapsed > 0 else None,
    )
    return ReplayResult(detector.identifier, tuple(records), stats)


@dataclass(frozen=True)
class ReplayProvenance:
    stream_config_path: str
    stream_seed: int
    drift_type: str
    split: str
    warmup_length: int
    project_version: str | None
    git_commit: str | None
    detector_id: str
    executed_at_utc: str
    stream_parameters: dict[str, JsonValue]


@dataclass(frozen=True)
class DevelopmentReplay:
    provenance: ReplayProvenance
    result: ReplayResult
    drift_events: tuple[DriftEvent, ...]


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(Path(__file__).resolve().parent), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def replay_development(
    config_path: Path,
    detector_factory: Callable[[], StreamingDetector],
    *,
    warmup: int = DEFAULT_WARMUP,
) -> DevelopmentReplay:
    """Load one explicit development config and reject holdout before generation."""
    return replay_synthetic_development(
        load_config(config_path),
        detector_factory,
        config_path=config_path,
        warmup=warmup,
    )


def validate_development_config(config: SyntheticConfig) -> None:
    if config.split != "development" or config.seed not in range(10):
        raise ValueError(
            "development replay requires split 'development' and a seed from 0 to 9"
        )


def replay_synthetic_development(
    config: SyntheticConfig,
    detector_factory: Callable[[], StreamingDetector],
    *,
    config_path: Path,
    warmup: int = DEFAULT_WARMUP,
) -> DevelopmentReplay:
    """Replay an effective development configuration and record its source path."""
    validate_development_config(config)
    executed_at = datetime.now(UTC).isoformat()
    stream = generate_stream(config)
    observations = (
        Observation(int(index), float(value), bool(label), str(phase), str(regime))
        for index, value, label, phase, regime in zip(
            stream.index,
            stream.observations,
            stream.anomaly_mask,
            stream.phase,
            stream.regime,
            strict=True,
        )
    )
    result = replay(observations, detector_factory, warmup=warmup)
    try:
        project_version = version("drift-anomaly")
    except PackageNotFoundError:
        project_version = None
    provenance = ReplayProvenance(
        stream_config_path=str(config_path),
        stream_seed=config.seed,
        drift_type=config.drift_type,
        split=config.split,
        warmup_length=warmup,
        project_version=project_version,
        git_commit=_git_commit(),
        detector_id=result.detector_id,
        executed_at_utc=executed_at,
        stream_parameters=asdict(config),
    )
    return DevelopmentReplay(provenance, result, stream.drift_events)


def export_replay(run: DevelopmentReplay, output: Path) -> None:
    """Publish one JSON artifact in a new, ignored results directory."""
    root = Path.cwd() / "results"
    output = output.resolve()
    if output == root or not output.is_relative_to(root):
        raise ValueError("output must be a new directory under results/")
    if output.exists():
        raise FileExistsError(f"output directory already exists: {output}")

    payload = {
        "schema_version": 1,
        "provenance": asdict(run.provenance),
        "stats": asdict(run.result.stats),
        "drift_events": [asdict(event) for event in run.drift_events],
        "records": [asdict(record) for record in run.result.records],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as temporary:
        staged = Path(temporary) / "replay"
        staged.mkdir()
        (staged / "replay.json").write_text(
            json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        staged.rename(output)


class _SmokeObserver:
    """Exercise the interface from the CLI without making predictions."""

    identifier = "infrastructure-smoke"

    def fit_initial(self, values: tuple[float, ...]) -> None:
        pass

    def score_one(self, value: float) -> Prediction:
        return Prediction()

    def update_one(self, value: float) -> None:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--warmup", type=int, default=DEFAULT_WARMUP)
    parser.add_argument("--output", type=Path, help="new directory under results/")
    args = parser.parse_args()

    try:
        run = replay_development(args.config, _SmokeObserver, warmup=args.warmup)
        if args.output is not None:
            export_replay(run, args.output)
    except (OSError, ValueError, yaml.YAMLError) as error:
        parser.exit(1, f"Replay: {error}\n")

    stats = run.result.stats
    print(
        f"Infrastructure smoke: {run.provenance.drift_type}, seed {run.provenance.stream_seed}, "
        f"{stats.observation_count} observations, {stats.warmup_count} warm-up, "
        f"{stats.scored_count} score calls, {stats.elapsed_seconds:.6f}s elapsed"
    )
    if args.output is not None:
        print(f"Exported {args.output / 'replay.json'}")


if __name__ == "__main__":
    main()
