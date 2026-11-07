"""Reference recommender + solvability self-check for ballast scenarios.

    python scenarios/oracle.py                 # check every case in scenarios/cases/*
    python scenarios/oracle.py --write         # also save oracle outputs to scenarios/oracle_out/<set>/<id>.json
    python scenarios/oracle.py --case scenarios/cases/test/c-021   # print one recommendation

`recommend(case)` is a plain rule-follower: it is what a correct agent's output looks like, and it proves each
case is solvable (some recommendation scores 1.0 with every applicable EVAL.md rule passing). Scoring uses
checker/check.py when it is importable; otherwise a minimal in-file implementation of the EVAL rules.

It also scores two baselines so the README can report difficulty:
  - `do_nothing`: no trades, empty profile updates.
  - `naive`: v0-like - rebalance to client targets only when a class is >5 points off, ignore life events.

Oracle outputs are never written into case directories (agents must not see them).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(REPO / "agent" / "tools"))
import portfolio as pf  # noqa: E402

BANDS = {1: (0.10, 0.30), 2: (0.30, 0.50), 3: (0.50, 0.70), 4: (0.70, 0.85), 5: (0.85, 1.00)}
SETS = ("practice", "test", "regression", "drift")

try:  # prefer the real checker (source of truth); never edited from here
    sys.path.insert(0, str(REPO))
    from checker.check import check as _real_check  # type: ignore
except Exception:  # pragma: no cover - fallback when checker/ is absent
    _real_check = None

sys.path.insert(0, str(REPO / "checker"))
import rules_ext as RX  # noqa: E402  (extended rules; no-ops for the original event types)

try:  # held-out forward backtest (needs PyYAML for config.yaml)
    sys.path.insert(0, str(ROOT))
    from backtest import backtest as _backtest, holdout_path as _bt_holdout  # type: ignore
except Exception:  # pragma: no cover
    _backtest = _bt_holdout = None


def load_case(d: Path) -> dict:
    j = lambda n: json.loads((d / f"{n}.json").read_text(encoding="utf-8"))  # noqa: E731
    return {"dir": d, "client": j("client"), "holdings": j("holdings"), "market": j("market"),
            "events": j("events").get("events", [])}


def _base_rec(case: dict) -> dict:
    return {"client_id": case["client"]["client_id"], "target_allocation": dict(case["client"]["targets"]),
            "trades": [], "rationale": [],
            "profile_updates": {"goals_add": [], "monthly_contribution": None, "risk_score": None},
            "flags": [], "no_action_reason": None}


def _diagnose(case: dict) -> dict:
    c, m = case["client"], case["market"]
    pre = pf.positions(case["holdings"])
    w = pf.weights(pre, m)
    lo, hi = BANDS[int(c["risk_score"])]
    types = {e["type"] for e in case["events"]}
    need_m = 6 if "layoff" in types else 3
    eq = w["by_class"]["equity"]
    # cash floor implied by base + extended rules (== need_m * expenses for the original event types)
    cash_req = RX.required_cash(c, case["events"], case["holdings"].get("as_of", ""))
    return {
        "pre": pre, "w": w, "lo": lo, "hi": hi, "mid": (lo + hi) / 2, "types": types, "need_m": need_m,
        "cash_req": cash_req, "restricted": RX.restricted_symbols(case["events"]),
        "noise_only": bool(case["events"]) and all(e["type"] in RX.NOISE for e in case["events"]),
        "band_bad": not (lo - 0.005 <= eq <= hi + 0.005),   # checker tolerances (EVAL.md section 1)
        "cash_bad": pre.get("CASH", 0.0) < cash_req - 1,
        "conc_bad": any(v > 0.105 for v in w["single_stocks"].values()),
        "glide_bad": c["age"] >= 55 and eq > (lo + hi) / 2 + 0.005,
        "drifted": any(abs(w["by_class"][k] - c["targets"][k]) > 0.05 for k in ("equity", "bond", "cash")),
    }


def _profile_updates(case: dict, rec: dict) -> None:
    c = case["client"]
    pu, flags = rec["profile_updates"], rec["flags"]
    for e in case["events"]:
        t, det = e["type"], e.get("details") or {}
        if t == "child":
            pu["goals_add"].append({"type": "education", "target_year": int(e["date"][:4]) + 18})
            rec["rationale"].append({"ref": f"event:{e['id']}", "text": "New child: add a college goal 18 years out."})
        elif t == "marriage":
            if "joint_profile_review" not in flags:
                flags.append("joint_profile_review")
            rec["rationale"].append({"ref": f"event:{e['id']}",
                                     "text": "Marriage: review a joint profile with both spouses; risk unchanged until then."})
        elif t == "job_change" and float(det.get("new_income", 0)) > float(c["annual_income"]):
            cur = float(c.get("monthly_contribution") or 0)
            new = max(cur * det["new_income"] / c["annual_income"], cur + 100, det["new_income"] * 0.10 / 12)
            pu["monthly_contribution"] = float(round(new / 50) * 50)
            rec["rationale"].append({"ref": f"event:{e['id']}", "text": "Raise: increase the monthly contribution in step with income."})
        elif t == "divorce":
            flags.append("beneficiary_and_titling_review")
        elif t == "inheritance":
            flags.append("inheritance_tax_basis_review")
        if t in RX.REVIEW_FLAGS and RX.REVIEW_FLAGS[t] not in flags:
            flags.append(RX.REVIEW_FLAGS[t])
            rec["rationale"].append({"ref": f"event:{e['id']}", "text": f"Needs human review: {RX.REVIEW_FLAGS[t]}."})


def recommend(case: dict) -> dict:
    c, m = case["client"], case["market"]
    syms = m["symbols"]
    dx = _diagnose(case)
    pre, T = dx["pre"], dx["w"]["total"]
    rec = _base_rec(case)
    _profile_updates(case, rec)
    # With events present no_churn cannot apply, so a 55+ client near the midpoint is rebalanced proactively
    # (keeps the next quiet quarter from landing in a no_churn-vs-glidepath conflict).
    glide_near = (bool(case["events"]) and not dx["noise_only"] and c["age"] >= 55
                  and dx["w"]["by_class"]["equity"] > dx["mid"] - 0.02)
    if not (dx["band_bad"] or dx["cash_bad"] or dx["conc_bad"] or dx["glide_bad"] or dx["drifted"] or glide_near):
        rec["no_action_reason"] = ("Every asset class is within 5 points of target and the portfolio already meets "
                                   "the emergency-fund, risk-band and concentration checks.")
        return rec

    lo, hi, mid = dx["lo"], dx["hi"], dx["mid"]
    exp = float(c["monthly_expenses"])
    tg = c["targets"]
    cash_usd = max(tg["cash"] * T, dx["cash_req"] * 1.02 + 50)
    e = min(max(tg["equity"], lo + 0.01), hi - 0.01)
    if c["age"] >= 55:
        e = min(e, mid - 0.03)   # buffer so a quarter of market drift rarely re-crosses the midpoint
    if cash_usd / T > 1 - e:
        e = 1 - cash_usd / T
        if e < lo + 0.002:
            raise ValueError(f"{c['client_id']}: infeasible (cash need {cash_usd:,.0f} leaves equity {e:.3f} < {lo})")
    b = 1 - e - cash_usd / T

    # per-symbol post-trade values
    singles = {s: v for s, v in pre.items() if syms.get(s, {}).get("single_stock")}
    # restricted symbols (blackout / insider / lockup) are never traded
    post_single = {s: (v if s in dx["restricted"] else min(v, 0.09 * T)) for s, v in singles.items()}
    fund_eq = e * T - sum(post_single.values())
    if fund_eq < 0:
        locked = sum(v for s, v in post_single.items() if s in dx["restricted"])
        free = sum(v for s, v in post_single.items() if s not in dx["restricted"])
        scale = max(e * T - locked, 0.0) / free if free else 1.0
        post_single = {s: (v if s in dx["restricted"] else v * scale) for s, v in post_single.items()}
        fund_eq = 0.0
    us, intl = pre.get("US_EQ", 0.0), pre.get("INTL_EQ", 0.0)
    share_intl = intl / (us + intl) if us + intl > 0 else 0.3
    target = {"US_EQ": fund_eq * (1 - share_intl), "INTL_EQ": fund_eq * share_intl, "BOND": b * T, **post_single}

    ev_ref = f"event:{case['events'][0]['id']}" if case["events"] else None
    layoff = next((f"event:{x['id']}" for x in case["events"] if x["type"] == "layoff"), None)
    trades, cash_flow = [], 0.0
    for s, tv in target.items():
        if s in dx["restricted"]:
            continue
        diff = round(tv - pre.get(s, 0.0), 2)
        if abs(diff) < 1:
            continue
        if s in singles and diff < 0 and dx["conc_bad"]:
            ref = "rule:concentration"
        elif dx["glide_bad"] and s in ("US_EQ", "INTL_EQ") and diff < 0:
            ref = "rule:glidepath"
        elif dx["band_bad"]:
            ref = "rule:risk_band"
        else:
            ref = ev_ref or "rule:rebalance"
        trades.append({"symbol": s, "action": "buy" if diff > 0 else "sell", "amount_usd": abs(diff), "reason_ref": ref})
        cash_flow -= diff
    cash_flow = round(cash_flow, 2)
    if abs(cash_flow) >= 0.01:
        ref = layoff or ("rule:emergency_fund" if dx["cash_bad"] else ev_ref or "rule:rebalance")
        trades.append({"symbol": "CASH", "action": "buy" if cash_flow > 0 else "sell", "amount_usd": abs(cash_flow),
                       "reason_ref": ref})
    rec["trades"] = trades
    post = pf.post_trade(case["holdings"], trades)
    wpost = pf.weights(post, m)["by_class"]
    ta = {k: round(wpost[k], 3) for k in ("equity", "bond")}
    ta["cash"] = round(1 - ta["equity"] - ta["bond"], 3)
    rec["target_allocation"] = ta
    for ref in sorted({t["reason_ref"] for t in trades}):
        if not any(r["ref"] == ref for r in rec["rationale"]):
            rec["rationale"].append({"ref": ref, "text": f"Trades to satisfy {ref}."})
    return rec


def do_nothing(case: dict) -> dict:
    rec = _base_rec(case)
    rec["no_action_reason"] = "No change."
    return rec


def naive(case: dict) -> dict:
    """v0-like: rebalance class weights to client targets if >5 points off; ignores events and policy."""
    c, m = case["client"], case["market"]
    dx = _diagnose(case)
    rec = _base_rec(case)
    if not dx["drifted"]:
        rec["no_action_reason"] = "Allocation is within 5 points of target."
        return rec
    pre, T = dx["pre"], dx["w"]["total"]
    trades, flow = [], 0.0
    for cls in ("equity", "bond"):
        members = [s for s in pre if m["symbols"][s]["class"] == cls]
        cur = sum(pre[s] for s in members)
        want = c["targets"][cls] * T
        for s in members:
            diff = round((want - cur) * (pre[s] / cur if cur else 1 / len(members)), 2)
            if abs(diff) >= 1:
                trades.append({"symbol": s, "action": "buy" if diff > 0 else "sell", "amount_usd": abs(diff),
                               "reason_ref": "rule:rebalance"})
                flow -= diff
    flow = round(flow, 2)
    if abs(flow) >= 0.01:
        trades.append({"symbol": "CASH", "action": "buy" if flow > 0 else "sell", "amount_usd": abs(flow),
                       "reason_ref": "rule:rebalance"})
    rec["trades"] = trades
    return rec


# ---------------------------------------------------------------- minimal fallback checker (EVAL.md section 2)
def _mini_check(case: dict, rec: dict) -> dict:
    c, m = case["client"], case["market"]
    post = pf.post_trade(case["holdings"], rec["trades"])
    w = pf.weights(post, m)
    lo, hi = BANDS[int(c["risk_score"])]
    types = {e["type"] for e in case["events"]}
    res = []
    eq = w["by_class"]["equity"]
    res.append(("risk_band", "hard", lo - 0.005 <= eq <= hi + 0.005))
    need = 6 if "layoff" in types else 3
    res.append(("emergency_fund", "hard", post.get("CASH", 0) >= need * c["monthly_expenses"] - 1))
    if any(m["symbols"][s].get("single_stock") for s in post):
        res.append(("concentration", "hard", all(v <= 0.105 for v in w["single_stocks"].values())))
    if rec["trades"]:
        ids = {e["id"] for e in case["events"]} | types
        ok = all((r.split(":")[0] == "event" and r.split(":", 1)[1] in ids) or
                 (r.split(":")[0] == "rule" and r.split(":", 1)[1] in
                  {"rebalance", "risk_band", "emergency_fund", "concentration", "glidepath"})
                 for r in (t["reason_ref"] for t in rec["trades"]))
        res.append(("cited", "hard", ok))
    if c["age"] >= 55:
        res.append(("glidepath", "soft", eq <= (lo + hi) / 2 + 0.005))
    n = sum(r[2] for r in res) + 1  # + valid_output (assumed)
    score = n / (len(res) + 1)
    return {"score": round(score, 4), "passed": all(r[2] for r in res if r[1] == "hard") and score >= 0.8,
            "violations": [{"rule": r[0], "severity": r[1]} for r in res if not r[2]]}


def score(case: dict, rec: dict) -> dict:
    if _real_check is not None:
        return _real_check(str(case["dir"]), rec)
    return _mini_check(case, rec)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--case")
    args = ap.parse_args()
    if args.case:
        case = load_case(Path(args.case))
        rec = recommend(case)
        print(json.dumps(rec, indent=2))
        print(json.dumps({k: v for k, v in score(case, rec).items() if k != "results"}, indent=2))
        return 0
    print(f"scoring with: {'checker/check.py' if _real_check else 'built-in minimal rules'}")
    print(f"{'set':<11}{'n':>3}  {'oracle solvable':>16}  {'naive pass':>10}  {'naive mean':>10}  {'do-nothing pass':>15}")
    bad = 0
    bt_rows: list[str] = []
    for s in SETS:
        dirs = sorted(p for p in (ROOT / "cases" / s).iterdir() if p.is_dir()) if (ROOT / "cases" / s).exists() else []
        ok = nv_pass = nv_sum = dn_pass = 0
        bt_acc = {k: {"ret": [], "mdd": [], "cov": [], "breach": 0} for k in ("oracle", "naive", "hold")}
        for d in dirs:
            case = load_case(d)
            try:
                rec = recommend(case)
                r = score(case, rec)
                solved = r["passed"] and r["score"] >= 0.9999
            except ValueError as exc:
                solved, r = False, {"violations": [{"rule": "infeasible", "detail": str(exc)}]}
            if solved:
                ok += 1
            else:
                bad += 1
                print(f"  UNSOLVED {s}/{d.name}: {r['violations']}")
            if args.write:
                out = ROOT / "oracle_out" / s
                out.mkdir(parents=True, exist_ok=True)
                (out / f"{d.name}.json").write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
            nv = score(case, naive(case))
            nv_pass += nv["passed"]
            nv_sum += nv["score"]
            dn_pass += score(case, do_nothing(case))["passed"]
            if _backtest is not None and _bt_holdout(d).exists():
                for name, r in (("oracle", rec), ("naive", naive(case)), ("hold", do_nothing(case))):
                    b = _backtest(d, r)
                    acc = bt_acc[name]
                    acc["ret"].append(b["forward_return"])
                    acc["mdd"].append(b["max_drawdown"])
                    acc["cov"].append(b["min_cash_coverage_months"])
                    acc["breach"] += b["emergency_fund_breached"]
        n = len(dirs) or 1
        print(f"{s:<11}{len(dirs):>3}  {ok:>10}/{len(dirs):<5}  {nv_pass / n:>10.2f}  {nv_sum / n:>10.2f}  {dn_pass / n:>15.2f}")
        for name, acc in bt_acc.items():
            if acc["ret"]:
                m = len(acc["ret"])
                bt_rows.append(f"{s:<11}{name:<8}{sum(acc['ret']) / m:>+10.3f}{min(acc['ret']):>+10.3f}"
                               f"{sum(acc['mdd']) / m:>+10.3f}{sorted(acc['cov'])[m // 2]:>12.1f}{acc['breach']:>6}/{m}")
    if bt_rows:
        print("\nheld-out backtest (scenarios/holdout; extra metric, not a policy rule)")
        print(f"{'set':<11}{'rec':<8}{'mean ret':>10}{'worst ret':>10}{'mean mdd':>10}{'med min cov':>12}{'EF breach':>9}")
        print("\n".join(bt_rows))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
