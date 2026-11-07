"""Messy client journeys j-007..j-030 (procedural, cascading, ~1/3 financial-services employees).

    python scenarios/journeys_ext.py          # rebuild j-007+ (j-001..j-006 untouched), then self-check all journeys

Same layout and mechanics as journeys.py (profile as of last review; holdings carried forward with oracle trades,
real monthly returns, contributions, RSU vesting, unemployment/disability draws; events since last review;
held-out future outside the checkpoint dir), plus:
  * 10-12 quarterly checkpoints over a real window anywhere in 1994-2025 (crash windows over-sampled for FS clients)
  * events from events_catalog.py with cascades scheduled across quarters (illness -> disability -> bills,
    layoff/firm collapse -> re-employment, home purchase -> relocation, ...); real crashes emit market_drop and,
    for FS employees, a firm collapse (employer stock -90%+) or desk shutdown / bonus cut in the same quarter
  * known cash needs are actually paid on their due dates during the roll-forward
  * at least one quiet checkpoint and one event type first seen in the holdout half
  * every checkpoint is verified solvable; an unsolvable draw is re-drawn at checkpoint level
"""
from __future__ import annotations

import json
import math
import random
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import journeys as J  # noqa: E402
import generate as G  # noqa: E402
import market_model as mm  # noqa: E402
import oracle  # noqa: E402
import events_catalog as E  # noqa: E402
import stress as ST  # noqa: E402

CFG, RX, pf = J.CFG, oracle.RX, J.pf
SJ = CFG["stress"]["journeys"]
FS_STOCKS = CFG["stress"]["fs_single_stocks"]
ALL_SINGLES = {**{t: {"price": v["price"], "beta": v["beta"], "idio_vol_annual": v["idio_vol_annual"]}
                  for t, v in CFG["single_stocks"].items()},
               **{t: {"price": v["price"], "beta": v["beta"], "idio_vol_annual": v["idio_vol_annual"]}
                  for t, v in FS_STOCKS.items()}}
CRASH_TROUGHS = ["2002-09", "2009-02", "2020-03", "2022-09", "1998-08", "2011-09", "2018-12", "2001-09"]
REEMPLOY_AFTER = {"layoff", "firm_collapse", "desk_shutdown", "business_failure"}
UNSEEN_LATE = ["death_of_spouse", "inheritance", "disaster_damage", "fraud_loss", "lawsuit", "tax_bill",
               "parent_long_term_care", "divorce", "trading_blackout", "medical_bill", "adult_child_moves_back",
               "lottery_win", "margin_call", "pension_buyout_offer"]
NOT_RANDOM = {"market_drop", "firm_collapse", "job_change", "margin_call", "business_sale", "lottery_win",
              "lawsuit_settlement"}   # scheduled or too rare to draw at random


def month_idx(months: list[str], m: str) -> int:
    return months.index(m)


def build_path(rng: random.Random, t01_end: str, n_check: int, shocks: dict) -> dict:
    data = mm.load_returns(CFG)
    months = [m for m, _ in data]
    H, F = CFG["market"]["history_months"], CFG["market"]["holdout_months"]
    i1 = months.index(t01_end)
    lo_i, hi_i = i1 - H + 1, i1 + J.STEP * (n_check - 1) + F
    rets = [dict(data[i][1]) for i in range(lo_i, hi_i + 1)]
    for tkr, ss in ALL_SINGLES.items():
        sig = ss["idio_vol_annual"] / math.sqrt(12)
        for k, r in enumerate(rets):
            x = r["CASH"] + ss["beta"] * (r["US_EQ"] - r["CASH"]) + rng.gauss(0, sig)
            x = (1 + x) * (1 + shocks.get(tkr, {}).get(months[lo_i + k], 0.0)) - 1
            r[tkr] = max(-0.97, x)
    syms = [s for s in rets[0] if s != "CASH"]
    level = {s: [1.0] for s in syms}
    for r in rets:
        for s in syms:
            level[s].append(level[s][-1] * (1 + r[s]))
    base = {**{s: a["price"] for s, a in CFG["assets"].items() if s != "CASH"}, **{t: v["price"] for t, v in ALL_SINGLES.items()}}
    t01_k = i1 - lo_i + 1
    price = {s: [base[s] * v / level[s][t01_k] for v in level[s]] for s in syms}
    return {"months": months[lo_i:hi_i + 1], "rets": rets, "price": price, "t01_k": t01_k}


