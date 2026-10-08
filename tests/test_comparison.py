# SPDX-License-Identifier: MIT

"""Tests for the audit comparison analyzer."""

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from searchops.db import DatabaseManager
from searchops.audit import AuditManager
from searchops.analyzers.comparison import _finding_key, compare_audits


class TestFindingKey(unittest.TestCase):
    def test_basic_key(self):
        f = {"finding_type": "missing-title", "url": "https://example.com/page"}
        self.assertEqual(_finding_key(f), "missing-title::https://example.com/page")

    def test_no_url(self):
        f = {"finding_type": "robots-blocks-all"}
        self.assertEqual(_finding_key(f), "robots-blocks-all::")

    def test_different_type_different_key(self):
        f1 = {"finding_type": "missing-title", "url": "/page"}
        f2 = {"finding_type": "missing-h1", "url": "/page"}
        self.assertNotEqual(_finding_key(f1), _finding_key(f2))


class TestCompareAudits(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.db.ensure_schema()
        self.mgr = AuditManager(self.db)

    def tearDown(self):
        self.db.close()

    def test_no_changes(self):
        baseline = self.mgr.create_audit("test", "https://example.com/")
        self.mgr.add_finding(baseline, "missing-title", "HIGH", "Missing title", url="/page1")
        self.mgr.complete_audit(baseline)

        current = self.mgr.create_audit("test", "https://example.com/")
        self.mgr.add_finding(current, "missing-title", "HIGH", "Missing title", url="/page1")
        self.mgr.complete_audit(current)

        result = compare_audits(self.mgr, baseline, current)
        self.assertEqual(result["summary"]["new_count"], 0)
        self.assertEqual(result["summary"]["resolved_count"], 0)
        self.assertEqual(result["summary"]["persistent_count"], 1)

    def test_new_finding(self):
        baseline = self.mgr.create_audit("test", "https://example.com/")
        self.mgr.complete_audit(baseline)

        current = self.mgr.create_audit("test", "https://example.com/")
        self.mgr.add_finding(current, "missing-title", "HIGH", "Missing title", url="/page1")
        self.mgr.complete_audit(current)

        result = compare_audits(self.mgr, baseline, current)
        self.assertEqual(result["summary"]["new_count"], 1)
        self.assertEqual(result["summary"]["resolved_count"], 0)
        self.assertEqual(result["new_findings"][0]["finding_type"], "missing-title")

    def test_resolved_finding(self):
        baseline = self.mgr.create_audit("test", "https://example.com/")
        self.mgr.add_finding(baseline, "missing-title", "HIGH", "Missing title", url="/page1")
        self.mgr.complete_audit(baseline)

        current = self.mgr.create_audit("test", "https://example.com/")
        self.mgr.complete_audit(current)

        result = compare_audits(self.mgr, baseline, current)
        self.assertEqual(result["summary"]["new_count"], 0)
        self.assertEqual(result["summary"]["resolved_count"], 1)
        self.assertEqual(result["resolved_findings"][0]["finding_type"], "missing-title")

    def test_severity_change(self):
        baseline = self.mgr.create_audit("test", "https://example.com/")
        self.mgr.add_finding(baseline, "thin-content", "MEDIUM", "Thin content", url="/page1")
        self.mgr.complete_audit(baseline)

        current = self.mgr.create_audit("test", "https://example.com/")
        self.mgr.add_finding(current, "thin-content", "HIGH", "Thin content", url="/page1")
        self.mgr.complete_audit(current)

        result = compare_audits(self.mgr, baseline, current)
        self.assertEqual(result["summary"]["persistent_count"], 1)
        persistent = result["persistent_findings"][0]
        self.assertIn("severity_changed", persistent)
        self.assertEqual(persistent["severity_changed"]["from"], "MEDIUM")
        self.assertEqual(persistent["severity_changed"]["to"], "HIGH")

    def test_mixed_changes(self):
        baseline = self.mgr.create_audit("test", "https://example.com/")
        self.mgr.add_finding(baseline, "missing-title", "HIGH", "Title", url="/page1")
        self.mgr.add_finding(baseline, "missing-h1", "MEDIUM", "H1", url="/page2")
        self.mgr.add_finding(baseline, "thin-content", "MEDIUM", "Thin", url="/page3")
        self.mgr.complete_audit(baseline)

        current = self.mgr.create_audit("test", "https://example.com/")
        self.mgr.add_finding(current, "missing-title", "HIGH", "Title", url="/page1")  # persistent
        self.mgr.add_finding(current, "missing-meta-description", "MEDIUM", "Meta", url="/page4")  # new
        # missing-h1 and thin-content resolved
        self.mgr.complete_audit(current)

        result = compare_audits(self.mgr, baseline, current)
        self.assertEqual(result["summary"]["new_count"], 1)
        self.assertEqual(result["summary"]["resolved_count"], 2)
        self.assertEqual(result["summary"]["persistent_count"], 1)

    def test_invalid_baseline(self):
        current = self.mgr.create_audit("test", "https://example.com/")
        self.mgr.complete_audit(current)
        result = compare_audits(self.mgr, "nonexistent", current)
        self.assertIn("error", result)

    def test_invalid_current(self):
        baseline = self.mgr.create_audit("test", "https://example.com/")
        self.mgr.complete_audit(baseline)
        result = compare_audits(self.mgr, baseline, "nonexistent")
        self.assertIn("error", result)

    def test_both_empty(self):
        baseline = self.mgr.create_audit("test", "https://example.com/")
        self.mgr.complete_audit(baseline)
        current = self.mgr.create_audit("test", "https://example.com/")
        self.mgr.complete_audit(current)

        result = compare_audits(self.mgr, baseline, current)
        self.assertEqual(result["summary"]["new_count"], 0)
        self.assertEqual(result["summary"]["resolved_count"], 0)
        self.assertEqual(result["summary"]["persistent_count"], 0)

    def test_severity_breakdown(self):
        baseline = self.mgr.create_audit("test", "https://example.com/")
        self.mgr.complete_audit(baseline)

        current = self.mgr.create_audit("test", "https://example.com/")
        self.mgr.add_finding(current, "missing-title", "HIGH", "T1", url="/p1")
        self.mgr.add_finding(current, "missing-h1", "MEDIUM", "T2", url="/p2")
        self.mgr.add_finding(current, "thin-content", "HIGH", "T3", url="/p3")
        self.mgr.complete_audit(current)

        result = compare_audits(self.mgr, baseline, current)
        self.assertEqual(result["new_by_severity"]["HIGH"], 2)
        self.assertEqual(result["new_by_severity"]["MEDIUM"], 1)

    def test_audit_type_included(self):
        baseline = self.mgr.create_audit("search-opportunities", "https://example.com/")
        self.mgr.complete_audit(baseline)
        current = self.mgr.create_audit("search-opportunities", "https://example.com/")
        self.mgr.complete_audit(current)

        result = compare_audits(self.mgr, baseline, current)
        self.assertEqual(result["baseline_audit_type"], "search-opportunities")
        self.assertEqual(result["current_audit_type"], "search-opportunities")


if __name__ == "__main__":
    unittest.main()
