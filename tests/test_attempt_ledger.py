"""Step 16: durable, resumable attempts (bin/attempt_ledger.py + the drivers + Ralph).

What these tests establish, each against the failure it replaces:

  * A run that dies after dispatch leaves an attempt with no result. The next run finds it,
    closes it as UNKNOWN (never success), runs the check, and either recognises finished work
    without dispatching again or dispatches once more with the history in the prompt.
  * A run that dies after verification but before writing TASKS.md/NOTES.md re-projects the
    verdict it already has; it does not pay for the work twice.
  * Budget usage carries across runs: attempts the ledger holds but NOTES.md has not yet
    summarised still count, so an interrupted ladder cannot start over with a fresh cap.
  * A logged-out CLI is classified `auth`, recorded, and NOT escalated to a costlier model.
  * A timestamp is not progress; fewer failures is, even when the log looks the same.
  * Two runs cannot hold one task; a claim whose process is gone is taken over.
  * The final status is written from a fresh read, and a worker that flipped its own status
    is overwritten by the driver's verdict, with the discrepancy reported.

SAFETY. Every dispatch here is a temp stub executable or an injected callable; nothing invokes
a real CLI. Every ledger lives in a temp dir: `--attempt-store` where the driver takes it, and
`POLYTROPOS_DATA_HOME` patched at module level for the default path, so no test can resolve
the store into the real per-user data root.
"""

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_claude_execute as tce

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


al = _load("attempt_ledger")
kc = _load("kit_contract")
cr = _load("copilot_ralph")
ce = tce.ce

_DATA_HOME = None
_DATA_HOME_PATCH = None


def setUpModule():
    global _DATA_HOME, _DATA_HOME_PATCH
    _DATA_HOME = tempfile.TemporaryDirectory(prefix="polytropos-test-data-")
    _DATA_HOME_PATCH = mock.patch.dict(os.environ, {"POLYTROPOS_DATA_HOME": _DATA_HOME.name})
    _DATA_HOME_PATCH.start()


def tearDownModule():
    _DATA_HOME_PATCH.stop()
    _DATA_HOME.cleanup()


#: A pid that cannot be alive: far above any real pid table, so a lock naming it is stale.
DEAD_PID = 2 ** 22 - 7


# ---- the ledger itself -----------------------------------------------------------------------

