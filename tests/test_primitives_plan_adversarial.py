"""Adversarial tests for T5: `plan`, `matrix --markdown`, and `render_matrix_markdown`.

Authored from T5's BRIEF and pinned acceptance criteria in
`.claude/kits/aesop-fold/TASKS.md` (section "T5 -- `plan` subcommand and `matrix
--markdown`"), NOT by reading `bin/primitives.py`'s implementation and reverse-engineering
tests that match it. Expectations were formed from the contract first; the real code was
then run against them.

bin/ is not a package; primitives.py is loaded via importlib by absolute path computed
from this file's own location, matching the repo's existing convention (see
tests/test_harness_select.py).

Safety: every manifest fixture used against the CLI is written to a fresh
`tempfile.TemporaryDirectory()` -- no tracked file in this repo is ever touched. The
matrix-derivation tests mutate only `copy.deepcopy()`'d in-memory dicts and hand the
mutated dict straight to the pure `render_matrix_markdown()` / `plan()` functions; no file
on disk (tracked or otherwise) is ever written to prove those mutations propagate. Nothing
here invokes a real `claude`/`copilot`/`codex`/`gh` CLI, touches the network, or reads
`~/`.
"""

import contextlib
import copy
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PRIM = _load("primitives")
MATRIX = PRIM.load_matrix()

VALID_HARNESS_IDS = ["claude-code", "codex", "copilot", "cursor", "antigravity", "vscode"]
PRIMITIVE_ORDER = MATRIX["primitives"]


def _run(argv):
    """Invoke primitives.main(argv); return (exit_code, stdout, stderr).

    Tolerates either a plain int return from main() or a SystemExit raised by argparse
    itself (e.g. for a malformed mutually-exclusive flag combination), so this helper
    reports the real observed exit code regardless of which mechanism produced it.
    """
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = PRIM.main(argv)
    except SystemExit as exc:
        code = exc.code
    return code, out.getvalue(), err.getvalue()


def _write(dirpath, text, name="manifest.toml"):
    p = Path(dirpath) / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def _table_lines(markdown_text):
    """Lines of the pipe-table only (header, separator, then one per primitive)."""
    return [line for line in markdown_text.split("\n") if line.startswith("|")]


CLEAN_MANIFEST = """\
version = 1
harnesses = ["claude-code"]

[project]
name = "fixture-clean"

[project.commands]
test = "true"

[pathway]
profile = "balanced"

[primitives]

[state]
dir = "tasks/"
"""

COPILOT_LIKE_MANIFEST = """\
version = 1
harnesses = ["copilot"]
registries = ["builtin"]

[project]
name = "fixture-copilot-like"
stack = ["python3-stdlib"]

[project.commands]
test = "python3 -m unittest discover -s tests"

[pathway]
profile = "token-lean"

[primitives]
agents = ["route", "architect"]
skills = ["route", "usage"]

[primitives.instructions]

[[primitives.instructions.blocks]]
scope = "project"
content = "Fixture instructions block."

[state]
dir = "tasks/"
"""

SECRET_ONLY_MANIFEST = CLEAN_MANIFEST.replace(
    'name = "fixture-clean"',
    'name = "fixture-clean"\nstack = ["ghp_ABCDEFGHIJ1234567890AB"]',
)

VERIFY_LOOP_ONLY_MANIFEST = CLEAN_MANIFEST.replace(
    'test = "true"', 'test = "TODO: set your test command"'
)

# Mirrors copilot/aesop.toml's own declared shape (harnesses=["copilot"], agents+skills
# populated, no commands/mcp/hooks/permissions/loops) as a plain dict, for pure-function
# tests that should not need TOML parsing at all.
COPILOT_LIKE_DICT = {
    "harnesses": ["copilot"],
    "primitives": {
        "instructions": {"blocks": [{"scope": "project", "content": "x"}]},
        "agents": ["route", "architect"],
        "skills": ["route", "usage"],
    },
}

