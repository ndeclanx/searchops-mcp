# SPDX-License-Identifier: MIT

"""SQL table definitions for SearchOps persistence.

All DDL is declared as constants so migrations.py can reference them.
JSON blobs use TEXT columns (sqlite3 doesn't have a native JSON type,
but ``json_extract()`` works on TEXT).
"""

# ------------------------------------------------------------------
# Migration tracking
# ------------------------------------------------------------------
CREATE_SCHEMA_VERSION = """\
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

# ------------------------------------------------------------------
# Audit runs
# ------------------------------------------------------------------
CREATE_AUDITS = """\
CREATE TABLE audits (
    id              TEXT PRIMARY KEY,
    audit_type      TEXT NOT NULL,
    site_url        TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    completed_at    TEXT,
    status          TEXT NOT NULL DEFAULT 'running',
    summary         TEXT,
    metadata        TEXT
);
"""

# ------------------------------------------------------------------
# Findings within an audit
# ------------------------------------------------------------------
CREATE_AUDIT_FINDINGS = """\
CREATE TABLE audit_findings (
    id              TEXT PRIMARY KEY,
    audit_id        TEXT NOT NULL REFERENCES audits(id),
    url             TEXT,
    finding_type    TEXT NOT NULL,
    severity        TEXT NOT NULL,
    confidence      REAL NOT NULL DEFAULT 0.6,
    title           TEXT NOT NULL,
    description     TEXT,
    evidence        TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

IDX_FINDINGS_AUDIT = "CREATE INDEX idx_findings_audit_id ON audit_findings(audit_id);"
IDX_FINDINGS_SEVERITY = "CREATE INDEX idx_findings_severity ON audit_findings(severity);"

# ------------------------------------------------------------------
# GSC data snapshots
# ------------------------------------------------------------------
CREATE_SNAPSHOTS = """\
CREATE TABLE snapshots (
    id              TEXT PRIMARY KEY,
    audit_id        TEXT REFERENCES audits(id),
    snapshot_type   TEXT NOT NULL,
    site_url        TEXT NOT NULL,
    period_start    TEXT,
    period_end      TEXT,
    data            TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# ------------------------------------------------------------------
# Crawl pages (used by M10)
# ------------------------------------------------------------------
CREATE_CRAWL_PAGES = """\
CREATE TABLE crawl_pages (
    id                  TEXT PRIMARY KEY,
    audit_id            TEXT REFERENCES audits(id),
    url                 TEXT NOT NULL,
    status_code         INTEGER,
    content_type        TEXT,
    title               TEXT,
    meta_description    TEXT,
    canonical           TEXT,
    h1                  TEXT,
    word_count          INTEGER,
    content_hash        TEXT,
    crawled_at          TEXT NOT NULL DEFAULT (datetime('now')),
    response_time_ms    INTEGER,
    metadata            TEXT
);
"""

IDX_CRAWL_PAGES_AUDIT = "CREATE INDEX idx_crawl_pages_audit_id ON crawl_pages(audit_id);"
IDX_CRAWL_PAGES_URL = "CREATE INDEX idx_crawl_pages_url ON crawl_pages(url);"

# ------------------------------------------------------------------
# Internal links discovered during crawl
# ------------------------------------------------------------------
CREATE_CRAWL_LINKS = """\
CREATE TABLE crawl_links (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_id        TEXT REFERENCES audits(id),
    source_url      TEXT NOT NULL,
    target_url      TEXT NOT NULL,
    anchor_text     TEXT,
    link_type       TEXT DEFAULT 'internal',
    is_followed     INTEGER DEFAULT 1
);
"""

IDX_CRAWL_LINKS_AUDIT = "CREATE INDEX idx_crawl_links_audit_id ON crawl_links(audit_id);"
IDX_CRAWL_LINKS_SOURCE = "CREATE INDEX idx_crawl_links_source ON crawl_links(source_url);"
IDX_CRAWL_LINKS_TARGET = "CREATE INDEX idx_crawl_links_target ON crawl_links(target_url);"
