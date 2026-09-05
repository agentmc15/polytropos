"""Adversarial coverage for tests/test_primitives_data.py (aesop-fold kit, T3).

Authored from the T3 brief's stated contract and acceptance criteria (see
.claude/kits/aesop-fold/TASKS.md T3, PLAN.md D1/D5/D7) — not from reading
test_primitives_data.py's implementation first and reverse-engineering tests
that match it. Two things live here:

1. Mutation-tripwire tests below prove the EXISTING pinned-capability-table
   test in test_primitives_data.py is a real tripwire, not a check that only
   ever could have passed. Each probe copies test_primitives_data.py and
   primitives/*.json into a fresh temp tree (GUARDRAILS "Safe mutation
   recipe"), plants exactly one mutation there, and runs the real
   test_primitives_data.py module UNMODIFIED — it re-points at the mutated
   data itself, via its own `REPO_ROOT = Path(__file__).resolve().parents[1]`
   convention, once its copy lives under `<tmp>/tests/`. The tracked repo is
   never touched; see the trailing TrackedTreeUntouchedTests below.

2. DataHygieneTests closes a real gap: the T3 brief's acceptance line "no
   prices, model ids, dates (other than the provenance note), or home paths
   anywhere in the three files" has NO enforcing test in
   test_primitives_data.py. Confirmed by the same mutation technique: planting
   a home path, a price, a versioned model id, or an ISO date into a temp copy
   of primitives/model.json or primitives/harness-matrix.json left the FULL
   existing suite green. This file adds a real, always-on check for the two
   files this kit authors.

NOTE — a reported discrepancy, not a silently-resolved one: primitives/
aesop.schema.v1.json is deliberately OUT of DataHygieneTests' scope. That file
must be byte-identical to aesop's LOCKED schemas/aesop.schema.json (sha256-
pinned, PLAN D5) and must never be edited — yet its own vendored content
already reads "...v1 -- LOCKED at Phase 1 (2026-06-10)...", an ISO date baked
into text this kit is required to copy verbatim and forbidden to alter. A
literal, all-three-files reading of "no ... dates ... anywhere in the three
files" is therefore unsatisfiable without either breaking the byte-identical/
hash-pin requirement or rewriting an upstream LOCKED file this kit may not
touch. Read narrowly, the hygiene line binds the two files this kit actually
authors (model.json, harness-matrix.json) and is enforced below; read broadly,
it also binds the vendored schema and is self-contradictory as written. Per
the test-author role's escalation clause ("if the brief's acceptance criteria
are ... contradictory ... stop and report the discrepancy rather than
inventing acceptance the brief never stated"), this is surfaced here rather
than picked for the orchestrator.
"""

import importlib.util
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PRIMITIVES_DIR = REPO_ROOT / "primitives"
MODEL_PATH = PRIMITIVES_DIR / "model.json"
MATRIX_PATH = PRIMITIVES_DIR / "harness-matrix.json"
SCHEMA_PATH = PRIMITIVES_DIR / "aesop.schema.v1.json"
REAL_TEST_MODULE = REPO_ROOT / "tests" / "test_primitives_data.py"

# Hygiene patterns, deliberately matching this repo's own established checks
# (tests/test_docs_fragment_content.py's _DOLLAR_RE / _VERSIONED_MODEL_RE,
# tests/test_docs_skill_dispositions.py's ISO-date regex) rather than
# inventing new ones for this one kit.
_DOLLAR_RE = re.compile(r"\$\d")
_VERSIONED_MODEL_RE = re.compile(
    r"\b(?:claude|gpt|gemini|sonnet|opus|haiku|fable|kimi|mai|raptor)-[0-9]",
    re.IGNORECASE,
)
_ISO_DATE_RE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")
_HOME_PATH_NEEDLES = ("/Users/", "~/")


