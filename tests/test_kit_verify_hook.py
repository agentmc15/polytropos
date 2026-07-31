"""Stdlib unittest regression suite for bin/kit_verify_hook.py.

bin/ is not a package; kit_verify_hook.py is loaded via importlib by absolute path computed
from this file's own location, per the repo's `BIN_DIR = Path(__file__).resolve().parent.parent
/ "bin"` convention (same pattern as tests/test_codex_execute.py).

============================================================================================
 SAFETY CONTRACT -- read this before adding a test here
============================================================================================
No test in this file ever invokes a real `claude`/`copilot`/`codex` binary. `precheck`'s
"verify command" is always a synthetic shell one-liner (`true`, `false`, a tiny inline Python
`-c` snippet) run through the module's own injectable-runner seam or its real `default_runner`
shelling to a harmless synthetic command -- never anything that dispatches an AI harness. Every
fixture lives under a fresh `tempfile.TemporaryDirectory()`; nothing here reads or writes the
real `.claude/kits/` in this repo, and `Path.home()` is never called anywhere in this file OR
(verified below by an AST walk, not a string grep -- see StaticSafetyTests) in the module under
test.
"""

import ast
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


kvh = _load("kit_verify_hook")


# ---- fixtures ---------------------------------------------------------------------------------

FIXTURE_TASKS_TEXT = """# TASKS -- fixture kit

### T1 — First fixture task
- status: done
- model: sonnet
- depends: (none)
- Verify: `true`

### T2 — Second fixture task
- status: in-progress
- model: sonnet
- depends: (none)
- Verify: `true`

### T3 — Third fixture task
- status: pending
- model: sonnet
- depends: T2
- Verify: `true`
"""


def _write_kit(root, slug="fixture-kit", tasks_text=FIXTURE_TASKS_TEXT):
    """Build `<root>/.claude/kits/<slug>/TASKS.md` and return (kit_dir, tasks_path)."""
    kit_dir = Path(root) / ".claude" / "kits" / slug
    kit_dir.mkdir(parents=True, exist_ok=True)
    tasks_path = kit_dir / "TASKS.md"
    tasks_path.write_text(tasks_text)
    return kit_dir, tasks_path


def _edit_event(cwd, file_path, old_str, new_str, tool_name="Edit"):
    return {
        "session_id": "abc123",
        "cwd": str(cwd),
        "hook_event_name": "PostToolUse",
        "tool_name": tool_name,
        "tool_input": {
            "file_path": str(file_path),
            "edits": [{"operation": "str_replace", "old_str": old_str, "new_str": new_str}],
        },
        "tool_use_id": "toolu_01FIXTURE",
    }


# ---- (a) record: marker write/read round-trip -------------------------------------------------

class MarkerRoundTripTests(unittest.TestCase):
    def test_write_marker_then_marker_exists_and_read_marker_time_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            kit_dir, _ = _write_kit(d)
            self.assertFalse(kvh.marker_exists(kit_dir, "T2"))
            self.assertIsNone(kvh.read_marker_time(kit_dir, "T2"))

            now = datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc)
            path = kvh.write_marker(kit_dir, "T2", "true", now=now)

            self.assertTrue(path.exists())
            self.assertTrue(kvh.marker_exists(kit_dir, "T2"))
            self.assertEqual(kvh.read_marker_time(kit_dir, "T2"), now)
            # marker lives under the kit-local, gitignored verify-pass/ directory
            self.assertEqual(path.parent, kit_dir / "verify-pass")

    def test_record_writes_marker_when_no_precheck_exists(self):
        with tempfile.TemporaryDirectory() as d:
            kit_dir, _ = _write_kit(d)
            ok, message = kvh.run_record(kit_dir, "T2", "true")
            self.assertTrue(ok)
            self.assertIn("T2", message)
            self.assertTrue(kvh.marker_exists(kit_dir, "T2"))


# ---- (a2) precheck: tautological-verify detection ----------------------------------------------

