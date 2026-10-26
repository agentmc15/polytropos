"""`kit_contract.py analyze`: a kit checked against itself before the first dispatch (kit-preflight T4).

WHAT WAS WRONG. The brief-defect ledger's most frequent kinds -- a verify command naming a
script no task writes, a verify block in a dialect the drivers never read, a path a brief
anchors on that is not in the tree -- were each found AFTER a dispatch had been paid for, by an
implementer or a verifier tripping over them. Every one is visible from TASKS.md's text plus a
stat of the tree. `analyze` reads exactly that and nothing else.

WHAT THESE TESTS PIN, against PLAN D2/D3 (D3 as amended before T4) and D17(a):

  - static by construction: `analyze_kit` has no runner parameter, and it still returns when
    `_pr`, `_ep`, `subprocess` and the `os` spawn family all raise;
  - only `verify-unparseable` fails (exit 3); a missing executable or path, in a brief or a
    verify, is a printed warning (exit 0) unless `strict`;
  - a path a task (or one upstream of it) says it creates is `created-by`, disclosed, never a
    silent pass, and a downstream task's claim does not count;
  - heredoc bodies and `$(...)` are not tokenized; `&&`/`||`/`;`/`|` split commands only
    outside quotes; `test`/`[` operands are values, never paths;
  - an exploration-shaped kit (`true`, `python3 -c ...`, briefs naming files they create)
    passes, so the drivers' fail-closed call cannot block a spike for being a spike;
  - nothing in the kit dir changes, and the fixture repo's `git status` stays empty.

Every fixture is a temp kit under `<tmp>/.claude/kits/fx` with its files under `<tmp>`, so the
repo root `analyze` resolves is the temp dir, never this checkout. No committed kit is read.
"""

import contextlib
import importlib.util
import inspect
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
KC_PATH = ROOT / "bin" / "kit_contract.py"


def _load():
    spec = importlib.util.spec_from_file_location("kit_contract_analyze_test", KC_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


kc = _load()

HINT = "uses a dialect (`Verify:` or a bare fence) that `kit_contract` does not read"


def _block(tid, brief, verify, depends=(), status="pending", dialect="bold"):
    """One task block. `dialect` picks the verify form: `bold` is the one `_extract_verify`
    reads; the others are the forms it does not."""
    dep = ", ".join(depends) if depends else "(none)"
    if dialect == "bold":
        vblock = f"**Verify.**\n\n```bash\n{verify}\n```\n"
    elif dialect == "bold-colon-bare":
        vblock = f"**Verify:**\n\n```\n{verify}\n```\n"
    elif dialect == "bold-dot-bare":
        vblock = f"**Verify.**\n\n```\n{verify}\n```\n"
    elif dialect == "dash-line":
        vblock = f"- Verify: `{verify}`\n"
    elif dialect == "plain-colon-bare":
        vblock = f"Verify:\n```\n{verify}\n```\n"
    elif dialect == "none":
        vblock = ""
    else:
        raise AssertionError(dialect)
    return (
        f"### {tid} — Task {tid}\n"
        f"- id: {tid}\n"
        f"- title: task {tid}\n"
        f"- status: {status}\n"
        f"- model: haiku\n"
        f"- depends: {dep}\n"
        f"\n**Brief.** {brief}\n"
        f"\n**Acceptance.** {tid} holds.\n\n"
        f"{vblock}"
    )


class _KitFixture(unittest.TestCase):
    """A temp repo root holding `.claude/kits/fx`; `analyze` must resolve paths against it."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="polytropos-analyze-")
        self.root = Path(self._tmp.name).resolve()
        self.kit = self.root / ".claude" / "kits" / "fx"
        self.kit.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def write_kit(self, *blocks):
        text = "# fx — tasks\n\n## Phase 1 — fixtures\n\n" + "\n".join(blocks)
        (self.kit / "TASKS.md").write_text(text)
        return kc.parse_tasks(text)

    def touch(self, *rels):
        for rel in rels:
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x\n")

    def analyze(self, tasks, strict=False):
        return kc.analyze_kit(self.kit, tasks, strict=strict)

    def kinds(self, result, task=None):
        return [f["kind"] for f in result["findings"] if task is None or f["task"] == task]

    def snapshot(self):
        files = {}
        for p in sorted(self.kit.rglob("*")):
            if p.is_file():
                files[str(p.relative_to(self.kit))] = p.read_bytes()
        return sorted(os.listdir(self.kit)), files

    def sound_kit(self):
        """Case 1's kit: every brief path and every verify path exists under the temp root."""
        self.touch("bin/tool.py", "docs/guide.md", "tests/test_tool.py")
        return self.write_kit(
            _block("T1", "Edit `bin/tool.py` and `docs/guide.md`; see `bin/tool.py:12`.",
                   "python3 bin/tool.py && python3 -m unittest discover -s tests -p "
                   "'test_tool.py' -q"),
            _block("T2", "Read `docs/guide.md`.", "test -f bin/tool.py && grep -q x docs/guide.md",
                   depends=["T1"]),
        )


class SoundAndUnsoundTests(_KitFixture):
    def test_case1_a_sound_kit_exits_0_with_every_path_existing(self):
        tasks = self.sound_kit()
        result = self.analyze(tasks)
        self.assertEqual(result["exit"], 0)
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["v"], kc.CONTRACT_VERSION)
        self.assertEqual(result["kit"], "fx")
        self.assertIs(result["strict"], False)
        brief = [e["path"] for e in result["paths"]["T1"]]
        self.assertEqual(brief, ["bin/tool.py", "docs/guide.md"])  # `:12` stripped, deduped
        for tid in ("T1", "T2"):
            for entry in result["paths"][tid] + result["verify"][tid]["paths"]:
                self.assertEqual(entry["state"], "exists", entry)
                self.assertIsNone(entry["by"])
            self.assertTrue(result["verify"][tid]["parseable"])
            self.assertIsNone(result["verify"][tid]["hint"])
        verify_paths = [e["path"] for e in result["verify"]["T1"]["paths"]]
        self.assertEqual(verify_paths, ["bin/tool.py", "tests/test_tool.py"])
        self.assertEqual(result["verify"]["T1"]["executables"],
                         [{"word": "python3", "state": "exists"}])

    def test_case2_a_verify_naming_an_absent_script_is_verify_missing_path(self):
        tasks = self.write_kit(_block("T1", "Do it.", "python3 bin/missing.py --check"))
        result = self.analyze(tasks)
        # D3's fourth amendment: a verify-missing-path warns (exit 0) and fails only under strict.
        self.assertEqual(result["exit"], 0)
        self.assertEqual(self.analyze(tasks, strict=True)["exit"], 3)
        self.assertEqual(self.kinds(result), ["verify-missing-path"])
        self.assertIn("bin/missing.py", result["findings"][0]["detail"])
        self.assertEqual(result["verify"]["T1"]["paths"],
                         [{"path": "bin/missing.py", "state": "missing", "by": None}])

    def test_a_first_word_path_is_checked_as_a_path(self):
        tasks = self.write_kit(_block("T1", "Do it.", "./scripts/check.sh --all"))
        result = self.analyze(tasks)
        self.assertEqual(self.kinds(result), ["verify-missing-path"])
        self.touch("scripts/check.sh")
        self.assertEqual(self.analyze(tasks)["exit"], 0)

    def test_case3_a_first_word_off_path_is_verify_missing_executable(self):
        tasks = self.write_kit(_block("T1", "Do it.", "no-such-binary-xyz --flag && true"))
        result = self.analyze(tasks)
        # D3's seventh amendment: a missing executable warns (exit 0) and fails only under strict.
        self.assertEqual(result["exit"], 0)
        self.assertEqual(self.analyze(tasks, strict=True)["exit"], 3)
        self.assertEqual(self.kinds(result), ["verify-missing-executable"])
        self.assertIn("no-such-binary-xyz", result["findings"][0]["detail"])
        self.assertEqual(result["verify"]["T1"]["executables"],
                         [{"word": "no-such-binary-xyz", "state": "missing"}])

    def test_case6_a_brief_path_is_advice_unless_strict(self):
        tasks = self.write_kit(_block("T1", "Update `docs/nowhere.md` to match.", "true"))
        result = self.analyze(tasks)
        self.assertEqual(result["exit"], 0)
        self.assertEqual(self.kinds(result), ["brief-missing-path"])
        self.assertIn("docs/nowhere.md", result["findings"][0]["detail"])
        strict = self.analyze(tasks, strict=True)
        self.assertEqual(strict["exit"], 3)
        self.assertIs(strict["strict"], True)

    def test_case10_mutation_deleting_the_fixture_file_flips_exit_0_to_3(self):
        tasks = self.sound_kit()
        self.assertEqual(self.analyze(tasks)["exit"], 0)
        (self.root / "bin" / "tool.py").unlink()
        result = self.analyze(tasks)
        # D3's fourth amendment: a verify-missing-path warns (exit 0) and fails only under strict.
        self.assertEqual(result["exit"], 0)
        self.assertEqual(self.analyze(tasks, strict=True)["exit"], 3)
        self.assertIn("verify-missing-path", self.kinds(result, "T1"))
        missing = [f for f in result["findings"] if f["kind"] == "verify-missing-path"]
        self.assertTrue(all("bin/tool.py" in f["detail"] for f in missing))

    def test_finding_kinds_and_path_states_are_exactly_the_planned_ones(self):
        self.assertEqual(kc.ANALYZE_FINDINGS, ("verify-unparseable", "verify-missing-executable",
                                               "verify-missing-path", "brief-missing-path"))
        self.assertEqual(kc.PATH_STATES, ("exists", "created-by", "missing"))


class DialectTests(_KitFixture):
    def test_case4_a_dialect_the_hook_reads_is_unparseable_with_the_hint(self):
        for dialect in ("bold-colon-bare", "bold-dot-bare", "dash-line"):
            with self.subTest(dialect=dialect):
                tasks = self.write_kit(_block("T1", "Do it.", "true", dialect=dialect))
                self.assertIsNone(tasks[0]["verify"])  # the drivers would run nothing
                result = self.analyze(tasks)
                self.assertEqual(result["exit"], 3)
                self.assertEqual(self.kinds(result), ["verify-unparseable"])
                self.assertFalse(result["verify"]["T1"]["parseable"])
                self.assertEqual(result["verify"]["T1"]["hint"], HINT)
                self.assertIn(HINT, result["findings"][0]["detail"])

    def test_no_verify_at_all_is_unparseable_without_the_hint(self):
        tasks = self.write_kit(_block("T1", "Do it.", "", dialect="none"))
        result = self.analyze(tasks)
        self.assertEqual(self.kinds(result), ["verify-unparseable"])
        self.assertIsNone(result["verify"]["T1"]["hint"])
        self.assertNotIn(HINT, result["findings"][0]["detail"])

    def test_a_plain_verify_colon_line_is_unparseable_without_the_hint(self):
        # PLAN R4 as corrected during T4: no parser reads a plain `Verify:` line + bare fence,
        # so D3's hint (fired only when `kit_verify_hook._task_verify_cmd` parses the block)
        # does not fire. sdd-docs-refresh is this case on every task.
        tasks = self.write_kit(_block("T1", "Do it.", "true", dialect="plain-colon-bare"))
        result = self.analyze(tasks)
        self.assertEqual(result["exit"], 3)
        self.assertEqual(self.kinds(result), ["verify-unparseable"])
        self.assertIsNone(result["verify"]["T1"]["hint"])
        self.assertNotIn(HINT, result["findings"][0]["detail"])


