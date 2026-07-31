"""Stdlib unittest regression suite for bin/plugin_staleness.py (context-weight kit T12).

SAFETY CONTRACT: every fixture used below lives under a fresh `tempfile.TemporaryDirectory()`
and is handed to the engine via explicit `--repo` / `--installed-manifest` arguments (or the
matching pure-function parameters) -- this file never resolves or reads the caller's real
`~/.claude/plugins/installed_plugins.json`, never opens the real repo's `.git`, and never calls
the stdlib home-resolution helper. The `git` binary, and the real `claude` CLI, are never
invoked anywhere in this file -- git fixtures are plain files written by hand (`.git/HEAD`,
a ref file, or `packed-refs`), matching how the engine itself reads them.

bin/ is not a package; plugin_staleness.py is loaded via importlib by absolute path computed
from this file's own location, mirroring tests/test_routing_scorecard.py and
tests/test_codex_usage.py.
"""

import contextlib
import importlib.util
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ps = _load("plugin_staleness")

DEFAULT_FILES = {
    "skills/demo/SKILL.md": "---\nname: demo\n---\nbody\n",
    "data/pricing.json": '{"models": {}}\n',
    "data/pricing.codex.json": '{"models": {}}\n',
    "CLAUDE.md": "# demo guardrails\n",
    "bin/tool.py": "#!/usr/bin/env python3\nprint('tool')\n",
}


# ---- fixture helpers --------------------------------------------------------------------------

def _write_files(base, files):
    for rel, content in files.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)


def _make_repo(base, name="fake-plugin", marketplace="fake-market", version="1.0.0", files=None):
    repo = base / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    plugin_dir = repo / ".claude-plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.json").write_text(json.dumps({"name": name, "version": version}))
    (plugin_dir / "marketplace.json").write_text(json.dumps({"name": marketplace}))
    _write_files(repo, files if files is not None else DEFAULT_FILES)
    return repo


def _make_install(base, files=None, subdir="install/1.0.0"):
    install = base / subdir
    install.mkdir(parents=True, exist_ok=True)
    _write_files(install, files if files is not None else DEFAULT_FILES)
    return install


def _write_manifest(base, plugin_key, entry, name="manifest.json"):
    path = base / name
    path.write_text(json.dumps({"version": 2, "plugins": {plugin_key: [entry]}}))
    return path


def _add_git_ref_head(repo, sha, ref="refs/heads/main"):
    git_dir = repo / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)
    (git_dir / "HEAD").write_text(f"ref: {ref}\n")
    ref_path = git_dir / ref
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    ref_path.write_text(sha + "\n")


def _add_git_packed_head(repo, sha, ref="refs/heads/main"):
    git_dir = repo / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)
    (git_dir / "HEAD").write_text(f"ref: {ref}\n")
    (git_dir / "packed-refs").write_text(f"# pack-refs\n{sha} {ref}\n")


def _add_git_detached_head(repo, sha):
    git_dir = repo / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)
    (git_dir / "HEAD").write_text(sha + "\n")