def market_json(path: dict, k: int, as_of: date, employer: str | None) -> dict:
    m = J.market_json(path, k, as_of)
    keep = set(CFG["assets"]) | set(CFG["single_stocks"]) | ({employer} if employer else set())
    m["symbols"] = {s: v for s, v in m["symbols"].items() if s in keep}
    if employer in FS_STOCKS:
        cash = m["symbols"].pop("CASH")
        m["symbols"][employer] = {"price": J.r2(path["price"][employer][k]), "class": "equity", "single_stock": True}
        m["symbols"]["CASH"] = cash
    m["history"]["prices"] = {s: v for s, v in m["history"]["prices"].items() if s in keep}
    return m


def future_json(path: dict, k: int, as_of: date, cid: str, employer: str | None) -> dict:
    f = J.future_json(path, k, as_of, cid)
    keep = set(CFG["assets"]) | set(CFG["single_stocks"]) | ({employer} if employer else set())
    f["prices"] = {s: v for s, v in f["prices"].items() if s in keep}
    return f


def persona(rng: random.Random, jid: str) -> dict:
    fs = int(jid[-3:]) % 3 == 0          # exactly 1/3 of j-007+ are financial-services employees
    age = rng.choice([rng.randint(24, 36), rng.randint(37, 52), rng.randint(53, 66)])
    hh = G.sample_household(rng, age, None)
    if fs:
        hh["retired"] = False
        inc = G.lognorm(rng, CFG["stress"]["fs_income_median"], CFG["stress"]["fs_income_sigma"])
        hh["income"] = G.round_to(min(max(inc, 100000), 900000), 500)
        hh["monthly_exp"] = G.round_to(hh["income"] * G.expense_ratio(hh["income"]) * rng.uniform(0.85, 1.0) / 12, 50)
        hh["total"] = G.round_to(hh["total"] * (hh["income"] / 150000) ** 0.8 * rng.uniform(1.0, 1.8), 100)
    # mass-affluent: portfolio worth 30-80 months of spending, so cash buffers actually bind
    hh["total"] = G.round_to(min(max(hh["total"], hh["monthly_exp"] * 30), hh["monthly_exp"] * 80), 100)
    employer = None
    if fs:
        employer = rng.choice(list(FS_STOCKS))
        hh["occupation"] = rng.choice(FS_STOCKS[employer]["roles"])
    elif not hh["retired"] and rng.random() < 0.3:
        employer = rng.choice(list(CFG["single_stocks"]))
        hh["occupation"] = rng.choice(CFG["single_stocks"][employer]["roles"])
    n_check = rng.choice(SJ["checkpoints"]) if len(SJ["checkpoints"]) == 2 else 10
    n_check = rng.randint(min(SJ["checkpoints"]), max(SJ["checkpoints"]))
    latest = J.add_months(date(2026, 9, 1), -(J.STEP * (n_check - 1) + 12))
    data_months = [m for m, _ in mm.load_returns(CFG)]
    last_ok = f"{latest.year}-{latest.month:02d}"
    if fs and rng.random() < 0.75 or rng.random() < 0.3:
        trough = rng.choice(CRASH_TROUGHS)
        ti = data_months.index(trough)
        t01_end = data_months[ti - J.STEP * rng.randint(2, n_check - 3)]
    else:
        cands = [m for m in data_months if "1994-06" <= m <= last_ok]
        t01_end = rng.choice(cands)
    if t01_end < "1994-06" or t01_end > last_ok:
        t01_end = max(min(t01_end, last_ok), "1994-06")
    return {"id": jid, "fs": fs, "age": age, "mtb": rng.randint(1, 12), "hh": hh, "employer": employer,
            "n_check": n_check, "t01_end": t01_end, "rsu_q": G.round_to(hh["income"] * rng.uniform(0.02, 0.06), 500) if employer else 0,
            "name": f"{rng.choice(G.FIRST)} {rng.choice(G.LAST)}"}