class CreatedByTests(_KitFixture):
    def test_case5_a_verify_path_an_upstream_brief_creates_is_created_by_that_task(self):
        tasks = self.write_kit(
            _block("T1", "Add new `tests/test_new.py` covering the parser.", "true"),
            _block("T2", "Run the suite.",
                   "python3 -m unittest discover -s tests -p 'test_new.py' -q", depends=["T1"]),
        )
        result = self.analyze(tasks)
        self.assertEqual(result["exit"], 0)
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["verify"]["T2"]["paths"],
                         [{"path": "tests/test_new.py", "state": "created-by", "by": "T1"}])

    def test_upstream_is_transitive(self):
        tasks = self.write_kit(
            _block("T1", "Write new `lib/core.py`.", "true"),
            _block("T2", "Wire it.", "true", depends=["T1"]),
            _block("T3", "Check it.", "python3 lib/core.py", depends=["T2"]),
        )
        result = self.analyze(tasks)
        self.assertEqual(result["exit"], 0)
        self.assertEqual(result["verify"]["T3"]["paths"][0]["by"], "T1")

    def test_a_downstream_or_unrelated_claim_does_not_count(self):
        tasks = self.write_kit(
            _block("T1", "Do it.", "python3 lib/later.py"),
            _block("T2", "Create `lib/later.py`.", "true", depends=["T1"]),
            _block("T3", "Create `lib/other.py`.", "true"),
            _block("T4", "Check.", "python3 lib/other.py", depends=["T1"]),
        )
        result = self.analyze(tasks)
        # D3's fourth amendment: a verify-missing-path warns (exit 0) and fails only under strict.
        self.assertEqual(result["exit"], 0)
        self.assertEqual(self.analyze(tasks, strict=True)["exit"], 3)
        self.assertEqual(result["verify"]["T1"]["paths"][0]["state"], "missing")
        self.assertEqual(result["verify"]["T4"]["paths"][0]["state"], "missing")

    def test_case9_a_task_verifying_the_file_its_own_brief_creates_is_created_by_itself(self):
        tasks = self.write_kit(
            _block("T1", "Write a new `tests/test_self.py` for the helper.",
                   "python3 -m unittest discover -s tests -p 'test_self.py' -q"),
        )
        result = self.analyze(tasks)
        self.assertEqual(result["exit"], 0)
        self.assertEqual(result["verify"]["T1"]["paths"],
                         [{"path": "tests/test_self.py", "state": "created-by", "by": "T1"}])
        self.assertEqual(result["paths"]["T1"],
                         [{"path": "tests/test_self.py", "state": "created-by", "by": "T1"}])

    def test_the_creation_word_must_be_a_whole_word_within_80_characters(self):
        far = "x" * 45
        tasks = self.write_kit(
            _block("T1", f"Renewed `docs/a.md`; new {far} `docs/b.md`; CREATES `docs/c.md`.",
                   "true"),
        )
        result = self.analyze(tasks)
        states = {e["path"]: e["state"] for e in result["paths"]["T1"]}
        # Third amendment, rule 5: the window is 80 characters, so `new` 45+ characters before
        # docs/b.md reaches it; the boundary itself is pinned by the 80-character test below.
        self.assertEqual(states, {"docs/a.md": "missing", "docs/b.md": "created-by",
                                  "docs/c.md": "created-by"})

    def test_the_creation_window_is_80_characters_and_reads_every_listed_form(self):
        # Third amendment, rule 5: the word must END within 80 characters before the path.
        near, far = "x" * 70, "x" * 85
        tasks = self.write_kit(_block(
            "T1", f"Implemented {near} `docs/near.md`. Built {far} `docs/far.md`. Splitting "
                  "`docs/s.md`; written `docs/w.md`; made `docs/m.md`; Scaffolds `docs/f.md`.",
            "true"))
        states = {e["path"]: e["state"] for e in self.analyze(tasks)["paths"]["T1"]}
        self.assertEqual(states, {"docs/near.md": "created-by", "docs/far.md": "missing",
                                  "docs/s.md": "created-by", "docs/w.md": "created-by",
                                  "docs/m.md": "created-by", "docs/f.md": "created-by"})

    def test_a_dot_slash_spelling_is_the_same_path_either_way(self):
        for brief, verify in (("Create `./spike/run.py`.", "python3 spike/run.py"),
                              ("Create `spike/run.py`.", "python3 ./spike/run.py")):
            with self.subTest(brief=brief, verify=verify):
                tasks = self.write_kit(_block("T1", brief, verify))
                self.assertEqual(self.analyze(tasks)["findings"], [])
        tasks = self.write_kit(_block("T1", "Create `a/./spike/run.py`.", "python3 spike/run.py"))
        self.assertEqual(self.kinds(self.analyze(tasks)), ["verify-missing-path"])

    def test_a_longer_path_containing_the_name_is_not_the_same_path(self):
        tasks = self.write_kit(
            _block("T1", "Add new `bin/x.py.bak` and new `old/bin/x.py`.", "true"),
            _block("T2", "Check.", "python3 bin/x.py", depends=["T1"]),
        )
        result = self.analyze(tasks)
        self.assertEqual(result["verify"]["T2"]["paths"][0]["state"], "missing")


class BriefPathTests(unittest.TestCase):
    def test_the_d3_span_rules(self):
        text = (
            "### T1 — t\n**Brief.** Touch `bin/a.py`, `notes.md`, `docs/b.md:42`, `c/d.txt.`, "
            "`e/f.json:`, `-flag/x`, `$HOME/x`, `~/x/y`, `<slug>/x.md`, `{a}/b`, "
            "`https://example.invalid/x`, `src/*.py`, `a?/b`, `a[0]/b`, `f(x)/y`, `a::b/c`, "
            "`tests/t.py::Case`, `a b/c.md`, `plain`, ``dbl/tick.md``, `x.yaml`, `y.sh`.\n"
            "```\n`fenced/not.md`\n```\n"
            "**Verify.**\n```bash\ntrue\n```\n`after/verify.md`\n"
        )
        self.assertEqual(kc.brief_paths(text), [
            "bin/a.py", "notes.md", "docs/b.md", "c/d.txt", "e/f.json", "x.yaml", "y.sh",
        ])

    def test_no_verify_marker_means_the_whole_block(self):
        self.assertEqual(kc.brief_paths("**Brief.** See `a/b.md`.\nVerify:\n```\nx\n```\n"),
                         ["a/b.md"])