FULL_MANIFEST_DICT = {
    "harnesses": ["claude-code", "cursor"],
    "primitives": {
        "instructions": {"blocks": [{"scope": "project", "content": "hello"}]},
        "skills": ["a"],
        "agents": ["b"],
        "commands": ["c"],
        "mcp": [{"name": "m", "transport": "stdio"}],
        "hooks": [{"name": "h"}],
        "permissions": {"unattended": "none"},
        "loops": [
            {
                "name": "g",
                "goal": "g",
                "verify": "true",
                "stops": {"max_iterations": 1, "no_progress_after": 1, "budget_usd": 1},
            }
        ],
    },
    "state": {"dir": "tasks/"},
}

EMPTY_LISTS_MANIFEST_DICT = {
    "harnesses": ["claude-code"],
    "primitives": {
        "skills": [],
        "agents": [],
        "commands": [],
        "mcp": [],
        "hooks": [],
        "loops": [],
        "permissions": {},
    },
}

ABSENT_KEYS_MANIFEST_DICT = {
    "harnesses": ["claude-code"],
    "primitives": {},
}

VARIABLE_PRIMITIVE_IDS = ["skill", "agent", "command", "mcp", "hook", "permissions", "loop"]


def _declared_map(plan_result, harness_id):
    entries = plan_result["harnesses"][harness_id]["primitives"]
    return {e["id"]: e["declared"] for e in entries}


# ---------------------------------------------------------------------------
# 1. `declared` semantics -- probe every branch.
# ---------------------------------------------------------------------------
class TestDeclaredSemantics(unittest.TestCase):
    def test_all_declared_true_when_fully_populated(self):
        result = PRIM.plan(FULL_MANIFEST_DICT, MATRIX, harnesses=["claude-code"])
        declared = _declared_map(result, "claude-code")
        for pid in PRIMITIVE_ORDER:
            self.assertTrue(declared[pid], f"{pid} should be declared True when populated")

    def test_variable_primitives_declared_false_when_lists_and_table_present_but_empty(self):
        result = PRIM.plan(EMPTY_LISTS_MANIFEST_DICT, MATRIX, harnesses=["claude-code"])
        declared = _declared_map(result, "claude-code")
        for pid in VARIABLE_PRIMITIVE_IDS:
            self.assertFalse(
                declared[pid],
                f"{pid} present-but-empty must be declared False (empty list/table)",
            )

    def test_variable_primitives_declared_false_when_keys_entirely_absent(self):
        result = PRIM.plan(ABSENT_KEYS_MANIFEST_DICT, MATRIX, harnesses=["claude-code"])
        declared = _declared_map(result, "claude-code")
        for pid in VARIABLE_PRIMITIVE_IDS:
            self.assertFalse(
                declared[pid], f"{pid} entirely absent must be declared False"
            )

    def test_instructions_and_state_declared_true_even_when_sections_wholly_absent(self):
        # ABSENT_KEYS_MANIFEST_DICT has no primitives.instructions and no top-level state.
        result = PRIM.plan(ABSENT_KEYS_MANIFEST_DICT, MATRIX, harnesses=["claude-code"])
        declared = _declared_map(result, "claude-code")
        self.assertTrue(declared["instructions"])
        self.assertTrue(declared["state"])

    def test_permissions_declared_true_with_single_default_looking_key(self):
        # unattended="none" is the SCHEMA DEFAULT VALUE -- presence of the key must still
        # count, regardless of whether the value looks like "nothing was configured".
        manifest = {
            "harnesses": ["claude-code"],
            "primitives": {"permissions": {"unattended": "none"}},
        }
        result = PRIM.plan(manifest, MATRIX, harnesses=["claude-code"])
        self.assertTrue(_declared_map(result, "claude-code")["permissions"])

    def test_permissions_declared_true_with_single_empty_list_value_key(self):
        # The key's VALUE is an empty list; the key itself is present. Declared is about
        # key presence in the table, not truthiness of that key's value.
        manifest = {
            "harnesses": ["claude-code"],
            "primitives": {"permissions": {"mutate_allow": []}},
        }
        result = PRIM.plan(manifest, MATRIX, harnesses=["claude-code"])
        self.assertTrue(_declared_map(result, "claude-code")["permissions"])

    def test_declared_is_identical_across_different_harnesses(self):
        # declared reflects the manifest, not the harness being planned for.
        result = PRIM.plan(FULL_MANIFEST_DICT, MATRIX, harnesses=["claude-code", "cursor"])
        self.assertEqual(
            _declared_map(result, "claude-code"), _declared_map(result, "cursor")
        )


