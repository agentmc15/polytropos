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
* No build spawns a process: git verbs are disabled, or answered by an injected runner that
  spawns nothing. Git itself runs only in `GitEnabledDiscoveryTests` -- `git init` and the
  engine's two read-only verbs, through `discover_checkouts`, never through a build -- inside a
  temp repo, with the user's git configuration isolated and every call recorded to prove it ran
  there. It skips when git is not installed.
* A built `index.html` is only ever probed with assertions, never printed.
"""

import ast
import builtins
import collections.abc
import contextlib
import html
import importlib.util
import io
import itertools
import json
import math
import os
import re
import shutil
import signal
import stat
import sys
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
ah = _load("attempt_history")
al = _load("attempt_ledger")
rs = _load("routing_scorecard")
kc = _load("kit_contract")

_DATA_HOME = None
_FAKE_HOME = None
_ENV_PATCH = None
_PROJECTS_GUARD = None


class _NotAnEmptyTempProjectsDir(BaseException):
    """Raised by the module-wide guard below when a build or model a test runs hands the
    routing scorecard anything but an existing, empty temp projects dir. A BaseException, so the
    engine's own `except Exception` containment cannot turn a GUARDRAILS breach into a quiet
    panel note: the test errors instead."""


def _guarded_history_card(real):
    """`routing_scorecard.assemble_history_card` -- the one projects-dir reader the dashboard
    calls (PLAN D15) -- refusing any `projects_dir` that is not an existing, empty directory
    under the temp root (GUARDRAILS: every build and model a test runs prices from an empty temp
    `--projects-dir`, never the scorecard's default)."""
    def guarded(*args, projects_dir=None, **kwargs):
        ok = False
        if projects_dir is not None:
            try:
                resolved = os.path.realpath(projects_dir)
                temp_root = os.path.realpath(tempfile.gettempdir())
                ok = (resolved.startswith(temp_root + os.sep) and os.path.isdir(resolved)
                      and not os.listdir(resolved))
            except OSError:
                ok = False
        if not ok:
            raise _NotAnEmptyTempProjectsDir(
                f"assemble_history_card was handed projects_dir={projects_dir!r}; every build "
                f"and model a test runs passes an empty temp projects dir (GUARDRAILS)")
        return real(*args, projects_dir=projects_dir, **kwargs)
    return guarded


def setUpModule():
    global _DATA_HOME, _FAKE_HOME, _ENV_PATCH, _PROJECTS_GUARD
    _DATA_HOME = tempfile.TemporaryDirectory(prefix="polytropos-test-data-")
    _FAKE_HOME = tempfile.TemporaryDirectory(prefix="polytropos-test-home-")
    _ENV_PATCH = mock.patch.dict(os.environ, {"POLYTROPOS_DATA_HOME": _DATA_HOME.name,
                                              "HOME": _FAKE_HOME.name})
    _ENV_PATCH.start()
    scorecard = db._mod("routing_scorecard")
    _PROJECTS_GUARD = mock.patch.object(scorecard, "assemble_history_card",
                                        _guarded_history_card(scorecard.assemble_history_card))
    _PROJECTS_GUARD.start()


def tearDownModule():
    _PROJECTS_GUARD.stop()
    _ENV_PATCH.stop()
    _DATA_HOME.cleanup()
    _FAKE_HOME.cleanup()


def _opts(case, **extra):
    """`build_model` opts for one test: an empty temp projects dir, always (GUARDRAILS), plus
    whatever the test sets. A `_WorldCase` lends its own empty `self.projects`; any other case
    gets a fresh empty temp dir, removed after the test."""
    projects = getattr(case, "projects", None)
    if projects is None:
        tmp = tempfile.TemporaryDirectory(prefix="dashboard-projects-")
        case.addCleanup(tmp.cleanup)
        projects = case.projects = Path(tmp.name)
    return {"notes": [], "projects_dir": str(projects), **extra}


EXACT_CSP_META = ('<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
                  'style-src \'unsafe-inline\'; img-src data:">')
NETWORK_TRIPWIRES = ("<script", "src=", 'href="http', 'href="//', "@import", "url(")
UNKNOWN_SPAN = '<span class="unknown">unknown</span>'
UNKNOWN_COUNT = {"count": None, "qualifier": "unknown"}


def exact(count):
    return {"count": count, "qualifier": "exact"}


def absent_classes(checkouts):
    """An absent data home: exact zeros, and every checkout definitively without a namespace."""
    return {
        "listing": "absent", "mapped": [], "unmapped": [],
        "residue": {**exact(0), "sample": []},
        "counts": {"mapped": exact(0), "unmapped": exact(0), "residue": exact(0)},
        "by_checkout": [{"checkout": checkout, "state": "absent"} for checkout in checkouts],
    }


def unknown_classes(checkouts):
    """Nothing could be classified: no rows and every count unknown -- never a zero."""
    return {
        "listing": "failed", "mapped": [], "unmapped": [],
        "residue": {**UNKNOWN_COUNT, "sample": []},
        "counts": {"mapped": UNKNOWN_COUNT, "unmapped": UNKNOWN_COUNT, "residue": UNKNOWN_COUNT},
        "by_checkout": [{"checkout": checkout, "state": "unknown"} for checkout in checkouts],
    }


@contextlib.contextmanager
def _scandir_in_name_order():
    """`os.scandir` yielding entries sorted by name, so a lowered listing cap cuts a KNOWN tail
    instead of whatever the filesystem's own order happens to be."""
    real = os.scandir

    @contextlib.contextmanager
    def ordered(path):
        with real(path) as found:
            entries = sorted(found, key=lambda entry: entry.name)
        yield iter(entries)

    with mock.patch("os.scandir", ordered):
        yield


def _section(page, pid):
    return page.split(f'<section id="{pid}">', 1)[1].split("</section>", 1)[0]

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


_AGE_TEXT_RE = re.compile(r"age: (?:-?\d+ days?|n/a)")


def _without_age(lines):
    """Neutralise every panel's `age: N days` segment (T6: telemetry/journal are the first
    panels with a genuinely dated `observed`, so their age is intentionally `now`-dependent,
    exactly like the built-at line PLAN D9 already excepts -- never a source of a real
    difference to compare away, but not a bug either when two builds pass a different `now`)."""
    return [_AGE_TEXT_RE.sub("age: <varies with build time>", line) for line in lines]


def _chmod_restorable(case, path, mode):
    original = stat.S_IMODE(os.lstat(path).st_mode)
    os.chmod(path, mode)
    case.addCleanup(os.chmod, path, original)


class _WorldCase(unittest.TestCase):
    """A fresh synthetic world per test, with the process sitting inside its checkout."""

    residue = 30
    # P3 fix round M1: True also writes the synthetic plugin install's captures into its namespace.
    plugin_install = False

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="dashboard-test-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.world = db.synthetic_world(self.tmp / "world", residue=self.residue,
                                        plugin_install=self.plugin_install)
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
        self.assertEqual(mapped["stores"], ["telemetry", "journal", "prefs", "attempts", "evals"])
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

    def test_absent_or_file_data_home_is_a_note_and_exact_zero_classes(self):
        checkouts = [str(self.world["checkout"])]
        classes, notes = self.classify(data_home=self.tmp / "nowhere")
        self.assertEqual(classes, absent_classes(checkouts))
        self.assertTrue(any("does not exist" in note for note in notes), notes)
        a_file = self.tmp / "data-home-file"
        a_file.write_text("not a directory\n")
        classes, notes = self.classify(data_home=a_file)
        self.assertEqual(classes, absent_classes(checkouts))
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
        self.assertEqual(classes, unknown_classes([str(self.world["checkout"])]))
        self.assertTrue(any("could not be listed" in note for note in notes), notes)
        self.assertTrue(any("could not be looked up by name (PermissionError)" in note
                            for note in notes), notes)

    def test_lowered_listing_cap_is_noted_on_its_panel_in_bounds_and_in_the_receipt(self):
        with _scandir_in_name_order():
            model = db.build_model(self.world["data_home"], [str(self.world["checkout"])],
                                   _opts(self), {"MAX_NAMESPACES_LISTED": 5})
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
        # In name order the mapped namespace ("checkout-…") comes first, then the residue
        # ("tmp…"), then "unmapped-…". The capped listing reached the first five names; the
        # mapped one among them was already looked up by name, so it classified four residue
        # and no unmapped namespace -- figures that are a lower bound and unknown, never exact.
        classes = model["classes"]
        self.assertEqual(classes["listing"], "truncated")
        self.assertEqual(classes["counts"], {"mapped": exact(1), "unmapped": UNKNOWN_COUNT,
                                             "residue": {"count": 4, "qualifier": "lower_bound"}})
        self.assertEqual(classes["residue"]["sample"], sorted(self.world["residue"])[:3])
        page = db.render_page(model, _FAKE_HOME.name)
        section = page.split('<section id="namespaces">', 1)[1].split("</section>", 1)[0]
        self.assertIn(f"<li>{html.escape(panel_notes[0], quote=True)}</li>", section)
        bounds = page.split('<section id="bounds">', 1)[1]
        self.assertIn("<td>MAX_NAMESPACES_LISTED</td><td>5</td><td>hit</td>", bounds)
        self.assertIn(html.escape(f"namespaces: {panel_notes[0]}", quote=True), bounds)
        receipt = db.build_receipt(model, _FAKE_HOME.name, self.tmp / "out")
        self.assertEqual(receipt["caps_hit"], ["MAX_NAMESPACES_LISTED"])
        self.assertIn(f"namespaces: {panel_notes[0]}", receipt["notes"])
        self.assertEqual(receipt["classes"], {
            "listing": "truncated", "mapped": exact(1), "unmapped": UNKNOWN_COUNT,
            "residue": {"count": 4, "qualifier": "lower_bound",
                        "sample": sorted(self.world["residue"])[:3]}})
        self.assertIn("1 mapped · " + UNKNOWN_SPAN + " unmapped · at least 4 residue.", section)
        self.assertIn("at least 4 namespaces, e.g.", section)

    def test_a_raising_namespaces_builder_cannot_drop_the_cap_note(self):
        def broken(_ctx):
            raise RuntimeError("boom")

        registry = [("namespaces", "Namespaces", broken), db.PANELS[-1]]
        with mock.patch.object(db, "PANELS", registry):
            model = db.build_model(self.world["data_home"], [str(self.world["checkout"])],
                                   _opts(self), {"MAX_NAMESPACES_LISTED": 5})
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


class ClassificationCompletenessTests(_WorldCase):
    """The classes say how complete they are (PLAN D5, D7c, R3; P1 fix round F1): a cut or
    failed listing, or a failed lookup, is a lower bound or `unknown` -- never a zero, and never
    "No namespace in this data home for" unless every lookup definitively found none."""

    def last_sorting_checkout(self):
        checkout = self.tmp / "zzzz-sorts-last"
        checkout.mkdir()
        namespace = rd.project_namespace(checkout)
        (self.world["data_home"] / namespace / "attempts").mkdir(parents=True)
        return str(checkout), namespace

    def test_a_capped_listing_never_drops_the_mapped_namespace_that_sorts_last(self):
        checkout, namespace = self.last_sorting_checkout()
        names = sorted(os.listdir(self.world["data_home"]))
        self.assertGreaterEqual(len(names), 4)
        self.assertEqual(names[-1], namespace)
        with _scandir_in_name_order():  # the one listed entry is names[0], never the mapped one
            model = db.build_model(self.world["data_home"], [checkout], _opts(self),
                                   {"MAX_NAMESPACES_LISTED": 1})
        classes = model["classes"]
        self.assertEqual([row["namespace"] for row in classes["mapped"]], [namespace])
        self.assertEqual(classes["mapped"][0]["stores"], ["attempts"])
        self.assertEqual(classes["by_checkout"], [{"checkout": checkout, "state": "mapped"}])
        receipt = db.build_receipt(model, _FAKE_HOME.name, self.tmp / "out")
        self.assertEqual(receipt["classes"], {
            "listing": "truncated", "mapped": exact(1),
            "unmapped": {"count": 1, "qualifier": "lower_bound"},
            "residue": {**UNKNOWN_COUNT, "sample": []}})
        for name in ("unmapped", "residue"):
            self.assertIn(receipt["classes"][name]["qualifier"], ("lower_bound", "unknown"))
        page = db.render_page(model, _FAKE_HOME.name)
        section = _section(page, "namespaces")
        self.assertNotIn("No namespace in this data home for", page)
        self.assertIn(f"1 mapped · at least 1 unmapped · {UNKNOWN_SPAN} residue.", section)
        self.assertIn("stopped at its cap (MAX_NAMESPACES_LISTED)", section)
        self.assertNotIn("No namespaces were found", page)
        summary = "\n".join(db.summary_lines(receipt))
        self.assertIn("namespaces: 1 mapped · at least 1 unmapped · unknown residue", summary)
        self.assertIn("data-home listing truncated", summary)
        panel_summary = model["panels"][0]["summary"]
        self.assertTrue(panel_summary.startswith("1 mapped · at least 1 unmapped · unknown "
                                                 "residue"), panel_summary)

    @unittest.skipIf(os.geteuid() == 0, "root lists a directory through mode 0o300")
    def test_an_unlistable_data_home_keeps_mapped_exact_and_the_rest_unknown(self):
        _chmod_restorable(self, self.world["data_home"], 0o300)  # search, but no read
        rc, out, stdout, stderr = self.build("out", "--json")
        self.assertEqual(rc, 0, stderr)
        receipt = self.receipt(out)
        self.assertEqual(json.loads(stdout), receipt)
        self.assertEqual(receipt["classes"], {
            "listing": "failed", "mapped": exact(1), "unmapped": UNKNOWN_COUNT,
            "residue": {**UNKNOWN_COUNT, "sample": []}})
        self.assertTrue(any("could not be listed (PermissionError)" in note
                            for note in receipt["notes"]), receipt["notes"])
        page = self.page(out)
        section = _section(page, "namespaces")
        self.assertIn(self.world["namespace"], section)  # the lookup still found it, by name
        self.assertIn(f"1 mapped · {UNKNOWN_SPAN} unmapped · {UNKNOWN_SPAN} residue.", section)
        self.assertIn("could not be listed, so whether it holds unmapped or residue", section)
        for wrong in ("0 unmapped", "0 residue", "No namespaces were found",
                      "No namespace in this data home for"):
            self.assertNotIn(wrong, page)

    @unittest.skipIf(os.geteuid() == 0, "root looks a name up through mode 0")
    def test_failed_lookups_leave_the_checkout_unknown_never_absent(self):
        _chmod_restorable(self, self.world["data_home"], 0o000)
        rc, out, stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        receipt = self.receipt(out)
        self.assertEqual(receipt["classes"], {
            "listing": "failed", "mapped": UNKNOWN_COUNT, "unmapped": UNKNOWN_COUNT,
            "residue": {**UNKNOWN_COUNT, "sample": []}})
        self.assertTrue(any("could not be looked up by name (PermissionError)" in note
                            for note in receipt["notes"]), receipt["notes"])
        page = self.page(out)
        checkout = os.path.realpath(self.world["checkout"])
        self.assertIn(f"It is unknown whether this data home holds a namespace for: {checkout}",
                      page)
        self.assertIn(f"{UNKNOWN_SPAN} mapped · {UNKNOWN_SPAN} unmapped · {UNKNOWN_SPAN} "
                      f"residue.", page)
        for wrong in ("No namespace in this data home for", "0 mapped", "0 unmapped",
                      "0 residue", "No namespaces were found"):
            self.assertNotIn(wrong, page)
        self.assertIn("No namespace can be shown: the data home could not be listed", page)
        self.assertIn("namespaces: unknown mapped · unknown unmapped · unknown residue", stdout)

    def test_a_cut_listing_that_found_nothing_says_it_was_cut_not_that_none_exist(self):
        (self.world["data_home"] / "0-a-plain-file").write_text("sorts first\n")
        with _scandir_in_name_order():
            model = db.build_model(self.world["data_home"], [], _opts(self),
                                   {"MAX_NAMESPACES_LISTED": 1})
        self.assertEqual(model["classes"]["counts"], {"mapped": exact(0),
                                                      "unmapped": UNKNOWN_COUNT,
                                                      "residue": UNKNOWN_COUNT})
        section = _section(db.render_page(model, _FAKE_HOME.name), "namespaces")
        self.assertNotIn("No namespaces were found", section)
        self.assertIn("No namespace was found among the entries the capped listing reached",
                      section)

    def test_an_absent_data_home_renders_absent_never_zeros(self):
        out = self.tmp / "out"
        nowhere = self.tmp / "nowhere"
        argv = self.build_argv(out)
        argv[argv.index("--data-home") + 1] = str(nowhere)
        rc, stdout, stderr = _run(argv)
        self.assertEqual(rc, 0, stderr)
        self.assertEqual(self.receipt(out)["classes"], {
            "listing": "absent", "mapped": exact(0), "unmapped": exact(0),
            "residue": {**exact(0), "sample": []}})
        page = self.page(out)
        self.assertIn(f"Data home {nowhere}: absent — no namespaces.", page)
        self.assertIn("namespaces: data home absent — no namespaces", stdout)
        # Page-wide and stdout-wide: an absent data home renders as text everywhere on the page,
        # never a zero -- the attempts panel's own residue line (T4) says "No data home, so no
        # residue namespaces to count." for this exact listing state (see NOTES.md, T4 retry).
        for text in (page, stdout):
            for wrong in ("0 mapped", "0 unmapped", "0 residue"):
                self.assertNotIn(wrong, text)

    def test_an_empty_but_existing_data_home_renders_text_never_zeros(self):
        empty_home = self.tmp / "empty-home"
        empty_home.mkdir()
        out = self.tmp / "out"
        argv = self.build_argv(out)
        argv[argv.index("--data-home") + 1] = str(empty_home)
        rc, stdout, stderr = _run(argv)
        self.assertEqual(rc, 0, stderr)
        self.assertEqual(self.receipt(out)["classes"], {
            "listing": "complete", "mapped": exact(0), "unmapped": exact(0),
            "residue": {**exact(0), "sample": []}})
        page = self.page(out)
        self.assertIn(f"Data home {empty_home}: empty — no namespaces.", page)
        self.assertIn("namespaces: data home empty — no namespaces", stdout)
        self.assertIn("No residue namespaces (heuristic:", page)
        for text in (page, stdout):
            for wrong in ("0 mapped", "0 unmapped", "0 residue"):
                self.assertNotIn(wrong, text)

    def test_a_link_at_the_expected_name_is_not_a_namespace_and_is_noted(self):
        data_home, namespace = self.world["data_home"], self.world["namespace"]
        elsewhere = self.tmp / "elsewhere-namespace"
        os.rename(data_home / namespace, elsewhere)
        os.symlink(elsewhere, data_home / namespace)
        classes, notes = self.classify()
        self.assertEqual(classes["mapped"], [])
        self.assertEqual(classes["counts"]["mapped"], exact(0))
        self.assertEqual(classes["by_checkout"],
                         [{"checkout": str(self.world["checkout"]), "state": "absent"}])
        self.assertNotIn(namespace, [row["namespace"] for row in classes["unmapped"]])
        skipped = [note for note in notes if "not a directory without following links" in note]
        self.assertEqual(len(skipped), 1, notes)
        self.assertIn(namespace, skipped[0])

    @unittest.skipIf(os.geteuid() == 0, "root searches a directory through mode 0")
    def test_a_data_home_that_cannot_be_examined_is_unknown_never_absent(self):
        locked = self.tmp / "locked"
        (locked / "data-home").mkdir(parents=True)
        _chmod_restorable(self, locked, 0o000)
        classes, notes = self.classify(data_home=locked / "data-home")
        self.assertEqual(classes, unknown_classes([str(self.world["checkout"])]))
        self.assertTrue(any("could not be examined (PermissionError)" in note for note in notes),
                        notes)
        self.assertFalse(any("does not exist" in note for note in notes), notes)


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
        # P2 fix round: refused at the `lstat` gate every non-regular leaf now meets, before
        # any open (it was refused by `safe_paths`' O_NOFOLLOW open before).
        self.assertIn("is a symlink, not a regular file — never opened; treated as absent",
                      notes[0])


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
        # P3 fix round M1: a blank plugin root would hash the working directory as the plugin
        # install, so it is refused like every other blank path.
        for name in ("out_dir", "data_home", "projects_dir", "plugin_root"):
            with self.subTest(name=name):
                kwargs = {"data_home": self.world["data_home"], "out_dir": self.tmp / "out",
                          "projects_dir": self.projects, name: ""}
                with self.assertRaises(refused):
                    db.assemble_build(self.cwd, git=False, home=_FAKE_HOME.name, **kwargs)
        self.assertNothingWrittenAnywhere(self.tmp / "out")

    def test_an_empty_data_home_checkout_or_config_dir_never_means_the_working_directory(self):
        (self.cwd / "looks-like-a-namespace").mkdir()
        model = db.build_model("", [str(self.world["checkout"])], _opts(self), None)
        self.assertEqual(model["classes"], unknown_classes([str(self.world["checkout"])]))
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
        # The pinned receipt shape (T8's skill relays it): exactly these keys, and `count` is
        # null exactly when the qualifier is `unknown`.
        self.assertEqual(receipt["classes"], {
            "listing": "complete", "mapped": exact(1), "unmapped": exact(1),
            "residue": {**exact(30), "sample": sorted(self.world["residue"])[:3]}})
        self.assertEqual([panel["id"] for panel in receipt["panels"]],
                         ["namespaces", "attempts", "scorecard", "kits", "telemetry", "journal",
                          "evals", "training", "rsi", "bounds"])
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
        early = db.build_model(
            self.world["data_home"], checkouts,
            _opts(self, now=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)), None)
        late = db.build_model(
            self.world["data_home"], checkouts,
            _opts(self, now=datetime(2026, 1, 2, 17, 30, tzinfo=timezone.utc)), None)
        page_early = db.render_page(early, _FAKE_HOME.name)
        page_late = db.render_page(late, _FAKE_HOME.name)
        self.assertNotEqual(page_early, page_late)
        # T6: telemetry/journal now carry a genuinely dated `observed`, so their `age` line is
        # intentionally `now`-dependent across these two explicit, calendar-day-apart `now`
        # values -- normalised away here on the same terms as the built-at line itself, never
        # hiding a difference anywhere else on the page.
        self.assertEqual(_without_age(_without_built_at(page_early)),
                         _without_age(_without_built_at(page_late)))

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
        model = db.build_model(None, [str(self.world["checkout"])], _opts(self), None)
        self.assertEqual(model["classes"], unknown_classes([str(self.world["checkout"])]))
        self.assertIsNone(model["data_home"])
        self.assertIn("namespaces: no data home was given — nothing was classified",
                      model["notes"])
        page = db.render_page(model, _FAKE_HOME.name)
        self.assertIn(f"Data home {UNKNOWN_SPAN}: {UNKNOWN_SPAN} mapped · {UNKNOWN_SPAN} "
                      f"unmapped · {UNKNOWN_SPAN} residue.", page)
        self.assertIn("No data home was given, so nothing was listed or looked up.", page)
        self.assertNotIn("0 mapped", page)
        self.assertNotIn("No namespace in this data home for", page)
        self.assertIn("data home: unknown", page)

    def test_model_is_json_serializable(self):
        model = db.build_model(self.world["data_home"], [str(self.world["checkout"])],
                               _opts(self, notes=["a note"]), None)
        self.assertEqual(json.loads(json.dumps(model))["schema_version"], 1)
        self.assertEqual(model["notes"][0], "a note")
        self.assertEqual([panel["id"] for panel in model["panels"]],
                         ["namespaces", "attempts", "scorecard", "kits", "telemetry", "journal",
                          "evals", "training", "rsi", "bounds"])

    def test_a_panel_builder_that_raises_is_a_note_not_an_exception(self):
        def broken(_ctx):
            raise RuntimeError("/secret/path/in/a/message")

        registry = [db.PANELS[0], ("attempts", "Attempts", broken), db.PANELS[-1]]
        with mock.patch.object(db, "PANELS", registry):
            model = db.build_model(self.world["data_home"], [str(self.world["checkout"])],
                                   _opts(self), None)
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

    def test_fmt_count_never_truncates(self):
        # P1 fix round F3: 0.9 once rendered `0`, 2.7 `2` and True `1`.
        for value, text in ((True, "True"), (False, "False"), (7, "7"), (2.0, "2"),
                            (-2.0, "-2"), (-0.0, "0"), (0.9, "0.9"), (2.7, "2.7"),
                            (1e23, "1e+23"), (float("nan"), "nan"), (float("-inf"), "-inf"),
                            ("0.9", "0.9"), ("not a number", "not a number")):
            with self.subTest(value=value):
                self.assertEqual(db.fmt_count(value), text)
        self.assertEqual(db.fmt_count(None), UNKNOWN_SPAN)
        for value, text in ((0.9, "0.9"), (True, "True"), (2.0, "2")):
            with self.subTest(typed=value):
                self.assertEqual(db._render_cell({"fmt": "count", "value": value}), text)

    def test_a_qualified_count_never_claims_more_than_it_knows(self):
        self.assertEqual(db.fmt_count(3, "lower_bound"), "at least 3")
        self.assertEqual(db.fmt_count(3, "exact"), "3")
        for value, qualifier in ((0, "lower_bound"), (None, "lower_bound"), (True, "lower_bound"),
                                 (2.5, "lower_bound"), (-1, "lower_bound"), (5, "unknown"),
                                 (5, "approximately"), (None, "exact")):
            with self.subTest(value=value, qualifier=qualifier):
                self.assertEqual(db.fmt_count(value, qualifier), UNKNOWN_SPAN)
        self.assertEqual(db._render_cell({"fmt": "count", "value": 3, "qualifier": "lower_bound"}),
                         "at least 3")
        self.assertEqual(db._render_cell({"fmt": "count", "value": 3, "qualifier": None}), "3")
        # A `p` block's `parts` render each typed cell once and escape each plain part once.
        self.assertEqual(
            db._render_block({"type": "p", "parts": [
                "n: ", {"fmt": "count", "value": None, "qualifier": "unknown"}, " <b>&", None]}),
            f"<p>n: {UNKNOWN_SPAN} &lt;b&gt;&amp;{UNKNOWN_SPAN}</p>")

    def test_fmt_usd_requires_a_basis_label_and_never_prints_a_bare_dollar(self):
        self.assertEqual(db.fmt_usd(None, "est."), '<span class="unknown">unknown</span>')
        self.assertNotIn("$", db.fmt_usd(None, "est."))
        rendered = db.fmt_usd(1.5, "est.")
        self.assertIn("$1.50", rendered)
        self.assertIn('<span class="label">est.</span>', rendered)
        with self.assertRaises(TypeError):
            db.fmt_usd(1.5)  # a DIRECT call without the basis still fails loudly

    def test_a_typed_usd_cell_without_a_basis_never_prints_a_dollar(self):
        # P1 fix round F2: a typed cell cannot fail loudly, so the rendering carries the rule.
        for cell in ({"fmt": "usd", "value": 2.5}, {"fmt": "usd", "value": 2.5, "basis": ""},
                     {"fmt": "usd", "value": 2.5, "basis": "   "},
                     {"fmt": "usd", "value": 2.5, "basis": None}):
            with self.subTest(cell=cell):
                rendered = db._render_cell(cell)
                self.assertEqual(rendered, '2.50 <span class="label">basis missing</span>')
                self.assertNotIn("$", rendered)
        self.assertEqual(db._render_cell({"fmt": "usd", "value": 2.5, "basis": "est."}),
                         '$2.50 <span class="label">est.</span>')
        self.assertEqual(db._render_cell({"fmt": "usd", "value": None}), UNKNOWN_SPAN)
        self.assertEqual(db.fmt_usd(float("nan"), " "),
                         'nan <span class="label">basis missing</span>')
        table = db.html_table(["usd"], [[{"fmt": "usd", "value": 2.5, "basis": "\t"}]])
        self.assertNotIn("$", table)
        self.assertIn('<td>2.50 <span class="label">basis missing</span></td>', table)

    def test_a_known_sub_cent_dollar_never_renders_as_zero(self):
        # P1 fix round F7. Compared as the whole amount, not a substring: "$0.004" contains
        # "$0.00".
        def amount(value):
            return db.fmt_usd(value, "est.").split(" <span", 1)[0]

        for value, text in ((0.004, "$0.004"), (-0.004, "$-0.004"), (0.0049, "$0.0049"),
                            (1e-05, "$1e-05"), (-1e-09, "$-1e-09"), (0.005, "$0.01"),
                            (1.5, "$1.50"), (-1.5, "$-1.50"), (1234.5, "$1,234.50"),
                            (0, "$0.00"), (0.0, "$0.00"), (-0.0, "$0.00")):
            with self.subTest(value=value):
                self.assertEqual(amount(value), text)
        self.assertEqual(db.fmt_usd(0.004, "est."), '$0.004 <span class="label">est.</span>')
        self.assertEqual(db.fmt_usd(0.004, ""), '0.004 <span class="label">basis missing</span>')

    def test_an_int_too_large_for_a_float_is_its_own_text_not_a_crash(self):
        huge = 10 ** 400
        self.assertEqual(db.fmt_usd(huge, "est."), f'{huge} <span class="label">est.</span>')
        self.assertEqual(db.fmt_credits(huge), str(huge))
        self.assertEqual(db.fmt_count(huge), str(huge))

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


