"""Synthetic client-case generator for ballast.

Writes scenarios/cases/{practice,test,regression,drift}/<case_id>/{client,holdings,market,events}.json,
the held-out forward window scenarios/holdout/<set>/<case_id>/future.json (never inside a case dir),
and scenarios/cases/manifest.json (archetype + tags per case; never copied into an agent's case dir).
All numeric calibration comes from scenarios/config.yaml; market paths come from market_model.py.

Deterministic: every case draws from random.Random(SET_SEED * 1000 + index). Stdlib + PyYAML.
Distributions are calibrated to public US data; see scenarios/SOURCES.md for every parameter.
All clients are synthetic (random first/last name pairs, invented employers and tickers).

    python scenarios/generate.py            # (re)write all four sets
    python scenarios/generate.py --dry-run  # validate only, print summary
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
import portfolio as pf  # noqa: E402  (shared post-trade math: same numbers as agent + checker)

import market_model as mm  # noqa: E402  (market history + held-out window)

# ---------------------------------------------------------------- calibration: everything numeric lives in config.yaml
CFG = mm.load_config()
AS_OF = CFG["as_of"]
REVIEW_WINDOW = tuple(date.fromisoformat(x) for x in CFG["review_window"])
SEEDS = CFG["seeds"]
BASE_MARKET = {s: {"price": a["price"], "class": a["class"]} for s, a in CFG["assets"].items() if s != "CASH"}
BASE_MARKET.update({t: {"price": v["price"], "class": "equity", "single_stock": True}
                    for t, v in CFG["single_stocks"].items()})
BASE_MARKET["CASH"] = {"price": CFG["assets"]["CASH"]["price"], "class": "cash"}
EMPLOYERS = {t: (v["company"], v["roles"]) for t, v in CFG["single_stocks"].items()}


def _int_keys(d: dict) -> dict:
    return {int(k): v for k, v in d.items()}


def _age_keys(d: dict) -> dict:
    return {tuple(int(x) for x in str(k).split("-")): v for k, v in d.items()}


BANDS = {int(k): tuple(v) for k, v in CFG["risk_bands"].items()}
MODEL_EQUITY = _int_keys(CFG["model_equity"])
LOW_HALF_EQUITY = _int_keys(CFG["low_half_equity"])   # <= band midpoint
STALE_EQUITY = _int_keys(CFG["stale_equity"])         # > band midpoint
HH, EV = CFG["household"], CFG["events"]
SCF_MEDIAN_INCOME_K = _age_keys(HH["scf_median_income_k"])
SCF_MEDIAN_RETIRE_K = _age_keys(HH["scf_median_retire_k"])
CE_QUINTILES = [tuple(x) for x in HH["ce_quintiles"]]
RISK_WEIGHTS = _age_keys(HH["risk_weights"])

FIRST = ["Maya", "Jordan", "Priya", "Marcus", "Elena", "Tyrone", "Hannah", "Diego", "Aisha", "Connor", "Mei",
         "Rafael", "Brianna", "Samuel", "Nadia", "Trevor", "Leila", "Owen", "Camila", "Darnell", "Ingrid",
         "Kenji", "Rosa", "Malik", "Abigail", "Hector", "Tessa", "Arjun", "Gloria", "Wesley", "Yasmin", "Grant",
         "Lucia", "Desmond", "Fiona", "Omar", "Natalie", "Victor", "Imani", "Patrick"]
LAST = ["Okafor", "Lindqvist", "Ramirez", "Chen", "Whitaker", "Patel", "Novak", "Delgado", "Brennan", "Haddad",
        "Sorensen", "Takahashi", "Mbeki", "Castellano", "Fairbanks", "Kowalski", "Abernathy", "Nguyen",
        "Oyelaran", "Pemberton", "Varga", "Quintero", "Holloway", "Rasmussen", "Iyer", "Marchetti", "Dubois",
        "Sandoval", "Achebe", "Lundgren", "Ferreira", "Gallagher", "Yilmaz", "Beaumont", "Mendoza", "Strand"]
KIDS = ["Theo", "Ava", "Mateo", "Zara", "Eli", "Nora", "Kai", "Iris", "Leo", "Maeve", "Ezra", "Luna"]
STATES = [("CA", 39), ("TX", 30), ("FL", 22), ("NY", 20), ("PA", 13), ("IL", 13), ("OH", 12), ("GA", 11),
          ("NC", 11), ("MI", 10), ("NJ", 9), ("VA", 9), ("WA", 8), ("AZ", 7), ("MA", 7), ("TN", 7),
          ("CO", 6), ("MN", 6), ("OR", 4), ("UT", 3)]
OCCUPATIONS = [  # (min income, max income, title)
    (40e3, 75e3, "dental hygienist"), (40e3, 70e3, "elementary school teacher"), (45e3, 80e3, "HVAC technician"),
    (45e3, 85e3, "paralegal"), (50e3, 90e3, "retail store manager"), (65e3, 120e3, "registered nurse"),
    (60e3, 120e3, "accountant"), (70e3, 130e3, "civil engineer"), (70e3, 125e3, "police sergeant"),
    (75e3, 140e3, "UX designer"), (70e3, 135e3, "logistics manager"), (110e3, 180e3, "physician assistant"),
    (120e3, 260e3, "software engineer"), (120e3, 230e3, "product manager"), (130e3, 320e3, "attorney"),
    (120e3, 210e3, "pharmacist"), (130e3, 300e3, "sales director"), (110e3, 220e3, "data scientist"),
    (200e3, 450e3, "anesthesiologist"), (90e3, 160e3, "electrical engineer"),
]
NEW_EMPLOYERS = ["Brightwater Health", "Corvane Analytics", "Larkspur Bank", "Tidewell Energy", "Orchard Labs",
                 "Halvorsen Group", "Mesa Ridge Schools", "Quillon Software", "Redfern Logistics"]
OLD_EMPLOYERS = ["Pinebrook Media", "Stellan Retail", "Alder & Finch", "Vectrix Systems", "Copperline Mfg",
                 "Bluefin Insurance", "Ridgeway Hospitality"]


# ---------------------------------------------------------------- helpers
def bucket(table: dict, age: int):
    for (a, b), v in table.items():
        if a <= age <= b:
            return v
    raise KeyError(age)


def r2(x: float) -> float:
    return round(x + 0.0, 2)


def round_to(x: float, step: float) -> float:
    return round(x / step) * step


def rand_date(rng: random.Random, lo: date = REVIEW_WINDOW[0], hi: date = REVIEW_WINDOW[1]) -> date:
    return lo + timedelta(days=rng.randint(0, (hi - lo).days))


def expense_ratio(income: float) -> float:
    """BLS CE spending/income ratio, log-linearly interpolated between quintile means."""
    pts = [(math.log(i), e / i) for i, e in CE_QUINTILES]
    x = math.log(max(income, 1))
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1] * (math.exp(pts[-1][0]) / income) ** 0.35  # flatten above top-quintile mean


def lognorm(rng: random.Random, median: float, sigma: float) -> float:
    return median * math.exp(rng.gauss(0, sigma))


class Retry(Exception):
    pass


# ---------------------------------------------------------------- household sampling
def sample_household(rng: random.Random, age: int, risk: int | None) -> dict:
    retired = age >= 66
    med_inc = bucket(SCF_MEDIAN_INCOME_K, age) * 1000 * HH["inflate_2022_2026"] * HH["investor_income_mult"]
    income = min(max(lognorm(rng, med_inc, HH["income_sigma"]), HH["income_clamp"][0]), HH["income_clamp"][1])
    income = round_to(income, 500)
    ratio = expense_ratio(income) * rng.uniform(*HH["expense_noise"])
    monthly_exp = round_to(max(income * ratio / 12, HH["min_monthly_expenses"]), 50)
    med_T = bucket(SCF_MEDIAN_RETIRE_K, age) * 1000 * HH["inflate_2022_2026"] * HH["taxable_mult"]  # + taxable
    total = lognorm(rng, med_T * (income / med_inc) ** 0.9, HH["total_sigma"])
    total = round_to(min(max(total, HH["total_clamp"][0]), HH["total_clamp"][1]), 100)
    if risk is None:
        risk = rng.choices([1, 2, 3, 4, 5], weights=bucket(RISK_WEIGHTS, age))[0]
    if retired:
        occ = "retired " + rng.choice([o[2] for o in OCCUPATIONS[:12]])
        contrib = 0.0
    else:
        fits = [o[2] for o in OCCUPATIONS if o[0] <= income <= o[1]] or [OCCUPATIONS[-2][2]]
        occ = rng.choice(fits)
        contrib = round_to(income * rng.uniform(*HH["contribution_rate"]) / 12, 50)  # Vanguard HAS total deferral ~12%
    married = rng.random() < (0.35 if age < 30 else 0.6)
    deps = 0 if age < 27 else rng.choices([0, 1, 2, 3], weights=[4, 3, 3, 1])[0] if age < 60 else rng.choice([0, 0, 1])
    return {"age": age, "income": income, "monthly_exp": monthly_exp, "total": total, "risk": risk,
            "retired": retired, "occupation": occ, "contrib": contrib, "married": married, "deps": deps,
            "name": f"{rng.choice(FIRST)} {rng.choice(LAST)}",
            "state": rng.choices([s for s, _ in STATES], weights=[w for _, w in STATES])[0]}


# ---------------------------------------------------------------- case construction
def build_positions(rng, total, w_eq, w_cash, singles: dict[str, float], intl_share: float, market) -> list[dict]:
    """Holdings whose class weights are (w_eq, 1-w_eq-w_cash, w_cash); singles = {ticker: weight}."""
    eq_usd = w_eq * total
    single_usd = {s: w * total for s, w in singles.items()}
    fund_eq = eq_usd - sum(single_usd.values())
    if fund_eq < 0:
        raise Retry("singles exceed equity")
    vals = {"US_EQ": fund_eq * (1 - intl_share), "INTL_EQ": fund_eq * intl_share,
            "BOND": (1 - w_eq - w_cash) * total, **single_usd, "CASH": w_cash * total}
    pos = []
    for sym in ["US_EQ", "INTL_EQ", "BOND", *singles, "CASH"]:
        v = vals[sym]
        if v < 1:
            continue
        price = market[sym]["price"]
        units = round(v / price, 3) if sym != "CASH" else round(v, 2)
        pos.append({"symbol": sym, "units": units, "value": r2(units * price)})
    return pos


def weights_of(positions, market) -> dict:
    return pf.weights(pf.positions({"positions": positions}), {"symbols": market})


def reprice(positions, market) -> list[dict]:
    return [{"symbol": p["symbol"], "units": p["units"], "value": r2(p["units"] * market[p["symbol"]]["price"])}
            for p in positions]


def make_case(rng: random.Random, cid: str, arch: dict, world: dict) -> dict:
    """Build one case for archetype `arch`. Raises Retry if the draw misses the archetype's constraints."""
    age = rng.randint(*arch.get("age", (27, 54)))
    hh = sample_household(rng, age, arch.get("risk"))
    hh["total"] = round_to(hh["total"] * arch.get("total_mult", 1.0), 100)
    lo, hi = BANDS[hh["risk"]]
    mid = (lo + hi) / 2
    events_wanted: list[str] = arch.get("events", [])
    T, exp = hh["total"], hh["monthly_exp"]

    # targets (client's model portfolio, consistent with the risk band)
    if age >= 55:
        te = rng.choice(STALE_EQUITY[hh["risk"]] if arch.get("stale_targets") else LOW_HALF_EQUITY[hh["risk"]])
    else:
        te = rng.choice(MODEL_EQUITY[hh["risk"]])
    cm = rng.uniform(*arch.get("cash_months", (3.4, 6.5)))
    wc = cm * exp / T
    if wc > 0.22:
        raise Retry("cash share unrealistic for portfolio size")
    if arch.get("drift") == "tol":
        tc = min(max(round(wc + rng.uniform(-0.02, 0.02), 2), 0.02), 0.20)
    else:
        # model-portfolio cash sleeve: a round number that covers ~3.5 months of expenses (advisor convention)
        tc = max(rng.choice(CFG["cash_sleeve_choices"]), math.ceil(CFG["cash_sleeve_min_months"] * exp / T * 100) / 100)
        if tc > 0.20:
            raise Retry("cash sleeve too large")
    tb = round(1 - te - tc, 2)
    if tb < 0:
        raise Retry("no room for bonds")
    targets = {"equity": te, "bond": tb, "cash": tc}

    # actual equity weight
    drift = arch.get("drift", "tol")
    if drift == "tol":
        we = te + rng.uniform(-0.035, 0.035)
    elif drift == "over":
        we = te + rng.uniform(0.065, 0.13)     # equities ran ahead of bonds since the last rebalance
    elif drift == "under":
        we = te - rng.uniform(0.065, 0.12)
    else:
        raise ValueError(drift)
    we = min(we, 0.995 - wc)
    if 1 - we - wc < 0:
        raise Retry("negative bond weight")

    singles: dict[str, float] = {}
    employer_tkr = None
    if arch.get("single"):
        employer_tkr = rng.choice(list(EMPLOYERS))
        singles[employer_tkr] = rng.uniform(*arch["single"])
    elif rng.random() < arch.get("p_small_single", HH["p_small_single"]):
        singles[rng.choice(list(EMPLOYERS))] = rng.uniform(*HH["small_single_weight"])  # "fun money" stock pick
    intl = 0.0 if rng.random() < HH["p_no_intl"] else rng.uniform(*HH["intl_share"])

    market = json.loads(json.dumps(BASE_MARKET))
    positions = build_positions(rng, T, we, wc, singles, intl, market)

    # ------------------------------------------------ events
    events: list[dict] = []
    goals = [{"type": "retirement", "target_year": 2026 + max(65 - age, 0)}] if age < 65 else []
    if hh["deps"] and age < 50 and rng.random() < 0.6:
        goals.append({"type": "education", "target_year": 2026 + rng.randint(4, 15)})
    if age < 36 and rng.random() < 0.4:
        goals.append({"type": "home_purchase", "target_year": 2026 + rng.randint(2, 6)})
    notes: list[str] = []
    employment = "retired" if hh["retired"] else "employed"
    marital = "married" if hh["married"] else "single"
    occupation = hh["occupation"]
    employer = None
    if employer_tkr:
        employer = f"{EMPLOYERS[employer_tkr][0]} ({employer_tkr})"
        occupation = rng.choice(EMPLOYERS[employer_tkr][1])
        notes.append(f"{employer_tkr} shares accumulated from RSU vesting and the ESPP.")
    income = hh["income"]
    expenses = exp
    dates = sorted(rand_date(rng) for _ in events_wanted)
    if len(set(dates)) < len(dates):
        raise Retry("two events on the same day")
    for i, (etype, d) in enumerate(zip(events_wanted, dates), start=1):
        eid = f"e{i}"
        det: dict = {}
        if etype == "layoff":
            L = EV["layoff"]
            tenure = rng.randint(*L["tenure_years"])
            weeks = min(max(L["severance_weeks_clamp"][0], round(tenure * rng.choice(L["weeks_per_year_choices"]))),
                        L["severance_weeks_clamp"][1])
            det = {"severance": round_to(income / 52 * weeks, 100), "severance_weeks": weeks,
                   "tenure_years": tenure, "employer": employer or rng.choice(OLD_EMPLOYERS),
                   "last_day": d.isoformat(),
                   "cobra_monthly_premium": rng.choice(L["cobra_family"]) if hh["deps"] or hh["married"]
                   else rng.choice(L["cobra_single"])}
            employment = "unemployed"
            notes.append(f"Laid off {d:%b %d}; severance paid as a lump sum to an outside checking account.")
        elif etype == "job_change":
            if arch.get("pay_cut"):
                new_inc = round_to(income * rng.uniform(*EV["job_change"]["pay_cut"]), 500)
                notes.append("Took a lower-paying role with a shorter commute and better hours.")
            else:
                new_inc = round_to(income * rng.uniform(*EV["job_change"]["raise"]), 500)
            det = {"new_income": new_inc, "previous_income": income, "new_employer": rng.choice(NEW_EMPLOYERS),
                   "start_date": d.isoformat(), "employer_401k_match_pct": rng.choice(EV["job_change"]["match_pct_choices"])}
            if rng.random() < EV["job_change"]["p_signing_bonus"] and not arch.get("pay_cut"):
                det["signing_bonus"] = round_to(new_inc * rng.uniform(*EV["job_change"]["signing_bonus"]), 500)
        elif etype == "marriage":
            sp_age = max(23, age + rng.randint(-4, 4))
            det = {"spouse_name": f"{rng.choice(FIRST)} {rng.choice(LAST)}", "spouse_age": sp_age,
                   "spouse_annual_income": round_to(lognorm(rng, EV["marriage"]["spouse_income_median"], EV["marriage"]["spouse_income_sigma"]), 1000),
                   "spouse_has_separate_accounts": True}
            marital = "married"
        elif etype == "child":
            det = {"child_name": rng.choice(KIDS), "birth_date": d.isoformat(), "adoption": rng.random() < EV["child"]["p_adoption"]}
            notes.append("Newborn at home; one parent on unpaid leave until January.")
        elif etype == "inheritance":
            amt = round_to(rng.uniform(*arch.get("inherit_x", EV["inheritance"]["default_multiple"])) * T, 1000)
            det = {"amount": amt, "source": rng.choice(["estate of a parent", "estate of a grandparent",
                                                        "estate of an aunt"]),
                   "form": "cash", "deposited_to": "CASH", "deposit_date": d.isoformat()}
            for p in positions:
                if p["symbol"] == "CASH":
                    p["units"] = r2(p["units"] + amt)
                    p["value"] = p["units"]
            notes.append("Inheritance proceeds were deposited into the brokerage cash sweep.")
        elif etype == "divorce":
            # holdings already reflect the post-settlement split; household now runs on one income
            transferred = round_to(T * rng.uniform(*EV["divorce"]["transfer_ratio"]), 1000)
            det = {"final_date": d.isoformat(), "assets_transferred_usd": transferred,
                   "custody": "shared" if hh["deps"] else None,
                   "child_support_monthly": round_to(rng.uniform(*EV["divorce"]["child_support"]), 50) if hh["deps"] else 0}
            expenses = round_to(exp * rng.uniform(*EV["divorce"]["expense_ratio"]), 50)   # smaller household, but a second home
            marital = "divorced"
            notes.append("Holdings shown are after the court-ordered transfer to the former spouse.")
        elif etype == "market_drop":
            # real peak-to-trough path from the replayed window (history ends at the anchor trough)
            dd = mm.drop_from_world(world, CFG["market"]["drop_lookback_months"])
            for sym, m in market.items():
                if sym != "CASH":
                    m["price"] = r2(m["price"] * (1 + dd["change"][sym]))
            positions = reprice(positions, market)
            last = date.fromisoformat(AS_OF) - timedelta(days=1)
            d = last - timedelta(days=1)
            det = {"us_equity_change_pct": round(100 * dd["change"]["US_EQ"], 1),
                   "intl_equity_change_pct": round(100 * dd["change"]["INTL_EQ"], 1),
                   "bond_change_pct": round(100 * dd["change"]["BOND"], 1),
                   "peak_date": mm.month_ends(last, dd["months_since_peak"] + 1)[0],
                   "trough_date": d.isoformat(),
                   "historical_analog": CFG["market"]["drop_anchors"][arch["drop_anchor"]]["label"]}
        events.append({"id": eid, "type": etype, "date": d.isoformat(), "details": det})

    w = weights_of(positions, market)
    total_now = w["total"]
    cash_now = pf.positions({"positions": positions}).get("CASH", 0.0)

    # ------------------------------------------------ archetype constraints (resample if missed)
    eq = w["by_class"]["equity"]
    cmo = cash_now / expenses
    max_single = max(w["single_stocks"].values(), default=0.0)
    need_m = 6 if "layoff" in events_wanted else 3
    cons = arch.get("check", lambda **k: True)
    if not cons(eq=eq, lo=lo, hi=hi, mid=mid, cmo=cmo, max_single=max_single, w=w, targets=targets, age=age):
        raise Retry("archetype constraint")
    # feasibility: some allocation passes every rule (cash need fits beside the minimum equity)
    if need_m * expenses * 1.03 / total_now > 1 - lo - 0.02:
        raise Retry("emergency fund cannot coexist with risk band")
    if arch.get("no_churn"):
        # a true no_churn case: in tolerance and already compliant (incl. glidepath for 55+)
        if any(abs(w["by_class"][k] - targets[k]) > 0.045 for k in targets):
            raise Retry("not within tolerance")
        if not (lo + 0.01 <= eq <= hi - 0.01) or cmo < 3.2 or max_single > 0.09:
            raise Retry("not compliant")
        if age >= 55 and eq > mid - 0.005:
            raise Retry("glidepath conflict")

    client = {
        "client_id": cid, "name": hh["name"], "age": age, "state": hh["state"], "occupation": occupation,
        "employment_status": employment, "marital_status": marital,
        "annual_income": income, "monthly_expenses": expenses, "dependents": hh["deps"],
        "risk_score": hh["risk"], "horizon_years": max(65 - age, 0) if age < 65 else max(90 - age, 8),
        "goals": goals, "targets": targets, "monthly_contribution": hh["contrib"],
    }
    if employer:
        client["employer"] = employer
    if arch.get("stale_targets"):
        notes.append("Model portfolio last revisited in 2019.")
    if notes:
        client["notes"] = " ".join(notes)
    holdings = {"as_of": AS_OF, "positions": positions}
    prices_now = {sym: m["price"] for sym, m in market.items()}
    market_json = {"as_of": AS_OF, "symbols": market, "history": mm.history_block(world, prices_now, AS_OF)}
    events.sort(key=lambda e: e["date"])
    return {"client": client, "holdings": holdings, "market": market_json, "events": {"events": events},
            "future": mm.future_block(world, prices_now, AS_OF, cid)}


