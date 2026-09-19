"""The three-arm recovery trial protocol (decision-improvement D18): a SPECIFICATION, not a run.

WHAT IS UNDER TEST. `bin/workflow_eval.py`'s D18 section builds one immutable, content-addressed
experiment specification for the kit's first hypothesis -- arm A the actual frozen recovery
policy, arm B the same-model retry control, arm C the same retry plus one bounded contract-context
package -- and the read-only accounting a future run's results would be read through. It builds a
document. It does not run an experiment, and these tests are mostly about the difference.

HOW EACH ACCEPTANCE TERM IS MADE STRUCTURAL RATHER THAN ASSERTED:

  * SYNTHETIC DISPATCHES NONE -- proven twice and neither proof is a mock returning a canned
    value. At runtime every dispatch seam this module can reach (`default_runner`, the protected
    gate, `proc_runner`, and `repo_bench`'s miner, sandbox builder and four graders) is replaced
    by a `_RaisingSeam` that RAISES, and a CONTROL test calls one to prove the trap is armed and
    reachable. Structurally, an AST walk over the D18 section's own functions asserts that none
    of them calls any dispatching name -- with non-empty guards on the section boundary, on the
    set of functions found, and on the number of call nodes actually visited, because a walk that
    finds nothing passes on every input.

  * A=B COLLAPSE -- when the frozen baseline already IS the control, two arms become one arm
    carrying both names, never two independent arms. The control is the other direction: a
    baseline that performs no extra attempt stays a separate arm, so the collapse is not simply
    something that always happens.

  * INPUTS PINNED -- checkpoint, acceptance, model, effort, diagnostics and ceiling live in one
    hashed object every arm cites; each of the six is tested for refusal on absence, one at a
    time; and an arm citing a different sha is refused.

  * EXISTING OWNER WRITES -- `carry_trial_protocol` writes into an envelope's own `labels` and
    `notes` and adds no key, and an AST sweep asserts the D18 section opens no file and names no
    writer. `write_envelope` stays the one envelope writer.

  * D07 REQUIRED LIVE -- a live run's requirements name D07's certification and D06's held-out
    controller SIDE BY SIDE, and satisfying one never discharges the other (Phase 2 F4). The
    certification must be what `exec_policy.certify_profile` actually returns; a hand-written
    `{"certified": True}` satisfies nothing. Nothing is wired: `gate_protected_dispatch` applies
    no confinement and ledgers nothing, so `CONFINED_DISPATCH_WIRED` is False and the flag is
    pinned to the code it describes in both directions.

Synthetic throughout: every fixture is built in this file, no temp home or store is created, no
file outside the repository is read, and nothing is installed.
"""

import ast
import importlib.util
import inspect
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF_PATH = ROOT / "bin" / "workflow_eval.py"
WF_SPEC = importlib.util.spec_from_file_location("workflow_eval_trial_protocol", WF_PATH)
wf = importlib.util.module_from_spec(WF_SPEC)
WF_SPEC.loader.exec_module(wf)

#: decision-improvement D19 (`RecoveryReportTests`, below) reads `bin/decision_eval.py`'s own
#: loader for the same reason `tests/test_decision_eval.py` does: `bin/` is not a package, so a
#: second `import` of it would produce a second, unrelated set of classes.
DE_PATH = ROOT / "bin" / "decision_eval.py"
DE_SPEC = importlib.util.spec_from_file_location("decision_eval_recovery_report", DE_PATH)
de = importlib.util.module_from_spec(DE_SPEC)
DE_SPEC.loader.exec_module(de)
dc = de._contract()

#: The exact banner lines that bound the D18 section. Asserted found before anything is walked:
#: a section slice that silently came back empty would make every structural test below vacuous.
SECTION_START = ("# THREE-ARM RECOVERY TRIAL PROTOCOL (decision-improvement D18) "
                 "-- A SPECIFICATION, NEVER A RUN")
SECTION_END = "# END OF THE THREE-ARM RECOVERY TRIAL PROTOCOL (decision-improvement D18)"

#: Every public name the D18 section is allowed to define. A new one must be added here, which is
#: how a dispatching helper smuggled into the section fails this file rather than sliding past it.
SECTION_FUNCTIONS = {
    "_tp_text", "_tp_mapping", "_tp_count", "_tp_ceiling_number", "_tp_cost", "pin_trial_inputs",
    "_tp_package", "build_arm", "arm_delta", "collapse_equivalent_arms", "trial_cohort",
    "trial_oracles", "trial_extraction", "_certification_evidence", "_study_run_reference",
    "live_requirements", "_blockers_from", "build_trial_protocol", "protocol_ref",
    "require_runnable", "carry_trial_protocol", "_tp_outcome", "arm_accounting",
    "compare_conditional_recovery",
}

#: Names that reach a model, a CLI, a grader, a miner or the filesystem. None of them may be
#: called from the D18 section, whose whole claim is that it produces a document.
DISPATCHING_NAMES = {
    "runner", "default_runner", "gate_protected_dispatch", "require_protected_trial",
    "run_protected_dispatch", "run_confined", "wrap_argv", "ProtectedProfile", "ProtectedLayout",
    "dispatch_cell", "mine_tasks", "mine_issue_tasks", "mine_general_tasks", "make_sandbox",
    "prepare_cell_sandbox", "build_grade_substrate", "grade_cells", "oracle_tests",
    "oracle_judge", "oracle_structural", "oracle_tests_full_patch", "build_plan", "Evaluation",
    "run", "Popen", "check_output", "call", "system", "popen",
}

#: Filesystem verbs. The section states it opens nothing; this is what holds it to that.
WRITER_NAMES = {
    "open", "write_text", "read_text", "write_bytes", "read_bytes", "mkdir", "unlink", "rmtree",
    "replace", "write_envelope", "read_envelope", "write_manifest", "read_manifest",
    "record_exposure", "record_results", "declare_cohort", "select_cohort", "retire",
    "confined_create_bytes", "confined_append", "iterdir", "copytree", "copy2",
}


def _section_bounds():
    """`(start, end)` line numbers of the D18 section, with both banners asserted present."""
    lines = WF_PATH.read_text(encoding="utf-8").splitlines()
    starts = [i + 1 for i, line in enumerate(lines) if line.strip() == SECTION_START]
    ends = [i + 1 for i, line in enumerate(lines) if line.strip() == SECTION_END]
    return starts, ends


def _section_functions():
    """Every `def` whose body lies inside the D18 section, as `{name: ast.FunctionDef}`."""
    starts, ends = _section_bounds()
    tree = ast.parse(WF_PATH.read_text(encoding="utf-8"))
    lo, hi = starts[0], ends[0]
    return {n.name: n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and lo < n.lineno < hi}


def _called_names(node):
    """`(names, call_count)` -- every name CALLED inside `node`.

    A bare `f(...)` contributes `f`; an `a.b.f(...)` contributes `f`, which is what catches
    `_rb().oracle_tests(...)`, `ep.wrap_argv(...)` and `ledger.append(...)` alike. The receiver's
    own name is deliberately NOT collected: it is a local variable, and flagging one because it
    happened to be spelled like a forbidden verb would turn this sweep into a name taboo instead
    of a call sweep.
    """
    names, calls = set(), 0
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        calls += 1
        func = sub.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            names.add(func.attr)
    return names, calls


class _RaisingSeam:
    """A seam that RAISES if ever invoked.

    Not a mock returning a canned value: a canned return is indistinguishable from a real result
    that happened to be ignored, and it would let a leaked dispatch pass silently. This makes the
    failure loud, and a control test below calls one to prove the trap is armed rather than inert.
    """

    def __init__(self, name):
        self.name = name
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError(f"dispatch seam {self.name!r} was reached: "
                             f"args={args!r} kwargs={kwargs!r}")


#: Every seam on `bin/workflow_eval.py` and its `repo_bench` sibling that could reach a model, a
#: CLI or a graded sandbox. `wf._rb()` is the SAME module object the D18 section would get.
WF_SEAMS = ("default_runner", "gate_protected_dispatch", "require_protected_trial",
            "write_envelope", "write_manifest", "record_exposure", "select_cohort")
RB_SEAMS = ("mine_tasks", "make_sandbox", "prepare_cell_sandbox", "build_grade_substrate",
            "grade_cells", "oracle_tests", "oracle_judge", "oracle_structural",
            "oracle_tests_full_patch", "dispatch_cell")


class _ArmedSeams:
    """Context manager that arms every seam and restores them afterwards."""

    def __init__(self, test):
        self.test = test
        self.saved = []
        self.seams = []

    def __enter__(self):
        rb = wf._rb()
        for module, names in ((wf, WF_SEAMS), (rb, RB_SEAMS)):
            for name in names:
                if not hasattr(module, name):
                    continue
                seam = _RaisingSeam(f"{module.__name__}.{name}")
                self.saved.append((module, name, getattr(module, name)))
                self.seams.append(seam)
                setattr(module, name, seam)
        self.test.assertTrue(self.saved, "no dispatch seam was armed; the trap is not set")
        return self

    def __exit__(self, *exc):
        for module, name, original in self.saved:
            setattr(module, name, original)
        return False


def _inputs(**over):
    """The pinned six, synthetic. No real model id, no real repository, no real command."""
    kwargs = {
        "checkpoint": {
            "item": "item-0001", "group": "group-a", "manifest": "manifest-0001",
            "base_commit": "0" * 40, "failure_class": "verification",
            "restored_by": "repo_bench.make_sandbox",
            "initial_attempt": {"basis": "estimated", "usd": 0.40},
        },
        "acceptance": {"command": "fixture-check", "sha": "acc-sha-1"},
        "model": "fixture-model-1",
        "effort": "medium",
        "diagnostics": ["failing-test", "stderr"],
        "ceiling": {"max_usd": 2.0, "max_dispatches": 4, "max_wall_seconds": 900},
    }
    kwargs.update(over)
    return wf.pin_trial_inputs(**kwargs)


def _package(**over):
    pkg = {"id": "ctx-0001", "sha": "ctx-sha-1", "items": 3, "bound": "<= 3 files, <= 8000 chars"}
    pkg.update(over)
    return pkg


