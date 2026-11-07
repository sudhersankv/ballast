"""check(case_dir, recommendation, run_error=None) -> {case_id, score, passed, violations, results}

score = passed applicable rules / applicable rules; valid_output failing => score 0.
passed = all applicable hard rules pass and score >= 0.8.   (EVAL.md section 4)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rules as R  # noqa: E402

PASS_SCORE = 0.8


def load_case(case_dir: str | Path) -> dict:
    d = Path(case_dir)
    ev = json.loads((d / "events.json").read_text(encoding="utf-8")) if (d / "events.json").exists() else {}
    return {
        "client": json.loads((d / "client.json").read_text(encoding="utf-8")),
        "holdings": json.loads((d / "holdings.json").read_text(encoding="utf-8")),
        "market": json.loads((d / "market.json").read_text(encoding="utf-8")),
        "events": ev.get("events", []),
    }


def check(case_dir: str | Path, recommendation: dict | None, run_error: str | None = None) -> dict:
    case = load_case(case_dir)
    case_id = case["client"].get("client_id", Path(case_dir).name)
    pre = R.pf.positions(case["holdings"])
    trades = (recommendation or {}).get("trades") if isinstance(recommendation, dict) else None
    post = R.pf.post_trade(case["holdings"], trades if isinstance(trades, list) else [])
    ctx = R.Ctx(case["client"], case["holdings"], case["market"], case["events"],
                recommendation, run_error, pre=pre, post=post)

    ok, detail = R.valid_output(ctx)
    results = [{"rule": "valid_output", "severity": "hard", "passed": ok, "detail": detail}]
    if not ok:
        return {"case_id": case_id, "score": 0.0, "passed": False,
                "violations": [{"rule": "valid_output", "severity": "hard", "detail": detail}],
                "results": results}

    for rule in R.RULES:
        res = rule(ctx)
        if res is None:
            continue
        results.append({"rule": rule.__name__, "severity": R.SEVERITY[rule.__name__],
                        "passed": bool(res[0]), "detail": res[1]})

    n_pass = sum(r["passed"] for r in results)
    score = round(n_pass / len(results), 4)
    hard_ok = all(r["passed"] for r in results if r["severity"] == "hard")
    violations = [{k: r[k] for k in ("rule", "severity", "detail")} for r in results if not r["passed"]]
    return {"case_id": case_id, "score": score, "passed": hard_ok and score >= PASS_SCORE,
            "violations": violations, "results": results}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python checker/check.py <case_dir> <recommendation.json>")
        sys.exit(2)
    rec = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    print(json.dumps(check(sys.argv[1], rec), indent=2))