class ChartGeometryAndTwinTests(unittest.TestCase):
    """P1 fix round F6: only finite numbers reach the geometry, and a twin's value column can
    carry a typed cell (a dollar sparkline keeps its basis on every row)."""

    @staticmethod
    def svg(fig):
        return fig.split("<svg", 1)[1].split("</svg>", 1)[0]

    @staticmethod
    def twin(fig):
        return fig.split("<figcaption>", 1)[1]

    def test_a_non_finite_bar_draws_nothing_and_breaks_no_other_bar(self):
        rows = [{"label": "a", "value": 2}, {"label": "b", "value": float("nan")},
                {"label": "c", "value": 4}, {"label": "d", "value": float("inf")},
                {"label": "e", "value": float("-inf")}, {"label": "f", "value": 10 ** 400}]
        fig = db.svg_bars(rows, "T", "D", "label", "value")
        svg = self.svg(fig)
        widths = [float(width) for width in re.findall(r'<rect [^>]*width="([^"]+)"', svg)]
        plot_width = db.CHART_WIDTH - db.BAR_LABEL_WIDTH - 8
        self.assertEqual(widths, [plot_width / 2, float(plot_width)])
        for bad in ("nan", "inf"):
            self.assertNotIn(bad, svg.lower())
        twin = self.twin(fig)
        for text in ("<td>nan</td>", "<td>inf</td>", "<td>-inf</td>", f"<td>{10 ** 400}</td>"):
            self.assertIn(text, twin)

    def test_a_non_finite_point_breaks_the_line_and_never_reaches_the_geometry(self):
        points = [("d1", 1), ("d2", 2), ("d3", float("nan")), ("d4", 3), ("d5", 4),
                  ("d6", float("inf"))]
        fig = db.svg_sparkline(points, "S", "D")
        svg = self.svg(fig)
        self.assertEqual(svg.count("<polyline"), 2)
        for bad in ("nan", "inf"):
            self.assertNotIn(bad, svg.lower())
        for group in re.findall(r'points="([^"]+)"', svg):
            for pair in group.split():
                self.assertTrue(all(math.isfinite(float(n)) for n in pair.split(",")), pair)
        twin = self.twin(fig)
        self.assertIn("<td>d3</td><td>nan</td>", twin)
        self.assertIn("<td>d6</td><td>inf</td>", twin)

    def test_a_value_cell_twin_renders_each_dollar_once_beside_its_basis(self):
        fig = db.svg_sparkline([("d1", 1.5), ("d2", None), ("d3", 2)], "Spend", "Spend by day",
                               value_header="USD (est.)",
                               value_cell={"fmt": "usd", "basis": "est."})
        twin = self.twin(fig)
        self.assertIn("<th>label</th><th>USD (est.)</th>", twin)
        self.assertIn('<td>$1.50 <span class="label">est.</span></td>', twin)
        self.assertIn('<td>$2.00 <span class="label">est.</span></td>', twin)
        self.assertIn(f"<td>d2</td><td>{UNKNOWN_SPAN}</td>", twin)
        self.assertEqual(twin.count('<span class="label">est.</span>'), 2)
        self.assertNotIn("&lt;span", fig)
        bars = db.svg_bars([{"k": "x", "v": 3}], "T", "D", "k", "v", value_header="USD",
                           value_cell={"fmt": "usd", "basis": "actual"})
        self.assertIn("<th>k</th><th>USD</th>", bars)
        self.assertIn('<td>$3.00 <span class="label">actual</span></td>', bars)
        self.assertNotIn("&lt;span", bars)

    def test_without_the_new_parameters_the_twin_headers_are_as_before(self):
        self.assertIn("<th>k</th><th>v</th>",
                      db.svg_bars([{"k": "x", "v": 3}], "T", "D", "k", "v"))
        self.assertIn("<th>label</th><th>value</th>", db.svg_sparkline([("d1", 1)], "S", "D"))


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
        model = db.build_model(None, [], _opts(self), None)
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
                                   _opts(self), None)
            page1 = db.render_page(model, _FAKE_HOME.name)
            page2 = db.render_page(model, _FAKE_HOME.name)
        self.assertEqual(page1, page2)
        self.assertIn('id="chart-1-title"', page1)
        self.assertIn('id="chart-2-title"', page1)

    def test_chart_blocks_pass_value_header_and_value_cell_through(self):
        def chart_panel(_ctx):
            return {"source": "test fixture", "observed": "2026-09-01", "notes": [],
                    "summary": "typed twins",
                    "blocks": [
                        {"type": "svg_sparkline", "title": "Spend", "desc": "by day",
                         "points": [["d1", 1.5], ["d2", None]], "value_header": "USD",
                         "value_cell": {"fmt": "usd", "basis": "est."}},
                        {"type": "svg_bars", "title": "Cost", "desc": "by kit",
                         "label_key": "kit", "value_key": "usd", "value_header": "USD",
                         "value_cell": {"fmt": "usd", "basis": "actual"},
                         "rows": [{"kit": "demo", "usd": 2}]},
                    ]}

        registry = [db.PANELS[0], ("charts", "Charts", chart_panel), db.PANELS[-1]]
        with mock.patch.object(db, "PANELS", registry):
            rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "charts")
        self.assertEqual(section.count("<th>USD</th>"), 2)
        self.assertIn('<td>$1.50 <span class="label">est.</span></td>', section)
        self.assertIn('<td>$2.00 <span class="label">actual</span></td>', section)
        self.assertNotIn("&lt;span", section)


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


class PageWideEscapingTests(_WorldCase):
    """P1 fix round F5: formatter output is never escaped a second time ANYWHERE on the page.
    Every later task re-runs this, so a panel that stores a pre-rendered `fmt_*` string in a
    cell, a list item or a `p` text is caught here."""

    def test_the_synthetic_world_page_holds_no_twice_escaped_markup(self):
        rc, out, _stdout, stderr = self.build()  # --out-dir, empty --projects-dir, --no-git
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        self.assertNotIn("&lt;span", page)
        self.assertNotIn("&amp;lt;", page)

    def test_the_tripwire_trips_on_a_pre_rendered_formatter_string(self):
        def wrong(_ctx):  # the mistake the tripwire exists for: a rendered string as a cell
            return {"source": "fixture", "observed": None, "notes": [], "summary": "wrong",
                    "blocks": [{"type": "table", "headers": ["usd"],
                                "rows": [[db.fmt_usd(1.5, "est.")]]}]}

        registry = [db.PANELS[0], ("wrong", "Wrong", wrong), db.PANELS[-1]]
        with mock.patch.object(db, "PANELS", registry):
            rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        self.assertIn("&lt;span", self.page(out))


class RenderContainmentTests(_WorldCase):
    """P1 fix round F4 (PLAN D10: never a crash): a malformed block renders as its own text,
    and a panel whose rendering still raises becomes a fallback section whose note -- the
    exception type only -- reaches the page, the bounds section and build.json."""

    SENTINEL = "SENTINEL-RENDER-MESSAGE /never/on/the/page"
    NOTE = "this panel could not be rendered (RuntimeError)"

    @staticmethod
    def malformed(_ctx):
        return {"source": "fixture", "observed": None, "notes": "one bare string note",
                "summary": "malformed fixture",
                "blocks": [
                    {"type": "table", "headers": 7, "rows": [None, 5, "a bare row", ["ok", 1]]},
                    {"type": "table", "headers": ["h"], "rows": 5},
                    {"type": "list", "items": 3},
                    {"type": "p", "parts": 4},
                    {"type": "svg_bars", "title": "B", "desc": "D", "label_key": ["unhashable"],
                     "value_key": "v", "rows": [7, {"v": 2}]},
                    {"type": "svg_sparkline", "title": "S", "desc": "D",
                     "points": [1, ["a", 2], ["b"], None, ["c", 3, 4]]},
                    {"type": "table", "headers": ["h"], "rows": [[{"fmt": ["unhashable"]}]]},
                    "not a mapping",
                ]}

    @staticmethod
    def charts(_ctx):
        return {"source": "fixture", "observed": "2026-09-01", "notes": [],
                "summary": "chart fixture",
                "blocks": [{"type": "svg_sparkline", "title": "S", "desc": "D",
                            "points": [["d1", 1], ["d2", 2]]}]}

    def raising(self, *_args, **_kwargs):
        raise RuntimeError(self.SENTINEL)

    def test_malformed_blocks_render_as_their_text_and_the_page_is_built(self):
        registry = [db.PANELS[0], ("malformed", "Malformed", self.malformed), db.PANELS[-1]]
        with mock.patch.object(db, "PANELS", registry):
            rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        section = _section(page, "malformed")
        self.assertNotIn("could not be rendered", page)
        self.assertIn("<th>7</th>", section)
        self.assertIn("<td>a bare row</td>", section)
        self.assertIn(f"<tr><td>{UNKNOWN_SPAN}</td></tr>", section)  # the None row
        self.assertIn("<li>one bare string note</li>", section)
        self.assertIn("<p>4</p>", section)
        self.assertIn("unrecognised fmt", section)
        self.assertIn("a block that is not a mapping was not rendered", section)
        self.assertEqual(section.count("<figure>"), 2)

    def test_a_panel_whose_rendering_raises_is_contained_and_noted_everywhere(self):
        registry = [db.PANELS[0], ("broken", "Broken <b>&", self.charts), db.PANELS[-1]]
        with mock.patch.object(db, "PANELS", registry), \
                mock.patch.object(db, "svg_sparkline", self.raising):
            rc, out, stdout, stderr = self.build("out", "--json")
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        receipt_text = (out / "build.json").read_text(encoding="utf-8")
        receipt = json.loads(receipt_text)
        self.assertEqual(re.findall(r'<section id="([^"]+)">', page),
                         ["namespaces", "broken", "bounds"])
        self.assertEqual(_section(page, "broken"),
                         f'\n<h2>Broken &lt;b&gt;&amp;</h2>\n<p class="notes">{self.NOTE}</p>\n')
        self.assertIn(f"<li>broken: {self.NOTE}</li>", _section(page, "bounds"))
        self.assertIn(f"broken: {self.NOTE}", receipt["notes"])
        self.assertEqual({entry["id"]: entry["summary"] for entry in receipt["panels"]}["broken"],
                         "could not be rendered (see notes)")
        self.assertIn("1 mapped · 1 unmapped · 30 residue.", _section(page, "namespaces"))
        for text in (page, receipt_text, stdout, stderr):
            self.assertNotIn("SENTINEL", text)
            self.assertNotIn("/never/on/the/page", text)

    def test_a_contained_failure_is_deterministic_and_leaves_the_model_untouched(self):
        registry = [db.PANELS[0], ("broken", "Broken", self.charts), db.PANELS[-1]]
        with mock.patch.object(db, "PANELS", registry), \
                mock.patch.object(db, "svg_sparkline", self.raising):
            model = db.build_model(self.world["data_home"], [str(self.world["checkout"])],
                                   _opts(self), None)
            before = json.dumps(model, sort_keys=True)
            page1 = db.render_page(model, _FAKE_HOME.name)
            page2 = db.render_page(model, _FAKE_HOME.name)
            page3, noted = db.render_build(model, _FAKE_HOME.name)
            page4, noted_again = db.render_build(noted, _FAKE_HOME.name)
        self.assertEqual(json.dumps(model, sort_keys=True), before)
        self.assertEqual(page1, page2)
        self.assertEqual(page1, page3)
        self.assertEqual(page3, page4)  # re-rendering the noted model adds nothing twice
        self.assertEqual(noted_again["notes"].count(f"broken: {self.NOTE}"), 1)
        self.assertNotIn(f"broken: {self.NOTE}", model["notes"])


class _AttemptsCase(_WorldCase):
    """Shared helpers for the attempts-panel tests (T4): the ledger and its history projection,
    rendered from `attempt_history.join_kits`/`summarize` and `attempt_ledger.AttemptLedger`
    only (PLAN D2, D3 row 1, D7a-c)."""

    def model(self, caps=None, checkouts=None):
        return db.build_model(self.world["data_home"],
                              checkouts if checkouts is not None
                              else [str(self.world["checkout"])],
                              _opts(self), caps)

    def panel(self, model):
        return next(p for p in model["panels"] if p["id"] == "attempts")

    def table(self, attempts, caption):
        return next(b for b in attempts["blocks"]
                    if b.get("type") == "table" and b.get("caption") == caption)

    def ledger_facts_table(self, attempts):
        return next(b for b in attempts["blocks"]
                    if b.get("type") == "table"
                    and b.get("headers", [])[:2] == ["namespace", "ledger"])


class ReadNamespacesTests(_AttemptsCase):
    """`read_namespaces` (P1 fix round S6): mapped first, then unmapped by name, bounded by
    MAX_NAMESPACES_READ -- the contract T6/T7 also build on."""

    def ctx(self, caps=None):
        caps = {**db.default_caps(), **(caps or {})}
        return {"model": self.model(caps), "caps": caps}

    def test_mapped_first_then_unmapped_by_name(self):
        rows, notes = db.read_namespaces(self.ctx())
        self.assertEqual(notes, [])
        self.assertEqual([row["mapped"] for row in rows], [True, False])
        self.assertEqual(rows[0]["namespace"], self.world["namespace"])
        self.assertEqual(rows[0]["checkout"], str(self.world["checkout"]))
        self.assertEqual(rows[1]["namespace"], db.UNMAPPED_NAMESPACE)
        self.assertNotIn("checkout", rows[1])

    def test_cap_lowered_to_one_keeps_the_mapped_row_first_and_notes_the_cut(self):
        rows, notes = db.read_namespaces(self.ctx({"MAX_NAMESPACES_READ": 1}))
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["mapped"])
        self.assertEqual(rows[0]["namespace"], self.world["namespace"])
        self.assertEqual(len(notes), 1)
        self.assertTrue(notes[0].startswith("cap MAX_NAMESPACES_READ (1) reached"))
        # P2 fix round polish: the cap bounds four panels' reads (attempts, telemetry, journal,
        # evals), so its note no longer claims it bounded ledger facts alone.
        self.assertIn("were read in depth", notes[0])
        self.assertNotIn("ledger facts", notes[0])

    def test_cap_not_hit_when_the_combined_list_fits(self):
        rows, notes = db.read_namespaces(self.ctx())
        self.assertEqual(len(rows), 2)
        self.assertEqual(notes, [])


class AttemptsHistoryTests(_AttemptsCase):
    """TASKS.md T4 items 1-2: the history projection per mapped checkout with a kits dir."""

    def test_records_and_by_source_line_is_the_owners_own_split(self):
        attempts = self.panel(self.model())
        line = next(b for b in attempts["blocks"]
                    if b.get("type") == "p" and b.get("parts")
                    and b["parts"][0] == "records: ")
        # 3 ledger records (T1 pass, T2 open, T3 estimated-cost) + 6 notes records (demo-kit
        # T1 pass, notes-kit T1 pass, notes-kit T2 blocked, scorecard-demo SC1/SC2/SC3 -- T5's
        # own kit; its `agent:` lines are not attempt_history's grammar and add no records) --
        # attempt_history's own split.
        self.assertEqual(line["parts"], [
            "records: ", {"fmt": "count", "value": 9}, "  by source: ",
            "ledger", ": ", {"fmt": "count", "value": 3}, "  ",
            "notes", ": ", {"fmt": "count", "value": 6}, "  "])

    def test_coverage_line_reports_kits_with_ledger_notes_and_role_use(self):
        attempts = self.panel(self.model())
        line = next(b for b in attempts["blocks"]
                    if b.get("type") == "p" and b.get("parts")
                    and b["parts"][0] == "coverage — kits: ")
        # T5 adds a third `.claude/kits` kit (scorecard-demo, with a NOTES.md) -- kits: 2 -> 3,
        # with_notes: 2 -> 3; it has no ledger of its own, so with_ledger is unchanged.
        self.assertEqual(line["parts"], [
            "coverage — kits: ", {"fmt": "count", "value": 3},
            "  with ledger: ", {"fmt": "count", "value": 1},
            "  with notes: ", {"fmt": "count", "value": 3},
            "  with role-use: ", {"fmt": "count", "value": 0}])

    def test_by_harness_tier_table_joins_results_as_text_pairs(self):
        attempts = self.panel(self.model())
        table = self.table(attempts, "records by harness and tier")
        rows = {(r[0], r[1]): (r[2]["value"], r[3]) for r in table["rows"]}
        # demo-kit's/notes-kit's/scorecard-demo's own outcome lines resolve model=sonnet to
        # claude/sonnet and model=haiku to claude/haiku; the ledger's own SYNTHETIC_MODEL is
        # unregistered, so harness and tier both stay unknown there.
        self.assertEqual(rows[("claude", "sonnet")],
                         (5, "blocked: 1, pass: 3, retry-pass: 1"))
        self.assertEqual(rows[("claude", "haiku")], (1, "pass: 1"))
        self.assertEqual(rows[("unknown", "unknown")], (3, "dispatched: 1, open: 1, pass: 1"))

    def test_bar_chart_of_records_by_harness_tier_has_a_table_twin_and_counts_only(self):
        model = self.model()
        attempts = self.panel(model)
        chart = next(b for b in attempts["blocks"] if b.get("type") == "svg_bars")
        self.assertEqual(chart["label_key"], "label")
        self.assertEqual(chart["value_key"], "value")
        self.assertEqual(sorted(row["label"] for row in chart["rows"]),
                         ["claude/haiku", "claude/sonnet", "unknown/unknown"])
        self.assertTrue(all(isinstance(row["value"], int) for row in chart["rows"]))
        page = db.render_page(model, _FAKE_HOME.name)
        section = _section(page, "attempts")
        self.assertEqual(section.count("<figure>"), 1)
        figure = section.split("<figure>", 1)[1].split("</figure>", 1)[0]
        self.assertIn("<table>", figure.split("<figcaption>", 1)[1])

    def test_unknown_table_has_every_key_including_the_four_provenance_refs(self):
        attempts = self.panel(self.model())
        table = self.table(attempts, "unknown, counted — never filled in")
        self.assertEqual(table["headers"], ["field", "unknown count"])
        values = {row[0]: row[1] for row in table["rows"]}
        self.assertEqual(list(values), ["harness", "tier", "observed_model", "cost", "duration",
                                        "acceptance_ref", "policy_ref", "decision_ref",
                                        "admission_ref"])
        for cell in values.values():
            self.assertEqual(cell["fmt"], "count")
            self.assertIsInstance(cell["value"], int)
        # cross-checked against the fixture by hand: 9 records (3 ledger + 6 notes, T5 added
        # scorecard-demo's SC1/SC2/SC3), of which only one ledger record (T3) carries a cost or
        # a duration, and notes-source records never count toward `observed_model` unknown.
        self.assertEqual({k: v["value"] for k, v in values.items()},
                         {"harness": 3, "tier": 3, "observed_model": 3, "cost": 8, "duration": 7,
                          "acceptance_ref": 9, "policy_ref": 9, "decision_ref": 9,
                          "admission_ref": 9})

    def test_failure_classes_table_is_empty_and_says_so(self):
        model = self.model()
        attempts = self.panel(model)
        table = self.table(attempts, "failure classes")
        self.assertEqual(table["rows"], [])
        page = db.render_page(model, _FAKE_HOME.name)
        self.assertIn("no failure classes recorded", _section(page, "attempts"))

    def test_every_cost_basis_has_a_row_and_a_costless_basis_is_unknown_not_zero(self):
        model = self.model()
        attempts = self.panel(model)
        table = self.table(attempts, "cost by basis")
        self.assertEqual([row[0] for row in table["rows"]], list(ah.COST_BASES))
        by_basis = {row[0]: row for row in table["rows"]}
        self.assertEqual(by_basis["estimated"][1], {"fmt": "count", "value": 1})
        self.assertEqual(by_basis["estimated"][2],
                         {"fmt": "usd", "value": 0.05, "basis": "estimated"})
        self.assertIsNone(by_basis["estimated"][3]["value"])  # no credits basis in this fixture
        for basis in ("billed", "credits", "proxy", "model-reported"):
            self.assertEqual(by_basis[basis][1], {"fmt": "count", "value": 0})
            self.assertIsNone(by_basis[basis][2]["value"])
            self.assertEqual(by_basis[basis][2]["basis"], basis)
        page = db.render_page(model, _FAKE_HOME.name)
        section = _section(page, "attempts")
        self.assertIn('$0.05 <span class="label">estimated</span>', section)
        self.assertIn('<span class="unknown">unknown</span>', section)
        for basis in ah.COST_BASES:
            self.assertIn(basis, section)

    def test_every_duration_basis_has_a_row(self):
        attempts = self.panel(self.model())
        table = self.table(attempts, "duration by basis")
        self.assertEqual([row[0] for row in table["rows"]], list(ah.DURATION_BASES))
        by_basis = {row[0]: row for row in table["rows"]}
        self.assertEqual(by_basis["process-wall"][1], {"fmt": "count", "value": 2})
        self.assertEqual(by_basis["process-wall"][2], {"fmt": "seconds", "value": 3.0})
        self.assertIsNone(by_basis["decision-latency"][2]["value"])

    def test_a_count_the_owner_did_not_emit_renders_unknown_never_zero(self):
        # P2 fix round S6 (PLAN R3): no `.get(..., 0)` default on an owner count. A basis, a tier
        # or a card that carries no count renders the styled `unknown`, never a fabricated 0 --
        # while the owner's OWN zero still renders as the zero it is.
        for row in db._cost_rows({}, ah.COST_BASES):
            self.assertEqual(row[1], {"fmt": "count", "value": None}, row[0])
        for row in db._duration_rows({}, ah.DURATION_BASES):
            self.assertEqual(row[1], {"fmt": "count", "value": None}, row[0])
        own_zero = db._cost_rows({"billed": {"n": 0, "usd": None, "credits": None}}, ("billed",))
        self.assertEqual(own_zero[0][1], {"fmt": "count", "value": 0})
        self.assertEqual(
            db._harness_tier_rows({"claude": {"tiers": {"sonnet": {"results": {"pass": 1}}}}}),
            [("claude", "sonnet", None, "pass: 1")])
        blocks = db._history_card_blocks({}, ah)
        records_line = next(b for b in blocks if b.get("type") == "p" and b.get("parts")
                            and b["parts"][0] == "records: ")
        self.assertEqual(records_line["parts"][1], {"fmt": "count", "value": None})
        rendered = "\n".join(db._render_block(block) for block in blocks)
        self.assertIn(f"records: {UNKNOWN_SPAN}", rendered)
        self.assertIn(f"<td>billed</td><td>{UNKNOWN_SPAN}</td>", rendered)
        self.assertNotIn("<td>billed</td><td>0</td>", rendered)

    def test_owner_never_summed_note_appears_beneath_both_tables(self):
        page = db.render_page(self.model(), _FAKE_HOME.name)
        section = _section(page, "attempts")
        self.assertEqual(section.count(ah.cost_totals([])["note"]), 2)

    def test_no_total_row_anywhere_in_the_attempts_section(self):
        page = db.render_page(self.model(), _FAKE_HOME.name)
        self.assertNotIn("total", _section(page, "attempts").lower())

    def test_no_sum_call_anywhere_in_dashboard_py(self):
        text = DASHBOARD_PATH.read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"^\s*[^#]*\bsum\(", text, re.MULTILINE), [])

    def test_latest_details_table_has_kit_task_result_run_columns(self):
        attempts = self.panel(self.model())
        table = self.table(attempts, "latest per task")
        self.assertTrue(table["details"])
        self.assertEqual(table["headers"], ["kit", "task", "result", "run"])
        rows = {(r[0], r[1]): (r[2], r[3]) for r in table["rows"]}
        self.assertEqual(rows[(db.DEMO_KIT, "T1")], ("pass", db.DEMO_RUN))
        self.assertEqual(rows[(db.NOTES_KIT, "T1")], ("pass", db.DEMO_RUN))
        self.assertEqual(rows[(db.NOTES_KIT, "T2")], ("blocked", db.DEMO_RUN))

    def test_lineage_chain_count_line(self):
        attempts = self.panel(self.model())
        line = next(b for b in attempts["blocks"]
                    if b.get("type") == "p" and b.get("parts")
                    and b["parts"][0] == "lineage chains: ")
        self.assertEqual(line["parts"], ["lineage chains: ", {"fmt": "count", "value": 0}])

    def test_card_notes_list_renders_even_when_empty(self):
        attempts = self.panel(self.model())
        notes_block = next(b for b in attempts["blocks"] if b.get("type") == "list")
        self.assertEqual(notes_block["items"], [])
        self.assertEqual(notes_block["empty"], "no notes from this history join")

    def test_codex_kits_root_is_a_second_history_target_with_its_own_label(self):
        tasks_kits = self.world["checkout"] / "tasks" / "kits"
        codex_ns = rd.project_namespace(tasks_kits)
        codex_kit_dir = tasks_kits / "codex-slug"
        codex_kit_dir.mkdir(parents=True)
        (codex_kit_dir / "TASKS.md").write_text("# TASKS\n")
        store = self.world["data_home"] / codex_ns / "attempts"
        ledger = al.AttemptLedger(store, "codex-slug")
        started = ledger.record_started("run-codex", "T1", "initial", "fake-cheap")
        ledger.record_finished("run-codex", "T1", started, "ok", 0, "ok")
        attempts = self.panel(self.model())
        labels = [b["text"] for b in attempts["blocks"]
                 if b.get("type") == "p" and str(b.get("text", "")).startswith("History for")]
        self.assertEqual(len(labels), 2)
        self.assertEqual(labels[0], f"History for {self.world['checkout']}:")
        self.assertEqual(labels[1], f"History for {self.world['checkout']} (tasks/kits):")

    def test_no_kits_dir_at_all_is_an_absence_sentence_not_an_error(self):
        import shutil
        shutil.rmtree(self.world["kits_dir"])
        attempts = self.panel(self.model())
        self.assertIn("no history projection to show",
                      " ".join(b.get("text", "") for b in attempts["blocks"]
                              if b.get("type") == "p"))

    def test_a_raising_join_kits_is_a_note_never_a_crash(self):
        real_ah = db._mod("attempt_history")

        def broken_join_kits(kits_dir, store=None, registry=None):
            raise RuntimeError("boom")

        with mock.patch.object(real_ah, "join_kits", broken_join_kits):
            model = self.model()
        attempts = self.panel(model)
        expected = f"attempt history unavailable for {self.world['checkout']}: RuntimeError"
        self.assertIn(expected, attempts["notes"])
        page = db.render_page(model, _FAKE_HOME.name)
        self.assertIn('<section id="attempts">', page)

    def test_a_symlinked_kit_dir_handed_to_join_kits_is_named_in_a_note(self):
        # P2 fix round S7: `attempt_history.join_kits` lists kit dirs with `Path.is_dir()`,
        # which follows a link, so the attempts panel names a symlinked kit dir exactly as the
        # scorecard panel already does for its own owner.
        outside = self.tmp / "outside-kit"
        outside.mkdir()
        (outside / "TASKS.md").write_text("# TASKS\n\n### OK1 — a task\n- status: done\n"
                                          "- model: sonnet\n")
        os.symlink(outside, self.world["kits_dir"] / "linked-kit", target_is_directory=True)
        # the scorecard panel is built too: an empty temp projects dir, per GUARDRAILS.
        model = db.build_model(self.world["data_home"], [str(self.world["checkout"])],
                               _opts(self), None)
        attempts = self.panel(model)
        expected = (f"{self.world['checkout']}: symlinked kit dir(s) linked-kit — "
                    f"attempt_history.join_kits follows these, unlike the kits-in-flight panel")
        self.assertIn(expected, attempts["notes"])
        scorecard = next(p for p in model["panels"] if p["id"] == "scorecard")
        self.assertTrue(any("linked-kit" in n and "routing_scorecard follows" in n
                            for n in scorecard["notes"]), scorecard["notes"])
        page = db.render_page(model, _FAKE_HOME.name)
        self.assertNotIn("total", _section(page, "attempts").lower())

    def test_oversize_kit_ledger_skips_that_historys_join_and_is_never_opened(self):
        events_path = (self.world["data_home"] / self.world["namespace"] / "attempts" /
                      db.DEMO_KIT / "events.jsonl")
        current = events_path.stat().st_size
        with open(events_path, "ab") as fh:
            fh.write(b"x" * (db.MAX_LEDGER_BYTES + 1 - current))
        self.assertEqual(events_path.stat().st_size, db.MAX_LEDGER_BYTES + 1)
        if os.geteuid() != 0:
            _chmod_restorable(self, events_path, 0)  # proves it is stat'd, never opened
        attempts = self.panel(self.model())
        marker = f"cap MAX_LEDGER_BYTES ({db.MAX_LEDGER_BYTES}) reached"
        history_note = next(n for n in attempts["notes"]
                            if n.startswith(marker) and "was not joined" in n)
        self.assertIn(db.DEMO_KIT, history_note)
        self.assertNotIn("<traceback", history_note)
        skip_text = " ".join(b.get("text", "") for b in attempts["blocks"]
                             if b.get("type") == "p")
        self.assertIn("not joined this build", skip_text)