# ---------------------------------------------------------------------------
# 2. D7 -- plan on a manifest declaring ONLY copilot, --harness cursor, must return a
#    full nine-entry cursor plan (never silently fall back to manifest["harnesses"]).
# ---------------------------------------------------------------------------
class TestD7CursorReadiness(unittest.TestCase):
    def test_cli_plan_explicit_cursor_on_copilot_only_manifest_json(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, COPILOT_LIKE_MANIFEST)
            code, out, err = _run(["plan", path, "--harness", "cursor", "--json"])
        self.assertEqual(code, 0, f"stdout={out!r} stderr={err!r}")
        data = json.loads(out)
        self.assertEqual(set(data["harnesses"].keys()), {"cursor"})
        entries = data["harnesses"]["cursor"]["primitives"]
        self.assertEqual(len(entries), 9)
        by_id = {e["id"]: e for e in entries}
        self.assertEqual(set(by_id.keys()), set(PRIMITIVE_ORDER))

        cursor_cells = MATRIX["harnesses"]["cursor"]["cells"]
        # Sanity: the matrix data itself matches D7's pinned qualitative claim.
        native_ids = {pid for pid, c in cursor_cells.items() if c["support"] == "native"}
        self.assertEqual(native_ids, {"instructions", "mcp", "state"})

        for pid, entry in by_id.items():
            self.assertEqual(entry["support"], cursor_cells[pid]["support"])
            self.assertEqual(entry["target"], cursor_cells[pid]["target"])

        expected_declared = {
            "instructions": True,
            "skill": True,
            "agent": True,
            "command": False,
            "mcp": False,
            "hook": False,
            "permissions": False,
            "loop": False,
            "state": True,
        }
        for pid, expected in expected_declared.items():
            self.assertEqual(
                by_id[pid]["declared"], expected, f"declared mismatch for {pid}"
            )

        self.assertEqual(
            data["harnesses"]["cursor"]["goal_mode"],
            MATRIX["harnesses"]["cursor"]["goal_mode"],
        )
        self.assertEqual(data["harnesses"]["cursor"]["goal_mode"], "ralph")

    def test_cli_plan_text_output_matches_pinned_line_shape(self):
        cursor_cells = MATRIX["harnesses"]["cursor"]["cells"]
        declared_map = {
            "instructions": True,
            "skill": True,
            "agent": True,
            "command": False,
            "mcp": False,
            "hook": False,
            "permissions": False,
            "loop": False,
            "state": True,
        }
        expected = [
            f"## cursor  (goal mode: {MATRIX['harnesses']['cursor']['goal_mode']})"
        ]
        for pid in PRIMITIVE_ORDER:
            decl_str = "declared" if declared_map[pid] else "—"
            support = cursor_cells[pid]["support"]
            targets = ", ".join(cursor_cells[pid]["target"])
            expected.append(f"{pid:<12}  {decl_str:<9}  {support}  {targets}")

        with tempfile.TemporaryDirectory() as d:
            path = _write(d, COPILOT_LIKE_MANIFEST)
            code, out, err = _run(["plan", path, "--harness", "cursor"])
        self.assertEqual(code, 0, f"stdout={out!r} stderr={err!r}")
        self.assertEqual(out.splitlines(), expected)

    def test_pure_plan_explicit_harness_overrides_manifest_declared_harnesses(self):
        # Isolate the pure function from the CLI entirely: a manifest declaring only
        # "copilot" must yield a "cursor" plan when harnesses=["cursor"] is passed, and
        # must NOT silently plan for "copilot" instead.
        result = PRIM.plan(COPILOT_LIKE_DICT, MATRIX, harnesses=["cursor"])
        self.assertEqual(set(result["harnesses"].keys()), {"cursor"})
        self.assertNotIn("copilot", result["harnesses"])
        entries = result["harnesses"]["cursor"]["primitives"]
        self.assertEqual(len(entries), 9)

    def test_pure_plan_none_harnesses_falls_back_to_manifest_harnesses(self):
        manifest = {"harnesses": ["claude-code", "codex"], "primitives": {}}
        result = PRIM.plan(manifest, MATRIX, harnesses=None)
        self.assertEqual(set(result["harnesses"].keys()), {"claude-code", "codex"})


