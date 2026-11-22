"""Checksum-verified NAB streams using the shared causal replay engine."""

import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from drift_anomaly import nab
from drift_anomaly.replay import DEFAULT_WARMUP, Observation, replay

MANIFEST = Path("configs/nab.yaml")
RAW_NAB = Path("data/raw/nab")


@dataclass(frozen=True)
class NABStream:
    series: str
    source: Path
    checksum: str
    revision: str
    timestamps: tuple[datetime, ...]
    observations: tuple[Observation, ...]
    windows: tuple[tuple[datetime, datetime], ...]
    duplicate_timestamps: int
    dropped_backwards: int
    unobserved_points: int


def _selected_annotations(data: bytes, series: str) -> list:
    key = re.escape(json.dumps(series).encode())
    match = re.search(rb"(?m)^\s*" + key + rb"\s*:\s*", data)
    if match is None:
        raise ValueError(f"missing NAB annotations for {series}")
    value, _ = json.JSONDecoder().raw_decode(data[match.end() :].decode("utf-8"))
    if not isinstance(value, list):
        raise TypeError("expected a NAB annotation list")
    return value


def _parse_rows(contents: bytes, *, skip_backwards: bool):
    reader = csv.reader(io.StringIO(contents.decode("utf-8"), newline=""), strict=True)
    if next(reader, None) != ["timestamp", "value"]:
        raise ValueError("unexpected NAB CSV header")
    rows = []
    duplicates = backwards = 0
    for row in reader:
        if len(row) != 2 or not nab.is_finite(row[1]):
            raise ValueError(f"NAB row {reader.line_num} requires a finite value")
        stamp = nab.parse_timestamp(row[0])
        if rows and stamp < rows[-1][0]:
            if not skip_backwards:
                raise ValueError(
                    f"NAB timestamp goes backwards at row {reader.line_num}"
                )
            backwards += 1
            continue
        duplicates += bool(rows and stamp == rows[-1][0])
        rows.append((stamp, float(row[1])))
    return rows, duplicates, backwards


def _load_series(series, config, raw, *, split):
    if series not in config[split]:
        raise ValueError(f"NAB series is outside the {split} split: {series}")
    raw = raw / config["revision"]
    source = raw / "data" / series
    checksum = config[split][series]
    rows, duplicates, backwards = _parse_rows(
        nab.checked_bytes(source.read_bytes(), checksum, series),
        skip_backwards=split == "final_evaluation",
    )

    def labels(name):
        contents = nab.checked_bytes(
            (raw / name).read_bytes(), config["metadata"][name], name
        )
        return _selected_annotations(contents, series)

    points = [nab.parse_timestamp(item) for item in labels(nab.POINT_LABELS)]
    if len(set(points)) != len(points):
        raise ValueError(f"duplicate NAB point annotations for {series}")
    windows = tuple(
        (nab.parse_timestamp(left), nab.parse_timestamp(right))
        for left, right in labels(nab.WINDOW_LABELS)
    )
    if any(left > right for left, right in windows):
        raise ValueError(f"reversed NAB annotation window for {series}")
    timestamps = tuple(stamp for stamp, _ in rows)
    if len(rows) <= DEFAULT_WARMUP:
        raise ValueError(f"NAB series has no data after warm-up: {series}")
    missing = set(points).difference(timestamps)
    if missing and split == "development":
        raise ValueError(f"NAB point annotations missing from observations: {series}")
    seen = set()
    observations = []
    for index, (stamp, value) in enumerate(rows):
        label = stamp in points and stamp not in seen
        if label:
            seen.add(stamp)
        observations.append(Observation(index, value, label))
    return NABStream(
        series,
        source,
        checksum,
        config["revision"],
        timestamps,
        tuple(observations),
        windows,
        duplicates,
        backwards,
        len(missing),
    )


def load_development_series(series: str, *, raw: Path = RAW_NAB) -> NABStream:
    """Reject final identifiers before reading any CSV or annotation content."""
    return _load_series(series, nab.load_config(MANIFEST), raw, split="development")


def replay_nab(stream: NABStream, factory):
    return replay(stream.observations, factory)
