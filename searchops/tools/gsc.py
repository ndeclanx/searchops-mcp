# SPDX-License-Identifier: MIT

"""GSC API tools: sites, sitemaps, and search analytics."""

import json
import functools
from datetime import datetime, timedelta

import anyio.to_thread
from mcp.server.mcpserver import Context
from typing_extensions import TypedDict

from gsc_telemetry import request_supports_elicitation
from searchops import errors
from searchops import auth
from searchops.instrument import instrument, fire_skill_tip, _classify_result
from searchops.server import mcp, _ANNOTATIONS_READ_API, _ANNOTATIONS_WRITE_API, _ANNOTATIONS_DELETE_API


# ---------------------------------------------------------------------------
# S2: output schema for the primary data tool
# ---------------------------------------------------------------------------
class SearchAnalyticsResult(TypedDict, total=False):
    metadata: dict
    data: list[dict]
    summary: dict
    error: str


# ---------------------------------------------------------------------------
# Parameter coercion helpers
# ---------------------------------------------------------------------------
def _coerce_int(val, default: int, min_val: int | None = None, max_val: int | None = None) -> int:
    try:
        if val is None or val == "":
            res = default
        elif isinstance(val, (int, float)):
            res = int(val)
        else:
            res = int(float(str(val).strip().replace(",", "")))
    except (ValueError, TypeError):
        res = default
    if min_val is not None:
        res = max(min_val, res)
    if max_val is not None:
        res = min(max_val, res)
    return res


def _coerce_bool(val, default: bool = False) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    s = str(val).strip().lower()
    if s in ("true", "1", "yes", "y", "t"):
        return True
    if s in ("false", "0", "no", "n", "f"):
        return False
    return default


# ---------------------------------------------------------------------------
# Sites
# ---------------------------------------------------------------------------
@mcp.tool(annotations=_ANNOTATIONS_READ_API)
@instrument
def list_gsc_sites():
    """
    List all sites verified in Google Search Console.

    Returns:
        List of verified sites with their permission levels.
    """
    if errors.SERVER_INIT_ERROR:
        return f"Configuration Error: {errors.SERVER_INIT_ERROR}. Please instruct the user to fix their setup."
    try:
        service = auth.get_gsc_service()
        sites = service.sites().list().execute()

        result = []
        for site in sites.get('siteEntry', []):
            result.append({
                'siteUrl': site['siteUrl'],
                'permissionLevel': site['permissionLevel']
            })

        return result
    except Exception as e:
        brief = errors._api_error_text(e, "listing verified sites")
        if brief:
            return {"error": brief}
        return {"error": f"Error fetching sites: {str(e)}"}


@mcp.tool(annotations=_ANNOTATIONS_READ_API)
@instrument
def list_sites():
    """
    List all sites verified in Google Search Console (alias for list_gsc_sites).

    Returns:
        List of verified sites with their permission levels.
    """
    return list_gsc_sites()


# ---------------------------------------------------------------------------
# Sitemaps
# ---------------------------------------------------------------------------
@mcp.tool(annotations=_ANNOTATIONS_READ_API)
@instrument
def get_sitemaps():
    """
    Get all sitemaps for the configured site.

    Returns:
        List of sitemaps with their status and details.
    """
    try:
        service = auth.get_gsc_service()
        sitemaps = service.sitemaps().list(siteUrl=errors.GSC_SITE_URL).execute()

        result = []
        for sitemap in sitemaps.get('sitemap', []):
            result.append({
                'path': sitemap.get('path'),
                'lastSubmitted': sitemap.get('lastSubmitted'),
                'isPending': sitemap.get('isPending', False),
                'isSitemapsIndex': sitemap.get('isSitemapsIndex', False),
                'type': sitemap.get('type'),
                'lastDownloaded': sitemap.get('lastDownloaded'),
                'warnings': sitemap.get('warnings', 0),
                'errors': sitemap.get('errors', 0)
            })

        return result

    except Exception as e:
        brief = errors._api_error_text(e, "fetching sitemaps")
        if brief:
            return {"error": brief}
        return {"error": f"Error fetching sitemaps: {str(e)}"}


@mcp.tool(annotations=_ANNOTATIONS_READ_API)
@instrument
def list_sitemaps():
    """
    List all sitemaps for the configured site (alias for get_sitemaps).

    Returns:
        List of sitemaps with their status and details.
    """
    return get_sitemaps()


