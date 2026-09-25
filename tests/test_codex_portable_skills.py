"""Focused packaging checks for Codex-native portable skill ports."""

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_ROOT = REPO_ROOT / "codex" / "skills"


class PortableSkillTests(unittest.TestCase):
    def test_every_claude_workflow_has_a_codex_entry_or_native_equivalent(self):
        claude = {path.parent.name for path in (REPO_ROOT / "skills").glob("*/SKILL.md")}
        codex = {path.parent.name for path in SKILLS_ROOT.glob("*/SKILL.md")}
        native_names = {"cost-report": "usage", "fable-check": "frontier-check"}
        self.assertEqual(len(claude), 15)
        self.assertTrue({native_names.get(name, name) for name in claude}.issubset(codex))

    def test_each_port_has_required_files_and_codex_root(self):
        for name in ("assess-improvement", "graphify"):
            with self.subTest(skill=name):
                root = SKILLS_ROOT / name
                card = (root / "SKILL.md").read_text()
                metadata = (root / "agents" / "openai.yaml").read_text()
                self.assertIn(f"name: {name}", card)
                self.assertIn("{{POLYTROPOS_ROOT}}", card)
                self.assertIn(f"${name}", metadata)

    def test_assessment_template_is_linked_and_packaged(self):
        root = SKILLS_ROOT / "assess-improvement"
        card = (root / "SKILL.md").read_text()
        template = root / "references" / "assessment-template.md"
        self.assertIn("references/assessment-template.md", card)
        self.assertTrue(template.is_file())
        self.assertIn("Evidence ledger", template.read_text())

    def test_graphify_preserves_offline_and_freshness_boundaries(self):
        card = (SKILLS_ROOT / "graphify" / "SKILL.md").read_text()
        for required in (
            "command -v graphify",
            "--no-label --no-viz",
            "graph_ground.py",
            "graph_brief.py",
            "unknown",
            "Never commit",
        ):
            with self.subTest(required=required):
                self.assertIn(required, card)
        self.assertNotIn("CLAUDE_PLUGIN_ROOT", card)


if __name__ == "__main__":
    unittest.main()
