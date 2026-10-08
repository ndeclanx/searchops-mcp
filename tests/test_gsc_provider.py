# SPDX-License-Identifier: MIT

"""Unit tests for GSCProvider.

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

from searchops.providers.gsc import GSCProvider  # noqa: E402
from searchops.providers import gsc_provider, DataProvider  # noqa: E402


class TestGSCProviderProtocol(unittest.TestCase):
    def test_gsc_provider_satisfies_data_provider(self):
        self.assertIsInstance(gsc_provider, DataProvider)

    def test_module_singleton_is_gsc_provider(self):
        self.assertIsInstance(gsc_provider, GSCProvider)


class TestGSCProviderListSites(unittest.TestCase):
    def test_list_sites_returns_formatted_entries(self):
        provider = GSCProvider()
        mock_service = MagicMock()
        mock_service.sites.return_value.list.return_value.execute.return_value = {
            "siteEntry": [
                {"siteUrl": "https://a.com/", "permissionLevel": "siteOwner"},
                {"siteUrl": "https://b.com/", "permissionLevel": "siteFullUser"},
            ]
        }
        provider._get_service = lambda: mock_service

        result = provider.list_sites()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], {"siteUrl": "https://a.com/", "permissionLevel": "siteOwner"})
        self.assertEqual(result[1], {"siteUrl": "https://b.com/", "permissionLevel": "siteFullUser"})

    def test_list_sites_empty(self):
        provider = GSCProvider()
        mock_service = MagicMock()
        mock_service.sites.return_value.list.return_value.execute.return_value = {
            "siteEntry": []
        }
        provider._get_service = lambda: mock_service
        self.assertEqual(provider.list_sites(), [])


class TestGSCProviderSitemaps(unittest.TestCase):
    def setUp(self):
        self.provider = GSCProvider()
        self.mock_service = MagicMock()
        self.provider._get_service = lambda: self.mock_service

    def test_get_sitemaps(self):
        self.mock_service.sitemaps.return_value.list.return_value.execute.return_value = {
            "sitemap": [
                {"path": "https://a.com/sitemap.xml", "type": "sitemap"},
            ]
        }
        result = self.provider.get_sitemaps("https://a.com/")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["path"], "https://a.com/sitemap.xml")
        self.mock_service.sitemaps.return_value.list.assert_called_once_with(siteUrl="https://a.com/")

    def test_get_sitemaps_empty(self):
        self.mock_service.sitemaps.return_value.list.return_value.execute.return_value = {}
        self.assertEqual(self.provider.get_sitemaps("https://a.com/"), [])

    def test_submit_sitemap(self):
        self.provider.submit_sitemap("https://a.com/", "https://a.com/sitemap.xml")
        self.mock_service.sitemaps.return_value.submit.assert_called_once_with(
            siteUrl="https://a.com/", feedpath="https://a.com/sitemap.xml"
        )

    def test_delete_sitemap(self):
        self.provider.delete_sitemap("https://a.com/", "https://a.com/sitemap.xml")
        self.mock_service.sitemaps.return_value.delete.assert_called_once_with(
            siteUrl="https://a.com/", feedpath="https://a.com/sitemap.xml"
        )


class TestGSCProviderSearchAnalytics(unittest.TestCase):
    def test_search_analytics_passes_body(self):
        provider = GSCProvider()
        mock_service = MagicMock()
        mock_service.searchanalytics.return_value.query.return_value.execute.return_value = {
            "rows": [{"clicks": 10, "impressions": 100}]
        }
        provider._get_service = lambda: mock_service

        body = {"startDate": "2025-01-01", "endDate": "2025-01-31", "dimensions": ["query"]}
        result = provider.search_analytics("https://a.com/", body)

        self.assertEqual(result["rows"][0]["clicks"], 10)
        mock_service.searchanalytics.return_value.query.assert_called_once_with(
            siteUrl="https://a.com/", body=body
        )

    def test_search_analytics_raises_on_error(self):
        provider = GSCProvider()
        mock_service = MagicMock()
        mock_service.searchanalytics.return_value.query.return_value.execute.side_effect = Exception("403")
        provider._get_service = lambda: mock_service

        with self.assertRaises(Exception):
            provider.search_analytics("https://a.com/", {})


if __name__ == "__main__":
    unittest.main()
