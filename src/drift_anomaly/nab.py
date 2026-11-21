"""Acquire and audit the pinned public NAB subset."""

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import median
from tempfile import NamedTemporaryFile
from urllib.request import urlopen

import yaml

SOURCE = "https://github.com/numenta/NAB"
RAW_SOURCE = "https://raw.githubusercontent.com/numenta/NAB"
SPLITS = ("development", "final_evaluation")
POINT_LABELS = "labels/combined_labels.json"
WINDOW_LABELS = "labels/combined_windows.json"
METADATA = {"LICENSE.txt", POINT_LABELS, WINDOW_LABELS}
SERIES_PATH = re.compile(r"[A-Za-z0-9_]+/[A-Za-z0-9_-]+\.csv")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d{1,6})?")


def load_config(path):
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or set(config) != {"revision", "metadata", *SPLITS}:
        raise ValueError("expected revision, metadata and both NAB splits")
    if not isinstance(config["revision"], str) or not re.fullmatch(
        r"[0-9a-f]{40}", config["revision"]
    ):
        raise ValueError("revision must be a full Git commit SHA")
    for group in ("metadata", *SPLITS):
        files = config[group]
        if not isinstance(files, dict) or not files:
            raise ValueError(f"{group} must be a nonempty path-to-checksum mapping")
        for name, digest in files.items():
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError(f"{group} contains an invalid SHA-256 digest")
            if group != "metadata" and (
                not isinstance(name, str) or not SERIES_PATH.fullmatch(name)
            ):
                raise ValueError(f"{group} contains an invalid NAB series path")
    if set(config["metadata"]) != METADATA:
        raise ValueError("metadata must include the license and both label files")
    if config[SPLITS[0]].keys() & config[SPLITS[1]].keys():
        raise ValueError("NAB splits must be disjoint")
    return config


def provenance(config):
    files = dict(config["metadata"])
    for split in SPLITS:
        files.update({f"data/{name}": digest for name, digest in config[split].items()})
    revision = config["revision"]
    return {
        "source": SOURCE,
        "revision": revision,
        "files": {
            name: {"sha256": digest, "url": f"{RAW_SOURCE}/{revision}/{name}"}
            for name, digest in sorted(files.items())
        },
    }


def checked_bytes(data, expected, name):
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"SHA-256 mismatch for {name}")
    return data


def write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(data)
            output.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def write_json(path, data):
    write_atomic(path, (json.dumps(data, indent=2, sort_keys=True) + "\n").encode())


def fetch(config, raw):
    manifest = provenance(config)
    _fetch_files(manifest["files"], raw)
    write_json(raw / "provenance.json", manifest)


def fetch_split(config, raw, split):
    """Acquire only the CSVs allowed for this experiment and shared metadata."""
    manifest = provenance(config)
    requested = set(config["metadata"]) | {f"data/{name}" for name in config[split]}
    files = {
        name: entry for name, entry in manifest["files"].items() if name in requested
    }
    _fetch_files(files, raw)
    write_json(raw / f"provenance_{split}.json", {**manifest, "files": files})


def _fetch_files(files, raw):
    for name, entry in files.items():
        path = raw / name
        if path.exists():
            checked_bytes(path.read_bytes(), entry["sha256"], name)
            continue
        with urlopen(entry["url"], timeout=30) as response:
            data = checked_bytes(response.read(), entry["sha256"], name)
        write_atomic(path, data)


def parse_timestamp(value):
    if not isinstance(value, str) or not TIMESTAMP.fullmatch(value):
        raise ValueError("expected a timezone-naive NAB timestamp")
    return datetime.fromisoformat(value)


def is_finite(value):
    try:
        return math.isfinite(float(value))
    except ValueError:
        return False


