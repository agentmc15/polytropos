"""Stdlib unittest regression suite for bin/copilot_ralph.py.

bin/ is not a package; copilot_ralph.py is loaded via importlib by absolute path computed
from this file's own location, per PLAN.md D2 (same convention as
tests/test_copilot_pricing.py and tests/test_harness_select.py).

============================ AI-CREDIT / NETWORK SAFETY CONTRACT ============================
This file NEVER invokes the real `copilot` CLI. Every engine-level test (`run_ralph`,
`parse_cost`, `tick_estimate`, `runway_ticks`, `PROFILES`) drives the module through
INJECTED callables (`run_tick` / `run_verify` fakes, `unittest.mock.Mock`) -- it never
constructs or shells out to a real command. The one CLI-level test class patches the
module's own `subprocess.run` to RAISE `AssertionError` for the whole test, then proves
`main(["--demo"])` and `main(["--dry-run", ...])` complete successfully anyway -- i.e. that
neither safe path spawns any subprocess at all, let alone the real `copilot` binary. No test
in this file touches the network. Every write goes through a `tempfile.TemporaryDirectory()`
or `tempfile.mkstemp()`; nothing is written outside a temp dir.
===============================================================================================

All pricing numbers used here are a synthetic fixture (deliberately fake, round numbers) so
this file never needs updating when data/pricing.copilot.json's real prices change, and so
nothing here could be mistaken for a real price. The fixture's billing_unit.usd_per_credit is
0.5 -- NOT the real AIC rate -- to prove the USD<->AIC conversion is derived from the pricing
dict at run time, never hardcoded. The one place this file touches the real
data/pricing.copilot.json is the CLI safety-smoke test, and only to read the first model id
(structure, not a price) needed to exercise --dry-run without inventing a fake id that might
not round-trip through the real loader.
"""

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cr = _load("copilot_ralph")


# ---- synthetic fixture ----------------------------------------------------------------------
#
# Deliberately fake, round numbers.
#   - billing_unit.usd_per_credit = 0.5 (real value is nowhere near this).
#   - "fake-cheap": plain cheap-tier model, input 1.0 / cached 0.1 / output 2.0 per MTok.
#   - task_profiles["T"]: 100000 in / 10000 out (the brief's example tick profile).

FIXTURE_PRICING = {
    "cached_date": "2020-01-01",
    "billing_unit": {
        "name": "AIC",
        "usd_per_credit": 0.5,
        "note": "Fixture unit -- deliberately not the real rate.",
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
    },
    "task_profiles": {
        "T": {
            "label": "Fixture tick profile",
            "input_tokens": 100000,
            "output_tokens": 10000,
        },
    },
}


class ParseCostTests(unittest.TestCase):
    """Port of aesop@5506617 ralph.ts parseCost -- see cr.parse_cost's own docstring."""

    def test_none_on_plain_text(self):
        output = "just some ordinary log output\nno JSON here at all\n"
        self.assertIsNone(cr.parse_cost(output))

    def test_picks_up_cost_usd_line(self):
        output = "some log line\n" + json.dumps({"cost_usd": 1.5}) + "\nmore log\n"
        self.assertEqual(cr.parse_cost(output), 1.5)

    def test_picks_up_total_cost_usd_line(self):
        output = "some log line\n" + json.dumps({"total_cost_usd": 2.5}) + "\n"
        self.assertEqual(cr.parse_cost(output), 2.5)

    def test_total_cost_usd_preferred_within_one_line(self):
        line = json.dumps({"cost_usd": 1.5, "total_cost_usd": 2.5})
        self.assertEqual(cr.parse_cost(line), 2.5)

    def test_last_cost_bearing_line_wins_across_output(self):
        output = "\n".join(
            [
                json.dumps({"cost_usd": 1.0}),
                "irrelevant line",
                json.dumps({"total_cost_usd": 9.9}),
                json.dumps({"cost_usd": 0.1}),
            ]
        )
        self.assertEqual(cr.parse_cost(output), 0.1)

    def test_malformed_brace_lines_are_skipped(self):
        output = "\n".join(
            [
                "{not valid json at all",
                json.dumps({"cost_usd": 3.3}),
                "{also broken",
            ]
        )
        self.assertEqual(cr.parse_cost(output), 3.3)


class VerifyFirstShortCircuitTests(unittest.TestCase):
    def test_verify_passing_before_any_tick_spends_nothing(self):
        run_tick = mock.Mock(side_effect=AssertionError("run_tick must never be called"))
        run_verify = mock.Mock(return_value=(0, "ok"))
        stops = {"max_iterations": 20, "no_progress_stop": 2, "budget_usd": 5.0}

        result = cr.run_ralph(
            goal="already done",
            run_tick=run_tick,
            run_verify=run_verify,
            stops=stops,
            est_per_tick_usd=1.0,
        )

        self.assertEqual(result, {"status": "verified", "iterations": 0, "cost_usd": 0.0})
        run_tick.assert_not_called()


