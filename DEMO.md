# Riskbind — 90-second demo script

Three agents, one pipeline, three different outcomes. Every number below
was produced by an actual run, not estimated — re-verify with
`./.venv/bin/python3 test_mcp_client.py` if you change the model.

## Pre-flight (do this before you're called up)

```bash
./.venv/bin/python3 mcp_activity_server.py &   # :8000
./.venv/bin/python3 mcp_policy_server.py &     # :8001
./.venv/bin/python3 test_approval_gate.py      # must print PASS
: > policy_ledger.jsonl                        # start from an empty ledger
```

Screen layout: TrueForge chat on the left, a terminal running
`tail -f policy_ledger.jsonl` on the right. The ledger pane is what makes
the irreversible step *visible* — a line appears only when a human
approves. Don't demo without it.

Have all three agent ids pasted somewhere you can grab them; don't type
them live.

## The 90 seconds

### 0:00–0:12 — the hook

> "This is an insurance company underwriting an AI agent. Live. Using an
> AI agent. I'm an actuary — I work on agentic payment insurance — and
> everyone here today built an agent that *acts*. I built the thing that
> prices what happens when it acts wrong."

### 0:12–0:45 — agent-safe-01: the approval pause

Type: `Underwrite agent-safe-01.`

What happens, and what to point at:

| On screen | Say |
|---|---|
| `get_agent_activity` → 240 actions, 2 flagged, max exposure $80 | "Real MCP call to a real server — that's criterion one." |
| risk model runs in the sandbox → score **5.64**, Z = **1.0** | "Scored in the sandbox. 240 actions means full credibility — we trust this agent's own track record completely." |
| `draft_policy_quote` → **preferred**, ×0.85, **$850** | "Preferred tier. 15% off the base premium." |
| **approval prompt appears** | *Stop talking. Let it sit for a beat.* "It will not bind without me. This is the irreversible step, and the harness stopped it." |
| Approve → ledger line appears in the right pane | "Now it's a real policy." |

That one run covers all three judging criteria. If you only get through
this beat, you have still shown everything the brief asked for.

### 0:45–1:10 — agent-risky-01: same pipeline, opposite answer

Type: `Now agent-risky-01.`

- 12 actions, 5 flagged, one **$9,000** exposure → score **100** →
  **decline**, no premium offered.
- **The pause fires here too.** Say so: *"Declining is also a binding
  decision — it goes in the ledger, so it also needs a human."* That's
  the point most people miss, and it's the strongest thing you can say
  about the design.

### 1:10–1:25 — agent-borderline-01: the interesting one

Type: `And agent-borderline-01.`

- 60 actions, 6 flagged, $1,200 exposure → Z = **0.3** → score **61.2** →
  **substandard**, ×1.6, **$1,600**, recommendation **flag_for_review**.
- "Sixty actions isn't enough history to trust on its own, so the model
  shrinks this agent toward the portfolio mean — Z of 0.3. Not a decline.
  Not an auto-bind. Priced, and sent to a human underwriter."

### 1:25–1:30 — close

> "Same pipeline, three outcomes: declined, bound, flagged. Three
> independent guards stop the irreversible step — the harness's approval
> pause, the sandbox refusing to call destructive tools at all, and the
> tool's own confirmation check. That's what underwriting an agent
> actually looks like."

## The numbers, verified

| Agent | Actions | Flagged | Max exposure | Z | Score | Tier | Outcome |
|---|---|---|---|---|---|---|---|
| `agent-safe-01` | 240 | 2 | $80 | 1.00 | **5.64** | preferred (×0.85) | auto_bind, **$850** |
| `agent-borderline-01` | 60 | 6 | $1,200 | 0.30 | **61.2** | substandard (×1.6) | flag_for_review, **$1,600** |
| `agent-risky-01` | 12 | 5 | $9,000 | 0.06 | **100.0** | decline | no premium |

## If something breaks

- **Approval prompt doesn't appear** — the `destructiveHint` annotation is
  gone or the servers were restarted from stale code. Run
  `test_approval_gate.py`; it names the tool that stopped pausing.
- **Servers unreachable** — `test_mcp_client.py` is the fastest triage; it
  prints tool lists before it calls anything.
- **TrueForge itself misbehaves** — fall back to
  `./.venv/bin/python3 test_mcp_client.py`, which walks the same pipeline
  over real MCP and shows `bind_or_flag` refusing without confirmation.
  Narrate it as "here's the same thing without the harness in the way."
  Rehearse this fallback once; it's ~20 seconds and it saves the demo.

## Questions to expect

**"Is the risk model real?"** Be straight: no, it's deliberately
simplified. The production work uses compound Poisson, Cox jump-diffusion
and Gumbel copulas. What survived into this demo is the *shape* —
frequency, severity, and a real Bühlmann credibility blend — because
that's what fits on a screen in a minute.

**"Where does credibility actually change the answer?"** The honest
answer, and worth pre-loading because it's the one place the story could
look overstated: on `agent-borderline-01` (own frequency 10.0 → blended
8.6) and on `agent-safe-01` (Z = 1.0, own experience fully trusted). On
`agent-risky-01` shrinkage actually pulls frequency *down* — 41.67 → 10.02
— because 12 actions is too thin to trust. That agent is declined on
**severity**: a $9,000 exposure against a $500 portfolio baseline is a
severity ratio of 18, and the raw score of 132 clamps to 100. Don't claim
credibility is what declined it; a sharp judge will check.

**"What stops the agent from just calling bind itself?"** Three things,
in order: TrueForge pauses on the `destructiveHint` annotation; Code Mode
refuses to call any non-read-only tool from inside the sandbox ("call it
directly so it can go through the user approval flow"); and `bind_or_flag`
itself returns `refused` without `human_confirmed=true`. The prompt
instruction is the *weakest* of the four and is not relied on.

**"Are the agents real?"** The activity source is a real MCP server with
canned agents — deliberate, so the demo doesn't depend on venue wifi. The
tool contract is `agent_id` in, activity out; pointing it at Stripe
test-mode payment history is a swap of one function body.
