# SPDX-License-Identifier: MIT

"""Indexing intelligence — compares crawled pages against GSC index status.

Uses the URL Inspection API (via GSCProvider) to check whether crawled pages
are indexed, and flags issues such as not-indexed pages, robots blocks,
canonical mismatches, and crawl errors.
"""

from __future__ import annotations

from searchops.audit import AuditManager
from searchops.db import DatabaseManager


# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------
_INDEXED_VERDICTS = {"PASS", "VERDICT_UNSPECIFIED"}
_DEFAULT_BATCH_SIZE = 50  # Max URLs to inspect per run (quota-aware)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _get_crawled_urls(db: DatabaseManager, crawl_audit_id: str) -> list[str]:
    """Return URLs from a previous crawl audit."""
    rows = db.execute(
        "SELECT url FROM crawl_pages WHERE audit_id = ? ORDER BY url",
        (crawl_audit_id,),
    ).fetchall()
    return [row["url"] for row in rows]


def _classify_inspection(result: dict) -> dict:
    """Extract key fields from an inspect_url API response."""
    # The response structure is nested under inspectionResult.indexStatusResult
    inspection = result.get("inspectionResult", result)
    index_result = inspection.get("indexStatusResult", {})

    verdict = index_result.get("verdict", "VERDICT_UNSPECIFIED")
    coverage = index_result.get("coverageState", "")
    robots = index_result.get("robotsTxtState", "")
    indexing = index_result.get("indexingState", "")
    crawled_as = index_result.get("crawledAs", "")
    last_crawl_time = index_result.get("lastCrawlTime", "")

    # Page fetch
    page_fetch = index_result.get("pageFetchState", "")

    # Canonical
    user_canonical = index_result.get("userCanonical", "")
    google_canonical = index_result.get("googleCanonical", "")

    return {
        "verdict": verdict,
        "coverage_state": coverage,
        "robots_txt_state": robots,
        "indexing_state": indexing,
        "page_fetch_state": page_fetch,
        "crawled_as": crawled_as,
        "last_crawl_time": last_crawl_time,
        "user_canonical": user_canonical,
        "google_canonical": google_canonical,
        "is_indexed": verdict in _INDEXED_VERDICTS,
    }


def _findings_from_inspection(url: str, info: dict) -> list[dict]:
    """Generate findings from a single URL inspection result."""
    findings = []

    if not info["is_indexed"]:
        severity = "HIGH"
        # Determine the reason
        coverage = info["coverage_state"]
        if "noindex" in coverage.lower():
            severity = "MEDIUM"
            finding_type = "noindex-tag"
            desc = f"{url} is excluded from indexing due to a noindex directive."
        elif info["robots_txt_state"] == "DISALLOWED":
            severity = "MEDIUM"
            finding_type = "blocked-by-robots"
            desc = f"{url} is blocked from indexing by robots.txt."
        elif "redirect" in coverage.lower():
            severity = "LOW"
            finding_type = "redirect-not-indexed"
            desc = f"{url} is a redirect and not independently indexed."
        elif "404" in coverage.lower() or "not found" in coverage.lower():
            finding_type = "not-found"
            desc = f"{url} returns a 404/not-found status to Google."
        elif "crawl" in coverage.lower() and "error" in coverage.lower():
            finding_type = "crawl-error"
            desc = f"{url} has a crawl error preventing indexing: {coverage}."
        else:
            finding_type = "not-indexed"
            desc = f"{url} is not indexed. Coverage state: {coverage or 'unknown'}."

        findings.append({
            "finding_type": finding_type,
            "severity": severity,
            "title": f"Not indexed: {url}",
            "description": desc,
            "evidence": {
                "url": url,
                "verdict": info["verdict"],
                "coverage_state": info["coverage_state"],
                "robots_txt_state": info["robots_txt_state"],
                "indexing_state": info["indexing_state"],
            },
        })

    # Canonical mismatch
    if (info["user_canonical"] and info["google_canonical"]
            and info["user_canonical"] != info["google_canonical"]):
        findings.append({
            "finding_type": "canonical-mismatch",
            "severity": "MEDIUM",
            "title": f"Canonical mismatch: {url}",
            "description": (
                f"User-declared canonical ({info['user_canonical']}) differs from "
                f"Google-selected canonical ({info['google_canonical']})."
            ),
            "evidence": {
                "url": url,
                "user_canonical": info["user_canonical"],
                "google_canonical": info["google_canonical"],
            },
        })

    # Page fetch issues
    if info["page_fetch_state"] and info["page_fetch_state"] not in ("SUCCESSFUL", ""):
        findings.append({
            "finding_type": "page-fetch-issue",
            "severity": "HIGH",
            "title": f"Page fetch issue: {url}",
            "description": f"Google reported page fetch state: {info['page_fetch_state']}.",
            "evidence": {
                "url": url,
                "page_fetch_state": info["page_fetch_state"],
            },
        })

    return findings


