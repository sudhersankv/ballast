# ballast. scenarios

These are synthetic US retail-investor households for the portfolio agent. Their profiles, holdings, market data and life events are calibrated to public data; every parameter and its source is listed in [SOURCES.md](SOURCES.md). All names, employers and tickers (`HLXR`, `NMBX`, `KSTL`) are invented.

## Regenerate

```bash
python scenarios/generate.py      # rewrites scenarios/cases/{practice,test,regression,drift}/ + manifest.json
python scenarios/oracle.py        # solvability self-check + baseline difficulty (uses checker/check.py)
python scenarios/oracle.py --case scenarios/cases/test/c-024   # one oracle recommendation + score
python scenarios/oracle.py --write                             # oracle outputs -> scenarios/oracle_out/
```

- The generator uses the stdlib only and is deterministic. Each case draws from `random.Random(SET_SEED*1000 + index)`, with seeds `practice=1001, test=2002, regression=3003, drift=4004`. A rerun gives byte-identical files.
- Weights and post-trade values reuse `agent/tools/portfolio.py`, so the generator, agent and checker share one set of math.
- Every case has `client.json`, `holdings.json`, `market.json` and `events.json`, laid out exactly as in SPEC.md. `client.json` adds realism fields that the checker ignores: `name`, `state`, `occupation`, `employment_status`, `marital_status`, `employer` and `notes`.
- In every position, `value = units × price` (to the cent). Each `targets` value falls inside the EVAL.md risk band for the client's `risk_score`.
- `cases/manifest.json` holds the archetype and tags for each case, for dashboards and analysis. It sits outside the case folders, so the agent never sees it. Oracle outputs are never written into case folders either.

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
| market_drop | – | – | – | 3 (2020-style −33.9%, 2022-style −25.4% with bonds −13%, −22% with concentration) |
| combos | – | – | – | market_drop+layoff, inheritance+child, divorce+job_change |

In practice and test, 6 of 20 cases (30%) are plain no-event cases (the first three rows). The age-55+ glidepath rows also have no events, but they count toward the "age 55+" category. The rest are split across layoff, job change, marriage, child and age 55+, matching SPEC.md. Archetype order is shuffled within each set, so case ids carry no signal about the archetype.

## Distributions (all 60 cases)

| | min | p25 | median | p75 | max |
| --- | --- | --- | --- | --- | --- |
| age | 26 | 38 | 46 | 53 | 70 |
| annual income | $58.5k | $107k | $151k | $220k | $420k |
| monthly expenses | $4.6k | $6.7k | $8.3k | $10.7k | $17.2k |
| portfolio total | $40k | $191k | $296k | $474k | $1.26M |
| cash, in months of expenses | 1.3 | 3.4 | 4.2 | 5.5 | 61 (post-inheritance) |
| severance (weeks) | 2 | 5 | 10 | 11 | 18 |
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

The generator guarantees these properties:

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
  - Inheritance deposits push equity below the band, so parking the windfall in cash fails risk_band.
  - Market drops push equity below the band. Single stocks fall harder.
  - Divorce leaves less than 3 months of cash.
  - Every drift case fails with no trades, so a playbook that learned "don't churn" without learning these events goes red.

## Files

- `generate.py`: the generator. Archetypes are defined at the bottom and calibration tables at the top.
- `oracle.py`: the reference recommender, the baselines and the solvability check.
- `SOURCES.md`: parameter → value → source URL, failed sources, and related public benchmarks.
- `fixtures/c-014/`: the SPEC.md example case used by checker tests (hand-made, not generated).
