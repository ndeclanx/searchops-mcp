# SPDX-License-Identifier: MIT

"""Schema discovery tools: dimensions and metrics."""

import json
from pathlib import Path

from mcp.server.mcpserver import Context

from searchops import PACKAGE_ROOT
from searchops.instrument import instrument, fire_skill_tip
from searchops.server import mcp, _ANNOTATIONS_READ_LOCAL


def load_gsc_dimensions():
    """Load available GSC dimensions from JSON file"""
    try:
        with open(PACKAGE_ROOT / "gsc_dimensions.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        import sys
        print("Warning: gsc_dimensions.json not found", file=sys.stderr)
        return {}


def load_gsc_metrics():
    """Load available GSC metrics from JSON file"""
    try:
        with open(PACKAGE_ROOT / "gsc_metrics.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        import sys
        print("Warning: gsc_metrics.json not found", file=sys.stderr)
        return {}


@mcp.tool(annotations=_ANNOTATIONS_READ_LOCAL)
@instrument
def list_available_dimensions(ctx: Context = None):
    """
    List all available GSC dimensions with their descriptions.

    Returns:
        List of dimension objects with api_name and description.
    """
    dimensions = load_gsc_dimensions()

    if ctx:
        fire_skill_tip(
            ctx=ctx,
            skill="generic",
            trigger="schema_discovery",
            tool_name="list_available_dimensions"
        )

    return dimensions.get('dimensions', [])


@mcp.tool(annotations=_ANNOTATIONS_READ_LOCAL)
@instrument
def list_available_metrics():
    """
    List all available GSC metrics with their descriptions.

    Returns:
        List of metric objects with api_name and description.
    """
    metrics = load_gsc_metrics()
    return metrics.get('metrics', [])
