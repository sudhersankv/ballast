"""Ballast storage: MongoDB when reachable, local JSONL fallback otherwise.

Collections (the web UI reads these exact shapes):
  playbooks     {version, parent, yaml, changelog, status, created_at}
                status: shipped | rejected | rolled_back | candidate
  generations   {version, parent, mode, practice, test, regression, decision, reason,
                 compliance, created_at}   practice/test/regression = {mean_score, pass_rate}
  runs          {run_id, playbook_version, case_id, set, score, passed, violations,
                 recommendation, tokens_in, tokens_out, seconds, created_at}
  drift_events  {time, level, rolling_score, baseline, violations, action,
                 from_version, to_version, case_ids}
  clients       {client_id, name, age, risk_score, events, agent_version, last_recommendation}
  life_events   {client_id, type, date, details, created_at}  (inserts trigger drift checks)
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

COLLECTIONS = ("playbooks", "generations", "runs", "drift_events", "clients", "life_events",
               "drift_analysis", "benchmarks", "loop_log")
FALLBACK_DIR = ROOT / "runs" / "store"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, uri: str | None = None, db: str | None = None):
        self.uri = uri if uri is not None else os.environ.get("MONGODB_URI", "")
        self.db_name = db or os.environ.get("MONGODB_DB", "ballast")
        self.db = None
        if self.uri:
            try:
                from pymongo import MongoClient

                client = MongoClient(self.uri, serverSelectionTimeoutMS=8000)
                client.admin.command("ping")
                self.db = client[self.db_name]
            except Exception as e:  # unreachable -> fallback, never crash the loop
                print(f"[store] MongoDB unreachable, using local JSONL: {e.__class__.__name__}")
        if self.db is None:
            FALLBACK_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def backend(self) -> str:
        return "mongodb" if self.db is not None else "jsonl"

    # ---- generic -------------------------------------------------------
    def insert(self, coll: str, doc: dict) -> dict:
        assert coll in COLLECTIONS, coll
        doc = {**doc}
        doc.setdefault("created_at", now())
        if self.db is not None:
            self.db[coll].insert_one(doc)
            doc.pop("_id", None)
        else:
            with open(FALLBACK_DIR / f"{coll}.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(doc, default=str) + "\n")
        return doc

    def upsert(self, coll: str, key: dict, doc: dict) -> None:
        if self.db is not None:
            self.db[coll].update_one(key, {"$set": doc}, upsert=True)
            return
        rows = [r for r in self.find(coll) if any(r.get(k) != v for k, v in key.items())]
        rows.append({**key, **doc})
        with open(FALLBACK_DIR / f"{coll}.jsonl", "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, default=str) + "\n")

    def find(self, coll: str, query: dict | None = None, sort: str | None = None,
             desc: bool = False, limit: int = 0) -> list[dict]:
        query = query or {}
        if self.db is not None:
            cur = self.db[coll].find(query, {"_id": 0})
            if sort:
                cur = cur.sort(sort, -1 if desc else 1)
            if limit:
                cur = cur.limit(limit)
            return list(cur)
        path = FALLBACK_DIR / f"{coll}.jsonl"
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []
        rows = [r for r in rows if all(r.get(k) == v for k, v in query.items())]
        if sort:
            rows.sort(key=lambda r: (r.get(sort) is None, r.get(sort)), reverse=desc)
        return rows[:limit] if limit else rows

    # ---- domain helpers --------------------------------------------------
    def save_playbook(self, version: int, parent: int | None, yaml_text: str, changelog: str,
                      status: str = "candidate") -> None:
        self.upsert("playbooks", {"version": version},
                    {"parent": parent, "yaml": yaml_text, "changelog": changelog,
                     "status": status, "created_at": now()})

    def set_playbook_status(self, version: int, status: str) -> None:
        if self.db is not None:
            self.db.playbooks.update_one({"version": version}, {"$set": {"status": status}})
        else:
            pb = self.find("playbooks", {"version": version})
            if pb:
                self.upsert("playbooks", {"version": version}, {**pb[0], "status": status})

    def last_shipped(self) -> dict | None:
        rows = self.find("playbooks", {"status": "shipped"}, sort="version", desc=True, limit=1)
        return rows[0] if rows else None

    def log_run(self, playbook_version: int, set_name: str, run: dict, check: dict) -> dict:
        return self.insert("runs", {
            "run_id": f"r-{uuid.uuid4().hex[:8]}",
            "playbook_version": playbook_version,
            "case_id": check.get("case_id") or run.get("case_id"),
            "set": set_name,
            "model": run.get("model"),
            "score": check.get("score"),
            "passed": check.get("passed"),
            "violations": check.get("violations", []),
            "recommendation": run.get("recommendation"),
            "tokens_in": run.get("tokens_in"),
            "tokens_out": run.get("tokens_out"),
            "seconds": run.get("seconds"),
            "error": run.get("error"),
            "turns": run.get("turns"),
            "steps": run.get("steps", []),
            "results": check.get("results", []),
            "backtest": check.get("backtest"),
        })

    def log_generation(self, doc: dict) -> dict:
        return self.insert("generations", doc)

    def log_drift(self, doc: dict) -> dict:
        doc = {**doc}
        doc.setdefault("time", now())
        return self.insert("drift_events", doc)

    def watch_life_events(self) -> Iterator[dict]:
        """Yield each newly inserted life event (MongoDB change stream). Mongo only."""
        if self.db is None:
            raise RuntimeError("change streams need MongoDB")
        with self.db.life_events.watch([{"$match": {"operationType": "insert"}}]) as stream:
            for change in stream:
                doc = change["fullDocument"]
                doc.pop("_id", None)
                yield doc


if __name__ == "__main__":
    s = Store()
    print("backend:", s.backend)
    for c in COLLECTIONS:
        print(f"  {c}: {len(s.find(c))}")
