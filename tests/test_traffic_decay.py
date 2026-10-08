# SPDX-License-Identifier: MIT

"""Tests for the traffic decay analyzer."""

import os
import sys
import unittest
from unittest.mock import MagicMock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from searchops.db import DatabaseManager
from searchops.audit import AuditManager
from searchops.analyzers.traffic_decay import (
    _build_lookup,
    _classify_decay,
    detect_traffic_decay,
    DEFAULT_THRESHOLDS,
)


def _make_row(query, clicks, impressions, ctr, position):
    return {"keys": [query], "clicks": clicks, "impressions": impressions, "ctr": ctr, "position": position}


class TestBuildLookup(unittest.TestCase):
    def test_basic(self):
        rows = [_make_row("test", 10, 100, 0.1, 3.0)]
        lookup = _build_lookup(rows)
        self.assertIn("test", lookup)
        self.assertEqual(lookup["test"]["ctr_pct"], 10.0)

    def test_empty(self):
        self.assertEqual(_build_lookup([]), {})


class TestClassifyDecay(unittest.TestCase):
    def setUp(self):
        self.thresholds = dict(DEFAULT_THRESHOLDS)

    def test_impressions_declined(self):
        baseline = {"query": "q", "clicks": 50, "impressions": 100, "ctr_pct": 50.0, "position": 3.0}
        current = {"query": "q", "clicks": 10, "impressions": 50, "ctr_pct": 20.0, "position": 3.0}
        results = _classify_decay(baseline, current, self.thresholds)
        types = [r[0] for r in results]
        self.assertIn("impressions-declined", types)

    def test_position_declined(self):
        baseline = {"query": "q", "clicks": 10, "impressions": 100, "ctr_pct": 10.0, "position": 3.0}
        current = {"query": "q", "clicks": 10, "impressions": 100, "ctr_pct": 10.0, "position": 6.0}
        results = _classify_decay(baseline, current, self.thresholds)
        types = [r[0] for r in results]
        self.assertIn("position-declined", types)

    def test_ctr_declined(self):
        baseline = {"query": "q", "clicks": 10, "impressions": 100, "ctr_pct": 10.0, "position": 3.0}
        current = {"query": "q", "clicks": 5, "impressions": 100, "ctr_pct": 5.0, "position": 3.0}
        results = _classify_decay(baseline, current, self.thresholds)
        types = [r[0] for r in results]
        self.assertIn("ctr-declined", types)

    def test_no_decay(self):
        baseline = {"query": "q", "clicks": 10, "impressions": 100, "ctr_pct": 10.0, "position": 3.0}
        current = {"query": "q", "clicks": 15, "impressions": 120, "ctr_pct": 12.5, "position": 2.5}
        results = _classify_decay(baseline, current, self.thresholds)
        self.assertEqual(results, [])

    def test_multiple_decays(self):
        baseline = {"query": "q", "clicks": 50, "impressions": 100, "ctr_pct": 50.0, "position": 2.0}
        current = {"query": "q", "clicks": 5, "impressions": 30, "ctr_pct": 16.7, "position": 8.0}
        results = _classify_decay(baseline, current, self.thresholds)
        types = [r[0] for r in results]
        self.assertIn("impressions-declined", types)
        self.assertIn("position-declined", types)
        self.assertIn("ctr-declined", types)


class TestDetectTrafficDecay(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.db.ensure_schema()
        self.mgr = AuditManager(self.db)
        self.mock_provider = MagicMock()

    def tearDown(self):
        self.db.close()

    def test_no_baseline_data(self):
        self.mock_provider.search_analytics.return_value = {"rows": []}
        result = detect_traffic_decay(
            self.mock_provider, self.mgr, "https://example.com/",
            "2025-02-01", "2025-02-14", "2025-01-15", "2025-01-31",
        )
        self.assertEqual(result["total_decays"], 0)
        self.assertIsNone(result["audit_id"])

    def test_decay_detected(self):
        self.mock_provider.search_analytics.side_effect = [
            {"rows": [_make_row("test query", 50, 200, 0.25, 3.0)]},  # baseline
            {"rows": [_make_row("test query", 10, 80, 0.125, 5.5)]},  # current
        ]
        result = detect_traffic_decay(
            self.mock_provider, self.mgr, "https://example.com/",
            "2025-02-01", "2025-02-14", "2025-01-15", "2025-01-31",
        )
        self.assertGreater(result["total_decays"], 0)
        self.assertIn("impressions-declined", result["decays"])
        audit = self.mgr.get_audit(result["audit_id"])
        self.assertEqual(audit["status"], "completed")

    def test_query_disappeared(self):
        self.mock_provider.search_analytics.side_effect = [
            {"rows": [_make_row("gone query", 50, 200, 0.25, 3.0)]},  # baseline
            {"rows": []},  # current - query gone
        ]
        result = detect_traffic_decay(
            self.mock_provider, self.mgr, "https://example.com/",
            "2025-02-01", "2025-02-14", "2025-01-15", "2025-01-31",
        )
        self.assertIn("impressions-declined", result["decays"])

    def test_low_impressions_filtered(self):
        self.mock_provider.search_analytics.side_effect = [
            {"rows": [_make_row("low", 1, 5, 0.2, 10.0)]},  # below min threshold
            {"rows": [_make_row("low", 0, 0, 0.0, 0.0)]},
        ]
        result = detect_traffic_decay(
            self.mock_provider, self.mgr, "https://example.com/",
            "2025-02-01", "2025-02-14", "2025-01-15", "2025-01-31",
        )
        self.assertEqual(result["total_decays"], 0)

    def test_custom_thresholds(self):
        self.mock_provider.search_analytics.side_effect = [
            {"rows": [_make_row("q", 10, 100, 0.1, 3.0)]},
            {"rows": [_make_row("q", 9, 90, 0.1, 3.0)]},  # 10% drop
        ]
        # Default 20% threshold: no flag
        result = detect_traffic_decay(
            self.mock_provider, self.mgr, "https://example.com/",
            "2025-02-01", "2025-02-14", "2025-01-15", "2025-01-31",
        )
        self.assertNotIn("impressions-declined", result.get("decays", {}))

        # Custom 5% threshold: flag
        self.mock_provider.search_analytics.side_effect = [
            {"rows": [_make_row("q2", 10, 100, 0.1, 3.0)]},
            {"rows": [_make_row("q2", 9, 90, 0.1, 3.0)]},
        ]
        result2 = detect_traffic_decay(
            self.mock_provider, self.mgr, "https://example.com/",
            "2025-02-01", "2025-02-14", "2025-01-15", "2025-01-31",
            impressions_decline_pct=5.0,
        )
        self.assertIn("impressions-declined", result2["decays"])

    def test_api_error_propagates(self):
        self.mock_provider.search_analytics.side_effect = RuntimeError("API error")
        with self.assertRaises(RuntimeError):
            detect_traffic_decay(
                self.mock_provider, self.mgr, "https://example.com/",
                "2025-02-01", "2025-02-14", "2025-01-15", "2025-01-31",
            )


if __name__ == "__main__":
    unittest.main()