# ---------------------------------------------------------------- archetypes
def A(name, **kw):
    kw["name"] = name
    return kw


# constraint helpers
def eq_out_of_tol(eq, targets, **_):
    return abs(eq - targets["equity"]) > 0.06


def cash_short(cmo, **_):
    return 1.2 <= cmo <= 2.6


STEADY = A("steady", drift="tol", events=[], no_churn=True)
STEADY_AGGR = A("steady_aggressive", drift="tol", events=[], no_churn=True, risk=5, age=(26, 40))
STEADY_55 = A("steady_55plus", drift="tol", events=[], age=(55, 70), no_churn=True)
DRIFTED = A("drifted_no_event", drift="over", events=[], check=lambda **k: eq_out_of_tol(**k))
CASH_SHORT = A("cash_short_no_event", drift="tol", events=[], cash_months=(1.3, 2.5), p_small_single=0.0,
               check=lambda **k: cash_short(**k) and abs(k["eq"] - k["targets"]["equity"]) <= 0.045)
LAYOFF = A("layoff", events=["layoff"], drift="tol", cash_months=(1.2, 4.5))
LAYOFF_CONC = A("layoff_concentration", events=["layoff"], drift="tol", cash_months=(1.5, 4.5),
                single=(0.14, 0.30), check=lambda **k: k["max_single"] > 0.12)
