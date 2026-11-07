"""Ballast web: FastAPI JSON API + static single-page app.

Reads MongoDB (MONGODB_URI, MONGODB_DB). Falls back to seed.json when Mongo is
unreachable or the runtime hasn't written playbooks/generations yet.
"""
import difflib
import json
import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).parent
SEED = json.loads((HERE / "seed.json").read_text())
COLLS = ["playbooks", "generations", "drift_events", "clients", "runs"]
OPTIONAL = ["drift_analysis", "benchmarks"]

app = FastAPI(title="ballast.")
_cache = {"t": 0.0, "data": None, "source": "demo"}


def _load(force_demo: bool = False):
    """Return (data, source). Cached for 5 s so the UI can poll cheaply."""
    if force_demo:
        return SEED, "demo"
    if _cache["data"] is not None and time.time() - _cache["t"] < 5:
        return _cache["data"], _cache["source"]
    data, source = SEED, "demo"
    uri = os.environ.get("MONGODB_URI")
    if uri:
        try:
            if "client" not in _cache:
                from pymongo import MongoClient

                _cache["client"] = MongoClient(uri, serverSelectionTimeoutMS=3000)
            db = _cache["client"][os.environ.get("MONGODB_DB", "ballast")]
            live = {c: list(db[c].find({}, {"_id": 0})) for c in COLLS + OPTIONAL}
            if live["playbooks"] and live["generations"]:
                # Optional collections fall back to seed individually so their panels never go blank.
                for c in OPTIONAL:
                    if not live[c]:
                        live[c] = SEED.get(c, [])
                data, source = live, "live"
        except Exception:
            pass
    _cache.update(t=time.time(), data=data, source=source)
    return data, source


def _shipped_current(gens, drift):
    """Current shipped version: last shipped generation, adjusted by the latest rollback/fix."""
    shipped = [g["version"] for g in sorted(gens, key=lambda g: g["created_at"]) if g["decision"] == "shipped"]
    cur = shipped[-1] if shipped else None
    for d in sorted(drift, key=lambda d: d["time"]):
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
    drift = sorted(d["drift_events"], key=lambda e: e["time"])
    cur = _shipped_current(gens, drift)
    by_v = {g["version"]: g for g in gens}
    base = by_v.get(0, gens[0] if gens else None)
    latest = by_v.get(cur)
    light = drift[-1]["level"] if drift else "green"
    return {
        "source": source,
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
            "drift_events": sum(1 for e in drift if e["level"] != "green"),
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
                    "violations_by_rule": by_rule})
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
    return sorted(d["drift_events"], key=lambda e: e["time"])


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
LIVE_DBS = {"ballast_dev", "ballast"}
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
        if not sess:
            return {"db": name, "session": None, "started_at": None, "log": [], "runs": [], "progress": None,
                    "blocks": [], "versions": []}
        first = d.loop_log.find_one({"session": sess}, {"_id": 0, "created_at": 1}, sort=[("created_at", 1)])
        start = first["created_at"] if first else ""
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
        return {"db": name, "session": sess, "started_at": start, "log": log, "runs": runs,
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
        r = next((x for x in SEED["runs"] if x["run_id"] == run_id), None)
        if not r:
            raise HTTPException(404, f"No run {run_id} in {name}")
        c = next((x for x in SEED["clients"] if x["client_id"] == r["case_id"]), None)
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


@app.get("/live")
def live_page():
    return FileResponse(HERE / "static" / "live.html")


@app.get("/api/analysis")
def analysis(demo: int = 0):
    """SubQ long-context drift analyses (newest last)."""
    d, _ = _load(bool(demo))
    return sorted(d.get("drift_analysis", []), key=lambda a: a["time"])


@app.get("/api/benchmark")
def benchmark(demo: int = 0):
    """Same playbook, same unseen clients, different agent models. Runtime tags each run with `model`."""
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
