# ballast. scenarios

These are synthetic US retail-investor households for the portfolio agent. Their profiles, holdings and life events are calibrated to public data. Fund price histories and the held-out forward months are **real monthly index returns** that have been re-dated. Every parameter and its source is listed in [SOURCES.md](SOURCES.md). All names, employers and tickers (`HLXR`, `NMBX`, `KSTL`) are invented.

## Regenerate

```bash
python scenarios/fetch_market_data.py   # optional: refresh data/monthly_returns.csv (committed; needs internet)
python scenarios/generate.py            # rewrites cases/{practice,test,regression,drift}/, holdout/, manifest.json
python scenarios/oracle.py              # solvability self-check, baseline difficulty, held-out backtest
python scenarios/oracle.py --case scenarios/cases/test/c-024    # one oracle recommendation + score
python scenarios/oracle.py --write      # oracle outputs -> scenarios/oracle_out/ (gitignored)
python scenarios/backtest.py <case_dir> <recommendation.json>   # forward metrics for any recommendation
```

- **Deterministic.** Households draw from `random.Random(SET_SEED*1000 + index)`, and the market window from `SET_SEED*1000 + index + 7,000,000`. Seeds are in `config.yaml`. A rerun gives byte-identical files.
- **Dependencies.** The stdlib, plus PyYAML for `config.yaml` (already in `requirements.txt`). No network access is needed unless you refresh the data.
- **Shared math.** Weights, post-trade values and the backtest's trade application all reuse `agent/tools/portfolio.py`, so the generator, agent, checker and backtest agree on the numbers.

## What is in a case

```
scenarios/cases/<set>/<id>/        <- copied into the agent's working directory
  client.json  holdings.json  market.json  events.json
scenarios/holdout/<set>/<id>/      <- never copied; only backtest.py reads it
  future.json
```

- `client.json`, `holdings.json` and `events.json` follow SPEC.md exactly. `client.json` adds realism fields that the checker ignores: `name`, `state`, `occupation`, `employment_status`, `marital_status`, `employer` and `notes`.
- `market.json` keeps the SPEC shape (`as_of`, `symbols{price, class, single_stock}`) and adds an optional `history` field. It holds 48 month-end total-return prices per non-cash symbol, ending at the current price, plus `dates`, `tbill_annual_pct` and a provenance `note`. Readers that ignore `history` are unaffected.
- `future.json` holds the next 12 month-end prices per symbol, the monthly T-bill `cash_return`, `source` (`real` or `simulated`), and `real_window` (which historical months were replayed). The real window is recorded only here and in the manifest, so the agent cannot look up "what happened next".
- In every position, `value = units × price` (to the cent). Each `targets` value falls inside the EVAL.md band for the client's `risk_score`.
- **Replay worlds.** Each case is an independent "replay world": a contiguous real window from 1990–2026 (French library US and developed ex-US market returns, a FRED GS10 bond model, T-bills), re-dated to end at as_of.
  - Non-drift windows avoid ending inside a crash.
  - Market-drop cases end at real troughs (2009-02, 2002-09, 2020-03, 2022-09). Their history shows the real fall, their market.json prices are lowered by that same real amount, and future.json holds the real rebound.
  - Single stocks are simulated with a beta and idiosyncratic noise.
- `cases/manifest.json` holds the archetype, tags, market source and overrides for each case.

## Drop-in data from teammates

- **`config.yaml`** holds every calibration number: assets and base prices, single-stock beta and vol, history and holdout lengths, crash anchors, simulation fallback, backtest settings, household tables, event parameters and seeds. A replacement with the same keys is picked up automatically.
- **`data/monthly_returns.csv`** (`month,US_EQ,INTL_EQ,BOND,CASH`, decimal monthly returns) can be replaced with any series. If the file is missing, returns are simulated from `config.market.simulate` and labelled `simulated`.
- **`overrides/<set>/<id>/{client,holdings,market,events,future}.json`** (same schema as the case files) replaces the generated file.
  - A `market.json` override reprices holdings at the same units.
  - Missing `history` or `future` blocks are rescaled to the new prices.
  - Run `oracle.py` afterwards, because an override can make a case unsolvable.

## Sets and event mix

