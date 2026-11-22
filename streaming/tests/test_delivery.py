"""Tests for paced, partitioned streaming and the Streamlit runtime."""

import json
import pickle
from dataclasses import replace
from pathlib import Path

import pytest
from drift_streaming.evaluate import reconcile
from drift_streaming.explain import explain
from drift_streaming.inputs import BENCHMARK_NAB, publish, replay_input
from drift_streaming.live import plan, run_live
from drift_streaming.spark import drain, local_session
from drift_streaming.state import BatchSink
from pyspark.errors import StreamingQueryException
from streamlit.testing.v1 import AppTest

DASHBOARD = Path("streaming/dashboard.py")
METHOD = ("full",)


def test_fractional_pacing_plan_is_deterministic_and_complete():
    rows = list(range(5))
    expected = [(2, [0]), (3, [1]), (4, [2]), (6, [3]), (7, [4])]
    assert list(plan(rows, 0.75)) == list(plan(rows, 0.75)) == expected


@pytest.fixture(scope="module")
def spark_session():
    session = local_session()
    try:
        yield session
    finally:
        session.stop()


def test_paced_keyed_partitions_keep_distinct_models(spark_session):
    from tempfile import TemporaryDirectory

    Path("results").mkdir(exist_ok=True)
    with TemporaryDirectory(dir="results") as folder:
        a = replay_input("sudden", benchmark=True)
        b = replace(
            a,
            stream_id="shifted",
            observations=tuple(
                replace(row, value=row.value + 30) for row in a.observations
            ),
        )
        output = Path(folder) / "two"
        summary = run_live(
            spark_session,
            output,
            [a, b],
            METHOD,
            rate=4096,
            interval=0.25,
            partitions=3,
        )
        assert summary["records"] == 1792 and summary["dropped_or_failed_records"] == 0
        import sqlite3
        from contextlib import closing

        with closing(sqlite3.connect(output / "query/state.sqlite")) as db:
            models = {
                row[0]: json.loads(row[1])["mean"]
                for row in db.execute("SELECT stream,payload FROM events WHERE idx=256")
            }
        assert models["shifted"] - models["sudden"] == pytest.approx(30)


def test_cooldown_recovers_after_retry(spark_session, tmp_path):
    data = replay_input("sudden", benchmark=True)
    source, work = tmp_path / "input", tmp_path / "work"
    publish(source, [data.rows()], 64)

    def stop(batch):
        if batch == 8:
            raise RuntimeError("forced stop inside model cooldown")

    with pytest.raises(StreamingQueryException, match="forced stop"):
        drain(spark_session, source, work, METHOD, partitions=2, after_commit=stop)
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(work / "state.sqlite")) as db:
        state = pickle.loads(db.execute("SELECT payload FROM states").fetchone()[0])
        assert state.version == 1 and state.next_index == 576
        assert state.detector._cooldown_end == 671
    sink, batches, _ = drain(spark_session, source, work, METHOD, partitions=2)
    assert batches[0]["batch_id"] == 8 and not batches[0]["committed"]
    reconcile([data], METHOD, sink.records())


def test_explanations_preserve_model_order_and_use_no_truth(tmp_path):
    data = replay_input("sudden", benchmark=True)
    sink = BatchSink(tmp_path / "state.sqlite", METHOD, {})
    from dataclasses import asdict

    sink.commit(0, (json.dumps(asdict(row)) for row in data.rows()))
    events = sink.records()
    details = explain(events)
    assert details == explain(
        [dict(row, anomaly_label=True, regime="unused") for row in events]
    )
    assert {d["classification"] for d in details} >= {
        "NORMAL",
        "ANOMALY",
        "DRIFT_SUSPECTED",
        "MODEL_ADAPTED",
    }
    refit = next(d for d in details if d["classification"] == "MODEL_ADAPTED")
    assert refit["index"] == 543 and refit["old_model"] != refit["new_model"]
    assert refit["scoring_model_version"] == 0 and refit["model_version"] == 1
    assert details[544]["cooldown_applied_at_row"]
    assert any(
        entry["used_in_refit"]
        for d in details
        for entry in d["posthoc_checkpoint_membership"]
    )


@pytest.mark.parametrize("source", ["sudden", BENCHMARK_NAB])
def test_dashboard_streamlit_runtime_end_to_end(source):
    app = AppTest.from_file(DASHBOARD, default_timeout=20).run()
    assert not app.exception and len(app.info) == 1
    app.sidebar.radio[0].set_value("Live replay").run()
    app.sidebar.selectbox[0].set_value(source)
    app.sidebar.select_slider[0].set_value(4.0)
    app.sidebar.button[0].click().run()
    job = app.session_state["job"]
    journal = app.session_state["run_dir"]
    try:
        assert job.wait(timeout=60) == 0, (journal / "job.log").read_text()
        app.run()
        assert not app.exception
        assert app.metric[0].value == "896"
        assert len(app.get("plotly_chart")) == 1
        assert any("Decision explanation" in item.value for item in app.subheader)
        if source == "sudden":
            assert [m.value for m in app.metric[1:]] == ["110", "1", "1"] or (
                int(app.metric[1].value) > 0
                and [m.value for m in app.metric[2:]] == ["1", "1"]
            )
            app.toggle[1].set_value(False).run()
            app.slider[0].set_value(543).run()
            assert any("MODEL_ADAPTED" in item.value for item in app.markdown)
            app.checkbox[0].check().run()
            assert "Synthetic truth" in app.get("plotly_chart")[0].proto.spec
            app.toggle[0].set_value(True).run()
            assert app.session_state["paused"]
        else:
            assert not app.checkbox
    finally:
        app.sidebar.button[1].click().run()
    assert len(app.info) == 1 and "run_dir" not in app.session_state


def test_dashboard_renders_sealed_tables_and_rejects_invalid_series():
    app = AppTest.from_file(DASHBOARD).run()
    app.sidebar.radio[0].set_value("Research results").run()
    assert len(app.dataframe) == 4
    app.sidebar.radio[0].set_value("Spark performance").run()
    assert len(app.dataframe) == 2
    with pytest.raises(ValueError, match="approved NAB development"):
        replay_input("realKnownCause/nyc_taxi.csv")
