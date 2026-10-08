# SPDX-License-Identifier: MIT

"""S6: workflow prompts (Protocol Surfaces v1).

User-invokable packaged workflows (client UIs surface these).  Each teaches
the model the server's quirks: discover names first, read the skill, pass
intent.  Pull-only — no token cost until a user invokes one.
"""

from gsc_telemetry import send_telemetry
from searchops.server import mcp


def _prompt_used(prompt_name, has_args):
    try:
        send_telemetry("prompt_used", {"prompt_name": prompt_name, "has_args": bool(has_args)})
    except Exception:
        pass


@mcp.prompt(name="analyze-brand-visibility", title="Analyze brand visibility",
            description="How visible is a brand in Google Search? Branded vs non-branded share, CTR, positions.")
def analyze_brand_visibility(brand_terms: str = "") -> str:
    _prompt_used("analyze-brand-visibility", bool(brand_terms))
    terms = brand_terms.strip() or "(ask the user for their brand name plus common variants and misspellings)"
    return f"""Analyze brand visibility in Google Search using the Google Search Console tools.
Brand terms: {terms}

Work this way:
1. Call skill_read("brand_visibility.md") first and follow its playbook — it has the proven field combinations.
2. Call list_available_dimensions before querying; never guess dimension names.
3. Query get_search_analytics with dimensions=["query"] and a filter {{"dimension": "query", "operator": "contains", "expression": "<brand term>"}} — one call per brand variant. Always pass intent (e.g. intent="brand visibility analysis for <term>").
4. Run one unfiltered call for site totals, then compute branded vs non-branded share.
5. Report: branded share of clicks/impressions, branded CTR vs overall CTR, average position for exact brand queries (should be near 1 — higher means a problem), and any misspellings ranking poorly.

Quirks to respect: ctr in results is already a percentage; position is an average where LOWER is better; dates default to the last 30 days ending 3 days ago because GSC data lags about 3 days."""


@mcp.prompt(name="content-opportunities", title="Find content opportunities",
            description="Striking-distance queries, low-CTR pages, and content gaps worth acting on.")
def content_opportunities(focus_area: str = "") -> str:
    _prompt_used("content-opportunities", bool(focus_area))
    focus = f"Focus area: {focus_area.strip()}\n" if focus_area.strip() else ""
    return f"""Find concrete content opportunities from Google Search Console data.
{focus}
Work this way:
1. Call skill_read("citation_opportunities.md") and skill_read("intent_efficiency.md") — follow their playbooks.
2. Call list_available_dimensions first; then get_search_analytics with dimensions=["query", "page"] and a generous row_limit. Always pass intent="find content opportunities".
3. Striking distance: queries at position 5-20 with real impressions but few clicks — improving those pages moves them to page one.
4. CTR gaps: queries at position < 10 with CTR under ~1% — title/meta rewrites, not new content.
5. Content gaps: recurring queries with no dedicated page — new content candidates.
6. Check dimensions=["searchAppearance"] (see skill_read("search_appearance_audit.md")) for AI Overview and rich-result exposure worth auditing.

Quirks to respect: use summary_only=true for cheap totals before pulling rows; ctr is already a percentage; position is an average where lower is better."""


@mcp.prompt(name="diagnose-traffic-drop", title="Diagnose a traffic drop",
            description="Compare two periods and localize a search traffic drop: which segment, impressions vs CTR, likely cause.")
def diagnose_traffic_drop(drop_period: str = "") -> str:
    _prompt_used("diagnose-traffic-drop", bool(drop_period))
    period = drop_period.strip() or "(ask the user roughly when the drop started; default to comparing the last 14 days against the 14 days before)"
    return f"""Diagnose a Google Search traffic drop using the Search Console tools.
Drop period: {period}

Work this way:
1. Call list_available_dimensions first. Pass intent="diagnose traffic drop" on every get_search_analytics call.
2. Shape first: get_search_analytics with dimensions=["date"] across a window covering both the drop and the baseline — confirm when it actually started and whether clicks, impressions, or both fell.
3. Then two matched-length pulls (drop window vs prior window) segmented one dimension at a time: ["query"], ["page"], ["device"], ["country"], ["searchAppearance"].
4. Localize: is the loss concentrated in brand or non-brand queries, specific pages, one device, one country, or one search appearance type?
5. Distinguish the failure class: impressions fell at stable position = indexing/coverage issue; position fell = ranking loss; CTR fell at stable position = SERP feature change stealing clicks.
6. Check get_sitemaps for errors or warnings while you are at it.
7. Report the drop's shape, the losing segment, and the most likely cause class — with the numbers that support it.

Quirks to respect: GSC data lags about 3 days — never include the last 3 days in either window; ctr is already a percentage; position is an average where lower is better."""


@mcp.prompt(name="site-health-diagnostic", title="Run site health diagnostic",
            description="Comprehensive SEO health audit: crawl, indexing, performance, opportunities, and traffic trends.")
def site_health_diagnostic(site_url: str = "") -> str:
    _prompt_used("site-health-diagnostic", bool(site_url))
    site = f"Site: {site_url.strip()}\n" if site_url.strip() else ""
    return f"""Run a comprehensive site health diagnostic using all available SearchOps tools.
{site}
Work this way:
1. Call skill_read("site_health_diagnostic.md") first — it has the full Hermes diagnostic playbook with all phases.
2. **Phase 1 — Crawl Infrastructure:**
   a. Call analyze_robots_txt() to check for robots.txt issues.
   b. If sitemap URLs are found, call parse_sitemap() for each.
   c. Call crawl_site(max_pages=50) to discover page-level issues.
3. **Phase 2 — Indexing Intelligence:**
   a. Call audit_indexing(crawl_audit_id=<id from step 2c>) to check index coverage.
4. **Phase 3 — Search Performance:**
   a. Call find_search_opportunities() for CTR and near-page-one opportunities.
   b. Call detect_traffic_decay_tool() for declining queries.
   c. Call detect_cannibalization_tool() for keyword cannibalization.
5. **Phase 4 — Page Performance:**
   a. Call analyze_performance(url=<homepage>) for Core Web Vitals.
   b. Optionally test 2-3 other important pages.
6. **Phase 5 — Synthesis:**
   a. Use get_audit_issues(severity="HIGH") for each audit to compile a priority list.
   b. Report findings grouped by severity: CRITICAL > HIGH > MEDIUM > LOW.

Present a structured report with sections for each phase, issue counts by severity, and prioritized action items."""
