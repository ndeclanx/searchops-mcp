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

## Future Tools (Planned)

| Tool | Milestone | Purpose |
|------|-----------|---------|
| `get_audit_summary` | M5 | Retrieve audit summary |
| `get_audit_issues` | M5 | Query audit findings with pagination |
| `get_issue` | M5 | Single issue with evidence |
| `find_search_opportunities` | M6 | CTR/near-page-one/rising queries |
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
