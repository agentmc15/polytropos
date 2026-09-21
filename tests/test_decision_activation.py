"""D23 -- the runtime transition that would be taken, and every reason it still refuses.

`ProtectedActivationGateTests` covers the protected-activation section of `bin/workflow_eval.py`,
the pinned-run bundle resolution in `bin/decision_policy.py`, and the driver start seam in
`bin/kit_contract.py`.

WHAT IS ACTUALLY UNDER TEST, in the order the acceptance asks it:

  * EACH MISSING GATE REFUSES. Four gates: the D07 protected profile, the current grouped and
    exposed evaluation manifest, D19's predeclared endpoint/margins/caps/stops, and D22's exact
    approval. Each is reached with the OTHER THREE SATISFIED and what is asserted is the blocker
    SET, so a gate that could only ever fire while another was already firing fails here. The
    positive control is the load-bearing one and it is not "activation happens": it is that all
    four gates pass over synthetic fixtures and the transition STILL refuses, with exactly one
    blocker -- `confining-dispatch-unwired`, which is unconditional because
    `workflow_eval.CONFINED_DISPATCH_WIRED` is False.
  * ABSENT POINTER IS LEGACY. No store, no directory, no generation: legacy, reason `no-pointer`,
    not an error and not a default activation. So is an unreadable generation, a retired one, a
    rolled-back one, one whose gate block contradicts the dispatch constant, and one whose
    declared eligibility a run falls outside.
  * CONCURRENT UPDATE SAFE. The swap is `O_EXCL` through `safe_paths.confined_create_bytes`, so
    "is this generation free" and "write it" are one kernel operation. Proved both sequentially
    (a stale expectation writes nothing) and with real threads (eight racers, exactly one
    winner, the loser's bytes nowhere on disk).
  * RUN PINS. A run takes the pointer ONCE at start; a later generation landing mid-run does not
    reach it. Proved through the real seam -- `kit_contract.start_task_lifecycle(policy_ref=...)`
    into `TaskRun`, with the pin read back off the attempt events the ledger actually wrote.
  * ROLLBACK PRESERVES EVIDENCE AND WORKSPACES. Every generation ever written stays on disk
    byte-identical, the evals store is untouched, a workspace beside it is untouched, and no
    dispatch seam is reached: every one of them is armed with a raiser for the duration.

WHAT A PASSING FIXTURE HERE PROVES, AND WHAT IT DOES NOT. Several tests build a sentinel report
that `exec_policy.certify_profile` certifies, a manifest that verifies against a temporary store,
and a complete set of operator declarations. That proves each gate READS what it claims to read
and that the four are individually reachable. It certifies no host's isolation, no live
deployment and no model's quality -- nothing here ran a sentinel, and `exec_policy.run_sentinels`
is the only thing that could. `fixture-proves-mechanics-not-safety` is that limit as a code on
every record, and a test asserts it is unconditional.

SEVERAL TESTS PATCH `CONFINED_DISPATCH_WIRED` TO TRUE, and that is deliberate: the pointer
mechanics -- minting, swapping, pinning, rolling back -- are unreachable otherwise, and code no
test can reach is code nobody has shown to work. Every such test restores the constant and then
asserts the SAME pointer reads as legacy in the world as it actually is. The patch is also the
proof that the constant is the single load-bearing fact: flip it and the gate opens, which is
exactly where such an edit should have to be visible.

SAFETY CONTRACT. Nothing here invokes a real `claude`/`codex`/`copilot`/`cursor`/`graphify`
binary, reads a real harness home, spends anything or touches a real store. Every prefs
directory, evals store, attempt store, workspace, manifest and envelope is built in a temporary
directory; `POLYTROPOS_DATA_HOME` is redirected for this module's run so even a mistake lands in
a throwaway; and every fixture comes from the generator that owns its shape --
`workflow_eval.build_manifest` for the manifest, `test_workflow_eval.synthetic_envelope` for the
run, D11's own `proposal_payload` and `bundle_payload` for the candidate and the bundle,
`test_decision_trial_protocol._sentinel_report` (built from `exec_policy.sentinels_for`) for the
profile evidence, and `kit_contract._demo_task` for the task.
"""

import ast
import concurrent.futures
import contextlib
import hashlib
import importlib.util
import inspect
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_decision_eval as tde
import test_decision_evaluation_manifest as tem
import test_decision_policy_bundle as tpb
import test_decision_trial_protocol as ttp
import test_workflow_eval as twe

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_activation_test",
                                                  BIN_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


we = _load("workflow_eval")
rg = _load("release_gate")
rt = _load("runtime_data")
rs = _load("routing_scorecard")   # D24's own additive markdown projection over the report
dp = we._dp()                    # the decision_policy instance workflow_eval itself reads
de = we._de()                    # ... and the decision_eval instance its declaration gate reads
kc = we._kc()
al = we._al()
dc = we._dc()
dpc = dp._contract()      # the class decision_policy's own refusals are raised from

SECTION_START = ("# PROTECTED ACTIVATION: THE POINTER, AND WHAT STILL REFUSES TO MINT ONE "
                 "(decision-improvement D23)")
SECTION_END = "# END OF THE PROTECTED ACTIVATION SECTION (decision-improvement D23)"

#: Every function the D23 section is allowed to define. A new one must be added here, which is
#: how a dispatching or extra-writing helper smuggled into the section fails this file rather
#: than sliding past the sweeps below.
SECTION_FUNCTIONS = {
    "manifest_currency", "trial_plan_completeness", "_activation_row", "_relayed_rows",
    "_unwired_dispatch", "activation_decision", "scope_key", "_eligibility", "_monitors",
    "_entry", "activation_entry", "rollback_entry", "retirement_entry", "validate_entry",
    "_generation_name", "_activation_rel", "activation_generations", "read_activation",
    "swap_activation", "activation_history", "_facts", "runtime_activation", "legacy",
    "pin_for_run", "run_pin", "activation_report",
}

#: The ONE function in the section that may write anything. Everything else opens nothing, or
#: opens a file for reading through `safe_paths.confined_read_bytes`.
SECTION_WRITERS = {"swap_activation"}

#: Filesystem and persistence verbs, for the sweep above. `confined_read_bytes` and `iterdir`
#: are deliberately absent: reading a store is not writing one.
WRITER_NAMES = {"write_text", "write_bytes", "mkdir", "unlink", "rmtree", "replace", "touch",
                "write_envelope", "write_manifest", "write_proposal", "write_approval",
                "apply_proposal", "rollback_policy", "record_exposure", "record_results",
                "declare_cohort", "select_cohort", "retire", "adjudicate", "_journal",
                "confined_create_bytes", "confined_append_bytes", "confined_write_bytes",
                "confined_replace", "confined_unlink"}

#: Names that reach a model, a CLI, a grader, a miner or a sandbox. The section may call none of
#: them: an activation decision is taken over documents and a pointer is a file.
DISPATCHING_NAMES = {
    "runner", "default_runner", "gate_protected_dispatch", "require_protected_trial",
    "run_protected_dispatch", "run_confined", "run_verify", "wrap_argv", "dispatch_cell",
    "mine_tasks", "make_sandbox", "prepare_cell_sandbox", "build_grade_substrate",
    "grade_cells", "oracle_tests", "oracle_judge", "oracle_structural", "build_plan",
    "Evaluation", "Popen", "check_output", "call", "system", "popen", "urlopen", "request",
    "run_sentinels", "home", "read_policy", "policy_base",
}

#: Every seam that could reach a model, a CLI, a graded sandbox, a provider -- or a stored record
#: written by somebody else's writer. Armed with a raiser where a test claims nothing is reached.
WF_SEAMS = ("default_runner", "gate_protected_dispatch", "require_protected_trial",
            "write_envelope", "write_manifest", "write_proposal", "write_approval",
            "build_proposal", "review_proposal", "apply_proposal", "rollback_policy",
            "record_exposure", "record_results", "declare_cohort", "select_cohort", "retire",
            "adjudicate", "read_policy")
RB_SEAMS = ("mine_tasks", "make_sandbox", "prepare_cell_sandbox", "build_grade_substrate",
            "grade_cells", "dispatch_cell")

_DATA_HOME = None
_DATA_HOME_PATCH = None


def setUpModule():
    # Patched for THIS module's run only: discovery imports every test module before any runs,
    # so an import-time environment write would leak into every other module.
    global _DATA_HOME, _DATA_HOME_PATCH
    _DATA_HOME = tempfile.TemporaryDirectory(prefix="polytropos-test-data-")
    _DATA_HOME_PATCH = mock.patch.dict(os.environ, {"POLYTROPOS_DATA_HOME": _DATA_HOME.name})
    _DATA_HOME_PATCH.start()


def tearDownModule():
    _DATA_HOME_PATCH.stop()
    _DATA_HOME.cleanup()


class _RaisingSeam:
    """A seam that RAISES if ever invoked. Not a mock returning a canned value: a canned return
    is indistinguishable from a real result that happened to be ignored."""

    def __init__(self, name):
        self.name = name

    def __call__(self, *args, **kwargs):
        raise AssertionError(f"seam {self.name!r} was reached: args={args!r} kwargs={kwargs!r}")


class _ArmedSeams:
    def __init__(self, test):
        self.test = test
        self.saved = []

    def __enter__(self):
        for module, names in ((we, WF_SEAMS), (we._rb(), RB_SEAMS)):
            for name in names:
                if not hasattr(module, name):
                    continue
                self.saved.append((module, name, getattr(module, name)))
                setattr(module, name, _RaisingSeam(f"{module.__name__}.{name}"))
        self.test.assertTrue(self.saved, "no seam was armed; the trap is not set")
        return self

    def __exit__(self, *exc):
        for module, name, original in self.saved:
            setattr(module, name, original)
        return False


def _section_bounds():
    lines = (BIN_DIR / "workflow_eval.py").read_text(encoding="utf-8").splitlines()
    starts = [i + 1 for i, line in enumerate(lines) if line.strip() == SECTION_START]
    ends = [i + 1 for i, line in enumerate(lines) if line.strip() == SECTION_END]
    if len(starts) != 1 or len(ends) != 1:
        raise AssertionError(f"the D23 section banners are not a single pair: {starts} {ends}")
    return starts[0], ends[0], ast.parse("\n".join(lines))


def _section_functions():
    start, end, tree = _section_bounds()
    found = {n.name: n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and start < n.lineno < end}
    if not found:
        raise AssertionError("the D23 section slice contains no function at all")
    return found


def _called_names(node):
    out = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                out.add(child.func.id)
            elif isinstance(child.func, ast.Attribute):
                out.add(child.func.attr)
    return out


