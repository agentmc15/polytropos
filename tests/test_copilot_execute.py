"""Stdlib unittest regression suite for bin/copilot_execute.py.

bin/ is not a package; copilot_execute.py is loaded via importlib by absolute path computed
from this file's own location, per the repo's `BIN_DIR = Path(__file__).resolve().parent.parent
/ "bin"` convention (same pattern as tests/test_harness_select.py).

============================================================================================
 SAFETY CONTRACT — read this before adding a test here
============================================================================================
No test in this file EVER invokes the real `copilot` binary or touches the real `~/.copilot`.
Every dispatch goes through one of two seams: an injected fake `runner`/`verify_runner`
callable (pure-function tests of `run_task`, `build_dispatch`, `escalation_ladder`), or a tiny
temp STUB shell executable written to a `tempfile.TemporaryDirectory()` and passed explicitly
via `--copilot-bin` (the end-to-end `main(["run", ...])` test) -- never a binary named
`copilot` resolved off PATH. `Path.home()` is never called anywhere in this file. The dry-run
test additionally proves the negative by patching `subprocess` in the loaded module to raise if
touched at all, then asserting `--dry-run` still completes and mutates nothing.

Fixture ids (`fake-cheap`, `fake-mid-a`, `fake-mid-b`, `fake-strong`, `fake-front`) and every
price in `PRICING_FIXTURE` are synthetic and never appear in `data/pricing.copilot.json`.
"""

import contextlib
import importlib.util
import io
import json
import re
import socket
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


# ---- fixtures ---------------------------------------------------------------------------------

# A synthetic STUB executable "name" used wherever a copilot_bin value is required but no
# process is actually spawned (build_dispatch is a pure argv builder; run_task's runner/
# verify_runner are fakes). Deliberately not the real CLI's name.
STUB_BIN = "stub-cli"

# Fake pricing dict, tiers expressed in file order: cheap, mid (two entries), strong, frontier.
# Round fake numbers only -- never the real roster's ids or rates.
PRICING_FIXTURE = {
    "models": {
        "fake-cheap": {"tier": "cheap", "input_per_mtok": 1.0, "output_per_mtok": 2.0},
        "fake-mid-a": {"tier": "mid", "input_per_mtok": 3.0, "output_per_mtok": 6.0},
        "fake-mid-b": {"tier": "mid", "input_per_mtok": 3.5, "output_per_mtok": 7.0},
        "fake-strong": {"tier": "strong", "input_per_mtok": 8.0, "output_per_mtok": 16.0},
        "fake-front": {"tier": "frontier", "input_per_mtok": 20.0, "output_per_mtok": 40.0},
    }
}

# Two phases, three tasks: T1 has a pinned model and depends: (none); T2 has no model line at
# all and depends: (none); T3 has no model-agnostic distinction but depends: T1.
TASKS_TEXT_FIXTURE = """# TASKS — fixture kit

## Phase 1 — Made-up phase one

### T1 — First fixture task
- status: pending
- model: fake-mid-a
- depends: (none)
- independent: yes

**Brief.** Do the first fixture thing with fake ids only.

**Acceptance.** Fake acceptance text for T1.

**Verify.**
```bash
true
```

### T2 — Second fixture task
- status: pending
- depends: (none)
- independent: no

**Brief.** Do the second fixture thing; has no model line at all.

**Acceptance.** Fake acceptance text for T2.

**Verify.**
```bash
true
```

## Phase 2 — Made-up phase two

### T3 — Third fixture task
- status: pending
- model: fake-cheap
- depends: T1
- independent: no

**Brief.** Do the third fixture thing; depends on the first.

**Acceptance.** Fake acceptance text for T3.

**Verify.**
```bash
true
```
"""

INVALID_STATUS_TASKS_TEXT = """## Phase 1 — Bad phase

### TX — Task with an invalid status value
- status: not-a-real-status
- depends: (none)
- independent: no

**Brief.** Irrelevant fixture brief text.

**Verify.**
```bash
true
```
"""

# A single-task kit whose verify command is the shell builtin `true`, for the end-to-end run.
SINGLE_TASK_TASKS_TEXT = """## Phase 1 — Only phase

### E1 — Only fixture task
- status: pending
- depends: (none)
- independent: yes

**Brief.** Fixture brief payload for the end-to-end stub-executable run.

**Acceptance.** Fake acceptance text for E1.

**Verify.**
```bash
true
```
"""

# A tiny POSIX shell STUB (never named after the real CLI): logs its argv, exits 0.
STUB_SHELL_TEMPLATE = "#!/bin/sh\necho \"$@\" >> \"{log}\"\nexit 0\n"


def _write_kit(tmp_path, text):
    kit_dir = Path(tmp_path) / "kit"
    kit_dir.mkdir()
    (kit_dir / "TASKS.md").write_text(text)
    return kit_dir


# ---- 1. parse_tasks ----------------------------------------------------------------------------

class ParseTasksTests(unittest.TestCase):
    def test_fields_parsed_for_all_three_fixture_tasks(self):
        tasks = ce.parse_tasks(TASKS_TEXT_FIXTURE)
        by_id = {t["id"]: t for t in tasks}
        self.assertEqual(set(by_id), {"T1", "T2", "T3"})

        t1 = by_id["T1"]
        self.assertEqual(t1["title"], "First fixture task")
        self.assertEqual(t1["status"], "pending")
        self.assertEqual(t1["model"], "fake-mid-a")
        self.assertEqual(t1["depends"], [])
        self.assertTrue(t1["independent"])
        self.assertIn("first fixture thing", t1["brief"].lower())
        self.assertEqual(t1["verify"], "true")

        t2 = by_id["T2"]
        self.assertIsNone(t2["model"])
        self.assertEqual(t2["depends"], [])
        self.assertFalse(t2["independent"])
        self.assertIn("no model line", t2["brief"].lower())

        t3 = by_id["T3"]
        self.assertEqual(t3["model"], "fake-cheap")
        self.assertEqual(t3["depends"], ["T1"])
        self.assertFalse(t3["independent"])


# ---- 2. invalid status --------------------------------------------------------------------------

class InvalidStatusTests(unittest.TestCase):
    def test_invalid_status_raises_value_error_listing_vocabulary(self):
        with self.assertRaises(ValueError) as ctx:
            ce.parse_tasks(INVALID_STATUS_TASKS_TEXT)
        msg = str(ctx.exception)
        for status_word in ("pending", "in-progress", "done", "blocked"):
            self.assertIn(status_word, msg)


# ---- 3. set_status -------------------------------------------------------------------------------

