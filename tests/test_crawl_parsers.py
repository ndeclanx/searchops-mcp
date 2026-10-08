# SPDX-License-Identifier: MIT

"""Tests for the crawl parsers (robots.txt and sitemap)."""

import os
import sys
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from searchops.db import DatabaseManager
from searchops.audit import AuditManager
from searchops.analyzers.crawl_parsers import (
    _robots_url,
    _parse_robots_lines,
    _assess_robots,
    _parse_sitemap_xml,
    _assess_sitemap,
    analyze_robots,
    parse_sitemap,
)


# ------------------------------------------------------------------
# robots.txt helpers
# ------------------------------------------------------------------
class TestRobotsUrl(unittest.TestCase):
    def test_normal_url(self):
        self.assertEqual(_robots_url("https://example.com/"), "https://example.com/robots.txt")

    def test_sc_domain(self):
        self.assertEqual(_robots_url("sc-domain:example.com"), "https://example.com/robots.txt")

    def test_no_trailing_slash(self):
        self.assertEqual(_robots_url("https://example.com"), "https://example.com/robots.txt")


class TestParseRobotsLines(unittest.TestCase):
    def test_basic_directives(self):
        body = "User-agent: *\nDisallow: /admin/\nAllow: /public/\nSitemap: https://example.com/sitemap.xml"
        directives = _parse_robots_lines(body)
        types = [d["type"] for d in directives]
        self.assertIn("user-agent", types)
        self.assertIn("disallow", types)
        self.assertIn("allow", types)
        self.assertIn("sitemap", types)

    def test_comments_stripped(self):
        body = "User-agent: * # all bots\nDisallow: /private/ # secret"
        directives = _parse_robots_lines(body)
        self.assertEqual(len(directives), 2)
        self.assertEqual(directives[1]["path"], "/private/")

    def test_empty_body(self):
        self.assertEqual(_parse_robots_lines(""), [])

    def test_syntax_error(self):
        body = "User-agent: *\nthis is invalid\nDisallow: /"
        directives = _parse_robots_lines(body)
        types = [d["type"] for d in directives]
        self.assertIn("syntax-error", types)

    def test_crawl_delay(self):
        body = "User-agent: *\nCrawl-delay: 10"
        directives = _parse_robots_lines(body)
        self.assertEqual(directives[1]["type"], "crawl-delay")
        self.assertEqual(directives[1]["value"], "10")

    def test_unknown_directive(self):
        body = "User-agent: *\nFoo: bar"
        directives = _parse_robots_lines(body)
        self.assertEqual(directives[1]["type"], "unknown-directive")
        self.assertEqual(directives[1]["field"], "foo")


class TestAssessRobots(unittest.TestCase):
    def test_blocks_all(self):
        directives = [
            {"type": "user-agent", "agent": "*", "line": 1},
            {"type": "disallow", "agent": "*", "path": "/", "line": 2},
        ]
        findings = _assess_robots(directives, "https://example.com/")
        types = [f["finding_type"] for f in findings]
        self.assertIn("robots-blocks-all", types)
        crit = [f for f in findings if f["finding_type"] == "robots-blocks-all"]
        self.assertEqual(crit[0]["severity"], "CRITICAL")

    def test_no_sitemap_directive(self):
        directives = [
            {"type": "user-agent", "agent": "*", "line": 1},
            {"type": "disallow", "agent": "*", "path": "/admin/", "line": 2},
        ]
        findings = _assess_robots(directives, "https://example.com/")
        types = [f["finding_type"] for f in findings]
        self.assertIn("robots-no-sitemap", types)

    def test_static_assets_blocked(self):
        directives = [
            {"type": "disallow", "agent": "*", "path": "/css/", "line": 1},
        ]
        findings = _assess_robots(directives, "https://example.com/")
        types = [f["finding_type"] for f in findings]
        self.assertIn("static-assets-blocked", types)

    def test_clean_robots(self):
        directives = [
            {"type": "user-agent", "agent": "*", "line": 1},
            {"type": "disallow", "agent": "*", "path": "/admin/", "line": 2},
            {"type": "sitemap", "url": "https://example.com/sitemap.xml", "line": 3},
        ]
        findings = _assess_robots(directives, "https://example.com/")
        self.assertEqual(len(findings), 0)


