"""Market history and held-out windows for ballast scenarios (shared by generate.py and backtest.py).

Each case is an independent "replay world": a contiguous window of REAL monthly total returns
(scenarios/data/monthly_returns.csv) is re-dated so that its history ends at as_of; the months that really
followed become the held-out future. Single stocks are simulated (rf + beta * (US - rf) + noise).
If the CSV is missing, returns are simulated from config.yaml market.simulate (labelled in the output).
"""
from __future__ import annotations

import csv
import math
import random
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
FUNDS = ("US_EQ", "INTL_EQ", "BOND", "CASH")


def load_config(path: str | Path | None = None) -> dict:
    return yaml.safe_load(Path(path or ROOT / "config.yaml").read_text(encoding="utf-8"))


def load_returns(cfg: dict) -> list[tuple[str, dict[str, float]]] | None:
    p = ROOT / cfg["market"]["returns_csv"]
    if not p.exists():
        return None
    with p.open(encoding="utf-8") as f:
        return [(r["month"], {k: float(r[k]) for k in FUNDS}) for r in csv.DictReader(f)]


def month_ends(last: date, n: int) -> list[str]:
    """n month-end dates ending at `last` (a month-end), oldest first."""
    out, d = [], last
    for _ in range(n):
        out.append(d.isoformat())
        d = d.replace(day=1) - timedelta(days=1)
    return out[::-1]


def next_month_ends(after: date, n: int) -> list[str]:
    out, d = [], after
    for _ in range(n):
        first_next = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        d = (first_next.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        out.append(d.isoformat())
    return out


def _cholesky(a: list[list[float]]) -> list[list[float]]:
    n = len(a)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = sum(L[i][k] * L[j][k] for k in range(j))
            L[i][j] = math.sqrt(max(a[i][i] - s, 1e-12)) if i == j else (a[i][j] - s) / L[j][j]
    return L


def simulate_returns(rng: random.Random, cfg: dict, n: int) -> list[dict[str, float]]:
    sim = cfg["market"]["simulate"]
    L = _cholesky([[float(sim["corr"][a][b]) for b in FUNDS] for a in FUNDS])
    out = []
    for _ in range(n):
        z = [rng.gauss(0, 1) for _ in FUNDS]
        e = [sum(L[i][k] * z[k] for k in range(i + 1)) for i in range(len(FUNDS))]
        out.append({s: sim["mu"][s] / 12 + sim["vol"][s] / math.sqrt(12) * e[i] for i, s in enumerate(FUNDS)})
    return out


def _cum(rs: list[float]) -> list[float]:
    p, out = 1.0, []
    for r in rs:
        p *= 1 + r
        out.append(p)
    return out


def trailing_drawdown(rs: list[float], lookback: int) -> tuple[float, int]:
    """(end / peak - 1, months from peak to end) over the last `lookback` months of returns."""
    path = [1.0] + _cum(rs)
    window = path[-(lookback + 1):]
    peak_i = max(range(len(window)), key=lambda i: window[i])
    return window[-1] / window[peak_i] - 1, len(window) - 1 - peak_i


def build_world(seed: int, cfg: dict, drop_anchor: str | None = None) -> dict:
    """Pick a window and return {'hist': [returns]*H, 'fut': [returns]*F, 'source', 'window'} incl. single stocks."""
    mk = cfg["market"]
    H, F = int(mk["history_months"]), int(mk["holdout_months"])
    rng = random.Random(seed)
    data = load_returns(cfg)
    if data is not None:
        months = [m for m, _ in data]
        if drop_anchor:
            end = months.index(mk["drop_anchors"][drop_anchor]["end"])
        else:
            lo = max(months.index(mk["anchor_earliest"]), H - 1)
            cands = [i for i in range(lo, len(months) - F)
                     if trailing_drawdown([data[j][1]["US_EQ"] for j in range(i - H + 1, i + 1)], 6)[0]
                     > mk["calm_max_trailing_drawdown"]]
            end = rng.choice(cands)
        rets = [dict(data[j][1]) for j in range(end - H + 1, end + F + 1)]
        source = "real"
        window = {"history": f"{months[end - H + 1]}..{months[end]}", "future": f"{months[end + 1]}..{months[end + F]}"}
    else:
        rets = simulate_returns(rng, cfg, H + F)
        source, window = "simulated", None
    for tkr, ss in cfg["single_stocks"].items():
        sig = ss["idio_vol_annual"] / math.sqrt(12)
        for r in rets:
            r[tkr] = max(-0.95, r["CASH"] + ss["beta"] * (r["US_EQ"] - r["CASH"]) + rng.gauss(0, sig))
    return {"hist": rets[:H], "fut": rets[H:], "source": source, "window": window}


def history_block(world: dict, prices_now: dict[str, float], as_of: str) -> dict:
    """market.json "history": month-end total-return prices ending at as_of prices (oldest first)."""
    H = len(world["hist"])
    last = date.fromisoformat(as_of) - timedelta(days=1)
    prices = {}
    for s, p_now in prices_now.items():
        if s == "CASH":
            continue
        ps, p = [], p_now
        for r in reversed(world["hist"]):
            ps.append(round(p, 2))
            p = p / (1 + r[s])
        prices[s] = ps[::-1]
    note = ("Month-end total-return prices (distributions reinvested). Fund series follow historical index "
            "returns re-dated to end at as_of; single-stock series are simulated.")
    if world["source"] == "simulated":
        note = "Month-end prices simulated from long-run return/volatility assumptions (no real data loaded)."
    return {"frequency": "monthly", "dates": month_ends(last, H), "prices": prices,
            "tbill_annual_pct": [round(1200 * r["CASH"], 2) for r in world["hist"]], "note": note}


def future_block(world: dict, prices_now: dict[str, float], as_of: str, case_id: str) -> dict:
    """Held-out window (scenarios/holdout/...): never copied into an agent's case directory."""
    start = date.fromisoformat(as_of) - timedelta(days=1)
    prices = {}
    for s, p0 in prices_now.items():
        if s == "CASH":
            continue
        prices[s] = [round(p0 * c, 4) for c in _cum([r[s] for r in world["fut"]])]
    return {"case_id": case_id, "as_of": as_of, "frequency": "monthly",
            "dates": next_month_ends(start, len(world["fut"])), "prices": prices,
            "cash_return": [round(r["CASH"], 6) for r in world["fut"]],
            "source": world["source"], "real_window": world["window"]}


def drop_from_world(world: dict, lookback: int) -> dict:
    """Peak-to-end change per symbol, measured from the US equity peak inside the history lookback."""
    us = [r["US_EQ"] for r in world["hist"]]
    dd, months_since_peak = trailing_drawdown(us, lookback)
    tail = world["hist"][len(world["hist"]) - months_since_peak:] if months_since_peak else []
    change = {s: (math.prod(1 + r[s] for r in tail) - 1) for s in world["hist"][0]}
    return {"us_drawdown": dd, "months_since_peak": months_since_peak, "change": change}
