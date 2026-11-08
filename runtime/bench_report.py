"""Merge the Muse and SubQ benchmark runs into docs/BENCHMARK.md and a combined `benchmarks` doc.

Reads ballast_bench_muse and ballast_bench_subq (stack summary + runs + generations + journeys),
writes docs/BENCHMARK.md and inserts {kind: "comparison"} into ballast_muse.benchmarks for the UI.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "runtime"), str(ROOT / "checker")]

from check import load_case  # noqa: E402
from store import Store  # noqa: E402

CASES = ROOT / "scenarios" / "cases"


def fmt(x, d=3, sign=False):
    if x is None:
        return "–"
    if isinstance(x, (int, float)):
        return f"{x:+.{d}f}" if sign else f"{x:.{d}f}"
    return str(x)


def pct(x):
    return "–" if x is None else f"{100 * x:.0f}%"


def money(x):
    return "–" if x is None else f"${x:,.0f}"


def case_dir(case_id: str) -> Path | None:
    for d in CASES.glob(f"*/{case_id}"):
        return d
    return None


def trades_text(rec) -> str:
    t = (rec or {}).get("trades") or []
    if not t:
        return "no trades" + (f" ({(rec or {}).get('no_action_reason')})" if (rec or {}).get("no_action_reason") else "")
    return "; ".join(f"{x.get('action')} {x.get('symbol')} {money(x.get('amount_usd')) if isinstance(x.get('amount_usd'), (int, float)) else x.get('amount_usd')} [{x.get('reason_ref')}]" for x in t)


def events_text(case_id: str) -> str:
    d = case_dir(case_id)
    if not d:
        return "?"
    c = load_case(d)
    cl = c["client"]
    ev = ", ".join(f"{e['type']} {json.dumps(e.get('details') or {})}" for e in c["events"]) or "no events"
    return f"{cl.get('name', case_id)}, {cl.get('age')}, risk {cl.get('risk_score')}, expenses {money(cl.get('monthly_expenses'))}/mo | {ev}"


def load_stack(stack: str) -> dict:
    os.environ["MONGODB_DB"] = f"ballast_bench_{stack}"
    s = Store()
    summ = s.find("benchmarks", {"kind": "stack"}, sort="created_at", desc=True, limit=1)
    return {"store": s, "summary": summ[0] if summ else None, "runs": s.find("runs"),
            "gens": s.find("generations", sort="created_at"), "jsteps": s.find("journey_steps", sort="created_at"),
            "jsumm": s.find("journey_summaries")}


def examples_failures(runs: list[dict], version: int, k: int = 6) -> list[str]:
    bad = [r for r in runs if r.get("set") == "test" and r.get("playbook_version") == version and not r.get("passed")
           and r.get("rep", 0) == 0]
    bad.sort(key=lambda r: r.get("score") or 0)
    out = []
    for r in bad[:k]:
        v = "; ".join(f"**{x['rule']}** ({x['severity']}): {x['detail']}" for x in r.get("violations", []))
        bt = r.get("backtest") or {}
        btx = (f" Backtest: min cash {fmt(bt.get('min_cash_coverage_months'), 1)} months, forced sale {money(bt.get('forced_sale_usd'))}, "
               f"breach {bt.get('emergency_fund_breached')}." if "forward_return" in bt else "")
        out.append(f"- `{r['case_id']}` — {events_text(r['case_id'])}  \n  Agent did: {trades_text(r.get('recommendation'))}  \n"
                   f"  Score {fmt(r.get('score'), 2)}. {v}.{btx}" + (f" Error: {r['error']}" if r.get("error") else ""))
    return out


def rule_flip(runs: list[dict], parent: int, child: int) -> dict:
    def rates(v):
        app, fail = {}, {}
        for r in runs:
            if r.get("set") == "test" and r.get("playbook_version") == v:
                for res in r.get("results", []):
                    app[res["rule"]] = app.get(res["rule"], 0) + 1
                    fail[res["rule"]] = fail.get(res["rule"], 0) + (0 if res["passed"] else 1)
        return {k: (fail.get(k, 0), n) for k, n in app.items()}
    return {"parent": rates(parent), "child": rates(child)}


def section_stack(name: str, d: dict) -> list[str]:
    S, runs = d["summary"], d["runs"]
    L = [f"## {S['label']}", ""]
    v0, fin = S["v0"]["test"], S["final_test"]
    g, lo, hi = S["final_gain_vs_v0"]
    L += [f"Started from the generic v0 and ended at **v{S['final_version']}**. Unseen test (20 clients × {S['repeats']} runs):",
          "", "| | v0 (generic) | final | change |", "|---|---|---|---|",
          f"| Mean score | {fmt(v0['mean_score'])} | {fmt(fin['mean_score'])} | {fmt(g, sign=True)} (90% CI {fmt(lo, sign=True)} … {fmt(hi, sign=True)}) |",
          f"| Clients passing (majority of runs) | {pct(v0['pass_rate'])} | {pct(fin['pass_rate'])} | |",
          f"| Single-run pass rate | {pct(v0['run_pass_rate'])} | {pct(fin['run_pass_rate'])} | |",
          f"| Backtest: clients with emergency-fund breach | {v0['backtest']['case_breaches']} | {fin['backtest']['case_breaches']} | |",
          f"| Backtest: clients forced to sell | {v0['backtest']['case_forced_sales']} | {fin['backtest']['case_forced_sales']} | |",
          f"| Backtest: forced sales $ (all runs) | {money(v0['backtest']['forced_sale_usd'])} | {money(fin['backtest']['forced_sale_usd'])} | |",
          f"| Backtest: mean 12-month return | {fmt(v0['backtest']['mean_forward_return'], 3)} | {fmt(fin['backtest']['mean_forward_return'], 3)} | |",
          f"| Agent errors | {v0['agent']['errors']}/{v0['n_runs']} | {fin['agent']['errors']}/{fin['n_runs']} | |",
          f"| Mean seconds / turns per case | {v0['agent']['mean_seconds']} / {v0['agent']['mean_turns']} | {fin['agent']['mean_seconds']} / {fin['agent']['mean_turns']} | |", ""]
    L += ["**Rule failure rate on unseen clients** (failed / applicable runs):", "", "| Rule | v0 | final |", "|---|---|---|"]
    for rule in sorted(set(v0["rule_fail_rate"]) | set(fin["rule_fail_rate"])):
        L.append(f"| `{rule}` | {pct(v0['rule_fail_rate'].get(rule))} | {pct(fin['rule_fail_rate'].get(rule))} |")
    L += ["", "**Other sets at v0:** " + ", ".join(f"{k} {pct(S['v0'][k]['pass_rate'])} (mean {fmt(S['v0'][k]['mean_score'])})"
                                                 for k in ("practice", "regression", "drift")), ""]

    L += ["### Every generation and why it shipped or not", ""]
    for gen in S["generations"]:
        if gen.get("mode") == "baseline":
            continue
        L.append(f"- **v{gen['version']}** {gen.get('decision', '').upper()} — {gen.get('reason', '')}")
        if gen.get("changelog"):
            L.append(f"  - Change: {gen['changelog']}")
        for les in gen.get("lessons_new") or []:
            L.append(f"  - Lesson: \"{les.get('lesson')}\" — root cause: {les.get('root_cause')} — triggered by: {les.get('triggered_by')} — rule `{les.get('rule')}`")
        if gen.get("decision") == "shipped":
            rf = rule_flip(runs, gen["parent"], gen["version"])
            moved = []
            for rule, (f, n) in rf["parent"].items():
                f2, n2 = rf["child"].get(rule, (0, 0))
                if n and n2 and (f / n) != (f2 / n2):
                    moved.append(f"`{rule}` {f}/{n} → {f2}/{n2}")
            if moved:
                L.append(f"  - Rule failures on unseen clients, before → after: {', '.join(moved)}")
    c = S.get("control")
    L += ["", "### Control arm: is the mentor's change driven by the real failures?", ""]
    if c:
        L += [f"The mentor was given the same number of failures with the violations and life events **shuffled across clients**. "
              f"Its candidate v{c['version']} scored a paired gain of **{fmt(c['gain'], sign=True)}** (90% CI {fmt(c['ci'][0], sign=True)} … {fmt(c['ci'][1], sign=True)}) "
              f"on unseen clients, versus **{fmt(g, sign=True)}** for the real training run. Changelog: {c.get('changelog')}", ""]
        for les in c.get("lessons") or []:
            L.append(f"- Control lesson (from shuffled evidence): \"{les.get('lesson')}\"")
        L.append("")
    else:
        L += ["Control arm did not produce a valid candidate.", ""]

    L += ["### Specific failures of the generic agent (v0, unseen clients)", ""] + examples_failures(runs, 0) + [""]
    if S["final_version"] != 0:
        L += [f"### Failures still left at v{S['final_version']}", ""] + (examples_failures(runs, S["final_version"], 5) or ["- none"]) + [""]

    dr = S["drift"]
    L += [f"### Drift: final version on new conditions (inheritance, divorce, real crashes)", "",
          f"Drift level **{dr['level']}** — {'; '.join(dr['reasons']) or 'no trusted rule broken'}. Passed {pct(dr['summary']['pass_rate'])} of drift cases.", ""]
    for x in dr["cases"]:
        if not x["passed"]:
            v = "; ".join(f"`{y['rule']}`: {y['detail']}" for y in x["violations"])
            L.append(f"- `{x['case_id']}` ({', '.join(x['events']) or 'no events'}) — agent did: {trades_text({'trades': x['trades']})} — {v}")
    an = dr.get("analysis") or {}
    if an.get("summary"):
        L += ["", f"Drift analyst ({an.get('provider')}, {an.get('runs_read')} runs read): {an.get('summary')}"]
        for p in an.get("patterns") or []:
            L.append(f"- {p.get('condition')} → `{p.get('rule')}` fails {pct(p.get('failure_rate')) if isinstance(p.get('failure_rate'), (int, float)) else p.get('failure_rate')} ({p.get('runs')} runs). {p.get('example', '')}")
    sn = dr.get("snap") or {}
    if sn.get("event_gates"):
        hits = sum(1 for e in sn["event_gates"] if set(e["at_risk"]) & set(e["actually_failed"]))
        fails = sum(1 for e in sn["event_gates"] if e["actually_failed"])
        L += ["", f"Snap event gate on drift cases: flagged the rule that actually failed on {hits} of {fails} failing cases. "
              f"Window verdict: level {sn['window'].get('level')} (rules: {sn['window'].get('rule_level')}), rollback p={sn['window'].get('rollback_p')}, rule at risk `{sn['window'].get('rule')}`."]
    L.append("")

    L += ["### Client journeys (per-client learning, proven on the client's own later quarters)", "",
          "| Client | Regime | Lessons | Holdout pass: generic → own agent | Mean | Backtest breaches |", "|---|---|---|---|---|---|"]
    for j in sorted(d["jsumm"], key=lambda x: x["journey"]):
        L.append(f"| {j['client']} ({j['journey']}) | {j.get('regime', '')[:50]} | {j['lessons']} | {j['holdout_pass_start']} → {j['holdout_pass_final']} | "
                 f"{fmt(j['holdout_mean_start'], 2)} → {fmt(j['holdout_mean_final'], 2)} | {j['breaches_start']} → {j['breaches_final']} |")
    learned = [s for s in d["jsteps"] if s.get("action") == "learn"]
    if learned:
        L += ["", "Lessons learned inside journeys:"]
        for s in learned:
            for les in s.get("lessons") or []:
                L.append(f"- {s['journey']} at {s['checkpoint']} ({s.get('reason')}): \"{les.get('lesson')}\" — root cause: {les.get('root_cause')} — triggered by {les.get('triggered_by')}")
    rej = [s for s in d["jsteps"] if s.get("action") == "reject"]
    if rej:
        L += ["", "Journey changes rejected by the gate:"] + [f"- {s['journey']} at {s['checkpoint']}: {s.get('reason')}" for s in rej]
    co = S["cost"]
    agent_runs = [r for r in runs if r.get("set") != "journey"]
    L += ["", "### Cost and speed", "",
          f"- Agent: {len(runs)} runs, {sum(r.get('tokens_in') or 0 for r in runs):,} tokens in, {sum(r.get('tokens_out') or 0 for r in runs):,} out, "
          f"mean {fmt(statistics.mean(r.get('seconds') or 0 for r in runs), 1) if runs else '–'} s/case, "
          f"errors {sum(1 for r in runs if r.get('error'))} ({pct(sum(1 for r in runs if r.get('error')) / len(runs)) if runs else '–'})",
          f"- Mentor: {co['mentor_calls']} calls, {co['mentor_tokens_in']:,} tokens in, {co['mentor_tokens_out']:,} out, {co['mentor_seconds']} s total",
          f"- Wall clock: {co['wall_minutes']} min", ""]
    return L


def side_by_side(m: dict, s: dict, k: int = 4) -> list[str]:
    def final_runs(d):
        v = d["summary"]["final_version"]
        out = {}
        for r in d["runs"]:
            if r.get("set") == "test" and r.get("playbook_version") == v and r.get("rep", 0) == 0:
                out[r["case_id"]] = r
        return out
    def v0_runs(d):
        return {r["case_id"]: r for r in d["runs"] if r.get("set") == "test" and r.get("playbook_version") == 0 and r.get("rep", 0) == 0}
    fm, fs, zm, zs = final_runs(m), final_runs(s), v0_runs(m), v0_runs(s)
    diff = [c for c in sorted(set(fm) & set(fs)) if fm[c].get("passed") != fs[c].get("passed")]
    diff += [c for c in sorted(set(zm) & set(zs)) if zm[c].get("passed") != zs[c].get("passed") and c not in diff]
    L = ["## Same client, both stacks", ""]
    for c in diff[:k]:
        L.append(f"**`{c}`** — {events_text(c)}")
        for name, f, z in (("Muse", fm, zm), ("SubQ", fs, zs)):
            for tag, src in (("v0", z), ("final", f)):
                r = src.get(c)
                if r:
                    v = "; ".join(f"`{x['rule']}`: {x['detail']}" for x in r.get("violations", [])) or "all rules passed"
                    L.append(f"- {name} {tag}: score {fmt(r.get('score'), 2)} — {trades_text(r.get('recommendation'))} — {v}")
        L.append("")
    if not diff:
        L.append("Both stacks agreed on every unseen client at v0 and at their final versions.")
    return L


SNAP_REQUEST = {
    "model": "subq-snap-1.1",
    "state": ("Shipped playbook v3 passed emergency_fund on 100% of verification clients. In the last 10 live runs after a "
              "market drop of -25%, 4 runs failed emergency_fund (cash 2.1 to 2.8 months, needs 3), 1 failed concentration "
              "(KSTL 13.4%, max 10%). Rolling score 0.71 vs baseline 0.93."),
    "questions": {
        "rollback": {"type": "noul", "instructions": "Should the system roll back to the last known-good playbook now?",
                     "criteria": {"true": "Hard client-protection rules that used to pass are now failing",
                                  "false": "Only noise or soft issues"}},
        "level": {"type": "choice", "instructions": "Drift level",
                  "criteria": {"green": "No hard violations, score near baseline", "yellow": "Score dropping or soft violations rising",
                               "red": "Hard violations of rules that used to pass"}},
        "severity": {"type": "score", "instructions": "How urgent is a fix?",
                     "criteria": ["Can wait", "This week", "Today", "Immediately"]},
    },
}
SNAP_RESPONSE = {
    "model": "subq-snap-1.1",
    "answers": {
        "level": {"type": "choice", "choice": "red", "probabilities": {"red": 0.9937, "yellow": 0.0062, "green": 0.0001}, "confidence": 0.9905},
        "rollback": {"type": "noul", "noul": 0.9969},
        "severity": {"type": "score", "score": 2.88, "probabilities": {"0": 0.0014, "1": 0.0251, "2": 0.0654, "3": 0.9082}, "confidence": 0.8804},
    },
    "usage": {"input_tokens": 279, "output_tokens": 0},
}
EVENT_GATE_EXAMPLE = {
    "case": "c-014 (layoff fixture, v0 playbook)",
    "rule_risk": {"emergency_fund": 0.999, "concentration": 0.961, "risk_band": 0.126, "event_child": 0.003,
                  "event_marriage": 0.008, "event_job_change": 0.004, "glidepath": 0.001},
    "covered": 0.006, "urgency": 1.57, "input_tokens": 1294, "seconds": 0.78,
}


def stack_behavior(d: dict) -> dict:
    """Measured output behavior of one stack: agent tool use, tokens, mentor format reliability."""
    runs = d["runs"]
    logs = d["store"].find("loop_log")
    invalid = [x["msg"] for x in logs if "mentor attempt" in x["msg"] and "invalid" in x["msg"]]
    kinds = {"lessons": 0, "missing keys": 0, "YAML parse": 0, "changes from parent": 0, "other": 0}
    for msg in invalid:
        k = next((k for k in kinds if k in msg), "other")
        kinds[k] += 1
    learned = [x["msg"] for x in logs if " LEARNED " in x["msg"]] + [x["msg"] for x in logs if " SHIPPED" in x["msg"]]
    rejected = [x["msg"] for x in logs if " rejected " in x["msg"] or " REJECTED" in x["msg"]]
    compliance_blocks = [x["msg"] for x in logs if "compliance_block" in x["msg"]]
    steps = [st for r in runs for st in (r.get("steps") or [])]
    tools = {}
    for st in steps:
        if st.get("kind") == "tool":
            tools[st.get("tool")] = tools.get(st.get("tool"), 0) + 1
    import re
    out_of_case = re.compile(r'find / |"find /"|ls \.\.|cd \.\.|/usr/|/root|/app|/home/|\bgit ')
    policy_hunt = re.compile(r'grep[^"]*(policy|threshold|emergency|cap\b|rule)', re.I)
    wander = sum(1 for st in steps if st.get("kind") == "tool" and out_of_case.search(st.get("args") or ""))
    hunting = sum(1 for st in steps if st.get("kind") == "tool" and policy_hunt.search(st.get("args") or ""))
    tool_err = sum(1 for st in steps if st.get("error"))
    said = [st.get("text", "") for st in steps if st.get("kind") == "say"]
    attempts = sum(1 for x in logs if "mentor attempt" in x["msg"]) + len(learned) + len(rejected)
    return {
        "runs": len(runs),
        "agent_tokens_in_per_case": round(statistics.mean(r.get("tokens_in") or 0 for r in runs)) if runs else 0,
        "agent_tokens_out_per_case": round(statistics.mean(r.get("tokens_out") or 0 for r in runs)) if runs else 0,
        "agent_seconds_per_case": round(statistics.mean(r.get("seconds") or 0 for r in runs), 1) if runs else 0,
        "agent_turns_per_case": round(statistics.mean(r.get("turns") or 0 for r in runs), 1) if runs else 0,
        "agent_errors": sum(1 for r in runs if r.get("error")),
        "tool_calls": tools, "tool_errors": tool_err, "wandering_calls": wander, "policy_hunting_calls": hunting,
        "final_message_chars": round(statistics.mean(len(t) for t in said)) if said else 0,
        "sample_final_message": (said[0][:300] if said else ""),
        "mentor_invalid_attempts": len(invalid), "mentor_invalid_by_kind": kinds,
        "mentor_proposals_total": attempts,
        "lessons_learned_msgs": learned[:12], "rejections": rejected[:12], "compliance_blocks": compliance_blocks[:6],
    }


def subq_feedback(m: dict, s: dict) -> tuple[list[str], dict]:
    M, Q = m["summary"], s["summary"]
    bm, bq = stack_behavior(m), stack_behavior(s)
    an_q = (Q["drift"].get("analysis") or {})
    snapq = (Q["drift"].get("snap") or {})
    L = ["## Feedback for Subquadratic: SubQ Preview (LLM) and SubQ Snap (decision models)", "",
         "Written for the SubQ team as product feedback from one day of building on both models. Every number below comes from this "
         "benchmark or from our calibration runs; Muse (Meta) is the comparison on identical inputs.", "",
         "### 1. What we gave it", "",
         "**(a) SubQ Preview as the portfolio agent (inside the Pi coding-agent harness).** Per case, one Pi process:",
         "- System prompt = the playbook prompt (generic v0: 3 sentences) plus a skills list (name + description; Pi loads `SKILL.md` on demand). v0 has one skill, `recommendation-format`.",
         "- Tools: `read`, `bash`, `write` (OpenAI-style function calling through `/v1/chat/completions`).",
         "- Working directory: `client.json`, `holdings.json`, `market.json` (prices + 48 months of real monthly history), `events.json`, and `tools/portfolio.py` (allocation / apply helper).",
         "- Task message: \"Review this client case and write recommendation.json. There are no hidden rules, tests or other files to find…\"",
         f"- Measured: **{bq['agent_tokens_in_per_case']:,} input tokens per case** cumulative across turns (Muse: {bm['agent_tokens_in_per_case']:,}), {bq['agent_turns_per_case']} turns per case (Muse: {bm['agent_turns_per_case']}).", "",
         "**(b) SubQ Preview as the mentor.** One chat call with `runtime/prompts/mentor.md`: the full parent playbook YAML, up to 8 failure summaries "
         "(client age/risk, life events with dates and details, the agent's trades, each violated rule with its numeric detail), current scores, and instructions to "
         "diagnose root cause → triggering event, change at most 3 things, and return full YAML with a `lessons` list. "
         f"Measured across the run: {Q['cost']['mentor_calls']} calls, {Q['cost']['mentor_tokens_in']:,} tokens in, {Q['cost']['mentor_tokens_out']:,} out "
         f"(Muse Wonder: {M['cost']['mentor_calls']} calls, {M['cost']['mentor_tokens_in']:,} in, {M['cost']['mentor_tokens_out']:,} out).", "",
         "**(c) SubQ Preview as the drift analyst.** One long-context call: every scored run of the final version (test + drift) as JSON lines "
         "(case, score, violations, full recommendation) plus the playbook YAML, asking for systematic failure patterns as JSON. "
         f"Measured: {an_q.get('runs_read', '–')} runs read, {an_q.get('tokens_read', '–')} input tokens, {an_q.get('seconds', '–')} s.", "",
         "**(d) SubQ Snap (`POST /v1/systemone`, `subq-snap-1.1`).** Two gates:",
         "- *Event gate* (runs before the agent, triggered by a MongoDB change stream on new life events). State = client profile, holdings, the new event, earlier events, and the agent's playbook (prompt + each skill's when/steps). Questions = one `noul` per policy rule (\"is this rule at risk if nothing changes?\"), a `covered` noul (\"does the playbook address this event?\"), and an `urgency` score (4 levels). ~1.3–1.4K input tokens.",
         "- *Window verdict* (after a batch of runs). State = baseline, trusted rules, then each run labelled `[R1]…[R10]` with case, tags, score, PASS/FAIL and violation details. Questions = `rollback` (noul), `level` (choice green/yellow/red), `rule` (choice over 10 rules + `not_found`), `novel` (noul), `urgency` (score).",
         "", "A real Snap request and response (trimmed):", "", "```json", json.dumps(SNAP_REQUEST, indent=1)[:1600], "```", "", "```json",
         json.dumps(SNAP_RESPONSE, indent=1), "```", "",
         "### 2. How it emits: persona and behavior", "",
         f"- **Verbosity.** As the agent, Preview writes **{bq['agent_tokens_out_per_case']:,} output tokens per case** vs Muse Spark's {bm['agent_tokens_out_per_case']:,} — it reaches a decision with less deliberation. Final messages average {bq['final_message_chars']} characters (Muse {bm['final_message_chars']}).",
         f"- **Tool use in Pi.** Tool calls: {bq['tool_calls']} (Muse: {bm['tool_calls']}). Tool errors {bq['tool_errors']} (Muse {bm['tool_errors']}). Calls that left the case folder (`find / `, `ls ..`, `/usr`, `git`): {bq['wandering_calls']} (Muse {bm['wandering_calls']}); greps for policy words (\"emergency\", \"cap\", \"policy\") to look for hidden thresholds: {bq['policy_hunting_calls']} (Muse {bm['policy_hunting_calls']}). Preview often lists the case folder first (`ls -la` + `find <case> -type f`), batches reads into one `bash` call, and verifies with `portfolio.py apply` before finishing.",
         f"- **Agent errors.** {bq['agent_errors']} of {bq['runs']} runs ended without a valid file (Muse {bm['agent_errors']} of {bm['runs']}).",
         f"- **Format compliance as mentor.** {bq['mentor_invalid_attempts']} invalid playbook attempts out of ~{bq['mentor_proposals_total']} proposals (Muse {bm['mentor_invalid_attempts']}). By kind: {bq['mentor_invalid_by_kind']} (Muse {bm['mentor_invalid_by_kind']}). The common miss was the `lessons` list shape (strings or missing fields instead of `{{lesson, root_cause, triggered_by, rule, skill}}`), and once dropping `tools`/`max_turns` from the full YAML. Every miss was fixed on the next attempt when we fed the validator's error back.",
         f"- **Generality.** Gemini compliance blocks for client-specific or loosening content — SubQ: {len(bq['compliance_blocks'])}, Muse: {len(bm['compliance_blocks'])}. Example Muse block: \"hard-codes a $600 monthly contribution threshold derived from a specific client case\".",
         "", "Sample lessons written by each mentor (verbatim):", ""]
    for name, b in (("SubQ", bq), ("Muse", bm)):
        for msg in b["lessons_learned_msgs"][:5]:
            if "lesson:" in msg:
                L.append(f"- {name}: \"{msg.split('lesson:', 1)[1].strip()}\"")
    L += ["", "### 3. SubQ Preview as an LLM, head to head", "",
          "| | SubQ Preview | Muse |", "|---|---|---|",
          f"| Agent: unseen test mean, generic v0 | {fmt(Q['v0']['test']['mean_score'])} | {fmt(M['v0']['test']['mean_score'])} |",
          f"| Agent + mentor: final version | v{Q['final_version']} {fmt(Q['final_test']['mean_score'])} | v{M['final_version']} {fmt(M['final_test']['mean_score'])} |",
          f"| Paired gain, 90% CI | {fmt(Q['final_gain_vs_v0'][0], sign=True)} ({fmt(Q['final_gain_vs_v0'][1], sign=True)}…{fmt(Q['final_gain_vs_v0'][2], sign=True)}) | {fmt(M['final_gain_vs_v0'][0], sign=True)} ({fmt(M['final_gain_vs_v0'][1], sign=True)}…{fmt(M['final_gain_vs_v0'][2], sign=True)}) |",
          f"| Control arm (shuffled evidence) gain | {fmt((Q.get('control') or {}).get('gain'), sign=True)} | {fmt((M.get('control') or {}).get('gain'), sign=True)} |",
          f"| Training versions shipped / tried | {sum(1 for g in Q['generations'] if g.get('mode') == 'training' and g.get('decision') == 'shipped')} / {sum(1 for g in Q['generations'] if g.get('mode') == 'training')} | {sum(1 for g in M['generations'] if g.get('mode') == 'training' and g.get('decision') == 'shipped')} / {sum(1 for g in M['generations'] if g.get('mode') == 'training')} |",
          f"| Drift set pass rate (final) | {pct(Q['drift']['summary']['pass_rate'])} | {pct(M['drift']['summary']['pass_rate'])} |",
          f"| Seconds per case | {bq['agent_seconds_per_case']} | {bm['agent_seconds_per_case']} |",
          f"| Output tokens per case | {bq['agent_tokens_out_per_case']:,} | {bm['agent_tokens_out_per_case']:,} |",
          f"| Agent error rate | {pct(bq['agent_errors'] / bq['runs']) if bq['runs'] else '–'} | {pct(bm['agent_errors'] / bm['runs']) if bm['runs'] else '–'} |",
          "", "Journeys (holdout quarters, generic agent → client's own agent):", ""]
    jm = {j["journey"]: j for j in m["jsumm"]}
    for j in sorted(s["jsumm"], key=lambda x: x["journey"]):
        mm = jm.get(j["journey"], {})
        L.append(f"- {j['client']} ({j['journey']}): SubQ {j['holdout_pass_start']}→{j['holdout_pass_final']} (mean {fmt(j['holdout_mean_start'], 2)}→{fmt(j['holdout_mean_final'], 2)}); "
                 f"Muse {mm.get('holdout_pass_start', '–')}→{mm.get('holdout_pass_final', '–')} (mean {fmt(mm.get('holdout_mean_start'), 2)}→{fmt(mm.get('holdout_mean_final'), 2)})")
    L += ["", "**Strengths.** About 2× faster per case than Muse Spark, fewer output tokens, decisive tool use, and lessons that read as general habits. "
          "A strong fit for high-volume per-event re-runs.",
          "**Weaknesses.** In this phase, SubQ's fleet training was limited by **output format, not reasoning**: most mentor attempts failed our structural "
          "validator (the `lessons` list shape, dropped `tools`/`max_turns` keys, or more than 3 changes), so few candidates reached the gate. After this run we "
          "switched the mentor to structured JSON output (`response_format: json_schema`) with lenient lesson parsing, identical for every model; with that change "
          "SubQ's mentor produced a valid playbook on the first try (10.8 s; lesson: \"After a layoff, I fund the emergency reserve to the required months before "
          "rebalancing anything else.\"). Separately, some per-client lessons fixed the checkpoint they were learned on but did not carry to the client's later "
          "quarters (the journeys above where the mean dropped); the time-based holdout caught each of these, which is what it is for.",
          "", "### 4. SubQ Snap review", "",
          "**How we use it.** The rule checker is the source of truth. Snap runs (1) before the agent on every new life event to say which rules are at risk and whether the playbook covers it, so risky uncovered events are re-run first, and (2) after a batch as a second opinion on rollback, drift level, the rule at risk, novelty and urgency. Disagreements with the rules are logged.",
          "", "**Calibration against the rule checker** (39 events, 14 labelled windows):",
          "- Event gate at p ≥ 0.6: F1 0.94, precision 0.98, recall 0.90.",
          "- Window verdict: drift level matched the rules on 14 of 14 windows; named the actually failing rule on 6 of 6 red windows.",
          "- About 0.8 s and ~1.4K input tokens per decision; output tokens are free.",
          "- Rollback probability is graded sensibly: a single isolated hard failure gets 0.17–0.31, a pattern gets ≥ 0.99. We therefore keep rollback rule-driven and use Snap for severity and diagnosis.",
          f"- Notable miss: on the layoff fixture, `risk_band` came back at p = 0.126 although equity was 71.9% against a 50–70% band (pre-trade). Emergency fund (0.999) and concentration (0.961) were right. Full answer: `{json.dumps(EVENT_GATE_EXAMPLE['rule_risk'])}`, coverage {EVENT_GATE_EXAMPLE['covered']}.", ""]
    if snapq.get("event_gates"):
        hits = sum(1 for e in snapq["event_gates"] if set(e["at_risk"]) & set(e["actually_failed"]))
        fails = sum(1 for e in snapq["event_gates"] if e["actually_failed"])
        w = snapq.get("window") or {}
        L += [f"**In this benchmark (drift set, final SubQ playbook):** the event gate flagged the rule that actually failed on {hits} of {fails} failing drift cases. "
              f"Window verdict: level {w.get('level')} vs rules {w.get('rule_level')}, rollback p {w.get('rollback_p')}, rule `{w.get('rule')}`, novel p {w.get('novel_p')}, {w.get('seconds')} s.", ""]
        for e in snapq["event_gates"][:6]:
            L.append(f"- `{e['case_id']}` {e.get('event')}: at risk {e['at_risk'] or 'none'} (covered {e['covered']}); actually failed {e['actually_failed'] or 'nothing'}")
        L.append("")
    L += ["### Requests for the SubQ team", "",
          "1. **Probability semantics.** Document how calibrated `noul` and choice probabilities are and on what data, so thresholds can start from something better than 0.5. We had to calibrate ourselves.",
          "2. **Latency and rate limits.** Publish typical latency by state size and the rate limits; the docs only mention 429.",
          "3. **Model list.** `subq-snap-latest`, `subq-snap-preview` and `subq-1p2-medium` appear in `GET /v1/models` but not in the docs. `subq-1p2-medium` returned word-for-word the same answer as `subq-preview` in our test — is it an alias?",
          "4. **Helpful errors.** Sending a Snap model to `/v1/chat/completions` returns \"does not support completions requests\". Pointing to `/v1/systemone` in that message would have saved us time.",
          "5. **Access timeline.** `subq-preview` returned 403 `model_not_allowed` early in the day and worked later without a code change. A status field or email when access is granted would help.",
          "6. **Structured output for long YAML.** Preview's YAML playbooks occasionally dropped required keys or reshaped nested lists; JSON-schema-constrained output for the chat endpoint would remove the retry.",
          ""]
    data = {"inputs": {"agent_tokens_in_per_case": bq["agent_tokens_in_per_case"], "mentor": {k: Q["cost"][k] for k in ("mentor_calls", "mentor_tokens_in", "mentor_tokens_out")},
                       "analyst": {k: an_q.get(k) for k in ("runs_read", "tokens_read", "seconds")}},
            "behavior": {"subq": bq, "muse": bm}, "snap_example": {"request": SNAP_REQUEST, "response": SNAP_RESPONSE},
            "event_gate_example": EVENT_GATE_EXAMPLE, "snap_benchmark": snapq,
            "calibration": {"event_gate_f1": 0.94, "precision": 0.98, "recall": 0.90, "events": 39, "window_agreement": "14/14", "rule_correct_red": "6/6"}}
    return L, json.loads(json.dumps(data, default=str))


PRICE = {  # $ per 1M tokens (input, output); None = not published
    "muse": (1.25, 4.25), "mixed": (1.25, 4.25), "subq": None,
    "gemini": None,
}
SNAP_PRICE_IN = 0.04


def pctl(xs: list[float], q: float):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def headline_metrics(stack: str, d: dict) -> dict:
    S, runs = d["summary"], d["runs"]
    fin_v = S["final_version"]
    test_v0 = [r for r in runs if r.get("set") == "test" and r.get("playbook_version") == 0]
    test_fin = [r for r in runs if r.get("set") == "test" and r.get("playbook_version") == fin_v]
    agent_runs = [r for r in runs]
    tin = sum(r.get("tokens_in") or 0 for r in agent_runs)
    tout = sum(r.get("tokens_out") or 0 for r in agent_runs)
    co = S["cost"]
    mt_in, mt_out = co["mentor_tokens_in"], co["mentor_tokens_out"]
    price = PRICE.get(stack)

    def dollars(i, o):
        return None if price is None else round(i / 1e6 * price[0] + o / 1e6 * price[1], 4)

    def per_pass(rs):
        p = sum(1 for r in rs if r.get("passed"))
        i = sum(r.get("tokens_in") or 0 for r in rs)
        o = sum(r.get("tokens_out") or 0 for r in rs)
        return {"passing_runs": p, "tokens_per_pass": round((i + o) / p) if p else None,
                "usd_per_pass": (None if dollars(i, o) is None or not p else round(dollars(i, o) / p, 4))}

    def consistency(rs):
        g: dict[str, list] = {}
        for r in rs:
            g.setdefault(r["case_id"], []).append(r)
        multi = {c: v for c, v in g.items() if len(v) > 1}
        if not multi:
            return {"identical_share": None, "mean_score_std": None}
        same = sum(1 for v in multi.values() if len({bool(x.get("passed")) for x in v}) == 1)
        stds = [statistics.pstdev([x.get("score") or 0 for x in v]) for v in multi.values()]
        return {"identical_share": round(same / len(multi), 3), "mean_score_std": round(statistics.mean(stds), 3)}

    def hard_rate(rs):
        return round(sum(1 for r in rs if any(v.get("severity") == "hard" for v in r.get("violations") or [])) / len(rs), 3) if rs else None

    secs = [r.get("seconds") or 0 for r in runs if r.get("set") != "journey"]

    def infra(r):  # the model API failed mid-run (rate limit / 5xx), not an agent decision
        e = r.get("error") or ""
        return e.startswith("provider error") or (e == "agent did not write recommendation.json"
                                                   and (r.get("turns") or 0) <= 2 and (r.get("tokens_out") or 0) < 400)
    infra_n = sum(1 for r in runs if infra(r))
    agent_err_n = sum(1 for r in runs if r.get("error") and not infra(r))
    logs = [x["msg"] for x in d["store"].find("loop_log")]
    bench_first_bad = sum(1 for m_ in logs if m_.startswith("[bench") and "mentor attempt 1 invalid" in m_)
    bench_seq = sum(1 for g in S["generations"] if g.get("mode") in ("training", "control"))
    j_first_bad = sum(1 for m_ in logs if m_.startswith("[journey") and "mentor attempt 1 invalid" in m_)
    j_seq = sum(1 for m_ in logs if m_.startswith("[journey") and (" LEARNED " in m_ or " rejected " in m_)) + \
        sum(1 for m_ in logs if m_.startswith("[journey") and "mentor attempt 2 invalid" in m_)
    seq = bench_seq + j_seq
    tr = [g for g in S["generations"] if g.get("mode") == "training"]
    shipped = [g for g in tr if g.get("decision") == "shipped"]
    ctrl = (S.get("control") or {}).get("gain")
    snap_tokens = sum(e.get("input_tokens") or 0 for e in ((S["drift"].get("snap") or {}).get("event_gates") or []))
    snap_tokens += ((S["drift"].get("snap") or {}).get("window") or {}).get("input_tokens") or 0
    js = d["jsumm"]
    improved = sum(1 for j in js if (j["holdout_mean_final"] or 0) > (j["holdout_mean_start"] or 0) + 1e-9)
    worse = sum(1 for j in js if (j["holdout_mean_final"] or 0) < (j["holdout_mean_start"] or 0) - 1e-9)
    an = S["drift"].get("analysis") or {}
    return {
        "cost": {"agent_tokens_in": tin, "agent_tokens_out": tout, "mentor_tokens_in": mt_in, "mentor_tokens_out": mt_out,
                 "agent_usd": dollars(tin, tout), "mentor_usd": dollars(mt_in, mt_out),
                 "snap_tokens": snap_tokens, "snap_usd": round(snap_tokens / 1e6 * SNAP_PRICE_IN, 5) if snap_tokens else None,
                 "v0": per_pass(test_v0), "final": per_pass(test_fin)},
        "consistency": {"v0": consistency(test_v0), "final": consistency(test_fin)},
        "latency": {"p50": pctl(secs, 0.5), "p95": pctl(secs, 0.95)},
        "errors": {"runs": len(runs), "infra": infra_n, "agent": agent_err_n,
                   "max_turns": sum(1 for r in runs if (r.get("error") or "").startswith("max_turns"))},
        "hard_violation_rate": {"v0": hard_rate(test_v0), "final": hard_rate(test_fin)},
        "pass_rate_runs": {"v0": S["v0"]["test"]["run_pass_rate"], "final": S["final_test"]["run_pass_rate"]},
        "mentor": {"valid_first_try": round(1 - (bench_first_bad + j_first_bad) / seq, 3) if seq else None,
                   "proposal_sequences": seq, "ship_rate": f"{len(shipped)}/{len(tr)}",
                   "mean_gain_shipped": round(statistics.mean(g["gain"] for g in shipped), 4) if shipped else None,
                   "control_gain": ctrl,
                   "regressions_blocked": sum(len(g.get("lost") or []) for g in tr if g.get("decision") != "shipped")
                   + sum(1 for m_ in logs if "broke earlier" in m_),
                   "regressions_shipped": sum(len(g.get("lost") or []) for g in shipped)},
        "journeys": {"improved": improved, "same": len(js) - improved - worse, "worse": worse},
        "analyst": {k: an.get(k) for k in ("provider", "model", "runs_read", "tokens_read", "seconds")},
    }


def headline_section(stacks: dict[str, dict]) -> list[str]:
    H = {k: headline_metrics(k, v) for k, v in stacks.items()}
    names = list(stacks)

    def r(label, f):
        return "| " + label + " | " + " | ".join(f(H[n]) for n in names) + " |"
    usd = lambda x: "–" if x is None else f"${x:,.4f}"
    L = ["## Headline metrics per stack", "",
         "| Metric | " + " | ".join(stacks[n]["summary"]["label"].split(" (")[0] for n in names) + " |",
         "|---|" + "---|" * len(names),
         r("Run pass rate on unseen test, v0 → final", lambda h: f"{pct(h['pass_rate_runs']['v0'])} → {pct(h['pass_rate_runs']['final'])}"),
         r("Hard-rule violation rate, v0 → final", lambda h: f"{pct(h['hard_violation_rate']['v0'])} → {pct(h['hard_violation_rate']['final'])}"),
         r("Consistency: cases identical across repeats, v0 → final", lambda h: f"{pct(h['consistency']['v0']['identical_share'])} → {pct(h['consistency']['final']['identical_share'])}"),
         r("Mean per-case score std-dev, v0 → final", lambda h: f"{fmt(h['consistency']['v0']['mean_score_std'])} → {fmt(h['consistency']['final']['mean_score_std'])}"),
         r("Latency per case p50 / p95 (s)", lambda h: f"{fmt(h['latency']['p50'], 1)} / {fmt(h['latency']['p95'], 1)}"),
         r("Tokens per passing case (final)", lambda h: f"{h['cost']['final']['tokens_per_pass']:,}" if h['cost']['final']['tokens_per_pass'] else "–"),
         r("Cost per passing recommendation (final)", lambda h: usd(h['cost']['final']['usd_per_pass'])),
         r("Agent tokens in / out (whole run)", lambda h: f"{h['cost']['agent_tokens_in']:,} / {h['cost']['agent_tokens_out']:,}"),
         r("Agent cost (whole run)", lambda h: usd(h['cost']['agent_usd'])),
         r("Mentor tokens in / out, cost", lambda h: f"{h['cost']['mentor_tokens_in']:,} / {h['cost']['mentor_tokens_out']:,}, {usd(h['cost']['mentor_usd'])}"),
         r("Snap tokens, cost", lambda h: f"{h['cost']['snap_tokens']:,}, {usd(h['cost']['snap_usd'])}" if h['cost']['snap_tokens'] else "not used"),
         r("Mentor valid on first try", lambda h: f"{pct(h['mentor']['valid_first_try'])} of {h['mentor']['proposal_sequences']}"),
         r("Fleet versions shipped / tried", lambda h: h['mentor']['ship_rate']),
         r("Mean gain per shipped version vs own control arm", lambda h: f"{fmt(h['mentor']['mean_gain_shipped'], sign=True)} vs {fmt(h['mentor']['control_gain'], sign=True)}"),
         r("Regressions blocked by gates / shipped", lambda h: f"{h['mentor']['regressions_blocked']} / {h['mentor']['regressions_shipped']}"),
         r("Journeys improved / same / worse (holdout mean)", lambda h: f"{h['journeys']['improved']} / {h['journeys']['same']} / {h['journeys']['worse']}"),
         r("Drift analyst: runs read, tokens, seconds", lambda h: f"{h['analyst'].get('runs_read')}, {h['analyst'].get('tokens_read')}, {h['analyst'].get('seconds')} ({h['analyst'].get('model')})"),
         "",
         "Pricing: Muse at $1.25 / 1M input and $4.25 / 1M output (published Spark pricing; Wonder assumed the same). SubQ Preview and Gemini 3.8 Flash prices "
         "were not published to us, so their $ cells are blank and tokens are reported instead. Snap at $0.04 / 1M input, output free. Tokenizers differ between "
         "providers and reasoning tokens are included in output counts, so tokens are comparable within a stack, not exactly across stacks.", ""]
    return L, H


FAIRNESS = ["## Fairness controls", "",
            "Every stack ran under identical conditions; only the model behind the agent and the mentor changed:",
            "- **Harness:** the same Pi coding-agent setup (tools `read`, `bash`, `write`; same sandbox user; same turn and time limits).",
            "- **Prompts:** the same generic starting playbook (`agent/playbooks/v000-generic.yaml`), the same task message, the same mentor prompt (`runtime/prompts/mentor.md`).",
            "- **Data and seeds:** the same cases, the same held-out market months, the same journeys, the same shuffling seed for the control arm.",
            "- **Gates:** the same paired gate (mean gain ≥ 0.02, bootstrap 90% CI above zero, no lost test client, regression flips re-checked, backtest not worse) and the same validator.",
            "- **Repeats:** the same number of runs per test client.",
            "- **Reviewer:** Gemini is the only compliance reviewer for every stack.",
            "",
            "SubQ Preview is a long-context model. The agent role (short cases, many tool turns) does not play to that strength; the drift-analyst role, "
            "which reads every run in one call, is the better test of it. Its analyst run is reported under each stack's drift section.", ""]


def main() -> None:
    m, s = load_stack("muse"), load_stack("subq")
    if not (m["summary"] and s["summary"]):
        print("missing stack summaries", bool(m["summary"]), bool(s["summary"]))
        return
    M, Q = m["summary"], s["summary"]

    def row(label, f):
        return f"| {label} | {f(M)} | {f(Q)} |"
    jm = {j["journey"]: j for j in m["jsumm"]}
    jq = {j["journey"]: j for j in s["jsumm"]}
    L = ["# ballast. benchmark: one framework, several models", "",
         "**What this shows.** ballast. is model-agnostic: the same harness, the same gates and the same generic starting skill file "
         "are applied to each model, and we measure whether the framework (failure → root cause → new skill → gated ship) improves "
         "that model and whether the gates catch that model's bad changes. It is not a contest between models; differences between "
         "stacks are reported so you can see where each one adapts or struggles. Honest negatives are kept.", "",
         "Same tests, same gates, same generic starting skill file, Gemini as the only reviewer. "
         f"Unseen test = 20 clients × {M['repeats']} runs each; a client passes if it passes in the majority of runs. "
         "Gains are paired per client with a bootstrap 90% confidence interval. Every run is also backtested over 12 real held-out months.",
         "", "| | Muse stack | SubQ stack |", "|---|---|---|",
         row("Agent / mentor", lambda x: f"{x['agent_model']} / {x['mentor']}"),
         row("Unseen test mean score, v0 → final", lambda x: f"{fmt(x['v0']['test']['mean_score'])} → {fmt(x['final_test']['mean_score'])}"),
         row("Paired gain (90% CI)", lambda x: f"{fmt(x['final_gain_vs_v0'][0], sign=True)} ({fmt(x['final_gain_vs_v0'][1], sign=True)} … {fmt(x['final_gain_vs_v0'][2], sign=True)})"),
         row("Clients passing, v0 → final", lambda x: f"{pct(x['v0']['test']['pass_rate'])} → {pct(x['final_test']['pass_rate'])}"),
         row("Versions shipped / tried", lambda x: f"{sum(1 for g in x['generations'] if g.get('decision') == 'shipped' and g.get('mode') == 'training')} / {sum(1 for g in x['generations'] if g.get('mode') == 'training')}"),
         row("Control arm gain (shuffled failures)", lambda x: fmt((x.get('control') or {}).get('gain'), sign=True)),
         row("Backtest clients with breach, v0 → final", lambda x: f"{x['v0']['test']['backtest']['case_breaches']} → {x['final_test']['backtest']['case_breaches']}"),
         row("Backtest clients forced to sell, v0 → final", lambda x: f"{x['v0']['test']['backtest']['case_forced_sales']} → {x['final_test']['backtest']['case_forced_sales']}"),
         row("Drift set: pass rate / level", lambda x: f"{pct(x['drift']['summary']['pass_rate'])} / {x['drift']['level']}"),
         row("Lessons in final playbook", lambda x: str(len(x.get('lessons') or []))),
         row("Agent mean seconds / turns", lambda x: f"{x['final_test']['agent']['mean_seconds']} / {x['final_test']['agent']['mean_turns']}"),
         row("Agent error rate (final test)", lambda x: pct(x['final_test']['agent']['error_rate'])),
         row("Mentor calls / tokens out", lambda x: f"{x['cost']['mentor_calls']} / {x['cost']['mentor_tokens_out']:,}"),
         row("Wall clock", lambda x: f"{x['cost']['wall_minutes']} min"),
         "", "### Journeys, holdout quarters (generic agent → client's own agent)", "",
         "| Client | Muse | SubQ |", "|---|---|---|"]
    for jid in sorted(set(jm) | set(jq)):
        a, b = jm.get(jid, {}), jq.get(jid, {})
        L.append(f"| {a.get('client') or b.get('client')} | {a.get('holdout_pass_start', '–')} → {a.get('holdout_pass_final', '–')} ({a.get('lessons', 0)} lessons) | "
                 f"{b.get('holdout_pass_start', '–')} → {b.get('holdout_pass_final', '–')} ({b.get('lessons', 0)} lessons) |")
    fb_lines, fb_data = subq_feedback(m, s)
    hl_lines, hl_data = headline_section({"muse": m, "subq": s})
    L = L[:6] + FAIRNESS + L[6:]
    L += [""] + hl_lines + side_by_side(m, s) + [""] + section_stack("muse", m) + section_stack("subq", s) + fb_lines
    L += ["## Method notes", "",
          "- Policy rules and thresholds are illustrative; clients are synthetic; market returns are real monthly data (Kenneth French library, FRED).",
          "- The mentor sees violation details for practice clients only; test, regression, drift and journey holdout quarters are never shown to it.",
          "- Run-to-run noise is real: the same agent and case can pass once and fail the next run. That is why every gate decision uses 3 runs per client and a paired confidence interval, and regression flips are re-run before they count.",
          "- The control arm uses the same mentor and gate with shuffled evidence; a real effect should beat it."]
    out = ROOT / "docs" / "BENCHMARK.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    os.environ["MONGODB_DB"] = "ballast_muse"
    Store().insert("benchmarks", {"kind": "comparison",
                                  "stacks": {"muse": json.loads(json.dumps({k: v for k, v in M.items() if k != "drift"}, default=str)),
                                             "subq": json.loads(json.dumps({k: v for k, v in Q.items() if k != "drift"}, default=str))},
                                  "subq_feedback": fb_data, "headline": json.loads(json.dumps(hl_data, default=str)),
                                  "markdown_path": "docs/BENCHMARK.md"})
    print("wrote", out)


def load_stack2(stack: str) -> dict:
    os.environ["MONGODB_DB"] = f"ballast_bench2_{stack}"
    s = Store()
    summ = s.find("benchmarks", {"kind": "stack"}, sort="created_at", desc=True, limit=1)
    return {"store": s, "summary": summ[0] if summ else None, "runs": s.find("runs"),
            "gens": s.find("generations", sort="created_at"), "jsteps": s.find("journey_steps", sort="created_at"),
            "jsumm": s.find("journey_summaries")}


def report2() -> None:
    order = ["muse", "subq", "gemini", "mixed"]
    D = {k: load_stack2(k) for k in order}
    D = {k: v for k, v in D.items() if v["summary"]}
    if not D:
        print("no phase-2 summaries yet")
        return
    names = list(D)
    lab = {k: D[k]["summary"]["label"].split(" (")[0] for k in names}
    H = {k: headline_metrics(k, D[k]) for k in names}

    def row(label, f):
        return "| " + label + " | " + " | ".join(f(k) for k in names) + " |"
    S = {k: D[k]["summary"] for k in names}
    L = ["", "---", "", "# Framework across models (phase 2: harder data)", "",
         "Same protocol for every model on the harder data: 300 stress cases with a 54-type event taxonomy (financial-services crises such as a firm "
         "collapse, deferred-compensation loss, trading blackout windows and margin calls; cascading health, family and debt events), split by a fixed seed "
         "into 60 practice and 60 test cases stratified by event family, plus the original 10 regression cases. Unseen test = 60 clients × 2 runs. "
         "The mentor uses structured JSON output for every model. Gemini reviews every stack, including its own (self-review caveat for the Gemini stack).", "",
         "| | " + " | ".join(lab[k] for k in names) + " |", "|---|" + "---|" * len(names),
         row("Agent / mentor", lambda k: f"{S[k]['agent_model']} / {S[k]['mentor']}"),
         row("Unseen test mean, generic v0 → final", lambda k: f"{fmt(S[k]['v0']['test']['mean_score'])} → {fmt(S[k]['final_test']['mean_score'])} (v{S[k]['final_version']})"),
         row("Paired gain, 90% CI", lambda k: f"{fmt(S[k]['final_gain_vs_v0'][0], sign=True)} ({fmt(S[k]['final_gain_vs_v0'][1], sign=True)}…{fmt(S[k]['final_gain_vs_v0'][2], sign=True)})"),
         row("Control arm gain (shuffled failures)", lambda k: fmt((S[k].get('control') or {}).get('gain'), sign=True)),
         row("Clients passing, v0 → final", lambda k: f"{pct(S[k]['v0']['test']['pass_rate'])} → {pct(S[k]['final_test']['pass_rate'])}"),
         row("Hard-rule violation rate, v0 → final", lambda k: f"{pct(H[k]['hard_violation_rate']['v0'])} → {pct(H[k]['hard_violation_rate']['final'])}"),
         row("Consistency across repeats, v0 → final", lambda k: f"{pct(H[k]['consistency']['v0']['identical_share'])} → {pct(H[k]['consistency']['final']['identical_share'])}"),
         row("Backtest breaches / forced sales, v0 → final", lambda k: f"{S[k]['v0']['test']['backtest']['case_breaches']}/{S[k]['v0']['test']['backtest']['case_forced_sales']} → {S[k]['final_test']['backtest']['case_breaches']}/{S[k]['final_test']['backtest']['case_forced_sales']}"),
         row("Versions shipped / tried", lambda k: H[k]['mentor']['ship_rate']),
         row("Mentor valid on first try", lambda k: pct(H[k]['mentor']['valid_first_try'])),
         row("Regressions blocked / shipped", lambda k: f"{H[k]['mentor']['regressions_blocked']} / {H[k]['mentor']['regressions_shipped']}"),
         row("Journeys improved / same / worse", lambda k: f"{H[k]['journeys']['improved']} / {H[k]['journeys']['same']} / {H[k]['journeys']['worse']}"),
         row("Latency p50 / p95 (s)", lambda k: f"{fmt(H[k]['latency']['p50'], 1)} / {fmt(H[k]['latency']['p95'], 1)}"),
         row("Errors: agent (of which out of turns) / provider-side, of runs", lambda k: f"{H[k]['errors']['agent']} ({H[k]['errors']['max_turns']}) / {H[k]['errors']['infra']} of {H[k]['errors']['runs']}"),
         row("Agent tokens in / out", lambda k: f"{H[k]['cost']['agent_tokens_in']:,} / {H[k]['cost']['agent_tokens_out']:,}"),
         row("Agent cost", lambda k: "–" if H[k]['cost']['agent_usd'] is None else f"${H[k]['cost']['agent_usd']:,.2f}"),
         row("Wall clock", lambda k: f"{S[k]['cost']['wall_minutes']} min"), ""]
    total_tokens = sum(H[k]["cost"]["agent_tokens_in"] + H[k]["cost"]["agent_tokens_out"] + H[k]["cost"]["mentor_tokens_in"] + H[k]["cost"]["mentor_tokens_out"] for k in names)
    L += [f"Total tokens across all phase-2 stacks: {total_tokens:,}.", ""]

    fams = sorted({f for k in names for f in (S[k].get("families") or {})})
    L += ["## Where each model adapts or struggles (unseen test pass rate by event family, v0 → final)", "",
          "| Family | n | " + " | ".join(lab[k] for k in names) + " |", "|---|---|" + "---|" * len(names)]
    for f in fams:
        n = next((S[k]["families"][f].get("v0", {}).get("n_cases") for k in names if f in (S[k].get("families") or {})), "")
        cells = []
        for k in names:
            x = (S[k].get("families") or {}).get(f, {})
            a, b = x.get("v0", {}).get("pass_rate"), x.get("final", {}).get("pass_rate")
            arrow = "" if a is None or b is None else (" ▲" if b > a else (" ▼" if b < a else ""))
            cells.append(f"{pct(a)} → {pct(b)}{arrow}")
        L.append(f"| {f} | {n} | " + " | ".join(cells) + " |")
    L += ["", "Top failing rules per family at the final version:", ""]
    for f in fams:
        parts = []
        for k in names:
            tf = ((S[k].get("families") or {}).get(f, {}).get("final") or {}).get("top_fail") or []
            if tf:
                parts.append(f"{lab[k]}: " + ", ".join(f"`{r}` {c}" for r, c in tf))
        if parts:
            L.append(f"- **{f}** — " + "; ".join(parts))
    L += ["", "## Gate decisions per model", ""]
    for k in names:
        L.append(f"**{lab[k]}**")
        for g in S[k]["generations"]:
            if g.get("mode") == "baseline":
                continue
            L.append(f"- v{g['version']} {g.get('mode')}: {g.get('decision', '').upper()} — {g.get('reason', '')}")
        L.append("")
    L += ["## Lessons per model (final playbook)", ""]
    for k in names:
        L.append(f"**{lab[k]}**")
        for les in S[k].get("lessons") or []:
            L.append(f"- \"{les.get('lesson')}\" — triggered by {les.get('triggered_by')}, rule `{les.get('rule')}`")
        if not S[k].get("lessons"):
            L.append("- (none shipped)")
        L.append("")
    L += ["## Journeys per model (holdout quarters: generic agent → client's own agent)", "",
          "| Journey | " + " | ".join(lab[k] for k in names) + " |", "|---|" + "---|" * len(names)]
    js = sorted({j["journey"] for k in names for j in D[k]["jsumm"]})
    for jid in js:
        cells = []
        client = ""
        for k in names:
            j = next((x for x in D[k]["jsumm"] if x["journey"] == jid), None)
            if j:
                client = j.get("client") or client
                cells.append(f"{j['holdout_pass_start']}→{j['holdout_pass_final']} ({fmt(j['holdout_mean_start'], 2)}→{fmt(j['holdout_mean_final'], 2)}, {j['lessons']} lessons)")
            else:
                cells.append("–")
        L.append(f"| {jid} {client} | " + " | ".join(cells) + " |")
    L += ["", "## Specific failures on the harder data (generic v0, first run)", ""]
    for k in names:
        L.append(f"**{lab[k]}**")
        bad = [r for r in D[k]["runs"] if r.get("set") == "test" and r.get("playbook_version") == 0 and not r.get("passed") and r.get("rep", 0) == 0]
        bad.sort(key=lambda r: r.get("score") or 0)
        for r in bad[:4]:
            v = "; ".join(f"`{x['rule']}`: {x['detail']}" for x in r.get("violations", []))
            L.append(f"- `{r['case_id']}` ({r.get('family')}) — agent did: {trades_text(r.get('recommendation'))} — {v}")
        L.append("")
    L += ["Notes: the Gemini stack is reviewed by Gemini, so its compliance gate is a self-review; the other gates (paired gain, CI, lost clients, "
          "regression re-checks, backtest) are model-independent. Prices are only published for Muse; other stacks report tokens.", ""]
    out = ROOT / "docs" / "BENCHMARK.md"
    text = out.read_text(encoding="utf-8") if out.exists() else ""
    marker = "\n---\n\n# Framework across models (phase 2"
    if marker in text:
        text = text[: text.index(marker)]
    out.write_text(text.rstrip("\n") + "\n" + "\n".join(L) + "\n", encoding="utf-8")
    os.environ["MONGODB_DB"] = "ballast_muse"
    Store().insert("benchmarks", {"kind": "framework_across_models", "phase": "2",
                                  "stacks": {k: json.loads(json.dumps({x: y for x, y in S[k].items() if x not in ("drift",)}, default=str)) for k in names},
                                  "headline": json.loads(json.dumps(H, default=str)), "markdown_path": "docs/BENCHMARK.md"})
    print("appended phase 2 to", out)


def muse_spend() -> dict:
    """All Muse usage recorded in MongoDB today: agent runs with a meta/ model + mentor tokens."""
    from pymongo import MongoClient
    c = MongoClient(os.environ["MONGODB_URI"])
    rows = []
    for name in sorted(c.list_database_names()):
        if not name.startswith("ballast"):
            continue
        db = c[name]
        if "runs" not in db.list_collection_names():
            continue
        agg = list(db.runs.aggregate([{"$match": {"model": {"$regex": "^meta/"}}},
                                      {"$group": {"_id": None, "n": {"$sum": 1}, "i": {"$sum": "$tokens_in"}, "o": {"$sum": "$tokens_out"}}}]))
        mt = 0
        muse_mentor_dbs = {"ballast_bench_muse", "ballast_bench2_muse", "ballast_muse"}  # the other DBs used SubQ/Gemini mentors
        for coll in (("generations", "journey_steps") if name in muse_mentor_dbs else ()):
            if coll in db.list_collection_names():
                for g in db[coll].find({"mentor_tokens": {"$exists": True}}, {"mentor_tokens": 1}):
                    mt += g.get("mentor_tokens") or 0
        if name == "ballast_bench_muse":
            s = db.benchmarks.find_one({"kind": "stack"}) or {}
            co = s.get("cost") or {}
            mt += (co.get("mentor_tokens_in") or 0) + (co.get("mentor_tokens_out") or 0)
        if agg or mt:
            a = agg[0] if agg else {"n": 0, "i": 0, "o": 0}
            rows.append({"db": name, "runs": a["n"], "tokens_in": a["i"], "tokens_out": a["o"], "mentor_tokens": mt})
    for r in rows:
        r["agent_usd"] = round(r["tokens_in"] / 1e6 * 1.25 + r["tokens_out"] / 1e6 * 4.25, 2)
        r["mentor_usd_max"] = round(r["mentor_tokens"] / 1e6 * 4.25, 2)  # in/out split not stored: priced at the output rate (upper bound)
    return {"rows": rows, "agent_usd": round(sum(r["agent_usd"] for r in rows), 2),
            "mentor_usd_max": round(sum(r["mentor_usd_max"] for r in rows), 2)}


def partial2() -> None:
    """Phase 2 stopped early (budget / credits). Summarize what was collected from raw runs."""
    labels = {"muse": "Muse (Spark agent, Wonder mentor)", "subq": "SubQ Preview", "gemini": "Gemini 3.8 Flash"}
    status = {"muse": "stopped for budget (Muse credit cap ~$100)",
              "subq": "stopped: SubQ credit ran out (402 insufficient_credits from stress case s-074); runs after that excluded",
              "gemini": "stopped for budget after the sandbox fix restart (v0 evaluation incomplete)",
              "mixed": "stopped for budget during v0 (Muse agent); its database was reset when SubQ credit ran out, so its runs are not in this report"}
    L = ["", "---", "", "# Framework across models (phase 2: harder data) — PARTIAL", "",
         "**Partial result.** Phase 2 was stopped before any stack finished: Muse and the mixed stack for budget, SubQ when its credit ran out "
         "(HTTP 402 `insufficient_credits`), Gemini for budget. No training generation completed in phase 2, so there are no phase-2 gate decisions or "
         "fleet gains to report. What follows is the generic-v0 behavior on the harder data and the per-client journey learning that did complete.", "",
         "Setup: 300 stress cases (54 event types, incl. financial-services crises: firm collapse, deferred-comp loss, blackout windows, margin calls; "
         "cascading health/family/debt events), fixed-seed 60/60 practice/test split stratified by event family; journeys j-008, j-012, j-015, j-018, "
         "j-020, j-021, j-024, j-027. Same harness, structured-JSON mentor, Gemini reviewer.", "",
         "| Stack | Status |", "|---|---|"] + [f"| {labels.get(k, k)} | {v} |" for k, v in status.items()] + [""]
    from pymongo import MongoClient
    c = MongoClient(os.environ["MONGODB_URI"])

    def infra(r):
        e = r.get("error") or ""
        return e.startswith("provider error") or (e == "agent did not write recommendation.json"
                                                   and (r.get("turns") or 0) <= 2 and (r.get("tokens_out") or 0) < 400)
    out = {}
    for k in ("muse", "subq", "gemini"):
        db = c[f"ballast_bench2_{k}"]
        runs = list(db.runs.find({}, {"steps": 0}).sort("created_at", 1))
        if k == "subq":
            first_bad = next((r["created_at"] for r in runs if infra(r)), None)
            runs = [r for r in runs if not first_bad or r["created_at"] < first_bad]
        t0 = [r for r in runs if r.get("set") == "test" and r.get("playbook_version") == 0 and not infra(r)]
        fam: dict[str, list] = {}
        for r in t0:
            fam.setdefault(r.get("family") or "unknown", []).append(r)
        hard = sum(1 for r in t0 if any(v.get("severity") == "hard" for v in r.get("violations") or []))
        steps = list(db.journey_steps.find({}, {"_id": 0}).sort("created_at", 1))
        out[k] = {"runs": len(runs), "t0": t0, "fam": fam, "hard": hard, "steps": steps,
                  "errors": {"max_turns": sum(1 for r in runs if (r.get("error") or "").startswith("max_turns")),
                             "timeout": sum(1 for r in runs if (r.get("error") or "").startswith("timeout")),
                             "infra": sum(1 for r in runs if infra(r)),
                             "other": sum(1 for r in runs if r.get("error") and not infra(r) and not (r.get("error") or "").startswith(("max_turns", "timeout")))},
                  "secs": [r.get("seconds") or 0 for r in runs]}
    ks = list(out)
    L += ["## Generic v0 on unseen stress cases (runs completed before the stop)", "",
          "| | " + " | ".join(labels[k] for k in ks) + " |", "|---|" + "---|" * len(ks),
          "| Test runs scored | " + " | ".join(str(len(out[k]["t0"])) for k in ks) + " |",
          "| Run pass rate | " + " | ".join(pct(sum(1 for r in out[k]["t0"] if r.get("passed")) / len(out[k]["t0"])) if out[k]["t0"] else "–" for k in ks) + " |",
          "| Mean score | " + " | ".join(fmt(statistics.mean(r.get("score") or 0 for r in out[k]["t0"])) if out[k]["t0"] else "–" for k in ks) + " |",
          "| Hard-rule violation rate | " + " | ".join(pct(out[k]["hard"] / len(out[k]["t0"])) if out[k]["t0"] else "–" for k in ks) + " |",
          "| Ran out of turns / timed out (all runs) | " + " | ".join(f"{out[k]['errors']['max_turns']} / {out[k]['errors']['timeout']} of {out[k]['runs']}" for k in ks) + " |",
          "| Provider-side errors (excluded) | " + " | ".join(str(out[k]["errors"]["infra"]) for k in ks) + " |",
          "| Latency p50 / p95 (s) | " + " | ".join(f"{fmt(pctl(out[k]['secs'], .5), 1)} / {fmt(pctl(out[k]['secs'], .95), 1)}" for k in ks) + " |", "",
          "For reference, on the same stress cases the scenario generator's naive rebalancer passes 34% and doing nothing passes 18%.", "",
          "### By event family (generic v0, run pass rate, n runs)", "", "| Family | " + " | ".join(labels[k] for k in ks) + " |", "|---|" + "---|" * len(ks)]
    for f in sorted({f for k in ks for f in out[k]["fam"]}):
        cells = []
        for k in ks:
            g = out[k]["fam"].get(f, [])
            cells.append(f"{pct(sum(1 for r in g if r.get('passed')) / len(g))} ({len(g)})" if g else "–")
        L.append(f"| {f} | " + " | ".join(cells) + " |")
    L += ["", "### Specific failures (generic v0)", ""]
    for k in ks:
        bad = sorted([r for r in out[k]["t0"] if not r.get("passed")], key=lambda r: r.get("score") or 0)[:4]
        if bad:
            L.append(f"**{labels[k]}**")
            for r in bad:
                v = "; ".join(f"`{x['rule']}`: {x['detail']}" for x in r.get("violations", [])) or (r.get("error") or "")
                L.append(f"- `{r['case_id']}` ({r.get('family')}) — agent did: {trades_text(r.get('recommendation'))} — {v}")
            L.append("")
    L += ["### Per-client learning in journeys (completed checkpoints)", ""]
    for k in ks:
        learned = [s for s in out[k]["steps"] if s.get("action") == "learn"]
        rejected = [s for s in out[k]["steps"] if s.get("action") == "reject"]
        proved = [s for s in out[k]["steps"] if s.get("action") == "prove"]
        L.append(f"**{labels[k]}** — {len(learned)} lessons learned, {len(rejected)} candidate changes rejected by the gate, {len(proved)} holdout checkpoints scored.")
        for s in learned[:8]:
            for les in s.get("lessons") or []:
                L.append(f"- {s['journey']} at {s['checkpoint']} ({s.get('reason')}): \"{les.get('lesson')}\" — triggered by {les.get('triggered_by')}")
        for s in rejected[:4]:
            L.append(f"- rejected at {s['journey']} {s['checkpoint']}: {s.get('reason')}")
        L.append("")
    sp = muse_spend()
    L += ["## Muse spend recorded today (phase 1 + phase 2 + other runs)", "",
          "Priced at $1.25 / 1M input and $4.25 / 1M output tokens. Mentor tokens are stored as one total, so they are priced at the output rate (an upper bound).", "",
          "| Database | Muse agent runs | Tokens in | Tokens out | Agent $ | Mentor tokens | Mentor $ (max) |", "|---|---|---|---|---|---|---|"]
    for r in sp["rows"]:
        L.append(f"| {r['db']} | {r['runs']:,} | {r['tokens_in']:,} | {r['tokens_out']:,} | ${r['agent_usd']:,.2f} | {r['mentor_tokens']:,} | ${r['mentor_usd_max']:,.2f} |")
    L += [f"| **Total** | | | | **${sp['agent_usd']:,.2f}** | | **${sp['mentor_usd_max']:,.2f}** |", "",
          "Not included: the mixed stack's phase-2 runs (Muse agent; its database was reset before the budget stop, so its tokens were not kept — "
          "roughly 75–100 runs, about $3–5 at the phase-1 Muse rate per run), and any Muse calls made outside the harness (direct tests, website live runs "
          "that were not logged to these databases).", "",
          "### Also found and fixed during phase 2", "",
          "- **Run isolation.** Concurrent runs on one machine shared `/tmp` and one unprivileged user. Under the generic v0, Gemini agents ran `find /tmp` and read "
          "other concurrent runs' skill files (8 of its first 22 runs). Phase 1 had 0 such runs; Muse, SubQ and mixed in phase 2 had none that read another run's "
          "skills. Fixed by placing every run under a root-owned, non-listable `/sandbox` (verified: the agent user gets Permission denied and finds no `SKILL.md`); "
          "Gemini was restarted on the fixed image and those contaminated runs were discarded.",
          "- **Provider errors.** The harness now records the model API's own error (e.g. 402 or 429) instead of \"did not write recommendation.json\", so provider "
          "failures are reported separately from agent failures.",
          "- **Gemini under a generic skill file** ran out of its 20 turns or the 3-minute limit on most cases once it could no longer find other runs' files. That is "
          "a real behavior; whether the mentor can teach it to be decisive was the next thing phase 2 would have measured.", ""]
    path = ROOT / "docs" / "BENCHMARK.md"
    text = path.read_text(encoding="utf-8")
    marker = "\n---\n\n# Framework across models (phase 2"
    if marker in text:
        text = text[: text.index(marker)]
    path.write_text(text.rstrip("\n") + "\n" + "\n".join(L) + "\n", encoding="utf-8")
    os.environ["MONGODB_DB"] = "ballast_muse"
    Store().insert("benchmarks", {"kind": "phase2_partial", "status": status, "muse_spend": sp,
                                  "v0": {k: {"runs": len(out[k]["t0"]), "pass": sum(1 for r in out[k]["t0"] if r.get("passed"))} for k in ks}})
    print("partial phase 2 written; Muse agent $", sp["agent_usd"], "mentor max $", sp["mentor_usd_max"])


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "partial2":
        partial2()
    elif len(sys.argv) > 1 and sys.argv[1] == "phase2":
        report2()
    else:
        main()
