"""Muse stack vs SubQ stack benchmark for ballast.

  python runtime/bench.py run muse      # on its own machine
  python runtime/bench.py run subq      # on its own machine
  python runtime/bench.py report        # merges both, writes docs/BENCHMARK.md + benchmarks docs

Stacks (Gemini is the only reviewer in both):
  muse: agent meta/muse-spark-1.3 (Pi), mentor Muse Wonder 1.0, drift analyst Muse, no Snap
  subq: agent subq/subq-preview (Pi), mentor SubQ Preview, drift analyst SubQ Preview, Snap gates on

Protocol (identical for both, starting from agent/playbooks/v000-generic.yaml):
  a. v0: test x3, practice x1, regression x1, drift x1 (checker + 12-month market backtest on every run)
  b. control arm (from v0): mentor gets SHUFFLED failures; candidate scored on test x3 (never shipped)
  c. training: up to 3 generations; candidate on test x3 + regression x1 (flips re-checked x2)
     ship iff mean paired gain >= 0.02 AND bootstrap 90% CI lower bound > 0 AND no test case that
     passed (majority) under the parent fails (majority) AND regression flips not confirmed AND
     backtest breaches / forced sales not worse AND Gemini approves
  d. journeys: all 6 clients, per-client learning from the generic v0, holdout start vs final
  e. drift: final shipped version on the drift set; drift_level; analyst diagnosis; Snap (subq)
  f. cost and speed per role
"""
from __future__ import annotations

import json
import os
import random
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERIC = ROOT / "agent" / "playbooks" / "v000-generic.yaml"
STACKS = {
    "muse": {"agent": "meta/muse-spark-1.3", "mentor": "muse", "analyst": "muse", "snap": False,
             "label": "Muse (Spark 1.3 agent, Wonder 1.0 mentor)"},
    "subq": {"agent": "subq/subq-preview", "mentor": "subq", "analyst": "subq", "snap": True,
             "label": "SubQ (Preview agent + mentor, Snap gates)"},
    "gemini": {"agent": "google/gemini-3.8-flash", "mentor": "gemini", "analyst": "gemini", "snap": False,
               "label": "Gemini 3.8 Flash (agent + mentor; also the reviewer: self-review caveat)"},
    "mixed": {"agent": "meta/muse-spark-1.3", "mentor": "subq", "analyst": "subq", "snap": False,
              "label": "Mixed (Muse Spark agent, SubQ Preview mentor)"},
}
REPEATS = int(os.environ.get("BENCH_REPEATS", "3"))
GENERATIONS = int(os.environ.get("BENCH_GENERATIONS", "3"))
WORKERS = int(os.environ.get("BENCH_WORKERS", "8"))
DATA = os.environ.get("BENCH_DATA", "core")          # core (60 cases) | stress (300 harder cases)
PHASE = os.environ.get("BENCH_PHASE", "1")
DO_DRIFT = os.environ.get("BENCH_DRIFT", "1") == "1"
JOURNEY_IDS = [j for j in os.environ.get("BENCH_JOURNEYS", "").split(",") if j]
MIN_GAIN = 0.02
SPLIT_SEED = 2026


def db_name(stack: str) -> str:
    return f"ballast_bench_{stack}" if PHASE == "1" else f"ballast_bench{PHASE}_{stack}"


def case_family(case_id: str, events: list[str] | None = None, fs: bool = False) -> str:
    """Event family for per-family reporting (events_catalog families; FS crises separate)."""
    if fs:
        return "fs_crisis"
    sys.path.insert(0, str(ROOT / "scenarios"))
    try:
        from events_catalog import CATALOG
    except Exception:
        CATALOG = {}
    for t in events or []:
        fam = (CATALOG.get(t) or {}).get("family")
        if fam:
            return fam
    core = {"layoff": "employment", "job_change": "employment", "marriage": "family", "child": "family",
            "divorce": "family", "inheritance": "windfall", "market_drop": "market"}
    for t in events or []:
        if t in core:
            return core[t]
    return "no_event"


