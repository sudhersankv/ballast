"""Generate web/seed.json: deterministic demo data matching the runtime's Mongo contract.

Run: python web/make_seed.py
"""
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

random.seed(7)
T0 = datetime(2026, 11, 7, 13, 0, tzinfo=timezone.utc)


def ts(minutes):
    return (T0 + timedelta(minutes=minutes)).isoformat()


# ---------- playbooks ----------
V0_SKILLS = """\
  - name: case-review
    description: Use at the start of every client case to read the files and decide on trades.
    body: |
      1. Read client.json, holdings.json and market.json.
      2. Run `python tools/portfolio.py allocation holdings.json` to see current weights by asset class.
      3. Compare the weights with `targets` in client.json and decide whether to trade.
      4. Write a draft recommendation.json, then run `python tools/portfolio.py apply holdings.json recommendation.json`.
      5. Fix the draft if the result looks wrong, then stop.
  - name: recommendation-format
    description: Use before writing recommendation.json, to get the exact output format.
    body: |
      Write one JSON object with keys client_id, target_allocation, trades, rationale,
      profile_updates, flags, no_action_reason. Trades net to zero. Cite every trade.
"""

LAYOFF = """\
  - name: layoff-playbook
    description: Use when events include a layoff or job loss.
    body: |
      1. Compute 6 months of expenses from client.json.
      2. Raise CASH to that level first, selling the most overweight holding.
      3. Only then rebalance the rest toward target. Cite the event id on each trade.
"""

LIFE = """\
  - name: life-event-updates
    description: Use when events include a child, marriage or job change.
    body: |
      - child: add an education goal 18 years after the event date.
      - marriage: add the flag joint_profile_review; leave risk_score unchanged.
      - job_change with higher income: raise monthly_contribution; leave risk_score unchanged.
"""

CHURN = """\
  - name: rebalance-check
    description: Use before writing any trades.
    body: |
      Run portfolio.py allocation. If every class is within 5 points of target and there
      are no new events, write no trades and give a no_action_reason.
"""

CONC = """\
  - name: concentration-guard
    description: Use when holdings include a single stock.
    body: |
      Check each single stock's weight after trades. If any is above the house limit,
      trim it first and move the proceeds to the most underweight class.
"""

SEVERANCE_BAD = """\
  - name: layoff-playbook
    description: Use when events include a layoff or job loss.
    body: |
      1. Count severance from events.json toward the cash buffer.
      2. If severance covers the gap, skip raising CASH.
      3. Rebalance the rest toward target.
"""

WINDFALL = """\
  - name: windfall-and-shock
    description: Use when events include an inheritance or divorce, or when prices moved sharply.
    body: |
      1. Recompute weights with today's prices before anything else.
      2. Inheritance: deploy new cash in stages toward target, keeping the cash buffer intact.
      3. Divorce: split shared holdings per details, then recheck the cash buffer on the new expenses.
      4. After a market drop, restore the cash buffer before buying equity.
"""


def yaml_for(version, parent, skills, changelog, max_turns=12):
    prompt = (
        "  You are a portfolio assistant for one client. You recommend trades; you never execute them.\n"
        "  The case files are in your working directory. When you are done, write recommendation.json there and stop.\n"
    )
    if version >= 1:
        prompt += "  Always read events.json before computing trades.\n"
    return (
        f"version: {version}\n"
        f"parent: {'null' if parent is None else parent}\n"
        "model: meta/muse\n"
        "prompt: |\n" + prompt +
        "skills:\n" + skills +
        "tools: [read, bash, write]\n"
        f"max_turns: {max_turns}\n"
        f'changelog: "{changelog}"\n'
    ) + (yaml.safe_dump({"lessons": lessons_for(version)}, sort_keys=False, width=200, allow_unicode=True) if lessons_for(version) else "")


