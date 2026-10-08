# SPDX-License-Identifier: MIT

"""Tests for the inspect_url MCP tool.

Stubs googleapiclient.discovery so no Google credentials are required.
"""

import os
import sys
import types
import unittest
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

    fastmcp = types.ModuleType("fastmcp")

    class _FakeMCP:
        def __init__(self, *a, **kw):
            pass
        def tool(self, *a, **kw):
            def _decorator(fn):
                return fn
            return _decorator
        def run(self, *a, **kw):
            pass

    fastmcp.FastMCP = _FakeMCP
    sys.modules.setdefault("fastmcp", fastmcp)

    fake_sa = os.path.join(REPO_ROOT, "tests", "_fake_sa.json")
    if not os.path.exists(fake_sa):
        with open(fake_sa, "w") as f:
            f.write("{}")
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = fake_sa
    os.environ.setdefault("GSC_SITE_URL", "https://example.com/")


_install_stubs()

import searchops.tools.gsc as gsc_tools  # noqa: E402
from searchops.providers import gsc_provider  # noqa: E402
from searchops.providers.gsc import QuotaExceededError  # noqa: E402
from searchops import errors  # noqa: E402


# Sample API response matching the URL Inspection API format
SAMPLE_INSPECTION_RESPONSE = {
    "inspectionResult": {
        "indexStatusResult": {
            "verdict": "PASS",
            "coverageState": "Submitted and indexed",
            "robotsTxtState": "ALLOWED",
            "indexingState": "INDEXING_ALLOWED",
            "lastCrawlTime": "2025-05-01T12:00:00Z",
            "pageFetchState": "SUCCESSFUL",
            "googleCanonical": "https://example.com/page",
            "userCanonical": "https://example.com/page",
            "crawledAs": "MOBILE",
            "sitemap": ["https://example.com/sitemap.xml"],
            "referringUrls": ["https://example.com/"],
        },
        "richResultsResult": {
            "verdict": "PASS",
            "detectedItems": [{"richResultType": "Article"}],
        },
    }
}


class TestInspectUrlTool(unittest.TestCase):
    def setUp(self):
        self._orig_inspect = gsc_provider.inspect_url
        self._orig_init_error = errors.SERVER_INIT_ERROR

    def tearDown(self):
        gsc_provider.inspect_url = self._orig_inspect
        errors.SERVER_INIT_ERROR = self._orig_init_error

    def test_returns_structured_result(self):
        gsc_provider.inspect_url = lambda site_url, url: SAMPLE_INSPECTION_RESPONSE

        result = gsc_tools.inspect_url("https://example.com/page")
        self.assertNotIn("error", result)
        self.assertEqual(result["inspected_url"], "https://example.com/page")
        self.assertEqual(result["index_status"]["verdict"], "PASS")
        self.assertEqual(result["index_status"]["coverage_state"], "Submitted and indexed")
        self.assertEqual(result["index_status"]["robots_txt_state"], "ALLOWED")
        self.assertEqual(result["index_status"]["crawled_as"], "MOBILE")
        self.assertEqual(result["index_status"]["google_canonical"], "https://example.com/page")
        self.assertIn("rich_results", result)

    def test_default_site_url(self):
        """When site_url is not passed, uses errors.GSC_SITE_URL."""
        captured = {}

        def fake_inspect(site_url, url):
            captured["site_url"] = site_url
            return {"inspectionResult": {"indexStatusResult": {}}}

        gsc_provider.inspect_url = fake_inspect
        gsc_tools.inspect_url("https://example.com/page")
        self.assertEqual(captured["site_url"], errors.GSC_SITE_URL.strip())

    def test_explicit_site_url_override(self):
        """When site_url is passed, it takes precedence."""
        captured = {}

        def fake_inspect(site_url, url):
            captured["site_url"] = site_url
            return {"inspectionResult": {"indexStatusResult": {}}}

        gsc_provider.inspect_url = fake_inspect
        gsc_tools.inspect_url("https://other.com/page", site_url="https://other.com/")
        self.assertEqual(captured["site_url"], "https://other.com/")

    def test_quota_exceeded_returns_error(self):
        def raise_quota(*a, **kw):
            raise QuotaExceededError("quota exceeded")

        gsc_provider.inspect_url = raise_quota
        result = gsc_tools.inspect_url("https://example.com/page")
        self.assertIn("error", result)
        self.assertIn("quota", result["error"].lower())

    def test_api_error_returns_error_dict(self):
        def raise_api_error(*a, **kw):
            raise Exception("403 PermissionDenied: not authorized")

        gsc_provider.inspect_url = raise_api_error
        result = gsc_tools.inspect_url("https://example.com/page")
        self.assertIn("error", result)

    def test_init_error_returns_config_error(self):
        errors.SERVER_INIT_ERROR = "Missing credentials"
        result = gsc_tools.inspect_url("https://example.com/page")
        self.assertIn("Configuration Error", result)

    def test_no_rich_results_omitted(self):
        """When no rich results, key is absent from output."""
        gsc_provider.inspect_url = lambda s, u: {
            "inspectionResult": {"indexStatusResult": {"verdict": "PASS"}}
        }
        result = gsc_tools.inspect_url("https://example.com/page")
        self.assertNotIn("rich_results", result)
        self.assertNotIn("amp_inspection", result)


if __name__ == "__main__":
    unittest.main()
