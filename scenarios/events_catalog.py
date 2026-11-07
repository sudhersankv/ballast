"""Life/work event taxonomy for the stress population (scenarios/stress.py, scenarios/journeys_ext.py).

CATALOG[type] = {family, freq, impact, src, make(rng, ctx) -> details}
  freq/impact/src are documentation (rendered into SOURCES.md / README.md); `src` keys point at SOURCES.md.
  make() randomizes severity; with probability AMBIGUOUS_P some amounts are withheld (None + a note) to test
  how the agent handles missing details. Grading of the new types lives in checker/rules_ext.py.
ctx keys: income, expenses, total, age, deps, employer (ticker|None), employer_name, fs (bool), date (event date),
          as_of (date), married (bool)
"""
from __future__ import annotations

from datetime import timedelta

AMBIGUOUS_P = 0.12


def _r(x: float, step: float = 100) -> float:
    return float(round(x / step) * step)


def _maybe(rng, det: dict, key: str, note: str) -> dict:
    if rng.random() < AMBIGUOUS_P:
        det[key] = None
        det["note"] = note
    return det


def _due(ctx, rng, lo_days: int, hi_days: int) -> str:
    return (ctx["as_of"] + timedelta(days=rng.randint(lo_days, hi_days))).isoformat()


FS_FIRMS = {"HVCG": "Halvard Capital Group", "MRTS": "Meridian Trust Securities", "ALDB": "Aldenbrook Partners"}

C: dict[str, dict] = {}


def ev(name, family, freq, impact, src):
    def deco(fn):
        C[name] = {"family": family, "freq": freq, "impact": impact, "src": src, "make": fn}
        return fn
    return deco


# ------------------------------------------------------------------ health
@ev("serious_illness", "health", "~40% lifetime cancer risk; 1 in 4 workers disabled before 67", "out-of-pocket costs, reduced hours", "ssa_disability")
def _(rng, x):
    d = {"diagnosis_category": rng.choice(["cancer", "cardiac", "autoimmune", "neurological"]),
         "monthly_cost_increase": _r(rng.uniform(400, 2200), 50), "work_hours_reduced_pct": rng.choice([0, 25, 50]),
         "insurance_out_of_pocket_max": rng.choice([4000, 6000, 9100, 18200])}
    return _maybe(rng, d, "monthly_cost_increase", "treatment plan not final; costs still being estimated")


@ev("disability", "health", "24% of 20-year-olds disabled before normal retirement age (SSA 2025)", "income drops to 50-70% benefit; care costs", "ssa_disability")
def _(rng, x):
    return {"kind": rng.choice(["short_term", "long_term"]), "benefit_pct_of_income": rng.choice([50, 60, 66, 70]),
            "monthly_cost_increase": _r(rng.uniform(200, 1500), 50), "expected_duration_months": rng.choice([3, 6, 12, None])}


@ev("parent_long_term_care", "health", "56-70% of people turning 65 will need LTC (ACL, 2023 study)", "monthly cost share for a parent's care", "acl_ltc")
def _(rng, x):
    d = {"care_type": rng.choice(["home health aide", "assisted living", "nursing home", "adult day care"]),
         "monthly_cost_increase": _r(rng.uniform(800, 4500), 50), "siblings_sharing_cost": rng.randint(0, 3)}
    return _maybe(rng, d, "monthly_cost_increase", "family has not agreed how to split the cost yet")


@ev("medical_bill", "health", "41% of adults carry medical or dental debt (KFF 2023)", "lump bill due within months", "kff_debt")
def _(rng, x):
    return {"amount_due": _r(rng.uniform(2000, 28000)), "due_date": _due(x, rng, 20, 150),
            "payment_plan_available": rng.random() < 0.5}


@ev("special_needs_diagnosis", "health", "about 1 in 6 US children has a developmental disability (CDC)", "therapy and care costs", "assumption")
def _(rng, x):
    return {"child_age": rng.randint(2, 12), "monthly_cost_increase": _r(rng.uniform(500, 2500), 50),
            "insurance_coverage": rng.choice(["partial", "pending appeal", "none"])}


# ------------------------------------------------------------------ family
@ev("death_of_spouse", "family", "widowhood rises sharply after 65; ~1 in 3 women 65+ widowed (Census)", "loss of second income; life-insurance payout", "assumption")
def _(rng, x):
    return {"life_insurance_payout": _r(rng.uniform(0.5, 3.0) * x["income"], 1000), "deposited_to": "CASH",
            "spouse_income_lost": _r(rng.uniform(30000, 150000), 1000),
            "survivor_benefit_monthly": rng.choice([0, 1400, 2100, 2800])}