class TokenizerTests(_KitFixture):
    def test_case7_heredoc_bodies_and_substitutions_are_not_tokenized(self):
        verify = (
            "python3 - <<'PY'\nimport fake.path\nopen('fake/path.py')\nPY\n"
            "cat <<EOF\nnope/one.py\nEOF\n"
            "cat <<-\"END\"\n\tnope/two.py\n\tEND\n"
            'cd "$(git rev-parse --show-toplevel)" && test -n "$(cat fake/other.py)" '
            "&& echo `cat fake/three.py`"
        )
        tasks = self.write_kit(_block("T1", "Do it.", verify))
        result = self.analyze(tasks)
        self.assertEqual(result["findings"], [], result["findings"])
        self.assertEqual(result["exit"], 0)
        words = [e["word"] for e in result["verify"]["T1"]["executables"]]
        self.assertEqual(words, ["python3", "cat"])

    def test_a_heredoc_terminator_must_be_exact(self):
        verify = "cat <<EOF\n EOF\nbin/still-body.py\nEOF\npython3 bin/after.py"
        tasks = self.write_kit(_block("T1", "Do it.", verify))
        result = self.analyze(tasks)
        self.assertEqual([e["path"] for e in result["verify"]["T1"]["paths"]], ["bin/after.py"])

    def test_case8_module_and_discover_forms_map_to_test_files(self):
        self.touch("tests/test_x.py")
        for verify in ("python3 -m unittest tests.test_x",
                       "python3 -m unittest discover -s tests -p 'test_x.py' -q",
                       "python3 -m unittest discover -p test_x.py"):
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                result = self.analyze(tasks)
                self.assertEqual(result["exit"], 0)
                self.assertEqual(result["verify"]["T1"]["paths"],
                                 [{"path": "tests/test_x.py", "state": "exists", "by": None}])
        (self.root / "tests" / "test_x.py").unlink()
        for verify in ("python3 -m unittest tests.test_x",
                       "python3 -m unittest discover -s tests -p 'test_x.py' -q"):
            with self.subTest(verify=verify, absent=True):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                result = self.analyze(tasks)
                self.assertEqual(self.kinds(result), ["verify-missing-path"])
                self.assertIn("tests/test_x.py", result["findings"][0]["detail"])

    def test_dash_m_names_python_modules_only(self):
        self.touch("tests/test_x.py", "data/keep.txt", "data.json")
        sound = (
            "python3 -m json.tool data.json",               # stdlib module; its argument is a file
            "git commit -m tests.update",                   # a message, not a module
            "python3 -m unittest -v tests.test_x.Case.test_y",  # module, then class and method
            "python3 -m unittest -k tests.not_a_module tests.test_x",  # `-k` takes a pattern
        )
        for verify in sound:
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                result = self.analyze(tasks)
                self.assertEqual(result["findings"], [])
        tasks = self.write_kit(_block("T1", "Do it.", "python3 -m tests.run_all"))
        result = self.analyze(tasks)
        self.assertEqual(self.kinds(result), ["verify-missing-path"])
        self.assertIn("tests/run_all.py", result["findings"][0]["detail"])
        tasks = self.write_kit(_block("T1", "Do it.", "uv run python -m unittest tests.test_gone"))
        self.assertIn("tests/test_gone.py", self.analyze(tasks)["findings"][0]["detail"])

    def test_discover_honors_its_start_directory(self):
        self.touch("suite/test_y.py")
        tasks = self.write_kit(_block(
            "T1", "Do it.", "python3 -m unittest discover -p 'test_y.py' -s suite"))
        result = self.analyze(tasks)
        self.assertEqual(result["exit"], 0)
        self.assertEqual(result["verify"]["T1"]["paths"][0]["path"], "suite/test_y.py")

    def test_case11a_quotes_and_test_operands_per_the_d3_amendment(self):
        verifies = (
            r"git log -1 --format=%s | grep -qE '^(feat|fix|docs)\(x\): y$'",
            'test "$(git branch --show-current)" = feat/some-branch',
            '[ "$(git branch --show-current)" = feat/other-branch ]',
            "! test -f gone/away.py && if [ -d also/gone ]; then true; fi",
            "grep -q 'a && no-such-binary-xyz' README.md",
            'grep -q "b || no-such-binary-xyz; c | d" README.md',
        )
        self.touch("README.md")
        for verify in verifies:
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                result = self.analyze(tasks)
                self.assertEqual(result["findings"], [])
                self.assertEqual(result["exit"], 0)
        tasks = self.write_kit(_block("T1", "Do it.", "echo foo | no-such-binary-xyz"))
        result = self.analyze(tasks)
        # D3's seventh amendment: a missing executable warns (exit 0) and fails only under strict.
        self.assertEqual(result["exit"], 0)
        self.assertEqual(self.analyze(tasks, strict=True)["exit"], 3)
        self.assertEqual(self.kinds(result), ["verify-missing-executable"])
        self.assertIn("no-such-binary-xyz", result["findings"][0]["detail"])

    def test_test_operands_are_exempt_but_other_builtins_arguments_are_not(self):
        tasks = self.write_kit(_block("T1", "Do it.", "cd nowhere/dir && echo ok"))
        result = self.analyze(tasks)
        self.assertEqual(self.kinds(result), ["verify-missing-path"])

    def test_output_redirection_assignments_and_dynamic_tokens(self):
        verify = ("FOO=bar/baz python3 -c 'print(1)' > out/file.txt 2>&1\n"
                  "python3 -c 'x' >> logs/run.log\n"
                  "ls $TMPDIR/x ~/y src/$NAME/z 'tests/*.py' https://example.invalid/a")
        tasks = self.write_kit(_block("T1", "Do it.", verify))
        result = self.analyze(tasks)
        self.assertEqual(result["findings"], [])
        self.assertEqual([e["word"] for e in result["verify"]["T1"]["executables"]],
                         ["python3", "ls"])

    def test_comments_continuations_and_escaped_operators(self):
        verify = ("# a comment naming bin/ghost.py, and don't\n"
                  "python3 -c 'print(1)' \\\n  --flag && find . -name x -exec true {} \\; -print\n"
                  "echo a#b")
        tasks = self.write_kit(_block("T1", "Do it.", verify))
        result = self.analyze(tasks)
        self.assertEqual(result["findings"], [], result["findings"])

    def test_case11b_an_exploration_shaped_kit_passes_with_no_finding(self):
        tasks = self.write_kit(
            _block("S1", "Spike: write new `spike/notes.md` with what you find.", "true"),
            _block("S2", "Add a new `spike/probe.py` and run it once.", 'python3 -c "print(1)"',
                   depends=["S1"]),
            _block("S3", "Create `spike/summary.md` from `spike/notes.md`.", 'test -n "$(ls)"',
                   depends=["S2"]),
            # spike/x.json is named by no brief: the code after `-c` is a quoted value (D3's
            # second amendment), never a path to check.
            _block("S4", "Read what the probe wrote.",
                   "python3 -c \"open('spike/x.json').read()\"", depends=["S3"]),
        )
        result = self.analyze(tasks)
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["exit"], 0)
        self.assertEqual(kc.analyze_kit(self.kit, tasks, strict=True)["exit"], 0)

    def test_case11c_the_second_d3_amendment_lets_ordinary_verifies_pass(self):
        self.touch("README.md")
        sound = (
            "grep -q '/dashboard/' README.md",            # (2) a quoted argument is a value
            "git show HEAD:docs/x.md",                    # (4) `:` before `/`: a git object
            "env MODE=a/b true",                          # (3) `=` before `/`: a value
            "[[ -f spike/a.md ]] && : && true",           # (1) `[[`/`:` builtins, `[[` operands
            "source /dev/null",                           # (1) `source` is a builtin
            "mkdir -p build && echo hi > build/r.txt && cat build/r.txt",  # (5) written earlier
        )
        for verify in sound:
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                result = self.analyze(tasks)
                self.assertEqual(result["findings"], [], result["findings"])
                self.assertEqual(result["exit"], 0)
        # Negative control: an unquoted script path still fails. The old second control,
        # `cat docs/nowhere.md`, is advisory after the third amendment (rule 1): see (11d).
        for verify, path in (("cat docs/nowhere.md", "docs/nowhere.md"),
                             ("python3 bin/missing.py", "bin/missing.py")):
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                result = self.analyze(tasks)
                if verify.startswith("cat "):
                    self.assertEqual((result["exit"], result["findings"]), (0, []))
                    self.assertEqual(result["verify"]["T1"]["paths"][0]["state"], "missing")
                    continue
                self.assertEqual(self.kinds(result), ["verify-missing-path"])
                self.assertIn(path, result["findings"][0]["detail"])
                # D3's fourth amendment: a verify-missing-path warns (exit 0) and fails only under strict.
                self.assertEqual(result["exit"], 0)
                self.assertEqual(self.analyze(tasks, strict=True)["exit"], 3)

    def test_case11d_the_third_d3_amendment_blocks_only_on_what_cannot_start(self):
        self.touch("README.md", "x.py", "sub/run.sh")
        sound = (
            "git diff --stat origin/main",
            "sed -i s/a/b/ README.md",
            "python3 x.py --out build/report.json",
            "rm -rf /tmp/zz-nothing",
            "T=$(mktemp -d); trap 'rm -rf \"$T\"' EXIT; true",
            'case "$X" in\n  a) no-such-binary-xyz nope/x.py ;;\n  *) ./bin/nope.sh ;;\nesac',
            "check_it() {\n  true\n}\ncheck_it && function other { true; }\nother",
            "[[ -f README.md && -d /tmp ]]",
            "cd sub && ./run.sh",
        )
        for verify in sound:
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                result = self.analyze(tasks)
                self.assertEqual(result["findings"], [], result["findings"])
                self.assertEqual(result["exit"], 0)
        # A data argument is resolved and recorded, but advisory: a summary line, no finding.
        tasks = self.write_kit(_block("T1", "Do it.", "cat docs/nowhere.md"))
        result = self.analyze(tasks)
        self.assertEqual((result["exit"], result["findings"]), (0, []))
        self.assertEqual(result["verify"]["T1"]["paths"],
                         [{"path": "docs/nowhere.md", "state": "missing", "by": None}])
        self.assertIn("analyze: T1 path docs/nowhere.md missing",
                      kc.render_analyze(result).splitlines())
        # The commonest spike shape: "Implement" the script the verify runs.
        tasks = self.write_kit(_block("T1", "Implement `spike/run.py` that prints hello.",
                                      "python3 spike/run.py"))
        result = self.analyze(tasks)
        self.assertEqual((result["exit"], result["findings"]), (0, []))
        self.assertEqual(result["verify"]["T1"]["paths"],
                         [{"path": "spike/run.py", "state": "created-by", "by": "T1"}])
        (self.root / "tests").mkdir()
        blocked = (
            ("./bin/nope.sh", "verify-missing-path", "bin/nope.sh"),
            ("cd /path/to/nowhere && true", "verify-missing-path", "/path/to/nowhere"),
            ("python3 zz.py", "verify-missing-path", "zz.py"),
            ("python3 -m unittest tests.test_nope", "verify-missing-path", "tests/test_nope.py"),
            # the verify's own words never claim to create a path
            ("git add nothere/x.py && python3 nothere/x.py", "verify-missing-path",
             "nothere/x.py"),
        )
        for verify, kind, path in blocked:
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                result = self.analyze(tasks)
                # D3's fourth amendment: a verify-missing-path warns (exit 0) and fails only under strict.
                self.assertEqual(result["exit"], 0)
                self.assertEqual(self.analyze(tasks, strict=True)["exit"], 3)
                self.assertEqual(self.kinds(result), [kind], result["findings"])
                self.assertIn(path, result["findings"][0]["detail"])

    def _stub_path(self, *names):
        """A PATH with stub executables first, so the fixture does not depend on the host's
        tools. analyze only looks them up (`shutil.which`); nothing runs them."""
        stub = self.root / "stub-bin"
        stub.mkdir(exist_ok=True)
        for name in names:
            (stub / name).write_text("#!/bin/sh\nexit 99\n")
            (stub / name).chmod(0o755)
        return mock.patch.dict(os.environ, {"PATH": str(stub) + os.pathsep + os.environ["PATH"]})

    def test_case11e_the_fourth_d3_amendment_blocks_only_on_sure_things(self):
        self.touch("README.md", "x.c")
        self.assertIsNone(shutil.which("myfunc"))
        quiet = (
            "exec 2>&1; true",
            "exec 3<README.md",
            "2>/dev/null true",
            "2>/dev/null",
            "echo hi 4>>log.txt && exec 5<&0",
            "arr=(a b c); echo ${arr[@]}",
        )
        # D3's fifth amendment: a verify using `source`/`.`/`eval` or an install step is not a
        # simple verify, so its unknown command word is a printed WARNING (exit 0; 3 strict)
        # rather than no finding at all, which was the fourth amendment's narrower scope.
        warned = ("source /dev/null && myfunc", ". /dev/null; myfunc", "eval true; myfunc",
                  "pip install foo && foo")
        with self._stub_path("pip", "cc"):
            for verify in quiet:
                with self.subTest(verify=verify):
                    tasks = self.write_kit(_block("T1", "Do it.", verify))
                    result = self.analyze(tasks)
                    self.assertEqual((result["exit"], result["findings"]), (0, []))
            for verify in warned:
                with self.subTest(verify=verify):
                    tasks = self.write_kit(_block("T1", "Do it.", verify))
                    result = self.analyze(tasks)
                    self.assertEqual(result["exit"], 0)
                    self.assertEqual(self.kinds(result), ["verify-missing-executable"])
                    self.assertEqual(self.analyze(tasks, strict=True)["exit"], 3)
            # Path findings are warnings now: printed, exit 0, exit 3 only under strict.
            for brief, verify, path in (
                    ("Do it.", "cc -o build/app x.c && build/app", "build/app"),
                    ("Do it.", "cd nodir 2>/dev/null || true", "nodir"),
                    ("Prototype `spike/run.py` that prints the dataset size.",
                     "python3 spike/run.py", "spike/run.py")):
                with self.subTest(verify=verify):
                    tasks = self.write_kit(_block("T1", brief, verify))
                    result = self.analyze(tasks)
                    self.assertEqual(result["exit"], 0)
                    self.assertNotIn("verify-missing-executable", self.kinds(result))
                    self.assertIn("verify-missing-path", self.kinds(result))
                    self.assertTrue(any(path in f["detail"] for f in result["findings"]))
                    self.assertEqual(self.analyze(tasks, strict=True)["exit"], 3)
                    out = io.StringIO()
                    self.assertEqual(kc.exit_if_unsound_kit(self.kit, tasks, out=out)["exit"], 0)
                    self.assertIn("verify-missing-path", out.getvalue())
        # An unknown bare command word in a simple verify: still found, and since the
        # seventh amendment a warning (exit 0; exit 3 only under strict).
        for verify in ("no-such-binary-xyz", "x | no-such-binary-xyz"):
            with self.subTest(verify=verify), self._stub_path("pip"):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                result = self.analyze(tasks)
                # D3's seventh amendment: a missing executable warns (exit 0) and fails only under strict.
                self.assertEqual(result["exit"], 0)
                self.assertEqual(self.analyze(tasks, strict=True)["exit"], 3)
                self.assertIn("verify-missing-executable", self.kinds(result))
        # D3's fifth amendment: a `source` or an install step ANYWHERE in the fence -- after the
        # unknown word too -- makes the verify not simple, so the finding warns (exit 0; 3 strict).
        for verify in ("myfunc && source /dev/null", "foo && pip install foo"):
            with self.subTest(verify=verify), self._stub_path("pip"):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                result = self.analyze(tasks)
                self.assertEqual(result["exit"], 0)
                self.assertIn("verify-missing-executable", self.kinds(result))
                self.assertEqual(self.analyze(tasks, strict=True)["exit"], 3)

    def _empty_path(self):
        """A PATH holding nothing, so every non-builtin command word is unknown on any host."""
        empty = self.root / "empty-bin"
        empty.mkdir(exist_ok=True)
        return mock.patch.dict(os.environ, {"PATH": str(empty)})

    def test_case11f_the_fifth_d3_amendment_blocks_only_on_simple_verifies(self):
        warned = (
            "main()\n{\n  helper\n}\nhelper() { echo hi; }\nmain",
            "if true; then g() { :; }; fi; g",
            "foo ( ) { echo; }\nfoo",
            "f() { case $1 in a) return 0;; *) return 1;; esac; }\nf a",
            "x='a;b'; echo ${x%%;*}",
            "x=$(cat <<EOF\n1) a\n2) b\nEOF\n)\necho \"$x\"",
            'export PATH="$PWD/bin:$PATH"\nmytool --help',
            "npm i -g typescript && tsc --version",
        )
        with self._empty_path():
            for verify in warned:
                with self.subTest(verify=verify):
                    tasks = self.write_kit(_block("T1", "Do it.", verify))
                    result = self.analyze(tasks)
                    self.assertIn("verify-missing-executable", self.kinds(result), result)
                    self.assertEqual(result["exit"], 0)
                    self.assertEqual(self.analyze(tasks, strict=True)["exit"], 3)
                    out = io.StringIO()
                    self.assertEqual(kc.exit_if_unsound_kit(self.kit, tasks, out=out)["exit"], 0)
                    self.assertIn("verify-missing-executable", out.getvalue())
        # A simple verify still refuses.
        for verify in ("no-such-binary-xyz", "true && no-such-binary-xyz",
                       "x | no-such-binary-xyz", "cd sub\nno-such-binary-xyz"):
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                result = self.analyze(tasks)
                # D3's seventh amendment: a missing executable warns (exit 0) and fails only under strict.
                self.assertEqual(result["exit"], 0)
                self.assertEqual(self.analyze(tasks, strict=True)["exit"], 3)
                self.assertIn("verify-missing-executable", self.kinds(result))
                self.assertNotIn("a warning, not a refusal", result["findings"][0]["detail"])
        # A command word with `$` anywhere is dynamic: no finding at all.
        for verify in ("V=3; python${V} -c 'print(1)'", "python$(echo 3) -c 'print(1)'"):
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                self.assertEqual(self.analyze(tasks)["findings"], [])
        # A feature only counts where the reader sees it: quoted or in a heredoc body it does
        # not, so these simple verifies still refuse.
        for verify in ("echo 'case function ${x} PATH=a eval'; no-such-binary-xyz",
                       "cat <<EOF\ncase x in\nf() {\nEOF\nno-such-binary-xyz",
                       "find . -name x && no-such-binary-xyz"):
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                # D3's seventh amendment: a missing executable warns (exit 0) and fails only under strict. The simple
                # verify's finding keeps its plain detail (no feature named).
                result = self.analyze(tasks)
                self.assertEqual((result["exit"], self.analyze(tasks, strict=True)["exit"]), (0, 3))
                self.assertNotIn("a warning, not a refusal", result["findings"][0]["detail"])

    def test_case11g_the_sixth_d3_amendment(self):
        clean = (
            'exec {fd}>"$TMPDIR/x"\ntrue',
            "exec {fd}>&-",
            "exec {a}>x {b}>y; true",
            "cat {fd}<README.md",
            '[[ -n "$HOME" &&\n-d . ]] && true',
            "(( 1 +\n2 )) && true",
            "for ((i=0;\ni<2; i++)); do :; done",
        )
        self.touch("README.md")
        for verify in clean:
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                result = self.analyze(tasks)
                self.assertEqual((result["exit"], result["findings"]), (0, []), result)
        # Tool guards: a tool probe makes the verify non-simple; the left operand of `||` is
        # expected to fail. Both give a WARNING (exit 0; exit 3 under strict).
        for verify in ("command -v nosuchzz >/dev/null && nosuchzz --version",
                       "type nosuchzz >/dev/null && nosuchzz", "hash nosuchzz && nosuchzz",
                       "which nosuchzz && nosuchzz",
                       "nosuchzz 2>/dev/null || true", "nosuchzz || exit 1",
                       "nosuchzz | cat || true", "nosuchzz && true || true"):
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                result = self.analyze(tasks)
                self.assertEqual(self.kinds(result), ["verify-missing-executable"])
                self.assertEqual(result["exit"], 0)
                self.assertEqual(self.analyze(tasks, strict=True)["exit"], 3)
        # Only the LEFT operand of `||` warns; the right one, and a plain one, still refuse.
        for verify in ("true || nosuchzz", "nosuchzz || true; nosuchzz",
                       "nosuchzz; true || true", "command -p true; nosuchzz"):
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                # D3's seventh amendment: a missing executable warns (exit 0) and fails only under strict. The
                # unguarded finding keeps its plain detail.
                result = self.analyze(tasks)
                self.assertEqual((result["exit"], self.analyze(tasks, strict=True)["exit"]), (0, 3))
                self.assertNotIn("a warning, not a refusal", result["findings"][-1]["detail"])
        # An empty or blank `**Verify.**` fence: nothing to run.
        for verify in ("", "   \n\t"):
            with self.subTest(verify=repr(verify)):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                self.assertEqual(tasks[0]["verify"], "")
                result = self.analyze(tasks)
                self.assertEqual(self.kinds(result), ["verify-unparseable"])
                self.assertIn("empty", result["findings"][0]["detail"])
                self.assertFalse(result["verify"]["T1"]["parseable"])
                self.assertEqual(result["exit"], 3)
        # The driver gate checks only what will run: a refusing finding on a `done` task is
        # printed but does not stop the run; on a pending or blocked task it does.
        for status, exits in (("done", False), ("pending", False), ("blocked", False)):
            # D3's seventh amendment: a missing executable warns (exit 0) and fails only under strict.
            # So the gate never exits on one, whatever the task's status.
            with self.subTest(status=status):
                tasks = self.write_kit(_block("T1", "Do it.", "no-such-binary-xyz",
                                              status=status),
                                       _block("T2", "Next.", "true", depends=["T1"]))
                out = io.StringIO()
                if exits:
                    with self.assertRaises(SystemExit) as caught:
                        kc.exit_if_unsound_kit(self.kit, tasks, out=out)
                    self.assertEqual(caught.exception.code, 3)
                else:
                    result = kc.exit_if_unsound_kit(self.kit, tasks, out=out)
                    self.assertEqual(self.kinds(result), ["verify-missing-executable"])
                    self.assertEqual(result["exit"], 0)
                self.assertIn("verify-missing-executable", out.getvalue())
        tasks = self.write_kit(_block("T1", "Do it.", "", status="done"))
        self.assertIsInstance(kc.exit_if_unsound_kit(self.kit, tasks, out=io.StringIO()), dict)
        # A simple verify's missing executable: kept, and since the seventh amendment a warning.
        tasks = self.write_kit(_block("T1", "Do it.", "no-such-binary-xyz"))
        # D3's seventh amendment: a missing executable warns (exit 0) and fails only under strict.
        self.assertEqual((self.analyze(tasks)["exit"], self.analyze(tasks, strict=True)["exit"]),
                         (0, 3))

    def test_round4_shapes_bash_would_run_do_not_refuse(self):
        # The stop rule's test (D3/D5 sixth amendment, (5)): a simple verify bash would run
        # must not refuse. Each of these runs in bash (given its own setup) and once refused.
        for verify in ("cat <<EOF\nline \\\nEOF\nEOF\ntrue",  # body continuation, unquoted
                       'cat <<E"O"F\nx\nEOF\ntrue'):          # a partly quoted delimiter
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                self.assertEqual(self.analyze(tasks)["exit"], 0, self.analyze(tasks))
        with self._empty_path():
            for verify in (
                    "shopt -s expand_aliases; alias f='echo'\nf",   # an alias, then expanded
                    "enable -f ./x.so f\nf",                        # a loaded builtin
                    "printf -v PATH '%s' bin\nnosuchzz", "read PATH <<< bin\nnosuchzz",
                    "VAR=PATH; export $VAR=bin\nnosuchzz",
                    "./install.sh\nnosuchzz", "sh install.sh\nnosuchzz",
                    "bash scripts/bootstrap.sh\nnosuchzz"):
                with self.subTest(verify=verify):
                    tasks = self.write_kit(_block("T1", "Do it.", verify))
                    self.assertEqual(self.analyze(tasks)["exit"], 0, self.analyze(tasks))
        # A quoted delimiter takes its body literally: `line \` does not join, so the first
        # `EOF` ends it and the second is a command.
        tasks = self.write_kit(_block("T1", "Do it.", "cat <<'EOF'\nline \\\nEOF\nEOF\ntrue"))
        self.assertEqual(self.kinds(self.analyze(tasks)), ["verify-missing-executable"])

    def test_sixth_amendment_item6_probes_in_substitutions_and_guarded_groups(self):
        # (6): a tool probe inside a command substitution is a probe; every command inside a
        # group that is the left operand of `||` is a left operand. Each of these WARNS.
        warned = (
            'x="$(command -v nosuchzz)"; test -n "$x" && nosuchzz',
            "x=`command -v nosuchzz`; test -n \"$x\" && nosuchzz",
            'x="$(type -p nosuchzz)"; nosuchzz', 'x=$(hash nosuchzz 2>&1); nosuchzz',
            "x=`which nosuchzz`; nosuchzz",
            "{ nosuchzz; } || true", "( nosuchzz ) || true", "( nosuchzz; true ) || true",
            "if nosuchzz; then :; fi || true", "{ true; nosuchzz; } > /dev/null || true",
            "while nosuchzz; do :; done || true", "until nosuchzz; do :; done || true",
            "for i in a; do nosuchzz; done || true",
            "{ ( if nosuchzz; then :; fi ); } || exit 0",
            "if true; then\n  nosuchzz\nfi ||\n  true",
            "{ nosuchzz; } && true || true",
            "nosuchzz && { true; } || true",
        )
        for verify in warned:
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                result = self.analyze(tasks)
                self.assertEqual(self.kinds(result), ["verify-missing-executable"], result)
                self.assertEqual(result["exit"], 0)
                self.assertEqual(self.analyze(tasks, strict=True)["exit"], 3)
        # Still refusals: the right operand, a group not guarded, a guarded group followed by
        # the same word unguarded, and `command -p` (not a probe) inside a substitution.
        for verify in ("true || nosuchzz", "{ nosuchzz; }; true || true",
                       "{ nosuchzz; } || true; nosuchzz", "( nosuchzz ) && true",
                       'x="$(command -p true)"; nosuchzz', "if true; then nosuchzz; fi"):
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                result = self.analyze(tasks)
                # D3's seventh amendment: a missing executable warns (exit 0) and fails only under strict.
                self.assertEqual(result["exit"], 0, result)
                self.assertEqual(self.analyze(tasks, strict=True)["exit"], 3)
                self.assertIn("verify-missing-executable", self.kinds(result))
                self.assertTrue(any("a warning, not a refusal" not in f["detail"]
                                    for f in result["findings"]))  # unguarded: plain detail

    def test_case11h_the_seventh_d3_amendment_only_unparseable_blocks(self):
        for verify in ("no-such-binary-xyz", "true && no-such-binary-xyz",
                       '[ -n "$GITHUB_ACTIONS" ] && nosuchtool_q annotate; true',
                       "true; exit 0; nosuchtool_q"):
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                result = self.analyze(tasks)
                self.assertIn("verify-missing-executable", self.kinds(result))
                self.assertEqual(result["exit"], 0)
                self.assertEqual(self.analyze(tasks, strict=True)["exit"], 3)
        # extglob: `@(a|b)` and its kin are one word once the verify turns extglob on.
        for verify in ("shopt -s extglob\necho @(a|b); true",
                       "shopt -s extglob; ls +(x|y) ?(p|q) *(m|n) !(r|s) 2>/dev/null; true"):
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                self.assertEqual(self.analyze(tasks)["findings"], [])
        # An empty fence still refuses.
        tasks = self.write_kit(_block("T1", "Do it.", ""))
        self.assertEqual(self.analyze(tasks)["exit"], 3)
        # The gate: only a `verify-unparseable` on a pending or in-progress task exits 3.
        for status, exits in (("pending", True), ("in-progress", True), ("done", False),
                              ("blocked", False)):
            for dialect, verify in (("none", "true"), ("bold", "")):
                with self.subTest(status=status, dialect=dialect):
                    tasks = self.write_kit(_block("T1", "Do it.", verify, status=status,
                                                  dialect=dialect))
                    out = io.StringIO()
                    if exits:
                        with self.assertRaises(SystemExit) as caught:
                            kc.exit_if_unsound_kit(self.kit, tasks, out=out)
                        self.assertEqual(caught.exception.code, 3)
                    else:
                        self.assertIsInstance(kc.exit_if_unsound_kit(self.kit, tasks, out=out),
                                              dict)
                    self.assertIn("verify-unparseable", out.getvalue())

    def test_case11h_a_long_depends_chain_is_linear(self):
        import time
        blocks = [_block(f"T{i}", f"Create new `gen/f{i}.py` and read `gen/f{max(1, i - 1)}.py` "
                                  f"and `gen/zz{i}.md`.",
                         f"python3 gen/f{i}.py && test -f gen/f{max(1, i - 1)}.py",
                         depends=[f"T{i - 1}"] if i > 1 else ())
                  for i in range(1, 1001)]
        tasks = self.write_kit(*blocks)
        start = time.monotonic()
        result = self.analyze(tasks)
        self.assertLess(time.monotonic() - start, 10.0)
        # Exactness, unchanged by the speed-up: each script is created by its own task; the read
        # of the previous file resolves to the UPSTREAM creator, which D3 prefers over the task
        # itself; `zz` lies within 80 characters of "Create new" in the task's own brief.
        self.assertEqual(result["verify"]["T500"]["paths"][0],
                         {"path": "gen/f500.py", "state": "created-by", "by": "T500"})
        self.assertIn({"path": "gen/f499.py", "state": "created-by", "by": "T499"},
                      result["paths"]["T500"])
        self.assertIn({"path": "gen/zz500.md", "state": "created-by", "by": "T500"},
                      result["paths"]["T500"])
        self.assertEqual(result["findings"], [])

    def test_the_created_by_index_answers_exactly_as_the_scan(self):
        # The linear index must give the original scan's answer for every path: the first
        # upstream claimant in file order, else the task itself, else missing.
        import random
        rng = random.Random(7)
        words = ["Create", "new", "add", "Implement", "read", "see", "edit", "Prototype", "and",
                 "then", "x" * 50, "(", ")", ".", ",", ";", "`", "~", "$"]
        paths = ["a/b.py", "./a/b.py", "a/b", "c/d.md", "a/b.py.bak", "e/f~", "e/f", "g/h$"]
        for trial in range(60):
            n = rng.randint(1, 6)
            blocks = []
            for i in range(1, n + 1):
                text = " ".join(rng.choice(words + [f"`{rng.choice(paths)}`", rng.choice(paths)])
                                for _ in range(rng.randint(3, 14)))
                deps = sorted({f"T{rng.randint(1, n)}" for _ in range(rng.randint(0, 2))} -
                              {f"T{i}"})
                blocks.append(_block(f"T{i}", text, "true", depends=deps))
            tasks = self.write_kit(*blocks)
            result = self.analyze(tasks)
            blocks_text = kc._task_blocks((self.kit / "TASKS.md").read_text())
            depends_of = {t["id"]: t["depends"] for t in tasks}
            for t in tasks:
                seen, stack = set(), list(depends_of[t["id"]])
                while stack:  # the reference upstream: plain transitive closure
                    d = stack.pop()
                    if d in seen or d == t["id"] or d not in depends_of:
                        continue
                    seen.add(d)
                    stack.extend(depends_of[d])
                creators = {u["id"]: kc._claim_text(blocks_text[u["id"]]) for u in tasks
                            if u["id"] in seen}
                creators[t["id"]] = kc._claim_text(blocks_text[t["id"]])
                for path in paths:
                    with self.subTest(trial=trial, task=t["id"], path=path):
                        expected = kc.classify_path(path, self.root, t["id"], creators)
                        index = kc._Creators([u["id"] for u in tasks],
                                             {u["id"]: creators.get(u["id"], kc._claim_text(
                                                 blocks_text[u["id"]])) for u in tasks},
                                             depends_of)
                        self.assertEqual(kc.classify_path(path, self.root, t["id"], index),
                                         expected)
                for entry in result["paths"][t["id"]]:
                    self.assertEqual(entry, kc.classify_path(entry["path"], self.root, t["id"],
                                                             creators))
        # Claim texts built directly, so a bare path can be the very LAST token: the end of the
        # text is a boundary for both readings (a kit-built claim text always ends with the
        # acceptance, so the trials above never reach it).
        for trial in range(200):
            n = rng.randint(1, 5)
            claim_of = {}
            for i in range(1, n + 1):
                text = " ".join(rng.choice(words + [rng.choice(paths)])
                                for _ in range(rng.randint(1, 8)))
                if rng.random() < 0.6:
                    text += " " + rng.choice(paths)  # the path is the last thing in the text
                claim_of[f"T{i}"] = text
            depends_of = {f"T{i}": sorted({f"T{rng.randint(1, n)}" for _ in range(
                rng.randint(0, 2))} - {f"T{i}"}) for i in range(1, n + 1)}
            index = kc._Creators(list(claim_of), claim_of, depends_of)
            for tid in claim_of:
                seen, stack = set(), list(depends_of[tid])
                while stack:
                    d = stack.pop()
                    if d in seen or d == tid or d not in depends_of:
                        continue
                    seen.add(d)
                    stack.extend(depends_of[d])
                creators = {u: claim_of[u] for u in claim_of if u in seen}
                creators[tid] = claim_of[tid]
                for path in paths:
                    with self.subTest(direct=trial, task=tid, path=path, text=claim_of[tid]):
                        self.assertEqual(kc.classify_path(path, self.root, tid, index),
                                         kc.classify_path(path, self.root, tid, creators))

    def test_repeated_unmatched_openers_are_linear(self):
        # The last red-team pass's hang (linear time, D3's fourth and fifth amendments): one
        # long word full of `$` (`${` repeated, or backtick substitutions that become `$_`)
        # made a backtracking regex quadratic. Two more inputs of the same family ride along:
        # a long `shopt -sss…` and a brief span with many `:digits` suffixes.
        import time
        for verify in ("${" * 50000, ("'\"" + "`") * 100000,
                       "shopt -" + "s" * 200000, "shopt " + "-a " * 100000):
            with self.subTest(shape=verify[:8], size=len(verify)):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                start = time.monotonic()
                self.analyze(tasks)
                self.assertLess(time.monotonic() - start, 10.0)
        tasks = self.write_kit(_block("T1", "See `x/" + ":1" * 50000 + "`.", "true"))
        start = time.monotonic()
        self.analyze(tasks)
        self.assertLess(time.monotonic() - start, 10.0)

    def test_the_linear_helpers_answer_exactly_as_the_regexes_they_replace(self):
        # Same findings as before for every input small enough for the old code: each linear
        # helper is checked against the regex (or loop) it replaced, on random short inputs.
        import random
        import re
        rng = random.Random(9)
        dynamic = re.compile(r"[^=/\s]*\$[^=/\s]*\+?=")
        extglob = re.compile(r"\bshopt\s+(?:-\w+\s+)*-\w*s\w*\s+(?:[\w-]+\s+)*extglob\b")
        suffix = re.compile(r":\d+$")

        def old_strip(path):
            while True:
                stripped = suffix.sub("", path.rstrip(".,:;"))
                if stripped == path:
                    return path
                path = stripped

        alphabet = ["$", "{", "=", "/", " ", "\t", "+", "a", "_", "x", "-", "s", "\n", ";", ":",
                    "1", ".", ",", "shopt", "extglob", "-s", "-qs", "-u", "²", "٣"]
        for _ in range(20000):
            text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 12)))
            self.assertEqual(kc._is_dynamic_name_assignment(text), bool(dynamic.match(text)), text)
            self.assertEqual(kc._extglob_on(text), bool(extglob.search(text)), text)
            self.assertEqual(kc._strip_line_suffix(text), old_strip(text), text)

    def test_case11h_a_closed_stdout_exits_quietly(self):
        blocks = [_block(f"T{i}", f"See `docs/nowhere{i}.md` and `docs/also{i}.md`.", "true")
                  for i in range(1, 400)]
        self.write_kit(*blocks)
        env = dict(os.environ, HOME=str(self.root), POLYTROPOS_DATA_HOME=str(self.root / "data"))
        for argv in (["--json"], []):
            with self.subTest(argv=argv):
                proc = subprocess.Popen([sys.executable, str(KC_PATH), "analyze", "--kit",
                                         str(self.kit), *argv], stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, env=env, cwd=self.root)
                proc.stdout.read(10)
                proc.stdout.close()
                err = proc.stderr.read().decode()
                proc.stderr.close()
                code = proc.wait(timeout=60)
                self.assertNotIn("Traceback", err)
                self.assertNotIn("Exception ignored", err)
                self.assertEqual(code, 0)  # analyze's own exit: brief warnings only

    def test_case11f_nested_groups_and_many_hinted_tasks_are_linear(self):
        import time
        tasks = self.write_kit(_block("T1", "Do it.", "{ " * 100_000 + "echo x\n" +
                                      "echo y\n" * 100_000))
        start = time.monotonic()
        self.analyze(tasks)
        self.assertLess(time.monotonic() - start, 10.0)
        tasks = self.write_kit(*(_block(f"T{i}", "Do.", "echo hi", dialect="bold-colon-bare")
                                 for i in range(1, 3001)))
        start = time.monotonic()
        result = self.analyze(tasks)
        self.assertLess(time.monotonic() - start, 10.0)
        self.assertEqual(len(result["findings"]), 3000)
        self.assertEqual(result["verify"]["T3000"]["hint"], HINT)

    def test_the_linear_lexer_reads_exactly_as_d3s_shlex(self):
        # `_lex` replaces the shlex call (shlex is quadratic in a token's length); it must read
        # every line as D3's `shlex.shlex(line, posix=True, punctuation_chars=True)` with
        # `whitespace_split=True` and no comment characters does, falling back the same way.
        import random
        import shlex

        def reference(line):
            try:
                lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
                lexer.whitespace_split = True
                lexer.commenters = ""
                return list(lexer), False
            except ValueError:
                return line.split(), True

        frags = ["'", '"', "\\", " ", "\t", "\r", "\n", ";", "&&", "|", ">", "<", "(", ")", "&",
                 "a", "b/c", "x=1", "#", "$", "`", "", "", "''", '""', "\\'",
                 '\\"', "\\\\", "é", "\x0c", "--opt", "=", "*"]
        rng = random.Random(4)
        lines = ["".join(rng.choice(frags) for _ in range(rng.randint(0, 24)))
                 for _ in range(4000)]
        lines += ["a 'b c' \"d \\\" e\" f\\ g", "x;y&&z||w|v", "'' \"\" a''b", "a\\", "'open",
                  '"open', '"a\\', "a 'b\nc' d"]
        for line in lines:
            with self.subTest(line=line):
                self.assertEqual(kc._lex(line), reference(line))

    def test_case11e_analysis_time_is_linear_in_the_verify_size(self):
        import time
        line = "a" * 3_000_000
        for verify in ("echo " + line, "echo '" + line, "echo " + "a/b " * 750_000,
                       "echo '" + "a/b " * 750_000, "x " * 1_500_000):
            with self.subTest(shape=verify[:12], size=len(verify)):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                start = time.monotonic()
                self.analyze(tasks)
                self.assertLess(time.monotonic() - start, 10.0)

    def test_cd_moves_relative_checks_and_a_subshell_undoes_it(self):
        self.touch("sub/run.sh", "top.sh")
        for verify in ("(cd sub && ./run.sh) && ./top.sh", "cd sub && bash run.sh",
                       "cd sub && cd .. && ./top.sh"):
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                self.assertEqual(self.analyze(tasks)["findings"], [])
        for verify, path in (("(cd sub) && ./run.sh", "run.sh"),
                             ("cd sub && ./top.sh", "sub/top.sh")):
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                result = self.analyze(tasks)
                self.assertEqual(self.kinds(result), ["verify-missing-path"])
                self.assertIn(path, result["findings"][0]["detail"])

    def test_a_dynamic_bare_or_failed_cd_stops_relative_checks_only(self):
        for verify in ('cd "$X" && ./nope.sh', "cd && ./nope.sh", "cd - && python3 nope.py",
                       "cd $(mktemp -d) && ./nope.sh", "pushd /tmp && ./nope.sh"):
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                self.assertEqual(self.analyze(tasks)["findings"], [])
        # An absolute path is still checked after a dynamic cd; a missing cd target is one
        # finding, not a cascade over everything relative after it.
        tasks = self.write_kit(_block("T1", "Do it.", 'cd "$X" && /nonexistent-zz-dir/run.sh'))
        self.assertEqual(self.kinds(self.analyze(tasks)), ["verify-missing-path"])
        tasks = self.write_kit(_block("T1", "Do it.", "cd gone/dir && ./a.sh && python3 b.py"))
        result = self.analyze(tasks)
        self.assertEqual(self.kinds(result), ["verify-missing-path"])
        self.assertIn("gone/dir", result["findings"][0]["detail"])

    def test_the_third_amendments_writers_count_for_later_commands(self):
        self.touch("x.py")
        for verify in ("cp x.py out/y.py && python3 out/y.py",
                       "mv x.py out/m.py && python3 out/m.py",
                       "ln -s x.py out/l.py && python3 out/l.py",
                       "install -D x.py out/i.py && python3 out/i.py",
                       "git init -q out/fx && cd out/fx",
                       "git clone -q https://example.invalid/r.git out/cl && cd out/cl",
                       "git clone -q https://example.invalid/proj.git && cd proj",
                       "git worktree add /tmp/zz-wt-nowhere && cd /tmp/zz-wt-nowhere"):
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                self.assertEqual(self.analyze(tasks)["findings"], [])

    def test_interpreter_script_operands_are_blocking(self):
        self.touch("sub/run.sh")
        sound = ("bash sub/run.sh", "bash -c 'ls nothing/here'", "python3 -c 'x' nope/a.py",
                 "node -e 'console.log(1)'", "python3 - <<'PY'\nprint(1)\nPY",
                 'python3 "quoted/gone.py"', "python3 -m json.tool data.json",
                 "env python3 gone.py")
        for verify in sound:
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                self.assertEqual(self.analyze(tasks)["findings"], [])
        for verify, path in (("sh nothing/here.sh", "nothing/here.sh"),
                             ("python3 -u zz.py", "zz.py"), ("perl -w gone.pl", "gone.pl"),
                             ("node gone.mjs", "gone.mjs"), ("ruby lib/gone.rb", "lib/gone.rb"),
                             # rule 1: `exec` runs its operand as the command word
                             ("exec python3 gone.py", "gone.py")):
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                result = self.analyze(tasks)
                self.assertEqual(self.kinds(result), ["verify-missing-path"])
                self.assertIn(path, result["findings"][0]["detail"])

    def test_the_command_word_after_a_reserved_prefix_or_exec_is_blocking(self):
        # Third amendment, rule 1, as the verifier read it: bash puts the command word right
        # after `if then else elif while until do ! {`, after `time`, and `exec` runs its
        # operand as the command. Assignment words between are skipped.
        self.touch("README.md")
        for verify, kind, detail in (
                ("if python3 bin/missing.py; then true; fi", "verify-missing-path",
                 "bin/missing.py"),
                ("for f in a; do python3 bin/missing.py; done", "verify-missing-path",
                 "bin/missing.py"),
                ("! no-such-binary-xyz", "verify-missing-executable", "no-such-binary-xyz"),
                ("exec python3 bin/missing.py", "verify-missing-path", "bin/missing.py"),
                ("time python3 bin/missing.py", "verify-missing-path", "bin/missing.py"),
                ("{ X=1 no-such-binary-xyz; }", "verify-missing-executable",
                 "no-such-binary-xyz"),
                ("while ./bin/nope.sh; do true; done", "verify-missing-path", "bin/nope.sh")):
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                result = self.analyze(tasks)
                self.assertEqual(self.kinds(result), [kind], result["findings"])
                self.assertIn(detail, result["findings"][0]["detail"])
                # D3's fourth amendment: a verify-missing-path warns (exit 0) and fails only under strict.
                # D3's seventh amendment: a missing executable warns (exit 0) and fails only under strict.
                self.assertEqual(result["exit"], 0)
                self.assertEqual(self.analyze(tasks, strict=True)["exit"], 3)
        # The `test`/`[`/`[[` exemption still applies when one of them is that command word.
        for verify in ("if [[ -f README.md ]]; then true; fi",
                       "while read -r l; do true; done < /dev/null",
                       "if [[ -d gone/dir ]]; then true; fi", "! [ -e gone/x ]",
                       "if ! test -f gone/y; then true; fi", "time true", "exec true"):
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                self.assertEqual(self.analyze(tasks)["findings"], [])

    def test_arithmetic_case_and_function_rules(self):
        for verify in ("(( 1 ))", "((x=1)) && true", "for ((i=0; i<3; i++)); do true; done",
                       "[[ a < b && c > d ]] && true",
                       'case "$1" in a) no-such-binary-xyz;; esac',
                       "local x=1; declare -a y; trap true EXIT; eval true; time true"):
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                self.assertEqual(self.analyze(tasks)["findings"], [])
        # Inside a function BODY a word resolves at call time, so a function defined later in the
        # verify counts there (fourth amendment: only sure things block); a NUL byte is dropped.
        for verify in ("main() { helper_zz; }\nhelper_zz() { true; }\nmain",
                       "".join(f"f{i}() {{ f{i + 1}; }}\n" for i in range(50)) + "f50() { :; }\nf0",
                       "function outer {\n  inner_zz\n}\nfunction inner_zz { true; }\nouter",
                       "true\x00 && true"):
            with self.subTest(verify=verify[:30]):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                self.assertEqual(self.analyze(tasks)["findings"], [])
        # At top level a function is defined only for LATER command words; the case block ends
        # at `esac`.
        tasks = self.write_kit(_block("T1", "Do it.", "helper_zz\nhelper_zz() { true; }"))
        self.assertEqual(self.kinds(self.analyze(tasks)), ["verify-missing-executable"])
        tasks = self.write_kit(_block("T1", "Do it.", "case x in\n x) true;;\nesac\nno-such-binary-xyz"))
        self.assertEqual(self.kinds(self.analyze(tasks)), ["verify-missing-executable"])

    def test_a_path_written_earlier_is_created_by_the_task_itself(self):
        tasks = self.write_kit(_block(
            "T7", "Do it.", "python3 -c 'x' 2>/dev/null > out/r.txt && cat out/r.txt && "
                            "echo y | tee logs/t.log && touch flags/done && cat logs/t.log "
                            "flags/done && cat ./out/r.txt"))
        result = self.analyze(tasks)
        self.assertEqual(result["findings"], [])
        entries = {e["path"]: e for e in result["verify"]["T7"]["paths"]}
        for path in ("out/r.txt", "logs/t.log", "flags/done"):
            self.assertEqual(entries[path], {"path": path, "state": "created-by", "by": "T7"})

    def test_only_an_earlier_command_counts_as_writing(self):
        for verify in ("cat late/r.txt && echo x > late/r.txt",
                       "cat late/r.txt > late/r.txt"):
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                # Third amendment, rule 1: the `cat` operand is advisory, so no finding; the
                # write still counts only for LATER commands, so the read stays `missing`.
                result = self.analyze(tasks)
                self.assertEqual(self.kinds(result), [])
                self.assertEqual(result["verify"]["T1"]["paths"],
                                 [{"path": "late/r.txt", "state": "missing", "by": None}])

    def test_a_file_beneath_a_made_directory_is_not_itself_written(self):
        # "Writes" is the `mkdir` operand itself (the amendment's own definition). Counting what
        # lies beneath it would clear an unquoted missing script, which stays checked.
        for verify, path in (("mkdir -p out/sub && cat out/sub/report.json",
                              "out/sub/report.json"),
                             ("mkdir -p bin && python3 bin/missing.py", "bin/missing.py")):
            with self.subTest(verify=verify):
                tasks = self.write_kit(_block("T1", "Do it.", verify))
                result = self.analyze(tasks)
                states = {e["path"]: e["state"] for e in result["verify"]["T1"]["paths"]}
                self.assertEqual(states[path], "missing")  # not counted as written
                if path.startswith("out/"):
                    # Third amendment, rule 1: a `cat` operand is advisory -- no finding.
                    self.assertEqual(self.kinds(result), [])
                    continue
                self.assertEqual(self.kinds(result), ["verify-missing-path"])
                self.assertIn(path, result["findings"][0]["detail"])
        tasks = self.write_kit(_block("T1", "Do it.", "mkdir -p out/sub && test -d out/sub && "
                                                      "ls out/sub"))
        self.assertEqual(self.analyze(tasks)["findings"], [])  # the operand itself is written

    def test_quoting_exempts_arguments_but_not_the_first_word_or_the_mappings(self):
        self.touch("tests/test_q.py")
        tasks = self.write_kit(_block("T1", "Do it.", 'python3 "bin/x.py" && cat \'docs/q.md\''))
        self.assertEqual(self.analyze(tasks)["findings"], [])  # the trade the user chose
        tasks = self.write_kit(_block("T1", "Do it.", "'./scripts/gone.sh' --all"))
        self.assertEqual(self.kinds(self.analyze(tasks)), ["verify-missing-path"])
        tasks = self.write_kit(_block(
            "T1", "Do it.", "python3 -m unittest discover -s 'tests' -p 'test_q.py' && "
                            "python3 -m unittest discover -p \"test_gone.py\""))
        result = self.analyze(tasks)
        self.assertEqual([e["path"] for e in result["verify"]["T1"]["paths"]],
                         ["tests/test_q.py", "tests/test_gone.py"])
        self.assertEqual(self.kinds(result), ["verify-missing-path"])

    def test_double_bracket_operands_are_values_even_after_a_prefix(self):
        tasks = self.write_kit(_block(
            "T1", "Do it.", "if [[ -d gone/dir ]]; then true; fi && ! [[ -e also/gone ]]"))
        self.assertEqual(self.analyze(tasks)["findings"], [])


