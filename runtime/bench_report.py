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
          "**Weaknesses.** Mentor output needed a format retry more often; some per-client lessons fixed the checkpoint they were learned on but did not carry "
          "to the client's later quarters (see the journeys above where the mean dropped). Each such case was caught by the time-based holdout, which is the point of the gate.",
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
    L = ["# ballast. benchmark: Muse stack vs SubQ stack", "",
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
    L += [""] + side_by_side(m, s) + [""] + section_stack("muse", m) + section_stack("subq", s) + fb_lines
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
                                  "subq_feedback": fb_data, "markdown_path": "docs/BENCHMARK.md"})
    print("wrote", out)


if __name__ == "__main__":
    main()
