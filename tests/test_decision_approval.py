"""D22 -- an approval binds the exact thing it approved, and binding is not authority.

`ExactApprovalTests` covers the exact-approval section of `bin/workflow_eval.py`: the six-name
lifecycle, the four hashes an approval record binds, the four ways an approval asked for is not
given, and -- the property the whole task turns on -- that mutating any bound field invalidates
the approval afterwards.

WHAT IS ACTUALLY UNDER TEST, in the order the acceptance asks it:

  * STALE / PARTIAL / SELF / SCOPE REJECT. Each of the four is reached with the other three
    SATISFIED, and what is asserted is the refusal SET rather than that some refusal happened --
    a guard that can only fire while another is already firing has never been shown to do
    anything. A positive control with nothing wrong is approved, so the four refusals are not
    satisfied by a decider that refuses everything.
  * REJECTIONS RETAINED. Every record is written whatever it decided; an approved one, a
    rejected one, an insufficient-evidence one and a scope refusal all stay on disk, stay listed
    with their reasons, and survive a later approval.
  * HASHES ARE NOT ISOLATION. Every record carries `unproven` -- three closed codes -- however
    many of its bindings re-derive; every binding row says it establishes `content-identity` and
    nothing else; the `authority` field is D20's `name-only`, READ from D20 rather than copied;
    and `promotion_eligibility` is never eligible while the confining dispatch this repository
    does not have stays unwired.
  * TEMP PREFS. Every storage function requires a prefs directory, no function in the section
    names the per-user default, and every test here passes a temporary one.
  * NO ACTIVATION. `canary`, `active`, `retired` and `rolled-back` appear nowhere in this
    vocabulary; `CONFINED_DISPATCH_WIRED` is untouched and False; the section defines no
    dispatching name and the only function in it that writes anything is `write_approval`.

THE DISTINCTION BEING DEFENDED. D20 recorded `authority: "name-only"` and said plainly that a
reviewer is a string the command was handed. Binding four correct hashes beside that name adds
INTEGRITY -- the evaluated thing is the approved thing -- and adds no authority whatever. Several
tests here exist only to stop that line being quietly crossed: the residual codes are
unconditional, the `establishes` code is the same on every row, and no record field is named
anything stronger than the check behind it.

SAFETY CONTRACT. Nothing here invokes a real `claude`/`codex`/`copilot`/`cursor`/`graphify`
binary, reads a real harness home, spends anything or touches a real store. Every prefs
directory, evals store, manifest and envelope is built in a temporary directory;
`POLYTROPOS_DATA_HOME` is redirected for this module's run so even a mistake lands in a
throwaway; and every fixture comes from the generator that owns its shape -- `build_manifest`
for the manifest, `test_workflow_eval.synthetic_envelope` for the run, D11's own
`proposal_payload` for the candidate -- rather than being hand-rolled here.
"""

import ast
import contextlib
import importlib.util
import inspect
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_decision_evaluation_manifest as tem
import test_decision_policy_bundle as tpb
import test_workflow_eval as twe

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_approval_test", BIN_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


we = _load("workflow_eval")
rg = _load("release_gate")
dc = we._dc()                     # the contract instance workflow_eval itself reads

SECTION_START = ("# EXACT APPROVAL: WHAT AN APPROVAL BINDS, AND WHAT BINDING IS NOT "
                 "(decision-improvement D22)")
SECTION_END = "# END OF THE EXACT APPROVAL SECTION (decision-improvement D22)"

#: Every function the D22 section is allowed to define. A new one must be added here, which is
#: how a dispatching or writing helper smuggled into the section fails this file rather than
#: sliding past the sweeps below.
SECTION_FUNCTIONS = {
    "candidate_digest", "envelope_digest", "_manifest_content", "partition_digest",
    "_binding_derivations", "approval_bindings", "approval_holds", "evidence_coverage",
    "_stale_findings", "_scope_findings", "_same_actor", "approval_stage", "approval_case",
    "decide_approval", "promotion_eligibility", "write_approval", "read_approval",
    "approval_report", "load_approval_case",
}

#: The one function in the section that is allowed to write anything. `write_approval` puts a
#: record under the caller's prefs directory and journals it; nothing else in the section opens,
#: creates or appends to anything at all.
SECTION_WRITERS = {"write_approval"}

#: Filesystem and persistence verbs, for the sweep above.
WRITER_NAMES = {"open", "write_text", "write_bytes", "mkdir", "unlink", "rmtree", "replace",
                "touch", "write_envelope", "write_manifest", "write_proposal", "apply_proposal",
                "rollback_policy", "record_exposure", "record_results", "declare_cohort",
                "select_cohort", "retire", "adjudicate", "_journal", "store_path",
                "confined_create_bytes", "confined_append_bytes"}

#: Names that reach a model, a CLI, a grader or a sandbox. The section may call none of them:
#: an approval is a decision taken over documents, and nothing about it runs anything.
DISPATCHING_NAMES = {
    "runner", "default_runner", "gate_protected_dispatch", "require_protected_trial",
    "run_protected_dispatch", "run_confined", "run_verify", "wrap_argv", "dispatch_cell",
    "mine_tasks", "make_sandbox", "prepare_cell_sandbox", "build_grade_substrate",
    "grade_cells", "oracle_tests", "oracle_judge", "oracle_structural", "build_plan",
    "Evaluation", "Popen", "check_output", "call", "system", "popen", "urlopen", "request",
    "run_sentinels", "home",
}

#: The runtime states this lifecycle deliberately does not have. Activation is separately gated.
ACTIVATION_STATES = ("canary", "active", "retired", "rolled-back")

#: Every seam that could reach a model, a CLI, a graded sandbox -- or a stored record written by
#: somebody else's writer. Armed with a raiser for the runtime proof.
WF_SEAMS = ("default_runner", "gate_protected_dispatch", "require_protected_trial",
            "write_envelope", "write_manifest", "write_proposal", "build_proposal",
            "review_proposal", "apply_proposal", "rollback_policy", "record_exposure",
            "record_results", "declare_cohort", "select_cohort", "retire")
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
        raise AssertionError(f"the D22 section banners are not a single pair: {starts} {ends}")
    return starts[0], ends[0], ast.parse("\n".join(lines))


def _section_functions():
    """Every `def` whose body lies inside the D22 section, as `{name: ast.FunctionDef}`."""
    start, end, tree = _section_bounds()
    return {n.name: n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and start < n.lineno < end}


def _called_names(node):
    out = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                out.add(child.func.id)
            elif isinstance(child.func, ast.Attribute):
                out.add(child.func.attr)
    return out


def _resolve(dotted):
    """`"decision_contract.parse_proposal(...).sha()"` -> the callable it names, or None.

    The point is that a `re_derived_by` string is checked against a function that EXISTS on the
    module it names, rather than being a sentence nobody can follow.
    """
    head = dotted.split("(")[0]
    module, _, attribute = head.rpartition(".")
    owner = {"workflow_eval": we, "decision_contract": dc, "exec_policy": we._ep()}.get(module)
    return getattr(owner, attribute, None) if owner is not None else None