@mcp.tool(annotations=_ANNOTATIONS_WRITE_API)
@instrument
def submit_sitemap(sitemap_url: str):
    """
    Submit a sitemap to Google Search Console.

    Args:
        sitemap_url: Full URL of the sitemap to submit

    Returns:
        Success message or error details.
    """
    try:
        service = auth.get_gsc_service()
        service.sitemaps().submit(
            siteUrl=errors.GSC_SITE_URL,
            feedpath=sitemap_url
        ).execute()

        return {"success": f"Sitemap submitted successfully: {sitemap_url}"}

    except Exception as e:
        brief = errors._api_error_text(e, "submitting a sitemap")
        if brief:
            return {"error": brief}
        return {"error": f"Error submitting sitemap: {str(e)}"}


@mcp.tool(annotations=_ANNOTATIONS_DELETE_API)
@instrument
def delete_sitemap(sitemap_url: str):
    """
    Delete a sitemap from Google Search Console.

    Args:
        sitemap_url: Full URL of the sitemap to delete

    Returns:
        Success message or error details.
    """
    try:
        service = auth.get_gsc_service()
        service.sitemaps().delete(
            siteUrl=errors.GSC_SITE_URL,
            feedpath=sitemap_url
        ).execute()

        return {"success": f"Sitemap deleted successfully: {sitemap_url}"}

    except Exception as e:
        brief = errors._api_error_text(e, "deleting a sitemap")
        if brief:
            return {"error": brief}
        return {"error": f"Error deleting sitemap: {str(e)}"}


# ---------------------------------------------------------------------------
# Search Analytics
# ---------------------------------------------------------------------------
def _get_search_analytics_impl(
    dimensions: list[str] = ["query"],
    start_date: str | None = None,
    end_date: str | None = None,
    filters: list[dict] | None = None,
    search_type: str = "web",
    row_limit: int = 1000,
    start_row: int = 0,
    summary_only: bool = False,
    intent: str = None,
    ctx: Context = None
):
    """The original get_search_analytics body, unchanged except the S3 brief
    hook in the except block.  Sync (blocking Google API client); the async
    tool wrapper runs it in a worker thread."""
    try:
        row_limit = _coerce_int(row_limit, default=1000, min_val=1, max_val=25000)
        start_row = _coerce_int(start_row, default=0, min_val=0)
        summary_only = _coerce_bool(summary_only, default=False)

        if ctx and row_limit > 5000:
            fire_skill_tip(
                ctx=ctx,
                skill="brand_visibility",
                trigger="large_query",
                tool_name="get_search_analytics"
            )

        # Handle string input for dimensions
        if isinstance(dimensions, str):
            try:
                dimensions = json.loads(dimensions)
                if not isinstance(dimensions, list):
                    dimensions = [str(dimensions)]
            except json.JSONDecodeError:
                dimensions = [d.strip() for d in dimensions.split(',')]

        # Validate dimensions (case-insensitive & snake_case friendly)
        valid_dimensions = ["country", "device", "page", "query", "searchAppearance", "date"]
        dim_map = {d.lower(): d for d in valid_dimensions}
        dim_map["search_appearance"] = "searchAppearance"
        dim_map["searchappearance"] = "searchAppearance"
        if not dimensions:
            dimensions = ["query"]
        normalized_dims = []
        for dim in dimensions:
            canonical = dim_map.get(str(dim).strip().lower())
            if not canonical:
                return {"error": f"Invalid dimension '{dim}'. Valid dimensions: {valid_dimensions}"}
            normalized_dims.append(canonical)
        dimensions = normalized_dims

        # Set default dates if not provided
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        if not end_date:
            end_date = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')

        # Handle filters
        request_filters = []
        if filters:
            if isinstance(filters, str):
                try:
                    filters = json.loads(filters)
                except json.JSONDecodeError:
                    return {"error": "Invalid filters format. Expected JSON array."}

            for filter_item in filters:
                raw_dim = filter_item.get('dimension', '')
                filter_dim = dim_map.get(str(raw_dim).strip().lower())
                if not filter_dim:
                    return {"error": f"Invalid filter dimension '{raw_dim}'. Valid dimensions: {valid_dimensions}"}

                request_filters.append({
                    'dimension': filter_dim,
                    'operator': str(filter_item.get('operator', 'equals')).lower(),
                    'expression': filter_item.get('expression')
                })

        # Validate search type (case-insensitive)
        valid_search_types = ["web", "image", "video", "news", "discover", "googleNews"]
        type_map = {t.lower(): t for t in valid_search_types}
        type_map["googlenews"] = "googleNews"
        type_map["google_news"] = "googleNews"
        canonical_type = type_map.get(str(search_type or "web").strip().lower())
        if not canonical_type:
            return {"error": f"Invalid search_type '{search_type}'. Valid types: {valid_search_types}"}
        search_type = canonical_type

        # Build the request
        request = {
            'startDate': start_date,
            'endDate': end_date,
            'dimensions': dimensions,
            'searchType': search_type,
            'rowLimit': min(row_limit, 25000),
            'startRow': start_row
        }

        if request_filters:
            request['dimensionFilterGroups'] = [{
                'filters': request_filters
            }]

        # Execute the request
        service = auth.get_gsc_service()
        response = service.searchanalytics().query(
            siteUrl=errors.GSC_SITE_URL,
            body=request
        ).execute()

        rows = response.get('rows', [])

        if summary_only:
            return {
                "summary": {
                    "total_clicks": sum(r.get('clicks', 0) for r in rows),
                    "total_impressions": sum(r.get('impressions', 0) for r in rows),
                    "avg_ctr": round((sum(r.get('clicks', 0) for r in rows) / sum(r.get('impressions', 0) for r in rows)) * 100, 2) if sum(r.get('impressions', 0) for r in rows) > 0 else 0,
                    "row_count": len(rows)
                }
            }

        # Format the response
        result = {
            'metadata': {
                'site_url': errors.GSC_SITE_URL,
                'start_date': start_date,
                'end_date': end_date,
                'dimensions': dimensions,
                'search_type': search_type,
                'total_rows': len(rows),
                'row_limit': row_limit,
                'start_row': start_row
            },
            'data': []
        }

        for row in rows:
            data_row = {}
            if 'keys' in row:
                for i, dimension in enumerate(dimensions):
                    if i < len(row['keys']):
                        data_row[dimension] = str(row['keys'][i])
            data_row['clicks'] = row.get('clicks', 0)
            data_row['impressions'] = row.get('impressions', 0)
            data_row['ctr'] = round(row.get('ctr', 0.0) * 100, 2)
            data_row['position'] = round(row.get('position', 0.0), 1)
            result['data'].append(data_row)

        return result

    except Exception as e:
        brief = errors._api_error_text(e, "fetching search analytics")
        if brief:
            return {"error": brief}
        import sys
        error_message = f"Error fetching GSC data: {str(e)}"
        print(error_message, file=sys.stderr)
        return {"error": error_message}


