"""Stdlib unittest regression suite for bin/codex_pricing.py.

bin/ is not a package; codex_pricing.py is loaded via importlib by absolute path
computed from this file's own location, per PLAN.md D10 (same convention as
tests/test_copilot_pricing.py).

All pricing numbers used here are SYNTHETIC fixtures (deliberately fake, round
numbers) so this file never needs updating when data/pricing.codex.json's real prices
change, and so nothing here could be mistaken for a real price. Crucially the fixtures'
`cache_read_multiplier` is 0.5 and `cache_write_multiplier` is 3.0 -- NOT the real
0.1 / 1.25 -- so any passing cost assertion proves the multipliers are read from the
pricing dict at run time, never hardcoded. Two fixture variants are carried: one with an
empty `strong` tier, one with an empty `mid` tier, so the D4 skip-up rule is proven
GENERAL (not just "strong happens to be empty on today's roster").

The only place this file touches the real data/pricing.codex.json is the live-data
structural test and the CLI smoke tests, all of which assert shape only (types, required
keys, positivity, vocabulary membership, the dual-framing phrase) -- never a price value.
The `est` CLI smoke uses a tier WORD so no real model-id literal appears in this test.
"""

import contextlib
import copy
import importlib.util
import io
import json
import unittest
from pathlib import Path
from unittest import mock

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cx = _load("codex_pricing")


# ---- synthetic fixtures -------------------------------------------------------------------
#
# Deliberately fake, round numbers. cache_read_multiplier = 0.5, cache_write_multiplier = 3.0
# (neither is the real 0.1 / 1.25). Rates are round so hand-computed expectations are exact.
#
# FIXTURE_EMPTY_STRONG (roster: cheap, mid, frontier -- NO strong):
#   proves skip-up when the shared 'strong' slot is empty (today's real-roster shape).
# FIXTURE_EMPTY_MID (roster: cheap, strong, frontier -- NO mid):
#   proves the SAME rule generalizes to a DIFFERENT empty tier.

FIXTURE_EMPTY_STRONG = {
    "cached_date": "2020-01-01",
    "update_from": "fixture -- not a real source",
    "billing_modes": {
        "api": {"unit": "USD", "note": "fixture api mode"},
        "subscription": {"unit": None, "usage_limited": True, "note": "fixture sub mode"},
    },
    "cache_read_multiplier": 0.5,
    "cache_write_multiplier": 3.0,
    "cache_min_life_minutes": 30,
    "plans": {
        "planP": {"usd_per_month": 10, "included_usage": None, "note": "fixture priced plan"},
        "planN": {"usd_per_month": None, "included_usage": None},
    },
    "knobs": {"reasoning_efforts": ["low", "high", "max"]},
    "models": {
        "fake-cheap": {
            "display": "Fake Cheap",
            "vendor": "fake-vendor",
            "tier": "cheap",
            "input_per_mtok": 2.0,
            "output_per_mtok": 4.0,
        },
        "fake-mid": {
            "display": "Fake Mid",
            "vendor": "fake-vendor",
            "tier": "mid",
            "input_per_mtok": 8.0,
            "output_per_mtok": 16.0,
        },
        "fake-frontier": {
            "display": "Fake Frontier",
            "vendor": "fake-vendor",
            "tier": "frontier",
            "input_per_mtok": 20.0,
            "output_per_mtok": 40.0,
        },
    },
    "task_profiles": {
        "T": {"label": "fixture task", "input_tokens": 100000, "output_tokens": 10000},
    },
}

# Empty-mid variant: cheap + strong + frontier, no mid. Same multipliers/profile.
FIXTURE_EMPTY_MID = copy.deepcopy(FIXTURE_EMPTY_STRONG)
FIXTURE_EMPTY_MID["models"] = {
    "fake-cheap": {
        "display": "Fake Cheap",
        "vendor": "fake-vendor",
        "tier": "cheap",
        "input_per_mtok": 2.0,
        "output_per_mtok": 4.0,
    },
    "fake-strong": {
        "display": "Fake Strong",
        "vendor": "fake-vendor",
        "tier": "strong",
        "input_per_mtok": 8.0,
        "output_per_mtok": 16.0,
    },
    "fake-frontier": {
        "display": "Fake Frontier",
        "vendor": "fake-vendor",
        "tier": "frontier",
        "input_per_mtok": 20.0,
        "output_per_mtok": 40.0,
    },
}