JOB_UP = A("job_change_raise", events=["job_change"], drift="tol")
JOB_UP_DRIFT = A("job_change_raise_drifted", events=["job_change"], drift="over",
                 check=lambda **k: eq_out_of_tol(**k))
JOB_UP_AGGR = A("job_change_raise", events=["job_change"], drift="tol", risk=5, age=(26, 38))
JOB_DOWN = A("job_change_paycut", events=["job_change"], drift="tol", pay_cut=True)
MARRIAGE = A("marriage", events=["marriage"], drift="tol", age=(26, 42))
CHILD = A("child", events=["child"], drift="tol", age=(27, 41))
GLIDE_STALE = A("age55_stale_targets", events=[], drift="over", stale_targets=True, age=(55, 66),
                check=lambda **k: k["eq"] > k["mid"] + 0.03 and eq_out_of_tol(**k))
GLIDE_CONC = A("age55_concentration", events=[], drift="tol", stale_targets=True, age=(55, 64),
               single=(0.12, 0.22), check=lambda **k: k["max_single"] > 0.115)
TWO_JOB_CHILD = A("job_change+child", events=["job_change", "child"], drift="tol", age=(28, 40))
TWO_MARRIAGE_JOB = A("marriage+job_change", events=["marriage", "job_change"], drift="tol", age=(27, 40))
TWO_LAYOFF_CHILD = A("layoff+child", events=["layoff", "child"], drift="tol", age=(29, 41), cash_months=(1.5, 4.0))
CONC_ONLY = A("concentration_no_event", events=[], drift="tol", single=(0.18, 0.32),
              check=lambda **k: k["max_single"] > 0.16)

