import re
import unittest
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover - supported fallback for old Python
    tomllib = None


ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "codex" / "agents"
EXPECTED = {
    "kit-implementer",
    "kit-verifier",
    "phase-reviewer",
    "repo-explorer",
}


class CodexAgentTests(unittest.TestCase):
    def test_exact_agent_roster_and_schema(self):
        files = sorted(AGENT_DIR.glob("*.toml"))
        self.assertEqual({path.stem for path in files}, EXPECTED)
        for path in files:
            raw = path.read_text(encoding="utf-8")
            if tomllib is not None:
                payload = tomllib.loads(raw)
                self.assertEqual(payload["name"], path.stem)
                self.assertTrue(payload["description"].strip())
                self.assertTrue(payload["developer_instructions"].strip())
                self.assertEqual(
                    set(payload), {"name", "description", "developer_instructions"}
                )
            else:
                self.assertRegex(raw, rf'^name = "{re.escape(path.stem)}"$', re.MULTILINE)
                self.assertIn('developer_instructions = """', raw)

    def test_agents_are_portable_and_unpinned(self):
        combined = "\n".join(
            path.read_text(encoding="utf-8") for path in AGENT_DIR.glob("*.toml")
        )
        rejected = (
            ".Codex/kits",
            ".claude/kits",
            "/path/to/polytropos",
            "CLAUDE_PLUGIN_ROOT",
            "model_reasoning_effort",
            "pricing.json",
        )
        for value in rejected:
            self.assertNotIn(value, combined)
        self.assertNotRegex(combined, r"(?m)^model\s*=")
        self.assertNotRegex(combined, r"\$\d+(?:\.\d+)?")
        self.assertNotRegex(combined, r"/(?:Users|home)/")

    def test_every_role_uses_current_generic_kit_contract(self):
        for path in AGENT_DIR.glob("*.toml"):
            raw = path.read_text(encoding="utf-8")
            self.assertIn("tasks/kits/<slug>", raw)
            self.assertIn("pending | in-progress | done | blocked", raw)

    def test_implementer_and_verifiers_have_required_boundaries(self):
        implementer = (AGENT_DIR / "kit-implementer.toml").read_text(encoding="utf-8")
        self.assertIn("exactly one", implementer.lower())
        self.assertIn("do not edit task status or NOTES.md", implementer)
        self.assertIn("verify command", implementer)
        self.assertIn("genuinely conflict", implementer)

        verifier = (AGENT_DIR / "kit-verifier.toml").read_text(encoding="utf-8")
        reviewer = (AGENT_DIR / "phase-reviewer.toml").read_text(encoding="utf-8")
        explorer = (AGENT_DIR / "repo-explorer.toml").read_text(encoding="utf-8")
        for raw in (verifier, reviewer, explorer):
            self.assertIn("read-only", raw)
        self.assertIn("Report PASS", verifier)
        self.assertIn("file-and-line evidence", verifier)
        self.assertIn("repository invariants", reviewer)
        self.assertIn("distinguish direct evidence from inference", explorer)


if __name__ == "__main__":
    unittest.main()
