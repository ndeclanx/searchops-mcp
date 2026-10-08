# SPDX-License-Identifier: MIT

"""Tests for the site crawler and single-page analyzer."""

import os
import sys
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from searchops.db import DatabaseManager
from searchops.audit import AuditManager
from searchops.analyzers.crawler import (
    _SEOHTMLParser,
    _normalize_url,
    _is_internal,
    _assess_page,
    analyze_single_url,
    crawl_site,
)


# ------------------------------------------------------------------
# HTML Parser
# ------------------------------------------------------------------
class TestSEOHTMLParser(unittest.TestCase):
    def _parse(self, html):
        p = _SEOHTMLParser()
        p.feed(html)
        p.finalize()
        return p

    def test_extracts_title(self):
        p = self._parse("<html><head><title>My Page</title></head></html>")
        self.assertEqual(p.title, "My Page")

    def test_extracts_meta_description(self):
        p = self._parse('<html><head><meta name="description" content="A description"></head></html>')
        self.assertEqual(p.meta_description, "A description")

    def test_extracts_canonical(self):
        p = self._parse('<html><head><link rel="canonical" href="https://example.com/page"></head></html>')
        self.assertEqual(p.canonical, "https://example.com/page")

    def test_extracts_h1(self):
        p = self._parse("<html><body><h1>Heading One</h1></body></html>")
        self.assertEqual(p.h1s, ["Heading One"])

    def test_multiple_h1(self):
        p = self._parse("<html><body><h1>First</h1><h1>Second</h1></body></html>")
        self.assertEqual(len(p.h1s), 2)

    def test_extracts_links(self):
        p = self._parse('<html><body><a href="/page2">Link</a></body></html>')
        self.assertEqual(len(p.links), 1)
        self.assertEqual(p.links[0]["href"], "/page2")

    def test_ignores_js_mailto_links(self):
        p = self._parse('<html><body><a href="javascript:void(0)">JS</a><a href="mailto:a@b.c">Mail</a></body></html>')
        self.assertEqual(len(p.links), 0)

    def test_word_count(self):
        p = self._parse("<html><body>one two three four five</body></html>")
        self.assertEqual(p.word_count, 5)

    def test_ignores_script_style_text(self):
        p = self._parse("<html><body><script>var x = 1;</script><style>.a{}</style>Hello World</body></html>")
        self.assertEqual(p.word_count, 2)


# ------------------------------------------------------------------
# URL helpers
# ------------------------------------------------------------------
class TestNormalizeUrl(unittest.TestCase):
    def test_relative_url(self):
        result = _normalize_url("https://example.com/page1", "/page2")
        self.assertEqual(result, "https://example.com/page2")

    def test_strips_fragment(self):
        result = _normalize_url("https://example.com/", "/page#section")
        self.assertEqual(result, "https://example.com/page")

    def test_non_http_returns_none(self):
        result = _normalize_url("https://example.com/", "ftp://example.com/file")
        self.assertIsNone(result)


class TestIsInternal(unittest.TestCase):
    def test_same_domain(self):
        self.assertTrue(_is_internal("https://example.com/page", "example.com"))

    def test_different_domain(self):
        self.assertFalse(_is_internal("https://other.com/page", "example.com"))


# ------------------------------------------------------------------
# Page assessment
# ------------------------------------------------------------------
class TestAssessPage(unittest.TestCase):
    def _make_parser(self, title="", meta_desc="", h1s=None, word_count=200):
        p = _SEOHTMLParser()
        p.title = title
        p.meta_description = meta_desc
        p.h1s = h1s or []
        p.word_count = word_count
        return p

    def test_missing_title(self):
        p = self._make_parser(title="")
        findings = _assess_page(p, "https://example.com/", 200)
        types = [f["finding_type"] for f in findings]
        self.assertIn("missing-title", types)

    def test_missing_meta_description(self):
        p = self._make_parser(title="Title", meta_desc="")
        findings = _assess_page(p, "https://example.com/", 200)
        types = [f["finding_type"] for f in findings]
        self.assertIn("missing-meta-description", types)

    def test_missing_h1(self):
        p = self._make_parser(title="Title", meta_desc="Desc")
        findings = _assess_page(p, "https://example.com/", 200)
        types = [f["finding_type"] for f in findings]
        self.assertIn("missing-h1", types)

    def test_thin_content(self):
        p = self._make_parser(title="Title", meta_desc="Desc", h1s=["H1"], word_count=50)
        findings = _assess_page(p, "https://example.com/", 200)
        types = [f["finding_type"] for f in findings]
        self.assertIn("thin-content", types)

    def test_clean_page(self):
        p = self._make_parser(title="Title", meta_desc="Desc", h1s=["H1"], word_count=500)
        findings = _assess_page(p, "https://example.com/", 200)
        self.assertEqual(len(findings), 0)

    def test_http_error(self):
        p = self._make_parser()
        findings = _assess_page(p, "https://example.com/", 404)
        self.assertEqual(findings[0]["finding_type"], "http-error")
        self.assertEqual(findings[0]["severity"], "HIGH")

    def test_title_too_long(self):
        p = self._make_parser(title="A" * 65, meta_desc="Desc", h1s=["H1"])
        findings = _assess_page(p, "https://example.com/", 200)
        types = [f["finding_type"] for f in findings]
        self.assertIn("title-too-long", types)

    def test_multiple_h1(self):
        p = self._make_parser(title="Title", meta_desc="Desc", h1s=["H1", "H2"])
        findings = _assess_page(p, "https://example.com/", 200)
        types = [f["finding_type"] for f in findings]
        self.assertIn("multiple-h1", types)


