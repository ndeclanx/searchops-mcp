# SPDX-License-Identifier: MIT

"""MCPServer instantiation, annotations, and boot logic.

This module creates the shared MCPServer instance (``mcp``) and defines the
tool annotation constants.  Tool modules register themselves via decorators
when imported at the bottom of this file — the circular import is safe because
``mcp`` and annotations are defined before those imports execute.
"""

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from gsc_telemetry import (
    MCP_SERVER_VERSION,
    send_telemetry,
    mark_boot_events,
)
from searchops import errors


# ---------------------------------------------------------------------------
# Server instructions (sent to the client on initialize)
# ---------------------------------------------------------------------------
GSC_MCP_INSTRUCTIONS = """\
Google Search Console Data API access for AI agents — query with schema-accurate names, interpret with skills.

How to work with this server:
1. DISCOVER names before querying: call list_available_dimensions and list_available_metrics to get the exact valid dimensions and metrics in THIS property. Never guess.
2. INTERPRET with skills: for anything beyond a raw pull, call skills_list first — the skills library has proven field combinations and how to read the result. Fetch the full playbook with skill_read.
3. RECOVER from setup errors in-chat: if a tool reports a configuration or authentication error, call setup_gsc_access — it can collect the missing value interactively when the client supports prompts.
"""

# ---------------------------------------------------------------------------
# MCPServer instance (shared across all tool modules)
# ---------------------------------------------------------------------------
mcp = MCPServer(
    "Google Search Console",
    version=MCP_SERVER_VERSION if MCP_SERVER_VERSION != "unknown" else "0.0.0",
    instructions=GSC_MCP_INSTRUCTIONS,
    website_url="https://github.com/surendranb/google-search-console-mcp",
)

# ---------------------------------------------------------------------------
# tools_listed telemetry hook
# ---------------------------------------------------------------------------
async def _list_tools_with_telemetry():
    tools = await mcp._list_tools_orig()
    send_telemetry("tools_listed", {"tool_count": len(tools)})
    return tools


mcp._list_tools_orig = mcp.list_tools
mcp.list_tools = _list_tools_with_telemetry

# ---------------------------------------------------------------------------
# S1: tool annotations (Protocol Surfaces v1)
# ---------------------------------------------------------------------------
_ANNOTATIONS_READ_LOCAL = ToolAnnotations(
    read_only_hint=True, idempotent_hint=True, open_world_hint=False)
_ANNOTATIONS_READ_API = ToolAnnotations(
    read_only_hint=True, idempotent_hint=True, open_world_hint=True)
_ANNOTATIONS_WRITE_API = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True)
_ANNOTATIONS_DELETE_API = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=True)
_ANNOTATIONS_SETUP = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True)


# ---------------------------------------------------------------------------
# Import tool modules to trigger @mcp.tool() registration.
# mcp and annotations are already defined above, so the circular import is
# safe: Python returns this partially-initialized module when the tool
# modules do `from searchops.server import mcp`.
# ---------------------------------------------------------------------------
import searchops.tools.gsc       # noqa: E402,F401
import searchops.tools.schema    # noqa: E402,F401
import searchops.tools.skills    # noqa: E402,F401
import searchops.tools.updates   # noqa: E402,F401
import searchops.prompts         # noqa: E402,F401
import searchops.resources       # noqa: E402,F401


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    """Main entry point for the MCP server."""
    import sys
    print("Starting GSC MCP server...", file=sys.stderr)
    mark_boot_events()
    send_telemetry("mcp_started", {"config_status": "error" if errors.SERVER_INIT_ERROR else "success"})
    mcp.run(transport="stdio")
