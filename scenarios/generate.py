"""Synthetic client-case generator for ballast.

Writes scenarios/cases/{practice,test,regression,drift}/<case_id>/{client,holdings,market,events}.json
plus scenarios/cases/manifest.json (archetype + tags per case; never copied into an agent's case dir).

Deterministic: every case draws from random.Random(SET_SEED * 1000 + index). Stdlib only.
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

AS_OF = "2026-11-01"
REVIEW_WINDOW = (date(2026, 8, 3), date(2026, 10, 28))  # life events happened since the last review
SEEDS = {"practice": 1001, "test": 2002, "regression": 3003, "drift": 4004}

# ---------------------------------------------------------------- asset universe (SPEC.md)
# Fund prices are illustrative levels of broad index ETFs; single stocks are invented.
BASE_MARKET = {
    "US_EQ":   {"price": 268.40, "class": "equity"},
    "INTL_EQ": {"price": 63.15,  "class": "equity"},
    "BOND":    {"price": 72.80,  "class": "bond"},
    "HLXR":    {"price": 142.30, "class": "equity", "single_stock": True},
    "NMBX":    {"price": 38.75,  "class": "equity", "single_stock": True},
    "KSTL":    {"price": 611.20, "class": "equity", "single_stock": True},
    "CASH":    {"price": 1.0,    "class": "cash"},
}
EMPLOYERS = {  # invented companies behind the invented tickers
    "HLXR": ("Helixar Therapeutics", ["research scientist", "clinical operations manager", "regulatory affairs lead"]),
    "NMBX": ("Nimbex Cloud", ["senior software engineer", "product manager", "solutions architect"]),
    "KSTL": ("Kestrel Freight", ["operations director", "supply-chain analyst", "regional sales manager"]),
}
SINGLE_BETA = {"HLXR": 1.6, "NMBX": 1.4, "KSTL": 1.1}  # drawdown multiplier vs US_EQ (assumption)

BANDS = {1: (0.10, 0.30), 2: (0.30, 0.50), 3: (0.50, 0.70), 4: (0.70, 0.85), 5: (0.85, 1.00)}  # EVAL.md
MODEL_EQUITY = {1: [0.20], 2: [0.40, 0.45], 3: [0.55, 0.60, 0.65], 4: [0.75, 0.80], 5: [0.88, 0.90]}
LOW_HALF_EQUITY = {1: [0.15, 0.20], 2: [0.35, 0.40], 3: [0.55, 0.60], 4: [0.75], 5: [0.90]}   # <= band midpoint
STALE_EQUITY = {1: [0.25], 2: [0.45], 3: [0.65], 4: [0.80], 5: [0.94]}                        # > band midpoint

# ---------------------------------------------------------------- calibration tables (SOURCES.md)
# SCF 2022 median before-tax family income by age of reference person, $k (Fed bulletin Table 1).
SCF_MEDIAN_INCOME_K = {(18, 34): 60.5, (35, 44): 85.9, (45, 54): 91.9, (55, 64): 81.9, (65, 74): 60.9, (75, 99): 49.1}
# SCF 2022 conditional median retirement-account balance by age, $k (secondary summaries of SCF 2022).
SCF_MEDIAN_RETIRE_K = {(18, 34): 18.9, (35, 44): 45.0, (45, 54): 133.0, (55, 64): 185.0, (65, 74): 200.0, (75, 99): 130.0}
INVESTOR_INCOME_MULT = 1.45   # stock-holding families skew to upper-middle income (SCF Box 2) - assumption
INFLATE_2022_2026 = 1.14      # CPI-U drift 2022->2026 - assumption
# BLS CE 2025: (mean income before taxes, mean annual expenditures) by income quintile.
CE_QUINTILES = [(46080, 51405), (78584, 68983), (126349, 92250), (286188, 159512)]
# Risk-score mix by age (assumption shaped by target-date glide paths: ~90% equity young, ~50% at 65).
RISK_WEIGHTS = {(18, 34): [0, 1, 3, 4, 2], (35, 44): [0, 1, 4, 4, 1], (45, 54): [0, 2, 5, 3, 1],
                (55, 64): [1, 3, 5, 2, 0], (65, 99): [2, 4, 3, 1, 0]}

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
    med_inc = bucket(SCF_MEDIAN_INCOME_K, age) * 1000 * INFLATE_2022_2026 * INVESTOR_INCOME_MULT
    income = min(max(lognorm(rng, med_inc, 0.42), 48_000), 420_000)
    income = round_to(income, 500)
    ratio = expense_ratio(income) * rng.uniform(0.88, 1.08)
    monthly_exp = round_to(max(income * ratio / 12, 2600), 50)
    med_T = bucket(SCF_MEDIAN_RETIRE_K, age) * 1000 * INFLATE_2022_2026 * 1.6  # retirement + taxable accounts
    total = lognorm(rng, med_T * (income / med_inc) ** 0.9, 0.5)
    total = round_to(min(max(total, 40_000), 2_500_000), 100)
    if risk is None:
        risk = rng.choices([1, 2, 3, 4, 5], weights=bucket(RISK_WEIGHTS, age))[0]
    if retired:
        occ = "retired " + rng.choice([o[2] for o in OCCUPATIONS[:12]])
        contrib = 0.0
    else:
        fits = [o[2] for o in OCCUPATIONS if o[0] <= income <= o[1]] or [OCCUPATIONS[-2][2]]
        occ = rng.choice(fits)
        contrib = round_to(income * rng.uniform(0.06, 0.16) / 12, 50)  # Vanguard HAS total deferral ~12%
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


def make_case(rng: random.Random, cid: str, arch: dict) -> dict:
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
        tc = max(rng.choice([0.03, 0.04, 0.05, 0.05, 0.06, 0.08]), math.ceil(3.5 * exp / T * 100) / 100)
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
    elif rng.random() < arch.get("p_small_single", 0.3):
        singles[rng.choice(list(EMPLOYERS))] = rng.uniform(0.02, 0.075)   # a "fun money" direct stock pick
    intl = 0.0 if rng.random() < 0.2 else rng.uniform(0.15, 0.40)

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
            tenure = rng.randint(2, 14)
            weeks = min(max(2, round(tenure * rng.choice([1, 1, 1, 1.5, 2]))), 40)
            det = {"severance": round_to(income / 52 * weeks, 100), "severance_weeks": weeks,
                   "tenure_years": tenure, "employer": employer or rng.choice(OLD_EMPLOYERS),
                   "last_day": d.isoformat(),
                   "cobra_monthly_premium": rng.choice([760, 810, 1490, 2130]) if hh["deps"] or hh["married"]
                   else rng.choice([690, 760, 820])}
            employment = "unemployed"
            notes.append(f"Laid off {d:%b %d}; severance paid as a lump sum to an outside checking account.")
        elif etype == "job_change":
            if arch.get("pay_cut"):
                new_inc = round_to(income * rng.uniform(0.80, 0.93), 500)
                notes.append("Took a lower-paying role with a shorter commute and better hours.")
            else:
                new_inc = round_to(income * rng.uniform(1.10, 1.32), 500)
            det = {"new_income": new_inc, "previous_income": income, "new_employer": rng.choice(NEW_EMPLOYERS),
                   "start_date": d.isoformat(), "employer_401k_match_pct": rng.choice([3, 4, 5, 6])}
            if rng.random() < 0.4 and not arch.get("pay_cut"):
                det["signing_bonus"] = round_to(new_inc * rng.uniform(0.05, 0.12), 500)
        elif etype == "marriage":
            sp_age = max(23, age + rng.randint(-4, 4))
            det = {"spouse_name": f"{rng.choice(FIRST)} {rng.choice(LAST)}", "spouse_age": sp_age,
                   "spouse_annual_income": round_to(lognorm(rng, 80_000, 0.4), 1000),
                   "spouse_has_separate_accounts": True}
            marital = "married"
        elif etype == "child":
            det = {"child_name": rng.choice(KIDS), "birth_date": d.isoformat(), "adoption": rng.random() < 0.08}
            notes.append("Newborn at home; one parent on unpaid leave until January.")
        elif etype == "inheritance":
            amt = round_to(rng.uniform(*arch.get("inherit_x", (0.6, 1.8))) * T, 1000)
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
            transferred = round_to(T * rng.uniform(0.8, 1.0), 1000)
            det = {"final_date": d.isoformat(), "assets_transferred_usd": transferred,
                   "custody": "shared" if hh["deps"] else None,
                   "child_support_monthly": round_to(rng.uniform(600, 1400), 50) if hh["deps"] else 0}
            expenses = round_to(exp * rng.uniform(0.80, 0.95), 50)   # smaller household, but a second home
            marital = "divorced"
            notes.append("Holdings shown are after the court-ordered transfer to the former spouse.")
        elif etype == "market_drop":
            us = arch["drop"]
            intl_d = us * rng.uniform(0.9, 1.1)
            bond_d = arch.get("bond_drop", 0.0)
            for s, m in market.items():
                if s == "US_EQ":
                    m["price"] = r2(m["price"] * (1 + us))
                elif s == "INTL_EQ":
                    m["price"] = r2(m["price"] * (1 + intl_d))
                elif s == "BOND":
                    m["price"] = r2(m["price"] * (1 + bond_d))
                elif m.get("single_stock"):
                    m["price"] = r2(m["price"] * max(0.15, 1 + us * SINGLE_BETA[s]))
            positions = reprice(positions, market)
            det = {"us_equity_change_pct": round(100 * us, 1), "intl_equity_change_pct": round(100 * intl_d, 1),
                   "bond_change_pct": round(100 * bond_d, 1),
                   "peak_date": (d - timedelta(days=rng.randint(33, 75))).isoformat(),
                   "trough_date": d.isoformat(), "historical_analog": arch["analog"]}
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
    return {"client": client, "holdings": holdings, "market": {"as_of": AS_OF, "symbols": market},
            "events": {"events": events}}


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
    A("market_drop_2020", events=["market_drop"], drift="tol", drop=-0.339,
      analog="Feb-Mar 2020 COVID crash (S&P 500 -33.9%)", risk=4, check=lambda **k: k["eq"] < k["lo"] - 0.01),
    A("market_drop_2022", events=["market_drop"], drift="tol", drop=-0.254, bond_drop=-0.13,
      analog="Jan-Oct 2022 bear market (S&P 500 -25.4%, US agg bonds about -13%)", risk=3,
      check=lambda **k: k["eq"] < k["lo"] - 0.01),
    A("market_drop+layoff", events=["market_drop", "layoff"], drift="tol", drop=-0.30, cash_months=(1.5, 3.5),
      analog="2020-style crash", risk=3),
    A("inheritance+child", events=["inheritance", "child"], drift="tol", age=(29, 40), inherit_x=(0.4, 0.9),
      check=lambda **k: k["eq"] < k["lo"] - 0.02),
    A("divorce+job_change", events=["divorce", "job_change"], drift="over", age=(35, 52), cash_months=(1.5, 3.0)),
    A("market_drop+concentration", events=["market_drop"], drift="tol", drop=-0.22, single=(0.13, 0.2),
      analog="2018-style 20%+ correction", risk=4, check=lambda **k: k["max_single"] > 0.105),
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


def generate(write: bool = True) -> dict:
    out_root = ROOT / "cases"
    manifest = {"generated_as_of": AS_OF, "seeds": SEEDS, "cases": {}}
    for set_name, items in SETS.items():
        set_dir = out_root / set_name
        if write and set_dir.exists():
            shutil.rmtree(set_dir)
        for idx, (cid, arch) in enumerate(shuffled(set_name, items)):
            rng = random.Random(SEEDS[set_name] * 1000 + idx)
            for attempt in range(5000):
                try:
                    case = make_case(rng, cid, arch)
                    break
                except Retry:
                    continue
            else:
                raise RuntimeError(f"{cid}: could not satisfy archetype {arch['name']}")
            manifest["cases"][cid] = {"set": set_name, "archetype": arch["name"], "tags": tags_for(case),
                                      "draws": attempt + 1}
            if write:
                d = set_dir / cid
                d.mkdir(parents=True, exist_ok=True)
                for fname in ("client", "holdings", "market", "events"):
                    (d / f"{fname}.json").write_text(json.dumps(case[fname], indent=2) + "\n", encoding="utf-8")
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