def _arms(inputs, *, baseline_attempts=1, baseline_diagnostics=("failing-test", "stderr"),
          repair_model_differs=False, repair_package=True):
    """A, B and C over one pinned input set. `baseline_attempts=0` is the non-collapsing case."""
    arms = [
        wf.build_arm("A", inputs=inputs, extra_attempts=baseline_attempts,
                     diagnostics_applied=list(baseline_diagnostics), context_package=None,
                     remaining_recovery="declared remaining recovery path"),
        wf.build_arm("B", inputs=inputs, extra_attempts=1,
                     diagnostics_applied=["failing-test", "stderr"], context_package=None,
                     remaining_recovery="declared remaining recovery path"),
    ]
    c_inputs = inputs
    if repair_model_differs:
        c_inputs = _inputs(model="fixture-model-2")
    arms.append(wf.build_arm(
        "C", inputs=c_inputs, extra_attempts=1,
        diagnostics_applied=["failing-test", "stderr"],
        context_package=_package() if repair_package else None,
        remaining_recovery="declared remaining recovery path"))
    return arms


def _manifest(*, leak=False, partition_items=2):
    """A D06 manifest built by its OWN owner over synthetic tasks -- never hand-assembled.

    `allocation` puts the whole pool in `promotion` so the cohort is deterministic; the grouping
    and screening that decide whether anything lands there at all are `build_manifest`'s.
    """
    tasks = []
    for i in range(partition_items):
        subject = f"fix the adapter so it rejects an empty payload ({i})"
        statement = "fixture statement %d: the adapter accepts an empty payload" % i
        source = "issue"
        if leak:
            # Exactly repo_bench's no-`gh` fallback: the problem statement IS the fix commit's
            # own subject plus its body, which is what `statement_source="commit-message"` means.
            statement = f"{subject}\n\nthe adapter validated nothing before this change"
            source = "commit-message"
        tasks.append({
            "task_id": f"task-{i:03d}", "mode": "issue-replay", "issue": f"{100 + i}",
            "subject": subject, "statement": statement,
            "statement_source": source, "reference_patch": "",
            "size_profile": "S", "oracle_tests_available": True,
        })
    return wf.build_manifest("fixture-repo", "0" * 40, tasks,
                             allocation={"promotion": 1}, on_leak="quarantine",
                             acceptance="fixture-check", created_by="test")


def _certification(**over):
    """The shape `exec_policy.certify_profile` actually returns, for a fully satisfied plan."""
    cert = {"profile": "fixture-profile", "backend": "fixture-backend", "certified": True,
            "required": 21, "satisfied": 21, "blocking": [],
            "not_proven": ["general filesystem confidentiality is not proven"],
            "label": "a hash is not enforcement"}
    cert.update(over)
    return cert


def _declarations(**over):
    decl = {name: f"operator-declared {name}" for name in wf.OPERATOR_DECLARATIONS}
    decl.update(over)
    return decl


