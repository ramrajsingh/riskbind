"""
policy_tools.py

The last two tools in Riskbind's pipeline:

    get_agent_activity -> run_risk_model -> draft_policy_quote -> [PAUSE] -> bind_or_flag

Both are designed the same way as risk_model.py: read JSON on stdin,
write JSON on stdout, so TrueForge can mount either as a plain
subprocess/script sandbox tool regardless of the agent's own language.

draft_policy_quote is safe to run freely -- it just turns a risk_score/tier
into a human-readable quote object.

bind_or_flag is the IRREVERSIBLE step. It writes a real decision to a
policy ledger (here: an append-only JSON-lines file standing in for a
database/Slack post/sheet -- swap the write in `_write_ledger` for
whatever's actually visible in the room).

What makes TrueForge pause in front of it is the `destructiveHint=True`
annotation on the MCP tool that wraps this function, in
mcp_policy_server.py -- see README, "The approval pause". Nothing in
agent-spec.json and nothing in the instructions can substitute for that
annotation. The `human_confirmed` guard below is the last of three
independent checks, not the first.
"""

import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

BASE_PREMIUM = float(os.environ.get("RISKBIND_BASE_PREMIUM", "1000.0"))
LEDGER_PATH = Path(
    os.environ.get("RISKBIND_LEDGER_PATH", Path(__file__).parent / "policy_ledger.jsonl")
)


@dataclass
class PolicyQuote:
    agent_id: str
    risk_score: float
    tier: str
    recommendation: str        # "auto_bind" | "flag_for_review" | "decline"
    premium: float | None       # None when declined
    rationale: str


def draft_policy_quote(risk_result: dict) -> PolicyQuote:
    """
    risk_result is exactly the JSON risk_model.score_agent produces:
    {agent_id, risk_score, tier, premium_multiplier, credibility_z, rationale}
    """
    agent_id = risk_result["agent_id"]
    tier = risk_result["tier"]
    multiplier = risk_result.get("premium_multiplier")
    risk_score = risk_result["risk_score"]

    if tier == "decline" or multiplier is None:
        return PolicyQuote(
            agent_id=agent_id, risk_score=risk_score, tier=tier,
            recommendation="decline", premium=None,
            rationale=f"Declined: risk_score {risk_score} in decline band. "
                       f"{risk_result.get('rationale', '')}",
        )

    premium = round(BASE_PREMIUM * multiplier, 2)

    if tier == "preferred":
        recommendation = "auto_bind"
    elif tier == "standard":
        recommendation = "auto_bind"
    else:  # substandard
        recommendation = "flag_for_review"

    rationale = (
        f"tier={tier}, multiplier={multiplier}, premium={premium}. "
        f"{risk_result.get('rationale', '')}"
    )

    return PolicyQuote(
        agent_id=agent_id, risk_score=risk_score, tier=tier,
        recommendation=recommendation, premium=premium, rationale=rationale,
    )


def _write_ledger(entry: dict) -> None:
    """
    Append-only ledger write -- the visible, real side effect of
    bind_or_flag. Swap this for a Slack webhook post or a Google Sheet
    append if you want something more visually "live" in the demo;
    the JSONL file is the zero-dependency fallback that still counts
    as a real, persisted decision.
    """
    entry = {**entry, "written_at": time.time()}
    with open(LEDGER_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def bind_or_flag(quote: dict, human_confirmed: bool) -> dict:
    """
    THE IRREVERSIBLE STEP. TrueForge should already have paused before
    reaching here, because the MCP tool wrapping this function is
    annotated destructiveHint=True. human_confirmed is the belt-and-
    suspenders check underneath that: this function refuses to write
    anything if it is somehow invoked without confirmation having
    happened.
    """
    if not human_confirmed:
        return {
            "status": "refused",
            "reason": "bind_or_flag called without human_confirmed=True. "
                      "This tool must not fire until a human has approved "
                      "the quote in this session.",
        }

    decision = "bound" if quote["recommendation"] == "auto_bind" else \
               "flagged" if quote["recommendation"] == "flag_for_review" else \
               "declined"

    entry = {
        "agent_id": quote["agent_id"],
        "decision": decision,
        "premium": quote.get("premium"),
        "tier": quote["tier"],
        "risk_score": quote["risk_score"],
    }
    _write_ledger(entry)

    return {"status": "written", **entry}


def main():
    """
    CLI entrypoint for mounting as a TrueForge subprocess tool.
    Reads {"tool": "draft_policy_quote"|"bind_or_flag", "input": {...}}
    on stdin, writes the tool's JSON result on stdout.
    """
    raw = sys.stdin.read()
    payload = json.loads(raw)
    tool = payload["tool"]
    tool_input = payload["input"]

    if tool == "draft_policy_quote":
        result = asdict(draft_policy_quote(tool_input))
    elif tool == "bind_or_flag":
        result = bind_or_flag(tool_input["quote"], tool_input.get("human_confirmed", False))
    else:
        result = {"error": f"unknown tool: {tool}"}

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
