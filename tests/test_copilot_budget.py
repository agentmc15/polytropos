"""Stdlib unittest regression suite for `bin/copilot_execute.py`'s budget mode (`--budget`).

bin/ is not a package; copilot_execute.py (and copilot_prefs.py, where needed) are loaded via
importlib by absolute path computed from this file's own location, per the repo's
`BIN_DIR = Path(__file__).resolve().parent.parent / "bin"` convention (same pattern as
tests/test_copilot_execute.py).

============================================================================================
 SAFETY CONTRACT — read this before adding a test here
============================================================================================
No test in this file EVER invokes the real `copilot` binary or touches the real `~/.copilot`.
Every dispatch goes through one of two seams: an injected fake `runner`/`verify_runner`
callable (pure-function tests of `budget_demote`/`run_task`), or a synthetic STUB_BIN string
passed via `--copilot-bin` where a dry-run never spawns anything anyway. `Path.home()` is
never called anywhere in this file. Every `main()` invocation passes `--no-prefs` (never a
bare run that could read a real `prefs/copilot.json`) and dry-run tests additionally patch
`subprocess` in the loaded module to raise if touched, proving the negative. Live-roster
end-to-end tests patch `ce.load_pricing` to the synthetic fixture below so they never depend
on `data/pricing.copilot.json`'s real contents.

Fixture ids (`fake-cheap`, `fake-mid-a`, `fake-mid-b`, `fake-strong`, `fake-front`) and every
price in `BUDGET_PRICING_FIXTURE` are synthetic and never appear in `data/pricing.copilot.json`.
This fixture is richer than `tests/test_copilot_execute.py`'s `PRICING_FIXTURE` because
`copilot_pricing.est_cost` (wired in by T2) needs `cached_input_per_mtok`, `task_profiles`,
and `billing_unit` — T1 only needs `budget_demote`, but the fixture is shared forward.
"""

import contextlib
import importlib.util
import io
import re
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


ce = _load("copilot_execute")
cp = _load("copilot_pricing")


# ---- fixtures ---------------------------------------------------------------------------------

# A synthetic STUB executable "name" used wherever a copilot_bin value is required but no
# process is actually spawned. Deliberately not the real CLI's name.
STUB_BIN = "stub-cli"

BUDGET_PRICING_FIXTURE = {
    "billing_unit": {"usd_per_credit": 0.01},
    "task_profiles": {"M": {"label": "fixture profile", "input_tokens": 100000, "output_tokens": 10000}},
    "models": {
        "fake-cheap": {"tier": "cheap", "input_per_mtok": 1.0, "cached_input_per_mtok": 0.1, "output_per_mtok": 2.0},
        "fake-cheap-b": {"tier": "cheap", "input_per_mtok": 1.2, "cached_input_per_mtok": 0.12, "output_per_mtok": 2.4},
        "fake-mid-a": {"tier": "mid", "input_per_mtok": 3.0, "cached_input_per_mtok": 0.3, "output_per_mtok": 6.0},
        "fake-mid-b": {"tier": "mid", "input_per_mtok": 3.5, "cached_input_per_mtok": 0.35, "output_per_mtok": 7.0},
        "fake-strong": {"tier": "strong", "input_per_mtok": 8.0, "cached_input_per_mtok": 0.8, "output_per_mtok": 16.0},
        "fake-front": {"tier": "frontier", "input_per_mtok": 20.0, "cached_input_per_mtok": 2.0, "output_per_mtok": 40.0},
    },
}

# A single-task kit, pinned to `fake-mid-a`, for CLI-level (main()) tests.
TASKS_TEXT_FIXTURE = """# TASKS — budget fixture kit

## Phase 1 — Only phase

### T1 — Only fixture task
- status: pending
- model: fake-mid-a
- depends: (none)
- independent: yes

**Brief.** Fixture brief payload for budget-mode tests.

**Acceptance.** Fake acceptance text for T1.

**Verify.**
```bash
true
```
"""


def _write_kit(tmp_path, text):
    kit_dir = Path(tmp_path) / "kit"
    kit_dir.mkdir()
    (kit_dir / "TASKS.md").write_text(text)
    return kit_dir


def _task(**overrides):
    base = {
        "id": "T1",
        "title": "fixture task",
        "status": "pending",
        "model": "fake-mid-a",
        "depends": [],
        "independent": True,
        "brief": "fake brief payload for budget run_task tests",
        "verify": "true",
    }
    base.update(overrides)
    return base


# ---- 1. budget_demote ---------------------------------------------------------------------------

class BudgetDemoteTests(unittest.TestCase):
    def test_mid_demotes_to_cheap(self):
        binfo = ce.budget_demote(BUDGET_PRICING_FIXTURE, "fake-mid-a")
        self.assertTrue(binfo["demoted"])
        self.assertEqual(binfo["standard_model"], "fake-mid-a")
        self.assertEqual(binfo["standard_tier"], "mid")
        self.assertEqual(binfo["target_tier"], "cheap")
        self.assertEqual(binfo["dispatched_model"], "fake-cheap")

    def test_strong_demotes_to_first_in_file_order_mid(self):
        binfo = ce.budget_demote(BUDGET_PRICING_FIXTURE, "fake-strong")
        self.assertTrue(binfo["demoted"])
        self.assertEqual(binfo["target_tier"], "mid")
        self.assertEqual(binfo["dispatched_model"], "fake-mid-a")

    def test_frontier_demotes_to_strong(self):
        binfo = ce.budget_demote(BUDGET_PRICING_FIXTURE, "fake-front")
        self.assertTrue(binfo["demoted"])
        self.assertEqual(binfo["target_tier"], "strong")
        self.assertEqual(binfo["dispatched_model"], "fake-strong")

    def test_cheap_is_already_the_floor_no_op(self):
        binfo = ce.budget_demote(BUDGET_PRICING_FIXTURE, "fake-cheap")
        self.assertFalse(binfo["demoted"])
        self.assertIsNone(binfo["target_tier"])
        self.assertEqual(binfo["dispatched_model"], "fake-cheap")
        self.assertIn("floor", binfo["notes"][-1])

    def test_unknown_id_no_op_with_pinned_note_substring(self):
        binfo = ce.budget_demote(BUDGET_PRICING_FIXTURE, "not-a-real-model")
        self.assertFalse(binfo["demoted"])
        self.assertEqual(binfo["dispatched_model"], "not-a-real-model")
        self.assertIn(
            "cannot demote not-a-real-model — not a live pricing id; dispatching as pinned",
            binfo["notes"][-1],
        )

    def test_model_id_none_assumes_mid_and_demotes_to_cheap(self):
        binfo = ce.budget_demote(BUDGET_PRICING_FIXTURE, None)
        self.assertIsNone(binfo["standard_model"])
        self.assertEqual(binfo["standard_tier"], ce.DEFAULT_ESCALATION_START)
        self.assertTrue(binfo["demoted"])
        self.assertEqual(binfo["dispatched_model"], "fake-cheap")
        self.assertIn("standard tier assumed mid", binfo["notes"][0])

    def test_prefs_pin_on_target_tier_wins(self):
        # Pin points at a SECOND cheap-tier model (not first in file order) -- a genuine
        # demotion, distinct from `fake-mid-a`'s file-order default `fake-cheap`.
        prefs = {
            "pins": {"cheap": "fake-cheap-b"}, "excludes": [], "notes": [], "source": None,
        }
        binfo = ce.budget_demote(BUDGET_PRICING_FIXTURE, "fake-mid-a", prefs=prefs)
        self.assertTrue(binfo["demoted"])
        self.assertEqual(binfo["dispatched_model"], "fake-cheap-b")

    def test_cross_tier_pin_claiming_demotion_it_did_not_make(self):
        # A3 fix: a `cheap`-tier pin that actually resolves to a STRONG-tier model (own
        # recorded tier not below `mid`) must not be reported as a demotion -- dispatching
        # `fake-strong` in place of `fake-mid-a` is not cheaper, whatever the pin claims.
        prefs = {
            "pins": {"cheap": "fake-strong"}, "excludes": [], "notes": [], "source": None,
        }
        binfo = ce.budget_demote(BUDGET_PRICING_FIXTURE, "fake-mid-a", prefs=prefs)
        self.assertFalse(binfo["demoted"])
        self.assertEqual(binfo["dispatched_model"], "fake-mid-a")
        self.assertIn(
            "tier 'cheap' is pinned to fake-strong (tier strong) — not below mid; no demotion",
            binfo["notes"][-1],
        )

    def test_target_tier_emptied_by_excludes_means_no_demotion(self):
        prefs = {
            "pins": {}, "excludes": ["fake-cheap", "fake-cheap-b"], "notes": [], "source": None,
        }
        binfo = ce.budget_demote(BUDGET_PRICING_FIXTURE, "fake-mid-a", prefs=prefs)
        self.assertFalse(binfo["demoted"])
        self.assertEqual(binfo["dispatched_model"], "fake-mid-a")
        self.assertIn("never a two-rung jump", binfo["notes"][-1])


