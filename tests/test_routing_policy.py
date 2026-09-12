"""Workflow shape, model, initial effort, and assurance are routed separately (step 19).

WHAT WAS MEASURED on the tree before `bin/routing_policy.py` and `codex_policy.route` existed:

  - `codex_policy.resolve_assignment(pricing, "mid")` raised "configured orchestrator
    'gpt-6-astra' is unavailable; execution is disabled" when Astra was marked unavailable,
    though the mid worker needed nothing from Astra. Every worker assignment went through
    `resolve_orchestrator` first.
  - A `frontier` plan was migrated down to the strongest worker; the frontier could be reached
    only after every cheaper rung had failed, through evidence-gated recovery.
  - Effort was one command-line value for every rung; nothing chose an initial effort from
    the task, and a rung that could not take it refused the whole run.
  - A dispatch that failed because the CLI was logged out climbed the ladder on Codex, though
    the Claude driver already knew that "an infrastructure failure fails the same way on a
    more expensive model".

These tests pin the replacement: the legacy behaviour under its own name (`reserved`, the
default, byte-identical dispatch), the opt-in `adaptive` policy that may send a hard task
straight to the frontier, hard filters before any preference, an unavailable orchestrator
disabling nothing a worker path does not need, explicit pins and unsupported efforts refused
rather than substituted, infrastructure-class failures stopping the ladder, and the same rule
routing a roster with a different tier order. Every dispatch is a mock or a stub script; the
real pricing files are read only where the test says so, and never for a live call.
"""

