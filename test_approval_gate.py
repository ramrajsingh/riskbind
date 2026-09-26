"""
test_approval_gate.py

Guards the single most important property of this project, and the literal
judging criterion: TrueForge must pause for human approval before
`bind_or_flag` -- the irreversible ledger write -- and must NOT pause on
anything else.

How TrueForge actually decides this (read out of @truefoundry/trueforge-core
0.2.1, `dist/core/mcp/toolSelectors.mjs`):

    isDestructive(annotations)  ->  annotations?.destructiveHint === true
    toolRequiresApproval(name, annotations, selectors)
        -> true if any selector is a matching tag OR literally equals `name`
    DEFAULT_REQUIRE_APPROVAL_FOR_TOOLS = ["@destructive"]

Two things follow, and both are easy to get wrong:

  * The `@destructive` tag resolves from the MCP tool's OWN annotations, as
    returned by list_tools over the wire. It is NOT read from any field in
    agent-spec.json. A tool with no annotations is treated as ordinary and
    fires with no prompt at all.
  * `require_approval_for_tools` also matches literal tool names, which is
    why agent-spec.json lists "bind_or_flag" alongside "@destructive" --
    belt and braces, so the pause survives someone dropping the annotation.

The functions below are a direct port of that TypeScript. The port was
cross-checked once by running TrueForge's real ToolSelectorPolicy against
these servers' live annotations; this test keeps it honest without needing
node or a TrueForge checkout in CI.

Run (servers must be up on :8000 and :8001):
    python3 test_approval_gate.py
"""

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

SPEC_PATH = Path(__file__).with_name("agent-spec.json")

SERVER_URLS = {
    "agent-activity-source": "http://127.0.0.1:8000/mcp",
    "policy-ledger": "http://127.0.0.1:8001/mcp",
}

# The one tool in this project that must pause. Anything else pausing is a
# bug too -- an approval prompt on every read makes the demo unwatchable.
MUST_PAUSE = {"policy-ledger/bind_or_flag"}


# --- port of trueforge-core/dist/core/mcp/toolSelectors.mjs -----------------

TOOL_TAGS = ("@all", "@read-only", "@write", "@destructive")


def _is_read_only(ann: dict | None) -> bool:
    return ann is not None and ann.get("readOnlyHint") is True


def _is_write(ann: dict | None) -> bool:
    return (ann is not None
            and ann.get("readOnlyHint") is False
            and ann.get("destructiveHint") is not True)


def _is_destructive(ann: dict | None) -> bool:
    return ann is not None and ann.get("destructiveHint") is True


def _tool_matches_tag(tag: str, ann: dict | None) -> bool:
    return {
        "@all": True,
        "@read-only": _is_read_only(ann),
        "@write": _is_write(ann),
        "@destructive": _is_destructive(ann),
    }[tag]


def tool_requires_approval(name: str, ann: dict | None, selectors) -> bool:
    """Mirror of toolRequiresApproval(). Empty/missing selectors => never."""
    if not selectors:
        return False
    for sel in selectors:
        if sel in TOOL_TAGS:
            if _tool_matches_tag(sel, ann):
                return True
        elif sel == name:
            return True
    return False


# --- live tool discovery ---------------------------------------------------

async def _list_tools(url: str) -> list[tuple[str, dict | None]]:
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return [
                (t.name,
                 t.annotations.model_dump(exclude_none=True) if t.annotations else None)
                for t in (await session.list_tools()).tools
            ]


def main() -> int:
    spec = json.loads(SPEC_PATH.read_text())
    servers = spec["manifest"]["mcp_servers"]

    pausing: set[str] = set()
    unannotated: list[str] = []

    for srv in servers:
        name = srv["name"]
        selectors = srv.get("require_approval_for_tools", ["@destructive"])
        try:
            tools = asyncio.run(_list_tools(SERVER_URLS[name]))
        except Exception as exc:
            print(f"FAIL: could not reach {name} at {SERVER_URLS[name]}: {exc}")
            print("      Start both servers first (see README Setup).")
            return 1

        print(f"\n{name}  require_approval_for_tools={selectors}")
        for tool_name, ann in tools:
            needs = tool_requires_approval(tool_name, ann, selectors)
            if needs:
                pausing.add(f"{name}/{tool_name}")
            if ann is None:
                unannotated.append(f"{name}/{tool_name}")
            print(f"  {'PAUSE ' if needs else '  run '} {tool_name:<20} {ann}")

    print("\nPauses for human approval:", sorted(pausing) or "(nothing)")

    ok = True
    if pausing != MUST_PAUSE:
        missing = MUST_PAUSE - pausing
        extra = pausing - MUST_PAUSE
        if missing:
            print(f"FAIL: these must pause but do not: {sorted(missing)}")
            print("      Most likely the ToolAnnotations(destructiveHint=True) was "
                  "dropped from the tool decorator.")
        if extra:
            print(f"FAIL: these pause but should not: {sorted(extra)}")
        ok = False

    if unannotated:
        # Not fatal on its own, but an unannotated tool is invisible to every
        # selector tag -- it can never be gated, and Code Mode treats it as safe.
        print(f"WARN: tools with no annotations at all: {unannotated}")

    print("\nPASS: exactly the irreversible step pauses." if ok else "\nFAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
