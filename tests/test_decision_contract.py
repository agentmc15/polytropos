"""D09 -- the strict contract parser for the decision-improvement-v1 kit.

`DecisionRequestValidationTests` covers `bin/decision_contract.py`: the four objects the shared
plan pins (`QuestionSpec`, `DecisionRequest`, `DecisionResult`, `DecisionRecord`) and the
refusals that are the point of having them. What is under test is not that the fields exist but
that the module refuses what the plan says must be refused:

  * Duplicate JSON keys, unknown fields, missing fields, wrong types and a boolean offered as a
    number. The schema is CLOSED and every key is present -- an unknown value is an explicit
    `null`, so "nobody knew" can never look like "nobody wrote the key".
  * Anything that would make a payload executable or authorising. A provider states what it
    believes; it never says what may be run, permitted, budgeted, accepted, reviewed or
    promoted. `BANNED_FIELDS` is that rule mechanised, and one test proves no field the
    contract itself defines collides with it.
  * Identity. A result must answer THIS request: same correlation id, same state snapshot
    digest, same question-set digest -- and that holds for the four terminal statuses too,
    because a timeout correlated to another call is not this call's timeout.
  * Completeness of a question. An id is a handle, never the question: wording is required, and
    a `choice` or `ordinal` level without a rubric entry that says more than the level's own
    name is refused.
  * Who owns a record. There is no context-free record parser and no path from a provider
    payload to a `DecisionRecord`; `build_record` takes the coordinator's fields keyword-only,
    and the record's admission grant must be a FRESH one, never the grant that paid for asking.
  * Reuse, not reinvention. A provenance reference is built by `attempt_ledger.make_ref` and the
    version it carries is the decision contract's, never the ledger's; a duration is
    `attempt_history`'s reserved `decision-latency` basis through that module's own helper; an
    operation scope is a key of `kit_contract.OPERATION_CAPS`.

Value semantics ABOVE the structural floor -- category coverage, distribution sums and their
tolerance, ordinal rubric matching, raw versus calibrated separation -- are D10's
(`DecisionValueValidationTests`) and are deliberately not asserted here.

============================================================================================
 SAFETY CONTRACT
============================================================================================
Nothing here invokes a real `claude`/`codex`/`copilot`/`cursor`/`graphify` binary, reads a real
`~/.claude`/`~/.codex`/`~/.copilot` home, opens a store, starts a process or touches the
network. Every fixture is a synthetic dict built in this file. The module under test is a pure
library with no I/O at all, which one test asserts structurally.
"""

import ast
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "bin"
MODULE_PATH = BIN_DIR / "decision_contract.py"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dc = _load("decision_contract")
al = _load("attempt_ledger")
ah = _load("attempt_history")
kc = _load("kit_contract")
rg = _load("release_gate")

QUESTION_TEXT = ("Did the failing attempt lack the interface contract of the module it "
                 "called across the boundary?")
ORDINAL_TEXT = ("How much of the failing behaviour does the supplied contract context "
                "actually explain?")


def question(**over):
    payload = {
        "id": "q-context-missing",
        "version": "v1",
        "kind": "boolean",
        "question": QUESTION_TEXT,
        "rubric": {},
        "outcomes": ["false", "true"],
        "abstention": "permitted",
        "dependencies": [],
        "sensitivity": "project-internal",
    }
    payload.update(over)
    return payload


def ordinal_question(**over):
    payload = {
        "id": "q-explains",
        "version": "v1",
        "kind": "ordinal",
        "question": ORDINAL_TEXT,
        "rubric": {
            "none": "no part of the observed failure follows from the supplied context",
            "some": "at least one failing assertion follows from the supplied context",
            "all": "every failing assertion follows from the supplied context",
        },
        "outcomes": ["none", "some", "all"],
        "abstention": "forbidden",
        "dependencies": ["q-context-missing"],
        "sensitivity": "project-internal",
    }
    payload.update(over)
    return payload


STATE = {"head": "0123abcd", "verify_rc": 1, "worktree_dirty": False, "last_failure": "assert"}
ALTERNATIVES = ["retry-same-model", "retry-with-contract-context", "stop"]


def _specs(question_payloads):
    return [dc.parse_question(q, f"q[{i}]") for i, q in enumerate(question_payloads)]


_UNSET = object()


