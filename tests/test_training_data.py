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
import inspect
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
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
        # Two reads were D31's and D32's (`read_snapshots`, `read_lifecycle`); the other four are
        # D33's dataset files -- two in `write_dataset` (the already-exported check and the
        # differing-bytes compare) and two in `read_dataset` (the manifest and the data files).
        # `DatasetExportTests` pins the safe_paths SURFACE as an exact set, which is the form of
        # this claim that does not have to be re-counted every time the file grows.
        self.assertEqual(source.count("sp.confined_read_bytes("), 6)
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


# ==================================================================================================
#  D33 -- GROUPED DATASET SPLITS AND REPRODUCIBLE LOCAL EXPORTS
# ==================================================================================================

we = td._wf()

#: The one repository and commit every fixture manifest is built over. Synthetic by its own
#: spelling: no real repository was read and no real commit is named anywhere below.
FIXTURE_REPO = "synthetic://fixture-repo"
FIXTURE_BASE = "0" * 40
FIXTURE_ACCEPTANCE = "python3 run_tests.py"

NOW = "2026-09-20T09:00:00Z"
BUILT_AT = "2026-09-20T10:00:00Z"
BUILT_BY = "synthetic-operator"

#: Strings that exist ONLY so their presence can be searched for. A payload line must not contain
#: any of them; an audit line must contain all of them. Distinctive on purpose: a short id could
#: appear in ordinary text by coincidence and prove nothing either way.
AUDIT_ONLY_SOURCE = "verify-tail-provenance-marker"
AUDIT_ONLY_REVIEWER = "reviewer-provenance-marker"
AUDIT_ONLY_EVIDENCE = "review-ref-provenance-marker"

#: Every stdlib primitive that could reach a network, a shell or another process. Armed with a
#: raiser for the whole of an export, with a control below that CALLS two of them so the trap is
#: proven armed rather than inert. The probe list IS this list -- `_ArmedSeams` asserts it.
STDLIB_SEAMS = (("socket", "socket"), ("socket", "create_connection"), ("socket", "getaddrinfo"),
                ("urllib.request", "urlopen"), ("http.client", "HTTPConnection"),
                ("http.client", "HTTPSConnection"), ("subprocess", "run"), ("subprocess", "Popen"),
                ("subprocess", "call"), ("subprocess", "check_call"),
                ("subprocess", "check_output"), ("os", "system"), ("os", "popen"),
                ("os", "execv"), ("os", "fork"), ("shutil", "which"))

#: Every `workflow_eval` entry point that WRITES (its manifests, its exposure log, its policy
#: files) or dispatches. D33 reads that module and must reach none of these: the evals store has one
#: writer and this is not it.
WF_SEAMS = ("write_manifest", "record_exposure", "record_results", "retire", "declare_cohort",
            "select_cohort", "default_runner", "apply_proposal")


def _diff(path):
    """A synthetic unified diff. Nothing here came out of a real repository."""
    return (f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"
            f"@@ -1,1 +1,1 @@\n-    old_call()\n+    new_call()\n")


def _task(task_id, *, issue=None, statement=None, reference_patch=None):
    """A mined-task record shaped like `repo_bench`'s pinned schema, invented from nothing."""
    return {"task_id": task_id, "mode": "issue-replay", "issue": issue,
            "base_commit": FIXTURE_BASE, "fix_commit": None, "subject": "",
            "statement": statement or f"the adapter drops a record in {task_id}",
            "statement_source": "issue",
            "reference_patch": reference_patch or _diff(f"src/{task_id}.py"),
            "setup_patch": None, "test_blobs": {}, "oracle_tests_available": True,
            "size_profile": "S", "labels": [], "notes": []}


def _pool():
    """Two variants of defect 1 and one of defect 2 -> two groups, one of them of size two.

    The group of two is what a split-refusal test needs, and the uneven sizes are what makes the
    determinism assertions non-vacuous: with one group of one item, `sorted()` pins nothing.
    """
    return [_task("T-1", issue=1), _task("T-2", issue=1), _task("T-3", issue=2)]


def _eval_manifest(tasks=None, *, allocation=None, on_leak="reject"):
    return we.build_manifest(FIXTURE_REPO, FIXTURE_BASE, _pool() if tasks is None else tasks,
                             allocation=allocation or {"development": 1}, on_leak=on_leak,
                             acceptance=FIXTURE_ACCEPTANCE, created_by="fixture",
                             created_at="2026-09-19T00:00:00+00:00")


def _dsnap(task_id, text, *, question=None, source=AUDIT_ONLY_SOURCE, sources=None):
    """One snapshot that joins to a mined task by `sources.task_ref`."""
    refs = {"attempt_ref": al.make_ref("a1b2c3d4", version=al.LEDGER_VERSION)}
    if task_id is not None:
        refs["task_ref"] = al.make_ref(task_id)
    return _snapshot(question=question or _question(),
                     sources=refs if sources is None else sources,
                     input={"observed_error": [_entry(text, source=source)]})


def _forge(record, mutate):
    """A record whose content was altered and whose THREE digests were correctly recomputed.

    D18's lesson made concrete: `build_trial_protocol` computes a correct digest over forged
    inputs, so a matching digest proves alteration was absent and never that the input was real.
    `assert_intact` therefore passes on everything this produces, which is exactly why the export
    re-derives placement itself instead of trusting the capture that is supposed to have happened.
    """
    forged = json.loads(json.dumps(record))
    mutate(forged)
    immutable = {"input": forged["input"], "question": forged["question"],
                 "boundary": forged["boundary"], "sources": forged["sources"],
                 "prediction_at": forged["prediction_at"]}
    forged["input_sha"] = td._sha(immutable)
    forged["example_id"] = f"ex-{forged['input_sha'][:16]}"
    forged.pop("content_sha", None)
    forged["content_sha"] = td._sha(forged)
    return forged


class _RaisingSeam:
    """A seam that fails loudly when reached.

    Not a mock returning a canned value: a canned return is indistinguishable from a real result
    that happened to be ignored, and it would let a leaked call pass silently.
    """

    def __init__(self, name):
        self.name = name
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError(f"seam {self.name!r} was reached: args={args!r} kwargs={kwargs!r}")


class _ArmedSeams:
    """Arms every `STDLIB_SEAMS` and `WF_SEAMS` name with a raiser, and restores them after."""

    def __init__(self, test):
        self.test = test
        self.patches = []
        self.armed = []

    def __enter__(self):
        for module, attr in STDLIB_SEAMS:
            patch = mock.patch(f"{module}.{attr}", _RaisingSeam(f"{module}.{attr}"))
            patch.start()
            self.patches.append(patch)
            self.armed.append(f"{module}.{attr}")
        for attr in WF_SEAMS:
            self.test.assertTrue(hasattr(we, attr), f"workflow_eval has no {attr!r} to arm")
            patch = mock.patch.object(we, attr, _RaisingSeam(f"workflow_eval.{attr}"))
            patch.start()
            self.patches.append(patch)
            self.armed.append(f"workflow_eval.{attr}")
        # The probe list IS the forbidden list, by name. A shorter one would let a leak through a
        # seam nobody replaced while every "nothing was called" assertion still passed.
        self.test.assertEqual(
            self.armed,
            [f"{module}.{attr}" for module, attr in STDLIB_SEAMS]
            + [f"workflow_eval.{attr}" for attr in WF_SEAMS])
        return self

    def __exit__(self, *exc):
        for patch in reversed(self.patches):
            patch.stop()
        return False


