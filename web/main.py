"""ballast. web: FastAPI JSON API + static single-page app.

Reads MongoDB (MONGODB_URI, MONGODB_DB). Falls back to seed.json when Mongo is
unreachable or the runtime hasn't written playbooks/generations yet.
"""
import difflib
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).parent
SEED = json.loads((HERE / "seed.json").read_text())
COLLS = ["playbooks", "generations", "drift_events", "clients", "runs"]
OPTIONAL = ["drift_analysis", "benchmarks", "journeys"]

app = FastAPI(title="ballast.")
_cache = {"t": 0.0, "data": None, "source": "demo"}


def _load(force_demo: bool = False):
    """Return (data, source). Cached for 5 s so the UI can poll cheaply."""
    if force_demo:
        return SEED, "demo"
    if _cache["data"] is not None and time.time() - _cache["t"] < 5:
        return _cache["data"], _cache["source"]
    # Real data only. The story reads the first db in STORY_DB (comma-separated) that has playbooks + generations.
    # Seed data is used only when a caller asks for ?demo=1. With nothing real yet, every collection is empty.
    data, source = {c: [] for c in COLLS + OPTIONAL}, "none"
    data["_db"] = None
    uri = os.environ.get("MONGODB_URI")
    if uri:
        try:
            if "client" not in _cache:
                from pymongo import MongoClient

                _cache["client"] = MongoClient(uri, serverSelectionTimeoutMS=3000)
            for name in [x.strip() for x in os.environ.get("STORY_DB", "ballast_bench_muse,ballast_muse").split(",") if x.strip()]:
                db = _cache["client"][name]
                if not db.generations.find_one({}, {"_id": 1}):
                    continue
                live = {c: list(db[c].find({}, {"_id": 0, "steps": 0} if c == "runs" else {"_id": 0})) for c in COLLS + OPTIONAL}
                if live["playbooks"] and live["generations"]:
                    live["_db"] = name
                    data, source = live, "live"
                    break
        except Exception:
            pass
    _cache.update(t=time.time(), data=data, source=source)
    return data, source


def _t(e: dict) -> str:
    return str(e.get("time") or e.get("created_at") or "")


def _shipped_current(gens, drift):
    """Current shipped version: last shipped generation, adjusted by the latest rollback/fix."""
    shipped = [g["version"] for g in sorted(gens, key=lambda g: g["created_at"]) if g["decision"] == "shipped"]
    cur = shipped[-1] if shipped else None
    for d in sorted(drift, key=_t):
        if d["action"] in ("rollback", "shipped_fix"):
            cur = d["to_version"]
    return cur


@app.get("/api/health")
def health(demo: int = 0):
    _, source = _load(bool(demo))
    return {"ok": True, "source": source}


@app.get("/api/overview")
def overview(demo: int = 0):
    d, source = _load(bool(demo))
    gens = sorted(d["generations"], key=lambda g: g["version"])
    drift = sorted(d["drift_events"], key=_t)
    cur = _shipped_current(gens, drift)
    by_v = {g["version"]: g for g in gens}
    base = by_v.get(0, gens[0] if gens else None)
    latest = by_v.get(cur)
    light = next((e["level"] for e in reversed(drift) if e.get("action") != "event_gate"), "green")
    return {
        "source": source, "db": d.get("_db"),
        "current_version": cur,
        "drift_level": light,
        "test_score": latest["test"]["mean_score"] if latest else None,
        "test_pass_rate": latest["test"]["pass_rate"] if latest else None,
        "baseline_score": base["test"]["mean_score"] if base else None,
        "delta_vs_v0": round(latest["test"]["mean_score"] - base["test"]["mean_score"], 3) if latest and base else None,
        "counts": {
            "versions": len(d["playbooks"]),
            "shipped": sum(1 for g in gens if g["decision"] == "shipped"),
            "rejected": sum(1 for g in gens if g["decision"] == "rejected"),
            "drift_events": sum(1 for e in drift if e["level"] != "green" and e.get("action") != "event_gate"),
            "clients": len(d["clients"]),
            "runs": len(d["runs"]),
        },
    }


@app.get("/api/versions")
def versions(demo: int = 0):
    d, _ = _load(bool(demo))
    pbs = {p["version"]: p for p in d["playbooks"]}
    out = []
    for g in sorted(d["generations"], key=lambda g: g["version"]):
        p = pbs.get(g["version"], {})
        v_runs = [r for r in d["runs"] if r["playbook_version"] == g["version"] and r["set"] == "test"]
        by_rule = {}
        for r in v_runs:
            for x in r["violations"]:
                by_rule[x["rule"]] = by_rule.get(x["rule"], 0) + 1
        out.append({**g, "changelog": p.get("changelog", ""), "status": p.get("status", g["decision"]),
                    "violations_by_rule": by_rule, "test_runs": len(v_runs)})
    return out


