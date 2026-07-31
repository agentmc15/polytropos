"""Stdlib unittest regression suite for bin/copilot_pricing.py.

bin/ is not a package; copilot_pricing.py is loaded via importlib by absolute path
computed from this file's own location, per PLAN.md D2 (same convention as
tests/test_aesop_bridge.py).

All pricing numbers used here are a synthetic fixture (deliberately fake, round
numbers) so this file never needs updating when data/pricing.copilot.json's real
prices change, and so nothing here could be mistaken for a real price. Crucially the
fixture's billing_unit.usd_per_credit is 0.5 -- NOT the real AIC rate -- to prove the
USD<->AIC conversion is derived from the pricing dict at run time, never hardcoded.
The only place this file touches the real data/pricing.copilot.json is the live-data
structural test and the CLI smoke test, both of which assert shape only (types,
required keys, positivity, vocabulary membership) -- never a price value.

No wall-clock assertions: every call that can be affected by promo logic passes
`today` explicitly as a `datetime.date`.
"""

import contextlib
import copy
import importlib.util
import io
import json
import math
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cp = _load("copilot_pricing")


# ---- synthetic fixture --------------------------------------------------------------------
#
# Deliberately fake, round numbers.
#   - billing_unit.usd_per_credit = 0.5 (real value is nowhere near this).
#   - fake-cheap: plain model, no long_context/promo/cache_write, tier "cheap".
#   - fake-strong-lc: long_context model (threshold 100000, doubled rates), tier "strong".
#   - fake-promo: promo model (until 2030-01-01, far in the future -- never the real
#     clock) that also carries a cache_write_per_mtok, which must have zero effect on
#     the estimate.
#   - plans: "planA" has a fixed allowance (1000), "planB" has a null allowance.
#   - task_profiles: "S" is small (below the long-context threshold), "T" sits exactly
#     AT the long-context threshold (must still use base rates), "T_PLUS" sits above it
#     (must use long_context rates for the whole estimate).

FIXTURE = {
    "cached_date": "2020-01-01",
    "billing_unit": {
        "name": "AIC",
        "usd_per_credit": 0.5,
        "note": "Fixture unit -- deliberately not the real 0.01 rate.",
    },
    "plans": {
        "planA": {"usd_per_month": 10, "included_aic_per_month": 1000},
        "planB": {
            "usd_per_month": None,
            "included_aic_per_month": None,
            "note": "no fixed allowance in this fixture",
        },
    },
    "models": {
        "fake-cheap": {
            "display": "Fake Cheap",
            "vendor": "fake-vendor",
            "tier": "cheap",
            "input_per_mtok": 1.0,
            "cached_input_per_mtok": 0.1,
            "output_per_mtok": 2.0,
        },
        "fake-strong-lc": {
            "display": "Fake Strong LC",
            "vendor": "fake-vendor",
            "tier": "strong",
            "input_per_mtok": 2.0,
            "cached_input_per_mtok": 0.2,
            "output_per_mtok": 4.0,
            "long_context": {
                "threshold_tokens": 100000,
                "input_per_mtok": 4.0,
                "cached_input_per_mtok": 0.4,
                "output_per_mtok": 8.0,
            },
        },
        "fake-promo": {
            "display": "Fake Promo",
            "vendor": "fake-vendor",
            "tier": "mid",
            "input_per_mtok": 1.0,
            "cached_input_per_mtok": 0.1,
            "cache_write_per_mtok": 5.0,
            "output_per_mtok": 2.0,
            "promo": {"until": "2030-01-01", "note": "fixture promo, far future"},
        },
    },
    "task_profiles": {
        "S": {
            "label": "Small fixture profile (below LC threshold)",
            "input_tokens": 10000,
            "output_tokens": 1000,
        },
        "T": {
            "label": "Exactly at LC threshold",
            "input_tokens": 100000,
            "output_tokens": 10000,
        },
        "T_PLUS": {
            "label": "Above LC threshold",
            "input_tokens": 200000,
            "output_tokens": 10000,
        },
    },
}