MIX = [STEADY, STEADY, STEADY_AGGR, STEADY_55, DRIFTED, CASH_SHORT,              # 6 no-event (30%)
       LAYOFF, LAYOFF, LAYOFF_CONC, JOB_UP, JOB_UP_DRIFT, JOB_DOWN,
       MARRIAGE, MARRIAGE, CHILD, CHILD, GLIDE_STALE, GLIDE_CONC,
       TWO_JOB_CHILD, TWO_LAYOFF_CHILD]
MIX_TEST = [STEADY, STEADY_AGGR, STEADY_55, STEADY_55, DRIFTED, CASH_SHORT,
            LAYOFF, LAYOFF_CONC, LAYOFF_CONC, JOB_UP, JOB_UP_AGGR, JOB_DOWN,
            MARRIAGE, CHILD, CHILD, GLIDE_STALE, GLIDE_CONC,
            TWO_JOB_CHILD, TWO_MARRIAGE_JOB, TWO_LAYOFF_CHILD]

# regression: clear-cut, wide margins, a correct agent always passes
REGRESSION = [
    A("reg_steady", drift="tol", events=[], no_churn=True, p_small_single=0.0, cash_months=(4.5, 6.0)),
    A("reg_steady_55plus", drift="tol", events=[], no_churn=True, age=(58, 68), p_small_single=0.0, cash_months=(4.5, 6.0)),
    A("reg_layoff_cash_thin", events=["layoff"], drift="tol", cash_months=(0.8, 1.6), p_small_single=0.0),
    A("reg_concentration", events=[], drift="tol", single=(0.25, 0.35), check=lambda **k: k["max_single"] > 0.22),
    A("reg_band_breach", events=[], drift="over", risk=2, check=lambda **k: k["eq"] > k["hi"] + 0.04),
    A("reg_child", events=["child"], drift="tol", age=(28, 38), cash_months=(4.0, 6.0), p_small_single=0.0),
    A("reg_marriage", events=["marriage"], drift="tol", age=(27, 38), cash_months=(4.0, 6.0), p_small_single=0.0),
    A("reg_job_raise", events=["job_change"], drift="tol", cash_months=(4.0, 6.0), p_small_single=0.0),
    A("reg_cash_short", events=[], drift="tol", cash_months=(0.8, 1.5), p_small_single=0.0,
      check=lambda **k: k["cmo"] < 1.6 and abs(k["eq"] - k["targets"]["equity"]) <= 0.045),
    A("reg_layoff_concentration", events=["layoff"], drift="tol", cash_months=(1.0, 2.5), single=(0.2, 0.3),
      check=lambda **k: k["max_single"] > 0.18),
]