import contextlib
import copy
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_codex_execute as tcx

ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(
        f"{name}_routing_test", ROOT / "bin" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rp = _load("routing_policy")
cp = _load("codex_policy")
kc = _load("kit_contract")
ce = tcx.ce

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


# ---- fixtures ---------------------------------------------------------------------------------

TIERS = ("cheap", "mid", "strong", "frontier")
CAPS = {"dispatch": "unknown", "sandbox_read_only": "unknown", "durable_attempts": "unknown"}

#: A Codex-shaped pricing dict with efforts and availability. Synthetic ids, round fake rates.
PRICING = {
    "knobs": {"reasoning_efforts": ["low", "medium", "high", "max"]},
    "cache_read_multiplier": 0.1,
    "task_profiles": {"S": {"input_tokens": 1000, "output_tokens": 100}},
    "orchestration_policy": {
        "orchestrator_model": "top",
        "orchestrator_tier": "frontier",
        "worker_tiers": ["cheap", "mid", "strong"],
        "default_worker_tier": "mid",
        "maximum_worker_tier": "strong",
        "verification_tier": "strong",
        "recovery_evidence_kinds": [
            "verify_failure", "integration_conflict", "lower_tier_correction_failed"
        ],
    },
    "models": {
        "small": {"tier": "cheap", "available": True, "input_per_mtok": 1.0,
                  "output_per_mtok": 2.0, "supported_reasoning_efforts": ["low", "medium"],
                  "default_reasoning_effort": "medium"},
        "usual": {"tier": "mid", "available": True, "input_per_mtok": 4.0,
                  "output_per_mtok": 8.0,
                  "supported_reasoning_efforts": ["low", "medium", "high", "max"],
                  "default_reasoning_effort": "medium"},
        "hard": {"tier": "strong", "available": True, "input_per_mtok": 8.0,
                 "output_per_mtok": 16.0,
                 "supported_reasoning_efforts": ["low", "medium", "high", "max"],
                 "default_reasoning_effort": "low"},
        "top": {"tier": "frontier", "available": True, "input_per_mtok": 20.0,
                "output_per_mtok": 40.0,
                "supported_reasoning_efforts": ["low", "medium", "high", "max"],
                "default_reasoning_effort": "medium"},
        "ledger-only": {"tier": "cost-only", "available": True, "input_per_mtok": 5.0,
                        "output_per_mtok": 5.0},
    },
}


def _task(model=None, **over):
    base = {"id": "T1", "title": "t", "status": "pending", "model": model, "depends": [],
            "independent": True, "evidence": None, "brief": "do the thing", "verify": "true"}
    base.update(over)
    return base


def _catalog(pricing=PRICING):
    return cp.catalog(pricing)


def _request(**over):
    base = {"harness": "codex", "task_id": "T1", "tiers": TIERS, "default_tier": "mid",
            "capabilities": dict(CAPS), "review_model": "hard", "acceptance_model": "top",
            "brief_chars": 12, "evidence": None, "planned": None}
    base.update(over)
    return base


def _models_dispatched(runner):
    return [call.args[0][call.args[0].index("--model") + 1] for call in runner.call_args_list]


def _efforts_dispatched(runner):
    out = []
    for call in runner.call_args_list:
        argv = call.args[0]
        out.append(next((a.split("=", 1)[1] for a in argv
                         if a.startswith("model_reasoning_effort=")), None))
    return out


# ---- 1. the neutral module ----------------------------------------------------------------------

class VocabularyTests(unittest.TestCase):
    def test_the_contract_names_its_vocabulary(self):
        self.assertEqual(rp.POLICIES, ("reserved", "adaptive"))
        self.assertEqual(rp.DEFAULT_POLICY, "reserved")
        self.assertEqual(rp.PREFERENCES, ("balanced", "cost", "quality", "latency"))
        self.assertEqual(rp.SHAPES, ("direct", "reviewed", "graph"))
        self.assertEqual(rp.ASSURANCE, ("verify", "independent-review", "acceptance"))
        for shape in rp.SHAPES:
            self.assertIn("verify", rp.SHAPE_ASSURANCE[shape])
            self.assertIn("dispatch", rp.SHAPE_REQUIRES[shape])
        self.assertEqual(rp.CONTRACT_VERSION, "polytropos.routing/1")

    def test_unknown_policy_or_preference_is_refused_not_defaulted(self):
        with self.assertRaises(rp.RoutingError):
            rp.decide(_catalog(), _request(), "learned")
        with self.assertRaises(rp.RoutingError):
            rp.decide(_catalog(), _request(), "adaptive", "cheapest")
        with self.assertRaises(rp.RoutingError):
            rp.decide(_catalog(), _request(planned="mythical"), "adaptive")
        with self.assertRaises(rp.RoutingError):
            rp.decide(_catalog(), {**_request(), "tiers": ()}, "adaptive")


class CatalogTests(unittest.TestCase):
    def test_a_catalog_is_ranks_not_tier_names_and_never_reads_the_orchestrator(self):
        rows = {r["id"]: r for r in _catalog()}
        self.assertEqual([rows[m]["rank"] for m in ("small", "usual", "hard", "top")],
                         [0, 1, 2, 3])
        self.assertTrue(rows["top"]["reserved"])
        self.assertFalse(rows["ledger-only"]["routable"])
        self.assertEqual(rows["ledger-only"]["rank"], -1)
        self.assertEqual(rows["small"]["efforts"], ["low", "medium"])
        self.assertEqual(rows["hard"]["default_effort"], "low")
        gone = copy.deepcopy(PRICING)
        gone["models"]["top"]["available"] = False
        self.assertEqual({r["id"]: r["availability"] for r in cp.catalog(gone)}["top"],
                         "unavailable")

    def test_availability_unknown_is_kept_unknown(self):
        no_flag = {"models": {"x": {"tier": "mid"}}}
        row = rp.catalog_from_pricing(no_flag, "demo", TIERS)[0]
        self.assertEqual(row["availability"], "unknown")
        self.assertIsNone(row["efforts"])

    def test_a_claude_shaped_roster_routes_by_its_own_order(self):
        claude_like = {"models": {"h": {"tier": "haiku"}, "s": {"tier": "sonnet"},
                                  "o": {"tier": "opus"}, "f": {"tier": "frontier"}}}
        order = ("haiku", "sonnet", "opus", "frontier")
        rows = rp.catalog_from_pricing(claude_like, "claude", order)
        d = rp.decide(rows, {"harness": "claude", "tiers": order, "default_tier": "sonnet",
                             "planned": "opus", "capabilities": {}}, "adaptive", "cost")
        self.assertEqual(d["model"], "o")
        self.assertEqual(d["ladder"], ["f"])
        self.assertEqual(d["tiers"], list(order))

    def test_an_estimator_failure_leaves_the_row_unpriced(self):
        def boom(model_id):
            raise KeyError(model_id)
        rows = rp.catalog_from_pricing(PRICING, "codex", TIERS, estimator=boom)
        self.assertTrue(all(r["estimate"] is None for r in rows))


class FiltersTests(unittest.TestCase):
    def test_hard_filters_come_before_any_preference(self):
        gone = [dict(r, availability="unavailable") if r["id"] == "top" else r
                for r in _catalog()]
        d = rp.decide(gone, _request(planned="mid"), "adaptive", "quality")
        self.assertEqual(d["model"], "hard", "quality picks the best that survived, not top")
        reasons = {c["id"]: c["reasons"] for c in d["candidates"]}
        self.assertEqual(reasons["top"], ["unavailable"])
        self.assertEqual(reasons["ledger-only"], ["not-routable"])
        self.assertEqual(reasons["small"], ["below-floor"])
        self.assertEqual(reasons["usual"], ["ranked-lower"])

    def test_an_explicit_pin_wins_over_the_preference(self):
        d = rp.decide(_catalog(), _request(planned="small"), "adaptive", "quality")
        self.assertEqual(d["model"], "small")
        self.assertEqual(d["floor"]["pinned"], "small")
        self.assertEqual(d["uncertainty"], "low")
        others = {c["id"]: c["reasons"] for c in d["candidates"] if c["id"] != "small"}
        self.assertTrue(all("pinned-elsewhere" in r or "not-routable" in r
                            for r in others.values()), others)

    def test_an_excluded_model_is_set_aside_by_name(self):
        d = rp.decide(_catalog(), _request(planned="mid", excludes=["usual"]), "adaptive")
        self.assertEqual(d["model"], "hard")
        self.assertEqual({c["id"]: c["reasons"] for c in d["candidates"]}["usual"],
                         ["excluded"])

    def test_an_unsupported_effort_is_refused_and_the_supporters_named(self):
        d = rp.decide(_catalog(), _request(planned="small", effort="max"), "adaptive")
        self.assertIsNone(d["model"])
        self.assertIn("effort 'max' is not supported", d["refusal"])
        self.assertIn("usual", d["refusal"])
        self.assertEqual({c["id"]: c["reasons"] for c in d["candidates"]}["small"],
                         ["effort-unsupported"])

    def test_a_refused_budget_selects_nothing_before_any_ranking(self):
        d = rp.decide(_catalog(), _request(planned="mid",
                                           budget={"ok": False, "reason": "cap reached"}),
                      "adaptive", "quality")
        self.assertIsNone(d["model"])
        self.assertEqual(d["refusal"], "budget: cap reached")
        self.assertEqual(d["ladder"], [])
        self.assertIsNone(d["estimate"])

    def test_the_reserved_row_may_not_implement_under_reserved_but_may_under_adaptive(self):
        reserved = rp.decide(_catalog(), _request(planned="frontier"), "reserved",
                             chosen="hard", ladder=[])
        self.assertEqual({c["id"]: c["reasons"] for c in reserved["candidates"]}["top"],
                         ["reserved"])
        self.assertEqual(reserved["floor"]["migrated"], ("frontier", "strong"))
        adaptive = rp.decide(_catalog(), _request(planned="frontier"), "adaptive")
        self.assertEqual(adaptive["model"], "top")
        self.assertEqual(adaptive["ladder"], [])
        self.assertIsNone(adaptive["floor"]["migrated"])


class FloorAndEffortTests(unittest.TestCase):
    def test_prior_failures_raise_the_floor_and_say_so(self):
        d = rp.decide(_catalog(), _request(planned="cheap", prior_failures=2), "adaptive")
        self.assertEqual(d["floor"]["tier"], "strong")
        self.assertIn("2 prior failed attempt(s): floor raised cheap -> strong",
                      d["floor"]["basis"])
        self.assertEqual(d["model"], "hard")
        self.assertEqual(d["uncertainty"], "medium")

    def test_prior_failures_never_move_an_explicit_pin(self):
        d = rp.decide(_catalog(), _request(planned="small", prior_failures=3), "adaptive")
        self.assertEqual(d["model"], "small")
        self.assertIn("floor already at the pin", d["floor"]["basis"][-1])

    def test_no_plan_means_the_default_tier_and_high_uncertainty(self):
        d = rp.decide(_catalog(), _request(), "adaptive")
        self.assertEqual(d["model"], "usual")
        self.assertEqual(d["uncertainty"], "high")
        self.assertIn("no plan: default tier mid", d["floor"]["basis"])

    def test_a_difficult_task_starts_one_effort_step_above_the_default_when_supported(self):
        d = rp.decide(_catalog(), _request(planned="strong"), "adaptive")
        self.assertEqual(d["model"], "hard")
        self.assertEqual(d["effort"], "medium", "hard's default is low; one step up is medium")
        self.assertIn("raised one step", d["effort_basis"])
        easy = rp.decide(_catalog(), _request(planned="mid"), "adaptive")
        self.assertEqual(easy["effort"], "medium")
        self.assertEqual(easy["effort_basis"], "model-default")

    def test_an_explicit_effort_is_never_raised(self):
        d = rp.decide(_catalog(), _request(planned="strong", effort="low"), "adaptive")
        self.assertEqual(d["effort"], "low")
        self.assertEqual(d["effort_basis"], "explicit")

    def test_reserved_chooses_no_effort_the_caller_did_not_give(self):
        d = rp.decide(_catalog(), _request(planned="strong", prior_failures=1), "reserved",
                      chosen="hard", ladder=[])
        self.assertIsNone(d["effort"])
        self.assertEqual(d["effort_basis"], "host-default")


class PreferenceAndShapeTests(unittest.TestCase):
    def test_cost_picks_the_cheapest_priced_model_at_the_floor(self):
        rows = _catalog()
        for r in rows:
            r["estimate"] = {"api_equivalent_usd": {"small": 0.1, "usual": 0.5, "hard": 0.9,
                                                    "top": 2.0}.get(r["id"]), "profile": "S"}
        twin = dict(next(r for r in rows if r["id"] == "usual"), id="usual-b",
                    estimate={"api_equivalent_usd": 0.3, "profile": "S"})
        rows.append(twin)
        d = rp.decide(rows, _request(planned="mid"), "adaptive", "cost")
        self.assertEqual(d["model"], "usual-b")
        balanced = rp.decide(rows, _request(planned="mid"), "adaptive", "balanced")
        self.assertEqual(balanced["model"], "usual", "balanced keeps catalog order")

    def test_quality_picks_the_highest_eligible_rank(self):
        d = rp.decide(_catalog(), _request(planned="cheap"), "adaptive", "quality")
        self.assertEqual(d["model"], "top")

    def test_latency_says_it_has_no_data_rather_than_pretending(self):
        d = rp.decide(_catalog(), _request(planned="mid"), "adaptive", "latency")
        self.assertEqual(d["model"], "usual")
        self.assertIn("no latency data", d["preference_note"])
        self.assertIn("no latency data", rp.explain(d))

    def test_shape_follows_difficulty_and_kit_context(self):
        direct = rp.decide(_catalog(), _request(planned="mid"), "adaptive")
        self.assertEqual((direct["shape"], direct["assurance"]), ("direct", ["verify"]))
        reviewed = rp.decide(_catalog(), _request(planned="strong"), "adaptive")
        self.assertEqual(reviewed["shape"], "reviewed")
        self.assertEqual(reviewed["assurance"], ["verify", "independent-review"])
        regression = rp.decide(_catalog(), _request(planned="strong", evidence="regression"),
                               "adaptive")
        self.assertEqual(regression["shape"], "direct")
        kit = rp.decide(_catalog(), _request(planned="mid", in_kit=True), "adaptive")
        self.assertEqual(kit["shape"], "graph")
        self.assertEqual(kit["assurance"], ["verify", "independent-review", "acceptance"])
        forced = rp.decide(_catalog(), _request(planned="mid", shape="reviewed"), "adaptive")
        self.assertEqual(forced["shape"], "reviewed")

    def test_an_unsupported_capability_drops_the_shape_to_a_simpler_one_and_says_so(self):
        caps = dict(CAPS, durable_attempts="unsupported")
        d = rp.decide(_catalog(), _request(planned="mid", in_kit=True, capabilities=caps),
                      "adaptive")
        self.assertEqual(d["shape_requested"], "graph")
        self.assertEqual(d["shape"], "reviewed")
        self.assertIn("falling back to reviewed", d["shape_notes"][0])
        self.assertEqual(d["capabilities"]["unverified"], ["dispatch", "sandbox_read_only"])

    def test_unverified_capabilities_are_named_not_hidden(self):
        d = rp.decide(_catalog(), _request(planned="mid"), "adaptive")
        self.assertEqual(d["capabilities"]["required"], ["dispatch"])
        self.assertEqual(d["capabilities"]["unverified"], ["dispatch"])
        self.assertIn("unverified: dispatch", rp.explain(d))


class EstimateAndExplainTests(unittest.TestCase):
    def test_the_estimate_is_per_stage_labelled_and_never_priced_as_a_bill(self):
        rows = _catalog()
        for r in rows:
            r["estimate"] = {"api_equivalent_usd": {"usual": 0.5, "hard": 0.9, "top": 2.0}.get(
                r["id"]), "profile": "S"}
        d = rp.decide(rows, _request(planned="mid", in_kit=True), "adaptive")
        est = d["estimate"]
        self.assertFalse(est["priced"])
        self.assertIn("never a bill", est["label"])
        self.assertEqual([s["stage"] for s in est["stages"]],
                         ["implementation", "independent-review", "acceptance"])
        self.assertEqual(est["total_api_equivalent_usd"], 3.4)
        self.assertTrue(est["complete"])

    def test_a_missing_stage_model_is_named_and_the_total_marked_incomplete(self):
        gone = [dict(r, availability="unavailable") if r["id"] == "top" else r
                for r in _catalog()]
        d = rp.decide(gone, _request(planned="mid", in_kit=True, acceptance_model=None),
                      "adaptive")
        stages = {s["stage"]: s["status"] for s in d["estimate"]["stages"]}
        self.assertEqual(stages["acceptance"], "no model")
        self.assertEqual(stages["implementation"], "unpriced")
        self.assertFalse(d["estimate"]["complete"])
        self.assertIsNone(d["estimate"]["total_api_equivalent_usd"])

    def test_explain_carries_every_decision_and_every_alternative(self):
        d = rp.decide(_catalog(), _request(planned="strong", prior_failures=1), "adaptive",
                      "quality")
        text = rp.explain(d)
        self.assertIn("routing: policy=adaptive preference=quality shape=reviewed "
                      "assurance=verify+independent-review", text)
        self.assertIn("model: top (frontier, rank 4/4)", text)
        self.assertIn("floor: frontier -- planned tier strong; 1 prior failed attempt(s): "
                      "floor raised strong -> frontier", text)
        self.assertIn("uncertainty=medium", text)
        self.assertIn("alternatives:", text)
        self.assertIn("hard (strong) below-floor", text)
        self.assertIn("ledger-only (cost-only) not-routable", text)
        refused = rp.decide(_catalog(), _request(planned="small", effort="max"), "adaptive")
        self.assertIn("refused:", rp.explain(refused))

    def test_no_success_probability_appears_anywhere(self):
        d = rp.decide(_catalog(), _request(planned="mid"), "adaptive")
        blob = json.dumps(d) + rp.explain(d)
        for word in ("probability", "likelihood", "confidence", "% success"):
            self.assertNotIn(word, blob)

    def test_a_chosen_model_absent_from_the_catalog_is_an_error(self):
        with self.assertRaises(rp.RoutingError):
            rp.decide(_catalog(), _request(planned="mid"), "reserved", chosen="ghost")


# ---- 2. the Codex policy's route --------------------------------------------------------------------

class CodexRouteTests(unittest.TestCase):
    def test_reserved_is_the_default_and_agrees_with_the_legacy_resolver(self):
        for planned in (None, "cheap", "mid", "strong", "frontier", "small", "usual", "hard"):
            with self.subTest(planned=planned):
                legacy = cp.resolve_assignment(PRICING, planned)
                d = cp.route(PRICING, cp.request_for(_task(planned), pricing=PRICING))
                self.assertEqual(d["policy"], "reserved")
                self.assertEqual(d["model"], legacy["model_id"])
                self.assertEqual(d["assignment"]["model_id"], legacy["model_id"])
                self.assertEqual(d["assignment"]["migration"], legacy["migration"])
                self.assertEqual(d["ladder"], cp.worker_ladder(PRICING, legacy["model_id"]))

    def test_reserved_agrees_with_the_legacy_resolver_on_the_real_roster(self):
        pricing = json.loads((ROOT / "data" / "pricing.codex.json").read_text())
        planned_values = [None, *cp.TIER_ORDER, *[
            mid for mid in cp.eligible_models(pricing, "implementer")]]
        for planned in planned_values:
            with self.subTest(planned=planned):
                legacy = cp.resolve_assignment(pricing, planned)
                d = cp.route(pricing, cp.request_for(_task(planned), pricing=pricing))
                self.assertEqual(d["model"], legacy["model_id"])

    def test_reserved_still_fails_closed_when_the_orchestrator_is_unavailable(self):
        gone = copy.deepcopy(PRICING)
        gone["models"]["top"]["available"] = False
        with self.assertRaisesRegex(cp.PolicyError, "execution is disabled"):
            cp.route(gone, cp.request_for(_task("mid"), pricing=gone))

    def test_adaptive_routes_a_worker_with_the_orchestrator_unavailable(self):
        gone = copy.deepcopy(PRICING)
        gone["models"]["top"]["available"] = False
        d = cp.route(gone, cp.request_for(_task("mid"), pricing=gone), policy="adaptive")
        self.assertEqual(d["model"], "usual")
        self.assertEqual(d["ladder"], ["hard"], "the unavailable frontier is not a rung")
        self.assertEqual(d["assignment"]["policy"], "adaptive")
        self.assertIsNone(cp.request_for(_task("mid"), pricing=gone)["acceptance_model"])

    def test_adaptive_sends_a_frontier_plan_straight_to_the_frontier(self):
        d = cp.route(PRICING, cp.request_for(_task("frontier"), pricing=PRICING),
                     policy="adaptive")
        self.assertEqual(d["model"], "top")
        self.assertEqual(d["ladder"], [])
        self.assertIsNone(d["assignment"]["migration"])

    def test_other_roles_route_as_reserved_under_every_policy(self):
        d = cp.route(PRICING, cp.request_for(_task(), role="verifier", pricing=PRICING),
                     policy="adaptive")
        self.assertEqual(d["policy"], "reserved")
        self.assertEqual(d["model"], "hard")
        self.assertIn("routes as reserved", d["shape_notes"][-1])

    def test_unknown_policy_or_preference_is_a_policy_error(self):
        req = cp.request_for(_task("mid"), pricing=PRICING)
        with self.assertRaises(cp.PolicyError):
            cp.route(PRICING, req, policy="learned")
        with self.assertRaises(cp.PolicyError):
            cp.route(PRICING, req, preference="cheapest")

    def test_the_request_carries_the_harness_facts_and_the_task_signals(self):
        req = cp.request_for(_task("strong", brief="x" * 40, evidence="regression"),
                             effort="high", profile="S", prior_failures=2, pricing=PRICING)
        self.assertEqual(req["tiers"], cp.TIER_ORDER)
        self.assertEqual(req["default_tier"], "mid")
        self.assertEqual(req["review_model"], "hard")
        self.assertEqual(req["acceptance_model"], "top")
        self.assertEqual(req["brief_chars"], 40)
        self.assertEqual(req["evidence"], "regression")
        self.assertEqual(req["effort"], "high")
        self.assertEqual(req["prior_failures"], 2)
        self.assertEqual(req["profile"], "S")
        self.assertIn("dispatch", req["capabilities"])

    def test_the_estimator_comes_from_the_pricing_engine_only_with_a_profile(self):
        self.assertIsNone(cp.default_estimator(PRICING, None))
        with self.assertRaises(cp.PolicyError):
            cp.default_estimator(PRICING, "XXL")
        pricing = json.loads((ROOT / "data" / "pricing.codex.json").read_text())
        est = cp.default_estimator(pricing, "S")
        worker = cp.eligible_models(pricing, "implementer")[0]
        figure = est(worker)
        self.assertEqual(figure["profile"], "S")
        self.assertIsInstance(figure["api_equivalent_usd"], float)
        d = cp.route(pricing, cp.request_for(_task("mid"), profile="S", pricing=pricing),
                     policy="adaptive")
        self.assertEqual(d["estimate"]["stages"][0]["status"], "est.")

    def test_capability_states_come_from_the_registry(self):
        states = cp.capability_states()
        self.assertIn("dispatch", states)
        self.assertIn(states["dispatch"], ("supported", "unsupported", "unknown"))


# ---- 3. the Codex driver's run_task -----------------------------------------------------------------

class RunTaskRoutingTests(unittest.TestCase):
    def test_reserved_dispatch_is_unchanged_and_the_decision_rides_along(self):
        runner = mock.Mock(return_value=(0, ""))
        result = ce.run_task(_task("mid"), PRICING, runner, mock.Mock(return_value=(0, "ok")),
                             codex_bin="stub")
        self.assertEqual(_models_dispatched(runner), ["usual"])
        self.assertEqual(_efforts_dispatched(runner), [None], "reserved adds no effort flag")
        self.assertEqual(result["policy"], "reserved")
        self.assertEqual(result["decision"]["model"], "usual")
        self.assertEqual(result["attempts"][0]["effort"], None)

    def test_adaptive_frontier_implementation_needs_no_failed_cheaper_attempt(self):
        runner = mock.Mock(return_value=(0, ""))
        result = ce.run_task(_task("frontier"), PRICING, runner,
                             mock.Mock(return_value=(0, "ok")), codex_bin="stub",
                             policy="adaptive")
        self.assertEqual(_models_dispatched(runner), ["top"])
        self.assertEqual(result["status"], "done")
        self.assertIsNone(result["recovery"])
        self.assertEqual(result["escalations"], [])
        self.assertEqual(result["policy"], "adaptive")
        self.assertEqual(_efforts_dispatched(runner), ["high"],
                         "difficult: one step above top's default medium")

    def test_adaptive_ladder_climbs_to_the_frontier_as_an_ordinary_rung(self):
        runner = mock.Mock(return_value=(0, ""))
        verify = mock.Mock(side_effect=[(1, "no"), (1, "no"), (0, "yes")])
        result = ce.run_task(_task("mid"), PRICING, runner, verify, codex_bin="stub",
                             policy="adaptive")
        self.assertEqual(_models_dispatched(runner), ["usual", "hard", "top"])
        self.assertEqual(result["status"], "done")
        self.assertIsNone(result["recovery"], "no separate recovery step under adaptive")
        self.assertEqual(result["escalations"], ["hard", "top"])

    def test_adaptive_with_the_orchestrator_unavailable_still_runs_the_worker(self):
        gone = copy.deepcopy(PRICING)
        gone["models"]["top"]["available"] = False
        runner = mock.Mock(return_value=(0, ""))
        result = ce.run_task(_task("mid"), gone, runner, mock.Mock(return_value=(0, "ok")),
                             codex_bin="stub", policy="adaptive")
        self.assertEqual(_models_dispatched(runner), ["usual"])
        self.assertEqual(result["status"], "done")
        with self.assertRaisesRegex(ce.PolicyError, "execution is disabled"):
            ce.run_task(_task("mid"), gone, runner, mock.Mock(return_value=(0, "ok")),
                        codex_bin="stub")

    def test_an_explicit_pin_is_dispatched_exactly_under_adaptive(self):
        runner = mock.Mock(return_value=(0, ""))
        ce.run_task(_task("small"), PRICING, runner, mock.Mock(return_value=(0, "ok")),
                    codex_bin="stub", policy="adaptive", preference="quality")
        self.assertEqual(_models_dispatched(runner), ["small"])

    def test_an_unsupported_effort_is_refused_before_any_dispatch_under_both_policies(self):
        runner = mock.Mock(return_value=(0, ""))
        with self.assertRaisesRegex(ce.PolicyError, "max"):
            ce.run_task(_task("small"), PRICING, runner, mock.Mock(), codex_bin="stub",
                        effort="max")
        with self.assertRaisesRegex(ce.PolicyError, "max"):
            ce.run_task(_task("small"), PRICING, runner, mock.Mock(), codex_bin="stub",
                        effort="max", policy="adaptive")
        runner.assert_not_called()

    def test_an_explicit_effort_is_a_hard_filter_so_a_rung_that_cannot_take_it_is_no_rung(self):
        # The frontier cannot take `high`; under adaptive it leaves the ladder rather than
        # running at some other effort the operator did not ask for. Under reserved the same
        # roster refuses the whole run at preflight, exactly as before.
        pricing = copy.deepcopy(PRICING)
        pricing["models"]["top"]["supported_reasoning_efforts"] = ["low", "medium"]
        runner = mock.Mock(return_value=(0, ""))
        verify = mock.Mock(return_value=(1, "no"))
        result = ce.run_task(_task("mid"), pricing, runner, verify, codex_bin="stub",
                             effort="high", policy="adaptive")
        self.assertEqual(_models_dispatched(runner), ["usual", "hard"])
        self.assertEqual(_efforts_dispatched(runner), ["high", "high"])
        self.assertEqual(result["status"], "blocked")
        self.assertEqual({c["id"]: c["reasons"] for c in result["decision"]["candidates"]}["top"],
                         ["effort-unsupported"])
        with self.assertRaisesRegex(ce.PolicyError, "does not support effort 'high'"):
            ce.run_task(_task("mid"), pricing, mock.Mock(), mock.Mock(), codex_bin="stub",
                        effort="high")

    def test_a_rung_that_cannot_take_the_decisions_own_effort_runs_at_its_default(self):
        # No explicit effort: the decision raised `hard` one step to `medium`; the frontier
        # rung reports only `low`, so it runs at `low` and the attempt says so.
        pricing = copy.deepcopy(PRICING)
        pricing["models"]["top"]["supported_reasoning_efforts"] = ["low"]
        pricing["models"]["top"]["default_reasoning_effort"] = "low"
        runner = mock.Mock(return_value=(0, ""))
        verify = mock.Mock(side_effect=[(1, "no"), (0, "yes")])
        result = ce.run_task(_task("strong"), pricing, runner, verify, codex_bin="stub",
                             policy="adaptive")
        self.assertEqual(_models_dispatched(runner), ["hard", "top"])
        self.assertEqual(_efforts_dispatched(runner), ["medium", "low"])
        self.assertEqual([a["effort"] for a in result["attempts"]], ["medium", "low"])
        self.assertEqual(result["status"], "done")

    def test_an_infrastructure_class_failure_does_not_escalate_under_either_policy(self):
        for policy in (None, "adaptive"):
            with self.subTest(policy=policy):
                runner = mock.Mock(return_value=(1, "error: not logged in"))
                result = ce.run_task(_task("cheap"), PRICING, runner, mock.Mock(),
                                     codex_bin="stub", policy=policy)
                self.assertEqual(runner.call_count, 1, "a pricier model is logged out too")
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["class"], "auth")
                self.assertEqual(result["escalations"], [])
                self.assertIsNone(result["recovery"])

    def test_a_bare_nonzero_dispatch_exit_still_climbs_as_it_always_has(self):
        runner = mock.Mock(side_effect=[(9, "dispatch failed"), (0, ""), (0, ""), (0, "")])
        verify = mock.Mock(return_value=(0, "ok"))
        result = ce.run_task(_task("cheap"), PRICING, runner, verify, codex_bin="stub")
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["attempts"][0]["failure_class"], "unknown")
        self.assertEqual(_models_dispatched(runner), ["small", "usual"])

    def test_a_rung_that_hits_an_infrastructure_failure_stops_the_ladder_there(self):
        runner = mock.Mock(side_effect=[(0, ""), (1, "connection refused")])
        verify = mock.Mock(return_value=(1, "still red"))
        result = ce.run_task(_task("cheap"), PRICING, runner, verify, codex_bin="stub")
        self.assertEqual(_models_dispatched(runner), ["small", "usual"])
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["class"], "infrastructure")
        self.assertIsNone(result["recovery"])

    def test_a_caller_supplied_decision_is_the_one_that_runs(self):
        decision = cp.route(PRICING, cp.request_for(_task("mid"), pricing=PRICING),
                            policy="adaptive", preference="quality")
        runner = mock.Mock(return_value=(0, ""))
        result = ce.run_task(_task("mid"), PRICING, runner, mock.Mock(return_value=(0, "ok")),
                             codex_bin="stub", decision=decision)
        self.assertEqual(_models_dispatched(runner), ["top"])
        self.assertIs(result["decision"], decision)

    def test_a_decision_that_selected_nothing_is_refused_not_dispatched(self):
        decision = cp.route(PRICING, cp.request_for(_task("small"), effort="max",
                                                     pricing=PRICING), policy="adaptive")
        runner = mock.Mock()
        with self.assertRaisesRegex(ce.PolicyError, "routing selected no model"):
            ce.run_task(_task("small"), PRICING, runner, mock.Mock(), codex_bin="stub",
                        decision=decision)
        runner.assert_not_called()

    def test_the_note_records_the_policy_the_run_was_made_under(self):
        result = ce.run_task(_task("mid"), PRICING, mock.Mock(return_value=(0, "")),
                             mock.Mock(return_value=(0, "ok")), codex_bin="stub",
                             policy="adaptive")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "NOTES.md"
            ce.append_note(path, result, _task("mid"))
            text = path.read_text()
            self.assertIn("- routing: policy=adaptive preference=balanced shape=direct "
                          "assurance=verify effort=medium uncertainty=low", text)


