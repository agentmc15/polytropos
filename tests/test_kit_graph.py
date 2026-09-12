"""The execution DAG is validated before anything is dispatched or written (step 18).

WHAT WAS MEASURED, on the tree before `kit_contract.validate_graph` existed:

  - A duplicate task id gave three answers. `--task T2` selected the LAST block carrying the
    id (dict last-wins), automatic selection took the FIRST (list order), and `set_status`
    wrote the first -- so a driver could dispatch one block's brief and mark the other done.
  - A cycle between T1 and T2 refused each of them with "depends on T2, which is 'pending'",
    a true sentence that can never become false, and let an unrelated T3 dispatch.
  - A self-dependency reported "no pending task has all dependencies done", the message for a
    kit that is waiting rather than one that is wrong.
  - A typo in one task's `depends:` let every other task run and left that task unreachable
    without a word.
  - Automatic selection walked past an `in-progress` task and dispatched the next pending one,
    so a dead run's task stayed in-progress until somebody noticed.

These tests pin the replacement: one graph verdict reached FIRST, before selection, before the
claim, before any write; the same verdict from `status`, from `run`, from `--dry-run`, and from
`kit_contract.py graph`; a diamond's frontier walked in file order; deliberate resume and
rerun still eligible by explicit `--task`; and the task state machine refusing an edge it does
not have before the temporary file exists. Every dispatch is a stub script in a temp dir; the
per-user data root is a temp dir for the whole module.
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

ROOT = Path(__file__).resolve().parents[1]
KITS_DIR = ROOT / ".claude" / "kits"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_graph_test", ROOT / "bin" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


kc = _load("kit_contract")
claude = tce.ce
copilot = _load("copilot_execute")
codex = _load("codex_execute")

_DATA_HOME = None
_DATA_HOME_PATCH = None


def setUpModule():
    # Step 16: the drivers default the attempt ledger to the per-user data root. Every test
    # here that reaches a driver's `run` runs with that root pointed at a temp dir.
    global _DATA_HOME, _DATA_HOME_PATCH
    _DATA_HOME = tempfile.TemporaryDirectory(prefix="polytropos-test-data-")
    _DATA_HOME_PATCH = mock.patch.dict(os.environ, {"POLYTROPOS_DATA_HOME": _DATA_HOME.name})
    _DATA_HOME_PATCH.start()


def tearDownModule():
    _DATA_HOME_PATCH.stop()
    _DATA_HOME.cleanup()


# ---- fixtures ---------------------------------------------------------------------------------

def _task(task_id, status="pending", depends=(), **overrides):
    base = {
        "id": task_id, "title": f"task {task_id}", "status": status, "model": None,
        "depends": list(depends), "independent": not depends, "evidence": None,
        "brief": f"do {task_id}", "verify": "true",
    }
    base.update(overrides)
    return base


def _diamond(done=()):
    """T1 -> {T2, T3} -> T4, with the named tasks already done."""
    tasks = [_task("T1"), _task("T2", depends=["T1"]), _task("T3", depends=["T1"]),
             _task("T4", depends=["T2", "T3"])]
    for t in tasks:
        if t["id"] in done:
            t["status"] = "done"
    return tasks


def _kit_text(specs):
    """TASKS.md text from `(id, status, depends)` triples, every verify `true` and every task
    `evidence: regression` so the Claude driver's red-green precheck never blocks a fixture
    whose command passes before the work -- these tests are about the graph, not the proof."""
    out = ["## Phase 1 — graph fixtures", ""]
    for spec in specs:
        task_id, status, depends = spec[:3]
        dep_line = ", ".join(depends) if depends else "(none)"
        out.append(
            f"### {task_id} — Task {task_id}\n"
            f"- status: {status}\n"
            f"- model: haiku\n"
            f"- depends: {dep_line}\n"
            f"- evidence: regression\n"
            f"\n**Brief.** Do {task_id}.\n"
            f"\n**Acceptance.** {task_id} is done.\n"
            f"\n**Verify.**\n\n```bash\ntrue\n```\n"
        )
    return "\n".join(out)


INVALID_KITS = {
    "cycle": [("T1", "pending", ["T2"]), ("T2", "pending", ["T1"]), ("T3", "pending", [])],
    "duplicate-id": [("T1", "pending", []), ("T1", "pending", [])],
    "unknown-dependency": [("T1", "pending", []), ("T2", "pending", ["T9"])],
    "self-dependency": [("T1", "pending", ["T1"])],
}


def _calls(log_path):
    if not Path(log_path).exists():
        return 0
    return Path(log_path).read_text().count("===CALL===")


def _snapshot(directory):
    """Every file under `directory` with its bytes, so "nothing was written" is checkable."""
    directory = Path(directory)
    return {
        str(p.relative_to(directory)): p.read_bytes()
        for p in sorted(directory.rglob("*")) if p.is_file()
    }


# ---- 1. the validator ---------------------------------------------------------------------------

class ValidateGraphTests(unittest.TestCase):
    def test_a_valid_diamond_has_no_findings(self):
        self.assertEqual(kc.validate_graph(_diamond()), [])

    def test_an_empty_kit_is_valid(self):
        self.assertEqual(kc.validate_graph([]), [])

    def test_a_duplicate_id_names_both_blocks_by_position(self):
        findings = kc.validate_graph([_task("T1"), _task("T2"), _task("T1")])
        self.assertEqual([f["kind"] for f in findings], ["duplicate-id"])
        self.assertEqual(findings[0]["task"], "T1")
        self.assertIn("#1, #3", findings[0]["detail"])
        self.assertIn("own id", findings[0]["fix"])

    def test_a_self_dependency_is_its_own_kind_not_an_unknown_one(self):
        findings = kc.validate_graph([_task("T1", depends=["T1"])])
        self.assertEqual([f["kind"] for f in findings], ["self-dependency"])
        self.assertIn("depends on itself", findings[0]["detail"])

    def test_an_unknown_dependency_keeps_the_sentence_the_drivers_already_print(self):
        findings = kc.validate_graph([_task("T2", depends=["T99"])])
        self.assertEqual([f["kind"] for f in findings], ["unknown-dependency"])
        self.assertIn("unknown task 'T99'", findings[0]["detail"])
        self.assertIn("(none)", findings[0]["fix"])

    def test_a_cycle_is_reported_as_a_closed_path_in_file_order(self):
        tasks = [_task("T1", depends=["T2"]), _task("T2", depends=["T3"]),
                 _task("T3", depends=["T1"]), _task("T4")]
        findings = kc.validate_graph(tasks)
        self.assertEqual([f["kind"] for f in findings], ["cycle"])
        self.assertEqual(findings[0]["detail"], "dependency cycle: T1 -> T2 -> T3 -> T1")

    def test_a_two_cycle_and_a_self_loop_are_distinct_findings(self):
        tasks = [_task("T1", depends=["T2"]), _task("T2", depends=["T1", "T2"])]
        kinds = sorted(f["kind"] for f in kc.validate_graph(tasks))
        self.assertEqual(kinds, ["cycle", "self-dependency"])

    def test_every_finding_is_reported_not_just_the_first(self):
        tasks = [_task("T1", depends=["T1"]), _task("T1"), _task("T2", depends=["T9"]),
                 _task("T3", depends=["T4"]), _task("T4", depends=["T3"])]
        kinds = sorted(f["kind"] for f in kc.validate_graph(tasks))
        self.assertEqual(kinds, ["cycle", "duplicate-id", "self-dependency",
                                 "unknown-dependency"])
        for f in kc.validate_graph(tasks):
            self.assertEqual(set(f), {"kind", "task", "detail", "fix"})
            self.assertIn(f["kind"], kc.FINDING_KINDS)

    def test_a_cycle_among_done_tasks_is_still_invalid(self):
        # Structure, not state: a plan that contradicts itself is wrong however far it got.
        tasks = [_task("T1", "done", ["T2"]), _task("T2", "done", ["T1"])]
        self.assertEqual([f["kind"] for f in kc.validate_graph(tasks)], ["cycle"])

    def test_rendering_names_the_count_the_kind_the_task_and_the_fix(self):
        text = kc.render_findings(kc.validate_graph([_task("T1", depends=["T1"])]))
        self.assertIn("graph: invalid -- 1 finding(s)", text)
        self.assertIn("nothing is dispatched and nothing is written", text)
        self.assertIn("self-dependency [T1]:", text)
        self.assertIn("fix:", text)

    def test_graph_invalid_carries_its_findings_and_renders_them(self):
        findings = kc.validate_graph([_task("T1", depends=["T1"])])
        exc = kc.GraphInvalid(findings)
        self.assertEqual(exc.findings, findings)
        self.assertIn("self-dependency", str(exc))
        self.assertIsInstance(exc, ValueError)


# ---- 2. frontier and graph state ----------------------------------------------------------------

class FrontierAndStateTests(unittest.TestCase):
    def test_a_diamonds_frontier_moves_as_tasks_complete(self):
        self.assertEqual(kc.ready_frontier(_diamond()), ["T1"])
        self.assertEqual(kc.ready_frontier(_diamond(done=["T1"])), ["T2", "T3"])
        self.assertEqual(kc.ready_frontier(_diamond(done=["T1", "T2"])), ["T3"])
        self.assertEqual(kc.ready_frontier(_diamond(done=["T1", "T3"])), ["T2"])
        self.assertEqual(kc.ready_frontier(_diamond(done=["T1", "T2", "T3"])), ["T4"])
        self.assertEqual(kc.ready_frontier(_diamond(done=["T1", "T2", "T3", "T4"])), [])

    def test_the_frontier_is_in_file_order_not_id_order(self):
        tasks = [_task("Z"), _task("A")]
        self.assertEqual(kc.ready_frontier(tasks), ["Z", "A"])

    def test_states_cover_every_case_and_nothing_else(self):
        self.assertEqual(kc.graph_state(_diamond())["state"], "ready")
        self.assertEqual(kc.graph_state(_diamond(done=["T1", "T2", "T3", "T4"]))["state"],
                         "complete")
        self.assertEqual(kc.graph_state([])["state"], "complete")
        interrupted = _diamond(done=["T1"])
        interrupted[1]["status"] = "in-progress"
        self.assertEqual(kc.graph_state(interrupted)["state"], "interrupted")
        waiting = _diamond(done=["T1"])
        waiting[1]["status"] = "blocked"
        waiting[2]["status"] = "blocked"
        self.assertEqual(kc.graph_state(waiting)["state"], "waiting")
        self.assertEqual(kc.graph_state([_task("T1", depends=["T1"])])["state"], "invalid")
        self.assertEqual(set(kc.GRAPH_STATES),
                         {"invalid", "complete", "ready", "interrupted", "waiting"})

    def test_interrupted_outranks_ready_because_nothing_here_schedules(self):
        tasks = [_task("T1", "in-progress"), _task("T2")]
        graph = kc.graph_state(tasks)
        self.assertEqual(graph["state"], "interrupted")
        self.assertEqual(graph["frontier"], ["T2"], "the frontier is still reported")
        self.assertEqual(graph["in_progress"], ["T1"])

    def test_waiting_on_names_what_holds_each_unready_pending_task(self):
        tasks = [_task("T1", "blocked"), _task("T2", depends=["T1"]),
                 _task("T3", depends=["T2"])]
        graph = kc.graph_state(tasks)
        self.assertEqual(graph["state"], "waiting")
        self.assertEqual(graph["waiting_on"], {"T2": [("T1", "blocked")],
                                               "T3": [("T2", "pending")]})
        self.assertEqual(graph["blocked"], ["T1"])

    def test_an_invalid_graph_has_an_empty_frontier(self):
        graph = kc.graph_state([_task("T1"), _task("T2", depends=["T9"])])
        self.assertEqual(graph["state"], "invalid")
        self.assertEqual(graph["frontier"], [], "T1 is not offered while the kit is wrong")

    def test_rendered_state_lines_are_actionable(self):
        self.assertIn("T1 runs next", kc.render_graph_state(kc.graph_state(_diamond())))
        interrupted = [_task("T1", "in-progress"), _task("T2")]
        line = kc.render_graph_state(kc.graph_state(interrupted))
        self.assertIn("resume with --task", line)
        self.assertIn("explicit --task only: T2", line)
        waiting = [_task("T1", "blocked"), _task("T2", depends=["T1"])]
        line = kc.render_graph_state(kc.graph_state(waiting))
        self.assertIn("T2 waits on T1 [blocked]", line)
        self.assertIn("retry a blocked task", line)
        self.assertIn("every task is done",
                      kc.render_graph_state(kc.graph_state([_task("T1", "done")])))


# ---- 3. one readiness rule ----------------------------------------------------------------------

class ReadinessTests(unittest.TestCase):
    def test_select_task_is_the_tuple_view_of_readiness(self):
        tasks = _diamond(done=["T1"])
        r = kc.readiness(tasks)
        self.assertEqual(kc.select_task(tasks), (r["task"], r["reason"]))
        self.assertEqual(r["mode"], "fresh")
        self.assertEqual(r["graph"]["state"], "ready")

    def test_an_invalid_graph_selects_nothing_whatever_is_named(self):
        tasks = [_task("T1"), _task("T2", depends=["T9"])]
        for named in (None, "T1", "T2", "T9"):
            with self.subTest(named=named):
                task, reason = kc.select_task(tasks, named)
                self.assertIsNone(task, "T1 is ready by its own edges and still not offered")
                self.assertIn("graph: invalid", reason)
                self.assertIn("unknown task 'T9'", reason)

    def test_each_explicit_status_maps_to_its_mode(self):
        for status, mode in kc.SELECTION_MODES.items():
            with self.subTest(status=status):
                r = kc.readiness([_task("T1", status)], "T1", allow_rerun=True)
                self.assertEqual(r["task"]["id"], "T1")
                self.assertEqual(r["mode"], mode)

    def test_a_done_task_needs_rerun_and_a_rerun_is_a_rerun(self):
        task, reason = kc.select_task([_task("T1", "done")], "T1")
        self.assertIsNone(task)
        self.assertIn("--rerun", reason)
        r = kc.readiness([_task("T1", "done")], "T1", allow_rerun=True)
        self.assertEqual(r["mode"], "rerun")

    def test_an_unfinished_explicit_prerequisite_is_named_with_its_status(self):
        tasks = [_task("T1", "blocked"), _task("T2", depends=["T1"])]
        task, reason = kc.select_task(tasks, "T2")
        self.assertIsNone(task)
        self.assertEqual(reason, "task T2 depends on T1, which is 'blocked' rather than done")

    def test_automatic_selection_refuses_while_a_task_is_in_progress(self):
        tasks = [_task("T1", "in-progress"), _task("T2")]
        task, reason = kc.select_task(tasks)
        self.assertIsNone(task, "T2 used to be dispatched here, leaving T1 in-progress")
        self.assertIn("T1 is in-progress", reason)
        self.assertIn("--task T1", reason)
        self.assertIn("nothing is replayed", reason)
        self.assertIn("explicit --task only: T2", reason)

    def test_naming_the_interrupted_task_resumes_it(self):
        tasks = [_task("T1", "in-progress"), _task("T2")]
        r = kc.readiness(tasks, "T1")
        self.assertEqual(r["task"]["id"], "T1")
        self.assertEqual(r["mode"], "resume")
        self.assertEqual(r["graph"]["state"], "interrupted")

    def test_naming_another_ready_task_is_allowed_and_deliberate(self):
        tasks = [_task("T1", "in-progress"), _task("T2")]
        r = kc.readiness(tasks, "T2")
        self.assertEqual(r["task"]["id"], "T2")
        self.assertEqual(r["mode"], "fresh")

    def test_every_in_progress_task_is_named_when_there_are_several(self):
        tasks = [_task("T1", "in-progress"), _task("T2", "in-progress")]
        _task_, reason = kc.select_task(tasks)
        self.assertIn("also in-progress: T2", reason)

    def test_a_waiting_kit_says_which_blocked_task_to_retry(self):
        tasks = [_task("T1", "blocked"), _task("T2", depends=["T1"])]
        task, reason = kc.select_task(tasks)
        self.assertIsNone(task)
        self.assertIn("no pending task has all dependencies done (pending: T2)", reason)
        self.assertIn("blocked: T1", reason)
        self.assertIn("--task <id>", reason)

    def test_a_kit_with_only_blocked_tasks_is_waiting_on_a_retry(self):
        task, reason = kc.select_task([_task("T1", "blocked")])
        self.assertIsNone(task)
        self.assertIn("no pending task in this kit", reason)
        self.assertIn("blocked: T1", reason)

    def test_a_complete_kit_keeps_the_historical_sentence(self):
        self.assertEqual(kc.select_task([_task("T1", "done")]), (None, "no pending task in this kit"))

    def test_the_low_level_selector_still_delegates(self):
        tasks = [_task("T1"), _task("T2", depends=["T9"])]
        self.assertIsNone(kc._select_task(tasks, "T1"))


# ---- 4. the task state machine ------------------------------------------------------------------

class TransitionTests(unittest.TestCase):
    def test_the_table_is_exactly_the_edges_the_drivers_make(self):
        self.assertEqual(kc.TRANSITIONS, {
            "pending": ("in-progress",),
            "in-progress": ("in-progress", "done", "blocked"),
            "done": ("in-progress",),
            "blocked": ("in-progress",),
        })
        self.assertEqual(set(kc.TRANSITIONS), set(kc.STATUSES))

    def test_every_pair_is_allowed_iff_the_table_says_so(self):
        for previous in kc.STATUSES:
            for new in kc.STATUSES:
                with self.subTest(previous=previous, new=new):
                    if new in kc.TRANSITIONS[previous]:
                        kc.check_transition(previous, new)
                    else:
                        with self.assertRaises(kc.InvalidTransition) as ctx:
                            kc.check_transition(previous, new)
                        self.assertIn(f"{previous!r} -> {new!r}", str(ctx.exception))

    def test_an_unknown_previous_status_is_not_checked(self):
        # `set_status` raises its own "unknown task id" for a missing block; the transition
        # check has nothing to say about a task that does not exist.
        kc.check_transition(None, "done")

    def test_an_invalid_new_status_is_still_a_value_error(self):
        with self.assertRaises(ValueError):
            kc.check_transition("pending", "finished")

    def test_invalid_transition_is_a_value_error_so_run_cli_exits_2(self):
        self.assertTrue(issubclass(kc.InvalidTransition, ValueError))

    def test_project_status_refuses_a_verdict_with_no_dispatch_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "TASKS.md"
            path.write_text(_kit_text([("T1", "pending", [])]))
            before = path.read_bytes()
            with self.assertRaises(kc.InvalidTransition):
                kc.project_status(path, "T1", "done")
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["TASKS.md"],
                             "no temporary file may be left behind")

    def test_project_status_checks_the_drivers_own_edge_when_expected_is_given(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "TASKS.md"
            path.write_text(_kit_text([("T1", "pending", [])]))
            with self.assertRaises(kc.InvalidTransition):
                kc.project_status(path, "T1", "blocked", expected="pending")
            self.assertEqual(kc.parse_tasks(path.read_text())[0]["status"], "pending")

    def test_a_workers_flip_does_not_change_which_edge_is_checked(self):
        # The driver holds T1 in-progress; a worker wrote `done`. `done -> blocked` has no edge,
        # but the driver's own edge is `in-progress -> blocked`, which does. The verdict is
        # written and the discrepancy reported (step 16), not refused.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "TASKS.md"
            path.write_text(_kit_text([("T1", "done", [])]))
            text, previous = kc.project_status(path, "T1", "blocked", expected="in-progress")
            self.assertEqual(previous, "done")
            self.assertEqual(kc.parse_tasks(text)[0]["status"], "blocked")

    def test_every_legal_driver_edge_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "TASKS.md"
            for previous in kc.STATUSES:
                for new in kc.TRANSITIONS[previous]:
                    with self.subTest(previous=previous, new=new):
                        path.write_text(_kit_text([("T1", previous, [])]))
                        _text, seen = kc.project_status(path, "T1", new)
                        self.assertEqual(seen, previous)
                        self.assertEqual(kc.parse_tasks(path.read_text())[0]["status"], new)


# ---- 5. plan drift ------------------------------------------------------------------------------

class PlanDriftTests(unittest.TestCase):
    def test_the_fields_a_worker_may_not_change_silently(self):
        self.assertEqual(kc.PLAN_FIELDS,
                         ("title", "model", "depends", "independent", "evidence", "brief",
                          "verify"))
        before = _task("T1")
        after = dict(before, depends=["T0"], verify="false", status="done")
        self.assertEqual(kc.plan_drift(before, after), ["depends", "verify"])
        self.assertEqual(kc.plan_drift(before, dict(before)), [])

    def test_projection_reports_and_records_a_block_changed_under_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = Path(tmp) / "fixturekit"
            kit.mkdir()
            tasks_path = kit / "TASKS.md"
            tasks_path.write_text(_kit_text([("T1", "pending", []), ("T2", "pending", [])]))
            snapshot = kc.parse_tasks(tasks_path.read_text())[0]
            ledger = kc.open_ledger(kit, store=Path(tmp) / "store")
            lifecycle = kc.TaskRun(ledger, "run-1", snapshot, workspace=Path(tmp))
            lifecycle.begin()
            kc.project_status(tasks_path, "T1", "in-progress")
            # The worker rewrites its own acceptance and its dependency while the run holds it.
            worked = tasks_path.read_text().replace(
                "**Acceptance.** T1 is done.", "**Acceptance.** T1 is whatever."
            ).replace("- depends: (none)\n- evidence: regression\n\n**Brief.** Do T1.",
                      "- depends: T2\n- evidence: regression\n\n**Brief.** Do less.")
            self.assertNotEqual(worked, tasks_path.read_text())
            tasks_path.write_text(worked)
            result = {"id": "T1", "status": "done", "model_used": "fake-haiku",
                      "escalations": [], "verify_rc": 0}
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                kc.finish_task_projection(lifecycle, tasks_path, snapshot, result)
            self.assertEqual(result["plan_drift"], ["depends", "brief"])
            self.assertIn("plan-drift: task T1", err.getvalue())
            self.assertIn("depends, brief", err.getvalue())
            self.assertIn("may not rewrite its own acceptance", err.getvalue())
            drift_events = [e for e in ledger.events() if e["kind"] == "plan.drift"]
            self.assertEqual(len(drift_events), 1)
            self.assertEqual(drift_events[0]["fields"], ["depends", "brief"])
            self.assertEqual(drift_events[0]["run"], "run-1")
            # The verdict stands and the file keeps the worker's edit for the architect to see.
            fresh = kc.parse_tasks(tasks_path.read_text())[0]
            self.assertEqual(fresh["status"], "done")
            self.assertEqual(fresh["depends"], ["T2"])
            lifecycle.end()

    def test_an_unchanged_block_records_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = Path(tmp) / "fixturekit"
            kit.mkdir()
            tasks_path = kit / "TASKS.md"
            tasks_path.write_text(_kit_text([("T1", "pending", [])]))
            snapshot = kc.parse_tasks(tasks_path.read_text())[0]
            ledger = kc.open_ledger(kit, store=Path(tmp) / "store")
            lifecycle = kc.TaskRun(ledger, "run-1", snapshot, workspace=Path(tmp))
            lifecycle.begin()
            kc.project_status(tasks_path, "T1", "in-progress")
            result = {"id": "T1", "status": "done", "model_used": None, "escalations": [],
                      "verify_rc": 0}
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                kc.finish_task_projection(lifecycle, tasks_path, snapshot, result)
            self.assertEqual(result["plan_drift"], [])
            self.assertNotIn("plan-drift", err.getvalue())
            self.assertEqual([e for e in ledger.events() if e["kind"] == "plan.drift"], [])
            lifecycle.end()


# ---- 6. zero dispatches, zero writes, on every driver -------------------------------------------

class ZeroDispatchOnInvalidGraphTests(unittest.TestCase):
    """The exit gate: cycles, duplicate, missing and self dependencies, and an unfinished
    explicit prerequisite cause zero dispatches and no state mutation -- on all three drivers,
    through their real `main`, with a stub binary that logs if it is ever run."""

    def _run(self, driver, bin_flag, tmp, kit, *extra):
        log = tmp / "stub.log"
        stub = tce._write_stub(tmp, log)
        store = tmp / "store"
        argv = ["run", "--kit", str(kit), bin_flag, str(stub),
                "--attempt-store", str(store), *extra]
        out, err = io.StringIO(), io.StringIO()
        patches = []
        if driver is claude:
            tce._write_agent_bundle(tmp, "fixturekit", "implementer", tce.PREAMBLE_FIXTURE_BODY)
            patches = [mock.patch.object(claude, "REPO_ROOT", tmp),
                       mock.patch.object(claude, "load_pricing",
                                         return_value=tce.PRICING_FIXTURE)]
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.redirect_stderr(err))
            with self.assertRaises(SystemExit) as ctx:
                driver.main(argv)
        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(_calls(log), 0, "the stub was dispatched")
        self.assertFalse(store.exists(), "the ledger was opened before the graph was judged")
        return out.getvalue(), err.getvalue()

    def _each_driver(self):
        yield "claude", claude, "--claude-bin"
        yield "copilot", copilot, "--copilot-bin"
        yield "codex", codex, "--codex-bin"

    def test_every_invalid_graph_refuses_on_every_driver_without_a_write(self):
        for kind, specs in INVALID_KITS.items():
            for name, driver, flag in self._each_driver():
                with self.subTest(driver=name, kind=kind), \
                        tempfile.TemporaryDirectory() as tmp_s:
                    tmp = Path(tmp_s)
                    kit = tmp / "fixturekit"
                    kit.mkdir()
                    (kit / "TASKS.md").write_text(_kit_text(specs))
                    before = _snapshot(kit)
                    out, err = self._run(driver, flag, tmp, kit)
                    self.assertEqual(_snapshot(kit), before, "the kit was written to")
                    self.assertIn("graph: invalid", err)
                    self.assertIn(f"{kind} [", err)
                    self.assertIn("fix:", err)
                    self.assertEqual(out, "")

    def test_an_unfinished_explicit_prerequisite_refuses_on_every_driver_without_a_write(self):
        specs = [("T1", "pending", []), ("T2", "pending", ["T1"])]
        for name, driver, flag in self._each_driver():
            with self.subTest(driver=name), tempfile.TemporaryDirectory() as tmp_s:
                tmp = Path(tmp_s)
                kit = tmp / "fixturekit"
                kit.mkdir()
                (kit / "TASKS.md").write_text(_kit_text(specs))
                before = _snapshot(kit)
                _out, err = self._run(driver, flag, tmp, kit, "--task", "T2")
                self.assertEqual(_snapshot(kit), before)
                self.assertIn("task T2 depends on T1, which is 'pending'", err)

    def test_an_interrupted_kit_refuses_automatic_selection_on_every_driver(self):
        specs = [("T1", "in-progress", []), ("T2", "pending", [])]
        for name, driver, flag in self._each_driver():
            with self.subTest(driver=name), tempfile.TemporaryDirectory() as tmp_s:
                tmp = Path(tmp_s)
                kit = tmp / "fixturekit"
                kit.mkdir()
                (kit / "TASKS.md").write_text(_kit_text(specs))
                before = _snapshot(kit)
                _out, err = self._run(driver, flag, tmp, kit)
                self.assertEqual(_snapshot(kit), before)
                self.assertIn("T1 is in-progress", err)
                self.assertIn("--task T1", err)

    def test_the_claude_full_preview_refuses_the_same_way(self):
        # `--dry-run` with no `--task` previews every pending task without selecting one, so
        # it is the one driver path that had to be told about the graph separately.
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit = tmp / "fixturekit"
            kit.mkdir()
            (kit / "TASKS.md").write_text(_kit_text(INVALID_KITS["cycle"]))
            tce._write_agent_bundle(tmp, "fixturekit", "implementer", tce.PREAMBLE_FIXTURE_BODY)
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(claude, "REPO_ROOT", tmp), \
                    mock.patch.object(claude, "load_pricing", return_value=tce.PRICING_FIXTURE), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as ctx:
                    claude.main(["run", "--kit", str(kit), "--claude-bin", tce.STUB_BIN,
                                 "--dry-run"])
            self.assertEqual(ctx.exception.code, 2)
            self.assertEqual(out.getvalue(), "", "no preview of a run that would refuse")
            self.assertIn("cycle [T1]: dependency cycle: T1 -> T2 -> T1", err.getvalue())


# ---- 7. a diamond, resume, and rerun through a real driver --------------------------------------

class DiamondThroughTheDriverTests(unittest.TestCase):
    """Sequential walk of T1 -> {T2, T3} -> T4 through the Claude driver's real `run`,
    dispatching a stub each time; then the resume and rerun gestures on the same kit."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.kit = self.tmp / "fixturekit"
        self.kit.mkdir()
        self.log = self.tmp / "stub.log"
        self.stub = tce._write_stub(self.tmp, self.log)
        self.store = self.tmp / "store"
        tce._write_agent_bundle(self.tmp, "fixturekit", "implementer", tce.PREAMBLE_FIXTURE_BODY)

    def tearDown(self):
        self._tmp.cleanup()

    def run_driver(self, *extra, expect_exit=None):
        out, err = io.StringIO(), io.StringIO()
        argv = ["run", "--kit", str(self.kit), "--claude-bin", str(self.stub),
                "--attempt-store", str(self.store), *extra]
        with mock.patch.object(claude, "REPO_ROOT", self.tmp), \
                mock.patch.object(claude, "load_pricing", return_value=tce.PRICING_FIXTURE), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            if expect_exit is None:
                claude.main(argv)
            else:
                with self.assertRaises(SystemExit) as ctx:
                    claude.main(argv)
                self.assertEqual(ctx.exception.code, expect_exit, err.getvalue())
        return out.getvalue(), err.getvalue()

    def status_line(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            claude.main(["status", "--kit", str(self.kit)])
        return out.getvalue().splitlines()[-1]

    def statuses(self):
        return {t["id"]: t["status"] for t in kc.parse_tasks((self.kit / "TASKS.md").read_text())}

    def outcome_order(self):
        notes = self.kit / "NOTES.md"
        if not notes.exists():
            return []
        # NOTES.md carries each outcome as a `- outcome: <id> ...` bullet.
        return [ln.strip().split()[2] for ln in notes.read_text().splitlines()
                if ln.strip().startswith("- outcome: ")]

    def test_the_frontier_is_walked_in_file_order_and_status_reports_each_step(self):
        (self.kit / "TASKS.md").write_text(_kit_text([
            ("T1", "pending", []), ("T2", "pending", ["T1"]), ("T3", "pending", ["T1"]),
            ("T4", "pending", ["T2", "T3"]),
        ]))
        self.assertEqual(self.status_line(), "graph: ready -- frontier: T1 (sequential: T1 runs next)")
        self.run_driver()
        self.assertEqual(self.statuses()["T1"], "done")
        self.assertEqual(self.status_line(),
                         "graph: ready -- frontier: T2, T3 (sequential: T2 runs next)")
        self.run_driver()
        self.assertEqual(self.status_line(), "graph: ready -- frontier: T3 (sequential: T3 runs next)")
        self.run_driver()
        self.assertEqual(self.status_line(), "graph: ready -- frontier: T4 (sequential: T4 runs next)")
        self.run_driver()
        self.assertEqual(self.status_line(), "graph: complete -- every task is done")
        self.assertEqual(self.outcome_order(), ["T1", "T2", "T3", "T4"])
        self.assertEqual(_calls(self.log), 4, "one dispatch per task, never two at once")
        _out, err = self.run_driver(expect_exit=2)
        self.assertIn("no pending task in this kit", err)
        self.assertEqual(_calls(self.log), 4)

    def test_a_dead_runs_task_is_resumed_by_name_and_never_walked_past(self):
        (self.kit / "TASKS.md").write_text(_kit_text([
            ("T1", "in-progress", []), ("T2", "pending", []),
        ]))
        ledger = kc.open_ledger(self.kit, store=self.store)
        ledger.append("verify.precheck", run="r0", task="T1", tautological=False, rc=1)
        ledger.record_started("r0", "T1", "initial", "fake-haiku")
        self.assertIn("graph: interrupted -- in-progress: T1", self.status_line())

        _out, err = self.run_driver(expect_exit=2)
        self.assertIn("T1 is in-progress", err)
        self.assertEqual(_calls(self.log), 0, "T2 must not be dispatched around T1")
        self.assertEqual(self.statuses(), {"T1": "in-progress", "T2": "pending"})

        _out, err = self.run_driver("--task", "T1")
        self.assertIn("nothing was re-dispatched", err)
        self.assertEqual(_calls(self.log), 0)
        self.assertEqual(self.statuses()["T1"], "done")
        self.assertEqual(self.status_line(), "graph: ready -- frontier: T2 (sequential: T2 runs next)")

    def test_a_rerun_is_deliberate_and_takes_the_done_to_in_progress_edge(self):
        (self.kit / "TASKS.md").write_text(_kit_text([("T1", "done", [])]))
        _out, err = self.run_driver("--task", "T1", expect_exit=2)
        self.assertIn("already done", err)
        self.assertEqual(_calls(self.log), 0)
        self.run_driver("--task", "T1", "--rerun")
        self.assertEqual(_calls(self.log), 1)
        self.assertEqual(self.statuses()["T1"], "done")
        self.assertEqual(self.outcome_order(), ["T1"])


# ---- 8. legacy kits and the command line --------------------------------------------------------

class LegacyKitsTests(unittest.TestCase):
    """Preserve valid legacy kits: every kit under .claude/kits still parses, and every kit with
    work left is a valid graph. Two finished kits carry prose in `- depends:` lines ("(none
    within this kit)", "T1–T8 (documents their output)"); the validator names those as unknown
    dependencies, which is what they are. Both are complete, so no run is affected; fixing the
    lines removes them from the set below."""

    PROSE_DEPENDS = {"aesop-bridge", "context-rules"}

    def test_every_kit_parses_and_every_unfinished_kit_is_valid(self):
        seen = 0
        invalid = {}
        for tasks_path in sorted(KITS_DIR.glob("*/TASKS.md")):
            tasks = kc.parse_tasks(tasks_path.read_text())
            seen += 1
            graph = kc.graph_state(tasks)
            if graph["state"] == "invalid":
                invalid[tasks_path.parent.name] = graph
            elif any(t["status"] != "done" for t in tasks):
                self.assertIn(graph["state"], ("ready", "interrupted", "waiting"))
        self.assertGreater(seen, 0)
        self.assertLessEqual(set(invalid), self.PROSE_DEPENDS)
        for slug, graph in invalid.items():
            self.assertEqual({f["kind"] for f in graph["findings"]}, {"unknown-dependency"}, slug)
            self.assertEqual(graph["pending"] + graph["in_progress"] + graph["blocked"], [],
                             f"{slug} is not finished, so its graph must be fixed")


class CommandLineTests(unittest.TestCase):
    def _cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = kc._cli(argv)
        return code, out.getvalue(), err.getvalue()

    def test_graph_reports_and_exits_2_on_an_invalid_kit(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = Path(tmp)
            (kit / "TASKS.md").write_text(_kit_text(INVALID_KITS["duplicate-id"]))
            code, out, _err = self._cli(["graph", "--kit", str(kit)])
            self.assertEqual(code, 2)
            self.assertIn("duplicate-id [T1]", out)
            code, out, _err = self._cli(["graph", "--kit", str(kit), "--json"])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(out)["state"], "invalid")

    def test_graph_json_carries_the_whole_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = Path(tmp)
            (kit / "TASKS.md").write_text(_kit_text([
                ("T1", "done", []), ("T2", "pending", ["T1"]), ("T3", "blocked", ["T1"]),
            ]))
            code, out, _err = self._cli(["graph", "--kit", str(kit), "--json"])
            self.assertEqual(code, 0)
            graph = json.loads(out)
            self.assertEqual(graph["state"], "ready")
            self.assertEqual(graph["frontier"], ["T2"])
            self.assertEqual(graph["blocked"], ["T3"])
            self.assertEqual(graph["findings"], [])

    def test_demo_walks_a_diamond_and_refuses_the_invalid_ones_spending_nothing(self):
        code, out, _err = self._cli(["demo"])
        self.assertEqual(code, 0)
        self.assertIn("frontier: T2, T3 (sequential: T2 runs next)", out)
        self.assertIn("graph: complete", out)
        self.assertIn("--task T2: T2 (resume)", out)
        for kind in kc.FINDING_KINDS:
            self.assertIn(f"{kind} [", out)
        self.assertIn("pending -> done: REFUSED", out)
        self.assertIn("in-progress -> done: allowed", out)

    def test_status_on_every_driver_ends_with_the_graph_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = Path(tmp) / "fixturekit"
            kit.mkdir()
            (kit / "TASKS.md").write_text(_kit_text([("T1", "in-progress", []), ("T2", "pending", [])]))
            for driver in (claude, copilot, codex):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    driver.main(["status", "--kit", str(kit)])
                lines = out.getvalue().splitlines()
                self.assertRegex(lines[-2], r"\d+ pending / \d+ in-progress / \d+ done / \d+ blocked")
                self.assertEqual(lines[-1],
                                 "graph: interrupted -- in-progress: T1; resume with --task <id> "
                                 "(also ready, by explicit --task only: T2)")


if __name__ == "__main__":
    unittest.main()
