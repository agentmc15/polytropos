"""Decision-time snapshots: frozen input, separate labels, and collection that is OFF (D31).

WHAT IS UNDER TEST. `bin/training_data.py` captures the bounded, redacted evidence ONE named
decision was taken on, so a future specialist could be trained on it -- setup only. Nothing here
collects anything: every fixture is synthetic, every store is a temp directory, every credential
is a made-up string, and no real transcript, harness home, model, network or CLI is touched by
any path in this file.

HOW EACH ACCEPTANCE TERM IS MADE STRUCTURAL RATHER THAN ASSERTED:

  * EXACT INPUT-TIME EVIDENCE IS IMMUTABLE -- `input_sha` is shown to cover exactly the five
    input-time blocks and nothing else, by mutating each one and each non-input one in turn; a
    store line edited after the fact is refused on read; and the defensive copy at the question
    boundary is proven load-bearing by a spec object that mutates the payload it handed over.
  * LATE LABELS CANNOT CHANGE INPUT -- the example's canonical bytes are compared before and
    after labelling, a label carrying input evidence is refused flat and two levels down, and a
    container the sweep cannot walk is refused rather than passed over.
  * MISSING HISTORICAL FIELDS STAY UNKNOWN -- the `unknown` list is asserted as an EXACT SET,
    a real zero is shown to survive beside an absent one, and a requested model is shown NOT to
    populate the dispatched or observed one.
  * DISABLED COLLECTION PRESERVES LEGACY BEHAVIOUR -- the evidence is never gathered at all,
    proven by a build callable that raises if it is ever invoked, with the positive control
    that flipping the switch DOES invoke it; and a stand-in host returns an identical answer and
    leaves an identical (empty) directory with the hook wired in.
  * SECRETS, OVERSIZE PAYLOADS AND UNKNOWN ELIGIBILITY CANNOT BE PERSISTED -- a credential shape
    is searched for in the whole serialised record and in the bytes on disk, with the control
    that the same text without it redacts nothing; oversize is refused rather than truncated at
    both the field and the record ceiling; and all four non-approved eligibility states fail
    closed before a payload exists.

The reconciliation tests are the other half: the cause taxonomy is pinned as an EXACT PARTITION
of `attempt_ledger.CLASSES` read at call time, and the two classes `classify_dispatch` can never
return are re-derived from that function and from its source rather than remembered here.
"""

import ast
import contextlib
import hashlib
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = ROOT / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_td_test", BIN_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


td = _load("training_data")

#: The module instances `training_data` ITSELF loaded, not fresh copies of them. `bin/` is not
#: a package, so two loaders of one file produce two unrelated classes: a `ContractError`
#: raised through `td`'s copy is not caught by `assertRaises` on a separately loaded one, and
#: `mock.patch.object` on a separate copy patches something nothing reads.
al = td._al()
dc = td._contract()

PREDICTED = "2026-09-19T10:00:00Z"
CAPTURED = "2026-09-19T10:00:05Z"
EARLIER = "2026-09-19T09:59:00Z"
LATER = "2026-09-19T11:00:00Z"

#: A made-up token with a published shape. Not a credential; the prefix is what matters.
SYNTHETIC_TOKEN = "sk-ant-" + "x9" * 20

#: Every gap the canonical fixture below genuinely has. Asserted as an exact set, because a
#: membership check passes on a list a dict literal always writes.
EXPECTED_UNKNOWN = {
    "label",
    "input.task_statement", "input.code_context", "input.tool_state", "input.constraints",
    "reproducibility.dispatched_model", "reproducibility.observed_model",
    "reproducibility.prompt_version", "reproducibility.policy_version",
    "reproducibility.code_revision", "reproducibility.capture_tooling",
    "reproducibility.labeling_tooling",
    "resources.usage", "resources.elapsed_seconds", "resources.review_effort",
    "resources.completeness",
    "sources.acceptance_ref", "sources.admission_ref", "sources.decision_ref",
    "sources.policy_ref", "sources.task_ref", "sources.attempt_ref.sha",
}


def _question():
    return dc.parse_question({
        "id": "q-missing-contract", "version": "1", "kind": "boolean",
        "question": "Was the failing attempt missing an interface contract it needed?",
        "rubric": {}, "outcomes": ["false", "true"], "abstention": "permitted",
        "dependencies": [], "sensitivity": "project-internal",
    })


def _scope(eligibility=td.ELIGIBLE_TO_PERSIST):
    return td.collection_scope(
        purpose="train a local failure-cause classifier on this project's own attempts",
        retention_days=30, eligibility=eligibility,
        approval_ref=al.make_ref("approval-synthetic", version="fixture/1"),
        source_restrictions=("synthetic-only",))


def _entry(text, observed_at=EARLIER, source="verify-tail", artifact_sha=None):
    return {"text": text, "observed_at": observed_at, "source": source,
            "artifact_sha": artifact_sha}


def _kwargs(**over):
    base = {
        "question": _question(),
        "prediction_at": PREDICTED,
        "captured_at": CAPTURED,
        "sources": {"attempt_ref": al.make_ref("a1b2c3d4", version=al.LEDGER_VERSION)},
        "input": {"observed_error": [_entry("AttributeError: no attribute 'emit'")]},
        "boundary": {"sequence": 3, "event": "attempt.failed"},
        "reproducibility": {"harness": "stub", "requested_model": "tier-mid"},
        "operational_class": "unknown",
    }
    base.update(over)
    return base


def _snapshot(**over):
    return td.snapshot(scope=_scope(), **_kwargs(**over))


class _Raises:
    """A build callable that fails the test if it is ever invoked."""

    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        raise AssertionError("the build callable ran; evidence was gathered")