class EstCostMathTests(unittest.TestCase):
    """fake-cheap: input=2.0, output=4.0 per MTok; cache_read_multiplier fixture=0.5.

    Profile T: 100000 input tokens, 10000 output tokens.
    """

    def test_cache_hit_0_8(self):
        # cached term uses input * 0.5 (fixture multiplier), NOT the real 0.1:
        # input_leg = 100000 * ((1-0.8)*2.0 + 0.8*2.0*0.5) / 1e6
        #           = 100000 * (0.4 + 0.8) / 1e6 = 100000 * 1.2 / 1e6 = 0.12
        # output_leg = 10000 / 1e6 * 4.0 = 0.04
        # usd_api = 0.16
        result = cx.est_cost(FIXTURE_EMPTY_STRONG, "T", "fake-cheap", cache_hit=0.8)
        self.assertAlmostEqual(result["usd_api"], 0.16)
        self.assertEqual(result["model_id"], "fake-cheap")

    def test_cache_hit_0(self):
        # No cache discount at all: input_leg = 100000 * 2.0 / 1e6 = 0.2; output_leg = 0.04
        # usd_api = 0.24
        result = cx.est_cost(FIXTURE_EMPTY_STRONG, "T", "fake-cheap", cache_hit=0)
        self.assertAlmostEqual(result["usd_api"], 0.24)

    def test_cached_term_uses_fixture_multiplier_not_real(self):
        # If code hardcoded the real 0.1, cache_hit=0.8 would give a different number.
        # Recompute independently with the fixture's own multiplier to be explicit.
        m = FIXTURE_EMPTY_STRONG["cache_read_multiplier"]
        self.assertEqual(m, 0.5)  # fixture, deliberately not 0.1
        expected = 100000 * ((1 - 0.8) * 2.0 + 0.8 * 2.0 * m) / 1e6 + 10000 / 1e6 * 4.0
        result = cx.est_cost(FIXTURE_EMPTY_STRONG, "T", "fake-cheap", cache_hit=0.8)
        self.assertAlmostEqual(result["usd_api"], expected)


class CacheWriteExclusionTests(unittest.TestCase):
    """cache_write_multiplier (fixture 3.0) must never affect an estimate."""

    def test_cache_write_multiplier_has_zero_effect(self):
        baseline = cx.est_cost(FIXTURE_EMPTY_STRONG, "T", "fake-cheap", cache_hit=0.8)

        mutated = copy.deepcopy(FIXTURE_EMPTY_STRONG)
        mutated["cache_write_multiplier"] = 9999.0
        after = cx.est_cost(mutated, "T", "fake-cheap", cache_hit=0.8)
        self.assertEqual(baseline["usd_api"], after["usd_api"])

        stripped = copy.deepcopy(FIXTURE_EMPTY_STRONG)
        del stripped["cache_write_multiplier"]
        after_stripped = cx.est_cost(stripped, "T", "fake-cheap", cache_hit=0.8)
        self.assertEqual(baseline["usd_api"], after_stripped["usd_api"])


