"""Generate web/seed.json: deterministic demo data matching the runtime's Mongo contract.

Run: python web/make_seed.py
"""
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
    )


PB = [
    # version, parent, skills, changelog, status, minute
    (0, None, V0_SKILLS, "Initial guideline: read files, rebalance toward targets, output format.", "shipped", 0),
    (1, 0, V0_SKILLS + LAYOFF, "Added layoff-playbook after emergency_fund failures on layoff cases.", "shipped", 40),
    (2, 1, V0_SKILLS + SEVERANCE_BAD, "Let severance count toward the cash buffer to reduce selling.", "rejected", 75),
    (3, 1, V0_SKILLS + LAYOFF + LIFE + CHURN, "Added life-event-updates and rebalance-check for no_churn and event rules.", "shipped", 110),
    (4, 3, V0_SKILLS + LAYOFF + LIFE + CHURN + CONC, "Added concentration-guard for single-stock limits.", "rolled_back", 150),
    (5, 4, V0_SKILLS + LAYOFF + LIFE + CHURN + CONC + WINDFALL, "Added windfall-and-shock after drift on inheritance and market-drop cases.", "shipped", 215),
]

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
    {"time": ts(185), "level": "red", "rolling_score": 0.58, "baseline": 0.89,
     "violations": [
         {"rule": "emergency_fund", "severity": "hard", "detail": "cash 1.4 months after market drop, needs 3"},
         {"rule": "risk_band", "severity": "hard", "detail": "equity 91% after inheritance, band 50-70% for risk 3"},
         {"rule": "cited", "severity": "hard", "detail": "trade US_EQ buy 40,000 cites event:windfall, not in events.json"},
     ],
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
        runs.append({
            "run_id": f"r-{v}{i + 1:03d}", "playbook_version": v, "case_id": cid, "set": "test", "model": "muse",
            "score": score, "passed": (not hard) and score >= 0.8, "violations": viol,
            "recommendation": rec if v == 5 else None,
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

seed = {"playbooks": playbooks, "generations": generations, "drift_events": drift_events,
        "clients": clients, "runs": runs, "drift_analysis": drift_analysis, "benchmarks": benchmarks}
out = Path(__file__).with_name("seed.json")
out.write_text(json.dumps(seed, indent=1))
print(f"wrote {out} ({len(runs)} runs, {len(clients)} clients)")