@ev("adult_child_moves_back", "family", "18% of 25-34 year-olds live in a parent's home (Pew 2023)", "household costs rise", "pew_parents")
def _(rng, x):
    return {"child_age": rng.randint(22, 31), "monthly_cost_increase": _r(rng.uniform(300, 1500), 50),
            "expected_stay_months": rng.choice([6, 12, 24, None])}


@ev("tuition_due", "family", "private nonprofit 4-yr published tuition $43,350 (College Board 2024-25)", "large known payment within a year", "collegeboard")
def _(rng, x):
    d = {"amount_due": _r(rng.uniform(9000, 62000)), "due_date": _due(x, rng, 30, 300),
         "school_type": rng.choice(["public in-state", "public out-of-state", "private nonprofit"]),
         "aid_package_final": rng.random() < 0.6}
    return d


# ------------------------------------------------------------------ housing
@ev("home_purchase", "housing", "first-time buyers: median age 38, 9% down (NAR 2024)", "down payment + closing costs due at closing", "nar")
def _(rng, x):
    price = _r(rng.uniform(2.5, 5.0) * x["income"], 5000)
    dp = rng.choice([0.05, 0.10, 0.20])
    return {"home_price": price, "down_payment_pct": int(dp * 100), "amount_due": _r(price * (dp + 0.03)),
            "due_date": _due(x, rng, 45, 240), "monthly_housing_cost_change": _r(rng.uniform(-300, 1800), 50)}


@ev("relocation", "housing", "~8% of Americans move each year (Census CPS)", "moving costs; cost of living change", "assumption")
def _(rng, x):
    return {"amount_due": _r(rng.uniform(4000, 25000)), "due_date": _due(x, rng, 15, 120),
            "cost_of_living_change_pct": rng.choice([-15, -5, 0, 10, 25]), "employer_relocation_package": rng.random() < 0.4}


@ev("disaster_damage", "housing", "billion-dollar US disasters: ~20+/yr recently (NOAA)", "uninsured repair cost", "assumption")
def _(rng, x):
    dmg = _r(rng.uniform(15000, 180000), 1000)
    cov = rng.choice([0, 50, 80, 90])
    d = {"peril": rng.choice(["hurricane", "wildfire", "flood", "tornado"]), "damage_usd": dmg,
         "insurance_covered_pct": cov, "amount_due": _r(dmg * (100 - cov) / 100), "due_date": _due(x, rng, 10, 180)}
    return _maybe(rng, d, "amount_due", "adjuster report pending")


@ev("foreclosure_risk", "housing", "~0.3% of housing units with a foreclosure filing per year (ATTOM)", "arrears due to cure default", "assumption")
def _(rng, x):
    return {"arrears_usd": (a := _r(rng.uniform(6000, 40000))), "amount_due": a, "due_date": _due(x, rng, 20, 90),
            "monthly_mortgage": _r(rng.uniform(1500, 4500), 50)}


# ------------------------------------------------------------------ work
@ev("furlough", "work", "used widely in 2020; government shutdowns", "unpaid weeks, return uncertain", "assumption")
def _(rng, x):
    return {"unpaid_weeks": rng.choice([4, 8, 12, 26]), "expected_return": rng.choice(["confirmed", "uncertain"]),
            "benefits_continued": rng.random() < 0.7}


@ev("pay_cut", "work", "common in downturns", "salary reduced 5-20%", "assumption")
def _(rng, x):
    return {"new_income": _r(x["income"] * rng.uniform(0.8, 0.95), 500), "reason": rng.choice(["cost cutting", "reduced hours"])}


@ev("bonus_cut", "work", "finance bonuses fall with markets (comp tied to revenue)", "variable comp down 30-100%", "assumption")
def _(rng, x):
    exp = _r(x["income"] * rng.uniform(0.1, 1.0), 1000)
    return {"expected_bonus": exp, "actual_bonus": _r(exp * rng.uniform(0.0, 0.7), 1000),
            "reason": rng.choice(["firm revenue down", "market downturn", "desk underperformed"])}


