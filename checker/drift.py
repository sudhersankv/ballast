"""Drift indicator (EVAL.md section 6). Used in drift mode only.

drift_level(recent_checks, baseline, trusted_rules, previous_checks=None)
  -> {"level": "green"|"yellow"|"red", "rolling_score", "violations", "reasons"}

recent_checks: newest-last list of check() results (window = last 10).
baseline: the shipped playbook's verification test mean_score.
trusted_rules: hard rules that passed 100% in the shipped playbook's verification run.
previous_checks: the 10 checks before the window (for the soft-violation trend).
"""
from __future__ import annotations

WINDOW = 10
DROP = 0.05
SOFT_RISE = 3


def trusted_rules_from(verification_checks: list[dict]) -> set[str]:
    """Hard rules that were applicable at least once and never failed in verification."""
    seen, failed = set(), set()
    for c in verification_checks:
        for r in c.get("results", []):
            if r["severity"] != "hard":
                continue
            seen.add(r["rule"])
            if not r["passed"]:
                failed.add(r["rule"])
    return seen - failed


def _soft(checks: list[dict]) -> int:
    return sum(1 for c in checks for v in c.get("violations", []) if v.get("severity") == "soft")


def drift_level(recent_checks: list[dict], baseline: float, trusted_rules: set[str] | list[str],
                previous_checks: list[dict] | None = None) -> dict:
    window = recent_checks[-WINDOW:]
    trusted = set(trusted_rules)
    rolling = round(sum(c["score"] for c in window) / len(window), 4) if window else baseline
    red_v = [{**v, "case_id": c.get("case_id")} for c in window for v in c.get("violations", [])
             if v.get("severity") == "hard" and v.get("rule") in trusted]
    reasons = []
    if red_v:
        level = "red"
        reasons.append(f"{len(red_v)} hard violation(s) of trusted rules: "
                       + ", ".join(sorted({v['rule'] for v in red_v})))
        violations = red_v
    else:
        violations = [{**v, "case_id": c.get("case_id")} for c in window for v in c.get("violations", [])]
        soft_now = _soft(window)
        soft_prev = _soft((previous_checks or [])[-WINDOW:]) if previous_checks else None
        if rolling < baseline - DROP:
            reasons.append(f"rolling score {rolling:.2f} < baseline {baseline:.2f} - {DROP}")
        if soft_prev is not None and soft_now - soft_prev >= SOFT_RISE:
            reasons.append(f"soft violations rose {soft_prev} -> {soft_now}")
        level = "yellow" if reasons else "green"
    return {"level": level, "rolling_score": rolling, "baseline": baseline,
            "violations": violations, "reasons": reasons,
            "case_ids": sorted({v["case_id"] for v in violations if v.get("case_id")})}
