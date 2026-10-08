# SPDX-License-Identifier: MIT

"""SQLite persistence layer for SearchOps.

Provides a ``DatabaseManager`` that handles connection lifecycle, WAL mode,
and schema migrations.  Use ``get_db()`` to obtain the process-wide singleton
(lazy-initialized on first call so the DB file is not created at import time).
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from searchops.db.migrations import apply_migrations, get_current_version


def _default_db_path() -> str:
    """Return ``~/.searchops/searchops.db`` (or override via env)."""
    explicit = os.getenv("SEARCHOPS_DB_PATH")
    if explicit:
        return explicit
    return str(Path.home() / ".searchops" / "searchops.db")


class DatabaseManager:
    """SQLite database manager for SearchOps.

    Parameters
    ----------
    db_path
        Path to the SQLite database file.  ``":memory:"`` is supported for
        testing.  Defaults to ``~/.searchops/searchops.db`` (overridable via
        ``SEARCHOPS_DB_PATH``).
    """

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or _default_db_path()
        self._conn: sqlite3.Connection | None = None

    @property
    def db_path(self) -> str:
        return self._db_path

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------
    def connect(self) -> sqlite3.Connection:
        """Return the managed connection (lazy init)."""
        if self._conn is None:
            # Create parent directory for file-based DBs
            if self._db_path != ":memory:":
                Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

            self._conn = sqlite3.connect(self._db_path)
            self._conn.row_factory = sqlite3.Row
            # Enable WAL mode for concurrent reads (no-op on :memory:)
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA foreign_keys=ON;")
        return self._conn

    def close(self):
        """Close the managed connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # SQL helpers
    # ------------------------------------------------------------------
    def execute(self, sql: str, params=()) -> sqlite3.Cursor:
        """Execute SQL on the managed connection."""
        return self.connect().execute(sql, params)

    def executemany(self, sql: str, params_seq) -> sqlite3.Cursor:
        """Execute SQL for multiple parameter sets."""
        return self.connect().executemany(sql, params_seq)

    def commit(self):
        """Commit the current transaction."""
        self.connect().commit()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------
    def get_schema_version(self) -> int:
        """Return current schema version (0 if uninitialized)."""
        return get_current_version(self.connect())

    def ensure_schema(self):
        """Run any pending migrations to bring the DB to the latest version."""
        apply_migrations(self.connect())


# ------------------------------------------------------------------
# Process-wide singleton (lazy)
# ------------------------------------------------------------------
_db: DatabaseManager | None = None


def get_db() -> DatabaseManager:
    """Return the process-wide ``DatabaseManager`` singleton.

    The database file and schema are created on first call.
    """
    global _db
    if _db is None:
        _db = DatabaseManager()
        _db.ensure_schema()
    return _db