class PrecheckTautologicalTests(unittest.TestCase):
    def test_precheck_on_a_pre_task_passing_verify_emits_defect_and_blocks_record(self):
        with tempfile.TemporaryDirectory() as d:
            kit_dir, _ = _write_kit(d)
            calls = []

            def fake_runner(cmd):
                calls.append(cmd)
                return 0, "already passing"  # tautological: pre-task tree already satisfies it

            buf = _capture_stdout(lambda: kvh.run_precheck(kit_dir, "T2", "true", fake_runner))
            self.assertEqual(calls, ["true"])
            # IN-GRAMMAR order: `defect: <task-id> kind=<kebab-token>`. The old
            # `defect: tautological-verify task=T2` form carried no `kind=` pair, so the
            # scorecard dropped the whole line as unrecognized (proved by the test below).
            self.assertIn("defect: T2 kind=tautological-verify", buf)
            self.assertNotIn("defect: tautological-verify", buf)

            record = kvh.read_precheck(kit_dir, "T2")
            self.assertTrue(record["tautological"])
            self.assertEqual(record["verify_cmd"], "true")

            # record refuses the SAME verify command
            ok, message = kvh.run_record(kit_dir, "T2", "true")
            self.assertFalse(ok)
            self.assertIn("refused", message)
            self.assertFalse(kvh.marker_exists(kit_dir, "T2"))

    def test_precheck_defect_line_parses_under_the_repos_own_defect_grammar(self):
        """The writer and the READER must agree. `precheck`'s defect line lands in a
        machine-read ledger family, so it is asserted against the real consumer --
        `bin/routing_scorecard.py`'s `parse_defects` -- not against a hand-copied regex. Loading
        that module here is a pure-function parse over an in-memory string: no disk, no home
        directory, no subprocess, no CLI (the lazy-load-inside-a-test pattern
        tests/test_telemetry_snapshot.py already uses)."""
        rs = _load("routing_scorecard")
        with tempfile.TemporaryDirectory() as d:
            kit_dir, _ = _write_kit(d)
            buf = _capture_stdout(
                lambda: kvh.run_precheck(kit_dir, "T2", "true", lambda cmd: (0, "already"))
            )
            events, notes = rs.parse_defects(buf)
            self.assertEqual(events, [{"task": "T2", "kind": "tautological-verify"}])
            self.assertEqual(notes, [])

            # And the pre-fix field order really was unparseable -- the assertion above is
            # discriminating, not vacuous.
            old_form = "defect: tautological-verify task=T2 verify already passes\n"
            old_events, old_notes = rs.parse_defects(old_form)
            self.assertEqual(old_events, [])
            self.assertEqual(len(old_notes), 1)
            self.assertIn("unrecognized defect line", old_notes[0])

    def test_record_succeeds_once_the_verify_command_changes(self):
        with tempfile.TemporaryDirectory() as d:
            kit_dir, _ = _write_kit(d)

            def tautological_runner(cmd):
                return 0, ""

            _capture_stdout(
                lambda: kvh.run_precheck(kit_dir, "T2", "true", tautological_runner)
            )
            # the verify command text is now different from what precheck saw -- refusal lifts
            ok, message = kvh.run_record(kit_dir, "T2", "python3 -m unittest discover -s tests")
            self.assertTrue(ok)
            self.assertTrue(kvh.marker_exists(kit_dir, "T2"))

    def test_precheck_on_a_genuinely_failing_pre_task_verify_is_not_tautological(self):
        with tempfile.TemporaryDirectory() as d:
            kit_dir, _ = _write_kit(d)

            def failing_runner(cmd):
                return 1, "not yet implemented"

            buf = _capture_stdout(
                lambda: kvh.run_precheck(kit_dir, "T2", "false", failing_runner)
            )
            self.assertNotIn("defect:", buf)
            record = kvh.read_precheck(kit_dir, "T2")
            self.assertFalse(record["tautological"])

            ok, _message = kvh.run_record(kit_dir, "T2", "false")
            self.assertTrue(ok)
            self.assertTrue(kvh.marker_exists(kit_dir, "T2"))


