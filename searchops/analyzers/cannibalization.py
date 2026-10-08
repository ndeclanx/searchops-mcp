# SPDX-License-Identifier: MIT

"""Cannibalization analyzer.

Detects queries where multiple pages from the same site compete for ranking,
splitting clicks and impressions across pages.
"""

from __future__ import annotations

from collections import defaultdict

from searchops.audit import AuditManager


# ------------------------------------------------------------------
# Default thresholds
# ------------------------------------------------------------------
DEFAULT_THRESHOLDS = {
    "min_pages": 2,                   # minimum competing pages to flag
    "min_impressions_per_query": 20,  # minimum total impressions for query
    "min_ctr_spread": 0.5,            # minimum CTR spread (percentage points)
}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _group_by_query(rows: list[dict]) -> dict[str, list[dict]]:
    """Group raw GSC rows (query+page dimensions) by query."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        keys = row.get("keys", [])
        if len(keys) < 2:
            continue
        query = keys[0]
        page = keys[1]
        groups[query].append({
            "query": query,
            "page": page,
            "clicks": row.get("clicks", 0),
            "impressions": row.get("impressions", 0),
            "ctr_pct": round(row.get("ctr", 0.0) * 100, 2),
            "position": round(row.get("position", 0.0), 1),
        })
    return dict(groups)


def _analyze_query_group(query: str, pages: list[dict], thresholds: dict) -> dict | None:
    """Analyze a group of pages for cannibalization. Returns evidence dict or None."""
    if len(pages) < thresholds["min_pages"]:
        return None

    total_impressions = sum(p["impressions"] for p in pages)
    if total_impressions < thresholds["min_impressions_per_query"]:
        return None

    # Sort by CTR descending to find the "winner" and "cannibalizers"
    sorted_pages = sorted(pages, key=lambda p: p["ctr_pct"], reverse=True)
    best = sorted_pages[0]
    worst = sorted_pages[-1]

    ctr_spread = best["ctr_pct"] - worst["ctr_pct"]
    if ctr_spread < thresholds["min_ctr_spread"]:
        return None

    return {
        "query": query,
        "page_count": len(pages),
        "total_impressions": total_impressions,
        "total_clicks": sum(p["clicks"] for p in pages),
        "ctr_spread": round(ctr_spread, 2),
        "best_page": best["page"],
        "best_ctr_pct": best["ctr_pct"],
        "best_position": best["position"],
        "competing_pages": [
            {
                "page": p["page"],
                "clicks": p["clicks"],
                "impressions": p["impressions"],
                "ctr_pct": p["ctr_pct"],
                "position": p["position"],
            }
            for p in sorted_pages
        ],
    }


# ------------------------------------------------------------------
# Main analyzer
# ------------------------------------------------------------------
def detect_cannibalization(
    gsc_provider,
    audit_manager: AuditManager,
    site_url: str,
    start_date: str,
    end_date: str,
    row_limit: int = 5000,
    **threshold_overrides,
) -> dict:
    """Detect keyword cannibalization and persist findings.

    Parameters
    ----------
    gsc_provider
        GSC provider with ``search_analytics`` method.
    audit_manager
        AuditManager for persisting results.
    site_url
        The GSC property URL.
    start_date, end_date
        Date range in YYYY-MM-DD format.
    row_limit
        Max rows to fetch from GSC.
    **threshold_overrides
        Override default thresholds.

    Returns
    -------
    dict
        Summary with audit_id, total_cannibalized, queries affected.
    """
    thresholds = {**DEFAULT_THRESHOLDS, **threshold_overrides}

    body = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": ["query", "page"],
        "searchType": "web",
        "rowLimit": row_limit,
    }
    response = gsc_provider.search_analytics(site_url, body)
    rows = response.get("rows", [])

    if not rows:
        return {
            "audit_id": None,
            "total_cannibalized": 0,
            "queries_affected": 0,
            "rows_analyzed": 0,
        }

    groups = _group_by_query(rows)

    audit_id = audit_manager.create_audit(
        "cannibalization",
        site_url,
        metadata={
            "start_date": start_date,
            "end_date": end_date,
            "thresholds": thresholds,
        },
    )

    try:
        queries_affected = 0

        for query, pages in groups.items():
            evidence = _analyze_query_group(query, pages, thresholds)
            if evidence is None:
                continue

            queries_affected += 1
            page_count = evidence["page_count"]

            # Severity based on number of competing pages and CTR spread
            if page_count >= 4 or evidence["ctr_spread"] >= 5.0:
                severity = "HIGH"
            elif page_count >= 3 or evidence["ctr_spread"] >= 2.0:
                severity = "MEDIUM"
            else:
                severity = "LOW"

            audit_manager.add_finding(
                audit_id=audit_id,
                finding_type="cannibalization",
                severity=severity,
                title=f"Cannibalization: '{query}' ({page_count} pages)",
                url=evidence["best_page"],
                description=(
                    f"Query '{query}' ranks on {page_count} different pages "
                    f"with a CTR spread of {evidence['ctr_spread']:.1f}%. "
                    f"Best page: {evidence['best_page']} ({evidence['best_ctr_pct']:.1f}% CTR). "
                    f"Consider consolidating content to focus ranking power."
                ),
                evidence=evidence,
                confidence=0.8,
            )

        audit_manager.complete_audit(audit_id, summary={
            "total_cannibalized": queries_affected,
            "queries_affected": queries_affected,
        })

        return {
            "audit_id": audit_id,
            "total_cannibalized": queries_affected,
            "queries_affected": queries_affected,
            "rows_analyzed": len(rows),
        }
    except Exception:
        audit_manager.fail_audit(audit_id, "Cannibalization analysis failed")
        raise