class BudgetStopTests(unittest.TestCase):
    def test_budget_trips_on_known_tick_with_hand_computed_cost(self):
        # run_verify always fails; run_tick emits no cost JSON, so every tick accrues the
        # estimate (2.0). budget_usd=5.0 -> tick1 cost=2.0 (<5), tick2 cost=4.0 (<5),
        # tick3 cost=6.0 (>=5) -> stop "budget" at iteration 3, cost_usd=6.0.
        # no_progress_stop is set well above 3 so the identical verify output never
        # preempts the budget stop.
        run_tick = mock.Mock(return_value="no cost line in this tick output")
        run_verify = mock.Mock(return_value=(1, "still failing"))
        stops = {"max_iterations": 10, "no_progress_stop": 10, "budget_usd": 5.0}

        result = cr.run_ralph(
            goal="g",
            run_tick=run_tick,
            run_verify=run_verify,
            stops=stops,
            est_per_tick_usd=2.0,
        )

        self.assertEqual(result["status"], "budget")
        self.assertEqual(result["iterations"], 3)
        self.assertAlmostEqual(result["cost_usd"], 6.0)


class ParsedCostBeatsEstimateTests(unittest.TestCase):
    def test_parsed_cost_line_wins_over_estimate(self):
        run_tick = mock.Mock(
            return_value=json.dumps({"total_cost_usd": 3.3}) + "\nrest of tick output\n"
        )
        # verify: fails pre-loop, then passes right after the one tick.
        run_verify = mock.Mock(side_effect=[(1, "pending"), (0, "done")])
        stops = {"max_iterations": 10, "no_progress_stop": 10, "budget_usd": 1000.0}

        result = cr.run_ralph(
            goal="g",
            run_tick=run_tick,
            run_verify=run_verify,
            stops=stops,
            est_per_tick_usd=100.0,  # deliberately far from the parsed 3.3
        )

        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["iterations"], 1)
        self.assertAlmostEqual(result["cost_usd"], 3.3)


class NoProgressStopTests(unittest.TestCase):
    def test_identical_verify_output_halts_after_exactly_no_progress_stop_ticks(self):
        run_tick = mock.Mock(return_value="tick output, no cost line")
        run_verify = mock.Mock(return_value=(1, "same output every time"))
        stops = {"max_iterations": 10, "no_progress_stop": 3, "budget_usd": 1000.0}

        result = cr.run_ralph(
            goal="g",
            run_tick=run_tick,
            run_verify=run_verify,
            stops=stops,
            est_per_tick_usd=0.01,
        )

        self.assertEqual(result["status"], "no_progress")
        self.assertEqual(result["iterations"], 3)

    def test_changing_verify_output_never_trips_no_progress_and_reaches_max_iterations(self):
        run_tick = mock.Mock(return_value="tick output, no cost line")
        counter = {"n": 0}

        def changing_verify():
            counter["n"] += 1
            return (1, f"output embeds iteration counter {counter['n']}")

        stops = {"max_iterations": 5, "no_progress_stop": 3, "budget_usd": 1000.0}

        result = cr.run_ralph(
            goal="g",
            run_tick=run_tick,
            run_verify=changing_verify,
            stops=stops,
            est_per_tick_usd=0.01,
        )

        self.assertEqual(result["status"], "max_iterations")
        self.assertEqual(result["iterations"], 5)


class StopCheckOrderingTests(unittest.TestCase):
    def test_verified_and_budget_exceeded_in_same_tick_returns_verified(self):
        # Estimate (100.0) vastly exceeds the budget (0.01) on the very first tick, AND
        # verify passes right after that tick -- proves "verified" is checked before
        # "budget" (pinned semantics: verified -> budget -> no-progress).
        run_tick = mock.Mock(return_value="no cost line here")
        run_verify = mock.Mock(side_effect=[(1, "pending"), (0, "done")])
        stops = {"max_iterations": 10, "no_progress_stop": 10, "budget_usd": 0.01}

        result = cr.run_ralph(
            goal="g",
            run_tick=run_tick,
            run_verify=run_verify,
            stops=stops,
            est_per_tick_usd=100.0,
        )

        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["iterations"], 1)