class SetStatusTests(unittest.TestCase):
    def test_changes_only_the_target_status_line_and_is_idempotent(self):
        updated = ce.set_status(TASKS_TEXT_FIXTURE, "T2", "in-progress")

        orig_lines = TASKS_TEXT_FIXTURE.splitlines()
        new_lines = updated.splitlines()
        self.assertEqual(len(orig_lines), len(new_lines))

        diffs = [i for i in range(len(orig_lines)) if orig_lines[i] != new_lines[i]]
        self.assertEqual(len(diffs), 1)
        i = diffs[0]
        self.assertTrue(orig_lines[i].strip().startswith("- status:"))
        self.assertEqual(new_lines[i].strip(), "- status: in-progress")
        for j in range(len(orig_lines)):
            if j != i:
                self.assertEqual(orig_lines[j], new_lines[j])

        # second call with the same status is idempotent: identical output text.
        twice = ce.set_status(updated, "T2", "in-progress")
        self.assertEqual(twice, updated)

    def test_unknown_id_raises_value_error(self):
        with self.assertRaises(ValueError):
            ce.set_status(TASKS_TEXT_FIXTURE, "NOPE", "done")

    def test_invalid_status_raises_value_error(self):
        with self.assertRaises(ValueError):
            ce.set_status(TASKS_TEXT_FIXTURE, "T1", "not-a-real-status")


# ---- 4. build_dispatch ----------------------------------------------------------------------------

class BuildDispatchTests(unittest.TestCase):
    def test_with_model_includes_pairs_and_flag_and_ends_with_prompt(self):
        argv = ce.build_dispatch(
            "implementer",
            "fake brief text",
            "fake-mid-a",
            copilot_bin=STUB_BIN,
            extra_args=("--deny-tool=shell(rm:*)",),
        )
        self.assertIsInstance(argv, list)
        self.assertEqual(
            argv,
            [
                STUB_BIN,
                "--agent", "implementer",
                "--model", "fake-mid-a",
                "--allow-all-tools",
                "--deny-tool=shell(rm:*)",
                "-p", "fake brief text",
            ],
        )

    def test_without_model_omits_model_flag(self):
        argv = ce.build_dispatch("implementer", "fake brief text", None, copilot_bin=STUB_BIN)
        self.assertNotIn("--model", argv)
        self.assertEqual(
            argv,
            [STUB_BIN, "--agent", "implementer", "--allow-all-tools", "-p", "fake brief text"],
        )

    def test_extra_args_included_in_order(self):
        argv = ce.build_dispatch(
            "verifier",
            "brief",
            None,
            copilot_bin=STUB_BIN,
            extra_args=("--allow-all-paths", "--allow-all-urls"),
        )
        self.assertLess(argv.index("--allow-all-paths"), argv.index("--allow-all-urls"))
        self.assertEqual(argv[-2:], ["-p", "brief"])


# ---- 5. escalation_ladder -------------------------------------------------------------------------

class EscalationLadderTests(unittest.TestCase):
    def test_from_mid_gives_strong_then_frontier(self):
        self.assertEqual(
            ce.escalation_ladder(PRICING_FIXTURE, "fake-mid-a"), ["fake-strong", "fake-front"]
        )

    def test_from_cheap_gives_all_three_tiers_above(self):
        self.assertEqual(
            ce.escalation_ladder(PRICING_FIXTURE, "fake-cheap"),
            ["fake-mid-a", "fake-strong", "fake-front"],
        )

    def test_from_frontier_gives_empty_ladder(self):
        self.assertEqual(ce.escalation_ladder(PRICING_FIXTURE, "fake-front"), [])

    def test_unknown_id_behaves_like_none_mid_start(self):
        unknown = ce.escalation_ladder(PRICING_FIXTURE, "not-a-fixture-id")
        none_start = ce.escalation_ladder(PRICING_FIXTURE, None)
        self.assertEqual(unknown, none_start)
        self.assertEqual(none_start, ["fake-strong", "fake-front"])

    def test_first_in_file_order_wins_within_a_tier(self):
        ladder = ce.escalation_ladder(PRICING_FIXTURE, "fake-cheap")
        self.assertEqual(ladder[0], "fake-mid-a")
        self.assertNotIn("fake-mid-b", ladder)


# ---- 6. run_task with fake runners -----------------------------------------------------------------

class RunTaskTests(unittest.TestCase):
    @staticmethod
    def _task(**overrides):
        base = {
            "id": "T1",
            "title": "fixture task",
            "status": "pending",
            "model": "fake-mid-a",
            "depends": [],
            "independent": True,
            "brief": "fake brief payload for run_task tests",
            "verify": "true",
        }
        base.update(overrides)
        return base

    def test_verify_passes_first_try(self):
        task = self._task()
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(return_value=(0, "ok"))

        result = ce.run_task(task, PRICING_FIXTURE, runner, verify_runner, copilot_bin=STUB_BIN)

        self.assertEqual(result["status"], "done")
        self.assertEqual(runner.call_count, 1)
        dispatched_argv = runner.call_args_list[0].args[0]
        self.assertIn("--model", dispatched_argv)
        self.assertEqual(
            dispatched_argv[dispatched_argv.index("--model") + 1], "fake-mid-a"
        )
        self.assertEqual(result["escalations"], [])
        self.assertEqual(result["model_used"], "fake-mid-a")

    def test_verify_fails_once_then_passes_escalates_exactly_one_rung(self):
        task = self._task()
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(
            side_effect=[(1, "boom: fixture failure"), (0, "ok now")]
        )

        result = ce.run_task(task, PRICING_FIXTURE, runner, verify_runner, copilot_bin=STUB_BIN)

        self.assertEqual(result["status"], "done")
        self.assertEqual(result["escalations"], ["fake-strong"])
        self.assertEqual(result["model_used"], "fake-strong")
        self.assertEqual(runner.call_count, 2)

        second_argv = runner.call_args_list[1].args[0]
        self.assertEqual(second_argv[second_argv.index("--model") + 1], "fake-strong")
        prompt_payload = second_argv[-1]
        self.assertIn(task["brief"], prompt_payload)
        self.assertIn("ESCALATION EVIDENCE", prompt_payload)
        self.assertIn("boom: fixture failure", prompt_payload)

    def test_verify_never_passes_exhausts_full_ladder_and_blocks(self):
        task = self._task()
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(return_value=(1, "always fails"))

        result = ce.run_task(task, PRICING_FIXTURE, runner, verify_runner, copilot_bin=STUB_BIN)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["escalations"], ["fake-strong", "fake-front"])
        self.assertEqual(runner.call_count, 3)  # initial dispatch + one per ladder rung

    def test_max_escalations_truncates_ladder(self):
        task = self._task()
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(return_value=(1, "always fails"))

        result = ce.run_task(
            task,
            PRICING_FIXTURE,
            runner,
            verify_runner,
            max_escalations=1,
            copilot_bin=STUB_BIN,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["escalations"], ["fake-strong"])
        self.assertEqual(runner.call_count, 2)


# ---- 7. append_note -------------------------------------------------------------------------------

