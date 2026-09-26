# Riskbind

Underwriting-side agent for TrueForge — reviews another AI agent's
activity, scores it with a simplified Bühlmann-credibility risk model,
drafts a policy quote, and pauses for a human before binding, flagging,
or declining coverage. Built for the TrueFoundry × Polaris hackathon
("Agents That Act").

The pitch: an insurance company underwriting an AI agent, live, using an
AI agent.

## Submission writeup

**Problem.** Autonomous agents now move money and change permissions, and
nothing prices what happens when one acts wrong. Riskbind is the
underwriting side of that: an insurer that reviews an agent's behaviour,
prices the risk, and binds, loads, or declines cover.

**What the agent reaches.** `get_agent_activity`, on a real MCP server
over streamable-http, returns a monitored agent's recent history: how many
actions, how many tripped a rule check, and the largest single exposure.

**Where it stops.** `bind_or_flag` writes a binding decision to the policy
ledger. It is annotated `destructiveHint=true`, so TrueForge pauses for
human approval before it runs — including on declines, which are binding
decisions too.

**Architecture.** `get_agent_activity` (MCP) → `run_risk_model` (sandboxed
skill) → `draft_policy_quote` (safe) → **approval pause** → `bind_or_flag`
(irreversible). The model blends flagged-action frequency, severity
against a portfolio baseline, and a Bühlmann credibility weight — full
credibility at 200 observed actions — into a 0–100 score, tiered
preferred / standard / substandard / decline.

**How TrueForge was used.** Both MCP servers are registered as
connectors; the risk model is a git skill run in TrueForge's sandbox.
Verified end to end on 0.2.1: activity pulled live, scored in the sandbox
to 5.64 / preferred / $850, `tool.approval_required` raised at
`bind_or_flag`, ledger empty until approval, written only after. Three
independent guards stop the irreversible step: the approval pause, Code
Mode's refusal to call any non-read-only tool, and the tool's own
`human_confirmed` check.

**Real vs mocked.** Real: both MCP servers, the scoring, the ledger
writes, and the approval gating — `test_approval_gate.py` asserts that
`bind_or_flag`, and only `bind_or_flag`, pauses. Mocked: the three demo
agents are canned fixtures inside the activity server, chosen over a live
API so the demo carries no network dependency. Pointing them at Stripe
test-mode payment history changes one function body, not the tool
contract.

**Known limits.** The risk model is deliberately simplified; the
production work uses compound Poisson, Cox jump-diffusion and Gumbel
copulas. Portfolio priors are hardcoded rather than fitted. The ledger is
an append-only JSON-lines file standing in for a system of record.

## Pipeline

```
get_agent_activity  -->  run_risk_model  -->  draft_policy_quote  -->  [PAUSE: human approval]  -->  bind_or_flag
   (real MCP call)         (sandboxed)          (safe, no side effects)                                (writes ledger)
```

## Project layout

- `mcp_activity_server.py` — real MCP server (FastMCP) for
  `agent-activity-source`. Exposes `list_agents`, `get_agent_activity`,
  `log_action`. Three canned demo agents: `agent-risky-01`,
  `agent-safe-01`, `agent-borderline-01`.
- `mcp_policy_server.py` — real MCP server for `policy-ledger`. Exposes
  `draft_policy_quote` (safe) and `bind_or_flag` (irreversible — refuses
  to write without `human_confirmed=true`).
- `activity_source.py` / `policy_tools.py` — the underlying plain
  FastAPI/CLI logic that the two MCP servers wrap. `policy_tools.py` also
  owns the ledger-write logic.
- `risk_model.py` — the scoring logic itself: frequency signal + severity
  signal + Bühlmann credibility blend, tiered into
  preferred/standard/substandard/decline.
- `test_mcp_client.py` — a real MCP client smoke test: connects to both
  servers, lists tools, runs the full pipeline. Run this first if
  anything seems off.
- `test_approval_gate.py` — asserts that `bind_or_flag`, and only
  `bind_or_flag`, pauses for human approval. See "The approval pause"
  below; this is the judging criterion, so run it before the demo.
- `agent-spec.json` — the TrueForge agent definition, shaped as a
  `POST /agents` body (`{name, description, manifest}`), validated
  against `AgentSpecSchema` from `@truefoundry/trueforge-core` 0.2.1.

## The approval pause

The pause is **driven by MCP tool annotations, not by anything in
`agent-spec.json`.** TrueForge resolves its `@destructive` tag like this
(`trueforge-core/dist/core/mcp/toolSelectors.mjs`):

```js
isDestructive(annotations) => annotations?.destructiveHint === true
DEFAULT_REQUIRE_APPROVAL_FOR_TOOLS = ["@destructive"]
```