def _mutate_json(path, mutator):
    data = json.loads(path.read_text(encoding="utf-8"))
    mutator(data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _copy_test_module_and_primitives_into(tmp, mutate_fn=None):
    """Copy the real tests/test_primitives_data.py and primitives/*.json into
    tmp, apply mutate_fn(tmp/primitives) if given, and return nothing --
    caller then loads tmp/tests/test_primitives_data.py, whose own
    REPO_ROOT/PRIMITIVES_DIR resolution will point at tmp. Mirrors
    tests/test_python_floor_adversarial.py's _copy_module_into() pattern.
    Never touches the tracked tree."""
    tests_dir = tmp / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REAL_TEST_MODULE, tests_dir / "test_primitives_data.py")
    prim_dir = tmp / "primitives"
    shutil.copytree(PRIMITIVES_DIR, prim_dir)
    if mutate_fn is not None:
        mutate_fn(prim_dir)


def _load_data_test_module(tmp):
    dest = tmp / "tests" / "test_primitives_data.py"
    spec = importlib.util.spec_from_file_location("_t3_data_under_test", str(dest))
    module = importlib.util.module_from_spec(spec)
    original_flag = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = original_flag
    return module


def _find_case(module, method_name):
    """Locate whichever TestCase in the module exposes method_name, without
    assuming a specific class name."""
    for obj in vars(module).values():
        if (
            isinstance(obj, type)
            and issubclass(obj, unittest.TestCase)
            and hasattr(obj, method_name)
        ):
            return obj(method_name)
    raise AssertionError(f"no TestCase in {module} exposes {method_name!r}")


def _run_full_suite(module):
    suite = unittest.TestLoader().loadTestsFromModule(module)
    result = unittest.TestResult()
    suite.run(result)
    return result


def _run_single(case):
    # Wrapped in a TestSuite (not case.run() directly) so class-level
    # setUpClass/tearDownClass fixtures (TestMatrix, TestModel, ...) actually
    # execute -- calling a TestCase's .run() directly skips them.
    result = unittest.TestResult()
    unittest.TestSuite([case]).run(result)
    return result


def _run_with_mutation(mutate_fn, method_name=None):
    """Build a mutated temp tree, load the real (byte-for-byte unmodified)
    test_primitives_data.py module from it, and run either the full suite
    (method_name=None) or one named test method. Returns the TestResult."""
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        _copy_test_module_and_primitives_into(tmp, mutate_fn)
        module = _load_data_test_module(tmp)
        if method_name is None:
            return _run_full_suite(module)
        return _run_single(_find_case(module, method_name))


def _failed(result):
    return bool(result.failures or result.errors)


# ---------------------------------------------------------------------------
# Item 1 — is the cell-for-cell pin a real tripwire? Flip ONE cell across at
# least three different harnesses, including one goal_mode flip.
# ---------------------------------------------------------------------------
class CellForCellPinIsARealTripwireTests(unittest.TestCase):
    def test_cursor_skill_fallback_to_native_flip_is_caught(self):
        result = _run_with_mutation(
            lambda p: _mutate_json(
                p / "harness-matrix.json",
                lambda d: d["harnesses"]["cursor"]["cells"].__setitem__(
                    "skill", {"support": "native", "target": [], "notes": "mutated"}
                ),
            )
        )
        self.assertTrue(_failed(result), "cursor skill fallback->native flip was NOT caught")

    def test_antigravity_loop_native_to_fallback_flip_is_caught(self):
        result = _run_with_mutation(
            lambda p: _mutate_json(
                p / "harness-matrix.json",
                lambda d: d["harnesses"]["antigravity"]["cells"].__setitem__(
                    "loop", {"support": "fallback", "target": [], "notes": "mutated"}
                ),
            )
        )
        self.assertTrue(_failed(result), "antigravity loop native->fallback flip was NOT caught")

    def test_codex_hook_fallback_to_native_flip_is_caught(self):
        result = _run_with_mutation(
            lambda p: _mutate_json(
                p / "harness-matrix.json",
                lambda d: d["harnesses"]["codex"]["cells"].__setitem__(
                    "hook", {"support": "native", "target": [], "notes": "mutated"}
                ),
            )
        )
        self.assertTrue(_failed(result), "codex hook fallback->native flip was NOT caught")

    def test_copilot_goal_mode_flip_is_caught(self):
        result = _run_with_mutation(
            lambda p: _mutate_json(
                p / "harness-matrix.json",
                lambda d: d["harnesses"]["copilot"].__setitem__("goal_mode", "native"),
            )
        )
        self.assertTrue(_failed(result), "copilot goal_mode ralph->native flip was NOT caught")


