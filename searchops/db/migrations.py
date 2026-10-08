# SPDX-License-Identifier: MIT

"""Forward-only schema migration engine.

Each migration is a dict entry ``{version: [sql_statements]}``.  Migrations
run inside a transaction and the version is bumped atomically after all
statements succeed.  Downgrades are not supported.
"""

from __future__ import annotations

import sqlite3

from searchops.db import schema


# ------------------------------------------------------------------
# Migration registry — append new versions, never modify old ones.
# ------------------------------------------------------------------
MIGRATIONS: dict[int, list[str]] = {
    1: [
        schema.CREATE_SCHEMA_VERSION,
        schema.CREATE_AUDITS,
        schema.CREATE_AUDIT_FINDINGS,
        schema.IDX_FINDINGS_AUDIT,
        schema.IDX_FINDINGS_SEVERITY,
        schema.CREATE_SNAPSHOTS,
        schema.CREATE_CRAWL_PAGES,
        schema.IDX_CRAWL_PAGES_AUDIT,
        schema.IDX_CRAWL_PAGES_URL,
        schema.CREATE_CRAWL_LINKS,
        schema.IDX_CRAWL_LINKS_AUDIT,
        schema.IDX_CRAWL_LINKS_SOURCE,
        schema.IDX_CRAWL_LINKS_TARGET,
    ],
}

LATEST_VERSION = max(MIGRATIONS)


def get_current_version(conn: sqlite3.Connection) -> int:
    """Return the current schema version (0 if uninitialized)."""
    try:
        row = conn.execute(
            "SELECT MAX(version) FROM schema_version"
        ).fetchone()
        return row[0] if row and row[0] is not None else 0
    except sqlite3.OperationalError:
        # schema_version table doesn't exist yet
        return 0


def apply_migrations(
    conn: sqlite3.Connection,
    target_version: int | None = None,
) -> int:
    """Apply all pending migrations up to *target_version* (default: latest).

    Returns the schema version after migrations.
    """
    if target_version is None:
        target_version = LATEST_VERSION

    current = get_current_version(conn)

    for version in sorted(MIGRATIONS):
        if version <= current or version > target_version:
            continue
        statements = MIGRATIONS[version]
        # Run all statements for this version in a transaction
        with conn:
            for sql in statements:
                conn.execute(sql)
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (version,),
            )

    return get_current_version(conn)
