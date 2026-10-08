# SPDX-License-Identifier: MIT

"""Tests for the indexing intelligence analyzer."""

import os
import sys
import unittest
from unittest.mock import MagicMock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from searchops.db import DatabaseManager
from searchops.audit import AuditManager
from searchops.analyzers.indexing import (
    _classify_inspection,
    _findings_from_inspection,
    _get_crawled_urls,
    audit_indexing,
)


def _make_inspection_result(
    verdict="PASS",
    coverage="Submitted and indexed",
    robots="ALLOWED",
    indexing="INDEXING_ALLOWED",
    page_fetch="SUCCESSFUL",
    user_canonical="",
    google_canonical="",
):
    return {
        "inspectionResult": {
            "indexStatusResult": {
                "verdict": verdict,
                "coverageState": coverage,
                "robotsTxtState": robots,
                "indexingState": indexing,
                "pageFetchState": page_fetch,
                "crawledAs": "DESKTOP",
                "lastCrawlTime": "2025-01-15T10:00:00Z",
                "userCanonical": user_canonical,
                "googleCanonical": google_canonical,
            }
        }
    }


class TestClassifyInspection(unittest.TestCase):
    def test_indexed_page(self):
        result = _make_inspection_result(verdict="PASS")
        info = _classify_inspection(result)
        self.assertTrue(info["is_indexed"])
        self.assertEqual(info["verdict"], "PASS")

    def test_not_indexed(self):
        result = _make_inspection_result(verdict="FAIL", coverage="Crawled - currently not indexed")
        info = _classify_inspection(result)
        self.assertFalse(info["is_indexed"])

    def test_canonical_info(self):
        result = _make_inspection_result(
            user_canonical="https://example.com/a",
            google_canonical="https://example.com/b",
        )
        info = _classify_inspection(result)
        self.assertEqual(info["user_canonical"], "https://example.com/a")
        self.assertEqual(info["google_canonical"], "https://example.com/b")


class TestFindingsFromInspection(unittest.TestCase):
    def test_indexed_no_findings(self):
        info = _classify_inspection(_make_inspection_result())
        findings = _findings_from_inspection("https://example.com/", info)
        self.assertEqual(len(findings), 0)

    def test_not_indexed_finding(self):
        info = _classify_inspection(
            _make_inspection_result(verdict="FAIL", coverage="Crawled - currently not indexed")
        )
        findings = _findings_from_inspection("https://example.com/page", info)
        self.assertTrue(any(f["finding_type"] == "not-indexed" for f in findings))
        self.assertTrue(any(f["severity"] == "HIGH" for f in findings))

    def test_noindex_tag(self):
        info = _classify_inspection(
            _make_inspection_result(verdict="FAIL", coverage="Excluded by noindex tag")
        )
        findings = _findings_from_inspection("https://example.com/page", info)
        self.assertTrue(any(f["finding_type"] == "noindex-tag" for f in findings))

    def test_blocked_by_robots(self):
        info = _classify_inspection(
            _make_inspection_result(verdict="FAIL", coverage="Blocked", robots="DISALLOWED")
        )
        findings = _findings_from_inspection("https://example.com/page", info)
        self.assertTrue(any(f["finding_type"] == "blocked-by-robots" for f in findings))

    def test_redirect(self):
        info = _classify_inspection(
            _make_inspection_result(verdict="FAIL", coverage="Page with redirect")
        )
        findings = _findings_from_inspection("https://example.com/old", info)
        self.assertTrue(any(f["finding_type"] == "redirect-not-indexed" for f in findings))

    def test_canonical_mismatch(self):
        info = _classify_inspection(_make_inspection_result(
            user_canonical="https://example.com/a",
            google_canonical="https://example.com/b",
        ))
        findings = _findings_from_inspection("https://example.com/a", info)
        self.assertTrue(any(f["finding_type"] == "canonical-mismatch" for f in findings))

    def test_no_canonical_mismatch_when_same(self):
        info = _classify_inspection(_make_inspection_result(
            user_canonical="https://example.com/a",
            google_canonical="https://example.com/a",
        ))
        findings = _findings_from_inspection("https://example.com/a", info)
        self.assertFalse(any(f["finding_type"] == "canonical-mismatch" for f in findings))

    def test_page_fetch_issue(self):
        info = _classify_inspection(_make_inspection_result(page_fetch="SOFT_404"))
        findings = _findings_from_inspection("https://example.com/page", info)
        self.assertTrue(any(f["finding_type"] == "page-fetch-issue" for f in findings))


