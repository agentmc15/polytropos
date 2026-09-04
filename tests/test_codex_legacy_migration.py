import importlib.util
import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
import harness_select as hs
import codex_legacy_migration as migration


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())


class LegacyMigrationTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        base = Path(temporary.name); repo, home, backup = base/"repo", base/"home", base/"backup"
        write(repo/"codex/prompts/route.md", "root={{POLYTROPOS_ROOT}}\n")
        write(repo/"codex/skills/route/SKILL.md", "root={{POLYTROPOS_ROOT}}\n")
        write(repo/".codex-plugin/plugin.json", json.dumps({"name":"polytropos","version":"1"}))
        prompt = f"root={repo.resolve()}\n".encode(); skill = prompt
        write(home/"prompts/route.md", prompt); write(home/"skills/route/SKILL.md", skill)
        return repo, home, backup, prompt, skill

    def test_preview_is_read_only_and_apply_requires_attestation(self):
        repo,home,backup,prompt,_=self.fixture(); path=home/"prompts/route.md"; stamp=path.stat().st_mtime_ns
        plan=migration.plan_retirement(repo,home,backup)
        self.assertFalse(backup.exists()); self.assertEqual(path.read_bytes(),prompt); self.assertEqual(path.stat().st_mtime_ns,stamp)
        with self.assertRaisesRegex(ValueError,"operator evidence"): migration.apply_retirement(plan)

    def test_matching_batch_retires_and_restores_bytes(self):
        repo,home,backup,prompt,skill=self.fixture()
        plan=migration.plan_retirement(repo,home,backup,("prompts","skills"),True)
        result=migration.apply_retirement(plan)
        self.assertEqual(len(result["files"]),2); self.assertFalse((home/"prompts/route.md").exists())
        self.assertFalse((home/"skills/route").exists())
        owner=json.loads((home/hs.OWNERSHIP_RELATIVE).read_text()); self.assertEqual(len(owner["retired"]),2)
        migration.restore_legacy(repo,home,backup)
        self.assertEqual((home/"prompts/route.md").read_bytes(),prompt); self.assertEqual((home/"skills/route/SKILL.md").read_bytes(),skill)

    def test_unknown_old_or_edited_content_blocks_whole_batch(self):
        repo,home,backup,_,_=self.fixture(); write(home/"prompts/route.md","same name, old banner\n")
        plan=migration.plan_retirement(repo,home,backup,("prompts","skills"),True)
        self.assertTrue(plan["blocked"])
        with self.assertRaises(ValueError): migration.apply_retirement(plan)
        self.assertTrue((home/"skills/route/SKILL.md").exists()); self.assertFalse(backup.exists())

    def test_skill_companion_file_blocks_whole_directory(self):
        repo,home,backup,_,_=self.fixture(); write(home/"skills/route/notes.txt","mine")
        plan=migration.plan_retirement(repo,home,backup,("skills",),True)
        self.assertTrue(plan["blocked"]); self.assertTrue(any(path.endswith("/skills/route/notes.txt") for path in plan["conflicts"]))

    def test_digest_change_and_backup_collision_are_safe(self):
        repo,home,backup,_,_=self.fixture(); plan=migration.plan_retirement(repo,home,backup,("prompts",),True)
        write(home/"prompts/route.md","changed")
        with self.assertRaisesRegex(ValueError,"changed since preview"): migration.apply_retirement(plan)
        self.assertEqual((home/"prompts/route.md").read_text(),"changed")
        write(home/"prompts/route.md",f"root={repo.resolve()}\n"); plan=migration.plan_retirement(repo,home,backup,("prompts",),True)
        write(Path(plan["actions"][0]["backup"]),"occupied")
        with self.assertRaises(FileExistsError): migration.apply_retirement(plan)
        self.assertTrue((home/"prompts/route.md").exists())

    def test_write_and_manifest_failures_roll_back(self):
        for kwargs in ({"fail_after":1},{"fail_manifest":True}):
            repo,home,backup,prompt,_=self.fixture(); plan=migration.plan_retirement(repo,home,backup,("prompts",),True)
            with self.assertRaises(RuntimeError): migration.apply_retirement(plan,**kwargs)
            self.assertEqual((home/"prompts/route.md").read_bytes(),prompt)
            self.assertFalse((backup/migration.MANIFEST_NAME).exists())

    def test_real_atomic_ownership_write_failure_rolls_back(self):
        repo, home, backup, prompt, _ = self.fixture()
        plan = migration.plan_retirement(repo, home, backup, ("prompts",), True)
        original = migration._atomic_write

        def fail_owner(path, payload):
            if Path(path).resolve() == (home / hs.OWNERSHIP_RELATIVE).resolve():
                raise OSError("disk full")
            return original(path, payload)

        with mock.patch.object(migration, "_atomic_write", side_effect=fail_owner):
            with self.assertRaisesRegex(OSError, "disk full"):
                migration.apply_retirement(plan)
        self.assertEqual((home / "prompts/route.md").read_bytes(), prompt)

    def test_backup_parent_symlink_is_rejected(self):
        repo, home, backup, prompt, _ = self.fixture()
        plan = migration.plan_retirement(repo, home, backup, ("prompts",), True)
        outside = backup.parent / "outside"
        outside.mkdir()
        backup.mkdir()
        (backup / "files").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            migration.apply_retirement(plan)
        self.assertEqual((home / "prompts/route.md").read_bytes(), prompt)

    def test_late_second_file_change_rolls_back_first(self):
        repo, home, backup, prompt, _ = self.fixture()
        write(repo / "codex/prompts/usage.md", "root={{POLYTROPOS_ROOT}}\n")
        write(home / "prompts/usage.md", prompt)
        plan = migration.plan_retirement(repo, home, backup, ("prompts",), True)

        def mutate_second(index, action):
            if index == 2:
                write(Path(action["destination"]), "late edit")

        with self.assertRaisesRegex(ValueError, "changed since preview"):
            migration.apply_retirement(plan, before_archive=mutate_second)
        self.assertTrue((home / "prompts/route.md").exists())
        self.assertEqual((home / "prompts/usage.md").read_text(), "late edit")

    def test_rollback_preserves_concurrent_replacement_and_original_backup(self):
        repo, home, backup, prompt, _ = self.fixture()
        write(repo / "codex/prompts/usage.md", "root={{POLYTROPOS_ROOT}}\n")
        write(home / "prompts/usage.md", prompt)
        plan = migration.plan_retirement(repo, home, backup, ("prompts",), True)

        def replace_first_then_break_second(index, action):
            if index == 2:
                write(home / "prompts/route.md", "concurrent replacement")
                write(Path(action["destination"]), "late second edit")

        with self.assertRaisesRegex(RuntimeError, "original payload retained at"):
            migration.apply_retirement(plan, before_archive=replace_first_then_break_second)
        self.assertEqual((home / "prompts/route.md").read_text(), "concurrent replacement")
        retained = backup / "files/prompts/route.md"
        self.assertEqual(retained.read_bytes(), prompt)

    def test_companion_added_after_preview_blocks_before_mutation(self):
        repo, home, backup, _, skill = self.fixture()
        plan = migration.plan_retirement(repo, home, backup, ("skills",), True)
        write(home / "skills/route/later.txt", "mine")
        with self.assertRaisesRegex(ValueError, "changed since preview"):
            migration.apply_retirement(plan)
        self.assertEqual((home / "skills/route/SKILL.md").read_bytes(), skill)

    def test_restore_refuses_collision_and_tampered_payload(self):
        repo,home,backup,_,_=self.fixture(); result=migration.apply_retirement(migration.plan_retirement(repo,home,backup,("prompts",),True))
        write(home/"prompts/route.md","later")
        with self.assertRaises(FileExistsError): migration.restore_legacy(repo,home,backup)
        (home/"prompts/route.md").unlink(); write(Path(result["files"][0]["backup"]),"tampered")
        with self.assertRaisesRegex(ValueError,"tampered"): migration.restore_legacy(repo,home,backup)
        self.assertFalse((home/"prompts/route.md").exists())

    def test_restore_rejects_parent_symlink_and_manifest_path_tampering(self):
        repo, home, backup, _, _ = self.fixture()
        migration.apply_retirement(migration.plan_retirement(repo, home, backup, ("prompts",), True))
        outside = home.parent / "outside-home"
        outside.mkdir()
        (home / "prompts").rmdir()
        (home / "prompts").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            migration.restore_legacy(repo, home, backup)
        (home / "prompts").unlink()

        manifest_path = backup / migration.MANIFEST_NAME
        original = json.loads(manifest_path.read_text())
        mutations = (
            ("relative", "../escape.md"),
            ("destination", str(home / "skills/route/SKILL.md")),
            ("backup", str(backup / "other.md")),
        )
        for key, value in mutations:
            tampered = json.loads(json.dumps(original))
            tampered["files"][0][key] = value
            manifest_path.write_text(json.dumps(tampered))
            with self.assertRaises(ValueError):
                migration.restore_legacy(repo, home, backup)
        manifest_path.write_text(json.dumps(original))

    def test_ownership_hash_proves_noncurrent_copy_and_restores_record(self):
        repo, home, backup, _, _ = self.fixture()
        old = b"an exact older managed payload\n"
        write(home / "prompts/route.md", old)
        key = "home:prompts/route.md"
        record = {
            "component": "prompts",
            "destination": key,
            "installed_hash": migration._sha256(old),
            "source_hash": "older-source",
        }
        write(home / hs.OWNERSHIP_RELATIVE, json.dumps({"version": 1, "files": [record]}))
        plan = migration.plan_retirement(repo, home, backup, ("prompts",), True)
        self.assertEqual(plan["actions"][0]["reason"], "ownership hash matches")
        migration.apply_retirement(plan)
        migration.restore_legacy(repo, home, backup)
        owner = json.loads((home / hs.OWNERSHIP_RELATIVE).read_text())
        self.assertEqual(owner["files"], [record])

    def test_malformed_ownership_manifest_fails_closed(self):
        repo, home, backup, _, _ = self.fixture()
        ownership_path = home / hs.OWNERSHIP_RELATIVE
        malformed = b"{ definitely not json"
        write(ownership_path, malformed)
        with self.assertRaisesRegex(ValueError, "ownership manifest is invalid"):
            migration.plan_retirement(repo, home, backup, ("prompts",), True)
        self.assertEqual(ownership_path.read_bytes(), malformed)
        self.assertTrue((home / "prompts/route.md").exists())

    def test_restore_failure_rolls_back_without_clobber(self):
        repo, home, backup, prompt, _ = self.fixture()
        write(repo / "codex/prompts/usage.md", "root={{POLYTROPOS_ROOT}}\n")
        write(home / "prompts/usage.md", prompt)
        migration.apply_retirement(migration.plan_retirement(repo, home, backup, ("prompts",), True))
        with self.assertRaises(RuntimeError):
            migration.restore_legacy(repo, home, backup, fail_after=1)
        self.assertFalse((home / "prompts/route.md").exists())
        self.assertFalse((home / "prompts/usage.md").exists())

    def test_existing_manifest_rejects_new_or_recreated_eligible_files(self):
        repo, home, backup, prompt, _ = self.fixture()
        old_plan = migration.plan_retirement(repo, home, backup, ("prompts",), True)
        migration.apply_retirement(old_plan)
        write(home / "prompts/route.md", prompt)
        with self.assertRaises(FileExistsError):
            migration.apply_retirement(old_plan)
        (home / "prompts/route.md").unlink()
        write(repo / "codex/prompts/usage.md", "root={{POLYTROPOS_ROOT}}\n")
        write(home / "prompts/usage.md", prompt)
        fresh = migration.plan_retirement(repo, home, backup, ("prompts",), True)
        with self.assertRaises(FileExistsError):
            migration.apply_retirement(fresh)

    def test_symlink_and_backup_discovery_escape_are_rejected(self):
        repo,home,backup,_,_=self.fixture(); target=home/"target"; write(target,"x")
        (home/"prompts/route.md").unlink(); (home/"prompts/route.md").symlink_to(target)
        self.assertTrue(migration.plan_retirement(repo,home,backup,("prompts",),True)["blocked"])
        with self.assertRaisesRegex(ValueError,"discovery root"):
            migration.plan_retirement(repo,home,home.parent/".agents/skills/backups",("prompts",),True)

    def test_backup_parent_alias_into_home_is_rejected(self):
        repo, home, backup, _, _ = self.fixture()
        alias = home.parent / "backup-alias"
        alias.symlink_to(home, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "discovery root"):
            migration.plan_retirement(repo, home, alias / "nested", ("prompts",), True)

    def test_render_lists_companion_conflict_path(self):
        repo, home, backup, _, _ = self.fixture()
        companion = home / "skills/route/mine.txt"
        write(companion, "mine")
        plan = migration.plan_retirement(repo, home, backup, ("skills",), True)
        self.assertIn(f"conflict: {companion.resolve()}", migration.render_plan(plan))

    def test_repeat_apply_is_idempotent_and_update_does_not_resurrect(self):
        repo,home,backup,_,_=self.fixture(); plan=migration.plan_retirement(repo,home,backup,("prompts",),True)
        first=migration.apply_retirement(plan); second=migration.apply_retirement(plan)
        self.assertEqual(first,second)
        fresh = migration.plan_retirement(repo, home, backup, ("prompts",), True)
        self.assertEqual(migration.apply_retirement(fresh), first)
        spec=importlib.util.spec_from_file_location("harness_update",ROOT/"bin/harness_update.py"); hu=importlib.util.module_from_spec(spec); spec.loader.exec_module(hu)
        hu.apply_codex_target(repo,home)
        self.assertFalse((home/"prompts/route.md").exists())

    def test_public_parser_requires_explicit_roots(self):
        with self.assertRaises(SystemExit): hs.main(["retire-legacy","--harness","codex"])
        args=hs.build_parser().parse_args(["restore-legacy","--harness","codex","--repo-root","/r","--codex-home","/h","--backup-root","/b"])
        self.assertEqual(args.harness,"codex")


if __name__ == "__main__": unittest.main()