@ev("startup_equity", "work", "common in tech hiring", "illiquid options, not in brokerage account", "assumption")
def _(rng, x):
    return {"company": rng.choice(["Quillon Software", "Orchard Labs", "Corvane Analytics"]), "options": rng.randint(5, 80) * 1000,
            "strike": round(rng.uniform(0.2, 6.0), 2), "last_409a_price": round(rng.uniform(0.5, 12), 2), "liquid": False}


@ev("ipo_lockup", "work", "lockups typically 180 days (Schwab)", "employer shares cannot be sold until lockup ends", "lockup")
def _(rng, x):
    return {"symbol": x["employer"], "lockup_end_date": _due(x, rng, 60, 180),
            "locked_shares_value_outside_account": _r(rng.uniform(50000, 900000), 1000)}


@ev("rsu_cliff", "work", "standard 1-year cliff then quarterly vesting", "employer shares land in the account", "assumption")
def _(rng, x):
    return {"symbol": x["employer"], "vest_value": _r(rng.uniform(0.08, 0.25) * x["total"], 100), "vest_date": x["date"].isoformat()}


@ev("sabbatical", "work", "unpaid leave; employer-dependent", "months without pay are a known cash need", "assumption")
def _(rng, x):
    m = rng.choice([2, 3, 6])
    return {"unpaid_months": m, "amount_due": _r(m * x["expenses"]), "due_date": _due(x, rng, 30, 200)}


@ev("gig_income", "work", "~1 in 3 workers do some independent work (McKinsey 2022)", "variable income; thicker buffer", "assumption")
def _(rng, x):
    return {"avg_monthly_income": _r(x["income"] / 12 * rng.uniform(0.5, 1.1), 50),
            "income_volatility_pct": rng.choice([25, 40, 60]), "platforms": rng.randint(1, 4)}


@ev("business_failure", "work", "about 1 in 5 new businesses fail in year one (BLS BED)", "owner income stops", "assumption")
def _(rng, x):
    return {"business": rng.choice(["restaurant", "consultancy", "retail shop", "contracting firm"]),
            "personal_guarantee_usd": rng.choice([0, 0, 25000, 75000])}


@ev("early_retirement_offer", "work", "common in corporate restructurings", "decision needed; lump sum offered", "assumption")
def _(rng, x):
    return {"lump_sum_offer": _r(x["income"] * rng.uniform(0.5, 1.5), 1000), "decision_deadline": _due(x, rng, 20, 60)}


@ev("pension_buyout_offer", "work", "pension risk transfer offers to vested participants", "lump sum vs annuity election", "assumption")
def _(rng, x):
    return {"lump_sum_offer": _r(rng.uniform(80000, 600000), 1000), "annuity_monthly": _r(rng.uniform(600, 3500), 50),
            "decision_deadline": _due(x, rng, 30, 90)}


@ev("retirement", "work", "median US retirement age ~62 (various surveys)", "salary stops; pension/SS start", "assumption")
def _(rng, x):
    return {"pension_monthly": rng.choice([0, 0, 900, 1800, 2600]), "social_security_monthly": rng.choice([1900, 2400, 3100]),
            "start_date": x["date"].isoformat()}


# ------------------------------------------------------------------ windfalls and losses
@ev("lottery_win", "windfall", "rare", "cash windfall after tax", "assumption")
def _(rng, x):
    return {"amount_after_tax": _r(rng.uniform(50000, 900000), 1000), "deposited_to": "CASH"}


@ev("lawsuit_settlement", "windfall", "rare", "settlement deposited", "assumption")
def _(rng, x):
    return {"amount": _r(rng.uniform(25000, 400000), 1000), "deposited_to": "CASH", "taxable": rng.random() < 0.5}


@ev("business_sale", "windfall", "owner exits; earnouts common", "large cash proceeds + earnout", "assumption")
def _(rng, x):
    return {"proceeds": _r(rng.uniform(150000, 2000000), 1000), "deposited_to": "CASH",
            "earnout_possible": _r(rng.uniform(0, 500000), 1000)}


@ev("crypto_loss", "loss", "16-20% of Americans have used crypto (Pew)", "loss in an outside exchange account", "pew_crypto")
def _(rng, x):
    return {"amount_lost": _r(rng.uniform(2000, 120000)), "account": "outside exchange (not in this portfolio)"}


@ev("fraud_loss", "loss", "$12.5B reported fraud losses in 2024; investment scams $5.7B (FTC)", "cash stolen from the account", "ftc")
def _(rng, x):
    return {"amount_lost": _r(rng.uniform(3000, 90000)), "scam_type": rng.choice(["investment", "imposter", "romance", "account takeover"]),
            "recovery_expected": rng.choice(["unlikely", "partial", "unknown"])}