class AttemptsLedgerFactsTests(_AttemptsCase):
    """TASKS.md T4 items 3-4: raw ledger facts per namespace read, and the residue line."""

    def test_open_attempts_is_one_for_the_demo_kit(self):
        attempts = self.panel(self.model())
        rows = self.ledger_facts_table(attempts)["rows"]
        row = next(r for r in rows if r[0] == self.world["namespace"] and r[1] == db.DEMO_KIT)
        self.assertEqual(row[5], {"fmt": "count", "value": 1})  # open attempts: T2 never finished
        self.assertEqual(row[2], {"fmt": "count", "value": 7})  # events
        self.assertEqual(row[3], {"fmt": "count", "value": 0})  # corrupt lines

    def test_the_corrupt_line_in_the_unmapped_ledger_is_counted(self):
        attempts = self.panel(self.model())
        rows = self.ledger_facts_table(attempts)["rows"]
        row = next(r for r in rows if r[0] == db.UNMAPPED_NAMESPACE)
        self.assertEqual(row[3], {"fmt": "count", "value": 1})
        # confirmed independently through the owner's own ledger, never a dashboard re-count.
        ledger = al.AttemptLedger(self.world["data_home"] / db.UNMAPPED_NAMESPACE / al.STORE,
                                  "other-kit")
        ledger.events()
        self.assertEqual(ledger.corrupt, 1)

    def test_claim_files_present_and_kind_histogram_are_rendered(self):
        attempts = self.panel(self.model())
        rows = self.ledger_facts_table(attempts)["rows"]
        row = next(r for r in rows if r[0] == self.world["namespace"] and r[1] == db.DEMO_KIT)
        self.assertEqual(row[4], "attempt.finished: 2, attempt.started: 3, "
                                 "task.projected: 1, verify.finished: 1")
        self.assertEqual(row[8], {"fmt": "count", "value": 0})
        self.assertEqual(row[6]["fmt"], "date")
        self.assertIsNotNone(row[6]["value"])
        self.assertEqual(row[7]["fmt"], "date")

    def _append_event(self, path, **fields):
        event = {"v": al.LEDGER_VERSION, "ts": "2026-09-25T00:00:00Z"}
        event.update(fields)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")

    def test_a_malformed_kind_in_the_mapped_or_unmapped_ledger_never_blanks_the_panel(self):
        """T4 retry R1: a dict- or list-typed `kind` must not raise (unhashable as a dict key)
        and must not take the whole panel down with it -- the other ledger's rows, and the
        history section's cost table, still render."""
        mapped_events = (self.world["data_home"] / self.world["namespace"] / "attempts" /
                         db.DEMO_KIT / "events.jsonl")
        self._append_event(mapped_events, kind={"n": 1})
        unmapped_events = (self.world["data_home"] / db.UNMAPPED_NAMESPACE / "attempts" /
                           "other-kit" / "events.jsonl")
        self._append_event(unmapped_events, kind=["a", "b"])
        model = self.model()
        attempts = self.panel(model)
        rows = {r[1]: r for r in self.ledger_facts_table(attempts)["rows"]}
        self.assertIn(f"{db.OTHER_KIND_LABEL}: 1", rows[db.DEMO_KIT][4])
        self.assertIn(f"{db.OTHER_KIND_LABEL}: 1", rows["other-kit"][4])
        # the rest of the panel is untouched: the cost table (history section) still renders.
        self.table(attempts, "cost by basis")
        page = db.render_page(model, _FAKE_HOME.name)
        section = _section(page, "attempts")
        self.assertIn(db.OTHER_KIND_LABEL, section)
        self.assertIn("cost by basis", section)

    def test_a_long_or_markup_kind_is_counted_under_the_other_kinds_label_and_never_rendered(self):
        """T4 retry R2: a kind outside the shape/length `attempt_ledger.py` itself ever writes
        is counted under `OTHER_KIND_LABEL` and never reaches the page as its own text."""
        long_kind = "x" * 20000
        markup_kind = "<script>alert(1)</script>"
        events_path = (self.world["data_home"] / self.world["namespace"] / "attempts" /
                      db.DEMO_KIT / "events.jsonl")
        self._append_event(events_path, kind=long_kind)
        self._append_event(events_path, kind=markup_kind)
        model = self.model()
        attempts = self.panel(model)
        rows = {r[1]: r for r in self.ledger_facts_table(attempts)["rows"]}
        self.assertIn(f"{db.OTHER_KIND_LABEL}: 2", rows[db.DEMO_KIT][4])
        page = db.render_page(model, _FAKE_HOME.name)
        self.assertNotIn(long_kind, page)
        self.assertNotIn(markup_kind, page)
        self.assertNotIn("<script>alert", page)

    def test_residue_namespaces_contribute_nothing_to_records_or_ledger_facts(self):
        model = self.model()
        attempts = self.panel(model)
        namespaces_seen = {row[0] for row in self.ledger_facts_table(attempts)["rows"]}
        self.assertEqual(namespaces_seen, {self.world["namespace"], db.UNMAPPED_NAMESPACE})
        page = db.render_page(model, _FAKE_HOME.name)
        section = _section(page, "attempts")
        for residue_name in self.world["residue"]:
            self.assertNotIn(residue_name, section)

    def test_residue_line_reads_class_count_and_matches_the_brief_wording(self):
        classes = self.model()["classes"]
        page = db.render_page(self.model(), _FAKE_HOME.name)
        section = _section(page, "attempts")
        expected = db._count_cell(db.class_count(classes, "residue"))
        self.assertEqual(expected, {"fmt": "count", "value": 30, "qualifier": "exact"})
        self.assertIn(
            "30 residue namespaces (heuristic: tempfile-shaped name holding only an attempts "
            "store) — counted, not opened, excluded from every figure above", section)

    def test_max_namespaces_read_cap_lowered_to_one_is_noted_on_page_and_receipt(self):
        model = self.model(caps={"MAX_NAMESPACES_READ": 1})
        attempts = self.panel(model)
        marker = "cap MAX_NAMESPACES_READ (1) reached"
        self.assertTrue(any(n.startswith(marker) for n in attempts["notes"]), attempts["notes"])
        rows = self.ledger_facts_table(attempts)["rows"]
        self.assertEqual({row[0] for row in rows}, {self.world["namespace"]})
        page = db.render_page(model, _FAKE_HOME.name)
        self.assertIn(marker, page)
        receipt = db.build_receipt(model, _FAKE_HOME.name, self.tmp / "out")
        self.assertIn("MAX_NAMESPACES_READ", receipt["caps_hit"])
        self.assertTrue(any(marker in n for n in receipt["notes"]), receipt["notes"])

    def test_oversize_ledger_row_is_skipped_never_read_and_others_still_show(self):
        events_path = (self.world["data_home"] / db.UNMAPPED_NAMESPACE / "attempts" /
                      "other-kit" / "events.jsonl")
        current = events_path.stat().st_size
        with open(events_path, "ab") as fh:
            fh.write(b"x" * (db.MAX_LEDGER_BYTES + 1 - current))
        if os.geteuid() != 0:
            _chmod_restorable(self, events_path, 0)  # proves it is stat'd, never opened
        attempts = self.panel(self.model())
        marker = f"cap MAX_LEDGER_BYTES ({db.MAX_LEDGER_BYTES}) reached"
        note = next(n for n in attempts["notes"]
                   if n.startswith(marker) and "never read" in n)
        self.assertIn(f"{db.UNMAPPED_NAMESPACE}/other-kit", note)
        rows = self.ledger_facts_table(attempts)["rows"]
        self.assertNotIn(db.UNMAPPED_NAMESPACE, [r[0] for r in rows])
        self.assertIn(self.world["namespace"], [r[0] for r in rows])  # unaffected

    def test_no_data_home_is_an_absence_sentence_for_both_sub_sections(self):
        model = db.build_model(None, [str(self.world["checkout"])], _opts(self), None)
        attempts = self.panel(model)
        texts = [b.get("text") for b in attempts["blocks"] if b.get("type") == "p"]
        self.assertIn("No data home was given, so no checkout's history could be joined.",
                      texts)
        self.assertIn("No data home was given, so no ledger could be read directly.", texts)

    def test_full_build_probe_matches_the_task_verify_block(self):
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        for basis in ah.COST_BASES:
            self.assertIn(basis, page)
        self.assertIn("bases are separate facts and are never summed together", page)
        self.assertIn("unknown", page)
        self.assertIn("residue namespaces", page)
        section = _section(page, "attempts")
        self.assertNotIn("total", section.lower())


class AttemptsPanelSectionGuardTests(_AttemptsCase):
    """T4 retry R1c: the history section, the ledger-facts section and the residue line are
    each built in their own guard inside `build_attempts_panel` -- a failure in one is a note
    naming that section, and the other two still render their real content."""

    def test_a_raising_section_is_a_note_naming_the_section_the_others_still_render(self):
        sentinel = "SENTINEL-DO-NOT-LEAK-92f1"

        def broken(*_a, **_k):
            raise RuntimeError(sentinel)

        for target in ("_ledger_facts_blocks", "_residue_line_block"):
            with self.subTest(target=target):
                with mock.patch.object(db, target, broken):
                    model = self.model()
                attempts = self.panel(model)
                self.assertTrue(any(sentinel not in n and "RuntimeError" in n
                                    for n in attempts["notes"]), attempts["notes"])
                self.assertFalse(any(sentinel in n for n in attempts["notes"]))
                page = db.render_page(model, _FAKE_HOME.name)
                self.assertNotIn(sentinel, page)
                self.assertIn("cost by basis", _section(page, "attempts"))

    def test_a_raising_history_section_leaves_ledger_facts_and_residue_intact(self):
        sentinel = "SENTINEL-HISTORY-7a3c"

        def broken(*_a, **_k):
            raise RuntimeError(sentinel)

        with mock.patch.object(db, "_history_section_blocks", broken):
            model = self.model()
        attempts = self.panel(model)
        self.assertTrue(any("history section" in n and "RuntimeError" in n
                            for n in attempts["notes"]), attempts["notes"])
        page = db.render_page(model, _FAKE_HOME.name)
        self.assertNotIn(sentinel, page)
        section = _section(page, "attempts")
        self.assertIn("Ledger facts, read directly", section)
        self.assertIn("residue namespaces", section)


class _ScorecardCase(_WorldCase):
    """Shared helpers for the routing-scorecard and kits-in-flight panel tests (T5): every
    figure comes from `routing_scorecard.assemble_history_card`/`scan_kits`/`build_roles_card`
    or `kit_contract.parse_tasks`/`validate_graph`/`graph_state` (PLAN D2, D3 rows 2 and 6)."""

    def model(self, caps=None, checkouts=None, opts_extra=None):
        # GUARDRAILS: every build a test runs passes an empty temp `--projects-dir`, never the
        # real default -- `self.projects` (from `_WorldCase.setUp`) is that empty temp dir.
        opts = {"notes": [], "projects_dir": str(self.projects), "no_transcripts": False,
               "git": False}
        opts.update(opts_extra or {})
        return db.build_model(self.world["data_home"],
                              checkouts if checkouts is not None
                              else [str(self.world["checkout"])],
                              opts, caps)

    def panel(self, model, pid):
        return next(p for p in model["panels"] if p["id"] == pid)

    def table(self, panel, caption):
        return next(b for b in panel["blocks"]
                    if b.get("type") == "table" and b.get("caption") == caption)


class ScorecardTokensTests(_ScorecardCase):
    """TASKS.md T5 item 1: the kits-dir tokens."""

    def test_tokens_contain_both_labels_matching_label_re(self):
        entries = db._scorecard_kits_dirs([str(self.world["checkout"])])
        base = Path(self.world["checkout"]).name
        self.assertEqual([e["label"] for e in entries], [base, f"{base}-codex"])
        for entry in entries:
            self.assertRegex(entry["label"], rs._LABEL_RE)
            self.assertTrue(Path(entry["path"]).is_dir())

    def test_a_checkout_with_no_kits_dir_contributes_nothing_and_is_never_passed(self):
        empty_checkout = self.tmp / "no-kits-here"
        empty_checkout.mkdir()
        self.assertEqual(db._scorecard_kits_dirs([str(empty_checkout)]), [])
        model = self.model(checkouts=[str(empty_checkout)])
        scorecard = self.panel(model, "scorecard")
        kits_panel = self.panel(model, "kits")
        self.assertEqual(scorecard["summary"], db._NO_KITS_DIRS_TEXT)
        self.assertEqual(scorecard["blocks"], [{"type": "p", "text": db._NO_KITS_DIRS_TEXT}])
        self.assertEqual(kits_panel["summary"], db._NO_KITS_DIRS_TEXT)
        # never reaching the owner at all: no ValueError note, because assemble_history_card
        # was never called with a nonexistent path.
        self.assertEqual(scorecard["notes"], [])

    def test_scorecard_labels_and_coverage_come_from_the_fixture_not_the_real_repo(self):
        # T5 retry V2 (verifier findings 1, 2): built from INSIDE the synthetic checkout, so
        # --no-git's primary checkout is the fixture itself, never this real repo -- the
        # `-codex` label must come from the fixture alone, not the real repo's own tracked
        # `.claude/kits`/`tasks/kits`, and the checkouts list must hold only the fixture.
        original_cwd = os.getcwd()
        os.chdir(self.world["checkout"])
        try:
            out = self.tmp / "v2-out"
            rc, _stdout, stderr = _run(
                ["build", "--data-home", str(self.world["data_home"]), "--out-dir", str(out),
                 "--projects-dir", str(self.projects), "--no-git"])
        finally:
            os.chdir(original_cwd)
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        section = _section(page, "scorecard")
        base = Path(self.world["checkout"]).name
        self.assertIn(f"{base}-codex", section)
        receipt = self.receipt(out)
        self.assertEqual(receipt["checkouts"],
                         [os.path.realpath(str(self.world["checkout"]))])

        # The dollars block's own "coverage" label: this fixture never carries a `session:`
        # line anywhere, so `dollars` stays the owner's quality-only `None` in a live build --
        # proving "coverage" live would mean faking a transcript file AND letting
        # session_cost.py's subagent-discovery glob touch real `/tmp`/`/private/tmp`
        # (`_TMP_BASES`), which this kit's own real-filesystem test discipline rules out.
        # Proven instead through the full `build_model`/render path (not a direct
        # `_dollars_blocks` call, which `test_dollars_carry_the_full_coverage_and_
        # counterfactual_label_on_every_figure` already covers) by patching the owner call to
        # return a hand-built priced card, so the label is confirmed to reach the actual
        # rendered scorecard section.
        priced_card = {
            "tiers": {}, "kits": [], "roles": {}, "reroutes": {}, "notes": [],
            "dollars": {
                "actual_usd": 1.23, "counterfactual_usd": 4.56, "delta_usd": 3.33,
                "ratio": 3.71,
                "counterfactual_model": {"key": "frontier-x", "display": "Frontier X"},
                "coverage": "partial", "kits_with_sessions": 1, "kits_total": 2,
                "sessions_priced": 1, "sessions_found": 2, "pricing_cached": "2026-09-25"},
        }
        real_rs = db._mod("routing_scorecard")
        with mock.patch.object(real_rs, "assemble_history_card",
                               lambda *a, **k: priced_card):
            model = self.model()
        page2 = db.render_page(model, _FAKE_HOME.name)
        self.assertIn("coverage", _section(page2, "scorecard"))


class ScorecardHistoryCardTests(_ScorecardCase):
    """TASKS.md T5 item 2: the history card's tiers/kits/dollars/roles/reroutes blocks."""

    def test_dollars_block_carries_the_owners_quality_only_wording(self):
        ts = _load("telemetry_snapshot")
        page = db.render_page(self.model(), _FAKE_HOME.name)
        section = _section(page, "scorecard")
        self.assertIn(ts._DOLLARS_QUALITY_ONLY_NOTE, section)

    def test_no_transcripts_adds_the_skip_note_and_uses_a_temp_dir(self):
        model = self.model(opts_extra={"no_transcripts": True})
        scorecard = self.panel(model, "scorecard")
        self.assertTrue(any(n.startswith("transcript pricing skipped (--no-transcripts)")
                            for n in scorecard["notes"]), scorecard["notes"])

    def test_rates_see_note_appears_iff_no_tier_carries_a_rate_key(self):
        # The real card: every tier carries first_try_rate/escalation_rate -- no note.
        page = db.render_page(self.model(), _FAKE_HOME.name)
        self.assertNotIn("rates: see", _section(page, "scorecard"))
        # A synthetic count-only card (a future owner shape, TASKS.md item 2's own scenario):
        # the note appears, and the dashboard never computes the missing rate itself.
        counts_only_card = {"tiers": {"sonnet": {"pinned": 3, "first_try": 2}}}
        blocks = db._tiers_table_and_chart(counts_only_card, rs)
        self.assertTrue(any(b.get("type") == "p"
                            and str(b.get("text", "")).startswith("rates: see")
                            for b in blocks), blocks)

    def test_tiers_table_renders_owner_rates_verbatim_not_through_fmt_count(self):
        model = self.model()
        scorecard = self.panel(model, "scorecard")
        table = self.table(scorecard, "tiers")
        rows = {row[0]: row for row in table["rows"]}
        fields = table["headers"][1:]
        sonnet = dict(zip(fields, rows["sonnet"][1:]))
        # 6 with_outcome, 4 first-try -> 0.6666666666666666, the owner's own unrounded float,
        # never reshaped by fmt_count (which would print a whole-number rate as a bare int).
        self.assertEqual(sonnet["first_try_rate"], 4 / 6)
        haiku = dict(zip(fields, rows["haiku"][1:]))
        self.assertEqual(haiku["first_try_rate"], 1.0)
        # opus has no outcomes at all: with_outcome is a real, verified zero (a typed count
        # cell), but its rate is genuinely unmeasured -- a plain `None`, never a fabricated 0.
        opus = dict(zip(fields, rows["opus"][1:]))
        self.assertEqual(opus["with_outcome"], {"fmt": "count", "value": 0})
        self.assertIsNone(opus["first_try_rate"])

    def test_history_kits_table_is_namespaced_and_cost_is_unknown_without_sessions(self):
        model = self.model()
        scorecard = self.panel(model, "scorecard")
        table = self.table(scorecard, "kits")
        kit_names = [row[0] for row in table["rows"]]
        base = Path(self.world["checkout"]).name
        self.assertIn(f"{base}/{db.SCORECARD_KIT}", kit_names)
        self.assertIn(f"{base}-codex/{db.CODEX_DEMO_KIT}", kit_names)
        for row in table["rows"]:
            self.assertEqual(row[-1], {"fmt": "usd", "value": None,
                                       "basis": "actual, priced sessions"})

    def test_dollars_carry_the_full_coverage_and_counterfactual_label_on_every_figure(self):
        # A hand-built priced card (TASKS.md item 2's exact dollars shape) -- a direct unit
        # test of the label text, since none of this kit's fixtures carry a `session:` line
        # (dollars stays None there; the quality-only path is covered above).
        priced_card = {"dollars": {
            "actual_usd": 1.23, "counterfactual_usd": 4.56, "delta_usd": 3.33, "ratio": 3.71,
            "counterfactual_model": {"key": "frontier-x", "display": "Frontier X"},
            "coverage": "partial", "kits_with_sessions": 1, "kits_total": 2,
            "sessions_priced": 1, "sessions_found": 2, "pricing_cached": "2026-09-25",
        }, "notes": []}
        blocks = db._dollars_blocks(priced_card)
        parts = blocks[0]["parts"]
        label = ("actual vs all-Frontier X counterfactual over priced sessions only — "
                 "coverage partial")
        dollar_cells = [p for p in parts if isinstance(p, dict) and p.get("fmt") == "usd"]
        self.assertEqual(len(dollar_cells), 3)
        for cell in dollar_cells:
            self.assertEqual(cell["basis"], label)
        self.assertEqual([c["value"] for c in dollar_cells], [1.23, 4.56, 3.33])

    def test_verifier_and_reviewer_by_tier_tables_render_owner_values_verbatim(self):
        # T5 retry V1: the per-tier evidence PLAN D14 cites, not left off as a "scope choice".
        model = self.model()
        scorecard = self.panel(model, "scorecard")
        for role_name in ("verifier", "reviewer"):
            table = self.table(scorecard, f"role: {role_name} by tier")
            self.assertEqual(table["headers"],
                             ["tier", "events", "with_precision", "findings", "confirmed",
                              "precision"])
            rows = {row[0]: row for row in table["rows"]}
            self.assertEqual(set(rows), set(rs.LIVE_TIER_ORDER))
            # scorecard-demo's two `agent: … role=verifier …` lines are both on model=sonnet.
            if role_name == "verifier":
                sonnet = dict(zip(table["headers"][1:], rows["sonnet"][1:]))
                self.assertEqual(sonnet["events"], {"fmt": "count", "value": 2})
            # a tier with no events for this role: a real, verified zero for `events`, but a
            # genuinely unmeasured `precision` -- plain `None`, never a fabricated 0.
            haiku = dict(zip(table["headers"][1:], rows["haiku"][1:]))
            self.assertEqual(haiku["events"], {"fmt": "count", "value": 0})
            self.assertIsNone(haiku["precision"])
        page = db.render_page(model, _FAKE_HOME.name)
        section = _section(page, "scorecard")
        self.assertIn("role: verifier by tier", section)
        self.assertIn("role: reviewer by tier", section)
        self.assertIn('<span class="unknown">unknown</span>', section)


class ScorecardRolesValueTests(_ScorecardCase):
    """TASKS.md T5 item 3: the per-role value card, the `run_roles` bare shape."""

    def test_aggregate_table_has_the_owners_below_floor_wording(self):
        model = self.model()
        scorecard = self.panel(model, "scorecard")
        table = self.table(scorecard, "aggregate role value")
        self.assertTrue(any("insufficient sample" in row[0] for row in table["rows"]),
                        table["rows"])

    def test_per_kit_roster_is_a_details_table(self):
        model = self.model()
        scorecard = self.panel(model, "scorecard")
        # one "per-kit roster" table per kits dir (checkout, checkout-codex).
        tables = [b for b in scorecard["blocks"]
                 if b.get("type") == "table" and b.get("caption") == "per-kit roster"]
        self.assertEqual(len(tables), 2, tables)
        for table in tables:
            self.assertTrue(table["details"])
            self.assertEqual(table["headers"], ["kit", "roster label", "roster size"])
        all_kits = [row[0] for table in tables for row in table["rows"]]
        self.assertIn(db.SCORECARD_KIT, all_kits)
        self.assertIn(db.CODEX_DEMO_KIT, all_kits)