class TestGetCrawledUrls(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.db.ensure_schema()

    def tearDown(self):
        self.db.close()

    def test_returns_urls_from_crawl(self):
        mgr = AuditManager(self.db)
        audit_id = mgr.create_audit("crawl", "https://example.com/")
        self.db.execute(
            "INSERT INTO crawl_pages (id, audit_id, url, status_code) VALUES (?, ?, ?, ?)",
            ("p1", audit_id, "https://example.com/page1", 200),
        )
        self.db.execute(
            "INSERT INTO crawl_pages (id, audit_id, url, status_code) VALUES (?, ?, ?, ?)",
            ("p2", audit_id, "https://example.com/page2", 200),
        )
        self.db.commit()
        urls = _get_crawled_urls(self.db, audit_id)
        self.assertEqual(len(urls), 2)

    def test_empty_crawl(self):
        urls = _get_crawled_urls(self.db, "nonexistent")
        self.assertEqual(urls, [])


class TestAuditIndexing(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.db.ensure_schema()
        self.mgr = AuditManager(self.db)
        self.mock_provider = MagicMock()

    def tearDown(self):
        self.db.close()

    def test_explicit_urls(self):
        self.mock_provider.inspect_url.return_value = _make_inspection_result()
        result = audit_indexing(
            self.mock_provider, self.db, self.mgr,
            "https://example.com/",
            urls=["https://example.com/page1"],
        )
        self.assertEqual(result["urls_checked"], 1)
        self.assertEqual(result["indexed_count"], 1)
        self.assertIsNotNone(result["audit_id"])

    def test_not_indexed_creates_finding(self):
        self.mock_provider.inspect_url.return_value = _make_inspection_result(
            verdict="FAIL", coverage="Crawled - currently not indexed",
        )
        result = audit_indexing(
            self.mock_provider, self.db, self.mgr,
            "https://example.com/",
            urls=["https://example.com/page1"],
        )
        self.assertEqual(result["not_indexed_count"], 1)
        self.assertGreater(result["findings_count"], 0)
        findings = self.mgr.get_findings(result["audit_id"])
        self.assertTrue(any(f["finding_type"] == "not-indexed" for f in findings))

    def test_from_crawl_audit(self):
        # Create parent audit, then insert crawl pages
        crawl_audit_id = self.mgr.create_audit("site-crawl", "https://example.com/")
        self.db.execute(
            "INSERT INTO crawl_pages (id, audit_id, url, status_code) VALUES (?, ?, ?, ?)",
            ("p1", crawl_audit_id, "https://example.com/page1", 200),
        )
        self.db.commit()
        self.mock_provider.inspect_url.return_value = _make_inspection_result()
        result = audit_indexing(
            self.mock_provider, self.db, self.mgr,
            "https://example.com/",
            crawl_audit_id=crawl_audit_id,
        )
        self.assertEqual(result["urls_checked"], 1)

    def test_no_urls_no_crawl(self):
        result = audit_indexing(
            self.mock_provider, self.db, self.mgr,
            "https://example.com/",
        )
        self.assertIn("error", result)

    def test_empty_url_list(self):
        result = audit_indexing(
            self.mock_provider, self.db, self.mgr,
            "https://example.com/",
            urls=[],
        )
        self.assertEqual(result["urls_checked"], 0)
        self.assertIsNone(result["audit_id"])

    def test_api_error_logged(self):
        self.mock_provider.inspect_url.side_effect = RuntimeError("API error")
        result = audit_indexing(
            self.mock_provider, self.db, self.mgr,
            "https://example.com/",
            urls=["https://example.com/page1"],
        )
        # Should complete (with errors logged), not raise
        self.assertIsNotNone(result["audit_id"])
        self.assertIsNotNone(result["errors"])

    def test_batch_size_caps(self):
        urls = [f"https://example.com/page{i}" for i in range(100)]
        self.mock_provider.inspect_url.return_value = _make_inspection_result()
        result = audit_indexing(
            self.mock_provider, self.db, self.mgr,
            "https://example.com/",
            urls=urls,
            batch_size=5,
        )
        self.assertEqual(result["urls_checked"], 5)
        self.assertEqual(self.mock_provider.inspect_url.call_count, 5)

    def test_audit_completed(self):
        self.mock_provider.inspect_url.return_value = _make_inspection_result()
        result = audit_indexing(
            self.mock_provider, self.db, self.mgr,
            "https://example.com/",
            urls=["https://example.com/"],
        )
        audit = self.mgr.get_audit(result["audit_id"])
        self.assertEqual(audit["status"], "completed")

    def test_mixed_results(self):
        def side_effect(site_url, url):
            if url.endswith("/good"):
                return _make_inspection_result()
            return _make_inspection_result(verdict="FAIL", coverage="Crawled - currently not indexed")

        self.mock_provider.inspect_url.side_effect = side_effect
        result = audit_indexing(
            self.mock_provider, self.db, self.mgr,
            "https://example.com/",
            urls=["https://example.com/good", "https://example.com/bad"],
        )
        self.assertEqual(result["indexed_count"], 1)
        self.assertEqual(result["not_indexed_count"], 1)


if __name__ == "__main__":
    unittest.main()
