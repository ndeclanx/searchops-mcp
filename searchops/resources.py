# SPDX-License-Identifier: MIT

"""S5: skills mirrored as MCP resources (Protocol Surfaces v1).

Same content as skill_read (local packaged file), discoverable without a
tool call.  Pull-only: costs nothing until a client actually reads one.
"""

import sys

from gsc_telemetry import send_telemetry
from searchops import PACKAGE_ROOT
from searchops.server import mcp


def _register_skill_resources():
    try:
        skills_dir = PACKAGE_ROOT / "skills"
        if not skills_dir.exists():
            return
        for md_file in sorted(skills_dir.glob("*.md")):
            stem = md_file.stem
            uri = f"skill://{stem}"
            title, desc = stem, ""
            try:
                for line in md_file.read_text().splitlines():
                    if line.startswith("title:"):
                        title = line.split(":", 1)[1].strip()
                    if line.startswith("description:"):
                        desc = line.split(":", 1)[1].strip()
            except Exception:
                pass

            def _make_reader(path=md_file, resource_uri=uri):
                def _skill_resource():
                    content = path.read_text()
                    send_telemetry("resource_read", {"resource_uri": resource_uri})
                    return content
                _skill_resource.__name__ = f"skill_resource_{path.stem}"
                return _skill_resource

            mcp.resource(
                uri,
                name=f"skill-{stem}",
                title=title,
                description=desc or f"GSC analysis skill: {stem}",
                mime_type="text/markdown",
            )(_make_reader())
    except Exception as e:
        print(f"Warning: skill resources not registered: {e}", file=sys.stderr)


_register_skill_resources()
