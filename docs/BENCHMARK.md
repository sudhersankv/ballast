# ballast. benchmark: one framework, several models

**What this shows.** ballast. is model-agnostic: the same harness, the same gates and the same generic starting skill file are applied to each model, and we measure whether the framework (failure → root cause → new skill → gated ship) improves that model and whether the gates catch that model's bad changes. It is not a contest between models; differences between stacks are reported so you can see where each one adapts or struggles. Honest negatives are kept.

Same tests, same gates, same generic starting skill file, Gemini as the only reviewer. Unseen test = 20 clients × 3 runs each; a client passes if it passes in the majority of runs. Gains are paired per client with a bootstrap 90% confidence interval. Every run is also backtested over 12 real held-out months.

## Fairness controls

Every stack ran under identical conditions; only the model behind the agent and the mentor changed:
- **Harness:** the same Pi coding-agent setup (tools `read`, `bash`, `write`; same sandbox user; same turn and time limits).
- **Prompts:** the same generic starting playbook (`agent/playbooks/v000-generic.yaml`), the same task message, the same mentor prompt (`runtime/prompts/mentor.md`).
- **Data and seeds:** the same cases, the same held-out market months, the same journeys, the same shuffling seed for the control arm.
- **Gates:** the same paired gate (mean gain ≥ 0.02, bootstrap 90% CI above zero, no lost test client, regression flips re-checked, backtest not worse) and the same validator.
- **Repeats:** the same number of runs per test client.
- **Reviewer:** Gemini is the only compliance reviewer for every stack.

SubQ Preview is a long-context model. The agent role (short cases, many tool turns) does not play to that strength; the drift-analyst role, which reads every run in one call, is the better test of it. Its analyst run is reported under each stack's drift section.

| | Muse stack | SubQ stack |
|---|---|---|
| Agent / mentor | meta/muse-spark-1.3 / muse | subq/subq-preview / subq |
| Unseen test mean score, v0 → final | 0.818 → 0.923 | 0.812 → 0.912 |
| Paired gain (90% CI) | +0.105 (+0.053 … +0.160) | +0.101 (+0.062 … +0.140) |
| Clients passing, v0 → final | 65% → 95% | 65% → 85% |
| Versions shipped / tried | 1 / 3 | 1 / 3 |
| Control arm gain (shuffled failures) | +0.003 | +0.069 |
| Backtest clients with breach, v0 → final | 3 → 0 | 4 → 0 |
| Backtest clients forced to sell, v0 → final | 2 → 0 | 3 → 0 |
| Drift set: pass rate / level | 100% / green | 70% / green |
| Lessons in final playbook | 5 | 5 |
| Agent mean seconds / turns | 59.7 / 7.3 | 28.6 / 7.0 |
| Agent error rate (final test) | 2% | 0% |
| Mentor calls / tokens out | 4 / 35,197 | 9 / 35,017 |
| Wall clock | 82.9 min | 32.1 min |

### Journeys, holdout quarters (generic agent → client's own agent)

| Client | Muse | SubQ |
|---|---|---|
| Priya Okafor | 3/5 → 3/5 (1 lessons) | 3/5 → 3/5 (1 lessons) |
| Marcus Delgado | 5/5 → 5/5 (1 lessons) | 5/5 → 5/5 (0 lessons) |
| Elena Varga | 5/5 → 5/5 (1 lessons) | 5/5 → 5/5 (1 lessons) |
| Kenji Lundgren | 5/5 → 5/5 (0 lessons) | 4/5 → 5/5 (3 lessons) |
| Hannah Brennan | 3/5 → 3/5 (2 lessons) | 4/5 → 3/5 (1 lessons) |
| Rafael Sandoval | 4/5 → 5/5 (1 lessons) | 4/5 → 5/5 (1 lessons) |

## Headline metrics per stack

| Metric | Muse | SubQ |
|---|---|---|
| Run pass rate on unseen test, v0 → final | 63% → 93% | 65% → 82% |
| Hard-rule violation rate, v0 → final | 25% → 7% | 23% → 13% |
| Consistency: cases identical across repeats, v0 → final | 75% → 95% | 70% → 80% |
| Mean per-case score std-dev, v0 → final | 0.029 → 0.027 | 0.064 → 0.028 |
| Latency per case p50 / p95 (s) | 50.4 / 114.6 | 29.7 / 47.4 |
| Tokens per passing case (final) | 28,281 | 15,997 |
| Cost per passing recommendation (final) | $0.0572 | – |
| Agent tokens in / out (whole run) | 9,269,659 / 3,207,600 | 3,761,447 / 1,626,660 |
| Agent cost (whole run) | $25.2194 | – |
| Mentor tokens in / out, cost | 9,149 / 35,197, $0.1610 | 18,515 / 35,017, – |
| Snap tokens, cost | not used | 17,494, $0.0007 |
| Mentor valid on first try | 100% of 10 | 18% of 11 |
| Fleet versions shipped / tried | 1/3 | 1/3 |
| Mean gain per shipped version vs own control arm | +0.105 vs +0.003 | +0.101 vs +0.069 |
| Regressions blocked by gates / shipped | 1 / 0 | 2 / 0 |
| Journeys improved / same / worse (holdout mean) | 1 / 4 / 1 | 2 / 2 / 2 |
| Drift analyst: runs read, tokens, seconds | 70, 27739, 26.6 (muse-spark-1.3) | 70, 45450, 9.0 (subq-preview) |

Pricing: Muse at $1.25 / 1M input and $4.25 / 1M output (published Spark pricing; Wonder assumed the same). SubQ Preview and Gemini 3.8 Flash prices were not published to us, so their $ cells are blank and tokens are reported instead. Snap at $0.04 / 1M input, output free. Tokenizers differ between providers and reasoning tokens are included in output counts, so tokens are comparable within a stack, not exactly across stacks.

## Same client, both stacks

**`c-028`** — Desmond Iyer, 38, risk 4, expenses $11,150/mo | marriage {"spouse_name": "Nadia Yilmaz", "spouse_age": 40, "spouse_annual_income": 125000, "spouse_has_separate_accounts": true}
- Muse v0: score 0.75 — no trades (Portfolio near targets; no trades needed.) — `event_marriage`: missing joint_profile_review flag
- Muse final: score 1.00 — no trades (Allocation within tolerance and cash reserve exceeds 3-month target; flagging joint review after marriage.) — all rules passed
- SubQ v0: score 0.75 — no trades (Allocation is within 1.6 points of every target and no concentration or liquidity rule is breached; the only change is a life event that needs a human review, not a trade.) — `event_marriage`: missing joint_profile_review flag
- SubQ final: score 0.75 — no trades (Allocation is within rebalancing tolerance of targets and the marriage event requires no reallocation; only a joint profile review is needed.) — `event_marriage`: missing joint_profile_review flag

**`c-032`** — Leila Patel, 37, risk 3, expenses $4,800/mo | layoff {"severance": 12400, "severance_weeks": 11, "tenure_years": 11, "employer": "Copperline Mfg", "last_day": "2026-08-16", "cobra_monthly_premium": 2130}, child {"child_name": "Leo", "birth_date": "2026-08-17", "adoption": false}
- Muse v0: score 0.60 — sell US_EQ $3,293 [rule:emergency_fund]; sell BOND $4,575 [rule:emergency_fund]; buy CASH $7,867 [rule:emergency_fund] — `emergency_fund`: cash 4.2 months, needs 6 after layoff; `event_child`: education goal target_year none, expected 2044 (birth year + 18)
- Muse final: score 1.00 — sell BOND $16,585 [rule:emergency_fund]; buy CASH $16,585 [rule:emergency_fund] — all rules passed
- SubQ v0: score 0.60 — sell BOND $3,000 [rule:emergency_fund]; buy CASH $3,000 [rule:emergency_fund] — `emergency_fund`: cash 3.2 months, needs 6 after layoff; `event_child`: education goal target_year none, expected 2044 (birth year + 18)
- SubQ final: score 0.80 — sell US_EQ $8,292 [rule:emergency_fund]; sell BOND $8,292 [rule:emergency_fund]; buy CASH $16,584 [rule:emergency_fund] — `risk_band`: equity 46.3% outside 50.0%-70.0% for risk 3

**`c-021`** — Abigail Achebe, 36, risk 4, expenses $6,200/mo | marriage {"spouse_name": "Marcus Okafor", "spouse_age": 40, "spouse_annual_income": 57000, "spouse_has_separate_accounts": true}, job_change {"new_income": 101000, "previous_income": 82000, "new_employer": "Quillon Software", "start_date": "2026-09-21", "employer_401k_match_pct": 6}
- Muse v0: score 0.80 — no trades (Allocation within tolerance of targets with no concentration; no trades needed.) — `event_marriage`: missing joint_profile_review flag
- Muse final: score 1.00 — sell US_EQ $1,304 [rule:rebalance]; buy BOND $347 [rule:rebalance]; buy CASH $957 [rule:rebalance] — all rules passed
- SubQ v0: score 0.60 — no trades (Allocation is within tolerance of the 80/6/14 targets (80.8/5.8/13.4), so no trades are needed.) — `event_marriage`: missing joint_profile_review flag; `event_job_change`: monthly_contribution None, needs > 900 after raise
- SubQ final: score 0.80 — no trades (Allocation is within 0.8 points of targets, no concentration issue, and cash covers 3.5 months — no trade is warranted; the events change contributions and profile items only.) — `event_marriage`: missing joint_profile_review flag

