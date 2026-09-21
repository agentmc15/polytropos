"""D02 -- Legacy goldens for the decision-improvement-v1 kit.

`LegacyDecisionGoldenTests` freezes EXISTING behavior of `bin/kit_contract.py` (the one
authority for parsing/readiness/admission) and of the four native drivers' `run_task` recovery
loops, plus `bin/workflow_eval.py`'s pull-only routing-policy file, as they stand at this HEAD.
These are GOLDENS, not a specification: every assertion below describes what the code already
does, including two asymmetries across the drivers that are real and deliberate (see D01's
NOTES.md carry-forward) -- not something this task fixes or hides. If future work changes one
of these behaviors on purpose, the failing assertion here is the reviewable signal to update
the golden, not evidence the change was wrong.

============================================================================================
 SAFETY CONTRACT
============================================================================================
No test here ever invokes a real `claude`/`codex`/`copilot`/`cursor` binary or touches a real
`~/.claude`/`~/.codex`/`~/.copilot` home. Every dispatch goes through an injected fake
`runner`/`verify_runner` callable -- `run_task` is a pure function of its arguments in every
driver, so a `unittest.mock.Mock` in place of a subprocess call is the entire seam. The two
tests that read an actual TASKS.md/PLAN.md do so from a `tempfile.TemporaryDirectory()`
fixture, never a real kit. `bin/workflow_eval.py`'s module-level `DEFAULT_STORE_DIR`/
`DEFAULT_PREFS_DIR` constants resolve through `bin/runtime_data.py`, so this module's load is
deferred to `setUpModule` with `POLYTROPOS_DATA_HOME` pointed at a temp directory first --
never the real per-user data root. No test here passes `policy="adaptive"` or reads
`prefs/routing-policy.json`; the point of the "pull-only" goldens is that nothing here needs
to.

Pricing dicts below are synthetic (`fake-*` ids, round numbers) and never appear in any
`data/pricing*.json`; this mirrors the convention already used by `tests/test_claude_execute.py`,
`tests/test_copilot_execute.py`, and `tests/test_codex_execute.py`.
"""

import importlib.util
import os
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


# The four native drivers plus the one shared kit contract they all delegate parsing,
# readiness, and admission to. None of this touches a home directory or pricing file at
# import time (each PRICING_PATH constant is a Path, read only inside load_pricing()).
kc = _load("kit_contract")
claude = _load("claude_execute")
copilot = _load("copilot_execute")
cursor = _load("cursor_execute")
codex = _load("codex_execute")

# bin/workflow_eval.py's DEFAULT_STORE_DIR/DEFAULT_PREFS_DIR resolve through
# bin/runtime_data.py AT IMPORT TIME, so its load is deferred until POLYTROPOS_DATA_HOME
# points at a temp directory (setUpModule below) -- the same guard
# tests/test_codex_execute.py's setUpModule uses for the attempt ledger's default root.
_DATA_HOME = None
_DATA_HOME_PATCH = None
workflow_eval = None


def setUpModule():
    global _DATA_HOME, _DATA_HOME_PATCH, workflow_eval
    _DATA_HOME = tempfile.TemporaryDirectory(prefix="polytropos-test-data-")
    _DATA_HOME_PATCH = mock.patch.dict(os.environ, {"POLYTROPOS_DATA_HOME": _DATA_HOME.name})
    _DATA_HOME_PATCH.start()
    workflow_eval = _load("workflow_eval")


def tearDownModule():
    _DATA_HOME_PATCH.stop()
    _DATA_HOME.cleanup()


STUB_BIN = "stub-cli"  # never resolved off PATH; every runner here is a Mock

# ---- pricing fixtures ---------------------------------------------------------------------
# Each mirrors the shape its own driver's existing test suite already proves works, with one
# tier ("sonnet"/"mid") deliberately left EMPTY so a passing escalation assertion proves the
# skip-up rule is read from data, not hardcoded.

CLAUDE_PRICING = {
    "models": {
        "fake-haiku": {"tier": "haiku", "input_per_mtok": 1.0, "output_per_mtok": 2.0},
        "fake-opus-a": {"tier": "opus", "input_per_mtok": 8.0, "output_per_mtok": 16.0},
        "fake-opus-b": {"tier": "opus", "input_per_mtok": 9.0, "output_per_mtok": 18.0},
        "fake-frontier": {"tier": "frontier", "input_per_mtok": 20.0, "output_per_mtok": 40.0},
    },
}