class KitsInFlightTests(_ScorecardCase):
    """TASKS.md T5 item 4: kits in flight, through `kit_contract` only."""

    def test_demo_kits_show_with_correct_counts_and_graph_state(self):
        model = self.model()
        kits_panel = self.panel(model, "kits")
        table = kits_panel["blocks"][0]
        self.assertEqual(table["headers"],
                         ["checkout label", "kit", "pending", "in-progress", "done",
                          "blocked", "graph state"])
        rows = {(r[0], r[1]): r for r in table["rows"]}
        base = Path(self.world["checkout"]).name

        def counts(row):
            return [c["value"] for c in row[2:6]]

        self.assertEqual(counts(rows[(base, db.DEMO_KIT)]), [0, 1, 1, 0])
        self.assertEqual(rows[(base, db.DEMO_KIT)][6], "interrupted")
        self.assertEqual(counts(rows[(base, db.NOTES_KIT)]), [0, 0, 1, 1])
        self.assertEqual(rows[(base, db.NOTES_KIT)][6], "waiting")
        self.assertEqual(counts(rows[(base, db.SCORECARD_KIT)]), [0, 0, 3, 0])
        self.assertEqual(rows[(base, db.SCORECARD_KIT)][6], "complete")
        codex_label = f"{base}-codex"
        self.assertEqual(counts(rows[(codex_label, db.CODEX_DEMO_KIT)]), [0, 0, 1, 0])
        self.assertEqual(rows[(codex_label, db.CODEX_DEMO_KIT)][6], "complete")

    def test_max_kits_per_dir_cap_lowered_is_noted(self):
        model = self.model(caps={"MAX_KITS_PER_DIR": 1})
        kits_panel = self.panel(model, "kits")
        self.assertTrue(any(n.startswith("cap MAX_KITS_PER_DIR (1) reached")
                            for n in kits_panel["notes"]), kits_panel["notes"])

    def test_a_kit_with_an_invalid_status_is_a_note_not_a_crash(self):
        bad_kit = self.world["kits_dir"] / "bad-status-kit"
        bad_kit.mkdir()
        (bad_kit / "TASKS.md").write_text(
            "# TASKS — bad-status-kit\n\n### BX1 — a task with no status\n- model: sonnet\n")
        model = self.model()
        kits_panel = self.panel(model, "kits")
        self.assertTrue(any("bad-status-kit" in n and "ValueError" in n
                            for n in kits_panel["notes"]), kits_panel["notes"])
        table = kits_panel["blocks"][0]
        self.assertNotIn("bad-status-kit", [row[1] for row in table["rows"]])
        # every other kit still renders.
        self.assertIn(db.SCORECARD_KIT, [row[1] for row in table["rows"]])

    def test_two_checkouts_colliding_on_a_label_are_renamed_and_noted(self):
        # T5 retry R2: the kits panel must use the SAME owner resolution
        # (routing_scorecard.resolve_kits_dirs) the scorecard panel already relies on via
        # assemble_history_card, not its own unresolved `_scorecard_kits_dirs` list. The
        # fixture checkout's OWN basename is "checkout", so its `tasks/kits` label is already
        # "checkout-codex" (it holds `codex-demo`) -- a second checkout literally named
        # "checkout-codex" collides with that label on its `.claude/kits`.
        checkout_b = self.tmp / "checkout-codex"
        kit_b = checkout_b / ".claude" / "kits" / "some-kit"
        kit_b.mkdir(parents=True)
        (kit_b / "TASKS.md").write_text(
            "# TASKS\n\n### CB1 — a task\n- status: done\n- model: sonnet\n")
        model = self.model(checkouts=[str(self.world["checkout"]), str(checkout_b)])
        kits_panel = self.panel(model, "kits")
        labels = {row[0] for row in kits_panel["blocks"][0]["rows"]}
        self.assertIn("checkout-codex", labels)
        self.assertIn("checkout-codex-2", labels)
        self.assertTrue(any("duplicate kits-dir label" in n and "checkout-codex" in n
                            for n in kits_panel["notes"]), kits_panel["notes"])
        self.assertIn("some-kit", [row[1] for row in kits_panel["blocks"][0]["rows"]])

    def test_a_symlinked_kit_dir_is_skipped_and_noted_never_read(self):
        # T5 retry R3: the kits panel never follows a symlinked kit dir (the namespace
        # classifier's own os.lstat/is_symlink convention); the scorecard's owner DOES follow
        # it, so the scorecard panel notes that difference by name.
        outside = self.tmp / "escape-hatch-target"
        outside.mkdir()
        sentinel = "SENTINEL-ESCAPE-HATCH-TITLE-9f3c"
        (outside / "TASKS.md").write_text(
            f"# TASKS\n\n### ES1 — {sentinel}\n- status: done\n- model: sonnet\n")
        os.symlink(outside, self.world["kits_dir"] / "escape-hatch")
        model = self.model()
        kits_panel = self.panel(model, "kits")
        self.assertNotIn("escape-hatch",
                         [row[1] for row in kits_panel["blocks"][0]["rows"]])
        self.assertTrue(any("escape-hatch" in n and "symlinked" in n
                            for n in kits_panel["notes"]), kits_panel["notes"])
        page = db.render_page(model, _FAKE_HOME.name)
        self.assertNotIn(sentinel, page)
        scorecard = self.panel(model, "scorecard")
        self.assertTrue(any("escape-hatch" in n and "routing_scorecard follows" in n
                            for n in scorecard["notes"]), scorecard["notes"])

    def test_a_symlinked_tasks_md_leaf_is_refused_with_a_note_never_read(self):
        # P2 fix round S7: a REAL kit dir whose TASKS.md is a link out of the checkout. The
        # kits panel checks the leaf with `os.lstat`, so it refuses the link instead of following
        # it; `read_text` is never reached for it.
        outside = self.tmp / "outside-tasks.md"
        sentinel = "SENTINEL-LINKED-TASKS-LEAF-4d2e"
        outside.write_text(f"# TASKS\n\n### LK1 — {sentinel}\n- status: done\n- model: sonnet\n")
        linked_kit = self.world["kits_dir"] / "linked-leaf-kit"
        linked_kit.mkdir()
        (linked_kit / "TASKS.md").symlink_to(outside)
        real_read_text = Path.read_text
        read = []

        def spying_read_text(path, *args, **kwargs):
            read.append(os.fspath(path))
            return real_read_text(path, *args, **kwargs)

        # The kits panel's builder alone: the scorecard and history owners read TASKS.md files
        # themselves (their own behaviour, named in their own panels' notes), not this panel.
        ctx = {"checkouts": [str(self.world["checkout"])], "caps": db.default_caps()}
        with mock.patch.object(Path, "read_text", spying_read_text):
            kits_panel = db.build_kits_panel(ctx)
        self.assertTrue(read)  # the spy saw the healthy kits' TASKS.md reads
        self.assertTrue(any("linked-leaf-kit" in n and "TASKS.md is a symlink" in n
                            and "never read" in n for n in kits_panel["notes"]),
                        kits_panel["notes"])
        self.assertNotIn("linked-leaf-kit", [row[1] for row in kits_panel["blocks"][0]["rows"]])
        self.assertNotIn(os.fspath(linked_kit / "TASKS.md"), read)
        self.assertIn(db.SCORECARD_KIT, [row[1] for row in kits_panel["blocks"][0]["rows"]])

    def test_oversized_tasks_md_is_skipped_via_stat_alone_and_never_opened(self):
        # T5 retry R4: os.stat gates the read; chmod 0 proves the file is never opened for
        # content (only stat, which needs no read permission on the file itself).
        big_kit_dir = self.world["kits_dir"] / "big-tasks-kit"
        big_kit_dir.mkdir()
        tasks_md = big_kit_dir / "TASKS.md"
        head = "# TASKS\n\n### BG1 — a task\n- status: done\n- model: sonnet\n".encode("utf-8")
        tasks_md.write_bytes(head + b"x" * (db.MAX_TASKS_MD_BYTES + 1 - len(head)))
        self.assertEqual(tasks_md.stat().st_size, db.MAX_TASKS_MD_BYTES + 1)
        if os.geteuid() != 0:
            _chmod_restorable(self, tasks_md, 0)
        model = self.model()
        kits_panel = self.panel(model, "kits")
        marker = f"cap MAX_TASKS_MD_BYTES ({db.MAX_TASKS_MD_BYTES}) reached"
        self.assertTrue(any(n.startswith(marker) and "big-tasks-kit" in n
                            for n in kits_panel["notes"]), kits_panel["notes"])
        self.assertFalse(any("could not be read" in n or "could not be stat" in n
                             for n in kits_panel["notes"]), kits_panel["notes"])
        self.assertNotIn("big-tasks-kit",
                         [row[1] for row in kits_panel["blocks"][0]["rows"]])


class EscControlCharacterTests(_ScorecardCase):
    """T5 retry R1: `esc` neutralises bidi-override and other control characters."""

    def test_bidi_override_in_a_kit_name_is_neutralised_everywhere_on_the_page(self):
        bidi_dir = self.world["kits_dir"] / "demo‮<done>-kit"
        bidi_dir.mkdir()
        (bidi_dir / "TASKS.md").write_text(
            "# TASKS\n\n### BX1 — a task\n- status: done\n- model: sonnet\n")
        page = db.render_page(self.model(), _FAKE_HOME.name)
        self.assertNotIn("‮", page)
        self.assertIn("⟨U+202E⟩", page)

    def test_an_arabic_letter_in_a_kit_name_renders_as_is(self):
        arabic_dir = self.world["kits_dir"] / "عربي-kit"
        arabic_dir.mkdir()
        (arabic_dir / "TASKS.md").write_text(
            "# TASKS\n\n### AR1 — a task\n- status: done\n- model: sonnet\n")
        page = db.render_page(self.model(), _FAKE_HOME.name)
        self.assertIn("عربي-kit", page)


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
        # P3 fix round M1: the demo maps its synthetic plugin install beside the checkout -- an
        # intended paired edit (this read "1 mapped" before the plugin install was mapped).
        self.assertIn("2 mapped · 1 unmapped · 30 residue", stdout)
        page_line = [line for line in stdout.splitlines() if line.startswith("page (removed")]
        self.assertEqual(len(page_line), 1, stdout)
        page_path = page_line[0].split(": ", 1)[1]
        self.assertTrue(page_path.startswith(str(scratch)), page_path)
        self.assertFalse(os.path.exists(page_path))

    def test_the_demo_page_shows_a_plugin_install_and_never_names_the_real_one(self):
        # P3 fix round M1: `demo` hands the build a synthetic plugin root, so its page shows the
        # plugin install class without ever naming the real PLUGIN_ROOT or its namespace. The
        # page is removed when the demo exits, so the writer is wrapped to see what it wrote.
        written = {}
        real_write = db.write_page

        def capture(out_dir, page_text, receipt):
            written["page"], written["receipt"] = page_text, json.dumps(receipt)
            return real_write(out_dir, page_text, receipt)

        with mock.patch.object(db, "write_page", capture):
            rc, _stdout, stderr = _run(["demo"])
        self.assertEqual(rc, 0, stderr)
        page = written["page"]
        self.assertIn(f"({db.PLUGIN_INSTALL_LABEL}):", _section(page, "telemetry"))
        self.assertIn(db.DEMO_PLUGIN_LABEL, _section(page, "telemetry"))
        for real in {str(db.PLUGIN_ROOT), os.path.realpath(db.PLUGIN_ROOT),
                     rd.project_namespace(db.PLUGIN_ROOT)}:
            self.assertNotIn(real, page)
            self.assertNotIn(real, written["receipt"])

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

    def test_the_summary_scopes_the_heuristic_to_the_residue_count_alone(self):
        # P3 fix round: "(heuristic: counted, never opened)" followed all three counts and read
        # as covering the mapped and unmapped ones too. It now names residue itself, right after
        # the residue count, and nothing qualifies the exact mapped and unmapped counts.
        world = db.synthetic_world(self.tmp / "world")
        projects = self.tmp / "projects"
        projects.mkdir()
        os.chdir(world["checkout"])
        rc, stdout, stderr = _run(["build", "--data-home", str(world["data_home"]),
                                   "--out-dir", str(self.tmp / "out"), "--projects-dir",
                                   str(projects), "--no-git"])
        self.assertEqual(rc, 0, stderr)
        line = next(line for line in stdout.splitlines() if line.startswith("namespaces:"))
        self.assertEqual(line, "namespaces: 1 mapped · 1 unmapped · 30 residue"
                               + db.RESIDUE_SUMMARY_QUALIFIER)
        self.assertIn("residue only", db.RESIDUE_SUMMARY_QUALIFIER)
        self.assertEqual(stdout.count("heuristic"), 1)


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
        # Split tokens, so this file never holds a banned word itself. `web`+`browser` is the
        # "open in browser" fence (PLAN OUT OF SCOPE); the rest spawn a process or reach a
        # network (P1 fix round F8).
        for token in ("Path" + ".home", "sub" + "process", "url" + "open", "http" + ".client",
                      "web" + "browser", "os" + ".system", "os" + ".popen", "sock" + "et",
                      "url" + "lib"):
            self.assertNotIn(token, text)

    def test_pinned_constants(self):
        self.assertEqual(db.BUILD_SCHEMA_VERSION, 1)
        self.assertEqual((db.PAGE_NAME, db.RECEIPT_NAME, db.CONFIG_NAME),
                         ("index.html", "build.json", "config.json"))
        self.assertEqual(db.CSP, "default-src 'none'; style-src 'unsafe-inline'; img-src data:")
        self.assertEqual(db.RESIDUE_NAMESPACE_RE.pattern, r"^tmp[a-z0-9_]{8}-[0-9a-f]{8}$")
        self.assertEqual(
            (db.MAX_NAMESPACES_LISTED, db.MAX_NAMESPACES_READ, db.MAX_LEDGER_BYTES,
             db.MAX_KITS_PER_DIR, db.MAX_TASKS_MD_BYTES, db.MAX_EVAL_RUNS_RENDERED,
             db.MAX_JOURNAL_DAYS, db.MAX_TELEMETRY_ENVELOPES_PER_SOURCE, db.MAX_DIGEST_BYTES,
             db.MAX_ENVELOPE_BYTES, db.MAX_EVAL_RESULTS_BYTES, db.MAX_PREFS_FILE_BYTES,
             db.MAX_PREFS_ENTRIES_SCANNED, db.GIT_TIMEOUT_SECONDS, db.MAX_RSI_ENGINE_BYTES,
             db.MAX_KIT_NOTES_BYTES, db.MAX_RSI_CONSTANTS_RENDERED, db.MAX_RSI_VALUE_CHARS,
             db.MAX_RSI_TABLE_ROWS),
            (5000, 32, 8 * 1024 * 1024, 100, 1024 * 1024, 10, 60, 120, 256 * 1024, 512 * 1024,
             4 * 1024 * 1024, 512 * 1024, 500, 20, 1024 * 1024, 2 * 1024 * 1024, 50, 120, 500))
        self.assertEqual(db.PLUGIN_ROOT, BIN_DIR.parent)
        self.assertEqual(db.default_caps(), {name: getattr(db, name) for name in db.CAP_NAMES})
        self.assertEqual(db.STORE_NAME, "dashboard")
        self.assertIn(db.STORE_NAME, rd.STORES)
        # The receipt's class vocabulary (P1 fix round F1), relayed by the skill.
        self.assertEqual(db.CLASS_NAMES, ("mapped", "unmapped", "residue"))
        self.assertEqual(db.LISTING_STATES, ("complete", "truncated", "failed", "absent"))
        self.assertEqual(db.COUNT_QUALIFIERS, ("exact", "lower_bound", "unknown"))

    def test_residue_pattern_matches_tempfile_names_only(self):
        self.assertTrue(db.RESIDUE_NAMESPACE_RE.fullmatch("tmpab3_x9kd-1a2b3c4d"))
        for name in ("tmpab3_x9kd-1a2b3c4d\n", "tmpAB3_X9KD-1a2b3c4d", "tmpab3_x9k-1a2b3c4d",
                     "polytropos-1a2b3c4d", "tmpab3_x9kd-1a2b3c4g"):
            self.assertIsNone(db.RESIDUE_NAMESPACE_RE.fullmatch(name), name)


class ProjectsDirGuardTests(_WorldCase):
    """GUARDRAILS: every build and model a test runs prices from an empty temp projects dir. The
    module-wide guard on the scorecard's projects-dir reader (`setUpModule`) is what makes that
    hold for every test in this file; this shows the guard trips."""

    def test_a_model_without_an_empty_temp_projects_dir_is_refused_by_the_guard(self):
        checkouts = [str(self.world["checkout"])]
        with self.assertRaises(_NotAnEmptyTempProjectsDir):
            db.build_model(self.world["data_home"], checkouts, {"notes": []}, None)
        (self.projects / "not-empty.jsonl").write_text("{}\n")
        with self.assertRaises(_NotAnEmptyTempProjectsDir):
            db.build_model(self.world["data_home"], checkouts, _opts(self), None)


# ---------------------------------------------------------------------------------------------
# Telemetry snapshots panel (T6 item 1).

class TelemetryPanelTests(_WorldCase):

    def test_the_owners_rogue_file_note_and_the_dashboards_unregistered_source_note_appear(self):
        # P2 fix round S8: renamed from `..._notes_from_the_owner_appear`. Since T6's retry the
        # rogue-file note is the owner's (`read_source_snapshots`), while the unregistered-source
        # note is the dashboard's own, mirroring `build_list_summary`'s wording -- the parity
        # test below pins that mirror against the owner itself.
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "telemetry")
        self.assertIn("rogue snapshot file skipped: cost_report/notes.json", section)
        self.assertIn("unregistered source dir: mystery", section)

    def test_per_source_rows_and_notes_match_the_owners_build_list_summary_on_a_clean_store(self):
        # P2 fix round S8 (the phase review's Q1 ruling): T6's retry packages the per-source
        # table itself, from `read_source_snapshots`, instead of calling the owner's
        # `build_list_summary` (which raises on a malformed `labels`). On a CLEAN store the owner
        # does not raise, so its own rows and notes are the reference the page must match: count,
        # first, last, latest status and latest labels per source, and every note, verbatim.
        ts = db._mod("telemetry_snapshot")
        summary, owner_notes = ts.build_list_summary(self.world["telemetry_dir"])
        self.assertIsNotNone(summary)
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "telemetry")
        self.assertEqual(sorted(row["source"] for row in summary["sources"]),
                         sorted(list(ts.SOURCES) + ["mystery"]))
        for row in summary["sources"]:
            labels = " | ".join(str(label) for label in row["latest_labels"]) or "—"
            expected = "<tr>" + "".join(f"<td>{cell}</td>" for cell in (
                db.esc(row["source"]), db.esc(row["registered"]), db.fmt_count(row["count"]),
                db.fmt_date(row["first_date"]), db.fmt_date(row["last_date"]),
                db.esc(row["latest_status"]), db.esc(labels))) + "</tr>"
            self.assertIn(expected, section, row["source"])
        self.assertTrue(owner_notes)
        for note in owner_notes:
            self.assertIn(db.esc(note), section)

    def test_latest_envelope_labels_appear_verbatim_registered_and_unregistered(self):
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "telemetry")
        # cost_report's LATEST (day 2) envelope's own labels (synthetic_world, T6 item 3).
        self.assertIn("synthetic cost_report day 2", section)
        self.assertIn("billing-mode: synthetic-flat", section)
        # day 1's label must not have been substituted for day 2's -- the LATEST envelope only.
        self.assertNotIn("synthetic cost_report day 1", section)
        # the unregistered "mystery" source dir renders labels only (PLAN D7g).
        self.assertIn("mystery label", section)

    def test_a_headline_field_absent_from_a_payload_renders_unknown(self):
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "telemetry")
        # cost_report's latest envelope omits "mode" on purpose (synthetic_world, T6 item 3).
        self.assertIn(f"<td>mode</td><td>{UNKNOWN_SPAN}</td>", section)
        # the OTHER headline fields for that same envelope still render their real values.
        self.assertIn("pricing_cached_date", section)
        self.assertIn("2026-01-02", section)
        self.assertIn("$15.00", section)

    def test_context_overview_and_attempts_headline_use_every_key_of_their_substructure(self):
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "telemetry")
        for field in ("claude.found", "codex.found", "copilot.found"):
            self.assertIn(field, section)
        for field in ("coverage.kits", "coverage.kits_with_ledger", "coverage.kits_with_notes",
                     "coverage.kits_with_role_use"):
            self.assertIn(field, section)

    def test_codex_usage_and_copilot_usage_headline_fields_render(self):
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "telemetry")
        self.assertIn("<td>branch</td><td>priced</td>", section)
        self.assertIn("<td>priced</td><td>True</td>", section)
        self.assertIn("totals.aic", section)
        self.assertIn("45.00", section)  # copilot_usage day 2's aic, a credits cell (no $)

    def test_a_mapped_namespace_without_a_telemetry_dir_renders_never_captured(self):
        checkout2 = self.tmp / "second-checkout-no-telemetry"
        checkout2.mkdir()
        namespace2 = rd.project_namespace(checkout2)
        (self.world["data_home"] / namespace2 / "attempts").mkdir(parents=True)
        rc, out, _stdout, stderr = self.build("out", "--checkout", str(checkout2))
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "telemetry")
        self.assertIn("never captured", section)
        self.assertIn("telemetry_snapshot.py", section)

    def test_a_symlinked_telemetry_store_is_not_followed(self):
        checkout2 = self.tmp / "linked-telemetry-checkout"
        checkout2.mkdir()
        namespace2 = rd.project_namespace(checkout2)
        ns2_dir = self.world["data_home"] / namespace2
        ns2_dir.mkdir(parents=True)
        (ns2_dir / "attempts").mkdir()
        elsewhere = self.tmp / "elsewhere-telemetry"
        elsewhere.mkdir()
        os.symlink(elsewhere, ns2_dir / "telemetry")
        rc, out, _stdout, stderr = self.build("out", "--checkout", str(checkout2))
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "telemetry")
        self.assertIn("is a symlink", section)
        self.assertIn("not followed", section)

    def test_unmapped_namespace_showing_a_telemetry_store_is_counted_and_noted_not_read(self):
        extra_unmapped = "extra-unmapped-telemetry-0000dead"
        (self.world["data_home"] / extra_unmapped / "telemetry").mkdir(parents=True)
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "telemetry")
        self.assertIn("unmapped namespace(s) show a telemetry store", section)
        self.assertIn("config.json", section)
        # counted, never named or opened by THIS panel -- the namespaces panel earlier on the
        # page is the one place an unmapped namespace's own name is shown (PLAN D4).
        self.assertNotIn(extra_unmapped, section)

    def test_telemetry_panel_shows_a_refresh_hint_naming_the_script(self):
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "telemetry")
        self.assertIn("telemetry_snapshot.py", section)
        self.assertEqual(section.count('<p class="meta">'), 2)  # source/observed/age + the hint

    def test_no_data_home_telemetry_panel_has_no_refresh_hint(self):
        model = db.build_model(None, [], _opts(self), None)
        telemetry = next(p for p in model["panels"] if p["id"] == "telemetry")
        self.assertIsNone(telemetry["refresh_hint"])

    def test_cost_report_sparkline_block_has_one_twin_row_per_kept_envelope(self):
        dated = [
            ("2026-01-01", {"status": "ok", "payload": {"totals": {"usd": 1.0}},
                           "labels": ["L1"]}),
            ("2026-01-02", {"status": "ok", "payload": {"totals": {"usd": 2.0}},
                           "labels": ["L2"]}),
        ]
        notes = []
        block = db._cost_report_sparkline_block(dated, "some-label", notes)
        self.assertEqual(block["type"], "svg_sparkline")
        self.assertEqual(block["points"], [("2026-01-01", 1.0), ("2026-01-02", 2.0)])
        self.assertEqual(block["value_cell"], {"fmt": "usd", "basis": "L2"})
        self.assertEqual(notes, [])
        self.assertIsNone(db._cost_report_sparkline_block([], "some-label", notes))

    def test_cost_report_sparkline_malformed_labels_is_a_note_not_a_crash(self):
        dated = [("2026-01-01", {"status": "ok", "payload": {"totals": {"usd": 1.0}},
                                 "labels": 42})]
        notes = []
        block = db._cost_report_sparkline_block(dated, "some-label", notes)
        self.assertEqual(block["value_cell"], {"fmt": "usd", "basis": "no label from cost_report"})
        self.assertTrue(any("labels" in n and "malformed" in n for n in notes), notes)

    def test_the_cost_report_sparkline_appears_in_the_rendered_section(self):
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "telemetry")
        self.assertIn("cost_report totals.usd across kept envelopes", section)
        self.assertIn("<svg", section)

    # -- T6 retry, red-team A: one malformed envelope must not blank the section. --------------

    def test_a_malformed_labels_field_on_the_latest_envelope_is_a_note_not_a_crash(self):
        cost_dir = self.world["telemetry_dir"] / "cost_report"
        bad = {"status": "ok", "labels": 42, "payload": {"totals": {"usd": 1.0}}}
        (cost_dir / "2026-01-03.json").write_text(json.dumps(bad))
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        section = _section(page, "telemetry")
        # every OTHER source, and the unregistered "mystery" one, survives intact.
        for source in ("codex_usage", "copilot_usage", "context_overview", "routing_history",
                      "attempts", "mystery"):
            self.assertIn(source, section)
        self.assertIn("cost_report: envelope", section)
        self.assertIn("field is malformed (not a list) and was not rendered", section)
        # cost_report itself still gets a row and a deep-dive -- only its labels are dropped.
        self.assertIn("<td>cost_report</td>", section)
        self.assertIn("cost_report — capture_date", section)
        self.assertNotIn("not available this build", page)

    # -- T6 retry, red-team B: a link inside the store is noted, its source never rendered. ----

    def test_a_symlinked_telemetry_source_directory_is_excluded_with_a_note(self):
        secret_dir = self.tmp / "outside-secret"
        secret_dir.mkdir()
        marker = "SECRET-LEAK-MARKER-9f21"
        (secret_dir / "2099-01-01.json").write_text(json.dumps(
            {"status": "ok", "labels": [marker], "payload": {}}))
        os.symlink(secret_dir, self.world["telemetry_dir"] / "leaky", target_is_directory=True)
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        section = _section(page, "telemetry")
        self.assertNotIn(marker, page)
        self.assertIn("leaky", section)
        self.assertIn("symlinked directory", section)
        self.assertIn("not followed", section)
        # the healthy sources are unaffected.
        self.assertIn("<td>cost_report</td>", section)

    def test_a_symlinked_envelope_file_excludes_the_whole_source_with_a_note(self):
        outside = self.tmp / "outside-file.json"
        outside.write_text(json.dumps({
            "status": "ok", "labels": ["definitely not an estimate"],
            "payload": {"totals": {"usd": 999999.99}, "mode": "FABRICATED",
                       "pricing_cached_date": "2099-01-01"},
        }))
        cost_dir = self.world["telemetry_dir"] / "cost_report"
        (cost_dir / "2099-01-01.json").symlink_to(outside)
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        section = _section(page, "telemetry")
        self.assertNotIn("999999.99", page)
        self.assertNotIn("999,999.99", page)
        self.assertNotIn("FABRICATED", page)
        self.assertIn("symlinked envelope file", section)
        self.assertNotIn("<td>cost_report</td>", section)  # the whole source is dropped
        self.assertNotIn("cost_report — capture_date", section)
        # a healthy sibling source is unaffected.
        self.assertIn("<td>codex_usage</td>", section)

    # -- T6 retry, red-team C: bound the envelope read. -----------------------------------------

    def test_an_oversized_envelope_file_skips_only_its_source(self):
        junk = "B" * (db.MAX_ENVELOPE_BYTES + 1024)
        oversized = {"status": "ok", "labels": ["oversized"],
                    "payload": {"totals": {"usd": 1.0}, "junk": junk}}
        cost_dir = self.world["telemetry_dir"] / "cost_report"
        (cost_dir / "2026-01-03.json").write_text(json.dumps(oversized))
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        section = _section(page, "telemetry")
        self.assertNotIn("B" * 100, page)
        self.assertIn("MAX_ENVELOPE_BYTES", page)
        self.assertNotIn("<td>cost_report</td>", section)
        self.assertIn("<td>codex_usage</td>", section)
        bounds = _section(page, "bounds")
        # T7 retry V2: the row's OWN status cell, not just that some row somewhere says "hit".
        self.assertIn(f"<td>MAX_ENVELOPE_BYTES</td><td>{db.MAX_ENVELOPE_BYTES}</td>"
                      f"<td>hit</td>", bounds)
        self.assertIn("MAX_ENVELOPE_BYTES", self.receipt(out)["caps_hit"])


