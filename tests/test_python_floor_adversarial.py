"""Adversarial coverage for tests/test_python_floor.py (aesop-fold kit, T2).

Authored from the T2 brief's acceptance criteria, not from reading
test_python_floor.py's implementation first. The brief pins several specifics a
plausible-but-wrong implementation could quietly miss while its own four named
tests still pass:

- the stale-claim sweep must walk all twelve declared roots, recursively
- it must scan exactly the seven declared file suffixes, no more, no less
- its regex has four alternation branches; each must independently trigger
- it must never scan `.claude/kits/`, `tasks/kits/`, `.claude/agents/`,
  `site-build/`, or `.git/`
- it must exclude only its own module file, by path, not the whole tests/ dir,
  and not merely because its own source happens to avoid the literal pattern
- the interpreter-floor check must be a real `>= (3, 11)` comparison, not
  vacuous
- `test_setup_md_declares_311_floor` must actually fail if the pinned row were
  reverted

Each test below builds a small synthetic tree under a fresh `mkdtemp()`
equivalent (`tempfile.TemporaryDirectory`), places a private copy of the real
tests/test_python_floor.py inside it (per GUARDRAILS' safe mutation recipe:
copy inputs to a temp dir, mutate the copy, point the code at the copy, expect
the result, then let the temp dir be removed automatically), and calls the
specific test method directly. The tracked repo is never mutated.

This file itself lives under tests/ and is therefore swept by the REAL
test_no_stale_floor_claims on every full-suite run. Every planted stale-floor
string below is therefore built by runtime concatenation of two half-strings
(mirroring the escaping discipline in test_python_floor.py's own regex
literal) so this module's own on-disk source never spells a contiguous
stale-floor string.
"""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
SWEEP_MODULE_PATH = REPO_ROOT / "tests" / "test_python_floor.py"

DIRECTORY_ROOTS = (
    "docs",
    "docs-src",
    "docs-site",
    "skills",
    "copilot",
    "codex",
    "copilot-docs",
    "bin",
    "tests",
)
FILE_ROOTS = ("README.md", "SETUP.md", "CLAUDE.md")

EXCLUDED_RELATIVE_DIRS = (
    ".claude/kits",
    "tasks/kits",
    ".claude/agents",
    "site-build",
    ".git",
)

VALID_SUFFIXES = (".md", ".py", ".toml", ".yaml", ".yml", ".json", ".txt")
NON_DECLARED_SUFFIX = ".rst"

# Split so this file's own source never spells a contiguous stale-floor
# string; see module docstring.
_STALE_PARTS = {
    "dotted_3_8_plus": ("polytropos requires python3 3.8", "+ or newer.\n"),
    "named_python_3_8": ("Built and tested against Python", " 3.8 originally.\n"),
    "dotted_3_10_plus": ("some other tool wants 3.10", "+ at minimum.\n"),
    "python_requires_eq": ("python_requires", " = \">=3.11\"\n"),
}


def _stale_text(label):
    a, b = _STALE_PARTS[label]
    return a + b


def _load_sweep_module(source_path):
    """Import a private copy of test_python_floor.py, isolated from
    sys.modules, without writing any __pycache__ bytecode cache anywhere
    (including next to the real tracked file when loaded directly)."""
    spec = importlib.util.spec_from_file_location(
        "_python_floor_under_test", str(source_path)
    )
    module = importlib.util.module_from_spec(spec)
    original_flag = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = original_flag
    return module


def _find_case(module, method_name):
    """Locate whichever unittest.TestCase subclass in the module exposes
    method_name, without assuming a specific class name (the brief pins test
    method names, not a class name)."""
    for obj in vars(module).values():
        if (
            isinstance(obj, type)
            and issubclass(obj, unittest.TestCase)
            and hasattr(obj, method_name)
        ):
            return obj(method_name)
    raise AssertionError(
        "no TestCase in %s exposes %s" % (getattr(module, "__file__", module), method_name)
    )


def _copy_module_into(tmp, mutate=None):
    """Copy the real sweep module into tmp/tests/test_python_floor.py so its
    own REPO_ROOT / SETUP_MD / self-exclusion all resolve relative to tmp,
    exactly per the brief's stated `REPO_ROOT = Path(__file__).resolve()
    .parents[1]` convention. Never touches the tracked file."""
    tests_dir = tmp / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    dest = tests_dir / "test_python_floor.py"
    text = SWEEP_MODULE_PATH.read_text(encoding="utf-8")
    if mutate is not None:
        text = mutate(text)
    dest.write_text(text, encoding="utf-8")
    return dest


