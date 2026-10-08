# CLAUDE.md — Development Rules for SearchOps MCP

This repository is an evolution of the existing `surendranb/google-search-console-mcp`. Do not rebuild it from scratch.

## Mandatory Rules

1. Read `IMPLEMENTATION_STATUS.md` before development work.
2. Confirm the current Git branch before modifying code.
3. Work only on the approved milestone.
4. Never implement multiple milestones without explicit approval.
5. Never start the next phase automatically.
6. Never create the next development branch unless the repository owner explicitly requests it.
7. At each milestone boundary, recommend the next branch and wait for confirmation.
8. Do not add Claude, Anthropic, AI attribution, Co-Authored-By trailers, or generated-by trailers to commits or PRs.
9. Preserve stable upstream functionality unless the approved task explicitly modifies it.
10. Avoid full-repository scans when targeted context is sufficient.
11. Keep MCP public tools limited and high-level.
12. No internal LLM dependency.
13. Perform deterministic aggregation and diagnostics in code.
14. Summary responses are the default.
15. Raw data is opt-in.
16. Large responses require pagination or progressive disclosure.
17. Protect GSC URL Inspection quota.
18. Cache external calls where safe.
19. New functionality requires tests.
20. Avoid unrelated refactors.
21. Update `IMPLEMENTATION_STATUS.md` after every milestone.
22. Use ADRs in `docs/adr/` for durable architecture decisions.
23. Stop after the approved milestone is complete.
24. Telemetry is disabled by default (opt-in via `GSC_MCP_TELEMETRY=true`).

## Session Protocol

1. Check current branch
2. Read `IMPLEMENTATION_STATUS.md`
3. Confirm the assigned phase/milestone
4. Read only relevant PRD sections
5. Read relevant architecture/ADR files
6. Inspect affected source files and tests
7. Implement only the assigned scope
8. Add/update tests
9. Run focused tests, then regression tests
10. Update documentation if required
11. Update `IMPLEMENTATION_STATUS.md`
12. Provide completion report
13. STOP — request creation of next branch

## Testing

```bash
# Run all tests
python -m pytest -v

# Run unit tests only (skip E2E)
python -m pytest -v -m "not e2e"

# Run E2E tests only
python -m pytest -v -m e2e
```

## Project Structure

- `gsc_mcp_server.py` — Main MCP server (monolithic, to be modularized in M1)
- `gsc_telemetry.py` — Anonymous usage telemetry (opt-in)
- `gsc_setup_flow.py` — Interactive setup recovery via MCP elicitation
- `skills/` — SEO diagnostic playbooks
- `tests/` — Unit and E2E tests
- `docs/` — Documentation and ADRs

## Environment Variables

Required:
- `GOOGLE_APPLICATION_CREDENTIALS` — Path to Google service account JSON key
- `GSC_SITE_URL` — Search Console property URL

Optional:
- `GSC_MCP_TELEMETRY=true` — Enable anonymous usage telemetry
- `DO_NOT_TRACK=1` — Disable telemetry (overrides opt-in)
