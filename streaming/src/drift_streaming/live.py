"""Paced synthetic and NAB input for local Structured Streaming."""

import argparse
import hashlib
import math
from dataclasses import replace
from itertools import zip_longest
from pathlib import Path
from threading import Event, Thread
from time import perf_counter

from drift_anomaly.experiments.static_baseline import write_json
from drift_anomaly.experiments.validation import execution_revision
from drift_anomaly.replay import _git_commit
from drift_streaming.benchmark import Resources, distribution
from drift_streaming.evaluate import reconcile
from drift_streaming.inputs import BENCHMARK_NAB, publish, replay_input
from drift_streaming.spark import adapter_revision, drain, local_session
from drift_streaming.state import MAX_BATCH_ROWS, METHODS


def plan(rows, per_interval):
    cursor, tick = 0, 0
    while cursor < len(rows):
        tick += 1
        end = min(len(rows), math.floor(tick * per_interval))
        if end > cursor:
            yield tick, rows[cursor:end]
            cursor = end


class Producer:
    def __init__(self, source, rows, rate, interval, speed):
        self.source, self.rows = source, rows
        self.rate, self.interval, self.speed = rate, interval, speed
        self.publications = []
        self.cancel = Event()
        self.error = None
        self.thread = Thread(target=self.produce, daemon=True)

    def produce(self):
        self.started = perf_counter()
        try:
            for tick, rows in plan(self.rows, self.rate * self.interval * self.speed):
                if self.cancel.wait(
                    max(0, self.started + tick * self.interval - perf_counter())
                ):
                    break
                begin = perf_counter()
                publish(
                    self.source, [rows], len(rows), start_file=len(self.publications)
                )
                self.publications.append((begin, perf_counter(), len(rows)))
        except (OSError, ValueError, OverflowError) as error:
            self.error = error

    def start(self):
        self.thread.start()

    def is_alive(self):
        return self.thread.is_alive()

    def result(self):
        self.thread.join()
        if self.error is not None:
            raise RuntimeError("input producer failed") from self.error

    def close(self):
        self.cancel.set()
        if self.thread.ident is not None:
            self.thread.join()


def make_streams(name, count, *, full_source=False):
    base = replay_input(name, benchmark=not full_source)
    return (
        [base]
        if count == 1
        else [
            replace(base, stream_id=f"{name}#{number + 1}") for number in range(count)
        ]
    )