PB = [
    # version, parent, skills, changelog, status, minute
    (0, None, V0_SKILLS, "Initial guideline: read files, rebalance toward targets, output format.", "shipped", 0),
    (1, 0, V0_SKILLS + LAYOFF, "Added layoff-playbook after emergency_fund failures on layoff cases.", "shipped", 40),
    (2, 1, V0_SKILLS + SEVERANCE_BAD, "Let severance count toward the cash buffer to reduce selling.", "rejected", 75),
    (3, 1, V0_SKILLS + LAYOFF + LIFE + CHURN, "Added life-event-updates and rebalance-check for no_churn and event rules.", "shipped", 110),
    (4, 3, V0_SKILLS + LAYOFF + LIFE + CHURN + CONC, "Added concentration-guard for single-stock limits.", "rolled_back", 150),
    (5, 4, V0_SKILLS + LAYOFF + LIFE + CHURN + CONC + WINDFALL, "Added windfall-and-shock after drift on inheritance and market-drop cases.", "shipped", 215),
]

# Lessons Muse writes into each playbook (first person, plain language). They accumulate along the shipped lineage.
def L(lesson, root_cause, triggered_by, rule, skill):
    return {"lesson": lesson, "root_cause": root_cause, "triggered_by": triggered_by, "rule": rule, "skill": skill}

LESSONS = {
    1: [L("After a layoff, I build six months of cash before rebalancing anything else.",
          "Rebalanced to normal targets and left 2.7 months of cash where 6 were needed.", "layoff", "emergency_fund", "layoff-playbook")],
    2: [L("Severance counts toward the cash buffer, so I can sell less after a layoff.",
          "Sold equity to raise cash the client was already about to receive.", "layoff", "emergency_fund", "layoff-playbook")],
    3: [L("When a child arrives, I add an education goal 18 years out.",
          "Treated a new child as no change and added no education goal.", "child", "event_child", "life-event-updates"),
        L("After a marriage, I flag a joint review and leave the risk score alone.",
          "Changed nothing after a marriage and never flagged the joint profile.", "marriage", "event_marriage", "life-event-updates"),
        L("When income rises, I raise the monthly contribution, not the risk.",
          "Left the monthly contribution at $1,500 after a raise.", "job_change", "event_job_change", "life-event-updates"),
        L("If nothing changed and every class is within five points of target, I leave the portfolio alone.",
          "Made 3 small trades in a portfolio that was already on target.", "no new events", "no_churn", "rebalance-check")],
    4: [L("I trim any single stock above ten percent before anything else.",
          "Kept ACME at 13% of the portfolio while rebalancing around it.", "single-stock holding", "concentration", "concentration-guard")],
    5: [L("After a market drop, I restore the cash buffer before buying any equity.",
          "Bought the dip and left 1.4 months of cash after prices fell.", "market drop", "emergency_fund", "windfall-and-shock"),
        L("I invest an inheritance in stages and stay inside the risk band.",
          "Put a large inheritance straight into equity, reaching 91% in a 50-70% band.", "inheritance", "risk_band", "windfall-and-shock"),
        L("I only cite events that are actually in the client's file.",
          "Cited event:windfall, an event the client never reported.", "unfamiliar event types", "cited", "windfall-and-shock")],
}
PARENT = {v: p for v, p, *_ in PB}
STATUS = {v: st for v, _, _, _, st, _ in PB}


def lessons_for(v):
    chain, cur = [], v
    while cur is not None:
        chain.append(cur)
        cur = PARENT[cur]
    out = []
    for x in reversed(chain):
        if x == v or STATUS[x] != "rejected":
            out += LESSONS.get(x, [])
    return out

playbooks = [
    {"version": v, "parent": p, "yaml": yaml_for(v, p, s, c), "changelog": c, "status": st, "created_at": ts(m)}
    for v, p, s, c, st, m in PB
]

# ---------- generations ----------
def sc(mean, pr):
    return {"mean_score": mean, "pass_rate": pr}