# ------------------------------------------------------------------
# Single URL analysis (mocked HTTP)
# ------------------------------------------------------------------
class TestAnalyzeSingleUrl(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.db.ensure_schema()
        self.mgr = AuditManager(self.db)

    def tearDown(self):
        self.db.close()

    @patch("searchops.analyzers.crawler._fetch_page")
    def test_successful_analysis(self, mock_fetch):
        html = "<html><head><title>Test</title><meta name='description' content='Desc'></head><body><h1>Hello</h1>" + " word" * 200 + "</body></html>"
        mock_fetch.return_value = (200, "text/html", html)
        result = analyze_single_url("https://example.com/", db=self.db)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["title"], "Test")
        self.assertEqual(result["h1"], "Hello")

    @patch("searchops.analyzers.crawler._fetch_page")
    def test_fetch_failure(self, mock_fetch):
        mock_fetch.return_value = (0, "", "")
        result = analyze_single_url("https://example.com/")
        self.assertEqual(result["status"], "fetch_error")

    @patch("searchops.analyzers.crawler._fetch_page")
    def test_persists_to_db(self, mock_fetch):
        html = "<html><head><title>Test</title></head><body><h1>H</h1>" + " word" * 200 + "</body></html>"
        mock_fetch.return_value = (200, "text/html", html)
        audit_id = self.mgr.create_audit("test", "https://example.com/")
        analyze_single_url("https://example.com/", db=self.db, audit_manager=self.mgr, audit_id=audit_id)
        rows = self.db.execute("SELECT * FROM crawl_pages WHERE audit_id = ?", (audit_id,)).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Test")


# ------------------------------------------------------------------
# Site crawler (mocked HTTP)
# ------------------------------------------------------------------
class TestCrawlSite(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.db.ensure_schema()
        self.mgr = AuditManager(self.db)

    def tearDown(self):
        self.db.close()

    @patch("searchops.analyzers.crawler._load_robots")
    @patch("searchops.analyzers.crawler._fetch_page")
    def test_basic_crawl(self, mock_fetch, mock_robots):
        mock_robots.return_value = None  # No robots.txt
        pages = {
            "https://example.com/": (200, "text/html",
                '<html><head><title>Home</title></head><body><h1>Home</h1>'
                '<a href="/about">About</a>' + ' word' * 200 + '</body></html>'),
            "https://example.com/about": (200, "text/html",
                '<html><head><title>About</title></head><body><h1>About</h1>' + ' word' * 200 + '</body></html>'),
        }
        mock_fetch.side_effect = lambda url, **kw: pages.get(url, (404, "", ""))
        result = crawl_site("https://example.com/", self.db, self.mgr, max_pages=10, max_depth=2)
        self.assertEqual(result["pages_crawled"], 2)
        self.assertIsNotNone(result["audit_id"])
        audit = self.mgr.get_audit(result["audit_id"])
        self.assertEqual(audit["status"], "completed")

    @patch("searchops.analyzers.crawler._load_robots")
    @patch("searchops.analyzers.crawler._fetch_page")
    def test_respects_max_pages(self, mock_fetch, mock_robots):
        mock_robots.return_value = None
        html = '<html><head><title>P</title></head><body><h1>P</h1><a href="/p2">L</a><a href="/p3">L</a>' + ' word' * 200 + '</body></html>'
        mock_fetch.return_value = (200, "text/html", html)
        result = crawl_site("https://example.com/", self.db, self.mgr, max_pages=1, max_depth=5)
        self.assertEqual(result["pages_crawled"], 1)

    @patch("searchops.analyzers.crawler._load_robots")
    @patch("searchops.analyzers.crawler._fetch_page")
    def test_stores_links(self, mock_fetch, mock_robots):
        mock_robots.return_value = None
        html = '<html><head><title>P</title></head><body><h1>H</h1><a href="/page2">Link</a><a href="https://external.com">Ext</a>' + ' word' * 200 + '</body></html>'
        mock_fetch.return_value = (200, "text/html", html)
        result = crawl_site("https://example.com/", self.db, self.mgr, max_pages=1)
        links = self.db.execute("SELECT * FROM crawl_links WHERE audit_id = ?", (result["audit_id"],)).fetchall()
        self.assertGreater(len(links), 0)
        link_types = [l["link_type"] for l in links]
        self.assertIn("internal", link_types)
        self.assertIn("external", link_types)

    def test_invalid_url(self):
        result = crawl_site("not-a-url", self.db, self.mgr)
        self.assertIn("error", result)

    @patch("searchops.analyzers.crawler._load_robots")
    @patch("searchops.analyzers.crawler._fetch_page")
    def test_does_not_follow_external_links(self, mock_fetch, mock_robots):
        mock_robots.return_value = None
        pages = {
            "https://example.com/": (200, "text/html",
                '<html><head><title>Home</title></head><body><h1>Home</h1>'
                '<a href="https://external.com/page">Ext</a>' + ' word' * 200 + '</body></html>'),
        }
        mock_fetch.side_effect = lambda url, **kw: pages.get(url, (404, "", ""))
        result = crawl_site("https://example.com/", self.db, self.mgr, max_pages=10)
        self.assertEqual(result["pages_crawled"], 1)  # Only the start page


if __name__ == "__main__":
    unittest.main()
