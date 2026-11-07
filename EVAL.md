# Ballast eval criteria

The checker is the one source of truth for "correct". It implements SPEC.md's policy rules with exact thresholds, so `checker/rules.py` can be coded straight from this file. Items marked **[decision]** fill a gap in SPEC.md; confirm them with the team.

## 1. Shared computation

Everything is scored on the holdings **after** trades. The checker and `tools/portfolio.py apply` must share one function.

- `post[s] = holdings[s].value + sum(buys of s) - sum(sells of s)`
- `T = sum(post)`. This is the same as the pre-trade total because trades net to zero.
- `w[class] = sum(post[s] for s where market[s].class == class) / T`, with class in {equity, bond, cash}.
- `w_sym[s] = post[s] / T`
- `cash_months = post["CASH"] / client.monthly_expenses`
- Tolerance: compare weights with ±0.005 (half a point) and dollars with ±$1, so rounding never fails a case. **[decision]**

## 2. Rules

A rule is **applicable** only when its trigger holds. Only applicable rules count toward the score.

| Rule | Sev | Applies when | Pass when |
| --- | --- | --- | --- |
| `valid_output` | Hard | always | See section 3. **If it fails, the case scores 0 and no other rule runs.** |
| `risk_band` | Hard | always | `lo ≤ w[equity] ≤ hi` for the client's `risk_score`: 1 = .10–.30, 2 = .30–.50, 3 = .50–.70, 4 = .70–.85, 5 = .85–1.00 |
| `emergency_fund` | Hard | always | `cash_months ≥ 3`, or `≥ 6` if events contain a `layoff`. Severance doesn't count; only `CASH` does. |
| `concentration` | Hard | holdings or trades include a `single_stock` symbol | every single stock has `w_sym ≤ 0.10` |
| `cited` | Hard | there is at least one trade | every trade's `reason_ref` is either `event:<id>` for an id in events.json (an event *type* such as `event:layoff` is also accepted **[decision]**) or `rule:<name>` with name in {rebalance, risk_band, emergency_fund, concentration, glidepath} |
| `no_churn` | Soft | no events, **and** every class is within ±0.05 of `client.targets` before trading, **and** the pre-trade holdings already pass risk_band, emergency_fund and concentration **[decision: without the last part, the rule would penalize a needed fix]** | `trades == []` and `no_action_reason` is a non-empty string |
| `event_child` | Soft | events contain `child` | `profile_updates.goals_add` has `{"type":"education"}` with `target_year` = event year + 18, ±1 **[decision]** |
| `event_marriage` | Soft | events contain `marriage` | `"joint_profile_review"` is in `flags` **and** `profile_updates.risk_score` is null |
| `event_job_change` | Soft | events contain `job_change` with `new_income > annual_income` | `profile_updates.monthly_contribution` is a number above the current value **and** `risk_score` is null |
| `glidepath` | Soft | `client.age ≥ 55` | `w[equity] ≤ (lo + hi) / 2`, the midpoint of the band **[decision]** |

The agent sees the citation vocabulary (`rule:<name>`) in its output format but never the thresholds. The vocabulary is part of the format, not the policy, so the agent can cite reasons without the rules leaking into the playbook.

## 3. `valid_output` checklist

The output fails if any of these fail:

1. `recommendation.json` exists and parses as a single JSON object.
2. It has exactly these keys: `client_id`, `target_allocation`, `trades`, `rationale`, `profile_updates`, `flags`, `no_action_reason`.
3. `client_id` equals the one in client.json.
4. `target_allocation` has keys equity, bond and cash, each in [0, 1], summing to 1 ± 0.01.
5. Each trade has `symbol` (from market.json), `action` (buy or sell), `amount_usd` (above 0) and `reason_ref` (a string).
6. Trades net to zero: `|sum(buys) - sum(sells)| ≤ $1`.
7. No sell is larger than the position: `post[s] ≥ -$1` for every symbol.
8. `profile_updates` has `goals_add` (a list of objects, each with `type`), `monthly_contribution` (a number or null) and `risk_score` (an integer 1–5 or null).
9. `flags` is a list of strings, and `rationale` is a list of `{ref, text}`.
10. If `trades == []`, `no_action_reason` is a non-empty string.
11. The agent finished within `max_turns` and 3 minutes (`run_case` gives `error: null`).