class StaticByConstructionTests(_KitFixture):
    def _every_fixture(self):
        yield self.sound_kit()
        yield self.write_kit(_block("T1", "Do it.", "python3 bin/missing.py"))
        yield self.write_kit(_block("T1", "Do it.", "no-such-binary-xyz"))
        yield self.write_kit(_block("T1", "Do it.", "true", dialect="bold-colon-bare"))
        yield self.write_kit(_block("T1", "See `docs/nowhere.md`.",
                                    "python3 - <<'PY'\nprint(1)\nPY\n"
                                    'test -z "$(git status --porcelain)"'))

    def test_case11_analyze_has_no_runner_and_survives_every_spawn_seam_raising(self):
        params = inspect.signature(kc.analyze_kit).parameters
        self.assertEqual(list(params), ["kit_dir", "tasks", "strict", "repo_root"])

        def boom(*_a, **_k):
            raise AssertionError("analyze tried to execute something")

        seams = [mock.patch.object(kc, "_pr", boom), mock.patch.object(kc, "_ep", boom)]
        for name in ("run", "Popen", "call", "check_call", "check_output", "getoutput",
                     "getstatusoutput"):
            seams.append(mock.patch.object(subprocess, name, boom))
        for name in ("system", "popen", "execv", "execve", "execvp", "posix_spawn",
                     "posix_spawnp", "fork"):
            if hasattr(os, name):
                seams.append(mock.patch.object(os, name, boom))
        # The hint loads kit_verify_hook lazily; make sure that load happens under the seams.
        if hasattr(kc, "_KIT_VERIFY_HOOK"):
            seams.append(mock.patch.object(kc, "_KIT_VERIFY_HOOK", None))
        with contextlib.ExitStack() as stack:
            for seam in seams:
                stack.enter_context(seam)
            results = [self.analyze(tasks) for tasks in self._every_fixture()]
        # D3's fourth amendment: a verify-missing-path warns (exit 0) and fails only under strict.
        # D3's seventh amendment: a missing executable warns (exit 0) and fails only under strict.
        self.assertEqual([r["exit"] for r in results], [0, 0, 0, 3, 0])
        self.assertEqual(results[3]["verify"]["T1"]["hint"], HINT)

    def test_case12_the_kit_dir_is_byte_identical_after_every_call(self):
        for tasks in self._every_fixture():
            (self.kit / "NOTES.md").write_text("## notes\n")
            before = self.snapshot()
            self.analyze(tasks)
            self.analyze(tasks, strict=True)
            kc.render_analyze(self.analyze(tasks))
            with contextlib.redirect_stderr(io.StringIO()), contextlib.suppress(SystemExit):
                kc.exit_if_unsound_kit(self.kit, tasks)
            with contextlib.redirect_stdout(io.StringIO()):
                kc._cli(["analyze", "--kit", str(self.kit), "--json"])
            self.assertEqual(self.snapshot(), before)

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_the_fixture_repo_stays_clean_in_git(self):
        tasks = self.sound_kit()
        env = dict(os.environ, HOME=str(self.root), GIT_CONFIG_NOSYSTEM="1",
                   GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True, env=env)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, env=env)
        subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-qm", "fixture"],
                       cwd=self.root, check=True, env=env)
        tasks_bytes = (self.kit / "TASKS.md").read_bytes()
        self.analyze(tasks)
        with contextlib.redirect_stdout(io.StringIO()):
            kc._cli(["analyze", "--kit", str(self.kit)])
        status = subprocess.run(["git", "status", "--porcelain"], cwd=self.root, env=env,
                                capture_output=True, text=True, check=True).stdout
        self.assertEqual(status, "")
        self.assertEqual((self.kit / "TASKS.md").read_bytes(), tasks_bytes)