DRIFT = [
    A("inheritance", events=["inheritance"], drift="tol", age=(38, 60), inherit_x=(0.35, 0.8),
      check=lambda **k: k["eq"] < k["lo"] - 0.03),
    A("inheritance_large", events=["inheritance"], drift="tol", age=(45, 62), inherit_x=(0.9, 1.4),
      check=lambda **k: k["eq"] < k["lo"] - 0.03),
    A("divorce", events=["divorce"], drift="tol", age=(36, 54), cash_months=(1.2, 2.6),
      check=lambda **k: k["cmo"] < 2.8),
    A("divorce_concentration", events=["divorce"], drift="tol", age=(38, 54), cash_months=(1.5, 2.6),
      single=(0.13, 0.22), check=lambda **k: k["cmo"] < 2.8 and k["max_single"] > 0.12),
    A("market_drop_gfc", events=["market_drop"], drift="tol", drop_anchor="gfc_2009", risk=4,
      check=lambda **k: k["eq"] < k["lo"] - 0.01),
    A("market_drop_2022", events=["market_drop"], drift="tol", drop_anchor="bear_2022", risk=3,
      check=lambda **k: k["eq"] < k["targets"]["equity"] - 0.055),
    A("market_drop+layoff", events=["market_drop", "layoff"], drift="tol", drop_anchor="covid_2020",
      cash_months=(1.5, 3.5), risk=3),
    A("inheritance+child", events=["inheritance", "child"], drift="tol", age=(29, 40), inherit_x=(0.4, 0.9),
      check=lambda **k: k["eq"] < k["lo"] - 0.02),
    A("divorce+job_change", events=["divorce", "job_change"], drift="over", age=(35, 52), cash_months=(1.5, 3.0)),
    A("market_drop+concentration", events=["market_drop"], drift="tol", drop_anchor="dotcom_2002",
      single=(0.2, 0.35), risk=4, check=lambda **k: k["max_single"] > 0.105),
]

