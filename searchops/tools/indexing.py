# SPDX-License-Identifier: MIT

"""MCP tool for indexing intelligence — audit_indexing."""

from __future__ import annotations

import anyio.to_thread

from searchops import errors
from searchops.audit import AuditManager
from searchops.db import get_db
from searchops.providers import gsc_provider
from searchops.analyzers.indexing import audit_indexing as _audit_indexing
from searchops.instrument import instrument
from searchops.server import mcp, _ANNOTATIONS_READ_API


@mcp.tool(annotations=_ANNOTATIONS_READ_API)
@instrument
async def audit_indexing(
    site_url: str | None = None,
    urls: list[str] | None = None,
    crawl_audit_id: str | None = None,
    batch_size: int = 50,
) -> dict:
    """Audit indexing status of URLs via the URL Inspection API.

    Checks whether pages are indexed by Google and identifies issues such as:
    - Pages not indexed (noindex, robots blocked, crawl errors, 404s)
    - Canonical mismatches (user vs Google-selected canonical)
    - Page fetch issues

    Provide either a list of URLs or a crawl_audit_id from a previous crawl_site run.
    Results are saved as audit findings queryable via get_audit_summary / get_audit_issues.

    Args:
        site_url: GSC property URL. Defaults to GSC_SITE_URL.
        urls: List of URLs to inspect. If omitted, uses crawl_audit_id.
        crawl_audit_id: Audit ID from a previous crawl_site run.
        batch_size: Max URLs to inspect per run (default 50, max 500). Counts against the 2,000/day inspect_url quota.
    """
    if errors.SERVER_INIT_ERROR:
        return f"Configuration Error: {errors.SERVER_INIT_ERROR}. Please instruct the user to fix their setup."

    target_site = (site_url or errors.GSC_SITE_URL or "").strip()
    if not target_site:
        return {"error": "No site_url provided and GSC_SITE_URL is not configured."}

    if not urls and not crawl_audit_id:
        return {"error": "Provide either 'urls' (list of URLs) or 'crawl_audit_id' (from a previous crawl_site run)."}

    def _run():
        db = get_db()
        mgr = AuditManager(db)
        return _audit_indexing(
            gsc_provider=gsc_provider,
            db=db,
            audit_manager=mgr,
            site_url=target_site,
            urls=urls,
            crawl_audit_id=crawl_audit_id,
            batch_size=batch_size,
        )

    try:
        return await anyio.to_thread.run_sync(_run)
    except Exception as e:
        brief = errors._api_error_text(e, "auditing indexing status")
        if brief:
            return {"error": brief}
        return {"error": f"Error auditing indexing status: {str(e)}"}
