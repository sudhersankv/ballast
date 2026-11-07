"""Live drift watcher: MongoDB change stream on `life_events` -> Snap event gate -> re-run -> drift.

  python runtime/watch.py                 # watch forever
  python runtime/inject_event.py c-021 layoff --details '{"severity": 20000}'   # demo trigger

On each inserted life event:
  1. Build the client's case with the new event appended (from scenarios/cases/*/<client_id>).
  2. Snap event gate with the shipped playbook: rules at risk? covered by the playbook? urgency?
  3. If rerun_now (or always with --always-run): run the agent on the updated case, score it.
  4. A hard violation of a trusted rule -> log red and hand off to drift mode (rollback + realign).
Everything is logged to drift_events / runs / loop_log so the UI shows it live.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "runtime"), str(ROOT / "checker"), str(ROOT / "agent")]

import loop  # noqa: E402  (shares store, logging, evaluate, drift)
import snap  # noqa: E402
from check import check, load_case  # noqa: E402
from drift import trusted_rules_from  # noqa: E402
from run_case import run_case  # noqa: E402


def find_case(client_id: str) -> Path | None:
    for d in (ROOT / "scenarios" / "cases").glob(f"*/{client_id}"):
        if d.is_dir():
            return d
    return None


def handle(ev: dict, always_run: bool = False) -> None:
    store, log = loop.store, loop.log
    src = find_case(ev["client_id"])
    if src is None:
        log(f"[watch] unknown client {ev['client_id']}")
        return
    shipped = store.last_shipped()
    current = shipped["version"] if shipped else 0  # the version clients are running right now
    if shipped and not loop.pb_path(current).exists():
        loop.pb_path(current).write_text(shipped["yaml"], encoding="utf-8")
    _, pb = loop.load_pb(current)
    tmp = Path(tempfile.mkdtemp(prefix="evt-")) / src.name
    shutil.copytree(src, tmp)
    events = json.loads((tmp / "events.json").read_text())
    new = {"id": f"e{len(events['events']) + 1}", "type": ev["type"], "date": ev.get("date"),
           "details": ev.get("details") or {}}
    events["events"].append(new)
    (tmp / "events.json").write_text(json.dumps(events))

    case = load_case(tmp)
    g = snap.event_gate(case, new, pb)
    log(f"[watch] {ev['client_id']} {ev['type']}: snap at-risk {g['at_risk'] or 'none'}, "
        f"covered p={g['covered']}, urgency {g['urgency']}/3, rerun_now={g['rerun_now']} ({g['seconds']}s)")
    store.log_drift({"level": "yellow" if g["rerun_now"] else "green", "action": "event_gate", "gates": [{**g, "case_id": ev["client_id"]}],
                     "from_version": current, "to_version": current, "violations": [], "rolling_score": None,
                     "baseline": None, "case_ids": [ev["client_id"]]})
    if not (g["rerun_now"] or always_run) or GATE_ONLY:
        return

    run = run_case(str(loop.pb_path(current)), str(tmp))
    chk = check(tmp, run["recommendation"], run["error"])
    store.log_run(current, "live", run, chk)
    trusted = trusted_rules_from([r["check"] for r in loop.evaluate(current, "test")]) if always_run else \
        {"risk_band", "emergency_fund", "concentration", "cited", "valid_output"}
    hard = [v for v in chk["violations"] if v["severity"] == "hard" and v["rule"] in trusted]
    log(f"[watch] {ev['client_id']} re-run on v{current}: score {chk['score']:.2f}, "
        f"{'PASS' if chk['passed'] else 'FAIL'} {'; '.join(v['rule'] + ': ' + v['detail'] for v in chk['violations'])}")
    store.upsert("clients", {"client_id": ev["client_id"]}, {
        "agent_version": current, "last_recommendation": run["recommendation"],
        "last_check": {k: chk[k] for k in ("score", "passed", "violations")}})
    if hard:
        store.log_drift({"level": "red", "action": "detected", "from_version": current, "to_version": current,
                         "violations": hard, "rolling_score": chk["score"], "baseline": None,
                         "case_ids": [ev["client_id"]], "trigger": "life_event"})
        log(f"[watch] RED: trusted rule broken on a live event -> drift mode")
        loop.drift()


GATE_ONLY = False


def main() -> None:
    global GATE_ONLY
    ap = argparse.ArgumentParser()
    ap.add_argument("--always-run", action="store_true")
    ap.add_argument("--gate-only", action="store_true", help="Snap gate only; skip agent re-runs (no Pi needed)")
    a = ap.parse_args()
    GATE_ONLY = a.gate_only
    loop.log("[watch] listening for new life events (MongoDB change stream)")
    for ev in loop.store.watch_life_events():
        try:
            handle(ev, a.always_run)
        except Exception as e:
            loop.log(f"[watch] error handling event: {e}")


if __name__ == "__main__":
    main()