SETS = {
    "practice": [(f"c-{i:03d}", a) for i, a in enumerate(MIX, start=1)],
    "test": [(f"c-{i:03d}", a) for i, a in enumerate(MIX_TEST, start=21)],
    "regression": [(f"c-{i:03d}", a) for i, a in enumerate(REGRESSION, start=41)],
    "drift": [(f"d-{i:03d}", a) for i, a in enumerate(DRIFT, start=1)],
}


def shuffled(set_name: str, items: list) -> list:
    """Shuffle archetype order (but keep ids sequential) so case ids carry no archetype signal."""
    arch = [a for _, a in items]
    random.Random(SEEDS[set_name]).shuffle(arch)
    return [(cid, a) for (cid, _), a in zip(items, arch)]


def tags_for(case: dict) -> list[str]:
    c, ev = case["client"], case["events"]["events"]
    w = pf.weights(pf.positions(case["holdings"]), case["market"])
    tags = sorted({e["type"] for e in ev})
    if c["age"] >= 55:
        tags.append("age55+")
    if w["single_stocks"]:
        tags.append("single_stock>10%" if max(w["single_stocks"].values()) > 0.10 else "single_stock")
    if not ev:
        tags.append("no_events")
    return tags


def apply_overrides(case: dict, set_name: str, cid: str, world: dict) -> list[str]:
    """Drop-in data: scenarios/overrides/<set>/<case_id>/{client,holdings,market,events,future}.json
    replaces the generated file (same schema as the case files). A market.json override reprices the
    holdings at the same units (value = units * price stays exact). If the override has no "history",
    the generated history is rescaled to the new prices; future.json is rescaled the same way unless it
    is overridden too. Run oracle.py afterwards: an override can make a case unsolvable."""
    odir = ROOT / "overrides" / set_name / cid
    if not odir.is_dir():
        return []
    done = []
    for fname in ("client", "holdings", "events", "market", "future"):
        f = odir / f"{fname}.json"
        if not f.exists():
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        if fname == "market":
            prices = {s: m["price"] for s, m in data["symbols"].items()}
            data.setdefault("history", mm.history_block(world, prices, data.get("as_of", AS_OF)))
            case["holdings"]["positions"] = reprice(case["holdings"]["positions"], data["symbols"])
            if not (odir / "future.json").exists():
                case["future"] = mm.future_block(world, prices, data.get("as_of", AS_OF), cid)
        case[fname] = data
        done.append(fname)
    return done