@ev("tax_bill", "loss", "underpayment common after RSU vesting / windfalls", "tax due by a known date", "assumption")
def _(rng, x):
    d = {"amount_due": _r(rng.uniform(0.03, 0.2) * x["income"]), "due_date": _due(x, rng, 15, 200),
         "reason": rng.choice(["RSU withholding shortfall", "capital gains", "self-employment tax", "audit adjustment"])}
    return _maybe(rng, d, "amount_due", "CPA still finalizing the return")


# ------------------------------------------------------------------ debt
@ev("student_loan_restart", "debt", "federal repayment restarted Oct 2023", "monthly payment resumes", "assumption")
def _(rng, x):
    return {"balance": _r(rng.uniform(15000, 120000)), "monthly_payment": _r(rng.uniform(150, 1100), 10)}


@ev("credit_card_debt", "debt", "$1.21T US card balances, Q2 2025 (NY Fed)", "high-APR balance", "nyfed")
def _(rng, x):
    return {"balance": _r(rng.uniform(4000, 45000)), "apr_pct": rng.choice([19.9, 22.9, 26.9, 29.9])}


@ev("margin_call", "debt", "triggered by drawdowns in leveraged accounts", "cash due within days", "assumption")
def _(rng, x):
    return {"amount_due": _r(rng.uniform(0.02, 0.10) * x["total"]), "due_date": _due(x, rng, 2, 7),
            "account": "outside margin account"}


# ------------------------------------------------------------------ legal
@ev("bankruptcy", "legal", "517,308 US filings in 2024 (US Courts)", "court process; assets may be constrained", "uscourts")
def _(rng, x):
    return {"chapter": rng.choice([7, 13]), "filed_by": rng.choice(["client", "client's business"])}


@ev("lawsuit", "legal", "personal liability suits", "possible judgment; legal fees", "assumption")
def _(rng, x):
    return {"claim_usd": _r(rng.uniform(20000, 800000), 1000), "insured": rng.random() < 0.5,
            "status": rng.choice(["filed", "discovery", "settlement talks"])}


@ev("legal_judgment", "legal", "follows lost suits", "amount due to court", "assumption")
def _(rng, x):
    return {"amount_due": _r(rng.uniform(10000, 120000)), "due_date": _due(x, rng, 30, 120)}


# ------------------------------------------------------------------ financial-services employees
@ev("bonus_deferral", "fs", "40-60% of senior bank bonuses deferred up to 4 years (2016 Sec. 956 proposal)", "most of the bonus vests later, often in employer stock", "fed956")
def _(rng, x):
    tot = _r(x["income"] * rng.uniform(0.4, 1.5), 1000)
    dp = rng.choice([40, 50, 60, 70])
    return {"total_bonus": tot, "cash_pct": 100 - dp, "deferred_pct": dp, "vesting_years": rng.choice([3, 4, 5]),
            "deferred_in": f"{x['employer']} stock units" if x["employer"] else "deferred cash"}


@ev("deferred_comp_clawback", "fs", "SEC Rule 10D-1 (2022) mandates no-fault clawback policies", "unvested pay forfeited", "fed956")
def _(rng, x):
    return {"amount_clawed": _r(x["income"] * rng.uniform(0.2, 1.0), 1000), "reason": rng.choice(["restatement", "risk event", "conduct review"])}


@ev("firm_collapse", "fs", "Lehman 2008: employee RSUs worthless, deferred comp subordinated", "employer stock -90%+, job and deferred comp gone", "lehman")
def _(rng, x):
    return {"employer": x["employer_name"], "symbol": x["employer"], "stock_change_pct": -round(rng.uniform(90, 99), 1),
            "deferred_comp_lost_usd": _r(x["income"] * rng.uniform(0.3, 2.0), 1000)}


@ev("trading_blackout", "fs", "quarterly insider-trading blackout windows are standard", "employer stock cannot be traded until window opens", "assumption")
def _(rng, x):
    return {"symbol": x["employer"], "window_opens": _due(x, rng, 10, 45)}


@ev("insider_status", "fs", "pre-clearance required for covered persons at broker-dealers", "every trade in employer stock needs pre-clearance; none granted", "assumption")
def _(rng, x):
    return {"symbol": x["employer"], "pre_clearance_required": True, "status": "restricted list"}