# ---- 2. budget-aware run_task ---------------------------------------------------------------

class BudgetRunTaskTests(unittest.TestCase):
    def test_budget_run_first_try_dispatches_demoted_model(self):
        task = _task()
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(return_value=(0, "ok"))

        result = ce.run_task(
            task, BUDGET_PRICING_FIXTURE, runner, verify_runner,
            copilot_bin=STUB_BIN, budget=True,
        )

        dispatched_argv = runner.call_args_list[0].args[0]
        self.assertIn("fake-cheap", dispatched_argv)
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["escalations"], [])
        self.assertTrue(result["budget"]["demoted"])

    def test_budget_run_escalates_to_standard_tier_first(self):
        task = _task()
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(side_effect=[(1, "bad"), (0, "ok")])

        result = ce.run_task(
            task, BUDGET_PRICING_FIXTURE, runner, verify_runner,
            copilot_bin=STUB_BIN, budget=True,
        )

        self.assertEqual(result["escalations"], ["fake-mid-a"])
        self.assertEqual(result["model_used"], "fake-mid-a")

    def test_b1_escalate_back_rung_is_the_pinned_model_not_first_in_tier_order(self):
        # B1 repro: the task pins `fake-mid-b`, a SECOND mid-tier model that is NOT first in
        # file order (`fake-mid-a` is). Under the pre-fix code, the escalation ladder was
        # computed from the DEMOTED model with `prefs=None`, which takes escalation_ladder's
        # prefs-free branch -- a pure file-order scan with no dedup set at all -- so the first
        # escalation rung lands on `fake-mid-a` (first in file order for `mid`), never on the
        # model the task actually pinned. The fix must escalate back to `fake-mid-b`.
        task = _task(model="fake-mid-b")
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(side_effect=[(1, "bad"), (0, "ok")])

        result = ce.run_task(
            task, BUDGET_PRICING_FIXTURE, runner, verify_runner,
            copilot_bin=STUB_BIN, budget=True,
        )

        self.assertEqual(result["escalations"], ["fake-mid-b"])
        self.assertEqual(result["model_used"], "fake-mid-b")

    def test_b1_budget_chain_length_never_exceeds_standard_plus_one(self):
        # PLAN D4's bound, proven for every pin in the fixture (plus the pin-less case):
        # budget's worst case is standard behavior plus exactly one cheap attempt. Both runs
        # exhaust their full ladder (verify always fails) so the comparison is apples-to-apples.
        for model_id in (None, "fake-cheap", "fake-mid-a", "fake-mid-b", "fake-strong", "fake-front"):
            with self.subTest(model_id=model_id):
                task = _task(model=model_id)
                always_fail = mock.Mock(return_value=(1, "bad"))

                standard_result = ce.run_task(
                    task, BUDGET_PRICING_FIXTURE, mock.Mock(return_value=None), always_fail,
                    copilot_bin=STUB_BIN, budget=False,
                )
                standard_len = 1 + len(standard_result["escalations"])

                budget_result = ce.run_task(
                    task, BUDGET_PRICING_FIXTURE, mock.Mock(return_value=None), always_fail,
                    copilot_bin=STUB_BIN, budget=True,
                )
                budget_len = 1 + len(budget_result["escalations"])

                self.assertLessEqual(budget_len, standard_len + 1)

    def test_b1_reviewer_repro_legal_cross_tier_pin_grows_chain_by_two_without_fix(self):
        # Reviewer's exact repro shape: a "legal" prefs pin sets a tier ABOVE the task's
        # standard tier to the task's OWN standard model id -- `resolve_tier` trusts a pin
        # blindly regardless of the pinned model's actual tier, so this is a legal prefs
        # config, not a malformed one. Under the pre-fix code, the escalation ladder was
        # computed from the DEMOTED model with a dedup set seeded ONLY from that demoted
        # model -- the standard model was absent from that set, so it (a) got wrongly
        # synthesized at the standard-tier rung via a file-order scan (a model OTHER than
        # the one actually pinned) AND (b) reappeared again, genuinely duplicated, at the
        # tier it was legally pinned to. Two extra dispatches, not one -- this is the
        # reviewer's concrete "standard = 2 dispatches, budget = 4" finding.
        prefs = {
            "pins": {"strong": "fake-mid-b"}, "excludes": [], "notes": [], "source": None,
        }
        task = _task(model="fake-mid-b")
        always_fail = mock.Mock(return_value=(1, "bad"))

        standard_result = ce.run_task(
            task, BUDGET_PRICING_FIXTURE, mock.Mock(return_value=None), always_fail,
            copilot_bin=STUB_BIN, prefs=prefs, budget=False,
        )
        budget_result = ce.run_task(
            task, BUDGET_PRICING_FIXTURE, mock.Mock(return_value=None), always_fail,
            copilot_bin=STUB_BIN, prefs=prefs, budget=True,
        )

        standard_len = 1 + len(standard_result["escalations"])
        budget_len = 1 + len(budget_result["escalations"])
        self.assertEqual(standard_len, 2)
        self.assertEqual(budget_len, 3)  # PLAN D4: standard + exactly one cheap attempt
        self.assertLessEqual(budget_len, standard_len + 1)
        # The first escalation rung must be the task's own pin, not a tier rescan.
        self.assertEqual(budget_result["escalations"][0], "fake-mid-b")


# ---- 3. byte-stability without --budget ------------------------------------------------------

class BudgetByteStabilityTests(unittest.TestCase):
    def test_run_task_result_keys_unchanged_default_and_explicit_false(self):
        task = _task()
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(return_value=(0, "ok"))
        expected_keys = {"id", "status", "model_used", "escalations", "verify_rc"}

        result_default = ce.run_task(
            task, BUDGET_PRICING_FIXTURE, runner, verify_runner, copilot_bin=STUB_BIN,
        )
        self.assertEqual(set(result_default.keys()), expected_keys)

        result_explicit = ce.run_task(
            task, BUDGET_PRICING_FIXTURE, runner, verify_runner, copilot_bin=STUB_BIN,
            budget=False,
        )
        self.assertEqual(set(result_explicit.keys()), expected_keys)

    def test_dry_run_without_budget_flag_prints_no_budget_line(self):
        # A8 fix: `--no-prefs` alone still routes through `effective_prefs`, which needs
        # `pricing` -- this test must not depend on the real `data/pricing.copilot.json`.
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, TASKS_TEXT_FIXTURE)

            with mock.patch.object(ce, "load_pricing", return_value=BUDGET_PRICING_FIXTURE):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    ce.main(
                        ["run", "--kit", str(kit_dir), "--task", "T1", "--dry-run", "--no-prefs"]
                    )
            output = buf.getvalue()
            for line in output.splitlines():
                self.assertFalse(line.startswith("budget:"))


