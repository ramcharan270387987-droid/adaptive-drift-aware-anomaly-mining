"""Local faculty demonstration over the trusted Spark output journal."""

import json
import os
import signal
import sqlite3
import subprocess
import sys
from contextlib import closing
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

import plotly.graph_objects as go
import streamlit as st
from drift_streaming.explain import explain
from drift_streaming.inputs import SYNTHETIC, replay_input
from drift_streaming.state import METHODS

from drift_anomaly import nab

RUN_ROOT = Path("results/dashboard")
EVIDENCE = Path("docs/evidence/delivery.json")
LABELS = {
    "static_zscore": "Static Z-score",
    "persistence": "ADWIN + persistence",
    "full": "Full selective policy",
    "fixed_schedule": "Fixed schedule",
    "immediate": "Immediate ADWIN",
    "filtering": "Persistence + filtering",
    "isolation_forest": "Isolation Forest",
    "lof": "Local Outlier Factor",
    "zscore_adwin_no_adaptation": "Z-score + ADWIN (frozen)",
    "zscore_page_hinkley_no_adaptation": "Z-score + Page-Hinkley (frozen)",
}
QUESTION = (
    "Can explicit concept-drift detection and selective model adaptation reduce false anomaly "
    "alarms after distribution changes without reducing sensitivity to genuine anomalies?"
)


def start_job(series, method, speed):
    run = RUN_ROOT / uuid4().hex
    run.mkdir(parents=True)
    with (run / "job.log").open("w") as log:
        job = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "drift_streaming.live",
                "--series",
                series,
                "--methods",
                method,
                "--speed",
                str(speed),
                "--rate",
                "96",
                "--interval",
                "0.25",
                "--output",
                str(run / "output"),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env={**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"},
        )
    return run, job


def reset_job():
    job = st.session_state.pop("job", None)
    if job is not None and job.poll() is None:
        os.killpg(job.pid, signal.SIGTERM)
    for key in (
        "run_dir",
        "selected_series",
        "selected_method",
        "last_view",
        "paused",
        "selected_index",
    ):
        st.session_state.pop(key, None)


def read_journal(run, stream_id, method):
    database = run / "output/query/state.sqlite"
    if not database.is_file():
        return []
    try:
        with closing(
            sqlite3.connect(
                f"{database.resolve().as_uri()}?mode=ro", uri=True, timeout=1
            )
        ) as db:
            return [
                json.loads(value)
                for (value,) in db.execute(
                    "SELECT payload FROM events WHERE stream = ? AND method = ? ORDER BY idx",
                    (stream_id, method),
                )
            ]
    except sqlite3.OperationalError as error:
        if "no such table" in str(error):
            return []
        raise


@lru_cache
def synthetic_overlay(series):
    source = replay_input(series, benchmark=True)
    return (
        [row.index for row in source.observations if row.anomaly_label],
        tuple((event.start, event.end) for event in source.drift_events),
    )


def stream_plot(rows, series, reveal_truth):
    figure = go.Figure()
    figure.add_scatter(
        x=[r["index"] for r in rows],
        y=[r["value"] for r in rows],
        mode="lines",
        name="Observation",
        line={"color": "#116d82", "width": 2},
    )
    for key, label, color, shape in (
        ("prediction", "Predicted anomaly", "#c24b31", "circle"),
        ("drift_alarm", "ADWIN alarm", "#ab6900", "triangle-up"),
        ("adaptation_event", "Refit", "#08795d", "diamond"),
    ):
        selected = [r for r in rows if r[key]]
        figure.add_scatter(
            x=[r["index"] for r in selected],
            y=[r["value"] for r in selected],
            name=label,
            mode="markers",
            marker={"size": 10, "color": color, "symbol": shape},
        )
    if reveal_truth and series in SYNTHETIC:
        positions, boundaries = synthetic_overlay(series)
        lookup = {r["index"]: r["value"] for r in rows}
        marks = [p for p in positions if p in lookup]
        figure.add_scatter(
            x=marks,
            y=[lookup[i] for i in marks],
            name="Synthetic truth",
            mode="markers",
            marker={"symbol": "x", "color": "#7050a4", "size": 10},
        )
        for start, end in boundaries:
            if start in lookup:
                if start == end:
                    figure.add_vline(x=start, line_dash="dot", line_color="#7050a4")
                else:
                    figure.add_vrect(
                        x0=start,
                        x1=min(end, rows[-1]["index"]),
                        opacity=0.12,
                        fillcolor="#7050a4",
                        line_width=0,
                    )
    figure.update_layout(
        height=430,
        xaxis_title="Observation index",
        yaxis_title="Raw value",
        legend={"orientation": "h", "y": 1.12},
        margin={"t": 36, "b": 30},
    )
    return figure