class AppendNoteTests(unittest.TestCase):
    def test_block_has_id_and_model_no_lesson_line_without_escalations(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes_path = Path(tmp) / "NOTES.md"
            task = {"id": "T1", "model": "fake-mid-a"}
            result = {
                "id": "T1",
                "status": "done",
                "model_used": "fake-mid-a",
                "escalations": [],
                "verify_rc": 0,
                "agent": "implementer",
            }
            ce.append_note(notes_path, result, task)
            text = notes_path.read_text()
            self.assertIn("T1", text)
            self.assertIn("fake-mid-a", text)
            self.assertNotIn("lesson-candidate (routing):", text)

    def test_escalations_add_lesson_candidate_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes_path = Path(tmp) / "NOTES.md"
            task = {"id": "T3", "model": "fake-mid-a"}
            result = {
                "id": "T3",
                "status": "done",
                "model_used": "fake-strong",
                "escalations": ["fake-strong"],
                "verify_rc": 0,
                "agent": "implementer",
            }
            ce.append_note(notes_path, result, task)
            text = notes_path.read_text()
            self.assertIn("T3", text)
            self.assertIn("fake-strong", text)
            self.assertTrue(
                any(
                    line.startswith("lesson-candidate (routing):")
                    for line in text.splitlines()
                )
            )


# ---- 8. end-to-end main(["run", ...]) with a STUB executable ----------------------------------------

class EndToEndRunWithStubExecutableTests(unittest.TestCase):
    def test_main_run_with_stub_executable_completes_done_and_logs_flags(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, SINGLE_TASK_TASKS_TEXT)

            stub_path = tmp / STUB_BIN
            log_path = tmp / "stub.log"
            stub_path.write_text(STUB_SHELL_TEMPLATE.format(log=log_path))
            stub_path.chmod(0o755)

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ce.main(["run", "--kit", str(kit_dir), "--copilot-bin", str(stub_path)])

            final_text = (kit_dir / "TASKS.md").read_text()
            tasks = ce.parse_tasks(final_text)
            self.assertEqual(tasks[0]["status"], "done")
            self.assertTrue((kit_dir / "NOTES.md").exists())

            self.assertTrue(log_path.exists())
            log_text = log_path.read_text()
            self.assertIn("--agent", log_text)
            self.assertIn("--allow-all-tools", log_text)


# ---- 9. dry-run spawns nothing ------------------------------------------------------------------------

class DryRunSpawnsNothingTests(unittest.TestCase):
    def test_dry_run_never_touches_subprocess_and_leaves_tasks_file_untouched(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, TASKS_TEXT_FIXTURE)
            before = (kit_dir / "TASKS.md").read_bytes()

            with mock.patch.object(ce, "subprocess") as mock_subprocess:
                mock_subprocess.run.side_effect = AssertionError("subprocess in dry-run")
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    ce.main(
                        ["run", "--kit", str(kit_dir), "--copilot-bin", STUB_BIN, "--dry-run"]
                    )

            after = (kit_dir / "TASKS.md").read_bytes()
            self.assertEqual(before, after)
            self.assertFalse((kit_dir / "NOTES.md").exists())
            self.assertIn("dispatch:", buf.getvalue())


# ---- 10. status --kit smoke ------------------------------------------------------------------------

class StatusSmokeTests(unittest.TestCase):
    def test_status_kit_lists_each_task_id_and_a_totals_line(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, TASKS_TEXT_FIXTURE)

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ce.main(["status", "--kit", str(kit_dir)])
            output = buf.getvalue()

            for task_id in ("T1", "T2", "T3"):
                self.assertIn(task_id, output)
            self.assertRegex(output, r"\d+ pending / \d+ in-progress / \d+ done / \d+ blocked")


# ---- 11. prefs-aware escalation_ladder -------------------------------------------------------------

class PrefsAwareLadderTests(unittest.TestCase):
    def test_prefs_none_identical_to_legacy(self):
        self.assertEqual(
            ce.escalation_ladder(PRICING_FIXTURE, "fake-mid-a", prefs=None),
            ["fake-strong", "fake-front"],
        )

    def test_pin_wins_outright_cross_tier_allowed(self):
        prefs = {"pins": {"strong": "fake-mid-b"}, "excludes": [], "notes": [], "source": None}
        self.assertEqual(
            ce.escalation_ladder(PRICING_FIXTURE, "fake-mid-a", prefs=prefs),
            ["fake-mid-b", "fake-front"],
        )

    def test_exclude_empties_tier_and_is_skipped(self):
        prefs = {"pins": {}, "excludes": ["fake-strong"], "notes": [], "source": None}
        self.assertEqual(
            ce.escalation_ladder(PRICING_FIXTURE, "fake-mid-a", prefs=prefs),
            ["fake-front"],
        )

    def test_excluded_frontier_with_no_pin_tops_out_lower(self):
        prefs = {"pins": {}, "excludes": ["fake-front"], "notes": [], "source": None}
        self.assertEqual(
            ce.escalation_ladder(PRICING_FIXTURE, "fake-strong", prefs=prefs),
            [],
        )

    def test_pin_equal_to_current_model_deduped(self):
        prefs = {
            "pins": {"frontier": "fake-strong"}, "excludes": [], "notes": [], "source": None
        }
        self.assertEqual(
            ce.escalation_ladder(PRICING_FIXTURE, "fake-strong", prefs=prefs),
            [],
        )


# ---- 12. prefs-aware run_task -----------------------------------------------------------------------

class RunTaskPrefsTests(unittest.TestCase):
    @staticmethod
    def _task(**overrides):
        base = {
            "id": "T1",
            "title": "fixture task",
            "status": "pending",
            "model": "fake-mid-a",
            "depends": [],
            "independent": True,
            "brief": "fake brief payload for run_task prefs tests",
            "verify": "true",
        }
        base.update(overrides)
        return base

    def test_excluded_task_model_substitutes_pin_and_notes(self):
        task = self._task()
        prefs = {
            "pins": {"mid": "fake-mid-b"}, "excludes": ["fake-mid-a"], "notes": [],
            "source": None,
        }
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(return_value=(0, "ok"))

        result = ce.run_task(
            task, PRICING_FIXTURE, runner, verify_runner, copilot_bin=STUB_BIN, prefs=prefs
        )

        dispatched_argv = runner.call_args_list[0].args[0]
        self.assertEqual(
            dispatched_argv[dispatched_argv.index("--model") + 1], "fake-mid-b"
        )
        self.assertEqual(result["model_used"], "fake-mid-b")
        self.assertEqual(len(result["prefs_notes"]), 1)
        self.assertIn("excluded", result["prefs_notes"][0])

    def test_excluded_task_model_with_no_resolution_raises(self):
        task = self._task()
        prefs = {
            "pins": {}, "excludes": ["fake-mid-a", "fake-mid-b"], "notes": [],
            "source": None,
        }
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(return_value=(0, "ok"))

        with self.assertRaises(ValueError):
            ce.run_task(
                task, PRICING_FIXTURE, runner, verify_runner, copilot_bin=STUB_BIN, prefs=prefs
            )

    def test_prefs_none_result_has_no_prefs_notes_key(self):
        task = self._task()
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(return_value=(0, "ok"))

        result = ce.run_task(task, PRICING_FIXTURE, runner, verify_runner, copilot_bin=STUB_BIN)

        self.assertNotIn("prefs_notes", result)


# ---- 13. CLI prefs flags -------------------------------------------------------------------------

class CliPrefsTests(unittest.TestCase):
    def test_dry_run_with_pin_and_exclude_shows_prefs_line_and_substituted_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, TASKS_TEXT_FIXTURE)
            before = (kit_dir / "TASKS.md").read_bytes()

            with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE), \
                 mock.patch.object(ce, "subprocess") as mock_subprocess:
                mock_subprocess.run.side_effect = AssertionError("subprocess in dry-run")
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    ce.main([
                        "run", "--kit", str(kit_dir), "--task", "T1",
                        "--copilot-bin", STUB_BIN, "--dry-run",
                        "--no-prefs", "--pin", "mid=fake-mid-b", "--exclude", "fake-mid-a",
                    ])
            output = buf.getvalue()

            self.assertIn("prefs:", output)
            dispatch_line = next(
                line for line in output.splitlines() if line.startswith("dispatch:")
            )
            self.assertIn("fake-mid-b", dispatch_line)

            after = (kit_dir / "TASKS.md").read_bytes()
            self.assertEqual(before, after)

    def test_pin_without_equals_exits_2_with_grammar_message(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, TASKS_TEXT_FIXTURE)

            with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                buf_err = io.StringIO()
                with contextlib.redirect_stderr(buf_err):
                    with self.assertRaises(SystemExit) as ctx:
                        ce.main([
                            "run", "--kit", str(kit_dir), "--task", "T1",
                            "--copilot-bin", STUB_BIN, "--dry-run",
                            "--no-prefs", "--pin", "mid",
                        ])
                self.assertEqual(ctx.exception.code, 2)
                self.assertIn("TIER=MODEL_ID", buf_err.getvalue())

    def test_pin_unknown_tier_exits_2_listing_tier_words(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, TASKS_TEXT_FIXTURE)

            with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                buf_err = io.StringIO()
                with contextlib.redirect_stderr(buf_err):
                    with self.assertRaises(SystemExit) as ctx:
                        ce.main([
                            "run", "--kit", str(kit_dir), "--task", "T1",
                            "--copilot-bin", STUB_BIN, "--dry-run",
                            "--no-prefs", "--pin", "nope=fake-cheap",
                        ])
                self.assertEqual(ctx.exception.code, 2)
                err = buf_err.getvalue()
                for tier_word in ce.TIER_ORDER:
                    self.assertIn(tier_word, err)

    def test_exclude_unknown_id_exits_2_with_valid_choices(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, TASKS_TEXT_FIXTURE)

            with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                buf_err = io.StringIO()
                with contextlib.redirect_stderr(buf_err):
                    with self.assertRaises(SystemExit) as ctx:
                        ce.main([
                            "run", "--kit", str(kit_dir), "--task", "T1",
                            "--copilot-bin", STUB_BIN, "--dry-run",
                            "--no-prefs", "--exclude", "not-a-model",
                        ])
                self.assertEqual(ctx.exception.code, 2)
                self.assertIn("valid choices", buf_err.getvalue())

    def test_pin_exclude_conflict_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, TASKS_TEXT_FIXTURE)

            with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                buf_err = io.StringIO()
                with contextlib.redirect_stderr(buf_err):
                    with self.assertRaises(SystemExit) as ctx:
                        ce.main([
                            "run", "--kit", str(kit_dir), "--task", "T1",
                            "--copilot-bin", STUB_BIN, "--dry-run",
                            "--no-prefs", "--pin", "mid=fake-mid-b", "--exclude", "fake-mid-b",
                        ])
                self.assertEqual(ctx.exception.code, 2)
                self.assertIn("conflicts with exclude", buf_err.getvalue())

    def test_file_pin_merged_with_flag_exclude_both_in_prefs_line(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, TASKS_TEXT_FIXTURE)
            prefs_path = tmp / "copilot.json"
            prefs_path.write_text(json.dumps({"pins": {"strong": "fake-strong"}}))

            with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    ce.main([
                        "run", "--kit", str(kit_dir), "--task", "T1",
                        "--copilot-bin", STUB_BIN, "--dry-run",
                        "--prefs", str(prefs_path), "--exclude", "fake-front",
                    ])
            output = buf.getvalue()
            prefs_line = next(line for line in output.splitlines() if line.startswith("prefs:"))
            self.assertIn("strong=fake-strong", prefs_line)
            self.assertIn("fake-front", prefs_line)