| Set | Ids | n | Purpose |
| --- | --- | --- | --- |
| practice | c-001..c-020 | 20 | failures feed Muse |
| test | c-021..c-040 | 20 | ship gate (unseen) |
| regression | c-041..c-050 | 10 | clear-cut; a correct agent must always pass |
| drift | d-001..d-010 | 10 | new event types and shifted markets |

| Category | practice | test | regression | drift |
| --- | --- | --- | --- | --- |
| no events, within tolerance (no_churn applies) | 4 (one risk 5, one aged 55+) | 4 (one risk 5, two aged 55+) | 2 | – |
| no events, drifted >5 pts | 1 | 1 | 1 (equity over band) | – |
| no events, cash below 3 months | 1 | 1 | 1 | – |
| no events, single stock >10% | – | – | 1 | – |
| age 55+, stale targets above band midpoint | 1 | 1 | – | – |
| age 55+, employer stock >10% | 1 | 1 | – | – |
| layoff | 2 | 1 | 1 | – |
| layoff + single stock >10% | 1 | 2 | 1 | – |
| job_change (raise) | 2 | 2 | 1 | – |
| job_change (pay cut, rule not applicable) | 1 | 1 | – | – |
| marriage | 2 | 1 | 1 | – |
| child | 2 | 2 | 1 | – |
| two events | 2 (job_change+child, layoff+child) | 3 (job_change+child, marriage+job_change, layoff+child) | – | – |
| inheritance | – | – | – | 2 (one large) |
| divorce | – | – | – | 2 (one with concentration) |
| market_drop (real windows) | – | – | – | 3 (GFC to 2009-02: US −50%; 2022: US −25% and bonds −10%; dot-com to 2002-09 with employer stock: US −42%) |
| combos | – | – | – | market_drop (COVID to 2020-03) + layoff, inheritance + child, divorce + job_change |

In practice and test, 6 of 20 cases (30%) are plain no-event cases (the first three rows). The age-55+ glidepath rows also have no events, but they count toward the "age 55+" category. The rest are split across layoff, job change, marriage, child and age 55+, matching SPEC.md. Archetype order is shuffled within each set, so case ids carry no signal about the archetype.

## Distributions (all 60 cases)

| | min | p25 | median | p75 | max |
| --- | --- | --- | --- | --- | --- |
| age | 26 | 38 | 46 | 53 | 70 |
| annual income | $58.5k | $111k | $151k | $215k | $420k |
| monthly expenses | $4.6k | $6.8k | $8.3k | $10.7k | $17.2k |
| portfolio total | $40k | $191k | $294k | $468k | $1.26M |
| cash, in months of expenses | 1.3 | 3.4 | 4.2 | 5.5 | 61 (post-inheritance) |
| severance (weeks) | 2 | 5 | 10 | 14 | 18 |
| job change new/old income | 0.81 | 1.12 | 1.17 | 1.23 | 1.30 |

Risk scores across all cases: 1 → 2, 2 → 7, 3 → 28, 4 → 19, 5 → 4. The population is "households with an investment account", which skews to upper-middle income compared with all US families (SCF median income is $70k). Concentration, thin cash and big windfalls are oversampled on purpose, because they are the situations the policy exists for.

## Solvability and difficulty

`python scenarios/oracle.py` runs three recommenders through `checker/check.py`:

| set | oracle solvable (score 1.0, every applicable rule passes) | naive pass rate | naive mean score | do-nothing pass rate |
| --- | --- | --- | --- | --- |
| practice | 20/20 | 0.45 | 0.79 | 0.35 |
| test | 20/20 | 0.50 | 0.77 | 0.45 |
| regression | 10/10 | 0.30 | 0.78 | 0.20 |
| drift | 10/10 | 0.60 | 0.83 | 0.00 |

- **oracle** is a plain rule-follower. It raises cash to 3 or 6 months (with a 2% margin), caps single stocks at 9%, clamps equity inside the band (to the low half at age 55+), and makes the event profile updates. It leaves an in-tolerance, compliant portfolio alone. Every case is 100% solvable.
- **naive** stands in for v0. It rebalances the classes to client targets when one is more than 5 points off and ignores events and policy. Its test pass rate of 0.50 sits inside EVAL.md's target band for v0 (0.4–0.6). A real Muse v0 may land a little higher, because it can read events.json.