# ---------------------------------------------------------------------------------------------
# P2 fix round S5: a FIFO at any leaf the build opens never hangs it.

class _BuildHung(BaseException):
    """Raised by the SIGALRM handler below. A BaseException, so none of the engine's own
    `except Exception` containment can swallow it: a regression FAILS instead of hanging."""


def _on_alarm(_signum, _frame):
    raise _BuildHung()


@unittest.skipUnless(hasattr(os, "mkfifo") and hasattr(signal, "SIGALRM"),
                     "needs os.mkfifo and SIGALRM")
class FifoLeafTests(_WorldCase):
    """At each leaf the build pre-checks before it -- or an owner it calls -- opens it whole, the
    leaf is `lstat`'d and must be a regular file: a FIFO there would block the open with no
    writer. It is excluded with a note and never opened. Each build runs under a 10 s alarm and
    disarms it in a `finally`."""

    def build_under_alarm(self, *extra):
        previous = signal.signal(signal.SIGALRM, _on_alarm)
        signal.alarm(10)
        try:
            return self.build("out", *extra)
        except _BuildHung:
            self.fail("the build blocked on a FIFO for 10 s")
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)

    def test_a_fifo_telemetry_envelope_excludes_only_its_source(self):
        os.mkfifo(self.world["telemetry_dir"] / "cost_report" / "2026-01-09.json")
        rc, out, _stdout, stderr = self.build_under_alarm()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "telemetry")
        self.assertIn("2026-01-09.json is a FIFO, not a regular file — never opened; the whole "
                      "source is not rendered", section)
        self.assertNotIn("<td>cost_report</td>", section)
        self.assertIn("<td>codex_usage</td>", section)

    def test_a_fifo_digest_json_is_skipped_and_the_other_days_render(self):
        day = self.world["journal_dir"] / "2026-01-09"
        day.mkdir()
        os.mkfifo(day / "digest.json")
        rc, out, _stdout, stderr = self.build_under_alarm()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "journal")
        self.assertIn("2026-01-09: digest.json is a FIFO, not a regular file — skipped, never "
                      "read", section)
        self.assertIn("$1.23", section)
        self.assertIn("$2.50", section)

    def test_a_fifo_results_json_excludes_that_run_and_the_vetted_cards_render(self):
        run = self.world["evals_dir"] / "run-2026-01-09-fifo"
        run.mkdir()
        os.mkfifo(run / "results.json")
        rc, out, _stdout, stderr = self.build_under_alarm()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "evals")
        self.assertIn("results.json is a FIFO, not a regular file — never opened", section)
        self.assertIn("list_runs was not called", section)  # it would open the FIFO too
        self.assertIn("run run-2026-01-01-demo — repo", section)

    def test_a_fifo_policy_file_excludes_the_three_prefs_reports(self):
        we = db._mod("workflow_eval")
        os.mkfifo(self.world["prefs_dir"] / we.POLICY_FILE)
        rc, out, _stdout, stderr = self.build_under_alarm()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "evals")
        self.assertIn("is a FIFO, not a regular file — never opened; policy/approval/activation "
                      "are not read this build", section)
        self.assertNotIn("none in force.", section)
        self.assertIn("run run-2026-01-01-demo — repo", section)

    def test_a_fifo_ledger_events_file_is_skipped_by_the_history_join_and_the_ledger_facts(self):
        events = Path(self.world["ledger"])  # the mapped demo-kit ledger's events file
        events.unlink()
        os.mkfifo(events)
        rc, out, _stdout, stderr = self.build_under_alarm()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "attempts")
        self.assertIn(db.esc(f"kit {db.DEMO_KIT}'s ledger file is a FIFO, not a regular file, "
                             f"and was never opened"), section)
        self.assertIn(f"{self.world['namespace']}/{db.DEMO_KIT}: its events file is a FIFO, not "
                      f"a regular file — skipped, never read", section)
        self.assertIn(db.UNMAPPED_NAMESPACE, section)  # the other ledger's row still renders

    def test_a_fifo_config_json_is_refused_with_a_note_and_treated_as_absent(self):
        # P2 fix round, closing S5's last leaf: the dashboard's own config.json, read before the
        # build even classifies anything.
        out = self.tmp / "out"
        out.mkdir(mode=0o700)
        os.mkfifo(out / "config.json")
        rc, out, _stdout, stderr = self.build_under_alarm()
        self.assertEqual(rc, 0, stderr)
        expected = "config.json in"
        notes = [note for note in self.receipt(out)["notes"] if note.startswith(expected)]
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("is a FIFO, not a regular file — never opened; treated as absent",
                      notes[0])
        self.assertIn("is a FIFO, not a regular file — never opened; treated as absent",
                      _section(self.page(out), "bounds"))
        self.assertTrue(stat.S_ISFIFO(os.lstat(out / "config.json").st_mode))  # left in place

    def test_a_fifo_tasks_md_is_skipped_with_a_note(self):
        kit = self.world["kits_dir"] / "fifo-kit"
        kit.mkdir()
        os.mkfifo(kit / "TASKS.md")
        rc, out, _stdout, stderr = self.build_under_alarm()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "kits")
        self.assertIn("fifo-kit: TASKS.md is a FIFO, not a regular file — skipped, never read",
                      section)
        self.assertIn(db.SCORECARD_KIT, section)


# ---------------------------------------------------------------------------------------------
# Journal digests panel (T6 item 2).

class JournalPanelTests(_WorldCase):

    def test_unknown_schema_version_day_is_noted_and_none_of_its_numbers_render(self):
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        section = _section(page, "journal")
        self.assertIn(f"{self.world['journal_days'][2]}: unknown digest version, not rendered",
                      section)
        self.assertNotIn("54321", page)

    def test_every_journal_day_note_carries_the_namespace_label(self):
        # P2 fix round polish: a day note names the namespace it came from, like every other
        # per-namespace note on the page, so two checkouts' same-day notes never read alike.
        checkout = str(self.world["checkout"])
        model = db.build_model(self.world["data_home"], [checkout], _opts(self), None)
        journal = next(p for p in model["panels"] if p["id"] == "journal")
        day = self.world["journal_days"][2]
        self.assertIn(f"{checkout}: {day}: unknown digest version, not rendered",
                      journal["notes"])
        self.assertFalse(any(note.startswith(f"{day}:") for note in journal["notes"]),
                         journal["notes"])

    def test_the_canary_inbox_string_never_renders_anywhere_on_the_page(self):
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        self.assertNotIn("CANARY-INBOX-TEXT-DO-NOT-RENDER", self.page(out))

    def test_latest_day_per_source_table_shows_priced_and_unpriced_correctly(self):
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "journal")
        self.assertIn(f"per-source detail for the latest day ({self.world['journal_days'][1]})",
                      section)
        self.assertIn("unpriced", section)  # codex_usage, priced: false
        self.assertIn("$2.50", section)     # cost_report day 2's usd_priced, priced: true

    def test_journal_panel_states_it_reads_nothing_else_from_the_digest(self):
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "journal")
        self.assertIn("not inbox, not signals, not any narrative file", section)

    def test_max_journal_days_cap_lowered_to_one_leaves_a_note(self):
        checkouts = [str(self.world["checkout"])]
        model = db.build_model(self.world["data_home"], checkouts, _opts(self),
                               {"MAX_JOURNAL_DAYS": 1})
        journal = next(p for p in model["panels"] if p["id"] == "journal")
        self.assertTrue(any(note.startswith("cap MAX_JOURNAL_DAYS (1) reached")
                            for note in journal["notes"]), journal["notes"])
        caps_row = {row["name"]: row for row in model["caps"]}["MAX_JOURNAL_DAYS"]
        self.assertTrue(caps_row["hit"])
        # only the single newest day (2026-01-03, the unrenderable schema-99 one) was kept.
        page = db.render_page(model, _FAKE_HOME.name)
        section = _section(page, "journal")
        self.assertIn("unknown digest version", section)
        self.assertNotIn("1.23", section)
        self.assertNotIn("2.5", section)

    def test_a_symlinked_journal_day_directory_is_not_followed(self):
        journal_dir = self.world["journal_dir"]
        elsewhere = self.tmp / "somewhere-else-journal"
        elsewhere.mkdir()
        (elsewhere / "digest.json").write_text(json.dumps({
            "schema_version": db._mod("journal_collect").SCHEMA_VERSION,
            "totals": {"usd_priced": 77.0, "sessions": 7, "sources_active": [],
                      "unpriced_sources": []},
            "sources": {},
        }))
        os.symlink(elsewhere, journal_dir / "2026-02-02")
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        section = _section(page, "journal")
        self.assertIn("2026-02-02", section)
        self.assertIn("symlinked day directory", section)
        self.assertNotIn("77.0", page)
        self.assertNotIn("somewhere-else-journal", page)

    def test_unmapped_namespace_showing_a_journal_store_is_counted_and_noted_not_read(self):
        extra_unmapped = "extra-unmapped-journal-0000beef"
        (self.world["data_home"] / extra_unmapped / "journal").mkdir(parents=True)
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "journal")
        self.assertIn("unmapped namespace(s) show a journal store", section)
        self.assertIn("config.json", section)
        # counted, never named or opened by THIS panel (PLAN D4) -- see the telemetry twin above.
        self.assertNotIn(extra_unmapped, section)

    def test_both_schema_one_days_render_with_sparkline_and_day_table(self):
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "journal")
        self.assertIn(self.world["journal_days"][0], section)
        self.assertIn(self.world["journal_days"][1], section)
        self.assertIn("$1.23", section)
        self.assertIn("$2.50", section)
        self.assertIn("journal usd_priced by day", section)
        self.assertIn("journal digests by day", section)

    def test_no_data_home_journal_panel_is_a_plain_note(self):
        model = db.build_model(None, [], _opts(self), None)
        journal = next(p for p in model["panels"] if p["id"] == "journal")
        self.assertIsNone(journal["observed"])
        self.assertIn("no journal digest could be read", journal["blocks"][0]["text"])

    # -- T6 retry, red-team C: bound the digest read. -------------------------------------------

    def test_an_oversized_digest_json_is_capped_and_never_read(self):
        junk = "A" * (db.MAX_DIGEST_BYTES + 1024)
        digest = {"schema_version": db._mod("journal_collect").SCHEMA_VERSION,
                 "totals": {"usd_priced": 1.23, "sessions": 1, "sources_active": [],
                            "unpriced_sources": []},
                 "sources": {}, "junk": junk}
        day_dir = self.world["journal_dir"] / "2099-01-01"
        day_dir.mkdir(parents=True)
        (day_dir / "digest.json").write_text(json.dumps(digest))
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        section = _section(page, "journal")
        self.assertNotIn("A" * 100, page)
        self.assertIn("MAX_DIGEST_BYTES", page)
        self.assertIn("2099-01-01", section)
        self.assertIn("skipped, never read", section)
        bounds = _section(page, "bounds")
        # T7 retry V2: the row's OWN status cell, not just that some row somewhere says "hit".
        self.assertIn(f"<td>MAX_DIGEST_BYTES</td><td>{db.MAX_DIGEST_BYTES}</td><td>hit</td>",
                      bounds)
        self.assertIn("MAX_DIGEST_BYTES", self.receipt(out)["caps_hit"])
        # the healthy schema-1 days are unaffected.
        self.assertIn("$1.23", section)
        self.assertIn(self.world["journal_days"][0], section)


# ---------------------------------------------------------------------------------------------
# Evaluation runs, policy/approvals/activation panel (T7 items 1-2).

class EvalsPanelTests(_WorldCase):

    def test_the_version_99_run_appears_only_through_the_owners_note(self):
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        section = _section(page, "evals")
        self.assertIn("run-2026-01-02-oldversion: not a polytropos.workflow-eval/1 envelope",
                      section)
        self.assertNotIn("<td>run-2026-01-02-oldversion</td>", section)

    def test_not_a_ranking_appears_for_a_single_repeat_run(self):
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        we = db._mod("workflow_eval")
        section = _section(self.page(out), "evals")
        self.assertIn(we.NOT_A_RANKING, section)

    def test_ranking_none_appears_and_no_ranking_list_does(self):
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "evals")
        self.assertIn("ranking: none — the owner did not rank", section)
        self.assertNotIn("ranking: v1", section)

    def test_a_below_floor_variant_renders_the_owners_label(self):
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "evals")
        self.assertIn("v1: BELOW EVIDENCE FLOOR (n=1 &lt; 10)", section)

    def test_spent_usd_none_renders_unknown(self):
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "evals")
        self.assertIn(f"<td>run-2026-01-01-demo</td><td>claude</td><td>demo-repo</td>"
                      f"<td>1</td><td>{UNKNOWN_SPAN}</td>", section)

    def test_the_not_a_run_directory_is_noted_never_rendered_as_a_run(self):
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "evals")
        self.assertIn("not-a-run: not an evaluation run", section)

    def test_manifests_are_counted_by_name_never_opened(self):
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "evals")
        self.assertIn("manifests (names only, never opened): 2", section)

    def test_approvals_absent_renders_the_owners_empty_shape_without_error(self):
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        section = _section(page, "evals")
        self.assertIn("no approvals recorded", section)
        self.assertNotIn("Traceback", page)
        self.assertNotIn("not available this build", section)

    def test_unmapped_namespace_showing_an_evals_or_prefs_store_is_counted_and_noted(self):
        extra1 = "extra-unmapped-evals-0000dead"
        extra2 = "extra-unmapped-prefs-0000beef"
        (self.world["data_home"] / extra1 / "evals").mkdir(parents=True)
        (self.world["data_home"] / extra2 / "prefs").mkdir(parents=True)
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "evals")
        # P2 fix round polish: the article follows the store name ("an evals", "a prefs").
        self.assertIn("unmapped namespace(s) show an evals store", section)
        self.assertIn("unmapped namespace(s) show a prefs store", section)
        self.assertNotIn("show a evals store", section)
        self.assertNotIn(extra1, section)
        self.assertNotIn(extra2, section)

    def test_max_eval_runs_rendered_cap_lowered_leaves_a_note(self):
        checkouts = [str(self.world["checkout"])]
        model = db.build_model(self.world["data_home"], checkouts, _opts(self),
                               {"MAX_EVAL_RUNS_RENDERED": 0})
        evals = next(p for p in model["panels"] if p["id"] == "evals")
        self.assertTrue(any(note.startswith("cap MAX_EVAL_RUNS_RENDERED (0) reached")
                            for note in evals["notes"]), evals["notes"])
        page = db.render_page(model, _FAKE_HOME.name)
        section = _section(page, "evals")
        # the run row still appears in the runs TABLE; no per-run card was built for it.
        self.assertIn("run-2026-01-01-demo", section)
        self.assertNotIn("variants (1 row)", section)

    def test_a_malformed_trial_field_is_a_note_not_a_crash_for_the_whole_namespace(self):
        # T7 retry R1: a trial whose `oracles` is a truthy string used to make the owner's
        # `_variant_summary` raise `AttributeError`. The owner now counts it as an oracle that
        # did not report, so the bad run's card renders; the dashboard's per-run catch is
        # then exercised by making `build_card` raise for that run alone.
        we = db._mod("workflow_eval")
        bad_run = self.world["evals_dir"] / "run-2026-01-05-oraclesstr"
        bad_run.mkdir(parents=True)
        envelope = {
            "v": we.EVAL_VERSION, "run_id": "run-2026-01-05-oraclesstr", "repo": "demo-repo",
            "harness": "claude", "repeats": 1, "evidence_floor": 10,
            "variants": [{"id": "v1"}],
            "trials": [{"trial": "t1", "variant": "v1", "task_id": "task1", "solved": True,
                       "oracles": "not-a-dict"}],
            "labels": ["synthetic eval run 2"],
        }
        (bad_run / "results.json").write_text(json.dumps(envelope))
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "evals")
        self.assertIn("run run-2026-01-05-oraclesstr — repo", section)
        self.assertNotIn("card unavailable", section)

        real_build_card = we.build_card

        def build_card_raising_for_the_bad_run(env):
            if env.get("run_id") == "run-2026-01-05-oraclesstr":
                raise AttributeError("simulated owner failure")
            return real_build_card(env)

        with mock.patch.object(we, "build_card", build_card_raising_for_the_bad_run):
            rc, out, _stdout, stderr = self.build("out-raising")
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        section = _section(page, "evals")
        # the good run's own card still renders in full ...
        self.assertIn("v1: BELOW EVIDENCE FLOOR", section)
        self.assertIn("<td>run-2026-01-01-demo</td>", section)
        # ... and the bad run gets its own note naming it and the exception type, never a
        # panel-wide "not available" fallback that would mean the whole section was lost.
        # (the run id is `!r`-quoted then HTML-escaped, so the apostrophes become `&#x27;`.)
        self.assertIn("run-2026-01-05-oraclesstr", section)
        self.assertIn("card unavailable (AttributeError)", section)
        # never the PANEL-WIDE fallback (`build_evals_panel`'s own per-namespace catch): its
        # own text names the checkout right after "Evaluation runs for", which would only
        # appear if the per-namespace catch fired and erased this whole section.
        self.assertNotIn(f"Evaluation runs for {self.world['checkout']}: not available",
                        section)

    def test_list_runs_raising_falls_back_to_per_run_reads_for_the_good_runs(self):
        # T7 retry R2: a `results.json` that is valid JSON but not an object (`[1, 2, 3]`)
        # used to make the owner's `list_runs` raise `AttributeError`. The owner now notes it
        # instead, so the raise is forced here to keep the dashboard's fallback path covered.
        second_run = self.world["evals_dir"] / "run-2026-01-03-second"
        second_run.mkdir(parents=True)
        good2 = dict(json.loads((self.world["good_run_dir"] / "results.json").read_text()))
        good2["run_id"] = "run-2026-01-03-second"
        (second_run / "results.json").write_text(json.dumps(good2))
        bad_run = self.world["evals_dir"] / "run-2026-01-04-notadict"
        bad_run.mkdir(parents=True)
        (bad_run / "results.json").write_text(json.dumps([1, 2, 3]))
        with mock.patch.object(db._mod("workflow_eval"), "list_runs",
                               side_effect=AttributeError("simulated owner failure")):
            rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        section = _section(page, "evals")
        self.assertIn("the runs table is not available this build — workflow_eval.list_runs "
                      "raised AttributeError", section)
        # both GOOD runs' own cards still render, from the owner's own read_envelope/build_card
        # over the pre-scan's safe directory names, never a re-parse of results.json here.
        self.assertIn("run run-2026-01-01-demo — repo", section)
        self.assertIn("run run-2026-01-03-second — repo", section)
        # the bad (non-object) run fails the version gate every card passes (P2 fix round B2):
        # the owner's own `list_runs` wording, and no card.
        we = db._mod("workflow_eval")
        self.assertIn(f"run-2026-01-04-notadict: not a {we.EVAL_VERSION} envelope", section)
        self.assertNotIn("run run-2026-01-04-notadict", section)
        # `list_runs` never finished, so the owner's own "not an evaluation run" note is
        # repeated by the dashboard for the directory that holds no results.json.
        self.assertIn("not-a-run: not an evaluation run", section)

    def test_a_symlinked_eval_run_directory_is_excluded_and_the_vetted_runs_cards_render(self):
        # P2 fix round S4 (renamed from `..._is_excluded_with_a_note`): one linked run plus one
        # good run -- the linked run is excluded by name, `list_runs` stays uncalled (it would
        # read the linked run too), and the good run's card still renders through the per-run
        # loop over vetted directory names.
        we = db._mod("workflow_eval")
        secret_dir = self.tmp / "outside-eval-secret"
        secret_dir.mkdir()
        marker = "EVAL-LEAK-MARKER-abc1"
        (secret_dir / "results.json").write_text(json.dumps({
            "v": we.EVAL_VERSION, "run_id": "leaky-run", "labels": [marker]}))
        os.symlink(secret_dir, self.world["evals_dir"] / "leaky", target_is_directory=True)
        # A wrapping spy, never a raising one: the engine contains an owner that raises, so a
        # raising stand-in would be swallowed and prove nothing.
        with mock.patch.object(we, "list_runs", wraps=we.list_runs) as list_runs:
            rc, out, _stdout, stderr = self.build()
        list_runs.assert_not_called()
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        section = _section(page, "evals")
        self.assertNotIn(marker, page)
        self.assertIn("evals run &#x27;leaky&#x27; excluded from this build (symlinked run "
                      "directory)", section)
        self.assertIn("list_runs was not called", section)
        self.assertNotIn("<td>run-2026-01-01-demo</td>", section)  # no runs table this build
        self.assertIn("run run-2026-01-01-demo — repo", section)   # ... but the card renders
        self.assertIn("v1: BELOW EVIDENCE FLOOR", section)
        self.assertIn(f"run-2026-01-02-oldversion: not a {we.EVAL_VERSION} envelope", section)
        self.assertIn("not-a-run: not an evaluation run", section)

    def test_a_symlinked_results_json_excludes_only_that_run_with_a_note(self):
        # Renamed from `..._excludes_the_whole_store_with_a_note` (P2 fix round S4).
        outside = self.tmp / "outside-results.json"
        outside.write_text(json.dumps({
            "v": db._mod("workflow_eval").EVAL_VERSION, "run_id": "fake",
            "labels": ["FABRICATED-EVAL-LABEL"]}))
        run_dir = self.world["evals_dir"] / "run-2099-01-01-linked"
        run_dir.mkdir()
        (run_dir / "results.json").symlink_to(outside)
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        section = _section(page, "evals")
        self.assertNotIn("FABRICATED-EVAL-LABEL", page)
        self.assertIn("symlinked results.json", section)
        self.assertNotIn("run run-2099-01-01-linked", section)
        self.assertIn("run run-2026-01-01-demo — repo", section)

    def test_an_oversized_results_json_excludes_only_that_run_and_hits_the_cap(self):
        # Renamed from `..._excludes_the_whole_store_with_a_note` (P2 fix round S4).
        junk = "C" * (db.MAX_EVAL_RESULTS_BYTES + 1024)
        run_dir = self.world["evals_dir"] / "run-2099-02-02-huge"
        run_dir.mkdir()
        (run_dir / "results.json").write_text(json.dumps({
            "v": db._mod("workflow_eval").EVAL_VERSION, "run_id": "huge", "junk": junk}))
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        section = _section(page, "evals")
        self.assertNotIn("C" * 100, page)
        self.assertIn("MAX_EVAL_RESULTS_BYTES", page)
        self.assertNotIn("run run-2099-02-02-huge", section)
        self.assertIn("run run-2026-01-01-demo — repo", section)
        bounds = _section(page, "bounds")
        # T7 retry V1/V2: the row's OWN status cell must read "hit" (V1's own fix routes the
        # exclusion through `cap_note`), not just that the row exists -- it renders on every
        # build regardless.
        self.assertIn(f"<td>MAX_EVAL_RESULTS_BYTES</td><td>{db.MAX_EVAL_RESULTS_BYTES}</td>"
                      f"<td>hit</td>", bounds)
        self.assertIn("MAX_EVAL_RESULTS_BYTES", self.receipt(out)["caps_hit"])

    def test_a_symlinked_prefs_entry_excludes_all_three_reports_with_a_note(self):
        # P2 fix round S3: the link sits INSIDE the owner's read set -- a proposal file the
        # owner's `policy_report` would read whole -- since only that set is pre-scanned now.
        we = db._mod("workflow_eval")
        outside = self.tmp / "outside-prefs-file.json"
        outside.write_text(json.dumps({"leak": "PREFS-LEAK-MARKER-77"}))
        proposals = self.world["prefs_dir"] / we.POLICY_PROPOSALS
        proposals.mkdir()
        (proposals / "linked.json").symlink_to(outside)
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        section = _section(page, "evals")
        self.assertNotIn("PREFS-LEAK-MARKER-77", page)
        self.assertIn("prefs entry", section)
        self.assertIn(html.escape(f"{we.POLICY_PROPOSALS}/linked.json", quote=True), section)
        self.assertIn("is a symlink", section)
        self.assertIn("policy/approval/activation are not read this build", section)
        self.assertNotIn("none in force.", section)  # the whole prefs section was skipped
        self.assertIn("run-2026-01-01-demo", section)  # evals runs are unaffected

    def test_an_oversized_prefs_file_excludes_all_three_reports_with_a_note(self):
        # P2 fix round S3: the oversized file is an approval record the owner reads whole.
        we = db._mod("workflow_eval")
        junk = "D" * (db.MAX_PREFS_FILE_BYTES + 1024)
        approvals = self.world["prefs_dir"] / we.POLICY_APPROVALS
        approvals.mkdir()
        (approvals / "huge.json").write_text(junk)
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        section = _section(page, "evals")
        self.assertNotIn("D" * 100, page)
        self.assertIn("MAX_PREFS_FILE_BYTES", page)
        self.assertNotIn("none in force.", section)
        bounds = _section(page, "bounds")
        # T7 retry V2: the row's OWN status cell, not just that the row exists.
        self.assertIn(f"<td>MAX_PREFS_FILE_BYTES</td><td>{db.MAX_PREFS_FILE_BYTES}</td>"
                      f"<td>hit</td>", bounds)
        self.assertIn("MAX_PREFS_FILE_BYTES", self.receipt(out)["caps_hit"])

    def test_max_prefs_entries_scanned_cap_lowered_leaves_a_note(self):
        # P2 fix round S3: the entry sits inside the owner's read set, the only part scanned.
        we = db._mod("workflow_eval")
        proposals = self.world["prefs_dir"] / we.POLICY_PROPOSALS
        proposals.mkdir()
        (proposals / "one-entry.json").write_text("{}")
        checkouts = [str(self.world["checkout"])]
        model = db.build_model(self.world["data_home"], checkouts, _opts(self),
                               {"MAX_PREFS_ENTRIES_SCANNED": 0})
        evals = next(p for p in model["panels"] if p["id"] == "evals")
        self.assertTrue(any(note.startswith("cap MAX_PREFS_ENTRIES_SCANNED (0) reached")
                            for note in evals["notes"]), evals["notes"])

    def test_totals_and_spend_tables_carry_the_basis_word_in_their_label(self):
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "evals")
        self.assertIn('<span class="label">model-reported</span>', section)
        self.assertIn('<span class="label">ceiling_usd</span>', section)

    def test_no_data_home_evals_panel_is_a_plain_note(self):
        model = db.build_model(None, [], _opts(self), None)
        evals = next(p for p in model["panels"] if p["id"] == "evals")
        self.assertIsNone(evals["observed"])
        self.assertIn("no evals or prefs store could be read", evals["blocks"][0]["text"])


