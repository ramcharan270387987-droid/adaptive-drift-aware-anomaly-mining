# Live faculty demonstration — 6 minutes 30 seconds

## Before the clock starts

Use the laptop setup in the [dashboard guide](../DEMO.md). From the repository root, run:

```bash
./scripts/run_dashboard.sh
```

Open the printed local URL. Cache the NAB development data by rehearsing the CloudWatch replay once. Keep the offline HTML open in another tab. The dashboard's replay launches development data only. Research results and Spark performance load recorded evidence.

## Timed narration

| Time | Action | Say this |
| --- | --- | --- |
| 0:00–0:35 | Show the already launched **Overview**. Select **sudden**, **Full selective policy**, and **4×**. Click **Start replay**. Wait for the stream caption or status. | “This dashboard shows the decisions made by the same causal scoring policy used in the research. I’m starting a development replay. The first 256 points fit the starting reference.” |
| 0:35–1:25 | Open **Live replay**. When the run finishes, turn off **Follow latest observation**. Use **Observation index**. Point to the left-hand normal regime, then enter **256**. Enable **Show synthetic evaluation overlays**. | “On the left, the early points fluctuate around the original normal level. At 256, this point scores about 6.905 against a threshold of 3.0, so it is flagged. The planted normal regime shifts later, at 320. The overlay comes from simulation truth and is used for inspection.” |
| 1:25–2:05 | Enter **351** and point to the ADWIN marker and explanation. | “ADWIN flags a change and opens a candidate here. The point’s own Z-score is below threshold. An alarm begins a check for persistence, so the scoring reference stays the same for now.” |
| 2:05–2:55 | Enter **479**. Read the explanation. If time permits, expand **Candidate, refit and retrospective membership** and open the checkpoint object. | “Both block medians pass the persistence test. Filtering leaves 121 observations, below the minimum of 128. The explanation records why the policy waits.” |
| 2:55–3:45 | Enter **543**. Show **Decision explanation** and compare **Scoring v0** with **After observation v1** under **Model state**. Enter **544**. | “Now 180 retained values support a refit. At 543 the prediction still used version zero. The refit changes the mean from 0.0582 to 1.3163 and the standard deviation from 0.9695 to 0.8479. Row 544 uses version one, with cooldown active through row 671. In this 896-point development trace there are 28 anomaly predictions, one ADWIN alarm, and one refit.” |
| 3:45–4:35 | Click **Reset replay** and wait for the empty prompt. Select `realAWSCloudwatch/ec2_cpu_utilization_53ea38.csv`, then click **Start replay**. Show the filename and the plot when records arrive. | “This is the CloudWatch CPU development trace. The demonstration uses the checksum-verified prefix of 896 observations. The synthetic overlay controls are absent. NAB’s anomaly annotations do not tell us where concept drift occurred.” |
| 4:35–5:35 | Open **Research results**. Show **Final synthetic holdout** and **Final NAB**. Point to the distinction between point detections and window hits. Open the failure section if time permits. | “These tables are sealed results. Against static Z-score, the full policy passed both synthetic criteria. On final NAB the same policy gained one exact point, from seven to eight out of thirteen, and added 11,288 point false positives. Fixed scheduling had fewer point false positives. A window hit can coexist with many extra flags.” |
| 5:35–6:30 | Open **Spark performance**. Point to the eight-stream rows for targets **4,096** and **8,192**. Reset when finished. | “The best single-host trial committed 3,886 rows per second, with 0.50 seconds p95 publish-to-commit latency. At the heavier setting with shorter triggers, the peak backlog rose to 21,300. These are finite local measurements. The research question is partially supported. The strongest evidence is controlled synthetic performance, and the NAB result limits generalization.” |

If the live view stalls, resume at the matching row in the [offline script](offline_demo_script.md). If a replay is simply running, **Pause display** freezes the visible view while Spark continues to process. Use **Reset replay** to stop or clear the session.
