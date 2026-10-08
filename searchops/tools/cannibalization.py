# SPDX-License-Identifier: MIT

"""MCP tool for detecting keyword cannibalization."""

from __future__ import annotations

from datetime import datetime, timedelta

import anyio.to_thread

from searchops import errors
from searchops.audit import AuditManager
from searchops.db import get_db
from searchops.providers import gsc_provider
from searchops.analyzers.cannibalization import detect_cannibalization
from searchops.instrument import instrument
from searchops.server import mcp, _ANNOTATIONS_READ_API


@mcp.tool(annotations=_ANNOTATIONS_READ_API)
@instrument
async def detect_cannibalization_tool(
    site_url: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    row_limit: int = 5000,
    min_pages: int = 2,
) -> dict:
    """Detect keyword cannibalization — queries where multiple pages compete.

    Finds queries ranking on 2+ pages from your site, identifies the best page,
    and flags cannibalization with severity based on page count and CTR spread.

    Args:
        site_url: GSC property URL. Defaults to GSC_SITE_URL.
        start_date: Start date (YYYY-MM-DD). Defaults to 30 days ago.
        end_date: End date (YYYY-MM-DD). Defaults to 3 days ago.
        row_limit: Max rows to fetch from GSC (default 5000).
        min_pages: Minimum competing pages to flag (default 2).
    """
    if errors.SERVER_INIT_ERROR:
        return f"Configuration Error: {errors.SERVER_INIT_ERROR}. Please instruct the user to fix their setup."

    target_site = (site_url or errors.GSC_SITE_URL or "").strip()
    if not target_site:
        return {"error": "No site_url provided and GSC_SITE_URL is not configured."}

    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    if not end_date:
        end_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")

    row_limit = max(1, min(int(row_limit), 25000))

    def _run():
        mgr = AuditManager(get_db())
        return detect_cannibalization(
            gsc_provider=gsc_provider,
            audit_manager=mgr,
            site_url=target_site,
            start_date=start_date,
            end_date=end_date,
            row_limit=row_limit,
            min_pages=min_pages,
        )

    try:
        return await anyio.to_thread.run_sync(_run)
    except Exception as e:
        brief = errors._api_error_text(e, "detecting cannibalization")
        if brief:
            return {"error": brief}
        return {"error": f"Error detecting cannibalization: {str(e)}"}
