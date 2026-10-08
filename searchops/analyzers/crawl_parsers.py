# SPDX-License-Identifier: MIT

"""Crawl parsers — robots.txt analysis and XML sitemap parsing.

Uses only stdlib (``urllib.request``, ``urllib.robotparser``,
``xml.etree.ElementTree``) to avoid adding external dependencies.
"""

from __future__ import annotations

import re
import ssl
import xml.etree.ElementTree as ET
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from searchops.audit import AuditManager


# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------
_USER_AGENT = "SearchOps-MCP/1.0"
_FETCH_TIMEOUT = 15  # seconds
_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_SITEMAP_MAX_URLS = 50_000  # spec limit per individual sitemap
_SITEMAP_MAX_BYTES = 52_428_800  # 50 MiB uncompressed spec limit


# ------------------------------------------------------------------
# HTTP helper
# ------------------------------------------------------------------
def _fetch_url(url: str, *, timeout: int = _FETCH_TIMEOUT) -> tuple[int, str]:
    """Fetch *url* and return ``(status_code, body_text)``.

    Raises ``URLError`` / ``HTTPError`` on network failures.
    """
    ctx = ssl.create_default_context()
    req = Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urlopen(req, timeout=timeout, context=ctx) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return (resp.status, body)
    except HTTPError as exc:
        return (exc.code, "")


# ------------------------------------------------------------------
# robots.txt analyzer
# ------------------------------------------------------------------

def _robots_url(site_url: str) -> str:
    """Derive robots.txt URL from a GSC property URL."""
    # GSC property URLs may look like "https://example.com/" or
    # "sc-domain:example.com".  Normalize.
    if site_url.startswith("sc-domain:"):
        domain = site_url[len("sc-domain:"):]
        return f"https://{domain}/robots.txt"
    parsed = urlparse(site_url)
    scheme = parsed.scheme or "https"
    host = parsed.netloc or parsed.path.rstrip("/")
    return f"{scheme}://{host}/robots.txt"


def _parse_robots_lines(body: str) -> list[dict]:
    """Parse robots.txt body into structured directive list."""
    directives: list[dict] = []
    current_agent = "*"
    line_num = 0

    for raw_line in body.splitlines():
        line_num += 1
        # Strip comments
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue

        parts = line.split(":", 1)
        if len(parts) != 2:
            directives.append({
                "line": line_num,
                "type": "syntax-error",
                "raw": raw_line.strip(),
            })
            continue

        field = parts[0].strip().lower()
        value = parts[1].strip()

        if field == "user-agent":
            current_agent = value
            directives.append({
                "line": line_num,
                "type": "user-agent",
                "agent": value,
            })
        elif field in ("disallow", "allow"):
            directives.append({
                "line": line_num,
                "type": field,
                "agent": current_agent,
                "path": value,
            })
        elif field == "sitemap":
            directives.append({
                "line": line_num,
                "type": "sitemap",
                "url": value,
            })
        elif field == "crawl-delay":
            directives.append({
                "line": line_num,
                "type": "crawl-delay",
                "agent": current_agent,
                "value": value,
            })
        else:
            directives.append({
                "line": line_num,
                "type": "unknown-directive",
                "field": field,
                "value": value,
            })

    return directives


