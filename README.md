# Ballast

A personal portfolio agent that gets measurably better with every run. It rebalances each client's portfolio to match their risk profile and life events, catches itself when it drifts, and uses Meta's Muse to rewrite its own playbook. It ships only the upgrades that score better on scenarios it has never seen.

Built at the AIE Code Summit 2026 Hackathon (Cerebral Valley, Shack15, SF, Nov 7 2026).

The full design is in **[SPEC.md](SPEC.md)**. Read it first.

> Synthetic data only. All policy numbers are illustrative demo assumptions, not financial advice. The agent recommends trades and never executes them.

## Layout

```text
agent/        Pi harness: playbooks/vNNN.yaml, run_case.py, tools/portfolio.py
checker/      fixed policy rules, check.py, drift.py (green/yellow/red)
scenarios/    generate.py -> cases/{practice,test,regression,drift}/
runtime/      loop.py (training + drift modes), mentor.py (Muse), store.py (MongoDB)
dashboard/    one-page score / drift / diff view
fetch/        Fetch.ai uAgent per client (Agentverse chat)
```

## Integration contracts (do not change without telling the team)

```python
run_case(playbook_path, case_dir) -> {"case_id", "recommendation", "turns", "tokens_in", "tokens_out", "seconds", "trace_path", "error"}
check(case_dir, recommendation)   -> {"case_id", "score", "passed", "violations": [{"rule", "severity", "detail"}]}
drift_level(recent_checks, baseline) -> {"level", "rolling_score", "violations"}
```

## Setup

Requires Python 3.12, Node 22.19 or newer, and the Pi CLI.

```bash
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
cp .env.example .env   # fill in keys; never commit .env
```

## Working together

- Branch per component (`agent/...`, `checker/...`), and make small PRs to `main`.
- `checker/` and `scenarios/` need no API keys, so they can be built and tested first.
