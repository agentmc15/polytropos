"""One kit contract, four adapters, and a guard against re-triplication (step 15).

WHAT WAS MEASURED. The three drivers shared 35 top-level names. Twenty-seven were the same code
three times — eighteen byte-for-byte identical, nine differing only in docstrings that said
things like "ported verbatim in shape from bin/copilot_execute.py's T7 function". Extracting
them surfaced three divergences that reading had not:

  1. `copilot_execute._parse_block` stripped backticks from a model pin; the other two did not,
     so the same `- model: \\`x\\`` line meant a different model depending on which driver read it.
  2. `codex_execute._select_task` refused an explicitly named task whose dependencies were
     unfinished; the other two returned it. `cmd_run` calls that function, so on two of three
     drivers `--task T5` dispatched while T4 was still pending.
  3. `append_plan_budget_stop_note` wrote `- role:` in two drivers and `- agent:` in the third,
     for the same event, into ledgers a shared reader parses.

None of those were found by inspection. They were found by trying to make one implementation
serve all three, which is the argument for having done it.
"""

import ast
import difflib
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRIVERS = ("claude_execute", "copilot_execute", "codex_execute")

#: The one function that legitimately repeats in every driver: the loader that reaches the
#: shared contract. It cannot come from the contract, because reaching the contract is what it
#: does. Everything else that repeats is a copy.
BOOTSTRAP = {"_kc"}


def _load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_contract_test", ROOT / "bin" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


kc = _load("kit_contract")
ha = _load("harness_adapter")

TASKS_MD = """\
## Phase 1 — setup

### T1 — First task
- status: done
- model: haiku

**Brief.** Do the first thing.

**Acceptance.** It is done.

**Verify.**

```bash
python3 -c "print(1)"
```

### T2 — Second task
- status: pending
- model: `fake-mid-a`
- depends: T1

**Brief.** Do the second thing.

**Acceptance.** It too is done.

**Verify.**

```bash
python3 -c "print(2)"
```

### T3 — Blocked task
- status: pending
- depends: T2

**Brief.** Waits on T2.

**Acceptance.** Later.

**Verify.**

```bash
python3 -c "print(3)"
```
"""


class ParsingTests(unittest.TestCase):
    def test_the_dialect_parses_with_no_field_dropped(self):
        tasks = kc.parse_tasks(TASKS_MD)
        self.assertEqual([t["id"] for t in tasks], ["T1", "T2", "T3"])
        self.assertEqual(tasks[0]["status"], "done")
        self.assertEqual(tasks[1]["depends"], ["T1"])
        for task in tasks:
            with self.subTest(task=task["id"]):
                self.assertTrue(task["brief"], "a brief was dropped")
                self.assertTrue(task["verify"], "a VERIFY COMMAND was dropped")

    def test_a_backticked_model_pin_resolves_to_the_bare_id(self):
        # Divergence (1): tolerated by one driver's parser and by neither of the other two.
        tasks = kc.parse_tasks(TASKS_MD)
        self.assertEqual(tasks[1]["model"], "fake-mid-a")
        self.assertEqual(tasks[0]["model"], "haiku")

    def test_task_ids_are_carried_through_unchanged(self):
        # Kits are committed files whose ledgers reference these ids; deriving new ones would
        # orphan every historical record that names one.
        for task in kc.parse_tasks(TASKS_MD):
            with self.subTest(task=task["id"]):
                self.assertIn(f"### {task['id']} ", TASKS_MD)
                self.assertEqual(kc.to_contract(task)["id"], task["id"])

    def test_the_normalized_view_is_versioned_and_complete(self):
        contract = kc.to_contract(kc.parse_tasks(TASKS_MD)[1], role="implementer", effort="medium")
        self.assertEqual(contract["contract"], kc.CONTRACT_VERSION)
        for field in kc.TASK_FIELDS:
            self.assertIn(field, contract)
        self.assertEqual(contract["role"], "implementer")
        self.assertEqual(contract["effort"], "medium")


class ReadinessTests(unittest.TestCase):
    """Divergence (2): naming a task used to be the way around the dependency check."""

    def setUp(self):
        self.tasks = kc.parse_tasks(TASKS_MD)

    def test_naming_a_dependency_blocked_task_does_not_select_it(self):
        task, reason = kc.select_task(self.tasks, task_id="T3")
        self.assertIsNone(task)
        self.assertIn("depends on T2", reason)

    def test_the_low_level_selector_applies_the_same_rule(self):
        # `cmd_run` calls this one. It used to be a second implementation with its own answer.
        self.assertIsNone(kc._select_task(self.tasks, "T3"))
        self.assertEqual(kc._select_task(self.tasks, "T2")["id"], "T2")

    def test_automatic_selection_takes_the_first_ready_task(self):
        task, reason = kc.select_task(self.tasks)
        self.assertIsNone(reason)
        self.assertEqual(task["id"], "T2")

    def test_a_completed_task_needs_an_explicit_rerun(self):
        task, reason = kc.select_task(self.tasks, task_id="T1")
        self.assertIsNone(task)
        self.assertIn("already done", reason)
        self.assertEqual(kc.select_task(self.tasks, task_id="T1", allow_rerun=True)[0]["id"], "T1")

    def test_an_unknown_id_says_so_rather_than_reporting_no_eligible_task(self):
        _task, reason = kc.select_task(self.tasks, task_id="T99")
        self.assertIn("no task with id", reason)


