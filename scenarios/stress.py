"""Stress population: ~300 messy single cases with overlapping / cascading life and work events.

    python scenarios/stress.py            # write scenarios/cases/stress/s-NNN + holdout/stress, self-check, report
    python scenarios/stress.py --check    # self-check only

Households reuse generate.py's calibrated sampler (SCF/CE), widened to ages 22-75, with ~25% financial-services
employees (higher, bonus-heavy pay; employer stock in invented FS tickers). Events come from events_catalog.py
(54 types, randomized severity, ~12% with withheld amounts) plus cascade rules (illness -> disability -> bills;
firm collapse -> employer stock wipe-out + crash; prop loss -> margin call; ...). Every case is verified solvable
(oracle.recommend scores 1.0 under checker/check.py incl. checker/rules_ext.py) or redrawn.
Outputs: scenarios/cases/stress/<id>/*.json, scenarios/holdout/stress/<id>/future.json,
scenarios/cases/stress_manifest.json (archetype/tags; outside every case dir), scenarios/stress_report.json.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import zlib
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import generate as G  # noqa: E402  (household sampler, positions, config)
import market_model as mm  # noqa: E402
import oracle  # noqa: E402
import events_catalog as E  # noqa: E402
from backtest import backtest  # noqa: E402

pf, RX, CFG = G.pf, oracle.RX, G.CFG
S = CFG["stress"]
FS_STOCKS = S["fs_single_stocks"]
OUT = ROOT / "cases" / "stress"
HOLD = ROOT / "holdout" / "stress"
AS_OF = date.fromisoformat(CFG["as_of"])

NOISE_GENERAL = ["startup_equity", "crypto_loss", "pay_cut", "student_loan_restart", "promotion_title_only", "annual_review"]
NOISE_FS = ["bonus_deferral", "carried_interest", "bonus_cut"]
POOL = {  # type: weight (eligibility checked in eligible())
    "layoff": 6, "job_change": 6, "marriage": 3, "child": 4, "divorce": 3, "inheritance": 3, "market_drop": 4,
    "serious_illness": 4, "disability": 2, "parent_long_term_care": 4, "medical_bill": 3, "special_needs_diagnosis": 1,
    "death_of_spouse": 2, "adult_child_moves_back": 3, "tuition_due": 4, "home_purchase": 4, "relocation": 2,
    "disaster_damage": 2, "foreclosure_risk": 1, "furlough": 2, "pay_cut": 2, "startup_equity": 2, "ipo_lockup": 1,
    "rsu_cliff": 2, "sabbatical": 1, "gig_income": 2, "business_failure": 1, "early_retirement_offer": 1,
    "pension_buyout_offer": 1, "retirement": 2, "lottery_win": 0.5, "lawsuit_settlement": 1, "business_sale": 1,
    "crypto_loss": 2, "fraud_loss": 2, "tax_bill": 3, "student_loan_restart": 2, "credit_card_debt": 2,
    "bankruptcy": 0.5, "lawsuit": 1, "legal_judgment": 0.5,
    # financial-services only
    "bonus_deferral": 5, "bonus_cut": 4, "deferred_comp_clawback": 2, "firm_collapse": 3, "trading_blackout": 4,
    "insider_status": 3, "carried_interest": 2, "desk_shutdown": 3, "regulatory_ban": 1, "prop_trading_loss": 2,
}
FS_ONLY = {"bonus_deferral", "bonus_cut", "deferred_comp_clawback", "firm_collapse", "insider_status",
           "carried_interest", "desk_shutdown", "regulatory_ban", "prop_trading_loss"}
NEEDS_EMPLOYER = {"ipo_lockup", "rsu_cliff", "trading_blackout", "insider_status", "firm_collapse"}
CASCADE = {
    "serious_illness": [("disability", 0.35), ("medical_bill", 0.4)],
    "firm_collapse": [("market_drop", 1.0), ("parent_long_term_care", 0.15), ("margin_call", 0.2)],
    "prop_trading_loss": [("margin_call", 0.7)],
    "market_drop": [("bonus_cut", 0.5), ("margin_call", 0.15), ("layoff", 0.2)],
    "death_of_spouse": [("adult_child_moves_back", 0.2), ("tax_bill", 0.3)],
    "home_purchase": [("relocation", 0.4)],
    "layoff": [("credit_card_debt", 0.25), ("foreclosure_risk", 0.15)],
    "divorce": [("relocation", 0.3)],
    "business_failure": [("bankruptcy", 0.3), ("credit_card_debt", 0.3)],
    "lawsuit": [("legal_judgment", 0.3)],
    "rsu_cliff": [("tax_bill", 0.4), ("trading_blackout", 0.3)],
    "retirement": [("pension_buyout_offer", 0.3)],
    "desk_shutdown": [("regulatory_ban", 0.1)],
}
DEPOSITS = {"inheritance": "amount", "lottery_win": "amount_after_tax", "lawsuit_settlement": "amount",
            "business_sale": "proceeds", "death_of_spouse": "life_insurance_payout"}
FS_TICKERS = list(FS_STOCKS)


def eligible(t: str, p: dict) -> bool:
    a = p["age"]
    if t in FS_ONLY and not p["fs"]:
        return False
    if t in NEEDS_EMPLOYER and not p["employer"]:
        return False
    if t == "disability" and p["retired"]:
        return False
    if t in {"layoff", "furlough", "desk_shutdown", "firm_collapse", "pay_cut", "bonus_cut", "sabbatical", "rsu_cliff",
             "job_change", "regulatory_ban", "early_retirement_offer", "deferred_comp_clawback"} and p["retired"]:
        return False
    rules = {"disability": a <= 66, "child": a <= 45, "marriage": a <= 62 and not p["married"], "divorce": p["married"],
             "death_of_spouse": p["married"] and a >= 40, "retirement": a >= 55 and not p["retired"],
             "pension_buyout_offer": a >= 45, "early_retirement_offer": a >= 50, "tuition_due": 40 <= a <= 65,
             "adult_child_moves_back": a >= 45, "parent_long_term_care": 35 <= a <= 68, "home_purchase": a <= 60,
             "student_loan_restart": a <= 50, "special_needs_diagnosis": a <= 50}
    return rules.get(t, True)


def sample_plan(rng: random.Random, p: dict) -> tuple[str, list[str]]:
    r = rng.random()
    if r < S["p_no_events"]:
        return "no_events", []
    if r < S["p_no_events"] + S["p_noise_only"]:
        pool = NOISE_GENERAL + (NOISE_FS if p["fs"] else [])
        pool = [t for t in pool if eligible(t, p)]
        return "noise_only", rng.sample(pool, rng.choice([1, 1, 2]))
    if p["fs"] and p["employer"] in FS_STOCKS and rng.random() < 0.25:
        # Lehman-style crisis: the firm fails in a crash, and life does not pause for it
        extra = [t for t in ("parent_long_term_care", "margin_call", "medical_bill", "tax_bill", "credit_card_debt",
                             "home_purchase", "child", "divorce") if eligible(t, p)]
        return "fs_crisis", ["firm_collapse", "market_drop"] + rng.sample(extra, rng.choice([0, 1, 1, 2]))
    k = rng.choices([1, 2, 3], weights=[4, 4, 2])[0]
    types: list[str] = []
    cand = [t for t in POOL if eligible(t, p)]
    w = [POOL[t] * (2.0 if p["fs"] and t in FS_ONLY else 1.0) for t in cand]
    while len(types) < k:
        t = rng.choices(cand, weights=w)[0]
        if t not in types:
            types.append(t)
    i = 0
    while i < len(types):  # cascades
        for nxt, pr in CASCADE.get(types[i], []):
            if nxt not in types and eligible(nxt, p) and rng.random() < pr and len(types) < S["max_events"]:
                types.append(nxt)
        i += 1
    if "firm_collapse" in types and "layoff" in types:
        types.remove("layoff")      # the collapse already ends the job
    return "events", types


def world_for(rng: random.Random, seed: int, types: list[str]) -> tuple[dict, str | None]:
    if "firm_collapse" in types:
        anchor = rng.choice(["gfc_2009", "gfc_2009", "dotcom_2002"])
    elif "market_drop" in types:
        anchor = rng.choice(list(CFG["market"]["drop_anchors"]))
    else:
        anchor = None
    return mm.build_world(seed, CFG, anchor), anchor


def make_case(rng: random.Random, cid: str, idx: int) -> dict:
    fs = rng.random() < S["fs_share"]
    age = rng.choices([rng.randint(22, 34), rng.randint(35, 54), rng.randint(55, 75)], weights=[3, 4, 3])[0]
    hh = G.sample_household(rng, age, None)
    if fs:
        inc = G.lognorm(rng, S["fs_income_median"], S["fs_income_sigma"])
        hh["income"] = G.round_to(min(max(inc, S["fs_income_clamp"][0]), S["fs_income_clamp"][1]), 500)
        hh["monthly_exp"] = G.round_to(max(hh["income"] * G.expense_ratio(hh["income"]) * rng.uniform(0.85, 1.05) / 12,
                                           3000), 50)
        hh["total"] = G.round_to(hh["total"] * (hh["income"] / 150000) ** 0.8 * rng.uniform(0.8, 1.6), 100)
    employer = None
    if fs and not hh["retired"]:
        employer = rng.choice(FS_TICKERS)
        hh["occupation"] = rng.choice(FS_STOCKS[employer]["roles"])
    elif not hh["retired"] and rng.random() < 0.22:
        employer = rng.choice(list(G.EMPLOYERS))
        hh["occupation"] = rng.choice(G.EMPLOYERS[employer][1])
    p = {"age": age, "fs": fs and not hh["retired"], "employer": employer, "retired": hh["retired"], "married": hh["married"]}
    kind, types = sample_plan(rng, p)
    world, anchor = world_for(rng, 9_000_000 + idx * 31 + rng.randint(0, 9), types)

    lo, hi = G.BANDS[hh["risk"]]
    mid = (lo + hi) / 2
    T, exp = hh["total"], hh["monthly_exp"]
    te = rng.choice(G.LOW_HALF_EQUITY[hh["risk"]] if age >= 55 else G.MODEL_EQUITY[hh["risk"]])
    calm = kind in ("no_events", "noise_only")
    cm = rng.uniform(3.4, 7.0) if calm else min(max(math.exp(rng.gauss(math.log(3.0), 0.5)), 0.6), 12)
    wc = cm * exp / T
    if wc > 0.25:
        raise G.Retry("cash share")
    tc = min(max(round(wc + rng.uniform(-0.02, 0.02), 2), 0.02), 0.25) if (calm or rng.random() < 0.6) else \
        max(rng.choice(CFG["cash_sleeve_choices"]), math.ceil(3.5 * exp / T * 100) / 100)
    tb = round(1 - te - tc, 2)
    if tb < 0 or tc > 0.25:
        raise G.Retry("targets")
    targets = {"equity": te, "bond": tb, "cash": tc}
    mode = "tol" if calm else rng.choices(["tol", "over", "under"], weights=[6, 2.5, 1.5])[0]
    we = te + (rng.uniform(-0.035, 0.035) if mode == "tol" else rng.uniform(0.06, 0.14) if mode == "over"
               else -rng.uniform(0.06, 0.12))
    we = min(we, 0.995 - wc)
    if 1 - we - wc < 0:
        raise G.Retry("bond")
    restricted_planned = bool(set(types) & RX.RESTRICTING)
    singles = {}
    if employer:
        singles[employer] = rng.uniform(0.02, 0.085) if (restricted_planned or calm) else rng.uniform(0.03, 0.30)
    market = json.loads(json.dumps(G.BASE_MARKET))
    if employer in FS_STOCKS:
        market = {k: v for k, v in market.items() if k != "CASH"}
        market[employer] = {"price": FS_STOCKS[employer]["price"], "class": "equity", "single_stock": True}
        market["CASH"] = {"price": 1.0, "class": "cash"}
    intl = 0.0 if rng.random() < 0.2 else rng.uniform(0.15, 0.40)
    positions = G.build_positions(rng, T, we, wc, singles, intl, market)

    # ---- events
    emp_name = (FS_STOCKS.get(employer, {}).get("company") or (G.EMPLOYERS[employer][0] if employer else None))
    dates = sorted(G.rand_date(rng) for _ in types)
    events, notes = [], []
    expenses = exp
    for i, (t, d) in enumerate(zip(types, dates), start=1):
        total_now = sum(q["value"] for q in positions)
        ctx = {"income": hh["income"], "expenses": expenses, "total": total_now, "age": age, "deps": hh["deps"],
               "employer": employer, "employer_name": emp_name, "fs": fs, "date": d, "as_of": AS_OF,
               "married": hh["married"]}
        det = E.CATALOG[t]["make"](rng, ctx)
        if t in DEPOSITS and det.get(DEPOSITS[t]):
            for q in positions:
                if q["symbol"] == "CASH":
                    q["units"] = G.r2(q["units"] + det[DEPOSITS[t]])
                    q["value"] = q["units"]
            if not any(q["symbol"] == "CASH" for q in positions):
                positions.append({"symbol": "CASH", "units": det[DEPOSITS[t]], "value": det[DEPOSITS[t]]})
        elif t == "fraud_loss":
            for q in positions:
                if q["symbol"] == "CASH":
                    lost = min(det["amount_lost"], G.round_to(q["value"] * 0.9, 100))
                    det["amount_lost"] = lost
                    q["units"] = G.r2(q["units"] - lost)
                    q["value"] = q["units"]
            det["taken_from"] = "this account's CASH"
        elif t == "rsu_cliff":
            px = market[employer]["price"]
            add = round(det["vest_value"] / px, 3)
            for q in positions:
                if q["symbol"] == employer:
                    q["units"] = round(q["units"] + add, 3)
                    break
            else:
                positions.insert(-1, {"symbol": employer, "units": add, "value": 0})
            positions = G.reprice(positions, market)
        elif t == "firm_collapse":
            market[employer]["price"] = G.r2(market[employer]["price"] * (1 + det["stock_change_pct"] / 100))
            positions = G.reprice(positions, market)
            notes.append(f"{emp_name} filed for bankruptcy; unvested deferred compensation is an unsecured claim.")
        elif t == "market_drop":
            dd = mm.drop_from_world(world, CFG["market"]["drop_lookback_months"])
            for sym, m in market.items():
                if sym in dd["change"] and sym != "CASH":
                    m["price"] = G.r2(m["price"] * (1 + dd["change"][sym]))
                elif m.get("single_stock") and sym != "CASH" and sym not in dd["change"]:
                    m["price"] = G.r2(m["price"] * (1 + dd["change"]["US_EQ"] * FS_STOCKS.get(sym, {}).get("beta", 1.3)))
            positions = G.reprice(positions, market)
            last = AS_OF - timedelta(days=1)
            d = last - timedelta(days=1)
            det = {"us_equity_change_pct": round(100 * dd["change"]["US_EQ"], 1),
                   "intl_equity_change_pct": round(100 * dd["change"]["INTL_EQ"], 1),
                   "bond_change_pct": round(100 * dd["change"]["BOND"], 1),
                   "peak_date": mm.month_ends(last, dd["months_since_peak"] + 1)[0], "trough_date": d.isoformat(),
                   "historical_analog": CFG["market"]["drop_anchors"][anchor]["label"] if anchor else "correction"}
        elif t == "divorce":
            notes.append("Holdings shown are after the settlement transfer.")
        elif t == "layoff":
            notes.append("Severance paid to an outside checking account.")
        events.append({"id": f"e{i}", "type": t, "date": d.isoformat(), "details": det})
    events.sort(key=lambda e: e["date"])

    w = G.weights_of(positions, market)
    client = {"client_id": cid, "name": f"{rng.choice(G.FIRST)} {rng.choice(G.LAST)}", "age": age, "state": hh["state"],
              "occupation": hh["occupation"], "industry": "financial services" if fs else None,
              "employment_status": "retired" if hh["retired"] else "employed",
              "marital_status": "married" if hh["married"] else "single", "annual_income": hh["income"],
              "monthly_expenses": expenses, "dependents": hh["deps"], "risk_score": hh["risk"],
              "horizon_years": max(65 - age, 0) if age < 65 else max(90 - age, 8),
              "goals": [{"type": "retirement", "target_year": 2026 + max(65 - age, 0)}] if age < 65 else [],
              "targets": targets, "monthly_contribution": 0.0 if hh["retired"] else hh["contrib"]}
    if client["industry"] is None:
        del client["industry"]
    if employer:
        client["employer"] = f"{emp_name} ({employer})"
    if notes:
        client["notes"] = " ".join(notes)
    # ---- feasibility / archetype constraints
    total = w["total"]
    req = RX.required_cash(client, events, AS_OF.isoformat())
    if req * 1.03 / total > 1 - lo - 0.03:
        raise G.Retry("cash floor vs risk band")
    restricted = RX.restricted_symbols(events)
    if any(w["by_symbol"].get(s, 0) > 0.095 for s in restricted):
        raise G.Retry("restricted symbol above cap")
    if calm:
        if any(abs(w["by_class"][k] - targets[k]) > 0.045 for k in targets):
            raise G.Retry("not in tolerance")
        eq, cmo = w["by_class"]["equity"], pf.positions({"positions": positions})["CASH"] / expenses
        if not (lo + 0.01 <= eq <= hi - 0.01) or cmo < 3.2 or max(w["single_stocks"].values(), default=0) > 0.09:
            raise G.Retry("not compliant")
        if age >= 55 and eq > mid - 0.005:
            raise G.Retry("glidepath")
    prices_now = {s: m["price"] for s, m in market.items()}
    fworld = dict(world)
    for tkr in market:
        if tkr in FS_STOCKS and tkr not in world["hist"][0]:  # simulate FS ticker paths (beta + noise)
            fs_rng = random.Random(zlib.crc32(f"{cid}/{tkr}".encode()))
            ss = FS_STOCKS[tkr]
            for part in ("hist", "fut"):
                for r in fworld[part]:
                    r[tkr] = max(-0.95, r["CASH"] + ss["beta"] * (r["US_EQ"] - r["CASH"])
                                 + fs_rng.gauss(0, ss["idio_vol_annual"] / math.sqrt(12)))
    mjson = {"as_of": AS_OF.isoformat(), "symbols": market, "history": mm.history_block(fworld, prices_now, AS_OF.isoformat())}
    return {"client": client, "holdings": {"as_of": AS_OF.isoformat(), "positions": positions}, "market": mjson,
            "events": {"events": events}, "future": mm.future_block(fworld, prices_now, AS_OF.isoformat(), cid),
            "meta": {"kind": kind, "types": types, "fs": fs, "anchor": anchor, "window": world["window"]}}


def write(case: dict, d: Path, hd: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    hd.mkdir(parents=True, exist_ok=True)
    for f in ("client", "holdings", "market", "events"):
        (d / f"{f}.json").write_text(json.dumps(case[f], indent=2) + "\n", encoding="utf-8")
    (hd / "future.json").write_text(json.dumps(case["future"], indent=2) + "\n", encoding="utf-8")


def generate() -> dict:
    for p in (OUT, HOLD):
        if p.exists():
            shutil.rmtree(p)
    manifest = {}
    for idx in range(1, S["n_cases"] + 1):
        cid = f"s-{idx:03d}"
        rng = random.Random(S["seed"] * 10_000 + idx)
        for attempt in range(4000):
            try:
                case = make_case(rng, cid, idx)
            except G.Retry:
                continue
            write(case, OUT / cid, HOLD / cid)
            c = oracle.load_case(OUT / cid)
            try:
                r = oracle.score(c, oracle.recommend(c))
            except ValueError:
                continue
            if r["passed"] and r["score"] >= 0.9999:
                break
        else:
            raise RuntimeError(f"{cid}: no solvable draw")
        manifest[cid] = {**case["meta"], "draws": attempt + 1}
    (ROOT / "cases" / "stress_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def check() -> dict:
    manifest = json.loads((ROOT / "cases" / "stress_manifest.json").read_text(encoding="utf-8"))
    fam = defaultdict(lambda: Counter())
    rows, unsolved = [], 0
    for cid in sorted(manifest):
        d = OUT / cid
        c = oracle.load_case(d)
        rec = oracle.recommend(c)
        o = oracle.score(c, rec)
        nv, dn = oracle.score(c, oracle.naive(c)), oracle.score(c, oracle.do_nothing(c))
        ok = o["passed"] and o["score"] >= 0.9999
        unsolved += not ok
        bo, bn = backtest(d, rec), backtest(d, oracle.naive(c))
        types = sorted({e["type"] for e in c["events"]})
        fams = sorted({E.CATALOG[t]["family"] for t in types}) or ["none"]
        if manifest[cid]["kind"] == "noise_only":
            fams = ["noise_only"]
        if c["client"].get("industry") == "financial services":
            fams = fams + ["(fs employee)"]
        for f in fams:
            fam[f]["n"] += 1
            fam[f]["naive"] += nv["passed"]
            fam[f]["nothing"] += dn["passed"]
            fam[f]["oracle_ef_breach"] += bo["emergency_fund_breached"]
            fam[f]["naive_ef_breach"] += bn["emergency_fund_breached"]
        rows.append({"case_id": cid, "types": types, "oracle_score": o["score"], "solved": ok,
                     "naive_passed": nv["passed"], "naive_violations": [v["rule"] for v in nv["violations"]],
                     "do_nothing_passed": dn["passed"], "oracle_fwd": bo["forward_return"], "naive_fwd": bn["forward_return"]})
        if not ok:
            print("UNSOLVED", cid, o["violations"])
    n = len(rows)
    print(f"stress: {n} cases, oracle solvable {n - unsolved}/{n}, naive pass {sum(r['naive_passed'] for r in rows) / n:.2f}, "
          f"do-nothing pass {sum(r['do_nothing_passed'] for r in rows) / n:.2f}")
    print(f"{'family':<16}{'n':>5}{'naive':>8}{'nothing':>9}{'EF breach naive/oracle':>24}")
    for f in sorted(fam, key=lambda k: -fam[k]["n"]):
        v = fam[f]
        print(f"{f:<16}{v['n']:>5}{v['naive'] / v['n']:>8.2f}{v['nothing'] / v['n']:>9.2f}{v['naive_ef_breach']:>14}/{v['oracle_ef_breach']}")
    viol = Counter(v for r in rows for v in r["naive_violations"])
    print("naive violations by rule:", dict(viol.most_common()))
    rep = {"n": n, "unsolved": unsolved, "families": {k: dict(v) for k, v in fam.items()}, "naive_violations": dict(viol),
           "cases": rows}
    (ROOT / "stress_report.json").write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if not a.check:
        generate()
    return 1 if check()["unsolved"] else 0


if __name__ == "__main__":
    sys.exit(main())
