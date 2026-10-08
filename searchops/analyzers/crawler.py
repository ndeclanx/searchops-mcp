# SPDX-License-Identifier: MIT

"""Site crawler and single-page analyzer.

Provides a lightweight BFS crawler and a single-page analyzer, both using
stdlib only (``urllib.request``, ``html.parser``).  Crawled data is persisted
to the ``crawl_pages`` and ``crawl_links`` tables via ``DatabaseManager``.
"""

from __future__ import annotations

import hashlib
import re
import ssl
import uuid
from collections import deque
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from searchops.audit import AuditManager
from searchops.db import DatabaseManager


# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------
_USER_AGENT = "SearchOps-MCP/1.0"
_FETCH_TIMEOUT = 15
_DEFAULT_MAX_PAGES = 50
_DEFAULT_MAX_DEPTH = 3


# ------------------------------------------------------------------
# HTML Parser
# ------------------------------------------------------------------
class _SEOHTMLParser(HTMLParser):
    """Extract SEO-relevant data from HTML."""

    def __init__(self):
        super().__init__()
        self.title = ""
        self.meta_description = ""
        self.canonical = ""
        self.h1s: list[str] = []
        self.links: list[dict] = []
        self.word_count = 0

        self._in_title = False
        self._in_h1 = False
        self._in_body = False
        self._in_skip = False  # inside <script> or <style>
        self._body_text: list[str] = []
        self._h1_text: list[str] = []
        self._current_tag = ""

    def handle_starttag(self, tag, attrs):
        self._current_tag = tag
        attr_dict = dict(attrs)

        if tag in ("script", "style", "noscript"):
            self._in_skip = True
        elif tag == "title":
            self._in_title = True
        elif tag == "h1":
            self._in_h1 = True
            self._h1_text = []
        elif tag == "body":
            self._in_body = True
        elif tag == "meta":
            name = attr_dict.get("name", "").lower()
            if name == "description":
                self.meta_description = attr_dict.get("content", "")
        elif tag == "link":
            rel = attr_dict.get("rel", "").lower()
            if rel == "canonical":
                self.canonical = attr_dict.get("href", "")
        elif tag == "a":
            href = attr_dict.get("href", "").strip()
            if href and not href.startswith(("#", "javascript:", "mailto:", "tel:")):
                rel = attr_dict.get("rel", "")
                self.links.append({
                    "href": href,
                    "anchor": "",
                    "nofollow": "nofollow" in rel.lower(),
                })

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._in_skip = False
        elif tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False
            self.h1s.append(" ".join(self._h1_text).strip())
        elif tag == "body":
            self._in_body = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._in_h1:
            self._h1_text.append(data)
        if self._in_body and not self._in_skip:
            self._body_text.append(data)

        # Update anchor text for the last link
        if self._current_tag == "a" and self.links:
            self.links[-1]["anchor"] += data

    def finalize(self):
        """Compute derived values after parsing completes."""
        text = " ".join(self._body_text)
        self.word_count = len(re.findall(r"\S+", text))
        self.title = self.title.strip()


# ------------------------------------------------------------------
# HTTP fetching
# ------------------------------------------------------------------
def _fetch_page(url: str, *, timeout: int = _FETCH_TIMEOUT) -> tuple[int, str, str]:
    """Fetch *url* and return ``(status_code, content_type, body)``.

    Returns ``(0, "", "")`` for connection/timeout errors.
    """
    ctx = ssl.create_default_context()
    req = Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urlopen(req, timeout=timeout, context=ctx) as resp:
            ct = resp.headers.get("Content-Type", "")
            body = resp.read().decode("utf-8", errors="replace")
            return (resp.status, ct, body)
    except HTTPError as exc:
        return (exc.code, "", "")
    except (URLError, OSError):
        return (0, "", "")


# ------------------------------------------------------------------
# URL normalization
# ------------------------------------------------------------------
def _normalize_url(base: str, href: str) -> str | None:
    """Resolve *href* against *base* and strip fragments. Returns None for non-HTTP."""
    resolved = urljoin(base, href)
    parsed = urlparse(resolved)
    if parsed.scheme not in ("http", "https"):
        return None
    # Strip fragment
    return parsed._replace(fragment="").geturl()


def _is_internal(url: str, site_domain: str) -> bool:
    """Check if *url* belongs to *site_domain*."""
    parsed = urlparse(url)
    return (parsed.netloc or "").lower() == site_domain.lower()


