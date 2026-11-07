# ballast. demo script

Site: https://ballast-web.fly.dev  (Live + Run: /live · How it's built: /architecture)
Run passcode: ask the team.

---

## The 1-minute version (opening, or if time is cut)

**Say:**
"Every financial firm wants AI agents looking after clients. The problem: when an agent gets something wrong, someone tweaks its prompt by hand and hopes. Nobody can prove the change made it better, and nobody notices when it starts drifting.

ballast. gives every client their own portfolio agent, built on **Muse**. When the agent gets a client wrong, **Muse reads the failure, finds the root cause, ties it to the life event that caused it, and rewrites the agent's skills**, with a plain-English lesson. The new version only ships if it does better on clients and future quarters it has never seen.

It gets better with every run, catches itself when it drifts, and never ships an upgrade it can't prove."

**Show:** the home page scoreboard (score on unseen clients by version), then one lesson card.

---

## The 3-minute demo

### 0:00–0:30 — The problem (home page, top)
"A client's plan goes stale the moment their life changes: a layoff, a new baby, a parent who needs care, a crash. Advisors catch it late. AI agents could help, but you can't trust an agent that changes itself unless every change is proven."

### 0:30–1:15 — Meet the agent (Live → Connected data → Miguel)
Open https://ballast-web.fly.dev/live#connected-cx-002 (Miguel Santos, ICU nurse). Press **Replay** on the v0 run (or Run it live on Muse).
"The agent is **Muse Spark** running inside a coding-agent harness. It's connected to Miguel's accounts, read-only. Nobody told it anything happened."
Point at the data wall: paychecks stop after Sept 26; a severance deposit; COBRA premiums; unemployment deposits.
Point at the agent's tool calls: payroll → bank → calendar.
"It worked out that Miguel was laid off, from his own data, and flagged the COBRA cost. Every trade cites the reason. It never executes; an advisor approves."
Then the verdict: "But it left him at 5.7 months of cash. Policy says 6 after a layoff. That's a fail."
Other connected clients if asked: Dana the rates trader (it found the desk wind-down and respected the trading blackout on her employer stock), Aisha (found her mother's home-care payments and the $43,350 tuition bill), Priya (found "expecting twins" in a message and set up two college goals).

### 1:15–2:15 — It learns (Connected data → v1, then Lessons / Journeys)
"Here's the part that matters. When the agent fails, **Muse becomes the mentor.** Muse Wonder read the five connected clients' failures, found the root cause of each, mapped it to the life event, and rewrote the agent's skills."
Read two of Muse's real lessons from that run:
- **"I build cash to a full six months of expenses after a layoff before putting any sale proceeds into bonds or rebalancing."** (root cause: it split proceeds into bonds while cash was still short)
- **"I add payments due within twelve months on top of my expense buffer when I work out how much cash to hold."** (from Aisha's tuition)
Show v1 re-run on the same clients (scores before → after).
Also: **"After a layoff, I build six months of cash before rebalancing anything else."** on the Lessons ledger.
"Then the gate: the new version has to score higher on clients it has never seen, break nothing that worked, survive 12 months of real market history it never saw, and pass an independent compliance review."
Show the real numbers: **v0 passed 11 of 20 unseen clients; Muse's rewrite passed 19 of 20 and cut cash shortfalls in the backtest from 6 to 0.** And the honesty point: "The gate still held that version back because one client it used to pass flipped. It doesn't ship what it can't prove."
Show a journey: one client, ten quarters through the 2008 crash, lessons appearing where they were learned, later quarters proving them.

### 2:15–2:45 — It catches itself (drift)
"When something new happens, an inheritance, a crash, a firm collapse, the agent can start slipping. ballast. watches for that, rolls back to the last good version on its own, and Muse writes the fix, which has to pass the same gate."
Show the drift step / coverage map. (Optional, only if asked: SubQ's decision model flags which rules a new life event puts at risk in under a second, and SubQ Preview reads every run at once to name the pattern.)

### 2:45–3:00 — Close
"Muse is the agent, and Muse is the teacher. Same framework works with other models too; we benchmarked it. It gets better with every run, catches itself when it drifts, and never ships an upgrade it can't prove."

---

## Numbers to have ready (all from real runs)

| What | Number |
| --- | --- |
| Muse v0 on 20 unseen clients | 11/20 passed, mean 0.792 |
| After one Muse rewrite | 19/20, mean 0.945; backtest cash breaches 6 → 0, forced sales $64.9K → $0 |
| Why it didn't ship | one regression client flipped; the gate is strict on purpose |
| Lesson example | "After a layoff, I build six months of cash before rebalancing anything else." |
| Overfitting caught | Gemini reviewer blocked a Muse change that hard-coded "$600" from one client; Muse's retry generalized it ("raise the contribution in proportion to the new income") |
| Test data | 60 cases + 6 client journeys (real 2000–2023 market regimes) + 300 stress clients with 54 life/work event types, incl. trading-firm collapses and blackout windows |
| Rules | 10 policy rules (+6 for the new event types), hidden from the agent |
| Harness | 12 handlers; each run sandboxed, 20-turn and 3-minute limits |

## If they ask

- **"Is it just learning the test?"** The rules are hidden; an independent reviewer blocks client-specific shortcuts (the "$600" example); every upgrade is scored on clients and future quarters it never saw; a control arm with shuffled failures tests whether gains are real.
- **"Does it only work with Muse?"** No. Same framework, same gates, also run with SubQ Preview as the agent and mentor. Muse is our default.
- **"Is it safe?"** It only recommends. Only the instructions change, never the model or the rules. Every change is readable, reviewed, and reversible.
- **"Real data?"** Synthetic clients, calibrated to Fed, BLS and CDC statistics; real monthly market returns 1990–2026.

*Synthetic clients only. Illustrative policy, not financial advice.*