generations = [
    {"version": 0, "parent": None, "mode": "training", "practice": sc(0.61, 0.40), "test": sc(0.63, 0.45),
     "regression": sc(1.0, 1.0), "decision": "shipped", "reason": "baseline", "compliance": None, "created_at": ts(5)},
    {"version": 1, "parent": 0, "mode": "training", "practice": sc(0.72, 0.55), "test": sc(0.74, 0.60),
     "regression": sc(1.0, 1.0), "decision": "shipped", "reason": "test +0.11, regression 100%",
     "compliance": {"reviewer": "gemini", "verdict": "approve", "note": "Adds a cash-first habit; no policy rule loosened."},
     "created_at": ts(45)},
    {"version": 2, "parent": 1, "mode": "training", "practice": sc(0.78, 0.65), "test": sc(0.71, 0.55),
     "regression": sc(0.9, 0.9), "decision": "rejected", "reason": "invalid_playbook: compliance block",
     "compliance": {"reviewer": "gemini", "verdict": "block",
                    "note": "Counting severance as cash weakens emergency_fund, which only counts CASH holdings."},
     "created_at": ts(80)},
    {"version": 3, "parent": 1, "mode": "training", "practice": sc(0.84, 0.75), "test": sc(0.86, 0.80),
     "regression": sc(1.0, 1.0), "decision": "shipped", "reason": "test +0.12, regression 100%",
     "compliance": {"reviewer": "gemini", "verdict": "approve", "note": "Event habits only; thresholds untouched."},
     "created_at": ts(115)},
    {"version": 4, "parent": 3, "mode": "training", "practice": sc(0.88, 0.80), "test": sc(0.89, 0.85),
     "regression": sc(1.0, 1.0), "decision": "shipped", "reason": "test +0.03, regression 100%",
     "compliance": {"reviewer": "gemini", "verdict": "approve", "note": "Trims single stocks; limit stays in the checker."},
     "created_at": ts(155)},
    {"version": 5, "parent": 4, "mode": "drift", "practice": sc(0.90, 0.85), "test": sc(0.91, 0.90),
     "regression": sc(1.0, 1.0), "decision": "shipped", "reason": "passes 10/10 drift cases, regression 100%",
     "compliance": {"reviewer": "gemini", "verdict": "approve", "note": "Adds handling for new event types; no rule loosened."},
     "created_at": ts(220)},
]

# ---------- drift events ----------
drift_cases = [f"d-{i:03d}" for i in range(1, 11)]
drift_events = [
    {"time": ts(158), "level": "green", "rolling_score": 0.89, "baseline": 0.89, "violations": [],
     "action": "none", "from_version": 4, "to_version": 4, "case_ids": []},
    # SubQ Snap decision gate: fired by the MongoDB change stream on each new life event, before the agent runs
    {"time": ts(176), "level": "yellow", "action": "event_gate", "from_version": 4, "to_version": 4, "case_ids": ["c-021"],
     "violations": [], "rolling_score": 0.89, "baseline": 0.89,
     "gates": [
         {"case_id": "c-021", "event": "layoff", "model": "subq-snap-1.1",
          "rule_risk": {"emergency_fund": 0.999, "risk_band": 0.21, "concentration": 0.64, "cited": 0.08},
          "at_risk": ["emergency_fund", "concentration"], "covered": 0.017, "urgency": 3, "rerun_now": True,
          "seconds": 0.78, "input_tokens": 1412},
         {"case_id": "d-003", "event": "inheritance", "model": "subq-snap-1.1",
          "rule_risk": {"risk_band": 0.93, "emergency_fund": 0.12, "cited": 0.71},
          "at_risk": ["risk_band", "cited"], "covered": 0.04, "urgency": 3, "rerun_now": True,
          "seconds": 0.61, "input_tokens": 1388},
         {"case_id": "c-007", "event": "child", "model": "subq-snap-1.1",
          "rule_risk": {"event_child": 0.06, "emergency_fund": 0.05},
          "at_risk": [], "covered": 0.97, "urgency": 0, "rerun_now": False,
          "seconds": 0.44, "input_tokens": 1356},
     ]},
    {"time": ts(185), "level": "red", "rolling_score": 0.58, "baseline": 0.89,
     "violations": [
         {"rule": "emergency_fund", "severity": "hard", "detail": "cash 1.4 months after market drop, needs 3"},
         {"rule": "risk_band", "severity": "hard", "detail": "equity 91% after inheritance, band 50-70% for risk 3"},
         {"rule": "cited", "severity": "hard", "detail": "trade US_EQ buy 40,000 cites event:windfall, not in events.json"},
     ],
     "snap": {"model": "subq-snap-1.1", "level": "red", "level_p": {"green": 0.01, "yellow": 0.03, "red": 0.96},
              "rollback_p": 0.94, "rule": "emergency_fund", "rule_p": 0.97, "novel_p": 0.88, "urgency": 3,
              "rule_level": "red", "agrees": True},
     "action": "rollback", "from_version": 4, "to_version": 3, "case_ids": drift_cases[:7]},
    {"time": ts(200), "level": "red", "rolling_score": 0.66, "baseline": 0.89,
     "violations": [{"rule": "emergency_fund", "severity": "hard", "detail": "cash 2.6 months after divorce split, needs 3"}],
     "action": "realign", "from_version": 3, "to_version": 3, "case_ids": drift_cases},
    {"time": ts(222), "level": "green", "rolling_score": 0.91, "baseline": 0.89, "violations": [],
     "action": "shipped_fix", "from_version": 3, "to_version": 5, "case_ids": drift_cases},
]

