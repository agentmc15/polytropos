"""D05 -- duration coverage for the decision-improvement-v1 kit.

`DurationCoverageTests` proves the four boundaries named by D03's authority inventory
(`docs/DECISION-IMPROVEMENT-AUTHORITY-INVENTORY.md`, "Duration coverage") are closed, and that
nothing along the way turns "never measured" into "measured zero":

  1. `kit_contract.provider_runner`'s `default_runner` (bound by `claude_execute.py` and
     `copilot_execute.py`) now returns `(rc, output, timing)`; `dispatch_status` normalises
     every raw shape a runner can return and never invents a timing dict.
  2. `codex_execute.default_runner` is its OWN runner, not `provider_runner` -- widening the
     shared function alone would leave Codex silently unfixed. It is proven here with a REAL
     dispatch through a temp stub script and the real `proc_runner`, not an injected double,
     because that is the one boundary a mock could paper over.
  3. `cursor_execute.run_task` already had the timing dict in hand (`proc`) and only dropped
     the one field; `kit_scheduler.Scheduler._work` had the identical omission, found while
     verifying the "four boundaries" claim structurally rather than by grep -- a fifth,
     unnamed instance of the same defect, closed the same way.
  4. `attempt_history` had no field for duration at all; `RECORD_FIELDS`/`observe`/`summarize`/
     `duration_totals`/`render_markdown` now carry and count it, on the `cost_totals` precedent
     the authority inventory names: bases are separate facts, never summed together.

Also covered: `record_role_dispatch` (a review/consult dispatch is a real process with real
timing, and had no way to record it at all); a crash-closed attempt and a pre-existing event
both keep duration unknown, never zero; a resumed run reprojects a previously recorded duration
rather than re-dispatching; `workflow_eval`'s three `wall_seconds` zero-coercions (rec init,
kit-stage init, variant aggregate) now report `None` for a trial that never dispatched, both at
the aggregate level (a pure-function test) and the seed level (one real, offline `Evaluation`
whose only trial is refused by routing before any sandbox or dispatch exists).

Not touched, and named rather than fixed (out of this task's path -- "own attempt projection",
not Ralph's own budget/runway arithmetic): `copilot_ralph._prior_state`'s two zero-coercions at
`cost += float(fin.get("cost_usd") or 0.0)` and `elapsed += float(fin.get("duration_s") or
0.0)`. `cost_usd`/`elapsed_s` feed `run_ralph`'s own budget comparisons and `f"{...:.4f}"`
formatting as real numbers throughout that function; making them `None`-safe there is a
restructuring of Ralph's stop-condition and runway logic, not a duration-projection fix, and
risks a real financial-safety regression if done carelessly. No test here asserts either
zero-coercion is correct; asserting it would bless it rather than merely leave it alone.

============================================================================================
 SAFETY CONTRACT
============================================================================================
No test here invokes a real `claude`/`codex`/`copilot`/`cursor`/`graphify` binary or touches a
real `~/.claude`/`~/.codex`/`~/.copilot` home. Every ledger lives in a
`tempfile.TemporaryDirectory()`, and `POLYTROPOS_DATA_HOME` is pinned to a temp directory for
the whole module (the seam `tests/test_attempt_ledger.py` and `tests/test_decision_provenance.py`
already use) so no default store can ever resolve into the real per-user data root. The three
dispatches that go through the real `proc_runner` (`kit_contract.provider_runner`, Codex's own
`default_runner`, and `kit_scheduler.StubDispatcher`) each run a throwaway shell script this
file writes into its own temp directory, never a name resolved off PATH and never anything
claiming to be a real harness.
`workflow_eval`'s one real `Evaluation` run dispatches nothing at all: its only trial is refused
by routing before any sandbox is built.
"""

import ast
import importlib.util
import io
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import test_claude_execute as tce
import test_codex_execute_policy as tcep
import test_copilot_execute as tcp
import test_workflow_eval as twe

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_duration_test", BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


