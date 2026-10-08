# SPDX-License-Identifier: MIT

"""Backward-compatible shim — real code lives in searchops/.

This module preserves the ``import gsc_mcp_server`` interface used by
gsc_setup_flow.py, existing tests, and the PyPI entry-point scripts.
All tool registrations happen as a side-effect of importing
``searchops.server`` (which in turn imports the tool modules).

The module object is replaced at the bottom by a custom ModuleType subclass
whose ``__setattr__`` propagates writes to the canonical searchops location
(needed for test monkeypatching backward compatibility — PEP 562 only added
module-level ``__getattr__``, not ``__setattr__``).
"""

import sys
import types

# Under ``python -m gsc_mcp_server`` the module name is "__main__"; without
# this alias gsc_setup_flow's ``import gsc_mcp_server`` would build a SECOND
# module instance with its own MCPServer.
sys.modules.setdefault("gsc_mcp_server", sys.modules[__name__])

# Eagerly import the searchops package — this triggers all @mcp.tool()
# registrations as a side-effect.
import searchops.server   # noqa: E402
import searchops.errors   # noqa: E402
import searchops.auth     # noqa: E402
import searchops.instrument  # noqa: E402
import searchops.updates  # noqa: E402
import searchops.providers  # noqa: E402

# Re-export the MCPServer instance eagerly so ``server.mcp.tool(...)`` in
# gsc_setup_flow.py can find it during that module's import.
mcp = searchops.server.mcp

# ---------------------------------------------------------------------------
# Name-to-module mapping for __getattr__ / __setattr__ delegation.
# ---------------------------------------------------------------------------
_ATTR_MAP = {
    # searchops.server
    "_ANNOTATIONS_READ_LOCAL": "searchops.server",
    "_ANNOTATIONS_READ_API": "searchops.server",
    "_ANNOTATIONS_WRITE_API": "searchops.server",
    "_ANNOTATIONS_DELETE_API": "searchops.server",
    "_ANNOTATIONS_SETUP": "searchops.server",
    "GSC_MCP_INSTRUCTIONS": "searchops.server",
    # searchops.errors
    "CREDENTIALS_PATH": "searchops.errors",
    "GSC_SITE_URL": "searchops.errors",
    "_guided_error": "searchops.errors",
    "BRIEF_CREDS_UNSET": "searchops.errors",
    "BRIEF_CREDS_MISSING": "searchops.errors",
    "BRIEF_SITE_UNSET": "searchops.errors",
    "BRIEF_403_PROPERTY": "searchops.errors",
    "BRIEF_401_INVALID": "searchops.errors",
    "_compute_init_state": "searchops.errors",
    "SERVER_INIT_ERROR": "searchops.errors",
    "SERVER_INIT_ERROR_CATEGORY": "searchops.errors",
    "SERVER_INIT_ERROR_BRIEF_VERSION": "searchops.errors",
    "_LAST_BRIEF": "searchops.errors",
    "_set_brief": "searchops.errors",
    "_AUTH_401_MARKERS": "searchops.errors",
    "_AUTH_403_MARKERS": "searchops.errors",
    "_api_error_text": "searchops.errors",
    # searchops.auth
    "get_gsc_service": "searchops.auth",
    "reinitialize": "searchops.auth",
    # searchops.instrument
    "instrument": "searchops.instrument",
    "fire_skill_tip": "searchops.instrument",
    "_result_chars": "searchops.instrument",
    "_INIT_ERROR_EXEMPT": "searchops.instrument",
    "_INLINE_RECOVERY_TOOLS": "searchops.instrument",
    "_find_ctx": "searchops.instrument",
    "_intercept": "searchops.instrument",
    "_classify_result": "searchops.instrument",
    "_emit_tool_telemetry": "searchops.instrument",
    # searchops.updates
    "_FLEET_CACHE_FILE": "searchops.updates",
    "_UPDATE_CHECK_TTL": "searchops.updates",
    "_NUDGE_THROTTLE_INTERVAL": "searchops.updates",
    "_parse_version": "searchops.updates",
    "check_server_update": "searchops.updates",
    "get_upgrade_nudge": "searchops.updates",
    # searchops.providers
    "gsc_provider": "searchops.providers",
    # searchops.tools.gsc
    "SearchAnalyticsResult": "searchops.tools.gsc",
    "_coerce_int": "searchops.tools.gsc",
    "_coerce_bool": "searchops.tools.gsc",
    "list_gsc_sites": "searchops.tools.gsc",
    "list_sites": "searchops.tools.gsc",
    "get_sitemaps": "searchops.tools.gsc",
    "list_sitemaps": "searchops.tools.gsc",
    "submit_sitemap": "searchops.tools.gsc",
    "delete_sitemap": "searchops.tools.gsc",
    "_get_search_analytics_impl": "searchops.tools.gsc",
    "get_search_analytics": "searchops.tools.gsc",
    "inspect_url": "searchops.tools.gsc",
    # searchops.tools.schema
    "load_gsc_dimensions": "searchops.tools.schema",
    "load_gsc_metrics": "searchops.tools.schema",
    "list_available_dimensions": "searchops.tools.schema",
    "list_available_metrics": "searchops.tools.schema",
    # searchops.tools.skills
    "skills_list": "searchops.tools.skills",
    "skill_read": "searchops.tools.skills",
    # searchops.tools.updates
    "check_for_updates": "searchops.tools.updates",
    # searchops.tools.audit
    "get_audit_summary": "searchops.tools.audit",
    "get_audit_issues": "searchops.tools.audit",
    "get_issue": "searchops.tools.audit",
    # searchops.tools.opportunities
    "find_search_opportunities": "searchops.tools.opportunities",
    # searchops.tools.traffic_decay
    "detect_traffic_decay_tool": "searchops.tools.traffic_decay",
    # searchops.tools.cannibalization
    "detect_cannibalization_tool": "searchops.tools.cannibalization",
    # searchops.tools.crawl_parsers
    "analyze_robots_txt": "searchops.tools.crawl_parsers",
    "parse_sitemap": "searchops.tools.crawl_parsers",
    # searchops.prompts
    "analyze_brand_visibility": "searchops.prompts",
    "content_opportunities": "searchops.prompts",
    "diagnose_traffic_drop": "searchops.prompts",
}