# ---- 4. the command line and PLAN.md -------------------------------------------------------------

KIT_TEXT = """## Phase 1 — routing fixtures

### T1 — Routed task
- status: pending
- model: {model}
- depends: (none)
- evidence: regression

**Brief.** Do the routed thing.

**Acceptance.** It is done.

**Verify.**

```bash
true
```
"""


class PlanRoutingLineTests(unittest.TestCase):
    def test_the_line_parses_like_the_budget_line(self):
        self.assertIsNone(kc.parse_plan_routing(None))
        self.assertIsNone(kc.parse_plan_routing("# plan\nbudget: max-dispatches=3\n"))
        self.assertEqual(kc.parse_plan_routing("routing: policy=adaptive preference=cost"),
                         {"policy": "adaptive", "preference": "cost"})
        self.assertEqual(kc.parse_plan_routing("  routing: profile=M nonsense=1"),
                         {"profile": "M"})
        self.assertIsNone(kc.parse_plan_routing("routing: nothing=here"))
        self.assertEqual(kc.PLAN_ROUTING_KEYS, ("policy", "preference", "profile"))


class DriverCommandLineTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.kit = self.tmp / "fixturekit"
        self.kit.mkdir()
        self.log = self.tmp / "stub.log"
        self.stub = tcx._write_stub(self.tmp, self.log)
        self.store = self.tmp / "store"

    def tearDown(self):
        self._tmp.cleanup()

    def _kit(self, model="mid", plan=None):
        (self.kit / "TASKS.md").write_text(KIT_TEXT.format(model=model))
        if plan is not None:
            (self.kit / "PLAN.md").write_text(plan)

    def _main(self, *argv, expect_exit=None):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(ce, "load_pricing", return_value=PRICING), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            if expect_exit is None:
                ce.main(list(argv))
            else:
                with self.assertRaises(SystemExit) as ctx:
                    ce.main(list(argv))
                self.assertEqual(ctx.exception.code, expect_exit, err.getvalue())
        return out.getvalue(), err.getvalue()

    def _run_args(self, *extra):
        return ["run", "--kit", str(self.kit), "--codex-bin", str(self.stub),
                "--attempt-store", str(self.store), *extra]

    def test_dry_run_under_each_policy_previews_the_decision_and_spawns_nothing(self):
        self._kit("frontier")
        out, _err = self._main(*self._run_args("--dry-run"))
        self.assertIn("dispatched=hard", out)
        self.assertIn("orchestrator: top (reserved recovery target)", out)
        self.assertIn("routing: policy=reserved", out)
        out, _err = self._main(*self._run_args("--dry-run", "--policy", "adaptive",
                                               "--preference", "quality"))
        self.assertIn("dispatched=top", out)
        self.assertIn("none reserved under the adaptive policy", out)
        self.assertIn("routing: policy=adaptive preference=quality", out)
        self.assertIn("model_reasoning_effort=high", out, "the raised initial effort")
        self.assertFalse(self.log.exists())
        self.assertFalse((self.kit / "NOTES.md").exists())

    def test_plan_md_selects_the_policy_and_the_flag_outranks_it(self):
        self._kit("frontier", plan="# plan\nrouting: policy=adaptive preference=cost\n")
        out, _err = self._main(*self._run_args("--dry-run"))
        self.assertIn("routing: policy=adaptive preference=cost", out)
        self.assertIn("dispatched=top", out)
        out, _err = self._main(*self._run_args("--dry-run", "--policy", "reserved"))
        self.assertIn("routing: policy=reserved preference=cost", out)
        self.assertIn("dispatched=hard", out)

    def test_an_unknown_plan_word_stops_the_run_before_anything_is_written(self):
        self._kit("mid", plan="routing: policy=learned\n")
        before = (self.kit / "TASKS.md").read_bytes()
        _out, err = self._main(*self._run_args(), expect_exit=2)
        self.assertIn("unknown routing policy 'learned'", err)
        self.assertEqual((self.kit / "TASKS.md").read_bytes(), before)
        self.assertFalse(self.log.exists())
        self.assertFalse(self.store.exists())

    def test_an_unknown_flag_value_is_refused_by_the_parser(self):
        self._kit()
        _out, err = self._main(*self._run_args("--policy", "learned"), expect_exit=2)
        self.assertIn("invalid choice", err)

    def test_an_unknown_profile_is_refused_before_dispatch(self):
        self._kit()
        _out, err = self._main(*self._run_args("--profile", "XXL"), expect_exit=2)
        self.assertIn("unknown task profile 'XXL'", err)
        self.assertFalse(self.log.exists())

    def test_a_real_adaptive_run_records_its_policy_in_the_note(self):
        self._kit("frontier")
        _out, err = self._main(*self._run_args("--policy", "adaptive"))
        self.assertIn("routing: policy=adaptive", err)
        notes = (self.kit / "NOTES.md").read_text()
        self.assertIn("- routing: policy=adaptive preference=balanced shape=graph "
                      "assurance=verify+independent-review+acceptance effort=high", notes)
        self.assertIn("dispatched_model=top", notes)
        self.assertEqual(tcx._dispatched_models(self.log.read_text()), ["top"])

    def test_a_real_reserved_run_records_reserved_and_dispatches_as_before(self):
        self._kit("frontier")
        self._main(*self._run_args())
        notes = (self.kit / "NOTES.md").read_text()
        self.assertIn("- routing: policy=reserved preference=balanced shape=graph", notes)
        self.assertIn("effort=host-default", notes)
        self.assertEqual(tcx._dispatched_models(self.log.read_text()), ["hard"])

    def test_prepare_explains_and_emits_the_decision_under_both_policies(self):
        out, _err = self._main("prepare", "--model", "frontier")
        blob = json.loads(out)
        self.assertEqual(blob["model_id"], "hard")
        self.assertEqual(blob["pool_mode"], "reserved")
        self.assertEqual(blob["decision"]["policy"], "reserved")
        out, _err = self._main("prepare", "--model", "frontier", "--policy", "adaptive")
        blob = json.loads(out)
        self.assertEqual(blob["model_id"], "top")
        self.assertEqual(blob["pool_mode"], "adaptive")
        self.assertEqual(blob["decision"]["shape"], "reviewed")
        out, _err = self._main("prepare", "--model", "strong", "--policy", "adaptive",
                               "--explain")
        self.assertIn("routing: policy=adaptive", out)
        self.assertIn("model: hard (strong, rank 3/4) effort=medium (raised one step", out)

    def test_prepare_refuses_an_unsupported_effort_with_exit_2(self):
        _out, err = self._main("prepare", "--model", "small", "--policy", "adaptive",
                               "--effort", "max", expect_exit=2)
        self.assertIn("refused:", err)
        self.assertIn("effort 'max' is not supported", err)


