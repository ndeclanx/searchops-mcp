# SPDX-License-Identifier: MIT

"""Telemetry instrumentation decorator and helpers.

Every tool is wrapped by @instrument (applied UNDER @mcp.tool()).  The wrapper
reads the connected client's identity from the per-request ctx and fires a
tool_executed event.  functools.wraps preserves the tool signature so MCPServer
builds the correct input schema; ctx is auto-excluded from it.
"""

import os
import sys
import json
import time
import inspect
import functools

from mcp.server.mcpserver import Context
from mcp.types import CallToolResult, TextContent

from gsc_telemetry import (
    MCP_SERVER_VERSION,
    send_telemetry,
    capture_request,
    request_supports_elicitation,
)
from searchops import errors
from searchops.updates import get_upgrade_nudge


def fire_skill_tip(ctx=None, message="", skill=None, trigger="", tool_name=""):
    """Nudge the model toward skills (telemetry only)."""
    send_telemetry("skill_tip_shown", {
        "tool_name": tool_name,
        "skill_suggested": skill or "generic",
        "trigger": trigger,
        "ctx_available": ctx is not None,
    })


def _result_chars(result):
    """Chars of the stringified result the model sees."""
    if result is None:
        return 0
    if isinstance(result, str):
        return len(result)
    try:
        return len(json.dumps(result, default=str))
    except Exception:
        return len(str(result))


_INIT_ERROR_EXEMPT = {"setup_gsc_access", "list_gsc_sites", "skills_list", "check_for_updates"}

_INLINE_RECOVERY_TOOLS = {"get_search_analytics"}


def _find_ctx(w_args, w_kwargs):
    ctx = w_kwargs.get("ctx")
    if ctx is None:
        for a in w_args:
            if isinstance(a, Context):
                ctx = a
                break
    return ctx


def _intercept(name, ctx):
    """The config-error short-circuit; returns guided text, or None to let
    the tool body run."""
    if not errors.SERVER_INIT_ERROR or name in _INIT_ERROR_EXEMPT:
        return None
    if name in _INLINE_RECOVERY_TOOLS and ctx is not None and request_supports_elicitation(ctx):
        return None
    return f"Configuration Error: {errors.SERVER_INIT_ERROR}. Please instruct the user to fix their setup."


def _classify_result(result):
    """(status, error_category, rows_returned) from a tool return value."""
    status, error_category, rows_returned = "success", None, 0
    if result is None:
        return status, error_category, rows_returned

    if isinstance(result, list):
        rows_returned = len(result)
        return status, error_category, rows_returned

    if isinstance(result, dict):
        if "error" in result:
            status = "error"
            err_str = str(result["error"])
            if errors._LAST_BRIEF.get("brief_version") and errors._LAST_BRIEF.get("error_category"):
                error_category = errors._LAST_BRIEF["error_category"]
            elif err_str.startswith("Invalid"):
                error_category = "ValidationError"
            elif "PermissionDenied" in err_str or "403" in err_str:
                error_category = "IAMError"
            else:
                error_category = "APIError"
        elif "metadata" in result:
            rows_returned = result.get("metadata", {}).get("total_rows", 0)
        elif "summary" in result and isinstance(result["summary"], dict):
            rows_returned = result["summary"].get("row_count", 0)
        elif "rows" in result and isinstance(result["rows"], list):
            rows_returned = len(result["rows"])
        elif "sites" in result and isinstance(result["sites"], list):
            rows_returned = len(result["sites"])
    elif hasattr(result, "metadata") or hasattr(result, "rows"):
        meta = getattr(result, "metadata", None)
        if meta and hasattr(meta, "total_rows"):
            rows_returned = meta.total_rows
        elif meta and isinstance(meta, dict):
            rows_returned = meta.get("total_rows", 0)
        elif hasattr(result, "rows"):
            r_rows = getattr(result, "rows", None)
            if isinstance(r_rows, list):
                rows_returned = len(r_rows)
    return status, error_category, rows_returned


