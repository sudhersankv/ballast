"""Forward backtest of a recommendation over the held-out window. An extra metric next to the policy
checker, never a replacement for it.

    python scenarios/backtest.py <case_dir> <recommendation.json> [--future path/to/future.json]

backtest(case_dir, recommendation) -> {
    "case_id", "months", "source",
    "forward_return"            time-weighted return over the window (withdrawals excluded),
    "max_drawdown"              worst peak-to-trough of that time-weighted index (<= 0),
    "end_value", "start_value",
    "min_cash_coverage_months"  worst month-end CASH / monthly_expenses,
    "forced_sale_usd"           risk assets sold because CASH ran out while funding expenses,
    "emergency_fund_breached"   unemployed: forced_sale_usd > 0; others: min coverage < employed_floor_months,
    "vs_hold_return"            forward_return minus the same client doing nothing (no trades),
}

The trades are applied with agent/tools/portfolio.py post_trade, the same math the checker uses. Unemployed
clients (employment_status == "unemployed") pay monthly_expenses from CASH for
config.backtest.unemployed_draw_months months. CASH earns the T-bill return. future.json lives in
scenarios/holdout/<set>/<id>/, which is never copied into the agent's working directory.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "agent" / "tools"))
sys.path.insert(0, str(ROOT))
import portfolio as pf  # noqa: E402
import market_model as mm  # noqa: E402


def holdout_path(case_dir: str | Path) -> Path:
    d = Path(case_dir).resolve()
    return ROOT / "holdout" / d.parent.name / d.name / "future.json"


def _valid_trades(rec: dict | None, market: dict) -> list[dict]:
    trades = (rec or {}).get("trades") if isinstance(rec, dict) else None
    if not isinstance(trades, list):
        return []
    ok = []
    for t in trades:
        if (isinstance(t, dict) and t.get("symbol") in market["symbols"] and t.get("action") in ("buy", "sell")
                and isinstance(t.get("amount_usd"), (int, float)) and t["amount_usd"] > 0):
            ok.append(t)
    return ok


def _simulate(post: dict[str, float], market: dict, future: dict, client: dict, cfg: dict) -> dict:
    bt = cfg["backtest"]
    prices_now = {s: market["symbols"][s]["price"] for s in post}
    units = {s: (v / prices_now[s] if prices_now[s] else 0.0) for s, v in post.items() if s != "CASH"}
    cash = post.get("CASH", 0.0)
    exp = float(client["monthly_expenses"])
    draw_months = int(bt["unemployed_draw_months"]) if client.get("employment_status") == "unemployed" else 0
    start = sum(post.values())
    v_prev, twr, peak, mdd = start, 1.0, 1.0, 0.0
    min_cov, forced = cash / exp, 0.0
    n = len(future["dates"])
    for i in range(n):
        if bt.get("cash_earns_rf", True):
            cash *= 1 + future["cash_return"][i]
        px = {s: future["prices"][s][i] for s in units}
        risk = {s: units[s] * px[s] for s in units}
        draw = exp if i < draw_months else 0.0
        if draw:
            cash -= draw
            if cash < 0:  # forced sale of risk assets, pro rata
                need, tot = -cash, sum(risk.values())
                forced += need
                cash = 0.0
                if tot > 0:
                    f = min(need / tot, 1.0)
                    for s in units:
                        units[s] *= 1 - f
                        risk[s] *= 1 - f
        v = cash + sum(risk.values())
        twr *= (v + draw) / v_prev if v_prev > 0 else 1.0
        peak = max(peak, twr)
        mdd = min(mdd, twr / peak - 1)
        min_cov = min(min_cov, cash / exp)
        v_prev = v
    breached = forced > 0 if draw_months else min_cov < bt["employed_floor_months"]
    return {"months": n, "start_value": round(start, 2), "end_value": round(v_prev, 2),
            "forward_return": round(twr - 1, 4), "max_drawdown": round(mdd, 4),
            "min_cash_coverage_months": round(min_cov, 2), "forced_sale_usd": round(forced, 2),
            "emergency_fund_breached": bool(breached)}


def backtest(case_dir: str | Path, recommendation: dict | None, future_path: str | Path | None = None,
             cfg: dict | None = None) -> dict:
    cfg = cfg or mm.load_config()
    d = Path(case_dir)
    load = lambda n: json.loads((d / f"{n}.json").read_text(encoding="utf-8"))  # noqa: E731
    client, holdings, market = load("client"), load("holdings"), load("market")
    fp = Path(future_path) if future_path else holdout_path(d)
    future = json.loads(fp.read_text(encoding="utf-8"))
    post = pf.post_trade(holdings, _valid_trades(recommendation, market))
    if any(v < -1 for v in post.values()):  # oversold: invalid; score as holding
        post = pf.positions(holdings)
    res = _simulate(post, market, future, client, cfg)
    hold = _simulate(pf.positions(holdings), market, future, client, cfg)
    res.update({"case_id": client["client_id"], "source": future.get("source"),
                "vs_hold_return": round(res["forward_return"] - hold["forward_return"], 4)})
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_dir")
    ap.add_argument("recommendation")
    ap.add_argument("--future")
    a = ap.parse_args()
    rec = json.loads(Path(a.recommendation).read_text(encoding="utf-8"))
    print(json.dumps(backtest(a.case_dir, rec, a.future), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