class EvalsP2FixTests(_WorldCase):
    """P2 fix round B1/B2/B3/S3: cards are read only by vetted directory names, every card passes
    the version gate, proxy dollars carry the owner's proxy label, and the prefs pre-scan covers
    exactly the owner's read set."""

    def we(self):
        return db._mod("workflow_eval")

    def good_envelope(self):
        return json.loads((self.world["good_run_dir"] / "results.json").read_text())

    # -- B1: a declared run_id never steers a read ---------------------------------------------

    def test_a_declared_run_id_outside_the_store_is_never_read_absolute_or_dotdot(self):
        we = self.we()
        evals_dir = self.world["evals_dir"]
        outside = self.tmp / "outside-the-store"
        outside.mkdir()
        canary = "CANARY-OUTSIDE-STORE-LABEL-3b7d"
        outside_envelope = dict(self.good_envelope(), labels=[canary], run_id="whatever")
        outside_envelope["pad"] = "x" * (db.MAX_EVAL_RESULTS_BYTES + 4096)
        (outside / "results.json").write_text(json.dumps(outside_envelope))
        declared = {"run-2026-09-02-absolute": str(outside),
                    "run-2026-09-03-dotdot": os.path.relpath(outside, evals_dir)}
        self.assertTrue(declared["run-2026-09-03-dotdot"].startswith(".."))
        for name, run_id in declared.items():
            (evals_dir / name).mkdir()
            (evals_dir / name / "results.json").write_text(
                json.dumps(dict(self.good_envelope(), run_id=run_id, labels=["inner"])))
        read = []
        real_read_envelope = we.read_envelope

        def spy(store_dir, run_id):
            read.append((Path(store_dir), run_id))
            return real_read_envelope(store_dir, run_id)

        with mock.patch.object(we, "read_envelope", spy):
            rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        self.assertNotIn(canary, page)
        # Every read went through a vetted directory name -- a plain name of a real directory
        # directly under the store holding a regular results.json within MAX_EVAL_RESULTS_BYTES
        # -- so the size cap holds for every file actually read.
        read_names = [run_id for _store, run_id in read]
        for name in declared:
            self.assertIn(name, read_names)
        for store, run_id in read:
            self.assertEqual(store, evals_dir)
            self.assertEqual(Path(run_id).name, run_id)
            self.assertNotIn(run_id, ("", ".", ".."))
            st = os.lstat(store / run_id / "results.json")
            self.assertTrue(stat.S_ISREG(st.st_mode))
            self.assertLessEqual(st.st_size, db.MAX_EVAL_RESULTS_BYTES)
        for run_id in declared.values():
            self.assertNotIn(run_id, read_names)
        # the declared-id runs' own cards are headed by their own directories.
        section = _section(page, "evals")
        self.assertIn("run run-2026-09-02-absolute  (run_id in its envelope: ", section)
        self.assertEqual(self.receipt(out)["caps_hit"], [])

    # -- B2: the version gate, on every path ---------------------------------------------------

    def plant_foreign_version_canary(self):
        """A canary in the fixture's foreign-version run's own `labels` (its version string is
        the fixture's, never retyped here)."""
        canary = "CANARY-FOREIGN-VERSION-LABEL-5e1a"
        results = self.world["old_run_dir"] / "results.json"
        envelope = json.loads(results.read_text())
        self.assertNotEqual(envelope["v"], self.we().EVAL_VERSION)
        envelope.update(labels=[canary], variants=[{"id": "vX"}], trials=[], repeats=1)
        results.write_text(json.dumps(envelope))
        return canary

    def assert_only_the_gate_note(self, page, canary):
        section = _section(page, "evals")
        note = f"run-2026-01-02-oldversion: not a {self.we().EVAL_VERSION} envelope"
        self.assertNotIn(canary, page)
        self.assertIn(note, section)
        self.assertEqual(section.count("run-2026-01-02-oldversion"), section.count(note))
        self.assertNotIn("run run-2026-01-02-oldversion", section)
        return section

    def test_a_foreign_version_run_renders_only_the_owners_note_on_the_normal_path(self):
        canary = self.plant_foreign_version_canary()
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = self.assert_only_the_gate_note(self.page(out), canary)
        self.assertIn("<td>run-2026-01-01-demo</td>", section)  # list_runs ran: the table shows
        self.assertIn("run run-2026-01-01-demo — repo", section)

    def test_a_foreign_version_run_renders_only_the_owners_note_on_the_fallback_path(self):
        canary = self.plant_foreign_version_canary()
        not_an_object = self.world["evals_dir"] / "run-2026-01-04-notadict"
        not_an_object.mkdir()
        (not_an_object / "results.json").write_text("[1, 2]")
        # The owner's `list_runs` now notes a non-object results.json instead of raising, so
        # the fallback path is forced here: it stays the dashboard's defence against any
        # other way the owner's listing can raise.
        with mock.patch.object(self.we(), "list_runs",
                               side_effect=AttributeError("simulated owner failure")):
            rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = self.assert_only_the_gate_note(self.page(out), canary)
        self.assertIn("workflow_eval.list_runs raised AttributeError", section)
        self.assertIn("run run-2026-01-01-demo — repo", section)

    def test_a_run_declaring_another_runs_directory_as_its_id_never_reads_that_directory(self):
        # The reviewer's normal-path B2 vector: a valid run whose envelope declares the
        # foreign-version run's DIRECTORY as its run_id. The old code read that directory
        # through the declared id and carded the foreign envelope.
        canary = self.plant_foreign_version_canary()
        steer = self.world["evals_dir"] / "run-2026-01-04-steer"
        steer.mkdir()
        (steer / "results.json").write_text(json.dumps(
            dict(self.good_envelope(), run_id=self.world["old_run_dir"].name)))
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        section = _section(page, "evals")
        self.assertNotIn(canary, page)
        self.assertNotIn("<p>run run-2026-01-02-oldversion", section)
        self.assertIn("run run-2026-01-04-steer  (run_id in its envelope: "
                      "run-2026-01-02-oldversion) — repo", section)
        self.assertIn(f"run-2026-01-02-oldversion: not a {self.we().EVAL_VERSION} envelope",
                      section)

    # -- B3: proxy dollars carry the owner's proxy label ---------------------------------------

    def test_proxy_dollars_carry_the_owners_proxy_label_and_no_bare_float_remains(self):
        we = self.we()
        run = self.world["evals_dir"] / "run-2026-01-06-proxy"
        run.mkdir()
        envelope = dict(self.good_envelope(), run_id=run.name)
        envelope["trials"] = [{"trial": "t1", "variant": "v1", "task_id": "task1",
                               "solved": True,
                               "stages": [{"cost": {"basis": "proxy",
                                                    "api_equivalent_usd": 3.75}}]}]
        envelope["totals"] = dict(envelope["totals"],
                                  proxy={"n": 1, "api_equivalent_usd": 7.25})
        (run / "results.json").write_text(json.dumps(envelope))
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "evals")
        beside = f'<span class="label">{db.esc(we.PROXY_LABEL)}</span>'
        for figure in ("3.75", "7.25"):  # the variant's usage, then the run's totals
            self.assertIn(f"${figure} {beside}", section)
            self.assertEqual(section.count(figure), section.count(f"${figure} {beside}"),
                             figure)
        self.assertIn("usage by basis — variant v1", section)
        # no per-basis dict is flattened into a cell any more: no bare float dollar remains.
        self.assertNotIn("&#x27;usd&#x27;", section)
        self.assertNotIn("&#x27;api_equivalent_usd&#x27;", section)
        self.assertNotIn('<span class="label">proxy</span>', section)

    # -- S3: the prefs pre-scan covers exactly the owner's read set ----------------------------

    def test_a_large_policy_journal_and_another_engines_large_file_never_darken_the_reports(self):
        we = self.we()
        prefs = self.world["prefs_dir"]
        line = b'{"kind": "policy.synthetic", "ts": "2026-01-01T00:00:00+00:00"}\n'
        (prefs / we.POLICY_JOURNAL).write_bytes(line * (600 * 1024 // len(line) + 1))
        (prefs / "another-engine-prefs.json").write_bytes(b"E" * (600 * 1024))
        self.assertGreater((prefs / we.POLICY_JOURNAL).stat().st_size, db.MAX_PREFS_FILE_BYTES)
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "evals")
        self.assertNotIn("policy/approval/activation are not read this build", section)
        self.assertIn("none in force.", section)                  # policy_report ran
        self.assertIn("no approvals recorded", section)           # approval_report ran
        self.assertIn("no activation scopes recorded", section)   # activation_report ran
        self.assertNotIn("MAX_PREFS_FILE_BYTES", self.receipt(out)["caps_hit"])

    def test_the_owners_read_set_is_read_from_its_public_constants(self):
        we = self.we()
        self.assertEqual([name for name, _kind in db._prefs_read_set(we)],
                         [we.POLICY_FILE, we.POLICY_HISTORY, we.POLICY_PROPOSALS,
                          we.POLICY_APPROVALS, we.POLICY_ACTIVATION])
        self.assertNotIn(we.POLICY_JOURNAL, [name for name, _kind in db._prefs_read_set(we)])
        # the file the owner's guard polices is never spelled in the engine (its attribute is).
        self.assertNotIn(we.POLICY_FILE, DASHBOARD_PATH.read_text(encoding="utf-8"))

    # -- The unlistable store says so (P2 fix round) ------------------------------------------

    def test_an_unlistable_evals_store_says_it_could_not_be_listed(self):
        # The store cannot be listed at all: nothing in it was vetted, and no run in it was found
        # to be linked, oversized or non-regular -- so the page must not say one was.
        if os.geteuid() == 0:
            self.skipTest("root can list a mode-0 directory")
        _chmod_restorable(self, self.world["evals_dir"], 0)
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "evals")
        self.assertIn("evals store could not be listed (PermissionError)", section)
        self.assertIn("The evals store could not be listed this build (see the notes above), so "
                      "nothing in it was read: no runs table, no run&#x27;s card and no manifest "
                      "count.", section)
        self.assertNotIn("a linked, oversized or non-regular run was found", section)
        self.assertNotIn("excluded from this build", section)
        self.assertNotIn("&lt;store&gt;", section)
        self.assertNotIn("manifests: no manifests directory", section)
        self.assertIn("none in force.", section)  # the namespace's prefs reports still render

    # -- No Python None as text (P2 fix round, PLAN R3) ----------------------------------------

    def test_a_none_in_a_variants_coverage_renders_unknown_never_python_none(self):
        # The fixture's one variant has no reviews, so the owner's `coverage.review_parsed` is
        # None -- a joined-dict cell that used to print Python's own `None`.
        variant = self.we().build_card(self.good_envelope())["variants"][0]
        self.assertIsNone(variant["coverage"]["review_parsed"])
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        section = _section(page, "evals")
        self.assertIn("<td>review_parsed: unknown, tests_oracle: 0.0</td>", section)
        self.assertNotIn("review_parsed: None", section)
        # a page-wide tripwire: Python's own None never stands in for an unknown value.
        self.assertIsNone(re.search(r"\bNone\b", re.sub(r"<[^>]+>", " ", page)))

    def test_a_joined_owner_dict_renders_none_as_unknown_at_every_depth(self):
        self.assertEqual(
            db._owner_value_cell({"b": {"c": None, "d": [1, None]}, "a": None, "e": 2}),
            "a: unknown, b: {c: unknown, d: [1, unknown]}, e: 2")
        # a dict without a None renders exactly as it did before the fix.
        self.assertEqual(db._owner_value_cell({"y": True, "x": 0.5}), "x: 0.5, y: True")


# ---------------------------------------------------------------------------------------------
# Training data readiness panel (T7 item 3).

class TrainingPanelTests(_WorldCase):

    def test_training_switches_render_false_false(self):
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "training")
        self.assertIn("<td>False</td><td>False</td>", section)

    def test_evals_and_training_panel_ids_are_in_the_model(self):
        checkouts = [str(self.world["checkout"])]
        model = db.build_model(self.world["data_home"], checkouts, _opts(self), None)
        ids = [p["id"] for p in model["panels"]]
        self.assertIn("evals", ids)
        self.assertIn("training", ids)

    def test_a_raising_status_call_is_a_note_not_a_crash(self):
        with mock.patch.object(db._mod("training_data"), "status",
                               side_effect=RuntimeError("boom")):
            rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "training")
        self.assertIn("training status unavailable (RuntimeError)", section)

    def test_no_checkouts_training_panel_is_a_plain_note(self):
        model = db.build_model(self.world["data_home"], [], _opts(self), None)
        training = next(p for p in model["panels"] if p["id"] == "training")
        self.assertIn("No checkout discovered", training["blocks"][0]["text"])

    def training_rows(self, model):
        training = next(p for p in model["panels"] if p["id"] == "training")
        table = next(b for b in training["blocks"] if b.get("type") == "table")
        return training, table["rows"]

    def test_the_training_store_path_sits_under_the_pages_data_home(self):
        # P2 fix round S1: the process's own data home (this module's `_DATA_HOME`) differs from
        # the page's (`--data-home`, the synthetic world's), and the row must follow the PAGE.
        self.assertNotEqual(os.path.realpath(_DATA_HOME.name),
                            os.path.realpath(self.world["data_home"]))
        rc, out, _stdout, stderr = self.build()
        self.assertEqual(rc, 0, stderr)
        section = _section(self.page(out), "training")
        self.assertIn(os.fspath(self.world["data_home"]), section)
        self.assertNotIn(_DATA_HOME.name, section)
        checkout = str(self.world["checkout"])
        _training, rows = self.training_rows(
            db.build_model(self.world["data_home"], [checkout], _opts(self), None))
        store_path = Path(rows[0][3])
        self.assertEqual(store_path.parent.parent, Path(self.world["data_home"]))
        self.assertEqual(store_path.parent.name, rd.project_namespace(checkout))
        self.assertEqual(rows[0][4], "env")

    def test_a_data_home_the_build_resolved_itself_keeps_the_owners_own_resolution(self):
        # S1's other half: with no explicit data home the page's IS the process's, and the
        # owner is called with no `env` at all -- its own resolution stands untouched.
        checkout = str(self.world["checkout"])
        opts = _opts(self, data_home_explicit=False)
        with mock.patch.object(db._mod("training_data"), "status",
                               wraps=db._mod("training_data").status) as status:
            training, _rows = self.training_rows(
                db.build_model(self.world["data_home"], [checkout], opts, None))
        status.assert_called_once_with(repo_root=checkout, env=None)
        self.assertFalse(any("page's data home" in note for note in training["notes"]))


# ---------------------------------------------------------------------------------------------
# The plugin install's store (P3 fix round M1, user decision 2026-09-26; amends PLAN D4 and D6).

@contextlib.contextmanager
def _paths_touched_inside(root):
    """Record every absolute path strictly INSIDE `root` (either spelling) that anything stats,
    lists or opens while the context is open -> that list. The root itself is not "inside":
    hashing it for its namespace resolves it, and that is all the plugin root is ever for.
    Relative paths (a `dir_fd` walk) and file descriptors cannot name `root` and are skipped."""
    prefixes = tuple({os.path.abspath(os.fspath(root)) + os.sep,
                      os.path.realpath(os.fspath(root)) + os.sep})
    touched = []

    def wrap(real):
        def spy(*args, **kwargs):
            path = args[0] if args else kwargs.get("path")
            if isinstance(path, (str, os.PathLike)):
                text = os.fspath(path)
                if isinstance(text, str) and text.startswith(prefixes):
                    touched.append(text)
            return real(*args, **kwargs)
        return spy

    with contextlib.ExitStack() as stack:
        for owner, name in ((os, "stat"), (os, "lstat"), (os, "listdir"), (os, "scandir"),
                            (os, "open"), (io, "open"), (builtins, "open")):
            stack.enter_context(mock.patch.object(owner, name, wrap(getattr(owner, name))))
        yield touched


class PluginInstallTests(_WorldCase):
    """The plugin root is a MAPPING-ONLY candidate: its one namespace is looked up by name,
    counted as mapped, labelled "plugin install", and read by the telemetry, journal and evals
    panels alone. It is never a checkout -- no git verb runs in it, no kits dir under it is read,
    it is never a history-join target -- and the attempts panel reads it exactly as it did before
    it was mapped. Every build goes through the real seam, `assemble_build(...,
    plugin_root=...)`."""

    plugin_install = True

    def assemble(self, plugin_root, **extra):
        """One build, git off unless a test says otherwise -> (out_dir, model, receipt, page)."""
        kwargs = {"data_home": self.world["data_home"], "out_dir": self.tmp / "out",
                  "flags": [str(self.world["checkout"])], "git": False,
                  "projects_dir": self.projects, "home": _FAKE_HOME.name,
                  "plugin_root": plugin_root}
        kwargs.update(extra)
        return db.assemble_build(self.world["checkout"], **kwargs)

    def plugin_label(self):
        return f"{os.path.realpath(self.world['plugin_root'])} ({db.PLUGIN_INSTALL_LABEL})"

    def test_telemetry_journal_and_evals_read_the_plugin_install_labelled_as_such(self):
        _out, model, receipt, page = self.assemble(self.world["plugin_root"])
        root = os.path.realpath(self.world["plugin_root"])
        namespace = self.world["plugin_namespace"]
        mapped = {row["namespace"]: row for row in model["classes"]["mapped"]}
        self.assertEqual(sorted(mapped), sorted([self.world["namespace"], namespace]))
        self.assertEqual((mapped[namespace]["kind"], mapped[namespace]["checkout"]),
                         (db.PLUGIN_INSTALL_KIND, root))
        self.assertEqual(mapped[namespace]["stores"], ["telemetry", "journal", "evals"])
        self.assertEqual(model["classes"]["plugin_install"],
                         {"root": root, "namespace": namespace, "state": "mapped"})
        # It counts as mapped, and it leaves the unmapped class (and its store counts).
        self.assertEqual(receipt["classes"]["mapped"], exact(2))
        self.assertEqual(receipt["classes"]["unmapped"], exact(1))
        label = html.escape(self.plugin_label())
        telemetry = _section(page, "telemetry")
        self.assertIn(f"Telemetry for {label}:", telemetry)
        self.assertIn(db.DEMO_PLUGIN_LABEL, telemetry)
        journal = _section(page, "journal")
        self.assertIn(f"Journal digests for {label}:", journal)
        self.assertIn(f"{label}: journal digests by day", journal)
        self.assertIn("$3.21", journal)
        evals = _section(page, "evals")
        self.assertIn(f"Evaluation runs for {label}:", evals)
        self.assertIn(f"Policy, approvals and activation for {label}:", evals)
        self.assertIn(db.DEMO_PLUGIN_RUN, evals)
        for lead in ("No unmapped namespace shows a telemetry store", "No unmapped namespace "
                     "shows a journal store", "No unmapped namespace shows an evals store"):
            self.assertIn(lead, page)
        namespaces = _section(page, "namespaces")
        self.assertIn(label, namespaces)
        self.assertIn("It is never a checkout", namespaces)
        # Only those three panels (and the namespaces census) name it.
        for pid in ("attempts", "scorecard", "kits", "training"):
            self.assertNotIn(db.PLUGIN_INSTALL_LABEL, _section(page, pid))
            self.assertNotIn(root, _section(page, pid))
        self.assertNotIn("CANARY-INBOX-TEXT-DO-NOT-RENDER", page)

    def test_kits_dirs_under_the_plugin_root_are_never_read_or_shown(self):
        root = self.world["plugin_root"]
        planted = {root / ".claude" / "kits" / "plugin-claude-kit-x",
                   root / "tasks" / "kits" / "plugin-codex-kit-y"}
        for kit_dir in planted:
            kit_dir.mkdir(parents=True)
            (kit_dir / "TASKS.md").write_text(db.DEMO_TASKS_MD, encoding="utf-8")
        with _paths_touched_inside(root) as touched:
            _out, model, receipt, page = self.assemble(root)
        self.assertEqual(touched, [])
        everything = page + json.dumps(model) + json.dumps(receipt)
        for kit_dir in planted:
            self.assertNotIn(kit_dir.name, everything)
        # The panels that read kits dirs still read the checkout's own.
        self.assertIn(db.DEMO_KIT, _section(page, "kits"))
        self.assertIn(db.CODEX_DEMO_KIT, _section(page, "kits"))
        self.assertEqual(model["checkouts"], [os.path.realpath(self.world["checkout"])])

    def test_git_never_runs_with_the_plugin_root_as_its_working_directory(self):
        checkout = os.path.realpath(self.world["checkout"])
        calls = []

        def runner(argv, cwd, timeout, name):
            calls.append((list(argv), os.path.realpath(cwd)))
            if argv[:2] == ["git", "rev-parse"]:
                return {"outcome": "ok", "rc": 0, "stdout": f"{checkout}\n"}
            return {"outcome": "ok", "rc": 0,
                    "stdout": f"worktree {checkout}\nHEAD {'a' * 40}\nbranch refs/heads/main\n"}

        _out, model, _receipt, _page = self.assemble(self.world["plugin_root"], git=True,
                                                    runner=runner)
        self.assertEqual(calls, [(["git", "rev-parse", "--show-toplevel"], checkout),
                                 (["git", "worktree", "list", "--porcelain"], checkout)])
        self.assertNotIn(os.path.realpath(self.world["plugin_root"]),
                         [cwd for _argv, cwd in calls])
        self.assertEqual(model["checkouts"], [checkout])
        self.assertEqual(model["classes"]["plugin_install"]["state"], "mapped")

    def test_a_plugin_root_that_is_the_checkout_gives_one_namespace_entry(self):
        _out, model, receipt, page = self.assemble(self.world["checkout"])
        classes = model["classes"]
        self.assertEqual([(row["namespace"], row["kind"]) for row in classes["mapped"]],
                         [(self.world["namespace"], "checkout")])
        self.assertEqual(receipt["classes"]["mapped"], exact(1))
        self.assertEqual(classes["plugin_install"],
                         {"root": os.path.realpath(self.world["checkout"]),
                          "namespace": self.world["namespace"], "state": "checkout"})
        self.assertNotIn(f"({db.PLUGIN_INSTALL_LABEL})", page)
        self.assertEqual(_section(page, "telemetry").count("Telemetry for "), 1)
        self.assertIn("so that checkout", _section(page, "namespaces"))

    def test_a_symlinked_plugin_namespace_is_noted_and_never_followed(self):
        data_home, namespace = self.world["data_home"], self.world["plugin_namespace"]
        elsewhere = self.tmp / "elsewhere-plugin-namespace"
        os.rename(data_home / namespace, elsewhere)
        os.symlink(elsewhere, data_home / namespace)
        _out, model, receipt, page = self.assemble(self.world["plugin_root"])
        classes = model["classes"]
        self.assertEqual([row["namespace"] for row in classes["mapped"]],
                         [self.world["namespace"]])
        self.assertNotIn(namespace, [row["namespace"] for row in classes["unmapped"]])
        self.assertEqual(classes["plugin_install"]["state"], "absent")
        self.assertEqual(receipt["classes"]["mapped"], exact(1))
        skipped = [note for note in model["notes"]
                   if "not a directory without following links" in note]
        self.assertEqual(len(skipped), 1, model["notes"])
        self.assertIn(namespace, skipped[0])
        for never in (db.DEMO_PLUGIN_LABEL, db.DEMO_PLUGIN_RUN, "$3.21", elsewhere.name,
                      f"({db.PLUGIN_INSTALL_LABEL}):"):
            self.assertNotIn(never, page)
        self.assertIn("this data home holds no namespace for it", _section(page, "namespaces"))

    def test_the_attempts_panel_model_is_identical_with_and_without_the_plugin_root(self):
        # A plugin root whose namespace sorts AFTER the unmapped ones: read as a mapped namespace
        # it would come first and, under a lowered read cap, push a different namespace out.
        root = self.tmp / "zz-plugin-root"
        root.mkdir()
        namespace = rd.project_namespace(root)
        self.assertGreater(namespace, db.UNMAPPED_NAMESPACE)
        ledger = al.AttemptLedger(self.world["data_home"] / namespace / al.STORE, "plugin-kit")
        started = ledger.record_started("plugin-run", "T1", "initial", db.SYNTHETIC_MODEL)
        ledger.record_finished("plugin-run", "T1", started, "ok", 0, "synthetic report")
        checkouts = [str(self.world["checkout"])]
        # The third variant cuts the data-home listing before it reaches the plugin namespace
        # (names in order: checkout-, plugin-, tmp… x30, unmapped-, zz-): unlisted, it was never
        # read before M1, so the attempts panel must not read it now either.
        for caps in (None, {"MAX_NAMESPACES_READ": 2}, {"MAX_NAMESPACES_LISTED": 5}):
            with self.subTest(caps=caps), _scandir_in_name_order():
                before = db.build_model(self.world["data_home"], checkouts, _opts(self), caps)
                after = db.build_model(self.world["data_home"], checkouts,
                                       _opts(self, plugin_root=str(root)), caps)
                panels = [next(p for p in model["panels"] if p["id"] == "attempts")
                          for model in (before, after)]
                self.assertEqual(json.dumps(panels[0], sort_keys=True),
                                 json.dumps(panels[1], sort_keys=True))
                # Not vacuous: the plugin root was in effect, and the classes differ.
                self.assertNotIn(namespace, [r["namespace"] for r in before["classes"]["mapped"]])
                self.assertIn(namespace, [r["namespace"] for r in after["classes"]["mapped"]])
                self.assertEqual(after["classes"]["plugin_install"]["state"], "mapped")
                listed = caps != {"MAX_NAMESPACES_LISTED": 5}
                self.assertEqual(namespace in [r["namespace"] for r in
                                               before["classes"]["unmapped"]], listed)
                read = namespace in json.dumps(panels[1])
                # Its ledger is read where it always was (last, by name): the lowered read cap
                # cuts it, and the cut listing never reached it.
                self.assertEqual(read, caps is None)

    def test_a_residue_shaped_plugin_namespace_is_never_opened_by_the_attempts_panel(self):
        # A plugin root named like a tempfile directory whose namespace holds only a ledger was
        # residue before M1 and never opened. The attempts panel still never opens it; the class
        # counts do change, deliberately: a hash match on the plugin root is not a heuristic, so
        # that namespace is the mapped plugin install now, not residue.
        root = self.tmp / "tmpplugin12"  # "tmp" + 8 name characters, as RESIDUE_NAMESPACE_RE wants
        root.mkdir()
        namespace = rd.project_namespace(root)
        self.assertTrue(db.RESIDUE_NAMESPACE_RE.fullmatch(namespace), namespace)
        al.AttemptLedger(self.world["data_home"] / namespace / al.STORE, "plugin-kit") \
            .record_started("plugin-run", "T1", "initial", db.SYNTHETIC_MODEL)
        checkouts = [str(self.world["checkout"])]
        before = db.build_model(self.world["data_home"], checkouts, _opts(self), None)
        after = db.build_model(self.world["data_home"], checkouts,
                               _opts(self, plugin_root=str(root)), None)
        plugin_row = next(r for r in after["classes"]["mapped"] if r["namespace"] == namespace)
        self.assertEqual(plugin_row["listed_as"], "residue")
        for model in (before, after):
            attempts = next(p for p in model["panels"] if p["id"] == "attempts")
            self.assertNotIn(namespace, json.dumps(attempts))
        self.assertEqual(db.class_count(before["classes"], "residue"), exact(31))
        self.assertEqual(db.class_count(after["classes"], "residue"), exact(30))

    def test_every_plugin_install_state_has_exactly_one_sentence(self):
        self.assertEqual(db.PLUGIN_INSTALL_STATES, ("mapped", "checkout", "absent", "unknown"))
        self.assertEqual(set(db._PLUGIN_INSTALL_TEXT), set(db.PLUGIN_INSTALL_STATES))
        block = db._plugin_install_block({"root": "/r", "namespace": "n", "state": "bogus"})
        self.assertEqual(block["parts"][-1], db._PLUGIN_INSTALL_TEXT["unknown"])

    def test_with_no_data_home_the_plugin_install_is_unknown_never_absent(self):
        model = db.build_model(None, [str(self.world["checkout"])],
                               _opts(self, plugin_root=str(self.world["plugin_root"])), None)
        self.assertEqual(model["classes"]["plugin_install"]["state"], "unknown")
        section = _section(db.render_page(model, _FAKE_HOME.name), "namespaces")
        self.assertIn("whether this data home holds its namespace is unknown", section)
        self.assertNotIn("holds no namespace for it", section)

    def test_plugin_root_none_maps_nothing_extra(self):
        _out, model, receipt, page = self.assemble(None)
        classes = model["classes"]
        self.assertNotIn("plugin_install", classes)
        self.assertEqual([row["namespace"] for row in classes["mapped"]],
                         [self.world["namespace"]])
        self.assertIn(self.world["plugin_namespace"],
                      [row["namespace"] for row in classes["unmapped"]])
        self.assertEqual((receipt["classes"]["mapped"], receipt["classes"]["unmapped"]),
                         (exact(1), exact(2)))
        self.assertNotIn(db.PLUGIN_INSTALL_LABEL, page)
        self.assertNotIn(db.DEMO_PLUGIN_LABEL, page)  # its telemetry is counted, never read
        self.assertIn("1 unmapped namespace(s) show a telemetry store in their one shallow "
                      "listing.", page)