class RenderAndHelperTests(_KitFixture):
    def test_render_is_terse_and_names_every_finding_and_resolution(self):
        # The absent path comes FIRST: a creation word within the creation window before a path makes
        # it created-by (D3), so "add new `a`; see `b`" would resolve `b` too.
        tasks = self.write_kit(
            _block("T1", "See `docs/nowhere.md` for context. Then add new `tests/test_new.py`.",
                   "true"),
            _block("T2", "Run.", "python3 -m unittest discover -s tests -p 'test_new.py' && "
                                 "no-such-binary-xyz", depends=["T1"]),
        )
        text = kc.render_analyze(self.analyze(tasks))
        lines = text.splitlines()
        self.assertIn("analyze: T1 brief-missing-path -- ", text)
        self.assertIn("analyze: T2 verify-missing-executable -- ", text)
        self.assertIn("analyze: T2 path tests/test_new.py created-by T1", lines)
        self.assertIn("analyze: T1 path tests/test_new.py created-by T1", lines)
        self.assertEqual(lines[-1], "analyze: 2 finding(s)")
        self.assertTrue(all(ln.startswith("analyze: ") for ln in lines))

    def test_render_of_a_sound_kit_ends_sound(self):
        self.assertEqual(kc.render_analyze(self.analyze(self.sound_kit())).splitlines()[-1],
                         "analyze: sound")

    def test_exit_if_unsound_kit_exits_3_only_on_a_failing_finding(self):
        tasks = self.write_kit(_block("T1", "See `docs/nowhere.md`.", "true"))
        out = io.StringIO()
        result = kc.exit_if_unsound_kit(self.kit, tasks, out=out)
        self.assertEqual(result["exit"], 0)
        self.assertIn("brief-missing-path", out.getvalue())
        tasks = self.write_kit(_block("T1", "Do it.", "python3 bin/missing.py"))
        out = io.StringIO()
        # D3's fourth amendment: a verify-missing-path warns (exit 0) and fails only under strict.
        # exit_if_unsound_kit returns, and still prints, when only path findings exist.
        result = kc.exit_if_unsound_kit(self.kit, tasks, out=out)
        self.assertEqual(result["exit"], 0)
        self.assertIn("verify-missing-path", out.getvalue())
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            kc.exit_if_unsound_kit(self.kit, tasks)
        self.assertIn("verify-missing-path", err.getvalue())
        tasks = self.write_kit(_block("T1", "Do it.", "no-such-binary-xyz"))
        # D3's seventh amendment: a missing executable warns (exit 0) and fails only under strict.
        out = io.StringIO()
        self.assertEqual(kc.exit_if_unsound_kit(self.kit, tasks, out=out)["exit"], 0)
        self.assertIn("verify-missing-executable", out.getvalue())
        tasks = self.write_kit(_block("T1", "Do it.", "true", dialect="none"))
        with self.assertRaises(SystemExit) as caught:
            kc.exit_if_unsound_kit(self.kit, tasks, out=io.StringIO())
        self.assertEqual(caught.exception.code, 3)

    def test_classify_path_states(self):
        self.touch("bin/here.py")
        creators = {"T1": "Add new `bin/made.py`.", "T2": "Write `bin/own.py`."}
        self.assertEqual(kc.classify_path("bin/here.py", self.root, "T2", creators),
                         {"path": "bin/here.py", "state": "exists", "by": None})
        self.assertEqual(kc.classify_path("bin/made.py", self.root, "T2", creators),
                         {"path": "bin/made.py", "state": "created-by", "by": "T1"})
        self.assertEqual(kc.classify_path("bin/own.py", self.root, "T2", creators),
                         {"path": "bin/own.py", "state": "created-by", "by": "T2"})
        self.assertEqual(kc.classify_path("bin/none.py", self.root, "T2", creators),
                         {"path": "bin/none.py", "state": "missing", "by": None})
        absolute = str(self.root / "bin" / "here.py")
        self.assertEqual(kc.classify_path(absolute, self.root, "T2", {})["state"], "exists")

    def test_verify_tokens_splits_only_outside_quotes(self):
        cmds = kc.verify_tokens("a 'x && y' && b \"p | q\" | c; d\ne")
        self.assertEqual([[str(t) for t in c] for c in cmds],
                         [["a", "x && y"], ["b", "p | q"], ["c"], ["d"], ["e"]])