class ModelPinBacktickToleranceTests(unittest.TestCase):
    """Regression guard (found by the first real Copilot-architected kit): a frontier model
    naturally backtick-formats the `- model:` pin (``- model: `fake-mid-a` ``), which the
    strict parser read as a literal-backtick model id. The parser now strips one surrounding
    backtick pair; everything else about the value stays bare."""

    def test_backticked_model_pin_parses_to_bare_id(self):
        text = (
            "## Phase 1 — x\n\n"
            "### T1 — t\n\n"
            "- status: pending\n"
            "- model: `fake-mid-a`\n\n"
            "**Brief.** b\n\n"
            "**Acceptance.** a\n\n"
            "**Verify.**\n```bash\ntrue\n```\n"
        )
        tasks = ce.parse_tasks(text)
        self.assertEqual(tasks[0]["model"], "fake-mid-a")

    def test_bare_model_pin_unchanged(self):
        tasks = ce.parse_tasks(TASKS_TEXT_FIXTURE)
        for task in tasks:
            self.assertNotIn("`", task["model"] or "")


# ---- 14. run id generation (T7, PLAN D8 -- format pinned positively AND negatively) ----------
#
# `generate_run_id` is ported verbatim in shape from `bin/claude_execute.py`'s T5 function
# (the resolved, reviewed design for this exact requirement); these tests mirror T5's own
# `RunIdGenerationTests` so the format assertion lives on both generator sides (Phase 1
# review F8).

