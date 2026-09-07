"""Runtime data lives outside the package, and credential shapes do not travel (step 13).

Two shared primitives, one file, because they answer the same question from opposite ends:
`bin/runtime_data.py` decides WHERE private data is kept, `bin/redact.py` decides WHAT may
leave in plain text.

Confirmed evidence behind both: synthetic inbox canaries survived persistence and summary
dispatch, and memory files were created 0644 in directories 0755 under `umask 022` — inside a
repository that is also a distributable, cached, frequently cloud-synced plugin.

Every fixture here is a temp directory with a fake HOME. Nothing reads or writes a real store.
"""

import importlib.util
import os
import stat
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_privacy", ROOT / "bin" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rd = _load("runtime_data")
redact = _load("redact")


class _Temp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.repo = self.dir / "checkout"
        self.repo.mkdir()
        self.home = self.dir / "home"
        self.home.mkdir()
        self.env = {"HOME": str(self.home)}


class DataHomeTests(_Temp):
    def test_each_os_gets_its_own_application_data_location(self):
        cases = {
            "darwin": self.home / "Library" / "Application Support" / "polytropos",
            "linux": self.home / ".local" / "share" / "polytropos",
        }
        for platform, expected in cases.items():
            with self.subTest(platform=platform):
                self.assertEqual(rd.user_data_home(env=self.env, platform=platform), expected)

    def test_xdg_is_honoured_where_it_applies(self):
        env = dict(self.env, XDG_DATA_HOME=str(self.dir / "xdg"))
        self.assertEqual(rd.user_data_home(env=env, platform="linux"),
                         self.dir / "xdg" / "polytropos")

    def test_two_checkouts_of_one_repo_do_not_share_a_store(self):
        other = self.dir / "elsewhere" / "checkout"
        other.mkdir(parents=True)
        first, second = rd.project_namespace(self.repo), rd.project_namespace(other)
        self.assertNotEqual(first, second)
        # ...and both are still recognizable to a person looking at a file browser.
        self.assertTrue(first.startswith("checkout-"))
        self.assertTrue(second.startswith("checkout-"))


class ResolutionTests(_Temp):
    def test_a_fresh_install_keeps_runtime_data_out_of_the_plugin_tree(self):
        resolved = rd.resolve_store("memory", self.repo, env=self.env, platform="darwin")
        self.assertEqual(resolved["origin"], "user-data-root")
        self.assertNotIn(str(self.repo), str(resolved["path"]))

    def test_an_existing_in_tree_store_keeps_being_used(self):
        # Continuity beats tidiness: an upgrade that relocated a user's notes would be
        # indistinguishable, from their side, from one that lost them.
        legacy = self.repo / "memory"
        legacy.mkdir()
        (legacy / "fact.md").write_text("something the user wrote")
        resolved = rd.resolve_store("memory", self.repo, env=self.env, platform="darwin")
        self.assertEqual(resolved["path"], legacy)
        self.assertEqual(resolved["origin"], "legacy-in-tree")
        self.assertIn("migrate", resolved["note"])

    def test_an_empty_in_tree_directory_is_not_a_store(self):
        (self.repo / "memory").mkdir()
        self.assertEqual(
            rd.resolve_store("memory", self.repo, env=self.env, platform="darwin")["origin"],
            "user-data-root",
        )

    def test_an_explicit_data_home_wins_over_everything(self):
        legacy = self.repo / "memory"
        legacy.mkdir()
        (legacy / "fact.md").write_text("x")
        env = dict(self.env, **{rd.DATA_HOME_VAR: str(self.dir / "chosen")})
        resolved = rd.resolve_store("memory", self.repo, env=env, platform="darwin")
        self.assertEqual(resolved["origin"], "env")
        self.assertIn(str(self.dir / "chosen"), str(resolved["path"]))


class PrivateCreationTests(_Temp):
    def test_created_directories_are_owner_only(self):
        target = self.dir / "a" / "b" / "c"
        rd.ensure_private(target)
        for path in (self.dir / "a", self.dir / "a" / "b", target):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode) & 0o077, 0, path)

    def test_an_existing_ancestor_keeps_the_mode_it_had(self):
        # Re-permissioning a directory somebody else made — a home dir, a synced folder — is
        # not this function's business and could break unrelated things.
        outer = self.dir / "outer"
        outer.mkdir(mode=0o755)
        before = stat.S_IMODE(outer.stat().st_mode)
        rd.ensure_private(outer / "inner")
        self.assertEqual(stat.S_IMODE(outer.stat().st_mode), before)
        self.assertEqual(stat.S_IMODE((outer / "inner").stat().st_mode) & 0o077, 0)


