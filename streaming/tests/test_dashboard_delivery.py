"""Regression checks for the dashboard launch and generated faculty handoff."""

import runpy
import socket
import subprocess
import sys
from pathlib import Path
from time import monotonic, sleep
from urllib.error import URLError
from urllib.request import urlopen
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = runpy.run_path(str(ROOT / "scripts/run_dashboard.py"))
EXPORTER = runpy.run_path(str(ROOT / "scripts/export_dashboard.py"))


def test_launcher_validates_committed_artifacts_and_names_missing_files(tmp_path):
    LAUNCHER["validate_artifacts"](ROOT)
    validate = LAUNCHER["validate_artifacts"]
    with pytest.raises(ValueError, match="Missing dashboard artifact: docs/evidence"):
        validate(tmp_path)
    for name in (
        "docs/evidence/delivery.json",
        "configs/nab.yaml",
        "streaming/dashboard.py",
    ):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
    with pytest.raises(ValueError, match="Invalid dashboard evidence"):
        validate(tmp_path)


def test_launcher_skips_open_port():
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        port = occupied.getsockname()[1]
        free = LAUNCHER["available_port"](port)
        assert free != port
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", free))


def test_served_favicon_is_png(tmp_path):
    port = LAUNCHER["available_port"](0)
    base = f"http://127.0.0.1:{port}"
    with (
        (tmp_path / "streamlit.log").open("w+") as log,
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "dashboard.py",
                "--server.headless=true",
                "--server.address=127.0.0.1",
                f"--server.port={port}",
                "--browser.gatherUsageStats=false",
            ],
            cwd=ROOT / "streaming",
            stdout=log,
            stderr=subprocess.STDOUT,
        ) as server,
    ):
        try:
            deadline = monotonic() + 15
            while True:
                try:
                    with urlopen(f"{base}/_stcore/health", timeout=1) as response:
                        assert response.read() == b"ok"
                    break
                except URLError:
                    if server.poll() is not None or monotonic() >= deadline:
                        log.seek(0)
                        pytest.fail(log.read())
                    sleep(0.1)
            with urlopen(base, timeout=3) as response:
                assert response.status == 200
            with urlopen(f"{base}/favicon.png", timeout=3) as response:
                assert response.headers.get_content_type() == "image/png"
                assert response.read().startswith(b"\x89PNG\r\n\x1a\n")
        finally:
            server.terminate()
            server.wait(timeout=10)


def test_offline_package_is_self_contained_complete_and_deterministic(tmp_path):
    a, b = tmp_path / "first", tmp_path / "second"
    export = EXPORTER["export"]
    export(ROOT, a)
    export(ROOT, b)
    name = "adaptive_drift_demo.html"
    html = (a / name).read_text(encoding="utf-8")
    assert html.count('src="data:image/png;base64,') == 6
    assert html.count("<table>") == 4
    assert "default-src 'none'" in html
    assert "https://" not in html and "http://" not in html
    assert all(
        f'href="#{section}"' in html and f'id="{section}"' in html
        for section in (
            "overview",
            "replay",
            "nab-demo",
            "results",
            "spark",
            "limitations",
        )
    )
    assert "543 · Model refit" in html and "Scoring version 1" in html
    assert "19478" in html and "5926" in html
    assert (a / "faculty_demo.zip").read_bytes() == (
        b / "faculty_demo.zip"
    ).read_bytes()
    with ZipFile(a / "faculty_demo.zip") as archive:
        assert set(archive.namelist()) == {
            name,
            "DEMO.md",
            "demo_events.csv",
            *(
                f"tables/{table}"
                for table in (
                    "table_d.csv",
                    "table_e.csv",
                    "table_f.csv",
                    "table_g.csv",
                )
            ),
            *(
                f"figures/{image}"
                for image in (
                    "01_architecture.png",
                    "05_alarm_persistence_refit.png",
                    "10_spark.png",
                    "11_nab_failure.png",
                )
            ),
            *(
                f"screenshots/demo_{kind}.png"
                for kind in ("synthetic", "nab", "research")
            ),
        }
        assert archive.read(name) == (a / name).read_bytes()
        assert (
            archive.read("tables/table_d.csv")
            == (ROOT / "docs/academic/tables/table_d.csv").read_bytes()
        )


def test_offline_export_names_missing_evidence(tmp_path):
    with pytest.raises(
        ValueError,
        match="Missing or unreadable demo artifact: streaming/offline_demo.html",
    ):
        EXPORTER["export"](tmp_path, tmp_path / "dist")