class RunIdGenerationTests(unittest.TestCase):
    RUN_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[0-9a-f]{4}$")

    def test_format_matches_utc_date_plus_four_hex(self):
        run_id = ce.generate_run_id()
        self.assertRegex(run_id, self.RUN_ID_RE)
        self.assertEqual(len(run_id), 15)  # YYYY-MM-DD (10) + '-' (1) + 4 hex (4)

    def test_now_is_injectable_and_pins_the_date_segment(self):
        from datetime import datetime, timezone
        fixed = datetime(2030, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        run_id = ce.generate_run_id(now=fixed)
        self.assertTrue(run_id.startswith("2030-01-02-"))
        self.assertRegex(run_id, self.RUN_ID_RE)

    def test_content_free_no_hostname_username_or_path_fragment(self):
        run_id = ce.generate_run_id()
        # Positive: the id matches an EXACT, fully-anchored regex of digits/hyphens/lowercase
        # hex only -- by construction this rules out arbitrary hostname/username/path text.
        self.assertRegex(run_id, self.RUN_ID_RE)
        # Negative: explicit checks against this machine's own identifying strings, and
        # against path separators, none of which may appear.
        self.assertNotIn(socket.gethostname(), run_id)
        self.assertNotIn("/", run_id)
        self.assertNotIn("\\", run_id)

    def test_ids_are_not_all_identical_across_calls(self):
        ids = {ce.generate_run_id() for _ in range(25)}
        self.assertGreater(len(ids), 1)


# ---- 15. id preamble (T7 -- kit/run/task ids in the dispatch prompt) --------------------------

class BuildIdPreambleTests(unittest.TestCase):
    def test_all_three_present(self):
        self.assertEqual(
            ce.build_id_preamble(kit="fixturekit", run_id="2026-07-26-9f3a", task_id="T1"),
            "[kit=fixturekit run=2026-07-26-9f3a task=T1]",
        )

    def test_none_given_yields_empty_string(self):
        self.assertEqual(ce.build_id_preamble(), "")

    def test_partial_omits_the_missing_pair(self):
        self.assertEqual(ce.build_id_preamble(task_id="T1"), "[task=T1]")


class BuildDispatchIdPreambleTests(unittest.TestCase):
    def test_ids_given_prefix_the_prompt(self):
        argv = ce.build_dispatch(
            "implementer", "fake brief text", "fake-mid-a", copilot_bin=STUB_BIN,
            kit="fixturekit", run_id="2026-07-26-9f3a", task_id="T1",
        )
        prompt = argv[-1]
        self.assertTrue(
            prompt.startswith("[kit=fixturekit run=2026-07-26-9f3a task=T1]\n\n")
        )
        self.assertTrue(prompt.endswith("fake brief text"))

    def test_no_ids_prompt_is_exactly_the_brief(self):
        argv = ce.build_dispatch(
            "implementer", "fake brief text", "fake-mid-a", copilot_bin=STUB_BIN,
        )
        self.assertEqual(argv[-1], "fake brief text")


# ---- 16. outcome ledger line (T1 grammar: run=/parent=) ---------------------------------------

class OutcomeResultClassificationTests(unittest.TestCase):
    def test_blocked_status_is_always_blocked(self):
        self.assertEqual(ce.outcome_result("blocked", [], None), "blocked")
        self.assertEqual(ce.outcome_result("blocked", ["fake-strong"], "T1"), "blocked")

    def test_done_no_escalation_no_parent_is_plain_pass(self):
        self.assertEqual(ce.outcome_result("done", [], None), "pass")

    def test_done_with_escalations_is_escalated_pass(self):
        self.assertEqual(ce.outcome_result("done", ["fake-strong"], None), "escalated-pass")

    def test_done_with_parent_but_no_ladder_escalation_is_escalated_pass(self):
        self.assertEqual(ce.outcome_result("done", [], "T4"), "escalated-pass")


class BuildOutcomeLineTests(unittest.TestCase):
    def test_minimal_line_no_run_no_parent(self):
        line = ce.build_outcome_line("T1", "fake-cheap", 1, "pass")
        self.assertEqual(
            line, "outcome: T1 model=fake-cheap attempts=1 result=pass review=none"
        )

    def test_run_id_appended_when_present(self):
        line = ce.build_outcome_line("T1", "fake-cheap", 1, "pass", run_id="2026-07-26-9f3a")
        self.assertTrue(line.endswith(" run=2026-07-26-9f3a"))

    def test_parent_appended_only_when_present(self):
        line = ce.build_outcome_line(
            "T5", "fake-front", 3, "escalated-pass",
            run_id="2026-07-26-9f3a", parent="T4",
        )
        self.assertTrue(line.endswith(" run=2026-07-26-9f3a parent=T4"))

    def test_no_parent_omits_the_field_entirely(self):
        line = ce.build_outcome_line("T1", "fake-cheap", 1, "pass", run_id="2026-07-26-9f3a")
        self.assertNotIn("parent=", line)


class AppendNoteOutcomeLineTests(unittest.TestCase):
    def test_outcome_line_written_with_run_id_no_parent_on_clean_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes_path = Path(tmp) / "NOTES.md"
            task = {"id": "T1", "model": "fake-mid-a"}
            result = {
                "id": "T1", "status": "done", "model_used": "fake-mid-a",
                "escalations": [], "verify_rc": 0, "agent": "implementer",
            }
            ce.append_note(notes_path, result, task, run_id="2026-07-26-abcd")
            text = notes_path.read_text()
            self.assertIn(
                "outcome: T1 model=fake-mid-a attempts=1 result=pass review=none "
                "run=2026-07-26-abcd",
                text,
            )
            self.assertNotIn("parent=", text)

    def test_escalations_write_escalated_pass_outcome_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes_path = Path(tmp) / "NOTES.md"
            task = {"id": "T3", "model": "fake-mid-a"}
            result = {
                "id": "T3", "status": "done", "model_used": "fake-strong",
                "escalations": ["fake-strong"], "verify_rc": 0, "agent": "implementer",
            }
            ce.append_note(notes_path, result, task, run_id="2026-07-26-abcd")
            text = notes_path.read_text()
            self.assertIn(
                "outcome: T3 model=fake-strong attempts=2 result=escalated-pass review=none "
                "run=2026-07-26-abcd",
                text,
            )

    def test_parent_flows_through_to_the_outcome_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes_path = Path(tmp) / "NOTES.md"
            task = {"id": "T5", "model": "fake-mid-a"}
            result = {
                "id": "T5", "status": "done", "model_used": "fake-mid-a",
                "escalations": [], "verify_rc": 0, "agent": "implementer",
            }
            ce.append_note(notes_path, result, task, run_id="2026-07-26-abcd", parent="T4")
            text = notes_path.read_text()
            self.assertIn("result=escalated-pass", text)
            self.assertIn("parent=T4", text)

    def test_no_model_pin_and_dispatch_never_ran_uses_unpinned_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes_path = Path(tmp) / "NOTES.md"
            task = {"id": "T2", "model": None}
            result = {
                "id": "T2", "status": "done", "model_used": None,
                "escalations": [], "verify_rc": 0, "agent": "implementer",
            }
            ce.append_note(notes_path, result, task, run_id="2026-07-26-abcd")
            text = notes_path.read_text()
            self.assertIn("outcome: T2 model=unpinned", text)  # single token -- no space

    def test_no_run_id_or_parent_still_writes_a_plain_outcome_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes_path = Path(tmp) / "NOTES.md"
            task = {"id": "T1", "model": "fake-mid-a"}
            result = {
                "id": "T1", "status": "done", "model_used": "fake-mid-a",
                "escalations": [], "verify_rc": 0, "agent": "implementer",
            }
            ce.append_note(notes_path, result, task)
            text = notes_path.read_text()
            self.assertIn(
                "outcome: T1 model=fake-mid-a attempts=1 result=pass review=none", text
            )
            self.assertNotIn("run=", text)
            self.assertNotIn("parent=", text)


# ---- 17. run_task threads kit/run_id into every dispatch (initial + escalation rungs) --------

class RunTaskIdPreambleTests(unittest.TestCase):
    @staticmethod
    def _task(**overrides):
        base = {
            "id": "T1",
            "title": "fixture task",
            "status": "pending",
            "model": "fake-mid-a",
            "depends": [],
            "independent": True,
            "brief": "fake brief payload for id-preamble tests",
            "verify": "true",
        }
        base.update(overrides)
        return base

    def test_kit_and_run_id_land_on_every_dispatch_including_escalations(self):
        task = self._task()
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(side_effect=[(1, "boom"), (0, "ok now")])

        ce.run_task(
            task, PRICING_FIXTURE, runner, verify_runner, copilot_bin=STUB_BIN,
            kit="fixturekit", run_id="2026-07-26-9f3a",
        )

        self.assertEqual(runner.call_count, 2)
        for call in runner.call_args_list:
            prompt = call.args[0][-1]
            self.assertTrue(
                prompt.startswith("[kit=fixturekit run=2026-07-26-9f3a task=T1]")
            )

    def test_no_kit_no_run_id_prompt_unaffected(self):
        task = self._task()
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(return_value=(0, "ok"))

        ce.run_task(task, PRICING_FIXTURE, runner, verify_runner, copilot_bin=STUB_BIN)

        prompt = runner.call_args_list[0].args[0][-1]
        self.assertEqual(prompt, task["brief"])


# ---- 18. end-to-end: --dry-run shows the id preamble, real run stamps run=/parent= -----------

class EndToEndIdPreambleAndLineageTests(unittest.TestCase):
    def test_dry_run_argv_shows_id_preamble(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, SINGLE_TASK_TASKS_TEXT)
            before = (kit_dir / "TASKS.md").read_bytes()

            with mock.patch.object(ce, "subprocess") as mock_subprocess:
                mock_subprocess.run.side_effect = AssertionError("subprocess in dry-run")
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    ce.main(
                        ["run", "--kit", str(kit_dir), "--copilot-bin", STUB_BIN, "--dry-run"]
                    )
            output = buf.getvalue()
            dispatch_line = next(
                line for line in output.splitlines() if line.startswith("dispatch:")
            )
            self.assertIn("[kit=kit run=", dispatch_line)
            self.assertIn("task=E1]", dispatch_line)

            after = (kit_dir / "TASKS.md").read_bytes()
            self.assertEqual(before, after)
            self.assertFalse((kit_dir / "NOTES.md").exists())

    def test_real_run_outcome_line_carries_run_id(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, SINGLE_TASK_TASKS_TEXT)

            stub_path = tmp / STUB_BIN
            log_path = tmp / "stub.log"
            stub_path.write_text(STUB_SHELL_TEMPLATE.format(log=log_path))
            stub_path.chmod(0o755)

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ce.main(["run", "--kit", str(kit_dir), "--copilot-bin", str(stub_path)])

            notes_text = (kit_dir / "NOTES.md").read_text()
            self.assertRegex(
                notes_text,
                r"outcome: E1 model=\S+ attempts=1 result=pass review=none run=\d{4}-\d{2}-\d{2}-[0-9a-f]{4}",
            )
            self.assertNotIn("parent=", notes_text)

    def test_parent_flag_lands_on_the_outcome_line_as_escalated_pass(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, SINGLE_TASK_TASKS_TEXT)

            stub_path = tmp / STUB_BIN
            log_path = tmp / "stub.log"
            stub_path.write_text(STUB_SHELL_TEMPLATE.format(log=log_path))
            stub_path.chmod(0o755)

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ce.main(
                    [
                        "run", "--kit", str(kit_dir), "--copilot-bin", str(stub_path),
                        "--parent", "X1",
                    ]
                )

            notes_text = (kit_dir / "NOTES.md").read_text()
            self.assertIn("result=escalated-pass", notes_text)
            self.assertIn("parent=X1", notes_text)

    def test_parent_equal_to_the_task_id_is_rejected_before_anything_is_written(self):
        """A task is never its own parent. `routing_scorecard` DROPS a self-referencing
        `parent=` with a note while still counting the `escalated-pass` it caused, so writing
        one would put a single line into a headline figure and into the "ignored" list at once
        -- the invariant the Phase 1 review adopted (F2) and the Phase 2 review found missing
        on an earlier driver (F-E). Rejected here at the writer: no status flip, no NOTES.md,
        no dispatch."""
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, SINGLE_TASK_TASKS_TEXT)
            before = (kit_dir / "TASKS.md").read_bytes()

            err = io.StringIO()
            with mock.patch.object(ce, "subprocess") as mock_subprocess:
                mock_subprocess.run.side_effect = AssertionError(
                    "dispatched despite a rejected --parent"
                )
                with contextlib.redirect_stderr(err):
                    with self.assertRaises(SystemExit) as ctx:
                        ce.main(
                            ["run", "--kit", str(kit_dir), "--copilot-bin", STUB_BIN,
                             "--parent", "E1"]
                        )
                mock_subprocess.run.assert_not_called()

            self.assertEqual(ctx.exception.code, 2)
            self.assertIn("cannot be its own", err.getvalue())
            self.assertEqual(before, (kit_dir / "TASKS.md").read_bytes())
            self.assertFalse((kit_dir / "NOTES.md").exists())