COPILOT_PRICING = {
    "models": {
        "fake-cheap": {"tier": "cheap", "input_per_mtok": 1.0, "output_per_mtok": 2.0},
        "fake-mid-a": {"tier": "mid", "input_per_mtok": 3.0, "output_per_mtok": 6.0},
        "fake-strong": {"tier": "strong", "input_per_mtok": 8.0, "output_per_mtok": 16.0},
        "fake-front": {"tier": "frontier", "input_per_mtok": 20.0, "output_per_mtok": 40.0},
    },
}

# codex_execute.run_task routes through bin/codex_policy.py, which needs an
# `orchestration_policy` block (worker tiers, the reserved orchestrator, and which failure
# kinds unlock its evidence-gated recovery attempt) alongside the plain model roster.
CODEX_PRICING = {
    "knobs": {"reasoning_efforts": ["low", "medium", "high"]},
    "orchestration_policy": {
        "orchestrator_model": "fake-frontier",
        "orchestrator_tier": "frontier",
        "worker_tiers": ["cheap", "mid", "strong"],
        "default_worker_tier": "strong",
        "maximum_worker_tier": "strong",
        "verification_tier": "strong",
        "recovery_evidence_kinds": [
            "verify_failure", "integration_conflict", "lower_tier_correction_failed"
        ],
    },
    "models": {
        "fake-cheap": {"tier": "cheap", "input_per_mtok": 1.0, "output_per_mtok": 2.0},
        "fake-strong-a": {"tier": "strong", "input_per_mtok": 8.0, "output_per_mtok": 16.0},
        "fake-frontier": {"tier": "frontier", "input_per_mtok": 20.0, "output_per_mtok": 40.0},
    },
}


def _task(**overrides):
    base = {
        "id": "T1",
        "title": "fixture task",
        "status": "pending",
        "model": None,
        "depends": [],
        "independent": True,
        "brief": "fake brief payload for legacy golden tests",
        "verify": "true",
    }
    base.update(overrides)
    return base


def _dummy_task(task_id, status, depends=()):
    return {
        "id": task_id, "title": f"{task_id} title", "status": status, "model": None,
        "depends": list(depends), "independent": False, "brief": f"{task_id} brief",
        "verify": "true",
    }


TASKS_FIXTURE_TEXT = """# TASKS -- fixture kit

### T1 — First fixture task
- status: pending
- model: fake-model
- depends: (none)

**Brief.** First fixture brief text.

**Verify.**
```bash
true
```

### T2 — Second fixture task
- status: pending
- model: fake-model
- depends: T1

**Brief.** Second fixture brief text; depends on T1.

**Verify.**
```bash
true
```
"""


