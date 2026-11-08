# ballast. demo script

Site: https://ballast-web.fly.dev · Live, Run, Chat: /live · How it's built: /architecture
Fetch.ai agent: `agent1q285agwxf87dre4qkz5p8crmknqnwxrk7lpta453uam8kjl0sahryq3tqxw`
Run passcode: ask the team.

---

## 1-minute version

"Every financial firm wants AI agents looking after clients. The problem: when an agent gets something wrong, someone tweaks its prompt by hand and hopes. Nobody can prove the change made it better, and nobody notices when it starts drifting.

ballast. gives every client their own portfolio agent, built on **Muse**. It's connected to the client's accounts, so it notices when life changes: a paycheck stops, a parent needs care. When the agent gets a client wrong, **Muse becomes the teacher**: it finds the root cause, ties it to the life event, and rewrites the agent's skills with a plain-English lesson. The new version only ships if it does better on clients it has never seen.

It gets better with every run, catches itself when it drifts, and never ships an upgrade it can't prove."

---

## 3-minute demo

### 0:00–0:25 · The problem (home page, top)
"A client's plan goes stale the moment their life changes: a layoff, a new baby, a parent who needs care. Clients rarely tell their advisor in time. AI agents could help, but you can't trust an agent that changes itself unless every change is proven."

### 0:25–1:10 · Meet the agent (/live → Chat with your agent)
Show Miguel's real Fetch.ai chat (or send it live on ASI:One: `@agent1q285…tqxw Hi, it's Miguel. My hospital let me go at the end of September and I'm on COBRA now. What should I do?`).
"This is Miguel, an ICU nurse, chatting with his own agent on Fetch.ai. Behind it, **Muse Spark** runs in a coding-agent harness, connected read-only to his accounts."
Click **Replay run**. Point at the tool calls: payroll → no pay stubs since Sept 26; bank → severance, unemployment, COBRA.
"It reads his real data, works out he needs six months of cash including COBRA, and recommends moving $26,000 into cash, with a reason on every trade. It never executes; an advisor approves."

### 1:10–2:10 · It learns (Connected data → v0 vs v1, then Proof)
Open `/live#connected-cx-002`.
"The first time, with generic skills, it noticed the layoff but stopped at 5.7 months of cash. Policy says 6. Fail."
"So **Muse Wonder became the mentor.** It read the failures, found the root cause, mapped it to the event, and wrote this lesson:"
> **"I build cash to a full six months of expenses after a layoff before putting any sale proceeds into bonds or rebalancing."**
"Miguel went from 0.75 to 1.00. Four of five connected clients went to a perfect score." (Priya went down slightly; be honest if asked.)
Scroll to **Proof** on the home page:
"But fixing the clients you learned from proves nothing. So every upgrade has to win on **20 clients it has never seen**, three runs each, against a 12-month market backtest, and pass an independent compliance review. Muse's v2 did: **65% → 95% pass rate, cash shortfalls 3 → 0, forced sales 2 → 0.** And when we fed the mentor shuffled, unrelated failures as a control, it gained almost nothing (+0.003 vs +0.105). The improvement comes from learning, not luck."

### 2:10–2:40 · It catches itself (gates and drift)
"The gate is strict. It rejected changes that looked better but broke a client, and it blocked a change where Muse tried to hard-code one client's number into general advice. When the world changes, a crash or a firm collapse, the agent's failures on rules it used to pass turn the light red, it rolls back on its own, and Muse writes the fix through the same gate."

### 2:40–3:00 · Close
"Muse is the agent and Muse is the teacher. The same framework improves other models too; we benchmarked it. ballast. gets better with every run, catches itself when it drifts, and never ships an upgrade it can't prove."

---

## Numbers to have ready (all real)

| What | Number |
| --- | --- |
| Muse v2 on 20 unseen clients ×3 | pass 65% → 95%, mean 0.818 → 0.923, cash breaches 3 → 0, forced sales 2 → 0, hard-rule violations 25% → 7%, consistent across repeats 75% → 95% |
| Same framework on SubQ Preview | 0.812 → 0.912, pass 65% → 85%; ~2× faster, ~half the tokens; control arm +0.069 (weaker proof) |
| Harder data (300 stress clients, starting skills only, partial run) | Muse 57%, SubQ 53%, Gemini 28%, naive rebalancer 34%, do-nothing 18%; trading-firm crises hardest (~47–50%) |
| Cost | $0.057 of Muse per passing recommendation |
| Gain vs control arm | +0.105 (90% CI +0.053 to +0.160) vs +0.003 with shuffled failures |
| Connected clients v0 → v1 | mean 0.821 → 0.960; 4 of 5 to 1.00; Priya 1.00 → 0.80 |
| Fetch.ai chat (Miguel) | 49 s on Muse, policy 1.00, $26K to cash, COBRA in the math |
| Overfitting caught | reviewer blocked a change that hard-coded "$600" from one client; Muse's retry generalized it |
| Test data | 60 cases, 6 journeys through real 2000–2023 markets, 300 stress clients with 54 event types incl. trading-firm collapses |
| Harness | 13 handlers; each run sandboxed; 10 policy rules (+6 for new events) hidden from the agent |

## If they ask

- **"Is it just learning the test?"** The rules are hidden; the reviewer blocks client-specific shortcuts; every upgrade is scored on unseen clients; the control arm with shuffled failures gained nothing.
- **"Did anything get worse?"** Yes: v2 trades more, so two soft rules (age-55 glide path, no trading in quiet months) got worse. Every hard rule and the backtest improved, so the gate shipped it; those are the next lessons.
- **"Only Muse?"** Same framework also runs SubQ Preview as agent and mentor. Muse is our default.
- **"Is it safe?"** It only recommends. Only the instructions change, never the model or the rules. Every change is readable, reviewed and reversible.
- **"Real data?"** Synthetic clients, calibrated to Fed, BLS and CDC statistics; real monthly market returns 1990–2026.

*Synthetic clients only. Illustrative policy, not financial advice.*
