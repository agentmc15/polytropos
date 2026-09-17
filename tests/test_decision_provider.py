"""D12 -- rules and replay, the two providers that answer a `DecisionRequest` through the one
`decision_provider.evaluate` interface, and the D09 validator both of them are checked against.

`RulesReplayProviderTests` covers `bin/decision_provider.py`:

  * RULES is a deterministic, local computation over the request's own `state`, driven by a
    caller-supplied rule table (`DEFAULT_RULES` ships empty, on purpose -- see the module
    docstring). It abstains per question where the question's own spec permits abstention, and
    for the WHOLE result where it cannot decide a question that forbids one.
  * REPLAY is a lookup into a caller-selected, content-addressed store. A cache hit reuses a
    prior answer without dispatching anything; a miss abstains; a cross-project request misses
    structurally, because project is part of `DecisionRequest.sha()` and so part of the key. A
    replayed payload is never mistaken for a fresh one: `dispatched_provider`,
    `observed_provider`, `dispatched_model`, `observed_model`, `duration` and `usage` are all
    forced to `None`, and `note` carries the stable `REPLAY_NOTE_PREFIX`.
  * "Historical cost remains on its original record" is enforced by construction:
    `record_result` is create-once, mirroring `workflow_eval.write_manifest`'s own precedent --
    the same identity recorded twice with the same content is a no-op; with different content it
    is refused, and nothing is overwritten either way.
  * Both implementations are reached through `evaluate`, and both of their outputs are run
    through `decision_contract.parse_result(payload, request)` in this file -- the D09 validator
    both providers are tested through, exactly as the brief requires.
  * `runner` is accepted by the interface and never invoked by either implementation. Proved two
    ways, deliberately paired: at runtime, by injecting a runner that RAISES the instant it is
    called and asserting it was never touched; structurally, by walking `_evaluate_replay`'s own
    AST and asserting that among its (non-empty) set of calls, none names `runner`.

============================================================================================
 SAFETY CONTRACT
============================================================================================
Nothing here invokes a real `claude`/`codex`/`copilot`/`cursor`/`graphify` binary, reads a real
`~/.claude`/`~/.codex`/`~/.copilot` home, starts a process or touches the network. The one I/O
this module performs -- the replay store -- is exercised here only through
`tempfile.TemporaryDirectory()`, created and destroyed by each test.

ONE LOADER, ON PURPOSE. `bin/` is not a package, so each module here is loaded by path and two
loaders of the same file produce two distinct sets of classes -- `decision_policy`'s own tests
already document being bitten by this. This file therefore reads `decision_contract` through
`decision_provider`'s OWN sibling loader (`dp._contract()`), never a second, independently
loaded copy, so a `DecisionRequest`/`DecisionResult` built here is `isinstance`-compatible with
what the module under test checks it against.
"""

import ast
import importlib.util
import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "bin"
MODULE_PATH = BIN_DIR / "decision_provider.py"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dp = _load("decision_provider")
dc = dp._contract()          # the SAME contract instance the module under test uses
al = dp._al()
kc = _load("kit_contract")
rg = _load("release_gate")

QUESTION_TEXT = ("Did the failing attempt lack the interface contract of the module it "
                 "called across the boundary?")
ORDINAL_TEXT = ("How much of the failing behaviour does the supplied contract context "
                "actually explain?")

PROJECT = "polytropos"
STATE = {"head": "0123abcd", "verify_rc": 1, "worktree_dirty": False, "last_failure": "assert"}
ALTERNATIVES = ["retry-same-model", "retry-with-contract-context", "stop"]


def question(**over):
    payload = {
        "id": "q-context-missing", "version": "v1", "kind": "boolean",
        "question": QUESTION_TEXT, "rubric": {}, "outcomes": ["false", "true"],
        "abstention": "permitted", "dependencies": [], "sensitivity": "project-internal",
    }
    payload.update(over)
    return payload


def forbidden_question(**over):
    payload = question(id="q-must-answer", abstention="forbidden")
    payload.update(over)
    return payload


