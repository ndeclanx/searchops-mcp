# SPDX-License-Identifier: MIT

"""Tests for the Hermes site health diagnostic skill and prompt."""

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from pathlib import Path


class TestHermesSkillFile(unittest.TestCase):
    """Verify the skill file exists and has correct frontmatter."""

    def setUp(self):
        self.skill_path = Path(REPO_ROOT) / "skills" / "site_health_diagnostic.md"

    def test_skill_file_exists(self):
        self.assertTrue(self.skill_path.exists(), "site_health_diagnostic.md should exist")

    def test_has_title(self):
        content = self.skill_path.read_text()
        self.assertTrue(
            any(line.startswith("title:") for line in content.splitlines()),
            "Skill should have a title: frontmatter line",
        )

    def test_has_description(self):
        content = self.skill_path.read_text()
        self.assertTrue(
            any(line.startswith("description:") for line in content.splitlines()),
            "Skill should have a description: frontmatter line",
        )

    def test_references_key_tools(self):
        content = self.skill_path.read_text()
        # The Hermes skill should reference major analysis tools
        for tool in [
            "analyze_robots_txt",
            "parse_sitemap",
            "crawl_site",
            "audit_indexing",
            "find_search_opportunities",
            "detect_traffic_decay_tool",
            "detect_cannibalization_tool",
            "analyze_performance",
        ]:
            self.assertIn(tool, content, f"Skill should reference {tool}")

    def test_has_execution_phases(self):
        content = self.skill_path.read_text()
        self.assertIn("Phase 1", content)
        self.assertIn("Phase 2", content)
        self.assertIn("Phase 3", content)
        self.assertIn("Phase 4", content)
        self.assertIn("Phase 5", content)


class TestSkillDiscovery(unittest.TestCase):
    """Verify the skill is discoverable via skills_list."""

    def test_skill_appears_in_list(self):
        from searchops.tools.skills import skills_list
        result = skills_list.__wrapped__()
        skill_ids = [s["id"] for s in result["skills"]]
        self.assertIn("site_health_diagnostic.md", skill_ids)

    def test_skill_readable(self):
        from searchops.tools.skills import skill_read
        result = skill_read.__wrapped__("site_health_diagnostic.md")
        self.assertNotIn("error", result)
        self.assertEqual(result["id"], "site_health_diagnostic.md")
        self.assertIn("Hermes", result["title"])
        self.assertIn("content", result)


class TestHermesPrompt(unittest.TestCase):
    """Verify the workflow prompt is registered and produces correct output."""

    def test_prompt_function_exists(self):
        from searchops.prompts import site_health_diagnostic
        result = site_health_diagnostic()
        self.assertIn("site health diagnostic", result.lower())
        self.assertIn("skill_read", result)
        self.assertIn("site_health_diagnostic.md", result)

    def test_prompt_with_site_url(self):
        from searchops.prompts import site_health_diagnostic
        result = site_health_diagnostic(site_url="https://example.com")
        self.assertIn("https://example.com", result)

    def test_prompt_references_phases(self):
        from searchops.prompts import site_health_diagnostic
        result = site_health_diagnostic()
        self.assertIn("Phase 1", result)
        self.assertIn("Phase 2", result)
        self.assertIn("Phase 3", result)
        self.assertIn("Phase 4", result)
        self.assertIn("Phase 5", result)


if __name__ == "__main__":
    unittest.main()
