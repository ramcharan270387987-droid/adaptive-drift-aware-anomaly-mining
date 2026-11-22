"""Check small generated development streams and pre-replay safeguards."""

from pathlib import Path

import pytest
import yaml

from drift_anomaly.adwin import ADWINDetector
from drift_anomaly.experiments import selective_smoke
from drift_anomaly.replay import replay_synthetic_development
from drift_anomaly.selective_adaptation import SelectiveZScore
from drift_anomaly.synthetic import SyntheticConfig
from drift_anomaly.zscore import StaticZScore

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/experiments/adwin_dev.yaml"


@pytest.mark.parametrize(
    "family", ["none", "sudden", "gradual", "incremental", "recurring"]
)
def test_small_development_streams_keep_the_same_adwin_alarms(family):
    config = SyntheticConfig(
        family,
        0,
        n_observations=1750,
        post_mean=1.5,
        drift_start=None if family == "none" else 384,
        drift_duration=128 if family in ("gradual", "incremental") else None,
    )

    def run(factory):
        return replay_synthetic_development(config, factory, config_path=CONFIG)

    adwin = run(lambda: ADWINDetector(selective_smoke.FROZEN_ADWIN))
    selective = run(
        lambda: SelectiveZScore(
            StaticZScore(selective_smoke.FROZEN_ZSCORE),
            ADWINDetector(selective_smoke.FROZEN_ADWIN),
        )
    )
    expected = [
        r.observation.index
        for r in adwin.result.scored_records()
        if r.update is not None and r.update.drift_alarm
    ]
    log = selective_smoke.stream_diagnostics(selective)
    assert [alarm["index"] for alarm in log["alarms"]] == expected
    if family == "none":
        assert not expected and not log["proposals"]
    else:
        assert expected and log["proposals"]
    assert log["refit_input_uses"] == sum(
        checkpoint["retained_count"]
        for proposal in log["proposals"]
        for checkpoint in proposal["checkpoints"]
        if checkpoint["decision"] == "refit"
    )


@pytest.mark.parametrize(
    ("stream", "seed", "error"),
    [
        ("configs/synthetic/sudden_holdout.yaml", 0, "development replay requires"),
        ("configs/synthetic/sudden_dev.yaml", 1000, "grid seeds"),
        ("configs/nab.yaml", 0, "invalid synthetic config fields"),
    ],
)
def test_disallowed_inputs_stop_before_replay(
    tmp_path, monkeypatch, stream, seed, error
):
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    data["streams"] = [str(ROOT / stream)]
    data["grid"]["seeds"] = [seed]
    config = tmp_path / "adwin.yaml"
    config.write_text(yaml.safe_dump(data), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    def fail(*args, **kwargs):
        pytest.fail("disallowed input reached replay")

    monkeypatch.setattr(selective_smoke, "replay_synthetic_development", fail)
    with pytest.raises(ValueError, match=error):
        selective_smoke.run_smoke(config, Path("results/blocked"))
    assert not Path("results").exists()
