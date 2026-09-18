"""D14 -- the prediction-time join: one row per decision, every fact placed in time against the
instant the decision was taken, and nothing claimed that an on-policy record cannot support.

`PredictionTimeJoinTests` covers `bin/decision_eval.py`:

  * FUTURE EXCLUDED. `placement` is the single primitive that decides whether a fact is a
    feature, outcome evidence, or unplaceable. The tests hand the join a record from before the
    prediction and a record from after it and assert which bucket each lands in; a row with no
    prediction instant has no features at all; and a zoneless or malformed timestamp is
    `unknown-time` rather than assumed local.
  * LABELS VISIBLE. Every question carries the target that defines what it is predicting and a
    label carrying every observation behind it. Two authorities that disagree produce `disputed`
    with BOTH kept, an unmapped observed value stays visible as unmapped, and a question nobody
    declared a target for is `missing` rather than absent from the row.
  * CENSORING VISIBLE. An open attempt, an unknown outcome, a skipped or excluded trial, an
    observation window still open, and a decision that REFUSED and so has no `DecisionRecord`
    at all, are each a row in the join with its reason attached.
  * NO UNTRIED-ACTION CLAIM. Only the action actually taken carries an outcome; a refused
    decision took none, so every alternative on that row is untried.
  * INPUT READ-ONLY, BY CONSTRUCTION. The module imports nothing that can write, has no
    filesystem parameter anywhere in its public surface, and leaves the envelope and the attempt
    records it was handed byte-identical -- including after a caller mutates the row it got
    back. `workflow_eval.build_card` folds an adjudication into the trial record it is given;
    this module deliberately does not, and the test would catch it if it started to.

============================================================================================
 SAFETY CONTRACT
============================================================================================
Nothing here invokes a real `claude`/`codex`/`copilot`/`cursor`/`graphify` binary, reads a real
`~/.claude`/`~/.codex`/`~/.copilot` home, opens a store, starts a process or touches the
network. The module under test performs no I/O at all -- that is one of the properties under
test -- so this file needs no temporary directory either.

ONE LOADER, ON PURPOSE. `bin/` is not a package, so two loaders of `decision_contract.py`
produce two unrelated sets of classes and `parse_record` refuses a request parsed by the other
copy. Every contract object here is therefore built through `decision_eval`'s OWN sibling
loader (`de._contract()`), and the policy, history and evaluation modules are read through its
loaders too.
"""

import ast
import importlib.util
import inspect
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "bin"
MODULE_PATH = BIN_DIR / "decision_eval.py"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


de = _load("decision_eval")
dc = de._contract()          # the SAME contract instance the module under test checks against
dp = de._dp()
ah = de._ah()
we = de._we()
al = _load("attempt_ledger")
kc = _load("kit_contract")
rg = _load("release_gate")

PROJECT = "polytropos"
RUN = "2026-09-16-aaaa"
TASK = "D14"
ALTERNATIVES = ["retry-same-model", "retry-with-contract-context", "stop"]

BEFORE = "2026-09-16T10:00:00.000000Z"
PREDICT = "2026-09-16T11:00:00.000000Z"
AFTER = "2026-09-16T12:00:00.000000Z"
LATER = "2026-09-16T13:00:00.000000Z"

RECOVERY_TEXT = ("Did the attempt that followed this decision reach an accepted verification "
                 "for the same task?")
GRADED_TEXT = ("Did the evaluation's tests oracle pass on the patch this trial produced for "
               "the task under grading?")

Q_RECOVERS = "q-recovers@v1"
Q_GRADED = "q-graded@v1"

_UNSET = object()

PROCESS_WALL = {"basis": "process-wall", "seconds": 12.5, "source": "ledger"}


def question_payload(**over):
    payload = {"id": "q-recovers", "version": "v1", "kind": "boolean",
               "question": RECOVERY_TEXT, "rubric": {}, "outcomes": ["false", "true"],
               "abstention": "permitted", "dependencies": [], "sensitivity": "project-internal"}
    payload.update(over)
    return payload


def graded_question_payload(**over):
    payload = question_payload(id="q-graded", question=GRADED_TEXT)
    payload.update(over)
    return payload


def _specs(payloads):
    return [dc.parse_question(q, f"q[{i}]") for i, q in enumerate(payloads)]


def request_payload(questions=None, **over):
    questions = [question_payload(), graded_question_payload()] if questions is None else questions
    state = {"head": "0123abcd", "verify_rc": 1, "worktree_dirty": False}
    payload = {
        "v": dc.CONTRACT_VERSION,
        "correlation_id": "corr-1",
        "run": RUN,
        "task": TASK,
        "attempt": "1",
        "intended_use": "recovery-selection",
        "task_ref": al.make_ref(TASK, version=kc.CONTRACT_VERSION),
        "acceptance_ref": al.make_ref("acc-1", sha="a" * 64, version=kc.CONTRACT_VERSION),
        "state": state,
        "state_sha": dc.state_digest(state),
        "alternatives": list(ALTERNATIVES),
        "questions": questions,
        "questions_sha": dc.questions_digest(_specs(questions)),
        "eligibility": {"project": PROJECT, "providers": ["rules"], "privacy": "project-local"},
        "deadline_s": 30,
        "resource_policy": {"operation_scope": "consult", "call_ceiling": 1, "repair_ceiling": 0},
        "admission_ref": al.make_ref("grant-ask-1", version=kc.CONTRACT_VERSION),
    }
    payload.update(over)
    return payload


