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
    controller SIDE BY SIDE, and satisfying one never discharges the other (Phase 2 F4). Nothing
    is wired: `gate_protected_dispatch` applies no confinement and ledgers nothing, so
    `CONFINED_DISPATCH_WIRED` is False and the flag is pinned to the code it describes in both
    directions.

  * THE EVIDENCE IS RE-DERIVED, NOT BELIEVED (Phase 4). `require_runnable` re-hashes the
    DOCUMENT; that left the evidence the document is built from unchecked, and four of the five
    requirement rows were dischargeable by a caller dict nobody consulted. So a manifest whose
    declared and derived digests disagree now yields NO cohort and its own blocker -- asserted
    here as a blocker SET beside an otherwise-satisfiable control, because a new blocker that
    only ever appears beside `confining-dispatch-unwired` proves nothing about itself -- and the
    protected-profile row is `exec_policy.certify_profile`'s verdict over a sentinel REPORT, so
    the reviewer's hand-written `{"certified": True, "required": 7, "satisfied": 7,
    "blocking": []}` satisfies nothing. What is still only a caller's word says so in
    `re_derived_by`, and a test holds every row to declaring which side it is on.

Synthetic throughout: every fixture is built in this file, no temp home or store is created, no
file outside the repository is read, and nothing is installed.
"""

import ast
import importlib.util
import inspect
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF_PATH = ROOT / "bin" / "workflow_eval.py"
WF_SPEC = importlib.util.spec_from_file_location("workflow_eval_trial_protocol", WF_PATH)
wf = importlib.util.module_from_spec(WF_SPEC)
WF_SPEC.loader.exec_module(wf)

#: D07's module, reached through `wf._ep()` on purpose: that is the SAME module object the D18
#: section consults, so a fixture built from `ep.SENTINELS` here is built from the very plan
#: `exec_policy.certify_profile` will check the report against. Loading `bin/exec_policy.py` a
#: second time would give a different module object and a fixture that only looked equivalent.
ep = wf._ep()

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


def _sentinel_report(*, backend="fixture-backend", rows=None, **over):
    """A synthetic sentinel REPORT that `exec_policy.certify_profile` certifies.

    Built from `ep.sentinels_for(backend)` rather than hand-listed, so the plan this fixture
    answers is the plan D07 will ask for. `backend` is a fictional name on purpose: a report that
    named a real backend would look like a claim about this host, and nothing here ran on any
    host. `sentinels_for` selects on the backend string alone, so a fictional one yields every
    backend-agnostic sentinel and the fixture stays identical on every platform.

    Nothing in this file runs a sentinel. `exec_policy.run_sentinels` spawns processes into a
    temporary tree; `exec_policy.certify_profile` is pure over a report dict, and it is the only
    part of D07 anything here touches.
    """
    plan = ep.sentinels_for(backend)
    if rows is None:
        rows = []
        for sentinel in plan:
            denies = sentinel.expect == "deny"
            rows.append({
                "id": sentinel.id, "role": sentinel.role, "expect": sentinel.expect,
                "outcome": "denied" if denies else "allowed", "why": sentinel.why,
                "detail": None, "confinement": backend,
                "control": "succeeded" if denies else "not-run",
                "errno": "EPERM" if denies else None,
                "denial_signal": "EPERM" if denies else None,
                "effect_observed": False,
            })
    report = {
        "version": ep.SENTINEL_VERSION, "profile": "fixture-profile",
        "status": ep.PROFILE_ENFORCED, "mode": "enforced", "backend": backend,
        "platform": "fixture-platform", "reason": None, "missing": [],
        "enforcement_label": ep.NOT_ISOLATION_LABEL,
        "not_proven": list(ep.SENTINEL_NOT_PROVEN),
        "controlled_tree_intact": True, "sentinels": rows,
    }
    report.update(over)
    return report


def _forged_manifest(*, honest=None, resha=False, **content_over):
    """An honest manifest with its content rewritten and its `sha` left as it was.

    This is the reviewer's forgery reduced to its mechanism: the declared digest and the derived
    digest no longer agree, and before this task nothing compared them. `resha=True` recomputes
    the digest over the rewritten content, which is the DIFFERENT attack -- a consistent rewrite,
    which `verify_manifest`'s own docstring says it cannot catch and which this file never claims
    it does.
    """
    forged = json.loads(json.dumps(honest if honest is not None else _manifest()))
    forged["content"].update(content_over)
    if resha:
        forged["sha"] = wf.manifest_digest(forged["content"])
        forged["id"] = forged["sha"][:16]
    return forged


def _declarations(**over):
    decl = {name: f"operator-declared {name}" for name in wf.OPERATOR_DECLARATIONS}
    decl.update(over)
    return decl


def _spec(**over):
    inputs = over.pop("inputs", None) or _inputs()
    kwargs = {
        "inputs": inputs, "arms": over.pop("arms", None) or _arms(inputs),
        "manifest": None, "partition": "promotion", "cohort": None, "sentinel_report": None,
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
                sentinel_report=_sentinel_report(), full_task_study_run=None,
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
        self.assertIsNone(cohort["verified"], "nothing was supplied, so nothing verified or "
                                              "failed to verify; False would say it failed")
        self.assertIsNone(cohort["verification"])
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

    # -- the manifest is re-verified, not taken on the caller's word (Phase 4) --------------------

    def test_a_manifest_that_does_not_match_its_own_digest_yields_no_cohort(self):
        """THE PHASE 4 DEFECT, IN ONE ASSERTION. `trial_cohort` used to report `frozen: True`
        because a `manifest` argument was passed. It now reports what `verify_manifest` found.

        The forgery is the reviewer's, reduced to its mechanism: the content is rewritten and the
        declared `sha` is left where it was, so the declared and derived digests disagree. Before
        this task nothing compared them, and two invented item ids were counted as held-out
        evidence.
        """
        forged = _forged_manifest(partitions={"promotion": ["invented-a", "invented-b"]})
        self.assertNotEqual(forged["sha"], wf.manifest_digest(forged["content"]),
                            "the fixture is not forged, so this test proves nothing")
        cohort = wf.trial_cohort(forged, "promotion", cohort=None)
        self.assertIs(cohort["frozen"], False)
        self.assertIs(cohort["verified"], False)
        self.assertEqual([f["kind"] for f in cohort["verification"]][:1], ["digest"])
        self.assertEqual(cohort["items"], [])
        self.assertEqual(cohort["item_count"], 0)
        self.assertEqual(cohort["groups"], [])
        self.assertEqual(cohort["group_count"], 0)
        self.assertIsNone(cohort["quarantined"])
        self.assertEqual(cohort["verified_by"], "workflow_eval.verify_manifest")

    def test_an_honest_manifest_is_verified_rather_than_merely_present(self):
        """The control on the check above: it is not something that refuses every manifest."""
        cohort = wf.trial_cohort(_manifest(partition_items=3), "promotion", cohort=None)
        self.assertIs(cohort["verified"], True)
        self.assertEqual(cohort["verification"], [])
        self.assertIs(cohort["frozen"], True)
        self.assertEqual(cohort["item_count"], 3)

    def test_the_forged_manifest_blocker_is_reachable_on_its_own(self):
        """ANTI-MASKING. A blocker that only ever appears beside `confining-dispatch-unwired`
        proves nothing about itself, so this asserts the blocker SET over a specification whose
        every other satisfiable precondition IS satisfied. The control beside it is the same
        specification with the honest manifest: exactly one blocker, and it is the one no caller
        can discharge.
        """
        satisfiable = {"sentinel_report": _sentinel_report(),
                       "full_task_study_run": {"run_id": "r1", "results_ref": "sha1"},
                       "operator_declarations": _declarations()}
        honest = _spec(manifest=_manifest(), **satisfiable)
        self.assertEqual({b["blocker"] for b in honest["content"]["blockers"]},
                         {"confining-dispatch-unwired"},
                         "the control is already blocked by something else, so the case below "
                         "could not tell a new blocker from a masked one")
        forged = _spec(manifest=_forged_manifest(
            partitions={"promotion": ["invented-a", "invented-b"]}), **satisfiable)
        self.assertEqual({b["blocker"] for b in forged["content"]["blockers"]},
                         {"manifest-unverified", "confining-dispatch-unwired"})

    def test_a_forged_manifest_is_never_reported_as_an_empty_partition(self):
        """The two facts a reader must be able to tell apart: a manifest that fails its own digest
        and an honest manifest whose partition is empty. One code for both would read a fabricated
        cohort as a thin one."""
        forged = _spec(manifest=_forged_manifest(
            partitions={"promotion": ["invented-a"]}), sentinel_report=_sentinel_report())
        codes = {b["blocker"] for b in forged["content"]["blockers"]}
        self.assertIn("manifest-unverified", codes)
        self.assertNotIn("no-held-out-evidence", codes)
        self.assertNotIn("cohort-not-frozen", codes)
        detail = next(b["detail"] for b in forged["content"]["blockers"]
                      if b["blocker"] == "manifest-unverified")
        self.assertIn("digest", detail)
        self.assertIn("verify_manifest", detail)

        empty = _spec(manifest=_manifest(leak=True), sentinel_report=_sentinel_report())
        empty_codes = {b["blocker"] for b in empty["content"]["blockers"]}
        self.assertIn("no-held-out-evidence", empty_codes)
        self.assertNotIn("manifest-unverified", empty_codes)

    def test_every_finding_verify_manifest_can_return_blocks_not_only_the_digest_one(self):
        """`verify_manifest` returns several kinds. The blocker is `any finding`, not `a digest
        finding`, so a consistently re-hashed manifest whose partitions disagree with its items is
        caught too -- which is the forgery that survives a recomputed digest."""
        resha = _forged_manifest(resha=True,
                                 partitions={"promotion": ["invented-a", "invented-b"]})
        self.assertEqual(resha["sha"], wf.manifest_digest(resha["content"]),
                         "this case is about a CONSISTENT rewrite; a stale sha would be the "
                         "other test")
        kinds = {f["kind"] for f in wf.verify_manifest(resha)}
        self.assertNotIn("digest", kinds)
        self.assertTrue(kinds, "the rewrite left nothing for verify_manifest to find")
        spec = _spec(manifest=resha, sentinel_report=_sentinel_report())
        self.assertIn("manifest-unverified",
                      {b["blocker"] for b in spec["content"]["blockers"]})

    def test_a_manifest_too_malformed_to_verify_is_refused_rather_than_crashing(self):
        """A caller dict that `verify_manifest` cannot even walk gets this module's own refusal.
        `assertIs(type(...))` rules out the `AttributeError` the unguarded call would raise."""
        for why, bad in {"items is a list": {"v": wf.MANIFEST_VERSION, "id": "x", "sha": "y",
                                             "content": {"items": ["not-a-mapping"]}},
                         "content is a list": {"v": wf.MANIFEST_VERSION, "id": "x", "sha": "y",
                                               "content": []},
                         "manifest is a string": "manifest-0001"}.items():
            with self.subTest(why=why):
                with self.assertRaises(wf.EvalError) as caught:
                    wf.trial_cohort(bad, "promotion", cohort=None)
                self.assertIs(type(caught.exception), wf.EvalError)

    # -- D07 required live, paired with D06 (Phase 2 F4) ----------------------------------------

    def test_a_live_run_requires_the_protected_profile_and_the_held_out_cohort_together(self):
        rows = {r["requirement"]: r for r in _spec()["content"]["live_requirements"]}
        self.assertIn("protected-profile-certified", rows)
        self.assertIn("held-out-evidence", rows)
        self.assertEqual(rows["protected-profile-certified"]["pairs_with"], "held-out-evidence")
        self.assertEqual(rows["held-out-evidence"]["pairs_with"], "protected-profile-certified")
        self.assertIn("certify_profile", rows["protected-profile-certified"]["owner"])
        self.assertIn("require_held_out", rows["held-out-evidence"]["owner"])
        self.assertIn("verify_manifest", rows["held-out-evidence"]["owner"])

    def test_every_requirement_row_says_which_function_re_derived_its_verdict(self):
        """Phase 4's rule, made readable rather than asserted in prose: a row that says
        `satisfied` over evidence nothing consulted is a name broader than its check.

        The three rows that ARE re-derived name the function that did it, and the function is
        checked to exist rather than merely to be spelled. The two that cannot be re-derived
        offline carry `None` and say what that means, instead of reading like the other three.
        """
        rows = {r["requirement"]: r for r in _spec()["content"]["live_requirements"]}
        self.assertEqual(len(rows), 5)
        derived = {
            "held-out-evidence": ("workflow_eval", "verify_manifest"),
            "protected-profile-certified": ("exec_policy", "certify_profile"),
            "confining-and-ledgered-dispatch": ("workflow_eval", "CONFINED_DISPATCH_WIRED"),
        }
        for name, (module, attr) in derived.items():
            with self.subTest(requirement=name):
                self.assertEqual(rows[name]["re_derived_by"], f"{module}.{attr}")
                self.assertTrue(hasattr(wf if module == "workflow_eval" else ep, attr),
                                f"{module}.{attr} does not exist, so the row names nothing")
        for name in ("whole-task-study", "operator-declarations"):
            with self.subTest(requirement=name):
                self.assertIsNone(rows[name]["re_derived_by"])
                self.assertIn(wf.UNDERIVED_EVIDENCE_NOTE, rows[name]["note"])
        self.assertEqual(sorted(rows), sorted(set(derived) | {"whole-task-study",
                                                              "operator-declarations"}),
                         "a requirement row was added or renamed without saying whether anything "
                         "re-derives it")

    def test_satisfying_the_profile_alone_never_discharges_the_held_out_requirement(self):
        spec = _spec(manifest=None, sentinel_report=_sentinel_report())
        rows = {r["requirement"]: r for r in spec["content"]["live_requirements"]}
        self.assertTrue(rows["protected-profile-certified"]["satisfied"])
        self.assertFalse(rows["held-out-evidence"]["satisfied"])
        self.assertIn("cohort-not-frozen", {b["blocker"] for b in spec["content"]["blockers"]})

    def test_satisfying_the_cohort_alone_never_discharges_the_profile_requirement(self):
        spec = _spec(manifest=_manifest(), sentinel_report=None)
        rows = {r["requirement"]: r for r in spec["content"]["live_requirements"]}
        self.assertTrue(rows["held-out-evidence"]["satisfied"])
        self.assertFalse(rows["protected-profile-certified"]["satisfied"])
        self.assertIn("protected-profile-uncertified",
                      {b["blocker"] for b in spec["content"]["blockers"]})

    def test_a_hand_written_certification_result_certifies_nothing(self):
        """THE PHASE 4 DEFECT, VERBATIM. This dict is the certification the reviewer handed
        `build_trial_protocol`, and under the old code it discharged D07 outright: the row's
        arithmetic was internally consistent, so the shape check passed, and `exec_policy` was
        never called. It is now fed in where the SENTINEL REPORT goes, and
        `exec_policy.certify_profile` reads it as what it is -- a report with no sentinels in it
        -- and refuses. The boolean the forger wrote is not consulted at any point.
        """
        forged = {"profile": "made-up", "backend": "none", "certified": True, "required": 7,
                  "satisfied": 7, "blocking": []}
        spec = _spec(manifest=_manifest(), sentinel_report=forged,
                     full_task_study_run={"run_id": "r1", "results_ref": "sha1"},
                     operator_declarations=_declarations())
        row = next(r for r in spec["content"]["live_requirements"]
                   if r["requirement"] == "protected-profile-certified")
        self.assertFalse(row["satisfied"])
        self.assertIsNone(row["evidence"])
        self.assertIn("certify_profile refused", row["reason"])
        self.assertEqual({b["blocker"] for b in spec["content"]["blockers"]},
                         {"protected-profile-uncertified", "confining-dispatch-unwired"})

    def test_the_certification_verdict_is_exec_policys_over_the_report_not_the_callers(self):
        """Each case breaks ONE thing D07 checks and nothing else, so each proves that
        `certify_profile` -- not a shape check in this module -- is what looked.

        A `certified: True` planted ON the report is the sharpest of them: the old code read that
        key, this code reads the sentinels underneath it, and the two disagree on purpose.
        """
        backend = "fixture-backend"
        good = _sentinel_report()

        def broken(mutate, **over):
            rows = json.loads(json.dumps(good["sentinels"]))
            mutate(rows)
            return _sentinel_report(rows=rows, **over)

        def _first_denial(rows):
            return next(r for r in rows if r["expect"] == "deny")

        cases = {
            "not enforced": _sentinel_report(status="unavailable", reason="no backend"),
            "controller tree not intact": _sentinel_report(controlled_tree_intact=False),
            "a sentinel missing from the plan": broken(lambda rows: rows.pop(0)),
            "a denial that did not happen": broken(
                lambda rows: _first_denial(rows).update(outcome="allowed")),
            "confined by something else": broken(
                lambda rows: _first_denial(rows).update(confinement="trusted-host")),
            "no control leg to attribute it": broken(
                lambda rows: _first_denial(rows).update(control="not-run")),
            "a non-zero exit read as a denial": broken(
                lambda rows: _first_denial(rows).update(denial_signal="ENOENT")),
            "no sentinels at all": _sentinel_report(rows=[]),
            "no plan for this backend": _sentinel_report(backend=None, rows=[]),
            "certified planted on the report": broken(
                lambda rows: _first_denial(rows).update(outcome="leaked"), certified=True),
        }
        for why, report in cases.items():
            with self.subTest(why=why):
                self.assertFalse(ep.certify_profile(report)["certified"],
                                 "the fixture is not actually broken, so this case proves "
                                 "nothing about what refused it")
                spec = _spec(manifest=_manifest(), sentinel_report=report)
                row = next(r for r in spec["content"]["live_requirements"]
                           if r["requirement"] == "protected-profile-certified")
                self.assertFalse(row["satisfied"])
                self.assertIsNone(row["evidence"])
        control = _spec(manifest=_manifest(), sentinel_report=_sentinel_report(backend=backend))
        row = next(r for r in control["content"]["live_requirements"]
                   if r["requirement"] == "protected-profile-certified")
        self.assertTrue(row["satisfied"],
                        "the unbroken fixture must certify, or every case above passes because "
                        "nothing could ever satisfy this requirement")

    def test_a_report_this_module_cannot_read_is_refused_rather_than_crashing(self):
        """Rubbish shaped vaguely like a report gets this module's own refusal. `certify_profile`
        indexes `row["id"]`, so a sentinel list of strings raises inside D07; the caller still
        sees an `EvalError`-free requirement row with a reason, never a stack trace."""
        for why, report in {"sentinels are strings": _sentinel_report(rows=["not-a-row"]),
                            "sentinels is not a list": _sentinel_report(rows=None,
                                                                       sentinels=7),
                            "empty dict": {}}.items():
            with self.subTest(why=why):
                row = next(r for r in _spec(manifest=_manifest(), sentinel_report=report)
                           ["content"]["live_requirements"]
                           if r["requirement"] == "protected-profile-certified")
                self.assertFalse(row["satisfied"])
                self.assertIsInstance(row["reason"], str)

    def test_a_complete_certification_is_carried_as_a_reference_not_a_report(self):
        spec = _spec(manifest=_manifest(), sentinel_report=_sentinel_report())
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
        spec = _spec(manifest=_manifest(), sentinel_report=_sentinel_report(),
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
        spec = _spec(manifest=_manifest(), sentinel_report=_sentinel_report(),
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
                "manifest": _manifest(), "sentinel_report": _sentinel_report(),
                "full_task_study_run": {"run_id": "r1", "results_ref": "sha1"},
                "operator_declarations": _declarations()},
            "leaking manifest quarantined": {
                "manifest": _manifest(leak=True), "sentinel_report": _sentinel_report()},
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
        spec = _spec(manifest=_manifest(), sentinel_report=_sentinel_report(),
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

    def test_a_content_that_is_not_a_mapping_is_refused_before_it_is_hashed(self):
        """The test above does NOT pin this refusal, which is why it is here. With the
        `content`-is-a-mapping check deleted, `{"content": [], "sha": "0"*64}` still raises
        `EvalError` -- `_canonical([])` serialises fine, the digest simply mismatches, and the
        TAMPERED path catches it for the wrong reason.

        So this pins the refusal two ways. By MESSAGE: a document with no `content` mapping is
        malformed, not forged, and calling it TAMPERED accuses a caller of something it did not
        do. And by the case the digest check cannot reach: a list whose sha is CORRECT walks
        straight past the mismatch and into `content.get("blockers")`, where an unguarded
        `require_runnable` raises `AttributeError` -- not an `EvalError` -- at the caller.
        """
        with self.assertRaises(wf.EvalError) as caught:
            wf.require_runnable({"content": [], "sha": "0" * 64})
        message = str(caught.exception)
        self.assertIn("`content` must be a mapping", message)
        self.assertNotIn("TAMPERED", message)

        honest_digest = wf._sha(wf._canonical([{"blocker": "x"}]))
        with self.assertRaises(wf.EvalError) as caught:
            wf.require_runnable({"content": [{"blocker": "x"}], "sha": honest_digest})
        self.assertIs(type(caught.exception), wf.EvalError)
        self.assertIn("`content` must be a mapping", str(caught.exception))
        self.assertNotIn("TAMPERED", str(caught.exception),
                         "a non-mapping content with a matching digest reached the blocker read")

    def test_an_absent_or_blank_sha_is_malformed_and_never_reported_as_tampering(self):
        """The same omission on the other guard. Deleting the `sha`-is-a-non-empty-string check
        leaves `derived != claimed` true for every non-string, so `EvalError` is still raised --
        and the document is reported as TAMPERED, which says a caller rewrote a specification
        when what it actually did was hand in one with no digest at all. The distinction is the
        whole reason the two refusals are written separately, so it is asserted by message."""
        for why, case in {"absent": {"content": {"blockers": []}},
                          "None": {"content": {}, "sha": None},
                          "blank": {"content": {}, "sha": "   "},
                          "an int": {"content": {}, "sha": 7}}.items():
            with self.subTest(sha=why):
                with self.assertRaises(wf.EvalError) as caught:
                    wf.require_runnable(case)
                message = str(caught.exception)
                self.assertIn("`sha` must be a non-empty string", message)
                self.assertNotIn("TAMPERED", message)

    def test_every_blocker_code_is_in_the_closed_vocabulary(self):
        spec = _spec()
        codes = {b["blocker"] for b in spec["content"]["blockers"]}
        self.assertTrue(codes)
        self.assertEqual(sorted(codes - set(wf.PROTOCOL_BLOCKERS)), [])

    def test_each_blocker_can_be_produced_in_isolation(self):
        """A reason that only ever fires beside another proves nothing about itself."""
        full = {"manifest": _manifest(), "sentinel_report": _sentinel_report(),
                "full_task_study_run": {"run_id": "r1", "results_ref": "sha1"},
                "operator_declarations": _declarations()}
        cases = {
            "cohort-not-frozen": {"manifest": None},
            "manifest-unverified": {"manifest": _forged_manifest(
                partitions={"promotion": ["invented-a"]})},
            "no-held-out-evidence": {"manifest": _manifest(leak=True)},
            "protected-profile-uncertified": {"sentinel_report": None},
            "full-task-study-not-run": {"full_task_study_run": None},
            "operator-declaration-missing": {"operator_declarations": _declarations(
                sample_size=None)},
        }
        self.assertEqual(sorted(set(cases) | {"confining-dispatch-unwired"}),
                         sorted(wf.PROTOCOL_BLOCKERS),
                         "a blocker code exists that no case here produces in isolation, so the "
                         "closed vocabulary is wider than what this test exercises")
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
        study = _spec(manifest=_manifest(), sentinel_report=_sentinel_report(),
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


def _rr_simple_accounting():
    """A WELL-FORMED `wf.arm_accounting` result, built by that function itself over one accepted
    record. Two jobs: it is what the vocabulary pins below read their field names off (an actual
    output, not a second hand-written copy of one), and it is the POSITIVE CONTROL every closure
    refusal below is measured against -- a guard that refused this too would be over-broad and
    would have broken the relay rather than tightened it."""
    arm = _spec()["content"]["arms"][0]
    return wf.arm_accounting(arm, [_record("i0", True, recovery=(0.10,))])


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

    # -- and neither do the three accounting vocabularies ----------------------------------------
    #
    # THE SAME DEFECT ONE LAYER DOWN. `RESOURCE_BASES`, `ACCOUNTING_EVIDENCE_KEYS` and
    # `ACCOUNTING_SCOPE_KEYS` are hand-written tuples in `bin/decision_eval.py` that must agree
    # with `bin/workflow_eval.py`'s own constants and with `arm_accounting`'s actual output. They
    # agreed by coincidence: nothing anywhere pinned them, so a basis or a field added, removed or
    # renamed on the owner's side would have gone on relaying -- silently dropping the new name,
    # in the direction that UNDER-reports resources. These four tests are the template the two
    # tests above already proved out, applied to those three vocabularies: an exact partition or
    # an exact equality against the owner's OWN constant or its OWN output, never a second copy
    # of the names asserted against the first copy of the names.

    def test_the_relayed_cost_bases_are_workflow_evals_own_five_exactly(self):
        """`de.RESOURCE_BASES` mirrors `wf.BASES` on purpose (decision_eval reaches no sibling
        function; see its `_we` docstring). Mirroring is only safe while something holds the two
        equal, and until now nothing did."""
        self.assertEqual(de.RESOURCE_BASES, wf.BASES)
        self.assertEqual(len(set(de.RESOURCE_BASES)), len(de.RESOURCE_BASES),
                         "a basis is listed twice")

    def test_the_bases_and_the_declared_non_bases_exactly_partition_a_real_totals_block(self):
        """The closure guard's own premise. `_assert_bases_kept_apart` now refuses any totals key
        that is neither one of the five bases nor a declared non-basis, which is only correct if
        those two sets together are exactly what `wf.empty_totals()` actually produces -- today
        the five bases plus its own `note`. Asserted against a real block from the owner, in both
        directions, so a sixth basis added there fails HERE rather than at a caller's relay."""
        totals = wf.empty_totals()
        bases, non_bases = set(de.RESOURCE_BASES), set(de.TOTALS_NON_BASIS_KEYS)
        self.assertEqual(non_bases, {"note"})
        self.assertEqual(bases & non_bases, set(), "a name is claimed both basis and non-basis")
        self.assertEqual(bases | non_bases, set(totals),
                         "RESOURCE_BASES + TOTALS_NON_BASIS_KEYS no longer covers a real "
                         "workflow_eval totals block exactly")

    def test_the_accounting_evidence_keys_are_exactly_arm_accountings_own_output_keys(self):
        """Read off the owner's ACTUAL output rather than a constant, because workflow_eval
        declares no constant for this: `arm_accounting`'s return literal IS the authority. Three
        differently-shaped accountings are checked, so the equality is a property of the function
        rather than of one fixture's inputs."""
        for label, accounting in (("accepted", _rr_simple_accounting()),
                                  ("zero-accepted", _rr_zero_accepted_accounting()),
                                  ("mixed-basis", _rr_mixed_basis_accounting())):
            with self.subTest(accounting=label):
                self.assertEqual(set(de.ACCOUNTING_EVIDENCE_KEYS), set(accounting))
        self.assertEqual(len(set(de.ACCOUNTING_EVIDENCE_KEYS)),
                         len(de.ACCOUNTING_EVIDENCE_KEYS), "a field is listed twice")

    def test_the_accounting_scope_keys_are_exactly_arm_accountings_own_scope_block_keys(self):
        accounting = _rr_simple_accounting()
        self.assertEqual(set(accounting["scopes"]), set(wf.ACCOUNTING_SCOPES),
                         "the fixture's scopes are not the owner's own scopes")
        self.assertTrue(accounting["scopes"], "no scope block to check -- this test would be "
                                              "vacuous")
        for name, block in sorted(accounting["scopes"].items()):
            with self.subTest(scope=name):
                self.assertEqual(set(de.ACCOUNTING_SCOPE_KEYS), set(block))
        self.assertEqual(len(set(de.ACCOUNTING_SCOPE_KEYS)), len(de.ACCOUNTING_SCOPE_KEYS),
                         "a field is listed twice")

    # -- stop fields required --------------------------------------------------------------------

    def test_a_complete_operator_plan_has_no_missing_fields_and_does_not_block(self):
        plan = de.operator_plan(_rr_declarations())
        self.assertEqual(plan["missing"], [])
        self.assertTrue(plan["own_declarations_complete"])
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
                self.assertFalse(plan["own_declarations_complete"])
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
        self.assertTrue(plan["own_declarations_complete"])
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
        self.assertTrue(report["operator"]["own_declarations_complete"])
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

    # -- what the relay does not know, it refuses rather than drops ------------------------------
    #
    # THE DEFECT THESE THREE FIX. `resource_evidence` relays by WHITELIST PROJECTION --
    # `{key: _copy(block[key]) for key in ACCOUNTING_SCOPE_KEYS}` and a hand-written literal for
    # the top level. A projection answers "what did I ask for", never "what was I given", so an
    # accounting carrying a field those tuples do not list relayed WITHOUT it and WITHOUT a word,
    # under a `RESOURCE_EVIDENCE_NOTE` that says every figure was carried field for field. The
    # drift direction is silent UNDER-reporting of resources.
    #
    # The third is the one with teeth. `_assert_bases_kept_apart` checked the PRESENCE of the five
    # bases and then swept `('proxy', 'unpriced')` BY NAME for a priced `usd` -- never closure. So
    # an undeclared SIXTH basis carrying a `usd` figure satisfied the presence check, was never
    # reached by the name sweep, and relayed straight through the guard that exists to stop
    # exactly that. A subscription-plan proxy dollar entering a priced total is the specific thing
    # this repo forbids, and an unrecognised basis is the path it would have taken.
    #
    # ANTI-MASKING, in every one of them: the refusal is asserted to carry `unknown-field` and the
    # word `undeclared`, which no other check in `resource_evidence` produces -- the missing-field
    # checks say `is missing`, the mapping check says `must be a mapping`, the priced-proxy check
    # says `carries a priced`, and each is asserted ABSENT. And each test ends by relaying the
    # same accounting with the added name removed, so what refused is the NAME and not the fixture.

    def test_an_undeclared_top_level_field_is_refused_rather_than_silently_dropped(self):
        accounting = _rr_simple_accounting()
        accounting["settled_usd"] = 3.0
        with self.assertRaises(dc.ContractError) as caught:
            de.resource_evidence([accounting])
        message = str(caught.exception)
        self.assertEqual(caught.exception.code, "unknown-field")
        self.assertIn("undeclared field(s)", message)
        self.assertIn("'settled_usd'", message)
        self.assertNotIn("is missing", message)
        self.assertNotIn("must be a mapping", message)
        del accounting["settled_usd"]
        self.assertEqual(de.resource_evidence([accounting])[0]["arm"], accounting["arm"])

    def test_an_undeclared_field_inside_a_scope_block_is_refused_rather_than_dropped(self):
        accounting = _rr_simple_accounting()
        accounting["scopes"]["recovery-only"]["settled_usd"] = 4.0
        with self.assertRaises(dc.ContractError) as caught:
            de.resource_evidence([accounting])
        message = str(caught.exception)
        self.assertEqual(caught.exception.code, "unknown-field")
        self.assertIn("undeclared field(s)", message)
        self.assertIn("'settled_usd'", message)
        self.assertIn("recovery-only", message)
        self.assertNotIn("is missing", message)
        del accounting["scopes"]["recovery-only"]["settled_usd"]
        self.assertIn("recovery-only", de.resource_evidence([accounting])[0]["scopes"])

    def test_an_undeclared_sixth_basis_carrying_usd_is_refused_rather_than_relayed(self):
        """THE ONE THAT MATTERS. Every declared basis is present, so the missing-basis check is
        satisfied; the priced-`usd` sweep only ever looks at `proxy` and `unpriced` by name, so it
        never sees this at all. Before closure this relayed a `usd` figure on a basis nothing in
        either module has ever vouched for."""
        accounting = _rr_simple_accounting()
        totals = accounting["scopes"]["recovery-only"]["totals"]
        self.assertEqual(set(de.RESOURCE_BASES) - set(totals), set(),
                         "the fixture is already missing a basis, so this proves nothing about "
                         "an undeclared sixth one")
        totals["subscription"] = {"n": 1, "usd": 12.5}
        with self.assertRaises(dc.ContractError) as caught:
            de.resource_evidence([accounting])
        message = str(caught.exception)
        self.assertEqual(caught.exception.code, "unknown-field")
        self.assertIn("undeclared basis(es)", message)
        self.assertIn("'subscription'", message)
        self.assertNotIn("missing basis", message)
        self.assertNotIn("carries a priced", message)
        del totals["subscription"]
        self.assertIsNotNone(de.resource_evidence([accounting]))

    def test_the_two_basis_guards_are_distinct_refusals_and_not_one_wearing_two_names(self):
        """A priced `proxy` and an undeclared sixth basis are different defects and must be
        distinguishable in the message, or a test asserting one could be satisfied by the other."""
        priced_proxy = _rr_simple_accounting()
        priced_proxy["scopes"]["recovery-only"]["totals"]["proxy"]["usd"] = 9.0
        with self.assertRaises(dc.ContractError) as proxy_caught:
            de.resource_evidence([priced_proxy])
        self.assertIn("carries a priced", str(proxy_caught.exception))
        self.assertNotIn("undeclared", str(proxy_caught.exception))
        self.assertEqual(proxy_caught.exception.code, "value-invalid")

        sixth = _rr_simple_accounting()
        sixth["scopes"]["recovery-only"]["totals"]["subscription"] = {"n": 1, "usd": 12.5}
        with self.assertRaises(dc.ContractError) as sixth_caught:
            de.resource_evidence([sixth])
        self.assertIn("undeclared basis(es)", str(sixth_caught.exception))
        self.assertEqual(sixth_caught.exception.code, "unknown-field")

    def test_a_well_formed_accounting_still_relays_every_field_it_was_given(self):
        """THE POSITIVE CONTROL for all three closure guards. `RESOURCE_EVIDENCE_NOTE` claims
        every figure is relayed field for field; this is what holds the claim to the whole key
        set of a real `arm_accounting` result rather than to the tuples this module happens to
        know. A guard made over-broad by the three tests above would break the relay here."""
        accounting = _rr_simple_accounting()
        relayed = de.resource_evidence([accounting])[0]
        self.assertEqual(set(relayed), set(accounting),
                         "the relay's own key set no longer matches the accounting it was given")
        for key in sorted(accounting):
            with self.subTest(field=key):
                self.assertEqual(relayed[key], accounting[key])
        for name, block in sorted(accounting["scopes"].items()):
            with self.subTest(scope=name):
                self.assertEqual(set(relayed["scopes"][name]), set(block))
                self.assertEqual(relayed["scopes"][name], block)
                # including the totals block's own non-basis `note`, which is a field like any
                # other and would be the first casualty of a bases-only projection.
                self.assertEqual(relayed["scopes"][name]["totals"]["note"],
                                 block["totals"]["note"])
        # ...and it is a copy, not the caller's own objects handed back.
        relayed["scopes"]["recovery-only"]["totals"]["estimated"]["usd"] = -1.0
        self.assertNotEqual(
            accounting["scopes"]["recovery-only"]["totals"]["estimated"]["usd"], -1.0)

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

    # -- no bare `complete`: the third over-broad name --------------------------------------------

    def test_the_plan_carries_no_bare_complete_key_to_be_misread(self):
        """THE DEFECT THIS FIXES. `operator_plan` renamed two fields so neither could be read as
        ranging over more than its own six declarations, and left a third: a bare `complete`
        sitting beside `status` and `blocks_promotion_on_these_fields`. With all six supplied it
        read True while `primary_endpoint`, `sample_size` and `independent_evaluation` were
        neither declared nor checked -- exactly the reading `SCOPE_NOTE` exists to rule out, and
        `SCOPE_NOTE`'s own prose already calls the field `own_declarations_complete`. The old key
        must be GONE, not shadowed by a second spelling of the same boolean."""
        for declarations in (_rr_declarations(), _rr_declarations(stopping_rule=None)):
            plan = de.operator_plan(declarations)
            with self.subTest(status=plan["status"]):
                self.assertNotIn("complete", plan)
                self.assertIn("own_declarations_complete", plan)
        complete = de.operator_plan(_rr_declarations())
        self.assertTrue(complete["own_declarations_complete"])
        self.assertFalse(de.operator_plan(
            _rr_declarations(stopping_rule=None))["own_declarations_complete"])
        # The payload's own name and the note that bounds it must stay one vocabulary.
        self.assertIn("own_declarations_complete", de.SCOPE_NOTE)
        # And the same boolean inside a report is spelled the same way.
        document = de.join([_rr_row()])
        report = de.recovery_report(provenance="synthetic", join_document=document,
                                    operator_declarations=_rr_declarations())
        self.assertNotIn("complete", report["operator"])
        self.assertTrue(report["operator"]["own_declarations_complete"])

    # -- the causal fence on THIS function, through the routes that can actually carry one --------

    #: The three `recovery_report` arguments copied into the report VERBATIM, keys and all. Each
    #: is the caller's own structure -- D18's protocol block, D18's accounting comparisons, and a
    #: caller-declared subgroup breakdown -- so each is a route by which a causal key can reach a
    #: report that no field of this module's own vocabulary could ever spell.
    CAUSAL_ROUTES = {
        "full_task_study": lambda key: {"status": "prospective", key: "the context package"},
        "comparisons": lambda key: [{"arm": "B", key: "the context package"}],
        "slices": lambda key: {"by_failure_class": {key: "the context package"}},
    }

    def _report_with(self, **over):
        return de.recovery_report(provenance="synthetic", join_document=de.join([_rr_row()]),
                                  operator_declarations=_rr_declarations(), **over)

    def test_a_causal_key_is_refused_through_every_caller_supplied_route(self):
        """THE MUTATION THIS PROVES. `recovery_report`'s closing
        `assert_no_causal_claim(report, where="the recovery report")` was the one call site of
        that sweep nobody pinned -- `join_row`'s and `calibration_report`'s are pinned in
        `tests/test_decision_eval.py` -- and replacing it with `return report` broke nothing,
        because no field this function builds from its own vocabulary can be spelled like
        causation. Three of its arguments are not from its own vocabulary: `full_task_study`,
        `comparisons` and `slices` are copied in verbatim. So a causal key CAN reach a report,
        by each of those three routes, and this function's own return is the only thing that
        refuses it.

        ANTI-MASKING. Each refusal is checked to be that closing sweep and not an earlier type
        check on the same argument: the message names `the recovery report` and carries
        `NO_CAUSAL_CLAIM`, which no other check in this function produces. And the identical
        argument with the causal key removed is asserted to pass all the way through, so the
        refusal is the KEY's doing rather than the route's shape.
        """
        for route, build in sorted(self.CAUSAL_ROUTES.items()):
            for key in ("caused_by", "root_cause"):
                with self.subTest(route=route, key=key):
                    with self.assertRaises(dc.ContractError) as caught:
                        self._report_with(**{route: build(key)})
                    message = str(caught.exception)
                    self.assertIn(f"{key!r}", message)
                    self.assertIn("the recovery report", message)
                    self.assertIn(de.NO_CAUSAL_CLAIM, message)
            with self.subTest(route=route, key="<none>"):
                report = self._report_with(**{route: build("note")})
                self.assertIsNotNone(report[route])

    def test_the_token_list_carries_the_base_forms_and_not_only_the_inflections(self):
        """`_is_causal_key` matches a WHOLE reduced key, never a substring, so `caused` did not
        catch `cause` and `causedby` did not catch `root_cause`. D14's four demonstration
        spellings each happened to contain a listed token, which is why the gap stayed invisible;
        `bin/decision_context.py`'s `DEPENDENCY_TOKENS` carries its base forms for this reason.
        Each spelling below is asserted on its own -- one that only ever fails beside another
        proves nothing about itself."""
        for key in ("cause", "root_cause", "rootcause", "Root-Cause", "led_to", "resulted_in",
                    "triggered_by", "effect_of", "attributable_to", "metrics.cause"):
            with self.subTest(key=key):
                with self.assertRaises(dc.ContractError) as caught:
                    de.assert_no_causal_claim({"recovery": {key: "the context package"}})
                self.assertIn("authority-field", str(caught.exception))
        # And the widened vocabulary reaches the real surface, not just the helper.
        with self.assertRaises(dc.ContractError):
            self._report_with(slices={"by_failure_class": {"root_cause": "flaky-host"}})

    def test_a_causal_word_in_a_value_is_still_allowed(self):
        """THE POSITIVE CONTROL ON THE WIDENING. The sweep refuses KEYS, deliberately: a
        `relation` or `edge_label` whose value is a causal word comes from evidence some other
        tool produced, and refusing it would let a third-party extractor's choice of word break
        an honest report. Widening the key vocabulary must not start failing those."""
        self.assertIsNotNone(de.assert_no_causal_claim(
            {"relation": "caused_by", "edge_label": "cause", "note": "root_cause analysis"}))
        report = self._report_with(
            slices={"relation": "caused_by", "edge_label": "root_cause", "rows": 2})
        self.assertEqual(report["slices"]["relation"], "caused_by")
        # `RELATIONS`, the vocabulary this module does own, still admits no causal word at all.
        for relation in de.RELATIONS:
            self.assertFalse(de._is_causal_key(relation))

    def test_the_module_states_the_sweep_as_a_token_list_and_never_as_a_guarantee(self):
        """SHAPE A AT THE VOCABULARY LAYER. The module docstring used to say categorically that
        a joined row "carries no causal claim" while the check behind it was a list of spellings.
        Widening that list moves the line and never removes it, so the claim -- not only the
        vocabulary -- had to be narrowed. This holds both halves at once: a spelling the list
        does not carry really does pass, and the module says so rather than promising absence."""
        # The limit, demonstrated rather than asserted: these are not caught, today.
        for uncaught in ("causation", "causality", "proximate_cause", "why_it_passed"):
            with self.subTest(uncaught=uncaught):
                self.assertIsNotNone(de.assert_no_causal_claim({uncaught: "x"}))
        self.assertNotIn("carries no causal claim", de.__doc__)
        self.assertIn("CAUSAL_TOKENS", de.__doc__)
        self.assertIn("is NOT caught", de.__doc__)
        self.assertIn("Shape-matching cannot establish absence",
                      de.assert_no_causal_claim.__doc__)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
