# SPDX-License-Identifier: MIT

"""Universal fleet update checker (async, non-blocking, 24h TTL, 7d re-nudge)."""

import json
import re
import time
import threading
import urllib.request
from pathlib import Path

_FLEET_CACHE_FILE = Path.home() / ".cache" / "mcp_fleet_updates.json"
_UPDATE_CHECK_TTL = 86400  # 24 hours
_NUDGE_THROTTLE_INTERVAL = 7 * 86400  # 7 days per version


def _parse_version(v: str) -> tuple[int, ...]:
    try:
        clean = re.sub(r"[^\d.]", "", v)
        parts = tuple(int(p) for p in clean.split(".") if p.isdigit())
        return parts if parts else (0,)
    except Exception:
        return (0,)


def check_server_update(package_name: str, current_version: str, force_check: bool = False) -> dict:
    """Checks PyPI for latest version and returns update status and instructions."""
    now = time.time()
    cache = {}
    if _FLEET_CACHE_FILE.exists():
        try:
            cache = json.loads(_FLEET_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    entry = cache.get(package_name, {})
    last_check = entry.get("last_checked", 0)
    latest_version = entry.get("latest_version", current_version)

    if force_check or (now - last_check > _UPDATE_CHECK_TTL):
        try:
            req = urllib.request.Request(
                f"https://pypi.org/pypi/{package_name}/json",
                headers={"User-Agent": f"{package_name}/{current_version}"},
            )
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                latest_version = data.get("info", {}).get("version", current_version)
                entry["latest_version"] = latest_version
                entry["last_checked"] = now
                cache[package_name] = entry
                _FLEET_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
                tmp = _FLEET_CACHE_FILE.with_suffix(".tmp")
                tmp.write_text(json.dumps(cache), encoding="utf-8")
                tmp.replace(_FLEET_CACHE_FILE)
        except Exception:
            pass

    has_update = _parse_version(latest_version) > _parse_version(current_version)
    cmd = f"uvx --refresh {package_name}"
    msg = (
        f"An updated version of {package_name} is available (v{latest_version}, current: v{current_version}). "
        f"Inform the user to run '{cmd}' to update. Do NOT attempt to run this command yourself in this session."
        if has_update
        else f"{package_name} is up to date (v{current_version})."
    )
    return {
        "server": package_name,
        "current_version": current_version,
        "latest_version": latest_version,
        "update_available": has_update,
        "upgrade_command": cmd if has_update else None,
        "message": msg,
    }


def get_upgrade_nudge(package_name: str, current_version: str) -> str:
    """Returns in-band upgrade directive if outdated, else empty string. Non-blocking."""
    try:
        now = time.time()
        cache = {}
        if _FLEET_CACHE_FILE.exists():
            try:
                cache = json.loads(_FLEET_CACHE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass

        entry = cache.get(package_name, {})
        last_check = entry.get("last_checked", 0)
        latest_version = entry.get("latest_version", current_version)
        last_nudged = entry.get("last_nudged", 0)

        if now - last_check > _UPDATE_CHECK_TTL:
            def _fetch():
                try:
                    req = urllib.request.Request(
                        f"https://pypi.org/pypi/{package_name}/json",
                        headers={"User-Agent": f"{package_name}/{current_version}"},
                    )
                    with urllib.request.urlopen(req, timeout=1.5) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        latest = data.get("info", {}).get("version", current_version)
                        _FLEET_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
                        cur = json.loads(_FLEET_CACHE_FILE.read_text(encoding="utf-8")) if _FLEET_CACHE_FILE.exists() else {}
                        cur[package_name] = {
                            "latest_version": latest,
                            "last_checked": time.time(),
                            "last_nudged": cur.get(package_name, {}).get("last_nudged", 0),
                        }
                        tmp = _FLEET_CACHE_FILE.with_suffix(".tmp")
                        tmp.write_text(json.dumps(cur), encoding="utf-8")
                        tmp.replace(_FLEET_CACHE_FILE)
                except Exception:
                    pass

            threading.Thread(target=_fetch, daemon=True).start()

        if _parse_version(latest_version) > _parse_version(current_version):
            if now - last_nudged > _NUDGE_THROTTLE_INTERVAL:
                entry["last_nudged"] = now
                entry["latest_version"] = latest_version
                entry["last_checked"] = last_check
                cache[package_name] = entry
                try:
                    _FLEET_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
                    tmp = _FLEET_CACHE_FILE.with_suffix(".tmp")
                    tmp.write_text(json.dumps(cache), encoding="utf-8")
                    tmp.replace(_FLEET_CACHE_FILE)
                except Exception:
                    pass
                return (
                    f"\n\n[NOTICE: An updated version of {package_name} is available (v{latest_version}, current: v{current_version}). "
                    f"Inform the user to run 'uvx --refresh {package_name}' to update. Do NOT attempt to run this command yourself in this session.]"
                )
    except Exception:
        pass
    return ""