**`c-023`** — Lucia Whitaker, 35, risk 4, expenses $6,800/mo | job_change {"new_income": 128500, "previous_income": 103000, "new_employer": "Mesa Ridge Schools", "start_date": "2026-09-11", "employer_401k_match_pct": 6}, child {"child_name": "Iris", "birth_date": "2026-09-23", "adoption": false}
- Muse v0: score 0.67 — sell US_EQ $5,216 [rule:rebalance]; buy BOND $5,216 [rule:rebalance] — `event_child`: education goal target_year none, expected 2044 (birth year + 18); `event_job_change`: monthly_contribution None, needs > 1,350 after raise
- Muse final: score 1.00 — sell US_EQ $3,157 [rule:rebalance]; sell CASH $2,059 [rule:rebalance]; buy BOND $5,216 [rule:rebalance] — all rules passed
- SubQ v0: score 0.83 — sell US_EQ $3,150 [rule:rebalance]; buy BOND $3,150 [rule:rebalance] — `event_child`: education goal target_year none, expected 2044 (birth year + 18)
- SubQ final: score 1.00 — sell US_EQ $3,157 [rule:rebalance]; buy BOND $3,157 [rule:rebalance] — all rules passed


## Muse (Spark 1.3 agent, Wonder 1.0 mentor)

Started from the generic v0 and ended at **v2**. Unseen test (20 clients × 3 runs):

| | v0 (generic) | final | change |
|---|---|---|---|
| Mean score | 0.818 | 0.923 | +0.105 (90% CI +0.053 … +0.160) |
| Clients passing (majority of runs) | 65% | 95% | |
| Single-run pass rate | 63% | 93% | |
| Backtest: clients with emergency-fund breach | 3 | 0 | |
| Backtest: clients forced to sell | 2 | 0 | |
| Backtest: forced sales $ (all runs) | $62,118 | $0 | |
| Backtest: mean 12-month return | 0.071 | 0.074 | |
| Agent errors | 0/60 | 1/60 | |
| Mean seconds / turns per case | 42.8 / 6.4 | 59.7 / 7.3 | |

**Rule failure rate on unseen clients** (failed / applicable runs):

| Rule | v0 | final |
|---|---|---|
| `cited` | 0% | 0% |
| `concentration` | 0% | 0% |
| `emergency_fund` | 18% | 0% |
| `event_child` | 92% | 0% |
| `event_job_change` | 92% | 0% |
| `event_marriage` | 100% | 0% |
| `glidepath` | 25% | 42% |
| `no_churn` | 83% | 100% |
| `risk_band` | 7% | 5% |
| `valid_output` | 0% | 2% |

**Other sets at v0:** practice 55% (mean 0.822), regression 60% (mean 0.847), drift 70% (mean 0.885)

### Every generation and why it shipped or not

- **v2** SHIPPED — test pass 0.65->0.95, mean 0.818->0.923, paired gain +0.105 (90% CI +0.053..+0.160); lost none; regression flips ['c-042', 'c-048'] confirmed none; backtest breaches 3->0, forced sales 2->0; Gemini approve
  - Change: Added emergency-fund-first and life-event-profile-updates skills and ordered them in the prompt, so cash is funded to target before other trades and every life event gets its profile update or flag.
  - Lesson: "After a layoff, I build six months of cash before rebalancing or diversifying anything else." — root cause: The agent left cash below the post-layoff target by making no trades, raising too little cash, or using sale proceeds for other assets. — triggered by: layoff — rule `emergency_fund`
  - Lesson: "When cash covers only a short period of expenses, I raise cash to at least three months before rebalancing." — root cause: The agent rebalanced and even sold cash without first checking how many months of expenses the cash covered. — triggered by: low cash — rule `emergency_fund`
  - Lesson: "When a child is born, I add an education goal aimed at the year the child turns eighteen." — root cause: The agent handled portfolio trades but left the education goal without a target year for the new child. — triggered by: child — rule `event_child`
  - Lesson: "After a pay rise at a new job, I raise the monthly contribution in line with the increase in pay." — root cause: The agent left monthly_contribution unchanged after an income increase from a job change. — triggered by: job_change — rule `event_job_change`
  - Lesson: "When a client marries, I flag the profile for a joint review even if accounts stay separate." — root cause: The agent added no profile flag after a marriage event. — triggered by: marriage — rule `event_marriage`
  - Rule failures on unseen clients, before → after: `valid_output` 0/60 → 1/60, `risk_band` 4/60 → 3/59, `emergency_fund` 11/60 → 0/59, `no_churn` 10/12 → 12/12, `glidepath` 3/12 → 5/12, `event_child` 11/12 → 0/12, `event_job_change` 11/12 → 0/12, `event_marriage` 6/6 → 0/6
- **v3** REJECTED — test pass 0.95->0.90, mean 0.923->0.930, paired gain +0.007 (90% CI -0.006..+0.027); lost ['c-024']; regression flips none confirmed none; backtest breaches 0->0, forced sales 0->0; Gemini approve | FAILED: gain>=0.02, ci_low>0, no_lost_test_cases
  - Change: Added risk-band-guard, made emergency-fund-first fund cash from non-equity first, and ordered the guard in the prompt, so cash raises no longer push equity outside the risk band.
  - Lesson: "When I raise cash for an emergency fund, I fund it from non-equity holdings first and recheck the equity share so cash trades do not push equity below the level for my risk profile." — root cause: The agent sold equity holdings to buy cash without checking the post-trade equity share, pushing equity below the minimum for the client risk level. — triggered by: low cash — rule `risk_band`
- **v4** REJECTED — test pass 0.95->1.00, mean 0.923->0.927, paired gain +0.004 (90% CI -0.022..+0.038); lost none; regression flips none confirmed none; backtest breaches 0->0, forced sales 0->0; Gemini approve | FAILED: gain>=0.02, ci_low>0
  - Change: Sharpened emergency-fund-first to fund cash from non-equity holdings first and verify post-trade equity share, so meeting the cash target does not push equity outside its risk band.
  - Lesson: "When I raise cash for the emergency fund, I sell non-equity holdings first so the equity share stays in line." — root cause: The agent funded cash by selling equity holdings, pushing the post-trade equity share below the range for the client risk level. — triggered by: low cash — rule `risk_band`

### Control arm: is the mentor's change driven by the real failures?

The mentor was given the same number of failures with the violations and life events **shuffled across clients**. Its candidate v1 scored a paired gain of **+0.003** (90% CI -0.028 … +0.034) on unseen clients, versus **+0.105** for the real training run. Changelog: Added emergency-fund-first, risk-band-check, and no-churn-tolerance skills to fix underfunded cash, out-of-band equity, and unnecessary trading.

- Control lesson (from shuffled evidence): "I check how many months of expenses my cash covers and fund it fully before doing anything else, even when nothing has happened."
- Control lesson (from shuffled evidence): "I check my equity share against the band for my current risk score and move it inside the band when it falls outside."
- Control lesson (from shuffled evidence): "I leave a portfolio alone when it is already close to target unless a hard rule or a real event requires a trade."

### Specific failures of the generic agent (v0, unseen clients)

- `c-032` — Leila Patel, 37, risk 3, expenses $4,800/mo | layoff {"severance": 12400, "severance_weeks": 11, "tenure_years": 11, "employer": "Copperline Mfg", "last_day": "2026-08-16", "cobra_monthly_premium": 2130}, child {"child_name": "Leo", "birth_date": "2026-08-17", "adoption": false}  
  Agent did: sell US_EQ $3,293 [rule:emergency_fund]; sell BOND $4,575 [rule:emergency_fund]; buy CASH $7,867 [rule:emergency_fund]  
  Score 0.60. **emergency_fund** (hard): cash 4.2 months, needs 6 after layoff; **event_child** (soft): education goal target_year none, expected 2044 (birth year + 18). Backtest: min cash 0.0 months, forced sale $8,500, breach True.
- `c-023` — Lucia Whitaker, 35, risk 4, expenses $6,800/mo | job_change {"new_income": 128500, "previous_income": 103000, "new_employer": "Mesa Ridge Schools", "start_date": "2026-09-11", "employer_401k_match_pct": 6}, child {"child_name": "Iris", "birth_date": "2026-09-23", "adoption": false}  
  Agent did: sell US_EQ $5,216 [rule:rebalance]; buy BOND $5,216 [rule:rebalance]  
  Score 0.67. **event_child** (soft): education goal target_year none, expected 2044 (birth year + 18); **event_job_change** (soft): monthly_contribution None, needs > 1,350 after raise. Backtest: min cash 4.5 months, forced sale $0, breach False.
- `c-022` — Lucia Beaumont, 35, risk 2, expenses $6,150/mo | no events  
  Agent did: sell BOND $3,710 [rule:rebalance]; buy US_EQ $2,317 [rule:rebalance]; buy INTL_EQ $665 [rule:rebalance]; buy CASH $728 [rule:rebalance]  
  Score 0.75. **emergency_fund** (hard): cash 2.1 months, needs 3. Backtest: min cash 2.1 months, forced sale $0, breach True.