def request_payload(questions=None, state=None, **over):
    """A valid request, with any one field replaced.

    `state_sha` and `questions_sha` are pulled out before the defaults are built, because the
    default for each is the digest of the content -- and a test that supplies a deliberately
    malformed snapshot must not have the fixture refuse it on the way in.
    """
    questions = [question()] if questions is None else questions
    state = dict(STATE) if state is None else state
    state_sha = over.pop("state_sha", _UNSET)
    if state_sha is _UNSET:
        state_sha = dc.state_digest(state)
    questions_sha = over.pop("questions_sha", _UNSET)
    if questions_sha is _UNSET:
        questions_sha = dc.questions_digest(_specs(questions))
    payload = {
        "v": dc.CONTRACT_VERSION,
        "correlation_id": "corr-1",
        "run": "2026-09-16-aaaa",
        "task": "D09",
        "attempt": None,
        "intended_use": "recovery-selection",
        "task_ref": al.make_ref("D09", version=kc.CONTRACT_VERSION),
        "acceptance_ref": al.make_ref("acc-1", sha="a" * 64, version=kc.CONTRACT_VERSION),
        "state": state,
        "state_sha": state_sha,
        "alternatives": list(ALTERNATIVES),
        "questions": questions,
        "questions_sha": questions_sha,
        "eligibility": {"project": "polytropos", "providers": ["rules"],
                        "privacy": "project-local"},
        "deadline_s": 30,
        "resource_policy": {"operation_scope": "consult", "call_ceiling": 1,
                            "repair_ceiling": 0},
        "admission_ref": al.make_ref("grant-ask-1", version=kc.CONTRACT_VERSION),
    }
    payload.update(over)
    return payload


def answer(outcome="true", abstained=False, **over):
    payload = {"outcome": outcome, "abstained": abstained, "raw": None, "calibrated": None,
               "vendor_confidence": None}
    payload.update(over)
    return payload


def result_payload(request, answers=None, **over):
    if answers is None:
        answers = {spec.qualified_id: answer() for spec in request.questions}
    payload = {
        "v": dc.CONTRACT_VERSION,
        "correlation_id": request.correlation_id,
        "state_sha": request.state_sha,
        "questions_sha": request.questions_sha,
        "status": "ok",
        "answers": answers,
        "recommended": "retry-with-contract-context",
        "evidence_refs": [],
        "requested_provider": "rules",
        "dispatched_provider": "rules",
        "observed_provider": None,
        "requested_model": None,
        "dispatched_model": None,
        "observed_model": None,
        "provider_contract_v": None,
        "duration": {"basis": "decision-latency", "seconds": 0.01, "source": "rules"},
        "usage": None,
        "note": None,
    }
    payload.update(over)
    return payload


