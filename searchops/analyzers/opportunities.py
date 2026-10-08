# SPDX-License-Identifier: MIT

"""Search opportunity analyzer.

Fetches GSC search analytics data and classifies queries into opportunity
types: low-CTR, near-page-one, and citation opportunities.  Findings are
persisted via ``AuditManager`` so they can be queried with the audit tools.
"""

from __future__ import annotations

from searchops.audit import AuditManager


# ------------------------------------------------------------------
# Default thresholds (derived from existing skills)
# ------------------------------------------------------------------
DEFAULT_THRESHOLDS = {
    "low_ctr_threshold": 2.0,           # percent
    "low_ctr_max_position": 10.0,
    "low_ctr_min_impressions": 50,
    "near_page_one_min_position": 5.0,
    "near_page_one_max_position": 20.0,
    "near_page_one_min_impressions": 10,
    "citation_max_position": 1.5,
    "citation_ctr_threshold": 1.0,      # percent
    "citation_min_impressions": 20,
}

# Opportunity type labels for finding titles
_TYPE_LABELS = {
    "low-ctr": "Low CTR",
    "near-page-one": "Near Page One",
    "citation-opportunity": "Citation Opportunity",
}

_TYPE_SEVERITY = {
    "low-ctr": "MEDIUM",
    "near-page-one": "MEDIUM",
    "citation-opportunity": "LOW",
}

_TYPE_CONFIDENCE = {
    "low-ctr": 0.8,
    "near-page-one": 0.7,
    "citation-opportunity": 0.9,
}

_TYPE_DESCRIPTIONS = {
    "low-ctr": (
        "This query ranks at position {position} but has only {ctr_pct}% CTR "
        "({clicks} clicks from {impressions} impressions). "
        "Consider improving the title tag and meta description to increase clicks."
    ),
    "near-page-one": (
        "This query is at position {position} with {impressions} impressions. "
        "Small content improvements could push it to page one."
    ),
    "citation-opportunity": (
        "This query ranks at position {position} but gets almost no clicks "
        "({ctr_pct}% CTR). Google may be answering directly from your content. "
        "Consider adding structured data or a stronger call-to-action."
    ),
}


# ------------------------------------------------------------------
# Row helpers
# ------------------------------------------------------------------
def _normalize_row(raw_row: dict) -> dict:
    """Convert a raw GSC API row into a normalized dict.

    CTR is converted from decimal (0.0-1.0) to percentage (0-100).
    """
    keys = raw_row.get("keys", [])
    return {
        "query": keys[0] if len(keys) > 0 else "",
        "page": keys[1] if len(keys) > 1 else "",
        "clicks": raw_row.get("clicks", 0),
        "impressions": raw_row.get("impressions", 0),
        "ctr_pct": round(raw_row.get("ctr", 0.0) * 100, 2),
        "position": round(raw_row.get("position", 0.0), 1),
    }


def _classify_row(row: dict, thresholds: dict) -> list[str]:
    """Return a list of opportunity types that this row matches."""
    types: list[str] = []
    pos = row["position"]
    ctr = row["ctr_pct"]
    imp = row["impressions"]

    # Low CTR: good position but poor click-through
    if (
        pos < thresholds["low_ctr_max_position"]
        and ctr < thresholds["low_ctr_threshold"]
        and imp >= thresholds["low_ctr_min_impressions"]
    ):
        types.append("low-ctr")

    # Near page one: striking distance
    if (
        thresholds["near_page_one_min_position"] <= pos <= thresholds["near_page_one_max_position"]
        and imp >= thresholds["near_page_one_min_impressions"]
    ):
        types.append("near-page-one")

    # Citation opportunity: top position, almost no clicks
    if (
        pos <= thresholds["citation_max_position"]
        and ctr < thresholds["citation_ctr_threshold"]
        and imp > thresholds["citation_min_impressions"]
    ):
        types.append("citation-opportunity")

    return types


# ------------------------------------------------------------------
# Main analyzer
# ------------------------------------------------------------------
def find_opportunities(
    gsc_provider,
    audit_manager: AuditManager,
    site_url: str,
    start_date: str,
    end_date: str,
    row_limit: int = 5000,
    **threshold_overrides,
) -> dict:
    """Analyze GSC data and persist opportunity findings.

    Parameters
    ----------
    gsc_provider
        The GSC provider instance (must have ``search_analytics`` method).
    audit_manager
        An ``AuditManager`` for persisting results.
    site_url
        The GSC property URL.
    start_date, end_date
        Date range in ``YYYY-MM-DD`` format.
    row_limit
        Max rows to fetch from GSC (default 5000).
    **threshold_overrides
        Override any default threshold (see ``DEFAULT_THRESHOLDS``).

    Returns
    -------
    dict
        Summary with ``audit_id``, ``total_opportunities``, and per-type counts.
    """
    # Merge thresholds
    thresholds = {**DEFAULT_THRESHOLDS, **threshold_overrides}

    # Fetch data from GSC
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
            "total_opportunities": 0,
            "opportunities": {},
            "rows_analyzed": 0,
        }

    # Create audit
    audit_id = audit_manager.create_audit(
        "search-opportunities",
        site_url,
        metadata={
            "start_date": start_date,
            "end_date": end_date,
            "row_limit": row_limit,
            "thresholds": thresholds,
        },
    )

    try:
        counts: dict[str, int] = {}

        for raw_row in rows:
            row = _normalize_row(raw_row)
            opp_types = _classify_row(row, thresholds)

            for opp_type in opp_types:
                counts[opp_type] = counts.get(opp_type, 0) + 1
                label = _TYPE_LABELS[opp_type]
                audit_manager.add_finding(
                    audit_id=audit_id,
                    finding_type=opp_type,
                    severity=_TYPE_SEVERITY[opp_type],
                    title=f"{label}: '{row['query']}'",
                    url=row["page"],
                    description=_TYPE_DESCRIPTIONS[opp_type].format(**row),
                    evidence={
                        "query": row["query"],
                        "page": row["page"],
                        "clicks": row["clicks"],
                        "impressions": row["impressions"],
                        "ctr_pct": row["ctr_pct"],
                        "position": row["position"],
                    },
                    confidence=_TYPE_CONFIDENCE[opp_type],
                )

        total = sum(counts.values())
        summary = {"total_opportunities": total, "by_type": counts}
        audit_manager.complete_audit(audit_id, summary=summary)

        return {
            "audit_id": audit_id,
            "total_opportunities": total,
            "opportunities": counts,
            "rows_analyzed": len(rows),
        }
    except Exception:
        audit_manager.fail_audit(audit_id, "Analysis failed")
        raise
