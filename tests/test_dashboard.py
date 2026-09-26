"""Stdlib unittest suite for bin/dashboard.py (observability-dashboard T2).

bin/ is not a package; dashboard.py is loaded via importlib by absolute path computed from this
file's own location (the house pattern).

SAFETY CONTRACT (binds every test in this file):

* The data home AND the home directory are pinned to temp dirs for the whole module
  (`setUpModule`, the tests/test_copilot_execute.py idiom), so nothing any code path resolves
  through bin/runtime_data.py -- or through the scrubber's home lookup -- can reach the real
  per-user data root or the real home.
* Every `build` passes `--out-dir`, `--projects-dir` (an empty temp dir) and `--no-git`, and
  runs from inside a synthetic checkout. Namespaces, ledgers and checkouts are built by
  `dashboard.synthetic_world` inside temp dirs.
* Nothing here spawns a process: git verbs are disabled, or answered by an injected runner.
* A built `index.html` is only ever probed with assertions, never printed.
"""

import contextlib
import html
import importlib.util
import io
import json
import os
import re
import stat
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
DASHBOARD_PATH = BIN_DIR / "dashboard.py"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


db = _load("dashboard")
rd = _load("runtime_data")

_DATA_HOME = None
_FAKE_HOME = None
_ENV_PATCH = None


def setUpModule():
    global _DATA_HOME, _FAKE_HOME, _ENV_PATCH
    _DATA_HOME = tempfile.TemporaryDirectory(prefix="polytropos-test-data-")
    _FAKE_HOME = tempfile.TemporaryDirectory(prefix="polytropos-test-home-")
    _ENV_PATCH = mock.patch.dict(os.environ, {"POLYTROPOS_DATA_HOME": _DATA_HOME.name,
                                              "HOME": _FAKE_HOME.name})
    _ENV_PATCH.start()


def tearDownModule():
    _ENV_PATCH.stop()
    _DATA_HOME.cleanup()
    _FAKE_HOME.cleanup()


EXACT_CSP_META = ('<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
                  'style-src \'unsafe-inline\'; img-src data:">')
NETWORK_TRIPWIRES = ("<script", "src=", 'href="http', 'href="//', "@import", "url(")
EMPTY_CLASSES = {"mapped": [], "unmapped": [], "residue": {"count": 0, "sample": []}}

# The panel ids, pinned for the whole kit in page order (TASKS.md, T2 brief item 5). Kept here
# rather than in the engine: `bin/*.py` is scanned by the evals and training stores'
# one-engine guards, which read a quoted store name as a module naming that store.
PINNED_PANEL_ORDER = ("namespaces", "attempts", "scorecard", "kits", "telemetry", "journal",
                      "evals", "training", "rsi", "bounds")


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = db.main(argv)
    return rc, out.getvalue(), err.getvalue()


def _without_built_at(text):
    return [line for line in text.splitlines() if "data-built-at" not in line]


def _chmod_restorable(case, path, mode):
    original = stat.S_IMODE(os.lstat(path).st_mode)
    os.chmod(path, mode)
    case.addCleanup(os.chmod, path, original)


class _WorldCase(unittest.TestCase):
    """A fresh synthetic world per test, with the process sitting inside its checkout."""

    residue = 30

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="dashboard-test-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.world = db.synthetic_world(self.tmp / "world", residue=self.residue)
        self.projects = self.tmp / "projects"
        self.projects.mkdir()
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.world["checkout"])

    def build_argv(self, out, *extra):
        return ["build", "--data-home", str(self.world["data_home"]), "--out-dir", str(out),
                "--checkout", str(self.world["checkout"]), "--projects-dir", str(self.projects),
                "--no-git", *extra]

    def build(self, out_name="out", *extra):
        out = self.tmp / out_name
        rc, stdout, stderr = _run(self.build_argv(out, *extra))
        return rc, out, stdout, stderr

    @staticmethod
    def page(out):
        return (out / "index.html").read_text(encoding="utf-8")

    @staticmethod
    def receipt(out):
        return json.loads((out / "build.json").read_text(encoding="utf-8"))

    def classify(self, data_home=None, caps=None):
        return db.classify_namespaces(data_home or self.world["data_home"],
                                      [str(self.world["checkout"])],
                                      caps or db.default_caps())


# ---------------------------------------------------------------------------------------------
# Namespace classification.

