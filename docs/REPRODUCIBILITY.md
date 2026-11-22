# Reproduction workflow

Run from the repository root on Linux with Python 3.12, uv and Java 21. The research and streaming projects have independent lockfiles. Keeping the adapter in its own environment preserves the sealed research fingerprint.

```bash
export UV_CACHE_DIR="$PWD/.cache/uv"
uv sync --locked --python 3.12
uv sync --project streaming --locked --python 3.12
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
```

## Development datasets and checks

Synthetic streams require no downloads. The pinned NAB loader verifies selected source CSVs and both label files. To acquire only the development subset from upstream:

```bash
.venv/bin/python - <<'PY'
from drift_anomaly import nab
from drift_anomaly.nab_replay import MANIFEST, RAW_NAB

dataset = nab.load_config(MANIFEST)
nab.fetch_split(dataset, RAW_NAB / dataset["revision"], "development")
PY
.venv/bin/python -m drift_anomaly.replay --config configs/synthetic/sudden_dev.yaml
.venv/bin/python -m drift_anomaly.experiments.selective_evaluation --output results/dev_selective_replay
```

The last command runs the fixed aligned development grid. Use a new ignored results path for each invocation.

## Spark and dashboard

```bash
streaming/.venv/bin/python -m drift_streaming.live --series sudden \
  --streams 4 --rate 512 --interval 0.5 --partitions 2 --output results/live_demo
streaming/.venv/bin/python -m drift_streaming.live --series nab \
  --methods full --rate 512 --output results/live_nab
streaming/.venv/bin/python -m drift_streaming.live --matrix \
  --output results/spark_sustained_reproduction
streaming/.venv/bin/python -m streamlit run streaming/dashboard.py \
  --server.address 127.0.0.1
```

Dashboard instructions are in the [demo checklist](DEMO.md). Spark benchmark numbers depend on the host and run order. Detector output equivalence is exact on the verified development fixtures.

## Sealed final results

Read [Final evaluation](final_evaluation.md), the [receipt](../configs/final_evaluation.yaml), and the portable [machine-readable summary](evidence/delivery.json). The dashboard reads the portable summary on a clean checkout. It never opens or evaluates a final series. The current launcher rejects the executed receipt. A data-free archive check can validate the historical frozen configuration:

```bash
frozen=$(mktemp /tmp/drift-final-frozen.XXXXXXXX.yaml)
git show 7e72ccb61297d58567fb1e41c077e6b537e9d897:configs/final_evaluation.yaml > "$frozen"
.venv/bin/python -m drift_anomaly.experiments.final_evaluation --config "$frozen" --check
rm "$frozen"
```

For full archived artifacts, restore the existing delivery archive at the repository root, then verify the original results and export CSV/plot copies without replaying any final data.
The archive is `results/research-evidence.tar.gz` from the delivered workspace. On a clean checkout, extract it at the repository root with `tar -xzf /path/to/research-evidence.tar.gz`. The included results are derived artifacts and contain no cached raw data.
The archive SHA-256 is `738bebdb3ea8a7a7b1622f232b12334d57c5a96d3553a49cfcf2bb9d68e570b6`.

```bash
streaming/.venv/bin/python scripts/package_delivery.py \
  --matrix results/spark-sustained-verified --output results/delivery
```

The packager refuses changed sealed artifacts or a changed research fingerprint. Any new final evaluation is a separate protocol decision and is outside this workflow.

## Quality checks

```bash
streaming/.venv/bin/python -m pytest -q tests streaming/tests
.venv/bin/ruff check .
.venv/bin/ruff format --check .
uv lock --check
uv lock --project streaming --check
uv sync --locked --check
uv sync --project streaming --locked --check
uv pip check --python .venv/bin/python
uv pip check --python streaming/.venv/bin/python
git diff --check
```

The dashboard tests start local Spark subprocesses for synthetic and NAB development replay. The NAB fixture uses the pinned development file, downloaded by the development loader if absent. Local generated input, checkpoints, screenshots and evidence archives belong under ignored `results/`.
