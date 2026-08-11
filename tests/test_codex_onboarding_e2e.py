import importlib.util
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "bin" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


selector = _load("harness_select")
syncer = _load("sync_codex_surfaces")


def _relocated(root):
    shutil.copytree(ROOT / "codex", root / "codex")
    shutil.copytree(ROOT / ".codex-plugin", root / ".codex-plugin")
    shutil.copytree(ROOT / ".agents" / "plugins", root / ".agents" / "plugins")
    (root / "data").mkdir()
    shutil.copy2(ROOT / "data" / "pricing.codex.json", root / "data" / "pricing.codex.json")
    (root / "bin").mkdir()
    for name in (
        "codex_pricing.py",
        "codex_execute.py",
        "codex_usage.py",
        "journal_collect.py",
        "journal_summarize.py",
        "journal_askpack.py",
        "journal_plan.py",
        "harness_select.py",
        "context_weight.py",
        "bench_routing.py",
        "memory_recall.py",
        "memory_store.py",
    ):
        shutil.copy2(ROOT / "bin" / name, root / "bin" / name)
    return root


def _files(root):
    return sorted(path for path in root.rglob("*") if path.is_file()) if root.exists() else []


class CodexOnboardingE2ETests(unittest.TestCase):
    def test_fresh_relocated_clone_validates_and_plans_deterministically(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            base = Path(tmp_s)
            repo, home = _relocated(base / "repo"), base / "home"
            skills = list((repo / "codex" / "skills").glob("*/SKILL.md"))
            agents = list((repo / "codex" / "agents").glob("*.toml"))
            self.assertEqual(len(skills), 12)
            self.assertEqual(len(agents), 4)
            plan = selector.plan_codex_setup(repo, home)
            self.assertEqual(plan["actions"][0]["state"], "up-to-date")
            self.assertEqual(
                selector.render_codex_plan(plan, as_json=True),
                selector.render_codex_plan(selector.plan_codex_setup(repo, home), as_json=True),
            )
            before = list(base.rglob("*"))
            doctor = selector.doctor_codex(repo, home)
            self.assertEqual(doctor["actions"][0]["state"], "up-to-date")
            self.assertEqual(list(base.rglob("*")), before)

    def test_managed_install_idempotence_update_and_user_conflict(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            base = Path(tmp_s)
            repo, home = _relocated(base / "repo"), base / "home"
            components = selector.CODEX_COMPONENTS
            first = selector.plan_codex_setup(
                repo,
                home,
                components=components,
                agent_scope="project",
                legacy_copy=True,
            )
            selector.apply_codex_plan(first)
            self.assertEqual(len(list((repo / ".codex" / "agents").glob("*.toml"))), 4)
            self.assertEqual(len(list((home / "skills").glob("*/SKILL.md"))), 12)
            self.assertEqual(len(list((home / "prompts").glob("*.md"))), 10)
            self.assertTrue((home / "AGENTS.md").is_file())

            ownership_path = home / selector.OWNERSHIP_RELATIVE
            ownership = json.loads(ownership_path.read_text())
            serialized = json.dumps(ownership)
            self.assertNotIn("developer_instructions", serialized)
            self.assertNotIn("API_KEY", serialized)
            self.assertTrue(all("source_hash" in record for record in ownership["files"]))

            tracked = _files(home) + _files(repo / ".codex")
            before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in tracked}
            second = selector.plan_codex_setup(
                repo,
                home,
                components=components,
                agent_scope="project",
                legacy_copy=True,
            )
            self.assertTrue(
                all(action["state"] == "up-to-date" for action in second["actions"])
            )
            selector.apply_codex_plan(second)
            self.assertEqual(
                {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in tracked}, before
            )

            source = repo / "codex" / "skills" / "route" / "SKILL.md"
            source.write_text(source.read_text() + "\n<!-- source update -->\n")
            prior_manifest = ownership_path.read_bytes()
            refresh = selector.plan_codex_setup(
                repo,
                home,
                components=components,
                agent_scope="project",
                legacy_copy=True,
                refresh_managed=True,
            )
            route = next(
                action
                for action in refresh["actions"]
                if action["destination"].endswith("skills/route/SKILL.md")
            )
            self.assertEqual(route["state"], "managed-update")
            selector.apply_codex_plan(refresh)
            self.assertNotEqual(ownership_path.read_bytes(), prior_manifest)

            installed_route = home / "skills" / "route" / "SKILL.md"
            installed_route.write_text(installed_route.read_text() + "\nuser edit\n")
            prior_manifest = ownership_path.read_bytes()
            conflict = selector.plan_codex_setup(
                repo,
                home,
                components=components,
                agent_scope="project",
                legacy_copy=True,
                refresh_managed=True,
            )
            self.assertEqual(
                next(
                    action["state"]
                    for action in conflict["actions"]
                    if action["destination"].endswith("skills/route/SKILL.md")
                ),
                "conflict",
            )
            with self.assertRaises(ValueError):
                selector.apply_codex_plan(conflict)
            self.assertTrue(installed_route.read_text().endswith("user edit\n"))
            self.assertEqual(ownership_path.read_bytes(), prior_manifest)

    def test_stale_legacy_copy_and_large_agent_collision_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            base = Path(tmp_s)
            repo, home = _relocated(base / "repo"), base / "home"
            source = repo / "codex" / "skills" / "route" / "SKILL.md"
            installed = home / "skills" / "route" / "SKILL.md"
            installed.parent.mkdir(parents=True)
            installed.write_text(
                source.read_text().replace(selector.PLACEHOLDER, "/Users/example/old/polytropos")
            )
            adopt = selector.plan_codex_setup(
                repo,
                home,
                components=("skills",),
                legacy_copy=True,
                refresh_managed=True,
            )
            self.assertEqual(
                next(
                    action["state"]
                    for action in adopt["actions"]
                    if action["destination"].endswith("skills/route/SKILL.md")
                ),
                "managed-update",
            )
            installed.write_text("unrelated personal skill\n")
            unrelated = selector.plan_codex_setup(
                repo,
                home,
                components=("skills",),
                legacy_copy=True,
                refresh_managed=True,
            )
            self.assertEqual(
                next(
                    action["state"]
                    for action in unrelated["actions"]
                    if action["destination"].endswith("skills/route/SKILL.md")
                ),
                "conflict",
            )

            destination = repo / ".codex" / "agents"
            destination.mkdir(parents=True)
            for index in range(84):
                (destination / f"legacy-{index:02d}.toml").write_text(
                    f'name = "legacy-{index:02d}"\n'
                )
            before = {path: path.read_bytes() for path in destination.glob("*.toml")}
            report = selector.doctor_codex(repo, home)
            unmanaged = [
                action for action in report["actions"]
                if action["component"] == "agents" and action["state"] == "unmanaged"
            ]
            self.assertEqual(len(unmanaged), 84)
            self.assertTrue(all("manual review" in action["reason"] for action in unmanaged))
            self.assertEqual({path: path.read_bytes() for path in destination.glob("*.toml")}, before)

    def test_prompt_drift_and_moved_plugin_fail_closed_correctly(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            base = Path(tmp_s)
            repo, home = _relocated(base / "repo"), base / "home"
            prompt = repo / "codex" / "prompts" / "route.md"
            prompt.write_text("drift\n")
            other_before = {
                path: path.read_bytes()
                for path in _files(repo)
                if not path.is_relative_to(repo / "codex" / "prompts")
            }
            self.assertIn("route.md", syncer.sync(repo, "check"))
            syncer.sync(repo, "build")
            self.assertEqual(syncer.sync(repo, "check"), [])
            self.assertEqual(
                {
                    path: path.read_bytes()
                    for path in _files(repo)
                    if not path.is_relative_to(repo / "codex" / "prompts")
                },
                other_before,
            )

            copied = home / "skills" / "route" / "SKILL.md"
            copied.parent.mkdir(parents=True)
            copied.write_text(
                (repo / "codex" / "skills" / "route" / "SKILL.md")
                .read_text()
                .replace(syncer.PLACEHOLDER, str(repo))
            )
            moved = base / "moved-repo"
            repo.replace(moved)
            moved_skill = moved / "codex" / "skills" / "route" / "SKILL.md"
            self.assertEqual(
                syncer.resolve_skill_root(moved_skill, "codex_pricing.py"), moved.resolve()
            )
            with self.assertRaisesRegex(RuntimeError, "doctor"):
                syncer.resolve_skill_root(copied, "codex_pricing.py", repo)

    def test_static_setup_and_sync_safety(self):
        setup = (ROOT / "bin" / "harness_select.py").read_text()
        sync = (ROOT / "bin" / "sync_codex_surfaces.py").read_text()
        combined = setup + sync
        for rejected in (
            "subprocess.run",
            "subprocess.Popen",
            "urllib",
            "requests.",
            "shutil.rmtree",
            "os.system",
        ):
            self.assertNotIn(rejected, combined)
        model_ids = json.loads((ROOT / "data" / "pricing.codex.json").read_text())["models"]
        for model_id in model_ids:
            self.assertNotIn(model_id, combined)
        self.assertIsNone(re.search(r"\$\d+(?:\.\d+)?", combined))


if __name__ == "__main__":
    unittest.main()
