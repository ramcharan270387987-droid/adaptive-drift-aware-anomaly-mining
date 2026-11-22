"""Transactional local detector state and prediction sink."""

import hashlib
import json
import math
import pickle
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from drift_anomaly.experiments.selective_evaluation import _selective_arm
from drift_anomaly.experiments.selective_smoke import FROZEN_ZSCORE
from drift_anomaly.replay import DEFAULT_WARMUP
from drift_anomaly.selective_adaptation import Ablation
from drift_anomaly.zscore import StaticZScore

METHODS = ("static_zscore", "persistence", "full")
MAX_BATCH_ROWS = 4096


def unique_fields(pairs):
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise ValueError("duplicate JSON field names")
    return fields


@dataclass(frozen=True)
class InputRow:
    stream_id: str
    index: int
    timestamp: str
    value: float

    @classmethod
    def parse(cls, line):
        row = json.loads(line, object_pairs_hook=unique_fields)
        if not isinstance(row, dict) or set(row) != {
            "stream_id",
            "index",
            "timestamp",
            "value",
        }:
            raise ValueError("expected stream_id, index, timestamp and value only")
        stream_id, index, timestamp, value = (
            row["stream_id"],
            row["index"],
            row["timestamp"],
            row["value"],
        )
        if (
            not isinstance(stream_id, str)
            or not stream_id.strip()
            or len(stream_id) > 128
        ):
            raise ValueError("invalid stream_id")
        if type(index) is not int or not 0 <= index <= 2**63 - 1:
            raise ValueError("invalid zero-based observation index")
        stamp = (
            datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else None
        )
        if (
            stamp is None
            or stamp.tzinfo is not None
            or stamp.isoformat(timespec="microseconds") != timestamp
        ):
            raise ValueError(
                "timestamp must be ISO 8601 without an offset, with microseconds"
            )
        try:
            finite = type(value) in (float, int) and math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            raise ValueError("value must be a finite number")
        return cls(stream_id, index, timestamp, float(value))


def factory(method):
    if method == "static_zscore":
        return StaticZScore(FROZEN_ZSCORE)
    if method in METHODS:
        return _selective_arm(Ablation(method)).factory()
    raise ValueError(f"unsupported streaming method {method!r}")


def encode(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":"))


@dataclass
class StreamState:
    detector: object
    next_index: int = 0
    timestamp: str = ""
    prefix: list[float] = field(default_factory=list)
    version: int = 0

    def step(self, row):
        if row.index != self.next_index or row.timestamp < self.timestamp:
            raise ValueError(
                f"{row.stream_id}: expected index {self.next_index} and nondecreasing timestamp, "
                f"received index {row.index} at {row.timestamp}"
            )
        self.next_index += 1
        self.timestamp = row.timestamp
        event = {
            **asdict(row),
            "warmup": row.index < DEFAULT_WARMUP,
            "score": None,
            "prediction": None,
            "drift_alarm": False,
            "adaptation_event": False,
            "model_version": None,
            "mean": None,
            "std": None,
            "update": None,
        }
        if event["warmup"]:
            self.prefix.append(row.value)
            if len(self.prefix) == DEFAULT_WARMUP:
                self.detector.fit_initial(tuple(self.prefix))
                self.prefix.clear()
            return event
        # Capture the same model object used for scoring, before any refit.
        model = (
            self.detector
            if isinstance(self.detector, StaticZScore)
            else self.detector._anomaly
        )
        prediction = self.detector.score_one(row.value)
        event.update(
            score=prediction.score,
            prediction=prediction.predicted_anomaly,
            model_version=self.version,
            mean=model.mean,
            std=model.std,
        )
        update = self.detector.update_one(row.value)
        if update is not None:
            detail = update.metadata.get("checkpoint", {})
            refit = detail.get("refit") is not None
            event.update(
                drift_alarm=update.drift_alarm is True,
                adaptation_event=refit,
                update=asdict(update),
            )
            self.version += refit
        return event


class BatchSink:
    """Store batch acknowledgment, outputs, and complete state atomically."""

    def __init__(self, database: Path, methods, fingerprint):
        self.methods = tuple(methods)
        if (
            not self.methods
            or len(set(self.methods)) != len(self.methods)
            or not set(self.methods) <= set(METHODS)
        ):
            raise ValueError("expected unique frozen methods")
        self.database = database
        manifest = encode(
            {"schema": 1, "methods": self.methods, "fingerprint": fingerprint}
        )
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS setup (manifest TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS batches (id INTEGER PRIMARY KEY, digest TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS states (
                    stream TEXT NOT NULL, method TEXT NOT NULL, payload BLOB NOT NULL,
                    PRIMARY KEY (stream, method)
                );
                CREATE TABLE IF NOT EXISTS events (
                    stream TEXT NOT NULL, method TEXT NOT NULL,
                    idx INTEGER NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY (stream, method, idx)
                );
            """)
            current = db.execute("SELECT manifest FROM setup").fetchone()
            if current is None:
                db.execute("INSERT INTO setup VALUES (?)", (manifest,))
            elif current != (manifest,):
                raise ValueError("checkpoint settings or detector versions changed")

    def connect(self):
        return sqlite3.connect(self.database, factory=ClosingConnection)

    def commit(self, batch_id, lines):
        rows = sorted(
            (InputRow.parse(line) for line in lines),
            key=lambda r: (r.stream_id, r.index),
        )
        digest = hashlib.sha256(encode([asdict(r) for r in rows]).encode()).hexdigest()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute(
                "SELECT digest FROM batches WHERE id = ?", (batch_id,)
            ).fetchone()
            if prior is not None:
                if prior != (digest,):
                    raise ValueError(f"Spark batch {batch_id} changed on recovery")
                return False
            expected = db.execute(
                "SELECT COALESCE(MAX(id) + 1, 0) FROM batches"
            ).fetchone()[0]
            if batch_id != expected:
                raise ValueError(
                    f"expected Spark batch {expected}, received {batch_id}"
                )
            states = {}
            records = []
            for row in rows:
                for method in self.methods:
                    key = (row.stream_id, method)
                    if key not in states:
                        saved = db.execute(
                            "SELECT payload FROM states WHERE stream = ? AND method = ?",
                            key,
                        ).fetchone()
                        # This database is private, local state created by this adapter.
                        states[key] = (
                            pickle.loads(saved[0])
                            if saved
                            else StreamState(factory(method))
                        )
                    event = states[key].step(row)
                    records.append(
                        (*key, row.index, encode({"method": method, **event}))
                    )
            db.executemany("INSERT INTO events VALUES (?, ?, ?, ?)", records)
            db.executemany(
                "INSERT OR REPLACE INTO states VALUES (?, ?, ?)",
                [(*key, pickle.dumps(state)) for key, state in states.items()],
            )
            db.execute("INSERT INTO batches VALUES (?, ?)", (batch_id, digest))
        return True

    def records(self):
        with self.connect() as db:
            return [
                json.loads(payload)
                for (payload,) in db.execute(
                    "SELECT payload FROM events ORDER BY stream,method,idx"
                )
            ]


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *info):
        try:
            return super().__exit__(*info)
        finally:
            self.close()