class LegacyDecisionGoldenTests(unittest.TestCase):

    # ---- A. kit_contract: the one authority for parsing, readiness, and admission ---------

    def test_all_drivers_delegate_parsing_and_readiness_to_the_one_kit_contract(self):
        """No driver keeps its own copy of parse/select: each loads bin/kit_contract.py (not
        a per-driver fork of it -- bin/ is not a package, so each driver's own `_kc()` loads
        the same file path by hand) and re-exports its names unchanged, rather than wrapping
        or shadowing them."""
        for driver in (claude, copilot, cursor, codex):
            self.assertEqual(Path(driver._kc().__file__).resolve(), Path(kc.__file__).resolve())
            self.assertIs(driver.parse_tasks, driver._kc().parse_tasks)
            self.assertIs(driver.select_task, driver._kc().select_task)
        for driver in (claude, copilot, codex):  # cursor uses budget_gate instead
            self.assertIs(driver.BudgetAdmission, driver._kc().BudgetAdmission)

    def test_explicit_selection_from_temp_tasks_file_refuses_unmet_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit_dir = Path(tmp) / "kit"
            kit_dir.mkdir()
            (kit_dir / "TASKS.md").write_text(TASKS_FIXTURE_TEXT)

            text = kc._read_tasks_text(kit_dir)
            tasks = kc.parse_tasks(text)
            self.assertEqual([t["id"] for t in tasks], ["T1", "T2"])
            self.assertEqual(tasks[1]["depends"], ["T1"])

            task, reason = kc.select_task(tasks, task_id="T2")
            self.assertIsNone(task)
            self.assertIn("T2 depends on T1", reason)
            self.assertIn("'pending'", reason)

            task, reason = kc.select_task(tasks, task_id="T1")
            self.assertIsNone(reason)
            self.assertEqual(task["id"], "T1")

    def test_readiness_refuses_a_task_already_done_without_rerun(self):
        tasks = [_dummy_task("T1", "done")]
        result = kc.readiness(tasks, task_id="T1")
        self.assertIsNone(result["task"])
        self.assertIn("already done", result["reason"])
        self.assertIn("--rerun", result["reason"])

    def test_readiness_refuses_a_stale_dependency_before_dispatch(self):
        tasks = [
            _dummy_task("T0", "done"),
            _dummy_task("T1", "done", depends=["T0"]),
            _dummy_task("T2", "pending", depends=["T1"]),
        ]
        freshness = {"T1": {"state": "stale", "changed": ["T0"]}}
        result = kc.readiness(tasks, task_id="T2", freshness=freshness)
        self.assertIsNone(result["task"])
        self.assertIn("T2 depends on T1", result["reason"])
        self.assertIn("stale", result["reason"])
        self.assertIn("refresh", result["reason"].lower())

    def test_readiness_automatic_selection_waits_on_a_blocked_dependency(self):
        tasks = [_dummy_task("T1", "blocked"), _dummy_task("T2", "pending", depends=["T1"])]
        result = kc.readiness(tasks)
        self.assertIsNone(result["task"])
        self.assertEqual(result["graph"]["state"], "waiting")
        self.assertIn("blocked: T1", result["reason"])

    def test_budget_admission_denies_when_the_kits_own_history_already_spent_the_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "PLAN.md"
            plan_path.write_text("autonomy: advisory\nbudget: max-dispatches=1\n")
            budget = kc.parse_plan_budget(plan_path.read_text())
            self.assertEqual(budget, {"max-dispatches": 1})

            admission = kc.BudgetAdmission(budget, used={"max-dispatches": 1})
            ok, reason = admission.check("initial")
            self.assertFalse(ok)
            self.assertIn("max-dispatches=1", reason)
            self.assertIn("already reached", reason)

            ok, _reason = admission.admit("initial")
            self.assertFalse(ok)
            self.assertEqual(admission.used["max-dispatches"], 1)  # a refusal grants nothing

    def test_budget_admission_caps_are_isolated_per_operation_kind(self):
        """max-escalations=0 refuses an escalation but not the initial attempt (T24 fix)."""
        admission = kc.BudgetAdmission({"max-escalations": 0})
        ok, _reason = admission.admit("initial")
        self.assertTrue(ok)
        ok, reason = admission.check("escalation")
        self.assertFalse(ok)
        self.assertIn("max-escalations=0", reason)

    # ---- B. workflow_eval: pull-only, absent active pointer is the legacy default ---------

    def test_only_codex_reaches_routing_policy_transitively(self):
        """D01's asymmetry: three drivers never touch routing_policy/codex_policy at all."""
        texts = {name: (BIN_DIR / f"{name}.py").read_text()
                 for name in ("claude_execute", "copilot_execute", "cursor_execute",
                              "codex_execute")}
        for name in ("claude_execute", "copilot_execute", "cursor_execute"):
            for needle in ("routing_policy", "codex_policy", "_sibling"):
                self.assertNotIn(needle, texts[name],
                                 f"{name} should not reach routing_policy/codex_policy")
        self.assertIn("codex_policy", texts["codex_execute"])

    def test_no_native_driver_reads_the_applied_routing_policy_file(self):
        for name in ("claude_execute", "copilot_execute", "cursor_execute", "codex_execute"):
            text = (BIN_DIR / f"{name}.py").read_text()
            self.assertNotIn("routing-policy.json", text)
            self.assertNotIn("read_policy", text)

    def test_workflow_eval_absent_policy_file_is_none_the_legacy_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(workflow_eval.read_policy(tmp))
            report = workflow_eval.policy_report(tmp)
            self.assertIsNone(report["policy"])
            self.assertEqual(report["consumption"], "pull-only")

    # ---- C. Claude driver: any dispatch failure stops before verify, whatever its class ----

    def test_claude_dispatch_failure_stops_before_verify_even_if_verify_would_pass(self):
        """Dispatch and verification are separate facts: a crashed process never reads done
        because the tree it left behind happens to already satisfy the check."""
        task = _task(model="fake-haiku")
        runner = mock.Mock(return_value=(1, "boom: the process crashed"))
        verify_runner = mock.Mock(return_value=(0, "would have passed"))

        result = claude.run_task(task, CLAUDE_PRICING, runner, verify_runner,
                                 claude_bin=STUB_BIN)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["failure"], "dispatch")
        self.assertIsNone(result["verify_rc"])
        self.assertEqual(result["escalations"], [])
        verify_runner.assert_not_called()
        self.assertEqual(runner.call_count, 1)

    def test_claude_escalates_tier_ladder_on_verify_failure_until_pass(self):
        task = _task(model="fake-haiku")
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(side_effect=[(1, "nope"), (0, "ok now")])

        result = claude.run_task(task, CLAUDE_PRICING, runner, verify_runner,
                                 claude_bin=STUB_BIN)

        self.assertEqual(result["status"], "done")
        # empty "sonnet" tier is skipped -- the next rung is opus, not a phantom sonnet model.
        self.assertEqual(result["escalations"], ["fake-opus-a"])
        self.assertEqual(result["model_used"], "fake-opus-a")
        self.assertEqual(runner.call_count, 2)

    def test_claude_ladder_exhausted_blocks_after_every_rung(self):
        task = _task(model="fake-haiku")
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(return_value=(1, "still failing"))

        result = claude.run_task(task, CLAUDE_PRICING, runner, verify_runner,
                                 claude_bin=STUB_BIN)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["escalations"], ["fake-opus-a", "fake-frontier"])
        self.assertEqual(runner.call_count, 3)

    def test_claude_max_escalations_truncates_ladder(self):
        task = _task(model="fake-haiku")
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(return_value=(1, "still failing"))

        result = claude.run_task(task, CLAUDE_PRICING, runner, verify_runner,
                                 claude_bin=STUB_BIN, max_escalations=1)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["escalations"], ["fake-opus-a"])
        self.assertEqual(runner.call_count, 2)

    def test_claude_admission_denial_returns_budget_stop_without_dispatch(self):
        task = _task(model="fake-haiku")
        admission = kc.BudgetAdmission({"max-dispatches": 0})
        runner = mock.Mock()
        verify_runner = mock.Mock()

        result = claude.run_task(task, CLAUDE_PRICING, runner, verify_runner,
                                 claude_bin=STUB_BIN, admission=admission)

        self.assertEqual(result["failure"], "budget")
        self.assertEqual(result["budget_stop"]["operation"], "initial")
        self.assertEqual(result["model_used"], "fake-haiku")  # resolved before the refusal
        runner.assert_not_called()
        verify_runner.assert_not_called()

    # ---- D. Copilot driver: ported verbatim in shape from Claude ---------------------------

    def test_copilot_dispatch_failure_stops_before_verify_even_if_verify_would_pass(self):
        task = _task(model="fake-cheap")
        runner = mock.Mock(return_value=(1, "boom: the process crashed"))
        verify_runner = mock.Mock(return_value=(0, "would have passed"))

        result = copilot.run_task(task, COPILOT_PRICING, runner, verify_runner,
                                  copilot_bin=STUB_BIN)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["failure"], "dispatch")
        self.assertIsNone(result["verify_rc"])
        verify_runner.assert_not_called()

    def test_copilot_escalates_tier_ladder_on_verify_failure_until_pass(self):
        task = _task(model="fake-cheap")
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(side_effect=[(1, "nope"), (1, "still nope"), (0, "ok")])

        result = copilot.run_task(task, COPILOT_PRICING, runner, verify_runner,
                                  copilot_bin=STUB_BIN)

        self.assertEqual(result["status"], "done")
        self.assertEqual(result["escalations"], ["fake-mid-a", "fake-strong"])
        self.assertEqual(result["model_used"], "fake-strong")
        self.assertEqual(runner.call_count, 3)

    def test_copilot_admission_denial_returns_budget_stop_without_dispatch(self):
        task = _task(model="fake-cheap")
        admission = kc.BudgetAdmission({"max-dispatches": 0})
        runner = mock.Mock()
        verify_runner = mock.Mock()

        result = copilot.run_task(task, COPILOT_PRICING, runner, verify_runner,
                                  copilot_bin=STUB_BIN, admission=admission)

        self.assertEqual(result["failure"], "budget")
        runner.assert_not_called()
        verify_runner.assert_not_called()

    # ---- E. Cursor driver: no tier ladder at all -- one attempt, then blocked -------------

    def test_cursor_verify_failure_blocks_after_exactly_one_attempt_no_ladder(self):
        task = _task(model="fake-model")
        runner = mock.Mock(return_value=(0, "dispatched", {"outcome": "ok"}))
        verify_runner = mock.Mock(return_value=(1, "still red"))

        result = cursor.run_task(task, runner, verify_runner, cursor_bin=STUB_BIN)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["escalations"], [])
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(verify_runner.call_count, 1)

    def test_cursor_dispatch_failure_stops_immediately(self):
        task = _task(model="fake-model")
        runner = mock.Mock(return_value=(1, "authentication failed", {"outcome": "denied"}))
        verify_runner = mock.Mock(return_value=(0, "would pass"))

        result = cursor.run_task(task, runner, verify_runner, cursor_bin=STUB_BIN)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["failure"], "dispatch")
        self.assertEqual(result["escalations"], [])
        self.assertEqual(result["class"], "auth")
        verify_runner.assert_not_called()

    def test_cursor_admission_denial_returns_budget_stop_without_dispatch(self):
        task = _task(model="fake-model")
        admission = kc.BudgetAdmission({"max-dispatches": 0})
        runner = mock.Mock()
        verify_runner = mock.Mock()

        result = cursor.run_task(task, runner, verify_runner, cursor_bin=STUB_BIN,
                                 admission=admission)

        self.assertEqual(result["failure"], "budget")
        runner.assert_not_called()
        verify_runner.assert_not_called()

    # ---- F. Codex driver: the two asymmetries D01 flagged as load-bearing ------------------

    def test_codex_unknown_class_dispatch_failure_still_climbs_the_ladder(self):
        """A bare, unrecognisable dispatch failure has ALWAYS been treated as the model's own
        failure and escalated (codex_execute.py's NO_ESCALATION_CLASSES comment says so by
        name) -- the opposite of Claude/Copilot, which stop on ANY dispatch failure."""
        task = _task(model="fake-cheap")
        runner = mock.Mock(side_effect=[(1, "boom: totally unexpected crash"), None])
        verify_runner = mock.Mock(return_value=(0, "ok"))

        result = codex.run_task(task, CODEX_PRICING, runner, verify_runner, codex_bin=STUB_BIN)

        self.assertEqual(result["status"], "done")
        self.assertEqual(result["escalations"], ["fake-strong-a"])
        self.assertEqual(result["attempts"][0]["result"], "dispatch-failed")
        self.assertEqual(result["attempts"][0]["failure_class"], "unknown")
        self.assertEqual(runner.call_count, 2)
        self.assertEqual(verify_runner.call_count, 1)

    def test_codex_no_escalation_class_dispatch_failure_stops_ladder_and_skips_recovery(self):
        """A class a pricier model shares (here: auth) stops the ladder AND the reserved-
        orchestrator recovery step -- one attempt total, unlike the unknown-class case above."""
        task = _task(model="fake-cheap")
        runner = mock.Mock(return_value=(1, "authentication failed -- please log in"))
        verify_runner = mock.Mock(return_value=(0, "ok"))

        result = codex.run_task(task, CODEX_PRICING, runner, verify_runner, codex_bin=STUB_BIN)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["escalations"], [])
        self.assertIsNone(result["recovery"])
        self.assertEqual(result["attempts"][0]["failure_class"], "auth")
        self.assertEqual(runner.call_count, 1)
        verify_runner.assert_not_called()

    def test_codex_ladder_exhausted_triggers_reserved_orchestrator_recovery(self):
        """Codex-only: an exhausted worker ladder unlocks one evidence-gated dispatch to the
        reserved orchestrator model. Claude/Copilot/Cursor have no equivalent last resort."""
        task = _task(model="fake-cheap")
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(return_value=(1, "always fails"))

        result = codex.run_task(task, CODEX_PRICING, runner, verify_runner, codex_bin=STUB_BIN)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["escalations"], ["fake-strong-a"])
        self.assertIsNotNone(result["recovery"])
        self.assertEqual(result["model_used"], "fake-frontier")
        self.assertEqual(runner.call_count, 3)  # initial + 1 worker rung + 1 recovery attempt

    def test_codex_admission_denial_raises_rather_than_returning(self):
        """The one driver-internal API asymmetry: Claude/Copilot/Cursor's run_task RETURNS a
        budget-stop dict on a refused admission; Codex's RAISES _BudgetRefused and relies on
        cmd_run to catch it (bin/codex_execute.py line ~1599). Both are handled correctly by
        each driver's own cmd_run today, but a future direct caller of codex.run_task that
        forgets the try/except would crash uncaught where the other three drivers degrade to
        a result dict -- worth knowing before wiring a new caller, not a defect to fix here."""
        task = _task(model="fake-cheap")
        admission = kc.BudgetAdmission({"max-dispatches": 0})
        runner = mock.Mock()
        verify_runner = mock.Mock()

        with self.assertRaises(codex._BudgetRefused) as ctx:
            codex.run_task(task, CODEX_PRICING, runner, verify_runner, codex_bin=STUB_BIN,
                           admission=admission)

        self.assertEqual(ctx.exception.kind, "initial")
        runner.assert_not_called()
        verify_runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
