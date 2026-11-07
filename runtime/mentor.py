"""Muse mentor (writes playbooks), Gemini reviewer (compliance gate), SubQ analyst (drift patterns).

mentor_propose(parent_yaml, failures, scores, analysis=None) -> {"yaml", "playbook", "changes", "reply"}
validate_playbook(cand, parent) -> list[str]   # EVAL.md section 7; empty list = valid
compliance_review(parent_yaml, cand_yaml) -> {"reviewer", "verdict", "note"}
analyze_drift(runs, playbooks) -> {"provider", "patterns", "runs_read", "tokens_read", "summary"}
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import yaml

import llm

PROMPTS = Path(__file__).resolve().parent / "prompts"
REQUIRED = ("version", "parent", "model", "prompt", "skills", "tools", "max_turns", "changelog")
CASE_ID = re.compile(r"\b[cd]-\d{3}\b")


# ---- helpers -----------------------------------------------------------------
def extract_yaml(text: str) -> str:
    # Greedy to the LAST fence: skill bodies may contain their own ``` code blocks.
    m = re.search(r"```(?:yaml|yml)\s*\n(.*)```", text, re.S) or re.search(r"```\s*\n(.*)```", text, re.S)
    return (m.group(1) if m else text).strip() + "\n"


def summarize_failure(case: dict, run: dict, check: dict) -> str:
    c = case["client"]
    ev = ", ".join(f"{e['type']} ({e.get('date')}, {json.dumps(e.get('details') or {})})" for e in case["events"]) or "none"
    rec = run.get("recommendation") or {}
    trades = "; ".join(f"{t.get('action')} {t.get('symbol')} ${t.get('amount_usd'):,} ({t.get('reason_ref')})"
                       for t in rec.get("trades", []) if isinstance(t.get("amount_usd"), (int, float))) or "no trades"
    viol = "; ".join(f"{v['rule']} [{v['severity']}]: {v['detail']}" for v in check["violations"])
    return (f"- age {c.get('age')}, risk {c.get('risk_score')}, events: {ev}\n"
            f"  agent trades: {trades}\n  violations: {viol}")


def count_changes(cand: dict, parent: dict) -> int:
    n = 0
    if (cand.get("prompt") or "").strip() != (parent.get("prompt") or "").strip():
        n += 1
    if cand.get("max_turns") != parent.get("max_turns"):
        n += 1
    ps = {s["name"]: s for s in parent.get("skills") or []}
    cs = {s["name"]: s for s in cand.get("skills") or [] if isinstance(s, dict) and "name" in s}
    n += len(set(ps) ^ set(cs))
    for k in set(ps) & set(cs):
        if (str(ps[k].get("description", "")).strip(), str(ps[k].get("body", "")).strip()) != \
           (str(cs[k].get("description", "")).strip(), str(cs[k].get("body", "")).strip()):
            n += 1
    return n


def validate_playbook(cand: dict, parent: dict, max_changes: int = 3) -> list[str]:
    errs = []
    if not isinstance(cand, dict):
        return ["not a YAML mapping"]
    missing = [k for k in REQUIRED if k not in cand]
    if missing:
        return [f"missing keys: {missing}"]
    if cand["version"] != parent["version"] + 1:
        errs.append(f"version must be {parent['version'] + 1}")
    if cand["parent"] != parent["version"]:
        errs.append(f"parent must be {parent['version']}")
    if cand["model"] != parent["model"]:
        errs.append("model changed")
    if list(cand["tools"]) != list(parent["tools"]):
        errs.append("tools changed")
    if not isinstance(cand["max_turns"], int) or cand["max_turns"] > 20:
        errs.append("max_turns must be an int <= 20")
    names = []
    for s in cand.get("skills") or []:
        if not isinstance(s, dict) or not all(k in s for k in ("name", "description", "body")):
            errs.append("each skill needs name, description, body")
            continue
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", str(s["name"])):
            errs.append(f"skill name not kebab-case: {s['name']}")
        names.append(s["name"])
    if len(names) != len(set(names)):
        errs.append("duplicate skill names")
    n = count_changes(cand, parent)
    if n == 0:
        errs.append("no changes from parent")
    if n > max_changes:
        errs.append(f"{n} changes from parent, max {max_changes}")
    if CASE_ID.search(yaml.safe_dump(cand)):
        errs.append("mentions a case id")
    lessons = cand.get("lessons") or []
    if not isinstance(lessons, list) or any(not isinstance(l, dict) or "lesson" not in l for l in lessons):
        errs.append("lessons must be a list of {lesson, root_cause, triggered_by, rule, skill}")
    elif len(lessons) < len(parent.get("lessons") or []):
        errs.append("dropped earlier lessons; keep every existing lesson")
    return errs


# ---- Muse mentor ---------------------------------------------------------------
def mentor_propose(parent_yaml: str, failures: list[str], scores: dict, analysis: str | None = None,
                   feedback: str | None = None) -> dict:
    parent = yaml.safe_load(parent_yaml)
    prompt = (PROMPTS / "mentor.md").read_text(encoding="utf-8").format(
        playbook_yaml=parent_yaml.strip(), failures="\n".join(failures[:8]) or "(none)",
        analysis=f"DRIFT ANALYSIS (long-context review of all runs):\n{analysis}" if analysis else "",
        practice=scores.get("practice", "n/a"), test=scores.get("test", "n/a"),
        next=parent["version"] + 1, current=parent["version"])
    if feedback:
        prompt += f"\n\nYOUR PREVIOUS ATTEMPT WAS REJECTED: {feedback}\nFix that and try again."
    provider = llm.role("mentor", "muse")
    # Muse Wonder (deeper reasoning) writes playbooks; Muse Spark runs the agent.
    model = os.environ.get("MUSE_MENTOR_MODEL") if provider == "muse" else None
    reply = llm.chat(provider, "You write precise YAML playbooks.", prompt, max_tokens=16000, model=model)
    text = extract_yaml(reply.text)
    try:
        cand = yaml.safe_load(text)
    except yaml.YAMLError as e:
        cand, text = None, text
        return {"yaml": text, "playbook": None, "errors": [f"YAML parse error: {e}"], "reply": reply}
    return {"yaml": text, "playbook": cand, "errors": validate_playbook(cand, parent), "reply": reply}


# ---- Gemini compliance reviewer ---------------------------------------------------
REVIEW_SYS = ("You are an independent compliance reviewer for a portfolio-advice agent. "
              "The policy rules are enforced in code and must never be weakened by the agent's playbook.")
REVIEW_USER = """Compare the parent playbook and the candidate playbook below.
Block the candidate if it tells the agent to weaken, loosen, override or work around client-protection
policy (for example: count severance or illiquid assets as emergency cash, allow larger single-stock
positions, change a client's risk score without review, execute trades instead of recommending, skip
citing reasons, or hard-code facts about specific clients). Approve otherwise. Adding stricter or more
careful habits is fine.