def _digest_tree(root):
    """Every file under `root`, by relative path -> sha256. What "preserved" is checked against."""
    out = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_file():
            out[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


class ProtectedActivationGateTests(unittest.TestCase):

    # ---- fixtures, every one of them from the generator that owns its shape ------------------

    N_TASKS = 6

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="polytropos-activation-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.prefs = self.root / "prefs"
        self.store = self.root / "evals"
        self.attempts = self.root / "attempts"
        self.workspace = self.root / "workspace"
        self.workspace.mkdir(parents=True)
        (self.workspace / "kept.txt").write_text("a user's tree, which a rollback never touches\n")

    # -- the documents a decision is taken over -------------------------------------------------

    def tasks(self, n=None):
        """`test_decision_evaluation_manifest`'s own task generator -- `repo_bench`'s pinned
        schema -- with one defect per task so nothing groups and every task is its own item."""
        return [tem.task(f"task-{i}", issue=i + 1,
                         statement=f"defect {i} shows up in the widget",
                         reference_patch=tem.diff(f"src/mod{i}.py", f"    old_{i}()",
                                                  f"    new_{i}()"))
                for i in range(self.N_TASKS if n is None else n)]

    def manifest(self, *, labels=()):
        return we.build_manifest(tem.REPO, tem.BASE, self.tasks(), acceptance=tem.TEST_CMD,
                                 allocation={"promotion": 1}, labels=labels)

    def candidate(self, manifest):
        return tpb.proposal_payload(
            evaluation={"endpoint": "accepted-completion", "partition": "promotion",
                        "manifest_ref": we.manifest_ref(manifest)})

    def envelope(self, **kw):
        kw.setdefault("n_tasks", self.N_TASKS)
        return twe.synthetic_envelope(**kw)

    def declarations(self, **over):
        """Every field BOTH owners require, with values their own validators accept. Built from
        the two vocabularies rather than listed, so a name added to either lands here."""
        names = set(we.OPERATOR_DECLARATIONS) | set(de.RECOVERY_REPORT_DECLARATIONS)
        decl = {name: f"operator-declared {name}" for name in names}
        decl["independent_label_source"] = de.LABEL_SOURCES[0]
        decl["observation_window"] = "2026-09-19T00:00:00+00:00"
        decl.update(over)
        return {k: v for k, v in decl.items() if v is not None}

    def approved(self, manifest=None, *, envelope=None, decision="accept"):
        """A granted D22 approval over a complete evaluation -> `(record, case)`."""
        manifest = manifest or self.manifest()
        case = we.approval_case(candidate=self.candidate(manifest), manifest=manifest,
                                partition="promotion",
                                envelope=self.envelope() if envelope is None else envelope,
                                in_force={}, proposed_by="pat")
        record = we.decide_approval(case, by="alex", scope=dict(case["scope"]),
                                    decision=decision)
        return record, case

    def gate_inputs(self, **over):
        """The clean, all-four-gates-satisfied input set every refusal below deviates from by
        exactly one field.

        Each call gets its OWN evals store, because a deviation that dirties the store would
        otherwise contaminate the next case in the same test -- which is exactly the
        one-gate-fires-only-while-another-does artefact these tests exist to rule out.
        """
        manifest = over.pop("manifest", None) or self.manifest()
        record, case = self.approved(manifest)
        store = self.fresh_store(manifest)
        kw = {"approval": record, "case": case, "target_state": "canary",
              "sentinel_report": ttp._sentinel_report(), "store_dir": store,
              "manifest": manifest, "partition": "promotion",
              "declarations": self.declarations()}
        kw.update(over)
        return kw

    def fresh_store(self, manifest, *, exposed=False):
        """A temporary evals store holding this manifest, optionally already looked at."""
        self._stores = getattr(self, "_stores", 0) + 1
        store = self.root / f"evals-{self._stores}"
        store.mkdir(parents=True)
        we.write_manifest(store, manifest)
        if exposed:
            we.record_exposure(store, manifest, partition="promotion", purpose="inspection",
                               by="a curious human")
        return store

    def decide(self, **over):
        kw = self.gate_inputs(**over)
        approval = kw.pop("approval")
        return we.activation_decision(approval, **kw)

    # -- the pointer ----------------------------------------------------------------------------

    def scope(self):
        return {"project": tpb.PROJECT, "task_classes": [tpb.TASK_CLASS],
                "intended_uses": [tpb.USE]}

    def bundle(self, **over):
        payload = tpb.bundle_payload(**over)
        return payload, dp.bundle_ref(dp._contract().parse_bundle(payload))

    def eligibility(self, **over):
        row = {"task_classes": [tpb.TASK_CLASS], "cohort": [], "max_runs": 3}
        row.update(over)
        return row

    def monitors(self):
        return list(we.ACTIVATION_MONITORS[:3])

    def facts(self, **over):
        row = {"task_class": tpb.TASK_CLASS, "item": None, "runs_so_far": 0}
        row.update(over)
        return row

    @contextlib.contextmanager
    def wired(self):
        """Run this block in the world where a confining, ledgered dispatch path EXISTS.

        The only way to reach the pointer mechanics at all, because nothing mints a running
        entry otherwise -- and, incidentally, the proof that this one constant is what holds the
        gate shut. Every caller of this asserts the same pointer reads as legacy afterwards.
        """
        with mock.patch.object(we, "CONFINED_DISPATCH_WIRED", True):
            yield

    def canary(self, *, bundle_ref=None, eligibility=None, **over):
        """A minted canary entry. Only callable inside `wired()`; `activation_entry` refuses
        otherwise, which is itself one of the tests below."""
        _payload, ref = self.bundle()
        decision = self.decide(**over)
        return we.activation_entry(
            decision, scope=self.scope(), bundle_ref=ref if bundle_ref is None else bundle_ref,
            eligibility=self.eligibility() if eligibility is None else eligibility,
            monitors=self.monitors(), by="alex")

    def runtime(self):
        return dp.runtime_facts(
            project=tpb.PROJECT, task_class=tpb.TASK_CLASS, intended_use=tpb.USE,
            components={"decision_contract": dc.CONTRACT_VERSION,
                        "task_contract": kc.CONTRACT_VERSION, "provider_contract": None})

    def blockers(self, decision):
        return sorted(decision["blockers"])

    # ==========================================================================================
    #  THE POSITIVE CONTROL: ALL FOUR GATES PASS AND IT STILL REFUSES
    # ==========================================================================================

    def test_every_named_gate_is_satisfiable_and_the_transition_still_refuses(self):
        """THE LOAD-BEARING TEST, and its shape is the point. Without it every refusal below
        would be satisfied by a gate that refuses everything; with it, the four named gates are
        shown individually reachable AND the transition is shown to refuse anyway.

        A fixture that makes a gate pass proves the gate reads what it claims to read. It
        certifies no host, no isolation and no model, which is why
        `fixture-proves-mechanics-not-safety` is on the record it produces.
        """
        decision = self.decide()
        rows = {row["requirement"]: row for row in decision["requirements"]}
        for name in ("exact-approval", "protected-profile-certified",
                     "current-evaluation-manifest", "predeclared-trial-plan"):
            with self.subTest(gate=name):
                self.assertTrue(rows[name]["satisfied"],
                                f"{name} could not be satisfied: {rows[name]['reason']}")
        self.assertIs(decision["permitted"], False)
        self.assertEqual(self.blockers(decision), ["confining-dispatch-unwired"])
        self.assertIs(we.CONFINED_DISPATCH_WIRED, False)
        self.assertIs(rows["confining-and-ledgered-dispatch"]["satisfied"], False)
        self.assertEqual(rows["confining-and-ledgered-dispatch"]["re_derived_by"],
                         "workflow_eval.CONFINED_DISPATCH_WIRED")
        self.assertIn("fixture-proves-mechanics-not-safety", decision["unproven"])

    def test_each_of_the_four_gates_refuses_on_its_own_with_the_other_three_satisfied(self):
        """The blocker SET, not that some blocker appeared. Each row deviates from the clean
        control in exactly one way and the assertion is equality, so a gate that could only ever
        fire while another was already firing fails here.

        `confining-dispatch-unwired` is in every expected set because it is unconditional: it is
        not evidence about the deviation, it is the fact that holds whatever else is true.
        """
        exposed = self.manifest()
        rejected, case = self.approved(decision="reject")
        cases = {
            # D22: a refused approval record establishes nothing, however exactly it is bound.
            "exact-approval-missing": {"approval": rejected, "case": case},
            # D07: no sentinel report at all, so certify_profile has nothing to certify.
            "protected-profile-uncertified": {"sentinel_report": None},
            # D06: the document verifies and the STORE says its partition has been looked at.
            "evaluation-manifest-not-current": {
                "manifest": exposed,
                "store_dir": self.fresh_store(exposed, exposed=True)},
            # D19/D18: the one endpoint field D19's own plan does not cover.
            "trial-plan-incomplete": {"declarations": self.declarations(primary_endpoint=None)},
        }
        for blocker, deviation in cases.items():
            with self.subTest(blocker=blocker):
                decision = self.decide(**deviation)
                self.assertEqual(self.blockers(decision),
                                 sorted([blocker, "confining-dispatch-unwired"]))
                self.assertIs(decision["permitted"], False)
                row = next(r for r in decision["requirements"] if r["blocker"] == blocker)
                self.assertTrue(row["reason"], "an unsatisfied row with no reason")

    def test_an_unsatisfied_row_always_names_what_re_derived_it(self):
        """A row that says `satisfied` over evidence nobody consulted is a name broader than its
        check -- Phase 4's finding, and this kit's most-produced defect. Every row on an
        activation verdict names the function behind it, or says `None` where nothing re-derived
        one."""
        decision = self.decide()
        for row in decision["requirements"]:
            with self.subTest(requirement=row["requirement"]):
                self.assertIn("re_derived_by", row)
                if row["re_derived_by"] is not None:
                    self.assertTrue(str(row["re_derived_by"]).strip())
                if not row["satisfied"]:
                    self.assertTrue(row["reason"])
                    self.assertIn(row["blocker"], (
                        list(we.ACTIVATION_BLOCKERS) + ["confining-dispatch-unwired",
                                                        "protected-profile-uncertified",
                                                        "exact-approval-missing"]))

    # ==========================================================================================
    #  THE TWO GATES THIS SECTION DECIDES, AND WHY EACH IS TWO CHECKS
    # ==========================================================================================

    def test_the_manifest_gate_asks_both_the_document_and_the_store(self):
        """`MANIFEST_VERIFICATION_NOTE` has said since D18 that verifying a manifest is not the
        same as its partition still being unspent. Both halves are reachable on their own, and
        a store nobody supplied FAILS rather than being skipped."""
        honest = self.manifest()
        self.store.mkdir(parents=True, exist_ok=True)
        we.write_manifest(self.store, honest)
        clean = we.manifest_currency(self.store, honest, "promotion")
        self.assertTrue(clean["satisfied"], clean["reason"])
        self.assertEqual(clean["evidence"]["held_out"], self.N_TASKS)

        forged = json.loads(json.dumps(honest))
        forged["content"]["labels"] = ["rewritten after it was filed"]
        document_half = we.manifest_currency(self.store, forged, "promotion")
        self.assertFalse(document_half["satisfied"])
        self.assertIn("verify_manifest", document_half["reason"])

        we.record_exposure(self.store, honest, partition="promotion", purpose="inspection",
                           by="a curious human")
        store_half = we.manifest_currency(self.store, honest, "promotion")
        self.assertFalse(store_half["satisfied"])
        self.assertIn("require_held_out", store_half["reason"])

        unchecked = we.manifest_currency(None, honest, "promotion")
        self.assertFalse(unchecked["satisfied"])
        self.assertIn("unmade check is not a passed one", unchecked["reason"])

        absent = we.manifest_currency(self.store, None, "promotion")
        self.assertFalse(absent["satisfied"])
        self.assertIsNone(absent["evidence"]["manifest"])

    def test_the_manifest_gate_is_its_owners_verdict_and_not_a_second_opinion(self):
        """Proved by PATCHING each owner and watching the row follow it, so a second
        implementation of either check inside this section would fail here."""
        honest = self.manifest()
        self.store.mkdir(parents=True, exist_ok=True)
        we.write_manifest(self.store, honest)
        finding = [{"kind": "group-split", "detail": "patched"}]
        with mock.patch.object(we, "verify_manifest", return_value=finding) as patched:
            row = we.manifest_currency(self.store, honest, "promotion")
        self.assertTrue(patched.called, "the document half never asked verify_manifest")
        self.assertFalse(row["satisfied"])
        self.assertIn("group-split", row["reason"])
        with mock.patch.object(we, "require_held_out",
                               side_effect=we.EvalError("patched store refusal")) as patched:
            row = we.manifest_currency(self.store, honest, "promotion")
        self.assertTrue(patched.called, "the store half never asked require_held_out")
        self.assertFalse(row["satisfied"])
        self.assertIn("patched store refusal", row["reason"])

    def test_the_trial_plan_gate_is_the_union_of_two_owners_neither_of_which_covers_it(self):
        """D19's `operator_plan` covers six fields and says so; D18's `OPERATOR_DECLARATIONS`
        names seven; three of D18's are outside D19's plan entirely. Two halves, each phrased as
        though it were the whole -- Phase 2's F4 shape. The gate requires the UNION, which is
        what makes it stronger than either half.

        The proof that it is stronger: a declaration set that satisfies D19's plan COMPLETELY is
        still refused for each of the three fields D19's plan never looks at.
        """
        row = we.trial_plan_completeness(self.declarations())
        self.assertTrue(row["satisfied"], row["reason"])
        required = set(row["evidence"]["required"])
        self.assertEqual(required,
                         set(we.OPERATOR_DECLARATIONS) | set(de.RECOVERY_REPORT_DECLARATIONS))
        self.assertTrue(required - set(de.RECOVERY_REPORT_DECLARATIONS),
                        "D19's plan already covers everything; this gate composes nothing")
        for uncovered in de.RECOVERY_PLAN_UNCOVERED_DECLARATIONS:
            with self.subTest(uncovered=uncovered):
                thin = self.declarations(**{uncovered: None})
                # D19's own plan is COMPLETE over this input -- it never looks at this field.
                self.assertTrue(de.operator_plan(thin)["own_declarations_complete"])
                refused = we.trial_plan_completeness(thin)
                self.assertFalse(refused["satisfied"])
                self.assertEqual(refused["evidence"]["missing"], [uncovered])
                self.assertEqual(refused["blocker"], "trial-plan-incomplete")

    def test_the_trial_plan_gate_runs_the_owners_own_validator(self):
        """The other direction: a declaration set complete over the union, with a value only
        `decision_eval.operator_plan` knows is wrong. A gate that merely counted present keys
        would pass this."""
        bogus = self.declarations(independent_label_source="a source nobody defined")
        self.assertEqual(set(bogus), set(we.OPERATOR_DECLARATIONS)
                         | set(de.RECOVERY_REPORT_DECLARATIONS))
        row = we.trial_plan_completeness(bogus)
        self.assertFalse(row["satisfied"])
        self.assertIn("operator_plan refused", row["reason"])
        self.assertEqual(row["evidence"]["missing"], [])

    def test_both_declaration_vocabularies_are_read_from_their_owners_at_call_time(self):
        """A mutant that replaced either tuple with a literal copy of today's names would pass
        every test above and fail this one: the owner is patched and the required set follows."""
        # Built BEFORE the patch: this is a declaration set complete over today's two
        # vocabularies, handed to a gate whose owners have since grown a field.
        today = self.declarations()
        with mock.patch.object(de, "RECOVERY_REPORT_DECLARATIONS",
                               tuple(de.RECOVERY_REPORT_DECLARATIONS) + ("a_field_d19_added",)):
            row = we.trial_plan_completeness(today)
        self.assertFalse(row["satisfied"], "a field D19 added was not required")
        self.assertIn("a_field_d19_added", row["evidence"]["required"])
        self.assertEqual(row["evidence"]["missing"], ["a_field_d19_added"])
        with mock.patch.object(we, "OPERATOR_DECLARATIONS",
                               tuple(we.OPERATOR_DECLARATIONS) + ("a_field_d18_added",)):
            row = we.trial_plan_completeness(today)
        self.assertFalse(row["satisfied"], "a field D18 added was not required")
        self.assertIn("a_field_d18_added", row["evidence"]["required"])

    # ==========================================================================================
    #  THE RELAY: D22's ROWS, WHOLE, OR NOT AT ALL
    # ==========================================================================================

    def test_the_gate_relays_promotion_eligibilitys_rows_and_never_re_decides_them(self):
        """Activation is a SUPERSET of promotion eligibility and can never be laxer than it: the
        three rows D22 decides arrive here decided, tagged with where they came from."""
        record, case = self.approved()
        verdict = we.promotion_eligibility(record, case=case,
                                           sentinel_report=ttp._sentinel_report())
        decision = self.decide()
        relayed = {row["requirement"]: row for row in decision["requirements"]
                   if row["relayed_from"]}
        self.assertEqual(sorted(relayed),
                         sorted(row["requirement"] for row in verdict["requirements"]))
        for name, row in relayed.items():
            with self.subTest(requirement=name):
                self.assertEqual(row["relayed_from"], "workflow_eval.promotion_eligibility")
                self.assertNotIn(name, we.ACTIVATION_OWN_REQUIREMENTS)
        self.assertEqual(decision["promotion_eligible"], verdict["eligible"])

    def test_a_requirement_added_upstream_is_conjoined_rather_than_ignored(self):
        """The direction that matters for a gate: a precondition added by whoever owns
        `promotion_eligibility` fails closed here automatically, the way
        `decision_policy.denial_reasons` derives its hard filters by subtraction."""
        inputs = self.gate_inputs()
        approval = inputs.pop("approval")
        real = we.promotion_eligibility(approval, case=inputs["case"],
                                        sentinel_report=inputs["sentinel_report"])
        extra = dict(real)
        extra["requirements"] = list(real["requirements"]) + [
            {"requirement": "something-a-later-task-added", "satisfied": False,
             "reason": "added upstream", "blocker": "a-new-blocker",
             "re_derived_by": "somewhere else"}]
        with mock.patch.object(we, "promotion_eligibility", return_value=extra):
            decision = we.activation_decision(approval, **inputs)
        self.assertIn("a-new-blocker", decision["blockers"])
        self.assertIs(decision["permitted"], False)

    def test_a_relayed_row_that_cannot_be_read_whole_is_refused_never_trimmed(self):
        """`read_ref` drops an unknown key and D20's relay refuses one, for the reason that
        applies here too: a verdict that claimed to carry a requirement whose verdict it never
        read would be worse than no verdict."""
        inputs = self.gate_inputs()
        approval = inputs.pop("approval")
        real = we.promotion_eligibility(approval, case=inputs["case"],
                                        sentinel_report=inputs["sentinel_report"])
        broken = {
            "a row missing its verdict": [
                {k: v for k, v in real["requirements"][0].items() if k != "satisfied"}],
            "a row colliding with a local requirement": list(real["requirements"]) + [
                {"requirement": we.ACTIVATION_OWN_REQUIREMENTS[0], "satisfied": True,
                 "reason": None, "blocker": None, "re_derived_by": "somebody else"}],
            "no rows at all": [],
        }
        for label, rows in broken.items():
            with self.subTest(case=label):
                with mock.patch.object(we, "promotion_eligibility",
                                       return_value=dict(real, requirements=rows)):
                    with self.assertRaises(we.EvalError):
                        we.activation_decision(approval, **inputs)

    # ==========================================================================================
    #  NOTHING MINTS A POINTER WHILE THE DISPATCH IS UNWIRED
    # ==========================================================================================

    def test_no_argument_gets_a_pointer_past_the_gate_today(self):
        """`activation_entry` is the one place a running pointer is made and there is no keyword
        through which a caller can assert permission. A hand-built verdict claiming
        `permitted: True` is refused too, because `_unwired_dispatch` re-reads the constant."""
        _payload, ref = self.bundle()
        refused = self.decide()
        with self.assertRaises(we.EvalError) as raised:
            we.activation_entry(refused, scope=self.scope(), bundle_ref=ref,
                                eligibility=self.eligibility(), monitors=self.monitors(),
                                by="alex")
        self.assertIn("confining-dispatch-unwired", str(raised.exception))
        forged = dict(refused, permitted=True, blockers=[])
        with self.assertRaises(we.EvalError) as raised:
            we.activation_entry(forged, scope=self.scope(), bundle_ref=ref,
                                eligibility=self.eligibility(), monitors=self.monitors(),
                                by="alex")
        self.assertIn("CONFINED_DISPATCH_WIRED is False", str(raised.exception))
        self.assertEqual(we.activation_generations(self.prefs, self.scope()), ([], []))

    def test_a_hand_written_running_pointer_is_refused_by_the_writer(self):
        """The writer re-derives the one row it can. A `canary` entry whose stored gate block
        claims a permitted verdict is refused by `swap_activation` before a file exists."""
        with self.wired():
            entry = self.canary()
        with self.assertRaises(we.EvalError) as raised:
            we.swap_activation(self.prefs, self.scope(), entry=entry, expected=None)
        self.assertIn("CONFINED_DISPATCH_WIRED is False", str(raised.exception))
        self.assertEqual(we.activation_generations(self.prefs, self.scope()), ([], []))

    def test_a_running_pointer_written_in_another_world_reads_as_legacy_in_this_one(self):
        """And the reader re-derives it too. The entry is minted and stored under the patch;
        outside the patch the same bytes resolve every run to legacy, naming the dispatch fact
        rather than pretending the file is corrupt."""
        with self.wired():
            we.swap_activation(self.prefs, self.scope(), entry=self.canary(), expected=None)
            hot = we.runtime_activation(self.prefs, self.scope(), facts=self.facts())
            self.assertEqual(hot["mode"], "canary")
            self.assertEqual(hot["reasons"], ["pinned"])
        cold = we.runtime_activation(self.prefs, self.scope(), facts=self.facts())
        self.assertEqual(cold["mode"], "legacy")
        self.assertEqual(cold["reasons"], ["confining-dispatch-unwired"])
        self.assertIsNone(cold["pin"])
        # Read perfectly well, and refused for what it says rather than for being unreadable.
        reading = we.read_activation(self.prefs, self.scope())
        self.assertIsNone(reading["unreadable"])
        self.assertEqual(reading["entry"]["state"], "canary")
        row = we.activation_report(self.prefs)["scopes"][0]
        self.assertIn("CONFINED_DISPATCH_WIRED is False", row["dispatch_contradiction"])

    def test_retiring_and_rolling_back_need_no_gate_because_moving_away_never_does(self):
        """Refusing a rollback because some evidence went stale is how a bad activation gets
        stuck in place. Both of these mint and store with the constant exactly as it is."""
        for build in (
                lambda: we.retirement_entry(scope=self.scope(), by="sam", reason="done"),
                lambda: we.rollback_entry(scope=self.scope(), by="sam", reason="regressed",
                                          resolution=dp.resolve_bundle(None, [],
                                                                       self.runtime()))):
            with self.subTest(entry=build().get("state")):
                prefs = self.root / f"prefs-{build()['state']}"
                written = we.swap_activation(prefs, self.scope(), entry=build(), expected=None)
                self.assertIn(written["state"], ("retired", "rolled-back"))
                self.assertIsNone(written["gate"])
                self.assertIsNone(written["bundle_ref"])

    # ==========================================================================================
    #  ABSENT POINTER IS LEGACY
    # ==========================================================================================

    def test_absent_pointer_is_legacy_and_is_not_an_error(self):
        """No store, no directory, no generation. Three different absences, one answer, and none
        of them raises or defaults to an activation."""
        missing = self.root / "never-created"
        for label, prefs in (("no prefs directory at all", missing),
                             ("a prefs directory with nothing in it", self.prefs)):
            with self.subTest(case=label):
                self.prefs.mkdir(parents=True, exist_ok=True)
                answer = we.runtime_activation(prefs, self.scope(), facts=self.facts())
                self.assertEqual(answer["mode"], "legacy")
                self.assertEqual(answer["reasons"], ["no-pointer"])
                self.assertIsNone(answer["pin"])
                self.assertIsNone(answer["generation"])
                self.assertIsNone(we.run_pin(answer))
                self.assertIsNone(we.pin_for_run(answer))
        self.assertIn(we.ABSENT_POINTER_IS_LEGACY_LABEL,
                      we.runtime_activation(missing, self.scope())["labels"])

    def test_every_way_a_pointer_fails_to_resolve_ends_at_legacy_with_its_own_reason(self):
        """`RUNTIME_REASONS` is closed and all but `pinned` end at legacy. Each is reached on
        its own; the assertion is the reason LIST, so a branch that could only fire while
        another was already firing fails here."""
        scope = self.scope()
        # Unreadable: the latest generation is not JSON at all.
        broken = self.root / "prefs-unreadable"
        root = broken / we.POLICY_ACTIVATION / we.scope_key(scope)
        root.mkdir(parents=True)
        (root / "gen-000001.json").write_text("{not json")
        (root / "a-stray-file.txt").write_text("somebody's note")

        # Reachable in the world AS IT IS -- no patch, and `confining-dispatch-unwired` is the
        # one that fires over a perfectly readable canary entry.
        cold = {"no-pointer": (self.root / "prefs-never-written", self.facts()),
                "pointer-unreadable": (broken, self.facts())}
        with self.wired():
            for state, builder in (
                    ("pointer-retired",
                     lambda: we.retirement_entry(scope=scope, by="sam", reason="done")),
                    ("pointer-rolled-back",
                     lambda: we.rollback_entry(scope=scope, by="sam", reason="regressed",
                                               resolution=dp.resolve_bundle(None, [],
                                                                            self.runtime()))),
                    ("confining-dispatch-unwired", self.canary)):
                prefs = self.root / f"prefs-{state}"
                we.swap_activation(prefs, scope, entry=builder(), expected=None)
                cold[state] = (prefs, self.facts())

            # Reachable ONLY where the dispatch is wired, because the unwired row fires first
            # otherwise -- which is itself the point of the row above.
            hot = {}
            for reason, facts in (
                    ("eligibility-unestablished", None),
                    ("outside-eligible-cohort", self.facts(task_class="some-other-class")),
                    ("eligibility-limit-reached", self.facts(runs_so_far=3))):
                prefs = self.root / f"prefs-{reason}"
                we.swap_activation(prefs, scope, entry=self.canary(), expected=None)
                hot[reason] = (prefs, facts)
            pinned = self.root / "prefs-pinned"
            we.swap_activation(pinned, scope, entry=self.canary(), expected=None)
            hot["pinned"] = (pinned, self.facts())
            for reason, (prefs, facts) in hot.items():
                with self.subTest(reason=reason, world="dispatch wired"):
                    answer = we.runtime_activation(prefs, scope, facts=facts)
                    self.assertEqual(answer["reasons"], [reason])
                    self.assertEqual(answer["mode"],
                                     "canary" if reason == "pinned" else "legacy")

        self.assertEqual(sorted(set(cold) | set(hot)), sorted(we.RUNTIME_REASONS),
                         "every reason in the closed vocabulary is exercised, and only those")
        self.assertEqual(set(cold) & set(hot), set())
        for reason, (prefs, facts) in cold.items():
            with self.subTest(reason=reason, world="as it is"):
                answer = we.runtime_activation(prefs, scope, facts=facts)
                self.assertEqual(answer["reasons"], [reason])
                self.assertEqual(answer["mode"], "legacy")
                self.assertIsNone(answer["pin"])
        # And every one of the wired-only reasons collapses to the unwired row out here, which is
        # the property that matters most: an eligible canary is still legacy today.
        for reason, (prefs, facts) in hot.items():
            with self.subTest(reason=reason, world="as it is"):
                answer = we.runtime_activation(prefs, scope, facts=facts)
                self.assertEqual(answer["mode"], "legacy")
                self.assertEqual(answer["reasons"], ["confining-dispatch-unwired"])

    def test_a_stray_file_beside_the_generations_is_reported_and_never_read_as_one(self):
        with self.wired():
            we.swap_activation(self.prefs, self.scope(), entry=self.canary(), expected=None)
        root = self.prefs / we.POLICY_ACTIVATION / we.scope_key(self.scope())
        (root / "gen-000002.json.tmp").write_text("half a write")
        numbers, strays = we.activation_generations(self.prefs, self.scope())
        self.assertEqual(numbers, [1])
        self.assertEqual(strays, ["gen-000002.json.tmp"])
        self.assertEqual(we.activation_report(self.prefs)["scopes"][0]["strays"],
                         ["gen-000002.json.tmp"])

    # ==========================================================================================
    #  CONCURRENT UPDATE SAFE
    # ==========================================================================================

    def test_a_swap_from_a_stale_generation_writes_nothing(self):
        """The generation you read is the generation you may extend. A caller holding an older
        one loses on the kernel's own answer -- the name it would write is taken -- and nothing
        of its content reaches disk."""
        scope = self.scope()
        with self.wired():
            first = self.canary()
            second = we.retirement_entry(scope=scope, by="sam", reason="ended")
            we.swap_activation(self.prefs, scope, entry=first, expected=None)
            we.swap_activation(self.prefs, scope, entry=second, expected=1)
            before = _digest_tree(self.prefs / we.POLICY_ACTIVATION)
            stale = we.retirement_entry(scope=scope, by="lost", reason="a stale writer")
            with self.assertRaises(we.ActivationConflict) as raised:
                we.swap_activation(self.prefs, scope, entry=stale, expected=1)
        self.assertIn("Nothing was written", str(raised.exception))
        self.assertEqual(_digest_tree(self.prefs / we.POLICY_ACTIVATION), before)
        self.assertEqual([row["by"] for row in
                          we.activation_history(self.prefs, scope)["generations"]],
                         ["alex", "sam"], "the stale writer reached the history")
        self.assertEqual(we.activation_generations(self.prefs, scope)[0], [1, 2])

    def test_a_first_write_races_for_generation_one_and_only_one_wins(self):
        scope = self.scope()
        with self.wired():
            we.swap_activation(self.prefs, scope, entry=self.canary(), expected=None)
            with self.assertRaises(we.ActivationConflict):
                we.swap_activation(self.prefs, scope,
                                   entry=we.retirement_entry(scope=scope, by="second",
                                                             reason="also first"),
                                   expected=None)
        self.assertEqual(we.read_activation(self.prefs, scope)["entry"]["state"], "canary")

    def test_eight_concurrent_swaps_from_one_generation_leave_exactly_one_winner(self):
        """Real threads, and the property is unconditional: whatever the interleaving, exactly
        one generation 2 exists afterwards and it is one of the eight bodies -- never a mixture
        and never a later write on top of an earlier one."""
        scope = self.scope()
        with self.wired():
            we.swap_activation(self.prefs, scope, entry=self.canary(), expected=None)
            entries = [we.retirement_entry(scope=scope, by=f"racer-{i}", reason=f"attempt {i}")
                       for i in range(8)]

            def race(entry):
                try:
                    return we.swap_activation(self.prefs, scope, entry=entry, expected=1)["by"]
                except we.ActivationConflict:
                    return None

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                outcomes = list(pool.map(race, entries))
        winners = [name for name in outcomes if name is not None]
        self.assertEqual(len(winners), 1, f"{len(winners)} writers thought they won: {winners}")
        self.assertEqual(we.activation_generations(self.prefs, scope)[0], [1, 2])
        landed = we.read_activation(self.prefs, scope)["entry"]
        self.assertEqual(landed["by"], winners[0])
        self.assertEqual(landed["previous"], 1)

    def test_the_swap_is_one_kernel_operation_and_not_a_check_then_a_write(self):
        """Structural, because the race above can pass by luck once and this cannot: the writer
        calls `safe_paths.confined_create_bytes` -- `O_EXCL` -- and no whole-file write verb."""
        node = _section_functions()["swap_activation"]
        called = _called_names(node)
        self.assertIn("confined_create_bytes", called)
        for verb in ("confined_write_bytes", "confined_replace", "write_text", "write_bytes",
                     "exists", "is_file"):
            with self.subTest(verb=verb):
                self.assertNotIn(verb, called,
                                 f"swap_activation calls {verb}, which reopens the window "
                                 f"O_EXCL exists to close")
        self.assertTrue(we._sp().confined_create_bytes.__module__.endswith("safe_paths"))

    def test_the_swap_refuses_a_generation_expectation_that_is_not_one(self):
        """`expected` is a generation somebody READ. A bool, a negative number and a count past
        the filename's own ceiling are all caller defects, and each is refused before any name
        is composed -- a path built out of one of them is how a store gets written outside
        itself."""
        entry = we.retirement_entry(scope=self.scope(), by="sam", reason="done")
        for label, expected in (("a bool", True), ("zero", 0), ("a negative", -1),
                                ("not a number", "1"),
                                ("past the last filename", 999999)):
            with self.subTest(expected=label):
                with self.assertRaises(we.EvalError):
                    we.swap_activation(self.prefs, self.scope(), entry=entry, expected=expected)
        self.assertEqual(we.activation_generations(self.prefs, self.scope()), ([], []))
        self.assertTrue(issubclass(we.ActivationConflict, we.EvalError),
                        "a lost swap must be catchable as the module's own refusal")

    def test_the_remaining_caller_defects_are_refused_rather_than_guessed_at(self):
        """The edges that have no other route into a test: an unusable scope, a bundle reference
        that is not one, and an entry nobody signed. Each has a guard and each guard is reached
        from here, so none of them is decoration."""
        _payload, ref = self.bundle()
        for label, scope in (("not an object", ["project"]), ("an empty one", {})):
            with self.subTest(scope=label):
                with self.assertRaises(we.EvalError):
                    we.scope_key(scope)
        with self.wired():
            decision = self.decide()
            for label, bundle_ref in (
                    ("not a reference", {"id": "b"}),
                    ("a reference at another contract", dict(ref, v=we.MANIFEST_VERSION)),
                    ("nothing at all", None)):
                with self.subTest(bundle_ref=label):
                    with self.assertRaises(we.EvalError):
                        we.activation_entry(decision, scope=self.scope(),
                                            bundle_ref=bundle_ref,
                                            eligibility=self.eligibility(),
                                            monitors=self.monitors(), by="alex")
            with self.assertRaises(we.EvalError):
                we.activation_entry(decision, scope=self.scope(), bundle_ref=ref,
                                    eligibility=self.eligibility(), monitors=self.monitors(),
                                    by="")
        for build in (we.rollback_entry, we.retirement_entry):
            with self.subTest(builder=build.__name__):
                kw = {"scope": self.scope(), "by": "", "reason": "x"}
                if build is we.rollback_entry:
                    kw["resolution"] = dp.resolve_bundle(None, [], self.runtime())
                with self.assertRaises(we.EvalError):
                    build(**kw)
        with self.assertRaises(we.EvalError):
            we.rollback_entry(scope=self.scope(), by="sam", reason="x",
                              resolution={"source": "pinned"})

    def test_an_unreadable_older_generation_is_listed_and_never_dropped(self):
        """A history with a hole in it is how a rollback comes to look like it never happened."""
        scope = self.scope()
        with self.wired():
            we.swap_activation(self.prefs, scope, entry=self.canary(), expected=None)
            we.swap_activation(self.prefs, scope,
                               entry=we.retirement_entry(scope=scope, by="sam", reason="done"),
                               expected=1)
        root = self.prefs / we.POLICY_ACTIVATION / we.scope_key(scope)
        (root / "gen-000001.json").write_text("{corrupted after it was written")
        rows = we.activation_history(self.prefs, scope)["generations"]
        self.assertEqual([(row["generation"], row["state"]) for row in rows],
                         [(1, "unreadable"), (2, "retired")])
        self.assertTrue(rows[0]["detail"])

    # ==========================================================================================
    #  A RUN PINS WHAT IT STARTED WITH
    # ==========================================================================================

    def test_a_run_keeps_the_pointer_generation_it_started_under(self):
        """Through the REAL seam. `kit_contract.start_task_lifecycle(policy_ref=...)` hands the
        pin to `TaskRun`, which records it on every attempt; the assertion is read off the
        attempt events the ledger actually wrote, not off the object in memory.

        The pointer is swapped to a different bundle between the two attempts. A run that
        silently picked up the new one is the bug this term exists to prevent.
        """
        scope = self.scope()
        kit_dir = self.root / "kit"
        kit_dir.mkdir()
        task = kc._demo_task("T1")
        with self.wired():
            we.swap_activation(self.prefs, scope, entry=self.canary(), expected=None)
            started = we.runtime_activation(self.prefs, scope, facts=self.facts())
            pin = we.pin_for_run(started)
            self.assertIsNotNone(pin)
            lifecycle, _info = kc.start_task_lifecycle(
                kit_dir, task, "run-1", "test", store=self.attempts,
                workspace=self.workspace, policy_ref=pin)
            self.addCleanup(lifecycle.end)
            first = lifecycle.attempt_started("initial", "m")

            # A second generation lands, naming a DIFFERENT bundle, while the run is in flight.
            other_payload, other_ref = self.bundle(id="bundle-recovery-context-2")
            self.assertNotEqual(other_ref["id"], pin["id"])
            we.swap_activation(self.prefs, scope,
                               entry=self.canary(bundle_ref=other_ref), expected=1)
            second = lifecycle.attempt_started("retry", "m")
            fresh = we.runtime_activation(self.prefs, scope, facts=self.facts())

        pins = {ev["attempt"]: al.read_ref(ev.get("policy_ref"))
                for ev in lifecycle.ledger.events() if ev.get("kind") == "attempt.started"}
        self.assertEqual(sorted(pins), sorted([first, second]))
        self.assertEqual(pins[first]["id"], pin["id"])
        self.assertEqual(pins[second]["id"], pin["id"],
                         "the in-flight run picked up a generation that landed after it started")
        self.assertEqual(we.pin_for_run(fresh)["id"], other_ref["id"],
                         "a run starting NOW should see generation 2")
        self.assertEqual(started["generation"], 1)
        self.assertEqual(fresh["generation"], 2)

    def test_a_run_that_pinned_nothing_records_the_field_as_unknown(self):
        """Which is every run today, and is the shape `TaskRun` has always had: the default is
        None, the field is not written, and provenance reads it back as unknown."""
        kit_dir = self.root / "kit-unpinned"
        kit_dir.mkdir()
        lifecycle, _info = kc.start_task_lifecycle(kit_dir, kc._demo_task("T1"), "run-1", "test",
                                                   store=self.attempts, workspace=self.workspace)
        self.addCleanup(lifecycle.end)
        self.assertIsNone(lifecycle.policy_ref)
        attempt = lifecycle.attempt_started("initial", "m")
        event = next(ev for ev in lifecycle.ledger.events()
                     if ev.get("kind") == "attempt.started" and ev.get("attempt") == attempt)
        self.assertIsNone(al.read_ref(event.get("policy_ref")))
        self.assertIsNone(al.provenance(event)["policy_ref"])

    def test_pinned_bundle_has_no_parameter_a_pointer_could_arrive_through(self):
        """THE SIGNATURE IS THE GUARANTEE, the way `_admissible`'s is. There is no prefs
        directory, store, scope or pointer in this signature, so there is no expression in the
        function that could consult one -- `run pins` is a thing it cannot violate."""
        signature = inspect.signature(dp.pinned_bundle)
        self.assertEqual(list(signature.parameters), ["pin", "bundles", "runtime"])
        source = inspect.getsource(dp.pinned_bundle)
        for forbidden in ("prefs", "read_activation", "runtime_activation", "open(", "Path("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_a_canary_pin_resolves_its_bundle_and_still_does_not_act(self):
        """Resolving which parameters a pinned bundle holds and ACTING on them are two
        questions. `decision_policy` implements `legacy` and `shadow`; a `canary` pin resolves
        and reports that no mode it implements was pinned, and `select_action` still refuses the
        word by name."""
        payload, ref = self.bundle()
        with self.wired():
            we.swap_activation(self.prefs, self.scope(), entry=self.canary(bundle_ref=ref),
                               expected=None)
            pin = we.run_pin(we.runtime_activation(self.prefs, self.scope(),
                                                   facts=self.facts()))
        reading = dp.pinned_bundle(pin, [payload], self.runtime())
        self.assertEqual(reading["mode"], "canary")
        self.assertIs(reading["acts"], False)
        self.assertIn("select_action still refuses", reading["reason"])
        self.assertEqual(reading["resolution"].source, "pinned")
        self.assertEqual(reading["generation"], 1)
        self.assertNotIn("canary", dp.SELECTION_MODES)
        with self.assertRaises(dpc.ContractError):
            dp.select_action(object(), mode="canary")

    def test_an_unpinned_run_resolves_exactly_as_it_always_has(self):
        reading = dp.pinned_bundle(None, [], self.runtime())
        self.assertIs(reading["pinned"], False)
        self.assertEqual(reading["mode"], "legacy")
        self.assertIs(reading["acts"], True)
        self.assertEqual(reading["resolution"].source, "legacy")
        self.assertEqual(reading["resolution"].reasons, ("no-pin",))

    def test_a_malformed_pin_refuses_rather_than_degrading_to_legacy(self):
        """A run pinned to something unreadable is a caller defect, and answering it with the
        safe-looking default would hide which run is mis-pinned."""
        _payload, ref = self.bundle()
        good = {"mode": "canary", "generation": 1, "activation": "act-x", "bundle_ref": ref}
        for label, pin in (
                ("not an object", ["nope"]),
                ("an unknown key", dict(good, extra=1)),
                ("a missing key", {k: v for k, v in good.items() if k != "generation"}),
                ("an undeclared mode", dict(good, mode="turbo"))):
            with self.subTest(case=label):
                with self.assertRaises(dpc.ContractError):
                    dp.pinned_bundle(pin, [], self.runtime())

    # ==========================================================================================
    #  ROLLBACK
    # ==========================================================================================

    def test_rollback_names_the_fallback_its_owner_chose_and_ends_at_legacy(self):
        """`resolve_bundle` is what refuses an unapproved bundle (`approval-absent`) and what
        guarantees the chain terminates at legacy. This relays its answer and resolves no chain
        of its own -- and recording a target is not taking it: every future run reads legacy."""
        scope = self.scope()
        unapproved, _ref = self.bundle(
            provenance={"approval_ref": None,
                        "evaluation_ref": tpb.ref("manifest-1", we.MANIFEST_VERSION),
                        "rolled_back_from": None})
        pin = tpb.ref(unapproved["id"], dc.BUNDLE_VERSION,
                      sha=dc.parse_bundle(unapproved).sha())
        resolution = dp.resolve_bundle(pin, [unapproved], self.runtime())
        self.assertEqual(resolution.source, "legacy")
        self.assertIn("approval-absent", resolution.reasons)
        entry = we.rollback_entry(scope=scope, resolution=resolution, by="sam",
                                  reason="the canary regressed")
        self.assertEqual(entry["fallback"]["source"], "legacy")
        self.assertIsNone(entry["fallback"]["bundle_ref"])
        self.assertIn("approval-absent", entry["fallback"]["reasons"])
        self.assertEqual(entry["fallback"]["in_force_for_future_runs"], "legacy")
        self.assertIsNone(entry["bundle_ref"])
        self.assertIn(we.ROLLBACK_TARGET_NOT_ACTIVATED_LABEL, entry["labels"])
        we.swap_activation(self.prefs, scope, entry=entry, expected=None)
        answer = we.runtime_activation(self.prefs, scope, facts=self.facts())
        self.assertEqual(answer["mode"], "legacy")
        self.assertEqual(answer["reasons"], ["pointer-rolled-back"])

    def test_naming_a_fallback_bundle_is_not_activating_it(self):
        """The case the legacy fallback above cannot reach, and the one where `bundle_ref` being
        null does work: a resolution that SELECTS a real approved bundle. The rolled-back entry
        names it under `fallback` and pins nothing, because promoting it into a running state
        would need its own pass through the gate -- and `validate_entry` refuses an entry that
        tried to skip that."""
        scope = self.scope()
        payload, ref = self.bundle()
        resolution = dp.resolve_bundle(ref, [payload], self.runtime())
        self.assertEqual(resolution.source, "pinned", "the fallback resolved to nothing to name")
        self.assertIn("selected", resolution.reasons)

        entry = we.rollback_entry(scope=scope, resolution=resolution, by="sam",
                                  reason="the canary regressed")
        self.assertEqual(entry["fallback"]["bundle_ref"]["id"], payload["id"])
        self.assertIsNone(entry["bundle_ref"],
                          "the rollback pinned the fallback instead of merely naming it")
        self.assertEqual(entry["fallback"]["in_force_for_future_runs"], "legacy")
        self.assertIn("activation_decision", entry["fallback"]["requires"])

        we.swap_activation(self.prefs, scope, entry=entry, expected=None)
        answer = we.runtime_activation(self.prefs, scope, facts=self.facts())
        self.assertEqual(answer["mode"], "legacy")
        self.assertEqual(answer["reasons"], ["pointer-rolled-back"])
        self.assertIsNone(answer["pin"])
        self.assertEqual(answer["fallback"]["bundle_ref"]["id"], payload["id"])
        # And the writer refuses the shortcut outright, whichever way it is spelled.
        with self.assertRaises(we.EvalError) as raised:
            we.validate_entry(dict(entry, bundle_ref=ref))
        self.assertIn("bundle_ref", str(raised.exception))

    def test_rollback_preserves_every_generation_the_evidence_and_the_workspace(self):
        """Nothing is deleted, nothing is rewritten, nothing outside the pointer directory is
        touched: the earlier generations, the evals store and a user's workspace all come out
        byte-identical, and the history still lists what was rolled back from."""
        scope = self.scope()
        store = self.fresh_store(self.manifest())
        with self.wired():
            we.swap_activation(self.prefs, scope, entry=self.canary(), expected=None)
            we.swap_activation(self.prefs, scope, entry=self.canary(), expected=1)
        pointers_before = _digest_tree(self.prefs / we.POLICY_ACTIVATION)
        store_before = _digest_tree(store)
        workspace_before = _digest_tree(self.workspace)
        self.assertTrue(store_before and workspace_before, "nothing to preserve; test is empty")

        entry = we.rollback_entry(scope=scope, by="sam", reason="regressed",
                                  resolution=dp.resolve_bundle(None, [], self.runtime()))
        we.swap_activation(self.prefs, scope, entry=entry, expected=2)

        after = _digest_tree(self.prefs / we.POLICY_ACTIVATION)
        for name, digest in pointers_before.items():
            with self.subTest(generation=name):
                self.assertEqual(after.get(name), digest, "an earlier generation moved")
        self.assertEqual(_digest_tree(store), store_before, "the evals store moved")
        self.assertEqual(_digest_tree(self.workspace), workspace_before, "a workspace moved")
        history = we.activation_history(self.prefs, scope)["generations"]
        self.assertEqual([(row["generation"], row["state"]) for row in history],
                         [(1, "canary"), (2, "canary"), (3, "rolled-back")])
        self.assertIn(we.ROLLBACK_SCOPE_LABEL,
                      we.activation_history(self.prefs, scope)["labels"])

    def test_rollback_contacts_no_provider_and_writes_through_no_other_owner(self):
        """Every dispatch, grading, mining and foreign-writer seam is armed with a raiser for the
        duration. A canned return would be indistinguishable from a real call that was ignored,
        so these raise."""
        scope = self.scope()
        resolution = dp.resolve_bundle(None, [], self.runtime())
        with _ArmedSeams(self):
            entry = we.rollback_entry(scope=scope, resolution=resolution, by="sam",
                                      reason="regressed")
            we.swap_activation(self.prefs, scope, entry=entry, expected=None)
            answer = we.runtime_activation(self.prefs, scope, facts=self.facts())
            we.activation_history(self.prefs, scope)
            we.activation_report(self.prefs)
        self.assertEqual(answer["mode"], "legacy")

    # ==========================================================================================
    #  ELIGIBILITY AND MONITORING ARE DECLARED, BOUNDED, AND CHECKED
    # ==========================================================================================

    def test_an_unbounded_or_unwatched_canary_is_not_a_canary(self):
        _payload, ref = self.bundle()
        with self.wired():
            decision = self.decide()
            bad = {
                "no task class": self.eligibility(task_classes=[]),
                "no run ceiling": self.eligibility(max_runs=0),
                "a ceiling that is not a count": self.eligibility(max_runs=True),
                "an unknown key": dict(self.eligibility(), everything=True),
            }
            for label, eligibility in bad.items():
                with self.subTest(eligibility=label):
                    with self.assertRaises(we.EvalError):
                        we.activation_entry(decision, scope=self.scope(), bundle_ref=ref,
                                            eligibility=eligibility, monitors=self.monitors(),
                                            by="alex")
            for label, monitors in (("nothing watched", []),
                                    ("a monitor nobody declared", ["vibes"])):
                with self.subTest(monitors=label):
                    with self.assertRaises(we.EvalError):
                        we.activation_entry(decision, scope=self.scope(), bundle_ref=ref,
                                            eligibility=self.eligibility(), monitors=monitors,
                                            by="alex")

    def test_a_declared_cohort_bounds_which_runs_the_canary_reaches(self):
        scope = self.scope()
        with self.wired():
            we.swap_activation(
                self.prefs, scope,
                entry=self.canary(eligibility=self.eligibility(cohort=["item-a", "item-b"])),
                expected=None)
            inside = we.runtime_activation(self.prefs, scope,
                                           facts=self.facts(item="item-a"))
            outside = we.runtime_activation(self.prefs, scope,
                                            facts=self.facts(item="item-z"))
        self.assertEqual(inside["mode"], "canary")
        self.assertEqual(outside["mode"], "legacy")
        self.assertEqual(outside["reasons"], ["outside-eligible-cohort"])

    def test_runtime_facts_are_exactly_what_the_check_needs_or_nothing_is_checked(self):
        scope = self.scope()
        with self.wired():
            we.swap_activation(self.prefs, scope, entry=self.canary(), expected=None)
            for label, facts in (("an unknown key", dict(self.facts(), extra=1)),
                                 ("a missing key", {"task_class": tpb.TASK_CLASS,
                                                    "item": None}),
                                 ("a count that is not one", self.facts(runs_so_far=-1))):
                with self.subTest(facts=label):
                    with self.assertRaises(we.EvalError):
                        we.runtime_activation(self.prefs, scope, facts=facts)

    # ==========================================================================================
    #  THE HONESTY CONTRACT
    # ==========================================================================================

    def test_the_residual_codes_are_unconditional_and_machine_readable(self):
        """Not prose a reader has to notice. Every record carries all three codes whatever the
        gate decided and whichever world it was decided in, and every code has a note."""
        records = {"refused decision": self.decide(),
                   "report": we.activation_report(self.prefs)}
        with self.wired():
            records["permitted decision"] = self.decide()
            records["minted entry"] = self.canary()
        for label, record in records.items():
            with self.subTest(record=label):
                self.assertEqual(record["unproven"], list(we.ACTIVATION_UNPROVEN))
        self.assertEqual(sorted(we.ACTIVATION_UNPROVEN_NOTES), sorted(we.ACTIVATION_UNPROVEN))
        for code, note in we.ACTIVATION_UNPROVEN_NOTES.items():
            with self.subTest(code=code):
                self.assertGreater(len(note), 80, f"{code} has no note worth reading")

    def test_no_record_claims_a_name_broader_than_the_check_behind_it(self):
        """This kit's most-produced defect. `permitted` is the conjunction of the rows and
        nothing else; `promotion_eligible` is D22's own verdict; and no field anywhere says
        certified, verified, safe or isolated."""
        with self.wired():
            permitted = self.decide()
        self.assertIs(permitted["permitted"],
                      all(row["satisfied"] for row in permitted["requirements"]))
        refused = self.decide()
        self.assertIs(refused["permitted"],
                      all(row["satisfied"] for row in refused["requirements"]))
        blob = json.dumps({k: v for k, v in refused.items() if k != "labels"}).lower()
        for word in ("\"isolated\"", "\"safe\"", "\"certified\":true", "\"verified\":true"):
            with self.subTest(word=word):
                self.assertNotIn(word, blob.replace(" ", ""))

    def test_the_pointer_is_integrity_and_says_it_is_not_authority(self):
        self.assertIn("pointer-store-not-authenticated", we.ACTIVATION_UNPROVEN)
        with self.wired():
            entry = self.canary()
        self.assertIn(we.POINTER_NOT_AUTHORITY_LABEL, entry["labels"])
        self.assertIn(we.POINTER_NOT_AUTHORITY_LABEL, we.activation_report(self.prefs)["labels"])

    # ==========================================================================================
    #  STRUCTURE: WHAT THE SECTION IS, AND WHAT IT MAY NOT BECOME
    # ==========================================================================================

    def test_the_section_defines_only_what_it_declares(self):
        found = _section_functions()
        self.assertEqual(sorted(found), sorted(SECTION_FUNCTIONS))

    def test_nothing_in_the_section_dispatches_grades_mines_or_reaches_a_home(self):
        for name, node in _section_functions().items():
            with self.subTest(function=name):
                reached = sorted(_called_names(node) & DISPATCHING_NAMES)
                self.assertEqual(reached, [], f"{name} calls {reached}")

    def test_only_the_swap_writes_anything(self):
        for name, node in _section_functions().items():
            with self.subTest(function=name):
                verbs = sorted(_called_names(node) & WRITER_NAMES)
                if name in SECTION_WRITERS:
                    self.assertTrue(verbs, "the one writer writes nothing")
                else:
                    self.assertEqual(verbs, [], f"{name} writes: {verbs}")

    def test_the_section_names_no_default_store_and_needs_no_new_one(self):
        """`runtime_data.STORES` gains nothing and `.gitignore` gains nothing: the pointer lives
        under the prefs directory D20 already owns, and every function is handed one."""
        start, end, tree = _section_bounds()
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
                 and start < getattr(n, "lineno", 0) < end}
        for forbidden in ("DEFAULT_PREFS_DIR", "DEFAULT_STORE_DIR"):
            with self.subTest(name=forbidden):
                self.assertNotIn(forbidden, names)
        self.assertNotIn("activation", rt.STORES)
        self.assertNotIn("replay", rt.STORES)
        report = we.activation_report(self.prefs)
        self.assertTrue(report["path"].startswith(str(self.prefs)))
        self.assertEqual(we._prefs_paths(self.prefs)["activation"],
                         self.prefs / we.POLICY_ACTIVATION)

    def test_old_preferences_still_do_nothing_automatically(self):
        """Pull-only, as D20 held. Nothing in the section reads the applied preference file, and
        an existing one does not become a pointer because a pointer store now exists beside it."""
        self.prefs.mkdir(parents=True, exist_ok=True)
        (self.prefs / we.POLICY_FILE).write_text(
            json.dumps(tpb.preference_payload(), indent=2) + "\n")
        answer = we.runtime_activation(self.prefs, self.scope(), facts=self.facts())
        self.assertEqual(answer["mode"], "legacy")
        self.assertEqual(answer["reasons"], ["no-pointer"])
        self.assertIn(we.OLD_PREFERENCES_UNCHANGED_LABEL, answer["labels"])
        start, end, tree = _section_bounds()
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
                 and start < getattr(n, "lineno", 0) < end}
        self.assertNotIn("POLICY_FILE", names)
        self.assertEqual(we.policy_report(self.prefs)["consumption"], "pull-only")

    def test_the_lifecycle_vocabulary_is_closed_and_disjoint_from_the_approval_one(self):
        """D22 stops at `approved` on purpose; these four are what comes after it, and no name
        appears in both -- a state that meant two things in two vocabularies would make a report
        meaningless."""
        self.assertEqual(we.ACTIVATION_STATES, ("canary", "active", "retired", "rolled-back"))
        self.assertEqual(set(we.ACTIVATION_STATES) & set(we.APPROVAL_STATES), set())
        self.assertEqual(set(we.RUNNING_STATES) - set(we.ACTIVATION_STATES), set())
        self.assertEqual(set(we.RUNNING_STATES), set(dp.DEFERRED_MODES))
        self.assertEqual(set(we.ACTIVATION_BLOCKERS)
                         & set(we.PROTOCOL_BLOCKERS), set(),
                         "a blocker with two owners is a blocker nobody counts")
        with self.assertRaises(we.EvalError):
            we.activation_decision({}, target_state="retired")

    def test_the_entry_shape_is_closed_in_both_directions(self):
        with self.wired():
            entry = self.canary()
            self.assertEqual(sorted(entry), sorted(we.ACTIVATION_ENTRY_KEYS))
            for label, broken in (
                    ("an unknown key", dict(entry, surprise=1)),
                    ("a missing key", {k: v for k, v in entry.items() if k != "scope"}),
                    ("another version", dict(entry, v="polytropos.policy-activation/99")),
                    ("a state nobody declared", dict(entry, state="warming")),
                    ("nobody who took it", dict(entry, by="")),
                    ("a scope it does not name",
                     dict(entry, scope={"project": "somewhere-else", "task_classes": ["x"],
                                        "intended_uses": ["y"]}))):
                with self.subTest(entry=label):
                    with self.assertRaises(we.EvalError):
                        we.validate_entry(broken)

    def test_a_retired_or_rolled_back_entry_carries_no_bundle_gate_or_cohort(self):
        """A state that resolves every future run to legacy names none of them; recording a
        fallback is what the `fallback` block is for."""
        _payload, ref = self.bundle()
        base = we.retirement_entry(scope=self.scope(), by="sam", reason="done")
        for field, value in (("bundle_ref", ref), ("gate", {"permitted": True}),
                             ("eligibility", self.eligibility()),
                             ("monitors", self.monitors())):
            with self.subTest(field=field):
                with self.assertRaises(we.EvalError) as raised:
                    we.validate_entry(dict(base, **{field: value}))
                self.assertIn(field, str(raised.exception))

    def test_the_version_is_registered_and_no_existing_version_moved(self):
        """A new constant needs a `VERSION_SOURCES` row. Nothing already at /1 is bumped: the
        referenced OBJECT is versioned, never the envelope around it."""
        rows = {row["contract"]: row for row in rg.contract_versions()}
        self.assertEqual(rows["policy activation pointer"]["version"], we.ACTIVATION_VERSION)
        self.assertEqual(rows["policy activation pointer"]["owner"], "bin/workflow_eval.py")
        for name in ("EVAL_VERSION", "PROPOSAL_VERSION", "POLICY_VERSION", "MANIFEST_VERSION",
                     "POLICY_REFS_VERSION", "APPROVAL_VERSION", "TRIAL_PROTOCOL_VERSION"):
            with self.subTest(constant=name):
                self.assertTrue(getattr(we, name).endswith("/1"))

    def test_the_cli_reports_and_there_is_no_command_that_activates(self):
        """A read-only command. One that offered to take the transition would offer something
        that cannot happen -- and if one day it can, the edit that wires it should have to add
        the command in the same change."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = we.main(["activation", "--prefs-dir", str(self.prefs)])
        self.assertEqual(rc, 0)
        text = buf.getvalue()
        self.assertIn("confining, ledgered dispatch wired: False", text)
        self.assertIn("no pointer for any scope", text)
        parser = we.build_parser()
        actions = [a for a in parser._subparsers._group_actions[0].choices]
        self.assertIn("activation", actions)
        for banned in ("activate", "canary", "promote", "rollback-activation"):
            with self.subTest(command=banned):
                self.assertNotIn(banned, actions)

    # ==========================================================================================
    #  PHASE 5 REVIEW, F2: A WIRED RUNTIME STILL REFUSES AN APPROVAL NOTHING RE-DERIVED
    # ==========================================================================================

    def forged_approval(self):
        """A hand-built record that bound NOTHING, by the same name that proposed it. Every
        field is a string a caller chose; no `approval_case` and no `decide_approval` was
        involved, which is the whole point."""
        return {"v": we.APPROVAL_VERSION, "id": "appr-forged", "state": "approved",
                "granted": True, "bindings": None, "by": "mallory", "proposed_by": "mallory"}

    def test_a_wired_runtime_refuses_an_approval_that_bound_and_re_derived_nothing(self):
        """THE END-TO-END FORM OF THE PHASE 5 F2 FINDING, in the one world where the pointer
        mechanics are reachable at all. Today the refusal is entirely `CONFINED_DISPATCH_WIRED`:
        flip that constant and a forged approval with no `case` minted an entry, wrote a
        generation and read back as a canary, because
        `approval_ok = granted and (holds is None or holds['holds'])` read "nobody checked" as
        "the check passed" -- `trial_cohort`'s Phase 4 defect ("frozen because a `manifest`
        argument was PASSED") in a second place.

        Asserted on `permitted` and on the blocker SET. NOT on whether an entry could be minted,
        because in the world as it is that is False for the dispatch reason regardless -- which
        is exactly why this hid behind a gate that contributes nothing.
        """
        manifest = self.manifest()
        kw = {"case": None, "target_state": "canary", "sentinel_report": ttp._sentinel_report(),
              "store_dir": self.fresh_store(manifest), "manifest": manifest,
              "partition": "promotion", "declarations": self.declarations()}
        with self.wired():
            decision = we.activation_decision(self.forged_approval(), **kw)
            self.assertIs(decision["permitted"], False)
            self.assertEqual(self.blockers(decision), ["exact-approval-not-re-derived"])
            row = next(r for r in decision["requirements"]
                       if r["requirement"] == "exact-approval")
            self.assertIs(row["satisfied"], False)
            self.assertIsNone(row["re_derived_by"])
            with self.assertRaises(we.EvalError) as raised:
                we.activation_entry(decision, scope=self.scope(), bundle_ref=self.bundle()[1],
                                    eligibility=self.eligibility(), monitors=self.monitors(),
                                    by="mallory")
            self.assertIn("exact-approval-not-re-derived", str(raised.exception))
        self.assertIs(we.CONFINED_DISPATCH_WIRED, False)
        # And nothing was written on the way through: no generation exists for this scope.
        reading = we.read_activation(self.prefs, self.scope())
        self.assertEqual(reading["generations"], [])
        self.assertIsNone(reading["entry"])


class PolicyEvidenceReportTests(unittest.TestCase):
    """D24 -- workflow_eval's read-only projection over what D14-D23 already computed, decided
    or refused: lineage (approval -> evaluation -> profile -> manifest -> partition), scope,
    interventions, resource bases, quality (with the invalid/abstain distinction D15 draws),
    monitoring (a PROPOSAL only, never an action) and delayed/censored escaped defects.

    NOTHING HERE MEASURES A LIVE OUTCOME. Every fixture below is synthetic, exactly as D19-D23's
    own fixtures are, and the same `fixture-proves-mechanics-not-safety` limit applies: a
    passing test here shows this section relays what its owners already computed, never that
    any of it has been observed for real. `we.MECHANICS_NOT_PERFORMANCE_LABEL` is on every
    assembled report for that reason, and this file never asserts a number as a gain.
    """

    N_TASKS = 3

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="polytropos-policy-evidence-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    # -- fixtures, every one from the generator that owns its shape -----------------------------

    def tasks(self, n=None):
        return [tem.task(f"task-{i}", issue=i + 1,
                         statement=f"defect {i} shows up in the widget",
                         reference_patch=tem.diff(f"src/mod{i}.py", f"    old_{i}()",
                                                  f"    new_{i}()"))
                for i in range(self.N_TASKS if n is None else n)]

    def manifest(self):
        return we.build_manifest(tem.REPO, tem.BASE, self.tasks(), acceptance=tem.TEST_CMD,
                                 allocation={"promotion": 1}, labels=())

    def candidate(self, manifest):
        return tpb.proposal_payload(
            evaluation={"endpoint": "accepted-completion", "partition": "promotion",
                        "manifest_ref": we.manifest_ref(manifest)})

    def envelope(self, **kw):
        kw.setdefault("n_tasks", self.N_TASKS)
        return twe.synthetic_envelope(**kw)

    def scope_dict(self):
        return {"project": tpb.PROJECT, "task_classes": [tpb.TASK_CLASS],
                "intended_uses": [tpb.USE]}

    def approved(self, manifest=None, *, envelope=None, scope=None, decision="accept"):
        """A granted (or refused) D22 approval over a complete evaluation -> `(record, case)`."""
        manifest = manifest or self.manifest()
        candidate = self.candidate(manifest)
        case = we.approval_case(candidate=candidate, manifest=manifest, partition="promotion",
                                envelope=self.envelope() if envelope is None else envelope,
                                in_force={}, proposed_by="pat")
        record = we.decide_approval(
            case, by="alex", scope=dict(case["scope"]) if scope is None else scope,
            decision=decision)
        return record, case

    def sentinel(self):
        return ttp._sentinel_report()

    def arm_record(self, item, accepted, *, initial=0.40, reused=False, recovery=()):
        return {"item": item, "accepted": accepted,
                "initial_attempt": {"basis": "estimated", "usd": initial},
                "initial_attempt_reused": reused,
                "recovery_costs": [{"basis": "estimated", "usd": usd} for usd in recovery],
                "overhead": []}

    def recovery_with_accounting(self):
        accounting = we.arm_accounting({"arm": "repair"},
                                       [self.arm_record("item-0001", True, recovery=(0.2,))])
        return de.recovery_report(provenance="synthetic",
                                  join_document=de.join([]), operator_declarations={},
                                  accountings=[accounting]), accounting

    def recovery_with_intervention(self):
        """A real D14 join, through D14's OWN separately-loaded module (`tde`), carrying one
        `human-adjudication` label source -- built exactly the way
        `test_decision_eval.PredictionTimeJoinTests` builds its own disagreement fixture."""
        req = tde.request()
        res = tde.result_for(req)
        rec = tde.record_for(req, res)
        trial = tde.trial_record(solved=False, accepted=True, acceptance_by="kit-check")
        env = tde.envelope_with(trial, [{"trial": "t-1", "by": "a-person", "verdict": "solved",
                                         "note": "", "at": tde.LATER}])
        row = tde.de.join_row(req, prediction_at=tde.PREDICT, result=res, record=rec,
                              targets=[tde.recovery_target(), tde.graded_target()],
                              envelope=env, trial_id="t-1")
        joined = tde.de.join([row])
        return tde.de.recovery_report(provenance="synthetic", join_document=joined,
                                      operator_declarations={})

    def recovery_with_quality(self):
        pair = de.calibration_report_pair(tde.bulk_rows(25), question=tde.Q)
        return de.recovery_report(provenance="synthetic", join_document=de.join([]),
                                  operator_declarations={}, calibration=pair)

    # ==========================================================================================
    #  LINEAGE: APPROVAL -> EVALUATION -> PROFILE -> MANIFEST -> PARTITION
    # ==========================================================================================

    def test_lineage_is_always_the_same_five_links_whatever_was_supplied(self):
        """"Lineage complete" is a STRUCTURAL property of the function, not a fact about which
        arguments happened to be supplied: calling it with nothing at all still returns all
        five names, in order, each explicitly absent -- a projection that quietly narrowed
        itself when its input thinned out would assert a completeness it never checked."""
        lin = we.lineage_report()
        self.assertEqual([link["link"] for link in lin["links"]], list(we.LINEAGE_LINKS))
        self.assertEqual(lin["missing"], list(we.LINEAGE_LINKS))
        for link in lin["links"]:
            with self.subTest(link=link["link"]):
                self.assertFalse(link["present"])

    def test_lineage_is_complete_and_present_over_a_real_approved_case(self):
        manifest = self.manifest()
        record, case = self.approved(manifest)
        sentinel_report = self.sentinel()
        lin = we.lineage_report(approval=record, case=case, sentinel_report=sentinel_report)
        self.assertEqual(lin["missing"], [])
        for link in lin["links"]:
            with self.subTest(link=link["link"]):
                self.assertTrue(link["present"], link.get("reason"))
        approval_link = lin["links"][0]
        self.assertEqual(approval_link["id"], record["id"])
        self.assertEqual(approval_link["state"], "approved")
        for link in lin["links"][1:]:
            if "content_identity_rederived" in link:
                with self.subTest(link=link["link"]):
                    self.assertIs(link["content_identity_rederived"], True, link)

    def test_lineage_relays_promotion_eligibility_rather_than_redeciding(self):
        """Every fact on the approval and profile links comes from `promotion_eligibility`'s OWN
        rows, relayed whole. Patching that function to answer differently changes what this
        section reports, which is the proof it is a relay and not a second decision."""
        fake_reason = "a patched reason nothing here computed"
        fake_verdict = {
            "eligible": False,
            "requirements": [
                {"requirement": "exact-approval", "satisfied": False, "reason": fake_reason,
                 "blocker": "exact-approval-missing", "re_derived_by": "a patched function",
                 "evidence": {}, "note": "patched note", "relayed_from": None},
                {"requirement": "protected-profile-certified", "satisfied": True, "reason": None,
                 "blocker": None, "re_derived_by": "a patched function",
                 "evidence": {"patched": True}, "note": "patched profile note",
                 "relayed_from": None},
                {"requirement": "confining-and-ledgered-dispatch", "satisfied": False,
                 "reason": "unwired", "blocker": "confining-dispatch-unwired",
                 "re_derived_by": "workflow_eval.CONFINED_DISPATCH_WIRED", "evidence": None,
                 "note": None, "relayed_from": None},
            ],
            "blockers": ["exact-approval-missing", "confining-dispatch-unwired"],
            "holds": None, "unproven": list(we.APPROVAL_UNPROVEN), "labels": [],
        }
        with mock.patch.object(we, "promotion_eligibility", return_value=fake_verdict) as patched:
            lin = we.lineage_report(approval={"id": "appr-x"})
        self.assertTrue(patched.called)
        approval_link = lin["links"][0]
        self.assertEqual(approval_link["reason"], fake_reason)
        self.assertFalse(approval_link["present"] and approval_link["satisfied"])
        self.assertFalse(approval_link["satisfied"])
        profile_link = lin["links"][2]
        self.assertTrue(profile_link["present"])
        self.assertEqual(profile_link["certificate"], {"patched": True})
        self.assertTrue(profile_link["satisfied"])

    def test_lineage_naming_note_disambiguates_evaluation_from_manifest(self):
        lin = we.lineage_report()
        self.assertIn("D22", lin["naming_note"])
        self.assertIn("evaluation", lin["naming_note"])
        self.assertIn("manifest", lin["naming_note"])
        self.assertEqual(lin["naming_note"], we.LINEAGE_NAMING_NOTE)

    def test_content_identity_moves_only_on_the_link_that_actually_changed(self):
        """A manifest rewritten after approval moves ONLY the `manifest` link's content-identity
        re-derivation -- `evaluation` (the run) and `partition` (unaffected membership) still
        hold, which is the proof this is a real per-slot re-derivation and not one flag for the
        whole record."""
        manifest = self.manifest()
        record, case = self.approved(manifest)
        forged = json.loads(json.dumps(manifest))
        forged["content"]["labels"] = ["rewritten after it was approved"]
        forged_case = we.approval_case(candidate=self.candidate(manifest), manifest=forged,
                                       partition="promotion", envelope=case["documents"]["envelope"],
                                       in_force={}, proposed_by="pat")
        lin = we.lineage_report(approval=record, case=forged_case, sentinel_report=self.sentinel())
        by_link = {link["link"]: link for link in lin["links"]}
        # A re-derived hash that simply DIFFERS (rather than failing to re-derive at all)
        # carries no `reason` -- D22's own `approval_holds` only fills that in when the slot
        # could not be re-derived, or was never bound; `matches: False` is the fact itself.
        self.assertIs(by_link["manifest"]["content_identity_rederived"], False)
        self.assertIs(by_link["evaluation"]["content_identity_rederived"], True)
        self.assertIs(by_link["partition"]["content_identity_rederived"], True)

    # ==========================================================================================
    #  SCOPE, VISIBLE EVEN WHEN ABSENT
    # ==========================================================================================

    def test_scope_visibility_reports_absence_explicitly(self):
        scope = we.scope_visibility()
        self.assertEqual(scope["present"], {"approver": False, "candidate": False,
                                            "activation": False})
        self.assertIsNone(scope["agrees"])

    def test_scope_visibility_agrees_when_the_approver_scoped_it_the_same_way(self):
        record, _case = self.approved()
        scope = we.scope_visibility(approval=record)
        self.assertTrue(scope["present"]["approver"])
        self.assertTrue(scope["present"]["candidate"])
        self.assertIs(scope["agrees"], True)

    def test_scope_visibility_disagrees_when_the_approver_scoped_it_differently(self):
        manifest = self.manifest()
        candidate = self.candidate(manifest)
        case = we.approval_case(candidate=candidate, manifest=manifest, partition="promotion",
                                envelope=self.envelope(), in_force={}, proposed_by="pat")
        other_scope = {"project": "somewhere-else", "task_classes": [tpb.TASK_CLASS],
                      "intended_uses": [tpb.USE]}
        record = we.decide_approval(case, by="alex", scope=other_scope, decision="accept")
        scope = we.scope_visibility(approval=record)
        self.assertIs(scope["agrees"], False)
        self.assertEqual(scope["approver_scope"]["project"], "somewhere-else")

    def test_scope_visibility_relays_a_running_entrys_own_scope(self):
        entry = we.retirement_entry(scope=self.scope_dict(), by="sam", reason="done")
        scope = we.scope_visibility(entry=entry)
        self.assertTrue(scope["present"]["activation"])
        self.assertEqual(scope["activation_scope"], entry["scope"])

    def test_scope_visibility_relays_the_whole_scope_object_never_a_narrowed_one(self):
        """A relay that silently dropped a key -- `task_classes`, say -- would still show
        `present["approver"]` True and `agrees` True, exactly as D19's own relay carried an
        undeclared basis straight through while looking clean: a projection that narrows its
        input asserts a completeness it never checked. This checks the WHOLE object against the
        approval record's own stored fields, not one key picked out of it."""
        record, _case = self.approved()
        scope = we.scope_visibility(approval=record)
        self.assertEqual(scope["approver_scope"], record["scope"])
        self.assertEqual(scope["candidate_scope"], record["candidate_scope"])
        self.assertEqual(set(scope["approver_scope"]), set(record["scope"]),
                         "the approver scope lost or gained a key relative to the record")
        self.assertEqual(set(scope["candidate_scope"]), set(record["candidate_scope"]),
                         "the candidate scope lost or gained a key relative to the record")

    # ==========================================================================================
    #  INTERVENTIONS: HUMAN LABEL SOURCES, READ FROM THEIR OWNER AT CALL TIME
    # ==========================================================================================

    def test_intervention_evidence_absent_when_nothing_was_supplied(self):
        result = we.intervention_evidence(None)
        self.assertFalse(result["present"])
        self.assertIsNone(result["counts"])

    def test_intervention_evidence_counts_a_real_human_adjudication(self):
        recovery = self.recovery_with_intervention()
        result = we.intervention_evidence(recovery)
        self.assertTrue(result["present"])
        self.assertEqual(result["counts"]["human-adjudication"], 1)
        self.assertNotIn("kit-acceptance", result["counts"],
                         "an automatic source was counted as an intervention")

    def test_intervention_evidence_reads_human_label_sources_from_its_owner_at_call_time(self):
        """A mutant that copied `HUMAN_LABEL_SOURCES` into a literal would pass every test above
        and fail this one: the owner is patched and the counted set follows."""
        recovery = self.recovery_with_intervention()
        with mock.patch.object(de, "HUMAN_LABEL_SOURCES", ("kit-acceptance",)):
            result = we.intervention_evidence(recovery)
        self.assertEqual(result["human_sources"], ["kit-acceptance"])
        self.assertEqual(result["counts"], {"kit-acceptance": 1})

    # ==========================================================================================
    #  RESOURCE BASES: RELAYED WHOLE, KEPT APART, READ FROM THEIR OWNER AT CALL TIME
    # ==========================================================================================

    def test_resource_basis_report_absent_when_nothing_was_supplied(self):
        result = we.resource_basis_report(None)
        self.assertFalse(result["present"])
        self.assertIsNone(result["accountings"])
        self.assertEqual(result["bases"], list(de.RESOURCE_BASES))

    def test_resource_basis_report_invalid_input_abstains_rather_than_raises(self):
        for bad in ({"v": "not-a-recovery-report"}, {"no": "version-at-all"}, "a string",
                   123):
            with self.subTest(bad=bad if isinstance(bad, dict) else type(bad).__name__):
                result = we.resource_basis_report(bad)
                self.assertFalse(result["present"])
                self.assertIn("abstain", result["reason"])

    def test_resource_basis_report_relays_a_real_accounting_whole(self):
        recovery, accounting = self.recovery_with_accounting()
        result = we.resource_basis_report(recovery)
        self.assertTrue(result["present"])
        self.assertEqual(len(result["accountings"]), 1)
        self.assertEqual(result["accountings"][0]["arm"], "repair")
        self.assertEqual(result["note"], recovery["resources_note"])

    def test_resource_basis_report_present_is_false_over_an_empty_accountings_list(self):
        """`decision_eval.recovery_report` ALWAYS sets `resources` to a list, empty when no
        accounting was supplied -- never `None`. `present` must answer whether an accounting
        actually exists, not merely whether the key is there: a `resources is not None` check
        would read every valid-but-empty recovery report as resource evidence being present."""
        empty = de.recovery_report(provenance="synthetic", join_document=de.join([]),
                                   operator_declarations={})
        self.assertEqual(empty["resources"], [])
        result = we.resource_basis_report(empty)
        self.assertFalse(result["present"])
        self.assertIn("no resource evidence", result["reason"])

    def test_resource_basis_report_refuses_evidence_that_lost_a_basis(self):
        """The closure check: a scope block that lost one of the five bases is refused, never
        relayed as though the missing basis were simply absent evidence."""
        recovery, _accounting = self.recovery_with_accounting()
        corrupted = json.loads(json.dumps(recovery))
        del corrupted["resources"][0]["scopes"]["whole-task"]["totals"]["unpriced"]
        with self.assertRaises(we.EvalError) as raised:
            we.resource_basis_report(corrupted)
        self.assertIn("unpriced", str(raised.exception))

    def test_resource_basis_report_reads_resource_bases_from_its_owner_at_call_time(self):
        """A mutant that copied `RESOURCE_BASES` into a five-item literal would pass every test
        above and fail this one: patching the owner to a SIXTH basis makes a real accounting --
        which only ever carries the five decision_eval knew about when it was built -- look like
        it lost one, and this function refuses it rather than silently accepting five when six
        were promised."""
        recovery, _accounting = self.recovery_with_accounting()
        with mock.patch.object(de, "RESOURCE_BASES",
                               tuple(de.RESOURCE_BASES) + ("a-sixth-basis",)):
            with self.assertRaises(we.EvalError) as raised:
                we.resource_basis_report(recovery)
        self.assertIn("a-sixth-basis", str(raised.exception))

    # ==========================================================================================
    #  QUALITY: INVALID / UNKNOWN / REPORTED, NEVER ONE READ AS ANOTHER
    # ==========================================================================================

    def test_quality_evidence_unknown_when_nothing_was_supplied(self):
        self.assertEqual(we.quality_evidence(None)["status"], "unknown")

    def test_quality_evidence_invalid_input_abstains_rather_than_fabricates(self):
        for bad in ({"v": "garbage"}, "not-a-document", 42):
            with self.subTest(bad=bad if isinstance(bad, dict) else type(bad).__name__):
                result = we.quality_evidence(bad)
                self.assertEqual(result["status"], "invalid")
                self.assertIsNone(result["raw"])
                self.assertIsNone(result["calibrated"])

    def test_quality_evidence_reports_a_real_recovery_report_with_no_quality_block(self):
        recovery, _accounting = self.recovery_with_accounting()
        result = we.quality_evidence(recovery)
        self.assertEqual(result["status"], "no-quality-block")

    def test_quality_evidence_relays_abstained_and_insufficient_evidence_as_distinct(self):
        recovery = self.recovery_with_quality()
        result = we.quality_evidence(recovery)
        self.assertEqual(result["status"], "reported")
        for field in ("raw", "calibrated"):
            with self.subTest(field=field):
                self.assertIn("abstained", result[field])
                self.assertIn("classification_status", result[field])
                self.assertIn(result[field]["classification_status"], de.METRIC_STATUSES)
        self.assertIn("insufficient-evidence", result["note"])
        self.assertIn("abstained", result["note"])

    # ==========================================================================================
    #  MONITORING: A READOUT, AND A PROPOSAL THAT IS NEVER AN ACTION
    # ==========================================================================================

    def test_monitor_readout_is_total_and_never_fabricates_a_zero(self):
        readout = we.monitor_readout(None, None)
        self.assertEqual(readout["monitors"], [])
        readout = we.monitor_readout(list(we.ACTIVATION_MONITORS[:2]), None)
        self.assertEqual([row["status"] for row in readout["monitors"]], ["unknown", "unknown"])
        self.assertTrue(all(row["value"] is None for row in readout["monitors"]))

    def test_monitor_readout_refuses_a_monitor_or_observation_outside_the_vocabulary(self):
        with self.assertRaises(we.EvalError):
            we.monitor_readout(["not-a-real-monitor"], None)
        with self.assertRaises(we.EvalError):
            we.monitor_readout(None, {"not-a-real-monitor": True})

    def test_monitor_readout_never_silently_merges_an_undeclared_observation(self):
        code = we.ACTIVATION_MONITORS[0]
        readout = we.monitor_readout([], {code: True})
        self.assertEqual(readout["monitors"], [])
        self.assertEqual(readout["undeclared_observations"], [code])

    def test_monitor_proposal_abstains_without_a_named_procedure(self):
        readout = we.monitor_readout(list(we.ACTIVATION_MONITORS[:1]),
                                     {we.ACTIVATION_MONITORS[0]: True})
        result = we.monitor_proposal(readout, rollback_monitors=[we.ACTIVATION_MONITORS[0]],
                                     procedure=None)
        self.assertEqual(result["proposal"], "abstain-invalid-input")
        self.assertIn("no approved procedure", result["reason"])

    def test_monitor_proposal_abstains_on_a_non_boolean_observation(self):
        """INVALID INPUT PRODUCES AN ABSTENTION. A truthy non-boolean is not read as `True`: a
        monitor proposing rollback over a number it never validated is exactly the fabricated
        verdict this function refuses to produce."""
        code = we.ACTIVATION_MONITORS[0]
        readout = we.monitor_readout([code], {code: 7})
        result = we.monitor_proposal(readout, rollback_monitors=[code], procedure="proc-1")
        self.assertEqual(result["proposal"], "abstain-invalid-input")
        self.assertIn(code, result["evidence"]["invalid"])

    def test_monitor_proposal_reports_unknown_over_an_unread_monitor(self):
        code = we.ACTIVATION_MONITORS[0]
        readout = we.monitor_readout([code], None)
        result = we.monitor_proposal(readout, rollback_monitors=[code], procedure="proc-1")
        self.assertEqual(result["proposal"], "unknown")

    def test_monitor_proposal_no_signal_when_everything_observed_is_clean(self):
        codes = list(we.ACTIVATION_MONITORS[:2])
        readout = we.monitor_readout(codes, {codes[0]: False, codes[1]: False})
        result = we.monitor_proposal(readout, rollback_monitors=[codes[0]],
                                     drift_monitors=[codes[1]], procedure="proc-1")
        self.assertEqual(result["proposal"], "no-signal")

    def test_monitor_proposal_proposes_rollback_or_drift_when_a_monitor_fires(self):
        codes = list(we.ACTIVATION_MONITORS[:2])
        rollback_readout = we.monitor_readout([codes[0]], {codes[0]: True})
        rollback_result = we.monitor_proposal(rollback_readout, rollback_monitors=[codes[0]],
                                              procedure="proc-1")
        self.assertEqual(rollback_result["proposal"], "propose-rollback")
        drift_readout = we.monitor_readout([codes[1]], {codes[1]: True})
        drift_result = we.monitor_proposal(drift_readout, drift_monitors=[codes[1]],
                                           procedure="proc-1")
        self.assertEqual(drift_result["proposal"], "propose-drift-flag")

    def test_monitor_proposal_reads_review_authority_from_its_owner_at_call_time(self):
        code = we.ACTIVATION_MONITORS[0]
        readout = we.monitor_readout([code], {code: True})
        with mock.patch.object(we, "REVIEW_AUTHORITY", "a-patched-authority"):
            result = we.monitor_proposal(readout, rollback_monitors=[code], procedure="proc-1")
        self.assertEqual(result["authority"], "a-patched-authority")

    def test_monitor_proposal_never_touches_the_controller_or_the_approval_writer(self):
        """MONITORING CANNOT REWRITE CONTROLLER CONDITIONS OR GRANT APPROVAL. Every seam that
        could move the pointer or decide an approval is armed with a raiser for the duration;
        `monitor_proposal` still reaches the right answer, which is the proof it never needed
        them."""
        code = we.ACTIVATION_MONITORS[0]
        readout = we.monitor_readout([code], {code: True})
        saved = []
        for name in ("rollback_entry", "swap_activation", "decide_approval", "activation_entry",
                    "retirement_entry"):
            saved.append((name, getattr(we, name)))
            setattr(we, name, _RaisingSeam(f"we.{name}"))
        try:
            result = we.monitor_proposal(readout, rollback_monitors=[code], procedure="proc-1")
        finally:
            for name, original in saved:
                setattr(we, name, original)
        self.assertEqual(result["proposal"], "propose-rollback")

    # ==========================================================================================
    #  DELAYED / CENSORED ESCAPED DEFECTS, ATTRIBUTED AND NEVER DROPPED
    # ==========================================================================================

    def test_defect_instant_matches_decision_evals_own_over_a_table_of_cases(self):
        """Spelled alike on purpose rather than reached into as a private cross-module call --
        see `decision_eval.RESOURCE_BASES`'s own comment for why this kit prefers a test-pinned
        equivalence. If the two ever drifted apart this is where it would be caught."""
        cases = ["2026-09-19T00:00:00Z", "2026-09-19T00:00:00+00:00",
                "2026-09-19T00:00:00-02:00", "2026-09-19T00:00:00", "not-a-timestamp", "",
                None, 12345]
        for case in cases:
            with self.subTest(case=case):
                self.assertEqual(we._defect_instant(case), de._instant(case))

    def test_defect_window_report_places_every_defect_and_drops_none(self):
        window = "2026-09-19T00:00:00+00:00"
        defects = [
            {"decision_id": "d-within", "discovered_at": "2026-09-18T00:00:00+00:00",
             "status": "confirmed"},
            {"decision_id": "d-delayed", "discovered_at": "2026-09-20T00:00:00+00:00",
             "status": "confirmed"},
            {"decision_id": "d-censored", "discovered_at": "2026-09-20T00:00:00+00:00",
             "status": "censored"},
            {"decision_id": "d-no-timestamp", "status": "confirmed"},
            "not-even-an-object",
        ]
        result = we.defect_window_report(window, defects)
        self.assertEqual(result["total"], len(defects))
        self.assertEqual(result["counts"], {"within-window": 1, "delayed": 1, "censored": 1,
                                            "unknown-window": 1, "invalid": 1})
        by_id = {row["decision_id"]: row for row in result["defects"] if row["decision_id"]}
        self.assertEqual(by_id["d-within"]["placement"], "within-window")
        self.assertEqual(by_id["d-delayed"]["placement"], "delayed")
        self.assertEqual(by_id["d-delayed"]["decision_id"], "d-delayed",
                         "a delayed defect must stay attributed to the decision that caused it")
        self.assertEqual(by_id["d-censored"]["placement"], "censored")
        self.assertEqual(by_id["d-no-timestamp"]["placement"], "unknown-window")
        invalid_row = next(row for row in result["defects"] if row["placement"] == "invalid")
        self.assertTrue(invalid_row["reason"])

    def test_defect_window_report_unknown_window_when_none_was_declared(self):
        """No `observation_window` at all makes every entry `unknown-window` rather than a
        guess at `within-window` -- absence must never read as the earliest possible date."""
        result = we.defect_window_report(None, [
            {"decision_id": "d1", "discovered_at": "2026-09-18T00:00:00+00:00",
             "status": "confirmed"}])
        self.assertEqual(result["counts"]["unknown-window"], 1)
        self.assertEqual(result["counts"]["within-window"], 0)

    def test_defect_window_report_a_malformed_window_never_guesses_a_placement(self):
        result = we.defect_window_report("not-a-timestamp", [
            {"decision_id": "d1", "discovered_at": "2026-09-18T00:00:00+00:00",
             "status": "confirmed"},
            {"decision_id": "d2", "discovered_at": "2026-09-20T00:00:00+00:00",
             "status": "censored"}])
        self.assertTrue(result["window_invalid"])
        self.assertEqual(result["counts"]["invalid"], 1)
        self.assertEqual(result["counts"]["censored"], 1, "censored stays visible regardless")

    def test_defect_window_report_never_raises_on_a_batch_of_garbage(self):
        garbage = [None, 1, "x", {}, {"decision_id": "d1"}, {"status": "confirmed"},
                  {"decision_id": "d1", "status": "not-a-status"}]
        result = we.defect_window_report("2026-09-19T00:00:00+00:00", garbage)
        self.assertEqual(result["total"], len(garbage))
        self.assertTrue(all(row["placement"] == "invalid" for row in result["defects"]))

    # ==========================================================================================
    #  THE ASSEMBLED DOCUMENT: NO GAIN CLAIM, EVERY SECTION PRESENT
    # ==========================================================================================

    def test_policy_evidence_report_assembles_every_section(self):
        manifest = self.manifest()
        record, case = self.approved(manifest)
        report = we.policy_evidence_report(
            approval=record, case=case, sentinel_report=self.sentinel(),
            recovery=self.recovery_with_accounting()[0],
            monitors=list(we.ACTIVATION_MONITORS[:2]),
            observations={we.ACTIVATION_MONITORS[0]: True},
            rollback_monitors=[we.ACTIVATION_MONITORS[0]], procedure="proc-1",
            observation_window="2026-09-19T00:00:00+00:00",
            defects=[{"decision_id": "d1", "discovered_at": "2026-09-18T00:00:00+00:00",
                     "status": "confirmed"}])
        for key in ("v", "lineage", "scope", "interventions", "resources", "quality",
                   "monitoring", "defects", "unproven", "labels"):
            with self.subTest(key=key):
                self.assertIn(key, report)
        self.assertEqual(report["v"], we.POLICY_EVIDENCE_VERSION)
        self.assertEqual(report["monitoring"]["proposal"]["proposal"], "propose-rollback")
        self.assertEqual(report["unproven"], list(we.POLICY_EVIDENCE_UNPROVEN))

    def test_policy_evidence_report_never_claims_a_gain(self):
        """"No gain claim": nothing on this report may read as an improvement, a win rate, a
        speedup or a saving, over the fully-populated document above.

        THE EXEMPTION IS NARROW, BY IDENTITY, NOT BY DROPPING THE WHOLE `labels` KEY. Only the
        three KNOWN disclaimer constants legitimately NAME "win rate"/"saving" in order to
        disclaim them (`MECHANICS_NOT_PERFORMANCE_LABEL` in particular) -- exactly the way
        `decision_eval.assert_no_causal_claim` sweeps KEYS, never disclaiming prose, for a
        causal token. Dropping the whole `labels` key would exempt a FOURTH label nobody wrote
        yet along with the three that earned the exemption, which is this kit's most-produced
        defect wearing test clothing: an exclusion broader than the reason for it. So this
        sweeps `labels` too, with only entries EQUAL to the three named constants removed --
        and the second half of the test proves that narrowing actually bites.
        """
        manifest = self.manifest()
        record, case = self.approved(manifest)
        report = we.policy_evidence_report(
            approval=record, case=case, sentinel_report=self.sentinel(),
            recovery=self.recovery_with_quality(),
            monitors=list(we.ACTIVATION_MONITORS[:2]),
            observations={we.ACTIVATION_MONITORS[0]: False, we.ACTIVATION_MONITORS[1]: False},
            rollback_monitors=[we.ACTIVATION_MONITORS[0]],
            drift_monitors=[we.ACTIVATION_MONITORS[1]], procedure="proc-1",
            observation_window="2026-09-19T00:00:00+00:00", defects=[])
        known_disclaimers = {we.MECHANICS_NOT_PERFORMANCE_LABEL, we.MONITORING_NOT_AUTHORITY_LABEL,
                            we.LINEAGE_NAMING_NOTE}
        forbidden = ("winrate", "improvement", "improved", "speedup", "savings", "saved",
                    "roi", "fasterthan", "cheaperthan")

        def sweep(doc):
            """Every field, `labels` included, with only entries EQUAL to a known disclaimer
            constant removed -- never the whole key, and never by position."""
            swept = dict(doc)
            swept["labels"] = [label for label in doc.get("labels") or []
                               if label not in known_disclaimers]
            blob = json.dumps(swept).lower().replace(" ", "").replace("_", "")
            return [token for token in forbidden if token in blob]

        hits = sweep(report)
        self.assertEqual(hits, [], f"gain-claim token(s) found: {hits}")

        # PROVE THE TIGHTENING BITES. A fourth label -- not one of the three known constants --
        # that genuinely claims a gain must NOT be exempted just because it lives under
        # `labels`. If this does not go red, the narrowing did nothing.
        tampered = dict(report, labels=list(report["labels"]) +
                        ["this candidate showed a 12% win rate improvement over baseline"])
        tampered_hits = sweep(tampered)
        self.assertNotEqual(tampered_hits, [],
                            "an injected gain-claiming label was not caught by the sweep")
        self.assertIn("winrate", tampered_hits)

    def test_policy_evidence_unproven_notes_are_closed_and_readable(self):
        self.assertEqual(sorted(we.POLICY_EVIDENCE_UNPROVEN_NOTES),
                         sorted(we.POLICY_EVIDENCE_UNPROVEN))
        for code, note in we.POLICY_EVIDENCE_UNPROVEN_NOTES.items():
            with self.subTest(code=code):
                self.assertGreater(len(note), 80, f"{code} has no note worth reading")

    def test_the_version_is_registered_and_no_existing_version_moved(self):
        rows = {row["contract"]: row for row in rg.contract_versions()}
        self.assertEqual(rows["policy evidence report"]["version"], we.POLICY_EVIDENCE_VERSION)
        self.assertEqual(rows["policy evidence report"]["owner"], "bin/workflow_eval.py")
        for name in ("EVAL_VERSION", "PROPOSAL_VERSION", "POLICY_VERSION", "MANIFEST_VERSION",
                    "POLICY_REFS_VERSION", "APPROVAL_VERSION", "TRIAL_PROTOCOL_VERSION",
                    "ACTIVATION_VERSION"):
            with self.subTest(constant=name):
                self.assertTrue(getattr(we, name).endswith("/1"))
        version_constants = [n for n in dir(we) if n.endswith("_VERSION")
                            and isinstance(getattr(we, n), str)]
        self.assertEqual(len(version_constants), 9,
                         "exactly eight pre-existing *_VERSION constants plus this task's own")

    # ==========================================================================================
    #  ROUTING_SCORECARD'S OWN ADDITIVE PROJECTION: A RENDERER, NOTHING COMPUTED
    # ==========================================================================================

    def test_routing_scorecard_renders_the_report_without_computing_anything_new(self):
        """`render_policy_evidence_markdown` is additive to `bin/routing_scorecard.py` -- a new
        function beside its other `render_*` cards, reusing `_int_or_na` -- and it is proven
        here rather than left uninvoked: every section of a real report appears in the
        rendered text, and a count this report never measured renders `n/a`, never `0`."""
        manifest = self.manifest()
        record, case = self.approved(manifest)
        report = we.policy_evidence_report(approval=record, case=case,
                                           sentinel_report=self.sentinel())
        text = rs.render_policy_evidence_markdown(report)
        self.assertIn(we.POLICY_EVIDENCE_VERSION, text)
        for heading in ("Lineage", "Scope", "Interventions", "Resource bases", "Quality",
                       "Monitoring", "Delayed / censored"):
            with self.subTest(heading=heading):
                self.assertIn(heading, text)
        self.assertIn("n/a", text, "an unmeasured count must render n/a, never a fabricated 0")
        self.assertNotIn("None", text.split("\n")[0])

    # ==========================================================================================
    #  PHASE 5 REVIEW, F1: THE COUNTS ARE READ FROM THE BLOCK THEY LIVE IN, AND ASSERTED AS
    #  VALUES AGAINST THE GENERATOR -- NEVER AS KEY PRESENCE
    # ==========================================================================================

    def quality_pair(self, resolved=20, abstained=5):
        """A REAL `calibration_report_pair` whose three coverage counts are three DIFFERENT
        numbers, so no assertion below can be satisfied by a coincidence: `resolved` is every
        row, `scoreable` is the rows that carried a distribution, and `abstained` is the rest."""
        rows = tde.bulk_rows(resolved) + tde.bulk_rows(abstained, abstained=True)
        return de.calibration_report_pair(rows, question=tde.Q)

    def recovery_with_quality_pair(self, pair):
        return de.recovery_report(provenance="synthetic", join_document=de.join([]),
                                  operator_declarations={}, calibration=pair)

    def test_quality_evidence_reads_the_counts_from_the_coverage_block_they_live_in(self):
        """`resolved`/`scoreable`/`abstained` live under `coverage` on a
        `decision_eval.calibration_report()` document, NOT at its top level. Reading the top
        level yields `None` for all three while `status` is still `reported` and the keys are
        still present -- known evidence rendered as unknown, on a report whose contract is
        "unknown visible".

        ASSERTED AS VALUES AGAINST THE GENERATOR. The test this replaces checked only that the
        keys existed, and the keys exist unconditionally because the dict literal always writes
        them; that is the vacuous assertion this kit keeps finding. Here every count is compared
        to the number `decision_eval` itself computed, and the three are deliberately different
        (25 / 20 / 5) so a projection that read the wrong one cannot pass.
        """
        pair = self.quality_pair()
        result = we.quality_evidence(self.recovery_with_quality_pair(pair))
        self.assertEqual(result["status"], "reported")
        for field in ("raw", "calibrated"):
            with self.subTest(field=field):
                truth = pair[field]["coverage"]
                # What the owner actually computed, pinned here so a fixture that stopped
                # producing three distinct counts fails loudly instead of weakening the test.
                self.assertEqual((truth["resolved"], truth["scoreable"], truth["abstained"]),
                                 (25, 20, 5))
                self.assertIsNone(pair[field].get("resolved"),
                                  "the top level carries no count; that is the whole finding")
                block = result[field]
                self.assertEqual(block["resolved"], 25)
                self.assertEqual(block["scoreable"], 20)
                self.assertEqual(block["abstained"], 5)
                self.assertEqual(block["classification_status"],
                                 pair[field]["classification"]["status"])

    def test_quality_evidence_relays_coverage_whole_so_a_new_count_cannot_vanish(self):
        """The four-field projection was ALSO unclosed: a count `decision_eval` adds to its own
        coverage block would disappear here silently, which is the same defect F4 names in
        `resource_basis_report`. The block is relayed WHOLE beside the named projection, so a
        field this function never heard of still reaches the reader."""
        pair = self.quality_pair()
        recovery = json.loads(json.dumps(self.recovery_with_quality_pair(pair)))
        for field in ("raw", "calibrated"):
            recovery["quality"][field]["coverage"]["a-seventh-count"] = 7
        result = we.quality_evidence(recovery)
        for field in ("raw", "calibrated"):
            with self.subTest(field=field):
                self.assertEqual(result[field]["coverage"],
                                 recovery["quality"][field]["coverage"])
                self.assertEqual(result[field]["coverage"]["a-seventh-count"], 7)
                self.assertIsNone(result[field]["coverage_reason"])

    def test_quality_evidence_says_so_when_a_count_it_projects_is_not_there(self):
        """The other direction of the same closure. A coverage block that no longer carries one
        of the three projected counts must be REPORTED as a shape change, not rendered as an
        unmeasured `n/a`: `None` because nobody counted and `None` because this function looked
        in the wrong place are the two facts the finding conflated, and a reader is owed the
        difference."""
        pair = self.quality_pair()
        recovery = json.loads(json.dumps(self.recovery_with_quality_pair(pair)))
        del recovery["quality"]["raw"]["coverage"]["resolved"]
        result = we.quality_evidence(recovery)
        self.assertIsNone(result["raw"]["resolved"])
        self.assertIn("resolved", result["raw"]["coverage_reason"])
        # The other field is untouched and still reports its real numbers: a shape change in one
        # block never blanks a block that is fine.
        self.assertEqual(result["calibrated"]["resolved"], 25)
        self.assertIsNone(result["calibrated"]["coverage_reason"])

    def test_quality_evidence_reads_the_projected_count_names_from_one_place(self):
        """The three names this function projects are a declared, closed tuple rather than three
        string literals spread through a dict comprehension -- so the closure check above and the
        projection below it can never disagree about what "the counts" are."""
        self.assertEqual(we.QUALITY_COVERAGE_COUNTS, ("resolved", "scoreable", "abstained"))
        pair = self.quality_pair()
        result = we.quality_evidence(self.recovery_with_quality_pair(pair))
        for field in ("raw", "calibrated"):
            for name in we.QUALITY_COVERAGE_COUNTS:
                with self.subTest(field=field, count=name):
                    self.assertEqual(result[field][name], pair[field]["coverage"][name])

    def test_the_operator_sees_the_real_counts_rather_than_n_a(self):
        """THE OPERATOR-FACING CONSEQUENCE, end to end through the renderer that actually prints
        this to a human. `routing_scorecard.render_policy_evidence_markdown` was printing
        `resolved=n/a scoreable=n/a abstained=n/a` over a report whose counts were all known.
        Nothing in the renderer changed -- it renders what it is given, and what it was given
        was wrong."""
        manifest = self.manifest()
        record, case = self.approved(manifest)
        report = we.policy_evidence_report(approval=record, case=case,
                                           sentinel_report=self.sentinel(),
                                           recovery=self.recovery_with_quality_pair(
                                               self.quality_pair()))
        text = rs.render_policy_evidence_markdown(report)
        self.assertIn("resolved=25 scoreable=20 abstained=5", text)
        self.assertNotIn("resolved=n/a", text)

    # ==========================================================================================
    #  PHASE 5 REVIEW, F4: THE BASIS CHECK RUNS IN BOTH DIRECTIONS
    # ==========================================================================================

    def test_resource_basis_report_refuses_an_undeclared_sixth_basis(self):
        """Phase 4's F4, reproduced here one phase later. `missing` checked only
        `bases - totals`; the payload is then copied WHOLESALE, so an undeclared sixth basis
        carrying real dollars relayed intact onto a report whose own `bases` field named five.
        This is the direction that lies -- a subscription proxy dollar entering a priced total
        is exactly what this repo forbids, and an unrecognised basis is the path it takes."""
        recovery, _accounting = self.recovery_with_accounting()
        smuggled = json.loads(json.dumps(recovery))
        smuggled["resources"][0]["scopes"]["whole-task"]["totals"]["a-sixth-basis"] = {"usd": 12.5}
        with self.assertRaises(we.EvalError) as raised:
            we.resource_basis_report(smuggled)
        message = str(raised.exception)
        self.assertIn("a-sixth-basis", message)
        self.assertIn("whole-task", message)

    def test_resource_basis_report_still_relays_a_well_formed_accounting(self):
        """POSITIVE CONTROL for the direction just added, and the reason a naive subtraction
        would have been wrong: every real `arm_accounting` total carries a `note` key, which is
        not a basis and must not be refused as one. Without this, the guard above would be
        satisfied by a check that refuses every honest accounting."""
        recovery, accounting = self.recovery_with_accounting()
        totals = accounting["scopes"]["whole-task"]["totals"]
        self.assertIn("note", totals)
        self.assertEqual(sorted(set(totals) - set(de.RESOURCE_BASES)),
                         sorted(de.TOTALS_NON_BASIS_KEYS))
        result = we.resource_basis_report(recovery)
        self.assertTrue(result["present"])
        self.assertEqual(result["accountings"][0]["arm"], "repair")

    def test_resource_basis_report_reads_the_non_basis_keys_from_their_owner(self):
        """THE MUTANT THIS KILLS: a copy of `{"note"}` written as a literal here. Patching
        `decision_eval.TOTALS_NON_BASIS_KEYS` to empty makes a REAL accounting's own `note` key
        undeclared, and this must refuse it -- a hardcoded exemption would keep passing and
        would go on exempting `note` after its owner stopped declaring it."""
        recovery, _accounting = self.recovery_with_accounting()
        with mock.patch.object(de, "TOTALS_NON_BASIS_KEYS", ()):
            with self.assertRaises(we.EvalError) as raised:
                we.resource_basis_report(recovery)
        self.assertIn("note", str(raised.exception))

    # ==========================================================================================
    #  PHASE 5 REVIEW, F3: "NO GAIN CLAIM" IS ENFORCED BY THE PRODUCT, NOT ONLY BY A TEST
    # ==========================================================================================

    def populated_report(self, **over):
        manifest = self.manifest()
        record, case = self.approved(manifest)
        kw = {"approval": record, "case": case, "sentinel_report": self.sentinel(),
              "recovery": self.recovery_with_quality_pair(self.quality_pair()),
              "monitors": list(we.ACTIVATION_MONITORS[:2]),
              "observations": {we.ACTIVATION_MONITORS[0]: False,
                               we.ACTIVATION_MONITORS[1]: False},
              "rollback_monitors": [we.ACTIVATION_MONITORS[0]],
              "drift_monitors": [we.ACTIVATION_MONITORS[1]], "procedure": "proc-1",
              "observation_window": "2026-09-19T00:00:00+00:00", "defects": []}
        kw.update(over)
        return we.policy_evidence_report(**kw)

    def test_a_caller_supplied_note_claiming_a_gain_is_refused_by_the_product(self):
        """A capability claim whose only enforcement is a test over one fixture is not
        enforcement. `notes` went straight onto `labels` and rendered as a blockquote directly
        above the disclaimer denying it; `decision_eval.assert_no_causal_claim` is the precedent,
        one phase earlier in this same kit, and it is CALLED at the end of the two reports that
        own it rather than asserted about from outside."""
        with self.assertRaises(we.EvalError) as raised:
            self.populated_report(
                notes=["this candidate showed a 12% win rate improvement over baseline"])
        message = str(raised.exception)
        self.assertIn("winrate", message)
        self.assertIn(we.NO_GAIN_CLAIM, message)

    def test_the_gain_sweep_exempts_exactly_the_one_disclaimer_that_needs_it(self):
        """POSITIVE CONTROL plus the narrowing that makes it worth having.

        `MECHANICS_NOT_PERFORMANCE_LABEL` has to NAME "a win rate, or a saving" in order to
        disclaim them, so a fully populated report must still build. The other two disclaimers
        this report carries contain no token AT ALL, so exempting them would be an exclusion wider
        than its reason -- this kit's signature defect, and exactly what the Phase 4 review caught
        in the TEST that preceded this constant. Asserted here in both directions: the exempt set
        is one entry, that entry really does carry a token, and the other two really are inert, so
        an edit that put a claim into one of them refuses loudly instead of riding an exemption it
        never needed.
        """
        report = self.populated_report()
        self.assertIn(we.MECHANICS_NOT_PERFORMANCE_LABEL, report["labels"])
        self.assertEqual(we.GAIN_CLAIM_EXEMPT, (we.MECHANICS_NOT_PERFORMANCE_LABEL,))
        self.assertEqual(we._gain_hits(we.MECHANICS_NOT_PERFORMANCE_LABEL), ["winrate"])
        for label in (we.MONITORING_NOT_AUTHORITY_LABEL, we.LINEAGE_NAMING_NOTE):
            with self.subTest(label=label[:40]):
                self.assertNotIn(label, we.GAIN_CLAIM_EXEMPT)
                self.assertEqual(we._gain_hits(label), [],
                                 "this disclaimer now carries a token and is NOT exempt, so "
                                 "every report refuses; exempt it on purpose or reword it")
        tampered = dict(report, labels=list(report["labels"]) +
                        ["a 12% win rate improvement over baseline"])
        with self.assertRaises(we.EvalError):
            we.assert_no_gain_claim(tampered, where="a tampered report")

    def test_the_gain_sweep_reaches_a_claim_buried_anywhere_in_the_document(self):
        """Not only `labels`. The sweep walks every string in the document, keys included, the
        way `assert_no_causal_claim` walks every key -- a claim smuggled into a nested `reason`
        or a monitor note is the same claim."""
        report = self.populated_report()
        claim = "measured a 30% speedup"
        places = {
            "a nested link's reason": lambda d: d["lineage"]["links"][0].__setitem__("reason",
                                                                                    claim),
            "a monitor proposal's own labels": lambda d: d["monitoring"]["proposal"]["labels"]
                                                          .append(claim),
            "a quality note": lambda d: d["quality"].__setitem__("note", claim),
            "a KEY rather than a value": lambda d: d["resources"].__setitem__("speedup", 1.3),
        }
        for label, bury in places.items():
            with self.subTest(at=label):
                buried = json.loads(json.dumps(report))
                bury(buried)
                with self.assertRaises(we.EvalError) as raised:
                    we.assert_no_gain_claim(buried, where="a report with a buried claim")
                self.assertIn("speedup", str(raised.exception))

    def test_the_gain_sweep_discloses_what_shape_matching_cannot_prove(self):
        """D19 now says this about `causation`/`causality`: it is a token list, shape-matching
        cannot establish absence, and the note names spellings that are NOT caught. Widening a
        list under a categorical claim only moves the line, so the limit is stated rather than
        implied."""
        self.assertIn("winrate", we.GAIN_TOKENS)
        limit = we.assert_no_gain_claim.__doc__ + we.NO_GAIN_CLAIM
        for uncaught in ("outperform", "uplift", "beat the baseline"):
            with self.subTest(spelling=uncaught):
                self.assertNotIn(uncaught.replace(" ", ""), we.GAIN_TOKENS)
        self.assertIn("cannot", limit.lower())
        self.assertIn("outperform", limit)
        # And the named-uncaught spellings really do pass, which is what makes the disclosure
        # true rather than decorative.
        self.assertEqual(we._gain_hits("this run outperformed the baseline"), [])


if __name__ == "__main__":
    unittest.main()
