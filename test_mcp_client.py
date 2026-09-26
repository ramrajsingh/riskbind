"""
Quick MCP client smoke test: connects to both servers over
streamable-http, lists their tools, and runs the full pipeline for one
agent -- proving real MCP tool-call plumbing, not just HTTP health checks.
"""
import asyncio
import json
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def call(session: ClientSession, tool_name: str, args: dict):
    result = await session.call_tool(tool_name, args)

    # Prefer structuredContent. FastMCP emits one text block PER ITEM for a
    # tool that returns a list, so reading content[0] alone silently drops
    # every agent but the first out of list_agents.
    structured = result.structuredContent
    if isinstance(structured, dict):
        # List returns are wrapped as {"result": [...]}; dict returns are not.
        return structured["result"] if set(structured) == {"result"} else structured

    text = result.content[0].text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


async def main():
    async with streamablehttp_client("http://127.0.0.1:8000/mcp") as (r1, w1, _):
        async with ClientSession(r1, w1) as activity_session:
            await activity_session.initialize()
            tools = await activity_session.list_tools()
            print("activity server tools:", [t.name for t in tools.tools])

            agents = await call(activity_session, "list_agents", {})
            print(f"agents ({len(agents)}):", [a["agent_id"] for a in agents])

            activity = await call(activity_session, "get_agent_activity",
                                   {"agent_id": "agent-risky-01"})
            print("activity:", activity)

    async with streamablehttp_client("http://127.0.0.1:8001/mcp") as (r2, w2, _):
        async with ClientSession(r2, w2) as policy_session:
            await policy_session.initialize()
            tools = await policy_session.list_tools()
            print("policy server tools:", [t.name for t in tools.tools])

            # Feed a fabricated risk_model output through the quote+bind chain
            risk_result = {
                "agent_id": "agent-risky-01", "risk_score": 100.0, "tier": "decline",
                "premium_multiplier": None, "credibility_z": 0.06, "rationale": "test",
            }
            quote = await call(policy_session, "draft_policy_quote",
                                {"risk_result": risk_result})
            print("quote:", quote)

            refused = await call(policy_session, "bind_or_flag",
                                  {"quote": quote, "human_confirmed": False})
            print("bind_or_flag (unconfirmed):", refused)

            written = await call(policy_session, "bind_or_flag",
                                  {"quote": quote, "human_confirmed": True})
            print("bind_or_flag (confirmed):", written)


if __name__ == "__main__":
    asyncio.run(main())