class SweepRootCoverageTests(unittest.TestCase):
    """Brief item 4: 'walk these roots' names twelve specific roots. A sweep
    that silently skips one, or only looks at top-level files, would let a
    stale claim live there undetected."""

    def test_walks_every_declared_directory_root_recursively(self):
        for root_name in DIRECTORY_ROOTS:
            with self.subTest(root=root_name):
                with tempfile.TemporaryDirectory() as tmp_str:
                    tmp = Path(tmp_str)
                    module_copy = _copy_module_into(tmp)
                    nested = tmp / root_name / "a" / "b"
                    nested.mkdir(parents=True)
                    (nested / "deep.md").write_text(
                        _stale_text("named_python_3_8"), encoding="utf-8"
                    )
                    module = _load_sweep_module(module_copy)
                    case = _find_case(module, "test_no_stale_floor_claims")
                    with self.assertRaises(
                        AssertionError,
                        msg="sweep missed a claim nested two levels under %r" % root_name,
                    ):
                        case.test_no_stale_floor_claims()

    def test_walks_every_declared_file_root(self):
        for root_name in FILE_ROOTS:
            with self.subTest(root=root_name):
                with tempfile.TemporaryDirectory() as tmp_str:
                    tmp = Path(tmp_str)
                    module_copy = _copy_module_into(tmp)
                    (tmp / root_name).write_text(
                        _stale_text("named_python_3_8"), encoding="utf-8"
                    )
                    module = _load_sweep_module(module_copy)
                    case = _find_case(module, "test_no_stale_floor_claims")
                    with self.assertRaises(
                        AssertionError,
                        msg="sweep missed a claim written into file root %r" % root_name,
                    ):
                        case.test_no_stale_floor_claims()


