"""Verify causal replay mechanics with instrumented test detectors."""

import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from drift_anomaly import replay as harness
from drift_anomaly.replay import Observation, Prediction, UpdateEvent, replay

CONFIG_DIR = Path(__file__).resolve().parents[1] / "configs/synthetic"


class RecordingDetector:
    identifier = "recording-test"

    def __init__(self, calls):
        self.calls = calls
        self.total = 0.0

    def fit_initial(self, values):
        self.calls.append(("fit", values))
        self.total = sum(values)

    def score_one(self, value):
        assert type(value) is float
        self.calls.append(("score", value))
        return Prediction(score=self.total + value)

    def update_one(self, value):
        assert type(value) is float
        self.calls.append(("update", value))
        self.total += value


def test_source_advances_only_after_current_point_is_scored_and_updated():
    calls = []

    def source():
        calls.append(("pull", 0))
        yield Observation(0, 1.0, True, "pre_drift", "A")
        assert calls[-1] == ("fit", (1.0,))
        calls.append(("pull", 2))
        yield Observation(2, 4.0, True, "in_transition", "B")
        assert calls[-2:] == [("score", 4.0), ("update", 4.0)]
        calls.append(("pull", 5))
        yield Observation(5, 10.0)
        assert calls[-2:] == [("score", 10.0), ("update", 10.0)]

    result = replay(source(), lambda: RecordingDetector(calls), warmup=1)

    assert calls == [
        ("pull", 0),
        ("fit", (1.0,)),
        ("pull", 2),
        ("score", 4.0),
        ("update", 4.0),
        ("pull", 5),
        ("score", 10.0),
        ("update", 10.0),
    ]
    assert [record.prediction.score for record in result.scored_records()] == [
        5.0,
        15.0,
    ]
    assert result.stats.warmup_last_index == 0
    assert result.stats.first_scored_index == 2


def test_default_warmup_uses_only_prefix_and_is_excluded_from_scored_records():
    calls = []
    rows = [
        Observation(index, float(index), index in (10, 255, 256))
        for index in range(259)
    ]

    result = replay(iter(rows), lambda: RecordingDetector(calls))

    assert calls[0] == ("fit", tuple(float(index) for index in range(256)))
    assert calls[1:3] == [("score", 256.0), ("update", 256.0)]
    assert len(calls) == 7
    assert result.records[255].warmup is True
    assert result.records[255].prediction is None
    assert result.records[255].update is None
    first = next(result.scored_records())
    assert first.observation.anomaly_label is True
    assert first.warmup is False
    assert first.prediction.score == sum(range(257))
    assert result.stats.observation_count == 259
    assert result.stats.warmup_count == 256
    assert result.stats.scored_count == 3
    assert result.stats.warmup_anomaly_count == 2
    assert result.stats.warmup_last_index == 255
    assert result.stats.first_scored_index == 256
    assert result.stats.elapsed_seconds >= 0
    assert result.stats.observations_per_second == pytest.approx(
        259 / result.stats.elapsed_seconds
    )
    assert result.stats.scored_observations_per_second == pytest.approx(
        3 / result.stats.elapsed_seconds
    )


def test_same_inputs_replay_deterministically_with_fresh_state():
    observations = [Observation(index, float(index)) for index in range(6)]
    instances = []

    def factory():
        detector = RecordingDetector([])
        instances.append(detector)
        return detector

    first = replay(iter(observations), factory, warmup=2)
    second = replay(iter(observations), factory, warmup=2)
    assert len(instances) == 2
    assert instances[0] is not instances[1]
    assert first.records == second.records
    assert first.stats.scored_count == second.stats.scored_count == 4


def test_altering_future_observations_cannot_affect_earlier_scores():
    rows = [Observation(index, float(index)) for index in range(6)]
    changed = [*rows[:4], replace(rows[4], value=200.0), replace(rows[5], value=-300.0)]
    original = replay(rows, lambda: RecordingDetector([]), warmup=2)
    edited = replay(changed, lambda: RecordingDetector([]), warmup=2)
    assert original.records[:4] == edited.records[:4]
    assert original.records[4].prediction != edited.records[4].prediction


def test_ground_truth_does_not_affect_detector_calls_or_predictions():
    rows = [
        Observation(index, float(index), False, "stationary", "A") for index in range(4)
    ]
    changed = [
        replace(row, anomaly_label=True, drift_phase="in_transition", regime="B")
        for row in rows
    ]
    nominal_calls, altered_calls = [], []
    nominal = replay(rows, lambda: RecordingDetector(nominal_calls), warmup=1)
    altered = replay(changed, lambda: RecordingDetector(altered_calls), warmup=1)
    assert nominal_calls == altered_calls
    assert nominal.records[1].prediction == altered.records[1].prediction
    assert nominal.records[1].observation != altered.records[1].observation
    assert nominal.stats.warmup_anomaly_count == 0
    assert altered.stats.warmup_anomaly_count == 1


def test_prediction_snapshot_precedes_mutating_update_and_drift_events_remain_separate():
    class MutableMetadataDetector(RecordingDetector):
        def __init__(self):
            super().__init__([])
            self.metadata = {"values": []}

        def score_one(self, value):
            return Prediction(
                score=value, predicted_anomaly=value == 2.0, metadata=self.metadata
            )

        def update_one(self, value):
            self.metadata["values"].append(value)
            return UpdateEvent(drift_alarm=value == 2.0, metadata=self.metadata)

    result = replay(
        [Observation(4, 1.0), Observation(7, 2.0)],
        MutableMetadataDetector,
        warmup=0,
    )
    first, second = result.records
    assert first.prediction.metadata == {"values": []}
    assert first.update.metadata == {"values": [1.0]}
    assert second.prediction.metadata == {"values": [1.0]}
    assert second.prediction.predicted_anomaly is True
    assert second.prediction.drift_alarm is None
    assert second.update.drift_alarm is True
    assert second.update.metadata == {"values": [1.0, 2.0]}
    assert result.stats.warmup_last_index is None
    assert result.stats.first_scored_index == 4