## Held-out backtest (extra metric, not a policy rule)

`backtest.py` applies the trades with `portfolio.post_trade`, then marks the result to market over the 12 held-out months. Unemployed clients pay `monthly_expenses` out of CASH for 6 months, and CASH earns the T-bill rate. It reports:

- `forward_return`: time-weighted.
- `max_drawdown`.
- `min_cash_coverage_months`.
- `forced_sale_usd`: risk assets sold because cash ran out.
- `emergency_fund_breached`: a forced sale if unemployed, otherwise cash below 3 months.
- `vs_hold_return`.

Current output, with "hold" meaning no trades:

| set | rec | mean fwd return | worst | mean max DD | median min cash cover (months) | EF breached |
| --- | --- | --- | --- | --- | --- | --- |
| practice | oracle | +8.5% | −15.4% | −7.1% | 3.8 | 0/20 |
| practice | naive | +8.9% | −12.7% | −7.0% | 4.1 | 5/20 |
| practice | hold | +9.1% | −12.7% | −7.1% | 4.7 | 5/20 |
| test | oracle | +7.7% | −13.8% | −7.0% | 3.9 | 0/20 |
| test | naive | +8.9% | −13.8% | −7.9% | 3.9 | 5/20 |
| test | hold | +8.7% | −13.8% | −8.1% | 4.0 | 5/20 |
| regression | oracle | +5.1% | −20.6% | −8.2% | 4.2 | 0/10 |
| regression | naive | +4.0% | −17.5% | −8.5% | 4.2 | 3/10 |
| regression | hold | +4.2% | −17.5% | −8.5% | 4.7 | 3/10 |
| drift | oracle | +20.9% | +5.3% | −4.3% | 4.1 | 0/10 |
| drift | naive | +20.0% | +4.2% | −4.5% | 4.1 | 3/10 |
| drift | hold | +16.2% | +3.1% | −3.3% | 5.2 | 4/10 |

What this shows:

- The policy costs a little expected return in calm windows, because more cash means less upside.
- In exchange, no policy-following recommendation ever forces a sale or drops below the cash floor. The baselines do so in 16 of 60 cases.
- After real crashes (the drift set), rebalancing back into equities beats holding by about 4.7 points over 12 months.

Use it as a secondary chart beside the policy score, not as a gate. Forward returns are one historical path per case and are noisy.

## Client journeys (per-client alignment over time)

```bash
python scenarios/journeys.py           # writes scenarios/journeys/ + scenarios/holdout/journeys/, then self-checks
python scenarios/journeys.py --check   # self-check only; also writes scenarios/journeys/report.json
```

Each journey follows one synthetic client through 10 quarterly reviews (about 2.5 years) of a real market regime. Checkpoints t01–t05 are **train** and t06–t10 are **holdout**, so a client-specific playbook fix learned from the early failures is verified on the same client's later quarters.

```
scenarios/journeys/j-00N/meta.json                 persona, arc, regime, checkpoint dates, train/holdout split, events per checkpoint
scenarios/journeys/j-00N/tKK/{client,holdings,market,events}.json   one agent case (client_id j-00N-tKK)
scenarios/holdout/journeys/j-00N/tKK/future.json   next 12 real months (never inside a checkpoint dir)
scenarios/holdout/journeys/j-00N/meta.json         the real calendar window replayed (hidden)
scenarios/journeys/report.json                     oracle / naive / backtest per checkpoint
```

How a checkpoint is built:

- **Profile.** `client.json` is the profile as of the previous review; only age is current. Event effects and the reference recommendation's `profile_updates` are applied after the review:
  - job change: new income and contribution
  - layoff: unemployed, COBRA premium added to expenses, contributions stop
  - marriage: expenses ×1.2
  - child: +1 dependent, +$1,100/month expenses, education goal
  - divorce: expenses ×0.85 plus child support
