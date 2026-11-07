"""Bundle scenarios/cases/connected/* into web/connected.json for the "Connected data" view.

  python web/make_connected.py D:/AIECodeSummit/scenarios

Each case: client/holdings/market + connectors/*.json (whatever shape) + events.json (the hidden truth).
"""
import json
import sys
from pathlib import Path


def load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main(root: str) -> None:
    base = Path(root) / "cases" / "connected"
    out = []
    for d in sorted(base.glob("*")):
        if not (d / "client.json").exists():
            continue
        conn = {p.stem: load(p) for p in sorted((d / "connectors").glob("*.json"))} if (d / "connectors").exists() else {}
        out.append({"id": d.name, "case": f"connected/{d.name}", "client": load(d / "client.json"),
                    "holdings": load(d / "holdings.json"), "connectors": conn,
                    "truth": (load(d / "events.json") or {}).get("events", [])})
    dst = Path(__file__).with_name("connected.json")
    dst.write_text(json.dumps(out, indent=0))
    print(f"wrote {dst} ({len(out)} connected clients)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "../scenarios")