def _run_main(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = ps.main(argv)
    return code, buf.getvalue()


# ---- read_plugin_identity ----------------------------------------------------------------------

class ReadPluginIdentityTests(unittest.TestCase):
    def test_reads_name_marketplace_version_from_repo_owned_files(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _make_repo(Path(td), name="acme-plugin", marketplace="acme-market", version="9.9.9")
            self.assertEqual(ps.read_plugin_identity(repo), ("acme-plugin", "acme-market", "9.9.9"))


# ---- resolve_installed_entry -------------------------------------------------------------------

class ResolveInstalledEntryTests(unittest.TestCase):
    def test_missing_manifest_file_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "nope.json"
            self.assertIsNone(ps.resolve_installed_entry(missing, "a@b"))

    def test_malformed_json_returns_none_not_raise(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "manifest.json"
            p.write_text("{not json")
            self.assertIsNone(ps.resolve_installed_entry(p, "a@b"))

    def test_missing_plugins_key_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "manifest.json"
            p.write_text(json.dumps({"version": 2}))
            self.assertIsNone(ps.resolve_installed_entry(p, "a@b"))

    def test_no_entry_for_key_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write_manifest(Path(td), "other@market", {"installPath": "/x", "version": "1.0.0"})
            self.assertIsNone(ps.resolve_installed_entry(p, "a@b"))

    def test_empty_entry_list_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "manifest.json"
            p.write_text(json.dumps({"plugins": {"a@b": []}}))
            self.assertIsNone(ps.resolve_installed_entry(p, "a@b"))

    def test_valid_entry_returns_first_record(self):
        with tempfile.TemporaryDirectory() as td:
            entry = {"installPath": "/x", "version": "1.0.0", "gitCommitSha": "deadbeef"}
            p = _write_manifest(Path(td), "a@b", entry)
            self.assertEqual(ps.resolve_installed_entry(p, "a@b"), entry)


# ---- read_git_head_sha ---------------------------------------------------------------------

class ReadGitHeadShaTests(unittest.TestCase):
    def test_no_git_dir_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(ps.read_git_head_sha(Path(td)))

    def test_ref_head_resolves_via_ref_file(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            _add_git_ref_head(repo, "a" * 40)
            self.assertEqual(ps.read_git_head_sha(repo), "a" * 40)

    def test_ref_head_falls_back_to_packed_refs(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            _add_git_packed_head(repo, "b" * 40)
            self.assertEqual(ps.read_git_head_sha(repo), "b" * 40)

    def test_detached_head_returns_sha_directly(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            _add_git_detached_head(repo, "c" * 40)
            self.assertEqual(ps.read_git_head_sha(repo), "c" * 40)

    def test_unresolvable_ref_returns_none_not_raise(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            git_dir = repo / ".git"
            git_dir.mkdir()
            (git_dir / "HEAD").write_text("ref: refs/heads/nowhere\n")
            self.assertIsNone(ps.read_git_head_sha(repo))

    def test_never_invokes_a_git_binary(self):
        # Structural proof, not just behavioral: the function contains no subprocess/os.system
        # call at all, so there is nothing to invoke a git binary with in the first place.
        source = (BIN_DIR / "plugin_staleness.py").read_text()
        self.assertNotIn("subprocess", source)
        self.assertNotIn("os.system", source)
        self.assertNotIn("os.popen", source)


# ---- compare_files --------------------------------------------------------------------------

class CompareFilesTests(unittest.TestCase):
    def test_identical_content_reports_identical(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base)
            install = _make_install(base)
            statuses = {f["path"]: f["status"] for f in ps.compare_files(repo, install)}
            self.assertTrue(statuses)
            self.assertTrue(all(s == "identical" for s in statuses.values()))

    def test_differing_content_reports_differs(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base)
            files = dict(DEFAULT_FILES)
            files["CLAUDE.md"] = "# stale guardrails (18 days old)\n"
            install = _make_install(base, files=files)
            statuses = {f["path"]: f["status"] for f in ps.compare_files(repo, install)}
            self.assertEqual(statuses["CLAUDE.md"], "DIFFERS")
            self.assertEqual(statuses["bin/tool.py"], "identical")

    def test_file_only_in_repo_reports_missing(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            files = dict(DEFAULT_FILES)
            files["bin/new_tool.py"] = "print('new')\n"
            repo = _make_repo(base, files=files)
            install = _make_install(base)  # no bin/new_tool.py
            statuses = {f["path"]: f["status"] for f in ps.compare_files(repo, install)}
            self.assertEqual(statuses["bin/new_tool.py"], "missing")

    def test_file_only_in_install_reports_missing(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base)
            install_files = dict(DEFAULT_FILES)
            install_files["bin/removed_from_repo.py"] = "print('old')\n"
            install = _make_install(base, files=install_files)
            statuses = {f["path"]: f["status"] for f in ps.compare_files(repo, install)}
            self.assertEqual(statuses["bin/removed_from_repo.py"], "missing")

    def test_missing_install_dir_reports_everything_missing(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base)
            nonexistent = base / "no-such-install-dir"
            statuses = {f["path"]: f["status"] for f in ps.compare_files(repo, nonexistent)}
            self.assertTrue(statuses)
            self.assertTrue(all(s == "missing" for s in statuses.values()))

    def test_none_install_dir_reports_everything_missing(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base)
            statuses = {f["path"]: f["status"] for f in ps.compare_files(repo, None)}
            self.assertTrue(statuses)
            self.assertTrue(all(s == "missing" for s in statuses.values()))


# ---- build_remedy (byte-exact, per the brief's pinned string) --------------------------------

class BuildRemedyTests(unittest.TestCase):
    def test_remedy_is_byte_exact(self):
        expected = (
            'stale install — bump "version" in .claude-plugin/plugin.json, then: '
            "claude plugin marketplace update acme-market && claude plugin update "
            "acme-plugin@acme-market (restart to apply)"
        )
        self.assertEqual(ps.build_remedy("acme-plugin", "acme-market"), expected)


# ---- check_staleness: the three exit-code outcomes --------------------------------------------

class CheckStalenessNotInstalledTests(unittest.TestCase):
    def test_missing_manifest_file_is_not_installed_exit_0(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base)
            manifest = base / "does-not-exist.json"
            result = ps.check_staleness(repo, manifest)
            self.assertFalse(result["installed"])
            self.assertFalse(result["drifted"])
            self.assertEqual(result["exit_code"], ps.EXIT_OK)
            self.assertEqual(result["exit_code"], 0)

    def test_manifest_present_but_no_entry_is_not_installed_exit_0(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base, name="fake-plugin", marketplace="fake-market")
            manifest = _write_manifest(base, "other-plugin@other-market", {"installPath": str(base), "version": "1.0.0"})
            result = ps.check_staleness(repo, manifest)
            self.assertFalse(result["installed"])
            self.assertEqual(result["exit_code"], 0)
            self.assertNotIn("remedy", result)

    def test_render_markdown_not_installed_names_the_key_and_never_tracebacks(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base, name="fake-plugin", marketplace="fake-market")
            manifest = base / "absent.json"
            result = ps.check_staleness(repo, manifest)
            md = ps.render_markdown(result)
            self.assertIn("not installed", md)
            self.assertIn("fake-plugin@fake-market", md)
            self.assertNotIn("Traceback", md)


class CheckStalenessInSyncTests(unittest.TestCase):
    def test_identical_files_matching_version_and_git_sha_is_in_sync_exit_0(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base, name="fake-plugin", marketplace="fake-market", version="1.0.0")
            sha = "d" * 40
            _add_git_ref_head(repo, sha)
            install = _make_install(base)
            entry = {"installPath": str(install), "version": "1.0.0", "gitCommitSha": sha}
            manifest = _write_manifest(base, "fake-plugin@fake-market", entry)

            result = ps.check_staleness(repo, manifest)
            self.assertTrue(result["installed"])
            self.assertFalse(result["drifted"])
            self.assertEqual(result["exit_code"], ps.EXIT_OK)
            self.assertEqual(result["files_diff_count"], 0)
            self.assertTrue(result["version_match"])
            self.assertTrue(result["git_match"])
            self.assertNotIn("remedy", result)

    def test_in_sync_without_git_dir_degrades_gracefully(self):
        # No .git directory in the repo fixture -- git comparison must not be possible, and
        # must not be required for an in-sync verdict, and must never raise.
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base, name="fake-plugin", marketplace="fake-market", version="2.0.0")
            install = _make_install(base)
            entry = {"installPath": str(install), "version": "2.0.0", "gitCommitSha": "e" * 40}
            manifest = _write_manifest(base, "fake-plugin@fake-market", entry)

            result = ps.check_staleness(repo, manifest)
            self.assertIsNone(result["repo_git_sha"])
            self.assertFalse(result["git_comparable"])
            self.assertIsNone(result["git_match"])
            self.assertFalse(result["drifted"])
            self.assertEqual(result["exit_code"], 0)


class CheckStalenessDriftedTests(unittest.TestCase):
    def test_file_content_diff_alone_drifts_exit_3(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base, name="fake-plugin", marketplace="fake-market", version="1.0.0")
            install_files = dict(DEFAULT_FILES)
            install_files["CLAUDE.md"] = "# 18-day-old guardrails\n"
            install = _make_install(base, files=install_files)
            entry = {"installPath": str(install), "version": "1.0.0"}
            manifest = _write_manifest(base, "fake-plugin@fake-market", entry)

            result = ps.check_staleness(repo, manifest)
            self.assertTrue(result["drifted"])
            self.assertEqual(result["exit_code"], ps.EXIT_DRIFTED)
            self.assertEqual(result["exit_code"], 3)
            self.assertTrue(result["version_match"])  # version alone would have said "fine"
            self.assertIn("remedy", result)
            self.assertEqual(result["remedy"], ps.build_remedy("fake-plugin", "fake-market"))

    def test_version_mismatch_alone_drifts_exit_3(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base, name="fake-plugin", marketplace="fake-market", version="2.0.0")
            install = _make_install(base)  # byte-identical files
            entry = {"installPath": str(install), "version": "1.0.0"}
            manifest = _write_manifest(base, "fake-plugin@fake-market", entry)

            result = ps.check_staleness(repo, manifest)
            self.assertEqual(result["files_diff_count"], 0)
            self.assertFalse(result["version_match"])
            self.assertTrue(result["drifted"])
            self.assertEqual(result["exit_code"], 3)

    def test_git_sha_mismatch_alone_is_sha_stale_not_drifted_exit_0(self):
        # A squash-merge or rebase rewrites the recorded commit id for an otherwise-unchanged
        # tree -- files and version both still match, so this must NOT be exit 3. See the
        # dedicated CheckStalenessShaStaleTests class below for full coverage of this status.
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base, name="fake-plugin", marketplace="fake-market", version="1.0.0")
            _add_git_ref_head(repo, "f" * 40)
            install = _make_install(base)
            entry = {"installPath": str(install), "version": "1.0.0", "gitCommitSha": "1" * 40}
            manifest = _write_manifest(base, "fake-plugin@fake-market", entry)

            result = ps.check_staleness(repo, manifest)
            self.assertEqual(result["files_diff_count"], 0)
            self.assertTrue(result["version_match"])
            self.assertTrue(result["git_comparable"])
            self.assertFalse(result["git_match"])
            self.assertEqual(result["status"], "SHA STALE")
            self.assertFalse(result["drifted"])
            self.assertEqual(result["exit_code"], 0)

    def test_render_markdown_drifted_includes_status_and_remedy(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base, name="fake-plugin", marketplace="fake-market", version="2.0.0")
            install = _make_install(base)
            entry = {"installPath": str(install), "version": "1.0.0"}
            manifest = _write_manifest(base, "fake-plugin@fake-market", entry)

            result = ps.check_staleness(repo, manifest)
            md = ps.render_markdown(result)
            self.assertIn("status: DRIFTED", md)
            self.assertIn("remedy:", md)
            self.assertIn("bump \"version\" in .claude-plugin/plugin.json", md)


# ---- check_staleness: SHA STALE (content current, only the recorded commit id is stale) ------

class CheckStalenessShaStaleTests(unittest.TestCase):
    def _sha_stale_fixture(self, td):
        base = Path(td)
        repo = _make_repo(base, name="fake-plugin", marketplace="fake-market", version="1.0.0")
        _add_git_ref_head(repo, "6" * 40)  # e.g. the squash-merge's new HEAD
        install = _make_install(base)  # byte-identical files
        entry = {
            "installPath": str(install),
            "version": "1.0.0",
            "gitCommitSha": "e" * 40,  # the SHA recorded at install time -- now stale
        }
        manifest = _write_manifest(base, "fake-plugin@fake-market", entry)
        return repo, manifest

    def test_identical_files_matching_version_differing_head_is_sha_stale_exit_0(self):
        with tempfile.TemporaryDirectory() as td:
            repo, manifest = self._sha_stale_fixture(td)
            result = ps.check_staleness(repo, manifest)

            self.assertEqual(result["files_diff_count"], 0)
            self.assertTrue(result["version_match"])
            self.assertTrue(result["git_comparable"])
            self.assertFalse(result["git_match"])
            self.assertEqual(result["status"], "SHA STALE")
            self.assertFalse(result["drifted"])
            self.assertEqual(result["exit_code"], ps.EXIT_OK)
            self.assertEqual(result["exit_code"], 0)
            self.assertNotIn("remedy", result)
            self.assertIn("note", result)
            self.assertIn("no action is required", result["note"].lower())

    def test_sha_stale_report_omits_remedy_and_states_no_action_required(self):
        with tempfile.TemporaryDirectory() as td:
            repo, manifest = self._sha_stale_fixture(td)
            result = ps.check_staleness(repo, manifest)
            md = ps.render_markdown(result)

            self.assertIn("status: SHA STALE", md)
            # The DRIFTED remedy's pinned CLI text and its "bump the version" framing must be
            # entirely absent -- printing it here is the false alarm this status exists to kill.
            self.assertNotIn("remedy:", md)
            self.assertNotIn("claude plugin marketplace update", md)
            self.assertNotIn("claude plugin update", md)
            self.assertNotIn('bump "version"', md)
            self.assertIn("no action is required", md.lower())
            # The evidence (version line, git HEAD line, install path, per-file list) must still
            # be visible -- only the status/remedy portion of the report changes.
            self.assertIn("version: repo `1.0.0` vs installed `1.0.0` — match", md)
            self.assertIn("MISMATCH", md)  # the git HEAD line still flags the differing SHA
            self.assertIn("identical", md)

    def test_real_drift_wins_over_matching_sha(self):
        # One file differs; the recorded git HEAD matches. File difference must dominate.
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base, name="fake-plugin", marketplace="fake-market", version="1.0.0")
            sha = "a" * 40
            _add_git_ref_head(repo, sha)
            install_files = dict(DEFAULT_FILES)
            install_files["CLAUDE.md"] = "# stale content despite matching HEAD\n"
            install = _make_install(base, files=install_files)
            entry = {"installPath": str(install), "version": "1.0.0", "gitCommitSha": sha}
            manifest = _write_manifest(base, "fake-plugin@fake-market", entry)

            result = ps.check_staleness(repo, manifest)
            self.assertTrue(result["git_comparable"])
            self.assertTrue(result["git_match"])
            self.assertGreater(result["files_diff_count"], 0)
            self.assertEqual(result["status"], "DRIFTED")
            self.assertTrue(result["drifted"])
            self.assertEqual(result["exit_code"], 3)
            self.assertIn("remedy", result)

    def test_file_difference_and_differing_head_is_drifted(self):
        # Both a file difference AND a differing recorded HEAD -- file difference must still be
        # what decides the status.
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base, name="fake-plugin", marketplace="fake-market", version="1.0.0")
            _add_git_ref_head(repo, "7" * 40)
            install_files = dict(DEFAULT_FILES)
            install_files["CLAUDE.md"] = "# stale content AND stale HEAD\n"
            install = _make_install(base, files=install_files)
            entry = {"installPath": str(install), "version": "1.0.0", "gitCommitSha": "9" * 40}
            manifest = _write_manifest(base, "fake-plugin@fake-market", entry)

            result = ps.check_staleness(repo, manifest)
            self.assertTrue(result["git_comparable"])
            self.assertFalse(result["git_match"])
            self.assertGreater(result["files_diff_count"], 0)
            self.assertEqual(result["status"], "DRIFTED")
            self.assertTrue(result["drifted"])
            self.assertEqual(result["exit_code"], 3)
            self.assertIn("remedy", result)

    def test_version_mismatch_with_identical_files_and_matching_head_is_drifted(self):
        # A version difference is a real install difference, even with identical files and a
        # matching recorded HEAD -- it must not be swallowed into SHA STALE.
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base, name="fake-plugin", marketplace="fake-market", version="2.0.0")
            sha = "b" * 40
            _add_git_ref_head(repo, sha)
            install = _make_install(base)  # byte-identical files
            entry = {"installPath": str(install), "version": "1.0.0", "gitCommitSha": sha}
            manifest = _write_manifest(base, "fake-plugin@fake-market", entry)

            result = ps.check_staleness(repo, manifest)
            self.assertEqual(result["files_diff_count"], 0)
            self.assertTrue(result["git_comparable"])
            self.assertTrue(result["git_match"])
            self.assertFalse(result["version_match"])
            self.assertEqual(result["status"], "DRIFTED")
            self.assertTrue(result["drifted"])
            self.assertEqual(result["exit_code"], 3)


# ---- CLI (main) -------------------------------------------------------------------------------

class MainCliTests(unittest.TestCase):
    def test_json_in_sync_round_trips_and_exits_0(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base, name="fake-plugin", marketplace="fake-market", version="1.0.0")
            install = _make_install(base)
            entry = {"installPath": str(install), "version": "1.0.0"}
            manifest = _write_manifest(base, "fake-plugin@fake-market", entry)

            code, out = _run_main(["--repo", str(repo), "--installed-manifest", str(manifest), "--json"])
            self.assertEqual(code, 0)
            parsed = json.loads(out)
            self.assertTrue(parsed["installed"])
            self.assertFalse(parsed["drifted"])

    def test_json_drifted_round_trips_and_exits_3(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base, name="fake-plugin", marketplace="fake-market", version="3.0.0")
            install = _make_install(base)
            entry = {"installPath": str(install), "version": "1.0.0"}
            manifest = _write_manifest(base, "fake-plugin@fake-market", entry)

            code, out = _run_main(["--repo", str(repo), "--installed-manifest", str(manifest), "--json"])
            self.assertEqual(code, 3)
            parsed = json.loads(out)
            self.assertTrue(parsed["drifted"])
            self.assertIn("remedy", parsed)

    def test_json_not_installed_round_trips_and_exits_0(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base, name="fake-plugin", marketplace="fake-market")
            manifest = base / "absent.json"

            code, out = _run_main(["--repo", str(repo), "--installed-manifest", str(manifest), "--json"])
            self.assertEqual(code, 0)
            parsed = json.loads(out)
            self.assertFalse(parsed["installed"])

    def test_markdown_default_output_for_each_outcome(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = _make_repo(base, name="fake-plugin", marketplace="fake-market", version="1.0.0")
            install = _make_install(base)

            # in sync
            manifest_ok = _write_manifest(
                base, "fake-plugin@fake-market", {"installPath": str(install), "version": "1.0.0"}, name="ok.json"
            )
            code, out = _run_main(["--repo", str(repo), "--installed-manifest", str(manifest_ok)])
            self.assertEqual(code, 0)
            self.assertIn("status: IN SYNC", out)

            # drifted (version bump not yet installed)
            manifest_stale = _write_manifest(
                base, "fake-plugin@fake-market", {"installPath": str(install), "version": "0.9.0"}, name="stale.json"
            )
            code, out = _run_main(["--repo", str(repo), "--installed-manifest", str(manifest_stale)])
            self.assertEqual(code, 3)
            self.assertIn("status: DRIFTED", out)

            # not installed
            code, out = _run_main(["--repo", str(repo), "--installed-manifest", str(base / "nope.json")])
            self.assertEqual(code, 0)
            self.assertIn("not installed", out)


# ---- static hygiene: mirrors the task's own verify-command checks for extra regression safety --

class SourceHygieneTests(unittest.TestCase):
    def setUp(self):
        self.source = (BIN_DIR / "plugin_staleness.py").read_text()
        self.lines = self.source.splitlines()

    def test_zero_stdlib_home_helper_uses(self):
        self.assertNotIn("Path.home()", self.source)

    def test_no_real_cli_invocation_outside_comments(self):
        pattern = re.compile(r"subprocess|claude plugin (update|install)")
        offenders = [ln for ln in self.lines if pattern.search(ln) and not ln.strip().startswith("#")]
        self.assertEqual(offenders, [], f"found real-CLI-shaped code: {offenders!r}")

    def test_module_docstring_states_read_only_and_never_runs_the_remedy(self):
        self.assertIn("read-only", self.source.lower())
        self.assertIn("never runs them", self.source)


if __name__ == "__main__":
    unittest.main()
