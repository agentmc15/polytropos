"""Stdlib unittest regression suite for bin/claude_execute.py.

bin/ is not a package; claude_execute.py is loaded via importlib by absolute path computed
from this file's own location, per the repo's `BIN_DIR = Path(__file__).resolve().parent.parent
/ "bin"` convention (same pattern as tests/test_codex_execute.py).

============================================================================================
 SAFETY CONTRACT -- read this before adding a test here
============================================================================================
No test in this file EVER invokes the real `claude` binary or touches the real `~/.claude`.
Every dispatch goes through one of two seams: an injected fake `runner`/`verify_runner`
callable (pure-function tests of `run_task`, `build_dispatch`, `escalation_ladder`), or a tiny
temp STUB shell executable written to a `tempfile.TemporaryDirectory()` and passed explicitly
via `--claude-bin` (the end-to-end `main(["run", ...])` tests) -- never a binary named `claude`
resolved off PATH. `Path.home()` is never called anywhere in this file or in
`bin/claude_execute.py`. The dry-run tests additionally prove the negative by patching
`subprocess` in the loaded module to raise if touched at all, then asserting the command
still completes and mutates/writes nothing.

`cmd_run`'s real (non-dry-run) path also calls `bin/kit_verify_hook.py`'s real
`run_precheck`/`run_record` functions (loaded from the ACTUAL repo module via the driver's own
`_load_verify_hook_module`) -- this is read/write ONLY under the temp kit fixture's own
`verify-pass/` directory (pure local file I/O, no subprocess, no CLI, no network), so it is
harmless even though it is "real" code rather than a stub.

Fixture ids (`fake-haiku`, `fake-opus-a`, `fake-opus-b`, `fake-frontier`) and every price in
`PRICING_FIXTURE` are synthetic and never appear in `data/pricing.json`. The fixture
deliberately leaves the `sonnet` tier EMPTY (not `opus`) -- mirroring
tests/test_codex_execute.py's empty-`mid` fixture -- so the skip-up rule is proven general,
not just "opus happens to be empty on today's real roster". End-to-end tests patch
`claude_execute.load_pricing` to return this synthetic dict so the real `data/pricing.json`
is never consulted for tier/escalation behavior; end-to-end tests that need a kit-agent
preamble write their OWN temp `.claude/agents/<slug>-<role>.md` fixture and patch `REPO_ROOT`
to that temp dir -- the real `.claude/agents/` bundle is never read by this file.
"""

import contextlib
import importlib.util
import io
import re
import shlex
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


ce = _load("claude_execute")


# ---- fixtures -----------------------------------------------------------------------------

# A synthetic STUB executable "name" used wherever a claude_bin value is required but no
# process is actually spawned (build_dispatch is a pure argv builder; run_task's
# runner/verify_runner are fakes). Deliberately not the real CLI's name.
STUB_BIN = "stub-cli"

# Fake pricing dict, tiers expressed in file order: haiku, opus (two entries), frontier.
# The `sonnet` tier is deliberately EMPTY -- and deliberately NOT `opus` -- so a passing
# skip-up assertion proves the rule is read from data, not hardcoded to today's real-roster
# shape. Round fake numbers only -- never the real roster's ids or rates.
PRICING_FIXTURE = {
    "models": {
        "fake-haiku": {"tier": "haiku", "input_per_mtok": 1.0, "output_per_mtok": 2.0},
        "fake-opus-a": {"tier": "opus", "input_per_mtok": 8.0, "output_per_mtok": 16.0},
        "fake-opus-b": {"tier": "opus", "input_per_mtok": 9.0, "output_per_mtok": 18.0},
        "fake-frontier": {"tier": "frontier", "input_per_mtok": 20.0, "output_per_mtok": 40.0},
    },
}

# Two phases, three tasks: T1 has a pinned model id and depends: (none); T2 has no model line
# at all and depends: (none); T3 pins a TIER WORD ("sonnet", empty -- resolves via skip-up)
# and depends: T1.
TASKS_TEXT_FIXTURE = """# TASKS -- fixture kit

## Phase 1 -- Made-up phase one

### T1 — First fixture task
- status: pending
- model: fake-haiku
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

## Phase 2 -- Made-up phase two

### T3 — Third fixture task
- status: pending
- model: sonnet
- depends: T1
- independent: no

**Brief.** Do the third fixture thing; depends on the first, pinned via an empty tier word.

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

# Three tasks for the dry-run "preview every pending task" acceptance criterion: T1/T2
# pending, T3 already done -- the preview must show T1/T2 and must NOT show T3.
DRY_RUN_ALL_PENDING_TASKS_TEXT = """## Phase 1 — Preview phase

### T1 — First pending task
- status: pending
- model: fake-haiku
- depends: (none)
- independent: yes

**Brief.** First pending fixture brief.

**Verify.**
```bash
true
```

### T2 — Second pending task
- status: pending
- model: fake-opus-a
- depends: (none)
- independent: yes

**Brief.** Second pending fixture brief.

**Verify.**
```bash
true
```

### T3 — Already done task
- status: done
- model: fake-haiku
- depends: (none)
- independent: yes

**Brief.** Already-done fixture brief; must not appear in the preview.

**Verify.**
```bash
true
```
"""


def _single_task_text(verify_cmd, task_id="E1", model="fake-haiku"):
    """A one-task kit whose verify command is caller-supplied (so tests can make it
    genuinely fail pre-task and pass post-task, or make it trivially tautological)."""
    return f"""## Phase 1 — Only phase

### {task_id} — Only fixture task
- status: pending
- model: {model}
- depends: (none)
- independent: yes

**Brief.** Fixture brief payload for the end-to-end stub-executable run.

**Acceptance.** Fake acceptance text for {task_id}.

