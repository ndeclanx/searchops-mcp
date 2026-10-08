# SPDX-License-Identifier: MIT

"""MCP tool for comparing audits — compare_audits."""

from __future__ import annotations

import anyio.to_thread

from searchops.audit import AuditManager
from searchops.db import get_db
from searchops.analyzers.comparison import compare_audits as _compare_audits
from searchops.instrument import instrument
from searchops.server import mcp, _ANNOTATIONS_READ_LOCAL


@mcp.tool(annotations=_ANNOTATIONS_READ_LOCAL)
@instrument
async def compare_audits(
    baseline_audit_id: str,
    current_audit_id: str,
) -> dict:
    """Compare two audits to track changes over time.

    Identifies new issues (appeared since baseline), resolved issues
    (fixed since baseline), and persistent issues (still present).
    Also detects severity changes on persistent findings.

    Use this after running the same analysis tool twice (e.g. two
    find_search_opportunities runs) to see what improved or regressed.

    Args:
        baseline_audit_id: The older audit ID (baseline).
        current_audit_id: The newer audit ID to compare against.
    """
    def _run():
        mgr = AuditManager(get_db())
        return _compare_audits(
            audit_manager=mgr,
            baseline_audit_id=baseline_audit_id,
            current_audit_id=current_audit_id,
        )

    try:
        return await anyio.to_thread.run_sync(_run)
    except Exception as e:
        return {"error": f"Error comparing audits: {str(e)}"}
