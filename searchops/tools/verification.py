# SPDX-License-Identifier: MIT

"""MCP tool for verifying whether an issue has been resolved."""

from __future__ import annotations

import anyio.to_thread

from searchops.audit import AuditManager
from searchops.db import get_db
from searchops.analyzers.verification import verify_issue as _verify_issue
from searchops.instrument import instrument
from searchops.server import mcp, _ANNOTATIONS_READ_API


@mcp.tool(annotations=_ANNOTATIONS_READ_API)
@instrument
async def verify_issue(
    finding_id: str,
) -> dict:
    """Re-check whether a previously found issue has been resolved.

    Reads the finding from the database and performs the appropriate re-check
    (e.g., re-fetching the page to check if a missing title has been added).

    Supported finding types for automatic verification:
    - missing-title, missing-meta-description, missing-h1
    - multiple-h1, thin-content
    - title-too-long, meta-description-too-long
    - http-error

    Other finding types return a "manual verification required" response.

    Args:
        finding_id: The finding ID to re-check (from get_audit_issues or get_issue).
    """
    def _run():
        mgr = AuditManager(get_db())
        return _verify_issue(audit_manager=mgr, finding_id=finding_id)

    try:
        return await anyio.to_thread.run_sync(_run)
    except Exception as e:
        return {"error": f"Error verifying issue: {str(e)}"}
