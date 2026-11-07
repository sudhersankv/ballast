"""SubQ Snap decision gates for ballast. drift checking.

Snap (POST /v1/systemone, model subq-snap-1.1) answers structured questions about a `state`
with calibrated probabilities: noul (yes/no), choice (one option), score (ordered levels).
Input-only billing ($0.04 / 1M tokens), 384K-token window.

Two gates:
  event_gate(case, event, playbook)   -- per new life event, BEFORE the agent runs:
      which rules does this event put at risk, and does the current playbook cover it?
  window_verdict(window, baseline, trusted, rule_report)  -- AFTER runs, over the last N checks:
      roll back? drift level? which rule? how urgent? novel condition?

The rule-based checker stays the source of truth for pass/fail. Snap adds early warning
(event gate) and an independent second opinion on rollback (window verdict). Disagreements
are logged so thresholds can be calibrated (see snap_calibrate.py).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

URL = (os.environ.get("SUBQ_BASE_URL") or "https://api.subq.ai/v1").rstrip("/") + "/systemone"
MODEL = os.environ.get("SUBQ_SNAP_MODEL", "subq-snap-1.1")
MAX_STATE_CHARS = 900_000  # ~250K tokens: stay well under the 393,216-token window
CONFIG = Path(__file__).resolve().parent / "snap_thresholds.json"

RULE_TEXT = {
    "risk_band": "equity share must sit inside the band for the client's risk score",
    "emergency_fund": "cash must cover 3 months of expenses, or 6 after a layoff; severance does not count",
    "concentration": "no single stock above 10% of the portfolio",
    "cited": "every trade must cite a life event or rule from the case",
    "no_churn": "no trades when the portfolio is within 5 points of target and nothing happened",
    "event_child": "a new child needs an education goal 18 years out",
    "event_marriage": "marriage needs a joint-profile review flag and no unilateral risk change",
    "event_job_change": "a raise should raise the monthly contribution",
    "glidepath": "clients 55 or older keep equity in the low half of their band",
}
DEFAULT_THRESHOLDS = {"event_risk": 0.6, "uncovered": 0.5, "rollback": 0.8}


def thresholds() -> dict:
    try:
        return {**DEFAULT_THRESHOLDS, **json.loads(CONFIG.read_text())}
    except Exception:
        return dict(DEFAULT_THRESHOLDS)


def decide(state: str | dict | list, questions: dict, model: str = MODEL) -> dict:
    """One Decisions API call. Returns {answers, usage, seconds} or raises."""
    if not isinstance(state, str):
        state = json.dumps(state, default=str)
    state = state[:MAX_STATE_CHARS]
    t0 = time.time()
    r = httpx.post(URL, timeout=120, headers={"Authorization": f"Bearer {os.environ['SUBQ_API_KEY']}"},
                   json={"model": model, "state": state, "questions": questions})
    if r.status_code != 200:
        raise RuntimeError(f"snap {r.status_code}: {r.text[:300]}")
    out = r.json()
    return {"model": out.get("model", model), "answers": out["answers"],
            "input_tokens": (out.get("usage") or {}).get("input_tokens", 0),
            "seconds": round(time.time() - t0, 2)}


def _skills_text(playbook: dict) -> str:
    lines = [f"[PROMPT] {(playbook.get('prompt') or '').strip()}"]
    for s in playbook.get("skills") or []:
        body = " ".join(str(s.get("body", "")).split())[:600]
        lines.append(f"[SKILL {s['name']}] when: {s.get('description', '')} | steps: {body}")
    return "\n".join(lines)


# ---- gate 1: per life event, before the agent runs ------------------------------
def event_gate(case: dict, event: dict, playbook: dict) -> dict:
    c, h = case["client"], case["holdings"]
    state = (
        "--- CLIENT ---\n" + json.dumps({k: c.get(k) for k in (
            "age", "annual_income", "monthly_expenses", "dependents", "risk_score", "targets",
            "monthly_contribution", "goals")}) +
        "\n--- HOLDINGS ---\n" + json.dumps(h.get("positions")) +
        "\n--- NEW LIFE EVENT ---\n" + json.dumps(event) +
        "\n--- EARLIER EVENTS ---\n" + json.dumps([e for e in case.get("events", []) if e is not event]) +
        "\n--- AGENT PLAYBOOK (what the agent has been taught) ---\n" + _skills_text(playbook)
    )
    q = {f"risk_{r}": {"type": "noul",
                       "instructions": f"After this event, is the client's portfolio at risk of breaking this policy if nothing changes: {txt}?",
                       "criteria": {"true": "The event makes a breach likely or already present",
                                    "false": "This rule is unaffected or still comfortably met"}}
         for r, txt in RULE_TEXT.items() if r not in ("cited", "no_churn")}
    q["covered"] = {"type": "noul",
                    "instructions": "Does the agent playbook contain specific guidance for handling this kind of life event correctly?",
                    "criteria": {"true": "A skill or prompt line clearly addresses this event type",
                                 "false": "Nothing in the playbook addresses this situation"}}
    q["urgency"] = {"type": "score", "instructions": "How soon should this client's portfolio be reviewed?",
                    "criteria": ["Next scheduled review", "This month", "This week", "Today"]}
    res = decide(state, q)
    a = res["answers"]
    risks = {r[5:]: round(v["noul"], 3) for r, v in a.items() if r.startswith("risk_")}
    th = thresholds()
    at_risk = sorted([r for r, p in risks.items() if p >= th["event_risk"]], key=lambda r: -risks[r])
    covered = round(a["covered"]["noul"], 3)
    return {"gate": "event", "model": res["model"], "event": event.get("type"), "rule_risk": risks,
            "at_risk": at_risk, "covered": covered, "urgency": round(a["urgency"]["score"], 2),
            "rerun_now": bool(at_risk) and covered < th["uncovered"],
            "input_tokens": res["input_tokens"], "seconds": res["seconds"]}


# ---- gate 2: over a window of scored runs -------------------------------------------
def window_verdict(window: list[dict], baseline: float, trusted: set[str] | list[str],
                   rule_report: dict | None = None) -> dict:
    lines = [f"Baseline mean score of the shipped playbook on unseen clients: {baseline:.2f}.",
             f"Rules the shipped playbook passed 100% of the time in verification: {', '.join(sorted(trusted)) or 'none'}.",
             "--- RECENT RUNS (newest last) ---"]
    for i, c in enumerate(window, 1):
        v = "; ".join(f"{x['rule']} ({x['severity']}): {x['detail']}" for x in c.get("violations", [])) or "no violations"
        tags = c.get("tags") or ""
        lines.append(f"[R{i}] case {c.get('case_id')} {tags} score {c['score']:.2f} {'PASS' if c['passed'] else 'FAIL'} | {v}")
    rules = sorted(set(RULE_TEXT) | {"valid_output"})
    q = {
        "rollback": {"type": "noul",
                     "instructions": "Should the system roll back to the last known-good playbook now?",
                     "criteria": {"true": "Client-protection rules that used to pass are now failing in a pattern",
                                  "false": "Failures are isolated noise or only minor soft issues"}},
        "level": {"type": "choice", "instructions": "What is the drift level of the agent?",
                  "criteria": {"green": "No hard violations and scores near baseline",
                               "yellow": "Scores slipping or soft violations rising, no hard breaches of trusted rules",
                               "red": "Hard violations of rules the agent used to pass"}},
        "rule": {"type": "choice", "instructions": "Which policy rule is most at risk across these runs?",
                 "criteria": {**{r: RULE_TEXT.get(r, "output is missing or malformed") for r in rules},
                              "not_found": "No rule is clearly at risk"}},
        "novel": {"type": "noul", "instructions": "Are the failures caused by conditions that look new (event types or market moves) rather than the agent forgetting what it knew?",
                  "criteria": {"true": "Failures cluster on new kinds of situations", "false": "Failures are on familiar situations"}},
        "urgency": {"type": "score", "instructions": "How urgent is a fix?",
                    "criteria": ["Can wait", "This week", "Today", "Immediately"]},
    }
    res = decide("\n".join(lines), q)
    a = res["answers"]
    th = thresholds()
    rb = round(a["rollback"]["noul"], 3)
    out = {"gate": "window", "model": res["model"], "rollback_p": rb, "rollback": rb >= th["rollback"],
           "level": a["level"]["choice"], "level_p": {k: round(v, 3) for k, v in a["level"]["probabilities"].items()},
           "rule": a["rule"]["choice"], "rule_p": round(a["rule"]["probabilities"].get(a["rule"]["choice"], 0), 3),
           "novel_p": round(a["novel"]["noul"], 3), "urgency": round(a["urgency"]["score"], 2),
           "input_tokens": res["input_tokens"], "seconds": res["seconds"], "runs": len(window)}
    if rule_report is not None:
        out["rule_level"] = rule_report.get("level")
        out["agrees"] = (out["level"] == rule_report.get("level"))
    return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "checker"))
    import yaml
    from check import load_case
    case = load_case(Path(__file__).resolve().parents[1] / "scenarios" / "fixtures" / "c-014")
    pb = yaml.safe_load((Path(__file__).resolve().parents[1] / "agent" / "playbooks" / "v000.yaml").read_text(encoding="utf-8"))
    print(json.dumps(event_gate(case, case["events"][0], pb), indent=1))