# ---- 4. budget dry-run CLI ---------------------------------------------------------------------

class BudgetDryRunTests(unittest.TestCase):
    def test_budget_dry_run_prints_pinned_line_and_touches_nothing(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, TASKS_TEXT_FIXTURE)
            before = (kit_dir / "TASKS.md").read_bytes()

            with mock.patch.object(ce, "load_pricing", return_value=BUDGET_PRICING_FIXTURE), \
                 mock.patch.object(ce, "subprocess") as mock_subprocess:
                mock_subprocess.run.side_effect = AssertionError("subprocess in dry-run")
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    ce.main([
                        "run", "--kit", str(kit_dir), "--task", "T1",
                        "--dry-run", "--budget", "--no-prefs",
                    ])

            output = buf.getvalue()
            self.assertIn(
                "budget: demoted mid -> cheap — dispatching fake-cheap "
                "(standard: fake-mid-a)",
                output,
            )
            dispatch_lines = [ln for ln in output.splitlines() if ln.startswith("dispatch:")]
            self.assertTrue(dispatch_lines)
            self.assertIn("fake-cheap", dispatch_lines[0])

            after = (kit_dir / "TASKS.md").read_bytes()
            self.assertEqual(before, after)


# ---- 5. --budget-profile validation ------------------------------------------------------------

class BudgetProfileFlagTests(unittest.TestCase):
    def test_unknown_profile_exits_2_with_message(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, TASKS_TEXT_FIXTURE)

            with mock.patch.object(ce, "load_pricing", return_value=BUDGET_PRICING_FIXTURE):
                buf_out = io.StringIO()
                buf_err = io.StringIO()
                with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                    with self.assertRaises(SystemExit) as cm:
                        ce.main([
                            "run", "--kit", str(kit_dir), "--task", "T1",
                            "--dry-run", "--budget", "--budget-profile", "ZZ", "--no-prefs",
                        ])
                self.assertEqual(cm.exception.code, 2)
                self.assertIn("unknown task profile 'ZZ'", buf_err.getvalue())


# ---- 6. budget_report ---------------------------------------------------------------------------

class BudgetReportTests(unittest.TestCase):
    def test_est_cost_spot_check_fake_cheap_profile_m(self):
        # One hand-computed spot check, never hand-copied elsewhere in this class.
        self.assertAlmostEqual(
            cp.est_cost(BUDGET_PRICING_FIXTURE, "M", "fake-cheap")["usd"], 0.048, places=9
        )

    def test_first_try_budget_run_saves(self):
        binfo = ce.budget_demote(BUDGET_PRICING_FIXTURE, "fake-mid-a")
        expected_standard = cp.est_cost(BUDGET_PRICING_FIXTURE, "M", "fake-mid-a")
        expected_actual = cp.est_cost(BUDGET_PRICING_FIXTURE, "M", "fake-cheap")

        report = ce.budget_report(BUDGET_PRICING_FIXTURE, binfo, [], "M")

        self.assertTrue(report["priced"])
        self.assertAlmostEqual(report["standard_usd"], expected_standard["usd"])
        self.assertAlmostEqual(report["actual_usd"], expected_actual["usd"])
        self.assertGreater(report["delta_usd"], 0)
        line = ce._format_budget_report_line(report)
        self.assertIn("saved", line)
        self.assertIn("estimate — not a bill", line)

    def test_escalated_run_backfires(self):
        # Demoted mid->cheap, then escalates to the standard tier (fake-mid-a) -- two
        # dispatches priced against ONE standard dispatch, so the estimate goes negative.
        binfo = ce.budget_demote(BUDGET_PRICING_FIXTURE, "fake-mid-a")
        expected_standard = cp.est_cost(BUDGET_PRICING_FIXTURE, "M", "fake-mid-a")
        expected_cheap = cp.est_cost(BUDGET_PRICING_FIXTURE, "M", "fake-cheap")
        expected_mid = cp.est_cost(BUDGET_PRICING_FIXTURE, "M", "fake-mid-a")

        report = ce.budget_report(BUDGET_PRICING_FIXTURE, binfo, ["fake-mid-a"], "M")

        self.assertTrue(report["priced"])
        self.assertAlmostEqual(report["standard_usd"], expected_standard["usd"])
        self.assertAlmostEqual(
            report["actual_usd"], expected_cheap["usd"] + expected_mid["usd"]
        )
        self.assertLess(report["delta_usd"], 0)
        self.assertEqual(report["dispatches"], 2)
        line = ce._format_budget_report_line(report)
        self.assertIn("BACKFIRED", line)
        self.assertIn("not a bill", line)

    def test_no_demotion_when_target_tier_fully_excluded_is_not_counted(self):
        # T8 item 2: `binfo["demoted"]` is False here (the cheap tier is fully excluded), so
        # `budget_report` must short-circuit to "not counted" instead of trying to price a
        # None (agent-default) dispatch and risk mislabeling any escalation BACKFIRED.
        prefs = {"pins": {}, "excludes": ["fake-cheap", "fake-cheap-b"], "notes": [], "source": None}
        binfo = ce.budget_demote(BUDGET_PRICING_FIXTURE, None, prefs=prefs)
        self.assertFalse(binfo["demoted"])
        self.assertIsNone(binfo["dispatched_model"])  # pin-less task, no demotion resolved

        report = ce.budget_report(BUDGET_PRICING_FIXTURE, binfo, [], "M", prefs=prefs)

        self.assertFalse(report["priced"])
        self.assertTrue(report.get("not_counted"))
        line = ce._format_budget_report_line(report)
        self.assertNotIn("BACKFIRED", line)
        self.assertIn("not counted", line)

    def test_agent_default_chain_still_unpriced_with_pinned_reason_when_demoted(self):
        # Defensive coverage: IF a demoted run's chain ever carried a None (agent-default)
        # leg, budget_report must still degrade to `unpriced` with this reason instead of
        # crashing or fabricating a dollar figure. A real `budget_demote` result never
        # produces this combination (a resolved demotion candidate is always a concrete
        # pricing id), so this binfo is hand-built rather than produced by `budget_demote`.
        binfo = {
            "standard_model": "fake-mid-a", "standard_tier": "mid", "target_tier": "cheap",
            "dispatched_model": None, "demoted": True, "notes": [],
        }
        report = ce.budget_report(BUDGET_PRICING_FIXTURE, binfo, [], "M")
        self.assertFalse(report["priced"])
        self.assertFalse(report.get("not_counted"))
        self.assertEqual(
            report["reason"], "dispatched at agent default — model unknown to the driver"
        )
        line = ce._format_budget_report_line(report)
        self.assertIn("unpriced", line)
        self.assertIn("no dollars fabricated", line)

    def test_floor_pinned_escalating_run_prints_no_backfired(self):
        # T8 acceptance (item 2): a floor-pinned task that still needs escalation dispatches
        # the SAME chain standard would (no demotion happened), so it must never be priced --
        # and therefore never printed as BACKFIRED -- however many rungs it climbs. This test
        # FAILS if the `binfo["demoted"]` short-circuit is reverted: pre-fix, `budget_report`
        # would price fake-cheap+fake-mid-a+fake-strong against a single fake-cheap standard
        # dispatch and print BACKFIRED.
        binfo = ce.budget_demote(BUDGET_PRICING_FIXTURE, "fake-cheap")  # already at the floor
        self.assertFalse(binfo["demoted"])

        report = ce.budget_report(
            BUDGET_PRICING_FIXTURE, binfo, ["fake-mid-a", "fake-strong"], "M"
        )
        self.assertTrue(report.get("not_counted"))
        line = ce._format_budget_report_line(report)
        self.assertNotIn("BACKFIRED", line)

    def test_unknown_profile_at_report_time_is_unpriced_never_crashes(self):
        binfo = ce.budget_demote(BUDGET_PRICING_FIXTURE, "fake-mid-a")
        report = ce.budget_report(BUDGET_PRICING_FIXTURE, binfo, [], "ZZ")
        self.assertFalse(report["priced"])
        self.assertIn("unknown task profile", report["reason"])


