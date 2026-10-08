# SPDX-License-Identifier: MIT

"""GSC data provider — wraps all Google Search Console API calls.

Tools in ``searchops.tools.gsc`` delegate API interaction to this class.
Auth, credential management, and the ``reinitialize()`` flow still live in
``searchops.auth``; this class calls through to them.
"""

from __future__ import annotations

import os
from datetime import date

from searchops import auth, errors


class QuotaExceededError(Exception):
    """Raised when the in-memory daily quota for a resource is exhausted."""


class GSCProvider:
    """Thin wrapper around the Google Search Console API.

    All methods raise on transport/auth errors — callers (tools) are
    responsible for catching and translating via ``errors._api_error_text``.
    """

    def __init__(self):
        self._inspect_quota_limit = int(
            os.getenv("SEARCHOPS_INSPECT_QUOTA_DAILY", "2000")
        )
        self._inspect_count = 0
        self._inspect_date: date | None = None

    # ------------------------------------------------------------------
    # Service construction
    # ------------------------------------------------------------------
    def _get_service(self):
        """Build and return a GSC API service object."""
        return auth.get_gsc_service()

    # ------------------------------------------------------------------
    # Sites
    # ------------------------------------------------------------------
    def list_sites(self) -> list[dict]:
        """Return verified sites with permission levels."""
        service = self._get_service()
        resp = service.sites().list().execute()
        return [
            {"siteUrl": s["siteUrl"], "permissionLevel": s["permissionLevel"]}
            for s in resp.get("siteEntry", [])
        ]

    # ------------------------------------------------------------------
    # Sitemaps
    # ------------------------------------------------------------------
    def get_sitemaps(self, site_url: str) -> list[dict]:
        """Return raw sitemap entries for *site_url*."""
        service = self._get_service()
        resp = service.sitemaps().list(siteUrl=site_url).execute()
        return resp.get("sitemap", [])

    def submit_sitemap(self, site_url: str, sitemap_url: str) -> None:
        """Submit *sitemap_url* to GSC for *site_url*."""
        service = self._get_service()
        service.sitemaps().submit(
            siteUrl=site_url, feedpath=sitemap_url
        ).execute()

    def delete_sitemap(self, site_url: str, sitemap_url: str) -> None:
        """Delete *sitemap_url* from GSC for *site_url*."""
        service = self._get_service()
        service.sitemaps().delete(
            siteUrl=site_url, feedpath=sitemap_url
        ).execute()

    # ------------------------------------------------------------------
    # Search Analytics
    # ------------------------------------------------------------------
    def search_analytics(self, site_url: str, body: dict) -> dict:
        """Execute a ``searchAnalytics.query`` call and return the raw response."""
        service = self._get_service()
        return service.searchanalytics().query(
            siteUrl=site_url, body=body
        ).execute()

    # ------------------------------------------------------------------
    # URL Inspection
    # ------------------------------------------------------------------
    def _check_inspect_quota(self) -> None:
        """Enforce in-memory daily quota for URL Inspection API calls.

        Resets automatically when the date changes (server-local time).
        Raises ``QuotaExceededError`` if the daily limit is reached.
        """
        today = date.today()
        if self._inspect_date != today:
            self._inspect_count = 0
            self._inspect_date = today
        if self._inspect_count >= self._inspect_quota_limit:
            raise QuotaExceededError(
                f"URL Inspection API daily quota exhausted "
                f"({self._inspect_quota_limit} calls/day). "
                f"The quota resets at midnight server time. "
                f"Adjust with SEARCHOPS_INSPECT_QUOTA_DAILY env var."
            )

    def inspect_url(self, site_url: str, inspection_url: str) -> dict:
        """Inspect a URL via the URL Inspection API.

        Returns the raw ``inspectionResult`` from the API response.
        Raises ``QuotaExceededError`` if the daily limit is reached.
        """
        self._check_inspect_quota()
        service = self._get_service()
        body = {
            "inspectionUrl": inspection_url,
            "siteUrl": site_url,
        }
        result = service.urlInspection().index().inspect(body=body).execute()
        self._inspect_count += 1
        return result

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def reinitialize(self) -> tuple[bool, str, str]:
        """Re-read config, verify connectivity.  Delegates to ``auth.reinitialize()``."""
        return auth.reinitialize()