@st.fragment(run_every=0.5)
def live_view(overview=False):
    run = st.session_state.get("run_dir")
    if run is None:
        st.info("Choose a development source and select Start replay.")
        return
    series = st.session_state["selected_series"]
    method = st.session_state["selected_method"]
    job = st.session_state.get("job")
    code = job.poll() if job is not None else 0
    status = (
        "Streaming"
        if code is None
        else "Replay complete"
        if code == 0
        else "Replay failed"
    )
    st.subheader(status)
    st.caption(f"{series} · {LABELS[method]}")
    if code not in (0, None):
        st.error(
            "The streaming process stopped. Review the local job log, reset, and retry."
        )
    try:
        if st.session_state.get("paused") and "last_view" in st.session_state:
            rows = st.session_state["last_view"]
        else:
            rows = read_journal(run, series, method)
            st.session_state["last_view"] = rows
    except sqlite3.Error:
        st.error("The committed prediction journal could not be read.")
        return
    for column, label, value in zip(
        st.columns(4),
        ("Records", "Anomalies", "ADWIN alarms", "Refits"),
        (
            len(rows),
            sum(r["prediction"] is True for r in rows),
            sum(r["drift_alarm"] for r in rows),
            sum(r["adaptation_event"] for r in rows),
        ),
        strict=True,
    ):
        column.metric(label, value)
    if not rows:
        return
    decisions = explain(rows)
    if overview:
        st.write("Current model", decisions[-1]["current_model"] or "Warming up")
        return
    st.toggle(
        "Pause display",
        key="paused",
        help="Spark continues committing rows while the view is paused.",
    )
    truth = (
        st.checkbox("Show synthetic evaluation overlays")
        if series in SYNTHETIC
        else False
    )
    st.plotly_chart(stream_plot(rows, series, truth), key="stream_plot")
    follow = st.toggle("Follow latest observation", value=True)
    position = (
        len(rows) - 1
        if follow
        else st.slider("Observation index", 0, len(rows) - 1, key="selected_index")
        if len(rows) > 1
        else 0
    )
    item = decisions[position]
    explanation, model = st.columns([3, 2])
    with explanation:
        st.subheader("Decision explanation")
        st.markdown(f"**{item['classification']}** · observation {item['index']}")
        st.write(item["reason"])
        st.write(
            f"Score {item['score']} · threshold {item['threshold']:.1f} · signed Z {item['z_score']}"
        )
        st.write(
            f"ADWIN alarm {item['adwin_alarm']} · persistence {item['persistence']}"
        )
        with st.expander("Candidate, refit and retrospective membership"):
            st.json(
                {
                    key: item[key]
                    for key in (
                        "candidate",
                        "checkpoint",
                        "old_model",
                        "new_model",
                        "posthoc_checkpoint_membership",
                    )
                },
                expanded=False,
            )
    with model:
        st.subheader("Model state")
        st.json(
            {
                "reference_at_score": {
                    "mean": item["scoring_mean"],
                    "std": item["scoring_std"],
                },
                "reference_after_observation": item["current_model"],
                "version": item["model_version"],
                "refits": item["model_version"],
                "last_refit": item["last_refit_index"],
                "cooldown_through": item["cooldown_through_index"],
            },
            expanded=True,
        )