def stress_split() -> dict:
    """Fixed, stratified 60/60 practice/test split of the stress cases (same for every stack)."""
    man = json.loads((ROOT / "scenarios" / "cases" / "stress_manifest.json").read_text(encoding="utf-8"))
    fams: dict[str, list[str]] = {}
    family = {}
    for cid, m in sorted(man.items()):
        f = case_family(cid, m.get("types") or [], bool(m.get("fs")))
        family[cid] = f
        fams.setdefault(f, []).append(cid)
    rng = random.Random(SPLIT_SEED)
    practice, test = [], []
    for f in sorted(fams):
        ids = fams[f][:]
        rng.shuffle(ids)
        for i, cid in enumerate(ids):
            (practice if i % 2 == 0 else test).append(cid)
    rng.shuffle(practice)
    rng.shuffle(test)
    return {"practice": sorted(practice[:60]), "test": sorted(test[:60]), "family": family}


def configure(stack: str) -> None:
    c = STACKS[stack]
    os.environ.update({
        "MONGODB_DB": db_name(stack), "BALLAST_MODEL": c["agent"],
        "MENTOR_PROVIDER": c["mentor"], "ANALYST_PROVIDER": c["analyst"], "REVIEWER_PROVIDER": "gemini",
        "JOURNEY_BASE_PLAYBOOK": str(GENERIC), "SUBQ_MODEL": os.environ.get("SUBQ_MODEL", "subq-preview"),
    })


