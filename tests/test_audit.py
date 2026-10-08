# SPDX-License-Identifier: MIT

"""Tests for the audit framework — AuditManager and MCP query tools.

All tests use in-memory SQLite databases.
"""

import json
import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from searchops.db import DatabaseManager
from searchops.audit import AuditManager, Severity, SEVERITY_ORDER, _severity_at_or_above


class TestSeverity(unittest.TestCase):
    def test_enum_values(self):
        self.assertEqual(Severity.CRITICAL.value, "CRITICAL")
        self.assertEqual(Severity.INFO.value, "INFO")

    def test_severity_order_has_all_values(self):
        for s in Severity:
            self.assertIn(s.value, SEVERITY_ORDER)

    def test_severity_at_or_above_high(self):
        result = _severity_at_or_above("HIGH")
        self.assertIn("CRITICAL", result)
        self.assertIn("HIGH", result)
        self.assertNotIn("MEDIUM", result)
        self.assertNotIn("LOW", result)
        self.assertNotIn("INFO", result)

    def test_severity_at_or_above_info(self):
        result = _severity_at_or_above("INFO")
        self.assertEqual(len(result), 5)


class TestAuditManager(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.db.ensure_schema()
        self.mgr = AuditManager(self.db)

    def tearDown(self):
        self.db.close()

    def test_create_audit(self):
        audit_id = self.mgr.create_audit("indexing", "https://example.com/")
        self.assertIsNotNone(audit_id)
        audit = self.mgr.get_audit(audit_id)
        self.assertEqual(audit["audit_type"], "indexing")
        self.assertEqual(audit["site_url"], "https://example.com/")
        self.assertEqual(audit["status"], "running")

    def test_create_audit_with_metadata(self):
        meta = {"source": "test", "version": 1}
        audit_id = self.mgr.create_audit("technical", "https://example.com/", metadata=meta)
        audit = self.mgr.get_audit(audit_id)
        self.assertEqual(json.loads(audit["metadata"]), meta)

    def test_add_finding(self):
        audit_id = self.mgr.create_audit("technical", "https://example.com/")
        finding_id = self.mgr.add_finding(
            audit_id,
            finding_type="canonical-mismatch",
            severity="HIGH",
            title="Canonical mismatch",
            url="https://example.com/page",
            description="Declared canonical differs from Google's chosen URL",
            evidence={"declared": "/page", "google": "/page/"},
            confidence=0.9,
        )
        self.assertIsNotNone(finding_id)
        finding = self.mgr.get_finding(finding_id)
        self.assertEqual(finding["severity"], "HIGH")
        self.assertEqual(finding["confidence"], 0.9)
        self.assertEqual(finding["evidence"]["declared"], "/page")

    def test_complete_audit(self):
        audit_id = self.mgr.create_audit("indexing", "https://example.com/")
        summary = {"total_findings": 3}
        self.mgr.complete_audit(audit_id, summary=summary)
        audit = self.mgr.get_audit(audit_id)
        self.assertEqual(audit["status"], "completed")
        self.assertIsNotNone(audit["completed_at"])
        self.assertEqual(json.loads(audit["summary"]), summary)

    def test_fail_audit(self):
        audit_id = self.mgr.create_audit("indexing", "https://example.com/")
        self.mgr.fail_audit(audit_id, "API timeout")
        audit = self.mgr.get_audit(audit_id)
        self.assertEqual(audit["status"], "failed")
        self.assertEqual(json.loads(audit["summary"])["error"], "API timeout")

    def test_get_audit_not_found(self):
        self.assertIsNone(self.mgr.get_audit("nonexistent-id"))

    def test_get_latest_audit(self):
        self.mgr.create_audit("indexing", "https://a.com/")
        latest_id = self.mgr.create_audit("indexing", "https://b.com/")
        latest = self.mgr.get_latest_audit()
        self.assertEqual(latest["id"], latest_id)

    def test_get_latest_audit_filtered_by_type(self):
        self.mgr.create_audit("indexing", "https://example.com/")
        tech_id = self.mgr.create_audit("technical", "https://example.com/")
        latest = self.mgr.get_latest_audit(audit_type="technical")
        self.assertEqual(latest["id"], tech_id)

    def test_get_latest_audit_none(self):
        self.assertIsNone(self.mgr.get_latest_audit())

    def test_get_findings_pagination(self):
        audit_id = self.mgr.create_audit("technical", "https://example.com/")
        for i in range(10):
            self.mgr.add_finding(audit_id, "test-type", "MEDIUM", f"Finding {i}")
        page1 = self.mgr.get_findings(audit_id, limit=3, offset=0)
        page2 = self.mgr.get_findings(audit_id, limit=3, offset=3)
        self.assertEqual(len(page1), 3)
        self.assertEqual(len(page2), 3)
        # No overlap
        ids1 = {f["id"] for f in page1}
        ids2 = {f["id"] for f in page2}
        self.assertTrue(ids1.isdisjoint(ids2))

    def test_get_findings_severity_filter(self):
        audit_id = self.mgr.create_audit("technical", "https://example.com/")
        for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"):
            self.mgr.add_finding(audit_id, "test-type", sev, f"Finding {sev}")

        high_and_above = self.mgr.get_findings(audit_id, severity="HIGH")
        severities = {f["severity"] for f in high_and_above}
        self.assertEqual(severities, {"CRITICAL", "HIGH"})

    def test_count_findings(self):
        audit_id = self.mgr.create_audit("technical", "https://example.com/")
        for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"):
            self.mgr.add_finding(audit_id, "test-type", sev, f"Finding {sev}")
        self.assertEqual(self.mgr.count_findings(audit_id), 5)
        self.assertEqual(self.mgr.count_findings(audit_id, severity="HIGH"), 2)

    def test_get_finding_not_found(self):
        self.assertIsNone(self.mgr.get_finding("nonexistent-id"))

    def test_get_audit_summary_counts(self):
        audit_id = self.mgr.create_audit("technical", "https://example.com/")
        self.mgr.add_finding(audit_id, "a", "CRITICAL", "C1")
        self.mgr.add_finding(audit_id, "a", "CRITICAL", "C2")
        self.mgr.add_finding(audit_id, "a", "HIGH", "H1")
        self.mgr.add_finding(audit_id, "a", "LOW", "L1")
        summary = self.mgr.get_audit_summary(audit_id)
        self.assertEqual(summary["total_findings"], 4)
        self.assertEqual(summary["findings_by_severity"]["CRITICAL"], 2)
        self.assertEqual(summary["findings_by_severity"]["HIGH"], 1)
        self.assertEqual(summary["findings_by_severity"]["LOW"], 1)
        self.assertEqual(summary["audit_type"], "technical")

    def test_get_audit_summary_not_found(self):
        result = self.mgr.get_audit_summary("nonexistent-id")
        self.assertIn("error", result)


class TestAuditTools(unittest.TestCase):
    """Test the MCP tool functions directly (no server needed)."""

    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.db.ensure_schema()
        self.mgr = AuditManager(self.db)
        # Patch get_db to return our in-memory DB
        import searchops.tools.audit as tools_mod
        self._orig_get_manager = tools_mod._get_manager
        tools_mod._get_manager = lambda: self.mgr

    def tearDown(self):
        import searchops.tools.audit as tools_mod
        tools_mod._get_manager = self._orig_get_manager
        self.db.close()

    def test_get_audit_summary_tool(self):
        from searchops.tools.audit import get_audit_summary
        audit_id = self.mgr.create_audit("indexing", "https://example.com/")
        self.mgr.add_finding(audit_id, "test", "HIGH", "Title")
        # The tool function is the inner function (unwrapped by @instrument)
        result = get_audit_summary.__wrapped__(audit_id=audit_id)
        self.assertEqual(result["total_findings"], 1)
        self.assertEqual(result["audit_id"], audit_id)

    def test_get_audit_summary_tool_no_audit(self):
        from searchops.tools.audit import get_audit_summary
        result = get_audit_summary.__wrapped__()
        self.assertIn("error", result)

    def test_get_audit_issues_tool(self):
        from searchops.tools.audit import get_audit_issues
        audit_id = self.mgr.create_audit("indexing", "https://example.com/")
        for i in range(5):
            self.mgr.add_finding(audit_id, "test", "MEDIUM", f"Finding {i}")
        result = get_audit_issues.__wrapped__(audit_id=audit_id, limit=3)
        self.assertEqual(len(result["findings"]), 3)
        self.assertEqual(result["pagination"]["total"], 5)
        self.assertTrue(result["pagination"]["has_more"])

    def test_get_audit_issues_tool_severity_filter(self):
        from searchops.tools.audit import get_audit_issues
        audit_id = self.mgr.create_audit("indexing", "https://example.com/")
        self.mgr.add_finding(audit_id, "test", "CRITICAL", "C1")
        self.mgr.add_finding(audit_id, "test", "LOW", "L1")
        result = get_audit_issues.__wrapped__(audit_id=audit_id, severity="HIGH")
        self.assertEqual(result["pagination"]["total"], 1)
        self.assertEqual(result["findings"][0]["severity"], "CRITICAL")

    def test_get_issue_tool(self):
        from searchops.tools.audit import get_issue
        audit_id = self.mgr.create_audit("indexing", "https://example.com/")
        fid = self.mgr.add_finding(
            audit_id, "test", "HIGH", "Title",
            evidence={"key": "value"},
        )
        result = get_issue.__wrapped__(finding_id=fid)
        self.assertEqual(result["id"], fid)
        self.assertEqual(result["evidence"], {"key": "value"})

    def test_get_issue_tool_not_found(self):
        from searchops.tools.audit import get_issue
        result = get_issue.__wrapped__(finding_id="nonexistent")
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
