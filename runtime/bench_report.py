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
    L += [""] + side_by_side(m, s) + [""] + section_stack("muse", m) + section_stack("subq", s)
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
                                  "markdown_path": "docs/BENCHMARK.md"})
    print("wrote", out)


if __name__ == "__main__":
    main()