class ClassificationTests(_WorldCase):

    def test_synthetic_world_is_one_mapped_one_unmapped_thirty_residue(self):
        classes, _notes = self.classify()
        self.assertEqual(len(classes["mapped"]), 1)
        mapped = classes["mapped"][0]
        self.assertEqual(mapped["namespace"], self.world["namespace"])
        self.assertEqual(mapped["kind"], "checkout")
        self.assertEqual(mapped["checkout"], str(self.world["checkout"]))
        self.assertEqual(mapped["stores"], ["attempts"])
        self.assertEqual(classes["unmapped"], [{"namespace": db.UNMAPPED_NAMESPACE,
                                                "stores": ["attempts"]}])
        self.assertEqual(classes["residue"]["count"], 30)
        self.assertEqual(classes["residue"]["sample"], sorted(self.world["residue"])[:3])

    def test_residue_is_listed_once_and_never_opened(self):
        victim = sorted(self.world["residue"])[-1]  # outside the three-name sample
        events = self.world["data_home"] / victim / "attempts" / "kit" / "events.jsonl"
        self.assertTrue(events.is_file())
        if os.geteuid() != 0:
            _chmod_restorable(self, events, 0)
        listed = []
        real_listdir = os.listdir

        def spy(path="."):
            listed.append(os.fspath(path))
            return real_listdir(path)

        with mock.patch("os.listdir", spy):
            rc, out, _stdout, _stderr = self.build()
        self.assertEqual(rc, 0)
        receipt = self.receipt(out)
        self.assertEqual(receipt["classes"]["residue"]["count"], 30)
        for note in receipt["notes"]:
            self.assertNotIn(victim, note)
            self.assertNotIn("PermissionError", note)
        self.assertNotIn(victim, self.page(out))
        residue_listings = [path for path in listed
                            if any(name in path for name in self.world["residue"])]
        self.assertEqual(len(residue_listings), 30, residue_listings[:5])
        for path in residue_listings:
            self.assertEqual(Path(path).parent, self.world["data_home"])

    def test_symlink_entries_are_skipped_with_a_note_and_never_followed(self):
        data_home = self.world["data_home"]
        residue_shaped = "tmpzzzzzzzz-00000000"
        os.symlink(data_home / sorted(self.world["residue"])[0], data_home / residue_shaped)
        os.symlink(data_home / self.world["namespace"], data_home / "linked-namespace")
        classes, notes = self.classify()
        self.assertEqual(classes["residue"]["count"], 30)
        self.assertEqual(len(classes["mapped"]), 1)
        self.assertNotIn("linked-namespace", [row["namespace"] for row in classes["unmapped"]])
        skipped = [note for note in notes if "not a directory without following links" in note]
        self.assertEqual(len(skipped), 1, notes)
        self.assertIn(residue_shaped, skipped[0])
        self.assertIn("linked-namespace", skipped[0])
        self.assertIn("2 data-home entries skipped", skipped[0])

    def test_residue_needs_the_name_and_nothing_but_an_attempts_store(self):
        data_home = self.world["data_home"]
        busy = "tmpbusybusy-0000beef"       # residue-shaped name, but a second store
        empty = "tmpemptyemp-0000cafe"      # residue-shaped name, nothing inside at all
        (data_home / busy / "attempts").mkdir(parents=True)
        (data_home / busy / "telemetry").mkdir()
        (data_home / empty).mkdir()
        (data_home / "kept-name-0000f00d" / "attempts").mkdir(parents=True)
        classes, _notes = self.classify()
        unmapped = {row["namespace"]: row["stores"] for row in classes["unmapped"]}
        self.assertEqual(unmapped[busy], sorted(["attempts", "telemetry"], key=rd.STORES.index))
        self.assertEqual(unmapped["kept-name-0000f00d"], ["attempts"])
        self.assertNotIn(empty, unmapped)
        self.assertEqual(classes["residue"]["count"], 31)

    def test_absent_or_file_data_home_is_a_note_and_empty_classes(self):
        classes, notes = self.classify(data_home=self.tmp / "nowhere")
        self.assertEqual(classes, EMPTY_CLASSES)
        self.assertTrue(any("does not exist" in note for note in notes), notes)
        a_file = self.tmp / "data-home-file"
        a_file.write_text("not a directory\n")
        classes, notes = self.classify(data_home=a_file)
        self.assertEqual(classes, EMPTY_CLASSES)
        self.assertTrue(any("is not a directory" in note for note in notes), notes)

    def test_absent_data_home_still_builds_a_page(self):
        out = self.tmp / "out"
        argv = self.build_argv(out)
        argv[argv.index("--data-home") + 1] = str(self.tmp / "nowhere")
        rc, _stdout, _stderr = _run(argv)
        self.assertEqual(rc, 0)
        receipt = self.receipt(out)
        self.assertEqual(receipt["classes"]["residue"]["count"], 0)
        self.assertTrue(any("does not exist" in note for note in receipt["notes"]))
        self.assertIn("No namespaces were found in the data home.", self.page(out))

    @unittest.skipIf(os.geteuid() == 0, "root reads through chmod 0")
    def test_unlistable_namespace_and_data_home_are_notes(self):
        unmapped = self.world["data_home"] / db.UNMAPPED_NAMESPACE
        _chmod_restorable(self, unmapped, 0)
        classes, notes = self.classify()
        self.assertEqual(classes["unmapped"],
                         [{"namespace": db.UNMAPPED_NAMESPACE, "stores": None}])
        self.assertTrue(any(db.UNMAPPED_NAMESPACE in note and "could not be listed" in note
                            for note in notes), notes)
        _chmod_restorable(self, self.world["data_home"], 0)
        classes, notes = self.classify()
        self.assertEqual(classes, EMPTY_CLASSES)
        self.assertTrue(any("could not be listed" in note for note in notes), notes)

    def test_lowered_listing_cap_is_noted_on_its_panel_in_bounds_and_in_the_receipt(self):
        model = db.build_model(self.world["data_home"], [str(self.world["checkout"])],
                               {"notes": []}, {"MAX_NAMESPACES_LISTED": 5})
        marker = "cap MAX_NAMESPACES_LISTED (5) reached"
        namespaces = model["panels"][0]
        self.assertEqual(namespaces["id"], "namespaces")
        panel_notes = [note for note in namespaces["notes"] if note.startswith(marker)]
        self.assertEqual(len(panel_notes), 1, namespaces["notes"])
        self.assertEqual([note for note in model["notes"] if marker in note],
                         [f"namespaces: {panel_notes[0]}"])
        rows = {row["name"]: row for row in model["caps"]}
        self.assertTrue(rows["MAX_NAMESPACES_LISTED"]["hit"])
        self.assertEqual(rows["MAX_NAMESPACES_LISTED"]["value"], 5)
        self.assertFalse(rows["MAX_NAMESPACES_READ"]["hit"])
        classes = model["classes"]
        self.assertEqual(len(classes["mapped"]) + len(classes["unmapped"])
                         + classes["residue"]["count"], 5)
        page = db.render_page(model, _FAKE_HOME.name)
        section = page.split('<section id="namespaces">', 1)[1].split("</section>", 1)[0]
        self.assertIn(f"<li>{html.escape(panel_notes[0], quote=True)}</li>", section)
        bounds = page.split('<section id="bounds">', 1)[1]
        self.assertIn("<td>MAX_NAMESPACES_LISTED</td><td>5</td><td>hit</td>", bounds)
        self.assertIn(html.escape(f"namespaces: {panel_notes[0]}", quote=True), bounds)
        receipt = db.build_receipt(model, _FAKE_HOME.name, self.tmp / "out")
        self.assertEqual(receipt["caps_hit"], ["MAX_NAMESPACES_LISTED"])
        self.assertIn(f"namespaces: {panel_notes[0]}", receipt["notes"])

    def test_a_raising_namespaces_builder_cannot_drop_the_cap_note(self):
        def broken(_ctx):
            raise RuntimeError("boom")

        registry = [("namespaces", "Namespaces", broken), db.PANELS[-1]]
        with mock.patch.object(db, "PANELS", registry):
            model = db.build_model(self.world["data_home"], [str(self.world["checkout"])],
                                   {}, {"MAX_NAMESPACES_LISTED": 5})
        notes = model["panels"][0]["notes"]
        self.assertTrue(any(note.startswith("cap MAX_NAMESPACES_LISTED (5) reached")
                            for note in notes), notes)
        self.assertIn("panel could not be built (RuntimeError)", notes)
        self.assertTrue({row["name"]: row for row in model["caps"]}["MAX_NAMESPACES_LISTED"]["hit"])

    def test_codex_kits_root_maps_with_its_own_kind(self):
        namespace = rd.project_namespace(self.world["checkout"] / "tasks" / "kits")
        (self.world["data_home"] / namespace / "attempts").mkdir(parents=True)
        classes, _notes = self.classify()
        kinds = {row["namespace"]: row["kind"] for row in classes["mapped"]}
        self.assertEqual(kinds, {self.world["namespace"]: "checkout", namespace: "codex-kits"})

    def test_non_store_entries_in_a_namespace_are_noted(self):
        unmapped = self.world["data_home"] / db.UNMAPPED_NAMESPACE
        (unmapped / "stray.txt").write_text("x\n")
        (unmapped / "not-a-store").mkdir()
        classes, notes = self.classify()
        self.assertEqual(classes["unmapped"][0]["stores"], ["attempts"])
        self.assertTrue(any(db.UNMAPPED_NAMESPACE in note and "2 entries that are not a store"
                            in note for note in notes), notes)

    def test_legacy_in_tree_store_is_noted_not_scanned(self):
        memory = self.world["checkout"] / "memory"
        memory.mkdir()
        (memory / "fact.json").write_text("{}\n")
        env = {key: value for key, value in os.environ.items() if key != "POLYTROPOS_DATA_HOME"}
        with mock.patch.dict(os.environ, env, clear=True):
            _classes, notes = self.classify()
        expected = (f"legacy in-tree store memory at {memory} — not scanned by the dashboard")
        self.assertIn(expected, notes)


# ---------------------------------------------------------------------------------------------
# Checkout discovery.

