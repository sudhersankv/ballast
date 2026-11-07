"""Build web/cases.json: the case index (with a short preview) for the "Run it" panel.

The web image only ships web/, so this reads the repo's scenarios/ folder at build time:
  python web/make_cases.py D:/AIECodeSummit/scenarios
Case ids match runtime/worker.py: "<set>/<id>", "fixtures/<id>", "journeys/<j>/<t>".
"""
import json
import sys
from pathlib import Path


def preview(d: Path) -> dict:
    def load(n):
        try:
            return json.loads((d / n).read_text(encoding="utf-8"))
        except Exception:
            return {}
    c, h, e = load("client.json"), load("holdings.json"), load("events.json")
    pos = h.get("positions") or []
    cash = sum(p.get("value", 0) for p in pos if p.get("symbol") == "CASH")
    total = sum(p.get("value", 0) for p in pos)
    exp = c.get("monthly_expenses") or 0
    return {"age": c.get("age"), "risk": c.get("risk_score"), "name": c.get("name"),
            "events": [x.get("type") for x in e.get("events") or []],
            "cash_months": round(cash / exp, 1) if exp else None, "value": round(total), "as_of": h.get("as_of")}


def main(root: str) -> None:
    root = Path(root)
    out = []
    for d in sorted((root / "fixtures").glob("*")):
        if (d / "client.json").exists():
            out.append({"case": f"fixtures/{d.name}", "group": "fixtures", **preview(d)})
    for d in sorted((root / "cases" / "connected").glob("*")):
        if (d / "client.json").exists():
            # connected clients: life events are hidden from the agent, so the preview hides them too
            out.append({"case": f"connected/{d.name}", "group": "connected", **preview(d), "events": [], "connected": True})
    for s in ("test", "practice", "regression", "drift"):
        for d in sorted((root / "cases" / s).glob("*")):
            if (d / "client.json").exists():
                out.append({"case": f"{s}/{d.name}", "group": s, **preview(d)})
    for j in sorted((root / "journeys").glob("j-*")):
        for t in sorted(j.glob("t*")):
            if (t / "client.json").exists():
                out.append({"case": f"journeys/{j.name}/{t.name}", "group": f"journeys/{j.name}", "journey": j.name, **preview(t)})
    dst = Path(__file__).with_name("cases.json")
    dst.write_text(json.dumps(out, indent=0))
    print(f"wrote {dst} ({len(out)} cases)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "../scenarios")
