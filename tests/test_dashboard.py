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
