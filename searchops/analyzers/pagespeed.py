# SPDX-License-Identifier: MIT

"""PageSpeed Insights analyzer.

Queries the PageSpeed Insights API (free, no auth required) to evaluate
Core Web Vitals and performance metrics for a given URL.
"""

from __future__ import annotations

import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from searchops.audit import AuditManager


# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------
_PSI_API = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
_USER_AGENT = "SearchOps-MCP/1.0"
_FETCH_TIMEOUT = 60  # PSI can be slow

# Core Web Vitals thresholds (from web.dev)
_CWV_THRESHOLDS = {
    "LARGEST_CONTENTFUL_PAINT_MS": {"good": 2500, "poor": 4000, "unit": "ms", "label": "LCP"},
    "FIRST_INPUT_DELAY_MS": {"good": 100, "poor": 300, "unit": "ms", "label": "FID"},
    "CUMULATIVE_LAYOUT_SHIFT_SCORE": {"good": 0.1, "poor": 0.25, "unit": "", "label": "CLS"},
    "INTERACTION_TO_NEXT_PAINT": {"good": 200, "poor": 500, "unit": "ms", "label": "INP"},
    "FIRST_CONTENTFUL_PAINT_MS": {"good": 1800, "poor": 3000, "unit": "ms", "label": "FCP"},
    "EXPERIMENTAL_TIME_TO_FIRST_BYTE": {"good": 800, "poor": 1800, "unit": "ms", "label": "TTFB"},
}


