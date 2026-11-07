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
- `overrides/`: drop-in per-case files (see its README).
- `SOURCES.md`: parameter → value → source URL, failed sources, and related public benchmarks.
- `fixtures/c-014/`: the SPEC.md example case used by checker tests (hand-made, not generated).