@mcp.tool(annotations=_ANNOTATIONS_READ_API, structured_output=True)
@instrument
async def get_search_analytics(
    dimensions: list[str] = ["query"],
    start_date: str | None = None,
    end_date: str | None = None,
    filters: list[dict] | None = None,
    search_type: str = "web",
    row_limit: int = 1000,
    start_row: int = 0,
    summary_only: bool = False,
    intent: str = None,
    ctx: Context = None
) -> SearchAnalyticsResult | str:
    """
    Retrieve Google Search Console search analytics data.

    Args:
        dimensions: List of dimensions from: country, device, page, query, searchAppearance, date
        start_date: Start date in YYYY-MM-DD format (defaults to 30 days ago)
        end_date: End date in YYYY-MM-DD format (defaults to 3 days ago)
        filters: List of filter objects (e.g., [{"dimension": "country", "operator": "equals", "expression": "usa"}])
        search_type: Type of search ('web', 'image', 'video', 'news', 'discover', 'googleNews')
        row_limit: Maximum number of rows to return (max 25000)
        start_row: Starting row for pagination (0-based)
        summary_only: If True, returns only aggregated totals (Token Efficient)
        intent: Short plain-English description of what the user is trying to learn/accomplish. E.g. "which queries drive clicks to the pricing page", "mobile vs desktop performance last month".

    Returns:
        Dictionary containing search analytics data with clicks, impressions, ctr, and position metrics.
    """
    # S7: setup recovery at the point of friction.
    if errors.SERVER_INIT_ERROR and ctx is not None and request_supports_elicitation(ctx):
        try:
            from gsc_setup_flow import run_inline_recovery
            recovered, message = await run_inline_recovery(ctx)
            if not recovered:
                return {"error": message}
        except Exception:
            if errors.SERVER_INIT_ERROR:
                return f"Configuration Error: {errors.SERVER_INIT_ERROR}. Please instruct the user to fix their setup."

    call = functools.partial(
        _get_search_analytics_impl,
        dimensions=dimensions, start_date=start_date, end_date=end_date,
        filters=filters, search_type=search_type, row_limit=row_limit,
        start_row=start_row, summary_only=summary_only, intent=intent, ctx=ctx,
    )
    result = await anyio.to_thread.run_sync(call)

    # S7: one retry at the wall
    try:
        if (isinstance(result, dict) and "error" in result and ctx is not None
                and errors._LAST_BRIEF["error_category"] in ("IAMError", "AuthError")
                and request_supports_elicitation(ctx)):
            from gsc_setup_flow import run_inline_recovery
            recovered, _message = await run_inline_recovery(
                ctx, entry_category=errors._LAST_BRIEF["error_category"])
            if recovered:
                errors._set_brief(None, None)
                result = await anyio.to_thread.run_sync(call)
    except Exception:
        pass

    return result
