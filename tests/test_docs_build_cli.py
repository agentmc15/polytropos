"""Adversarial tests for bin/docs_build.py's build/check CLI layer (T5).

Derived from the T5 brief in .claude/kits/docs-site/TASKS.md ("### T5 -- build/check
CLI, first real build, drift + nav + link tests"), PLAN.md D2/D3/D4, and the P1
carry-forward F3 in NOTES.md ("T5 must land real argparse exit codes... unknown
subcommand -> non-zero") -- written from the BRIEF's pinned CLI contract, not from
reading bin/docs_build.py's implementation first.

Scope is deliberately the CLI surface only: argparse `build`/`check` subcommands,
`--repo-root`, exit codes 0/1/2, the stale-vs-unknown drift distinction (missing vs.
differing vs. an orphan file under a generator-owned root), byte-stability
(UTF-8/LF/one trailing newline), build/build idempotence, the printed rebuild-remedy
line, and repo-root isolation. The render-function unit tests already live in
tests/test_docs_build.py and tests/test_docs_build_adversarial.py; the live-tree
drift/nav/link/context-leak groups live in tests/test_docs_site.py -- this file does
not duplicate either.

bin/ is not a package; docs_build.py is loaded via importlib by absolute path, the
repo's established `_load` idiom (see tests/test_harness_select.py). Every fixture is
either a from-scratch synthetic repo under tempfile.TemporaryDirectory() or a temp
COPY of real source directories (the GUARDRAILS.md temp-copy recipe) -- nothing here
ever writes to a tracked file, and `main([...])` is always invoked in-process, never
as a subprocess.
"""

import contextlib
import importlib.util
import io
import shutil
import tempfile
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


db = _load("docs_build")


def _write_skill(root, harness_dir, name, description, body="Body text.\n"):
    """Create <root>/<harness_dir>/<name>/SKILL.md with a flat name/description
    frontmatter block and the given body."""
    skill_dir = Path(root) / harness_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    content = f"---\nname: {name}\ndescription: {description}\n---\n\n{body}"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return skill_dir


def _make_minimal_repo(tmp_path):
    """The smallest fixture that satisfies skill_inventory's 'every harness root
    exists, every immediate subdir is a valid skill' rule: one skill, named
    'alpha', present in all three harnesses. Yields exactly 8 expected pages: 3
    skill pages + 3 harness index pages + 1 parity page + 1 deep-dives/index.md
    (T6: expected_pages() always emits the deep-dive index, even with an empty
    table, since this fixture has no docs/ dir at all). docs-site/ does not
    exist yet under this root -- a fresh build must mkdir -p it."""
    root = Path(tmp_path)
    _write_skill(root, "skills", "alpha", "Alpha skill for Claude Code.")
    _write_skill(root, "copilot/.github/skills", "alpha", "Alpha skill for Copilot CLI.")
    _write_skill(root, "codex/skills", "alpha", "Alpha skill for Codex CLI.")
    return root


def _copy_real_dirs(tmp_path, names):
    """Copy the named real repo directories into tmp_path (the GUARDRAILS.md
    temp-copy recipe) -- never mutates anything under REPO_ROOT itself."""
    dest = Path(tmp_path)
    for name in names:
        shutil.copytree(REPO_ROOT / name, dest / name)
    return dest


def _run_main(argv):
    """Invoke db.main(argv) in-process, capturing stdout/stderr, and return
    (exit_code, stdout_text, stderr_text). argparse itself calls sys.exit() on an
    unrecognized subcommand or flag, which raises SystemExit rather than
    returning a value -- that path is normalized here too so every caller gets a
    uniform (code, out, err) triple."""
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = db.main(argv)
    except SystemExit as exc:
        code = exc.code
    return code, out.getvalue(), err.getvalue()


