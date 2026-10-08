# SPDX-License-Identifier: MIT

"""check_for_updates MCP tool."""

from gsc_telemetry import MCP_SERVER_VERSION
from searchops.instrument import instrument
from searchops.updates import check_server_update
from searchops.server import mcp, _ANNOTATIONS_READ_LOCAL


@mcp.tool(
    name="check_for_updates",
    description="Check PyPI for newer versions of this MCP server and get upgrade instructions.",
    annotations=_ANNOTATIONS_READ_LOCAL,
)
@instrument
def check_for_updates() -> dict:
    """Check PyPI for newer versions of google-search-console-mcp."""
    return check_server_update("google-search-console-mcp", MCP_SERVER_VERSION, force_check=True)