@app.get("/api/versions/{v}")
def version_detail(v: int, demo: int = 0):
    d, _ = _load(bool(demo))
    pbs = {p["version"]: p for p in d["playbooks"]}
    if v not in pbs:
        raise HTTPException(404, f"No playbook version {v}")
    p = pbs[v]
    parent = pbs.get(p["parent"]) if p["parent"] is not None else None
    diff = list(difflib.unified_diff(
        (parent["yaml"] if parent else "").splitlines(), p["yaml"].splitlines(),
        fromfile=f"v{p['parent']}" if parent else "empty", tofile=f"v{v}", lineterm="", n=2))
    sample = [r for r in d["runs"] if r["playbook_version"] == v and r["violations"]][:8]
    return {**p, "diff": diff, "sample_violations": [
        {"case_id": r["case_id"], **x} for r in sample for x in r["violations"]][:12]}


@app.get("/api/drift")
def drift(demo: int = 0):
    d, _ = _load(bool(demo))
    return sorted(d["drift_events"], key=_t)


@app.get("/api/clients")
def clients(demo: int = 0):
    d, _ = _load(bool(demo))
    latest = {}
    for r in d["runs"]:
        if r["set"] == "test" and (r["case_id"] not in latest or r["playbook_version"] > latest[r["case_id"]]["playbook_version"]):
            latest[r["case_id"]] = r
    out = []
    for c in d["clients"]:
        r = latest.get(c["client_id"])
        out.append({k: c.get(k) for k in ("client_id", "name", "age", "risk_score", "events", "agent_version")} |
                   {"score": r["score"] if r else None, "passed": r["passed"] if r else None,
                    "trades": len((c.get("last_recommendation") or {}).get("trades", []))})
    return out


@app.get("/api/clients/{cid}")
def client_detail(cid: str, demo: int = 0):
    d, _ = _load(bool(demo))
    c = next((c for c in d["clients"] if c["client_id"] == cid), None)
    if not c:
        raise HTTPException(404, f"No client {cid}")
    history = sorted(
        ({"version": r["playbook_version"], "score": r["score"], "passed": r["passed"], "violations": r["violations"]}
         for r in d["runs"] if r["case_id"] == cid and r["set"] == "test"),
        key=lambda h: h["version"])
    return {**c, "history": history}


# ---------------------------------------------------------------- live view
LIVE_DBS = {"ballast_muse", "ballast_dev", "ballast", "ballast_bench_muse", "ballast_bench_subq"}
SET_SIZES = {"practice": 20, "test": 20, "regression": 10, "drift": 10}
SLIM = {"_id": 0, "run_id": 1, "playbook_version": 1, "set": 1, "case_id": 1, "model": 1, "score": 1, "passed": 1,
        "turns": 1, "seconds": 1, "error": 1, "created_at": 1, "violations": 1, "tokens_in": 1, "tokens_out": 1}


def _db(name: str | None):
    """Mongo database for the live view. Raises 503 if Mongo isn't configured."""
    name = name or os.environ.get("LIVE_DB", "ballast_dev")
    if name not in LIVE_DBS:
        raise HTTPException(400, f"db must be one of {sorted(LIVE_DBS)}")
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        raise HTTPException(503, "MONGODB_URI is not set on the server")
    if "client" not in _cache:
        from pymongo import MongoClient

        _cache["client"] = MongoClient(uri, serverSelectionTimeoutMS=3000)
    return _cache["client"][name], name


def _mongo_guard(fn):
    try:
        return fn()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"MongoDB unreachable ({e.__class__.__name__})")


def _slim(r: dict) -> dict:
    v = r.pop("violations", None) or []
    r["n_violations"] = len(v)
    r["top_violation"] = f"{v[0].get('rule')}: {v[0].get('detail')}" if v else None
    if r.get("error"):
        r["error"] = str(r["error"])[:160]
    return r


@app.get("/api/live/status")
def live_status(db: str | None = None):
    from datetime import datetime, timezone

    def q():
        d, name = _db(db)
        a = d.runs.find_one({}, {"_id": 0, "created_at": 1}, sort=[("created_at", -1)])
        b = d.loop_log.find_one({}, {"_id": 0, "created_at": 1}, sort=[("created_at", -1)])
        return name, [x["created_at"] for x in (a, b) if x]

    name, stamps = _mongo_guard(q)
    latest = max(stamps) if stamps else None
    age = None
    if latest:
        try:
            age = round((datetime.now(timezone.utc) - datetime.fromisoformat(latest)).total_seconds(), 1)
        except ValueError:
            pass
    return {"db": name, "last_activity": latest, "age_seconds": age, "active": age is not None and age < 120}


