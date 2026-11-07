You improve a portfolio agent by editing its playbook (YAML).
The model and the policy rules are fixed; only the playbook changes.
The agent recommends trades for one client per case and never executes them.

CURRENT PLAYBOOK:
```yaml
{playbook_yaml}
```

FAILED CASES (summaries, max 8):
{failures}

{analysis}

CURRENT SCORES: practice {practice}, test {test}

Write an improved playbook. Rules:
- Change at most 3 things. A change is: a skill added, a skill removed, a skill's description or body edited, the prompt edited, or max_turns changed. Prefer adding or sharpening a skill.
- Skills must be general habits that apply to any client, never about a specific client, name or case id.
- Never restate, weaken or override the policy rules, and never invent numeric thresholds you were not shown in the violation details.
- Keep `model` and `tools` exactly as they are. max_turns must be at most 20.
- Each skill needs a unique kebab-case `name`, a one-line `description` saying when to use it, and a `body` with concrete steps.

Return ONLY the full YAML in one ```yaml block, with version = {next}, parent = {current}, and a one-line `changelog` saying what changed and why.
