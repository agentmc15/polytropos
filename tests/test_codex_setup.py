import contextlib
import importlib.util
import inspect
import io
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("harness_select_setup", ROOT / "bin" / "harness_select.py")
hs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hs)


AGENTS = ("kit-implementer", "kit-verifier", "phase-reviewer", "repo-explorer")


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fake_repo(root):
    manifest = {
        "name": "polytropos",
        "version": "1.2.3",
        "skills": "./codex/skills/",
    }
    marketplace = {
        "plugins": [
            {"name": "polytropos", "source": {"source": "local", "path": "./"}}
        ]
    }
    _write(root / ".codex-plugin" / "plugin.json", json.dumps(manifest))
    _write(root / ".agents" / "plugins" / "marketplace.json", json.dumps(marketplace))
    for name in AGENTS:
        _write(
            root / "codex" / "agents" / f"{name}.toml",
            f'name = "{name}"\n'
            f'description = "Fixture for {name}"\n'
            'developer_instructions = """Use tasks/kits/<slug>. '
            'States: pending | in-progress | done | blocked."""\n',
        )
    _write(
        root / "codex" / "skills" / "route" / "SKILL.md",
        "Repo: {{POLYTROPOS_ROOT}}\nEngine: {{POLYTROPOS_ROOT}}/bin/codex_pricing.py\n",
    )
    _write(
        root / "codex" / "prompts" / "route.md",
        "Repo: {{POLYTROPOS_ROOT}}\n",
    )
    _write(root / "codex" / "AGENTS.md", "Repo: {{POLYTROPOS_ROOT}}\n")
    return root


def _snapshot(root):
    if not root.exists():
        return []
    return [
        (path.relative_to(root).as_posix(), path.read_bytes())
        for path in sorted(path for path in root.rglob("*") if path.is_file())
    ]


class ComponentParserTests(unittest.TestCase):
    def test_defaults_and_canonical_order(self):
        self.assertEqual(hs.parse_codex_components(None), ("plugin", "agents"))
        self.assertEqual(
            hs.parse_codex_components("guidance,plugin,skills"),
            ("plugin", "skills", "guidance"),
        )

    def test_unknown_duplicate_and_empty_values_rejected(self):
        for raw in ("plugin,plugin", "plugin,mystery", "plugin,", ""):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                hs.parse_codex_components(raw)


class PlanningTests(unittest.TestCase):
    def test_plugin_ready_and_agent_scopes(self):
        with tempfile.TemporaryDirectory() as root_s, tempfile.TemporaryDirectory() as home_s:
            root, home = _fake_repo(Path(root_s)), Path(home_s)
            project = hs.plan_codex_setup(root, home)
            self.assertEqual(project["actions"][0]["component"], "plugin")
            self.assertEqual(project["actions"][0]["state"], "up-to-date")
            agent_destinations = [
                action["destination"]
                for action in project["actions"]
                if action["component"] == "agents"
            ]
            self.assertTrue(all("/.codex/agents/" in value for value in agent_destinations))

            user = hs.plan_codex_setup(root, home, components=("agents",), agent_scope="user")
            self.assertTrue(
                all(
                    str(home / "agents") in action["destination"]
                    for action in user["actions"]
                )
            )

    def test_copy_components_require_explicit_legacy_mode(self):
        with tempfile.TemporaryDirectory() as root_s, tempfile.TemporaryDirectory() as home_s:
            root = _fake_repo(Path(root_s))
            with self.assertRaisesRegex(ValueError, "legacy-copy"):
                hs.plan_codex_setup(root, Path(home_s), components=("skills",))

    def test_malformed_or_escaping_plugin_is_conflict(self):
        with tempfile.TemporaryDirectory() as root_s, tempfile.TemporaryDirectory() as home_s:
            root = _fake_repo(Path(root_s))
            manifest_path = root / ".codex-plugin" / "plugin.json"
            payload = json.loads(manifest_path.read_text())
            payload["skills"] = "./../escape"
            manifest_path.write_text(json.dumps(payload))
            plan = hs.plan_codex_setup(root, Path(home_s), components=("plugin",))
            self.assertEqual(plan["actions"][0]["state"], "conflict")

    def test_dry_planning_and_doctor_are_byte_read_only(self):
        with tempfile.TemporaryDirectory() as root_s, tempfile.TemporaryDirectory() as home_s:
            root, home = _fake_repo(Path(root_s)), Path(home_s)
            before_root, before_home = _snapshot(root), _snapshot(home)
            hs.plan_codex_setup(root, home)
            hs.doctor_codex(root, home)
            self.assertEqual(_snapshot(root), before_root)
            self.assertEqual(_snapshot(home), before_home)


