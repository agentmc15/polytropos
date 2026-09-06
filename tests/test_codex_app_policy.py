import importlib.util
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("codex_app_policy", ROOT / "bin/codex_app_policy.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)
harness_spec = importlib.util.spec_from_file_location("harness_select_app_policy", ROOT / "bin/harness_select.py")
harness = importlib.util.module_from_spec(harness_spec)
harness_spec.loader.exec_module(harness)


class AppPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.repo = base / "repo"
        self.home = base / "home"
        self.backup = base / "backup"
        (self.repo / "data").mkdir(parents=True)
        (self.repo / "codex/agents").mkdir(parents=True)
        (self.repo / "data/pricing.codex.json").write_bytes(
            (ROOT / "data/pricing.codex.json").read_bytes()
        )
        (self.repo / "bin").mkdir()
        (self.repo / "bin/codex_policy.py").write_bytes((ROOT / "bin/codex_policy.py").read_bytes())
        for source in (ROOT / "codex/agents").glob("*.toml"):
            (self.repo / "codex/agents" / source.name).write_bytes(source.read_bytes())
        self.runtime = base / "models.json"
        pricing = json.loads((self.repo / "data/pricing.codex.json").read_text())
        self.runtime.write_text(json.dumps({"data": [
            {"id": mid} for mid, info in pricing["models"].items()
            if info.get("available", True) and info.get("tier") in {"cheap", "mid", "strong", "frontier"}
        ]}))

    def tearDown(self):
        self.temp.cleanup()

    def plan(self, runtime=True):
        return app.plan_app_policy(
            self.repo, self.home, self.backup, self.runtime if runtime else None
        )

    def test_plan_preserves_unrelated_config_and_sets_central_models(self):
        self.home.mkdir()
        (self.home / "config.toml").write_text('model = "old"\ncustom = true\n[agents]\nmax_threads = 9\n')
        plan = self.plan()
        config = next(a for a in plan["actions"] if a["component"] == "config")
        desired = config["desired"].decode()
        self.assertIn("custom = true", desired)
        self.assertIn("max_threads = 9", desired)
        self.assertIn(f'model = "{plan["orchestrator_model"]}"', desired)
        self.assertIn(f'default_subagent_model = "{plan["default_subagent_model"]}"', desired)

    def test_verifiers_are_pinned_and_implementer_inherits_worker_override(self):
        plan = self.plan()
        by_role = {a.get("role"): a for a in plan["actions"] if a["component"] == "agent"}
        for name in ("phase-reviewer", "kit-verifier"):
            self.assertIn("model = ", by_role[name]["desired"].decode())
        self.assertNotIn("model = ", by_role["kit-implementer"]["desired"].decode())

    def test_runtime_snapshot_is_required_for_apply_and_missing_model_fails(self):
        with self.assertRaisesRegex(app.AppPolicyError, "validated runtime"):
            app.apply_app_policy(self.plan(runtime=False))
        self.runtime.write_text('{"data": []}')
        with self.assertRaisesRegex(app.AppPolicyError, "missing required"):
            self.plan()

    def test_apply_backs_up_and_preserves_custom_guidance(self):
        self.home.mkdir()
        (self.home / "config.toml").write_text('custom = "keep"\n')
        (self.home / "AGENTS.md").write_text("my private guidance\n")
        result = app.apply_app_policy(self.plan())
        self.assertEqual(result["runtime_models"], "validated")
        self.assertIn("my private guidance", (self.home / "AGENTS.md").read_text())
        self.assertTrue((self.backup / "home/guidance/AGENTS.md").is_file())
        self.assertTrue((self.home / "polytropos/app-policy-manifest.json").is_file())

    def test_unmanaged_role_is_conflict_and_never_overwritten(self):
        target = self.home / "agents/kit-verifier.toml"
        target.parent.mkdir(parents=True)
        target.write_text("private = true\n")
        plan = self.plan()
        action = next(a for a in plan["actions"] if a.get("role") == "kit-verifier")
        self.assertEqual(action["state"], "conflict")
        with self.assertRaisesRegex(app.AppPolicyError, "refusing to overwrite"):
            app.apply_app_policy(plan)
        self.assertEqual(target.read_text(), "private = true\n")

    def test_backup_must_be_outside_repo_and_home(self):
        with self.assertRaisesRegex(app.AppPolicyError, "outside the repository"):
            app.plan_app_policy(self.repo, self.home, self.repo / "backup", self.runtime)

    def test_source_contains_no_model_process_dispatch(self):
        source = (ROOT / "bin/codex_app_policy.py").read_text()
        self.assertNotIn("codex exec", source)
        self.assertNotIn("subprocess", source)

    def test_project_role_shadow_is_updated_when_it_matches_canonical(self):
        target = self.repo / ".codex/agents/kit-verifier.toml"
        target.parent.mkdir(parents=True)
        target.write_bytes((self.repo / "codex/agents/kit-verifier.toml").read_bytes())
        action = next(a for a in self.plan()["actions"]
                      if a.get("role") == "kit-verifier" and a.get("scope") == "project")
        self.assertEqual(action["state"], "managed-update")
        self.assertIn("sandbox_mode = \"read-only\"", action["desired"].decode())

    def test_stale_plan_is_rejected(self):
        plan = self.plan()
        target = Path(next(a for a in plan["actions"] if a["component"] == "config")["destination"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("changed after plan\n")
        with self.assertRaisesRegex(app.AppPolicyError, "changed after plan"):
            app.apply_app_policy(plan)

    def test_symlink_destination_is_rejected(self):
        self.home.mkdir()
        real = Path(self.temp.name) / "real-config"
        real.write_text("")
        (self.home / "config.toml").symlink_to(real)
        plan = self.plan()
        with self.assertRaisesRegex(app.AppPolicyError, "symlinked"):
            app.apply_app_policy(plan)

    def test_intermediate_project_symlink_is_rejected(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (self.repo / ".codex").symlink_to(outside, target_is_directory=True)
        plan = self.plan()
        with self.assertRaisesRegex(app.AppPolicyError, "symlinked"):
            app.apply_app_policy(plan)

    def test_manifest_failure_rolls_back_live_writes(self):
        plan = self.plan()
        original_atomic = app._atomic_write

        def fail_manifest(path, data):
            if Path(path) == Path(plan["manifest_path"]):
                raise OSError("synthetic manifest failure")
            return original_atomic(path, data)

        with mock.patch.object(app, "_atomic_write", side_effect=fail_manifest):
            with self.assertRaisesRegex(OSError, "manifest failure"):
                app.apply_app_policy(plan)
        self.assertFalse((self.home / "config.toml").exists())
        self.assertFalse(Path(plan["manifest_path"]).exists())

    def test_malformed_installer_ownership_fails_clearly(self):
        path = self.home / "polytropos/install-manifest.json"
        path.parent.mkdir(parents=True)
        path.write_text('{"files": ["bad"]}')
        with self.assertRaisesRegex(app.AppPolicyError, "invalid Codex install ownership record"):
            self.plan()

    def test_nonobject_app_ownership_manifest_fails_clearly(self):
        path = self.home / "polytropos/app-policy-manifest.json"
        path.parent.mkdir(parents=True)
        for payload in ("[]", '["bad"]'):
            path.write_text(payload)
            with self.assertRaisesRegex(app.AppPolicyError, "manifest object"):
                self.plan()

    def test_harness_setup_preserves_applied_policy_roles_and_guidance(self):
        app.apply_app_policy(self.plan())
        before = {
            path: path.read_bytes()
            for path in (
                self.home / "AGENTS.md",
                self.repo / ".codex/agents/phase-reviewer.toml",
                self.repo / ".codex/agents/kit-verifier.toml",
            )
        }
        setup = harness.plan_codex_setup(
            self.repo, self.home, components=("agents", "guidance"),
            agent_scope="project", legacy_copy=True, refresh_managed=True,
        )
        relevant = [a for a in setup["actions"] if a["component"] in {"agents", "guidance"}]
        self.assertTrue(relevant)
        self.assertTrue(all(a["state"] == "up-to-date" for a in relevant))
        self.assertTrue(any("central Codex app policy" in a["reason"] for a in relevant))
        harness.apply_codex_plan(setup)
        self.assertEqual(before, {path: path.read_bytes() for path in before})


if __name__ == "__main__":
    unittest.main()
