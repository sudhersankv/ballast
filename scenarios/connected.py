"""Generate 5 'connected data' clients: life changes are hidden in day-to-day data feeds.

  python scenarios/connected.py

Writes scenarios/cases/connected/cx-00N/{client,holdings,market,events}.json + connectors/*.json.
events.json holds the TRUE events for the grader; the harness hides it from the agent, which must
discover them through tools/clientdata.py.
"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "cases" / "connected"
TEMPLATE_MARKET = ROOT / "cases" / "test" / "c-021" / "market.json"
AS_OF = "2026-11-01"
BANDS = {1: (0.10, 0.30), 2: (0.30, 0.50), 3: (0.50, 0.70), 4: (0.70, 0.85), 5: (0.85, 1.00)}


def holdings(market, values):
    pos = []
    for sym, val in values.items():
        price = market["symbols"][sym]["price"]
        units = round(val / price, 4)
        pos.append({"symbol": sym, "units": units, "value": round(units * price, 2)})
    return {"as_of": AS_OF, "positions": pos}


def paychecks(start, end, net, employer, every=14):
    from datetime import date, timedelta
    d, out = date.fromisoformat(start), []
    while d.isoformat() <= end:
        out.append({"date": d.isoformat(), "description": f"PAYROLL {employer} DIRECT DEP", "amount": net, "category": "income"})
        d += timedelta(days=every)
    return out


def monthly(desc, amount, cat, months, day=1):
    return [{"date": f"{m}-{day:02d}", "description": desc, "amount": amount, "category": cat} for m in months]


MONTHS = ["2026-08", "2026-09", "2026-10"]


def base_spend(rent, groceries=900):
    return (monthly("RENT/MORTGAGE", -rent, "housing", MONTHS, 3)
            + monthly("WHOLE FOODS / TRADER JOES", -groceries, "groceries", MONTHS, 12)
            + monthly("UTILITIES", -260, "utilities", MONTHS, 18))


def clients():
    return [
        dict(id="cx-001", client=dict(name="Dana Reyes", age=41, state="NY", occupation="rates trader",
             employer="Halvard Capital Group", employment_status="employed", marital_status="single",
             annual_income=310000, monthly_expenses=11800, dependents=1, risk_score=4, horizon_years=24,
             targets={"equity": 0.75, "bond": 0.15, "cash": 0.10}, monthly_contribution=4000),
             values={"US_EQ": 380000, "INTL_EQ": 90000, "BOND": 85000, "HLXR": 56000, "CASH": 40000},
             events=[{"id": "e1", "type": "desk_shutdown", "date": "2026-10-28", "details": {"effective": "2026-12-31"}},
                     {"id": "e2", "type": "trading_blackout", "date": "2026-10-15", "details": {"symbol": "HLXR", "until": "2026-12-15"}}],
             connectors=dict(
                 payroll={"employer": "Halvard Capital Group", "status": "active", "base_salary": 210000,
                          "bonus": {"2025_total": 260000, "paid_cash": 78000, "deferred": 182000, "deferred_pct": 0.70, "vests": "2027-2029, forfeited on termination for cause"},
                          "stubs": [{"date": "2026-10-15", "gross": 8750, "net": 5420}, {"date": "2026-10-31", "gross": 8750, "net": 5420}]},
                 employer={"portal": "Halvard HR", "insider_status": "covered person",
                           "trading_windows": [{"symbol": "HLXR", "status": "BLACKOUT", "from": "2026-10-15", "until": "2026-12-15", "note": "Q4 earnings + restructuring"}],
                           "notices": [{"date": "2026-10-28", "title": "Rates trading desk wind-down", "body": "The rates desk will be wound down effective 2026-12-31. Affected employees will be contacted individually."}]},
                 bank={"as_of": AS_OF, "transactions": sorted(paychecks("2026-08-15", "2026-10-31", 5420, "HALVARD CAP") + base_spend(6200, 1300) + monthly("TUTORING - LITTLE SCHOLARS", -650, "childcare", MONTHS, 20), key=lambda t: t["date"])},
                 messages={"messages": [{"date": "2026-10-29", "text": "Crazy week. Lots of rumors on the floor. Can we talk about my HLXR shares when you get a sec?"}]},
                 calendar={"upcoming": [{"date": "2026-12-15", "title": "HLXR trading window opens"}]},
                 credit={"score": 781, "balances": [{"type": "card", "balance": 3200}]})),
        dict(id="cx-002", client=dict(name="Miguel Santos", age=36, state="AZ", occupation="ICU nurse",
             employer="Desert Valley Health", employment_status="employed", marital_status="married",
             annual_income=96000, monthly_expenses=6400, dependents=2, risk_score=3, horizon_years=29,
             targets={"equity": 0.60, "bond": 0.28, "cash": 0.12}, monthly_contribution=900),
             values={"US_EQ": 92000, "INTL_EQ": 24000, "BOND": 46000, "CASH": 21000},
             events=[{"id": "e1", "type": "layoff", "date": "2026-09-30", "details": {"severance": 6000, "reported": False}}],
             connectors=dict(
                 payroll={"employer": "Desert Valley Health", "status": "no pay stubs since 2026-09-26",
                          "stubs": [{"date": "2026-09-12", "gross": 3690, "net": 2810}, {"date": "2026-09-26", "gross": 3690, "net": 2810}]},
                 bank={"as_of": AS_OF, "transactions": sorted(paychecks("2026-08-01", "2026-09-26", 2810, "DESERT VALLEY HLTH")
                       + [{"date": "2026-10-02", "description": "DESERT VALLEY HLTH SEVERANCE", "amount": 6000, "category": "income"},
                          {"date": "2026-10-10", "description": "AZ DES UNEMPLOYMENT INS", "amount": 640, "category": "income"},
                          {"date": "2026-10-24", "description": "AZ DES UNEMPLOYMENT INS", "amount": 640, "category": "income"},
                          {"date": "2026-10-05", "description": "COBRA PREMIUM - WAGEWORKS", "amount": -1420, "category": "insurance"}]
                       + base_spend(2300, 1100), key=lambda t: t["date"])},
                 messages={"messages": []},
                 calendar={"upcoming": [{"date": "2026-11-05", "title": "COBRA premium due", "amount": 1420}]},
                 credit={"score": 742, "balances": [{"type": "card", "balance": 2100}, {"type": "auto", "balance": 14800}]})),
        dict(id="cx-003", client=dict(name="Aisha Karim", age=47, state="IL", occupation="product manager",
             employer="Lumen Freight", employment_status="employed", marital_status="married",
             annual_income=185000, monthly_expenses=9200, dependents=2, risk_score=3, horizon_years=18,
             targets={"equity": 0.62, "bond": 0.28, "cash": 0.10}, monthly_contribution=2500),
             values={"US_EQ": 230000, "INTL_EQ": 60000, "BOND": 120000, "CASH": 45000},
             events=[{"id": "e1", "type": "parent_long_term_care", "date": "2026-09-20", "details": {"monthly_cost_increase": 4100}},
                     {"id": "e2", "type": "tuition_due", "date": "2026-10-01", "details": {"amount_due": 43350, "due_date": "2027-03-01"}}],
             connectors=dict(
                 payroll={"employer": "Lumen Freight", "status": "active", "stubs": [{"date": "2026-10-31", "gross": 7710, "net": 5330}]},
                 bank={"as_of": AS_OF, "transactions": sorted(paychecks("2026-08-01", "2026-10-31", 5330, "LUMEN FREIGHT")
                       + [{"date": "2026-10-01", "description": "SUNRISE HOME CARE LLC", "amount": -4100, "category": "care"},
                          {"date": "2026-11-01", "description": "SUNRISE HOME CARE LLC", "amount": -4100, "category": "care"},
                          {"date": "2026-09-22", "description": "WALGREENS - MOBILITY AIDS", "amount": -640, "category": "medical"}]
                       + base_spend(3800, 1400), key=lambda t: t["date"])},
                 messages={"messages": [{"date": "2026-09-21", "text": "Mom moved in with us after her fall. We hired a home aide for weekdays."}]},
                 calendar={"upcoming": [{"date": "2027-03-01", "title": "Spring tuition - Northbridge University", "amount": 43350}]},
                 credit={"score": 768, "balances": [{"type": "mortgage", "balance": 312000}]})),
        dict(id="cx-004", client=dict(name="Tom Becker", age=58, state="OH", occupation="mechanical engineer",
             employer="Arden Aerospace", employment_status="employed", marital_status="married",
             annual_income=150000, monthly_expenses=7600, dependents=0, risk_score=3, horizon_years=9,
             targets={"equity": 0.58, "bond": 0.32, "cash": 0.10}, monthly_contribution=1500),
             values={"US_EQ": 310000, "INTL_EQ": 70000, "BOND": 150000, "CASH": 60000},
             events=[{"id": "e1", "type": "job_change", "date": "2026-10-01", "details": {"new_income": 168000, "employer": "Arden Aerospace (promotion)"}}],
             connectors=dict(
                 payroll={"employer": "Arden Aerospace", "status": "active", "title_change": "Senior Principal Engineer (2026-10-01)",
                          "stubs": [{"date": "2026-09-30", "gross": 6250, "net": 4480}, {"date": "2026-10-31", "gross": 7000, "net": 4990}]},
                 bank={"as_of": AS_OF, "transactions": sorted(paychecks("2026-08-15", "2026-09-30", 4480, "ARDEN AEROSPACE", 15)
                       + paychecks("2026-10-15", "2026-10-31", 4990, "ARDEN AEROSPACE", 16) + base_spend(2900, 1000), key=lambda t: t["date"])},
                 messages={"messages": [{"date": "2026-10-03", "text": "Got the promotion! Nothing else new on our end."}]},
                 calendar={"upcoming": []},
                 credit={"score": 805, "balances": []})),
        dict(id="cx-005", client=dict(name="Priya Shah", age=33, state="CA", occupation="UX designer",
             employer="Pixelwell", employment_status="employed", marital_status="married",
             annual_income=128000, monthly_expenses=7100, dependents=0, risk_score=4, horizon_years=32,
             targets={"equity": 0.78, "bond": 0.10, "cash": 0.12}, monthly_contribution=1200),
             values={"US_EQ": 140000, "INTL_EQ": 30000, "BOND": 19000, "CASH": 26000},
             events=[{"id": "e1", "type": "child", "date": "2027-03-15", "details": {"count": 2, "note": "twins expected"}}],
             connectors=dict(
                 payroll={"employer": "Pixelwell", "status": "active", "stubs": [{"date": "2026-10-31", "gross": 5330, "net": 3910}]},
                 bank={"as_of": AS_OF, "transactions": sorted(paychecks("2026-08-01", "2026-10-31", 3910, "PIXELWELL")
                       + [{"date": "2026-10-19", "description": "BABYLIST REGISTRY", "amount": -480, "category": "shopping"},
                          {"date": "2026-10-27", "description": "STANFORD HEALTH - OB CLINIC", "amount": -350, "category": "medical"}]
                       + base_spend(3400, 950), key=lambda t: t["date"])},
                 messages={"messages": [{"date": "2026-10-20", "text": "Big news: we're expecting twins in March!"}]},
                 calendar={"upcoming": [{"date": "2027-03-15", "title": "Due date (twins)"}]},
                 credit={"score": 752, "balances": [{"type": "card", "balance": 9400, "trend": "up 3 months in a row"}]})),
    ]


def main():
    market = json.loads(TEMPLATE_MARKET.read_text(encoding="utf-8"))
    if OUT.exists():
        shutil.rmtree(OUT)
    for c in clients():
        d = OUT / c["id"]
        (d / "connectors").mkdir(parents=True)
        client = {"client_id": c["id"], **c["client"], "goals": [{"type": "retirement", "target_year": 2026 + c["client"]["horizon_years"]}]}
        lo, hi = BANDS[client["risk_score"]]
        assert lo <= client["targets"]["equity"] <= hi, c["id"]
        (d / "client.json").write_text(json.dumps(client, indent=2))
        (d / "holdings.json").write_text(json.dumps(holdings(market, c["values"]), indent=2))
        (d / "market.json").write_text(json.dumps(market, indent=2))
        (d / "events.json").write_text(json.dumps({"events": c["events"]}, indent=2))
        for name, data in c["connectors"].items():
            (d / "connectors" / f"{name}.json").write_text(json.dumps(data, indent=2))
    print(f"wrote {len(clients())} connected clients to {OUT}")


if __name__ == "__main__":
    main()
