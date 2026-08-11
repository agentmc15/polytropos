import importlib.util
import contextlib
import io
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "bin" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


recall = _load("memory_recall")
store = _load("memory_store")


class MemorySkillTests(unittest.TestCase):
    def test_commands_match_real_parsers(self):
        with tempfile.TemporaryDirectory() as memory_s, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(recall.main(["--demo"]), 0)
            self.assertEqual(
                store.main(
                    ["review", "--memory-dir", memory_s, "--now", "2026-08-11"]
                ),
                0,
            )

    def test_pull_only_privacy_and_honesty_contract(self):
        text = (ROOT / "codex" / "skills" / "memory" / "SKILL.md").read_text()
        flat = " ".join(text.split())
        for phrase in (
            "pull-only",
            "budget-capped winners",
            "Never dump or bulk-read",
            "source, confidence",
            "expiry, contradiction, and staleness",
            "explicit `--memory-dir`",
            "no automatic write",
            "background watcher",
        ):
            self.assertIn(phrase, flat)

    def test_no_implicit_home_network_harness_or_pricing_behavior(self):
        text = (ROOT / "codex" / "skills" / "memory" / "SKILL.md").read_text()
        for rejected in ("Path.home", "subprocess", "urlopen", "codex exec", "pricing.json"):
            self.assertNotIn(rejected, text)
        self.assertIn('POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"', text)
        self.assertNotIn("/Users/", text)


if __name__ == "__main__":
    unittest.main()