# ---------- clients + runs ----------
FIRST = ["Maya", "Jonah", "Priya", "Theo", "Ines", "Kofi", "Lena", "Arjun", "Sofia", "Malik",
         "Hana", "Diego", "Ruth", "Omar", "Elise", "Kenji", "Nadia", "Felix", "Amara", "Wes"]
LAST = ["Okafor", "Lindqvist", "Raman", "Castillo", "Weber", "Mensah", "Novak", "Iyer", "Brandt", "Haddad",
        "Sato", "Ferreira", "Kowalski", "Aziz", "Moreau", "Tanaka", "Petrov", "Huber", "Diallo", "Park"]
EVENT_PLAN = ["layoff", None, "child", "marriage", None, "job_change", "layoff", None, "child", "age55",
              None, "marriage", "layoff", "job_change", None, "child", "layoff", None, "marriage", "age55"]
BANDS = {1: (0.10, 0.30), 2: (0.30, 0.50), 3: (0.50, 0.70), 4: (0.70, 0.85), 5: (0.85, 1.00)}

clients, runs = [], []
for i in range(20):
    cid = f"c-{i + 1:03d}"
    ev = EVENT_PLAN[i]
    risk = random.choice([2, 3, 3, 4, 4, 5]) if ev != "age55" else random.choice([2, 3])
    age = random.randint(57, 63) if ev == "age55" else random.randint(28, 52)
    expenses = random.choice([3800, 4400, 5200, 6100, 7000])
    total = random.choice([95000, 120000, 139000, 180000, 240000])
    lo, hi = BANDS[risk]
    tgt_eq = round((lo + hi) / 2, 2)
    tgt_cash = 0.10
    targets = {"equity": tgt_eq, "bond": round(1 - tgt_eq - tgt_cash, 2), "cash": tgt_cash}
    events = []
    if ev and ev != "age55":
        events.append({"id": "e1", "type": ev, "date": f"2026-10-{random.randint(2, 28):02d}"})

    cash_now = round(total * 0.06)
    single = round(total * random.choice([0.04, 0.08, 0.13]))
    trades, rationale, updates, flags = [], [], {"goals_add": [], "monthly_contribution": None, "risk_score": None}, []
    no_action = None
    if ev == "layoff":
        need = expenses * 6 - cash_now
        trades = [{"symbol": "US_EQ", "action": "sell", "amount_usd": need, "reason_ref": "event:e1"},
                  {"symbol": "CASH", "action": "buy", "amount_usd": need, "reason_ref": "rule:emergency_fund"}]
        rationale = [{"ref": "event:e1", "text": f"Job loss: raise cash to 6 months of expenses (${expenses * 6:,})."},
                     {"ref": "rule:emergency_fund", "text": "Cash buffer comes first after a layoff."}]
    elif ev == "child":
        yr = 2026 + 18
        updates["goals_add"] = [{"type": "education", "target_year": yr}]
        rationale = [{"ref": "event:e1", "text": f"New child: education goal for {yr}."}]
        no_action = "Allocation within 5 points of target; goal added."
    elif ev == "marriage":
        flags = ["joint_profile_review"]
        rationale = [{"ref": "event:e1", "text": "Marriage: joint profile review before any risk change."}]
        no_action = "Holding until the joint review."
    elif ev == "job_change":
        updates["monthly_contribution"] = 2200
        rationale = [{"ref": "event:e1", "text": "Higher income: raise monthly contribution to $2,200."}]
        no_action = "Allocation on target; contribution raised."
    elif ev == "age55":
        amt = round(total * 0.06)
        trades = [{"symbol": "US_EQ", "action": "sell", "amount_usd": amt, "reason_ref": "rule:glidepath"},
                  {"symbol": "BOND", "action": "buy", "amount_usd": amt, "reason_ref": "rule:glidepath"}]
        rationale = [{"ref": "rule:glidepath", "text": f"Age {age}: move equity to the lower half of the band."}]
    else:
        no_action = "Every class within 5 points of target and no new events."
    if single > total * 0.10:
        trim = single - round(total * 0.09)
        trades += [{"symbol": "ACME", "action": "sell", "amount_usd": trim, "reason_ref": "rule:concentration"},
                   {"symbol": "INTL_EQ", "action": "buy", "amount_usd": trim, "reason_ref": "rule:concentration"}]
        rationale.append({"ref": "rule:concentration", "text": f"ACME is {single / total:.0%} of the portfolio; trim to 9%."})
        no_action = None

    rec = {"client_id": cid, "target_allocation": targets, "trades": trades, "rationale": rationale,
           "profile_updates": updates, "flags": flags, "no_action_reason": no_action}

    clients.append({
        "client_id": cid, "name": f"{FIRST[i]} {LAST[i]}", "age": age, "risk_score": risk,
        "monthly_expenses": expenses, "portfolio_value": total,
        "events": [{"type": e["type"], "date": e["date"]} for e in events],
        "agent_version": 5, "last_recommendation": rec,
    })

    # runs: test set, every version. v0 misses events; improves per version.
    for g in generations:
        v = g["version"]
        viol = []
        if v == 0 and ev == "layoff":
            left = 2.7 if i == 0 else round(random.uniform(2.1, 3.1), 1)
            viol.append({"rule": "emergency_fund", "severity": "hard",
                         "detail": f"cash {left} months after rebalancing to normal targets, needs 6 after layoff"})
        if v <= 2 and ev == "child":
            viol.append({"rule": "event_child", "severity": "soft", "detail": "no education goal added for new child"})
        if v <= 2 and ev == "marriage":
            viol.append({"rule": "event_marriage", "severity": "soft", "detail": "joint_profile_review flag missing"})
        if v <= 2 and ev == "job_change":
            viol.append({"rule": "event_job_change", "severity": "soft", "detail": "monthly_contribution unchanged at $1,500"})
        if v <= 2 and ev is None and random.random() < 0.5:
            viol.append({"rule": "no_churn", "severity": "soft", "detail": "3 trades while every class was within 5 points"})
        if v <= 3 and single > total * 0.10:
            viol.append({"rule": "concentration", "severity": "hard",
                         "detail": f"ACME {single / total:.1%} of portfolio, max 10%"})
        if v == 2 and ev == "layoff":
            viol.append({"rule": "emergency_fund", "severity": "hard",
                         "detail": f"cash {cash_now / expenses:.1f} months, needs 6 after layoff (severance not counted)"})
        if v == 5 and i in (4, 13):
            viol.append({"rule": "no_churn", "severity": "soft", "detail": "2 small trades while every class was within 5 points"})
        if v == 5 and i == 9:
            viol.append({"rule": "glidepath", "severity": "soft", "detail": "equity 63% at age 60, should be at or below 60%"})
        n_rules = 6 + (1 if ev else 0)
        score = round(max(0.0, 1 - len(viol) / n_rules), 2)
        hard = any(x["severity"] == "hard" for x in viol)
        # rule-by-rule results, with the numeric detail a passing check reports too
        need = 6 if ev == "layoff" else 3
        cash_after = 6.0 if ev == "layoff" else round(cash_now / expenses + 1.2, 1)
        passing = {
            "valid_output": "ok",
            "risk_band": f"equity {tgt_eq:.0%} within {lo:.0%}-{hi:.0%} for risk {risk}",
            "emergency_fund": f"cash {cash_after} months, needs {need}" + (" after layoff" if ev == "layoff" else ""),
            "cited": "all trades cited",
            "concentration": f"ACME {min(single / total, 0.09):.1%} of portfolio, max 10%",
            "no_churn": "no trades; every class within 5 points",
            "event_child": f"education goal added for {2026 + 18}",
            "event_marriage": "joint_profile_review flagged; risk score unchanged",
            "event_job_change": "monthly contribution raised to $2,200",
            "glidepath": "equity at or below the band midpoint",
        }
        applicable = ["valid_output", "risk_band", "emergency_fund", "cited", "concentration"]
        applicable += {"child": ["event_child"], "marriage": ["event_marriage"], "job_change": ["event_job_change"],
                       "age55": ["glidepath"], None: ["no_churn"]}.get(ev, [])
        bad = {x["rule"]: x for x in viol}
        results = [{"rule": r, "severity": "hard" if r in ("valid_output", "risk_band", "emergency_fund", "cited", "concentration") else "soft",
                    "passed": r not in bad, "detail": bad[r]["detail"] if r in bad else passing[r]} for r in applicable]
        for set_name, case in (("test", cid), ("practice", f"p-{i + 1:03d}")):
            runs.append({
                "run_id": f"r-{v}{i + 1:03d}" if set_name == "test" else f"p-{v}{i + 1:03d}",
                "playbook_version": v, "case_id": case, "set": set_name, "model": "muse",
                "score": score, "passed": (not hard) and score >= 0.8, "violations": viol, "results": results,
                "recommendation": rec if v == 5 and set_name == "test" else None,
                "tokens_in": random.randint(9000, 16000), "tokens_out": random.randint(700, 1600),
                "seconds": round(random.uniform(24, 70), 1), "created_at": g["created_at"],
            })

