"""Per-client alignment over time: one client's personal agent improves checkpoint by checkpoint.

  python runtime/journey.py                 # all journeys in parallel
  python runtime/journey.py j-001 j-004     # selected journeys

For each journey (one client, quarterly checkpoints t01..t10; meta.json marks train vs holdout):
  TRAIN checkpoints, in time order:
    1. The client's current playbook runs on the checkpoint (as of that date). Checker + market backtest.
    2. On failure: Muse diagnoses the root cause, maps it to the triggering event, and rewrites THIS
       client's playbook (with a plain-language lesson).
    3. Verify: the candidate must pass this checkpoint's hard rules and not break any earlier train
       checkpoint the client's agent already passed, and Gemini must approve. Up to 2 attempts.
  HOLDOUT checkpoints (later in time, never shown to Muse):
    4. Run the client's final playbook AND the starting playbook on every holdout checkpoint.
       Alignment gain = final vs start on the client's own future.
Everything is logged: runs (set "journey", case_id "j-001/t04"), journey_playbooks, journey_steps, loop_log.
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "runtime"), str(ROOT / "checker"), str(ROOT / "agent"), str(ROOT / "scenarios")]

import mentor  # noqa: E402
from backtest import backtest, holdout_path  # noqa: E402
from check import check, load_case  # noqa: E402
from loop import log, store  # noqa: E402
from run_case import run_case  # noqa: E402

JOURNEYS = ROOT / "scenarios" / "journeys"
WORK = ROOT / "runs" / "journeys"
BASE = Path(os.environ.get("JOURNEY_BASE_PLAYBOOK", ROOT / "agent" / "playbooks" / "v000.yaml"))
ATTEMPTS = 2


def run_checkpoint(jid: str, cp: str, pb_file: Path, version: int, phase: str) -> dict:
    d = JOURNEYS / jid / cp
    run = run_case(str(pb_file), str(d))
    chk = check(d, run["recommendation"], run["error"])
    try:
        fut = ROOT / "scenarios" / "holdout" / "journeys" / jid / cp / "future.json"
        chk["backtest"] = backtest(d, run["recommendation"], fut if fut.exists() else None)
    except Exception as e:
        chk["backtest"] = {"error": str(e)}
    chk["case_id"] = f"{jid}/{cp}"
    run["case_id"] = f"{jid}/{cp}"
    doc = store.log_run(version, "journey", run, chk)
    store.upsert("runs", {"run_id": doc["run_id"]}, {**doc, "journey": jid, "checkpoint": cp, "phase": phase})
    return {"cp": cp, "dir": d, "run": run, "check": chk, "run_id": doc["run_id"]}


def hard_ok(chk: dict) -> bool:
    return all(r["passed"] for r in chk.get("results", []) if r["severity"] == "hard")


def save_pb(jid: str, version: int, parent: int | None, text: str, status: str, cp: str | None) -> Path:
    p = WORK / jid / f"v{version:03d}.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    pb = yaml.safe_load(text)
    store.upsert("journey_playbooks", {"journey": jid, "version": version}, {
        "parent": parent, "yaml": text, "changelog": pb.get("changelog", ""), "lessons": pb.get("lessons") or [],
        "status": status, "learned_at": cp})
    return p


def step(jid: str, cp: str, **kw) -> None:
    store.insert("journey_steps", {"journey": jid, "checkpoint": cp, **kw})


def run_journey(jid: str) -> dict:
    meta = json.loads((JOURNEYS / jid / "meta.json").read_text(encoding="utf-8"))
    cps = meta["checkpoints"]
    train = [c["id"] for c in cps if c.get("split") == "train"]
    hold = [c["id"] for c in cps if c.get("split") != "train"]
    who = meta.get("persona", {}).get("name", jid) if isinstance(meta.get("persona"), dict) else meta.get("persona", jid)
    log(f"[journey {jid}] {who}: {meta.get('regime', '')} | train {train[0]}-{train[-1]}, holdout {hold[0]}-{hold[-1]}")

    base_text = BASE.read_text(encoding="utf-8")
    start_v = yaml.safe_load(base_text)["version"]
    cur_v, cur_text = start_v, base_text
    cur_file = save_pb(jid, cur_v, None, cur_text, "shipped", None)
    passed_before: list[str] = []

    for cp in train:
        r = run_checkpoint(jid, cp, cur_file, cur_v, "train")
        c = r["check"]
        log(f"[journey {jid}] {cp} v{cur_v}: score {c['score']:.2f} {'PASS' if c['passed'] else 'FAIL'}"
            + ("" if c["passed"] else " | " + "; ".join(f"{v['rule']}: {v['detail']}" for v in c["violations"])))
        step(jid, cp, phase="train", version=cur_v, score=c["score"], passed=c["passed"],
             violations=c["violations"], backtest=c.get("backtest"), run_id=r["run_id"], action="evaluate")
        if c["passed"]:
            passed_before.append(cp)
            continue
        fail_text = [mentor.summarize_failure(load_case(r["dir"]), r["run"], c)]
        feedback = None
        for attempt in range(1, ATTEMPTS + 1):
            out = mentor.mentor_propose(cur_text, fail_text, {"practice": c["score"], "test": "n/a"}, None, feedback)
            if out["errors"]:
                feedback = "; ".join(out["errors"])
                log(f"[journey {jid}] {cp} mentor attempt {attempt} invalid: {feedback}")
                continue
            cand_text = out["yaml"]
            review = mentor.compliance_review(cur_text, cand_text)
            new_v = cur_v + 1
            cand_file = save_pb(jid, new_v, cur_v, cand_text, "candidate", cp)
            lessons = (out["playbook"].get("lessons") or [])[len(yaml.safe_load(cur_text).get("lessons") or []):]
            if review["verdict"] == "block":
                reason = f"compliance_block: {review['note']}"
                ok = False
            else:
                # Verify on this checkpoint + every earlier train checkpoint the agent already passed.
                checks = [run_checkpoint(jid, x, cand_file, new_v, "verify") for x in [cp] + passed_before]
                now = checks[0]["check"]
                broke = [x["cp"] for x in checks[1:] if not x["check"]["passed"]]
                ok = hard_ok(now) and now["score"] > c["score"] and not broke
                reason = (f"{cp} score {c['score']:.2f}->{now['score']:.2f}"
                          + (f"; broke earlier {', '.join(broke)}" if broke else "; earlier checkpoints held"))
            status = "shipped" if ok else "rejected"
            save_pb(jid, new_v, cur_v, cand_text, status, cp)
            step(jid, cp, phase="train", version=new_v, action="learn" if ok else "reject", reason=reason,
                 lessons=lessons, compliance=review, changelog=out["playbook"].get("changelog", ""),
                 mentor_tokens=out["reply"].tokens_in + out["reply"].tokens_out)
            log(f"[journey {jid}] {cp} v{new_v} {'LEARNED' if ok else 'rejected'} ({reason})"
                + (f" | lesson: {lessons[0].get('lesson')}" if ok and lessons else ""))
            if ok:
                cur_v, cur_text, cur_file = new_v, cand_text, cand_file
                passed_before.append(cp)
                break
            feedback = f"rejected: {reason}"

    # Holdout: the client's own future, final playbook vs the starting playbook.
    base_file = WORK / jid / f"v{start_v:03d}.yaml"

    def both(cp):
        return (run_checkpoint(jid, cp, base_file, start_v, "holdout_start"),
                run_checkpoint(jid, cp, cur_file, cur_v, "holdout_final") if cur_v != start_v else None)

    with ThreadPoolExecutor(3) as ex:
        pairs = list(ex.map(both, hold))
    s_pass = sum(p[0]["check"]["passed"] for p in pairs)
    f_pass = sum((p[1] or p[0])["check"]["passed"] for p in pairs)
    s_mean = sum(p[0]["check"]["score"] for p in pairs) / len(pairs)
    f_mean = sum((p[1] or p[0])["check"]["score"] for p in pairs) / len(pairs)

    def bt_count(side, key):
        return sum(1 for p in pairs if ((p[side] or p[0])["check"].get("backtest") or {}).get(key))
    summary = {"journey": jid, "client": who, "regime": meta.get("regime"), "start_version": start_v,
               "final_version": cur_v, "lessons": len(yaml.safe_load(cur_text).get("lessons") or []),
               "holdout_pass_start": f"{s_pass}/{len(pairs)}", "holdout_pass_final": f"{f_pass}/{len(pairs)}",
               "holdout_mean_start": round(s_mean, 3), "holdout_mean_final": round(f_mean, 3),
               "breaches_start": bt_count(0, "emergency_fund_breached"), "breaches_final": bt_count(1, "emergency_fund_breached")}
    for p in pairs:
        f = p[1] or p[0]
        step(jid, p[0]["cp"], phase="holdout", version=cur_v, score=f["check"]["score"], passed=f["check"]["passed"],
             start_score=p[0]["check"]["score"], start_passed=p[0]["check"]["passed"], action="prove",
             violations=f["check"]["violations"], backtest=f["check"].get("backtest"))
    store.upsert("journey_summaries", {"journey": jid}, summary)
    log(f"[journey {jid}] HOLDOUT {summary['holdout_pass_start']} -> {summary['holdout_pass_final']} "
        f"(mean {s_mean:.2f} -> {f_mean:.2f}), {summary['lessons']} lessons, breaches "
        f"{summary['breaches_start']} -> {summary['breaches_final']}")
    return summary


if __name__ == "__main__":
    ids = sys.argv[1:] or sorted(p.name for p in JOURNEYS.iterdir() if p.is_dir() and p.name.startswith("j-"))
    with ThreadPoolExecutor(len(ids)) as ex:
        results = list(ex.map(run_journey, ids))
    print(json.dumps(results, indent=1))
