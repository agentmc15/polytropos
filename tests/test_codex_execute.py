"""Stdlib unittest regression suite for bin/codex_execute.py.

bin/ is not a package; codex_execute.py is loaded via importlib by absolute path computed
from this file's own location, per the repo's `BIN_DIR = Path(__file__).resolve().parent.parent
/ "bin"` convention (same pattern as tests/test_copilot_execute.py).

============================================================================================
 SAFETY CONTRACT -- read this before adding a test here
============================================================================================
No test in this file EVER invokes the real `codex` binary or touches the real `~/.codex`.
Every dispatch goes through one of two seams: an injected fake `runner`/`verify_runner`
callable (pure-function tests of `run_task`, `build_dispatch`, `escalation_ladder`), or a tiny
temp STUB shell executable written to a `tempfile.TemporaryDirectory()` and passed explicitly
via `--codex-bin` (the end-to-end `main(["run", ...])` tests) -- never a binary named `codex`
resolved off PATH. `Path.home()` is never called anywhere in this file. The dry-run test and
the invalid-effort test additionally prove the negative by patching `subprocess` in the loaded
module to raise if touched at all, then asserting the command still completes (or exits before
dispatch) and mutates nothing.

Fixture ids (`fake-cheap`, `fake-strong-a`, `fake-strong-b`, `fake-frontier`) and every price in
`PRICING_FIXTURE` are synthetic and never appear in `data/pricing.codex.json`. The fixture
deliberately leaves the `mid` tier EMPTY (not `strong`) -- mirroring tests/test_codex_pricing.py's
FIXTURE_EMPTY_MID -- so the D4 skip-up rule is proven general, not just "strong happens to be
empty on today's real roster". End-to-end tests patch `codex_execute.load_pricing` to return
this synthetic dict so the real `data/pricing.codex.json` is never consulted for tier/escalation
behavior; the real bundle under `codex/prompts/` IS read (read-only) by the end-to-end tests via
the driver's own `REPO_ROOT`, since `cmd_run` has no override for it -- this is harmless, it is
never written.
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


ce = _load("codex_execute")


# ---- fixtures ---------------------------------------------------------------------------------

# A synthetic STUB executable "name" used wherever a codex_bin value is required but no process
# is actually spawned (build_dispatch is a pure argv builder; run_task's runner/verify_runner
# are fakes). Deliberately not the real CLI's name.
STUB_BIN = "stub-cli"

# Fake pricing dict, tiers expressed in file order: cheap, strong (two entries), frontier.
# The `mid` tier is deliberately EMPTY -- and deliberately NOT `strong` -- so a passing skip-up
# assertion proves the rule is read from data, not hardcoded to today's real-roster shape.
# Round fake numbers only -- never the real roster's ids or rates. `knobs.reasoning_efforts`
# is a different word list than the real pricing file's, so a passing validation test proves
# the effort vocabulary is read from the pricing dict at run time.
PRICING_FIXTURE = {
    "knobs": {"reasoning_efforts": ["low", "medium", "high"]},
    "models": {
        "fake-cheap": {"tier": "cheap", "input_per_mtok": 1.0, "output_per_mtok": 2.0},
        "fake-strong-a": {"tier": "strong", "input_per_mtok": 8.0, "output_per_mtok": 16.0},
        "fake-strong-b": {"tier": "strong", "input_per_mtok": 9.0, "output_per_mtok": 18.0},
        "fake-frontier": {"tier": "frontier", "input_per_mtok": 20.0, "output_per_mtok": 40.0},
    },
}

# Two phases, three tasks: T1 has a pinned model id and depends: (none); T2 has no model line
# at all and depends: (none); T3 pins a TIER WORD ("mid", empty -- resolves via skip-up) and
# depends: T1.
TASKS_TEXT_FIXTURE = """# TASKS -- fixture kit

## Phase 1 -- Made-up phase one

### T1 — First fixture task
- status: pending
- model: fake-cheap
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
- model: mid
- depends: T1
- independent: no

**Brief.** Do the third fixture thing; depends on the first, pinned via an empty tier word.

**Acceptance.** Fake acceptance text for T3.

**Verify.**
```bash
true
```
"""

# A single-task kit whose verify command always passes, for the end-to-end happy-path and
# dry-run runs.
SINGLE_TASK_TASKS_TEXT = """## Phase 1 — Only phase

### E1 — Only fixture task
- status: pending
- model: fake-cheap
- depends: (none)
- independent: yes

**Brief.** Fixture brief payload for the end-to-end stub-executable run.

**Acceptance.** Fake acceptance text for E1.

**Verify.**
```bash
true
```
"""

# A single-task kit whose verify command always FAILS, for the end-to-end escalation-exhausted
# run.
ESCALATION_TASKS_TEXT = """## Phase 1 — Only phase

### B1 — Blocked fixture task
- status: pending
- model: fake-cheap
- depends: (none)
- independent: yes

**Brief.** Fixture brief payload whose verify always fails, to exhaust the escalation ladder.