class EstCostMathTests(unittest.TestCase):
    """fake-cheap: input=1.0, cached=0.1, output=2.0 per MTok, no long_context/promo."""

    def test_cache_hit_0_8(self):
        # effective_input_mult = (1 - 0.8) * 1.0 + 0.8 * 0.1 = 0.28
        # usd = 10000 * 0.28 / 1e6 + 1000 / 1e6 * 2.0 = 0.0028 + 0.002 = 0.0048
        result = cp.est_cost(
            FIXTURE, "S", "fake-cheap", cache_hit=0.8, today=date(2020, 1, 1)
        )
        self.assertAlmostEqual(result["usd"], 0.0048)
        # aic = usd / billing_unit.usd_per_credit (fixture's 0.5, not the real 0.01)
        self.assertAlmostEqual(result["aic"], 0.0048 / 0.5)
        self.assertAlmostEqual(result["aic"], 0.0096)
        self.assertEqual(result["rates_used"], "base")
        self.assertEqual(result["warnings"], [])

    def test_cache_hit_0(self):
        # usd = 10000 * 1.0 / 1e6 + 1000 / 1e6 * 2.0 = 0.01 + 0.002 = 0.012
        result = cp.est_cost(
            FIXTURE, "S", "fake-cheap", cache_hit=0, today=date(2020, 1, 1)
        )
        self.assertAlmostEqual(result["usd"], 0.012)
        self.assertAlmostEqual(result["aic"], 0.024)
        self.assertEqual(result["rates_used"], "base")


class LongContextBoundaryTests(unittest.TestCase):
    """fake-strong-lc: base 2.0/0.2/4.0, long_context (threshold 100000) 4.0/0.4/8.0."""

    def test_at_threshold_uses_base_rates(self):
        # input_tokens (100000) is NOT > threshold_tokens (100000) -> base rates.
        # usd = 100000 * (0.2*2.0 + 0.8*0.2) / 1e6 + 10000/1e6*4.0
        #     = 100000 * 0.56 / 1e6 + 0.04 = 0.056 + 0.04 = 0.096
        result = cp.est_cost(
            FIXTURE, "T", "fake-strong-lc", cache_hit=0.8, today=date(2020, 1, 1)
        )
        self.assertAlmostEqual(result["usd"], 0.096)
        self.assertEqual(result["rates_used"], "base")

    def test_above_threshold_uses_long_context_rates_for_whole_estimate(self):
        # input_tokens (200000) > threshold_tokens (100000) -> long_context rates
        # apply to the WHOLE estimate (both input and output legs).
        # usd = 200000 * (0.2*4.0 + 0.8*0.4) / 1e6 + 10000/1e6*8.0
        #     = 200000 * 1.12 / 1e6 + 0.08 = 0.224 + 0.08 = 0.304
        result = cp.est_cost(
            FIXTURE, "T_PLUS", "fake-strong-lc", cache_hit=0.8, today=date(2020, 1, 1)
        )
        self.assertAlmostEqual(result["usd"], 0.304)
        self.assertEqual(result["rates_used"], "long_context")


class CacheWriteExclusionTests(unittest.TestCase):
    """fake-promo carries cache_write_per_mtok=5.0; it must never affect the estimate."""

    def test_cache_write_present_has_zero_effect(self):
        baseline = cp.est_cost(
            FIXTURE, "S", "fake-promo", cache_hit=0.8, today=date(2020, 1, 1)
        )
        # Same input/cached/output rates as fake-cheap's "S" case -> same exact usd.
        self.assertAlmostEqual(baseline["usd"], 0.0048)

        # Wildly different cache_write_per_mtok -> identical usd.
        mutated = copy.deepcopy(FIXTURE)
        mutated["models"]["fake-promo"]["cache_write_per_mtok"] = 9999.0
        result_mutated = cp.est_cost(
            mutated, "S", "fake-promo", cache_hit=0.8, today=date(2020, 1, 1)
        )
        self.assertEqual(baseline["usd"], result_mutated["usd"])

        # Removing the key entirely -> still identical usd.
        stripped = copy.deepcopy(FIXTURE)
        del stripped["models"]["fake-promo"]["cache_write_per_mtok"]
        result_stripped = cp.est_cost(
            stripped, "S", "fake-promo", cache_hit=0.8, today=date(2020, 1, 1)
        )
        self.assertEqual(baseline["usd"], result_stripped["usd"])


