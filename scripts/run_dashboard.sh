#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if ! command -v uv >/dev/null; then
    printf '%s\n' 'uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/ and retry.' >&2
    exit 1
fi

if ! uv sync --project streaming --locked --check --offline --python 3.12; then
    printf '%s\n' 'The locked streaming environment is missing or out of sync.' \
        'From the repository root, run: uv sync --project streaming --locked --python 3.12' >&2
    exit 1
fi

export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
exec uv run --project streaming --locked --no-sync --offline --python 3.12 python scripts/run_dashboard.py
