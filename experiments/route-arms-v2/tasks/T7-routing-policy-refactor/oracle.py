#!/usr/bin/env python3
"""Hidden oracle for T7-routing-policy-refactor."""

import ast
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "bin" / "routing_policy.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("routing_policy_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rp = _load_module()
TIERS = ("cheap", "mid", "strong", "frontier")
CAPS = {"dispatch": "unknown", "sandbox_read_only": "unknown", "durable_attempts": "unknown"}


def _est(usd):
    return {"api_equivalent_usd": usd, "profile": "M"}


def _catalog():
    return [
        rp.catalog_entry("small", "cheap", 0, "available", efforts=["low", "medium"],
                         default_effort="medium", estimate=_est(0.05)),
        rp.catalog_entry("usual", "mid", 1, "available",
                         efforts=["low", "medium", "high", "max"],
                         default_effort="medium", estimate=_est(0.40)),
        rp.catalog_entry("hard", "strong", 2, "available",
                         efforts=["low", "medium", "high", "max"],
                         default_effort="low", estimate=_est(0.90)),
        rp.catalog_entry("top", "frontier", 3, "available", reserved=True,
                         efforts=["low", "medium", "high", "max"],
                         default_effort="medium", estimate=_est(2.50)),
        rp.catalog_entry("ledger", "cost-only", -1, "available", routable=False),
        rp.catalog_entry("gone", "mid", 1, "unavailable", estimate=_est(0.30)),
    ]


def _request(**overrides):
    data = {
        "harness": "demo", "task_id": "T1", "tiers": TIERS, "default_tier": "mid",
        "capabilities": dict(CAPS), "review_model": "hard", "acceptance_model": "top",
        "brief_chars": 12, "evidence": None, "planned": None,
    }
    data.update(overrides)
    return data


def _reasons(decision):
    return {c["id"]: c["reasons"] for c in decision["candidates"]}


def _tree():
    return ast.parse(MODULE_PATH.read_text(encoding="utf-8"))


def _func(tree, name):
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name!r} not found")


def _calls_named(node, name):
    return [n for n in ast.walk(node) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name) and n.func.id == name]


