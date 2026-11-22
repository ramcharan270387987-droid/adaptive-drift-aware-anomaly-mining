# Release-candidate verification

## Source identity and safeguards

The clean reproduction began from `7d1e3fc5e5782e83ed538671cfa88bdbdd2234cf`, the academic-delivery commit. The local `work` branch was clean and matched `origin/work`. The remote `main` tip was an ancestor. Release changes are documentation and packaging only. The final-science execution remains `7e72ccb61297d58567fb1e41c077e6b537e9d897`, with research fingerprint `a75d7c3c968a8263c1e2047cde34a603d3fb4bb7ea026c8eb68737b374f9a723`. All six original receipt digests passed. No final holdout scoring was executed.

## Fresh worktree commands

Commands below were run with Python 3.12.14, uv 0.13.9, OpenJDK 21.0.13, Spark 4.1.1, Streamlit 1.58.0 and Chromium 156 on Linux. The worktree had neither environment nor a cache at creation. The system interpreter and tools were preinstalled.

```bash
git status -sb
git rev-parse HEAD
git ls-remote --heads origin work main
git ls-remote --tags origin
java -version
uv --version
chromium --version
clean=$(mktemp -d /workspace/drift-rc.XXXXXXXX)
git worktree add --detach "$clean" HEAD
cd "$clean"
export UV_CACHE_DIR="$PWD/.cache/uv"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
uv sync --locked --python 3.12
uv sync --project streaming --locked --python 3.12
```

```bash
.venv/bin/python - <<'PY'
from drift_anomaly import nab
from drift_anomaly.nab_replay import MANIFEST, RAW_NAB

dataset = nab.load_config(MANIFEST)
nab.fetch_split(dataset, RAW_NAB / dataset["revision"], "development")
for series in dataset["development"]:
    from drift_anomaly.nab_replay import load_development_series
    data = load_development_series(series)
    print(series, len(data.observations))
PY
.venv/bin/python -m drift_anomaly.replay --config configs/synthetic/sudden_dev.yaml
streaming/.venv/bin/python -m drift_streaming.live --series sudden \
  --streams 4 --rate 512 --interval 0.5 --partitions 2 --output results/live_demo
```

Acquisition verified five development CSVs and three pinned metadata artifacts. The examples contained 4,032, 4,730, 2,500, 4,032 and 4,032 observations in manifest order. The synthetic smoke processed 4,096 observations, including 256 warm-up rows. The Spark demo reconciled 3,584 inputs across four streams and three policies in 14 batches, with eight alarms and eight refits and zero dropped records.

```bash
streaming/.venv/bin/python -m streamlit run streaming/dashboard.py \
  --server.address 127.0.0.1 --server.port 8781 --server.headless true \
  >/tmp/drift-rc-streamlit.log 2>&1
```

From another shell in the worktree, health and browser checks used the following commands. The release verification artifact folder contains the Playwright scripts and captured evidence. These are validation tools in the checking environment. The documented application launch requires only the locked environments and Java.

```bash
curl -fsS http://127.0.0.1:8781/_stcore/health
FAST_REHEARSAL=1 python /tmp/drift-rc-browser.py
python /tmp/drift-rc-browser.py
```

The dashboard reads the portable summary at `docs/evidence/delivery.json`. The historical configuration and archived outputs were also checked directly. The archive was supplied from the original workspace; neither a cached detector nor a final dataset was copied into the fresh worktree.

```bash
export MPLCONFIGDIR="$PWD/.cache/matplotlib"
frozen=$(mktemp /tmp/drift-final-frozen.XXXXXXXX.yaml)
git show 7e72ccb61297d58567fb1e41c077e6b537e9d897:configs/final_evaluation.yaml > "$frozen"
.venv/bin/python -m drift_anomaly.experiments.final_evaluation --config "$frozen" --check
rm "$frozen"
archive=/workspace/adaptive-drift-aware-anomaly-mining/results/research-evidence.tar.gz
printf '%s  %s\n' 738bebdb3ea8a7a7b1622f232b12334d57c5a96d3553a49cfcf2bb9d68e570b6 "$archive" | sha256sum --check
tar -xzf "$archive"
streaming/.venv/bin/python scripts/package_delivery.py --matrix results/spark-sustained-verified --output results/delivery
cmp docs/evidence/delivery.json results/delivery/delivery.json
git status --short
```

The regenerated summary matched byte-for-byte. Fontconfig issued cache-location warnings during plot generation, with a successful exit and matching data.

## Demo and offline fallback

The Chromium walk-through follows the 6:30 presentation schedule, from Overview and development replay to synthetic and NAB result tables, Spark performance, limitations, and reset. The on-screen sequence shows the anomaly at 256, ADWIN at 351, a passed persistence check at 479 with 121 retained observations, refit at 543 with 180 observations and version 1 scoring from 544. The script now specifies expanding the JSON root and its checkpoint node, and distinguishes scoring-time model statistics from the post-row version. The runtime emitted a favicon HTTP 500 under pinned Streamlit, independently of the verified views.

The self-contained offline export was built and tested with:

```bash
pandoc docs/OFFLINE_DEMO.md --from=gfm+yaml_metadata_block --standalone \
  --embed-resources --resource-path=docs --to=html5 \
  -o results/release-candidate/Offline_Faculty_Demo.html
python /tmp/drift-rc-offline.py
```

The browser was put in offline mode. The managed browser blocked direct `file://` navigation, so the check loaded the exact HTML bytes directly. Eight images and three tables rendered with zero web requests. The HTML provides the complete fallback narration. The same export ran from a loopback static server with every external request blocked. A browser that allows local files can open the saved HTML directly. [Offline script](OFFLINE_DEMO.md)

## Report and manuscript audit

The 30 report sections remain consecutive. The cover includes student and registration number, programme, department, institution, supervisor, academic year and submission date placeholders. Figure and table links, 12 numbered citations, sealed metric definitions and development/final labels were checked. Both PDFs were reviewed for rendering and extractable text. The IEEE-style draft preserves the full policy as confirmatory and persistence as secondary, carries the negative NAB result, and bounds the systems claims to local Spark. Author names, affiliations, institution, email, venue template and acknowledgements if applicable must be supplied before submission. [Academic evidence audit](academic/AUDIT.md)

## QA commands and outcomes

```bash
.venv/bin/python -m pytest -q tests
streaming/.venv/bin/python -m pytest -q tests streaming/tests
.venv/bin/ruff check .
.venv/bin/ruff format --check .
uv lock --check --offline
uv lock --project streaming --check --offline
uv sync --locked --check --offline
uv sync --project streaming --locked --check --offline
uv pip check --python .venv/bin/python
uv pip check --python streaming/.venv/bin/python
git diff --check
git status --short
```

The core suite passed 241 tests in 16.94 seconds in the research-only environment. The combined suite passed 263 tests in 77.98 seconds in the streaming environment. Ruff reported 107 formatted files and no lint errors. Both locks were current, both sync checks reported no changes, and dependency checks passed for 28 and 66 installed packages. The indexed-file check found no common credential signatures or runtime paths among 160 files. The largest tracked blob was 392,639 bytes, below the 10 MiB check threshold. The academic check covered 12 references, 40 exact table rows, all six sealed digests and local links. The demonstration was exercised on the local host; personal presentation review remains with the student. [Submission checklist](SUBMISSION_CHECKLIST.md)
