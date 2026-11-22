"""Exercise split barriers, label mapping, provenance, statistics and the freeze."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from drift_anomaly import nab
from drift_anomaly.experiments import final_evaluation, static_baseline, validation
from drift_anomaly.experiments.nab_evaluation import run_nab
from drift_anomaly.experiments.validation_cases import FailureCases
from drift_anomaly.experiments.validation_stats import paired_seed_summary
from drift_anomaly.nab_replay import _parse_rows, load_development_series
from drift_anomaly.replay import Prediction

DEV = "test/dev.csv"
FINAL = "test/final.csv"


@pytest.fixture
def mock_nab(tmp_path, monkeypatch):
    import drift_anomaly.nab_replay as loader

    revision = "a" * 40
    source = tmp_path / revision
    config = {
        "revision": revision,
        "development": {},
        "final_evaluation": {FINAL: "0" * 64},
        "metadata": {"LICENSE.txt": "0" * 64},
    }

    def write(name, data):
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return hashlib.sha256(data).hexdigest()

    prefix = "2020-01-01 00:00:00,1\n" * 256
    csv = (
        "timestamp,value\n"
        + prefix
        + "2020-01-01 00:01:00,10\n2020-01-01 00:01:00,10\n"
        + "2020-01-01 00:02:00,2\n"
    )
    config["development"][DEV] = write(f"data/{DEV}", csv.encode())
    # The unselected annotation bodies cannot be deserialized.
    points = f'{{\n"{DEV}": ["2020-01-01 00:01:00"],\n"{FINAL}": INVALID\n}}'
    windows = f'{{\n"{DEV}": [["2020-01-01 00:01:00","2020-01-01 00:02:00"]],\n"{FINAL}": INVALID\n}}'
    config["metadata"][nab.POINT_LABELS] = write(nab.POINT_LABELS, points.encode())
    config["metadata"][nab.WINDOW_LABELS] = write(nab.WINDOW_LABELS, windows.encode())
    manifest = tmp_path / "nab.yaml"
    manifest.write_text(yaml.safe_dump(config))
    monkeypatch.setattr(loader, "MANIFEST", manifest)
    return tmp_path, source


def test_nab_verified_point_and_window_replay_has_scalar_only_detector(mock_nab):
    stream = load_development_series(DEV, raw=mock_nab[0])
    assert stream.source == mock_nab[1] / "data" / DEV
    assert stream.checksum == hashlib.sha256(stream.source.read_bytes()).hexdigest()
    assert stream.duplicate_timestamps == 256
    assert [row.anomaly_label for row in stream.observations[-3:]] == [
        True,
        False,
        False,
    ]
    assert all(
        row.drift_phase is None and row.regime is None for row in stream.observations
    )
    calls = []

    class ScalarDetector:
        identifier = "test"

        def fit_initial(self, values):
            assert values == (1.0,) * 256

        def score_one(self, value):
            calls.append(("score", value))
            return Prediction(value, value > 5)

        def update_one(self, value):
            calls.append(("update", value))

    summary = run_nab(
        [stream], [validation.Arm("static_zscore", ScalarDetector)], FailureCases()
    )
    assert calls == [
        (action, value) for value in (10.0, 10.0, 2.0) for action in ("score", "update")
    ]
    row = summary["by_arm"]["static_zscore"][0]
    assert (row["tp"], row["fp"], row["tn"], row["fn"]) == (1, 1, 1, 0)
    assert (row["eligible_windows"], row["window_hits"]) == (1, 1)
    assert "drift_window" not in row
    assert row["drift_truth_available"] is False


@pytest.mark.parametrize("series", [FINAL, "../test/dev.csv"])
def test_nab_rejects_unselected_series_before_reading_files(mock_nab, series):
    with pytest.raises(ValueError, match="outside the development split"):
        load_development_series(series, raw=mock_nab[0] / "nonexistent")


@pytest.mark.parametrize("file", [f"data/{DEV}", nab.POINT_LABELS, nab.WINDOW_LABELS])
def test_nab_rejects_corrupted_pinned_bytes(mock_nab, file):
    (mock_nab[1] / file).write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        load_development_series(DEV, raw=mock_nab[0])


def test_nab_keeps_ties_and_rejects_backwards_development_rows():
    content = (
        b"timestamp,value\n2020-01-01 00:01:00,10\n"
        b"2020-01-01 00:00:00,11\n2020-01-01 00:01:00,12\n"
    )
    with pytest.raises(ValueError, match="goes backwards"):
        _parse_rows(content, skip_backwards=False)
    rows, duplicates, backwards = _parse_rows(content, skip_backwards=True)
    assert [value for _, value in rows] == [10.0, 12.0]
    assert (duplicates, backwards) == (1, 1)


@pytest.mark.parametrize("value", ["NaN", "Inf", ""])
def test_nab_rejects_non_finite_or_missing_values(value):
    with pytest.raises(ValueError, match="requires a finite value"):
        _parse_rows(
            f"timestamp,value\n2020-01-01 00:00:00,{value}\n".encode(),
            skip_backwards=False,
        )


def test_robustness_identity_and_pairing_without_generating_any_stream():
    experiment = validation.frozen_experiment(validation.ROBUSTNESS_GRID)
    scenarios = [cfg for _, _, cfg in static_baseline.scenarios(experiment)]
    assert len(scenarios) == len(set(scenarios)) == 250
    assert {cfg.seed for cfg in scenarios} == set(range(2000, 2010))
    assert {cfg.drift_start for cfg in scenarios if cfg.drift_type != "none"} == {
        1603,
        2747,
    }
    assert {
        cfg.drift_duration
        for cfg in scenarios
        if cfg.drift_type in ("gradual", "incremental")
    } == {192, 384}
    assert {cfg.post_mean for cfg in scenarios if cfg.drift_type != "none"} == {
        1.0,
        2.25,
    }
    assert all(cfg.n_observations == 4096 and cfg.warmup == 256 for cfg in scenarios)
    for cfg in scenarios:
        clean, injected = [pair for _, pair in static_baseline.paired_variants(cfg)]
        assert clean == replace(injected, anomaly_count=0, anomaly_fraction=None)
        assert injected.injection_count == 12

    with pytest.raises(ValueError, match="outside"):
        validation._replay_frozen(
            replace(scenarios[0], seed=1000),
            None,
            config_path=Path("unused"),
            grid=validation.ROBUSTNESS_GRID,
            split="robustness",
        )


def test_seed_bootstrap_is_repeatable_and_reports_effect_direction():
    blocks = [[float(seed), float(seed)] for seed in range(1, 11)]
    summary = paired_seed_summary(blocks)
    assert summary == paired_seed_summary(blocks)
    assert summary["observed_difference"] == summary["median"] == 5.5
    assert summary["ci95"][0] > 0
    assert summary["rank_biserial"] == 1
    assert summary["wilcoxon_p"] == pytest.approx(2 / 1024)
    assert paired_seed_summary([[0.0]] * 10)["wilcoxon_p"] is None


def test_final_manifest_validates_exact_freeze_and_rejects_drift(tmp_path):
    manifest = tmp_path / "freeze.yaml"
    spec = json.loads(json.dumps(final_evaluation.frozen_spec()))
    manifest.write_text(yaml.safe_dump(spec))
    assert final_evaluation.load_frozen(manifest) == spec
    spec["models"]["selective"]["persistence_cutoff"] = 0.75
    manifest.write_text(yaml.safe_dump(spec))
    with pytest.raises(ValueError, match="modified"):
        final_evaluation.load_frozen(manifest)


@pytest.mark.parametrize("complete", [True, False])
def test_final_cli_refuses_unfrozen_or_unauthorized_execution(
    tmp_path, monkeypatch, capsys, complete
):
    manifest = tmp_path / "freeze.yaml"
    spec = final_evaluation.frozen_spec() if complete else {"status": "frozen"}
    manifest.write_text(yaml.safe_dump(spec))
    monkeypatch.setattr("sys.argv", ["final_evaluation", "--config", str(manifest)])
    monkeypatch.setattr(
        final_evaluation, "run_final", lambda _: pytest.fail("opened final outcomes")
    )
    with pytest.raises(SystemExit) as error:
        final_evaluation.main()
    assert error.value.code == 1
    assert ("--authorize-final" if complete else "unfrozen") in capsys.readouterr().err


def test_split_acquisition_only_requests_development_csvs(mock_nab, monkeypatch):
    import drift_anomaly.nab_replay as loader

    requested = []
    monkeypatch.setattr(nab, "_fetch_files", lambda files, _: requested.extend(files))
    config = nab.load_config(loader.MANIFEST)
    nab.fetch_split(config, mock_nab[1], "development")
    assert set(requested) == {*nab.METADATA, f"data/{DEV}"}
