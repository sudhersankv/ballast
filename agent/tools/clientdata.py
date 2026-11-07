"""Read-only connectors to a client's day-to-day data (consented, logged).

Usage (from the case directory):
  python tools/clientdata.py sources            # which connectors this client has granted
  python tools/clientdata.py bank [--days 90]   # account transactions
  python tools/clientdata.py payroll            # pay stubs and HR status
  python tools/clientdata.py employer           # employer portal: trading windows, notices
  python tools/clientdata.py calendar           # upcoming known expenses and dates
  python tools/clientdata.py messages           # notes the client sent their advisor
  python tools/clientdata.py credit             # credit report balances
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent / "connectors"


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    src = argv[0]
    granted = sorted(p.stem for p in DIR.glob("*.json")) if DIR.exists() else []
    if src == "sources":
        print(json.dumps({"granted": granted, "access": "read-only"}, indent=1))
        return 0
    if src not in granted:
        print(json.dumps({"error": f"no access to '{src}'", "granted": granted}))
        return 1
    data = json.loads((DIR / f"{src}.json").read_text(encoding="utf-8"))
    if src == "bank" and "--days" in argv:
        days = int(argv[argv.index("--days") + 1])
        cutoff = (date.fromisoformat(data["as_of"]) - timedelta(days=days)).isoformat()
        data["transactions"] = [t for t in data["transactions"] if t["date"] >= cutoff]
    print(json.dumps(data, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