# ---- 19. `parent=` rides ONLY an escalation result (Phases 3-4 review, P34-F2) ----------------

# Same single fixture task as SINGLE_TASK_TASKS_TEXT, but with a verify command that can never
# pass -- so the whole ladder fails and the run ends `blocked`. Dispatch still goes to the temp
# STUB executable only; `false` is a shell builtin, not a CLI.
BLOCKED_TASK_TASKS_TEXT = SINGLE_TASK_TASKS_TEXT.replace("```bash\ntrue\n```",
                                                         "```bash\nfalse\n```")


class ParentOnlyOnEscalationResultTests(unittest.TestCase):
    """`bin/routing_scorecard.py`'s `build_lineage` keeps `parent=` ONLY when the carrying
    outcome's own `result` is `escalated-pass`; any other placement is dropped with an "out of
    grammar, ignored" note WHILE the classification that same line produced is still counted --
    one line in a headline figure and in the "ignored" list at once, the F2 invariant, from the
    writer side. So a run given `--parent` that ends BLOCKED must write no `parent=` at all.

    The pre-existing `--parent` tests only ever exercised a PASSING run, which is why the
    unconditional pass-through shipped; these exercise the blocked and escalated paths as a
    pair.
    """

    @staticmethod
    def _blocked_result():
        return {
            "id": "T7", "status": "blocked", "model_used": "fake-front",
            "escalations": ["fake-strong", "fake-front"], "verify_rc": 1,
            "agent": "implementer",
        }

    def test_append_note_blocked_with_parent_writes_no_parent_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes_path = Path(tmp) / "NOTES.md"
            task = {"id": "T7", "model": "fake-mid-a"}
            ce.append_note(
                notes_path, self._blocked_result(), task,
                run_id="2026-07-26-abcd", parent="T4",
            )
            text = notes_path.read_text()
            self.assertIn("result=blocked", text)
            self.assertNotIn("parent=", text)
            self.assertNotIn("T4", text)

    def test_append_note_escalated_with_parent_still_writes_parent_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes_path = Path(tmp) / "NOTES.md"
            task = {"id": "T7", "model": "fake-mid-a"}
            result = {
                "id": "T7", "status": "done", "model_used": "fake-strong",
                "escalations": ["fake-strong"], "verify_rc": 0, "agent": "implementer",
            }
            ce.append_note(notes_path, result, task, run_id="2026-07-26-abcd", parent="T4")
            text = notes_path.read_text()
            self.assertIn("result=escalated-pass", text)
            self.assertIn("parent=T4", text)

    def test_build_outcome_line_itself_is_unchanged(self):
        """The gate lives in `append_note`, not in the line builder: `build_outcome_line` is a
        pure formatter and still writes whatever `parent` it is handed (T2's callers depend on
        that, and nothing else in the file may quietly re-interpret its arguments)."""
        line = ce.build_outcome_line("T7", "fake-front", 3, "blocked", parent="T4")
        self.assertTrue(line.endswith(" parent=T4"))

    def test_end_to_end_blocked_run_with_parent_flag_writes_no_parent(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, BLOCKED_TASK_TASKS_TEXT)

            stub_path = tmp / STUB_BIN
            log_path = tmp / "stub.log"
            stub_path.write_text(STUB_SHELL_TEMPLATE.format(log=log_path))
            stub_path.chmod(0o755)

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                with self.assertRaises(SystemExit) as ctx:  # a blocked task exits nonzero
                    ce.main(
                        [
                            "run", "--kit", str(kit_dir), "--copilot-bin", str(stub_path),
                            "--parent", "X1",
                        ]
                    )
            self.assertEqual(ctx.exception.code, 1)

            notes_text = (kit_dir / "NOTES.md").read_text()
            self.assertIn("result=blocked", notes_text)
            self.assertNotIn("parent=", notes_text)
            self.assertNotIn("X1", notes_text)
            # stdout stays machine-clean: the omission is silent, never a warning line.
            self.assertNotIn("parent", buf.getvalue())