al = _load("attempt_ledger")
kc = _load("kit_contract")
ah = _load("attempt_history")
pr = _load("proc_runner")
cex = _load("codex_execute")
cux = _load("cursor_execute")
ks = _load("kit_scheduler")

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


#: A task as `kit_contract.parse_tasks` would produce one -- shared by the claude/cursor
#: fixtures below (codex reuses `test_codex_execute_policy.task()` for its own tier pricing).
FIXTURE_TASK = {
    "id": "T1", "title": "fixture", "status": "pending", "model": "fake-haiku",
    "depends": [], "independent": True, "evidence": None,
    "brief": "do the fixture thing", "acceptance": "The fixture thing is done and says so.",
    "verify": "true",
}


class DurationCoverageTests(unittest.TestCase):

    # ---- the shared normaliser --------------------------------------------------------------

    def test_dispatch_status_normalises_all_three_raw_shapes_and_never_invents_timing(self):
        # None: the injected-fixture shape every pre-existing test's runner returns.
        self.assertEqual(kc.dispatch_status(None), (None, "", {}))
        # A 2-tuple: no timing was ever offered, so `timing` is `{}` -- unmeasured, not zero.
        self.assertEqual(kc.dispatch_status((1, "boom")), (1, "boom", {}))
        self.assertEqual(kc.dispatch_status((0, None)), (0, "", {}))
        # A 3-tuple carrying a real `proc_runner`-shaped dict.
        timing = {"duration_s": 4.5, "outcome": "ok", "terminal": True}
        self.assertEqual(kc.dispatch_status((0, "hi", timing)), (0, "hi", timing))
        # A non-dict third element is defensive: it normalises to `{}` rather than being
        # trusted as a timing dict it structurally cannot be.
        self.assertEqual(kc.dispatch_status((1, "x", "not-a-dict")), (1, "x", {}))

    def test_provider_runner_now_returns_the_full_proc_runner_result_as_its_third_element(self):
        # Boundary 1 (claude, copilot): `kit_contract.provider_runner`'s `default_runner` used
        # to discard everything `proc_runner` measured. A real dispatch of an instant stub
        # proves the third element is the timing dict, not a placeholder.
        runner = kc.provider_runner("claude")
        with tempfile.TemporaryDirectory() as tmp:
            stub = Path(tmp) / "stub.sh"
            stub.write_text("#!/bin/sh\necho hi\nexit 0\n")
            stub.chmod(0o755)
            rc, output, timing = runner([str(stub)], cwd=tmp)
        self.assertEqual(rc, 0)
        self.assertIn("hi", output)
        self.assertIsInstance(timing["duration_s"], float)
        self.assertGreaterEqual(timing["duration_s"], 0.0)
        self.assertEqual(timing["outcome"], pr.OUTCOME_OK)

    # ---- claude and copilot (boundary 1) ----------------------------------------------------

    def test_claude_records_measured_duration_and_the_precise_timeout_outcome(self):
        ce = tce.ce
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-claude")
            lifecycle = kc.TaskRun(ledger, "r1", dict(FIXTURE_TASK), workspace=tmp)
            # A real proc_runner timeout (`OUTCOME_TIMEOUT`) is the shape a stalled dispatch
            # returns; the injected runner reproduces exactly the tuple `provider_runner` now
            # emits, per the brief's "timeout, cancellation" requirement.
            timing = {"duration_s": 12.5, "outcome": pr.OUTCOME_TIMEOUT, "timed_out": True}
            runner = mock.Mock(return_value=(pr.INFRASTRUCTURE_RC, "stalled", timing))
            result = ce.run_task(dict(FIXTURE_TASK), tce.PRICING_FIXTURE, runner,
                                 mock.Mock(), claude_bin=tce.STUB_BIN, lifecycle=lifecycle)
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["failure"], "dispatch")
            history = ledger.task_history("T1")
            self.assertEqual(len(history), 1)
            finished = history[0]["finished"]
            self.assertEqual(finished["duration_s"], 12.5)
            self.assertEqual(finished["outcome"], pr.OUTCOME_TIMEOUT)
            self.assertEqual(finished["class"], "infrastructure")
            self.assertEqual(al.recovery_for(finished["class"]), "stop")

    def test_copilot_records_measured_duration_and_the_precise_cancelled_outcome(self):
        ce = tcp.ce
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-copilot")
            task = dict(FIXTURE_TASK, model="fake-cheap")
            lifecycle = kc.TaskRun(ledger, "r1", task, workspace=tmp)
            timing = {"duration_s": 3.0, "outcome": pr.OUTCOME_CANCELLED}
            runner = mock.Mock(return_value=(pr.INFRASTRUCTURE_RC, "killed", timing))
            result = ce.run_task(task, tcp.PRICING_FIXTURE, runner, mock.Mock(),
                                 lifecycle=lifecycle)
            self.assertEqual(result["status"], "blocked")
            history = ledger.task_history("T1")
            finished = history[0]["finished"]
            self.assertEqual(finished["duration_s"], 3.0)
            self.assertEqual(finished["outcome"], pr.OUTCOME_CANCELLED)
            self.assertEqual(finished["class"], "infrastructure")

    # ---- codex (boundary 2 -- shown, not asserted around) -----------------------------------

    def test_codex_default_runner_carries_proc_runners_duration_in_its_own_telemetry(self):
        # This is THE claim D03/the brief singled out: `codex_execute.default_runner` is its
        # own runner and widening `provider_runner` does not reach it. Proven with a REAL
        # dispatch through the real `proc_runner`, not a mock, so there is nothing left to
        # paper over.
        with tempfile.TemporaryDirectory() as tmp:
            stub = Path(tmp) / "codex-stub.sh"
            stub.write_text("#!/bin/sh\necho 'not a json event'\nexit 0\n")
            stub.chmod(0o755)
            rc, output, telemetry = cex.default_runner([str(stub)], cwd=tmp)
        self.assertEqual(rc, 0)
        self.assertIsInstance(telemetry, dict)
        self.assertIsInstance(telemetry["duration_s"], float)
        self.assertGreaterEqual(telemetry["duration_s"], 0.0)
        self.assertEqual(telemetry["outcome"], pr.OUTCOME_OK)
        # `attest_runtime_model`'s own direct-call contract is untouched (pinned by
        # tests/test_codex_execute_policy.py: `{}` when no correlated thread exists) --
        # `default_runner` adds the timing keys AFTER calling it, it does not change it.
        self.assertEqual(cex.attest_runtime_model(output.stdout, datetime.now(timezone.utc)), {})

    def test_codex_run_task_records_the_runners_telemetry_duration_on_the_ledger(self):
        # The second half of boundary 2: `dispatch_and_verify` must actually READ the timing
        # `default_runner` now offers and pass it to `attempt_finished`. An injected runner
        # stands in for `default_runner`'s return shape so this test does not need a second
        # real dispatch to prove the wiring downstream of it.
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-codex")
            task = tcep.task()
            lifecycle = kc.TaskRun(ledger, "r1", task, workspace=tmp)
            runner = mock.Mock(return_value=(0, "ok", {"duration_s": 7.5, "outcome": "ok"}))
            verify = mock.Mock(return_value=(0, "verified"))
            result = cex.run_task(task, tcep.PRICING, runner, verify, codex_bin="stub",
                                  lifecycle=lifecycle)
            self.assertEqual(result["status"], "done")
            history = ledger.task_history("T1")
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["finished"]["duration_s"], 7.5)
            self.assertEqual(history[0]["finished"]["outcome"], "ok")

    # ---- cursor (boundary 3) and kit_scheduler (a fifth instance of the same defect) --------

    def test_cursor_run_task_records_the_runners_proc_dict_duration_on_the_ledger(self):
        # Cursor's runner always returned the whole `proc_runner` result as its third element
        # (`proc["duration_s"]` was already in hand); only the call to `attempt_finished`
        # dropped the one field.
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-cursor")
            task = dict(FIXTURE_TASK)
            task["model"] = None
            lifecycle = kc.TaskRun(ledger, "r1", task, workspace=tmp)
            runner = mock.Mock(return_value=(0, "ok", {"duration_s": 3.2, "outcome": "ok"}))
            verify = mock.Mock(return_value=(0, "verified"))
            result = cux.run_task(task, runner, verify, lifecycle=lifecycle)
            self.assertEqual(result["status"], "done")
            history = ledger.task_history("T1")
            self.assertEqual(history[0]["finished"]["duration_s"], 3.2)

    def test_kit_schedulers_stub_dispatcher_result_already_carries_measured_duration(self):
        # Found while verifying the "four boundaries" claim structurally: `kit_scheduler`'s
        # dispatchers already return the full `proc_runner` result (like Cursor's), and
        # `Scheduler._work` had the identical one-line omission. Not one of D03's four named
        # boundaries -- a fifth, separate instance of the same defect, closed the same way.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stub = root / "stub.sh"
            stub.write_text("#!/bin/sh\necho ok\nexit 0\n")
            stub.chmod(0o755)
            dispatcher = ks.StubDispatcher(str(stub))
            rc, output, proc = dispatcher({"id": "T1"}, "prompt", root)
        self.assertEqual(rc, 0)
        self.assertIsInstance(proc.get("duration_s"), float)

    def test_kit_scheduler_work_passes_that_duration_to_attempt_finished(self):
        # Derived structurally (AST), not by grep, per this kit's own citation-discipline rule.
        source = (BIN_DIR / "kit_scheduler.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        work_fn = next(n for n in ast.walk(tree)
                       if isinstance(n, ast.FunctionDef) and n.name == "_work")
        call = next(n for n in ast.walk(work_fn)
                   if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                   and n.func.attr == "attempt_finished")
        self.assertIn("duration_s", {kw.arg for kw in call.keywords})

    # ---- review/consult overhead (record_role_dispatch) -------------------------------------

    def test_a_review_dispatchs_duration_is_recorded_through_record_role_dispatch(self):
        # A phase review or acceptance dispatch is a real process with real timing, and had no
        # parameter to carry it at all -- the brief's "review/consult overhead ... in complete
        # workflow totals" requires this slot to exist, not just the four native drivers' own.
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store"
            kit_dir = Path(tmp) / "fixturekit"
            kit_dir.mkdir()
            kc.record_role_dispatch(kit_dir, "r1", "reviewer", "1", "fake-opus", 0, "ok",
                                    actor="claude-code", store=store, duration_s=9.9)
            ledger = al.AttemptLedger(store, kit_dir.name)
            history = ledger.task_history("phase-1")
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["finished"]["duration_s"], 9.9)

    # ---- attempt_history (boundary 4) --------------------------------------------------------

    def test_attempt_history_projects_duration_with_its_basis_and_counts_the_unmeasured(self):
        registry = ah._mod("model_registry").registry()
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            measured = ledger.record_started("r1", "T1", "initial", "fake-haiku")
            ledger.record_finished("r1", "T1", measured, "ok", 0, "did it", duration_s=6.25)
            unmeasured = ledger.record_started("r1", "T2", "initial", "fake-haiku")
            ledger.record_finished("r1", "T2", unmeasured, "ok", 0, "did it")
            records = ah.ledger_records("kit-a", ledger, registry)
            by_task = {r["task"]: r for r in records}
            self.assertEqual(by_task["T1"]["duration"],
                             {"basis": "process-wall", "seconds": 6.25, "source": "ledger"})
            self.assertIn("duration", by_task["T1"]["observed"])
            self.assertIsNone(by_task["T2"]["duration"])
            self.assertNotIn("duration", by_task["T2"]["observed"])

            card = ah.summarize(records, registry=registry)
            self.assertEqual(card["unknown"]["duration"], 1)
            self.assertEqual(card["duration"]["by_basis"]["process-wall"], {"n": 1, "seconds": 6.25})
            self.assertEqual(card["duration"]["records_with_duration"], 1)
            rendered = ah.render_markdown(card)
            self.assertIn("## Duration", rendered)
            self.assertIn("duration=1", rendered)

    def test_duration_totals_never_sums_a_process_wall_second_with_a_model_reported_one(self):
        # Only `process-wall` has a producer today; `model-reported` is hand-built here (the
        # literal shape `RECORD_FIELDS["duration"]` carries: basis/seconds/source) to prove the
        # bases stay apart in the total even once a future adapter fills it in -- the authority
        # inventory names this precedent explicitly (`cost_totals`'s own note).
        wall_rec = ah.observe(ah.blank(), duration={"basis": "process-wall", "seconds": 2.0,
                                                    "source": "ledger"})
        reported_rec = ah.observe(ah.blank(), duration={"basis": "model-reported",
                                                        "seconds": 30.0, "source": "output"})
        unmeasured_rec = ah.blank()
        totals = ah.duration_totals([wall_rec, reported_rec, unmeasured_rec])
        self.assertEqual(totals["by_basis"]["process-wall"], {"n": 1, "seconds": 2.0})
        self.assertEqual(totals["by_basis"]["model-reported"], {"n": 1, "seconds": 30.0})
        self.assertEqual(totals["by_basis"]["decision-latency"], {"n": 0, "seconds": None})
        self.assertEqual(totals["records_with_duration"], 2)
        self.assertEqual(totals["records"], 3)
        self.assertIn("never summed together", totals["note"])

    # ---- unknown stays unknown across a crash and a resume -----------------------------------

    def test_a_crash_closed_attempt_keeps_duration_unknown_never_zero(self):
        registry = ah._mod("model_registry").registry()
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            run1 = kc.TaskRun(ledger, "r1", dict(FIXTURE_TASK), workspace=tmp)
            run1.begin()
            run1.attempt_started("initial", "fake-haiku", verify_cmd="true")
            # The process dies before a finish is ever recorded.
            ledger.release("T1", "r1")
            run2 = kc.TaskRun(ledger, "r2", dict(FIXTURE_TASK), workspace=tmp)
            info = run2.begin()
            self.assertEqual(len(info["closed_unknown"]), 1)
            history = ledger.task_history("T1")
            finished = history[0]["finished"]
            self.assertEqual(finished["outcome"], al.OUTCOME_UNKNOWN)
            self.assertIsNone(finished["duration_s"], "an attempt nobody timed is unknown, not 0.0")
            records = ah.ledger_records("kit-a", ledger, registry)
            self.assertIsNone(records[0]["duration"])
            totals = ah.duration_totals(records)
            self.assertEqual(totals["by_basis"]["process-wall"]["n"], 0)

    def test_a_resumed_run_reprojects_the_recorded_duration_rather_than_redispatching(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            task = dict(FIXTURE_TASK)
            run1 = kc.TaskRun(ledger, "r1", task, workspace=tmp)
            run1.begin()
            attempt = run1.attempt_started("initial", "fake-haiku", verify_cmd="true")
            run1.attempt_finished(attempt, 0, "done", duration_s=4.2)
            run1.verify_finished(attempt, 0, "OK")
            # The process dies before TASKS.md/NOTES.md say so.
            pending = ledger.unprojected("T1")
            self.assertEqual([ev["attempt"] for ev in pending], [attempt])
            ledger.release("T1", "r1")

            run2 = kc.TaskRun(ledger, "r2", task, workspace=tmp)
            info = run2.begin()
            never_dispatch = mock.Mock(side_effect=AssertionError(
                "a resume that finds a settled attempt must not dispatch again"))
            recon = kc.reconcile_task(run2, info, lambda cmd: (0, "OK"), task["verify"])
            never_dispatch.assert_not_called()
            self.assertEqual(recon["mode"], "resolved")
            history = ledger.task_history("T1")
            self.assertEqual(len(history), 1, "a resume settles the attempt, it does not add one")
            self.assertEqual(history[0]["finished"]["duration_s"], 4.2,
                             "the ORIGINAL measured duration, not re-measured or discarded")

    # ---- workflow_eval's wall_seconds zero-coercions -----------------------------------------

    def test_variant_summary_never_reports_a_never_dispatched_trial_as_zero_wall_seconds(self):
        we = twe.we
        base = {"variant": "v", "task_id": "t1", "excluded": None, "solved": None,
               "accepted": None, "incorrect_acceptance": False, "review": None, "resume": None,
               "adjudication": None, "oracles": None, "robustness": {k: None for k in we.ROBUSTNESS}}
        skipped_only = [dict(base, skipped="routing-refused", wall_seconds=None)]
        summary = we._variant_summary("v", skipped_only, floor=1, repeats=1)
        self.assertIsNone(summary["wall_seconds"],
                          "nothing was ever dispatched: unmeasured, not a 0.0 measurement")
        self.assertIsNone(summary["mean_wall_seconds"])

        measured = dict(base, skipped=None, wall_seconds=2.5, solved=True,
                        oracles={"tests": {"available": True}})
        mixed = we._variant_summary("v", skipped_only + [measured], floor=1, repeats=1)
        self.assertEqual(mixed["wall_seconds"], 2.5,
                         "the skip contributes nothing (not +0.0); only the real dispatch counts")
        self.assertEqual(mixed["mean_wall_seconds"], 2.5)

    def test_a_real_routing_refusal_produces_an_unmeasured_trial_not_a_measured_zero(self):
        # The seed-level fix (`_run_trial`'s `rec` init), exercised end to end through one
        # real, entirely offline `Evaluation`: a tierless harness under an adaptive routing
        # policy is refused before any sandbox or dispatch exists (twe's own scenario,
        # `RoutingTests.test_a_tierless_harness_under_a_routing_policy_is_skipped_as_refused`).
        we = twe.we
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = twe.build_repo(root / "target")
            stub = root / "stub"
            stub.write_text("#!/bin/sh\nexit 0\n")
            stub.chmod(0o755)
            adapter = we.stub_adapter()
            tasks = []
            plan = we.build_plan(
                repo, adapter["name"], [], workflows=("direct",), policies=("adaptive",),
                repeats=1, mode="issue-replay", test_cmd=f"{sys.executable} run_tests.py",
                scratch_dir=root / "scratch", adapter=adapter, tasks_out=tasks,
                test_runner=twe.test_runner,
            )
            plan["_variants_full"] = we.build_variants(
                adapter["name"], plan["candidates"], plan["workflows"], plan["policies"])
            out = io.StringIO()
            never_dispatch = mock.Mock(side_effect=AssertionError(
                "a routing-refused trial must never reach the dispatcher"))
            ev = we.Evaluation(plan, tasks, adapter, store_dir=root / "store",
                               runner=never_dispatch, test_runner=twe.test_runner,
                               binary=str(stub), out=out, err=out, max_usd=1000.0,
                               exec_mode="trusted-host")
            env = ev.run()
        self.assertEqual(env["trials"][0]["skipped"], "routing-refused")
        self.assertIsNone(env["trials"][0]["wall_seconds"],
                          "never dispatched: unmeasured, not the old 0.0 seed")
        never_dispatch.assert_not_called()

    # ---- LEDGER_VERSION did not move ----------------------------------------------------------

    def test_the_ledger_version_did_not_move(self):
        self.assertEqual(al.LEDGER_VERSION, "polytropos.attempts/1")
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            a = ledger.record_started("r1", "T1", "initial", "fake-haiku")
            ledger.record_finished("r1", "T1", a, "ok", 0, "x", duration_s=1.5)
            self.assertEqual(len(ledger.events()), 2)
            self.assertEqual(ledger.corrupt, 0)
            with mock.patch.object(al, "LEDGER_VERSION", "polytropos.attempts/2"):
                self.assertEqual(ledger.events(), [])
                self.assertEqual(ledger.corrupt, 2)
            self.assertEqual(len(ledger.events()), 2)
            self.assertEqual(ledger.corrupt, 0)


if __name__ == "__main__":
    unittest.main()
