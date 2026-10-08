# SPDX-License-Identifier: MIT

"""MCP tool for finding search optimization opportunities."""

from __future__ import annotations

import functools
from datetime import datetime, timedelta

import anyio.to_thread

from searchops import errors
from searchops.audit import AuditManager
from searchops.db import get_db
from searchops.providers import gsc_provider
from searchops.analyzers.opportunities import find_opportunities
from searchops.instrument import instrument
from searchops.server import mcp, _ANNOTATIONS_READ_API


@mcp.tool(annotations=_ANNOTATIONS_READ_API)
@instrument
async def find_search_opportunities(
    site_url: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    row_limit: int = 5000,
    low_ctr_threshold: float = 2.0,
    near_page_one_max_position: float = 20.0,
) -> dict:
    """Find search queries with optimization potential.

    Analyzes GSC search analytics data to identify:
    - Low-CTR queries ranking in the top 10 positions
    - Near-page-one queries (position 5-20) with impressions
    - Citation opportunities (position #1 with almost no clicks)

    Results are saved as audit findings queryable via get_audit_summary / get_audit_issues.

    Args:
        site_url: GSC property URL. Defaults to GSC_SITE_URL.
        start_date: Start date (YYYY-MM-DD). Defaults to 30 days ago.
        end_date: End date (YYYY-MM-DD). Defaults to 3 days ago.
        row_limit: Max rows to fetch from GSC (default 5000).
        low_ctr_threshold: CTR percentage threshold for low-CTR detection (default 2.0).
        near_page_one_max_position: Max position for near-page-one (default 20.0).
    """
    if errors.SERVER_INIT_ERROR:
        return f"Configuration Error: {errors.SERVER_INIT_ERROR}. Please instruct the user to fix their setup."

    target_site = (site_url or errors.GSC_SITE_URL or "").strip()
    if not target_site:
        return {"error": "No site_url provided and GSC_SITE_URL is not configured."}

    # Default date range: 30 days ago to 3 days ago (same as get_search_analytics)
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    if not end_date:
        end_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")

    row_limit = max(1, min(int(row_limit), 25000))

    def _run():
        mgr = AuditManager(get_db())
        return find_opportunities(
            gsc_provider=gsc_provider,
            audit_manager=mgr,
            site_url=target_site,
            start_date=start_date,
            end_date=end_date,
            row_limit=row_limit,
            low_ctr_threshold=low_ctr_threshold,
            near_page_one_max_position=near_page_one_max_position,
        )

    try:
        return await anyio.to_thread.run_sync(_run)
    except Exception as e:
        brief = errors._api_error_text(e, "analyzing search opportunities")
        if brief:
            return {"error": brief}
        return {"error": f"Error analyzing search opportunities: {str(e)}"}