class CommandLineTests(_KitFixture):
    def _proc(self, *argv):
        env = dict(os.environ, HOME=str(self.root), POLYTROPOS_DATA_HOME=str(self.root / "data"))
        return subprocess.run([sys.executable, str(KC_PATH), "analyze", "--kit", str(self.kit),
                               *argv], capture_output=True, text=True, env=env, cwd=self.root,
                              timeout=60)

    def test_case13_json_parses_and_its_exit_is_the_process_return(self):
        self.sound_kit()
        proc = self._proc("--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["exit"], 0)
        self.write_kit(_block("T1", "Do it.", "python3 bin/missing.py"))
        proc = self._proc("--json")
        # D3's fourth amendment: a verify-missing-path warns (exit 0) and fails only under strict.
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["exit"], 0)
        self.assertEqual(payload["findings"][0]["kind"], "verify-missing-path")
        proc = self._proc()
        self.assertEqual(proc.returncode, 0)
        self.assertIn("analyze: T1 verify-missing-path -- ", proc.stdout)
        proc = self._proc("--json", "--strict")
        self.assertEqual((proc.returncode, json.loads(proc.stdout)["exit"]), (3, 3))

    def test_strict_flips_a_brief_only_kit(self):
        self.write_kit(_block("T1", "See `docs/nowhere.md`.", "true"))
        self.assertEqual(self._proc().returncode, 0)
        self.assertEqual(self._proc("--strict").returncode, 3)

    def test_an_invalid_graph_returns_2_before_any_analysis(self):
        self.write_kit(_block("T1", "Do it.", "true"), _block("T1", "Again.", "true"))

        def never(*_a, **_k):
            raise AssertionError("analysis ran on an invalid graph")

        with mock.patch.object(kc, "analyze_kit", never), \
                contextlib.redirect_stderr(io.StringIO()) as err, \
                self.assertRaises(SystemExit) as caught:
            kc._cli(["analyze", "--kit", str(self.kit)])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("duplicate-id", err.getvalue())
        self.assertEqual(self._proc().returncode, 2)

    def test_help_lists_analyze(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            kc._cli(["--help"])
        self.assertIn("analyze", out.getvalue())


class BriefDerivedGapTests(_KitFixture):
    """Gaps the brief's own case list leaves open, written from PLAN D2/D3/D5/D17(a)/R4."""

    def verify_kinds(self, verify, **kw):
        tasks = self.write_kit(_block("T1", "Do it.", verify))
        return self.analyze(tasks, **kw)

    # -- result dict shape ------------------------------------------------------------------
    def test_result_dict_has_exactly_the_briefed_shape(self):
        tasks = self.sound_kit()
        result = self.analyze(tasks)
        self.assertEqual(set(result), {"v", "kit", "strict", "exit", "findings", "paths", "verify"})
        self.assertEqual(result["v"], kc.CONTRACT_VERSION)
        self.assertEqual(result["kit"], "fx")
        self.assertIs(result["strict"], False)
        self.assertIs(self.analyze(tasks, strict=True)["strict"], True)
        for tid in ("T1", "T2"):
            v = result["verify"][tid]
            self.assertEqual(set(v), {"parseable", "hint", "executables", "paths"})
            self.assertIs(v["parseable"], True)
            self.assertIsNone(v["hint"])
            for e in v["executables"]:
                self.assertEqual(set(e), {"word", "state"})
            for e in v["paths"] + result["paths"][tid]:
                self.assertEqual(set(e), {"path", "state", "by"})
                self.assertIn(e["state"], kc.PATH_STATES)
        json.dumps(result)

    def test_result_is_deterministic_across_calls(self):
        tasks = self.sound_kit()
        self.assertEqual(self.analyze(tasks), self.analyze(tasks))

    def test_finding_entries_have_exactly_task_kind_detail(self):
        result = self.verify_kinds("python3 bin/missing.py")
        self.assertEqual(len(result["findings"]), 1)
        f = result["findings"][0]
        self.assertEqual(set(f), {"task", "kind", "detail"})
        self.assertEqual((f["task"], f["kind"]), ("T1", "verify-missing-path"))
        self.assertIn("bin/missing.py", f["detail"])

    # -- strict / non-strict exit split -------------------------------------------------------
    def test_strict_never_changes_a_verify_finding_and_never_lowers_exit(self):
        for strict in (False, True):
            # D3's fourth amendment: a verify-missing-path warns (exit 0) and fails only under strict.
            self.assertEqual(self.verify_kinds("python3 bin/missing.py", strict=strict)["exit"],
                             3 if strict else 0)
            # D3's seventh amendment: a missing executable warns (exit 0) and fails only under strict.
            self.assertEqual(self.verify_kinds("no-such-binary-xyz", strict=strict)["exit"],
                             3 if strict else 0)

    def test_unparseable_verify_exits_3_even_non_strict(self):
        tasks = self.write_kit(_block("T1", "Do it.", "true", dialect="plain-colon-bare"))
        result = self.analyze(tasks)
        self.assertEqual(result["exit"], 3)
        self.assertEqual(self.kinds(result), ["verify-unparseable"])
        self.assertIs(result["verify"]["T1"]["parseable"], False)

    def test_strict_with_a_sound_kit_stays_0(self):
        self.assertEqual(self.analyze(self.sound_kit(), strict=True)["exit"], 0)

    def test_brief_findings_are_reported_alongside_a_verify_exit_3(self):
        tasks = self.write_kit(_block("T1", "See `docs/nowhere.md`.", "python3 bin/missing.py"))
        result = self.analyze(tasks)
        # D3's fourth amendment: a verify-missing-path warns (exit 0) and fails only under strict.
        self.assertEqual(result["exit"], 0)
        self.assertEqual(self.analyze(tasks, strict=True)["exit"], 3)
        self.assertEqual(sorted(self.kinds(result)), ["brief-missing-path", "verify-missing-path"])

    # -- created-by scoping -------------------------------------------------------------------
    def test_a_downstream_task_creating_a_brief_path_does_not_count_upstream(self):
        tasks = self.write_kit(
            _block("T1", "Read `docs/later.md`.", "true"),
            _block("T2", "Add new `docs/later.md`.", "true", depends=["T1"]),
        )
        result = self.analyze(tasks)
        self.assertEqual(self.kinds(result), ["brief-missing-path"])
        self.assertEqual(result["findings"][0]["task"], "T1")

    def test_brief_path_created_by_is_transitive_over_depends(self):
        tasks = self.write_kit(
            _block("T1", "Add new `lib/core.py`.", "true"),
            _block("T2", "Wire.", "true", depends=["T1"]),
            _block("T3", "Then read `lib/core.py` again.", "true", depends=["T2"]),
        )
        result = self.analyze(tasks)
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["paths"]["T3"], [{"path": "lib/core.py", "state": "created-by",
                                                   "by": "T1"}])

    def test_creator_must_be_upstream_not_merely_earlier_in_the_file(self):
        tasks = self.write_kit(
            _block("T1", "Add new `lib/core.py`.", "true"),
            _block("T2", "Unrelated.", "python3 lib/core.py"),
        )
        result = self.analyze(tasks)
        self.assertEqual(self.kinds(result), ["verify-missing-path"])

    def test_creation_words_are_case_insensitive(self):
        tasks = self.write_kit(
            _block("T1", "Creates `lib/a.py`. WRITE `lib/b.py`. New `lib/c.py`.", "true"),
            _block("T2", "Run.", "python3 lib/a.py && python3 lib/b.py && python3 lib/c.py",
                   depends=["T1"]),
        )
        result = self.analyze(tasks)
        self.assertEqual(result["findings"], [])
        self.assertEqual({p["by"] for p in result["verify"]["T2"]["paths"]}, {"T1"})

    def test_a_non_creation_verb_does_not_make_a_path_created_by(self):
        tasks = self.write_kit(
            _block("T1", "Delete `lib/old.py`, review `lib/rev.py`.", "true"),
            _block("T2", "Run.", "python3 lib/old.py", depends=["T1"]),
        )
        self.assertEqual(self.kinds(self.analyze(tasks)),
                         ["brief-missing-path", "brief-missing-path", "verify-missing-path"])

    def test_a_path_written_by_another_tasks_verify_does_not_count(self):
        tasks = self.write_kit(
            _block("T1", "Do it.", "echo hi > out/r.txt"),
            _block("T2", "Check.", "cat out/r.txt", depends=["T1"]),
        )
        # Third amendment, rule 1: `cat`'s operand is a data argument -- resolved and recorded,
        # never a finding. T1's write still does not count for T2: the state stays `missing`.
        result = self.analyze(tasks)
        self.assertEqual(self.kinds(result, "T2"), [])
        self.assertEqual(result["verify"]["T2"]["paths"],
                         [{"path": "out/r.txt", "state": "missing", "by": None}])

    def test_an_existing_directory_counts_as_existing(self):
        (self.root / "docs" / "sdd").mkdir(parents=True)
        result = self.verify_kinds("ls docs/sdd")
        self.assertEqual(result["exit"], 0)
        self.assertEqual(result["verify"]["T1"]["paths"][0]["state"], "exists")

    def test_brief_paths_are_read_from_acceptance_text_too_but_not_from_the_verify_fence(self):
        text = (
            "### T1 — x\n- id: T1\n- title: t\n- status: pending\n- model: haiku\n"
            "- depends: (none)\n\n**Brief.** Do it.\n\n"
            "**Acceptance.** `docs/accept.md` is present.\n\n"
            "**Verify.**\n\n```bash\ntrue # `docs/infence.md`\n```\n"
        )
        (self.kit / "TASKS.md").write_text("# fx\n\n## Phase 1 — x\n\n" + text)
        result = self.analyze(kc.parse_tasks((self.kit / "TASKS.md").read_text()))
        details = " ".join(f["detail"] for f in result["findings"] if f["kind"] == "brief-missing-path")
        self.assertIn("docs/accept.md", details)
        self.assertNotIn("docs/infence.md", details)

    # -- heredocs -----------------------------------------------------------------------------
    def test_unquoted_and_double_quoted_heredoc_tags_hide_their_bodies(self):
        for opener in ("<<EOF", '<<"EOF"', "<<'EOF'"):
            verify = f"python3 - {opener}\nimport fake.path_x\nopen('nowhere/dir/x.py')\n" \
                     f"no-such-binary-xyz inside\nEOF"
            self.touch("bin/ok.py")
            result = self.verify_kinds(f"true\n{verify}")
            self.assertEqual(result["findings"], [], opener)

    def test_commands_after_the_heredoc_terminator_are_still_checked(self):
        verify = "python3 - <<'PY'\nprint(1)\nPY\nno-such-binary-xyz"
        self.assertEqual(self.kinds(self.verify_kinds(verify)), ["verify-missing-executable"])
        verify = "python3 - <<'PY'\nprint(1)\nPY\ncat docs/nowhere.md"
        # Third amendment, rule 1: the data argument is still read (recorded), never a finding.
        result = self.verify_kinds(verify)
        self.assertEqual(self.kinds(result), [])
        self.assertEqual(result["verify"]["T1"]["paths"],
                         [{"path": "docs/nowhere.md", "state": "missing", "by": None}])

    def test_the_command_on_the_heredoc_opening_line_is_still_checked(self):
        verify = "no-such-binary-xyz - <<'PY'\nbody\nPY"
        self.assertEqual(self.kinds(self.verify_kinds(verify)), ["verify-missing-executable"])

    def test_two_heredocs_in_one_verify(self):
        verify = "cat <<A\nx/y/z.py\nA\ncat <<'B'\nq/r/s.py\nB\ntrue"
        self.assertEqual(self.verify_kinds(verify)["findings"], [])

    # -- redirection --------------------------------------------------------------------------
    def test_redirection_targets_are_skipped_for_all_forms(self):
        self.touch("bin/tool.py")
        for verify in ("python3 bin/tool.py > out/log.txt", "python3 bin/tool.py >> out/log.txt",
                       "python3 bin/tool.py >out/log.txt", "echo hi > nowhere/a.txt && true"):
            self.assertEqual(self.verify_kinds(verify)["findings"], [], verify)

    def test_redirection_skip_does_not_swallow_the_next_command(self):
        self.touch("bin/tool.py")
        verify = "python3 bin/tool.py > out/log.txt && python3 bin/missing.py"
        result = self.verify_kinds(verify)
        self.assertEqual(self.kinds(result), ["verify-missing-path"])
        self.assertIn("bin/missing.py", result["findings"][0]["detail"])

    def test_an_input_operand_to_the_left_of_a_redirect_is_still_checked(self):
        verify = "cat docs/nowhere.md > out/copy.txt"
        # Third amendment, rule 1: still resolved and recorded, but a data argument is advice.
        result = self.verify_kinds(verify)
        self.assertEqual(self.kinds(result), [])
        self.assertEqual(result["verify"]["T1"]["paths"],
                         [{"path": "docs/nowhere.md", "state": "missing", "by": None}])

    # -- written earlier in the same verify: later commands only ------------------------------
    def test_touch_tee_and_mkdir_operands_count_for_later_commands(self):
        for verify in ("touch spike/a.txt && cat spike/a.txt",
                       "echo hi | tee spike/b.txt && cat spike/b.txt",
                       "mkdir -p spike/d && ls spike/d"):
            result = self.verify_kinds(verify)
            self.assertEqual(result["findings"], [], verify)
            self.assertIn("created-by", {p["state"] for p in result["verify"]["T1"]["paths"]})
            self.assertEqual({p["by"] for p in result["verify"]["T1"]["paths"] if p["by"]}, {"T1"})

    def test_a_read_before_the_write_is_missing(self):
        for verify in ("cat spike/a.txt && touch spike/a.txt",
                       "cat spike/a.txt; echo hi > spike/a.txt"):
            # Third amendment, rule 1: a data argument is never a finding; the read before the
            # write is still recorded `missing`, not `created-by`.
            result = self.verify_kinds(verify)
            self.assertEqual(self.kinds(result), [], verify)
            self.assertEqual(result["verify"]["T1"]["paths"],
                             [{"path": "spike/a.txt", "state": "missing", "by": None}], verify)

    def test_the_writing_command_itself_does_not_make_its_own_read_operand_created(self):
        # Third amendment, rule 1: no finding for a data argument; still `missing`, not created.
        result = self.verify_kinds("cat spike/in.txt > spike/in.txt")
        self.assertEqual(self.kinds(result), [])
        self.assertEqual(result["verify"]["T1"]["paths"],
                         [{"path": "spike/in.txt", "state": "missing", "by": None}])

    # -- first word handling ------------------------------------------------------------------
    def test_a_quoted_first_word_is_still_checked(self):
        self.assertEqual(self.kinds(self.verify_kinds('"no-such-binary-xyz" --flag')),
                         ["verify-missing-executable"])
        self.assertEqual(self.kinds(self.verify_kinds("'bin/missing.py' --flag")),
                         ["verify-missing-path"])

    def test_every_operator_outside_quotes_starts_a_new_command(self):
        for verify in ("true || no-such-binary-xyz", "true; no-such-binary-xyz",
                       "true && no-such-binary-xyz", "true | no-such-binary-xyz",
                       "true\nno-such-binary-xyz"):
            self.assertEqual(self.kinds(self.verify_kinds(verify)),
                             ["verify-missing-executable"], verify)

    def test_operators_inside_quotes_do_not_start_a_command(self):
        for verify in ("echo 'a && no-such-binary-xyz'", 'echo "a | no-such-binary-xyz"',
                       "echo 'a; no-such-binary-xyz'"):
            self.assertEqual(self.verify_kinds(verify)["findings"], [], verify)

    def test_an_executable_on_path_resolves_and_is_recorded(self):
        result = self.verify_kinds("python3 -c 'print(1)'")
        words = [e["word"] for e in result["verify"]["T1"]["executables"]]
        self.assertIn("python3", words)
        self.assertEqual(result["findings"], [])

    def test_a_missing_executable_is_recorded_in_the_verify_entry(self):
        result = self.verify_kinds("no-such-binary-xyz")
        entry = [e for e in result["verify"]["T1"]["executables"]
                 if e["word"] == "no-such-binary-xyz"]
        self.assertEqual(len(entry), 1)
        self.assertNotEqual(entry[0]["state"], "exists")

    # -- D17(a) -----------------------------------------------------------------------------
    def test_the_spike_kit_passes_through_the_drivers_gate_without_exiting(self):
        tasks = self.write_kit(
            _block("T1", "Sketch new `spike/notes.md`.", "true"),
            _block("T2", "Probe.", 'python3 -c "print(1)"', depends=["T1"]),
            _block("T3", "Look.", 'test -n "$(ls)"', depends=["T2"]),
        )
        out = io.StringIO()
        result = kc.exit_if_unsound_kit(self.kit, tasks, out=out)
        self.assertEqual(result["exit"], 0)

    # -- render_analyze / exit_if_unsound_kit -------------------------------------------------
    def test_render_finding_line_format_is_exact(self):
        result = self.verify_kinds("python3 bin/missing.py")
        f = result["findings"][0]
        lines = kc.render_analyze(result).splitlines()
        self.assertEqual(lines[0], f"analyze: T1 verify-missing-path -- {f['detail']}")
        self.assertEqual(lines[-1], "analyze: 1 finding(s)")

    def test_render_sound_kit_is_exactly_one_line_and_hides_existing_paths(self):
        text = kc.render_analyze(self.analyze(self.sound_kit()))
        self.assertEqual(text.strip().splitlines(), ["analyze: sound"])
        self.assertNotIn("exists", text)

    def test_render_orders_findings_then_paths_then_summary(self):
        tasks = self.write_kit(
            _block("T1", "Add new `lib/core.py`.", "true"),
            _block("T2", "Run.", "python3 lib/core.py && no-such-binary-xyz", depends=["T1"]),
        )
        lines = kc.render_analyze(self.analyze(tasks)).splitlines()
        idx_f = [i for i, ln in enumerate(lines) if "verify-missing-executable" in ln][0]
        idx_p = [i for i, ln in enumerate(lines) if " path lib/core.py created-by T1" in ln][0]
        self.assertLess(idx_f, idx_p)
        self.assertEqual(idx_p < len(lines) - 1, True)
        self.assertEqual(lines[-1], "analyze: 1 finding(s)")

    def test_render_is_terse_one_line_per_item(self):
        tasks = self.write_kit(
            _block("T1", "See `docs/a.md` `docs/b.md` `docs/c.md`.", "true"),
        )
        lines = kc.render_analyze(self.analyze(tasks)).splitlines()
        # one line per finding, one per non-exists path summary (missing counts), one total
        self.assertEqual(len([ln for ln in lines if "brief-missing-path" in ln]), 3)
        self.assertEqual(lines[-1], "analyze: 3 finding(s)")
        self.assertTrue(all(ln.startswith("analyze: ") and ln.strip() for ln in lines))
        self.assertLessEqual(len(lines), 7)

    def test_exit_if_unsound_kit_writes_only_to_out_and_never_strict(self):
        tasks = self.write_kit(_block("T1", "See `docs/nowhere.md`.", "true"))
        out, stdout = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = kc.exit_if_unsound_kit(self.kit, tasks, out=out)
        self.assertEqual(result["exit"], 0)
        self.assertIs(result["strict"], False)
        self.assertEqual(stdout.getvalue(), "")
        self.assertTrue(out.getvalue().strip())

    def test_exit_if_unsound_kit_exits_3_for_unparseable_and_missing_executable(self):
        tasks = self.write_kit(_block("T1", "Do.", "true", dialect="none"))
        with self.assertRaises(SystemExit) as caught:
            kc.exit_if_unsound_kit(self.kit, tasks, out=io.StringIO())
        self.assertEqual(caught.exception.code, 3)
        # D3's seventh amendment: a missing executable warns (exit 0) and fails only under strict.
        tasks = self.write_kit(_block("T1", "Do.", "no-such-binary-xyz"))
        out = io.StringIO()
        self.assertEqual(kc.exit_if_unsound_kit(self.kit, tasks, out=out)["exit"], 0)
        self.assertIn("verify-missing-executable", out.getvalue())

    # -- CLI ----------------------------------------------------------------------------------
    def _run(self, *argv):
        env = dict(os.environ, HOME=str(self.root), POLYTROPOS_DATA_HOME=str(self.root / "data"))
        return subprocess.run([sys.executable, str(KC_PATH), "analyze", "--kit", str(self.kit),
                               *argv], capture_output=True, text=True, env=env, cwd=self.root,
                              timeout=60)

    def test_unknown_dependency_is_exit_2_with_empty_stdout(self):
        self.write_kit(_block("T1", "Do.", "python3 bin/missing.py", depends=["T9"]))
        proc = self._run("--json")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")

    def test_a_cycle_is_exit_2_before_analysis(self):
        self.write_kit(_block("T1", "Do.", "python3 bin/missing.py", depends=["T2"]),
                       _block("T2", "Do.", "true", depends=["T1"]))
        proc = self._run()
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("verify-missing-path", proc.stdout)

    def test_json_output_with_strict_reports_strict_true_and_exit_3(self):
        self.write_kit(_block("T1", "See `docs/nowhere.md`.", "true"))
        proc = self._run("--json", "--strict")
        self.assertEqual(proc.returncode, 3)
        payload = json.loads(proc.stdout)
        self.assertIs(payload["strict"], True)
        self.assertEqual(payload["exit"], 3)

    def test_analyze_writes_nothing_under_the_temp_root_beyond_what_exists(self):
        self.sound_kit()
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        self._run("--json")
        after = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        self.assertEqual(before, after)


