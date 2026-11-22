"""Preflight and start the loopback-only faculty dashboard."""

import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
DEFAULT_PORT = 8501
EVIDENCE = Path("docs/evidence/delivery.json")
NAB_CONFIG = Path("configs/nab.yaml")


def validate_artifacts(root):
    for path in (EVIDENCE, NAB_CONFIG, Path("streaming/dashboard.py")):
        if not (root / path).is_file():
            raise ValueError(
                f"Missing dashboard artifact: {path}. Restore it from Git."
            )
    try:
        data = json.loads((root / EVIDENCE).read_text(encoding="utf-8"))
        required = (
            "research_revision",
            "synthetic",
            "nab",
            "update_efficiency",
            "failures",
            "spark_sustained",
            "spark_backlog",
        )
        if not isinstance(data, dict) or any(not data.get(key) for key in required):
            raise ValueError("required result sections are missing")
    except (OSError, ValueError) as error:
        raise ValueError(
            f"Invalid dashboard evidence: {EVIDENCE}. Restore it from Git."
        ) from error


def check_java():
    java_home = os.environ.get("JAVA_HOME")
    executable = str(Path(java_home) / "bin/java") if java_home else "java"
    try:
        output = subprocess.check_output(
            [executable, "-version"], stderr=subprocess.STDOUT, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        output = ""
    if not re.search(r'version "21(?:[.+-]|")', output):
        raise ValueError(
            "Install Java 21 and point JAVA_HOME or PATH to it for Spark replay."
        )


def available_port(first=DEFAULT_PORT):
    for port in (*range(first, min(first + 20, 65536)), 0):
        with socket.socket() as probe:
            try:
                probe.bind((HOST, port))
            except OSError:
                continue
            return probe.getsockname()[1]
    raise OSError("No local dashboard port could be opened.")


def main():
    try:
        validate_artifacts(ROOT)
        check_java()
        port = available_port()
    except (ValueError, OSError) as error:
        sys.exit(f"Dashboard preflight failed. {error}")
    os.chdir(ROOT)
    print(f"Starting dashboard at http://{HOST}:{port} on this machine.", flush=True)
    print("Open that address in your browser. Press Ctrl+C to stop.", flush=True)
    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(ROOT / "streaming/dashboard.py"),
            "--server.headless=true",
            f"--server.address={HOST}",
            f"--server.port={port}",
            "--browser.gatherUsageStats=false",
        ],
    )


if __name__ == "__main__":
    main()
