"""Installation is ownership-aware, and a plan is not a promise (roadmap step 11).

Two failures motivate this file, and every test below is one of them or a boundary of the fix.

FAILURE ONE: THE COPILOT INSTALLER OVERWROTE EVERYTHING. It wrote every destination
unconditionally, so a same-named file the user wrote themselves, and every edit they made to
one of ours, was replaced with no record it had existed. Codex had ownership classification;
Copilot had none.

FAILURE TWO: A PLAN IS A SNAPSHOT AND APPLYING IT IS NOT INSTANT. Between classification and
writing, a destination called absent can be created and a managed destination called unchanged
can be edited. Both were overwritten anyway. Rollback had the mirror-image bug: it restored
prior bytes over a destination without checking whether the bytes there were still the ones it
had written, so recovering from a partial failure could erase a concurrent change.

Every fixture here is a temporary directory. No test reads or writes a real harness home.
"""

import importlib.util
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_ownership", ROOT / "bin" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hs = _load("harness_select")
#: The SAME module object `harness_select` uses, not a second copy of the file. Loading
#: `bin/safe_paths.py` twice would give two unrelated `SafePathExists` classes, and an
#: `except` in one module would not catch a raise from the other.
sp = hs._sp()

AGENT = (
    "name: route\n"
    "Repo: {{POLYTROPOS_ROOT}}\n"
    "Engine: {{POLYTROPOS_ROOT}}/bin/codex_pricing.py\n"
)
SKILL = "Engine: {{POLYTROPOS_ROOT}}/bin/codex_pricing.py\n"
CODEX_AGENTS = ("kit-implementer", "kit-verifier", "phase-reviewer", "repo-explorer")


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _copilot_repo(root, agent=AGENT, skill=SKILL):
    _write(root / "copilot" / ".github" / "agents" / "route.agent.md", agent)
    _write(root / "copilot" / ".github" / "skills" / "lessons-loop" / "SKILL.md", skill)
    return root


def _codex_repo(root):
    _write(root / ".codex-plugin" / "plugin.json", json.dumps({"name": "polytropos", "version": "1.2.3"}))
    _write(
        root / ".agents" / "plugins" / "marketplace.json",
        json.dumps({"plugins": [{"name": "polytropos", "source": {"source": "local", "path": "./"}}]}),
    )
    for name in CODEX_AGENTS:
        _write(
            root / "codex" / "agents" / f"{name}.toml",
            f'name = "{name}"\ndescription = "Fixture for {name}"\n'
            'developer_instructions = """Use tasks/kits/<slug>. '
            'States: pending | in-progress | done | blocked."""\n',
        )
    _write(root / "codex" / "prompts" / "route.md", "Repo: {{POLYTROPOS_ROOT}}\n")
    _write(root / "codex" / "AGENTS.md", "Repo: {{POLYTROPOS_ROOT}}\n")
    return root


class _Fixture(unittest.TestCase):
    """A repo root and a harness home, both temporary, cleaned up by the test framework."""

    def setUp(self):
        self.root_dir = tempfile.TemporaryDirectory()
        self.home_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.root_dir.cleanup)
        self.addCleanup(self.home_dir.cleanup)
        self.root = Path(self.root_dir.name)
        self.home = Path(self.home_dir.name)

    def states(self, result):
        return {action["relative"]: action["state"] for action in result.actions}