class SuffixFilterTests(unittest.TestCase):
    """Brief item 4 pins the exact suffix set. Too narrow silently under-
    scans; too broad (e.g. no filter at all) is a different, unreported bug
    the brief also doesn't call for."""

    def test_each_declared_suffix_is_scanned(self):
        for suffix in VALID_SUFFIXES:
            with self.subTest(suffix=suffix):
                with tempfile.TemporaryDirectory() as tmp_str:
                    tmp = Path(tmp_str)
                    module_copy = _copy_module_into(tmp)
                    docs = tmp / "docs"
                    docs.mkdir()
                    (docs / ("note" + suffix)).write_text(
                        _stale_text("named_python_3_8"), encoding="utf-8"
                    )
                    module = _load_sweep_module(module_copy)
                    case = _find_case(module, "test_no_stale_floor_claims")
                    with self.assertRaises(
                        AssertionError, msg="suffix %r was not scanned" % suffix
                    ):
                        case.test_no_stale_floor_claims()

    def test_non_declared_suffix_is_not_scanned(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            module_copy = _copy_module_into(tmp)
            docs = tmp / "docs"
            docs.mkdir()
            (docs / ("note" + NON_DECLARED_SUFFIX)).write_text(
                _stale_text("named_python_3_8"), encoding="utf-8"
            )
            module = _load_sweep_module(module_copy)
            case = _find_case(module, "test_no_stale_floor_claims")
            case.test_no_stale_floor_claims()  # must not raise


class RegexAlternativeTests(unittest.TestCase):
    """Brief item 4 pins a four-alternative regex. A sweep whose pattern only
    covers one alternative (a plausible copy-paste slip) is a weak tripwire;
    each alternative is planted in isolation (no other alternative present in
    the same file) so a failure can only be attributed to that branch."""

    def test_each_regex_alternative_triggers_independently(self):
        for label in _STALE_PARTS:
            with self.subTest(pattern=label):
                with tempfile.TemporaryDirectory() as tmp_str:
                    tmp = Path(tmp_str)
                    module_copy = _copy_module_into(tmp)
                    docs = tmp / "docs"
                    docs.mkdir()
                    (docs / "note.md").write_text(_stale_text(label), encoding="utf-8")
                    module = _load_sweep_module(module_copy)
                    case = _find_case(module, "test_no_stale_floor_claims")
                    with self.assertRaises(
                        AssertionError, msg="regex alternative %r did not trigger" % label
                    ):
                        case.test_no_stale_floor_claims()


class ExclusionTests(unittest.TestCase):
    """Brief item 4: 'Do NOT scan .claude/kits/, tasks/kits/, or
    .claude/agents/ ... Do NOT scan site-build/ or .git/.' Historical kit
    records and build output must never be flagged even when they contain an
    old floor claim verbatim."""

    def test_declared_excluded_dirs_never_flagged(self):
        for rel in EXCLUDED_RELATIVE_DIRS:
            with self.subTest(excluded=rel):
                with tempfile.TemporaryDirectory() as tmp_str:
                    tmp = Path(tmp_str)
                    module_copy = _copy_module_into(tmp)
                    target = tmp / Path(rel) / "sub"
                    target.mkdir(parents=True)
                    (target / "old.md").write_text(
                        _stale_text("named_python_3_8"), encoding="utf-8"
                    )
                    module = _load_sweep_module(module_copy)
                    case = _find_case(module, "test_no_stale_floor_claims")
                    case.test_no_stale_floor_claims()  # must not raise


class SelfExclusionTests(unittest.TestCase):
    """Brief item 4: 'skip this test file itself.' test_python_floor.py's own
    regex literal is written with escapes so it never spells a contiguous
    stale-floor string — meaning the sweep might merely be passing on its own
    module by luck rather than by a real path-based exclusion. This class
    forces a genuine, unescaped match into a copy of the module's own source
    and checks whether it is still excluded (by identity/path), and that the
    exclusion is scoped to that one file, not the whole tests/ directory."""

    def test_self_file_excluded_even_with_a_literal_offending_match(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)

            def mutate(text):
                return "# stray note: " + _stale_text("named_python_3_8") + text

            module_copy = _copy_module_into(tmp, mutate=mutate)
            mutated_text = module_copy.read_text(encoding="utf-8")
            self.assertIn(
                _stale_text("named_python_3_8").strip(),
                mutated_text,
                "test setup bug: the mutation did not actually land",
            )
            module = _load_sweep_module(module_copy)
            case = _find_case(module, "test_no_stale_floor_claims")
            case.test_no_stale_floor_claims()  # must not raise

    def test_sibling_tests_file_is_not_exempted(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            module_copy = _copy_module_into(tmp)
            (module_copy.parent / "test_something_else.py").write_text(
                _stale_text("named_python_3_8"), encoding="utf-8"
            )
            module = _load_sweep_module(module_copy)
            case = _find_case(module, "test_no_stale_floor_claims")
            with self.assertRaises(
                AssertionError,
                msg="self-exclusion exempted a sibling tests/ file, not just its own module",
            ):
                case.test_no_stale_floor_claims()


class FloorChecksAreRealTests(unittest.TestCase):
    """Brief item 1: 'sys.version_info >= (3, 11), failure message naming
    SETUP.md and tomllib.' Brief item 2: import tomllib succeeds, 'fails with
    a clear message otherwise.' Both must be real checks, not vacuous ones
    that pass regardless of interpreter state."""

    def test_interpreter_check_fails_below_floor_with_named_message(self):
        module = _load_sweep_module(SWEEP_MODULE_PATH)
        case = _find_case(module, "test_interpreter_meets_documented_floor")
        with mock.patch("sys.version_info", (3, 10, 9)):
            with self.assertRaises(AssertionError) as ctx:
                case.test_interpreter_meets_documented_floor()
        message = str(ctx.exception)
        self.assertIn("SETUP.md", message)
        self.assertIn("tomllib", message)

    def test_interpreter_check_passes_at_exact_floor(self):
        module = _load_sweep_module(SWEEP_MODULE_PATH)
        case = _find_case(module, "test_interpreter_meets_documented_floor")
        with mock.patch("sys.version_info", (3, 11, 0)):
            case.test_interpreter_meets_documented_floor()  # must not raise

    def test_tomllib_check_fails_when_tomllib_unavailable(self):
        module = _load_sweep_module(SWEEP_MODULE_PATH)
        case = _find_case(module, "test_tomllib_importable")
        with mock.patch.dict(sys.modules, {"tomllib": None}):
            with self.assertRaises(AssertionError):
                case.test_tomllib_importable()


class SetupMdDeclarationTests(unittest.TestCase):
    """Brief item 3, and the mission's specific question: does
    test_setup_md_declares_311_floor actually fail if the pinned row were
    reverted to its old, superseded floor text, rather than passing
    regardless of SETUP.md's content?"""

    def test_fails_if_pinned_row_is_reverted(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            module_copy = _copy_module_into(tmp)
            reverted = (
                "| `python3` (3.8"
                + "+) | polytropos \N{EM DASH} **stdlib-only**, "
                "nothing to `pip install` |\n"
            )
            (tmp / "SETUP.md").write_text(reverted, encoding="utf-8")
            module = _load_sweep_module(module_copy)
            case = _find_case(module, "test_setup_md_declares_311_floor")
            with self.assertRaises(AssertionError):
                case.test_setup_md_declares_311_floor()

    def test_passes_with_the_correct_pinned_row(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            module_copy = _copy_module_into(tmp)
            correct = (
                "| `python3` (3.11+) | polytropos \N{EM DASH} **stdlib-only**, "
                "nothing to `pip install`; 3.11 is the floor because the stdlib "
                "TOML parser (`tomllib`) arrived there |\n"
            )
            (tmp / "SETUP.md").write_text(correct, encoding="utf-8")
            module = _load_sweep_module(module_copy)
            case = _find_case(module, "test_setup_md_declares_311_floor")
            case.test_setup_md_declares_311_floor()  # must not raise


if __name__ == "__main__":
    unittest.main()