So a tool with no `annotations` is not destructive as far as TrueForge is
concerned — it just runs, with no prompt. `bind_or_flag` therefore
declares it at the tool:

```python
@mcp.tool(
    name="bind_or_flag",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
)
```

`require_approval_for_tools` also matches **literal tool names**, so the
spec lists `["@destructive", "bind_or_flag"]` — the pause survives even
if someone drops the annotation.

Two consequences worth knowing on stage:

- `readOnlyHint=True` on the read tools keeps them callable from inside
  Code Mode. TrueForge refuses to run anything non-read-only there
  ("call it directly so it can go through the user approval flow"), which
  is exactly why the irreversible step can't be smuggled through the
  sandbox. `log_action` is honestly marked as writing, so it too must be
  called directly.
- `config.sandbox.enabled` must be `true` — it defaults to **false**, and
  skills and Code Mode both need it. That's judging criterion #2.

There are three independent guards on the irreversible step: TrueForge's
approval pause, Code Mode's refusal to call destructive tools, and
`bind_or_flag`'s own `human_confirmed` check.

## Setup

A venv is required: `mcp[cli]>=1.9.1,<2` is specifically v1 — v2 renamed
`FastMCP` to `MCPServer`, so a system Python with mcp 2.x installed will
break the imports.

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

./.venv/bin/python3 mcp_activity_server.py &   # streamable-http on :8000
./.venv/bin/python3 mcp_policy_server.py &     # streamable-http on :8001

./.venv/bin/python3 test_mcp_client.py         # smoke test
./.venv/bin/python3 test_approval_gate.py      # the judging criterion
```

Then TrueForge itself (needs node >= 22.14):

```bash
npx @truefoundry/trueforge
```

The two MCP servers are registered **in TrueForge**, not in
`agent-spec.json` — `mcp_servers[].name` references a server configured
under Settings → Connectors (`PUT /settings/mcp-servers`), and the urls
`http://127.0.0.1:8000/mcp` / `http://127.0.0.1:8001/mcp` go there. The
names must match `agent-activity-source` and `policy-ledger` exactly.

`manifest.model.name` must be a `provider/model` FQN where the provider
segment names a configured model provider, so `openai/gpt-5-4-mini`
assumes the OpenAI provider is registered as `openai`. TrueForge also
ships presets for `anthropic`, `google-gemini`, `alibaba`, `fireworks`,
`moonshot`, `together`, `zai`, and `custom` — swapping providers is a
one-line change and does not affect the approval pause, which the harness
enforces from the tool annotation regardless of model.

TrueForge blocks loopback URLs by default, so it will reject both MCP
servers unless you start it with them allowed:

```bash
OUTBOUND_URL_ALLOWED_HOSTS='["127.0.0.1","localhost","::1"]' npx @truefoundry/trueforge
```

## Demo script

See [DEMO.md](DEMO.md) — timed beats, the verified numbers, a pre-flight
checklist, a fallback for when TrueForge misbehaves on stage, and the
questions to expect.

The spread, in one line each:

1. **agent-safe-01** (240 clean actions, Z=1.0) → 5.64 → **preferred,
   $850** → auto-bind. This is the run that shows the approval pause.
2. **agent-risky-01** (12 actions, one $9,000 exposure) → 100 →
   **decline**. Pauses too: declining is also a binding decision.
3. **agent-borderline-01** (60 actions, Z=0.3) → 61.2 → **substandard,
   $1,600** → flagged for review.

## Still open

- [x] ~~End-to-end run against a live TrueForge instance.~~ Done on
      0.2.1 — approval fired at `bind_or_flag`, ledger written only after
      approval. Two host prerequisites, both easy to trip over:
      `OUTBOUND_URL_ALLOWED_HOSTS` (above), and **git must come from
      Homebrew** — the sandbox deliberately does not allow-read the Xcode
      select paths, so `/usr/bin/git` is a shim that fails inside it and
      skills never clone (`brew install git`).
- [x] ~~Point the demo agents at a live external source.~~ **Decided:
      they stay local.** No venue-wifi dependency on stage, and it's
      still a real MCP call. The tool contract is `agent_id` in, activity
      out — swapping `_AGENTS` for Stripe test-mode payment history is a
      one-function change if it's ever wanted.
- [ ] Rehearse [DEMO.md](DEMO.md), including the fallback path.
- [ ] Build-story post for the community prize (tag @truefoundry and
      @polariscodes).

## Credit

The MCP server pattern (`FastMCP`, `@mcp.tool()`, `/health` route,
`streamable-http`) is modeled on TrueFoundry's own reference example at
`truefoundry/agentic-ai-with-truefoundry`, module10,
`deploying_your_custom_mcp_server/financial_analyst/server.py`.
