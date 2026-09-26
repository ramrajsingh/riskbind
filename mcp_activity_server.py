"""
mcp_activity_server.py

"agent-activity-source" as a REAL MCP server, not a plain REST API.

Structured after TrueFoundry's own reference pattern in
truefoundry/agentic-ai-with-truefoundry (module10, financial_analyst/server.py):
FastMCP app, @mcp.tool()-decorated functions, a /health route for
monitoring, served over streamable-http so TrueForge can mount it
directly as an MCP tool source (matches the "mcp_servers" entry named
"agent-activity-source" in agent-spec.json).

Swap the canned _AGENTS dict for a real Stripe test-mode account or a
GitHub Actions log later -- the tool contract (agent_id in, activity
dict out) stays the same either way.

Run:
    pip install "mcp[cli]>=1.9.1,<2"
    python3 mcp_activity_server.py
    # serves over streamable-http on 0.0.0.0:8000
"""

import os
import time
from dataclasses import dataclass, field
from typing import Dict, List

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse

mcp = FastMCP("agent-activity-source", stateless_http=True)


@dataclass
class Action:
    ts: float
    action_type: str
    exposure: float
    flagged: bool


@dataclass
class AgentRecord:
    agent_id: str
    display_name: str
    actions: List[Action] = field(default_factory=list)

    def as_activity(self) -> dict:
        n_actions = len(self.actions)
        n_flagged = sum(1 for a in self.actions if a.flagged)
        max_exposure = max((a.exposure for a in self.actions), default=0.0)
        return {
            "agent_id": self.agent_id,
            "n_actions": n_actions,
            "n_flagged_actions": n_flagged,
            "max_single_exposure": max_exposure,
        }


def _seed_actions(n: int, flagged_count: int, base_exposure: float, spike: float = None) -> List[Action]:
    now = time.time()
    actions = []
    for i in range(n):
        is_flagged = i < flagged_count
        exposure = spike if (spike and i == 0) else base_exposure
        actions.append(Action(ts=now - (n - i) * 60, action_type="api_call",
                               exposure=exposure, flagged=is_flagged))
    return actions


# Same three canned demo agents as the REST version -- risky, safe, borderline.
_AGENTS: Dict[str, AgentRecord] = {
    "agent-risky-01": AgentRecord(
        agent_id="agent-risky-01",
        display_name="New vendor-refund bot (thin history)",
        actions=_seed_actions(n=12, flagged_count=5, base_exposure=150, spike=9000),
    ),
    "agent-safe-01": AgentRecord(
        agent_id="agent-safe-01",
        display_name="Payroll reconciliation agent (2yr clean history)",
        actions=_seed_actions(n=240, flagged_count=2, base_exposure=80),
    ),
    "agent-borderline-01": AgentRecord(
        agent_id="agent-borderline-01",
        display_name="New support-refund agent (moderate exposure)",
        actions=_seed_actions(n=60, flagged_count=6, base_exposure=300, spike=1200),
    ),
}


@mcp.tool(
    name="list_agents",
    description="List all known agent_ids with their display name and action count. "
                "Use this to discover which agents are available to review.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
def list_agents() -> list[dict]:
    return [
        {"agent_id": rec.agent_id, "display_name": rec.display_name,
         "n_actions": len(rec.actions)}
        for rec in _AGENTS.values()
    ]


@mcp.tool(
    name="get_agent_activity",
    description="Pull a given agent's recent action history: total actions, "
                "how many were flagged by anomaly/rule checks, and the dollar/permission "
                "exposure of its single largest action. This is the real tool call the "
                "risk model scores against.",
    # readOnlyHint=True keeps this callable from inside the sandbox's Code
    # Mode; TrueForge blocks anything not marked read-only there.
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
def get_agent_activity(agent_id: str) -> dict:
    rec = _AGENTS.get(agent_id)
    if not rec:
        raise ValueError(f"unknown agent_id: {agent_id}")
    return rec.as_activity()


@mcp.tool(
    name="log_action",
    description="Append a synthetic action to an agent's history. Lets you demo "
                "live drift in the room instead of only static fixtures.",
    # Mutates state, so not read-only -- which also means TrueForge won't let
    # Code Mode call it. Call it directly during the demo. It is not
    # destructive, so it does not trigger an approval pause.
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def log_action(agent_id: str, action_type: str = "api_call",
               exposure: float = 100.0, flagged: bool = False) -> dict:
    rec = _AGENTS.get(agent_id)
    if not rec:
        raise ValueError(f"unknown agent_id: {agent_id}")
    rec.actions.append(Action(ts=time.time(), action_type=action_type,
                               exposure=exposure, flagged=flagged))
    return rec.as_activity()


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint for monitoring server status."""
    return JSONResponse({"status": "OK"})


if __name__ == "__main__":
    mcp.settings.host = os.environ.get("RISKBIND_HOST", "0.0.0.0")
    mcp.settings.port = int(os.environ.get("RISKBIND_ACTIVITY_PORT", "8000"))
    mcp.run(transport="streamable-http")