@ev("carried_interest", "fs", "PE/hedge-fund professionals", "large illiquid future payout; not in this account", "assumption")
def _(rng, x):
    return {"fund": rng.choice(["Fund III", "Fund IV", "Opportunities Fund"]), "estimated_value": _r(rng.uniform(100000, 3000000), 1000),
            "expected_years_to_realize": rng.randint(3, 8), "liquid": False}


@ev("desk_shutdown", "fs", "desks closed in restructurings (e.g. 2008, 2023)", "job ends; garden leave pay for a few months", "assumption")
def _(rng, x):
    return {"garden_leave_months": rng.choice([1, 3, 6]), "severance": _r(x["income"] * rng.uniform(0.1, 0.5), 1000)}


@ev("regulatory_ban", "fs", "FINRA/SEC industry bars", "barred from the industry for months/years", "assumption")
def _(rng, x):
    return {"duration_months": rng.choice([6, 12, 24, None]), "regulator": rng.choice(["FINRA", "SEC", "state regulator"])}


@ev("prop_trading_loss", "fs", "personal trading losses in outside accounts", "loss outside this portfolio; may trigger a margin call", "assumption")
def _(rng, x):
    return {"loss_usd": _r(rng.uniform(10000, 250000), 1000), "account": "personal brokerage (outside)"}


# ------------------------------------------------------------------ original types used in the stress set
@ev("layoff", "work", "~1.1%/month layoff rate (BLS JOLTS)", "income stops; severance outside the account", "jolts")
def _(rng, x):
    weeks = min(max(2, round(rng.randint(1, 15) * rng.choice([1, 1, 1.5, 2]))), 40)
    return {"severance": _r(x["income"] / 52 * weeks), "severance_weeks": weeks, "employer": x["employer_name"] or "previous employer",
            "last_day": x["date"].isoformat(), "cobra_monthly_premium": rng.choice([690, 760, 1490, 2130])}


@ev("job_change", "work", "Atlanta Fed: ~4% median wage growth; switchers vary widely", "new income (up or down)", "atl_fed")
def _(rng, x):
    return {"new_income": _r(x["income"] * rng.choice([rng.uniform(1.08, 1.35), rng.uniform(0.75, 0.97)]), 500),
            "previous_income": x["income"], "start_date": x["date"].isoformat()}


@ev("marriage", "family", "6.2 per 1,000 (CDC 2022)", "joint profile", "cdc_marriage")
def _(rng, x):
    return {"spouse_annual_income": _r(rng.uniform(30000, 160000), 1000), "spouse_has_separate_accounts": True}


@ev("child", "family", "twins 30.7 per 1,000 births (CDC 2023)", "new dependent(s); education goal", "cdc_twins")
def _(rng, x):
    d = {"birth_date": x["date"].isoformat(), "adoption": rng.random() < 0.06}
    if rng.random() < 0.08:
        d["multiple_birth"] = 2
    return d


@ev("divorce", "family", "2.3 per 1,000 (CDC 2024)", "assets split; alimony/child support", "cdc_marriage")
def _(rng, x):
    return {"assets_transferred_usd": _r(x["total"] * rng.uniform(0.6, 1.0), 1000),
            "alimony_monthly": rng.choice([0, 0, 1200, 2500, -1500]), "child_support_monthly": rng.choice([0, 700, 1300])}


@ev("inheritance", "windfall", "~1 in 4 families ever inherit (SCF)", "cash deposited", "scf_inherit")
def _(rng, x):
    return {"amount": _r(rng.uniform(0.15, 1.2) * x["total"], 1000), "form": "cash", "deposited_to": "CASH"}


@ev("market_drop", "market", "real troughs 2002/2009/2020/2022", "equity prices fall", "market")
def _(rng, x):
    return {}


CATALOG = C
FAMILIES = sorted({v["family"] for v in C.values()})


@ev("promotion_title_only", "work", "title changes without pay change", "no financial change", "assumption")
def _(rng, x):
    return {"new_title": rng.choice(["Senior Manager", "Director", "Principal", "Vice President"]), "pay_change": 0}


@ev("annual_review", "work", "routine HR review", "no financial change", "assumption")
def _(rng, x):
    return {"rating": rng.choice(["meets", "exceeds", "strong"]), "merit_increase_pct": 0, "note": "raise deferred to next cycle"}


CATALOG = C
FAMILIES = sorted({v["family"] for v in C.values()})
