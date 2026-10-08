# SPDX-License-Identifier: MIT

"""Traffic decay analyzer.

Compares two periods of GSC search analytics data (baseline vs current)
to detect queries and pages with declining traffic.  Classifies declines
into impressions loss, position loss, or CTR loss.
"""

from __future__ import annotations

from searchops.audit import AuditManager


# ------------------------------------------------------------------
# Default thresholds
# ------------------------------------------------------------------
DEFAULT_THRESHOLDS = {
    "impressions_decline_pct": 20.0,    # % decline to flag
    "position_decline": 2.0,            # position increase (worsening)
    "ctr_decline_pct": 20.0,            # % relative CTR decline
    "min_baseline_impressions": 20,     # minimum impressions in baseline
}

_TYPE_LABELS = {
    "impressions-declined": "Impressions Declined",
    "position-declined": "Position Declined",
    "ctr-declined": "CTR Declined",
}

_TYPE_SEVERITY = {
    "impressions-declined": "HIGH",
    "position-declined": "MEDIUM",
    "ctr-declined": "MEDIUM",
}

_TYPE_CONFIDENCE = {
    "impressions-declined": 0.85,
    "position-declined": 0.8,
    "ctr-declined": 0.75,
}

_TYPE_DESCRIPTIONS = {
    "impressions-declined": (
        "Impressions for '{query}' dropped {decline_pct:.0f}% "
        "(from {baseline_impressions} to {current_impressions}). "
        "This may indicate an indexing issue or visibility loss."
    ),
    "position-declined": (
        "Average position for '{query}' worsened from {baseline_position} to "
        "{current_position} (+{position_change:.1f}). "
        "Content quality or competitive changes may be the cause."
    ),
    "ctr-declined": (
        "CTR for '{query}' dropped {decline_pct:.0f}% "
        "(from {baseline_ctr_pct:.1f}% to {current_ctr_pct:.1f}%). "
        "SERP features or title/snippet changes may be stealing clicks."
    ),
}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _build_lookup(rows: list[dict]) -> dict[str, dict]:
    """Build a dict keyed by query from raw GSC rows."""
    lookup: dict[str, dict] = {}
    for row in rows:
        keys = row.get("keys", [])
        query = keys[0] if keys else ""
        if not query:
            continue
        lookup[query] = {
            "query": query,
            "clicks": row.get("clicks", 0),
            "impressions": row.get("impressions", 0),
            "ctr_pct": round(row.get("ctr", 0.0) * 100, 2),
            "position": round(row.get("position", 0.0), 1),
        }
    return lookup


def _classify_decay(baseline: dict, current: dict, thresholds: dict) -> list[tuple[str, dict]]:
    """Return list of (decay_type, evidence) tuples for a query."""
    results: list[tuple[str, dict]] = []

    b_imp = baseline["impressions"]
    c_imp = current["impressions"]
    b_pos = baseline["position"]
    c_pos = current["position"]
    b_ctr = baseline["ctr_pct"]
    c_ctr = current["ctr_pct"]

    evidence_base = {
        "query": baseline["query"],
        "baseline_clicks": baseline["clicks"],
        "baseline_impressions": b_imp,
        "baseline_ctr_pct": b_ctr,
        "baseline_position": b_pos,
        "current_clicks": current["clicks"],
        "current_impressions": c_imp,
        "current_ctr_pct": c_ctr,
        "current_position": c_pos,
    }

    # Impressions decline
    if b_imp > 0:
        imp_decline = ((b_imp - c_imp) / b_imp) * 100
        if imp_decline >= thresholds["impressions_decline_pct"]:
            results.append((
                "impressions-declined",
                {**evidence_base, "decline_pct": imp_decline},
            ))

    # Position decline (higher number = worse)
    position_change = c_pos - b_pos
    if position_change >= thresholds["position_decline"]:
        results.append((
            "position-declined",
            {**evidence_base, "position_change": position_change},
        ))

    # CTR decline (relative)
    if b_ctr > 0:
        ctr_decline = ((b_ctr - c_ctr) / b_ctr) * 100
        if ctr_decline >= thresholds["ctr_decline_pct"]:
            results.append((
                "ctr-declined",
                {**evidence_base, "decline_pct": ctr_decline},
            ))

    return results


