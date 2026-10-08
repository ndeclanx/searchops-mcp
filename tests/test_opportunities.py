# SPDX-License-Identifier: MIT

"""Tests for the search opportunity analyzer and MCP tool.

All tests use in-memory SQLite databases and mock GSC providers.
"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from searchops.db import DatabaseManager
from searchops.audit import AuditManager
from searchops.analyzers.opportunities import (
    _normalize_row,
    _classify_row,
    find_opportunities,
    DEFAULT_THRESHOLDS,
)


# ------------------------------------------------------------------
# Helper: build a raw GSC API row
# ------------------------------------------------------------------
def _make_row(query, page, clicks, impressions, ctr, position):
    """Build a raw GSC API row dict (ctr as decimal 0.0-1.0)."""
    return {
        "keys": [query, page],
        "clicks": clicks,
        "impressions": impressions,
        "ctr": ctr,
        "position": position,
    }


class TestNormalizeRow(unittest.TestCase):
    def test_ctr_conversion(self):
        row = _make_row("test", "https://example.com/", 5, 100, 0.015, 3.2)
        norm = _normalize_row(row)
        self.assertEqual(norm["ctr_pct"], 1.5)
        self.assertEqual(norm["position"], 3.2)
        self.assertEqual(norm["query"], "test")
        self.assertEqual(norm["page"], "https://example.com/")

    def test_zero_ctr(self):
        row = _make_row("test", "https://example.com/", 0, 200, 0.0, 1.0)
        norm = _normalize_row(row)
        self.assertEqual(norm["ctr_pct"], 0.0)

    def test_missing_keys(self):
        row = {"keys": [], "clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}
        norm = _normalize_row(row)
        self.assertEqual(norm["query"], "")
        self.assertEqual(norm["page"], "")


class TestClassifyRow(unittest.TestCase):
    def setUp(self):
        self.thresholds = dict(DEFAULT_THRESHOLDS)

    def test_low_ctr_match(self):
        row = {"position": 5.0, "ctr_pct": 0.5, "impressions": 100}
        types = _classify_row(row, self.thresholds)
        self.assertIn("low-ctr", types)

    def test_low_ctr_no_match_high_ctr(self):
        row = {"position": 5.0, "ctr_pct": 5.0, "impressions": 100}
        types = _classify_row(row, self.thresholds)
        self.assertNotIn("low-ctr", types)

    def test_low_ctr_no_match_low_impressions(self):
        row = {"position": 5.0, "ctr_pct": 0.5, "impressions": 5}
        types = _classify_row(row, self.thresholds)
        self.assertNotIn("low-ctr", types)

    def test_low_ctr_no_match_bad_position(self):
        row = {"position": 15.0, "ctr_pct": 0.5, "impressions": 100}
        types = _classify_row(row, self.thresholds)
        self.assertNotIn("low-ctr", types)

    def test_near_page_one_match(self):
        row = {"position": 12.0, "ctr_pct": 1.0, "impressions": 50}
        types = _classify_row(row, self.thresholds)
        self.assertIn("near-page-one", types)

    def test_near_page_one_no_match_too_high(self):
        row = {"position": 25.0, "ctr_pct": 1.0, "impressions": 50}
        types = _classify_row(row, self.thresholds)
        self.assertNotIn("near-page-one", types)

    def test_near_page_one_no_match_too_low(self):
        row = {"position": 3.0, "ctr_pct": 1.0, "impressions": 50}
        types = _classify_row(row, self.thresholds)
        self.assertNotIn("near-page-one", types)

    def test_citation_match(self):
        row = {"position": 1.2, "ctr_pct": 0.3, "impressions": 100}
        types = _classify_row(row, self.thresholds)
        self.assertIn("citation-opportunity", types)

    def test_citation_no_match_position_too_high(self):
        row = {"position": 3.0, "ctr_pct": 0.3, "impressions": 100}
        types = _classify_row(row, self.thresholds)
        self.assertNotIn("citation-opportunity", types)

    def test_citation_no_match_ctr_too_high(self):
        row = {"position": 1.2, "ctr_pct": 5.0, "impressions": 100}
        types = _classify_row(row, self.thresholds)
        self.assertNotIn("citation-opportunity", types)

    def test_no_match(self):
        row = {"position": 1.0, "ctr_pct": 15.0, "impressions": 1000}
        types = _classify_row(row, self.thresholds)
        self.assertEqual(types, [])

    def test_multiple_types(self):
        # Position 1.2, CTR 0.3%, 100 impressions → low-ctr AND citation
        row = {"position": 1.2, "ctr_pct": 0.3, "impressions": 100}
        types = _classify_row(row, self.thresholds)
        self.assertIn("low-ctr", types)
        self.assertIn("citation-opportunity", types)


class TestFindOpportunities(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.db.ensure_schema()
        self.mgr = AuditManager(self.db)
        self.mock_provider = MagicMock()

    def tearDown(self):
        self.db.close()

    def test_no_data_returns_empty(self):
        self.mock_provider.search_analytics.return_value = {"rows": []}
        result = find_opportunities(
            self.mock_provider, self.mgr, "https://example.com/",
            "2025-01-01", "2025-01-31",
        )
        self.assertEqual(result["total_opportunities"], 0)
        self.assertIsNone(result["audit_id"])

    def test_no_rows_key_returns_empty(self):
        self.mock_provider.search_analytics.return_value = {}
        result = find_opportunities(
            self.mock_provider, self.mgr, "https://example.com/",
            "2025-01-01", "2025-01-31",
        )
        self.assertEqual(result["total_opportunities"], 0)

    def test_low_ctr_findings_persisted(self):
        self.mock_provider.search_analytics.return_value = {
            "rows": [_make_row("test query", "https://example.com/page", 1, 200, 0.005, 3.2)]
        }
        result = find_opportunities(
            self.mock_provider, self.mgr, "https://example.com/",
            "2025-01-01", "2025-01-31",
        )
        self.assertGreater(result["total_opportunities"], 0)
        self.assertIn("low-ctr", result["opportunities"])

        findings = self.mgr.get_findings(result["audit_id"])
        low_ctr = [f for f in findings if f["finding_type"] == "low-ctr"]
        self.assertEqual(len(low_ctr), 1)
        evidence = json.loads(low_ctr[0]["evidence"])
        self.assertEqual(evidence["ctr_pct"], 0.5)
        self.assertEqual(evidence["query"], "test query")

    def test_near_page_one_findings(self):
        self.mock_provider.search_analytics.return_value = {
            "rows": [_make_row("near query", "https://example.com/page", 2, 50, 0.04, 12.5)]
        }
        result = find_opportunities(
            self.mock_provider, self.mgr, "https://example.com/",
            "2025-01-01", "2025-01-31",
        )
        self.assertIn("near-page-one", result["opportunities"])

    def test_citation_findings(self):
        self.mock_provider.search_analytics.return_value = {
            "rows": [_make_row("citation q", "https://example.com/page", 0, 500, 0.002, 1.1)]
        }
        result = find_opportunities(
            self.mock_provider, self.mgr, "https://example.com/",
            "2025-01-01", "2025-01-31",
        )
        self.assertIn("citation-opportunity", result["opportunities"])

    def test_audit_completed(self):
        self.mock_provider.search_analytics.return_value = {
            "rows": [_make_row("test", "https://example.com/", 1, 100, 0.01, 5.0)]
        }
        result = find_opportunities(
            self.mock_provider, self.mgr, "https://example.com/",
            "2025-01-01", "2025-01-31",
        )
        audit = self.mgr.get_audit(result["audit_id"])
        self.assertEqual(audit["status"], "completed")

    def test_rows_analyzed_count(self):
        self.mock_provider.search_analytics.return_value = {
            "rows": [
                _make_row("q1", "https://example.com/a", 10, 100, 0.1, 2.0),
                _make_row("q2", "https://example.com/b", 5, 50, 0.1, 3.0),
                _make_row("q3", "https://example.com/c", 1, 200, 0.005, 8.0),
            ]
        }
        result = find_opportunities(
            self.mock_provider, self.mgr, "https://example.com/",
            "2025-01-01", "2025-01-31",
        )
        self.assertEqual(result["rows_analyzed"], 3)

    def test_custom_thresholds(self):
        # With default threshold (2%), this row's CTR 3% would NOT match low-ctr.
        # With threshold=5%, it SHOULD match.
        self.mock_provider.search_analytics.return_value = {
            "rows": [_make_row("test", "https://example.com/", 3, 100, 0.03, 5.0)]
        }
        result = find_opportunities(
            self.mock_provider, self.mgr, "https://example.com/",
            "2025-01-01", "2025-01-31",
            low_ctr_threshold=5.0,
        )
        self.assertIn("low-ctr", result["opportunities"])

    def test_api_error_propagates(self):
        self.mock_provider.search_analytics.side_effect = RuntimeError("API down")
        with self.assertRaises(RuntimeError):
            find_opportunities(
                self.mock_provider, self.mgr, "https://example.com/",
                "2025-01-01", "2025-01-31",
            )

    def test_request_body_dimensions(self):
        self.mock_provider.search_analytics.return_value = {"rows": []}
        find_opportunities(
            self.mock_provider, self.mgr, "https://example.com/",
            "2025-01-01", "2025-01-31",
        )
        call_args = self.mock_provider.search_analytics.call_args
        body = call_args[0][1]  # positional: (site_url, body)
        self.assertEqual(body["dimensions"], ["query", "page"])
        self.assertEqual(body["searchType"], "web")

    def test_multiple_opportunity_types_same_row(self):
        # Position 1.2, CTR 0.3% (0.003), 100 impressions → both low-ctr and citation
        self.mock_provider.search_analytics.return_value = {
            "rows": [_make_row("multi", "https://example.com/", 0, 100, 0.003, 1.2)]
        }
        result = find_opportunities(
            self.mock_provider, self.mgr, "https://example.com/",
            "2025-01-01", "2025-01-31",
        )
        self.assertIn("low-ctr", result["opportunities"])
        self.assertIn("citation-opportunity", result["opportunities"])
        # Total should be 2 (one finding per type)
        self.assertEqual(result["total_opportunities"], 2)


class TestFindSearchOpportunitiesTool(unittest.TestCase):
    """Test the MCP tool function directly.

    The async tool uses anyio.to_thread.run_sync, which creates a new thread.
    SQLite connections can't cross threads by default, so we create the DB
    with check_same_thread=False for these integration tests.
    """

    def setUp(self):
        import sqlite3
        # Create a thread-safe in-memory DB for async tool tests
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON;")
        self.db = DatabaseManager(":memory:")
        self.db._conn = conn
        self.db.ensure_schema()
        self.mock_provider = MagicMock()
        self.mock_provider.search_analytics.return_value = {
            "rows": [_make_row("test", "https://example.com/page", 1, 200, 0.005, 3.2)]
        }

        # Patch the tool's dependencies
        import searchops.tools.opportunities as tools_mod
        self._orig_gsc_provider = tools_mod.gsc_provider
        self._orig_get_db = tools_mod.get_db
        tools_mod.gsc_provider = self.mock_provider
        tools_mod.get_db = lambda: self.db

        import searchops.errors as err_mod
        self._orig_init_error = err_mod.SERVER_INIT_ERROR
        err_mod.SERVER_INIT_ERROR = None

        self._orig_gsc_site_url = err_mod.GSC_SITE_URL
        err_mod.GSC_SITE_URL = "https://example.com/"

    def tearDown(self):
        import searchops.tools.opportunities as tools_mod
        tools_mod.gsc_provider = self._orig_gsc_provider
        tools_mod.get_db = self._orig_get_db

        import searchops.errors as err_mod
        err_mod.SERVER_INIT_ERROR = self._orig_init_error
        err_mod.GSC_SITE_URL = self._orig_gsc_site_url

        self.db.close()

    def test_tool_returns_summary(self):
        from searchops.tools.opportunities import find_search_opportunities
        import asyncio
        result = asyncio.new_event_loop().run_until_complete(
            find_search_opportunities.__wrapped__(
                site_url="https://example.com/",
                start_date="2025-01-01",
                end_date="2025-01-31",
            )
        )
        self.assertIn("total_opportunities", result)
        self.assertGreater(result["total_opportunities"], 0)

    def test_tool_no_site_url_error(self):
        import searchops.errors as err_mod
        err_mod.GSC_SITE_URL = None
        from searchops.tools.opportunities import find_search_opportunities
        import asyncio
        result = asyncio.new_event_loop().run_until_complete(
            find_search_opportunities.__wrapped__(
                start_date="2025-01-01",
                end_date="2025-01-31",
            )
        )
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