class CopilotFirstInstallTests(_Fixture):
    def test_first_install_writes_every_destination_and_claims_ownership(self):
        _copilot_repo(self.root)
        result = hs.install_copilot(self.home, repo_root=self.root)

        self.assertEqual(
            self.states(result),
            {"agents/route.agent.md": "install", "skills/lessons-loop/SKILL.md": "install"},
        )
        self.assertEqual(
            (self.home / "agents" / "route.agent.md").read_text(),
            AGENT.replace(hs.PLACEHOLDER, str(self.root)),
        )
        manifest = json.loads((self.home / hs.COPILOT_OWNERSHIP_RELATIVE).read_text())
        self.assertEqual(
            sorted(record["destination"] for record in manifest["files"]),
            ["agents/route.agent.md", "skills/lessons-loop/SKILL.md"],
        )

    def test_the_returned_value_is_still_the_plain_destination_list(self):
        # Backward compatibility, asserted rather than assumed: every caller that predates
        # ownership indexes, counts, or compares this to a literal list of paths.
        _copilot_repo(self.root)
        result = hs.install_copilot(self.home, repo_root=self.root)
        self.assertEqual(
            list(result),
            [
                self.home / "agents" / "route.agent.md",
                self.home / "skills" / "lessons-loop" / "SKILL.md",
            ],
        )
        self.assertEqual(result, [Path(p) for p in result])

    def test_dry_run_classifies_without_creating_anything(self):
        _copilot_repo(self.root)
        result = hs.install_copilot(self.home, repo_root=self.root, dry_run=True)
        self.assertEqual(set(self.states(result).values()), {"install"})
        self.assertEqual(list(self.home.iterdir()), [])

    def test_ownership_manifest_is_owner_readable_only(self):
        _copilot_repo(self.root)
        hs.install_copilot(self.home, repo_root=self.root)
        mode = (self.home / hs.COPILOT_OWNERSHIP_RELATIVE).stat().st_mode
        self.assertEqual(stat.S_IMODE(mode) & 0o077, 0)


class CopilotReinstallAndUpgradeTests(_Fixture):
    def test_reinstall_is_up_to_date_and_leaves_the_bytes_alone(self):
        _copilot_repo(self.root)
        hs.install_copilot(self.home, repo_root=self.root)
        destination = self.home / "agents" / "route.agent.md"
        before = destination.stat().st_mtime_ns

        result = hs.install_copilot(self.home, repo_root=self.root)

        self.assertEqual(set(self.states(result).values()), {"up-to-date"})
        self.assertEqual(destination.stat().st_mtime_ns, before)

    def test_managed_upgrade_refreshes_an_unchanged_copy_with_no_extra_flag(self):
        # The routine case. It must not acquire a confirmation ritual just because unmanaged
        # destinations acquired one.
        _copilot_repo(self.root)
        hs.install_copilot(self.home, repo_root=self.root)
        _write(self.root / "copilot" / ".github" / "agents" / "route.agent.md", AGENT + "new line\n")

        result = hs.install_copilot(self.home, repo_root=self.root)

        self.assertEqual(self.states(result)["agents/route.agent.md"], "managed-update")
        self.assertIn("new line", (self.home / "agents" / "route.agent.md").read_text())

    def test_a_home_installed_before_ownership_existed_is_claimed_without_a_write(self):
        # Adoption of an identical destination changes no bytes, which is what lets an older
        # install become managed without anything being overwritten to get there.
        _copilot_repo(self.root)
        resolved = AGENT.replace(hs.PLACEHOLDER, str(self.root))
        _write(self.home / "agents" / "route.agent.md", resolved)
        _write(self.home / "skills" / "lessons-loop" / "SKILL.md",
               SKILL.replace(hs.PLACEHOLDER, str(self.root)))

        result = hs.install_copilot(self.home, repo_root=self.root)

        self.assertEqual(set(self.states(result).values()), {"up-to-date"})
        manifest = json.loads((self.home / hs.COPILOT_OWNERSHIP_RELATIVE).read_text())
        self.assertEqual(len(manifest["files"]), 2)

    def test_a_copy_installed_from_another_repo_path_is_recognized_and_refreshed(self):
        _copilot_repo(self.root)
        # A home-shaped prior root, because that is the shape the legacy recognizer looks for.
        _write(
            self.home / "agents" / "route.agent.md",
            AGENT.replace(hs.PLACEHOLDER, "/Users/someone/polytropos"),
        )

        result = hs.install_copilot(self.home, repo_root=self.root)

        self.assertEqual(self.states(result)["agents/route.agent.md"], "managed-update")
        self.assertEqual(
            (self.home / "agents" / "route.agent.md").read_text(),
            AGENT.replace(hs.PLACEHOLDER, str(self.root)),
        )


