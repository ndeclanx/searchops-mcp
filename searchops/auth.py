# SPDX-License-Identifier: MIT

"""GSC API authentication and service initialization."""

import os
import sys

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

from searchops import errors


def get_gsc_service():
    """Initialize and return Google Search Console API service"""
    try:
        credentials = Credentials.from_service_account_file(errors.CREDENTIALS_PATH)
        service = build('searchconsole', 'v1', credentials=credentials)
        return service
    except Exception as e:
        print(f"Error initializing GSC service: {str(e)}", file=sys.stderr)
        raise


def reinitialize():
    """Re-read config from the environment, rebuild the init state, and verify
    against the GSC API with one sites().list() call (proves the key is valid
    AND the configured property is accessible).  Used by the S7 setup recovery.
    Returns (ok, category, detail).  Never raises."""
    errors.CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    errors.GSC_SITE_URL = os.getenv("GSC_SITE_URL")
    errors.SERVER_INIT_ERROR, errors.SERVER_INIT_ERROR_CATEGORY, errors.SERVER_INIT_ERROR_BRIEF_VERSION = errors._compute_init_state()
    if errors.SERVER_INIT_ERROR:
        return False, "config", errors.SERVER_INIT_ERROR
    try:
        service = get_gsc_service()
        sites = service.sites().list().execute()
        entries = {s.get("siteUrl", "") for s in sites.get("siteEntry", [])}
        target = (errors.GSC_SITE_URL or "").strip()
        if target not in entries and target.rstrip("/") not in {e.rstrip("/") for e in entries}:
            detail = (f"the key works, but '{target}' is not among the properties this "
                      f"service account can access ({len(entries)} visible)")
            errors.SERVER_INIT_ERROR = errors._api_error_text(
                Exception("403 PermissionDenied: " + detail),
                "verifying property access")
            errors.SERVER_INIT_ERROR_CATEGORY = "IAMError"
            errors.SERVER_INIT_ERROR_BRIEF_VERSION = errors.BRIEF_403_PROPERTY
            return False, "property_access", detail
        return True, "ok", "initialized"
    except Exception as e:
        err = str(e)
        brief = errors._api_error_text(e, "verifying access")
        if brief:
            errors.SERVER_INIT_ERROR = brief
            errors.SERVER_INIT_ERROR_CATEGORY = errors._LAST_BRIEF["error_category"] or "InternalError"
            errors.SERVER_INIT_ERROR_BRIEF_VERSION = errors._LAST_BRIEF["brief_version"]
            cat = "property_access" if errors._LAST_BRIEF["error_category"] == "IAMError" else "invalid_credentials"
            return False, cat, err
        errors.SERVER_INIT_ERROR = f"Could not connect to Google Search Console: {err}"
        errors.SERVER_INIT_ERROR_CATEGORY = "InternalError"
        errors.SERVER_INIT_ERROR_BRIEF_VERSION = None
        return False, "setup", err