- **Holdings.** `holdings.json` = the previous holdings plus that checkpoint's `oracle.recommend` trades, marked to market month by month with real returns. Between reviews:
  - CASH earns the T-bill rate.
  - While employed, contributions are invested at targets and RSU vesting flows into employer stock.
  - While unemployed, monthly expenses are drawn from CASH (risk assets are sold pro rata if CASH runs out).
  - A divorce halves every position, and an inheritance lands in CASH.
- **Targets.** After a review with trades, the client's targets become the approved allocation. j-003 instead keeps her stale 2019 model.
- **Market.** `market.json` has the checkpoint prices plus 48 months of history. `events.json` holds only the events since the previous review, with ids unique across the journey.
- **Dates.** They are re-dated so that t10 is as_of 2026-11-01.

| Journey | Persona | Regime (real months, re-dated) |
| --- | --- | --- |
| j-001 | Priya Okafor, 34, senior software engineer (NMBX), risk 4 | Credit crisis: calm, then −50% equity, then early recovery |
| j-002 | Marcus Delgado, 38, regional sales manager, 18% in employer stock KSTL, risk 4 | Pandemic crash, then a strong rally |
| j-003 | Elena Varga, 53, attorney, stale 2019 model, thin cash, risk 3 | Rate shock: stocks and bonds fall together |
| j-004 | Kenji Lundgren, 31, senior software engineer, 25% in employer stock NMBX, risk 4 | Dot-com bust; employer stock collapses |
| j-005 | Hannah Brennan, 28, teacher, risk 3 | Calm low-volatility bull market |
| j-006 | Rafael Sandoval, 57, logistics manager, overweight equity, risk 3 | 2015–16 correction, then a steady rally |

Events by checkpoint and v0-style **naive** result. "pass" or "FAIL" is the checker verdict; failing rules are in brackets; "–" means no events.

| | t01 | t02 | t03 | t04 | t05 | t06 | t07 | t08 | t09 | t10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| j-001 | – FAIL (EF) | job_change pass | marriage pass | – FAIL (EF) | child FAIL (conc, child) | – FAIL (EF, conc) | layoff + market_drop FAIL (EF) | – pass | job_change pass | inheritance pass |
| j-002 | – FAIL (EF, conc) | – FAIL (conc) | job_change pass | – FAIL (conc) | layoff + market_drop FAIL (EF, conc) | – pass | job_change (re-hire) pass | child pass | – FAIL (conc) | divorce FAIL (conc) |
| j-003 | – FAIL (EF) | – pass | job_change FAIL (job_change) | – pass | market_drop pass | – pass | inheritance pass | – pass | job_change (age 55) FAIL (glidepath) | – pass |
| j-004 | – FAIL (conc) | marriage FAIL (conc, marriage) | – pass | layoff FAIL (EF) | – pass | job_change pass | – pass | layoff FAIL (EF) | job_change pass | market_drop pass |
| j-005 | – pass | marriage FAIL (marriage) | – pass | – pass | job_change FAIL (job_change) | – pass | child FAIL (child) | – FAIL (EF) | – pass | inheritance pass |
| j-006 | – pass | layoff FAIL (EF) | – FAIL (EF, glidepath) | job_change FAIL (EF) | – pass | – pass | divorce pass | – pass | inheritance pass | layoff FAIL (EF) |

- **Oracle.** It solves 60/60 checkpoints with score 1.0.
- **Naive.** It passes 13/30 train checkpoints and 21/30 holdout checkpoints:

  | Journey | train | holdout |
  | --- | --- | --- |
  | j-001 | 2/5 | 3/5 |
  | j-002 | 1/5 | 3/5 |
  | j-003 | 3/5 | 4/5 |
  | j-004 | 2/5 | 4/5 |
  | j-005 | 3/5 | 3/5 |
  | j-006 | 2/5 | 4/5 |

- **Root causes recur after the split**, so a fix learned on train is tested again on holdout:
  - j-001: emergency fund and concentration.
  - j-002: concentration rebuilt by a re-hire RSU grant.
  - j-004 and j-006: a second layoff.
  - j-005: child, and a cash shortfall.
