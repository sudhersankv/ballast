---
name: recommendation-format
description: Use before writing recommendation.json, to get the exact output format.
---

Write one JSON object to recommendation.json with exactly these keys:

```json
{
  "client_id": "<from client.json>",
  "target_allocation": {"equity": 0.60, "bond": 0.30, "cash": 0.10},
  "trades": [
    {"symbol": "US_EQ", "action": "sell", "amount_usd": 5000, "reason_ref": "rule:rebalance"},
    {"symbol": "BOND", "action": "buy", "amount_usd": 5000, "reason_ref": "rule:rebalance"}
  ],
  "rationale": [{"ref": "rule:rebalance", "text": "Equity is above target."}],
  "profile_updates": {"goals_add": [], "monthly_contribution": null, "risk_score": null},
  "flags": [],
  "no_action_reason": null
}
```

- `target_allocation` values sum to 1.0.
- `symbol` must be a symbol in market.json. `CASH` is tradable. `action` is `buy` or `sell`.
- `amount_usd` is positive. Total buys must equal total sells (trades net to zero).
- Never sell more than the current value of a position.
- `reason_ref` is `event:<event id>` for an event in events.json, or `rule:<name>` where
  name is one of: rebalance, risk_band, emergency_fund, concentration, glidepath.
- Each `reason_ref` used in trades should have a matching `rationale` entry.
- `profile_updates`: `null` means no change. `goals_add` takes objects like
  `{"type": "education", "target_year": 2044}`.
- `flags`: strings for items a human should review.
- If you make no trades, `trades` is `[]` and `no_action_reason` is a short string.