class CopilotPreservationTests(_Fixture):
    def test_a_user_file_at_one_of_our_destinations_is_never_overwritten(self):
        _copilot_repo(self.root)
        _write(self.home / "agents" / "route.agent.md", "my own agent\n")

        result = hs.install_copilot(self.home, repo_root=self.root)

        self.assertEqual(self.states(result)["agents/route.agent.md"], "conflict")
        self.assertEqual((self.home / "agents" / "route.agent.md").read_text(), "my own agent\n")
        self.assertIn("--adopt-existing", result.conflicts[0]["reason"])
        # The unrelated destination still installs: one conflict does not block the rest.
        self.assertTrue((self.home / "skills" / "lessons-loop" / "SKILL.md").is_file())

    def test_an_edit_made_after_install_is_preserved_on_the_next_install(self):
        _copilot_repo(self.root)
        hs.install_copilot(self.home, repo_root=self.root)
        destination = self.home / "agents" / "route.agent.md"
        destination.write_text("edited by me\n")

        result = hs.install_copilot(self.home, repo_root=self.root)

        self.assertEqual(self.states(result)["agents/route.agent.md"], "conflict")
        self.assertEqual(destination.read_text(), "edited by me\n")
        self.assertIn("edited after install", result.conflicts[0]["reason"])

    def test_an_unreadable_manifest_makes_us_own_nothing_rather_than_everything(self):
        _copilot_repo(self.root)
        hs.install_copilot(self.home, repo_root=self.root)
        (self.home / hs.COPILOT_OWNERSHIP_RELATIVE).write_text("{ not json")
        (self.home / "agents" / "route.agent.md").write_text("edited by me\n")

        result = hs.install_copilot(self.home, repo_root=self.root)

        self.assertEqual(self.states(result)["agents/route.agent.md"], "conflict")
        self.assertEqual((self.home / "agents" / "route.agent.md").read_text(), "edited by me\n")


class CopilotAdoptionTests(_Fixture):
    def test_adopt_overwrites_and_keeps_the_prior_bytes_beside_the_destination(self):
        _copilot_repo(self.root)
        _write(self.home / "agents" / "route.agent.md", "my own agent\n")

        result = hs.install_copilot(self.home, repo_root=self.root, adopt_unmanaged=True)

        self.assertEqual(self.states(result)["agents/route.agent.md"], "adopt-update")
        self.assertEqual(
            (self.home / "agents" / "route.agent.md").read_text(),
            AGENT.replace(hs.PLACEHOLDER, str(self.root)),
        )
        backup = self.home / "agents" / f"route.agent.md{hs.COPILOT_BACKUP_SUFFIX}"
        self.assertEqual(backup.read_text(), "my own agent\n")

    def test_adoption_refuses_rather_than_overwrite_an_earlier_adoptions_backup(self):
        _copilot_repo(self.root)
        _write(self.home / "agents" / "route.agent.md", "first version\n")
        _write(self.home / "agents" / f"route.agent.md{hs.COPILOT_BACKUP_SUFFIX}", "older backup\n")

        with self.assertRaises(hs.StalePlanError) as ctx:
            hs.install_copilot(self.home, repo_root=self.root, adopt_unmanaged=True)

        self.assertIn("already exists", str(ctx.exception))
        self.assertEqual(
            (self.home / "agents" / f"route.agent.md{hs.COPILOT_BACKUP_SUFFIX}").read_text(),
            "older backup\n",
        )
        # Refusal rolled back: the destination is still the user's.
        self.assertEqual((self.home / "agents" / "route.agent.md").read_text(), "first version\n")


class CopilotSymlinkTests(_Fixture):
    def test_a_symlink_at_a_destination_is_preserved_and_never_written_through(self):
        _copilot_repo(self.root)
        outside = Path(self.root_dir.name) / "outside.md"
        outside.write_text("untouched\n")
        (self.home / "agents").mkdir()
        (self.home / "agents" / "route.agent.md").symlink_to(outside)

        result = hs.install_copilot(self.home, repo_root=self.root)

        self.assertEqual(self.states(result)["agents/route.agent.md"], "conflict")
        self.assertEqual(outside.read_text(), "untouched\n")
        self.assertTrue((self.home / "agents" / "route.agent.md").is_symlink())

    def test_a_symlinked_parent_directory_is_refused_not_traversed(self):
        _copilot_repo(self.root)
        outside_dir = Path(self.root_dir.name) / "outside-agents"
        outside_dir.mkdir()
        (self.home / "agents").symlink_to(outside_dir, target_is_directory=True)

        with self.assertRaises(sp.SafePathError):
            hs.install_copilot(self.home, repo_root=self.root)

        self.assertEqual(list(outside_dir.iterdir()), [])


