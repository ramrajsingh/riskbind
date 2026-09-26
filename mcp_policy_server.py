"""
mcp_policy_server.py

"policy-ledger" as a real MCP server, matching the "mcp_servers" entry
tagged @destructive in agent-spec.json. This is the server TrueForge
should pause in front of before bind_or_flag actually fires.

Wraps the same logic as policy_tools.py (kept there as plain, testable
Python) behind MCP tool decorators, following the same FastMCP +
streamable-http + /health pattern as mcp_activity_server.py and
TrueFoundry's own financial_analyst/server.py reference.

Run on a different port from the activity server:
    pip install "mcp[cli]>=1.9.1,<2"
    python3 mcp_policy_server.py
    # serves over streamable-http on 0.0.0.0:8001
"""

import os

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse

from policy_tools import draft_policy_quote as _draft_policy_quote
from policy_tools import bind_or_flag as _bind_or_flag
from dataclasses import asdict

mcp = FastMCP("policy-ledger", stateless_http=True)


@mcp.tool(
    name="draft_policy_quote",
    description="Safe, side-effect-free step. Takes the risk_model output "
                "(agent_id, risk_score, tier, premium_multiplier, credibility_z, rationale) "
                "and turns it into a policy quote with a premium and a recommendation "
                "(auto_bind / flag_for_review / decline). Does not write anything.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
def draft_policy_quote(risk_result: dict) -> dict:
    return asdict(_draft_policy_quote(risk_result))


@mcp.tool(
    name="bind_or_flag",
    description="IRREVERSIBLE. Writes the final bind/flag/decline decision to the "
                "policy ledger. Must only be called after a human has explicitly "
                "confirmed the quote in this session -- pass human_confirmed=true only "
                "once that confirmation has actually happened. This tool is tagged "
                "@destructive so TrueForge should pause and ask for approval before "
                "calling it regardless of what the agent's own reasoning concludes.",
    # This is what actually makes TrueForge pause. Its `@destructive` tag
    # resolves via the MCP tool's own annotations (isDestructive() checks
    # `annotations.destructiveHint === true`), NOT via anything declared in
    # agent-spec.json -- and require_approval_for_tools defaults to
    # ["@destructive"]. Without destructiveHint here, this tool is treated as
    # ordinary and fires with no approval prompt at all.
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
)
def bind_or_flag(quote: dict, human_confirmed: bool = False) -> dict:
    return _bind_or_flag(quote, human_confirmed)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "OK"})


if __name__ == "__main__":
    mcp.settings.host = os.environ.get("RISKBIND_HOST", "0.0.0.0")
    mcp.settings.port = int(os.environ.get("RISKBIND_POLICY_PORT", "8001"))
    mcp.run(transport="streamable-http")