class SourceErrorExitCodeTests(unittest.TestCase):
    """Brief: 'exit 2 on any source error (inventory/fragment ValueError -- print
    the message to stderr...)' -- for BOTH build and check."""

    def _make_broken_repo(self, tmp_path):
        root = _make_minimal_repo(tmp_path)
        # Frontmatter `name` no longer matches the directory name -- the
        # canonical inventory ValueError the brief names as its example.
        skill_md = root / "skills" / "alpha" / "SKILL.md"
        skill_md.write_text(
            "---\nname: mismatched\ndescription: Alpha skill for Claude Code.\n---\n\nBody text.\n",
            encoding="utf-8",
        )
        return root

    def test_build_exits_2_on_source_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_broken_repo(tmp)
            code, out, err = _run_main(["build", "--repo-root", str(root)])
            self.assertEqual(code, 2)
            self.assertTrue(err.strip(), "expected an error message on stderr")

    def test_check_exits_2_on_source_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_broken_repo(tmp)
            code, out, err = _run_main(["check", "--repo-root", str(root)])
            self.assertEqual(code, 2)
            self.assertTrue(err.strip(), "expected an error message on stderr")


class FragmentSourceErrorExitCodeTests(unittest.TestCase):
    """Brief explicitly names BOTH 'inventory' and 'fragment' ValueError as the
    exit-2 source-error class -- a malformed skill covers the former; an orphan
    fragment (matching no inventory record) covers the latter."""

    def _make_repo_with_orphan_fragment(self, tmp_path):
        root = _make_minimal_repo(tmp_path)
        orphan = root / "docs-src" / "fragments" / "skills" / "claude" / "ghost.md"
        orphan.parent.mkdir(parents=True, exist_ok=True)
        orphan.write_text("### Ghost\n\nNo such skill exists.\n", encoding="utf-8")
        return root

    def test_orphan_fragment_causes_exit_2_on_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_repo_with_orphan_fragment(tmp)
            code, out, err = _run_main(["build", "--repo-root", str(root)])
            self.assertEqual(code, 2)
            self.assertTrue(err.strip())

    def test_orphan_fragment_causes_exit_2_on_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_repo_with_orphan_fragment(tmp)
            code, out, err = _run_main(["check", "--repo-root", str(root)])
            self.assertEqual(code, 2)
            self.assertTrue(err.strip())


class UnknownSubcommandTests(unittest.TestCase):
    """NOTES.md F3: 'T5 must land real argparse exit codes (unknown subcommand ->
    non-zero)' -- the T1 stub main() exited 0 for any argv; this is the
    regression guard for that carry-forward fix."""

    def test_unknown_subcommand_exits_nonzero(self):
        code, out, err = _run_main(["frobnicate"])
        self.assertNotEqual(code, 0)

    def test_missing_subcommand_exits_nonzero(self):
        code, out, err = _run_main([])
        self.assertNotEqual(code, 0)


class CheckUnknownFileTests(unittest.TestCase):
    """Brief: check 'ALSO scan[s] the generator-owned roots... for files NOT in
    the expected set -> report as `unknown` (drift)'."""

    def test_unknown_file_under_generated_root_is_reported_and_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_minimal_repo(tmp)
            code, out, err = _run_main(["build", "--repo-root", str(root)])
            self.assertEqual(code, 0)

            orphan = root / "docs-site" / "skills" / "not-generated.md"
            orphan.write_text("hand-written orphan, never produced by the generator\n", encoding="utf-8")

            code, out, err = _run_main(["check", "--repo-root", str(root)])
            self.assertEqual(code, 1)
            self.assertIn("docs-site/skills/not-generated.md", err)
            self.assertIn("unknown", err.lower())
            self.assertIn("python3 bin/docs_build.py build", err)


class CheckMissingPageTests(unittest.TestCase):
    """Brief: 'check exit 1 when an expected page is MISSING (not just
    differing)' -- byte-compare treats missing and differing both as 'stale',
    but a missing page must still be caught, not silently skipped because
    there's nothing on disk to compare against."""

    def test_missing_expected_page_is_stale_and_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_minimal_repo(tmp)
            _run_main(["build", "--repo-root", str(root)])

            missing = root / "docs-site" / "skills" / "claude" / "alpha.md"
            self.assertTrue(missing.is_file())
            missing.unlink()

            code, out, err = _run_main(["check", "--repo-root", str(root)])
            self.assertEqual(code, 1)
            self.assertIn("docs-site/skills/claude/alpha.md", err)
            self.assertIn("stale", err.lower())
            self.assertIn("python3 bin/docs_build.py build", err)