def test_fully_warmup_stream_initializes_without_scoring():
    calls = []
    result = replay([Observation(8, 3.0)], lambda: RecordingDetector(calls), warmup=1)
    assert calls == [("fit", (3.0,))]
    assert list(result.scored_records()) == []
    assert result.stats.first_scored_index is None
    assert result.stats.scored_count == 0


@pytest.mark.parametrize(
    ("rows", "warmup", "message"),
    [
        ([], 0, "requires at least one observation"),
        ([Observation(0, 1.0)], 2, "received 1 observations for a warm-up of 2"),
        ([Observation(0, 1.0)], -1, "warmup must be a non-negative integer"),
        (
            [Observation(2, 1.0), Observation(2, 2.0)],
            1,
            "indices must be strictly increasing",
        ),
        (
            [Observation(2, 1.0), Observation(1, 2.0)],
            1,
            "indices must be strictly increasing",
        ),
        ([Observation(0, float("nan"))], 0, "non-finite observation at index 0"),
    ],
)
def test_invalid_input_rejected(rows, warmup, message):
    with pytest.raises(ValueError, match=message):
        replay(rows, lambda: RecordingDetector([]), warmup=warmup)


def test_non_finite_score_is_rejected_before_update():
    calls = []

    class InvalidScorer(RecordingDetector):
        def score_one(self, value):
            return Prediction(score=float("inf"))

    with pytest.raises(ValueError, match="non-finite score at index 0"):
        replay([Observation(0, 1.0)], lambda: InvalidScorer(calls), warmup=0)
    assert calls == [("fit", ())]


def test_development_entry_point_loads_only_the_selected_config(monkeypatch):
    selected = CONFIG_DIR / "sudden_dev.yaml"
    seen = []
    original = harness.load_config

    def tracked_load(path):
        seen.append(path)
        return original(path)

    monkeypatch.setattr(harness, "load_config", tracked_load)
    run = harness.replay_development(selected, lambda: RecordingDetector([]))

    assert seen == [selected]
    assert run.provenance.split == "development"
    assert run.provenance.stream_config_path == str(selected)
    assert run.provenance.stream_seed == 0
    assert run.result.stats.scored_count == 4096 - 256
    assert len(run.drift_events) == 1


@pytest.mark.parametrize(
    ("split", "seed"), [("final_evaluation", 1000), ("development", 1000)]
)
def test_reserved_inputs_are_rejected_before_generation_or_detector_creation(
    tmp_path, monkeypatch, split, seed
):
    def unexpected(*args):
        pytest.fail("reserved input was passed to generation or a detector")

    path = tmp_path / "renamed_dev.yaml"
    path.write_text(
        f"drift_type: none\nseed: {seed}\nsplit: {split}\n", encoding="utf-8"
    )
    monkeypatch.setattr(harness, "generate_stream", unexpected)
    with pytest.raises(ValueError, match="development replay requires"):
        harness.replay_development(path, unexpected)


def test_cli_smoke_exports_records_and_provenance(tmp_path):
    config = tmp_path / "test_dev.yaml"
    config.write_text(
        "split: development\ndrift_type: sudden\nseed: 1\nn_observations: 12\n"
        "drift_start: 6\nwarmup: 3\n",
        encoding="utf-8",
    )
    command = [
        sys.executable,
        "-m",
        "drift_anomaly.replay",
        "--config",
        str(config),
        "--warmup",
        "3",
        "--output",
        "results/tiny",
    ]
    completed = subprocess.run(
        command, cwd=tmp_path, capture_output=True, text=True, check=True
    )
    assert "12 observations, 3 warm-up, 9 score calls" in completed.stdout
    path = tmp_path / "results/tiny/replay.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["provenance"]["stream_config_path"] == str(config)
    assert payload["provenance"]["stream_seed"] == 1
    assert payload["provenance"]["drift_type"] == "sudden"
    assert payload["provenance"]["split"] == "development"
    assert payload["provenance"]["warmup_length"] == 3
    assert payload["provenance"]["detector_id"] == "infrastructure-smoke"
    assert payload["provenance"]["project_version"]
    assert payload["provenance"]["executed_at_utc"].endswith("+00:00")
    assert "git_commit" in payload["provenance"]
    assert payload["drift_events"][0]["start"] == 6
    assert [record["observation"]["index"] for record in payload["records"]] == list(
        range(12)
    )
    assert payload["records"][2]["warmup"] is True
    assert payload["records"][2]["prediction"] is None
    assert payload["records"][3]["warmup"] is False
    assert payload["records"][3]["prediction"]["score"] is None
    assert payload["records"][6]["observation"]["anomaly_label"] is False
    assert payload["records"][6]["observation"]["regime"] == "B"
    assert payload["stats"]["first_scored_index"] == 3
    assert payload["stats"]["scored_count"] == 9

    retry = subprocess.run(
        command, cwd=tmp_path, capture_output=True, text=True, check=False
    )
    assert retry.returncode == 1
    assert "already exists" in retry.stderr
    assert json.loads(path.read_text(encoding="utf-8")) == payload


def test_export_cannot_write_outside_results(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run = harness.replay_development(
        CONFIG_DIR / "sudden_dev.yaml", lambda: RecordingDetector([])
    )
    with pytest.raises(ValueError, match="new directory under results"):
        harness.export_replay(run, tmp_path / "other")
    assert not (tmp_path / "other").exists()