# ------------------------------------------------------------------
# robots.txt integration (with mocked HTTP)
# ------------------------------------------------------------------
class TestAnalyzeRobots(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.db.ensure_schema()
        self.mgr = AuditManager(self.db)

    def tearDown(self):
        self.db.close()

    @patch("searchops.analyzers.crawl_parsers._fetch_url")
    def test_normal_robots(self, mock_fetch):
        mock_fetch.return_value = (200, "User-agent: *\nDisallow: /admin/\nSitemap: https://example.com/sitemap.xml")
        result = analyze_robots("https://example.com/", audit_manager=self.mgr)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["disallow_count"], 1)
        self.assertEqual(result["sitemap_urls"], ["https://example.com/sitemap.xml"])
        # No issues found, so no audit created
        self.assertIsNone(result["audit_id"])

    @patch("searchops.analyzers.crawl_parsers._fetch_url")
    def test_404_robots(self, mock_fetch):
        mock_fetch.return_value = (404, "")
        result = analyze_robots("https://example.com/")
        self.assertEqual(result["status"], "not_found")

    @patch("searchops.analyzers.crawl_parsers._fetch_url")
    def test_blocks_all_creates_audit(self, mock_fetch):
        mock_fetch.return_value = (200, "User-agent: *\nDisallow: /")
        result = analyze_robots("https://example.com/", audit_manager=self.mgr)
        self.assertIsNotNone(result["audit_id"])
        self.assertGreater(result["findings_count"], 0)
        audit = self.mgr.get_audit(result["audit_id"])
        self.assertEqual(audit["status"], "completed")

    @patch("searchops.analyzers.crawl_parsers._fetch_url")
    def test_fetch_error(self, mock_fetch):
        from urllib.error import URLError
        mock_fetch.side_effect = URLError("connection refused")
        result = analyze_robots("https://example.com/")
        self.assertEqual(result["status"], "fetch_error")

    @patch("searchops.analyzers.crawl_parsers._fetch_url")
    def test_no_audit_manager(self, mock_fetch):
        mock_fetch.return_value = (200, "User-agent: *\nDisallow: /")
        result = analyze_robots("https://example.com/", audit_manager=None)
        # Findings detected but no audit since no manager
        self.assertIsNone(result["audit_id"])
        self.assertGreater(result["findings_count"], 0)


