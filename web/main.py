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
