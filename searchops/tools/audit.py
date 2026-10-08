# SPDX-License-Identifier: MIT

"""MCP query tools for the audit framework.

Three read-only tools that query audits and findings stored in the local
SQLite database.  All use ``_ANNOTATIONS_READ_LOCAL`` (read-only, idempotent,
no external API call).
"""

from __future__ import annotations

import json

from searchops.db import get_db
from searchops.audit import AuditManager
from searchops.instrument import instrument
from searchops.server import mcp, _ANNOTATIONS_READ_LOCAL


def _get_manager() -> AuditManager:
    """Return an AuditManager backed by the process-wide DB."""
    return AuditManager(get_db())


def _resolve_audit(manager: AuditManager, audit_id: str | None, audit_type: str | None = None) -> dict | None:
    """Return the requested audit or the latest one."""
    if audit_id:
        return manager.get_audit(audit_id)
    return manager.get_latest_audit(audit_type=audit_type)


# ---------------------------------------------------------------------------
# get_audit_summary
# ---------------------------------------------------------------------------
@mcp.tool(annotations=_ANNOTATIONS_READ_LOCAL)
@instrument
def get_audit_summary(
    audit_id: str | None = None,
    audit_type: str | None = None,
) -> dict:
    """Get summary of an audit's findings.

    Args:
        audit_id: Specific audit ID. If omitted, uses the latest audit.
        audit_type: Filter latest audit by type (e.g. 'indexing', 'technical').

    Returns a dict with audit metadata and findings counts broken down by severity.
    """
    mgr = _get_manager()
    audit = _resolve_audit(mgr, audit_id, audit_type)
    if audit is None:
        return {"error": "No audit found."}
    return mgr.get_audit_summary(audit["id"])


# ---------------------------------------------------------------------------
# get_audit_issues
# ---------------------------------------------------------------------------
@mcp.tool(annotations=_ANNOTATIONS_READ_LOCAL)
@instrument
def get_audit_issues(
    audit_id: str | None = None,
    severity: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Query audit findings with pagination.

    Args:
        audit_id: Specific audit ID. If omitted, uses the latest audit.
        severity: Minimum severity filter (e.g. 'HIGH' returns CRITICAL + HIGH).
        limit: Max results per page (default 20, max 100).
        offset: Pagination offset.

    Returns a dict with findings list and pagination metadata.
    """
    mgr = _get_manager()
    audit = _resolve_audit(mgr, audit_id)
    if audit is None:
        return {"error": "No audit found."}

    # Clamp limit
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    findings = mgr.get_findings(audit["id"], severity=severity, limit=limit, offset=offset)
    total = mgr.count_findings(audit["id"], severity=severity)

    # Parse evidence JSON in each finding for display
    for f in findings:
        if f.get("evidence"):
            try:
                f["evidence"] = json.loads(f["evidence"])
            except (json.JSONDecodeError, TypeError):
                pass

    return {
        "audit_id": audit["id"],
        "findings": findings,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": total,
            "has_more": offset + limit < total,
        },
    }


# ---------------------------------------------------------------------------
# get_issue
# ---------------------------------------------------------------------------
@mcp.tool(annotations=_ANNOTATIONS_READ_LOCAL)
@instrument
def get_issue(finding_id: str) -> dict:
    """Get a single audit finding with full evidence.

    Args:
        finding_id: The finding UUID.

    Returns the full finding dict including parsed evidence JSON.
    """
    mgr = _get_manager()
    finding = mgr.get_finding(finding_id)
    if finding is None:
        return {"error": f"Finding {finding_id} not found."}
    return finding
