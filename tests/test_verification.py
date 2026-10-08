# SPDX-License-Identifier: MIT

"""Tests for the issue verification analyzer."""

import os
import sys
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from searchops.db import DatabaseManager
from searchops.audit import AuditManager
from searchops.analyzers.verification import verify_issue


class TestVerifyIssue(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.db.ensure_schema()
        self.mgr = AuditManager(self.db)
        # Create an audit with various findings
        self.audit_id = self.mgr.create_audit("site-crawl", "https://example.com/")

    def tearDown(self):
        self.db.close()

    def test_finding_not_found(self):
        result = verify_issue(self.mgr, "nonexistent")
        self.assertIn("error", result)

    def test_no_url(self):
        fid = self.mgr.add_finding(
            self.audit_id, "robots-blocks-all", "CRITICAL", "Blocks all",
            url=None,
        )
        result = verify_issue(self.mgr, fid)
        self.assertIsNone(result["resolved"])
        self.assertIn("no URL", result["reason"])

    def test_unsupported_finding_type(self):
        fid = self.mgr.add_finding(
            self.audit_id, "some-unknown-type", "LOW", "Unknown",
            url="https://example.com/",
        )
        result = verify_issue(self.mgr, fid)
        self.assertIsNone(result["resolved"])
        self.assertIn("manual", result["reason"].lower())

    @patch("searchops.analyzers.verification._fetch_page")
    def test_missing_title_resolved(self, mock_fetch):
        fid = self.mgr.add_finding(
            self.audit_id, "missing-title", "HIGH", "Missing title",
            url="https://example.com/page",
        )
        html = "<html><head><title>Fixed Title</title></head><body><h1>H</h1>" + " w" * 200 + "</body></html>"
        mock_fetch.return_value = (200, "text/html", html)
        result = verify_issue(self.mgr, fid)
        self.assertTrue(result["resolved"])
        self.assertIn("Fixed Title", result["reason"])

    @patch("searchops.analyzers.verification._fetch_page")
    def test_missing_title_still_missing(self, mock_fetch):
        fid = self.mgr.add_finding(
            self.audit_id, "missing-title", "HIGH", "Missing title",
            url="https://example.com/page",
        )
        html = "<html><head></head><body>content</body></html>"
        mock_fetch.return_value = (200, "text/html", html)
        result = verify_issue(self.mgr, fid)
        self.assertFalse(result["resolved"])

    @patch("searchops.analyzers.verification._fetch_page")
    def test_missing_h1_resolved(self, mock_fetch):
        fid = self.mgr.add_finding(
            self.audit_id, "missing-h1", "MEDIUM", "Missing H1",
            url="https://example.com/page",
        )
        html = "<html><body><h1>New Heading</h1></body></html>"
        mock_fetch.return_value = (200, "text/html", html)
        result = verify_issue(self.mgr, fid)
        self.assertTrue(result["resolved"])

    @patch("searchops.analyzers.verification._fetch_page")
    def test_missing_meta_resolved(self, mock_fetch):
        fid = self.mgr.add_finding(
            self.audit_id, "missing-meta-description", "MEDIUM", "Missing meta",
            url="https://example.com/page",
        )
        html = '<html><head><meta name="description" content="Now present"></head><body>c</body></html>'
        mock_fetch.return_value = (200, "text/html", html)
        result = verify_issue(self.mgr, fid)
        self.assertTrue(result["resolved"])

    @patch("searchops.analyzers.verification._fetch_page")
    def test_http_error_resolved(self, mock_fetch):
        fid = self.mgr.add_finding(
            self.audit_id, "http-error", "HIGH", "HTTP 404",
            url="https://example.com/page",
            evidence={"status_code": 404},
        )
        mock_fetch.return_value = (200, "text/html", "<html></html>")
        result = verify_issue(self.mgr, fid)
        self.assertTrue(result["resolved"])

    @patch("searchops.analyzers.verification._fetch_page")
    def test_http_error_still_broken(self, mock_fetch):
        fid = self.mgr.add_finding(
            self.audit_id, "http-error", "HIGH", "HTTP 500",
            url="https://example.com/page",
        )
        mock_fetch.return_value = (500, "", "")
        result = verify_issue(self.mgr, fid)
        self.assertFalse(result["resolved"])

    @patch("searchops.analyzers.verification._fetch_page")
    def test_thin_content_resolved(self, mock_fetch):
        fid = self.mgr.add_finding(
            self.audit_id, "thin-content", "MEDIUM", "Thin content",
            url="https://example.com/page",
        )
        html = "<html><body>" + " word" * 150 + "</body></html>"
        mock_fetch.return_value = (200, "text/html", html)
        result = verify_issue(self.mgr, fid)
        self.assertTrue(result["resolved"])

    @patch("searchops.analyzers.verification._fetch_page")
    def test_multiple_h1_resolved(self, mock_fetch):
        fid = self.mgr.add_finding(
            self.audit_id, "multiple-h1", "LOW", "Multiple H1",
            url="https://example.com/page",
        )
        html = "<html><body><h1>Only One</h1></body></html>"
        mock_fetch.return_value = (200, "text/html", html)
        result = verify_issue(self.mgr, fid)
        self.assertTrue(result["resolved"])

    @patch("searchops.analyzers.verification._fetch_page")
    def test_url_unreachable(self, mock_fetch):
        fid = self.mgr.add_finding(
            self.audit_id, "missing-title", "HIGH", "Missing title",
            url="https://example.com/page",
        )
        mock_fetch.return_value = (0, "", "")
        result = verify_issue(self.mgr, fid)
        self.assertFalse(result["resolved"])
        self.assertIn("unreachable", result["reason"].lower())

    def test_result_includes_finding_metadata(self):
        fid = self.mgr.add_finding(
            self.audit_id, "some-unknown-type", "HIGH", "Test Title",
            url="https://example.com/page",
        )
        result = verify_issue(self.mgr, fid)
        self.assertEqual(result["finding_id"], fid)
        self.assertEqual(result["finding_type"], "some-unknown-type")
        self.assertEqual(result["url"], "https://example.com/page")
        self.assertEqual(result["severity"], "HIGH")


if __name__ == "__main__":
    unittest.main()
