"""bin/cursor_execute.py (step 23): a kit run through a stub Cursor, end to end.

SAFETY CONTRACT. No test here runs Cursor's `agent` or any binary resolved off PATH: every
dispatch goes to a throwaway shell script in a temp dir, named explicitly by `--cursor-bin`,
that answers `--version` like Cursor (or deliberately does not), logs its argv, and prints a
JSON object. The attempt ledger is pointed at a temp store by `--attempt-store`, and the
per-user data root is patched to a temp dir for the whole module. The real bundle under
`cursor/agents/` is read (never written) for the prompt preamble. `--dry-run` is proven to
spawn nothing, not even the identity probe.
"""

import contextlib
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_cursor_execute_test",
                                                  BIN_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ce = _load("cursor_execute")
kc = _load("kit_contract")
al = _load("attempt_ledger")

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


CURSOR_VERSION = "cursor-agent 2026.09.01-stub"
OTHER_VERSION = "acme-agent 3.1"

STUB = """#!/bin/sh
if [ "$1" = "--version" ]; then printf '%s\\n' "%VERSION%"; exit 0; fi
if [ "$1" = "about" ]; then printf '{}\\n'; exit 0; fi
if [ "$1" = "models" ]; then printf 'stub-model-a\\n'; exit 0; fi
printf '===CALL===\\n' >> "%LOG%"
for a in "$@"; do printf '%s\\n' "$a" >> "%LOG%"; done
eval "last=\\${$#}"
printf '%s' "$last" > "%PROMPT%"
%ACTION%
printf '%s\\n' '%OUTPUT%'
exit %RC%
"""


def _task_text(verify_cmd, task_id="E1", model=None):
    model_line = f"- model: {model}\n" if model else ""
    return (
        f"## Phase 1 — Only phase\n\n### {task_id} — Fixture task\n- status: pending\n"
        f"{model_line}- depends: (none)\n- independent: yes\n- evidence: regression\n\n"
        f"**Brief.** Fixture brief for the stub run.\n\n**Acceptance.** Fixture acceptance.\n\n"
        f"**Verify.**\n```bash\n{verify_cmd}\n```\n"
    )


def _calls(log):
    return Path(log).read_text().count("===CALL===") if Path(log).exists() else 0


def _flag_value(log, flag):
    lines = Path(log).read_text().splitlines()
    return lines[lines.index(flag) + 1] if flag in lines else None