# ------------------------------------------------------------------
# Sitemap XML parser
# ------------------------------------------------------------------
class TestParseSitemapXml(unittest.TestCase):
    def test_urlset(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/page1</loc><lastmod>2025-01-01</lastmod></url>
            <url><loc>https://example.com/page2</loc></url>
        </urlset>"""
        parsed = _parse_sitemap_xml(xml)
        self.assertEqual(parsed["type"], "sitemap")
        self.assertEqual(len(parsed["urls"]), 2)
        self.assertEqual(parsed["urls"][0]["loc"], "https://example.com/page1")
        self.assertEqual(parsed["urls"][0]["lastmod"], "2025-01-01")

    def test_sitemapindex(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <sitemap><loc>https://example.com/sitemap1.xml</loc></sitemap>
            <sitemap><loc>https://example.com/sitemap2.xml</loc></sitemap>
        </sitemapindex>"""
        parsed = _parse_sitemap_xml(xml)
        self.assertEqual(parsed["type"], "sitemapindex")
        self.assertEqual(len(parsed["sitemaps"]), 2)

    def test_invalid_xml(self):
        parsed = _parse_sitemap_xml("this is not xml")
        self.assertTrue(len(parsed["errors"]) > 0)

    def test_unknown_root(self):
        xml = "<root><item>test</item></root>"
        parsed = _parse_sitemap_xml(xml)
        self.assertTrue(len(parsed["errors"]) > 0)
        self.assertIn("unknown_root_element", parsed["errors"][0]["error"])

    def test_changefreq_and_priority(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url>
                <loc>https://example.com/</loc>
                <changefreq>daily</changefreq>
                <priority>1.0</priority>
            </url>
        </urlset>"""
        parsed = _parse_sitemap_xml(xml)
        self.assertEqual(parsed["urls"][0]["changefreq"], "daily")
        self.assertEqual(parsed["urls"][0]["priority"], "1.0")


class TestAssessSitemap(unittest.TestCase):
    def test_domain_mismatch(self):
        parsed = {
            "type": "sitemap",
            "urls": [
                {"loc": "https://other-domain.com/page1"},
                {"loc": "https://example.com/page2"},
            ],
            "sitemaps": [],
            "errors": [],
        }
        findings = _assess_sitemap(parsed, "https://example.com/sitemap.xml", "https://example.com/")
        types = [f["finding_type"] for f in findings]
        self.assertIn("sitemap-domain-mismatch", types)

    def test_no_lastmod(self):
        parsed = {
            "type": "sitemap",
            "urls": [{"loc": "https://example.com/page1"}, {"loc": "https://example.com/page2"}],
            "sitemaps": [],
            "errors": [],
        }
        findings = _assess_sitemap(parsed, "https://example.com/sitemap.xml", "https://example.com/")
        types = [f["finding_type"] for f in findings]
        self.assertIn("sitemap-no-lastmod", types)

    def test_clean_sitemap(self):
        parsed = {
            "type": "sitemap",
            "urls": [{"loc": "https://example.com/page1", "lastmod": "2025-01-01"}],
            "sitemaps": [],
            "errors": [],
        }
        findings = _assess_sitemap(parsed, "https://example.com/sitemap.xml", "https://example.com/")
        self.assertEqual(len(findings), 0)

    def test_parse_error_finding(self):
        parsed = {
            "type": "sitemap",
            "urls": [],
            "sitemaps": [],
            "errors": [{"error": "xml_parse_error", "detail": "bad xml"}],
        }
        findings = _assess_sitemap(parsed, "https://example.com/sitemap.xml", None)
        self.assertEqual(findings[0]["severity"], "HIGH")


# ------------------------------------------------------------------
# Sitemap integration (with mocked HTTP)
# ------------------------------------------------------------------
class TestParseSitemap(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.db.ensure_schema()
        self.mgr = AuditManager(self.db)

    def tearDown(self):
        self.db.close()

    @patch("searchops.analyzers.crawl_parsers._fetch_url")
    def test_valid_sitemap(self, mock_fetch):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/page1</loc><lastmod>2025-01-01</lastmod></url>
        </urlset>"""
        mock_fetch.return_value = (200, xml)
        result = parse_sitemap("https://example.com/sitemap.xml", site_url="https://example.com/", audit_manager=self.mgr)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["url_count"], 1)
        self.assertEqual(result["type"], "sitemap")

    @patch("searchops.analyzers.crawl_parsers._fetch_url")
    def test_sitemap_with_issues(self, mock_fetch):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://other.com/page1</loc></url>
        </urlset>"""
        mock_fetch.return_value = (200, xml)
        result = parse_sitemap("https://example.com/sitemap.xml", site_url="https://example.com/", audit_manager=self.mgr)
        self.assertIsNotNone(result["audit_id"])
        self.assertGreater(result["findings_count"], 0)

    @patch("searchops.analyzers.crawl_parsers._fetch_url")
    def test_fetch_error(self, mock_fetch):
        from urllib.error import URLError
        mock_fetch.side_effect = URLError("timeout")
        result = parse_sitemap("https://example.com/sitemap.xml")
        self.assertEqual(result["status"], "fetch_error")

    @patch("searchops.analyzers.crawl_parsers._fetch_url")
    def test_http_error(self, mock_fetch):
        mock_fetch.return_value = (500, "")
        result = parse_sitemap("https://example.com/sitemap.xml")
        self.assertEqual(result["status"], "http_500")

    @patch("searchops.analyzers.crawl_parsers._fetch_url")
    def test_sitemapindex_parsed(self, mock_fetch):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <sitemap><loc>https://example.com/sitemap1.xml</loc></sitemap>
        </sitemapindex>"""
        mock_fetch.return_value = (200, xml)
        result = parse_sitemap("https://example.com/sitemap.xml")
        self.assertEqual(result["type"], "sitemapindex")
        self.assertEqual(result["sitemap_count"], 1)


if __name__ == "__main__":
    unittest.main()
