"""Client journeys: one synthetic client reviewed quarterly over ~2.5 years of a REAL market regime.

    python scenarios/journeys.py            # write scenarios/journeys/ + scenarios/holdout/journeys/, then self-check
    python scenarios/journeys.py --check    # self-check only (existing files)

Layout:
  scenarios/journeys/j-00N/meta.json                      persona, arc, regime, checkpoints, train/holdout split
  scenarios/journeys/j-00N/tKK/{client,holdings,market,events}.json   what the agent sees at checkpoint KK
  scenarios/holdout/journeys/j-00N/tKK/future.json        next 12 real months (never in a checkpoint dir)
  scenarios/holdout/journeys/j-00N/meta.json              real calendar window replayed (hidden from agent/Muse)
  scenarios/journeys/report.json                          oracle/naive/backtest per checkpoint

How a checkpoint is built:
  * client.json is the profile as of the PREVIOUS review (age is current). Effects of new events (income, marital
    status, dependents, expenses) and the reference recommendation's profile_updates are applied AFTER the review,
    so the agent must react to events.json - exactly like the single-case sets.
  * holdings.json = previous checkpoint's holdings + oracle.recommend trades, marked to market month by month with the
    real returns, plus T-bill interest on CASH, monthly contributions (invested at targets) while employed, RSU
    vesting into employer stock, and expense draws from CASH while unemployed. Divorce splits positions; an
    inheritance is deposited to CASH.
  * market.json = prices at the checkpoint + 48 months of history (real fund returns, simulated single stocks).
  * events.json = only events since the previous checkpoint.
Dates are re-dated so the last checkpoint is as_of = config.as_of; the real window lives only in holdout/.
Deterministic: seeded per journey; reuses config.yaml and data/monthly_returns.csv.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "agent" / "tools"))
sys.path.insert(0, str(ROOT))
import portfolio as pf  # noqa: E402
import market_model as mm  # noqa: E402
import oracle  # noqa: E402
from backtest import backtest  # noqa: E402

CFG = mm.load_config()
EV = CFG["events"]
N_CHECK, STEP, TRAIN = 10, 3, 5          # 10 quarterly checkpoints; t01-t05 train, t06-t10 holdout
JOURNEY_SEED = 5005
OUT = ROOT / "journeys"
HOLD = ROOT / "holdout" / "journeys"
FUNDS = ("US_EQ", "INTL_EQ", "BOND")

# Profile effects applied after the review in which an event appears (assumptions; see SOURCES.md).
MARRIAGE_EXPENSE_MULT = 1.2
CHILD_MONTHLY_COST = 1100      # USDA-based cost of raising a child, inflated (assumption)
DIVORCE_EXPENSE_MULT = 0.85

JOURNEYS = [
    dict(id="j-001", name="Priya Okafor", state="WA", age=34, months_to_birthday=5, occupation="senior software engineer",
         employer="NMBX", income=165000, expenses=7800, deps=0, marital="single", risk=4, total=310000,
         weights={"equity": 0.77, "cash": 0.07}, single_w=0.07, intl=0.30, contrib=1900, rsu_q=6000,
         targets={"equity": 0.75, "bond": 0.17, "cash": 0.08}, real_t01_end="2007-06",
         regime="Credit crisis: steady market, then a 50% equity crash and early recovery",
         arc="Promotion, marriage and a first child in a calm market; laid off at the bottom of the crash; "
             "re-employed during the recovery; then an unexpected inheritance.",
         events={2: [("job_change", {"raise": 1.18})], 3: [("marriage", {})], 5: [("child", {})],
                 7: [("layoff", {"tenure": 6}), ("market_drop", {})], 9: [("job_change", {"ratio": 0.95})],
                 10: [("inheritance", {"x": 0.30})]}),
    dict(id="j-002", name="Marcus Delgado", state="TX", age=38, months_to_birthday=2, occupation="regional sales manager",
         employer="KSTL", income=142000, expenses=7200, deps=1, marital="married", risk=4, total=420000,
         weights={"equity": 0.80, "cash": 0.05}, single_w=0.18, intl=0.20, contrib=1500, rsu_q=8000,
         targets={"equity": 0.75, "bond": 0.18, "cash": 0.07}, real_t01_end="2019-03",
         regime="Pandemic shock: a fast 20%+ crash, then a strong rally",
         arc="Holds too much employer stock; promoted; laid off in the pandemic crash; re-hired by the same "
             "employer at lower pay with a sign-on RSU grant that rebuilds the concentration; second child; divorce late "
             "in the window.",
         events={3: [("job_change", {"raise": 1.12})], 5: [("layoff", {"tenure": 9}), ("market_drop", {})],
                 7: [("job_change", {"ratio": 0.90, "same_employer": True, "rsu_q": 16000})], 8: [("child", {})], 10: [("divorce", {})]}),
    dict(id="j-003", name="Elena Varga", state="IL", age=53, months_to_birthday=11, occupation="attorney",
         employer=None, income=285000, expenses=13500, deps=1, marital="married", risk=3, total=950000,
         weights={"equity": 0.64, "cash": 0.03}, single_w=0.0, intl=0.25, contrib=3500, rsu_q=0,
         targets={"equity": 0.65, "bond": 0.30, "cash": 0.05}, targets_update=False, real_t01_end="2021-03",
         regime="Rate shock: stocks and bonds fall together, then a partial recovery",
         arc="Pre-retiree holding a stale model allocation; made partner; caught by a stock and bond drawdown; "
             "inherits from a parent; turns 55 and cuts back her hours.",
         events={3: [("job_change", {"raise": 1.15})], 5: [("market_drop", {})], 7: [("inheritance", {"x": 0.25})],
                 9: [("job_change", {"ratio": 0.80})]}),
    dict(id="j-004", name="Kenji Lundgren", state="CA", age=31, months_to_birthday=7, occupation="senior software engineer",
         employer="NMBX", income=150000, expenses=6200, deps=0, marital="single", risk=4, total=330000,
         weights={"equity": 0.80, "cash": 0.06}, single_w=0.25, intl=0.20, contrib=1600, rsu_q=7000,
         targets={"equity": 0.78, "bond": 0.14, "cash": 0.08}, real_t01_end="2000-03",
         shocks={"NMBX": {"2000-12": -0.35, "2001-06": -0.40}},
         regime="Dot-com bust: a slow multi-year bear market, with employer stock collapsing",
         arc="A quarter of the portfolio in employer stock at the peak; marries; laid off when the stock collapses; "
             "re-employed at a startup that folds a year later (second layoff); re-employed again; "
             "the bear market deepens late in the window.",
         events={2: [("marriage", {})], 4: [("layoff", {"tenure": 4})], 6: [("job_change", {"ratio": 0.90})],
                 8: [("layoff", {"tenure": 1})], 9: [("job_change", {"ratio": 1.05})], 10: [("market_drop", {})]}),
    dict(id="j-005", name="Hannah Brennan", state="OH", age=28, months_to_birthday=8, occupation="elementary school teacher",
         employer=None, income=68000, expenses=4300, deps=0, marital="single", risk=3, total=85000,
         weights={"equity": 0.61, "cash": 0.16}, single_w=0.0, intl=0.30, contrib=600, rsu_q=0,
         targets={"equity": 0.60, "bond": 0.24, "cash": 0.16}, real_t01_end="2013-06",
         regime="Calm bull market with low volatility (a small correction at the end)",
         arc="A young saver: marries, moves into school administration with a raise, has a child, and "
             "receives an inheritance late. Many quiet quarters, so no-churn is tested.",
         events={2: [("marriage", {})], 5: [("job_change", {"raise": 1.20})], 7: [("child", {})],
                 10: [("inheritance", {"x": 0.60})]}),
    dict(id="j-006", name="Rafael Sandoval", state="FL", age=57, months_to_birthday=6, occupation="logistics manager",
         employer=None, income=125000, expenses=7900, deps=0, marital="married", risk=3, total=720000,
         weights={"equity": 0.72, "cash": 0.06}, single_w=0.0, intl=0.20, contrib=1200, rsu_q=0,
         targets={"equity": 0.65, "bond": 0.29, "cash": 0.06}, real_t01_end="2015-06",
         regime="Mixed: a 2015-16 correction, then a steady rally",
         arc="Pre-retiree already past 55 holding too much equity; takes an early buyout (layoff with large "
             "severance); returns as a consultant at lower pay; a late-life divorce; inherits; the consulting "
             "contract ends.",
         events={2: [("layoff", {"tenure": 18})], 4: [("job_change", {"ratio": 0.70})], 7: [("divorce", {})],
                 9: [("inheritance", {"x": 0.20})], 10: [("layoff", {"tenure": 2})]}),
]


# ---------------------------------------------------------------- dates
def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def month_end(first: date) -> date:
    return add_months(first, 1) - timedelta(days=1)


def r2(x: float) -> float:
    return round(x + 0.0, 2)


def round_to(x: float, step: float) -> float:
    return round(x / step) * step


# ---------------------------------------------------------------- market path
def build_path(j: dict, rng: random.Random) -> dict:
    """Monthly total-return price index per symbol over [t01 history start, t10 + holdout], base = t01 price."""
    data = mm.load_returns(CFG)
    months = [m for m, _ in data]
    H, F = CFG["market"]["history_months"], CFG["market"]["holdout_months"]
    i1 = months.index(j["real_t01_end"])
    lo_i, hi_i = i1 - H + 1, i1 + STEP * (N_CHECK - 1) + F
    if lo_i < 0 or hi_i >= len(months):
        raise ValueError(f"{j['id']}: real window out of data range")
    rets = [dict(data[i][1]) for i in range(lo_i, hi_i + 1)]
    shocks = j.get("shocks", {})
    for tkr, ss in CFG["single_stocks"].items():
        sig = ss["idio_vol_annual"] / math.sqrt(12)
        for k, r in enumerate(rets):
            x = r["CASH"] + ss["beta"] * (r["US_EQ"] - r["CASH"]) + rng.gauss(0, sig)
            x = (1 + x) * (1 + shocks.get(tkr, {}).get(months[lo_i + k], 0.0)) - 1
            r[tkr] = max(-0.9, x)
    syms = [s for s in rets[0] if s != "CASH"]
    level = {s: [1.0] for s in syms}
    for r in rets:
        for s in syms:
            level[s].append(level[s][-1] * (1 + r[s]))
    # level[s][k+1] is the index at the end of real month lo_i + k; normalise so t01 = base price
    base = {**{s: a["price"] for s, a in CFG["assets"].items() if s != "CASH"},
            **{t: v["price"] for t, v in CFG["single_stocks"].items()}}
    t01_k = i1 - lo_i + 1
    price = {s: [base[s] * v / level[s][t01_k] for v in level[s]] for s in syms}
    return {"months": months[lo_i:hi_i + 1], "rets": rets, "price": price, "t01_k": t01_k}


def px_at(path: dict, k: int) -> dict:          # k indexes level arrays (end of real month lo_i + k - 1)
    return {s: path["price"][s][k] for s in path["price"]}


# ---------------------------------------------------------------- holdings helpers
def to_units(values: dict, prices: dict) -> dict:
    return {s: (v if s == "CASH" else v / prices[s]) for s, v in values.items() if v > 0.005}


def holdings_json(units: dict, prices: dict, as_of: str) -> dict:
    order = [s for s in ("US_EQ", "INTL_EQ", "BOND") if s in units] + \
            sorted(s for s in units if s not in ("US_EQ", "INTL_EQ", "BOND", "CASH")) + (["CASH"] if "CASH" in units else [])
    pos = []
    for s in order:
        if s == "CASH":
            u = round(units[s], 2)
            pos.append({"symbol": s, "units": u, "value": u})
        else:
            u = round(units[s], 3)
            if u <= 0:
                continue
            pos.append({"symbol": s, "units": u, "value": r2(u * prices[s])})
    return {"as_of": as_of, "positions": pos}


def market_json(path: dict, k: int, as_of: date) -> dict:
    H = CFG["market"]["history_months"]
    prices = px_at(path, k)
    syms = {s: {"price": r2(p), "class": CFG["assets"][s]["class"]} for s, p in prices.items() if s in CFG["assets"]}
    syms.update({t: {"price": r2(prices[t]), "class": "equity", "single_stock": True} for t in CFG["single_stocks"]})
    syms["CASH"] = {"price": 1.0, "class": "cash"}
    last = as_of - timedelta(days=1)
    hist = {s: [r2(path["price"][s][i]) for i in range(k - H + 1, k + 1)] for s in prices}
    return {"as_of": as_of.isoformat(), "symbols": syms,
            "history": {"frequency": "monthly", "dates": mm.month_ends(last, H), "prices": hist,
                        "tbill_annual_pct": [round(1200 * path["rets"][i - 1]["CASH"], 2) for i in range(k - H + 1, k + 1)],
                        "note": "Month-end total-return prices. Fund series follow historical index returns re-dated "
                                "to end at as_of; single-stock series are simulated."}}


def future_json(path: dict, k: int, as_of: date, cid: str) -> dict:
    F = CFG["market"]["holdout_months"]
    p0 = {s: r2(v) for s, v in px_at(path, k).items()}
    prices = {s: [round(p0[s] * path["price"][s][k + i] / path["price"][s][k], 4) for i in range(1, F + 1)]
              for s in p0}
    return {"case_id": cid, "as_of": as_of.isoformat(), "frequency": "monthly",
            "dates": mm.next_month_ends(as_of - timedelta(days=1), F), "prices": prices,
            "cash_return": [round(path["rets"][k + i - 1]["CASH"], 6) for i in range(1, F + 1)], "source": "real",
            "real_window": {"future": f"{path['months'][k]}..{path['months'][k + F - 1]}"}}


# ---------------------------------------------------------------- journey simulation
def build_journey(j: dict) -> dict:
    rng = random.Random(JOURNEY_SEED * 100 + int(j["id"][-3:]))
    path = build_path(j, rng)
    final_asof = date.fromisoformat(CFG["as_of"])
    asofs = [add_months(final_asof, -STEP * (N_CHECK - k)) for k in range(1, N_CHECK + 1)]
    ks = [path["t01_k"] + STEP * (k - 1) for k in range(1, N_CHECK + 1)]

    # initial holdings at t01
    T = j["total"]
    p1 = px_at(path, ks[0])
    we, wc = j["weights"]["equity"], j["weights"]["cash"]
    eq_fund = (we - j["single_w"]) * T
    vals = {"US_EQ": eq_fund * (1 - j["intl"]), "INTL_EQ": eq_fund * j["intl"], "BOND": (1 - we - wc) * T, "CASH": wc * T}
    if j["employer"]:
        vals[j["employer"]] = j["single_w"] * T
    units = to_units(vals, p1)

    prof = {"name": j["name"], "state": j["state"], "occupation": j["occupation"], "employment_status": "employed",
            "marital_status": j["marital"], "annual_income": j["income"], "monthly_expenses": j["expenses"],
            "dependents": j["deps"], "risk_score": j["risk"], "targets": dict(j["targets"]),
            "monthly_contribution": j["contrib"],
            "goals": [{"type": "retirement", "target_year": final_asof.year + max(65 - j["age"], 2)}]}
    employer_name = CFG["single_stocks"][j["employer"]]["company"] if j["employer"] else None
    if employer_name:
        prof["employer"] = f"{employer_name} ({j['employer']})"
    at_employer = bool(j["employer"])
    rsu_q = j["rsu_q"]
    unemployed_extra = 0.0
    eid = 0
    checkpoints = []
    for c in range(1, N_CHECK + 1):
        k, as_of = ks[c - 1], asofs[c - 1]
        cid = f"{j['id']}-t{c:02d}"
        # ---- roll forward from previous checkpoint
        if c > 1:
            for m in range(ks[c - 2] + 1, k + 1):
                r = path["rets"][m - 1]
                px = px_at(path, m)
                units["CASH"] = units.get("CASH", 0.0) * (1 + r["CASH"])
                if prof["employment_status"] == "employed" and prof["monthly_contribution"]:
                    tg = prof["targets"]
                    us_share = units.get("US_EQ", 0) * px["US_EQ"]
                    in_share = units.get("INTL_EQ", 0) * px["INTL_EQ"]
                    f_us = us_share / (us_share + in_share) if us_share + in_share else 0.7
                    cfund = float(prof["monthly_contribution"])
                    units["US_EQ"] = units.get("US_EQ", 0) + cfund * tg["equity"] * f_us / px["US_EQ"]
                    units["INTL_EQ"] = units.get("INTL_EQ", 0) + cfund * tg["equity"] * (1 - f_us) / px["INTL_EQ"]
                    units["BOND"] = units.get("BOND", 0) + cfund * tg["bond"] / px["BOND"]
                    units["CASH"] += cfund * tg["cash"]
                if at_employer and prof["employment_status"] == "employed" and rsu_q and (m - ks[0]) % 3 == 0:
                    units[j["employer"]] = units.get(j["employer"], 0) + rsu_q / px[j["employer"]]
                if prof["employment_status"] == "unemployed":
                    units["CASH"] -= prof["monthly_expenses"]
                    if units["CASH"] < 0:   # forced sale, pro rata across risk assets
                        need = -units["CASH"]
                        units["CASH"] = 0.0
                        risk_v = {s: u * px[s] for s, u in units.items() if s != "CASH"}
                        tot = sum(risk_v.values())
                        for s in risk_v:
                            units[s] *= 1 - min(need / tot, 1.0)
        prices = {s: r2(v) for s, v in px_at(path, k).items()}
        # ---- events since the last review
        events = []
        prev_asof = asofs[c - 2] if c > 1 else add_months(as_of, -STEP)
        span = (as_of - prev_asof).days
        evs = j["events"].get(c, [])
        offs = sorted(rng.sample(range(5, span - 3), len(evs)))
        total_now = sum(u * (1 if s == "CASH" else prices[s]) for s, u in units.items())
        post_effects = []
        for (etype, opt), off in zip(evs, offs):
            eid += 1
            d = prev_asof + timedelta(days=off)
            det: dict = {}
            if etype == "job_change":
                prev_inc = prof["annual_income"]
                new_inc = round_to(prev_inc * opt.get("raise", opt.get("ratio", 1.0)), 500)
                det = {"new_income": new_inc, "previous_income": prev_inc,
                       "new_employer": rng.choice(["Brightwater Health", "Corvane Analytics", "Larkspur Bank",
                                                   "Tidewell Energy", "Orchard Labs", "Halvorsen Group"])
                       if "ratio" in opt and not opt.get("same_employer") else
                       (prof.get("employer") or "previous employer") if opt.get("same_employer") else "same employer (promotion)",
                       "start_date": d.isoformat(),
                       "employer_401k_match_pct": rng.choice(EV["job_change"]["match_pct_choices"])}
                post_effects.append(("job_change", {**det, "same_employer": bool(opt.get("same_employer")),
                                                    "rsu_q": opt.get("rsu_q")}))
            elif etype == "layoff":
                weeks = min(max(2, round(opt["tenure"] * rng.choice(EV["layoff"]["weeks_per_year_choices"]))), 40)
                cobra = rng.choice(EV["layoff"]["cobra_family"] if prof["dependents"] or prof["marital_status"] == "married"
                                   else EV["layoff"]["cobra_single"])
                det = {"severance": round_to(prof["annual_income"] / 52 * weeks, 100), "severance_weeks": weeks,
                       "tenure_years": opt["tenure"], "employer": prof.get("employer") or "previous employer",
                       "last_day": d.isoformat(), "cobra_monthly_premium": cobra}
                post_effects.append(("layoff", det))
            elif etype == "marriage":
                det = {"spouse_name": rng.choice(["Jordan Haddad", "Mei Sorensen", "Omar Castellano", "Leila Novak",
                                                  "Grant Iyer"]),
                       "spouse_age": j["age"] + rng.randint(-3, 3),
                       "spouse_annual_income": round_to(mm.math.exp(rng.gauss(0, 0.4)) * 80000, 1000),
                       "spouse_has_separate_accounts": True}
                post_effects.append(("marriage", det))
            elif etype == "child":
                det = {"child_name": rng.choice(["Theo", "Ava", "Mateo", "Nora", "Kai", "Iris"]),
                       "birth_date": d.isoformat(), "adoption": False}
                post_effects.append(("child", det))
            elif etype == "inheritance":
                amt = round_to(opt["x"] * total_now, 1000)
                units["CASH"] = units.get("CASH", 0.0) + amt
                det = {"amount": amt, "source": "estate of a parent", "form": "cash", "deposited_to": "CASH",
                       "deposit_date": d.isoformat()}
            elif etype == "divorce":
                transferred = 0.0
                for s in list(units):
                    v = units[s] * (1 if s == "CASH" else prices[s])
                    transferred += v * 0.5
                    units[s] *= 0.5
                det = {"final_date": d.isoformat(), "assets_transferred_usd": round_to(transferred, 1000),
                       "custody": "shared" if prof["dependents"] else None,
                       "child_support_monthly": 900 if prof["dependents"] else 0}
                post_effects.append(("divorce", det))
            elif etype == "market_drop":
                us = [path["rets"][i]["US_EQ"] for i in range(k - 12, k)]
                dd, since = mm.trailing_drawdown(us, 12)
                tail = range(k - since, k)
                chg = {s: math.prod(1 + path["rets"][i][s] for i in tail) - 1 for s in ("US_EQ", "INTL_EQ", "BOND")}
                d = as_of - timedelta(days=2)
                det = {"us_equity_change_pct": round(100 * chg["US_EQ"], 1),
                       "intl_equity_change_pct": round(100 * chg["INTL_EQ"], 1),
                       "bond_change_pct": round(100 * chg["BOND"], 1),
                       "peak_date": mm.month_ends(as_of - timedelta(days=1), since + 1)[0],
                       "trough_date": d.isoformat(), "historical_analog": j["regime"]}
            events.append({"id": f"e{eid}", "type": etype, "date": d.isoformat(), "details": det})
        events.sort(key=lambda e: e["date"])

        age = j["age"] + (STEP * (c - 1) + 12 - j["months_to_birthday"]) // 12
        client = {"client_id": cid, **{k2: prof[k2] for k2 in ("name",)}, "age": age,
                  **{k2: prof[k2] for k2 in ("state", "occupation", "employment_status", "marital_status")},
                  "annual_income": prof["annual_income"], "monthly_expenses": prof["monthly_expenses"],
                  "dependents": prof["dependents"], "risk_score": prof["risk_score"],
                  "horizon_years": max(65 - age, 0) if age < 65 else 10,
                  "goals": [dict(g) for g in prof["goals"]], "targets": dict(prof["targets"]),
                  "monthly_contribution": prof["monthly_contribution"]}
        if prof.get("employer"):
            client["employer"] = prof["employer"]
        case = {"client": client, "holdings": holdings_json(units, prices, as_of.isoformat()),
                "market": market_json(path, k, as_of), "events": {"events": events},
                "future": future_json(path, k, as_of, cid)}
        checkpoints.append((c, case))

        # ---- reference recommendation, then carry it forward
        d_tmp = OUT / j["id"] / f"t{c:02d}"
        write_case(d_tmp, HOLD / j["id"] / f"t{c:02d}", case)
        loaded = oracle.load_case(d_tmp)
        rec = oracle.recommend(loaded)
        post = pf.post_trade(case["holdings"], rec["trades"])
        units = to_units({s: v for s, v in post.items()}, {**prices, "CASH": 1.0})
        pu = rec["profile_updates"]
        if rec["trades"] and j.get("targets_update", True):
            ta = rec["target_allocation"]
            eq, bd = round(ta["equity"], 2), round(ta["bond"], 2)
            prof["targets"] = {"equity": eq, "bond": bd, "cash": round(1 - eq - bd, 2)}
        prof["goals"] += pu["goals_add"]
        for etype, det in post_effects:
            if etype == "job_change":
                prof["annual_income"] = det["new_income"]
                if prof["employment_status"] == "unemployed":
                    prof["monthly_expenses"] = round_to(prof["monthly_expenses"] - unemployed_extra, 50)
                    unemployed_extra = 0.0
                    prof["employment_status"] = "employed"
                    prof["monthly_contribution"] = round_to(det["new_income"] * 0.10 / 12, 50)
                    if det.get("same_employer"):
                        at_employer = bool(j["employer"])
                        rsu_q = det.get("rsu_q") or rsu_q   # re-hire grant (sign-on RSUs)
                    else:
                        prof["occupation"] = j["occupation"] if "consult" not in j["arc"] else "independent consultant"
                        prof.pop("employer", None)
                        at_employer = False
                if pu["monthly_contribution"] is not None:
                    prof["monthly_contribution"] = pu["monthly_contribution"]
            elif etype == "layoff":
                prof["employment_status"] = "unemployed"
                unemployed_extra = det["cobra_monthly_premium"]
                prof["monthly_expenses"] = round_to(prof["monthly_expenses"] + unemployed_extra, 50)
                prof["monthly_contribution"] = 0
                at_employer = False
            elif etype == "marriage":
                prof["marital_status"] = "married"
                prof["monthly_expenses"] = round_to(prof["monthly_expenses"] * MARRIAGE_EXPENSE_MULT, 50)
            elif etype == "child":
                prof["dependents"] += 1
                prof["monthly_expenses"] = round_to(prof["monthly_expenses"] + CHILD_MONTHLY_COST, 50)
            elif etype == "divorce":
                prof["marital_status"] = "divorced"
                prof["monthly_expenses"] = round_to(prof["monthly_expenses"] * DIVORCE_EXPENSE_MULT
                                                    + det["child_support_monthly"], 50)
    meta = {"journey_id": j["id"], "persona": {k2: j[k2] for k2 in ("name", "state", "occupation")} |
            {"age_at_start": j["age"], "risk_score": j["risk"]},
            "arc": j["arc"], "regime": j["regime"],
            "checkpoints": [{"id": f"t{c:02d}", "as_of": asofs[c - 1].isoformat(),
                             "split": "train" if c <= TRAIN else "holdout",
                             "events": [e["type"] for e in case["events"]["events"]]} for c, case in checkpoints],
            "train": [f"t{c:02d}" for c in range(1, TRAIN + 1)],
            "holdout": [f"t{c:02d}" for c in range(TRAIN + 1, N_CHECK + 1)]}
    hidden = {"journey_id": j["id"], "real_window": {
        "t01_history_end": j["real_t01_end"], "t10_history_end": path["months"][ks[-1] - 1],
        "months": f"{path['months'][0]}..{path['months'][-1]}"}}
    return {"meta": meta, "hidden": hidden}


def write_case(d: Path, hd: Path, case: dict) -> None:
    d.mkdir(parents=True, exist_ok=True)
    hd.mkdir(parents=True, exist_ok=True)
    for f in ("client", "holdings", "market", "events"):
        (d / f"{f}.json").write_text(json.dumps(case[f], indent=2) + "\n", encoding="utf-8")
    (hd / "future.json").write_text(json.dumps(case["future"], indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- self-check
def check_all() -> dict:
    report = {}
    print(f"{'journey':<7} {'ckpt':<4} {'split':<7} {'age':>3} {'events':<26} {'oracle':>6} {'naive':>7} {'n.score':>7}"
          f" {'fwd ret':>8} {'n.EF':>5}")
    bad = 0
    for jd in sorted(p for p in OUT.iterdir() if p.is_dir()):
        meta = json.loads((jd / "meta.json").read_text(encoding="utf-8"))
        rows = []
        for cp in meta["checkpoints"]:
            d = jd / cp["id"]
            case = oracle.load_case(d)
            rec = oracle.recommend(case)
            o = oracle.score(case, rec)
            n = oracle.score(case, oracle.naive(case))
            ok = o["passed"] and o["score"] >= 0.9999
            bad += not ok
            bo, bn = backtest(d, rec, HOLD / jd.name / cp["id"] / "future.json"), \
                backtest(d, oracle.naive(case), HOLD / jd.name / cp["id"] / "future.json")
            rows.append({"checkpoint": cp["id"], "split": cp["split"], "events": cp["events"],
                         "oracle_score": o["score"], "oracle_solved": ok, "naive_passed": n["passed"],
                         "naive_score": n["score"], "naive_violations": [v["rule"] for v in n["violations"]],
                         "oracle_fwd_return": bo["forward_return"], "naive_fwd_return": bn["forward_return"],
                         "oracle_ef_breach": bo["emergency_fund_breached"], "naive_ef_breach": bn["emergency_fund_breached"]})
            print(f"{jd.name:<7} {cp['id']:<4} {cp['split']:<7} {case['client']['age']:>3} "
                  f"{'+'.join(cp['events']) or '-':<26} {'ok' if ok else 'FAIL':>6} {'pass' if n['passed'] else 'fail':>7}"
                  f" {n['score']:>7.2f} {bo['forward_return']:>+8.3f} {'Y' if bn['emergency_fund_breached'] else '-':>5}"
                  + ("" if n["passed"] else f"  {','.join(r for r in rows[-1]['naive_violations'])}"))
            if not ok:
                print("   UNSOLVED:", o["violations"])
        tr = [r for r in rows if r["split"] == "train"]
        ho = [r for r in rows if r["split"] == "holdout"]
        report[jd.name] = {"meta": meta, "checkpoints": rows,
                           "summary": {"oracle_solvable": f"{sum(r['oracle_solved'] for r in rows)}/{len(rows)}",
                                       "naive_pass_train": f"{sum(r['naive_passed'] for r in tr)}/{len(tr)}",
                                       "naive_pass_holdout": f"{sum(r['naive_passed'] for r in ho)}/{len(ho)}"}}
        print(f"  {jd.name}: oracle {report[jd.name]['summary']['oracle_solvable']}, naive train "
              f"{report[jd.name]['summary']['naive_pass_train']}, naive holdout {report[jd.name]['summary']['naive_pass_holdout']}")
    (OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    report["_unsolved"] = bad
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if not a.check:
        for p in (OUT, HOLD):
            if p.exists():
                shutil.rmtree(p)
        for j in JOURNEYS:
            res = build_journey(j)
            (OUT / j["id"] / "meta.json").write_text(json.dumps(res["meta"], indent=2) + "\n", encoding="utf-8")
            (HOLD / j["id"] / "meta.json").write_text(json.dumps(res["hidden"], indent=2) + "\n", encoding="utf-8")
    rep = check_all()
    return 1 if rep["_unsolved"] else 0


if __name__ == "__main__":
    sys.exit(main())
