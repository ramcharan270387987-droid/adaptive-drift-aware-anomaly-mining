"""Paired seed-block summaries for synthetic validation."""

from collections import defaultdict
from statistics import mean, median, stdev

import numpy as np
from scipy.stats import rankdata, wilcoxon

BOOTSTRAP_SEED = 1729
BOOTSTRAP_REPLICATES = 10_000
CONTRASTS = (
    ("persistence", "fixed_schedule"),
    ("full", "fixed_schedule"),
    ("persistence", "full"),
    ("persistence", "static_zscore"),
    ("full", "static_zscore"),
)


def describe(values):
    return {
        "n": len(values),
        "mean": mean(values) if values else None,
        "median": median(values) if values else None,
        "sd": stdev(values) if len(values) > 1 else None,
    }


def paired_seed_summary(blocks):
    """Test block means, and bootstrap the stream-weighted paired difference."""
    means = np.array([mean(block) for block in blocks])
    result = describe(means.tolist())
    result.update(
        eligible_streams=sum(map(len, blocks)),
        observed_difference=None,
        ci95=None,
        wilcoxon_p=None,
        p_holm=None,
        rank_biserial=None,
    )
    if not len(means):
        return result
    sums = np.array([sum(block) for block in blocks])
    counts = np.array([len(block) for block in blocks])
    result["observed_difference"] = float(sums.sum() / counts.sum())
    if len(means) < 2:
        return result
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    samples = rng.integers(len(means), size=(BOOTSTRAP_REPLICATES, len(means)))
    boot = sums[samples].sum(axis=1) / counts[samples].sum(axis=1)
    result["ci95"] = np.quantile(boot, [0.025, 0.975]).tolist()
    # Stable rounding prevents equivalent rational score differences creating rank ties by chance.
    nonzero = np.round(means, 12)
    nonzero = nonzero[nonzero != 0]
    result["nonzero_blocks"] = len(nonzero)
    if len(nonzero) >= 6:
        ranks = rankdata(abs(nonzero))
        result["rank_biserial"] = float(np.dot(np.sign(nonzero), ranks) / ranks.sum())
        result["wilcoxon_p"] = float(wilcoxon(nonzero, method="auto").pvalue)
    return result


def _apply_holm(rows):
    tested = sorted(
        (row for row in rows if row["wilcoxon_p"] is not None),
        key=lambda row: row["wilcoxon_p"],
    )
    previous = 0.0
    for index, row in enumerate(tested):
        previous = min(1.0, max(previous, (len(tested) - index) * row["wilcoxon_p"]))
        row["p_holm"] = previous


def synthetic_contrasts(by_arm):
    rows = []
    for left, right in CONTRASTS:
        if left not in by_arm or right not in by_arm:
            continue
        a = {
            row["stream_id"]: row for row in by_arm[left] if row["drift_type"] != "none"
        }
        b = {
            row["stream_id"]: row
            for row in by_arm[right]
            if row["drift_type"] != "none"
        }
        if a.keys() != b.keys():
            raise ValueError("statistical comparison requires identical paired streams")
        for metric in ("event_window_fpr", "recall"):
            blocks = defaultdict(list)
            for stream_id in sorted(a):
                first, second = a[stream_id], b[stream_id]
                if first["seed"] != second["seed"]:
                    raise ValueError("paired stream seed mismatch")
                if metric == "event_window_fpr":
                    x = first["drift_window"]["false_positive_rate"]
                    y = second["drift_window"]["false_positive_rate"]
                else:
                    x, y = first["recall"], second["recall"]
                if x is not None and y is not None:
                    blocks[first["seed"]].append(x - y)
            rows.append(
                {
                    "left": left,
                    "right": right,
                    "metric": metric,
                    **paired_seed_summary([blocks[seed] for seed in sorted(blocks)]),
                }
            )
    _apply_holm(rows)
    return rows