def _assess_robots(directives: list[dict], site_url: str) -> list[dict]:
    """Return a list of finding dicts from parsed directives."""
    findings: list[dict] = []

    # Gather disallow rules for the wildcard agent
    wildcard_disallows = [
        d for d in directives
        if d["type"] == "disallow" and d.get("agent") == "*"
    ]

    # Check for overly broad disallow (blocks everything)
    for d in wildcard_disallows:
        if d["path"] == "/":
            findings.append({
                "finding_type": "robots-blocks-all",
                "severity": "CRITICAL",
                "title": "robots.txt blocks all crawlers",
                "description": (
                    f"Line {d['line']}: 'Disallow: /' for User-agent: * "
                    "blocks all search engine crawlers from the entire site."
                ),
                "evidence": d,
            })

    # Check for important paths blocked
    important_patterns = [
        (re.compile(r"^/(?:css|js|assets|static|images|img|fonts)/", re.I),
         "static-assets-blocked",
         "Blocking static assets may prevent search engines from rendering pages"),
    ]
    for d in directives:
        if d["type"] != "disallow" or not d.get("path"):
            continue
        for pattern, ftype, desc in important_patterns:
            if pattern.match(d["path"]):
                findings.append({
                    "finding_type": ftype,
                    "severity": "MEDIUM",
                    "title": f"Important path blocked: {d['path']}",
                    "description": f"Line {d['line']}: {desc}.",
                    "evidence": d,
                })

    # Syntax errors
    for d in directives:
        if d["type"] == "syntax-error":
            findings.append({
                "finding_type": "robots-syntax-error",
                "severity": "LOW",
                "title": f"Syntax error at line {d['line']}",
                "description": f"Unrecognized line: {d.get('raw', '')}",
                "evidence": d,
            })

    # Unknown directives
    for d in directives:
        if d["type"] == "unknown-directive":
            findings.append({
                "finding_type": "robots-unknown-directive",
                "severity": "INFO",
                "title": f"Unknown directive '{d['field']}' at line {d['line']}",
                "description": f"'{d['field']}: {d['value']}' is not a standard robots.txt directive.",
                "evidence": d,
            })

    # Check if any sitemap references exist
    sitemap_refs = [d for d in directives if d["type"] == "sitemap"]
    if not sitemap_refs:
        findings.append({
            "finding_type": "robots-no-sitemap",
            "severity": "MEDIUM",
            "title": "No Sitemap directive in robots.txt",
            "description": (
                "robots.txt does not reference a sitemap. "
                "Adding a Sitemap directive helps search engines discover your XML sitemap."
            ),
            "evidence": {"note": "No Sitemap directive found"},
        })

    return findings


def analyze_robots(
    site_url: str,
    audit_manager: AuditManager | None = None,
) -> dict:
    """Fetch and analyze a site's robots.txt.

    Parameters
    ----------
    site_url
        The site URL (GSC property URL or plain domain).
    audit_manager
        Optional AuditManager for persisting findings.

    Returns
    -------
    dict
        Parsed directives, findings, and optional audit_id.
    """
    url = _robots_url(site_url)

    try:
        status, body = _fetch_url(url)
    except (URLError, OSError) as exc:
        return {
            "audit_id": None,
            "url": url,
            "status": "fetch_error",
            "error": str(exc),
            "directives": [],
            "findings_count": 0,
        }

    if status == 404:
        return {
            "audit_id": None,
            "url": url,
            "status": "not_found",
            "message": "No robots.txt found (404). All paths are crawlable by default.",
            "directives": [],
            "findings_count": 0,
        }

    if status != 200:
        return {
            "audit_id": None,
            "url": url,
            "status": f"http_{status}",
            "error": f"Unexpected HTTP {status} fetching robots.txt",
            "directives": [],
            "findings_count": 0,
        }

    directives = _parse_robots_lines(body)
    issues = _assess_robots(directives, site_url)

    audit_id = None
    if audit_manager and issues:
        audit_id = audit_manager.create_audit(
            "robots-txt",
            site_url,
            metadata={"url": url, "directive_count": len(directives)},
        )
        try:
            for issue in issues:
                audit_manager.add_finding(
                    audit_id=audit_id,
                    finding_type=issue["finding_type"],
                    severity=issue["severity"],
                    title=issue["title"],
                    description=issue.get("description", ""),
                    evidence=issue.get("evidence"),
                    confidence=0.9,
                )
            audit_manager.complete_audit(audit_id, summary={
                "findings_count": len(issues),
                "directive_count": len(directives),
            })
        except Exception:
            audit_manager.fail_audit(audit_id, "robots.txt analysis failed")
            raise

    # Build summary of directives by type
    user_agents = sorted({d.get("agent", "") for d in directives if d["type"] == "user-agent"})
    disallow_count = sum(1 for d in directives if d["type"] == "disallow")
    allow_count = sum(1 for d in directives if d["type"] == "allow")
    sitemap_urls = [d["url"] for d in directives if d["type"] == "sitemap"]

    return {
        "audit_id": audit_id,
        "url": url,
        "status": "ok",
        "user_agents": user_agents,
        "disallow_count": disallow_count,
        "allow_count": allow_count,
        "sitemap_urls": sitemap_urls,
        "directive_count": len(directives),
        "findings_count": len(issues),
        "directives": directives,
    }


