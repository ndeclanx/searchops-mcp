# Google Search Console (GSC) MCP Server 🔍

> **Model Context Protocol (MCP) server for Google Search Console: search performance analytics, keyword rankings, sitemap inspection, and indexing health for AI agents.**

[![CI](https://github.com/surendranb/google-search-console-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/surendranb/google-search-console-mcp/actions)
[![PyPI version](https://img.shields.io/pypi/v/google-search-console-mcp.svg?style=flat-square&color=blue)](https://pypi.org/project/google-search-console-mcp/)
[![npm version](https://img.shields.io/npm/v/@surendranb/google-search-console-mcp.svg?style=flat-square&color=red)](https://www.npmjs.com/package/@surendranb/google-search-console-mcp)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/surendranb/google-search-console-mcp/badge)](https://scorecard.dev/viewer/?site=github.com/surendranb/google-search-console-mcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)

🌐 **Live Documentation & Web Portal**: [https://gsc.builditwithai.xyz](https://gsc.builditwithai.xyz)

---

## ⚡ Quickstart

```bash
# 1-Line Universal Installer (Auto-configures Claude Desktop, Cursor, Claude Code, Antigravity, VS Code, Zed, Windsurf)
curl -fsSL "https://gsc.builditwithai.xyz/install" | bash

# Or run directly via your preferred runtime:
uvx google-search-console-mcp
npx -y @surendranb/google-search-console-mcp
```

---

---

## 🤖 Client Setup

### A. Claude Code (CLI)
```bash
claude mcp add google-search-console -- uvx google-search-console-mcp
```

### B. Cursor & Google Antigravity (`mcp.json`)
```json
{
  "mcpServers": {
    "google-search-console": {
      "command": "uvx",
      "args": ["google-search-console-mcp"]
    }
  }
}
```

### C. Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "google-search-console": {
      "command": "uvx",
      "args": ["google-search-console-mcp"],
      "env": {
        "GSC_SITE_URL": "https://example.com/",
        "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/service_account.json"
      }
    }
  }
}
```

### D. VS Code (Cline / Roo Code / Continue)
```json
{
  "mcpServers": {
    "google-search-console": {
      "command": "npx",
      "args": ["-y", "@surendranb/google-search-console-mcp"]
    }
  }
}
```

---

## 🛠️ Tools & Capabilities

| Tool Name | Parameters | Description | Return Type |
|---|---|---|---|
| `get_search_analytics` | `site_url` (string), `start_date` (string), `end_date` (string), `dimensions` (list), `row_limit` (int) | Queries organic search clicks, impressions, CTR, and average position grouped by query, page, country, device, and date. | `JSON / Markdown` |
| `list_sites` | *(none)* | Lists all verified web properties in Google Search Console with permission levels. | `JSON` |
| `get_sitemaps` / `list_sitemaps` | *(none)* | Retrieves all submitted XML sitemaps, last download date, and indexed URL counts. | `JSON` |
| `submit_sitemap` | `sitemap_url` (string) | Submits a new XML sitemap directly to Google Search Console. | `JSON` |
| `delete_sitemap` | `sitemap_url` (string) | Removes an obsolete or incorrect sitemap from Search Console. | `JSON` |
| `skill_read` | `skill_id` (string) | Loads expert SEO diagnostic playbooks. | `Markdown` |
| `skills_list` | *(none)* | Lists all available GSC analytical skills. | `JSON` |

---

## 🔒 Telemetry & Privacy

This package supports anonymous, non-PII diagnostic telemetry (command executions, latency, error codes). Telemetry is **disabled by default**.

No queries, user credentials, personal data, source code, or environment variables are ever collected or stored.

To opt in:
```bash
export GSC_MCP_TELEMETRY=true
```

To explicitly disable (overrides opt-in):
```bash
export DO_NOT_TRACK=1
```

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
