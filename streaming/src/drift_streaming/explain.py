"""Render the frozen detector trace without using ground truth."""

from drift_anomaly.experiments.selective_smoke import FROZEN_ZSCORE

FAILURE_TEXT = {
    "persistence_failed": "the two median blocks did not pass the persistence rule",
    "insufficient_retained": "fewer than 128 values survived filtering",
    "budget_blocked": "the refit would exceed the adaptation budget",
}

ALARMS = {
    "accepted": "ADWIN opened a candidate for persistence checks",
    "duplicate": "ADWIN alarm while a candidate was already open",
    "cooldown_suppressed": "ADWIN alarm suppressed during cooldown",
    "budget_suppressed": "ADWIN alarm suppressed by the refit budget",
}


def explain(rows):
    """Explain one stream/method in order; retention annotations are post-hoc."""
    decisions = []
    membership = {}
    pending = None
    cooldown_end, last_refit = -1, None
    current_stats = None
    threshold = FROZEN_ZSCORE.threshold
    for row in rows:
        index = row["index"]
        update = (row["update"] or {}).get("metadata", {})
        checkpoint = update.get("checkpoint")
        proposal = update.get("proposal")
        disposition = update.get("alarm_disposition")
        persistence = (
            "awaiting checkpoint" if pending is not None else "no active candidate"
        )
        if proposal is not None:
            pending = dict(proposal)
            persistence = "awaiting checkpoint"
        old = new = None
        if row["warmup"]:
            state, detail = (
                "NORMAL",
                "Warm-up observation. No anomaly decision was made.",
            )
            z_score = None
        else:
            mean, std = row["mean"], row["std"]
            current_stats = {"mean": mean, "std": std}
            scale = max(std, FROZEN_ZSCORE.minimum_std)
            z_score = row["score"] if row["value"] >= mean else -row["score"]
            state = "ANOMALY" if row["prediction"] else "NORMAL"
            direction = "above" if z_score >= 0 else "below"
            detail = (
                f"{'Anomaly' if row['prediction'] else 'Normal'}: "
                f"value is {abs(z_score):.2f} effective standard deviations {direction} "
                f"the scoring mean (threshold {threshold:.1f})."
            )
            if std < scale:
                detail += " The frozen minimum scale applies."
        if disposition is not None:
            state = "DRIFT_SUSPECTED"
            detail += f" {ALARMS[disposition]}."
        candidate = dict(pending) if pending else None
        cooldown_applied = index <= cooldown_end
        if checkpoint is not None:
            passed = checkpoint["persistence_passed"]
            persistence = "passed" if passed else "failed"
            if passed:
                state = "DRIFT_CONFIRMED"
                detail += " The two median blocks passed the frozen persistence check."
            failures = "; ".join(FAILURE_TEXT.get(f, f) for f in checkpoint["failures"])
            if failures:
                detail += f" Refit {checkpoint['decision']}: {failures}."
            refit = checkpoint.get("refit")
            retained = set(checkpoint["retained_positions"])
            for position in checkpoint["candidate_positions"]:
                membership.setdefault(position, []).append(
                    {
                        "checkpoint_index": index,
                        "decision": checkpoint["decision"],
                        "retained": position in retained,
                        "used_in_refit": refit is not None and position in retained,
                    }
                )
            if refit is not None:
                state = "MODEL_ADAPTED"
                old, new = refit["before"], refit["after"]
                current_stats = new
                last_refit = index
                cooldown_end = (
                    refit["cooldown"]["last_position"] if refit["cooldown"] else -1
                )
                detail += f" Model refit after scoring, using {checkpoint['retained_count']} retained observations."
            if checkpoint["decision"] in ("closed", "refit"):
                pending = None
        elif pending is not None and proposal is None:
            detail += " Persistence checkpoint pending."
        decisions.append(
            {
                "index": index,
                "value": row["value"],
                "score": row["score"],
                "threshold": threshold,
                "z_score": z_score,
                "prediction": row["prediction"],
                "classification": state,
                "reason": detail,
                "persistence": persistence,
                "candidate": candidate,
                "candidate_open_after_row": pending is not None,
                "checkpoint": checkpoint,
                "adwin_alarm": row["drift_alarm"],
                "alarm_disposition": disposition,
                "adaptation_event": row["adaptation_event"],
                "scoring_mean": row["mean"],
                "scoring_std": row["std"],
                "old_model": old,
                "new_model": new,
                "current_model": current_stats,
                "scoring_model_version": row["model_version"],
                "model_version": None
                if row["model_version"] is None
                else row["model_version"] + int(row["adaptation_event"]),
                "last_refit_index": last_refit,
                "cooldown_applied_at_row": cooldown_applied,
                "cooldown_through_index": cooldown_end
                if cooldown_end >= index
                else None,
            }
        )
    for decision in decisions:
        decision["posthoc_checkpoint_membership"] = membership.get(
            decision["index"], []
        )
    return decisions