# ---------------------------------------------------------------------------------------------
# The skill's relay promise (P3 fix round M2).

class PlainBuildStdoutCanaryTests(_WorldCase):
    """The skill relays the plain `build` stdout and promises every line of it is a count
    (skills/dashboard/SKILL.md, "Context hygiene"): the page and receipt paths, the namespace
    counts, each panel's `summary`, the caps hit and a bare count of notes. It relays each
    summary verbatim, so a summary that interpolated a name read out of a checkout or the data
    home would break that promise silently. Each canary is planted where the model is KNOWN to
    carry it -- the build.json assertion proves it got there -- and must never reach stdout."""

    def plant_canaries(self):
        """Plant every canary -> ({canary: where}, extra build argv). One entry per placement; a
        later panel's canary joins here (T10's is an RSI contract version string)."""
        world, canaries, argv = self.world, {}, []
        target = self.tmp / "canary-kit-target"
        target.mkdir()
        os.symlink(target, world["kits_dir"] / "canarykitdir7f3a")
        canaries["canarykitdir7f3a"] = "a symlinked kit dir under the checkout's .claude/kits"
        stray = world["data_home"] / "canary-namespace-9b1c"
        stray.mkdir()
        (stray / "stray.txt").write_text("not a store\n", encoding="utf-8")
        canaries["canary-namespace-9b1c"] = "an unmapped namespace's name in the data home"
        second = self.tmp / "canary-checkout-c4d2"
        second.mkdir()
        argv += ["--checkout", str(second)]
        canaries["canary-checkout-c4d2"] = "a second checkout's path given through --checkout"
        (world["telemetry_dir"] / "canarysource1a2b").mkdir()
        canaries["canarysource1a2b"] = "an unregistered telemetry source dir's name"
        (world["evals_dir"] / "canary-not-a-run-3c4d").mkdir()
        canaries["canary-not-a-run-3c4d"] = "an evals store entry that is not a run"
        # T10: a contract version read out of a stub engine in the fixture checkout. The page
        # renders it as data and the receipt records it in the rsi panel's note; the rsi summary
        # is fixed words and counts, so stdout never carries it.
        engine = world["checkout"] / "bin"
        engine.mkdir()
        (engine / "recursive_improvement.py").write_text(
            'CANARY_VERSION = "polytropos.rsi-canary-5f2e/1"\n', encoding="utf-8")
        canaries["polytropos.rsi-canary-5f2e/1"] = "an RSI contract version read from a stub engine"
        return canaries, argv

    def test_plain_build_stdout_never_carries_checkout_text(self):
        canaries, argv = self.plant_canaries()
        rc, out, stdout, stderr = self.build("out", *argv)  # plain build: never --json
        self.assertEqual(rc, 0, stderr)
        self.assertTrue(stdout.startswith("page:"), stdout)
        receipt_text = (out / "build.json").read_text(encoding="utf-8")
        for canary, where in canaries.items():
            with self.subTest(canary=canary, where=where):
                self.assertEqual(stdout.count(canary), 0, stdout)
                self.assertGreaterEqual(receipt_text.count(canary), 1)


# ---------------------------------------------------------------------------------------------
# The skill's default git path, through the real runner, at the discovery level (P3 fix round
# S10, as corrected by its follow-up: GUARDRAILS gives every `build` `--no-git`, so no test here
# runs a build with git on).