# ---- 7. NOTES.md budget record --------------------------------------------------------------

BUDGET_NOTES_LINE_RE = re.compile(
    r"^- budget: standard=\S+ actual=\S+ profile=M "
    r"est_standard_usd=(\d+\.\d{4}|unpriced) est_actual_usd=(\d+\.\d{4}|unpriced) "
    r"delta_usd=([+-]\d+\.\d{4}|unpriced) status=\S+$"
)


class BudgetNotesTests(unittest.TestCase):
    def test_budget_run_writes_exactly_one_matching_budget_line(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, TASKS_TEXT_FIXTURE)

            stub_path = tmp / "stub-cli"
            log_path = tmp / "stub.log"
            stub_path.write_text("#!/bin/sh\necho \"$@\" >> \"{log}\"\nexit 0\n".format(log=log_path))
            stub_path.chmod(0o755)

            with mock.patch.object(ce, "load_pricing", return_value=BUDGET_PRICING_FIXTURE):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    ce.main([
                        "run", "--kit", str(kit_dir), "--task", "T1",
                        "--copilot-bin", str(stub_path), "--budget", "--no-prefs",
                    ])

            notes_text = (kit_dir / "NOTES.md").read_text()
            budget_lines = [
                ln for ln in notes_text.splitlines() if ln.startswith("- budget:")
            ]
            self.assertEqual(len(budget_lines), 1)
            self.assertRegex(budget_lines[0], BUDGET_NOTES_LINE_RE)

    def test_non_budget_run_has_no_budget_line(self):
        # A8 fix: same live-roster fence hole as the dry-run test above.
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, TASKS_TEXT_FIXTURE)

            stub_path = tmp / "stub-cli"
            log_path = tmp / "stub.log"
            stub_path.write_text("#!/bin/sh\necho \"$@\" >> \"{log}\"\nexit 0\n".format(log=log_path))
            stub_path.chmod(0o755)

            with mock.patch.object(ce, "load_pricing", return_value=BUDGET_PRICING_FIXTURE):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    ce.main([
                        "run", "--kit", str(kit_dir), "--task", "T1",
                        "--copilot-bin", str(stub_path), "--no-prefs",
                    ])

            notes_text = (kit_dir / "NOTES.md").read_text()
            self.assertNotIn("- budget:", notes_text)

    def test_budget_line_carries_task_status_a4(self):
        # A4 fix: the NOTES budget line must carry the task's own status as a seventh token,
        # so the ledger can tell a done saving from a blocked one.
        task = _task()
        result = {
            "id": "T1", "status": "done", "model_used": "fake-cheap", "escalations": [],
            "verify_rc": 0,
            "budget": {
                "standard_model": "fake-mid-a", "standard_tier": "mid", "target_tier": "cheap",
                "dispatched_model": "fake-cheap", "demoted": True,
                "notes": ["demoted mid -> cheap: fake-cheap"],
            },
            "budget_report": ce.budget_report(
                BUDGET_PRICING_FIXTURE,
                {
                    "standard_model": "fake-mid-a", "dispatched_model": "fake-cheap",
                    "demoted": True,
                },
                [], "M",
            ),
        }
        with tempfile.TemporaryDirectory() as tmp_s:
            notes_path = Path(tmp_s) / "NOTES.md"
            ce.append_note(notes_path, result, task)
            text = notes_path.read_text()
        self.assertRegex(
            [ln for ln in text.splitlines() if ln.startswith("- budget:")][0],
            BUDGET_NOTES_LINE_RE,
        )
        self.assertIn("status=done", text)

    def test_a5_agent_default_leg_rendered_in_place_not_dropped(self):
        # A5 fix: `append_note`'s dispatch_chain filter used to be `[m for m in (...) if m]`,
        # which silently DROPPED a `None` (agent-default) leg -- a three-dispatch chain with
        # an agent-default first leg was mis-rendered as a two-token chain. The fix renders
        # `None` in place as the literal `agent-default`.
        task = _task(model=None)
        result = {
            "id": "T1", "status": "done", "model_used": "fake-strong",
            "escalations": ["fake-mid-a", "fake-strong"], "verify_rc": 0,
            "budget": {
                "standard_model": None, "standard_tier": "mid", "target_tier": None,
                "dispatched_model": None, "demoted": False,
                "notes": ["tier 'cheap' resolves to nothing (empty or fully excluded) — no "
                          "demotion, never a two-rung jump"],
            },
            "budget_report": {"priced": False, "reason": "unpriced for this test", "profile": "M"},
        }
        with tempfile.TemporaryDirectory() as tmp_s:
            notes_path = Path(tmp_s) / "NOTES.md"
            ce.append_note(notes_path, result, task)
            text = notes_path.read_text()
        budget_line = [ln for ln in text.splitlines() if ln.startswith("- budget:")][0]
        self.assertIn("actual=agent-default+fake-mid-a+fake-strong", budget_line)

    def test_not_counted_report_writes_not_counted_delta_usd_never_backfired(self):
        # T8 item 2, end to end: a floor-pinned run's `budget_report` short-circuits to
        # `not_counted`, and `append_note` must render that as the literal `delta_usd=
        # not-counted` token (never a priced/BACKFIRED line) so `cmd_budget` can skip it.
        task = _task(model="fake-cheap")
        binfo = ce.budget_demote(BUDGET_PRICING_FIXTURE, "fake-cheap")
        self.assertFalse(binfo["demoted"])
        report = ce.budget_report(BUDGET_PRICING_FIXTURE, binfo, ["fake-mid-a"], "M")
        result = {
            "id": "T1", "status": "done", "model_used": "fake-mid-a",
            "escalations": ["fake-mid-a"], "verify_rc": 0,
            "budget": binfo, "budget_report": report,
        }
        with tempfile.TemporaryDirectory() as tmp_s:
            notes_path = Path(tmp_s) / "NOTES.md"
            ce.append_note(notes_path, result, task)
            text = notes_path.read_text()
        budget_line = [ln for ln in text.splitlines() if ln.startswith("- budget:")][0]
        self.assertIn("delta_usd=not-counted", budget_line)
        self.assertIn("est_standard_usd=not-counted", budget_line)
        self.assertIn("est_actual_usd=not-counted", budget_line)
        self.assertNotIn("BACKFIRED", text)


class BudgetAssumedMarkerTests(unittest.TestCase):
    """A6: pin the `assumed` marker on both surfaces that show it, plus the priced branch."""

    def test_append_note_standard_token_uses_assumed_marker_for_pinless_task(self):
        task = _task(model=None)
        result = {
            "id": "T1", "status": "done", "model_used": None, "escalations": [],
            "verify_rc": 0,
            "budget": {
                "standard_model": None, "standard_tier": "mid", "target_tier": "cheap",
                "dispatched_model": "fake-cheap", "demoted": True,
                "notes": ["task has no model pin — standard tier assumed mid (agent default)"],
            },
            "budget_report": {"priced": False, "reason": "test-only", "profile": "M"},
        }
        with tempfile.TemporaryDirectory() as tmp_s:
            notes_path = Path(tmp_s) / "NOTES.md"
            ce.append_note(notes_path, result, task)
            text = notes_path.read_text()
        self.assertIn("standard=assumed-mid", text)

    def test_format_budget_line_shows_assumed_tier_for_pinless_demotion(self):
        binfo = ce.budget_demote(BUDGET_PRICING_FIXTURE, None)
        line = ce._format_budget_line(binfo)
        self.assertIn(f"(standard: agent default (assumed {ce.DEFAULT_ESCALATION_START}))", line)

    def test_budget_report_priced_assumed_tier_branch(self):
        # Only the UNPRICED assumed-tier path had coverage before; this pins the PRICED one.
        binfo = ce.budget_demote(BUDGET_PRICING_FIXTURE, None)
        report = ce.budget_report(BUDGET_PRICING_FIXTURE, binfo, [], "M")
        self.assertTrue(report["priced"])
        self.assertEqual(report["standard_label"], "assumed-mid")


