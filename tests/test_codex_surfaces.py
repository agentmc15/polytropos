import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "sync_codex_surfaces", ROOT / "bin" / "sync_codex_surfaces.py"
)
syncer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(syncer)


def _fixture(root):
    shutil.copytree(ROOT / "codex", root / "codex")
    (root / "data").mkdir()
    (root / "data" / "pricing.codex.json").write_text("{}\n")
    (root / "bin").mkdir()
    engines = {
        "codex_pricing.py",
        "codex_execute.py",
        "codex_usage.py",
        "journal_collect.py",
        "journal_summarize.py",
        "journal_askpack.py",
        "journal_plan.py",
    }
    for engine in engines:
        (root / "bin" / engine).write_text("# fixture\n")
    return root


class RootResolutionTests(unittest.TestCase):
    def test_relocated_plugin_resolves_at_two_roots(self):
        for _ in range(2):
            with tempfile.TemporaryDirectory() as tmp_s:
                root = _fixture(Path(tmp_s) / "relocated")
                skill = root / "codex" / "skills" / "route" / "SKILL.md"
                self.assertEqual(
                    syncer.resolve_skill_root(skill, "codex_pricing.py"), root.resolve()
                )

    def test_managed_copy_uses_proven_installed_root(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            base = Path(tmp_s)
            root = _fixture(base / "repo")
            copied = base / "home" / "skills" / "route" / "SKILL.md"
            copied.parent.mkdir(parents=True)
            copied.write_text((root / "codex" / "skills" / "route" / "SKILL.md").read_text())
            self.assertEqual(
                syncer.resolve_skill_root(copied, "codex_pricing.py", root), root.resolve()
            )

    def test_stale_literal_and_missing_sentinels_fail_with_doctor(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            base = Path(tmp_s)
            root = _fixture(base / "repo")
            copied = base / "home" / "skills" / "route" / "SKILL.md"
            copied.parent.mkdir(parents=True)
            copied.write_text("fixture")
            for installed in (syncer.PLACEHOLDER, base / "missing"):
                with self.subTest(installed=installed), self.assertRaisesRegex(
                    RuntimeError, "harness_select.py doctor"
                ):
                    syncer.resolve_skill_root(copied, "codex_pricing.py", installed)
            (root / "bin" / "codex_pricing.py").unlink()
            with self.assertRaisesRegex(RuntimeError, "harness_select.py doctor"):
                syncer.resolve_skill_root(
                    root / "codex" / "skills" / "route" / "SKILL.md",
                    "codex_pricing.py",
                )


class CanonicalSkillTests(unittest.TestCase):
    def test_all_seven_share_root_contract_and_quote_commands(self):
        for stem in syncer.SKILL_STEMS:
            path = ROOT / "codex" / "skills" / stem / "SKILL.md"
            text = path.read_text()
            with self.subTest(stem=stem):
                self.assertIn("## Resolve the plugin root before running commands", text)
                self.assertIn('POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"', text)
                self.assertIn(syncer.DOCTOR_REMEDY, text)
                self.assertIn("Reject a literal placeholder", text)
                self.assertNotIn("python3 {{POLYTROPOS_ROOT}}", text)
                for line in text.splitlines():
                    if "python3 " in line and "$POLYTROPOS_ROOT/bin/" in line:
                        self.assertIn('python3 "$POLYTROPOS_ROOT/bin/', line)

    def test_no_cross_harness_or_model_id_leakage(self):
        model_ids = json.loads((ROOT / "data" / "pricing.codex.json").read_text())["models"]
        for stem in syncer.SKILL_STEMS:
            text = (ROOT / "codex" / "skills" / stem / "SKILL.md").read_text()
            self.assertNotIn("CLAUDE_PLUGIN_ROOT", text)
            self.assertNotIn("data/pricing.copilot.json", text)
            for model_id in model_ids:
                self.assertNotIn(model_id, text)


class PromptSyncTests(unittest.TestCase):
    def test_checked_in_prompts_are_current_and_deprecated(self):
        self.assertEqual(syncer.sync(ROOT, "check"), [])
        for path in (ROOT / "codex" / "prompts").glob("*.md"):
            self.assertIn("Deprecated compatibility prompt", path.read_text())

    def test_check_is_read_only_and_build_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            root = _fixture(Path(tmp_s) / "repo")
            route = root / "codex" / "prompts" / "route.md"
            route.write_text("drift\n")
            before = route.read_bytes()
            self.assertIn("route.md", syncer.sync(root, "check"))
            self.assertEqual(route.read_bytes(), before)
            syncer.sync(root, "build")
            first = {path.name: path.read_bytes() for path in (root / "codex" / "prompts").glob("*.md")}
            self.assertEqual(syncer.sync(root, "check"), [])
            syncer.sync(root, "build")
            second = {path.name: path.read_bytes() for path in (root / "codex" / "prompts").glob("*.md")}
            self.assertEqual(first, second)

    def test_unknown_prompt_and_malformed_source_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            root = _fixture(Path(tmp_s) / "repo")
            (root / "codex" / "prompts" / "unknown.md").write_text("unknown")
            with self.assertRaisesRegex(ValueError, "unknown"):
                syncer.sync(root, "check")
            (root / "codex" / "prompts" / "unknown.md").unlink()
            (root / "codex" / "skills" / "route" / "SKILL.md").write_text("no anchor")
            with self.assertRaisesRegex(ValueError, "frontmatter anchor"):
                syncer.sync(root, "check")


if __name__ == "__main__":
    unittest.main()
