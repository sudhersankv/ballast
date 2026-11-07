# ballast. — how it works, end to end

Written for someone new to the project. No prior knowledge assumed.

---

## 1. The short version

ballast. gives every client a personal AI agent that looks after their investment portfolio. The agent reads the client's situation and recommends trades. A human approves them; the agent never trades on its own.

The interesting part is not the agent. It is the **harness around it**: a system that watches the agent's mistakes, figures out *why* each one happened, rewrites the agent's instructions to fix it, and only keeps the new instructions if it can **prove** they work on situations the agent has never seen. When the world changes and the agent starts slipping, the harness notices, rolls back, and fixes it again.

The one-line pitch: **it gets better with every run, catches itself when it drifts, and never ships an upgrade it can't prove.**

---

## 2. The big idea (beyond finance)

### The problem

AI agents are being put in charge of real work. Today, when an agent gets something wrong, a person edits its prompt by hand, tries a few examples, and hopes. Nobody can say whether the edit made the agent better overall, or whether it quietly broke something else. And when conditions change (new kinds of customers, a market crash), agents drift without anyone noticing until damage is done.

### What we built: AutoML, but for an agent's instructions

AutoML is the idea of letting a machine search for a better model setup and keeping only what scores better on held-out data. ballast. applies the same discipline to an AI agent's **instructions** instead of a model's weights:

| AutoML | ballast. |
| --- | --- |
| Searches model settings | Searches the agent's **playbook** (its instructions and skills) |
| A training set to learn from | **Practice** cases the agent fails on |
| A validation set to decide | **Unseen test** cases and the client's **future** quarters |
| Keep the setting only if validation improves | **Ship** the new playbook only if it passes every **gate** |

### Why it is safe

- **Only words change.** The model, the tools and the rules are fixed. The thing that evolves is a readable text file. Anyone can open it and see exactly what the agent was told.
- **The rules live outside the agent.** The grading rules are code the agent cannot see or edit. It cannot "loosen" its own standards.
- **Every change needs evidence.** A new version must score higher on situations it never trained on, break nothing that already worked, survive a replay of real market history, and pass an independent compliance review.
- **It can undo itself.** If performance drops, it rolls back to the last version that was proven good. After three failed fix attempts it stops and asks a human.
- **It only recommends.** No trade happens without a person approving it.
- **It runs locked down.** Each agent run happens in a sandbox as a restricted user that cannot read the grading code or any passwords.

### Why it is prescriptive

Every improvement comes out as a **lesson** a person can read, tied to a cause:

> "After a layoff, I build six months of cash before rebalancing anything else."
> Learned from: a layoff. Root cause: the agent put sale proceeds into stocks and bonds without checking cash. Rule it fixes: emergency fund. Proven on: unseen clients, 4 failing → 0.

So the output is not a black box that got better. It is a list of specific, auditable behaviors, each with the failure it came from and the evidence that it works.

---

### The harder version of the problem: nobody tells the agent

In real life, clients rarely tell their advisor that something changed. The signal is in their data: paychecks stop, a home-care payment appears, an HR portal posts a desk wind-down. So the agent is **connected** to the client's accounts (read-only, with consent, every read logged) and has to **discover** what changed before it can act. The grader still knows the truth, so we can score whether it noticed.

## 3. Today's use case: a portfolio agent per client

A wealth-management firm has many clients. Their lives change: layoffs, raises, marriages, new children, divorces, inheritances. Markets change too: crashes, rallies, rate shocks. A plan written at onboarding goes stale fast.

ballast. gives each client their own agent. At every review, the agent looks at the client's profile, holdings, the market and any new life events, and recommends trades with a reason for each one. Over time, the harness teaches each client's agent the lessons that matter for that client.

All clients are synthetic. All policy numbers are illustrative, not financial advice.

---

## 4. Words we use