class DriverPreflightTests(_KitFixture):
    """PLAN D5: each driver's `run` refuses (exit 3) an unreadable verify before any dispatch,
    and only warns on a missing executable or path. `--dry-run` spawns nothing in every driver."""

    DRIVERS = ("claude", "copilot", "codex", "cursor")

    def _run_driver(self, driver, verify):
        if driver == "codex":
            # codex's own `no runnable verify command` guard (exit 2) fires first on the SELECTED
            # task, so its unreadable verify sits on a second pending task, which the kit-wide
            # check still sees before any dispatch.
            self.write_kit(_block("T1", "Do.", "true" if verify == "" else verify),
                           _block("T2", "Do.", verify if verify == "" else "true"))
        else:
            self.write_kit(_block("T1", "Do.", verify))
        tasks_md = self.kit / "TASKS.md"
        tasks_md.write_text(tasks_md.read_text().replace(
            "- model: haiku", "- model: mid" if driver == "codex" else "- model: sonnet"))
        (self.kit / "PLAN.md").write_text("# fx plan\n")
        # The claude driver reads its kit agent from the workspace (cwd), never this checkout.
        agents = self.root / ".claude" / "agents"
        agents.mkdir(parents=True, exist_ok=True)
        (agents / "fx-implementer.md").write_text(
            "---\nname: fx-implementer\ndescription: fixture\nmodel: sonnet\n---\n\nFixture.\n")
        home = self.root / "home"
        home.mkdir(exist_ok=True)
        env = dict(os.environ, HOME=str(home))
        before = self.snapshot()
        proc = subprocess.run(
            [sys.executable, str(Path(kc.__file__).resolve().parent / f"{driver}_execute.py"),
             "run", "--kit", str(self.kit), "--dry-run",
             "--attempt-store", str(self.root / "store")],
            capture_output=True, text=True, env=env, cwd=str(self.root), timeout=120)
        self.assertEqual(self.snapshot(), before, f"{driver} changed the kit dir")
        return proc

    def test_an_empty_verify_fence_refuses_with_exit_3_in_every_driver(self):
        for driver in self.DRIVERS:
            with self.subTest(driver=driver):
                proc = self._run_driver(driver, "")
                self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
                self.assertIn("verify-unparseable", proc.stderr)

    def test_a_readable_verify_dry_runs_normally_in_every_driver(self):
        for driver in self.DRIVERS:
            with self.subTest(driver=driver):
                proc = self._run_driver(driver, "true")
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertNotIn("verify-unparseable", proc.stderr)

    def test_a_missing_executable_only_warns_in_every_driver(self):
        for driver in self.DRIVERS:
            with self.subTest(driver=driver):
                proc = self._run_driver(driver, "no-such-binary-xyz")
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn("verify-missing-executable", proc.stderr)

    def test_a_missing_path_only_warns_in_every_driver(self):
        for driver in self.DRIVERS:
            with self.subTest(driver=driver):
                proc = self._run_driver(driver, "python3 bin/missing.py")
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn("verify-missing-path", proc.stderr)