# ------------------------------------------------------------------
# XML Sitemap parser
# ------------------------------------------------------------------

def _parse_sitemap_xml(body: str) -> dict:
    """Parse a sitemap or sitemapindex XML string.

    Returns
    -------
    dict
        ``{"type": "sitemap"|"sitemapindex", "urls": [...], "sitemaps": [...], "errors": [...]}``.
    """
    result: dict = {"type": "sitemap", "urls": [], "sitemaps": [], "errors": []}

    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        result["errors"].append({"error": "xml_parse_error", "detail": str(exc)})
        return result

    # Strip namespace for easier tag matching
    tag = root.tag
    if "}" in tag:
        tag = tag.split("}", 1)[1]

    if tag == "sitemapindex":
        result["type"] = "sitemapindex"
        for child in root:
            child_tag = child.tag
            if "}" in child_tag:
                child_tag = child_tag.split("}", 1)[1]
            if child_tag != "sitemap":
                continue
            entry: dict = {}
            for sub in child:
                sub_tag = sub.tag
                if "}" in sub_tag:
                    sub_tag = sub_tag.split("}", 1)[1]
                if sub_tag == "loc":
                    entry["loc"] = (sub.text or "").strip()
                elif sub_tag == "lastmod":
                    entry["lastmod"] = (sub.text or "").strip()
            if entry.get("loc"):
                result["sitemaps"].append(entry)
    elif tag == "urlset":
        result["type"] = "sitemap"
        for child in root:
            child_tag = child.tag
            if "}" in child_tag:
                child_tag = child_tag.split("}", 1)[1]
            if child_tag != "url":
                continue
            entry = {}
            for sub in child:
                sub_tag = sub.tag
                if "}" in sub_tag:
                    sub_tag = sub_tag.split("}", 1)[1]
                if sub_tag == "loc":
                    entry["loc"] = (sub.text or "").strip()
                elif sub_tag == "lastmod":
                    entry["lastmod"] = (sub.text or "").strip()
                elif sub_tag == "changefreq":
                    entry["changefreq"] = (sub.text or "").strip()
                elif sub_tag == "priority":
                    entry["priority"] = (sub.text or "").strip()
            if entry.get("loc"):
                result["urls"].append(entry)
    else:
        result["errors"].append({
            "error": "unknown_root_element",
            "detail": f"Expected <urlset> or <sitemapindex>, got <{tag}>",
        })

    return result