class CopilotRollbackTests(_Fixture):
    def test_a_partial_failure_takes_back_this_runs_own_writes(self):
        _copilot_repo(self.root)
        plan = hs.plan_copilot_install(self.home, repo_root=self.root)

        with self.assertRaisesRegex(RuntimeError, "simulated"):
            hs.apply_copilot_plan(plan, fail_after=1)

        self.assertFalse((self.home / "agents" / "route.agent.md").exists())
        self.assertFalse((self.home / "skills" / "lessons-loop" / "SKILL.md").exists())
        self.assertFalse((self.home / hs.COPILOT_OWNERSHIP_RELATIVE).exists())

    def test_a_partial_failure_restores_prior_bytes_it_replaced(self):
        _copilot_repo(self.root)
        hs.install_copilot(self.home, repo_root=self.root)
        _write(self.root / "copilot" / ".github" / "agents" / "route.agent.md", AGENT + "v2\n")
        _write(self.root / "copilot" / ".github" / "skills" / "lessons-loop" / "SKILL.md", SKILL + "v2\n")
        before = (self.home / "agents" / "route.agent.md").read_bytes()
        plan = hs.plan_copilot_install(self.home, repo_root=self.root)
        self.assertEqual(set(a["state"] for a in plan["actions"]), {"managed-update"})

        with self.assertRaisesRegex(RuntimeError, "simulated"):
            hs.apply_copilot_plan(plan, fail_after=1)

        self.assertEqual((self.home / "agents" / "route.agent.md").read_bytes(), before)

    def test_rollback_leaves_a_destination_something_else_changed_after_we_wrote_it(self):
        # The mirror-image of the bug this file exists for: undoing our own write is repair,
        # undoing somebody else's is the same destruction in the other direction.
        _copilot_repo(self.root)
        hs.install_copilot(self.home, repo_root=self.root)
        _write(self.root / "copilot" / ".github" / "agents" / "route.agent.md", AGENT + "v2\n")
        _write(self.root / "copilot" / ".github" / "skills" / "lessons-loop" / "SKILL.md", SKILL + "v2\n")
        plan = hs.plan_copilot_install(self.home, repo_root=self.root)

        destination = self.home / "agents" / "route.agent.md"
        original_replace = sp.confined_replace

        def replace_then_interfere(root, rel_path, data, **kwargs):
            original_replace(root, rel_path, data, **kwargs)
            if rel_path == "agents/route.agent.md" and b"v2" in data:
                destination.write_text("written by someone else\n")

        hs._sp().confined_replace = replace_then_interfere
        self.addCleanup(setattr, hs._sp(), "confined_replace", original_replace)

        with self.assertRaisesRegex(RuntimeError, "left as found"):
            hs.apply_copilot_plan(plan, fail_after=1)

        self.assertEqual(destination.read_text(), "written by someone else\n")