def request(**over):
    return dc.parse_request(request_payload(**over))


def result_for(req, **over):
    answers = {spec.qualified_id: {"outcome": "true", "abstained": False, "raw": None,
                                   "calibrated": None, "vendor_confidence": None}
               for spec in req.questions}
    payload = {
        "v": dc.CONTRACT_VERSION, "correlation_id": req.correlation_id,
        "state_sha": req.state_sha, "questions_sha": req.questions_sha,
        "status": "ok", "answers": answers, "recommended": "retry-with-contract-context",
        "evidence_refs": [], "requested_provider": "rules", "dispatched_provider": "rules",
        "observed_provider": None, "requested_model": None, "dispatched_model": None,
        "observed_model": None, "provider_contract_v": None,
        "duration": {"basis": "decision-latency", "seconds": 0.02, "source": "rules"},
        "usage": None, "note": None,
    }
    payload.update(over)
    return dc.parse_result(payload, req)


def record_for(req, res, **over):
    kwargs = {"decision_id": "dec-1", "mode": "legacy", "baseline": "retry-same-model",
              "selected": "retry-with-contract-context",
              "admission_ref": al.make_ref("grant-act-1", version=kc.CONTRACT_VERSION),
              "reason_codes": ["advice-differs-from-baseline"],
              "rejected": [{"action": "stop", "reason": "not-selected"}],
              "duration_s": 0.02, "duration_source": "coordinator"}
    kwargs.update(over)
    return dc.build_record(req, res, **kwargs)


def hist(**fields):
    """One `attempt_history` record, built through that module's own constructor so the fixture
    cannot drift from the projection this join claims to read."""
    rec = ah.blank()
    base = {"kit": "decision-improvement-v1", "run": RUN, "task": TASK, "source": "ledger"}
    base.update(fields)
    ah.observe(rec, **base)
    return rec


def trial_record(**over):
    payload = {"trial": "t-1", "task_id": "task-a", "variant": "v-1", "harness": "stub",
               "workflow": "direct", "policy": "pinned", "solved": True, "accepted": True,
               "acceptance_by": "kit-check", "incorrect_acceptance": False, "review": None,
               "skipped": None, "excluded": None}
    payload.update(over)
    return payload


def envelope_with(trial=None, adjudications=(), **over):
    payload = {
        "v": we.EVAL_VERSION, "run_id": "2026-09-16-eval", "repo": str(ROOT),
        "harness": "stub", "trials": [trial] if trial is not None else [],
        "adjudications": list(adjudications),
        "holdout": {"tasks": ["task-a"], "reserved_from": "routing tuning",
                    "partition": "promotion",
                    "manifest_ref": {"id": "m-1", "sha": "b" * 64, "v": we.MANIFEST_VERSION}},
    }
    payload.update(over)
    return payload


def recovery_target():
    return de.target(Q_RECOVERS, observable="attempt-outcome",
                     mapping={"pass": "true", "verify-failed": "false",
                              "dispatch-failed": "false"})


def graded_target():
    return de.target(Q_GRADED, observable="trial-outcome",
                     mapping={"solved": "true", "not-solved": "false",
                              "accepted": "true", "not-accepted": "false"})


