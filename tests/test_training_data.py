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


if __name__ == "__main__":
    unittest.main()