class LedgerFieldTests(unittest.TestCase):
    """Divergence (3): the same event under two field names, in ledgers a shared reader parses."""

    def _write(self, **kwargs):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        notes = Path(tmp.name) / "NOTES.md"
        kc.append_plan_budget_stop_note(
            notes, kc.parse_tasks(TASKS_MD)[1], "2026-01-01-abcd", "max-dispatches",
            3, 3, 0, **kwargs
        )
        return notes.read_text()

    def test_each_driver_keeps_the_field_name_its_ledgers_already_use(self):
        self.assertIn("- role: implementer", self._write(role="implementer"))
        self.assertIn("- agent: implementer", self._write(agent="implementer"))

    def test_it_refuses_to_guess_which_name_to_write(self):
        for kwargs in ({}, {"role": "a", "agent": "b"}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    self._write(**kwargs)


class TripleImplementationTests(unittest.TestCase):
    """The extraction has to stick, or it was a one-time tidy-up rather than a fix."""

    def _top_level(self, module):
        text = (ROOT / "bin" / f"{module}.py").read_text(encoding="utf-8")
        tree = ast.parse(text)
        return {n.name: ast.get_source_segment(text, n)
                for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}

    def test_no_driver_redefines_a_name_the_contract_owns(self):
        owned = set(self._top_level("kit_contract"))
        owned.discard("_cli")
        for driver in DRIVERS:
            with self.subTest(driver=driver):
                clash = sorted(owned & set(self._top_level(driver)))
                self.assertEqual(
                    clash, [],
                    f"{driver} defines {clash}, which bin/kit_contract.py already owns — "
                    f"re-export it instead, or the two will drift as they did before",
                )

    def test_no_two_drivers_share_a_substantial_implementation(self):
        # The failure mode this file exists for, stated as a test: a function appearing in two
        # drivers with near-identical bodies is a copy, and a copy is a future divergence.
        bodies = {d: self._top_level(d) for d in DRIVERS}
        for i, first in enumerate(DRIVERS):
            for second in DRIVERS[i + 1:]:
                shared = set(bodies[first]) & set(bodies[second])
                for name in sorted(shared):
                    a, b = bodies[first][name], bodies[second][name]
                    if name in BOOTSTRAP:
                        continue
                    if len(a.splitlines()) < 8:
                        continue  # a short CLI shim is not a shared implementation
                    with self.subTest(pair=f"{first}/{second}", name=name):
                        ratio = difflib.SequenceMatcher(None, a, b).ratio()
                        self.assertLess(
                            ratio, 0.85,
                            f"{name} is {ratio:.0%} identical between {first} and {second} — "
                            f"move it to bin/kit_contract.py",
                        )

    def test_every_driver_reaches_the_contract(self):
        for driver in DRIVERS:
            with self.subTest(driver=driver):
                module = _load(driver)
                self.assertEqual(module.CONTRACT_VERSION, kc.CONTRACT_VERSION)
                # Identity would compare two separately-loaded copies of the same file, which
                # `bin/` not being a package makes unavoidable. What matters is that the name
                # resolves INTO the contract rather than to a local definition.
                self.assertEqual(module.parse_tasks.__module__, "kit_contract")
                self.assertEqual(module.select_task.__module__, "kit_contract")
                self.assertEqual(module.cmd_status.__module__, "kit_contract")


class CapabilityRegistryTests(unittest.TestCase):
    def test_unknown_is_a_state_and_it_does_not_count_as_yes(self):
        row = ha.capability("x", product=ha.SUPPORTED, implemented=ha.SUPPORTED)
        self.assertEqual(row["verified"], ha.UNKNOWN)
        self.assertEqual(ha.effective(row), ha.UNKNOWN)

    def test_the_effective_state_is_the_weakest_of_the_three(self):
        cases = [
            ((ha.SUPPORTED, ha.SUPPORTED, ha.SUPPORTED), ha.SUPPORTED),
            ((ha.SUPPORTED, ha.SUPPORTED, ha.UNKNOWN), ha.UNKNOWN),
            ((ha.SUPPORTED, ha.UNSUPPORTED, ha.UNKNOWN), ha.UNSUPPORTED),
            ((ha.UNKNOWN, ha.SUPPORTED, ha.SUPPORTED), ha.UNKNOWN),
        ]
        for (product, implemented, verified), expected in cases:
            with self.subTest(states=(product, implemented, verified)):
                row = ha.capability("x", product=product, implemented=implemented,
                                    verified=verified,
                                    verified_on="2026-01-01" if verified == ha.SUPPORTED else None)
                self.assertEqual(ha.effective(row), expected)

    def test_a_polytropos_capability_is_not_weakened_by_a_vendor_having_no_opinion(self):
        row = ha.capability("confined_verify", product=ha.NOT_APPLICABLE,
                            implemented=ha.SUPPORTED, verified=ha.SUPPORTED,
                            verified_on="2026-09-06")
        self.assertEqual(ha.effective(row), ha.SUPPORTED)

    def test_a_verification_without_a_date_is_refused(self):
        with self.assertRaises(ValueError):
            ha.capability("x", verified=ha.SUPPORTED)

    def test_requiring_an_unverified_capability_raises(self):
        adapter = ha.StubAdapter()
        adapter.requires("dispatch")
        for name in ("status", "cancel", "never-heard-of-it"):
            with self.subTest(capability=name):
                with self.assertRaises(ha.CapabilityError):
                    adapter.requires(name)

    def test_the_registry_covers_every_driver_and_the_stub(self):
        registry = ha.load_capabilities()
        for harness in ("claude-code", "codex", "copilot", "stub", "cursor"):
            with self.subTest(harness=harness):
                self.assertIn(harness, registry["harnesses"])
                rows = ha.registry_capabilities(harness)
                self.assertIn("dispatch", rows)

    def test_the_registry_records_what_was_actually_verified_and_what_was_not(self):
        # The honest shape: one harness has live evidence, the others do not, and the file says
        # so rather than rounding up.
        claude = ha.registry_capabilities("claude-code")
        self.assertEqual(ha.effective(claude["tool_pin"]), ha.SUPPORTED)
        self.assertTrue(claude["tool_pin"]["verified_on"])
        for harness in ("codex", "copilot"):
            with self.subTest(harness=harness):
                self.assertEqual(ha.effective(ha.registry_capabilities(harness)["dispatch"]),
                                 ha.UNKNOWN)

    def test_the_historical_product_matrix_is_left_alone(self):
        # It answers a different question, pinned from aesop's own research at a stated commit.
        matrix = ROOT / "primitives" / "harness-matrix.json"
        self.assertTrue(matrix.is_file())
        import json
        payload = json.loads(matrix.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], "polytropos-harness-matrix/v1")
        self.assertIn("aesop_commit", payload["source"])


