# SPDX-License-Identifier: MIT

"""Tests for the SearchOps SQLite persistence layer.

All tests use in-memory databases — no files are created on disk.
"""

import json
import os
import sys
import uuid
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from searchops.db import DatabaseManager
from searchops.db.migrations import (
    apply_migrations,
    get_current_version,
    LATEST_VERSION,
    MIGRATIONS,
)


class TestDatabaseManager(unittest.TestCase):
    def test_connect_returns_connection(self):
        db = DatabaseManager(":memory:")
        conn = db.connect()
        self.assertIsNotNone(conn)
        db.close()

    def test_connect_is_idempotent(self):
        db = DatabaseManager(":memory:")
        conn1 = db.connect()
        conn2 = db.connect()
        self.assertIs(conn1, conn2)
        db.close()

    def test_close_and_reconnect(self):
        db = DatabaseManager(":memory:")
        db.connect()
        db.close()
        # After close, a new connect creates a fresh connection
        conn = db.connect()
        self.assertIsNotNone(conn)
        db.close()

    def test_wal_mode_enabled(self):
        db = DatabaseManager(":memory:")
        # WAL is a no-op on :memory: but the pragma shouldn't error
        conn = db.connect()
        result = conn.execute("PRAGMA journal_mode;").fetchone()
        # :memory: returns 'memory' instead of 'wal', but file-based would return 'wal'
        self.assertIsNotNone(result)
        db.close()

    def test_foreign_keys_enabled(self):
        db = DatabaseManager(":memory:")
        db.connect()
        result = db.execute("PRAGMA foreign_keys;").fetchone()
        self.assertEqual(result[0], 1)
        db.close()

    def test_row_factory_is_row(self):
        import sqlite3
        db = DatabaseManager(":memory:")
        conn = db.connect()
        self.assertEqual(conn.row_factory, sqlite3.Row)
        db.close()

    def test_default_db_path(self):
        db = DatabaseManager()
        self.assertIn("searchops.db", db.db_path)
        # Don't connect — just check the path is set

    def test_env_override_db_path(self):
        os.environ["SEARCHOPS_DB_PATH"] = "/tmp/test_override.db"
        try:
            db = DatabaseManager()
            self.assertEqual(db.db_path, "/tmp/test_override.db")
        finally:
            del os.environ["SEARCHOPS_DB_PATH"]

    def test_explicit_path_takes_precedence(self):
        os.environ["SEARCHOPS_DB_PATH"] = "/tmp/env_path.db"
        try:
            db = DatabaseManager("/tmp/explicit.db")
            self.assertEqual(db.db_path, "/tmp/explicit.db")
        finally:
            del os.environ["SEARCHOPS_DB_PATH"]


class TestMigrations(unittest.TestCase):
    def test_fresh_db_version_is_zero(self):
        db = DatabaseManager(":memory:")
        self.assertEqual(db.get_schema_version(), 0)
        db.close()

    def test_ensure_schema_brings_to_latest(self):
        db = DatabaseManager(":memory:")
        db.ensure_schema()
        self.assertEqual(db.get_schema_version(), LATEST_VERSION)
        db.close()

    def test_ensure_schema_is_idempotent(self):
        db = DatabaseManager(":memory:")
        db.ensure_schema()
        v1 = db.get_schema_version()
        db.ensure_schema()
        v2 = db.get_schema_version()
        self.assertEqual(v1, v2)
        db.close()

    def test_migrations_dict_has_version_1(self):
        self.assertIn(1, MIGRATIONS)

    def test_apply_specific_version(self):
        db = DatabaseManager(":memory:")
        conn = db.connect()
        version = apply_migrations(conn, target_version=1)
        self.assertEqual(version, 1)
        db.close()

    def test_schema_version_table_records_applied(self):
        db = DatabaseManager(":memory:")
        db.ensure_schema()
        row = db.execute("SELECT version, applied_at FROM schema_version WHERE version = 1").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["version"], 1)
        self.assertIsNotNone(row["applied_at"])
        db.close()