@app.get("/api/live")
def live(since: str | None = None, db: str | None = None, session: str | None = None):
    """New log lines and slim runs since `since` for the latest (or given) session, plus progress per block."""
    def q():
        d, name = _db(db)
        last = d.loop_log.find_one({}, {"_id": 0, "session": 1}, sort=[("created_at", -1)])
        sess = session or (last or {}).get("session")
        if sess:
            first = d.loop_log.find_one({"session": sess}, {"_id": 0, "created_at": 1}, sort=[("created_at", 1)])
            start = first["created_at"] if first else ""
        else:
            # no loop log yet (or it was reset): still show the runs from the last 12 hours
            if not d.runs.find_one({}, {"_id": 1}):
                return {"db": name, "session": None, "started_at": None, "log": [], "runs": [], "gates": [], "progress": None,
                        "blocks": [], "versions": []}
            sess, start = "runs", (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
        lq = {"session": sess, **({"created_at": {"$gt": since}} if since else {})}
        log = list(d.loop_log.find(lq, {"_id": 0}).sort("created_at", 1).limit(800))
        runs = [_slim(r) for r in d.runs.find({"created_at": {"$gt": max(start, since or "")}}, SLIM)
                .sort("created_at", 1).limit(800)]
        pipe = [{"$match": {"created_at": {"$gte": start}}},
                {"$group": {"_id": {"v": "$playbook_version", "s": "$set"}, "done": {"$sum": 1},
                            "passed": {"$sum": {"$cond": ["$passed", 1, 0]}}, "mean": {"$avg": "$score"},
                            "first": {"$min": "$created_at"}, "last": {"$max": "$created_at"}}},
                {"$sort": {"first": 1}}]
        blocks = [{"version": b["_id"]["v"], "set": b["_id"]["s"], "done": b["done"], "passed": b["passed"],
                   "failed": b["done"] - b["passed"], "mean": round(b["mean"] or 0, 3),
                   "total": max(SET_SIZES.get(b["_id"]["s"], b["done"]), b["done"]), "first": b["first"], "last": b["last"]}
                  for b in d.runs.aggregate(pipe)]
        versions = list(d.playbooks.find({}, {"_id": 0, "version": 1, "parent": 1, "status": 1, "changelog": 1,
                                                "created_at": 1}).sort("version", 1))
        # SubQ Snap event gates (fired by the change stream on new life events); not tied to a loop session
        gfloor = since or (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        gates = []
        for doc in d.drift_events.find({"action": "event_gate", "$or": [{"time": {"$gt": gfloor}}, {"created_at": {"$gt": gfloor}}]},
                                       {"_id": 0}).sort("time", 1).limit(200):
            t = doc.get("time") or doc.get("created_at")
            for g in doc.get("gates") or []:
                gates.append({**g, "time": t})
        return {"db": name, "session": sess, "started_at": start, "log": log, "runs": runs, "gates": gates,
                "progress": blocks[-1] if blocks else None, "blocks": blocks, "versions": versions}

    return _mongo_guard(q)


@app.get("/api/runs/{run_id}")
def run_detail(run_id: str, db: str | None = None):
    """Full run (trace steps, rule-by-rule results, recommendation) plus the client's profile."""
    def q():
        d, name = _db(db)
        r = d.runs.find_one({"run_id": run_id}, {"_id": 0})
        c = d.clients.find_one({"client_id": r["case_id"]}, {"_id": 0, "last_recommendation": 0}) if r else None
        return name, r, c

    name, r, c = _mongo_guard(q)
    if not r:
        raise HTTPException(404, f"No run {run_id} in {name}")
    return {**r, "client": c, "db": name}


@app.get("/api/live/versions/{v}")
def live_version(v: int, db: str | None = None):
    """Playbook YAML, diff vs parent, and generation metrics + compliance verdict, from the live db."""
    def q():
        d, name = _db(db)
        p = d.playbooks.find_one({"version": v}, {"_id": 0})
        par = d.playbooks.find_one({"version": p["parent"]}, {"_id": 0}) if p and p.get("parent") is not None else None
        gens = list(d.generations.find({"version": v}, {"_id": 0}).sort("created_at", 1))
        return name, p, par, gens

    name, p, par, gens = _mongo_guard(q)
    if not p:
        raise HTTPException(404, f"No playbook v{v} in {name}")
    diff = list(difflib.unified_diff((par or {}).get("yaml", "").splitlines(), p.get("yaml", "").splitlines(),
                                     fromfile=f"v{p.get('parent')}", tofile=f"v{v}", lineterm="", n=2))
    return {**p, "diff": diff, "generations": gens, "db": name}


# ---------------------------------------------------------------- lineage (the genome view)
def _elements(text: str) -> list[dict]:
    """Playbook YAML -> ordered base pairs: prompt, each skill, max_turns."""
    try:
        d = yaml.safe_load(text or "") or {}
    except yaml.YAMLError:
        return [{"key": "prompt", "kind": "prompt", "name": "prompt", "desc": "unparseable YAML", "body": text or ""}]
    out = [{"key": "prompt", "kind": "prompt", "name": "prompt", "desc": "Instructions every case starts from",
            "body": str(d.get("prompt") or "").strip()}]
    for s in d.get("skills") or []:
        out.append({"key": f"skill:{s.get('name')}", "kind": "skill", "name": str(s.get("name")),
                    "desc": str(s.get("description") or ""), "body": str(s.get("body") or "").strip()})
    out.append({"key": "max_turns", "kind": "limit", "name": f"max_turns {d.get('max_turns')}",
                "desc": "Turn budget per case", "body": str(d.get("max_turns"))})
    return out


def _mutations(parent: list[dict] | None, child: list[dict]) -> dict:
    if parent is None:
        return {"added": [], "removed": [], "edited": []}
    p, c = {e["key"]: e for e in parent}, {e["key"]: e for e in child}
    return {
        "added": [c[k] for k in c if k not in p],
        "removed": [p[k] for k in p if k not in c],
        "edited": [{**c[k], "before": p[k]["body"], "before_name": p[k]["name"]}
                   for k in c if k in p and (c[k]["body"] != p[k]["body"] or c[k]["desc"] != p[k]["desc"])],
    }


def _latest(runs: list[dict], version, set_name: str) -> dict:
    """Latest run per case for one version and set."""
    out = {}
    for r in runs:
        if r.get("playbook_version") == version and r.get("set") == set_name:
            if r["case_id"] not in out or str(r.get("created_at")) > str(out[r["case_id"]].get("created_at")):
                out[r["case_id"]] = r
    return out


def _rule_counts(rs: dict) -> dict:
    n = {}
    for r in rs.values():
        for x in r.get("violations") or []:
            n[x["rule"]] = n.get(x["rule"], 0) + 1
    return n


@app.get("/api/lineage")
def lineage(db: str | None = None, demo: int = 0):
    """Every playbook version as a genome: its base pairs, the mutations from its parent, why Muse made them
    (the parent's practice failures), and what it learned (rule-level change on unseen test clients)."""
    if db:
        def q():
            d, _ = _db(db)
            return {"playbooks": list(d.playbooks.find({}, {"_id": 0})),
                    "generations": list(d.generations.find({}, {"_id": 0})),
                    "runs": list(d.runs.find({}, {"_id": 0, "steps": 0, "recommendation": 0}))}
        data = _mongo_guard(q)
    else:
        data, _ = _load(bool(demo))
    pbs = {p["version"]: p for p in data["playbooks"]}
    gens = {}
    for g in sorted(data["generations"], key=lambda g: str(g.get("created_at"))):
        gens[g["version"]] = g
    runs = data["runs"]
    out = []
    for v in sorted(pbs):
        p = pbs[v]
        els = _elements(p.get("yaml", ""))
        par = pbs.get(p.get("parent"))
        par_els = _elements(par["yaml"]) if par else None
        # why: what the parent got wrong on the practice set (the only set Muse sees)
        why_set = "practice"
        par_prac = _latest(runs, p.get("parent"), "practice") if par else {}
        if par and not par_prac:
            why_set, par_prac = "test", _latest(runs, p.get("parent"), "test")
        why = sorted(({"rule": k, "count": n, "total": len(par_prac)} for k, n in _rule_counts(par_prac).items()),
                     key=lambda x: -x["count"])[:4]
        for w in why:
            ex = next((x for r in par_prac.values() for x in r.get("violations") or [] if x["rule"] == w["rule"]), None)
            w["example"] = ex["detail"] if ex else None
        # learned: rule-level change on unseen test clients, parent -> child
        before, after = (_latest(runs, p.get("parent"), "test") if par else {}), _latest(runs, v, "test")
        cb, ca = _rule_counts(before), _rule_counts(after)
        rules = sorted(({"rule": k, "before": cb.get(k, 0), "after": ca.get(k, 0)} for k in set(cb) | set(ca)),
                       key=lambda x: (x["after"] - x["before"], -x["before"]))
        example = None
        for rr in rules:
            if rr["before"] > rr["after"]:
                for cid, r0 in before.items():
                    v0 = next((x for x in r0.get("violations") or [] if x["rule"] == rr["rule"]), None)
                    r1 = after.get(cid)
                    if v0 and r1 and not any(x["rule"] == rr["rule"] for x in r1.get("violations") or []):
                        res = next((x for x in r1.get("results") or [] if x.get("rule") == rr["rule"]), None)
                        example = {"case_id": cid, "rule": rr["rule"], "before": v0["detail"],
                                   "after": (res or {}).get("detail") or "passes"}
                        break
            if example:
                break
        mean = lambda rs: round(sum(r.get("score") or 0 for r in rs.values()) / len(rs), 3) if rs else None
        g = gens.get(v)
        out.append({
            "version": v, "parent": p.get("parent"), "status": p.get("status"), "changelog": p.get("changelog", ""),
            "elements": els, "mutations": _mutations(par_els, els),
            "lessons_added": [l for l in _lessons(p.get("yaml", "")) if l["lesson"] not in {x["lesson"] for x in _lessons((par or {}).get("yaml", ""))}],
            "lessons": _lessons(p.get("yaml", "")),
            "why": why, "why_set": why_set,
            "learned": {"rules": rules, "score_before": mean(before), "score_after": mean(after),
                        "cases": len(after), "example": example},
            "gate": {k: g.get(k) for k in ("mode", "test", "regression", "practice", "decision", "reason", "compliance")} if g else None,
        })
    return out


@app.get("/live")
def live_page():
    return FileResponse(HERE / "static" / "live.html")


# ---------------------------------------------------------------- run it: jobs for runtime/worker.py
CASES = json.loads((HERE / "cases.json").read_text()) if (HERE / "cases.json").exists() else []
CASE_IDS = {c["case"] for c in CASES}
RUN_MODELS = {"meta/muse-spark-1.3": "Muse Spark 1.3", "subq/subq-preview": "SubQ Preview", "google/gemini-3.8-flash": "Gemini 3.8 Flash"}
_rate: dict[str, list[float]] = {}
RATE_N, RATE_WINDOW = 10, 600


@app.get("/api/cases")
def cases():
    return CASES


@app.get("/api/playbook_versions")
def playbook_versions(journey: str | None = None, db: str | None = None):
    def q():
        d, _ = _db(db)
        coll = d.journey_playbooks if journey else d.playbooks
        f = {"journey": journey} if journey else {}
        return [{"version": p["version"], "status": p.get("status"), "changelog": p.get("changelog", "")}
                for p in coll.find(f, {"_id": 0, "version": 1, "status": 1, "changelog": 1}).sort("version", 1)]
    return _mongo_guard(q)


@app.post("/api/run")
async def run_job(request: Request):
    import uuid

    body = await request.json()
    secret = os.environ.get("RUN_PASSCODE")
    if not secret:
        raise HTTPException(503, "Live runs are off: RUN_PASSCODE isn't set on the server")
    if str(body.get("passcode", "")) != secret:
        raise HTTPException(403, "Wrong passcode")
    case = str(body.get("case", ""))
    if case not in CASE_IDS:
        raise HTTPException(400, f"Unknown case {case!r}")
    models = [m for m in (body.get("models") or []) if m in RUN_MODELS]
    if not models:
        raise HTTPException(400, "Pick at least one model")
    pv = body.get("playbook_version")
    pv = None if pv in (None, "", "v0") else int(pv)
    journey = case.split("/")[1] if case.startswith("journeys/") and pv is not None else None
    ip = (request.headers.get("fly-client-ip") or request.client.host or "?")
    now_t = time.time()
    hits = [t for t in _rate.get(ip, []) if now_t - t < RATE_WINDOW]
    if len(hits) + len(models) > RATE_N:
        raise HTTPException(429, f"Limit is {RATE_N} runs per 10 minutes. Try again in {int(RATE_WINDOW - (now_t - min(hits)))} s")
    _rate[ip] = hits + [now_t] * len(models)

    def q():
        d, name = _db(None)
        ids = []
        for m in models:
            jid = f"job-{uuid.uuid4().hex[:8]}"
            d.jobs.insert_one({"job_id": jid, "status": "queued", "case": case, "model": m, "playbook_version": pv,
                               "journey": journey, "source": "web", "created_at": datetime.now(timezone.utc).isoformat()})
            ids.append(jid)
        return {"db": name, "job_ids": ids}
    return _mongo_guard(q)


@app.get("/api/jobs")
def jobs(limit: int = 20):
    def q():
        d, _ = _db(None)
        out = []
        for j in d.jobs.find({}, {"_id": 0, "steps": 0, "result.recommendation": 0, "result.check.results": 0}).sort("created_at", -1).limit(min(limit, 50)):
            r = j.pop("result", None) or {}
            chk = r.get("check") or {}
            out.append({**j, "score": chk.get("score"), "passed": chk.get("passed"), "seconds": r.get("seconds"), "turns": r.get("turns"),
                        "error": r.get("error") or j.get("error")})
        return out
    return _mongo_guard(q)


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    def q():
        d, _ = _db(None)
        return d.jobs.find_one({"job_id": job_id}, {"_id": 0})
    j = _mongo_guard(q)
    if not j:
        raise HTTPException(404, f"No job {job_id}")
    return j


@app.get("/architecture")
def architecture_page():
    return FileResponse(HERE / "static" / "arch.html")


@app.get("/api/analysis")
def analysis(demo: int = 0):
    """SubQ long-context drift analyses (newest last)."""
    d, _ = _load(bool(demo))
    return sorted(d.get("drift_analysis", []), key=_t)


# ---------------------------------------------------------------- lessons: what the agent has learned
def _lessons(text: str) -> list[dict]:
    try:
        d = yaml.safe_load(text or "") or {}
    except yaml.YAMLError:
        return []
    out = []
    for l in d.get("lessons") or []:
        if isinstance(l, dict) and l.get("lesson"):
            out.append({k: str(l.get(k) or "") for k in ("lesson", "root_cause", "triggered_by", "rule", "skill")})
    return out


def _data(db: str | None, demo: int):
    if db:
        def q():
            d, _ = _db(db)
            return {c: list(d[c].find({}, {"_id": 0, "steps": 0, "recommendation": 0} if c == "runs" else {"_id": 0}))
                    for c in ("playbooks", "generations", "runs", "drift_events", "journeys")}
        return _mongo_guard(q)
    d, _ = _load(bool(demo))
    return d


def _journey_rows(data: dict) -> list[dict]:
    """Journey meta (collection `journeys`, else seed) joined with runs where set == "journey" and case_id "j-001/t04"."""
    live_runs = [r for r in data.get("runs", []) if r.get("set") == "journey"]
    demo = not (data.get("journeys") and live_runs)
    metas = SEED.get("journeys", []) if demo else data["journeys"]
    runs = [r for r in SEED["runs"] if r.get("set") == "journey"] if demo else live_runs
    out = []
    for m in metas:
        m = {**m, "source": "demo" if demo else "live"}
        jid = m["journey_id"]
        cps = []
        for cp in m.get("checkpoints", []):
            mine = [r for r in runs if r.get("case_id") == f"{jid}/{cp['id']}"]
            def pick(track):
                rs = [r for r in mine if r.get("track") == track] or (
                    [r for r in mine if r.get("playbook_version") == 0] if track == "baseline" else
                    sorted(mine, key=lambda r: r.get("playbook_version") or 0)[-1:])
                if not rs:
                    return None
                r = sorted(rs, key=lambda r: str(r.get("created_at")))[-1]
                v = (r.get("violations") or [])
                return {"version": r.get("playbook_version"), "passed": r.get("passed"), "score": r.get("score"),
                        "violation": f"{v[0]['rule']}: {v[0]['detail']}" if v else None, "run_id": r.get("run_id")}
            cps.append({**cp, "baseline": pick("baseline"), "personal": pick("personal")})
        out.append({**m, "checkpoints": cps})
    return out


def _real_journeys(name: str) -> list[dict]:
    """Journeys in the runtime's actual schema: journeys (meta.json), journey_steps, journey_playbooks,
    journey_summaries, and runs with set "journey" + phase. Empty list if there is nothing real yet."""
    d, _ = _db(name)
    metas = list(d.journeys.find({}, {"_id": 0}).sort("journey_id", 1))
    steps = list(d.journey_steps.find({}, {"_id": 0}).sort("created_at", 1))
    if not metas or not steps:
        return []
    pbs = list(d.journey_playbooks.find({}, {"_id": 0, "yaml": 0}))
    sums = {s["journey"]: s for s in d.journey_summaries.find({}, {"_id": 0})}
    runs = list(d.runs.find({"set": "journey"}, {"_id": 0, "steps": 0, "recommendation": 0, "results": 0}).sort("created_at", 1))
    out = []
    for m in metas:
        jid = m["journey_id"]
        jsteps = [s for s in steps if s.get("journey") == jid]
        jruns = [r for r in runs if r.get("journey") == jid or str(r.get("case_id", "")).startswith(jid + "/")]
        jpbs = sorted([p for p in pbs if p.get("journey") == jid], key=lambda p: p.get("version") or 0)
        shipped = [p for p in jpbs if p.get("status") == "shipped"]
        # lessons: the latest shipped playbook's accumulated list; learned_at = the first version that contains it
        lessons = []
        for l in (shipped[-1].get("lessons") if shipped else None) or []:
            first = next((p for p in jpbs if any(x.get("lesson") == l.get("lesson") for x in p.get("lessons") or [])), None)
            lessons.append({**{k: l.get(k) for k in ("lesson", "root_cause", "triggered_by", "rule", "skill")},
                            "at": (first or {}).get("learned_at"), "version": (first or {}).get("version")})
        crash = "Equity crash" if "crash" in str(m.get("regime", "")).lower() else "Market drop"

        def res(r):
            if not r:
                return None
            v = r.get("violations") or []
            return {"version": r.get("playbook_version", r.get("version")), "passed": r.get("passed"), "score": r.get("score"),
                    "violation": f"{v[0]['rule']}: {v[0]['detail']}" if v else None, "run_id": r.get("run_id"), "backtest": r.get("backtest")}

        cps = []
        for cp in m.get("checkpoints", []):
            cid = cp["id"]
            here_runs = [r for r in jruns if r.get("checkpoint") == cid or r.get("case_id") == f"{jid}/{cid}"]
            here_steps = [s for s in jsteps if s.get("checkpoint") == cid]
            by_phase = lambda ph: [r for r in here_runs if r.get("phase") == ph]
            if cp.get("split") == "holdout":
                base = (by_phase("holdout_start") or [None])[-1]
                pers = (by_phase("holdout_final") or [None])[-1]
                prove = next((s for s in reversed(here_steps) if s.get("action") == "prove"), None)
                if prove and not pers:
                    pers = prove
                if prove and not base and prove.get("start_score") is not None:
                    base = {"playbook_version": 0, "passed": prove.get("start_passed"), "score": prove.get("start_score"), "violations": []}
            else:
                train = by_phase("train")
                base = next((r for r in train if (r.get("playbook_version") or 0) == 0), None)
                ev = next((s for s in here_steps if s.get("action") == "evaluate"), None)
                pers = (train[-1] if train else None) or ev
            cps.append({"id": cid, "date": cp.get("as_of"), "split": cp.get("split"), "events": cp.get("events") or [],
                        "regime": crash if "market_drop" in (cp.get("events") or []) else None,
                        "baseline": res(base), "personal": res(pers),
                        "actions": [{"action": s.get("action"), "version": s.get("version"), "reason": s.get("reason"),
                                     "lessons": [x.get("lesson") for x in s.get("lessons") or []]} for s in here_steps
                                    if s.get("action") in ("learn", "reject")]})
        done = [c for c in cps if c["personal"]]
        p = m.get("persona") or {}
        out.append({"journey_id": jid, "source": "live", "db": name,
                    "persona": {"name": p.get("name", jid), "age": p.get("age", p.get("age_at_start")), "occupation": p.get("occupation", ""),
                                "risk_score": p.get("risk_score"), "state": p.get("state")},
                    "arc": m.get("arc", ""), "regime_text": m.get("regime", ""),
                    "regimes": [{"name": crash, "kind": "crash"}] if any(c["regime"] for c in cps) else [],
                    "checkpoints": cps, "lessons": lessons, "summary": sums.get(jid),
                    "progress": {"done": len(done), "total": len(cps), "at": done[-1]["id"] if done else None,
                                 "versions": len(shipped), "rejected": sum(1 for p in jpbs if p.get("status") == "rejected")}})
    return out


@app.get("/api/scoreboard")
def scoreboard(db: str | None = None):
    """The real training run's generations (practice / test / regression per version) for the hero instrument panel."""
    def q():
        # same database as the replay story, so the hero and the replay never disagree
        d, name = _db(db or _load()[0].get("_db") or os.environ.get("LIVE_DB", "ballast_muse"))
        gens = list(d.generations.find({}, {"_id": 0}).sort("created_at", 1))
        model = (d.runs.find_one({"set": "test"}, {"_id": 0, "model": 1}, sort=[("created_at", -1)]) or {}).get("model")
        return name, gens, model
    try:
        name, gens, model = _mongo_guard(q)
    except HTTPException:
        return {"db": None, "model": None, "versions": []}

    def cell(m, set_name):
        if not m:
            return None
        n = m.get("n") or SET_SIZES.get(set_name, 20)
        return {"mean": m.get("mean_score"), "pass_rate": m.get("pass_rate"), "passed": round((m.get("pass_rate") or 0) * n), "n": n}
    return {"db": name, "model": model, "versions": [
        {"version": g.get("version"), "decision": g.get("decision"), "reason": g.get("reason"), "mode": g.get("mode"),
         "practice": cell(g.get("practice"), "practice"), "test": cell(g.get("test"), "test"),
         "regression": cell(g.get("regression"), "regression"), "created_at": g.get("created_at")} for g in gens]}


@app.get("/api/journeys")
def journeys(db: str | None = None, demo: int = 0):
    """Real journeys from the runtime (LIVE_DB, or ?db=) when they exist; otherwise the seed's demo journeys."""
    if not demo:
        try:
            real = _real_journeys(db or os.environ.get("LIVE_DB", "ballast_muse"))
            if real:
                return real
        except HTTPException:
            if db:
                raise
        except Exception:
            pass
    rows = _journey_rows(_data(None, demo))
    return [{**r, "source": "demo"} for r in rows]


@app.get("/api/lessons")
def lessons(db: str | None = None, demo: int = 0):
    """The lesson ledger: every lesson in the shipped lineage, where it was learned and where it was proven."""
    data = _data(db, demo)
    pbs = {p["version"]: p for p in data["playbooks"]}
    gens = {g["version"]: g for g in sorted(data["generations"], key=lambda g: str(g.get("created_at")))}
    runs = data["runs"]
    shipped = [v for v in sorted(pbs) if pbs[v].get("status") in ("shipped", "rolled_back")]
    current = max((v for v in shipped if pbs[v].get("status") == "shipped"), default=None)
    journeys_ = _journey_rows(data)

    def fail_count(v, rule, set_name="test"):
        rs = _latest(runs, v, set_name)
        return sum(1 for r in rs.values() if any(x["rule"] == rule for x in r.get("violations") or [])), len(rs)

    ledger, seen = [], set()
    for v in shipped:
        for l in _lessons(pbs[v].get("yaml", "")):
            if l["lesson"] in seen:
                continue
            seen.add(l["lesson"])
            parent = pbs[v].get("parent")
            ex = None
            if parent is not None:
                for r in _latest(runs, parent, "practice").values():
                    ex = next((x["detail"] for x in r.get("violations") or [] if x["rule"] == l["rule"]), None)
                    if ex:
                        break
            before = fail_count(parent, l["rule"]) if parent is not None else (0, 0)
            after = fail_count(v, l["rule"])
            now = fail_count(current, l["rule"]) if current is not None else after
            # journey checkpoints (holdout) where this rule passes for the personal agent but fails for the generic one
            jproof = [f"{j['journey_id']}/{c['id']}" for j in journeys_ for c in j["checkpoints"]
                      if c.get("split") == "holdout" and c.get("personal") and c["personal"].get("passed")
                      and c.get("baseline") and (c["baseline"].get("violation") or "").startswith(l["rule"])]
            g = gens.get(v) or {}
            ledger.append({**l, "version": v, "status": pbs[v].get("status"), "date": g.get("created_at") or pbs[v].get("created_at"),
                           "gate_reason": g.get("reason"), "mode": g.get("mode"),
                           "example": ex, "proven": {"before": before[0], "after": after[0], "now": now[0], "cases": after[1] or before[1],
                                                     "current_version": current, "journeys": jproof}})
    rejected = []
    for v in sorted(pbs):
        if pbs[v].get("status") == "rejected":
            for l in _lessons(pbs[v].get("yaml", "")):
                if l["lesson"] not in seen:
                    g = gens.get(v) or {}
                    rejected.append({**l, "version": v, "reason": g.get("reason"), "compliance": g.get("compliance")})
    # per-client lessons from the journey runtime (journey_playbooks), when this db has them
    jl = []
    try:
        for j in _real_journeys(db or os.environ.get("LIVE_DB", "ballast_muse")):
            if j["lessons"]:
                jl.append({"journey": j["journey_id"], "client": j["persona"]["name"], "lessons": j["lessons"]})
    except Exception:
        pass
    return {"lessons": ledger, "rejected": rejected, "current_version": current, "journey_lessons": jl,
            "playbook_yaml": pbs[current]["yaml"] if current is not None else None}


@app.get("/api/benchmark")
def benchmark(demo: int = 0):
    """Head to head: the Muse stack vs the SubQ stack, same tests from the same generic v0, read live from the two
    benchmark databases (interim until the final summary lands). Gemini is only the compliance reviewer, not a contender."""
    if not demo and os.environ.get("MONGODB_URI"):
        real = []
        try:
            for name, key, label, provider in (("ballast_bench_muse", "muse", "Muse Spark 1.3", "Meta Model API, Muse stack"),
                                               ("ballast_bench_subq", "subq", "SubQ Preview", "Subquadratic, SubQ stack")):
                d, _ = _db(name)
                rs = list(d.runs.find({}, {"_id": 0, "tokens_in": 1, "tokens_out": 1, "seconds": 1, "score": 1, "passed": 1, "created_at": 1, "set": 1}))
                if not rs:
                    continue
                n = len(rs)
                stamps = sorted(r["created_at"] for r in rs if r.get("created_at"))
                span = (datetime.fromisoformat(stamps[-1]) - datetime.fromisoformat(stamps[0])).total_seconds() / 60 if len(stamps) > 1 else 0
                g = d.generations.find_one({"version": 0}, {"_id": 0, "test": 1})
                sums = list(d.journey_summaries.find({}, {"_id": 0}))
                avg = lambda k: round(sum(float(s.get(k) or 0) for s in sums) / len(sums), 3) if sums else None
                scored = [r for r in rs if r.get("score") is not None]
                real.append({"model": key, "label": label, "provider": provider, "real": True, "db": name, "runs": n,
                             "_test": (g or {}).get("test") if g else None,
                             "mean_score": round(sum(r["score"] for r in scored) / max(1, len(scored)), 3),
                             "score_basis": "all runs so far",
                             "pass_rate": round(sum(1 for r in scored if r.get("passed")) / max(1, len(scored)), 3),
                             "tokens": round(sum((r.get("tokens_in") or 0) + (r.get("tokens_out") or 0) for r in rs) / n),
                             "seconds": round(sum(r.get("seconds") or 0 for r in rs) / n, 1),
                             "runs_per_min": round(n / span, 1) if span else None,
                             "journeys": len(sums), "holdout_start": avg("holdout_mean_start"), "holdout_final": avg("holdout_mean_final")})
        except Exception:
            real = []
        # compare on one basis: v0 test only when every stack has it, otherwise all runs so far for both
        if real and all(r.get("_test") for r in real):
            for r in real:
                r.update(mean_score=r["_test"]["mean_score"], pass_rate=r["_test"]["pass_rate"], score_basis="v0 test")
        for r in real:
            r.pop("_test", None)
        if real:
            return real
    if not demo:
        return []  # real only: nothing to compare yet
    d, _ = _load(bool(demo))
    rows = d.get("benchmarks") or []
    if not rows:
        by = {}
        for r in d["runs"]:
            if r.get("model") and r["set"] == "test":
                by.setdefault(r["model"], []).append(r)
        rows = [{"model": m, "label": m, "provider": "", "mean_score": round(sum(x["score"] for x in rs) / len(rs), 3),
                 "pass_rate": round(sum(1 for x in rs if x["passed"]) / len(rs), 3),
                 "tokens": round(sum(x.get("tokens_in", 0) + x.get("tokens_out", 0) for x in rs) / len(rs)),
                 "seconds": round(sum(x.get("seconds", 0) for x in rs) / len(rs), 1)} for m, rs in by.items()]
    return rows


app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(HERE / "static" / "index.html")