**Acceptance.** Fake acceptance text for B1.

**Verify.**
```bash
false
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

# A tiny bash STUB (never named after the real CLI): logs its argv MINUS the last element (the
# prompt -- which can be many KB of multi-line preamble text that itself mentions `--model <id>`
# as documentation, which would otherwise pollute a naive substring/regex scan of the log) behind
# a call-boundary marker, then exits 0. `%LOG%` is replaced via str.replace (not str.format,
# since the script's own `${...}` array syntax would collide with format-string braces).
STUB_SHELL_TEMPLATE = """#!/bin/bash
echo "===CALL===" >> "%LOG%"
args=("$@")
n=${#args[@]}
unset "args[$((n-1))]"
printf '%s\\n' "${args[@]}" >> "%LOG%"
exit 0
"""


def _write_stub(tmp_path, log_path):
    stub_path = Path(tmp_path) / STUB_BIN
    stub_path.write_text(STUB_SHELL_TEMPLATE.replace("%LOG%", str(log_path)))
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

# A fixture role-preamble bundle body, written to a TEMP repo_root only -- never the real
# codex/prompts/ bundle. Carries frontmatter to strip and the placeholder to resolve in memory.
PREAMBLE_FIXTURE_BODY = """---
description: fixture role preamble, never the real bundle
---

Fixture preamble body. Repo root resolves to {{POLYTROPOS_ROOT}} in memory only.
"""


def _write_kit(tmp_path, text):
    kit_dir = Path(tmp_path) / "kit"
    kit_dir.mkdir()
    (kit_dir / "TASKS.md").write_text(text)
    return kit_dir


def _write_preamble_bundle(tmp_path, role, body):
    prompts_dir = Path(tmp_path) / "codex" / "prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / f"{role}.md").write_text(body)
    return Path(tmp_path)


# ---- 1. parse_tasks ----------------------------------------------------------------------------

class ParseTasksTests(unittest.TestCase):
    def test_fields_parsed_for_all_three_fixture_tasks(self):
        tasks = ce.parse_tasks(TASKS_TEXT_FIXTURE)
        by_id = {t["id"]: t for t in tasks}
        self.assertEqual(set(by_id), {"T1", "T2", "T3"})

        t1 = by_id["T1"]
        self.assertEqual(t1["title"], "First fixture task")
        self.assertEqual(t1["status"], "pending")
        self.assertEqual(t1["model"], "fake-cheap")
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
        self.assertEqual(t3["model"], "mid")  # raw tier word, unresolved at parse time
        self.assertEqual(t3["depends"], ["T1"])
        self.assertFalse(t3["independent"])

    def test_invalid_status_raises_value_error_listing_vocabulary(self):
        with self.assertRaises(ValueError) as ctx:
            ce.parse_tasks(INVALID_STATUS_TASKS_TEXT)
        msg = str(ctx.exception)
        for status_word in ce.STATUSES:
            self.assertIn(status_word, msg)


# ---- 2. tier resolution (D4 skip-up) and escalation_ladder --------------------------------------

class TierResolutionAndEscalationLadderTests(unittest.TestCase):
    def test_empty_mid_tier_skips_up_to_strong_first_in_file_order(self):
        # `mid` has ZERO models in the fixture -- and it is not `strong` -- proving the skip-up
        # rule generalizes to whichever tier happens to be empty.
        self.assertEqual(ce.resolve_tier(PRICING_FIXTURE, "mid"), "fake-strong-a")

    def test_populated_tiers_resolve_directly(self):
        self.assertEqual(ce.resolve_tier(PRICING_FIXTURE, "cheap"), "fake-cheap")
        self.assertEqual(ce.resolve_tier(PRICING_FIXTURE, "strong"), "fake-strong-a")
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

    def test_escalation_ladder_from_cheap_skips_empty_mid(self):
        ladder = ce.escalation_ladder(PRICING_FIXTURE, "fake-cheap")
        self.assertEqual(ladder, ["fake-strong-a", "fake-frontier"])

    def test_escalation_ladder_first_in_file_order_within_tier(self):
        ladder = ce.escalation_ladder(PRICING_FIXTURE, "fake-cheap")
        self.assertEqual(ladder[0], "fake-strong-a")
        self.assertNotIn("fake-strong-b", ladder)

    def test_escalation_ladder_from_frontier_is_empty(self):
        self.assertEqual(ce.escalation_ladder(PRICING_FIXTURE, "fake-frontier"), [])

    def test_unknown_or_none_model_id_defaults_to_mid_start(self):
        unknown = ce.escalation_ladder(PRICING_FIXTURE, "not-a-fixture-id")
        none_start = ce.escalation_ladder(PRICING_FIXTURE, None)
        self.assertEqual(unknown, none_start)
        self.assertEqual(none_start, ["fake-strong-a", "fake-frontier"])


# ---- 3. build_dispatch anatomy -------------------------------------------------------------------

class BuildDispatchTests(unittest.TestCase):
    def test_model_pinned_exact_argv(self):
        argv = ce.build_dispatch(STUB_BIN, "fake-cheap", "fake prompt text")
        self.assertIsInstance(argv, list)
        self.assertEqual(
            argv,
            [STUB_BIN, "exec", "--model", "fake-cheap", "--full-auto", "fake prompt text"],
        )

    def test_tier_word_pinned_resolves_through_skip_up_before_dispatch(self):
        model_id = ce.resolve_model(PRICING_FIXTURE, "mid")
        self.assertEqual(model_id, "fake-strong-a")  # skip-up: mid empty -> strong
        argv = ce.build_dispatch(STUB_BIN, model_id, "fake prompt text")
        self.assertEqual(argv[argv.index("--model") + 1], "fake-strong-a")

    def test_no_model_field_omits_model_pair(self):
        argv = ce.build_dispatch(STUB_BIN, None, "fake prompt text")
        self.assertNotIn("--model", argv)
        self.assertEqual(argv, [STUB_BIN, "exec", "--full-auto", "fake prompt text"])

    def test_effort_given_adds_reasoning_effort_flag(self):
        efforts = PRICING_FIXTURE["knobs"]["reasoning_efforts"]
        self.assertIn("high", efforts)  # sanity: using a word from the synthetic knobs list
        argv = ce.build_dispatch(STUB_BIN, "fake-cheap", "fake prompt text", effort="high")
        self.assertIn("-c", argv)
        self.assertEqual(argv[argv.index("-c") + 1], "model_reasoning_effort=high")

    def test_extra_args_positioned_before_prompt(self):
        argv = ce.build_dispatch(
            STUB_BIN,
            "fake-cheap",
            "fake prompt text",
            extra_args=("--sandbox=workspace-write", "--skip-git-repo-check"),
        )
        self.assertLess(
            argv.index("--sandbox=workspace-write"), argv.index("--skip-git-repo-check")
        )
        self.assertLess(argv.index("--skip-git-repo-check"), len(argv) - 1)

    def test_prompt_is_always_the_last_element(self):
        argv = ce.build_dispatch(
            STUB_BIN,
            "fake-cheap",
            "prompt-marker",
            effort="low",
            extra_args=("--extra1", "--extra2"),
        )
        self.assertEqual(argv[-1], "prompt-marker")

    def test_never_shell_true_dispatch_is_a_list(self):
        argv = ce.build_dispatch(STUB_BIN, "fake-cheap", "prompt text")
        self.assertIsInstance(argv, list)
        self.assertNotIsInstance(argv, str)


# ---- 4. preamble composition ---------------------------------------------------------------------

class PreambleCompositionTests(unittest.TestCase):
    def test_strips_frontmatter_resolves_placeholder_and_leaves_disk_file_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _write_preamble_bundle(tmp, "implementer", PREAMBLE_FIXTURE_BODY)

            result = ce.load_preamble("implementer", repo_root=repo_root)

            self.assertNotIn("{{POLYTROPOS_ROOT}}", result)
            self.assertIn(str(repo_root), result)
            self.assertFalse(result.lstrip().startswith("---"))
            self.assertNotIn("description: fixture role preamble", result)

            # the bundle file on disk is never rewritten -- placeholder still present.
            on_disk = (repo_root / "codex" / "prompts" / "implementer.md").read_text()
            self.assertIn("{{POLYTROPOS_ROOT}}", on_disk)

    def test_missing_role_file_raises_filenotfounderror_naming_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError) as ctx:
                ce.load_preamble("no-such-role", repo_root=Path(tmp))
            self.assertIn("no-such-role", str(ctx.exception))

    def test_cmd_run_dry_run_composes_the_real_preamble_plus_separator_plus_brief(self):
        # Drives `main(["run", ..., "--dry-run"])` end to end and inspects the ACTUAL prompt
        # `cmd_run` built and printed in its dispatch argv -- never a string the test re-derives
        # by hand with the same "preamble + separator + brief" formula. `cmd_run` has no CLI
        # override for the preamble's repo_root (it always reads the module-global `REPO_ROOT`),
        # so `REPO_ROOT` itself is patched to a temp fixture repo_root carrying the
        # frontmatter'd, placeholder-bearing bundle; the kit's brief is the known fixture text
        # from `SINGLE_TASK_TASKS_TEXT`, pinned via `parse_tasks` before it's relied on below.
        with tempfile.TemporaryDirectory() as tmp:
            fixture_repo_root = _write_preamble_bundle(tmp, "implementer", PREAMBLE_FIXTURE_BODY)
            kit_dir = _write_kit(tmp, SINGLE_TASK_TASKS_TEXT)
            known_brief = ce.parse_tasks(SINGLE_TASK_TASKS_TEXT)[0]["brief"]
            self.assertEqual(
                known_brief, "Fixture brief payload for the end-to-end stub-executable run."
            )

            buf = io.StringIO()
            with mock.patch.object(ce, "REPO_ROOT", fixture_repo_root):
                with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                    with contextlib.redirect_stdout(buf):
                        ce.main(
                            ["run", "--kit", str(kit_dir), "--codex-bin", STUB_BIN, "--dry-run"]
                        )
            output = buf.getvalue()

            # Pull the real dispatch argv back out of the printed `dispatch: <shlex.join(argv)>`
            # line -- the composed prompt may itself contain embedded newlines, so slice on the
            # `dispatch: ` / `\nverify: ` markers rather than splitting the buffer into lines.
            dispatch_start = output.index("dispatch: ") + len("dispatch: ")
            dispatch_end = output.rindex("\nverify: ")
            argv = shlex.split(output[dispatch_start:dispatch_end])

            self.assertEqual(argv[0], STUB_BIN)
            self.assertIn("--model", argv)
            self.assertEqual(argv[argv.index("--model") + 1], "fake-cheap")

            composed = argv[-1]  # the REAL prompt cmd_run dispatched -- captured, not re-derived

            # Genuine content checks against the real composition cmd_run actually built.
            self.assertNotIn("{{POLYTROPOS_ROOT}}", composed)
            self.assertNotIn("description: fixture role preamble", composed)
            self.assertIn(str(fixture_repo_root), composed)
            self.assertTrue(composed.endswith("\n\n---\n\n" + known_brief))

            # Cross-check against calling the real `load_preamble` directly (not a hand-written
            # re-derivation of the formula) plus the fixture kit's own parsed brief text.
            expected_preamble = ce.load_preamble("implementer", repo_root=fixture_repo_root)
            expected_tail = expected_preamble + "\n\n---\n\n" + known_brief
            self.assertTrue(composed.endswith(expected_tail))

            # T8 (PLAN D8/T7, ported in shape): `cmd_run` also prefixes the prompt with the
            # id-lineage preamble -- `[kit=<slug> run=<run id> task=<task id>]` -- ahead of the
            # role preamble; the rest of the composition (role preamble + separator + brief,
            # asserted above) is unchanged. The `run=` id is fresh random hex per invocation, so
            # it can't be pinned literally: extract it and confirm the prefix is EXACTLY what
            # `build_id_preamble` produces for it, not a hand-derived approximation.
            prefix = composed[: -len(expected_tail)]
            self.assertRegex(
                prefix, r"^\[kit=kit run=\d{4}-\d{2}-\d{2}-[0-9a-f]{4} task=E1\]\n\n$"
            )
            run_id = prefix.split("run=")[1].split(" ")[0]
            self.assertEqual(
                prefix, ce.build_id_preamble(kit="kit", run_id=run_id, task_id="E1") + "\n\n"
            )

            # the bundle file on disk is still untouched by the dry run -- placeholder present.
            on_disk = (fixture_repo_root / "codex" / "prompts" / "implementer.md").read_text()
            self.assertIn("{{POLYTROPOS_ROOT}}", on_disk)


# ---- 5. run_task with fake runners (pure, no subprocess anywhere) -------------------------------

class RunTaskTests(unittest.TestCase):
    @staticmethod
    def _task(**overrides):
        base = {
            "id": "T1",
            "title": "fixture task",
            "status": "pending",
            "model": "fake-cheap",
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

        result = ce.run_task(task, PRICING_FIXTURE, runner, verify_runner, codex_bin=STUB_BIN)

        self.assertEqual(result["status"], "done")
        self.assertEqual(runner.call_count, 1)
        dispatched_argv = runner.call_args_list[0].args[0]
        self.assertIn("--model", dispatched_argv)
        self.assertEqual(dispatched_argv[dispatched_argv.index("--model") + 1], "fake-cheap")
        self.assertEqual(result["escalations"], [])
        self.assertEqual(result["model_used"], "fake-cheap")

    def test_verify_fails_once_then_passes_escalates_exactly_one_rung_skipping_empty_mid(self):
        task = self._task()
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(side_effect=[(1, "boom: fixture failure"), (0, "ok now")])

        result = ce.run_task(task, PRICING_FIXTURE, runner, verify_runner, codex_bin=STUB_BIN)

        self.assertEqual(result["status"], "done")
        # empty `mid` tier is skipped -- the very next rung is `strong`, not a phantom `mid`.
        self.assertEqual(result["escalations"], ["fake-strong-a"])
        self.assertEqual(result["model_used"], "fake-strong-a")
        self.assertEqual(runner.call_count, 2)

        second_argv = runner.call_args_list[1].args[0]
        self.assertEqual(second_argv[second_argv.index("--model") + 1], "fake-strong-a")
        prompt_payload = second_argv[-1]
        self.assertIn(task["brief"], prompt_payload)
        self.assertIn("ESCALATION EVIDENCE", prompt_payload)
        self.assertIn("boom: fixture failure", prompt_payload)

    def test_verify_never_passes_exhausts_full_ladder_and_blocks(self):
        task = self._task()
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(return_value=(1, "always fails"))

        result = ce.run_task(task, PRICING_FIXTURE, runner, verify_runner, codex_bin=STUB_BIN)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["escalations"], ["fake-strong-a", "fake-frontier"])
        self.assertEqual(runner.call_count, 3)  # initial dispatch + one per ladder rung

    def test_max_escalations_truncates_ladder(self):
        task = self._task()
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(return_value=(1, "always fails"))

        result = ce.run_task(
            task, PRICING_FIXTURE, runner, verify_runner, max_escalations=1, codex_bin=STUB_BIN
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["escalations"], ["fake-strong-a"])
        self.assertEqual(runner.call_count, 2)


# ---- 6. append_note -------------------------------------------------------------------------------

class AppendNoteTests(unittest.TestCase):
    def test_block_has_id_and_model_no_lesson_line_without_escalations(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes_path = Path(tmp) / "NOTES.md"
            task = {"id": "T1", "model": "fake-cheap"}
            result = {
                "id": "T1",
                "status": "done",
                "model_used": "fake-cheap",
                "escalations": [],
                "verify_rc": 0,
                "role": "implementer",
            }
            ce.append_note(notes_path, result, task)
            text = notes_path.read_text()
            self.assertIn("T1", text)
            self.assertIn("fake-cheap", text)
            self.assertNotIn("lesson-candidate (routing):", text)

    def test_escalations_add_lesson_candidate_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes_path = Path(tmp) / "NOTES.md"
            task = {"id": "T3", "model": "fake-cheap"}
            result = {
                "id": "T3",
                "status": "done",
                "model_used": "fake-strong-a",
                "escalations": ["fake-strong-a"],
                "verify_rc": 0,
                "role": "implementer",
            }
            ce.append_note(notes_path, result, task)
            text = notes_path.read_text()
            self.assertIn("T3", text)
            self.assertIn("fake-strong-a", text)
            self.assertTrue(
                any(
                    line.startswith("lesson-candidate (routing):")
                    for line in text.splitlines()
                )
            )


# ---- 7. end-to-end main(["run", ...]) with a STUB executable -----------------------------------

class EndToEndRunHappyPathTests(unittest.TestCase):
    def test_main_run_with_stub_executable_completes_done_surgically(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, SINGLE_TASK_TASKS_TEXT)
            before_text = (kit_dir / "TASKS.md").read_text()

            log_path = tmp / "stub.log"
            stub_path = _write_stub(tmp, log_path)

            buf = io.StringIO()
            with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                with contextlib.redirect_stdout(buf):
                    ce.main(["run", "--kit", str(kit_dir), "--codex-bin", str(stub_path)])

            after_text = (kit_dir / "TASKS.md").read_text()
            before_lines = before_text.splitlines()
            after_lines = after_text.splitlines()
            self.assertEqual(len(before_lines), len(after_lines))
            diffs = [i for i in range(len(before_lines)) if before_lines[i] != after_lines[i]]
            self.assertEqual(len(diffs), 1)
            i = diffs[0]
            self.assertTrue(before_lines[i].strip().startswith("- status:"))
            self.assertEqual(after_lines[i].strip(), "- status: done")
            for j in range(len(before_lines)):
                if j != i:
                    self.assertEqual(before_lines[j], after_lines[j])

            tasks = ce.parse_tasks(after_text)
            self.assertEqual(tasks[0]["status"], "done")
            self.assertTrue((kit_dir / "NOTES.md").exists())
            self.assertIn("fake-cheap", (kit_dir / "NOTES.md").read_text())

            log_text = log_path.read_text()
            self.assertIn("exec", log_text)
            self.assertIn("--full-auto", log_text)
            self.assertEqual(_dispatched_models(log_text), ["fake-cheap"])


class EndToEndEscalationTests(unittest.TestCase):
    def test_escalation_exhausts_ladder_blocks_and_writes_lesson_note(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, ESCALATION_TASKS_TEXT)

            log_path = tmp / "stub.log"
            stub_path = _write_stub(tmp, log_path)

            buf = io.StringIO()
            with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                with contextlib.redirect_stdout(buf):
                    with self.assertRaises(SystemExit) as ctx:
                        ce.main(["run", "--kit", str(kit_dir), "--codex-bin", str(stub_path)])
            self.assertEqual(ctx.exception.code, 1)

            final_text = (kit_dir / "TASKS.md").read_text()
            tasks = ce.parse_tasks(final_text)
            self.assertEqual(tasks[0]["status"], "blocked")

            notes_text = (kit_dir / "NOTES.md").read_text()
            self.assertIn("lesson-candidate (routing):", notes_text)
            self.assertIn("fake-frontier", notes_text)

            # dispatch order across the ladder: cheap -> strong-a -> frontier, and the empty
            # `mid` tier's (nonexistent) model never appears in the sequence.
            log_text = log_path.read_text()
            self.assertEqual(
                _dispatched_models(log_text),
                ["fake-cheap", "fake-strong-a", "fake-frontier"],
            )


# ---- 8. dry-run spawns nothing --------------------------------------------------------------------

class DryRunSpawnsNothingTests(unittest.TestCase):
    def test_dry_run_never_touches_subprocess_and_leaves_kit_untouched(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, SINGLE_TASK_TASKS_TEXT)
            before = (kit_dir / "TASKS.md").read_bytes()

            with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                with mock.patch.object(ce, "subprocess") as mock_subprocess:
                    mock_subprocess.run.side_effect = AssertionError("subprocess in dry-run")
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        ce.main(
                            ["run", "--kit", str(kit_dir), "--codex-bin", STUB_BIN, "--dry-run"]
                        )
                    mock_subprocess.run.assert_not_called()

            after = (kit_dir / "TASKS.md").read_bytes()
            self.assertEqual(before, after)
            self.assertFalse((kit_dir / "NOTES.md").exists())
            self.assertIn("dispatch:", buf.getvalue())


class InvalidEffortRejectedBeforeDispatchTests(unittest.TestCase):
    def test_invalid_effort_exits_2_before_any_dispatch_or_write(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, SINGLE_TASK_TASKS_TEXT)
            before = (kit_dir / "TASKS.md").read_bytes()

            with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                with mock.patch.object(ce, "subprocess") as mock_subprocess:
                    mock_subprocess.run.side_effect = AssertionError("subprocess touched")
                    err = io.StringIO()
                    with contextlib.redirect_stderr(err):
                        with self.assertRaises(SystemExit) as ctx:
                            ce.main(
                                [
                                    "run", "--kit", str(kit_dir), "--codex-bin", STUB_BIN,
                                    "--effort", "not-a-real-effort",
                                ]
                            )
                    mock_subprocess.run.assert_not_called()
            self.assertEqual(ctx.exception.code, 2)
            self.assertIn("not-a-real-effort", err.getvalue())

            after = (kit_dir / "TASKS.md").read_bytes()
            self.assertEqual(before, after)
            self.assertFalse((kit_dir / "NOTES.md").exists())


# ---- 9. status --kit smoke ------------------------------------------------------------------------

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


# ---- 10. run id generation (T8, ported in shape from T7, PLAN D8 -- format pinned positively
# AND negatively) ---------------------------------------------------------------------------
#
# `generate_run_id` is ported verbatim in shape from `bin/copilot_execute.py`'s T7 function
# (itself ported from `bin/claude_execute.py`'s T5); these tests mirror T7's own
# `RunIdGenerationTests` so the format assertion lives on every generator side (Phase 1 review
# F8).

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


# ---- 11. id preamble (T8 -- kit/run/task ids in the dispatch prompt) ------------------------

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


# ---- 12. outcome ledger line (T1 grammar: run=/parent=) --------------------------------------

class OutcomeResultClassificationTests(unittest.TestCase):
    def test_blocked_status_is_always_blocked(self):
        self.assertEqual(ce.outcome_result("blocked", [], None), "blocked")
        self.assertEqual(ce.outcome_result("blocked", ["fake-strong-a"], "T1"), "blocked")

    def test_done_no_escalation_no_parent_is_plain_pass(self):
        self.assertEqual(ce.outcome_result("done", [], None), "pass")

    def test_done_with_escalations_is_escalated_pass(self):
        self.assertEqual(ce.outcome_result("done", ["fake-strong-a"], None), "escalated-pass")

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
            "T5", "fake-frontier", 3, "escalated-pass",
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
            task = {"id": "T1", "model": "fake-cheap"}
            result = {
                "id": "T1", "status": "done", "model_used": "fake-cheap",
                "escalations": [], "verify_rc": 0, "role": "implementer",
            }
            ce.append_note(notes_path, result, task, run_id="2026-07-26-abcd")
            text = notes_path.read_text()
            self.assertIn(
                "outcome: T1 model=fake-cheap attempts=1 result=pass review=none "
                "run=2026-07-26-abcd",
                text,
            )
            self.assertNotIn("parent=", text)

    def test_escalations_write_escalated_pass_outcome_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes_path = Path(tmp) / "NOTES.md"
            task = {"id": "T3", "model": "fake-cheap"}
            result = {
                "id": "T3", "status": "done", "model_used": "fake-strong-a",
                "escalations": ["fake-strong-a"], "verify_rc": 0, "role": "implementer",
            }
            ce.append_note(notes_path, result, task, run_id="2026-07-26-abcd")
            text = notes_path.read_text()
            self.assertIn(
                "outcome: T3 model=fake-strong-a attempts=2 result=escalated-pass "
                "review=none run=2026-07-26-abcd",
                text,
            )

    def test_parent_flows_through_to_the_outcome_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes_path = Path(tmp) / "NOTES.md"
            task = {"id": "T5", "model": "fake-cheap"}
            result = {
                "id": "T5", "status": "done", "model_used": "fake-cheap",
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
            self.assertIn("outcome: T2 model=unpinned", text)  # single token -- no space

    def test_no_run_id_or_parent_still_writes_a_plain_outcome_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes_path = Path(tmp) / "NOTES.md"
            task = {"id": "T1", "model": "fake-cheap"}
            result = {
                "id": "T1", "status": "done", "model_used": "fake-cheap",
                "escalations": [], "verify_rc": 0, "role": "implementer",
            }
            ce.append_note(notes_path, result, task)
            text = notes_path.read_text()
            self.assertIn(
                "outcome: T1 model=fake-cheap attempts=1 result=pass review=none", text
            )
            self.assertNotIn("run=", text)
            self.assertNotIn("parent=", text)


# ---- 13. run_task's precomputed prompt carries the id preamble onto every dispatch, including
# escalations (T8's analogue of T7's `RunTaskIdPreambleTests`) -------------------------------
#
# Unlike `copilot_execute.py` (whose `build_dispatch` re-composes the prompt from `brief` +
# ids on EVERY call), `codex_execute.py`'s `run_task` receives one already-fully-composed
# `prompt` string from its caller (`cmd_run`) and reuses that same string -- with escalation
# evidence appended -- for every rung. So the id preamble only needs to be baked into `prompt`
# ONCE by the caller (exactly what `cmd_run` now does) to land on every dispatch automatically;
# `run_task` itself needs no `kit`/`run_id` parameters to achieve the same effect T7 achieves
# via re-composition per rung.

class RunTaskIdPreambleTests(unittest.TestCase):
    @staticmethod
    def _task(**overrides):
        base = {
            "id": "T1",
            "title": "fixture task",
            "status": "pending",
            "model": "fake-cheap",
            "depends": [],
            "independent": True,
            "brief": "fake brief payload for id-preamble tests",
            "verify": "true",
        }
        base.update(overrides)
        return base

    def test_id_preamble_in_prompt_lands_on_every_dispatch_including_escalations(self):
        task = self._task()
        id_preamble = ce.build_id_preamble(
            kit="fixturekit", run_id="2026-07-26-9f3a", task_id="T1"
        )
        prompt = f"{id_preamble}\n\n{task['brief']}"
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(side_effect=[(1, "boom"), (0, "ok now")])

        ce.run_task(
            task, PRICING_FIXTURE, runner, verify_runner, prompt=prompt, codex_bin=STUB_BIN,
        )

        self.assertEqual(runner.call_count, 2)
        for call in runner.call_args_list:
            dispatched_prompt = call.args[0][-1]
            self.assertTrue(
                dispatched_prompt.startswith("[kit=fixturekit run=2026-07-26-9f3a task=T1]")
            )

    def test_no_prompt_given_falls_back_to_bare_brief_unaffected(self):
        task = self._task()
        runner = mock.Mock(return_value=None)
        verify_runner = mock.Mock(return_value=(0, "ok"))

        ce.run_task(task, PRICING_FIXTURE, runner, verify_runner, codex_bin=STUB_BIN)

        dispatched_prompt = runner.call_args_list[0].args[0][-1]
        self.assertEqual(dispatched_prompt, task["brief"])


# ---- 14. end-to-end: --dry-run shows the id preamble, real run stamps run=/parent= -----------

class EndToEndIdPreambleAndLineageTests(unittest.TestCase):
    def test_dry_run_argv_shows_id_preamble(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, SINGLE_TASK_TASKS_TEXT)
            before = (kit_dir / "TASKS.md").read_bytes()

            with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                with mock.patch.object(ce, "subprocess") as mock_subprocess:
                    mock_subprocess.run.side_effect = AssertionError("subprocess in dry-run")
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        ce.main(
                            ["run", "--kit", str(kit_dir), "--codex-bin", STUB_BIN, "--dry-run"]
                        )
            output = buf.getvalue()
            self.assertIn("[kit=kit run=", output)
            self.assertIn("task=E1]", output)

            after = (kit_dir / "TASKS.md").read_bytes()
            self.assertEqual(before, after)
            self.assertFalse((kit_dir / "NOTES.md").exists())

    def test_real_run_outcome_line_carries_run_id(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, SINGLE_TASK_TASKS_TEXT)

            log_path = tmp / "stub.log"
            stub_path = _write_stub(tmp, log_path)

            buf = io.StringIO()
            with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                with contextlib.redirect_stdout(buf):
                    ce.main(["run", "--kit", str(kit_dir), "--codex-bin", str(stub_path)])

            notes_text = (kit_dir / "NOTES.md").read_text()
            self.assertRegex(
                notes_text,
                r"outcome: E1 model=\S+ attempts=1 result=pass review=none "
                r"run=\d{4}-\d{2}-\d{2}-[0-9a-f]{4}",
            )
            self.assertNotIn("parent=", notes_text)

    def test_parent_flag_lands_on_the_outcome_line_as_escalated_pass(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            kit_dir = _write_kit(tmp, SINGLE_TASK_TASKS_TEXT)

            log_path = tmp / "stub.log"
            stub_path = _write_stub(tmp, log_path)

            buf = io.StringIO()
            with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                with contextlib.redirect_stdout(buf):
                    ce.main(
                        [
                            "run", "--kit", str(kit_dir), "--codex-bin", str(stub_path),
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
            with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                with mock.patch.object(ce, "subprocess") as mock_subprocess:
                    mock_subprocess.run.side_effect = AssertionError(
                        "dispatched despite a rejected --parent"
                    )
                    with contextlib.redirect_stderr(err):
                        with self.assertRaises(SystemExit) as ctx:
                            ce.main(
                                ["run", "--kit", str(kit_dir), "--codex-bin", STUB_BIN,
                                 "--parent", "E1"]
                            )
                    mock_subprocess.run.assert_not_called()

            self.assertEqual(ctx.exception.code, 2)
            self.assertIn("cannot be its own", err.getvalue())
            self.assertEqual(before, (kit_dir / "TASKS.md").read_bytes())
            self.assertFalse((kit_dir / "NOTES.md").exists())


# ---- 15. `parent=` rides ONLY an escalation result (Phases 3-4 review, P34-F2) ----------------

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
            task = {"id": "T7", "model": "fake-cheap"}
            result = {
                "id": "T7", "status": "blocked", "model_used": "fake-front",
                "escalations": ["fake-strong-a", "fake-front"], "verify_rc": 1,
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
            task = {"id": "T7", "model": "fake-cheap"}
            result = {
                "id": "T7", "status": "done", "model_used": "fake-strong-a",
                "escalations": ["fake-strong-a"], "verify_rc": 0, "role": "implementer",
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
            kit_dir = _write_kit(tmp, ESCALATION_TASKS_TEXT)  # verify is `false` -> blocked

            log_path = tmp / "stub.log"
            stub_path = _write_stub(tmp, log_path)

            buf = io.StringIO()
            with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                with contextlib.redirect_stdout(buf):
                    with self.assertRaises(SystemExit) as ctx:  # a blocked task exits nonzero
                        ce.main(
                            [
                                "run", "--kit", str(kit_dir), "--codex-bin", str(stub_path),
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


class CountPlanBudgetUsageTests(unittest.TestCase):
    def test_empty_notes_all_zero(self):
        self.assertEqual(
            ce.count_plan_budget_usage(""),
            {"max-dispatches": 0, "max-escalations": 0, "max-consults": 0},
        )

    def test_sums_attempts_and_escalations_across_lines(self):
        notes = "\n".join([
            "- outcome: A1 model=fake-cheap attempts=1 result=pass review=none",
            "- outcome: A2 model=fake-strong-a attempts=3 result=escalated-pass review=none",
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
            kit_dir = _write_kit(tmp, SINGLE_TASK_TASKS_TEXT)  # task id E1, model fake-cheap
            (kit_dir / "PLAN.md").write_text("# PLAN\n\nbudget: max-dispatches=1\n")
            (kit_dir / "NOTES.md").write_text(
                "## 2026-07-25T00:00:00Z — E0\n"
                "- outcome: E0 model=fake-cheap attempts=1 result=pass review=none "
                "run=2026-07-25-1234\n"
            )
            before_tasks_text = (kit_dir / "TASKS.md").read_text()

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
                                    ["run", "--kit", str(kit_dir), "--codex-bin", "unused-stub"]
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
                r"outcome: E1 model=fake-cheap attempts=0 result=budget-stop review=none "
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
            kit_dir = _write_kit(tmp, SINGLE_TASK_TASKS_TEXT)  # task id E1, model fake-cheap
            (kit_dir / "PLAN.md").write_text("# PLAN\n\nbudget: max-dispatches=1\n")
            recorded = (
                "## 2026-07-25T00:00:00Z — E1\n"
                "- outcome: E1 model=fake-cheap attempts=2 result=blocked review=revised "
                "run=2026-07-25-1234 failure=verification\n"
            )
            (kit_dir / "NOTES.md").write_text(recorded)
            before_tasks_text = (kit_dir / "TASKS.md").read_text()

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
                                    ["run", "--kit", str(kit_dir), "--task", "E1",
                                     "--codex-bin", "unused-stub"]
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
                "- outcome: E1 model=fake-cheap attempts=0 result=budget-stop review=none "
                "run=2026-07-25-5678\n"
            )

            with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                with mock.patch.object(ce, "subprocess") as mock_subprocess:
                    mock_subprocess.run.side_effect = AssertionError("dispatched")
                    err = io.StringIO()
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        with contextlib.redirect_stderr(err):
                            with self.assertRaises(SystemExit):
                                ce.main(
                                    ["run", "--kit", str(kit_dir), "--task", "E1",
                                     "--codex-bin", "unused-stub"]
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
            log_path = tmp / "stub.log"
            stub_path = _write_stub(tmp, log_path)

            buf = io.StringIO()
            with mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE):
                with contextlib.redirect_stdout(buf):
                    ce.main(["run", "--kit", str(kit_dir), "--codex-bin", str(stub_path)])

            tasks = ce.parse_tasks((kit_dir / "TASKS.md").read_text())
            self.assertEqual(tasks[0]["status"], "done")
            notes_text = (kit_dir / "NOTES.md").read_text()
            self.assertIn("result=pass", notes_text)
            self.assertNotIn("budget-stop", notes_text)


if __name__ == "__main__":
    unittest.main()