# ---------------------------------------------------------------------------
# 3. validate-first gate.
# ---------------------------------------------------------------------------
class TestValidateFirstGate(unittest.TestCase):
    def test_secret_only_finding_blocks_plan_with_no_plan_output(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, SECRET_ONLY_MANIFEST)
            code, out, err = _run(["plan", path])
        self.assertEqual(code, 2)
        combined = out + err
        self.assertIn("secret", combined)
        self.assertNotIn("##", combined, "a secret-only finding must produce NO plan output")

    def test_non_secret_finding_also_blocks_plan(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, VERIFY_LOOP_ONLY_MANIFEST)
            code, out, err = _run(["plan", path])
        self.assertEqual(code, 2)
        combined = out + err
        self.assertIn("verify-loop", combined)
        self.assertNotIn("##", combined, "any finding must block plan output, not just secret")

    def test_clean_manifest_plan_exits_zero_with_output(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, CLEAN_MANIFEST)
            code, out, err = _run(["plan", path])
        self.assertEqual(code, 0, f"stdout={out!r} stderr={err!r}")
        self.assertIn("##", out)


class TestPlanUnknownHarness(unittest.TestCase):
    def test_plan_unknown_harness_exits_2_and_lists_valid_ids(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, CLEAN_MANIFEST)
            code, out, err = _run(["plan", path, "--harness", "not-a-real-harness"])
        self.assertEqual(code, 2)
        combined = out + err
        for hid in VALID_HARNESS_IDS:
            self.assertIn(hid, combined, f"valid id {hid} should be listed on error")


