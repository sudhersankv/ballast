"""Insert a life event into MongoDB (the demo trigger for runtime/watch.py).

  python runtime/inject_event.py c-021 layoff --details '{"severance": 18000}'
  python runtime/inject_event.py c-033 inheritance --details '{"amount": 250000, "asset": "KSTL"}'
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from store import Store  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("client_id")
ap.add_argument("type", choices=["layoff", "job_change", "marriage", "child", "inheritance", "divorce", "market_drop"])
ap.add_argument("--date", default=date.today().isoformat())
ap.add_argument("--details", default="{}")
a = ap.parse_args()
doc = Store().insert("life_events", {"client_id": a.client_id, "type": a.type, "date": a.date,
                                     "details": json.loads(a.details)})
print("inserted", doc)