| Word | Meaning |
| --- | --- |
| **Client case** | One client at one point in time: four files — profile (`client.json`), holdings (`holdings.json`), market prices and 4 years of history (`market.json`), and life events since the last review (`events.json`). |
| **Agent** | The AI that reviews a case and writes `recommendation.json`: trades, target mix, reasons, profile updates (e.g. raise the monthly contribution), and flags for a human. |
| **Harness** | The program that runs the agent: gives it the case files, a few tools (read files, run a calculator script, write a file), a turn limit and a time limit. We use the **Pi** coding-agent harness. |
| **Playbook** | The agent's instructions: a short prompt, a set of **skills** (step-by-step habits for specific situations), a turn limit, and the **lessons** it has learned. The only thing that ever changes. |
| **Skill** | One named habit inside the playbook, e.g. `emergency-fund-priority`: "when there is a layoff, raise cash to six months first." |
| **Lesson** | A plain-language sentence describing what the agent learned, with the root cause, the triggering event, and the rule it fixes. |
| **Rule** | A fixed policy check, e.g. "cash must cover 3 months of expenses, 6 after a layoff." **Hard** rules must pass; **soft** rules lower the score. |
| **Checker** | The code that grades a recommendation against the 10 rules. Gives a **score** (0–1) and a list of **violations** with numbers. |
| **Backtest** | Replays the 12 months of real market history *after* the review date (which the agent never saw) to see what the recommendation would have done: return, worst drop, whether the client ran out of cash and had to sell. |
| **Mentor** | The AI that reads failures and writes the next playbook. It must name the root cause and the event that triggered it. |
| **Gate** | The set of checks a new playbook must pass before it ships. |
| **Version / generation** | Each playbook gets a number: v0, v1, v2… One round of "test, learn, gate" is a generation. |
| **Practice / test / regression / drift** | Groups of cases. The mentor only ever sees practice failures. Test decides shipping. Regression must not break. Drift is held back to test what happens when the world changes. |
| **Client journey** | One client reviewed every quarter for 2.5 years (10 **checkpoints**), through a real market period, with life events along the way. The first 5 are for learning, the last 5 (**holdout**) prove it. |
| **Drift** | The agent starting to fail on rules it used to pass, usually because something new happened. |
| **Rollback** | Switching back to the last version that was proven good. |
| **Snap gate** | A fast yes/no check (from SubQ's decision model) on each new life event: which rules are at risk, and does the playbook cover this? |
| **Control arm** | A deliberate fake: the mentor is fed shuffled failures. If its changes still "helped," our improvements would be luck. They shouldn't. |

---

## 5. Step by step: what happens

### 5a. One client review (the inner loop)

1. **Prepare the case.** The four case files are copied into a fresh, empty folder, plus a small calculator script (`portfolio.py`) the agent can use to see current weights and test its trades.
2. **Build the agent's instructions.** The playbook is turned into a system prompt plus one file per skill.
3. **Run the agent.** The harness starts Muse inside the sandbox. The agent reads the files, runs the calculator, writes a draft, checks it, and saves `recommendation.json`. We stop it after 20 turns or 3 minutes. Every step it takes is recorded.
4. **Grade it.** The checker runs the 10 rules and produces a score and violations, e.g. `emergency_fund: cash 2.7 months, needs 6 after layoff`.
5. **Backtest it.** The trades are applied and the portfolio is marked to market over the next 12 real months. If the client is unemployed, living costs come out of cash; if cash runs out, investments are sold (a **forced sale**).
6. **Save everything.** The run, the trace, the score, the violations and the backtest go into the database. The live view shows it within seconds.

### 5b. Getting better (the training loop)

1. Run the current playbook on 20 **practice** clients.
2. Hand up to 8 failures to the **mentor**. For each, it sees the client's events, the trades the agent made, and the exact violation.
3. The mentor diagnoses the root cause, maps it to the triggering event, and writes a new playbook: at most 3 changes, with a new lesson. It may not mention specific clients or invent thresholds.
4. **Validate** the new playbook (format, change count, no client names, lessons kept).
5. **Compliance review:** Gemini compares old and new and blocks anything that loosens client protection.
6. Run the candidate on 20 **unseen test** clients (3 times each, to separate real gains from luck) and on the 10 **regression** clients.
7. **Gate:** ship only if the test score rises by at least 0.02 with confidence, no client that passed now fails, the backtest shows no more cash breaches or forced sales, and the reviewer approved. Otherwise reject, and log why.
8. Repeat.

### 5c. Each client's own agent (the journey loop)

1. Start the client with the generic playbook.
2. Walk through their first 5 quarterly checkpoints in order. At each, run the agent, grade and backtest it.
3. When it fails, the mentor writes a fix *for this client*, with a lesson. The fix is kept only if it passes this checkpoint and still passes every earlier one.
4. On the last 5 checkpoints (the client's future, never shown to the mentor), run **both** the generic agent and the client's own agent. The difference is the proof that this client's agent is better aligned.

### 5d. Catching drift (the safety loop)

1. A new life event lands in the database (e.g. "I got laid off").
2. The database fires a **change stream** event instantly.
3. The **Snap gate** asks, in under a second: which rules does this put at risk, and does the current playbook cover it?
4. If a rule is at risk and the playbook doesn't cover it, the client's agent is re-run immediately.
5. If a rule the agent used to always pass now fails, the drift light goes **red**, and the system **rolls back** to the last good version.
6. A long-context **analyst** reads every run, every client timeline and every playbook version in one pass, and names the pattern (e.g. "layoff plus a concentrated stock fails the cash rule 70% of the time").
7. The mentor writes a fix from that diagnosis. It ships only if it passes the drifted cases and the regression set. After 3 failed attempts, it escalates to a human.

---

## 6. The runtime: every handler

"Handler" here means a piece of the system with one job, its inputs, and its outputs. There are **13 runtime handlers** plus the web app.

| # | Handler | File | Job | Needs |
| --- | --- | --- | --- | --- |
| 1 | Case runner | `agent/run_case.py` | Runs one client case through Pi in a sandbox; enforces turn and time limits; records every step | Pi (Node 22.19+), a model key, Linux user `agent` |
| 2 | Portfolio calculator | `agent/tools/portfolio.py` | The agent's tool: current weights, cash in months, what trades would do. The checker uses the same math | Python only |
| 2b | Client data connectors | `agent/tools/clientdata.py` | Read-only access to the client's bank transactions, payroll, employer portal (trading windows, HR notices), calendar, messages and credit report. When a client is connected, the harness hides `events.json`; the agent must find the life change itself | Client consent per source; synthetic feeds in `connectors/` |
| 3 | Checker | `checker/check.py`, `rules.py` | Grades a recommendation: 10 rules, score, pass, violations | Python only |
| 4 | Drift indicator | `checker/drift.py` | Green / yellow / red from a window of graded runs | Python only |
| 5 | Backtest | `scenarios/backtest.py` | Replays the 12 held-out months: return, drawdown, cash coverage, forced sales | Held-out market files |
| 6 | Mentor | `runtime/mentor.py` (`mentor_propose`, `validate_playbook`) | Diagnoses failures and writes the next playbook with lessons; validates it | Muse (or SubQ) key |
| 7 | Compliance reviewer | `runtime/mentor.py` (`compliance_review`) | Blocks changes that weaken client protection | Gemini key |
| 8 | Drift analyst | `runtime/mentor.py` (`analyze_drift`) | Reads all runs at once and names patterns | SubQ Preview (or Muse) key |
| 9 | Snap gates | `runtime/snap.py` | Per-event rule-risk check; second opinion on rollback | SubQ key |
| 10 | Training and drift loop | `runtime/loop.py` (`train`, `drift`, `bench`) | Orchestrates generations, gates, rollback, model comparisons | All of the above, MongoDB |
| 11 | Journey loop | `runtime/journey.py` | Per-client learning over quarterly checkpoints, proven on the client's future | All of the above |
| 12 | Live watcher | `runtime/watch.py` (+ `inject_event.py`) | Listens to MongoDB for new life events; runs the Snap gate, re-runs, triggers drift mode | MongoDB change streams |
| — | Store | `runtime/store.py` | Writes and reads everything; falls back to local files if the database is down | MongoDB URI |
| — | Model client | `runtime/llm.py` | One way to call Muse, Gemini or SubQ | Keys |
| — | Web app | `web/main.py` | The website and live view; read-only over the database | MongoDB URI |

### What's stored (MongoDB collections)

`playbooks`, `generations`, `runs`, `drift_events`, `drift_analysis`, `clients`, `life_events`, `benchmarks`, `loop_log`, `journeys`, `journey_playbooks`, `journey_steps`, `journey_summaries`.

### Where it runs

| Piece | Where |
| --- | --- |
| Agent runs, loops, journeys | Fly.io machines in Virginia (`ballast-runner`). Meta's API refuses requests from Fly's San Jose region |
| Website and live view | Fly.io (`ballast-web`), https://ballast-web.fly.dev |
| Database | MongoDB Atlas (free tier) |
| Models | Meta Model API (`api.meta.ai`), Subquadratic (`api.subq.ai`), Google Gemini |

---

## 7. Who does what (models and partners)

| Part | Role |
| --- | --- |
| **Muse Spark 1.3** (Meta) | The portfolio agent |
| **Muse Wonder 1.0** (Meta) | The mentor that writes new playbooks and lessons |
| **SubQ Snap** (Subquadratic) | Fast decision gates: rule risk per life event, rollback verdict |
| **SubQ Preview** (Subquadratic) | Long-context analyst; also benchmarked as an agent and mentor |
| **Gemini** (Google DeepMind) | Independent compliance reviewer |
| **Pi** | The agent harness: runs the model with tools, limits and a sandbox |
| **MongoDB Atlas** | All data; change streams trigger drift checks on new life events |
| **Fly.io** | Runs everything |
| **Fetch.ai** (next) | Lets a client chat with their own agent on Agentverse |

---

## 8. The test data

- **60 single cases** in four groups (practice 20, test 20, regression 10, drift 10), calibrated to public US data: the Federal Reserve's Survey of Consumer Finances, BLS spending and layoff statistics, CDC life-event ages, Vanguard glide paths.
- **6 client journeys**, each 10 quarterly checkpoints through a real market period: the 2008 crisis, COVID, the 2022 rate shock, the dot-com bust, a calm bull market, and a 2015–17 correction.
- **Real market history:** monthly returns from 1990 to 2026 (Kenneth French data library for stocks and cash, FRED Treasury yields for bonds). Each case gets 4 years of history; the next 12 months are hidden in a separate folder for the backtest.
- A reference solver passes every case and every checkpoint, so every test is fair.

---

## 9. What we built today

1. Repo, spec and evaluation criteria (with a teammate).
2. Linux runner on Fly with a sandboxed Pi harness.
3. The checker (10 rules, 11 tests) and drift indicator.
4. Realistic scenarios, real market history, held-out months and the backtest.
5. The mentor with root-cause diagnosis and lessons; the Gemini reviewer.
6. The training loop with gates; the drift loop with rollback and escalation.
7. SubQ Snap gates, calibrated against the checker (F1 0.94), and the live change-stream watcher.
8. Six client journeys and the per-client learning loop.
9. The website: guided replay, live view, lessons, journeys, coverage map, benchmark.
10. Real runs on Muse. v0 passed 11 of 20 unseen clients; Muse's v1 passed 19 of 20 and cut backtest cash breaches from 6 to 0 (the gate held it back because one regression client flipped, which the 3× repeated runs now address).

## 10. What's next

1. Finish the Muse vs SubQ benchmark (same tests, repeated runs, control arm, journeys, drift, cost).
2. Start the demo from a truly generic playbook, so the first 2–3 checkpoints fail and the learning is visible.
3. Fetch.ai: each client chats with their own agent.
4. Vector search over past drift cases, so the mentor sees similar past fixes.
5. Hide numeric thresholds from the mentor's view of failures, so gains come from reasoning rather than copying the grader.