class PredictionTimeJoinTests(unittest.TestCase):

    maxDiff = None

    # ---- fixtures ------------------------------------------------------------------------------

    def row(self, **over):
        req = over.pop("request", None) or request()
        res = over.pop("result", _UNSET)
        if res is _UNSET:
            res = result_for(req)
        rec = over.pop("record", _UNSET)
        if rec is _UNSET:
            rec = record_for(req, res)
        kwargs = {"prediction_at": PREDICT, "result": res, "record": rec,
                  "targets": [recovery_target(), graded_target()]}
        kwargs.update(over)
        return de.join_row(req, **kwargs)

    def refusal(self, code, callable_, *args, **kwargs):
        with self.assertRaises(dc.ContractError) as caught:
            callable_(*args, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        return caught.exception

    def label_for(self, row, question):
        return next(q["label"] for q in row["questions"] if q["question"] == question)

    # ---- future excluded -------------------------------------------------------------------------

    def test_a_fact_recorded_after_the_prediction_is_never_a_feature(self):
        row = self.row(history=[hist(attempt=1, ts=BEFORE, result="verify-failed",
                                     failure_class="verification"),
                                hist(attempt=2, ts=AFTER, result="pass")])
        features = row["features"]["at_prediction"]
        future = row["features"]["excluded_as_future"]
        self.assertEqual([f["ref"]["attempt"] for f in features], [1])
        self.assertEqual([f["ref"]["attempt"] for f in future], [2])
        self.assertEqual([f["placement"] for f in features], ["at-or-before-prediction"])
        self.assertEqual([f["placement"] for f in future], ["after-prediction"])
        # The outcome of the attempt that came after is evidence, and it is EVIDENCE only: it
        # must not appear among the facts the decision was taken on.
        self.assertNotIn("pass", [f["value"] for f in features])
        self.assertIn("pass", [f["value"] for f in row["outcome_evidence"]])

    def test_a_fact_at_the_prediction_instant_itself_is_knowable(self):
        row = self.row(history=[hist(attempt=1, ts=PREDICT, result="verify-failed")])
        self.assertEqual([f["ref"]["attempt"] for f in row["features"]["at_prediction"]], [1])
        self.assertEqual(row["features"]["excluded_as_future"], [])

    def test_with_no_prediction_instant_nothing_at_all_is_a_feature(self):
        row = self.row(prediction_at=None,
                       history=[hist(attempt=1, ts=BEFORE, result="verify-failed"),
                                hist(attempt=2, ts=AFTER, result="pass")])
        self.assertEqual(row["features"]["at_prediction"], [])
        self.assertEqual(row["features"]["excluded_as_future"], [])
        self.assertEqual([f["ref"]["attempt"] for f in row["features"]["unknown_time"]], [1, 2])
        self.assertIn("prediction-time-unknown", row["unresolved"])

    def test_a_timestamp_with_no_zone_is_unplaceable_rather_than_assumed_local(self):
        for stamp in ("2026-09-16T10:00:00", "not-a-timestamp", "", None):
            with self.subTest(ts=stamp):
                self.assertEqual(de.placement(stamp, PREDICT), "unknown-time")
        row = self.row(history=[hist(attempt=1, ts="2026-09-16T10:00:00", result="pass")])
        self.assertEqual(row["features"]["at_prediction"], [])
        self.assertEqual([f["ref"]["attempt"] for f in row["features"]["unknown_time"]], [1])

    def test_an_offset_timestamp_places_against_utc_rather_than_by_its_characters(self):
        # 09:30-02:00 is 11:30Z, which is AFTER the 11:00Z prediction although it reads earlier.
        self.assertEqual(de.placement("2026-09-16T09:30:00-02:00", PREDICT), "after-prediction")
        self.assertEqual(de.placement("2026-09-16T13:30:00+03:00", PREDICT),
                         "at-or-before-prediction")

    def test_a_prediction_instant_that_names_no_instant_is_refused(self):
        self.refusal("value-invalid", self.row, prediction_at="halfway through Tuesday")

    # ---- labels visible --------------------------------------------------------------------------

    def test_every_question_carries_its_target_and_the_provenance_of_its_label(self):
        row = self.row(history=[hist(attempt=2, ts=AFTER, result="pass")])
        self.assertEqual([q["question"] for q in row["questions"]], [Q_RECOVERS, Q_GRADED])
        recovered = next(q for q in row["questions"] if q["question"] == Q_RECOVERS)
        self.assertEqual(recovered["target"]["observable"], "attempt-outcome")
        self.assertEqual(recovered["target"]["mapping"]["pass"], "true")
        self.assertEqual(recovered["answer"]["outcome"], "true")
        label = recovered["label"]
        self.assertEqual(label["status"], "resolved")
        self.assertEqual(label["value"], "true")
        self.assertEqual(label["sources"], ["attempt-outcome"])
        self.assertEqual([o["observed"] for o in label["observations"]], ["pass"])
        self.assertEqual(label["observations"][0]["ref"]["attempt"], 2)
        self.assertEqual(label["observations"][0]["observed_at"], AFTER)

    def test_two_sources_that_disagree_make_the_label_disputed_and_keep_both(self):
        trial = trial_record(solved=False, accepted=True, acceptance_by="kit-check")
        env = envelope_with(trial, [{"trial": "t-1", "by": "a-person", "verdict": "solved",
                                     "note": "", "at": LATER}])
        row = self.row(envelope=env, trial_id="t-1")
        label = self.label_for(row, Q_GRADED)
        self.assertEqual(label["status"], "disputed")
        self.assertIsNone(label["value"], "a disputed label names no winner")
        self.assertEqual(sorted((d["source"], d["label"]) for d in label["disagreement"]),
                         [("human-adjudication", "true"), ("kit-acceptance", "true"),
                          ("tests-oracle", "false")])
        self.assertEqual([d["human"] for d in label["disagreement"]
                          if d["source"] == "human-adjudication"], [True])
        self.assertIn("sources-disagree", label["reasons"])

    def test_a_human_verdict_of_unsure_is_visible_and_settles_nothing(self):
        trial = trial_record(solved=None, accepted=None, acceptance_by=None)
        env = envelope_with(trial, [{"trial": "t-1", "by": "a-person", "verdict": "unsure",
                                     "note": "", "at": LATER}])
        row = self.row(envelope=env, trial_id="t-1")
        label = self.label_for(row, Q_GRADED)
        self.assertEqual(label["status"], "missing")
        self.assertIn("observations-abstained", label["reasons"])
        self.assertEqual([(o["source"], o["abstained"]) for o in label["observations"]],
                         [("human-adjudication", True)])

    def test_a_question_with_no_declared_target_is_missing_rather_than_absent(self):
        row = self.row(targets=[recovery_target()],
                       history=[hist(attempt=2, ts=AFTER, result="pass")])
        label = self.label_for(row, Q_GRADED)
        self.assertEqual(label["status"], "missing")
        self.assertEqual(label["reasons"], ["no-target-declared"])
        self.assertIsNone(next(q for q in row["questions"]
                               if q["question"] == Q_GRADED)["target"])

    def test_an_observed_value_the_target_does_not_map_stays_visible_as_unmapped(self):
        # `retry-pass` is a real attempt result this target declares no translation for, and it
        # is not one of the results that censor -- so the row is MISSING a label and says which
        # of the two reasons applies, rather than reporting no observation at all.
        row = self.row(history=[hist(attempt=2, ts=AFTER, result="retry-pass")])
        label = self.label_for(row, Q_RECOVERS)
        self.assertEqual([o["observed"] for o in label["observations"]], ["retry-pass"])
        self.assertTrue(label["observations"][0]["unmapped"])
        self.assertIsNone(label["observations"][0]["label"])
        self.assertEqual(label["status"], "missing")
        self.assertEqual(label["reasons"], ["observation-unmapped"])

    def test_an_unmapped_value_that_also_censors_reports_the_censoring(self):
        row = self.row(history=[hist(attempt=2, ts=AFTER, result="budget-stop")])
        label = self.label_for(row, Q_RECOVERS)
        self.assertTrue(label["observations"][0]["unmapped"])
        self.assertEqual(label["status"], "censored")
        self.assertEqual(label["reasons"], ["attempt-budget-stop"])

    def test_a_target_for_a_question_the_request_never_asked_is_refused(self):
        bogus = de.target("q-never-asked@v1", observable="attempt-outcome",
                          mapping={"pass": "true"})
        self.refusal("unknown-question", self.row, targets=[bogus])

    def test_a_target_mapping_onto_an_outcome_the_question_does_not_permit_is_refused(self):
        bad = de.target(Q_RECOVERS, observable="attempt-outcome", mapping={"pass": "maybe"})
        self.refusal("unknown-value", self.row, targets=[bad])

    def test_a_target_with_an_unknown_observable_or_no_mapping_is_refused(self):
        self.refusal("unknown-value", de.target, Q_RECOVERS, observable="vibes",
                     mapping={"pass": "true"})
        self.refusal("missing-field", de.target, Q_RECOVERS, observable="attempt-outcome",
                     mapping={})

    def test_one_question_cannot_carry_two_targets(self):
        self.refusal("duplicate-entry", self.row,
                     targets=[recovery_target(), recovery_target()])

    # ---- censoring visible -----------------------------------------------------------------------

    def test_an_open_attempt_censors_the_label_instead_of_dropping_the_row(self):
        row = self.row(history=[hist(attempt=2, ts=AFTER, result="open")])
        self.assertIn("attempt-open", row["censoring"])
        self.assertEqual(self.label_for(row, Q_RECOVERS)["status"], "censored")
        self.assertIn("attempt-open", self.label_for(row, Q_RECOVERS)["reasons"])

    def test_an_outcome_nobody_observed_is_censored_and_named(self):
        row = self.row(history=[hist(attempt=2, ts=AFTER, result="unknown")])
        self.assertIn("outcome-unknown", row["censoring"])
        self.assertEqual(self.label_for(row, Q_RECOVERS)["status"], "censored")

    def test_a_skipped_or_excluded_trial_is_censored_rather_than_disappearing(self):
        for field, reason in (("skipped", "trial-skipped"), ("excluded", "trial-excluded")):
            with self.subTest(field=field):
                trial = trial_record(solved=None, accepted=None, acceptance_by=None,
                                     **{field: "cost-ceiling"})
                row = self.row(envelope=envelope_with(trial), trial_id="t-1")
                self.assertIn(reason, row["censoring"])
                self.assertEqual(self.label_for(row, Q_GRADED)["status"], "censored")
                self.assertEqual(row["trial"][field], "cost-ceiling")

    def test_an_observation_window_still_open_censors_the_row(self):
        row = self.row(history=[hist(attempt=2, ts=AFTER, result="pass")],
                       window_closes_at=LATER, as_of=AFTER)
        self.assertIn("observation-window-open", row["censoring"])
        closed = self.row(history=[hist(attempt=2, ts=AFTER, result="pass")],
                          window_closes_at=AFTER, as_of=LATER)
        self.assertNotIn("observation-window-open", closed["censoring"])

    def test_a_window_with_no_as_of_is_open_rather_than_assumed_closed(self):
        row = self.row(history=[hist(attempt=2, ts=AFTER, result="pass")],
                       window_closes_at=LATER)
        self.assertIn("observation-window-open", row["censoring"])

    def test_a_refused_decision_has_no_record_and_is_joined_as_unresolved_and_censored(self):
        """The open architect decision recorded against D13: `ActionSelection` sets no action on
        a refusal and `parse_record` requires one, so a refused decision has no `DecisionRecord`
        at this contract revision. The join represents that rather than inventing a record."""
        req = request()
        res = result_for(req)
        row = self.row(request=req, result=res, record=None,
                       refusal={"reasons": ["check-unestablished"],
                                "text": "a fresh coordinator check was never made"},
                       history=[hist(attempt=2, ts=AFTER, result="pass")])
        self.assertIsNone(row["decision"]["record"])
        self.assertEqual(row["decision"]["refusal"]["reasons"], ["check-unestablished"])
        self.assertIn("refusal-has-no-record", row["unresolved"])
        self.assertIn("refusal-has-no-record", row["censoring"])
        self.assertIsNone(row["actions"]["taken"])

    def test_a_refusal_reason_outside_the_policy_vocabulary_is_refused(self):
        self.refusal("unknown-value", self.row, record=None,
                     refusal={"reasons": ["felt-wrong"]})
        self.refusal("missing-field", self.row, record=None, refusal={"reasons": []})
        for reason in dp.REFUSAL_REASONS:
            with self.subTest(reason=reason):
                row = self.row(record=None, refusal={"reasons": [reason]})
                self.assertEqual(row["decision"]["refusal"]["reasons"], [reason])

    def test_a_record_and_a_refusal_cannot_both_be_claimed(self):
        self.refusal("value-invalid", self.row, refusal={"reasons": ["check-failed"]})

    def test_a_decision_with_neither_record_nor_refusal_says_the_record_is_absent(self):
        row = self.row(record=None)
        self.assertIn("decision-record-absent", row["unresolved"])
        self.assertIn("decision-record-absent", row["censoring"])

    # ---- no untried-action claim -------------------------------------------------------------------

    def test_only_the_action_actually_taken_carries_an_outcome(self):
        row = self.row(history=[hist(attempt=2, ts=AFTER, result="pass")])
        by_action = {a["action"]: a for a in row["actions"]["alternatives"]}
        self.assertEqual(sorted(by_action), sorted(ALTERNATIVES))
        taken = by_action["retry-with-contract-context"]
        self.assertTrue(taken["taken"])
        self.assertEqual(taken["outcome"]["result"], "pass")
        self.assertEqual(taken["outcome_basis"], "observed-after-prediction")
        self.assertIsNone(taken["why"])
        for action in ("retry-same-model", "stop"):
            with self.subTest(action=action):
                self.assertFalse(by_action[action]["taken"])
                self.assertIsNone(by_action[action]["outcome"],
                                  "an on-policy log reveals no untried action's outcome")
                self.assertIsNone(by_action[action]["outcome_basis"])
                self.assertEqual(by_action[action]["why"], de.UNTRIED_ACTION_NOTE)

    def test_a_refused_decision_leaves_every_alternative_untried(self):
        row = self.row(record=None, refusal={"reasons": ["baseline-refused"]},
                       history=[hist(attempt=2, ts=AFTER, result="pass")])
        self.assertEqual([a["outcome"] for a in row["actions"]["alternatives"]], [None] * 3)
        self.assertEqual({a["why"] for a in row["actions"]["alternatives"]},
                         {de.UNTRIED_ACTION_NOTE})

    def test_the_coverage_counts_untried_alternatives_rather_than_hiding_them(self):
        row = self.row(history=[hist(attempt=2, ts=AFTER, result="pass")])
        counts = de.join([row])["coverage"]
        self.assertEqual(counts["actions_taken"], 1)
        self.assertEqual(counts["untried_alternatives"], 2)

    # ---- the causal fence ---------------------------------------------------------------------------

    def test_a_recovery_after_a_failure_is_ordering_and_never_causation(self):
        row = self.row(history=[hist(attempt=2, ts=AFTER, result="verify-failed",
                                     failure_class="verification"),
                                hist(attempt=3, ts=LATER, result="pass")])
        recovery = row["recovery"]
        self.assertEqual(recovery["relation"], "followed")
        self.assertIn(recovery["relation"], de.RELATIONS)
        self.assertEqual(recovery["failure"]["ref"]["attempt"], 2)
        self.assertEqual(recovery["recovery"]["ref"]["attempt"], 3)
        self.assertEqual(recovery["intervention"], "retry-with-contract-context")
        self.assertIsNone(recovery["causal_claim"])
        self.assertEqual(recovery["note"], de.NO_CAUSAL_CLAIM)

    def test_the_relation_vocabulary_admits_no_causal_word(self):
        self.assertEqual(de.RELATIONS, ("preceded", "co-occurred", "followed"))
        for relation in de.RELATIONS:
            with self.subTest(relation=relation):
                self.assertFalse(de._is_causal_key(relation))

    def test_a_causal_key_is_refused_wherever_it_is_spelled(self):
        for key in ("caused_by", "because", "Proves", "c.a.u.s.e.d", "root.cause.causedby",
                    "due-to", "explains"):
            with self.subTest(key=key):
                self.refusal("authority-field", de.assert_no_causal_claim,
                             {"recovery": {key: "the context package"}})
        # And it is applied to the rows this module emits, not merely available.
        self.assertIsNotNone(de.assert_no_causal_claim(self.row()))

    def test_a_deterministic_infrastructure_failure_stays_a_fact_about_the_host(self):
        for cls in de.DETERMINISTIC_FAILURE_CLASSES:
            with self.subTest(cls=cls):
                row = self.row(history=[hist(attempt=2, ts=AFTER, result="dispatch-failed",
                                             failure_class=cls)])
                outcome = row["actions"]["outcome"]
                self.assertEqual(outcome["failure_class"], cls)
                self.assertEqual(outcome["failure_class_basis"], "trusted-event")
                self.assertTrue(outcome["deterministic_infrastructure"])
                self.assertEqual(outcome["note"], de.INFRASTRUCTURE_FACT_NOTE)

    def test_a_model_failure_is_not_dressed_up_as_an_infrastructure_fact(self):
        row = self.row(history=[hist(attempt=2, ts=AFTER, result="dispatch-failed",
                                     failure_class="model")])
        self.assertFalse(row["actions"]["outcome"]["deterministic_infrastructure"])
        self.assertIsNone(row["actions"]["outcome"]["note"])

    def test_the_failure_class_comes_from_the_event_and_never_from_the_answer(self):
        """An answer is what a provider believes; a failure class is what the ledger recorded.
        A result whose answers say otherwise cannot move the class the row reports."""
        req = request()
        res = result_for(req, answers={
            Q_RECOVERS: {"outcome": "false", "abstained": False, "raw": None,
                         "calibrated": None, "vendor_confidence": None},
            Q_GRADED: {"outcome": "false", "abstained": False, "raw": None,
                       "calibrated": None, "vendor_confidence": None}})
        row = self.row(request=req, result=res, record=record_for(req, res),
                       history=[hist(attempt=2, ts=AFTER, result="dispatch-failed",
                                     failure_class="auth")])
        self.assertEqual(row["actions"]["outcome"]["failure_class"], "auth")
        self.assertEqual(row["actions"]["outcome"]["failure_class_basis"], "trusted-event")

    # ---- the decision basis --------------------------------------------------------------------------

    def test_the_three_provider_and_model_slots_are_carried_apart(self):
        req = request()
        res = result_for(req, requested_provider="rules", dispatched_provider=None,
                         observed_provider=None, requested_model="a-model",
                         dispatched_model=None, observed_model=None)
        row = self.row(request=req, result=res, record=record_for(req, res))
        self.assertEqual(row["decision"]["provider"],
                         {"requested": "rules", "dispatched": None, "observed": None})
        self.assertEqual(row["decision"]["model"],
                         {"requested": "a-model", "dispatched": None, "observed": None})

    def test_the_record_basis_is_carried_whole(self):
        row = self.row()
        basis = row["decision"]["record"]
        self.assertEqual(basis["mode"], "legacy")
        self.assertEqual(basis["baseline"], "retry-same-model")
        self.assertEqual(basis["selected"], "retry-with-contract-context")
        self.assertEqual(basis["reason_codes"], ["advice-differs-from-baseline"])
        self.assertEqual(basis["rejected"], [{"action": "stop", "reason": "not-selected"}])
        self.assertEqual(basis["result_status"], "ok")
        self.assertEqual(basis["admission_ref"]["id"], "grant-act-1")

    def test_the_provider_free_text_note_is_not_carried_into_the_row(self):
        req = request()
        res = result_for(req, note="a provider wrote this and nothing redacted it")
        row = self.row(request=req, result=res, record=record_for(req, res))
        self.assertIsNone(row["decision"]["note"])
        self.assertEqual(row["decision"]["note_withheld"], de.NOTE_WITHHELD)
        self.assertNotIn("a provider wrote this", json.dumps(row))

    def test_two_clocks_are_never_summed_into_one_number(self):
        row = self.row(history=[hist(attempt=2, ts=AFTER, result="pass",
                                     duration=dict(PROCESS_WALL))])
        grouped = de.duration_by_basis(row)["by_basis"]
        self.assertEqual([entry["seconds"] for entry in grouped["decision-latency"]], [0.02])
        self.assertEqual([entry["seconds"] for entry in grouped["process-wall"]], [12.5])
        self.assertEqual(grouped["model-reported"], [])
        self.assertEqual(sorted(grouped), sorted(ah.DURATION_BASES))
        self.assertNotIn(12.52, [entry["seconds"] for basis in grouped.values()
                                 for entry in basis])

    def test_a_duration_measured_on_an_undeclared_basis_is_refused(self):
        self.refusal("unknown-value", self.row,
                     history=[hist(attempt=2, ts=AFTER, result="pass",
                                   duration={"basis": "stopwatch", "seconds": 1.0,
                                             "source": "x"})])

    # ---- what may be joined ------------------------------------------------------------------------

    def test_a_raw_payload_is_refused_because_the_contract_is_the_validator(self):
        self.refusal("wrong-type", de.join_row, request_payload(), prediction_at=PREDICT)
        req = request()
        self.refusal("wrong-type", de.join_row, req, prediction_at=PREDICT,
                     result=result_for(req).to_payload(), record=None)

    def test_an_object_of_a_different_contract_version_is_refused(self):
        class Impostor:
            def to_payload(self):
                return {"v": "polytropos.decision/99"}

        self.refusal("unknown-value", de.join_row, Impostor(), prediction_at=PREDICT)

    def test_a_result_or_record_about_a_different_correlation_is_refused(self):
        req = request()
        other = request(correlation_id="corr-2")
        self.refusal("correlation-mismatch", de.join_row, req, prediction_at=PREDICT,
                     result=result_for(other), record=None)
        # And the record's own correlation is checked separately from the result's: a record
        # built against another request parses cleanly and is still about a different decision.
        other_result = result_for(other)
        self.refusal("correlation-mismatch", de.join_row, req, prediction_at=PREDICT,
                     result=result_for(req), record=record_for(other, other_result))

    def test_a_record_that_is_not_the_attempt_projection_is_refused(self):
        rogue = dict(hist(attempt=2, ts=AFTER, result="pass"))
        rogue["invented_field"] = "from somewhere else"
        self.refusal("unknown-field", self.row, history=[rogue])

    def test_an_envelope_of_an_unknown_version_or_a_missing_trial_is_refused(self):
        self.refusal("unknown-value", self.row,
                     envelope=envelope_with(trial_record(), v="polytropos.workflow-eval/99"),
                     trial_id="t-1")
        self.refusal("value-invalid", self.row, envelope=envelope_with(trial_record()),
                     trial_id="t-absent")
        self.refusal("missing-field", self.row, envelope=None, trial_id="t-1")

    def test_the_envelope_references_are_carried_without_the_trial(self):
        row = self.row(envelope=envelope_with(trial_record()))
        self.assertEqual(row["evaluation"]["partition"], "promotion")
        self.assertEqual(row["evaluation"]["manifest_ref"]["id"], "m-1")
        self.assertIsNone(row["trial"])

    # ---- input read-only ---------------------------------------------------------------------------

    def test_the_inputs_are_byte_identical_after_a_join(self):
        trial = trial_record(solved=False)
        adjudications = [{"trial": "t-1", "by": "a-person", "verdict": "solved", "note": "",
                          "at": LATER}]
        env = envelope_with(trial, adjudications)
        history = [hist(attempt=1, ts=BEFORE, result="verify-failed"),
                   hist(attempt=2, ts=AFTER, result="pass")]
        before_env = json.dumps(env, sort_keys=True, default=str)
        before_history = json.dumps(history, sort_keys=True, default=str)

        row = self.row(history=history, envelope=env, trial_id="t-1")
        de.join([row])

        self.assertEqual(json.dumps(env, sort_keys=True, default=str), before_env,
                         "the evaluation envelope was modified by reading it")
        self.assertEqual(json.dumps(history, sort_keys=True, default=str), before_history,
                         "an attempt record was modified by reading it")
        # `workflow_eval.build_card` writes the adjudication INTO the trial record it is given.
        # This join must not, or the evidence changes shape by being evaluated.
        self.assertNotIn("adjudication", trial)

    def test_mutating_a_returned_row_cannot_reach_back_into_the_inputs(self):
        env = envelope_with(trial_record())
        history = [hist(attempt=2, ts=AFTER, result="pass",
                        duration=dict(PROCESS_WALL))]
        before_env = json.dumps(env, sort_keys=True, default=str)
        before_history = json.dumps(history, sort_keys=True, default=str)

        row = self.row(history=history, envelope=env, trial_id="t-1")
        row["evaluation"]["manifest_ref"]["id"] = "tampered"
        row["features"]["excluded_as_future"][0]["ref"]["attempt"] = 99
        row["features"]["excluded_as_future"][0]["duration"]["seconds"] = 99.0
        row["trial"]["variant"] = "tampered"
        row["actions"]["outcome"]["ref"]["run"] = "tampered"

        self.assertEqual(json.dumps(env, sort_keys=True, default=str), before_env)
        self.assertEqual(json.dumps(history, sort_keys=True, default=str), before_history)

    def test_one_fact_seen_twice_is_two_objects_rather_than_one(self):
        """The same attempt fact is listed as excluded-from-the-features AND as outcome
        evidence. A reader annotating the evidence must not be editing the feature."""
        row = self.row(history=[hist(attempt=2, ts=AFTER, result="pass")])
        evidence = row["outcome_evidence"][0]
        self.assertEqual(evidence["ref"]["attempt"], 2)
        evidence["value"] = "tampered"
        evidence["ref"]["attempt"] = 99
        self.assertEqual(row["features"]["excluded_as_future"][0]["value"], "pass")
        self.assertEqual(row["features"]["excluded_as_future"][0]["ref"]["attempt"], 2)

    def test_the_module_imports_nothing_that_can_write(self):
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module)
        self.assertEqual(sorted(imported),
                         ["datetime", "importlib.util", "pathlib", "re", "types"],
                         "an import appeared that can write, spawn or reach the network")

    def test_the_module_carries_no_write_call_anywhere(self):
        writes = {"write", "write_text", "write_bytes", "writelines", "mkdir", "touch",
                  "rename", "replace", "unlink", "rmdir", "rmtree", "remove", "truncate",
                  "chmod", "symlink_to", "hardlink_to", "makedirs", "dump", "flush"}
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        found = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id in ("open", "exec", "eval", "compile"):
                found.append(func.id)
            if isinstance(func, ast.Attribute) and func.attr in writes:
                found.append(func.attr)
        self.assertEqual(found, [], "this module reads projections; it has no write path")

    def test_no_public_function_takes_a_filesystem_location(self):
        """Read-only by construction rather than by not-writing: there is nowhere to write TO.
        Every input is a projection some other owner already read."""
        offenders, checked = [], []
        for name, obj in vars(de).items():
            if name.startswith("_") or not inspect.isfunction(obj):
                continue
            checked.append(name)
            for parameter in inspect.signature(obj).parameters:
                if any(word in parameter.lower()
                       for word in ("dir", "path", "file", "store", "root")):
                    offenders.append(f"{name}({parameter})")
        self.assertEqual(offenders, [])
        # Non-vacuous: the sweep has to have looked at the join itself.
        self.assertIn("join_row", checked)
        self.assertGreaterEqual(len(checked), 8, checked)

    def test_the_module_reaches_for_no_function_of_the_owners_it_reads(self):
        """Each sibling is loaded for a VOCABULARY. Pinning which names are reached is what
        keeps a reader from quietly becoming a second writer of somebody else's store."""
        expected = {"_contract": {"ContractError", "CONTRACT_VERSION"},
                    "_dp": {"REFUSAL_REASONS"},
                    "_ah": {"RECORD_FIELDS", "DURATION_BASES"},
                    "_we": {"EVAL_VERSION"}}
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        reached = {loader: set() for loader in expected}
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name)
                    and node.value.func.id in reached):
                reached[node.value.func.id].add(node.attr)
        self.assertEqual(reached, expected)

    # ---- coverage and the document ------------------------------------------------------------------

    def test_coverage_counts_what_it_could_not_resolve_rather_than_filtering_it(self):
        resolved = self.row(history=[hist(attempt=2, ts=AFTER, result="pass")])
        censored = self.row(history=[hist(attempt=3, ts=AFTER, result="open")])
        refused = self.row(record=None, refusal={"reasons": ["check-failed"]},
                           prediction_at=None)
        document = de.join([resolved, censored, refused], notes=["synthetic fixture"])

        self.assertEqual(document["v"], de.JOIN_VERSION)
        self.assertEqual(len(document["rows"]), 3)
        counts = document["coverage"]
        self.assertEqual(counts["rows"], 3)
        self.assertEqual(counts["questions"], 6)
        self.assertEqual(counts["label_status"]["resolved"], 1)
        self.assertEqual(counts["censoring"]["attempt-open"], 1)
        self.assertEqual(counts["censoring"]["refusal-has-no-record"], 1)
        self.assertEqual(counts["unresolved"]["prediction-time-unknown"], 1)
        self.assertEqual(counts["rows_without_prediction_time"], 1)
        self.assertEqual(counts["facts"]["after-prediction"], 2)
        self.assertEqual(sorted(counts["label_status"]), sorted(de.LABEL_STATUSES))
        self.assertIn(de.UNTRIED_ACTION_NOTE, document["disclosures"])
        self.assertIn(de.NO_CAUSAL_CLAIM, document["disclosures"])
        self.assertEqual(document["notes"], ["synthetic fixture"])

    def test_a_document_refuses_a_row_of_another_schema(self):
        row = self.row()
        row["v"] = "polytropos.decision-join/99"
        self.refusal("unknown-value", de.join, [row])
        self.refusal("unknown-value", de.join, [{"not": "a row"}])
        self.refusal("wrong-type", de.join, ["not a row at all"])
        self.refusal("wrong-type", de.join, "rows are a list")

    def test_the_join_version_is_declared_on_the_release_surface(self):
        self.assertIn(("decision prediction join", "decision_eval", "JOIN_VERSION"),
                      rg.VERSION_SOURCES)


if __name__ == "__main__":
    unittest.main()
