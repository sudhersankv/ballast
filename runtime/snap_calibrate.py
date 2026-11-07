"""Calibrate Snap gate thresholds against the rule checker (ground truth).

Event gate: for every case with life events, a rule is truly "at risk" if a do-nothing
recommendation fails it under checker/check.py. We sweep the noul threshold and pick the
one with the best F1, per gate.

Window verdict: we build windows of 10 scored runs with known drift levels
(green = reference answers, yellow = soft misses only, red = hard misses of trusted rules)
and pick the rollback threshold that separates red from the rest.

Writes runtime/snap_thresholds.json and runtime/snap_calibration.json (report).
"""
from __future__ import annotations

import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "runtime"), str(ROOT / "checker"), str(ROOT / "scenarios")]
import oracle  # noqa: E402
import snap  # noqa: E402
from check import check, load_case  # noqa: E402
from drift import drift_level, trusted_rules_from  # noqa: E402

CASES = ROOT / "scenarios" / "cases"
GATED = [r for r in snap.RULE_TEXT if r not in ("cited", "no_churn")]


def all_cases() -> list[Path]:
    return sorted(p for s in ("practice", "test", "regression", "drift") for p in (CASES / s).iterdir() if p.is_dir())


def best_threshold(scores: list[float], labels: list[bool]) -> tuple[float, dict]:
    best = (0.5, {"f1": -1})
    for t in [i / 20 for i in range(1, 20)]:
        tp = sum(s >= t and l for s, l in zip(scores, labels))
        fp = sum(s >= t and not l for s, l in zip(scores, labels))
        fn = sum(s < t and l for s, l in zip(scores, labels))
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        if f1 > best[1]["f1"]:
            best = (t, {"f1": round(f1, 3), "precision": round(p, 3), "recall": round(r, 3), "tp": tp, "fp": fp, "fn": fn})
    return best


def calibrate_event_gate(playbook: dict) -> dict:
    jobs = []
    for d in all_cases():
        case = load_case(d)
        if not case["events"]:
            continue
        hold = check(d, oracle.do_nothing(oracle.load_case(d)))
        failed = {v["rule"] for v in hold["violations"]}
        applicable = {r["rule"] for r in hold["results"]}
        jobs.append((d, case, failed, applicable))

    def one(j):
        d, case, failed, applicable = j
        g = snap.event_gate(case, case["events"][-1], playbook)
        return d.name, g, failed, applicable

    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(one, jobs))
    scores, labels, per_rule = [], [], {}
    for name, g, failed, applicable in res:
        for r in GATED:
            if r not in applicable:
                continue
            p, l = g["rule_risk"].get(r, 0.0), r in failed
            scores.append(p)
            labels.append(l)
            per_rule.setdefault(r, []).append((p, l))
    t, stats = best_threshold(scores, labels)
    rule_stats = {r: best_threshold([p for p, _ in v], [l for _, l in v])[1] | {"n": len(v)} for r, v in per_rule.items()}
    return {"threshold": t, "overall": stats, "per_rule": rule_stats, "cases": len(res),
            "avg_seconds": round(sum(g["seconds"] for _, g, _, _ in res) / len(res), 2),
            "avg_tokens": round(sum(g["input_tokens"] for _, g, _, _ in res) / len(res))}


def calibrate_window(seed: int = 7) -> dict:
    rng = random.Random(seed)
    dirs = all_cases()
    good, soft_bad, hard_bad = [], [], []
    for d in dirs:
        oc = oracle.load_case(d)
        g = check(d, oracle.recommend(oc))
        g["tags"] = "/".join(e["type"] for e in load_case(d)["events"]) or "no events"
        good.append(g)
        for rec in (oracle.naive(oc), oracle.do_nothing(oc)):
            c = check(d, rec)
            c["tags"] = g["tags"]
            sev = {v["severity"] for v in c["violations"]}
            if "hard" in sev:
                hard_bad.append(c)
            elif sev == {"soft"}:
                soft_bad.append(c)
    trusted = trusted_rules_from(good)
    baseline = sum(c["score"] for c in good) / len(good)
    windows = []
    for _ in range(5):
        windows.append(rng.sample(good, 10))
    for k in (1, 3, 5):
        for _ in range(2):
            windows.append(rng.sample(good, 10 - k) + rng.sample(hard_bad, k))
    for _ in range(3):
        windows.append(rng.sample(good, 6) + rng.sample(soft_bad, min(4, len(soft_bad))))

    def one(w):
        rule = drift_level(w, baseline, trusted)
        return rule, snap.window_verdict(w, baseline, trusted, rule)

    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(one, windows))
    t, stats = best_threshold([v["rollback_p"] for _, v in res], [r["level"] == "red" for r, _ in res])
    agree = sum(v["level"] == r["level"] for r, v in res)
    rule_hit = sum(1 for r, v in res if r["level"] == "red" and v["rule"] in {x["rule"] for x in r["violations"]})
    reds = sum(1 for r, _ in res if r["level"] == "red")
    return {"threshold": t, "rollback": stats, "level_agreement": f"{agree}/{len(res)}",
            "at_risk_rule_correct_on_red": f"{rule_hit}/{reds}",
            "windows": [{"rule_level": r["level"], "snap_level": v["level"], "rollback_p": v["rollback_p"],
                         "snap_rule": v["rule"]} for r, v in res]}


if __name__ == "__main__":
    pb = yaml.safe_load((ROOT / "agent" / "playbooks" / "v000.yaml").read_text(encoding="utf-8"))
    ev = calibrate_event_gate(pb)
    print("event gate:", json.dumps({k: ev[k] for k in ("threshold", "overall", "cases", "avg_seconds", "avg_tokens")}))
    win = calibrate_window()
    print("window:", json.dumps({k: win[k] for k in ("threshold", "rollback", "level_agreement", "at_risk_rule_correct_on_red")}))
    th = {**snap.DEFAULT_THRESHOLDS, "event_risk": ev["threshold"], "rollback": win["threshold"]}
    snap.CONFIG.write_text(json.dumps(th, indent=1))
    (ROOT / "runtime" / "snap_calibration.json").write_text(json.dumps({"event_gate": ev, "window": win}, indent=1))
    print("thresholds:", th)