# ---------------------------------------------------------------------------------------
def run_stack(stack: str) -> None:
    configure(stack)
    sys.path[:0] = [str(ROOT / "runtime"), str(ROOT / "checker"), str(ROOT / "agent"), str(ROOT / "scenarios")]
    import yaml
    import mentor
    import journey
    from backtest import backtest
    from check import check, load_case
    from drift import drift_level, trusted_rules_from
    from loop import case_dirs, failures_for_mentor, log, store
    from run_case import run_case

    work = ROOT / "runs" / f"bench{PHASE}" / stack
    work.mkdir(parents=True, exist_ok=True)
    split = stress_split() if DATA == "stress" else None
    stress_root = ROOT / "scenarios" / "cases" / "stress"

    def dirs_for(set_name: str) -> list[Path]:
        if split and set_name in ("practice", "test"):
            return [stress_root / cid for cid in split[set_name]]
        return case_dirs(set_name)

    def family_of(case_id: str, case_dir: str) -> str:
        if split and case_id in split["family"]:
            return split["family"][case_id]
        try:
            return case_family(case_id, [e["type"] for e in load_case(case_dir)["events"]])
        except Exception:
            return "unknown"

    if split:
        (work / "split.json").write_text(json.dumps(split, indent=1), encoding="utf-8")
    cost = {"mentor_tokens_in": 0, "mentor_tokens_out": 0, "mentor_seconds": 0.0, "mentor_calls": 0}
    t_start = time.time()

    def pb_file(v: int) -> Path:
        return work / f"v{v:03d}.yaml"

    def write_pb(v: int, parent, text: str, status: str) -> None:
        pb_file(v).write_text(text, encoding="utf-8")
        store.save_playbook(v, parent, text, (yaml.safe_load(text) or {}).get("changelog", ""), status)

    def run_set(v: int, set_name: str, repeats: int = 1, dirs=None, arm: str = "main") -> list[dict]:
        dirs = dirs if dirs is not None else dirs_for(set_name)
        jobs = [(d, r) for r in range(repeats) for d in dirs]

        def one(job):
            d, r = job
            run = run_case(str(pb_file(v)), str(d))
            chk = check(d, run["recommendation"], run["error"])
            try:
                chk["backtest"] = backtest(d, run["recommendation"])
            except Exception as e:
                chk["backtest"] = {"error": f"{e.__class__.__name__}: {e}"}
            doc = store.log_run(v, set_name, run, chk)
            fam = family_of(chk["case_id"], str(d))
            store.upsert("runs", {"run_id": doc["run_id"]}, {"rep": r, "arm": arm, "stack": stack, "family": fam})
            return {"case_dir": str(d), "case_id": chk["case_id"], "rep": r, "run": run, "check": chk,
                    "run_id": doc["run_id"], "family": fam}

        with ThreadPoolExecutor(WORKERS) as ex:
            return list(ex.map(one, jobs))

    def summarize(results: list[dict]) -> dict:
        g: dict[str, list] = {}
        for r in results:
            g.setdefault(r["case_id"], []).append(r)
        case_score = {c: round(statistics.mean(x["check"]["score"] for x in rs), 4) for c, rs in g.items()}
        case_pass = {c: sum(x["check"]["passed"] for x in rs) * 2 > len(rs) for c, rs in g.items()}
        app: dict[str, int] = {}
        fail: dict[str, int] = {}
        for r in results:
            for res in r["check"].get("results", []):
                app[res["rule"]] = app.get(res["rule"], 0) + 1
                if not res["passed"]:
                    fail[res["rule"]] = fail.get(res["rule"], 0) + 1
        bts = [r["check"].get("backtest") or {} for r in results]
        okb = [b for b in bts if "forward_return" in b]
        case_breach = {c: sum(bool((x["check"].get("backtest") or {}).get("emergency_fund_breached")) for x in rs) * 2 > len(rs)
                       for c, rs in g.items()}
        case_forced = {c: sum(((x["check"].get("backtest") or {}).get("forced_sale_usd") or 0) > 0 for x in rs) * 2 > len(rs)
                       for c, rs in g.items()}
        runs = [r["run"] for r in results]
        return {
            "n_cases": len(g), "n_runs": len(results),
            "mean_score": round(statistics.mean(case_score.values()), 4) if case_score else 0.0,
            "pass_rate": round(sum(case_pass.values()) / len(case_pass), 4) if case_pass else 0.0,
            "run_pass_rate": round(sum(r["check"]["passed"] for r in results) / len(results), 4) if results else 0.0,
            "case_score": case_score, "case_pass": case_pass,
            "rule_fail_rate": {k: round(fail.get(k, 0) / n, 3) for k, n in sorted(app.items())},
            "rule_fail_count": fail,
            "backtest": {
                "runs": len(okb),
                "mean_forward_return": round(statistics.mean(b["forward_return"] for b in okb), 4) if okb else None,
                "mean_vs_hold": round(statistics.mean(b.get("vs_hold_return", 0) for b in okb), 4) if okb else None,
                "worst_drawdown": round(min(b["max_drawdown"] for b in okb), 4) if okb else None,
                "breach_runs": sum(1 for b in okb if b["emergency_fund_breached"]),
                "forced_sale_runs": sum(1 for b in okb if b["forced_sale_usd"] > 0),
                "forced_sale_usd": round(sum(b["forced_sale_usd"] for b in okb), 2),
                "case_breaches": sum(case_breach.values()), "case_forced_sales": sum(case_forced.values()),
            },
            "agent": {
                "tokens_in": sum(x.get("tokens_in") or 0 for x in runs),
                "tokens_out": sum(x.get("tokens_out") or 0 for x in runs),
                "mean_seconds": round(statistics.mean(x.get("seconds") or 0 for x in runs), 1) if runs else 0,
                "mean_turns": round(statistics.mean(x.get("turns") or 0 for x in runs), 1) if runs else 0,
                "errors": sum(1 for x in runs if x.get("error")),
                "error_rate": round(sum(1 for x in runs if x.get("error")) / len(runs), 3) if runs else 0,
            },
        }

    def paired(ps: dict, cs: dict, B: int = 2000, seed: int = 7) -> tuple[float, float, float]:
        cases = sorted(set(ps["case_score"]) & set(cs["case_score"]))
        d = [cs["case_score"][c] - ps["case_score"][c] for c in cases]
        if not d:
            return 0.0, 0.0, 0.0
        rng = random.Random(seed)
        boots = sorted(statistics.mean(rng.choice(d) for _ in d) for _ in range(B))
        return round(statistics.mean(d), 4), round(boots[int(0.05 * B)], 4), round(boots[int(0.95 * B) - 1], 4)

    def slim(s: dict) -> dict:
        return {k: v for k, v in s.items() if k not in ("case_score", "case_pass")}

    def propose(parent_text: str, fails: list[str], scores: dict, analysis=None) -> dict | None:
        feedback = None
        for attempt in range(1, 4):
            out = mentor.mentor_propose(parent_text, fails, scores, analysis, feedback)
            cost["mentor_calls"] += 1
            cost["mentor_tokens_in"] += out["reply"].tokens_in
            cost["mentor_tokens_out"] += out["reply"].tokens_out
            cost["mentor_seconds"] += out["reply"].seconds
            if not out["errors"]:
                return out
            feedback = "; ".join(out["errors"])
            log(f"[bench {stack}] mentor attempt {attempt} invalid: {feedback}")
        return None

    def shuffled_failures(results: list[dict], seed: int = 11) -> list[str]:
        rng = random.Random(seed)
        bad = [r for r in results if not r["check"]["passed"]][:8]
        out = []
        for r in bad:
            donor = rng.choice([o for o in results if o["case_id"] != r["case_id"]])
            fake = {**r["check"], "violations": donor["check"]["violations"] or
                    [{"rule": "no_churn", "severity": "soft", "detail": "made trades with nothing to do"}]}
            case = load_case(r["case_dir"])
            case["events"] = load_case(rng.choice(results)["case_dir"])["events"]
            out.append(mentor.summarize_failure(case, r["run"], fake))
        return out

    # ---- start journeys in the background (independent of fleet training) -------------
    journey_results: list[dict] = []

    journey.WORK = ROOT / "runs" / f"journeys{PHASE}"

    def journeys_thread():
        ids = JOURNEY_IDS or sorted(p.name for p in journey.JOURNEYS.iterdir()
                                    if p.is_dir() and p.name.startswith("j-") and p.name <= "j-006")
        with ThreadPoolExecutor(len(ids)) as ex:
            journey_results.extend(ex.map(journey.run_journey, ids))

    jt = threading.Thread(target=journeys_thread, daemon=True)
    jt.start()

    # ---- a. v0 --------------------------------------------------------------------------
    text0 = GENERIC.read_text(encoding="utf-8")
    write_pb(0, None, text0, "shipped")
    log(f"[bench {stack}] {STACKS[stack]['label']}: evaluating generic v0")
    v0_test = run_set(0, "test", REPEATS)
    v0_prac = run_set(0, "practice")
    v0_reg = run_set(0, "regression")
    v0_drift = run_set(0, "drift") if DO_DRIFT else []
    S = {"test": summarize(v0_test), "practice": summarize(v0_prac),
         "regression": summarize(v0_reg), "drift": summarize(v0_drift) if v0_drift else summarize(v0_reg)}
    log(f"[bench {stack}] v0 test {S['test']['pass_rate']:.2f} pass, mean {S['test']['mean_score']:.3f} | "
        f"practice {S['practice']['pass_rate']:.2f} | regression {S['regression']['pass_rate']:.2f} | drift {S['drift']['pass_rate']:.2f}")
    store.log_generation({"version": 0, "parent": None, "mode": "baseline",
                          **{k: slim(v) for k, v in S.items()}, "decision": "shipped", "reason": "generic baseline",
                          "compliance": None})
    generations = [{"version": 0, "mode": "baseline", "test": slim(S["test"]), "practice": slim(S["practice"]),
                    "regression": slim(S["regression"]), "drift": slim(S["drift"]), "decision": "shipped"}]

    cur, cur_text = 0, text0
    cur_test, cur_reg, cur_prac = v0_test, v0_reg, v0_prac
    next_v = 1

    def gate(cand_v: int, cand_text: str, mode: str) -> dict:
        review = mentor.compliance_review(cur_text, cand_text)
        ct = run_set(cand_v, "test", REPEATS, arm=mode)
        ps, cs = summarize(cur_test), summarize(ct)
        gain, lo, hi = paired(ps, cs)
        lost = sorted(c for c, p in ps["case_pass"].items() if p and not cs["case_pass"].get(c, True))
        res = {"review": review, "test_results": ct, "ps": ps, "cs": cs, "gain": gain, "ci": [lo, hi], "lost": lost}
        if mode == "control":
            res["ok"] = False
            res["reason"] = f"control arm (never shipped): gain {gain:+.3f}, 90% CI [{lo:+.3f}, {hi:+.3f}]"
            return res
        cr = run_set(cand_v, "regression", 1, arm=mode)
        pr, crs = summarize(cur_reg), summarize(cr)
        flips = [c for c, p in pr["case_pass"].items() if p and not crs["case_pass"].get(c, True)]
        confirmed = []
        for c in flips:
            d = [x for x in dirs_for("regression") if x.name == c]
            ec = run_set(cand_v, "regression", 2, d, arm=mode)
            ep = run_set(cur, "regression", 2, d, arm=mode)
            c_ok = sum(x["check"]["passed"] for x in ec + [r for r in cr if r["case_id"] == c]) >= 2
            p_ok = sum(x["check"]["passed"] for x in ep + [r for r in cur_reg if r["case_id"] == c]) >= 2
            if p_ok and not c_ok:
                confirmed.append(c)
        res.update({"reg_results": cr, "reg_flips": flips, "reg_confirmed": confirmed})
        pb, cb = ps["backtest"], cs["backtest"]
        bt_worse = cb["case_breaches"] > pb["case_breaches"] or cb["case_forced_sales"] > pb["case_forced_sales"]
        checks = {
            "gain>=0.02": gain >= MIN_GAIN, "ci_low>0": lo > 0, "no_lost_test_cases": not lost,
            "no_confirmed_regressions": not confirmed, "backtest_not_worse": not bt_worse,
            "gemini_approves": review["verdict"] == "approve",
        }
        res["checks"] = checks
        res["ok"] = all(checks.values())
        failed = [k for k, v in checks.items() if not v]
        res["reason"] = (f"test pass {ps['pass_rate']:.2f}->{cs['pass_rate']:.2f}, mean {ps['mean_score']:.3f}->{cs['mean_score']:.3f}, "
                         f"paired gain {gain:+.3f} (90% CI {lo:+.3f}..{hi:+.3f}); lost {lost or 'none'}; "
                         f"regression flips {flips or 'none'} confirmed {confirmed or 'none'}; "
                         f"backtest breaches {pb['case_breaches']}->{cb['case_breaches']}, forced sales {pb['case_forced_sales']}->{cb['case_forced_sales']}; "
                         f"Gemini {review['verdict']}" + (f" | FAILED: {', '.join(failed)}" if failed else ""))
        return res

    # ---- b. control arm (from v0) --------------------------------------------------------
    fails_shuffled = shuffled_failures(v0_prac)
    control = None
    if fails_shuffled:
        out = propose(cur_text, fails_shuffled, {"practice": S["practice"]["mean_score"], "test": S["test"]["mean_score"]})
        if out:
            out["playbook"]["version"], out["playbook"]["parent"] = next_v, cur
            ctext = yaml.safe_dump(out["playbook"], sort_keys=False, allow_unicode=True)
            write_pb(next_v, cur, ctext, "control")
            gr = gate(next_v, ctext, "control")
            control = {"version": next_v, "gain": gr["gain"], "ci": gr["ci"], "test": slim(gr["cs"]),
                       "lessons": out["playbook"].get("lessons") or [], "changelog": out["playbook"].get("changelog"),
                       "compliance": gr["review"]}
            store.log_generation({"version": next_v, "parent": cur, "mode": "control", "test": slim(gr["cs"]),
                                  "decision": "rejected", "reason": gr["reason"], "compliance": gr["review"],
                                  "gain": gr["gain"], "ci": gr["ci"]})
            log(f"[bench {stack}] CONTROL v{next_v}: {gr['reason']}")
            next_v += 1

    # ---- c. training ------------------------------------------------------------------------
    for gen in range(GENERATIONS):
        fails = failures_for_mentor(cur_prac)
        if not fails:
            log(f"[bench {stack}] no practice failures left at v{cur}")
            break
        out = propose(cur_text, fails, {"practice": summarize(cur_prac)["mean_score"], "test": summarize(cur_test)["mean_score"]})
        if out is None:
            generations.append({"version": next_v, "mode": "training", "decision": "rejected", "reason": "invalid_playbook"})
            store.log_generation({"version": next_v, "parent": cur, "mode": "training", "decision": "rejected",
                                  "reason": "invalid_playbook", "compliance": None})
            next_v += 1
            continue
        out["playbook"]["version"], out["playbook"]["parent"] = next_v, cur
        ctext = yaml.safe_dump(out["playbook"], sort_keys=False, allow_unicode=True)
        write_pb(next_v, cur, ctext, "candidate")
        gr = gate(next_v, ctext, "training")
        status = "shipped" if gr["ok"] else "rejected"
        store.set_playbook_status(next_v, status)
        new_lessons = (out["playbook"].get("lessons") or [])[len(yaml.safe_load(cur_text).get("lessons") or []):]
        gdoc = {"version": next_v, "parent": cur, "mode": "training", "test": slim(gr["cs"]),
                "regression": slim(summarize(gr["reg_results"])), "decision": status, "reason": gr["reason"],
                "compliance": gr["review"], "gain": gr["gain"], "ci": gr["ci"], "checks": gr["checks"],
                "lost": gr["lost"], "reg_flips": gr["reg_flips"], "reg_confirmed": gr["reg_confirmed"],
                "lessons_new": new_lessons, "changelog": out["playbook"].get("changelog")}
        store.log_generation(gdoc)
        generations.append(gdoc)
        log(f"[bench {stack}] v{next_v} {'SHIPPED' if gr['ok'] else 'REJECTED'}: {gr['reason']}")
        if gr["ok"]:
            cur, cur_text = next_v, ctext
            cur_test, cur_reg = gr["test_results"], gr["reg_results"]
            cur_prac = run_set(cur, "practice")
            practice_s = summarize(cur_prac)
            gdoc["practice"] = slim(practice_s)
            store.upsert("generations", {"version": cur}, {"practice": slim(practice_s)})
        next_v += 1

    # ---- e. drift on the final shipped version ------------------------------------------------
    if DO_DRIFT:
        final_drift = run_set(cur, "drift", 1, arm="drift") if cur != 0 else v0_drift
    else:
        final_drift = cur_test
    final_test_s = summarize(cur_test)
    trusted = trusted_rules_from([r["check"] for r in cur_test])
    report = drift_level([r["check"] for r in final_drift], final_test_s["mean_score"], trusted)
    drift_cases = []
    for r in final_drift:
        case = load_case(r["case_dir"])
        drift_cases.append({"case_id": r["case_id"], "events": [e["type"] for e in case["events"]],
                            "passed": r["check"]["passed"], "score": r["check"]["score"],
                            "violations": r["check"]["violations"],
                            "trades": (r["run"].get("recommendation") or {}).get("trades"),
                            "backtest": r["check"].get("backtest")})
    analysis = None
    try:
        sl = [{"playbook_version": cur, "case_id": r["case_id"], "set": s, "score": r["check"]["score"],
               "passed": r["check"]["passed"], "violations": r["check"]["violations"],
               "recommendation": r["run"].get("recommendation")} for s, rs in (("test", cur_test), ("drift", final_drift)) for r in rs]
        analysis = mentor.analyze_drift(sl, [{"version": cur, "status": "shipped", "yaml": cur_text}])
    except Exception as e:
        analysis = {"error": str(e)}
    snap_out = None
    if STACKS[stack]["snap"]:
        import snap
        try:
            pb = yaml.safe_load(cur_text)
            gates = []
            for r in final_drift:
                case = load_case(r["case_dir"])
                if case["events"]:
                    g = snap.event_gate(case, case["events"][-1], pb)
                    g["case_id"] = r["case_id"]
                    g["actually_failed"] = sorted({v["rule"] for v in r["check"]["violations"]})
                    gates.append(g)
            win = snap.window_verdict([{**r["check"], "tags": "/".join(e["type"] for e in load_case(r["case_dir"])["events"])}
                                       for r in final_drift], final_test_s["mean_score"], trusted, report)
            snap_out = {"event_gates": gates, "window": win}
        except Exception as e:
            snap_out = {"error": str(e)}
    store.log_drift({"level": report["level"], "rolling_score": report["rolling_score"], "baseline": final_test_s["mean_score"],
                     "violations": report["violations"][:40], "action": "detected" if report["level"] != "green" else "none",
                     "from_version": cur, "to_version": cur, "case_ids": report["case_ids"], "snap": (snap_out or {}).get("window")})
    log(f"[bench {stack}] drift on v{cur}: {report['level']} ({'; '.join(report['reasons']) or 'ok'})")

    # ---- d. journeys ----------------------------------------------------------------------------
    jt.join()

    # ---- f. summary -----------------------------------------------------------------------------
    pb_final = yaml.safe_load(cur_text)

    def per_family(v0_results, final_results):
        out = {}
        for tag, rs in (("v0", v0_results), ("final", final_results)):
            groups: dict[str, list] = {}
            for r in rs:
                groups.setdefault(r.get("family") or "unknown", []).append(r)
            for f, g in groups.items():
                s_ = summarize(g)
                out.setdefault(f, {})[tag] = {"n_cases": s_["n_cases"], "pass_rate": s_["pass_rate"],
                                               "mean_score": s_["mean_score"],
                                               "top_fail": sorted(s_["rule_fail_count"].items(), key=lambda kv: -kv[1])[:3]}
        return out

    summary = {
        "phase": PHASE, "data": DATA, "families": per_family(v0_test, cur_test),
        "drift_ran": DO_DRIFT,
        "stack": stack, "label": STACKS[stack]["label"], "agent_model": STACKS[stack]["agent"],
        "mentor": STACKS[stack]["mentor"], "reviewer": "gemini", "repeats": REPEATS,
        "v0": {k: slim(v) for k, v in S.items()},
        "final_version": cur, "final_test": slim(final_test_s),
        "final_gain_vs_v0": paired(S["test"], final_test_s),
        "generations": [{k: v for k, v in g.items() if k not in ("test_results",)} for g in generations],
        "control": control,
        "lessons": pb_final.get("lessons") or [], "final_changelog": pb_final.get("changelog"),
        "drift": {"level": report["level"], "reasons": report["reasons"], "rolling_score": report["rolling_score"],
                  "summary": slim(summarize(final_drift)), "cases": drift_cases, "analysis": analysis, "snap": snap_out},
        "journeys": journey_results,
        "cost": {**cost, "mentor_seconds": round(cost["mentor_seconds"], 1),
                 "wall_minutes": round((time.time() - t_start) / 60, 1)},
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    store.insert("benchmarks", {"kind": "stack", **json.loads(json.dumps(summary, default=str))})
    (work / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    log(f"[bench {stack}] DONE in {summary['cost']['wall_minutes']} min: v0 {S['test']['mean_score']:.3f} -> "
        f"v{cur} {final_test_s['mean_score']:.3f} (pass {S['test']['pass_rate']:.2f}->{final_test_s['pass_rate']:.2f})")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "run":
        run_stack(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] == "report":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import bench_report
        bench_report.main()
    else:
        print(__doc__)