# ------------------------------------------------------------------
# Single-page analysis
# ------------------------------------------------------------------
def _assess_page(parsed: _SEOHTMLParser, url: str, status_code: int) -> list[dict]:
    """Return SEO findings for a single parsed page."""
    findings: list[dict] = []

    if status_code >= 400:
        findings.append({
            "finding_type": "http-error",
            "severity": "HIGH",
            "title": f"HTTP {status_code} error",
            "description": f"{url} returned HTTP {status_code}.",
            "evidence": {"url": url, "status_code": status_code},
        })
        return findings

    if not parsed.title:
        findings.append({
            "finding_type": "missing-title",
            "severity": "HIGH",
            "title": "Missing page title",
            "description": f"{url} has no <title> tag.",
            "evidence": {"url": url},
        })
    elif len(parsed.title) > 60:
        findings.append({
            "finding_type": "title-too-long",
            "severity": "LOW",
            "title": f"Title too long ({len(parsed.title)} chars)",
            "description": f"Title is {len(parsed.title)} characters. Recommended max is 60.",
            "evidence": {"url": url, "title": parsed.title, "length": len(parsed.title)},
        })

    if not parsed.meta_description:
        findings.append({
            "finding_type": "missing-meta-description",
            "severity": "MEDIUM",
            "title": "Missing meta description",
            "description": f"{url} has no meta description.",
            "evidence": {"url": url},
        })
    elif len(parsed.meta_description) > 160:
        findings.append({
            "finding_type": "meta-description-too-long",
            "severity": "LOW",
            "title": f"Meta description too long ({len(parsed.meta_description)} chars)",
            "description": f"Meta description is {len(parsed.meta_description)} characters. Recommended max is 160.",
            "evidence": {"url": url, "length": len(parsed.meta_description)},
        })

    if not parsed.h1s:
        findings.append({
            "finding_type": "missing-h1",
            "severity": "MEDIUM",
            "title": "Missing H1 heading",
            "description": f"{url} has no <h1> tag.",
            "evidence": {"url": url},
        })
    elif len(parsed.h1s) > 1:
        findings.append({
            "finding_type": "multiple-h1",
            "severity": "LOW",
            "title": f"Multiple H1 tags ({len(parsed.h1s)})",
            "description": f"{url} has {len(parsed.h1s)} H1 tags. Best practice is one per page.",
            "evidence": {"url": url, "h1s": parsed.h1s},
        })

    if parsed.word_count < 100:
        findings.append({
            "finding_type": "thin-content",
            "severity": "MEDIUM",
            "title": f"Thin content ({parsed.word_count} words)",
            "description": f"{url} has only {parsed.word_count} words. Pages with thin content may not rank well.",
            "evidence": {"url": url, "word_count": parsed.word_count},
        })

    return findings