def _assess_sitemap(parsed: dict, sitemap_url: str, site_url: str | None) -> list[dict]:
    """Return findings for a parsed sitemap."""
    findings: list[dict] = []

    for err in parsed.get("errors", []):
        findings.append({
            "finding_type": "sitemap-parse-error",
            "severity": "HIGH",
            "title": f"Sitemap parse error: {err['error']}",
            "description": err.get("detail", ""),
            "evidence": err,
        })

    urls = parsed.get("urls", [])

    # Check URL count limit
    if len(urls) > _SITEMAP_MAX_URLS:
        findings.append({
            "finding_type": "sitemap-too-large",
            "severity": "HIGH",
            "title": f"Sitemap exceeds {_SITEMAP_MAX_URLS:,} URL limit",
            "description": (
                f"Sitemap contains {len(urls):,} URLs. "
                f"The sitemap spec limits individual sitemaps to {_SITEMAP_MAX_URLS:,} URLs. "
                "Split into multiple sitemaps referenced by a sitemapindex."
            ),
            "evidence": {"url_count": len(urls), "limit": _SITEMAP_MAX_URLS},
        })

    # Check for domain mismatch
    if site_url:
        site_parsed = urlparse(site_url.replace("sc-domain:", "https://"))
        site_domain = site_parsed.netloc or site_parsed.path.rstrip("/")
        mismatched = []
        for u in urls:
            loc = u.get("loc", "")
            loc_parsed = urlparse(loc)
            loc_domain = loc_parsed.netloc or ""
            if loc_domain and loc_domain != site_domain:
                mismatched.append(loc)
        if mismatched:
            findings.append({
                "finding_type": "sitemap-domain-mismatch",
                "severity": "MEDIUM",
                "title": f"{len(mismatched)} URL(s) don't match site domain",
                "description": (
                    f"Found {len(mismatched)} URL(s) with domains that don't match "
                    f"the site domain '{site_domain}'."
                ),
                "evidence": {"mismatched_urls": mismatched[:10], "total": len(mismatched)},
            })

    # Check for missing lastmod
    urls_without_lastmod = [u for u in urls if not u.get("lastmod")]
    if urls and len(urls_without_lastmod) == len(urls):
        findings.append({
            "finding_type": "sitemap-no-lastmod",
            "severity": "LOW",
            "title": "No URLs have lastmod dates",
            "description": (
                "None of the URLs in this sitemap include lastmod dates. "
                "Adding lastmod helps search engines prioritize crawling recently updated pages."
            ),
            "evidence": {"total_urls": len(urls)},
        })

    return findings


def parse_sitemap(
    sitemap_url: str,
    site_url: str | None = None,
    audit_manager: AuditManager | None = None,
) -> dict:
    """Fetch and parse an XML sitemap or sitemapindex.

    Parameters
    ----------
    sitemap_url
        Full URL to the sitemap XML file.
    site_url
        Optional site URL for domain-mismatch validation.
    audit_manager
        Optional AuditManager for persisting findings.

    Returns
    -------
    dict
        Parsed sitemap data with urls/sitemaps, stats, and optional audit_id.
    """
    try:
        status, body = _fetch_url(sitemap_url)
    except (URLError, OSError) as exc:
        return {
            "audit_id": None,
            "sitemap_url": sitemap_url,
            "status": "fetch_error",
            "error": str(exc),
            "type": None,
            "url_count": 0,
            "sitemap_count": 0,
            "findings_count": 0,
        }

    if status != 200:
        return {
            "audit_id": None,
            "sitemap_url": sitemap_url,
            "status": f"http_{status}",
            "error": f"HTTP {status} fetching sitemap",
            "type": None,
            "url_count": 0,
            "sitemap_count": 0,
            "findings_count": 0,
        }

    parsed = _parse_sitemap_xml(body)
    issues = _assess_sitemap(parsed, sitemap_url, site_url)

    audit_id = None
    if audit_manager and issues:
        audit_id = audit_manager.create_audit(
            "sitemap-analysis",
            site_url or sitemap_url,
            metadata={
                "sitemap_url": sitemap_url,
                "sitemap_type": parsed["type"],
                "url_count": len(parsed["urls"]),
                "sitemap_count": len(parsed["sitemaps"]),
            },
        )
        try:
            for issue in issues:
                audit_manager.add_finding(
                    audit_id=audit_id,
                    finding_type=issue["finding_type"],
                    severity=issue["severity"],
                    title=issue["title"],
                    description=issue.get("description", ""),
                    evidence=issue.get("evidence"),
                    confidence=0.9,
                )
            audit_manager.complete_audit(audit_id, summary={
                "findings_count": len(issues),
                "url_count": len(parsed["urls"]),
                "sitemap_count": len(parsed["sitemaps"]),
            })
        except Exception:
            audit_manager.fail_audit(audit_id, "Sitemap analysis failed")
            raise

    return {
        "audit_id": audit_id,
        "sitemap_url": sitemap_url,
        "status": "ok",
        "type": parsed["type"],
        "url_count": len(parsed["urls"]),
        "sitemap_count": len(parsed["sitemaps"]),
        "urls": parsed["urls"],
        "sitemaps": parsed["sitemaps"],
        "findings_count": len(issues),
    }
