"""D13 -- which action a run takes under the existing routing, and why.

`LegacySelectionTests` covers the selection half of `bin/decision_policy.py`: `select_action`
and the two seam adapters that feed it. D11 owns the other half of the same file -- bundle
resolution -- and `PolicyBundleContractTests` in `tests/test_decision_policy_bundle.py` is
untouched by this one; so are D09's and D10's classes in `tests/test_decision_contract.py`,
D12's in `tests/test_decision_provider.py`, and D02's goldens in `tests/test_decision_legacy.py`,
which this task's verify command re-runs as a REGRESSION guard rather than as a subject.

What is under test is not that a selection has fields but that it refuses what it must:

  * LEGACY IS THE ANSWER. In both modes this module implements, the selected action is the one
    the existing routing already picked, or nothing at all. Advice that disagrees is RECORDED
    and not followed. Take the bundle away and the behaviour is the behaviour that was there
    before any of this existed.
  * CONFIDENCE IS NOT AUTHORITY. `_admissible(action, facts)` has no parameter a probability,
    a calibrated number or a vendor confidence could arrive through, and nothing in the module
    reads one. A maximally confident recommendation for a denied action and an abstention reach
    that function as the same thing: a name.
  * AN EXPLICIT PIN AND A RESERVED DEFAULT SURVIVE. A recommendation naming anything but the
    pin is refused as such, a recommendation naming a held-back reserved model is refused as
    such, and a baseline that is not the pin refuses the whole selection rather than quietly
    standing in for it.
  * STALE ADVICE IS NOT WEAK ADVICE. A result correlated to another call, or about an older
    state, or about a different question set, is dropped whole; so is an abstention, a terminal
    status, and a recommendation that was never an eligible alternative.
  * AN UNMADE CHECK IS NOT A PASSED CHECK. The four fresh coordinator checks are consumed, never
    performed, and `None` refuses exactly as `False` does.
  * ACTIVATION IS SOMEBODY ELSE'S. `canary` and `active` are refused by name rather than
    downgraded to shadow, and nothing here reads, locates or consumes a runtime pointer.

============================================================================================
 SAFETY CONTRACT
============================================================================================
Nothing here invokes a real `claude`/`codex`/`copilot`/`cursor`/`graphify` binary, reads a real
`~/.claude`/`~/.codex`/`~/.copilot` home, opens a store, writes a file, starts a process or
touches the network. Every fixture is a synthetic dict built in this file; no pricing file is
read and no model id in it appears in any `data/pricing*.json`. The module under test is a pure
library with no I/O at all, and `bin/workflow_eval.py` is deliberately NOT loaded here -- its
module-level constants resolve through the per-user data root at import time, and this file
needs nothing from it.

ONE LOADER, ON PURPOSE. `bin/` is not a package, so each module is loaded by path and two
loaders of one file produce two distinct sets of classes. This file reads the contract and the
router through `decision_policy`'s OWN instances, so a class identity is never accidentally
compared across a boundary -- and one test deliberately builds a second contract instance to
prove the selection path survives it.
"""

import ast
import dataclasses
import hashlib
import importlib.util
import inspect
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "bin"
POLICY_PATH = BIN_DIR / "decision_policy.py"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dp = _load("decision_policy")
dc = dp._contract()          # the SAME contract instance the module under test uses
rp = dp._rp()                # the SAME router instance, for its filter vocabulary
al = dp._al()
kc = _load("kit_contract")

#: Three eligible actions, so a denial, a pin and a reserved hold-back can each be isolated to
#: one of them without any two fixtures colliding.
BASELINE = "retry-same-model"
OTHER = "retry-with-contract-context"
STOP = "stop"
ALTERNATIVES = [BASELINE, OTHER, STOP]

QUESTION_TEXT = ("Did the failing attempt lack the interface contract of the module it "
                 "called across the boundary?")

STATE_SNAPSHOT = {"head": "0123abcd", "verify_rc": 1, "worktree_dirty": False}

#: A synthetic evaluation-manifest version. The bundle contract requires a provenance pointer to
#: carry its referenced contract's version and deliberately does not interpret WHICH contract
#: that is, so nothing here needs the workbench loaded to say one.
MANIFEST_V = "polytropos.synthetic-manifest/1"
APPROVAL_V = "polytropos.synthetic-approval/1"

PROJECT = "polytropos"
TASK_CLASS = "recovery-cross-module"
USE = "recovery-selection"


def digest(seed):
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def ref(identity, version, sha=None):
    return al.make_ref(identity, sha=digest(identity) if sha is None else sha, version=version)


def question(**over):
    payload = {
        "id": "q-context-missing", "version": "v1", "kind": "boolean",
        "question": QUESTION_TEXT, "rubric": {}, "outcomes": ["false", "true"],
        "abstention": "permitted", "dependencies": [], "sensitivity": "project-internal",
    }
    payload.update(over)
    return payload


def request_payload(**over):
    questions = over.pop("questions", None) or [question()]
    snapshot = over.pop("state", None) or dict(STATE_SNAPSHOT)
    specs = [dc.parse_question(q, f"q[{i}]") for i, q in enumerate(questions)]
    payload = {
        "v": dc.CONTRACT_VERSION,
        "correlation_id": "corr-1",
        "run": "2026-09-17-d13a",
        "task": "D13",
        "attempt": None,
        "intended_use": USE,
        "task_ref": al.make_ref("D13", version=kc.CONTRACT_VERSION),
        "acceptance_ref": al.make_ref("acc-1", sha="a" * 64, version=kc.CONTRACT_VERSION),
        "state": snapshot,
        "state_sha": dc.state_digest(snapshot),
        "alternatives": list(ALTERNATIVES),
        "questions": questions,
        "questions_sha": dc.questions_digest(specs),
        "eligibility": {"project": PROJECT, "providers": ["rules"],
                        "privacy": "project-local"},
        "deadline_s": 30,
        "resource_policy": {"operation_scope": "consult", "call_ceiling": 1,
                            "repair_ceiling": 0},
        "admission_ref": al.make_ref("grant-ask-1", version=kc.CONTRACT_VERSION),
    }
    payload.update(over)
    return payload


def request(**over):
    return dc.parse_request(request_payload(**over))


def answer(**over):
    payload = {"outcome": "true", "abstained": False, "raw": None, "calibrated": None,
               "vendor_confidence": None}
    payload.update(over)
    return payload


#: The most confident answer this contract can express: the whole raw distribution and the whole
#: calibrated distribution on one outcome, and a vendor confidence at the top of its own scale.
#: Used wherever a test needs to show that confidence changed nothing.
CERTAIN = answer(raw={"false": 0.0, "true": 1.0}, calibrated={"false": 0.0, "true": 1.0},
                 vendor_confidence=1.0)