def _capture_stdout(fn):
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn()
    return buf.getvalue()


# ---- (b) hook: PostToolUse enforcement ---------------------------------------------------------

class HookEnforcementTests(unittest.TestCase):
    def test_hook_blocks_a_marker_less_done_flip(self):
        with tempfile.TemporaryDirectory() as d:
            kit_dir, tasks_path = _write_kit(d)
            # simulate the edit having already landed on disk (PostToolUse fires AFTER the tool
            # ran), flipping T2 from in-progress to done
            tasks_path.write_text(
                tasks_path.read_text().replace("- status: in-progress", "- status: done")
            )
            old_str = "### T2 — Second fixture task\n- status: in-progress"
            new_str = "### T2 — Second fixture task\n- status: done"
            event = _edit_event(d, tasks_path, old_str, new_str)

            found = kvh.detect_done_flip(event)
            self.assertIsNotNone(found)
            found_kit_dir, task_id = found
            self.assertEqual(task_id, "T2")
            self.assertEqual(found_kit_dir, kit_dir)

            allow, message = kvh.evaluate_hook_event(event)
            self.assertFalse(allow)
            self.assertIn("T2", message)
            self.assertIn("no verify-pass marker", message)

    def test_hook_passes_a_fresh_marker_flip(self):
        with tempfile.TemporaryDirectory() as d:
            kit_dir, tasks_path = _write_kit(d)
            tasks_path.write_text(
                tasks_path.read_text().replace("- status: in-progress", "- status: done")
            )
            old_str = "### T2 — Second fixture task\n- status: in-progress"
            new_str = "### T2 — Second fixture task\n- status: done"
            event = _edit_event(d, tasks_path, old_str, new_str)

            kvh.write_marker(kit_dir, "T2", "true")

            allow, message = kvh.evaluate_hook_event(event)
            self.assertTrue(allow)
            self.assertEqual(message, "")

    def test_hook_ignores_edits_that_do_not_touch_a_kit_tasks_md(self):
        with tempfile.TemporaryDirectory() as d:
            other_path = Path(d) / "README.md"
            other_path.write_text("status: done\n")
            event = _edit_event(d, other_path, "old", "status: done")
            allow, message = kvh.evaluate_hook_event(event)
            self.assertTrue(allow)
            self.assertEqual(message, "")

    def test_hook_ignores_edits_that_do_not_flip_to_done(self):
        with tempfile.TemporaryDirectory() as d:
            kit_dir, tasks_path = _write_kit(d)
            tasks_path.write_text(
                tasks_path.read_text().replace("- status: pending", "- status: in-progress")
            )
            event = _edit_event(
                d, tasks_path,
                "### T3 — Third fixture task\n- status: pending",
                "### T3 — Third fixture task\n- status: in-progress",
            )
            allow, message = kvh.evaluate_hook_event(event)
            self.assertTrue(allow)
            self.assertEqual(message, "")

    def test_hook_ignores_the_write_tool_for_a_kit_tasks_md(self):
        """Documented payload gap: Write's tool_input carries only the new file_contents, no
        prior content, so a genuine flip cannot be diff-checked -- the hook is a silent no-op."""
        with tempfile.TemporaryDirectory() as d:
            kit_dir, tasks_path = _write_kit(d)
            new_text = tasks_path.read_text().replace(
                "- status: in-progress", "- status: done"
            )
            tasks_path.write_text(new_text)
            event = {
                "cwd": str(d),
                "hook_event_name": "PostToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": str(tasks_path), "file_contents": new_text},
            }
            allow, message = kvh.evaluate_hook_event(event)
            self.assertTrue(allow)
            self.assertEqual(message, "")

    def test_hook_ambiguous_snippet_falls_back_to_scanning_current_file(self):
        """When old_str/new_str omit the heading (only valid when the status text was already
        unique file-wide), attribution falls back to scanning the current on-disk file. Uses a
        fixture with NO pre-existing `done` task, so "- status: done" is unique post-edit --
        the one scenario where a heading-less snippet is actually unambiguous."""
        no_prior_done_text = """# TASKS -- fixture kit

### T2 — Second fixture task
- status: in-progress
- model: sonnet
- depends: (none)

### T3 — Third fixture task
- status: pending
- model: sonnet
- depends: T2
"""
        with tempfile.TemporaryDirectory() as d:
            kit_dir, tasks_path = _write_kit(d, tasks_text=no_prior_done_text)
            tasks_path.write_text(
                tasks_path.read_text().replace("- status: in-progress", "- status: done")
            )
            # no heading in the snippet this time -- "- status: in-progress" was unique
            # file-wide pre-edit (only T2 had it), so Edit's uniqueness contract permits this
            event = _edit_event(d, tasks_path, "- status: in-progress", "- status: done")
            found = kvh.detect_done_flip(event)
            self.assertEqual(found, (kit_dir, "T2"))


