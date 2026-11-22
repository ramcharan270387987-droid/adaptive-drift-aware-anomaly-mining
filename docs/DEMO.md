# Faculty demonstration script

Target runtime **6 minutes 30 seconds**. Use the development fixtures. Before the session, install both locked environments, check Java 21, and bring up the dashboard. [Setup](REPRODUCIBILITY.md)

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
streaming/.venv/bin/python -m streamlit run streaming/dashboard.py \
  --server.address 127.0.0.1
```

| Time | Action | What to say and verify |
| --- | --- | --- |
| 0:00–0:35 | Open Overview. Select **sudden**, **Full selective policy**, and **4×**. Start replay. | “The detector scores using past state. The dashboard reads the committed journal. The first 256 observations fit the starting model.” |
| 0:35–1:25 | Open Live replay. Once it finishes, turn off **Follow latest observation** and select index **256**. | The score is approximately **6.905**, above threshold 3.0. It is a point anomaly prediction before the planted change at 320. Toggle the synthetic overlays and identify them as evaluation-only. |
| 1:25–2:05 | Select index **351**. | ADWIN raises a drift alarm and opens a candidate. The point score itself is below threshold. An alarm is evidence of a change and does not immediately refit. |
| 2:05–2:55 | Select index **479** and expand the candidate information. | Both median blocks pass persistence. Only **121** observations survive filtering; fewer than the required 128. The policy waits. |
| 2:55–3:45 | Select **543**, then **544**. Read the explanation and model-state panels. | The refit uses **180** retained observations. At 543 the score still uses version 0. The mean changes from about 0.0582 to 1.3163, and the standard deviation from 0.9695 to 0.8479. Index 544 uses version 1 and starts the cooldown. The verified run shows 28 anomaly predictions, one alarm and one refit. |
| 3:45–4:35 | Reset, choose the CloudWatch CPU NAB development file, and start the replay. | The dashboard reads a checksum-verified 896-observation prefix. Synthetic overlay controls are absent. A model event on this trace would be observed evidence; NAB does not label general concept drift. While the replay loads, bring up Research results. |
| 4:35–5:35 | Show Final synthetic holdout and Final NAB in Research results. | Full policy passed the two synthetic criteria versus static. NAB gained one exact labeled point and added 11,288 false positives. Show the window-hit distinction and the machine-temperature failure. |
| 5:35–6:30 | Show Spark performance and reset. | Quote 3,886 committed rows/s for the 4,096 target, with 0.50 s p95. Describe the queue at the 8,192 target. These are finite single-host observations, and the sealed tables did not run as part of the demonstration. |

## Offline fallback

Open the saved [synthetic screenshot](academic/figures/demo_synthetic.png), [NAB screenshot](academic/figures/demo_nab.png), and [research view](academic/figures/demo_research.png). Use the [decision timeline](academic/figures/05_alarm_persistence_refit.png) and [recorded event extract](academic/demo_events.csv) to present indices 256, 351, 479, 543 and 544. Use the [sealed tables](academic/TABLES.md) for final results and Spark numbers. State that the fallback displays prior verified outputs.