drift_analysis = [{
    "time": ts(192), "analyst": "subq", "model": "subq-snap-1.1",
    "runs_read": 240, "client_timelines": 60, "playbook_versions": 5, "tokens_read": 1_420_000,
    "seconds": 38.4, "mode": "single long-context pass",
    "summary": "One pass over 240 runs, 60 client timelines and 5 playbook versions. The drift is systematic, not random: "
               "it clusters where a cash shock hits a portfolio the playbook already considers balanced.",
    "patterns": [
        {"rule": "emergency_fund", "condition": "layoff + single-stock holding, after a market drop",
         "failure_rate": 0.70, "runs": 30, "example": "cash 1.4 months after market drop, needs 3"},
        {"rule": "risk_band", "condition": "inheritance over 25% of portfolio value",
         "failure_rate": 0.62, "runs": 21, "example": "equity 91% after inheritance, band 50-70% for risk 3"},
        {"rule": "cited", "condition": "event types the playbook has never seen (inheritance, divorce)",
         "failure_rate": 0.48, "runs": 27, "example": "trade cites event:windfall, not in events.json"},
    ],
    "handoff": "Muse gets these 3 patterns plus 8 example traces, not raw logs.",
}]

benchmarks = [
    {"model": "muse", "label": "Muse", "provider": "Meta Model API", "playbook_version": 5,
     "mean_score": 0.91, "pass_rate": 0.90, "tokens": 13200, "seconds": 41.0},
    {"model": "gemini", "label": "Gemini", "provider": "Google DeepMind", "playbook_version": 5,
     "mean_score": 0.88, "pass_rate": 0.85, "tokens": 14100, "seconds": 36.5},
    {"model": "subq", "label": "SubQ", "provider": "Subquadratic", "playbook_version": 5,
     "mean_score": 0.84, "pass_rate": 0.80, "tokens": 15800, "seconds": 52.2},
]