def analyze_single_url(
    url: str,
    db: DatabaseManager | None = None,
    audit_manager: AuditManager | None = None,
    audit_id: str | None = None,
) -> dict:
    """Fetch and analyze a single URL for SEO issues.

    Parameters
    ----------
    url
        The URL to analyze.
    db
        Optional DatabaseManager for persisting crawl data.
    audit_manager
        Optional AuditManager for persisting findings.
    audit_id
        Optional existing audit to add findings to.

    Returns
    -------
    dict
        Page data with title, meta_description, canonical, h1, word_count,
        links, and findings.
    """
    import time
    start = time.monotonic()
    status_code, content_type, body = _fetch_page(url)
    elapsed_ms = int((time.monotonic() - start) * 1000)

    if status_code == 0:
        return {
            "url": url,
            "status": "fetch_error",
            "status_code": 0,
            "error": "Connection failed or timed out",
        }

    # Parse HTML only if content type looks like HTML
    is_html = "html" in content_type.lower() or (not content_type and body.lstrip().startswith("<"))
    parser = _SEOHTMLParser()
    if is_html and body:
        try:
            parser.feed(body)
            parser.finalize()
        except Exception:
            pass  # Best-effort parsing

    content_hash = hashlib.md5(body.encode("utf-8")).hexdigest() if body else None

    # Persist to crawl_pages
    page_id = str(uuid.uuid4())
    if db:
        db.execute(
            """INSERT INTO crawl_pages
               (id, audit_id, url, status_code, content_type, title,
                meta_description, canonical, h1, word_count, content_hash,
                response_time_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (page_id, audit_id, url, status_code, content_type,
             parser.title or None, parser.meta_description or None,
             parser.canonical or None,
             parser.h1s[0] if parser.h1s else None,
             parser.word_count, content_hash, elapsed_ms),
        )
        db.commit()

    # Assess SEO issues
    findings = _assess_page(parser, url, status_code) if is_html else []

    if audit_manager and audit_id and findings:
        for f in findings:
            audit_manager.add_finding(
                audit_id=audit_id,
                finding_type=f["finding_type"],
                severity=f["severity"],
                title=f["title"],
                url=url,
                description=f.get("description", ""),
                evidence=f.get("evidence"),
                confidence=0.8,
            )

    # Resolve links
    resolved_links = []
    for link in parser.links:
        resolved = _normalize_url(url, link["href"])
        if resolved:
            resolved_links.append({
                "target_url": resolved,
                "anchor_text": link["anchor"].strip(),
                "nofollow": link["nofollow"],
            })

    return {
        "url": url,
        "status": "ok",
        "status_code": status_code,
        "content_type": content_type,
        "title": parser.title or None,
        "meta_description": parser.meta_description or None,
        "canonical": parser.canonical or None,
        "h1": parser.h1s[0] if parser.h1s else None,
        "h1_count": len(parser.h1s),
        "word_count": parser.word_count,
        "response_time_ms": elapsed_ms,
        "link_count": len(resolved_links),
        "findings_count": len(findings),
        "links": resolved_links,
    }


# ------------------------------------------------------------------
# BFS Site Crawler
# ------------------------------------------------------------------
def _load_robots(site_url: str) -> RobotFileParser | None:
    """Fetch and parse robots.txt for the site. Returns None on failure."""
    parsed = urlparse(site_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
        return rp
    except Exception:
        return None


def crawl_site(
    start_url: str,
    db: DatabaseManager,
    audit_manager: AuditManager,
    max_pages: int = _DEFAULT_MAX_PAGES,
    max_depth: int = _DEFAULT_MAX_DEPTH,
    respect_robots: bool = True,
) -> dict:
    """Crawl a site starting from *start_url* using BFS.

    Parameters
    ----------
    start_url
        The starting URL for the crawl.
    db
        DatabaseManager for persisting crawl data.
    audit_manager
        AuditManager for persisting findings.
    max_pages
        Maximum number of pages to crawl (default 50).
    max_depth
        Maximum link-follow depth (default 3).
    respect_robots
        Whether to respect robots.txt directives (default True).

    Returns
    -------
    dict
        Summary with audit_id, pages_crawled, links_found, findings_count.
    """
    parsed_start = urlparse(start_url)
    site_domain = parsed_start.netloc
    if not site_domain:
        return {"error": "Invalid start URL — cannot determine domain."}

    max_pages = max(1, min(int(max_pages), 500))
    max_depth = max(1, min(int(max_depth), 10))

    # Load robots.txt
    robots = _load_robots(start_url) if respect_robots else None

    audit_id = audit_manager.create_audit(
        "site-crawl",
        start_url,
        metadata={
            "max_pages": max_pages,
            "max_depth": max_depth,
            "respect_robots": respect_robots,
        },
    )

    try:
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(start_url, 0)])
        total_links = 0
        total_findings = 0

        while queue and len(visited) < max_pages:
            current_url, depth = queue.popleft()

            if current_url in visited:
                continue

            # Robots check
            if robots and not robots.can_fetch(_USER_AGENT, current_url):
                continue

            visited.add(current_url)

            result = analyze_single_url(
                current_url,
                db=db,
                audit_manager=audit_manager,
                audit_id=audit_id,
            )

            if result.get("status") != "ok":
                continue

            total_findings += result.get("findings_count", 0)

            # Store links and queue internal ones
            for link in result.get("links", []):
                target = link["target_url"]
                is_int = _is_internal(target, site_domain)
                link_type = "internal" if is_int else "external"

                db.execute(
                    """INSERT INTO crawl_links
                       (audit_id, source_url, target_url, anchor_text, link_type, is_followed)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (audit_id, current_url, target,
                     link["anchor_text"], link_type,
                     0 if link["nofollow"] else 1),
                )
                total_links += 1

                if is_int and target not in visited and depth < max_depth:
                    queue.append((target, depth + 1))

            db.commit()

        # Check for orphan pages (pages not linked to by any other page)
        cursor = db.execute(
            """SELECT url FROM crawl_pages
               WHERE audit_id = ? AND url NOT IN (
                   SELECT target_url FROM crawl_links WHERE audit_id = ?
               ) AND url != ?""",
            (audit_id, audit_id, start_url),
        )
        orphans = [row["url"] for row in cursor.fetchall()]
        if orphans:
            audit_manager.add_finding(
                audit_id=audit_id,
                finding_type="orphan-pages",
                severity="MEDIUM",
                title=f"{len(orphans)} orphan page(s) found",
                description=(
                    f"Found {len(orphans)} page(s) not linked to by any other crawled page. "
                    "These pages may be difficult for search engines to discover."
                ),
                evidence={"orphan_urls": orphans[:20], "total": len(orphans)},
                confidence=0.7,
            )
            total_findings += 1

        audit_manager.complete_audit(audit_id, summary={
            "pages_crawled": len(visited),
            "links_found": total_links,
            "findings_count": total_findings,
        })

        return {
            "audit_id": audit_id,
            "pages_crawled": len(visited),
            "links_found": total_links,
            "findings_count": total_findings,
        }

    except Exception:
        audit_manager.fail_audit(audit_id, "Site crawl failed")
        raise