# ---- freshness fix: precheck-invalidates + verify-command-match (the T4 re-fix) ----------------

def _done_flip_event(d, tasks_path):
    tasks_path.write_text(
        tasks_path.read_text().replace("- status: in-progress", "- status: done")
    )
    return _edit_event(
        d, tasks_path,
        "### T2 — Second fixture task\n- status: in-progress",
        "### T2 — Second fixture task\n- status: done",
    )


class FreshnessTests(unittest.TestCase):
    def test_precheck_then_record_round_trips(self):
        """The sanctioned attempt cycle: precheck (fails pre-task, so non-tautological) ->
        implementation -> record a real pass -> the done flip is allowed."""
        with tempfile.TemporaryDirectory() as d:
            kit_dir, tasks_path = _write_kit(d)

            kvh.run_precheck(kit_dir, "T2", "true", lambda cmd: (1, "not yet implemented"))
            self.assertFalse(kvh.marker_exists(kit_dir, "T2"))

            ok, _message = kvh.run_record(kit_dir, "T2", "true")
            self.assertTrue(ok)
            self.assertTrue(kvh.marker_exists(kit_dir, "T2"))

            event = _done_flip_event(d, tasks_path)
            allow, message = kvh.evaluate_hook_event(event)
            self.assertTrue(allow)
            self.assertEqual(message, "")

    def test_stale_marker_across_attempts_is_blocked(self):
        """A marker earned in an EARLIER attempt must not certify a LATER done flip. Simulates
        done -> in-progress -> done again: the second attempt's `precheck` deletes the first
        attempt's marker, so a done flip with no fresh `record` is blocked -- closing the gap
        the orchestrator identified (marker-existence-only certifying any later flip)."""
        with tempfile.TemporaryDirectory() as d:
            kit_dir, tasks_path = _write_kit(d)

            # first attempt: precheck, then a genuine pass is recorded
            kvh.run_precheck(kit_dir, "T2", "true", lambda cmd: (1, "not yet"))
            kvh.run_record(kit_dir, "T2", "true")
            self.assertTrue(kvh.marker_exists(kit_dir, "T2"))
            first_marker_time = kvh.read_marker_time(kit_dir, "T2")
            self.assertIsNotNone(first_marker_time)

            # task flips done -> in-progress (a new attempt starts) -- precheck runs again
            buf = _capture_stdout(
                lambda: kvh.run_precheck(kit_dir, "T2", "true", lambda cmd: (1, "not yet"))
            )
            self.assertIn("invalidated the prior verify-pass marker", buf)
            self.assertIn("task=T2", buf)
            # the stale marker from the FIRST attempt is gone
            self.assertFalse(kvh.marker_exists(kit_dir, "T2"))

            # the done flip lands on disk WITHOUT a fresh `record` for this second attempt
            event = _done_flip_event(d, tasks_path)
            allow, message = kvh.evaluate_hook_event(event)
            self.assertFalse(allow)
            self.assertIn("no verify-pass marker", message)

    def test_changed_verify_command_invalidates_marker(self):
        """A marker certifies a SPECIFIC verify command string. If TASKS.md's `- Verify:` line
        for the task changes after the marker was earned (without a fresh precheck/record
        cycle), the hook must block -- no ordering rule catches this, only a text comparison."""
        with tempfile.TemporaryDirectory() as d:
            kit_dir, tasks_path = _write_kit(d)

            ok, _message = kvh.run_record(kit_dir, "T2", "true")
            self.assertTrue(ok)
            self.assertTrue(kvh.marker_exists(kit_dir, "T2"))

            # verify command rewritten in TASKS.md after the marker was earned, and status
            # flipped to done in the same edit
            rewritten_block = (
                "### T2 — Second fixture task\n"
                "- status: done\n"
                "- model: sonnet\n"
                "- depends: (none)\n"
                "- Verify: `false`"
            )
            original_block = (
                "### T2 — Second fixture task\n"
                "- status: in-progress\n"
                "- model: sonnet\n"
                "- depends: (none)\n"
                "- Verify: `true`"
            )
            new_text = tasks_path.read_text().replace(original_block, rewritten_block)
            tasks_path.write_text(new_text)
            event = _edit_event(
                d, tasks_path,
                "### T2 — Second fixture task\n- status: in-progress",
                "### T2 — Second fixture task\n- status: done",
            )

            allow, message = kvh.evaluate_hook_event(event)
            self.assertFalse(allow)
            self.assertIn("verify command", message.lower())
            self.assertIn("`true`", message)
            self.assertIn("`false`", message)

    def test_matching_verify_command_after_record_is_allowed(self):
        """Sanity counterpart to the mismatch test: an UNCHANGED verify command still passes."""
        with tempfile.TemporaryDirectory() as d:
            kit_dir, tasks_path = _write_kit(d)
            kvh.run_record(kit_dir, "T2", "true")
            event = _done_flip_event(d, tasks_path)
            allow, message = kvh.evaluate_hook_event(event)
            self.assertTrue(allow)
            self.assertEqual(message, "")

    def test_unparsable_verify_line_falls_back_to_existence_only(self):
        """A kit TASKS.md that carries no verify command in EITHER supported dialect -- neither
        a `- Verify: `cmd`` line nor a `**Verify.**`/`**Verify:**` fenced block (a format this
        module doesn't require; see VerifyDialectTests for the dialects it does read) -- can't be
        command-matched, so the check is skipped and marker existence + precheck-freshness alone
        govern: fail-open on the unparsable case rather than blocking something it can't
        evaluate."""
        no_verify_line_text = """# TASKS -- fixture kit

### T2 — Second fixture task
- status: in-progress
- model: sonnet
- depends: (none)
"""
        with tempfile.TemporaryDirectory() as d:
            kit_dir, tasks_path = _write_kit(d, tasks_text=no_verify_line_text)
            kvh.run_record(kit_dir, "T2", "some-command-not-in-tasks-md")
            event = _done_flip_event(d, tasks_path)
            allow, message = kvh.evaluate_hook_event(event)
            self.assertTrue(allow)
            self.assertEqual(message, "")


