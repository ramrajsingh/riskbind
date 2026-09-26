# Riskbind — 3:00 demo video script

Rubric: **3:00 hard cap**, MP4 1080p, audio narration *or* captions, and
**at least 30 seconds showing TrueForge in use**. This script spends
~1:50 inside TrueForge, comfortably over that bar.

Word counts assume ~150 wpm. Total narration is ~380 words, leaving slack
for tool latency.

## Before you hit record

```bash
cd /Users/apple/proj/riskbind && : > policy_ledger.jsonl
```

- TrueForge UI at **http://localhost:8790**, session open, window large
  enough that tool names are legible at 1080p.
- A terminal beside it running `tail -f policy_ledger.jsonl`. This pane is
  the point — it is how a viewer sees that nothing was written until a
  human said yes.
- Close anything with personal content. You are publishing this.

## 0:00–0:20 — the hook (~45 words)

> "Everyone at this hackathon built an agent that acts. I built the thing
> that prices what happens when one acts wrong.
>
> Riskbind is an insurance company that underwrites AI agents — and it
> underwrites them using an AI agent. I'm an actuary; this is the
> day job, pointed at the room."

## 0:20–0:50 — the pipeline, on screen (~70 words)

Show `agent-spec.json`, then switch to TrueForge.

> "Four steps. Pull the agent's real activity over MCP. Score it in a
> sandbox. Draft a quote. Then stop — and wait for a human — before
> binding anything.
>
> Those first three are safe. The fourth writes a policy and can't be
> undone. That asymmetry is the whole design."

## 0:50–1:50 — the live run (~130 words) — THIS IS THE ≥30s SEGMENT

Type into TrueForge: `Underwrite agent-safe-01.`

Narrate against what appears, pausing when the approval card shows:

> "`get_agent_activity` — a real MCP call to a real server. 240 actions,
> 2 flagged, largest exposure eighty dollars.
>
> Now the risk model runs in TrueForge's sandbox. Three signals:
> flagged-action frequency, severity against the portfolio baseline, and
> a Bühlmann credibility weight. 240 actions is full credibility — we
> trust this agent's own track record completely. Score: 5.64.
> Preferred tier. Eight hundred and fifty dollars."

**Stop talking when the approval prompt appears. Let it sit for two
seconds.** Point at the ledger pane.

> "And it stops. It will not bind without me. Ledger's still empty."

Click approve.

> "Now it's a policy."

The line appears in the tail pane. Let the viewer read it.

## 1:50–2:30 — the other two outcomes (~90 words)

`Now underwrite agent-risky-01.`

> "Same pipeline. Twelve actions, one nine-thousand-dollar exposure.
> Score 100 — declined, no premium offered. And notice it pauses here
> too: declining is also a binding decision, so it also needs a human.
>
> And agent-borderline-01 — sixty actions, not enough history to trust on
> its own, so the model shrinks it toward the book average. Sixty-one
> point two. Substandard, sixteen hundred, flagged for a human
> underwriter. Not a decline. Not an auto-bind."

## 2:30–3:00 — close on the guarantee (~70 words)

> "Three independent things stop that irreversible step. TrueForge pauses
> on the tool's destructive annotation. The sandbox refuses to call
> non-read-only tools at all. And the tool itself refuses to write
> without explicit confirmation.
>
> I found that first one the hard way — my agent spec looked right, and
> the pause was never going to fire. Real underwriting is mostly finding
> the thing that was quietly not true."

## If you'd rather not type live

Claude can fire each step through the TrueForge API on your cue while you
narrate — deterministic timing, no alt-tabbing. Say "go" per beat.

## What not to claim

- Don't say credibility drove the `agent-risky-01` decline. It didn't —
  shrinkage pulls that agent's frequency *down* (41.67 → 10.02). Severity
  drove it. See DEMO.md's Q&A section.
- Don't call the demo agents live data. They're canned fixtures in the
  activity server, deliberately, so the demo has no network dependency.
  The README says so and the rubric asks for real-vs-mocked explicitly.