class PromoWarningTests(unittest.TestCase):
    """fake-promo: promo.until = 2030-01-01. Boundary via `today` only, never the real clock."""

    def test_today_before_until_no_warning(self):
        result = cp.est_cost(
            FIXTURE, "S", "fake-promo", cache_hit=0.8, today=date(2029, 12, 31)
        )
        self.assertEqual(result["warnings"], [])

    def test_today_equals_until_no_warning(self):
        result = cp.est_cost(
            FIXTURE, "S", "fake-promo", cache_hit=0.8, today=date(2030, 1, 1)
        )
        self.assertEqual(result["warnings"], [])

    def test_today_after_until_appends_warning(self):
        result = cp.est_cost(
            FIXTURE, "S", "fake-promo", cache_hit=0.8, today=date(2030, 1, 2)
        )
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("2030-01-01", result["warnings"][0])
        self.assertIn("promo pricing ended", result["warnings"][0])

    def test_no_promo_model_never_warns(self):
        result = cp.est_cost(
            FIXTURE, "S", "fake-cheap", cache_hit=0.8, today=date(2099, 1, 1)
        )
        self.assertEqual(result["warnings"], [])


class PlanRunwayTests(unittest.TestCase):
    def test_tasks_per_month_floor_and_pct_of_allowance(self):
        # est_aic_per_task for "S" on fake-cheap at cache_hit=0.8 is 0.0096 (see
        # EstCostMathTests). planA.included_aic_per_month = 1000.
        # tasks_per_month = floor(1000 / 0.0096) = floor(104166.666...) = 104166
        # pct_of_allowance = 0.0096 / 1000 * 100 = 0.00096
        result = cp.plan_runway(
            FIXTURE, "planA", "S", "fake-cheap", cache_hit=0.8, today=date(2020, 1, 1)
        )
        self.assertAlmostEqual(result["est_aic_per_task"], 0.0096)
        self.assertEqual(result["tasks_per_month"], 104166)
        self.assertAlmostEqual(result["pct_of_allowance"], 0.00096)

    def test_null_allowance_plan_raises_keyerror_naming_plan(self):
        with self.assertRaises(KeyError) as cm:
            cp.plan_runway(
                FIXTURE, "planB", "S", "fake-cheap", cache_hit=0.8, today=date(2020, 1, 1)
            )
        self.assertIn("planB", str(cm.exception))

    def test_unknown_plan_raises_keyerror_listing_choices(self):
        with self.assertRaises(KeyError) as cm:
            cp.plan_runway(
                FIXTURE,
                "not-a-real-plan",
                "S",
                "fake-cheap",
                cache_hit=0.8,
                today=date(2020, 1, 1),
            )
        msg = str(cm.exception)
        self.assertIn("valid choices", msg)
        for plan_id in FIXTURE["plans"]:
            self.assertIn(plan_id, msg)