class ExactApprovalTests(unittest.TestCase):

    # ---- fixtures, every one of them from the generator that owns its shape ------------------

    N_TASKS = 6

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="polytropos-approval-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.prefs = self.root / "prefs"
        self.store = self.root / "evals"

    def tasks(self, n=None):
        """`test_decision_evaluation_manifest`'s own task generator -- `repo_bench`'s pinned
        schema -- with one defect per task so nothing groups and every task is its own item."""
        return [tem.task(f"task-{i}", issue=i + 1,
                         statement=f"defect {i} shows up in the widget",
                         reference_patch=tem.diff(f"src/mod{i}.py", f"    old_{i}()",
                                                  f"    new_{i}()"))
                for i in range(self.N_TASKS if n is None else n)]

    def manifest(self, *, tasks=None, labels=(), allocation=None):
        """A real manifest from the real builder. The default allocation puts every group in
        `promotion`, which is what makes a complete evaluation of it expressible at all."""
        return we.build_manifest(tem.REPO, tem.BASE, self.tasks() if tasks is None else tasks,
                                 acceptance=tem.TEST_CMD,
                                 allocation={"promotion": 1} if allocation is None else allocation,
                                 labels=labels)

    def envelope(self, **kw):
        kw.setdefault("n_tasks", self.N_TASKS)
        return twe.synthetic_envelope(**kw)

    def candidate(self, manifest, **over):
        """D11's own candidate fixture, pinned to a REAL manifest through this module's own
        `manifest_ref`. Nothing here writes a reference by hand."""
        payload = tpb.proposal_payload(
            evaluation={"endpoint": "accepted-completion", "partition": "promotion",
                        "manifest_ref": we.manifest_ref(manifest)})
        payload.update(over)
        return payload

    def case(self, **over):
        """The clean case every refusal below is a single deviation from."""
        manifest = over.pop("manifest", None) or self.manifest()
        kw = {"candidate": over.pop("candidate", None) or self.candidate(manifest),
              "manifest": manifest, "partition": "promotion",
              "envelope": self.envelope(), "in_force": {}, "proposed_by": "pat"}
        kw.update(over)
        return we.approval_case(**kw)

    def scope_of(self, case):
        return dict(case["scope"])

    def decide(self, case, **kw):
        kw.setdefault("by", "alex")
        kw.setdefault("scope", self.scope_of(case))
        kw.setdefault("decision", "accept")
        return we.decide_approval(case, **kw)

    def refusals(self, record):
        return sorted({row["reason"] for row in record["refusals"]})

    # ==========================================================================================
    #  THE POSITIVE CONTROL, AND THE FOUR REFUSALS EACH REACHED ON ITS OWN
    # ==========================================================================================

    def test_a_clean_case_is_approved_and_every_binding_re_derives(self):
        """POSITIVE CONTROL, and the load-bearing one. Without it every refusal below would be
        satisfied by a decider that refuses everything and every mutation check by a comparison
        that never matches."""
        case = self.case()
        self.assertEqual(case["state"], "evaluated")
        self.assertEqual(case["stale"], [])
        self.assertTrue(case["coverage"]["complete"])
        self.assertEqual(case["coverage"]["members"], self.N_TASKS)
        record = self.decide(case)
        self.assertEqual(record["refusals"], [])
        self.assertEqual(record["state"], "approved")
        self.assertIs(record["granted"], True)
        self.assertEqual(record["from_state"], "evaluated")
        self.assertEqual(record["v"], we.APPROVAL_VERSION)
        for slot in we.APPROVAL_BINDINGS:
            with self.subTest(slot=slot):
                self.assertTrue(record["bindings"][slot]["hash"], f"{slot} bound nothing")
        docs = case["documents"]
        held = we.approval_holds(record, candidate=docs["candidate"], manifest=docs["manifest"],
                                 partition=docs["partition"], envelope=docs["envelope"])
        self.assertTrue(held["holds"])
        self.assertEqual(held["moved"], [])

    def test_each_of_the_four_refusals_is_reachable_with_the_other_three_satisfied(self):
        """The refusal SET, not that some refusal happened. Each row below deviates from the
        clean control in exactly one way, and the assertion is equality with a one-element set,
        so a guard that could only ever fire while another was already firing fails here."""
        clean = self.case()
        scope = self.scope_of(clean)
        rewritten = self.manifest(labels=("a second label over the same pool",))
        cases = {
            # Same pool, same items, different content digest: the candidate's own pin no longer
            # matches the manifest in hand, and nothing else about the case changed.
            "stale": (self.case(manifest=rewritten, candidate=self.candidate(self.manifest())),
                      {}, "rejected"),
            # A run over four of the six items in the partition.
            "partial": (self.case(envelope=self.envelope(n_tasks=4, run_id="2026-09-13-short")),
                        {}, "insufficient-evidence"),
            "self-approval": (clean, {"by": "pat"}, "rejected"),
            "scope": (clean, {"scope": dict(scope, task_classes=[])}, "rejected"),
        }
        self.assertEqual(sorted(cases), sorted(we.APPROVAL_REFUSALS),
                         "every code in the vocabulary is exercised, and only those")
        for reason, (case, kw, state) in cases.items():
            with self.subTest(refusal=reason):
                record = self.decide(case, **kw)
                self.assertEqual(self.refusals(record), [reason])
                self.assertEqual(record["state"], state)
                self.assertIs(record["granted"], False)
                self.assertTrue(record["refusals"][0]["detail"],
                                "a refusal with no detail is a refusal nobody can act on")
        # and the control, run last, so the four above cannot be passing because everything is.
        self.assertEqual(self.decide(clean)["state"], "approved")

    def test_stale_has_three_independent_entrances(self):
        """`stale` is not one check wearing three hats: the manifest can fail its own digest, or
        be a different manifest from the one the candidate pinned, or the approval can be taken
        over a partition the candidate never nominated. Each is reached alone."""
        manifest = self.manifest()
        candidate = self.candidate(manifest)
        # A document filed under an id that is not its content's digest. Its `sha` field is
        # untouched, so the candidate pinned to THIS document matches it and only the
        # document's own inconsistency is left to find.
        misfiled = json.loads(json.dumps(manifest))
        misfiled["id"] = "deadbeefdeadbeef"
        cases = {
            "not the document it claims to be":
                self.case(manifest=misfiled, candidate=self.candidate(misfiled)),
            "the evidence moved after the candidate was written":
                self.case(manifest=self.manifest(labels=("relabelled",)), candidate=candidate),
        }
        for fragment, case in cases.items():
            with self.subTest(entrance=fragment):
                self.assertEqual(len(case["stale"]), 1, case["stale"])
                self.assertIn(fragment, case["stale"][0])
                self.assertEqual(self.refusals(self.decide(case)), ["stale"])
        # The third: the candidate nominates `promotion` and this approval is over `audit`.
        both = self.manifest(allocation={"promotion": 1, "audit": 1})
        case = self.case(manifest=both, candidate=self.candidate(both), partition="audit")
        self.assertEqual(len(case["stale"]), 1)
        self.assertIn("nominates the 'promotion' partition", case["stale"][0])
        self.assertEqual(self.refusals(self.decide(case)), ["stale"])

    def test_partial_is_insufficient_evidence_and_not_a_verdict_against_the_candidate(self):
        """D15's distinction, kept: evidence too thin to score is a state of the EVIDENCE. It is
        reported under its own state name, it is not `rejected`, and it never appears while
        something else is also wrong -- then the record says everything that was wrong."""
        case = self.case(envelope=self.envelope(n_tasks=4, run_id="2026-09-13-short"))
        record = self.decide(case)
        self.assertEqual(record["state"], "insufficient-evidence")
        self.assertNotEqual(record["state"], "rejected")
        self.assertEqual(case["coverage"]["covered"], 4)
        self.assertEqual(len(case["coverage"]["missing"]), 2)
        # Thin evidence AND a scope that does not cover: two refusals, and the state falls back
        # to `rejected` rather than reporting only the evidence.
        both = self.decide(case, scope=dict(self.scope_of(case), task_classes=[]))
        self.assertEqual(self.refusals(both), ["partial", "scope"])
        self.assertEqual(both["state"], "rejected")

    def test_coverage_counts_results_and_not_declarations(self):
        """A task declared in the holdout and never run was not evaluated. The reader looks at
        TRIALS, so an envelope that claims the whole partition and has results for half of it is
        partial -- which is exactly the shape a truncated run has."""
        manifest = self.manifest()
        envelope = self.envelope()
        envelope["trials"] = [t for t in envelope["trials"] if t["task_id"] != "task-5"]
        self.assertIn("task-5", envelope["holdout"]["tasks"], "the declaration still claims it")
        coverage = we.evidence_coverage(manifest, "promotion", envelope)
        self.assertFalse(coverage["complete"])
        self.assertEqual(coverage["covered"], self.N_TASKS - 1)
        self.assertEqual(self.refusals(self.decide(self.case(manifest=manifest,
                                                             envelope=envelope))), ["partial"])

    def test_an_empty_partition_is_incomplete_rather_than_vacuously_covered(self):
        """Nothing was covered because there was nothing there. Reading that as full coverage is
        how an empty cohort becomes evidence."""
        manifest = self.manifest(allocation={"promotion": 1, "audit": 1})
        empty = next(name for name in ("development", "calibration")
                     if not manifest["content"]["partitions"][name])
        coverage = we.evidence_coverage(manifest, empty, self.envelope())
        self.assertEqual(coverage["members"], 0)
        self.assertFalse(coverage["complete"])
        self.assertIn("is empty", coverage["detail"])

    def test_self_approval_is_refused_however_the_name_is_spelled(self):
        """And the record says what that comparison IS. The structural half of the rule is the
        one that actually holds: a candidate payload cannot carry an authority field at all, so
        the approving name can never come out of the thing being approved."""
        case = self.case()
        for spelling in ("pat", "PAT", "  Pat  "):
            with self.subTest(by=spelling):
                record = self.decide(case, by=spelling)
                self.assertEqual(self.refusals(record), ["self-approval"])
                self.assertIn(we.SELF_APPROVAL_NOTE, record["refusals"][0]["detail"])
        self.assertIn("not authenticated either", we.SELF_APPROVAL_NOTE)
        # The structural half, proven against the contract rather than asserted about it.
        banned = next(name for name in dc.BANNED_FIELDS if "approv" in name.lower())
        with self.assertRaises(dc.ContractError):
            dc.parse_proposal(dict(self.candidate(self.manifest()), **{banned: "pat"}))

    def test_scope_must_cover_and_never_merely_overlap(self):
        """An approval for one project or one task class is not an approval for another. A wider
        scope than the candidate claims is fine; a narrower one approves something else."""
        case = self.case()
        scope = self.scope_of(case)
        wider = dict(scope, task_classes=sorted(set(scope["task_classes"]) | {"another-class"}))
        self.assertEqual(self.decide(case, scope=wider)["state"], "approved")
        for label, bad in (
                ("a task class dropped", dict(scope, task_classes=[])),
                ("a different project", dict(scope, project="some-other-project")),
                ("an intended use dropped", dict(scope, intended_uses=[])),
                ("a key the candidate's scope does not have",
                 dict(scope, everything="yes")),
                ("a missing key", {k: v for k, v in scope.items() if k != "project"}),
                ("no scope at all", None)):
            with self.subTest(scope=label):
                record = self.decide(case, scope=bad)
                self.assertEqual(self.refusals(record), ["scope"])
        # PARTIAL OVERLAP is the case a coverage check gets wrong: a candidate claiming two task
        # classes, approved for one of them, has been approved for something narrower than it
        # claims -- and an approval that accepted an intersection would say yes to that.
        manifest = self.manifest()
        two = self.case(manifest=manifest, candidate=self.candidate(
            manifest, scope={"project": tpb.PROJECT,
                             "task_classes": [tpb.TASK_CLASS, "recovery-single-module"],
                             "intended_uses": [tpb.USE]}))
        self.assertEqual(len(two["scope"]["task_classes"]), 2)
        half = dict(self.scope_of(two), task_classes=[tpb.TASK_CLASS])
        record = self.decide(two, scope=half)
        self.assertEqual(self.refusals(record), ["scope"])
        self.assertIn("recovery-single-module", record["refusals"][0]["detail"])
        self.assertEqual(self.decide(two, scope=self.scope_of(two))["state"], "approved")
        # The keys compared are the CONTRACT's, taken from what it parsed, not a list in here.
        parsed = dc.parse_proposal(case["documents"]["candidate"])
        self.assertEqual(sorted(case["scope"]), sorted(dict(parsed.scope)))

    # ==========================================================================================
    #  MUTATIONS INVALIDATE APPROVAL
    # ==========================================================================================

    def test_mutating_any_bound_field_invalidates_the_approval_and_names_which(self):
        """The central property. Each of the four bound objects is mutated in turn, the approval
        stops holding, and `moved` names exactly the slot that moved -- beside an unmutated
        control that still holds, without which this could be a check that always fails."""
        case = self.case()
        docs = dict(case["documents"])
        record = self.decide(case)
        self.assertIs(record["granted"], True)
        base = {"candidate": docs["candidate"], "manifest": docs["manifest"],
                "partition": "promotion", "envelope": docs["envelope"]}
        mutations = {
            "candidate": {"candidate": dict(docs["candidate"], id="cand-a-different-one")},
            "evaluation": {"manifest": self.manifest(labels=("rewritten after approval",))},
            "partition": {"partition": "audit"},
            "source": {"envelope": self.envelope(n_tasks=4, run_id="2026-09-13-short")},
        }
        self.assertEqual(sorted(mutations), sorted(we.APPROVAL_BINDINGS),
                         "every bound slot is mutated, and only those")
        for slot, mutation in mutations.items():
            with self.subTest(mutated=slot):
                held = we.approval_holds(record, **dict(base, **mutation))
                self.assertFalse(held["holds"])
                self.assertEqual(held["moved"], [slot])
                row = next(r for r in held["rows"] if r["slot"] == slot)
                self.assertNotEqual(row["bound"], row["re_derived"])
        self.assertTrue(we.approval_holds(record, **base)["holds"], "the control still holds")

    def test_a_binding_that_cannot_be_re_derived_counts_as_moved_and_not_as_unchanged(self):
        """A re-derivation that raises is the most dangerous case: read as "unchanged" it would
        turn a corrupted document into a still-valid approval."""
        case = self.case()
        record = self.decide(case)
        docs = case["documents"]
        base = {"candidate": docs["candidate"], "manifest": docs["manifest"],
                "partition": "promotion", "envelope": docs["envelope"]}
        for slot, mutation in (
                ("candidate", {"candidate": {"v": "not-a-candidate"}}),
                ("evaluation", {"manifest": "not a manifest at all"}),
                ("source", {"envelope": dict(docs["envelope"], v="polytropos.something/9")})):
            with self.subTest(broken=slot):
                held = we.approval_holds(record, **dict(base, **mutation))
                self.assertFalse(held["holds"])
                self.assertIn(slot, held["moved"])
                row = next(r for r in held["rows"] if r["slot"] == slot)
                self.assertIsNone(row["re_derived"])
                self.assertIn("could not be re-derived", row["reason"])
        # A slot that was never bound has not been shown to hold either.
        offline = self.case(envelope=None)
        rejected = self.decide(offline, decision="reject")
        held = we.approval_holds(rejected, **base)
        self.assertIn("source", held["moved"])
        self.assertIn("nothing was ever bound", next(
            r for r in held["rows"] if r["slot"] == "source")["reason"])

    def test_a_re_serialised_candidate_is_the_same_candidate(self):
        """The candidate hash is the contract's digest over the contract's normalised payload,
        not a hash of the bytes as handed in. A reordered mapping is one candidate, so a
        re-serialisation that changed nothing invalidates nothing."""
        case = self.case()
        record = self.decide(case)
        docs = case["documents"]
        shuffled = json.loads(json.dumps(
            {k: docs["candidate"][k] for k in reversed(list(docs["candidate"]))}))
        self.assertNotEqual(json.dumps(shuffled), json.dumps(docs["candidate"]))
        self.assertTrue(we.approval_holds(
            record, candidate=shuffled, manifest=docs["manifest"], partition="promotion",
            envelope=docs["envelope"])["holds"])

    # ==========================================================================================
    #  THE LIFECYCLE: SIX NAMES, AND NO ACTIVATION AMONG THEM
    # ==========================================================================================

    def test_the_lifecycle_is_the_six_canonical_names_and_carries_no_activation_state(self):
        """Canary, active, retired and rolled-back are a separately gated transition's states.
        Having them here would let something in this section look like a step towards running."""
        self.assertEqual(we.APPROVAL_STATES,
                         ("draft", "offline-valid", "evaluated", "approved", "rejected",
                          "insufficient-evidence"))
        self.assertEqual(sorted(we.APPROVAL_TRANSITIONS), sorted(we.APPROVAL_STATES))
        for state, onward in we.APPROVAL_TRANSITIONS.items():
            with self.subTest(state=state):
                self.assertEqual(sorted(set(onward) - set(we.APPROVAL_STATES)), [])
        for name in ACTIVATION_STATES:
            with self.subTest(absent=name):
                self.assertNotIn(name, we.APPROVAL_STATES)
                self.assertNotIn(name, [s for onward in we.APPROVAL_TRANSITIONS.values()
                                        for s in onward])

    def test_the_offline_valid_state_is_d21s_own_verdict_and_not_a_second_opinion(self):
        """`approval_case` asks `validate_draft` -- the D21 function that owns what this
        evaluator admits -- rather than re-deciding offline validity here. Proven by PATCHING
        that function and watching the state follow it."""
        manifest = self.manifest()
        candidate = self.candidate(manifest)
        kw = {"candidate": candidate, "manifest": manifest, "partition": "promotion"}
        self.assertEqual(we.approval_case(in_force=None, envelope=None, **kw)["state"], "draft")
        self.assertEqual(we.approval_case(in_force={}, envelope=None, **kw)["state"],
                         "offline-valid")
        self.assertEqual(we.approval_case(in_force={}, envelope=self.envelope(),
                                          **kw)["state"], "evaluated")
        refused = {"verdict": "refused", "reason": "code", "detail": "patched"}
        with mock.patch.object(we, "validate_draft", return_value=refused) as patched:
            case = we.approval_case(in_force={}, envelope=self.envelope(), **kw)
        self.assertEqual(case["state"], "rejected")
        self.assertEqual(case["draft"], refused)
        self.assertTrue(patched.called, "the stage was derived without asking D21 at all")

    def test_approval_is_reachable_only_from_evaluated_while_refusal_is_reachable_from_anywhere(self):
        """The asymmetry is the guard: a person may always say no, and may only say yes over
        something that was actually evaluated. Approving what was never evaluated is the defect
        this task exists to prevent, so it raises rather than producing a refused record."""
        manifest = self.manifest()
        candidate = self.candidate(manifest)
        kw = {"candidate": candidate, "manifest": manifest, "partition": "promotion"}
        for state, case in (
                ("draft", we.approval_case(in_force=None, envelope=None, **kw)),
                ("offline-valid", we.approval_case(in_force={}, envelope=None, **kw))):
            with self.subTest(state=state):
                self.assertEqual(case["state"], state)
                with self.assertRaises(we.EvalError) as cm:
                    self.decide(case)
                self.assertIn(f"{state!r} state cannot become 'approved'", str(cm.exception))
                refused = self.decide(case, decision="reject")
                self.assertEqual(refused["state"], "rejected")
                self.assertEqual(refused["from_state"], state)
        # and a terminal state reaches nothing at all.
        terminal = dict(self.case(), state="approved")
        for decision in ("accept", "reject"):
            with self.subTest(decision=decision), self.assertRaises(we.EvalError) as cm:
                self.decide(terminal, decision=decision)
            self.assertIn("terminal state", str(cm.exception))

    def test_a_decision_needs_a_name_and_a_word_the_vocabulary_has(self):
        case = self.case()
        for kw in ({"by": ""}, {"decision": "approve"}, {"decision": ""}):
            with self.subTest(**kw), self.assertRaises(we.EvalError):
                self.decide(case, **kw)
        with self.assertRaises(we.EvalError):
            self.decide(dict(case, state="canary"))

    # ==========================================================================================
    #  REJECTIONS RETAINED
    # ==========================================================================================

    def test_every_record_is_kept_and_listed_whatever_it_decided(self):
        """A refusal nobody can read is a refusal nobody can review. Four records with four
        different outcomes, all on disk, all listed with their reasons, and all still there
        after a later approval."""
        clean = self.case()
        scope = self.scope_of(clean)
        written = {}
        for label, record in (
                ("rejected-by-person", self.decide(clean, decision="reject", note="not yet")),
                ("self-approval", self.decide(clean, by="pat")),
                ("scope", self.decide(clean, scope=dict(scope, task_classes=[]))),
                ("partial", self.decide(self.case(
                    envelope=self.envelope(n_tasks=4, run_id="2026-09-13-short")))),
                ("approved", self.decide(clean))):
            path = we.write_approval(self.prefs, record)
            self.assertTrue(path.exists())
            written[label] = record
        report = we.approval_report(self.prefs)
        self.assertEqual(len(report["approvals"]), len(written))
        by_id = {row["id"]: row for row in report["approvals"]}
        for label, record in written.items():
            with self.subTest(record=label):
                row = by_id[record["id"]]
                self.assertEqual(row["state"], record["state"])
                self.assertEqual(row["refusals"], self.refusals(record))
                self.assertEqual(json.loads(
                    (self.prefs / we.POLICY_APPROVALS / f"{record['id']}.json").read_text()),
                    record)
        self.assertEqual(sorted(r["state"] for r in report["approvals"]),
                         sorted(["approved", "insufficient-evidence", "rejected", "rejected",
                                 "rejected"]))
        # The journal carries the same outcomes, and a reader that cannot parse a file says so
        # rather than quietly shortening the list.
        kinds = [json.loads(line)["kind"]
                 for line in (self.prefs / we.POLICY_JOURNAL).read_text().splitlines()]
        self.assertEqual(kinds, ["policy.approval"] * len(written))
        (self.prefs / we.POLICY_APPROVALS / "appr-broken.json").write_text("{not json")
        report = we.approval_report(self.prefs)
        self.assertEqual(len(report["approvals"]), len(written) + 1)
        self.assertIn("unreadable", [row["state"] for row in report["approvals"]])

    def test_a_stored_record_is_never_edited_into_a_different_one(self):
        """Retention has a second half: a record already on disk is not silently replaced. The
        same bytes twice is a no-op; different bytes under the same id is refused, so a decision
        cannot be overwritten by a later one that happened to hash to the same name."""
        record = self.decide(self.case())
        we.write_approval(self.prefs, record)
        we.write_approval(self.prefs, record)
        self.assertEqual(len(we.approval_report(self.prefs)["approvals"]), 1)
        with self.assertRaises(we.EvalError) as cm:
            we.write_approval(self.prefs, dict(record, state="approved", granted=True,
                                               refusals=[], note="edited"))
        self.assertIn("Nothing was overwritten", str(cm.exception))
        self.assertEqual(we.read_approval(self.prefs, record["id"]), record)
        # Two decisions that differ only in the scope they were taken over are two records.
        case = self.case()
        wide = dict(self.scope_of(case),
                    task_classes=sorted(set(self.scope_of(case)["task_classes"]) | {"extra"}))
        at = "2026-09-19T00:00:00+00:00"
        first = we.decide_approval(case, by="alex", scope=self.scope_of(case),
                                   decision="accept", now=at)
        second = we.decide_approval(case, by="alex", scope=wide, decision="accept", now=at)
        self.assertNotEqual(first["id"], second["id"])

    def test_a_stored_record_is_read_back_only_under_its_own_version(self):
        """The version refusal is asserted with NOTHING on disk and by its message, because the
        create-once guard beside it would otherwise refuse the same call for a different reason
        and this test would pass without the version ever being looked at -- which is what a
        mutation run caught it doing."""
        record = self.decide(self.case())
        with self.assertRaises(we.EvalError) as cm:
            we.write_approval(self.prefs, dict(record, v="polytropos.something-else/1"))
        self.assertIn(we.APPROVAL_VERSION, str(cm.exception))
        self.assertFalse((self.prefs / we.POLICY_APPROVALS).exists(),
                         "a refused write created the directory anyway")
        we.write_approval(self.prefs, record)
        self.assertEqual(we.read_approval(self.prefs, record["id"]), record)
        with self.assertRaises(FileNotFoundError):
            we.read_approval(self.prefs, "appr-nothing")
        (self.prefs / we.POLICY_APPROVALS / f"{record['id']}.json").write_text(
            json.dumps(dict(record, v="polytropos.something-else/1")))
        with self.assertRaises(we.EvalError) as cm:
            we.read_approval(self.prefs, record["id"])
        self.assertIn(we.APPROVAL_VERSION, str(cm.exception))

    # ==========================================================================================
    #  HASHES ARE NOT ISOLATION, AND BINDING IS NOT AUTHORITY
    # ==========================================================================================

    def test_a_fully_bound_approval_still_carries_every_unproven_code(self):
        """The acceptance term "hashes not isolation", from the inside. Four correct hashes do
        not discharge one residual, and the residual is machine-readable rather than prose."""
        records = [self.decide(self.case()),
                   self.decide(self.case(), decision="reject"),
                   self.decide(self.case(), by="pat")]
        for record in records:
            with self.subTest(state=record["state"]):
                self.assertEqual(record["unproven"], list(we.APPROVAL_UNPROVEN))
                for slot in we.APPROVAL_BINDINGS:
                    row = record["bindings"][slot]
                    self.assertEqual(row["does_not_establish"], list(we.APPROVAL_UNPROVEN))
                    self.assertEqual(row["establishes"], we.BINDING_ESTABLISHES)
                self.assertIn(we.NOT_ENFORCEMENT_LABEL, record["labels"])
                self.assertIn(we.BINDING_NOT_AUTHORITY_LABEL, record["labels"])
        self.assertEqual(we.BINDING_ESTABLISHES, "content-identity")
        self.assertEqual(sorted(we.APPROVAL_UNPROVEN), sorted(we.APPROVAL_UNPROVEN_NOTES))
        self.assertIn("not authentication", we.BINDING_NOT_AUTHORITY_LABEL)
        self.assertIn("never prevents it", we.NOT_ENFORCEMENT_LABEL)
        # One establishes-code across every row: a row that claimed more than content identity
        # would be the defect this section exists to avoid.
        self.assertEqual({row["establishes"] for row in records[0]["bindings"].values()},
                         {we.BINDING_ESTABLISHES})

    def test_the_authority_field_is_read_from_the_review_owner_rather_than_copied(self):
        """One answer in this file to what an authority field is worth, not two. Proven by
        patching D20's constant and watching the approval record follow it."""
        record = self.decide(self.case())
        self.assertEqual(record["authority"], we.REVIEW_AUTHORITY)
        self.assertEqual(record["authority"], "name-only")
        self.assertIn(we.REVIEW_AUTHORITY_LABEL, record["labels"])
        with mock.patch.object(we, "REVIEW_AUTHORITY", "patched-authority"):
            self.assertEqual(self.decide(self.case())["authority"], "patched-authority")

    def test_no_binding_row_names_a_function_that_does_not_exist(self):
        """`re_derived_by` is D18's device and is worth exactly as much as the name in it being
        resolvable. Every one of the four is resolved to a real callable on the module it names."""
        record = self.decide(self.case())
        for slot in we.APPROVAL_BINDINGS:
            with self.subTest(slot=slot):
                named = record["bindings"][slot]["re_derived_by"]
                self.assertTrue(named)
                self.assertTrue(callable(_resolve(named)), f"{named} resolves to nothing")

    def test_promotion_eligibility_is_never_eligible_and_names_what_is_missing(self):
        """An exactly bound, granted approval over a re-deriving case is still not promotable:
        the profile is uncertified and no dispatch path in this repository both confines and is
        ledgered. That is the correct answer, not a gap -- and it is where "no activation" is
        enforced rather than merely stated."""
        case = self.case()
        record = self.decide(case)
        verdict = we.promotion_eligibility(record, case=case)
        self.assertFalse(verdict["eligible"])
        self.assertEqual(sorted(verdict["blockers"]),
                         ["confining-dispatch-unwired", "protected-profile-uncertified"])
        rows = {row["requirement"]: row for row in verdict["requirements"]}
        self.assertTrue(rows["exact-approval"]["satisfied"])
        self.assertEqual(rows["exact-approval"]["re_derived_by"], "workflow_eval.approval_holds")
        self.assertFalse(we.CONFINED_DISPATCH_WIRED)
        self.assertEqual(rows["confining-and-ledgered-dispatch"]["re_derived_by"],
                         "workflow_eval.CONFINED_DISPATCH_WIRED")
        for name, row in rows.items():
            with self.subTest(requirement=name):
                self.assertIn("re_derived_by", row)
                if not row["satisfied"]:
                    self.assertTrue(row["reason"], "an unsatisfied row with no reason")
        self.assertEqual(verdict["unproven"], list(we.APPROVAL_UNPROVEN))
        self.assertIn(we.APPROVAL_NOT_ACTIVATION_LABEL, verdict["labels"])

    def test_eligibility_says_when_it_read_a_state_instead_of_re_deriving_one(self):
        """Phase 4's finding, applied here: a row that says `satisfied` over evidence nobody
        consulted is a name broader than its check. Without a case there is nothing to re-derive
        from, and the row says so instead of reading like the ones that did."""
        case = self.case()
        record = self.decide(case)
        bare = we.promotion_eligibility(record)
        row = next(r for r in bare["requirements"] if r["requirement"] == "exact-approval")
        self.assertIsNone(row["re_derived_by"])
        self.assertIn("READ and not", row["note"])
        self.assertIsNone(bare["holds"])
        # And with a case whose evidence has since moved, the row is unsatisfied and says which
        # binding moved -- a granted record is not enough on its own.
        moved = dict(case, documents=dict(case["documents"],
                                          manifest=self.manifest(labels=("moved since",))))
        verdict = we.promotion_eligibility(record, case=moved)
        row = next(r for r in verdict["requirements"] if r["requirement"] == "exact-approval")
        self.assertFalse(row["satisfied"])
        self.assertIn("evaluation", row["reason"])
        self.assertIn("exact-approval-missing", verdict["blockers"])

    def test_an_unverified_or_asserted_profile_establishes_no_eligibility(self):
        """The profile row is `exec_policy.certify_profile`'s verdict over a sentinel REPORT, not
        a word the caller chose: a document that simply claims to be certified is refused."""
        case = self.case()
        record = self.decide(case)
        forged = {"profile": "made-up", "backend": "none", "certified": True,
                  "required": 7, "satisfied": 7, "blocking": []}
        for label, report in (("absent", None), ("asserted", forged)):
            with self.subTest(report=label):
                verdict = we.promotion_eligibility(record, case=case, sentinel_report=report)
                row = next(r for r in verdict["requirements"]
                           if r["requirement"] == "protected-profile-certified")
                self.assertFalse(row["satisfied"])
                self.assertFalse(verdict["eligible"])
                self.assertEqual(row["re_derived_by"], "exec_policy.certify_profile")

    # ==========================================================================================
    #  NO ACTIVATION, ONE WRITER, TEMP PREFS
    # ==========================================================================================

    def test_the_section_defines_exactly_the_functions_it_is_allowed_to(self):
        found = set(_section_functions())
        self.assertEqual(found, SECTION_FUNCTIONS,
                         "a function appeared in or left the D22 section without this list "
                         "moving with it")

    def test_nothing_in_the_section_dispatches_and_only_one_function_writes(self):
        """Structural, so it holds for paths no test walked. The section's whole claim is that
        an approval is a decision taken over documents: it runs nothing, and the only thing it
        puts on disk is the record itself, under the directory the caller named."""
        writers = set()
        for name, node in sorted(_section_functions().items()):
            called = _called_names(node)
            with self.subTest(function=name):
                self.assertEqual(sorted(called & DISPATCHING_NAMES), [])
            if called & WRITER_NAMES:
                writers.add(name)
        self.assertEqual(writers, SECTION_WRITERS)
        start, end, tree = _section_bounds()
        text = "\n".join((BIN_DIR / "workflow_eval.py").read_text(
            encoding="utf-8").splitlines()[start:end - 1])
        for forbidden in ("Path.home", "subprocess", "POLYTROPOS_DATA_HOME"):
            with self.subTest(absent=forbidden):
                self.assertNotIn(forbidden, text)

    def test_the_whole_flow_writes_only_under_the_prefs_directory_it_was_handed(self):
        """One writer, checked by inventory. The evals store the case was read out of is not
        written to, no runtime pointer file appears anywhere, and in particular nothing named
        for a store `runtime_data` does not declare."""
        self.store.mkdir(parents=True)
        manifest = self.manifest()
        we.write_manifest(self.store, manifest)
        envelope = self.envelope()
        (self.store / envelope["run_id"]).mkdir(parents=True)
        we.write_envelope(self.store, envelope["run_id"], envelope)
        before = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*"))
        case = we.approval_case(candidate=self.candidate(manifest), manifest=manifest,
                                partition="promotion", envelope=envelope, in_force={},
                                proposed_by="pat")
        record = self.decide(case)
        we.write_approval(self.prefs, record)
        we.approval_report(self.prefs)
        we.promotion_eligibility(record, case=case)
        after = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*"))
        appeared = sorted(set(after) - set(before))
        self.assertEqual(appeared, sorted([
            "prefs", f"prefs/{we.POLICY_APPROVALS}",
            f"prefs/{we.POLICY_APPROVALS}/{record['id']}.json", f"prefs/{we.POLICY_JOURNAL}"]))
        self.assertNotIn(we.POLICY_FILE, [Path(p).name for p in after])
        self.assertEqual([p for p in after if "replay" in p or "pointer" in p], [])

    def test_every_storage_function_requires_a_prefs_directory(self):
        """Temp prefs guaranteed at the library level rather than by test discipline: none of
        these can be called without naming a directory, and no function in the section mentions
        the per-user default. The CLI is the only place a default is supplied."""
        for name in ("write_approval", "read_approval", "approval_report"):
            with self.subTest(function=name):
                parameter = inspect.signature(getattr(we, name)).parameters["prefs_dir"]
                self.assertIs(parameter.default, inspect.Parameter.empty)
        for name, node in sorted(_section_functions().items()):
            named = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            with self.subTest(function=name):
                self.assertEqual(named & {"DEFAULT_PREFS_DIR", "DEFAULT_STORE_DIR"}, set())

    def test_nothing_in_a_whole_flow_reaches_a_dispatch_or_another_writer(self):
        """Runtime proof beside the structural one, with every dispatch and foreign-writer seam
        armed to raise -- and a control that fires one, so the trap is not inert."""
        case = self.case()
        with _ArmedSeams(self):
            record = self.decide(case)
            we.write_approval(self.prefs, record)
            we.approval_holds(record, **{k: case["documents"][k]
                                         for k in ("candidate", "manifest", "partition",
                                                   "envelope")})
            we.promotion_eligibility(record, case=case)
            we.approval_report(self.prefs)
            with self.assertRaises(AssertionError):
                we.write_envelope(self.store, "r", {})

    def test_the_approval_record_is_registered_as_its_own_contract_version(self):
        """A new stored object carries a new version; nothing existing moved. A bump of one of
        those would make every record already written unreadable, since their readers refuse any
        `v` that is not current."""
        rows = {row["contract"]: row for row in rg.contract_versions()}
        self.assertEqual(rows["policy approval record"]["version"], we.APPROVAL_VERSION)
        self.assertEqual(rows["policy approval record"]["owner"], "bin/workflow_eval.py")
        for contract, version in (("policy proposal", "polytropos.policy-proposal/1"),
                                  ("routing policy file", "polytropos.routing-policy/1"),
                                  ("evaluation manifest", "polytropos.eval-manifest/1"),
                                  ("policy reference block", "polytropos.policy-refs/1")):
            with self.subTest(contract=contract):
                self.assertEqual(rows[contract]["version"], version)
        self.assertEqual(len({row["version"] for row in rows.values()}), len(rows),
                         "two contracts sharing a version string would make a reader guess")

    # ==========================================================================================
    #  THE PRODUCTION PATH: ORIGIN, WHERE THERE IS ANY
    # ==========================================================================================

    def _store_with(self, manifest, envelope):
        self.store.mkdir(parents=True, exist_ok=True)
        we.write_manifest(self.store, manifest)
        (self.store / envelope["run_id"]).mkdir(parents=True, exist_ok=True)
        we.write_envelope(self.store, envelope["run_id"], envelope)

    def _case_file(self, manifest, envelope, **over):
        document = {"candidate": self.candidate(manifest), "in_force": {},
                    "manifest": manifest["id"], "run": envelope["run_id"],
                    "partition": "promotion", "proposed_by": "pat"}
        document.update(over)
        path = self.root / "case.json"
        path.write_text(json.dumps(document))
        return path

    def _scope_file(self, case):
        path = self.root / "scope.json"
        path.write_text(json.dumps(self.scope_of(case)))
        return path

    def test_the_cli_path_re_derives_the_manifest_off_disk_before_binding_it(self):
        """The difference between the library entry point and this one. `load_approval_case`
        reads the manifest through `read_manifest`, which re-derives its digest and refuses a
        file rewritten since it was written -- so on this path the `evaluation` binding is taken
        from a document that was actually opened and checked."""
        manifest, envelope = self.manifest(), self.envelope()
        self._store_with(manifest, envelope)
        case_path = self._case_file(manifest, envelope)
        case = we.load_approval_case(json.loads(case_path.read_text()), self.store)
        scope_path = self._scope_file(case)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = we.main(["approve", "--case", str(case_path), "--by", "alex",
                            "--decision", "accept", "--scope", str(scope_path),
                            "--store-dir", str(self.store), "--prefs-dir", str(self.prefs)])
        self.assertEqual(code, 0)
        self.assertIn("approved", out.getvalue())
        self.assertIn(we.APPROVAL_NOT_ACTIVATION_LABEL, out.getvalue())
        stored = we.approval_report(self.prefs)["approvals"]
        self.assertEqual([row["state"] for row in stored], ["approved"])
        # Rewrite the manifest file. The next case build refuses at the read, before anything is
        # bound to it -- detection, which is all a digest ever offers.
        path = self.store / we.MANIFEST_DIR / f"{manifest['id']}.json"
        doc = json.loads(path.read_text())
        doc["content"]["repo"] = "synthetic://somewhere-else"
        path.write_text(json.dumps(doc))
        with self.assertRaises(we.EvalError) as cm:
            we.load_approval_case(json.loads(case_path.read_text()), self.store)
        self.assertIn("rewritten", str(cm.exception))

    def test_the_cli_refuses_an_approval_and_reports_it_rather_than_writing_nothing(self):
        manifest, envelope = self.manifest(), self.envelope()
        self._store_with(manifest, envelope)
        case_path = self._case_file(manifest, envelope)
        case = we.load_approval_case(json.loads(case_path.read_text()), self.store)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = we.main(["approve", "--case", str(case_path), "--by", "pat",
                            "--decision", "accept", "--scope", str(self._scope_file(case)),
                            "--store-dir", str(self.store), "--prefs-dir", str(self.prefs)])
        self.assertEqual(code, 3, "a refused approval is not a successful one")
        self.assertIn("self-approval", out.getvalue())
        self.assertEqual([row["state"] for row in we.approval_report(self.prefs)["approvals"]],
                         ["rejected"])
        listing = io.StringIO()
        with contextlib.redirect_stdout(listing):
            self.assertEqual(we.main(["approvals", "--prefs-dir", str(self.prefs)]), 0)
        self.assertIn("self-approval", listing.getvalue())
        self.assertIn(we.REVIEW_AUTHORITY_LABEL, listing.getvalue())

    def test_a_case_file_carrying_a_field_nobody_reads_is_refused(self):
        """A field nobody reads is an instruction nobody follows, and a document that decides an
        approval is the wrong place to be permissive about one."""
        manifest, envelope = self.manifest(), self.envelope()
        self._store_with(manifest, envelope)
        good = json.loads(self._case_file(manifest, envelope).read_text())
        self.assertEqual(sorted(good), sorted(we.APPROVAL_CASE_KEYS))
        for label, document in (("an unknown key", dict(good, approved_by="alex")),
                                ("no manifest", {k: v for k, v in good.items()
                                                 if k != "manifest"}),
                                ("not an object", ["candidate"])):
            with self.subTest(case=label), self.assertRaises(we.EvalError):
                we.load_approval_case(document, self.store)

    # ==========================================================================================
    #  ONE AUTHORITY PER CONCERN: EVERY VOCABULARY READ FROM ITS OWNER
    # ==========================================================================================

    def test_the_partition_vocabulary_is_read_from_its_owner_at_call_time(self):
        """`partition_digest` and `evidence_coverage` ask this module's own `PARTITIONS` table
        rather than carrying a list. Proven by patching the table and watching both follow."""
        manifest = self.manifest()
        self.assertTrue(we.partition_digest(manifest, "promotion"))
        with mock.patch.object(we, "PARTITIONS", ("development",)):
            for function, args in ((we.partition_digest, (manifest, "promotion")),
                                   (we.evidence_coverage,
                                    (manifest, "promotion", self.envelope()))):
                with self.subTest(function=function.__name__):
                    with self.assertRaises(we.EvalError) as cm:
                        function(*args)
                    self.assertIn("unknown partition", str(cm.exception))

    def test_the_candidate_hash_is_the_contracts_own_digest(self):
        """Not a second digest of the same thing: `candidate_digest` CALLS
        `CandidateProposal.sha()`, and a payload the contract refuses raises here rather than
        being bound to anything.

        Asserting the two values are equal would not be enough, and finding that out is what a
        mutation run is for: a byte-digest of the payload agrees with the contract's digest for
        every payload the contract admits, because `to_payload()` round-trips the admitted
        fields and both modules canonicalise the same way. So the read is pinned by PATCHING the
        owner's method and watching the binding follow it.
        """
        payload = self.candidate(self.manifest())
        parsed, digest = we.candidate_digest(payload)
        self.assertEqual(digest, dc.parse_proposal(payload).sha())
        self.assertEqual(parsed.id, dc.parse_proposal(payload).id)
        with mock.patch.object(dc.CandidateProposal, "sha", lambda self: "digest-from-d11"):
            self.assertEqual(we.candidate_digest(payload)[1], "digest-from-d11")
            bindings = we.approval_bindings(candidate=payload, manifest=self.manifest(),
                                            partition="promotion", envelope=self.envelope())
            self.assertEqual(bindings["candidate"]["hash"], "digest-from-d11")
        with self.assertRaises(we.EvalError) as cm:
            we.candidate_digest(dict(payload, diff={}))
        self.assertIn("nothing to bind an approval to", str(cm.exception))

    def test_the_evaluation_hash_is_the_manifests_own_digest(self):
        manifest = self.manifest()
        bindings = we.approval_bindings(candidate=self.candidate(manifest), manifest=manifest,
                                        partition="promotion", envelope=self.envelope())
        self.assertEqual(bindings["evaluation"]["hash"], manifest["sha"])
        self.assertEqual(bindings["evaluation"]["hash"],
                         we.manifest_digest(manifest["content"]))
        self.assertTrue(manifest["id"].startswith(bindings["evaluation"]["hash"][:16]))
        for bad in (None, "a manifest", {"v": we.MANIFEST_VERSION}):
            with self.subTest(manifest=bad), self.assertRaises(we.EvalError):
                we.partition_digest(bad, "promotion")

    def test_the_source_hash_is_over_the_whole_result_envelope(self):
        """Over the whole envelope, not a summary of it: an approval bound to a summary would
        not notice a trial's verdict being edited underneath it."""
        envelope = self.envelope()
        digest = we.envelope_digest(envelope)
        edited = json.loads(json.dumps(envelope))
        edited["trials"][0]["solved"] = not edited["trials"][0]["solved"]
        self.assertNotEqual(we.envelope_digest(edited), digest)
        for bad in (None, {"v": "polytropos.workflow-eval/999"}, "results"):
            with self.subTest(envelope=bad), self.assertRaises(we.EvalError):
                we.envelope_digest(bad)

    # ==========================================================================================
    #  PHASE 5 REVIEW, F2: A GATE NAMED `exact-approval` IS NOT SATISFIED BY A RECORD THAT
    #  BOUND NOTHING AND THAT NOTHING RE-DERIVED
    # ==========================================================================================

    def forged(self, **over):
        """A hand-built record, by the same name that proposed it, whose `bindings` are `None`.
        No `approval_case` and no `decide_approval` were involved: every field here is a string
        a caller chose, which is exactly what the gate must not accept as evidence."""
        row = {"v": we.APPROVAL_VERSION, "id": "appr-forged", "state": "approved",
               "granted": True, "bindings": None, "by": "mallory", "proposed_by": "mallory"}
        row.update(over)
        return row

    def exact_row(self, verdict):
        return next(r for r in verdict["requirements"] if r["requirement"] == "exact-approval")

    def test_an_approval_with_no_case_does_not_satisfy_the_exact_approval_gate(self):
        """`approval_ok = granted and (holds is None or holds['holds'])` made `holds is None` --
        "no `case` was supplied, so nothing was re-derived" -- satisfy the gate. That is
        `trial_cohort`'s Phase 4 defect in a second place: `satisfied: True` because a `granted`
        KEY was passed, the way `frozen: True` was because a `manifest` ARGUMENT was passed.

        ASSERTED ON `satisfied` AND ON THE BLOCKER SET, NEVER ON `eligible`. `eligible` is False
        here for two other reasons (the profile and the dispatch constant), and asserting on it
        is precisely how this hid for a whole phase.

        `approval_holds` already stated the rule this now applies -- "a slot that was never bound
        counts as moved" -- and `manifest_currency` in the same file says "an unmade check is not
        a passed one".
        """
        verdict = we.promotion_eligibility(self.forged())
        row = self.exact_row(verdict)
        self.assertIs(row["satisfied"], False)
        self.assertIsNone(row["re_derived_by"], "nothing re-derived it, and the row says so")
        self.assertEqual(row["blocker"], "exact-approval-not-re-derived")
        self.assertEqual(sorted(verdict["blockers"]),
                         ["confining-dispatch-unwired", "exact-approval-not-re-derived",
                          "protected-profile-uncertified"])
        self.assertIn("no case", row["reason"])
        self.assertIsNone(verdict["holds"])

    def test_a_genuinely_granted_record_also_fails_the_gate_with_no_case(self):
        """The finding is not about forgery, it is about an unmade check. A REAL record from
        `decide_approval` over a REAL case is still not evidence for this gate when the case is
        not supplied to re-derive it from: what the record says and what the objects in hand
        re-derive to are different facts."""
        case = self.case()
        record = self.decide(case)
        self.assertIs(record["granted"], True)
        bare = self.exact_row(we.promotion_eligibility(record))
        self.assertIs(bare["satisfied"], False)
        self.assertEqual(bare["blocker"], "exact-approval-not-re-derived")
        # ... and with the case, the same record satisfies it. Without this control the guard
        # above would be satisfied by a gate that refuses everything.
        supplied = self.exact_row(we.promotion_eligibility(record, case=case))
        self.assertIs(supplied["satisfied"], True)
        self.assertEqual(supplied["re_derived_by"], "workflow_eval.approval_holds")
        self.assertIsNone(supplied["blocker"])

    def test_the_two_approval_blockers_are_a_closed_vocabulary_and_mean_different_things(self):
        """"The approval was refused" and "nothing re-derived the approval" are two facts and
        the record keeps them apart, for `PROTOCOL_BLOCKERS`' own stated reason: a reader who
        could not tell them apart would read an unchecked approval as a rejected one."""
        self.assertEqual(we.PROMOTION_APPROVAL_BLOCKERS,
                         ("exact-approval-missing", "exact-approval-not-re-derived"))
        case = self.case()
        refused = self.decide(case, decision="reject")
        self.assertEqual(self.exact_row(we.promotion_eligibility(refused, case=case))["blocker"],
                         "exact-approval-missing")
        self.assertEqual(self.exact_row(we.promotion_eligibility(self.decide(case)))["blocker"],
                         "exact-approval-not-re-derived")
        for verdict in (we.promotion_eligibility(None),
                        we.promotion_eligibility(self.forged()),
                        we.promotion_eligibility(refused, case=case)):
            row = self.exact_row(verdict)
            with self.subTest(blocker=row["blocker"]):
                self.assertIn(row["blocker"], we.PROMOTION_APPROVAL_BLOCKERS)

    # ==========================================================================================
    #  PHASE 5 REVIEW, F5: TEXT THAT BECOMES A FILENAME IS TEXT THAT CAN NAME A PATH
    # ==========================================================================================

    def test_write_approval_refuses_an_id_that_can_leave_the_prefs_directory(self):
        """`paths["approvals"] / f"{record['id']}.json"` is a hand-composed destination path, and
        the repo invariant is that every write into a caller-selected root goes through
        `bin/safe_paths.py`. The demonstration was a real escape: an id of `../../OUTSIDE/pwned`
        wrote a file outside the prefs directory entirely.

        The strongest evidence that the neighbouring plain write was the bug rather than the
        precedent is one commit later in this same phase: `swap_activation` writes to this same
        store through `safe_paths.confined_create_bytes` with `validate_id` first, saying "text
        that becomes a filename is text that can name a path".
        """
        outside = self.root / "OUTSIDE"
        for bad in ("../../OUTSIDE/pwned", "/etc/pwned", "..", ".hidden", "a/b", ""):
            with self.subTest(id=bad):
                with self.assertRaises(we._sp().SafePathError) as raised:
                    we.write_approval(self.prefs, self.forged(id=bad))
                self.assertIn("safe identifier", str(raised.exception))
        self.assertFalse(outside.exists(), "a write escaped the prefs directory")
        self.assertEqual(sorted(p.name for p in self.root.rglob("*.json")), [])
        # POSITIVE CONTROL: the ids this code actually mints are accepted, so the guard is not
        # simply refusing everything.
        record = self.decide(self.case())
        self.assertTrue(record["id"].startswith("appr-"))
        path = we.write_approval(self.prefs, record)
        self.assertEqual(path.parent, self.prefs / we.POLICY_APPROVALS)
        self.assertEqual(we.read_approval(self.prefs, record["id"])["id"], record["id"])

    def test_read_approval_refuses_a_traversing_id_rather_than_reading_what_it_names(self):
        """The reader is the other half. A reader that follows `../..` out of the store is an
        arbitrary-file read through an id, and it would report whatever it found as an approval
        record of this repository's own."""
        planted = self.root / "secret.json"
        planted.write_text(json.dumps({"v": we.APPROVAL_VERSION, "id": "secret"}) + "\n")
        (self.prefs / we.POLICY_APPROVALS).mkdir(parents=True)
        for bad in ("../../secret", "/etc/passwd", ".."):
            with self.subTest(id=bad):
                with self.assertRaises(we._sp().SafePathError):
                    we.read_approval(self.prefs, bad)
        with self.assertRaises(FileNotFoundError):
            we.read_approval(self.prefs, "appr-nothing-here")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
