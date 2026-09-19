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

#: The four functions the task names as the existing owners, plus the readers around them.
OWNER_FUNCTIONS = ("build_proposal", "review_proposal", "apply_proposal", "rollback_policy")

#: The D20 additions, as a group, for the structural sweeps.
RELAY_FUNCTIONS = ("_policy_ref", "_policy_ref_version", "policy_refs", "read_policy_refs",
                   "_relay_refs", "_ref_ids")

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


if __name__ == "__main__":
    unittest.main()
