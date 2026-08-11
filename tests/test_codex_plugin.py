import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / ".codex-plugin" / "plugin.json"
MARKETPLACE_PATH = ROOT / ".agents" / "plugins" / "marketplace.json"


class CodexPluginTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        self.marketplace = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))

    def test_manifest_identifies_skills_only_plugin(self):
        self.assertEqual(self.manifest["name"], "polytropos")
        self.assertRegex(self.manifest["version"], r"^\d+\.\d+\.\d+$")
        self.assertTrue(self.manifest["description"].strip())
        self.assertEqual(self.manifest["author"]["name"], "agentmc15")
        self.assertEqual(self.manifest["license"], "MIT")
        self.assertEqual(self.manifest["skills"], "./codex/skills/")
        for undeclared in ("agents", "apps", "hooks", "mcpServers"):
            self.assertNotIn(undeclared, self.manifest)

    def test_declared_paths_are_relative_contained_and_present(self):
        for raw_path in (self.manifest["skills"],):
            self.assertTrue(raw_path.startswith("./"))
            resolved = (ROOT / raw_path).resolve()
            self.assertTrue(resolved.is_relative_to(ROOT.resolve()))
            self.assertTrue(resolved.exists())

        plugin = self.marketplace["plugins"][0]
        raw_path = plugin["source"]["path"]
        self.assertTrue(raw_path.startswith("./"))
        marketplace_root = ROOT
        resolved = (marketplace_root / raw_path).resolve()
        self.assertTrue(resolved.is_relative_to(ROOT.resolve()))
        self.assertEqual(resolved, ROOT.resolve())
        self.assertTrue((resolved / ".codex-plugin" / "plugin.json").is_file())

    def test_marketplace_exposes_one_local_plugin(self):
        self.assertEqual(self.marketplace["name"], "polytropos-local")
        self.assertTrue(self.marketplace["interface"]["displayName"])
        self.assertEqual(len(self.marketplace["plugins"]), 1)
        plugin = self.marketplace["plugins"][0]
        self.assertEqual(plugin["name"], self.manifest["name"])
        self.assertTrue(plugin["description"].strip())
        self.assertEqual(plugin["source"], {"source": "local", "path": "./"})

    def test_codex_metadata_does_not_reference_other_harness_pricing(self):
        payload = MANIFEST_PATH.read_text(encoding="utf-8") + MARKETPLACE_PATH.read_text(
            encoding="utf-8"
        )
        self.assertNotIn("pricing.json", payload)
        self.assertNotIn("pricing.copilot.json", payload)
        self.assertIsNone(re.search(r"claude|copilot", payload, re.IGNORECASE))

    def test_claude_metadata_remains_separate_and_parseable(self):
        claude_manifest = json.loads(
            (ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        claude_marketplace = json.loads(
            (ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
        )
        self.assertEqual(claude_manifest["name"], "polytropos")
        self.assertIsInstance(claude_marketplace["plugins"], list)
        self.assertNotIn("skills", claude_manifest)
        self.assertNotIn("interface", claude_manifest)


if __name__ == "__main__":
    unittest.main()