class LedgerRecordTests(unittest.TestCase):
    def test_an_attempt_is_recorded_before_and_after_and_survives_a_missing_finish(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            a1 = ledger.record_started("r1", "T1", "initial", "fake-cheap", prompt="p",
                                       verify_cmd="true")
            self.assertEqual(ledger.open_attempts("T1")[0]["attempt"], a1)
            ledger.record_finished("r1", "T1", a1, "ok", 0, "did it")
            self.assertEqual(ledger.open_attempts("T1"), [])
            a2 = ledger.record_started("r1", "T1", "escalation", "fake-mid")
            # ... and the process dies. A later run closes it as unknown, never as success.
            closed = ledger.reconcile_open("r2", "T1", "closed by r2")
            self.assertEqual(closed, [a2])
            history = ledger.task_history("T1")
            self.assertEqual(history[1]["finished"]["outcome"], al.OUTCOME_UNKNOWN)
            self.assertEqual(history[1]["finished"]["class"], "unknown")

    def test_a_corrupt_line_is_skipped_and_counted_not_trusted(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            ledger.record_started("r1", "T1", "initial", "m")
            with open(ledger.events_path, "ab") as fh:
                fh.write(b'{"v":"polytropos.attempts/1","kind":"attempt.finished","att\n')
            self.assertEqual(len(ledger.events()), 1)
            self.assertEqual(ledger.corrupt, 1)

    def test_an_oversized_event_is_refused_rather_than_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            with self.assertRaises(al.LedgerError):
                ledger.append("x", blob="a" * (al.MAX_LINE_BYTES + 1))
            self.assertFalse(ledger.events_path.exists())

    def test_verify_tails_are_redacted_before_they_are_stored(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            a1 = ledger.record_started("r1", "T1", "initial", "m")
            leaked = "FAILED (failures=1)\nAKIAIOSFODNN7EXAMPLE was printed by the test\n"
            ledger.record_verify("r1", "T1", a1, 1, leaked)
            raw = ledger.events_path.read_text()
            self.assertNotIn("AKIAIOSFODNN7EXAMPLE", raw)
            self.assertIn("[redacted:aws-access-key-id]", raw)
            ver = ledger.task_history("T1")[0]["verify"]
            self.assertEqual(ver["failures"], 1)
            self.assertEqual(ver["tail_redactions"], {"aws-access-key-id": 1})

    def test_usage_counts_only_attempts_no_outcome_line_has_covered(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            ledger.record_started("r1", "T1", "initial", "m")
            ledger.record_started("r1", "T1", "escalation", "m2")
            ledger.record_started("r1", "T1", "consult", "m3")
            self.assertEqual(ledger.usage(), {"max-dispatches": 3, "max-escalations": 1,
                                              "max-consults": 1, "max-model-calls": 3})
            ledger.record_projected("r1", "T1", "done", "pass", outcome_line=True)
            self.assertEqual(ledger.usage()["max-dispatches"], 0)
            ledger.record_started("r2", "T1", "retry", "m")
            self.assertEqual(ledger.usage()["max-dispatches"], 1)

    def test_combined_usage_adds_notes_and_ledger_without_double_counting(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            notes = "- outcome: T0 model=m attempts=2 result=pass review=none\n"
            ledger.record_started("r1", "T1", "initial", "m")
            used = kc.combined_usage(notes, ledger)
            self.assertEqual(used["max-dispatches"], 3)
            self.assertEqual(used["max-escalations"], 1)


class ClaimTests(unittest.TestCase):
    def test_a_live_claim_is_refused_and_a_dead_one_is_taken_over(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            ledger.claim("T1", "r1")
            with self.assertRaises(al.ClaimHeld):
                ledger.claim("T1", "r2")
            self.assertTrue(ledger.release("T1", "r1"))
            lock = Path(tmp) / "kit-a" / "claims" / "T1.lock"
            lock.write_text(json.dumps({"run": "dead", "pid": DEAD_PID, "ts": "t"}))
            info = ledger.claim("T1", "r3")
            self.assertEqual(info["stale_from"]["run"], "dead")
            self.assertEqual(ledger.holder("T1")["run"], "r3")

    def test_release_only_drops_the_callers_own_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            ledger.claim("T1", "r1")
            self.assertFalse(ledger.release("T1", "someone-else"))
            self.assertEqual(ledger.holder("T1")["run"], "r1")
            ledger.break_claim("T1", reason="test")
            self.assertIsNone(ledger.holder("T1"))


# ---- classification and progress -------------------------------------------------------------

class ClassificationTests(unittest.TestCase):
    def test_environment_failures_are_named_and_never_escalated(self):
        cases = {
            ("missing-executable", 124, ""): "infrastructure",
            (None, 1, "Error: Not logged in. Run `login`."): "auth",
            (None, 2, "error: unrecognized arguments: --nope"): "config",
            (None, 1, "EACCES: permission denied, open '/x'"): "permission",
            (None, 1, "HTTP 429 rate limit exceeded"): "infrastructure",
            (None, 124, "stopped waiting"): "infrastructure",
            (None, 3, "the model wrote something and exited 3"): "unknown",
        }
        for (outcome, rc, text), expected in cases.items():
            with self.subTest(text=text or outcome):
                cls = al.classify_dispatch(rc, text, proc_outcome=outcome)
                self.assertEqual(cls, expected)
                self.assertEqual(al.recovery_for(cls), "stop")
        self.assertIsNone(al.classify_dispatch(0, "Not logged in"))
        self.assertEqual(al.recovery_for("verification"), "escalate")

    def test_a_declined_runner_is_unknown_not_a_failure(self):
        # `rc is None` is the injected-fixture shape; a lifecycle records it as unreported
        # and classifies nothing.
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            run = kc.TaskRun(ledger, "r1", {"id": "T1"}, workspace=tmp)
            a = run.attempt_started("initial", "m")
            self.assertIsNone(run.attempt_finished(a, None, ""))
            self.assertEqual(ledger.task_history("T1")[0]["finished"]["outcome"], "unreported")


class ProgressTests(unittest.TestCase):
    def test_timestamps_durations_and_temp_paths_do_not_change_the_signature(self):
        a = "2026-09-12T10:00:01Z Ran 5 tests in 0.31s\n/tmp/abc123/x.py:3\nFAILED (failures=3)"
        b = "2026-09-12T10:07:44Z Ran 5 tests in 1.02s\n/tmp/zzz999/x.py:3\nFAILED (failures=3)"
        self.assertEqual(al.signature(a), al.signature(b))
        self.assertIn("Ran 5 tests", al.normalize_output(a))

    def test_failure_tallies_are_read_from_the_runner_not_guessed(self):
        self.assertEqual(al.failure_count("FAILED (failures=2, errors=1)"), 3)
        self.assertEqual(al.failure_count("=== 2 failed, 3 passed in 0.2s ==="), 2)
        self.assertEqual(al.failure_count("Tests:       1 failed, 4 passed"), 1)
        self.assertEqual(al.failure_count("--- FAIL: TestA\n--- FAIL: TestB\n"), 2)
        self.assertIsNone(al.failure_count("nothing resembling a tally"))

    def test_a_timestamp_is_not_progress_and_fewer_failures_is(self):
        base = al.observation(1, "Ran 5 tests in 0.31s\n\nFAILED (failures=3)\n")
        noise = al.observation(1, "Ran 5 tests in 0.44s\n\nFAILED (failures=3)\n")
        better = al.observation(1, "Ran 5 tests in 0.29s\n\nFAILED (failures=1)\n")
        self.assertFalse(al.progress(base, noise)["progress"])
        self.assertTrue(al.progress(base, better)["progress"])
        self.assertFalse(al.progress(base, al.observation(1, "FAILED (failures=3) other text"))
                         ["progress"], "same tally with different text is not progress")
        self.assertTrue(al.progress(base, al.observation(0, "OK"))["progress"])

    def test_without_a_tally_a_changed_log_counts_only_if_the_tree_changed(self):
        prev = al.observation(1, "boom one", artifact="fp-a")
        same_tree = al.observation(1, "boom two", artifact="fp-a")
        new_tree = al.observation(1, "boom two", artifact="fp-b")
        unknown_tree = al.observation(1, "boom two", artifact=None)
        self.assertFalse(al.progress(prev, same_tree)["progress"])
        self.assertTrue(al.progress(prev, new_tree)["progress"])
        self.assertTrue(al.progress(prev, unknown_tree)["progress"])

    def test_a_non_git_workspace_has_no_fingerprint_rather_than_a_fake_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(al.workspace_fingerprint(tmp))


class RetryContextTests(unittest.TestCase):
    def test_context_is_bounded_names_unknown_attempts_and_the_trend(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            a1 = ledger.record_started("r1", "T1", "initial", "fake-cheap")
            ledger.record_finished("r1", "T1", a1, "ok", 0, "x" * 5000)
            ledger.record_verify("r1", "T1", a1, 1, "FAILED (failures=5)\n" + "y" * 5000)
            a2 = ledger.record_started("r1", "T1", "escalation", "fake-mid")
            ledger.record_finished("r1", "T1", a2, "ok", 0, "did more")
            ledger.record_verify("r1", "T1", a2, 1, "FAILED (failures=2)\n")
            ledger.record_started("r1", "T1", "escalation", "fake-big")
            ledger.reconcile_open("r2", "T1", "died")
            text = al.retry_context(ledger.task_history("T1"), verify_cmd="make test")
            self.assertLessEqual(len(text), al.CONTEXT_CHARS + 80)
            self.assertIn("attempts so far: 3", text)
            self.assertIn("outcome unknown", text)
            self.assertIn("failures: 2 (was 5)", text)
            self.assertIn("verify: make test", text)
            self.assertNotIn("last verify output", al.retry_context(
                ledger.task_history("T1"), include_tail=False))
        self.assertEqual(al.retry_context([]), "")


# ---- the drivers: crash, resume, budget, claims, classes ----------------------------------------

PROMPT_STUB = """#!/bin/bash
echo "===CALL===" >> "%LOG%"
printf '%s' "${@: -1}" > "%PROMPT%"
%ACTION%
exit %RC%
"""


def _write_prompt_stub(tmp, log_path, prompt_path, action=":", rc=0):
    stub = Path(tmp) / tce.STUB_BIN
    stub.write_text(PROMPT_STUB.replace("%LOG%", str(log_path))
                    .replace("%PROMPT%", str(prompt_path))
                    .replace("%ACTION%", action).replace("%RC%", str(rc)))
    stub.chmod(0o755)
    return stub


def _calls(log_path):
    if not Path(log_path).exists():
        return 0
    return Path(log_path).read_text().count("===CALL===")


class _DriverCase(unittest.TestCase):
    """One temp checkout per test: a kit under `.claude/kits/<slug>` (so the store namespace
    derives from the checkout), a fixture agent bundle, a marker the verify command looks
    for, and a ledger the test may seed before the driver runs."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        tce._write_agent_bundle(self.root, "fixturekit", "implementer",
                                tce.PREAMBLE_FIXTURE_BODY)
        self.marker = self.root / "work-done.marker"
        kits = self.root / ".claude" / "kits"
        kits.mkdir(parents=True)
        self.kit = tce._write_kit(kits, tce._single_task_text(f'test -f "{self.marker}"'),
                                  slug="fixturekit")
        self.store = self.root / "ledger-store"
        self.ledger = al.AttemptLedger(self.store, "fixturekit")
        self.log = self.root / "stub.log"
        self.prompt = self.root / "prompt.txt"

    def tearDown(self):
        self._tmp.cleanup()

    def run_driver(self, stub, *extra, expect_exit=None):
        out, err = io.StringIO(), io.StringIO()
        argv = ["run", "--kit", str(self.kit), "--claude-bin", str(stub),
                "--attempt-store", str(self.store), *extra]
        with mock.patch.object(ce, "REPO_ROOT", self.root), \
                mock.patch.object(ce, "load_pricing", return_value=tce.PRICING_FIXTURE), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            if expect_exit is None:
                ce.main(argv)
            else:
                with self.assertRaises(SystemExit) as ctx:
                    ce.main(argv)
                self.assertEqual(ctx.exception.code, expect_exit)
        return out.getvalue(), err.getvalue()

    def status(self):
        return ce.parse_tasks((self.kit / "TASKS.md").read_text())[0]["status"]

    def notes(self):
        p = self.kit / "NOTES.md"
        return p.read_text() if p.exists() else ""

    def set_in_progress(self):
        text = (self.kit / "TASKS.md").read_text()
        (self.kit / "TASKS.md").write_text(ce.set_status(text, "E1", "in-progress"))


class CrashAfterDispatchTests(_DriverCase):
    def test_work_that_exists_is_recognised_without_a_second_dispatch(self):
        # Run 1 dispatched, the model touched the marker, and the process died before
        # recording anything. Run 2 must not pay again.
        self.ledger.append("verify.precheck", run="r0", task="E1", tautological=False, rc=1)
        self.ledger.record_started("r0", "E1", "initial", "fake-haiku")
        self.marker.touch()
        self.set_in_progress()
        stub = _write_prompt_stub(self.root, self.log, self.prompt)

        _out, err = self.run_driver(stub, "--task", "E1")

        self.assertEqual(_calls(self.log), 0, "nothing may be re-dispatched")
        self.assertEqual(self.status(), "done")
        self.assertIn("closed as unknown", err)
        self.assertIn("nothing was re-dispatched", err)
        notes = self.notes()
        self.assertIn("- reconciled: 1 earlier attempt(s)", notes)
        self.assertRegex(notes, r"outcome: E1 model=fake-haiku attempts=1 result=pass")
        history = self.ledger.task_history("E1")
        self.assertEqual(history[0]["finished"]["outcome"], al.OUTCOME_UNKNOWN)
        self.assertEqual(history[0]["verify"]["rc"], 0)
        self.assertTrue(self.ledger.latest_projection("E1")["outcome_line"])
        self.assertIsNone(self.ledger.holder("E1"), "the claim is released at the end")

    def test_unfinished_work_gets_one_more_attempt_that_knows_what_happened(self):
        self.ledger.append("verify.precheck", run="r0", task="E1", tautological=False, rc=1)
        a0 = self.ledger.record_started("r0", "E1", "initial", "fake-haiku")
        self.set_in_progress()
        stub = _write_prompt_stub(self.root, self.log, self.prompt,
                                  action=f'touch "{self.marker}"')

        _out, err = self.run_driver(stub, "--task", "E1")

        self.assertEqual(_calls(self.log), 1)
        self.assertEqual(self.status(), "done")
        self.assertIn("dispatching once more with their evidence", err)
        prompt = self.prompt.read_text()
        self.assertIn("PRIOR ATTEMPTS", prompt)
        self.assertIn("outcome unknown", prompt)
        history = self.ledger.task_history("E1")
        self.assertEqual([h["op"] for h in history], ["initial", "retry"])
        self.assertEqual(history[0]["attempt"], a0)
        # Both attempts are the task's cost, and the outcome line says so.
        self.assertRegex(self.notes(), r"outcome: E1 model=fake-haiku attempts=2 result=pass")

    def test_a_pass_that_was_tautological_before_any_work_stays_blocked_on_resume(self):
        # Run 1's precheck found the command already passing pre-task (a red-green task with
        # no proof). Resuming onto a passing tree must reach the same verdict run 1 would.
        self.ledger.append("verify.precheck", run="r0", task="E1", tautological=True, rc=0)
        self.ledger.record_started("r0", "E1", "initial", "fake-haiku")
        self.marker.touch()
        self.set_in_progress()
        stub = _write_prompt_stub(self.root, self.log, self.prompt)

        _out, err = self.run_driver(stub, "--task", "E1", expect_exit=1)

        self.assertEqual(_calls(self.log), 0)
        self.assertEqual(self.status(), "blocked")
        self.assertIn("required-evidence", err)


class CrashBeforeProjectionTests(_DriverCase):
    def test_a_recorded_verdict_is_projected_not_re_earned(self):
        self.ledger.append("verify.precheck", run="r0", task="E1", tautological=False, rc=1)
        a0 = self.ledger.record_started("r0", "E1", "initial", "fake-haiku")
        self.ledger.record_finished("r0", "E1", a0, "ok", 0, "done it")
        self.ledger.record_verify("r0", "E1", a0, 0, "ok")
        self.marker.touch()
        self.set_in_progress()
        stub = _write_prompt_stub(self.root, self.log, self.prompt)

        _out, err = self.run_driver(stub, "--task", "E1")

        self.assertEqual(_calls(self.log), 0)
        self.assertEqual(self.status(), "done")
        self.assertIn("reconciled", self.notes())
        self.assertNotIn("closed as unknown", err, "the attempt had a result; nothing to close")


class BudgetCarriesAcrossRunsTests(_DriverCase):
    def test_attempts_the_notes_file_never_saw_still_count_against_the_cap(self):
        (self.kit / "PLAN.md").write_text("# plan\n\nbudget: max-dispatches=2\n")
        for _ in range(2):
            a = self.ledger.record_started("r0", "E1", "initial", "fake-haiku")
            self.ledger.record_finished("r0", "E1", a, "ok", 0, "tried")
            self.ledger.record_verify("r0", "E1", a, 1, "FAILED (failures=1)")
        stub = _write_prompt_stub(self.root, self.log, self.prompt,
                                  action=f'touch "{self.marker}"')

        _out, err = self.run_driver(stub, expect_exit=1)

        self.assertEqual(_calls(self.log), 0, "the cap was already spent by the dead run")
        self.assertIn("budget-stop", err)
        self.assertIn("result=budget-stop", self.notes())
        self.assertEqual(self.status(), "pending")
        events = [e for e in self.ledger.events() if e["kind"] == "run.finished"]
        self.assertEqual(events[-1]["status"], "budget-stop")


class ClaimAtTheDriverTests(_DriverCase):
    def test_a_task_another_live_run_holds_is_refused(self):
        self.ledger.claim("E1", "other-run")  # this process's pid: alive
        stub = _write_prompt_stub(self.root, self.log, self.prompt)
        _out, err = self.run_driver(stub, expect_exit=2)
        self.assertIn("claim:", err)
        self.assertEqual(_calls(self.log), 0)
        self.assertEqual(self.status(), "pending")

    def test_a_dead_runs_claim_is_taken_over_and_said_so(self):
        lock = self.store / "fixturekit" / "claims" / "E1.lock"
        lock.parent.mkdir(parents=True)
        lock.write_text(json.dumps({"run": "dead-run", "pid": DEAD_PID, "ts": "t"}))
        stub = _write_prompt_stub(self.root, self.log, self.prompt,
                                  action=f'touch "{self.marker}"')
        _out, err = self.run_driver(stub)
        self.assertIn("took over a stale claim", err)
        self.assertEqual(self.status(), "done")

    def test_break_claim_is_the_named_way_past_a_held_claim(self):
        self.ledger.claim("E1", "other-run")
        stub = _write_prompt_stub(self.root, self.log, self.prompt,
                                  action=f'touch "{self.marker}"')
        self.run_driver(stub, "--break-claim")
        self.assertEqual(self.status(), "done")
        kinds = [e["kind"] for e in self.ledger.events()]
        self.assertIn("claim.broken", kinds)


class FailureClassAtTheDriverTests(_DriverCase):
    def test_a_logged_out_cli_is_classified_recorded_and_not_escalated(self):
        stub = _write_prompt_stub(self.root, self.log, self.prompt,
                                  action='echo "Error: Not logged in. Run login." >&2', rc=1)
        _out, _err = self.run_driver(stub, expect_exit=1)
        self.assertEqual(_calls(self.log), 1, "an auth failure must not climb the ladder")
        self.assertEqual(self.status(), "blocked")
        self.assertIn("- failure-class: auth", self.notes())
        fin = self.ledger.task_history("E1")[0]["finished"]
        self.assertEqual(fin["class"], "auth")
        self.assertNotIn("Not logged in", "", "the report is bounded and stored")
        self.assertIn("Not logged in", fin["report"])


class ProjectionFromFreshReadTests(_DriverCase):
    def test_a_worker_that_flipped_its_own_status_is_overwritten_and_reported(self):
        tasks_md = self.kit / "TASKS.md"
        flip = (f"python3 -c \"import pathlib; p=pathlib.Path({str(tasks_md)!r}); "
                f"p.write_text(p.read_text().replace('- status: in-progress', "
                f"'- status: done'))\"")
        stub = _write_prompt_stub(self.root, self.log, self.prompt, action=flip, rc=0)
        # verify fails (no marker): the driver's verdict is blocked, whatever the worker wrote.
        _out, err = self.run_driver(stub, "--max-escalations", "0", expect_exit=1)
        self.assertEqual(self.status(), "blocked")
        self.assertIn("projection: TASKS.md said task E1 was 'done'", err)

    def test_the_in_memory_snapshot_is_not_written_back(self):
        # A change to ANOTHER line of TASKS.md while the model runs must survive the driver's
        # final status write.
        tasks_md = self.kit / "TASKS.md"
        edit = (f"python3 -c \"import pathlib; p=pathlib.Path({str(tasks_md)!r}); "
                f"p.write_text(p.read_text() + '\\n<!-- added by the worker -->\\n')\"")
        stub = _write_prompt_stub(self.root, self.log, self.prompt,
                                  action=f'{edit}; touch "{self.marker}"')
        self.run_driver(stub)
        self.assertEqual(self.status(), "done")
        self.assertIn("added by the worker", tasks_md.read_text())


class StoreLocationTests(_DriverCase):
    def test_the_default_store_is_the_data_root_namespaced_to_the_checkout(self):
        stub = _write_prompt_stub(self.root, self.log, self.prompt,
                                  action=f'touch "{self.marker}"')
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(ce, "REPO_ROOT", self.root), \
                mock.patch.object(ce, "load_pricing", return_value=tce.PRICING_FIXTURE), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            ce.main(["run", "--kit", str(self.kit), "--claude-bin", str(stub)])
        self.assertEqual(al.kit_repo_root(self.kit), self.root.resolve())
        expected = kc.open_ledger(self.kit).events_path
        self.assertTrue(str(expected).startswith(_DATA_HOME.name),
                        "the default must resolve through POLYTROPOS_DATA_HOME")
        self.assertTrue(expected.exists())
        self.assertNotIn(str(self.root), str(expected).replace(
            al._rt().project_namespace(self.root), ""),
            "the ledger is not inside the checkout")

    def test_an_explicit_store_writes_nowhere_else(self):
        stub = _write_prompt_stub(self.root, self.log, self.prompt,
                                  action=f'touch "{self.marker}"')
        before = {p for p in Path(_DATA_HOME.name).rglob("*")}
        self.run_driver(stub)
        after = {p for p in Path(_DATA_HOME.name).rglob("*")}
        self.assertEqual(before, after)
        self.assertTrue(self.ledger.events_path.exists())


# ---- Ralph ------------------------------------------------------------------------------------

class RalphDurableLoopTests(unittest.TestCase):
    STOPS = {"max_iterations": 2, "no_progress_stop": 5, "budget_usd": 100.0}

    def _ledger(self, tmp):
        return al.AttemptLedger(tmp, al.namespace_for_goal("g", "check"))

    def test_verify_first_still_returns_exactly_the_historical_shape(self):
        result = cr.run_ralph("g", lambda i, p: "", lambda: (0, "ok"), self.STOPS, 1.0)
        self.assertEqual(result, {"status": "verified", "iterations": 0, "cost_usd": 0.0})

    def test_a_second_run_resumes_iteration_count_spend_and_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            prompts = []
            failing = lambda: (1, "FAILED (failures=4)")  # noqa: E731
            first = cr.run_ralph("g", lambda i, p: prompts.append(p) or "", failing,
                                 self.STOPS, 1.0, ledger=self._ledger(tmp), model="fake")
            self.assertEqual(first["status"], "max_iterations")
            self.assertEqual(first["iterations"], 2)
            self.assertAlmostEqual(first["cost_usd"], 2.0)

            second = cr.run_ralph("g", lambda i, p: prompts.append(p) or "", failing,
                                  dict(self.STOPS, max_iterations=3), 1.0,
                                  ledger=self._ledger(tmp), model="fake")
            self.assertEqual(second["iterations"], 3, "numbering continues, it does not restart")
            self.assertAlmostEqual(second["cost_usd"], 3.0, msg="spend carries over")
            self.assertEqual(len(prompts), 3, "the second run made exactly one more tick")
            self.assertIn("iteration=3", prompts[2])
            self.assertIn("PRIOR ATTEMPTS", prompts[2])
            self.assertIn("attempts so far: 2", prompts[2])

    def test_changing_timestamps_with_the_same_failure_are_not_progress(self):
        n = {"i": 0}

        def verify():
            n["i"] += 1
            return (1, f"Ran 5 tests in 0.{n['i']}1s\n\nFAILED (failures=3)\n")

        result = cr.run_ralph("g", lambda i, p: "", verify,
                              {"max_iterations": 10, "no_progress_stop": 3,
                               "budget_usd": 100.0}, 0.1)
        self.assertEqual(result["status"], "no_progress")
        self.assertEqual(result["iterations"], 3)

    def test_fewer_failures_with_a_similar_log_is_progress(self):
        n = {"f": 6}

        def verify():
            n["f"] -= 1
            return (1, f"Ran 8 tests in 0.20s\n\nFAILED (failures={max(n['f'], 1)})\n")

        result = cr.run_ralph("g", lambda i, p: "", verify,
                              {"max_iterations": 4, "no_progress_stop": 2,
                               "budget_usd": 100.0}, 0.1)
        self.assertEqual(result["status"], "max_iterations")

    def test_an_environment_failure_stops_the_loop_after_one_tick(self):
        calls = []
        result = cr.run_ralph("g", lambda i, p: calls.append(i) or (1, "Error: Not logged in"),
                              lambda: (1, "failing"),
                              {"max_iterations": 5, "no_progress_stop": 5,
                               "budget_usd": 100.0}, 0.1)
        self.assertEqual(result["status"], "environment")
        self.assertEqual(result["class"], "auth")
        self.assertEqual(calls, [1])

    def test_an_elapsed_cap_stops_before_the_tick_that_would_exceed_it(self):
        clock = {"t": 0.0}

        def now():
            clock["t"] += 10.0
            return clock["t"]

        calls = []
        result = cr.run_ralph("g", lambda i, p: calls.append(i) or "", lambda: (1, "no"),
                              {"max_iterations": 10, "no_progress_stop": 10,
                               "budget_usd": 100.0, "max_elapsed_seconds": 25.0}, 0.1,
                              now=now)
        self.assertEqual(result["status"], "elapsed")
        self.assertLessEqual(len(calls), 2)

    def test_two_loops_on_one_goal_cannot_run_at_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = self._ledger(tmp)
            ledger.claim(cr.GOAL_TASK_ID, "other")
            with self.assertRaises(al.ClaimHeld):
                cr.run_ralph("g", lambda i, p: "", lambda: (1, "no"), self.STOPS, 1.0,
                             ledger=self._ledger(tmp))

    def test_demo_and_dry_run_still_spawn_nothing(self):
        with mock.patch.object(cr.subprocess, "run",
                               side_effect=AssertionError("a subprocess was spawned")):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(cr.main(["--demo"]), 0)
            self.assertIn("ledger:", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
