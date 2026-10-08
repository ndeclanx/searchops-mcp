# Architecture — SearchOps MCP

## Overview

SearchOps MCP is a Model Context Protocol (MCP) v2.0 server providing Google Search Console data to AI agents. It evolved from `surendranb/google-search-console-mcp`.

## Runtime Architecture

```
AI Agent (Claude, Cursor, etc.)
        │
        │ MCP 2.0 / stdio
        │
   ┌────▼────────────────────┐
   │   gsc_mcp_server.py     │
   │   (MCPServer + tools)   │
   │                         │
   │  ┌─ Tool Registration   │
   │  ├─ Error Briefs (S3)   │
   │  ├─ Instrumentation     │
   │  ├─ Prompts (S6)        │
   │  └─ Resources (S5)      │
   └────┬────────────────────┘
        │
   ┌────▼────────────────────┐
   │  Google Search Console  │
   │  API v1 / Webmasters    │
   └─────────────────────────┘
```

## Source Files

| File | Lines | Purpose |
|------|-------|---------|
| `gsc_mcp_server.py` | ~1,355 | Main MCP server — all tools, error handling, instrumentation, prompts, resources |
| `gsc_telemetry.py` | ~657 | Anonymous usage telemetry (opt-in, MCP Telemetry Standard v2) |
| `gsc_setup_flow.py` | ~258 | Interactive setup recovery via MCP elicitation (S7) |
| `skills/*.md` | 5 files | SEO diagnostic playbooks |

## Key Patterns

### Protocol Surfaces v1
- **S1 — Tool Annotations:** Every tool carries `read_only`, `destructive`, `idempotent`, `open_world` hints
- **S2 — Output Schema:** `get_search_analytics` declares `SearchAnalyticsResult` TypedDict
- **S3 — Error Briefs:** User-fixable failures get versioned, two-audience error text
- **S5 — Skills as Resources:** Playbooks registered as `skill://` MCP resources
- **S6 — Workflow Prompts:** 3 packaged analysis workflows
- **S7 — Setup Recovery:** Inline elicitation for born-broken config

### Instrumentation
The `@instrument` decorator wraps all tools with telemetry capture (latency, status, error category, rows returned).

### Error Handling
- Init-time validation of credentials and site URL
- S3 guided briefs for auth failures (versioned for measurement)
- Config errors block data tools; exempt: `setup_gsc_access`, `list_gsc_sites`, `skills_list`, `check_for_updates`

### Authentication
- Service account only (Google `Credentials` from JSON key file)
- Env vars: `GOOGLE_APPLICATION_CREDENTIALS`, `GSC_SITE_URL`

## Dependencies
- `mcp>=2.0.0,<3` — MCP SDK
- `google-api-python-client` — Google API client
- `google-auth`, `google-auth-oauthlib`, `google-auth-httplib2` — Auth

## Test Structure
- `tests/test_get_search_analytics.py` — Unit: dimension normalization, coercion, summary
- `tests/test_setup_flow.py` — Unit: setup recovery paths
- `tests/test_updates.py` — Unit: version checking
- `tests/e2e/test_e2e.py` — E2E: full server subprocess via MCP stdio

## Packaging
- **Python:** `google-search-console-mcp` on PyPI (hatchling build)
- **NPM:** `@surendranb/google-search-console-mcp` (Node.js wrapper spawning uvx)
- **Entry points:** `google-search-console-mcp`, `gsc-mcp`, `gsc-mcp-server`

## Future Architecture (Post-Modularization)

After M1, the monolithic server will be extracted into:

```
searchops/
├── __init__.py
├── server.py          # MCPServer + main()
├── auth.py            # Credentials
├── errors.py          # S3 briefs
├── instrument.py      # @instrument decorator
├── prompts.py         # S6 prompts
├── resources.py       # S5 resources
├── tools/
│   ├── gsc.py         # GSC tools
│   ├── schema.py      # Dimension/metric discovery
│   ├── skills.py      # Skill tools
│   └── updates.py     # Version check
├── providers/         # (M2) Data provider abstraction
├── db/                # (M4) SQLite persistence
├── crawl/             # (M9-M10) Website crawling
└── analyzers/         # (M6-M8) Deterministic analysis
```
