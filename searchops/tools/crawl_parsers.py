# SPDX-License-Identifier: MIT

"""MCP tools for parsing robots.txt and XML sitemaps."""

from __future__ import annotations

import anyio.to_thread

from searchops import errors
from searchops.audit import AuditManager
from searchops.db import get_db
from searchops.analyzers.crawl_parsers import (
    analyze_robots as _analyze_robots,
    parse_sitemap as _parse_sitemap,
)
from searchops.instrument import instrument
from searchops.server import mcp, _ANNOTATIONS_READ_API


@mcp.tool(annotations=_ANNOTATIONS_READ_API)
@instrument
async def analyze_robots_txt(
    site_url: str | None = None,
) -> dict:
    """Fetch and analyze a site's robots.txt file.

    Parses directives (User-agent, Disallow, Allow, Sitemap, Crawl-delay)
    and flags potential issues such as:
    - Blocking all crawlers (Disallow: /)
    - Blocking important asset paths (css, js, images)
    - Missing Sitemap directive
    - Syntax errors

    Results are saved as audit findings queryable via get_audit_summary / get_audit_issues.

    Args:
        site_url: Site URL or GSC property URL. Defaults to GSC_SITE_URL.
    """
    target_site = (site_url or errors.GSC_SITE_URL or "").strip()
    if not target_site:
        return {"error": "No site_url provided and GSC_SITE_URL is not configured."}

    def _run():
        mgr = AuditManager(get_db())
        return _analyze_robots(site_url=target_site, audit_manager=mgr)

    try:
        return await anyio.to_thread.run_sync(_run)
    except Exception as e:
        return {"error": f"Error analyzing robots.txt: {str(e)}"}


@mcp.tool(annotations=_ANNOTATIONS_READ_API)
@instrument
async def parse_sitemap(
    sitemap_url: str,
    site_url: str | None = None,
) -> dict:
    """Fetch and parse an XML sitemap or sitemap index.

    Parses the sitemap and returns the list of URLs (for urlset) or
    child sitemaps (for sitemapindex). Also validates:
    - URL count vs the 50,000 limit
    - Domain mismatches between sitemap URLs and site domain
    - Missing lastmod dates

    Results are saved as audit findings queryable via get_audit_summary / get_audit_issues.

    Args:
        sitemap_url: Full URL to the XML sitemap.
        site_url: Optional site URL for domain-mismatch validation. Defaults to GSC_SITE_URL.
    """
    target_site = (site_url or errors.GSC_SITE_URL or "").strip() or None

    def _run():
        mgr = AuditManager(get_db())
        return _parse_sitemap(
            sitemap_url=sitemap_url,
            site_url=target_site,
            audit_manager=mgr,
        )

    try:
        return await anyio.to_thread.run_sync(_run)
    except Exception as e:
        return {"error": f"Error parsing sitemap: {str(e)}"}