class ParsePlanBudgetTests(unittest.TestCase):
    def test_absent_plan_returns_none(self):
        self.assertIsNone(ce.parse_plan_budget(None))
        self.assertIsNone(ce.parse_plan_budget(""))

    def test_no_budget_line_returns_none(self):
        self.assertIsNone(ce.parse_plan_budget("# PLAN\n\nautonomy: advisory\n"))

    def test_all_three_keys_parsed(self):
        text = "# PLAN\n\nbudget: max-dispatches=5 max-escalations=2 max-consults=1\n"
        self.assertEqual(
            ce.parse_plan_budget(text),
            {"max-dispatches": 5, "max-escalations": 2, "max-consults": 1},
        )

    def test_subset_of_keys_parsed(self):
        self.assertEqual(
            ce.parse_plan_budget("budget: max-dispatches=3\n"), {"max-dispatches": 3},
        )

    def test_never_confused_with_the_dollar_savings_budget_flag(self):
        # `--budget`/`cmd_budget` writes its OWN `- budget: standard=... actual=...` line
        # family (a completely different feature, PLAN D5) -- that line must never be
        # mistaken for this PLAN.md dial's `budget:` line by parse_plan_budget.
        dollar_budget_note = (
            "- budget: standard=fake-mid-a actual=fake-cheap profile=M "
            "est_standard_usd=0.0100 est_actual_usd=0.0050 delta_usd=+0.0050 status=done"
        )
        self.assertIsNone(ce.parse_plan_budget(dollar_budget_note))


class CountPlanBudgetUsageTests(unittest.TestCase):
    def test_empty_notes_all_zero(self):
        self.assertEqual(
            ce.count_plan_budget_usage(""),
            {"max-dispatches": 0, "max-escalations": 0, "max-consults": 0},
        )

    def test_sums_attempts_and_escalations_across_lines(self):
        notes = "\n".join([
            "- outcome: A1 model=fake-cheap attempts=1 result=pass review=none",
            "- outcome: A2 model=fake-strong attempts=3 result=escalated-pass review=none",
        ])
        used = ce.count_plan_budget_usage(notes)
        self.assertEqual(used["max-dispatches"], 4)
        self.assertEqual(used["max-escalations"], 2)
        self.assertEqual(used["max-consults"], 0)

    def test_parent_bearing_line_counts_one_consult(self):
        notes = ("- outcome: A1 model=fake-front attempts=1 result=escalated-pass "
                  "review=none run=2026-07-26-aaaa parent=X1")
        used = ce.count_plan_budget_usage(notes)
        self.assertEqual(used["max-consults"], 1)


class PlanBudgetExhaustedTests(unittest.TestCase):
    def test_none_exhausted_below_all_caps(self):
        budget = {"max-dispatches": 5, "max-escalations": 3, "max-consults": 1}
        used = {"max-dispatches": 2, "max-escalations": 0, "max-consults": 0}
        self.assertIsNone(ce.plan_budget_exhausted(budget, used, is_consult=False))

    def test_dispatches_cap_reached_at_equality(self):
        budget = {"max-dispatches": 2}
        used = {"max-dispatches": 2, "max-escalations": 0, "max-consults": 0}
        self.assertEqual(ce.plan_budget_exhausted(budget, used, is_consult=False), "max-dispatches")

    def test_consults_cap_only_checked_when_this_run_is_a_consult(self):
        budget = {"max-consults": 1}
        used = {"max-dispatches": 0, "max-escalations": 0, "max-consults": 1}
        self.assertIsNone(ce.plan_budget_exhausted(budget, used, is_consult=False))
        self.assertEqual(ce.plan_budget_exhausted(budget, used, is_consult=True), "max-consults")


