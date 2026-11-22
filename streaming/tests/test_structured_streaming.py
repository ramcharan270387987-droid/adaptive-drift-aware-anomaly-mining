"""Exercise the ordered file source, frozen state and checkpoint replay."""

import json

import pytest
from drift_streaming.evaluate import reconcile
from drift_streaming.inputs import publish, replay_input
from drift_streaming.spark import drain, local_session
from drift_streaming.state import BatchSink, InputRow
from pyspark.errors import StreamingQueryException

METHODS = ("static_zscore", "persistence", "full")
STAMP = "2000-01-01T00:00:00.000000"


@pytest.fixture(scope="module")
def spark():
    session = local_session()
    assert session.version == "4.1.1"
    assert session.sparkContext.master == "local[2]"
    try:
        yield session
    finally:
        session.stop()


def row(index, **fields):
    return json.dumps(
        {
            "stream_id": "series",
            "index": index,
            "timestamp": STAMP,
            "value": 1,
            **fields,
        }
    )


@pytest.mark.parametrize(
    "line",
    [
        "not json",
        row(0, value=None),
        row(0, value=float("nan")),
        row(0, value=float("inf")),
        row(0, value="2.0"),
        row(0, timestamp="2000-01-01T00:00:00.000000+00:00"),
        row(0, timestamp="bad"),
        row(0, anomaly_label=True),
        row(-1),
        row(0).replace('"index": 0', '"index": 1, "index": 0'),
    ],
)
def test_schema_rejects_bad_rows_and_labels(line):
    with pytest.raises(ValueError):
        InputRow.parse(line)


def test_ties_sort_by_index_and_transaction_rolls_back_on_invalid_order(tmp_path):
    sink = BatchSink(tmp_path / "state.sqlite", ("full",), {})
    assert sink.commit(0, [row(1), row(0)])
    assert not sink.commit(0, [row(0), row(1)])
    assert [event["index"] for event in sink.records()] == [0, 1]
    with pytest.raises(ValueError, match="changed on recovery"):
        sink.commit(0, [row(0), row(1, value=9)])
    with pytest.raises(ValueError, match="expected index 3"):
        sink.commit(1, [row(2), row(2)])
    with pytest.raises(ValueError, match="nondecreasing timestamp"):
        sink.commit(1, [row(2, timestamp="1999-01-01T00:00:00.000000")])
    assert len(sink.records()) == 2
    assert sink.commit(1, [])
    assert sink.commit(2, [row(2)])


def test_batch_size_invariance_and_score_before_refit(spark, tmp_path):
    stream = replay_input("sudden", benchmark=True)
    gold = None
    for size in (64, 256):
        work = tmp_path / str(size)
        publish(work / "input", [stream.rows()], size)
        sink, batches, _ = drain(spark, work / "input", work / "query", METHODS)
        records = sink.records()
        summaries = reconcile([stream], METHODS, records)
        assert [b["rows"] for b in batches if b["rows"]][-1] == (
            128 if size == 256 else 64
        )
        assert summaries["sudden:full"]["alarms"] > 0
        assert summaries["sudden:full"]["refits"] > 0
        full = [r for r in records if r["method"] == "full"]
        assert full[255]["warmup"] and not full[256]["warmup"]
        at = next(r["index"] for r in full if r["adaptation_event"])
        assert full[at]["model_version"] == 0
        assert full[at + 1]["model_version"] == 1
        assert full[at]["mean"] != full[at + 1]["mean"]
        if gold is None:
            gold = records
        else:
            assert records == gold


def test_restart_retries_committed_batches_and_keeps_warmup_and_pending_proposal(
    spark, tmp_path
):
    stream = replay_input("sudden", benchmark=True)
    source, work = tmp_path / "input", tmp_path / "query"
    publish(source, [stream.rows()], 64)

    def fault_at(target):
        def fail(batch_id):
            if batch_id == target:
                raise RuntimeError("simulated failure after durable commit")

        return fail

    # Terminate once during warm-up and again after the first ADWIN alarm.
    for cutoff in (2, 5):
        with pytest.raises(StreamingQueryException, match="simulated failure"):
            drain(spark, source, work, METHODS, after_commit=fault_at(cutoff))
    sink, batches, _ = drain(spark, source, work, METHODS)
    assert batches[0]["batch_id"] == 5 and not batches[0]["committed"]
    outputs = sink.records()
    assert len(outputs) == len(METHODS) * len(stream.observations)
    full = [r for r in outputs if r["method"] == "full"]
    assert 256 < next(r["index"] for r in full if r["drift_alarm"]) < 384
    assert next(r["index"] for r in full if r["adaptation_event"]) >= 384
    reconcile([stream], METHODS, outputs)
    _, batches_after_drain, _ = drain(spark, source, work, METHODS)
    assert not batches_after_drain


def test_invalid_file_fails_query_without_committing_a_batch(spark, tmp_path):
    source, work = tmp_path / "input", tmp_path / "query"
    source.mkdir()
    (source / "invalid.jsonl").write_text(row(0, value=None) + "\n")
    with pytest.raises(StreamingQueryException, match="finite number"):
        drain(spark, source, work, METHODS)
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(work / "state.sqlite")) as db:
        assert db.execute("SELECT COUNT(*) FROM batches").fetchone() == (0,)
        assert db.execute("SELECT COUNT(*) FROM events").fetchone() == (0,)


def test_sources_reject_final_nab_identity():
    with pytest.raises(ValueError, match="approved NAB development"):
        replay_input("realKnownCause/nyc_taxi.csv")
