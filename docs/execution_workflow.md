# Codex Cloud, GitHub, and Kaggle workflow

This document describes the proposed experiment workflow. Kaggle job submission, notebook network access, and artifact export still need verification.

## Repository layout

Introduce directories as their first tracked files are added. Keep the implementation and unit tests in Python, version experiment configuration in Git, and store data and generated artifacts outside the repository history.

| Path | Purpose |
| --- | --- |
| `src/drift_anomaly/` | Python package, including the future `experiments/run.py` entry point |
| `tests/` | Unit and smoke tests with small synthetic inputs |
| `configs/` | Versioned experiment configurations, including seed, input revision, and CPU settings |
| `scripts/` | Scripted acquisition, preprocessing, and artifact export |
| `data/raw/` and `data/processed/` | Local cache for immutable raw inputs and derived data |
| `experiments/kaggle/` | Thin Kaggle notebook or launcher |
| `results/` | Per-run output directories for local review and artifact export |
| `docs/` | Environment, execution, and research documentation |

Once implemented and installed into the run environment, the same command should run in Codex Cloud and Kaggle. The module and configuration path below are proposed.

```bash
python -m drift_anomaly.experiments.run --config configs/experiment.yaml
```

## Run from an exact revision

1. Develop on a Git branch in Codex Cloud. Run unit tests and a small synthetic CPU smoke test using the project's pinned dependencies.
2. Commit the source, configuration, and dependency lock or pins. Once publishing is authorized, publish the tested commit to the approved GitHub repository and pass its full SHA to the Kaggle run.
3. Default to a free Kaggle session with the accelerator set to **None**. Use a thin notebook to set up the pinned Python environment, retrieve the exact source revision and inputs, invoke the CLI, and preserve its outputs. A Kaggle script can call the same CLI if unattended submission is needed later.
4. With network access, fetch the expected commit from GitHub, check out in detached mode, and verify that `git rev-parse HEAD` matches the expected SHA before running. For private GitHub access, use approved read-only credentials through Kaggle Secrets or another supported secret store. When notebook internet is unavailable, attach a private, verified bundle prepared from the exact commit and a compatible dependency wheelhouse if needed. Verify the bundle checksum and resolve the checked-out SHA before running.
5. Write to a unique directory under `results/` locally or `/kaggle/working/results/` in Kaggle. Save the Kaggle run output and export its file bundle to approved artifact storage. Record the artifact location with the run identifier.
6. Inspect the run manifest, logs, and measured metrics before writing research conclusions.

## Run artifacts

| Artifact | Contents |
| --- | --- |
| `manifest.json` | Full source Git SHA, configuration filename and digest, random seed, Python and resolved dependency versions, dataset source and immutable revision or version, verified input checksums, UTC start and end times, run status, and runtime hardware including CPU, memory, and accelerator setting |
| `config.yaml` | Exact copy of the configuration consumed by the run |
| `metrics.json` | Measured metrics with their names and, where applicable, evaluation window or split |
| `run.log` | Execution diagnostics with secrets excluded |

Include failure status and diagnostics when a run fails. Capture resolved dependency versions through package metadata so the manifest does not inherit credential-bearing package URLs or environment variables.

## Data and credentials

Pin NAB to an immutable upstream commit. Have the acquisition script verify expected checksums before accepting inputs into the raw cache and record the source URL, upstream revision, and file checksums. Cache by version and checksum. Key derived data by the raw input checksum and preprocessing configuration and code revision. Keep small synthetic test fixtures with the tests.

In Kaggle, use a versioned attached dataset under `/kaggle/input/` when an approved cached copy is available. Treat it as read-only and write derived data and run outputs to a writable directory. Pass paths through configuration or documented environment variables so the same scripts can use local caches in Codex Cloud.

For future Kaggle API operations, inject `KAGGLE_USERNAME` and `KAGGLE_KEY` through the environment from a secret store, or mount a private `kaggle.json` outside the checkout with restrictive permissions. The standard legacy path is `~/.kaggle/kaggle.json`. Set `KAGGLE_CONFIG_DIR` when the mounted file lives elsewhere. Keep GitHub and Kaggle credentials separate and out of source, notebooks, Git URLs, command output, and exported artifacts. Keep project repository visibility unchanged when configuring Kaggle access.