# ---------- client journeys: one client across years of life events and market regimes ----------
# Each checkpoint runs twice: the generic agent (v0, "baseline") and this client's own agent ("personal"),
# whose playbook gains a lesson right after it fails a train checkpoint. Holdout checkpoints are never trained on.
JOURNEYS = [
    {"journey_id": "j-001",
     "persona": {"name": "Dana Whitfield", "age": 41, "occupation": "product manager", "risk_score": 4, "household": "married in 2019, one child in 2022"},
     "arc": "Marriage, a layoff in the COVID crash, a better job, a first child during the 2022 rate shock, then an inheritance.",
     "regimes": [{"name": "COVID crash", "kind": "crash", "start": "2020-02-20", "end": "2020-06-30"},
                 {"name": "2022 rate shock", "kind": "rates", "start": "2022-03-01", "end": "2022-10-31"}],
     "checkpoints": [
         {"id": "t01", "date": "2019-06-30", "events": ["marriage"], "regime": None, "split": "train"},
         {"id": "t02", "date": "2019-12-31", "events": [], "regime": None, "split": "holdout"},
         {"id": "t03", "date": "2020-03-31", "events": ["layoff"], "regime": "COVID crash", "split": "train"},
         {"id": "t04", "date": "2020-12-31", "events": ["job_change"], "regime": None, "split": "train"},
         {"id": "t05", "date": "2021-06-30", "events": [], "regime": None, "split": "holdout"},
         {"id": "t06", "date": "2022-03-31", "events": ["child"], "regime": "2022 rate shock", "split": "holdout"},
         {"id": "t07", "date": "2022-09-30", "events": ["market_drop"], "regime": "2022 rate shock", "split": "holdout"},
         {"id": "t08", "date": "2023-06-30", "events": ["inheritance"], "regime": None, "split": "holdout"},
     ],
     # (checkpoint, generic-agent violation, personal version that served it, personal violation or None, lesson learned there)
     "plan": [
         ("t01", ("event_marriage", "no joint_profile_review flag after marriage"), 0, ("event_marriage", "no joint_profile_review flag after marriage"), 3),
         ("t02", ("no_churn", "4 trades while every class was within 5 points"), 1, None, None),
         ("t03", ("emergency_fund", "cash 2.7 months after rebalancing to normal targets, needs 6 after layoff"), 1, ("emergency_fund", "cash 2.7 months, needs 6 after layoff"), 1),
         ("t04", ("event_job_change", "monthly_contribution unchanged at $1,500 after a raise"), 2, ("event_job_change", "monthly_contribution unchanged at $1,500 after a raise"), 3),
         ("t05", ("no_churn", "3 trades while every class was within 5 points"), 3, None, None),
         ("t06", ("event_child", "no education goal added for new child"), 3, None, None),
         ("t07", ("emergency_fund", "cash 1.9 months after an 18% market drop, needs 3"), 3, None, None),
         ("t08", ("risk_band", "equity 88% after inheritance, band 70-85% for risk 4"), 3, None, None),
     ],
     "lesson_at": {"t01": 1, "t03": 0, "t04": 2}},
    {"journey_id": "j-002",
     "persona": {"name": "Marcus Bell", "age": 58, "occupation": "plant manager", "risk_score": 3, "household": "two adult children"},
     "arc": "Ten years from retirement when the 2008 crisis hits, a divorce in 2010, then retirement in 2015.",
     "regimes": [{"name": "Global financial crisis", "kind": "crash", "start": "2008-09-15", "end": "2009-03-31"}],
     "checkpoints": [
         {"id": "t01", "date": "2007-12-31", "events": [], "regime": None, "split": "train"},
         {"id": "t02", "date": "2008-12-31", "events": ["market_drop"], "regime": "Global financial crisis", "split": "train"},
         {"id": "t03", "date": "2009-06-30", "events": [], "regime": None, "split": "holdout"},
         {"id": "t04", "date": "2010-09-30", "events": ["divorce"], "regime": None, "split": "train"},
         {"id": "t05", "date": "2012-12-31", "events": [], "regime": None, "split": "holdout"},
         {"id": "t06", "date": "2015-06-30", "events": ["retirement"], "regime": None, "split": "holdout"},
     ],
     "plan": [
         ("t01", ("glidepath", "equity 68% at age 58, should be at or below 60%"), 0, ("glidepath", "equity 68% at age 58, should be at or below 60%"), None),
         ("t02", ("emergency_fund", "cash 1.6 months after a 38% market drop, needs 3"), 1, ("emergency_fund", "cash 1.6 months after a 38% market drop, needs 3"), 1),
         ("t03", ("glidepath", "equity 66% at age 59, should be at or below 60%"), 2, None, None),
         ("t04", ("emergency_fund", "cash 2.2 months on the new single-household expenses, needs 3"), 2, ("emergency_fund", "cash 2.2 months on the new single-household expenses, needs 3"), 2),
         ("t05", ("glidepath", "equity 64% at age 62, should be at or below 60%"), 3, None, None),
         ("t06", ("emergency_fund", "cash 2.4 months at retirement, needs 3"), 3, None, None),
     ],
     "lesson_at": {}},
]
JLESSONS = {
    "j-001": [
        {"at": "t03", "version": 2, **L("After a layoff, I build six months of cash before rebalancing anything else.",
                                         "Rebalanced to normal targets and left 2.7 months of cash where 6 were needed.", "layoff", "emergency_fund", "layoff-playbook")},
        {"at": "t01", "version": 1, **L("After a marriage, I flag a joint review and leave the risk score alone.",
                                         "Changed nothing after the marriage and never flagged the joint profile.", "marriage", "event_marriage", "life-event-updates")},
        {"at": "t04", "version": 3, **L("When income rises, I raise the monthly contribution, not the risk.",
                                         "Left the monthly contribution at $1,500 after Dana's raise.", "job_change", "event_job_change", "life-event-updates")},
    ],
    "j-002": [
        {"at": "t01", "version": 1, **L("Within ten years of retirement, I keep equity in the lower half of the band.",
                                         "Held 68% equity at 58 with retirement nine years out.", "approaching retirement", "glidepath", "glidepath-check")},
        {"at": "t02", "version": 2, **L("After a market drop, I restore the cash buffer before buying any equity.",
                                         "Bought the dip in late 2008 and left 1.6 months of cash.", "market drop", "emergency_fund", "windfall-and-shock")},
        {"at": "t04", "version": 3, **L("After a divorce, I recompute the cash buffer on the new household's expenses.",
                                         "Kept the old joint-household buffer, 2.2 months for one person.", "divorce", "emergency_fund", "life-event-updates")},
    ],
}
journeys, jruns = [], []
for j in JOURNEYS:
    plan = j.pop("plan")
    j.pop("lesson_at")
    j["lessons"] = JLESSONS[j["journey_id"]]
    journeys.append(j)
    for k, (cp, gv, pv, pviol, _) in enumerate(plan):
        date = next(c["date"] for c in j["checkpoints"] if c["id"] == cp)
        for track, ver, viol in (("baseline", 0, gv), ("personal", pv, pviol)):
            vs = [{"rule": viol[0], "severity": "hard" if viol[0] in ("emergency_fund", "risk_band", "concentration", "cited") else "soft", "detail": viol[1]}] if viol else []
            hard = any(x["severity"] == "hard" for x in vs)
            score = round(1 - len(vs) / 6, 3)
            jruns.append({"run_id": f"jr-{j['journey_id'][2:]}{cp}-{track[0]}", "playbook_version": ver, "case_id": f"{j['journey_id']}/{cp}",
                          "set": "journey", "track": track, "model": "muse", "score": score, "passed": not hard and score >= 0.8,
                          "violations": vs, "results": [], "created_at": f"{date}T12:00:00+00:00"})
runs += jruns

seed = {"playbooks": playbooks, "generations": generations, "drift_events": drift_events,
        "clients": clients, "runs": runs, "drift_analysis": drift_analysis, "benchmarks": benchmarks, "journeys": journeys}
out = Path(__file__).with_name("seed.json")
out.write_text(json.dumps(seed, indent=1))
print(f"wrote {out} ({len(runs)} runs, {len(clients)} clients)")