# ---- 5. the neutral command line ---------------------------------------------------------------------

class NeutralCommandLineTests(unittest.TestCase):
    def _cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = rp._cli(argv)
        return code, out.getvalue(), err.getvalue()

    def test_demo_walks_both_policies_and_a_second_roster_spending_nothing(self):
        code, out, _err = self._cli(["demo"])
        self.assertEqual(code, 0)
        self.assertIn("policy=reserved", out)
        self.assertIn("policy=adaptive", out)
        self.assertIn("the worker-only path still routes", out)
        self.assertIn("refused: no eligible model", out)
        self.assertIn("refused: budget:", out)
        self.assertIn("demo-large (opus", out)
        for real in ("gpt-", "claude-"):
            self.assertNotIn(real, out, "the demo never names a real model id")

    def test_decide_reads_one_harness_file_from_a_pricing_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "pricing.codex.json").write_text(json.dumps(PRICING))
            code, out, _err = self._cli(["decide", "--harness", "codex", "--pricing-dir", tmp,
                                         "--planned", "frontier", "--policy", "adaptive",
                                         "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["model"], "top")
            code, out, _err = self._cli(["decide", "--harness", "codex", "--pricing-dir", tmp,
                                         "--planned", "small", "--effort", "max",
                                         "--policy", "adaptive"])
            self.assertEqual(code, 1)
            self.assertIn("refused:", out)


if __name__ == "__main__":
    unittest.main()