def _spec(**over):
    inputs = over.pop("inputs", None) or _inputs()
    kwargs = {
        "inputs": inputs, "arms": over.pop("arms", None) or _arms(inputs),
        "manifest": None, "partition": "promotion", "cohort": None, "certification": None,
        "full_task_study_run": None, "operator_declarations": {}, "created_by": "test",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    kwargs.update(over)
    return wf.build_trial_protocol(**kwargs)


def _record(item, accepted, *, initial=0.40, reused=False, recovery=(), overhead=()):
    return {
        "item": item, "accepted": accepted,
        "initial_attempt": {"basis": "estimated", "usd": initial},
        "initial_attempt_reused": reused,
        "recovery_costs": [{"basis": "estimated", "usd": usd} for usd in recovery],
        "overhead": [{"kind": kind, "scope": scope, "cost": {"basis": "estimated", "usd": usd}}
                     for kind, scope, usd in overhead],
    }


class ThreeArmProtocolTests(unittest.TestCase):
    """decision-improvement D18. Every test below is offline and synthetic."""

    maxDiff = None

    # -- synthetic dispatches none: the runtime proof ------------------------------------------

    def test_the_dispatch_trap_is_armed_and_reachable(self):
        """CONTROL. Without this, every "nothing was dispatched" test below could be passing
        because the seams were never replaced rather than because nothing reached them."""
        with _ArmedSeams(self) as armed:
            self.assertGreaterEqual(len(armed.saved), len(WF_SEAMS),
                                    "fewer seams armed than this module defines")
            with self.assertRaises(AssertionError):
                wf.default_runner("stub")
            rb = wf._rb()
            with self.assertRaises(AssertionError):
                rb.mine_tasks("fixture-repo")

    def test_building_the_whole_specification_reaches_no_dispatch_seam(self):
        with _ArmedSeams(self) as armed:
            inputs = _inputs()
            arms = _arms(inputs)
            manifest = _manifest()
            spec = wf.build_trial_protocol(
                inputs=inputs, arms=arms, manifest=manifest, partition="promotion", cohort=None,
                certification=_certification(), full_task_study_run=None,
                operator_declarations=_declarations(), created_by="test",
                created_at="2026-01-01T00:00:00+00:00")
            wf.protocol_ref(spec)
            wf.carry_trial_protocol({}, spec)
            with self.assertRaises(wf.EvalError):
                wf.require_runnable(spec)
            accounting = [wf.arm_accounting(arm, [_record("item-0001", True, recovery=(0.2,))])
                          for arm in spec["content"]["arms"]]
            wf.compare_conditional_recovery(accounting, baseline_arm="A", threshold=None)
            self.assertEqual([s.calls for s in armed.seams], [[] for _ in armed.seams])

    def test_no_d18_function_takes_a_runner_a_store_or_a_path(self):
        """A function that cannot be handed a dispatcher or a destination cannot use one."""
        forbidden = ("runner", "dispatch", "store", "store_dir", "prefs_dir", "scratch_dir",
                     "dir", "path", "root", "repo", "out", "file")
        checked = 0
        for name in sorted(SECTION_FUNCTIONS):
            fn = getattr(wf, name)
            for param in inspect.signature(fn).parameters:
                checked += 1
                lowered = param.lower()
                self.assertFalse(
                    any(lowered == bad or lowered.endswith("_" + bad) for bad in forbidden),
                    f"{name}({param}) offers a dispatch or a destination to a specification")
        self.assertGreater(checked, 0, "no parameter was inspected")

    # -- synthetic dispatches none: the structural proof ---------------------------------------

    def test_the_section_banners_bound_exactly_one_region(self):
        """The non-empty guard every structural test below depends on."""
        starts, ends = _section_bounds()
        self.assertEqual(len(starts), 1, f"expected one start banner, found {len(starts)}")
        self.assertEqual(len(ends), 1, f"expected one end banner, found {len(ends)}")
        self.assertLess(starts[0], ends[0], "the section's end banner precedes its start")

    def test_the_section_defines_exactly_the_functions_this_file_knows_about(self):
        found = _section_functions()
        self.assertTrue(found, "no function was found inside the D18 section")
        self.assertEqual(set(found), SECTION_FUNCTIONS,
                         "a function appeared in or left the D18 section without this file's "
                         "knowledge; every D18 function is swept for dispatch and for writes")

    def test_no_function_in_the_section_calls_anything_that_dispatches(self):
        found = _section_functions()
        self.assertTrue(found, "no function was found inside the D18 section")
        total_calls = 0
        for name, node in sorted(found.items()):
            names, calls = _called_names(node)
            total_calls += calls
            leaked = sorted(names & DISPATCHING_NAMES)
            self.assertEqual(leaked, [], f"{name} calls {leaked}, which reaches a model, a CLI, "
                                         f"a grader or a miner from a specification builder")
        self.assertGreater(total_calls, 0, "the walk visited no call at all, so it constrains "
                                           "nothing")

    def test_no_function_in_the_section_opens_reads_or_writes_anything(self):
        found = _section_functions()
        self.assertTrue(found, "no function was found inside the D18 section")
        total_calls = 0
        for name, node in sorted(found.items()):
            names, calls = _called_names(node)
            total_calls += calls
            leaked = sorted(names & WRITER_NAMES)
            self.assertEqual(leaked, [], f"{name} calls {leaked}; the specification writes "
                                         f"nothing and workflow_eval.write_envelope stays the "
                                         f"one envelope writer")
        self.assertGreater(total_calls, 0, "the walk visited no call at all")

    # -- A = B collapse ------------------------------------------------------------------------

    def test_a_baseline_that_already_is_the_control_collapses_into_one_arm(self):
        spec = _spec()
        content = spec["content"]
        self.assertEqual(content["nominal_arms"], ["A", "B", "C"])
        self.assertEqual([a["arm"] for a in content["arms"]], ["A", "C"])
        collapsed = content["arms"][0]
        self.assertEqual(collapsed["collapsed_from"], ["A", "B"])
        self.assertEqual(collapsed["collapse_reason"], "arms-equivalent")
        self.assertEqual([e["arms"] for e in content["equivalences"]], [["A", "B"]])
        self.assertIn("never two independent arms", content["equivalences"][0]["note"])

    def test_a_baseline_that_retries_differently_stays_a_separate_arm(self):
        """The control on the collapse: it is not something that always happens."""
        inputs = _inputs()
        spec = _spec(inputs=inputs, arms=_arms(inputs, baseline_attempts=0))
        content = spec["content"]
        self.assertEqual([a["arm"] for a in content["arms"]], ["A", "B", "C"])
        self.assertEqual(content["equivalences"], [])
        self.assertEqual([a["collapsed_from"] for a in content["arms"]], [["A"], ["B"], ["C"]])

    def test_a_baseline_with_different_diagnostics_stays_a_separate_arm(self):
        inputs = _inputs()
        spec = _spec(inputs=inputs, arms=_arms(inputs, baseline_diagnostics=("stderr",)))
        self.assertEqual([a["arm"] for a in spec["content"]["arms"]], ["A", "B", "C"])

    def test_the_collapsed_arm_keeps_both_roles_rather_than_losing_one(self):
        arms = _spec()["content"]["arms"]
        self.assertIn(wf.ARM_ROLES["A"], arms[0]["role"])
        self.assertIn(wf.ARM_ROLES["B"], arms[0]["role"])

    def test_the_arm_signature_ignores_the_arms_own_name(self):
        inputs = _inputs()
        a = wf.build_arm("A", inputs=inputs, extra_attempts=1,
                         diagnostics_applied=["stderr"], context_package=None,
                         remaining_recovery="p")
        b = wf.build_arm("B", inputs=inputs, extra_attempts=1,
                         diagnostics_applied=["stderr"], context_package=None,
                         remaining_recovery="p")
        self.assertEqual(a["signature"], b["signature"])
        self.assertNotIn("arm", wf.ARM_SIGNATURE_FIELDS)

    def test_a_collapsed_cohort_is_accounted_once_not_twice(self):
        spec = _spec()
        rows = [_record("i1", True, recovery=(0.2,)), _record("i2", False, recovery=(0.2,))]
        totals = [wf.arm_accounting(arm, rows) for arm in spec["content"]["arms"]]
        self.assertEqual(len(totals), 2)
        self.assertEqual(totals[0]["collapsed_from"], ["A", "B"])
        self.assertEqual(sum(t["items"] for t in totals), 4,
                         "two arms over two items; a collapse that produced three arms would "
                         "count the baseline cohort twice")

    # -- inputs pinned -------------------------------------------------------------------------

    def test_every_one_of_the_six_pinned_inputs_is_required(self):
        """Each absence in isolation: a field that only ever fails beside another proves nothing."""
        base = {
            "checkpoint": {"item": "i", "group": "g", "manifest": "m", "base_commit": "c",
                           "failure_class": "verification", "restored_by": "r",
                           "initial_attempt": {"basis": "estimated", "usd": 0.1}},
            "acceptance": {"command": "c", "sha": "s"}, "model": "m", "effort": "e",
            "diagnostics": ["d"], "ceiling": {"max_usd": 1.0, "max_dispatches": 1,
                                              "max_wall_seconds": 60},
        }
        self.assertEqual(sorted(base), sorted(wf.PINNED_INPUTS))
        wf.pin_trial_inputs(**base)  # the control: complete, it builds
        for name in wf.PINNED_INPUTS:
            with self.subTest(missing=name):
                broken = dict(base)
                broken.pop(name)
                with self.assertRaises(TypeError):
                    wf.pin_trial_inputs(**broken)
            with self.subTest(empty=name):
                broken = dict(base)
                broken[name] = None
                with self.assertRaises(wf.EvalError):
                    wf.pin_trial_inputs(**broken)

    def test_no_pinned_input_has_a_default_to_inherit(self):
        signature = inspect.signature(wf.pin_trial_inputs)
        self.assertEqual(sorted(signature.parameters), sorted(wf.PINNED_INPUTS))
        for name, param in signature.parameters.items():
            self.assertIs(param.default, inspect.Parameter.empty,
                          f"{name} has a default, so a caller can inherit a decision it never "
                          f"made")
            self.assertEqual(param.kind, inspect.Parameter.KEYWORD_ONLY)

    def test_build_trial_protocol_has_no_default_either(self):
        for name, param in inspect.signature(wf.build_trial_protocol).parameters.items():
            self.assertIs(param.default, inspect.Parameter.empty, f"{name} has a default")
            self.assertEqual(param.kind, inspect.Parameter.KEYWORD_ONLY)

    def test_a_checkpoint_without_its_initial_attempt_cost_is_refused(self):
        checkpoint = {"item": "i", "group": "g", "manifest": "m", "base_commit": "c",
                      "failure_class": "verification", "restored_by": "r"}
        with self.assertRaises(wf.EvalError) as caught:
            _inputs(checkpoint=checkpoint)
        self.assertIn("initial_attempt", str(caught.exception))

    def test_an_unpriceable_ceiling_is_refused_rather_than_treated_as_no_ceiling(self):
        for bad in ({"max_usd": None, "max_dispatches": 1, "max_wall_seconds": 60},
                    {"max_usd": 0, "max_dispatches": 1, "max_wall_seconds": 60},
                    {"max_usd": 1.0, "max_dispatches": 0, "max_wall_seconds": 60},
                    {"max_usd": 1.0, "max_dispatches": True, "max_wall_seconds": 60},
                    {"max_usd": 1.0, "max_dispatches": 1, "max_wall_seconds": float("inf")}):
            with self.subTest(ceiling=bad), self.assertRaises(wf.EvalError):
                _inputs(ceiling=bad)

    def test_the_pinned_object_is_content_addressed_and_order_independent(self):
        a = _inputs(diagnostics=["failing-test", "stderr"])
        b = _inputs(diagnostics=["stderr", "failing-test"])
        self.assertEqual(a["sha"], b["sha"])
        self.assertNotEqual(a["sha"], _inputs(effort="high")["sha"])
        self.assertNotEqual(a["sha"], _inputs(model="fixture-model-2")["sha"])

    def test_an_arm_citing_different_inputs_is_refused(self):
        inputs = _inputs()
        with self.assertRaises(wf.EvalError) as caught:
            _spec(inputs=inputs, arms=_arms(inputs, repair_model_differs=True))
        self.assertIn("the arms are not comparing the same", str(caught.exception))

    def test_an_arm_cannot_apply_a_diagnostic_the_trial_never_pinned(self):
        inputs = _inputs(diagnostics=["stderr"])
        with self.assertRaises(wf.EvalError) as caught:
            wf.build_arm("B", inputs=inputs, extra_attempts=1,
                         diagnostics_applied=["stderr", "smuggled"], context_package=None,
                         remaining_recovery="p")
        self.assertIn("smuggled", str(caught.exception))

    def test_changing_the_model_and_the_context_at_once_is_refused_by_name(self):
        inputs = _inputs()
        b = wf.build_arm("B", inputs=inputs, extra_attempts=1,
                         diagnostics_applied=["failing-test", "stderr"], context_package=None,
                         remaining_recovery="p")
        c = wf.build_arm("C", inputs=inputs, extra_attempts=2,
                         diagnostics_applied=["failing-test", "stderr"],
                         context_package=_package(), remaining_recovery="p")
        with self.assertRaises(wf.EvalError) as caught:
            _spec(inputs=inputs, arms=[b, c])
        self.assertIn("extra_attempts", str(caught.exception))
        self.assertIn("cannot attribute its own result", str(caught.exception))

    def test_an_arm_c_with_no_package_has_no_intervention_and_is_refused(self):
        inputs = _inputs()
        with self.assertRaises(wf.EvalError) as caught:
            _spec(inputs=inputs, arms=_arms(inputs, repair_package=False))
        self.assertIn("no intervention under test", str(caught.exception))

    def test_only_arm_c_may_carry_the_intervention(self):
        inputs = _inputs()
        for name in ("A", "B"):
            with self.subTest(arm=name), self.assertRaises(wf.EvalError):
                wf.build_arm(name, inputs=inputs, extra_attempts=1, diagnostics_applied=[],
                             context_package=_package(), remaining_recovery="p")

    def test_an_empty_context_package_is_an_abstention_not_an_arm_c_that_does_nothing(self):
        """The shared plan's "no applicable context is a legitimate abstention": a checkpoint with
        nothing to supply leaves the cohort, rather than diluting arm C with a repair that was
        never applied."""
        with self.assertRaises(wf.EvalError) as caught:
            wf.build_arm("C", inputs=_inputs(), extra_attempts=1, diagnostics_applied=[],
                         context_package=_package(items=0), remaining_recovery="p")
        self.assertIn("items", str(caught.exception))

    def test_the_context_package_is_a_reference_and_never_its_payload(self):
        arm = wf.build_arm("C", inputs=_inputs(), extra_attempts=1, diagnostics_applied=[],
                           context_package=_package(files=["secret.py"], text="print(1)"),
                           remaining_recovery="p")
        self.assertEqual(sorted(arm["context_package"]), ["bound", "id", "items", "sha"])

    def test_the_specification_is_content_addressed_outside_its_provenance(self):
        one = _spec(created_by="alice", created_at="2026-01-01T00:00:00+00:00")
        two = _spec(created_by="bob", created_at="2026-06-06T06:06:06+00:00")
        self.assertEqual(one["sha"], two["sha"])
        self.assertEqual(one["id"], two["id"])
        self.assertNotEqual(one["created_at"], two["created_at"])
        self.assertEqual(one["digest"]["excludes"],
                         ["created_at", "created_by", "id", "sha", "digest"])

    # -- the frozen, grouped, held-out cohort ---------------------------------------------------

    def test_the_cohort_comes_from_the_immutable_manifest_grouped(self):
        manifest = _manifest(partition_items=3)
        cohort = wf.trial_cohort(manifest, "promotion", cohort=None)
        self.assertTrue(cohort["frozen"])
        self.assertTrue(cohort["held_out"])
        self.assertEqual(cohort["item_count"], 3)
        self.assertEqual(cohort["group_count"], 3)
        self.assertEqual(cohort["manifest_ref"], wf.manifest_ref(manifest))
        self.assertIn("one defect, one group, one partition", cohort["grouping"])

    def test_an_absent_manifest_is_a_cohort_that_is_not_frozen(self):
        cohort = wf.trial_cohort(None, "promotion", cohort=None)
        self.assertFalse(cohort["frozen"])
        self.assertEqual(cohort["item_count"], 0)
        self.assertIsNone(cohort["manifest_ref"])
        blockers = {b["blocker"] for b in _spec(manifest=None)["content"]["blockers"]}
        self.assertIn("cohort-not-frozen", blockers)

    def test_a_fitting_partition_can_never_be_cited_as_held_out_evidence(self):
        manifest = wf.build_manifest(
            "fixture-repo", "0" * 40,
            [{"task_id": "task-000", "mode": "issue-replay", "issue": "1",
              "subject": "s", "statement": "a fixture statement about an adapter",
              "statement_source": "issue", "reference_patch": "", "size_profile": "S",
              "oracle_tests_available": True}],
            allocation={"calibration": 1}, on_leak="quarantine", created_by="test")
        spec = _spec(manifest=manifest, partition="calibration")
        detail = next(b["detail"] for b in spec["content"]["blockers"]
                      if b["blocker"] == "no-held-out-evidence")
        self.assertIn("fitting material", detail)

    def test_the_default_mining_cohort_is_reported_empty_with_its_cause_named(self):
        """D06's product finding: without `gh`, the statement IS the fix commit message, the
        screen flags it, quarantine is contagious within the group, and the partition empties."""
        manifest = _manifest(leak=True, partition_items=2)
        self.assertEqual(wf.manifest_summary(manifest)["partitions"]["promotion"], 0)
        spec = _spec(manifest=manifest)
        detail = next(b["detail"] for b in spec["content"]["blockers"]
                      if b["blocker"] == "no-held-out-evidence")
        self.assertIn("future-fix-message", detail)
        self.assertIn("EMPTY", detail)

    def test_a_cohort_never_declared_on_the_manifest_is_refused(self):
        with self.assertRaises(wf.EvalError) as caught:
            wf.trial_cohort(_manifest(), "promotion", cohort="chosen-afterwards")
        self.assertIn("not a cohort", str(caught.exception))

    def test_a_predeclared_cohort_narrows_to_its_own_declared_items(self):
        tasks = [{"task_id": f"task-{i:03d}", "mode": "issue-replay", "issue": str(200 + i),
                  "subject": f"s{i}", "statement": f"a fixture statement number {i}",
                  "statement_source": "issue", "reference_patch": "", "size_profile": "S",
                  "oracle_tests_available": True} for i in range(3)]
        seed = wf.build_manifest("fixture-repo", "0" * 40, tasks, allocation={"promotion": 1},
                                 on_leak="quarantine", created_by="test")
        chosen = seed["content"]["partitions"]["promotion"][:2]
        manifest = wf.build_manifest(
            "fixture-repo", "0" * 40, tasks, allocation={"promotion": 1}, on_leak="quarantine",
            created_by="test",
            cohorts=[{"cohort": "narrow", "partition": "promotion", "items": chosen}])
        cohort = wf.trial_cohort(manifest, "promotion", cohort="narrow")
        self.assertEqual(cohort["items"], sorted(chosen))
        self.assertEqual(cohort["item_count"], 2)

    # -- D07 required live, paired with D06 (Phase 2 F4) ----------------------------------------

    def test_a_live_run_requires_the_protected_profile_and_the_held_out_cohort_together(self):
        rows = {r["requirement"]: r for r in _spec()["content"]["live_requirements"]}
        self.assertIn("protected-profile-certified", rows)
        self.assertIn("held-out-evidence", rows)
        self.assertEqual(rows["protected-profile-certified"]["pairs_with"], "held-out-evidence")
        self.assertEqual(rows["held-out-evidence"]["pairs_with"], "protected-profile-certified")
        self.assertIn("certify_profile", rows["protected-profile-certified"]["owner"])
        self.assertIn("require_held_out", rows["held-out-evidence"]["owner"])

    def test_satisfying_the_profile_alone_never_discharges_the_held_out_requirement(self):
        spec = _spec(manifest=None, certification=_certification())
        rows = {r["requirement"]: r for r in spec["content"]["live_requirements"]}
        self.assertTrue(rows["protected-profile-certified"]["satisfied"])
        self.assertFalse(rows["held-out-evidence"]["satisfied"])
        self.assertIn("cohort-not-frozen", {b["blocker"] for b in spec["content"]["blockers"]})

    def test_satisfying_the_cohort_alone_never_discharges_the_profile_requirement(self):
        spec = _spec(manifest=_manifest(), certification=None)
        rows = {r["requirement"]: r for r in spec["content"]["live_requirements"]}
        self.assertTrue(rows["held-out-evidence"]["satisfied"])
        self.assertFalse(rows["protected-profile-certified"]["satisfied"])
        self.assertIn("protected-profile-uncertified",
                      {b["blocker"] for b in spec["content"]["blockers"]})

    def test_a_certification_claim_that_is_not_d07s_arithmetic_satisfies_nothing(self):
        """The third case is the one a coarser fixture misses. `{"certified": True}` alone is
        caught twice over -- by the missing-keys check AND, downstream, by the absent sentinel
        plan -- so it proves nothing about the first. A claim whose ARITHMETIC is all present and
        which merely never names a profile or a backend reaches the first check alone."""
        nameless = {"certified": True, "required": 21, "satisfied": 21, "blocking": []}
        for bad, why in (({"certified": True}, "missing everything"),
                         (nameless, "names no profile and no backend"),
                         (_certification(certified="yes"), "not literally True"),
                         (_certification(required=0, satisfied=0), "no sentinel plan"),
                         (_certification(satisfied=20), "partially satisfied"),
                         (_certification(blocking=[{"id": "x", "why": "y"}]), "blocking finding")):
            with self.subTest(why=why):
                spec = _spec(manifest=_manifest(), certification=bad)
                self.assertIn("protected-profile-uncertified",
                              {b["blocker"] for b in spec["content"]["blockers"]})
        row = next(r for r in _spec(manifest=_manifest(), certification=nameless)
                   ["content"]["live_requirements"]
                   if r["requirement"] == "protected-profile-certified")
        self.assertIn("missing ['profile', 'backend']", row["reason"])

    def test_a_complete_certification_is_carried_as_a_reference_not_a_report(self):
        spec = _spec(manifest=_manifest(), certification=_certification())
        row = next(r for r in spec["content"]["live_requirements"]
                   if r["requirement"] == "protected-profile-certified")
        self.assertTrue(row["satisfied"])
        self.assertEqual(sorted(row["evidence"]),
                         ["backend", "label", "not_proven", "profile", "required", "satisfied"])
        self.assertIn("AVAILABILITY gate", row["note"])

    def test_nothing_is_wired_so_a_live_trial_is_blocked_by_derivation(self):
        """D08's gate applies no confinement and ledgers nothing. The flag says so, and the two
        assertions below keep the flag and the code from drifting apart in either direction."""
        self.assertIs(wf.CONFINED_DISPATCH_WIRED, False)
        source = WF_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        gate = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                    and n.name == "gate_protected_dispatch")
        names, calls = _called_names(gate)
        self.assertGreater(calls, 0, "the gate's body has no call at all to inspect")
        self.assertEqual(sorted(names & {"wrap_argv", "ProtectedProfile", "ProtectedLayout",
                                         "run_confined"}), [],
                         "the gate now confines something; CONFINED_DISPATCH_WIRED must move in "
                         "the same edit, together with the ledger open/close")
        self.assertEqual(sorted(names & {"append", "ledger", "AttemptLedger", "make_ref"}), [],
                         "the gate now records something; CONFINED_DISPATCH_WIRED must move in "
                         "the same edit, together with a confining runner")

    def test_a_specification_always_refuses_to_be_treated_as_a_run(self):
        spec = _spec(manifest=_manifest(), certification=_certification(),
                     full_task_study_run={"run_id": "r1", "results_ref": "sha1"},
                     operator_declarations=_declarations())
        blockers = {b["blocker"] for b in spec["content"]["blockers"]}
        self.assertEqual(blockers, {"confining-dispatch-unwired"},
                         "every satisfiable precondition was satisfied, and the one that is not "
                         "satisfiable by data still refuses")
        with self.assertRaises(wf.EvalError) as caught:
            wf.require_runnable(spec)
        self.assertIn("not a run", str(caught.exception))
        self.assertIs(spec["content"]["runnable"], False)

    # -- the enforcement point consults the thing being enforced ---------------------------------

    def test_a_spec_with_its_blockers_emptied_and_a_stale_sha_is_refused_as_tampered(self):
        """THE DEFECT THIS PAIR FIXES. `require_runnable` used to trust the dict it was handed: it
        read `content["blockers"]` and never re-derived the digest. So the
        `confining-dispatch-unwired` blocker -- derived from code and pinned in both directions by
        `test_nothing_is_wired_so_a_live_trial_is_blocked_by_derivation` -- was dischargeable by a
        caller who emptied the list, without touching `CONFINED_DISPATCH_WIRED` at all.

        The specification is content-addressed, so this is detectable and the check is the whole
        fix: re-hash `content` the way `build_trial_protocol` hashed it and refuse a mismatch.
        """
        spec = _spec(manifest=_manifest(), certification=_certification(),
                     full_task_study_run={"run_id": "r1", "results_ref": "sha1"},
                     operator_declarations=_declarations())
        honest_sha = spec["sha"]
        self.assertTrue(spec["content"]["blockers"], "nothing to empty; the tamper is a no-op")
        spec["content"]["blockers"] = []
        self.assertEqual(spec["sha"], honest_sha,
                         "leaving the sha stale is the point: this is the tamper a caller makes")
        with self.assertRaises(wf.EvalError) as caught:
            wf.require_runnable(spec)
        message = str(caught.exception)
        self.assertIn("TAMPERED", message)
        self.assertIn(honest_sha, message)
        self.assertNotIn("unsatisfied precondition", message,
                         "a forged specification must never be reported as an honest one")

    def test_a_fabricated_spec_dict_is_refused_instead_of_being_returned(self):
        """The minimal forgery: four keys, no `build_trial_protocol` anywhere near it. This used to
        be RETURNED, which is what made the gate decorative."""
        forged = {"id": "deadbeefdeadbeef", "sha": "0" * 64, "v": wf.TRIAL_PROTOCOL_VERSION,
                  "content": {"blockers": []}}
        with self.assertRaises(wf.EvalError) as caught:
            wf.require_runnable(forged)
        self.assertIn("TAMPERED", str(caught.exception))

    def test_an_untampered_spec_reaches_the_blocker_path_and_never_the_digest_refusal(self):
        """THE MASKING RISK IS IN THE FIX, NOT ONLY IN THE OLD CODE. A digest check that refused
        EVERY specification -- a canonicalisation that did not round-trip, a hash taken over the
        wrong object -- would turn every assertion in this file about blockers into a pass for the
        wrong reason while the suite stayed green. So the two refusals are told apart here BY
        MESSAGE, not merely by exception type, and the round-trip is asserted directly.
        """
        shapes = {
            "nothing supplied": {},
            "everything satisfiable satisfied": {
                "manifest": _manifest(), "certification": _certification(),
                "full_task_study_run": {"run_id": "r1", "results_ref": "sha1"},
                "operator_declarations": _declarations()},
            "leaking manifest quarantined": {
                "manifest": _manifest(leak=True), "certification": _certification()},
        }
        for label, over in shapes.items():
            with self.subTest(spec=label):
                spec = _spec(**over)
                self.assertEqual(wf._sha(wf._canonical(spec["content"])), spec["sha"],
                                 "an honest specification must verify against its own digest, or "
                                 "every blocker assertion in this file is vacuous")
                with self.assertRaises(wf.EvalError) as caught:
                    wf.require_runnable(spec)
                message = str(caught.exception)
                self.assertIn("not a run", message)
                self.assertIn("unsatisfied precondition", message)
                self.assertIn("confining-dispatch-unwired", message)
                self.assertNotIn("TAMPERED", message,
                                 "the digest check is refusing honest specifications, so the "
                                 "blocker path is never exercised")
                self.assertNotIn("malformed specification", message)

    def test_tampering_a_field_that_is_not_the_blockers_is_refused_by_the_same_digest(self):
        """The reverse direction: without this, the check above would be a test of one FIELD rather
        than of the digest. `cohort.held_out` is the nastiest field to flip -- it is what turns a
        fitting partition into a claim of held-out evidence -- and it is nowhere near `blockers`.
        """
        spec = _spec(manifest=_manifest(), certification=_certification(),
                     full_task_study_run={"run_id": "r1", "results_ref": "sha1"},
                     operator_declarations=_declarations())
        honest_sha = spec["sha"]
        cohort = spec["content"]["cohort"]
        self.assertIsInstance(cohort["held_out"], bool)
        cohort["held_out"] = not cohort["held_out"]
        self.assertEqual(spec["sha"], honest_sha)
        with self.assertRaises(wf.EvalError) as caught:
            wf.require_runnable(spec)
        self.assertIn("TAMPERED", str(caught.exception))

    def test_a_malformed_spec_is_an_eval_error_and_never_a_key_or_type_error(self):
        """A caller handing in rubbish gets this module's own refusal, not a stack trace from
        `dict.__getitem__` or `json.dumps`. `assertRaises(EvalError)` is what rules a `KeyError` or
        a `TypeError` out -- neither is an `EvalError`, so either would fail this test as an error
        rather than pass it -- and `assertIs(type(...))` rules out a subclass standing in.
        """
        cases = {
            "not a mapping at all": None,
            "a list": [],
            "a string": "spec",
            "empty": {},
            "content absent": {"sha": "0" * 64},
            "sha absent": {"content": {"blockers": []}},
            "content is None": {"content": None, "sha": "0" * 64},
            "content is a list": {"content": [], "sha": "0" * 64},
            "sha is None": {"content": {}, "sha": None},
            "sha is blank": {"content": {}, "sha": "   "},
            "sha is an int": {"content": {}, "sha": 7},
            "content does not serialise": {"content": {"blockers": {1, 2}}, "sha": "0" * 64},
        }
        for label, case in cases.items():
            with self.subTest(spec=label):
                with self.assertRaises(wf.EvalError) as caught:
                    wf.require_runnable(case)
                self.assertIs(type(caught.exception), wf.EvalError)

    def test_every_blocker_code_is_in_the_closed_vocabulary(self):
        spec = _spec()
        codes = {b["blocker"] for b in spec["content"]["blockers"]}
        self.assertTrue(codes)
        self.assertEqual(sorted(codes - set(wf.PROTOCOL_BLOCKERS)), [])

    def test_each_blocker_can_be_produced_in_isolation(self):
        """A reason that only ever fires beside another proves nothing about itself."""
        full = {"manifest": _manifest(), "certification": _certification(),
                "full_task_study_run": {"run_id": "r1", "results_ref": "sha1"},
                "operator_declarations": _declarations()}
        cases = {
            "cohort-not-frozen": {"manifest": None},
            "protected-profile-uncertified": {"certification": None},
            "full-task-study-not-run": {"full_task_study_run": None},
            "operator-declaration-missing": {"operator_declarations": _declarations(
                sample_size=None)},
        }
        for code, override in cases.items():
            with self.subTest(blocker=code):
                spec = _spec(**{**full, **override})
                codes = {b["blocker"] for b in spec["content"]["blockers"]}
                self.assertEqual(codes, {code, "confining-dispatch-unwired"})

    # -- no invented number ----------------------------------------------------------------------

    def test_no_sample_size_or_threshold_is_supplied_when_none_was_declared(self):
        spec = _spec()
        self.assertEqual(sorted(spec["content"]["declarations"]),
                         sorted(wf.OPERATOR_DECLARATIONS))
        self.assertEqual(set(spec["content"]["declarations"].values()), {None})
        missing = {b["detail"] for b in spec["content"]["blockers"]
                   if b["blocker"] == "operator-declaration-missing"}
        self.assertEqual(missing, set(wf.OPERATOR_DECLARATIONS))
        self.assertIn(wf.NO_INVENTED_NUMBER_LABEL, spec["content"]["labels"])

    def test_the_module_defines_no_default_sample_size_or_success_threshold(self):
        found = _section_functions()
        self.assertTrue(found)
        constants = {name for name in dir(wf) if name.isupper()}
        self.assertTrue(constants)
        for name in sorted(constants):
            lowered = name.lower()
            if not any(word in lowered for word in ("sample", "threshold", "min_n", "power")):
                continue
            value = getattr(wf, name)
            self.assertNotIsInstance(value, (int, float),
                                     f"{name} is a numeric sample/threshold default this module "
                                     f"has no evidence for")

    def test_a_comparison_returns_no_verdict_without_an_operator_threshold(self):
        spec = _spec()
        accepted = [_record(f"i{i}", True, recovery=(0.2,)) for i in range(3)]
        failed = [_record(f"j{i}", False, recovery=(0.2,)) for i in range(3)]
        base = wf.arm_accounting(spec["content"]["arms"][0], accepted[:1] + failed)
        repair = wf.arm_accounting(spec["content"]["arms"][1], accepted + failed[:1])
        rows = wf.compare_conditional_recovery([base, repair], baseline_arm="A", threshold=None)
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["verdict"])
        self.assertIn("no operator-declared practical gain threshold", rows[0]["verdict_reason"])
        self.assertGreater(rows[0]["delta"], 0.0)
        self.assertIsNotNone(rows[0]["intervals_overlap"])

    def test_a_comparison_names_the_threshold_as_the_operators_when_one_is_declared(self):
        spec = _spec()
        base = wf.arm_accounting(spec["content"]["arms"][0],
                                 [_record("i0", True), _record("i1", False)])
        repair = wf.arm_accounting(spec["content"]["arms"][1],
                                   [_record("i0", True), _record("i1", True)])
        rows = wf.compare_conditional_recovery([base, repair], baseline_arm="A", threshold=0.2)
        self.assertEqual(rows[0]["verdict"], "meets-declared-threshold")
        self.assertIn("the operator's declared threshold", rows[0]["verdict_reason"])
        rows = wf.compare_conditional_recovery([base, repair], baseline_arm="A", threshold=0.9)
        self.assertEqual(rows[0]["verdict"], "below-declared-threshold")

    def test_a_comparison_over_an_unresolved_arm_has_no_delta_at_all(self):
        spec = _spec()
        base = wf.arm_accounting(spec["content"]["arms"][0], [_record("i0", True)])
        censored = wf.arm_accounting(spec["content"]["arms"][1], [_record("i0", None)])
        rows = wf.compare_conditional_recovery([base, censored], baseline_arm="A", threshold=0.1)
        self.assertIsNone(rows[0]["delta"])
        self.assertIsNone(rows[0]["verdict"])
        self.assertIn("resolved no outcome", rows[0]["verdict_reason"])

    # -- recovery and whole-task accounting ------------------------------------------------------

    def test_the_initial_attempt_is_in_the_whole_task_total_and_not_in_recovery_only(self):
        arm = _spec()["content"]["arms"][0]
        totals = wf.arm_accounting(arm, [_record("i0", True, initial=0.40, recovery=(0.10,))])
        self.assertAlmostEqual(totals["scopes"]["recovery-only"]["priced_usd"], 0.10)
        self.assertAlmostEqual(totals["scopes"]["whole-task"]["priced_usd"], 0.50)

    def test_an_analytically_reused_checkpoint_still_carries_its_initial_attempt_cost(self):
        """Reusing a checkpoint does not make the first attempt free."""
        arm = _spec()["content"]["arms"][0]
        fresh = wf.arm_accounting(arm, [_record("i0", True, initial=0.40, reused=False,
                                                recovery=(0.10,))])
        reused = wf.arm_accounting(arm, [_record("i0", True, initial=0.40, reused=True,
                                                 recovery=(0.10,))])
        self.assertEqual(reused["scopes"]["whole-task"]["priced_usd"],
                         fresh["scopes"]["whole-task"]["priced_usd"])
        self.assertAlmostEqual(reused["scopes"]["whole-task"]["priced_usd"], 0.50)
        self.assertEqual(reused["initial_attempt"]["analytically_reused"], 1)
        self.assertEqual(fresh["initial_attempt"]["analytically_reused"], 0)
        self.assertIn("was not free", reused["initial_attempt"]["label"])

    def test_a_record_must_say_whether_the_first_attempt_was_re_run_or_attributed(self):
        arm = _spec()["content"]["arms"][0]
        record = _record("i0", True)
        record.pop("initial_attempt_reused")
        with self.assertRaises(wf.EvalError) as caught:
            wf.arm_accounting(arm, [record])
        self.assertIn("never one it guesses", str(caught.exception))

    def test_a_record_without_its_initial_attempt_cost_is_refused(self):
        arm = _spec()["content"]["arms"][0]
        record = _record("i0", True)
        record.pop("initial_attempt")
        with self.assertRaises(wf.EvalError) as caught:
            wf.arm_accounting(arm, [record])
        self.assertIn("initial_attempt", str(caught.exception))

    def test_failures_stay_in_the_cohort_totals_and_in_the_numerator(self):
        arm = _spec()["content"]["arms"][0]
        totals = wf.arm_accounting(arm, [
            _record("i0", True, initial=0.0, recovery=(1.0,)),
            _record("i1", False, initial=0.0, recovery=(3.0,)),
        ])
        block = totals["scopes"]["recovery-only"]
        self.assertAlmostEqual(block["priced_usd"], 4.0)
        self.assertAlmostEqual(block["cost_per_accepted_usd"], 4.0,
                               msg="the failed item's resources were dropped from the numerator")
        self.assertEqual((totals["accepted"], totals["failed"], totals["items"]), (1, 1, 2))

    def test_cost_per_accepted_task_is_undefined_and_never_zero_with_nothing_accepted(self):
        arm = _spec()["content"]["arms"][0]
        totals = wf.arm_accounting(arm, [_record("i0", False, recovery=(2.0,))])
        for scope in wf.ACCOUNTING_SCOPES:
            block = totals["scopes"][scope]
            self.assertIsNone(block["cost_per_accepted_usd"])
            self.assertIn("undefined", block["undefined_reason"])
            self.assertGreater(block["priced_usd"], 0.0)

    def test_a_censored_outcome_is_counted_apart_and_never_silently_a_failure(self):
        arm = _spec()["content"]["arms"][0]
        totals = wf.arm_accounting(arm, [_record("i0", True), _record("i1", None)])
        self.assertEqual((totals["accepted"], totals["failed"], totals["censored"]), (1, 0, 1))
        self.assertEqual(totals["conditional_recovery"]["n"], 1)
        self.assertEqual(totals["conditional_recovery"]["rate"], 1.0)
        self.assertEqual(totals["conditional_recovery"]["censored"], 1)
        self.assertEqual(totals["items"], 2, "the censored item is still in the cohort")

    def test_an_absent_accepted_key_is_refused_rather_than_read_as_a_failure(self):
        arm = _spec()["content"]["arms"][0]
        record = _record("i0", True)
        record.pop("accepted")
        with self.assertRaises(wf.EvalError) as caught:
            wf.arm_accounting(arm, [record])
        self.assertIn("absent key is not a failure", str(caught.exception))

    def test_overhead_lands_at_the_scope_it_declares(self):
        arm = _spec()["content"]["arms"][0]
        totals = wf.arm_accounting(arm, [_record(
            "i0", True, initial=0.0,
            overhead=(("retrieval", "recovery-only", 0.05), ("planning", "whole-task", 0.30)))])
        self.assertAlmostEqual(totals["scopes"]["recovery-only"]["priced_usd"], 0.05)
        self.assertAlmostEqual(totals["scopes"]["whole-task"]["priced_usd"], 0.35)

    def test_an_unattributed_or_unknown_overhead_cost_is_refused(self):
        arm = _spec()["content"]["arms"][0]
        for kind, scope in (("retrieval", "somewhere"), ("bribery", "whole-task")):
            with self.subTest(kind=kind, scope=scope), self.assertRaises(wf.EvalError):
                wf.arm_accounting(arm, [_record("i0", True, overhead=((kind, scope, 0.1),))])

    def test_a_cost_without_a_basis_is_refused_everywhere_it_can_appear(self):
        arm = _spec()["content"]["arms"][0]
        record = _record("i0", True)
        record["recovery_costs"] = [{"usd": 1.0}]
        with self.assertRaises(wf.EvalError) as caught:
            wf.arm_accounting(arm, [record])
        self.assertIn("basis", str(caught.exception))

    def test_bases_are_kept_apart_and_a_proxy_never_enters_a_priced_total(self):
        arm = _spec()["content"]["arms"][0]
        record = _record("i0", True, initial=0.0)
        record["recovery_costs"] = [{"basis": "proxy", "api_equivalent_usd": 9.0},
                                    {"basis": "unpriced"},
                                    {"basis": "estimated", "usd": 0.25}]
        totals = wf.arm_accounting(arm, [record])
        block = totals["scopes"]["recovery-only"]
        self.assertAlmostEqual(block["priced_usd"], 0.25)
        self.assertEqual(block["totals"]["proxy"]["n"], 1)
        self.assertEqual(block["totals"]["unpriced"]["n"], 1)
        self.assertAlmostEqual(block["totals"]["proxy"]["api_equivalent_usd"], 9.0)
        self.assertIn("never summed", block["totals"]["note"])

    def test_conditional_recovery_carries_an_interval_and_its_own_caveat(self):
        arm = _spec()["content"]["arms"][0]
        totals = wf.arm_accounting(arm, [_record("i0", True), _record("i1", False)])
        rate = totals["conditional_recovery"]
        self.assertEqual((rate["k"], rate["n"]), (1, 2))
        self.assertEqual(rate["ci95"], wf.wilson(1, 2))
        self.assertIn("says nothing about whole-task completion", rate["note"])

    def test_an_empty_cohort_reports_no_rate_rather_than_zero(self):
        arm = _spec()["content"]["arms"][0]
        totals = wf.arm_accounting(arm, [])
        self.assertIsNone(totals["conditional_recovery"]["rate"])
        self.assertIsNone(totals["conditional_recovery"]["ci95"])
        self.assertIn("no outcome was resolved",
                      totals["conditional_recovery"]["undefined_reason"])

    # -- the prospective whole-task study --------------------------------------------------------

    def test_the_whole_task_study_is_prospective_and_the_checkpoint_study_never_satisfies_it(self):
        study = _spec(manifest=_manifest(), certification=_certification(),
                      operator_declarations=_declarations())["content"]["full_task_study"]
        self.assertEqual(study["status"], "prospective")
        self.assertIsNone(study["run"])
        self.assertIs(study["satisfied_by_checkpoint_study"], False)
        self.assertEqual(study["required_before"], "general rollout")
        self.assertIn("conditions on having already failed once", study["note"])

    def test_a_declared_study_run_is_carried_as_a_reference(self):
        spec = _spec(full_task_study_run={"run_id": "2026-01-01-abcd", "results_ref": "sha"})
        study = spec["content"]["full_task_study"]
        self.assertEqual(study["status"], "run")
        self.assertEqual(study["run"], {"run_id": "2026-01-01-abcd", "results_ref": "sha"})
        self.assertNotIn("full-task-study-not-run",
                         {b["blocker"] for b in spec["content"]["blockers"]})

    def test_a_study_run_without_its_results_reference_is_refused(self):
        with self.assertRaises(wf.EvalError):
            _spec(full_task_study_run={"run_id": "r1"})

    # -- repo_bench's extraction and oracles, workflow_eval's envelope ---------------------------

    def test_the_graders_are_repo_benchs_own_four_with_their_own_labels(self):
        rb = wf._rb()
        oracles = {o["oracle"]: o for o in wf.trial_oracles()}
        self.assertEqual(sorted(oracles), ["judge", "resources", "structural", "tests"])
        self.assertEqual(oracles["structural"]["label"], rb.STRUCTURAL_LABEL)
        self.assertEqual(oracles["judge"]["label"], rb.JUDGE_LABEL)
        self.assertEqual(oracles["tests"]["label"], wf.SOLVED_LABEL)
        self.assertEqual([o["objective"] for o in
                          (oracles["tests"], oracles["structural"], oracles["judge"])],
                         [True, False, False],
                         "a judge opinion is not ground truth and a similarity signal is not a "
                         "verdict")

    def test_the_extraction_names_repo_bench_and_this_module_copies_nothing(self):
        extraction = wf.trial_extraction()
        self.assertEqual(extraction["owner"], "repo_bench")
        self.assertEqual(extraction["envelope_writer"], "workflow_eval")
        self.assertIn("make_sandbox", extraction["snapshot"])
        self.assertIn("copies nothing and extracts nothing itself", extraction["note"])

    def test_carrying_a_protocol_writes_only_into_the_envelopes_existing_labels_and_notes(self):
        spec = _spec(manifest=_manifest())
        envelope = {"v": wf.EVAL_VERSION, "labels": ["pre-existing"], "notes": ["pre-existing"]}
        before = sorted(envelope)
        out = wf.carry_trial_protocol(envelope, spec)
        self.assertIs(out, envelope)
        self.assertEqual(sorted(envelope), before, "a new top-level key appeared")
        self.assertEqual(envelope["labels"][0], "pre-existing")
        self.assertEqual(envelope["notes"][0], "pre-existing")
        self.assertIn(spec["id"], envelope["labels"][1])
        self.assertIn("SPECIFICATION only", envelope["labels"][1])

    def test_carrying_a_protocol_into_an_empty_envelope_creates_only_labels_and_notes(self):
        envelope = wf.carry_trial_protocol({}, _spec())
        self.assertEqual(sorted(envelope), ["labels", "notes"])

    def test_the_envelope_note_says_how_many_arms_survived_the_collapse(self):
        envelope = wf.carry_trial_protocol({}, _spec(manifest=_manifest()))
        note = envelope["notes"][0]
        self.assertIn("arms ['A', 'C']", note)
        self.assertIn("nominal ['A', 'B', 'C']", note)
        self.assertIn("1 equivalence(s)", note)

    def test_the_enforcement_disclaimer_reaches_the_envelope_beside_the_counts(self):
        """Phase 2 review, F5: a reader of `results.json` alone saw partition counts with nothing
        saying they are tamper-evident rather than enforced."""
        envelope = wf.carry_trial_protocol({}, _spec(manifest=_manifest()))
        self.assertTrue(any(wf.NOT_ENFORCEMENT_LABEL in n for n in envelope["notes"]))
        summary = wf.manifest_summary(_manifest())
        self.assertEqual(summary["enforcement"], wf.NOT_ENFORCEMENT_LABEL)

    def test_the_protocol_reference_is_an_identity_and_never_the_document(self):
        spec = _spec()
        self.assertEqual(sorted(wf.protocol_ref(spec)), ["id", "sha", "v"])
        self.assertEqual(wf.protocol_ref(spec)["v"], wf.TRIAL_PROTOCOL_VERSION)
        self.assertIsNone(wf.protocol_ref(None))

    def test_the_specification_says_out_loud_that_it_is_not_a_run(self):
        spec = _spec()
        self.assertIn(wf.NOT_A_RUN_LABEL, spec["content"]["labels"])
        self.assertIn("no figure below was measured", wf.NOT_A_RUN_LABEL)
        self.assertIn(wf.NOT_ENFORCEMENT_LABEL, spec["content"]["labels"])

    def test_the_protocol_version_is_its_own_and_is_not_the_envelope_version(self):
        spec = _spec()
        self.assertEqual(spec["v"], wf.TRIAL_PROTOCOL_VERSION)
        self.assertNotEqual(wf.TRIAL_PROTOCOL_VERSION, wf.EVAL_VERSION)
        self.assertNotEqual(wf.TRIAL_PROTOCOL_VERSION, wf.MANIFEST_VERSION)


