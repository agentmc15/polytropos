"""D20 -- the evaluation workbench stays the one owner of policy persistence.

`WorkflowEvalOwnershipTests` covers what `bin/workflow_eval.py`'s proposal/review/apply/rollback
functions gained: the bundle and manifest references a proposal and an applied policy may now
name, and the migration that lets every record written before those existed keep working.

WHAT IS ACTUALLY UNDER TEST, in the order the acceptance asks it:

  * EXISTING BEHAVIOUR COMPATIBLE. Neither `PROPOSAL_VERSION` nor `POLICY_VERSION` moved -- the
    new block carries its OWN version, on the referenced object rather than on the envelope
    around it -- so a proposal file and a preference file written before D20 still read, still
    review, still apply and still roll back. They read as UNKNOWN, which is what they are, and
    nothing back-fills them. The historical preference payload, taken from D11's own fixture, is
    driven through a real rollback here.
  * ONE WRITER. The whole flow creates files under the prefs directory it was handed and nowhere
    else; the reference helpers open nothing, hash nothing and dereference nothing; and adding a
    bundle reference to the preference file does not make that file a bundle -- `parse_bundle`
    still refuses it by name and `describe_legacy_preferences` still reads it for what it is.
  * REJECTIONS RETAINED. A rejected candidate keeps its file, its status and the review that
    rejected it, and is still listed after a later proposal is applied and rolled back; every
    superseded policy version keeps its exact bytes in history.
  * NO AUTO CONSUME. Recording a reference consumes nothing: the applied file still says
    pull-only, apply never opens the manifest a proposal cites, and no driver gained a reader.
  * TEMP PREFS. Every function under test requires a prefs directory -- none of them defaults to
    the per-user store -- and every test here passes a temporary one.

THE RELAY, AND WHY IT REFUSES RATHER THAN TRIMS. `attempt_ledger.read_ref` is a projection: it
reads `id`, `sha` and `v` and ignores every other key. A relay that ran a caller's reference
through it and stored the result would silently drop whatever else was there while presenting the
record as carrying what it was given. So `_policy_ref` checks closure in both directions FIRST,
against `attempt_ledger.REF_FIELDS` read from its owner, and one test here proves the projection
really does drop an extra key before proving the relay refuses it.

`BoundedProposalTests` (D21) covers the section beside it: what the evaluator ADMITS as a
bounded candidate draft, and what `bin/improvement_loop.py` is allowed to be while asking. Five
refusals -- code, assurance, hidden, duplicate, budget -- each reached with the other four
satisfied and asserted as a refusal SET; producing no candidate kept distinct from refusing
every candidate; both bounds tripped at their limit and one past it; and the claim that nothing
here infers anything proved at runtime with every dispatch and persistence seam armed to raise,
beside a control that fires one. The loop is not a persistence owner and the proof is an
inventory: a whole run through both its CLI paths adds no file to the temporary root or to the
redirected data home.

SAFETY CONTRACT. Nothing here invokes a real `claude`/`codex`/`copilot`/`cursor`/`graphify`
binary, reads a real harness home, spends anything, or touches a real store. Every prefs
directory, evals store and manifest is built in a temporary directory; `POLYTROPOS_DATA_HOME` is
redirected for this module's run so even a mistake lands in a throwaway; every fixture is
synthetic and comes from the generator that owns its shape rather than being hand-rolled here.
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
    spec = importlib.util.spec_from_file_location(f"{name}_workbench_test", BIN_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


we = _load("workflow_eval")
rg = _load("release_gate")
al = we._al()
dc = we._dc()                     # the contract instance workflow_eval itself reads
dp = _load("decision_policy")
il = _load("improvement_loop")

# ONE EVALUATOR INSTANCE, ON PURPOSE. `bin/` is not a package, so `improvement_loop`'s own
# sibling loader would build a SECOND `workflow_eval` and a second `decision_contract` behind
# it. Two instances would make this file's patches invisible to the module under test and,
# worse, would let the armed dispatch seams below be armed on a module nothing actually calls.
# Priming the cache is the whole of the accommodation; nothing else here reaches into it.
il._MODS["workflow_eval"] = we
il._MODS["decision_policy"] = dp

#: The four functions the task names as the existing owners, plus the readers around them.
OWNER_FUNCTIONS = ("build_proposal", "review_proposal", "apply_proposal", "rollback_policy")

#: The D20 additions, as a group, for the structural sweeps.
RELAY_FUNCTIONS = ("_policy_ref", "_policy_ref_version", "policy_refs", "read_policy_refs",
                   "_relay_refs", "_ref_ids")

# ---- D21: the bounded draft section, its bounds, and the trap --------------------------------

SECTION_START = "# BOUNDED CANDIDATE DRAFTS: WHAT THIS EVALUATOR ADMITS (decision-improvement D21)"
SECTION_END = "# END OF THE BOUNDED CANDIDATE DRAFT SECTION (decision-improvement D21)"

#: Every function the D21 section is allowed to define. A new one must be added here, which is
#: how a dispatching or writing helper smuggled into the section fails this file rather than
#: sliding past the sweeps below.
SECTION_FUNCTIONS = {
    "draft_partitions", "label_vocabulary", "workflow_stages", "baseline_workflow",
    "draft_ceiling", "draft_budget", "_draft_in_force", "draft_key", "_draft_vocabulary",
    "_draft_hidden", "_draft_assurance", "_draft_verdict", "validate_draft",
    "validate_draft_batch",
}

#: Names that reach a model, a CLI, a grader or a sandbox. Neither the D21 section nor
#: `improvement_loop` may call one: the whole claim of a bounded draft is that it is produced
#: without inference.
DISPATCHING_NAMES = {
    "runner", "default_runner", "gate_protected_dispatch", "require_protected_trial",
    "run_protected_dispatch", "run_confined", "wrap_argv", "dispatch_cell", "mine_tasks",
    "mine_issue_tasks", "mine_general_tasks", "make_sandbox", "prepare_cell_sandbox",
    "build_grade_substrate", "grade_cells", "oracle_tests", "oracle_judge", "oracle_structural",
    "oracle_tests_full_patch", "build_plan", "Evaluation", "Popen", "check_output", "call",
    "system", "popen", "urlopen", "request",
}

#: Filesystem and persistence verbs. `improvement_loop` is not a persistence owner and the D21
#: section is not a writer; this is what holds both to it. `read_manifest` is deliberately
#: absent for `improvement_loop`, which is meant to read a manifest through its owner -- and
#: deliberately present for the section, which opens nothing at all.
WRITER_NAMES = {
    "open", "write_text", "write_bytes", "mkdir", "unlink", "rmtree", "replace", "touch",
    "write_envelope", "write_manifest", "write_proposal", "build_proposal", "review_proposal",
    "apply_proposal", "rollback_policy", "record_exposure", "record_results", "declare_cohort",
    "select_cohort", "retire", "adjudicate", "_journal", "store_path", "confined_create_bytes",
    "confined_append",
}

#: Every seam on the evaluator and its `repo_bench` sibling that could reach a model, a CLI, a
#: graded sandbox -- or a stored record. Armed with a raiser for the runtime proof.
WF_SEAMS = ("default_runner", "gate_protected_dispatch", "require_protected_trial",
            "write_envelope", "write_manifest", "write_proposal", "build_proposal",
            "review_proposal", "apply_proposal", "rollback_policy", "record_exposure",
            "record_results", "declare_cohort", "select_cohort", "retire", "_journal")
RB_SEAMS = ("mine_tasks", "make_sandbox", "prepare_cell_sandbox", "build_grade_substrate",
            "grade_cells", "oracle_tests", "oracle_judge", "oracle_structural",
            "oracle_tests_full_patch", "dispatch_cell")


class _RaisingSeam:
    """A seam that RAISES if ever invoked.

    Not a mock returning a canned value: a canned return is indistinguishable from a real
    result that happened to be ignored, and it would let a leaked dispatch or a leaked write
    pass in silence. A control test calls one to prove the trap is armed rather than inert.
    """

    def __init__(self, name):
        self.name = name
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError(f"seam {self.name!r} was reached: args={args!r} kwargs={kwargs!r}")


class _ArmedSeams:
    """Arms every dispatch and persistence seam for the duration of a block."""

    def __init__(self, test):
        self.test = test
        self.saved = []
        self.seams = []

    def __enter__(self):
        for module, names in ((we, WF_SEAMS), (we._rb(), RB_SEAMS)):
            for name in names:
                if not hasattr(module, name):
                    continue
                seam = _RaisingSeam(f"{module.__name__}.{name}")
                self.saved.append((module, name, getattr(module, name)))
                self.seams.append(seam)
                setattr(module, name, seam)
        self.test.assertTrue(self.saved, "no seam was armed; the trap is not set")
        return self

    def __exit__(self, *exc):
        for module, name, original in self.saved:
            setattr(module, name, original)
        return False


def _section_functions():
    """Every `def` whose body lies inside the D21 section, as `{name: ast.FunctionDef}`."""
    lines = (BIN_DIR / "workflow_eval.py").read_text(encoding="utf-8").splitlines()
    starts = [i + 1 for i, line in enumerate(lines) if line.strip() == SECTION_START]
    ends = [i + 1 for i, line in enumerate(lines) if line.strip() == SECTION_END]
    if len(starts) != 1 or len(ends) != 1:
        raise AssertionError(f"the D21 section banners are not a single pair: {starts} {ends}")
    tree = ast.parse("\n".join(lines))
    return {n.name: n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and starts[0] < n.lineno < ends[0]}


def _loop_functions():
    """Every function `bin/improvement_loop.py` defines."""
    tree = ast.parse((BIN_DIR / "improvement_loop.py").read_text(encoding="utf-8"))
    return {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}

_DATA_HOME = None
_DATA_HOME_PATCH = None


def setUpModule():
    # Patched for THIS module's run only, following test_workflow_eval's own note: discovery
    # imports every test module before any runs, so an import-time environment write would
    # leak into every other module and the subprocesses they spawn.
    global _DATA_HOME, _DATA_HOME_PATCH
    _DATA_HOME = tempfile.TemporaryDirectory(prefix="polytropos-test-data-")
    _DATA_HOME_PATCH = mock.patch.dict(os.environ, {"POLYTROPOS_DATA_HOME": _DATA_HOME.name})
    _DATA_HOME_PATCH.start()


def tearDownModule():
    _DATA_HOME_PATCH.stop()
    _DATA_HOME.cleanup()


def _source_function(name):
    tree = ast.parse((BIN_DIR / "workflow_eval.py").read_text(encoding="utf-8"))
    return next(node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == name)


def _called_names(node):
    """Every plain and attribute call name inside one function, for the structural sweeps."""
    out = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                out.add(child.func.id)
            elif isinstance(child.func, ast.Attribute):
                out.add(child.func.attr)
    return out


class WorkflowEvalOwnershipTests(unittest.TestCase):

    # ---- fixtures, every one of them from the generator that owns its shape ------------------

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="polytropos-workbench-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.prefs = self.root / "prefs"
        self.store = self.root / "evals"

    def envelope(self, **kw):
        """test_workflow_eval's own synthetic run envelope -- the shape `build_proposal` is
        already proven against there, rather than a second guess at it written here."""
        return twe.synthetic_envelope(**kw)

    def manifest(self, tasks=None):
        """A real manifest from the real builder, over test_decision_evaluation_manifest's
        synthetic pool. `build_manifest` is the owner of this shape and its digest."""
        return we.build_manifest(tem.REPO, tem.BASE, tem.pool(6, 2) if tasks is None else tasks,
                                 acceptance=tem.TEST_CMD)

    def manifest_reference(self):
        return we.manifest_ref(self.manifest())

    def bundle_reference(self):
        """D11's own bundle fixture, through D11's own reference builder. This test file never
        writes a reference by hand: a hand-written one would test this file's guess at the
        shape, and the shape is exactly what is in question."""
        return dp.bundle_ref(tpb.bundle_payload())

    def proposed(self, *, refs=True, run_id="2026-09-13-abcd"):
        """One written proposal, optionally carrying both references."""
        env = self.envelope(run_id=run_id)
        kw = {"bundle_ref": self.bundle_reference(),
              "manifest_ref": self.manifest_reference()} if refs else {}
        proposal = we.build_proposal(env, {"workflow": "kit"}, "proposer", self.prefs, **kw)
        we.write_proposal(self.prefs, proposal)
        return env, proposal

    # ==========================================================================================
    #  THE RELAY: what it accepts is exactly what its owners produce
    # ==========================================================================================

    def test_the_relay_accepts_exactly_what_its_owners_produce_and_relays_it_unchanged(self):
        """POSITIVE CONTROL. Two genuinely well-formed references, each built by the owner that
        owns it, must pass and must come back out identical. Without this, every refusal below
        would be satisfied by a relay that refused everything."""
        produced = {"bundle": self.bundle_reference(), "manifest": self.manifest_reference()}
        for slot, ref in produced.items():
            with self.subTest(slot=slot):
                relayed = we._policy_ref(ref, slot)
                self.assertEqual(relayed, ref, "a relay alters nothing it relays")
                self.assertIsNot(relayed, ref, "and hands back its own dict, not the caller's")
        block = we.policy_refs(bundle_ref=produced["bundle"], manifest_ref=produced["manifest"])
        self.assertEqual(set(block), set(we.POLICY_REFS_KEYS))
        self.assertEqual(block["v"], we.POLICY_REFS_VERSION)
        self.assertEqual(block["bundle"], produced["bundle"])
        self.assertEqual(block["manifest"], produced["manifest"])

    def test_the_accepted_key_set_is_an_exact_partition_of_the_reference_owners_fields(self):
        """Pinned to `attempt_ledger.REF_FIELDS`, which is the owner's own constant, by exact
        partition rather than by a list written out in this file -- a list here could drift from
        the owner and a test built on it would go on passing. Both real generators are checked,
        so a field either of them grows or loses fails this before it reaches the relay."""
        owner = set(al.REF_FIELDS)
        self.assertTrue(owner, "an empty owner constant would make every check below vacuous")
        for slot, ref in (("bundle", self.bundle_reference()),
                          ("manifest", self.manifest_reference())):
            with self.subTest(slot=slot):
                shared = set(ref) & owner
                uncovered = set(ref) - owner
                self.assertEqual(shared | uncovered, owner)
                self.assertEqual(shared & uncovered, set())
        # And the relay's own accepted set is that same partition, proven by behaviour: drop any
        # one owner field and it refuses; add any key at all and it refuses.
        for slot in we.POLICY_REF_SLOTS:
            base = self.bundle_reference() if slot == "bundle" else self.manifest_reference()
            for field in owner:
                short = {k: v for k, v in base.items() if k != field}
                with self.subTest(slot=slot, missing=field):
                    with self.assertRaises(we.EvalError) as cm:
                        we._policy_ref(short, slot)
                    self.assertIn(repr(field), str(cm.exception))

    def test_an_extra_key_is_refused_rather_than_dropped_the_way_read_ref_would_drop_it(self):
        """The reason closure is checked at all, demonstrated in one test: the owner's reader
        is a PROJECTION. It is shown dropping the extra key first, so the refusal that follows
        is visibly guarding against a real silent loss rather than a hypothetical one."""
        ref = self.manifest_reference()
        smuggled = dict(ref, approved_by="someone", scope="everything")
        projected = al.read_ref(smuggled)
        self.assertEqual(projected, ref, "read_ref drops what it does not read, in silence")
        with self.assertRaises(we.EvalError) as cm:
            we._policy_ref(smuggled, "manifest")
        message = str(cm.exception)
        self.assertIn("'approved_by'", message)
        self.assertIn("'scope'", message)
        self.assertIn("relayed whole or not at all", message)

    def test_a_whole_payload_is_never_accepted_where_a_pointer_is_required(self):
        """A bundle, a candidate, a preference file and a manifest all carry keys a reference
        does not, so closure refuses each of them as the shape error it is."""
        for label, payload in (("bundle payload", tpb.bundle_payload()),
                               ("candidate payload", tpb.proposal_payload()),
                               ("preference payload", tpb.preference_payload()),
                               ("manifest", self.manifest())):
            for slot in we.POLICY_REF_SLOTS:
                with self.subTest(payload=label, slot=slot):
                    with self.assertRaises(we.EvalError):
                        we._policy_ref(payload, slot)

    def test_a_preference_reference_never_becomes_a_bundle_reference(self):
        """The invariant D11 states and this record could quietly break: the pull-only
        preference file is not a bundle, and pointing at it from a proposal's bundle slot would
        promote a file nothing consumes into the thing a run pins."""
        self.assertEqual(dc.LEGACY_PREFERENCE_VERSION, we.POLICY_VERSION,
                         "the contract's name for the preference shape is still its owner's")
        pointer = al.make_ref("routing-policy", sha="a" * 64, version=we.POLICY_VERSION)
        with self.assertRaises(we.EvalError) as cm:
            we._policy_ref(pointer, "bundle")
        message = str(cm.exception)
        self.assertIn("pull-only", message)
        self.assertIn(dc.BUNDLE_VERSION, message)
        # And it is not smuggled in through the other slot either.
        with self.assertRaises(we.EvalError):
            we._policy_ref(pointer, "manifest")

    def test_each_slot_demands_its_own_owners_contract_and_neither_accepts_the_others(self):
        """The versions are READ from their owners, so there is no literal here to drift; the
        cross-slot swap proves the two are actually distinguished rather than both accepted."""
        self.assertEqual(we._policy_ref_version("bundle"), dc.BUNDLE_VERSION)
        self.assertEqual(we._policy_ref_version("manifest"), we.MANIFEST_VERSION)
        self.assertEqual(dc.BUNDLE_VERSION, dp._contract().BUNDLE_VERSION,
                         "one version string, whichever loader read it")
        self.assertNotEqual(dc.BUNDLE_VERSION, we.MANIFEST_VERSION)
        with self.assertRaises(we.EvalError):
            we._policy_ref(self.manifest_reference(), "bundle")
        with self.assertRaises(we.EvalError):
            we._policy_ref(self.bundle_reference(), "manifest")
        with self.assertRaises(we.EvalError):
            we._policy_ref_version("calibration")

    def test_a_pointer_that_pins_no_bytes_and_no_contract_is_refused(self):
        """`make_ref` permits both to be absent, because for an event's provenance absent is the
        honest record. Here the whole point of naming a bundle or a manifest is that a later
        reader can notice those bytes changing, and an unpinned pointer cannot."""
        for missing in ("sha", "v"):
            with self.subTest(missing=missing):
                ref = dict(self.manifest_reference(), **{missing: None})
                with self.assertRaises(we.EvalError) as cm:
                    we._policy_ref(ref, "manifest")
                self.assertIn(missing, str(cm.exception))
        for bad in (None, "manifest-1", 7, ["id"]):
            with self.subTest(value=bad):
                with self.assertRaises(we.EvalError):
                    we._policy_ref(bad, "manifest")
        # A pointer long enough to be a payload is refused where that bound is DEFINED, by
        # handing the owner's reader's output back to the owner's constructor. `read_ref` does
        # not enforce it, so without that round trip this would be stored.
        oversized = dict(self.manifest_reference(), sha="a" * (al.REF_PART_CHARS + 1))
        self.assertIsNotNone(al.read_ref(oversized), "read_ref itself admits it")
        with self.assertRaises(we.EvalError) as cm:
            we._policy_ref(oversized, "manifest")
        self.assertIn("attempt_ledger would make", str(cm.exception))

    def test_the_relay_reads_its_owners_constants_rather_than_keeping_a_copy(self):
        """The mirror problem, settled by making there be no mirror. Both facts the relay needs
        -- what a reference's fields ARE, and which contract each slot names -- are read from
        their owners at call time, so moving the owner moves the relay. A local literal would
        satisfy every other test in this file while silently drifting."""
        with mock.patch.object(al, "REF_FIELDS", tuple(al.REF_FIELDS) + ("origin",)):
            with self.assertRaises(we.EvalError) as cm:
                we._policy_ref(self.manifest_reference(), "manifest")
            self.assertIn("'origin'", str(cm.exception))
        with mock.patch.object(dc, "BUNDLE_VERSION", "polytropos.policy-bundle/9"):
            self.assertEqual(we._policy_ref_version("bundle"), "polytropos.policy-bundle/9")
            with self.assertRaises(we.EvalError):
                we._policy_ref(self.bundle_reference(), "bundle")
        with mock.patch.object(we, "MANIFEST_VERSION", "polytropos.eval-manifest/9"):
            self.assertEqual(we._policy_ref_version("manifest"), "polytropos.eval-manifest/9")
        # and back to normal, so nothing above leaked
        self.assertEqual(we._policy_ref_version("bundle"), dc.BUNDLE_VERSION)
        self.assertEqual(we._policy_ref(self.manifest_reference(), "manifest"),
                         self.manifest_reference())

    def test_the_relay_opens_nothing_hashes_nothing_and_dereferences_nothing(self):
        """Structural, and the honesty limit stated as a test: a relayed reference is a complete
        pointer naming the right contract, and NOT evidence that its target exists or still
        digests to that sha. If one of these functions ever grew a digest of its own, the record
        would be asserting something it had not checked -- and there would be a second
        derivation to drift from its owner's."""
        forbidden = {"open", "read_text", "write_text", "mkdir", "read_bytes", "write_bytes",
                     "_sha", "manifest_digest", "_canonical", "sha256", "read_manifest",
                     "parse_bundle", "home", "run"}
        for name in RELAY_FUNCTIONS:
            with self.subTest(function=name):
                called = _called_names(_source_function(name))
                self.assertEqual(called & forbidden, set())
        # It reaches its owners for exactly two things: what a reference is, and which contract
        # each slot names.
        self.assertIn("read_ref", _called_names(_source_function("_policy_ref")))
        self.assertIn("make_ref", _called_names(_source_function("_policy_ref")))

    # ==========================================================================================
    #  EXISTING BEHAVIOUR COMPATIBLE: the versioned migration
    # ==========================================================================================

    def test_the_block_carries_its_own_version_and_neither_stored_contract_was_bumped(self):
        """Bumping `PROPOSAL_VERSION` would make `read_proposal` refuse every stored proposal and
        bumping `POLICY_VERSION` would make every stored preference file unreadable to its own
        contract. The new version therefore lives on the referenced object."""
        self.assertNotIn(we.POLICY_REFS_VERSION, (we.PROPOSAL_VERSION, we.POLICY_VERSION,
                                                  we.EVAL_VERSION, we.MANIFEST_VERSION))
        self.assertEqual(we.policy_refs()["v"], we.POLICY_REFS_VERSION)
        # A proposal written at the current PROPOSAL_VERSION still reads; the block's version is
        # inside the record, not on it.
        _env, proposal = self.proposed()
        stored = json.loads((self.prefs / we.POLICY_PROPOSALS
                             / f"{proposal['id']}.json").read_text())
        self.assertEqual(stored["v"], we.PROPOSAL_VERSION)
        self.assertEqual(stored["refs"]["v"], we.POLICY_REFS_VERSION)
        # Registered where a reader finds every contract's current version.
        self.assertIn(("policy reference block", "workflow_eval", "POLICY_REFS_VERSION"),
                      rg.VERSION_SOURCES)
        row = next(r for r in rg.contract_versions()
                   if r["contract"] == "policy reference block")
        self.assertEqual(row["version"], we.POLICY_REFS_VERSION)
        self.assertEqual(row["owner"], "bin/workflow_eval.py")

    def test_a_proposal_written_before_the_block_existed_still_reviews_and_applies(self):
        """The migration, driven over a record with no block at all: it reads as unknown, it is
        not back-filled, and every existing step still works on it."""
        _env, proposal = self.proposed(refs=False)
        path = self.prefs / we.POLICY_PROPOSALS / f"{proposal['id']}.json"
        old = json.loads(path.read_text())
        old.pop("refs")                       # exactly what a pre-D20 file on disk looks like
        path.write_text(json.dumps(old, indent=2) + "\n")

        read = we.read_policy_refs(old)
        self.assertFalse(read["recorded"])
        self.assertEqual((read["v"], read["bundle"], read["manifest"], read["unreadable"]),
                         (None, None, None, []))

        we.review_proposal(self.prefs, proposal["id"], "reviewer", "accept")
        new, previous = we.apply_proposal(self.prefs, proposal["id"])
        self.assertIsNone(previous)
        self.assertEqual(new["version"], 1)
        self.assertEqual(new["refs"], {"v": we.POLICY_REFS_VERSION, "bundle": None,
                                       "manifest": None},
                         "unknown is written as unknown, never invented from the record")
        self.assertIn("pull-only", new["consumption"])

    def test_the_historical_preference_file_still_reads_rolls_back_and_is_not_a_bundle(self):
        """D11's own fixture for the shape this module wrote before D20, driven through a real
        rollback. Its bytes come back exactly, it reads as having no reference block, and it is
        still refused as a bundle."""
        historical = tpb.preference_payload()
        self.prefs.mkdir(parents=True)
        (self.prefs / we.POLICY_HISTORY).mkdir()
        (self.prefs / we.POLICY_HISTORY / "v3.json").write_text(
            json.dumps(historical, indent=2) + "\n")
        newer = dict(historical, version=4, defaults={"workflow": "direct"})
        (self.prefs / we.POLICY_FILE).write_text(json.dumps(newer, indent=2) + "\n")

        report = we.policy_report(self.prefs)
        self.assertEqual(report["policy"]["version"], 4)
        self.assertFalse(report["refs"]["recorded"])
        self.assertEqual(report["consumption"], "pull-only")

        restored, previous = we.rollback_policy(self.prefs)
        self.assertEqual((restored["version"], previous["version"]), (3, 4))
        self.assertEqual(json.loads((self.prefs / we.POLICY_FILE).read_text()), historical)
        self.assertTrue((self.prefs / we.POLICY_HISTORY / "v4.json").exists())

        view = dp.describe_legacy_preferences(restored)
        self.assertEqual(view.reasons, (dp.LEGACY_PREFERENCE_REASON,))
        self.assertRaises(dp._contract().ContractError, dp._contract().parse_bundle, restored)

    def test_a_block_this_writer_would_not_have_written_is_refused_not_laundered(self):
        """`read_policy_refs` degrades, because it is a reader. `apply_proposal` refuses, because
        copying an edited block into the applied policy would hand it that policy's authority."""
        _env, proposal = self.proposed()
        path = self.prefs / we.POLICY_PROPOSALS / f"{proposal['id']}.json"
        we.review_proposal(self.prefs, proposal["id"], "reviewer", "accept")

        stored = json.loads(path.read_text())
        stored["refs"]["bundle"] = dict(stored["refs"]["bundle"], approved="yes")
        path.write_text(json.dumps(stored, indent=2) + "\n")

        degraded = we.read_policy_refs(stored)
        self.assertTrue(degraded["recorded"])
        self.assertIsNone(degraded["bundle"])
        self.assertEqual(degraded["unreadable"], ["bundle"])
        self.assertIsNotNone(degraded["manifest"], "one bad slot never blanks the other")

        with self.assertRaises(we.EvalError) as cm:
            we.apply_proposal(self.prefs, proposal["id"])
        self.assertIn(proposal["id"], str(cm.exception))
        self.assertIsNone(we.read_policy(self.prefs), "and nothing was written")

        for block, needle in (("not an object", "not an object"),
                              ({"v": we.POLICY_REFS_VERSION}, "missing"),
                              ({"v": we.POLICY_REFS_VERSION, "bundle": None, "manifest": None,
                                "extra": 1}, "unknown key"),
                              ({"v": "polytropos.policy-refs/99", "bundle": None,
                                "manifest": None}, "policy-refs/99")):
            with self.subTest(block=needle):
                stored["refs"] = block
                path.write_text(json.dumps(stored, indent=2) + "\n")
                with self.assertRaises(we.EvalError) as cm:
                    we.apply_proposal(self.prefs, proposal["id"])
                self.assertIn(needle, str(cm.exception))

    def test_a_malformed_reference_refuses_the_proposal_before_any_evidence_work(self):
        """A malformed input is answered as a malformed input. The envelope here is also below
        the evidence floor, so a relay checked after the evidence would report the floor and
        never mention the reference the caller actually got wrong."""
        sparse = self.envelope(n_tasks=2)
        with self.assertRaises(we.EvalError) as cm:
            we.build_proposal(sparse, {"workflow": "kit"}, "me", self.prefs,
                              bundle_ref={"id": "b", "sha": None, "v": dc.BUNDLE_VERSION})
        self.assertIn("bundle reference", str(cm.exception))
        self.assertNotIn("evidence floor", str(cm.exception))
        self.assertFalse(self.prefs.exists(), "a refused proposal writes nothing")

    # ==========================================================================================
    #  ONE WRITER, NO AUTO CONSUME
    # ==========================================================================================

    def test_the_whole_flow_writes_only_under_the_prefs_directory_it_was_handed(self):
        """One writer, checked by inventory: propose, review, apply and roll back, then look at
        everything that appeared anywhere under the temporary root. No second store, no second
        envelope file, and in particular nothing named for a store `runtime_data` does not
        declare."""
        env, proposal = self.proposed()
        we.review_proposal(self.prefs, proposal["id"], "reviewer", "accept")
        we.apply_proposal(self.prefs, proposal["id"])
        env2 = self.envelope(run_id="2026-09-13-bbbb")
        for trial in env2["trials"]:
            trial["task_id"] = trial["task_id"].replace("task-", "other-")
        env2["holdout"]["tasks"] = [f"other-{i}" for i in range(6)]
        second = we.build_proposal(env2, {"workflow": "direct"}, "proposer", self.prefs,
                                   manifest_ref=self.manifest_reference())
        we.write_proposal(self.prefs, second)
        we.review_proposal(self.prefs, second["id"], "reviewer", "accept")
        we.apply_proposal(self.prefs, second["id"])
        we.rollback_policy(self.prefs)

        created = sorted(p.relative_to(self.root).parts[0]
                         for p in self.root.iterdir())
        self.assertEqual(created, ["prefs"], "nothing was written outside the prefs directory")
        names = sorted(p.name for p in self.prefs.iterdir())
        self.assertEqual(names, sorted([we.POLICY_FILE, we.POLICY_HISTORY, we.POLICY_PROPOSALS,
                                        we.POLICY_JOURNAL]))
        self.assertNotIn("replay", [p.name for p in self.root.rglob("*")])

    def test_every_owner_function_requires_a_prefs_directory(self):
        """Temp prefs, guaranteed at the library level rather than by test discipline: none of
        these can be called without naming a directory, so none of them can silently reach the
        per-user store. The CLI is the only place a default is supplied."""
        for name in OWNER_FUNCTIONS + ("policy_report", "read_policy", "policy_base",
                                       "write_proposal", "read_proposal"):
            with self.subTest(function=name):
                parameter = inspect.signature(getattr(we, name)).parameters["prefs_dir"]
                self.assertIs(parameter.default, inspect.Parameter.empty)
        source = (BIN_DIR / "workflow_eval.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        for name in OWNER_FUNCTIONS + RELAY_FUNCTIONS:
            with self.subTest(function=name):
                fn = next(n for n in ast.walk(tree)
                          if isinstance(n, ast.FunctionDef) and n.name == name)
                named = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
                self.assertEqual(named & {"DEFAULT_PREFS_DIR", "DEFAULT_STORE_DIR"}, set())

    def test_recording_a_reference_consumes_nothing_and_opens_nothing(self):
        """No auto consume. Applying a proposal that cites a manifest does not open the manifest,
        does not make the preference file executable policy, and does not give any driver a
        reason to read it."""
        _env, proposal = self.proposed()
        we.review_proposal(self.prefs, proposal["id"], "reviewer", "accept")
        with mock.patch.object(we, "read_manifest",
                               side_effect=AssertionError("apply dereferenced the manifest")):
            new, _previous = we.apply_proposal(self.prefs, proposal["id"])
        self.assertEqual(new["refs"]["manifest"], self.manifest_reference())
        self.assertIn("pull-only", new["consumption"])
        # The applied file now names a bundle. It is still not a bundle.
        self.assertTrue(dp._contract().is_legacy_preference_payload(new))
        self.assertRaises(dp._contract().ContractError, dp._contract().parse_bundle, new)
        view = dp.describe_legacy_preferences(new)
        self.assertEqual(view.reasons, (dp.LEGACY_PREFERENCE_REASON,))
        # And no driver reads it, exactly as before this record grew a reference.
        for driver in ("claude_execute", "copilot_execute", "cursor_execute", "codex_execute"):
            text = (BIN_DIR / f"{driver}.py").read_text(encoding="utf-8")
            self.assertNotIn(we.POLICY_FILE, text)
            self.assertNotIn("read_policy", text)
            self.assertNotIn("POLICY_REFS_VERSION", text)

    def test_an_accepting_review_says_what_it_actually_checked(self):
        """A name in a JSON field is a name. The record says so, in the review entry and in the
        label the applied policy carries, rather than leaving a reader to read authority into
        the presence of a reviewer."""
        _env, proposal = self.proposed()
        reviewed = we.review_proposal(self.prefs, proposal["id"], "reviewer", "accept",
                                      note="read the evidence")
        entry = reviewed["reviews"][-1]
        self.assertEqual(entry["authority"], we.REVIEW_AUTHORITY)
        self.assertEqual(entry["authority"], "name-only")
        new, _previous = we.apply_proposal(self.prefs, proposal["id"])
        self.assertIn(we.REVIEW_AUTHORITY_LABEL, new["labels"])
        self.assertIn("not authentication", we.REVIEW_AUTHORITY_LABEL)
        self.assertEqual(we.policy_report(self.prefs)["review_authority"],
                         we.REVIEW_AUTHORITY_LABEL)
        with self.assertRaises(we.EvalError):
            we.review_proposal(self.prefs, proposal["id"], "", "accept")

    # ==========================================================================================
    #  REJECTIONS RETAINED
    # ==========================================================================================

    def test_a_rejected_candidate_and_every_old_version_stay_inspectable(self):
        """Neither an apply nor a rollback erases the evidence of what was refused."""
        _env, rejected = self.proposed(refs=False)
        we.review_proposal(self.prefs, rejected["id"], "reviewer", "reject",
                           note="the cohort is too narrow")

        env2 = self.envelope(run_id="2026-09-13-bbbb")
        for trial in env2["trials"]:
            trial["task_id"] = trial["task_id"].replace("task-", "other-")
        env2["holdout"]["tasks"] = [f"other-{i}" for i in range(6)]
        accepted = we.build_proposal(env2, {"workflow": "direct"}, "proposer", self.prefs,
                                     manifest_ref=self.manifest_reference())
        we.write_proposal(self.prefs, accepted)
        we.review_proposal(self.prefs, accepted["id"], "reviewer", "accept")
        first, _ = we.apply_proposal(self.prefs, accepted["id"])
        first_bytes = (self.prefs / we.POLICY_FILE).read_text()

        env3 = self.envelope(run_id="2026-09-13-cccc")
        for trial in env3["trials"]:
            trial["task_id"] = trial["task_id"].replace("task-", "third-")
        env3["holdout"]["tasks"] = [f"third-{i}" for i in range(6)]
        third = we.build_proposal(env3, {"workflow": "kit"}, "proposer", self.prefs)
        we.write_proposal(self.prefs, third)
        we.review_proposal(self.prefs, third["id"], "reviewer", "accept")
        we.apply_proposal(self.prefs, third["id"])
        we.rollback_policy(self.prefs)

        stored = json.loads((self.prefs / we.POLICY_PROPOSALS
                             / f"{rejected['id']}.json").read_text())
        self.assertEqual(stored["status"], "rejected")
        self.assertEqual([r["decision"] for r in stored["reviews"]], ["reject"])
        self.assertIn("too narrow", stored["reviews"][0]["note"])

        report = we.policy_report(self.prefs)
        rows = {row["id"]: row for row in report["proposals"]}
        self.assertEqual(sorted(rows), sorted([rejected["id"], accepted["id"], third["id"]]))
        self.assertEqual(rows[rejected["id"]]["decisions"], ["reject"])
        self.assertEqual(rows[rejected["id"]]["status"], "rejected")
        self.assertEqual(rows[rejected["id"]]["refs"],
                         {"v": we.POLICY_REFS_VERSION, "bundle": None, "manifest": None,
                          "recorded": True, "unreadable": []},
                         "a proposal that cited nothing says so; only a pre-D20 file is "
                         "`recorded: False`")
        self.assertEqual(rows[accepted["id"]]["refs"]["manifest"], self.manifest_reference())

        self.assertEqual(report["history_versions"], [1, 2])
        self.assertEqual((self.prefs / we.POLICY_FILE).read_text(), first_bytes,
                         "the rolled-back-to version is its own earlier bytes")
        self.assertEqual(json.loads(
            (self.prefs / we.POLICY_HISTORY / "v2.json").read_text())["version"], 2,
            "the version rolled back FROM is kept, references and all")

    def test_the_journal_records_which_references_each_step_moved(self):
        """The part of a rollback a later reader cannot reconstruct from the version numbers."""
        _env, proposal = self.proposed()
        we.review_proposal(self.prefs, proposal["id"], "reviewer", "accept")
        we.apply_proposal(self.prefs, proposal["id"])
        env2 = self.envelope(run_id="2026-09-13-bbbb")
        for trial in env2["trials"]:
            trial["task_id"] = trial["task_id"].replace("task-", "other-")
        env2["holdout"]["tasks"] = [f"other-{i}" for i in range(6)]
        second = we.build_proposal(env2, {"workflow": "direct"}, "proposer", self.prefs)
        we.write_proposal(self.prefs, second)
        we.review_proposal(self.prefs, second["id"], "reviewer", "accept")
        we.apply_proposal(self.prefs, second["id"])
        we.rollback_policy(self.prefs)

        lines = [json.loads(line) for line
                 in (self.prefs / we.POLICY_JOURNAL).read_text().splitlines()]
        kinds = [line["kind"] for line in lines]
        self.assertEqual(kinds, ["policy.proposed", "policy.reviewed", "policy.applied",
                                 "policy.proposed", "policy.reviewed", "policy.applied",
                                 "policy.rolled-back"])
        manifest_id = self.manifest_reference()["id"]
        self.assertEqual(lines[0]["refs"]["manifest"], manifest_id)
        self.assertEqual(lines[2]["refs"]["manifest"], manifest_id)
        self.assertEqual(lines[3]["refs"], {"bundle": None, "manifest": None})
        rolled = lines[-1]
        self.assertEqual((rolled["from_version"], rolled["to_version"]), (2, 1))
        self.assertEqual(rolled["from_refs"], {"bundle": None, "manifest": None})
        self.assertEqual(rolled["to_refs"]["manifest"], manifest_id)

    # ==========================================================================================
    #  THE CLI PATH THAT ACTUALLY USES THIS
    # ==========================================================================================

    def test_propose_reads_and_re_digests_the_manifest_before_taking_a_reference_to_it(self):
        """The one production caller: `workflow_eval.py propose --manifest`. It goes through
        `read_manifest`, which re-derives the digest and refuses a rewritten file, so the
        reference the proposal records was taken from a manifest this command opened."""
        env = self.envelope()
        run_dir = self.store / env["run_id"]
        run_dir.mkdir(parents=True)
        (run_dir / "results.json").write_text(json.dumps(env) + "\n")
        manifest = self.manifest()
        we.write_manifest(self.store, manifest)

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = we.main(["propose", "--run", env["run_id"], "--set", "workflow=kit",
                            "--by", "proposer", "--manifest", manifest["id"],
                            "--store-dir", str(self.store), "--prefs-dir", str(self.prefs)])
        self.assertIn(f"manifest={manifest['id']}", out.getvalue())
        self.assertEqual(code, 0)
        written = json.loads(next((self.prefs / we.POLICY_PROPOSALS).glob("*.json")).read_text())
        self.assertEqual(written["refs"]["manifest"], we.manifest_ref(manifest))
        self.assertIsNone(written["refs"]["bundle"],
                          "no bundle store exists to read one from, so none is invented")

        path = self.store / we.MANIFEST_DIR / f"{manifest['id']}.json"
        tampered = json.loads(path.read_text())
        tampered["content"]["rules"]["allocation"]["audit"] += 1
        path.write_text(json.dumps(tampered, indent=2, sort_keys=True) + "\n")
        with self.assertRaises(we.EvalError) as cm:
            we.cmd_propose(we.build_parser().parse_args(
                ["propose", "--run", env["run_id"], "--set", "policy=adaptive",
                 "--by", "proposer", "--manifest", manifest["id"],
                 "--store-dir", str(self.store), "--prefs-dir", str(self.prefs)]))
        self.assertIn("rewritten", str(cm.exception))

    # ==========================================================================================
    #  PHASE 5 REVIEW, F5: TEXT THAT BECOMES A FILENAME IS TEXT THAT CAN NAME A PATH
    # ==========================================================================================

    def traversing_proposal(self, pid):
        """A real proposal from the real builder, with only its id replaced. The id is the only
        thing under test, so nothing else about the record is hand-written."""
        proposal = we.build_proposal(self.envelope(), {"workflow": "kit"}, "proposer", self.prefs)
        return dict(proposal, id=pid)

    def test_write_proposal_refuses_an_id_that_can_leave_the_prefs_directory(self):
        """`paths["proposals"] / f"{proposal['id']}.json"` is a hand-composed destination path
        into a CALLER-SELECTED root, which the repo invariant sends through `bin/safe_paths.py`.
        `write_approval` next door had the same shape and the same escape; `swap_activation`, one
        commit later in the same phase, is the answer this follows -- `validate_id` first,
        because text that becomes a filename is text that can name a path."""
        outside = self.root / "OUTSIDE"
        for bad in ("../../OUTSIDE/pwned", "/etc/pwned", "..", ".hidden", "a/b", ""):
            with self.subTest(id=bad):
                with self.assertRaises(we._sp().SafePathError) as raised:
                    we.write_proposal(self.prefs, self.traversing_proposal(bad))
                self.assertIn("safe identifier", str(raised.exception))
        self.assertFalse(outside.exists(), "a write escaped the prefs directory")
        # POSITIVE CONTROL: the ids `build_proposal` actually mints are accepted.
        _env, proposal = self.proposed()
        self.assertTrue(proposal["id"].startswith("prop-"))
        self.assertEqual(we.read_proposal(self.prefs, proposal["id"])["id"], proposal["id"])

    def test_read_and_review_proposal_refuse_a_traversing_id(self):
        """`review_proposal` READS and WRITES BACK from its `--proposal` CLI argument, so it is
        the one of the pair that could both disclose a file and overwrite one. Both halves are
        closed, and the write-back reuses the validated id rather than the caller's string."""
        planted = self.root / "secret.json"
        planted.write_text(json.dumps({"v": we.PROPOSAL_VERSION, "id": "secret",
                                       "status": "proposed", "reviews": []}) + "\n")
        before = planted.read_text()
        (self.prefs / we.POLICY_PROPOSALS).mkdir(parents=True)
        for bad in ("../../secret", "/etc/passwd", ".."):
            with self.subTest(id=bad):
                with self.assertRaises(we._sp().SafePathError):
                    we.read_proposal(self.prefs, bad)
                with self.assertRaises(we._sp().SafePathError):
                    we.review_proposal(self.prefs, bad, "alex", "accept")
        self.assertEqual(planted.read_text(), before, "the planted file was rewritten")
        # POSITIVE CONTROL: a real id still reviews, so neither guard refuses everything.
        _env, proposal = self.proposed()
        reviewed = we.review_proposal(self.prefs, proposal["id"], "alex", "accept")
        self.assertEqual(reviewed["status"], "accepted")


class BoundedProposalTests(unittest.TestCase):
    """D21 -- what the evaluator admits as a bounded draft, and what `bin/improvement_loop.py`
    is allowed to be while asking it.

    THE FIVE REFUSALS. `code`, `assurance`, `hidden`, `duplicate` and `budget`, each reached
    with the other four SATISFIED, and asserted as the refusal SET of a batch rather than as
    "something was refused". Beside each one is the same payload with only the offending field
    corrected, which is admitted: a guard that fires on everything has not been shown to fire on
    anything in particular.

    NO-CANDIDATE IS A RESULT. A search that proposes nothing is a successful outcome and is kept
    distinct from a batch where everything was refused, so an empty run can neither read as a
    clean review nor as a failure. Every refusal test asserts how many candidates were examined,
    so an empty batch can never stand in for a real one.

    NO INFERENCE. Every dispatch seam on the evaluator and its `repo_bench` sibling -- plus
    every persistence seam, because this module is not a persistence owner either -- is armed
    with a raiser for a whole drafting run, and a control test calls one to prove the trap is
    armed rather than inert. The structural half sweeps both the D21 section and every function
    in `improvement_loop` for dispatching and writing names, and for a parameter through which a
    dispatcher could be handed in.

    ONE OWNER. The loop writes nothing: a full run through both its CLI paths is inventoried
    against the temporary root and the redirected data home, and neither gains a file.
    """

    # ---- fixtures, from the generator that owns each shape ------------------------------------

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="polytropos-drafts-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.store = self.root / "evals"

    def draft(self, **over):
        """D11's own candidate fixture. Its diff is a boolean dial, its partition is promotion
        and its statements are three different sentences, so it is admitted as it stands."""
        return tpb.proposal_payload(**over)

    def other_draft(self, **over):
        """A second ADMISSIBLE draft, distinct from `draft()` in the dial it turns."""
        kw = {"id": "cand-context-files-1", "diff": {"recovery.contract_context_files": 6}}
        kw.update(over)
        return tpb.proposal_payload(**kw)

    def evaluation(self, **over):
        payload = {"endpoint": "accepted-recovery", "partition": "promotion",
                   "manifest_ref": tpb.ref("manifest-1", we.MANIFEST_VERSION)}
        payload.update(over)
        return payload

    def manifest(self):
        """A real manifest whose promotion partition is not empty, from the real builder."""
        return we.build_manifest(tem.REPO, tem.BASE, tem.pool(12, 2), acceptance=tem.TEST_CMD)

    def bundle(self, **over):
        return tpb.bundle_payload(**over)

    def batch(self, drafts, *, in_force=None, **kw):
        return we.validate_draft_batch(drafts, in_force={} if in_force is None else in_force,
                                       **kw)

    def only(self, report):
        """The single row of a one-draft batch, with the batch's own bookkeeping asserted so an
        empty batch can never be mistaken for one that examined something."""
        self.assertIn(report["outcome"], we.DRAFT_OUTCOMES)
        self.assertEqual(report["drafts"], len(report["candidates"]))
        self.assertEqual(len(report["candidates"]), 1)
        return report["candidates"][0]

    # ==========================================================================================
    #  THE POSITIVE CONTROL, AND THE FIVE REFUSALS AS A SET
    # ==========================================================================================

    def test_a_well_formed_draft_is_admitted_and_comes_back_whole(self):
        """POSITIVE CONTROL. Without it every refusal below would be satisfied by a validator
        that refused everything, and the over-broad versions of these guards -- a hidden check
        that rejects any partition, an assurance check that rejects any workflow change -- would
        all still pass. D11's own generator produces the payload, so what is under test is the
        code and not this file's guess at the shape."""
        payload = self.draft()
        report = self.batch([payload])
        row = self.only(report)
        self.assertEqual((row["verdict"], row["reason"]), ("valid", None))
        self.assertEqual(report["outcome"], "candidates")
        self.assertEqual(report["refusals"], [])
        self.assertEqual((report["examined"], len(report["admitted"])), (1, 1))
        self.assertIs(row["payload"], payload, "the draft is carried, never rebuilt")
        self.assertEqual(row["id"], payload["id"])
        self.assertTrue(row["key"])

    def test_each_of_the_five_refusals_is_reachable_with_the_other_four_satisfied(self):
        """THE ANTI-MASKING TEST. One batch per refusal, each built from an ADMISSIBLE draft
        with exactly one thing wrong, so the refusal set is a single code every time -- a guard
        that only ever fired beside another would show up here as a set of two. The union is
        pinned against `DRAFT_REFUSALS` so a sixth code cannot appear unannounced and a fifth
        cannot quietly become unreachable."""
        marker = ("The ANSWER-KEY beside the held-out cohort already shows which of these "
                  "attempts the oracle accepted before any of them ran.")
        cases = {
            # code: a banned executable field, with everything else admissible
            "code": ([self.draft(diff={"command": "pytest -x"})], {}),
            # assurance: a real dial, a real value, and it removes the review stage
            "assurance": ([self.draft(diff={"routing.default_workflow": "direct"})],
                          {"in_force": {"routing.default_workflow": "reviewed"}}),
            # hidden: the single-use final audit nominated as the candidate's own evaluation
            "hidden": ([self.draft(evaluation=self.evaluation(partition="audit"))], {}),
            # duplicate: one change, two wordings
            "duplicate": ([self.draft(), self.draft(id="cand-restated-1", hypothesis=marker
                                                    .replace("ANSWER-KEY", "reference set"))],
                          {}),
            # budget: two admissible drafts under a ceiling of one
            "budget": ([self.draft(), self.other_draft()],
                       {"budget": we.draft_budget(max_candidates=1)}),
        }
        seen = set()
        for reason, (drafts, kw) in cases.items():
            with self.subTest(reason=reason):
                report = self.batch(drafts, **kw)
                self.assertEqual(report["refusals"], [reason],
                                 f"{reason} did not fire alone: {report['refusals']}")
                self.assertEqual(report["examined"], len(drafts),
                                 "every draft in this case must actually have been looked at")
                self.assertEqual(len(report["refused"]), 1)
                seen.add(reason)
        self.assertEqual(sorted(seen), sorted(we.DRAFT_REFUSALS),
                         "every declared refusal is reachable and no other one exists")

    def test_correcting_the_one_offending_field_admits_each_refused_draft(self):
        """The other half of the anti-masking argument: each refused payload above differs from
        an ADMITTED one in exactly the field the refusal names. Without this, an over-broad
        guard would look identical to a correct one."""
        pairs = (
            (self.draft(diff={"command": "pytest -x"}),
             self.draft(diff={"recovery.contract_context_package": True})),
            (self.draft(diff={"routing.default_workflow": "direct"}),
             self.draft(diff={"routing.default_workflow": "reviewed"})),
            (self.draft(evaluation=self.evaluation(partition="audit")),
             self.draft(evaluation=self.evaluation(partition="promotion"))),
        )
        for bad, good in pairs:
            with self.subTest(diff=bad["diff"], partition=bad["evaluation"]["partition"]):
                self.assertEqual(self.only(self.batch([bad]))["verdict"], "refused")
                self.assertEqual(self.only(self.batch([good]))["verdict"], "valid")

    # ==========================================================================================
    #  CODE: not a data change this surface can make
    # ==========================================================================================

    def test_code_refuses_an_executable_field_a_key_off_the_allowlist_and_an_unrunnable_value(self):
        """Three routes into one refusal, and the third is the one this module OWNS: D11's
        allowlist checks that a label is a well-formed label and says in as many words that the
        VALUES belong to the owning surface's vocabulary. `routing.default_workflow` names a
        workflow only this evaluator runs, so a value naming nothing is only detectable here."""
        for label, diff, needle in (
                ("executable field", {"command": "pytest -x"}, "allowlist refused"),
                ("authority field", {"skip_review": True}, "allowlist refused"),
                ("off the allowlist", {"skills.entrypoint": "x"}, "allowlist refused"),
                ("wrong kind", {"recovery.contract_context_files": "4"}, "allowlist refused"),
                ("unrunnable workflow", {"routing.default_workflow": "yolo"},
                 "names nothing this evaluator runs"),
                ("unrunnable policy", {"routing.default_policy": "assured"},
                 "names nothing this evaluator runs")):
            with self.subTest(case=label):
                row = self.only(self.batch([self.draft(diff=diff)]))
                self.assertEqual((row["verdict"], row["reason"]), ("refused", "code"))
                self.assertIn(needle, row["detail"])

    def test_a_label_dial_with_no_vocabulary_here_is_refused_rather_than_admitted(self):
        """UNKNOWN MEANS NO. If the contract grows a label dial this evaluator has no vocabulary
        for, a draft setting it is refused -- not waved through on the allowlist's word. The
        allowlist says the key may be set; only this module can say whether the VALUE names
        anything, and a value it cannot judge has not been judged."""
        with mock.patch.dict(dc.DIFF_PARAMETERS, {"routing.default_shape": "label"}):
            row = self.only(self.batch([self.draft(diff={"routing.default_shape": "swarm"})]))
            self.assertEqual((row["verdict"], row["reason"]), ("refused", "code"))
            self.assertIn("owns no vocabulary", row["detail"])
        with self.assertRaises(we.EvalError):
            we.label_vocabulary("routing.default_shape")

    def test_the_label_vocabularies_are_this_modules_own_tuples_and_cover_every_label_dial(self):
        """No mirror: both vocabularies are the tuples a run is actually routed by, read at call
        time. A list written out here could drift from them and this test would go on passing,
        so the coverage check is an exact partition of the allowlist instead -- and the workflow
        vocabulary is proven to follow BOTH tuples it is built from, in both directions."""
        self.assertEqual(we.label_vocabulary("routing.default_workflow"), we.WORKFLOWS)
        self.assertEqual(we.label_vocabulary("routing.default_policy"), we.POLICIES)
        labels = sorted(k for k, kind in dc.DIFF_PARAMETERS.items() if kind == "label")
        self.assertTrue(labels, "an empty label set would make this check vacuous")
        for dial in labels:
            with self.subTest(dial=dial):
                self.assertTrue(we.label_vocabulary(dial))
        swarm = self.draft(diff={"routing.default_workflow": "swarm"})
        with mock.patch.object(we, "WORKFLOWS", tuple(we.WORKFLOWS) + ("swarm",)):
            self.assertNotIn("swarm", we.label_vocabulary("routing.default_workflow"))
            row = self.only(self.batch([swarm]))
            self.assertEqual(row["reason"], "code",
                             "routable in name only: WORKFLOW_STAGES has no entry, so the "
                             "assurance consequence cannot be worked out and it is not admitted")
            stages = dict(we.WORKFLOW_STAGES, swarm=("implement", "review", "check"))
            with mock.patch.object(we, "WORKFLOW_STAGES", stages):
                self.assertIn("swarm", we.label_vocabulary("routing.default_workflow"))
                self.assertEqual(self.only(self.batch([swarm]))["verdict"], "valid",
                                 "it runs every stage 'reviewed' runs, so nothing is dropped")
        self.assertNotIn("swarm", we.label_vocabulary("routing.default_workflow"))

    # ==========================================================================================
    #  HIDDEN: what a proposer is blind to
    # ==========================================================================================

    def test_hidden_refuses_the_final_audit_and_an_answer_key_in_the_drafts_own_words(self):
        marker = ("Every attempt whose ANSWER-KEY line already records the accepted outcome "
                  "recovers under this setting.")
        row = self.only(self.batch([self.draft(evaluation=self.evaluation(partition="audit"))]))
        self.assertEqual((row["verdict"], row["reason"]), ("refused", "hidden"))
        self.assertIn("audit-blind", row["detail"])
        self.assertIn("single-use", row["detail"])
        row = self.only(self.batch([self.draft(hypothesis=marker)]))
        self.assertEqual((row["verdict"], row["reason"]), ("refused", "hidden"))
        self.assertIn("ANSWER-KEY", row["detail"])
        self.assertIn("hidden-label marker", row["detail"])

    def test_the_nominable_partitions_are_derived_from_the_owners_own_table(self):
        """`draft_partitions` is computed from `PARTITION_ROLES` at call time, so a partition
        whose role changes moves with it. Both directions are checked, because a function that
        returned a constant tuple would satisfy only one of them."""
        self.assertEqual(we.draft_partitions(), ("promotion",))
        roles = {name: dict(row) for name, row in we.PARTITION_ROLES.items()}
        roles["promotion"]["single_use"] = True
        with mock.patch.object(we, "PARTITION_ROLES", roles):
            self.assertEqual(we.draft_partitions(), ())
            self.assertEqual(self.only(self.batch([self.draft()]))["reason"], "hidden")
        roles = {name: dict(row) for name, row in we.PARTITION_ROLES.items()}
        roles["audit"]["single_use"] = False
        with mock.patch.object(we, "PARTITION_ROLES", roles):
            self.assertEqual(we.draft_partitions(), ("promotion", "audit"))
            row = self.only(self.batch(
                [self.draft(evaluation=self.evaluation(partition="audit"))]))
            self.assertEqual(row["verdict"], "valid")

    # ==========================================================================================
    #  ASSURANCE: a candidate may raise a check and never remove one
    # ==========================================================================================

    def test_assurance_refuses_dropping_a_stage_and_admits_adding_one(self):
        """A workflow IS a set of steps -- `WORKFLOW_STAGES` says which -- so a default that
        drops one is a proposal to stop doing it. Adding one is admitted, which is what makes
        this a direction check rather than a ban on touching the dial at all."""
        cases = (("reviewed", "direct", "refused"), ("reviewed", "kit", "refused"),
                 ("kit", "direct", "refused"), ("direct", "reviewed", "valid"),
                 ("direct", "kit", "valid"), ("reviewed", "reviewed", "valid"))
        for current, proposed, expected in cases:
            with self.subTest(frm=current, to=proposed):
                row = self.only(self.batch(
                    [self.draft(diff={"routing.default_workflow": proposed})],
                    in_force={"routing.default_workflow": current}))
                self.assertEqual(row["verdict"], expected)
                if expected == "refused":
                    self.assertEqual(row["reason"], "assurance")
                    dropped = sorted(set(we.workflow_stages(current))
                                     - set(we.workflow_stages(proposed)))
                    for stage in dropped:
                        self.assertIn(repr(stage), row["detail"])

    def test_removing_the_mandatory_review_is_named_as_what_it_is(self):
        row = self.only(self.batch([self.draft(diff={"routing.default_workflow": "direct"})],
                                   in_force={"routing.default_workflow": "reviewed"}))
        self.assertIn("independent review", row["detail"])
        self.assertIn("mandatory", row["detail"])
        self.assertIn("'review'", row["detail"])

    def test_a_bundle_that_sets_no_workflow_falls_back_to_the_task_contracts_own_default(self):
        """The hole this closes: with no in-force value the first candidate to set the dial
        could set it to the workflow that runs no review, and the reduction would look like an
        addition because nobody had written the current value down. The default is READ from
        `kit_contract`, so there is no second copy of it here to drift."""
        kc = we._kc()
        self.assertEqual(we.baseline_workflow({}), kc.DEFAULT_WORKFLOW)
        row = self.only(self.batch([self.draft(diff={"routing.default_workflow": "direct"})]))
        self.assertEqual((row["verdict"], row["reason"]), ("refused", "assurance"))
        self.assertIn(repr(kc.DEFAULT_WORKFLOW), row["detail"])
        with mock.patch.object(kc, "DEFAULT_WORKFLOW", "direct"):
            self.assertEqual(we.baseline_workflow({}), "direct")
            row = self.only(self.batch(
                [self.draft(diff={"routing.default_workflow": "direct"})]))
            self.assertEqual(row["verdict"], "valid", "nothing is dropped against 'direct'")

    def test_a_task_contract_default_this_evaluator_does_not_run_refuses_to_decide(self):
        """REFUSE WHAT YOU CANNOT INSPECT. The two vocabularies overlap and are not the same.
        With no bundle value and a default this module does not run, there is no baseline, and
        guessing a correspondence would invent the very thing the check needs."""
        kc = we._kc()
        with mock.patch.object(kc, "DEFAULT_WORKFLOW", "extended"):
            with self.assertRaises(we.EvalError) as cm:
                we.baseline_workflow({})
            self.assertIn("refuses to decide", str(cm.exception))
            with self.assertRaises(we.EvalError):
                self.batch([self.draft(diff={"routing.default_workflow": "direct"})])
        self.assertEqual(we.baseline_workflow({}), kc.DEFAULT_WORKFLOW, "nothing leaked")

    def test_a_dial_with_no_assurance_consequence_is_not_refused_for_one(self):
        """The control on the assurance check: `routing.default_policy` chooses which model a
        stage runs under and adds or removes no stage, so changing it is not a reduction."""
        for value in we.POLICIES:
            with self.subTest(policy=value):
                row = self.only(self.batch([self.draft(diff={"routing.default_policy": value})]))
                self.assertEqual(row["verdict"], "valid")

    # ==========================================================================================
    #  DUPLICATE
    # ==========================================================================================

    def test_one_change_to_one_parent_is_one_proposal_however_it_is_worded(self):
        """The dedupe key is the parent and the change, not the id and not the digest of the
        whole payload -- both of which a reworded hypothesis moves."""
        first = self.draft()
        restated = self.draft(id="cand-restated-1",
                              hypothesis="Handing the callee's interface to the retry recovers "
                                         "more cross-module failures than the frozen arm does.")
        report = self.batch([first, restated])
        self.assertEqual(report["refusals"], ["duplicate"])
        self.assertEqual([r["verdict"] for r in report["candidates"]], ["valid", "refused"])
        self.assertEqual(report["candidates"][0]["key"], report["candidates"][1]["key"])
        # And the key is available to a caller, so a later batch does not re-propose it.
        again = self.batch([first], known=[report["candidates"][0]["key"]])
        self.assertEqual(self.only(again)["reason"], "duplicate")
        # A different parent is a different proposal even with an identical diff.
        other_parent = self.draft(id="cand-elsewhere-1",
                                  parent=tpb.ref("bundle-other-9", dc.BUNDLE_VERSION))
        self.assertEqual(self.only(self.batch([other_parent],
                                              known=[report["candidates"][0]["key"]]))["verdict"],
                         "valid")

    # ==========================================================================================
    #  BUDGET: a cap that cannot be reached is not a cap
    # ==========================================================================================

    def test_both_bounds_admit_at_their_limit_and_refuse_one_past_it(self):
        drafts = [self.draft(), self.other_draft()]
        at_limit = self.batch(drafts, budget=we.draft_budget(max_candidates=2, max_effort=2))
        self.assertEqual(at_limit["refusals"], [])
        self.assertEqual((len(at_limit["admitted"]), at_limit["examined"]), (2, 2))

        over_count = self.batch(drafts, budget=we.draft_budget(max_candidates=1, max_effort=2))
        self.assertEqual(over_count["refusals"], ["budget"])
        self.assertEqual((len(over_count["admitted"]), over_count["examined"]), (1, 2))
        refused = over_count["refused"][0]
        self.assertIn("ceiling of 1 candidate", refused["detail"])
        self.assertTrue(refused["examined"], "it was looked at and found valid first")

        over_effort = self.batch(drafts, budget=we.draft_budget(max_candidates=2, max_effort=1))
        self.assertEqual(over_effort["refusals"], ["budget"])
        self.assertEqual((len(over_effort["admitted"]), over_effort["examined"]), (1, 1))
        refused = over_effort["refused"][0]
        self.assertIn("effort ceiling of 1", refused["detail"])
        self.assertFalse(refused["examined"], "the ceiling is the cost of LOOKING")
        self.assertEqual(over_effort["budget"]["effort_spent"], 1)

    def test_a_caller_may_lower_a_bound_and_may_never_raise_one(self):
        """The direction is the point: a bound a caller widens on request is not a bound, and
        'candidate data cannot change budget policy' is not enforced by one that asks politely.
        """
        ceiling = we.draft_ceiling()
        self.assertEqual(we.draft_budget()["candidates"], ceiling["candidates"])
        self.assertEqual(we.draft_budget(max_effort=1)["effort"], 1)
        for kwargs in ({"max_candidates": ceiling["candidates"] + 1},
                       {"max_effort": ceiling["effort"] + 1}):
            with self.subTest(**kwargs):
                with self.assertRaises(we.EvalError) as cm:
                    we.draft_budget(**kwargs)
                self.assertIn("ceiling", str(cm.exception))
        for bad in ({"max_candidates": -1}, {"max_effort": True}, {"max_candidates": 1.5},
                    {"max_effort": "2"}):
            with self.subTest(**bad):
                self.assertRaises(we.EvalError, we.draft_budget, **bad)

    def test_the_ceiling_is_derived_from_the_allowlist_rather_than_copied_from_it(self):
        """A number written out here could drift from the allowlist it is supposed to bound and
        every other test in this file would go on passing."""
        dials = len(dc.DIFF_PARAMETERS)
        self.assertEqual(we.draft_ceiling()["candidates"], dials)
        self.assertEqual(we.draft_ceiling()["effort"], we.DRAFT_EFFORT_PER_DIAL * dials)
        with mock.patch.dict(dc.DIFF_PARAMETERS, {"routing.default_shape": "label"}):
            self.assertEqual(we.draft_ceiling()["candidates"], dials + 1)
            self.assertEqual(we.draft_budget(max_candidates=dials + 1)["candidates"], dials + 1)
        with self.assertRaises(we.EvalError):
            we.draft_budget(max_candidates=dials + 1)
        self.assertIn("never a price", we.DRAFT_EFFORT_UNIT)
        self.assertIn("effort_unit", we.draft_ceiling())

    # ==========================================================================================
    #  NO-CANDIDATE IS A RESULT, AND EVIDENCE IS RETAINED
    # ==========================================================================================

    def test_producing_no_candidate_is_a_successful_outcome_distinct_from_all_rejected(self):
        """"No applicable change" is a legitimate abstention, not a failure -- and not the same
        fact as "everything proposed was refused". Collapsing the two would let an empty search
        read as a clean review."""
        empty = self.batch([])
        self.assertEqual(empty["outcome"], "no-candidate")
        self.assertEqual((empty["drafts"], empty["examined"], empty["refusals"]), (0, 0, []))
        self.assertEqual((empty["admitted"], empty["refused"]), ([], []))

        rejected = self.batch([self.draft(diff={"command": "x"})])
        self.assertEqual(rejected["outcome"], "all-rejected")
        self.assertEqual(rejected["admitted"], [])
        self.assertNotEqual(rejected["outcome"], empty["outcome"])

        # The loop's own search reaches the same outcome by finding nothing to turn.
        report = il.run_draft({"source": "deterministic", "bundle": self.bundle(),
                               "evaluation": self.evaluation(),
                               "evidence": [tpb.ref("attempt-a", dc.CONTRACT_VERSION),
                                            tpb.ref("attempt-b", dc.CONTRACT_VERSION)],
                               "dials": []})
        self.assertEqual(report["outcome"], "no-candidate")
        self.assertEqual(report["drafts"], 0)

        # And the CLI agrees at the one place a caller would notice: finding nothing EXITS 0.
        for job, expected in (({"source": "manual", "bundle": self.bundle(), "drafts": []}, 0),
                              ({"source": "manual", "bundle": self.bundle(),
                                "drafts": [self.draft(diff={"command": "x"})]}, 3)):
            path = self.root / f"job-{expected}.json"
            path.write_text(json.dumps(job), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(il.main(["draft", "--job", str(path)]), expected)

    def test_every_refused_candidate_keeps_its_payload_and_its_reason(self):
        """A rejection that vanishes is a rejection nobody can review. The unreadable draft and
        the one the effort ceiling never reached are kept too, and each says which it is."""
        good, unreadable = self.draft(), {"v": dc.CANDIDATE_VERSION}
        unreached = self.other_draft()
        report = self.batch([good, unreadable, unreached],
                            budget=we.draft_budget(max_candidates=2, max_effort=2))
        self.assertEqual([r["verdict"] for r in report["candidates"]],
                         ["valid", "refused", "refused"])
        self.assertEqual(sorted(report["refusals"]), ["budget", "code"])
        for row, payload in zip(report["candidates"], [good, unreadable, unreached]):
            with self.subTest(id=row["id"]):
                self.assertIs(row["payload"], payload, "carried by identity, never rebuilt")
        self.assertIsNone(report["candidates"][1]["id"], "an unreadable draft has no id to take")
        self.assertFalse(report["candidates"][2]["examined"])
        self.assertEqual(len(report["refused"]), 2)

    def test_the_validator_returns_a_verdict_for_anything_and_raises_only_about_the_setup(self):
        """The two jobs kept apart. A CANDIDATE is never an exception -- refusing by raising
        would abandon the rest of the batch and lose the record of what was refused. The
        CALLER's own setup still raises, because that is not a fact about any candidate."""
        for payload in (None, "a draft", ["not", "a", "draft"], 7, {"v": "nope"}):
            with self.subTest(payload=payload):
                row = we.validate_draft(payload, in_force={})
                self.assertEqual((row["verdict"], row["reason"]), ("refused", "code"))
        for bad in ("not a mapping", ["x"], {"routing.unknown_dial": 1}):
            with self.subTest(in_force=bad):
                self.assertRaises(we.EvalError, we.validate_draft, self.draft(), in_force=bad)
        self.assertRaises(we.EvalError, we.validate_draft_batch, [], in_force={},
                          budget={"candidates": 1})

    # ==========================================================================================
    #  NO LIVE INFERENCE: the runtime proof, and its control
    # ==========================================================================================

    def test_the_seam_trap_is_armed_and_reachable(self):
        """CONTROL. Without this, every "nothing was dispatched" assertion below could be
        passing because the seams were never actually replaced."""
        with _ArmedSeams(self) as armed:
            with self.assertRaises(AssertionError):
                we.default_runner("stub")
            self.assertTrue(any(seam.calls for seam in armed.seams))
        self.assertFalse(isinstance(we.default_runner, _RaisingSeam), "restored afterwards")

    def test_a_whole_drafting_run_reaches_no_dispatching_or_storing_seam(self):
        job = {"source": "deterministic", "bundle": self.bundle(),
               "evaluation": self.evaluation(),
               "evidence": [tpb.ref("attempt-a", dc.CONTRACT_VERSION),
                            tpb.ref("attempt-b", dc.CONTRACT_VERSION)],
               "counterevidence": [tpb.ref("attempt-c", dc.CONTRACT_VERSION)]}
        with _ArmedSeams(self):
            report = il.run_draft(job)
            manual = il.run_draft({"source": "manual", "bundle": self.bundle(),
                                   "drafts": [self.draft(), self.other_draft()]})
            demo = il.run_draft(il.demo_job())
            il.render_report(demo)
        self.assertTrue(report["drafts"], "the search produced something to have dispatched for")
        self.assertEqual(len(manual["admitted"]), 2)
        self.assertEqual(demo["outcome"], "candidates")

    def test_no_function_in_the_section_or_the_loop_calls_anything_that_dispatches(self):
        """The structural half. `SECTION_FUNCTIONS` is exact, so a helper added to the section
        fails here rather than sliding past the sweep."""
        section = _section_functions()
        self.assertEqual(set(section), SECTION_FUNCTIONS)
        for name, node in sorted(section.items()):
            with self.subTest(function=name):
                called = _called_names(node)
                self.assertEqual(called & DISPATCHING_NAMES, set())
                self.assertEqual(called & WRITER_NAMES, set(),
                                 "the section opens nothing and stores nothing")
        loop = _loop_functions()
        self.assertTrue(loop)
        for name, node in sorted(loop.items()):
            with self.subTest(function=f"improvement_loop.{name}"):
                called = _called_names(node)
                self.assertEqual(called & DISPATCHING_NAMES, set())
                self.assertEqual(called & WRITER_NAMES, set(),
                                 "the loop is not a persistence owner: it reads a manifest "
                                 "through its owner and writes nothing at all")
        source = (BIN_DIR / "improvement_loop.py").read_text(encoding="utf-8")
        for banned in ("subprocess", "proc_runner", "copilot_execute", "claude_execute",
                       "codex_execute", "cursor_execute", "Path.home"):
            with self.subTest(name=banned):
                self.assertNotIn(banned, source)

    def test_the_loop_has_no_seam_through_which_a_dispatcher_could_be_passed(self):
        """A function that cannot be handed a runner cannot use one."""
        forbidden = {"runner", "dispatcher", "git_runner", "test_runner", "binary", "argv",
                     "model", "prefs_dir", "proposer"}
        checked = 0
        for name, fn in sorted(vars(il).items()):
            if not inspect.isfunction(fn) or fn.__module__ != il.__name__:
                continue
            if name == "main":
                # `main(argv)` is the CLI's own argument vector, which is what a command line
                # is. Every other function is swept, including the three `cmd_*` it reaches.
                continue
            checked += 1
            with self.subTest(function=name):
                offered = set(inspect.signature(fn).parameters) & forbidden
                self.assertEqual(offered, set(), f"{name} offers {sorted(offered)}")
        self.assertGreater(checked, 5, "nothing was swept; the filter matched no function")

    def test_the_optional_proposer_is_declared_and_is_not_wired(self):
        """Declared so a reader learns what it would have to be; not wired, so nothing here can
        reach a model. Separately budgeted and audit-blind are stated in the label rather than
        left to be inferred from silence."""
        self.assertIn("proposer", il.SOURCES)
        self.assertIs(il.PROPOSER_WIRED, False)
        with self.assertRaises(il.LoopError) as cm:
            il.run_draft({"source": "proposer", "bundle": self.bundle(), "drafts": []})
        self.assertIn("not wired", str(cm.exception))
        self.assertIn("own budget", il.PROPOSER_LABEL)
        self.assertIn("audit-blind", il.PROPOSER_LABEL)
        with mock.patch.object(il, "PROPOSER_WIRED", True):
            with self.assertRaises(il.LoopError):
                il.run_draft({"source": "manual", "bundle": self.bundle(), "drafts": []})

    # ==========================================================================================
    #  ONE OWNER: the loop stores nothing
    # ==========================================================================================

    def test_a_whole_run_through_both_cli_paths_creates_no_file_anywhere(self):
        """One owner, checked by inventory rather than by intention: the temporary root and the
        redirected data home are both listed before and after, and neither gains anything. The
        job file this test writes is the only thing that appears, and it appears before the
        run."""
        job_path = self.root / "job.json"
        job_path.write_text(json.dumps({
            "source": "deterministic", "bundle": self.bundle(),
            "evaluation": self.evaluation(),
            "evidence": [tpb.ref("attempt-a", dc.CONTRACT_VERSION),
                         tpb.ref("attempt-b", dc.CONTRACT_VERSION)]}), encoding="utf-8")
        home = Path(_DATA_HOME.name)
        before_root = sorted(p.relative_to(self.root) for p in self.root.rglob("*"))
        before_home = sorted(p.relative_to(home) for p in home.rglob("*"))

        rendered, machine = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(rendered):
            self.assertEqual(il.main(["draft", "--job", str(job_path)]), 0)
        with contextlib.redirect_stdout(machine):
            self.assertEqual(il.main(["demo", "--json"]), 0)
        self.assertIn("admitted", rendered.getvalue())
        self.assertEqual(json.loads(machine.getvalue())["outcome"], "candidates",
                         "the run really produced a report rather than nothing at all")

        self.assertEqual(sorted(p.relative_to(self.root) for p in self.root.rglob("*")),
                         before_root, "the drafting run wrote nothing under the root")
        self.assertEqual(sorted(p.relative_to(home) for p in home.rglob("*")), before_home,
                         "and nothing in the data home either")

    def test_the_section_stores_nothing_and_therefore_versions_nothing(self):
        """No new stored object means no new `*_VERSION` constant -- which matters, because one
        would need a `release_gate.VERSION_SOURCES` row and that stales two generated documents.
        A draft is not a record: the D20 proposal file is what a record of one looks like."""
        lines = (BIN_DIR / "workflow_eval.py").read_text(encoding="utf-8").splitlines()
        start = next(i + 1 for i, line in enumerate(lines) if line.strip() == SECTION_START)
        end = next(i + 1 for i, line in enumerate(lines) if line.strip() == SECTION_END)
        tree = ast.parse("\n".join(lines))
        assigned = {t.id for node in tree.body if isinstance(node, ast.Assign)
                    and start < node.lineno < end
                    for t in node.targets if isinstance(t, ast.Name)}
        self.assertTrue(assigned, "the section defines constants; this check is not vacuous")
        self.assertEqual(sorted(n for n in assigned if n.endswith("_VERSION")), [])
        self.assertNotIn("improvement_loop", [row[1] for row in rg.VERSION_SOURCES])
        self.assertNotIn("replay", [p.name for p in self.root.rglob("*")])

    def test_the_loop_reads_the_same_contract_instance_the_evaluator_judges_with(self):
        """`bin/` is not a package, so two loaders make two `ContractError`s. The loop reaches
        its contract THROUGH the evaluator, which is what keeps a refusal catchable."""
        self.assertIs(il._dc(), we._dc())
        self.assertIs(il._we(), we)

    # ==========================================================================================
    #  THE EVIDENCE SEAM: read-only, audit-blind, and it degrades
    # ==========================================================================================

    def test_the_evidence_seam_reports_what_may_be_cited_and_refuses_what_a_proposer_is_blind_to(self):
        manifest = self.manifest()
        we.write_manifest(self.store, manifest)
        state = il.prepare_evaluation(self.store, manifest["id"])
        self.assertTrue(state["ready"])
        self.assertEqual(state["manifest_ref"], we.manifest_ref(manifest))
        self.assertEqual(sorted(state["items"]),
                         sorted(manifest["content"]["partitions"]["promotion"]))
        self.assertIsNone(state["blockers"])
        for partition in ("audit", "calibration", "development"):
            with self.subTest(partition=partition):
                with self.assertRaises(il.LoopError) as cm:
                    il.prepare_evaluation(self.store, manifest["id"], partition=partition)
                self.assertIn("proposer does not read", str(cm.exception))
        with self.assertRaises(il.LoopError):
            il.prepare_evaluation(self.store, manifest["id"], partition="nowhere")

    def test_the_evidence_seam_degrades_with_its_blockers_and_still_refuses_a_rewrite(self):
        """A reader names every reason the material cannot be cited instead of raising on the
        first -- but a manifest whose bytes moved after they were written is not a fact about
        the evidence, and `read_manifest` refuses it where that check is defined."""
        manifest = self.manifest()
        we.write_manifest(self.store, manifest)
        retired = manifest["content"]["partitions"]["promotion"][0]
        we.retire(self.store, manifest, items=[retired], reason="withdrawn", by="tester")
        state = il.prepare_evaluation(self.store, manifest["id"])
        self.assertFalse(state["ready"])
        self.assertIn(retired, state["blockers"])
        self.assertEqual(state["items"], [])

        path = self.store / we.MANIFEST_DIR / f"{manifest['id']}.json"
        tampered = json.loads(path.read_text())
        tampered["content"]["rules"]["allocation"]["audit"] += 1
        path.write_text(json.dumps(tampered, indent=2, sort_keys=True) + "\n")
        with self.assertRaises(we.EvalError) as cm:
            il.prepare_evaluation(self.store, manifest["id"])
        self.assertIn("rewritten", str(cm.exception))

    # ==========================================================================================
    #  THE DETERMINISTIC SEARCH
    # ==========================================================================================

    def test_the_search_words_every_candidate_from_the_dial_it_turns(self):
        """Precise and deterministic: each candidate names its dial, the value in force and the
        value proposed, so no two are two wordings of one claim -- and running it twice produces
        the identical payloads, which is what makes a key comparison meaningful at all."""
        bundle = self.bundle(parameters={"routing.default_workflow": "direct",
                                         "recovery.contract_context_files": 4})
        kwargs = {"evaluation": self.evaluation(),
                  "evidence": [tpb.ref("attempt-a", dc.CONTRACT_VERSION),
                               tpb.ref("attempt-b", dc.CONTRACT_VERSION)]}
        drafts = il.deterministic_drafts(bundle, **kwargs)
        self.assertEqual(drafts, il.deterministic_drafts(bundle, **kwargs), "deterministic")
        self.assertTrue(drafts)
        for payload in drafts:
            with self.subTest(draft=payload["id"]):
                candidate = dc.parse_proposal(payload)       # the real parser, not a guess
                dial, value = next(iter(candidate.diff.items()))
                self.assertIn(dial, candidate.hypothesis)
                self.assertIn(json.dumps(value), candidate.hypothesis)
                self.assertIn(dial, candidate.falsification)
        keys = [we.draft_key(dc.parse_proposal(p)) for p in drafts]
        self.assertEqual(len(set(keys)), len(keys), "a search never emits one change twice")
        report = we.validate_draft_batch(drafts, in_force={"routing.default_workflow": "direct",
                                                           "recovery.contract_context_files": 4})
        self.assertEqual(report["examined"], len(drafts))
        self.assertTrue(report["admitted"], "the search is not a generator of refusals only")
        with self.assertRaises(il.LoopError):
            il.deterministic_drafts(bundle, dials=["routing.nonexistent"], **kwargs)

    def test_a_job_with_a_field_nobody_reads_is_refused_rather_than_ignored(self):
        """A field nobody reads is an instruction nobody follows, and silently dropping it is
        how a caller comes to believe a bound was applied."""
        base = {"source": "manual", "bundle": self.bundle(), "drafts": [self.draft()]}
        for over, needle in ((("approve", True), "nothing here reads"),
                             (("budget", {"max_model_calls": 4}), "the bounds are"),
                             (("budget", "none"), "must be an object"),
                             (("source", "oracle"), "source must be one of")):
            with self.subTest(field=over[0]):
                with self.assertRaises(il.LoopError) as cm:
                    il.run_draft(dict(base, **{over[0]: over[1]}))
                self.assertIn(needle, str(cm.exception))
        with self.assertRaises(il.LoopError):
            il.run_draft(dict(base, dials=["routing.default_policy"]))
        with self.assertRaises(il.LoopError):
            il.run_draft({"source": "manual", "drafts": []})


if __name__ == "__main__":
    unittest.main()