# ------------------------------------------------------------------
# Main analyzer
# ------------------------------------------------------------------
def detect_traffic_decay(
    gsc_provider,
    audit_manager: AuditManager,
    site_url: str,
    current_start: str,
    current_end: str,
    baseline_start: str,
    baseline_end: str,
    row_limit: int = 5000,
    **threshold_overrides,
) -> dict:
    """Compare two periods and persist decay findings.

    Parameters
    ----------
    gsc_provider
        GSC provider with ``search_analytics`` method.
    audit_manager
        AuditManager for persisting results.
    site_url
        The GSC property URL.
    current_start, current_end
        The "current" (drop) period.
    baseline_start, baseline_end
        The "baseline" (prior healthy) period.
    row_limit
        Max rows per GSC query.
    **threshold_overrides
        Override default thresholds.

    Returns
    -------
    dict
        Summary with audit_id, total_decays, and per-type counts.
    """
    thresholds = {**DEFAULT_THRESHOLDS, **threshold_overrides}

    base_body = {
        "startDate": baseline_start,
        "endDate": baseline_end,
        "dimensions": ["query"],
        "searchType": "web",
        "rowLimit": row_limit,
    }
    curr_body = {
        "startDate": current_start,
        "endDate": current_end,
        "dimensions": ["query"],
        "searchType": "web",
        "rowLimit": row_limit,
    }

    baseline_resp = gsc_provider.search_analytics(site_url, base_body)
    current_resp = gsc_provider.search_analytics(site_url, curr_body)

    baseline_lookup = _build_lookup(baseline_resp.get("rows", []))
    current_lookup = _build_lookup(current_resp.get("rows", []))

    if not baseline_lookup:
        return {
            "audit_id": None,
            "total_decays": 0,
            "decays": {},
            "queries_compared": 0,
        }

    audit_id = audit_manager.create_audit(
        "traffic-decay",
        site_url,
        metadata={
            "baseline_start": baseline_start,
            "baseline_end": baseline_end,
            "current_start": current_start,
            "current_end": current_end,
            "thresholds": thresholds,
        },
    )

    try:
        counts: dict[str, int] = {}
        queries_compared = 0

        for query, baseline in baseline_lookup.items():
            if baseline["impressions"] < thresholds["min_baseline_impressions"]:
                continue

            queries_compared += 1
            # If query disappeared entirely, treat as full impressions loss
            current = current_lookup.get(query, {
                "query": query, "clicks": 0, "impressions": 0,
                "ctr_pct": 0.0, "position": 0.0,
            })

            decays = _classify_decay(baseline, current, thresholds)
            for decay_type, evidence in decays:
                counts[decay_type] = counts.get(decay_type, 0) + 1
                label = _TYPE_LABELS[decay_type]
                desc_template = _TYPE_DESCRIPTIONS[decay_type]
                audit_manager.add_finding(
                    audit_id=audit_id,
                    finding_type=decay_type,
                    severity=_TYPE_SEVERITY[decay_type],
                    title=f"{label}: '{query}'",
                    description=desc_template.format(**evidence),
                    evidence=evidence,
                    confidence=_TYPE_CONFIDENCE[decay_type],
                )

        total = sum(counts.values())
        audit_manager.complete_audit(audit_id, summary={
            "total_decays": total, "by_type": counts,
            "queries_compared": queries_compared,
        })

        return {
            "audit_id": audit_id,
            "total_decays": total,
            "decays": counts,
            "queries_compared": queries_compared,
        }
    except Exception:
        audit_manager.fail_audit(audit_id, "Traffic decay analysis failed")
        raise