def result_payload(req, **over):
    answers = over.pop("answers", None)
    if answers is None:
        answers = {spec.qualified_id: answer() for spec in req.questions}
    payload = {
        "v": dc.CONTRACT_VERSION,
        "correlation_id": req.correlation_id,
        "state_sha": req.state_sha,
        "questions_sha": req.questions_sha,
        "status": "ok",
        "answers": answers,
        "recommended": OTHER,
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


def bundle_payload(**over):
    payload = {
        "v": dc.BUNDLE_VERSION,
        "id": "bundle-recovery-context-1",
        "parent": ref("bundle-legacy-0", dc.BUNDLE_VERSION),
        "scope": {"project": PROJECT, "task_classes": [TASK_CLASS], "intended_uses": [USE]},
        "components": {"decision_contract": dc.CONTRACT_VERSION,
                       "task_contract": kc.CONTRACT_VERSION, "provider_contract": None},
        "parameters": {"recovery.contract_context_package": True,
                       "recovery.contract_context_files": 4},
        "requirements": {"capabilities": [], "providers": [], "calibration": None},
        "fallback": {"kind": "legacy", "bundle_ref": None},
        "provenance": {"approval_ref": ref("approval-1", APPROVAL_V),
                       "evaluation_ref": ref("manifest-1", MANIFEST_V),
                       "rolled_back_from": None},
    }
    payload.update(over)
    return payload


def routing_candidate(identity, reasons=()):
    """One row of a `routing_policy` decision's `candidates`, in that module's own shape."""
    return {"id": identity, "tier": "fake-tier", "rank": 0, "availability": "available",
            "routable": True, "reserved": False, "efforts": None, "default_effort": None,
            "estimate": None, "note": "", "eligible": not reasons, "reasons": list(reasons)}


def routing_decision(**over):
    """A `routing_policy` decision payload, carrying only what the seam actually reads."""
    payload = {
        "v": rp.CONTRACT_VERSION,
        "harness": "fake-harness",
        "task_id": "D13",
        "policy": rp.DEFAULT_POLICY,
        "model": BASELINE,
        "floor": {"tier": "fake-tier", "rank": 0, "basis": [], "pinned": None,
                  "migrated": None},
        "candidates": [routing_candidate(BASELINE), routing_candidate(OTHER),
                       routing_candidate(STOP)],
        "ladder": [],
        "refusal": None,
    }
    payload.update(over)
    return payload


class LegacySelectionTests(unittest.TestCase):

    # ---- fixtures ---------------------------------------------------------------------------

    def setUp(self):
        self.request = request()
        self.grant = al.make_ref("grant-act-1", version=kc.CONTRACT_VERSION)

    def checks(self, **over):
        base = {name: True for name in dp.COORDINATOR_CHECKS}
        base.update(over)
        return base

    def state(self, **over):
        kwargs = {"request": self.request, "baseline": BASELINE, "checks": self.checks(),
                  "admission_ref": self.grant}
        kwargs.update(over)
        return dp.selection_state(**kwargs)

    def result(self, req=None, **over):
        req = self.request if req is None else req
        return dc.parse_result(result_payload(req, **over), req)

    def bundle(self, **over):
        """A resolution with a real, fully met bundle in force."""
        payload = bundle_payload(**over)
        facts = dp.runtime_facts(
            project=PROJECT, task_class=TASK_CLASS, intended_use=USE,
            components={"decision_contract": dc.CONTRACT_VERSION,
                        "task_contract": kc.CONTRACT_VERSION, "provider_contract": None})
        resolution = dp.resolve_bundle(dp.bundle_ref(payload), [payload], facts)
        self.assertEqual(resolution.source, "pinned", "the shadow fixture needs a live bundle")
        return resolution

    def refusal(self, code, callable_, *args, **kwargs):
        with self.assertRaises(dc.ContractError) as caught:
            callable_(*args, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        return caught.exception

    def rejected(self, selection):
        return {entry["action"]: entry["reason"] for entry in selection.rejected}

    # ---- A. the vocabularies, and what they may not collide with -----------------------------

    def test_the_selection_vocabulary_is_its_own_and_shares_no_code_with_resolution(self):
        """D11's two vocabularies answer "which parameters are in force"; these answer "which
        action is taken". A code meaning both would make either report's tally meaningless."""
        self.assertTrue(dp.SELECTION_REASONS and dp.RESOLUTION_REASONS)
        self.assertEqual(sorted(set(dp.SELECTION_REASONS) & set(dp.RESOLUTION_REASONS)), [])
        # `legacy` IS deliberately the same word in both vocabularies, and forcing it apart
        # would be the mistake: it names one fact -- the frozen existing behaviour -- and two
        # spellings of that would be two things to keep in step for no gain.
        self.assertEqual(sorted(set(dp.SELECTION_MODES) & set(dp.RESOLUTION_SOURCES)),
                         ["legacy"])
        self.assertEqual(list(dp.SELECTION_REASONS), sorted(set(dp.SELECTION_REASONS)))
        self.assertTrue(set(dp.REFUSAL_REASONS) <= set(dp.SELECTION_REASONS))

    def test_the_modes_this_module_implements_plus_the_ones_it_defers_are_the_contracts_own(self):
        """Derived, not copied: a mode word added to the contract has to be classified here as
        implemented or deferred, and cannot simply go unmentioned."""
        self.assertEqual(tuple(dp.SELECTION_MODES) + tuple(dp.DEFERRED_MODES), dc.DECISION_MODES)
        self.assertEqual(sorted(set(dp.SELECTION_MODES) & set(dp.DEFERRED_MODES)), [])

    def test_the_denial_vocabulary_is_the_routers_own_minus_the_one_filter_that_ranks(self):
        """`ranked-lower` means another eligible candidate ranked higher -- exactly the kind of
        choice advice is allowed to have an opinion about. Every other filter is a denial."""
        self.assertIn("ranked-lower", rp.FILTERS)
        self.assertEqual(sorted(dp.denial_reasons()),
                         sorted(set(rp.FILTERS) - set(dp.SOFT_FILTERS)))
        self.assertNotIn("ranked-lower", dp.denial_reasons())
        self.assertTrue(set(dp.SOFT_FILTERS) <= set(rp.FILTERS))
        self.assertEqual(sorted(dp.rejection_reasons()),
                         sorted(set(dp.denial_reasons()) | set(dp.OTHER_REJECTIONS)))

    def test_a_filter_the_router_gains_later_is_a_denial_here_without_anyone_editing_this(self):
        """The split is by SUBTRACTION, so the safe direction is the automatic one."""
        with mock.patch.object(rp, "FILTERS", tuple(rp.FILTERS) + ("newly-invented-filter",)):
            self.assertIn("newly-invented-filter", dp.denial_reasons())
            self.assertIn("newly-invented-filter", dp.rejection_reasons())

    def test_no_name_this_module_defines_is_one_the_contract_bans(self):
        """The ban exists so a payload cannot arrive claiming an authority. A CHECK OUTCOME must
        not be spelled like the grant either -- which is why the budget check is
        `budget_admission`, and why this sweep is what keeps that from drifting back."""
        defined = set(dp.SELECTION_KEYS) | set(dp.COORDINATOR_CHECKS) | set(dp.SELECTION_MODES)
        defined |= set(dp.SELECTION_REASONS) | set(dp.rejection_reasons())
        defined |= {f.name for f in dataclasses.fields(dp.ActionSelection)}
        self.assertTrue(defined, "the name sets are what this test sweeps")
        self.assertTrue(dc.BANNED_FIELDS, "an empty ban has nothing for this sweep to collide")
        self.assertEqual(sorted(name for name in defined if dc._is_banned_key(name)), [])
        # And the ban still matches its own plain spellings, so this is not passing because the
        # comparison quietly stopped banning anything.
        self.assertTrue(dc._is_banned_key("budget"))

    def test_every_reason_this_selection_produces_is_declared_and_every_declared_one_is_used(self):
        tree = ast.parse(POLICY_PATH.read_text(encoding="utf-8"))
        appended = {"codes": set(), "refused": set()}
        constants = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                constants.add(node.value)
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "append" and node.args
                    and isinstance(node.func.value, ast.Name)
                    and isinstance(node.args[0], ast.Constant)):
                continue
            if node.func.value.id in appended:
                appended[node.func.value.id].add(node.args[0].value)
        # Without these the two sweeps below would pass trivially on empty sets -- the vacuous
        # AST guard this phase has shipped more than once.
        self.assertTrue(appended["codes"], "the walk found no selection reasons at all")
        self.assertTrue(appended["refused"], "the walk found no refusal reasons at all")
        self.assertEqual(sorted(appended["codes"] - set(dp.SELECTION_REASONS)), [])
        self.assertEqual(sorted(appended["refused"] - set(dp.REFUSAL_REASONS)), [])
        # Both directions: a declared reason nothing produces is a branch somebody removed.
        self.assertEqual(sorted(set(dp.SELECTION_REASONS) - constants), [])

    def test_every_refusal_reason_carries_the_sentence_its_refusal_is_printed_from(self):
        """A refusal code with no sentence would raise from inside the refusal path, which is
        the one place a raise helps least."""
        self.assertEqual(sorted(dp._REFUSAL_TEXT), sorted(dp.REFUSAL_REASONS))
        for text in dp._REFUSAL_TEXT.values():
            self.assertTrue(text and isinstance(text, str))

    # ---- B. legacy is the answer, and nothing moves it ---------------------------------------

    def test_with_no_bundle_and_no_advice_the_selection_is_the_existing_routings_own(self):
        selection = dp.select_action(self.state())
        self.assertEqual(selection.selected, BASELINE)
        self.assertEqual(selection.baseline, BASELINE)
        self.assertEqual(selection.mode, "legacy")
        self.assertIsNone(selection.refusal)
        self.assertIsNone(selection.recommended)
        self.assertIsNone(selection.recommendation)
        self.assertIsNone(selection.bundle_sha)
        self.assertTrue(selection.reason("legacy-default"))
        self.assertTrue(selection.reason("no-advice"))

    def test_advice_that_disagrees_is_recorded_and_not_followed_in_either_mode(self):
        """The whole safety property of this task, asserted in both modes it implements."""
        for mode, resolution in (("legacy", None), ("shadow", self.bundle())):
            with self.subTest(mode=mode):
                selection = dp.select_action(
                    self.state(), self.result(answers={"q-context-missing@v1": CERTAIN}),
                    resolution, mode=mode)
                self.assertEqual(selection.recommended, OTHER)
                self.assertTrue(selection.recommendation["admissible"])
                self.assertEqual(selection.selected, BASELINE)
                self.assertTrue(selection.reason("advice-differs-from-baseline"))

    def test_a_bundle_that_resolved_does_not_by_itself_change_the_mode_or_the_selection(self):
        """Resolving a bundle says which parameters are in force. It is not an activation, and a
        run stays in the mode its coordinator is actually in."""
        selection = dp.select_action(self.state(), None, self.bundle())
        self.assertEqual(selection.mode, "legacy")
        self.assertEqual(selection.requested_mode, "legacy")
        self.assertEqual(selection.selected, BASELINE)
        self.assertIsNotNone(selection.bundle_sha)

    def test_a_bundles_own_parameters_do_not_reach_the_selection(self):
        """A bundle carrying a routing parameter still selects the baseline: applying one is an
        activation, and this module performs none."""
        resolution = self.bundle(parameters={"routing.default_policy": "adaptive"})
        selection = dp.select_action(self.state(), self.result(), resolution, mode="shadow")
        self.assertEqual(dict(resolution.parameters), {"routing.default_policy": "adaptive"})
        self.assertEqual(selection.selected, BASELINE)

    def test_asking_for_shadow_with_nothing_in_force_restores_legacy(self):
        """Take the bundle away and the behaviour is the one that was there before any of this
        existed -- including the mode word the record carries."""
        for resolution in (None, dp.resolve_bundle(None, [], self.bundle_facts())):
            with self.subTest(resolution=resolution):
                selection = dp.select_action(self.state(), self.result(), resolution,
                                             mode="shadow")
                self.assertEqual(selection.requested_mode, "shadow")
                self.assertEqual(selection.mode, "legacy")
                self.assertTrue(selection.reason("shadow-without-bundle"))
                self.assertIsNone(selection.bundle_sha)
                self.assertEqual(selection.selected, BASELINE)

    def bundle_facts(self):
        return dp.runtime_facts(
            project=PROJECT, task_class=TASK_CLASS, intended_use=USE,
            components={"decision_contract": dc.CONTRACT_VERSION,
                        "task_contract": kc.CONTRACT_VERSION, "provider_contract": None})

    def test_a_shadow_over_a_live_bundle_says_so_and_still_selects_the_baseline(self):
        selection = dp.select_action(self.state(), self.result(), self.bundle(), mode="shadow")
        self.assertEqual(selection.mode, "shadow")
        self.assertTrue(selection.reason("mode-shadow"))
        self.assertFalse(selection.reason("legacy-default"))
        self.assertEqual(selection.selected, BASELINE)

    def test_an_activation_mode_is_refused_by_name_rather_than_treated_as_shadow(self):
        for mode in dp.DEFERRED_MODES:
            with self.subTest(mode=mode):
                error = self.refusal("unknown-value", dp.select_action, self.state(),
                                     self.result(), self.bundle(), mode=mode)
                self.assertIn(mode, str(error))
                self.assertIn("gated", str(error))

    def test_an_unknown_mode_word_is_refused_before_anything_else_is_looked_at(self):
        """Isolated by pairing it with a state that is ALSO invalid: without this guard the
        state's own refusal answers first and the mode word goes unnoticed, which is how the
        check below was found to be masked by the one in `ActionSelection` rather than real."""
        self.refusal("unknown-value", dp.select_action, self.state(), mode="enthusiastic")
        self.refusal("unknown-value", dp.select_action, ["not", "a", "state"],
                     mode="enthusiastic")

    # ---- C. confidence is not authority ------------------------------------------------------

    def test_the_admissibility_check_has_no_parameter_a_confidence_could_arrive_through(self):
        """The signature IS the guarantee: there is no expression inside this function that
        could weigh a number against a denial, because no number reaches it."""
        self.assertEqual(list(inspect.signature(dp._admissible).parameters), ["action", "facts"])

    def test_nothing_in_this_module_reads_an_answers_numbers(self):
        tree = ast.parse(POLICY_PATH.read_text(encoding="utf-8"))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                names.add(node.value)
        self.assertIn("baseline", names, "the walk reaches the code that matters")
        for forbidden in ("vendor_confidence", "calibrated", "raw", "answers", "probability"):
            with self.subTest(name=forbidden):
                self.assertNotIn(forbidden, names)

    def test_a_maximally_confident_recommendation_for_a_denied_action_is_refused_as_denied(self):
        """The security-relevant rule. Every number the contract can carry is at the top of its
        range and the answer still loses to the denial -- and loses NAMING the denial, so a
        report cannot record this as the advice having been weighed and found wanting."""
        state = self.state(denials={OTHER: "unavailable"})
        selection = dp.select_action(
            state, self.result(answers={"q-context-missing@v1": CERTAIN}), self.bundle(),
            mode="shadow")
        self.assertEqual(selection.recommended, OTHER)
        self.assertFalse(selection.recommendation["admissible"])
        self.assertEqual(selection.recommendation["reason"], "unavailable")
        self.assertTrue(selection.reason("advice-inadmissible"))
        self.assertEqual(selection.selected, BASELINE)
        self.assertEqual(self.rejected(selection)[OTHER], "unavailable")

    def test_the_same_maximally_confident_recommendation_for_an_open_action_is_admissible(self):
        """The positive control. Without it, every assertion above would also pass against an
        `_admissible` that refused everything."""
        selection = dp.select_action(
            self.state(), self.result(answers={"q-context-missing@v1": CERTAIN}),
            self.bundle(), mode="shadow")
        self.assertTrue(selection.recommendation["admissible"])
        self.assertIsNone(selection.recommendation["reason"])

    def test_an_unconfident_recommendation_for_an_open_action_is_equally_admissible(self):
        """The other half of the control: confidence is not consulted in EITHER direction."""
        low = answer(raw={"false": 0.5, "true": 0.5}, vendor_confidence=0.0)
        selection = dp.select_action(
            self.state(), self.result(answers={"q-context-missing@v1": low}), self.bundle(),
            mode="shadow")
        self.assertTrue(selection.recommendation["admissible"])

    def test_a_recommendation_naming_a_reserved_default_is_held_back(self):
        state = self.state(reserved=[OTHER])
        selection = dp.select_action(state, self.result(), self.bundle(), mode="shadow")
        self.assertFalse(selection.recommendation["admissible"])
        self.assertEqual(selection.recommendation["reason"], "reserved")
        self.assertEqual(selection.selected, BASELINE)

    def test_a_recommendation_naming_anything_but_the_explicit_pin_is_refused(self):
        state = self.state(pin=BASELINE)
        selection = dp.select_action(state, self.result(), self.bundle(), mode="shadow")
        self.assertFalse(selection.recommendation["admissible"])
        self.assertEqual(selection.recommendation["reason"], "pinned-elsewhere")
        self.assertEqual(selection.selected, BASELINE)

    def test_a_recommendation_that_names_the_pin_itself_is_admissible(self):
        """The pin's control: a pin refuses OTHER actions, not every action."""
        state = self.state(pin=BASELINE)
        selection = dp.select_action(state, self.result(recommended=BASELINE), self.bundle(),
                                     mode="shadow")
        self.assertTrue(selection.recommendation["admissible"])
        self.assertTrue(selection.reason("advice-matches-baseline"))

    # ---- D. stale advice is not weak advice --------------------------------------------------

    def test_a_result_correlated_to_another_call_is_not_advice_about_this_one(self):
        other = request(correlation_id="corr-2")
        selection = dp.select_action(self.state(), self.result(other), self.bundle(),
                                     mode="shadow")
        self.assertTrue(selection.reason("result-correlation-mismatch"))
        self.assertIsNone(selection.recommended)
        self.assertIsNone(selection.recommendation)
        self.assertEqual(selection.selected, BASELINE)

    def test_a_result_about_an_older_state_is_dropped_whole(self):
        older = request(state={"head": "9999ffff", "verify_rc": 0, "worktree_dirty": True})
        selection = dp.select_action(self.state(), self.result(older), self.bundle(),
                                     mode="shadow")
        self.assertTrue(selection.reason("result-state-stale"))
        self.assertFalse(selection.reason("result-correlation-mismatch"))
        self.assertIsNone(selection.recommended)

    def test_a_result_about_a_different_question_set_is_dropped_whole(self):
        reworded = request(questions=[question(version="v2")])
        selection = dp.select_action(self.state(), self.result(reworded), self.bundle(),
                                     mode="shadow")
        self.assertTrue(selection.reason("result-questions-stale"))
        self.assertFalse(selection.reason("result-state-stale"))
        self.assertIsNone(selection.recommended)

    def test_all_three_staleness_facts_are_reported_and_not_just_the_first(self):
        """Collected rather than short-circuited, so a test asserting one cannot be satisfied by
        a different check refusing the same input first."""
        far = request(correlation_id="corr-3", questions=[question(version="v2")],
                      state={"head": "9999ffff", "verify_rc": 0, "worktree_dirty": True})
        selection = dp.select_action(self.state(), self.result(far), self.bundle(),
                                     mode="shadow")
        for code in ("result-correlation-mismatch", "result-state-stale",
                     "result-questions-stale"):
            with self.subTest(code=code):
                self.assertTrue(selection.reason(code))

    def test_the_grant_that_paid_for_asking_does_not_pay_for_acting(self):
        """The same refusal the record contract makes, made BEFORE the action instead of after
        it: asking and acting are two operations and the first one's grant is already spent."""
        state = self.state(admission_ref=dict(self.request.admission_ref))
        selection = dp.select_action(state, self.result())
        self.assertTrue(selection.reason("action-admission-stale"))
        self.assertIsNone(selection.selected)
        self.assertIn("already spent", selection.refusal)

    def test_an_abstention_is_not_a_recommendation(self):
        """D12's rules provider ships an empty rule table and therefore abstains wholesale.
        Reading that as agreement with the baseline would turn "I have nothing to say" into a
        second vote for whatever was already happening."""
        abstained = self.result(status="abstain", recommended=None,
                                answers={"q-context-missing@v1":
                                         answer(outcome=None, abstained=True)})
        selection = dp.select_action(self.state(), abstained, self.bundle(), mode="shadow")
        self.assertTrue(selection.reason("result-abstained"))
        self.assertFalse(selection.reason("advice-matches-baseline"))
        self.assertIsNone(selection.recommendation)
        self.assertEqual(selection.selected, BASELINE)

    def test_a_terminal_result_carries_no_advice(self):
        for status in dc.TERMINAL_STATUSES:
            with self.subTest(status=status):
                terminal = self.result(status=status, recommended=None, answers={})
                selection = dp.select_action(self.state(), terminal, self.bundle(),
                                             mode="shadow")
                self.assertTrue(selection.reason("result-not-answering"))
                self.assertIsNone(selection.recommendation)
                self.assertEqual(selection.selected, BASELINE)

    def test_an_answering_result_that_recommends_nothing_is_not_a_recommendation(self):
        selection = dp.select_action(self.state(), self.result(recommended=None), self.bundle(),
                                     mode="shadow")
        self.assertTrue(selection.reason("recommendation-absent"))
        self.assertIsNone(selection.recommendation)

    def test_a_recommendation_that_was_never_an_alternative_is_refused(self):
        """Reachable with two genuinely parsed objects: correlation, state and question digests
        can all agree while the eligible alternatives differ, because the alternatives sit
        inside `request.sha()` and inside none of those three."""
        widened = request(alternatives=[BASELINE, "escalate-tier", STOP])
        advice = dc.parse_result(result_payload(widened, recommended="escalate-tier"), widened)
        self.assertEqual(advice.correlation_id, self.request.correlation_id)
        self.assertEqual(advice.state_sha, self.request.state_sha)
        selection = dp.select_action(self.state(), advice, self.bundle(), mode="shadow")
        self.assertTrue(selection.reason("recommendation-not-an-alternative"))
        self.assertIsNone(selection.recommendation)
        self.assertEqual(selection.selected, BASELINE)

    def test_a_payload_never_reaches_the_selection_without_being_parsed_first(self):
        """Raw provider data becomes a judgement only by surviving the contract's own parser. A
        selection that accepted a payload would be a second, weaker parser for the same bytes."""
        error = self.refusal("wrong-type", dp.select_action, self.state(),
                             result_payload(self.request))
        self.assertIn("parser", str(error))
        self.refusal("wrong-type", dp.select_action, self.state(), object())

    def test_a_result_from_another_contract_version_is_refused(self):
        stub = types.SimpleNamespace(
            to_payload=lambda: dict(result_payload(self.request), v="polytropos.decision/99"))
        self.refusal("unknown-value", dp.select_action, self.state(), stub)

    # ---- E. an unmade check is not a passed check --------------------------------------------

    def test_a_check_that_failed_refuses_the_whole_selection(self):
        for name in dp.COORDINATOR_CHECKS:
            with self.subTest(check=name):
                selection = dp.select_action(self.state(checks=self.checks(**{name: False})))
                self.assertTrue(selection.reason("check-failed"))
                self.assertIsNone(selection.selected)
                self.assertIsNotNone(selection.refusal)

    def test_a_check_nobody_made_is_not_a_check_that_passed(self):
        for name in dp.COORDINATOR_CHECKS:
            with self.subTest(check=name):
                selection = dp.select_action(self.state(checks=self.checks(**{name: None})))
                self.assertTrue(selection.reason("check-unestablished"))
                self.assertFalse(selection.reason("check-failed"))
                self.assertIsNone(selection.selected)

    def test_a_failed_check_and_an_unmade_one_are_both_reported(self):
        state = self.state(checks=self.checks(privacy=False, capability=None))
        selection = dp.select_action(state)
        self.assertTrue(selection.reason("check-failed"))
        self.assertTrue(selection.reason("check-unestablished"))

    def test_the_checks_are_closed_and_an_unmade_one_is_written_as_one(self):
        self.refusal("wrong-type", self.state, checks=["capability"])
        self.refusal("unknown-field", self.state, checks=dict(self.checks(), invented=True))
        partial = self.checks()
        del partial["privacy"]
        error = self.refusal("missing-field", self.state, checks=partial)
        self.assertIn("explicit null", str(error))
        self.refusal("wrong-type", self.state, checks=self.checks(privacy="yes"))
        self.refusal("wrong-type", self.state, checks=self.checks(privacy=1))

    # ---- F. the baseline, the pin, and the reserved default ----------------------------------

    def test_a_baseline_denied_since_the_routing_ran_refuses_rather_than_choosing_another(self):
        """A fresh recheck with teeth. Advice cannot route around a denial and neither may this
        module: there is no authority here to pick a different action, so it stops."""
        for reason in dp.denial_reasons():
            if reason in ("reserved", "pinned-elsewhere"):
                continue
            with self.subTest(denial=reason):
                selection = dp.select_action(self.state(denials={BASELINE: reason}))
                self.assertTrue(selection.reason("baseline-refused"))
                self.assertIsNone(selection.selected)
                self.assertEqual(self.rejected(selection)[BASELINE], reason)

    def test_a_baseline_that_is_not_the_explicit_pin_refuses_and_is_named_an_override(self):
        """Named on its own rather than folded into the generic refusal, so the one case that
        means "somebody overrode an explicit pin" stays countable."""
        selection = dp.select_action(self.state(pin=OTHER))
        self.assertTrue(selection.reason("pin-overridden"))
        self.assertFalse(selection.reason("baseline-refused"))
        self.assertIsNone(selection.selected)
        self.assertIn("explicit pin", selection.refusal)

    def test_a_pin_the_routing_honoured_selects_normally(self):
        """The pin's positive control: honouring a pin is not a refusal."""
        selection = dp.select_action(self.state(pin=BASELINE))
        self.assertEqual(selection.selected, BASELINE)
        self.assertIsNone(selection.refusal)

    def test_a_pin_that_survived_no_filter_at_all_still_refuses_rather_than_substituting(self):
        """A pin naming something that is not even an eligible alternative is expressible on
        purpose: it is what a filtered-out pin looks like, and the answer is to stop."""
        selection = dp.select_action(self.state(pin="a-model-nothing-offered"))
        self.assertTrue(selection.reason("pin-overridden"))
        self.assertIsNone(selection.selected)

    def test_a_routing_that_selected_nothing_refuses(self):
        selection = dp.select_action(self.state(baseline=None))
        self.assertTrue(selection.reason("baseline-absent"))
        self.assertIsNone(selection.selected)
        self.assertIsNone(selection.baseline)

    def test_the_baseline_may_be_the_reserved_model_when_nothing_holds_it_back(self):
        """The Codex recovery path deliberately dispatches to the reserved orchestrator. Holding
        a model back is a fact the coordinator states, not something this module assumes."""
        selection = dp.select_action(self.state(baseline=OTHER, reserved=[STOP]))
        self.assertEqual(selection.selected, OTHER)
        self.assertEqual(self.rejected(selection)[STOP], "reserved")

    def test_a_baseline_the_coordinator_also_held_back_is_a_contradiction_it_refuses_to_read(self):
        error = self.refusal("value-invalid", self.state, baseline=BASELINE,
                             reserved=[BASELINE])
        self.assertIn("disagree", str(error))

    def test_every_refusal_that_can_co_occur_is_reported_and_not_just_the_first(self):
        state = self.state(baseline=None, checks=self.checks(privacy=False),
                           admission_ref=dict(self.request.admission_ref))
        selection = dp.select_action(state)
        for code in ("baseline-absent", "check-failed", "action-admission-stale"):
            with self.subTest(code=code):
                self.assertTrue(selection.reason(code))

    # ---- G. every alternative that was not selected, and why ---------------------------------

    def test_every_alternative_that_was_not_selected_is_listed_with_why(self):
        state = self.state(denials={OTHER: "over-budget"}, reserved=[STOP])
        selection = dp.select_action(state)
        self.assertEqual(self.rejected(selection), {OTHER: "over-budget", STOP: "reserved"})
        self.assertNotIn(BASELINE, self.rejected(selection))

    def test_an_alternative_nothing_denied_is_rejected_for_simply_not_being_the_one(self):
        selection = dp.select_action(self.state())
        self.assertEqual(self.rejected(selection),
                         {OTHER: "not-selected", STOP: "not-selected"})

    def test_a_refused_selection_lists_every_alternative_including_the_baseline(self):
        selection = dp.select_action(self.state(checks=self.checks(privacy=False)))
        self.assertIsNone(selection.selected)
        self.assertEqual(sorted(self.rejected(selection)), sorted(ALTERNATIVES))

    # ---- H. the selection object's own guards -------------------------------------------------

    def built(self, **over):
        payload = {"mode": "legacy", "requested_mode": "legacy", "baseline": BASELINE,
                   "recommended": None, "recommendation": None, "selected": BASELINE,
                   "refusal": None, "bundle_sha": None, "reasons": ("legacy-default",),
                   "rejected": ()}
        payload.update(over)
        return dp.ActionSelection(**payload)

    def test_the_positive_control_for_every_guard_below_builds(self):
        """Without this, every `assertRaises` below would also pass against a constructor that
        refused everything it was given."""
        selection = self.built()
        self.assertEqual(selection.selected, BASELINE)

    def test_a_mode_outside_the_two_this_module_implements_cannot_be_built(self):
        for field in ("mode", "requested_mode"):
            for word in dp.DEFERRED_MODES + ("invented",):
                with self.subTest(field=field, mode=word):
                    self.refusal("unknown-value", self.built, **{field: word})

    def test_an_undeclared_or_repeated_reason_cannot_be_built(self):
        self.refusal("unknown-value", self.built, reasons=("promoted",))
        # D11's codes are a DIFFERENT vocabulary and are undeclared here on purpose.
        self.refusal("unknown-value", self.built, reasons=("selected",))
        self.refusal("duplicate-entry", self.built,
                     reasons=("legacy-default", "legacy-default"))

    def test_a_selection_carries_no_more_reasons_than_a_record_can_hold(self):
        self.refusal("bounds-exceeded", self.built, reasons=())
        too_many = dp.SELECTION_REASONS[:dc.MAX_REASON_CODES + 1]
        self.assertGreater(len(too_many), dc.MAX_REASON_CODES)
        self.refusal("bounds-exceeded", self.built, reasons=too_many, selected=None,
                     refusal="because")

    def test_a_selection_names_an_action_exactly_when_nothing_refused_it(self):
        self.refusal("value-invalid", self.built, selected=None, refusal=None,
                     reasons=("legacy-default", "baseline-absent"))
        self.refusal("value-invalid", self.built, selected=BASELINE, refusal="because")

    def test_a_selection_refuses_exactly_when_it_carries_a_declared_refusal_reason(self):
        """Without this a selection could refuse for a cause nobody can count -- the same defect
        as an undeclared reason code, with extra steps."""
        self.refusal("value-invalid", self.built, selected=None, refusal="because",
                     reasons=("legacy-default",))
        self.refusal("value-invalid", self.built, selected=BASELINE, refusal=None,
                     reasons=("legacy-default", "baseline-refused"))

    def test_a_shadow_selection_without_a_bundle_digest_cannot_be_built(self):
        self.refusal("value-invalid", self.built, mode="shadow", requested_mode="shadow",
                     reasons=("mode-shadow",), bundle_sha=None)
        self.built(mode="shadow", requested_mode="shadow", reasons=("mode-shadow",),
                   bundle_sha="a" * 64)

    def test_a_selection_may_not_reject_its_own_selected_action_or_reject_one_twice(self):
        entry = {"action": BASELINE, "reason": "not-selected"}
        self.refusal("value-invalid", self.built, rejected=(entry,))
        twice = ({"action": OTHER, "reason": "not-selected"},
                 {"action": OTHER, "reason": "excluded"})
        self.refusal("duplicate-entry", self.built, rejected=twice)
        self.refusal("unknown-value", self.built,
                     rejected=({"action": OTHER, "reason": "ranked-lower"},))

    def test_a_selection_carries_no_grant_and_nothing_that_could_be_run(self):
        selection = dp.select_action(self.state(), self.result(), self.bundle(), mode="shadow")
        for absent in ("approve", "approved", "grant", "permission", "budget", "activate",
                       "argv", "command"):
            with self.subTest(attribute=absent):
                self.assertFalse(hasattr(selection, absent))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            selection.selected = OTHER
        with self.assertRaises(TypeError):
            selection.recommendation["admissible"] = True

    # ---- I. the state contract ----------------------------------------------------------------

    def test_the_selection_state_is_closed_and_an_unestablished_fact_is_written_as_one(self):
        base = self.state()
        self.assertEqual(sorted(base), sorted(dp.SELECTION_KEYS))
        self.refusal("wrong-type", dp.select_action, ["not", "a", "state"])
        self.refusal("unknown-field", dp.select_action, dict(base, invented=True))
        for key in dp.SELECTION_KEYS:
            with self.subTest(missing=key):
                short = dict(base)
                del short[key]
                self.refusal("missing-field", dp.select_action, short)

    def test_the_alternatives_come_from_the_request_and_never_from_a_second_list(self):
        """So a selection cannot name an action that was not on the table when the question was
        asked, and the record contract's own check on the same field agrees by construction."""
        self.refusal("unknown-action", self.state, baseline="a-model-nobody-offered")
        self.refusal("unknown-action", self.state, reserved=["a-model-nobody-offered"])
        self.refusal("unknown-action", self.state,
                     denials={"a-model-nobody-offered": "unavailable"})

    def test_a_request_with_no_eligible_alternative_leaves_nothing_to_select_among(self):
        with mock.patch.object(type(self.request), "to_payload",
                               lambda self_: dict(request_payload(), alternatives=[])):
            self.refusal("value-invalid", self.state, baseline=None)

    def test_an_action_is_held_back_or_denied_and_never_both(self):
        """Two different facts with two different remedies. An action carrying both would let
        whichever check ran first mask the other one permanently."""
        error = self.refusal("duplicate-entry", self.state, baseline=BASELINE,
                             reserved=[OTHER], denials={OTHER: "unavailable"})
        self.assertIn(OTHER, str(error))

    def test_a_denial_reason_outside_the_routers_vocabulary_is_refused(self):
        self.refusal("unknown-value", self.state, denials={OTHER: "i-just-did-not-fancy-it"})
        self.refusal("unknown-value", self.state, denials={OTHER: "ranked-lower"})
        self.refusal("wrong-type", self.state, denials=[OTHER])

    def test_acting_without_a_fresh_grant_is_not_expressible(self):
        """There is no null here that means "acting anyway"."""
        for bad in (None, "grant-act-1", {"sha": "a" * 64}, 7):
            with self.subTest(grant=bad):
                self.refusal("not-a-reference", self.state, admission_ref=bad)

    def test_a_pin_is_an_action_name_or_no_pin_at_all(self):
        self.refusal("value-invalid", self.state, pin="")
        self.refusal("value-invalid", self.state, pin=7)

    def test_reserved_defaults_are_a_list(self):
        self.refusal("wrong-type", self.state, reserved=BASELINE)

    def test_a_request_that_was_never_parsed_is_not_a_request(self):
        self.refusal("wrong-type", self.state, request=request_payload())
        self.refusal("wrong-type", self.state, request=object())
        self.refusal("wrong-type", self.state,
                     request=types.SimpleNamespace(to_payload=lambda: "not a payload"))
        self.refusal("unknown-value", self.state, request=types.SimpleNamespace(
            to_payload=lambda: dict(request_payload(), v="polytropos.decision/99")))

    def test_selection_is_payload_shaped_so_a_second_loader_cannot_break_it(self):
        """`bin/` is not a package: two loaders of one file produce two class objects, and an
        `isinstance` across that boundary is false. This kit has already been bitten by it."""
        other = _load("decision_contract")
        self.assertIsNot(other.DecisionRequest, dc.DecisionRequest)
        foreign_request = other.parse_request(request_payload())
        foreign_result = other.parse_result(result_payload(foreign_request), foreign_request)
        selection = dp.select_action(self.state(request=foreign_request), foreign_result)
        self.assertEqual(selection.selected, BASELINE)
        self.assertEqual(selection.recommended, OTHER)

    # ---- J. the two seams this repository actually has -----------------------------------------

    def seam(self, decision=None, **over):
        payload = routing_decision(**(decision or {}))
        kwargs = {"request": self.request, "checks": self.checks(),
                  "admission_ref": self.grant}
        kwargs.update(over)
        return dp.state_from_routing(payload, **kwargs)

    def test_a_routing_decision_becomes_a_state_without_the_router_being_re_run(self):
        """Read as data. No rule here rederives the router's own decision, because a second
        implementation that disagreed would be worse than none at all."""
        selection = dp.select_action(self.seam())
        self.assertEqual(selection.selected, BASELINE)
        self.assertEqual(self.rejected(selection),
                         {OTHER: "not-selected", STOP: "not-selected"})

    def test_the_reserved_orchestrator_hold_back_survives_the_routing_seam(self):
        state = self.seam({"candidates": [routing_candidate(BASELINE),
                                          routing_candidate(OTHER, ["reserved"]),
                                          routing_candidate(STOP)]})
        self.assertEqual(state["reserved"], [OTHER])
        self.assertEqual(state["denials"], {})
        selection = dp.select_action(state, self.result(), self.bundle(), mode="shadow")
        self.assertEqual(selection.recommendation["reason"], "reserved")
        self.assertEqual(selection.selected, BASELINE)

    def test_an_explicit_pin_survives_the_routing_seam(self):
        state = self.seam({"floor": {"tier": "fake-tier", "rank": 0, "basis": [],
                                     "pinned": BASELINE, "migrated": None},
                           "candidates": [routing_candidate(BASELINE),
                                          routing_candidate(OTHER, ["pinned-elsewhere"]),
                                          routing_candidate(STOP, ["pinned-elsewhere"])]})
        self.assertEqual(state["pin"], BASELINE)
        selection = dp.select_action(state, self.result(), self.bundle(), mode="shadow")
        self.assertEqual(selection.selected, BASELINE)
        self.assertFalse(selection.recommendation["admissible"])

    def test_a_routing_that_refused_carries_no_baseline_through_the_seam(self):
        state = self.seam({"model": None, "refusal": "no eligible model at or above tier x"})
        selection = dp.select_action(state)
        self.assertTrue(selection.reason("baseline-absent"))
        self.assertIsNone(selection.selected)

    def test_a_ranking_is_not_a_denial_at_the_routing_seam(self):
        """`ranked-lower` is the one filter advice is allowed to have an opinion about."""
        state = self.seam({"candidates": [routing_candidate(BASELINE),
                                          routing_candidate(OTHER, ["ranked-lower"]),
                                          routing_candidate(STOP, ["ranked-lower"])]})
        self.assertEqual(state["denials"], {})
        selection = dp.select_action(state, self.result(), self.bundle(), mode="shadow")
        self.assertTrue(selection.recommendation["admissible"])

    def test_a_hard_filter_becomes_a_denial_at_the_routing_seam(self):
        for reason in dp.denial_reasons():
            if reason == "reserved":
                continue
            with self.subTest(filter=reason):
                state = self.seam({"candidates": [routing_candidate(BASELINE),
                                                  routing_candidate(OTHER, [reason]),
                                                  routing_candidate(STOP)]})
                self.assertEqual(state["denials"], {OTHER: reason})

    def test_a_catalog_row_that_was_never_an_eligible_alternative_is_skipped(self):
        """The router's catalog names rows that were never on the table -- non-routable models,
        cost-only entries -- precisely so an explanation can name them."""
        state = self.seam({"candidates": [routing_candidate(BASELINE),
                                          routing_candidate("fake-cost-only",
                                                            ["not-routable"])]})
        self.assertEqual(state["denials"], {})
        self.assertEqual(dp.select_action(state).selected, BASELINE)

    def test_a_payload_that_is_not_a_routing_decision_is_refused(self):
        error = self.refusal("unknown-value", dp.state_from_routing,
                             dict(routing_decision(), v="polytropos.routing/99"),
                             request=self.request, checks=self.checks(),
                             admission_ref=self.grant)
        self.assertIn(rp.CONTRACT_VERSION, str(error))
        self.refusal("wrong-type", dp.state_from_routing, ["not", "a", "decision"],
                     request=self.request, checks=self.checks(), admission_ref=self.grant)
        self.refusal("wrong-type", dp.state_from_routing,
                     dict(routing_decision(), candidates=["not-an-object"]),
                     request=self.request, checks=self.checks(), admission_ref=self.grant)

    def test_the_seam_reads_the_routers_own_contract_version_rather_than_a_copy(self):
        payload = routing_decision()
        self.assertEqual(payload["v"], rp.CONTRACT_VERSION)
        # Built BEFORE the patch on purpose: built inside it, the fixture would pick the new
        # version up too and the test would prove nothing.
        with mock.patch.object(rp, "CONTRACT_VERSION", "polytropos.routing/2"):
            self.refusal("unknown-value", dp.state_from_routing, payload,
                         request=self.request, checks=self.checks(),
                         admission_ref=self.grant)

    def test_a_driver_with_a_tier_ladder_reaches_the_same_state(self):
        state = dp.state_from_ladder(request=self.request, baseline=BASELINE,
                                     ladder=[OTHER, STOP], checks=self.checks(),
                                     admission_ref=self.grant)
        selection = dp.select_action(state)
        self.assertEqual(selection.selected, BASELINE)
        self.assertEqual(sorted(self.rejected(selection)), sorted([OTHER, STOP]))

    def test_a_driver_with_no_ladder_at_all_is_this_seam_with_an_empty_one(self):
        """Cursor's case. One attempt, no rungs, and the selection is the same shape."""
        state = dp.state_from_ladder(request=self.request, baseline=BASELINE, ladder=[],
                                     checks=self.checks(), admission_ref=self.grant)
        self.assertEqual(dp.select_action(state).selected, BASELINE)

    def test_a_ladder_rung_that_was_never_an_alternative_is_refused_at_the_seam(self):
        """The whole point of having this seam: a rung that was not on the table would
        otherwise enter the decision unnoticed."""
        error = self.refusal("unknown-action", dp.state_from_ladder, request=self.request,
                             baseline=BASELINE, ladder=[OTHER, "fake-frontier"],
                             checks=self.checks(), admission_ref=self.grant)
        self.assertIn("fake-frontier", str(error))
        self.refusal("wrong-type", dp.state_from_ladder, request=self.request,
                     baseline=BASELINE, ladder=OTHER, checks=self.checks(),
                     admission_ref=self.grant)

    def test_a_baseline_that_is_also_a_rung_above_itself_is_refused(self):
        self.refusal("duplicate-entry", dp.state_from_ladder, request=self.request,
                     baseline=BASELINE, ladder=[BASELINE, OTHER], checks=self.checks(),
                     admission_ref=self.grant)

    # ---- K. purity, and what nothing calls ----------------------------------------------------

    def test_a_bundle_resolution_is_the_only_bundle_shape_this_takes(self):
        self.refusal("wrong-type", dp.select_action, self.state(), None, "a-bundle-id")
        # Given a bundle AND a digest on purpose: without them the missing-digest guard below
        # refuses first, and the source vocabulary goes unchecked -- which is exactly what a
        # weaker fixture hid here. A resolution claiming an activation this module does not
        # implement must not read as a bundle in force.
        self.refusal("wrong-type", dp.select_action, self.state(), None,
                     types.SimpleNamespace(source="active", bundle=types.SimpleNamespace(
                         sha=lambda: "b" * 64)))
        self.refusal("wrong-type", dp.select_action, self.state(), None,
                     types.SimpleNamespace(source="active"))
        self.refusal("wrong-type", dp.select_action, self.state(), None,
                     types.SimpleNamespace(source="pinned", bundle=None))

    def test_a_legacy_resolution_reads_exactly_like_no_bundle_at_all(self):
        legacy = dp.resolve_bundle(None, [], self.bundle_facts())
        self.assertEqual(legacy.source, "legacy")
        selection = dp.select_action(self.state(), None, legacy)
        self.assertIsNone(selection.bundle_sha)
        self.assertEqual(selection.mode, "legacy")

    def test_nothing_in_this_repository_calls_the_selection_or_either_seam(self):
        """A green suite says these functions work, never that anything invokes them. The chain
        to a runtime is a later, separately gated task, and three of the four native drivers are
        frozen by their own goldens against even naming the router. When this list stops being
        empty, that is the signal to check the wiring rather than a failure."""
        callers = []
        for path in sorted(BIN_DIR.glob("*.py")):
            if path.name == "decision_policy.py":
                continue
            text = path.read_text(encoding="utf-8")
            for name in ("select_action", "state_from_routing", "state_from_ladder",
                         "selection_state"):
                if name in text:
                    callers.append(f"{path.name}:{name}")
        self.assertEqual(callers, [])

    def test_the_selection_reaches_for_no_private_name_of_the_router(self):
        """This module loads the router for its VOCABULARY. It never calls `decide`, never
        builds a catalog and never routes -- a second router would be a second authority."""
        tree = ast.parse(POLICY_PATH.read_text(encoding="utf-8"))
        reached = set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name)
                    and node.value.func.id == "_rp"):
                reached.add(node.attr)
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                    and node.value.id == "router"):
                reached.add(node.attr)
        self.assertTrue(reached, "the walk found no router access at all")
        self.assertEqual(sorted(reached), ["CONTRACT_VERSION", "FILTERS"])

    def test_the_selection_half_of_this_module_opens_nothing_and_starts_nothing(self):
        text = POLICY_PATH.read_text(encoding="utf-8")
        tree = ast.parse(text)
        calls = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Attribute):
                    calls.add(fn.attr)
                elif isinstance(fn, ast.Name):
                    calls.add(fn.id)
        self.assertIn("select_action", {node.name for node in ast.walk(tree)
                                        if isinstance(node, ast.FunctionDef)})
        self.assertTrue(calls, "the AST walk found no calls, so the sweep below is vacuous")
        self.assertIn("_admissible", calls, "the walk reaches the code that matters")
        for writer in ("open", "write_text", "write_bytes", "mkdir", "unlink", "rename",
                       "system", "run", "Popen", "urlopen", "connect"):
            with self.subTest(call=writer):
                self.assertNotIn(writer, calls)


if __name__ == "__main__":
    unittest.main()
