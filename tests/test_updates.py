# SPDX-License-Identifier: MIT

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import gsc_mcp_server as server


def test_parse_version():
    assert server._parse_version("0.10.7") == (0, 10, 7)
    assert server._parse_version("v0.10.8") == (0, 10, 8)
    assert server._parse_version("0.10.8") > server._parse_version("0.10.7")
    assert server._parse_version("unknown") == (0,)


def test_check_server_update_outdated():
    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_cache = Path(tmp_dir) / "mcp_fleet_updates.json"
        with patch.object(server, "_FLEET_CACHE_FILE", fake_cache):
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({"info": {"version": "0.11.0"}}).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_resp.__exit__.return_value = False

            with patch("urllib.request.urlopen", return_value=mock_resp):
                res = server.check_server_update("google-search-console-mcp", "0.10.8", force_check=True)

            assert res["update_available"] is True
            assert res["current_version"] == "0.10.8"
            assert res["latest_version"] == "0.11.0"
            assert res["upgrade_command"] == "uvx --refresh google-search-console-mcp"
            assert "Inform the user to run 'uvx --refresh google-search-console-mcp' to update." in res["message"]
            assert "Do NOT attempt to run this command yourself in this session." in res["message"]


def test_check_server_update_up_to_date():
    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_cache = Path(tmp_dir) / "mcp_fleet_updates.json"
        with patch.object(server, "_FLEET_CACHE_FILE", fake_cache):
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({"info": {"version": "0.10.8"}}).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_resp.__exit__.return_value = False

            with patch("urllib.request.urlopen", return_value=mock_resp):
                res = server.check_server_update("google-search-console-mcp", "0.10.8", force_check=True)

            assert res["update_available"] is False
            assert res["upgrade_command"] is None
            assert res["message"] == "google-search-console-mcp is up to date (v0.10.8)."


def test_get_upgrade_nudge():
    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_cache = Path(tmp_dir) / "mcp_fleet_updates.json"
        fake_cache.write_text(json.dumps({
            "google-search-console-mcp": {
                "latest_version": "0.11.0",
                "last_checked": 9999999999.0,
                "last_nudged": 0,
            }
        }), encoding="utf-8")

        with patch.object(server, "_FLEET_CACHE_FILE", fake_cache):
            nudge = server.get_upgrade_nudge("google-search-console-mcp", "0.10.8")
            assert "NOTICE: An updated version of google-search-console-mcp is available (v0.11.0, current: v0.10.8)." in nudge
            assert "uvx --refresh google-search-console-mcp" in nudge
            assert "Do NOT attempt to run this command yourself in this session." in nudge

            # Throttled second call returns empty string
            second_nudge = server.get_upgrade_nudge("google-search-console-mcp", "0.10.8")
            assert second_nudge == ""


def test_check_for_updates_tool_registered():
    import asyncio
    res = asyncio.run(server.mcp.call_tool("check_for_updates", {}))
    assert not res.is_error
    content = json.loads(res.content[0].text)
    assert content["server"] == "google-search-console-mcp"
    assert "current_version" in content
    assert "update_available" in content
