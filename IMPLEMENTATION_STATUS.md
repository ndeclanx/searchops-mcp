# Implementation Status — SearchOps MCP

## Current Phase
**Phase 4 — Analysis Tools** (IN PROGRESS)

## Current Milestone
**Milestone 8: Cannibalization Detection** (`feat/cannibalization`) — COMPLETE

## Completed Milestones
- **M0: Fork Stabilization** (`chore/fork-stabilization`)
- **M1: Extract Modular Package Structure** (`refactor/modular-package`)
- **M2: GSC Provider Abstraction** (`refactor/gsc-provider`)
- **M3: Implement `inspect_url` Tool** (`feat/inspect-url`)
- **M4: SQLite Database Layer** (`feat/sqlite-persistence`)
- **M5: Audit Framework and Query Tools** (`feat/audit-framework`)
- **M6: CTR Opportunities and Near-Page-One** (`feat/search-opportunities`)
- **M7: Traffic Decay Detection** (`feat/traffic-decay`)
- **M8: Cannibalization Detection** (`feat/cannibalization`)

## Pending Milestones
- M9: Crawl Parsers (`feat/crawl-parsers`)
- M10: Site Crawler (`feat/site-crawler`)
- M11: Indexing Intelligence (`feat/indexing-intelligence`)
- M12: Historical Comparison (`feat/audit-comparison`)
- M13: PageSpeed Integration (`feat/pagespeed`)
- M14: Verification Tool (`feat/verification`)
- M15: SearchOps Hermes Skill (`feat/searchops-skill`)
- M16: n8n Webhook Integration (`feat/n8n-automation`)

## Blocked Work
None.

## Important Decisions
- Telemetry flipped to opt-in (disabled by default) per PRD requirement.
- Phantom tool references (`inspect_url`, `list_sitemaps`) cleaned up in docs; `list_sitemaps` added as alias for `get_sitemaps`.
- Pre-existing E2E test failures on Windows (`test_telemetry_events_flow`, `test_first_run_disclosure`) documented as baseline — these fail before any changes due to Windows-specific telemetry timing issues.
- M1: `gsc_mcp_server.py` converted to a `_ShimModule` subclass (not a plain module) to support `__setattr__` propagation. PEP 562 only added module-level `__getattr__`; test monkeypatching requires `__setattr__` on the type. This is a well-established pattern (used by `lazy_loader`, `importlib.util`, etc.).
- M2: All GSC API calls now go through `GSCProvider` class in `searchops/providers/gsc.py`. Tools no longer call `auth.get_gsc_service()` directly.
- M3: `inspect_url` uses in-memory quota limiter (default 2,000/day, configurable via `SEARCHOPS_INSPECT_QUOTA_DAILY`). Resets at midnight server time; does not persist across restarts.
- M4: SQLite database at `~/.searchops/searchops.db` (override with `SEARCHOPS_DB_PATH`). WAL mode, forward-only migrations, lazy initialization (DB file not created until first tool that needs it).
- M5: `AuditManager` in `searchops/audit.py` manages audit lifecycle (create → add findings → complete/fail). Severity filtering returns findings at or above a threshold (e.g. `severity="HIGH"` returns CRITICAL + HIGH). Three read-only MCP tools for querying (`get_audit_summary`, `get_audit_issues`, `get_issue`).
- M6: `find_search_opportunities` analyzes GSC data and classifies queries into three opportunity types: low-CTR (position < 10, CTR < 2%), near-page-one (position 5-20), citation opportunities (position ≤ 1.5, CTR < 1%). Thresholds are configurable. Analysis logic in `searchops/analyzers/opportunities.py`, MCP tool wrapper in `searchops/tools/opportunities.py`.
- M7: `detect_traffic_decay_tool` compares two periods of GSC data to find impressions drops (≥20%), position losses (≥2.0), and CTR declines (≥20% relative). Configurable thresholds. Handles disappeared queries as full impressions loss.
- M8: `detect_cannibalization_tool` finds queries ranking on 2+ pages from the same site. Groups by query, identifies best page by CTR, flags CTR spread. Severity scales with page count and spread.

## Known Technical Debt
- `gsc_setup_flow.py` still imports `gsc_mcp_server as server` (preserved via shim for backward compatibility).

## Current Test Status
- **Post-M7:** 139 unit tests passed, 2 E2E failed (pre-existing Windows baseline)
- Unit tests: 139 passed (search analytics: 6, setup flow: 7, updates: 5, imports: 12, provider: 14, inspect_url: 7, database: 23, audit: 25, opportunities: 28, traffic_decay: 13)
- E2E tests: 6 passed, 2 failed (Windows `Path.home()` doesn't use `HOME` env var — `test_telemetry_events_flow`, `test_first_run_disclosure`)

## Current Public MCP Tools
1. `get_search_analytics` — Query search metrics
2. `list_sites` / `list_gsc_sites` — List properties
3. `get_sitemaps` / `list_sitemaps` — List sitemaps
4. `submit_sitemap` — Submit sitemap
5. `delete_sitemap` — Delete sitemap
6. `inspect_url` — URL Inspection API (index status, crawl info, rich results)
7. `list_available_dimensions` — Schema discovery
8. `list_available_metrics` — Schema discovery
9. `skills_list` — List playbooks
10. `skill_read` — Load playbook
11. `setup_gsc_access` — Interactive setup
12. `check_for_updates` — Version check
13. `get_audit_summary` — Audit summary with severity breakdown
14. `get_audit_issues` — Query audit findings with pagination
15. `get_issue` — Single finding with full evidence
16. `find_search_opportunities` — CTR/near-page-one/citation opportunity detection
17. `detect_traffic_decay_tool` — Period-over-period traffic decline detection
18. `detect_cannibalization_tool` — Multi-page keyword cannibalization detection

## Next Recommended Milestone
M9: Crawl Parsers (`feat/crawl-parsers`)