# ---------------------------------------------------------------------------
# 4. `matrix --markdown` determinism and derivation.
# ---------------------------------------------------------------------------
class TestMatrixMarkdown(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_byte_stable_across_two_runs(self):
        _, out_a, _ = _run(["matrix", "--markdown"])
        _, out_b, _ = _run(["matrix", "--markdown"])
        self.assertEqual(out_a, out_b)

    def test_lf_only_and_single_trailing_newline(self):
        _, out, _ = _run(["matrix", "--markdown"])
        self.assertNotIn("\r", out)
        self.assertTrue(out.endswith("\n"))
        self.assertFalse(out.endswith("\n\n"))

    def test_table_matches_independent_renderer_built_from_matrix_json(self):
        # NOTE: T5's brief shows a compact "|---|---|...|" separator in its illustrative
        # "print exactly" block, but its OWN pinned Verify: script greps `^| ` (pipe then
        # a literal space) and requires exactly 11 matching lines (header + 9 rows + the
        # separator). A compact, space-free separator would only bring the count to 10
        # (header + 9 rows), never satisfying that grep. The verify script is the
        # mechanically-checked, authoritative half of the contract, so this independent
        # renderer follows it: a separator row of "| --- | --- | ... |", matching the
        # header/data rows' own spacing convention.
        hids = list(MATRIX["harnesses"].keys())
        sep_cells = ["---"] * (1 + len(hids))
        lines = [
            "| Primitive | " + " | ".join(hids) + " |",
            "| " + " | ".join(sep_cells) + " |",
        ]
        for pid in PRIMITIVE_ORDER:
            cells = [MATRIX["harnesses"][h]["cells"][pid]["support"] for h in hids]
            lines.append("| " + pid + " | " + " | ".join(cells) + " |")
        lines.append("")
        goal_line = "Goal modes: " + " · ".join(
            f"{h}={MATRIX['harnesses'][h]['goal_mode']}" for h in hids
        )
        lines.append(goal_line)
        expected = "\n".join(lines) + "\n"

        _, out, _ = _run(["matrix", "--markdown"])
        self.assertEqual(out, expected)

    def test_pinned_verify_script_line_count_is_11(self):
        # Direct encoding of T5's own pinned Verify: command:
        #   test "$(grep -c '^| ' /tmp/pt-matrix-a.md)" = "11"
        _, out, _ = _run(["matrix", "--markdown"])
        matching = [line for line in out.split("\n") if line.startswith("| ")]
        self.assertEqual(len(matching), 11)

    def test_goal_modes_line_matches_pinned_literal_example(self):
        expected_line = (
            "Goal modes: claude-code=native · codex=native · copilot=ralph "
            "· cursor=ralph · antigravity=scheduled · vscode=ralph"
        )
        _, out, _ = _run(["matrix", "--markdown"])
        self.assertIn(expected_line, out.splitlines())

    def test_cli_output_matches_pure_render_function_on_same_matrix(self):
        _, cli_out, _ = _run(["matrix", "--markdown"])
        pure_out = PRIM.render_matrix_markdown(PRIM.load_matrix())
        self.assertEqual(cli_out.rstrip("\n"), pure_out.rstrip("\n"))


# ---------------------------------------------------------------------------
# 5. `--markdown --harness x` is a usage error (exit 1), never exit 2 (findings).
# ---------------------------------------------------------------------------
class TestMarkdownHarnessUsageError(unittest.TestCase):
    def test_markdown_with_harness_exits_1_not_2(self):
        code, out, err = _run(["matrix", "--markdown", "--harness", "cursor"])
        self.assertEqual(code, 1, f"stdout={out!r} stderr={err!r}")

    def test_markdown_with_harness_error_message_on_stderr_prefixed_error(self):
        _, out, err = _run(["matrix", "--markdown", "--harness", "cursor"])
        self.assertTrue(
            err.strip().startswith("error:") or out.strip().startswith("error:"),
            f"expected an 'error:'-prefixed usage message; got stdout={out!r} stderr={err!r}",
        )

    def test_markdown_alone_still_exits_0(self):
        code, _, _ = _run(["matrix", "--markdown"])
        self.assertEqual(code, 0)


# ---------------------------------------------------------------------------
# 6. `render_matrix_markdown` is importable, pure, and takes matrix as data.
# ---------------------------------------------------------------------------
class TestRenderMatrixMarkdownPurity(unittest.TestCase):
    def test_importable_top_level_and_deterministic_on_repeat_call(self):
        out_a = PRIM.render_matrix_markdown(MATRIX)
        out_b = PRIM.render_matrix_markdown(MATRIX)
        self.assertEqual(out_a, out_b)
        self.assertIsInstance(out_a, str)

    def test_reflects_mutated_goal_mode(self):
        mutated = copy.deepcopy(MATRIX)
        mutated["harnesses"]["copilot"]["goal_mode"] = "native"
        out = PRIM.render_matrix_markdown(mutated)
        self.assertIn("copilot=native", out)
        self.assertNotIn("copilot=ralph", out)

    def test_reflects_mutated_cell_support(self):
        baseline = PRIM.render_matrix_markdown(MATRIX)
        mutated = copy.deepcopy(MATRIX)
        mutated["harnesses"]["cursor"]["cells"]["skill"]["support"] = "native"
        out = PRIM.render_matrix_markdown(mutated)
        self.assertNotEqual(out, baseline)

        hids = list(mutated["harnesses"].keys())
        col = hids.index("cursor") + 1  # column 0 is "Primitive"
        row_idx = 2 + PRIMITIVE_ORDER.index("skill")  # 0=header,1=sep,2..=rows
        row = _table_lines(out)[row_idx]
        cell = [c.strip() for c in row.strip("|").split("|")][col]
        self.assertEqual(cell, "native")

    def test_reflects_reordered_and_renamed_harness_key(self):
        mutated = copy.deepcopy(MATRIX)
        mutated["harnesses"]["zzz-renamed"] = mutated["harnesses"].pop("antigravity")
        reordered_ids = ["cursor"] + [h for h in mutated["harnesses"] if h != "cursor"]
        mutated["harnesses"] = {h: mutated["harnesses"][h] for h in reordered_ids}

        out = PRIM.render_matrix_markdown(mutated)
        header = _table_lines(out)[0]
        self.assertIn("zzz-renamed", header)
        self.assertNotIn("antigravity", out)
        self.assertLess(header.index("cursor"), header.index("claude-code"))

    def test_fully_fabricated_matrix_proves_no_disk_read(self):
        fake_matrix = {
            "primitives": list(reversed(PRIMITIVE_ORDER)),
            "harnesses": {
                "zzz-fake-harness": {
                    "goal_mode": "totally-made-up",
                    "cells": {
                        pid: {"support": "native", "target": [], "notes": "x"}
                        for pid in PRIMITIVE_ORDER
                    },
                }
            },
        }
        out = PRIM.render_matrix_markdown(fake_matrix)
        for real_hid in VALID_HARNESS_IDS:
            self.assertNotIn(real_hid, out, f"real harness id {real_hid} leaked in")
        self.assertIn("zzz-fake-harness", out)
        self.assertIn("totally-made-up", out)

        rows = _table_lines(out)[2:]
        row_ids_in_order = [r.strip("|").split("|")[0].strip() for r in rows]
        self.assertEqual(row_ids_in_order, list(reversed(PRIMITIVE_ORDER)))


# ---------------------------------------------------------------------------
# 7. Regression check on T4's `check` surface after the cmd_check/cmd_plan refactor.
# ---------------------------------------------------------------------------
class TestCheckRegressionAfterT5Refactor(unittest.TestCase):
    def test_check_clean_manifest_exits_0(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, CLEAN_MANIFEST)
            code, out, err = _run(["check", path])
        self.assertEqual(code, 0, f"stdout={out!r} stderr={err!r}")
        self.assertIn("ok:", out)

    def test_check_missing_file_exits_1_with_error_prefix_on_stderr(self):
        code, out, err = _run(["check", "/definitely/not/a/real/manifest__.toml"])
        self.assertEqual(code, 1)
        self.assertTrue(err.strip().startswith("error:"), f"stderr={err!r}")

    def test_check_findings_exits_2_and_prints_findings(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, VERIFY_LOOP_ONLY_MANIFEST)
            code, out, err = _run(["check", path])
        self.assertEqual(code, 2)
        self.assertIn("verify-loop", out)
        self.assertIn("finding", out)

    def test_check_json_exactly_three_keys_clean_and_dirty(self):
        with tempfile.TemporaryDirectory() as d:
            clean_path = _write(d, CLEAN_MANIFEST, name="clean.toml")
            dirty_path = _write(d, VERIFY_LOOP_ONLY_MANIFEST, name="dirty.toml")

            code_clean, out_clean, _ = _run(["check", clean_path, "--json"])
            code_dirty, out_dirty, _ = _run(["check", dirty_path, "--json"])

        self.assertEqual(code_clean, 0)
        self.assertEqual(code_dirty, 2)
        data_clean = json.loads(out_clean)
        data_dirty = json.loads(out_dirty)
        self.assertEqual(set(data_clean.keys()), {"manifest", "ok", "findings"})
        self.assertEqual(set(data_dirty.keys()), {"manifest", "ok", "findings"})
        self.assertTrue(data_clean["ok"])
        self.assertFalse(data_dirty["ok"])


if __name__ == "__main__":
    unittest.main()
