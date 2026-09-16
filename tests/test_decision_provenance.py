"""D04 -- attempt provenance for the decision-improvement-v1 kit.

`AttemptProvenanceTests` covers the four references an attempt may now carry
(`attempt_ledger.PROVENANCE_REFS`): the acceptance criteria it was dispatched against, the
policy bundle the run is pinned to, the decision record that produced the selection, and the
budget grant that admitted the call. What is under test is not that the fields exist but that
they behave the way the authority inventory (`docs/DECISION-IMPROVEMENT-AUTHORITY-INVENTORY.md`)
says they must:

  * `LEDGER_VERSION` did NOT move. `AttemptLedger.events()` discards every line whose `v` is not
    the current constant and counts it as corrupt, so a bump for an additive field would make
    every historical event in every user's store unreadable -- silently, as a corruption count.
    The first test asserts the constant AND mutation-proves why it matters.
  * The migration is read-time only. An event written before these fields existed loads, and its
    provenance reads `unknown` -- never a default, never a zero, never back-filled.
  * A reference is a pointer, not a payload: an id, optionally the digest of the referenced
    bytes, and the REFERENCED contract's own version. Anything larger is refused; anything that
    is not a reference reads as unknown rather than as itself.
  * A crash keeps what it recorded. Before the started record there is nothing to reconcile;
    between the started record and its finish the attempt closes as `unknown` with its
    references intact and its allowance still consumed; after verify and before projection the
    verdict is re-projected rather than re-dispatched.
  * Nothing here claims exactly-once execution, replays an attempt, or refunds a call whose
    outcome nobody observed.
  * `max-dispatches` still means exactly what it meant, and review/acceptance overhead still
    sits outside it in `max-model-calls`.

============================================================================================
 SAFETY CONTRACT
============================================================================================
No test here invokes a real `claude`/`codex`/`copilot`/`cursor`/`graphify` binary or touches a
real `~/.claude`/`~/.codex`/`~/.copilot` home. Every ledger lives in a
`tempfile.TemporaryDirectory()`, and `POLYTROPOS_DATA_HOME` is pinned to a temp directory for
the whole module so no default store can ever resolve into the real per-user data root -- the
same seam `tests/test_attempt_ledger.py` uses. The one end-to-end driver run dispatches a temp
bash STUB written by this test, never a CLI off PATH, and its pricing is the synthetic
`fake-*` fixture, never `data/pricing.json`.
"""

import ast
import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_claude_execute as tce

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


al = _load("attempt_ledger")
kc = _load("kit_contract")
ah = _load("attempt_history")
ce = tce.ce

_DATA_HOME = None
_DATA_HOME_PATCH = None


def setUpModule():
    global _DATA_HOME, _DATA_HOME_PATCH
    _DATA_HOME = tempfile.TemporaryDirectory(prefix="polytropos-test-data-")
    _DATA_HOME_PATCH = mock.patch.dict(os.environ, {"POLYTROPOS_DATA_HOME": _DATA_HOME.name})
    _DATA_HOME_PATCH.start()


def tearDownModule():
    _DATA_HOME_PATCH.stop()
    _DATA_HOME.cleanup()


#: A pid that cannot be alive, so a claim naming it is stale.
DEAD_PID = 2 ** 22 - 7

#: The event kinds the attempt ledger owns. Used by the one-writer test.
ATTEMPT_KINDS = {"attempt.started", "attempt.finished", "verify.finished", "task.projected"}

#: A task as `kit_contract.parse_tasks` produces one, with acceptance text and a verify command.
FIXTURE_TASK = {
    "id": "T1", "title": "fixture", "status": "pending", "model": "fake-haiku",
    "depends": [], "independent": True, "evidence": None,
    "brief": "do the fixture thing",
    "acceptance": "The fixture thing is done and says so.",
    "verify": "true",
}

