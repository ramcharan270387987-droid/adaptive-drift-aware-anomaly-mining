"""Verify NAB provenance and quality reporting with small local fixtures."""

import hashlib
from io import BytesIO
from pathlib import Path

import pytest
import yaml

from drift_anomaly import nab

CONFIG = Path(__file__).resolve().parents[1] / "configs/nab.yaml"


def test_load_pinned_config_and_derive_provenance():
    config = nab.load_config(CONFIG)
    manifest = nab.provenance(config)
    assert manifest["source"] == "https://github.com/numenta/NAB"
    assert manifest["revision"] == config["revision"]
    assert len(config["development"]) == len(config["final_evaluation"]) == 5
    assert len(manifest["files"]) == 13
    for name, entry in manifest["files"].items():
        assert entry["url"] == f"{nab.RAW_SOURCE}/{config['revision']}/{name}"


@pytest.mark.parametrize(
    ("name", "error"),
    [("../outside.csv", "invalid NAB series path"), (None, "splits must be disjoint")],
)
def test_config_rejects_unsafe_or_overlapping_series(tmp_path, name, error):
    config = nab.load_config(CONFIG)
    config["final_evaluation"][name or next(iter(config["development"]))] = "0" * 64
    path = tmp_path / "nab.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        nab.load_config(path)


def test_fetch_validates_before_caching_and_checks_cached_bytes(tmp_path, monkeypatch):
    data = b"checked payload"
    sha = hashlib.sha256(data).hexdigest()
    manifest = {"files": {"data/example.csv": {"sha256": sha, "url": "fixture"}}}
    monkeypatch.setattr(nab, "provenance", lambda config: manifest)
    calls = []

    def download(url, *, timeout):
        calls.append((url, timeout))
        return BytesIO(data)

    path = tmp_path / "data/example.csv"
    monkeypatch.setattr(nab, "urlopen", download)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        manifest["files"]["data/example.csv"]["sha256"] = "0" * 64
        nab.fetch({}, tmp_path)
    assert not path.exists()

    manifest["files"]["data/example.csv"]["sha256"] = sha
    nab.fetch({}, tmp_path)
    nab.fetch({}, tmp_path)
    assert calls == [("fixture", 30), ("fixture", 30)]
    assert path.read_bytes() == data
    assert (tmp_path / "provenance.json").is_file()
    path.write_bytes(b"corruption")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        nab.fetch({}, tmp_path)
    assert path.read_bytes() == b"corruption"


def test_audit_counts_quality_issues_in_source_order(tmp_path):
    path = tmp_path / "stream.csv"
    path.write_text(
        "timestamp,value\n"
        "2024-01-01 00:00:00,1\n"
        "2024-01-01 00:05:00,2\n"
        "2024-01-01 00:05:00,2\n"
        "2024-01-01 00:03:00,NaN\n"
        "2024-01-01 00:08:00,abc\n"
        "bad,\n"
        ",3,extra\n",
        encoding="utf-8",
    )
    result = nab.audit_series(
        path,
        ["2024-01-01 00:05:00", "2024-01-01 00:06:00"],
        [["2024-01-01 00:04:00.000000", "2024-01-01 00:06:00.000000"]],
    )
    assert result["rows"] == 7
    assert result["duplicate_rows"] == result["duplicate_timestamps"] == 1
    assert result["malformed_rows"] == result["non_monotonic_steps"] == 1
    assert result["missing_values"] == result["missing_timestamps"] == 1
    assert result["invalid_numeric_values"] == 2
    assert result["invalid_timestamps"] == 1
    assert result["timestamp_min"] == "2024-01-01 00:00:00"
    assert result["timestamp_max"] == "2024-01-01 00:08:00"
    assert result["sampling_seconds"]["mode"] == 300
    assert result["labels"]["anomaly_count"] == 2
    assert result["labels"]["point_labels_matched"] == 1
    assert result["labels"]["point_labels_with_multiple_observations"] == 1
    assert result["labels"]["windows_with_observations"] == 1


def test_audit_distinguishes_unlabeled_series_from_zero_anomalies(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("timestamp,value\n", encoding="utf-8")
    assert nab.audit_series(path, None, None)["labels"]["anomaly_count"] is None
    assert nab.audit_series(path, [], [])["labels"]["anomaly_count"] == 0