- `c-028` — Desmond Iyer, 38, risk 4, expenses $11,150/mo | marriage {"spouse_name": "Nadia Yilmaz", "spouse_age": 40, "spouse_annual_income": 125000, "spouse_has_separate_accounts": true}  
  Agent did: no trades (Portfolio near targets; no trades needed.)  
  Score 0.75. **event_marriage** (soft): missing joint_profile_review flag. Backtest: min cash 4.1 months, forced sale $0, breach False.
- `c-024` — Diego Kowalski, 54, risk 3, expenses $8,700/mo | layoff {"severance": 30500, "severance_weeks": 10, "tenure_years": 10, "employer": "Helixar Therapeutics (HLXR)", "last_day": "2026-09-12", "cobra_monthly_premium": 760}  
  Agent did: sell HLXR $77,000 [rule:concentration]; sell BOND $11,866 [rule:rebalance]; buy CASH $34,744 [rule:emergency_fund]; buy US_EQ $37,622 [rule:rebalance]; buy INTL_EQ $16,500 [rule:rebalance]  
  Score 0.80. **emergency_fund** (hard): cash 5.9 months, needs 6 after layoff. Backtest: min cash 0.0 months, forced sale $0, breach False.
- `c-036` — Hector Oyelaran, 45, risk 4, expenses $9,100/mo | layoff {"severance": 14600, "severance_weeks": 5, "tenure_years": 5, "employer": "Kestrel Freight (KSTL)", "last_day": "2026-10-28", "cobra_monthly_premium": 760}  
  Agent did: sell KSTL $32,500 [rule:concentration]; buy CASH $32,500 [rule:emergency_fund]  
  Score 0.80. **risk_band** (hard): equity 65.9% outside 70.0%-85.0% for risk 4. Backtest: min cash 0.5 months, forced sale $0, breach False.

### Failures still left at v2

- `c-036` — Hector Oyelaran, 45, risk 4, expenses $9,100/mo | layoff {"severance": 14600, "severance_weeks": 5, "tenure_years": 5, "employer": "Kestrel Freight (KSTL)", "last_day": "2026-10-28", "cobra_monthly_premium": 760}  
  Agent did: sell KSTL $28,392 [rule:emergency_fund]; buy CASH $28,392 [rule:emergency_fund]; sell KSTL $15,000 [rule:concentration]; buy US_EQ $15,000 [rule:concentration]  
  Score 0.80. **risk_band** (hard): equity 67.9% outside 70.0%-85.0% for risk 4. Backtest: min cash 0.0 months, forced sale $0, breach False.

### Drift: final version on new conditions (inheritance, divorce, real crashes)

Drift level **green** — no trusted rule broken. Passed 100% of drift cases.


Drift analyst (muse, 70 runs read): v2 shows 3 repeat failure clusters across 20 of 70 runs, all in test not drift. No-event small-drift churn, age-based glidepath excess, and layoff cash funding that breaks the risk band explain all systematic drift; inheritance, market-drop and divorce cases pass 10/10.
- no life events and portfolio within 5pts of target (c-025, c-031, c-037, c-040) → `no_churn` fails 100% (12 runs). 3 trades on a portfolio within 5 points of target with no events
- age >=55 (c-029 age 55, c-039 age 63) → `glidepath` fails 83% (6 runs). age 55: equity 45.0%, needs <= 40.0% (low half of band)
- layoff + 25.4% single-stock concentration with 6-month cash need (c-036, risk 4) → `risk_band` fails 100% (3 runs). equity 67.9% outside 70.0%-85.0% for risk 4

### Client journeys (per-client learning, proven on the client's own later quarters)