#: A pre-D04 event stream: the exact field set `record_started`/`record_finished`/
#: `record_projected` wrote before provenance references existed, stamped with the SAME
#: `LEDGER_VERSION` the code carries today. Hand-written on purpose -- the point of the test is
#: that a reader written after the change still reads bytes written before it.
HISTORICAL_EVENTS = [
    {"v": "polytropos.attempts/1", "ts": "2026-01-01T00:00:00.000000Z", "kind": "claim.taken",
     "run": "2026-01-01-old1", "task": "T1", "stale_from": None},
    {"v": "polytropos.attempts/1", "ts": "2026-01-01T00:00:01.000000Z", "kind": "attempt.started",
     "run": "2026-01-01-old1", "task": "T1", "attempt": "aaaabbbb", "op": "initial",
     "model": "fake-haiku", "prompt_sha": "0" * 64, "verify_sha": "1" * 64,
     "artifact": "fp-old", "role": "implementer", "parent": None,
     "requested_model": "fake-haiku", "effort": None, "actor": "claude-code"},
    {"v": "polytropos.attempts/1", "ts": "2026-01-01T00:00:02.000000Z",
     "kind": "attempt.finished", "run": "2026-01-01-old1", "task": "T1", "attempt": "aaaabbbb",
     "outcome": "ok", "rc": 0, "class": None, "report": "did it", "report_redactions": {},
     "duration_s": None},
    {"v": "polytropos.attempts/1", "ts": "2026-01-01T00:00:03.000000Z", "kind": "verify.finished",
     "run": "2026-01-01-old1", "task": "T1", "attempt": "aaaabbbb", "rc": 0,
     "signature": "2" * 64, "failures": None, "tail": "OK", "tail_redactions": {},
     "artifact": "fp-old"},
    {"v": "polytropos.attempts/1", "ts": "2026-01-01T00:00:04.000000Z", "kind": "task.projected",
     "run": "2026-01-01-old1", "task": "T1", "status": "done", "result": "pass",
     "outcome_line": True, "note": "", "artifact": "fp-old", "upstream": {}},
]


def _seed(root, namespace, events):
    """Write an event stream by hand, the way a store written by an older release looks."""
    path = Path(root) / namespace
    path.mkdir(parents=True, exist_ok=True)
    (path / al.EVENTS_FILE).write_text(
        "".join(json.dumps(ev, sort_keys=True) + "\n" for ev in events), encoding="utf-8"
    )


def _started(ledger, task="T1"):
    return [ev for ev in ledger.events()
            if ev.get("kind") == "attempt.started" and ev.get("task") == task]