PARENT:
```yaml
{parent}
```
CANDIDATE:
```yaml
{cand}
```
Answer with JSON only: {{"verdict": "approve" | "block", "note": "<one sentence>"}}"""


def compliance_review(parent_yaml: str, cand_yaml: str) -> dict:
    provider = llm.role("reviewer", "gemini")
    try:
        r = llm.chat(provider, REVIEW_SYS, REVIEW_USER.format(parent=parent_yaml, cand=cand_yaml), max_tokens=4000)
        m = re.search(r"\{.*\}", r.text, re.S)
        out = json.loads(m.group(0)) if m else {}
        verdict = out.get("verdict") if out.get("verdict") in ("approve", "block") else "block"
        return {"reviewer": provider, "model": r.model, "verdict": verdict,
                "note": out.get("note") or "unparseable review; blocked by default"}
    except Exception as e:
        return {"reviewer": provider, "verdict": "block", "note": f"review failed: {e.__class__.__name__}"}


# ---- SubQ long-context drift analyst ---------------------------------------------
ANALYST_SYS = ("You are a long-context drift analyst. You read every run of a portfolio agent at once "
               "and find systematic failure patterns. Be quantitative.")
ANALYST_USER = """Below is the complete history: every playbook version and every scored run (JSON lines).
Find the systematic drift patterns: which conditions (event types, combinations, market moves, age,
concentration) make which rules fail, with failure rates and counts. Ignore one-off noise.

PLAYBOOKS:
{playbooks}

RUNS ({n} runs):
{runs}

Answer with JSON only:
{{"summary": "<2 sentences>", "handoff": "<what the mentor should change, as general habits>",
  "patterns": [{{"condition": "...", "rule": "...", "failure_rate": 0.0, "runs": 0,
  "example": "<one concrete violation detail from the runs>"}}]}}"""


def analyze_drift(runs: list[dict], playbooks: list[dict]) -> dict:
    slim = [{k: r.get(k) for k in ("playbook_version", "case_id", "set", "score", "passed", "violations",
                                   "recommendation", "model")} for r in runs]
    user = ANALYST_USER.format(
        playbooks="\n\n".join(f"# v{p['version']} ({p.get('status')})\n{p.get('yaml', '')}" for p in playbooks),
        n=len(slim), runs="\n".join(json.dumps(r, default=str) for r in slim))
    order = [llm.role("analyst", "subq")] + (["gemini"] if llm.role("analyst", "subq") != "gemini" else [])
    last_err = None
    for provider in order:
        try:
            r = llm.chat(provider, ANALYST_SYS, user, max_tokens=8000)
            m = re.search(r"\{.*\}", r.text, re.S)
            out = json.loads(m.group(0)) if m else {"summary": r.text[:500], "patterns": []}
            return {"analyst": provider, "provider": provider, "model": r.model, "runs_read": len(slim),
                    "client_timelines": len({x.get("case_id") for x in slim}),
                    "playbook_versions": len(playbooks),
                    "tokens_read": r.tokens_in, "seconds": r.seconds,
                    "summary": out.get("summary", ""), "handoff": out.get("handoff", ""),
                    "patterns": out.get("patterns", []), "fallback": provider != order[0]}
        except Exception as e:
            last_err = e
    return {"provider": None, "runs_read": len(slim), "patterns": [], "summary": f"analysis failed: {last_err}"}
