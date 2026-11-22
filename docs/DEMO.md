# Faculty demonstration

1. Launch Streamlit using the [reproduction workflow](REPRODUCIBILITY.md). Open the displayed local URL.
2. Select **Live replay**, **sudden**, **Full selective policy**, and **4×** replay speed. Select **Start replay**. Spark startup and 256-point warm-up precede the first scored rows.
3. After the replay completes, point out the red anomaly predictions, orange ADWIN marker at index 351 and green refit marker at 543. Turn off **Follow latest observation** and select index 543. Compare the scoring-time model and new statistics. Index 544 uses version 1 and shows the active cooldown. **Show synthetic evaluation overlays** adds separately styled synthetic truth.
4. Use **Pause display** to hold the view while Spark continues writing. Use **Reset replay** to clear the view. The original local journal remains available as evidence.
5. Select the CloudWatch CPU development file and run it. The live demo replays the first 896 observations. Its plot has predictions and observed event markers and does not show synthetic truth controls. Use the full-source CLI flag for a complete development file.
6. Open **Research results** to compare the final synthetic and NAB tables and read the failure cases. Open **Spark performance** to compare the paced and preloaded backlog runs.

The synthetic confirmatory method met both criteria against static Z-score. Final NAB outcomes show the boundary of that finding. The full policy detected one additional point at a cost of 11,288 extra point false positives. The performance page reports single-host measurements.