**Verify.**
```bash
{verify_cmd}
```
"""


# A single-task kit whose verify command always FAILS, for the end-to-end
# escalation-exhausted run (never tautological: `false` never passes, pre- or post-task).
ESCALATION_TASKS_TEXT = _single_task_text("false", task_id="B1")


# A tiny bash STUB (never named after the real CLI): logs its argv MINUS the last element (the
# prompt -- which can be many KB of multi-line preamble text) behind a call-boundary marker,
# then (optionally) touches a "work done" marker file to simulate an implementer's edit, then
# exits 0. `%LOG%`/`%MARKER%` are replaced via str.replace (not str.format, since the script's
# own `${...}` array syntax would collide with format-string braces).
STUB_SHELL_TEMPLATE = """#!/bin/bash
echo "===CALL===" >> "%LOG%"
args=("$@")
n=${#args[@]}
unset "args[$((n-1))]"
printf '%s\\n' "${args[@]}" >> "%LOG%"
%TOUCH%
exit 0
"""


def _write_stub(tmp_path, log_path, marker_path=None):
    stub_path = Path(tmp_path) / STUB_BIN
    touch_line = f'touch "{marker_path}"' if marker_path else ":"
    body = STUB_SHELL_TEMPLATE.replace("%LOG%", str(log_path)).replace("%TOUCH%", touch_line)
    stub_path.write_text(body)
    stub_path.chmod(0o755)
    return stub_path


def _dispatched_models(log_text):
    """Per logged call (each stub invocation, argv minus the trailing prompt), the value that
    followed a `--model` flag, or None if the call had no `--model` pair."""
    blocks = [b for b in log_text.split("===CALL===\n") if b.strip() != ""]
    models = []
    for block in blocks:
        lines = [ln for ln in block.splitlines() if ln != ""]
        if "--model" in lines:
            models.append(lines[lines.index("--model") + 1])
        else:
            models.append(None)
    return models


# A fixture kit-agent bundle body, written to a TEMP repo_root only -- never the real
# `.claude/agents/` bundle. Carries frontmatter to strip.
PREAMBLE_FIXTURE_BODY = """---
name: fixturekit-implementer
description: fixture kit agent, never the real bundle
model: sonnet
---

Fixture kit-agent preamble body.
"""


def _write_kit(tmp_path, text, slug="fixturekit"):
    kit_dir = Path(tmp_path) / slug
    kit_dir.mkdir()
    (kit_dir / "TASKS.md").write_text(text)
    return kit_dir


def _write_agent_bundle(tmp_path, slug, role, body):
    agents_dir = Path(tmp_path) / ".claude" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / f"{slug}-{role}.md").write_text(body)
    return Path(tmp_path)


# ---- 1. parse_tasks ------------------------------------------------------------------------

class ParseTasksTests(unittest.TestCase):
    def test_fields_parsed_for_all_three_fixture_tasks(self):
        tasks = ce.parse_tasks(TASKS_TEXT_FIXTURE)
        by_id = {t["id"]: t for t in tasks}
        self.assertEqual(set(by_id), {"T1", "T2", "T3"})

        t1 = by_id["T1"]
        self.assertEqual(t1["title"], "First fixture task")
        self.assertEqual(t1["status"], "pending")
        self.assertEqual(t1["model"], "fake-haiku")
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
        self.assertEqual(t3["model"], "sonnet")  # raw tier word, unresolved at parse time
        self.assertEqual(t3["depends"], ["T1"])
        self.assertFalse(t3["independent"])

    def test_invalid_status_raises_value_error_listing_vocabulary(self):
        with self.assertRaises(ValueError) as ctx:
            ce.parse_tasks(INVALID_STATUS_TASKS_TEXT)
        msg = str(ctx.exception)
        for status_word in ce.STATUSES:
            self.assertIn(status_word, msg)


# ---- 2. tier resolution (skip-up) and escalation_ladder ------------------------------------

class TierResolutionAndEscalationLadderTests(unittest.TestCase):
    def test_empty_sonnet_tier_skips_up_to_opus_first_in_file_order(self):
        # `sonnet` has ZERO models in the fixture -- and it is not `opus` -- proving the
        # skip-up rule generalizes to whichever tier happens to be empty.
        self.assertEqual(ce.resolve_tier(PRICING_FIXTURE, "sonnet"), "fake-opus-a")

    def test_populated_tiers_resolve_directly(self):
        self.assertEqual(ce.resolve_tier(PRICING_FIXTURE, "haiku"), "fake-haiku")
        self.assertEqual(ce.resolve_tier(PRICING_FIXTURE, "opus"), "fake-opus-a")
        self.assertEqual(ce.resolve_tier(PRICING_FIXTURE, "frontier"), "fake-frontier")

    def test_unknown_tier_word_raises_keyerror_listing_vocabulary(self):
        with self.assertRaises(KeyError) as ctx:
            ce.resolve_tier(PRICING_FIXTURE, "nonsense-tier")
        msg = str(ctx.exception)
        for tier in ce.TIER_ORDER:
            self.assertIn(tier, msg)

    def test_resolve_model_passthrough_none_and_unknown(self):
        self.assertEqual(ce.resolve_model(PRICING_FIXTURE, "fake-frontier"), "fake-frontier")
        self.assertIsNone(ce.resolve_model(PRICING_FIXTURE, None))
        with self.assertRaises(KeyError) as ctx:
            ce.resolve_model(PRICING_FIXTURE, "not-a-model-or-tier")
        msg = str(ctx.exception)
        for mid in PRICING_FIXTURE["models"]:
            self.assertIn(mid, msg)

    def test_escalation_ladder_from_haiku_skips_empty_sonnet(self):
        ladder = ce.escalation_ladder(PRICING_FIXTURE, "fake-haiku")
        self.assertEqual(ladder, ["fake-opus-a", "fake-frontier"])

    def test_escalation_ladder_first_in_file_order_within_tier(self):
        ladder = ce.escalation_ladder(PRICING_FIXTURE, "fake-haiku")
        self.assertEqual(ladder[0], "fake-opus-a")
        self.assertNotIn("fake-opus-b", ladder)

    def test_escalation_ladder_from_frontier_is_empty(self):
        self.assertEqual(ce.escalation_ladder(PRICING_FIXTURE, "fake-frontier"), [])

    def test_unknown_or_none_model_id_defaults_to_sonnet_start(self):
        unknown = ce.escalation_ladder(PRICING_FIXTURE, "not-a-fixture-id")
        none_start = ce.escalation_ladder(PRICING_FIXTURE, None)
        self.assertEqual(unknown, none_start)
        self.assertEqual(none_start, ["fake-opus-a", "fake-frontier"])
        self.assertEqual(ce.DEFAULT_ESCALATION_START, "sonnet")


# ---- 3. build_dispatch anatomy --------------------------------------------------------------

class BuildDispatchTests(unittest.TestCase):
    def test_model_pinned_exact_argv(self):
        argv = ce.build_dispatch(STUB_BIN, "fake-haiku", "fake prompt text")
        self.assertIsInstance(argv, list)
        self.assertEqual(
            argv,
            [STUB_BIN, "-p", "--model", "fake-haiku", ce.PERMISSION_FLAG, "fake prompt text"],
        )

    def test_tier_word_pinned_resolves_through_skip_up_before_dispatch(self):
        model_id = ce.resolve_model(PRICING_FIXTURE, "sonnet")
        self.assertEqual(model_id, "fake-opus-a")  # skip-up: sonnet empty -> opus
        argv = ce.build_dispatch(STUB_BIN, model_id, "fake prompt text")
        self.assertEqual(argv[argv.index("--model") + 1], "fake-opus-a")

    def test_no_model_field_omits_model_pair(self):
        argv = ce.build_dispatch(STUB_BIN, None, "fake prompt text")
        self.assertNotIn("--model", argv)
        self.assertEqual(argv, [STUB_BIN, "-p", ce.PERMISSION_FLAG, "fake prompt text"])

    def test_permission_flag_always_present(self):
        argv = ce.build_dispatch(STUB_BIN, "fake-haiku", "prompt")
        self.assertIn(ce.PERMISSION_FLAG, argv)

    def test_extra_args_positioned_before_prompt(self):
        argv = ce.build_dispatch(
            STUB_BIN, "fake-haiku", "fake prompt text",
            extra_args=("--verbose", "--output-format=json"),
        )
        self.assertLess(argv.index("--verbose"), argv.index("--output-format=json"))
        self.assertLess(argv.index("--output-format=json"), len(argv) - 1)

    def test_prompt_is_always_the_last_element(self):
        argv = ce.build_dispatch(
            STUB_BIN, "fake-haiku", "prompt-marker", extra_args=("--extra1", "--extra2"),
        )
        self.assertEqual(argv[-1], "prompt-marker")

    def test_never_shell_true_dispatch_is_a_list(self):
        argv = ce.build_dispatch(STUB_BIN, "fake-haiku", "prompt text")
        self.assertIsInstance(argv, list)
        self.assertNotIsInstance(argv, str)


# ---- 4. preamble composition ------------------------------------------------------------------

class PreambleCompositionTests(unittest.TestCase):
    def test_strips_frontmatter_and_leaves_disk_file_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _write_agent_bundle(
                tmp, "fixturekit", "implementer", PREAMBLE_FIXTURE_BODY
            )

            result = ce.load_preamble("implementer", "fixturekit", repo_root=repo_root)

            self.assertFalse(result.lstrip().startswith("---"))
            self.assertNotIn("description: fixture kit agent", result)
            self.assertIn("Fixture kit-agent preamble body.", result)

            # the bundle file on disk is never rewritten.
            on_disk = (
                repo_root / ".claude" / "agents" / "fixturekit-implementer.md"
            ).read_text()
            self.assertIn("description: fixture kit agent", on_disk)

    def test_missing_role_file_raises_filenotfounderror_naming_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError) as ctx:
                ce.load_preamble("no-such-role", "fixturekit", repo_root=Path(tmp))
            self.assertIn("no-such-role", str(ctx.exception))
            self.assertIn("fixturekit", str(ctx.exception))

    def test_cmd_run_dry_run_composes_the_real_preamble_plus_separator_plus_brief(self):
        # Drives `main(["run", ..., "--dry-run"])` end to end and inspects the ACTUAL prompt
        # `cmd_run` built and printed in its dispatch argv -- never a string the test
        # re-derives by hand.
        with tempfile.TemporaryDirectory() as tmp:
            fixture_repo_root = _write_agent_bundle(
                tmp, "fixturekit", "implementer", PREAMBLE_FIXTURE_BODY
            )
            kit_dir = _write_kit(tmp, _single_task_text("true"), slug="fixturekit")
            known_brief = ce.parse_tasks(_single_task_text("true"))[0]["brief"]

            buf = io.StringIO()
            with mock.patch.object(ce, "REPO_ROOT", fixture_repo_root):
                with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                    with contextlib.redirect_stdout(buf):
                        ce.main(
                            ["run", "--kit", str(kit_dir), "--claude-bin", STUB_BIN, "--dry-run"]
                        )
            output = buf.getvalue()

            dispatch_start = output.index("dispatch: ") + len("dispatch: ")
            dispatch_end = output.rindex("\nverify: ")
            argv = shlex.split(output[dispatch_start:dispatch_end])

            self.assertEqual(argv[0], STUB_BIN)
            self.assertIn("--model", argv)
            self.assertEqual(argv[argv.index("--model") + 1], "fake-haiku")
            self.assertIn(ce.PERMISSION_FLAG, argv)

            composed = argv[-1]  # the REAL prompt cmd_run dispatched -- captured, not re-derived
            self.assertIn("Fixture kit-agent preamble body.", composed)
            self.assertTrue(composed.endswith("\n\n---\n\n" + known_brief))

            expected_preamble = ce.load_preamble(
                "implementer", "fixturekit", repo_root=fixture_repo_root
            )
            self.assertEqual(composed, expected_preamble + "\n\n---\n\n" + known_brief)

            on_disk = (
                fixture_repo_root / ".claude" / "agents" / "fixturekit-implementer.md"
            ).read_text()
            self.assertIn("description: fixture kit agent", on_disk)


# ---- 5. run_task with fake runners (pure, no subprocess anywhere) --------------------------

class RunTaskTests(unittest.TestCase):
    @staticmethod
    def _task(**overrides):
        base = {
            "id": "T1",
            "title": "fixture task",
            "status": "pending",
            "model": "fake-haiku",
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

        result = ce.run_task(task, PRICING_FIXTURE, runner, verify_runner, claude_bin=STUB_BIN)

        self.assertEqual(result["status"], "done")
        self.assertEqual(runner.call_count, 1)
        dispatched_argv = runner.call_args_list[0].args[0]
        self.assertIn("--model", dispatched_argv)
        self.assertEqual(dispatched_argv[dispatched_argv.index("--model") + 1], "fake-haiku")
        self.assertEqual(result["escalations"], [])
        self.assertEqual(result["model_used"], "fake-haiku")

    def test_verify_fails_once_then_passes_escalates_exactly_one_rung_skipping_empty_sonnet(self):
        task = self._task()
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(side_effect=[(1, "boom: fixture failure"), (0, "ok now")])

        result = ce.run_task(task, PRICING_FIXTURE, runner, verify_runner, claude_bin=STUB_BIN)

        self.assertEqual(result["status"], "done")
        self.assertEqual(result["escalations"], ["fake-opus-a"])
        self.assertEqual(result["model_used"], "fake-opus-a")
        self.assertEqual(runner.call_count, 2)

        second_argv = runner.call_args_list[1].args[0]
        self.assertEqual(second_argv[second_argv.index("--model") + 1], "fake-opus-a")
        prompt_payload = second_argv[-1]
        self.assertIn(task["brief"], prompt_payload)
        self.assertIn("ESCALATION EVIDENCE", prompt_payload)
        self.assertIn("boom: fixture failure", prompt_payload)

    def test_verify_never_passes_exhausts_full_ladder_and_blocks(self):
        task = self._task()
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(return_value=(1, "always fails"))

        result = ce.run_task(task, PRICING_FIXTURE, runner, verify_runner, claude_bin=STUB_BIN)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["escalations"], ["fake-opus-a", "fake-frontier"])
        self.assertEqual(runner.call_count, 3)  # initial dispatch + one per ladder rung

    def test_max_escalations_truncates_ladder(self):
        task = self._task()
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(return_value=(1, "always fails"))

        result = ce.run_task(
            task, PRICING_FIXTURE, runner, verify_runner, max_escalations=1, claude_bin=STUB_BIN
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["escalations"], ["fake-opus-a"])
        self.assertEqual(runner.call_count, 2)


# ---- 6. run id generation (F8: format pinned positively AND negatively) --------------------

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
        # against path separators / the repo root, none of which may appear.
        self.assertNotIn(socket.gethostname(), run_id)
        self.assertNotIn("/", run_id)
        self.assertNotIn("\\", run_id)
        self.assertNotIn(str(ce.REPO_ROOT), run_id)

    def test_ids_are_not_all_identical_across_calls(self):
        ids = {ce.generate_run_id() for _ in range(25)}
        self.assertGreater(len(ids), 1)


# ---- 7. outcome ledger line (T1 grammar: run=/parent=) --------------------------------------

class OutcomeResultClassificationTests(unittest.TestCase):
    def test_blocked_status_is_always_blocked(self):
        self.assertEqual(ce.outcome_result("blocked", [], None), "blocked")
        self.assertEqual(ce.outcome_result("blocked", ["fake-opus-a"], "T1"), "blocked")

    def test_done_no_escalation_no_parent_is_plain_pass(self):
        self.assertEqual(ce.outcome_result("done", [], None), "pass")

    def test_done_with_escalations_is_escalated_pass(self):
        self.assertEqual(ce.outcome_result("done", ["fake-opus-a"], None), "escalated-pass")

    def test_done_with_parent_but_no_ladder_escalation_is_escalated_pass(self):
        self.assertEqual(ce.outcome_result("done", [], "T4"), "escalated-pass")


class BuildOutcomeLineTests(unittest.TestCase):
    def test_minimal_line_no_run_no_parent(self):
        line = ce.build_outcome_line("T1", "fake-haiku", 1, "pass")
        self.assertEqual(
            line, "outcome: T1 model=fake-haiku attempts=1 result=pass review=none"
        )

    def test_run_id_appended_when_present(self):
        line = ce.build_outcome_line("T1", "fake-haiku", 1, "pass", run_id="2026-07-26-9f3a")
        self.assertTrue(line.endswith(" run=2026-07-26-9f3a"))

    def test_parent_appended_only_when_present(self):
        line = ce.build_outcome_line(
            "T5", "fake-frontier", 3, "escalated-pass",
            run_id="2026-07-26-9f3a", parent="T4",
        )
        self.assertTrue(line.endswith(" run=2026-07-26-9f3a parent=T4"))

    def test_no_parent_omits_the_field_entirely(self):
        line = ce.build_outcome_line("T1", "fake-haiku", 1, "pass", run_id="2026-07-26-9f3a")
        self.assertNotIn("parent=", line)


class AppendNoteTests(unittest.TestCase):
    def test_block_has_id_and_model_no_lesson_line_without_escalations(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes_path = Path(tmp) / "NOTES.md"
            task = {"id": "T1", "model": "fake-haiku"}
            result = {
                "id": "T1", "status": "done", "model_used": "fake-haiku",
                "escalations": [], "verify_rc": 0, "role": "implementer",
            }
            ce.append_note(notes_path, result, task, run_id="2026-07-26-abcd")
            text = notes_path.read_text()
            self.assertIn("T1", text)
            self.assertIn("fake-haiku", text)
            self.assertNotIn("lesson-candidate (routing):", text)
            self.assertIn(
                "outcome: T1 model=fake-haiku attempts=1 result=pass review=none "
                "run=2026-07-26-abcd",
                text,
            )
            self.assertNotIn("parent=", text)

    def test_escalations_add_lesson_candidate_line_and_escalated_pass_outcome(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes_path = Path(tmp) / "NOTES.md"
            task = {"id": "T3", "model": "fake-haiku"}
            result = {
                "id": "T3", "status": "done", "model_used": "fake-opus-a",
                "escalations": ["fake-opus-a"], "verify_rc": 0, "role": "implementer",
            }
            ce.append_note(notes_path, result, task, run_id="2026-07-26-abcd")
            text = notes_path.read_text()
            self.assertIn("T3", text)
            self.assertIn("fake-opus-a", text)
            self.assertTrue(
                any(
                    line.startswith("lesson-candidate (routing):")
                    for line in text.splitlines()
                )
            )
            self.assertIn(
                "outcome: T3 model=fake-opus-a attempts=2 result=escalated-pass review=none "
                "run=2026-07-26-abcd",
                text,
            )

    def test_parent_flows_through_to_the_outcome_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes_path = Path(tmp) / "NOTES.md"
            task = {"id": "T5", "model": "fake-haiku"}
            result = {
                "id": "T5", "status": "done", "model_used": "fake-haiku",
                "escalations": [], "verify_rc": 0, "role": "implementer",
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
                "escalations": [], "verify_rc": 0, "role": "implementer",
            }
            ce.append_note(notes_path, result, task, run_id="2026-07-26-abcd")
            text = notes_path.read_text()
            self.assertIn("model used: claude default", text)
            self.assertIn("outcome: T2 model=unpinned", text)  # single token -- no space

    def test_blocked_status_writes_blocked_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes_path = Path(tmp) / "NOTES.md"
            task = {"id": "B1", "model": "fake-haiku"}
            result = {
                "id": "B1", "status": "blocked", "model_used": "fake-frontier",
                "escalations": ["fake-opus-a", "fake-frontier"], "verify_rc": 1,
                "role": "implementer",
            }
            ce.append_note(notes_path, result, task, run_id="2026-07-26-abcd")
            text = notes_path.read_text()
            self.assertIn("result=blocked", text)


# ---- 8. end-to-end main(["run", ...]) with a STUB executable -------------------------------

class EndToEndRunHappyPathTests(unittest.TestCase):
    def test_main_run_with_stub_executable_completes_done_writes_marker_and_outcome_line(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            fixture_repo_root = _write_agent_bundle(
                tmp, "fixturekit", "implementer", PREAMBLE_FIXTURE_BODY
            )
            marker = tmp / "work-done.marker"
            kit_dir = _write_kit(
                tmp, _single_task_text(f'test -f "{marker}"'), slug="fixturekit"
            )
            before_text = (kit_dir / "TASKS.md").read_text()

            log_path = tmp / "stub.log"
            stub_path = _write_stub(tmp, log_path, marker_path=marker)

            buf = io.StringIO()
            with mock.patch.object(ce, "REPO_ROOT", fixture_repo_root):
                with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                    with contextlib.redirect_stdout(buf):
                        ce.main(["run", "--kit", str(kit_dir), "--claude-bin", str(stub_path)])

            after_text = (kit_dir / "TASKS.md").read_text()
            before_lines = before_text.splitlines()
            after_lines = after_text.splitlines()
            self.assertEqual(len(before_lines), len(after_lines))
            diffs = [i for i in range(len(before_lines)) if before_lines[i] != after_lines[i]]
            self.assertEqual(len(diffs), 1)
            i = diffs[0]
            self.assertEqual(after_lines[i].strip(), "- status: done")

            tasks = ce.parse_tasks(after_text)
            self.assertEqual(tasks[0]["status"], "done")

            notes_text = (kit_dir / "NOTES.md").read_text()
            self.assertIn("fake-haiku", notes_text)
            self.assertRegex(notes_text, r"outcome: E1 model=fake-haiku attempts=1 result=pass "
                                          r"review=none run=\d{4}-\d{2}-\d{2}-[0-9a-f]{4}")

            # Not tautological (marker doesn't exist pre-task) -> record succeeds -> a real
            # verify-pass marker exists.
            self.assertTrue((kit_dir / "verify-pass" / "E1").exists())

            log_text = log_path.read_text()
            self.assertEqual(_dispatched_models(log_text), ["fake-haiku"])
            self.assertIn(ce.PERMISSION_FLAG, log_text)


class EndToEndTautologicalVerifyTests(unittest.TestCase):
    def test_tautological_verify_labels_the_ledger_line_and_exits_nonzero(self):
        # `true` passes on the PRE-task tree too (D10) -- precheck flags it tautological, and
        # record refuses to write the pass marker. The refusal is NOT discarded: it rides into
        # NOTES.md as an in-grammar `defect: <task-id> kind=tautological-verify` line beside the
        # `outcome:` line (a `result=pass` written off a verify that could never fail would
        # otherwise be indistinguishable from a genuine red -> green first-try pass, and NOTES.md
        # is the routing evidence base), goes to STDERR, and makes `run` exit nonzero.
        # What it deliberately does NOT do is change the done/blocked decision (PLAN D11: an
        # analysis signal never changes routing state) -- the task still ends up `done`.
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            fixture_repo_root = _write_agent_bundle(
                tmp, "fixturekit", "implementer", PREAMBLE_FIXTURE_BODY
            )
            kit_dir = _write_kit(tmp, _single_task_text("true"), slug="fixturekit")
            log_path = tmp / "stub.log"
            stub_path = _write_stub(tmp, log_path)

            buf = io.StringIO()
            err = io.StringIO()
            with mock.patch.object(ce, "REPO_ROOT", fixture_repo_root):
                with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                    with contextlib.redirect_stdout(buf):
                        with contextlib.redirect_stderr(err):
                            with self.assertRaises(SystemExit) as ctx:
                                ce.main(
                                    ["run", "--kit", str(kit_dir),
                                     "--claude-bin", str(stub_path)]
                                )
            self.assertNotEqual(ctx.exception.code, 0)

            # the `done` write is untouched -- status follows the verify's exit code
            tasks = ce.parse_tasks((kit_dir / "TASKS.md").read_text())
            self.assertEqual(tasks[0]["status"], "done")

            notes_text = (kit_dir / "NOTES.md").read_text()
            self.assertIn("result=pass", notes_text)
            # ... but the ledger no longer LIES about it: the honesty label ships beside it
            self.assertIn("defect: E1 kind=tautological-verify", notes_text)

            # record refused -- no pass marker persisted; `run_record`'s refusal message
            # ("refused: task E1's verify command ...") went to stderr, not stdout. (precheck's
            # own defect line still prints on stdout, hence the specific prefix here.)
            self.assertFalse((kit_dir / "verify-pass" / "E1").exists())
            self.assertIn("refused: task E1", err.getvalue())
            self.assertNotIn("refused: task E1", buf.getvalue())

    def test_the_defect_line_parses_under_the_repos_own_defect_grammar(self):
        """The written line lands in a machine-read ledger family, so it is asserted against the
        real consumer -- `bin/routing_scorecard.py`'s `parse_defects` -- rather than a
        hand-copied regex. Pure-function parse over an in-memory string: no disk, no home
        directory, no subprocess, no CLI."""
        rs = _load("routing_scorecard")
        line = ce.build_defect_line("E1", "tautological-verify")
        self.assertEqual(line, "defect: E1 kind=tautological-verify")
        events, notes = rs.parse_defects(line + "\n")
        self.assertEqual(events, [{"task": "E1", "kind": "tautological-verify"}])
        self.assertEqual(notes, [])

    def test_a_genuine_red_to_green_pass_writes_no_defect_line_and_exits_zero(self):
        """The unchanged path, asserted explicitly: a verify that genuinely fails pre-task and
        passes post-task records its marker, writes NO defect line, and exits 0."""
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            fixture_repo_root = _write_agent_bundle(
                tmp, "fixturekit", "implementer", PREAMBLE_FIXTURE_BODY
            )
            marker = tmp / "work-done.marker"
            kit_dir = _write_kit(
                tmp, _single_task_text(f'test -f "{marker}"'), slug="fixturekit"
            )
            stub_path = _write_stub(tmp, tmp / "stub.log", marker_path=marker)

            buf = io.StringIO()
            with mock.patch.object(ce, "REPO_ROOT", fixture_repo_root):
                with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                    with contextlib.redirect_stdout(buf):
                        ce.main(["run", "--kit", str(kit_dir), "--claude-bin", str(stub_path)])

            notes_text = (kit_dir / "NOTES.md").read_text()
            self.assertIn("result=pass", notes_text)
            self.assertNotIn("defect:", notes_text)
            self.assertTrue((kit_dir / "verify-pass" / "E1").exists())


class EndToEndEscalationTests(unittest.TestCase):
    def test_escalation_exhausts_ladder_blocks_and_writes_lesson_note(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            fixture_repo_root = _write_agent_bundle(
                tmp, "fixturekit", "implementer", PREAMBLE_FIXTURE_BODY
            )
            kit_dir = _write_kit(tmp, ESCALATION_TASKS_TEXT, slug="fixturekit")

            log_path = tmp / "stub.log"
            stub_path = _write_stub(tmp, log_path)

            buf = io.StringIO()
            with mock.patch.object(ce, "REPO_ROOT", fixture_repo_root):
                with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                    with contextlib.redirect_stdout(buf):
                        with self.assertRaises(SystemExit) as ctx:
                            ce.main(
                                ["run", "--kit", str(kit_dir), "--claude-bin", str(stub_path)]
                            )
            self.assertEqual(ctx.exception.code, 1)

            final_text = (kit_dir / "TASKS.md").read_text()
            tasks = ce.parse_tasks(final_text)
            self.assertEqual(tasks[0]["status"], "blocked")

            notes_text = (kit_dir / "NOTES.md").read_text()
            self.assertIn("lesson-candidate (routing):", notes_text)
            self.assertIn("fake-frontier", notes_text)
            self.assertIn("result=blocked", notes_text)

            log_text = log_path.read_text()
            self.assertEqual(
                _dispatched_models(log_text),
                ["fake-haiku", "fake-opus-a", "fake-frontier"],
            )


class ParentFlagEndToEndTests(unittest.TestCase):
    def test_parent_flag_lands_on_the_outcome_line_as_escalated_pass(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            fixture_repo_root = _write_agent_bundle(
                tmp, "fixturekit", "implementer", PREAMBLE_FIXTURE_BODY
            )
            marker = tmp / "consult-done.marker"
            kit_dir = _write_kit(
                tmp, _single_task_text(f'test -f "{marker}"', task_id="Y1"), slug="fixturekit"
            )
            log_path = tmp / "stub.log"
            stub_path = _write_stub(tmp, log_path, marker_path=marker)

            buf = io.StringIO()
            with mock.patch.object(ce, "REPO_ROOT", fixture_repo_root):
                with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                    with contextlib.redirect_stdout(buf):
                        ce.main(
                            [
                                "run", "--kit", str(kit_dir), "--claude-bin", str(stub_path),
                                "--parent", "X1",
                            ]
                        )

            notes_text = (kit_dir / "NOTES.md").read_text()
            self.assertIn("result=escalated-pass", notes_text)
            self.assertIn("parent=X1", notes_text)

    def test_parent_equal_to_the_task_id_is_rejected_before_anything_is_written(self):
        """A task is never its own parent. `routing_scorecard` DROPS a self-referencing `parent=`
        with a note while still counting the `escalated-pass` it caused, so writing one would put
        a single line into a headline figure and into the "ignored" list at once -- the invariant
        the Phase 1 review adopted. Rejected at the writer, with nothing written: no status flip,
        no NOTES.md, no marker, no dispatch."""
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            fixture_repo_root = _write_agent_bundle(
                tmp, "fixturekit", "implementer", PREAMBLE_FIXTURE_BODY
            )
            kit_dir = _write_kit(
                tmp, _single_task_text("true", task_id="W1"), slug="fixturekit"
            )
            before = (kit_dir / "TASKS.md").read_bytes()

            err = io.StringIO()
            with mock.patch.object(ce, "REPO_ROOT", fixture_repo_root):
                with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                    with mock.patch.object(ce, "subprocess") as mock_subprocess:
                        mock_subprocess.run.side_effect = AssertionError(
                            "dispatched despite a rejected --parent"
                        )
                        with contextlib.redirect_stderr(err):
                            with self.assertRaises(SystemExit) as ctx:
                                ce.main(
                                    ["run", "--kit", str(kit_dir), "--claude-bin", STUB_BIN,
                                     "--parent", "W1"]
                                )
                        mock_subprocess.run.assert_not_called()

            self.assertEqual(ctx.exception.code, 2)
            self.assertIn("cannot be its own", err.getvalue())
            self.assertEqual(before, (kit_dir / "TASKS.md").read_bytes())
            self.assertFalse((kit_dir / "NOTES.md").exists())
            self.assertFalse((kit_dir / "verify-pass").exists())


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

    def test_append_note_blocked_with_parent_writes_no_parent_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes_path = Path(tmp) / "NOTES.md"
            task = {"id": "B7", "model": "fake-haiku"}
            result = {
                "id": "B7", "status": "blocked", "model_used": "fake-frontier",
                "escalations": ["fake-opus-a", "fake-frontier"], "verify_rc": 1,
                "role": "implementer",
            }
            ce.append_note(notes_path, result, task, run_id="2026-07-26-abcd", parent="T4")
            text = notes_path.read_text()
            self.assertIn("result=blocked", text)
            self.assertNotIn("parent=", text)
            self.assertNotIn("T4", text)

    def test_append_note_escalated_with_parent_still_writes_parent_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes_path = Path(tmp) / "NOTES.md"
            task = {"id": "B7", "model": "fake-haiku"}
            result = {
                "id": "B7", "status": "done", "model_used": "fake-opus-a",
                "escalations": ["fake-opus-a"], "verify_rc": 0, "role": "implementer",
            }
            ce.append_note(notes_path, result, task, run_id="2026-07-26-abcd", parent="T4")
            text = notes_path.read_text()
            self.assertIn("result=escalated-pass", text)
            self.assertIn("parent=T4", text)

    def test_blocked_with_parent_still_carries_its_defect_line_when_flagged(self):
        """The `parent=` omission is scoped to that one field: the same write path's
        `defect_kind` label still lands beside the `outcome:` line (F-A's honesty fix must not
        be collateral damage of P34-F2's)."""
        with tempfile.TemporaryDirectory() as tmp:
            notes_path = Path(tmp) / "NOTES.md"
            task = {"id": "B7", "model": "fake-haiku"}
            result = {
                "id": "B7", "status": "blocked", "model_used": "fake-frontier",
                "escalations": ["fake-frontier"], "verify_rc": 1, "role": "implementer",
            }
            ce.append_note(
                notes_path, result, task, run_id="2026-07-26-abcd", parent="T4",
                defect_kind="tautological-verify",
            )
            text = notes_path.read_text()
            self.assertNotIn("parent=", text)
            self.assertIn("defect: B7 kind=tautological-verify", text)

    def test_build_outcome_line_itself_is_unchanged(self):
        """The gate lives in `append_note`, not in the line builder: `build_outcome_line` is a
        pure formatter and still writes whatever `parent` it is handed (T2's callers depend on
        that, and nothing else in the file may quietly re-interpret its arguments)."""
        line = ce.build_outcome_line("B7", "fake-frontier", 3, "blocked", parent="T4")
        self.assertTrue(line.endswith(" parent=T4"))

    def test_end_to_end_blocked_run_with_parent_flag_writes_no_parent(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            fixture_repo_root = _write_agent_bundle(
                tmp, "fixturekit", "implementer", PREAMBLE_FIXTURE_BODY
            )
            # verify is `false` -> fails pre-task (not tautological) and after every rung ->
            # ladder exhausted -> blocked.
            kit_dir = _write_kit(tmp, ESCALATION_TASKS_TEXT, slug="fixturekit")

            log_path = tmp / "stub.log"
            stub_path = _write_stub(tmp, log_path)

            buf = io.StringIO()
            with mock.patch.object(ce, "REPO_ROOT", fixture_repo_root):
                with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                    with contextlib.redirect_stdout(buf):
                        with self.assertRaises(SystemExit) as ctx:
                            ce.main(
                                ["run", "--kit", str(kit_dir), "--claude-bin", str(stub_path),
                                 "--parent", "X1"]
                            )
            self.assertEqual(ctx.exception.code, 1)

            notes_text = (kit_dir / "NOTES.md").read_text()
            self.assertIn("result=blocked", notes_text)
            self.assertNotIn("parent=", notes_text)
            self.assertNotIn("X1", notes_text)
            # stdout stays machine-clean: the omission is silent, never a warning line.
            self.assertNotIn("parent", buf.getvalue())


# ---- 9. dry-run spawns/writes nothing --------------------------------------------------------

class DryRunSpawnsNothingTests(unittest.TestCase):
    def test_dry_run_never_touches_subprocess_and_leaves_kit_untouched(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            fixture_repo_root = _write_agent_bundle(
                tmp, "fixturekit", "implementer", PREAMBLE_FIXTURE_BODY
            )
            kit_dir = _write_kit(tmp, _single_task_text("true"), slug="fixturekit")
            before = (kit_dir / "TASKS.md").read_bytes()

            with mock.patch.object(ce, "REPO_ROOT", fixture_repo_root):
                with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                    with mock.patch.object(ce, "subprocess") as mock_subprocess:
                        mock_subprocess.run.side_effect = AssertionError(
                            "subprocess in dry-run"
                        )
                        buf = io.StringIO()
                        with contextlib.redirect_stdout(buf):
                            ce.main(
                                [
                                    "run", "--kit", str(kit_dir), "--claude-bin", STUB_BIN,
                                    "--dry-run",
                                ]
                            )
                        mock_subprocess.run.assert_not_called()

            after = (kit_dir / "TASKS.md").read_bytes()
            self.assertEqual(before, after)
            self.assertFalse((kit_dir / "NOTES.md").exists())
            self.assertFalse((kit_dir / "verify-pass").exists())
            self.assertIn("dispatch:", buf.getvalue())

    def test_dry_run_previews_every_pending_task_not_just_the_first_eligible_one(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            fixture_repo_root = _write_agent_bundle(
                tmp, "fixturekit", "implementer", PREAMBLE_FIXTURE_BODY
            )
            kit_dir = _write_kit(tmp, DRY_RUN_ALL_PENDING_TASKS_TEXT, slug="fixturekit")

            buf = io.StringIO()
            with mock.patch.object(ce, "REPO_ROOT", fixture_repo_root):
                with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                    with mock.patch.object(ce, "subprocess") as mock_subprocess:
                        mock_subprocess.run.side_effect = AssertionError("subprocess touched")
                        with contextlib.redirect_stdout(buf):
                            ce.main(
                                ["run", "--kit", str(kit_dir), "--claude-bin", STUB_BIN,
                                 "--dry-run"]
                            )
            output = buf.getvalue()
            self.assertIn("task: T1", output)
            self.assertIn("task: T2", output)
            self.assertNotIn("task: T3", output)  # already done -- excluded from the preview
            self.assertFalse((kit_dir / "NOTES.md").exists())

    def test_dry_run_with_explicit_task_previews_only_that_task(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            fixture_repo_root = _write_agent_bundle(
                tmp, "fixturekit", "implementer", PREAMBLE_FIXTURE_BODY
            )
            kit_dir = _write_kit(tmp, DRY_RUN_ALL_PENDING_TASKS_TEXT, slug="fixturekit")

            buf = io.StringIO()
            with mock.patch.object(ce, "REPO_ROOT", fixture_repo_root):
                with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                    with contextlib.redirect_stdout(buf):
                        ce.main(
                            ["run", "--kit", str(kit_dir), "--claude-bin", STUB_BIN,
                             "--task", "T2", "--dry-run"]
                        )
            output = buf.getvalue()
            self.assertIn("task: T2", output)
            self.assertNotIn("task: T1", output)


# ---- 10. status --kit smoke -------------------------------------------------------------------

class StatusSmokeTests(unittest.TestCase):
    def test_status_kit_lists_each_task_id_and_a_totals_line(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, TASKS_TEXT_FIXTURE, slug="fixturekit")

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ce.main(["status", "--kit", str(kit_dir)])
            output = buf.getvalue()

            for task_id in ("T1", "T2", "T3"):
                self.assertIn(task_id, output)
            self.assertRegex(output, r"\d+ pending / \d+ in-progress / \d+ done / \d+ blocked")


# ---- 11. review subcommand dry-run --------------------------------------------------------

class ReviewDryRunTests(unittest.TestCase):
    def test_review_dry_run_prints_dispatch_and_spawns_nothing(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            fixture_repo_root = _write_agent_bundle(
                tmp, "fixturekit", "reviewer", PREAMBLE_FIXTURE_BODY
            )
            kit_dir = _write_kit(tmp, TASKS_TEXT_FIXTURE, slug="fixturekit")

            buf = io.StringIO()
            with mock.patch.object(ce, "REPO_ROOT", fixture_repo_root):
                with mock.patch.object(ce, "subprocess") as mock_subprocess:
                    mock_subprocess.run.side_effect = AssertionError("subprocess in dry-run")
                    with contextlib.redirect_stdout(buf):
                        ce.main(
                            ["review", "--kit", str(kit_dir), "--phase", "1",
                             "--claude-bin", STUB_BIN, "--dry-run"]
                        )
                    mock_subprocess.run.assert_not_called()
            output = buf.getvalue()
            self.assertIn("phase: 1", output)
            self.assertIn("dispatch:", output)
            self.assertIn(STUB_BIN, output)


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

    def test_unrecognized_key_ignored_leaving_none_if_nothing_recognized(self):
        self.assertIsNone(ce.parse_plan_budget("budget: max-frobnicate=9\n"))


class CountPlanBudgetUsageTests(unittest.TestCase):
    def test_empty_notes_all_zero(self):
        self.assertEqual(
            ce.count_plan_budget_usage(""),
            {"max-dispatches": 0, "max-escalations": 0, "max-consults": 0},
        )

    def test_sums_attempts_and_escalations_across_lines(self):
        notes = "\n".join([
            "- outcome: A1 model=fake-haiku attempts=1 result=pass review=none",
            "- outcome: A2 model=fake-opus-a attempts=3 result=escalated-pass review=none",
        ])
        used = ce.count_plan_budget_usage(notes)
        self.assertEqual(used["max-dispatches"], 4)
        self.assertEqual(used["max-escalations"], 2)
        self.assertEqual(used["max-consults"], 0)

    def test_parent_bearing_line_counts_one_consult(self):
        notes = ("- outcome: A1 model=fake-frontier attempts=1 result=escalated-pass "
                  "review=none run=2026-07-26-aaaa parent=X1")
        used = ce.count_plan_budget_usage(notes)
        self.assertEqual(used["max-consults"], 1)

    def test_missing_attempts_defaults_to_one(self):
        used = ce.count_plan_budget_usage("- outcome: A1 model=fake-haiku result=pass review=none")
        self.assertEqual(used["max-dispatches"], 1)
        self.assertEqual(used["max-escalations"], 0)


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
            fixture_repo_root = _write_agent_bundle(
                tmp, "fixturekit", "implementer", PREAMBLE_FIXTURE_BODY
            )
            kit_dir = _write_kit(tmp, _single_task_text("true", task_id="G1"), slug="fixturekit")
            (kit_dir / "PLAN.md").write_text("# PLAN\n\nbudget: max-dispatches=1\n")
            (kit_dir / "NOTES.md").write_text(
                "## 2026-07-25T00:00:00Z — G0\n"
                "- outcome: G0 model=fake-haiku attempts=1 result=pass review=none "
                "run=2026-07-25-1234\n"
            )
            before_tasks_text = (kit_dir / "TASKS.md").read_text()

            with mock.patch.object(ce, "REPO_ROOT", fixture_repo_root):
                with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
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
                                        ["run", "--kit", str(kit_dir),
                                         "--claude-bin", str(tmp / "unused-stub")]
                                    )
                        mock_subprocess.run.assert_not_called()

            self.assertEqual(ctx.exception.code, 1)
            self.assertIn("budget-stop", err.getvalue())
            self.assertIn("max-dispatches", err.getvalue())

            # TASKS.md is byte-identical -- the task was never marked in-progress or done.
            after_tasks_text = (kit_dir / "TASKS.md").read_text()
            self.assertEqual(before_tasks_text, after_tasks_text)
            tasks = ce.parse_tasks(after_tasks_text)
            self.assertEqual(tasks[0]["status"], "pending")

            notes_text = (kit_dir / "NOTES.md").read_text()
            self.assertRegex(
                notes_text,
                r"outcome: G1 model=fake-haiku attempts=0 result=budget-stop review=none "
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
            fixture_repo_root = _write_agent_bundle(
                tmp, "fixturekit", "implementer", PREAMBLE_FIXTURE_BODY
            )
            kit_dir = _write_kit(tmp, _single_task_text("true", task_id="G3"), slug="fixturekit")
            (kit_dir / "PLAN.md").write_text("# PLAN\n\nbudget: max-dispatches=1\n")
            recorded = (
                "## 2026-07-25T00:00:00Z — G3\n"
                "- outcome: G3 model=fake-haiku attempts=2 result=blocked review=revised "
                "run=2026-07-25-1234 failure=verification\n"
            )
            (kit_dir / "NOTES.md").write_text(recorded)
            before_tasks_text = (kit_dir / "TASKS.md").read_text()

            with mock.patch.object(ce, "REPO_ROOT", fixture_repo_root):
                with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
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
                                        ["run", "--kit", str(kit_dir), "--task", "G3",
                                         "--claude-bin", str(tmp / "unused-stub")]
                                    )
                        mock_subprocess.run.assert_not_called()

            self.assertEqual(ctx.exception.code, 1)
            # The stop is still reported -- never hidden -- and says why nothing was recorded.
            self.assertIn("budget-stop", err.getvalue())
            self.assertIn("NOT recorded in the ledger", err.getvalue())
            self.assertIn("result=blocked", err.getvalue())

            # NOTES.md is byte-identical: no budget-stop line was appended at all.
            self.assertEqual((kit_dir / "NOTES.md").read_text(), recorded)
            self.assertEqual((kit_dir / "TASKS.md").read_text(), before_tasks_text)

    def test_budget_stop_after_an_earlier_budget_stop_is_still_recorded(self):
        """The guard rejects only a real VERDICT. A prior `budget-stop` for the same id is not
        one, so a second stop records normally -- the guard must not silence the dial."""
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            fixture_repo_root = _write_agent_bundle(
                tmp, "fixturekit", "implementer", PREAMBLE_FIXTURE_BODY
            )
            kit_dir = _write_kit(tmp, _single_task_text("true", task_id="G4"), slug="fixturekit")
            (kit_dir / "PLAN.md").write_text("# PLAN\n\nbudget: max-dispatches=1\n")
            (kit_dir / "NOTES.md").write_text(
                "## 2026-07-25T00:00:00Z — G0\n"
                "- outcome: G0 model=fake-haiku attempts=1 result=pass review=none "
                "run=2026-07-25-1234\n"
                "## 2026-07-25T01:00:00Z — G4\n"
                "- outcome: G4 model=fake-haiku attempts=0 result=budget-stop review=none "
                "run=2026-07-25-5678\n"
            )

            with mock.patch.object(ce, "REPO_ROOT", fixture_repo_root):
                with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                    with mock.patch.object(ce, "subprocess") as mock_subprocess:
                        mock_subprocess.run.side_effect = AssertionError("dispatched")
                        err = io.StringIO()
                        buf = io.StringIO()
                        with contextlib.redirect_stdout(buf):
                            with contextlib.redirect_stderr(err):
                                with self.assertRaises(SystemExit):
                                    ce.main(
                                        ["run", "--kit", str(kit_dir), "--task", "G4",
                                         "--claude-bin", str(tmp / "unused-stub")]
                                    )

            self.assertNotIn("NOT recorded in the ledger", err.getvalue())
            self.assertEqual(
                (kit_dir / "NOTES.md").read_text().count("result=budget-stop"), 2)

    def test_recorded_outcome_result_reads_the_last_line_for_that_id_only(self):
        notes = (
            "- outcome: A1 model=fake-haiku attempts=1 result=pass review=none\n"
            "outcome: A2 model=fake-haiku attempts=1 result=blocked review=none\n"
            "- outcome: A1 model=fake-haiku attempts=2 result=retry-pass review=clean\n"
        )
        self.assertEqual(ce.recorded_outcome_result(notes, "A1"), "retry-pass")
        self.assertEqual(ce.recorded_outcome_result(notes, "A2"), "blocked")
        self.assertIsNone(ce.recorded_outcome_result(notes, "A3"))
        self.assertIsNone(ce.recorded_outcome_result("", "A1"))

    def test_absent_budget_block_is_unaffected_today_behavior(self):
        """No PLAN.md at all (or a PLAN.md with no `budget:` line) -> the run dispatches
        normally, exactly as it did before T9 -- byte-identical to the existing happy-path
        end-to-end test's assertions."""
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            fixture_repo_root = _write_agent_bundle(
                tmp, "fixturekit", "implementer", PREAMBLE_FIXTURE_BODY
            )
            marker = tmp / "g2-done.marker"
            kit_dir = _write_kit(
                tmp, _single_task_text(f'test -f "{marker}"', task_id="G2"), slug="fixturekit"
            )
            log_path = tmp / "stub.log"
            stub_path = _write_stub(tmp, log_path, marker_path=marker)

            buf = io.StringIO()
            with mock.patch.object(ce, "REPO_ROOT", fixture_repo_root):
                with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                    with contextlib.redirect_stdout(buf):
                        ce.main(["run", "--kit", str(kit_dir), "--claude-bin", str(stub_path)])

            tasks = ce.parse_tasks((kit_dir / "TASKS.md").read_text())
            self.assertEqual(tasks[0]["status"], "done")
            notes_text = (kit_dir / "NOTES.md").read_text()
            self.assertIn("result=pass", notes_text)
            self.assertNotIn("budget-stop", notes_text)
            self.assertEqual(log_path.read_text().count("===CALL==="), 1)


if __name__ == "__main__":
    unittest.main()
