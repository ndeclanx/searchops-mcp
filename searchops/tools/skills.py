# SPDX-License-Identifier: MIT

"""Skill (playbook) tools: list and read."""

from pathlib import Path

from gsc_telemetry import send_telemetry
from searchops import PACKAGE_ROOT
from searchops.instrument import instrument
from searchops.server import mcp, _ANNOTATIONS_READ_LOCAL

_SKILLS_DIR = PACKAGE_ROOT / "skills"


@mcp.tool(annotations=_ANNOTATIONS_READ_LOCAL)
@instrument
def skills_list():
    """
    List available analytical skills (playbooks) for Google Search Console.
    Use this to learn proven field combinations and how to interpret GSC data for specific SEO tasks. Fetch the full playbook with skill_read.
    """
    if not _SKILLS_DIR.exists():
        return {"skills": [], "message": "No skills directory found."}

    available_skills = []
    for md_file in _SKILLS_DIR.glob("*.md"):
        try:
            content = md_file.read_text()
            title = md_file.stem
            desc = ""
            for line in content.splitlines():
                if line.startswith("title:"): title = line.split(":", 1)[1].strip()
                if line.startswith("description:"): desc = line.split(":", 1)[1].strip()

            available_skills.append({
                "id": md_file.name,
                "title": title,
                "description": desc,
            })
        except Exception:
            pass

    return {"skills": available_skills}


@mcp.tool(annotations=_ANNOTATIONS_READ_LOCAL)
@instrument
def skill_read(skill_id: str):
    """
    Fetch the full content of one analytical skill (playbook) for Google Search Console.

    Args:
        skill_id: The skill id from skills_list (e.g., "brand_visibility.md")

    Returns:
        The full skill content with title, description, and playbook steps.
    """
    if not _SKILLS_DIR.exists():
        send_telemetry("skill_read", {"skill_name": skill_id, "fetch_ok": False})
        return {"error": "No skills directory found."}

    skill_file = (_SKILLS_DIR / skill_id).resolve()
    if not skill_file.is_relative_to(_SKILLS_DIR.resolve()):
        send_telemetry("skill_read", {"skill_name": skill_id, "fetch_ok": False})
        return {"error": f"Skill '{skill_id}' not found. Call skills_list to see available skills."}
    if not skill_file.exists() or not skill_file.is_file():
        send_telemetry("skill_read", {"skill_name": skill_id, "fetch_ok": False})
        return {"error": f"Skill '{skill_id}' not found. Call skills_list to see available skills."}

    try:
        content = skill_file.read_text()
        title = skill_file.stem
        desc = ""
        for line in content.splitlines():
            if line.startswith("title:"): title = line.split(":", 1)[1].strip()
            if line.startswith("description:"): desc = line.split(":", 1)[1].strip()
        send_telemetry("skill_read", {"skill_name": skill_file.name, "fetch_ok": True})
        return {"id": skill_file.name, "title": title, "description": desc, "content": content}
    except Exception as e:
        send_telemetry("skill_read", {"skill_name": skill_id, "fetch_ok": False})
        return {"error": f"Error reading skill: {str(e)}"}
