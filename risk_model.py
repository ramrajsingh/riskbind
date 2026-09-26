"""
risk_model.py

Simplified, hackathon-scale version of the RMI Agentic Payment Insurance
scoring logic. Takes an agent's recent activity + portfolio context and
returns a risk score, tier, and a suggested premium multiplier.

This intentionally leaves out the full compound Poisson / Cox jump-diffusion
/ Gumbel copula machinery from the v5.0 spec -- for a one-day demo you want
one formula that's fast to explain on stage, not a due-diligence model.
It keeps the shape of the real pipeline: frequency signal, severity signal,
credibility-weighted blend, tiered output.

Meant to be invoked as a TrueForge sandbox tool: reads JSON on stdin,
writes JSON on stdout, so it can be wired in as a subprocess/script tool
regardless of which language the rest of the agent is in.
"""

import json
import sys
from dataclasses import dataclass, asdict


# --- Portfolio priors -------------------------------------------------
# Stand-in for the peer-group experience your Bühlmann credibility
# weighting blends against when an agent has thin history. In production
# these would come from your actual book of business.
PORTFOLIO_MEAN_FREQUENCY = 0.08   # baseline "bad action" rate per 100 actions
PORTFOLIO_MEAN_SEVERITY = 500.0   # baseline dollar exposure per flagged action

# Credibility full-weight threshold: an agent needs at least this many
# observed actions before its own history fully dominates the score.
FULL_CREDIBILITY_ACTIONS = 200


@dataclass
class RiskResult:
    agent_id: str
    risk_score: float          # 0-100, higher = riskier
    tier: str                  # "preferred" | "standard" | "substandard" | "decline"
    premium_multiplier: float  # applied to a flat base premium
    credibility_z: float       # 0-1, how much weight went to the agent's own data
    rationale: str


def credibility_weight(n_actions: int) -> float:
    """Bühlmann-style shrinkage: Z -> 1 as an agent accumulates history."""
    return min(1.0, n_actions / FULL_CREDIBILITY_ACTIONS)


def score_agent(activity: dict) -> RiskResult:
    """
    activity expected shape:
    {
        "agent_id": str,
        "n_actions": int,               # actions observed in the review window
        "n_flagged_actions": int,       # actions that tripped a rule/anomaly check
        "max_single_exposure": float,   # largest single action's dollar/permission exposure
    }
    """
    agent_id = activity["agent_id"]
    n_actions = max(activity.get("n_actions", 0), 1)  # avoid div-by-zero
    n_flagged = activity.get("n_flagged_actions", 0)
    max_exposure = activity.get("max_single_exposure", 0.0)

    # Frequency signal: observed flag rate per 100 actions
    own_frequency = (n_flagged / n_actions) * 100

    # Severity signal: largest exposure vs. portfolio baseline
    severity_ratio = max_exposure / PORTFOLIO_MEAN_SEVERITY if PORTFOLIO_MEAN_SEVERITY else 0

    # Credibility blend on the frequency signal (the piece that needs
    # enough history to trust on its own)
    z = credibility_weight(n_actions)
    blended_frequency = z * own_frequency + (1 - z) * (PORTFOLIO_MEAN_FREQUENCY * 100)

    # Combine into a single 0-100 risk score. Weights are illustrative --
    # tune live during the demo if you have time.
    raw_score = (0.6 * blended_frequency * 10) + (0.4 * severity_ratio * 10)
    risk_score = max(0.0, min(100.0, raw_score))

    if risk_score < 20:
        tier, multiplier = "preferred", 0.85
    elif risk_score < 45:
        tier, multiplier = "standard", 1.0
    elif risk_score < 70:
        tier, multiplier = "substandard", 1.6
    else:
        tier, multiplier = "decline", float("inf")

    rationale = (
        f"n_actions={n_actions}, flagged={n_flagged} "
        f"(own_freq={own_frequency:.2f}/100, blended={blended_frequency:.2f}/100, Z={z:.2f}); "
        f"max_exposure={max_exposure:.0f} (severity_ratio={severity_ratio:.2f})"
    )

    return RiskResult(
        agent_id=agent_id,
        risk_score=round(risk_score, 2),
        tier=tier,
        premium_multiplier=multiplier,
        credibility_z=round(z, 3),
        rationale=rationale,
    )


def main():
    raw = sys.stdin.read()
    activity = json.loads(raw)
    result = score_agent(activity)
    out = asdict(result)
    # inf doesn't survive JSON encoding cleanly -- represent "decline" explicitly
    if out["premium_multiplier"] == float("inf"):
        out["premium_multiplier"] = None
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
