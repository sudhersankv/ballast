"""Hand-made checker tests from EVAL.md section 8, plus event and drift rules."""
import copy
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "checker"))
from check import check  # noqa: E402
from drift import drift_level, trusted_rules_from  # noqa: E402

FIX = ROOT / "scenarios" / "fixtures" / "c-014"

GOOD = {
    "client_id": "c-014",
    "target_allocation": {"equity": 0.56, "bond": 0.22, "cash": 0.22},
    "trades": [
        {"symbol": "ACME", "action": "sell", "amount_usd": 6000, "reason_ref": "rule:concentration"},
        {"symbol": "US_EQ", "action": "sell", "amount_usd": 16200, "reason_ref": "event:e1"},
        {"symbol": "CASH", "action": "buy", "amount_usd": 22200, "reason_ref": "event:e1"},
    ],
    "rationale": [{"ref": "event:e1", "text": "Layoff: raise cash to 6 months."},
                  {"ref": "rule:concentration", "text": "Trim ACME below 10%."}],
    "profile_updates": {"goals_add": [], "monthly_contribution": None, "risk_score": None},
    "flags": [],
    "no_action_reason": None,
}


def rules_failed(res):
    return {v["rule"] for v in res["violations"]}


def case_with(events=None, client_patch=None):
    d = Path(tempfile.mkdtemp()) / "c-014"
    shutil.copytree(FIX, d)
    if events is not None:
        (d / "events.json").write_text(json.dumps({"events": events}))
    if client_patch:
        c = json.loads((d / "client.json").read_text())
        c.update(client_patch)
        (d / "client.json").write_text(json.dumps(c))
    return d


def test_no_trades_fails_cash_and_concentration():
    rec = {**GOOD, "trades": [], "no_action_reason": "nothing to do"}
    res = check(FIX, rec)
    assert not res["passed"]
    assert {"emergency_fund", "concentration"} <= rules_failed(res)
    ef = next(v for v in res["violations"] if v["rule"] == "emergency_fund")
    assert "1.7 months, needs 6" in ef["detail"]


def test_good_layoff_passes_all():
    res = check(FIX, GOOD)
    assert res["passed"] and res["score"] == 1.0, res


def test_unbalanced_trades_invalid():
    rec = copy.deepcopy(GOOD)
    rec["trades"][2]["amount_usd"] = 20000
    res = check(FIX, rec)
    assert res["score"] == 0.0 and rules_failed(res) == {"valid_output"}


def test_uncited_trade_fails_hard():
    rec = copy.deepcopy(GOOD)
    rec["trades"][0]["reason_ref"] = "because"
    res = check(FIX, rec)
    assert not res["passed"] and "cited" in rules_failed(res)


def test_missing_file_and_run_error():
    assert check(FIX, None)["score"] == 0.0
    assert rules_failed(check(FIX, GOOD, run_error="max_turns (20) reached")) == {"valid_output"}


def test_extra_key_invalid():
    assert rules_failed(check(FIX, {**GOOD, "notes": "x"})) == {"valid_output"}


def test_child_marriage_job_change():
    d = case_with(events=[{"id": "e1", "type": "layoff", "date": "2026-10-20", "details": {}},
                          {"id": "e2", "type": "child", "date": "2026-09-01", "details": {}},
                          {"id": "e3", "type": "marriage", "date": "2026-06-01", "details": {}}])
    res = check(d, GOOD)
    assert {"event_child", "event_marriage"} <= rules_failed(res)
    rec = copy.deepcopy(GOOD)
    rec["profile_updates"]["goals_add"] = [{"type": "education", "target_year": 2044}]
    rec["flags"] = ["joint_profile_review"]
    assert check(d, rec)["passed"]


def test_job_change_needs_higher_contribution():
    d = case_with(events=[{"id": "e1", "type": "job_change", "date": "2026-10-01",
                           "details": {"new_income": 180000}}])
    rec = copy.deepcopy(GOOD)
    rec["trades"][1]["reason_ref"] = rec["trades"][2]["reason_ref"] = "rule:emergency_fund"
    assert "event_job_change" in rules_failed(check(d, rec))
    rec["profile_updates"]["monthly_contribution"] = 2200
    assert "event_job_change" not in rules_failed(check(d, rec))


def test_glidepath():
    d = case_with(client_patch={"age": 60})
    res = check(d, GOOD)  # equity 56.0% > midpoint 60%? no -> passes
    assert "glidepath" not in rules_failed(res)
    d2 = case_with(client_patch={"age": 60, "risk_score": 4})  # band 70-85, eq 56% -> risk_band fails
    assert "risk_band" in rules_failed(check(d2, GOOD))


def test_no_churn():
    d = case_with(events=[], client_patch={"targets": {"equity": 0.56, "bond": 0.22, "cash": 0.22}})
    # Pre-trade holdings fail emergency_fund (1.7 months) so trading is a needed fix -> not applicable.
    assert "no_churn" not in {r["rule"] for r in check(d, GOOD)["results"]}


def test_drift_levels():
    good = check(FIX, GOOD)
    bad = check(FIX, {**GOOD, "trades": [], "no_action_reason": "hold"})
    trusted = trusted_rules_from([good] * 5)
    assert "emergency_fund" in trusted
    assert drift_level([good] * 10, 1.0, trusted)["level"] == "green"
    red = drift_level([good] * 9 + [bad], 1.0, trusted)
    assert red["level"] == "red" and "c-014" in red["case_ids"]