def run_live(
    session, output, streams, methods, *, rate, interval, speed=1.0, partitions=2
):
    if (
        not streams
        or not all(math.isfinite(x) and x > 0 for x in (rate, interval, speed))
        or not 0.05 <= interval <= 5
        or not 1 <= partitions <= 16
        or not 1 <= rate * speed <= 100_000
        or math.ceil(rate * interval * speed) > MAX_BATCH_ROWS
    ):
        raise ValueError("unsupported rate, interval, replay speed, or partition count")
    root = Path("results").resolve()
    if output.resolve() == root or not output.resolve().is_relative_to(root):
        raise ValueError("output must be a new directory under results/")
    output.mkdir(parents=True)
    source = output / "input"
    source.mkdir()
    rows = [
        row
        for group in zip_longest(*(stream.rows() for stream in streams))
        for row in group
        if row is not None
    ]
    producer = Producer(source, rows, rate, interval, speed)
    with Resources() as resources:
        sink, timings, elapsed = drain(
            session,
            source,
            output / "query",
            methods,
            live_producer=producer,
            interval=interval,
            partitions=partitions,
        )
    active = [batch for batch in timings if batch["rows"]]
    if [b["rows"] for b in active] != [
        p[2] for p in producer.publications
    ] or not active:
        raise ValueError("live file and committed batch counts differ")
    # Identify each micro-batch by the immutable source file order verified by the sink.
    delays = [
        batch["commit_monotonic"] - release[0]
        for batch, release in zip(active, producer.publications, strict=True)
    ]
    arrival_wall = producer.publications[-1][1] - producer.started
    finish = active[-1]["commit_monotonic"]
    db = output / "query/state.sqlite"
    with sink.connect() as connection:
        model_bytes = connection.execute(
            "SELECT SUM(length(payload)) FROM states"
        ).fetchone()[0]
    results = reconcile(streams, methods, sink.records())
    first_publication_wall = producer.publications[0][0]
    last_publication = producer.publications[-1][1]
    during_arrival_peak = max(
        sum(p[2] for p in producer.publications if p[1] <= now)
        - sum(b["rows"] for b in active if b["commit_monotonic"] <= now)
        for _, now, _ in producer.publications
    )
    summary = {
        "source_count": len(streams),
        "records": len(rows),
        "batches": len(active),
        "target_arrival_records_sec": rate * speed,
        "interval_seconds": interval,
        "partitions": partitions,
        "observed_arrival_records_sec": len(rows) / arrival_wall,
        "sustained_records_sec": len(rows) / max(finish - producer.started, 1e-9),
        "producer_to_commit_latency_seconds": distribution(
            [
                delay
                for delay, batch in zip(delays, active, strict=True)
                for _ in range(batch["rows"])
            ]
        ),
        "batch_processing_seconds": distribution(
            [b["processing_seconds"] for b in active]
        ),
        "peak_observed_uncommitted_input_rows": during_arrival_peak,
        "tail_drain_seconds": finish - last_publication,
        "first_file_commit_seconds": active[0]["commit_monotonic"]
        - first_publication_wall,
        "terminal_backlog_rows": sum(
            b["rows"] for b in active if b["commit_monotonic"] > last_publication
        ),
        "model_state_bytes": model_bytes,
        "sqlite_bytes_including_journal": sum(
            file.stat().st_size for file in db.parent.glob("state.sqlite*")
        ),
        "refits": sum(r["refits"] for r in results.values()),
        "alarms": sum(r["alarms"] for r in results.values()),
        "dropped_or_failed_records": len(rows) - sum(b["rows"] for b in active),
        **resources.summary(elapsed),
    }
    write_json(output / "benchmark.json", summary)
    write_json(output / "reconciliation.json", results)
    write_json(
        output / "batches.json",
        [
            {**batch, "publish_to_commit_seconds": delay}
            for batch, delay in zip(active, delays, strict=True)
        ],
    )
    write_json(
        output / "manifest.json",
        {
            "git_head_at_execution": _git_commit(),
            "research_tree": execution_revision(),
            "adapter_sha256": adapter_revision(),
            "spark": session.version,
            "master": session.sparkContext.master,
            "lock_sha256": hashlib.sha256(
                Path("streaming/uv.lock").read_bytes()
            ).hexdigest(),
            "methods": methods,
            "sources": {s.stream_id: s.provenance for s in streams},
        },
    )
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--series", default="sudden")
    parser.add_argument("--streams", type=int, default=1)
    parser.add_argument("--rate", type=float, default=256)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--speed", type=float, default=1)
    parser.add_argument("--partitions", type=int, default=2)
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=METHODS)
    parser.add_argument("--matrix", action="store_true")
    parser.add_argument("--full-source", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.streams <= 32:
        parser.error("choose 1 to 32 independent streams")
    session = local_session()
    try:
        if args.matrix:
            matrix = []
            for count in (1, 4, 8):
                for rate, interval in ((512, 0.5), (2048, 0.25)):
                    report = run_live(
                        session,
                        args.output / f"s{count}-r{rate}",
                        make_streams("sudden", count),
                        ("full",),
                        rate=rate,
                        interval=interval,
                        partitions=args.partitions,
                    )
                    matrix.append(report)
                    print(report, flush=True)
            for rate, interval in ((4096, 0.25), (8192, 0.10)):
                report = run_live(
                    session,
                    args.output / f"s8-r{rate}",
                    make_streams("sudden", 8, full_source=True),
                    ("full",),
                    rate=rate,
                    interval=interval,
                    partitions=args.partitions,
                )
                matrix.append(report)
                print(report, flush=True)
            write_json(args.output / "matrix.json", matrix)
        else:
            series = BENCHMARK_NAB if args.series == "nab" else args.series
            print(
                run_live(
                    session,
                    args.output,
                    make_streams(series, args.streams, full_source=args.full_source),
                    args.methods,
                    rate=args.rate,
                    interval=args.interval,
                    speed=args.speed,
                    partitions=args.partitions,
                ),
                flush=True,
            )
    finally:
        session.stop()


if __name__ == "__main__":
    main()
