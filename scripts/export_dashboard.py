"""Export the faculty demo from committed evidence without running experiments."""

import argparse
import base64
import csv
from html import escape
from pathlib import Path
from string import Template
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
ACADEMIC = Path("docs/academic")
TEMPLATE = Path("streaming/offline_demo.html")
EVENTS = ACADEMIC / "demo_events.csv"
TABLES = {
    "synthetic": "table_d.csv",
    "nab": "table_e.csv",
    "efficiency": "table_f.csv",
    "spark": "table_g.csv",
}
FIGURES = {
    "architecture": "01_architecture.png",
    "replay": "demo_synthetic.png",
    "timeline": "05_alarm_persistence_refit.png",
    "nab_replay": "demo_nab.png",
    "failure": "11_nab_failure.png",
    "benchmark": "10_spark.png",
}
SCREENSHOTS = ("demo_synthetic.png", "demo_nab.png", "demo_research.png")
EXPLANATIONS = (
    (
        "Anomaly prediction",
        "The observation exceeds the frozen threshold of 3.0 before the planted drift at 320.",
    ),
    (
        "ADWIN alarm",
        "ADWIN opens a drift candidate. This observation is below the anomaly threshold.",
    ),
    (
        "Persistence confirmed",
        "Both median blocks pass. Only 121 values survived filtering, so the policy waits for 128.",
    ),
    (
        "Model refit",
        "The model fits 180 retained values after scoring the current observation with version 0.",
    ),
    ("Updated reference", "The next observation uses version 1. Cooldown is active."),
)


def read_asset(root, path):
    try:
        return (root / path).read_bytes()
    except OSError as error:
        raise ValueError(
            f"Missing or unreadable demo artifact: {path}. Restore it from Git."
        ) from error


def image_data(root, filename):
    data = read_asset(root, ACADEMIC / "figures" / filename)
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def render_table(source):
    header, *records = csv.reader(source.splitlines())
    columns = "".join(f'<th scope="col">{escape(label)}</th>' for label in header)
    body = []
    for label, *values in records:
        cells = "".join(f"<td>{escape(value)}</td>" for value in values)
        body.append(f'<tr><th scope="row">{escape(label)}</th>{cells}</tr>')
    return f'<div class="table"><table><thead><tr>{columns}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def render_events(source):
    records = csv.DictReader(source.splitlines())
    details = []
    for row, (title, explanation) in zip(records, EXPLANATIONS, strict=True):
        index = int(row["Index"])
        score = float(row["Absolute Z"])
        mean = float(row["Scoring mean"])
        std = float(row["Scoring standard deviation"])
        version = int(row["Scoring version"])
        opened = " open" if not details else ""
        details.append(
            f"<details{opened}><summary>{index} · {title}</summary>"
            f"<p>{explanation}</p><p>Score {score:.3f} · Scoring version {version} · "
            f"Mean {mean:.4f} · Standard deviation {std:.4f}</p></details>"
        )
    return "\n".join(details)


def export(root, output):
    template = Template(read_asset(root, TEMPLATE).decode("utf-8"))
    tables = {
        key: read_asset(root, ACADEMIC / "tables" / filename)
        for key, filename in TABLES.items()
    }
    events = read_asset(root, EVENTS)
    html = template.substitute(
        **{name: image_data(root, filename) for name, filename in FIGURES.items()},
        **{
            name + "_table": render_table(data.decode("utf-8"))
            for name, data in tables.items()
        },
        events=render_events(events.decode("utf-8")),
    ).encode("utf-8")
    narration = read_asset(root, Path("docs/OFFLINE_DEMO.md")).decode("utf-8")
    for filename in FIGURES.values():
        folder = "screenshots" if filename in SCREENSHOTS else "figures"
        narration = narration.replace(
            f"academic/figures/{filename}", f"{folder}/{filename}"
        )
    files = {
        "adaptive_drift_demo.html": html,
        "DEMO.md": narration.encode("utf-8"),
        "demo_events.csv": events,
        **{f"tables/{TABLES[key]}": data for key, data in tables.items()},
        **{
            f"figures/{filename}": read_asset(root, ACADEMIC / "figures" / filename)
            for filename in FIGURES.values()
            if filename not in SCREENSHOTS
        },
        **{
            f"screenshots/{filename}": read_asset(root, ACADEMIC / "figures" / filename)
            for filename in SCREENSHOTS
        },
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "adaptive_drift_demo.html").write_bytes(html)
    with ZipFile(output / "faculty_demo.zip", "w") as archive:
        for name, data in sorted(files.items()):
            archive.writestr(ZipInfo(name), data, compress_type=ZIP_DEFLATED)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    try:
        export(ROOT, args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Could not export faculty demo. {error}\n")
    print(f"Offline demo and faculty archive written to {args.output.resolve()}")


if __name__ == "__main__":
    main()