class MigrationTests(_Temp):
    def _legacy(self, *files):
        legacy = self.repo / "memory"
        (legacy / "facts").mkdir(parents=True)
        for name in files:
            (legacy / "facts" / name).write_text(f"content of {name}")
        return legacy

    def test_a_dry_run_reports_and_writes_nothing(self):
        self._legacy("a.md", "b.md")
        report = rd.migrate("memory", self.repo, env=self.env, platform="darwin")
        self.assertFalse(report["applied"])
        self.assertEqual(sorted(report["copy"]), ["facts/a.md", "facts/b.md"])
        self.assertFalse(Path(report["target"]).exists())

    def test_applying_copies_and_never_removes_the_original(self):
        legacy = self._legacy("a.md")
        report = rd.migrate("memory", self.repo, env=self.env, platform="darwin", apply=True)
        self.assertEqual(report["copied"], ["facts/a.md"])
        self.assertTrue((Path(report["target"]) / "facts" / "a.md").is_file())
        # Reversible by deleting the copy; a mistake costs disk, not data.
        self.assertTrue((legacy / "facts" / "a.md").is_file())

    def test_migrated_files_are_owner_only(self):
        self._legacy("a.md")
        report = rd.migrate("memory", self.repo, env=self.env, platform="darwin", apply=True)
        mode = (Path(report["target"]) / "facts" / "a.md").stat().st_mode
        self.assertEqual(stat.S_IMODE(mode) & 0o077, 0)

    def test_an_existing_destination_file_is_a_conflict_and_is_not_overwritten(self):
        self._legacy("a.md")
        target = rd.user_data_home(env=self.env, platform="darwin") / \
            rd.project_namespace(self.repo) / "memory" / "facts"
        target.mkdir(parents=True)
        (target / "a.md").write_text("already here")

        report = rd.migrate("memory", self.repo, env=self.env, platform="darwin", apply=True)

        self.assertEqual(report["conflicts"], ["facts/a.md"])
        self.assertEqual(report["copied"], [])
        self.assertEqual((target / "a.md").read_text(), "already here")

    def test_migrating_an_absent_store_is_not_an_error(self):
        report = rd.migrate("memory", self.repo, env=self.env, platform="darwin", apply=True)
        self.assertFalse(report["present"])
        self.assertEqual(report["copied"], [])


class RetentionTests(_Temp):
    def _store(self):
        path = self.repo / "telemetry"
        path.mkdir()
        (path / "old.json").write_text("{}")
        (path / "new.json").write_text("{}")
        os.utime(path / "old.json", (0, 0))
        return path

    def test_forget_is_a_dry_run_by_default(self):
        store = self._store()
        report = rd.forget("telemetry", self.repo, env=self.env, platform="darwin")
        self.assertEqual(sorted(report["matched"]), ["new.json", "old.json"])
        self.assertEqual(report["removed"], [])
        self.assertTrue((store / "old.json").is_file())

    def test_forget_is_scoped_by_age(self):
        store = self._store()
        report = rd.forget("telemetry", self.repo, older_than_days=1, env=self.env,
                           platform="darwin", apply=True)
        self.assertEqual(report["removed"], ["old.json"])
        self.assertTrue((store / "new.json").is_file())

    def test_export_copies_out_without_changing_the_store(self):
        store = self._store()
        report = rd.export("telemetry", self.repo, self.dir / "out", env=self.env,
                           platform="darwin")
        self.assertEqual(sorted(report["copied"]), ["new.json", "old.json"])
        self.assertTrue((self.dir / "out" / "telemetry" / "old.json").is_file())
        self.assertTrue((store / "old.json").is_file())


class RedactionTests(unittest.TestCase):
    def test_published_credential_shapes_are_caught(self):
        cases = {
            "aws-access-key-id": "AKIAIOSFODNN7EXAMPLE",
            "github-token": "ghp_abcdefghijklmnopqrstuvwxyz012345",
            "anthropic-key": "sk-ant-api03-aaaaaaaaaaaaaaaaaaaaaaaa",
            "google-api-key": "AIza" + "b" * 35,
            "slack-token": "xoxb-123456789012-abcdefghijkl",
            "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N",
            "private-key": "-----BEGIN RSA PRIVATE KEY-----",
        }
        for kind, value in cases.items():
            with self.subTest(kind=kind):
                outcome = redact.redact(f"note: {value} end", limit=None)
                self.assertNotIn(value, outcome["text"])
                self.assertIn(kind, outcome["redactions"])

    def test_a_home_grown_secret_is_caught_by_its_name_not_its_shape(self):
        # `db_password = hunter2` has no distinctive value shape, only a distinctive key. The
        # leading-prefix case matters: `_` is a word character, so a plain \b misses it.
        for line in ("db_password = hunter2", "MY_API_KEY=abc123", "client_secret: s3cr3t"):
            with self.subTest(line=line):
                outcome = redact.redact(line, limit=None)
                self.assertIn("assigned-secret", outcome["redactions"])

    def test_ordinary_prose_is_left_alone(self):
        for line in ("call Bob about the renewal", "review the Q3 deck",
                     "notes: discussed pricing with the vendor", "check /usr/local/bin/x"):
            with self.subTest(line=line):
                self.assertEqual(redact.redact(line, limit=None)["text"], line)

    def test_the_report_never_contains_what_it_found(self):
        secret = "ghp_abcdefghijklmnopqrstuvwxyz012345"
        outcome = redact.redact(f"token {secret}", limit=None)
        rendered = redact.describe({"redactions": outcome["redactions"], "truncated": 0})
        self.assertNotIn(secret, rendered)
        self.assertNotIn(secret, str(outcome["redactions"]))

    def test_it_refuses_to_claim_more_than_shape_matching_can_deliver(self):
        rendered = redact.describe({"redactions": {"jwt": 1}, "truncated": 0})
        self.assertIn("cannot prove no secret remains", rendered)

    def test_redaction_happens_before_truncation(self):
        # Cutting first could leave the tail of a key in the retained half, where nothing
        # would match it any more.
        secret = "ghp_" + "z" * 40
        outcome = redact.redact("x" * 40 + " " + secret, limit=50)
        self.assertNotIn("zzzz", outcome["text"])
        self.assertTrue(outcome["truncated"])

    def test_a_field_is_bounded_even_when_it_is_clean(self):
        outcome = redact.redact("y" * 5000, limit=100)
        self.assertTrue(outcome["truncated"])
        self.assertLess(len(outcome["text"]), 200)
        self.assertEqual(outcome["original_length"], 5000)


if __name__ == "__main__":
    unittest.main()