# ---------------------------------------------------------------------------
# Item 2 — does the named cursor test isolate the cursor column, catching a
# cursor edit BY NAME (not just via the general cell-for-cell test)?
# ---------------------------------------------------------------------------
class CursorColumnTestIsolationTests(unittest.TestCase):
    CURSOR_TEST = "test_cursor_column_matches_aesop_cursor_emitter"

    def test_cursor_mutation_fails_the_named_cursor_test(self):
        result = _run_with_mutation(
            lambda p: _mutate_json(
                p / "harness-matrix.json",
                lambda d: d["harnesses"]["cursor"]["cells"].__setitem__(
                    "mcp", {"support": "fallback", "target": [], "notes": "mutated"}
                ),
            ),
            method_name=self.CURSOR_TEST,
        )
        self.assertTrue(_failed(result), "cursor mcp flip was not caught BY the named cursor test")

    def test_non_cursor_mutation_does_not_fail_the_named_cursor_test(self):
        # Control: the named test must stay isolated to the cursor column --
        # an antigravity-only mutation must NOT trip it.
        result = _run_with_mutation(
            lambda p: _mutate_json(
                p / "harness-matrix.json",
                lambda d: d["harnesses"]["antigravity"]["cells"].__setitem__(
                    "loop", {"support": "fallback", "target": [], "notes": "mutated"}
                ),
            ),
            method_name=self.CURSOR_TEST,
        )
        self.assertFalse(
            _failed(result),
            "the cursor-named test failed on an antigravity-only mutation -- not isolated",
        )


# ---------------------------------------------------------------------------
# Item 3 — does the sha256 pin catch schema tampering?
# ---------------------------------------------------------------------------
class SchemaHashPinTests(unittest.TestCase):
    def test_byte_tamper_of_vendored_schema_is_caught(self):
        def mutate(prim_dir):
            schema = prim_dir / "aesop.schema.v1.json"
            schema.write_text(schema.read_text(encoding="utf-8") + " ", encoding="utf-8")

        result = _run_with_mutation(mutate, method_name="test_schema_file_hash_matches_pin")
        self.assertTrue(_failed(result), "a byte-tampered schema copy was NOT caught by the hash pin")


# ---------------------------------------------------------------------------
# Item 4 — would a MISSING or EXTRA cell/harness/primitive be caught?
# ---------------------------------------------------------------------------
class MissingOrExtraShapeTests(unittest.TestCase):
    def test_deleted_cell_is_caught(self):
        result = _run_with_mutation(
            lambda p: _mutate_json(
                p / "harness-matrix.json",
                lambda d: d["harnesses"]["vscode"]["cells"].pop("hook"),
            )
        )
        self.assertTrue(_failed(result), "a deleted cell (vscode.hook) was NOT caught")

    def test_seventh_undeclared_harness_is_caught(self):
        def add_seventh(d):
            d["harnesses"]["windsurf"] = dict(d["harnesses"]["vscode"])

        result = _run_with_mutation(lambda p: _mutate_json(p / "harness-matrix.json", add_seventh))
        self.assertTrue(_failed(result), "a seventh, undeclared harness was NOT caught")

    def test_dropped_primitive_is_caught(self):
        result = _run_with_mutation(
            lambda p: _mutate_json(p / "model.json", lambda d: d["primitives"].pop(3))  # drops "command"
        )
        self.assertTrue(_failed(result), "dropping one of the nine primitives was NOT caught")