class CheckDifferingPageTests(unittest.TestCase):
    """The other half of 'missing or differing -> stale': a page that exists but
    whose bytes no longer match expected_pages() must also be caught."""

    def test_differing_page_is_stale_and_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_minimal_repo(tmp)
            _run_main(["build", "--repo-root", str(root)])

            page = root / "docs-site" / "skills" / "claude" / "alpha.md"
            page.write_bytes(page.read_bytes() + b"\nhand-edited, never rebuilt\n")

            code, out, err = _run_main(["check", "--repo-root", str(root)])
            self.assertEqual(code, 1)
            self.assertIn("docs-site/skills/claude/alpha.md", err)


class CheckNeverBuiltTreeTests(unittest.TestCase):
    """A fixture that has never been built at all (docs-site/ does not exist):
    every expected page is missing, so check must report drift, not crash."""

    def test_check_before_any_build_reports_missing_pages_and_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_minimal_repo(tmp)
            self.assertFalse((root / "docs-site").exists())

            code, out, err = _run_main(["check", "--repo-root", str(root)])
            self.assertEqual(code, 1)
            for rel in (
                "docs-site/skills/index.md",
                "docs-site/skills/claude/index.md",
                "docs-site/skills/claude/alpha.md",
            ):
                self.assertIn(rel, err)


class ByteStabilityTests(unittest.TestCase):
    """Brief/GUARDRAILS: generated bytes are 'UTF-8, LF, one trailing newline' --
    checked on every page a fresh build actually writes."""

    def test_every_written_page_is_utf8_lf_single_trailing_newline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_minimal_repo(tmp)
            code, out, err = _run_main(["build", "--repo-root", str(root)])
            self.assertEqual(code, 0)

            pages = sorted((root / "docs-site").rglob("*.md"))
            self.assertEqual(len(pages), 8)
            for path in pages:
                raw = path.read_bytes()
                text = raw.decode("utf-8")  # must not raise UnicodeDecodeError
                self.assertNotIn(b"\r", raw, f"{path} contains a CR byte")
                self.assertTrue(text.endswith("\n"), f"{path} is missing its trailing newline")
                self.assertFalse(text.endswith("\n\n"), f"{path} has more than one trailing newline")


class IdempotentDoubleBuildTests(unittest.TestCase):
    """Brief: 'build twice -> unchanged N on the second run (idempotent,
    byte-stable)', exercised here on the minimal synthetic fixture (N=8, T6:
    the always-present deep-dives/index.md joins the 7 T5-era pages)."""

    def test_second_build_reports_all_unchanged_and_bytes_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_minimal_repo(tmp)

            code1, out1, err1 = _run_main(["build", "--repo-root", str(root)])
            self.assertEqual(code1, 0)
            self.assertIn("written 8 / unchanged 0", out1)

            before = {p: p.read_bytes() for p in sorted((root / "docs-site").rglob("*.md"))}
            self.assertEqual(len(before), 8)

            code2, out2, err2 = _run_main(["build", "--repo-root", str(root)])
            self.assertEqual(code2, 0)
            self.assertIn("written 0 / unchanged 8", out2)

            after = {p: p.read_bytes() for p in before}
            self.assertEqual(before, after, "second build must not change any byte of any page")


