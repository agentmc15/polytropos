"""Stdlib unittest regression suite for bin/harness_select.py.

bin/ is not a package; harness_select.py is loaded via importlib by absolute path
computed from this file's own location, per PLAN.md D2 (same convention as
tests/test_copilot_pricing.py and tests/test_cost_report.py).

SAFETY: every `install_copilot` / `main(["install", ...])` call in this file passes an
explicit home directory rooted under a `tempfile.TemporaryDirectory()`. Nothing here ever
reads or writes the real `~/.copilot` -- `Path.home()` is never invoked, and no test relies
on `$PWD` (paths are resolved via `Path(__file__).resolve()` per the repo's Desktop/desktop
case-quirk note in NOTES.md).
"""

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hs = _load("harness_select")


# Fake bundle content -- deliberately not real route.agent.md text, just something with the
# placeholder appearing twice plus surrounding text that must survive byte-identical.
FAKE_AGENT_TEXT = (
    "---\n"
    "name: route\n"
    "description: fake agent fixture for tests\n"
    "---\n"
    "\n"
    "Repo root is {{POLYTROPOS_ROOT}}.\n"
    "Pricing data lives at {{POLYTROPOS_ROOT}}/data/pricing.copilot.json.\n"
    "Nothing else here should change.\n"
)

# Fake skill content -- deliberately not the real lessons-loop SKILL.md text, just something
# with the placeholder appearing once plus surrounding text that must survive byte-identical.
FAKE_SKILL_TEXT = (
    "# lessons-loop (fake fixture)\n"
    "\n"
    "This skill lives under {{POLYTROPOS_ROOT}}/copilot/.github/skills/lessons-loop.\n"
    "Nothing else here should change.\n"
)


def _make_fake_repo_root(tmp_path, agent_text=FAKE_AGENT_TEXT, filename="route.agent.md"):
    """Build `<tmp_path>/copilot/.github/agents/<filename>` with `agent_text`."""
    agents_dir = tmp_path / "copilot" / ".github" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / filename).write_text(agent_text)
    return tmp_path


def _add_fake_skill(tmp_path, skill_text=FAKE_SKILL_TEXT, rel="lessons-loop/SKILL.md"):
    """Add `<tmp_path>/copilot/.github/skills/<rel>` with `skill_text` to an existing fake repo root."""
    skill_path = tmp_path / "copilot" / ".github" / "skills" / rel
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(skill_text)
    return tmp_path


class InstallCopilotPlaceholderTests(unittest.TestCase):
    def test_placeholder_replaced_both_occurrences_rest_identical(self):
        with tempfile.TemporaryDirectory() as tmp_root_s, tempfile.TemporaryDirectory() as tmp_home_s:
            tmp_root = _make_fake_repo_root(Path(tmp_root_s))
            tmp_home = Path(tmp_home_s)

            dest_paths = hs.install_copilot(tmp_home, repo_root=tmp_root)

            self.assertEqual(dest_paths, [tmp_home / "agents" / "route.agent.md"])
            written = (tmp_home / "agents" / "route.agent.md").read_text()
            expected = FAKE_AGENT_TEXT.replace(hs.PLACEHOLDER, str(tmp_root))
            self.assertEqual(written, expected)
            # Both occurrences replaced -- the placeholder must not survive at all.
            self.assertNotIn(hs.PLACEHOLDER, written)
            self.assertEqual(written.count(str(tmp_root)), 2)
            # Everything else byte-identical: same text minus only the placeholder swap.
            self.assertIn("name: route\n", written)
            self.assertIn("Nothing else here should change.\n", written)


class InstallCopilotDryRunTests(unittest.TestCase):
    def test_dry_run_returns_dest_list_but_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp_root_s, tempfile.TemporaryDirectory() as tmp_home_s:
            tmp_root = _make_fake_repo_root(Path(tmp_root_s))
            tmp_home = Path(tmp_home_s)

            dest_paths = hs.install_copilot(tmp_home, repo_root=tmp_root, dry_run=True)

            self.assertEqual(dest_paths, [tmp_home / "agents" / "route.agent.md"])
            # dry-run must create nothing: no agents/ dir, no file.
            self.assertFalse((tmp_home / "agents").exists())
            self.assertFalse((tmp_home / "agents" / "route.agent.md").exists())
            # The home dir itself (created by TemporaryDirectory) should have no children.
            self.assertEqual(list(tmp_home.iterdir()), [])