class BurnIndexTests(unittest.TestCase):
    """Burn index = usd_api / cheapest same-profile usd_api across the whole roster."""

    def test_cheap_model_burn_index_is_one(self):
        result = cx.est_cost(FIXTURE_EMPTY_STRONG, "T", "fake-cheap", cache_hit=0.8)
        sub = result["subscription"]
        self.assertAlmostEqual(sub["burn_index_vs_cheapest"], 1.0)
        self.assertEqual(sub["cheapest_model_id"], "fake-cheap")

    def test_frontier_burn_index_hand_computed_ratio_vs_cheap(self):
        # frontier usd_api at cache_hit=0.8:
        # input_leg = 100000 * (0.2*20.0 + 0.8*20.0*0.5)/1e6 = 100000*(4.0+8.0)/1e6 = 1.2
        # output_leg = 10000/1e6*40.0 = 0.4 ; usd_api = 1.6
        # cheap usd_api = 0.16 -> burn = 1.6 / 0.16 = 10.0
        result = cx.est_cost(FIXTURE_EMPTY_STRONG, "T", "fake-frontier", cache_hit=0.8)
        self.assertAlmostEqual(result["usd_api"], 1.6)
        self.assertAlmostEqual(result["subscription"]["burn_index_vs_cheapest"], 10.0)
        self.assertEqual(result["subscription"]["cheapest_model_id"], "fake-cheap")

    def test_billed_usd_is_none_in_every_result(self):
        for mid in FIXTURE_EMPTY_STRONG["models"]:
            result = cx.est_cost(FIXTURE_EMPTY_STRONG, "T", mid, cache_hit=0.8)
            self.assertIsNone(result["subscription"]["billed_usd"])
            self.assertAlmostEqual(
                result["subscription"]["api_equivalent_usd"], result["usd_api"]
            )


class ResolveTierSkipUpTests(unittest.TestCase):
    """The D4 skip-up rule, proven on BOTH empty-tier variants."""

    def test_empty_strong_skips_up_to_frontier(self):
        self.assertEqual(cx.resolve_tier(FIXTURE_EMPTY_STRONG, "strong"), "fake-frontier")

    def test_empty_mid_skips_up_to_strong(self):
        # Different empty tier -> proves the rule, not today's data.
        self.assertEqual(cx.resolve_tier(FIXTURE_EMPTY_MID, "mid"), "fake-strong")

    def test_populated_tier_resolves_to_first_file_order_model(self):
        # Add a second cheap model AFTER fake-cheap; resolve must pick the first.
        fx = copy.deepcopy(FIXTURE_EMPTY_STRONG)
        fx["models"]["fake-cheap-2"] = {
            "display": "Fake Cheap 2",
            "vendor": "fake-vendor",
            "tier": "cheap",
            "input_per_mtok": 3.0,
            "output_per_mtok": 6.0,
        }
        self.assertEqual(cx.resolve_tier(fx, "cheap"), "fake-cheap")

    def test_populated_tiers_direct(self):
        self.assertEqual(cx.resolve_tier(FIXTURE_EMPTY_STRONG, "cheap"), "fake-cheap")
        self.assertEqual(cx.resolve_tier(FIXTURE_EMPTY_STRONG, "mid"), "fake-mid")
        self.assertEqual(cx.resolve_tier(FIXTURE_EMPTY_STRONG, "frontier"), "fake-frontier")

    def test_unknown_tier_word_raises_keyerror_listing_vocabulary(self):
        with self.assertRaises(KeyError) as ctx:
            cx.resolve_tier(FIXTURE_EMPTY_STRONG, "gigabrain")
        msg = str(ctx.exception)
        for tier in cx.TIER_ORDER:
            self.assertIn(tier, msg)

    def test_nothing_at_or_above_request_raises_keyerror(self):
        # Roster with only a cheap model; request frontier -> nothing at/above it.
        fx = copy.deepcopy(FIXTURE_EMPTY_STRONG)
        fx["models"] = {"fake-cheap": FIXTURE_EMPTY_STRONG["models"]["fake-cheap"]}
        with self.assertRaises(KeyError):
            cx.resolve_tier(fx, "frontier")


