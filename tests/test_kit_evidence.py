"""`kit_contract.py accept` (kit-preflight T7, PLAN B1/D6/R10): the acceptance an interactive
kit's `outcome:` line already states, recorded in the attempt ledger outside the tree.

Every fixture is a temp kit under `<tmp>/.claude/kits/fx` in a real `git init` repo with one
commit (so `workspace_fingerprint` returns a digest), a temp `--attempt-store`, and a temp HOME.
No committed kit is accepted against and no real store is touched.

`DriftTests` cover `kit_contract.py drift` (kit-preflight T8, PLAN B3/D7/R9): every verify goes
through an injected runner -- or, for the command line, a stand-in `_ep()` whose
`verify_runner` never builds a sandbox -- so no test here executes a real verify command.
"""

import hashlib
import inspect
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
KC = ROOT / "bin" / "kit_contract.py"


def _fresh_run_ids(n):
    """Distinct ids from the production `generate_run_id()`, as the loop would stamp them.

    The CLI cannot be handed a clock (a settable clock in production would be a backfill
    door), so every test that drives `accept` as a process uses ids dated now; the guard's
    today-or-yesterday window absorbs a run that crosses UTC midnight.
    """
    sys.path.insert(0, str(ROOT / "bin"))
    try:
        import kit_contract as _kc
    finally:
        sys.path.pop(0)
    ids = set()
    while len(ids) < n:
        ids.add(_kc.generate_run_id())
    return sorted(ids)


RUN1, RUN2, RUN3, RUN4 = _fresh_run_ids(4)
_TASK_RUN = {"T1": RUN1, "T2": RUN2}


def _block(tid, status="done", depends=()):
    dep = ", ".join(depends) if depends else "(none)"
    return (f"### {tid} — Task {tid}\n- id: {tid}\n- title: task {tid}\n- status: {status}\n"
            f"- model: haiku\n- depends: {dep}\n\n**Brief.** Do {tid}.\n\n"
            f"**Acceptance.** {tid} holds.\n\n**Verify.**\n\n```bash\ntrue\n```\n")


def _outcome(tid, result="pass", run=None):
    """An outcome line stamped with a run id: T1 -> RUN1, T2 -> RUN2 unless `run` is given.

    `run=False` leaves the pair out, the shape of a line written before `run=` existed."""
    run = _TASK_RUN.get(tid, RUN1) if run is None else run
    tail = f" run={run}" if run else ""
    return f"- outcome: {tid} model=haiku attempts=1 result={result} review=none{tail}\n"


class AcceptTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="polytropos-accept-")
        self.root = Path(self._tmp.name).resolve()
        self.kit = self.root / ".claude" / "kits" / "fx"
        self.kit.mkdir(parents=True)
        self.store = self.root / "store"
        self.home = self.root / "home"
        self.home.mkdir()
        self.git("init", "-q")
        (self.root / "seed.txt").write_text("seed\n")
        self.git("add", "seed.txt")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "seed")

    def tearDown(self):
        self._tmp.cleanup()

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def write_kit(self, t1="done", t2="done", notes=""):
        (self.kit / "TASKS.md").write_text(
            "# fx — tasks\n\n## Phase 1 — fixtures\n\n"
            + _block("T1", t1) + "\n" + _block("T2", t2, depends=["T1"]))
        (self.kit / "NOTES.md").write_text("# notes\n" + notes)

    def kit_bytes(self):
        return {str(p.relative_to(self.kit)): p.read_bytes()
                for p in sorted(self.kit.rglob("*")) if p.is_file()}

    def run_kc(self, *args):
        return subprocess.run(
            [sys.executable, str(KC), *args], capture_output=True, text=True,
            env=dict(os.environ, HOME=str(self.home)), cwd=str(self.root), timeout=120)

    def accept(self, task, run, *extra):
        return self.run_kc("accept", "--kit", str(self.kit), "--task", task, "--run", run,
                           "--attempt-store", str(self.store), *extra)

    def freshness(self):
        return self.run_kc("freshness", "--kit", str(self.kit),
                           "--attempt-store", str(self.store))

    def both_outcomes(self):
        self.write_kit(notes=_outcome("T1") + _outcome("T2"))

    def append_notes(self, text):
        with open(self.kit / "NOTES.md", "a") as fh:
            fh.write(text)

    def test_accepting_both_reads_fresh_and_prints_one_line(self):
        self.both_outcomes()
        p1 = self.accept("T1", RUN1)
        self.assertEqual(p1.returncode, 0, p1.stderr)
        self.assertRegex(p1.stdout.strip(), r"^accept: T1 result=pass artifact=[0-9a-f]{12} "
                                            r"upstream=none$")
        p2 = self.accept("T2", RUN2)
        self.assertEqual(p2.returncode, 0, p2.stderr)
        self.assertEqual(len(p2.stdout.strip().splitlines()), 1)
        self.assertRegex(p2.stdout, r"upstream=T1:[0-9a-f]{12}")
        f = self.freshness()
        self.assertEqual(f.returncode, 0, f.stdout + f.stderr)
        self.assertIn("T2 fresh", f.stdout)

    def test_a_changed_tree_then_reaccepting_upstream_makes_the_dependant_stale(self):
        self.both_outcomes()
        self.accept("T1", RUN1)
        self.accept("T2", RUN2)
        (self.root / "new.txt").write_text("changed\n")
        self.git("add", "new.txt")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "more")
        self.append_notes(_outcome("T1", run=RUN3))  # the loop stamps a fresh line per run
        again = self.accept("T1", RUN3)
        self.assertEqual(again.returncode, 0, again.stderr)
        f = self.freshness()
        self.assertEqual(f.returncode, 1, f.stdout + f.stderr)
        self.assertIn("T2 stale", f.stdout)

    def test_a_task_that_is_not_done_is_refused(self):
        self.write_kit(t1="pending", notes=_outcome("T1"))
        p = self.accept("T1", RUN1)
        self.assertEqual(p.returncode, 2)
        self.assertIn("not done", p.stderr)
        self.assertFalse(self.store.exists())

    def test_done_without_an_outcome_line_is_refused(self):
        self.write_kit()
        p = self.accept("T1", RUN1)
        self.assertEqual(p.returncode, 2)
        self.assertIn("write the outcome line first", p.stderr)

    def test_a_non_passing_outcome_is_refused(self):
        self.write_kit(notes=_outcome("T1", "blocked"))
        p = self.accept("T1", RUN1)
        self.assertEqual(p.returncode, 2)
        self.assertIn("write the outcome line first", p.stderr)

    def test_retry_pass_and_escalated_pass_are_accepted(self):
        for result in ("retry-pass", "escalated-pass"):
            with self.subTest(result=result):
                self.write_kit(notes=_outcome("T1", result))
                p = self.accept("T1", RUN1)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertIn(f"result={result}", p.stdout)

    def test_no_backfill_flag_exists(self):
        self.both_outcomes()
        for flag, val in (("--artifact", "abc"), ("--upstream", "T1:abc"), ("--at", "2026-01-01"),
                          ("--from-notes", "")):
            with self.subTest(flag=flag):
                p = self.accept("T1", RUN1, flag, val) if val else self.accept("T1", RUN1, flag)
                self.assertEqual(p.returncode, 2)
                self.assertIn("unrecognized arguments", p.stderr)
        self.assertFalse(self.store.exists())

    def test_a_malformed_run_id_or_unknown_task_is_refused(self):
        self.both_outcomes()
        self.assertEqual(self.accept("T1", "not-a-run").returncode, 2)
        self.assertEqual(self.accept("T9", RUN1).returncode, 2)
        self.assertFalse(self.store.exists())

    def test_the_kit_dir_is_never_written_and_the_ledger_lives_in_the_store(self):
        self.both_outcomes()
        before = self.kit_bytes()
        names_before = sorted(p.name for p in (self.root / ".claude").rglob("*"))
        for args in (("T1", RUN1), ("T2", RUN2), ("T1", RUN3), ("T1", "bad")):
            self.accept(*args)
            self.freshness()
            self.assertEqual(self.kit_bytes(), before)
        self.assertEqual(sorted(p.name for p in (self.root / ".claude").rglob("*")), names_before)
        self.assertTrue(any(p.is_file() for p in self.store.rglob("*")))

    def test_the_committed_kit_still_reads_unknown_for_upstream_tasks(self):
        # Live-tree, read-only. Against an empty temp store this proves only that `freshness`
        # runs, the kit parses, and tasks with upstream read `unknown` when no acceptance is
        # recorded; it does not prove no backfill path exists.
        kit = ROOT / ".claude" / "kits" / "sdd-docs-refresh"
        if not kit.exists():
            self.skipTest("committed kit absent")
        p = self.run_kc("freshness", "--kit", str(kit), "--attempt-store",
                        str(self.root / "empty-store"))
        self.assertEqual(p.returncode, 0, p.stderr)
        lines = [ln for ln in p.stdout.splitlines() if ln.startswith("evidence: T")]
        self.assertTrue(lines, p.stdout)
        with_upstream = [ln for ln in lines if "no upstream task" not in ln]
        self.assertTrue(with_upstream, p.stdout)
        for ln in with_upstream:
            self.assertIn(" unknown", ln)

    def _stored(self):
        return "".join(p.read_text() for p in self.store.rglob("*") if p.is_file())

    def test_a_secret_shaped_note_is_stored_redacted_and_reported_by_kind(self):
        self.both_outcomes()
        secret = "ghp_abcdefghijklmnopqrstuvwxyz012345"
        p = self.accept("T1", RUN1, "--note", f"token {secret} ok")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn(secret, self._stored())
        self.assertIn("[redacted:github-token]", self._stored())
        self.assertIn("github-token", p.stderr)
        self.assertNotIn(secret, p.stdout + p.stderr)

    def test_an_overlong_note_is_stored_bounded(self):
        self.both_outcomes()
        p = self.accept("T1", RUN1, "--note", "x" * 5000)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("x" * 1000, self._stored())
        self.assertIn("truncated", self._stored())

    def _assert_clean_refusal(self, p):
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertNotIn("Traceback", p.stderr)
        self.assertTrue(p.stderr.startswith("accept: "), p.stderr)

    def test_notes_md_that_is_a_directory_exits_2_cleanly(self):
        self.write_kit()
        (self.kit / "NOTES.md").unlink()
        (self.kit / "NOTES.md").mkdir()
        self._assert_clean_refusal(self.accept("T1", RUN1))
        self.assertFalse(self.store.exists())

    def test_binary_notes_md_exits_2_with_a_readable_message(self):
        self.write_kit()
        (self.kit / "NOTES.md").write_bytes(b"\xff\xfe\x00\x80")
        p = self.accept("T1", RUN1)
        self._assert_clean_refusal(p)
        self.assertIn("not UTF-8", p.stderr)
        self.assertFalse(self.store.exists())

    def test_an_unwritable_store_parent_exits_2_cleanly(self):
        self.both_outcomes()
        parent = self.root / "ro"
        parent.mkdir()
        parent.chmod(0o500)
        try:
            if os.access(parent, os.W_OK):
                self.skipTest("running as a user who ignores directory modes")
            p = self.run_kc("accept", "--kit", str(self.kit), "--task", "T1", "--run", RUN1,
                            "--attempt-store", str(parent / "store"))
            self._assert_clean_refusal(p)
            self.assertEqual(list(parent.iterdir()), [])
        finally:
            parent.chmod(0o700)

    def test_a_store_that_is_a_regular_file_exits_2_cleanly(self):
        self.both_outcomes()
        self.store.write_text("not a dir\n")
        self._assert_clean_refusal(self.accept("T1", RUN1))
        self.assertEqual(self.store.read_text(), "not a dir\n")

    def test_run_ids_must_carry_a_real_calendar_date(self):
        self.both_outcomes()
        for bad in ("2026-13-45-0000", "9999-99-99-ffff", "2026-02-30-abcd"):
            with self.subTest(run=bad):
                self.assertEqual(self.accept("T1", bad).returncode, 2)
        self.assertFalse(self.store.exists())
        # a real calendar date passes the shape rule; an old one then fails the window rule,
        # with the window's reason rather than the shape's
        self.write_kit(notes=_outcome("T1", run="2026-02-28-abcd"))
        old = self.accept("T1", "2026-02-28-abcd")
        self.assertEqual(old.returncode, 2, old.stdout + old.stderr)
        self.assertNotIn("is not a run id", old.stderr)
        self.assertIn("2026-02-28", old.stderr)
        self.assertFalse(self.store.exists())
        self.both_outcomes()
        self.assertEqual(self.accept("T1", RUN1).returncode, 0)