class StateFileTests(unittest.TestCase):
    def test_each_tick_rewrites_valid_json_and_parents_are_auto_created(self):
        run_tick = mock.Mock(return_value="no cost line")
        run_verify = mock.Mock(side_effect=[(1, "pending"), (0, "done")])
        stops = {"max_iterations": 10, "no_progress_stop": 10, "budget_usd": 1000.0}

        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "nested" / "dirs" / "state.json"
            self.assertFalse(state_path.parent.exists())

            result = cr.run_ralph(
                goal="the goal",
                run_tick=run_tick,
                run_verify=run_verify,
                stops=stops,
                est_per_tick_usd=1.0,
                state_path=state_path,
            )

            self.assertTrue(state_path.exists())
            data = json.loads(state_path.read_text())
            self.assertEqual(
                set(data.keys()), {"goal", "iteration", "cost_usd", "verified"}
            )
            self.assertEqual(data["goal"], "the goal")
            self.assertEqual(data["iteration"], result["iterations"])
            self.assertAlmostEqual(data["cost_usd"], result["cost_usd"])
            self.assertEqual(data["verified"], True)


class TickEstimateTests(unittest.TestCase):
    def test_usd_matches_hand_computed_math_and_aic_is_usd_over_point_five(self):
        # fake-cheap: input 1.0 / cached 0.1 / output 2.0 per MTok; task_profiles["T"]:
        # 100000 in / 10000 out; cache_hit defaults to 0.8.
        # usd = 100000 * ((1-0.8)*1.0 + 0.8*0.1) / 1e6 + 10000/1e6*2.0
        #     = 100000 * 0.28 / 1e6 + 0.02 = 0.028 + 0.02 = 0.048
        # aic = usd / billing_unit.usd_per_credit (fixture's 0.5)
        est = cr.tick_estimate(FIXTURE_PRICING, "T", "fake-cheap")

        self.assertAlmostEqual(est["usd"], 0.048)
        self.assertAlmostEqual(est["aic"], est["usd"] / 0.5)
        self.assertAlmostEqual(est["aic"], 0.096)


class RunwayTicksTests(unittest.TestCase):
    def test_floor_behavior(self):
        # (10 - 0) / 3 = 3.333... -> floor 3
        self.assertEqual(cr.runway_ticks(10.0, 0.0, 3.0), 3)

    def test_never_negative_clamp(self):
        # spent already exceeds budget -> negative numerator clamps to 0.
        self.assertEqual(cr.runway_ticks(5.0, 10.0, 1.0), 0)


class ProfilesPinTests(unittest.TestCase):
    """PROFILES values are loop-knob pins from aesop@5506617 profiles/{token-lean,
    balanced,accuracy-max}.yaml `guardrails:` blocks -- NOT prices, so they are allowed to
    live as literals in code (see bin/copilot_ralph.py's own comment citing the commit)."""

    def test_exactly_three_profiles_with_exactly_the_three_fields(self):
        self.assertEqual(set(cr.PROFILES), {"token-lean", "balanced", "accuracy-max"})
        for name, profile in cr.PROFILES.items():
            self.assertEqual(
                set(profile.keys()),
                {"max_iterations", "no_progress_stop", "budget_usd"},
                name,
            )

    def test_values_match_the_aesop_5506617_pins(self):
        self.assertEqual(
            cr.PROFILES["token-lean"],
            {"max_iterations": 20, "no_progress_stop": 2, "budget_usd": 5.0},
        )
        self.assertEqual(
            cr.PROFILES["balanced"],
            {"max_iterations": 40, "no_progress_stop": 3, "budget_usd": 25.0},
        )
        self.assertEqual(
            cr.PROFILES["accuracy-max"],
            {"max_iterations": 80, "no_progress_stop": 4, "budget_usd": 100.0},
        )


class CliSafetySmokeTests(unittest.TestCase):
    """THE #1 RULE, proven at the CLI boundary: with the module's own subprocess.run
    patched to raise, both --demo and --dry-run must complete successfully -- i.e. neither
    path spawns a subprocess at all, let alone the real `copilot` binary."""

    def test_demo_and_dry_run_spawn_nothing(self):
        real_pricing = cr.copilot_pricing.load_pricing()
        first_model_id = next(iter(real_pricing["models"]))

        with mock.patch.object(
            cr.subprocess, "run", side_effect=AssertionError("a real subprocess was spawned")
        ):
            demo_buf = io.StringIO()
            with contextlib.redirect_stdout(demo_buf):
                demo_rc = cr.main(["--demo"])
            self.assertEqual(demo_rc, 0)
            self.assertIn("halt: verified", demo_buf.getvalue())

            dry_run_buf = io.StringIO()
            with contextlib.redirect_stdout(dry_run_buf):
                dry_run_rc = cr.main(
                    [
                        "--dry-run",
                        "--goal",
                        "g",
                        "--verify-cmd",
                        "true",
                        "--model",
                        first_model_id,
                    ]
                )
            self.assertEqual(dry_run_rc, 0)
            self.assertIn("tick argv:", dry_run_buf.getvalue())


if __name__ == "__main__":
    unittest.main()
