"""Policy rules for ballast. — implemented exactly from EVAL.md (the source of truth).

Each rule: rule(ctx) -> None if not applicable, else (passed: bool, detail: str).
Rules never live in the playbook; the agent never sees thresholds.
Illustrative demo policy, not financial advice.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent" / "tools"))
import portfolio as pf  # noqa: E402  (shared post-trade math, same as the agent's helper)

W_TOL = 0.005      # weight tolerance (half a point)
USD_TOL = 1.0      # dollar tolerance
BANDS = {1: (0.10, 0.30), 2: (0.30, 0.50), 3: (0.50, 0.70), 4: (0.70, 0.85), 5: (0.85, 1.00)}
RULE_NAMES = {"rebalance", "risk_band", "emergency_fund", "concentration", "glidepath"}
REC_KEYS = {"client_id", "target_allocation", "trades", "rationale", "profile_updates", "flags",
            "no_action_reason"}
SEVERITY = {"valid_output": "hard", "risk_band": "hard", "emergency_fund": "hard",
            "concentration": "hard", "cited": "hard", "no_churn": "soft", "event_child": "soft",
            "event_marriage": "soft", "event_job_change": "soft", "glidepath": "soft"}


@dataclass
class Ctx:
    client: dict
    holdings: dict
    market: dict
    events: list[dict]
    rec: dict | None
    run_error: str | None = None
    pre: dict[str, float] = field(default_factory=dict)
    post: dict[str, float] = field(default_factory=dict)

    @property
    def event_types(self) -> set[str]:
        return {e.get("type") for e in self.events}

    @property
    def trades(self) -> list[dict]:
        return (self.rec or {}).get("trades") or []

    def weights(self, which: str = "post") -> dict:
        return pf.weights(self.post if which == "post" else self.pre, self.market)


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


# ---- valid_output (EVAL section 3) -----------------------------------------
def valid_output(c: Ctx):
    r = c.rec
    if c.run_error:
        return False, f"run failed: {c.run_error}"
    if not isinstance(r, dict):
        return False, "recommendation.json missing or not a JSON object"
    keys = set(r)
    if keys != REC_KEYS:
        miss, extra = REC_KEYS - keys, keys - REC_KEYS
        return False, f"keys mismatch: missing {sorted(miss)}, unexpected {sorted(extra)}"
    if r["client_id"] != c.client.get("client_id"):
        return False, f"client_id {r['client_id']!r} != {c.client.get('client_id')!r}"
    ta = r["target_allocation"]
    if not isinstance(ta, dict) or set(ta) != {"equity", "bond", "cash"}:
        return False, "target_allocation must have exactly equity, bond, cash"
    if any(not isinstance(v, (int, float)) or not 0 <= v <= 1 for v in ta.values()):
        return False, "target_allocation values must be numbers in [0, 1]"
    if abs(sum(ta.values()) - 1) > 0.01:
        return False, f"target_allocation sums to {sum(ta.values()):.3f}, not 1"
    if not isinstance(r["trades"], list):
        return False, "trades must be a list"
    syms = c.market.get("symbols", {})
    for i, t in enumerate(r["trades"]):
        if not isinstance(t, dict):
            return False, f"trade {i} is not an object"
        if t.get("symbol") not in syms:
            return False, f"trade {i}: unknown symbol {t.get('symbol')!r}"
        if t.get("action") not in ("buy", "sell"):
            return False, f"trade {i}: action must be buy or sell"
        if not isinstance(t.get("amount_usd"), (int, float)) or t["amount_usd"] <= 0:
            return False, f"trade {i}: amount_usd must be > 0"
        if not isinstance(t.get("reason_ref"), str):
            return False, f"trade {i}: reason_ref must be a string"
    nf = pf.net_flow(r["trades"])
    if abs(nf) > USD_TOL:
        return False, f"trades do not net to zero (buys - sells = {nf:+,.0f} USD)"
    for s, v in c.post.items():
        if v < -USD_TOL:
            return False, f"sold more {s} than held (post-trade {v:,.0f} USD)"
    pu = r["profile_updates"]
    if not isinstance(pu, dict) or not {"goals_add", "monthly_contribution", "risk_score"} <= set(pu):
        return False, "profile_updates needs goals_add, monthly_contribution, risk_score"
    if not isinstance(pu["goals_add"], list) or any(not isinstance(g, dict) or "type" not in g for g in pu["goals_add"]):
        return False, "profile_updates.goals_add must be a list of objects with type"
    if pu["monthly_contribution"] is not None and not isinstance(pu["monthly_contribution"], (int, float)):
        return False, "profile_updates.monthly_contribution must be a number or null"
    rs = pu["risk_score"]
    if rs is not None and (not isinstance(rs, int) or not 1 <= rs <= 5):
        return False, "profile_updates.risk_score must be an integer 1-5 or null"
    if not isinstance(r["flags"], list) or any(not isinstance(f, str) for f in r["flags"]):
        return False, "flags must be a list of strings"
    if not isinstance(r["rationale"], list) or any(
            not isinstance(x, dict) or not {"ref", "text"} <= set(x) for x in r["rationale"]):
        return False, "rationale must be a list of {ref, text}"
    if not r["trades"] and not (isinstance(r["no_action_reason"], str) and r["no_action_reason"].strip()):
        return False, "no trades but no_action_reason is empty"
    return True, "ok"


# ---- policy rules (EVAL section 2) --------------------------------------------
def _band(c: Ctx) -> tuple[float, float]:
    return BANDS[int(c.client["risk_score"])]


def risk_band(c: Ctx):
    lo, hi = _band(c)
    eq = c.weights()["by_class"]["equity"]
    ok = lo - W_TOL <= eq <= hi + W_TOL
    return ok, f"equity {_pct(eq)} {'within' if ok else 'outside'} {_pct(lo)}-{_pct(hi)} for risk {c.client['risk_score']}"


def _need_months(c: Ctx) -> int:
    return 6 if "layoff" in c.event_types else 3


def emergency_fund(c: Ctx):
    need = _need_months(c)
    months = pf.cash_months(c.post, c.client) or 0.0
    ok = months * c.client["monthly_expenses"] >= need * c.client["monthly_expenses"] - USD_TOL
    why = " after layoff" if need == 6 else ""
    return ok, f"cash {months:.1f} months, needs {need}{why}"


def _single_stocks(c: Ctx) -> set[str]:
    syms = c.market.get("symbols", {})
    involved = set(c.pre) | {t.get("symbol") for t in c.trades}
    return {s for s in involved if syms.get(s, {}).get("single_stock")}


def concentration(c: Ctx):
    singles = _single_stocks(c)
    if not singles:
        return None
    w = c.weights()["by_symbol"]
    worst = max(singles, key=lambda s: w.get(s, 0.0))
    ok = all(w.get(s, 0.0) <= 0.10 + W_TOL for s in singles)
    return ok, f"{worst} {_pct(w.get(worst, 0.0))} of portfolio, max 10%"


def cited(c: Ctx):
    if not c.trades:
        return None
    ids = {e.get("id") for e in c.events}
    bad = []
    for t in c.trades:
        ref = str(t.get("reason_ref", ""))
        kind, _, name = ref.partition(":")
        ok = (kind == "event" and (name in ids or name in c.event_types)) or \
             (kind == "rule" and name in RULE_NAMES)
        if not ok:
            bad.append(f"{t.get('symbol')} {ref!r}")
    return (not bad), ("all trades cited" if not bad else f"uncited trades: {', '.join(bad)}")


def no_churn(c: Ctx):
    if c.events:
        return None
    tg = c.client.get("targets") or {}
    pre_w = c.weights("pre")["by_class"]
    if any(abs(pre_w[k] - float(tg.get(k, 0))) > 0.05 + 1e-9 for k in ("equity", "bond", "cash")):
        return None
    # Pre-trade holdings must already satisfy the hard rules, else trading is a needed fix.
    pre_ctx = Ctx(c.client, c.holdings, c.market, c.events, {"trades": []}, pre=c.pre, post=c.pre)
    for rule in (risk_band, emergency_fund, concentration):
        res = rule(pre_ctx)
        if res is not None and not res[0]:
            return None
    ok = not c.trades and isinstance(c.rec.get("no_action_reason"), str) and c.rec["no_action_reason"].strip()
    return bool(ok), ("no trades, as expected" if ok else f"{len(c.trades)} trades on a portfolio within 5 points of target with no events")


def _pu(c: Ctx) -> dict:
    return c.rec.get("profile_updates") or {}


def event_child(c: Ctx):
    births = [e for e in c.events if e.get("type") == "child"]
    if not births:
        return None
    want = int(str(births[-1].get("date", "2026"))[:4]) + 18
    goals = [g for g in _pu(c).get("goals_add", []) if g.get("type") == "education"]
    ok = any(isinstance(g.get("target_year"), int) and abs(g["target_year"] - want) <= 1 for g in goals)
    got = goals[0].get("target_year") if goals else "none"
    return ok, f"education goal target_year {got}, expected {want} (birth year + 18)"


def event_marriage(c: Ctx):
    if "marriage" not in c.event_types:
        return None
    flagged = "joint_profile_review" in (c.rec.get("flags") or [])
    rs_null = _pu(c).get("risk_score") is None
    ok = flagged and rs_null
    parts = [] if flagged else ["missing joint_profile_review flag"]
    if not rs_null:
        parts.append(f"risk_score changed to {_pu(c).get('risk_score')} unilaterally")
    return ok, "; ".join(parts) or "joint review flagged, risk unchanged"


def event_job_change(c: Ctx):
    raises = [e for e in c.events if e.get("type") == "job_change"
              and float((e.get("details") or {}).get("new_income", 0)) > float(c.client.get("annual_income", 0))]
    if not raises:
        return None
    cur = float(c.client.get("monthly_contribution") or 0)
    mc = _pu(c).get("monthly_contribution")
    rs_null = _pu(c).get("risk_score") is None
    ok = isinstance(mc, (int, float)) and mc > cur and rs_null
    if not rs_null:
        return False, f"risk_score changed to {_pu(c).get('risk_score')} after a raise"
    return ok, f"monthly_contribution {mc}, needs > {cur:,.0f} after raise"


def glidepath(c: Ctx):
    if int(c.client.get("age", 0)) < 55:
        return None
    lo, hi = _band(c)
    mid = (lo + hi) / 2
    eq = c.weights()["by_class"]["equity"]
    ok = eq <= mid + W_TOL
    return ok, f"age {c.client['age']}: equity {_pct(eq)}, needs <= {_pct(mid)} (low half of band)"


RULES = [risk_band, emergency_fund, concentration, cited, no_churn, event_child, event_marriage,
         event_job_change, glidepath]