| Client | Regime | Lessons | Holdout pass: generic → own agent | Mean | Backtest breaches |
|---|---|---|---|---|---|
| Priya Okafor (j-001) | Credit crisis: steady market, then a 50% equity cr | 1 | 3/5 → 3/5 | 0.92 → 0.92 | 3 → 3 |
| Marcus Delgado (j-002) | Pandemic shock: a fast 20%+ crash, then a strong r | 1 | 5/5 → 5/5 | 0.97 → 0.97 | 0 → 0 |
| Elena Varga (j-003) | Rate shock: stocks and bonds fall together, then a | 1 | 5/5 → 5/5 | 0.88 → 0.92 | 0 → 0 |
| Kenji Lundgren (j-004) | Dot-com bust: a slow multi-year bear market, with  | 0 | 5/5 → 5/5 | 0.93 → 0.93 | 2 → 2 |
| Hannah Brennan (j-005) | Calm bull market with low volatility (a small corr | 2 | 3/5 → 3/5 | 0.88 → 0.88 | 1 → 1 |
| Rafael Sandoval (j-006) | Mixed: a 2015-16 correction, then a steady rally | 1 | 4/5 → 5/5 | 0.95 → 0.93 | 0 → 0 |

Lessons learned inside journeys:
- j-005 at t02 (t02 score 0.75->1.00; earlier checkpoints held): "When a client gets married, I flag the case for a joint profile review even if I recommend no trades." — root cause: The agent ignored the marriage event and added no human-review flag when it decided on no trades. — triggered by marriage
- j-006 at t02 (t02 score 0.80->1.00; earlier checkpoints held): "After a layoff, I build six months of cash before rebalancing anything else." — root cause: The agent rebalanced into equities without first checking whether cash met the post-layoff emergency fund need. — triggered by layoff
- j-003 at t03 (t03 score 0.75->1.00; earlier checkpoints held): "After a job change that raises my income, I increase my monthly contribution in line with the raise instead of leaving it unchanged." — root cause: The agent ignored the income increase in the job_change event and left monthly_contribution null while making no trades. — triggered by job_change
- j-001 at t04 (t04 score 0.80->1.00; earlier checkpoints held): "Before rebalancing or reducing a concentrated holding, I check my cash in months of expenses and send sale proceeds to cash first if it is below the required emergency fund." — root cause: The agent rebalanced sale proceeds into equities without checking post-trade cash coverage against the emergency fund requirement. — triggered by Cash reserves below the required emergency fund
- j-005 at t05 (t05 score 0.75->1.00; earlier checkpoints held): "When I get a raise in a job change, I increase my monthly contribution in proportion to the new income instead of leaving it unchanged." — root cause: The agent left monthly_contribution as null and took no action after a job change with a raise. — triggered by job_change
- j-002 at t05 (t05 score 0.80->1.00; earlier checkpoints held): "Before finalizing any trades after a layoff or market drop, I recompute my post-trade equity share and adjust the funding mix until it stays inside my client's risk band." — root cause: The agent funded cash from a concentrated equity sale without recomputing the resulting equity share, pushing equity below the allowed band. — triggered by layoff

Journey changes rejected by the gate:
- j-005 at t05: compliance_block: The candidate hard-codes a $600 monthly contribution threshold derived from a specific client case into general guidance for all job changes.

### Cost and speed

- Agent: 514 runs, 9,269,659 tokens in, 3,207,600 out, mean 54.3 s/case, errors 4 (1%)
- Mentor: 4 calls, 9,149 tokens in, 35,197 out, 228.4 s total
- Wall clock: 82.9 min

## SubQ (Preview agent + mentor, Snap gates)

Started from the generic v0 and ended at **v3**. Unseen test (20 clients × 3 runs):

| | v0 (generic) | final | change |
|---|---|---|---|
| Mean score | 0.812 | 0.912 | +0.101 (90% CI +0.062 … +0.140) |
| Clients passing (majority of runs) | 65% | 85% | |
| Single-run pass rate | 65% | 82% | |
| Backtest: clients with emergency-fund breach | 4 | 0 | |
| Backtest: clients forced to sell | 3 | 0 | |
| Backtest: forced sales $ (all runs) | $143,894 | $0 | |
| Backtest: mean 12-month return | 0.075 | 0.075 | |
| Agent errors | 0/60 | 0/60 | |
| Mean seconds / turns per case | 19.2 / 6.1 | 28.6 / 7.0 | |

**Rule failure rate on unseen clients** (failed / applicable runs):

| Rule | v0 | final |
|---|---|---|
| `cited` | 0% | 0% |
| `concentration` | 0% | 0% |
| `emergency_fund` | 20% | 2% |
| `event_child` | 92% | 0% |
| `event_job_change` | 83% | 8% |
| `event_marriage` | 100% | 100% |
| `glidepath` | 46% | 42% |
| `no_churn` | 46% | 58% |
| `risk_band` | 3% | 12% |
| `valid_output` | 2% | 0% |

**Other sets at v0:** practice 65% (mean 0.831), regression 60% (mean 0.857), drift 60% (mean 0.877)

### Every generation and why it shipped or not

- **v2** REJECTED — invalid_playbook
- **v3** SHIPPED — test pass 0.65->0.85, mean 0.812->0.912, paired gain +0.101 (90% CI +0.062..+0.140); lost none; regression flips none confirmed none; backtest breaches 4->0, forced sales 3->0; Gemini approve
  - Change: Added policy-constraint-check and life-event-profile-updates skills and required them in the prompt; fixes post-trade risk-band/emergency-fund breaches and missed life-event profile updates.
  - Lesson: "Before I place any trade, I check that the post-trade allocation still satisfies the client's risk band." — root cause: I sold equity into cash without checking the resulting equity weight against the risk band. — triggered by: layoff or any large cash-raising trade — rule `risk_band`
  - Lesson: "Before discretionary rebalancing, I fund the emergency reserve to the policy minimum for the client's situation." — root cause: I rebalanced or raised cash without first meeting the emergency-fund requirement. — triggered by: layoff, job loss, or low cash reserve — rule `emergency_fund`
  - Lesson: "When a child event appears, I add an education goal with a target year based on the birth date." — root cause: I ignored the child event's profile update. — triggered by: child birth or adoption — rule `event_child`
  - Lesson: "When income rises at a job change, I update the monthly contribution instead of leaving it null." — root cause: I ignored the job-change income increase and left monthly_contribution unchanged. — triggered by: job_change with higher income — rule `event_job_change`
  - Lesson: "When a client marries, I add a joint_profile_review flag so a human reviews accounts and beneficiaries." — root cause: I treated marriage as no action and omitted the joint-profile review flag. — triggered by: marriage — rule `event_marriage`
  - Rule failures on unseen clients, before → after: `valid_output` 1/60 → 0/60, `risk_band` 2/59 → 7/60, `emergency_fund` 12/59 → 1/60, `event_job_change` 10/12 → 1/12, `event_child` 11/12 → 0/12, `no_churn` 5/11 → 7/12, `glidepath` 5/11 → 5/12
- **v4** REJECTED — test pass 0.85->0.90, mean 0.912->0.928, paired gain +0.016 (90% CI -0.006..+0.039); lost ['c-038']; regression flips none confirmed none; backtest breaches 0->1, forced sales 0->1; Gemini approve | FAILED: gain>=0.02, ci_low>0, no_lost_test_cases, backtest_not_worse
  - Change: Sharpened policy-constraint-check to size cash-raising sales against the risk band, protect the cash reserve on every trade, and forbid no-trade output when a hard rule is already violated; made life-event-profile-updates require at least one flag or update per event so marriage always yields joint_profile_review.
  - Lesson: "After a layoff, I raise cash only up to the point where equity stays inside the risk band, and I flag any reserve shortfall instead of overselling equity." — root cause: I sold equity down to 30% equity for a risk-3 client while raising emergency cash. — triggered by: layoff with a short cash reserve — rule `risk_band`
  - Lesson: "Before any rebalance, I check that the trade leaves the required months of cash untouched." — root cause: I rebalanced into bonds and left 1.5 months of cash when 3 were required. — triggered by: rebalance while the cash reserve is near the minimum — rule `emergency_fund`
  - Lesson: "After a layoff with a short reserve, I never return no trades — I fund cash within the risk band or flag the gap." — root cause: I returned no trades while cash was 2.5 months against a 6-month post-layoff requirement. — triggered by: layoff with a short cash reserve — rule `emergency_fund`
  - Lesson: "When I sell a concentrated position, I recompute total equity weight after redeploying the proceeds." — root cause: I moved concentration proceeds into cash and left equity at 65.5% for a risk-4 client. — triggered by: concentration sale during a layoff — rule `risk_band`
  - Lesson: "Every life event produces at least one flag or profile update, even when no numbers change." — root cause: A marriage event produced no joint_profile_review flag. — triggered by: marriage — rule `event_marriage`

### Control arm: is the mentor's change driven by the real failures?

The mentor was given the same number of failures with the violations and life events **shuffled across clients**. Its candidate v1 scored a paired gain of **+0.069** (90% CI -0.002 … +0.134) on unseen clients, versus **+0.101** for the real training run. Changelog: Added three general habits: fund the cash reserve first, avoid churn inside the rebalance band, and update goals/contributions after life events.

- Control lesson (from shuffled evidence): "Before deciding no action or rebalancing, I check the client's cash reserve against the policy minimum and fund it first from overweight assets."
- Control lesson (from shuffled evidence): "When the portfolio is inside the policy rebalance band, I do not trade unless an event creates a real cash or risk need."
- Control lesson (from shuffled evidence): "After a birth or adoption, I add an education goal for birth year plus 18 and refresh monthly contribution when income changes."
- Control lesson (from shuffled evidence): "After a job change or raise, I update monthly_contribution to the policy minimum for the new income before finishing."

### Specific failures of the generic agent (v0, unseen clients)

- `c-025` — Victor Achebe, 66, risk 3, expenses $5,200/mo | no events  
  Agent did: sell BOND $10,768 [rule:emergency_fund]; buy CASH $10,768 [rule:emergency_fund]  
  Score 0.00. **valid_output** (hard): profile_updates.goals_add must be a list of objects with type. Backtest: min cash 6.0 months, forced sale $0, breach False.
- `c-021` — Abigail Achebe, 36, risk 4, expenses $6,200/mo | marriage {"spouse_name": "Marcus Okafor", "spouse_age": 40, "spouse_annual_income": 57000, "spouse_has_separate_accounts": true}, job_change {"new_income": 101000, "previous_income": 82000, "new_employer": "Quillon Software", "start_date": "2026-09-21", "employer_401k_match_pct": 6}  
  Agent did: no trades (Allocation is within tolerance of the 80/6/14 targets (80.8/5.8/13.4), so no trades are needed.)  
  Score 0.60. **event_marriage** (soft): missing joint_profile_review flag; **event_job_change** (soft): monthly_contribution None, needs > 900 after raise. Backtest: min cash 3.5 months, forced sale $0, breach False.
- `c-032` — Leila Patel, 37, risk 3, expenses $4,800/mo | layoff {"severance": 12400, "severance_weeks": 11, "tenure_years": 11, "employer": "Copperline Mfg", "last_day": "2026-08-16", "cobra_monthly_premium": 2130}, child {"child_name": "Leo", "birth_date": "2026-08-17", "adoption": false}  
  Agent did: sell BOND $3,000 [rule:emergency_fund]; buy CASH $3,000 [rule:emergency_fund]  
  Score 0.60. **emergency_fund** (hard): cash 3.2 months, needs 6 after layoff; **event_child** (soft): education goal target_year none, expected 2044 (birth year + 18). Backtest: min cash 0.0 months, forced sale $13,452, breach True.
- `c-022` — Lucia Beaumont, 35, risk 2, expenses $6,150/mo | no events  
  Agent did: sell BOND $3,710 [rule:rebalance]; buy US_EQ $2,320 [rule:rebalance]; buy INTL_EQ $660 [rule:rebalance]; buy CASH $730 [rule:rebalance]  
  Score 0.75. **emergency_fund** (hard): cash 2.1 months, needs 3. Backtest: min cash 2.1 months, forced sale $0, breach True.
- `c-028` — Desmond Iyer, 38, risk 4, expenses $11,150/mo | marriage {"spouse_name": "Nadia Yilmaz", "spouse_age": 40, "spouse_annual_income": 125000, "spouse_has_separate_accounts": true}  
  Agent did: no trades (Allocation is within 1.6 points of every target and no concentration or liquidity rule is breached; the only change is a life event that needs a human review, not a trade.)  
  Score 0.75. **event_marriage** (soft): missing joint_profile_review flag. Backtest: min cash 4.1 months, forced sale $0, breach False.
- `c-024` — Diego Kowalski, 54, risk 3, expenses $8,700/mo | layoff {"severance": 30500, "severance_weeks": 10, "tenure_years": 10, "employer": "Helixar Therapeutics (HLXR)", "last_day": "2026-09-12", "cobra_monthly_premium": 760}  
  Agent did: sell HLXR $61,250 [rule:concentration]; buy US_EQ $37,940 [rule:concentration]; buy INTL_EQ $16,530 [rule:concentration]; buy BOND $4,235 [rule:rebalance]; buy CASH $2,545 [rule:emergency_fund]  
  Score 0.80. **emergency_fund** (hard): cash 2.2 months, needs 6 after layoff. Backtest: min cash 0.0 months, forced sale $32,746, breach True.

### Failures still left at v3

- `c-028` — Desmond Iyer, 38, risk 4, expenses $11,150/mo | marriage {"spouse_name": "Nadia Yilmaz", "spouse_age": 40, "spouse_annual_income": 125000, "spouse_has_separate_accounts": true}  
  Agent did: no trades (Allocation is within rebalancing tolerance of targets and the marriage event requires no reallocation; only a joint profile review is needed.)  
  Score 0.75. **event_marriage** (soft): missing joint_profile_review flag. Backtest: min cash 4.1 months, forced sale $0, breach False.
- `c-032` — Leila Patel, 37, risk 3, expenses $4,800/mo | layoff {"severance": 12400, "severance_weeks": 11, "tenure_years": 11, "employer": "Copperline Mfg", "last_day": "2026-08-16", "cobra_monthly_premium": 2130}, child {"child_name": "Leo", "birth_date": "2026-08-17", "adoption": false}  
  Agent did: sell US_EQ $8,292 [rule:emergency_fund]; sell BOND $8,292 [rule:emergency_fund]; buy CASH $16,584 [rule:emergency_fund]  
  Score 0.80. **risk_band** (hard): equity 46.3% outside 50.0%-70.0% for risk 3. Backtest: min cash 0.1 months, forced sale $0, breach False.
- `c-036` — Hector Oyelaran, 45, risk 4, expenses $9,100/mo | layoff {"severance": 14600, "severance_weeks": 5, "tenure_years": 5, "employer": "Kestrel Freight (KSTL)", "last_day": "2026-10-28", "cobra_monthly_premium": 760}  
  Agent did: sell KSTL $32,031 [rule:concentration]; buy CASH $28,391 [rule:emergency_fund]; buy BOND $3,640 [rule:rebalance]  
  Score 0.80. **risk_band** (hard): equity 66.1% outside 70.0%-85.0% for risk 4. Backtest: min cash 0.0 months, forced sale $0, breach True.

### Drift: final version on new conditions (inheritance, divorce, real crashes)

Drift level **green** — no trusted rule broken. Passed 70% of drift cases.

- `d-001` (divorce) — agent did: sell US_EQ $3,686 [rule:rebalance]; buy BOND $3,686 [rule:rebalance] — `emergency_fund`: cash 1.4 months, needs 3
- `d-005` (divorce) — agent did: sell KSTL $18,000 [rule:concentration]; sell BOND $1,714 [rule:rebalance]; buy US_EQ $11,000 [rule:concentration]; buy INTL_EQ $6,332 [rule:concentration]; buy CASH $2,382 [rule:rebalance] — `emergency_fund`: cash 2.4 months, needs 3
- `d-010` (inheritance, child) — agent did: sell CASH $43,094 [rule:rebalance]; sell HLXR $2,249 [rule:concentration]; buy BOND $8,703 [event:e1]; buy US_EQ $27,000 [event:e1]; buy INTL_EQ $9,640 [event:e1] — `risk_band`: equity 62.0% outside 70.0%-85.0% for risk 4

Drift analyst (subq, 70 runs read): Across 70 runs the same five failure modes repeat: marriage events never produce a compliant joint_profile_review flag (6/6 runs), layoffs where the 6-month reserve is funded by selling equity push equity below the risk-band floor (7/13 layoff runs, plus d-010 by the same mechanism), and no-event portfolios within 5 points of target still get traded (7/15 runs). Near-retirement clients with stale 2019 targets are left at the stated equity weight (5/6 runs), and thin cash reserves without an income-loss event are rebalanced down instead of funded (3/5 runs).
- marriage event in events.json (c-021, c-028; 6 runs) → `event_marriage` fails 100% (6 runs). c-028: 'missing joint_profile_review flag' — the marriage is described in the rationale but no compliant flag is emitted; c-021 run 2 even lists a joint_profile_review flag and is still scored as missing
- layoff / income loss where the 6-month reserve is funded by selling equity (c-024, c-026, c-032, c-036, d-002; 13 runs) → `risk_band` fails 54% (13 runs). c-036: 'equity 66.1% outside 70.0%-85.0% for risk 4' — the KSTL trim funds a 6.4-month reserve and lands 4-14 points under the band floor; c-032 fails 3/3 at 46.3%, 46.5%, 40.8% vs a 50% floor
- no events and portfolio within 5 points of target, with the cash reserve off its target (c-025, c-031, c-037; 9 runs) → `no_churn` fails 78% (9 runs). c-031: '3 trades on a portfolio within 5 points of target with no events' — bond trimmed 14,124 to hit exact 88/2/10 weights; c-037 fails 3/3
- client near retirement (age 55 with 10-year horizon, age 63 with 2-year horizon) and model targets last revised 2019 (c-029, c-039; 6 runs) → `glidepath` fails 83% (6 runs). c-039: 'age 63: equity 65.0%, needs <= 60.0% (low half of band)' — the stated 65% target is followed and the concern is only flagged; c-029 fails 3/3 at 45.0% vs a 40% ceiling
- cash below the 3-month floor with no income-loss event (c-022, d-001, d-005; 5 runs) → `emergency_fund` fails 60% (5 runs). d-001: 'cash 1.4 months, needs 3' — the rebalance follows the 3% cash target and leaves the reserve untouched; c-022 fails only in the run that rebalanced to the stated 14% cash target instead of funding the reserve first

Snap event gate on drift cases: flagged the rule that actually failed on 1 of 3 failing cases. Window verdict: level red (rules: green), rollback p=0.294, rule at risk `emergency_fund`.

### Client journeys (per-client learning, proven on the client's own later quarters)

| Client | Regime | Lessons | Holdout pass: generic → own agent | Mean | Backtest breaches |
|---|---|---|---|---|---|
| Priya Okafor (j-001) | Credit crisis: steady market, then a 50% equity cr | 1 | 3/5 → 3/5 | 0.92 → 0.84 | 3 → 3 |
| Marcus Delgado (j-002) | Pandemic shock: a fast 20%+ crash, then a strong r | 0 | 5/5 → 5/5 | 0.97 → 0.97 | 0 → 0 |
| Elena Varga (j-003) | Rate shock: stocks and bonds fall together, then a | 1 | 5/5 → 5/5 | 0.92 → 0.92 | 0 → 0 |
| Kenji Lundgren (j-004) | Dot-com bust: a slow multi-year bear market, with  | 3 | 4/5 → 5/5 | 0.93 → 1.00 | 2 → 1 |
| Hannah Brennan (j-005) | Calm bull market with low volatility (a small corr | 1 | 4/5 → 3/5 | 0.93 → 0.88 | 1 → 1 |
| Rafael Sandoval (j-006) | Mixed: a 2015-16 correction, then a steady rally | 1 | 4/5 → 5/5 | 0.95 → 0.97 | 0 → 0 |

Lessons learned inside journeys:
- j-005 at t02 (t02 score 0.75->0.80; earlier checkpoints held): "When a client marries and the spouse has separate accounts, I flag the profile for a joint review instead of returning no action." — root cause: I ignored the marriage event details and returned no trades without flagging that the client's profile needed a joint review. — triggered by marriage life event with spouse financial details
- j-006 at t02 (t02 score 0.75->1.00; earlier checkpoints held): "After a layoff, I check the client's cash runway against the required months and recommend raising cash first if it is short." — root cause: The agent made no trades and did not check the emergency-fund requirement after a layoff, leaving cash below the required runway. — triggered by layoff event
- j-003 at t03 (t03 score 0.75->1.00; earlier checkpoints held): "After a raise or job change, I update the client's monthly contribution instead of leaving it null." — root cause: The agent saw the job_change event but made no trades and left monthly_contribution null, ignoring the income change. — triggered by job_change event with a salary increase
- j-004 at t02 (t02 score 0.60->1.00; earlier checkpoints held): "Before I answer with no trades, I check every holding's weight against the concentration cap." — root cause: I returned no trades without weighing the positions, so an over-cap holding was left untouched. — triggered by any case where a holding's weight may exceed the concentration cap
- j-004 at t02 (t02 score 0.60->1.00; earlier checkpoints held): "When a client marries, I flag the profile for a joint review and record the spouse's income and separate accounts where the case data supports it." — root cause: I ignored the marriage event and wrote no joint_profile_review flag or profile update. — triggered by marriage event
- j-001 at t04 (t04 score 0.80->1.00; earlier checkpoints held): "Before I rebalance, I check how many months of expenses the client holds in cash, and I never sell cash below the emergency-fund floor." — root cause: The agent treated cash as a rebalancing source and sold it to fund an equity buy without checking the client's months of expenses. — triggered by A routine rebalance case with no life events, where cash looked like idle capital.
- j-004 at t04 (t04 score 0.80->1.00; earlier checkpoints held): "After a layoff, I work out how many months of expenses the cash covers and fill any shortfall from sale proceeds before I put a dollar into equities." — root cause: I trimmed the over-cap employer stock but sent most of the proceeds into equities, leaving cash below the required months of expenses. — triggered by layoff or income-drop event

Journey changes rejected by the gate:
- j-002 at t05: t05 score 0.80->0.80; broke earlier t01, t04
- j-004 at t04: t04 score 0.80->0.80; earlier checkpoints held

### Cost and speed

- Agent: 441 runs, 3,761,447 tokens in, 1,626,660 out, mean 28.2 s/case, errors 0 (0%)
- Mentor: 9 calls, 18,515 tokens in, 35,017 out, 83.8 s total
- Wall clock: 32.1 min

## Feedback for Subquadratic: SubQ Preview (LLM) and SubQ Snap (decision models)

Written for the SubQ team as product feedback from one day of building on both models. Every number below comes from this benchmark or from our calibration runs; Muse (Meta) is the comparison on identical inputs.

### 1. What we gave it

**(a) SubQ Preview as the portfolio agent (inside the Pi coding-agent harness).** Per case, one Pi process:
- System prompt = the playbook prompt (generic v0: 3 sentences) plus a skills list (name + description; Pi loads `SKILL.md` on demand). v0 has one skill, `recommendation-format`.
- Tools: `read`, `bash`, `write` (OpenAI-style function calling through `/v1/chat/completions`).
- Working directory: `client.json`, `holdings.json`, `market.json` (prices + 48 months of real monthly history), `events.json`, and `tools/portfolio.py` (allocation / apply helper).
- Task message: "Review this client case and write recommendation.json. There are no hidden rules, tests or other files to find…"
- Measured: **8,529 input tokens per case** cumulative across turns (Muse: 18,034), 6.6 turns per case (Muse: 7.0).

**(b) SubQ Preview as the mentor.** One chat call with `runtime/prompts/mentor.md`: the full parent playbook YAML, up to 8 failure summaries (client age/risk, life events with dates and details, the agent's trades, each violated rule with its numeric detail), current scores, and instructions to diagnose root cause → triggering event, change at most 3 things, and return full YAML with a `lessons` list. Measured across the run: 9 calls, 18,515 tokens in, 35,017 out (Muse Wonder: 4 calls, 9,149 in, 35,197 out).

**(c) SubQ Preview as the drift analyst.** One long-context call: every scored run of the final version (test + drift) as JSON lines (case, score, violations, full recommendation) plus the playbook YAML, asking for systematic failure patterns as JSON. Measured: 70 runs read, 45450 input tokens, 9.0 s.

**(d) SubQ Snap (`POST /v1/systemone`, `subq-snap-1.1`).** Two gates:
- *Event gate* (runs before the agent, triggered by a MongoDB change stream on new life events). State = client profile, holdings, the new event, earlier events, and the agent's playbook (prompt + each skill's when/steps). Questions = one `noul` per policy rule ("is this rule at risk if nothing changes?"), a `covered` noul ("does the playbook address this event?"), and an `urgency` score (4 levels). ~1.3–1.4K input tokens.
- *Window verdict* (after a batch of runs). State = baseline, trusted rules, then each run labelled `[R1]…[R10]` with case, tags, score, PASS/FAIL and violation details. Questions = `rollback` (noul), `level` (choice green/yellow/red), `rule` (choice over 10 rules + `not_found`), `novel` (noul), `urgency` (score).

A real Snap request and response (trimmed):

```json
{
 "model": "subq-snap-1.1",
 "state": "Shipped playbook v3 passed emergency_fund on 100% of verification clients. In the last 10 live runs after a market drop of -25%, 4 runs failed emergency_fund (cash 2.1 to 2.8 months, needs 3), 1 failed concentration (KSTL 13.4%, max 10%). Rolling score 0.71 vs baseline 0.93.",
 "questions": {
  "rollback": {
   "type": "noul",
   "instructions": "Should the system roll back to the last known-good playbook now?",
   "criteria": {
    "true": "Hard client-protection rules that used to pass are now failing",
    "false": "Only noise or soft issues"
   }
  },
  "level": {
   "type": "choice",
   "instructions": "Drift level",
   "criteria": {
    "green": "No hard violations, score near baseline",
    "yellow": "Score dropping or soft violations rising",
    "red": "Hard violations of rules that used to pass"
   }
  },
  "severity": {
   "type": "score",
   "instructions": "How urgent is a fix?",
   "criteria": [
    "Can wait",
    "This week",
    "Today",
    "Immediately"
   ]
  }
 }
}
```

```json
{
 "model": "subq-snap-1.1",
 "answers": {
  "level": {
   "type": "choice",
   "choice": "red",
   "probabilities": {
    "red": 0.9937,
    "yellow": 0.0062,
    "green": 0.0001
   },
   "confidence": 0.9905
  },
  "rollback": {
   "type": "noul",
   "noul": 0.9969
  },
  "severity": {
   "type": "score",
   "score": 2.88,
   "probabilities": {
    "0": 0.0014,
    "1": 0.0251,
    "2": 0.0654,
    "3": 0.9082
   },
   "confidence": 0.8804
  }
 },
 "usage": {
  "input_tokens": 279,
  "output_tokens": 0
 }
}
```

### 2. How it emits: persona and behavior

- **Verbosity.** As the agent, Preview writes **3,689 output tokens per case** vs Muse Spark's 6,240 — it reaches a decision with less deliberation. Final messages average 302 characters (Muse 95).
- **Tool use in Pi.** Tool calls: {'bash': 1644, 'read': 2734, 'write': 438} (Muse: {'bash': 1639, 'read': 3560, 'write': 506}). Tool errors 9 (Muse 9). Calls that left the case folder (`find / `, `ls ..`, `/usr`, `git`): 0 (Muse 0); greps for policy words ("emergency", "cap", "policy") to look for hidden thresholds: 1 (Muse 0). Preview often lists the case folder first (`ls -la` + `find <case> -type f`), batches reads into one `bash` call, and verifies with `portfolio.py apply` before finishing.
- **Agent errors.** 0 of 441 runs ended without a valid file (Muse 4 of 514).
- **Format compliance as mentor.** 12 invalid playbook attempts out of ~22 proposals (Muse 0). By kind: {'lessons': 10, 'missing keys': 1, 'YAML parse': 0, 'changes from parent': 1, 'other': 0} (Muse {'lessons': 0, 'missing keys': 0, 'YAML parse': 0, 'changes from parent': 0, 'other': 0}). The common miss was the `lessons` list shape (strings or missing fields instead of `{lesson, root_cause, triggered_by, rule, skill}`), and once dropping `tools`/`max_turns` from the full YAML. Every miss was fixed on the next attempt when we fed the validator's error back.
- **Generality.** Gemini compliance blocks for client-specific or loosening content — SubQ: 0, Muse: 1. Example Muse block: "hard-codes a $600 monthly contribution threshold derived from a specific client case".

Sample lessons written by each mentor (verbatim):

- SubQ: "When a client marries and the spouse has separate accounts, I flag the profile for a joint review instead of returning no action."
- SubQ: "After a layoff, I check the client's cash runway against the required months and recommend raising cash first if it is short."
- SubQ: "After a raise or job change, I update the client's monthly contribution instead of leaving it null."
- SubQ: "Before I answer with no trades, I check every holding's weight against the concentration cap."
- SubQ: "Before I rebalance, I check how many months of expenses the client holds in cash, and I never sell cash below the emergency-fund floor."
- Muse: "When a client gets married, I flag the case for a joint profile review even if I recommend no trades."
- Muse: "After a layoff, I build six months of cash before rebalancing anything else."
- Muse: "After a job change that raises my income, I increase my monthly contribution in line with the raise instead of leaving it unchanged."
- Muse: "Before rebalancing or reducing a concentrated holding, I check my cash in months of expenses and send sale proceeds to cash first if it is below the required emergency fund."
- Muse: "When I get a raise in a job change, I increase my monthly contribution in proportion to the new income instead of leaving it unchanged."

### 3. SubQ Preview as an LLM, head to head

| | SubQ Preview | Muse |
|---|---|---|
| Agent: unseen test mean, generic v0 | 0.812 | 0.818 |
| Agent + mentor: final version | v3 0.912 | v2 0.923 |
| Paired gain, 90% CI | +0.101 (+0.062…+0.140) | +0.105 (+0.053…+0.160) |
| Control arm (shuffled evidence) gain | +0.069 | +0.003 |
| Training versions shipped / tried | 1 / 3 | 1 / 3 |
| Drift set pass rate (final) | 70% | 100% |
| Seconds per case | 28.2 | 54.3 |
| Output tokens per case | 3,689 | 6,240 |
| Agent error rate | 0% | 1% |

Journeys (holdout quarters, generic agent → client's own agent):

- Priya Okafor (j-001): SubQ 3/5→3/5 (mean 0.92→0.84); Muse 3/5→3/5 (mean 0.92→0.92)
- Marcus Delgado (j-002): SubQ 5/5→5/5 (mean 0.97→0.97); Muse 5/5→5/5 (mean 0.97→0.97)
- Elena Varga (j-003): SubQ 5/5→5/5 (mean 0.92→0.92); Muse 5/5→5/5 (mean 0.88→0.92)
- Kenji Lundgren (j-004): SubQ 4/5→5/5 (mean 0.93→1.00); Muse 5/5→5/5 (mean 0.93→0.93)
- Hannah Brennan (j-005): SubQ 4/5→3/5 (mean 0.93→0.88); Muse 3/5→3/5 (mean 0.88→0.88)
- Rafael Sandoval (j-006): SubQ 4/5→5/5 (mean 0.95→0.97); Muse 4/5→5/5 (mean 0.95→0.93)

**Strengths.** About 2× faster per case than Muse Spark, fewer output tokens, decisive tool use, and lessons that read as general habits. A strong fit for high-volume per-event re-runs.
**Weaknesses.** In this phase, SubQ's fleet training was limited by **output format, not reasoning**: most mentor attempts failed our structural validator (the `lessons` list shape, dropped `tools`/`max_turns` keys, or more than 3 changes), so few candidates reached the gate. After this run we switched the mentor to structured JSON output (`response_format: json_schema`) with lenient lesson parsing, identical for every model; with that change SubQ's mentor produced a valid playbook on the first try (10.8 s; lesson: "After a layoff, I fund the emergency reserve to the required months before rebalancing anything else."). Separately, some per-client lessons fixed the checkpoint they were learned on but did not carry to the client's later quarters (the journeys above where the mean dropped); the time-based holdout caught each of these, which is what it is for.

### 4. SubQ Snap review

**How we use it.** The rule checker is the source of truth. Snap runs (1) before the agent on every new life event to say which rules are at risk and whether the playbook covers it, so risky uncovered events are re-run first, and (2) after a batch as a second opinion on rollback, drift level, the rule at risk, novelty and urgency. Disagreements with the rules are logged.

**Calibration against the rule checker** (39 events, 14 labelled windows):
- Event gate at p ≥ 0.6: F1 0.94, precision 0.98, recall 0.90.
- Window verdict: drift level matched the rules on 14 of 14 windows; named the actually failing rule on 6 of 6 red windows.
- About 0.8 s and ~1.4K input tokens per decision; output tokens are free.
- Rollback probability is graded sensibly: a single isolated hard failure gets 0.17–0.31, a pattern gets ≥ 0.99. We therefore keep rollback rule-driven and use Snap for severity and diagnosis.
- Notable miss: on the layoff fixture, `risk_band` came back at p = 0.126 although equity was 71.9% against a 50–70% band (pre-trade). Emergency fund (0.999) and concentration (0.961) were right. Full answer: `{"emergency_fund": 0.999, "concentration": 0.961, "risk_band": 0.126, "event_child": 0.003, "event_marriage": 0.008, "event_job_change": 0.004, "glidepath": 0.001}`, coverage 0.006.

**In this benchmark (drift set, final SubQ playbook):** the event gate flagged the rule that actually failed on 1 of 3 failing drift cases. Window verdict: level red vs rules green, rollback p 0.294, rule `emergency_fund`, novel p 0.28, 0.14 s.

- `d-001` divorce: at risk ['emergency_fund'] (covered 0.013); actually failed ['emergency_fund']
- `d-002` market_drop: at risk ['emergency_fund'] (covered 0.043); actually failed nothing
- `d-003` inheritance: at risk ['risk_band'] (covered 0.015); actually failed nothing
- `d-004` job_change: at risk ['event_job_change'] (covered 1.0); actually failed nothing
- `d-005` divorce: at risk ['concentration'] (covered 0.024); actually failed ['emergency_fund']
- `d-006` inheritance: at risk ['risk_band'] (covered 0.03); actually failed nothing

### Requests for the SubQ team

1. **Probability semantics.** Document how calibrated `noul` and choice probabilities are and on what data, so thresholds can start from something better than 0.5. We had to calibrate ourselves.
2. **Latency and rate limits.** Publish typical latency by state size and the rate limits; the docs only mention 429.
3. **Model list.** `subq-snap-latest`, `subq-snap-preview` and `subq-1p2-medium` appear in `GET /v1/models` but not in the docs. `subq-1p2-medium` returned word-for-word the same answer as `subq-preview` in our test — is it an alias?
4. **Helpful errors.** Sending a Snap model to `/v1/chat/completions` returns "does not support completions requests". Pointing to `/v1/systemone` in that message would have saved us time.
5. **Access timeline.** `subq-preview` returned 403 `model_not_allowed` early in the day and worked later without a code change. A status field or email when access is granted would help.
6. **Structured output for long YAML.** Preview's YAML playbooks occasionally dropped required keys or reshaped nested lists; JSON-schema-constrained output for the chat endpoint would remove the retry.

## Method notes

- Policy rules and thresholds are illustrative; clients are synthetic; market returns are real monthly data (Kenneth French library, FRED).
- The mentor sees violation details for practice clients only; test, regression, drift and journey holdout quarters are never shown to it.
- Run-to-run noise is real: the same agent and case can pass once and fail the next run. That is why every gate decision uses 3 runs per client and a paired confidence interval, and regression flips are re-run before they count.
- The control arm uses the same mentor and gate with shuffled evidence; a real effect should beat it.

---

# Framework across models (phase 2: harder data) — PARTIAL

**Partial result.** Phase 2 was stopped before any stack finished: Muse and the mixed stack for budget, SubQ when its credit ran out (HTTP 402 `insufficient_credits`), Gemini for budget. No training generation completed in phase 2, so there are no phase-2 gate decisions or fleet gains to report. What follows is the generic-v0 behavior on the harder data and the per-client journey learning that did complete.

Setup: 300 stress cases (54 event types, incl. financial-services crises: firm collapse, deferred-comp loss, blackout windows, margin calls; cascading health/family/debt events), fixed-seed 60/60 practice/test split stratified by event family; journeys j-008, j-012, j-015, j-018, j-020, j-021, j-024, j-027. Same harness, structured-JSON mentor, Gemini reviewer.

| Stack | Status |
|---|---|
| Muse (Spark agent, Wonder mentor) | stopped for budget (Muse credit cap ~$100) |
| SubQ Preview | stopped: SubQ credit ran out (402 insufficient_credits from stress case s-074); runs after that excluded |
| Gemini 3.8 Flash | stopped for budget after the sandbox fix restart (v0 evaluation incomplete) |
| mixed | stopped for budget during v0 (Muse agent); its database was reset when SubQ credit ran out, so its runs are not in this report |

## Generic v0 on unseen stress cases (runs completed before the stop)

| | Muse (Spark agent, Wonder mentor) | SubQ Preview | Gemini 3.8 Flash |
|---|---|---|---|
| Test runs scored | 120 | 120 | 43 |
| Run pass rate | 57% | 53% | 28% |
| Mean score | 0.805 | 0.772 | 0.323 |
| Hard-rule violation rate | 42% | 43% | 67% |
| Ran out of turns / timed out (all runs) | 0 / 1 of 265 | 0 / 0 of 260 | 39 / 6 of 69 |
| Provider-side errors (excluded) | 0 | 0 | 0 |
| Latency p50 / p95 (s) | 68.0 / 127.5 | 30.5 / 106.5 | 149.9 / 262.0 |

For reference, on the same stress cases the scenario generator's naive rebalancer passes 34% and doing nothing passes 18%.

### By event family (generic v0, run pass rate, n runs)

| Family | Muse (Spark agent, Wonder mentor) | SubQ Preview | Gemini 3.8 Flash |
|---|---|---|---|
| debt | 100% (2) | 0% (2) | 100% (1) |
| family | 60% (10) | 70% (10) | 0% (3) |
| fs_crisis | 47% (32) | 50% (32) | 18% (11) |
| health | 67% (18) | 50% (18) | 17% (6) |
| housing | 33% (6) | 0% (6) | 0% (2) |
| legal | 100% (4) | 75% (4) | 0% (2) |
| loss | 25% (8) | 25% (8) | 0% (4) |
| no_event | 100% (6) | 100% (6) | 67% (3) |
| windfall | 75% (8) | 75% (8) | 67% (3) |
| work | 50% (26) | 58% (26) | 50% (8) |

### Specific failures (generic v0)

**Muse (Spark agent, Wonder mentor)**
- `s-081` (fs_crisis) — agent did: no trades (Paused trading pending Chapter 7 bankruptcy clearance; referred for human and attorney review.) — `risk_band`: equity 24.2% outside 30.0%-50.0% for risk 2; `emergency_fund`: cash 0.7 months, needs 3; `review_flag`: missing flag(s): legal_review
- `s-081` (fs_crisis) — agent did: no trades (Pause all trading pending trustee/attorney clearance after recent Chapter 7 filing.) — `risk_band`: equity 24.2% outside 30.0%-50.0% for risk 2; `emergency_fund`: cash 0.7 months, needs 3; `review_flag`: missing flag(s): legal_review
- `s-170` (work) — agent did: sell CASH $16,665 [rule:emergency_fund]; buy BOND $12,339 [rule:rebalance]; buy US_EQ $3,200 [rule:rebalance]; buy INTL_EQ $1,126 [rule:rebalance] — `emergency_fund`: cash 5.5 months, needs 6 after layoff; `income_shock_fund`: cash 5.5 months, needs 6 after income shock (furlough); `review_flag`: missing flag(s): debt_review
- `s-294` (family) — agent did: sell BOND $17,180 [rule:rebalance]; buy US_EQ $9,275 [rule:rebalance]; buy CASH $7,905 [event:e2] — `emergency_fund`: cash 2.5 months, needs 3; `event_marriage`: missing joint_profile_review flag; `known_cash_need`: cash 29,707 USD, needs 45,150 (3 months expenses + 9,900 due within 12 months)

**SubQ Preview**
- `s-090` (fs_crisis) — agent did: sell BOND $41,720 [rule:emergency_fund]; buy CASH $41,720 [rule:emergency_fund]; sell BOND $37,000 [event:e3]; buy CASH $37,000 [event:e3] — `valid_output`: profile_updates.goals_add must be a list of objects with type
- `s-230` (health) — agent did: sell US_EQ $13,400 [rule:rebalance]; sell INTL_EQ $4,271 [rule:rebalance]; buy BOND $6,228 [rule:rebalance]; buy CASH $11,443 [rule:rebalance] — `valid_output`: profile_updates.goals_add must be a list of objects with type
- `s-256` (fs_crisis) — agent did: sell BOND $23,442 [rule:emergency_fund]; buy CASH $23,442 [rule:emergency_fund] — `valid_output`: profile_updates.goals_add must be a list of objects with type
- `s-031` (health) — agent did: sell US_EQ $4,767 [rule:rebalance]; sell BOND $9,000 [rule:emergency_fund]; buy CASH $13,767 [rule:emergency_fund] — `valid_output`: profile_updates.goals_add must be a list of objects with type

**Gemini 3.8 Flash**
- `s-020` (fs_crisis) — agent did: no trades — `valid_output`: run failed: max_turns (20) reached
- `s-049` (family) — agent did: no trades — `valid_output`: run failed: max_turns (20) reached
- `s-031` (health) — agent did: no trades (Asset allocation drift is modest (+2.3% equity, -2.7% bond, +0.5% cash) and well within typical 5% rebalancing tolerance bands. Existing cash reserves of $26,290 sufficiently cover the $9,100 medical out-of-pocket maximum. The recent cancer diagnosis and external crypto loss require human advisor consultation before modifying portfolio targets or liquidating assets.) — `valid_output`: run failed: timeout after 180s
- `s-066` (loss) — agent did: sell US_EQ $22,638 [rule:rebalance]; buy BOND $8,621 [rule:rebalance]; buy CASH $14,017 [rule:rebalance] — `valid_output`: run failed: max_turns (20) reached

### Per-client learning in journeys (completed checkpoints)

**Muse (Spark agent, Wonder mentor)** — 6 lessons learned, 8 candidate changes rejected by the gate, 22 holdout checkpoints scored.
- j-020 at t01 (t01 score 0.80->1.00; earlier checkpoints held): "I fund cash to the required months of expenses before using any sale proceeds to rebalance into bonds or other assets." — triggered by cash reserves below the required emergency-fund months
- j-027 at t01 (t01 score 0.80->1.00; earlier checkpoints held): "I fund cash to the required months of expenses first, before using any sale proceeds to rebalance or reduce concentration." — triggered by A concentrated holding sale while cash was below the required emergency level, with no life event.
- j-018 at t03 (t03 score 0.75->1.00; earlier checkpoints held): "After an income shock, I build cash to six months of expenses before putting sale proceeds into bonds or equities." — triggered by regulatory_ban
- j-018 at t03 (t03 score 0.75->1.00; earlier checkpoints held): "When an event raises regulatory, insider, restricted-list, or pre-clearance issues, I add a legal_review flag for a human to check." — triggered by regulatory_ban, insider_status
- j-012 at t05 (t05 score 0.71->1.00; earlier checkpoints held): "After a disability or other income shock, I build cash to six months of my new monthly expenses before buying equities again." — triggered by disability
- j-012 at t05 (t05 score 0.71->1.00; earlier checkpoints held): "When care costs raise my monthly spending, I recalculate my cash buffer using the increased expenses, not the old ones." — triggered by disability with monthly cost increase
- j-027 at t02 (t02 score 0.57->1.00; earlier checkpoints held): "After an income shock, I build six months of cash before rebalancing anything else." — triggered by An income shock event such as a desk shutdown or furlough
- j-027 at t02 (t02 score 0.57->1.00; earlier checkpoints held): "When I sell a concentrated equity holding, I replace enough of it with diversified equity to keep total equity inside the client's risk band." — triggered by A concentrated equity sale that would move post-trade equity outside the risk band
- j-027 at t02 (t02 score 0.57->1.00; earlier checkpoints held): "When I see a credit card debt event, I add the debt_review flag for human review." — triggered by A credit_card_debt event
- j-015 at t04 (t04 score 0.80->1.00; earlier checkpoints held): "When cash is short of the required emergency fund, I put sale proceeds into cash first and verify I finish clearly above the minimum, not just at it, before buying anything else." — triggered by Low cash relative to monthly expenses with no life events reported
- rejected at j-027 t01: t01 score 0.80->0.80; earlier checkpoints held
- rejected at j-021 t02: t02 score 0.75->0.88; earlier checkpoints held
- rejected at j-015 t02: t02 score 0.83->0.83; earlier checkpoints held
- rejected at j-015 t02: t02 score 0.83->0.83; earlier checkpoints held

**SubQ Preview** — 7 lessons learned, 21 candidate changes rejected by the gate, 27 holdout checkpoints scored.
- j-012 at t01 (t01 score 0.80->1.00; earlier checkpoints held): "When a holding is over its concentration cap, I compute the exact dollar excess from the portfolio total and re-check the post-trade weight before I write the trade." — triggered by A single holding sitting above the concentration cap in a case with no life events to distract from the arithmetic.
- j-008 at t02 (t02 score 0.83->1.00; earlier checkpoints held): "When a client needs cash for a dated expense, I fund it from cash and from positions that are already over their target or over their cap, and I recheck every holding's weight before I write the recommendation." — triggered by home_purchase event with a large amount due
- j-021 at t04 (t04 score 0.86->1.00; earlier checkpoints held): "After an income shock, I check the client's cash runway against the required months and top up cash before doing other rebalancing." — triggered by firm_collapse and gig_income events
- j-012 at t04 (t04 score 0.60->1.00; earlier checkpoints held): "Even when a case is dominated by life events, I still screen every holding against its concentration cap before I decide on trades." — triggered by A case carrying several life events (high-interest debt, a deferred comp clawback) and no obvious rebalance trigger, so the agent concluded 'no trades' without checking caps first.
- j-012 at t04 (t04 score 0.60->1.00; earlier checkpoints held): "When a case has high-interest debt or a legal or conduct event, I add the matching review flag even if I recommend no trades." — triggered by A credit card debt event and a deferred compensation clawback for a conduct review.
- j-027 at t03 (t03 score 0.67->1.00; earlier checkpoints held): "Before I recommend any trade, I check how many months of expenses the client's cash covers, and if it is short I top up cash first instead of buying bonds." — triggered by any trade recommendation, especially one triggered by a concentration or rebalance signal while cash is thin
- j-027 at t03 (t03 score 0.67->1.00; earlier checkpoints held): "When a client changes jobs and earns more, I set a positive monthly contribution from the new income instead of leaving it null." — triggered by job_change event with a higher new_income
- j-008 at t03 (t03 score 0.67->1.00; earlier checkpoints held): "When a client has dated cash needs, I reserve cash for the emergency-fund floor and every known amount due before I buy any non-cash asset." — triggered by multiple dated cash needs (tax bill and relocation) due within the policy horizon, rule: emergency_fund, skill: life-event-cash-needs
- j-012 at t05 (t05 score 0.71->1.00; earlier checkpoints held): "When a case has an income shock or a new recurring cost, I compute months of cash coverage against post-event expenses and size the cash reserve before I finalize any trade." — triggered by A long-term disability event that cut income to a share of its former level and added a monthly care cost on top of existing expenses.
- rejected at j-027 t01: t01 score 0.60->0.60; earlier checkpoints held
- rejected at j-020 t01: t01 score 0.80->0.80; earlier checkpoints held
- rejected at j-027 t01: t01 score 0.60->0.80; earlier checkpoints held
- rejected at j-020 t01: t01 score 0.80->0.80; earlier checkpoints held

**Gemini 3.8 Flash** — 0 lessons learned, 13 candidate changes rejected by the gate, 0 holdout checkpoints scored.
- rejected at j-020 t01: t01 score 0.00->0.00; earlier checkpoints held
- rejected at j-027 t01: t01 score 0.00->0.50; earlier checkpoints held
- rejected at j-020 t01: t01 score 0.00->0.00; earlier checkpoints held
- rejected at j-018 t01: t01 score 0.00->0.00; earlier checkpoints held

## Muse spend recorded today (phase 1 + phase 2 + other runs)

Priced at $1.25 / 1M input and $4.25 / 1M output tokens. Mentor tokens are stored as one total, so they are priced at the output rate (an upper bound).

| Database | Muse agent runs | Tokens in | Tokens out | Agent $ | Mentor tokens | Mentor $ (max) |
|---|---|---|---|---|---|---|
| ballast_bench2_muse | 265 | 4,619,218 | 1,893,405 | $13.82 | 105,202 | $0.45 |
| ballast_bench_muse | 514 | 9,269,659 | 3,207,600 | $25.22 | 85,728 | $0.36 |
| ballast_muse | 299 | 4,883,998 | 1,192,633 | $11.17 | 47,627 | $0.20 |
| **Total** | | | | **$50.21** | | **$1.01** |

Not included: the mixed stack's phase-2 runs (Muse agent; its database was reset before the budget stop, so its tokens were not kept — roughly 75–100 runs, about $3–5 at the phase-1 Muse rate per run), and any Muse calls made outside the harness (direct tests, website live runs that were not logged to these databases).

### Also found and fixed during phase 2

- **Run isolation.** Concurrent runs on one machine shared `/tmp` and one unprivileged user. Under the generic v0, Gemini agents ran `find /tmp` and read other concurrent runs' skill files (8 of its first 22 runs). Phase 1 had 0 such runs; Muse, SubQ and mixed in phase 2 had none that read another run's skills. Fixed by placing every run under a root-owned, non-listable `/sandbox` (verified: the agent user gets Permission denied and finds no `SKILL.md`); Gemini was restarted on the fixed image and those contaminated runs were discarded.
- **Provider errors.** The harness now records the model API's own error (e.g. 402 or 429) instead of "did not write recommendation.json", so provider failures are reported separately from agent failures.
- **Gemini under a generic skill file** ran out of its 20 turns or the 3-minute limit on most cases once it could no longer find other runs' files. That is a real behavior; whether the mentor can teach it to be decisive was the next thing phase 2 would have measured.