class _ShimModule(types.ModuleType):
    """A ModuleType subclass that delegates reads and writes to searchops.

    PEP 562 only supports module-level ``__getattr__`` — ``__setattr__``
    requires a custom type.  Existing tests monkeypatch attributes on
    ``gsc_mcp_server`` (e.g. ``get_gsc_service``); the ``__setattr__`` here
    propagates that write to the canonical searchops submodule so the tool
    code (which uses module-attribute access like ``auth.get_gsc_service()``)
    picks up the patched version.
    """

    def __getattr__(self, name):
        mod_name = _ATTR_MAP.get(name)
        if mod_name is not None:
            mod = sys.modules.get(mod_name)
            if mod is not None:
                return getattr(mod, name)
        raise AttributeError(f"module {self.__name__!r} has no attribute {name!r}")

    def __setattr__(self, name, value):
        mod_name = _ATTR_MAP.get(name)
        if mod_name is not None:
            mod = sys.modules.get(mod_name)
            if mod is not None:
                setattr(mod, name, value)
        # Also store locally so subsequent reads find the set value.
        super().__setattr__(name, value)

    def __delattr__(self, name):
        mod_name = _ATTR_MAP.get(name)
        if mod_name is not None:
            mod = sys.modules.get(mod_name)
            if mod is not None:
                try:
                    delattr(mod, name)
                except AttributeError:
                    pass
        try:
            super().__delattr__(name)
        except AttributeError:
            pass


# ---------------------------------------------------------------------------
# Replace the plain module object with _ShimModule so __setattr__ works.
# ---------------------------------------------------------------------------
_current = sys.modules[__name__]
_shim = _ShimModule(__name__)
_shim.__dict__.update(_current.__dict__)
_shim.__file__ = _current.__file__
_shim.__loader__ = getattr(_current, "__loader__", None)
_shim.__spec__ = getattr(_current, "__spec__", None)
if hasattr(_current, "__path__"):
    _shim.__path__ = _current.__path__
sys.modules[__name__] = _shim
sys.modules["gsc_mcp_server"] = _shim

# S7: the interactive setup-recovery tool (registers setup_gsc_access).
# Imported AFTER the shim replacement — gsc_setup_flow accesses
# server.mcp, server._ANNOTATIONS_SETUP, and server.instrument.
import gsc_setup_flow  # noqa: E402,F401


def main():
    """Main entry point for the MCP server."""
    searchops.server.main()


_shim.main = main

if __name__ == "__main__":
    main()