class DatasetExportTests(unittest.TestCase):
    """D33: grouped splits, deterministic local exports, immutable manifests. All offline.

    WHICH TASK PREVENTS AND WHICH ONLY DECIDES. D32's `export_eligibility` DECIDES -- it returns
    refusal codes and carries `enforcement-not-provided` unconditionally. D33 is the CALLER that
    acts on that decision: `build_dataset` puts no record with a non-empty refusal list into a
    payload line, so for the one route this module owns -- a local JSONL export -- the gate is
    enforced. `test_the_export_follows_the_gates_verdict_and_has_no_second_eligibility_check`
    proves the reuse by patching the authority and watching the export obey it.

    HOW EACH ACCEPTANCE TERM IS MADE STRUCTURAL RATHER THAN ASSERTED:

      * RELATED ATTEMPTS CANNOT CROSS PROTECTED SPLITS -- a manifest is FORGED so one variant of a
        two-variant defect sits in `promotion` and its digest is recomputed, so the only finding
        `workflow_eval.verify_manifest` reports is `group-split`; the whole export then refuses and
        writes nothing. The partition roles are derived from `PARTITION_ROLES` at call time and
        patched BOTH ways: marking `development` held-out refuses, removing it refuses, and a fifth
        partition appears in the derived held-out list without being named here.
      * EXPOSED OR REVOKED EXAMPLES REFUSE -- a revoked example, an expired one, an item retired in
        `workflow_eval`'s own log and an item exposed for a purpose that is not development's own
        each drop out with their code, with the controls that an exposure for development's OWN
        purpose does not refuse and that a fully eligible record does export. An unread exposure log
        is `exposure-not-checked`, not a clean one.
      * FUTURE-ANSWER LEAKAGE AND MISSING SOURCE REFERENCES FAIL -- placement is re-derived at
        export over a record whose digests were correctly recomputed around a late entry, so the
        one route `assert_intact` cannot see is covered; a quarantined group carries D06's own
        `future-fix-message` screening; and a record naming no task reference, an unknown one, or an
        ambiguous one fails rather than exporting with a gap.
      * REPEATED EXPORT IS DETERMINISTIC -- a fixture with three groups, four included examples and
        four different exclusion codes is exported twice in REVERSED input order and compared BYTE
        for byte, in this process and in two child processes under different `PYTHONHASHSEED`s. The
        dataset id is shown not to move when the declared provenance does.
      * NO NETWORK OR TRAINING ACTION OCCURS -- sixteen stdlib primitives and eight `workflow_eval`
        writers are armed with raisers for a whole build/write/read cycle, with the control test
        that calls two of them and asserts each one bites.
      * AUDIT METADATA IS SEPARATE FROM MODEL INPUTS -- the two closed schemas are asserted to share
        exactly the join key, an input entry's provenance is shown to be absent from the payload
        bytes and present in the audit bytes, and no action record reaches either file.
    """

    maxDiff = None

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="training-d33-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.store = self.tmp / "training"
        self.evals = self.tmp / "evals"
        self.manifest = _eval_manifest()
        self.record = _dsnap("T-1", "AttributeError: no attribute 'emit'")

    # ---- fixture helpers ----------------------------------------------------------------------

    def resolve(self, record, *, reviewer=AUDIT_ONLY_REVIEWER, ref=AUDIT_ONLY_EVIDENCE):
        """Persist `record` and give it a RESOLVED adjudication, the state an export needs."""
        td.persist(record, self.store)
        entry = _adjudicate(record, reviewer=_reviewer(reviewer), evidence=[_ev(ref_id=ref)])
        td.persist_lifecycle(entry, self.store)
        return entry

    def export(self, records=None, **over):
        kwargs = {
            "eval_manifest": self.manifest, "store_dir": self.store, "exposure_dir": self.evals,
            "now": NOW, "purpose": self.record["eligibility"]["purpose"],
            "destination": "local-development-partition",
            "built_at": BUILT_AT, "built_by": BUILT_BY,
        }
        kwargs.update(over)
        return td.build_dataset(self.record if records is None else records, **kwargs)

    def codes(self, dataset, example_id=None):
        rows = dataset["manifest"]["content"]["excluded"]
        if example_id is not None:
            rows = [row for row in rows if row["example_id"] == example_id]
        return sorted({code for row in rows for code in row["refusals"]})

    def eligible_case(self):
        """The positive control: one persisted, adjudicated, exportable record."""
        self.resolve(self.record)
        return self.export([self.record])

    # ---- the positive control, which provably bites -------------------------------------------

    def test_a_fully_eligible_development_record_exports_with_nothing_excluded(self):
        """THE CONTROL for every refusal below. Without it they could all be passing because the
        fixture never exports anything at all."""
        dataset = self.eligible_case()
        content = dataset["manifest"]["content"]
        self.assertEqual(content["counts"], {"offered": 1, "unique": 1,
                                             "duplicates_collapsed": 0, "included": 1,
                                             "excluded": 0, "groups": 1, "items": 1})
        self.assertEqual(content["excluded"], [])
        self.assertEqual(len(dataset["payload"]), 1)
        self.assertEqual(len(dataset["audit_metadata"]), 1)
        self.assertEqual(content["examples"][0]["example_id"], self.record["example_id"])
        self.assertEqual(dataset["payload"][0]["target"],
                         {"shape": "failure-cause", "cause": "missing-context",
                          "contributing": [], "taxonomy_v": td.TAXONOMY_VERSION})
        self.assertEqual(content["included_by_target"], {"failure-cause/missing-context": 1})
        self.assertEqual(content["partition"], td.TRAINABLE_PARTITION)

    # ---- A. related attempts cannot cross protected splits ------------------------------------

    def test_two_variants_of_one_defect_are_one_group_and_land_in_one_partition(self):
        """D06's invariant, read rather than restated: the group the export records is the
        manifest's own, with BOTH variants in it and one partition."""
        first = _dsnap("T-1", "AttributeError: no attribute 'emit'")
        second = _dsnap("T-2", "TypeError: the adapter shape is wrong")
        for record in (first, second):
            self.resolve(record)
        content = self.export([first, second])["manifest"]["content"]
        self.assertEqual(content["counts"]["included"], 2)
        self.assertEqual(content["counts"]["groups"], 1)
        row = list(content["groups"].values())[0]
        self.assertEqual(row["key"], "issue:1")
        self.assertEqual(row["size"], 2)
        self.assertIs(row["solo"], False)
        self.assertEqual(sorted(row["drawn"]), sorted(row["items"]))
        self.assertEqual(row["partition"], td.TRAINABLE_PARTITION)
        self.assertEqual(sorted(row["examples"]),
                         sorted([first["example_id"], second["example_id"]]))

    def test_a_group_split_across_partitions_refuses_the_whole_export(self):
        """THE HEADLINE REFUSAL, and it is refused rather than merely absent from the fixture.

        The manifest is forged so one of defect 1's two variants sits in `promotion`, and its digest
        is recomputed so the ONLY finding `verify_manifest` reports is `group-split` -- otherwise a
        `digest` finding would be doing the refusing and this would prove nothing about grouping.
        """
        first = _dsnap("T-1", "AttributeError: no attribute 'emit'")
        self.resolve(first)
        forged = json.loads(json.dumps(self.manifest))
        content = forged["content"]
        group = next(row for row in content["groups"].values() if len(row["items"]) > 1)
        moved = sorted(group["items"])[0]
        content["items"][moved]["partition"] = "promotion"
        content["partitions"]["development"] = sorted(
            i for i in content["partitions"]["development"] if i != moved)
        content["partitions"]["promotion"] = [moved]
        forged["sha"] = we.manifest_digest(content)
        forged["id"] = forged["sha"][:16]
        findings = we.verify_manifest(forged)
        self.assertEqual(sorted({finding["kind"] for finding in findings}), ["group-split"])
        with self.assertRaises(dc.ContractError) as raised:
            self.export([first], eval_manifest=forged)
        self.assertEqual(raised.exception.code, "value-invalid")
        self.assertIn("group-split", str(raised.exception))
        self.assertFalse((self.store / td.DATASET_DIR).exists())

    def test_the_partition_roles_are_the_owners_and_a_held_out_development_refuses(self):
        """Derived from `PARTITION_ROLES` at call time, and patched BOTH ways."""
        rules = td.dataset_rules()
        self.assertEqual(rules["trainable"], td.TRAINABLE_PARTITION)
        self.assertEqual(rules["partitions"], list(we.PARTITIONS))
        self.assertEqual(set(rules["held_out"]),
                         {n for n in we.PARTITIONS if we.PARTITION_ROLES[n]["held_out"]})
        self.assertEqual(set(rules["single_use"]),
                         {n for n in we.PARTITIONS if we.PARTITION_ROLES[n]["single_use"]})
        self.assertEqual(set(rules["fitting"]),
                         {n for n in we.PARTITIONS if we.PARTITION_ROLES[n]["fitting"]})
        self.assertEqual(set(rules["refused"]), set(we.PARTITIONS) - {td.TRAINABLE_PARTITION})
        self.assertEqual(rules["trainable_purpose"],
                         we.PARTITION_ROLES[td.TRAINABLE_PARTITION]["purpose"])
        self.assertEqual(rules["quarantine_bucket"], we.QUARANTINE)

        held = dict(we.PARTITION_ROLES)
        held[td.TRAINABLE_PARTITION] = dict(held[td.TRAINABLE_PARTITION], held_out=True)
        with mock.patch.object(we, "PARTITION_ROLES", held), \
                mock.patch.object(we, "PARTITIONS", tuple(held)):
            with self.assertRaises(dc.ContractError) as raised:
                td.dataset_rules()
            self.assertEqual(raised.exception.code, "value-invalid")

        renamed = {k: v for k, v in we.PARTITION_ROLES.items() if k != td.TRAINABLE_PARTITION}
        with mock.patch.object(we, "PARTITION_ROLES", renamed), \
                mock.patch.object(we, "PARTITIONS", tuple(renamed)):
            with self.assertRaises(dc.ContractError) as raised:
                td.dataset_rules()
            self.assertEqual(raised.exception.code, "unknown-value")
            self.assertIn(td.TRAINABLE_PARTITION, str(raised.exception))

        widened = dict(we.PARTITION_ROLES)
        widened["shadow"] = {"purpose": "audit-evidence", "fitting": False, "held_out": True,
                             "single_use": True, "note": "a fifth partition nobody here names"}
        with mock.patch.object(we, "PARTITION_ROLES", widened), \
                mock.patch.object(we, "PARTITIONS", tuple(widened)):
            grown = td.dataset_rules()
            self.assertIn("shadow", grown["held_out"])
            self.assertIn("shadow", grown["single_use"])
            self.assertIn("shadow", grown["refused"])

        stale = dict(we.PARTITION_ROLES)
        stale.pop("calibration")
        with mock.patch.object(we, "PARTITION_ROLES", stale):
            with self.assertRaises(dc.ContractError) as raised:
                td.dataset_rules()
            self.assertEqual(raised.exception.code, "unknown-value")
            self.assertIn("calibration", str(raised.exception))

    def test_held_out_and_single_use_material_refuses_and_names_the_role_that_refused_it(self):
        """`promotion` is held out; `audit` is held out AND single-use. The codes say which."""
        self.resolve(self.record)
        for name, expected in (
                ("promotion", ["partition-held-out", "partition-not-trainable"]),
                ("audit", ["partition-held-out", "partition-not-trainable",
                           "partition-single-use"]),
                ("calibration", ["partition-not-trainable"])):
            with self.subTest(partition=name):
                dataset = self.export([self.record],
                                      eval_manifest=_eval_manifest(allocation={name: 1}))
                self.assertEqual(dataset["manifest"]["content"]["counts"]["included"], 0)
                self.assertEqual(self.codes(dataset), expected)
                self.assertEqual(dataset["bytes"]["payload"], b"")

    def test_only_the_trainable_partition_may_be_asked_for(self):
        self.resolve(self.record)
        for name in set(we.PARTITIONS) - {td.TRAINABLE_PARTITION}:
            with self.subTest(partition=name):
                with self.assertRaises(dc.ContractError) as raised:
                    self.export([self.record], partition=name)
                self.assertEqual(raised.exception.code, "value-invalid")

    def test_a_quarantined_group_refuses_and_carries_the_owners_leak_screening(self):
        """D06's lesson exactly: a statement mining the fix leaks the answer into the problem, so
        its WHOLE group is quarantined -- and quarantine is not a partition."""
        leaky = _pool()
        leaky[0] = _task("T-1", issue=1,
                         statement="the adapter drops a record\n" + _diff("src/x.py"))
        manifest = _eval_manifest(leaky, on_leak="quarantine")
        self.assertIn(we.QUARANTINE, {row["partition"]
                                      for row in manifest["content"]["groups"].values()})
        first = _dsnap("T-1", "AttributeError: no attribute 'emit'")
        second = _dsnap("T-2", "TypeError: the adapter shape is wrong")
        for record in (first, second):
            self.resolve(record)
        dataset = self.export([first, second], eval_manifest=manifest)
        self.assertEqual(dataset["manifest"]["content"]["counts"]["included"], 0)
        self.assertEqual(self.codes(dataset, first["example_id"]),
                         ["leak-screened-positive", "partition-not-trainable",
                          "partition-quarantined"])
        # The other variant's OWN statement screens clean. What keeps it out is the
        # contagion D06 states: a leak in one variant quarantines the whole group, because
        # knowing the answer to one is knowing the answer to the other.
        self.assertEqual(self.codes(dataset, second["example_id"]),
                         ["partition-not-trainable", "partition-quarantined"])

    # ---- B. exposed or revoked examples refuse ------------------------------------------------

    def test_the_export_follows_the_gates_verdict_and_has_no_second_eligibility_check(self):
        """REUSE, PROVEN. The authority is patched to refuse, and the export obeys it -- so there
        is no second copy of the eligibility decision deciding otherwise."""
        dataset = self.eligible_case()
        self.assertEqual(dataset["manifest"]["content"]["counts"]["included"], 1)
        real = td.export_eligibility

        def refusing(record, **kwargs):
            answer = real(record, **kwargs)
            answer["exportable"] = False
            answer["refusals"] = ["eligibility-revoked"]
            return answer

        with mock.patch.object(td, "export_eligibility", refusing):
            refused = self.export([self.record])
        self.assertEqual(refused["manifest"]["content"]["counts"]["included"], 0)
        self.assertEqual(self.codes(refused), ["eligibility-revoked"])
        self.assertEqual(refused["bytes"]["payload"], b"")

    def test_a_revoked_or_expired_example_never_reaches_a_payload_line(self):
        self.resolve(self.record)
        tombstone = td.revoke(self.record, revoked_at=LATER, reason="the owner withdrew it",
                              by=al.make_ref("synthetic-owner"))
        td.persist_lifecycle(tombstone, self.store)
        revoked = self.export([self.record])
        self.assertEqual(self.codes(revoked), ["eligibility-revoked"])
        self.assertEqual(revoked["bytes"]["payload"], b"")
        self.assertEqual(revoked["manifest"]["content"]["excluded_by_code"],
                         {"eligibility-revoked": 1})

    def test_an_expired_retention_period_refuses_the_export(self):
        self.resolve(self.record)
        self.assertEqual(self.export([self.record], now=IN_RETENTION)
                         ["manifest"]["content"]["counts"]["included"], 1)
        stale = self.export([self.record], now=PAST_RETENTION)
        self.assertEqual(self.codes(stale), ["eligibility-expired"])

    def test_an_item_exposed_for_another_purpose_or_retired_refuses(self):
        """The mirror of `_held_out_blockers`, for the one partition a fit may happen in. The
        purpose compared against is read from `PARTITION_ROLES` -- and the control is an exposure
        for development's OWN purpose, which does not refuse."""
        self.resolve(self.record)
        item = self.manifest["content"]["partitions"][td.TRAINABLE_PARTITION]
        target = next(iid for iid in item
                      if self.manifest["content"]["items"][iid]["task_id"] == "T-1")
        own = we.PARTITION_ROLES[td.TRAINABLE_PARTITION]["purpose"]
        we.record_exposure(self.evals, self.manifest, partition=td.TRAINABLE_PARTITION,
                           purpose=own, items=[target], by="fixture")
        self.assertEqual(self.export([self.record])["manifest"]["content"]["counts"]["included"],
                         1, "development's own purpose is not an exposure elsewhere")
        we.record_exposure(self.evals, self.manifest, partition=td.TRAINABLE_PARTITION,
                           purpose="inspection", items=[target], by="fixture")
        elsewhere = self.export([self.record])
        self.assertEqual(self.codes(elsewhere), ["item-exposed-elsewhere"])
        we.retire(self.evals, self.manifest, items=[target], reason="contaminated", by="fixture")
        retired = self.export([self.record])
        self.assertEqual(self.codes(retired), ["item-exposed-elsewhere", "item-retired"])

    def test_an_unread_exposure_log_is_not_a_clean_one(self):
        self.resolve(self.record)
        unchecked = self.export([self.record], exposure_dir=None)
        self.assertEqual(self.codes(unchecked), ["exposure-not-checked"])
        exposure = unchecked["manifest"]["content"]["exposure"]
        self.assertEqual(exposure, {"checked": False, "store": None, "entries": None,
                                    "unreadable": None,
                                    "owner": "bin/workflow_eval.py:exposure_state",
                                    "recorded_here": False})

    def test_the_training_store_is_required_so_the_unmade_check_codes_cannot_arise(self):
        """D32's disclosure closed: without `store_dir`, `export_eligibility` answers
        `label-not-checked` + `revocation-not-checked` rather than an all-clear. This export
        demands the store, so neither code can reach a dataset at all."""
        self.resolve(self.record)
        with self.assertRaises(dc.ContractError) as raised:
            self.export([self.record], store_dir=None)
        self.assertEqual(raised.exception.code, "missing-field")
        self.assertIn("label-not-checked", str(raised.exception))
        every = set()
        for records, over in (([self.record], {}),
                              ([self.record], {"exposure_dir": None}),
                              ([_dsnap(None, "no task ref")], {})):
            every.update(self.codes(self.export(records, **over)))
        self.assertEqual(every & {"label-not-checked", "revocation-not-checked"}, set())

    def test_an_unadjudicated_or_disputed_label_refuses_through_the_owners_codes(self):
        td.persist(self.record, self.store)
        self.assertEqual(self.codes(self.export([self.record])), ["label-unadjudicated"])
        thin = _adjudicate(self.record, evidence=[])
        td.persist_lifecycle(thin, self.store)
        self.assertEqual(self.codes(self.export([self.record])), ["label-unresolved"])
        first = _adjudicate(self.record, cause="missing-context",
                            reviewer=_reviewer("reviewer-first"))
        second = _adjudicate(self.record, cause="configuration-permission",
                             reviewer=_reviewer("reviewer-second", source="review-verdict"),
                             evidence=[_ev(source="review-verdict")])
        for entry in (first, second):
            td.persist_lifecycle(entry, self.store)
        self.assertEqual(self.codes(self.export([self.record])), ["label-disputed"])

    def test_a_disagreement_that_is_a_target_still_needs_one_head_to_export(self):
        """Two ambiguity heads naming different competing causes ARE an eligible target for D32 --
        and there is no single adjudication to take one from, so the export refuses rather than
        picking. `target-not-single-headed` is the only code that says so."""
        td.persist(self.record, self.store)
        pairs = (("missing-context", "implementation-error"),
                 ("missing-context", "configuration-permission"))
        for index, (left, right) in enumerate(pairs):
            entry = _adjudicate(
                self.record, shape="ambiguity", cause=None,
                reviewer=_reviewer(f"reviewer-{index}"),
                contributing=[{"cause": left, "evidence": [_ev(ref_id=f"r{index}a")]},
                              {"cause": right, "evidence": [_ev(ref_id=f"r{index}b")]}])
            td.persist_lifecycle(entry, self.store)
        state = td.label_state(td.read_lifecycle(self.store, self.record["example_id"],
                                                 "adjudication"))
        self.assertEqual(state["status"], "disputed")
        self.assertIs(state["target"]["eligible"], True)
        self.assertIsNone(state["current"])
        self.assertEqual(self.codes(self.export([self.record])), ["target-not-single-headed"])

    # ---- C. future-answer leakage and missing source references fail --------------------------

    def test_evidence_from_after_the_decision_fails_at_export_although_its_digests_match(self):
        """The one route `assert_intact` cannot see. The forged record's three digests are all
        correct, so the ONLY thing that can refuse it is placement re-derived here."""
        forged = _forge(self.record, lambda r: r["input"]["observed_error"][0].update(
            {"observed_at": LATER}))
        self.assertEqual(sorted(k for k, v in td.integrity(forged).items()
                                if k.endswith("_ok") and not v), [])
        self.resolve(forged)
        self.assertEqual(self.codes(self.export([forged])), ["input-after-the-decision"])
        control = _forge(self.record, lambda r: r["input"]["observed_error"][0].update(
            {"observed_at": EARLIER}))
        self.resolve(control)
        self.assertEqual(self.export([control])["manifest"]["content"]["counts"]["included"], 1)

    def test_an_entry_nobody_can_place_in_time_refuses_and_the_placements_are_the_owners(self):
        forged = _forge(self.record, lambda r: r["input"]["observed_error"][0].update(
            {"observed_at": "whenever"}))
        self.resolve(forged)
        self.assertEqual(self.codes(self.export([forged])), ["input-placement-unknown"])
        de = _load("decision_eval")
        with mock.patch.object(td._de(), "FACT_PLACEMENTS",
                               tuple(de.FACT_PLACEMENTS) + ("some-fourth-answer",)):
            with self.assertRaises(dc.ContractError) as raised:
                td._placement_codes()
            self.assertEqual(raised.exception.code, "unknown-value")

    def test_a_truncated_entry_refuses_rather_than_exporting_half_an_example(self):
        forged = _forge(self.record,
                        lambda r: r["input"]["observed_error"][0].update({"truncated": True}))
        self.resolve(forged)
        self.assertEqual(self.codes(self.export([forged])), ["input-truncated"])

    def test_an_input_the_export_cannot_walk_refuses_rather_than_being_skipped(self):
        """Two refusals, and the messages are what tell them apart: the outer one names the FIELD
        and its type, the inner one names the entry. Pinned, because otherwise the outer guard
        could be deleted and the inner one would answer for both with a worse diagnostic."""
        field = _forge(self.record, lambda r: r["input"].update({"observed_error": "a string"}))
        self.resolve(field)
        with self.assertRaises(dc.ContractError) as raised:
            self.export([field])
        self.assertEqual(raised.exception.code, "wrong-type")
        self.assertIn("not a list of entries", str(raised.exception))
        self.assertIn("input.observed_error", str(raised.exception))
        entry = _forge(self.record, lambda r: r["input"].update({"observed_error": ["a string"]}))
        self.resolve(entry)
        with self.assertRaises(dc.ContractError) as raised:
            self.export([entry])
        self.assertEqual(raised.exception.code, "wrong-type")
        self.assertIn("not an object", str(raised.exception))

    def test_a_missing_unknown_or_ambiguous_source_reference_fails(self):
        """A record nobody can place in a group cannot be shown not to cross a split."""
        none = _dsnap(None, "no task reference at all")
        self.resolve(none)
        self.assertEqual(self.codes(self.export([none])), ["source-reference-missing"])
        stray = _dsnap("T-NOT-MINED", "a task the manifest never saw")
        self.resolve(stray)
        self.assertEqual(self.codes(self.export([stray])), ["source-not-in-manifest"])
        twins = _pool() + [_task("T-1", issue=99)]
        doubled = _eval_manifest(twins)
        self.resolve(self.record)
        self.assertEqual(self.codes(self.export([self.record], eval_manifest=doubled)),
                         ["source-ambiguous"])

    def test_the_question_wording_cannot_smuggle_the_bookkeeping_into_the_input(self):
        """The route a closed schema cannot close: the question's own text is the caller's, copied
        verbatim out of the record. A question quoting the group id has put the audit metadata
        where a model would read it."""
        group = next(row for row in self.manifest["content"]["groups"].values()
                     if "T-1" in {self.manifest["content"]["items"][i]["task_id"]
                                  for i in row["items"]})
        quoting = dc.parse_question({
            "id": "q-leaky", "version": "1", "kind": "boolean",
            "question": f"Was the attempt in defect group {group['group']} missing a contract?",
            "rubric": {}, "outcomes": ["false", "true"], "abstention": "permitted",
            "dependencies": [], "sensitivity": "project-internal"})
        leaky = _dsnap("T-1", "AttributeError: no attribute 'emit'", question=quoting)
        self.resolve(leaky)
        self.assertEqual(self.codes(self.export([leaky])), ["audit-identity-in-payload"])
        clean = dc.parse_question({
            "id": "q-leaky", "version": "1", "kind": "boolean",
            "question": "Was the attempt in that defect group missing a contract it needed?",
            "rubric": {}, "outcomes": ["false", "true"], "abstention": "permitted",
            "dependencies": [], "sensitivity": "project-internal"})
        control = _dsnap("T-1", "AttributeError: no attribute 'emit'", question=clean)
        self.resolve(control)
        self.assertEqual(self.export([control])["manifest"]["content"]["counts"]["included"], 1)

    # ---- D. repeated export is deterministic --------------------------------------------------

    def mixed_case(self):
        """A fixture with enough SHAPE to order: three groups, four included examples, four
        exclusion codes. D26's trap was a determinism assertion over data too simple to exercise
        it -- with one finding per case, `sorted()` pins nothing and its mutant survives."""
        manifest = _eval_manifest(_pool() + [_task("T-4", issue=3), _task("T-5", issue=4)])
        included, excluded = [], []
        for task_id, text in (("T-1", "AttributeError: no attribute 'emit'"),
                              ("T-2", "TypeError: the adapter shape is wrong"),
                              ("T-3", "KeyError: the route is missing"),
                              ("T-4", "ValueError: the record is malformed")):
            record = _dsnap(task_id, text)
            self.resolve(record)
            included.append(record)
        stray = _dsnap("T-NOT-MINED", "a task the manifest never saw")
        self.resolve(stray)
        excluded.append(stray)
        unlabelled = _dsnap("T-5", "IndexError: the batch is empty")
        td.persist(unlabelled, self.store)
        excluded.append(unlabelled)
        revoked = _dsnap("T-5", "OSError: the adapter refused to close")
        self.resolve(revoked)
        td.persist_lifecycle(td.revoke(revoked, revoked_at=LATER, reason="withdrawn",
                                       by=al.make_ref("owner")), self.store)
        excluded.append(revoked)
        late = _forge(_dsnap("T-5", "TimeoutError: the retry never returned"),
                      lambda r: r["input"]["observed_error"][0].update({"observed_at": LATER}))
        self.resolve(late)
        excluded.append(late)
        return manifest, included + excluded

    def test_the_same_material_exports_to_identical_bytes_whatever_order_it_arrives_in(self):
        manifest, records = self.mixed_case()
        first = self.export(list(records), eval_manifest=manifest)
        second = self.export(list(reversed(records)), eval_manifest=manifest)
        content = first["manifest"]["content"]
        self.assertEqual(content["counts"]["included"], 4)
        self.assertEqual(content["counts"]["excluded"], 4)
        self.assertEqual(content["counts"]["groups"], 3)
        self.assertEqual(sorted(content["excluded_by_code"]),
                         ["eligibility-revoked", "input-after-the-decision",
                          "label-unadjudicated", "source-not-in-manifest"])
        self.assertEqual(first["bytes"], second["bytes"])
        self.assertEqual(first["manifest"]["dataset_id"], second["manifest"]["dataset_id"])

    def test_the_dataset_id_does_not_move_when_the_declared_provenance_does(self):
        manifest, records = self.mixed_case()
        first = self.export(records, eval_manifest=manifest)
        later = self.export(records, eval_manifest=manifest, built_at="2027-01-01T00:00:00Z",
                            built_by="somebody-else")
        self.assertEqual(first["manifest"]["sha"], later["manifest"]["sha"])
        self.assertEqual(first["manifest"]["dataset_id"], later["manifest"]["dataset_id"])
        self.assertEqual(first["bytes"]["payload"], later["bytes"]["payload"])
        self.assertEqual(first["bytes"]["audit_metadata"], later["bytes"]["audit_metadata"])
        self.assertNotEqual(first["bytes"]["manifest"], later["bytes"]["manifest"])
        self.assertEqual(sorted(first["manifest"]["digest"]["excludes"]),
                         ["built_at", "built_by", "dataset_id", "digest", "sha"])
        for excluded in first["manifest"]["digest"]["excludes"]:
            self.assertNotIn(excluded, first["manifest"]["content"])

    def test_the_same_record_offered_twice_is_one_payload_line_and_a_counted_duplicate(self):
        self.resolve(self.record)
        once = self.export([self.record])
        twice = self.export([self.record, self.record, self.record])
        self.assertEqual(twice["bytes"]["payload"], once["bytes"]["payload"])
        self.assertEqual(twice["manifest"]["content"]["counts"],
                         dict(once["manifest"]["content"]["counts"], offered=3,
                              duplicates_collapsed=2))
        other = _forge(self.record, lambda r: r.update({"captured_at": "2026-09-19T10:00:06Z"}))
        other["example_id"] = self.record["example_id"]
        other.pop("content_sha")
        other["content_sha"] = td._sha(other)
        with self.assertRaises(dc.ContractError) as raised:
            self.export([self.record, other])
        self.assertEqual(raised.exception.code, "duplicate-entry")

    def test_the_digest_is_stable_across_processes_and_hash_seeds(self):
        """The failure a same-process assertion cannot see: a set's iteration order, or a dict keyed
        by something str-hashed, reaching the canonical bytes. Two interpreters, two
        PYTHONHASHSEEDs, one id -- or this dataset is not content-addressed at all."""
        manifest, records = self.mixed_case()
        dataset = self.export(records, eval_manifest=manifest)
        script = self.tmp / "reexport.py"
        script.write_text(
            "import importlib.util, json, sys\n"
            "from pathlib import Path\n"
            "def load(p, n):\n"
            "    s = importlib.util.spec_from_file_location(n, p)\n"
            "    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m\n"
            "td = load(sys.argv[1], 'td_child')\n"
            "payload = json.loads(Path(sys.argv[2]).read_text())\n"
            "out = td.build_dataset(payload['records'], eval_manifest=payload['manifest'],\n"
            "                       store_dir=payload['store'], exposure_dir=payload['evals'],\n"
            "                       now=payload['now'], purpose=payload['purpose'],\n"
            "                       destination=payload['destination'],\n"
            "                       built_at=payload['built_at'], built_by=payload['built_by'])\n"
            "print(out['manifest']['dataset_id'], out['manifest']['sha'])\n",
            encoding="utf-8")
        handoff = self.tmp / "handoff.json"
        handoff.write_text(json.dumps({
            "records": records, "manifest": manifest, "store": str(self.store),
            "evals": str(self.evals), "now": NOW,
            "purpose": self.record["eligibility"]["purpose"],
            "destination": "local-development-partition",
            "built_at": BUILT_AT, "built_by": BUILT_BY}), encoding="utf-8")
        seen = set()
        for seed in ("0", "424242"):
            env = dict(os.environ, PYTHONHASHSEED=seed,
                       POLYTROPOS_DATA_HOME=str(self.tmp / "child-home"))
            proc = subprocess.run(
                [sys.executable, "-B", str(script), str(BIN_DIR / "training_data.py"),
                 str(handoff)], capture_output=True, text=True, env=env)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            seen.add(proc.stdout.strip())
        self.assertEqual(
            seen, {f"{dataset['manifest']['dataset_id']} {dataset['manifest']['sha']}"})

    # ---- the immutable artifact on disk -------------------------------------------------------

    def test_writing_twice_keeps_the_first_and_differing_content_under_one_id_refuses(self):
        dataset = self.eligible_case()
        first = td.write_dataset(dataset, self.store)
        self.assertEqual((first["written"], first["reason"]), (True, None))
        root = self.store / td.DATASET_DIR / dataset["manifest"]["dataset_id"]
        before = {name: (root / name).read_bytes() for name in sorted(td.DATASET_FILES.values())}
        second = td.write_dataset(dataset, self.store)
        self.assertEqual((second["written"], second["reason"]), (False, "already-exported"))
        self.assertEqual({name: (root / name).read_bytes()
                          for name in sorted(td.DATASET_FILES.values())}, before)
        forged = json.loads(json.dumps(dataset["manifest"]))
        forged["content"]["counts"]["included"] = 99
        forged["sha"] = td._sha(forged["content"])
        forged["dataset_id"] = dataset["manifest"]["dataset_id"]
        with self.assertRaises(dc.ContractError) as raised:
            td.write_dataset(dict(dataset, manifest=forged), self.store)
        self.assertEqual(raised.exception.code, "value-invalid")
        forged["dataset_id"] = f"ds-{forged['sha'][:16]}"
        renamed = dict(dataset, manifest=forged)
        self.assertNotEqual(renamed["manifest"]["dataset_id"],
                            dataset["manifest"]["dataset_id"],
                            "different content is a different dataset, not a collision")
        self.assertEqual(td.write_dataset(renamed, self.store)["written"], True)

    def test_a_rewritten_export_is_detected_on_read(self):
        dataset = self.eligible_case()
        td.write_dataset(dataset, self.store)
        did = dataset["manifest"]["dataset_id"]
        loaded = td.read_dataset(self.store, did)
        self.assertEqual(loaded["payload"], dataset["payload"])
        self.assertEqual(loaded["audit_metadata"], dataset["audit_metadata"])
        self.assertEqual(loaded["manifest"]["sha"], dataset["manifest"]["sha"])
        root = self.store / td.DATASET_DIR / did
        original = (root / "payload.jsonl").read_bytes()
        (root / "payload.jsonl").write_bytes(original.replace(b"missing-context",
                                                             b"implementation-error"))
        with self.assertRaises(dc.ContractError) as raised:
            td.read_dataset(self.store, did)
        self.assertEqual(raised.exception.code, "value-invalid")
        (root / "payload.jsonl").write_bytes(original)
        body = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        body["content"]["counts"]["included"] = 42
        (root / "manifest.json").write_text(td.canonical(body) + "\n", encoding="utf-8")
        with self.assertRaises(dc.ContractError) as raised:
            td.read_dataset(self.store, did)
        self.assertEqual(raised.exception.code, "value-invalid")

    def test_a_reader_does_not_create_the_store_and_a_bad_id_is_refused_first(self):
        with self.assertRaises(dc.ContractError):
            td.read_dataset(self.store, "ds-0123456789abcdef")
        self.assertFalse(self.store.exists())
        for bad in ("a/b/c", "../escape", "/etc/passwd", ".hidden", "ds-not-hex-at-all"):
            with self.subTest(dataset_id=bad):
                with self.assertRaises(dc.ContractError) as raised:
                    td.read_dataset(self.store, bad)
                self.assertEqual(raised.exception.code, "value-invalid")
                self.assertFalse(self.store.exists())

    def test_the_export_writes_only_the_three_files_under_the_training_store(self):
        dataset = self.eligible_case()
        self.assertFalse((self.store / td.DATASET_DIR).exists(),
                         "build_dataset wrote something")
        td.write_dataset(dataset, self.store)
        did = dataset["manifest"]["dataset_id"]
        under = sorted(str(path.relative_to(self.store))
                       for path in self.store.rglob("*") if path.is_file())
        self.assertEqual([name for name in under if name.startswith(td.DATASET_DIR)],
                         sorted(f"{td.DATASET_DIR}/{did}/{name}"
                                for name in td.DATASET_FILES.values()))
        self.assertFalse(self.evals.exists(), "the evals store was created by an export")

    def test_the_safe_paths_surface_this_module_reaches_is_exactly_five_names(self):
        """The count-free form of `test_the_lifecycle_writes_through_the_confined_helper...`: what
        matters is that every path operation is one of `safe_paths`' own verbs, not how many call
        sites there are."""
        tree = ast.parse((BIN_DIR / "training_data.py").read_text(encoding="utf-8"))
        reached = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            value = node.value
            if isinstance(value, ast.Name) and value.id == "sp":
                reached.add(node.attr)
            elif isinstance(value, ast.Call) and isinstance(value.func, ast.Name) \
                    and value.func.id == "_sp":
                reached.add(node.attr)
        self.assertEqual(sorted(reached), ["SafePathExists", "confined_append_bytes",
                                          "confined_create_bytes", "confined_read_bytes",
                                          "validate_id"])

    # ---- E. audit metadata is separate from model inputs --------------------------------------

    def test_the_payload_and_audit_schemas_share_exactly_the_join_key(self):
        self.assertEqual(set(td.PAYLOAD_FIELDS) & set(td.AUDIT_FIELDS), {"example_id"})
        self.assertEqual(td.PAYLOAD_FIELDS, ("example_id", "question", "input", "target"))
        self.assertEqual(set(td.PAYLOAD_ENTRY_KEYS), {"text", "observed_at"})
        self.assertLess(set(td.PAYLOAD_ENTRY_KEYS), set(td.ENTRY_KEYS))
        dataset = self.eligible_case()
        self.assertEqual(set(dataset["payload"][0]), set(td.PAYLOAD_FIELDS))
        self.assertEqual(set(dataset["audit_metadata"][0]), set(td.AUDIT_FIELDS))
        entry = dataset["payload"][0]["input"]["observed_error"][0]
        self.assertEqual(set(entry), set(td.PAYLOAD_ENTRY_KEYS))
        for banned in ("outcome", "action", "taken", "reviewer", "evidence", "provenance",
                       "eligibility", "redaction"):
            self.assertEqual([name for name in td.PAYLOAD_FIELDS if banned in name], [],
                             f"{banned!r} is audit metadata and has no place in a model input")
        # THE SEPARATION IS LOSSLESS. Everything a stored entry carries is in one of the two
        # files: the text and its instant in the payload, the rest in the audit's
        # `input_provenance`. `provenance` is the only stored key with no counterpart, because it
        # is flattened there into `source` and `artifact_sha`.
        stored = set(self.record["input"]["observed_error"][0])
        kept = set(td.PAYLOAD_ENTRY_KEYS) | set(
            dataset["audit_metadata"][0]["input_provenance"]["observed_error"][0])
        self.assertEqual(stored - kept, {"provenance"})
        self.assertEqual(kept - stored, {"source", "artifact_sha"})

    def test_a_payload_line_carries_no_provenance_and_the_audit_line_carries_all_of_it(self):
        dataset = self.eligible_case()
        payload = dataset["bytes"]["payload"].decode("utf-8")
        audit = dataset["bytes"]["audit_metadata"].decode("utf-8")
        for marker in (AUDIT_ONLY_SOURCE, AUDIT_ONLY_REVIEWER, AUDIT_ONLY_EVIDENCE,
                       dataset["manifest"]["content"]["examples"][0]["item"],
                       dataset["manifest"]["content"]["examples"][0]["group"],
                       dataset["manifest"]["content"]["examples"][0]["label_head"],
                       self.record["content_sha"], td.TRAINABLE_PARTITION):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, payload)
                self.assertIn(marker, audit)
        self.assertIn(self.record["example_id"], payload)
        self.assertIn(self.record["example_id"], audit)
        self.assertIn("AttributeError", payload)

    def test_no_action_record_reaches_either_file(self):
        """D32's own disclosure: `attach_action` accepts an `ACTION_OUTCOMES` member DIRECTLY, so a
        stored action does not say whether its outcome was derived or declared. This export reads no
        action record at all rather than presenting a declared field as a measured one."""
        self.resolve(self.record)
        action = td.attach_action(self.record, taken="re-ran the verify command after a retry",
                                  outcome=td.action_outcome("retry-pass"), observed_at=LATER)
        td.persist_lifecycle(action, self.store)
        dataset = self.export([self.record])
        both = (dataset["bytes"]["payload"] + dataset["bytes"]["audit_metadata"]).decode("utf-8")
        self.assertNotIn("re-ran the verify command", both)
        self.assertNotIn(action["content_sha"], both)
        self.assertNotIn("retry-pass", both)
        names = set(td.PAYLOAD_FIELDS) | set(td.AUDIT_FIELDS)
        self.assertEqual(names & {"action", "outcome", "actions", "outcomes", "taken"}, set())
        self.assertEqual(dataset["manifest"]["content"]["counts"]["included"], 1)

    def test_the_manifest_carries_the_label_version_and_the_grouping_owner(self):
        dataset = self.eligible_case()
        content = dataset["manifest"]["content"]
        head = td.read_lifecycle(self.store, self.record["example_id"], "adjudication")[0]
        row = content["examples"][0]
        self.assertEqual(row["label_head"], head["content_sha"])
        self.assertEqual(row["label_taxonomy_v"], td.TAXONOMY_VERSION)
        self.assertEqual(row["payload_sha"], td._sha(dataset["payload"][0]))
        self.assertEqual(row["audit_metadata_sha"], td._sha(dataset["audit_metadata"][0]))
        self.assertEqual(content["source_manifest"], we.manifest_ref(self.manifest))
        self.assertEqual(content["source_partition_digest"],
                         we.partition_digest(self.manifest, td.TRAINABLE_PARTITION))
        self.assertNotEqual(content["source_partition_digest"], self.manifest["sha"])
        # It moves when the drawn item set moves, and it is the OWNER's function that says so.
        smaller = _eval_manifest([_task("T-1", issue=1)])
        self.assertNotEqual(we.partition_digest(smaller, td.TRAINABLE_PARTITION),
                            content["source_partition_digest"])
        self.assertEqual(content["rules"]["grouping"], we.GROUPING_RULE)
        self.assertEqual(content["rules"]["assignment"], we.ASSIGNMENT_RULE)
        self.assertEqual(content["rules"]["enforcement"], we.NOT_ENFORCEMENT_LABEL)
        self.assertEqual(content["rules"]["partitions"], json.loads(json.dumps(
            dict(we.PARTITION_ROLES))))
        self.assertEqual(content["content_identities"]["payload_sha"],
                         hashlib.sha256(dataset["bytes"]["payload"]).hexdigest())
        self.assertEqual(content["content_identities"]["audit_metadata_sha"],
                         hashlib.sha256(dataset["bytes"]["audit_metadata"]).hexdigest())
        self.assertEqual(content["schemas"]["shared_fields"], ["example_id"])

    def test_every_not_established_code_rides_on_every_manifest_unconditionally(self):
        empty = self.export([])
        full = self.eligible_case()
        for dataset in (empty, full):
            content = dataset["manifest"]["content"]
            self.assertEqual(content["not_established"], list(td.DATASET_NOT_ESTABLISHED))
            self.assertEqual(set(content["not_established_notes"]),
                             set(td.DATASET_NOT_ESTABLISHED))
            self.assertIs(content["exposure"]["recorded_here"], False)
            self.assertIn(td.AUDIT_SEPARATION_NOTE, content["notes"])
            self.assertIn(td.NOT_WIRED_LABEL, content["notes"])
        self.assertIn("no model was trained",
                      td.DATASET_NOT_ESTABLISHED_NOTES["no-transfer-and-no-training-performed"])
        self.assertIn("forged",
                      td.DATASET_NOT_ESTABLISHED_NOTES[
                          "digest-identifies-content-not-provenance"])

    # ---- F. no network or training action -----------------------------------------------------

    def test_the_seam_trap_is_armed_and_bites(self):
        """CONTROL. Without this, every "nothing was reached" assertion below could be passing
        because the seams were never replaced rather than because nothing reached them."""
        with _ArmedSeams(self) as armed:
            self.assertEqual(len(armed.armed), len(STDLIB_SEAMS) + len(WF_SEAMS))
            with self.assertRaises(AssertionError):
                socket.socket()
            with self.assertRaises(AssertionError):
                subprocess.run(["this-never-runs"])
            with self.assertRaises(AssertionError):
                we.record_exposure(self.evals, self.manifest, partition=td.TRAINABLE_PARTITION)

    def test_a_whole_build_write_and_read_cycle_reaches_no_forbidden_seam(self):
        self.resolve(self.record)
        item = next(iid for iid in self.manifest["content"]["partitions"][td.TRAINABLE_PARTITION]
                    if self.manifest["content"]["items"][iid]["task_id"] == "T-1")
        we.record_exposure(self.evals, self.manifest, partition=td.TRAINABLE_PARTITION,
                           purpose=we.PARTITION_ROLES[td.TRAINABLE_PARTITION]["purpose"],
                           items=[item], by="fixture")
        with _ArmedSeams(self):
            dataset = self.export([self.record])
            td.write_dataset(dataset, self.store)
            td.read_dataset(self.store, dataset["manifest"]["dataset_id"])
            td.dataset_rules()
            td.exclusion_codes()
            td.dataset_integrity(dataset["manifest"])
        self.assertEqual(dataset["manifest"]["content"]["counts"]["included"], 1)
        self.assertEqual(dataset["manifest"]["content"]["exposure"]["entries"], 1)

    def test_the_module_declares_no_trainer_and_no_transfer_verb(self):
        tree = ast.parse((BIN_DIR / "training_data.py").read_text(encoding="utf-8"))
        names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        self.assertIn("build_dataset", names)
        for verb in ("train", "fine_tune", "finetune", "upload", "download", "post", "send",
                     "transfer", "publish", "push"):
            self.assertEqual([name for name in names if verb in name], [],
                             f"a function named for {verb!r} would be a capability this task has "
                             f"no authority to add")
        self.assertIs(td.COLLECTION_ENABLED, False)
        self.assertIs(td.CAPTURE_WIRED, False)
        self.assertEqual(td.collection_state()["reason"], "collection-disabled")
        self.assertEqual(
            td.collection_scope(purpose="export with rights nobody confirmed", retention_days=7,
                                approval_ref=al.make_ref("approval-synthetic")).eligibility,
            "unknown")

    # ---- G. one vocabulary, one owner, one version --------------------------------------------

    def test_no_partition_or_exposure_vocabulary_is_copied_into_this_module(self):
        """Only ONE of `workflow_eval`'s partition names may appear as a literal here, and it is
        the trainable one. The Phase 4 review found three hand-copied vocabularies that agreed
        only by coincidence of that commit."""
        tree = ast.parse((BIN_DIR / "training_data.py").read_text(encoding="utf-8"))
        constants = {node.value for node in ast.walk(tree)
                     if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        self.assertGreater(len(constants), 50)  # the sweep walked something
        self.assertEqual(constants & set(we.PARTITIONS), {td.TRAINABLE_PARTITION})
        self.assertEqual(constants & set(we.BUCKETS), {td.TRAINABLE_PARTITION})
        self.assertEqual(constants & set(we.EXPOSURE_PURPOSES) - {td.TRAINABLE_PARTITION}, set())
        self.assertEqual(constants & set(we.LEAK_KINDS), set())
        self.assertNotIn(we.GROUPING_RULE, constants)
        self.assertNotIn(we.MANIFEST_VERSION, constants)

    def test_the_exclusion_vocabulary_is_the_union_and_a_collision_refuses(self):
        codes = td.exclusion_codes()
        self.assertEqual(set(codes), set(td.EXPORT_REFUSALS) | set(td.DATASET_EXCLUSIONS))
        self.assertEqual(list(codes), sorted(codes))
        self.assertEqual(set(td.EXPORT_REFUSALS) & set(td.DATASET_EXCLUSIONS), set())
        with mock.patch.object(td, "EXPORT_REFUSALS",
                               tuple(td.EXPORT_REFUSALS) + ("item-retired",)):
            with self.assertRaises(dc.ContractError) as raised:
                td.exclusion_codes()
            self.assertEqual(raised.exception.code, "duplicate-entry")

    def test_every_dataset_exclusion_code_is_reached_by_its_own_case(self):
        """A code nothing can emit reads as a guard and is not one. Every member of
        `DATASET_EXCLUSIONS` is reached below, and the union is asserted to be the whole tuple."""
        seen = set()

        def add(dataset):
            seen.update(self.codes(dataset))

        self.resolve(self.record)
        add(self.export([self.record], exposure_dir=None))
        add(self.export([_dsnap(None, "nothing points at a task")]))
        stray = _dsnap("T-NOT-MINED", "a task the manifest never saw")
        self.resolve(stray)
        add(self.export([stray]))
        for name in ("promotion", "audit", "calibration"):
            add(self.export([self.record], eval_manifest=_eval_manifest(allocation={name: 1})))
        leaky = _pool()
        leaky[0] = _task("T-1", issue=1,
                         statement="the adapter drops a record\n" + _diff("src/x.py"))
        add(self.export([self.record], eval_manifest=_eval_manifest(leaky, on_leak="quarantine")))
        twins = _pool() + [_task("T-1", issue=99)]
        add(self.export([self.record], eval_manifest=_eval_manifest(twins)))
        item = next(iid for iid in self.manifest["content"]["partitions"][td.TRAINABLE_PARTITION]
                    if self.manifest["content"]["items"][iid]["task_id"] == "T-1")
        we.record_exposure(self.evals, self.manifest, partition=td.TRAINABLE_PARTITION,
                           purpose="inspection", items=[item], by="fixture")
        we.retire(self.evals, self.manifest, items=[item], reason="contaminated", by="fixture")
        add(self.export([self.record]))
        for mutate in (lambda r: r["input"]["observed_error"][0].update({"observed_at": LATER}),
                       lambda r: r["input"]["observed_error"][0].update(
                           {"observed_at": "whenever"}),
                       lambda r: r["input"]["observed_error"][0].update({"truncated": True})):
            forged = _forge(self.record, mutate)
            self.resolve(forged)
            add(self.export([forged], exposure_dir=self.tmp / "clean-evals"))
        group = next(row for row in self.manifest["content"]["groups"].values()
                     if "T-1" in {self.manifest["content"]["items"][i]["task_id"]
                                  for i in row["items"]})
        quoting = dc.parse_question({
            "id": "q-leaky", "version": "1", "kind": "boolean",
            "question": f"Was the attempt in defect group {group['group']} missing a contract?",
            "rubric": {}, "outcomes": ["false", "true"], "abstention": "permitted",
            "dependencies": [], "sensitivity": "project-internal"})
        leak = _dsnap("T-1", "AttributeError: no attribute 'emit'", question=quoting)
        self.resolve(leak)
        add(self.export([leak], exposure_dir=self.tmp / "clean-evals"))
        ambiguous = _dsnap("T-3", "KeyError: the route is missing")
        td.persist(ambiguous, self.store)
        for index, (left, right) in enumerate((("missing-context", "implementation-error"),
                                               ("missing-context", "configuration-permission"))):
            td.persist_lifecycle(_adjudicate(
                ambiguous, shape="ambiguity", cause=None, reviewer=_reviewer(f"amb-{index}"),
                contributing=[{"cause": left, "evidence": [_ev(ref_id=f"a{index}")]},
                              {"cause": right, "evidence": [_ev(ref_id=f"b{index}")]}]),
                self.store)
        add(self.export([ambiguous], exposure_dir=self.tmp / "clean-evals"))
        self.assertEqual(sorted(set(td.DATASET_EXCLUSIONS) - seen), [],
                         "these codes are declared and nothing emits them")

    def test_the_dataset_version_is_registered_and_is_its_own_object(self):
        rg = _load("release_gate")
        rows = {(module, attr) for _, module, attr in rg.VERSION_SOURCES}
        self.assertIn(("training_data", "DATASET_VERSION"), rows)
        self.assertEqual(len({td.SNAPSHOT_VERSION, td.TAXONOMY_VERSION, td.LIFECYCLE_VERSION,
                              td.DATASET_VERSION}), 4)
        # D33 adds a version; it never bumps one D31 or D32 registered.
        self.assertEqual(td.SNAPSHOT_VERSION, "polytropos.training-snapshot/1")
        self.assertEqual(td.TAXONOMY_VERSION, "polytropos.training-cause-taxonomy/1")
        self.assertEqual(td.LIFECYCLE_VERSION, "polytropos.training-label-lifecycle/1")
        self.assertEqual(we.MANIFEST_VERSION, "polytropos.eval-manifest/1")
        dataset = self.eligible_case()
        self.assertEqual(dataset["manifest"]["v"], td.DATASET_VERSION)
        self.assertEqual(dataset["manifest"]["content"]["exporter"]["version"],
                         td.DATASET_VERSION)
        self.assertEqual(td.status(repo_root=ROOT,
                                   env={"POLYTROPOS_DATA_HOME": str(self.tmp / "h")})
                         ["store_exists"], False)

    def test_an_export_past_its_ceiling_refuses_rather_than_trimming(self):
        first = _dsnap("T-1", "AttributeError: no attribute 'emit'")
        second = _dsnap("T-2", "TypeError: the adapter shape is wrong")
        for record in (first, second):
            self.resolve(record)
        with mock.patch.object(td, "MAX_DATASET_EXAMPLES", 1):
            with self.assertRaises(dc.ContractError) as raised:
                self.export([first, second])
            self.assertEqual(raised.exception.code, "bounds-exceeded")
        self.assertEqual(self.export([first, second])
                         ["manifest"]["content"]["counts"]["included"], 2)

    def test_a_source_manifest_from_another_schema_is_refused(self):
        self.resolve(self.record)
        for bad in (None, {}, {"v": "something.else/1", "content": {}}):
            with self.subTest(manifest=bad):
                with self.assertRaises(dc.ContractError) as raised:
                    self.export([self.record], eval_manifest=bad)
                self.assertEqual(raised.exception.code, "not-a-reference")
        with self.assertRaises(dc.ContractError) as raised:
            self.export([{"v": "something.else/1"}])
        self.assertEqual(raised.exception.code, "not-a-reference")

    def test_provenance_and_the_evaluation_clock_have_no_defaults(self):
        """A clock read inside the exporter would make the same material export to different bytes
        on two runs, which is the whole of `DETERMINISM_NOTE`."""
        source = (BIN_DIR / "training_data.py").read_text(encoding="utf-8")
        self.assertNotIn("datetime.date.today", source)
        self.assertNotIn("datetime.datetime.now", source)
        self.assertNotIn("utcnow", source)
        self.resolve(self.record)
        for missing in ("built_at", "built_by", "now"):
            with self.subTest(missing=missing):
                with self.assertRaises(dc.ContractError):
                    self.export([self.record], **{missing: None})
        with self.assertRaises(TypeError):
            td.build_dataset([self.record], eval_manifest=self.manifest, store_dir=self.store,
                             exposure_dir=self.evals, now=NOW,
                             purpose=self.record["eligibility"]["purpose"],
                             destination="local-development-partition", built_by=BUILT_BY)

    def test_a_parent_dataset_is_a_dataset_id_or_nothing(self):
        dataset = self.eligible_case()
        did = dataset["manifest"]["dataset_id"]
        child = self.export([self.record], parent=did)
        self.assertEqual(child["manifest"]["content"]["parent"], did)
        self.assertNotEqual(child["manifest"]["dataset_id"], did)
        self.assertIsNone(dataset["manifest"]["content"]["parent"])
        for bad in ("not-an-id", "ds-nothex", f"{did}/../escape"):
            with self.subTest(parent=bad):
                with self.assertRaises(dc.ContractError):
                    self.export([self.record], parent=bad)

    def test_a_refusal_the_vocabulary_does_not_name_is_refused_rather_than_returned(self):
        """`exclusion_codes` is the union of D32's codes and D33's, and a code outside it is a
        refusal this export cannot honestly report."""
        self.resolve(self.record)
        thinned = tuple(code for code in td.DATASET_EXCLUSIONS
                        if code != "exposure-not-checked")
        with mock.patch.object(td, "DATASET_EXCLUSIONS", thinned):
            with self.assertRaises(dc.ContractError) as raised:
                self.export([self.record], exposure_dir=None)
            self.assertEqual(raised.exception.code, "unknown-value")
            self.assertIn("exposure-not-checked", str(raised.exception))

    def test_a_rewritten_manifest_under_one_id_refuses_a_re_export(self):
        """The branch `dataset_integrity` cannot reach: the export in hand is sound and the FILE on
        disk is not. That is a rewrite, not a re-run, and nothing is overwritten."""
        dataset = self.eligible_case()
        td.write_dataset(dataset, self.store)
        path = (self.store / td.DATASET_DIR / dataset["manifest"]["dataset_id"]
                / td.DATASET_FILES["manifest"])
        stored = json.loads(path.read_text(encoding="utf-8"))
        stored["content"]["counts"]["included"] = 99
        path.write_text(td.canonical(stored) + "\n", encoding="utf-8")
        with self.assertRaises(dc.ContractError) as raised:
            td.write_dataset(dataset, self.store)
        self.assertEqual(raised.exception.code, "duplicate-entry")
        self.assertIn("rewrite", str(raised.exception))
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))
                         ["content"]["counts"]["included"], 99, "the file was overwritten")
        path.write_text(json.dumps({"v": "something.else/1"}) + "\n", encoding="utf-8")
        with self.assertRaises(dc.ContractError) as raised:
            td.write_dataset(dataset, self.store)
        self.assertEqual(raised.exception.code, "unknown-value")

    def test_an_interrupted_export_leaves_no_manifest_and_the_retry_completes(self):
        """THE MANIFEST IS WRITTEN LAST, and that is what the order buys: after a failure partway
        through, the directory holds data files and no manifest, so a reader refuses rather than
        trusting a manifest whose files were never written."""
        dataset = self.eligible_case()
        did = dataset["manifest"]["dataset_id"]
        root = self.store / td.DATASET_DIR / did
        sp = td._sp()
        real = sp.confined_create_bytes

        def fail_on_manifest(store_root, rel, data, **kwargs):
            if rel.endswith(td.DATASET_FILES["manifest"]):
                raise OSError("the export was interrupted")
            return real(store_root, rel, data, **kwargs)

        with mock.patch.object(sp, "confined_create_bytes", fail_on_manifest):
            with self.assertRaises(OSError):
                td.write_dataset(dataset, self.store)
        self.assertTrue((root / td.DATASET_FILES["payload"]).exists())
        self.assertTrue((root / td.DATASET_FILES["audit_metadata"]).exists())
        self.assertFalse((root / td.DATASET_FILES["manifest"]).exists())
        with self.assertRaises(dc.ContractError) as raised:
            td.read_dataset(self.store, did)
        self.assertEqual(raised.exception.code, "not-a-reference")
        receipt = td.write_dataset(dataset, self.store)
        self.assertEqual((receipt["written"], receipt["reason"]), (True, None))
        self.assertEqual(td.read_dataset(self.store, did)["payload"], dataset["payload"])

    def test_a_data_file_already_holding_different_bytes_under_one_id_refuses(self):
        """The other half of an interrupted export: the name is taken and the bytes are not ours.
        With a content-addressed id that cannot be a re-run, so nothing is overwritten."""
        dataset = self.eligible_case()
        did = dataset["manifest"]["dataset_id"]
        rel = f"{td.DATASET_DIR}/{did}/{td.DATASET_FILES['payload']}"
        td._rt().ensure_private(self.store)
        td._sp().confined_create_bytes(self.store, rel, b"{}\n", what="fixture")
        with self.assertRaises(dc.ContractError) as raised:
            td.write_dataset(dataset, self.store)
        self.assertEqual(raised.exception.code, "duplicate-entry")
        self.assertEqual((self.store / rel).read_bytes(), b"{}\n")

    def test_the_source_manifests_own_ordering_never_reaches_these_bytes(self):
        """A manifest is caller-supplied data. Its group membership arriving in another order is a
        different input to the same material, and it must not move a single byte."""
        first = _dsnap("T-1", "AttributeError: no attribute 'emit'")
        second = _dsnap("T-2", "TypeError: the adapter shape is wrong")
        for record in (first, second):
            self.resolve(record)
        shuffled = json.loads(json.dumps(self.manifest))
        group = next(row for row in shuffled["content"]["groups"].values()
                     if len(row["items"]) > 1)
        group["items"] = list(reversed(group["items"]))
        shuffled["sha"] = we.manifest_digest(shuffled["content"])
        shuffled["id"] = shuffled["sha"][:16]
        self.assertEqual(we.verify_manifest(shuffled), [])
        self.assertNotEqual(group["items"],
                            next(row for row in self.manifest["content"]["groups"].values()
                                 if len(row["items"]) > 1)["items"])
        plain = self.export([first, second])
        reordered = self.export([first, second], eval_manifest=shuffled)
        self.assertEqual(reordered["bytes"]["payload"], plain["bytes"]["payload"])
        self.assertEqual(
            list(reordered["manifest"]["content"]["groups"].values())[0]["items"],
            list(plain["manifest"]["content"]["groups"].values())[0]["items"])
        # The audit bytes DO differ, and must: they name the source manifest by its content digest,
        # and a manifest whose bytes moved is a different manifest. What may not differ is the
        # material -- the payload -- or this exporter's own view of who is in which group.
        self.assertNotEqual(reordered["manifest"]["content"]["source_manifest"],
                            plain["manifest"]["content"]["source_manifest"])

    # ---- the demo, offline ---------------------------------------------------------------------

    def test_the_demo_walks_grouping_to_export_and_writes_nothing_into_the_evals_store(self):
        before = sorted(p.name for p in Path(tempfile.gettempdir()).glob("training-demo-*"))
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = td._cli(["demo", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        steps = {step["step"]: step for step in payload["steps"]}
        self.assertEqual(steps["grouped by defect"]["variants"], 2)
        self.assertEqual(steps["grouped by defect"]["partition"], td.TRAINABLE_PARTITION)
        self.assertIs(steps["dataset built"]["deterministic"], True)
        self.assertIs(steps["dataset built"]["duplicate_collapsed_to_one_line"], True)
        self.assertEqual(steps["dataset built"]["duplicates_collapsed"], 1)
        self.assertEqual(steps["dataset written and inspected"]["payload_keys"],
                         sorted(td.PAYLOAD_FIELDS))
        self.assertEqual(steps["dataset written and inspected"]["second_write"],
                         "already-exported")
        self.assertEqual(steps["promotion material refused"]["included"], 0)
        self.assertIn("partition-held-out", steps["audit material refused"]["refusals"])
        self.assertIn("partition-single-use", steps["audit material refused"]["refusals"])
        self.assertEqual(steps["revoked example leaves the dataset"]["refusals"],
                         {"eligibility-revoked": 1})
        self.assertEqual(payload["exposure_log_files"], 0)
        after = sorted(p.name for p in Path(tempfile.gettempdir()).glob("training-demo-*"))
        self.assertEqual(before, after)


# ==================================================================================================
#  D34 -- COLLECTION READINESS AND THE OPERATOR'S RUNBOOK
# ==================================================================================================

READINESS_DOC_PATH = ROOT / "docs" / "TRAINING-DATA-READINESS.md"

#: A purpose that carries a `workflow_eval.GAIN_TOKENS` spelling, used to prove the sweep is CALLED
#: by `readiness_report` rather than asserted about from outside. Made up; no such scope exists.
CLAIMING_PURPOSE = "collect evidence of a measured improvement in recovery"


def _doc_text():
    return READINESS_DOC_PATH.read_text(encoding="utf-8")


def _doc_prose(text):
    """The document with every inline-code span, fenced block and indented listing removed.

    A repository path quoted out of this checkout carries the token `improvement`, because the
    checkout's own directory is named for the body of work. That is a fact about the sweep's
    matching rule and not a claim in the document, so the two are separated here and BOTH are
    asserted: the prose must be clean, and every token in the whole file must be accounted for by
    a path spelling.
    """
    without_fences = re.sub(r"(?ms)^```.*?^```", " ", text)
    without_indented = re.sub(r"(?m)^ {4}.*$", " ", without_fences)
    return re.sub(r"`[^`]*`", " ", without_indented)


class ReadinessTests(unittest.TestCase):
    """D34: the gates, the operator's runbook, and the report that says what it does not say.

    THE ACCEPTANCE TERM THIS WHOLE CLASS TURNS ON is "synthetic tests are not training
    readiness". Every fixture below is invented, every store is a temporary directory, no
    decision in this repository has ever been captured and no label has ever been adjudicated by
    a real reviewer. So the distinction is carried as CODES on every report -- read from
    `readiness_codes()`, asserted unconditional over three differently-shaped reports -- rather
    than as prose a reader can skip.

    HOW EACH ACCEPTANCE TERM IS MADE STRUCTURAL RATHER THAN ASSERTED:

      * A WORKING COLLECTION/EXPORT SETUP WITH AN EXPLICIT READINESS REPORT -- one integration
        walk runs capture -> review -> export -> inspect -> revoke -> refused re-export in a temp
        store, and a second test proves the chain has no seam that works only because a fixture
        pre-set a field: every value the later stage needs is asserted EQUAL to the earlier
        stage's own output, not to a constant in this file.
      * NO ARBITRARY DATASET-SIZE THRESHOLD -- `sufficiency.minimum_examples` and its basis are
        None; a one-example dataset opens the export gate; three examples leave
        `collection-target-chosen` exactly as unmet as one does, because nothing here measures a
        target; and the ceiling is shown to track its constant rather than a number typed twice.
      * NEGATIVE CASES AND DISABLED MODE PASS -- with collection off the build callable is never
        invoked and the store is never created, with the positive control that switching it on
        DOES invoke it; and a tampered record, an unreviewed one, a disputed one, an
        uncomputable expiry, a missing store, a foreign schema and two records claiming one id
        each get their own case.
      * SYNTHETIC TESTS ARE NOT TRAINING READINESS -- the codes above, plus the document's own
        "what is not ready" section asserted present, plus the proof that the report is swept by
        the product's own gain authority and refuses a purpose that reads as a performance claim.
      * NO MODEL DOWNLOAD, TRAINING, PRIVATE BACKFILL OR UPLOAD -- sixteen stdlib primitives and
        eight `workflow_eval` writers are armed with raisers for a whole readiness run, reusing
        D33's trap and its control; and `record_exposure` is proven to have no call site in the
        module at all, by AST rather than by a substring the runbook's own text would defeat.
    """

    maxDiff = None

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="training-d34-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.store = self.tmp / "training"
        self.evals = self.tmp / "evals"
        self.manifest = _eval_manifest()
        self.record = _dsnap("T-1", "AttributeError: no attribute 'emit'")

    # ---- fixture helpers ----------------------------------------------------------------------

    def resolve(self, record):
        """Persist `record` and give it a RESOLVED adjudication -- the state an export needs."""
        td.persist(record, self.store)
        entry = _adjudicate(record)
        td.persist_lifecycle(entry, self.store)
        return entry

    def export(self, records=None, **over):
        kwargs = {
            "eval_manifest": self.manifest, "store_dir": self.store, "exposure_dir": self.evals,
            "now": NOW, "purpose": self.record["eligibility"]["purpose"],
            "destination": "local-development-partition",
            "built_at": BUILT_AT, "built_by": BUILT_BY,
        }
        kwargs.update(over)
        return td.build_dataset([self.record] if records is None else records, **kwargs)

    def report(self, records=None, **over):
        kwargs = {"store_dir": self.store, "now": NOW, "eval_manifest": self.manifest,
                  "exposure_dir": self.evals, "scope": _scope(), "enabled": True}
        kwargs.update(over)
        return td.readiness_report([self.record] if records is None else records, **kwargs)

    def gates(self, report):
        return {row["gate"]: row["state"] for row in report["gates"]}

    def detail(self, report, gate):
        return next(row["detail"] for row in report["gates"] if row["gate"] == gate)

    def walked(self):
        """The whole chain: capture -> review -> export -> write -> read back. Returns its parts."""
        entry = self.resolve(self.record)
        dataset = self.export()
        td.write_dataset(dataset, self.store)
        read_back = td.read_dataset(self.store, dataset["manifest"]["dataset_id"])
        return entry, dataset, read_back

    # ---- A. the integration walk, end to end, in a temp store ---------------------------------

    def test_the_chain_runs_capture_to_review_to_export_to_revoked_re_export(self):
        """THE POSITIVE CONTROL for everything below, and the one place the phase is exercised as
        a CHAIN rather than per unit.

        Capture through the opt-in hook (not `snapshot` directly, so the seam a host would call
        is the one under test), read the stored line back, adjudicate it, let the gate decide,
        export, write, read back, report -- then revoke and watch every downstream answer change.
        """
        calls = []

        def gather():
            calls.append(1)
            return dict(_kwargs(sources={"attempt_ref": al.make_ref("a1b2c3d4",
                                                                    version=al.LEDGER_VERSION),
                                         "task_ref": al.make_ref("T-1")},
                                input={"observed_error": [_entry("AttributeError: no attribute "
                                                                 "'emit'",
                                                                 source=AUDIT_ONLY_SOURCE)]}))

        receipt = td.capture_hook(gather, store_dir=self.store, scope=_scope(), enabled=True)
        self.assertEqual(calls, [1])
        self.assertEqual(receipt["collected"], True)
        stored = td.read_snapshots(self.store, CAPTURED)
        self.assertEqual(len(stored), 1)
        record = stored[0]
        self.assertEqual(record["example_id"], receipt["receipt"]["example_id"])

        entry = _adjudicate(record)
        td.persist_lifecycle(entry, self.store)
        decision = td.export_eligibility(record, now=NOW,
                                         purpose=record["eligibility"]["purpose"],
                                         destination="local-development-partition",
                                         store_dir=self.store)
        self.assertEqual(decision["refusals"], [])

        dataset = self.export([record])
        self.assertEqual(dataset["manifest"]["content"]["counts"]["included"], 1)
        self.assertEqual(td.write_dataset(dataset, self.store)["written"], True)
        read_back = td.read_dataset(self.store, dataset["manifest"]["dataset_id"])
        self.assertEqual(read_back["manifest"]["sha"], dataset["manifest"]["sha"])

        report = self.report([record], dataset=read_back["manifest"])
        self.assertEqual(self.gates(report)["dataset-exported-and-readable"], "met")
        self.assertEqual(report["records"]["intact"], 1)
        self.assertEqual(report["label_agreement"]["supervised_targets"], 1)

        tombstone = td.revoke(record, revoked_at="2026-09-21T08:00:00Z",
                              reason="the owner withdrew this example",
                              by=al.make_ref("synthetic-owner"),
                              dependents=[{"kind": "trained-checkpoint",
                                           "ref": al.make_ref("checkpoint-1")}])
        td.persist_lifecycle(tombstone, self.store)
        self.assertEqual(tombstone["identified"], ["checkpoint-1"])
        self.assertEqual(tombstone["unreached"], list(td.REVOCATION_UNREACHED))

        refused = td.export_eligibility(record, now="2026-09-22T09:00:00Z",
                                        purpose=record["eligibility"]["purpose"],
                                        destination="local-development-partition",
                                        store_dir=self.store)
        self.assertEqual(refused["refusals"], ["eligibility-revoked"])
        after = self.export([record], now="2026-09-22T09:00:00Z")
        self.assertEqual(after["manifest"]["content"]["counts"]["included"], 0)
        self.assertEqual(after["manifest"]["content"]["excluded_by_code"],
                         {"eligibility-revoked": 1})
        final = self.report([record], now="2026-09-22T09:00:00Z",
                            dataset=after["manifest"])
        self.assertEqual(final["retention"]["revoked"], [record["example_id"]])
        self.assertEqual(self.gates(final)["dataset-exported-and-readable"], "unmet")

    def test_the_chain_carries_each_stages_own_output_and_not_a_fixture_constant(self):
        """A chain with a seam only a fixture holds together passes every per-unit test and fails
        the first time a real value differs. So every hand-off is asserted against the EARLIER
        STAGE'S OWN OUTPUT: the capture receipt's id, the adjudication's digest, the manifest's
        item id, and the source reference the snapshot was built with."""
        entry, dataset, read_back = self.walked()
        content = read_back["manifest"]["content"]
        row = content["examples"][0]

        self.assertEqual(row["example_id"], self.record["example_id"])
        self.assertEqual(row["input_sha"], self.record["input_sha"])
        self.assertEqual(row["content_sha"], self.record["content_sha"])
        self.assertEqual(row["label_head"], entry["content_sha"])
        self.assertEqual(row["cause"], entry["cause"])
        self.assertEqual(row["item"], next(
            iid for iid, item in self.manifest["content"]["items"].items()
            if item["task_id"] == self.record["sources"]["task_ref"]["id"]))
        self.assertEqual(read_back["payload"][0]["target"]["cause"], entry["cause"])

        report = self.report(dataset=read_back["manifest"])
        self.assertEqual(report["dataset"]["dataset_id"], dataset["manifest"]["dataset_id"])
        self.assertEqual(report["exposure"]["drawn_items"], [row["item"]])
        self.assertEqual(report["category_coverage"]["resolved_by_class"][entry["cause"]], 1)

    def test_a_readiness_run_writes_nothing_and_leaves_the_store_byte_identical(self):
        """The report is COMPUTED, never stored. Proven over the bytes, not over an intention."""
        self.walked()

        def tree():
            return {str(p.relative_to(self.tmp)): p.read_bytes()
                    for p in sorted(self.tmp.rglob("*")) if p.is_file()}

        before = tree()
        self.report(dataset=self.export()["manifest"])
        self.assertEqual(tree(), before)

    # ---- B. the exposure gate: D33's obligation, carried ---------------------------------------

    def test_the_export_records_no_exposure_and_the_operators_own_call_is_what_closes_the_gate(
            self):
        """THE SINGLE MOST CONSEQUENTIAL THING THIS TASK HAS TO SAY.

        D33 refused to write another engine's store, so an export leaves NO trace in
        `workflow_eval`'s exposure log. The gate is therefore `unmet` after a clean export, names
        the items with no entry, and flips to `met` only when the OPERATOR calls
        `workflow_eval.record_exposure` themselves -- which is what step 10 of the runbook says
        to do.
        """
        self.walked()
        dataset = self.export()
        report = self.report(dataset=dataset["manifest"])
        item = dataset["manifest"]["content"]["examples"][0]["item"]

        self.assertFalse(self.evals.exists(), "the export must not create the evaluation store")
        self.assertEqual(self.gates(report)["exposure-recorded-in-the-eval-store"], "unmet")
        detail = self.detail(report, "exposure-recorded-in-the-eval-store")
        self.assertEqual(detail["items_with_no_exposure_entry"], [item])
        self.assertEqual(detail["recorded_by_this_module"], False)
        self.assertIn("record_exposure", detail["note"])
        self.assertIn("exposure-not-recorded-in-the-eval-store", report["not_established"])

        we.record_exposure(self.evals, self.manifest, partition=td.TRAINABLE_PARTITION,
                           items=[item], by="synthetic-operator",
                           note="the operator's own step 10")
        closed = self.report(dataset=dataset["manifest"])
        self.assertEqual(self.gates(closed)["exposure-recorded-in-the-eval-store"], "met")
        self.assertEqual(self.detail(closed, "exposure-recorded-in-the-eval-store")
                         ["items_with_no_exposure_entry"], [])
        # Recording it does NOT discharge the unconditional code: this module still wrote nothing
        # there, which is a different statement from "the log is now current".
        self.assertIn("exposure-not-recorded-in-the-eval-store", closed["not_established"])
        self.assertEqual(closed["exposure"]["recorded_by_this_module"], False)

    def test_an_unread_exposure_log_is_unknown_rather_than_a_clean_one(self):
        self.walked()
        dataset = self.export()
        blind = self.report(dataset=dataset["manifest"], exposure_dir=None)
        self.assertEqual(self.gates(blind)["exposure-recorded-in-the-eval-store"], "unknown")
        self.assertEqual(blind["exposure"]["checked"], False)
        self.assertEqual(blind["exposure"]["entries"], None)

    def test_the_runbook_names_the_call_the_operator_must_make_and_nothing_here_makes_it(self):
        """The remedy names the function; the module never calls it. The second half is by AST --
        a substring check would be satisfied by the runbook's own text, which is exactly the
        thing under suspicion."""
        walk = td.runbook()
        step = next(row for row in walk["steps"]
                    if row["gate"] == "exposure-recorded-in-the-eval-store")
        self.assertEqual(step["step"], 10)
        self.assertIn("workflow_eval.record_exposure", step["remedy"])
        self.assertIn("YOURSELF", step["do"])
        export_step = next(row for row in walk["steps"]
                           if row["gate"] == "dataset-exported-and-readable")
        self.assertLess(export_step["step"], step["step"],
                        "the exposure is recorded after the draw it records")

        tree = ast.parse((BIN_DIR / "training_data.py").read_text(encoding="utf-8"))
        called = {node.func.attr for node in ast.walk(tree)
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        self.assertGreater(len(called), 20)                     # the sweep walked something
        self.assertNotIn("record_exposure", called)
        self.assertIn("exposure_state", called)                 # it READS the log
        self.assertIn("record_exposure", _doc_text())

    # ---- C. disabled mode -----------------------------------------------------------------------

    def test_with_collection_off_nothing_is_gathered_and_no_store_is_created(self):
        """Disabled mode, through the readiness surface. The build callable RAISES if it is ever
        invoked, and the control below proves the same fixture does invoke it when the switch is
        on -- without which this could be passing on a hook that never calls anything."""
        never = _Raises()
        off = td.capture_hook(never, store_dir=self.store, scope=_scope(), enabled=None)
        self.assertEqual(never.calls, 0)
        self.assertEqual(off["collected"], False)
        self.assertEqual(off["reason"], "collection-disabled")
        self.assertFalse(self.store.exists())

        report = td.readiness_report([], store_dir=self.store, now=NOW)
        self.assertEqual(self.gates(report)["collection-switched-on"], "unmet")
        self.assertEqual(self.gates(report)["capture-wired-to-a-caller"], "unmet")
        self.assertEqual(self.gates(report)["scope-eligibility-approved"], "unknown")
        self.assertEqual(self.gates(report)["records-captured"], "unmet")
        self.assertEqual(self.gates(report)["records-intact"], "unknown")
        self.assertEqual(report["collection"]["collecting"], False)
        self.assertEqual(report["collection"]["to_enable"], list(td.TO_ENABLE))
        self.assertEqual(set(report["not_ready"]) & {"collection-switched-on",
                                                     "capture-wired-to-a-caller",
                                                     "records-captured"},
                         {"collection-switched-on", "capture-wired-to-a-caller",
                          "records-captured"})
        self.assertFalse(self.store.exists())

        # THE CONTROL. The same fixture, the same store, the switch on: it is invoked.
        counted = []
        td.capture_hook(lambda: counted.append(1) or dict(_kwargs()),
                        store_dir=self.store, scope=_scope(), enabled=True)
        self.assertEqual(counted, [1])

    def test_no_gate_reads_met_for_a_scope_whose_rights_nobody_approved(self):
        for status in td.ELIGIBILITY_STATUSES:
            if status == td.ELIGIBLE_TO_PERSIST:
                continue
            with self.subTest(status=status):
                report = td.readiness_report([], store_dir=self.store, now=NOW,
                                             scope=_scope(eligibility=status), enabled=True)
                self.assertEqual(self.gates(report)["scope-eligibility-approved"], "unmet")
                self.assertEqual(self.detail(report, "scope-eligibility-approved")["declared"],
                                 status)
        approved = td.readiness_report([], store_dir=self.store, now=NOW, scope=_scope(),
                                       enabled=True)
        self.assertEqual(self.gates(approved)["scope-eligibility-approved"], "met")

    # ---- D. the negative cases -------------------------------------------------------------------

    def test_a_record_edited_after_capture_fails_the_intact_gate_and_is_counted_out(self):
        self.resolve(self.record)
        tampered = td._copy(dict(self.record))
        tampered["input"]["observed_error"][0]["text"] = "a different error entirely"
        report = self.report([tampered])
        self.assertEqual(self.gates(report)["records-intact"], "unmet")
        self.assertEqual(report["records"]["not_intact"], [self.record["example_id"]])
        self.assertEqual(report["records"]["intact"], 0)
        self.assertEqual(report["label_agreement"]["supervised_targets"], 0)
        self.assertEqual(self.gates(report)["labels-adjudicated"], "unknown")

    def test_an_unreviewed_or_disputed_label_leaves_the_label_gate_unmet(self):
        td.persist(self.record, self.store)
        unreviewed = self.report()
        self.assertEqual(self.gates(unreviewed)["labels-adjudicated"], "unmet")
        self.assertEqual(unreviewed["label_agreement"]["by_status"], {td.UNADJUDICATED: 1})

        td.persist_lifecycle(_adjudicate(self.record), self.store)
        # A SECOND SUPPORTED cause, not an unsupported one: two live heads that each reached a
        # target and disagree, which is the disagreement the lifecycle refuses to settle.
        td.persist_lifecycle(_adjudicate(self.record, cause="environment-infrastructure",
                                         reviewer=_reviewer("reviewer-b", "human-adjudication"),
                                         decided_at=REVIEWED_LATER,
                                         evidence=[_ev(ref_id="review-2",
                                                       observed_at=REVIEWED_LATER)]), self.store)
        disputed = self.report()
        self.assertEqual(self.gates(disputed)["labels-adjudicated"], "unmet")
        self.assertEqual(disputed["label_agreement"]["by_status"], {"disputed": 1})
        self.assertEqual(disputed["label_agreement"]["disputed"], 1)
        self.assertEqual(disputed["label_agreement"]["corroborated"], 0)
        self.assertEqual(disputed["label_agreement"]["distinct_reviewers"], 2)

    def test_two_readers_reaching_one_target_are_counted_as_corroboration(self):
        """The control for the disagreement case above: the same two-head shape, agreeing."""
        td.persist(self.record, self.store)
        td.persist_lifecycle(_adjudicate(self.record), self.store)
        td.persist_lifecycle(_adjudicate(self.record,
                                         reviewer=_reviewer("reviewer-b", "human-adjudication"),
                                         decided_at=REVIEWED_LATER,
                                         evidence=[_ev(ref_id="review-2",
                                                       observed_at=REVIEWED_LATER)]), self.store)
        report = self.report()
        self.assertEqual(report["label_agreement"]["corroborated"], 1)
        self.assertEqual(report["label_agreement"]["disputed"], 0)
        self.assertEqual(self.gates(report)["labels-adjudicated"], "met")

    def test_an_expiry_nobody_could_compute_leaves_the_retention_gate_unmet(self):
        broken = _reseal(self.record, expires_on=None)
        self.resolve(self.record)
        report = self.report([broken])
        self.assertEqual(self.gates(report)["retention-enforceable"], "unmet")
        self.assertEqual(report["retention"]["expiry_not_computable"], [broken["example_id"]])
        self.assertEqual(report["retention"]["by_state"], {"unknown": 1})

    def test_a_report_without_a_store_refuses_because_an_unmade_check_is_not_a_passed_one(self):
        with self.assertRaises(dc.ContractError) as raised:
            td.readiness_report([self.record], store_dir=None, now=NOW)
        self.assertEqual(raised.exception.code, "missing-field")
        self.assertIn("label-not-checked", str(raised.exception))

    def test_a_foreign_schema_or_two_records_claiming_one_id_refuse_rather_than_counting(self):
        for record, code in ((dict(self.record, v="something.else/1"), "not-a-reference"),
                             ({"v": td.DATASET_VERSION}, "not-a-reference")):
            with self.subTest(code=code):
                with self.assertRaises(dc.ContractError) as raised:
                    self.report([record])
                self.assertEqual(raised.exception.code, code)
        # `_forge` recomputes all three digests, so this twin is INTACT and shares the example
        # id (the capture instant is not input-time evidence and sits outside `input_sha`).
        twin = _forge(self.record, lambda r: r.update(captured_at="2026-09-19T10:00:06Z"))
        self.assertEqual(twin["example_id"], self.record["example_id"])
        self.assertNotEqual(twin["content_sha"], self.record["content_sha"])
        with self.assertRaises(dc.ContractError) as raised:
            self.report([self.record, twin])
        self.assertEqual(raised.exception.code, "duplicate-entry")
        # The control: the SAME record offered twice is one example, not a refusal.
        self.resolve(self.record)
        self.assertEqual(self.report([self.record, self.record])["records"],
                         dict(self.report()["records"], offered=2))

    def test_the_instant_a_retention_verdict_is_taken_at_has_no_default(self):
        self.resolve(self.record)
        with self.assertRaises(TypeError):
            td.readiness_report([self.record], store_dir=self.store)
        for bad in ("not-an-instant", "2026-09-20", None):
            with self.subTest(now=bad):
                with self.assertRaises(dc.ContractError):
                    self.report(now=bad)

    # ---- E. the gain sweep, called rather than asserted about -----------------------------------

    def test_a_report_whose_declared_purpose_reads_as_a_performance_claim_refuses(self):
        """D24's lesson, applied here: caller text reaches this report, so the sweep is CALLED at
        the end of `readiness_report` rather than asserted about from outside. Deleting that call
        makes this test go green in the wrong direction, which is what makes it a guard."""
        claiming = td.collection_scope(
            purpose=CLAIMING_PURPOSE, retention_days=30,
            eligibility=td.ELIGIBLE_TO_PERSIST,
            approval_ref=al.make_ref("approval-synthetic", version="fixture/1"))
        record = td.snapshot(scope=claiming, **_kwargs())
        td.persist(record, self.store)
        td.persist_lifecycle(_adjudicate(record), self.store)
        with self.assertRaises(we.EvalError) as raised:
            self.report([record])
        self.assertIn("gain-claim token", str(raised.exception))
        # THE CONTROL: the ordinary fixture's purpose carries no token and reports normally.
        self.resolve(self.record)
        self.assertEqual(self.report()["records"]["permitted_purposes"],
                         [self.record["eligibility"]["purpose"]])

    def test_the_gain_vocabulary_is_the_products_and_is_not_copied_into_this_module(self):
        """D26's method: the checker delegates the vocabulary and holds none of its own. The
        readiness section carries no token at all, and the TWO occurrences anywhere in the module
        are classified rather than waved through -- both are identifiers D31 already carried, one
        a sibling module's name and one the specification's own path."""
        source = inspect.getsource(td.readiness_report)
        self.assertIn("assert_no_gain_claim", source)
        for name in ("readiness_report", "runbook", "checkpoint_links", "readiness_codes",
                     "readiness_notes", "readiness_gates"):
            with self.subTest(fn=name):
                text = inspect.getsource(getattr(td, name))
                self.assertEqual([t for t in we.GAIN_TOKENS if t in text], [])
        for table in (td.GATE_REMEDIES, td.READINESS_NOT_ESTABLISHED_NOTES):
            for value in table.values():
                self.assertEqual(we._gain_hits(value), [])

        module = (BIN_DIR / "training_data.py").read_text(encoding="utf-8").lower()
        found = [(token, index)
                 for token in we.GAIN_TOKENS
                 for index in range(len(module))
                 if module.startswith(token, index)]
        self.assertEqual({token for token, _ in found}, {"improvement"})
        for token, index in found:
            with self.subTest(index=index):
                self.assertTrue(
                    module.startswith("improvement_loop", index)
                    or module[index - len("decision-"):].startswith("decision-improvement"),
                    f"an unclassified gain token at {index}")

        with mock.patch.object(we, "assert_no_gain_claim",
                               side_effect=we.EvalError("stubbed")):
            self.resolve(self.record)
            with self.assertRaises(we.EvalError):
                self.report()

    # ---- F. no arbitrary dataset-size threshold ---------------------------------------------------

    def test_no_minimum_sample_count_is_asserted_and_more_records_do_not_close_the_gate(self):
        """"No arbitrary dataset-size threshold." A dataset of ONE exports and opens its gate; a
        dataset of THREE leaves `collection-target-chosen` exactly as unmet, because nothing here
        measures a target and a number chosen to close it would be the invented threshold."""
        records = [self.record,
                   _dsnap("T-2", "TypeError: the adapter shape is wrong"),
                   _dsnap("T-3", "KeyError: the adapter lost a field")]
        for record in records:
            self.resolve(record)
        one = self.report([records[0]], dataset=self.export([records[0]])["manifest"])
        many = self.report(records, dataset=self.export(records)["manifest"])

        self.assertEqual(one["dataset"]["counts"]["included"], 1)
        self.assertEqual(many["dataset"]["counts"]["included"], 3)
        for report in (one, many):
            self.assertEqual(self.gates(report)["dataset-exported-and-readable"], "met")
            self.assertEqual(self.gates(report)["collection-target-chosen"], "unmet")
            self.assertEqual(report["sufficiency"]["minimum_examples"], None)
            self.assertEqual(report["sufficiency"]["basis"], None)
            self.assertEqual(report["sufficiency"]["ceiling"], td.MAX_DATASET_EXAMPLES)
        self.assertEqual(self.detail(many, "collection-target-chosen")["minimum_examples"], None)

    def test_the_only_size_bound_is_a_ceiling_that_refuses_rather_than_trimming(self):
        self.resolve(self.record)
        with mock.patch.object(td, "MAX_DATASET_EXAMPLES", 7):
            self.assertEqual(self.report()["sufficiency"]["ceiling"], 7)
        second = _dsnap("T-2", "TypeError: the adapter shape is wrong")
        self.resolve(second)
        with mock.patch.object(td, "MAX_DATASET_EXAMPLES", 1):
            with self.assertRaises(dc.ContractError) as raised:
                self.export([self.record, second])
        self.assertEqual(raised.exception.code, "bounds-exceeded")
        self.assertIn("refused rather than trimmed", str(raised.exception))

    # ---- G. synthetic tests are not training readiness --------------------------------------------

    def test_every_report_carries_the_codes_that_deny_readiness_unconditionally(self):
        """Three differently-shaped reports -- empty, partial, complete -- carry the SAME codes.
        A code a branch could drop is not a disclaimer, it is a hope."""
        self.walked()
        shapes = {
            "empty": td.readiness_report([], store_dir=self.store, now=NOW),
            "no dataset": self.report(),
            "complete": self.report(dataset=self.export()["manifest"]),
        }
        for name, report in shapes.items():
            with self.subTest(shape=name):
                self.assertEqual(report["not_established"], list(td.readiness_codes()))
                self.assertEqual(set(report["not_established_notes"]),
                                 set(td.readiness_codes()))
                self.assertIn("synthetic-fixtures-are-not-readiness", report["not_established"])
                self.assertIn("training-sufficiency-not-established", report["not_established"])
                self.assertIn("readiness-is-a-report-not-an-authorization",
                              report["not_established"])
                self.assertEqual(report["v"], td.READINESS_VERSION)
                self.assertIn(td.SYNTHETIC_NOTE, report["notes"])

    def test_the_readiness_vocabulary_is_the_union_of_two_owners_and_a_collision_refuses(self):
        codes = td.readiness_codes()
        self.assertEqual(set(codes),
                         set(td.DATASET_NOT_ESTABLISHED) | set(td.READINESS_NOT_ESTABLISHED))
        self.assertEqual(list(codes), sorted(codes))
        self.assertEqual(set(td.DATASET_NOT_ESTABLISHED) & set(td.READINESS_NOT_ESTABLISHED),
                         set())
        with mock.patch.object(td, "READINESS_NOT_ESTABLISHED",
                               tuple(td.READINESS_NOT_ESTABLISHED) + ("access-not-enforced",)):
            with self.assertRaises(dc.ContractError) as raised:
                td.readiness_codes()
            self.assertEqual(raised.exception.code, "duplicate-entry")
        with mock.patch.object(td, "READINESS_NOT_ESTABLISHED_NOTES",
                               dict(td.READINESS_NOT_ESTABLISHED_NOTES, extra="x")):
            with self.assertRaises(dc.ContractError) as raised:
                td.readiness_notes()
            self.assertEqual(raised.exception.code, "unknown-value")

    def test_the_checkpoint_link_is_names_only_and_a_revocation_can_only_identify_one(self):
        links = td.checkpoint_links()
        self.assertEqual(set(links["fields"]), set(td.CHECKPOINT_LINK_FIELDS))
        self.assertEqual(sorted(set(links["fields"].values())), [None])
        self.assertEqual(links["exists"], False)
        self.assertEqual(links["revocation_reach"], td.REVOCATION_REACH["trained-checkpoint"])
        self.assertEqual(links["revocation_reach"], "identified-only")
        self.assertEqual(links["unreached"], list(td.REVOCATION_UNREACHED))
        self.assertIn("never unlearns it", links["note"])
        with mock.patch.object(td, "REVOCATION_REACH",
                               {k: v for k, v in td.REVOCATION_REACH.items()
                                if k != "trained-checkpoint"}):
            with self.assertRaises(dc.ContractError) as raised:
                td.checkpoint_links()
            self.assertEqual(raised.exception.code, "unknown-value")

    # ---- H. the runbook and the gates are one authority --------------------------------------------

    def test_the_runbook_covers_every_gate_exactly_and_refuses_a_gap(self):
        walk = td.runbook()
        self.assertEqual(len(walk["steps"]), len(td.READINESS_GATES))
        self.assertEqual(set(step["gate"] for step in walk["steps"]), set(td.READINESS_GATES))
        self.assertEqual([step["step"] for step in walk["steps"]],
                         list(range(1, len(td.READINESS_GATES) + 1)))
        for step in walk["steps"]:
            self.assertEqual(step["remedy"], td.GATE_REMEDIES[step["gate"]])

        for name, steps, code in (
            ("a dropped step", td.RUNBOOK_STEPS[:-1], "unknown-value"),
            ("a gate nobody declared",
             td.RUNBOOK_STEPS[:-1] + ({"step": len(td.RUNBOOK_STEPS), "gate": "invented-gate",
                                       "do": "x", "command": None},), "unknown-value"),
            ("two steps on one gate",
             td.RUNBOOK_STEPS[:-1] + (dict(td.RUNBOOK_STEPS[0], step=len(td.RUNBOOK_STEPS)),),
             "duplicate-entry"),
            ("misnumbered",
             tuple(dict(step, step=step["step"] + 1) for step in td.RUNBOOK_STEPS),
             "value-invalid"),
        ):
            with self.subTest(case=name):
                with mock.patch.object(td, "RUNBOOK_STEPS", steps):
                    with self.assertRaises(dc.ContractError) as raised:
                        td.runbook()
                    self.assertEqual(raised.exception.code, code)

    def test_a_remedy_for_a_gate_nobody_declared_and_a_gate_with_no_remedy_both_refuse(self):
        self.assertEqual(set(td.readiness_gates()), set(td.READINESS_GATES))
        for name, table in (
            ("an extra remedy", dict(td.GATE_REMEDIES, invented="x")),
            ("a missing remedy", {k: v for k, v in td.GATE_REMEDIES.items()
                                  if k != "records-intact"}),
        ):
            with self.subTest(case=name):
                with mock.patch.object(td, "GATE_REMEDIES", table):
                    with self.assertRaises(dc.ContractError) as raised:
                        td.readiness_gates()
                    self.assertEqual(raised.exception.code, "unknown-value")

    def test_every_gate_state_is_reached_and_no_report_invents_a_gate_or_a_state(self):
        """All three states occur across the cases below, and every row of every report names a
        declared gate with a declared state and the remedy its own table holds."""
        self.walked()
        seen = set()
        for report in (td.readiness_report([], store_dir=self.store, now=NOW),
                       self.report(),
                       self.report(dataset=self.export()["manifest"])):
            self.assertEqual([row["gate"] for row in report["gates"]],
                             list(td.READINESS_GATES))
            for row in report["gates"]:
                self.assertIn(row["state"], td.GATE_STATES)
                self.assertEqual(row["remedy"], td.GATE_REMEDIES[row["gate"]])
                seen.add(row["state"])
            self.assertEqual(sum(report["gate_states"].values()), len(td.READINESS_GATES))
            self.assertEqual(report["not_ready"],
                             [row["gate"] for row in report["gates"] if row["state"] != "met"])
        self.assertEqual(seen, set(td.GATE_STATES))

    def test_the_enabling_steps_are_one_list_read_by_both_the_status_card_and_the_report(self):
        card = td.status(repo_root=ROOT, env={"POLYTROPOS_DATA_HOME": str(self.tmp / "h")})
        self.assertEqual(card["to_enable"], list(td.TO_ENABLE))
        self.assertEqual(td.runbook()["to_enable"], list(td.TO_ENABLE))
        self.assertEqual(td.readiness_report([], store_dir=self.store, now=NOW)
                         ["collection"]["to_enable"], list(td.TO_ENABLE))
        self.assertEqual(len(td.TO_ENABLE), 3)

    # ---- I. nothing downloads, trains, uploads or writes another engine's store --------------------

    def test_a_whole_readiness_run_reaches_no_network_process_or_evaluation_store_writer(self):
        self.walked()
        dataset = self.export()
        with _ArmedSeams(self):
            report = td.readiness_report([self.record], store_dir=self.store, now=NOW,
                                         dataset=dataset["manifest"],
                                         eval_manifest=self.manifest, exposure_dir=self.evals,
                                         scope=_scope(), enabled=True)
            walk = td.runbook()
            links = td.checkpoint_links()
        self.assertEqual(report["records"]["intact"], 1)
        self.assertEqual(len(walk["steps"]), len(td.READINESS_GATES))
        self.assertEqual(links["exists"], False)

    def test_the_armed_trap_still_bites_which_is_the_control_for_the_run_above(self):
        with _ArmedSeams(self):
            with self.assertRaises(AssertionError):
                shutil.which("python3")
            with self.assertRaises(AssertionError):
                we.record_exposure(self.evals, self.manifest,
                                   partition=td.TRAINABLE_PARTITION, items=[], by="x")

    def test_this_section_adds_no_trainer_no_transfer_verb_and_no_new_path_seam(self):
        source = (BIN_DIR / "training_data.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        self.assertIn("readiness_report", names)
        self.assertIn("runbook", names)
        for verb in ("train", "fine_tune", "finetune", "upload", "download", "post", "send",
                     "transfer", "publish", "push", "fetch", "checkpoint_write"):
            self.assertEqual([name for name in names if verb in name], [], verb)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertEqual(imported & {"subprocess", "socket", "urllib", "http", "ftplib",
                                     "sqlite3", "requests"}, set())
        self.assertIs(td.COLLECTION_ENABLED, False)
        self.assertIs(td.CAPTURE_WIRED, False)

    # ---- J. the release gate's own mappings --------------------------------------------------------

    def test_the_readiness_version_is_registered_and_none_of_the_four_already_there_moved(self):
        rg = _load("release_gate")
        rows = {(module, attr) for _, module, attr in rg.VERSION_SOURCES}
        self.assertIn(("training_data", "READINESS_VERSION"), rows)
        self.assertEqual(len({td.SNAPSHOT_VERSION, td.TAXONOMY_VERSION, td.LIFECYCLE_VERSION,
                              td.DATASET_VERSION, td.READINESS_VERSION}), 5)
        self.assertEqual(td.SNAPSHOT_VERSION, "polytropos.training-snapshot/1")
        self.assertEqual(td.TAXONOMY_VERSION, "polytropos.training-cause-taxonomy/1")
        self.assertEqual(td.LIFECYCLE_VERSION, "polytropos.training-label-lifecycle/1")
        self.assertEqual(td.DATASET_VERSION, "polytropos.training-dataset/1")
        self.assertEqual(td.READINESS_VERSION, "polytropos.training-readiness/1")

    def test_the_release_gate_maps_this_phase_and_every_mapped_id_names_a_real_test(self):
        rg = _load("release_gate")
        row = next(c for c in rg.CONTRACTS if c["id"] == "privacy-eligibility")
        mapped = [tid for tid in row["tests"]["shared"] if tid.startswith("test_training_data.")]
        self.assertEqual(len(mapped), 5)
        self.assertIn("test_training_data.ReadinessTests", mapped)
        resolved = rg.resolve_test_ids(mapped)
        self.assertEqual(sorted(resolved), sorted(mapped))
        for tid, count in resolved.items():
            with self.subTest(tid=tid):
                self.assertGreater(count, 0, f"{tid} resolves to no test")
        self.assertGreater(resolved["test_training_data.ReadinessTests"], 10)

    def test_the_gate_can_check_the_commands_the_checklist_names_because_the_parser_is_askable(
            self):
        rg = _load("release_gate")
        self.assertEqual(rg.command_findings(ROOT), [])
        cited = dict(rg.checklist_commands())
        self.assertIn("bin/training_data.py", cited)
        verbs = rg._subcommands(td)
        self.assertEqual(verbs, {"status", "taxonomy", "readiness", "demo"})
        for _script, sub in rg.checklist_commands():
            if _script == "bin/training_data.py" and sub:
                with self.subTest(sub=sub):
                    self.assertIn(sub, verbs)
        for step in td.runbook()["steps"]:
            if step["command"]:
                with self.subTest(step=step["step"]):
                    self.assertIn(step["command"], verbs)

    # ---- K. the document -----------------------------------------------------------------------------

    def test_the_document_exists_names_every_gate_and_states_what_is_not_ready(self):
        text = _doc_text()
        self.assertEqual(len(re.findall(r"(?m)^# ", text)), 1)
        self.assertIn("## What is not ready", text)
        for gate in td.READINESS_GATES:
            with self.subTest(gate=gate):
                self.assertIn(gate, text)
        for phrase in ("No real decision has ever been captured",
                       "No real label has been adjudicated",
                       "No dataset has been built from anything but a fixture",
                       "No collection target exists",
                       "No checkpoint exists",
                       "A green suite is not readiness"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        self.assertIn("COLLECTION_ENABLED", text)
        self.assertIn("CAPTURE_WIRED", text)
        self.assertIn("MAX_DATASET_EXAMPLES", text)
        self.assertIn("export_eligibility", text)
        self.assertIn("build_dataset", text)

    def test_the_document_makes_no_performance_claim_and_its_one_token_is_a_repository_path(self):
        """D27's finding, made a test. The checkout's own directory carries a gain-token
        spelling, so ANY path quoted out of this tree trips the sweep. The document is therefore
        split: the PROSE is handed to the product's own authority and must pass, and every token
        in the whole file must sit inside an inline-code span. The control at the end proves the
        prose sweep bites."""
        text = _doc_text()
        prose = _doc_prose(text)
        we.assert_no_gain_claim(prose, where="the readiness runbook's prose")

        spans = [(m.start(), m.end()) for m in re.finditer(r"`[^`]*`", text)]
        lowered = text.lower()
        carriers = set()
        for token in we.GAIN_TOKENS:
            for match in re.finditer(re.escape(token), lowered):
                inside = next((text[a:b] for a, b in spans
                               if a <= match.start() and match.end() <= b), None)
                self.assertIsNotNone(
                    inside, f"{token!r} at {match.start()} is outside every inline-code span")
                self.assertIn("decision-improvement", inside)
                carriers.add(token)
        self.assertEqual(carriers, {"improvement"})

        # THE CONTROL. Without it the split above could be passing because the sweep is inert.
        with self.assertRaises(we.EvalError):
            we.assert_no_gain_claim(prose + "\n\nThis shipped a measured improvement.\n",
                                    where="a doctored copy")

    def test_the_document_and_the_module_do_not_drift_about_the_operators_own_step(self):
        text = _doc_text()
        self.assertIn("workflow_eval.record_exposure", text)
        self.assertIn("exposure-not-recorded-in-the-eval-store", text)
        self.assertIn("identified-only", text)
        for code in td.READINESS_NOT_ESTABLISHED:
            with self.subTest(code=code):
                self.assertIn(code, text)
        self.assertEqual(td.READINESS_DOC, "docs/TRAINING-DATA-READINESS.md")
        self.assertTrue((ROOT / td.READINESS_DOC).is_file())
        self.assertEqual(td.readiness_report([], store_dir=self.store, now=NOW)["doc"],
                         td.READINESS_DOC)

    def test_the_document_has_a_deep_dive_mirror_and_the_generators_are_current(self):
        """Writing into `docs/` is visible to `docs_build`, which globs `docs/*.md`
        NON-recursively -- unlike D27's file under `docs/ASSESSMENTS/`, which was invisible to
        it. So the mirror has to exist and the nav has to carry it."""
        db = _load("docs_build")
        slug = db.deep_dive_slug(READINESS_DOC_PATH.name)
        self.assertEqual(slug, "training-data-readiness")
        mirror = ROOT / "docs-site" / "deep-dives" / f"{slug}.md"
        self.assertTrue(mirror.is_file(), f"{mirror} is missing; run docs_build.py build")
        self.assertIn(f"deep-dives/{slug}.md",
                      (ROOT / "mkdocs.yml").read_text(encoding="utf-8"))
        self.assertIn("# Training-data collection readiness",
                      mirror.read_text(encoding="utf-8"))

    # ---- L. the CLI, offline --------------------------------------------------------------------------

    def test_the_readiness_verb_prints_the_gates_and_reads_no_store(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = td._cli(["readiness", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["v"], td.READINESS_VERSION)
        self.assertEqual(payload["status"]["collection_enabled"], False)
        self.assertEqual(payload["status"]["capture_wired"], False)
        self.assertEqual(payload["sufficiency"]["minimum_examples"], None)
        self.assertEqual(len(payload["runbook"]["steps"]), len(td.READINESS_GATES))
        self.assertEqual(payload["not_established"], list(td.readiness_codes()))
        plain = io.StringIO()
        with contextlib.redirect_stdout(plain):
            self.assertEqual(td._cli(["readiness"]), 0)
        self.assertIn("minimum examples   : None", plain.getvalue())

    def test_the_demo_walks_the_readiness_step_and_shows_the_exposure_gate_still_shut(self):
        before = sorted(p.name for p in Path(tempfile.gettempdir()).glob("training-demo-*"))
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(td._cli(["demo", "--json"]), 0)
        steps = {step["step"]: step for step in json.loads(buffer.getvalue())["steps"]}
        reported = steps["readiness reported"]
        self.assertIn("exposure-recorded-in-the-eval-store", reported["not_ready"])
        self.assertIn("capture-wired-to-a-caller", reported["not_ready"])
        self.assertIn("collection-target-chosen", reported["not_ready"])
        self.assertEqual(reported["minimum_examples"], None)
        self.assertEqual(reported["exposure_recorded_here"], False)
        self.assertEqual(sum(reported["gate_states"].values()), len(td.READINESS_GATES))
        after = sorted(p.name for p in Path(tempfile.gettempdir()).glob("training-demo-*"))
        self.assertEqual(before, after)