# ---- verify DIALECT coverage: the fenced form 25 of this repo's 27 kits actually use ------------

# Deliberately carries NO `- Verify: `cmd`` line anywhere: the dialect the original parser
# understood is absent, so every assertion below can only pass through the fenced path. T2 uses
# `**Verify.**` + a ```bash fence (22 of this repo's kits write it that way), T3 uses
# `**Verify:**` + a bare, language-less fence with a MULTI-LINE command (3 kits' form).
FENCED_TASKS_TEXT = """# TASKS -- fixture kit (fenced verify dialect)

### T1 — First fixture task
- status: done
- model: sonnet
- depends: (none)

**Verify.**
```bash
true
```

### T2 — Second fixture task
- status: in-progress
- model: sonnet
- depends: (none)

**Acceptance.** Fixture acceptance prose; mentions no fence of its own.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_fixture.py'
```

### T3 — Third fixture task
- status: pending
- model: sonnet
- depends: T2

**Verify:**
```
first-fixture-command &&
second-fixture-command
```
"""

# The third way a kit can write it (one kit in this repo does): a bold marker followed by a
# backticked one-liner rather than a fence. Neither dialect parses it -> documented fail-open.
BOLD_MARKER_NO_FENCE_TEXT = """# TASKS -- fixture kit (marker, no fence)

### T2 — Second fixture task
- status: in-progress
- model: sonnet
- depends: (none)

**Verify:**
`python3 -m unittest discover -s tests`
"""