def audit_series(path, point_labels, window_labels):
    counts = Counter()
    timestamps = Counter()
    deltas = Counter()
    seen = set()
    previous = None
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.reader(source, strict=True)
        if next(reader, None) != ["timestamp", "value"]:
            raise ValueError(f"unexpected CSV header in {path}")
        for row in reader:
            counts["rows"] += 1
            counts["duplicate_rows"] += tuple(row) in seen
            seen.add(tuple(row))
            counts["malformed_rows"] += len(row) != 2
            stamp = row[0].strip() if row else ""
            value = row[1].strip() if len(row) > 1 else ""
            counts["missing_values"] += not value
            counts["invalid_numeric_values"] += bool(value) and not is_finite(value)
            counts["missing_timestamps"] += not stamp
            try:
                timestamp = parse_timestamp(stamp)
            except ValueError:
                counts["invalid_timestamps"] += bool(stamp)
                previous = None
                continue
            counts["duplicate_timestamps"] += timestamp in timestamps
            timestamps[timestamp] += 1
            if previous is not None:
                delta = (timestamp - previous).total_seconds()
                counts["non_monotonic_steps"] += delta < 0
                if delta > 0:
                    deltas[delta] += 1
            previous = timestamp

    mode = min(deltas, key=lambda delta: (-deltas[delta], delta)) if deltas else None
    first, last = (min(timestamps), max(timestamps)) if timestamps else (None, None)
    return {
        **dict.fromkeys(
            (
                "rows",
                "malformed_rows",
                "missing_values",
                "missing_timestamps",
                "invalid_numeric_values",
                "invalid_timestamps",
                "duplicate_rows",
                "duplicate_timestamps",
                "non_monotonic_steps",
            ),
            0,
        ),
        **counts,
        "timestamp_min": first.isoformat(sep=" ") if first else None,
        "timestamp_max": last.isoformat(sep=" ") if last else None,
        "sampling_seconds": {
            "min": min(deltas) if deltas else None,
            "median": median(list(deltas.elements())) if deltas else None,
            "mode": mode,
            "max": max(deltas) if deltas else None,
            "positive_steps": deltas.total(),
            "non_modal_positive_steps": deltas.total() - deltas[mode],
        },
        "labels": audit_labels(timestamps, point_labels, window_labels),
    }


def audit_labels(timestamps, point_labels, window_labels):
    points = [parse_timestamp(point) for point in (point_labels or [])]
    windows = []
    for start, end in window_labels or []:
        left, right = parse_timestamp(start), parse_timestamp(end)
        if left > right:
            raise ValueError("anomaly window ends before it starts")
        windows.append((left, right))
    return {
        "point_key_present": point_labels is not None,
        "window_key_present": window_labels is not None,
        "anomaly_count": len(points) if point_labels is not None else None,
        "point_labels_matched": sum(point in timestamps for point in points),
        "point_labels_with_multiple_observations": sum(
            timestamps[point] > 1 for point in points
        ),
        "point_labels_in_windows": sum(
            any(left <= point <= right for left, right in windows) for point in points
        ),
        "duplicate_point_labels": len(points) - len(set(points)),
        "window_count": len(windows) if window_labels is not None else None,
        "windows_with_observations": sum(
            any(left <= stamp <= right for stamp in timestamps)
            for left, right in windows
        ),
    }


def audit(config, raw):
    manifest = provenance(config)
    for name, entry in manifest["files"].items():
        checked_bytes((raw / name).read_bytes(), entry["sha256"], name)
    points = json.loads((raw / POINT_LABELS).read_text(encoding="utf-8"))
    windows = json.loads((raw / WINDOW_LABELS).read_text(encoding="utf-8"))
    return {
        "schema_version": 1,
        "source": SOURCE,
        "revision": config["revision"],
        "series": {
            name: {
                "split": split,
                "sha256": config[split][name],
                **audit_series(
                    raw / "data" / name, points.get(name), windows.get(name)
                ),
            }
            for split in SPLITS
            for name in config[split]
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/nab.yaml"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("fetch", help="fetch and check the selected files")
    audit_command = commands.add_parser(
        "audit", help="report quality of the local files"
    )
    audit_command.add_argument(
        "--output", type=Path, default=Path("data/processed/nab-audit.json")
    )
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        raw = Path("data/raw/nab") / config["revision"]
        if args.command == "fetch":
            fetch(config, raw)
            print(f"Verified {len(provenance(config)['files'])} files in {raw}")
        else:
            if args.output.resolve().is_relative_to(Path("data/raw").resolve()):
                raise ValueError("audit output must be outside data/raw")
            summary = audit(config, raw)
            write_json(args.output, summary)
            print(f"Audited {len(summary['series'])} series in {args.output}")
    except (ValueError, OSError, csv.Error, yaml.YAMLError) as error:
        parser.exit(1, f"NAB: {error}\n")


if __name__ == "__main__":
    main()