class BudgetReportExceptionGuardTests(unittest.TestCase):
    """A7: `cmd_run`'s cost-report exception guard must never change status/exit code."""

    def test_budget_report_exception_does_not_change_status_or_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, TASKS_TEXT_FIXTURE)

            stub_path = tmp / "stub-cli"
            stub_path.write_text("#!/bin/sh\nexit 0\n")
            stub_path.chmod(0o755)

            with mock.patch.object(ce, "load_pricing", return_value=BUDGET_PRICING_FIXTURE), \
                 mock.patch.object(ce, "budget_report", side_effect=RuntimeError("boom")):
                buf = io.StringIO()
                code = 0
                with contextlib.redirect_stdout(buf):
                    try:
                        ce.main([
                            "run", "--kit", str(kit_dir), "--task", "T1",
                            "--copilot-bin", str(stub_path), "--budget", "--no-prefs",
                        ])
                    except SystemExit as e:
                        code = e.code if e.code is not None else 0

            output = buf.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("task T1: done", output)
            self.assertIn("budget est.: unpriced — boom (no dollars fabricated)", output)

            tasks_text = (kit_dir / "TASKS.md").read_text()
            self.assertIn("- status: done", tasks_text)

            notes_text = (kit_dir / "NOTES.md").read_text()
            self.assertIn("est_standard_usd=unpriced est_actual_usd=unpriced", notes_text)


# ---- 8. `budget --kit` ledger subcommand -----------------------------------------------------

# Two priced rows (T1 saves, T2 backfires -> net +0.0480, SAVING), one unpriced row (T3), one
# malformed budget line (T4 -- missing actual/est_standard_usd/est_actual_usd), and one plain
# non-budget block (T5). All priced/unpriced rows carry status=done.
LEDGER_NOTES_MIXED = """## 2026-07-25T10:00:00Z — T1
- agent: implementer
- model used: fake-cheap
- escalations: (none)
- verify: exit 0
- budget: standard=fake-mid-a actual=fake-cheap profile=M est_standard_usd=0.1440 est_actual_usd=0.0480 delta_usd=+0.0960 status=done

## 2026-07-25T10:05:00Z — T2
- agent: implementer
- model used: fake-mid-a
- escalations: fake-mid-a
- verify: exit 0
- budget: standard=fake-mid-a actual=fake-cheap+fake-mid-a profile=M est_standard_usd=0.1440 est_actual_usd=0.1920 delta_usd=-0.0480 status=done

## 2026-07-25T10:10:00Z — T3
- agent: implementer
- model used: agent default
- escalations: (none)
- verify: exit 0
- budget: standard=assumed-mid actual=agent-default profile=M est_standard_usd=unpriced est_actual_usd=unpriced delta_usd=unpriced status=done

## 2026-07-25T10:15:00Z — T4
- agent: implementer
- model used: fake-strong
- escalations: (none)
- verify: exit 0
- budget: standard=fake-strong profile=M delta_usd=+0.0100 status=done

## 2026-07-25T10:20:00Z — T5
- agent: implementer
- model used: fake-strong
- escalations: (none)
- verify: exit 0
"""

# Two priced rows, net negative -> LOSING.
LEDGER_NOTES_LOSING = """## 2026-07-25T11:00:00Z — L1
- agent: implementer
- model used: fake-cheap
- escalations: fake-strong
- verify: exit 0
- budget: standard=fake-mid-a actual=fake-cheap+fake-strong profile=M est_standard_usd=0.1440 est_actual_usd=0.2000 delta_usd=-0.0560 status=done

## 2026-07-25T11:05:00Z — L2
- agent: implementer
- model used: fake-mid-a
- escalations: fake-mid-a
- verify: exit 0
- budget: standard=fake-mid-a actual=fake-cheap+fake-mid-a profile=M est_standard_usd=0.1440 est_actual_usd=0.1600 delta_usd=-0.0160 status=done
"""

# Two priced rows that cancel out exactly -> break-even.
LEDGER_NOTES_BREAK_EVEN = """## 2026-07-25T12:00:00Z — B1
- agent: implementer
- model used: fake-cheap
- escalations: (none)
- verify: exit 0
- budget: standard=fake-mid-a actual=fake-cheap profile=M est_standard_usd=0.1440 est_actual_usd=0.0940 delta_usd=+0.0500 status=done

## 2026-07-25T12:05:00Z — B2
- agent: implementer
- model used: fake-mid-a
- escalations: fake-mid-a
- verify: exit 0
- budget: standard=fake-mid-a actual=fake-cheap+fake-mid-a profile=M est_standard_usd=0.1440 est_actual_usd=0.1940 delta_usd=-0.0500 status=done
"""

# One unpriced row only -> no priced runs to total.
LEDGER_NOTES_NO_PRICED = """## 2026-07-25T13:00:00Z — U1
- agent: implementer
- model used: agent default
- escalations: (none)
- verify: exit 0
- budget: standard=assumed-mid actual=agent-default profile=M est_standard_usd=unpriced est_actual_usd=unpriced delta_usd=unpriced status=done
"""

# A recorded run block with no `- budget:` line at all (a non-budget run).
LEDGER_NOTES_NO_BUDGET_LINES = """## 2026-07-25T14:00:00Z — N1
- agent: implementer
- model used: fake-mid-a
- escalations: (none)
- verify: exit 0
"""

# A4: a BLOCKED run whose delta_usd is a large positive number -- it must never be credited
# with a saving. The only row here is not `done`, so the net must show zero priced runs and
# an explicit exclusion, never the (fabricated) saving this row's own delta_usd would imply.
LEDGER_NOTES_BLOCKED_EXCLUDED = """## 2026-07-25T15:00:00Z — X1
- agent: implementer
- model used: fake-cheap
- escalations: (none)
- verify: exit 1
- budget: standard=fake-mid-a actual=fake-cheap profile=M est_standard_usd=0.1440 est_actual_usd=0.0480 delta_usd=+0.0960 status=blocked
"""

# A4: one done/priced saving row plus one blocked row whose own delta_usd would otherwise
# inflate the net -- the blocked row must be excluded and the verdict must reflect ONLY the
# done row's saving.
LEDGER_NOTES_MIXED_STATUS = """## 2026-07-25T16:00:00Z — M1
- agent: implementer
- model used: fake-cheap
- escalations: (none)
- verify: exit 0
- budget: standard=fake-mid-a actual=fake-cheap profile=M est_standard_usd=0.1440 est_actual_usd=0.0480 delta_usd=+0.0960 status=done

## 2026-07-25T16:05:00Z — M2
- agent: implementer
- model used: fake-cheap
- escalations: (none)
- verify: exit 1
- budget: standard=fake-mid-a actual=fake-cheap profile=M est_standard_usd=0.1440 est_actual_usd=0.0480 delta_usd=+0.0960 status=blocked
"""

