# SPDX-License-Identifier: MIT

"""MCP tools for site crawling and single-page analysis."""

from __future__ import annotations

import anyio.to_thread

from searchops import errors
from searchops.audit import AuditManager
from searchops.db import get_db
from searchops.analyzers.crawler import analyze_single_url, crawl_site as _crawl_site
from searchops.instrument import instrument
from searchops.server import mcp, _ANNOTATIONS_READ_API


@mcp.tool(annotations=_ANNOTATIONS_READ_API)
@instrument
async def analyze_url(
    url: str,
    site_url: str | None = None,
) -> dict:
    """Fetch and analyze a single URL for SEO issues.

    Fetches the page, parses the HTML, and checks for common SEO problems:
    - Missing or too-long title tags
    - Missing meta description
    - Missing or multiple H1 tags
    - Thin content (< 100 words)
    - HTTP errors

    Returns page metadata (title, description, canonical, H1, word count)
    and a list of links found on the page.

    Args:
        url: The URL to analyze.
        site_url: Optional GSC property URL for audit context. Defaults to GSC_SITE_URL.
    """
    target_site = (site_url or errors.GSC_SITE_URL or "").strip() or None

    def _run():
        db = get_db()
        mgr = AuditManager(db)
        audit_id = mgr.create_audit("url-analysis", target_site or url, metadata={"url": url})
        try:
            result = analyze_single_url(url, db=db, audit_manager=mgr, audit_id=audit_id)
            if result.get("findings_count", 0) > 0 or result.get("status") == "ok":
                mgr.complete_audit(audit_id, summary={
                    "url": url,
                    "findings_count": result.get("findings_count", 0),
                })
            else:
                mgr.complete_audit(audit_id, summary={"url": url, "status": result.get("status")})
            result["audit_id"] = audit_id
            return result
        except Exception:
            mgr.fail_audit(audit_id, "URL analysis failed")
            raise

    try:
        return await anyio.to_thread.run_sync(_run)
    except Exception as e:
        return {"error": f"Error analyzing URL: {str(e)}"}


@mcp.tool(annotations=_ANNOTATIONS_READ_API)
@instrument
async def crawl_site(
    start_url: str | None = None,
    site_url: str | None = None,
    max_pages: int = 50,
    max_depth: int = 3,
    respect_robots: bool = True,
) -> dict:
    """Crawl a website starting from a URL using BFS.

    Follows internal links up to max_depth, analyzing each page for SEO issues.
    Stores crawled pages and links in the database. Detects orphan pages
    (not linked to by other pages).

    Results are saved as audit findings queryable via get_audit_summary / get_audit_issues.

    Args:
        start_url: The starting URL for the crawl. Defaults to GSC_SITE_URL.
        site_url: GSC property URL (for context). Defaults to GSC_SITE_URL.
        max_pages: Maximum pages to crawl (default 50, max 500).
        max_depth: Maximum link-follow depth (default 3, max 10).
        respect_robots: Whether to respect robots.txt (default True).
    """
    target_site = (site_url or errors.GSC_SITE_URL or "").strip() or None
    crawl_start = (start_url or target_site or "").strip()

    if not crawl_start:
        return {"error": "No start_url provided and GSC_SITE_URL is not configured."}

    def _run():
        db = get_db()
        mgr = AuditManager(db)
        return _crawl_site(
            start_url=crawl_start,
            db=db,
            audit_manager=mgr,
            max_pages=max_pages,
            max_depth=max_depth,
            respect_robots=respect_robots,
        )

    try:
        return await anyio.to_thread.run_sync(_run)
    except Exception as e:
        return {"error": f"Error crawling site: {str(e)}"}