class RealTreeIdempotenceTests(unittest.TestCase):
    """Runs the CLI against a temp COPY of the real sources (skills/,
    copilot/.github/skills/, codex/skills/, docs/), with no docs-site/ output
    copied in, proving the brief's 'build twice -> unchanged N' claim against
    the FULL real roster -- never writing to a tracked file. T5 pinned this at
    43 (39 skill pages + 3 harness indexes + 1 parity page); T6 extends the set
    with 25 deep-dive pages (24 docs/*.md mirrors + 1 index), for 68 total --
    this test derives the count dynamically so it stays meaningful if that
    changes again."""

    def test_build_twice_on_the_full_real_roster(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _copy_real_dirs(tmp, ("skills", "copilot", "codex", "docs"))
            expected_count = len(db.expected_pages(root))
            self.assertEqual(expected_count, 68, "T6's pinned page-set size (68 total)")

            code1, out1, err1 = _run_main(["build", "--repo-root", str(root)])
            self.assertEqual(code1, 0, f"stderr={err1!r}")
            self.assertIn(f"written {expected_count} / unchanged 0", out1)

            code2, out2, err2 = _run_main(["build", "--repo-root", str(root)])
            self.assertEqual(code2, 0, f"stderr={err2!r}")
            self.assertIn(f"unchanged {expected_count}", out2)
            self.assertIn("written 0", out2)


class MutationProbeRecipeTests(unittest.TestCase):
    """Replicates the exact GUARDRAILS.md / T5-verify-command temp-copy mutation
    probe in-process (main([...]) rather than a subprocess): copy the real
    skills/copilot/codex/docs/docs-src/docs-site trees (T6: docs/ must be copied
    too, so the copied docs-site/deep-dives/*.md output matches what
    expected_pages() re-derives from the copied docs/ sources; T7: docs-src/
    must be copied too, once fragments exist, so the copied tree's re-derived
    skill/harness-index/parity pages include their spliced '## In practice' /
    '## Using these skills' / '## Why the rosters differ' sections and match
    the committed docs-site/ output -- this is GUARDRAILS.md's own canonical
    drift-probe recipe, `cp -R skills copilot codex docs docs-src docs-site
    bin`), append text to one real SKILL.md's COPY, and confirm `check
    --repo-root <temp>` reports drift and prints the rebuild remedy -- never
    touching the real tree."""

    def test_mutating_a_copied_skill_makes_check_report_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _copy_real_dirs(tmp, ("skills", "copilot", "codex", "docs", "docs-src", "docs-site"))

            # Sanity: the copied tree starts fresh, matching the real committed
            # docs-site/ output, before we mutate anything.
            pre_code, _, pre_err = _run_main(["check", "--repo-root", str(root)])
            self.assertEqual(pre_code, 0, f"expected the unmodified copy to be fresh; stderr={pre_err!r}")

            route_skill = root / "skills" / "route" / "SKILL.md"
            with route_skill.open("a", encoding="utf-8") as fh:
                fh.write("\nmutation-probe\n")

            code, out, err = _run_main(["check", "--repo-root", str(root)])
            self.assertEqual(code, 1)
            self.assertIn("python3 bin/docs_build.py build", err)


class RepoRootIsolationTests(unittest.TestCase):
    """Brief: `--repo-root PATH` (default REPO_ROOT). check_site is read-only, so
    it is safe to invoke the default directly against the real repo; build is
    exercised only against a wholly synthetic temp fixture, and the real
    committed page bytes are diffed before/after to prove isolation."""

    def test_default_repo_root_check_runs_against_the_real_committed_tree(self):
        # No --repo-root supplied. If this ever regresses to defaulting at cwd
        # (or anywhere else) instead of REPO_ROOT, this would spuriously fail
        # or pass for the wrong reason depending on test-runner cwd -- the
        # value of this test is that it currently must exit 0 against a repo
        # we independently know (via `python3 bin/docs_build.py check`, see the
        # verify-command output in this report) to be fresh.
        code, out, err = _run_main(["check"])
        self.assertEqual(code, 0, f"expected the committed tree to already be fresh; stderr={err!r}")

    def test_pointing_at_a_temp_fixture_never_touches_the_real_tree(self):
        real_index = REPO_ROOT / "docs-site" / "skills" / "index.md"
        before = real_index.read_bytes()

        with tempfile.TemporaryDirectory() as tmp:
            root = _make_minimal_repo(tmp)
            code, out, err = _run_main(["build", "--repo-root", str(root)])
            self.assertEqual(code, 0)
            self.assertTrue((root / "docs-site" / "skills" / "index.md").is_file())

        after = real_index.read_bytes()
        self.assertEqual(before, after, "the real committed page must be byte-identical after a --repo-root build elsewhere")


if __name__ == "__main__":
    unittest.main()