# T8 item 1 (BLOCKING): the exact repro from the review -- a done row that saved +$0.2340 and
# a blocked row that overspent -$1.8720. Old (A4-symmetric) behavior credited this kit with
# "SAVING money" because the blocked row's overspend vanished along with its status exclusion.
# The rows net -$1.6380: the combined verdict must say so, never a bare SAVING.
LEDGER_NOTES_DONE_SAVES_BLOCKED_OVERSPENDS = """## 2026-07-25T17:00:00Z — T1
- agent: implementer
- model used: fake-cheap
- escalations: (none)
- verify: exit 0
- budget: standard=fake-mid-a actual=fake-cheap profile=M est_standard_usd=0.3510 est_actual_usd=0.1170 delta_usd=+0.2340 status=done

## 2026-07-25T17:05:00Z — T2
- agent: implementer
- model used: fake-cheap
- escalations: fake-mid-a
- verify: exit 1
- budget: standard=fake-mid-a actual=fake-cheap profile=M est_standard_usd=0.3510 est_actual_usd=2.2230 delta_usd=-1.8720 status=blocked
"""

# T8 item 2: one done/priced row plus one `not-counted` row (no demotion happened). The
# not-counted row must be skipped from every total and counted on its own line, never folded
# into "unpriced" or "excluded".
LEDGER_NOTES_NOT_COUNTED = """## 2026-07-25T18:00:00Z — NC1
- agent: implementer
- model used: fake-cheap
- escalations: (none)
- verify: exit 0
- budget: standard=fake-mid-a actual=fake-cheap profile=M est_standard_usd=0.1440 est_actual_usd=0.0480 delta_usd=+0.0960 status=done

## 2026-07-25T18:05:00Z — NC2
- agent: implementer
- model used: fake-cheap
- escalations: fake-mid-a
- verify: exit 0
- budget: standard=fake-cheap actual=fake-cheap+fake-mid-a profile=M est_standard_usd=not-counted est_actual_usd=not-counted delta_usd=not-counted status=done
"""

# T9 item 2: the ONLY row is an unpriced BLOCKED run. Pre-T9 this reported "unpriced runs: 0"
# (the count only ever tallied `done` rows), which was simply false -- an unpriced blocked row
# was reported NOWHERE. It must also never fabricate a dollar figure on the excluded line.
LEDGER_NOTES_UNPRICED_BLOCKED_ONLY = """## 2026-07-25T19:00:00Z — P1
- agent: implementer
- model used: fake-cheap
- escalations: (none)
- verify: exit 1
- budget: standard=fake-mid-a actual=fake-cheap profile=M est_standard_usd=unpriced est_actual_usd=unpriced delta_usd=unpriced status=blocked
"""

# T9 acceptance: "A ledger with 2 excluded rows where 1 prices discloses `over 1 of 2 priced`."
LEDGER_NOTES_EXCLUDED_PARTIAL_PRICED = """## 2026-07-25T19:05:00Z — Q1
- agent: implementer
- model used: fake-cheap
- escalations: (none)
- verify: exit 1
- budget: standard=fake-mid-a actual=fake-cheap profile=M est_standard_usd=0.1440 est_actual_usd=0.0480 delta_usd=+0.0960 status=blocked

## 2026-07-25T19:10:00Z — Q2
- agent: implementer
- model used: fake-cheap
- escalations: (none)
- verify: exit 1
- budget: standard=fake-mid-a actual=fake-cheap profile=M est_standard_usd=unpriced est_actual_usd=unpriced delta_usd=unpriced status=blocked
"""

# T9 item 3: `done` rows net EXACTLY 0.0 (a saving row and an equal-and-opposite backfire row),
# plus a blocked row that overspent -$5. Pre-T9 the suppression guard was `total > 0`, which a
# `done` net of exactly 0.0 never satisfies, so this printed a bare "verdict: break-even" on a
# kit that actually lost $5 once the blocked run is counted.
LEDGER_NOTES_ZERO_DONE_BLOCKED_OVERSPEND = """## 2026-07-25T19:15:00Z — R1
- agent: implementer
- model used: fake-cheap
- escalations: (none)
- verify: exit 0
- budget: standard=fake-mid-a actual=fake-cheap profile=M est_standard_usd=1.0000 est_actual_usd=0.5000 delta_usd=+0.5000 status=done

## 2026-07-25T19:20:00Z — R2
- agent: implementer
- model used: fake-mid-a
- escalations: fake-mid-a
- verify: exit 0
- budget: standard=fake-mid-a actual=fake-cheap+fake-mid-a profile=M est_standard_usd=1.0000 est_actual_usd=1.5000 delta_usd=-0.5000 status=done

## 2026-07-25T19:25:00Z — R3
- agent: implementer
- model used: fake-cheap
- escalations: fake-mid-a
- verify: exit 1
- budget: standard=fake-mid-a actual=fake-cheap profile=M est_standard_usd=1.0000 est_actual_usd=6.0000 delta_usd=-5.0000 status=blocked
"""

# T9 item 4: a `done` row saves comfortably (net positive, unqualified SAVING territory), but
# the ONLY excluded (blocked) row is unpriced -- so `excluded_total` stays 0.0 and can never
# trip the T8 suppression guard, even though the blocked run's real cost is simply unknown. The
# verdict must say the figure is incomplete rather than an unqualified SAVING.
LEDGER_NOTES_SAVING_WITH_UNPRICED_EXCLUDED = """## 2026-07-25T19:30:00Z — S1
- agent: implementer
- model used: fake-cheap
- escalations: (none)
- verify: exit 0
- budget: standard=fake-mid-a actual=fake-cheap profile=M est_standard_usd=0.1440 est_actual_usd=0.0480 delta_usd=+0.0960 status=done

## 2026-07-25T19:35:00Z — S2
- agent: implementer
- model used: fake-cheap
- escalations: (none)
- verify: exit 1
- budget: standard=fake-mid-a actual=fake-cheap profile=M est_standard_usd=unpriced est_actual_usd=unpriced delta_usd=unpriced status=blocked
"""


def _write_notes_kit(tmp_path, notes_text):
    kit_dir = Path(tmp_path) / "kit"
    kit_dir.mkdir()
    (kit_dir / "NOTES.md").write_text(notes_text)
    return kit_dir


def _run_main_capturing(argv):
    """Run `ce.main(argv)`, capturing stdout and any `SystemExit` code (default 0)."""
    buf = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(buf):
        try:
            ce.main(argv)
        except SystemExit as e:
            code = e.code if e.code is not None else 0
    return code, buf.getvalue()