# ------------------------------------------------------------------
# Main analyzer
# ------------------------------------------------------------------
def audit_indexing(
    gsc_provider,
    db: DatabaseManager,
    audit_manager: AuditManager,
    site_url: str,
    urls: list[str] | None = None,
    crawl_audit_id: str | None = None,
    batch_size: int = _DEFAULT_BATCH_SIZE,
) -> dict:
    """Check indexing status for a set of URLs.

    Parameters
    ----------
    gsc_provider
        GSCProvider instance (for inspect_url calls).
    db
        DatabaseManager for reading crawl data.
    audit_manager
        AuditManager for persisting findings.
    site_url
        The GSC property URL.
    urls
        Explicit list of URLs to inspect. If None, reads from crawl_audit_id.
    crawl_audit_id
        Audit ID of a previous crawl to get URLs from.
    batch_size
        Max number of URLs to inspect (default 50, respects API quota).

    Returns
    -------
    dict
        Summary with audit_id, urls_checked, indexed_count, not_indexed_count,
        findings_count.
    """
    # Determine the URL list
    if urls is not None:
        url_list = list(urls)
    elif crawl_audit_id:
        url_list = _get_crawled_urls(db, crawl_audit_id)
    else:
        return {"error": "Provide either 'urls' or 'crawl_audit_id'."}

    if not url_list:
        return {
            "audit_id": None,
            "urls_checked": 0,
            "indexed_count": 0,
            "not_indexed_count": 0,
            "findings_count": 0,
        }

    # Cap to batch_size
    batch_size = max(1, min(int(batch_size), 500))
    url_list = url_list[:batch_size]

    audit_id = audit_manager.create_audit(
        "indexing-audit",
        site_url,
        metadata={
            "url_count": len(url_list),
            "crawl_audit_id": crawl_audit_id,
        },
    )

    try:
        indexed_count = 0
        not_indexed_count = 0
        total_findings = 0
        errors_list = []

        for url in url_list:
            try:
                raw_result = gsc_provider.inspect_url(site_url, url)
            except Exception as exc:
                errors_list.append({"url": url, "error": str(exc)})
                continue

            info = _classify_inspection(raw_result)

            if info["is_indexed"]:
                indexed_count += 1
            else:
                not_indexed_count += 1

            findings = _findings_from_inspection(url, info)
            for f in findings:
                audit_manager.add_finding(
                    audit_id=audit_id,
                    finding_type=f["finding_type"],
                    severity=f["severity"],
                    title=f["title"],
                    url=url,
                    description=f.get("description", ""),
                    evidence=f.get("evidence"),
                    confidence=0.9,
                )
                total_findings += 1

        audit_manager.complete_audit(audit_id, summary={
            "urls_checked": len(url_list),
            "indexed_count": indexed_count,
            "not_indexed_count": not_indexed_count,
            "findings_count": total_findings,
            "errors": len(errors_list),
        })

        return {
            "audit_id": audit_id,
            "urls_checked": len(url_list),
            "indexed_count": indexed_count,
            "not_indexed_count": not_indexed_count,
            "findings_count": total_findings,
            "errors": errors_list if errors_list else None,
        }

    except Exception:
        audit_manager.fail_audit(audit_id, "Indexing audit failed")
        raise