class CodexStalePlanTests(_Fixture):
    def _plan(self, **kwargs):
        _codex_repo(self.root)
        return hs.plan_codex_setup(self.root, self.home, **kwargs)

    def test_a_destination_created_after_the_plan_is_not_overwritten(self):
        plan = self._plan(components=("prompts",), legacy_copy=True)
        action = next(a for a in plan["actions"] if a["component"] == "prompts")
        self.assertEqual(action["state"], "install")

        _write(Path(action["destination"]), "created in the gap\n")

        with self.assertRaises(hs.StalePlanError) as ctx:
            hs.apply_codex_plan(plan)

        self.assertIn("exists", str(ctx.exception))
        self.assertEqual(Path(action["destination"]).read_text(), "created in the gap\n")

    def test_a_managed_destination_edited_after_the_plan_is_not_overwritten(self):
        _codex_repo(self.root)
        first = hs.plan_codex_setup(self.root, self.home, components=("prompts",), legacy_copy=True)
        hs.apply_codex_plan(first)
        _write(self.root / "codex" / "prompts" / "route.md", "Repo: {{POLYTROPOS_ROOT}}\nv2\n")
        plan = hs.plan_codex_setup(
            self.root, self.home, components=("prompts",), legacy_copy=True, refresh_managed=True
        )
        action = next(a for a in plan["actions"] if a["component"] == "prompts")
        self.assertEqual(action["state"], "managed-update")

        Path(action["destination"]).write_text("edited in the gap\n")

        with self.assertRaises(hs.StalePlanError) as ctx:
            hs.apply_codex_plan(plan)

        self.assertIn("changed after the plan", str(ctx.exception))
        self.assertEqual(Path(action["destination"]).read_text(), "edited in the gap\n")

    def test_rollback_preserves_a_destination_changed_during_recovery(self):
        plan = self._plan(components=("agents",), agent_scope="user")
        writable = [a for a in plan["actions"] if a["state"] == "install"]
        self.assertGreaterEqual(len(writable), 2)

        # Change a destination's bytes AFTER this run wrote them and BEFORE rollback inspects
        # them -- the exact window in which a concurrent edit used to be erased by recovery.
        module = hs._sp()
        original_read = module.confined_read_bytes
        interfered = []

        def read_but_it_moved(root, rel_path, **kwargs):
            if kwargs.get("what") == "rollback" and not interfered:
                interfered.append(rel_path)
                Path(root, *rel_path.split("/")).write_text("someone else's file\n")
            return original_read(root, rel_path, **kwargs)

        module.confined_read_bytes = read_but_it_moved
        self.addCleanup(setattr, module, "confined_read_bytes", original_read)

        with self.assertRaisesRegex(RuntimeError, "left as found"):
            hs.apply_codex_plan(plan, fail_after=len(writable))

        changed = Path(self.home, *interfered[0].split("/"))
        self.assertEqual(changed.read_text(), "someone else's file\n")

    def test_recorded_ownership_hashes_the_bytes_written_not_a_reread(self):
        plan = self._plan(components=("prompts",), legacy_copy=True)
        action = next(a for a in plan["actions"] if a["component"] == "prompts")
        hs.apply_codex_plan(plan)
        # Someone rewrites the destination straight after the install.
        Path(action["destination"]).write_text("changed right after\n")

        manifest = json.loads((self.home / hs.OWNERSHIP_RELATIVE).read_text())
        record = next(r for r in manifest["files"] if r["component"] == "prompts")
        self.assertEqual(record["installed_hash"], action["_installed_digest"])


class SafeCreateTests(unittest.TestCase):
    def test_creation_refuses_a_name_that_is_already_taken(self):
        with tempfile.TemporaryDirectory() as home:
            sp.confined_create_bytes(home, "a/b.txt", b"first")
            with self.assertRaises(sp.SafePathExists):
                sp.confined_create_bytes(home, "a/b.txt", b"second")
            self.assertEqual(Path(home, "a", "b.txt").read_bytes(), b"first")

    def test_a_symlink_at_the_name_counts_as_taken_and_is_not_written_through(self):
        with tempfile.TemporaryDirectory() as home_s, tempfile.TemporaryDirectory() as out_s:
            outside = Path(out_s) / "target.txt"
            outside.write_text("untouched")
            Path(home_s, "link.txt").symlink_to(outside)

            with self.assertRaises(sp.SafePathExists):
                sp.confined_create_bytes(home_s, "link.txt", b"payload")

            self.assertEqual(outside.read_text(), "untouched")

    def test_exists_is_a_subclass_of_the_modules_own_refusal(self):
        # Callers that already catch SafePathError keep catching this one.
        self.assertTrue(issubclass(sp.SafePathExists, sp.SafePathError))
        self.assertTrue(issubclass(sp.SafePathExists, ValueError))

    def test_traversal_is_refused_before_anything_is_created(self):
        with tempfile.TemporaryDirectory() as home:
            with self.assertRaises(sp.SafePathError):
                sp.confined_create_bytes(home, "../escape.txt", b"payload")
            self.assertFalse(Path(home).parent.joinpath("escape.txt").exists())


if __name__ == "__main__":
    unittest.main()