class DriverPreflightGapTests(_KitFixture):
    """Test-author additions for T5 (PLAN D5, R1, D3's sixth and seventh amendments): the gate
    is kit-wide, status-aware, runs before any store or kit write, and is the contract's own
    object. Every run is `--dry-run` with a temp HOME and a temp `--attempt-store`."""

    DRIVERS = ("claude", "copilot", "codex", "cursor")

    def _stage(self, driver, *blocks):
        self.write_kit(*blocks)
        tasks_md = self.kit / "TASKS.md"
        tasks_md.write_text(tasks_md.read_text().replace(
            "- model: haiku", "- model: mid" if driver == "codex" else "- model: sonnet"))
        (self.kit / "PLAN.md").write_text("# fx plan\n")
        agents = self.root / ".claude" / "agents"
        agents.mkdir(parents=True, exist_ok=True)
        (agents / "fx-implementer.md").write_text(
            "---\nname: fx-implementer\ndescription: fixture\nmodel: sonnet\n---\n\nFixture.\n")

    def _drive(self, driver, extra=()):
        home = self.root / "home"
        home.mkdir(exist_ok=True)
        store = self.root / "store"
        before = self.snapshot()
        proc = subprocess.run(
            [sys.executable, str(ROOT / "bin" / f"{driver}_execute.py"), "run",
             "--kit", str(self.kit), "--dry-run", "--attempt-store", str(store), *extra],
            capture_output=True, text=True, env=dict(os.environ, HOME=str(home)),
            cwd=str(self.root), timeout=120)
        return proc, before, store

    def _store_files(self, store):
        return sorted(str(p) for p in store.rglob("*")) if store.exists() else []

    def test_a_refusal_writes_nothing_to_the_store_or_the_kit(self):
        # D5: "before any --dry-run branch, any claim, any preamble" -- a refusal leaves no trace.
        for driver in self.DRIVERS:
            with self.subTest(driver=driver):
                self._stage(driver, _block("T1", "Do.", "true"), _block("T2", "Do.", ""))
                proc, before, store = self._drive(driver)
                self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(self._store_files(store), [], f"{driver} touched the store")
                shutil.rmtree(store, ignore_errors=True)

    def test_a_non_selected_unparseable_pending_task_still_refuses_the_kit(self):
        # D5: the check is kit-wide; the selected task (T1) is fine, the later one is not.
        for driver in self.DRIVERS:
            with self.subTest(driver=driver):
                self._stage(driver, _block("T1", "Do.", "true"),
                            _block("T2", "Do.", "true", depends=["T1"]),
                            _block("T3", "Do.", "  ", depends=["T2"]))
                proc, _, _ = self._drive(driver)
                self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
                self.assertIn("verify-unparseable", proc.stderr)

    def test_an_unparseable_verify_on_an_in_progress_task_refuses(self):
        # D3 seventh amendment (3): `pending` or `in-progress` can refuse.
        for driver in self.DRIVERS:
            with self.subTest(driver=driver):
                self._stage(driver, _block("T1", "Do.", "true"),
                            _block("T2", "Do.", "", status="in-progress"))
                # codex rejects an empty verify on the SELECTED task itself (exit 2, existing
                # behaviour), so there the unreadable in-progress task is not the selected one.
                proc, _, _ = self._drive(
                    driver, ("--task", "T1" if driver == "codex" else "T2"))
                self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
                self.assertIn("verify-unparseable", proc.stderr)

    def test_an_unparseable_verify_on_done_or_blocked_never_refuses(self):
        # D3 seventh amendment (3): done/blocked findings are printed, never refuse a run.
        for status in ("done", "blocked"):
            for driver in self.DRIVERS:
                with self.subTest(driver=driver, status=status):
                    self._stage(driver, _block("T1", "Do.", "", status=status),
                                _block("T2", "Do.", "true"))
                    proc, _, _ = self._drive(driver)
                    self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                    self.assertIn("verify-unparseable", proc.stderr)  # still printed

    def test_warnings_leave_the_normal_dry_run_exit_code_unchanged(self):
        # D5: a warning-only kit exits exactly as a clean kit does.
        for driver in self.DRIVERS:
            with self.subTest(driver=driver):
                self._stage(driver, _block("T1", "Do.", "true"))
                clean, _, _ = self._drive(driver)
                self._stage(driver, _block("T1", "Do `bin/nope.py`.",
                                           "no-such-binary-xyz && python3 bin/missing.py"))
                warned, _, _ = self._drive(driver)
                self.assertEqual(warned.returncode, clean.returncode, warned.stderr)
                self.assertIn("verify-missing", warned.stderr)

    def test_the_reexport_is_the_contracts_own_object_and_sits_after_roster_for_run(self):
        # D5 / T5 acceptance: one call per driver, within 12 lines after `roster_for_run(`.
        sys.path.insert(0, str(ROOT / "bin"))
        try:
            for driver in self.DRIVERS:
                with self.subTest(driver=driver):
                    mod = importlib.import_module(f"{driver}_execute")
                    self.assertIs(mod.exit_if_unsound_kit, mod._CONTRACT.exit_if_unsound_kit)
                    self.assertEqual(mod._CONTRACT.exit_if_unsound_kit.__module__, "kit_contract")
                    lines = (ROOT / "bin" / f"{driver}_execute.py").read_text().splitlines()
                    calls = [i for i, l in enumerate(lines) if "exit_if_unsound_kit(kit, tasks, selected=args.task)" in l]
                    roster = [i for i, l in enumerate(lines) if "roster_for_run(plan_text" in l]
                    self.assertEqual(len(calls), 1)
                    self.assertTrue(any(0 < calls[0] - r <= 12 for r in roster), (calls, roster))
        finally:
            sys.path.remove(str(ROOT / "bin"))


class SelectedTaskGateTests(_KitFixture):
    """PLAN D5 as amended during T5: the task a run is told to run (`--task`) refuses on an
    unparseable verify whatever its status; a done/blocked task nobody selected still does not."""

    DRIVERS = ("claude", "copilot", "codex", "cursor")

    def _run(self, driver, t1_status, *extra):
        self.write_kit(_block("T1", "Do.", "", status=t1_status), _block("T2", "Do.", "true"))
        tasks_md = self.kit / "TASKS.md"
        tasks_md.write_text(tasks_md.read_text().replace(
            "- model: haiku", "- model: mid" if driver == "codex" else "- model: sonnet"))
        (self.kit / "PLAN.md").write_text("# fx plan\n")
        agents = self.root / ".claude" / "agents"
        agents.mkdir(parents=True, exist_ok=True)
        (agents / "fx-implementer.md").write_text(
            "---\nname: fx-implementer\ndescription: fixture\nmodel: sonnet\n---\n\nFixture.\n")
        home = self.root / "home"
        home.mkdir(exist_ok=True)
        before = self.snapshot()
        proc = subprocess.run(
            [sys.executable, str(Path(kc.__file__).resolve().parent / f"{driver}_execute.py"),
             "run", "--kit", str(self.kit), "--dry-run",
             "--attempt-store", str(self.root / "store"), *extra],
            capture_output=True, text=True, env=dict(os.environ, HOME=str(home)),
            cwd=str(self.root), timeout=120)
        self.assertEqual(self.snapshot(), before, f"{driver} changed the kit dir")
        return proc

    def _assert_refused(self, driver, proc):
        out = proc.stdout + proc.stderr
        self.assertNotIn("dispatch:", proc.stdout)
        if driver == "codex":
            # codex's older PolicyError guard fires before the gate for a falsy selected verify,
            # so its `selected=` wiring is unreachable for the selected task; that is expected.
            self.assertEqual(proc.returncode, 2, out)
            self.assertIn("has no runnable verify command", proc.stderr)
        else:
            self.assertEqual(proc.returncode, 3, out)
            self.assertIn("verify-unparseable", proc.stderr)

    def test_selecting_a_done_task_with_rerun_refuses_on_its_unreadable_verify(self):
        for driver in self.DRIVERS:
            with self.subTest(driver=driver):
                proc = self._run(driver, "done", "--task", "T1", "--rerun")
                self._assert_refused(driver, proc)

    def test_selecting_a_blocked_task_refuses_on_its_unreadable_verify(self):
        for driver in self.DRIVERS:
            with self.subTest(driver=driver):
                proc = self._run(driver, "blocked", "--task", "T1")
                self._assert_refused(driver, proc)

    def test_a_plain_run_of_a_sound_pending_task_beside_a_done_unreadable_one_still_runs(self):
        for driver in self.DRIVERS:
            with self.subTest(driver=driver):
                proc = self._run(driver, "done")
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn("verify-unparseable", proc.stderr)  # printed, not refused


if __name__ == "__main__":
    unittest.main()