def ordinal_question(**over):
    payload = {
        "id": "q-explains", "version": "v1", "kind": "ordinal", "question": ORDINAL_TEXT,
        "rubric": {
            "none": "no part of the observed failure follows from the supplied context",
            "some": "at least one failing assertion follows from the supplied context",
            "all": "every failing assertion follows from the supplied context",
        },
        "outcomes": ["none", "some", "all"], "abstention": "forbidden", "dependencies": [],
        "sensitivity": "project-internal",
    }
    payload.update(over)
    return payload


def _specs(question_payloads):
    return [dc.parse_question(q, f"q[{i}]") for i, q in enumerate(question_payloads)]


_UNSET = object()


def request_payload(questions=None, state=None, **over):
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
        "task": "D12",
        "attempt": None,
        "intended_use": "recovery-selection",
        "task_ref": al.make_ref("D12", version=kc.CONTRACT_VERSION),
        "acceptance_ref": al.make_ref("acc-1", sha="a" * 64, version=kc.CONTRACT_VERSION),
        "state": state,
        "state_sha": state_sha,
        "alternatives": list(ALTERNATIVES),
        "questions": questions,
        "questions_sha": questions_sha,
        "eligibility": {"project": PROJECT, "providers": ["rules", "replay"],
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


class _RaisingRunner:
    """A runner that RAISES if ever invoked -- a canned return value is too weak a witness that
    a call was never made. Mirrors `test_decision_experiment_boundary.py`'s own `_RaisingRunner`
    exactly, so both proofs read the same way across the kit."""

    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError(f"provider runner reached: args={args!r} kwargs={kwargs!r}")


class RulesReplayProviderTests(unittest.TestCase):

    maxDiff = None

    # ---- fixtures -----------------------------------------------------------------------------

    def result_for(self, req, **over):
        """A hand-built, ALREADY VALID `DecisionResult` -- the shape a live vendor would have
        returned -- used as the thing `record_result` persists in the replay tests below."""
        answers = {spec.qualified_id: {"outcome": "true", "abstained": False, "raw": None,
                                       "calibrated": None, "vendor_confidence": None}
                  for spec in req.questions}
        payload = {
            "v": dc.CONTRACT_VERSION, "correlation_id": req.correlation_id,
            "state_sha": req.state_sha, "questions_sha": req.questions_sha,
            "status": "ok", "answers": answers, "recommended": "stop", "evidence_refs": [],
            "requested_provider": "rules", "dispatched_provider": "rules",
            "observed_provider": None, "requested_model": None, "dispatched_model": None,
            "observed_model": None, "provider_contract_v": None,
            "duration": {"basis": "decision-latency", "seconds": 0.01, "source": "rules"},
            "usage": None, "note": None,
        }
        payload.update(over)
        return dc.parse_result(payload, req)

    def refusal(self, code, callable_, *args, **kwargs):
        with self.assertRaises(dc.ContractError) as caught:
            callable_(*args, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        return caught.exception

    # ---- the one interface, and the D09 validator both implementations run through -----------

    def test_an_unknown_mode_is_refused_and_dispatches_nothing(self):
        req = request()
        self.refusal("unknown-value", dp.evaluate, req, mode="live", provider="rules")

    def test_replay_without_a_store_dir_is_refused_rather_than_silently_local(self):
        req = request()
        self.refusal("missing-field", dp.evaluate, req, mode="replay", provider="rules")

    def test_a_raw_payload_is_not_accepted_in_place_of_the_parsed_request(self):
        payload = request_payload()
        self.refusal("wrong-type", dp.evaluate, payload, mode="rules", provider="rules")
        self.refusal("wrong-type", dp._evaluate_rules, payload, provider="rules")
        with tempfile.TemporaryDirectory() as tmp:
            self.refusal("wrong-type", dp._evaluate_replay, payload, tmp, provider="rules")

    def test_a_provider_the_request_never_named_eligible_is_refused_by_both_modes(self):
        req = request()
        self.refusal("unknown-value", dp.evaluate, req, mode="rules", provider="gpt-x")
        with tempfile.TemporaryDirectory() as tmp:
            self.refusal("unknown-value", dp.evaluate, req, mode="replay", provider="gpt-x",
                         store_dir=tmp)

    # ---- rules: abstains where it must -------------------------------------------------------

    def test_the_default_rule_table_is_empty_and_the_provider_abstains_wholesale(self):
        req = request()
        payload = dp.evaluate(req, mode="rules", provider="rules")
        self.assertEqual(payload["status"], "abstain")
        self.assertEqual(payload["answers"], {})
        self.assertIsNone(payload["recommended"])
        self.assertEqual(payload["note"], dp.RULES_ABSTAIN_EMPTY_NOTE)
        result = dc.parse_result(payload, req)
        self.assertEqual(result.status, "abstain")

    def test_a_rule_that_decides_every_question_produces_an_ok_result_through_the_validator(self):
        req = request(questions=[question()])

        def decide(state, spec):
            return "true" if state.get("worktree_dirty") is False else "false"

        payload = dp.evaluate(req, mode="rules", provider="rules",
                              rules={"q-context-missing@v1": decide})
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["answers"]["q-context-missing@v1"]["outcome"], "true")
        self.assertIsNone(payload["recommended"], "a rules provider selects nothing; D13 does")
        result = dc.parse_result(payload, req)
        self.assertEqual(result.answers["q-context-missing@v1"]["outcome"], "true")
        self.assertEqual(payload["duration"]["basis"], "decision-latency")
        self.assertEqual(payload["duration"]["source"], "rules")
        self.assertGreaterEqual(payload["duration"]["seconds"], 0.0)

    def test_a_permitted_question_the_rule_cannot_decide_is_answered_ok_with_that_one_abstained(self):
        # Both questions here permit abstention, so a MIX of decided and individually-abstained
        # answers is a legal 'ok' -- distinct from the whole-result abstention the next test
        # proves for a FORBIDDEN gap.
        req = request(questions=[question(), question(id="q-side")])

        def decide_first(state, spec):
            return "true" if spec.id == "q-context-missing" else None

        payload = dp.evaluate(req, mode="rules", provider="rules",
                              rules={"q-context-missing@v1": decide_first})
        self.assertEqual(payload["status"], "ok")
        self.assertFalse(payload["answers"]["q-context-missing@v1"]["abstained"])
        self.assertTrue(payload["answers"]["q-side@v1"]["abstained"])
        self.assertIsNone(payload["answers"]["q-side@v1"]["outcome"])
        dc.parse_result(payload, req)

    def test_a_forbidden_question_the_rule_cannot_decide_abstains_the_whole_result(self):
        req = request(questions=[question(), forbidden_question()])

        def decide_first(state, spec):
            return "true" if spec.id == "q-context-missing" else None

        payload = dp.evaluate(req, mode="rules", provider="rules",
                              rules={"q-context-missing@v1": decide_first})
        self.assertEqual(payload["status"], "abstain")
        self.assertEqual(payload["answers"], {})
        self.assertEqual(payload["note"], dp.RULES_ABSTAIN_BLOCKED_NOTE)
        dc.parse_result(payload, req)

    def test_a_rule_that_invents_a_category_is_refused_not_passed_through(self):
        req = request()

        def bad_rule(state, spec):
            return "maybe"

        self.refusal("unknown-value", dp.evaluate, req, mode="rules", provider="rules",
                     rules={"q-context-missing@v1": bad_rule})

    def test_a_malformed_rule_table_is_refused(self):
        req = request()
        self.refusal("wrong-type", dp.evaluate, req, mode="rules", provider="rules",
                     rules={"q-context-missing@v1": "not-callable"})
        self.refusal("wrong-type", dp.evaluate, req, mode="rules", provider="rules",
                     rules=["not", "a", "mapping"])

    def test_rules_never_touches_the_runner(self):
        runner = _RaisingRunner()
        req = request()
        payload = dp.evaluate(req, mode="rules", provider="rules", runner=runner)
        self.assertEqual(payload["status"], "abstain")
        self.assertEqual(runner.calls, [])

    # ---- replay: makes no call ----------------------------------------------------------------

    def test_a_cache_miss_abstains_and_never_reaches_the_runner(self):
        runner = _RaisingRunner()
        req = request()
        with tempfile.TemporaryDirectory() as tmp:
            payload = dp.evaluate(req, mode="replay", provider="rules", store_dir=tmp,
                                  runner=runner)
        self.assertEqual(payload["status"], "abstain")
        self.assertEqual(payload["note"], dp.REPLAY_MISS_NOTE)
        self.assertEqual(runner.calls, [], "replay makes no call, even on a miss")
        dc.parse_result(payload, req)

    def test_a_replayed_hit_reuses_the_answer_and_marks_itself_not_a_fresh_observation(self):
        runner = _RaisingRunner()
        req = request()
        result = self.result_for(req)
        with tempfile.TemporaryDirectory() as tmp:
            dp.record_result(tmp, req, result, provider="rules")
            payload = dp.evaluate(req, mode="replay", provider="rules", store_dir=tmp,
                                  runner=runner)
        self.assertEqual(runner.calls, [], "replay makes no call on a hit either")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["answers"], result.to_payload()["answers"])
        self.assertEqual(payload["recommended"], "stop")
        self.assertEqual(payload["requested_provider"], "rules")
        # Not a fresh vendor observation, by construction:
        self.assertIsNone(payload["dispatched_provider"])
        self.assertIsNone(payload["observed_provider"])
        self.assertIsNone(payload["dispatched_model"])
        self.assertIsNone(payload["observed_model"])
        self.assertIsNone(payload["duration"], "a replay took no fresh time; unknown, not zero")
        self.assertIsNone(payload["usage"], "a replay spent no fresh dollars; unknown, not zero")
        self.assertTrue(payload["note"].startswith(dp.REPLAY_NOTE_PREFIX))
        self.assertIn(repr(req.correlation_id), payload["note"])
        parsed = dc.parse_result(payload, req)
        self.assertEqual(parsed.correlation_id, req.correlation_id)

    def test_a_cross_project_request_misses_even_with_every_other_field_identical(self):
        req = request()
        other = request(eligibility={"project": "some-other-project",
                                     "providers": ["rules", "replay"],
                                     "privacy": "project-local"},
                        correlation_id="corr-2")
        result = self.result_for(req)
        with tempfile.TemporaryDirectory() as tmp:
            dp.record_result(tmp, req, result, provider="rules")
            payload = dp.evaluate(other, mode="replay", provider="rules", store_dir=tmp)
        self.assertEqual(payload["status"], "abstain")
        self.assertEqual(payload["note"], dp.REPLAY_MISS_NOTE)

    def test_a_different_provider_or_model_is_a_different_identity(self):
        req = request()
        result = self.result_for(req)
        with tempfile.TemporaryDirectory() as tmp:
            dp.record_result(tmp, req, result, provider="rules", model=None)
            miss_by_model = dp.evaluate(req, mode="replay", provider="rules", store_dir=tmp,
                                        model="some-model")
            self.assertEqual(miss_by_model["status"], "abstain")
            miss_by_bundle = dp.evaluate(req, mode="replay", provider="rules", store_dir=tmp,
                                         bundle_sha="a" * 64)
            self.assertEqual(miss_by_bundle["status"], "abstain")

    # ---- record_result: create-once, one owner of its own history ----------------------------

    def test_recording_the_same_identity_twice_with_identical_content_is_a_harmless_no_op(self):
        req = request()
        result = self.result_for(req)
        with tempfile.TemporaryDirectory() as tmp:
            key1 = dp.record_result(tmp, req, result, provider="rules")
            key2 = dp.record_result(tmp, req, result, provider="rules")
            self.assertEqual(key1, key2)
            store_files = list((Path(tmp) / dp.RECORD_DIR).glob("*.json"))
            self.assertEqual(len(store_files), 1)

    def test_recording_the_same_identity_with_different_content_is_refused_and_nothing_moves(self):
        req = request()
        result = self.result_for(req)
        different = self.result_for(req, recommended="retry-same-model")
        with tempfile.TemporaryDirectory() as tmp:
            dp.record_result(tmp, req, result, provider="rules")
            before = (Path(tmp) / dp.RECORD_DIR).glob("*.json")
            before_bytes = {p: p.read_bytes() for p in before}
            self.refusal("value-invalid", dp.record_result, tmp, req, different,
                         provider="rules")
            after = (Path(tmp) / dp.RECORD_DIR).glob("*.json")
            for p in after:
                self.assertEqual(p.read_bytes(), before_bytes[p], "nothing was overwritten")
            # The replayed answer is still the FIRST one, never the second call's.
            replayed = dp.evaluate(req, mode="replay", provider="rules", store_dir=tmp)
            self.assertEqual(replayed["recommended"], "stop")

    def test_recording_a_result_whose_provider_or_model_does_not_match_is_refused(self):
        req = request()
        result = self.result_for(req)
        with tempfile.TemporaryDirectory() as tmp:
            self.refusal("value-invalid", dp.record_result, tmp, req, result,
                         provider="rules", model="not-none")
        with tempfile.TemporaryDirectory() as tmp:
            wrong_provider_result = self.result_for(req, requested_provider="replay",
                                                    dispatched_provider="replay")
            self.refusal("value-invalid", dp.record_result, tmp, req, wrong_provider_result,
                         provider="rules")

    def test_a_replayed_result_cannot_be_recorded_as_though_it_were_fresh(self):
        req = request()
        result = self.result_for(req)
        with tempfile.TemporaryDirectory() as tmp:
            dp.record_result(tmp, req, result, provider="rules")
            replayed_payload = dp.evaluate(req, mode="replay", provider="rules", store_dir=tmp)
            replayed_result = dc.parse_result(replayed_payload, req)
            self.refusal("value-invalid", dp.record_result, tmp, req, replayed_result,
                         provider="rules")

    def test_recording_a_result_uncorrelated_to_the_request_is_refused(self):
        req = request()
        other = request(correlation_id="corr-9")
        result = self.result_for(other)
        with tempfile.TemporaryDirectory() as tmp:
            self.refusal("correlation-mismatch", dp.record_result, tmp, req, result,
                         provider="rules")

    def test_recording_or_reading_needs_the_parsed_result_not_a_payload(self):
        req = request()
        payload = self.result_for(req).to_payload()
        with tempfile.TemporaryDirectory() as tmp:
            self.refusal("wrong-type", dp.record_result, tmp, req, payload, provider="rules")

    # ---- invalid rejects: a tampered or malformed store record is refused --------------------

    def test_a_rewritten_store_record_is_refused_rather_than_silently_served(self):
        req = request()
        result = self.result_for(req)
        with tempfile.TemporaryDirectory() as tmp:
            dp.record_result(tmp, req, result, provider="rules")
            store_files = list((Path(tmp) / dp.RECORD_DIR).glob("*.json"))
            self.assertEqual(len(store_files), 1)
            path = store_files[0]
            blob = json.loads(path.read_text())
            blob["content"]["result"]["recommended"] = "stop-tampered"
            path.write_text(json.dumps(blob))
            self.refusal("value-invalid", dp.evaluate, req, mode="replay", provider="rules",
                         store_dir=tmp)

    def test_a_store_record_of_the_wrong_version_is_refused(self):
        req = request()
        result = self.result_for(req)
        with tempfile.TemporaryDirectory() as tmp:
            key = dp.record_result(tmp, req, result, provider="rules")
            path = Path(tmp) / dp.RECORD_DIR / f"{key}.json"
            blob = json.loads(path.read_text())
            blob["v"] = "polytropos.decision-replay/999"
            path.write_text(json.dumps(blob))
            self.refusal("unknown-value", dp.evaluate, req, mode="replay", provider="rules",
                         store_dir=tmp)

    def test_a_malformed_bundle_or_calibrator_reference_is_refused(self):
        req = request()
        self.refusal("value-invalid", dp.replay_key, req, provider="rules",
                     bundle_sha="not-a-digest")
        self.refusal("not-a-reference", dp.replay_key, req, provider="rules",
                     calibrator_ref="not-a-reference")
        with tempfile.TemporaryDirectory() as tmp:
            self.refusal("value-invalid", dp.record_result, tmp, req, self.result_for(req),
                         provider="rules", bundle_sha="short")

    # ---- the D08 proof shape, both halves, for "replay makes no call" -------------------------

    def test_a_replay_hit_still_never_reaches_a_runner_that_raises(self):
        runner = _RaisingRunner()
        req = request()
        result = self.result_for(req)
        with tempfile.TemporaryDirectory() as tmp:
            dp.record_result(tmp, req, result, provider="rules")
            payload = dp.evaluate(req, mode="replay", provider="rules", store_dir=tmp,
                                  runner=runner)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(runner.calls, [])

    def test_the_replay_implementation_never_names_runner_in_its_own_ast(self):
        """Structural half of the pairing above. `_evaluate_replay` genuinely calls several
        things (`_require_request`, `replay_key`, `_read_record`, `parse_result`, ...); the
        non-empty assertion below is the guard that keeps this from passing on an empty walk --
        without it, a typo'd function name would make the sweep vacuously pass too."""
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "_evaluate_replay")
        calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
        self.assertTrue(calls, "the AST walk found no calls at all in _evaluate_replay, so "
                               "the sweep below would pass trivially")
        for call in calls:
            fn_node = call.func
            name = (fn_node.id if isinstance(fn_node, ast.Name)
                    else fn_node.attr if isinstance(fn_node, ast.Attribute) else None)
            self.assertNotEqual(name, "runner",
                               "_evaluate_replay must never call the thing named 'runner'")

    def test_rules_also_never_names_runner_in_its_own_ast(self):
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "_evaluate_rules")
        calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
        self.assertTrue(calls, "the AST walk found no calls at all in _evaluate_rules")
        for call in calls:
            fn_node = call.func
            name = (fn_node.id if isinstance(fn_node, ast.Name)
                    else fn_node.attr if isinstance(fn_node, ast.Attribute) else None)
            self.assertNotEqual(name, "runner")

    def test_runner_is_accepted_by_every_public_entry_point(self):
        for fn in (dp.evaluate, dp._evaluate_rules, dp._evaluate_replay):
            with self.subTest(fn=fn.__name__):
                self.assertIn("runner", inspect.signature(fn).parameters)

    # ---- reuse, not reinvention -----------------------------------------------------------

    def test_the_replay_version_is_declared_on_the_release_surface_in_its_own_right(self):
        rows = {r["contract"]: r for r in rg.contract_versions()}
        self.assertIn(("decision replay record", "decision_provider", "REPLAY_VERSION"),
                      rg.VERSION_SOURCES)
        self.assertEqual(rows["decision replay record"]["version"], dp.REPLAY_VERSION)
        self.assertEqual(rows["decision replay record"]["owner"], "bin/decision_provider.py")
        self.assertNotEqual(dp.REPLAY_VERSION, dc.CONTRACT_VERSION)
        self.assertNotEqual(dp.REPLAY_VERSION, dc.BUNDLE_VERSION)
        self.assertNotEqual(dp.REPLAY_VERSION, dc.CANDIDATE_VERSION)
        self.assertNotEqual(dp.REPLAY_VERSION, al.LEDGER_VERSION)

    def test_a_calibrator_reference_is_the_ledgers_own_shape_read_by_its_own_code(self):
        req = request()
        ref = al.make_ref("cal-1", sha="b" * 64, version="polytropos.calibrator/1")
        key_with = dp.replay_key(req, provider="rules", calibrator_ref=ref)
        key_without = dp.replay_key(req, provider="rules")
        self.assertNotEqual(key_with, key_without)
        # A digest-free reference pins nothing, so it is refused here exactly as `_ref` refuses
        # one for a REQUIRED reference elsewhere in this contract.
        self.refusal("not-a-reference", dp.replay_key, req, provider="rules",
                     calibrator_ref=al.make_ref("cal-1"))

    def test_both_new_and_reused_result_shapes_still_pass_the_d09_validator(self):
        """The literal acceptance requirement: both implementations are tested THROUGH the D09
        validator, not merely asserted to look right by this file's own eyes."""
        req = request()
        rules_payload = dp.evaluate(req, mode="rules", provider="rules")
        dc.parse_result(rules_payload, req)
        with tempfile.TemporaryDirectory() as tmp:
            miss_payload = dp.evaluate(req, mode="replay", provider="rules", store_dir=tmp)
            dc.parse_result(miss_payload, req)
            dp.record_result(tmp, req, self.result_for(req), provider="rules")
            hit_payload = dp.evaluate(req, mode="replay", provider="rules", store_dir=tmp)
            dc.parse_result(hit_payload, req)

    # ---- structural hygiene, mirroring D09/D11's own guards -----------------------------------

    def test_the_module_is_stdlib_only_and_touches_no_home_or_process(self):
        text = MODULE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(text)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])
        # Without this guard a module reaching every import dynamically would pass the two
        # checks below on an empty set -- the vacuous-AST-guard hole D09 shipped four of.
        self.assertTrue(imported, "the AST walk found no imports at all")
        self.assertTrue(imported <= set(sys.stdlib_module_names), sorted(imported))
        for forbidden in ("subprocess", "socket", "urllib", "http", "ssl", "shutil", "os"):
            with self.subTest(module=forbidden):
                self.assertNotIn(forbidden, imported)
        for pattern in ("subprocess.", "Path.home(", "os.environ"):
            with self.subTest(pattern=pattern):
                self.assertNotIn(pattern, text)

    def test_all_filesystem_access_goes_through_safe_paths_never_a_raw_primitive(self):
        """This module DOES write and read a store -- unlike D09/D11's zero-I/O libraries --
        so the honest claim here is narrower: every byte in or out goes through
        `safe_paths.confined_*`, and the only raw filesystem call anywhere is the one `mkdir`
        that creates the caller's own `store_dir` if it does not yet exist (the same shape
        `workflow_eval._manifest_root` already uses for its own store)."""
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        calls = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn_node = node.func
                if isinstance(fn_node, ast.Attribute):
                    calls.add(fn_node.attr)
                elif isinstance(fn_node, ast.Name):
                    calls.add(fn_node.id)
        self.assertTrue(calls, "the AST walk found no calls at all, so both sweeps below "
                               "would pass trivially")
        self.assertIn("confined_create_bytes", calls)
        self.assertIn("confined_read_bytes", calls)
        self.assertIn("validate_id", calls)
        for writer in ("open", "write_text", "write_bytes", "unlink", "rename", "rmtree",
                      "touch", "system", "run", "Popen", "replace"):
            with self.subTest(call=writer):
                self.assertNotIn(writer, calls)

    def test_the_module_reaches_for_no_private_name_of_the_contract_or_the_ledger(self):
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        public, private = set(), set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            value = node.value
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
                if value.func.id in ("_contract", "_al", "_sp"):
                    (private if node.attr.startswith("_") else public).add(node.attr)
        self.assertTrue(public, "the walk found no sibling-module access at all")
        self.assertIn("parse_result", public)
        self.assertIn("read_ref", public)
        self.assertEqual(sorted(private), [])

    def test_every_refusal_this_module_raises_uses_a_declared_reason_code(self):
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        raised = set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "_refuse"):
                self.assertTrue(node.args, "a refusal always names its reason code first")
                first = node.args[0]
                self.assertIsInstance(first, ast.Constant, ast.dump(first))
                raised.add(first.value)
        self.assertTrue(raised)
        self.assertEqual(sorted(raised - set(dc.REASON_CODES)), [])

    def test_the_attempt_event_kinds_are_not_appended_from_this_module(self):
        # This module is a library the coordinator calls; it records no attempt event itself.
        # `test_decision_provenance.py` sweeps every bin/*.py for exactly this literal set.
        kinds = {"attempt.started", "attempt.finished", "verify.finished", "task.projected"}
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn_node = node.func
            name = (fn_node.attr if isinstance(fn_node, ast.Attribute)
                    else fn_node.id if isinstance(fn_node, ast.Name) else None)
            if name in ("append", "_record") and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant):
                    self.assertNotIn(first.value, kinds)

    def test_the_module_never_writes_the_evaluation_stores_own_reserved_name(self):
        # tests/test_decision_evaluation_manifest.py sweeps every bin/*.py for a quoted "evals"
        # substring and expects exactly two files to carry it; this must not become a third.
        text = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn('"evals"', text)
        self.assertNotIn("'evals'", text)

    def test_no_subprocess_call_and_no_policy_file_literal(self):
        text = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("subprocess.", text)
        self.assertNotIn("routing-policy.json", text)


if __name__ == "__main__":
    unittest.main()