class InstallCopilotIdempotenceTests(unittest.TestCase):
    def test_install_twice_overwrites_not_appends(self):
        with tempfile.TemporaryDirectory() as tmp_root_s, tempfile.TemporaryDirectory() as tmp_home_s:
            tmp_root = _make_fake_repo_root(Path(tmp_root_s))
            tmp_home = Path(tmp_home_s)

            first_dest = hs.install_copilot(tmp_home, repo_root=tmp_root)
            first_text = (tmp_home / "agents" / "route.agent.md").read_text()

            second_dest = hs.install_copilot(tmp_home, repo_root=tmp_root)
            second_text = (tmp_home / "agents" / "route.agent.md").read_text()

            self.assertEqual(first_dest, second_dest)
            self.assertEqual(first_text, second_text)
            expected = FAKE_AGENT_TEXT.replace(hs.PLACEHOLDER, str(tmp_root))
            self.assertEqual(second_text, expected)
            # Not doubled/appended.
            self.assertEqual(second_text.count("name: route"), 1)


class InstallCopilotMissingBundleTests(unittest.TestCase):
    def test_missing_bundle_raises_filenotfounderror_naming_expected_path(self):
        with tempfile.TemporaryDirectory() as tmp_root_s, tempfile.TemporaryDirectory() as tmp_home_s:
            tmp_root = Path(tmp_root_s)  # empty -- no copilot/.github/agents at all
            tmp_home = Path(tmp_home_s)

            expected_bundle_path = tmp_root / "copilot" / ".github" / "agents"

            with self.assertRaises(FileNotFoundError) as ctx:
                hs.install_copilot(tmp_home, repo_root=tmp_root)

            self.assertIn(str(expected_bundle_path), str(ctx.exception))
            # And nothing was written.
            self.assertFalse((tmp_home / "agents").exists())

    def test_empty_bundle_dir_also_raises(self):
        with tempfile.TemporaryDirectory() as tmp_root_s, tempfile.TemporaryDirectory() as tmp_home_s:
            tmp_root = Path(tmp_root_s)
            agents_dir = tmp_root / "copilot" / ".github" / "agents"
            agents_dir.mkdir(parents=True)  # exists, but no *.agent.md files inside
            tmp_home = Path(tmp_home_s)

            with self.assertRaises(FileNotFoundError) as ctx:
                hs.install_copilot(tmp_home, repo_root=tmp_root)

            self.assertIn(str(agents_dir), str(ctx.exception))


class InstallCopilotSkillsTests(unittest.TestCase):
    def test_skills_install_resolves_placeholder_and_preserves_structure(self):
        with tempfile.TemporaryDirectory() as tmp_root_s, tempfile.TemporaryDirectory() as tmp_home_s:
            tmp_root = _make_fake_repo_root(Path(tmp_root_s))
            _add_fake_skill(tmp_root)
            tmp_home = Path(tmp_home_s)

            dest_paths = hs.install_copilot(tmp_home, repo_root=tmp_root)

            expected_skill_dest = tmp_home / "skills" / "lessons-loop" / "SKILL.md"
            self.assertIn(expected_skill_dest, dest_paths)
            self.assertTrue(expected_skill_dest.is_file())

            written = expected_skill_dest.read_text()
            expected = FAKE_SKILL_TEXT.replace(hs.PLACEHOLDER, str(tmp_root))
            self.assertEqual(written, expected)
            self.assertNotIn(hs.PLACEHOLDER, written)
            self.assertIn("Nothing else here should change.\n", written)

            # Agents still installed too.
            self.assertIn(tmp_home / "agents" / "route.agent.md", dest_paths)
            self.assertTrue((tmp_home / "agents" / "route.agent.md").is_file())


