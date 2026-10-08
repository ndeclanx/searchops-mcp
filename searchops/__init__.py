# SPDX-License-Identifier: MIT

"""SearchOps MCP — modular package root."""

from pathlib import Path

# Anchor for locating data files (gsc_dimensions.json, skills/, etc.)
# that live alongside gsc_mcp_server.py at the package root.
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
