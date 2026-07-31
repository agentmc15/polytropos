"""Stdlib unittest regression suite for bin/aesop_bridge.py.

bin/ is not a package; aesop_bridge.py is loaded via importlib by absolute path
computed from this file's own location, per PLAN.md D2.

All pricing numbers used here are a synthetic fixture (deliberately fake, round
numbers) so this file never needs updating when data/pricing.json's real prices
change, and so nothing here could be mistaken for a real price. The only place
this file touches the real data/pricing.json is the CLI smoke test, which
asserts shape (valid JSON) only — never a price value.
"""

import contextlib
import importlib.util
import io
import json
import unittest
from datetime import date
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ab = _load("aesop_bridge")


# ---- synthetic fixture --------------------------------------------------------------------
#
# Deliberately fake, round numbers. Two models share tier "opus" (fake-opus-old listed
# first) to prove tier_map takes the first match in file order. One "frontier" model, one
# "sonnet" model with intro_pricing (boundary tested via the `today` parameter, never the
# real clock), one "haiku" model. One task_profiles entry with round token counts.

FIXTURE = {
    "cache_read_multiplier": 0.1,
    "models": {
        "fake-opus-old": {
            "display": "Fake Opus Old",
            "tier": "opus",
            "input_per_mtok": 4.0,
            "output_per_mtok": 8.0,
        },
        "fake-opus-new": {
            "display": "Fake Opus New",
            "tier": "opus",
            "input_per_mtok": 5.0,
            "output_per_mtok": 9.0,
        },
        "fake-frontier": {
            "display": "Fake Frontier",
            "tier": "frontier",
            "input_per_mtok": 20.0,
            "output_per_mtok": 40.0,
        },
        "fake-sonnet": {
            "display": "Fake Sonnet",
            "tier": "sonnet",
            "input_per_mtok": 3.0,
            "output_per_mtok": 6.0,
            "intro_pricing": {
                "input_per_mtok": 1.0,
                "output_per_mtok": 2.0,
                "until": "2030-06-15",
            },
        },
        "fake-haiku": {
            "display": "Fake Haiku",
            "tier": "haiku",
            "input_per_mtok": 1.0,
            "output_per_mtok": 2.0,
        },
    },
    "task_profiles": {
        "TEST": {
            "label": "Fixture test profile",
            "input_tokens": 1_000_000,
            "output_tokens": 100_000,
        },
    },
}


def _fixture_without_frontier():
    models = {k: v for k, v in FIXTURE["models"].items() if k != "fake-frontier"}
    return {**FIXTURE, "models": models}


class TierMapTests(unittest.TestCase):
    def test_first_model_per_tier_in_insertion_order(self):
        tm = ab.tier_map(FIXTURE)
        self.assertEqual(
            tm,
            {
                "frontier": "fake-frontier",
                "strong": "fake-opus-old",  # first "opus" model wins, not fake-opus-new
                "mid": "fake-sonnet",
                "cheap": "fake-haiku",
            },
        )

    def test_missing_frontier_omits_key(self):
        tm = ab.tier_map(_fixture_without_frontier())
        self.assertNotIn("frontier", tm)
        self.assertEqual(
            tm, {"strong": "fake-opus-old", "mid": "fake-sonnet", "cheap": "fake-haiku"}
        )


class EstTickMathTests(unittest.TestCase):
    def test_cache_hit_0_8(self):
        # fake-haiku: input=1.0, output=2.0 per MTok, no intro_pricing.
        # effective_input_mult = (1 - 0.8) + 0.8 * 0.1 = 0.28
        # cost = 1_000_000 * 0.28 / 1e6 * 1.0 + 100_000 / 1e6 * 2.0 = 0.28 + 0.2 = 0.48
        cost = ab.est_tick(FIXTURE, "TEST", "fake-haiku", cache_hit=0.8, today=date(2020, 1, 1))
        self.assertAlmostEqual(cost, 0.48)

    def test_cache_hit_0(self):
        # effective_input_mult = 1.0
        # cost = 1_000_000 / 1e6 * 1.0 + 100_000 / 1e6 * 2.0 = 1.0 + 0.2 = 1.2
        cost = ab.est_tick(FIXTURE, "TEST", "fake-haiku", cache_hit=0, today=date(2020, 1, 1))
        self.assertAlmostEqual(cost, 1.2)