class PublicBehaviourGoldenTests(unittest.TestCase):
    def test_vocabularies_and_contract_are_unchanged(self):
        self.assertEqual(rp.CONTRACT_VERSION, "polytropos.routing/1")
        self.assertEqual(rp.POLICIES, ("reserved", "adaptive"))
        self.assertEqual(rp.DEFAULT_POLICY, "reserved")
        self.assertEqual(rp.PREFERENCES, ("balanced", "cost", "quality", "latency"))
        self.assertEqual(rp.DEFAULT_PREFERENCE, "balanced")
        self.assertEqual(rp.SHAPES, ("direct", "reviewed", "graph"))
        self.assertEqual(rp.FILTERS, ("unavailable", "not-routable", "reserved",
                                      "pinned-elsewhere", "excluded",
                                      "effort-unsupported", "below-floor", "over-budget",
                                      "ranked-lower"))

    def test_catalog_entry_keeps_exact_shape(self):
        self.assertEqual(
            rp.catalog_entry("x", "mid", "1", availability="unknown", routable=1,
                             reserved=0, efforts=("low",), default_effort="low",
                             estimate={"api_equivalent_usd": 1}, note="n"),
            {"id": "x", "tier": "mid", "rank": 1, "availability": "unknown",
             "routable": True, "reserved": False, "efforts": ["low"],
             "default_effort": "low", "estimate": {"api_equivalent_usd": 1},
             "note": "n"},
        )

    def test_catalog_from_pricing_maps_availability_rank_and_notes_exactly(self):
        pricing = {"models": {
            "a": {"tier": "cheap", "available": True, "notes": "x" * 130},
            "b": {"tier": "mid", "available": False},
            "c": {"tier": "other"},
        }}
        rows = rp.catalog_from_pricing(pricing, "demo", TIERS, reserved_model="b")
        self.assertEqual(
            rows,
            [
                {"id": "a", "tier": "cheap", "rank": 0, "availability": "available",
                 "routable": True, "reserved": False, "efforts": None,
                 "default_effort": None, "estimate": None, "note": "x" * 120},
                {"id": "b", "tier": "mid", "rank": 1, "availability": "unavailable",
                 "routable": True, "reserved": True, "efforts": None,
                 "default_effort": None, "estimate": None, "note": ""},
                {"id": "c", "tier": "other", "rank": -1, "availability": "unknown",
                 "routable": False, "reserved": False, "efforts": None,
                 "default_effort": None, "estimate": None, "note": ""},
            ],
        )

    def test_reserved_default_decision_summary_is_exact(self):
        d = rp.decide(_catalog(), _request(), "reserved")
        self.assertEqual((d["model"], d["tier"], d["rank"], d["effort"], d["effort_basis"]),
                         ("usual", "mid", 1, None, "host-default"))
        self.assertEqual(d["floor"], {"tier": "mid", "rank": 1,
                                      "basis": ["no plan: default tier mid"],
                                      "pinned": None, "migrated": None})
        self.assertEqual(d["ladder"], ["hard"])
        self.assertEqual(_reasons(d), {"small": ["below-floor"], "usual": [],
                                       "hard": ["ranked-lower"], "top": ["reserved"],
                                       "ledger": ["not-routable"],
                                       "gone": ["unavailable"]})

    def test_reserved_default_estimate_is_exact(self):
        d = rp.decide(_catalog(), _request(), "reserved")
        self.assertEqual(d["estimate"], {
            "label": "est., API-equivalent, never a bill", "priced": False, "profile": "M",
            "stages": [{"stage": "implementation", "model": "usual",
                        "api_equivalent_usd": 0.4, "status": "est."}],
            "total_api_equivalent_usd": 0.4, "complete": True,
        })

    def test_adaptive_quality_mid_picks_frontier_exactly(self):
        d = rp.decide(_catalog(), _request(planned="mid"), "adaptive", "quality")
        self.assertEqual((d["model"], d["tier"], d["rank"], d["effort"], d["effort_basis"]),
                         ("top", "frontier", 3, "medium", "model-default"))
        self.assertEqual(d["ladder"], [])
        self.assertEqual(_reasons(d)["usual"], ["ranked-lower"])
        self.assertEqual(_reasons(d)["top"], [])

    def test_adaptive_cost_mid_keeps_floor_and_ladder_exactly(self):
        d = rp.decide(_catalog(), _request(planned="mid"), "adaptive", "cost")
        self.assertEqual((d["model"], d["tier"], d["rank"]), ("usual", "mid", 1))
        self.assertEqual(d["ladder"], ["hard", "top"])
        self.assertEqual(_reasons(d)["top"], ["ranked-lower"])

    def test_explicit_pin_overrides_quality_exactly(self):
        d = rp.decide(_catalog(), _request(planned="small"), "adaptive", "quality")
        self.assertEqual((d["model"], d["tier"], d["rank"]), ("small", "cheap", 0))
        self.assertEqual(d["floor"], {"tier": "cheap", "rank": 0,
                                      "basis": ["pinned model small (cheap)"],
                                      "pinned": "small", "migrated": None})
        self.assertEqual(d["uncertainty"], "low")
        self.assertEqual(_reasons(d)["usual"], ["pinned-elsewhere"])

    def test_unsupported_effort_refusal_is_exact(self):
        d = rp.decide(_catalog(), _request(planned="small", effort="max"), "adaptive")
        self.assertIsNone(d["model"])
        self.assertEqual(d["refusal"], "no eligible model at or above tier cheap (filters that "
                         "applied: effort-unsupported, not-routable, pinned-elsewhere, "
                         "unavailable); effort 'max' is not supported by the models at that "
                         "tier (supported by: usual, hard, top)")
        self.assertEqual(_reasons(d)["small"], ["effort-unsupported"])

    def test_budget_refusal_is_before_ranking_exactly(self):
        d = rp.decide(_catalog(), _request(planned="mid",
                                           budget={"ok": False, "reason": "cap reached"}),
                      "adaptive", "quality")
        self.assertEqual(d["refusal"], "budget: cap reached")
        self.assertEqual(d["ladder"], [])
        self.assertIsNone(d["estimate"])
        self.assertEqual(_reasons(d), {"small": ["below-floor"], "usual": ["over-budget"],
                                       "hard": ["over-budget"], "top": ["over-budget"],
                                       "ledger": ["not-routable"], "gone": ["unavailable"]})

    def test_reserved_frontier_chosen_migrates_down_exactly(self):
        d = rp.decide(_catalog(), _request(planned="frontier"), "reserved",
                      chosen="hard", ladder=[])
        self.assertEqual((d["model"], d["tier"], d["rank"], d["effort"]),
                         ("hard", "strong", 2, None))
        self.assertEqual(d["floor"], {"tier": "strong", "rank": 2,
                                      "basis": ["planned tier frontier",
                                                "reserved policy: frontier plan migrates down "
                                                "to strong"],
                                      "pinned": None, "migrated": ("frontier", "strong")})

    def test_prior_failures_raise_floor_and_effort_exactly(self):
        d = rp.decide(_catalog(), _request(planned="cheap", prior_failures=2), "adaptive")
        self.assertEqual(d["floor"], {"tier": "strong", "rank": 2,
                                      "basis": ["planned tier cheap",
                                                "2 prior failed attempt(s): floor raised cheap "
                                                "-> strong"],
                                      "pinned": None, "migrated": None})
        self.assertEqual((d["model"], d["effort"], d["effort_basis"]),
                         ("hard", "medium", "raised one step above the model default 'low'"))

    def test_shape_fallback_notes_are_exact(self):
        d = rp.decide(_catalog(), _request(planned="strong", shape="graph",
                                           capabilities={"dispatch": "unknown",
                                                         "sandbox_read_only": "unsupported",
                                                         "durable_attempts": "unsupported"}),
                      "adaptive")
        self.assertEqual(d["shape"], "direct")
        self.assertEqual(d["shape_notes"], [
            "graph needs sandbox_read_only, durable_attempts, which this host reports "
            "unsupported; falling back to reviewed",
            "reviewed needs sandbox_read_only, which this host reports unsupported; falling "
            "back to direct",
        ])
        self.assertEqual(d["capabilities"], {"required": ["dispatch"],
                                             "states": {"dispatch": "unknown"},
                                             "unverified": ["dispatch"],
                                             "unsupported": []})

    def test_graph_estimate_names_missing_models_exactly(self):
        d = rp.decide(_catalog(), _request(planned="mid", shape="graph", review_model="missing",
                                           acceptance_model=None), "adaptive")
        self.assertEqual(d["assurance"], ["verify", "independent-review", "acceptance"])
        self.assertEqual(d["estimate"], {
            "label": "est., API-equivalent, never a bill", "priced": False, "profile": "M",
            "stages": [
                {"stage": "implementation", "model": "usual",
                 "api_equivalent_usd": 0.4, "status": "est."},
                {"stage": "independent-review", "model": "missing",
                 "api_equivalent_usd": None, "status": "unavailable"},
                {"stage": "acceptance", "model": None,
                 "api_equivalent_usd": None, "status": "no model"},
            ],
            "total_api_equivalent_usd": 0.4, "complete": False,
        })

    def test_latency_preference_note_is_exact(self):
        d = rp.decide(_catalog(), _request(planned="mid"), "adaptive", "latency")
        self.assertEqual(d["model"], "usual")
        self.assertEqual(d["preference_note"], "no latency data in this catalog; the choice is "
                         "the balanced one and this note says so rather than pretending "
                         "otherwise")

    def test_ladder_uses_one_candidate_per_higher_rank_exactly(self):
        catalog = _catalog() + [rp.catalog_entry("also-hard", "strong", 2, "available"),
                                rp.catalog_entry("also-top", "frontier", 3, "available")]
        d = rp.decide(catalog, _request(planned="mid"), "adaptive", "cost")
        self.assertEqual(d["ladder"], ["hard", "top"])

    def test_unknown_planned_and_non_routable_pin_errors_are_exact(self):
        with self.assertRaisesRegex(rp.RoutingError, "unknown planned model or tier 'missing'"):
            rp.decide(_catalog(), _request(planned="missing"), "adaptive")
        with self.assertRaisesRegex(rp.RoutingError, "planned 'ledger' is not a routable tier"):
            rp.decide(_catalog(), _request(planned="ledger"), "adaptive")

    def test_chosen_model_error_is_exact(self):
        with self.assertRaisesRegex(rp.RoutingError, "chosen model 'missing' is not in the catalog"):
            rp.decide(_catalog(), _request(planned="mid"), "reserved", chosen="missing")

    def test_explain_reserved_default_output_is_exact(self):
        d = rp.decide(_catalog(), _request(), "reserved")
        self.assertEqual(rp.explain(d), "\n".join([
            "routing: policy=reserved preference=balanced shape=direct assurance=verify",
            "  model: usual (mid, rank 2/4) effort=host-default",
            "  floor: mid -- no plan: default tier mid",
            "  signals: planned=none prior_failures=0 evidence=red-green (default) "
            "brief_chars=12 uncertainty=high",
            "  ladder: hard",
            "  estimate (est., API-equivalent, never a bill, profile M): "
            "implementation=usual:0.4000 total=0.4000",
            "  alternatives: small (cheap) below-floor; hard (strong) ranked-lower; top "
            "(frontier) reserved; ledger (cost-only) not-routable; gone (mid) unavailable",
            "  capabilities (direct): unverified: dispatch",
        ]))

    def test_explain_budget_refusal_output_is_exact(self):
        d = rp.decide(_catalog(), _request(planned="mid",
                                           budget={"ok": False, "reason": "cap reached"}),
                      "adaptive", "quality")
        self.assertEqual(rp.explain(d), "\n".join([
            "routing: policy=adaptive preference=quality shape=direct assurance=verify",
            "  refused: budget: cap reached",
            "  floor: mid -- planned tier mid",
            "  signals: planned=mid prior_failures=0 evidence=red-green (default) "
            "brief_chars=12 uncertainty=low",
            "  alternatives: small (cheap) below-floor; usual (mid) over-budget; hard "
            "(strong) over-budget; top (frontier) over-budget; ledger (cost-only) "
            "not-routable; gone (mid) unavailable",
            "  capabilities (direct): unverified: dispatch",
        ]))

    def test_cli_demo_exit_code_and_headers_are_unchanged(self):
        proc = subprocess.run([sys.executable, "bin/routing_policy.py", "demo"], cwd=ROOT,
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "")
        self.assertEqual([line for line in proc.stdout.splitlines() if line.startswith("==")], [
            "== the same hard task under both policies (planned frontier, one prior failure) ==",
            "== the reserved model is unavailable; the worker-only path still routes ==",
            "== an explicit pin is honoured; an unsupported effort is refused, not substituted ==",
            "== cost preference within the floor; budget refusal before any choice ==",
            "== a different roster, a different tier order, the same rule ==",
        ])

    def test_cli_bad_planned_returns_two_with_exact_message(self):
        proc = subprocess.run([sys.executable, "bin/routing_policy.py", "decide",
                               "--harness", "codex", "--planned", "missing"], cwd=ROOT,
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              check=False)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(proc.stderr, "unknown planned model or tier 'missing'\n")


