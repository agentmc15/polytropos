import importlib.util
import re
import shlex
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = (ROOT / "README.md", ROOT / "SETUP.md", ROOT / "docs" / "CODEX-HARNESS.md")
SPEC = importlib.util.spec_from_file_location("harness_select_docs", ROOT / "bin" / "harness_select.py")
selector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(selector)


class CodexDocsTests(unittest.TestCase):
    def test_documented_setup_commands_parse_without_execution(self):
        parser = selector.build_parser()
        found = 0
        for path in DOCS:
            for line in path.read_text().splitlines():
                if not line.startswith("python3 bin/harness_select.py "):
                    continue
                found += 1
                argv = shlex.split(line)[2:]
                parser.parse_args(argv)
        self.assertGreaterEqual(found, 8)

    def test_documented_skill_and_agent_inventories_match_disk(self):
        guide = (ROOT / "docs" / "CODEX-HARNESS.md").read_text()
        skills = sorted(path.parent.name for path in (ROOT / "codex" / "skills").glob("*/SKILL.md"))
        agents = sorted(path.stem for path in (ROOT / "codex" / "agents").glob("*.toml"))
        self.assertEqual(len(skills), 12)
        self.assertEqual(len(agents), 4)
        for skill in skills:
            self.assertIn(f"`${skill}`", guide)
        for agent in agents:
            self.assertIn(f"`{agent}`", guide)

    def test_current_native_invocation_and_install_terms_are_present(self):
        guide = (ROOT / "docs" / "CODEX-HARNESS.md").read_text()
        for token in ("/plugins", "/skills", "/agent", "$route", "--refresh-managed", "--legacy-copy"):
            self.assertIn(token, guide)
        self.assertIn("installing the plugin does not install the agents", guide)
        self.assertIn("deprecated compatibility mirrors", guide)
        self.assertNotIn("Codex has no custom-agent files", guide)
        self.assertNotIn("Ask the `route` prompt", guide)

    def test_local_markdown_links_resolve(self):
        for path in DOCS:
            for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", path.read_text()):
                if target.startswith(("https://", "http://", "#")):
                    continue
                clean = target.split("#", 1)[0]
                self.assertTrue((path.parent / clean).resolve().exists(), f"{path}: {target}")

    def test_codex_guide_has_no_live_model_id_price_or_allowance(self):
        guide = (ROOT / "docs" / "CODEX-HARNESS.md").read_text()
        self.assertNotRegex(guide, r"gpt-[\w.-]+")
        self.assertNotRegex(guide, r"\$\d+(?:\.\d+)?")
        self.assertNotRegex(guide, r"\b\d+[kKmM]\s+(?:tokens|requests)\b")

    def test_follow_on_section_is_future_tense_and_statusline_is_native(self):
        guide = (ROOT / "docs" / "CODEX-HARNESS.md").read_text()
        section = guide.split("## Good next Codex additions", 1)[1]
        for phrase in ("repo-bench", "verify hook", "Automation templates", "Plugin icons", "context-fidelity"):
            self.assertIn(phrase, section)
        self.assertIn("built-in `/statusline`", section)
        self.assertIn("does not need to be ported", section)


if __name__ == "__main__":
    unittest.main()
