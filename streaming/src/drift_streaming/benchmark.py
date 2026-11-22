"""Run the reproducible local Structured Streaming demonstration or benchmark."""

import argparse
import hashlib
import json
import os
import platform
import subprocess
from importlib.metadata import version
from pathlib import Path
from statistics import median, quantiles
from threading import Event, Thread

import psutil

from drift_anomaly.experiments.static_baseline import write_json
from drift_anomaly.experiments.validation import execution_revision
from drift_anomaly.replay import _git_commit
from drift_streaming.evaluate import reconcile
from drift_streaming.inputs import BENCHMARK_SERIES, publish, replay_input
from drift_streaming.spark import adapter_revision, drain, local_session
from drift_streaming.state import MAX_BATCH_ROWS, METHODS, encode


class Resources:
    def __init__(self):
        self.stop = Event()
        self.cpu = {}
        self.peak_rss = 0
        self.process = psutil.Process()

    def sample(self):
        rss = 0
        for process in [self.process, *self.process.children(recursive=True)]:
            try:
                key = process.pid, process.create_time()
                cpu = process.cpu_times()
                total = cpu.user + cpu.system
                self.cpu.setdefault(key, [total, total])[1] = total
                rss += process.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        self.peak_rss = max(rss, self.peak_rss)

    def monitor(self):
        while not self.stop.wait(0.1):
            self.sample()

    def __enter__(self):
        self.sample()
        self.thread = Thread(target=self.monitor, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join()
        self.sample()

    def summary(self, wall_time):
        cpu_seconds = sum(last - first for first, last in self.cpu.values())
        return {
            "peak_sampled_process_tree_rss_bytes": self.peak_rss,
            "process_tree_cpu_seconds": cpu_seconds,
            "mean_cpu_percent_one_core": 100 * cpu_seconds / wall_time,
        }


def distribution(values):
    return {
        "p50": median(values),
        "p95": quantiles(values, n=100, method="inclusive")[94]
        if len(values) > 1
        else values[0],
        "max": max(values),
    }


def run(output, streams, sizes, methods):
    if any(size < 1 or size * len(streams) > MAX_BATCH_ROWS for size in sizes):
        raise ValueError("invalid chunk size for the bounded Spark callback")
    root = Path("results").resolve()
    if output.resolve() == root or not output.resolve().is_relative_to(root):
        raise ValueError("streaming outputs must be in a new directory under results/")
    output.mkdir(parents=True)
    summaries, gold = {}, None
    session = local_session()
    try:
        for size in sizes:
            folder = output / f"batch-{size}"
            source = folder / "input"
            publish(source, [stream.rows() for stream in streams], size)
            with Resources() as resources:
                sink, timings, wall_time = drain(
                    session, source, folder / "query", methods
                )
            records = sink.records()
            reconciliation = reconcile(streams, methods, records)
            if gold is None:
                gold = records
            elif records != gold:
                raise ValueError("stream outputs depend on micro-batch size")
            active = [batch for batch in timings if batch["rows"]]
            physical_rows = sum(len(stream.observations) for stream in streams)
            if sum(batch["rows"] for batch in timings) != physical_rows:
                raise ValueError("Spark input counts do not match source counts")
            rows_per_batch = [batch["rows"] for batch in active]
            if rows_per_batch != [
                sum(
                    min(size, max(0, len(stream.observations) - offset))
                    for stream in streams
                )
                for offset in range(
                    0, max(len(stream.observations) for stream in streams), size
                )
            ]:
                raise ValueError(
                    "Spark did not consume one generated chunk per trigger"
                )
            summary = {
                "input_records": physical_rows,
                "output_records": len(records),
                "nonempty_batches": len(active),
                "elapsed_seconds": wall_time,
                "input_records_per_second": physical_rows / wall_time,
                "output_records_per_second": len(records) / wall_time,
                "processing_seconds_per_batch": distribution(
                    [b["processing_seconds"] for b in active]
                ),
                "backlog_latency_seconds_per_input_record": distribution(
                    [
                        b["available_to_commit_seconds"]
                        for b in active
                        for _ in range(b["rows"])
                    ]
                ),
                "post_score_update_calls": sum(
                    r["post_score_update_calls"] for r in reconciliation.values()
                ),
                "adwin_updates_after_warmup": sum(
                    r["adwin_updates_after_warmup"] for r in reconciliation.values()
                ),
                "refits": sum(r["refits"] for r in reconciliation.values()),
                "alarms": sum(r["alarms"] for r in reconciliation.values()),
                **resources.summary(wall_time),
            }
            summaries[size] = summary
            write_json(folder / "batches.json", timings)
            write_json(folder / "reconciliation.json", reconciliation)
            with (folder / "predictions.jsonl").open("w", encoding="utf-8") as file:
                for record in records:
                    file.write(encode(record) + "\n")
            print(json.dumps({"batch_size_per_stream": size, **summary}), flush=True)
        write_json(output / "benchmark.json", summaries)
        write_json(
            output / "manifest.json",
            {
                "git_commit": _git_commit(),
                "research_tree_sha256": execution_revision(),
                "adapter_sha256": adapter_revision(),
                "streaming_lock_sha256": hashlib.sha256(
                    Path("streaming/uv.lock").read_bytes()
                ).hexdigest(),
                "python": platform.python_version(),
                "platform": platform.platform(),
                "logical_cpus": os.cpu_count(),
                "master": session.sparkContext.master,
                "spark": session.version,
                "pyspark": version("pyspark"),
                "river": version("river"),
                "java": subprocess.check_output(
                    ["java", "-version"], stderr=subprocess.STDOUT, text=True
                ).strip(),
                "methods": methods,
                "batch_sizes_per_stream": sizes,
                "sources": {source.stream_id: source.provenance for source in streams},
            },
        )
    finally:
        session.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument(
        "--series", action="append", help="development synthetic family or NAB path"
    )
    parser.add_argument("--batch-sizes", nargs="+", type=int)
    parser.add_argument("--methods", choices=METHODS, nargs="+", default=METHODS)
    args = parser.parse_args()
    names = args.series or (BENCHMARK_SERIES if args.benchmark else ("sudden",))
    sizes = args.batch_sizes or ([256, 64, 16, 1] if args.benchmark else [256])
    if len(set(names)) != len(names) or len(set(sizes)) != len(sizes):
        parser.error("series and batch sizes must be distinct")
    run(
        args.output,
        [replay_input(name, benchmark=args.benchmark) for name in names],
        sizes,
        args.methods,
    )


if __name__ == "__main__":
    main()