class InstallCopilotAgentsOnlyBackwardCompatTests(unittest.TestCase):
    def test_agents_only_bundle_with_no_skills_dir_installs_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp_root_s, tempfile.TemporaryDirectory() as tmp_home_s:
            tmp_root = _make_fake_repo_root(Path(tmp_root_s))  # no skills dir at all
            tmp_home = Path(tmp_home_s)

            skills_dir = tmp_root / "copilot" / ".github" / "skills"
            self.assertFalse(skills_dir.exists())

            dest_paths = hs.install_copilot(tmp_home, repo_root=tmp_root)

            self.assertEqual(dest_paths, [tmp_home / "agents" / "route.agent.md"])
            self.assertTrue((tmp_home / "agents" / "route.agent.md").is_file())
            # No skills/ dir should have been created.
            self.assertFalse((tmp_home / "skills").exists())


class InstallCopilotSkillsDryRunTests(unittest.TestCase):
    def test_dry_run_lists_skill_dests_but_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp_root_s, tempfile.TemporaryDirectory() as tmp_home_s:
            tmp_root = _make_fake_repo_root(Path(tmp_root_s))
            _add_fake_skill(tmp_root)
            tmp_home = Path(tmp_home_s)

            dest_paths = hs.install_copilot(tmp_home, repo_root=tmp_root, dry_run=True)

            expected_skill_dest = tmp_home / "skills" / "lessons-loop" / "SKILL.md"
            self.assertIn(expected_skill_dest, dest_paths)
            self.assertIn(tmp_home / "agents" / "route.agent.md", dest_paths)

            # dry-run must create nothing: no skills/ dir, no agents/ dir, no files.
            self.assertFalse((tmp_home / "skills").exists())
            self.assertFalse((tmp_home / "agents").exists())
            self.assertEqual(list(tmp_home.iterdir()), [])


class DetectTests(unittest.TestCase):
    def test_detect_key_and_boolean_combinations(self):
        combos = [
            ({"claude": "/usr/bin/claude", "copilot": "/usr/bin/copilot"},
             {"claude-code": True, "copilot": True, "codex": False}),
            ({}, {"claude-code": False, "copilot": False, "codex": False}),
            ({"claude": "/usr/bin/claude"}, {"claude-code": True, "copilot": False, "codex": False}),
            ({"copilot": "/opt/homebrew/bin/copilot"}, {"claude-code": False, "copilot": True, "codex": False}),
            ({"codex": "/usr/local/bin/codex"}, {"claude-code": False, "copilot": False, "codex": True}),
        ]
        for which_map, expected in combos:
            with self.subTest(which_map=which_map):
                def fake_which(name, _map=which_map):
                    return _map.get(name)

                with mock.patch.object(hs.shutil, "which", side_effect=fake_which):
                    result = hs.detect()

                self.assertEqual(set(result.keys()), {"claude-code", "copilot", "codex"})
                self.assertEqual(result, expected)


class ClaudeCodeInstallCliTests(unittest.TestCase):
    def test_claude_code_install_writes_nothing_and_prints_marketplace_message(self):
        with tempfile.TemporaryDirectory() as parent_s:
            # A fresh temp home that does NOT pre-exist, passed via --copilot-home. The
            # claude-code path must never touch it.
            tmp_home = Path(parent_s) / "untouched-copilot-home"
            self.assertFalse(tmp_home.exists())

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                hs.main(["install", "--harness", "claude-code", "--copilot-home", str(tmp_home)])

            output = buf.getvalue()
            self.assertIn("marketplace", output.lower())
            self.assertFalse(tmp_home.exists())


class LiveTreeGuardTests(unittest.TestCase):
    """Guards against someone accidentally committing a resolved (non-placeholder) bundle."""

    def test_real_bundle_has_route_agent_with_placeholder_intact(self):
        route_agent = hs.BUNDLE_AGENTS / "route.agent.md"
        self.assertTrue(route_agent.is_file(), f"expected {route_agent} to exist")
        text = route_agent.read_text()
        self.assertIn(hs.PLACEHOLDER, text)

    def test_real_lessons_loop_skill_has_no_absolute_path(self):
        skill_path = hs.BUNDLE_SKILLS / "lessons-loop" / "SKILL.md"
        self.assertTrue(skill_path.is_file(), f"expected {skill_path} to exist")
        text = skill_path.read_text()
        self.assertNotIn("/Users/", text)
        self.assertNotIn("/home/", text)


if __name__ == "__main__":
    unittest.main()