class GitEnabledDiscoveryTests(unittest.TestCase):
    """The two read-only git verbs the skill's default build runs, run for real:
    `discover_checkouts(<repo>, flags=(<repo>,), git=True)` with no injected runner, so `_git`
    goes through `proc_runner` -- inside a `git init` temp repo, `--checkout <repo>` as the skill
    passes it. No `build` runs. The user's git configuration is isolated (every inherited `GIT_*`
    variable dropped, `GIT_CONFIG_GLOBAL` an empty temp file, `GIT_CONFIG_NOSYSTEM`, the temp
    `HOME`, and a ceiling at the temp root), and a spy that calls through records every git call
    with its result, so the test fails if one ever ran outside that repo -- the real repository
    and its worktrees included."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="dashboard-git-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def test_real_git_discovery_maps_the_temp_repo_as_its_primary_checkout(self):
        if shutil.which("git") is None:
            self.skipTest("git is not installed")
        repo = self.tmp / "repo"
        repo.mkdir()
        real_repo = os.path.realpath(repo)
        empty_config = self.tmp / "empty-gitconfig"
        empty_config.write_text("", encoding="utf-8")
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        env.update({"GIT_CONFIG_GLOBAL": str(empty_config), "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CEILING_DIRECTORIES": os.pathsep.join(
                        sorted({str(self.tmp), os.path.realpath(self.tmp)})),
                    "HOME": _FAKE_HOME.name})
        pr = db._mod("proc_runner")
        real_run = pr.run
        calls = []

        def spy(argv, cwd, **kwargs):
            result = real_run(argv, cwd=cwd, **kwargs)
            calls.append((list(argv), os.path.realpath(cwd), result))
            return result

        with mock.patch.dict(os.environ, env, clear=True):
            init = real_run(["git", "init", "-q"], cwd=repo, timeout=db.GIT_TIMEOUT_SECONDS,
                            name="git init (test fixture)")
            self.assertEqual(init.get("outcome"), "ok", init)
            with mock.patch.object(pr, "run", spy):
                checkouts, notes = db.discover_checkouts(repo, flags=(str(repo),), git=True)
        # The spy saw exactly the two read-only verbs, both run in the temp repo, both succeeding.
        self.assertEqual([(argv, cwd) for argv, cwd, _result in calls],
                         [(["git", "rev-parse", "--show-toplevel"], real_repo),
                          (["git", "worktree", "list", "--porcelain"], real_repo)])
        for _argv, _cwd, result in calls:
            self.assertEqual(result.get("outcome"), "ok", result)
        # The primary checkout is git's own toplevel -- the temp repo -- not a fallback to the
        # working directory, and `git worktree list` yields that repo alone.
        toplevel = calls[0][2]["stdout"].splitlines()[0]
        self.assertEqual(os.path.realpath(toplevel), real_repo)
        self.assertEqual([os.path.realpath(path)
                          for path in db._porcelain_worktrees(calls[1][2]["stdout"])], [real_repo])
        self.assertEqual(checkouts, [real_repo])
        self.assertEqual(notes, [])  # no git-failure note, and no `--no-git` note


# ---------------------------------------------------------------------------------------------
# RSI panel (T10): each checkout's `bin/recursive_improvement.py` read as text and never run, the
# `tasks/kits/recursive-improvement` kit's progress, and the version guard T11 inherits.

class RsiPanelTests(_WorldCase):
    """The engine is parsed, never imported or run (user decision 2026-09-26). Every file is looked
    up without following a link, gated by its own named cap and read bounded; the summary is fixed
    words and counts. A test that needs an engine writes its own stub into the synthetic
    checkout, whose `tasks/kits/` already holds the synthetic RSI kit."""

    VERSION_A = "polytropos.rsi-fixture-a/1"
    VERSION_B = "polytropos.rsi-fixture-b/1"
    STUB = (f'FIXTURE_A_VERSION = "{VERSION_A}"\n'
            f'FIXTURE_B_VERSION = "{VERSION_B}"\n'
            'ARMS = ("A", "B", "C")\n')
    SUMMARY_TEMPLATE = ("engine present in N of N checkout(s), parsed in N, unknown in N; RSI kit "
                        "present in N, unknown in N")

    def engine(self, source):
        """Write `source` (str or bytes) as the synthetic checkout's engine -> its path."""
        path = self.world["checkout"] / "bin" / "recursive_improvement.py"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(source.encode("utf-8") if isinstance(source, str) else source)
        return path

    def status(self, **kwargs):
        return db.rsi_status(self.world["checkout"], **kwargs)

    def model(self, caps=None):
        return db.build_model(self.world["data_home"], [str(self.world["checkout"])],
                              _opts(self), caps)

    @staticmethod
    def rsi(model):
        return next(p for p in model["panels"] if p["id"] == "rsi")

    @staticmethod
    def block(panel, headers):
        return next(b for b in panel["blocks"]
                    if b.get("type") == "table" and b.get("headers") == headers)

    @staticmethod
    def counts_in(panel, lead):
        """The typed count values of the `p` block whose first part is `lead`."""
        parts = next(b["parts"] for b in panel["blocks"]
                     if b.get("type") == "p" and (b.get("parts") or [None])[0] == lead)
        return [part["value"] for part in parts if isinstance(part, dict)]

    def built(self, *extra):
        """One CLI build (`--out-dir`, an empty `--projects-dir`, `--no-git`) -> (the rsi section,
        the page, the receipt text, stdout)."""
        rc, out, stdout, stderr = self.build("out", *extra)
        self.assertEqual(rc, 0, stderr)
        page = self.page(out)
        return _section(page, "rsi"), page, (out / "build.json").read_text(encoding="utf-8"), stdout

    # -- the engine ------------------------------------------------------------------------------

    def test_the_synthetic_checkout_shows_the_absent_engine_line(self):
        self.assertEqual(self.status(), {"present": False})
        section, page, _receipt, _stdout = self.built()
        self.assertIn(db.esc(db.RSI_ENGINE_ABSENT), section)
        self.assertIn("RSI kit present in this checkout", section)
        self.assertNotIn(db.esc(db.RSI_NOTHING_TO_RENDER), section)  # a parsed engine's line only
        self.assertNotIn("Traceback", page)

    def test_a_stub_engines_versions_render_as_data_and_nothing_to_render_is_said(self):
        self.engine(self.STUB)
        status = self.status()
        self.assertEqual((status["present"], status["parsed"]), (True, True))
        self.assertEqual(status["versions"], [["FIXTURE_A_VERSION", self.VERSION_A],
                                              ["FIXTURE_B_VERSION", self.VERSION_B]])
        self.assertEqual(status["known_versions"], [self.VERSION_A, self.VERSION_B])
        self.assertEqual(status["arms"], ["A", "B", "C"])
        self.assertEqual((status["store"], status["store_defined"], status["readers"],
                          status["not_rendered"]), (None, False, [], []))
        section, page, receipt, _stdout = self.built()
        self.assertIn(f"<td>FIXTURE_A_VERSION</td><td>{self.VERSION_A}</td>", section)
        self.assertIn(f"<td>FIXTURE_B_VERSION</td><td>{self.VERSION_B}</td>", section)
        self.assertIn("<p>arms (ARMS): A, B, C</p>", section)
        self.assertIn("STORE: not defined at module scope", section)
        self.assertIn(db.esc(db.RSI_NOTHING_TO_RENDER), section)
        self.assertNotIn(db.esc(db.RSI_RECORDS_NOT_READ), section)
        self.assertIn(self.VERSION_A, receipt)  # the receipt records the versions it read
        self.assertNotIn("Traceback", page)

    def test_a_stub_that_fails_to_parse_is_named_by_type_with_no_message_text(self):
        # T10 A4 replaces "a stub that raises RuntimeError on import": nothing is ever imported.
        source = "def (:\n"
        self.engine(source)
        status = self.status()
        self.assertEqual({key: status[key] for key in ("present", "parsed", "error")},
                         {"present": True, "parsed": False, "error": "SyntaxError"})
        try:
            ast.parse(source, filename="recursive_improvement.py")
        except SyntaxError as exc:
            message, detail = str(exc), exc.msg
        section, page, receipt, stdout = self.built()
        self.assertIn(db.esc(db.RSI_ENGINE_NOT_PARSED), section)
        self.assertIn("bin/recursive_improvement.py could not be parsed (SyntaxError) — nothing "
                      "in it is rendered", section)
        for text in (page, receipt, stdout):
            self.assertNotIn(message, text)
            self.assertNotIn(detail, text)
            self.assertNotIn("Traceback", text)

    def test_a_stub_whose_top_level_would_have_side_effects_is_parsed_never_run(self):
        # T10 A4, the test that proves nothing is executed: were the file run, the marker would
        # exist and the canary would be an exception message.
        marker = self.tmp / "rsi-side-effect-marker"
        canary = "CANARY-RSI-TOP-LEVEL-RAN-7d1e"
        self.engine(self.STUB + f"open({str(marker)!r}, 'w').write('ran')\n"
                                f"raise RuntimeError({canary!r})\n")
        section, page, receipt, stdout = self.built()
        self.assertIn(f"<td>FIXTURE_A_VERSION</td><td>{self.VERSION_A}</td>", section)
        self.assertIn(f"<td>FIXTURE_B_VERSION</td><td>{self.VERSION_B}</td>", section)
        self.assertIn("<p>arms (ARMS): A, B, C</p>", section)
        for text in (page, receipt, stdout):
            self.assertNotIn(canary, text)
            self.assertNotIn("Traceback", text)
        self.assertFalse(os.path.lexists(marker))

    def test_a_store_kind_unknown_to_runtime_data_is_named_and_never_resolved(self):
        self.engine(self.STUB + 'STORE = "not-a-store"\n')
        self.assertEqual(self.status(data_home=self.world["data_home"])["store"],
                         {"value": "not-a-store", "known": False, "path": None, "state": None})
        section, _page, _receipt, _stdout = self.built()
        self.assertIn(f"<p>STORE not-a-store: {db.RSI_STORE_UNKNOWN}</p>", section)
        self.assertIn(db.esc(db.RSI_RECORDS_NOT_READ), section)
        self.assertNotIn(db.esc(db.RSI_NOTHING_TO_RENDER), section)

    def test_a_known_store_resolves_under_the_pages_data_home_scrubbed_with_its_existence(self):
        # The Phase 2 carry-forward: the PAGE's data home, never the process's own.
        self.assertNotEqual(os.path.realpath(_DATA_HOME.name),
                            os.path.realpath(self.world["data_home"]))
        namespace = self.world["namespace"]
        for store, state in (("telemetry", "exists"), ("memory", "does not exist")):
            with self.subTest(store=store):
                self.engine(self.STUB + f'STORE = "{store}"\n')
                section = _section(db.render_page(self.model(), str(self.tmp)), "rsi")
                self.assertIn(db.esc(f"STORE {store}: resolved for this checkout under this "
                                     f"page's data home — ~/world/data-home/{namespace}/{store} — "
                                     f"{state}"), section)
                for spelling in {str(self.tmp), os.path.realpath(self.tmp), _DATA_HOME.name}:
                    self.assertNotIn(spelling, section)
                self.assertIn(db.esc(db.RSI_RECORDS_NOT_READ), section)
        # With no data home at all, nothing is resolved -- never against the process's own.
        self.assertEqual(self.status()["store"],
                         {"value": "memory", "known": True, "path": None,
                          "state": "not resolved — no data home was given"})

    def test_a_symlinked_store_is_noted_and_never_followed(self):
        elsewhere = self.tmp / "elsewhere-memory"
        elsewhere.mkdir()
        (self.world["data_home"] / self.world["namespace"] / "memory").symlink_to(elsewhere)
        self.engine(self.STUB + 'STORE = "memory"\n')
        status = self.status(data_home=self.world["data_home"])
        self.assertEqual(status["store"]["state"],
                         "is a symlink, not a store directory — not followed, not read")
        self.assertTrue(any(note.endswith(f"the memory store its RSI engine names is a symlink in "
                                          f"this page's data home ({self.world['namespace']}/"
                                          f"memory) — not followed, not read")
                            for note in status["notes"]), status["notes"])
        rsi = self.rsi(self.model())
        self.assertTrue(any("the memory store its RSI engine names is a symlink" in note
                            for note in rsi["notes"]), rsi["notes"])
        self.assertNotIn("elsewhere-memory", json.dumps(rsi))

    def test_a_symlinked_engine_is_noted_by_kind_and_never_read(self):
        outside = self.tmp / "outside-engine"
        outside.mkdir()
        target = outside / "recursive_improvement.py"
        target.write_text('LINKED_VERSION = "polytropos.rsi-linked-canary/1"\n', encoding="utf-8")
        (self.world["checkout"] / "bin").mkdir()
        (self.world["checkout"] / "bin" / "recursive_improvement.py").symlink_to(target)
        with mock.patch.object(db, "_read_bounded", wraps=db._read_bounded) as read:
            model = self.model()
            status = self.status()
        self.assertFalse([call for call in read.call_args_list
                          if os.fspath(call.args[0]).endswith("recursive_improvement.py")])
        self.assertEqual({key: status[key] for key in ("present", "parsed", "refused")},
                         {"present": True, "parsed": False, "refused": "a symlink"})
        rsi = self.rsi(model)
        self.assertTrue(any(note.endswith("bin/recursive_improvement.py is a symlink, not a "
                                          "regular file — never read") for note in rsi["notes"]),
                        rsi["notes"])
        page = db.render_page(model, _FAKE_HOME.name)
        self.assertIn(db.esc(db.RSI_ENGINE_NOT_PARSED), _section(page, "rsi"))
        self.assertNotIn("linked-canary", page)

    def test_an_engine_behind_a_symlinked_bin_is_unknown_and_never_looked_at(self):
        outside = self.tmp / "outside-bin"
        outside.mkdir()
        (outside / "recursive_improvement.py").write_text(
            'BEHIND_VERSION = "polytropos.rsi-behind-canary/1"\n', encoding="utf-8")
        (self.world["checkout"] / "bin").symlink_to(outside)
        self.assertEqual(self.status()["present"], None)
        rsi = self.rsi(self.model())
        self.assertTrue(any(note.endswith("bin is a symlink — not followed; "
                                          "bin/recursive_improvement.py is never read through it")
                            for note in rsi["notes"]), rsi["notes"])
        self.assertTrue(rsi["summary"].startswith("engine present in 0 of 1 checkout(s), parsed "
                                                  "in 0, unknown in 1;"), rsi["summary"])
        page = db.render_page(self.model(), _FAKE_HOME.name)
        self.assertIn(db.esc(db.RSI_ENGINE_UNKNOWN), _section(page, "rsi"))
        self.assertNotIn("behind-canary", page)

    def test_an_oversize_engine_gets_a_cap_note_and_is_never_read_or_parsed(self):
        canary = "polytropos.rsi-oversize-canary/1"
        path = self.engine(f'OVERSIZE_VERSION = "{canary}"\n')
        size = path.stat().st_size
        if os.geteuid() != 0:
            _chmod_restorable(self, path, 0)  # an open would fail loudly; the size gate never opens
        with mock.patch.object(db, "MAX_RSI_ENGINE_BYTES", 16):
            section, page, receipt, _stdout = self.built()
        self.assertIn("MAX_RSI_ENGINE_BYTES", json.loads(receipt)["caps_hit"])
        self.assertIn(f"cap MAX_RSI_ENGINE_BYTES (16) reached — ", section)
        self.assertIn(f"bin/recursive_improvement.py is {size} bytes — never read", section)
        self.assertIn(db.esc(db.RSI_ENGINE_NOT_PARSED), section)
        self.assertNotIn("could not be read", section)
        for text in (page, receipt):
            self.assertNotIn(canary, text)

    def test_a_non_utf8_engine_is_named_by_type_and_never_parsed(self):
        self.engine(b'FIXTURE_A_VERSION = "\xff\xfe"\n')
        status = self.status()
        self.assertEqual({key: status[key] for key in ("present", "parsed", "error")},
                         {"present": True, "parsed": False, "error": "UnicodeDecodeError"})
        rsi = self.rsi(self.model())
        self.assertTrue(any(note.endswith("bin/recursive_improvement.py could not be parsed "
                                          "(UnicodeDecodeError) — nothing in it is rendered")
                            for note in rsi["notes"]), rsi["notes"])

    @unittest.skipUnless(hasattr(os, "mkfifo") and hasattr(signal, "SIGALRM"),
                         "needs os.mkfifo and SIGALRM")
    def test_a_fifo_engine_is_named_by_kind_and_never_opened(self):
        (self.world["checkout"] / "bin").mkdir()
        os.mkfifo(self.world["checkout"] / "bin" / "recursive_improvement.py")
        previous = signal.signal(signal.SIGALRM, _on_alarm)
        signal.alarm(10)
        try:
            section, _page, _receipt, _stdout = self.built()
        except _BuildHung:
            self.fail("the build blocked on a FIFO engine for 10 s")
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
        self.assertIn("bin/recursive_improvement.py is a FIFO, not a regular file — never read",
                      section)
        self.assertIn(db.esc(db.RSI_ENGINE_NOT_PARSED), section)

    def test_names_bound_in_forms_not_read_as_data_are_noted_by_name_and_never_rendered(self):
        self.engine(self.STUB
                    + 'JOINED_VERSION = "polytropos.rsi-" + "joined-canary/1"\n'
                      "NUMBER_VERSION = 7\n"
                      'ARMS = ("A", 2)\n'
                      'try:\n    STORE = "attempts"\nexcept ImportError:\n    pass\n'
                      "def read_records():\n    return []\n"
                      'FIXTURE_B_VERSION += "-changed"\n')
        status = self.status()
        self.assertEqual(status["versions"], [["FIXTURE_A_VERSION", self.VERSION_A]])
        self.assertEqual(status["known_versions"], [self.VERSION_A])
        self.assertEqual((status["arms"], status["store"], status["store_defined"]),
                         (None, None, True))
        self.assertEqual(status["readers"], [["read_records", "at the top level"]])
        self.assertEqual(dict(status["not_rendered"]), {
            "JOINED_VERSION": "is not a literal",
            "NUMBER_VERSION": "is not a string",
            "ARMS": "is not a tuple or list of strings",
            "STORE": "is bound inside a block, which only running the file could settle",
            "FIXTURE_B_VERSION": "is bound at the top level in a form not read as data"})
        model = self.model()
        notes = self.rsi(model)["notes"]
        for name, reason in status["not_rendered"]:
            self.assertTrue(any(note.endswith(f"bin/recursive_improvement.py: {name} {reason} — "
                                              f"not rendered") for note in notes), (name, notes))
        page = db.render_page(model, _FAKE_HOME.name)
        section = _section(page, "rsi")
        self.assertIn("arms (ARMS): not read as data — see the notes above", section)
        self.assertIn("STORE: bound, but not read as data — see the notes above", section)
        self.assertIn("<li>read_records — bound at the top level</li>", section)
        self.assertIn(db.esc(db.RSI_RECORDS_NOT_READ), section)
        self.assertNotIn("joined-canary", page)
        self.assertNotIn(self.VERSION_B, page)  # re-bound after its literal: no longer a fact

    def test_the_rendered_constants_and_their_length_are_capped_with_notes(self):
        long_value = "polytropos.rsi-" + "x" * 200 + "/1"
        self.engine(self.STUB + f'LONG_VERSION = "{long_value}"\n')
        with self.subTest(cap="MAX_RSI_CONSTANTS_RENDERED"):
            rsi = self.rsi(self.model({"MAX_RSI_CONSTANTS_RENDERED": 1}))
            table = self.block(rsi, ["constant", "contract version"])
            self.assertEqual(table["rows"], [["FIXTURE_A_VERSION", self.VERSION_A]])
            for noun in ("3 contract version constants", "3 arms"):
                self.assertTrue(any(note.startswith("cap MAX_RSI_CONSTANTS_RENDERED (1) reached")
                                    and noun in note for note in rsi["notes"]),
                                (noun, rsi["notes"]))
            self.assertIn({"type": "p", "parts": ["arms (ARMS): ", "A"]}, rsi["blocks"])
        with self.subTest(cap="MAX_RSI_VALUE_CHARS"):
            model = self.model({"MAX_RSI_VALUE_CHARS": 40})
            rsi = self.rsi(model)
            table = self.block(rsi, ["constant", "contract version"])
            self.assertIn(["LONG_VERSION", db.RSI_WITHHELD], table["rows"])
            self.assertTrue(any(note.startswith("cap MAX_RSI_VALUE_CHARS (40) reached")
                                for note in rsi["notes"]), rsi["notes"])
            self.assertIn("MAX_RSI_VALUE_CHARS",
                          [row["name"] for row in model["caps"] if row["hit"]])
            self.assertNotIn("x" * 200, db.render_page(model, _FAKE_HOME.name))
            self.assertIn(long_value, self.status()["known_versions"])  # data, just not rendered

    def test_a_planted_cap_marker_in_checkout_text_never_marks_a_cap_hit(self):
        # A cap is hit only when `cap_note` fires, never because a note's text -- which may carry
        # a string read out of a checkout -- looks like one. The engine's contract version value
        # rides verbatim into the "read as text" note, so it is the plant.
        planted = "cap MAX_LEDGER_BYTES (0) reached"
        self.engine(f'PLANTED_VERSION = "{planted}"\nARMS = ("A", "B")\n')
        model = self.model({"MAX_RSI_CONSTANTS_RENDERED": 1})
        self.assertTrue(any(planted in note for note in model["notes"]), model["notes"])
        hit = [row["name"] for row in model["caps"] if row["hit"]]
        self.assertNotIn("MAX_LEDGER_BYTES", hit)
        # The genuine hit in the same build still shows.
        self.assertIn("MAX_RSI_CONSTANTS_RENDERED", hit)
        bounds = next(p for p in model["panels"] if p["id"] == "bounds")
        self.assertEqual(bounds["summary"], f"1 of {len(db.CAP_NAMES)} caps hit")
        _section_html, page, receipt, _stdout = self.built()
        self.assertIn(db.esc(planted), page)
        self.assertEqual(json.loads(receipt)["caps_hit"], [])
        self.assertIn("<tr><td>MAX_LEDGER_BYTES</td><td>8388608</td><td>not hit</td></tr>",
                      _section(page, "bounds"))

    # -- the kit ---------------------------------------------------------------------------------

    def test_the_rsi_kit_tables_come_from_the_synthetic_kit(self):
        rsi = self.rsi(self.model())
        self.assertEqual(self.block(rsi, ["id", "title", "status", "model"])["rows"], [
            ["R1", "a synthetic finished RSI task", "done", db.SYNTHETIC_MODEL],
            ["R2", "a synthetic pending RSI task", "pending", db.SYNTHETIC_MODEL],
            ["R3", "a synthetic pending RSI task after it", "pending", db.SYNTHETIC_MODEL]])
        self.assertEqual(tuple(kc.STATUSES), ("pending", "in-progress", "done", "blocked"))
        self.assertEqual(self.counts_in(rsi, "task status counts — "), [2, 0, 1, 0])
        outcomes = self.block(rsi, ["task", "result", "dispatched model", "observed model", "run"])
        self.assertEqual(outcomes["rows"], [["R1", "pass", db.SYNTHETIC_MODEL, None, db.DEMO_RUN]])
        self.assertEqual(self.counts_in(rsi, "actual-use: lines "), [1, 1])
        kits_namespace = rd.project_namespace(self.world["checkout"] / "tasks" / "kits")
        pointer = next(b for b in rsi["blocks"] if b.get("type") == "p"
                       and kits_namespace in (b.get("parts") or ()))
        self.assertIn("not among the namespaces mapped in this build", pointer["parts"])
        section = _section(db.render_page(self.model(), _FAKE_HOME.name), "rsi")
        self.assertIn(f"<td>R1</td><td>pass</td><td>{db.SYNTHETIC_MODEL}</td>"
                      f"<td>{UNKNOWN_SPAN}</td><td>{db.DEMO_RUN}</td>", section)
        # With the kits namespace in the data home, the pointer sends the reader to the Attempts
        # panel instead.
        al.AttemptLedger(self.world["data_home"] / kits_namespace / al.STORE, db.RSI_KIT) \
            .record_started(db.DEMO_RUN, "R1", "initial", db.SYNTHETIC_MODEL)
        pointer = next(b for b in self.rsi(self.model())["blocks"] if b.get("type") == "p"
                       and kits_namespace in (b.get("parts") or ()))
        self.assertIn("mapped in this build; its ledger facts are in the Attempts panel",
                      pointer["parts"])

    def test_the_rsi_tables_are_row_capped_and_the_status_counts_still_cover_every_task(self):
        kit = self.world["rsi_kit_dir"]
        with (kit / "NOTES.md").open("a", encoding="utf-8") as handle:
            for task in ("R2", "R3"):
                handle.write(f"- outcome: {task} model={db.SYNTHETIC_MODEL} attempts=1 "
                             f"result=pass review=none run={db.DEMO_RUN}\n")
        headers = ["task", "result", "dispatched model", "observed model", "run"]
        full = self.rsi(self.model())
        self.assertEqual(len(self.block(full, headers)["rows"]), 3)
        self.assertFalse(any("MAX_RSI_TABLE_ROWS" in note for note in full["notes"]))
        model = self.model({"MAX_RSI_TABLE_ROWS": 1})
        rsi = self.rsi(model)
        self.assertEqual(self.block(rsi, ["id", "title", "status", "model"])["rows"],
                         [["R1", "a synthetic finished RSI task", "done", db.SYNTHETIC_MODEL]])
        self.assertEqual(self.counts_in(rsi, "task status counts — "), [2, 0, 1, 0])  # all three
        self.assertEqual([row[0] for row in self.block(rsi, headers)["rows"]], ["R1"])
        for noun in ("tasks/kits/recursive-improvement/TASKS.md holds 3 tasks; only the first 1",
                     "tasks/kits/recursive-improvement/NOTES.md holds 3 outcome: lines the "
                     "owner reads; only the first 1"):
            self.assertTrue(any(note.startswith("cap MAX_RSI_TABLE_ROWS (1) reached — ")
                                and noun in note for note in rsi["notes"]), (noun, rsi["notes"]))
        self.assertIn("MAX_RSI_TABLE_ROWS", [row["name"] for row in model["caps"] if row["hit"]])
        with mock.patch.object(db, "MAX_RSI_TABLE_ROWS", 1):
            section, page, receipt, _stdout = self.built()
        self.assertEqual(json.loads(receipt)["caps_hit"], ["MAX_RSI_TABLE_ROWS"])
        self.assertIn("<tr><td>MAX_RSI_TABLE_ROWS</td><td>1</td><td>hit</td></tr>",
                      _section(page, "bounds"))
        self.assertNotIn("a synthetic pending RSI task", section)

    def test_oversize_rsi_tasks_md_and_notes_md_get_cap_notes_and_are_never_read(self):
        kit = self.world["rsi_kit_dir"]
        tasks_size = (kit / "TASKS.md").stat().st_size
        notes_size = (kit / "NOTES.md").stat().st_size
        rsi = self.rsi(self.model({"MAX_TASKS_MD_BYTES": 16, "MAX_KIT_NOTES_BYTES": 16}))
        for cap, name, size in (("MAX_TASKS_MD_BYTES", "TASKS.md", tasks_size),
                                ("MAX_KIT_NOTES_BYTES", "NOTES.md", notes_size)):
            self.assertTrue(any(note.startswith(f"cap {cap} (16) reached — ") and note.endswith(
                f"tasks/kits/recursive-improvement/{name} is {size} bytes — never read")
                for note in rsi["notes"]), (cap, rsi["notes"]))
            self.assertIn({"type": "p", "text": f"{name} not read — see the notes above."},
                          rsi["blocks"])
        with mock.patch.object(db, "MAX_TASKS_MD_BYTES", 16), \
                mock.patch.object(db, "MAX_KIT_NOTES_BYTES", 16):
            _section_html, page, receipt, _stdout = self.built()
        hit = json.loads(receipt)["caps_hit"]
        self.assertIn("MAX_TASKS_MD_BYTES", hit)
        self.assertIn("MAX_KIT_NOTES_BYTES", hit)
        self.assertNotIn("a synthetic finished RSI task", _section(page, "rsi"))

    def test_a_symlinked_notes_md_is_noted_and_never_read(self):
        canary = "CANARY-LINKED-RSI-NOTES-2b7c"
        outside = self.tmp / "outside-notes.md"
        outside.write_text(f"- outcome: R1 model=sonnet attempts=1 result=pass run={canary}\n",
                           encoding="utf-8")
        notes_md = self.world["rsi_kit_dir"] / "NOTES.md"
        notes_md.unlink()
        notes_md.symlink_to(outside)
        model = self.model()
        rsi = self.rsi(model)
        self.assertTrue(any(note.endswith("tasks/kits/recursive-improvement/NOTES.md is a symlink, "
                                          "not a regular file — never read")
                            for note in rsi["notes"]), rsi["notes"])
        self.assertIn({"type": "p", "text": "NOTES.md not read — see the notes above."},
                      rsi["blocks"])
        self.assertFalse([b for b in rsi["blocks"] if b.get("type") == "table"
                          and b.get("headers", [None])[0] == "task"])
        self.assertNotIn(canary, _section(db.render_page(model, _FAKE_HOME.name), "rsi"))

    def test_undecodable_rsi_kit_files_are_named_by_type(self):
        kit = self.world["rsi_kit_dir"]
        (kit / "TASKS.md").write_bytes(b"# TASKS \xff\xfe\n")
        (kit / "NOTES.md").write_bytes(b"- outcome: R1 \xff\xfe\n")
        rsi = self.rsi(self.model())
        for suffix in ("tasks/kits/recursive-improvement/TASKS.md could not be parsed "
                       "(UnicodeDecodeError)",
                       "tasks/kits/recursive-improvement/NOTES.md could not be decoded "
                       "(UnicodeDecodeError)"):
            self.assertTrue(any(note.endswith(suffix) for note in rsi["notes"]),
                            (suffix, rsi["notes"]))

    def test_an_absent_rsi_kit_is_said_in_words(self):
        shutil.rmtree(self.world["rsi_kit_dir"])
        rsi = self.rsi(self.model())
        self.assertIn({"type": "p", "text": db.RSI_KIT_ABSENT}, rsi["blocks"])
        self.assertTrue(rsi["summary"].endswith("RSI kit present in 0, unknown in 0"),
                        rsi["summary"])

    # -- the guard, the summary, and what is never probed ----------------------------------------

    def test_rsi_record_kind_names_known_unknown_and_non_records(self):
        known = (self.VERSION_A, self.VERSION_B)
        self.assertEqual(db.rsi_record_kind({"v": self.VERSION_A}, known),
                         ("known", self.VERSION_A))
        newer = "polytropos.rsi-fixture-a/2"
        self.assertEqual(db.rsi_record_kind({"v": newer, "payload": 1}, known), ("unknown", newer))
        for obj in (None, self.VERSION_A, [{"v": self.VERSION_A}], {}, {"v": 7}, {"v": None},
                    {"v": "polytropos.workflow-eval/1"}, {"version": self.VERSION_A}):
            with self.subTest(obj=obj):
                self.assertEqual(db.rsi_record_kind(obj, known), ("not-a-record", None))
        # One known version handed as a bare string is one version, never a substring test.
        self.assertEqual(db.rsi_record_kind({"v": "polytropos.rsi-fixture"}, self.VERSION_A),
                         ("unknown", "polytropos.rsi-fixture"))
        self.assertEqual(db.rsi_record_kind({"v": self.VERSION_A}, None),
                         ("unknown", self.VERSION_A))
        self.engine(self.STUB)
        self.assertEqual(db.rsi_record_kind({"v": self.VERSION_B}, self.status()["known_versions"]),
                         ("known", self.VERSION_B))

    # -- T10 retry (attempt 2 of 2): the red-team's three findings ------------------------------

    @unittest.skipUnless(hasattr(signal, "SIGALRM"), "needs SIGALRM")
    def test_the_parse_is_linear_in_reader_shaped_names(self):
        # R1: the reader de-duplication scanned a growing list, so 40,000 names holding READ took
        # about 10 s where as many plain names take a fraction of one. A set makes each name O(1).
        # The bound fails the old scan several times over; the alarm keeps any regression from
        # hanging the suite.
        count = 40_000
        tree = ast.parse("".join(f"READ_{index} = {index}\n" for index in range(count)))
        previous = signal.signal(signal.SIGALRM, _on_alarm)
        signal.alarm(60)
        try:
            started = time.monotonic()
            facts = db._rsi_parse(tree)
            elapsed = time.monotonic() - started
        except _BuildHung:
            self.fail(f"parsing {count} reader-shaped names ran past 60 s")
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
        self.assertEqual(len(facts["readers"]), count)
        self.assertLess(elapsed, 3.0, f"{count} reader-shaped names took {elapsed:.1f} s")
        # Each `[name, where]` is still kept once, at its first binding.
        facts = db._rsi_parse(ast.parse("READ_A = 1\nREAD_A = 2\ntry:\n    READ_A = 3\n"
                                        "except ImportError:\n    pass\n"))
        self.assertEqual(facts["readers"], [["READ_A", "at the top level"],
                                            ["READ_A", "inside a block"]])

    def test_a_statement_nested_past_the_recursion_limit_is_still_read(self):
        # R1, the walk: `ast.parse` accepts a left-nested chain several times deeper than the
        # interpreter's recursion limit. A recursive walk raised there and the whole engine read
        # as unparsed; the walk keeps its own stack, so the deepest binding is found.
        depth = 3000
        if sys.getrecursionlimit() >= depth:
            self.skipTest("the recursion limit is raised past this test's depth")
        chain = ("x = (READ_DEEP := 0) + "
                 + " + ".join(f"(w{index} := 0)" for index in range(depth)) + "\n")
        self.engine(self.STUB + chain)
        status = self.status()
        self.assertEqual((status["present"], status["parsed"]), (True, True), status.get("notes"))
        self.assertEqual(status["known_versions"], [self.VERSION_A, self.VERSION_B])
        self.assertEqual(status["readers"], [["READ_DEEP", "at the top level"]])

    @unittest.skipUnless(hasattr(signal, "SIGALRM"), "needs SIGALRM")
    def test_rsi_record_kind_never_drains_an_iterator_and_reads_a_sized_collection(self):
        # R2: `known_versions` is a string or a finite, sized collection. A generator or an
        # iterator is no known version at all and is never iterated; a collection is read no
        # further than its own length.
        version = self.VERSION_A

        class EndlessCollection(collections.abc.Collection):
            """Says it holds one item, and would iterate forever if trusted past that."""

            def __len__(self):
                return 1

            def __iter__(self):
                return itertools.repeat(version)

            def __contains__(self, item):
                return item == version

        def slow_and_endless():
            # Endless, but slow, so a regression that drains it holds a few hundred items when
            # the alarm fires rather than filling memory for five seconds.
            while True:
                time.sleep(0.01)
                yield "polytropos.rsi-never/1"

        previous = signal.signal(signal.SIGALRM, _on_alarm)
        signal.alarm(5)
        try:
            endless = db.rsi_record_kind({"v": version}, slow_and_endless())
            capped = db.rsi_record_kind({"v": version}, EndlessCollection())
        except _BuildHung:
            self.fail("rsi_record_kind iterated its known versions without a bound")
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
        self.assertEqual(endless, ("unknown", version))
        self.assertEqual(capped, ("known", version))
        untouched = iter([version])
        self.assertEqual(db.rsi_record_kind({"v": version}, untouched), ("unknown", version))
        self.assertEqual(next(untouched), version)  # nothing was taken from it
        for known in ({"a": version}.values(), {version: 1}.keys(), {version},
                      frozenset([version]), [version], (version,)):
            with self.subTest(known=type(known).__name__):
                self.assertEqual(db.rsi_record_kind({"v": version}, known), ("known", version))

    def test_a_reassigned_name_sits_at_its_final_binding_with_its_final_value(self):
        # R3: running the file leaves A_VERSION holding its last value, set by its last
        # assignment, so its row sits there -- after B_VERSION -- and never shows the first value.
        # A name unsettled twice has its note at the later statement too.
        self.engine('A_VERSION = "polytropos.rsi-a/1"\n'
                    'B_VERSION = "polytropos.rsi-b/1"\n'
                    'A_VERSION = "polytropos.rsi-a/2"\n'
                    "C_VERSION = 1\n"
                    "D_VERSION = 2\n"
                    'C_VERSION = f"polytropos.rsi-c/{3}"\n')
        status = self.status()
        self.assertEqual(status["versions"], [["B_VERSION", "polytropos.rsi-b/1"],
                                              ["A_VERSION", "polytropos.rsi-a/2"]])
        self.assertEqual(status["known_versions"], ["polytropos.rsi-b/1", "polytropos.rsi-a/2"])
        self.assertEqual(status["not_rendered"], [["D_VERSION", "is not a string"],
                                                  ["C_VERSION", "is not a literal"]])
        rsi = self.rsi(self.model())
        self.assertEqual(self.block(rsi, ["constant", "contract version"])["rows"],
                         status["versions"])
        self.assertNotIn("polytropos.rsi-a/1", json.dumps(rsi))

    # -- P4 fix round: M1 (no plan state on the page) and S2 (module-scope walrus bindings) ------

    PLAN_STATE = (r"\bR0\d\b", r"\blanded\b", r"\bmain\b", r"\bPLAN\b", r"\bT1\d\b")

    def test_an_engine_shaped_like_r02s_renders_no_plan_state(self):
        # M1: R02's engine has no STORE, and its readers are named outcome_eligibility_inventory
        # and derived_lineage, which match no reader shape. The page says what the file shows and
        # what the page does -- never a plan task's status, a branch or a PLAN decision.
        self.engine(self.STUB
                    + "def outcome_eligibility_inventory(ledger, captures=()):\n    return {}\n"
                      "def derived_lineage(ledger, captures=()):\n    return []\n")
        status = self.status()
        self.assertEqual((status["store_defined"], status["readers"]), (False, []))
        section, _page, receipt, _stdout = self.built()
        self.assertIn(db.esc(db.RSI_NOTHING_TO_RENDER), section)
        text = html.unescape(re.sub(r"<[^>]+>", " ", section))
        rsi_notes = [note for note in json.loads(receipt)["notes"] if note.startswith("rsi:")]
        rsi_source = next(p["source"] for p in json.loads(receipt)["panels"] if p["id"] == "rsi")
        self.assertIn(rsi_source, text)  # the meta line is part of what the section renders
        # The panel's own lines, source and notes name no plan task, branch or PLAN decision --
        # the synthetic kit's titles carry none of these words either.
        for pattern in (r"\bR02\b", r"\blanded\b", r"\bmain\b", r"\bPLAN\b"):
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, text, re.IGNORECASE), text)
                self.assertFalse([note for note in rsi_notes
                                  if re.search(pattern, note, re.IGNORECASE)], rsi_notes)

    def test_no_rsi_line_names_plan_state(self):
        # M1, held for every fixed line the panel prints: no plan task, no branch, no PLAN
        # decision, no kit task number.
        lines = {name: value for name, value in vars(db).items()
                 if name.startswith("RSI_") and isinstance(value, str)}
        self.assertIn("RSI_NOTHING_TO_RENDER", lines)
        self.assertIn("RSI_RECORDS_NOT_READ", lines)
        for name, value in lines.items():
            for pattern in self.PLAN_STATE:
                with self.subTest(line=name, pattern=pattern):
                    self.assertIsNone(re.search(pattern, value), value)

    def test_a_walrus_in_a_default_unsettles_a_version_and_binds_store(self):
        # S2: a default is evaluated where the def stands, so a walrus there binds at module
        # scope. The version is no longer what its literal said, and STORE is bound but not
        # read as data.
        self.engine(self.STUB
                    + 'def f(x=(FIXTURE_A_VERSION := "polytropos.rsi-fixture-a/2")):\n'
                      "    pass\n"
                      'def g(*, y=(STORE := "attempts")):\n    pass\n')
        status = self.status()
        self.assertEqual(status["versions"], [["FIXTURE_B_VERSION", self.VERSION_B]])
        self.assertEqual(dict(status["not_rendered"]), {
            "FIXTURE_A_VERSION": "is bound at the top level in a form not read as data",
            "STORE": "is bound at the top level in a form not read as data"})
        self.assertEqual((status["store"], status["store_defined"]), (None, True))
        section, page, _receipt, _stdout = self.built()
        self.assertIn("STORE: bound, but not read as data — see the notes above", section)
        self.assertIn(db.esc(db.RSI_RECORDS_NOT_READ), section)
        self.assertNotIn(db.esc(db.RSI_NOTHING_TO_RENDER), section)
        for value in (self.VERSION_A, "polytropos.rsi-fixture-a/2"):
            self.assertNotIn(value, page)

    def test_a_walrus_in_a_decorator_a_class_base_or_an_evaluated_annotation_unsettles(self):
        # S2: each of these is evaluated at module scope when the file runs (checked on this
        # interpreter), so a walrus in one binds the module's name: noted, never rendered.
        literal = 'A_VERSION = "polytropos.rsi-a/1"\n'
        cases = {
            "function decorator": "d = lambda g: g\n@(A_VERSION := d)\ndef f():\n    pass\n",
            "class decorator": "d = lambda c: c\n@(A_VERSION := d)\nclass C:\n    pass\n",
            "class base": "class C((A_VERSION := object)):\n    pass\n",
            "class keyword": "class C(metaclass=(A_VERSION := type)):\n    pass\n",
            "parameter annotation": "def f(x: (A_VERSION := int)):\n    pass\n",
            "return annotation": "def f() -> (A_VERSION := int):\n    pass\n",
            "annotation with a value": "x: (A_VERSION := int) = 1\n",
            "bare annotation": "x: (A_VERSION := int)\n",
            "its own annotation": 'A_VERSION: (A_VERSION := str) = "polytropos.rsi-a/2"\n',
            "bare complex target": "d = {}\nd[(A_VERSION := 1)]: int\n",
            "lambda default": "f = lambda x=(A_VERSION := 1): x\n",
            "misplaced __future__ import": ("x = 1\nfrom __future__ import annotations\n"
                                            "def f(a: (A_VERSION := int)):\n    pass\n"),
        }
        for label, source in cases.items():
            with self.subTest(position=label):
                facts = db._rsi_parse(ast.parse(literal + source))
                self.assertEqual(facts["versions"], [])
                self.assertEqual(facts["not_rendered"], [
                    ["A_VERSION", "is bound at the top level in a form not read as data"]])

    def test_a_walrus_where_python_never_binds_it_leaves_the_version_settled(self):
        # S2's other edge. Postponed annotations are never evaluated, and a type-parameter bound
        # is evaluated lazily in its own scope: the compiler rejects a walrus in either (checked
        # here on this test's own snippets, never on checkout code), so it can never bind. A
        # class body is the class's own scope. None of them unsettles the version.
        literal = 'A_VERSION = "polytropos.rsi-a/1"\n'
        never_compiles = {
            "postponed annotation": ('"""doc"""\nfrom __future__ import annotations\n' + literal
                                     + "def f(x: (A_VERSION := int)):\n    pass\n"),
            "type-parameter bound": literal + "def f[T: (A_VERSION := int)]():\n    pass\n",
        }
        for label, source in never_compiles.items():
            with self.subTest(position=label):
                with self.assertRaises(SyntaxError):
                    compile(source, "<the test's own snippet>", "exec")
                facts = db._rsi_parse(ast.parse(source))
                self.assertEqual(facts["versions"], [["A_VERSION", "polytropos.rsi-a/1"]])
                self.assertEqual(facts["not_rendered"], [])
        facts = db._rsi_parse(ast.parse(literal + "class C:\n    (A_VERSION := 2)\n"))
        self.assertEqual(facts["versions"], [["A_VERSION", "polytropos.rsi-a/1"]])

    def test_the_rsi_summary_is_fixed_words_and_counts_only(self):
        # P3 review M2 / T10 A3: `summary_lines` relays the summary verbatim to the session.
        arm = "ARM-CANARY-9c1d"
        self.engine(self.STUB.replace('"C")', f'"{arm}")') + 'STORE = "telemetry"\n')
        section, _page, receipt, stdout = self.built()
        summary = next(p["summary"] for p in json.loads(receipt)["panels"] if p["id"] == "rsi")
        for text in (self.VERSION_A, self.VERSION_B, "FIXTURE_A_VERSION", arm, "telemetry",
                     "a synthetic finished RSI task", "R1", "recursive", "/", "~",
                     "Error"):
            self.assertNotIn(text, summary)
        self.assertEqual(re.sub(r"\d+", "N", summary), self.SUMMARY_TEMPLATE)
        self.assertEqual(summary, "engine present in 1 of 1 checkout(s), parsed in 1, unknown in "
                                  "0; RSI kit present in 1, unknown in 0")
        self.assertIn(f"  {'rsi':<11} {summary}", stdout.splitlines())
        self.assertIn(arm, section)  # on the page, as data

    def test_the_plugin_root_is_never_probed_for_an_rsi_engine_or_kit(self):
        # T10 A7: the plugin install is not a checkout, so nothing under its root is looked for.
        root = self.world["plugin_root"]
        canary, title = "polytropos.rsi-plugin-root-canary/1", "CANARY-PLUGIN-RSI-TITLE-4e5f"
        (root / "bin").mkdir()
        (root / "bin" / "recursive_improvement.py").write_text(f'PLUGIN_VERSION = "{canary}"\n',
                                                               encoding="utf-8")
        kit = root / "tasks" / "kits" / db.RSI_KIT
        kit.mkdir(parents=True)
        (kit / "TASKS.md").write_text(f"# TASKS\n\n### PR1 — {title}\n- status: done\n"
                                      f"- model: sonnet\n", encoding="utf-8")
        with _paths_touched_inside(root) as touched:
            _out, model, receipt, page = db.assemble_build(
                self.world["checkout"], data_home=self.world["data_home"],
                out_dir=self.tmp / "out", flags=[str(self.world["checkout"])], git=False,
                projects_dir=self.projects, home=_FAKE_HOME.name, plugin_root=root)
        self.assertEqual(touched, [])
        everything = page + json.dumps(model) + json.dumps(receipt)
        self.assertNotIn(canary, everything)
        self.assertNotIn(title, everything)
        self.assertEqual(self.rsi(model)["summary"],
                         "engine present in 0 of 1 checkout(s), parsed in 0, unknown in 0; RSI "
                         "kit present in 1, unknown in 0")

    def test_no_checkout_is_a_plain_sentence_and_a_count_free_summary(self):
        rsi = self.rsi(db.build_model(self.world["data_home"], [], _opts(self), None))
        self.assertEqual(rsi["summary"], "no checkout discovered — nothing probed")
        self.assertEqual(rsi["blocks"], [{"type": "p", "text": "No checkout discovered — no RSI "
                                                               "engine or kit to look for."}])


class RsiSourceTests(unittest.TestCase):
    """T10 A1 and A5, read off the engine's own source: nothing in it can import or run a
    checkout's code, and the RSI contract prefix is spelled once."""

    def test_no_checkout_code_is_imported_or_run_by_the_engine(self):
        source = DASHBOARD_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}

        def calls_in(node):
            return {id(call) for call in ast.walk(node) if isinstance(call, ast.Call)}

        in_load, in_mod = calls_in(functions["_load"]), calls_in(functions["_mod"])
        offenders, loaded = [], []
        for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
            func = call.func
            if isinstance(func, ast.Name) and func.id in ("exec", "eval", "compile", "__import__"):
                offenders.append(func.id)
            if isinstance(func, ast.Attribute) and func.attr in (
                    "exec_module", "spec_from_file_location", "module_from_spec",
                    "import_module", "run_path", "run_module", "reload") \
                    and id(call) not in in_load:
                offenders.append(func.attr)
            if isinstance(func, ast.Name) and func.id in ("_mod", "_load") \
                    and id(call) not in in_mod:
                # Every other loader call names its owner as a literal, so it can be read here.
                self.assertTrue(call.args and isinstance(call.args[0], ast.Constant),
                                ast.dump(call))
                loaded.append(call.args[0].value)
        self.assertEqual(offenders, [])
        # The one module loader reads siblings from PLUGIN_ROOT's own bin/, and nothing asks it
        # for the RSI engine.
        self.assertIn('PLUGIN_ROOT / "bin"', ast.get_source_segment(source, functions["_load"]))
        self.assertIn("kit_contract", loaded)
        self.assertNotIn("recursive_improvement", loaded)
        self.assertNotIn("runpy", source)

    def test_the_rsi_contract_prefix_is_spelled_on_one_line_only(self):
        lines = [line for line in DASHBOARD_PATH.read_text(encoding="utf-8").splitlines()
                 if re.search(r"polytropos.rsi-", line)]
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("startswith(", lines[0])


if __name__ == "__main__":
    unittest.main()
