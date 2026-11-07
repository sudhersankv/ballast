"""Live-run worker: runs agent jobs requested from the website, streaming each step to MongoDB.

  python runtime/worker.py        # runs on the Fly runner (iad); needs Pi + model keys

The website inserts a doc into `jobs`:
  {job_id, status: "queued", case: "test/c-021" | "stress/s-0042" | "journeys/j-001/t04" | "fixtures/c-014",
   model: "meta/muse-spark-1.3" | "subq/subq-preview" | "google/gemini-3.8-flash",
   playbook_version: int | null, journey: "j-001" | null, created_at}
This worker picks it up via a change stream (and sweeps queued jobs on start), then updates the same doc:
  status running -> done | error, started_at, finished_at,
  steps: [... appended live as the agent works ...],
  result: {recommendation, check {score, passed, violations, results}, backtest, turns, tokens_in, tokens_out, seconds, model}
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "runtime"), str(ROOT / "checker"), str(ROOT / "agent"), str(ROOT / "scenarios")]

from backtest import backtest  # noqa: E402
from check import check  # noqa: E402
from run_case import run_case  # noqa: E402
from store import Store, now  # noqa: E402

ALLOWED_MODELS = {"meta/muse-spark-1.3", "meta/muse-wonder-1.0", "subq/subq-preview", "google/gemini-3.8-flash"}
MAX_PARALLEL = int(os.environ.get("WORKER_PARALLEL", "3"))
store = Store()
sem = threading.Semaphore(MAX_PARALLEL)


def case_dir(spec: str) -> Path:
    parts = spec.strip("/").split("/")
    if parts[0] == "journeys":
        d = ROOT / "scenarios" / "journeys" / parts[1] / parts[2]
    elif parts[0] == "fixtures":
        d = ROOT / "scenarios" / "fixtures" / parts[1]
    else:
        d = ROOT / "scenarios" / "cases" / parts[0] / parts[1]
    if not (d / "client.json").exists() or ".." in spec:
        raise ValueError(f"unknown case {spec!r}")
    return d


def playbook_file(job: dict) -> Path:
    v = job.get("playbook_version")
    if v is None:
        return ROOT / "agent" / "playbooks" / "v000.yaml"
    coll = "journey_playbooks" if job.get("journey") else "playbooks"
    q = {"version": int(v), **({"journey": job["journey"]} if job.get("journey") else {})}
    rows = store.find(coll, q)
    if not rows:
        raise ValueError(f"playbook v{v} not found in {coll}")
    p = Path(tempfile.mkdtemp(prefix="job-pb-")) / f"v{int(v):03d}.yaml"
    p.write_text(rows[0]["yaml"], encoding="utf-8")
    return p


def update(job_id: str, fields: dict, push_step: dict | None = None) -> None:
    upd = {"$set": fields}
    if push_step is not None:
        upd["$push"] = {"steps": push_step}
    store.db.jobs.update_one({"job_id": job_id}, upd)


def run_job(job: dict) -> None:
    jid = job["job_id"]
    with sem:
        try:
            if job.get("model") not in ALLOWED_MODELS:
                raise ValueError(f"model not allowed: {job.get('model')}")
            d = case_dir(job["case"])
            pb = playbook_file(job)
            update(jid, {"status": "running", "started_at": now(), "steps": []})
            res = run_case(str(pb), str(d), on_step=lambda s: update(jid, {"updated_at": now()}, push_step=s),
                           model=job["model"])
            chk = check(d, res["recommendation"], res["error"])
            try:
                bt = backtest(d, res["recommendation"])
            except Exception as e:
                bt = {"error": str(e)}
            result = {k: res.get(k) for k in ("recommendation", "turns", "tokens_in", "tokens_out", "seconds", "model", "error")}
            result["check"] = {k: chk[k] for k in ("score", "passed", "violations", "results")}
            result["backtest"] = bt
            update(jid, {"status": "done", "finished_at": now(), "result": result})
        except Exception as e:
            update(jid, {"status": "error", "finished_at": now(), "error": f"{e.__class__.__name__}: {e}",
                         "trace": traceback.format_exc()[-1500:]})


def start(job: dict) -> None:
    # claim atomically so two workers never run the same job
    claimed = store.db.jobs.find_one_and_update({"job_id": job["job_id"], "status": "queued"},
                                                {"$set": {"status": "claimed"}})
    if claimed:
        threading.Thread(target=run_job, args=(claimed,), daemon=True).start()


def main() -> None:
    if store.db is None:
        raise SystemExit("worker needs MongoDB")
    print(f"[worker] db={store.db_name}, parallel={MAX_PARALLEL}", flush=True)
    for j in store.db.jobs.find({"status": "queued"}, {"_id": 0}):
        start(j)
    with store.db.jobs.watch([{"$match": {"operationType": "insert"}}]) as stream:
        for ch in stream:
            doc = ch["fullDocument"]
            doc.pop("_id", None)
            print(f"[worker] job {doc.get('job_id')} {doc.get('case')} {doc.get('model')}", flush=True)
            start(doc)


if __name__ == "__main__":
    main()
