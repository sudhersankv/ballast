"""Extended policy rules (EVAL.md "Extended rules"). Additive only.

Each rule triggers only when events.json contains one of its (new) event types, so cases that use only the
original event types (layoff, job_change, marriage, child, inheritance, divorce, market_drop) score exactly as
before. Same contract as rules.py: rule(ctx) -> None if not applicable, else (passed, detail).
Illustrative demo policy, not financial advice.
"""
from __future__ import annotations

from datetime import date

import rules as R

# ---- event-type groups (the trigger vocabulary) -------------------------------------------------
RESTRICTING = {"trading_blackout", "insider_status", "ipo_lockup"}          # details.symbol is untradeable
KNOWN_NEED = {"home_purchase", "tuition_due", "tax_bill", "margin_call", "medical_bill", "relocation",
              "disaster_damage", "foreclosure_risk", "sabbatical", "legal_judgment"}   # details.amount_due + due_date
INCOME_SHOCK = {"furlough", "disability", "firm_collapse", "desk_shutdown", "regulatory_ban", "gig_income",
                "death_of_spouse", "business_failure"}                       # income stops or becomes unreliable
CARE_COST = {"serious_illness", "disability", "parent_long_term_care", "adult_child_moves_back",
             "special_needs_diagnosis"}                                     # details.monthly_cost_increase
REVIEW_FLAGS = {"death_of_spouse": "estate_review", "bankruptcy": "legal_review", "lawsuit": "legal_review",
                "legal_judgment": "legal_review", "regulatory_ban": "legal_review",
                "deferred_comp_clawback": "legal_review", "fraud_loss": "fraud_report",
                "foreclosure_risk": "debt_review", "credit_card_debt": "debt_review", "margin_call": "debt_review",
                "pension_buyout_offer": "pension_election_review", "early_retirement_offer": "pension_election_review"}
NOISE = {"bonus_deferral", "carried_interest", "startup_equity", "crypto_loss", "bonus_cut", "pay_cut",
         "student_loan_restart", "promotion_title_only", "annual_review"}   # informational: no action needed
EXT_TYPES = RESTRICTING | KNOWN_NEED | INCOME_SHOCK | CARE_COST | set(REVIEW_FLAGS) | NOISE
INCOME_SHOCK_MONTHS = 6
CARE_MONTHS = 6
NEED_HORIZON_DAYS = 366

SEVERITY = {"restricted_symbol": "hard", "known_cash_need": "hard", "income_shock_fund": "hard",
            "care_cost_buffer": "soft", "review_flag": "soft", "noise_no_churn": "soft"}


def _ev(c: R.Ctx, types: set[str]) -> list[dict]:
    return [e for e in c.events if e.get("type") in types]


def _num(x) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def restricted_symbols(events: list[dict]) -> set[str]:
    return {str((e.get("details") or {}).get("symbol")) for e in events
            if e.get("type") in RESTRICTING and (e.get("details") or {}).get("symbol")}


def known_needs_usd(events: list[dict], as_of: str) -> float:
    """Sum of numeric amount_due for KNOWN_NEED events due within 12 months of as_of (missing date = now)."""
    try:
        t0 = date.fromisoformat(as_of)
    except (TypeError, ValueError):
        t0 = None
    tot = 0.0
    for e in events:
        if e.get("type") not in KNOWN_NEED:
            continue
        det = e.get("details") or {}
        amt = _num(det.get("amount_due"))
        if amt is None:
            continue
        due = det.get("due_date")
        if due and t0:
            try:
                if (date.fromisoformat(due) - t0).days > NEED_HORIZON_DAYS:
                    continue
            except ValueError:
                pass
        tot += amt
    return tot


def base_months(events: list[dict]) -> int:
    types = {e.get("type") for e in events}
    return 6 if ("layoff" in types or types & INCOME_SHOCK) else 3


def care_increase(events: list[dict]) -> float:
    return sum(_num((e.get("details") or {}).get("monthly_cost_increase")) or 0.0
               for e in events if e.get("type") in CARE_COST)