class PlanRunwayPoolTests(unittest.TestCase):
    """Pooled-AIC runway (PLAN.md D8): plan_runway's additive `pool_aic` keyword.

    Expectations are derived from cp.est_cost on the same fixture/profile/model
    rather than hand-copied rates, so these tests still hold if the fixture's
    numbers ever change. Uses the file's own FIXTURE (planA fixed 1000 / planB
    null allowance, fake-cheap model, S profile) -- no new fixture data.
    """

    def _est_aic(self):
        return cp.est_cost(
            FIXTURE, "S", "fake-cheap", cache_hit=0.8, today=date(2020, 1, 1)
        )["aic"]

    def test_null_allowance_plan_with_pool_uses_pool(self):
        est_aic = self._est_aic()
        result = cp.plan_runway(
            FIXTURE, "planB", "S", "fake-cheap", cache_hit=0.8,
            today=date(2020, 1, 1), pool_aic=500,
        )
        self.assertEqual(result["allowance_source"], "pool")
        self.assertEqual(result["allowance_aic"], 500)
        self.assertEqual(result["tasks_per_month"], math.floor(500 / est_aic))
        self.assertAlmostEqual(result["pct_of_allowance"], est_aic / 500 * 100)

    def test_null_allowance_plan_without_pool_still_raises_keyerror(self):
        with self.assertRaises(KeyError) as cm:
            cp.plan_runway(
                FIXTURE, "planB", "S", "fake-cheap", cache_hit=0.8,
                today=date(2020, 1, 1),
            )
        msg = str(cm.exception)
        self.assertIn("planB", msg)
        self.assertIn("pool", msg.lower())

    def test_fixed_plan_with_pool_overrides_fixed_allowance(self):
        result = cp.plan_runway(
            FIXTURE, "planA", "S", "fake-cheap", cache_hit=0.8,
            today=date(2020, 1, 1), pool_aic=2000,
        )
        self.assertEqual(result["allowance_source"], "pool")
        self.assertEqual(result["allowance_aic"], 2000)

    def test_fixed_plan_without_pool_uses_plan_allowance_and_keeps_original_keys(self):
        result = cp.plan_runway(
            FIXTURE, "planA", "S", "fake-cheap", cache_hit=0.8,
            today=date(2020, 1, 1),
        )
        self.assertEqual(result["allowance_source"], "plan")
        self.assertEqual(result["allowance_aic"], 1000)
        for key in ("est_aic_per_task", "tasks_per_month", "pct_of_allowance"):
            self.assertIn(key, result)

    def test_pool_must_be_a_positive_number(self):
        for bad_pool in (0, -5):
            with self.assertRaises(ValueError):
                cp.plan_runway(
                    FIXTURE, "planA", "S", "fake-cheap", cache_hit=0.8,
                    today=date(2020, 1, 1), pool_aic=bad_pool,
                )

    def test_unknown_plan_with_pool_still_raises_keyerror(self):
        # A pool never legitimizes a bad plan id.
        with self.assertRaises(KeyError):
            cp.plan_runway(
                FIXTURE, "not-a-real-plan", "S", "fake-cheap", cache_hit=0.8,
                today=date(2020, 1, 1), pool_aic=500,
            )

    def test_cli_pool_json_reports_allowance_source_and_value(self):
        with mock.patch.object(cp, "load_pricing", return_value=FIXTURE):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cp.main(
                    ["runway", "planB", "S", "fake-cheap", "--pool-aic", "500", "--json"]
                )
            out = json.loads(buf.getvalue())
            self.assertEqual(out["allowance_source"], "pool")
            self.assertEqual(out["allowance_aic"], 500)

    def test_cli_no_pool_on_null_allowance_plan_exits_2_mentioning_pool(self):
        with mock.patch.object(cp, "load_pricing", return_value=FIXTURE):
            err = io.StringIO()
            with self.assertRaises(SystemExit) as cm:
                with contextlib.redirect_stderr(err):
                    cp.main(["runway", "planB", "S", "fake-cheap", "--json"])
            self.assertEqual(cm.exception.code, 2)
            self.assertIn("pool", err.getvalue().lower())


class UnknownKeyTests(unittest.TestCase):
    def test_unknown_model_id_raises_keyerror_listing_choices(self):
        with self.assertRaises(KeyError) as cm:
            cp.est_cost(FIXTURE, "S", "not-a-real-model", today=date(2020, 1, 1))
        msg = str(cm.exception)
        self.assertIn("valid choices", msg)
        for model_id in FIXTURE["models"]:
            self.assertIn(model_id, msg)

    def test_unknown_profile_raises_keyerror_listing_choices(self):
        with self.assertRaises(KeyError) as cm:
            cp.est_cost(FIXTURE, "not-a-real-profile", "fake-cheap", today=date(2020, 1, 1))
        msg = str(cm.exception)
        self.assertIn("valid choices", msg)
        for profile_id in FIXTURE["task_profiles"]:
            self.assertIn(profile_id, msg)


class ModelsTableTests(unittest.TestCase):
    def test_preserves_file_order(self):
        rows = cp.models_table(FIXTURE, today=date(2020, 1, 1))
        self.assertEqual([r["id"] for r in rows], list(FIXTURE["models"]))

    def test_no_est_columns_without_profile(self):
        rows = cp.models_table(FIXTURE, today=date(2020, 1, 1))
        for row in rows:
            self.assertNotIn("est_usd", row)
            self.assertNotIn("est_aic", row)

    def test_est_columns_present_and_correct_with_profile(self):
        rows = cp.models_table(
            FIXTURE, profile="S", cache_hit=0.8, today=date(2020, 1, 1)
        )
        row = next(r for r in rows if r["id"] == "fake-cheap")
        self.assertIn("est_usd", row)
        self.assertIn("est_aic", row)
        self.assertAlmostEqual(row["est_usd"], 0.0048)
        self.assertAlmostEqual(row["est_aic"], 0.0096)