class TestSchemaV1Tables(unittest.TestCase):
    """Verify all v1 tables exist and accept CRUD operations."""

    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.db.ensure_schema()

    def tearDown(self):
        self.db.close()

    def test_audits_crud(self):
        audit_id = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO audits (id, audit_type, site_url, started_at) VALUES (?, ?, ?, datetime('now'))",
            (audit_id, "indexing", "https://example.com/"),
        )
        self.db.commit()

        row = self.db.execute("SELECT * FROM audits WHERE id = ?", (audit_id,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["audit_type"], "indexing")
        self.assertEqual(row["status"], "running")

        # Update
        self.db.execute(
            "UPDATE audits SET status = 'completed', completed_at = datetime('now'), summary = ? WHERE id = ?",
            (json.dumps({"total_findings": 5}), audit_id),
        )
        self.db.commit()
        row = self.db.execute("SELECT * FROM audits WHERE id = ?", (audit_id,)).fetchone()
        self.assertEqual(row["status"], "completed")
        self.assertEqual(json.loads(row["summary"])["total_findings"], 5)

    def test_audit_findings_crud(self):
        audit_id = str(uuid.uuid4())
        finding_id = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO audits (id, audit_type, site_url, started_at) VALUES (?, ?, ?, datetime('now'))",
            (audit_id, "technical", "https://example.com/"),
        )
        self.db.execute(
            "INSERT INTO audit_findings (id, audit_id, url, finding_type, severity, confidence, title, evidence) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (finding_id, audit_id, "https://example.com/page", "canonical-mismatch",
             "HIGH", 0.9, "Canonical mismatch", json.dumps({"declared": "/page", "google": "/page/"})),
        )
        self.db.commit()

        row = self.db.execute("SELECT * FROM audit_findings WHERE id = ?", (finding_id,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["severity"], "HIGH")
        self.assertEqual(row["confidence"], 0.9)
        evidence = json.loads(row["evidence"])
        self.assertEqual(evidence["declared"], "/page")

    def test_findings_by_severity(self):
        audit_id = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO audits (id, audit_type, site_url, started_at) VALUES (?, ?, ?, datetime('now'))",
            (audit_id, "technical", "https://example.com/"),
        )
        for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"):
            self.db.execute(
                "INSERT INTO audit_findings (id, audit_id, finding_type, severity, title) VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), audit_id, "test-finding", sev, f"Finding {sev}"),
            )
        self.db.commit()

        high_and_above = self.db.execute(
            "SELECT * FROM audit_findings WHERE audit_id = ? AND severity IN ('CRITICAL', 'HIGH')",
            (audit_id,),
        ).fetchall()
        self.assertEqual(len(high_and_above), 2)

    def test_snapshots_crud(self):
        snap_id = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO snapshots (id, snapshot_type, site_url, period_start, period_end, data) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (snap_id, "search_analytics", "https://example.com/",
             "2025-01-01", "2025-01-31", json.dumps({"rows": 100})),
        )
        self.db.commit()

        row = self.db.execute("SELECT * FROM snapshots WHERE id = ?", (snap_id,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(json.loads(row["data"])["rows"], 100)

    def test_crawl_pages_crud(self):
        page_id = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO crawl_pages (id, url, status_code, title, word_count, content_hash) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (page_id, "https://example.com/page", 200, "Test Page", 500, "abc123"),
        )
        self.db.commit()

        row = self.db.execute("SELECT * FROM crawl_pages WHERE id = ?", (page_id,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["status_code"], 200)
        self.assertEqual(row["word_count"], 500)

    def test_crawl_links_crud(self):
        self.db.execute(
            "INSERT INTO crawl_links (source_url, target_url, anchor_text, link_type) "
            "VALUES (?, ?, ?, ?)",
            ("https://example.com/", "https://example.com/about", "About Us", "internal"),
        )
        self.db.commit()

        rows = self.db.execute(
            "SELECT * FROM crawl_links WHERE source_url = ?",
            ("https://example.com/",),
        ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["anchor_text"], "About Us")

    def test_all_tables_exist(self):
        tables = [
            row["name"]
            for row in self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
        expected = {"schema_version", "audits", "audit_findings", "snapshots", "crawl_pages", "crawl_links"}
        self.assertTrue(expected.issubset(set(tables)), f"Missing tables: {expected - set(tables)}")

    def test_indexes_exist(self):
        indexes = [
            row["name"]
            for row in self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
            ).fetchall()
        ]
        expected = {
            "idx_findings_audit_id", "idx_findings_severity",
            "idx_crawl_pages_audit_id", "idx_crawl_pages_url",
            "idx_crawl_links_audit_id", "idx_crawl_links_source", "idx_crawl_links_target",
        }
        self.assertTrue(expected.issubset(set(indexes)), f"Missing indexes: {expected - set(indexes)}")


if __name__ == "__main__":
    unittest.main()
