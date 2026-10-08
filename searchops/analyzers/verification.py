# SPDX-License-Identifier: MIT

"""Issue verification — re-check whether a previously found issue is resolved.

Reads a finding from the audit database, performs the appropriate re-check
(HTTP fetch, HTML parse, etc.), and returns whether the issue persists.
"""

from __future__ import annotations

import json

from searchops.audit import AuditManager
from searchops.analyzers.crawler import _fetch_page, _SEOHTMLParser


# ------------------------------------------------------------------
# Verification strategies per finding type
# ------------------------------------------------------------------
def _verify_http_error(url: str, evidence: dict) -> dict:
    """Re-check an HTTP error finding."""
    status, ct, body = _fetch_page(url)
    if status == 0:
        return {"resolved": False, "reason": "URL still unreachable."}
    if status >= 400:
        return {"resolved": False, "reason": f"URL still returns HTTP {status}."}
    return {"resolved": True, "reason": f"URL now returns HTTP {status}."}


def _verify_html_element(url: str, finding_type: str) -> dict:
    """Re-check missing HTML element findings (title, meta, h1)."""
    status, ct, body = _fetch_page(url)
    if status == 0:
        return {"resolved": False, "reason": "URL unreachable — cannot verify."}
    if status >= 400:
        return {"resolved": False, "reason": f"URL returns HTTP {status}."}

    if "html" not in ct.lower() and not body.lstrip().startswith("<"):
        return {"resolved": False, "reason": "Response is not HTML."}

    parser = _SEOHTMLParser()
    try:
        parser.feed(body)
        parser.finalize()
    except Exception:
        return {"resolved": False, "reason": "Failed to parse HTML."}

    if finding_type == "missing-title":
        if parser.title:
            return {"resolved": True, "reason": f"Title tag now present: '{parser.title}'."}
        return {"resolved": False, "reason": "Title tag still missing."}

    if finding_type == "missing-meta-description":
        if parser.meta_description:
            return {"resolved": True, "reason": "Meta description now present."}
        return {"resolved": False, "reason": "Meta description still missing."}

    if finding_type == "missing-h1":
        if parser.h1s:
            return {"resolved": True, "reason": f"H1 now present: '{parser.h1s[0]}'."}
        return {"resolved": False, "reason": "H1 still missing."}

    if finding_type == "multiple-h1":
        if len(parser.h1s) <= 1:
            return {"resolved": True, "reason": f"Now has {len(parser.h1s)} H1 tag(s)."}
        return {"resolved": False, "reason": f"Still has {len(parser.h1s)} H1 tags."}

    if finding_type == "thin-content":
        if parser.word_count >= 100:
            return {"resolved": True, "reason": f"Word count now {parser.word_count}."}
        return {"resolved": False, "reason": f"Word count still low ({parser.word_count})."}

    if finding_type in ("title-too-long", "meta-description-too-long"):
        if finding_type == "title-too-long":
            if len(parser.title) <= 60:
                return {"resolved": True, "reason": f"Title now {len(parser.title)} chars."}
            return {"resolved": False, "reason": f"Title still {len(parser.title)} chars."}
        else:
            if len(parser.meta_description) <= 160:
                return {"resolved": True, "reason": f"Meta description now {len(parser.meta_description)} chars."}
            return {"resolved": False, "reason": f"Meta description still {len(parser.meta_description)} chars."}

    return {"resolved": None, "reason": f"No verifier for finding type '{finding_type}'."}


# Strategy mapping
_VERIFIERS = {
    "http-error": lambda url, ev: _verify_http_error(url, ev),
    "missing-title": lambda url, ev: _verify_html_element(url, "missing-title"),
    "missing-meta-description": lambda url, ev: _verify_html_element(url, "missing-meta-description"),
    "missing-h1": lambda url, ev: _verify_html_element(url, "missing-h1"),
    "multiple-h1": lambda url, ev: _verify_html_element(url, "multiple-h1"),
    "thin-content": lambda url, ev: _verify_html_element(url, "thin-content"),
    "title-too-long": lambda url, ev: _verify_html_element(url, "title-too-long"),
    "meta-description-too-long": lambda url, ev: _verify_html_element(url, "meta-description-too-long"),
}


# ------------------------------------------------------------------
# Main verifier
# ------------------------------------------------------------------
def verify_issue(
    audit_manager: AuditManager,
    finding_id: str,
) -> dict:
    """Re-check whether a previously found issue has been resolved.

    Parameters
    ----------
    audit_manager
        AuditManager for reading finding data.
    finding_id
        The finding ID to re-check.

    Returns
    -------
    dict
        Verification result with resolved status, reason, and finding details.
    """
    finding = audit_manager.get_finding(finding_id)
    if not finding:
        return {"error": f"Finding '{finding_id}' not found."}

    finding_type = finding.get("finding_type", "")
    url = finding.get("url")
    evidence_raw = finding.get("evidence")

    # Parse evidence JSON if it's a string
    evidence = {}
    if isinstance(evidence_raw, str):
        try:
            evidence = json.loads(evidence_raw)
        except (json.JSONDecodeError, TypeError):
            pass
    elif isinstance(evidence_raw, dict):
        evidence = evidence_raw

    title = finding.get("title")
    severity = finding.get("severity")

    if not url:
        return {
            "finding_id": finding_id,
            "finding_type": finding_type,
            "title": title,
            "severity": severity,
            "resolved": None,
            "reason": "Finding has no URL — cannot verify automatically.",
        }

    verifier = _VERIFIERS.get(finding_type)
    if not verifier:
        return {
            "finding_id": finding_id,
            "finding_type": finding_type,
            "url": url,
            "title": title,
            "severity": severity,
            "resolved": None,
            "reason": f"No automatic verifier for finding type '{finding_type}'. Manual verification required.",
        }

    result = verifier(url, evidence)

    return {
        "finding_id": finding_id,
        "finding_type": finding_type,
        "url": url,
        "title": finding.get("title"),
        "severity": finding.get("severity"),
        "resolved": result["resolved"],
        "reason": result["reason"],
    }