class IntroPricingBoundaryTests(unittest.TestCase):
    """fake-sonnet: base 3.0/6.0, intro 1.0/2.0 until 2030-06-15. Boundary via `today`
    only — never the real clock."""

    def test_today_equals_until_applies_intro_rate(self):
        # intro rate (1.0/2.0), cache_hit=0.8 -> effective_input_mult=0.28
        # cost = 0.28 * 1.0 + 0.1 * 2.0 = 0.28 + 0.2 = 0.48
        cost = ab.est_tick(
            FIXTURE, "TEST", "fake-sonnet", cache_hit=0.8, today=date(2030, 6, 15)
        )
        self.assertAlmostEqual(cost, 0.48)

    def test_today_one_day_after_uses_base_rate(self):
        # base rate (3.0/6.0), cache_hit=0.8 -> effective_input_mult=0.28
        # cost = 0.28 * 3.0 + 0.1 * 6.0 = 0.84 + 0.6 = 1.44
        cost = ab.est_tick(
            FIXTURE, "TEST", "fake-sonnet", cache_hit=0.8, today=date(2030, 6, 16)
        )
        self.assertAlmostEqual(cost, 1.44)


class CheckBudgetTests(unittest.TestCase):
    def test_iterations_is_floor_and_warning_below_ten(self):
        # tick = 0.48 (see EstTickMathTests); 2.0 / 0.48 = 4.1666... -> floor 4 (< 10)
        result = ab.check_budget(
            FIXTURE, 2.0, "TEST", "fake-haiku", cache_hit=0.8, today=date(2020, 1, 1)
        )
        self.assertAlmostEqual(result["est_tick_usd"], 0.48)
        self.assertEqual(result["iterations"], 4)
        self.assertIsNotNone(result["warning"])
        self.assertIn("10 iterations", result["warning"])

    def test_no_warning_at_or_above_ten_iterations(self):
        # tick = 0.48; 10.0 / 0.48 = 20.833... -> floor 20 (>= 10)
        result = ab.check_budget(
            FIXTURE, 10.0, "TEST", "fake-haiku", cache_hit=0.8, today=date(2020, 1, 1)
        )
        self.assertEqual(result["iterations"], 20)
        self.assertIsNone(result["warning"])


class UnknownKeyTests(unittest.TestCase):
    def test_unknown_model_id_raises_keyerror_listing_choices(self):
        with self.assertRaises(KeyError) as cm:
            ab.est_tick(FIXTURE, "TEST", "not-a-real-model", today=date(2020, 1, 1))
        msg = str(cm.exception)
        self.assertIn("valid choices", msg)
        for model_id in FIXTURE["models"]:
            self.assertIn(model_id, msg)

    def test_unknown_profile_raises_keyerror_listing_choices(self):
        with self.assertRaises(KeyError) as cm:
            ab.est_tick(FIXTURE, "not-a-real-profile", "fake-haiku", today=date(2020, 1, 1))
        msg = str(cm.exception)
        self.assertIn("valid choices", msg)
        self.assertIn("TEST", msg)


class CliSmokeTests(unittest.TestCase):
    def test_tiers_json_against_real_pricing_parses(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ab.main(["tiers", "--json"])
        parsed = json.loads(buf.getvalue())
        self.assertIsInstance(parsed, dict)
        # Shape only, no price value assertions: every value is a real model id.
        real_pricing = ab.load_pricing()
        for tier, model_id in parsed.items():
            self.assertIn(model_id, real_pricing["models"])


if __name__ == "__main__":
    unittest.main()
