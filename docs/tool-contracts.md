# Tool Contracts — SearchOps MCP

## Current MCP Tools

### `get_search_analytics`
- **Type:** Read-only, idempotent, open-world
- **Parameters:** dimensions, start_date, end_date, filters, search_type, row_limit, start_row, summary_only, intent
- **Default mode:** summary (token-efficient)
- **Quota:** None (GSC Search Analytics has generous limits)

### `list_sites` / `list_gsc_sites`
- **Type:** Read-only, idempotent, open-world
- **Parameters:** None
- **Note:** Exempt from config-error intercept (allows setup detection)

### `get_sitemaps` / `list_sitemaps`
- **Type:** Read-only, idempotent, open-world
- **Parameters:** None

### `submit_sitemap`
- **Type:** Write (not destructive), idempotent, open-world
- **Parameters:** sitemap_url

### `delete_sitemap`
- **Type:** Write, destructive, idempotent, open-world
- **Parameters:** sitemap_url

### `list_available_dimensions`
- **Type:** Read-only, idempotent, local (no API call)
- **Parameters:** None

### `list_available_metrics`
- **Type:** Read-only, idempotent, local (no API call)
- **Parameters:** None

### `skills_list`
- **Type:** Read-only, idempotent, local
- **Parameters:** None
- **Note:** Exempt from config-error intercept

### `skill_read`
- **Type:** Read-only, idempotent, local
- **Parameters:** skill_id
- **Note:** Path traversal protection applied

### `setup_gsc_access`
- **Type:** Write (config), not destructive, idempotent, open-world
- **Parameters:** None (uses MCP elicitation)
- **Note:** Exempt from config-error intercept

### `check_for_updates`
- **Type:** Read-only, idempotent, local
- **Parameters:** None
- **Note:** Queries PyPI with 24h cache TTL

### `inspect_url`
- **Type:** Read-only, idempotent, open-world
- **Parameters:** url (required), site_url (optional, defaults to GSC_SITE_URL)
- **Quota:** 2,000 calls/day (in-memory, configurable via `SEARCHOPS_INSPECT_QUOTA_DAILY`)
- **Returns:** Index status verdict, coverage state, robots.txt state, indexing state, crawl info, canonical URLs, rich results, AMP status

### `get_audit_summary`
- **Type:** Read-only, idempotent, local (no API call)
- **Parameters:** audit_id (optional), audit_type (optional)
- **Returns:** Audit metadata + findings counts by severity
- **Note:** If audit_id omitted, uses the latest audit

### `get_audit_issues`
- **Type:** Read-only, idempotent, local (no API call)
- **Parameters:** audit_id (optional), severity (optional min filter), limit (default 20, max 100), offset
- **Returns:** Findings list + pagination metadata
- **Note:** severity="HIGH" returns CRITICAL + HIGH findings

### `get_issue`
- **Type:** Read-only, idempotent, local (no API call)
- **Parameters:** finding_id (required)
- **Returns:** Full finding dict with parsed evidence JSON

### `find_search_opportunities`
- **Type:** Read-only (GSC API), idempotent, open-world
- **Parameters:** site_url (optional), start_date, end_date, row_limit (default 5000), low_ctr_threshold (default 2.0%), near_page_one_max_position (default 20.0)
- **Returns:** Summary with audit_id, total_opportunities, per-type counts, rows_analyzed
- **Note:** Creates an audit with findings persisted in SQLite. Query results via `get_audit_issues`.
- **Opportunity types:** low-ctr (pos < 10, CTR < 2%), near-page-one (pos 5-20), citation-opportunity (pos ≤ 1.5, CTR < 1%)

## Future Tools (Planned)

| Tool | Milestone | Purpose |
|------|-----------|---------|
| `detect_traffic_decay` | M7 | Period-over-period decline detection |
| `detect_cannibalization` | M8 | Multi-page query overlap |
| `analyze_robots_txt` | M9 | Parse robots.txt |
| `parse_sitemap` | M9 | Parse XML sitemaps |
| `crawl_site` | M10 | Site crawling |
| `analyze_url` | M10 | Single-page analysis |
| `audit_indexing` | M11 | Full indexing audit |
| `compare_audits` | M12 | Audit-to-audit diff |
| `analyze_performance` | M13 | PageSpeed Insights |
| `verify_issue` | M14 | Issue fix verification |
