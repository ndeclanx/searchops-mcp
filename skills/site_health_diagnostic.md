title: Site Health Diagnostic (Hermes)
description: Comprehensive site health audit combining crawl analysis, indexing checks, performance metrics, and search opportunity detection.

# Site Health Diagnostic — Hermes

**When to use:** Run this diagnostic when you need a full picture of a site's SEO health. It combines multiple analysis passes to identify technical issues, content gaps, indexing problems, and performance bottlenecks in a single workflow.

**Prerequisites:**
- GSC property configured (`GSC_SITE_URL` or pass `site_url` to each tool)
- Tools available: `analyze_robots_txt`, `parse_sitemap`, `crawl_site`, `audit_indexing`, `find_search_opportunities`, `detect_traffic_decay_tool`, `detect_cannibalization_tool`, `analyze_performance`

**How to execute:**

## Phase 1: Crawl Infrastructure

1. Call `analyze_robots_txt()` to check for robots.txt issues (blocked paths, missing sitemap references, syntax errors).
2. If the robots.txt lists sitemap URLs, call `parse_sitemap(sitemap_url=<url>)` for each one. Check for domain mismatches, missing lastmod dates, and URL count violations.
3. Call `crawl_site(max_pages=50, max_depth=3)` to crawl the site. This discovers orphan pages, missing titles, thin content, and broken links.

## Phase 2: Indexing Intelligence

4. Using the `audit_id` from step 3, call `audit_indexing(crawl_audit_id=<audit_id>, batch_size=20)` to check which crawled pages are actually indexed by Google. This identifies noindex pages, robots-blocked pages, canonical mismatches, and crawl errors.

## Phase 3: Search Performance

5. Call `find_search_opportunities()` to detect low-CTR queries, near-page-one opportunities, and citation opportunities.
6. Call `detect_traffic_decay_tool()` to compare recent traffic against the prior period and flag declining queries.
7. Call `detect_cannibalization_tool()` to find queries where multiple pages compete for the same ranking.

## Phase 4: Page Performance

8. Pick the top 3-5 most important pages (homepage, top traffic pages from step 5) and call `analyze_performance(url=<page_url>)` for each. Flag pages with poor Lighthouse scores, slow LCP, or high CLS.

## Phase 5: Synthesis

9. Use `get_audit_summary()` and `get_audit_issues(severity="HIGH")` for each audit created above to compile a severity-ranked issue list.
10. If a previous diagnostic exists, call `compare_audits(baseline_audit_id=<old>, current_audit_id=<new>)` to track progress.

**Interpreting results:**
- **CRITICAL findings** (e.g., robots.txt blocks all crawlers) need immediate action.
- **HIGH findings** (e.g., pages not indexed, poor performance scores) are the next priority.
- **MEDIUM findings** (e.g., missing meta descriptions, near-page-one queries) are optimization opportunities.
- **LOW/INFO findings** are nice-to-have improvements.

**Typical output structure:**
- Crawl health: X pages crawled, Y issues found
- Index coverage: X% of pages indexed, Y indexing issues
- Search opportunities: X low-CTR queries, Y near-page-one queries
- Traffic trends: X declining queries, Y cannibalized queries
- Performance: Average Lighthouse score, Core Web Vitals status