class VerifyDialectTests(unittest.TestCase):
    def test_fenced_dialect_is_parsed_for_both_marker_spellings(self):
        """The regression F-D names: 2 of this repo's 27 kits use the `- Verify: `cmd`` line and
        25 carry a `**Verify.**`/`**Verify:**` marker (24 of them with a fenced block), so
        parsing only the first form made the command-match check inert on every kit this repo
        had actually executed."""
        self.assertNotIn("- Verify:", FENCED_TASKS_TEXT)  # the other dialect really is absent
        self.assertEqual(
            kvh._task_verify_cmd(FENCED_TASKS_TEXT, "T2"),
            "python3 -m unittest discover -s tests -p 'test_fixture.py'",
        )
        # `**Verify:**` (colon) + a fence with NO language tag + a multi-line command
        self.assertEqual(
            kvh._task_verify_cmd(FENCED_TASKS_TEXT, "T3"),
            "first-fixture-command &&\nsecond-fixture-command",
        )
        self.assertEqual(kvh._task_verify_cmd(FENCED_TASKS_TEXT, "T1"), "true")

    def test_single_line_dialect_still_parses_unchanged(self):
        """Additive: the original dialect keeps working exactly as before."""
        self.assertEqual(kvh._task_verify_cmd(FIXTURE_TASKS_TEXT, "T2"), "true")
        self.assertIsNone(kvh._task_verify_cmd(FIXTURE_TASKS_TEXT, "NOPE"))

    def test_marker_without_a_fence_is_not_guessed_at(self):
        """A bold marker followed by prose or a backticked one-liner is NOT this dialect: the
        parser requires the fence directly after the marker and otherwise returns None (skip the
        command-match check) rather than guessing. A false MATCH would let a rewritten verify
        certify a flip; a false MISS would block a legitimate one -- so fail open, exactly as the
        module docstring's DIALECT COVERAGE note states."""
        self.assertIsNone(kvh._task_verify_cmd(BOLD_MARKER_NO_FENCE_TEXT, "T2"))
        with tempfile.TemporaryDirectory() as d:
            kit_dir, tasks_path = _write_kit(d, tasks_text=BOLD_MARKER_NO_FENCE_TEXT)
            kvh.run_record(kit_dir, "T2", "a-command-that-is-not-in-tasks-md")
            allow, message = kvh.evaluate_hook_event(_done_flip_event(d, tasks_path))
            self.assertTrue(allow)
            self.assertEqual(message, "")

    def test_rewritten_fenced_verify_command_blocks_the_done_flip(self):
        """The half of the enforcement that was inert: a fenced-dialect kit whose verify command
        is rewritten after the marker was earned must now be caught."""
        with tempfile.TemporaryDirectory() as d:
            kit_dir, tasks_path = _write_kit(d, tasks_text=FENCED_TASKS_TEXT)
            earned = "python3 -m unittest discover -s tests -p 'test_fixture.py'"
            ok, _message = kvh.run_record(kit_dir, "T2", earned)
            self.assertTrue(ok)

            # the fence body is swapped for something that trivially passes
            tasks_path.write_text(tasks_path.read_text().replace(earned, "true"))

            allow, message = kvh.evaluate_hook_event(_done_flip_event(d, tasks_path))
            self.assertFalse(allow)
            self.assertIn("verify command", message.lower())
            self.assertIn(earned, message)
            self.assertIn("`true`", message)

    def test_unchanged_fenced_verify_command_is_allowed(self):
        """Counterpart: the same fenced kit, command untouched -> the flip passes."""
        with tempfile.TemporaryDirectory() as d:
            kit_dir, tasks_path = _write_kit(d, tasks_text=FENCED_TASKS_TEXT)
            ok, _message = kvh.run_record(
                kit_dir, "T2", "python3 -m unittest discover -s tests -p 'test_fixture.py'"
            )
            self.assertTrue(ok)
            allow, message = kvh.evaluate_hook_event(_done_flip_event(d, tasks_path))
            self.assertTrue(allow)
            self.assertEqual(message, "")