class ResolveModelTests(unittest.TestCase):
    def test_model_id_returned_verbatim(self):
        self.assertEqual(cx.resolve_model(FIXTURE_EMPTY_STRONG, "fake-mid"), "fake-mid")

    def test_tier_word_resolves_via_resolve_tier(self):
        self.assertEqual(cx.resolve_model(FIXTURE_EMPTY_STRONG, "strong"), "fake-frontier")

    def test_unknown_raises_keyerror_listing_ids_and_tiers(self):
        with self.assertRaises(KeyError) as ctx:
            cx.resolve_model(FIXTURE_EMPTY_STRONG, "nonsense")
        msg = str(ctx.exception)
        for mid in FIXTURE_EMPTY_STRONG["models"]:
            self.assertIn(mid, msg)
        for tier in cx.TIER_ORDER:
            self.assertIn(tier, msg)


class UnknownProfileTests(unittest.TestCase):
    def test_unknown_profile_raises_keyerror_listing_choices(self):
        with self.assertRaises(KeyError) as ctx:
            cx.est_cost(FIXTURE_EMPTY_STRONG, "not-a-profile", "fake-cheap")
        msg = str(ctx.exception)
        self.assertIn("valid choices", msg)
        for pid in FIXTURE_EMPTY_STRONG["task_profiles"]:
            self.assertIn(pid, msg)


class ModelsTableTests(unittest.TestCase):
    def test_preserves_file_order(self):
        rows = cx.models_table(FIXTURE_EMPTY_STRONG)
        self.assertEqual([r["id"] for r in rows], list(FIXTURE_EMPTY_STRONG["models"]))

    def test_cached_input_per_mtok_is_computed(self):
        rows = cx.models_table(FIXTURE_EMPTY_STRONG)
        m = FIXTURE_EMPTY_STRONG["cache_read_multiplier"]
        for r in rows:
            self.assertAlmostEqual(r["cached_input_per_mtok"], r["input_per_mtok"] * m)

    def test_no_est_columns_without_profile(self):
        rows = cx.models_table(FIXTURE_EMPTY_STRONG)
        for r in rows:
            self.assertNotIn("est_usd_api", r)
            self.assertNotIn("burn_index", r)

    def test_est_columns_present_with_profile(self):
        rows = cx.models_table(FIXTURE_EMPTY_STRONG, profile="T", cache_hit=0.8)
        cheap = next(r for r in rows if r["id"] == "fake-cheap")
        self.assertIn("est_usd_api", cheap)
        self.assertIn("burn_index", cheap)
        self.assertAlmostEqual(cheap["est_usd_api"], 0.16)
        self.assertAlmostEqual(cheap["burn_index"], 1.0)


class PlansTableTests(unittest.TestCase):
    def test_preserves_file_order(self):
        rows = cx.plans_table(FIXTURE_EMPTY_STRONG)
        self.assertEqual([r["id"] for r in rows], list(FIXTURE_EMPTY_STRONG["plans"]))

    def test_null_included_usage_stays_none(self):
        rows = cx.plans_table(FIXTURE_EMPTY_STRONG)
        for r in rows:
            self.assertIsNone(r["included_usage"])  # never invented
        priced = next(r for r in rows if r["id"] == "planP")
        self.assertEqual(priced["usd_per_month"], 10)
        nullp = next(r for r in rows if r["id"] == "planN")
        self.assertIsNone(nullp["usd_per_month"])
        self.assertIsNone(nullp["note"])


