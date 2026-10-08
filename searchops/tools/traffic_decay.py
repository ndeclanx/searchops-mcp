# SPDX-License-Identifier: MIT

"""MCP tool for detecting traffic decay."""

from __future__ import annotations

from datetime import datetime, timedelta

import anyio.to_thread

from searchops import errors
from searchops.audit import AuditManager
from searchops.db import get_db
from searchops.providers import gsc_provider
from searchops.analyzers.traffic_decay import detect_traffic_decay
from searchops.instrument import instrument
from searchops.server import mcp, _ANNOTATIONS_READ_API


@mcp.tool(annotations=_ANNOTATIONS_READ_API)
@instrument
async def detect_traffic_decay_tool(
    site_url: str | None = None,
    current_start: str | None = None,
    current_end: str | None = None,
    baseline_start: str | None = None,
    baseline_end: str | None = None,
    comparison_days: int = 14,
    row_limit: int = 5000,
    impressions_decline_pct: float = 20.0,
    position_decline: float = 2.0,
) -> dict:
    """Detect queries and pages with declining traffic.

    Compares a current period against a baseline to find impressions drops,
    ranking losses, and CTR declines.  Results are saved as audit findings.

    Args:
        site_url: GSC property URL. Defaults to GSC_SITE_URL.
        current_start: Start of current (drop) period (YYYY-MM-DD). Defaults to last 14 days.
        current_end: End of current period. Defaults to 3 days ago.
        baseline_start: Start of baseline period. Defaults to period before current.
        baseline_end: End of baseline period. Defaults to day before current_start.
        comparison_days: Number of days per period (default 14).
        row_limit: Max rows to fetch from GSC.
        impressions_decline_pct: Min % decline to flag (default 20).
        position_decline: Min position worsening to flag (default 2.0).
    """
    if errors.SERVER_INIT_ERROR:
        return f"Configuration Error: {errors.SERVER_INIT_ERROR}. Please instruct the user to fix their setup."

    target_site = (site_url or errors.GSC_SITE_URL or "").strip()
    if not target_site:
        return {"error": "No site_url provided and GSC_SITE_URL is not configured."}

    # Default date ranges
    if not current_end:
        current_end = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    if not current_start:
        current_start = (datetime.strptime(current_end, "%Y-%m-%d") - timedelta(days=comparison_days)).strftime("%Y-%m-%d")
    if not baseline_end:
        baseline_end = (datetime.strptime(current_start, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    if not baseline_start:
        baseline_start = (datetime.strptime(baseline_end, "%Y-%m-%d") - timedelta(days=comparison_days)).strftime("%Y-%m-%d")

    row_limit = max(1, min(int(row_limit), 25000))

    def _run():
        mgr = AuditManager(get_db())
        return detect_traffic_decay(
            gsc_provider=gsc_provider,
            audit_manager=mgr,
            site_url=target_site,
            current_start=current_start,
            current_end=current_end,
            baseline_start=baseline_start,
            baseline_end=baseline_end,
            row_limit=row_limit,
            impressions_decline_pct=impressions_decline_pct,
            position_decline=position_decline,
        )

    try:
        return await anyio.to_thread.run_sync(_run)
    except Exception as e:
        brief = errors._api_error_text(e, "detecting traffic decay")
        if brief:
            return {"error": brief}
        return {"error": f"Error detecting traffic decay: {str(e)}"}