def _rr_row(**over):
    """A minimal fixture SHAPED like one row of `decision_eval.join()`'s own output -- not built
    through `join_row` (that is D14's own, exhaustively tested machinery in
    `tests/test_decision_eval.py`), but carrying exactly the keys `decision_eval.coverage`,
    `decision_eval.duration_by_basis` and `decision_eval.time_by_basis` read. Every field is
    optional in the real join's own reader (`.get(...) or default`), so a synthetic row that
    supplies only what one test needs is still a faithful fixture, not a shortcut past it.
    """
    base = {
        "v": de.JOIN_VERSION,
        "correlation_id": "corr-1",
        "prediction_at": "2026-01-01T00:00:00+00:00",
        "censoring": [],
        "unresolved": [],
        "features": {"at_prediction": [], "excluded_as_future": [], "unknown_time": []},
        "questions": [],
        "actions": {"alternatives": []},
        "decision": {"record": None},
    }
    base.update(over)
    return base


def _rr_cal_row(outcome, label_value, *, question="q-1@v1", raw=None, calibrated=None,
               abstained=False):
    """A minimal fixture shaped like one row's `questions[]` entry, enough for
    `decision_eval.calibration_report` to score -- not a full D15 fixture, which is
    `tests/test_decision_eval.py`'s own scope."""
    return {
        "v": de.JOIN_VERSION,
        "questions": [{
            "question": question, "outcomes": ["false", "true"],
            "answer": {"outcome": outcome, "abstained": abstained, "raw": raw,
                      "calibrated": calibrated},
            "label": {"status": "resolved", "value": label_value},
        }],
    }