def build(jid: str, seed: int) -> dict:
    rng = random.Random(seed)
    P = persona(rng, jid)
    hh, n = P["hh"], P["n_check"]
    data_months = [m for m, _ in mm.load_returns(CFG)]
    i1 = data_months.index(P["t01_end"])
    real_end = [data_months[i1 + J.STEP * (c - 1)] for c in range(1, n + 1)]
    # crash checkpoints from US trailing 12-month drawdown at each checkpoint
    us = {m: r["US_EQ"] for m, r in mm.load_returns(CFG)}
    crash = []
    for c in range(2, n + 1):
        i = data_months.index(real_end[c - 1])
        dd, _ = mm.trailing_drawdown([us[data_months[j]] for j in range(i - 11, i + 1)], 12)
        if dd < -0.15 and not any(abs(c - x) < 3 for x in crash):
            crash.append(c)
    collapse_c = None
    shocks: dict = {}
    if P["fs"] and crash and rng.random() < 0.6:
        collapse_c = crash[0]
        shocks = {P["employer"]: {real_end[collapse_c - 1]: -rng.uniform(0.90, 0.98)}}
    path = build_path(rng, P["t01_end"], n, shocks)
    final_asof = date.fromisoformat(CFG["as_of"])
    asofs = [J.add_months(final_asof, -J.STEP * (n - c)) for c in range(1, n + 1)]
    ks = [path["t01_k"] + J.STEP * (c - 1) for c in range(1, n + 1)]
    train_n = n // 2

    # initial holdings
    risk = hh["risk"]
    lo, hi = G.BANDS[risk]
    te = rng.choice(G.LOW_HALF_EQUITY[risk] if P["age"] >= 55 else G.MODEL_EQUITY[risk])
    tc = max(0.03, round(rng.uniform(2.5, 5) * hh["monthly_exp"] / hh["total"], 2))
    tb = round(1 - te - tc, 2)
    if tb < 0 or 6 * hh["monthly_exp"] * 1.05 / hh["total"] > 1 - lo - 0.04:
        raise RuntimeError("persona infeasible (cash floor vs risk band)")
    we = te + rng.uniform(-0.03, 0.08)
    wc = max(0.01, rng.uniform(1.0, 4.0) * hh["monthly_exp"] / hh["total"])   # starting cash: 1-4 months
    p1 = J.px_at(path, ks[0])
    sw = rng.uniform(0.03, 0.22) if P["employer"] else 0.0
    eq_fund = max(we - sw, 0.05) * hh["total"]
    intl = rng.uniform(0.15, 0.35)
    vals = {"US_EQ": eq_fund * (1 - intl), "INTL_EQ": eq_fund * intl, "BOND": max(1 - we - wc, 0) * hh["total"],
            "CASH": wc * hh["total"]}
    if P["employer"]:
        vals[P["employer"]] = sw * hh["total"]
    units = J.to_units(vals, {**p1, "CASH": 1.0})
    emp_name = (FS_STOCKS.get(P["employer"], {}).get("company") or
                (CFG["single_stocks"][P["employer"]]["company"] if P["employer"] else None))
    prof = {"name": P["name"], "state": hh["state"], "occupation": hh["occupation"],
            "industry": "financial services" if P["fs"] else None,
            "employment_status": "retired" if hh["retired"] else "employed",
            "marital_status": "married" if hh["married"] else "single", "annual_income": hh["income"],
            "monthly_expenses": hh["monthly_exp"], "dependents": hh["deps"], "risk_score": risk,
            "targets": {"equity": te, "bond": tb, "cash": round(1 - te - tb, 2)},
            "monthly_contribution": 0.0 if hh["retired"] else hh["contrib"],
            "goals": [{"type": "retirement", "target_year": final_asof.year + max(65 - P["age"], 2)}] if P["age"] < 63 else []}
    if P["employer"]:
        prof["employer"] = f"{emp_name} ({P['employer']})"
    st = {"at_employer": bool(P["employer"]), "draw_frac": 0.0, "furlough_left": 0, "pending_needs": [],
          "reemploy_at": None, "used": set(), "disability_cost": 0.0}
    scheduled: dict[int, list[str]] = {}
    if collapse_c:
        scheduled.setdefault(collapse_c, []).extend(["firm_collapse", "market_drop"])
    for c in crash:
        if c != collapse_c:
            scheduled.setdefault(c, []).append("market_drop")
            if P["fs"] and rng.random() < 0.6:
                scheduled[c].append(rng.choice(["desk_shutdown", "bonus_cut", "bonus_cut"]))
    quiet = rng.choice([c for c in range(2, n + 1) if c not in scheduled])
    late_c = rng.choice([c for c in range(train_n + 1, n + 1) if c != quiet])
    eid = 0
    out_cps = []
    for c in range(1, n + 1):
        k, as_of = ks[c - 1], asofs[c - 1]
        cid = f"{jid}-t{c:02d}"
        age = P["age"] + (J.STEP * (c - 1) + 12 - P["mtb"]) // 12
        # ---- roll forward
        if c > 1:
            for m in range(ks[c - 2] + 1, k + 1):
                r = path["rets"][m - 1]
                px = J.px_at(path, m)
                mdate = J.add_months(asofs[c - 2], m - ks[c - 2]) - timedelta(days=1)
                units["CASH"] = units.get("CASH", 0.0) * (1 + r["CASH"])
                if prof["employment_status"] in ("employed", "self-employed") and prof["monthly_contribution"]:
                    tg, cf = prof["targets"], float(prof["monthly_contribution"])
                    units["US_EQ"] = units.get("US_EQ", 0) + cf * tg["equity"] * 0.75 / px["US_EQ"]
                    units["INTL_EQ"] = units.get("INTL_EQ", 0) + cf * tg["equity"] * 0.25 / px["INTL_EQ"]
                    units["BOND"] = units.get("BOND", 0) + cf * tg["bond"] / px["BOND"]
                    units["CASH"] += cf * tg["cash"]
                if st["at_employer"] and prof["employment_status"] == "employed" and P["rsu_q"] and (m - ks[0]) % 3 == 0:
                    units[P["employer"]] = units.get(P["employer"], 0) + P["rsu_q"] / px[P["employer"]]
                draw = prof["monthly_expenses"] * st["draw_frac"]
                if st["furlough_left"] > 0:
                    draw = prof["monthly_expenses"]
                    st["furlough_left"] -= 1
                for need in list(st["pending_needs"]):
                    if need[0] <= mdate.isoformat():
                        draw += need[1]
                        st["pending_needs"].remove(need)
                units["CASH"] -= draw
                if units["CASH"] < 0:
                    short, units["CASH"] = -units["CASH"], 0.0
                    rv = {s: u * px[s] for s, u in units.items() if s != "CASH"}
                    tot = sum(rv.values())
                    for s in rv:
                        units[s] *= 1 - min(short / tot, 1.0)
        prices = {s: J.r2(v) for s, v in J.px_at(path, k).items()}
        pre_units, pre_prof, pre_st = dict(units), json.loads(json.dumps(prof)), {**st, "used": set(st["used"]),
                                                                                    "pending_needs": list(st["pending_needs"])}
        # ---- choose events for this checkpoint (with checkpoint-level redraws)
        for attempt in range(40):
            units, prof = dict(pre_units), json.loads(json.dumps(pre_prof))
            st = {**pre_st, "used": set(pre_st["used"]), "pending_needs": list(pre_st["pending_needs"])}
            types = [t for t in scheduled.get(c, [])   # scheduled FS shocks only hit clients still in that job
                     if not ((t in ST.FS_ONLY and prof["employment_status"] != "employed")
                             or (t == "firm_collapse" and not st["at_employer"]))]
            if st["reemploy_at"] == c and "job_change" not in types:
                types.append("job_change")
            if c == late_c:
                pool = [t for t in UNSEEN_LATE if t not in st["used"] and ST.eligible(t, _elig(P, prof, age, st))]
                if pool:
                    types.append(rng.choice(pool))
            n_rand = 0
            if c != quiet and c > 1:
                n_rand = (rng.random() < 0.4) if types else                     (rng.random() < SJ["p_event_quarter"]) + (rng.random() < 0.4) + (rng.random() < 0.12)
            el = _elig(P, prof, age, st)
            for _ in range(n_rand):
                cand = [t for t in ST.POOL if t not in NOT_RANDOM and ST.eligible(t, el) and t not in types]
                w = [ST.POOL[t] * (2 if P["fs"] and t in ST.FS_ONLY else 1) for t in cand]
                types.append(rng.choices(cand, weights=w)[0])
                for nxt, pr in ST.CASCADE.get(types[-1], []):
                    if nxt in ("market_drop", "layoff"):
                        continue
                    if rng.random() < pr and ST.eligible(nxt, el) and nxt not in types:
                        if nxt in ("disability", "relocation", "medical_bill") and c < n:
                            scheduled.setdefault(c + 1, []).append(nxt)
                        else:
                            types.append(nxt)
            if c == 1 and attempt > 0:
                types = []
            if c == quiet and attempt > 2:     # a quiet quarter that cannot be solved gets a small routine event
                types = ["annual_review"] if attempt < 6 else [rng.choice(["tax_bill", "medical_bill"])]
            res = apply_events(rng, c, types, eid, P, prof, st, units, prices, path, k, as_of, age, emp_name)
            if res is None:
                continue
            events, post_effects, new_eid = res
            client = make_client(cid, prof, age)
            case = {"client": client, "holdings": J.holdings_json(units, prices, as_of.isoformat()),
                    "market": market_json(path, k, as_of, P["employer"]), "events": {"events": events},
                    "future": future_json(path, k, as_of, cid, P["employer"])}
            d, hd = J.OUT / jid / f"t{c:02d}", J.HOLD / jid / f"t{c:02d}"
            J.write_case(d, hd, case)
            loaded = oracle.load_case(d)
            try:
                rec = oracle.recommend(loaded)
            except ValueError:
                continue
            sc = oracle.score(loaded, rec)
            if sc["passed"] and sc["score"] >= 0.9999:
                break
        else:
            raise RuntimeError(f"{jid} t{c:02d}: no solvable draw")
        eid = new_eid
        st["used"] |= set(types)
        out_cps.append({"id": f"t{c:02d}", "as_of": as_of.isoformat(), "split": "train" if c <= train_n else "holdout",
                        "age": age, "events": [e["type"] for e in events]})
        # ---- after the review: apply trades, then profile effects
        post = pf.post_trade(case["holdings"], rec["trades"])
        units = J.to_units(dict(post), {**prices, "CASH": 1.0})
        # the client's model allocation stays fixed (the agent's cash raises are deviations it must keep justifying)
        prof["goals"] += rec["profile_updates"]["goals_add"]
        for t, det in post_effects:
            profile_effect(rng, t, det, prof, st, P, c, n, rec)
    meta = {"journey_id": jid, "persona": {"name": P["name"], "state": hh["state"], "occupation": hh["occupation"],
                                           "industry": "financial services" if P["fs"] else "other",
                                           "age_at_start": P["age"], "risk_score": risk,
                                           "employer": f"{emp_name} ({P['employer']})" if P["employer"] else None},
            "arc": arc_text(out_cps), "regime": regime_text(path, ks),
            "checkpoints": out_cps, "train": [x["id"] for x in out_cps if x["split"] == "train"],
            "holdout": [x["id"] for x in out_cps if x["split"] == "holdout"],
            "unseen_late_checkpoint": f"t{late_c:02d}", "quiet_checkpoint": f"t{quiet:02d}"}
    hidden = {"journey_id": jid, "real_window": {"t01_history_end": P["t01_end"], "last_history_end": real_end[-1],
                                                 "collapse_checkpoint": f"t{collapse_c:02d}" if collapse_c else None}}
    return {"meta": meta, "hidden": hidden}


