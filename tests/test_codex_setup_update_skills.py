from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CodexSetupUpdateSkillTests(unittest.TestCase):
    def test_setup_uses_native_codex_status_line(self):
        text = (ROOT / "codex/skills/setup/SKILL.md").read_text()
        for field in (
            "model-with-reasoning",
            "estimated-thread-cost",
            "context-used",
            "five-hour-limit",
            "weekly-limit",
            "used-tokens",
        ):
            self.assertIn(field, text)
        self.assertIn("/statusline", text)
        self.assertIn("explicit confirmation", text)
        self.assertIn("Do not install or invoke the Claude-only `bin/statusline.py`", text)

    def test_update_is_check_first_and_no_implicit_apply(self):
        text = (ROOT / "codex/skills/update/SKILL.md").read_text()
        self.assertLess(text.index("harness_update.py\" check"), text.index("harness_update.py\" apply"))
        self.assertIn("only when the user explicitly requested a refresh", text)
        self.assertIn("--dry-run", text)
        self.assertIn("never writes `~/.claude`", text)
        self.assertIn("skip-differs", text)

    def test_managed_root_placeholder_is_present(self):
        for name in ("setup", "update"):
            text = (ROOT / f"codex/skills/{name}/SKILL.md").read_text()
            self.assertIn("{{POLYTROPOS_ROOT}}", text)


if __name__ == "__main__":
    unittest.main()