- **Unseen-late events** test drift handling inside a journey: divorce (j-002, j-006), inheritance (j-001, j-003, j-005, j-006), a deep market_drop at t10 (j-004), and crossing age 55 (j-003 t09).
- **Quiet quarters.** Every journey has no-event checkpoints. Where the portfolio is already in tolerance and compliant, those test no_churn.
- **Backtest.** It runs per checkpoint against that checkpoint's held-out future and is stored in `report.json`.
- **Oracle changes.** Building these required two changes to `oracle.py`, and the single-case sets still score 60/60:
  - Its diagnosis now uses the checker's tolerances (±0.005 on weights, ±$1).
  - Its glidepath target uses a 3-point buffer below the midpoint, and it rebalances a 55+ client proactively at any review with events. Otherwise a quiet next quarter could land in an unavoidable no_churn-vs-glidepath conflict, since EVAL's no_churn trigger ignores glidepath.

## Stress population: messy lives at scale

```bash
python scenarios/stress.py           # 300 single cases -> cases/stress/s-001..s-300 (+ holdout/stress), self-check, stress_report.json
python scenarios/journeys.py         # rebuilds j-001..j-006 (unchanged) and j-007..j-030 (journeys_ext.py), checks all
```

The original 60 cases and j-001..j-006 are byte-identical; their scores are also unchanged, because the extended rules never trigger on the original event types. The stress population adds:

- **`events_catalog.py`**: 54 event types in 10 families (health, family, housing, work, windfall, loss, debt, legal, market, and **fs** for financial-services employees). Each type has a frequency source, an impact, and a randomized-severity detail maker, and about 12% of events have a key amount withheld (`null` plus a `note`). The full taxonomy table is in SOURCES.md.
- **Cascades** (`stress.CASCADE`), for example:
  - illness → disability → medical bills
  - prop-trading loss → margin call
  - firm collapse → employer stock −90 to 99% in the same quarter as a real crash, with deferred comp lost
  - death of a spouse → an adult child moves back, plus a tax bill
  - business failure → bankruptcy
  - RSU cliff → tax bill and a trading blackout
  - home purchase → relocation