def _elig(P, prof, age, st) -> dict:
    return {"age": age, "fs": P["fs"] and prof["employment_status"] == "employed",
            "employer": P["employer"] if st["at_employer"] else None,
            "retired": prof["employment_status"] in ("retired", "unemployed", "on_disability"),
            "married": prof["marital_status"] == "married"}


def apply_events(rng, c, types, eid, P, prof, st, units, prices, path, k, as_of, age, emp_name):
    prev = J.add_months(as_of, -J.STEP)
    span = (as_of - prev).days
    if len(types) > span - 10:
        return None
    offs = sorted(rng.sample(range(5, span - 3), len(types)))
    events, post = [], []
    total_now = sum(u * (1 if s == "CASH" else prices[s]) for s, u in units.items())
    for t, off in zip(types, offs):
        eid += 1
        d = prev + timedelta(days=off)
        ctx = {"income": prof["annual_income"], "expenses": prof["monthly_expenses"], "total": total_now, "age": age,
               "deps": prof["dependents"], "employer": P["employer"], "employer_name": emp_name, "fs": P["fs"],
               "date": d, "as_of": as_of, "married": prof["marital_status"] == "married"}
        if t == "market_drop":
            usr = [path["rets"][i]["US_EQ"] for i in range(k - 12, k)]
            dd, since = mm.trailing_drawdown(usr, 12)
            tail = range(k - since, k)
            chg = {s: math.prod(1 + path["rets"][i][s] for i in tail) - 1 for s in ("US_EQ", "INTL_EQ", "BOND")}
            d = as_of - timedelta(days=2)
            det = {"us_equity_change_pct": round(100 * chg["US_EQ"], 1), "intl_equity_change_pct": round(100 * chg["INTL_EQ"], 1),
                   "bond_change_pct": round(100 * chg["BOND"], 1),
                   "peak_date": mm.month_ends(as_of - timedelta(days=1), since + 1)[0], "trough_date": d.isoformat()}
        elif t == "job_change":
            det = {"new_income": G.round_to(prof["annual_income"] * rng.uniform(0.78, 1.2), 500),
                   "previous_income": prof["annual_income"], "start_date": d.isoformat(),
                   "new_employer": rng.choice(["Brightwater Health", "Corvane Analytics", "Larkspur Bank", "Orchard Labs"])}
        else:
            det = E.CATALOG[t]["make"](rng, ctx)
        # holdings effects visible at this checkpoint
        if t in ST.DEPOSITS and det.get(ST.DEPOSITS[t]):
            units["CASH"] = units.get("CASH", 0.0) + det[ST.DEPOSITS[t]]
        elif t == "fraud_loss":
            lost = min(det["amount_lost"], G.round_to(units.get("CASH", 0) * 0.9, 100))
            det["amount_lost"], det["taken_from"] = lost, "this account's CASH"
            units["CASH"] -= lost
        elif t == "rsu_cliff":
            units[P["employer"]] = units.get(P["employer"], 0) + det["vest_value"] / prices[P["employer"]]
        elif t == "divorce":
            for s in list(units):
                units[s] *= 0.5
            det["assets_transferred_usd"] = G.round_to(total_now * 0.5, 1000)
        elif t == "firm_collapse":
            det["stock_change_pct"] = round(100 * (prices[P["employer"]] / J.px_at(path, k - 3)[P["employer"]] - 1), 1)
        if t in RX.KNOWN_NEED and isinstance(det.get("amount_due"), (int, float)) and det.get("due_date"):
            st["pending_needs"].append((det["due_date"], det["amount_due"]))
        events.append({"id": f"e{eid}", "type": t, "date": d.isoformat(), "details": det})
        post.append((t, det))
    # feasibility before writing
    w = pf.weights({s: (u if s == "CASH" else u * prices[s]) for s, u in units.items()},
                   {"symbols": {**{s: {"class": CFG["assets"][s]["class"]} for s in CFG["assets"]},
                                **{s: {"class": "equity", "single_stock": True} for s in ALL_SINGLES}}})
    restricted = RX.restricted_symbols(events)
    if any(w["by_symbol"].get(s, 0) > 0.095 for s in restricted):
        return None
    lo = G.BANDS[prof["risk_score"]][0]
    if RX.required_cash(prof | {"monthly_expenses": prof["monthly_expenses"]}, events, as_of.isoformat()) * 1.03 \
            / max(w["total"], 1) > 1 - lo - 0.03:
        return None
    events.sort(key=lambda e: e["date"])
    return events, post, eid