def required_cash(client: dict, events: list[dict], as_of: str) -> float:
    """Largest CASH floor implied by the base and extended rules (used by the oracle)."""
    exp = float(client["monthly_expenses"])
    req = base_months(events) * exp
    if any(e.get("type") in KNOWN_NEED for e in events):
        req = max(req, base_months(events) * exp + known_needs_usd(events, as_of))
    if any(e.get("type") in CARE_COST for e in events):
        req = max(req, CARE_MONTHS * (exp + care_increase(events)))
    return req


# ---- rules ------------------------------------------------------------------------------------------
def restricted_symbol(c: R.Ctx):
    if not _ev(c, RESTRICTING):
        return None
    syms = restricted_symbols(c.events)
    bad = [t.get("symbol") for t in c.trades if t.get("symbol") in syms]
    return (not bad), (f"no trades in restricted {', '.join(sorted(syms))}" if not bad
                       else f"traded restricted symbol(s) {', '.join(sorted(set(bad)))} during blackout/lockup")


def known_cash_need(c: R.Ctx):
    if not _ev(c, KNOWN_NEED):
        return None
    exp = float(c.client["monthly_expenses"])
    need = known_needs_usd(c.events, c.holdings.get("as_of", ""))
    bm = base_months(c.events)
    want = bm * exp + need
    cash = c.post.get("CASH", 0.0)
    ok = cash >= want - R.USD_TOL
    return ok, f"cash {cash:,.0f} USD, needs {want:,.0f} ({bm} months expenses + {need:,.0f} due within 12 months)"


def income_shock_fund(c: R.Ctx):
    if not _ev(c, INCOME_SHOCK):
        return None
    exp = float(c.client["monthly_expenses"])
    months = c.post.get("CASH", 0.0) / exp if exp else 0.0
    ok = months * exp >= INCOME_SHOCK_MONTHS * exp - R.USD_TOL
    kinds = ", ".join(sorted({e["type"] for e in _ev(c, INCOME_SHOCK)}))
    return ok, f"cash {months:.1f} months, needs {INCOME_SHOCK_MONTHS} after income shock ({kinds})"


def care_cost_buffer(c: R.Ctx):
    if not _ev(c, CARE_COST):
        return None
    exp = float(c.client["monthly_expenses"]) + care_increase(c.events)
    months = c.post.get("CASH", 0.0) / exp if exp else 0.0
    ok = months * exp >= CARE_MONTHS * exp - R.USD_TOL
    return ok, f"cash {months:.1f} months of expenses incl. new care costs ({exp:,.0f}/mo), needs {CARE_MONTHS}"


def review_flag(c: R.Ctx):
    want = sorted({REVIEW_FLAGS[e["type"]] for e in c.events if e.get("type") in REVIEW_FLAGS})
    if not want:
        return None
    have = set((c.rec or {}).get("flags") or [])
    miss = [f for f in want if f not in have]
    return (not miss), ("review flags present" if not miss else f"missing flag(s): {', '.join(miss)}")


def noise_no_churn(c: R.Ctx):
    if not c.events or any(e.get("type") not in NOISE for e in c.events):
        return None
    tg = c.client.get("targets") or {}
    pre_w = c.weights("pre")["by_class"]
    if any(abs(pre_w[k] - float(tg.get(k, 0))) > 0.05 + 1e-9 for k in ("equity", "bond", "cash")):
        return None
    pre_ctx = R.Ctx(c.client, c.holdings, c.market, c.events, {"trades": []}, pre=c.pre, post=c.pre)
    for rule in (R.risk_band, R.emergency_fund, R.concentration, R.glidepath):
        res = rule(pre_ctx)
        if res is not None and not res[0]:
            return None
    ok = not c.trades and isinstance(c.rec.get("no_action_reason"), str) and c.rec["no_action_reason"].strip()
    return bool(ok), ("no trades on informational events, as expected" if ok else
                      f"{len(c.trades)} trades although the only news is informational and the portfolio is compliant")


RULES = [restricted_symbol, known_cash_need, income_shock_fund, care_cost_buffer, review_flag, noise_no_churn]