def evidence_view(performance):
    try:
        data = json.loads(EVIDENCE.read_text())
    except (OSError, ValueError):
        st.error("Published evidence could not be loaded.")
        return
    if performance:
        st.subheader("Single-host local Spark benchmark")
        st.caption("Spark local[2] · 2 shuffle partitions in the paced runs · CPU only")
        st.dataframe(
            [
                {
                    "Streams": row["source_count"],
                    "Target rows/s": row["target_arrival_records_sec"],
                    "Committed rows/s": round(row["sustained_records_sec"]),
                    "p95 backlog (s)": round(
                        row["producer_to_commit_latency_seconds"]["p95"], 3
                    ),
                    "RSS (MiB)": round(
                        row["peak_sampled_process_tree_rss_bytes"] / 2**20
                    ),
                    "Batch interval (s)": row["interval_seconds"],
                }
                for row in data["spark_sustained"]
            ],
            hide_index=True,
        )
        st.subheader("Backlog replay by batch size")
        st.dataframe(
            [
                {
                    "Rows per stream": size,
                    "Input rows/s": round(row["input_records_per_second"]),
                    "p95 latency (s)": round(
                        row["backlog_latency_seconds_per_input_record"]["p95"], 3
                    ),
                    "RSS (MiB)": round(
                        row["peak_sampled_process_tree_rss_bytes"] / 2**20
                    ),
                }
                for size, row in data["spark_backlog"].items()
            ],
            hide_index=True,
        )
        return
    st.subheader("Sealed research results")
    st.caption(f"Frozen evaluation revision {data['research_revision'][:12]}")
    st.write(
        "The full policy passed both synthetic confirmatory criteria. On final NAB it detected one extra labeled point and increased false positives."
    )
    for key, title in (("synthetic", "Final synthetic holdout"), ("nab", "Final NAB")):
        st.subheader(title)
        st.dataframe(
            [
                {
                    "Method": LABELS.get(name, name),
                    "TP": row["tp"],
                    "FP": row["fp"],
                    "Recall": round(row["recall"], 4),
                    "F1": round(row["f1"], 4),
                    "FPR": round(row["false_positive_rate"], 4),
                }
                for name, row in data[key].items()
            ],
            hide_index=True,
        )
    st.subheader("Update efficiency")
    st.dataframe(
        [
            {
                "Method": LABELS.get(name, name),
                "Refits": row["refits"],
                "Refit inputs": row["refit_input_uses"],
            }
            for name, row in data["update_efficiency"].items()
        ],
        hide_index=True,
    )
    with st.expander("Representative failures and limitations"):
        st.dataframe(data["failures"], hide_index=True)
        st.write(
            "NAB provides anomaly annotations and has no independent drift truth. The synthetic inputs are univariate Gaussian streams with scripted changes."
        )


def app():
    st.set_page_config(page_title="Drift-aware anomaly mining", layout="wide")
    st.title("Adaptive Drift-Aware Anomaly Mining")
    page = st.sidebar.radio(
        "View", ("Overview", "Live replay", "Research results", "Spark performance")
    )
    datasets = tuple(nab.load_config(Path("configs/nab.yaml"))["development"])
    with st.sidebar.form("replay"):
        selected = st.selectbox("Development source", (*SYNTHETIC, *datasets))
        method = st.selectbox(
            "Detector policy", METHODS, index=2, format_func=LABELS.get
        )
        speed = st.select_slider(
            "Replay speed", options=(0.5, 1.0, 2.0, 4.0), value=2.0
        )
        start = st.form_submit_button("Start replay", type="primary")
    if st.sidebar.button("Reset replay"):
        reset_job()
    if start:
        if selected not in (*SYNTHETIC, *datasets) or method not in METHODS:
            st.error("Choose an approved development source and detector policy.")
        else:
            reset_job()
            try:
                run, job = start_job(selected, method, speed)
            except OSError:
                st.error("Unable to start the local Spark replay.")
            else:
                st.session_state.update(
                    run_dir=run,
                    job=job,
                    selected_series=selected,
                    selected_method=method,
                )
    if page == "Overview":
        st.markdown(QUESTION)
        live_view(overview=True)
    elif page == "Live replay":
        live_view()
    else:
        evidence_view(page == "Spark performance")


app()