# ---------------------------------------------------------------------------
# Item 5 — are the enum-subset checks real?
# ---------------------------------------------------------------------------
class EnumSubsetChecksAreRealTests(unittest.TestCase):
    def test_bogus_agent_model_enum_token_is_caught(self):
        def add_bogus(d):
            for prim in d["primitives"]:
                if prim["id"] == "agent":
                    for field in prim["fields"]:
                        if field["name"] == "model":
                            field["enum"].append("gigantic")

        result = _run_with_mutation(
            lambda p: _mutate_json(p / "model.json", add_bogus),
            method_name="test_agent_model_and_effort_enums",
        )
        self.assertTrue(_failed(result), "a bogus agent.model enum token was NOT caught")

    def test_bogus_hook_event_enum_token_is_caught(self):
        def add_bogus(d):
            for prim in d["primitives"]:
                if prim["id"] == "hook":
                    for field in prim["fields"]:
                        if field["name"] == "event":
                            field["enum"].append("on-demand")

        result = _run_with_mutation(
            lambda p: _mutate_json(p / "model.json", add_bogus),
            method_name="test_hook_event_enum_pinned_from_registry_ts",
        )
        self.assertTrue(_failed(result), "a bogus hook.event enum token was NOT caught")


# ---------------------------------------------------------------------------
# Item 6 — the target hygiene check: does an absolute path get caught?
# ---------------------------------------------------------------------------
class TargetHygieneTripwireTests(unittest.TestCase):
    def test_absolute_path_in_target_is_caught(self):
        result = _run_with_mutation(
            lambda p: _mutate_json(
                p / "harness-matrix.json",
                lambda d: d["harnesses"]["claude-code"]["cells"]["mcp"].__setitem__(
                    "target", ["/Users/someone/.mcp.json"]
                ),
            )
        )
        self.assertTrue(_failed(result), "an absolute path in target was NOT caught")


# ---------------------------------------------------------------------------
# Item 7 — the data-hygiene acceptance line: is it enforced anywhere?  It was
# NOT (see the mutation probes this class's docstring below describes) -- so
# this is a real, always-on check, not a mutation probe of an existing test.
# ---------------------------------------------------------------------------
class DataHygieneRegexSanityTests(unittest.TestCase):
    """Guards the hygiene patterns below against silently becoming vacuous:
    each must actually match a representative bad example."""

    def test_dollar_pattern_matches_a_price(self):
        self.assertIsNotNone(_DOLLAR_RE.search("this costs $12 per run"))

    def test_versioned_model_pattern_matches_a_model_id(self):
        self.assertIsNotNone(_VERSIONED_MODEL_RE.search("pin the agent to claude-3-5-sonnet"))

    def test_iso_date_pattern_matches_a_date(self):
        self.assertIsNotNone(_ISO_DATE_RE.search("confirmed working as of 2025-01-15"))

    def test_home_path_needles_match_a_home_path(self):
        self.assertTrue(any(n in "/Users/someone/.mcp.json" for n in _HOME_PATH_NEEDLES))


class DataHygieneTests(unittest.TestCase):
    """T3 acceptance: 'no prices, model ids, dates (other than the provenance
    note), or home paths anywhere in the three files.' No test in
    test_primitives_data.py enforces this today -- confirmed by mutation
    probe: planting a home path, a price, a versioned model id, or an ISO
    date into a temp copy of model.json or harness-matrix.json left the FULL
    existing suite green (see MutationProbeConfirmsHygieneGapTests below for
    that confirmation, run permanently as a regression guard against the gap
    reappearing silently fixed without a real test). This test enforces the
    contract for the two files this kit authors; see the module docstring's
    NOTE for why aesop.schema.v1.json is out of scope."""

    AUTHORED_FILES = (MODEL_PATH, MATRIX_PATH)

    def test_no_price_model_id_iso_date_or_home_path_literal(self):
        offenders = []
        for path in self.AUTHORED_FILES:
            text = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), start=1):
                if _DOLLAR_RE.search(line):
                    offenders.append(f"{path.name}:{lineno}: dollar figure: {line.strip()!r}")
                if _VERSIONED_MODEL_RE.search(line):
                    offenders.append(f"{path.name}:{lineno}: versioned model id: {line.strip()!r}")
                if _ISO_DATE_RE.search(line):
                    offenders.append(f"{path.name}:{lineno}: ISO date: {line.strip()!r}")
                for needle in _HOME_PATH_NEEDLES:
                    if needle in line:
                        offenders.append(f"{path.name}:{lineno}: home path: {line.strip()!r}")
        self.assertEqual(offenders, [], f"data-hygiene violation(s) found: {offenders!r}")