class DiscoveryTests(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="dashboard-discover-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(os.path.realpath(tmp.name))
        self.top = self.tmp / "repo"
        self.sub = self.top / "sub"
        self.sub.mkdir(parents=True)
        self.other = self.tmp / "other"
        self.other.mkdir()
        self.worktree = self.tmp / "repo-wt"
        self.worktree.mkdir()
        self.gone = self.tmp / "gone-wt"

    def porcelain(self):
        return (f"worktree {self.top}\nHEAD {'a' * 40}\nbranch refs/heads/main\n\n"
                f"worktree {self.worktree}\nHEAD {'b' * 40}\ndetached\n\n"
                f"worktree {self.gone}\nHEAD {'c' * 40}\nprunable gitdir file points to "
                f"non-existent location\n")

    def test_injected_runner_yields_primary_flags_then_worktrees(self):
        calls = []

        def runner(argv, cwd, timeout, name):
            calls.append({"argv": list(argv), "cwd": cwd, "timeout": timeout, "name": name})
            if argv[:2] == ["git", "rev-parse"]:
                return {"outcome": "ok", "rc": 0, "stdout": f"{self.top}\n"}
            if cwd == str(self.top):
                return {"outcome": "ok", "rc": 0, "stdout": self.porcelain()}
            return {"outcome": "ok", "rc": 0,
                    "stdout": f"worktree {cwd}\nHEAD {'d' * 40}\nbranch refs/heads/other\n"}

        checkouts, notes = db.discover_checkouts(self.sub, flags=[str(self.other)], runner=runner)
        self.assertEqual(checkouts, [str(self.top), str(self.other), str(self.worktree)])
        self.assertEqual(calls[0]["argv"], ["git", "rev-parse", "--show-toplevel"])
        self.assertEqual(calls[0]["cwd"], str(self.sub))
        worktree_calls = [call for call in calls
                          if call["argv"] == ["git", "worktree", "list", "--porcelain"]]
        self.assertEqual([call["cwd"] for call in worktree_calls], [str(self.top), str(self.other)])
        plugin_root = os.path.realpath(db.PLUGIN_ROOT)
        for call in calls:
            self.assertEqual(call["timeout"], db.GIT_TIMEOUT_SECONDS)
            self.assertNotEqual(os.path.realpath(call["cwd"]), plugin_root)
        self.assertNotIn(plugin_root, checkouts)
        gone = [note for note in notes if str(self.gone) in note]
        self.assertEqual(len(gone), 1, notes)
        self.assertIn("not a directory", gone[0])

    def test_missing_git_falls_back_to_the_working_directory_with_a_note(self):
        def runner(argv, cwd, timeout, name):
            return {"outcome": "missing-executable"}

        checkouts, notes = db.discover_checkouts(self.sub, runner=runner)
        self.assertEqual(checkouts, [str(self.sub)])
        self.assertTrue(any("missing-executable" in note
                            and "the primary checkout is the working directory" in note
                            for note in notes), notes)

    def test_no_git_runs_nothing(self):
        calls = []

        def runner(argv, cwd, timeout, name):
            calls.append(list(argv))  # recorded, not raised: `_git` turns a raise into a note
            return {"outcome": "ok", "rc": 0, "stdout": f"worktree {self.other}\n"}

        checkouts, notes = db.discover_checkouts(self.sub, flags=[str(self.worktree)],
                                                 git=False, runner=runner)
        self.assertEqual(calls, [])
        self.assertEqual(checkouts, [str(self.sub), str(self.worktree)])
        self.assertTrue(any("--no-git" in note for note in notes), notes)
        self.assertFalse(any("could not run" in note for note in notes), notes)

    def test_a_raising_or_timed_out_runner_is_a_note(self):
        def raising(argv, cwd, timeout, name):
            raise RuntimeError("boom")

        checkouts, notes = db.discover_checkouts(self.sub, runner=raising)
        self.assertEqual(checkouts, [str(self.sub)])
        self.assertTrue(any("could not run (RuntimeError)" in note for note in notes), notes)

        def timing_out(argv, cwd, timeout, name):
            return {"outcome": "timeout", "rc": 124, "stdout": ""}

        checkouts, notes = db.discover_checkouts(self.sub, runner=timing_out)
        self.assertEqual(checkouts, [str(self.sub)])
        self.assertTrue(any("exceeded GIT_TIMEOUT_SECONDS" in note for note in notes), notes)

    def test_candidates_dedupe_by_real_path_and_bad_ones_are_notes(self):
        link = self.tmp / "link-to-other"
        os.symlink(self.other, link)
        checkouts, notes = db.discover_checkouts(
            self.sub,
            flags=[str(self.worktree), str(link), "../../repo-wt", str(self.tmp / "absent")],
            config=[str(self.other)], git=False)
        self.assertEqual(checkouts, [str(self.sub), str(self.worktree), str(self.other)])
        self.assertTrue(any(str(self.tmp / "absent") in note and "not a directory" in note
                            for note in notes), notes)

    def test_porcelain_paths_are_parsed_and_quoted_ones_unquoted(self):
        text = ('worktree /tmp/plain path\nHEAD x\n\n'
                'worktree "/tmp/D\\303\\251v wt"\nHEAD y\n\n'
                'bare\n')
        self.assertEqual(db._porcelain_worktrees(text), ["/tmp/plain path", "/tmp/Dév wt"])
        self.assertEqual(db._porcelain_worktrees(""), [])


# ---------------------------------------------------------------------------------------------
# config.json.

class ConfigTests(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="dashboard-config-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.out = self.tmp / "store"
        self.out.mkdir()
        self.good = self.tmp / "good-checkout"
        self.good.mkdir()

    def write(self, data):
        raw = data if isinstance(data, bytes) else json.dumps(data).encode("utf-8")
        (self.out / "config.json").write_bytes(raw)

    def test_absent_config_or_out_dir_adds_nothing_and_says_nothing(self):
        self.assertEqual(db.read_config(self.out), ([], []))
        self.assertEqual(db.read_config(self.tmp / "no-store-yet"), ([], []))

    def test_dotdot_path_is_skipped_with_a_note(self):
        dotdot = f"{self.good}/../{self.good.name}"
        self.write({"checkouts": [dotdot, str(self.good)]})
        checkouts, notes = db.read_config(self.out)
        self.assertEqual(checkouts, [str(self.good)])
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("contains '..'", notes[0])

    def test_non_list_checkouts_is_a_note(self):
        self.write({"checkouts": str(self.good)})
        checkouts, notes = db.read_config(self.out)
        self.assertEqual(checkouts, [])
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("no `checkouts` list", notes[0])

    def test_non_object_and_undecodable_files_are_notes(self):
        for raw, expected in ((b"[1, 2]", "not a JSON object"), (b"{nope", "not UTF-8 JSON"),
                              (b"\xff\xfe", "not UTF-8 JSON")):
            self.write(raw)
            checkouts, notes = db.read_config(self.out)
            self.assertEqual(checkouts, [])
            self.assertEqual(len(notes), 1, notes)
            self.assertIn(expected, notes[0])

    def test_bad_entries_are_skipped_one_note_each(self):
        self.write({"checkouts": [7, "relative/path", str(self.tmp / "absent"), str(self.good)]})
        checkouts, notes = db.read_config(self.out)
        self.assertEqual(checkouts, [str(self.good)])
        self.assertEqual(len(notes), 3, notes)
        self.assertIn("type int", notes[0])
        self.assertIn("not an absolute path", notes[1])
        self.assertIn("not a directory", notes[2])

    def test_symlinked_config_is_refused_not_followed(self):
        real = self.tmp / "elsewhere.json"
        real.write_text(json.dumps({"checkouts": [str(self.good)]}))
        os.symlink(real, self.out / "config.json")
        checkouts, notes = db.read_config(self.out)
        self.assertEqual(checkouts, [])
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("could not be read (SafePathError)", notes[0])


class ConfigBuildTests(_WorldCase):

    def test_config_checkouts_are_candidates_in_a_build(self):
        out = self.tmp / "out"
        out.mkdir()
        (out / "config.json").write_text(json.dumps({"checkouts": [str(self.world["checkout"])]}))
        os.chdir(self.tmp)  # the primary is then NOT the world checkout; only config names it
        rc, stdout, _stderr = _run(["build", "--data-home", str(self.world["data_home"]),
                                    "--out-dir", str(out), "--projects-dir", str(self.projects),
                                    "--no-git", "--json"])
        self.assertEqual(rc, 0)
        receipt = json.loads(stdout)
        self.assertEqual(receipt["classes"]["mapped"]["count"], 1)
        self.assertEqual(receipt["checkouts"][1], os.path.realpath(self.world["checkout"]))


# ---------------------------------------------------------------------------------------------
# The private writer.

class WriterTests(_WorldCase):

    def test_write_page_leaves_a_0700_dir_and_0600_files(self):
        out = self.tmp / "fresh" / "nested" / "out"
        paths = db.write_page(out, "<!doctype html>\n", {"schema_version": 1})
        self.assertEqual(stat.S_IMODE(os.stat(out).st_mode), 0o700)
        for key in ("page", "receipt"):
            self.assertEqual(stat.S_IMODE(os.stat(paths[key]).st_mode), 0o600)
        self.assertEqual(json.loads(paths["receipt"].read_text()), {"schema_version": 1})

    def test_a_build_writes_0700_and_0600_and_a_rebuild_replaces_in_place(self):
        for _ in range(2):
            rc, out, _stdout, stderr = self.build()
            self.assertEqual(rc, 0, stderr)
        self.assertEqual(stat.S_IMODE(os.stat(out).st_mode), 0o700)
        for name in ("index.html", "build.json"):
            mode = os.lstat(out / name).st_mode
            self.assertTrue(stat.S_ISREG(mode))
            self.assertEqual(stat.S_IMODE(mode), 0o600)
        self.assertEqual(sorted(os.listdir(out)), ["build.json", "index.html"])

    def test_symlinked_index_leaf_is_refused_with_exit_2(self):
        out = self.tmp / "out"
        out.mkdir(mode=0o700)
        target = self.tmp / "elsewhere.html"
        target.write_text("KEEP\n")
        os.symlink(target, out / "index.html")
        rc, _out, stdout, stderr = self.build()
        self.assertEqual(rc, 2)
        self.assertEqual(stdout, "")
        self.assertIn("refusing to replace it", stderr)
        self.assertEqual(target.read_text(), "KEEP\n")
        self.assertTrue(os.path.islink(out / "index.html"))
        self.assertFalse(os.path.lexists(out / "build.json"))

    def test_symlinked_receipt_leaf_is_refused_before_the_page_is_written(self):
        out = self.tmp / "out"
        out.mkdir(mode=0o700)
        os.symlink(self.tmp / "dangling", out / "build.json")
        rc, _out, _stdout, stderr = self.build()
        self.assertEqual(rc, 2)
        self.assertIn("refusing to replace it", stderr)
        self.assertFalse(os.path.lexists(out / "index.html"))

    def test_out_dir_that_is_a_file_exits_2(self):
        (self.tmp / "out").write_text("a file, not a directory\n")
        rc, _out, stdout, stderr = self.build()
        self.assertEqual(rc, 2)
        self.assertEqual(stdout, "")
        self.assertTrue(stderr.startswith(f"dashboard: the page was not written (out dir: "
                                          f"{self.tmp / 'out'}): "), stderr)

    def test_default_out_dir_is_the_dashboard_store_resolved_at_call_time(self):
        first, second = self.tmp / "home-a", self.tmp / "home-b"
        with mock.patch.dict(os.environ, {"POLYTROPOS_DATA_HOME": str(first)}):
            path_a = Path(db.default_out_dir(self.world["checkout"]))
        with mock.patch.dict(os.environ, {"POLYTROPOS_DATA_HOME": str(second)}):
            path_b = Path(db.default_out_dir(self.world["checkout"]))
        self.assertEqual(path_a, first / self.world["namespace"] / "dashboard")
        self.assertEqual(path_b, second / self.world["namespace"] / "dashboard")
        self.assertFalse(first.exists() or second.exists())


class EmptyPathFlagTests(_WorldCase):
    """An empty or blank path is refused, never collapsed to `.` (the working directory)."""

    def setUp(self):
        super().setUp()
        self.cwd = self.tmp / "cwd"
        self.cwd.mkdir()
        os.chdir(self.cwd)

    def assertNothingWrittenAnywhere(self, out):
        self.assertEqual(os.listdir(self.cwd), [])
        self.assertFalse(os.path.lexists(out))
        self.assertEqual(os.listdir(_DATA_HOME.name), [])
        self.assertEqual(os.listdir(_FAKE_HOME.name), [])

    def test_the_path_flags_are_every_build_option_that_takes_a_path(self):
        self.assertEqual(db.BUILD_PATH_FLAGS,
                         ("--data-home", "--out-dir", "--checkout", "--projects-dir"))
        for flag in db.BUILD_PATH_FLAGS:
            value = getattr(db._parser().parse_args(["build", flag, "/x"]),
                            flag[2:].replace("-", "_"))
            self.assertEqual(value, ["/x"] if flag == "--checkout" else "/x")

    def test_every_empty_or_blank_path_flag_exits_2_and_writes_nothing(self):
        out = self.tmp / "out"
        for flag in db.BUILD_PATH_FLAGS:
            for bad in ("", "   ", "\t"):
                with self.subTest(flag=flag, value=repr(bad)):
                    argv = self.build_argv(out, "--json")
                    if flag == "--checkout":
                        argv += [flag, bad]  # one blank entry among valid ones is enough
                    else:
                        argv[argv.index(flag) + 1] = bad
                    rc, stdout, stderr = _run(argv)
                    self.assertEqual(rc, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn(f"dashboard: {flag} needs a path", stderr)
                    self.assertIn("nothing was read or written", stderr)
                    self.assertNothingWrittenAnywhere(out)

    def test_the_same_build_with_real_paths_leaves_the_working_directory_empty(self):
        out = self.tmp / "out"
        rc, _stdout, stderr = _run(self.build_argv(out))
        self.assertEqual(rc, 0, stderr)
        self.assertEqual(os.listdir(self.cwd), [])
        self.assertEqual(sorted(os.listdir(out)), ["build.json", "index.html"])

    def test_the_writer_and_the_assembler_refuse_an_empty_path_too(self):
        refused = db._mod("safe_paths").SafePathError
        for blank in ("", "  "):
            with self.assertRaises(refused):
                db.write_page(blank, "<!doctype html>\n", {})
        for name in ("out_dir", "data_home", "projects_dir"):
            with self.subTest(name=name):
                kwargs = {"data_home": self.world["data_home"], "out_dir": self.tmp / "out",
                          "projects_dir": self.projects, name: ""}
                with self.assertRaises(refused):
                    db.assemble_build(self.cwd, git=False, home=_FAKE_HOME.name, **kwargs)
        self.assertNothingWrittenAnywhere(self.tmp / "out")

    def test_an_empty_data_home_checkout_or_config_dir_never_means_the_working_directory(self):
        (self.cwd / "looks-like-a-namespace").mkdir()
        model = db.build_model("", [str(self.world["checkout"])], {}, None)
        self.assertEqual(model["classes"], EMPTY_CLASSES)
        self.assertIn("namespaces: no data home was given — nothing was classified",
                      model["notes"])
        self.assertNotIn("looks-like-a-namespace", json.dumps(model))
        checkouts, notes = db.discover_checkouts(self.world["checkout"], flags=["", "  "],
                                                 git=False)
        self.assertEqual(checkouts, [os.path.realpath(self.world["checkout"])])
        self.assertEqual(len([note for note in notes if "an empty checkout path" in note]), 2)
        (self.cwd / "config.json").write_text(json.dumps({"checkouts": [str(self.tmp)]}))
        self.assertEqual(db.read_config(""),
                         ([], ["no output directory was given — config.json was not read"]))


class WriteFailureMessageTests(_WorldCase):

    def test_the_message_states_the_out_dir_and_the_error_without_blaming_the_out_dir(self):
        out = self.tmp / "out"

        def failing(out_dir, html, receipt):
            raise PermissionError(13, "Permission denied", "/elsewhere/.index.html.x1y2")

        with mock.patch.object(db, "write_page", failing):
            rc, stdout, stderr = _run(self.build_argv(out))
        self.assertEqual(rc, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, f"dashboard: the page was not written (out dir: {out}): "
                                 f"[Errno 13] Permission denied: '/elsewhere/.index.html.x1y2'\n")
        self.assertNotIn("could not be written into", stderr)

    @unittest.skipIf(os.geteuid() == 0, "root writes through mode 0o500")
    def test_an_unwritable_working_directory_is_not_blamed_on_the_out_dir(self):
        cwd = self.tmp / "readonly-cwd"
        cwd.mkdir()
        out = self.tmp / "writable-out"
        os.chdir(cwd)
        _chmod_restorable(self, cwd, 0o500)
        rc, stdout, stderr = _run(self.build_argv(out))
        self.assertEqual(os.listdir(cwd), [])
        if rc == 0:  # safe_paths no longer reserves its temp name in the working directory
            self.assertTrue((out / "index.html").is_file())
            return
        self.assertEqual(rc, 2, stderr)
        self.assertEqual(stdout, "")
        self.assertTrue(stderr.startswith(f"dashboard: the page was not written (out dir: "
                                          f"{out}): "), stderr)
        self.assertNotIn("could not be written into", stderr)


# ---------------------------------------------------------------------------------------------
# The page shell.

class PageTests(_WorldCase):

    def setUp(self):
        super().setUp()
        rc, self.out, self.stdout, stderr = self.build("out", "--json")
        self.assertEqual(rc, 0, stderr)
        self.html = self.page(self.out)

    def test_first_http_equiv_meta_is_the_exact_csp_and_the_head_is_in_order(self):
        first = re.search(r"<meta http-equiv[^>]*>", self.html)
        self.assertIsNotNone(first)
        self.assertEqual(first.group(0), EXACT_CSP_META)
        self.assertEqual(self.html.count("http-equiv"), 1)
        self.assertTrue(self.html.startswith('<!doctype html>\n<html lang="en">\n<head>\n'))
        head = self.html.split("</head>", 1)[0]
        order = [head.index('<meta charset="utf-8">'), head.index(EXACT_CSP_META),
                 head.index('<meta name="viewport"'), head.index("<title>"),
                 head.index("<style>")]
        self.assertEqual(order, sorted(order))
        self.assertLess(self.html.index(EXACT_CSP_META), self.html.index("<body"))
        self.assertEqual(self.html.count("<style>"), 1)
        for char in '"<>&':
            self.assertNotIn(char, db.CSP)  # emitted verbatim, so it must need no escaping

    def test_no_network_capable_markup_and_only_anchor_links(self):
        for bad in NETWORK_TRIPWIRES:
            self.assertNotIn(bad, self.html)
        lowered = self.html.lower()
        for bad in ("<link", "<iframe", "<form", "<img", "<object", "<embed", "<base"):
            self.assertNotIn(bad, lowered)
        hrefs = re.findall(r'href="([^"]*)"', self.html)
        ids = set(re.findall(r'id="([^"]*)"', self.html))
        self.assertEqual(hrefs, ["#" + pid for pid, _title, _builder in db.PANELS])
        for href in hrefs:
            self.assertIn(href[1:], ids)

    def test_panels_render_in_the_pinned_order_one_section_each(self):
        registered = [pid for pid, _title, _builder in db.PANELS]
        self.assertEqual(registered[0], "namespaces")
        self.assertEqual(registered[-1], "bounds")
        positions = [PINNED_PANEL_ORDER.index(pid) for pid in registered]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(len(set(registered)), len(registered))
        self.assertEqual(re.findall(r'<section id="([^"]+)">', self.html), registered)

    def test_stylesheet_shell(self):
        style = self.html.split("<style>", 1)[1].split("</style>", 1)[0]
        root = style.split(":root {", 1)[1].split("}", 1)[0]
        dark = style.split("@media (prefers-color-scheme: dark) {", 1)[1].split("}\n}", 1)[0]
        for prop in ("--bg:", "--fg:", "--muted:", "--accent:", "--line:"):
            self.assertIn(prop, root)
            self.assertIn(prop, dark)
        self.assertEqual(style.count("prefers-color-scheme: dark"), 1)
        body = style.split("body {", 1)[1].split("}", 1)[0]
        self.assertIn("background: var(--bg);", body)
        self.assertIn("color: var(--fg);", body)
        self.assertIn("font-family: system-ui", body)
        wrap = style.split(".wrap {", 1)[1].split("}", 1)[0]
        self.assertIn("max-width:", wrap)
        self.assertIn("padding: 0 16px;", wrap)
        self.assertIn(".table-wrap { overflow-x: auto; }", style)

    def test_header_carries_built_at_on_one_line_and_every_table_is_wrapped(self):
        built = [line for line in self.html.splitlines() if "data-built-at" in line]
        self.assertEqual(len(built), 1)
        receipt = self.receipt(self.out)
        self.assertIn(f'data-built-at="{receipt["built_at"]}"', built[0])
        self.assertEqual(self.html.count(receipt["built_at"]), 2)  # attribute + text, same line
        self.assertEqual(self.html.count("<table>"), self.html.count('<div class="table-wrap">'))

    def test_json_flag_prints_the_receipt_the_store_holds(self):
        receipt = self.receipt(self.out)
        self.assertEqual(json.loads(self.stdout), receipt)
        self.assertEqual(receipt["schema_version"], db.BUILD_SCHEMA_VERSION)
        self.assertEqual(receipt["classes"]["mapped"], {"count": 1})
        self.assertEqual(receipt["classes"]["unmapped"], {"count": 1})
        self.assertEqual(receipt["classes"]["residue"]["count"], 30)
        self.assertEqual(len(receipt["classes"]["residue"]["sample"]), 3)
        self.assertEqual([panel["id"] for panel in receipt["panels"]], ["namespaces", "bounds"])
        self.assertEqual([row["name"] for row in receipt["caps"]], list(db.CAP_NAMES))
        self.assertEqual(receipt["caps_hit"], [])
        self.assertEqual(receipt["page"], str(self.out / "index.html"))
        self.assertTrue(any("--no-git" in note for note in receipt["notes"]))

    def test_bounds_panel_lists_every_cap_and_every_note(self):
        bounds = self.html.split('<section id="bounds">', 1)[1]
        for name in db.CAP_NAMES:
            self.assertIn(f"<td>{name}</td>", bounds)
        self.assertEqual(bounds.count("<td>not hit</td>"), len(db.CAP_NAMES))
        notes = self.receipt(self.out)["notes"]
        self.assertTrue(notes)
        for note in notes:
            self.assertIn(f"<li>{html.escape(note, quote=True)}</li>", bounds)

    def test_residue_row_states_the_heuristic_and_its_limit(self):
        section = self.html.split('<section id="namespaces">', 1)[1].split("</section>", 1)[0]
        self.assertIn("30 namespaces, e.g.", section)
        self.assertIn("residue (heuristic)", section)
        self.assertIn("never opened", section)
        self.assertIn("miscounted", section)


class RenderingTests(_WorldCase):

    def test_two_builds_are_byte_identical_but_for_the_built_at_line(self):
        rc1, out1, _stdout, _stderr = self.build("out1")
        rc2, out2, _stdout, _stderr = self.build("out2")
        self.assertEqual((rc1, rc2), (0, 0))
        self.assertEqual(_without_built_at(self.page(out1)), _without_built_at(self.page(out2)))
        checkouts = [str(self.world["checkout"])]
        early = db.build_model(self.world["data_home"], checkouts,
                               {"now": datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)}, None)
        late = db.build_model(self.world["data_home"], checkouts,
                              {"now": datetime(2026, 1, 2, 17, 30, tzinfo=timezone.utc)}, None)
        page_early = db.render_page(early, _FAKE_HOME.name)
        page_late = db.render_page(late, _FAKE_HOME.name)
        self.assertNotEqual(page_early, page_late)
        self.assertEqual(_without_built_at(page_early), _without_built_at(page_late))

    def test_fake_home_never_appears_while_tilde_does(self):
        home = self.tmp / "home"
        world = db.synthetic_world(home / "world")
        projects = home / "projects"
        projects.mkdir()
        out = home / "out"
        os.chdir(world["checkout"])
        with mock.patch.dict(os.environ, {"HOME": str(home)}):
            rc, stdout, stderr = _run(["build", "--data-home", str(world["data_home"]),
                                       "--out-dir", str(out), "--projects-dir", str(projects),
                                       "--no-git"])
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        receipt_text = (out / "build.json").read_text(encoding="utf-8")
        for spelling in {str(home), os.path.realpath(home)}:
            for text in (page, receipt_text, stdout):
                self.assertNotIn(spelling, text)
        for text in (page, receipt_text):
            self.assertNotIn("/private~", text)  # a realpath spelling was scrubbed whole
        self.assertIn("~/", page)
        self.assertIn("~/world/checkout", page)
        self.assertIn("~/world/data-home", page)

    def test_every_string_is_escaped_and_tripwires_neutralised(self):
        data_home = self.world["data_home"]
        for name in ("ns-<script>x", "ns-src=a-href=b-url(c)-@import", "ns-ünïcode-✓-😀"):
            (data_home / name).mkdir()
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        for bad in NETWORK_TRIPWIRES:
            self.assertNotIn(bad, page)
        self.assertIn("ns-&lt;script&gt;x", page)
        self.assertIn("ns-src&#61;a-href&#61;b-url&#40;c)-&#64;import", page)
        self.assertIn("ns-ünïcode-✓-😀", page)

    def test_a_missing_data_home_argument_is_a_note_not_an_exception(self):
        model = db.build_model(None, [str(self.world["checkout"])], {}, None)
        self.assertEqual(model["classes"], EMPTY_CLASSES)
        self.assertIsNone(model["data_home"])
        self.assertIn("namespaces: no data home was given — nothing was classified",
                      model["notes"])
        page = db.render_page(model, _FAKE_HOME.name)
        self.assertIn("Data home unknown: 0 mapped", page)
        self.assertIn("data home: unknown", page)

    def test_model_is_json_serializable(self):
        model = db.build_model(self.world["data_home"], [str(self.world["checkout"])],
                               {"notes": ["a note"]}, None)
        self.assertEqual(json.loads(json.dumps(model))["schema_version"], 1)
        self.assertEqual(model["notes"][0], "a note")
        self.assertEqual([panel["id"] for panel in model["panels"]], ["namespaces", "bounds"])

    def test_a_panel_builder_that_raises_is_a_note_not_an_exception(self):
        def broken(_ctx):
            raise RuntimeError("/secret/path/in/a/message")

        registry = [db.PANELS[0], ("attempts", "Attempts", broken), db.PANELS[-1]]
        with mock.patch.object(db, "PANELS", registry):
            model = db.build_model(self.world["data_home"], [str(self.world["checkout"])],
                                   {}, None)
            page = db.render_page(model, _FAKE_HOME.name)
        self.assertIn("attempts: panel could not be built (RuntimeError)", model["notes"])
        self.assertNotIn("/secret/path", json.dumps(model))
        self.assertNotIn("/secret/path", page)
        self.assertIn('<section id="attempts">', page)


# ---------------------------------------------------------------------------------------------
# Rendering toolkit (T3): esc, the formatters, tables, charts and panel chrome. Every later
# panel builds with these, so the honesty contract (PLAN D7) is written once and enforced here.

class EscTests(unittest.TestCase):

    def test_none_is_a_styled_unknown_span_never_blank(self):
        self.assertEqual(db.esc(None), '<span class="unknown">unknown</span>')

    def test_values_are_escaped_and_tripwires_neutralised(self):
        self.assertEqual(db.esc('<script>&"'), "&lt;script&gt;&amp;&quot;")
        self.assertIn("😀", db.esc("emoji 😀"))
        self.assertEqual(db.esc("src=x href=y url(z) @import"),
                         "src&#61;x href&#61;y url&#40;z) &#64;import")

    def test_non_string_values_are_stringified_first(self):
        self.assertEqual(db.esc(5), "5")
        self.assertEqual(db.esc(1.5), "1.5")


class FormatterTests(unittest.TestCase):

    def test_fmt_count(self):
        self.assertEqual(db.fmt_count(None), '<span class="unknown">unknown</span>')
        self.assertEqual(db.fmt_count(0), "0")
        self.assertEqual(db.fmt_count(42), "42")

    def test_fmt_usd_requires_a_basis_label_and_never_prints_a_bare_dollar(self):
        self.assertEqual(db.fmt_usd(None, "est."), '<span class="unknown">unknown</span>')
        self.assertNotIn("$", db.fmt_usd(None, "est."))
        rendered = db.fmt_usd(1.5, "est.")
        self.assertIn("$1.50", rendered)
        self.assertIn('<span class="label">est.</span>', rendered)
        with self.assertRaises(TypeError):
            db.fmt_usd(1.5)  # the basis label is required, never optional (PLAN D7a/b)

    def test_fmt_usd_on_bad_input_still_carries_the_label_never_crashes_the_panel(self):
        rendered = db.fmt_usd("not-a-number", "est.")
        self.assertIn("not-a-number", rendered)
        self.assertIn('<span class="label">est.</span>', rendered)

    def test_fmt_credits_has_no_basis_label(self):
        self.assertEqual(db.fmt_credits(None), '<span class="unknown">unknown</span>')
        self.assertEqual(db.fmt_credits(2), "2.00")
        self.assertEqual(db.fmt_credits(2.5), "2.50")

    def test_fmt_seconds(self):
        self.assertEqual(db.fmt_seconds(None), '<span class="unknown">unknown</span>')
        self.assertEqual(db.fmt_seconds(3), "3s")
        self.assertEqual(db.fmt_seconds(3.0), "3s")
        self.assertEqual(db.fmt_seconds(3.5), "3.5s")

    def test_fmt_date_passes_the_owners_text_through_unchanged(self):
        self.assertEqual(db.fmt_date(None), '<span class="unknown">unknown</span>')
        self.assertEqual(db.fmt_date("2026-09-06"), "2026-09-06")

    def test_age_days_parses_dates_and_iso_timestamps(self):
        self.assertEqual(db.age_days("2026-09-01", "2026-09-25"), 24)
        self.assertEqual(db.age_days("2026-09-01T00:00:00Z", "2026-09-25T12:00:00Z"), 24)
        self.assertEqual(db.age_days("2026-09-25", "2026-09-25"), 0)
        self.assertIsNone(db.age_days(None, "2026-09-25"))
        self.assertIsNone(db.age_days("2026-09-25", None))
        self.assertIsNone(db.age_days("not a date", "2026-09-25"))
        self.assertIsNone(db.age_days("2026-09-25", "not a date"))


class HtmlTableTests(unittest.TestCase):

    def test_basic_table_has_a_caption_wrap_div_and_escaped_cells(self):
        rendered = db.html_table(["a", "b"], [[1, 2], [None, "x"]], caption="Cap")
        self.assertIn('<div class="table-wrap">', rendered)
        self.assertIn("<caption>Cap</caption>", rendered)
        self.assertIn("<th>a</th><th>b</th>", rendered)
        self.assertIn("<td>1</td><td>2</td>", rendered)
        self.assertIn('<td><span class="unknown">unknown</span></td><td>x</td>', rendered)

    def test_details_wraps_with_a_row_count_and_no_duplicate_caption(self):
        rendered = db.html_table(["n"], [[1], [2], [3]], caption="Long table", details=True)
        self.assertTrue(rendered.startswith("<details>"))
        self.assertIn("<summary>Long table (3 rows)</summary>", rendered)
        self.assertNotIn("<caption>", rendered)
        self.assertIn('<div class="table-wrap">', rendered)

    def test_details_row_count_is_singular_for_one_row(self):
        rendered = db.html_table(["n"], [[1]], caption="One", details=True)
        self.assertIn("(1 row)", rendered)

    def test_cell_escaping_and_emoji(self):
        rendered = db.html_table(["h"], [['<script>&"'], ["😀"]])
        self.assertIn("&lt;script&gt;&amp;&quot;", rendered)
        self.assertIn("😀", rendered)

    def test_table_block_details_flag_is_honoured_by_the_generic_dispatcher(self):
        rendered = db._render_block({"type": "table", "headers": ["n"], "rows": [[1], [2]],
                                     "caption": "Big", "details": True})
        self.assertTrue(rendered.startswith("<details>"))
        self.assertIn("(2 rows)", rendered)


class TypedCellTests(unittest.TestCase):
    """A table cell is either a plain value (escaped exactly once, so a builder cannot smuggle
    raw HTML through a string) or a typed `{"fmt": ...}` cell dispatched to its formatter,
    whose own already-escaped HTML is used as-is rather than escaped a second time. This is the
    fix for the T3 red-team's confirmed double-escaping break: T4's cost-by-basis table (and
    every later panel) builds its `usd`/`credits` cells this way."""

    def test_typed_usd_cell_renders_markup_once_not_as_escaped_text(self):
        rendered = db.html_table(
            ["basis", "amount"],
            [["actual", {"fmt": "usd", "value": 1.5, "basis": "actual"}]])
        self.assertIn('<td>$1.50 <span class="label">actual</span></td>', rendered)
        self.assertNotIn("&lt;span", rendered)
        self.assertNotIn("&quot;", rendered)

    def test_typed_usd_cell_none_value_renders_the_styled_unknown_span_not_escaped_text(self):
        rendered = db.html_table(
            ["basis", "amount"],
            [["estimated", {"fmt": "usd", "value": None, "basis": "estimated"}]])
        self.assertIn('<td><span class="unknown">unknown</span></td>', rendered)
        self.assertNotIn("&lt;span", rendered)

    def test_credits_count_seconds_date_typed_cells_all_render_once(self):
        rendered = db.html_table(
            ["k", "v"],
            [["credits", {"fmt": "credits", "value": 2.5}],
             ["count", {"fmt": "count", "value": 7}],
             ["seconds", {"fmt": "seconds", "value": 3.5}],
             ["date", {"fmt": "date", "value": "2026-09-01"}]])
        self.assertIn("<td>2.50</td>", rendered)
        self.assertIn("<td>7</td>", rendered)
        self.assertIn("<td>3.5s</td>", rendered)
        self.assertIn("<td>2026-09-01</td>", rendered)
        self.assertNotIn("&lt;span", rendered)
        self.assertNotIn("&quot;", rendered)

    def test_plain_string_cell_with_markup_is_still_escaped_exactly_once(self):
        rendered = db.html_table(["h"], [["<b>not html</b>"]])
        self.assertIn("<td>&lt;b&gt;not html&lt;/b&gt;</td>", rendered)
        self.assertNotIn("<b>not html</b>", rendered)   # never rendered as a real tag
        self.assertNotIn("&amp;lt;", rendered)          # and never escaped TWICE either

    def test_unrecognised_fmt_key_renders_a_sentence_not_a_crash(self):
        rendered = db.html_table(["h"], [[{"fmt": "bogus", "value": 1}]])
        self.assertIn("unrecognised fmt", rendered)

    def test_table_block_dispatch_supports_typed_cells_too(self):
        rendered = db._render_block({"type": "table", "headers": ["b", "amt"],
                                     "rows": [["actual", {"fmt": "usd", "value": 2,
                                                          "basis": "actual"}]]})
        self.assertIn('<span class="label">actual</span>', rendered)
        self.assertNotIn("&lt;span", rendered)


class NonFiniteFormatterTests(unittest.TestCase):
    """NaN/±Infinity -- as floats (what a JSON NaN/Infinity/1e400 round-trips to) or as the
    strings "nan"/"Infinity"/"-Infinity"/"1e400" (`float()` accepts every one of these without
    raising) -- never crash a formatter and never earn a `$`, credits or seconds suffix; each
    renders its own escaped, recorded text instead, exactly like an unparsable value already
    did. This is the fix for the T3 red-team's confirmed non-finite breaks."""

    NON_FINITE_VALUES = (float("nan"), float("inf"), float("-inf"),
                        "nan", "Infinity", "-Infinity", "1e400")

    # value -> the exact text every formatter falls back to (its own str(), verbatim -- a
    # string form is never reinterpreted: "1e400" stays "1e400", never becomes "inf").
    EXPECTED_TEXT = {
        float("nan"): "nan", float("inf"): "inf", float("-inf"): "-inf",
        "nan": "nan", "Infinity": "Infinity", "-Infinity": "-Infinity", "1e400": "1e400",
    }

    def test_fmt_usd_never_crashes_never_prints_a_dollar_keeps_the_basis_label(self):
        for value, text in self.EXPECTED_TEXT.items():
            with self.subTest(value=value):
                rendered = db.fmt_usd(value, "est.")
                self.assertEqual(rendered, f'{text} <span class="label">est.</span>')
                self.assertNotIn("$", rendered)

    def test_fmt_credits_never_crashes_and_renders_its_own_text_no_unit(self):
        for value, text in self.EXPECTED_TEXT.items():
            with self.subTest(value=value):
                self.assertEqual(db.fmt_credits(value), text)

    def test_fmt_count_never_crashes_and_renders_its_own_text(self):
        for value, text in self.EXPECTED_TEXT.items():
            with self.subTest(value=value):
                self.assertEqual(db.fmt_count(value), text)

    def test_fmt_seconds_never_crashes_and_never_gets_an_s_suffix(self):
        for value, text in self.EXPECTED_TEXT.items():
            with self.subTest(value=value):
                rendered = db.fmt_seconds(value)
                self.assertEqual(rendered, text)
                self.assertFalse(rendered.endswith("s"), rendered)


class ChartTests(unittest.TestCase):

    def test_svg_bars_title_and_desc_are_the_first_children_and_carry_a_table_twin(self):
        rows = [{"label": "sonnet", "value": 3}, {"label": "opus", "value": None}]
        fig = db.svg_bars(rows, "Records", "Records by tier", "label", "value")
        self.assertTrue(fig.startswith("<figure>"))
        svg = fig.split("<svg", 1)[1]
        first_mark = min((i for i in (svg.find("<rect"), svg.find("<text"))
                          if i != -1), default=len(svg))
        self.assertLess(svg.index("<title"), svg.index("<desc"))
        self.assertLess(svg.index("<desc"), first_mark)
        self.assertIn('role="img"', fig)
        self.assertIn("aria-labelledby=", fig)
        self.assertLess(fig.index("</svg>"), fig.index("<figcaption>"))
        self.assertIn("<table>", fig.split("<figcaption>", 1)[1])
        self.assertIn('<span class="unknown">unknown</span>', fig)  # opus's None value
        self.assertTrue(fig.rstrip().endswith("</figure>"))

    def test_svg_bars_none_value_draws_no_rect_for_that_row(self):
        fig = db.svg_bars([{"label": "only-none", "value": None}], "T", "D", "label", "value")
        self.assertNotIn("<rect", fig)

    def test_svg_sparkline_structure_and_none_breaks_the_line(self):
        fig = db.svg_sparkline([("d1", 1), ("d2", None), ("d3", 4)], "Spark", "Spark desc")
        svg = fig.split("<svg", 1)[1]
        self.assertLess(svg.index("<title"), svg.index("<desc"))
        polyline = svg.find("<polyline")
        if polyline != -1:
            self.assertLess(svg.index("<desc"), polyline)
        self.assertIn("<table>", fig.split("<figcaption>", 1)[1])
        self.assertIn('<span class="unknown">unknown</span>', fig)

    def test_chart_ids_are_unique_between_two_charts_in_one_render(self):
        db._reset_chart_sequence()
        fig1 = db.svg_bars([{"label": "a", "value": 1}], "T1", "D1", "label", "value")
        fig2 = db.svg_bars([{"label": "b", "value": 1}], "T2", "D2", "label", "value")
        id1 = re.search(r'<title id="([^"]+)"', fig1).group(1)
        id2 = re.search(r'<title id="([^"]+)"', fig2).group(1)
        self.assertNotEqual(id1, id2)


class PanelChromeTests(unittest.TestCase):

    def test_meta_line_names_source_observed_and_age(self):
        section = db.panel("p1", "Panel One", "bin/owner.py", "2026-09-01", 5, [], "<p>body</p>")
        self.assertIn('<section id="p1">', section)
        self.assertIn("<h2>Panel One</h2>", section)
        self.assertIn("source: bin/owner.py", section)
        self.assertIn("observed: 2026-09-01", section)
        self.assertIn("age: 5 days", section)
        self.assertIn("<p>body</p>", section)

    def test_observed_none_is_never_captured_and_age_none_is_n_a(self):
        section = db.panel("p2", "P2", "src", None, None, [], "")
        self.assertIn("observed: never captured", section)
        self.assertIn("age: n/a", section)

    def test_empty_or_whitespace_only_observed_is_also_never_captured_not_blank(self):
        # PLAN D7(d)/GUARDRAILS: absence is a word, never a blank -- this is the fix for the
        # T3 red-team's confirmed break where an empty/whitespace `observed` rendered blank.
        for blank in ("", "   ", "\t\n"):
            with self.subTest(observed=repr(blank)):
                section = db.panel("p8", "P8", "src", blank, None, [], "")
                self.assertIn("observed: never captured", section)

    def test_age_one_day_is_singular(self):
        section = db.panel("p3", "P3", "src", "2026-09-24", 1, [], "")
        self.assertIn("age: 1 day", section)
        self.assertNotIn("age: 1 days", section)

    def test_notes_render_even_when_empty(self):
        empty = db.panel("p4", "P4", "src", None, None, [], "")
        self.assertIn('<p class="notes">notes: none</p>', empty)
        with_notes = db.panel("p5", "P5", "src", None, None, ["a note"], "")
        self.assertIn('<ul class="notes">', with_notes)
        self.assertIn("<li>a note</li>", with_notes)

    def test_refresh_hint_is_an_optional_second_meta_line(self):
        with_hint = db.panel("p6", "P6", "src", None, None, [], "",
                             refresh_hint="run X to refresh")
        self.assertIn("run X to refresh", with_hint)
        self.assertEqual(with_hint.count('<p class="meta">'), 2)
        without_hint = db.panel("p7", "P7", "src", None, None, [], "")
        self.assertEqual(without_hint.count('<p class="meta">'), 1)

    def test_nav_renders_an_anchor_per_panel_falling_back_to_id_for_a_missing_title(self):
        rendered = db.nav([{"id": "a", "title": "Alpha"}, {"id": "b", "title": None}])
        self.assertIn('<a href="#a">Alpha</a>', rendered)
        self.assertIn('<a href="#b">b</a>', rendered)


class PanelDictContractTests(unittest.TestCase):

    def test_build_model_adds_a_refresh_hint_key_defaulting_to_none(self):
        model = db.build_model(None, [], {}, None)
        self.assertTrue(model["panels"])
        for entry in model["panels"]:
            self.assertIn("refresh_hint", entry)
            self.assertIsNone(entry["refresh_hint"])


class ChartIntegrationTests(_WorldCase):
    """`svg_bars`/`svg_sparkline` reached the way a real panel reaches them: as `blocks` in a
    built page, dispatched by `_render_block` after the whole model has been scrubbed."""

    @staticmethod
    def _chart_blocks():
        return [
            {"type": "svg_bars", "title": "Bars", "desc": "Bars desc", "label_key": "label",
             "value_key": "value",
             "rows": [{"label": "x", "value": 3}, {"label": "y", "value": None}]},
            {"type": "svg_sparkline", "title": "Spark", "desc": "Spark desc",
             "points": [("d1", 1), ("d2", None), ("d3", 4)]},
        ]

    def test_every_svg_in_a_built_page_has_title_desc_first_and_a_table_twin(self):
        def chart_panel(_ctx):
            return {"source": "test fixture", "observed": "2026-09-01", "notes": [],
                    "summary": "chart fixture", "blocks": self._chart_blocks()}

        registry = [db.PANELS[0], ("charts", "Charts", chart_panel), db.PANELS[-1]]
        with mock.patch.object(db, "PANELS", registry):
            rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        self.assertEqual(re.findall(r'<section id="([^"]+)">', page),
                         ["namespaces", "charts", "bounds"])
        figures = page.split("<figure>")[1:]
        self.assertEqual(len(figures), 2, figures)
        for figure in figures:
            body = figure.split("</figure>", 1)[0]
            svg = body.split("<svg", 1)[1]
            first_mark = min((i for i in (svg.find("<rect"), svg.find("<text"),
                                          svg.find("<polyline")) if i != -1), default=len(svg))
            self.assertLess(svg.index("<title"), svg.index("<desc"))
            self.assertLess(svg.index("<desc"), first_mark)
            self.assertLess(body.index("</svg>"), body.index("<figcaption>"))
            self.assertIn("<table>", body.split("<figcaption>", 1)[1])
        self.assertIn("unknown", page)
        for bad in NETWORK_TRIPWIRES:
            self.assertNotIn(bad, page)
        self.assertNotIn("<link", page.lower())
        hrefs = re.findall(r'href="([^"]*)"', page)
        ids = set(re.findall(r'id="([^"]*)"', page))
        self.assertTrue(hrefs)
        for href in hrefs:
            self.assertIn(href[1:], ids)

    def test_two_renders_of_the_same_model_get_the_same_chart_ids(self):
        def chart_panel(_ctx):
            return {"source": "s", "observed": None, "notes": [], "summary": "",
                    "blocks": self._chart_blocks()}

        registry = [db.PANELS[0], ("charts", "Charts", chart_panel), db.PANELS[-1]]
        with mock.patch.object(db, "PANELS", registry):
            model = db.build_model(self.world["data_home"], [str(self.world["checkout"])],
                                   {}, None)
            page1 = db.render_page(model, _FAKE_HOME.name)
            page2 = db.render_page(model, _FAKE_HOME.name)
        self.assertEqual(page1, page2)
        self.assertIn('id="chart-1-title"', page1)
        self.assertIn('id="chart-2-title"', page1)


class TypedCellIntegrationTests(_WorldCase):
    """The typed-cell mechanism reached the way a real panel reaches it: as a `table` block's
    row values in a page built through `build`, scrubbed then rendered exactly once -- this is
    exactly the shape T4's cost-by-basis table builds (PLAN D3 row 1: cells through
    `fmt_usd(value, basis)` / `fmt_credits`)."""

    def test_a_typed_cell_in_a_built_page_renders_markup_once_not_escaped_text(self):
        def cost_panel(_ctx):
            return {"source": "test fixture", "observed": "2026-09-01", "notes": [],
                    "summary": "cost fixture",
                    "blocks": [{"type": "table", "headers": ["basis", "usd"],
                               "rows": [["actual", {"fmt": "usd", "value": 1.5,
                                                    "basis": "actual"}],
                                       ["estimated", {"fmt": "usd", "value": None,
                                                     "basis": "estimated"}]]}]}

        registry = [db.PANELS[0], ("cost", "Cost", cost_panel), db.PANELS[-1]]
        with mock.patch.object(db, "PANELS", registry):
            rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        self.assertIn('<span class="label">actual</span>', page)
        self.assertIn('<span class="unknown">unknown</span>', page)
        self.assertNotIn("&lt;span", page)
        self.assertNotIn("&quot;label&quot;", page)


class StylesheetCompletionTests(_WorldCase):

    def setUp(self):
        super().setUp()
        rc, out, _stdout, stderr = self.build("out", "--json")
        self.assertEqual(rc, 0, stderr)
        self.html = self.page(out)
        self.style = self.html.split("<style>", 1)[1].split("</style>", 1)[0]

    def test_new_rules_are_present(self):
        for rule in (".label {", ".unknown {", "figure {", "figcaption {", "details {",
                    "svg { width: 100%; height: auto; }"):
            self.assertIn(rule, self.style)

    def test_label_is_monospace_and_muted(self):
        rule = self.style.split(".label {", 1)[1].split("}", 1)[0]
        self.assertIn("monospace", rule)
        self.assertIn("var(--muted)", rule)

    def test_unknown_is_italic_muted_and_never_hidden(self):
        rule = self.style.split(".unknown {", 1)[1].split("}", 1)[0]
        self.assertIn("italic", rule)
        self.assertIn("var(--muted)", rule)
        self.assertNotIn("display:none", rule.replace(" ", ""))
        self.assertNotIn("visibility:hidden", rule.replace(" ", ""))

    def test_dark_scheme_still_declared_exactly_once(self):
        self.assertEqual(self.style.count("prefers-color-scheme: dark"), 1)

    def test_no_url_import_or_link_anywhere_on_the_page(self):
        for bad in ("url(", "@import"):
            self.assertNotIn(bad, self.html)
        self.assertNotIn("<link", self.html.lower())


# ---------------------------------------------------------------------------------------------
# where and demo.

class CliTests(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="dashboard-cli-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.tmp)

    def test_where_prints_a_path_under_the_patched_data_home(self):
        rc, stdout, _stderr = _run(["where", "--no-git"])
        self.assertEqual(rc, 0)
        self.assertIn(_DATA_HOME.name, stdout)
        self.assertIn("env", stdout)
        rc, stdout, _stderr = _run(["where", "--no-git", "--json"])
        self.assertEqual(rc, 0)
        info = json.loads(stdout)
        self.assertEqual(info["origin"], "env")
        self.assertTrue(info["path"].startswith(_DATA_HOME.name), info)
        self.assertEqual(Path(info["path"]).name, "dashboard")
        self.assertEqual(os.listdir(_DATA_HOME.name), [])  # where writes nothing

    def test_demo_exits_zero_spawns_nothing_and_leaves_nothing_behind(self):
        scratch = self.tmp / "tempdir"
        scratch.mkdir()
        real_mod = db._mod

        def guarded(name):
            if name == "proc_runner":
                raise AssertionError("the demo must spawn nothing")
            return real_mod(name)

        with mock.patch.object(tempfile, "tempdir", str(scratch)), \
                mock.patch.object(db, "_mod", guarded):
            rc, stdout, stderr = _run(["demo"])
        self.assertEqual(rc, 0, stderr)
        self.assertEqual(os.listdir(scratch), [])
        self.assertEqual(os.listdir(_DATA_HOME.name), [])
        self.assertIn("1 mapped · 1 unmapped · 30 residue", stdout)
        page_line = [line for line in stdout.splitlines() if line.startswith("page (removed")]
        self.assertEqual(len(page_line), 1, stdout)
        page_path = page_line[0].split(": ", 1)[1]
        self.assertTrue(page_path.startswith(str(scratch)), page_path)
        self.assertFalse(os.path.exists(page_path))

    def test_build_summary_fits_one_screen(self):
        world = db.synthetic_world(self.tmp / "world")
        projects = self.tmp / "projects"
        projects.mkdir()
        os.chdir(world["checkout"])
        rc, stdout, stderr = _run(["build", "--data-home", str(world["data_home"]),
                                   "--out-dir", str(self.tmp / "out"), "--projects-dir",
                                   str(projects), "--no-git"])
        self.assertEqual(rc, 0, stderr)
        lines = stdout.splitlines()
        self.assertLessEqual(len(lines), 24)
        self.assertTrue(lines[0].startswith("page:"))
        self.assertTrue(any(line.startswith("caps hit:   none") for line in lines))
        self.assertTrue(any(line.startswith("  namespaces") for line in lines))
        self.assertTrue(any(line.startswith("  bounds") for line in lines))


# ---------------------------------------------------------------------------------------------
# Scale, scrubbing and the source itself.

class ScaleTests(unittest.TestCase):

    def test_fifteen_hundred_residue_are_counted_exactly_in_single_digit_seconds(self):
        tmp = tempfile.TemporaryDirectory(prefix="dashboard-scale-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        world = db.synthetic_world(root / "world", residue=1500)
        projects = root / "projects"
        projects.mkdir()
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(world["checkout"])
        started = time.monotonic()
        rc, stdout, stderr = _run(["build", "--data-home", str(world["data_home"]), "--out-dir",
                                   str(root / "out"), "--checkout", str(world["checkout"]),
                                   "--projects-dir", str(projects), "--no-git", "--json"])
        elapsed = time.monotonic() - started
        self.assertEqual(rc, 0, stderr)
        receipt = json.loads(stdout)
        self.assertEqual(receipt["classes"]["residue"]["count"], 1500)
        self.assertEqual(receipt["classes"]["mapped"]["count"], 1)
        self.assertEqual(receipt["classes"]["unmapped"]["count"], 1)
        self.assertEqual(receipt["caps_hit"], [])
        self.assertLess(elapsed, 10.0)


class ScrubTests(unittest.TestCase):

    def test_scrub_replaces_whole_components_only(self):
        self.assertEqual(db.scrub("/Users/ann/x", "/Users/ann"), "~/x")
        self.assertEqual(db.scrub("/Users/anna/x", "/Users/ann"), "/Users/anna/x")
        self.assertEqual(db.scrub("at /Users/ann — and /Users/ann/y", "/Users/ann"),
                         "at ~ — and ~/y")
        self.assertEqual(db.scrub("/Users/ann/x", "/Users/ann/"), "~/x")
        self.assertEqual(db.scrub("/x/y", "/"), "/x/y")
        self.assertEqual(db.scrub("/x/y", ""), "/x/y")
        self.assertIsNone(db.scrub(None, "/Users/ann"))

    def test_scrub_covers_the_realpath_spelling_of_home(self):
        tmp = tempfile.TemporaryDirectory(prefix="dashboard-scrub-")
        self.addCleanup(tmp.cleanup)
        base = Path(os.path.realpath(tmp.name))
        real = base / "real-home"
        real.mkdir()
        link = base / "link-home"
        os.symlink(real, link)
        self.assertEqual(db.scrub(f"{real}/a and {link}/b", str(link)), "~/a and ~/b")


class SourceTests(unittest.TestCase):

    def test_no_home_lookup_process_or_network_primitive_in_the_engine(self):
        text = DASHBOARD_PATH.read_text(encoding="utf-8")
        for token in ("Path" + ".home", "sub" + "process", "url" + "open", "http" + ".client"):
            self.assertNotIn(token, text)

    def test_pinned_constants(self):
        self.assertEqual(db.BUILD_SCHEMA_VERSION, 1)
        self.assertEqual((db.PAGE_NAME, db.RECEIPT_NAME, db.CONFIG_NAME),
                         ("index.html", "build.json", "config.json"))
        self.assertEqual(db.CSP, "default-src 'none'; style-src 'unsafe-inline'; img-src data:")
        self.assertEqual(db.RESIDUE_NAMESPACE_RE.pattern, r"^tmp[a-z0-9_]{8}-[0-9a-f]{8}$")
        self.assertEqual(
            (db.MAX_NAMESPACES_LISTED, db.MAX_NAMESPACES_READ, db.MAX_LEDGER_BYTES,
             db.MAX_KITS_PER_DIR, db.MAX_EVAL_RUNS_RENDERED, db.MAX_JOURNAL_DAYS,
             db.MAX_TELEMETRY_ENVELOPES_PER_SOURCE, db.GIT_TIMEOUT_SECONDS),
            (5000, 32, 8 * 1024 * 1024, 100, 10, 60, 120, 20))
        self.assertEqual(db.PLUGIN_ROOT, BIN_DIR.parent)
        self.assertEqual(db.default_caps(), {name: getattr(db, name) for name in db.CAP_NAMES})
        self.assertEqual(db.STORE_NAME, "dashboard")
        self.assertIn(db.STORE_NAME, rd.STORES)

    def test_residue_pattern_matches_tempfile_names_only(self):
        self.assertTrue(db.RESIDUE_NAMESPACE_RE.fullmatch("tmpab3_x9kd-1a2b3c4d"))
        for name in ("tmpab3_x9kd-1a2b3c4d\n", "tmpAB3_X9KD-1a2b3c4d", "tmpab3_x9k-1a2b3c4d",
                     "polytropos-1a2b3c4d", "tmpab3_x9kd-1a2b3c4g"):
            self.assertIsNone(db.RESIDUE_NAMESPACE_RE.fullmatch(name), name)


if __name__ == "__main__":
    unittest.main()