class KnobsCmdTests(unittest.TestCase):
    """cmd_knobs(args, pricing) -- the reasoning-effort/mode-notes subcommand (PLAN.md D6).

    Synthetic fixtures only, except the real-file smoke test (shape/substring only, no
    price literal).
    """

    def test_knobs_prints_efforts_notes_and_modes(self):
        fixture = {
            "knobs": {
                "reasoning_efforts": ["aa", "bb"],
                "reasoning_efforts_note": "fake note",
                "modes": {"fakemode": {"note": "fake mode note"}},
            }
        }
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cx.cmd_knobs(mock.Mock(json=False), fixture)
        out = buf.getvalue()
        self.assertIn("aa | bb", out)
        self.assertIn("fake note", out)
        self.assertIn("mode fakemode: fake mode note", out)

    def test_knobs_absent_is_honest_and_exit_0(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cx.cmd_knobs(mock.Mock(json=False), {})  # no knobs key at all
        out = buf.getvalue()
        self.assertIn("no knobs recorded", out)

    def test_knobs_json_round_trips(self):
        fixture_knobs = {
            "reasoning_efforts": ["aa", "bb"],
            "reasoning_efforts_note": "fake note",
            "modes": {"fakemode": {"note": "fake mode note"}},
        }
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cx.cmd_knobs(mock.Mock(json=True), {"knobs": fixture_knobs})
        self.assertEqual(json.loads(buf.getvalue()), fixture_knobs)

    def test_knobs_real_file_smoke(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cx.main(["knobs"])
        out = buf.getvalue()
        self.assertIn("xhigh", out)  # the T2-landed correction
        self.assertIn("ultra", out)  # the mode note is relayed


class LiveDataStructureTests(unittest.TestCase):
    """Structural validation of the REAL data/pricing.codex.json -- shape only, no price
    literals asserted."""

    def test_required_top_level_keys_present(self):
        pricing = cx.load_pricing()
        for key in (
            "cached_date", "update_from", "billing_modes", "cache_read_multiplier",
            "cache_write_multiplier", "plans", "models", "knobs", "task_profiles",
        ):
            self.assertIn(key, pricing)

    def test_subscription_unit_is_null(self):
        pricing = cx.load_pricing()
        self.assertIsNone(pricing["billing_modes"]["subscription"]["unit"])

    def test_every_model_has_required_positive_fields_and_valid_tier(self):
        pricing = cx.load_pricing()
        # A model's tier is either a routing tier OR the documented 'non-routing' sentinel:
        # observed, non-selectable ids (e.g. codex-auto-review, Codex Desktop's auto-review
        # feature) live in the roster only so usage can be priced, and resolve_tier skips them.
        valid_tiers = set(cx.TIER_ORDER) | {"non-routing"}
        for model_id, info in pricing["models"].items():
            self.assertIn("display", info, model_id)
            self.assertIn("vendor", info, model_id)
            self.assertIn(info.get("tier"), valid_tiers, model_id)
            self.assertGreater(info["input_per_mtok"], 0, model_id)
            self.assertGreater(info["output_per_mtok"], 0, model_id)

    def test_non_routing_models_are_never_selected_by_resolve_tier(self):
        pricing = cx.load_pricing()
        non_routing = {k for k, v in pricing["models"].items() if v.get("tier") == "non-routing"}
        for tier in cx.TIER_ORDER:
            try:
                resolved = cx.resolve_tier(pricing, tier)
            except KeyError:
                continue  # unpopulated tier at/above the ladder top — fine
            self.assertNotIn(resolved, non_routing, tier)

    def test_task_profiles_are_exactly_xs_s_m_l_xl(self):
        pricing = cx.load_pricing()
        self.assertEqual(set(pricing["task_profiles"]), {"XS", "S", "M", "L", "XL"})


class CliSmokeTests(unittest.TestCase):
    def test_models_json_against_real_pricing_parses(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cx.main(["models", "--json"])
        rows = json.loads(buf.getvalue())
        self.assertIsInstance(rows, list)
        real = cx.load_pricing()
        self.assertEqual([r["id"] for r in rows], list(real["models"]))

    def test_est_with_tier_word_prints_not_a_bill(self):
        # Tier word (not an id literal) so no real model id appears in this test.
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cx.main(["est", "M", "cheap"])
        out = buf.getvalue()
        self.assertIn("not a bill", out)
        self.assertIn("not token-billed", out)

    def test_est_json_with_tier_word_has_null_billed_usd(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cx.main(["est", "M", "cheap", "--json"])
        out = json.loads(buf.getvalue())
        self.assertIsNone(out["subscription"]["billed_usd"])

    def test_unknown_id_exits_2(self):
        err = io.StringIO()
        with self.assertRaises(SystemExit) as ctx:
            with contextlib.redirect_stderr(err):
                cx.main(["est", "M", "not-a-real-model"])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