class SnapshotTests(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="training-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.store = self.tmp / "store"

    # ---- the switches: collection is off -------------------------------------------------

    def test_a_fresh_checkout_has_collection_off_and_nothing_wired(self):
        """The two constants ship False, and they are different facts."""
        self.assertIs(td.COLLECTION_ENABLED, False)
        self.assertIs(td.CAPTURE_WIRED, False)
        state = td.collection_state()
        self.assertEqual(state["collecting"], False)
        self.assertEqual(state["reason"], "collection-disabled")

    def test_with_collection_off_the_evidence_is_never_gathered_at_all(self):
        """Not "gathered then dropped": the build callable is never called, so nothing is
        read, digested, or written, and the store directory does not come into existence."""
        build = _Raises()
        report = td.capture_hook(build, store_dir=self.store, scope=_scope())
        self.assertEqual(build.calls, 0)
        self.assertEqual(report["collected"], False)
        self.assertEqual(report["reason"], "collection-disabled")
        self.assertEqual(report["built"], False)
        self.assertFalse(self.store.exists())
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), [])

    def test_the_switch_is_re_derived_at_call_time_not_captured_at_import(self):
        """The positive control for the test above: with the constant flipped, the same call
        DOES reach the build callable -- so "never called" was the switch, not the fixture."""
        build = _Raises()
        with mock.patch.object(td, "COLLECTION_ENABLED", True):
            report = td.capture_hook(build, store_dir=self.store, scope=_scope())
        self.assertEqual(build.calls, 1)
        self.assertEqual(report["collected"], False)
        self.assertEqual(report["reason"], "refused")
        self.assertIn("the build callable ran", report["error"])

    def test_an_explicit_enabled_false_beats_a_flipped_constant(self):
        build = _Raises()
        with mock.patch.object(td, "COLLECTION_ENABLED", True):
            report = td.capture_hook(build, store_dir=self.store, scope=_scope(),
                                     enabled=False)
        self.assertEqual(build.calls, 0)
        self.assertEqual(report["reason"], "collection-disabled")

    def test_a_host_with_the_hook_wired_in_behaves_identically_to_one_without(self):
        """Legacy behaviour, compared rather than asserted: the same answer, and the same
        (empty) directory listing, with and without the hook in the path."""

        def host(hook=None):
            answer = {"selected": "retry", "attempt": "a1"}
            if hook is not None:
                hook()
            return answer

        without = host()
        listing_without = sorted(str(p) for p in self.tmp.rglob("*"))
        build = _Raises()
        with_hook = host(lambda: td.capture_hook(build, store_dir=self.store, scope=_scope()))
        listing_with = sorted(str(p) for p in self.tmp.rglob("*"))
        self.assertEqual(without, with_hook)
        self.assertEqual(listing_without, listing_with)
        self.assertEqual(listing_with, [])
        self.assertEqual(build.calls, 0)

    def test_the_hook_never_raises_into_the_run_it_observes(self):
        """A capture that fails must not break the host. The strict form is `snapshot`."""
        def build():
            raise ValueError("the evidence could not be assembled")

        report = td.capture_hook(build, store_dir=self.store, scope=_scope(), enabled=True)
        self.assertEqual(report["collected"], False)
        self.assertEqual(report["reason"], "refused")
        self.assertIn("could not be assembled", report["error"])
        self.assertFalse(self.store.exists())

    def test_the_hook_refuses_a_malformed_scope_instead_of_raising(self):
        """"Never raises" has to hold for BAD arguments too, or a host cannot rely on it."""
        report = td.capture_hook(lambda: _kwargs(), store_dir=self.store,
                                 scope={"eligibility": "approved"}, enabled=True)
        self.assertEqual(report["collected"], False)
        self.assertEqual(report["reason"], "refused")
        self.assertIn("collection_scope", report["error"])
        self.assertEqual(report["built"], False)
        self.assertFalse(self.store.exists())
        no_store = td.capture_hook(lambda: _kwargs(), scope=_scope(), enabled=True)
        self.assertEqual(no_store["reason"], "refused")
        self.assertIn("store seam", no_store["error"])

    def test_no_production_path_calls_the_capture_hook(self):
        """`CAPTURE_WIRED` is False, and this is what that claim is worth.

        The one module that names this one is `release_gate`, which reads two version
        constants for its contract table. It never captures anything, and the assertion is an
        exact set so a second importer cannot appear without this test saying so.
        """
        naming = set()
        for path in sorted(BIN_DIR.glob("*.py")):
            if path.name == "training_data.py":
                continue
            if "training_data" in path.read_text(encoding="utf-8"):
                naming.add(path.name)
        self.assertEqual(naming, {"release_gate.py"})
        gate = (BIN_DIR / "release_gate.py").read_text(encoding="utf-8")
        for call in ("capture_hook", "collection_scope", "persist(", "snapshot("):
            self.assertNotIn(call, gate)
        self.assertIs(td.CAPTURE_WIRED, False)
        self.assertIn("CAPTURE_WIRED is False", td.NOT_WIRED_LABEL)

    # ---- eligibility: unknown use rights fail closed -----------------------------------------

    def test_every_non_approved_eligibility_refuses_before_a_payload_exists(self):
        for status in td.ELIGIBILITY_STATUSES:
            if status == td.ELIGIBLE_TO_PERSIST:
                continue
            with self.subTest(status=status):
                build = _Raises()
                report = td.capture_hook(build, store_dir=self.store,
                                         scope=_scope(eligibility=status), enabled=True)
                self.assertEqual(build.calls, 0)
                self.assertEqual(report["reason"], "eligibility-not-approved")
                self.assertFalse(self.store.exists())
                with self.assertRaises(dc.ContractError) as raised:
                    td.snapshot(scope=_scope(eligibility=status), **_kwargs())
                self.assertEqual(raised.exception.code, "value-invalid")

    def test_a_scope_defaults_to_unknown_rights_rather_than_to_approved(self):
        scope = td.collection_scope(purpose="collect for a purpose nobody approved",
                                    retention_days=7,
                                    approval_ref=al.make_ref("approval-synthetic"))
        self.assertEqual(scope.eligibility, "unknown")
        self.assertEqual(td.collection_state(scope=scope, enabled=True)["reason"],
                         "eligibility-not-approved")

    def test_a_scope_without_an_owner_approval_or_a_retention_period_is_refused(self):
        for kwargs, code in (
            ({"approval_ref": None}, "missing-field"),
            ({"approval_ref": "approval-synthetic"}, "not-a-reference"),
            ({"retention_days": 0}, "value-invalid"),
            ({"retention_days": None}, "missing-field"),
            ({"purpose": "training"}, "value-invalid"),
        ):
            with self.subTest(kwargs=kwargs):
                base = {"purpose": "train a local failure-cause classifier here",
                        "retention_days": 30, "eligibility": td.ELIGIBLE_TO_PERSIST,
                        "approval_ref": al.make_ref("approval-synthetic")}
                base.update(kwargs)
                with self.assertRaises(dc.ContractError) as raised:
                    td.collection_scope(**base)
                self.assertEqual(raised.exception.code, code)

    def test_a_record_whose_eligibility_is_not_approved_cannot_be_persisted(self):
        """Belt and braces: even a hand-altered record is refused at the write."""
        record = _snapshot()
        tampered = dict(record)
        tampered["eligibility"] = dict(record["eligibility"], status="revoked")
        tampered["content_sha"] = td._sha(
            {k: v for k, v in tampered.items() if k != "content_sha"})
        with self.assertRaises(dc.ContractError) as raised:
            td.persist(tampered, self.store)
        self.assertEqual(raised.exception.code, "value-invalid")
        self.assertFalse(self.store.exists())

    # ---- exact input-time evidence is immutable ----------------------------------------------

    def test_the_input_digest_covers_exactly_the_input_time_evidence(self):
        """Each of the five input-time blocks changes `input_sha`; nothing else does."""
        base = _snapshot()
        moved = {
            "input": _snapshot(input={"observed_error": [_entry("a different error")]}),
            "question": _snapshot(question=dc.parse_question({
                "id": "q-other", "version": "1", "kind": "boolean",
                "question": "Did the attempt fail for a reason the environment caused?",
                "rubric": {}, "outcomes": ["false", "true"], "abstention": "permitted",
                "dependencies": [], "sensitivity": "project-internal"})),
            "boundary": _snapshot(boundary={"sequence": 4, "event": "attempt.failed"}),
            "sources": _snapshot(sources={
                "attempt_ref": al.make_ref("deadbeef", version=al.LEDGER_VERSION)}),
            "prediction_at": _snapshot(prediction_at="2026-09-19T09:59:59Z"),
        }
        for name, other in moved.items():
            with self.subTest(changed=name):
                self.assertNotEqual(other["input_sha"], base["input_sha"])
        unmoved = {
            "captured_at": _snapshot(captured_at="2026-09-20T08:00:00Z"),
            "reproducibility": _snapshot(reproducibility={"harness": "stub",
                                                          "requested_model": "tier-mid",
                                                          "code_revision": "abc123"}),
            "resources": _snapshot(resources={"usage": {"estimated": 1200}}),
            "operational_class": _snapshot(operational_class="infrastructure"),
        }
        for name, other in unmoved.items():
            with self.subTest(unchanged_by=name):
                self.assertEqual(other["input_sha"], base["input_sha"])
                self.assertNotEqual(other["content_sha"], base["content_sha"])

    def test_the_example_id_is_derived_from_the_input_so_one_id_names_one_input(self):
        base = _snapshot()
        self.assertEqual(base["example_id"], f"ex-{base['input_sha'][:16]}")
        self.assertEqual(base["example_id_basis"], "input-sha")
        other = _snapshot(input={"observed_error": [_entry("a different error")]})
        self.assertNotEqual(other["example_id"], base["example_id"])
        self.assertEqual(_snapshot()["example_id"], base["example_id"])

    def test_identical_evidence_captured_twice_is_one_example_not_two(self):
        record = _snapshot()
        first = td.persist(record, self.store)
        second = td.persist(_snapshot(), self.store)
        self.assertEqual(first["written"], True)
        self.assertEqual(second["written"], False)
        self.assertEqual(second["reason"], "already-captured")
        self.assertEqual(len(td.read_snapshots(self.store, CAPTURED)), 1)

    def test_a_stored_line_edited_after_capture_is_refused_on_read(self):
        record = _snapshot()
        td.persist(record, self.store)
        path = self.store / "snapshots" / f"{CAPTURED[:10]}.jsonl"
        stored = json.loads(path.read_text(encoding="utf-8").strip())
        stored["input"]["observed_error"][0]["text"] = "an error nobody observed"
        path.write_text(td.canonical(stored) + "\n", encoding="utf-8")
        with self.assertRaises(dc.ContractError) as raised:
            td.read_snapshots(self.store, CAPTURED)
        self.assertEqual(raised.exception.code, "value-invalid")
        self.assertIn("input_sha_ok", str(raised.exception))

    def test_a_forged_line_that_reworks_its_own_digests_is_still_refused(self):
        """A rewritten line cannot make itself look original: the example id is DERIVED from
        the input digest, so recomputing the digest leaves the id naming the old input."""
        record = _snapshot()
        td.persist(record, self.store)
        path = self.store / "snapshots" / f"{CAPTURED[:10]}.jsonl"
        forged = json.loads(path.read_text(encoding="utf-8").strip())
        forged["input"]["observed_error"][0]["text"] = "an error nobody observed"
        forged["input_sha"] = td._sha({
            "input": forged["input"], "question": forged["question"],
            "boundary": forged["boundary"], "sources": forged["sources"],
            "prediction_at": forged["prediction_at"]})
        forged["content_sha"] = td._sha(
            {k: v for k, v in forged.items() if k != "content_sha"})
        path.write_text(td.canonical(forged) + "\n", encoding="utf-8")
        with self.assertRaises(dc.ContractError) as raised:
            td.persist(_snapshot(), self.store)
        self.assertEqual(raised.exception.code, "value-invalid")
        self.assertIn("example_id_ok", str(raised.exception))
        self.assertEqual(td.integrity(forged)["example_id_ok"], False)

    def test_two_different_inputs_sharing_an_example_id_refuse_rather_than_stack(self):
        """The id-prefix collision branch, reached by deliberately crippling the digest.

        Through the real hash this cannot happen without a 64-bit collision, so the only
        honest way to exercise it is to make one: every digest below shares a fixed 16-hex
        prefix while still differing overall, which is exactly the shape the branch is for.
        Without this the guard would be code no test could ever reach.
        """
        real = td._sha

        def colliding(payload):
            return "a" * 16 + real(payload)[16:]

        with mock.patch.object(td, "_sha", colliding):
            first = _snapshot()
            second = _snapshot(input={"observed_error": [_entry("a different error")]})
            self.assertEqual(first["example_id"], second["example_id"])
            self.assertNotEqual(first["input_sha"], second["input_sha"])
            td.persist(first, self.store)
            with self.assertRaises(dc.ContractError) as raised:
                td.persist(second, self.store)
        self.assertEqual(raised.exception.code, "duplicate-entry")

    def test_the_bytes_on_disk_are_the_records_own_canonical_form(self):
        record = _snapshot()
        td.persist(record, self.store)
        path = self.store / "snapshots" / f"{CAPTURED[:10]}.jsonl"
        self.assertEqual(path.read_text(encoding="utf-8"), td.canonical(record) + "\n")
        self.assertEqual(td.read_snapshots(self.store, CAPTURED)[0], record)

    def test_a_question_payload_the_caller_keeps_mutating_cannot_reach_the_record(self):
        """The defensive copy at the question boundary, given a real route.

        `decision_contract.QuestionSpec.to_payload()` builds a fresh dict, so the copy would
        be invisible against it. The duck type accepts any object with that method, and one
        that hands back a dict it retains is exactly what the copy is there for.
        """
        class LeakySpec:
            def __init__(self):
                self.payload = {"id": "q-leaky", "version": "1", "kind": "boolean",
                                "question": "Did the attempt fail for a reason it was shown?",
                                "rubric": {}, "outcomes": ["false", "true"],
                                "abstention": "permitted", "dependencies": [],
                                "sensitivity": "project-internal"}

            def to_payload(self):
                return self.payload

            def digest(self):
                return hashlib.sha256(b"q-leaky").hexdigest()

        spec = LeakySpec()
        record = td.snapshot(scope=_scope(), **_kwargs(question=spec))
        before = td.canonical(record)
        spec.payload["question"] = "a question nobody asked"
        spec.payload["outcomes"].append("maybe")
        self.assertEqual(td.canonical(record), before)
        self.assertEqual(record["question"]["spec"]["outcomes"], ["false", "true"])
        td.assert_intact(record)

    def test_evidence_from_after_the_decision_can_never_enter_an_input(self):
        for observed_at in (LATER, "2026-09-19T10:00:01Z"):
            with self.subTest(observed_at=observed_at):
                with self.assertRaises(dc.ContractError) as raised:
                    _snapshot(input={"code_context": [_entry("the patch that fixed it",
                                                             observed_at=observed_at)]})
                self.assertEqual(raised.exception.code, "value-invalid")
                self.assertIn("after-prediction", str(raised.exception))
        at_the_instant = _snapshot(input={"code_context": [_entry("what it was shown",
                                                                  observed_at=PREDICTED)]})
        self.assertEqual(at_the_instant["input"]["code_context"][0]["placement"],
                         td.ADMISSIBLE_PLACEMENT)

    def test_evidence_with_an_unreadable_instant_is_refused_not_assumed_contemporaneous(self):
        for observed_at in ("2026-09-19 09:59:00", "yesterday", "2026-09-19T09:59:00"):
            with self.subTest(observed_at=observed_at):
                with self.assertRaises(dc.ContractError) as raised:
                    _snapshot(input={"code_context": [_entry("x", observed_at=observed_at)]})
                self.assertEqual(raised.exception.code, "value-invalid")

    def test_the_capture_and_decision_instants_are_refused_unless_they_name_an_instant(self):
        """The other two routes into the same check, and the one with no second line of
        defence: an entry's own stamp is caught again downstream by its placement, but a
        zoneless `captured_at` would sail through into the file name and the expiry date."""
        for unreadable in ("2026-09-19 10:00:05", "today", "2026-09-19T10:00:05", ""):
            with self.subTest(captured_at=unreadable):
                with self.assertRaises(dc.ContractError) as raised:
                    _snapshot(captured_at=unreadable)
                self.assertIn("captured_at", str(raised.exception))
            with self.subTest(prediction_at=unreadable):
                with self.assertRaises(dc.ContractError) as raised:
                    _snapshot(prediction_at=unreadable)
                self.assertIn("prediction_at", str(raised.exception))

    # ---- late labels cannot change input -----------------------------------------------------

    def test_attaching_a_label_leaves_the_example_byte_identical(self):
        record = _snapshot()
        before = td.canonical(record)
        pair = td.attach_label(record, {"claimed_cause": "missing-context",
                                        "by": "synthetic-reviewer"})
        self.assertEqual(td.canonical(pair["example"]), before)
        self.assertEqual(td.canonical(record), before)
        self.assertEqual(pair["label"]["input_sha"], record["input_sha"])
        self.assertEqual(pair["label"]["example_id"], record["example_id"])
        self.assertEqual(pair["label"]["status"], "unadjudicated")
        self.assertNotIn("label", pair["example"])
        self.assertIn("label", pair["example"]["unknown"])

    def test_a_label_carrying_input_evidence_is_refused_at_any_depth(self):
        record = _snapshot()
        for payload in (
            {"task_statement": "what the model should have been told"},
            {"evidence": {"observed_error": "the error, written down later"}},
            {"findings": [{"code_context": "the file it should have seen"}]},
            {"input_sha": "0" * 64},
            {"corrected.question": "a better question"},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(dc.ContractError) as raised:
                    td.attach_label(record, payload)
                self.assertEqual(raised.exception.code, "authority-field")

    def test_a_label_the_sweep_cannot_walk_is_refused_rather_than_passed_over(self):
        record = _snapshot()
        for payload in ({"blob": b"opaque"}, {"seen": {"a", "b"}},
                        {"rows": (x for x in ("a",))}):
            with self.subTest(payload=type(list(payload.values())[0]).__name__):
                with self.assertRaises(dc.ContractError) as raised:
                    td.attach_label(record, payload)
                self.assertEqual(raised.exception.code, "authority-field")
                self.assertIn("cannot inspect", str(raised.exception))

    def test_an_input_field_nobody_declared_is_refused_at_capture(self):
        """The other half of the same fence: a caller cannot widen the input either."""
        for field in ("root_cause", "fix_patch", "reviewer_verdict", "transcript"):
            with self.subTest(field=field):
                with self.assertRaises(dc.ContractError) as raised:
                    _snapshot(input={"observed_error": [_entry("x")], field: [_entry("y")]})
                self.assertEqual(raised.exception.code, "unknown-field")

    def test_an_entry_key_nobody_declared_is_refused(self):
        with self.assertRaises(dc.ContractError) as raised:
            _snapshot(input={"observed_error": [dict(_entry("x"), outcome="pass")]})
        self.assertEqual(raised.exception.code, "unknown-field")

    def test_a_snapshot_has_no_label_slot_for_anything_to_fill(self):
        record = _snapshot()
        self.assertNotIn("label", record)
        self.assertEqual(record["candidate_cause"]["adjudicated"], False)
        self.assertIn("never an adjudicated target", record["candidate_cause"]["note"])
        self.assertIn(td.LABEL_SEPARATE_NOTE, record["disclosures"])

    # ---- missing historical fields stay unknown ----------------------------------------------

    def test_every_gap_is_named_in_unknown_as_an_exact_set(self):
        record = _snapshot()
        self.assertEqual(set(record["unknown"]), EXPECTED_UNKNOWN)
        self.assertEqual(record["unknown"], sorted(record["unknown"]))
        for field in ("task_statement", "code_context", "tool_state", "constraints"):
            self.assertIsNone(record["input"][field])

    def test_a_requested_model_does_not_populate_the_dispatched_or_observed_one(self):
        record = _snapshot(reproducibility={"harness": "stub", "requested_model": "tier-mid"})
        self.assertEqual(record["reproducibility"]["requested_model"], "tier-mid")
        self.assertIsNone(record["reproducibility"]["dispatched_model"])
        self.assertIsNone(record["reproducibility"]["observed_model"])
        self.assertIn("reproducibility.dispatched_model", record["unknown"])
        self.assertIn("reproducibility.observed_model", record["unknown"])

    def test_an_absent_usage_record_is_unknown_and_a_measured_zero_is_zero(self):
        absent = _snapshot()
        self.assertIsNone(absent["resources"]["usage"])
        self.assertIn("resources.usage", absent["unknown"])
        measured = _snapshot(resources={"usage": {"model-reported": 0}})
        self.assertEqual(measured["resources"]["usage"], {"model-reported": 0})
        self.assertNotIn("resources.usage", measured["unknown"])

    def test_resource_bases_are_kept_apart_and_an_empty_account_is_refused(self):
        record = _snapshot(resources={"usage": {"model-reported": 120, "estimated": 300},
                                      "completeness": "partial"})
        self.assertEqual(record["resources"]["usage"], {"model-reported": 120,
                                                        "estimated": 300})
        self.assertEqual(record["resources"]["completeness"], "partial")
        self.assertIn("never added", record["resources"]["note"])
        with self.assertRaises(dc.ContractError) as raised:
            _snapshot(resources={"usage": {}})
        self.assertEqual(raised.exception.code, "value-invalid")

    def test_an_unknown_resource_basis_is_refused_against_its_owner_at_call_time(self):
        with self.assertRaises(dc.ContractError) as raised:
            _snapshot(resources={"usage": {"invented-basis": 1}})
        self.assertEqual(raised.exception.code, "unknown-field")
        with mock.patch.object(td._de(), "RESOURCE_BASES", ("invented-basis",)):
            moved = _snapshot(resources={"usage": {"invented-basis": 1}})
            self.assertEqual(moved["resources"]["usage"], {"invented-basis": 1})
            with self.assertRaises(dc.ContractError):
                _snapshot(resources={"usage": {"model-reported": 1}})

    def test_a_reference_with_no_digest_names_its_gap_rather_than_inventing_one(self):
        record = _snapshot()
        self.assertEqual(record["sources"]["attempt_ref"],
                         {"id": "a1b2c3d4", "sha": None, "v": al.LEDGER_VERSION})
        self.assertIn("sources.attempt_ref.sha", record["unknown"])
        self.assertNotIn("sources.attempt_ref", record["unknown"])
        self.assertIn("sources.decision_ref", record["unknown"])

    def test_labelling_tooling_cannot_be_dated_to_the_moment_of_capture(self):
        with self.assertRaises(dc.ContractError) as raised:
            _snapshot(reproducibility={"harness": "stub", "labeling_tooling": "reviewer/1"})
        self.assertEqual(raised.exception.code, "value-invalid")

    def test_an_absent_boundary_sequence_is_unknown_rather_than_zero(self):
        record = _snapshot(boundary={"event": "attempt.failed"})
        self.assertIsNone(record["boundary"]["sequence"])
        self.assertIn("boundary.sequence", record["unknown"])
        counted = _snapshot(boundary={"sequence": 0, "event": "attempt.failed"})
        self.assertEqual(counted["boundary"]["sequence"], 0)
        self.assertNotIn("boundary.sequence", counted["unknown"])

    def test_an_empty_input_list_is_refused_because_absent_and_none_are_different(self):
        with self.assertRaises(dc.ContractError) as raised:
            _snapshot(input={"observed_error": [_entry("x")], "code_context": []})
        self.assertEqual(raised.exception.code, "value-invalid")

    def test_a_snapshot_with_no_input_and_no_source_is_refused(self):
        with self.assertRaises(dc.ContractError) as raised:
            _snapshot(input={})
        self.assertEqual(raised.exception.code, "missing-field")
        with self.assertRaises(dc.ContractError) as raised:
            _snapshot(sources={"task_ref": al.make_ref("D31")})
        self.assertEqual(raised.exception.code, "missing-field")
        self.assertIn("trace back", str(raised.exception))

    # ---- secrets, bounds, and what redaction does not promise --------------------------------

    def test_a_credential_shape_is_labelled_and_never_reaches_the_record_or_the_disk(self):
        record = _snapshot(input={"observed_error": [
            _entry(f"401 unauthorized using {SYNTHETIC_TOKEN} from the config")]})
        td.persist(record, self.store)
        on_disk = (self.store / "snapshots" / f"{CAPTURED[:10]}.jsonl").read_text("utf-8")
        self.assertNotIn(SYNTHETIC_TOKEN, td.canonical(record))
        self.assertNotIn(SYNTHETIC_TOKEN, on_disk)
        self.assertEqual(record["redaction"]["redactions"], {"anthropic-key": 1})
        self.assertIn("[redacted:anthropic-key]",
                      record["input"]["observed_error"][0]["text"])

    def test_the_redaction_report_is_kinds_and_counts_and_the_control_finds_nothing(self):
        """The control matters: without it, an always-empty report would pass the test above
        for the wrong reason."""
        clean = _snapshot(input={"observed_error": [_entry("401 unauthorized from the config")]})
        self.assertEqual(clean["redaction"]["redactions"], {})
        loaded = _snapshot(input={"observed_error": [
            _entry(f"{SYNTHETIC_TOKEN} and {SYNTHETIC_TOKEN} both rejected")]})
        self.assertEqual(loaded["redaction"]["redactions"], {"anthropic-key": 2})
        for value in loaded["redaction"]["redactions"].values():
            self.assertIsInstance(value, int)

    def test_the_record_says_what_shape_matching_cannot_prove(self):
        record = _snapshot()
        self.assertIn("cannot prove", record["redaction"]["note"])
        self.assertIn(td.REDACTION_LIMIT_NOTE, record["disclosures"])

    def test_an_oversize_entry_is_refused_rather_than_quietly_truncated(self):
        big = "x" * (td.MAX_FIELD_CHARS + 1)
        with self.assertRaises(dc.ContractError) as raised:
            _snapshot(input={"observed_error": [_entry(big)]})
        self.assertEqual(raised.exception.code, "bounds-exceeded")
        self.assertIn("refused rather than truncated", str(raised.exception))
        fits = _snapshot(input={"observed_error": [_entry("x" * td.MAX_FIELD_CHARS)]})
        self.assertEqual(fits["redaction"]["truncated"], 0)

    def test_too_many_entries_in_one_field_are_refused(self):
        entries = [_entry(f"error {index}") for index in range(td.MAX_ENTRIES_PER_FIELD + 1)]
        with self.assertRaises(dc.ContractError) as raised:
            _snapshot(input={"observed_error": entries})
        self.assertEqual(raised.exception.code, "bounds-exceeded")

    def test_a_record_past_the_line_ceiling_is_refused_whole(self):
        filled = {field: [_entry("y" * (td.MAX_FIELD_CHARS - 1), source=f"s{index}")
                          for index in range(td.MAX_ENTRIES_PER_FIELD)]
                  for field in td.INPUT_FIELDS}
        with self.assertRaises(dc.ContractError) as raised:
            _snapshot(input=filled)
        self.assertEqual(raised.exception.code, "bounds-exceeded")
        self.assertIn(str(td.MAX_RECORD_BYTES), str(raised.exception))
        self.assertFalse(self.store.exists())

    # ---- the store lives outside the tree, written by this engine only -----------------------

    def test_the_store_is_registered_and_resolves_through_runtime_data(self):
        rt = _load("runtime_data")
        self.assertIn(td.STORE, rt.STORES)
        home = self.tmp / "data-home"
        env = {"POLYTROPOS_DATA_HOME": str(home), "HOME": str(self.tmp / "not-a-home")}
        resolved = td.default_store(ROOT, env=env)
        self.assertTrue(str(resolved).startswith(str(home)))
        self.assertNotIn(str(ROOT / td.STORE), str(resolved))
        self.assertFalse(Path(resolved).exists())

    def test_the_store_carries_a_root_anchored_ignore_rule(self):
        rules = {line.strip()
                 for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()}
        self.assertIn(f"/{td.STORE}/", rules)

    def test_the_module_reaches_no_home_directory_and_no_process(self):
        source = (BIN_DIR / "training_data.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertEqual(imported & {"subprocess", "socket", "urllib", "http", "ftplib",
                                     "sqlite3", "requests"}, set())
        self.assertNotIn("Path.home", source)
        self.assertNotIn("expanduser", source)
        attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        self.assertNotIn("home", attributes)
        self.assertGreater(len(attributes), 20)  # the sweep walked something

    def test_writes_go_through_the_confined_path_helper(self):
        """A hand-composed destination is the thing `safe_paths` exists to prevent."""
        source = (BIN_DIR / "training_data.py").read_text(encoding="utf-8")
        self.assertIn("confined_append_bytes", source)
        self.assertIn("confined_read_bytes", source)
        self.assertNotIn("open(", source.replace("os.open(", ""))

    def test_a_capture_date_that_could_name_a_path_is_refused_before_it_becomes_one(self):
        """`read_snapshots` takes a capture date straight from a caller.

        `safe_parts` would stop `..` and an absolute path, and it would NOT stop `a/b/c`,
        which quietly reads and creates nested directories under the store, or a leading dot,
        which writes a hidden file. The date is validated as ONE filename component first.
        """
        sp = td._sp()
        for captured_at in ("a/b/c", ".hidden", "../escape", "/etc/passwd"):
            with self.subTest(captured_at=captured_at):
                with self.assertRaises(sp.SafePathError):
                    td.read_snapshots(self.store, captured_at)
                self.assertFalse(self.store.exists())

    def test_a_reader_does_not_create_the_store(self):
        self.assertEqual(td.read_snapshots(self.store, CAPTURED), [])
        self.assertFalse(self.store.exists())

    def test_records_are_filed_by_capture_date_not_by_the_decisions_date(self):
        record = _snapshot(prediction_at="2026-09-18T23:00:00Z",
                           captured_at="2026-09-19T00:05:00Z",
                           input={"observed_error": [_entry("x",
                                                            observed_at="2026-09-18T22:00:00Z")]})
        receipt = td.persist(record, self.store)
        self.assertTrue(receipt["path"].endswith("2026-09-19.jsonl"))
        self.assertEqual(record["prediction_at"], "2026-09-18T23:00:00Z")

    # ---- the reconciliation with the classes that already exist ------------------------------

    def test_the_candidate_mapping_is_an_exact_partition_of_the_ledgers_classes(self):
        report = td.reconcile_operational_classes()
        self.assertEqual(set(report["candidate_of"]), set(al.CLASSES))
        self.assertEqual(set(report["candidate_of"].values()) - set(td.CAUSE_CLASSES), set())
        self.assertEqual(report["operational_owner"], "bin/attempt_ledger.py:CLASSES")

    def test_a_class_the_ledger_adds_or_drops_refuses_rather_than_disappearing(self):
        with mock.patch.object(td._al(), "CLASSES", al.CLASSES + ("flakiness",)):
            with self.assertRaises(dc.ContractError) as raised:
                td.reconcile_operational_classes()
            self.assertEqual(raised.exception.code, "unknown-value")
            self.assertIn("flakiness", str(raised.exception))
        with mock.patch.object(td._al(), "CLASSES", ("model", "unknown")):
            with self.assertRaises(dc.ContractError) as raised:
                td.reconcile_operational_classes()
            self.assertIn("unknown", str(raised.exception))

    def test_a_symptom_is_not_promoted_to_a_cause(self):
        self.assertEqual(td.candidate_cause("verification"), "unknown")
        self.assertEqual(td.candidate_cause("model"), "unknown")
        self.assertEqual(td.candidate_cause("infrastructure"), "environment-infrastructure")
        for name in ("auth", "config", "permission"):
            self.assertEqual(td.candidate_cause(name), "configuration-permission")
        self.assertIsNone(td.candidate_cause(None))
        with self.assertRaises(dc.ContractError):
            td.candidate_cause("implementation-error")

    def test_the_review_only_classes_are_unreachable_from_an_operational_signal(self):
        produced = set(td.OPERATIONAL_TO_CANDIDATE.values())
        self.assertEqual(produced & set(td.REVIEW_ONLY_CLASSES), set())
        self.assertEqual(set(td.REVIEW_ONLY_CLASSES) - set(td.CAUSE_CLASSES), set())

    def test_the_two_classes_classify_dispatch_never_returns_are_named_and_still_unreachable(
            self):
        """Re-derived, not remembered: the function is called and then read.

        Calling it shows which classes real inputs reach; reading it shows the other two have
        no return statement at all. The first alone would prove only that this fixture missed
        them.
        """
        cases = (
            (1, "fatal: not logged in", None, "auth"),
            (2, "unknown model tier-zzz", None, "config"),
            (1, "permission denied: /etc/hosts", None, "permission"),
            (1, "connection refused", None, "infrastructure"),
            (1, "something nobody here can attribute", None, "unknown"),
            (0, "FAIL: everything", None, None),
            (1, "", "timeout", "infrastructure"),
        )
        observed = set()
        for rc, output, proc_outcome, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(al.classify_dispatch(rc, output, proc_outcome), expected)
            observed.add(expected)
        observed.discard(None)
        self.assertEqual(observed, set(al.CLASSES) - set(td.NOT_PRODUCED_BY_DISPATCH))
        import inspect
        body = inspect.getsource(al.classify_dispatch)
        for name in td.NOT_PRODUCED_BY_DISPATCH:
            self.assertNotIn(f'return "{name}"', body)
        for name in observed:
            self.assertIn(f'return "{name}"', body)

    def test_the_reference_names_come_from_the_ledger_and_refuse_a_collision(self):
        names = td.source_ref_names()
        self.assertEqual(set(al.PROVENANCE_REFS) - set(names), set())
        self.assertEqual(set(td.REQUIRED_SOURCE_ONE_OF) - set(names), set())
        with mock.patch.object(td._al(), "PROVENANCE_REFS",
                               al.PROVENANCE_REFS + ("attempt_ref",)):
            with self.assertRaises(dc.ContractError) as raised:
                td.source_ref_names()
            self.assertEqual(raised.exception.code, "duplicate-entry")

    def test_no_owner_vocabulary_is_copied_into_this_module_as_a_constant(self):
        tree = ast.parse((BIN_DIR / "training_data.py").read_text(encoding="utf-8"))
        constants = {node.value for node in ast.walk(tree)
                     if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        self.assertGreater(len(constants), 50)  # the sweep walked something
        de = _load("decision_eval")
        self.assertEqual(constants & set(de.RESOURCE_BASES), set())
        self.assertEqual(constants & set(de.FACT_PLACEMENTS) - {td.ADMISSIBLE_PLACEMENT}, set())

    # ---- the serialiser and the versions -----------------------------------------------------

    def test_canonical_form_is_the_decision_contracts_own(self):
        payload = {"b": 1, "a": [2, {"d": 3, "c": 4}]}
        self.assertEqual(td.canonical(payload), dc.dumps(payload))

    def test_a_duplicate_key_in_a_stored_line_is_refused_on_read(self):
        record = _snapshot()
        td.persist(record, self.store)
        path = self.store / "snapshots" / f"{CAPTURED[:10]}.jsonl"
        text = path.read_text(encoding="utf-8").strip()
        path.write_text(text[:-1] + ',"v":"other"}' + "\n", encoding="utf-8")
        with self.assertRaises(dc.ContractError) as raised:
            td.read_snapshots(self.store, CAPTURED)
        self.assertEqual(raised.exception.code, "duplicate-key")

    def test_a_line_from_another_schema_is_refused_rather_than_read_as_this_one(self):
        self.store.mkdir(parents=True)
        (self.store / "snapshots").mkdir()
        (self.store / "snapshots" / f"{CAPTURED[:10]}.jsonl").write_text(
            json.dumps({"v": "something.else/1", "example_id": "ex-0"}) + "\n",
            encoding="utf-8")
        with self.assertRaises(dc.ContractError) as raised:
            td.read_snapshots(self.store, CAPTURED)
        self.assertEqual(raised.exception.code, "unknown-value")

    def test_both_versions_are_registered_with_the_release_gate(self):
        rg = _load("release_gate")
        rows = {(module, attr) for _, module, attr in rg.VERSION_SOURCES}
        self.assertIn(("training_data", "SNAPSHOT_VERSION"), rows)
        self.assertIn(("training_data", "TAXONOMY_VERSION"), rows)
        self.assertNotEqual(td.SNAPSHOT_VERSION, td.TAXONOMY_VERSION)
        self.assertEqual(_snapshot()["v"], td.SNAPSHOT_VERSION)

    def test_the_ledger_version_did_not_move_for_this_record(self):
        """A new referenced object gets its own version; the pointing line keeps its own."""
        self.assertEqual(al.LEDGER_VERSION, "polytropos.attempts/1")
        self.assertTrue(td.SNAPSHOT_VERSION.startswith("polytropos.training-snapshot/"))

    # ---- the CLI, offline ---------------------------------------------------------------------

    def test_the_demo_is_synthetic_offline_and_leaves_nothing_behind(self):
        before = sorted(p.name for p in Path(tempfile.gettempdir()).glob("training-demo-*"))
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = td._cli(["demo", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["synthetic"], True)
        steps = {step["step"]: step for step in payload["steps"]}
        self.assertEqual(steps["collection off"]["reason"], "collection-disabled")
        self.assertEqual(steps["unknown eligibility"]["reason"], "eligibility-not-approved")
        self.assertEqual(steps["late label"]["example_bytes_unchanged"], True)
        self.assertEqual(steps["credential-shaped text"]["redactions"], {"anthropic-key": 1})
        after = sorted(p.name for p in Path(tempfile.gettempdir()).glob("training-demo-*"))
        self.assertEqual(before, after)

    def test_status_reports_both_switches_and_how_to_turn_collection_on(self):
        report = td.status(repo_root=ROOT, env={"POLYTROPOS_DATA_HOME": str(self.tmp / "h")})
        self.assertEqual(report["collection_enabled"], False)
        self.assertEqual(report["capture_wired"], False)
        self.assertEqual(report["store_exists"], False)
        self.assertEqual(len(report["to_enable"]), 3)
        self.assertTrue(report["store_path"].startswith(str(self.tmp / "h")))


REVIEWED = "2026-09-19T12:00:00Z"
REVIEWED_LATER = "2026-09-19T13:00:00Z"
IN_RETENTION = "2026-10-19T23:00:00Z"   # the expiry date itself: still usable
PAST_RETENTION = "2026-10-20T00:30:00Z"  # one day later: expired
EXPIRES_ON = "2026-10-19"                # captured 2026-09-19 + the fixture's 30 days


def _ev(source="human-adjudication", ref_id="review-1", observed_at=REVIEWED, stage=None):
    return td.review_evidence(source=source, ref=al.make_ref(ref_id, version="fixture/1"),
                              observed_at=observed_at, stage=stage)


def _reviewer(name="reviewer-a", source="human-adjudication"):
    return {"id": name, "source": source}


def _adjudicate(record, **over):
    base = {"shape": "failure-cause", "cause": "missing-context",
            "reviewer": _reviewer(), "decided_at": REVIEWED, "evidence": [_ev()]}
    base.update(over)
    return td.adjudicate(record, **base)


def _reseal(record, **eligibility):
    """A record whose eligibility block was altered and whose digest was recomputed.

    The doctoring is the only way to reach the states `snapshot()` refuses to BUILD: D31 made
    `unknown`, `refused`, `expired` and `revoked` unconstructible at capture, and D32's gates
    still have to answer for a record that arrives in one of them.
    """
    out = td._copy(dict(record))
    out["eligibility"] = dict(out["eligibility"], **eligibility)
    out["content_sha"] = td._sha({k: v for k, v in out.items() if k != "content_sha"})
    return out


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str):
                yield key
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


class LabelEligibilityTests(unittest.TestCase):
    """D32: reviewed labels, the three origins kept apart, retention and revocation.

    HOW EACH ACCEPTANCE TERM IS MADE STRUCTURAL:

      * UNSUPPORTED CLAIMS REMAIN UNRESOLVED -- a claimed cause with no evidence, with only the
        ledger's own class, with only a provider's suggestion, or with a mechanical reading where
        an independent reader is required, comes back `cause: None` and `unresolved` with the
        reason naming which support was missing; the claim survives under `claim` and is never
        promoted. The evidence weight is RE-DERIVED from the source, so a caller cannot hand over
        an operational observation labelled `review`.
      * FUTURE ACTIONS ARE SEPARATE FROM ORIGINAL INPUTS -- an adjudication and an action record
        are refused when they place at or before the decision, which is the exact mirror of D31's
        input rule; the example's canonical bytes are compared before and after; and the action
        record's key set is pinned against `decision_eval._is_causal_key` and
        `_is_input_shaped`, because that record has no free-form slot for a sweep to inspect.
      * UNKNOWN USE RIGHTS REFUSE EXPORT -- every one of the fourteen `EXPORT_REFUSALS` codes is
        reached by its own case and their union is asserted to be the whole tuple, with the
        positive control that a fully eligible example exports with an EMPTY refusal list.
      * EXPIRY AND REVOCATION INVALIDATE DEPENDENT EXPORTS AND IDENTIFY DOWNSTREAM ARTIFACTS
        WITHOUT CLAIMING MODEL UNLEARNING -- retention is enforced against an explicit `now` with
        the expiry date itself shown to be usable and the next day shown not to be; `approved` is
        reachable from exactly one state so nothing renews or reinstates; and every revocation
        carries all four `REVOCATION_UNREACHED` codes whether it names four dependents or none,
        with a checkpoint `identified-only` and every string on the record checked for an
        unlearning word that is not negated.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="training-d32-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.store = self.tmp / "store"
        self.record = _snapshot()

    # ---- the locks D31 shut are still shut ----------------------------------------------------

    def test_the_lifecycle_did_not_turn_collection_on(self):
        """D32 extends what happens to a label. It does not open any of the three locks."""
        self.assertIs(td.COLLECTION_ENABLED, False)
        self.assertIs(td.CAPTURE_WIRED, False)
        scope = td.collection_scope(purpose="collect for a purpose nobody approved",
                                    retention_days=7,
                                    approval_ref=al.make_ref("approval-synthetic"))
        self.assertEqual(scope.eligibility, "unknown")
        self.assertEqual(td.collection_state()["reason"], "collection-disabled")
        self.assertEqual(td.status(repo_root=ROOT,
                                   env={"POLYTROPOS_DATA_HOME": str(self.tmp / "h")})
                         ["store_exists"], False)

    def test_the_lifecycle_version_is_registered_and_is_its_own_object(self):
        rg = _load("release_gate")
        rows = {(module, attr) for _, module, attr in rg.VERSION_SOURCES}
        self.assertIn(("training_data", "LIFECYCLE_VERSION"), rows)
        self.assertEqual(len({td.SNAPSHOT_VERSION, td.TAXONOMY_VERSION, td.LIFECYCLE_VERSION}), 3)
        self.assertEqual(al.LEDGER_VERSION, "polytropos.attempts/1")
        self.assertEqual(set(td.LIFECYCLE_DIRS), set(td.LIFECYCLE_KINDS))
        self.assertEqual(sorted(td.LIFECYCLE_DIRS.values()), ["actions", "labels", "revocations"])

    # ---- unsupported claims remain unresolved -------------------------------------------------

    def test_a_cause_nobody_can_support_is_not_recorded_as_the_cause(self):
        """The headline. `cause` stays None, the ask survives under `claim`, and the reason says
        which support was missing -- not defaulted, not guessed, not promoted."""
        thin = _adjudicate(self.record, evidence=(),
                           claim={"claimed_cause": "missing-context", "by": "a hunch"})
        self.assertEqual(thin["status"], "unresolved")
        self.assertIsNone(thin["cause"])
        self.assertEqual(thin["unresolved_reason"], "no-supporting-evidence")
        self.assertEqual(thin["claim"], {"claimed_cause": "missing-context", "by": "a hunch"})
        state = td.label_state([thin])
        self.assertEqual(state["status"], "unresolved")
        self.assertEqual(state["target"], {"eligible": False, "reason": "no-supporting-evidence",
                                           "status": "unresolved", "shape": "failure-cause",
                                           "cause": None,
                                           "note": "a target is only what review evidence "
                                                   "supported; this record's did not"})

    def test_a_supported_cause_is_recorded_which_is_the_control_for_the_case_above(self):
        strong = _adjudicate(self.record)
        self.assertEqual(strong["status"], "resolved")
        self.assertEqual(strong["cause"], "missing-context")
        self.assertIsNone(strong["unresolved_reason"])
        self.assertEqual(td.label_state([strong])["target"]["eligible"], True)

    def test_a_review_only_class_needs_an_independent_reader_not_a_reproduction(self):
        """`missing-context` is one of D31's review-only classes. A reproduction narrows it and
        cannot establish it; the control is the same evidence against a class that IS mechanical."""
        mechanical = _adjudicate(self.record, evidence=[_ev(source="tests-oracle")])
        self.assertEqual(mechanical["status"], "unresolved")
        self.assertEqual(mechanical["unresolved_reason"], "no-independent-reader")
        deterministic = _adjudicate(self.record, cause="environment-infrastructure",
                                    evidence=[_ev(source="tests-oracle", stage="dispatch")])
        self.assertEqual(deterministic["status"], "resolved")
        self.assertEqual(deterministic["cause"], "environment-infrastructure")
        self.assertEqual(deterministic["evidence"][0]["stage"], "dispatch")
        for name in td.REVIEW_ONLY_CLASSES:
            with self.subTest(review_only=name):
                thin = _adjudicate(self.record, cause=name,
                                   contributing=[{"cause": "missing-context",
                                                  "evidence": [_ev(source="tests-oracle")]},
                                                 {"cause": "configuration-permission",
                                                  "evidence": [_ev(source="tests-oracle",
                                                                   ref_id="probe-2")]}],
                                   evidence=[_ev(source="tests-oracle")])
                self.assertEqual(thin["status"], "unresolved")
                self.assertEqual(thin["unresolved_reason"], "no-independent-reader")
                self.assertIsNone(thin["cause"])

    def test_the_ledgers_own_class_supports_nothing_and_its_weight_cannot_be_faked(self):
        """`attempt-outcome` is the candidate route D31 built. Passing it with `weight: review`
        does not make it one: `_evidence_list` re-derives the weight from the source."""
        operational = _adjudicate(self.record, cause="environment-infrastructure",
                                  evidence=[_ev(source="attempt-outcome")])
        self.assertEqual(operational["status"], "unresolved")
        self.assertEqual(operational["unresolved_reason"], "operational-signal-only")
        self.assertEqual(operational["evidence"][0]["weight"], "operational")
        faked = dict(_ev(source="attempt-outcome"), weight="review")
        forged = _adjudicate(self.record, cause="environment-infrastructure", evidence=[faked])
        self.assertEqual(forged["evidence"][0]["weight"], "operational")
        self.assertEqual(forged["unresolved_reason"], "operational-signal-only")

    def test_a_provider_suggestion_is_a_candidate_and_never_the_target(self):
        guessed = _adjudicate(
            self.record, evidence=(),
            suggestion={"by": al.make_ref("synthetic-model", version="fixture/1"),
                        "claim": {"guessed_cause": "missing-context", "confidence": "high"}})
        self.assertEqual(guessed["status"], "unresolved")
        self.assertIsNone(guessed["cause"])
        self.assertEqual(guessed["unresolved_reason"], "provider-suggestion-only")
        self.assertEqual(guessed["provider_suggestion"]["adjudicated"], False)
        self.assertEqual(guessed["provider_suggestion"]["claim"],
                         {"guessed_cause": "missing-context", "confidence": "high"})
        self.assertEqual(guessed["provider_suggestion"]["by"]["id"], "synthetic-model")

    def test_a_claim_or_a_suggestion_using_an_adjudicated_field_name_is_refused(self):
        """The structural half of the three-way separation: a guess may not arrive already
        wearing the target's clothes."""
        for payload in ({"cause": "missing-context"}, {"status": "resolved"},
                        {"evidence": ["a reproduction"]}, {"nested": {"contributing": ["x"]}},
                        {"candidate_cause": "unknown"}, {"corrected.target": "x"}):
            with self.subTest(claim=payload):
                with self.assertRaises(dc.ContractError) as raised:
                    _adjudicate(self.record, claim=payload)
                self.assertEqual(raised.exception.code, "authority-field")
            with self.subTest(suggestion=payload):
                with self.assertRaises(dc.ContractError) as raised:
                    _adjudicate(self.record,
                                suggestion={"by": al.make_ref("m"), "claim": payload})
                self.assertEqual(raised.exception.code, "authority-field")

    def test_a_claim_carrying_input_evidence_is_refused_at_any_depth(self):
        for payload in ({"task_statement": "what it should have been told"},
                        {"findings": [{"observed_error": "written down later"}]},
                        {"input_sha": "0" * 64}):
            with self.subTest(claim=payload):
                with self.assertRaises(dc.ContractError) as raised:
                    _adjudicate(self.record, claim=payload)
                self.assertEqual(raised.exception.code, "authority-field")

    def test_the_three_origins_are_three_slots_and_only_one_is_the_target(self):
        both = _adjudicate(
            self.record, claim={"claimed_cause": "missing-context"},
            suggestion={"by": al.make_ref("synthetic-model"),
                        "claim": {"guessed_cause": "implementation-error"}})
        self.assertEqual(both["status"], "resolved")
        self.assertEqual(both["cause"], "missing-context")
        self.assertEqual(both["operational_observation"],
                         {"class": "unknown", "from_operational": "unknown",
                          "adjudicated": False, "note": td.CANDIDATE_LABEL_NOTE})
        self.assertEqual(both["provider_suggestion"]["claim"],
                         {"guessed_cause": "implementation-error"})
        self.assertEqual(both["provider_suggestion"]["adjudicated"], False)
        self.assertEqual(both["claim"], {"claimed_cause": "missing-context"})

    def test_multiple_causes_needs_each_contributing_cause_separately_supported(self):
        one = _adjudicate(self.record, cause="multiple-causes",
                          contributing=[{"cause": "missing-context", "evidence": [_ev()]}])
        self.assertEqual(one["status"], "unresolved")
        self.assertEqual(one["unresolved_reason"],
                         "contributing-causes-not-separately-supported")
        pooled = _adjudicate(
            self.record, cause="multiple-causes",
            contributing=[{"cause": "missing-context", "evidence": [_ev()]},
                          {"cause": "configuration-permission", "evidence": []}])
        self.assertEqual(pooled["unresolved_reason"],
                         "contributing-causes-not-separately-supported")
        both = _adjudicate(
            self.record, cause="multiple-causes",
            contributing=[{"cause": "missing-context", "evidence": [_ev()]},
                          {"cause": "configuration-permission",
                           "evidence": [_ev(source="tests-oracle", ref_id="probe-2")]}])
        self.assertEqual(both["status"], "resolved")
        self.assertEqual(both["cause"], "multiple-causes")
        self.assertEqual([row["cause"] for row in both["contributing"]],
                         ["missing-context", "configuration-permission"])
        self.assertEqual([row["supported"] for row in both["contributing"]], [True, True])

    def test_a_contributing_cause_named_twice_is_refused(self):
        with self.assertRaises(dc.ContractError) as raised:
            _adjudicate(self.record, cause="multiple-causes",
                        contributing=[{"cause": "missing-context", "evidence": [_ev()]},
                                      {"cause": "missing-context", "evidence": [_ev()]}])
        self.assertEqual(raised.exception.code, "duplicate-entry")

    def test_unresolved_is_not_borrowed_from_the_metric_vocabulary(self):
        """D15's distinction: `insufficient-evidence` means a metric had too few scoreable rows.
        A label with no independent reader is a different situation and gets a different word."""
        de = _load("decision_eval")
        self.assertEqual(set(td.UNSUPPORTED_REASONS) & set(de.METRIC_STATUSES), set())
        self.assertNotIn("insufficient-evidence", td.UNSUPPORTED_REASONS)
        self.assertIn("not-yet-reviewed", td.UNSUPPORTED_REASONS)
        self.assertNotEqual(td.UNADJUDICATED, "unresolved")

    # ---- the reconciliations, patched both ways -----------------------------------------------

    def test_the_evidence_weights_are_an_exact_partition_of_their_owner(self):
        report = td.reconcile_label_sources()
        self.assertEqual(set(report["weight_of"]), set(_load("decision_eval").LABEL_SOURCES))
        self.assertEqual(report["owner"], "bin/decision_eval.py:LABEL_SOURCES")
        self.assertEqual(set(report["weight_of"].values()), set(td.EVIDENCE_WEIGHTS))
        de = td._de()
        with mock.patch.object(de, "LABEL_SOURCES", de.LABEL_SOURCES + ("vibes",)):
            with self.assertRaises(dc.ContractError) as raised:
                td.reconcile_label_sources()
            self.assertEqual(raised.exception.code, "unknown-value")
            self.assertIn("vibes", str(raised.exception))
        with mock.patch.object(de, "LABEL_SOURCES", ("tests-oracle",)):
            with self.assertRaises(dc.ContractError) as raised:
                td.reconcile_label_sources()
            self.assertIn("human-adjudication", str(raised.exception))

    def test_a_human_source_weighed_as_mechanical_is_refused(self):
        """`decision_eval`'s rule is that a human verdict is not ground truth. A person's
        judgement counted as a mechanical reading would let it establish a review-only class
        without an independent reader being what did it."""
        de = td._de()
        with mock.patch.object(de, "HUMAN_LABEL_SOURCES", ("tests-oracle",)):
            with self.assertRaises(dc.ContractError) as raised:
                td.reconcile_label_sources()
            self.assertIn("tests-oracle", str(raised.exception))
        with mock.patch.object(de, "HUMAN_LABEL_SOURCES", ("a-person-nobody-declared",)):
            with self.assertRaises(dc.ContractError) as raised:
                td.reconcile_label_sources()
            self.assertIn("LABEL_SOURCES", str(raised.exception))

    def test_a_censored_attempt_result_reads_as_unknown_and_never_as_a_failure(self):
        de = _load("decision_eval")
        for name in de.RECOVERED_RESULTS:
            self.assertEqual(td.action_outcome(name), "success")
        for name in de.FAILED_RESULTS:
            self.assertEqual(td.action_outcome(name), "failure")
        for name in de.CENSORING_BY_RESULT:
            self.assertEqual(td.action_outcome(name), "unknown")
        self.assertIsNone(td.action_outcome(None))
        with self.assertRaises(dc.ContractError):
            td.action_outcome("invented-result")

    def test_the_action_outcome_map_refuses_a_result_the_owner_moved(self):
        de = td._de()
        with mock.patch.object(de, "FAILED_RESULTS", de.FAILED_RESULTS + ("gave-up",)):
            with self.assertRaises(dc.ContractError) as raised:
                td.reconcile_action_outcomes()
            self.assertIn("gave-up", str(raised.exception))
        with mock.patch.object(de, "FAILED_RESULTS", de.FAILED_RESULTS + ("open",)):
            with self.assertRaises(dc.ContractError) as raised:
                td.reconcile_action_outcomes()
            self.assertEqual(raised.exception.code, "duplicate-entry")
        with mock.patch.object(td, "RESULT_TO_ACTION_OUTCOME",
                               dict(td.RESULT_TO_ACTION_OUTCOME, **{"open": "failure"})):
            with self.assertRaises(dc.ContractError) as raised:
                td.reconcile_action_outcomes()
            self.assertIn("'unknown'", str(raised.exception))
            self.assertIn("open", str(raised.exception))

    # ---- future actions are separate from original inputs -------------------------------------

    def test_an_adjudication_leaves_the_example_byte_identical_and_quotes_none_of_it(self):
        before = td.canonical(self.record)
        entry = _adjudicate(self.record)
        self.assertEqual(td.canonical(self.record), before)
        self.assertEqual(entry["example_id"], self.record["example_id"])
        self.assertEqual(entry["input_sha"], self.record["input_sha"])
        self.assertNotIn("AttributeError", td.canonical(entry))
        self.assertNotIn("input", entry)
        td.assert_intact(self.record)

    def test_a_review_dated_at_or_before_the_decision_is_refused(self):
        """The exact mirror of D31's input rule. A review that could have been an input is not a
        review, and the control is that one instant later is accepted."""
        for decided_at in (PREDICTED, EARLIER):
            with self.subTest(decided_at=decided_at):
                with self.assertRaises(dc.ContractError) as raised:
                    _adjudicate(self.record, decided_at=decided_at)
                self.assertEqual(raised.exception.code, "value-invalid")
                self.assertIn("at-or-before-prediction", str(raised.exception))
        later = _adjudicate(self.record, decided_at="2026-09-19T10:00:01Z")
        self.assertEqual(later["decided_placement"], "after-prediction")

    def test_an_action_record_is_a_separate_artifact_that_places_after_the_decision(self):
        action = td.attach_action(self.record, taken="re-ran the verify command",
                                  outcome=td.action_outcome("verify-failed"),
                                  observed_at=LATER, retries=1,
                                  alternatives=("escalate", "ask for the missing file"),
                                  verification=[_ev(source="tests-oracle", observed_at=LATER)])
        self.assertEqual(action["kind"], "action")
        self.assertEqual(action["outcome"], "failure")
        self.assertEqual(action["placement"], "after-prediction")
        self.assertEqual(action["alternatives"], ["escalate", "ask for the missing file"])
        self.assertEqual(action["retries"], 1)
        self.assertEqual(action["unknown"], ["intervention"])
        self.assertEqual(td.canonical(self.record), td.canonical(_snapshot()))
        for observed_at in (PREDICTED, EARLIER):
            with self.subTest(observed_at=observed_at):
                with self.assertRaises(dc.ContractError) as raised:
                    td.attach_action(self.record, taken="x", outcome="failure",
                                     observed_at=observed_at)
                self.assertEqual(raised.exception.code, "value-invalid")

    def test_the_action_record_has_no_causal_and_no_input_field_in_its_schema(self):
        """The action record has no caller-keyed object, so the enforcement is the CLOSED schema
        rather than a run-time sweep. This pins the exact key set against the two predicates that
        would catch a later `root_cause` or `task_statement` field."""
        action = td.attach_action(self.record, taken="re-ran the verify command",
                                  outcome="failure", observed_at=LATER)
        self.assertEqual(sorted(action), [
            "alternatives", "content_sha", "example_id", "input_sha", "intervention", "kind",
            "notes", "observed_at", "outcome", "placement", "recorded_at", "retries",
            "taken", "taxonomy_v", "unknown", "v", "verification"])
        de = td._de()
        for key in action:
            with self.subTest(key=key):
                self.assertFalse(de._is_causal_key(key))
                # `input_sha` is the one input-shaped name a lifecycle record must carry:
                # POINTING at the input is the whole design, and carrying its digest is how the
                # pointer is checkable. Every other field name is refused by both predicates.
                self.assertEqual(td._is_input_shaped(key), key == "input_sha")
        self.assertIn(de.UNTRIED_ACTION_NOTE, action["notes"])
        self.assertIn(de.NO_CAUSAL_CLAIM, action["notes"])
        self.assertNotIn("optimal", td.canonical(action))

    def test_review_evidence_is_dated_and_placed_so_it_cannot_be_moved_into_an_input(self):
        item = _ev(observed_at=LATER)
        self.assertEqual(item["observed_at"], LATER)
        self.assertEqual(item["weight"], "review")
        self.assertEqual(item["ref"], {"id": "review-1", "sha": None, "v": "fixture/1"})
        self.assertEqual(item["ref_gaps"], ["sha"])
        with self.assertRaises(dc.ContractError) as raised:
            td.review_evidence(source="human-adjudication", ref="review-1", observed_at=LATER)
        self.assertEqual(raised.exception.code, "not-a-reference")
        with self.assertRaises(dc.ContractError) as raised:
            td.review_evidence(source="a-model", ref=al.make_ref("r"), observed_at=LATER)
        self.assertEqual(raised.exception.code, "unknown-value")
        with self.assertRaises(dc.ContractError) as raised:
            _snapshot(input={"code_context": [_entry("the reviewer's diagnosis",
                                                     observed_at=LATER)]})
        self.assertEqual(raised.exception.code, "value-invalid")

    def test_an_adjudication_or_an_action_needs_an_approved_record(self):
        for status in ("unknown", "refused", "expired", "revoked"):
            with self.subTest(status=status):
                doctored = _reseal(self.record, status=status)
                with self.assertRaises(dc.ContractError) as raised:
                    _adjudicate(doctored)
                self.assertEqual(raised.exception.code, "value-invalid")
                with self.assertRaises(dc.ContractError):
                    td.attach_action(doctored, taken="x", outcome="failure", observed_at=LATER)
                revocation = td.revoke(doctored, revoked_at=LATER, reason="withdrawn",
                                       by=al.make_ref("owner"))
                self.assertEqual(revocation["prior_status"], status)

    def test_a_reviewer_must_be_an_independent_reader(self):
        for source in ("tests-oracle", "kit-acceptance", "attempt-outcome"):
            with self.subTest(source=source):
                with self.assertRaises(dc.ContractError) as raised:
                    _adjudicate(self.record, reviewer=_reviewer(source=source))
                self.assertEqual(raised.exception.code, "value-invalid")
        for source in ("human-adjudication", "review-verdict"):
            with self.subTest(source=source):
                entry = _adjudicate(self.record, reviewer=_reviewer(source=source))
                self.assertEqual(entry["reviewer"]["source"], source)
        self.assertEqual(sorted(td.ADJUDICATION_NOT_ESTABLISHED),
                         ["cause-not-experimentally-confirmed", "evidence-not-dereferenced",
                          "reviewer-not-authenticated"])
        self.assertEqual(_adjudicate(self.record)["not_established"],
                         list(td.ADJUDICATION_NOT_ESTABLISHED))

    # ---- correction history and disagreement --------------------------------------------------

    def test_a_correction_appends_and_never_rewrites_the_record_it_supersedes(self):
        first = _adjudicate(self.record, evidence=())
        td.persist_lifecycle(first, self.store)
        raw_before = (self.store / "labels"
                      / f"{self.record['example_id']}.jsonl").read_text("utf-8")
        second = _adjudicate(self.record, prior=first,
                             correction_reason="an independent reader looked at it")
        td.persist_lifecycle(second, self.store)
        lines = (self.store / "labels"
                 / f"{self.record['example_id']}.jsonl").read_text("utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0] + "\n", raw_before)
        self.assertEqual(second["supersedes"], first["content_sha"])
        self.assertEqual(second["correction"]["from_status"], "unresolved")
        self.assertIsNone(second["correction"]["from_cause"])
        state = td.label_state(td.read_lifecycle(self.store, self.record["example_id"],
                                                "adjudication"))
        self.assertEqual(state["status"], "resolved")
        self.assertEqual(state["current"], second["content_sha"])
        self.assertEqual(state["heads"], [second["content_sha"]])
        self.assertEqual(state["recorded"], 2)
        self.assertEqual(state["corrections"],
                         [{"of": first["content_sha"], "to": second["content_sha"],
                           "from_status": "unresolved", "to_status": "resolved",
                           "reason": "an independent reader looked at it"}])

    def test_a_correction_that_re_derived_nothing_is_refused(self):
        first = _adjudicate(self.record)
        with self.assertRaises(dc.ContractError) as raised:
            _adjudicate(self.record, prior=first, correction_reason="saying it again")
        self.assertEqual(raised.exception.code, "value-invalid")
        self.assertIn("re-derived nothing", str(raised.exception))
        moved = _adjudicate(self.record, cause="environment-infrastructure", prior=first,
                            correction_reason="the reproduction pointed at the host")
        self.assertEqual(moved["status"], "resolved")
        self.assertEqual(moved["cause"], "environment-infrastructure")

    def test_a_correction_needs_a_reason_and_a_reason_needs_a_correction(self):
        first = _adjudicate(self.record)
        with self.assertRaises(dc.ContractError) as raised:
            _adjudicate(self.record, cause="configuration-permission", prior=first)
        self.assertEqual(raised.exception.code, "missing-field")
        with self.assertRaises(dc.ContractError) as raised:
            _adjudicate(self.record, correction_reason="nothing to correct")
        self.assertEqual(raised.exception.code, "value-invalid")

    def test_a_correction_of_another_example_or_another_kind_is_refused(self):
        other = _snapshot(input={"observed_error": [_entry("a different error")]})
        first = _adjudicate(other)
        with self.assertRaises(dc.ContractError) as raised:
            _adjudicate(self.record, prior=first, correction_reason="wrong example")
        self.assertEqual(raised.exception.code, "value-invalid")
        action = td.attach_action(self.record, taken="x", outcome="failure", observed_at=LATER)
        with self.assertRaises(dc.ContractError) as raised:
            _adjudicate(self.record, prior=action, correction_reason="wrong kind")
        self.assertEqual(raised.exception.code, "wrong-type")

    def test_two_live_heads_that_disagree_are_disputed_and_no_reviewer_wins(self):
        human = _adjudicate(self.record, reviewer=_reviewer("reviewer-a", "human-adjudication"))
        verdict = _adjudicate(self.record, cause="environment-infrastructure",
                              reviewer=_reviewer("reviewer-b", "review-verdict"),
                              decided_at=REVIEWED_LATER,
                              evidence=[_ev(source="tests-oracle", ref_id="probe-9")])
        state = td.label_state([human, verdict])
        self.assertEqual(state["status"], "disputed")
        self.assertIsNone(state["current"])
        self.assertEqual(sorted(state["heads"]),
                         sorted([human["content_sha"], verdict["content_sha"]]))
        self.assertEqual(state["disagreement"]["causes"],
                         ["environment-infrastructure", "missing-context"])
        self.assertEqual(state["disagreement"]["reviewers"], ["reviewer-a", "reviewer-b"])
        self.assertIsNone(state["disagreement"]["resolved_by"])
        self.assertEqual(state["target"]["eligible"], False)
        self.assertEqual(state["target"]["reason"], "disagreement-unresolved")

    def test_two_live_heads_that_agree_are_corroboration_and_the_later_one_is_current(self):
        early = _adjudicate(self.record, reviewer=_reviewer("reviewer-a"))
        late = _adjudicate(self.record, reviewer=_reviewer("reviewer-b", "review-verdict"),
                           decided_at=REVIEWED_LATER)
        self.assertNotEqual(early["content_sha"], late["content_sha"])
        state = td.label_state([early, late])
        self.assertEqual(state["status"], "resolved")
        self.assertEqual(state["current"], late["content_sha"])
        self.assertEqual(state["disagreement"]["resolved_by"], "agreement")
        self.assertEqual(state["target"]["eligible"], True)
        self.assertEqual(td.label_state([late, early])["current"], late["content_sha"])

    def test_a_disagreement_is_a_target_only_when_every_head_models_ambiguity(self):
        def ambiguous(second, **over):
            base = {"shape": "ambiguity", "cause": None,
                    "contributing": [{"cause": "missing-context", "evidence": [_ev()]},
                                     {"cause": second,
                                      "evidence": [_ev(ref_id="probe-2")]}]}
            base.update(over)
            return _adjudicate(self.record, **base)

        one = ambiguous("configuration-permission")
        two = ambiguous("environment-infrastructure", reviewer=_reviewer("reviewer-b"),
                        decided_at=REVIEWED_LATER)
        state = td.label_state([one, two])
        self.assertEqual(state["status"], "disputed")
        self.assertEqual(state["target"]["eligible"], True)
        self.assertEqual(state["target"]["shape"], "ambiguity")
        mixed = td.label_state([one, _adjudicate(self.record, reviewer=_reviewer("reviewer-c"),
                                                 decided_at=REVIEWED_LATER)])
        self.assertEqual(mixed["status"], "disputed")
        self.assertEqual(mixed["target"]["eligible"], False)

    def test_the_label_status_table_is_an_exact_partition_that_never_returns_to_unadjudicated(
            self):
        self.assertEqual(set(td.LABEL_STATUS_TRANSITIONS), set(td.LABEL_STATUSES))
        reachable = {name for targets in td.LABEL_STATUS_TRANSITIONS.values()
                     for name in targets}
        self.assertEqual(reachable - set(td.LABEL_STATUSES), set())
        self.assertNotIn(td.UNADJUDICATED, reachable)
        self.assertEqual(td.SUPERVISED_TARGET_STATUS, "resolved")
        with self.assertRaises(dc.ContractError) as raised:
            td._assert_label_transition("resolved", td.UNADJUDICATED, changed=True)
        self.assertEqual(raised.exception.code, "unknown-value")
        self.assertEqual(td._assert_label_transition("unresolved", "resolved", changed=True),
                         "resolved")

    def test_an_empty_history_is_not_yet_reviewed_rather_than_unresolved(self):
        state = td.label_state([])
        self.assertEqual(state["status"], td.UNADJUDICATED)
        self.assertEqual(state["recorded"], 0)
        self.assertEqual(state["heads"], [])
        self.assertIsNone(state["current"])
        self.assertIsNone(state["disagreement"])
        self.assertEqual(state["target"], {"eligible": False, "reason": "not-yet-reviewed",
                                          "status": td.UNADJUDICATED, "shape": None,
                                          "cause": None,
                                          "note": "nobody has reviewed this example"})
        with self.assertRaises(dc.ContractError) as raised:
            td.label_state([_adjudicate(self.record),
                            _adjudicate(_snapshot(input={"observed_error":
                                                         [_entry("another error")]}))])
        self.assertEqual(raised.exception.code, "value-invalid")

    # ---- the four explicit schemas ------------------------------------------------------------

    def test_a_no_failure_example_is_evidence_and_is_not_forced_into_the_taxonomy(self):
        clean = _snapshot(operational_class=None)
        entry = _adjudicate(clean, shape="no-failure", cause=None)
        self.assertEqual(entry["status"], "resolved")
        self.assertIsNone(entry["cause"])
        self.assertEqual(entry["contributing"], [])
        self.assertIsNone(entry["operational_observation"]["from_operational"])
        self.assertEqual(td.label_state([entry])["target"]["eligible"], True)
        with self.assertRaises(dc.ContractError) as raised:
            _adjudicate(clean, shape="no-failure")
        self.assertEqual(raised.exception.code, "value-invalid")
        self.assertIn("names no cause", str(raised.exception))

    def test_a_failed_dispatch_cannot_be_adjudicated_as_a_no_failure_example(self):
        with self.assertRaises(dc.ContractError) as raised:
            _adjudicate(self.record, shape="no-failure", cause=None)
        self.assertEqual(raised.exception.code, "value-invalid")
        self.assertIn("classified", str(raised.exception))
        self.assertEqual(self.record["candidate_cause"]["from_operational"], "unknown")
        self.assertIsNone(al.classify_dispatch(0, "everything passed", None))

    def test_a_no_failure_example_still_needs_support(self):
        clean = _snapshot(operational_class=None)
        thin = _adjudicate(clean, shape="no-failure", cause=None, evidence=())
        self.assertEqual(thin["status"], "unresolved")
        self.assertEqual(thin["unresolved_reason"], "no-supporting-evidence")
        operational = _adjudicate(clean, shape="no-failure", cause=None,
                                  evidence=[_ev(source="attempt-outcome")])
        self.assertEqual(operational["unresolved_reason"], "operational-signal-only")

    def test_an_ambiguity_adjudication_needs_two_competing_causes_each_supported(self):
        with self.assertRaises(dc.ContractError) as raised:
            _adjudicate(self.record, shape="ambiguity", cause="missing-context")
        self.assertEqual(raised.exception.code, "value-invalid")
        self.assertIn("no single cause", str(raised.exception))
        with self.assertRaises(dc.ContractError) as raised:
            _adjudicate(self.record, shape="ambiguity", cause=None,
                        contributing=[{"cause": "missing-context", "evidence": [_ev()]}])
        self.assertEqual(raised.exception.code, "value-invalid")
        self.assertIn("at least two", str(raised.exception))
        thin = _adjudicate(self.record, shape="ambiguity", cause=None,
                           contributing=[{"cause": "missing-context", "evidence": [_ev()]},
                                         {"cause": "implementation-error", "evidence": []}])
        self.assertEqual(thin["unresolved_reason"],
                         "contributing-causes-not-separately-supported")
        both = _adjudicate(
            self.record, shape="ambiguity", cause=None,
            contributing=[{"cause": "missing-context", "evidence": [_ev()]},
                          {"cause": "implementation-error",
                           "evidence": [_ev(ref_id="review-2")]}])
        self.assertEqual(both["status"], "resolved")
        self.assertIsNone(both["cause"])
        self.assertEqual(td.QUESTION_SHAPES, ("failure-cause", "no-failure", "ambiguity"))

    def test_an_unknown_shape_or_an_unknown_cause_is_refused(self):
        with self.assertRaises(dc.ContractError) as raised:
            _adjudicate(self.record, shape="whatever")
        self.assertEqual(raised.exception.code, "unknown-value")
        with self.assertRaises(dc.ContractError) as raised:
            _adjudicate(self.record, cause="the tests went red")
        self.assertEqual(raised.exception.code, "unknown-value")
        with self.assertRaises(dc.ContractError) as raised:
            _adjudicate(self.record, cause=None)
        self.assertEqual(raised.exception.code, "missing-field")

    # ---- retention: expiry is acted on --------------------------------------------------------

    def test_retention_is_enforced_against_an_explicit_now_with_no_default_clock(self):
        with self.assertRaises(TypeError):
            td.eligibility_state(self.record)
        self.assertEqual(self.record["eligibility"]["expires_on"], EXPIRES_ON)
        live = td.eligibility_state(self.record, now=IN_RETENTION)
        self.assertEqual(live["state"], "approved")
        self.assertEqual(live["expired"], False)
        self.assertEqual(live["checked_at"], EXPIRES_ON)
        stale = td.eligibility_state(self.record, now=PAST_RETENTION)
        self.assertEqual(stale["state"], "expired")
        self.assertEqual(stale["expired"], True)
        self.assertEqual(stale["reason"], "retention-expired")
        self.assertEqual(stale["declared"], "approved")

    def test_an_expiry_nobody_could_compute_fails_closed_as_unknown(self):
        blind = _reseal(self.record, expires_on=None)
        state = td.eligibility_state(blind, now=IN_RETENTION)
        self.assertEqual(state["state"], "unknown")
        self.assertEqual(state["reason"], "retention-unknown")
        self.assertEqual(state["declared"], "approved")

    def test_a_status_that_was_never_approved_stands_as_it_is(self):
        for status in ("unknown", "refused"):
            with self.subTest(status=status):
                state = td.eligibility_state(_reseal(self.record, status=status),
                                             now=PAST_RETENTION)
                self.assertEqual(state["state"], status)
                self.assertIsNone(state["reason"])
                self.assertEqual(state["terminal"], False)

    def test_the_eligibility_table_is_an_exact_partition_that_renews_nothing(self):
        self.assertEqual(set(td.ELIGIBILITY_TRANSITIONS), set(td.ELIGIBILITY_STATUSES))
        naming_approved = sorted(name for name, targets
                                 in td.ELIGIBILITY_TRANSITIONS.items()
                                 if td.ELIGIBLE_TO_PERSIST in targets)
        self.assertEqual(naming_approved, ["unknown"])
        self.assertEqual(td.ELIGIBILITY_TRANSITIONS["revoked"], ())
        self.assertEqual(td.ELIGIBILITY_TRANSITIONS["expired"], ("revoked",))
        self.assertEqual(td.ELIGIBILITY_TERMINAL, ("revoked",))
        for current in td.ELIGIBILITY_STATUSES:
            with self.subTest(current=current):
                self.assertEqual(td.transition_eligibility(current, "revoked"), "revoked")
        for current in ("expired", "revoked", "refused"):
            with self.subTest(renew=current):
                with self.assertRaises(dc.ContractError) as raised:
                    td.transition_eligibility(current, "approved")
                self.assertEqual(raised.exception.code, "unknown-value")
        self.assertEqual(td.transition_eligibility("unknown", "approved"), "approved")
        with mock.patch.object(td, "ELIGIBILITY_STATUSES",
                               td.ELIGIBILITY_STATUSES + ("suspended",)):
            with self.assertRaises(dc.ContractError) as raised:
                td.transition_eligibility("unknown", "approved")
            self.assertIn("suspended", str(raised.exception))

    # ---- revocation: what it reaches and what it does not ------------------------------------

    def _tombstone(self, **over):
        base = {"revoked_at": "2026-09-21T08:00:00Z",
                "reason": "the owner withdrew this example",
                "by": al.make_ref("owner-1", version="fixture/1")}
        base.update(over)
        return td.revoke(self.record, **base)

    def test_revocation_invalidates_manifests_and_only_identifies_a_checkpoint(self):
        tombstone = self._tombstone(dependents=[
            {"kind": "export-manifest", "ref": al.make_ref("manifest-1")},
            {"kind": "derived-dataset", "ref": al.make_ref("dataset-1")},
            {"kind": "readiness-report", "ref": al.make_ref("report-1")},
            {"kind": "trained-checkpoint", "ref": al.make_ref("checkpoint-1")}])
        self.assertEqual(tombstone["invalidated"], ["dataset-1", "manifest-1", "report-1"])
        self.assertEqual(tombstone["identified"], ["checkpoint-1"])
        self.assertEqual(tombstone["reach_of"], {
            "derived-dataset": "invalidated", "export-manifest": "invalidated",
            "readiness-report": "invalidated", "trained-checkpoint": "identified-only"})
        self.assertEqual(td.REVOCATION_REACH["trained-checkpoint"], "identified-only")
        self.assertEqual(set(td.REVOCATION_REACH.values()), set(td.REACH_LEVELS))
        self.assertEqual(tombstone["reaches"], list(td.REVOCATION_REACHES))
        self.assertEqual(tombstone["status"], "revoked")
        self.assertEqual(tombstone["prior_status"], "approved")

    def test_every_unreached_code_rides_on_every_revocation_unconditionally(self):
        """Nothing discharges one. A revocation naming four dependents and one naming none carry
        the same four codes, and the checkpoint one is among them."""
        self.assertEqual(td.REVOCATION_UNREACHED,
                         ("trained-weights-not-unlearned", "exported-copies-not-recalled",
                          "downstream-artifacts-not-rebuilt", "byte-erasure-not-proven"))
        loaded = self._tombstone(dependents=[
            {"kind": "export-manifest", "ref": al.make_ref("manifest-1")},
            {"kind": "trained-checkpoint", "ref": al.make_ref("checkpoint-1")}])
        bare = self._tombstone()
        for tombstone in (loaded, bare):
            with self.subTest(dependents=len(tombstone["dependents"])):
                self.assertEqual(tombstone["unreached"], list(td.REVOCATION_UNREACHED))
                self.assertEqual(set(tombstone["unreached_notes"]),
                                 set(td.REVOCATION_UNREACHED))
                self.assertIn(td.UNLEARNING_NOTE, tombstone["notes"])
        self.assertEqual(bare["invalidated"], [])
        self.assertEqual(bare["identified"], [])

    def test_no_string_on_a_revocation_claims_a_model_forgot_anything(self):
        """Every unlearning word that appears anywhere on the record appears inside a NEGATION.
        A record that said `weights_cleared` or dropped the `not` would fail here."""
        tombstone = self._tombstone(dependents=[
            {"kind": "trained-checkpoint", "ref": al.make_ref("checkpoint-1")}])
        checked = 0
        for text in _strings(tombstone):
            words = set(td._key_words(text))
            if words & set(td.UNLEARNING_WORDS):
                checked += 1
                lowered = text.lower()
                self.assertTrue(any(mark in lowered
                                    for mark in ("not ", "never", "cannot", "-not-", "neither")),
                                f"unnegated unlearning claim: {text!r}")
        self.assertGreater(checked, 1)
        self.assertIn("trained-weights-not-unlearned", tombstone["unreached"])

    def test_a_dependent_claiming_the_model_unlearned_it_is_refused(self):
        for dependents in (
            [{"kind": "trained-checkpoint", "ref": al.make_ref("c"), "unlearned": True}],
            [{"kind": "trained-checkpoint", "ref": al.make_ref("c"), "weights_purged": True}],
            [{"kind": "trained-checkpoint",
              "ref": {"id": "c", "scrubbedFromWeights": True}}],
            [{"kind": "trained-checkpoint", "ref": al.make_ref("c"), "model-forgot": True}],
        ):
            with self.subTest(dependents=dependents):
                with self.assertRaises(dc.ContractError) as raised:
                    self._tombstone(dependents=dependents)
                self.assertEqual(raised.exception.code, "authority-field")
                self.assertIn("forgot this example", str(raised.exception))

    def test_a_dependent_carrying_input_evidence_or_an_unwalkable_value_is_refused(self):
        for dependents in (
            [{"kind": "export-manifest", "ref": al.make_ref("m"),
              "observed_error": "the error"}],
            [{"kind": "export-manifest", "ref": {"id": "m", "task_statement": "x"}}],
            [{"kind": "export-manifest", "ref": al.make_ref("m"), "blob": b"opaque"}],
            [{"kind": "export-manifest", "ref": al.make_ref("m"), "seen": {"a", "b"}}],
        ):
            with self.subTest(dependents=dependents):
                with self.assertRaises(dc.ContractError) as raised:
                    self._tombstone(dependents=dependents)
                self.assertEqual(raised.exception.code, "authority-field")

    def test_an_unknown_downstream_kind_or_a_reach_table_gap_is_refused(self):
        with self.assertRaises(dc.ContractError) as raised:
            self._tombstone(dependents=[{"kind": "a-blog-post", "ref": al.make_ref("p")}])
        self.assertEqual(raised.exception.code, "unknown-value")
        with mock.patch.object(td, "DOWNSTREAM_KINDS",
                               td.DOWNSTREAM_KINDS + ("fine-tuned-adapter",)):
            with self.assertRaises(dc.ContractError) as raised:
                self._tombstone()
            self.assertIn("fine-tuned-adapter", str(raised.exception))
        with mock.patch.object(td, "REVOCATION_REACH",
                               dict(td.REVOCATION_REACH, **{"trained-checkpoint": "erased"})):
            with self.assertRaises(dc.ContractError) as raised:
                self._tombstone()
            self.assertIn("erased", str(raised.exception))

    def test_a_tombstone_carries_no_input_evidence_and_redacts_its_reason(self):
        text = self.record["input"]["observed_error"][0]["text"]
        tombstone = self._tombstone(
            reason=f"withdrawn after {SYNTHETIC_TOKEN} turned up in the brief")
        serialized = td.canonical(tombstone)
        self.assertNotIn(text, serialized)
        self.assertNotIn("AttributeError", serialized)
        self.assertNotIn(SYNTHETIC_TOKEN, serialized)
        self.assertEqual(tombstone["redactions"], {"anthropic-key": 1})
        clean = self._tombstone(reason="withdrawn at the owner's request")
        self.assertEqual(clean["redactions"], {})
        self.assertEqual(sorted(tombstone["by"]), ["id", "sha", "v"])
        with self.assertRaises(dc.ContractError) as raised:
            self._tombstone(by="owner-1")
        self.assertEqual(raised.exception.code, "not-a-reference")

    def test_revocation_beats_expiry_and_the_declared_status_and_is_terminal(self):
        tombstone = self._tombstone()
        state = td.eligibility_state(self.record, now=PAST_RETENTION,
                                     revocations=[tombstone])
        self.assertEqual(state["state"], "revoked")
        self.assertEqual(state["expired"], False)
        self.assertEqual(state["revoked"], True)
        self.assertEqual(state["terminal"], True)
        self.assertEqual(state["reaches"], list(td.REVOCATION_REACHES))
        self.assertEqual(state["unreached"], list(td.REVOCATION_UNREACHED))
        self.assertEqual(state["revocations"], [tombstone["content_sha"]])
        with self.assertRaises(dc.ContractError) as raised:
            td.eligibility_state(self.record, now=IN_RETENTION,
                                 revocations=[_adjudicate(self.record)])
        self.assertEqual(raised.exception.code, "wrong-type")

    def test_a_revocation_of_another_example_cannot_be_applied_to_this_one(self):
        other = _snapshot(input={"observed_error": [_entry("a different error")]})
        elsewhere = td.revoke(other, revoked_at="2026-09-21T08:00:00Z", reason="withdrawn",
                              by=al.make_ref("owner-1"))
        with self.assertRaises(dc.ContractError) as raised:
            td.eligibility_state(self.record, now=IN_RETENTION, revocations=[elsewhere])
        self.assertEqual(raised.exception.code, "value-invalid")

    # ---- unknown use rights refuse export ----------------------------------------------------

    def _exportable(self, **over):
        base = {"now": IN_RETENTION, "purpose": self.record["eligibility"]["purpose"],
                "destination": "local-development-partition",
                "adjudications": [_adjudicate(self.record)], "revocations": []}
        base.update(over)
        record = base.pop("record", self.record)
        return td.export_eligibility(record, **base)

    def test_a_fully_eligible_example_exports_with_an_empty_refusal_list(self):
        """The positive control. Without it every refusal test below could pass on a gate that
        refuses everything."""
        decision = self._exportable()
        self.assertEqual(decision["refusals"], [])
        self.assertEqual(decision["exportable"], True)
        self.assertEqual(decision["eligibility"]["state"], "approved")
        self.assertEqual(decision["label"]["status"], "resolved")
        self.assertEqual(decision["unreached"], [])
        self.assertEqual(decision["not_established"], list(td.EXPORT_NOT_ESTABLISHED))
        self.assertEqual(set(decision["not_established_notes"]),
                         set(td.EXPORT_NOT_ESTABLISHED))

    def test_unknown_use_rights_refuse_export(self):
        for status, code in (("unknown", "eligibility-unknown"),
                             ("refused", "eligibility-refused")):
            with self.subTest(status=status):
                decision = td.export_eligibility(
                    _reseal(self.record, status=status), now=IN_RETENTION,
                    purpose=self.record["eligibility"]["purpose"],
                    destination="local-development-partition",
                    adjudications=[_adjudicate(self.record)], revocations=[])
                self.assertEqual(decision["exportable"], False)
                self.assertEqual(decision["refusals"], [code])

    def test_every_export_refusal_code_is_reachable_by_its_own_case(self):
        """A code nothing can emit reads as a guard and is not one, so each of the fourteen gets
        a case and their union is asserted to be the whole tuple."""
        adjudicated = [_adjudicate(self.record)]
        unresolved = [_adjudicate(self.record, evidence=())]
        disputed = [_adjudicate(self.record),
                    _adjudicate(self.record, cause="environment-infrastructure",
                                reviewer=_reviewer("reviewer-b", "review-verdict"),
                                decided_at=REVIEWED_LATER,
                                evidence=[_ev(source="tests-oracle", ref_id="probe-9")])]
        broken = td._copy(dict(self.record))
        broken["eligibility"] = dict(broken["eligibility"], purpose="a purpose nobody declared")
        cases = {
            "record-not-intact": dict(record=broken),
            "retention-unknown": dict(record=_reseal(self.record, expires_on=None)),
            "eligibility-unknown": dict(record=_reseal(self.record, status="unknown")),
            "eligibility-refused": dict(record=_reseal(self.record, status="refused")),
            "eligibility-expired": dict(now=PAST_RETENTION),
            "eligibility-revoked": dict(revocations=[self._tombstone()]),
            "label-not-checked": dict(adjudications=None),
            "label-unadjudicated": dict(adjudications=[]),
            "label-unresolved": dict(adjudications=unresolved),
            "label-disputed": dict(adjudications=disputed),
            "revocation-not-checked": dict(revocations=None),
            "purpose-not-declared": dict(purpose=None),
            "purpose-outside-scope": dict(purpose="export it wherever it is wanted"),
            "destination-not-declared": dict(destination=None),
        }
        self.assertEqual(sorted(cases), sorted(td.EXPORT_REFUSALS))
        seen = set()
        for code, over in sorted(cases.items()):
            with self.subTest(code=code):
                record = over.pop("record", self.record)
                base = {"now": IN_RETENTION,
                        "purpose": self.record["eligibility"]["purpose"],
                        "destination": "local-development-partition",
                        "adjudications": adjudicated, "revocations": []}
                base.update(over)
                decision = td.export_eligibility(record, **base)
                self.assertIn(code, decision["refusals"])
                if code == "record-not-intact":
                    self.assertEqual(decision["refusals"], ["record-not-intact"])
                    self.assertIsNone(decision["eligibility"])
                self.assertEqual(decision["exportable"], False)
                seen.update(decision["refusals"])
        self.assertEqual(seen, set(td.EXPORT_REFUSALS))

    def test_a_refusal_the_vocabulary_does_not_name_is_refused_rather_than_returned(self):
        """`EXPORT_REFUSALS` is what a caller branches on and what a report counts, so the
        emitter is checked against it rather than trusted to agree. Reached the only honest way:
        by shrinking the vocabulary and watching the decision refuse to answer in it."""
        shrunk = tuple(name for name in td.EXPORT_REFUSALS if name != "purpose-outside-scope")
        with mock.patch.object(td, "EXPORT_REFUSALS", shrunk):
            with self.assertRaises(dc.ContractError) as raised:
                self._exportable(purpose="export it wherever it is wanted")
            self.assertEqual(raised.exception.code, "unknown-value")
            self.assertIn("purpose-outside-scope", str(raised.exception))
            self.assertEqual(self._exportable()["refusals"], [])

    def test_an_unmade_check_is_not_a_passed_check(self):
        """Passing nothing is not "there were none": a gate that treated absence as an all-clear
        would let a revoked example export because nobody looked."""
        blind = td.export_eligibility(self.record, now=IN_RETENTION,
                                      purpose=self.record["eligibility"]["purpose"],
                                      destination="local-development-partition")
        self.assertEqual(sorted(blind["refusals"]),
                         ["label-not-checked", "revocation-not-checked"])
        self.assertEqual(blind["checked"], "caller")
        self.assertEqual(blind["exportable"], False)

    def test_the_gate_reads_the_store_itself_when_it_is_given_one(self):
        td.persist_lifecycle(_adjudicate(self.record), self.store)
        allowed = td.export_eligibility(self.record, now=IN_RETENTION,
                                        purpose=self.record["eligibility"]["purpose"],
                                        destination="local-development-partition",
                                        store_dir=self.store)
        self.assertEqual(allowed["refusals"], [])
        self.assertEqual(allowed["checked"], "store")
        td.persist_lifecycle(self._tombstone(), self.store)
        refused = td.export_eligibility(self.record, now=IN_RETENTION,
                                        purpose=self.record["eligibility"]["purpose"],
                                        destination="local-development-partition",
                                        store_dir=self.store)
        self.assertEqual(refused["refusals"], ["eligibility-revoked"])
        self.assertEqual(refused["unreached"], list(td.REVOCATION_UNREACHED))
        self.assertIn(td.UNLEARNING_NOTE, refused["notes"])

    def test_a_declared_purpose_is_compared_and_the_comparison_says_what_it_is(self):
        decision = self._exportable(purpose="train a local failure-cause classifier")
        self.assertEqual(decision["refusals"], ["purpose-outside-scope"])
        self.assertEqual(decision["permitted_purpose"],
                         self.record["eligibility"]["purpose"])
        self.assertIn("purpose-strings-compared-not-interpreted", decision["not_established"])
        self.assertIn("cannot read intent",
                      decision["not_established_notes"]
                      ["purpose-strings-compared-not-interpreted"])

    def test_nothing_in_the_decision_reaches_a_destination_or_writes_a_file(self):
        before = sorted(str(p) for p in self.tmp.rglob("*"))
        decision = self._exportable()
        self.assertEqual(decision["exportable"], True)
        self.assertEqual(sorted(str(p) for p in self.tmp.rglob("*")), before)
        self.assertFalse(self.store.exists())
        self.assertIn("destination-not-contacted", decision["not_established"])
        self.assertIn("enforcement-not-provided", decision["not_established"])

    # ---- the store: keyed by example, confined, and never created by a read -------------------

    def test_lifecycle_records_are_keyed_by_example_and_land_where_the_reader_looks(self):
        entry = _adjudicate(self.record)
        receipt = td.persist_lifecycle(entry, self.store)
        self.assertEqual(receipt["written"], True)
        self.assertTrue(receipt["path"].endswith(
            f"labels/{self.record['example_id']}.jsonl"))
        self.assertEqual(td.read_lifecycle(self.store, self.record["example_id"],
                                           "adjudication"), [entry])
        self.assertEqual(td.read_lifecycle(self.store, self.record["example_id"], "action"), [])
        again = td.persist_lifecycle(entry, self.store)
        self.assertEqual(again["written"], False)
        self.assertEqual(again["reason"], "already-recorded")
        self.assertEqual(len(td.read_lifecycle(self.store, self.record["example_id"],
                                               "adjudication")), 1)

    def test_a_reader_does_not_create_the_store_and_an_unknown_kind_is_refused(self):
        self.assertEqual(td.read_lifecycle(self.store, self.record["example_id"],
                                           "revocation"), [])
        self.assertFalse(self.store.exists())
        with self.assertRaises(dc.ContractError) as raised:
            td.read_lifecycle(self.store, self.record["example_id"], "opinion")
        self.assertEqual(raised.exception.code, "unknown-value")
        self.assertFalse(self.store.exists())

    def test_an_example_id_that_could_name_a_path_is_refused_before_it_becomes_one(self):
        for example_id in ("a/b/c", ".hidden", "../escape", "/etc/passwd", "ex-XYZ",
                           "ex-" + "0" * 15, ""):
            with self.subTest(example_id=example_id):
                with self.assertRaises(dc.ContractError):
                    td.read_lifecycle(self.store, example_id, "adjudication")
                self.assertFalse(self.store.exists())
        self.assertEqual(td._example_id("ex-" + "0" * 16), "ex-" + "0" * 16)

    def test_a_tampered_or_foreign_lifecycle_line_is_refused_on_read(self):
        entry = _adjudicate(self.record)
        td.persist_lifecycle(entry, self.store)
        path = self.store / "labels" / f"{self.record['example_id']}.jsonl"
        stored = json.loads(path.read_text(encoding="utf-8").strip())
        stored["cause"] = "implementation-error"
        path.write_text(td.canonical(stored) + "\n", encoding="utf-8")
        with self.assertRaises(dc.ContractError) as raised:
            td.read_lifecycle(self.store, self.record["example_id"], "adjudication")
        self.assertEqual(raised.exception.code, "value-invalid")
        self.assertIn("content_sha_ok", str(raised.exception))
        path.write_text(json.dumps({"v": "something.else/1", "kind": "adjudication"}) + "\n",
                        encoding="utf-8")
        with self.assertRaises(dc.ContractError) as raised:
            td.read_lifecycle(self.store, self.record["example_id"], "adjudication")
        self.assertEqual(raised.exception.code, "unknown-value")
        action = td.attach_action(self.record, taken="x", outcome="failure", observed_at=LATER)
        path.write_text(td.canonical(action) + "\n", encoding="utf-8")
        with self.assertRaises(dc.ContractError) as raised:
            td.read_lifecycle(self.store, self.record["example_id"], "adjudication")
        self.assertIn("in the 'adjudication' file", str(raised.exception))

    def test_the_bytes_on_disk_are_the_records_own_canonical_form(self):
        entry = _adjudicate(self.record)
        td.persist_lifecycle(entry, self.store)
        path = self.store / "labels" / f"{self.record['example_id']}.jsonl"
        self.assertEqual(path.read_text(encoding="utf-8"), td.canonical(entry) + "\n")
        self.assertEqual(td.lifecycle_integrity(entry)["content_sha_ok"], True)
        with self.assertRaises(dc.ContractError) as raised:
            td.lifecycle_integrity(dict(self.record))
        self.assertEqual(raised.exception.code, "not-a-reference")

    def test_a_history_past_its_ceiling_refuses_rather_than_dropping_the_oldest(self):
        first = _adjudicate(self.record)
        second = _adjudicate(self.record, cause="configuration-permission")
        with mock.patch.object(td, "MAX_LIFECYCLE_ENTRIES", 1):
            td.persist_lifecycle(first, self.store)
            with self.assertRaises(dc.ContractError) as raised:
                td.persist_lifecycle(second, self.store)
            self.assertEqual(raised.exception.code, "bounds-exceeded")
        self.assertEqual(len(td.read_lifecycle(self.store, self.record["example_id"],
                                               "adjudication")), 1)

    def test_the_bounded_lists_refuse_rather_than_truncate(self):
        many = [_ev(ref_id=f"review-{index}") for index in range(td.MAX_EVIDENCE + 1)]
        with self.assertRaises(dc.ContractError) as raised:
            _adjudicate(self.record, evidence=many)
        self.assertEqual(raised.exception.code, "bounds-exceeded")
        dependents = [{"kind": "export-manifest", "ref": al.make_ref(f"m{index}")}
                      for index in range(td.MAX_DEPENDENTS + 1)]
        with self.assertRaises(dc.ContractError) as raised:
            self._tombstone(dependents=dependents)
        self.assertEqual(raised.exception.code, "bounds-exceeded")
        rows = [{"cause": name, "evidence": [_ev()]} for name in td.CAUSE_CLASSES]
        with mock.patch.object(td, "MAX_CONTRIBUTING", 2):
            with self.assertRaises(dc.ContractError) as raised:
                _adjudicate(self.record, cause="multiple-causes", contributing=rows)
            self.assertEqual(raised.exception.code, "bounds-exceeded")

    def test_the_lifecycle_writes_through_the_confined_helper_and_nothing_else(self):
        source = (BIN_DIR / "training_data.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("sp.confined_append_bytes("), 2)
        self.assertEqual(source.count("sp.confined_read_bytes("), 2)
        self.assertNotIn("open(", source.replace("os.open(", ""))
        self.assertNotIn("Path.home", source)
        self.assertNotIn("datetime.date.today", source)
        self.assertNotIn("utcnow", source)

    # ---- the demo shows the whole lifecycle, offline -----------------------------------------

    def test_the_demo_walks_capture_to_refused_re_export_and_leaves_nothing_behind(self):
        before = sorted(p.name for p in Path(tempfile.gettempdir()).glob("training-demo-*"))
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = td._cli(["demo", "--json"])
        self.assertEqual(code, 0)
        steps = {step["step"]: step for step in json.loads(buffer.getvalue())["steps"]}
        self.assertEqual(steps["unsupported claim"]["cause"], None)
        self.assertEqual(steps["unsupported claim"]["status"], "unresolved")
        self.assertEqual(steps["reviewed and corrected"]["status"], "resolved")
        self.assertEqual(steps["reviewed and corrected"]["corrections"], 1)
        self.assertEqual(steps["export decided"]["exportable"], True)
        self.assertEqual(steps["retention expired"]["refusals"], ["eligibility-expired"])
        self.assertEqual(steps["revoked"]["identified"], ["checkpoint-1"])
        self.assertEqual(steps["revoked"]["invalidated"], ["manifest-1"])
        self.assertEqual(steps["revoked"]["unreached"], list(td.REVOCATION_UNREACHED))
        self.assertEqual(steps["re-export refused"]["exportable"], False)
        self.assertEqual(steps["re-export refused"]["refusals"], ["eligibility-revoked"])
        after = sorted(p.name for p in Path(tempfile.gettempdir()).glob("training-demo-*"))
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
