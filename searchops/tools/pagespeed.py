# SPDX-License-Identifier: MIT

"""MCP tool for PageSpeed Insights performance analysis."""

from __future__ import annotations

import os

import anyio.to_thread

from searchops import errors
from searchops.audit import AuditManager
from searchops.db import get_db
from searchops.analyzers.pagespeed import analyze_performance as _analyze_performance
from searchops.instrument import instrument
from searchops.server import mcp, _ANNOTATIONS_READ_API


@mcp.tool(annotations=_ANNOTATIONS_READ_API)
@instrument
async def analyze_performance(
    url: str,
    strategy: str = "mobile",
) -> dict:
    """Analyze a URL's performance using Google PageSpeed Insights.

    Returns Lighthouse performance score, Core Web Vitals (field data from CrUX),
    and lab metrics (FCP, LCP, TBT, CLS, Speed Index, TTI).

    Flags performance issues:
    - Poor performance (score < 50)
    - Needs improvement (score < 90)
    - Slow LCP (> 4000ms)
    - High CLS (> 0.25)
    - High TBT (> 600ms)

    Results are saved as audit findings queryable via get_audit_summary / get_audit_issues.

    Args:
        url: The URL to analyze.
        strategy: "mobile" or "desktop" (default "mobile").
    """
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("PAGESPEED_API_KEY")

    def _run():
        mgr = AuditManager(get_db())
        return _analyze_performance(
            url=url,
            strategy=strategy,
            api_key=api_key,
            audit_manager=mgr,
        )

    try:
        return await anyio.to_thread.run_sync(_run)
    except Exception as e:
        return {"error": f"Error analyzing performance: {str(e)}"}