# ------------------------------------------------------------------
# API interaction
# ------------------------------------------------------------------
def _fetch_psi(url: str, strategy: str = "mobile", api_key: str | None = None) -> dict:
    """Call PageSpeed Insights API and return raw JSON response."""
    params = {
        "url": url,
        "strategy": strategy,
        "category": "performance",
    }
    if api_key:
        params["key"] = api_key

    api_url = f"{_PSI_API}?{urlencode(params)}"
    ctx = ssl.create_default_context()
    req = Request(api_url, headers={"User-Agent": _USER_AGENT})

    with urlopen(req, timeout=_FETCH_TIMEOUT, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ------------------------------------------------------------------
# Result parsing
# ------------------------------------------------------------------
def _extract_metrics(data: dict) -> dict:
    """Extract key metrics from PSI response."""
    metrics = {}

    # Lighthouse performance score
    lh = data.get("lighthouseResult", {})
    categories = lh.get("categories", {})
    perf = categories.get("performance", {})
    metrics["performance_score"] = round((perf.get("score", 0) or 0) * 100)

    # Lighthouse audits (individual metrics)
    audits = lh.get("audits", {})

    # Core Web Vitals from field data (CrUX)
    loading = data.get("loadingExperience", {})
    crux_metrics = loading.get("metrics", {})
    metrics["crux_origin"] = loading.get("origin_fallback", False)
    metrics["crux_overall"] = loading.get("overall_category", "NONE")

    field_data = {}
    for metric_key, thresholds in _CWV_THRESHOLDS.items():
        crux = crux_metrics.get(metric_key, {})
        if crux:
            percentile = crux.get("percentile", None)
            category = crux.get("category", "NONE")
            field_data[thresholds["label"]] = {
                "value": percentile,
                "category": category,
                "unit": thresholds["unit"],
            }
    metrics["field_data"] = field_data

    # Lab data from Lighthouse
    lab_data = {}
    lab_metrics = {
        "first-contentful-paint": "FCP",
        "largest-contentful-paint": "LCP",
        "total-blocking-time": "TBT",
        "cumulative-layout-shift": "CLS",
        "speed-index": "SI",
        "interactive": "TTI",
    }
    for audit_key, label in lab_metrics.items():
        audit = audits.get(audit_key, {})
        if audit:
            lab_data[label] = {
                "value": audit.get("numericValue"),
                "display": audit.get("displayValue", ""),
                "score": round((audit.get("score", 0) or 0) * 100),
            }
    metrics["lab_data"] = lab_data

    return metrics


def _assess_performance(url: str, metrics: dict) -> list[dict]:
    """Generate findings from performance metrics."""
    findings = []

    score = metrics.get("performance_score", 0)
    if score < 50:
        findings.append({
            "finding_type": "poor-performance",
            "severity": "HIGH",
            "title": f"Poor performance score: {score}/100",
            "description": (
                f"{url} has a Lighthouse performance score of {score}/100. "
                "Scores below 50 indicate significant performance issues."
            ),
            "evidence": {"url": url, "score": score},
        })
    elif score < 90:
        findings.append({
            "finding_type": "needs-improvement-performance",
            "severity": "MEDIUM",
            "title": f"Performance needs improvement: {score}/100",
            "description": (
                f"{url} has a Lighthouse performance score of {score}/100. "
                "Target 90+ for good performance."
            ),
            "evidence": {"url": url, "score": score},
        })

    # Check individual lab metrics
    lab = metrics.get("lab_data", {})

    lcp = lab.get("LCP", {})
    if lcp.get("value") and lcp["value"] > 4000:
        findings.append({
            "finding_type": "slow-lcp",
            "severity": "HIGH",
            "title": f"Slow LCP: {lcp.get('display', '')}",
            "description": (
                f"Largest Contentful Paint is {lcp['value']:.0f}ms. "
                "Target is under 2500ms for good user experience."
            ),
            "evidence": {"url": url, "lcp_ms": lcp["value"]},
        })

    cls = lab.get("CLS", {})
    if cls.get("value") and cls["value"] > 0.25:
        findings.append({
            "finding_type": "high-cls",
            "severity": "HIGH",
            "title": f"High CLS: {cls.get('display', '')}",
            "description": (
                f"Cumulative Layout Shift is {cls['value']:.3f}. "
                "Target is under 0.1 for good visual stability."
            ),
            "evidence": {"url": url, "cls": cls["value"]},
        })

    tbt = lab.get("TBT", {})
    if tbt.get("value") and tbt["value"] > 600:
        findings.append({
            "finding_type": "high-tbt",
            "severity": "MEDIUM",
            "title": f"High TBT: {tbt.get('display', '')}",
            "description": (
                f"Total Blocking Time is {tbt['value']:.0f}ms. "
                "Target is under 200ms for good interactivity."
            ),
            "evidence": {"url": url, "tbt_ms": tbt["value"]},
        })

    return findings


# ------------------------------------------------------------------
# Main analyzer
# ------------------------------------------------------------------
def analyze_performance(
    url: str,
    strategy: str = "mobile",
    api_key: str | None = None,
    audit_manager: AuditManager | None = None,
) -> dict:
    """Analyze a URL's performance using PageSpeed Insights.

    Parameters
    ----------
    url
        The URL to analyze.
    strategy
        "mobile" or "desktop" (default "mobile").
    api_key
        Optional Google API key (increases rate limits).
    audit_manager
        Optional AuditManager for persisting findings.

    Returns
    -------
    dict
        Performance metrics, scores, and findings.
    """
    try:
        raw = _fetch_psi(url, strategy=strategy, api_key=api_key)
    except HTTPError as exc:
        return {
            "audit_id": None,
            "url": url,
            "status": "api_error",
            "error": f"PageSpeed Insights API returned HTTP {exc.code}",
        }
    except (URLError, OSError) as exc:
        return {
            "audit_id": None,
            "url": url,
            "status": "fetch_error",
            "error": str(exc),
        }

    metrics = _extract_metrics(raw)
    findings = _assess_performance(url, metrics)

    audit_id = None
    if audit_manager and findings:
        audit_id = audit_manager.create_audit(
            "pagespeed",
            url,
            metadata={
                "strategy": strategy,
                "performance_score": metrics["performance_score"],
            },
        )
        try:
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
            audit_manager.complete_audit(audit_id, summary={
                "performance_score": metrics["performance_score"],
                "findings_count": len(findings),
            })
        except Exception:
            audit_manager.fail_audit(audit_id, "PageSpeed analysis failed")
            raise

    return {
        "audit_id": audit_id,
        "url": url,
        "status": "ok",
        "strategy": strategy,
        "performance_score": metrics["performance_score"],
        "crux_overall": metrics.get("crux_overall", "NONE"),
        "field_data": metrics.get("field_data", {}),
        "lab_data": metrics.get("lab_data", {}),
        "findings_count": len(findings),
    }