class StructuralRefactorTests(unittest.TestCase):
    def test_catalog_by_id_helper_exists_and_is_private(self):
        fn = _func(_tree(), "_catalog_by_id")
        self.assertEqual(fn.name, "_catalog_by_id")
        self.assertEqual([a.arg for a in fn.args.args], ["catalog"])

    def test_catalog_by_id_has_the_single_id_dict_comprehension(self):
        fn = _func(_tree(), "_catalog_by_id")
        comps = [n for n in ast.walk(fn) if isinstance(n, ast.DictComp)]
        self.assertEqual(len(comps), 1)
        comp = comps[0]
        self.assertIsInstance(comp.key, ast.Subscript)
        self.assertIsInstance(comp.key.slice, ast.Constant)
        self.assertEqual(comp.key.slice.value, "id")
        self.assertIsInstance(comp.value, ast.Name)
        self.assertEqual(comp.generators[0].target.id, comp.value.id)

    def test_floor_uses_catalog_by_id_once(self):
        self.assertEqual(len(_calls_named(_func(_tree(), "_floor"), "_catalog_by_id")), 1)

    def test_estimate_uses_catalog_by_id_once(self):
        self.assertEqual(len(_calls_named(_func(_tree(), "_estimate"), "_catalog_by_id")), 1)

    def test_decide_uses_catalog_by_id_for_chosen_lookup(self):
        self.assertEqual(len(_calls_named(_func(_tree(), "decide"), "_catalog_by_id")), 1)

    def test_id_lookup_dict_comprehensions_exist_only_in_helper(self):
        tree = _tree()
        offenders = []
        for name in ("_floor", "decide", "_estimate"):
            fn = _func(tree, name)
            for node in ast.walk(fn):
                if isinstance(node, ast.DictComp) and isinstance(node.key, ast.Subscript):
                    if isinstance(node.key.slice, ast.Constant) and node.key.slice.value == "id":
                        offenders.append(name)
        self.assertEqual(offenders, [])

    def test_decide_no_longer_scans_candidates_with_next_for_chosen(self):
        fn = _func(_tree(), "decide")
        next_calls = _calls_named(fn, "next")
        self.assertEqual(next_calls, [])

    def test_candidate_filter_reason_helper_exists_with_exact_signature(self):
        fn = _func(_tree(), "_candidate_filter_reason")
        self.assertEqual([a.arg for a in fn.args.args],
                         ["entry", "floor", "request", "rules", "excludes",
                          "explicit_effort", "budget"])

    def test_candidate_filter_reason_owns_all_hard_filter_literals(self):
        fn = _func(_tree(), "_candidate_filter_reason")
        strings = {n.value for n in ast.walk(fn) if isinstance(n, ast.Constant)
                   and isinstance(n.value, str)}
        self.assertTrue({"not-routable", "unavailable", "pinned-elsewhere", "excluded",
                         "reserved", "effort-unsupported", "below-floor", "over-budget"}
                        <= strings)

    def test_decide_calls_candidate_filter_reason_once(self):
        self.assertEqual(len(_calls_named(_func(_tree(), "decide"),
                                          "_candidate_filter_reason")), 1)

    def test_decide_no_longer_duplicates_hard_filter_string_literals(self):
        fn = _func(_tree(), "decide")
        strings = {n.value for n in ast.walk(fn) if isinstance(n, ast.Constant)
                   and isinstance(n.value, str)}
        self.assertFalse({"not-routable", "unavailable", "pinned-elsewhere", "excluded",
                          "reserved", "below-floor", "over-budget"} & strings)

    def test_filter_helper_returns_one_reason_or_none_not_mutating_lists(self):
        fn = _func(_tree(), "_candidate_filter_reason")
        self.assertFalse(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                             and n.func.attr == "append" for n in ast.walk(fn)))
        returns = [n.value for n in ast.walk(fn) if isinstance(n, ast.Return)]
        self.assertTrue(any(isinstance(v, ast.Constant) and v.value is None for v in returns))


if __name__ == "__main__":
    unittest.main()