## 4. Case score and pass

- `score = passed applicable rules / applicable rules`
- `passed = all applicable hard rules pass and score ≥ 0.8`
- Violation detail strings must be specific and numeric, because Muse learns from them. For example: `"cash 2.1 months, needs 6 after layoff"` or `"ACME 12.9% of portfolio, max 10%"`.

Since 4 to 5 hard rules always apply, a case with one or two soft rules passes with one soft miss but fails with two. That's intended.

## 5. Set metrics and the ship gate (training mode)

For each candidate playbook, record per set: `mean_score`, `pass_rate`, violation counts by rule, tokens and seconds.

A candidate **ships** only if all three hold:

1. `test.mean_score ≥ parent.test.mean_score + 0.02` **[decision: the margin keeps LLM noise from shipping a no-op]**
2. `regression.pass_rate == 1.0`
3. The playbook is valid (section 7).

Otherwise it is rejected, and the reason is logged (`no_test_gain`, `regression_fail` or `invalid_playbook`). Muse never sees test or regression cases, only practice failures.

**Baseline sanity check:** v0 should land at a test pass_rate of about 0.4–0.6. If it is above 0.7, make the scenarios harder before training.

## 6. Drift indicator (drift mode only)

- `baseline` = the shipped playbook's verification `test.mean_score`.
- `trusted_rules` = the hard rules that had a 100% pass rate in the shipped playbook's verification run.
- `rolling` = the mean score over the last 10 runs.

| Level | Trigger |
| --- | --- |
| **Red** | Any run in the window has a hard violation of a rule in `trusted_rules`. |
| **Yellow** | Not red, and either `rolling < baseline - 0.05` or soft violations in the last 10 runs exceed those in the previous 10 by 3 or more. |
| **Green** | Otherwise. |

**[decision]** SPEC.md triggers red on "a case type the shipped playbook passed". But drift cases use *new* event types (inheritance, divorce, market drop) that were never in verification, so that wording would never fire on the demo cases. Keying red on rules instead fixes this: a market drop that pushes cash below 3 months breaks `emergency_fund`, which v-shipped always passed, so the indicator goes red. This matters for the demo.

**Realign verification:** a fix ships if it passes every captured drift case (all hard rules, score ≥ 0.8) **and** regression pass_rate is 1.0. Muse gets 3 attempts, then the system escalates.

## 7. Playbook validity (checked before any run)

1. Parses as YAML with keys `version`, `parent`, `model`, `prompt`, `skills`, `tools`, `max_turns` and `changelog`.
2. `version == parent + 1`, `model` and `tools` are unchanged from the parent, and `max_turns` is ≤ 20.
3. Each skill has a unique kebab-case `name`, a `description` and a `body`.
4. **At most 3 changes from the parent.** One change is any of: a skill added, a skill removed, a skill's description or body edited, the prompt edited, or max_turns changed. **[decision]**
5. There are no case or client ids (regex `\bc-\d{3}\b`) and no names from case files.
6. Policy restatement (optional, done by the Gemini reviewer): the playbook must not loosen or override a rule. For example, "cash can include severance" or "concentration limit is 20%" are rejected.

## 8. Hand-made checker tests (do these first, before any API keys)

For a layoff case like SPEC.md's example (risk 3, expenses 5,200, total 139k, ACME 12.9%):

| Recommendation | Expected |
| --- | --- |
| No trades | fails emergency_fund (cash 1.7 months, needs 6) and concentration; score low, passed = false |
| Sell 6k ACME and 16.2k US_EQ, buy 22.2k CASH, cited `event:e1` and `rule:concentration` | passes all; score 1.0 |
| Same trades but buys don't match sells | valid_output fails, score 0 |
| Same trades, one trade's reason_ref is `"because"` | fails cited (hard), passed = false |
