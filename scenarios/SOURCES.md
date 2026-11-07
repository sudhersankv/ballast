# Scenario calibration sources

Each generator parameter, the value used, and where it comes from. Researched 2026-11-07.
"Assumption" marks a value with no direct public source, or one where the source did not load. All clients, employers and tickers are synthetic. Treat the numbers as plausible ranges for a demo, not a statistically representative sample.

## Household profile

| Parameter (generate.py) | Value used | Source | Notes |
| --- | --- | --- | --- |
| `SCF_MEDIAN_INCOME_K` median family income by age | <35: 60.5k, 35–44: 85.9k, 45–54: 91.9k, 55–64: 81.9k, 65–74: 60.9k, 75+: 49.1k (2022 $) | Fed, *Changes in U.S. Family Finances from 2019 to 2022* (SCF bulletin), Table 1. https://www.federalreserve.gov/publications/files/scf23.pdf | Text extracted from the PDF. All-family median 70.3k, mean 141.9k. |
| `INVESTOR_INCOME_MULT` | 1.45× | SCF bulletin Box 2: stock ownership is 34% in the bottom half of usual income, 78% in the upper-middle group and 95% in the top decile (same URL) | **Assumption** on the size of the multiplier. Clients who use a portfolio agent skew toward upper-middle income. The resulting median income is about $150k. |
| `INFLATE_2022_2026` | 1.14× | **Assumption**: cumulative CPI-U, 2022 to 2026. | |
| Income spread | lognormal, σ = 0.42, clamped to 48k–420k | **Assumption** | The SCF mean/median ratio is about 2. We clamp the tails. |
| `CE_QUINTILES` (spending as a share of income) | Q2 46.1k→51.4k, Q3 78.6k→69.0k, Q4 126.3k→92.3k, Q5 286.2k→159.5k. Log-interpolated, then multiplied by U(0.88, 1.08). | BLS Consumer Expenditure Survey 2025 news release. https://www.bls.gov/news.release/cesan.htm | Also cross-checked against the 2023 quintile means: 33.8k, 48.9k, 65.5k, 87.9k, 150.1k (https://www.bls.gov/news.release/archives/cesan_09252024.htm, via search summary). CE spending includes pension contributions, so `monthly_expenses` slightly overstates living costs. That is conservative for the emergency fund. |
| `SCF_MEDIAN_RETIRE_K` portfolio size by age | <35: 18.9k, 35–44: 45k, 45–54: 133k, 55–64: 185k, 65–74: 200k, 75+: 130k (conditional medians) | Secondary summaries of SCF 2022: https://www.fool.com/retirement/2024/08/28/average-retirement-savings-for-americans-by-age , https://www.nerdwallet.com/article/investing/the-average-retirement-savings-by-age-and-why-you-need-more . The bulletin gives the all-age conditional median of $86,900 and mean of $334,000 (Fed URL above). | The 35–44 value is from a secondary source and was not checked against the Fed tables. We multiply by 1.6 for taxable accounts, by (income ratio)^0.9 and by a lognormal with σ = 0.5. Totals are clamped to 40k–2.5M. The resulting median is about $295k. |
| Stock ownership (direct + indirect) | justifies "every client holds funds" | SCF 2022 Box 2: 58% of families hold stock directly or indirectly; 21% hold stock directly (Fed URL above) | |
| `cash_months` (cash held in the portfolio) | default U(3.4, 6.5) months. Stressed archetypes: 0.8–4.5 months. | Fed SHED 2023: 63% of adults could cover a $400 expense with cash or its equivalent. https://www.federalreserve.gov/publications/2024-economic-well-being-of-us-households-in-2023-executive-summary.htm . SCF 2022: median transaction-account balance $8,000 (Fed bulletin). | Thin cash is common in real life. Stressed cases deliberately oversample it. |
| Risk score by age (`RISK_WEIGHTS`) | younger households weighted toward 3–5, 65+ toward 1–3 | Vanguard target-date glide path: 90% equity at the start, about 50% at retirement, 30% by about age 72. https://workplace.vanguard.com/insights-and-research/perspective/tdf-glide-path-essentials-setting-the-right-starting-point.html , https://workplace.vanguard.com/investment/strategies/tdf-glide-path.html | **Assumption** for the exact weights. A risk score of 5 is also forced on two archetypes so that every band appears. |
| Model allocations (`targets`) | equity: risk 1 = .20, 2 = .40/.45, 3 = .55–.65, 4 = .75/.80, 5 = .88/.90. Age 55+ uses the low half of the band. The cash sleeve is a round number covering at least 3.5 months of expenses (or the actual cash share for in-tolerance cases). | Glide-path sources above. The bands are from EVAL.md. | Every target falls inside its EVAL band. The "stale" 55+ targets are deliberately in the upper half, standing for a model portfolio last set in 2019. |
| International share of equity | 0 for 20% of clients, else U(15%, 40%) | Vanguard TDFs hold about 40% of equity abroad (glide-path page above). Retail investors show home bias. | **Assumption** |
| `monthly_contribution` | 6–16% of income ÷ 12. Retirees: 0. | Vanguard *How America Saves 2026*: total deferral (employee + employer) about 12%. https://workplace.vanguard.com/content/dam/inst/iig-transformation/insights/pdf/has/how-america-saves-2026.pdf | The PDF was not opened. The figure comes from search-result summaries. |
| Employer single-stock concentration | concentration archetypes hold 12–35% in one stock. About 30% of other clients hold a "fun money" stock at 2–7.5%. | Vanguard HAS 2026: about 2% of participants hold more than 20% in company stock, and 8% of plans offer it (InvestmentNews summary: https://www.investmentnews.com/retirement-planning/auto-enrollment-retirement-plan-adoption-rates-hit-new-highs-in-2025-says-vanguard/267032). Direct stock ownership: 21% of families (SCF 2022). | Concentration is **deliberately oversampled** relative to the population. It is the stress case the policy exists for. |
| Names, states, occupations | random first/last pairs from a 40×36 list, states weighted roughly by population, occupation picked by income range | **Assumption** | All synthetic. Any match with a real person is coincidence. |

## Life events

| Event | Value used | Source |
| --- | --- | --- |
| Layoff incidence (motivation for share) | about 1.0–1.1% of employment per month; 20.2M layoffs in 2024 | BLS JOLTS annual 2024: https://www.bls.gov/news.release/archives/jolts_03112025.htm . The FRED series JTSLDR also covers it. |
| Re-employment after displacement | 65.7% of long-tenured displaced workers were re-employed by Jan 2024 | BLS Displaced Worker Survey: https://www.bls.gov/opub/ted/2024/65-7-percent-of-long-tenured-displaced-workers-were-reemployed-in-january-2024.htm , https://www.bls.gov/news.release/disp.nr0.htm |
| Severance formula | tenure U(2, 14) years × {1, 1, 1, 1.5, 2} weeks per year, minimum 2 weeks, maximum 40 | Most common formula is 1 week per year of service (57% of employers), then 2 weeks (24%), per ASE survey summaries: https://sbam.org/?p=26537 , https://www.plansponsor.com/two-weeks-severance-pay-prevalent . Manchester survey average: 1.4–1.7 weeks per year (https://www.workforce.com/news/how-much-severance-to-pay). The survey sources are dated (1998–2024). |
| COBRA premium in layoff details | single coverage $690–820/month, family $1,490–2,130/month | **Assumption** based on KFF Employer Health Benefits Survey 2024 (single about $8,951/yr, family about $25,572/yr): https://www.kff.org/health-costs/report/2024-employer-health-benefits-survey/ . Not fetched this session. Values recalled. |
| Job change raise | new_income = income × U(1.10, 1.32). Pay-cut archetype: × U(0.80, 0.93). | Atlanta Fed Wage Growth Tracker: median switcher and stayer wage growth was about 4% in 2025 (stayers led). https://fred.stlouisfed.org/series/FRBATLWGT12MMUMHWGJST , https://news.bloombergtax.com/human-resources-news/quitting-your-job-wont-help-you-get-paid-more-money-right-now . Our raises **deliberately exceed the median**: they model a promotion-style move that the job_change rule is meant to test. Pay cuts are included so the agent must check direction. |
| Marriage | ages 26–42. Spouse income is lognormal with median $80k. | CDC/NCHS: marriage rate 6.2 per 1,000 in 2022 (https://www.cdc.gov/nchs/blog/posts/2024/03/marriages-in-the-u-s-in-2022-returned-to-pre-pandemic-levels.html). Median age at first marriage is about 30.8 for men and 28.4–28.8 for women (https://www.bgsu.edu/ncfmr/resources/data/family-profiles/fp-26-01.html). Spouse income is an **assumption**. |
| Child | parent ages 27–41. 8% adoptions. | CDC/NCHS: mean age at first birth is 27.5 (2023), and the birth rate peaks at ages 30–34. https://www.cdc.gov/nchs/blog/posts/2025/06/the-rising-age-of-motherhood-in-the-united-states.html |
| Divorce (drift only) | ages 35–54. Holdings are already post-split (the transfer equals 80–100% of the remaining portfolio, i.e. about a 50/50 split). Expenses ×0.80–0.95. Cash 1.2–3 months. | CDC/NCHS divorce rate: 2.4 per 1,000 (2022) and 2.3 (2024): https://www.cdc.gov/nchs/data/dvs/marriage-divorce/national-marriage-divorce-rates-00-24.pdf . Median duration of marriage at first divorce is about 13 years (NCFMR): https://www.bgsu.edu/ncfmr/resources/data/family-profiles/FP-25-22.html . The asset-split and expense ratios are **assumptions**. |
| Inheritance (drift only) | 0.35–0.9× portfolio, or 0.9–1.4× for the "large" archetype. Paid in cash and deposited to `CASH`. | About 1 in 4 families have ever received an inheritance. The recipient median is about $69k (SCF 2022) to $124k (SCF 2025, which includes trusts and gifts). Boldin analysis of SCF: https://www.boldin.com/retirement/average-inheritance-how-much-are-retirees-leaving-to-heirs/ ; Wharton Budget Model: https://budgetmodel.wharton.upenn.edu/issues/2021/12/17/inheritances-by-race . Our amounts ($82k–$530k in the current draw) are at or **above the recipient median on purpose**, so the windfall pushes equity below the risk band. |
| Market drop (drift only) | The drop is the **real** month-end peak-to-trough path of the replayed window (see "Market history" below). In the current draw: GFC to Feb 2009, US −50.3% / intl −55.9% / bonds +15.6%. Dot-com to Sep 2002, US −42.1%. 2022 to Sep 2022, US −24.8% / bonds −10.1%. COVID to Mar 2020, US −20.2% at monthly closes. Prices in market.json are lowered by the same amount and holdings are revalued at the same units. | Cross-check against daily-close S&P 500 peak to trough: 2020 −33.9%, 2022 −25.4%, 2008 about −57%. https://or.indexologyblog.com/2023/01/09/do-friendly-bears-exist/ , https://pro.stockalarm.io/blog/what-is-a-bear-market , https://www.benzinga.com/z/44669291 . Monthly closes miss intra-month lows, which is why COVID shows −20% instead of −34%. |

## Market history and held-out window

| Parameter (config.yaml `market`) | Value used | Source |
| --- | --- | --- |
| `returns_csv`, US_EQ | CRSP US value-weighted market total return (Fama-French Mkt-RF + RF), monthly 1990-07..2026-09. A proxy for S&P 500 TR: 11.1% CAGR, 15.1% vol. Calendar checks: 2008 −36.7%, 2022 −19.9%, 2023 +26.7%. | Kenneth R. French Data Library, *F-F Research Data Factors*. https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html (file built from the 202609 CRSP database) |
| INTL_EQ | Developed ex-US market total return in USD (Fama-French), 1990-07 onward. A proxy for MSCI EAFE: 6.3% CAGR, 16.3% vol, correlation with US 0.77. 2008 −42.8%. | Same library, *Developed ex US 3 Factors* |
| BOND | Modeled from FRED GS10 (10-year Treasury, monthly average yield): `r = y[t-1]/12 − D·Δy`, with D = 6.0 to match the US Aggregate duration. 4.8% CAGR, 4.6% vol. 2008 +14.5%, 2022 −9.8% (the real Agg was about −13%; this proxy has no credit spread or convexity). | https://fred.stlouisfed.org/series/GS10 . FRED's daily equity and ICE bond total-return series are truncated by licensing (10 years and 3 years), so they could not be used. |
| CASH | 1-month T-bill return (Fama-French RF; ICE BofA 1-month T-bill from 2024-06) | French library |
| Replay design | Each case takes a contiguous 48-month window of real returns, re-dated to end at as_of (2026-10-31). The 12 months that **actually followed** become `future.json`. Non-drift windows are drawn uniformly from window ends between 1994-06 and 2025-09, excluding any window whose last 6 months fell more than 12%. Market-drop cases end at real troughs: 2009-02, 2002-09, 2020-03, 2022-09. | Design choice. The real window labels sit only in `holdout/*/future.json` (`real_window`) and the manifest, never in a case directory, so the agent cannot look up "what happened next". |
| Single stocks (HLXR, NMBX, KSTL) | **Simulated**: `rf + β(US − rf) + ε`, with β = 1.6 / 1.4 / 1.1 and annual idiosyncratic vol 45% / 35% / 25% | **Assumption**. The betas and idiosyncratic vols are typical of biotech, software and freight names. |
| Fallback when the CSV is missing | Multivariate normal monthly returns. Annual μ: US 10%, intl 7%, bonds 4.5%, cash 3%. σ: 15.5%, 16.5%, 4.5%, 0.6%. US–intl ρ = 0.77. | Calibrated to the CSV statistics above. Output is labelled `"source": "simulated"`. |
| `backtest.unemployed_draw_months` | 6 | **Assumption**. BLS DWS shows about a third of long-tenured displaced workers still not re-employed at survey time (URL above). |

## Client journeys (journeys.py)

| Parameter | Value | Source |
| --- | --- | --- |
| Real regime windows (t01 history end → t10) | j-001 2007-06 → 2009-09. j-002 2019-03 → 2021-06. j-003 2021-03 → 2023-06. j-004 2000-03 → 2002-06. j-005 2013-06 → 2015-09. j-006 2015-06 → 2017-09. | `data/monthly_returns.csv` (French library, FRED GS10). See "Market history" above. |
| Employer-stock idiosyncratic shocks (j-004 NMBX) | −35% in 2000-12 and −40% in 2001-06, on top of the β = 1.4 simulation | **Assumption**: scripted to mirror dot-com single-name collapses |
| Child cost | +$1,100/month expenses | **Assumption**. The USDA *Expenditures on Children by Families* (2015 report: about $12.9k/yr for middle-income two-parent households, https://www.usda.gov/media/blog/2017/01/13/cost-raising-child) inflated to 2026 is about $16k/yr. We use about 80% of that, since some costs are already in expenses. The report was not fetched in this session. |
| Marriage | expenses ×1.2 | **Assumption**: a second adult in the household, but shared housing |
| Divorce | half of every position transferred; expenses ×0.85 plus $900/month child support when there are dependents | **Assumption**: equal split under equitable distribution |
| Unemployed months | expenses drawn from CASH every month until a job_change event, plus the COBRA premium | Severance and COBRA rows above; BLS DWS |
| Contributions while employed | `monthly_contribution`, invested at targets every month. Re-employment resets it to 10% of the new income. | Vanguard HAS (above) |
| RSU vesting | j-001 $6k/qtr, j-002 $8k/qtr (a $16k/qtr sign-on grant after the re-hire), j-004 $7k/qtr | **Assumption**: typical tech or sales-manager equity grants |

## Event taxonomy (stress population; scenarios/events_catalog.py)

54 types in 10 families. The counts are occurrences in the 300 stress cases and in journeys j-007..j-030. Severity is randomized per event (see `make()` in the catalog), and about 12% of events have a key amount withheld (`null` plus a `note`).

| Type | Family | Frequency / anchor | Typical impact | Graded by | Stress n | Journey n | Source |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `credit_card_debt` | debt | $1.21T US card balances, Q2 2025 (NY Fed) | high-APR balance | review_flag (debt_review) | 21 | 12 | https://www.newyorkfed.org/newsevents/news/research/2025/20250805 |
| `margin_call` | debt | triggered by drawdowns in leveraged accounts | cash due within days | known_cash_need, review_flag (debt_review) | 5 | 5 | **assumption** (not fetched) |
| `student_loan_restart` | debt | federal repayment restarted Oct 2023 | monthly payment resumes | noise_no_churn | 2 | 1 | **assumption** (not fetched) |
| `adult_child_moves_back` | family | 18% of 25-34 year-olds live in a parent's home (Pew 2023) | household costs rise | care_cost_buffer | 16 | 9 | https://www.pewresearch.org/short-reads/2022/08/24/americans-more-likely-to-say-its-a-bad-thing-than-a-good-thing-that-more-young-adults-live-with-their-parents/ |
| `child` | family | twins 30.7 per 1,000 births (CDC 2023) | new dependent(s); education goal | event_child | 4 | 7 | https://www.cdc.gov/nchs/fastats/multiple.htm |
| `death_of_spouse` | family | widowhood rises sharply after 65; ~1 in 3 women 65+ widowed (Census) | loss of second income; life-insurance payout | income_shock_fund, review_flag (estate_review) | 13 | 4 | **assumption** (not fetched) |
| `divorce` | family | 2.3 per 1,000 (CDC 2024) | assets split; alimony/child support | (base rules) | 11 | 1 | https://www.cdc.gov/nchs/data/dvs/marriage-divorce/national-marriage-divorce-rates-00-24.pdf |
| `marriage` | family | 6.2 per 1,000 (CDC 2022) | joint profile | event_marriage | 5 | 3 | https://www.cdc.gov/nchs/data/dvs/marriage-divorce/national-marriage-divorce-rates-00-24.pdf |
| `tuition_due` | family | private nonprofit 4-yr published tuition $43,350 (College Board 2024-25) | large known payment within a year | known_cash_need | 12 | 12 | https://research.collegeboard.org/trends/college-pricing/highlights |
| `bonus_deferral` | fs | 40-60% of senior bank bonuses deferred up to 4 years (2016 Sec. 956 proposal) | most of the bonus vests later, often in employer stock | noise_no_churn | 6 | 4 | https://www.federalreserve.gov/SECRS/2016/November/20161110/R-1536/R-1536_072216_130464_572204174586_1.pdf |
| `carried_interest` | fs | PE/hedge-fund professionals | large illiquid future payout; not in this account | noise_no_churn | 1 | 0 | **assumption** (not fetched) |
| `deferred_comp_clawback` | fs | SEC Rule 10D-1 (2022) mandates no-fault clawback policies | unvested pay forfeited | review_flag (legal_review) | 5 | 1 | https://www.federalreserve.gov/SECRS/2016/November/20161110/R-1536/R-1536_072216_130464_572204174586_1.pdf |
| `desk_shutdown` | fs | desks closed in restructurings (e.g. 2008, 2023) | job ends; garden leave pay for a few months | income_shock_fund | 3 | 2 | **assumption** (not fetched) |
| `firm_collapse` | fs | Lehman 2008: employee RSUs worthless, deferred comp subordinated | employer stock -90%+, job and deferred comp gone | income_shock_fund | 10 | 3 | https://www.courthousenews.com/ex-lehman-employees-lose-ground-bankruptcy-case/ |
| `insider_status` | fs | pre-clearance required for covered persons at broker-dealers | every trade in employer stock needs pre-clearance; none granted | restricted_symbol | 0 | 1 | **assumption** (not fetched) |
| `prop_trading_loss` | fs | personal trading losses in outside accounts | loss outside this portfolio; may trigger a margin call | context only (base rules still apply) | 3 | 4 | **assumption** (not fetched) |
| `regulatory_ban` | fs | FINRA/SEC industry bars | barred from the industry for months/years | income_shock_fund, review_flag (legal_review) | 2 | 3 | **assumption** (not fetched) |
| `trading_blackout` | fs | quarterly insider-trading blackout windows are standard | employer stock cannot be traded until window opens | restricted_symbol | 5 | 1 | **assumption** (not fetched) |
| `disability` | health | 24% of 20-year-olds disabled before normal retirement age (SSA 2025) | income drops to 50-70% benefit; care costs | income_shock_fund, care_cost_buffer | 15 | 8 | https://www.ssa.gov/oact/NOTES/ran6/an2025-6.pdf |
| `medical_bill` | health | 41% of adults carry medical or dental debt (KFF 2023) | lump bill due within months | known_cash_need | 29 | 24 | https://www.kff.org/health-costs/issue-brief/the-burden-of-medical-debt-in-the-united-states/ |
| `parent_long_term_care` | health | 56-70% of people turning 65 will need LTC (ACL, 2023 study) | monthly cost share for a parent's care | care_cost_buffer | 18 | 11 | https://acl.gov/ltc/basic-needs/how-much-care-will-you-need |
| `serious_illness` | health | ~40% lifetime cancer risk; 1 in 4 workers disabled before 67 | out-of-pocket costs, reduced hours | care_cost_buffer | 25 | 9 | https://www.ssa.gov/oact/NOTES/ran6/an2025-6.pdf |
| `special_needs_diagnosis` | health | about 1 in 6 US children has a developmental disability (CDC) | therapy and care costs | care_cost_buffer | 1 | 2 | **assumption** (not fetched) |
| `disaster_damage` | housing | billion-dollar US disasters: ~20+/yr recently (NOAA) | uninsured repair cost | known_cash_need | 17 | 3 | **assumption** (not fetched) |
| `foreclosure_risk` | housing | ~0.3% of housing units with a foreclosure filing per year (ATTOM) | arrears due to cure default | known_cash_need, review_flag (debt_review) | 5 | 11 | **assumption** (not fetched) |
| `home_purchase` | housing | first-time buyers: median age 38, 9% down (NAR 2024) | down payment + closing costs due at closing | known_cash_need | 7 | 8 | https://www.nar.realtor/newsroom/first-time-home-buyers-shrink-to-historic-low-of-24-as-buyer-age-hits-record-high |
| `relocation` | housing | ~8% of Americans move each year (Census CPS) | moving costs; cost of living change | known_cash_need | 20 | 11 | **assumption** (not fetched) |
| `bankruptcy` | legal | 517,308 US filings in 2024 (US Courts) | court process; assets may be constrained | review_flag (legal_review) | 4 | 1 | https://www.uscourts.gov/news/2024/11/07/bankruptcy-filings-rise-16-percent |
| `lawsuit` | legal | personal liability suits | possible judgment; legal fees | review_flag (legal_review) | 6 | 4 | **assumption** (not fetched) |
| `legal_judgment` | legal | follows lost suits | amount due to court | known_cash_need, review_flag (legal_review) | 2 | 1 | **assumption** (not fetched) |
| `crypto_loss` | loss | 16-20% of Americans have used crypto (Pew) | loss in an outside exchange account | noise_no_churn | 22 | 11 | https://cointelegraph.com/news/pew-research-center-at-least-16-of-americans-have-owned-crypto |
| `fraud_loss` | loss | $12.5B reported fraud losses in 2024; investment scams $5.7B (FTC) | cash stolen from the account | review_flag (fraud_report) | 13 | 10 | https://www.ftc.gov/news-events/news/press-releases/2025/03/new-ftc-data-show-big-jump-reported-losses-fraud-125-billion-2024 |
| `tax_bill` | loss | underpayment common after RSU vesting / windfalls | tax due by a known date | known_cash_need | 27 | 13 | **assumption** (not fetched) |
| `market_drop` | market | real troughs 2002/2009/2020/2022 | equity prices fall | risk_band | 33 | 22 | see 'Market history' (French library / FRED GS10) |
| `business_sale` | windfall | owner exits; earnouts common | large cash proceeds + earnout | context only (base rules still apply) | 8 | 0 | **assumption** (not fetched) |
| `inheritance` | windfall | ~1 in 4 families ever inherit (SCF) | cash deposited | risk_band | 27 | 16 | https://www.boldin.com/retirement/average-inheritance-how-much-are-retirees-leaving-to-heirs/ |
| `lawsuit_settlement` | windfall | rare | settlement deposited | context only (base rules still apply) | 8 | 0 | **assumption** (not fetched) |
| `lottery_win` | windfall | rare | cash windfall after tax | context only (base rules still apply) | 6 | 1 | **assumption** (not fetched) |
| `annual_review` | work | routine HR review | no financial change | noise_no_churn | 8 | 0 | **assumption** (not fetched) |
| `bonus_cut` | work | finance bonuses fall with markets (comp tied to revenue) | variable comp down 30-100% | noise_no_churn | 2 | 3 | **assumption** (not fetched) |
| `business_failure` | work | about 1 in 5 new businesses fail in year one (BLS BED) | owner income stops | income_shock_fund | 6 | 4 | **assumption** (not fetched) |
| `early_retirement_offer` | work | common in corporate restructurings | decision needed; lump sum offered | review_flag (pension_election_review) | 2 | 3 | **assumption** (not fetched) |
| `furlough` | work | used widely in 2020; government shutdowns | unpaid weeks, return uncertain | income_shock_fund | 8 | 1 | **assumption** (not fetched) |
| `gig_income` | work | ~1 in 3 workers do some independent work (McKinsey 2022) | variable income; thicker buffer | income_shock_fund | 11 | 6 | **assumption** (not fetched) |
| `ipo_lockup` | work | lockups typically 180 days (Schwab) | employer shares cannot be sold until lockup ends | restricted_symbol | 3 | 0 | https://www.schwab.com/learn/story/what-is-ipo-lockup-period |
| `job_change` | work | Atlanta Fed: ~4% median wage growth; switchers vary widely | new income (up or down) | event_job_change | 24 | 26 | https://fred.stlouisfed.org/series/FRBATLWGT12MMUMHWGJST |
| `layoff` | work | ~1.1%/month layoff rate (BLS JOLTS) | income stops; severance outside the account | emergency_fund (6 mo) | 21 | 19 | https://www.bls.gov/news.release/archives/jolts_03112025.htm |
| `pay_cut` | work | common in downturns | salary reduced 5-20% | noise_no_churn | 12 | 5 | **assumption** (not fetched) |
| `pension_buyout_offer` | work | pension risk transfer offers to vested participants | lump sum vs annuity election | review_flag (pension_election_review) | 11 | 4 | **assumption** (not fetched) |
| `promotion_title_only` | work | title changes without pay change | no financial change | noise_no_churn | 7 | 0 | **assumption** (not fetched) |
| `retirement` | work | median US retirement age ~62 (various surveys) | salary stops; pension/SS start | context only (base rules still apply) | 4 | 2 | **assumption** (not fetched) |
| `rsu_cliff` | work | standard 1-year cliff then quarterly vesting | employer shares land in the account | context only (base rules still apply) | 3 | 1 | **assumption** (not fetched) |
| `sabbatical` | work | unpaid leave; employer-dependent | months without pay are a known cash need | known_cash_need | 4 | 5 | **assumption** (not fetched) |
| `startup_equity` | work | common in tech hiring | illiquid options, not in brokerage account | noise_no_churn | 22 | 9 | **assumption** (not fetched) |


Stress-population household calibration (scenarios/config.yaml `stress`):

| Parameter | Value | Source |
| --- | --- | --- |
| Ages | 22–75, weighted 3:4:3 across 22–34, 35–54 and 55–75 | Household tables above (SCF buckets extended to 75+) |
| Financial-services share | 25% of stress cases; exactly 1/3 of journeys j-007+ | **Assumption** (the client is a financial firm, so its own staff are over-represented) |
| FS income | lognormal, median $230k, σ 0.55, clamped to $90k–$1.2M; bonus-heavy | **Assumption**. Deferral share: 40–60% of senior bonuses (2016 §956 proposal) |
| FS employer tickers | HVCG / MRTS / ALDB (invented), β 1.5 / 1.7 / 1.3; firm_collapse marks the stock down 90–99% | Lehman 2008 (employee RSUs worthless) |
| Journey portfolio size | clamped to 30–80 months of expenses (mass-affluent), so cash floors actually bind | **Assumption** |
| Long-term-care costs | $800–4,500/month cost share | Recalled Genworth/CareScout 2023 medians (home health aide about $75k/yr, nursing home about $116k/yr). **Not fetched.** |

## Sources that failed or were only partly used

- FRED `SP500` (10 years only) and `BAMLCC0A0CMTRIV` (3 years only) are truncated by licensing. Stooq blocks automated downloads (JavaScript challenge). We used the Kenneth French library and FRED GS10 instead.
- No free monthly MSCI EAFE or Bloomberg US Aggregate series was available. The French developed ex-US and GS10 proxies above stand in for them.
- Fed SCF bulletin PDF (scf23.pdf). WebFetch could not read the PDF, which arrived as binary. Text was extracted locally with pypdf, and Table 1 and the Box 2 text were used directly. The age-specific retirement-balance medians could not be found in the extracted text, so we used secondary summaries (see above).
- Vanguard *How America Saves 2026* PDF: not opened. Figures come from search summaries.
- KFF 2024 EHBS: not fetched. Values recalled (see above).
- The 2023 CE quintile table was seen only through a search summary of an unofficial reproduction. The 2025 quintile figures were fetched from bls.gov.

## Public benchmarks reviewed (alignment / citation)

| Benchmark | What it covers | Fits ballast? |
| --- | --- | --- |
| **FinBen** (Xie et al., NeurIPS 2024 D&B). https://arxiv.org/abs/2402.12659 | 36 datasets and 24 tasks in 7 areas: information extraction, QA, text generation, risk management, forecasting, and decision-making, including trading agents. | Partly. It is the best umbrella citation for "financial LLM evaluation". It has no client-profile, policy-compliance or rebalancing task, and its trading tasks score return and Sharpe ratio, not suitability. |
| **InvestorBench** (Li et al., ACL 2025). https://arxiv.org/abs/2412.18174 | LLM agents trading stocks, crypto and ETFs in a POMDP with memory. | Closest on the "agent" axis. It measures P&L, not policy compliance or life events. Worth citing as related work. |
| **FinanceBench** (Islam et al., Patronus AI, 2023). https://arxiv.org/abs/2311.11944 | 10,231 open-book QA items over SEC filings. | No. It is document QA, not advice. |
| **UCFE** (User-Centric Financial Expertise) | User-simulated financial tasks judged by an LLM. | Loosely. It is advice-quality evaluation, but subjective (LLM-as-judge). Ballast uses deterministic rules instead. |

No public benchmark was found for **suitability-constrained rebalancing for a household's life events**, which is what ballast tests. The nearest real-world analog is the regulatory suitability framework: FINRA Rule 2111 (https://www.finra.org/rules-guidance/rulebooks/finra-rules/2111) and the SEC's Regulation Best Interest require recommendations to fit the investor's profile, including age, liquidity needs, risk tolerance and time horizon. The case schema mirrors that investment-profile list. That framing is the strongest "real-world task" claim; the benchmarks above are related work, not alignment targets.
