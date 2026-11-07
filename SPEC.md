# Ballast: Build Spec

Nov 7, 2026 · @Sudhersan

**One-liner:** Ballast is a personal portfolio agent that gets measurably better with every run. It rebalances each client's portfolio to their risk profile and life events, catches itself when it drifts from intended behavior, and uses Meta's Muse to rewrite its own playbook, shipping only fixes that prove better on scenarios it has never seen.

Name: **Ballast**.

## Goal and hackathon fit

We target the first theme fully: systems that "get measurably better with every run" ([event page](https://cerebralvalley.ai/e/aie-code-2026-hackathon)). Proof is a score on unseen client scenarios that rises each generation, and recovers after drift.

- **Muse runs everything:** Muse powers the whole system. It is the portfolio agent's model and the mentor that writes every upgrade to the playbook. This targets the $5,000 best-use-of-Meta-Model-API prize. Pitch line: "Muse makes itself better at your job."
- **Personal agent:** every client gets an agent shaped by their own profile, and it keeps adapting as their life changes.
- **Demo data is synthetic.** The agent recommends; a human approves. It never executes trades.
- **Illustrative rules:** the policy numbers below are demo assumptions, not financial advice.

## Sponsor integrations (prize plan)

Muse stays the core. Each other partner gets one real job, so the project qualifies for any sponsor prize announced on the day. Only the Meta prize ($5,000) is published so far; $11,000 total.

| Sponsor | Role in the system | Demo moment | Priority |
| --- | --- | --- | --- |
| Meta (Muse) | The agent's model and the mentor that rewrites the playbook. | Muse diagnoses drift and writes the fix. | Must |
| MongoDB | Clients, events, playbook versions, runs and drift events. Change streams trigger a drift check when a new life event is inserted; vector search finds similar past drift cases for Muse. | Insert a life event; the check fires instantly. | Must |
| Fetch.ai | Each client's agent is registered as a uAgent on Agentverse. The client reports a life event in chat ("I got laid off"); the agent logs it and returns a recommendation. | Client chats with their own agent. | High |
| Google DeepMind (Gemini) | Independent compliance reviewer: checks each Muse playbook change for anything that weakens policy before it ships. | A risky change is blocked by the reviewer. | Medium |
| Subquadratic (SubQ) | Long-context drift analyst: reads every run and client timeline at once and summarizes systematic drift patterns for Muse. | "Across 200 runs, layoffs with single-stock exposure fail 70% of the time." | Stretch |

Ask each sponsor at kickoff whether they have a prize and what they judge on, then adjust the demo emphasis.

## System overview

| Component | What it does |
| --- | --- |
| Portfolio agent (inner) | Pi harness. Reads a client case, outputs a rebalancing recommendation. |
| Playbook (harness config) | Versioned YAML: instructions, skills, checklists, limits. The only thing that evolves. |
| Policy checker and drift indicator | Scores each recommendation against fixed policy rules; reports drift level and reasons. |
| Scenario generator | Creates synthetic client cases for practice, test, regression and drift demos. |
| Outer loop (runtime) | Runs scenarios, detects drift, rolls back, calls Muse, verifies, ships or rejects. |
| Muse (mentor) | Reads failures and violations, writes the next playbook version. |
| MongoDB | Stores playbook versions, runs, scores, drift events. |
| Dashboard | Score by version, drift indicator, playbook diffs. |

The outer loop is task-agnostic. Everything portfolio-specific lives in the agent, the playbook, the checker and the scenarios.

## Inner agent: the portfolio agent

**Input (one folder per case, copied into the agent's working directory):**

- `client.json`: profile (age, income, monthly expenses, dependents, risk score 1 to 5, horizon years, goals).
- `holdings.json`: current positions (symbol, units, value in USD).
- `market.json`: prices and asset class of each symbol.
- `events.json`: life events since the last review (type, date, details).
- `tools/portfolio.py`: a helper CLI the agent can call, for example `python tools/portfolio.py allocation holdings.json` prints current weights by asset class.

**Asset universe (keep it small):** `US_EQ` (US stock fund), `INTL_EQ` (international stock fund), `BOND` (bond fund), `CASH`, plus 3 single stocks for concentration tests.

**Output: `recommendation.json`**

```json
{
  "client_id": "c-014",
  "target_allocation": {"equity": 0.55, "bond": 0.30, "cash": 0.15},
  "trades": [
    {"symbol": "US_EQ", "action": "sell", "amount_usd": 12000, "reason_ref": "event:layoff"},
    {"symbol": "CASH", "action": "buy", "amount_usd": 12000, "reason_ref": "rule:emergency_fund"}
  ],
  "rationale": [
    {"ref": "event:layoff", "text": "Job loss: raise cash to 6 months of expenses."}
  ],
  "profile_updates": {"goals_add": [], "monthly_contribution": null, "risk_score": null},
  "flags": [],
  "no_action_reason": null
}
```

- `profile_updates`: non-trade changes. `goals_add` takes goal objects such as `{"type": "education", "target_year": 2044}`. A `null` field means no change.
- `flags`: items for human review, for example `"joint_profile_review"` after a marriage.
- `CASH` is a tradable symbol, so a cash buy offsets a sell and "trades net to zero" includes it.

**Pi invocation (one fresh process per case):**

```bash
pi --mode json --no-session --no-extensions --no-context-files \
   --no-skills --skill <playbook_dir>/skills \
   --append-system-prompt <playbook_dir>/prompt.md \
   --tools read,bash,write \
   --model meta/muse "Review this client case and write recommendation.json."
```

Pi has no max-turns flag: count `turn_end` events in the JSON stream and stop the process at the playbook's `max_turns`. Hard timeout: 3 minutes per case.

**Runs on Linux only** (WSL locally, or a Fly Machine). On native Windows, Pi replaces `bash` with `powershell`, so the agent's tool set would differ between machines and scores wouldn't be comparable. Flags are from Pi's [CLI docs](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/cli.md).

## Data schemas

All case files are JSON. Amounts in USD, dates ISO `YYYY-MM-DD`.

**`client.json`**

```json
{"client_id": "c-014", "age": 38, "annual_income": 140000, "monthly_expenses": 5200,
 "dependents": 1, "risk_score": 3, "horizon_years": 25,
 "goals": [{"type": "retirement", "target_year": 2053}],
 "targets": {"equity": 0.60, "bond": 0.30, "cash": 0.10},
 "monthly_contribution": 1500}
```

**`holdings.json`**

```json
{"as_of": "2026-11-01", "positions": [
  {"symbol": "US_EQ", "units": 410, "value": 82000},
  {"symbol": "BOND", "units": 300, "value": 30000},
  {"symbol": "ACME", "units": 90, "value": 18000},
  {"symbol": "CASH", "units": 9000, "value": 9000}]}
```

**`market.json`**

```json
{"as_of": "2026-11-01", "symbols": {
  "US_EQ": {"price": 200.0, "class": "equity"},
  "INTL_EQ": {"price": 55.0, "class": "equity"},
  "BOND": {"price": 100.0, "class": "bond"},
  "ACME": {"price": 200.0, "class": "equity", "single_stock": true},
  "CASH": {"price": 1.0, "class": "cash"}}}
```

**`events.json`**

```json
{"events": [{"id": "e1", "type": "layoff", "date": "2026-10-20", "details": {"severance": 20000}}]}
```

Event types: `layoff`, `job_change` (details: `new_income`), `marriage`, `child`, `inheritance` (drift set only), `divorce` (drift set only), `market_drop` (drift set only; prices in `market.json` are lowered).

## Policy rules (intended behavior)

These define "correct". They live in the checker, never in the playbook, so the agent cannot loosen them.

| Rule id | Rule | Severity |
| --- | --- | --- |
| `risk_band` | Equity share after trades within the band for the risk score: 1 = 10–30%, 2 = 30–50%, 3 = 50–70%, 4 = 70–85%, 5 = 85–100%. | Hard |
| `emergency_fund` | Cash after trades ≥ 3 months of expenses; ≥ 6 months after a layoff or job-loss event. Only `CASH` in holdings counts; severance in event details does not. | Hard |
| `concentration` | No single stock above 10% of the portfolio. | Hard |
| `no_churn` | If every asset class is within ±5 points of target and there are no new events, make no trades. | Soft |
| `event_child` | New child: `profile_updates.goals_add` includes an `education` goal about 18 years out. | Soft |
| `event_marriage` | Marriage: `flags` includes `joint_profile_review`; `profile_updates.risk_score` stays `null`. | Soft |
| `event_job_change` | Higher income: `profile_updates.monthly_contribution` is above the current value; `risk_score` stays `null`. | Soft |
| `glidepath` | Age 55 or older: equity at the low half of the band. | Soft |
| `cited` | Every trade has a `reason_ref` that matches an event or rule in the case. | Hard |
| `valid_output` | `recommendation.json` exists and matches the schema; trades net to zero. | Hard |

**Case score:** fraction of applicable rules passed. **Case pass:** all hard rules pass and the score is at least 0.8.

## Drift indicator

Runs after every agent run and over a rolling window. Interface (one record per run):

```json
{"run_id": "r-881", "playbook_version": 6, "case_id": "c-014",
 "score": 0.71, "level": "red",
 "violations": [{"rule": "emergency_fund", "detail": "cash 2.1 months, needs 6 after layoff"}]}
```

| Level | Trigger |
| --- | --- |
| Green | No hard violations, and the rolling 10-run average is within 0.05 of baseline. |
| Yellow | Rolling average dropped by 0.05 or more, or soft violations are rising. |
| Red | A hard violation on a case type (event mix) that the shipped playbook passed in its verification run. |

**When drift is computed:** only in drift mode, measured against the last *shipped* playbook's verification baseline. During training, v0 is expected to fail about half the cases, so failures there are training signal, not drift.

The `violations` list is the most important field: it is what Muse reads to fix the agent.

## The playbook (harness config)

One versioned YAML file per version. Version 0 is the teammate's initial guideline.

```yaml
version: 4
parent: 3
model: meta/muse          # fixed; never changed by the loop
prompt: |
  You are a portfolio assistant. Recommend, never execute.
  Always read events.json before computing trades.
skills:
  - name: layoff-playbook
    description: Use when events include a layoff or job loss.
    body: |
      1. Compute 6 months of expenses. 2. Raise CASH to that level first.
      3. Only then rebalance the rest to the risk band.
  - name: rebalance-check
    description: Use before writing any trades.
    body: |
      Run portfolio.py allocation; if all classes are within 5 points of target
      and there are no new events, write no trades.
tools: [read, bash, write]
max_turns: 12
changelog: "Added layoff-playbook after emergency_fund drift"
```

Each skill is written to `skills/<name>/SKILL.md` (frontmatter `name` and `description`, then the body) before the run; `prompt` goes to `prompt.md`.

## Scenarios

A generator script creates synthetic cases with random profiles, holdings and events.

| Set | Size | Purpose |
| --- | --- | --- |
| Practice | 20 | Agent runs these; failures feed Muse. |
| Test (unseen) | 20 | Decides whether an upgrade ships. Never shown to Muse. |
| Regression (golden) | 10 | Must always pass; protects against fixes that break other behavior. |
| Drift injection | 10 | Held back for the demo: new event types (inheritance, divorce, market crash) and shifted market data. |

Mix of events in practice and test: about 30% no events (tests `no_churn`), the rest spread across layoff, job change, marriage, child and age 55+.

## Outer loop

The same runtime as before, with two modes.

**Training mode (improve):**

1. Run the current playbook on the practice set; collect violations.
2. Muse reads the playbook and up to 8 failed cases (case summary, agent output, violations) and returns a new playbook YAML plus a changelog.
3. Run the candidate on the test set and the regression set.
4. Ship if the test score improves and regression stays 100%; otherwise reject. Log either way.

**Drift mode (catch and realign):**

1. **Detect:** the drift indicator turns yellow or red on live or scheduled runs.
2. **Contain:** on red, roll back to the last known-good playbook immediately.
3. **Capture:** each drifted case becomes a new test scenario (and is added to practice if it is a new event type).
4. **Realign:** Muse reads the drifted cases and violations and writes a fix.
5. **Verify:** the fix must pass the drifted cases and the full regression set.
6. **Ship or escalate:** ship on pass; after 3 failed attempts, keep the last good version and flag a human.

```python
while True:
    report = monitor(playbook, scheduled_cases)          # drift indicator
    if report.level == "red":
        playbook = last_good()                            # contain
    if report.level in ("yellow", "red"):
        add_to_tests(report.drifted_cases)                # capture
        for attempt in range(3):
            cand = muse_fix(playbook, report.violations)  # realign
            if passes(cand, report.drifted_cases) and passes_all(cand, regression):
                playbook = ship(cand); break              # verify + ship
        else:
            escalate(report)
```

**Muse prompt rules:** change at most 3 things per version; never reference case ids or client names; skills must be general habits; never restate or weaken policy rules; output must parse against the playbook schema.

**Muse prompt template (`runtime/prompts/mentor.md`):**

```text
You improve a portfolio agent by editing its playbook (YAML).
The model and the policy rules are fixed; only the playbook changes.

CURRENT PLAYBOOK:
{playbook_yaml}

FAILED CASES (summaries, max 8):
{for each: event types, risk score, agent trades, violations with details}

CURRENT SCORES: practice {p}, test {t}

Write an improved playbook. Rules:
- Change at most 3 things. Prefer adding or sharpening a skill.
- Skills must be general habits, never about a specific client or case id.
- Never restate, weaken or override the policy rules.
Return ONLY the full YAML, with version = {next}, parent = {current},
and a one-line changelog.
```

## Storage and dashboard

**MongoDB collections:** `playbooks` (version, parent, YAML, changelog, status), `runs` (playbook version, case, set, score, violations, tokens, seconds), `drift_events` (time, level, violations, action taken), `generations` (test score, regression score, shipped or rejected, reason).

**Dashboard (one page):**

- Line chart: test score by playbook version, with drift events marked.
- Drift indicator light (green, yellow, red) with the latest violations.
- Playbook version list with diffs and shipped or rejected badges.

## Demo script (3 minutes)

1. **Version 0:** the agent handles routine cases but misses life events. Show its score and violations.
2. **It learns:** Muse writes a layoff playbook; show the diff. Score rises on unseen clients.
3. **Drift:** inject new conditions (an inheritance event plus a market drop). The indicator goes red; the agent rolls back automatically.
4. **Realign:** Muse writes a fix; it passes the drifted cases and the regression set; the indicator returns to green.
5. **Close:** "It gets better with every run, catches itself when it drifts, and never ships an upgrade it can't prove."

## Repo layout

```text
agent/
  playbooks/v000.yaml     # initial guideline
  run_case.py             # materialize playbook, run Pi, return result + metrics
  tools/portfolio.py      # helper CLI copied into each case dir
checker/
  rules.py                # one function per rule id
  check.py                # check(case_dir, recommendation) -> {score, passed, violations}
  drift.py                # rolling window -> green / yellow / red
scenarios/
  generate.py             # writes cases/<set>/<case_id>/*.json
  cases/{practice,test,regression,drift}/
runtime/
  loop.py                 # training mode + drift mode
  mentor.py               # Muse call + YAML validation
  store.py                # MongoDB writes
  prompts/mentor.md
dashboard/app.py
```

## Integration contracts

Three functions connect the parts: the agent, the checker and the outer loop.

```python
run_case(playbook_path: str, case_dir: str) -> dict
#   {"case_id", "recommendation": dict | None, "turns", "tokens_in", "tokens_out",
#    "seconds", "trace_path", "error": str | None}

check(case_dir: str, recommendation: dict | None) -> dict
#   {"case_id", "score": float, "passed": bool,
#    "violations": [{"rule", "severity", "detail"}]}

drift_level(recent_checks: list[dict], baseline: float) -> dict
#   {"level": "green" | "yellow" | "red", "rolling_score", "violations"}
```

## Build sequence

1. **Pi runs one case:** Muse added as a provider in `~/.pi/agent/models.json`; `--mode json` stream saved with token usage.
2. **`portfolio.py` helper:** `allocation` (weights by asset class) and `apply` (holdings after trades).
3. **Playbook v0 and `run_case`:** writes skills and prompt, runs Pi, stops at max turns or 3 minutes, returns the contract dict.
4. **Checker:** one function per policy rule; hand-made good and bad recommendations get the expected violations.
5. **Scenario generator:** 60 cases across the four sets, with fixed seeds.
6. **Muse mentor:** template call, YAML extraction and validation (parses, required keys, at most 3 changes, no case ids).
7. **Training mode:** evaluate, mentor, verify, ship or reject, logged to MongoDB; 3 to 5 generations.
8. **Drift indicator and drift mode:** a forced red triggers rollback, capture, a Muse fix and verification.
9. **Dashboard and demo run.**

**Baseline:** Muse runs everything, so the room to improve comes from the playbook, not the model. Keep v0 deliberately minimal (no life-event guidance, no rebalancing checks) and confirm it fails roughly half the test cases before training. If v0 already passes most cases, make the scenarios harder (several events per client, concentration plus layoff) rather than switching models.

## Open questions

- Muse API endpoint, auth and rate limits: confirm with Meta's team on site.
- Submission deadline and format: confirm at check-in.

## Sources

- [AIE Code Summit 2026 Hackathon](https://cerebralvalley.ai/e/aie-code-2026-hackathon)
- [Pi CLI docs](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/cli.md)
