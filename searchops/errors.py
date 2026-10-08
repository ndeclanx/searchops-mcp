# SPDX-License-Identifier: MIT

"""S3 error briefs, configuration state, and init-time checks.

All user-fixable failure paths get ONE versioned brief: what happened,
retrying won't help (when true), and numbered steps forwardable to the
human.  The version tag rides tool_executed as `brief_version` so
PostHog can measure post-brief success per brief revision.
"""

import os


# ---------------------------------------------------------------------------
# Configuration from environment variables
# ---------------------------------------------------------------------------
CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
GSC_SITE_URL = os.getenv("GSC_SITE_URL")  # e.g., "https://example.com/"


# ---------------------------------------------------------------------------
# S3: two-audience error briefs (Protocol Surfaces v1)
# ---------------------------------------------------------------------------
BRIEF_CREDS_UNSET = "gsc-creds-unset-v1"
BRIEF_CREDS_MISSING = "gsc-creds-missing-v1"
BRIEF_SITE_UNSET = "gsc-site-unset-v1"
BRIEF_403_PROPERTY = "gsc-403-property-v1"
BRIEF_401_INVALID = "gsc-401-invalid-v1"
BRIEF_INSPECT_QUOTA = "gsc-inspect-quota-v1"


def _guided_error(what, steps):
    step_text = " ".join(f"({i}) {s}" for i, s in enumerate(steps, 1))
    return (f"[SETUP BLOCKED] {what}  "
            f"RETRYING WON'T HELP — do not re-call data tools.  "
            f"WHAT MUST HAPPEN: {step_text}")


def _compute_init_state():
    """(error_text, error_category, brief_version) from the current env.
    Same check order as the original boot logic: creds unset > site unset >
    creds file missing."""
    creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    site = os.getenv("GSC_SITE_URL")
    if not creds:
        return (
            _guided_error(
                "No Google credentials are configured — the GOOGLE_APPLICATION_CREDENTIALS "
                "environment variable is unset.",
                [
                    "In Google Cloud Console > IAM & Admin > Service Accounts, create (or pick) "
                    "a service account and download a JSON key.",
                    "In Search Console (search.google.com/search-console) > Settings > "
                    "Users and permissions, add that service account's email as a user.",
                    "Set GOOGLE_APPLICATION_CREDENTIALS to the key's absolute path in this MCP "
                    "server's env config and restart the client — or, if this client supports "
                    "interactive prompts, call setup_gsc_access to fix it in-chat now.",
                ],
            ),
            "InternalError",
            BRIEF_CREDS_UNSET,
        )
    if not site:
        return (
            _guided_error(
                "GSC_SITE_URL is not set, so this server does not know which Search Console "
                "property to query.",
                [
                    "Copy the property EXACTLY as it appears in the Search Console property "
                    "selector: URL-prefix properties look like 'https://example.com/' (trailing "
                    "slash included); Domain properties look like 'sc-domain:example.com'.",
                    "Set GSC_SITE_URL to that value in this MCP server's env config and restart "
                    "the client — or call setup_gsc_access to set it in-chat if this client "
                    "supports interactive prompts.",
                ],
            ),
            "InternalError",
            BRIEF_SITE_UNSET,
        )
    if not os.path.exists(creds):
        return (
            _guided_error(
                f"The credentials file was not found at '{creds}' "
                "(from GOOGLE_APPLICATION_CREDENTIALS).",
                [
                    "Verify the JSON key exists at that exact absolute path on THIS machine "
                    "(the one running the MCP server).",
                    "Fix the path in this MCP server's env config and restart the client — or "
                    "call setup_gsc_access to correct it in-chat if this client supports "
                    "interactive prompts.",
                ],
            ),
            "InternalError",
            BRIEF_CREDS_MISSING,
        )
    return None, None, None


SERVER_INIT_ERROR, SERVER_INIT_ERROR_CATEGORY, SERVER_INIT_ERROR_BRIEF_VERSION = _compute_init_state()

# The brief (if any) behind the most recent API-error return.  Module state,
# not a contextvar: tool bodies run inside anyio worker threads whose context
# copies never propagate back, so a contextvar set in the body would be
# invisible to the telemetry wrapper.
_LAST_BRIEF = {"brief_version": None, "error_category": None}


def _set_brief(brief_version, error_category):
    _LAST_BRIEF["brief_version"] = brief_version
    _LAST_BRIEF["error_category"] = error_category


_AUTH_401_MARKERS = (
    "401", "unauthorized", "invalid_grant", "invalid_client",
    "could not deserialize key data", "no key could be detected",
    "was not in the expected format", "invalid jwt", "malformed",
    "unable to load pem file",
)
_AUTH_403_MARKERS = ("403", "permissiondenied", "permission denied", "forbidden",
                     "insufficient permission", "does not have sufficient permission")


def _api_error_text(e, operation):
    """S3 hook for the API tools' except blocks: user-fixable auth failures get
    a versioned two-audience brief; every other error keeps the legacy text
    byte-for-byte (built by the caller).  Returns brief text or None."""
    try:
        err = str(e)
        low = err.lower()
        if any(m in low for m in _AUTH_403_MARKERS):
            _set_brief(BRIEF_403_PROPERTY, "IAMError")
            return _guided_error(
                f"Google returned 403 while {operation} — the service account has NO ACCESS "
                f"to property '{GSC_SITE_URL}'.",
                [
                    "In Search Console (search.google.com/search-console) > Settings > "
                    "Users and permissions, add the service account's email (the client_email "
                    "field inside the JSON key file) as a user — 'Full' permission is enough "
                    "for read queries.",
                    "Double-check GSC_SITE_URL matches the property EXACTLY — "
                    "'https://example.com/' and 'sc-domain:example.com' are DIFFERENT properties.",
                    "Then retry — or call setup_gsc_access to verify in-chat if this client "
                    "supports interactive prompts.",
                ],
            ) + f"  [Original error: {err[:200]}]"
        if any(m in low for m in _AUTH_401_MARKERS):
            _set_brief(BRIEF_401_INVALID, "AuthError")
            return _guided_error(
                "Google rejected the credentials — the JSON key at "
                "GOOGLE_APPLICATION_CREDENTIALS is malformed, revoked, or not a "
                "service-account key.",
                [
                    "In Google Cloud Console > IAM & Admin > Service Accounts > Keys, create a "
                    "fresh JSON key and download it.",
                    "Point GOOGLE_APPLICATION_CREDENTIALS at the new file's absolute path and "
                    "restart the client — or call setup_gsc_access to swap it in-chat if this "
                    "client supports interactive prompts.",
                ],
            ) + f"  [Original error: {err[:200]}]"
    except Exception:
        pass
    return None