class UnsoundGateGraphOrderTests(unittest.TestCase):
    """Phase 2 finding 4: a duplicate id plus an empty fence is a graph error (exit 2) in
    every driver, not an exit-3 analyze refusal."""

    def test_duplicate_id_with_an_empty_fence_exits_2_in_claude_and_cursor(self):
        for driver in ("claude", "cursor"):
            with self.subTest(driver=driver), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                kit = root / ".claude" / "kits" / "fx"
                kit.mkdir(parents=True)
                (kit / "TASKS.md").write_text(
                    "# fx — tasks\n\n## Phase 1 — fixtures\n\n"
                    + _block("T1", "pending") + "\n"
                    + _block("T1", "pending").replace("\ntrue\n", "\n\n"))
                (kit / "PLAN.md").write_text("# plan\n")
                (root / "home").mkdir()
                proc = subprocess.run(
                    [sys.executable, str(ROOT / "bin" / f"{driver}_execute.py"), "run",
                     "--kit", str(kit), "--dry-run", "--attempt-store", str(root / "store")],
                    capture_output=True, text=True, cwd=str(root), timeout=120,
                    env=dict(os.environ, HOME=str(root / "home")))
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                self.assertNotIn("verify-unparseable", proc.stderr)


class AcceptTestAuthorTests(unittest.TestCase):
    """Brief-derived gaps (T7 test-author): D6 "a projection takes no claim", GUARDRAILS
    "accept takes no claim, writes nothing in the tree ... no --artifact/--upstream/--at/
    --from-notes", B1 "refuses to backfill", R10 ordering, and finding 4's red-proof."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="polytropos-accept-ta-")
        self.root = Path(self._tmp.name).resolve()
        self.kit = self.root / ".claude" / "kits" / "fx"
        self.kit.mkdir(parents=True)
        self.store = self.root / "store"
        self.home = self.root / "home"
        self.home.mkdir()
        self.git("init", "-q")
        (self.root / "seed.txt").write_text("seed\n")
        self.git("add", "seed.txt")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "seed")

    def tearDown(self):
        self._tmp.cleanup()

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def write_kit(self, notes, t1="done", t2="done"):
        (self.kit / "TASKS.md").write_text(
            "# fx — tasks\n\n## Phase 1 — fixtures\n\n"
            + _block("T1", t1) + "\n" + _block("T2", t2, depends=["T1"]))
        (self.kit / "NOTES.md").write_text("# notes\n" + notes)

    def run_kc(self, *args):
        return subprocess.run(
            [sys.executable, str(KC), *args], capture_output=True, text=True,
            env=dict(os.environ, HOME=str(self.home)), cwd=str(self.root), timeout=120)

    def accept(self, task, run, *extra):
        return self.run_kc("accept", "--kit", str(self.kit), "--task", task, "--run", run,
                           "--attempt-store", str(self.store), *extra)

    def append_notes(self, text):
        with open(self.kit / "NOTES.md", "a") as fh:
            fh.write(text)

    def events(self):
        out = []
        for f in sorted(self.store.rglob("*.jsonl")):
            for ln in f.read_text().splitlines():
                if ln.strip():
                    out.append(json.loads(ln))
        return out

    def snapshot(self, skip):
        snap = {}
        for p in sorted(self.root.rglob("*")):
            rel = p.relative_to(self.root)
            if p.is_file() and not any(part in skip for part in rel.parts):
                snap[str(rel)] = p.read_bytes()
        return snap

    # -- takes no claim ------------------------------------------------------------------------

    def test_accept_leaves_no_claim_or_open_attempt_and_a_driver_can_still_claim(self):
        self.write_kit(_outcome("T1") + _outcome("T2"))
        self.assertEqual(self.accept("T1", RUN1).returncode, 0)
        self.assertEqual(self.accept("T2", RUN2).returncode, 0)
        kinds = {e["kind"] for e in self.events()}
        self.assertEqual(kinds, {"task.projected"}, kinds)
        self.assertEqual(list(self.store.rglob("*.lock")), [])
        sys.path.insert(0, str(ROOT / "bin"))
        try:
            import kit_contract as kc
        finally:
            sys.path.pop(0)
        ledger = kc.open_ledger(self.kit, store=str(self.store))
        self.assertEqual(ledger.open_attempts(), [])
        self.assertIsNone(ledger.holder("T1"))
        ledger.claim("T1", "2026-10-24-dddd")  # raises ClaimHeld if accept left a claim
        self.assertEqual(ledger.holder("T1")["run"], "2026-10-24-dddd")

    # -- re-accepting replaces ---------------------------------------------------------------

    def test_reaccepting_makes_the_latest_acceptance_the_only_one_that_counts(self):
        self.write_kit(_outcome("T1") + _outcome("T2"))
        self.accept("T1", RUN1)
        self.accept("T2", RUN2)
        first = [e for e in self.events() if e["task"] == "T1"][-1]
        (self.root / "new.txt").write_text("x\n")
        self.git("add", "new.txt")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "more")
        self.append_notes(_outcome("T1", run=RUN3))
        self.assertEqual(self.accept("T1", RUN3).returncode, 0)
        done = [e for e in self.events() if e["task"] == "T1" and e["kind"] == "task.projected"]
        self.assertEqual([e["run"] for e in done], [RUN1, RUN3])
        self.assertNotEqual(done[0]["artifact"], done[1]["artifact"])
        f = self.run_kc("freshness", "--kit", str(self.kit), "--attempt-store", str(self.store))
        self.assertIn("T2 stale", f.stdout)
        # accepting the dependant again on the same tree restores fresh: latest wins, no stacking
        self.append_notes(_outcome("T2", run=RUN4))
        self.assertEqual(self.accept("T2", RUN4).returncode, 0)
        f = self.run_kc("freshness", "--kit", str(self.kit), "--attempt-store", str(self.store))
        self.assertIn("T2 fresh", f.stdout, f.stdout)
        self.assertNotEqual(first["artifact"], done[1]["artifact"])

    # -- writes nothing in the tree ----------------------------------------------------------

    def test_nothing_under_tmp_changes_except_the_store(self):
        self.write_kit(_outcome("T1") + _outcome("T2") + _outcome("T1", run=RUN3))
        before = self.snapshot(skip={".git", "store"})
        for args in (("T1", RUN1), ("T2", RUN2), ("T1", RUN3), ("T1", "bad"), ("T9", RUN1)):
            self.accept(*args)
        self.assertEqual(self.snapshot(skip={".git", "store"}), before)
        self.assertEqual(self.accept("T1", RUN3).returncode, 0)
        self.assertEqual(self.snapshot(skip={".git", "store"}), before)

    # -- flags ---------------------------------------------------------------------------------

    def test_every_abbreviation_of_a_forbidden_flag_is_rejected(self):
        self.write_kit(_outcome("T1") + _outcome("T2"))
        flags = ["--art", "--arti", "--artifa", "--artifact", "--up", "--ups", "--upstr",
                 "--upstream", "--at", "--fro", "--from", "--from-", "--from-n",
                 "--from-notes"]
        for flag in flags:
            with self.subTest(flag=flag):
                p = self.accept("T1", RUN1, f"{flag}=abc")
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                p = self.accept("T1", RUN1, flag, "abc")
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertFalse(self.store.exists())

    # -- outcome-line reading ----------------------------------------------------------------

    def test_a_quoted_outcome_line_is_not_the_passing_result(self):
        quoted = [
            "`- outcome: T1 model=haiku attempts=1 result=pass review=none`\n",
            "* outcome: T1 model=haiku attempts=1 result=pass review=none\n",
            "> outcome: T1 model=haiku attempts=1 result=pass review=none\n",
            "The line was outcome: T1 model=haiku attempts=1 result=pass review=none\n",
            "see `outcome: T1 result=pass` for the format\n",
        ]
        for text in quoted:
            with self.subTest(text=text):
                self.write_kit(text)
                p = self.accept("T1", RUN1)
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertIn("write the outcome line first", p.stderr)
        self.assertFalse(self.store.exists())

    def test_the_latest_outcome_line_for_the_task_wins(self):
        self.write_kit(_outcome("T1", "blocked") + _outcome("T2") + _outcome("T1", "retry-pass"))
        p = self.accept("T1", RUN1)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("result=retry-pass", p.stdout)
        ev = [e for e in self.events() if e["task"] == "T1"][-1]
        self.assertEqual(ev["result"], "retry-pass")

    def test_a_blocked_outcome_after_a_pass_refuses(self):
        self.write_kit(_outcome("T1") + _outcome("T1", "blocked"))
        p = self.accept("T1", RUN1)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertFalse(self.store.exists())

    def test_another_tasks_pass_line_does_not_accept_this_one(self):
        self.write_kit(_outcome("T2"))
        p = self.accept("T1", RUN1)
        self.assertEqual(p.returncode, 2)
        self.assertFalse(self.store.exists())

    # -- run id --------------------------------------------------------------------------------

    def test_run_id_shape_is_enforced_exactly(self):
        self.write_kit(_outcome("T1"))
        for bad in ("2026-10-24-AAAA", "2026-10-24-aaa", "2026-10-24-aaaaa", "26-10-24-aaaa",
                    "2026-10-24-gggg", "../x", "2026-10-24-aaaa\n", "x2026-10-24-aaaa",
                    "2026-10-24-aaaa ", "", "2026-10-24"):
            with self.subTest(run=bad):
                p = self.accept("T1", bad)
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertFalse(self.store.exists())
        self.assertEqual(self.accept("T1", RUN1).returncode, 0)

    # -- ledger is the only source for upstream ---------------------------------------------

    def test_upstream_artifact_comes_from_the_ledger_never_from_notes_prose(self):
        fake = "deadbeef" * 8
        self.write_kit(_outcome("T1") + _outcome("T2")
                       + f"- T1 artifact={fake} upstream=none accepted\n"
                       + f"artifact: T1 {fake}\n")
        p = self.accept("T2", RUN2)  # T1 never accepted via the ledger
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("upstream=T1:unknown", p.stdout)
        self.assertNotIn("deadbeef", p.stdout)
        for path in self.store.rglob("*"):
            if path.is_file():
                self.assertNotIn("deadbeef", path.read_text())
        f = self.run_kc("freshness", "--kit", str(self.kit), "--attempt-store", str(self.store))
        self.assertNotIn("T2 fresh", f.stdout)
        # once T1 is accepted for real, T2's re-accept carries T1's ledger artifact
        self.assertEqual(self.accept("T1", RUN1).returncode, 0)
        t1 = [e for e in self.events() if e["task"] == "T1"][-1]["artifact"]
        self.append_notes(_outcome("T2", run=RUN3))
        p = self.accept("T2", RUN3)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn(f"upstream=T1:{t1[:12]}", p.stdout)

    # -- finding 4 red-proof -------------------------------------------------------------------

    def test_unsound_gate_returns_on_invalid_graph_and_would_exit_3_without_the_guard(self):
        import io
        from unittest import mock
        sys.path.insert(0, str(ROOT / "bin"))
        try:
            import kit_contract as kc
        finally:
            sys.path.pop(0)
        text = ("# fx — tasks\n\n## Phase 1 — fixtures\n\n"
                + _block("T1", "pending") + "\n"
                + _block("T1", "pending").replace("\ntrue\n", "\n\n"))
        (self.kit / "TASKS.md").write_text(text)
        tasks = kc.parse_tasks(text)
        self.assertTrue(kc.validate_graph(tasks), "fixture must be an invalid graph")
        # with the guard: returns, does not exit
        try:
            res = kc.exit_if_unsound_kit(self.kit, tasks, out=io.StringIO())
        except SystemExit as e:
            self.fail(f"exit_if_unsound_kit exited {e.code} on an invalid graph")
        self.assertIsNone(res)
        # mutation: pretend the graph is valid (the old behaviour) -> the empty fence exits 3
        with mock.patch.object(kc, "validate_graph", return_value=[]):
            with self.assertRaises(SystemExit) as cm:
                kc.exit_if_unsound_kit(self.kit, tasks, out=io.StringIO())
        self.assertEqual(cm.exception.code, 3)


# ---- drift (kit-preflight T8) ---------------------------------------------------------------------

def _kc():
    sys.path.insert(0, str(ROOT / "bin"))
    try:
        import kit_contract as kc
    finally:
        sys.path.pop(0)
    return kc


def _vblock(tid, verify="true", status="done", depends=(), fence=None, acceptance=""):
    """A task block with its own verify text; `fence` replaces the whole verify section, and
    `acceptance=None` leaves the `**Acceptance.**` paragraph out (default: `<tid> holds.`)."""
    dep = ", ".join(depends) if depends else "(none)"
    tail = fence if fence is not None else f"**Verify.**\n\n```bash\n{verify}\n```\n"
    if acceptance == "":
        acceptance = f"{tid} holds."
    para = "" if acceptance is None else f"**Acceptance.** {acceptance}\n\n"
    return (f"### {tid} — Task {tid}\n- id: {tid}\n- title: task {tid}\n- status: {status}\n"
            f"- model: haiku\n- depends: {dep}\n\n**Brief.** Do {tid}.\n\n" + para + tail)


#: A `- Verify:` + bare fence block: the other dialect, which `_extract_verify` does not read.
_OTHER_DIALECT = "- Verify:\n\n```\ntrue\n```\n"

#: Text the fake runners print; it must never reach the ledger.
_RUNNER_OUTPUT = "SECRET-RUNNER-OUTPUT /Users/someone/private/path"


class _Runner:
    """`runner(cmd) -> (rc, output)`, recording each call; rc per command text, default 0."""

    def __init__(self, rcs=None, raises=None):
        self.calls = []
        self.rcs = dict(rcs or {})
        self.raises = raises

    def __call__(self, cmd):
        self.calls.append(cmd)
        if self.raises is not None:
            raise self.raises
        return self.rcs.get(cmd, 0), _RUNNER_OUTPUT


class _FakeEP:
    """Stands in for `kit_contract._ep()`: its `verify_runner` reports a confinement through
    `on_result` the way `exec_policy.verify_runner` does, and never touches a sandbox."""

    def __init__(self, rc=1, confinement="fake-box", raises=None):
        self.rc, self.confinement, self.raises = rc, confinement, raises
        self.built, self.calls = [], []

    def verify_runner(self, workspace, mode="enforced", on_result=None, **_kw):
        self.built.append((Path(workspace), mode))
        label = "trusted-host" if mode == "trusted-host" else self.confinement

        def runner(cmd):
            self.calls.append(cmd)
            if self.raises is not None:
                raise self.raises
            if on_result is not None:
                on_result({"rc": self.rc, "output": _RUNNER_OUTPUT, "confinement": label})
            return self.rc, _RUNNER_OUTPUT

        return runner


class DriftTests(unittest.TestCase):
    """PLAN B3/D7 (as amended after the Phase 2 review), R6, R9. The git repo is `<tmp>/repo`
    and the store `<tmp>/store`, beside it, so `git status` in the repo sees only the tree."""

    def setUp(self):
        self.kc = _kc()
        self._tmp = tempfile.TemporaryDirectory(prefix="polytropos-drift-")
        base = Path(self._tmp.name).resolve()
        self.root = base / "repo"
        self.kits_dir = self.root / ".claude" / "kits"
        self.kit = self.kits_dir / "fx"
        self.kit.mkdir(parents=True)
        self.store = base / "store"
        self.home = base / "home"
        self.home.mkdir()
        self.git("init", "-q")
        (self.root / "seed.txt").write_text("seed\n")
        self.git("add", "seed.txt")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "seed")

    def tearDown(self):
        self._tmp.cleanup()

    # -- helpers ----------------------------------------------------------------------------

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True,
                              text=True).stdout

    def write_kit(self, blocks, notes="", kit=None):
        kit = kit or self.kit
        kit.mkdir(parents=True, exist_ok=True)
        (kit / "TASKS.md").write_text("# fx — tasks\n\n## Phase 1 — fixtures\n\n"
                                      + "\n".join(blocks))
        (kit / "NOTES.md").write_text("# notes\n" + notes)

    def tasks(self, kit=None):
        return self.kc.parse_tasks(((kit or self.kit) / "TASKS.md").read_text())

    def drift(self, runner, tasks=None, **kw):
        kw.setdefault("store", str(self.store))
        return self.kc.drift_kit(self.kit, tasks if tasks is not None else self.tasks(), runner,
                                 **kw)

    def events(self, kind="evidence.drift"):
        out = []
        for f in sorted(self.store.rglob("*.jsonl")) if self.store.exists() else ():
            for ln in f.read_text().splitlines():
                if ln.strip():
                    ev = json.loads(ln)
                    if kind is None or ev.get("kind") == kind:
                        out.append(ev)
        return out

    def cli(self, *argv, ep=None):
        out, err = io.StringIO(), io.StringIO()
        ep = ep if ep is not None else _FakeEP(rc=0)
        with mock.patch.object(self.kc, "_ep", return_value=ep), \
                redirect_stdout(out), redirect_stderr(err):
            try:
                rc = self.kc._cli(["drift", *argv])
            except SystemExit as exc:
                rc = ("exit", exc.code)
        return rc, out.getvalue(), err.getvalue(), ep

    def kit_bytes(self):
        return {str(p.relative_to(self.kit)): p.read_bytes()
                for p in sorted(self.kit.rglob("*")) if p.is_file()}

    def porcelain(self):
        return self.git("status", "--porcelain", "--untracked-files=all")

    # -- (1) one run per distinct verify text ---------------------------------------------

    def test_identical_verify_texts_run_once_and_the_later_task_lists_shared_with(self):
        self.write_kit([_vblock("T1", "true"), _vblock("T2", "test -f seed.txt"),
                        _vblock("T3", "true")])
        runner = _Runner()
        r = self.drift(runner)
        self.assertEqual(runner.calls, ["true", "test -f seed.txt"])
        self.assertEqual({t: e["state"] for t, e in r["tasks"].items()},
                         {"T1": "holds", "T2": "holds", "T3": "holds"})
        self.assertEqual(r["tasks"]["T1"]["shared_with"], [])
        self.assertEqual(r["tasks"]["T2"]["shared_with"], [])
        self.assertEqual(r["tasks"]["T3"]["shared_with"], ["T1"])
        self.assertEqual(r["exit"], 0)
        self.assertEqual(set(r), {"v", "kit", "confinement", "tasks", "exit"})
        self.assertEqual(r["kit"], "fx")

    def test_many_tasks_sharing_one_verify_run_it_once_and_each_event_stays_bounded(self):
        n = 300
        self.write_kit([_vblock(f"T{i}", "true") for i in range(n)])
        runner = _Runner()
        r = self.drift(runner, run_id=RUN1)
        self.assertEqual(runner.calls, ["true"])
        self.assertEqual({tuple(e["shared_with"]) for t, e in r["tasks"].items() if t != "T0"},
                         {("T0",)})
        evs = self.events()
        self.assertEqual(len(evs), n)
        self.assertLess(max(len(json.dumps(e)) for e in evs), 1024)

    def test_a_shared_failure_is_drifted_for_every_task_that_shares_it(self):
        self.write_kit([_vblock("T1", "false-ish"), _vblock("T2", "false-ish")])
        runner = _Runner(rcs={"false-ish": 1})
        r = self.drift(runner)
        self.assertEqual(runner.calls, ["false-ish"])
        self.assertEqual(r["tasks"]["T2"]["state"], "drifted")
        self.assertEqual(r["tasks"]["T2"]["rc"], 1)
        self.assertEqual(r["tasks"]["T2"]["shared_with"], ["T1"])

    # -- (2) a failing verify ---------------------------------------------------------------

    def test_a_failing_verify_is_drifted_and_exit_is_3(self):
        self.write_kit([_vblock("T1", "true"), _vblock("T2", "test -f gone.txt")])
        r = self.drift(_Runner(rcs={"test -f gone.txt": 1}))
        self.assertEqual(r["tasks"]["T1"]["state"], "holds")
        self.assertEqual(r["tasks"]["T2"]["state"], "drifted")
        self.assertEqual(r["tasks"]["T2"]["rc"], 1)
        self.assertEqual(r["exit"], 3)
        self.assertEqual(self.kc.render_drift(r).splitlines()[-1],
                         "drift: 1 hold, 1 drifted, 0 unrunnable")

    def test_a_runner_that_cannot_start_the_process_is_drifted_not_a_crash(self):
        self.write_kit([_vblock("T1", "true")])
        r = self.drift(_Runner(raises=OSError("cannot start")))
        self.assertEqual(r["tasks"]["T1"]["state"], "drifted")
        self.assertEqual(r["tasks"]["T1"]["rc"], 126)
        self.assertEqual(r["exit"], 3)

    # -- (3) unrunnable means unparseable, and nothing else --------------------------------

    def test_only_an_unparseable_verify_is_unrunnable_and_it_is_never_run(self):
        self.write_kit([
            _vblock("T1", ""),                                      # empty fence
            _vblock("T2", fence=_OTHER_DIALECT),                    # the other dialect
            _vblock("T3", "python3 bin/missing_tool.py --check"),   # missing script: warns
            _vblock("T4", "git diff --stat origin/main"),           # a ref, not a path
            _vblock("T5", "nosuch-tool-zz9 --version"),             # missing executable: warns
        ])
        runner = _Runner(rcs={"nosuch-tool-zz9 --version": 127})
        r = self.drift(runner)
        t = r["tasks"]
        self.assertEqual(t["T1"]["state"], "unrunnable")
        self.assertEqual(t["T2"]["state"], "unrunnable")
        self.assertIsNone(t["T1"]["rc"])
        self.assertIn("empty", t["T1"]["reason"])
        self.assertEqual(runner.calls, ["python3 bin/missing_tool.py --check",
                                        "git diff --stat origin/main",
                                        "nosuch-tool-zz9 --version"])
        self.assertNotIn("", runner.calls)
        self.assertEqual(t["T3"]["state"], "holds")
        self.assertIn("verify-missing-path", [w["kind"] for w in t["T3"]["warnings"]])
        self.assertEqual(t["T4"]["state"], "holds")
        self.assertEqual(t["T4"]["warnings"], [])
        self.assertEqual(t["T5"]["state"], "drifted")
        self.assertIn("verify-missing-executable", [w["kind"] for w in t["T5"]["warnings"]])
        self.assertEqual(r["exit"], 3)
        self.assertEqual(self.kc.render_drift(r).splitlines()[-1],
                         "drift: 2 hold, 1 drifted, 2 unrunnable")

    def test_unrunnable_is_read_from_findings_never_from_path_entry_states(self):
        # `origin/main`, `s/a/b/` and an `--out` target are recorded `missing` in the static
        # entry without any finding; each such verify is still run.
        verifies = ["git diff --stat origin/main", "sed s/a/b/ seed.txt",
                    "python3 -c 'print(1)' --out build/out.txt"]
        self.write_kit([_vblock(f"T{i}", v) for i, v in enumerate(verifies, 1)])
        static = self.kc.analyze_kit(self.kit, self.tasks())
        missing = [p for tid in static["verify"] for p in static["verify"][tid]["paths"]
                   if p["state"] == "missing"]
        self.assertTrue(missing, "fixture must hold a non-blocking `missing` entry")
        runner = _Runner()
        r = self.drift(runner)
        self.assertEqual(runner.calls, verifies)
        self.assertEqual({e["state"] for e in r["tasks"].values()}, {"holds"})

    # -- (4) only done tasks -----------------------------------------------------------------

    def test_tasks_that_are_not_done_are_absent_and_never_run(self):
        self.write_kit([_vblock("T1", "true"), _vblock("T2", "echo pending", "pending"),
                        _vblock("T3", "echo wip", "in-progress"),
                        _vblock("T4", "echo stuck", "blocked"),
                        _vblock("T5", "", "pending")])
        runner = _Runner()
        r = self.drift(runner)
        self.assertEqual(list(r["tasks"]), ["T1"])
        self.assertEqual(runner.calls, ["true"])
        self.assertEqual(r["exit"], 0)
        self.assertEqual(len(self.events()), 1)

    # -- (5) the acceptance identity, through TASKS.md (PLAN D7/B1 amended during T8) ----------

    def accept_cli(self, task, run):
        return subprocess.run(
            [sys.executable, str(KC), "accept", "--kit", str(self.kit), "--task", task, "--run",
             run, "--attempt-store", str(self.store)], capture_output=True, text=True,
            cwd=str(self.root), timeout=120, env=dict(os.environ, HOME=str(self.home)))

    def drift_lines(self, record=False):
        flags = () if record else ("--no-record",)
        rc, out, err, _ep = self.cli("--kit", str(self.kit), "--attempt-store", str(self.store),
                                     *flags, ep=_FakeEP(rc=0))
        self.assertIn(rc, (0, 3), out + err)
        return out.splitlines()

    def edit_tasks(self, old, new):
        path = self.kit / "TASKS.md"
        text = path.read_text()
        self.assertEqual(text.count(old), 1, old)
        path.write_text(text.replace(old, new))

    def test_acceptance_through_tasks_md_reads_unknown_then_unchanged_then_changed(self):
        self.write_kit([_vblock("T1", "true"), _vblock("T2", "test -f seed.txt")],
                       notes=_outcome("T1") + _outcome("T2"))
        self.assertIn("drift: T1 holds acceptance=unknown", self.drift_lines())  # none recorded
        p = self.accept_cli("T1", RUN1)
        self.assertEqual(p.returncode, 0, p.stderr)
        (acc,) = [e for e in self.events("task.projected") if e["task"] == "T1"]
        self.assertEqual(acc["acceptance_ref"]["sha"],
                         self.kc.acceptance_identity(self.tasks()[0])["sha"])
        lines = self.drift_lines()
        self.assertIn("drift: T1 holds acceptance=unchanged", lines)
        self.assertIn("drift: T2 holds acceptance=unknown", lines)  # never accepted
        self.drift_lines(record=True)  # a recorded run carries the same answer in its event
        self.assertEqual({e["task"]: e["acceptance"] for e in self.events()},
                         {"T1": "unchanged", "T2": "unknown"})
        self.edit_tasks("**Acceptance.** T1 holds.",
                        "**Acceptance.** T1 holds, and so does a new clause.")
        self.assertIn("drift: T1 holds acceptance=changed", self.drift_lines())
        self.edit_tasks("**Acceptance.** T1 holds, and so does a new clause.",
                        "**Acceptance.** T1 holds.")
        self.assertIn("drift: T1 holds acceptance=unchanged", self.drift_lines())
        # the identity covers the verify command too
        self.edit_tasks("```bash\ntrue\n```", "```bash\ntrue && true\n```")
        self.assertIn("drift: T1 holds acceptance=changed", self.drift_lines())
        # re-accepting against the edited block makes it current again: the latest wins
        with open(self.kit / "NOTES.md", "a") as fh:
            fh.write(_outcome("T1", run=RUN3))  # the loop stamps a fresh line per run
        self.assertEqual(self.accept_cli("T1", RUN3).returncode, 0)
        self.assertIn("drift: T1 holds acceptance=unchanged", self.drift_lines())

    def test_a_task_without_an_acceptance_paragraph_records_no_ref_and_reads_unknown(self):
        self.write_kit([_vblock("T1", "true", acceptance=None)], notes=_outcome("T1"))
        self.assertEqual(self.tasks()[0]["acceptance"], "")
        self.assertEqual(self.accept_cli("T1", RUN1).returncode, 0)
        (acc,) = self.events("task.projected")
        self.assertNotIn("acceptance_ref", acc)
        self.assertIn("drift: T1 holds acceptance=unknown", self.drift_lines())

    def test_a_record_written_before_acceptance_was_parsed_reads_unknown_never_changed(self):
        # The exact shape `accept` and the drivers' projections wrote before the parser carried
        # `acceptance`: a done projection with artifact and upstream, and no acceptance_ref.
        self.write_kit([_vblock("T1", "true"), _vblock("T2", "true", depends=["T1"])],
                       notes=_outcome("T1") + _outcome("T2"))
        ledger = self.kc.open_ledger(self.kit, store=str(self.store))
        art = self.kc._al().workspace_fingerprint(self.root)
        self.assertTrue(art)
        ledger.record_projected(RUN1, "T1", "done", result="pass", outcome_line=True,
                                artifact=art, upstream={})
        ledger.record_projected(RUN2, "T2", "done", result="pass", outcome_line=True,
                                artifact=art, upstream={"T1": art})
        self.assertFalse(any("acceptance_ref" in e for e in self.events("task.projected")))
        lines = self.drift_lines()
        self.assertIn("drift: T1 holds acceptance=unknown", lines)
        self.assertIn("drift: T2 holds acceptance=unknown shared-with T1", lines)
        fresh = self.kc.kit_freshness(self.kit, self.tasks(), store=str(self.store))
        self.assertEqual(fresh["T2"]["state"], "fresh")  # artifacts agree: never stale
        p = subprocess.run([sys.executable, str(KC), "freshness", "--kit", str(self.kit),
                            "--attempt-store", str(self.store)], capture_output=True, text=True,
                           cwd=str(self.root), timeout=120,
                           env=dict(os.environ, HOME=str(self.home)))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertNotIn("stale", p.stdout)

    def test_a_malformed_stored_ref_reads_unknown_never_changed(self):
        self.write_kit([_vblock("T1", "true")])
        ledger = self.kc.open_ledger(self.kit, store=str(self.store))
        self.assertIsNotNone(self.kc.acceptance_identity(self.tasks()[0]))
        for bogus in ("not-a-ref", {"sha": "a" * 64}, {"id": "x"}):
            with self.subTest(ref=bogus):
                ledger.append("task.projected", run=RUN1, task="T1", status="done",
                              result="pass", outcome_line=True, note="", artifact=None,
                              upstream=None, acceptance_ref=bogus)
                r = self.drift(_Runner(), record=False)
                self.assertEqual(r["tasks"]["T1"]["acceptance"], "unknown")

    # -- (6) the ledger event ----------------------------------------------------------------

    _EVENT_KEYS = {"v", "ts", "kind", "run", "task", "state", "rc", "acceptance", "verify_sha",
                   "confinement", "shared_with"}

    def test_one_event_per_checked_task_with_exactly_the_d7_fields_and_no_output(self):
        self.write_kit([_vblock("T1", "true"), _vblock("T2", "test -f x"), _vblock("T3", "true"),
                        _vblock("T4", ""), _vblock("T5", "true", "pending")])
        self.drift(_Runner(rcs={"test -f x": 1}), run_id=RUN1, confinement="box-x")
        evs = self.events()
        self.assertEqual([e["task"] for e in evs], ["T1", "T2", "T3", "T4"])
        for e in evs:
            with self.subTest(task=e["task"]):
                self.assertEqual(set(e), self._EVENT_KEYS)
                self.assertNotIn("output", e)
                self.assertEqual(e["run"], RUN1)
                self.assertEqual(e["confinement"], "box-x")
        by = {e["task"]: e for e in evs}
        self.assertEqual(by["T1"]["verify_sha"], hashlib.sha256(b"true").hexdigest())
        self.assertEqual(by["T2"]["verify_sha"], hashlib.sha256(b"test -f x").hexdigest())
        self.assertEqual((by["T2"]["state"], by["T2"]["rc"]), ("drifted", 1))
        self.assertEqual(by["T3"]["shared_with"], ["T1"])
        self.assertEqual((by["T4"]["state"], by["T4"]["rc"], by["T4"]["verify_sha"]),
                         ("unrunnable", None, None))
        stored = "".join(p.read_text() for p in self.store.rglob("*") if p.is_file())
        self.assertNotIn("SECRET-RUNNER-OUTPUT", stored)
        self.assertNotIn("/Users/someone", stored)

    def test_a_recorded_run_without_a_run_id_still_gets_a_content_free_one(self):
        self.write_kit([_vblock("T1", "true")])
        self.drift(_Runner())
        (ev,) = self.events()
        self.assertTrue(self.kc._valid_run_id(ev["run"]), ev["run"])

    def test_no_record_writes_nothing_and_creates_no_store(self):
        self.write_kit([_vblock("T1", "true"), _vblock("T2", "")])
        self.drift(_Runner(), record=False)
        self.assertFalse(self.store.exists())
        rc, out, err, _ep = self.cli("--kit", str(self.kit), "--attempt-store", str(self.store),
                                     "--no-record")
        self.assertEqual(rc, 3, out + err)
        self.assertFalse(self.store.exists())
        rc, out, err, _ep = self.cli("--kit", str(self.kit), "--attempt-store", str(self.store))
        self.assertEqual(len(self.events()), 2)

    # -- (7) nothing in the tree changes -------------------------------------------------------

    def test_the_kit_dir_and_the_tree_are_untouched_by_every_kind_of_run(self):
        self.write_kit([_vblock("T1", "true"), _vblock("T2", "test -f x"), _vblock("T3", ""),
                        _vblock("T4", "echo p", "pending")],
                       notes=_outcome("T1") + _outcome("T2"))
        kit_before, git_before = self.kit_bytes(), self.porcelain()
        statuses = [(t["id"], t["status"]) for t in self.tasks()]
        runs = [
            lambda: self.drift(_Runner()),
            lambda: self.drift(_Runner(rcs={"test -f x": 1}), record=False),
            lambda: self.drift(_Runner(raises=OSError("x"))),
            lambda: self.cli("--kit", str(self.kit), "--attempt-store", str(self.store)),
            lambda: self.cli("--kit", str(self.kit), "--attempt-store", str(self.store),
                             "--json", ep=_FakeEP(rc=1)),
            lambda: self.cli("--kit", str(self.kit), "--attempt-store", str(self.store),
                             "--no-record", "--exec-mode", "trusted-host"),
            lambda: self.cli("--all", "--kits-dir", str(self.kits_dir), "--attempt-store",
                             str(self.store)),
        ]
        for i, run in enumerate(runs):
            with self.subTest(run=i):
                run()
                self.assertEqual(self.kit_bytes(), kit_before)
                self.assertEqual(self.porcelain(), git_before)
                self.assertEqual([(t["id"], t["status"]) for t in self.tasks()], statuses)

    def test_no_status_writing_helper_is_referenced_by_drift(self):
        forbidden = ("project_status", "set_status", "append_run_note", "finish_task_projection",
                     "refresh_task", "start_task_lifecycle", "TaskRun", "append_block",
                     "write_text", "write_bytes")
        # positive control: the same read sees these names where they ARE used
        self.assertIn("project_status", inspect.getsource(self.kc.refresh_task))
        self.assertIn("append_run_note", inspect.getsource(self.kc.refresh_task))
        for fn in (self.kc.drift_kit, self.kc.render_drift, self.kc._drift_cli):
            src = inspect.getsource(fn)
            for name in forbidden:
                with self.subTest(fn=fn.__name__, name=name):
                    self.assertNotIn(name, src)

    # -- (8) the command line never returns 1 ---------------------------------------------------

    def test_the_cli_returns_3_on_a_failing_runner_never_1(self):
        self.write_kit([_vblock("T1", "true"), _vblock("T2", "test -f seed.txt")])
        rc, out, err, ep = self.cli("--kit", str(self.kit), "--attempt-store", str(self.store),
                                    ep=_FakeEP(rc=1))
        self.assertEqual(rc, 3, out + err)
        self.assertEqual(ep.calls, ["true", "test -f seed.txt"])
        self.assertEqual(ep.built, [(self.kc._al().kit_repo_root(self.kit), "enforced")])
        lines = out.splitlines()
        self.assertEqual(lines[0], "drift: fx confinement=fake-box")
        self.assertEqual(lines[1], "drift: T1 drifted acceptance=unknown")
        self.assertEqual(lines[-1], "drift: 0 hold, 2 drifted, 0 unrunnable")
        self.assertEqual({e["confinement"] for e in self.events()}, {"fake-box"})

    def test_the_cli_returns_3_when_the_runner_cannot_start_and_2_without_a_boundary(self):
        self.write_kit([_vblock("T1", "true")])
        rc, out, err, _ep = self.cli("--kit", str(self.kit), "--attempt-store", str(self.store),
                                     ep=_FakeEP(raises=OSError("no such file")))
        self.assertEqual(rc, 3, out + err)
        # `SandboxUnavailable` is a RuntimeError: a refusal before anything was checked
        rc, out, err, _ep = self.cli("--kit", str(self.kit), "--attempt-store", str(self.store),
                                     ep=_FakeEP(raises=RuntimeError("no OS confinement backend")))
        self.assertEqual(rc, 2, out + err)
        self.assertIn("no OS confinement backend", err)
        self.assertNotIn("Traceback", err)

    def test_the_cli_returns_0_when_everything_holds_and_names_trusted_host(self):
        self.write_kit([_vblock("T1", "true"), _vblock("T2", "true")])
        rc, out, err, ep = self.cli("--kit", str(self.kit), "--attempt-store", str(self.store),
                                    "--exec-mode", "trusted-host", ep=_FakeEP(rc=0))
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(ep.built[0][1], "trusted-host")
        self.assertEqual(out.splitlines(),
                         ["drift: fx confinement=trusted-host",
                          "drift: T1 holds acceptance=unknown",
                          "drift: T2 holds acceptance=unknown shared-with T1",
                          "drift: 2 hold, 0 drifted, 0 unrunnable"])
        self.assertEqual({e["confinement"] for e in self.events()}, {"trusted-host"})

    def test_trusted_host_is_named_even_when_nothing_ran(self):
        self.write_kit([_vblock("T1", "")])
        rc, out, err, ep = self.cli("--kit", str(self.kit), "--no-record", "--exec-mode",
                                    "trusted-host", "--attempt-store", str(self.store))
        self.assertEqual(rc, 3, out + err)
        self.assertEqual(ep.calls, [])
        self.assertEqual(out.splitlines()[0], "drift: fx confinement=trusted-host")

    def test_warnings_and_unrunnable_reasons_are_labelled_on_stderr(self):
        self.write_kit([_vblock("T1", "nosuch-tool-zz9 --version"), _vblock("T2", "")])
        rc, out, err, _ep = self.cli("--kit", str(self.kit), "--no-record", "--attempt-store",
                                     str(self.store), ep=_FakeEP(rc=127))
        self.assertEqual(rc, 3)
        self.assertIn("drift: fx T1 warning verify-missing-executable", err)
        self.assertIn("drift: fx T2 unrunnable -- ", err)

    def test_the_cli_json_is_the_report(self):
        self.write_kit([_vblock("T1", "true")])
        rc, out, err, _ep = self.cli("--kit", str(self.kit), "--json", "--attempt-store",
                                     str(self.store), ep=_FakeEP(rc=0))
        self.assertEqual(rc, 0, err)
        body = json.loads(out)
        self.assertEqual(set(body), {"v", "kit", "confinement", "tasks", "exit"})
        self.assertEqual(body["tasks"]["T1"]["state"], "holds")
        self.assertEqual(body["confinement"], "fake-box")

    def test_an_invalid_graph_under_kit_exits_2_and_builds_no_runner(self):
        self.write_kit([_vblock("T1", "true"), _vblock("T1", "true")])
        rc, out, err, ep = self.cli("--kit", str(self.kit), "--attempt-store", str(self.store))
        self.assertEqual(rc, ("exit", 2), out + err)
        self.assertIn("duplicate-id [T1]", err)  # the graph's verdict, not an argparse refusal
        self.assertEqual(ep.built, [])
        self.assertFalse(self.store.exists())

    def test_a_kit_dir_without_tasks_md_exits_2(self):
        rc, out, err, ep = self.cli("--kit", str(self.root / "nowhere"), "--attempt-store",
                                    str(self.store))
        self.assertEqual(rc, 2, out + err)
        self.assertEqual(ep.built, [])

    def test_the_process_exit_is_3_never_1_and_nothing_is_executed(self):
        # A real process with the real `exec_policy` loaded: the kit's only done task cannot be
        # read, so the runner is built but never called and no verify runs anywhere.
        self.write_kit([_vblock("T1", ""), _vblock("T2", "true", "pending")])
        p = subprocess.run(
            [sys.executable, str(KC), "drift", "--kit", str(self.kit), "--attempt-store",
             str(self.store)], capture_output=True, text=True, cwd=str(self.root), timeout=120,
            env=dict(os.environ, HOME=str(self.home)))
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertIn("drift: T1 unrunnable acceptance=unknown", p.stdout)
        self.assertNotIn("Traceback", p.stderr)

    def test_help_lists_drift_and_its_flags(self):
        p = subprocess.run([sys.executable, str(KC), "--help"], capture_output=True, text=True,
                           timeout=60, env=dict(os.environ, HOME=str(self.home)))
        self.assertIn("drift", p.stdout)
        p = subprocess.run([sys.executable, str(KC), "drift", "--help"], capture_output=True,
                           text=True, timeout=60, env=dict(os.environ, HOME=str(self.home)))
        for flag in ("--kit", "--all", "--kits-dir", "--attempt-store", "--exec-mode",
                     "--json", "--no-record"):
            self.assertIn(flag, p.stdout)

    # -- (9) --all -----------------------------------------------------------------------------

    def test_all_reports_an_unparseable_kit_completes_and_exits_3(self):
        self.write_kit([_vblock("T1", "true")])
        old = self.kits_dir / "a-old"  # sorts first, so completing proves it continued
        old.mkdir()
        (old / "TASKS.md").write_text("# old — tasks\n\n### T1 — Old task\n\n" + _OTHER_DIALECT)
        rc, out, err, ep = self.cli("--all", "--kits-dir", str(self.kits_dir), "--attempt-store",
                                    str(self.store), ep=_FakeEP(rc=0))
        self.assertEqual(rc, 3, out + err)  # D7, amended after T8's red-team: a skip is not a hold
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("kit: a-old unparseable -- "), out)
        self.assertIn("drift: fx confinement=fake-box", lines)
        self.assertEqual(lines[-1], "drift: 1 hold, 0 drifted, 0 unrunnable")
        self.assertEqual(ep.calls, ["true"])

    def test_all_exits_3_when_any_kit_drifts_and_reads_the_other_dialect_as_unrunnable(self):
        self.write_kit([_vblock("T1", "true")])
        legacy = self.kits_dir / "legacy"  # R4: parses (has statuses), verify unreadable
        self.write_kit([_vblock("T1", fence=_OTHER_DIALECT)], kit=legacy)
        rc, out, err, ep = self.cli("--all", "--kits-dir", str(self.kits_dir), "--attempt-store",
                                    str(self.store), ep=_FakeEP(rc=0))
        self.assertEqual(rc, 3, out + err)
        # nothing ran for `legacy` in enforced mode, so no run reported a boundary to name
        self.assertIn("drift: legacy confinement=unknown", out)
        self.assertIn("drift: fx confinement=fake-box", out)
        self.assertIn("drift: T1 unrunnable acceptance=unknown", out)
        rc, out, err, _ep = self.cli("--all", "--kits-dir", str(self.kits_dir), "--json",
                                     "--no-record", "--attempt-store", str(self.store),
                                     ep=_FakeEP(rc=0))
        body = json.loads(out)
        self.assertEqual([k["kit"] for k in body["kits"]], ["fx", "legacy"])
        self.assertEqual(body["exit"], 3)

    def test_all_skips_a_kit_the_ledger_cannot_name_completes_and_exits_3(self):
        self.write_kit([_vblock("T1", "true")])
        hidden = self.kits_dir / ".scratch"  # a leading dot is not a safe ledger namespace
        self.write_kit([_vblock("T1", "true")], kit=hidden)
        rc, out, err, ep = self.cli("--all", "--kits-dir", str(self.kits_dir), "--attempt-store",
                                    str(self.store), ep=_FakeEP(rc=0))
        self.assertEqual(rc, 3, out + err)
        self.assertIn("kit: .scratch skipped -- ", out)
        self.assertIn("drift: fx confinement=fake-box", out)
        self.assertNotIn("Traceback", err)

    # D7 amended again after T8's red-team ("a skipped kit gives 3"): under --all, a kit that is
    # reported but not checked makes the exit 3; --kit refusals stay 2; an empty dir stays 0.

    def _all(self, kits_dir, *extra):
        return self.cli("--all", "--kits-dir", str(kits_dir), "--exec-mode", "trusted-host",
                        "--attempt-store", str(self.store), *extra, ep=_FakeEP(rc=0))

    def _skip_kits(self):
        """One kits dir per skip path, each holding only that kit -> {path kind: kits dir}."""
        out = {}
        d = self.root / "only-bytes"
        (d / "kit").mkdir(parents=True)
        (d / "kit" / "TASKS.md").write_bytes(b"\xff\xfe")  # the red-team's repro
        out["unparseable"] = d
        d = self.root / "only-invalid"
        self.write_kit([_vblock("T1", "true"), _vblock("T1", "true")], kit=d / "dup")
        out["invalid graph"] = d
        d = self.root / "only-refused"
        self.write_kit([_vblock("T1", "true")], kit=d / ".scratch")
        out["skipped"] = d
        return out

    def test_all_with_every_kit_skipped_exits_3_in_text_and_json(self):
        kinds = self._skip_kits()
        for kind, kits_dir in kinds.items():
            with self.subTest(path=kind):
                rc, out, err, ep = self._all(kits_dir)
                self.assertEqual(rc, 3, out + err)
                self.assertIn(kind, out)
                self.assertEqual(ep.calls, [])
                rc, out, err, _ep = self._all(kits_dir, "--json")
                self.assertEqual(rc, 3, out + err)
                self.assertEqual(json.loads(out)["exit"], 3)
        together = self.root / "all-skipped"  # every skip path in one kits dir
        together.mkdir()
        for kits_dir in kinds.values():
            for sub in list(kits_dir.iterdir()):
                sub.rename(together / sub.name)
        rc, out, err, _ep = self._all(together)
        self.assertEqual(rc, 3, out + err)
        rc, out, err, _ep = self._all(together, "--json")
        self.assertEqual((rc, json.loads(out)["exit"]), (3, 3), out + err)
        self.assertEqual(len(json.loads(out)["kits"]), 3)

    def test_one_holding_kit_plus_one_unparseable_kit_exits_3(self):
        self.write_kit([_vblock("T1", "true")])
        (self.kits_dir / "zz-bytes").mkdir()
        (self.kits_dir / "zz-bytes" / "TASKS.md").write_bytes(b"\xff\xfe")
        rc, out, err, _ep = self._all(self.kits_dir)
        self.assertEqual(rc, 3, out + err)
        self.assertIn("drift: 1 hold, 0 drifted, 0 unrunnable", out)
        self.assertIn("kit: zz-bytes unparseable -- ", out)
        rc, out, err, _ep = self._all(self.kits_dir, "--json")
        self.assertEqual((rc, json.loads(out)["exit"]), (3, 3))

    def test_one_holding_kit_alone_exits_0(self):
        self.write_kit([_vblock("T1", "true")])
        rc, out, err, _ep = self._all(self.kits_dir)
        self.assertEqual(rc, 0, out + err)
        rc, out, err, _ep = self._all(self.kits_dir, "--json")
        self.assertEqual((rc, json.loads(out)["exit"]), (0, 0))

    def test_an_invalid_graph_is_3_under_all_and_still_2_under_kit(self):
        self.write_kit([_vblock("T1", "true"), _vblock("T1", "true")])
        rc, out, err, ep = self._all(self.kits_dir)
        self.assertEqual(rc, 3, out + err)
        self.assertIn("kit: fx invalid graph -- ", out)
        rc, out, err, ep = self.cli("--kit", str(self.kit), "--attempt-store", str(self.store))
        self.assertEqual(rc, ("exit", 2), out + err)

    def test_an_empty_kits_dir_exits_0_and_says_so(self):
        empty = self.root / "empty-kits"
        empty.mkdir()
        rc, out, err, ep = self._all(empty)
        self.assertEqual(rc, 0, out + err)
        self.assertIn("drift: no kit under", out)
        rc, out, err, _ep = self._all(empty, "--json")
        self.assertEqual((rc, json.loads(out)["exit"]), (0, 0))

    def test_all_over_a_missing_kits_dir_exits_2(self):
        rc, out, err, ep = self.cli("--all", "--kits-dir", str(self.root / "nowhere"),
                                    "--attempt-store", str(self.store))
        self.assertEqual(rc, 2, out + err)
        self.assertEqual(ep.built, [])

    # -- (10) R9: an evidence.drift event breaks no reader -------------------------------------

    def test_attempt_history_and_the_ledger_readers_ignore_evidence_drift(self):
        self.write_kit([_vblock("T1", "true"), _vblock("T2", "true", depends=["T1"])],
                       notes=_outcome("T1") + _outcome("T2"))
        self.kc.accept_task(self.kit, self.tasks()[0], RUN1, store=str(self.store),
                            workspace=self.root)
        self.kc.accept_task(self.kit, self.tasks()[1], RUN2, store=str(self.store),
                            workspace=self.root)
        fresh_before = self.kc.kit_freshness(self.kit, self.tasks(), store=str(self.store))
        self.drift(_Runner(), run_id=RUN3)
        self.assertEqual(len(self.events()), 2)
        ledger = self.kc.open_ledger(self.kit, store=str(self.store))
        self.assertEqual(ledger.usage(), {"max-dispatches": 0, "max-escalations": 0,
                                          "max-consults": 0, "max-model-calls": 0})
        self.assertEqual(ledger.unprojected("T1"), [])
        self.assertEqual(ledger.task_history("T1"), [])
        self.assertEqual(ledger.open_attempts(), [])
        self.assertEqual(ledger.latest_acceptance("T1")["run"], RUN1)
        self.assertEqual(self.kc.kit_freshness(self.kit, self.tasks(), store=str(self.store)),
                         fresh_before)
        sys.path.insert(0, str(ROOT / "bin"))
        try:
            import attempt_history as ah
        finally:
            sys.path.pop(0)
        records, notes = ah.join_kit(self.kit, store=str(self.store))
        self.assertEqual([r for r in records if r["source"] == "ledger"], [])
        self.assertEqual(sorted(r["task"] for r in records), ["T1", "T2"])  # the outcome lines
        ah.summarize(records, notes)  # the card's reader takes the joined records as they are


class AcceptanceParseTests(unittest.TestCase):
    """PLAN D7/B1 amended during T8 ("parse acceptance now"): `parse_tasks` carries each task's
    `**Acceptance.**` paragraph -- up to `**Verify.**` or the block's end, stripped, `""` when
    absent -- so `acceptance_identity` has something to identify."""

    def setUp(self):
        self.kc = _kc()

    def parse(self, body, head="### T1 — t\n- status: pending\n\n"):
        return self.kc.parse_tasks(head + body)[0]

    def test_the_paragraph_between_acceptance_and_verify_is_carried_stripped(self):
        t = self.parse("**Brief.** Do it.\n\n**Acceptance.**  It holds,\nacross two lines.  \n\n"
                       "**Verify.**\n\n```bash\ntrue\n```\n")
        self.assertEqual(t["acceptance"], "It holds,\nacross two lines.")
        self.assertEqual(t["brief"], "Do it.")
        self.assertEqual(t["verify"], "true")
        self.assertIsNotNone(self.kc.acceptance_identity(t))
        self.assertEqual(self.kc.to_contract(t)["acceptance"], t["acceptance"])

    def test_a_block_without_the_paragraph_carries_an_empty_string(self):
        for body in ("**Brief.** Do it.\n\n**Verify.**\n\n```bash\ntrue\n```\n", ""):
            with self.subTest(body=body):
                t = self.parse(body)
                self.assertEqual(t["acceptance"], "")
                self.assertIsNone(self.kc.acceptance_identity(t))

    def test_an_acceptance_holding_a_fenced_block_keeps_it_and_the_verify_is_unchanged(self):
        t = self.parse("**Brief.** Do it.\n\n**Acceptance.** The command prints:\n\n"
                       "```bash\necho acceptance-fence\n```\n\nand exits 0.\n\n"
                       "**Verify.**\n\n```bash\ntrue\n```\n")
        self.assertEqual(t["acceptance"],
                         "The command prints:\n\n```bash\necho acceptance-fence\n```\n\n"
                         "and exits 0.")
        self.assertEqual(t["verify"], "true")
        self.assertEqual(t["brief"], "Do it.")

    def test_without_a_verify_marker_the_paragraph_runs_to_the_block_end(self):
        tasks = self.kc.parse_tasks("### T1 — t\n- status: pending\n\n**Acceptance.** Ends here."
                                    "\n\n### T2 — u\n- status: pending\n")
        self.assertEqual(tasks[0]["acceptance"], "Ends here.")
        self.assertIsNone(tasks[0]["verify"])
        self.assertEqual(tasks[1]["acceptance"], "")

    def test_the_identity_is_stable_and_moves_only_with_the_text(self):
        body = "**Acceptance.** It holds.\n\n**Verify.**\n\n```bash\ntrue\n```\n"
        a, b = self.parse(body), self.parse(body)
        self.assertEqual(self.kc.acceptance_identity(a), self.kc.acceptance_identity(b))
        c = self.parse(body.replace("It holds.", "It holds twice."))
        self.assertNotEqual(self.kc.acceptance_identity(a)["sha"],
                            self.kc.acceptance_identity(c)["sha"])

    def test_every_committed_kit_that_parsed_before_still_parses(self):
        # Read-only over the committed TASKS.md files: nothing is run, accepted, or written.
        kits = sorted((ROOT / ".claude" / "kits").glob("*/TASKS.md"))
        if not kits:
            self.skipTest("no committed kits")
        parsed = 0
        for path in kits:
            try:
                tasks = self.kc.parse_tasks(path.read_text())
            except ValueError:
                continue  # an older dialect without `- status:` lines, refused as before
            parsed += 1
            for t in tasks:
                with self.subTest(kit=path.parent.name, task=t["id"]):
                    self.assertIsInstance(t["acceptance"], str)
        self.assertGreater(parsed, 0)


class DriftTestAuthorTests(unittest.TestCase):
    """Adversarial T8 tests written from the brief (PLAN D7 as amended twice, B1, R9)."""

    # reuse DriftTests' fixture plumbing without re-collecting its tests
    setUp = DriftTests.setUp
    tearDown = DriftTests.tearDown
    git = DriftTests.git
    write_kit = DriftTests.write_kit
    tasks = DriftTests.tasks
    drift = DriftTests.drift
    events = DriftTests.events
    cli = DriftTests.cli
    kit_bytes = DriftTests.kit_bytes
    porcelain = DriftTests.porcelain

    def parse(self, body):
        return self.kc.parse_tasks("### T1 \u2014 t\n- status: done\n\n" + body)[0]

    # -- D7 state rule ------------------------------------------------------------------------

    def test_whitespace_only_fence_is_unrunnable_and_never_run(self):
        self.write_kit([_vblock("T1", "   \n  "), _vblock("T3", "true")])
        runner = _Runner()
        r = self.drift(runner)
        self.assertEqual(r["tasks"]["T1"]["state"], "unrunnable")
        self.assertEqual(r["tasks"]["T3"]["state"], "holds")
        self.assertEqual(runner.calls, ["true"])
        self.assertEqual(r["exit"], 3)

    def test_unclosed_quote_is_ambiguous_plan_d3_defines_unparseable_as_none_or_empty(self):
        # AMBIGUOUS: the task prompt listed "an unclosed quote" as unparseable, but PLAN D3
        # (seventh amendment) defines verify-unparseable as `_extract_verify` None or an
        # empty/whitespace fence only. Observed: the text is run and judged by rc.
        self.write_kit([_vblock("T2", "echo 'unclosed")])
        runner = _Runner()
        r = self.drift(runner)
        self.assertEqual(runner.calls, ["echo 'unclosed"])
        self.assertEqual(r["tasks"]["T2"]["state"], "holds")

    def test_missing_findings_are_warnings_and_the_state_follows_rc_alone(self):
        self.write_kit([_vblock("T1", "python3 bin/no_such_script_zz.py")])
        r = self.drift(_Runner())
        self.assertEqual(r["tasks"]["T1"]["state"], "holds")
        self.assertTrue(r["tasks"]["T1"]["warnings"])
        self.assertEqual(r["exit"], 0)
        r = self.drift(_Runner(rcs={"python3 bin/no_such_script_zz.py": 2}))
        self.assertEqual(r["tasks"]["T1"]["state"], "drifted")
        self.assertEqual(r["tasks"]["T1"]["rc"], 2)

    def test_dedupe_keys_on_the_stripped_verify_text(self):
        self.write_kit([_vblock("T1", "true"), _vblock("T2", "true")])
        tasks = self.tasks()
        tasks[0]["verify"] = "  true\n"
        tasks[1]["verify"] = "\ttrue  "
        runner = _Runner()
        r = self.drift(runner, tasks=tasks)
        self.assertEqual(runner.calls, ["true"])
        self.assertEqual(r["tasks"]["T2"]["shared_with"], ["T1"])

    def test_a_kit_with_no_done_tasks_exits_0_and_runs_nothing(self):
        self.write_kit([_vblock("T1", "true", "pending"), _vblock("T2", "true", "blocked"),
                        _vblock("T3", "true", "in-progress")])
        runner = _Runner()
        r = self.drift(runner)
        self.assertEqual((r["tasks"], r["exit"], runner.calls), ({}, 0, []))

    def test_a_raising_runner_through_the_cli_is_never_1(self):
        self.write_kit([_vblock("T1", "true")])
        rc, out, err, _ep = self.cli("--kit", str(self.kit), "--attempt-store", str(self.store),
                                     ep=_FakeEP(raises=ValueError("boom")))
        self.assertNotEqual(rc, 1, out + err)

    # -- parser edges (step 6) ----------------------------------------------------------------

    def test_crlf_blocks_parse_the_same_acceptance_without_carriage_returns(self):
        t = self.parse("**Brief.** b\r\n\r\n**Acceptance.** crlf text\r\nline2\r\n\r\n"
                       "**Verify.**\r\n\r\n```bash\r\ntrue\r\n```\r\n")
        self.assertEqual(t["acceptance"].replace("\r", ""), "crlf text\nline2")
        self.assertNotIn("\r", t["acceptance"])
        self.assertEqual(t["verify"], "true")

    def test_two_acceptance_markers_run_from_the_first_to_verify(self):
        t = self.parse("**Brief.** b\n\n**Acceptance.** one.\n\n**Acceptance.** two.\n\n"
                       "**Verify.**\n\n```bash\ntrue\n```\n")
        # the rule is "between **Acceptance.** and **Verify.**": the first marker starts it
        self.assertTrue(t["acceptance"].startswith("one."))
        self.assertIn("two.", t["acceptance"])
        self.assertEqual(t["verify"], "true")

    # Third dispatch: the markers count only where they begin a line, outside a fence.
    accept_cli = DriftTests.accept_cli
    drift_lines = DriftTests.drift_lines
    edit_tasks = DriftTests.edit_tasks

    def _raw_block(self, body):
        return "### T1 — Task T1\n- status: done\n- depends: (none)\n\n" + body

    def test_acceptance_marker_quoted_in_the_brief_does_not_start_the_acceptance(self):
        body = ("**Brief.** Mention `**Acceptance.**` in the brief-quoted-clause.\n\n"
                "**Acceptance.** real.\n\n**Verify.**\n\n```bash\ntrue\n```\n")
        t = self.parse(body)
        self.assertEqual(t["acceptance"], "real.")
        self.assertEqual(t["verify"], "true")
        # through TASKS.md: the brief's words are not part of the acceptance identity, so
        # editing them after an `accept` leaves `drift` reading `unchanged`
        self.write_kit([self._raw_block(body)], notes=_outcome("T1"))
        self.assertEqual(self.accept_cli("T1", RUN1).returncode, 0)
        self.assertIn("drift: T1 holds acceptance=unchanged", self.drift_lines())
        self.edit_tasks("brief-quoted-clause", "brief-quoted-clause, reworded")
        self.assertIn("drift: T1 holds acceptance=unchanged", self.drift_lines())

    def test_verify_marker_inside_an_acceptance_fence_does_not_end_the_acceptance(self):
        body = ("**Brief.** b\n\n**Acceptance.** shows:\n\n```\n**Verify.**\nfoo\n```\n\n"
                "trailing-clause\n\n**Verify.**\n\n```bash\ntrue\n```\n")
        t = self.parse(body)
        self.assertEqual(t["acceptance"],
                         "shows:\n\n```\n**Verify.**\nfoo\n```\n\ntrailing-clause")
        self.assertEqual(t["verify"], "true")
        # an edit after the inner marker is an edit of the acceptance: `drift` reads `changed`
        self.write_kit([self._raw_block(body)], notes=_outcome("T1"))
        self.assertEqual(self.accept_cli("T1", RUN1).returncode, 0)
        self.assertIn("drift: T1 holds acceptance=unchanged", self.drift_lines())
        self.edit_tasks("trailing-clause", "trailing-clause, tightened")
        self.assertIn("drift: T1 holds acceptance=changed", self.drift_lines())

    def test_markers_count_only_at_a_line_start_and_outside_any_fence(self):
        # an indented heading with text after it starts the acceptance; a four-backtick fence
        # holding a three-backtick line and both markers neither starts nor ends it
        t = self.parse("**Brief.** b\n\n````\n**Acceptance.** fenced-out\n```\n**Verify.**\n"
                       "````\n\n  **Acceptance.** It holds, see `**Verify.**` below.\n"
                       "````md\n**Verify.**\n```\n````\nlast-line\n**Verify.**\n\n"
                       "```bash\ntrue\n```\n")
        self.assertTrue(t["acceptance"].startswith("It holds, see `**Verify.**` below."),
                        t["acceptance"])
        self.assertTrue(t["acceptance"].endswith("last-line"), t["acceptance"])
        self.assertNotIn("fenced-out", t["acceptance"])

    def test_tilde_fences_hide_markers_too_and_close_only_on_their_own_character(self):
        # the red-team's repro: a `~~~` fence holding a line-leading `**Verify.**`
        self.assertEqual(
            self.kc._extract_acceptance(
                "**Acceptance.** a\n~~~\nx\n**Verify.** q\n~~~\nmore\n**Verify.**\n"),
            "a\n~~~\nx\n**Verify.** q\n~~~\nmore")
        # a `~~~` fence holding a ``` line and both markers neither starts nor ends it, and a
        # ``` line never closes a `~~~` fence (nor a ~~~ line a ``` fence)
        t = self.parse("**Brief.** b\n\n~~~\n**Acceptance.** fenced-out\n```\n**Verify.**\n~~~\n\n"
                       "**Acceptance.** real\n~~~~ text\n```\n**Verify.** inside\n~~~\n"
                       "~~~~\n```\n~~~\n**Verify.** still-inside\n```\nlast-line\n"
                       "**Verify.**\n\n```bash\ntrue\n```\n")
        acc = t["acceptance"]
        self.assertTrue(acc.startswith("real\n"), acc)
        self.assertNotIn("fenced-out", acc)
        self.assertIn("**Verify.** inside", acc)
        self.assertIn("**Verify.** still-inside", acc)
        self.assertTrue(acc.endswith("last-line"), acc)
        self.assertEqual(t["verify"], "true")

    def test_committed_kits_that_quote_a_marker_parse_the_acceptance_from_its_heading(self):
        # Read-only over committed TASKS.md files: nothing is run, accepted, or written.
        import re
        cases = {"codex-harness": ("T9",), "copilot-workflow": ("T3", "T4"),
                 "kit-preflight": ("T8",)}
        for slug, ids in cases.items():
            path = ROOT / ".claude" / "kits" / slug / "TASKS.md"
            if not path.exists():
                continue
            text = path.read_text()
            tasks = {t["id"]: t for t in self.kc.parse_tasks(text)}
            for tid in ids:
                with self.subTest(kit=slug, task=tid):
                    acc = tasks[tid]["acceptance"]
                    self.assertTrue(acc, "the task has an **Acceptance.** heading")
                    # a fragment is the tail of a quoted marker (`` `/ ``, `` ` (or ``, `` `, and ``);
                    # a leading code span such as `` `--help` lists `` is real text
                    self.assertNotRegex(acc, r"^`[\s,.;:)/]", acc[:60])
                    heading = re.compile(r"(?m)^[ \t]*\*\*Acceptance\.\*\*\s*"
                                         + re.escape(acc[:40]))
                    self.assertRegex(text, heading)

    # -- ledger event and no-record ------------------------------------------------------------

    def test_event_has_only_d7_keys_plus_envelope_and_no_output_even_with_secret_output(self):
        self.write_kit([_vblock("T1", "true")])

        def runner(cmd):
            return 0, "AKIAIOSFODNN7EXAMPLE sk-secret-token-123"
        self.drift(runner, run_id=RUN1, confinement="box")
        (ev,) = self.events()
        d7 = {"run", "task", "state", "rc", "acceptance", "verify_sha", "confinement",
              "shared_with"}
        self.assertTrue(d7 <= set(ev))
        extra = set(ev) - d7
        self.assertLessEqual(extra, {"v", "kind", "ts", "at", "when", "kit", "id", "seq"})
        stored = "".join(p.read_text() for p in self.store.rglob("*") if p.is_file())
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", stored)
        self.assertNotIn("sk-secret", stored)

    def test_cli_no_record_writes_nothing(self):
        self.write_kit([_vblock("T1", "true")])
        self.cli("--kit", str(self.kit), "--no-record", "--attempt-store", str(self.store))
        self.assertEqual(self.events(kind=None), [])

    # -- read-only tree -------------------------------------------------------------------------

    def test_drift_all_over_an_unparseable_kit_leaves_bytes_and_porcelain_unchanged(self):
        self.write_kit([_vblock("T1", "true")])
        bad = self.kits_dir / "bad"
        bad.mkdir()
        (bad / "TASKS.md").write_text("# bad\n\n### T1 \u2014 x\n" + _OTHER_DIALECT)
        self.git("add", "-A")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "kits")
        before = (self.kit_bytes(), self.porcelain(),
                  {p.name: p.read_bytes() for p in bad.iterdir()})
        rc, out, err, _ep = self.cli("--all", "--kits-dir", str(self.kits_dir),
                                     "--attempt-store", str(self.store))
        after = (self.kit_bytes(), self.porcelain(),
                 {p.name: p.read_bytes() for p in bad.iterdir()})
        self.assertEqual(before, after)
        self.assertIn("kit: bad unparseable", out + err)
        self.assertNotEqual(rc, 1)

    # -- first line / confinement ---------------------------------------------------------------

    def test_trusted_host_first_line_never_names_an_enforced_backend(self):
        self.write_kit([_vblock("T1", "true")])
        ep = _FakeEP(rc=0, confinement="sandbox-exec")
        rc, out, err, _ep = self.cli("--kit", str(self.kit), "--exec-mode", "trusted-host",
                                     "--no-record", "--attempt-store", str(self.store), ep=ep)
        self.assertEqual(out.splitlines()[0], "drift: fx confinement=trusted-host")
        self.assertNotIn("sandbox-exec", out)
        rc, out, err, _ep = self.cli("--kit", str(self.kit), "--no-record",
                                     "--attempt-store", str(self.store), ep=ep)
        self.assertEqual(out.splitlines()[0], "drift: fx confinement=sandbox-exec")


class AcceptRunGuardTests(unittest.TestCase):
    """`accept` refuses unless the task's latest passing `outcome:` line carries `run=` equal to
    `--run` and that run's date is today or yesterday in UTC (PLAN D6/B1, amended 2026-10-24
    after the Phase 3 review, which copied a finished kit and accepted all 11 of its tasks).

    The window is pinned IN-PROCESS through `accept_task(now=...)`, a seam that exists only for
    unit tests and is not reachable from the command line. Tests that drive the real process
    use ids from the production `generate_run_id()`. No test here reads the real clock to
    decide a date-window case, and no committed kit is touched."""

    NOW = None  # set in setUpClass: a pinned UTC instant

    @classmethod
    def setUpClass(cls):
        from datetime import datetime, timezone
        cls.NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
        sys.path.insert(0, str(ROOT / "bin"))
        try:
            import kit_contract as kc
        finally:
            sys.path.pop(0)
        cls.kc = kc

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="polytropos-accept-guard-")
        self.root = Path(self._tmp.name).resolve()
        self.kit = self.root / ".claude" / "kits" / "fx"
        self.kit.mkdir(parents=True)
        self.store = self.root / "store"
        self.home = self.root / "home"
        self.home.mkdir()
        self.git("init", "-q")
        (self.root / "seed.txt").write_text("seed\n")
        self.git("add", "seed.txt")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "seed")

    def tearDown(self):
        self._tmp.cleanup()

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def write_kit(self, notes, tasks=("T1", "T2"), chain=False):
        body = "".join(_block(t, "done", depends=(tasks[i - 1],) if chain and i else ()) + "\n"
                       for i, t in enumerate(tasks))
        (self.kit / "TASKS.md").write_text("# fx — tasks\n\n## Phase 1 — fixtures\n\n" + body)
        (self.kit / "NOTES.md").write_text("# notes\n" + notes)

    def run_kc(self, *args):
        return subprocess.run(
            [sys.executable, str(KC), *args], capture_output=True, text=True,
            env=dict(os.environ, HOME=str(self.home)), cwd=str(self.root), timeout=120)

    def cli_accept(self, task, run, kit=None):
        return self.run_kc("accept", "--kit", str(kit or self.kit), "--task", task, "--run", run,
                           "--attempt-store", str(self.store))

    def accept_at(self, run, now, task="T1"):
        tasks = self.kc.parse_tasks((self.kit / "TASKS.md").read_text())
        t = next(x for x in tasks if x["id"] == task)
        return self.kc.accept_task(self.kit, t, run, store=str(self.store), now=now)

    def refusal(self, run, now, task="T1"):
        with self.assertRaises(ValueError) as cm:
            self.accept_at(run, now, task)
        self.assertFalse(self.store.exists(), "a refusal must write nothing")
        return str(cm.exception)

    # -- the process, with a fresh id from the production generator ---------------------------

    def test_a_matching_fresh_run_exits_0(self):
        self.write_kit(_outcome("T1", run=RUN1))
        p = self.cli_accept("T1", RUN1)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_a_mismatched_run_exits_2_and_names_both_ids(self):
        self.write_kit(_outcome("T1", run=RUN1))
        p = self.cli_accept("T1", RUN2)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn(RUN1, p.stderr)
        self.assertIn(RUN2, p.stderr)
        self.assertFalse(self.store.exists())

    def test_a_line_without_run_exits_2(self):
        self.write_kit(_outcome("T1", run=False))
        p = self.cli_accept("T1", RUN1)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("run=", p.stderr)
        self.assertFalse(self.store.exists())

    def test_the_clock_is_not_reachable_from_the_command_line(self):
        self.write_kit(_outcome("T1", run=RUN1))
        for extra in (["--now", "2026-10-24T00:00:00"], ["--today", "2026-10-24"]):
            with self.subTest(extra=extra):
                p = self.run_kc("accept", "--kit", str(self.kit), "--task", "T1", "--run", RUN1,
                                "--attempt-store", str(self.store), *extra)
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertIn("unrecognized arguments", p.stderr)
        old = "2026-01-05-abcd"
        self.write_kit(_outcome("T1", run=old))
        p = self.run_kc("accept", "--kit", str(self.kit), "--task", "T1", "--run", old,
                        "--attempt-store", str(self.store))
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        for var in ("POLYTROPOS_NOW", "KIT_CONTRACT_NOW", "NOW", "FAKETIME"):
            q = subprocess.run(
                [sys.executable, str(KC), "accept", "--kit", str(self.kit), "--task", "T1",
                 "--run", old, "--attempt-store", str(self.store)], capture_output=True,
                text=True, cwd=str(self.root), timeout=120,
                env=dict(os.environ, HOME=str(self.home), **{var: "2026-01-05T00:00:00"}))
            self.assertEqual(q.returncode, 2, f"{var}: {q.stdout}{q.stderr}")
        self.assertFalse(self.store.exists())

    def test_the_reviewers_repro_a_copied_finished_kit_is_refused_for_every_task(self):
        # The Phase 3 review copied a finished kit into a temp dir and accepted its done tasks.
        # Its lines carry the run ids of the day they were written, long past the window.
        old = ["2026-03-02-1a2b", "2026-03-02-3c4d", "2026-03-03-5e6f"]
        self.write_kit("".join(_outcome(t, run=r) for t, r in zip(("T1", "T2", "T3"), old)),
                       tasks=("T1", "T2", "T3"), chain=True)
        for tid, run in zip(("T1", "T2", "T3"), old):
            with self.subTest(task=tid):
                p = self.cli_accept(tid, run)
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertTrue(p.stderr.startswith("accept: "), p.stderr)
                self.assertIn("2026-03-0", p.stderr)  # names the run's date
        self.assertFalse(self.store.exists())
        f = self.run_kc("freshness", "--kit", str(self.kit), "--attempt-store", str(self.store))
        self.assertIn("T2 unknown", f.stdout)
        self.assertIn("T3 unknown", f.stdout)
        self.assertNotIn("T2 fresh", f.stdout)
        self.assertNotIn("T3 fresh", f.stdout)
        # a freshly stamped line for the same task is what makes it acceptable
        (self.kit / "NOTES.md").write_text(
            (self.kit / "NOTES.md").read_text() + _outcome("T1", run=RUN1))
        self.assertEqual(self.cli_accept("T1", RUN1).returncode, 0)

    # -- the date window, in-process with a pinned clock --------------------------------------

    def test_todays_run_is_accepted(self):
        self.write_kit(_outcome("T1", run="2026-10-24-aaaa"))
        out = self.accept_at("2026-10-24-aaaa", self.NOW)
        self.assertEqual(out["id"], "T1")

    def test_yesterdays_run_is_accepted(self):
        self.write_kit(_outcome("T1", run="2026-10-23-aaaa"))
        out = self.accept_at("2026-10-23-aaaa", self.NOW)
        self.assertEqual(out["id"], "T1")

    def test_a_matching_run_dated_two_days_ago_is_refused_naming_both_dates(self):
        self.write_kit(_outcome("T1", run="2026-10-22-aaaa"))
        msg = self.refusal("2026-10-22-aaaa", self.NOW)
        self.assertIn("2026-10-22", msg)
        self.assertIn("2026-10-24", msg)

    def test_a_run_dated_in_the_future_is_refused(self):
        self.write_kit(_outcome("T1", run="2026-10-26-aaaa"))
        msg = self.refusal("2026-10-26-aaaa", self.NOW)
        self.assertIn("2026-10-26", msg)

    def test_the_window_follows_the_injected_clock_not_the_real_one(self):
        from datetime import datetime, timezone
        self.write_kit(_outcome("T1", run="2026-10-22-aaaa"))
        out = self.accept_at("2026-10-22-aaaa", datetime(2026, 10, 23, 0, 5, tzinfo=timezone.utc))
        self.assertEqual(out["id"], "T1")

    def test_a_mismatched_run_is_refused_in_process_naming_both_ids(self):
        self.write_kit(_outcome("T1", run="2026-10-24-aaaa"))
        msg = self.refusal("2026-10-24-bbbb", self.NOW)
        self.assertIn("2026-10-24-aaaa", msg)
        self.assertIn("2026-10-24-bbbb", msg)

    def test_a_line_without_run_is_refused_in_process(self):
        self.write_kit(_outcome("T1", run=False))
        self.assertIn("run=", self.refusal("2026-10-24-aaaa", self.NOW))

    def test_the_latest_passing_line_is_the_one_whose_run_counts(self):
        self.write_kit(_outcome("T1", run="2026-10-24-aaaa")
                       + _outcome("T1", "retry-pass", run="2026-10-24-bbbb"))
        self.assertIn("2026-10-24-bbbb", self.refusal("2026-10-24-aaaa", self.NOW))
        self.assertEqual(self.accept_at("2026-10-24-bbbb", self.NOW)["result"], "retry-pass")



if __name__ == "__main__":
    unittest.main()