def make_client(cid, prof, age) -> dict:
    c = {"client_id": cid, "name": prof["name"], "age": age, "state": prof["state"], "occupation": prof["occupation"]}
    if prof.get("industry"):
        c["industry"] = prof["industry"]
    c.update({"employment_status": prof["employment_status"], "marital_status": prof["marital_status"],
              "annual_income": prof["annual_income"], "monthly_expenses": prof["monthly_expenses"],
              "dependents": prof["dependents"], "risk_score": prof["risk_score"],
              "horizon_years": max(65 - age, 0) if age < 65 else max(90 - age, 8),
              "goals": [dict(g) for g in prof["goals"]], "targets": dict(prof["targets"]),
              "monthly_contribution": prof["monthly_contribution"]})
    if prof.get("employer"):
        c["employer"] = prof["employer"]
    return c


def profile_effect(rng, t, det, prof, st, P, c, n, rec) -> None:
    R = G.round_to
    inc = lambda x: R(prof["monthly_expenses"] + (x or 0), 50)  # noqa: E731
    if t in REEMPLOY_AFTER or t == "regulatory_ban":
        prof["employment_status"], prof["monthly_contribution"], st["draw_frac"] = "unemployed", 0.0, 1.0
        st["at_employer"] = False
        prof.pop("employer", None)
        if c < n:
            st["reemploy_at"] = min(n, c + rng.randint(1, 3))
    elif t == "job_change":
        prof["annual_income"] = det["new_income"]
        if prof["employment_status"] != "employed":
            prof["employment_status"], st["draw_frac"] = "employed", 0.0
            prof["occupation"] = prof["occupation"] if not P["fs"] else rng.choice(["consultant", "operations manager", prof["occupation"]])
            prof["monthly_contribution"] = R(det["new_income"] * 0.08 / 12, 50)
        if rec["profile_updates"]["monthly_contribution"] is not None:
            prof["monthly_contribution"] = rec["profile_updates"]["monthly_contribution"]
    elif t == "furlough":
        st["furlough_left"] = min(3, math.ceil(det["unpaid_weeks"] / 4.3))
    elif t == "disability":
        prof["employment_status"] = "on_disability"
        prof["monthly_contribution"] = 0.0
        st["draw_frac"] = max(0.0, 1 - det["benefit_pct_of_income"] / 100) * 0.6
        prof["monthly_expenses"] = inc(det.get("monthly_cost_increase"))
    elif t in ("serious_illness", "parent_long_term_care", "special_needs_diagnosis"):
        prof["monthly_expenses"] = inc(det.get("monthly_cost_increase"))
    elif t == "adult_child_moves_back":
        prof["monthly_expenses"] = inc(det.get("monthly_cost_increase"))
        prof["dependents"] += 1
    elif t == "death_of_spouse":
        prof["marital_status"] = "widowed"
        prof["monthly_expenses"] = R(prof["monthly_expenses"] * 0.8, 50)
    elif t == "marriage":
        prof["marital_status"] = "married"
        prof["monthly_expenses"] = R(prof["monthly_expenses"] * 1.2, 50)
    elif t == "divorce":
        prof["marital_status"] = "divorced"
        prof["monthly_expenses"] = R(prof["monthly_expenses"] * 0.85 + max(det.get("alimony_monthly") or 0, 0)
                                     + (det.get("child_support_monthly") or 0), 50)
    elif t == "child":
        prof["dependents"] += det.get("multiple_birth", 1)
        prof["monthly_expenses"] = inc(1100 * det.get("multiple_birth", 1))
    elif t == "home_purchase":
        prof["monthly_expenses"] = inc(det.get("monthly_housing_cost_change"))
    elif t == "relocation":
        prof["monthly_expenses"] = R(prof["monthly_expenses"] * (1 + det["cost_of_living_change_pct"] / 100), 50)
    elif t == "pay_cut":
        prof["annual_income"] = det["new_income"]
    elif t == "gig_income":
        prof["employment_status"], prof["annual_income"] = "self-employed", R(det["avg_monthly_income"] * 12, 500)
        st["at_employer"] = False
    elif t == "retirement":
        prof["employment_status"], prof["monthly_contribution"] = "retired", 0.0
        prof["annual_income"] = R(12 * (det["pension_monthly"] + det["social_security_monthly"]), 500)
        st["draw_frac"] = 0.3
    elif t in ("student_loan_restart",):
        prof["monthly_expenses"] = inc(det["monthly_payment"])
    elif t == "credit_card_debt":
        prof["monthly_expenses"] = inc(R(det["balance"] * 0.03, 10))
    elif t == "sabbatical":
        st["furlough_left"] = min(3, det["unpaid_months"])