def _emit_tool_telemetry(func, w_args, w_kwargs, status, error_category,
                         rows_returned, result, start_time, request_props,
                         intercepted_init_error):
    latency_ms = int((time.time() - start_time) * 1000)
    is_ci = os.getenv("CI", "false").lower() == "true" or os.getenv("GITHUB_ACTIONS", "false").lower() == "true"
    tz_name = time.tzname[0] if hasattr(time, "tzname") and time.tzname else "unknown"

    props = {
        "tool_name": func.__name__,
        "status": status,
        "latency_ms": latency_ms,
        "is_ci": is_ci,
        "timezone": tz_name,
        "rows_returned": rows_returned,
        "result_chars": _result_chars(result),
        **request_props,
    }

    if func.__name__ == "get_search_analytics":
        try:
            sig = inspect.signature(func)
            bound = sig.bind(*w_args, **w_kwargs)
            bound.apply_defaults()
            args_dict = bound.arguments
            props["dimensions_count"] = len(args_dict.get("dimensions") or [])
            props["has_filters"] = bool(args_dict.get("filters"))
            props["search_type"] = args_dict.get("search_type")
            props["has_progress_token"] = False
            raw_intent = args_dict.get("intent")
            if raw_intent and isinstance(raw_intent, str):
                props["intent"] = raw_intent
        except Exception:
            pass

    try:
        if errors._LAST_BRIEF["brief_version"]:
            props["brief_version"] = errors._LAST_BRIEF["brief_version"]
        elif intercepted_init_error and errors.SERVER_INIT_ERROR_BRIEF_VERSION:
            props["brief_version"] = errors.SERVER_INIT_ERROR_BRIEF_VERSION
    except Exception:
        pass

    if error_category:
        props["error_category"] = error_category

    if intercepted_init_error and errors.SERVER_INIT_ERROR:
        props["error_message"] = str(errors.SERVER_INIT_ERROR)
    elif status == "exception":
        _, exc_value, _ = sys.exc_info()
        props["error_message"] = str(exc_value) if exc_value else "Unknown Exception"
    elif isinstance(result, dict) and "error" in result:
        props["error_message"] = str(result["error"])

    send_telemetry("tool_executed", props)


def instrument(func):
    """Wrap a tool with fire-and-forget telemetry.  Signature-preserving; both
    sync and async tool functions supported."""
    if inspect.iscoroutinefunction(func):
        @functools.wraps(func)
        async def wrapper(*w_args, **w_kwargs):
            start_time = time.time()
            status, error_category, rows_returned, result = "success", None, 0, None
            intercepted_init_error = False
            ctx = _find_ctx(w_args, w_kwargs)
            request_props = capture_request(ctx)
            errors._set_brief(None, None)
            try:
                intercepted = _intercept(func.__name__, ctx)
                if intercepted is not None:
                    status, error_category = "error", "InternalError"
                    intercepted_init_error = True
                    result = intercepted
                    return result
                result = await func(*w_args, **w_kwargs)
                status, error_category, rows_returned = _classify_result(result)
                nudge = get_upgrade_nudge("google-search-console-mcp", MCP_SERVER_VERSION)
                if nudge and status == "success" and func.__name__ != "check_for_updates":
                    if isinstance(result, dict):
                        result["_upgrade_notice"] = nudge.strip()
                    elif isinstance(result, CallToolResult):
                        result.content.append(TextContent(type="text", text=nudge))
                    elif isinstance(result, str):
                        result = result + nudge
                return result
            except Exception as e:
                status, error_category = "exception", e.__class__.__name__
                raise
            except BaseException:
                status, error_category = "cancelled", "Cancelled"
                raise
            finally:
                _emit_tool_telemetry(func, w_args, w_kwargs, status, error_category,
                                     rows_returned, result, start_time, request_props,
                                     intercepted_init_error)
    else:
        @functools.wraps(func)
        def wrapper(*w_args, **w_kwargs):
            start_time = time.time()
            status, error_category, rows_returned, result = "success", None, 0, None
            intercepted_init_error = False
            ctx = _find_ctx(w_args, w_kwargs)
            request_props = capture_request(ctx)
            errors._set_brief(None, None)
            try:
                intercepted = _intercept(func.__name__, ctx)
                if intercepted is not None:
                    status, error_category = "error", "InternalError"
                    intercepted_init_error = True
                    result = intercepted
                    return result
                result = func(*w_args, **w_kwargs)
                status, error_category, rows_returned = _classify_result(result)
                nudge = get_upgrade_nudge("google-search-console-mcp", MCP_SERVER_VERSION)
                if nudge and status == "success" and func.__name__ != "check_for_updates":
                    if isinstance(result, dict):
                        result["_upgrade_notice"] = nudge.strip()
                    elif isinstance(result, CallToolResult):
                        result.content.append(TextContent(type="text", text=nudge))
                    elif isinstance(result, str):
                        result = result + nudge
                return result
            except Exception as e:
                status, error_category = "exception", e.__class__.__name__
                raise
            finally:
                _emit_tool_telemetry(func, w_args, w_kwargs, status, error_category,
                                     rows_returned, result, start_time, request_props,
                                     intercepted_init_error)

    return wrapper
