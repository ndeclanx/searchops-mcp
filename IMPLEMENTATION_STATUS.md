# Implementation Status — SearchOps MCP

## Current Phase
**Phase 0 — Fork Stabilization** (COMPLETE)

## Current Milestone
**Milestone 0: Fork Stabilization** (`chore/fork-stabilization`) — COMPLETE

## Completed Milestones
- **M0: Fork Stabilization** (`chore/fork-stabilization`)

## Pending Milestones
- M1: Extract Modular Package Structure (`refactor/modular-package`)
- M2: GSC Provider Abstraction (`refactor/gsc-provider`)
- M3: Implement `inspect_url` Tool (`feat/inspect-url`)
- M4: SQLite Database Layer (`feat/sqlite-persistence`)
- M5: Audit Framework and Query Tools (`feat/audit-framework`)
- M6: CTR Opportunities and Near-Page-One (`feat/search-opportunities`)
- M7: Traffic Decay Detection (`feat/traffic-decay`)
- M8: Cannibalization Detection (`feat/cannibalization`)
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

## Known Technical Debt
- `gsc_mcp_server.py` is a ~1,370-line monolith (to be addressed in M1).
- `inspect_url` tool is not implemented (to be addressed in M3). References removed from docs in M0.
- Circular import: `gsc_setup_flow.py` imports `gsc_mcp_server as server`.

## Current Test Status
- **Post-M0:** 24 passed, 2 failed (pre-existing Windows E2E failures, unchanged from baseline)
- Unit tests: 18 passed (search analytics: 6, setup flow: 7, updates: 5)
- E2E tests: 6 passed, 2 failed (Windows `Path.home()` doesn't use `HOME` env var — `test_telemetry_events_flow`, `test_first_run_disclosure`)

## Current Public MCP Tools
1. `get_search_analytics` — Query search metrics
2. `list_sites` / `list_gsc_sites` — List properties
3. `get_sitemaps` / `list_sitemaps` — List sitemaps
4. `submit_sitemap` — Submit sitemap
5. `delete_sitemap` — Delete sitemap
6. `list_available_dimensions` — Schema discovery
7. `list_available_metrics` — Schema discovery
8. `skills_list` — List playbooks
9. `skill_read` — Load playbook
10. `setup_gsc_access` — Interactive setup
11. `check_for_updates` — Version check

## Next Recommended Milestone
M1: Extract Modular Package Structure (`refactor/modular-package`)