def generate(write: bool = True) -> dict:
    out_root = ROOT / "cases"
    manifest = {"generated_as_of": AS_OF, "seeds": SEEDS, "cases": {}}
    for set_name, items in SETS.items():
        set_dir = out_root / set_name
        hold_dir = ROOT / "holdout" / set_name
        for d in (set_dir, hold_dir):
            if write and d.exists():
                shutil.rmtree(d)
        for idx, (cid, arch) in enumerate(shuffled(set_name, items)):
            rng = random.Random(SEEDS[set_name] * 1000 + idx)
            world = mm.build_world(SEEDS[set_name] * 1000 + idx + 7_000_000, CFG, arch.get("drop_anchor"))
            for attempt in range(5000):
                try:
                    case = make_case(rng, cid, arch, world)
                    break
                except Retry:
                    continue
            else:
                raise RuntimeError(f"{cid}: could not satisfy archetype {arch['name']}")
            overridden = apply_overrides(case, set_name, cid, world)
            manifest["cases"][cid] = {"set": set_name, "archetype": arch["name"], "tags": tags_for(case),
                                      "draws": attempt + 1, "market_source": world["source"],
                                      "overrides": overridden}
            if write:
                d = set_dir / cid
                d.mkdir(parents=True, exist_ok=True)
                for fname in ("client", "holdings", "market", "events"):
                    (d / f"{fname}.json").write_text(json.dumps(case[fname], indent=2) + "\n", encoding="utf-8")
                hd = hold_dir / cid
                hd.mkdir(parents=True, exist_ok=True)
                (hd / "future.json").write_text(json.dumps(case["future"], indent=2) + "\n", encoding="utf-8")
    if write:
        (out_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="build and validate without writing files")
    args = ap.parse_args()
    m = generate(write=not args.dry_run)
    by_set: dict[str, int] = {}
    for info in m["cases"].values():
        by_set[info["set"]] = by_set.get(info["set"], 0) + 1
    print(json.dumps(by_set))
    return 0


if __name__ == "__main__":
    sys.exit(main())
