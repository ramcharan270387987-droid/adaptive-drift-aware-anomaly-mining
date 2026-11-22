# Adaptive Drift-Aware Explainable Streaming Anomaly Mining

A reproducible research project and local demonstration of causal anomaly scoring, concept-drift monitoring, and selective model refitting. The scientific evaluation is complete and sealed. The engineering demo runs on CPU with Spark Structured Streaming and Streamlit.

**Research question** — Can explicit concept-drift detection and selective model adaptation reduce false anomaly alarms after distribution changes without reducing sensitivity to genuine anomalies?

## Key findings

- The frozen full policy passed both synthetic confirmatory criteria against static Z-score. Paired event-window FPR fell 2.005 percentage points and paired recall rose 2.222 points.
- On final NAB, the same policy detected 8/13 exact points versus 7/13 for static Z-score, while raising point false positives from 8,190 to 19,478. NAB does not have independent drift labels.
- The full policy and the secondary persistence policy used about 91% fewer synthetic refits than fixed scheduling. The engineering implementation reproduced reference replay across four Spark batch sizes and after checkpoint recovery.

[Academic delivery index](docs/academic/README.md) · [Sealed final report](docs/final_evaluation.md) · [Project report](docs/PROJECT_REPORT.md) · [Status](docs/STATUS.md)

## Quick start

Use Python 3.12, uv, Java 21 and a Linux CPU host.

```bash
export UV_CACHE_DIR="$PWD/.cache/uv"
uv sync --locked --python 3.12
uv sync --project streaming --locked --python 3.12
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
streaming/.venv/bin/python -m streamlit run streaming/dashboard.py --server.address 127.0.0.1
```

Choose **Live replay**, **sudden**, and **Full selective policy**. The [demo checklist](docs/DEMO.md) shows how to inspect an anomaly, alarm and refit, then replay a development NAB file.

## Run experiments and checks

```bash
.venv/bin/python -m drift_anomaly.replay --config configs/synthetic/sudden_dev.yaml
.venv/bin/python -m drift_anomaly.experiments.selective_evaluation --output results/dev_selective
streaming/.venv/bin/python -m drift_streaming.live --series sudden \
  --streams 4 --rate 512 --interval 0.5 --output results/live_demo
streaming/.venv/bin/python -m pytest -q tests streaming/tests
```

Synthetic data are generated locally. The [reproducibility workflow](docs/REPRODUCIBILITY.md) covers checksum-verified NAB development acquisition, benchmark commands, dependency checks and reading the sealed results. Normal setup and demos never execute final holdout. Keep the frozen receipt and thresholds intact.

## Repository

| Location | Contents |
| --- | --- |
| `src/drift_anomaly/`, `tests/` | Frozen estimators, causal replay, metrics and research validation |
| `configs/` | Dataset pins, experiment protocol inputs and executed evaluation receipt |
| `streaming/` | Separately locked Spark adapter, paced producer, explanations, dashboard and runtime tests |
| `scripts/` | Verification and delivery packaging |
| `docs/` | Protocol, architecture, reports, demo checklist and portable results |
| `results/`, `data/raw/` | Ignored local run artifacts and cached source data |

The streaming path is source → Spark micro-batch → ordered per-stream detector state → SQLite prediction journal → explanation layer and dashboard. The research path evaluates the same detectors offline against frozen data splits. [Architecture](docs/ARCHITECTURE.md) · [Spark guide](docs/spark_streaming.md) · [Sustained benchmark](docs/SUSTAINED_STREAMING.md) · [IEEE manuscript draft](docs/IEEE_MANUSCRIPT.md)

The study uses univariate simulations, Z-score adaptation and a small NAB subset. The Spark measurements cover one local host and do not establish multi-host scalability. Kafka and cluster deployment remain future work.

## Faculty materials

[Dashboard launch and demo script](docs/DEMO.md) · [Presentation outline](docs/academic/PRESENTATION.md) · [Viva preparation](docs/academic/VIVA.md) · [Figures](docs/academic/FIGURES.md) · [Publication tables](docs/academic/TABLES.md) · [Verified references](docs/academic/REFERENCES.md)

## Release candidate

[Release notes](docs/RELEASE_NOTES.md) · [Clean-environment verification](docs/RELEASE_VERIFICATION.md) · [Submission checklist](docs/SUBMISSION_CHECKLIST.md) · [Offline demo](docs/OFFLINE_DEMO.md)
