import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load(filename, module_name):
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "bin" / f"{filename}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hs = load("harness_select", "harness_select_native")
hu = load("harness_update", "harness_update_native")
AGENTS = ("kit-implementer", "kit-verifier", "phase-reviewer", "repo-explorer")


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def fixture(root):
    write(root / ".codex-plugin" / "plugin.json", json.dumps({
        "name": "polytropos", "version": "1.0.0", "skills": "./codex/skills/"
    }))
    write(root / ".agents" / "plugins" / "marketplace.json", json.dumps({
        "plugins": [{"name": "polytropos", "source": {"source": "local", "path": "./"}}]
    }))
    for name in AGENTS:
        write(root / "codex" / "agents" / f"{name}.toml",
              f'name = "{name}"\ndescription = "fixture"\ndeveloper_instructions = "fixture"\n')
    write(root / "codex" / "skills" / "route" / "SKILL.md", "root {{POLYTROPOS_ROOT}}\n")
    write(root / "codex" / "prompts" / "route.md", "root {{POLYTROPOS_ROOT}}\n")
    write(root / "codex" / "AGENTS.md", "root {{POLYTROPOS_ROOT}}\n")
    return root


class NativeDefaultTests(unittest.TestCase):
    def test_no_flags_codex_cli_dispatches_to_native_planner(self):
        args = hs.build_parser().parse_args(["install", "--harness", "codex"])
        fake = {
            "version": 1, "bundle_version": "1", "repo_root": "/repo",
            "codex_home": "/home", "agent_scope": "project",
            "components": ["plugin", "agents"], "actions": [],
            "package_readiness": {"state": "ready", "reason": "fixture"},
            "activation": {"state": "unknown", "reason": "fixture"},
        }
        with mock.patch.object(hs, "plan_codex_setup", return_value=fake) as planner, \
             mock.patch.object(hs, "apply_codex_plan") as apply, \
             mock.patch.object(hs.Path, "home", return_value=Path("/explicit-fake-home")), \
             contextlib.redirect_stdout(io.StringIO()):
            hs.cmd_install(args)
        self.assertEqual(planner.call_args.kwargs["components"], ("plugin", "agents"))
        apply.assert_called_once_with(fake)

    def test_legacy_mode_requires_explicit_components(self):
        with self.assertRaisesRegex(SystemExit, "requires explicit --components"):
            hs.main(["install", "--harness", "codex", "--legacy-copy"])

    def test_legacy_helper_preserves_differing_prompt(self):
        with tempfile.TemporaryDirectory() as repo_s, tempfile.TemporaryDirectory() as home_s:
            repo, home = fixture(Path(repo_s)), Path(home_s)
            destination = home / "prompts" / "route.md"
            write(destination, "personal prompt\n")
            results = hs.install_codex(home, repo_root=repo)
            self.assertIn((destination, "skip-differs"), results)
            self.assertEqual(destination.read_text(), "personal prompt\n")

    def test_default_install_and_empty_home_update_create_no_legacy_surfaces(self):
        with tempfile.TemporaryDirectory() as repo_s, tempfile.TemporaryDirectory() as home_s:
            repo, home = fixture(Path(repo_s)), Path(home_s)
            plan = hs.plan_codex_setup(repo, home)
            hs.apply_codex_plan(plan)
            self.assertFalse((home / "prompts").exists())
            self.assertFalse((home / "skills").exists())
            self.assertFalse((home / "AGENTS.md").exists())

            result = hu.apply_codex_target(repo, home)
            self.assertEqual(result["action"], "updated")
            self.assertFalse((home / "prompts").exists())
            self.assertFalse((home / "skills").exists())
            self.assertFalse((home / "AGENTS.md").exists())

    def test_update_refreshes_owned_copy_and_preserves_edited_unowned_copy(self):
        with tempfile.TemporaryDirectory() as repo_s, tempfile.TemporaryDirectory() as home_s:
            repo, home = fixture(Path(repo_s)), Path(home_s)
            legacy = hs.plan_codex_setup(repo, home, components=("prompts",),
                                         legacy_copy=True)
            hs.apply_codex_plan(legacy)
            source = repo / "codex" / "prompts" / "route.md"
            source.write_text("updated {{POLYTROPOS_ROOT}}\n")
            hu.apply_codex_target(repo, home)
            self.assertEqual((home / "prompts" / "route.md").read_text(),
                             f"updated {repo.resolve()}\n")

            destination = home / "prompts" / "route.md"
            destination.write_text("user edit\n")
            hu.apply_codex_target(repo, home)
            self.assertEqual(destination.read_text(), "user edit\n")

    def test_component_apply_preserves_unselected_records_and_manifest_metadata(self):
        with tempfile.TemporaryDirectory() as repo_s, tempfile.TemporaryDirectory() as home_s:
            repo, home = fixture(Path(repo_s)), Path(home_s)
            legacy = hs.plan_codex_setup(repo, home, components=("prompts",), legacy_copy=True)
            hs.apply_codex_plan(legacy)
            manifest_path = home / hs.OWNERSHIP_RELATIVE
            manifest = json.loads(manifest_path.read_text())
            manifest["retired"] = {"prompts": ["old.md"]}
            manifest_path.write_text(json.dumps(manifest))

            agents = hs.plan_codex_setup(repo, home, components=("agents",), agent_scope="user")
            hs.apply_codex_plan(agents)
            merged = json.loads(manifest_path.read_text())
            self.assertEqual(merged["retired"], {"prompts": ["old.md"]})
            self.assertTrue(any(item["component"] == "prompts" for item in merged["files"]))
            self.assertTrue(any(item["component"] == "agents" for item in merged["files"]))

    def test_update_dry_run_is_byte_read_only_and_absent_home_is_noninstalling(self):
        with tempfile.TemporaryDirectory() as repo_s, tempfile.TemporaryDirectory() as parent_s:
            repo = fixture(Path(repo_s))
            home = Path(parent_s) / "missing"
            result = hu.apply_codex_target(repo, home, dry_run=True)
            self.assertEqual(result["action"], "not installed")
            self.assertFalse(home.exists())

            existing = Path(parent_s) / "existing"
            existing.mkdir()
            write(existing / "prompts" / "route.md", "personal prompt\n")
            before = {
                path: (path.read_bytes(), path.stat().st_mtime_ns)
                for path in existing.rglob("*") if path.is_file()
            }
            result = hu.apply_codex_target(repo, existing, dry_run=True)
            self.assertEqual(result["action"], "would-update")
            self.assertEqual(before, {
                path: (path.read_bytes(), path.stat().st_mtime_ns)
                for path in existing.rglob("*") if path.is_file()
            })


if __name__ == "__main__":
    unittest.main()
