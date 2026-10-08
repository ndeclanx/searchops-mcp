# Implementation Status — SearchOps MCP

## Current Phase
**Phase 1 — Controlled Refactoring** (IN PROGRESS)

## Current Milestone
**Milestone 1: Extract Modular Package Structure** (`refactor/modular-package`) — COMPLETE

## Completed Milestones
- **M0: Fork Stabilization** (`chore/fork-stabilization`)
- **M1: Extract Modular Package Structure** (`refactor/modular-package`)

## Pending Milestones
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
- M1: `gsc_mcp_server.py` converted to a `_ShimModule` subclass (not a plain module) to support `__setattr__` propagation. PEP 562 only added module-level `__getattr__`; test monkeypatching requires `__setattr__` on the type. This is a well-established pattern (used by `lazy_loader`, `importlib.util`, etc.).
- M1: `searchops/tools/gsc.py` uses module-attribute access (`auth.get_gsc_service()`) rather than bound-name imports to ensure monkeypatching on the shim propagates to call sites.

## Known Technical Debt
- `inspect_url` tool is not implemented (to be addressed in M3). References removed from docs in M0.
- `gsc_setup_flow.py` still imports `gsc_mcp_server as server` (preserved via shim for backward compatibility).

## Current Test Status
- **Post-M1:** 34 passed, 2 failed (pre-existing Windows E2E failures, unchanged from M0 baseline)
- Unit tests: 28 passed (search analytics: 6, setup flow: 7, updates: 5, imports: 10)
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
M2: GSC Provider Abstraction (`refactor/gsc-provider`)