class AttemptProvenanceTests(unittest.TestCase):

    # ---- the constraint that governs everything else -----------------------------------------

    def test_the_ledger_version_did_not_move_and_a_bump_would_hide_every_old_event(self):
        # The constant itself, pinned: additive optional fields keep `polytropos.attempts/1`.
        self.assertEqual(al.LEDGER_VERSION, "polytropos.attempts/1")
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            ledger.record_started("r1", "T1", "initial", "fake-haiku",
                                  acceptance_ref=al.make_ref("acc-1"))
            self.assertEqual(len(ledger.events()), 1)
            self.assertEqual(ledger.corrupt, 0)
            # Mutation proof of WHY: the reader gates on equality, so a bumped constant does not
            # migrate the store, it discards it -- and reports the loss as corruption.
            with mock.patch.object(al, "LEDGER_VERSION", "polytropos.attempts/2"):
                self.assertEqual(ledger.events(), [])
                self.assertEqual(ledger.corrupt, 1)
            self.assertEqual(len(ledger.events()), 1)
            self.assertEqual(ledger.corrupt, 0)

    # ---- old records load ---------------------------------------------------------------------

    def test_an_event_stream_written_before_provenance_existed_loads_and_reads_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            _seed(tmp, "kit-old", HISTORICAL_EVENTS)
            ledger = al.AttemptLedger(tmp, "kit-old")
            events = ledger.events()
            self.assertEqual(len(events), len(HISTORICAL_EVENTS))
            self.assertEqual(ledger.corrupt, 0, "an old line is not corruption")
            history = ledger.task_history("T1")
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["finished"]["outcome"], "ok")
            # Every reference answers, and every answer is unknown.
            prov = al.provenance(history[0]["started"])
            self.assertEqual(set(prov), set(al.PROVENANCE_REFS))
            self.assertEqual(list(prov.values()), [None, None, None, None])
            self.assertEqual(al.ref_gaps(None), sorted(al.REF_FIELDS))
            # The projection is equally unknown, and nothing back-fills it from the task.
            acc = ledger.latest_acceptance("T1")
            self.assertIsNotNone(acc)
            self.assertIsNone(al.provenance(acc)["acceptance_ref"])
            self.assertEqual(acc.get("artifact"), "fp-old")

    def test_reading_an_old_stream_never_rewrites_it(self):
        # Read-time migration means the bytes on disk do not change when a new reader opens them.
        with tempfile.TemporaryDirectory() as tmp:
            _seed(tmp, "kit-old", HISTORICAL_EVENTS)
            path = Path(tmp) / "kit-old" / al.EVENTS_FILE
            before = path.read_bytes()
            ledger = al.AttemptLedger(tmp, "kit-old")
            ledger.events()
            ledger.task_history("T1")
            ledger.usage()
            ledger.unprojected("T1")
            self.assertEqual(path.read_bytes(), before)

    # ---- references round-trip ----------------------------------------------------------------

    def test_every_reference_round_trips_with_its_digest_and_its_own_contract_version(self):
        refs = {
            "acceptance_ref": al.make_ref("acc-9", sha="a" * 64, version="polytropos.task/1"),
            "policy_ref": al.make_ref("bundle-3", sha="b" * 64, version="example.bundle/1"),
            "decision_ref": al.make_ref("dec-7", sha="c" * 64, version="example.decision/1"),
            "admission_ref": al.make_ref("grant-2", sha="d" * 64, version="polytropos.task/1"),
        }
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            attempt = ledger.record_started("r1", "T1", "initial", "fake-haiku", **refs)
            started = _started(ledger)[0]
            self.assertEqual(started["attempt"], attempt)
            self.assertEqual(al.provenance(started), refs)
            for name, ref in refs.items():
                with self.subTest(ref=name):
                    self.assertEqual(al.ref_gaps(ref), [])
            # The version on the line stays the LEDGER's; the version inside a reference is the
            # referenced contract's. They are different facts and must not be conflated.
            self.assertEqual(started["v"], al.LEDGER_VERSION)
            self.assertNotEqual(refs["decision_ref"]["v"], al.LEDGER_VERSION)

    def test_a_partially_known_reference_names_its_gaps_instead_of_completing_them(self):
        ref = al.make_ref("dec-1")
        self.assertEqual(ref, {"id": "dec-1", "sha": None, "v": None})
        self.assertEqual(al.ref_gaps(ref), ["sha", "v"])
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            ledger.record_started("r1", "T1", "initial", "m", decision_ref=ref)
            read = al.provenance(_started(ledger)[0])["decision_ref"]
            self.assertEqual(read, ref)
            self.assertEqual(al.ref_gaps(read), ["sha", "v"])

    def test_an_attempt_recording_no_reference_writes_no_field_at_all(self):
        # Absent, not an explicit null: a line written today without references is the same
        # shape as one written before they existed, so nothing has to tell them apart.
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            ledger.record_started("r1", "T1", "initial", "m")
            started = _started(ledger)[0]
            for name in al.PROVENANCE_REFS:
                self.assertNotIn(name, started)
            self.assertEqual(list(al.provenance(started).values()), [None] * 4)

    # ---- a reference is a pointer, never a payload ---------------------------------------------

    def test_the_ledger_refuses_anything_that_is_not_an_identity(self):
        for bad in (None, "", "   ", 7, True, {"id": "x"}, ["x"]):
            with self.subTest(bad=bad):
                with self.assertRaises(al.RefError):
                    al.make_ref(bad)
        with self.assertRaises(al.RefError):
            al.make_ref("x", sha=b"bytes")
        with self.assertRaises(al.RefError):
            al.make_ref("x" * (al.REF_PART_CHARS + 1))
        with self.assertRaises(al.RefError):
            al.make_ref("x", sha="s" * (al.REF_PART_CHARS + 1))
        # A payload smuggled in as a "reference" is refused where it is recorded, too.
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            with self.assertRaises(al.RefError):
                ledger.record_started("r1", "T1", "initial", "m",
                                      decision_ref={"rubric": "x" * 4000})
            with self.assertRaises(al.RefError):
                ledger.record_started("r1", "T1", "initial", "m", policy_ref="bundle-3")
            with self.assertRaises(al.RefError):
                al.validated_refs(rubric_ref=al.make_ref("x"))
            self.assertEqual(ledger.events(), [], "a refused record writes nothing")

    def test_an_unreadable_reference_reads_as_unknown_rather_than_as_itself(self):
        # A store can hold anything a hand-edit put there. Guessing what a malformed reference
        # meant would INVENT provenance, so it reads exactly like absence.
        damaged = dict(HISTORICAL_EVENTS[1])
        damaged.update({"decision_ref": 7, "policy_ref": "bundle-3",
                        "acceptance_ref": {"sha": "a" * 64}, "admission_ref": {"id": "  "}})
        with tempfile.TemporaryDirectory() as tmp:
            _seed(tmp, "kit-bent", [HISTORICAL_EVENTS[0], damaged])
            ledger = al.AttemptLedger(tmp, "kit-bent")
            self.assertEqual(len(ledger.events()), 2)
            self.assertEqual(ledger.corrupt, 0, "an unreadable reference is not a corrupt line")
            self.assertEqual(list(al.provenance(_started(ledger)[0]).values()), [None] * 4)

    # ---- crash and resume ----------------------------------------------------------------------

    def test_a_crash_before_the_attempt_was_recorded_leaves_nothing_to_reconcile(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            run1 = kc.TaskRun(ledger, "r1", dict(FIXTURE_TASK), workspace=tmp)
            run1.begin()  # claimed, run.started written, then the process dies here
            ledger.release("T1", "r1")
            run2 = kc.TaskRun(ledger, "r2", dict(FIXTURE_TASK), workspace=tmp)
            info = run2.begin()
            self.assertEqual(info["closed_unknown"], [])
            self.assertEqual(info["unprojected"], [])
            self.assertEqual(ledger.usage(),
                             {"max-dispatches": 0, "max-escalations": 0, "max-consults": 0,
                              "max-model-calls": 0})

    def test_a_crash_between_the_started_record_and_its_finish_keeps_every_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            admission = kc.BudgetAdmission({"max-dispatches": 3})
            run1 = kc.TaskRun(ledger, "r1", dict(FIXTURE_TASK), workspace=tmp)
            run1.bind_admission(admission)
            run1.begin()
            ok, _ = admission.admit("initial")
            self.assertTrue(ok)
            attempt = run1.attempt_started("initial", "fake-haiku", prompt="p", verify_cmd="true")
            before = al.provenance(_started(ledger)[0])
            self.assertIsNotNone(before["acceptance_ref"])
            self.assertIsNotNone(before["admission_ref"])

            # The process dies. A later run closes the attempt as UNKNOWN and does not replay it.
            ledger.release("T1", "r1")
            run2 = kc.TaskRun(ledger, "r2", dict(FIXTURE_TASK), workspace=tmp)
            info = run2.begin()
            self.assertEqual(info["closed_unknown"], [attempt])
            history = ledger.task_history("T1")
            self.assertEqual(len(history), 1, "a resume settles the attempt, it does not add one")
            self.assertEqual(history[0]["finished"]["outcome"], al.OUTCOME_UNKNOWN)
            self.assertEqual(history[0]["finished"]["class"], "unknown")
            self.assertEqual(al.recovery_for("unknown"), "stop")
            # The references survive the takeover unchanged: they live on the started event.
            self.assertEqual(al.provenance(history[0]["started"]), before)
            # And the allowance the attempt consumed stays consumed. No refund for an unknown.
            self.assertEqual(ledger.usage()["max-dispatches"], 1)
            self.assertEqual(admission.used["max-dispatches"], 1)

    def test_a_crash_after_verify_but_before_projection_reprojects_with_its_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            run1 = kc.TaskRun(ledger, "r1", dict(FIXTURE_TASK), workspace=tmp)
            run1.begin()
            attempt = run1.attempt_started("initial", "fake-haiku", verify_cmd="true")
            run1.attempt_finished(attempt, 0, "done")
            run1.verify_finished(attempt, 0, "OK")
            # ... and the process dies before TASKS.md/NOTES.md say so.
            pending = ledger.unprojected("T1")
            self.assertEqual([ev["attempt"] for ev in pending], [attempt])

            ledger.release("T1", "r1")
            run2 = kc.TaskRun(ledger, "r2", dict(FIXTURE_TASK), workspace=tmp)
            run2.begin()
            run2.project("done", "pass", outcome_line=True)
            acc = ledger.latest_acceptance("T1")
            self.assertEqual(al.provenance(acc)["acceptance_ref"],
                             kc.acceptance_identity(FIXTURE_TASK))
            self.assertEqual(ledger.unprojected("T1"), [])
            # Re-projecting a verdict already held is not a second dispatch.
            self.assertEqual(len(ledger.task_history("T1")), 1)

    def test_a_duplicate_completion_neither_adds_an_attempt_nor_spends_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            run = kc.TaskRun(ledger, "r1", dict(FIXTURE_TASK), workspace=tmp)
            run.begin()
            attempt = run.attempt_started("initial", "fake-haiku")
            run.attempt_finished(attempt, 0, "first record")
            run.attempt_finished(attempt, 0, "the same attempt, recorded twice")
            history = ledger.task_history("T1")
            self.assertEqual(len(history), 1)
            self.assertIn("recorded twice", history[0]["finished"]["report"])
            self.assertEqual(ledger.open_attempts("T1"), [])
            self.assertEqual(ledger.reconcile_open("r2", "T1", "nothing is open"), [])
            self.assertEqual(ledger.usage()["max-dispatches"], 1)
            self.assertIsNotNone(al.provenance(history[0]["started"])["acceptance_ref"])

    def test_a_stale_claim_is_taken_over_and_the_dead_runs_references_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            first = kc.BudgetAdmission({"max-dispatches": 4})
            run1 = kc.TaskRun(ledger, "r1", dict(FIXTURE_TASK), workspace=tmp)
            run1.bind_admission(first)
            run1.begin()
            first.admit("initial")
            dead_attempt = run1.attempt_started("initial", "fake-haiku")
            dead_refs = al.provenance(_started(ledger)[0])

            # The holder's process is gone; its lock names a pid that cannot be alive.
            lock = Path(tmp) / "kit-a" / al.CLAIMS_DIR / "T1.lock"
            lock.write_text(json.dumps({"run": "r1", "pid": DEAD_PID, "ts": al.utc_now()}))

            second = kc.BudgetAdmission({"max-dispatches": 4}, used=ledger.usage())
            run2 = kc.TaskRun(ledger, "r2", dict(FIXTURE_TASK), workspace=tmp)
            run2.bind_admission(second)
            info = run2.begin()
            self.assertEqual((info["stale_from"] or {}).get("pid"), DEAD_PID)
            self.assertEqual(info["closed_unknown"], [dead_attempt])
            second.admit("retry")
            live_attempt = run2.attempt_started("retry", "fake-haiku")

            by_id = {h["attempt"]: h for h in ledger.task_history("T1")}
            self.assertEqual(al.provenance(by_id[dead_attempt]["started"]), dead_refs)
            live = al.provenance(by_id[live_attempt]["started"])
            self.assertIsNotNone(live["admission_ref"])
            self.assertNotEqual(live["admission_ref"]["id"], dead_refs["admission_ref"]["id"],
                                "a resumed run's attempt is admitted by its own grant")

    def test_a_budget_exhausted_resume_refuses_before_it_spends_and_mints_no_grant(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            # One unprojected attempt from a dead run already spent the kit's single dispatch.
            ledger.record_started("r1", "T1", "initial", "fake-haiku")
            used = kc.combined_usage("", ledger)
            self.assertEqual(used["max-dispatches"], 1)
            admission = kc.BudgetAdmission({"max-dispatches": 1}, used=used)
            run2 = kc.TaskRun(ledger, "r2", dict(FIXTURE_TASK), workspace=tmp)
            run2.bind_admission(admission)
            ok, reason = admission.admit("retry")
            self.assertFalse(ok)
            self.assertIn("max-dispatches=1", reason)
            self.assertEqual(admission.grants, [], "a refusal is not a grant")
            self.assertEqual(admission.granted, [])
            self.assertIsNone(admission.ref_for("retry"))
            self.assertEqual(admission.used["max-dispatches"], 1, "a refusal consumes nothing")
            # Nothing was dispatched, so nothing was recorded: no attempt, no reference.
            self.assertEqual(len(_started(ledger)), 1)

    def test_a_failed_dispatch_whose_check_would_pass_keeps_its_provenance_and_its_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            admission = kc.BudgetAdmission({"max-dispatches": 2})
            run = kc.TaskRun(ledger, "r1", dict(FIXTURE_TASK), workspace=tmp)
            run.bind_admission(admission)
            run.begin()
            admission.admit("initial")
            attempt = run.attempt_started("initial", "fake-haiku", verify_cmd="true")
            cls = run.attempt_finished(attempt, 1, "Error: Not logged in. Run `login`.")
            self.assertEqual(cls, "auth")
            self.assertEqual(al.recovery_for(cls), "stop")
            # The check passes on the tree the failed dispatch never touched. That is a fact
            # about the tree, not about work this attempt did -- and it changes nothing about
            # what the attempt consumed or which decisions it was made under.
            run.verify_finished(attempt, 0, "OK")
            history = ledger.task_history("T1")[0]
            self.assertEqual(history["finished"]["class"], "auth")
            self.assertEqual(history["verify"]["rc"], 0)
            prov = al.provenance(history["started"])
            self.assertIsNotNone(prov["acceptance_ref"])
            self.assertIsNotNone(prov["admission_ref"])
            self.assertEqual(ledger.usage()["max-dispatches"], 1)

    # ---- grants ---------------------------------------------------------------------------------

    def test_a_grant_is_minted_at_admission_funds_one_attempt_and_is_never_reused(self):
        admission = kc.BudgetAdmission({"max-dispatches": 3, "max-escalations": 2})
        self.assertIsNone(admission.ref_for("initial"), "no grant, no reference")
        admission.admit("initial")
        self.assertEqual(admission.granted, ["initial"])
        self.assertEqual(len(admission.grants), 1)
        ref = admission.ref_for("initial")
        self.assertEqual(ref["id"], admission.grants[0]["id"])
        self.assertEqual(ref["sha"], admission.grants[0]["sha"])
        self.assertEqual(ref["v"], kc.CONTRACT_VERSION)
        self.assertEqual(al.ref_gaps(ref), [])
        # One grant funds one operation: a second attempt cannot inherit it.
        self.assertIsNone(admission.ref_for("initial"))
        # A grant of a different kind is not this operation's grant.
        admission.admit("escalation")
        self.assertIsNone(admission.ref_for("initial"))
        self.assertIsNotNone(admission.ref_for("escalation"))
        # The id is content-free; the digest is over the grant's own content.
        self.assertNotIn("escalation", admission.grants[1]["id"])
        self.assertNotEqual(admission.grants[0]["sha"], admission.grants[1]["sha"])

    def test_an_attempt_records_no_admission_reference_when_no_budget_admitted_it(self):
        # A kit that declares no budget has no admission at all. That is unknown, not
        # "unadmitted", and nothing invents a grant to fill the field.
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            run = kc.TaskRun(ledger, "r1", dict(FIXTURE_TASK), workspace=tmp)
            self.assertIsNone(run.admission)
            run.attempt_started("initial", "fake-haiku")
            self.assertIsNone(al.provenance(_started(ledger)[0])["admission_ref"])

    # ---- acceptance identity ---------------------------------------------------------------------

    def test_the_acceptance_identity_changes_with_the_criteria_and_with_the_check(self):
        base = kc.acceptance_identity(FIXTURE_TASK)
        self.assertEqual(base["v"], kc.CONTRACT_VERSION)
        self.assertEqual(len(base["sha"]), 64)
        self.assertEqual(base["id"], base["sha"][:16])
        self.assertEqual(base, kc.acceptance_identity(dict(FIXTURE_TASK)), "stable")
        reworded = dict(FIXTURE_TASK, acceptance="The fixture thing is done. Mostly.")
        rechecked = dict(FIXTURE_TASK, verify="python3 -m unittest something_else")
        renamed = dict(FIXTURE_TASK, id="T2")
        for name, task in (("acceptance", reworded), ("verify", rechecked), ("id", renamed)):
            with self.subTest(changed=name):
                self.assertNotEqual(kc.acceptance_identity(task)["sha"], base["sha"])

    def test_a_task_declaring_no_acceptance_has_no_identity_rather_than_an_empty_one(self):
        for task in ({"id": "T1"}, {"id": "T1", "acceptance": ""},
                     {"id": "T1", "acceptance": "   "}, None):
            with self.subTest(task=task):
                self.assertIsNone(kc.acceptance_identity(task))
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            run = kc.TaskRun(ledger, "r1", {"id": "T1"}, workspace=tmp)
            run.attempt_started("initial", "m")
            run.project("done", "pass", outcome_line=True)
            self.assertIsNone(al.provenance(_started(ledger)[0])["acceptance_ref"])
            self.assertIsNone(
                al.provenance(ledger.latest_acceptance("T1"))["acceptance_ref"])

    def test_nothing_mints_a_policy_or_decision_reference_at_this_revision(self):
        # Honest state, asserted rather than assumed: the bundle contract (D11) and the decision
        # contract (D09) do not exist yet, so a run pins neither and both read unknown. The seam
        # accepts one the moment there is one to accept.
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            default = kc.TaskRun(ledger, "r1", dict(FIXTURE_TASK), workspace=tmp)
            self.assertIsNone(default.policy_ref)
            self.assertIsNone(default.decision_ref)
            default.attempt_started("initial", "fake-haiku")
            prov = al.provenance(_started(ledger)[0])
            self.assertIsNone(prov["policy_ref"])
            self.assertIsNone(prov["decision_ref"])

            pinned = kc.TaskRun(ledger, "r2", dict(FIXTURE_TASK, id="T2"), workspace=tmp,
                                policy_ref=al.make_ref("bundle-1", version="example.bundle/1"),
                                decision_ref=al.make_ref("dec-1", version="example.decision/1"))
            pinned.attempt_started("initial", "fake-haiku")
            prov = al.provenance(_started(ledger, task="T2")[0])
            self.assertEqual(prov["policy_ref"]["id"], "bundle-1")
            self.assertEqual(prov["decision_ref"]["id"], "dec-1")

    # ---- what a cap means is untouched --------------------------------------------------------

    def test_max_dispatches_still_means_what_it_meant_and_review_overhead_sits_outside_it(self):
        # Frozen arithmetic: `max-dispatches` counts every model call on a TASK -- initial,
        # retry, escalation, consult -- and has never counted phase review or final acceptance.
        # Provenance adds a field to an event; it redefines no cap.
        self.assertEqual(kc.OPERATION_CAPS, {
            "initial": ("max-dispatches", "max-model-calls"),
            "retry": ("max-dispatches", "max-model-calls"),
            "escalation": ("max-dispatches", "max-escalations", "max-model-calls"),
            "consult": ("max-dispatches", "max-consults", "max-model-calls"),
            "review": ("max-model-calls",),
            "acceptance": ("max-model-calls",),
        })
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            for op in ("initial", "retry", "escalation", "consult", "review", "acceptance"):
                ledger.record_started("r1", "T1", op, "fake-haiku",
                                      acceptance_ref=al.make_ref("acc-1", version="x/1"))
            self.assertEqual(ledger.usage(), {
                "max-dispatches": 4, "max-escalations": 1, "max-consults": 1,
                "max-model-calls": 6,
            })
            admission = kc.BudgetAdmission({"max-dispatches": 4, "max-model-calls": 6})
            for op in ("initial", "retry", "escalation", "consult", "review", "acceptance"):
                self.assertTrue(admission.admit(op)[0], op)
            self.assertEqual(admission.used["max-dispatches"], 4)
            self.assertEqual(admission.used["max-model-calls"], 6)
            self.assertFalse(admission.admit("review")[0], "the aggregate cap still binds")

    # ---- one writer -------------------------------------------------------------------------------

    def test_the_attempt_event_kinds_are_appended_from_exactly_one_module(self):
        # Derived structurally rather than by grep: a kind literal sitting on the line after
        # `append(` is invisible to the obvious pattern, which is how kinds were missed before.
        writers = {}
        for path in sorted(BIN_DIR.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                name = (fn.attr if isinstance(fn, ast.Attribute)
                        else fn.id if isinstance(fn, ast.Name) else None)
                if name not in ("append", "_record") or not node.args:
                    continue
                first = node.args[0]
                if isinstance(first, ast.Constant) and first.value in ATTEMPT_KINDS:
                    writers.setdefault(first.value, set()).add(path.name)
        self.assertEqual(set(writers), ATTEMPT_KINDS, "every attempt kind is still written")
        for kind, files in sorted(writers.items()):
            with self.subTest(kind=kind):
                self.assertEqual(files, {"attempt_ledger.py"},
                                 f"{kind} is appended from {sorted(files)}; the attempt ledger "
                                 f"is the one writer of attempt events")

    # ---- the projection discloses what nobody recorded -------------------------------------------

    def test_the_record_fields_and_the_ledgers_reference_names_cannot_drift(self):
        self.assertEqual(tuple(ah.PROVENANCE_FIELDS), tuple(al.PROVENANCE_REFS))
        for name in al.PROVENANCE_REFS:
            with self.subTest(field=name):
                self.assertIn(name, ah.RECORD_FIELDS)
                # `observe` raises for a key outside RECORD_FIELDS, so this is what makes a
                # reference projectable at all.
                self.assertEqual(ah.observe(ah.blank(), **{name: {"id": "x"}})[name], {"id": "x"})

    def test_the_history_projects_every_reference_and_counts_the_ones_nobody_recorded(self):
        registry = ah._mod("model_registry").registry()
        with tempfile.TemporaryDirectory() as tmp:
            ledger = al.AttemptLedger(tmp, "kit-a")
            with_refs = ledger.record_started(
                "r1", "T1", "initial", "fake-haiku",
                acceptance_ref=al.make_ref("acc-1", sha="a" * 64, version="polytropos.task/1"),
                admission_ref=al.make_ref("grant-1", sha="d" * 64, version="polytropos.task/1"),
            )
            ledger.record_finished("r1", "T1", with_refs, "ok", 0, "did it")
            without = ledger.record_started("r1", "T2", "initial", "fake-haiku")
            ledger.record_finished("r1", "T2", without, "ok", 0, "did it")
            records = ah.ledger_records("kit-a", ledger, registry)
            by_task = {r["task"]: r for r in records}
            self.assertEqual(by_task["T1"]["acceptance_ref"]["id"], "acc-1")
            self.assertEqual(by_task["T1"]["admission_ref"]["v"], "polytropos.task/1")
            self.assertIn("acceptance_ref", by_task["T1"]["observed"])
            self.assertIsNone(by_task["T1"]["policy_ref"])
            self.assertNotIn("policy_ref", by_task["T1"]["observed"])
            for name in al.PROVENANCE_REFS:
                self.assertIsNone(by_task["T2"][name])

            card = ah.summarize(records, registry=registry)
            self.assertEqual(card["unknown"]["acceptance_ref"], 1)
            self.assertEqual(card["unknown"]["admission_ref"], 1)
            self.assertEqual(card["unknown"]["policy_ref"], 2)
            self.assertEqual(card["unknown"]["decision_ref"], 2)
            self.assertEqual(card["schema"], ah.HISTORY_VERSION,
                             "an additive record field does not restamp the card")
            rendered = ah.render_markdown(card)
            self.assertIn("unknown provenance:", rendered)
            self.assertIn("policy=2", rendered)
            self.assertIn("never inferred", rendered)

    # ---- the production path --------------------------------------------------------------------

    def test_every_native_driver_binds_the_admission_it_creates(self):
        # Cursor reaches the binding through the shared `budget_gate`; the other three carry
        # the admission block inline and bind where they build it.
        self.assertIn("bind_admission", ast.get_source_segment(
            (BIN_DIR / "kit_contract.py").read_text(encoding="utf-8"),
            next(n for n in ast.parse((BIN_DIR / "kit_contract.py").read_text(encoding="utf-8")).body
                 if isinstance(n, ast.FunctionDef) and n.name == "budget_gate")))
        for driver in ("claude_execute", "codex_execute", "copilot_execute"):
            with self.subTest(driver=driver):
                text = (BIN_DIR / f"{driver}.py").read_text(encoding="utf-8")
                fn = next(n for n in ast.parse(text).body
                          if isinstance(n, ast.FunctionDef) and n.name == "cmd_run")
                self.assertIn("bind_admission", ast.get_source_segment(text, fn))
        self.assertIn("budget_gate", (BIN_DIR / "cursor_execute.py").read_text(encoding="utf-8"))

    def test_an_end_to_end_driver_run_records_the_acceptance_and_the_grant(self):
        # A whole `claude_execute run` against a temp checkout, a temp attempt store, and a
        # temp bash STUB. Nothing off PATH is invoked and no real home is read.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tce._write_agent_bundle(root, "fixturekit", "implementer", tce.PREAMBLE_FIXTURE_BODY)
            marker = root / "work-done.marker"
            kits = root / ".claude" / "kits"
            kits.mkdir(parents=True)
            kit = tce._write_kit(kits, tce._single_task_text(f'test -f "{marker}"'),
                                 slug="fixturekit")
            (kit / "PLAN.md").write_text("# plan\n\nbudget: max-dispatches=2\n")
            store = root / "ledger-store"
            log = root / "stub.log"
            stub = tce._write_stub(root, log, marker)

            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(ce, "REPO_ROOT", root), \
                    mock.patch.object(ce, "load_pricing", return_value=tce.PRICING_FIXTURE), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                ce.main(["run", "--kit", str(kit), "--claude-bin", str(stub),
                         "--attempt-store", str(store)])

            ledger = al.AttemptLedger(store, "fixturekit")
            self.assertEqual(ledger.corrupt, 0)
            started = _started(ledger, task="E1")
            self.assertEqual(len(started), 1, "one dispatch, one attempt")
            prov = al.provenance(started[0])
            task = ce.parse_tasks((kit / "TASKS.md").read_text())[0]
            self.assertEqual(prov["acceptance_ref"], kc.acceptance_identity(task))
            self.assertIsNotNone(prov["admission_ref"], "the grant that admitted the dispatch")
            self.assertEqual(prov["admission_ref"]["v"], kc.CONTRACT_VERSION)
            self.assertEqual(al.ref_gaps(prov["admission_ref"]), [])
            # Nothing mints a policy or decision reference yet, and none is invented.
            self.assertIsNone(prov["policy_ref"])
            self.assertIsNone(prov["decision_ref"])
            # The verdict's projection names the criteria it was reached against.
            acc = ledger.latest_acceptance("E1")
            self.assertEqual(acc["status"], "done")
            self.assertEqual(al.provenance(acc)["acceptance_ref"],
                             kc.acceptance_identity(task))


if __name__ == "__main__":
    unittest.main()
