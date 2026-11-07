"""Portfolio helper CLI for the Ballast agent, and the shared post-trade math.

Stdlib only: this file is copied into every case directory as tools/portfolio.py.
The checker imports the same functions, so the agent and the checker agree on numbers.

Usage (from the case directory):
  python tools/portfolio.py allocation holdings.json
  python tools/portfolio.py apply holdings.json recommendation.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

CLASSES = ("equity", "bond", "cash")


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def positions(holdings: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    for p in holdings.get("positions", []):
        out[p["symbol"]] = out.get(p["symbol"], 0.0) + float(p["value"])
    return out


def post_trade(holdings: dict, trades: list[dict]) -> dict[str, float]:
    """Value per symbol after applying trades (buys add, sells subtract)."""
    post = positions(holdings)
    for t in trades or []:
        amt = float(t.get("amount_usd", 0))
        sign = 1 if t.get("action") == "buy" else -1 if t.get("action") == "sell" else 0
        post[t["symbol"]] = post.get(t["symbol"], 0.0) + sign * amt
    return post


def net_flow(trades: list[dict]) -> float:
    """sum(buys) - sum(sells); 0 means trades net to zero."""
    return sum(float(t.get("amount_usd", 0)) * (1 if t.get("action") == "buy" else -1) for t in trades or [])


def weights(post: dict[str, float], market: dict) -> dict:
    total = sum(post.values())
    syms = market.get("symbols", {})
    by_class = {c: 0.0 for c in CLASSES}
    for s, v in post.items():
        by_class[syms.get(s, {}).get("class", "cash" if s == "CASH" else "equity")] += v
    w_class = {c: (v / total if total else 0.0) for c, v in by_class.items()}
    w_sym = {s: (v / total if total else 0.0) for s, v in post.items()}
    single = {s: w for s, w in w_sym.items() if syms.get(s, {}).get("single_stock")}
    return {"total": total, "by_class": w_class, "by_symbol": w_sym, "single_stocks": single}


def cash_months(post: dict[str, float], client: dict) -> float | None:
    exp = float(client.get("monthly_expenses") or 0)
    return post.get("CASH", 0.0) / exp if exp else None


def summary(post: dict[str, float], market: dict, client: dict | None) -> dict:
    w = weights(post, market)
    out = {
        "total_usd": round(w["total"], 2),
        "weights_by_class": {k: round(v, 4) for k, v in w["by_class"].items()},
        "weights_by_symbol": {k: round(v, 4) for k, v in sorted(w["by_symbol"].items())},
        "single_stock_weights": {k: round(v, 4) for k, v in w["single_stocks"].items()},
        "values_usd": {k: round(v, 2) for k, v in sorted(post.items())},
    }
    if client:
        cm = cash_months(post, client)
        out["cash_months_of_expenses"] = None if cm is None else round(cm, 2)
        if client.get("targets"):
            out["drift_vs_targets_pts"] = {
                c: round(100 * (w["by_class"][c] - float(client["targets"].get(c, 0))), 1) for c in CLASSES
            }
    return out


def _case_files(holdings_path: str) -> tuple[dict, dict, dict | None]:
    d = Path(holdings_path).resolve().parent
    market = load(d / "market.json") if (d / "market.json").exists() else {"symbols": {}}
    client = load(d / "client.json") if (d / "client.json").exists() else None
    return load(holdings_path), market, client


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in ("allocation", "apply"):
        print(__doc__)
        return 2
    holdings, market, client = _case_files(argv[1])
    if argv[0] == "allocation":
        print(json.dumps(summary(positions(holdings), market, client), indent=2))
        return 0
    if len(argv) < 3:
        print("apply needs: holdings.json recommendation.json")
        return 2
    rec = load(argv[2])
    trades = rec.get("trades", [])
    post = post_trade(holdings, trades)
    out = summary(post, market, client)
    problems = []
    nf = net_flow(trades)
    if abs(nf) > 1:
        problems.append(f"trades do not net to zero: buys - sells = {nf:+.2f} USD")
    for s, v in post.items():
        if v < -1:
            problems.append(f"{s} sold more than held: post-trade value {v:.2f} USD")
    for t in trades:
        if t.get("symbol") not in market.get("symbols", {}):
            problems.append(f"unknown symbol {t.get('symbol')!r}")
    out["problems"] = problems
    print(json.dumps(out, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
