# SPDX-License-Identifier: MIT

"""Verify all public names are importable from both the searchops package
and the backward-compatible gsc_mcp_server shim."""

import os
import sys
import types
from unittest.mock import MagicMock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)


def _install_stubs():
    """Stub external dependencies before importing the server module."""
    google_pkg = types.ModuleType("google")
    google_oauth2 = types.ModuleType("google.oauth2")
    google_oauth2_sa = types.ModuleType("google.oauth2.service_account")

    class _Creds:
        @classmethod
        def from_service_account_file(cls, *args, **kwargs):
            return cls()

    google_oauth2_sa.Credentials = _Creds
    google_oauth2.service_account = google_oauth2_sa
    google_pkg.oauth2 = google_oauth2

    sys.modules.setdefault("google", google_pkg)
    sys.modules["google.oauth2"] = google_oauth2
    sys.modules["google.oauth2.service_account"] = google_oauth2_sa

    googleapiclient = types.ModuleType("googleapiclient")
    googleapiclient_discovery = types.ModuleType("googleapiclient.discovery")
    googleapiclient_discovery.build = lambda *a, **kw: MagicMock()
    googleapiclient.discovery = googleapiclient_discovery
    sys.modules.setdefault("googleapiclient", googleapiclient)
    sys.modules["googleapiclient.discovery"] = googleapiclient_discovery

    fake_sa = os.path.join(REPO_ROOT, "tests", "_fake_sa.json")
    if not os.path.exists(fake_sa):
        with open(fake_sa, "w") as f:
            f.write("{}")
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = fake_sa
    os.environ.setdefault("GSC_SITE_URL", "https://example.com/")


_install_stubs()


def test_searchops_package_importable():
    """The searchops package and its submodules are importable."""
    import searchops
    import searchops.server
    import searchops.errors
    import searchops.auth
    import searchops.instrument
    import searchops.updates
    import searchops.prompts
    import searchops.resources
    import searchops.tools.gsc
    import searchops.tools.schema
    import searchops.tools.skills
    import searchops.tools.updates
    assert hasattr(searchops, "PACKAGE_ROOT")


def test_shim_exposes_mcp():
    """The shim module exposes the MCPServer instance."""
    import gsc_mcp_server
    assert hasattr(gsc_mcp_server, "mcp")
    assert gsc_mcp_server.mcp is not None


def test_shim_delegates_mutable_globals():
    """SERVER_INIT_ERROR reads through to searchops.errors."""
    import gsc_mcp_server
    import searchops.errors
    assert gsc_mcp_server.SERVER_INIT_ERROR is searchops.errors.SERVER_INIT_ERROR


def test_shim_delegates_functions():
    """Functions like reinitialize are accessible from the shim."""
    import gsc_mcp_server
    import searchops.auth
    assert gsc_mcp_server.reinitialize is searchops.auth.reinitialize


def test_shim_delegates_instrument():
    """The instrument decorator is accessible from the shim."""
    import gsc_mcp_server
    import searchops.instrument
    assert gsc_mcp_server.instrument is searchops.instrument.instrument


def test_shim_delegates_annotations():
    """Annotation constants are accessible from the shim."""
    import gsc_mcp_server
    import searchops.server
    assert gsc_mcp_server._ANNOTATIONS_SETUP is searchops.server._ANNOTATIONS_SETUP
    assert gsc_mcp_server._ANNOTATIONS_READ_API is searchops.server._ANNOTATIONS_READ_API


def test_shim_delegates_update_utils():
    """Update utilities are accessible from the shim."""
    import gsc_mcp_server
    import searchops.updates
    assert gsc_mcp_server._parse_version is searchops.updates._parse_version
    assert gsc_mcp_server.check_server_update is searchops.updates.check_server_update


def test_shim_delegates_classify_result():
    """_classify_result is accessible from the shim."""
    import gsc_mcp_server
    import searchops.instrument
    assert gsc_mcp_server._classify_result is searchops.instrument._classify_result


def test_shim_has_main():
    """The shim has a main() entry point."""
    import gsc_mcp_server
    assert callable(gsc_mcp_server.main)


def test_same_mcp_instance():
    """The shim and searchops.server share the same MCPServer instance."""
    import gsc_mcp_server
    import searchops.server
    assert gsc_mcp_server.mcp is searchops.server.mcp
