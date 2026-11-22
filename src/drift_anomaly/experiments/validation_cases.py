"""Select and plot observed failures using deterministic rules."""

from dataclasses import dataclass

from drift_anomaly.evaluation import NominalAlarms


def count_nominal(result, left, right):
    alarms = NominalAlarms()
    for row in result.records[left:right]:
        if not row.warmup and row.observation.anomaly_label is False:
            alarms.add(row.prediction.predicted_anomaly)
    return alarms.summary()


@dataclass
class FailureCase:
    rank: int
    arm: str
    series: str
    index: int
    start: int
    end: int
    values: list[float]
    predictions: list[int]
    anomalies: list[int]
    drift: list[tuple[int, int]]
    alarms: list[int]
    refits: list[int]
    windows: list[tuple[int, int]]


class FailureCases:
    def __init__(self):
        self.cases = {}

    def consider(
        self,
        category,
        rank,
        arm,
        series,
        index,
        result,
        *,
        drift=(),
        alarms=(),
        refits=(),
        windows=(),
    ):
        previous = self.cases.get(category)
        if previous is not None and previous.rank >= rank:
            return
        start, end = max(0, index - 128), min(len(result.records), index + 257)
        rows = result.records[start:end]
        self.cases[category] = FailureCase(
            rank,
            arm,
            series,
            index,
            start,
            end,
            [row.observation.value for row in rows],
            [
                row.observation.index
                for row in rows
                if row.prediction and row.prediction.predicted_anomaly
            ],
            [row.observation.index for row in rows if row.observation.anomaly_label],
            [(event.start, event.end) for event in drift],
            list(alarms),
            list(refits),
            list(windows),
        )

    def synthetic(self, arm, series, run, detail, drift):
        if arm != "full":
            return
        events, result = run.drift_events, run.result
        refits = sorted(
            detail["unmatched_refit_indices"]
            + [
                match["index"]
                for match in detail["refit_matches"]
                if match["index"] is not None
            ]
        )
        kwargs = {"drift": events, "alarms": drift.alarm_indices, "refits": refits}

        def select(category, rank, index):
            self.consider(category, rank, arm, series, index, result, **kwargs)

        for row in result.scored_records():
            if row.observation.anomaly_label and not row.prediction.predicted_anomaly:
                select("missed_anomaly", 1, row.observation.index)
                break
        if drift.false_alarm_indices:
            select("false_adwin_alarm", 1, drift.false_alarm_indices[0])
        if detail["unmatched_refit_indices"]:
            select("unnecessary_refit", 1, detail["unmatched_refit_indices"][0])
        for number, (event, match) in enumerate(
            zip(events, detail["refit_matches"], strict=True)
        ):
            delay = match["onset_delay"]
            if delay is not None:
                select("late_refit", delay, match["index"])
            start = event.end + 1
            end = min(
                start + 256,
                events[number + 1].start
                if number + 1 < len(events)
                else len(result.records),
            )
            fp = count_nominal(result, start, end)["fp"]
            if fp:
                select("post_drift_fp_burst", fp, start)
            if run.provenance.drift_type == "recurring" and number == 1 and fp:
                select("recurring_state_recovery", fp, start)

    def publish(self, output):
        from dataclasses import asdict

        from drift_anomaly.experiments.static_baseline import prepare_plots, write_json

        if not self.cases:
            return
        plots = prepare_plots(output)
        import matplotlib.pyplot as plt

        for name, case in self.cases.items():
            fig, ax = plt.subplots(figsize=(9, 3), layout="constrained")
            ax.plot(
                range(case.start, case.end), case.values, linewidth=0.8, color="#35485d"
            )
            for spans, color, label in (
                (case.drift, "#d4a017", "Drift"),
                (case.windows, "#7984aa", "NAB window"),
            ):
                for i, (left, right) in enumerate(
                    (a, b) for a, b in spans if a < case.end and b >= case.start
                ):
                    if left == right:
                        ax.axvline(left, color=color, label=label if i == 0 else None)
                    else:
                        ax.axvspan(
                            left,
                            right,
                            color=color,
                            alpha=0.22,
                            label=label if i == 0 else None,
                        )
            for indices, color, mark, label in (
                (case.predictions, "#df6728", ".", "Predicted anomaly"),
                (case.anomalies, "#86253e", "x", "Labeled anomaly"),
            ):
                selected = [i for i in indices if case.start <= i < case.end]
                if selected:
                    ax.scatter(
                        selected,
                        [case.values[i - case.start] for i in selected],
                        marker=mark,
                        s=18,
                        color=color,
                        label=label,
                    )
            for indices, color, label in (
                (case.alarms, "#4059ad", "ADWIN alarm"),
                (case.refits, "#158467", "Refit"),
            ):
                for n, i in enumerate(i for i in indices if case.start <= i < case.end):
                    ax.axvline(
                        i,
                        color=color,
                        linestyle="--",
                        alpha=0.8,
                        label=label if n == 0 else None,
                    )
            ax.set(
                xlim=(case.start, case.end - 1),
                xlabel="Replay index",
                ylabel="Raw value",
                title=name.replace("_", " "),
            )
            ax.legend(loc="best", fontsize=7, ncols=2)
            fig.savefig(plots / f"{name}.png", dpi=140)
            plt.close(fig)
        write_json(
            output / "failure_cases.json",
            {name: asdict(case) for name, case in self.cases.items()},
        )