class AdapterConformanceTests(unittest.TestCase):
    """The same logical task through every adapter, including one that is not a real harness."""

    def adapters(self):
        return [ha.StubAdapter()]

    def test_every_adapter_builds_a_dispatch_argv_for_the_same_task(self):
        task = kc.to_contract(kc.parse_tasks(TASKS_MD)[1])
        for adapter in self.adapters():
            with self.subTest(adapter=adapter.name):
                argv = adapter.build_dispatch(task, model_id="fake-mid-a", prompt="do it")
                self.assertIsInstance(argv, list)
                self.assertTrue(all(isinstance(a, str) for a in argv))
                self.assertIn("T2", argv)

    def test_every_adapter_normalizes_a_runner_result_the_same_way(self):
        raw = {"outcome": "ok", "rc": 0, "terminal": True, "stdout": "out", "stderr": "",
               "detail": "", "duration_s": 1.5}
        for adapter in self.adapters():
            with self.subTest(adapter=adapter.name):
                result = adapter.normalize_result(raw)
                self.assertEqual(result["contract"], ha.ADAPTER_VERSION)
                self.assertEqual(result["harness"], adapter.name)
                self.assertEqual(result["outcome"], "ok")
                self.assertTrue(result["terminal"])

    def test_an_unsupported_operation_raises_rather_than_returning_a_fake_answer(self):
        for adapter in self.adapters():
            with self.subTest(adapter=adapter.name):
                if adapter.supports("status") != ha.SUPPORTED:
                    with self.assertRaises(ha.CapabilityError):
                        adapter.status("run-1")
                if adapter.supports("cancel") != ha.SUPPORTED:
                    with self.assertRaises(ha.CapabilityError):
                        adapter.cancel("run-1")

    def test_an_adapter_that_implements_nothing_still_answers_honestly(self):
        bare = ha.Adapter()
        self.assertEqual(bare.supports("dispatch"), ha.UNKNOWN)
        with self.assertRaises(NotImplementedError):
            bare.build_dispatch({"id": "T1"})
        with self.assertRaises(ha.CapabilityError):
            bare.requires("dispatch")

    def test_no_adapter_reads_another_harnesses_pricing(self):
        seen = {}
        for harness, entry in ha.load_capabilities()["harnesses"].items():
            path = entry.get("pricing_file")
            if path is None:
                continue
            with self.subTest(harness=harness):
                self.assertNotIn(path, seen,
                                 f"{harness} and {seen.get(path)} name the same pricing file")
                seen[path] = harness


if __name__ == "__main__":
    unittest.main()
