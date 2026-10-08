# SPDX-License-Identifier: MIT

"""Tests for the cannibalization analyzer."""

import os
import sys
import unittest
from unittest.mock import MagicMock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from searchops.db import DatabaseManager
from searchops.audit import AuditManager
from searchops.analyzers.cannibalization import (
    _group_by_query,
    _analyze_query_group,
    detect_cannibalization,
    DEFAULT_THRESHOLDS,
)


def _make_row(query, page, clicks, impressions, ctr, position):
    return {"keys": [query, page], "clicks": clicks, "impressions": impressions, "ctr": ctr, "position": position}


class TestGroupByQuery(unittest.TestCase):
    def test_groups_correctly(self):
        rows = [
            _make_row("q1", "/a", 10, 100, 0.1, 3.0),
            _make_row("q1", "/b", 5, 80, 0.06, 5.0),
            _make_row("q2", "/c", 20, 200, 0.1, 2.0),
        ]
        groups = _group_by_query(rows)
        self.assertEqual(len(groups["q1"]), 2)
        self.assertEqual(len(groups["q2"]), 1)

    def test_empty(self):
        self.assertEqual(_group_by_query([]), {})


class TestAnalyzeQueryGroup(unittest.TestCase):
    def setUp(self):
        self.thresholds = dict(DEFAULT_THRESHOLDS)

    def test_cannibalization_detected(self):
        pages = [
            {"query": "q", "page": "/a", "clicks": 10, "impressions": 100, "ctr_pct": 10.0, "position": 3.0},
            {"query": "q", "page": "/b", "clicks": 2, "impressions": 80, "ctr_pct": 2.5, "position": 8.0},
        ]
        result = _analyze_query_group("q", pages, self.thresholds)
        self.assertIsNotNone(result)
        self.assertEqual(result["page_count"], 2)
        self.assertEqual(result["best_page"], "/a")

    def test_no_cannibalization_single_page(self):
        pages = [
            {"query": "q", "page": "/a", "clicks": 10, "impressions": 100, "ctr_pct": 10.0, "position": 3.0},
        ]
        result = _analyze_query_group("q", pages, self.thresholds)
        self.assertIsNone(result)

    def test_no_cannibalization_low_impressions(self):
        pages = [
            {"query": "q", "page": "/a", "clicks": 1, "impressions": 5, "ctr_pct": 20.0, "position": 3.0},
            {"query": "q", "page": "/b", "clicks": 0, "impressions": 3, "ctr_pct": 0.0, "position": 10.0},
        ]
        result = _analyze_query_group("q", pages, self.thresholds)
        self.assertIsNone(result)

    def test_no_cannibalization_low_ctr_spread(self):
        pages = [
            {"query": "q", "page": "/a", "clicks": 5, "impressions": 50, "ctr_pct": 10.0, "position": 3.0},
            {"query": "q", "page": "/b", "clicks": 5, "impressions": 50, "ctr_pct": 9.8, "position": 3.5},
        ]
        result = _analyze_query_group("q", pages, self.thresholds)
        self.assertIsNone(result)


class TestDetectCannibalization(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.db.ensure_schema()
        self.mgr = AuditManager(self.db)
        self.mock_provider = MagicMock()

    def tearDown(self):
        self.db.close()

    def test_no_data(self):
        self.mock_provider.search_analytics.return_value = {"rows": []}
        result = detect_cannibalization(
            self.mock_provider, self.mgr, "https://example.com/",
            "2025-01-01", "2025-01-31",
        )
        self.assertEqual(result["total_cannibalized"], 0)
        self.assertIsNone(result["audit_id"])

    def test_cannibalization_found(self):
        self.mock_provider.search_analytics.return_value = {
            "rows": [
                _make_row("shared query", "/page-a", 10, 100, 0.1, 3.0),
                _make_row("shared query", "/page-b", 2, 80, 0.025, 8.0),
            ]
        }
        result = detect_cannibalization(
            self.mock_provider, self.mgr, "https://example.com/",
            "2025-01-01", "2025-01-31",
        )
        self.assertEqual(result["queries_affected"], 1)
        findings = self.mgr.get_findings(result["audit_id"])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["finding_type"], "cannibalization")

    def test_audit_completed(self):
        self.mock_provider.search_analytics.return_value = {
            "rows": [
                _make_row("q", "/a", 10, 100, 0.1, 3.0),
                _make_row("q", "/b", 2, 50, 0.04, 7.0),
            ]
        }
        result = detect_cannibalization(
            self.mock_provider, self.mgr, "https://example.com/",
            "2025-01-01", "2025-01-31",
        )
        audit = self.mgr.get_audit(result["audit_id"])
        self.assertEqual(audit["status"], "completed")

    def test_high_severity_many_pages(self):
        self.mock_provider.search_analytics.return_value = {
            "rows": [
                _make_row("q", "/a", 10, 100, 0.1, 2.0),
                _make_row("q", "/b", 3, 80, 0.04, 5.0),
                _make_row("q", "/c", 1, 60, 0.02, 8.0),
                _make_row("q", "/d", 0, 40, 0.0, 12.0),
            ]
        }
        result = detect_cannibalization(
            self.mock_provider, self.mgr, "https://example.com/",
            "2025-01-01", "2025-01-31",
        )
        findings = self.mgr.get_findings(result["audit_id"])
        self.assertEqual(findings[0]["severity"], "HIGH")

    def test_api_error(self):
        self.mock_provider.search_analytics.side_effect = RuntimeError("API error")
        with self.assertRaises(RuntimeError):
            detect_cannibalization(
                self.mock_provider, self.mgr, "https://example.com/",
                "2025-01-01", "2025-01-31",
            )


if __name__ == "__main__":
    unittest.main()