# ---- CLI end-to-end: record + hook wired through main() ----------------------------------------

class CliEndToEndTests(unittest.TestCase):
    def test_record_cli_then_hook_cli_round_trip(self):
        import io
        from unittest import mock

        with tempfile.TemporaryDirectory() as d:
            kit_dir, tasks_path = _write_kit(d)
            tasks_path.write_text(
                tasks_path.read_text().replace("- status: in-progress", "- status: done")
            )
            event = _edit_event(
                d, tasks_path,
                "### T2 — Second fixture task\n- status: in-progress",
                "### T2 — Second fixture task\n- status: done",
            )

            kvh.main(["record", "--kit-dir", str(kit_dir), "--task-id", "T2",
                      "--verify-cmd", "true"])
            self.assertTrue(kvh.marker_exists(kit_dir, "T2"))

            stdin_buf = io.StringIO(json.dumps(event))
            with mock.patch("sys.stdin", stdin_buf):
                try:
                    kvh.main(["hook"])
                except SystemExit as e:
                    self.fail(f"hook unexpectedly blocked a fresh-marker flip: exit {e.code}")

    def test_hook_cli_exits_nonzero_without_a_marker(self):
        import io
        from unittest import mock

        with tempfile.TemporaryDirectory() as d:
            kit_dir, tasks_path = _write_kit(d)
            tasks_path.write_text(
                tasks_path.read_text().replace("- status: in-progress", "- status: done")
            )
            event = _edit_event(
                d, tasks_path,
                "### T2 — Second fixture task\n- status: in-progress",
                "### T2 — Second fixture task\n- status: done",
            )
            stdin_buf = io.StringIO(json.dumps(event))
            with mock.patch("sys.stdin", stdin_buf):
                with self.assertRaises(SystemExit) as ctx:
                    kvh.main(["hook"])
            self.assertEqual(ctx.exception.code, 2)


# ---- static safety: no Path.home() CALL anywhere in the module under test ----------------------

class StaticSafetyTests(unittest.TestCase):
    def test_module_never_calls_path_home(self):
        """AST-based, not a string grep: this module's own docstring legitimately DISCUSSES
        `Path.home()` (as part of stating the safety contract), so a naive substring/grep check
        would false-flag a correct file (the house precedent this repo has already hit once).
        Only a real `ast.Call` node matching `Path.home(...)` counts."""
        source = (BIN_DIR / "kit_verify_hook.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "home"
                and isinstance(func.value, ast.Name)
                and func.value.id == "Path"
            ):
                self.fail("Path.home() called in bin/kit_verify_hook.py")

    def test_module_docstring_does_mention_path_home_as_documentation(self):
        """Sanity check on the test above: the string DOES appear in the file (as prose), so
        the AST check above is proven to be discriminating rather than vacuously passing."""
        source = (BIN_DIR / "kit_verify_hook.py").read_text(encoding="utf-8")
        self.assertIn("Path.home()", source)


if __name__ == "__main__":
    unittest.main()
