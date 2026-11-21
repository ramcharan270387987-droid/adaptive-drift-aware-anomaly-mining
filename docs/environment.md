# Environment verification

Initial observations from 21 November 2026 in the selected Codex Cloud environment. Tool availability and resource figures reflect that setup pass.

| Item | Observed result |
| --- | --- |
| OS | Debian GNU/Linux 13.7 (trixie), Linux x86-64 |
| Python | 3.12.14 |
| pip | 26.2.2 in the base interpreter and 25.0.1 in the new project virtual environment |
| Virtual environment | `python3 -m venv .venv` succeeded. The project interpreter and its bundled pip run directly from `.venv/bin/`. |
| Git | 2.56.1 |
| GitHub CLI | 2.46.0. `gh auth status --hostname github.com` and a read-only `gh api user` request succeeded with output suppressed. |
| Java | OpenJDK 21.0.13 |
| Spark and PySpark | Neither `spark-submit` nor `pyspark` found on PATH. The inspected Python environment had no PySpark distribution. |
| pytest | No executable or Python distribution found. |
| Jupyter | No executable or Jupyter, Jupyter Core, JupyterLab, or Notebook distribution found. |
| Kaggle | No CLI or Python distribution found. Checked for a legacy environment variable pair, a token binding, and credential files in standard locations. None was detected. |
| CPU | AMD EPYC 9V74. Three logical CPUs visible, with a cgroup quota equivalent to two CPUs. |
| RAM | 9.7 GiB visible, 9.2 GiB reported available at inspection, with an 8 GiB cgroup limit. |
| Disk | 7.5 GiB available on the workspace filesystem at inspection. |
| GPU | No GPU device or PCI display controller was visible to the task. GPU compute was unused. |

## Repository and dependencies

The project scaffold was initialized under `/workspace/adaptive-drift-aware-anomaly-mining`. The base environment had uv 0.13.9. The initial virtual environment was bootstrapped with the Python standard library.

## Connectivity

| Endpoint | Check | Result |
| --- | --- | --- |
| GitHub | Public HTTPS request | HTTP 200 |
| Official Numenta NAB repository | GitHub API metadata request, repository page, and `git ls-remote … HEAD` | HTTP 200 for both HTTP requests. Git HEAD lookup succeeded. |
| Kaggle | Unauthenticated GET to homepage and API documentation | HTTP 200 for both pages |
| Kaggle competition list API | Unauthenticated GET | HTTP 401. The API is reachable and this request requires authentication. |

Kaggle job submission, notebook network access, and artifact export remain unverified.