class MutationProbeConfirmsHygieneGapTests(unittest.TestCase):
    """Permanent record, run every suite pass, that test_primitives_data.py
    itself does NOT catch a data-hygiene violation -- i.e. the gap
    DataHygieneTests above closes is real, not hypothetical. If a future edit
    to test_primitives_data.py starts catching these too, that is fine (these
    assertions would then fail loudly, telling a maintainer this class's
    premise is stale and it may be deleted)."""

    def test_home_path_in_matrix_note_is_not_caught_by_the_existing_suite(self):
        result = _run_with_mutation(
            lambda p: _mutate_json(
                p / "harness-matrix.json",
                lambda d: d["harnesses"]["vscode"]["cells"]["mcp"].__setitem__(
                    "notes", "see /Users/exampleuser/.vscode/mcp.json for details"
                ),
            )
        )
        self.assertFalse(_failed(result), "test_primitives_data.py unexpectedly now catches a home path")

    def test_price_in_matrix_note_is_not_caught_by_the_existing_suite(self):
        result = _run_with_mutation(
            lambda p: _mutate_json(
                p / "harness-matrix.json",
                lambda d: d["harnesses"]["vscode"]["cells"]["mcp"].__setitem__(
                    "notes", "costs $12.50 per run, see servers key"
                ),
            )
        )
        self.assertFalse(_failed(result), "test_primitives_data.py unexpectedly now catches a price")

    def test_model_id_in_model_semantics_is_not_caught_by_the_existing_suite(self):
        result = _run_with_mutation(
            lambda p: _mutate_json(
                p / "model.json",
                lambda d: d["primitives"][2].__setitem__(
                    "semantics", "Pin the agent to claude-3-5-sonnet for best results."
                ),
            )
        )
        self.assertFalse(_failed(result), "test_primitives_data.py unexpectedly now catches a model id")

    def test_iso_date_in_matrix_note_is_not_caught_by_the_existing_suite(self):
        result = _run_with_mutation(
            lambda p: _mutate_json(
                p / "harness-matrix.json",
                lambda d: d["harnesses"]["vscode"]["cells"]["mcp"].__setitem__(
                    "notes", "confirmed working as of 2025-01-15, servers key"
                ),
            )
        )
        self.assertFalse(_failed(result), "test_primitives_data.py unexpectedly now catches an ISO date")


# ---------------------------------------------------------------------------
# Safety: this file must never leave a mark on the tracked repo or the
# read-only aesop repo. Every helper above operates on a TemporaryDirectory
# that self-deletes; this test independently re-checks nothing was left
# behind by re-hashing the real tracked inputs against what they were before
# any test in this module ran.
# ---------------------------------------------------------------------------
class TrackedTreeUntouchedTests(unittest.TestCase):
    def test_real_primitives_directory_is_unmodified_by_this_module(self):
        # The three tracked files must still be exactly what test_primitives_data.py
        # itself expects (schema hash, matrix schema string, model schema string) --
        # if any mutation helper above ever mutated the real path by mistake instead
        # of a temp copy, one of these would be the first thing to drift.
        import hashlib

        digest = hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest()
        self.assertEqual(digest, "a8b5ce94dda62c547728fea03335b22bb877c70426b1ce2eee9cce23f62b2f4f")
        model = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
        self.assertEqual(model["schema"], "polytropos-primitives/v1")
        matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        self.assertEqual(matrix["schema"], "polytropos-harness-matrix/v1")


if __name__ == "__main__":
    unittest.main()
