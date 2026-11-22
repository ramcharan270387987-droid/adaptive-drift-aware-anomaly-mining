"""Free development replay sources and ordered file publication."""

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from os import link, utime
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import time_ns

from drift_anomaly import nab
from drift_anomaly.nab_replay import MANIFEST, RAW_NAB, load_development_series
from drift_anomaly.replay import Observation, validate_development_config
from drift_anomaly.synthetic import DriftEvent, generate_stream, load_config
from drift_streaming.state import InputRow, encode

SYNTHETIC = ("stationary", "sudden", "gradual", "incremental", "recurring")
BENCHMARK_NAB = "realAWSCloudwatch/ec2_cpu_utilization_53ea38.csv"
BENCHMARK_SERIES = ("stationary", "sudden", "recurring", BENCHMARK_NAB)
BENCHMARK_LENGTH = 896


@dataclass(frozen=True)
class ReplayInput:
    stream_id: str
    timestamps: tuple[str, ...]
    observations: tuple[Observation, ...]
    drift_events: tuple[DriftEvent, ...]
    provenance: dict

    def rows(self):
        return [
            InputRow(self.stream_id, row.index, stamp, row.value)
            for row, stamp in zip(self.observations, self.timestamps, strict=True)
        ]


def replay_input(series, *, benchmark=False):
    if series in SYNTHETIC:
        path = Path("configs/synthetic") / f"{series}_dev.yaml"
        config = load_config(path)
        validate_development_config(config)
        if benchmark:
            # Short fixed workloads allow row-per-stream Spark triggers in local tests.
            changes = {"n_observations": BENCHMARK_LENGTH}
            if series in ("sudden", "recurring"):
                changes.update(drift_start=320)
            if series == "recurring":
                changes.update(recurrence_period=192)
            config = replace(config, **changes)
        generated = generate_stream(config)
        epoch = datetime(2000, 1, 1, tzinfo=UTC).replace(tzinfo=None)
        observations = tuple(
            Observation(
                i,
                float(value),
                bool(generated.anomaly_mask[i]),
                str(generated.phase[i]),
                str(generated.regime[i]),
            )
            for i, value in enumerate(generated.observations)
        )
        return ReplayInput(
            series,
            tuple(
                (epoch + timedelta(seconds=i)).isoformat(timespec="microseconds")
                for i in range(len(observations))
            ),
            observations,
            generated.drift_events,
            {
                "split": "development",
                "template": str(path),
                "effective_config": asdict(config),
            },
        )
    dataset = nab.load_config(MANIFEST)
    if series not in dataset["development"]:
        raise ValueError(
            "choose a synthetic development family or an approved NAB development series"
        )
    if not (RAW_NAB / dataset["revision"] / "data" / series).is_file():
        nab.fetch_split(dataset, RAW_NAB / dataset["revision"], "development")
    loaded = load_development_series(series)
    limit = BENCHMARK_LENGTH if benchmark else len(loaded.observations)
    return ReplayInput(
        series,
        tuple(
            stamp.isoformat(timespec="microseconds")
            for stamp in loaded.timestamps[:limit]
        ),
        loaded.observations[:limit],
        (),
        {
            "split": "development",
            "revision": loaded.revision,
            "sha256": loaded.checksum,
            "source": str(loaded.source),
            "prefix_rows": limit,
        },
    )


def publish(source: Path, rows_by_stream, batch_size, *, start_file=0):
    """Each atomically published file represents one micro-batch."""
    source.mkdir(parents=True, exist_ok=True)
    if not rows_by_stream or batch_size < 1:
        raise ValueError("source requires streams and a positive batch size")
    existing = list(source.glob("batch-*.jsonl"))
    base = max(
        time_ns(), max((f.stat().st_mtime_ns for f in existing), default=0) + 2_000_000
    )
    for number, offset in enumerate(
        range(0, max(map(len, rows_by_stream)), batch_size), start_file
    ):
        target = source / f"batch-{number:08d}.jsonl"
        if target.exists():
            raise FileExistsError(target)
        temp = None
        try:
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=source, prefix=".staged-", delete=False
            ) as file:
                temp = Path(file.name)
                for rows in rows_by_stream:
                    for row in rows[offset : offset + batch_size]:
                        file.write(encode(asdict(row)) + "\n")
            stamp = base + (number - start_file) * 2_000_000
            utime(temp, ns=(stamp, stamp))
            link(temp, target)
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)