class KnobsCmdTests(unittest.TestCase):
    """cp.cmd_knobs via cp.main(["knobs", ...]) -- synthetic fixtures plus one live smoke."""

    def test_knobs_prints_efforts_and_notes(self):
        fixture = copy.deepcopy(FIXTURE)
        fixture["knobs"] = {
            "reasoning_efforts": ["Alpha", "Beta"],
            "reasoning_efforts_note": "fake note",
        }
        with mock.patch.object(cp, "load_pricing", return_value=fixture):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cp.main(["knobs"])
            out = buf.getvalue()
            self.assertIn("Alpha | Beta", out)
            self.assertIn("fake note", out)

    def test_knobs_absent_is_honest_and_exit_0(self):
        fixture = copy.deepcopy(FIXTURE)
        self.assertNotIn("knobs", fixture)
        with mock.patch.object(cp, "load_pricing", return_value=fixture):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cp.main(["knobs"])
            out = buf.getvalue()
            self.assertIn("no knobs recorded", out)

    def test_knobs_json_round_trips(self):
        fixture = copy.deepcopy(FIXTURE)
        fixture["knobs"] = {
            "reasoning_efforts": ["Alpha", "Beta"],
            "reasoning_efforts_note": "fake note",
        }
        with mock.patch.object(cp, "load_pricing", return_value=fixture):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cp.main(["knobs", "--json"])
            out = json.loads(buf.getvalue())
            self.assertEqual(out, fixture["knobs"])

    def test_knobs_real_file_smoke(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cp.main(["knobs"])
        out = buf.getvalue()
        self.assertIn("Extra High", out)
        self.assertIn("unconfirmed", out.lower())


class LiveDataStructureTests(unittest.TestCase):
    """Structural validation of the REAL data/pricing.copilot.json.

    No price/credit/allowance literals are asserted here -- only shape, types,
    positivity, and vocabulary membership.
    """

    def test_required_top_level_keys_present(self):
        pricing = cp.load_pricing()
        for key in ("cached_date", "billing_unit", "plans", "models", "task_profiles"):
            self.assertIn(key, pricing)

    def test_every_model_has_required_positive_fields(self):
        pricing = cp.load_pricing()
        valid_tiers = {"frontier", "strong", "mid", "cheap"}
        for model_id, info in pricing["models"].items():
            self.assertIn("display", info, model_id)
            self.assertIn("vendor", info, model_id)
            self.assertIn(info.get("tier"), valid_tiers, model_id)
            self.assertGreater(info["input_per_mtok"], 0, model_id)
            self.assertGreater(info["cached_input_per_mtok"], 0, model_id)
            self.assertGreater(info["output_per_mtok"], 0, model_id)
            if "long_context" in info:
                self.assertGreater(info["long_context"]["threshold_tokens"], 0, model_id)

    def test_task_profiles_are_exactly_xs_s_m_l_xl(self):
        pricing = cp.load_pricing()
        self.assertEqual(set(pricing["task_profiles"]), {"XS", "S", "M", "L", "XL"})


class CliSmokeTests(unittest.TestCase):
    def test_models_json_against_real_pricing_parses(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cp.main(["models", "--json"])
        rows = json.loads(buf.getvalue())
        self.assertIsInstance(rows, list)
        real_pricing = cp.load_pricing()
        self.assertEqual([r["id"] for r in rows], list(real_pricing["models"]))


class PrefsCmdTests(unittest.TestCase):
    """cp.cmd_prefs via cp.main(["prefs", ...]) -- FIXTURE has NO frontier-tier model, the
    honesty case for an unresolvable tier. Every invocation passes --prefs <temp path> or
    --no-prefs -- never the real default prefs/copilot.json path.
    """

    def test_no_file_reports_absence_and_file_order_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefs_path = Path(tmp) / "copilot.json"
            with mock.patch.object(cp, "load_pricing", return_value=copy.deepcopy(FIXTURE)):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    cp.main(["prefs", "--prefs", str(prefs_path)])
                out = buf.getvalue()

            self.assertIn("source: (no prefs file)", out)
            self.assertIn("pins: (none)", out)
            self.assertIn("cheap", out)
            self.assertIn("fake-cheap", out)
            self.assertIn("fake-promo", out)
            self.assertIn("fake-strong-lc", out)
            self.assertIn("(none — no non-excluded model carries this tier)", out)

    def test_file_pin_marked_pinned_with_cross_tier_annotation_and_stale_tier_unresolvable(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefs_path = Path(tmp) / "copilot.json"
            prefs_path.write_text(json.dumps({
                "schema_version": 1,
                "pins": {"mid": "fake-cheap"},
                "excludes": ["fake-strong-lc"],
            }))
            with mock.patch.object(cp, "load_pricing", return_value=copy.deepcopy(FIXTURE)):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    cp.main(["prefs", "--prefs", str(prefs_path)])
                out = buf.getvalue()

            mid_line = next(line for line in out.splitlines() if line.strip().startswith("mid"))
            self.assertIn("fake-cheap", mid_line)
            self.assertIn("(pinned)", mid_line)
            self.assertIn("model's own tier: cheap", mid_line)

            strong_line = next(
                line for line in out.splitlines() if line.strip().startswith("strong")
            )
            self.assertIn("(none — no non-excluded model carries this tier)", strong_line)

    def test_flag_pin_over_file_conflicts_with_file_exclude_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefs_path = Path(tmp) / "copilot.json"
            prefs_path.write_text(json.dumps({
                "pins": {"mid": "fake-cheap"},
                "excludes": ["fake-strong-lc"],
            }))
            with mock.patch.object(cp, "load_pricing", return_value=copy.deepcopy(FIXTURE)):
                err = io.StringIO()
                with self.assertRaises(SystemExit) as cm:
                    with contextlib.redirect_stderr(err):
                        cp.main([
                            "prefs", "--prefs", str(prefs_path),
                            "--pin", "mid=fake-strong-lc",
                        ])
                self.assertEqual(cm.exception.code, 2)
                self.assertIn("conflicts with exclude", err.getvalue())

    def test_flag_pin_replaces_only_its_tier_other_file_pin_survives(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefs_path = Path(tmp) / "copilot.json"
            prefs_path.write_text(json.dumps({
                "pins": {"mid": "fake-promo", "cheap": "fake-cheap"},
            }))
            with mock.patch.object(cp, "load_pricing", return_value=copy.deepcopy(FIXTURE)):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    cp.main([
                        "prefs", "--prefs", str(prefs_path), "--pin", "mid=fake-cheap", "--json",
                    ])
                out = json.loads(buf.getvalue())

            self.assertEqual(out["pins"]["mid"], "fake-cheap")
            self.assertEqual(out["pins"]["cheap"], "fake-cheap")

    def test_malformed_file_notes_malformed_and_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefs_path = Path(tmp) / "copilot.json"
            prefs_path.write_text("{not valid json")
            with mock.patch.object(cp, "load_pricing", return_value=copy.deepcopy(FIXTURE)):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    cp.main(["prefs", "--prefs", str(prefs_path)])
                out = buf.getvalue()

            self.assertIn("malformed", out)
            self.assertIn("pins: (none)", out)
            self.assertIn("fake-cheap", out)

    def test_no_prefs_with_populated_file_ignores_it_and_uses_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefs_path = Path(tmp) / "copilot.json"
            prefs_path.write_text(json.dumps({"pins": {"mid": "fake-cheap"}}))
            with mock.patch.object(cp, "load_pricing", return_value=copy.deepcopy(FIXTURE)):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    cp.main(["prefs", "--prefs", str(prefs_path), "--no-prefs"])
                out = buf.getvalue()

            self.assertIn("source: (prefs file ignored: --no-prefs)", out)
            self.assertIn("pins: (none)", out)
            self.assertIn("fake-promo", out)

    def test_json_has_exactly_six_keys_and_null_frontier(self):
        with mock.patch.object(cp, "load_pricing", return_value=copy.deepcopy(FIXTURE)):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cp.main(["prefs", "--no-prefs", "--json"])
            out = json.loads(buf.getvalue())

        self.assertEqual(
            set(out), {"source", "pins", "excludes", "resolved", "resolved_via", "notes"}
        )
        self.assertIsNone(out["resolved"]["frontier"])


if __name__ == "__main__":
    unittest.main()
