# SPDX-License-Identifier: MIT

"""Audit comparison — diff two audits to track finding changes over time.

Compares findings between a baseline and a current audit to identify
new issues, resolved issues, and persistent (unchanged) issues.
"""

from __future__ import annotations

from searchops.audit import AuditManager


# ------------------------------------------------------------------
# Comparison logic
# ------------------------------------------------------------------
def _finding_key(finding: dict) -> str:
    """Generate a stable key for matching findings across audits.

    Uses finding_type + url as the identity. This means the same issue
    on the same URL will be matched even if the title/description changes.
    """
    ftype = finding.get("finding_type", "")
    url = finding.get("url", "") or ""
    return f"{ftype}::{url}"


def compare_audits(
    audit_manager: AuditManager,
    baseline_audit_id: str,
    current_audit_id: str,
) -> dict:
    """Compare findings between two audits.

    Parameters
    ----------
    audit_manager
        AuditManager for reading audit data.
    baseline_audit_id
        The older audit to use as baseline.
    current_audit_id
        The newer audit to compare against.

    Returns
    -------
    dict
        Comparison summary with new, resolved, persistent findings counts
        and detailed lists.
    """
    baseline_audit = audit_manager.get_audit(baseline_audit_id)
    current_audit = audit_manager.get_audit(current_audit_id)

    if not baseline_audit:
        return {"error": f"Baseline audit '{baseline_audit_id}' not found."}
    if not current_audit:
        return {"error": f"Current audit '{current_audit_id}' not found."}

    # Fetch all findings (no limit — comparison needs full picture)
    baseline_findings = audit_manager.get_findings(baseline_audit_id, limit=10000)
    current_findings = audit_manager.get_findings(current_audit_id, limit=10000)

    # Build lookup by key
    baseline_by_key: dict[str, dict] = {}
    for f in baseline_findings:
        key = _finding_key(f)
        baseline_by_key[key] = f

    current_by_key: dict[str, dict] = {}
    for f in current_findings:
        key = _finding_key(f)
        current_by_key[key] = f

    baseline_keys = set(baseline_by_key.keys())
    current_keys = set(current_by_key.keys())

    new_keys = current_keys - baseline_keys
    resolved_keys = baseline_keys - current_keys
    persistent_keys = baseline_keys & current_keys

    # Build detailed result lists
    new_findings = []
    for key in sorted(new_keys):
        f = current_by_key[key]
        new_findings.append({
            "finding_type": f.get("finding_type"),
            "severity": f.get("severity"),
            "title": f.get("title"),
            "url": f.get("url"),
        })

    resolved_findings = []
    for key in sorted(resolved_keys):
        f = baseline_by_key[key]
        resolved_findings.append({
            "finding_type": f.get("finding_type"),
            "severity": f.get("severity"),
            "title": f.get("title"),
            "url": f.get("url"),
        })

    persistent_findings = []
    for key in sorted(persistent_keys):
        baseline_f = baseline_by_key[key]
        current_f = current_by_key[key]
        entry = {
            "finding_type": current_f.get("finding_type"),
            "severity": current_f.get("severity"),
            "title": current_f.get("title"),
            "url": current_f.get("url"),
        }
        # Check if severity changed
        if baseline_f.get("severity") != current_f.get("severity"):
            entry["severity_changed"] = {
                "from": baseline_f.get("severity"),
                "to": current_f.get("severity"),
            }
        persistent_findings.append(entry)

    # Severity breakdown for new findings
    new_by_severity: dict[str, int] = {}
    for f in new_findings:
        sev = f.get("severity", "UNKNOWN")
        new_by_severity[sev] = new_by_severity.get(sev, 0) + 1

    resolved_by_severity: dict[str, int] = {}
    for f in resolved_findings:
        sev = f.get("severity", "UNKNOWN")
        resolved_by_severity[sev] = resolved_by_severity.get(sev, 0) + 1

    return {
        "baseline_audit_id": baseline_audit_id,
        "current_audit_id": current_audit_id,
        "baseline_audit_type": baseline_audit.get("audit_type"),
        "current_audit_type": current_audit.get("audit_type"),
        "summary": {
            "new_count": len(new_findings),
            "resolved_count": len(resolved_findings),
            "persistent_count": len(persistent_findings),
            "baseline_total": len(baseline_findings),
            "current_total": len(current_findings),
        },
        "new_by_severity": new_by_severity,
        "resolved_by_severity": resolved_by_severity,
        "new_findings": new_findings,
        "resolved_findings": resolved_findings,
        "persistent_findings": persistent_findings,
    }
