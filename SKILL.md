---
name: risk-scoring
description: Score a monitored AI agent's activity into an insurance risk score and tier, using frequency, severity and a Bühlmann credibility blend. Use this after get_agent_activity and before draft_policy_quote.
---

# Risk scoring

Turns an agent's activity record into a risk score, a tier, and a premium
multiplier. Run it in the sandbox — it is a plain script with no
dependencies beyond the standard library.

## How to run it

This skill is mounted at `skills/risk-scoring/` relative to the sandbox
working directory, so the script is at `skills/risk-scoring/risk_model.py`.
There is no `/workspace` and no container root — use the relative path
below exactly as written, from the default working directory.

`risk_model.py` reads JSON on stdin and writes JSON on stdout:

```bash
echo '{"agent_id":"agent-safe-01","n_actions":240,"n_flagged_actions":2,"max_single_exposure":80}' | python3 skills/risk-scoring/risk_model.py
```

It needs only the Python standard library — no pip install, no venv
activation. If that path somehow misses, locate it with
`find . -name risk_model.py` rather than guessing another absolute path.

Input — exactly what `get_agent_activity` returns:

| field | meaning |
|---|---|
| `agent_id` | the agent being underwritten |
| `n_actions` | actions observed in the review window |
| `n_flagged_actions` | actions that tripped a rule or anomaly check |
| `max_single_exposure` | largest single action's dollar exposure |

Output:

| field | meaning |
|---|---|
| `risk_score` | 0–100, higher is riskier |
| `tier` | `preferred` / `standard` / `substandard` / `decline` |
| `premium_multiplier` | 0.85 / 1.0 / 1.6, or `null` when declined |
| `credibility_z` | 0–1, how much weight the agent's own history carried |
| `rationale` | the intermediate numbers, for showing your working |

Pass the whole output object straight to `draft_policy_quote` as
`risk_result`. Do not round, reinterpret, or recompute any of it.

## What the score means

Three signals combine:

- **Frequency** — flagged actions per 100, a stand-in for hazard rate.
- **Severity** — largest exposure against a £500 portfolio baseline, a
  stand-in for tail risk.
- **Credibility** — a Bühlmann shrinkage, `Z * own + (1-Z) * portfolio_mean`,
  with `Z` reaching 1.0 at 200 observed actions. A thin-history agent is
  pulled toward the book average rather than judged on a small sample.

So a new agent with a bad run is not automatically declined on frequency —
it is the severity term that dominates when exposure is large relative to
the book. Say that plainly when explaining a decline; do not claim
credibility drove a verdict it did not.

## After scoring

Scoring is safe and repeatable. The step that follows it is not:
`bind_or_flag` writes the decision to the policy ledger and cannot be
undone. It pauses for human approval, and it will refuse outright unless
`human_confirmed` is true. Never describe a policy as bound until that
tool has actually returned a written result.
