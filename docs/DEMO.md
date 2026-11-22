# Faculty demonstration script

## A. Local laptop dashboard

Use this mode for the 6-minute-30-second faculty demonstration. On Linux, macOS, or Windows with WSL, install Java 21 and [uv](https://docs.astral.sh/uv/getting-started/installation/). Run these commands in a Bash terminal. If you already have the checkout, open it on branch `work` and start at the first `uv sync`.

```bash
git clone --branch work https://github.com/ramcharan270387987-droid/adaptive-drift-aware-anomaly-mining.git
cd adaptive-drift-aware-anomaly-mining
uv sync --locked --python 3.12
uv sync --project streaming --locked --python 3.12
./scripts/run_dashboard.sh
```

Open the URL printed by the launcher in your laptop browser. It uses `127.0.0.1:8501` when available and selects another loopback port if necessary. Press Ctrl+C in the terminal to stop. The first NAB development replay needs access to the pinned public dataset unless the verified development files are already cached. Start it once before presenting if internet access is uncertain. [Data setup](REPRODUCIBILITY.md)

| Time | Action | What to say and verify |
| --- | --- | --- |
| 0:00–0:35 | Open Overview. Select **sudden**, **Full selective policy**, and **4×**. Start replay. | “The detector scores using past state. The dashboard reads the committed journal. The first 256 observations fit the starting model.” |
| 0:35–1:25 | Open Live replay. Once it finishes, turn off **Follow latest observation** and enter **256** in **Observation index**. | The score is approximately **6.905**, above threshold 3.0. It is a point anomaly prediction before the planted change at 320. Toggle the synthetic overlays and identify them as evaluation-only. |
| 1:25–2:05 | Select index **351**. | ADWIN raises a drift alarm and opens a candidate. The point score itself is below threshold. An alarm is evidence of a change and does not immediately refit. |
| 2:05–2:55 | Select index **479** and expand **Candidate, refit and retrospective membership**, then use the disclosure triangles to open the JSON root and its `checkpoint` object. | Both median blocks pass persistence. Only **121** observations survive filtering; fewer than the required 128. The policy waits. |
| 2:55–3:45 | Select **543**, then **544**. Read the explanation and model-state panels. | The refit uses **180** retained observations. At 543, compare **Scoring v0** with **After observation v1** in Model state. The mean changes from about 0.0582 to 1.3163, and the standard deviation from 0.9695 to 0.8479. Index 544 uses version 1 and starts the cooldown. The verified run shows 28 anomaly predictions, one alarm and one refit. |
| 3:45–4:35 | Reset and wait for the empty replay prompt. Choose the CloudWatch CPU NAB development file, start the replay, and confirm the filename in the caption. | The dashboard reads a checksum-verified 896-observation prefix. Synthetic overlay controls are absent. A model event on this trace would be observed evidence; NAB does not label general concept drift. While the replay loads, bring up Research results. |
| 4:35–5:35 | Show Final synthetic holdout and Final NAB in Research results. | Full policy passed the two synthetic criteria versus static. NAB gained one exact labeled point and added 11,288 false positives. Show the window-hit distinction and the machine-temperature failure. |
| 5:35–6:30 | Show Spark performance and reset. | Quote 3,886 committed rows/s for the 4,096 target, with 0.50 s p95. Describe the queue at the 8,192 target. These are finite single-host observations, and the sealed tables did not run as part of the demonstration. |

## B. Codex environment dashboard

Use the same launcher from the Codex checkout for development and testing. Open the printed loopback address in Chromium **inside the Codex workspace desktop**. Use **New tab (+) → Desktop** on clients that offer it. A Codex Web Preview requires environment-specific HTTP forwarding. This dashboard runs without that handoff. The Codex loopback address is scoped to the Codex machine.

## C. Standalone offline demo

Download `adaptive_drift_demo.html` or unzip `faculty_demo.zip` and double-click `adaptive_drift_demo.html`. The file opens directly in a browser on your laptop and uses only recorded evidence. There is no setup on the viewing machine.

Generate both files from the committed evidence with:

```bash
uv run --locked --no-sync python scripts/export_dashboard.py
```

Open `dist/adaptive_drift_demo.html`. The companion `dist/faculty_demo.zip` includes demo instructions, recorded dashboard screenshots, the event extract, sealed result tables, and the architecture, benchmark and failure figures. [Offline narration](OFFLINE_DEMO.md)
