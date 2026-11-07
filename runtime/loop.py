"""ballast. outer loop: training mode (improve) and drift mode (catch and realign).

  python runtime/loop.py train  --generations 3
  python runtime/loop.py drift
  python runtime/loop.py bench  --models meta/<id>,google/gemini-3.8-flash --set test

Gate (EVAL.md section 5): a candidate ships only if
  test.mean_score >= parent.test.mean_score + 0.02, no regression case the parent passed now fails,
  the playbook is valid, and the Gemini compliance reviewer approves.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "runtime"), str(ROOT / "checker"), str(ROOT / "agent")]

import mentor  # noqa: E402
import snap  # noqa: E402
from check import check, load_case  # noqa: E402
from drift import drift_level, trusted_rules_from  # noqa: E402
from run_case import run_case  # noqa: E402
from store import Store  # noqa: E402

PLAYBOOKS = ROOT / "agent" / "playbooks"
CASES = ROOT / "scenarios" / "cases"
WORKERS = int(os.environ.get("BALLAST_WORKERS", "6"))
MIN_GAIN = 0.02
MAX_ATTEMPTS = 3
DRIFT_PASS = float(os.environ.get("BALLAST_DRIFT_PASS", "1.0"))

store = Store()
_cache: dict[tuple[int, str, str], list[dict]] = {}


SESSION = f"s-{int(__import__('time').time())}"


def log(msg: str) -> None:
    """Console + `loop_log` collection, so the UI can stream the live run."""
    print(msg, flush=True)
    try:
        store.insert("loop_log", {"session": SESSION, "msg": msg.strip()})
    except Exception:
        pass


def pb_path(v: int) -> Path:
    return PLAYBOOKS / f"v{v:03d}.yaml"


def case_dirs(set_name: str) -> list[Path]:
    d = CASES / set_name
    return sorted(p for p in d.iterdir() if p.is_dir()) if d.exists() else []


# ---- evaluation ------------------------------------------------------------------
def evaluate(version: int, set_name: str, dirs: list[Path] | None = None, model: str | None = None) -> list[dict]:
    key = (version, set_name, model or "")
    custom = dirs is not None
    if key in _cache and not custom:
        return _cache[key]
    dirs = dirs if custom else case_dirs(set_name)
    if model:
        os.environ["BALLAST_MODEL"] = model

    def one(d: Path) -> dict:
        run = run_case(str(pb_path(version)), str(d))
        chk = check(d, run["recommendation"], run["error"])
        store.log_run(version, set_name, run, chk)
        return {"case_dir": str(d), "run": run, "check": chk}

    with ThreadPoolExecutor(WORKERS) as ex:
        out = list(ex.map(one, dirs))
    if not custom:
        _cache[key] = out
    passed = sum(r["check"]["passed"] for r in out)
    log(f"  v{version} {set_name}: {passed}/{len(out)} passed, mean {metrics(out)['mean_score']:.3f}")
    return out


def metrics(results: list[dict]) -> dict:
    if not results:
        return {"mean_score": 0.0, "pass_rate": 0.0, "n": 0, "violations": {}}
    viol: dict[str, int] = {}
    for r in results:
        for v in r["check"]["violations"]:
            viol[v["rule"]] = viol.get(v["rule"], 0) + 1
    return {"mean_score": round(sum(r["check"]["score"] for r in results) / len(results), 4),
            "pass_rate": round(sum(r["check"]["passed"] for r in results) / len(results), 4),
            "n": len(results), "violations": viol,
            "tokens": sum((r["run"].get("tokens_in") or 0) + (r["run"].get("tokens_out") or 0) for r in results),
            "seconds": round(sum(r["run"].get("seconds") or 0 for r in results), 1)}


def update_clients(version: int, results: list[dict]) -> None:
    """Each test client's personal agent = the shipped version; the UI's client view reads this."""
    for r in results:
        case = load_case(r["case_dir"])
        c = case["client"]
        store.upsert("clients", {"client_id": c["client_id"]}, {
            "name": c.get("name", c["client_id"]), "age": c.get("age"), "risk_score": c.get("risk_score"),
            "occupation": c.get("occupation"), "events": [{"type": e["type"], "date": e.get("date")} for e in case["events"]],
            "agent_version": version, "last_recommendation": r["run"].get("recommendation"),
            "last_check": {k: r["check"][k] for k in ("score", "passed", "violations")}})


def failures_for_mentor(results: list[dict], k: int = 8) -> list[str]:
    bad = sorted((r for r in results if not r["check"]["passed"]), key=lambda r: r["check"]["score"])
    return [mentor.summarize_failure(load_case(r["case_dir"]), r["run"], r["check"]) for r in bad[:k]]


def regressions(parent: list[dict], cand: list[dict]) -> list[str]:
    was = {r["check"]["case_id"] for r in parent if r["check"]["passed"]}
    return sorted(r["check"]["case_id"] for r in cand if r["check"]["case_id"] in was and not r["check"]["passed"])


# ---- playbook bookkeeping -----------------------------------------------------------
def load_pb(v: int) -> tuple[str, dict]:
    text = pb_path(v).read_text(encoding="utf-8")
    return text, yaml.safe_load(text)


def ensure_baseline() -> int:
    """v0 is the shipped baseline if nothing has shipped yet."""
    shipped = store.last_shipped()
    if shipped:
        if not pb_path(shipped["version"]).exists():
            pb_path(shipped["version"]).write_text(shipped["yaml"], encoding="utf-8")
        return shipped["version"]
    text, pb = load_pb(0)
    log("baseline: evaluating v0")
    res = {s: evaluate(0, s) for s in ("practice", "test", "regression")}
    store.save_playbook(0, None, text, pb.get("changelog", ""), "shipped")
    store.log_generation({"version": 0, "parent": None, "mode": "training",
                          **{s: metrics(r) for s, r in res.items()},
                          "decision": "shipped", "reason": "baseline", "compliance": None})
    update_clients(0, res["test"])
    return 0


def propose(parent_v: int, failures: list[str], scores: dict, analysis: str | None = None) -> dict | None:
    parent_text, _ = load_pb(parent_v)
    feedback = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        out = mentor.mentor_propose(parent_text, failures, scores, analysis, feedback)
        if not out["errors"]:
            return out
        feedback = "; ".join(out["errors"])
        log(f"  mentor attempt {attempt} invalid: {feedback}")
    return None


# ---- training mode ---------------------------------------------------------------------
def train(generations: int) -> None:
    current = ensure_baseline()
    for _ in range(generations):
        parent_text, parent = load_pb(current)
        log(f"\n== generation from v{current} ==")
        practice = evaluate(current, "practice")
        fails = failures_for_mentor(practice)
        if not fails:
            log("  no practice failures; nothing to learn")
            break
        p_test = evaluate(current, "test")
        p_reg = evaluate(current, "regression")
        out = propose(current, fails, {"practice": metrics(practice)["mean_score"],
                                       "test": metrics(p_test)["mean_score"]})
        # Every candidate gets a fresh version number, so rejected ones stay visible.
        nxt = max([p["version"] for p in store.find("playbooks")] + [current]) + 1
        if out is not None:
            out["playbook"]["version"], out["playbook"]["parent"] = nxt, current
            out["yaml"] = yaml.safe_dump(out["playbook"], sort_keys=False, allow_unicode=True)
        if out is None:
            store.log_generation({"version": nxt, "parent": current, "mode": "training",
                                  "decision": "rejected", "reason": "invalid_playbook", "compliance": None})
            continue
        review = mentor.compliance_review(parent_text, out["yaml"])
        pb_path(nxt).write_text(out["yaml"], encoding="utf-8")
        store.save_playbook(nxt, current, out["yaml"], out["playbook"].get("changelog", ""), "candidate")
        if review["verdict"] == "block":
            reason, res = f"compliance_block: {review['note']}", {}
        else:
            res = {"practice": evaluate(nxt, "practice"), "test": evaluate(nxt, "test"),
                   "regression": evaluate(nxt, "regression")}
            gain = metrics(res["test"])["mean_score"] - metrics(p_test)["mean_score"]
            regs = regressions(p_reg, res["regression"])
            if regs:
                reason = f"regression_fail: {', '.join(regs)}"
            elif gain < MIN_GAIN:
                reason = f"no_test_gain: {gain:+.3f} (needs +{MIN_GAIN})"
            else:
                reason = f"test {gain:+.3f} vs v{current}; regression held"
        shipped = reason.startswith("test ")
        store.set_playbook_status(nxt, "shipped" if shipped else "rejected")
        store.log_generation({"version": nxt, "parent": current, "mode": "training",
                              **{s: metrics(r) for s, r in res.items()},
                              "decision": "shipped" if shipped else "rejected", "reason": reason,
                              "compliance": review, "mentor_tokens": out["reply"].tokens_in + out["reply"].tokens_out})
        log(f"  v{nxt}: {'SHIPPED' if shipped else 'REJECTED'} ({reason})")
        if shipped:
            current = nxt
            update_clients(nxt, res["test"])


# ---- drift mode ----------------------------------------------------------------------
def drift() -> None:
    current = ensure_baseline()
    gen = [g for g in store.find("generations", {"version": current})]
    baseline = (gen[-1].get("test") or {}).get("mean_score", 1.0) if gen else 1.0
    trusted = trusted_rules_from([r["check"] for r in evaluate(current, "test")])
    log(f"\n== drift monitor on v{current} (baseline {baseline:.3f}, trusted {sorted(trusted)}) ==")
    # Gate 1 (Snap, before running): which new events put rules at risk that the playbook doesn't cover?
    _, cur_pb = load_pb(current)
    gates = []
    for d in case_dirs("drift"):
        case = load_case(d)
        if case["events"]:
            try:
                g = snap.event_gate(case, case["events"][-1], cur_pb)
                g["case_id"] = case["client"]["client_id"]
                gates.append(g)
            except Exception as e:
                log(f"  snap event gate failed on {d.name}: {e}")
    flagged = [g for g in gates if g["rerun_now"]]
    if gates:
        store.log_drift({"level": "yellow" if flagged else "green", "action": "event_gate", "gates": gates,
                         "from_version": current, "to_version": current, "violations": [],
                         "rolling_score": None, "baseline": baseline, "case_ids": [g["case_id"] for g in flagged]})
        log(f"  snap event gate: {len(flagged)}/{len(gates)} new events put rules at risk with no playbook coverage "
            f"({', '.join(sorted({r for g in flagged for r in g['at_risk']})) or 'none'})")
    # Run flagged cases first (early warning), then the rest.
    order = {g["case_id"]: i for i, g in enumerate(flagged)}
    dirs = sorted(case_dirs("drift"), key=lambda d: order.get(d.name, 999))
    drift_res = evaluate(current, "drift", dirs)
    report = drift_level([r["check"] for r in drift_res], baseline, trusted)
    # Gate 2 (Snap, after running): independent verdict on the window; rules stay authoritative.
    verdict = None
    try:
        window = [{**r["check"], "tags": "/".join(e["type"] for e in load_case(r["case_dir"])["events"])} for r in drift_res]
        verdict = snap.window_verdict(window, baseline, trusted, report)
        log(f"  snap verdict: level {verdict['level']} (rules say {report['level']}), rollback p={verdict['rollback_p']}, "
            f"rule at risk {verdict['rule']}, novel p={verdict['novel_p']}, urgency {verdict['urgency']}/3")
    except Exception as e:
        log(f"  snap window verdict failed: {e}")
    store.log_drift({"level": report["level"], "rolling_score": report["rolling_score"], "baseline": baseline,
                     "violations": report["violations"][:50], "action": "none" if report["level"] == "green" else "detected",
                     "from_version": current, "to_version": current, "case_ids": report["case_ids"], "snap": verdict})
    log(f"  level: {report['level']} ({'; '.join(report['reasons']) or 'ok'})")
    if report["level"] == "green":
        return

    # Contain: roll back to the last good version (the shipped parent), mark current rolled back.
    cur_pb = store.find("playbooks", {"version": current})
    good = (cur_pb[0].get("parent") if cur_pb else None)
    good = current if good is None else good
    if report["level"] == "red" and good != current:
        store.set_playbook_status(current, "rolled_back")
        store.log_drift({"level": "red", "rolling_score": report["rolling_score"], "baseline": baseline,
                         "violations": [], "action": "rollback", "from_version": current, "to_version": good,
                         "case_ids": report["case_ids"], "snap": verdict})
        log(f"  rolled back v{current} -> v{good}")
    drifted = [Path(r["case_dir"]) for r in drift_res if r["check"]["case_id"] in report["case_ids"]]

    # Diagnose: SubQ reads every run at once (long context).
    # Logged after the rollback event and before realign, so the UI replay orders it correctly.
    analysis = mentor.analyze_drift(store.find("runs"), store.find("playbooks"))
    store.insert("drift_analysis", {**analysis, "time": __import__("store").now()})
    log(f"  analyst ({analysis.get('provider')}): {analysis.get('summary', '')[:200]}")
    store.log_drift({"level": "red", "rolling_score": report["rolling_score"], "baseline": baseline,
                     "violations": [], "action": "realign", "from_version": good, "to_version": None,
                     "case_ids": report["case_ids"]})

    # Realign + verify, up to 3 attempts.
    good_reg = evaluate(good, "regression")
    fails = failures_for_mentor(drift_res)
    analysis_text = json.dumps({"summary": analysis.get("summary"), "handoff": analysis.get("handoff"),
                                "patterns": analysis.get("patterns"),
                                "snap_verdict": {k: (verdict or {}).get(k) for k in ("rule", "novel_p", "urgency")},
                                "events_at_risk": [{"event": g["event"], "at_risk": g["at_risk"]} for g in flagged]},
                               indent=1)
    latest = max(p["version"] for p in store.find("playbooks"))
    for attempt in range(1, MAX_ATTEMPTS + 1):
        out = propose(good, fails, {"practice": "n/a", "test": baseline}, analysis_text)
        if out is None:
            continue
        nxt = latest + attempt
        out["playbook"]["version"], out["playbook"]["parent"] = nxt, good
        text = yaml.safe_dump(out["playbook"], sort_keys=False, allow_unicode=True)
        pb_path(nxt).write_text(text, encoding="utf-8")
        store.save_playbook(nxt, good, text, out["playbook"].get("changelog", ""), "candidate")
        review = mentor.compliance_review(load_pb(good)[0], text)
        d_res = evaluate(nxt, "drift", drifted)
        reg = evaluate(nxt, "regression")
        d_pass = sum(r["check"]["passed"] for r in d_res)
        regs = regressions(good_reg, reg)
        ok = review["verdict"] == "approve" and d_pass >= DRIFT_PASS * len(d_res) and not regs
        reason = (f"passes {d_pass}/{len(d_res)} drift cases; regression {'held' if not regs else 'failed: ' + ', '.join(regs)}"
                  + ("" if review["verdict"] == "approve" else f"; compliance_block: {review['note']}"))
        store.set_playbook_status(nxt, "shipped" if ok else "rejected")
        store.log_generation({"version": nxt, "parent": good, "mode": "drift",
                              "practice": metrics([]), "test": metrics(d_res), "regression": metrics(reg),
                              "decision": "shipped" if ok else "rejected", "reason": reason, "compliance": review})
        log(f"  fix v{nxt} attempt {attempt}: {'SHIPPED' if ok else 'rejected'} ({reason})")
        if ok:
            store.log_drift({"level": "green", "rolling_score": metrics(d_res)["mean_score"], "baseline": baseline,
                             "violations": [], "action": "shipped_fix", "from_version": good, "to_version": nxt,
                             "case_ids": report["case_ids"]})
            return
        fails = failures_for_mentor(d_res) or fails
    store.log_drift({"level": "red", "rolling_score": report["rolling_score"], "baseline": baseline,
                     "violations": [], "action": "escalated", "from_version": good, "to_version": good,
                     "case_ids": report["case_ids"]})
    log("  escalated to a human after 3 failed fixes; keeping last good version")


# ---- model benchmark -----------------------------------------------------------------
def bench(models: list[str], set_name: str, version: int) -> None:
    rows = []
    for m in models:
        res = evaluate(version, set_name, model=m)
        rows.append({"model": m, "set": set_name, "version": version, **metrics(res)})
        log(json.dumps(rows[-1]))
    store.insert("generations", {"version": version, "parent": None, "mode": "benchmark",
                                 "decision": "benchmark", "reason": f"{len(models)} models on {set_name}",
                                 "benchmark": rows, "compliance": None})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["train", "drift", "bench"])
    ap.add_argument("--generations", type=int, default=3)
    ap.add_argument("--models", default="")
    ap.add_argument("--set", default="test")
    ap.add_argument("--version", type=int, default=None)
    a = ap.parse_args()
    log(f"store: {store.backend}")
    if a.mode == "train":
        train(a.generations)
    elif a.mode == "drift":
        drift()
    else:
        bench([m for m in a.models.split(",") if m], a.set, a.version if a.version is not None else ensure_baseline())