class BudgetLedgerTests(unittest.TestCase):
    def test_mixed_ledger_counts_totals_and_skips_malformed(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            kit_dir = _write_notes_kit(tmp_s, LEDGER_NOTES_MIXED)
            code, output = _run_main_capturing(["budget", "--kit", str(kit_dir)])

        self.assertEqual(code, 0)
        self.assertIn(
            "note: skipped malformed budget line: "
            "- budget: standard=fake-strong profile=M delta_usd=+0.0100",
            output,
        )
        self.assertIn(
            "T1  delta_usd=+0.0960  standard=fake-mid-a  actual=fake-cheap  status=done", output
        )
        self.assertIn(
            "T2  delta_usd=-0.0480  standard=fake-mid-a  actual=fake-cheap+fake-mid-a  "
            "status=done",
            output,
        )
        self.assertIn(
            "T3  delta_usd=unpriced  standard=assumed-mid  actual=agent-default  status=done",
            output,
        )
        self.assertNotIn("T4  delta_usd", output)
        self.assertNotIn("T5  delta_usd", output)
        # B2: the header caveat and every net-dollar line carry the honesty label.
        self.assertIn(
            "All figures are labeled estimates recorded at run time — not a bill.", output
        )
        # T9: all three `done` rows (T1, T2, T3) count toward the headline total's denominator
        # -- T3 is unpriced, so `done_n_priced` (2) < `done_n_total` (3) and `_render_money`
        # discloses the partial coverage rather than silently pretending completeness.
        self.assertIn(
            "priced runs: 2 — est. net $+0.0480 over 2 of 3 priced [estimates — not a bill]",
            output,
        )
        self.assertIn("unpriced runs: 1 (excluded from the total)", output)
        self.assertIn("verdict: budget mode is SAVING money on this kit", output)

    def test_losing_kit_prints_pinned_losing_verdict(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            kit_dir = _write_notes_kit(tmp_s, LEDGER_NOTES_LOSING)
            code, output = _run_main_capturing(["budget", "--kit", str(kit_dir)])
        self.assertEqual(code, 0)
        self.assertIn(
            "verdict: budget mode is LOSING money on this kit — consider dropping --budget",
            output,
        )

    def test_break_even_kit_prints_pinned_break_even_verdict(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            kit_dir = _write_notes_kit(tmp_s, LEDGER_NOTES_BREAK_EVEN)
            code, output = _run_main_capturing(["budget", "--kit", str(kit_dir)])
        self.assertEqual(code, 0)
        self.assertIn("verdict: break-even", output)

    def test_no_priced_runs_prints_pinned_verdict(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            kit_dir = _write_notes_kit(tmp_s, LEDGER_NOTES_NO_PRICED)
            code, output = _run_main_capturing(["budget", "--kit", str(kit_dir)])
        self.assertEqual(code, 0)
        self.assertIn(
            "verdict: no priced budget runs — nothing to total (unpriced runs: 1)", output
        )
        # B2 fix: zero priced rows must print NO net dollar figure at all -- no fabricated
        # `est. net $+0.0000`.
        self.assertIn("priced runs: 0 — no priced runs to total", output)
        self.assertNotIn("est. net $+0.0000", output)
        self.assertNotIn("est. net $", output)

    def test_blocked_run_is_excluded_from_net_never_credited_a4(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            kit_dir = _write_notes_kit(tmp_s, LEDGER_NOTES_BLOCKED_EXCLUDED)
            code, output = _run_main_capturing(["budget", "--kit", str(kit_dir)])
        self.assertEqual(code, 0)
        # A blocked run's own positive delta_usd must never enter the net or the verdict.
        self.assertIn("priced runs: 0 — no priced runs to total", output)
        self.assertIn("excluded runs: 1 (not done — X1)", output)
        self.assertIn(
            "verdict: no priced budget runs — nothing to total (unpriced runs: 0)", output
        )
        self.assertNotIn("SAVING", output)

    def test_mixed_status_net_reflects_only_done_rows_a4(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            kit_dir = _write_notes_kit(tmp_s, LEDGER_NOTES_MIXED_STATUS)
            code, output = _run_main_capturing(["budget", "--kit", str(kit_dir)])
        self.assertEqual(code, 0)
        self.assertIn(
            "priced runs: 1 — est. net $+0.0960 [estimates — not a bill]",
            output,
        )
        self.assertIn("excluded runs: 1 (not done — M2)", output)
        self.assertIn("verdict: budget mode is SAVING money on this kit", output)

    def test_blocked_overspend_suppresses_optimistic_saving_verdict_t8(self):
        # T8 item 1 (BLOCKING), the exact live repro: rows net -$1.6380 (a done row that
        # saved +$0.2340, a blocked row that overspent -$1.8720). Pre-fix (A4-symmetric
        # exclusion) this printed a bare "SAVING money on this kit" verdict because the
        # blocked row's overspend vanished along with its status exclusion -- the same class
        # of dishonesty A4 was written to remove, reintroduced from the other side. This test
        # FAILS if the combined-net suppression is reverted.
        with tempfile.TemporaryDirectory() as tmp_s:
            kit_dir = _write_notes_kit(tmp_s, LEDGER_NOTES_DONE_SAVES_BLOCKED_OVERSPENDS)
            code, output = _run_main_capturing(["budget", "--kit", str(kit_dir)])
        self.assertEqual(code, 0)
        self.assertNotIn("verdict: budget mode is SAVING money on this kit", output)
        self.assertIn(
            "priced runs: 1 — est. net $+0.2340 [estimates — not a bill]",
            output,
        )
        self.assertIn(
            "excluded runs: 1 (not done — T2); their recorded net: est. net $-1.8720 "
            "[estimates — not a bill]",
            output,
        )
        self.assertIn(
            "verdict: budget mode is SAVING on completed work but LOSING overall once "
            "blocked runs are counted — consider dropping --budget",
            output,
        )

    def test_not_counted_rows_skipped_from_every_total_t8(self):
        # T8 item 2: a `delta_usd=not-counted` row must never enter the priced net, the
        # unpriced count, or the excluded-rows net -- only its own dedicated count line.
        with tempfile.TemporaryDirectory() as tmp_s:
            kit_dir = _write_notes_kit(tmp_s, LEDGER_NOTES_NOT_COUNTED)
            code, output = _run_main_capturing(["budget", "--kit", str(kit_dir)])
        self.assertEqual(code, 0)
        self.assertIn(
            "priced runs: 1 — est. net $+0.0960 [estimates — not a bill]",
            output,
        )
        self.assertIn("unpriced runs: 0 (excluded from the total)", output)
        self.assertIn("not-counted runs: 1", output)
        self.assertNotIn("excluded runs", output)

    def test_absent_notes_file_exits_0_with_pinned_message(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            kit_dir = Path(tmp_s) / "kit"
            kit_dir.mkdir()
            code, output = _run_main_capturing(["budget", "--kit", str(kit_dir)])
        self.assertEqual(code, 0)
        self.assertIn(
            f"no NOTES.md under kit dir {kit_dir} — no budget runs recorded.", output
        )

    def test_no_budget_lines_exits_0_with_pinned_message(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            kit_dir = _write_notes_kit(tmp_s, LEDGER_NOTES_NO_BUDGET_LINES)
            code, output = _run_main_capturing(["budget", "--kit", str(kit_dir)])
        notes_path = kit_dir / "NOTES.md"
        self.assertEqual(code, 0)
        self.assertIn(
            f"no budget runs recorded in {notes_path} — nothing to report.", output
        )

    def test_budget_command_never_dispatches_writes_or_loads_pricing_or_prefs(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            kit_dir = _write_notes_kit(tmp_s, LEDGER_NOTES_MIXED)
            before = (kit_dir / "NOTES.md").read_bytes()

            with mock.patch.object(ce, "subprocess") as mock_subprocess, \
                 mock.patch.object(ce, "load_pricing") as mock_load_pricing, \
                 mock.patch.object(ce, "_load_prefs_module") as mock_load_prefs:
                mock_subprocess.run.side_effect = AssertionError("subprocess touched")
                mock_load_pricing.side_effect = AssertionError("pricing loaded")
                mock_load_prefs.side_effect = AssertionError("prefs loaded")
                code, _output = _run_main_capturing(["budget", "--kit", str(kit_dir)])

            self.assertEqual(code, 0)
            after = (kit_dir / "NOTES.md").read_bytes()
            self.assertEqual(before, after)

    # ---- T9: root-cause fix -- one money renderer that cannot fabricate a dollar ------------

    def test_t9_unpriced_blocked_only_row_prints_no_dollar_and_counts_as_unpriced(self):
        # T9 item 2 (the exact live repro): a lone unpriced BLOCKED row. Pre-fix this printed
        # "unpriced runs: 0" (the count only ever tallied `done` rows) -- simply false, and the
        # excluded line still tried to format a `$` figure from zero priced data. This test
        # FAILS if `_render_money` is bypassed on the excluded line, or if unpriced counting is
        # narrowed back to `done` rows only.
        with tempfile.TemporaryDirectory() as tmp_s:
            kit_dir = _write_notes_kit(tmp_s, LEDGER_NOTES_UNPRICED_BLOCKED_ONLY)
            code, output = _run_main_capturing(["budget", "--kit", str(kit_dir)])
        self.assertEqual(code, 0)
        self.assertNotIn("$", output)
        self.assertIn("unpriced runs: 1 (excluded from the total)", output)
        self.assertIn("priced runs: 0 — no priced runs to total", output)
        self.assertIn(
            "excluded runs: 1 (not done — P1); their recorded net: no priced runs to total",
            output,
        )

    def test_t9_excluded_rows_partial_priced_discloses_coverage(self):
        # T9 acceptance: "A ledger with 2 excluded rows where 1 prices discloses
        # `over 1 of 2 priced`." This test FAILS if the excluded line reverts to a bare
        # `${excluded_net:+.4f}` that hides the fact only half the excluded rows were priced.
        with tempfile.TemporaryDirectory() as tmp_s:
            kit_dir = _write_notes_kit(tmp_s, LEDGER_NOTES_EXCLUDED_PARTIAL_PRICED)
            code, output = _run_main_capturing(["budget", "--kit", str(kit_dir)])
        self.assertEqual(code, 0)
        self.assertIn("over 1 of 2 priced", output)
        self.assertIn(
            "excluded runs: 2 (not done — Q1, Q2); their recorded net: "
            "est. net $+0.0960 over 1 of 2 priced [estimates — not a bill]",
            output,
        )
        self.assertIn("unpriced runs: 1 (excluded from the total)", output)

    def test_t9_zero_done_net_with_blocked_overspend_is_not_a_bare_break_even(self):
        # T9 item 3, the exact acceptance repro: `done` rows net EXACTLY 0.0, plus a blocked
        # row that overspent $5. The old guard was `total > 0`, which 0.0 never satisfies, so
        # this printed a bare "verdict: break-even" on a kit that lost $5 overall. This test
        # FAILS if the guard is narrowed back from `>= 0` to `> 0`.
        with tempfile.TemporaryDirectory() as tmp_s:
            kit_dir = _write_notes_kit(tmp_s, LEDGER_NOTES_ZERO_DONE_BLOCKED_OVERSPEND)
            code, output = _run_main_capturing(["budget", "--kit", str(kit_dir)])
        self.assertEqual(code, 0)
        self.assertNotIn("verdict: break-even\n", output)
        self.assertFalse(output.rstrip("\n").endswith("verdict: break-even"))
        self.assertIn(
            "verdict: budget mode is break-even on completed work but LOSING overall once "
            "blocked runs are counted — consider dropping --budget",
            output,
        )

    def test_t9_verdict_qualified_when_excluded_row_is_unpriced(self):
        # T9 item 4: a `done` row saves comfortably and no `done` figure is negative, but the
        # ONLY excluded (blocked) row is unpriced, so `excluded_total` stays 0.0 and can never
        # trip the T8 suppression guard even though the blocked run's true cost is unknown. The
        # verdict must disclose that the overall figure is incomplete rather than print an
        # unqualified SAVING. This test FAILS if the qualifier suffix is removed.
        with tempfile.TemporaryDirectory() as tmp_s:
            kit_dir = _write_notes_kit(tmp_s, LEDGER_NOTES_SAVING_WITH_UNPRICED_EXCLUDED)
            code, output = _run_main_capturing(["budget", "--kit", str(kit_dir)])
        self.assertEqual(code, 0)
        self.assertIn(
            "verdict: budget mode is SAVING money on this kit "
            "(some blocked runs are unpriced — the overall figure is incomplete)",
            output,
        )

    def test_t9_verdict_unqualified_when_no_excluded_row_is_unpriced(self):
        # Negative control for the previous test: when every excluded row IS priced, no
        # qualifier is appended. This test FAILS if the qualifier is applied unconditionally.
        with tempfile.TemporaryDirectory() as tmp_s:
            kit_dir = _write_notes_kit(tmp_s, LEDGER_NOTES_MIXED_STATUS)
            code, output = _run_main_capturing(["budget", "--kit", str(kit_dir)])
        self.assertEqual(code, 0)
        lines = [ln for ln in output.splitlines() if ln.startswith("verdict:")]
        self.assertEqual(lines, ["verdict: budget mode is SAVING money on this kit"])


class RenderMoneyTests(unittest.TestCase):
    """Direct coverage of the T9 root-cause helper `_render_money` (bin/copilot_execute.py)."""

    def test_zero_priced_never_prints_a_dollar_figure(self):
        rendered = ce._render_money(123.4567, 0, 5)
        self.assertEqual(rendered, "no priced runs to total")
        self.assertNotIn("$", rendered)

    def test_zero_priced_ignores_the_total_value_entirely(self):
        # However `total` was computed, the n_priced==0 branch must win -- a stray non-zero
        # `total` (which should be structurally impossible upstream) must still never surface.
        self.assertEqual(ce._render_money(-999.0, 0, 0), "no priced runs to total")

    def test_fully_priced_renders_the_unqualified_estimate(self):
        self.assertEqual(
            ce._render_money(0.048, 2, 2), "est. net $+0.0480 [estimates — not a bill]"
        )
        self.assertEqual(
            ce._render_money(-1.872, 3, 3), "est. net $-1.8720 [estimates — not a bill]"
        )

    def test_partial_coverage_discloses_priced_of_total(self):
        self.assertEqual(
            ce._render_money(0.096, 1, 2),
            "est. net $+0.0960 over 1 of 2 priced [estimates — not a bill]",
        )


class MoneyRenderingInvariantTests(unittest.TestCase):
    """Structural guard for the T9 root-cause fix (see .claude/kits/copilot-budget-mode/NOTES.md).

    Three review rounds of that kit shipped the same defect -- a dollar figure rendered from
    zero priced data -- each time on the line written to fix the previous one, because each fix
    added a new money-printing path with its own accumulator starting at 0.0. T9 routed every
    dollar in ``cmd_budget`` through ``_render_money``, which refuses to emit currency when
    nothing was priced. That property was TRUE when T9 landed but nothing enforced it, so the
    next contributor could reintroduce the class by adding one f-string. These tests are the
    enforcement: they fail on a stray ``$`` rather than waiting for a fourth review to find it.
    """

    @staticmethod
    def _body(name):
        src = (BIN_DIR / "copilot_execute.py").read_text()
        m = re.search(r"\ndef " + re.escape(name) + r"\(.*?\n(?=\ndef |\Z)", src, re.S)
        assert m, f"function {name} not found in copilot_execute.py"
        return m.group(0)

    def test_cmd_budget_renders_no_currency_of_its_own(self):
        """Every dollar the ledger prints must come from _render_money."""
        body = self._body("cmd_budget")
        self.assertIn("_render_money(", body, "cmd_budget no longer uses the money renderer")
        self.assertEqual(
            body.count("$"), 0,
            "cmd_budget contains a '$' of its own — route it through _render_money instead; "
            "a bare accumulator defaulting to 0.0 is how the fabricated-zero defect recurred "
            "three times (NOTES.md, T9)",
        )

    def test_render_money_refuses_to_price_nothing(self):
        """The helper's contract, asserted directly: no priced rows means no number."""
        for total in (0.0, -0.0, 123.45, -999.0, float("inf")):
            with self.subTest(total=total):
                self.assertNotIn("$", ce._render_money(total, 0, 7))

    def test_report_line_guards_every_currency_site(self):
        """The run --budget path renders money too; its '$' sites must sit behind the
        not-counted and unpriced early returns, so an unpriced report can never print one."""
        body = self._body("_format_budget_report_line")
        first_dollar = body.index("$")
        for guard in ('if report.get("not_counted")', 'if not report["priced"]'):
            self.assertIn(guard, body, f"missing guard: {guard}")
            self.assertLess(
                body.index(guard), first_dollar,
                f"guard {guard!r} must precede every currency format string",
            )


if __name__ == "__main__":
    unittest.main()