def _rr_declarations(**over):
    decl = {name: f"operator-declared {name}" for name in de.RECOVERY_REPORT_DECLARATIONS}
    decl["independent_label_source"] = "human-adjudication"
    decl["observation_window"] = "2026-02-01T00:00:00+00:00"
    decl.update(over)
    return decl


def _rr_zero_accepted_accounting():
    arm = _spec()["content"]["arms"][0]
    return wf.arm_accounting(arm, [_record("i0", False, recovery=(2.0,))])


def _rr_mixed_basis_accounting():
    arm = _spec()["content"]["arms"][0]
    record = _record("i0", True, initial=0.0)
    record["recovery_costs"] = [{"basis": "proxy", "api_equivalent_usd": 9.0},
                                {"basis": "unpriced"}, {"basis": "estimated", "usd": 0.25}]
    return wf.arm_accounting(arm, [record])


class RecoveryReportTests(unittest.TestCase):
    """decision-improvement D19. `bin/decision_eval.py`'s recovery report: the operator's
    predeclared stop fields, and one document assembled from what D14/D15/D18 already computed
    without recomputing any of it. Every fixture below is synthetic."""

    maxDiff = None

    # -- do not become the second implementation ------------------------------------------------

    def test_stop_field_names_agree_with_workflow_evals_operator_declarations(self):
        """Four of this report's own six stop fields are the SAME concept as four of D18's seven
        `OPERATOR_DECLARATIONS`, deliberately spelled alike rather than reached across the module
        boundary for a function call. If either module renames one without the other, this is
        the test that catches it."""
        shared = set(wf.OPERATOR_DECLARATIONS) & set(de.RECOVERY_REPORT_DECLARATIONS)
        self.assertEqual(shared, {"practical_gain_threshold", "allowed_quality_regression",
                                  "interim_look_rule", "stopping_rule"})
        # And the two that belong to the join layer alone have no counterpart in D18's list.
        self.assertEqual(set(de.RECOVERY_REPORT_DECLARATIONS) - set(wf.OPERATOR_DECLARATIONS),
                         {"independent_label_source", "observation_window"})

    def test_the_shared_and_uncovered_names_exactly_partition_workflow_evals_seven(self):
        """THE F4 FIX. `operator_plan` covers only four of D18's seven `OPERATOR_DECLARATIONS`;
        the other three (`RECOVERY_PLAN_UNCOVERED_DECLARATIONS`) are workflow_eval's own. This
        pins the partition in the direction the shared-names test above does not: the two sets
        together must equal the whole seven, with no name double-counted and none left out. If a
        name is ever added to `workflow_eval.OPERATOR_DECLARATIONS` without a matching update
        here, or moved between "shared" and "uncovered" in only one file, this test catches it.
        """
        shared = set(wf.OPERATOR_DECLARATIONS) & set(de.RECOVERY_REPORT_DECLARATIONS)
        uncovered = set(de.RECOVERY_PLAN_UNCOVERED_DECLARATIONS)
        self.assertEqual(shared & uncovered, set(),
                         "a name is claimed both shared and uncovered")
        self.assertEqual(shared | uncovered, set(wf.OPERATOR_DECLARATIONS),
                         "the shared and uncovered sets no longer partition D18's own seven")
        self.assertEqual(uncovered, {"primary_endpoint", "sample_size", "independent_evaluation"})

    # -- stop fields required --------------------------------------------------------------------

    def test_a_complete_operator_plan_has_no_missing_fields_and_does_not_block(self):
        plan = de.operator_plan(_rr_declarations())
        self.assertEqual(plan["missing"], [])
        self.assertTrue(plan["complete"])
        self.assertEqual(plan["status"], "own-declarations-complete")
        self.assertFalse(plan["blocks_promotion_on_these_fields"])
        self.assertIsNone(plan["note"])

    def test_every_one_of_the_six_stop_fields_is_required_in_isolation(self):
        """Each absence on its own: a field that only ever fails beside another proves nothing
        about itself."""
        for name in de.RECOVERY_REPORT_DECLARATIONS:
            with self.subTest(missing=name):
                declarations = _rr_declarations()
                declarations[name] = None
                plan = de.operator_plan(declarations)
                self.assertEqual(plan["missing"], [name])
                self.assertFalse(plan["complete"])
                self.assertEqual(plan["status"], "own-declarations-incomplete")
                self.assertTrue(plan["blocks_promotion_on_these_fields"])
                self.assertIn("INCOMPLETE", plan["note"])

    def test_a_recovery_report_with_an_incomplete_plan_blocks_promotion(self):
        document = de.join([_rr_row()])
        declarations = _rr_declarations(stopping_rule=None)
        report = de.recovery_report(provenance="synthetic", join_document=document,
                                    operator_declarations=declarations)
        self.assertTrue(report["blocks_promotion_on_these_fields"])
        self.assertEqual(report["operator"]["status"], "own-declarations-incomplete")
        self.assertIn(de.PLAN_INCOMPLETE_NOTE, report["labels"])

    # -- the completeness claim cannot be read as covering the whole live-run precondition set ---

    def test_a_complete_plan_still_names_the_fields_it_does_not_cover(self):
        """THE DEFECT THIS FIXES. A plan reporting `own-declarations-complete` and
        `blocks_promotion_on_these_fields=False` over its own six fields must never be read, on
        its own, as "nothing blocks promotion": `workflow_eval.OPERATOR_DECLARATIONS`'s
        `primary_endpoint` and `sample_size` are required by `workflow_eval.live_requirements`
        and are untouched by this plan entirely."""
        plan = de.operator_plan(_rr_declarations())
        self.assertTrue(plan["complete"])
        self.assertEqual(sorted(plan["not_covered"]["fields"]),
                         sorted(de.RECOVERY_PLAN_UNCOVERED_DECLARATIONS))
        self.assertIn("primary_endpoint", plan["not_covered"]["fields"])
        self.assertIn("sample_size", plan["not_covered"]["fields"])
        self.assertEqual(plan["not_covered"]["owner"], "workflow_eval.live_requirements")
        self.assertEqual(plan["not_covered"]["pairs_with"], "decision_eval.operator_plan")

    def test_the_scope_note_is_always_present_even_on_a_complete_plan(self):
        """The note that rules out "own_declarations_complete means nothing blocks promotion"
        must not be conditioned on `missing` being non-empty -- a caller reading only a
        complete, non-blocking plan needs it exactly as much as one reading an incomplete one."""
        complete_plan = de.operator_plan(_rr_declarations())
        self.assertEqual(complete_plan["scope_note"], de.SCOPE_NOTE)
        incomplete_plan = de.operator_plan(_rr_declarations(stopping_rule=None))
        self.assertEqual(incomplete_plan["scope_note"], de.SCOPE_NOTE)

    def test_the_scope_note_reaches_the_reports_own_labels_regardless_of_completeness(self):
        document = de.join([_rr_row()])
        report = de.recovery_report(provenance="synthetic", join_document=document,
                                    operator_declarations=_rr_declarations())
        self.assertTrue(report["operator"]["complete"])
        self.assertIn(de.SCOPE_NOTE, report["labels"],
                     "a complete plan's report dropped the scope caveat from its own labels")

    def test_independent_label_source_must_be_one_of_the_labels_own_vocabulary(self):
        with self.assertRaises(dc.ContractError):
            de.operator_plan(_rr_declarations(independent_label_source="a-model-graded-itself"))

    def test_observation_window_must_name_an_instant(self):
        with self.assertRaises(dc.ContractError):
            de.operator_plan(_rr_declarations(observation_window="not-a-timestamp"))

    # -- zero ratio undefined ---------------------------------------------------------------------

    def test_cost_per_accepted_is_relayed_as_undefined_never_a_synthesized_zero(self):
        accounting = _rr_zero_accepted_accounting()
        relayed = de.resource_evidence([accounting])
        for scope in wf.ACCOUNTING_SCOPES:
            block = relayed[0]["scopes"][scope]
            self.assertIsNone(block["cost_per_accepted_usd"])
            self.assertIn("undefined", block["undefined_reason"])
            self.assertGreater(block["priced_usd"], 0.0)

    def test_a_forged_zero_accepted_ratio_is_refused_rather_than_relayed(self):
        """THE MUTATION THIS PROVES. Deleting `_assert_zero_ratio_undefined`'s call inside
        `resource_evidence` turns this from a refusal into a silent pass-through of a ratio that
        should never exist -- a forged accounting `workflow_eval.arm_accounting` itself would
        never produce, which is exactly why this module checks rather than trusts it."""
        accounting = _rr_zero_accepted_accounting()
        accounting["scopes"]["recovery-only"]["cost_per_accepted_usd"] = 0.0
        with self.assertRaises(dc.ContractError) as caught:
            de.resource_evidence([accounting])
        self.assertIn("must be undefined", str(caught.exception))

    # -- bases separate ----------------------------------------------------------------------------

    def test_bases_stay_separate_through_the_report(self):
        accounting = _rr_mixed_basis_accounting()
        relayed = de.resource_evidence([accounting])
        block = relayed[0]["scopes"]["recovery-only"]
        self.assertAlmostEqual(block["priced_usd"], 0.25)
        self.assertEqual(block["totals"]["proxy"]["n"], 1)
        self.assertEqual(block["totals"]["unpriced"]["n"], 1)
        self.assertAlmostEqual(block["totals"]["proxy"]["api_equivalent_usd"], 9.0)

    def test_a_forged_priced_proxy_basis_is_refused_rather_than_relayed(self):
        """A subscription-plan proxy dollar smuggled a 'usd' key -- something
        `workflow_eval.add_cost` never produces -- must never be relayed as though it were a
        priced figure."""
        accounting = _rr_mixed_basis_accounting()
        accounting["scopes"]["recovery-only"]["totals"]["proxy"]["usd"] = 9.0
        with self.assertRaises(dc.ContractError) as caught:
            de.resource_evidence([accounting])
        self.assertIn("proxy", str(caught.exception))

    def test_a_forged_missing_basis_is_refused(self):
        accounting = _rr_mixed_basis_accounting()
        del accounting["scopes"]["recovery-only"]["totals"]["unpriced"]
        with self.assertRaises(dc.ContractError) as caught:
            de.resource_evidence([accounting])
        self.assertIn("missing basis", str(caught.exception))

    def test_resource_evidence_refuses_an_accounting_missing_a_required_field(self):
        accounting = _rr_zero_accepted_accounting()
        del accounting["conditional_recovery"]
        with self.assertRaises(dc.ContractError):
            de.resource_evidence([accounting])

    # -- synthetic labeled --------------------------------------------------------------------------

    def test_a_recovery_report_over_synthetic_data_carries_the_synthetic_label(self):
        document = de.join([_rr_row()])
        report = de.recovery_report(provenance="synthetic", join_document=document,
                                    operator_declarations=_rr_declarations())
        self.assertIn(de.SYNTHETIC_LABEL, report["labels"])
        self.assertEqual(report["provenance"], "synthetic")

    def test_a_recovery_report_over_live_data_carries_no_synthetic_label(self):
        document = de.join([_rr_row()])
        report = de.recovery_report(provenance="live", join_document=document,
                                    operator_declarations=_rr_declarations())
        self.assertNotIn(de.SYNTHETIC_LABEL, report["labels"])

    def test_provenance_outside_the_closed_vocabulary_is_refused(self):
        document = de.join([_rr_row()])
        with self.assertRaises(dc.ContractError):
            de.recovery_report(provenance="mostly-real", join_document=document,
                               operator_declarations=_rr_declarations())

    # -- censoring visible --------------------------------------------------------------------------

    def test_censoring_is_visible_in_the_recovery_report(self):
        rows = [_rr_row(censoring=["attempt-open"]), _rr_row(correlation_id="corr-2",
                                                              censoring=["trial-skipped"]),
                _rr_row(correlation_id="corr-3")]
        document = de.join(rows)
        report = de.recovery_report(provenance="synthetic", join_document=document,
                                    operator_declarations=_rr_declarations())
        self.assertEqual(report["censoring"]["attempt-open"], 1)
        self.assertEqual(report["censoring"]["trial-skipped"], 1)
        self.assertEqual(report["censoring"], document["coverage"]["censoring"])

    def test_recovery_report_refuses_a_join_document_from_a_different_version(self):
        forged = {"v": "not-the-join-version", "rows": [], "coverage": {}}
        with self.assertRaises(dc.ContractError):
            de.recovery_report(provenance="synthetic", join_document=forged,
                               operator_declarations=_rr_declarations())

    # -- time, by the clock that measured it -----------------------------------------------------

    def test_time_by_basis_merges_many_rows_without_summing_across_bases(self):
        rows = [
            _rr_row(decision={"record": {"duration": {"basis": "decision-latency",
                                                       "seconds": 0.5, "source": "t"}}}),
            _rr_row(correlation_id="corr-2",
                   features={"at_prediction": [{"duration": {"basis": "process-wall",
                                                             "seconds": 12.0, "source": "t"}}],
                            "excluded_as_future": [], "unknown_time": []}),
        ]
        merged = de.time_by_basis(rows)
        self.assertEqual(len(merged["by_basis"]["decision-latency"]), 1)
        self.assertEqual(len(merged["by_basis"]["process-wall"]), 1)
        self.assertEqual(merged["by_basis"]["decision-latency"][0]["seconds"], 0.5)
        self.assertEqual(merged["note"], de.DURATIONS_SEPARATE)

    # -- subgroup slices ----------------------------------------------------------------------------

    def test_slice_coverage_buckets_by_the_declared_dimension_and_keeps_unassigned(self):
        rows = [_rr_row(correlation_id="corr-1"), _rr_row(correlation_id="corr-2"),
               _rr_row(correlation_id="corr-3")]
        result = de.slice_coverage(
            rows, {"corr-1": "cross-module", "corr-2": "cross-module"}, dimension="failure_class")
        self.assertEqual(sorted(result["slices"]), ["cross-module", "unassigned"])
        self.assertEqual(result["slices"]["cross-module"]["rows"], 2)
        self.assertEqual(result["slices"]["unassigned"]["rows"], 1)

    # -- every candidate tried or rejected, and its exposure -----------------------------------------

    def test_candidate_tally_counts_tried_accepted_rejected_and_exposure(self):
        tally = de.candidate_tally([
            {"id": "c1", "status": "tried", "exposure": 3},
            {"id": "c2", "status": "accepted", "exposure": 1},
            {"id": "c3", "status": "rejected", "exposure": 2},
            {"id": "c4", "status": "rejected", "exposure": None},
        ])
        self.assertEqual(tally["counts"], {"tried": 1, "accepted": 1, "rejected": 2})
        self.assertEqual(tally["total"], 4)
        self.assertEqual(tally["exposure_total"], 6)
        self.assertEqual(tally["exposure_known"], 3)
        self.assertEqual(tally["exposure_unknown"], 1)

    def test_candidate_tally_refuses_a_repeated_candidate_id(self):
        with self.assertRaises(dc.ContractError):
            de.candidate_tally([{"id": "c1", "status": "tried", "exposure": None},
                                {"id": "c1", "status": "rejected", "exposure": None}])

    # -- paired quality regression, judged only against an operator-declared cap --------------------

    def test_quality_regression_reports_no_verdict_without_an_operator_declared_cap(self):
        baseline = de.calibration_report(
            [_rr_cal_row("true", "true"), _rr_cal_row("true", "true")],
            question="q-1@v1", field="raw", min_samples=1)
        candidate = de.calibration_report(
            [_rr_cal_row("true", "true"), _rr_cal_row("true", "false")],
            question="q-1@v1", field="raw", min_samples=1)
        comparison = de.quality_regression(baseline, candidate, allowed_regression=None)
        self.assertIsNone(comparison["verdict"])
        self.assertIn("no operator-declared allowed_quality_regression",
                      comparison["verdict_reason"])
        self.assertAlmostEqual(comparison["delta"], -0.5)

    def test_quality_regression_reports_a_verdict_against_the_declared_cap(self):
        baseline = de.calibration_report(
            [_rr_cal_row("true", "true"), _rr_cal_row("true", "true")],
            question="q-1@v1", field="raw", min_samples=1)
        candidate = de.calibration_report(
            [_rr_cal_row("true", "true"), _rr_cal_row("true", "false")],
            question="q-1@v1", field="raw", min_samples=1)
        within = de.quality_regression(baseline, candidate, allowed_regression=0.6)
        self.assertEqual(within["verdict"], "within-allowed-regression")
        exceeds = de.quality_regression(baseline, candidate, allowed_regression=0.1)
        self.assertEqual(exceeds["verdict"], "regression-exceeds-allowance")

    # -- prospective versus checkpoint claims, and paired arm effects, carried as references ---------

    def test_recovery_report_carries_comparisons_and_full_task_study_as_references(self):
        spec = _spec()
        accepted = [_record(f"i{i}", True, recovery=(0.2,)) for i in range(2)]
        base = wf.arm_accounting(spec["content"]["arms"][0], accepted)
        repair = wf.arm_accounting(spec["content"]["arms"][1], accepted)
        comparisons = wf.compare_conditional_recovery([base, repair], baseline_arm="A",
                                                       threshold=None)
        study = spec["content"]["full_task_study"]
        document = de.join([_rr_row()])
        report = de.recovery_report(provenance="synthetic", join_document=document,
                                    operator_declarations=_rr_declarations(),
                                    comparisons=comparisons, full_task_study=study)
        self.assertEqual(report["comparisons"], comparisons)
        self.assertEqual(report["full_task_study"]["status"], "prospective")
        self.assertIs(report["full_task_study"]["satisfied_by_checkpoint_study"], False)

    def test_recovery_report_refuses_a_full_task_study_with_an_unknown_status(self):
        document = de.join([_rr_row()])
        with self.assertRaises(dc.ContractError):
            de.recovery_report(provenance="synthetic", join_document=document,
                               operator_declarations=_rr_declarations(),
                               full_task_study={"status": "definitely-happened"})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
