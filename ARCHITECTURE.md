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
   │   gsc_mcp_server.py     │  ← backward-compatible shim (_ShimModule)
   │   (delegates to searchops/) │
   └────┬────────────────────┘
        │
   ┌────▼────────────────────┐
   │   searchops/            │
   │  ┌─ server.py (MCPServer)│
   │  ├─ tools/gsc.py        │
   │  ├─ tools/schema.py     │
   │  ├─ tools/skills.py     │
   │  ├─ tools/updates.py    │
   │  ├─ instrument.py       │
   │  ├─ errors.py (S3)      │
   │  ├─ auth.py             │
   │  ├─ prompts.py (S6)     │
   │  └─ resources.py (S5)   │
   └────┬────────────────────┘
        │
   ┌────▼────────────────────┐
   │  Google Search Console  │
   │  API v1 / Webmasters    │
   └─────────────────────────┘
```

## Source Files

### searchops/ Package (Post-M1)

| File | Purpose |
|------|---------|
| `searchops/__init__.py` | Package root, `PACKAGE_ROOT` anchor for data files |
| `searchops/server.py` | MCPServer instantiation, annotations, instructions, `main()` |
| `searchops/errors.py` | S3 error briefs, config state, init checks, mutable config globals |
| `searchops/auth.py` | `get_gsc_service()`, `reinitialize()` |
| `searchops/instrument.py` | `@instrument` decorator, telemetry helpers, config-error intercept |
| `searchops/updates.py` | Fleet update checker (PyPI, 24h cache, 7d nudge throttle) |
| `searchops/prompts.py` | S6 workflow prompts (3 packaged analysis workflows) |
| `searchops/resources.py` | S5 skills mirrored as MCP resources |
| `searchops/tools/gsc.py` | GSC API tools (sites, sitemaps, search analytics) |
| `searchops/tools/schema.py` | Schema discovery (dimensions, metrics) |
| `searchops/tools/skills.py` | Skill/playbook tools |
| `searchops/tools/updates.py` | `check_for_updates` MCP tool |

### Legacy/Support Files

| File | Purpose |
|------|---------|
| `gsc_mcp_server.py` | Backward-compatible shim (`_ShimModule` subclass) — delegates to searchops/ |
| `gsc_telemetry.py` | Anonymous usage telemetry (opt-in, MCP Telemetry Standard v2) |
| `gsc_setup_flow.py` | Interactive setup recovery via MCP elicitation (S7) |
| `skills/*.md` | 5 SEO diagnostic playbooks |

## Key Patterns

### Protocol Surfaces v1
- **S1 — Tool Annotations:** Every tool carries `read_only`, `destructive`, `idempotent`, `open_world` hints
- **S2 — Output Schema:** `get_search_analytics` declares `SearchAnalyticsResult` TypedDict
- **S3 — Error Briefs:** User-fixable failures get versioned, two-audience error text
- **S5 — Skills as Resources:** Playbooks registered as `skill://` MCP resources
- **S6 — Workflow Prompts:** 3 packaged analysis workflows
- **S7 — Setup Recovery:** Inline elicitation for born-broken config

### Instrumentation
The `@instrument` decorator (`searchops/instrument.py`) wraps all tools with telemetry capture (latency, status, error category, rows returned).

### Error Handling
- Init-time validation of credentials and site URL (`searchops/errors.py`)
- S3 guided briefs for auth failures (versioned for measurement)
- Config errors block data tools; exempt: `setup_gsc_access`, `list_gsc_sites`, `skills_list`, `check_for_updates`

### Authentication
- Service account only (Google `Credentials` from JSON key file)
- Env vars: `GOOGLE_APPLICATION_CREDENTIALS`, `GSC_SITE_URL`

### Backward Compatibility (Shim)
- `gsc_mcp_server.py` is a `_ShimModule(types.ModuleType)` subclass
- `__getattr__` delegates reads to the canonical searchops submodule
- `__setattr__` propagates writes so test monkeypatching works
- `sys.modules["gsc_mcp_server"]` alias ensures `gsc_setup_flow.py` import works
- Entry points (`gsc-mcp`, etc.) still point to `gsc_mcp_server:main`

## Dependencies
- `mcp>=2.0.0,<3` — MCP SDK
- `google-api-python-client` — Google API client
- `google-auth`, `google-auth-oauthlib`, `google-auth-httplib2` — Auth

## Test Structure
- `tests/test_get_search_analytics.py` — Unit: dimension normalization, coercion, summary
- `tests/test_setup_flow.py` — Unit: setup recovery paths
- `tests/test_updates.py` — Unit: version checking
- `tests/test_imports.py` — Unit: import verification (both paths)
- `tests/e2e/test_e2e.py` — E2E: full server subprocess via MCP stdio

## Packaging
- **Python:** `google-search-console-mcp` on PyPI (hatchling build)
- **NPM:** `@surendranb/google-search-console-mcp` (Node.js wrapper spawning uvx)
- **Entry points:** `google-search-console-mcp`, `gsc-mcp`, `gsc-mcp-server`
- **Wheel includes:** `gsc_mcp_server.py`, `gsc_telemetry.py`, `gsc_setup_flow.py`, JSON files, `skills/`, `searchops/`

## Future Architecture (Post-Modularization)

```
searchops/
├── __init__.py
├── server.py          # MCPServer + main()
├── auth.py            # Credentials
├── errors.py          # S3 briefs
├── instrument.py      # @instrument decorator
├── updates.py         # Fleet update checker
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