class EndToEndPlanBudgetStopTests(unittest.TestCase):
    def test_budget_stop_before_dispatch_leaves_task_untouched_and_writes_ledger_line(self):
        """A PLAN.md `budget:` cap already reached by NOTES.md's own recorded history stops
        the run cleanly BEFORE any dispatch: no subprocess call, TASKS.md's status line
        unchanged (still pending), and exactly one `outcome: ... result=budget-stop` line
        (carrying `run=`) is appended to NOTES.md."""
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, SINGLE_TASK_TASKS_TEXT)  # task id E1, no model pin
            (kit_dir / "PLAN.md").write_text("# PLAN\n\nbudget: max-dispatches=1\n")
            (kit_dir / "NOTES.md").write_text(
                "## 2026-07-25T00:00:00Z — E0\n"
                "- outcome: E0 model=fake-cheap attempts=1 result=pass review=none "
                "run=2026-07-25-1234\n"
            )
            before_tasks_text = (kit_dir / "TASKS.md").read_text()

            with mock.patch.object(ce, "subprocess") as mock_subprocess:
                mock_subprocess.run.side_effect = AssertionError(
                    "dispatched despite an exhausted PLAN.md budget"
                )
                err = io.StringIO()
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    with contextlib.redirect_stderr(err):
                        with self.assertRaises(SystemExit) as ctx:
                            ce.main(
                                ["run", "--kit", str(kit_dir), "--copilot-bin", "unused-stub"]
                            )
                mock_subprocess.run.assert_not_called()

            self.assertEqual(ctx.exception.code, 1)
            self.assertIn("budget-stop", err.getvalue())
            self.assertIn("max-dispatches", err.getvalue())

            after_tasks_text = (kit_dir / "TASKS.md").read_text()
            self.assertEqual(before_tasks_text, after_tasks_text)
            tasks = ce.parse_tasks(after_tasks_text)
            self.assertEqual(tasks[0]["status"], "pending")

            notes_text = (kit_dir / "NOTES.md").read_text()
            self.assertRegex(
                notes_text,
                r"outcome: E1 model=unpinned attempts=0 result=budget-stop review=none "
                r"run=\d{4}-\d{2}-\d{2}-[0-9a-f]{4}",
            )
            self.assertIn("remaining tasks untouched: 1", notes_text)

    def test_budget_stop_is_not_recorded_when_the_task_already_has_a_verdict(self):
        """A `budget-stop` is not a verdict and must never displace one.

        Resuming an already-`blocked` task after the cap is spent is an ordinary gesture, and
        the budget gate fires BEFORE any status check -- so without this guard the driver
        appends a budget-stop line for a task id that already carries `result=blocked`, and the
        reader's last-wins rule drops the verdict and its `failure=` class from the kit card.
        The stop itself still happens (nothing dispatched, exit 1, both stderr lines); only the
        LEDGER WRITE is declined, so no line lands that the reader would have to ignore."""
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, SINGLE_TASK_TASKS_TEXT)  # task id E1, no model pin
            (kit_dir / "PLAN.md").write_text("# PLAN\n\nbudget: max-dispatches=1\n")
            recorded = (
                "## 2026-07-25T00:00:00Z — E1\n"
                "- outcome: E1 model=unpinned attempts=2 result=blocked review=revised "
                "run=2026-07-25-1234 failure=verification\n"
            )
            (kit_dir / "NOTES.md").write_text(recorded)
            before_tasks_text = (kit_dir / "TASKS.md").read_text()

            with mock.patch.object(ce, "subprocess") as mock_subprocess:
                mock_subprocess.run.side_effect = AssertionError(
                    "dispatched despite an exhausted PLAN.md budget"
                )
                err = io.StringIO()
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    with contextlib.redirect_stderr(err):
                        with self.assertRaises(SystemExit) as ctx:
                            ce.main(
                                ["run", "--kit", str(kit_dir), "--task", "E1",
                                 "--copilot-bin", "unused-stub"]
                            )
                mock_subprocess.run.assert_not_called()

            self.assertEqual(ctx.exception.code, 1)
            self.assertIn("budget-stop", err.getvalue())
            self.assertIn("NOT recorded in the ledger", err.getvalue())
            self.assertIn("result=blocked", err.getvalue())

            self.assertEqual((kit_dir / "NOTES.md").read_text(), recorded)
            self.assertEqual((kit_dir / "TASKS.md").read_text(), before_tasks_text)

    def test_budget_stop_after_an_earlier_budget_stop_is_still_recorded(self):
        """The guard rejects only a real VERDICT. A prior `budget-stop` for the same id is not
        one, so a second stop records normally -- the guard must not silence the dial."""
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, SINGLE_TASK_TASKS_TEXT)
            (kit_dir / "PLAN.md").write_text("# PLAN\n\nbudget: max-dispatches=1\n")
            (kit_dir / "NOTES.md").write_text(
                "## 2026-07-25T00:00:00Z — E0\n"
                "- outcome: E0 model=fake-cheap attempts=1 result=pass review=none "
                "run=2026-07-25-1234\n"
                "## 2026-07-25T01:00:00Z — E1\n"
                "- outcome: E1 model=unpinned attempts=0 result=budget-stop review=none "
                "run=2026-07-25-5678\n"
            )

            with mock.patch.object(ce, "subprocess") as mock_subprocess:
                mock_subprocess.run.side_effect = AssertionError("dispatched")
                err = io.StringIO()
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    with contextlib.redirect_stderr(err):
                        with self.assertRaises(SystemExit):
                            ce.main(
                                ["run", "--kit", str(kit_dir), "--task", "E1",
                                 "--copilot-bin", "unused-stub"]
                            )

            self.assertNotIn("NOT recorded in the ledger", err.getvalue())
            self.assertEqual(
                (kit_dir / "NOTES.md").read_text().count("result=budget-stop"), 2)

    def test_recorded_outcome_result_reads_the_last_line_for_that_id_only(self):
        notes = (
            "- outcome: A1 model=fake-cheap attempts=1 result=pass review=none\n"
            "outcome: A2 model=fake-cheap attempts=1 result=blocked review=none\n"
            "- outcome: A1 model=fake-cheap attempts=2 result=retry-pass review=clean\n"
        )
        self.assertEqual(ce.recorded_outcome_result(notes, "A1"), "retry-pass")
        self.assertEqual(ce.recorded_outcome_result(notes, "A2"), "blocked")
        self.assertIsNone(ce.recorded_outcome_result(notes, "A3"))
        self.assertIsNone(ce.recorded_outcome_result("", "A1"))

    def test_absent_budget_block_is_unaffected_today_behavior(self):
        """No PLAN.md at all -> the run dispatches normally, exactly as it did before T9."""
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, SINGLE_TASK_TASKS_TEXT)

            stub_path = tmp / STUB_BIN
            log_path = tmp / "stub.log"
            stub_path.write_text(STUB_SHELL_TEMPLATE.format(log=log_path))
            stub_path.chmod(0o755)

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ce.main(["run", "--kit", str(kit_dir), "--copilot-bin", str(stub_path)])

            tasks = ce.parse_tasks((kit_dir / "TASKS.md").read_text())
            self.assertEqual(tasks[0]["status"], "done")
            notes_text = (kit_dir / "NOTES.md").read_text()
            self.assertIn("result=pass", notes_text)
            self.assertNotIn("budget-stop", notes_text)


if __name__ == "__main__":
    unittest.main()
