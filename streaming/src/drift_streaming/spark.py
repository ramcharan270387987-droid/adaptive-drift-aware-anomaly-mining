"""Local Spark file source feeding a single ordered, transactional driver sink."""

import argparse
import hashlib
from collections.abc import Callable
from fcntl import LOCK_EX, LOCK_NB, flock
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

from pyspark.sql import SparkSession
from pyspark.sql.functions import get_json_object

from drift_anomaly.experiments.validation import execution_revision
from drift_streaming.state import MAX_BATCH_ROWS, METHODS, BatchSink


def adapter_revision():
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(root.glob("*.py")):
        digest.update(path.name.encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def local_session():
    session = (
        SparkSession.builder.master("local[2]")
        .appName("drift-anomaly-local")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .config("spark.driver.host", "127.0.0.1")
        .getOrCreate()
    )
    if session.sparkContext.master != "local[2]":
        raise ValueError("this adapter requires Spark local[2]")
    session.sparkContext.setLogLevel("ERROR")
    return session


def drain(
    session,
    source: Path,
    work: Path,
    methods,
    *,
    after_commit: Callable | None = None,
    live_producer=None,
    interval=0.5,
    partitions=1,
):
    """Drain available files, reusing the same Spark and SQLite state on restart."""
    if not source.is_dir():
        raise ValueError("the ordered Spark input directory must already exist")
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    checkpoint = work / "checkpoint"
    database = work / "state.sqlite"
    timings = []
    with (work / "query.lock").open("a") as lock:
        flock(lock, LOCK_EX | LOCK_NB)
        if checkpoint.exists() != database.exists():
            raise ValueError(
                "Spark checkpoint and detector database must be recovered together"
            )
        sink = BatchSink(
            database,
            methods,
            fingerprint={
                "source": str(source.resolve()),
                "research_tree": execution_revision(),
                "adapter_sha256": adapter_revision(),
                "versions": {
                    package: version(package)
                    for package in (
                        "drift-anomaly",
                        "drift-streaming",
                        "river",
                        "pyspark",
                    )
                },
            },
        )
        started = perf_counter()

        def on_batch(frame, batch_id):
            begin = perf_counter()
            if partitions > 1:
                frame = frame.repartition(
                    partitions, get_json_object("value", "$.stream_id")
                )
            lines = [row.value for row in frame.limit(MAX_BATCH_ROWS + 1).collect()]
            if len(lines) > MAX_BATCH_ROWS:
                raise ValueError(f"Spark micro-batch exceeds {MAX_BATCH_ROWS} rows")
            committed = sink.commit(batch_id, lines)
            end = perf_counter()
            timings.append(
                {
                    "batch_id": batch_id,
                    "rows": len(lines),
                    "committed": committed,
                    "processing_seconds": end - begin,
                    "available_to_commit_seconds": end - started,
                    "commit_monotonic": end,
                }
            )
            if after_commit is not None:
                after_commit(batch_id)

        writer = (
            session.readStream.format("text")
            .option("maxFilesPerTrigger", 1)
            .option("latestFirst", "false")
            .load(str(source.resolve()))
            .writeStream.foreachBatch(on_batch)
            .option("checkpointLocation", str(checkpoint.resolve()))
        )
        query = (
            writer.trigger(availableNow=True)
            if live_producer is None
            else writer.trigger(processingTime=f"{round(interval * 1000)} milliseconds")
        ).start()
        try:
            if live_producer is None:
                query.awaitTermination()
            else:
                live_producer.start()
                while live_producer.is_alive():
                    if query.awaitTermination(timeout=0.2):
                        raise RuntimeError("Spark stopped before the producer finished")
                live_producer.result()
                query.processAllAvailable()
        finally:
            if live_producer is not None:
                live_producer.close()
            if query.isActive:
                query.stop()
        return sink, timings, perf_counter() - started


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=METHODS)
    args = parser.parse_args()
    root = Path("results").resolve()
    work = args.work.resolve()
    if (
        work == root
        or not work.is_relative_to(root)
        or work.is_relative_to(args.source.resolve())
    ):
        parser.error(
            "query work must be a directory under results/ outside the input source"
        )
    session = local_session()
    try:
        _, batches, _ = drain(session, args.source, work, args.methods)
        print(
            f"Processed {sum(batch['committed'] for batch in batches)} new batches in {work}"
        )
    finally:
        session.stop()


if __name__ == "__main__":
    main()