class ManagedInstallTests(unittest.TestCase):
    def test_clean_install_idempotence_and_minimal_ownership(self):
        with tempfile.TemporaryDirectory() as root_s, tempfile.TemporaryDirectory() as home_s:
            root, home = _fake_repo(Path(root_s)), Path(home_s)
            plan = hs.plan_codex_setup(root, home, components=("agents",), agent_scope="user")
            hs.apply_codex_plan(plan)
            second = hs.plan_codex_setup(root, home, components=("agents",), agent_scope="user")
            self.assertEqual({action["state"] for action in second["actions"]}, {"up-to-date"})

            ownership = json.loads((home / hs.OWNERSHIP_RELATIVE).read_text())
            self.assertEqual(ownership["version"], hs.OWNERSHIP_VERSION)
            self.assertEqual(len(ownership["files"]), len(AGENTS))
            raw = json.dumps(ownership)
            self.assertNotIn("developer_instructions", raw)
            self.assertNotIn(str(root), raw)

    def test_managed_refresh_and_user_edit_conflict(self):
        with tempfile.TemporaryDirectory() as root_s, tempfile.TemporaryDirectory() as home_s:
            root, home = _fake_repo(Path(root_s)), Path(home_s)
            initial = hs.plan_codex_setup(root, home, components=("agents",), agent_scope="user")
            hs.apply_codex_plan(initial)
            source = root / "codex" / "agents" / "kit-implementer.toml"
            source.write_text(source.read_text() + "# refreshed\n")

            stale = hs.plan_codex_setup(root, home, components=("agents",), agent_scope="user")
            implementer = next(action for action in stale["actions"] if "kit-implementer" in action["destination"])
            self.assertEqual(implementer["state"], "unmanaged")
            refresh = hs.plan_codex_setup(
                root,
                home,
                components=("agents",),
                agent_scope="user",
                refresh_managed=True,
            )
            implementer = next(action for action in refresh["actions"] if "kit-implementer" in action["destination"])
            self.assertEqual(implementer["state"], "managed-update")

            destination = home / "agents" / "kit-verifier.toml"
            destination.write_text(destination.read_text() + "# user edit\n")
            conflicted = hs.plan_codex_setup(
                root,
                home,
                components=("agents",),
                agent_scope="user",
                refresh_managed=True,
            )
            verifier = next(action for action in conflicted["actions"] if "kit-verifier" in action["destination"])
            self.assertEqual(verifier["state"], "conflict")
            self.assertIn("preserving", verifier["reason"])

    def test_recognized_legacy_copy_can_be_adopted(self):
        with tempfile.TemporaryDirectory() as root_s, tempfile.TemporaryDirectory() as home_s:
            root, home = _fake_repo(Path(root_s)), Path(home_s)
            old_root = "/Users/example/old/polytropos"
            destination = home / "skills" / "route" / "SKILL.md"
            _write(
                destination,
                (root / "codex" / "skills" / "route" / "SKILL.md")
                .read_text()
                .replace(hs.PLACEHOLDER, old_root),
            )
            plan = hs.plan_codex_setup(
                root,
                home,
                components=("skills",),
                legacy_copy=True,
                refresh_managed=True,
            )
            self.assertEqual(plan["actions"][0]["state"], "managed-update")
            self.assertIn("legacy", plan["actions"][0]["reason"])

    def test_atomic_failure_restores_files_and_prior_manifest(self):
        with tempfile.TemporaryDirectory() as root_s, tempfile.TemporaryDirectory() as home_s:
            root, home = _fake_repo(Path(root_s)), Path(home_s)
            (home / "agents").mkdir()
            prior_manifest = b'{"version": 1, "files": []}\n'
            _write(home / hs.OWNERSHIP_RELATIVE, prior_manifest.decode())
            before = _snapshot(home)
            plan = hs.plan_codex_setup(root, home, components=("agents",), agent_scope="user")
            with self.assertRaisesRegex(RuntimeError, "simulated"):
                hs.apply_codex_plan(plan, fail_after=2)
            self.assertEqual(_snapshot(home), before)
            self.assertEqual((home / hs.OWNERSHIP_RELATIVE).read_bytes(), prior_manifest)


class RenderingAndCliTests(unittest.TestCase):
    def test_json_is_stable_and_excludes_contents(self):
        with tempfile.TemporaryDirectory() as root_s, tempfile.TemporaryDirectory() as home_s:
            plan = hs.plan_codex_setup(_fake_repo(Path(root_s)), Path(home_s))
            first = hs.render_codex_plan(plan, as_json=True)
            self.assertEqual(first, hs.render_codex_plan(plan, as_json=True))
            self.assertNotIn("_content", first)
            self.assertNotIn("developer_instructions", first)

    def test_cli_rejects_invalid_cross_harness_and_refresh_combinations(self):
        with self.assertRaisesRegex(SystemExit, "only with --harness codex"):
            hs.main(["install", "--harness", "copilot", "--components", "plugin"])
        with self.assertRaisesRegex(SystemExit, "explicit --codex-home"):
            hs.main(["install", "--harness", "codex", "--refresh-managed"])

    def test_modern_cli_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as root_s, tempfile.TemporaryDirectory() as parent_s:
            root = _fake_repo(Path(root_s))
            home = Path(parent_s) / "missing-home"
            with contextlib.redirect_stdout(io.StringIO()):
                hs.main(
                    [
                        "install", "--harness", "codex", "--repo-root", str(root),
                        "--codex-home", str(home), "--components", "plugin,agents",
                        "--agent-scope", "user", "--dry-run", "--json",
                    ]
                )
            self.assertFalse(home.exists())

    def test_pure_seams_do_not_resolve_real_home_or_launch_commands(self):
        source = inspect.getsource(hs.plan_codex_setup) + inspect.getsource(hs.doctor_codex)
        self.assertNotIn("Path.home", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("urlopen", source)


if __name__ == "__main__":
    unittest.main()
