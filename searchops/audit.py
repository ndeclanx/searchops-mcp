# SPDX-License-Identifier: MIT

"""Audit lifecycle manager.

``AuditManager`` wraps the ``audits`` and ``audit_findings`` tables created
by the v1 migration.  Downstream analyzers (M6-M8, M11) call
``create_audit`` / ``add_finding`` / ``complete_audit`` to persist results;
the MCP query tools in ``searchops.tools.audit`` read them back.
"""

from __future__ import annotations

import json
import uuid
from enum import Enum

from searchops.db import DatabaseManager


# ------------------------------------------------------------------
# Severity enum & ordering
# ------------------------------------------------------------------
class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


SEVERITY_ORDER: dict[str, int] = {
    "CRITICAL": 0,
    "HIGH": 1,
    "MEDIUM": 2,
    "LOW": 3,
    "INFO": 4,
}


def _severity_at_or_above(min_severity: str) -> list[str]:
    """Return all severity values at or above *min_severity*."""
    threshold = SEVERITY_ORDER.get(min_severity.upper(), 4)
    return [s for s, rank in SEVERITY_ORDER.items() if rank <= threshold]


# ------------------------------------------------------------------
# AuditManager
# ------------------------------------------------------------------
class AuditManager:
    """Create, populate, and query audits stored in SQLite."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    # ---- write operations ------------------------------------------------

    def create_audit(
        self,
        audit_type: str,
        site_url: str,
        metadata: dict | None = None,
    ) -> str:
        """Create a new audit row.  Returns the generated audit ID."""
        audit_id = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO audits (id, audit_type, site_url, started_at, metadata) "
            "VALUES (?, ?, ?, datetime('now'), ?)",
            (audit_id, audit_type, site_url, json.dumps(metadata) if metadata else None),
        )
        self.db.commit()
        return audit_id

    def add_finding(
        self,
        audit_id: str,
        finding_type: str,
        severity: str,
        title: str,
        url: str | None = None,
        description: str | None = None,
        evidence: dict | None = None,
        confidence: float = 0.6,
    ) -> str:
        """Add a finding to *audit_id*.  Returns the finding ID."""
        finding_id = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO audit_findings "
            "(id, audit_id, url, finding_type, severity, confidence, title, description, evidence) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                finding_id,
                audit_id,
                url,
                finding_type,
                severity.upper(),
                confidence,
                title,
                description,
                json.dumps(evidence) if evidence else None,
            ),
        )
        self.db.commit()
        return finding_id

    def complete_audit(self, audit_id: str, summary: dict | None = None) -> None:
        """Mark *audit_id* as completed."""
        self.db.execute(
            "UPDATE audits SET status = 'completed', completed_at = datetime('now'), "
            "summary = ? WHERE id = ?",
            (json.dumps(summary) if summary else None, audit_id),
        )
        self.db.commit()

    def fail_audit(self, audit_id: str, error: str) -> None:
        """Mark *audit_id* as failed."""
        self.db.execute(
            "UPDATE audits SET status = 'failed', completed_at = datetime('now'), "
            "summary = ? WHERE id = ?",
            (json.dumps({"error": error}), audit_id),
        )
        self.db.commit()

    # ---- read operations -------------------------------------------------

    def get_audit(self, audit_id: str) -> dict | None:
        """Return a single audit as a dict, or ``None``."""
        row = self.db.execute("SELECT * FROM audits WHERE id = ?", (audit_id,)).fetchone()
        return dict(row) if row else None

    def get_latest_audit(
        self,
        audit_type: str | None = None,
        site_url: str | None = None,
    ) -> dict | None:
        """Return the most recent audit, optionally filtered."""
        sql = "SELECT * FROM audits"
        params: list[str] = []
        clauses: list[str] = []
        if audit_type:
            clauses.append("audit_type = ?")
            params.append(audit_type)
        if site_url:
            clauses.append("site_url = ?")
            params.append(site_url)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY started_at DESC, rowid DESC LIMIT 1"
        row = self.db.execute(sql, tuple(params)).fetchone()
        return dict(row) if row else None

    def get_findings(
        self,
        audit_id: str,
        severity: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Return findings for *audit_id* with optional severity filter and pagination."""
        sql = "SELECT * FROM audit_findings WHERE audit_id = ?"
        params: list[object] = [audit_id]
        if severity:
            allowed = _severity_at_or_above(severity)
            placeholders = ", ".join("?" for _ in allowed)
            sql += f" AND severity IN ({placeholders})"
            params.extend(allowed)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self.db.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]

    def count_findings(self, audit_id: str, severity: str | None = None) -> int:
        """Count findings for *audit_id* with optional severity filter."""
        sql = "SELECT COUNT(*) FROM audit_findings WHERE audit_id = ?"
        params: list[object] = [audit_id]
        if severity:
            allowed = _severity_at_or_above(severity)
            placeholders = ", ".join("?" for _ in allowed)
            sql += f" AND severity IN ({placeholders})"
            params.extend(allowed)
        row = self.db.execute(sql, tuple(params)).fetchone()
        return row[0]

    def get_finding(self, finding_id: str) -> dict | None:
        """Return a single finding as a dict, or ``None``."""
        row = self.db.execute(
            "SELECT * FROM audit_findings WHERE id = ?", (finding_id,)
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        if result.get("evidence"):
            result["evidence"] = json.loads(result["evidence"])
        return result

    def get_audit_summary(self, audit_id: str) -> dict:
        """Compute severity counts and return an audit summary dict."""
        audit = self.get_audit(audit_id)
        if audit is None:
            return {"error": f"Audit {audit_id} not found."}

        rows = self.db.execute(
            "SELECT severity, COUNT(*) as cnt FROM audit_findings "
            "WHERE audit_id = ? GROUP BY severity",
            (audit_id,),
        ).fetchall()
        by_severity = {r["severity"]: r["cnt"] for r in rows}
        total = sum(by_severity.values())

        return {
            "audit_id": audit["id"],
            "audit_type": audit["audit_type"],
            "site_url": audit["site_url"],
            "status": audit["status"],
            "started_at": audit["started_at"],
            "completed_at": audit["completed_at"],
            "findings_by_severity": by_severity,
            "total_findings": total,
        }
