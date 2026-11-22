# Environment verification

Verified in Codex Cloud on 21 November 2026.

## Reproduce the development environment

Run these commands from the repository root with Python 3.12 and uv available. The setup was verified with Python **3.12.14** and uv **0.13.9**. The dependency manifest is [`pyproject.toml`](../pyproject.toml), and [`uv.lock`](../uv.lock) records the resolved dependencies. By default, uv installs the development group alongside the runtime dependencies and installs the `src/drift_anomaly` package in editable mode.

```bash
export UV_CACHE_DIR="$PWD/.cache/uv"
uv sync --locked --python 3.12 --system-certs
.venv/bin/python --version
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

For scripts that use Matplotlib, set a writable configuration and cache directory before Python starts. The example uses the repository's ignored cache directory. The smoke test uses a temporary directory.

```bash
export MPLCONFIGDIR="$PWD/.cache/matplotlib"
```

## Installed versions

All listed Python packages were imported from the project environment using `.venv/bin/python`. The editable project package, `drift-anomaly` 0.1.0, imported from `src/drift_anomaly`.

| Runtime dependency | Version | Development dependency | Version |
| --- | --- | --- | --- |
| NumPy | 2.5.5 | pytest | 9.2.0 |
| Pandas | 3.1.1 | Ruff | 0.17.6 |
| SciPy | 1.18.1 | | |
| scikit-learn | 1.9.1 | | |
| River | 0.27.0 | | |
| PyYAML | 6.0.4 | | |
| joblib | 1.6.0 | | |
| psutil | 7.2.2 | | |
| Matplotlib | 3.11.2 | | |
| Plotly | 7.1.0 | | |

## Verification results

| Check | Observed result |
| --- | --- |
| `.venv/bin/python --version` | Python 3.12.14 |
| `uv lock --check` | Lockfile matches the manifest |
| `uv sync --locked --check` | No environment changes required |
| `uv pip check --python .venv/bin/python` | All installed packages are compatible |
| `.venv/bin/python -m pytest` | 11 environment smoke tests passed |
| `.venv/bin/ruff check .` and `.venv/bin/ruff format --check .` | Both passed |
| `git status --short --branch` | Branch `work` with the environment setup changes pending commit |

The smoke tests check installation, imports, and YAML parsing. No model training or scientific experiment has been performed at this stage.

## Cloud services and later stages

| Item | Observed result |
| --- | --- |
| Runtime resources | Debian GNU/Linux 13.7 on x86-64. Three logical CPUs visible with a two-CPU quota, 8 GiB cgroup memory limit, and about 60 GiB of workspace disk available. |
| Java | OpenJDK 21.0.13 |
| PySpark | Not yet installed. `spark-submit` and `pyspark` were absent from PATH. |
| Official Numenta/NAB | `git ls-remote https://github.com/numenta/NAB.git HEAD` succeeded. Dataset acquisition is pending. |
| GitHub | Read access to `origin` succeeded. The Cloud proxy denied access to `api.github.com`. Write access remains unverified. |
| Kaggle | Not configured. The Cloud proxy denied access to `www.kaggle.com`, and the Kaggle CLI and Python package were absent. |