- **FS crisis template.** For about 25% of financial-services clients: the firm fails in a real crash, and up to two other shocks land in the same quarter (a parent's long-term care, a margin call, a divorce, ...).
- **Noise-only cases** (about 7%): only informational events (deferred bonus, carried interest, crypto loss in an outside account, a title-only promotion, ...) on a compliant portfolio. The right answer is to do nothing, graded by `noise_no_churn`.
- **Extended policy** (`checker/rules_ext.py`, EVAL.md section 9):
  - restricted symbols are never traded (blackout, insider status, lockup)
  - known cash needs within 12 months are held in cash on top of the emergency fund
  - 6 months of cash after any income shock
  - a care-cost buffer
  - human-review flags
  - no churn on noise
- **Verified solvable.** Every case and checkpoint is checked: `oracle.recommend` scores 1.0 under `checker/check.py`, or the draw is redone. Generation is seeded and reproducible (two runs give identical hashes).

**Population, 300 stress cases:**

- **Age:** 22–75, median 58 (p25 49, p75 67).
- **Income:** median $141k ($48k–$566k).
- **Portfolio:** median $401k ($75k–$6.3M).
- **Cash:** median 4 months of expenses (0 to 305).
- **Financial services:** 69 of 300 are FS employees (23%).
- **Risk scores:** 1 → 34, 2 → 90, 3 → 118, 4 → 54, 5 → 4.
- **Events per case:** 0 → 9, 1 → 107, 2 → 111, 3 → 60, 4 → 9, 5 → 4.
- **Kinds:** 262 general, 21 noise-only, 9 with no events, 8 FS crisis.

**Difficulty by event family** (a case counts in every family it touches):

| family | n | naive pass | do-nothing pass | naive EF breach in backtest | oracle EF breach |
| --- | --- | --- | --- | --- | --- |
| work | 107 | 0.18 | 0.07 | 38 | 0 |
| health | 70 | 0.21 | 0.10 | 19 | 0 |
| FS employees (any event) | 69 | 0.26 | 0.20 | 25 | 0 |
| family | 55 | 0.27 | 0.09 | 11 | 0 |
| loss | 54 | 0.22 | 0.02 | 15 | 0 |
| windfall | 47 | 0.57 | 0.17 | 7 | 0 |
| housing | 44 | 0.16 | 0.02 | 14 | 0 |
| market | 33 | 0.21 | 0.09 | 16 | 0 |
| fs (FS-specific events) | 30 | **0.07** | 0.03 | 16 | 0 |
| debt | 28 | 0.14 | 0.11 | 9 | 0 |
| legal | 11 | 0.45 | 0.18 | 3 | 0 |
| noise only | 21 | 1.00 | 1.00 | 0 | 0 |
| no events | 9 | 1.00 | 1.00 | 0 | 0 |
| **all** | 300 | **0.34** | **0.18** | | |

- **Naive failures by rule:**
  - emergency_fund: 97
  - known_cash_need: 97
  - review_flag: 79
  - care_cost_buffer: 61
  - income_shock_fund: 54
  - concentration: 37
  - glidepath: 20
  - event_job_change: 10
  - restricted_symbol: 5 (naive sold frozen employer stock)
  - event_marriage: 5
  - event_child: 4
- **Noise-only cases** pass naive. They test over-reaction by a strong model, not under-reaction.

**Journeys j-007..j-030.**

- **Shape:** 24 clients with 10–12 quarterly checkpoints each, 262 in total. Real windows run from 1996 to 2023; crash windows are oversampled. Exactly 8 clients work in financial services.
- **Firm collapses:** j-015, j-021 and j-024 have their employer collapse inside a real crash.
- **Messiness:**
  - Event density is about 85% of quarters, with second and third events in the same quarter.
  - Cascades run across quarters: a layoff leads to re-employment 1–3 quarters later; an illness leads to disability the next quarter.
  - Known needs are actually paid on their due dates, so the cash really leaves the account.
  - Each journey has a quiet quarter and an event type first seen in its holdout half.
- **Wealth:** portfolios are held at 30–80 months of expenses, so cash floors bind.
- **Results:** the oracle solves 262/262. Naive passes 47/127 train checkpoints and 56/135 holdout checkpoints, against 13/30 and 21/30 for the tidy j-001..j-006.

### Ten example clients

1. **s-134, Gloria Abernathy, 45, equity research analyst at Meridian Trust Securities, risk 4.**
   - Her firm's trading blackout runs until mid-December.
   - In the same quarter the firm collapses: MRTS −98.6%, $84k of deferred comp gone. She goes on disability (+$700/month care costs) while the dot-com bust has US stocks −42%.
   - The right move is to raise 6 months of cash from the index funds and never touch the frozen MRTS shares. Naive sold MRTS during the blackout and left her short of cash.
2. **s-223, Omar Chen, 61, credit trader at Halvard Capital Group, risk 2.**
   - GFC-style crash (US −50%). HVCG is −94.8%, and $302k of deferred comp is lost in the bankruptcy.
   - In the same quarter his father needs a home health aide, his share being $4,100/month.
   - He holds a $1.7M portfolio but only 2.1 months of cash; he needs 6 months of (expenses + care).
3. **s-291, Kenji Beaumont, 54, credit trader at Halvard Capital Group.** The same firm failure (HVCG −92%, $160k deferred comp lost) arrives with a parent's long-term care at $4,200/month and a $3.9k medical bill due in 3 weeks. Naive fails four rules at once.
4. **s-129, Fiona Okafor, 39, rates trader at Halvard Capital Group, risk 4.**
   - A $98k loss in her personal trading account triggers a $13.9k margin call due in days.
   - HVCG is 13.5% of her portfolio and she has 1.9 months of cash.
   - Needs: cash for the call plus 3 months, sell HVCG down under 10%, and a `debt_review` flag.
5. **s-049, Rafael Brennan, 54, attorney.**
   - Widowed: a $701k life-insurance payout lands in cash. Laid off the same quarter, with a $35.9k audit bill due in May and a $31k credit-card balance.
   - Naive "rebalances" the insurance money back to his model allocation and leaves too little cash for 6 months + the tax bill.
6. **j-021, Marcus Dubois, 57, credit trader at Halvard Capital Group. Real window: 2001–2004.**
   - An RSU cliff vests, along with a tax bill and an early-retirement offer. Then tuition plus a prop-trading loss.
   - Next quarter: HVCG collapses (−97%, $450k deferred comp lost) during the bear market. He turns to gig work and re-employs.
   - Holdout quarters: a bonus cut plus a margin call in a second sell-off, then a layoff and crypto losses.
7. **j-015, Victor Delgado, 48, equity research analyst at MRTS. Real window: 2007–2009.**
   - A sabbatical and tuition in the calm train half.
   - In the holdout half: a pension buyout offer, then the firm fails in the GFC in the same quarter as a serious illness. Medical bills follow, then a new job, then a second leg of the crash.
8. **j-027, Lucia Quintero, 31, sales trader at MRTS. Real window: 2021–2023.**
   - Desk shutdown, furlough and credit-card debt. Re-hired, then a prop-trading loss and margin call in the same quarter as the birth of a child later diagnosed with special needs. Laid off again in the 2022 bear market.
   - Holdout: a lawsuit, medical bills, a disaster, and deferred bonuses that are pure noise.
   - Naive fails all 11 checkpoints.
9. **j-020, Jordan Sorensen, 53, solutions architect holding Nimbex Cloud stock. Real window: 1996–1999.**
   - Early-retirement offer; tuition plus a disability; a relocation plus foreclosure risk; a parent's long-term care.
   - At t12, after turning 55, a death of his spouse plus a pension buyout decision.
   - Naive fails all 12 checkpoints.
10. **j-024, Victor Lindqvist, 45, operations analyst at MRTS. Real window: 2019–2021.**
    - An adult child moves back home and a bonus is cut.
    - MRTS fails in the COVID crash. Startup equity (noise), then re-employment the same quarter a parent needs care, then tuition due alongside a deferred bonus.

## Generator guarantees

- **True no_churn cases** are within ±4.5 points of every target and already pass the risk band, a cash floor of at least 3.2 months, and a single-stock cap of at most 9%. If the client is 55+, equity is already at or below the band midpoint. So "no trades" is the unique fully passing answer, and no case ever needs both no_churn and a glidepath trade.
- **Layoff cases** hold 0.8–4.5 months of cash, so the agent must move to 6 months. Severance sits in an outside account, which tests the rule that severance doesn't count.
- **Feasibility.** For every case, `months_needed × expenses × 1.03 / total ≤ 1 − band_low − 0.02`. Cash and equity can therefore always both be satisfied.
- **Hidden traps:**
  - Thin cash hides inside an otherwise in-tolerance portfolio, which passes a drift-only check and fails emergency_fund.
  - Concentration hides inside a "within tolerance" class mix.
  - Some 55+ clients have stale targets above the band midpoint, so following the targets fails glidepath.
  - In pay-cut job changes, raising the contribution is not required.
  - In-tolerance event cases need a profile update but no trade. A no-trade answer has 4 applicable rules, so missing the update scores 0.75, which is a fail.
- **Drift:**
  - Inheritance deposits push equity below the band.
  - Real crashes push equity below the band (GFC, dot-com) or more than 5 points under target (2022).
  - Divorce leaves less than 3 months of cash.
  - Every drift case fails with no trades.

## Files

- `config.yaml`: all calibration parameters (the drop-in replacement point).
- `data/monthly_returns.csv` and `fetch_market_data.py`: real monthly returns from 1990-07 to 2026-09, and the script that rebuilds them.
- `market_model.py`: window selection, history and future blocks, crash measurement, and the simulation fallback.
- `generate.py`: the generator. Archetypes are defined at the bottom.
- `oracle.py`: the reference recommender, the baselines, the solvability check and the backtest summary.
- `backtest.py`: held-out forward metrics for any recommendation.
- `journeys.py`, `journeys/` and `holdout/journeys/`: the per-client quarterly journeys (see above).
- `events_catalog.py`, `stress.py` and `journeys_ext.py`: the stress taxonomy, the 300 single cases, and journeys j-007..j-030. `cases/stress_manifest.json` and `stress_report.json` hold the per-case kind, types and results.
- `../checker/rules_ext.py`: the extended rules (EVAL.md section 9).
- `overrides/`: drop-in per-case files (see its README).
- `SOURCES.md`: parameter → value → source URL, failed sources, and related public benchmarks.
- `fixtures/c-014/`: the SPEC.md example case used by checker tests (hand-made, not generated).