class _Case(unittest.TestCase):
    """A temp checkout holding a kit under `.claude/kits/fixturekit`, a marker the verify
    command looks for, a stub `agent`, and a temp ledger store."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.marker = self.root / "work-done.marker"
        kits = self.root / ".claude" / "kits"
        kits.mkdir(parents=True)
        self.kit = kits / "fixturekit"
        self.kit.mkdir()
        (self.kit / "TASKS.md").write_text(_task_text(f'test -f "{self.marker}"'))
        self.store = self.root / "ledger-store"
        self.log = self.root / "stub.log"
        self.prompt = self.root / "prompt.txt"

    def tearDown(self):
        self._tmp.cleanup()

    def stub(self, version=CURSOR_VERSION, action=":", rc=0,
             output='{"model": "stub-model", "result": "done"}', name="stub-agent"):
        path = self.root / name
        path.write_text(STUB.replace("%VERSION%", version).replace("%LOG%", str(self.log))
                        .replace("%PROMPT%", str(self.prompt)).replace("%ACTION%", action)
                        .replace("%OUTPUT%", output).replace("%RC%", str(rc)))
        path.chmod(0o755)
        return path

    def run_driver(self, stub, *extra, command="run", expect_exit=None):
        out, err = io.StringIO(), io.StringIO()
        argv = [command, "--kit", str(self.kit), "--cursor-bin", str(stub),
                "--attempt-store", str(self.store), *extra]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            if expect_exit is None:
                ce.main(argv)
            else:
                with self.assertRaises(SystemExit) as ctx:
                    ce.main(argv)
                self.assertEqual(ctx.exception.code, expect_exit, err.getvalue())
        return out.getvalue(), err.getvalue()

    def status(self):
        return ce.parse_tasks((self.kit / "TASKS.md").read_text())[0]["status"]

    def notes(self):
        p = self.kit / "NOTES.md"
        return p.read_text() if p.exists() else ""

    def snapshot(self):
        return {p.name: p.read_bytes() for p in self.kit.iterdir() if p.is_file()}

    def ledger(self):
        return al.AttemptLedger(self.store, "fixturekit")


class DryRunTests(_Case):
    def test_dry_run_prints_the_argv_and_spawns_nothing_not_even_the_probe(self):
        before = self.snapshot()
        with mock.patch.object(ce, "identify", side_effect=AssertionError("probed")), \
                mock.patch.object(ce, "default_runner", side_effect=AssertionError("ran")):
            out, _err = self.run_driver(self.root / "never-created", "--dry-run",
                                        "--model", "m-x")
        self.assertIn("dispatch: ", out)
        self.assertIn("--force", out)
        self.assertIn("--output-format json", out)
        self.assertIn("--model m-x", out)
        self.assertIn("identity: not probed", out)
        self.assertIn("usd: null", out)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.store.exists())


class IdentityRefusalTests(_Case):
    def test_a_binary_that_is_not_cursor_is_refused_before_any_write(self):
        before = self.snapshot()
        stub = self.stub(version=OTHER_VERSION)
        _out, err = self.run_driver(stub, expect_exit=2)
        self.assertIn("cursor identity is unknown", err)
        self.assertEqual(_calls(self.log), 0, "no dispatch to an unidentified binary")
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.store.exists(), "refused before the ledger was opened")

    def test_an_absent_binary_is_refused_the_same_way(self):
        _out, err = self.run_driver(self.root / "missing-agent", expect_exit=2)
        self.assertIn("cursor identity is absent", err)
        self.assertEqual(self.status(), "pending")

    def test_probe_answers_without_a_kit(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ce.main(["probe", "--cursor-bin", str(self.stub()), "--models"])
        self.assertIn("cursor identity: cursor", buf.getvalue())
        self.assertIn("stub-model-a", buf.getvalue())
        with self.assertRaises(SystemExit) as ctx, contextlib.redirect_stdout(io.StringIO()):
            ce.main(["probe", "--cursor-bin", str(self.stub(version=OTHER_VERSION,
                                                              name="other"))])
        self.assertEqual(ctx.exception.code, 3)


class ReadyTaskTests(_Case):
    def test_a_ready_task_is_dispatched_once_verified_and_projected_done(self):
        before = (self.kit / "TASKS.md").read_text()
        stub = self.stub(action=f'touch "{self.marker}"')
        out, err = self.run_driver(stub)
        self.assertEqual(_calls(self.log), 1)
        self.assertEqual(self.status(), "done")
        self.assertIn("cursor: cursor (cursor-agent", err)
        self.assertIn("task E1: done", out)
        self.assertIn("observed=stub-model", out)
        self.assertIn("usd=null", out)
        after = (self.kit / "TASKS.md").read_text()
        diffs = [(a, b) for a, b in zip(before.splitlines(), after.splitlines()) if a != b]
        self.assertEqual(diffs, [("- status: pending", "- status: done")])
        # The argv is Cursor's headless write form.
        log = self.log.read_text().splitlines()
        self.assertEqual(log[1:5], ["-p", "--output-format", "json", "--trust"])
        self.assertEqual(_flag_value(self.log, "--workspace"), str(Path.cwd()))
        self.assertIn("--force", log)
        self.assertNotIn("--mode", log)
        self.assertNotIn("--model", log, "an unpinned task uses the host default")
        # The prompt carries the id preamble and the implementer role body.
        prompt = self.prompt.read_text()
        self.assertIn("task=E1", prompt)
        self.assertIn("You implement ONE task", prompt)
        self.assertNotIn("{{POLYTROPOS_ROOT}}", prompt)
        # NOTES.md: the generic run block, unpriced.
        notes = self.notes()
        self.assertIn("- harness: cursor", notes)
        self.assertIn("- observed model: stub-model", notes)
        self.assertIn("- usd: null (unpriced", notes)
        self.assertRegex(notes, r"outcome: E1 model=unpinned attempts=1 result=pass "
                                r"review=none run=\d{4}-\d{2}-\d{2}-[0-9a-f]{4}")
        # The ledger: one attempt, recorded before and after, verify recorded, claim released.
        history = self.ledger().task_history("E1")
        self.assertEqual([h["op"] for h in history], ["initial"])
        self.assertEqual(history[0]["finished"]["outcome"], "ok")
        self.assertEqual(history[0]["finished"].get("observed_model"), "stub-model")
        self.assertEqual(history[0]["verify"]["rc"], 0)
        self.assertIsNone(self.ledger().holder("E1"))
        kinds = [e["kind"] for e in self.ledger().events()]
        self.assertIn("roster.checked", kinds)
        self.assertIn("run.finished", kinds)
        self.assertIn("claim.released", kinds)

    def test_model_flag_is_passed_through_verbatim_and_pins_win_over_nothing(self):
        (self.kit / "TASKS.md").write_text(_task_text(f'test -f "{self.marker}"',
                                                      model="pinned-model"))
        stub = self.stub(action=f'touch "{self.marker}"')
        self.run_driver(stub)
        self.assertEqual(_flag_value(self.log, "--model"), "pinned-model")
        self.assertIn("- planned model: pinned-model", self.notes())
        self.assertRegex(self.notes(), r"outcome: E1 model=pinned-model attempts=1")

    def test_an_explicit_model_overrides_the_pin(self):
        (self.kit / "TASKS.md").write_text(_task_text(f'test -f "{self.marker}"',
                                                      model="pinned-model"))
        stub = self.stub(action=f'touch "{self.marker}"')
        self.run_driver(stub, "--model", "override-model")
        self.assertEqual(_flag_value(self.log, "--model"), "override-model")
        self.assertIn("- model used: override-model", self.notes())

    def test_extra_args_that_would_change_the_recorded_choice_are_refused_before_probe(self):
        stub = self.stub()
        _out, err = self.run_driver(stub, "--extra-arg=--force", expect_exit=2)
        self.assertIn("would override", err)
        self.assertEqual(_calls(self.log), 0)
        self.assertEqual(self.status(), "pending")


class FailureTests(_Case):
    def test_a_dispatch_failure_is_classified_blocked_and_never_verified(self):
        stub = self.stub(rc=2, output="something went wrong")
        out, _err = self.run_driver(stub, expect_exit=1)
        self.assertEqual(self.status(), "blocked")
        self.assertIn("verify_rc=None", out)
        notes = self.notes()
        self.assertIn("- dispatch: exit 2", notes)
        self.assertIn("- failure-class:", notes)
        self.assertIn("- verify: exit None", notes)
        self.assertRegex(notes, r"outcome: E1 model=unpinned attempts=1 result=blocked")
        history = self.ledger().task_history("E1")
        self.assertEqual(history[0]["finished"]["rc"], 2)
        self.assertIsNone(history[0].get("verify"))

    def test_a_verification_failure_blocks_after_one_attempt_there_is_no_ladder(self):
        stub = self.stub()  # never touches the marker
        out, _err = self.run_driver(stub, expect_exit=1)
        self.assertEqual(_calls(self.log), 1, "one dispatch: Cursor has no tier ladder")
        self.assertEqual(self.status(), "blocked")
        self.assertIn("verify_rc=1", out)
        notes = self.notes()
        self.assertIn("- verify: exit 1", notes)
        self.assertIn("- escalations: (none)", notes)
        self.assertRegex(notes, r"attempts=1 result=blocked")

    def test_a_logged_out_cli_is_named_and_recorded(self):
        stub = self.stub(rc=1, output="Error: not logged in. Run agent login first")
        self.run_driver(stub, expect_exit=1)
        self.assertIn("- failure-class: auth", self.notes())


class BudgetStopTests(_Case):
    def test_a_reached_plan_budget_stops_before_the_probe_and_the_dispatch(self):
        (self.kit / "PLAN.md").write_text("# plan\n\nbudget: max-dispatches=1\n")
        (self.kit / "NOTES.md").write_text(
            "## 2026-07-25T00:00:00Z — E0\n"
            "- outcome: E0 model=x attempts=1 result=pass review=none run=2026-07-25-1234\n")
        stub = self.stub(action=f'touch "{self.marker}"')
        before_tasks = (self.kit / "TASKS.md").read_text()
        _out, err = self.run_driver(stub, expect_exit=1)
        self.assertIn("budget-stop", err)
        self.assertIn("max-dispatches", err)
        self.assertEqual(_calls(self.log), 0)
        self.assertEqual((self.kit / "TASKS.md").read_text(), before_tasks)
        self.assertRegex(self.notes(), r"outcome: E1 model=unpinned attempts=0 "
                                       r"result=budget-stop review=none run=\d{4}")
        self.assertIsNone(self.ledger().holder("E1"))

    def test_a_budget_stop_never_displaces_a_recorded_verdict(self):
        (self.kit / "PLAN.md").write_text("budget: max-dispatches=1\n")
        (self.kit / "NOTES.md").write_text(
            "## 2026-07-25T00:00:00Z — E1\n"
            "- outcome: E1 model=x attempts=1 result=blocked review=none run=2026-07-25-1234\n")
        _out, err = self.run_driver(self.stub(), "--task", "E1", expect_exit=1)
        self.assertIn("NOT recorded in the ledger", err)
        self.assertEqual(self.notes().count("result=budget-stop"), 0)


class ResumeTests(_Case):
    def test_work_a_dead_run_left_is_recognised_without_a_second_dispatch(self):
        ledger = self.ledger()
        ledger.append("verify.precheck", run="r0", task="E1", tautological=False, rc=1)
        ledger.record_started("r0", "E1", "initial", None)
        self.marker.touch()
        text = (self.kit / "TASKS.md").read_text()
        (self.kit / "TASKS.md").write_text(ce.set_status(text, "E1", "in-progress"))
        stub = self.stub()
        _out, err = self.run_driver(stub, "--task", "E1")
        self.assertEqual(_calls(self.log), 0, "nothing may be re-dispatched")
        self.assertEqual(self.status(), "done")
        self.assertIn("nothing was re-dispatched", err)
        notes = self.notes()
        self.assertIn("- reconciled: 1 earlier attempt(s)", notes)
        self.assertIn("- harness: cursor", notes)
        self.assertRegex(notes, r"outcome: E1 model=unpinned attempts=1 result=pass")
        history = self.ledger().task_history("E1")
        self.assertEqual(history[0]["finished"]["outcome"], al.OUTCOME_UNKNOWN)
        self.assertEqual(history[0]["verify"]["rc"], 0)

    def test_unfinished_work_gets_one_more_attempt_that_carries_the_evidence(self):
        ledger = self.ledger()
        ledger.append("verify.precheck", run="r0", task="E1", tautological=False, rc=1)
        ledger.record_started("r0", "E1", "initial", None)
        text = (self.kit / "TASKS.md").read_text()
        (self.kit / "TASKS.md").write_text(ce.set_status(text, "E1", "in-progress"))
        stub = self.stub(action=f'touch "{self.marker}"')
        _out, err = self.run_driver(stub, "--task", "E1")
        self.assertEqual(_calls(self.log), 1)
        self.assertEqual(self.status(), "done")
        self.assertIn("dispatching once more with their evidence", err)
        self.assertIn("PRIOR ATTEMPTS", self.prompt.read_text())
        self.assertEqual([h["op"] for h in self.ledger().task_history("E1")],
                         ["initial", "retry"])
        self.assertRegex(self.notes(), r"attempts=2 result=pass")

    def test_a_task_another_live_run_holds_is_refused(self):
        self.ledger().claim("E1", "r-live")
        before = self.snapshot()
        _out, err = self.run_driver(self.stub(), "--task", "E1", expect_exit=2)
        self.assertIn("r-live", err)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(_calls(self.log), 0)


class RosterTests(_Case):
    def test_a_declared_role_cursor_cannot_run_stops_before_any_write(self):
        (self.kit / "PLAN.md").write_text("# plan\nroles: test-author\n")
        before = self.snapshot()
        _out, err = self.run_driver(self.stub(), expect_exit=2)
        self.assertIn("gap: test-author is not executed by this driver", err)
        self.assertIn("--roster-gap disclose", err)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(_calls(self.log), 0)
        self.assertFalse(self.store.exists())

    def test_disclose_proceeds_with_the_gap_recorded(self):
        (self.kit / "PLAN.md").write_text("# plan\nroles: test-author\n")
        stub = self.stub(action=f'touch "{self.marker}"')
        _out, err = self.run_driver(stub, "--roster-gap", "disclose")
        self.assertIn("proceeding WITHOUT test-author", err)
        self.assertEqual(self.status(), "done")
        checked = [e for e in self.ledger().events() if e["kind"] == "roster.checked"]
        self.assertEqual(len(checked), 1)
        self.assertEqual(checked[0]["executor"], "cursor")
        self.assertIn("test-author", checked[0]["gap"])

    def test_status_names_cursor_as_executor_with_its_partial_verifier(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ce.main(["status", "--kit", str(self.kit)])
        self.assertIn("roster: workflow=reviewed roles=implementer,verifier,reviewer",
                      out.getvalue())
        # The executor's own support is stated when a run is previewed.
        out, err = self.run_driver(self.root / "unused", "--dry-run")
        self.assertIn("executor=cursor", out + err)
        self.assertIn("partial: verifier", out + err)
        self.assertEqual(kc.ROLE_SUPPORT["cursor"]["reviewer"][0], "sequenced")
        self.assertEqual(kc.ROLE_SUPPORT["cursor"]["test-author"][0], "unsupported")


class ReviewTests(_Case):
    def test_a_review_is_read_only_recorded_and_leaves_the_kit_alone(self):
        before = self.snapshot()
        stub = self.stub()
        out, _err = self.run_driver(stub, "--phase", "1", command="review")
        log = self.log.read_text().splitlines()
        self.assertEqual(_flag_value(self.log, "--mode"), "ask")
        self.assertNotIn("--force", log)
        self.assertIn("Review phase 1", self.prompt.read_text())
        self.assertIn("change nothing", self.prompt.read_text())
        self.assertIn("stub-model", out)
        self.assertEqual(self.snapshot(), before, "a review projects nothing into the kit")
        history = self.ledger().task_history("phase-1")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["op"], "review")
        self.assertEqual(history[0]["finished"]["observed_model"], "stub-model")
        started = [e for e in self.ledger().events()
                   if e["kind"] == "attempt.started" and e["task"] == "phase-1"]
        self.assertEqual(started[0]["role"], "reviewer")
        self.assertEqual(started[0]["actor"], "cursor")

    def test_a_review_dry_run_spawns_nothing(self):
        with mock.patch.object(ce, "identify", side_effect=AssertionError("probed")):
            out, _err = self.run_driver(self.root / "never", "--phase", "2", "--dry-run",
                                        command="review")
        self.assertIn("--mode ask", out)
        self.assertEqual(_calls(self.log), 0)

    def test_a_review_by_a_non_cursor_binary_is_refused(self):
        _out, err = self.run_driver(self.stub(version=OTHER_VERSION), "--phase", "1",
                                    command="review", expect_exit=2)
        self.assertIn("cursor identity is unknown", err)
        self.assertFalse(self.store.exists())


class SourceHygieneTests(unittest.TestCase):
    def test_the_driver_reuses_the_contract_and_carries_no_process_primitive(self):
        source = (BIN_DIR / "cursor_execute.py").read_text()
        for banned in ("import subprocess", "os.system", "Path.home(", "sqlite3"):
            self.assertNotIn(banned, source)
        for reused in ("roster_for_run", "exit_if_invalid_graph", "start_task_lifecycle",
                       "budget_gate", "reconcile_task", "finish_task_projection",
                       "append_run_note", "record_role_dispatch", "verify_runner"):
            self.assertIn(reused, source, f"{reused} must come from the shared runtime")
        for ladder in ("escalation_ladder", "max_escalations", "next_rung", "tier_of"):
            self.assertNotIn(ladder, source, "no ladder of its own")
        self.assertEqual(ce.CONTRACT_VERSION, kc.CONTRACT_VERSION)
        self.assertEqual(ce.parse_tasks.__module__, "kit_contract")

    def test_help_runs_offline(self):
        with self.assertRaises(SystemExit) as ctx, contextlib.redirect_stdout(io.StringIO()):
            ce.main(["--help"])
        self.assertEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
