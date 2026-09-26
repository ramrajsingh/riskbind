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

# The only tiers risk_model.py can emit, and the multiplier each one carries.
# draft_policy_quote refuses anything else: a quote is only meaningful if the
# numbers behind it actually came out of the model.
VALID_TIERS = {
    "preferred": 0.85,
    "standard": 1.0,
    "substandard": 1.6,
    "decline": None,
}
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


def _validate_risk_result(risk_result: dict) -> None:
    """
    Reject anything that cannot have come out of risk_model.score_agent.

    This exists because an agent that fails to run the risk model will
    cheerfully invent a plausible-looking risk_result and pass it here --
    observed in practice: tier "low", credibility_z 1.8. Quoting on
    fabricated numbers is worse than failing, because the output looks
    exactly like a real quote. Fail loudly instead, so the agent sees the
    error and has to go and actually run the model.
    """
    if not isinstance(risk_result, dict):
        raise ValueError("risk_result must be an object from risk_model.py")

    for field in ("agent_id", "risk_score", "tier"):
        if field not in risk_result:
            raise ValueError(f"risk_result is missing '{field}'; it must be the "
                             f"unmodified JSON output of risk_model.py")

    tier = risk_result["tier"]
    if tier not in VALID_TIERS:
        raise ValueError(
            f"unknown tier {tier!r}. risk_model.py only ever emits "
            f"{sorted(VALID_TIERS)}. This risk_result did not come from the "
            f"risk model -- run it on the activity data and pass its output through unchanged."
        )

    score = risk_result["risk_score"]
    if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= score <= 100:
        raise ValueError(f"risk_score must be a number in 0..100, got {score!r}")

    z = risk_result.get("credibility_z")
    if z is not None and (not isinstance(z, (int, float)) or isinstance(z, bool) or not 0 <= z <= 1):
        raise ValueError(f"credibility_z must be a number in 0..1, got {z!r}")

    expected = VALID_TIERS[tier]
    actual = risk_result.get("premium_multiplier")
    if expected is None:
        if actual is not None:
            raise ValueError(f"tier 'decline' carries no premium_multiplier, got {actual!r}")
    elif actual is None or abs(float(actual) - expected) > 1e-9:
        raise ValueError(
            f"tier {tier!r} carries premium_multiplier {expected}, got {actual!r}. "
            f"The tier and multiplier disagree, so this risk_result was not produced "
            f"by risk_model.py."
        )


def draft_policy_quote(risk_result: dict) -> PolicyQuote:
    """
    risk_result is exactly the JSON risk_model.score_agent produces:
    {agent_id, risk_score, tier, premium_multiplier, credibility_z, rationale}

    Validated on the way in -- see _validate_risk_result.
    """
    _validate_risk_result(risk_result)

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