def arc_text(cps: list[dict]) -> str:
    parts = [f"{x['id']}: {'+'.join(x['events'])}" for x in cps if x["events"]]
    return "; ".join(parts)


def regime_text(path: dict, ks: list[int]) -> str:
    us = path["price"]["US_EQ"]
    seg = [us[k] for k in range(ks[0], ks[-1] + 1)]
    tot = seg[-1] / seg[0] - 1
    peak, mdd = seg[0], 0.0
    for v in seg:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    kind = "crash and recovery" if mdd < -0.3 else "bear market" if mdd < -0.18 else "choppy" if mdd < -0.1 else "calm bull"
    return f"{kind}: US equity {100 * tot:+.0f}% over the journey, worst drawdown {100 * mdd:.0f}%"


def main() -> int:
    first, nj = SJ["first_id"], SJ["n"]
    for i in range(first, first + nj):
        jid = f"j-{i:03d}"
        for p in (J.OUT / jid, J.HOLD / jid):
            if p.exists():
                shutil.rmtree(p)
        for attempt in range(60):   # journey-level redraw if a persona/checkpoint has no solvable draw
            try:
                res = build(jid, SJ["seed"] * 1000 + i + 7919 * attempt)
                break
            except RuntimeError:
                continue
        else:
            raise RuntimeError(f"{jid}: no solvable journey")
        (J.OUT / jid / "meta.json").write_text(json.dumps(res["meta"], indent=2) + "\n", encoding="utf-8")
        (J.HOLD / jid / "meta.json").write_text(json.dumps(res["hidden"], indent=2) + "\n", encoding="utf-8")
        print(jid, res["meta"]["persona"]["occupation"], "|", res["meta"]["regime"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
