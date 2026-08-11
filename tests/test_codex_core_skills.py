import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "bin" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


executor = _load("codex_execute")
selector = _load("harness_select")


class CoreSkillTests(unittest.TestCase):
    def test_execute_uses_real_driver_modes_and_safe_contract(self):
        text = (ROOT / "codex" / "skills" / "execute" / "SKILL.md").read_text()
        parser = executor.build_parser()
        parser.parse_args(["status", "--kit", "tasks/kits/example"])
        parser.parse_args(["run", "--kit", "tasks/kits/example", "--dry-run"])
        parser.parse_args(["run", "--kit", "tasks/kits/example", "--task", "T1"])
        parser.parse_args(["review", "--kit", "tasks/kits/example", "--phase", "1"])
        for token in ("status --kit", "run --kit", "review --kit", "--dry-run"):
            self.assertIn(token, text)
        self.assertIn("tasks/kits/<slug>", text)
        self.assertIn("pending | in-progress | done | blocked", text)
        self.assertIn("spends subscription usage", text)
        self.assertIn("verify command independently", text)
        self.assertNotIn(".Codex/kits", text)
        self.assertNotIn(".claude/kits", text)

    def test_execute_names_optional_agents_without_claiming_plugin_installs_them(self):
        text = (ROOT / "codex" / "skills" / "execute" / "SKILL.md").read_text()
        for name in ("kit-implementer", "kit-verifier", "phase-reviewer"):
            self.assertIn(name, text)
        self.assertIn("Plugin install does not install those agents", text.replace("\n", " "))
        self.assertIn("headless driver remains", text)

    def test_doctor_commands_parse_and_require_authority_for_writes(self):
        text = (ROOT / "codex" / "skills" / "doctor" / "SKILL.md").read_text()
        parser = selector.build_parser()
        parser.parse_args(
            [
                "doctor", "--harness", "codex", "--repo-root", "/tmp/repo",
                "--codex-home", "/tmp/home", "--json",
            ]
        )
        parser.parse_args(
            [
                "install", "--harness", "codex", "--repo-root", "/tmp/repo",
                "--codex-home", "/tmp/home", "--components", "plugin,agents",
                "--dry-run",
            ]
        )
        self.assertIn("read-only doctor", text)
        self.assertIn("explicit user", text)
        self.assertIn("--refresh-managed", text)
        self.assertNotIn("config.toml`.", text.replace("overwriting config.toml`.", ""))

    def test_plugin_and_installer_discover_final_skills_including_core_pair(self):
        skills = sorted(path.parent.name for path in (ROOT / "codex" / "skills").glob("*/SKILL.md"))
        self.assertEqual(len(skills), 12)
        self.assertTrue({"execute", "doctor"}.issubset(skills))
        manifest = (ROOT / ".codex-plugin" / "plugin.json").read_text()
        self.assertIn('"skills": "./codex/skills/"', manifest)
        with self.subTest("installer inventory"):
            inventory = selector._source_inventory(
                ROOT, Path("/tmp/codex-core-skills-home"), ("skills",), "user"
            )
            self.assertEqual(
                {source.parent.name for _, source, _ in inventory}, set(skills)
            )

    def test_new_skills_use_portable_unpinned_root_contract(self):
        for stem in ("execute", "doctor"):
            text = (ROOT / "codex" / "skills" / stem / "SKILL.md").read_text()
            self.assertIn('POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"', text)
            self.assertIn("harness_select.py doctor --harness codex", text)
            frontmatter = text.split("---", 2)[1]
            self.assertNotIn("model:", frontmatter)
            self.assertNotIn("/Users/", text)


if __name__ == "__main__":
    unittest.main()
