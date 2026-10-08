# SPDX-License-Identifier: MIT

"""Tests for the PageSpeed Insights analyzer."""

import os
import sys
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from searchops.db import DatabaseManager
from searchops.audit import AuditManager
from searchops.analyzers.pagespeed import (
    _extract_metrics,
    _assess_performance,
    analyze_performance,
)


def _make_psi_response(score=0.95, lcp_ms=2000, cls=0.05, tbt_ms=100, fcp_ms=1500):
    """Build a realistic PSI API response."""
    return {
        "lighthouseResult": {
            "categories": {
                "performance": {"score": score},
            },
            "audits": {
                "first-contentful-paint": {
                    "numericValue": fcp_ms,
                    "displayValue": f"{fcp_ms / 1000:.1f} s",
                    "score": 0.9,
                },
                "largest-contentful-paint": {
                    "numericValue": lcp_ms,
                    "displayValue": f"{lcp_ms / 1000:.1f} s",
                    "score": 0.8,
                },
                "total-blocking-time": {
                    "numericValue": tbt_ms,
                    "displayValue": f"{tbt_ms} ms",
                    "score": 0.9,
                },
                "cumulative-layout-shift": {
                    "numericValue": cls,
                    "displayValue": str(cls),
                    "score": 0.95,
                },
                "speed-index": {
                    "numericValue": 3000,
                    "displayValue": "3.0 s",
                    "score": 0.7,
                },
                "interactive": {
                    "numericValue": 4000,
                    "displayValue": "4.0 s",
                    "score": 0.6,
                },
            },
        },
        "loadingExperience": {
            "overall_category": "FAST",
            "metrics": {
                "LARGEST_CONTENTFUL_PAINT_MS": {
                    "percentile": lcp_ms,
                    "category": "FAST",
                },
                "CUMULATIVE_LAYOUT_SHIFT_SCORE": {
                    "percentile": int(cls * 100),
                    "category": "FAST",
                },
            },
        },
    }


class TestExtractMetrics(unittest.TestCase):
    def test_extracts_score(self):
        data = _make_psi_response(score=0.85)
        metrics = _extract_metrics(data)
        self.assertEqual(metrics["performance_score"], 85)

    def test_extracts_lab_data(self):
        data = _make_psi_response(lcp_ms=2500)
        metrics = _extract_metrics(data)
        self.assertIn("LCP", metrics["lab_data"])
        self.assertEqual(metrics["lab_data"]["LCP"]["value"], 2500)

    def test_extracts_field_data(self):
        data = _make_psi_response()
        metrics = _extract_metrics(data)
        self.assertIn("LCP", metrics["field_data"])

    def test_handles_missing_data(self):
        data = {"lighthouseResult": {"categories": {}, "audits": {}}, "loadingExperience": {}}
        metrics = _extract_metrics(data)
        self.assertEqual(metrics["performance_score"], 0)
        self.assertEqual(metrics["lab_data"], {})


class TestAssessPerformance(unittest.TestCase):
    def test_good_performance_no_findings(self):
        metrics = {
            "performance_score": 95,
            "lab_data": {
                "LCP": {"value": 2000},
                "CLS": {"value": 0.05},
                "TBT": {"value": 100},
            },
        }
        findings = _assess_performance("https://example.com/", metrics)
        self.assertEqual(len(findings), 0)

    def test_poor_performance(self):
        metrics = {"performance_score": 30, "lab_data": {}}
        findings = _assess_performance("https://example.com/", metrics)
        types = [f["finding_type"] for f in findings]
        self.assertIn("poor-performance", types)

    def test_needs_improvement(self):
        metrics = {"performance_score": 70, "lab_data": {}}
        findings = _assess_performance("https://example.com/", metrics)
        types = [f["finding_type"] for f in findings]
        self.assertIn("needs-improvement-performance", types)

    def test_slow_lcp(self):
        metrics = {
            "performance_score": 95,
            "lab_data": {"LCP": {"value": 5000, "display": "5.0 s"}},
        }
        findings = _assess_performance("https://example.com/", metrics)
        types = [f["finding_type"] for f in findings]
        self.assertIn("slow-lcp", types)

    def test_high_cls(self):
        metrics = {
            "performance_score": 95,
            "lab_data": {"CLS": {"value": 0.3, "display": "0.3"}},
        }
        findings = _assess_performance("https://example.com/", metrics)
        types = [f["finding_type"] for f in findings]
        self.assertIn("high-cls", types)

    def test_high_tbt(self):
        metrics = {
            "performance_score": 95,
            "lab_data": {"TBT": {"value": 800, "display": "800 ms"}},
        }
        findings = _assess_performance("https://example.com/", metrics)
        types = [f["finding_type"] for f in findings]
        self.assertIn("high-tbt", types)


class TestAnalyzePerformance(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.db.ensure_schema()
        self.mgr = AuditManager(self.db)

    def tearDown(self):
        self.db.close()

    @patch("searchops.analyzers.pagespeed._fetch_psi")
    def test_good_score(self, mock_fetch):
        mock_fetch.return_value = _make_psi_response(score=0.95)
        result = analyze_performance("https://example.com/", audit_manager=self.mgr)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["performance_score"], 95)
        # Good score = no findings = no audit
        self.assertIsNone(result["audit_id"])

    @patch("searchops.analyzers.pagespeed._fetch_psi")
    def test_poor_score_creates_audit(self, mock_fetch):
        mock_fetch.return_value = _make_psi_response(score=0.3)
        result = analyze_performance("https://example.com/", audit_manager=self.mgr)
        self.assertIsNotNone(result["audit_id"])
        self.assertGreater(result["findings_count"], 0)
        audit = self.mgr.get_audit(result["audit_id"])
        self.assertEqual(audit["status"], "completed")

    @patch("searchops.analyzers.pagespeed._fetch_psi")
    def test_api_error(self, mock_fetch):
        from urllib.error import URLError
        mock_fetch.side_effect = URLError("timeout")
        result = analyze_performance("https://example.com/")
        self.assertEqual(result["status"], "fetch_error")

    @patch("searchops.analyzers.pagespeed._fetch_psi")
    def test_strategy_passed(self, mock_fetch):
        mock_fetch.return_value = _make_psi_response()
        analyze_performance("https://example.com/", strategy="desktop")
        mock_fetch.assert_called_with("https://example.com/", strategy="desktop", api_key=None)

    @patch("searchops.analyzers.pagespeed._fetch_psi")
    def test_no_audit_manager(self, mock_fetch):
        mock_fetch.return_value = _make_psi_response(score=0.3)
        result = analyze_performance("https://example.com/", audit_manager=None)
        self.assertIsNone(result["audit_id"])
        self.assertGreater(result["findings_count"], 0)


if __name__ == "__main__":
    unittest.main()