class DecisionRequestValidationTests(unittest.TestCase):

    # ---- fixtures -------------------------------------------------------------------------

    def request(self, **over):
        return dc.parse_request(request_payload(**over))

    def result(self, request=None, **over):
        request = request or self.request()
        return request, dc.parse_result(result_payload(request, **over), request)

    def record(self, request=None, result=None, **over):
        if request is None:
            request, result = self.result()
        kwargs = {
            "decision_id": "dec-1",
            "mode": "shadow",
            "baseline": "retry-same-model",
            "selected": "retry-with-contract-context",
            "admission_ref": al.make_ref("grant-act-1", version=kc.CONTRACT_VERSION),
            "reason_codes": ["context-package-available"],
            "rejected": [{"action": "stop", "reason": "recovery-budget-remains"}],
            "duration_s": 0.01,
            "duration_source": "rules",
        }
        kwargs.update(over)
        return dc.build_record(request, result, **kwargs)

    def refusal(self, code, callable_, *args, **kwargs):
        with self.assertRaises(dc.ContractError) as caught:
            callable_(*args, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        return caught.exception

    # ---- duplicate keys and the parse boundary ----------------------------------------------

    def test_a_duplicate_json_key_is_refused_rather_than_resolved(self):
        # json keeps the LAST of two identical keys. Whichever one a parser keeps, the party
        # that wrote the bytes may have meant the other -- so neither is chosen.
        self.refusal("duplicate-key", dc.loads,
                     '{"status": "ok", "status": "invalid"}')
        self.refusal("duplicate-key", dc.loads,
                     '{"answers": {"q@v1": {"abstained": false, "abstained": true}}}')
        self.assertEqual(dc.loads('{"status": "ok"}'), {"status": "ok"})

    def test_a_non_finite_literal_never_becomes_a_number(self):
        for token in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(token=token):
                self.refusal("value-invalid", dc.loads, '{"vendor_confidence": %s}' % token)

    def test_a_payload_larger_than_the_bound_is_refused_before_it_is_parsed(self):
        oversized = json.dumps({"note": "x" * (dc.MAX_PAYLOAD_CHARS + 10)})
        self.refusal("bounds-exceeded", dc.loads, oversized)

    def test_text_that_is_not_json_is_a_refusal_and_not_a_traceback(self):
        self.refusal("value-invalid", dc.loads, "{not json")
        self.refusal("wrong-type", dc.loads, {"already": "parsed"})

    # ---- the schema is closed -----------------------------------------------------------------

    def test_an_extra_field_on_any_object_is_refused(self):
        request = self.request()
        cases = {
            "request": (dc.parse_request, (request_payload(priority="high"),)),
            "question": (dc.parse_question, (question(weight=3),)),
            "result": (dc.parse_result, (result_payload(request, seed=7), request)),
        }
        for name, (fn, args) in cases.items():
            with self.subTest(object=name):
                self.refusal("unknown-field", fn, *args)
        answers = {request.questions[0].qualified_id: answer(source="guess")}
        self.refusal("unknown-field", dc.parse_result,
                     result_payload(request, answers=answers), request)

    def test_a_missing_field_is_refused_because_unknown_is_written_as_an_explicit_null(self):
        payload = request_payload()
        del payload["attempt"]
        self.refusal("missing-field", dc.parse_request, payload)

        request = self.request()
        result = result_payload(request)
        del result["observed_model"]
        self.refusal("missing-field", dc.parse_result, result, request)

        spec = question()
        del spec["rubric"]
        self.refusal("missing-field", dc.parse_question, spec)

    def test_a_wrong_type_is_refused_and_a_boolean_is_never_a_number(self):
        self.refusal("wrong-type", dc.parse_request, request_payload(alternatives="stop"))
        self.refusal("wrong-type", dc.parse_request, request_payload(correlation_id=17))
        self.refusal("wrong-type", dc.parse_request,
                     request_payload(resource_policy={"operation_scope": "consult",
                                                      "call_ceiling": True,
                                                      "repair_ceiling": 0}))
        request = self.request()
        answers = {request.questions[0].qualified_id: answer(vendor_confidence=True)}
        self.refusal("wrong-type", dc.parse_result,
                     result_payload(request, answers=answers), request)

    def test_a_state_snapshot_is_flat_scalars_and_never_a_nested_payload(self):
        nested = {"head": "0123abcd", "diagnostics": {"stderr": "..."}}
        self.refusal("wrong-type", dc.parse_request,
                     request_payload(state=nested, state_sha="0" * 64))

    # ---- no authority, no executable field -------------------------------------------------------

    def test_an_authority_or_executable_field_is_refused_wherever_it_appears(self):
        request = self.request()
        self.refusal("authority-field", dc.parse_request,
                     request_payload(permissions=["write"]))
        self.refusal("authority-field", dc.parse_request,
                     request_payload(state={"argv": "rm -rf /"}, state_sha="0" * 64))
        self.refusal("authority-field", dc.parse_result,
                     result_payload(request, approve=True), request)
        answers = {request.questions[0].qualified_id: answer(max_dispatches=99)}
        self.refusal("authority-field", dc.parse_result,
                     result_payload(request, answers=answers), request)

    def test_a_banned_name_is_caught_however_it_is_spelled(self):
        # Punctuation is part of "however it is spelled". A comparison that only swaps dashes
        # for underscores and strips wrapping underscores leaves a trailing period intact, and
        # `_ID_RE` permits periods -- so `approve.` would be accepted as a field name that is
        # not `approve`. It is the same word, and the third surface below is the one that
        # matters most: a distribution's keys are PROVIDER-controlled answer data.
        request = self.request()
        key = request.questions[0].qualified_id
        for spelling in ("allowed-tools", "Allowed_Tools", "__approve__", "SHELL",
                         "approve.", "grant.", "budget.x", "trusted_host.",
                         "max_dispatches.", "a.p.p.r.o.v.e"):
            with self.subTest(spelling=spelling, surface="request"):
                payload = request_payload()
                payload[spelling] = "x"
                self.refusal("authority-field", dc.parse_request, payload)
            with self.subTest(spelling=spelling, surface="state"):
                # The snapshot is refused before its digest is even compared, so the fixture
                # need not (and cannot) compute a digest for a snapshot that will not parse.
                state = dict(STATE)
                state[spelling] = "x"
                self.refusal("authority-field", dc.parse_request,
                             request_payload(state=state, state_sha="0" * 64))
            with self.subTest(spelling=spelling, surface="distribution"):
                answers = {key: answer(raw={spelling: 0.5, "true": 0.5})}
                self.refusal("authority-field", dc.parse_result,
                             result_payload(request, answers=answers), request)

    def test_no_field_this_contract_defines_is_one_it_bans(self):
        # Otherwise the ban would make a legitimate object unparseable, and someone would
        # "fix" it by shrinking the ban. The sweep calls `_is_banned_key` -- the comparison
        # actually in force, not a copy of it -- so widening the ban cannot quietly stop being
        # checked here against the fields this contract itself defines.
        defined = set()
        for name in dir(dc):
            if name.endswith("_KEYS") and isinstance(getattr(dc, name), tuple):
                defined.update(getattr(dc, name))
        defined.update(("basis", "seconds", "source", "usd", "credits"))
        defined.update(al.REF_FIELDS)
        self.assertTrue(defined, "the key tuples are what this test sweeps")
        self.assertTrue(dc.BANNED_FIELDS, "an empty ban has nothing for this sweep to collide")
        collisions = sorted(k for k in defined if dc._is_banned_key(k))
        self.assertEqual(collisions, [])
        # The same comparison must still match a banned entry's OWN plain spelling. It reduces
        # the candidate with `_alnum`; comparing that against unreduced entries would unban
        # `max_dispatches`, `trusted_host` and `allowed_tools` while looking like a tightening.
        self.assertEqual(sorted(n for n in dc.BANNED_FIELDS if not dc._is_banned_key(n)), [])

    # ---- a question id is not a question -----------------------------------------------------

    def test_a_question_id_is_not_a_question(self):
        # Too short to be a question at all.
        self.refusal("incomplete-question", dc.parse_question, question(question="q-ctx"))
        self.refusal("incomplete-question", dc.parse_question,
                     question(question="Was context missing?"))
        # Enough words and enough characters, and still just the id with punctuation sprinkled
        # through it -- an id is a handle for a question and never the asking of one.
        self.refusal("incomplete-question", dc.parse_question,
                     question(question="Q  -  Context  -  Missing  ?"))
        # Enough words, too few characters to have asked anything.
        self.refusal("incomplete-question", dc.parse_question,
                     question(question="did it use a b?"))
        # Long enough to clear the character floor, but still not a sentence. This is the case
        # the word floor exists for: without it, padding the id passes.
        self.refusal("incomplete-question", dc.parse_question,
                     question(question="Wasinterfacecontextmissingfromtheattempt?"))
        self.refusal("incomplete-question", dc.parse_question,
                     question(question="missing interface-contract-context-for-the-callee?"))

    def test_an_ordinal_level_without_a_rubric_entry_is_refused(self):
        rubric = dict(ordinal_question()["rubric"])
        del rubric["some"]
        self.refusal("incomplete-question", dc.parse_question, ordinal_question(rubric=rubric))

    def test_a_rubric_that_only_repeats_the_level_name_is_refused(self):
        rubric = dict(ordinal_question()["rubric"])
        rubric["some"] = "x"
        self.refusal("incomplete-question", dc.parse_question, ordinal_question(rubric=rubric))

        # Long enough to clear the length floor and still nothing but the level's own name
        # with punctuation on it. Without this case the repetition check is dead code that
        # the length floor happens to shadow.
        self.refusal("incomplete-question", dc.parse_question, ordinal_question(
            outcomes=["insufficient", "partial", "complete"],
            rubric={"insufficient": "nothing in the failure follows from the supplied context",
                    "partial": "part of the failure follows from the supplied context",
                    "complete": "-- Complete. --"}))

    def test_a_boolean_question_carries_exactly_the_two_ordered_outcomes(self):
        self.refusal("value-invalid", dc.parse_question,
                     question(outcomes=["true", "false"]))
        self.refusal("value-invalid", dc.parse_question,
                     question(outcomes=["yes", "no"]))
        self.refusal("duplicate-entry", dc.parse_question,
                     question(kind="choice", outcomes=["a", "a"]))

    def test_a_question_cannot_depend_on_one_the_request_does_not_ask(self):
        self.refusal("unknown-question", dc.parse_request,
                     request_payload(questions=[ordinal_question()],
                                     questions_sha=dc.questions_digest(
                                         _specs([ordinal_question()]))))
        both = [question(), ordinal_question()]
        parsed = dc.parse_request(request_payload(
            questions=both, questions_sha=dc.questions_digest(_specs(both))))
        self.assertEqual(len(parsed.questions), 2)

    # ---- the snapshot and the question set are pinned ------------------------------------------

    def test_a_request_whose_declared_digest_does_not_match_its_own_content_is_refused(self):
        self.refusal("state-mismatch", dc.parse_request,
                     request_payload(state_sha="b" * 64))
        self.refusal("state-mismatch", dc.parse_request,
                     request_payload(questions_sha="c" * 64))

    def test_a_reworded_question_changes_the_digest_even_when_the_id_does_not(self):
        original = dc.questions_digest(_specs([question()]))
        reworded = dc.questions_digest(_specs([question(
            question=QUESTION_TEXT.replace("lack", "not have"))]))
        self.assertNotEqual(original, reworded)

    def test_a_result_correlated_to_another_request_is_refused(self):
        request = self.request()
        self.refusal("correlation-mismatch", dc.parse_result,
                     result_payload(request, correlation_id="corr-2"), request)

    def test_a_terminal_status_is_still_checked_against_the_request_it_answers(self):
        # The refusal statuses carry no values, which is exactly why it would be tempting to
        # wave them through. A timeout correlated to another call is not this call's timeout.
        request = self.request()
        # Every assertion in this test is inside the loop, so an emptied vocabulary would make
        # it green without checking a single status.
        self.assertTrue(dc.TERMINAL_STATUSES, "the terminal statuses are what this test checks")
        for status in dc.TERMINAL_STATUSES:
            with self.subTest(status=status, defect="correlation"):
                self.refusal("correlation-mismatch", dc.parse_result,
                             result_payload(request, status=status, answers={},
                                            recommended=None, correlation_id="corr-2"),
                             request)
            with self.subTest(status=status, defect="state"):
                self.refusal("state-mismatch", dc.parse_result,
                             result_payload(request, status=status, answers={},
                                            recommended=None, state_sha="d" * 64),
                             request)
            with self.subTest(status=status, defect="questions"):
                self.refusal("state-mismatch", dc.parse_result,
                             result_payload(request, status=status, answers={},
                                            recommended=None, questions_sha="e" * 64),
                             request)
            with self.subTest(status=status, accepted=True):
                parsed = dc.parse_result(
                    result_payload(request, status=status, answers={}, recommended=None),
                    request)
                self.assertEqual(parsed.status, status)
                self.assertEqual(dict(parsed.answers), {})

    def test_a_terminal_status_carries_no_answers_and_no_recommendation(self):
        request = self.request()
        answers = {request.questions[0].qualified_id: answer()}
        self.refusal("value-invalid", dc.parse_result,
                     result_payload(request, status="timeout", answers=answers,
                                    recommended=None), request)
        self.refusal("value-invalid", dc.parse_result,
                     result_payload(request, status="unavailable", answers={}), request)

    def test_a_result_answering_a_question_this_request_did_not_ask_is_refused(self):
        request = self.request()
        for key in ("q-context-missing@v2", "q-other@v1", "not-a-qualified-id"):
            with self.subTest(key=key):
                self.refusal("unknown-question", dc.parse_result,
                             result_payload(request, answers={key: answer()}), request)

    def test_a_result_whose_state_digest_is_stale_is_refused(self):
        request = self.request()
        moved = dict(STATE, verify_rc=0)
        self.refusal("state-mismatch", dc.parse_result,
                     result_payload(request, state_sha=dc.state_digest(moved)), request)

    # ---- actions -------------------------------------------------------------------------------

    def test_a_recommendation_outside_the_eligible_alternatives_is_refused(self):
        request = self.request()
        self.refusal("unknown-action", dc.parse_result,
                     result_payload(request, recommended="escalate-to-a-bigger-model"),
                     request)

    def test_a_record_cannot_name_an_action_that_was_never_eligible(self):
        request, result = self.result()
        for field in ("baseline", "selected"):
            with self.subTest(field=field):
                self.refusal("unknown-action", self.record, request, result,
                             **{field: "escalate-to-a-bigger-model"})
        self.refusal("unknown-action", self.record, request, result,
                     rejected=[{"action": "ship-it", "reason": "no"}])

    def test_a_record_reports_the_advice_it_got_and_never_improves_on_it(self):
        request, ok_result = self.result()
        record = self.record(request, ok_result)

        # A record cannot claim advice the result did not give,
        self.refusal("value-invalid", dc.parse_record,
                     dict(record.to_payload(), recommended="stop"), request, ok_result)
        # nor restate the result's status as something else.
        self.refusal("value-invalid", dc.parse_record,
                     dict(record.to_payload(), result_status="abstain"), request, ok_result)

        # When the provider abstains the coordinator still selects, and the record says the
        # recommendation was absent rather than borrowing the selection back into it.
        _, abstaining = self.result(request, status="abstain", recommended=None, answers={})
        abstained_record = self.record(request, abstaining,
                                       reason_codes=["provider-abstained", "legacy-default"])
        self.assertIsNone(abstained_record.recommended)
        self.assertEqual(abstained_record.selected, "retry-with-contract-context")
        self.assertEqual(abstained_record.result_status, "abstain")

    def test_a_record_cannot_reject_the_action_it_selected_or_repeat_a_rejection(self):
        request, result = self.result()
        self.refusal("value-invalid", self.record, request, result,
                     rejected=[{"action": "retry-with-contract-context", "reason": "no"}])
        self.refusal("duplicate-entry", self.record, request, result,
                     rejected=[{"action": "stop", "reason": "a"},
                               {"action": "stop", "reason": "b"}])

    # ---- answers, abstention and required answers -------------------------------------------------

    def test_an_ok_result_that_omits_a_question_is_refused(self):
        both = [question(), ordinal_question()]
        request = self.request(questions=both,
                               questions_sha=dc.questions_digest(_specs(both)))
        partial = {request.questions[0].qualified_id: answer()}
        error = self.refusal("missing-answer", dc.parse_result,
                             result_payload(request, answers=partial), request)
        self.assertIn("q-explains@v1", str(error))
        self.refusal("missing-answer", dc.parse_result,
                     result_payload(request, answers={}), request)

    def test_an_ok_result_cannot_abstain_on_an_answer_the_spec_marks_required(self):
        both = [question(), ordinal_question()]
        request = self.request(questions=both,
                               questions_sha=dc.questions_digest(_specs(both)))
        required = request.questions[1].qualified_id
        self.assertEqual(request.questions[1].abstention, "forbidden")
        answers = {request.questions[0].qualified_id: answer(),
                   required: answer(outcome=None, abstained=True)}
        self.refusal("missing-answer", dc.parse_result,
                     result_payload(request, answers=answers), request)

        # `forbidden` binds an `ok` result, not the provider's willingness to answer at all: a
        # whole-result abstention may list the required question among its abstentions.
        whole = dc.parse_result(
            result_payload(request, status="abstain", recommended=None,
                           answers={required: answer(outcome=None, abstained=True)}),
            request)
        self.assertTrue(whole.answers[required]["abstained"])

    def test_abstention_parses(self):
        request = self.request()
        key = request.questions[0].qualified_id

        # A whole-result abstention: no values, no recommendation.
        whole = dc.parse_result(result_payload(request, status="abstain", answers={},
                                               recommended=None), request)
        self.assertEqual(whole.status, "abstain")
        self.assertEqual(dict(whole.answers), {})

        # A per-question abstention on a question whose spec permits one, inside an `ok`
        # result -- a rule provider that reaches semantic uncertainty leaves the value absent
        # rather than guessing it.
        one = dc.parse_result(
            result_payload(request, answers={key: answer(outcome=None, abstained=True)},
                           recommended=None),
            request)
        self.assertTrue(one.answers[key]["abstained"])
        self.assertIsNone(one.answers[key]["outcome"])
        self.assertIsNone(one.answers[key]["raw"])
        self.assertIsNone(one.answers[key]["calibrated"])
        self.assertIsNone(one.answers[key]["vendor_confidence"])

        # And an abstaining result listing its abstentions explicitly.
        listed = dc.parse_result(
            result_payload(request, status="abstain", recommended=None,
                           answers={key: answer(outcome=None, abstained=True)}),
            request)
        self.assertEqual(listed.status, "abstain")

    def test_an_abstaining_result_holds_no_values_and_no_recommendation(self):
        request = self.request()
        key = request.questions[0].qualified_id
        self.refusal("value-invalid", dc.parse_result,
                     result_payload(request, status="abstain", recommended=None,
                                    answers={key: answer()}), request)
        self.refusal("value-invalid", dc.parse_result,
                     result_payload(request, status="abstain",
                                    answers={key: answer(outcome=None, abstained=True)}),
                     request)

    def test_an_answer_is_either_abstained_or_an_outcome_and_the_outcome_is_permitted(self):
        request = self.request()
        key = request.questions[0].qualified_id
        self.refusal("value-invalid", dc.parse_result,
                     result_payload(request, answers={key: answer(abstained=True)}), request)
        self.refusal("missing-answer", dc.parse_result,
                     result_payload(request, answers={key: answer(outcome=None)}), request)
        self.refusal("unknown-value", dc.parse_result,
                     result_payload(request, answers={key: answer(outcome="maybe")}), request)

    # ---- bounded payloads --------------------------------------------------------------------------

    def test_the_bounds_refuse_a_payload_that_has_become_a_channel(self):
        many_alternatives = [f"a-{n}" for n in range(dc.MAX_ALTERNATIVES + 1)]
        self.refusal("bounds-exceeded", dc.parse_request,
                     request_payload(alternatives=many_alternatives))
        self.refusal("bounds-exceeded", dc.parse_request,
                     request_payload(questions=[question()] * (dc.MAX_QUESTIONS + 1)))
        big_state = {f"k{n}": n for n in range(dc.MAX_STATE_ENTRIES + 1)}
        self.refusal("bounds-exceeded", dc.parse_request,
                     request_payload(state=big_state, state_sha="0" * 64))
        long_value = {"head": "x" * (dc.MAX_STATE_VALUE_CHARS + 1)}
        self.refusal("bounds-exceeded", dc.parse_request,
                     request_payload(state=long_value, state_sha="0" * 64))
        self.refusal("bounds-exceeded", dc.parse_question,
                     question(question=QUESTION_TEXT + "x" * dc.MAX_TEXT_CHARS))
        self.refusal("bounds-exceeded", dc.parse_request, request_payload(alternatives=[]))

    # ---- a record is the coordinator's -----------------------------------------------------------

    def test_there_is_no_path_from_a_provider_payload_to_a_record(self):
        request, result = self.result()
        payload = self.record(request, result).to_payload()
        # No context-free parser exists, and the one that does refuses to run without both.
        self.assertFalse([name for name in dir(dc)
                          if name in ("load_record", "read_record", "record_from_payload")])
        self.refusal("wrong-type", dc.parse_record, payload, payload, result)
        self.refusal("wrong-type", dc.parse_record, payload, request, result_payload(request))

    def test_a_result_cannot_carry_the_fields_only_a_coordinator_may_write(self):
        request = self.request()
        for field, value in (("selected", "stop"), ("mode", "active"),
                             ("bundle_sha", "f" * 64), ("baseline", "stop"),
                             ("reason_codes", ["because"])):
            with self.subTest(field=field):
                self.refusal("unknown-field", dc.parse_result,
                             result_payload(request, **{field: value}), request)

    def test_the_record_needs_a_fresh_admission_and_not_the_one_that_paid_for_asking(self):
        request, result = self.result()
        error = self.refusal("stale-admission", self.record, request, result,
                             admission_ref=dict(request.admission_ref))
        self.assertIn("grant-ask-1", str(error))
        fresh = self.record(request, result)
        self.assertEqual(fresh.admission_ref["id"], "grant-act-1")

    def test_build_record_takes_the_coordinators_fields_keyword_only(self):
        request, result = self.result()
        with self.assertRaises(TypeError):
            dc.build_record(request, result, "dec-1", "shadow")

    def test_a_record_requires_at_least_one_reason_code(self):
        request, result = self.result()
        self.refusal("bounds-exceeded", self.record, request, result, reason_codes=[])

    # ---- reuse, not reinvention ---------------------------------------------------------------------

    def test_a_reference_is_the_ledgers_reference_and_is_built_by_its_own_maker(self):
        self.refusal("not-a-reference", dc.parse_request, request_payload(task_ref="D09"))
        self.refusal("not-a-reference", dc.parse_request, request_payload(task_ref=None))
        self.refusal("not-a-reference", dc.parse_request,
                     request_payload(task_ref={"sha": "a" * 64}))
        self.refusal("unknown-field", dc.parse_request,
                     request_payload(task_ref={"id": "D09", "sha": None, "v": None,
                                               "payload": "the whole task"}))
        self.refusal("not-a-reference", dc.parse_request,
                     request_payload(task_ref={"id": "D09", "sha": "a" * 64,
                                               "v": "x" * (al.REF_PART_CHARS + 1)}))
        parsed = self.request()
        self.assertEqual(sorted(parsed.task_ref), sorted(al.REF_FIELDS))

    def test_the_decision_reference_carries_this_contracts_version_not_the_ledgers(self):
        record = self.record()
        ref = dc.decision_ref(record)
        self.assertEqual(ref["v"], dc.CONTRACT_VERSION)
        self.assertNotEqual(ref["v"], al.LEDGER_VERSION)
        self.assertEqual(ref["sha"], record.sha())
        # And the ledger accepts it as one of the four provenance references it already
        # reserves, without the ledger changing.
        self.assertIn("decision_ref", al.PROVENANCE_REFS)
        self.assertEqual(al.validated_refs(decision_ref=ref), {"decision_ref": ref})

    def test_the_ledger_envelope_version_did_not_move_for_this_contract(self):
        self.assertEqual(al.LEDGER_VERSION, "polytropos.attempts/1")
        self.assertNotEqual(dc.CONTRACT_VERSION, al.LEDGER_VERSION)

    def test_the_contract_version_is_declared_on_the_release_surface(self):
        self.assertIn(("decision contract", "decision_contract", "CONTRACT_VERSION"),
                      rg.VERSION_SOURCES)
        row = next(r for r in rg.contract_versions() if r["contract"] == "decision contract")
        self.assertEqual(row["version"], dc.CONTRACT_VERSION)
        self.assertEqual(row["owner"], "bin/decision_contract.py")

    def test_the_only_duration_is_the_basis_the_projection_already_reserved(self):
        request, result = self.result()
        self.assertEqual(dc.DECISION_DURATION_BASIS, "decision-latency")
        self.assertIn(dc.DECISION_DURATION_BASIS, ah.DURATION_BASES)
        self.assertEqual(result.duration,
                         ah._duration("decision-latency", 0.01, "rules"))
        self.assertEqual(sorted(result.duration), ["basis", "seconds", "source"])
        for basis in ("process-wall", "model-reported", "made-up"):
            with self.subTest(basis=basis):
                code = "unknown-value"
                self.refusal(code, dc.parse_result,
                             result_payload(request, duration={"basis": basis, "seconds": 1.0,
                                                               "source": "x"}),
                             request)
        self.assertIsNone(dc.parse_result(result_payload(request, duration=None),
                                          request).duration)

    def test_usage_rides_on_a_basis_the_projection_already_names(self):
        request = self.request()
        parsed = dc.parse_result(
            result_payload(request, usage={"basis": "estimated", "usd": 0.002,
                                           "credits": None, "source": "rules"}), request)
        self.assertEqual(parsed.usage, ah._cost("estimated", 0.002, None, "rules"))
        self.refusal("unknown-value", dc.parse_result,
                     result_payload(request, usage={"basis": "dollars", "usd": 1,
                                                    "credits": None, "source": "x"}),
                     request)

    def test_a_resource_scope_is_one_the_task_contract_already_defines(self):
        # Every positive case below is inside the loop; an empty vocabulary would leave only
        # the refusal, which an empty vocabulary also satisfies.
        self.assertTrue(kc.OPERATION_CAPS, "the scopes are what this test accepts")
        for scope in kc.OPERATION_CAPS:
            with self.subTest(scope=scope):
                parsed = self.request(resource_policy={"operation_scope": scope,
                                                       "call_ceiling": 1,
                                                       "repair_ceiling": 0})
                self.assertEqual(parsed.resource_policy["operation_scope"], scope)
        self.refusal("unknown-value", dc.parse_request,
                     request_payload(resource_policy={"operation_scope": "decision",
                                                      "call_ceiling": 1,
                                                      "repair_ceiling": 0}))

    # ---- vocabularies -------------------------------------------------------------------------------

    def test_the_status_and_mode_vocabularies_are_exactly_what_the_plan_pins(self):
        self.assertEqual(dc.RESULT_STATUSES,
                         ("ok", "abstain", "unsupported", "unavailable", "invalid", "timeout"))
        self.assertEqual(dc.DECISION_MODES, ("legacy", "shadow", "canary", "active"))
        self.assertEqual(set(dc.ANSWERING_STATUSES) | set(dc.TERMINAL_STATUSES),
                         set(dc.RESULT_STATUSES))
        self.assertEqual(set(dc.ANSWERING_STATUSES) & set(dc.TERMINAL_STATUSES), set())
        request = self.request()
        self.refusal("unknown-value", dc.parse_result,
                     result_payload(request, status="success"), request)
        self.refusal("unknown-value", dc.parse_request,
                     request_payload(intended_use="apply-the-patch"))
        self.refusal("unknown-value", dc.parse_request,
                     request_payload(eligibility={"project": "polytropos",
                                                  "providers": ["rules"],
                                                  "privacy": "unknown"}))

    def test_a_payload_of_another_contract_version_is_not_guessed_at(self):
        self.refusal("unknown-value", dc.parse_request,
                     request_payload(v="polytropos.decision/2"))
        request = self.request()
        self.refusal("unknown-value", dc.parse_result,
                     result_payload(request, v=al.LEDGER_VERSION), request)

    # ---- round trip ------------------------------------------------------------------------------------

    def test_every_object_round_trips_through_its_own_canonical_form(self):
        both = [question(), ordinal_question()]
        request = self.request(questions=both,
                               questions_sha=dc.questions_digest(_specs(both)))
        answers = {request.questions[0].qualified_id: answer(),
                   request.questions[1].qualified_id: answer(outcome="some")}
        result = dc.parse_result(result_payload(request, answers=answers), request)
        record = self.record(request, result)

        self.assertEqual(dc.parse_request(dc.loads(dc.dumps(request.to_payload()))), request)
        self.assertEqual(
            dc.parse_result(dc.loads(dc.dumps(result.to_payload())), request), result)
        self.assertEqual(
            dc.parse_record(dc.loads(dc.dumps(record.to_payload())), request, result), record)
        self.assertEqual(request.sha(),
                         dc.parse_request(request.to_payload()).sha())

    # ---- what the module itself may be ---------------------------------------------------------------

    def test_the_module_is_stdlib_only_and_starts_nothing(self):
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])
        # Both assertions below are subset/absence checks, and both hold trivially of the empty
        # set. Without this guard a module that imported nothing STATICALLY -- every import
        # rewritten as `importlib.import_module("os")`, which the AST walk cannot see -- would
        # pass this test while doing exactly what it forbids.
        self.assertTrue(imported, "the AST walk found no imports at all, so the two checks "
                                  "below would pass on an empty set; a module that reaches its "
                                  "imports dynamically is not proven stdlib-only by this test")
        self.assertTrue(imported <= set(sys.stdlib_module_names), sorted(imported))
        for forbidden in ("subprocess", "socket", "urllib", "http", "ssl", "shutil", "os"):
            with self.subTest(module=forbidden):
                self.assertNotIn(forbidden, imported)
        text = MODULE_PATH.read_text(encoding="utf-8")
        for spawn in ("subprocess.", "Path.home(", "os.environ"):
            with self.subTest(pattern=spawn):
                self.assertNotIn(spawn, text)

    def test_every_refusal_this_module_raises_uses_a_declared_reason_code(self):
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        raised = set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "ContractError"):
                self.assertTrue(node.args, "a refusal always names its reason code first")
                first = node.args[0]
                self.assertIsInstance(first, ast.Constant, ast.dump(first))
                raised.add(first.value)
        self.assertTrue(raised)
        self.assertEqual(sorted(raised - set(dc.REASON_CODES)), [])
        self.assertEqual(list(dc.REASON_CODES), sorted(set(dc.REASON_CODES)),
                         "the reason codes are sorted and unique so a reader can scan them")

    def test_an_undeclared_reason_code_cannot_be_raised_at_all(self):
        with self.assertRaises(ValueError):
            dc.ContractError("looks-wrong", "a message")


if __name__ == "__main__":
    unittest.main()
