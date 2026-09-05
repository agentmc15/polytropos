"""Adversarial coverage for tests/test_primitives_doc.py (aesop-fold kit, T8).

Authored from the T8 brief's stated contract and acceptance criteria (see
.claude/kits/aesop-fold/TASKS.md T8, PLAN.md D8) -- not from reading
test_primitives_doc.py's implementation first and reverse-engineering tests
that match it. The brief's own load-bearing claim is the drift test itself:
"the doc cannot silently drift from the data" (PLAN D8). This file proves
that claim rather than assuming it, following this repo's established
mutation-tripwire pattern (tests/test_primitives_data_adversarial.py,
tests/test_python_floor_adversarial.py): copy the REAL, byte-for-byte
unmodified test_primitives_doc.py plus its inputs (bin/primitives.py,
primitives/*.json, docs/PRIMITIVES.md, mkdocs.yml) into a fresh temp tree
(GUARDRAILS.md "Safe mutation recipe"), plant exactly one mutation there,
and run the actual shipped test module against it. The tracked repo is
never touched -- see TrackedTreeUntouchedTests below.

Questions the T8 brief's contract implies but does not itself test:

1. Does the drift test fail when the DOC's embedded matrix region diverges
   from the data, and separately when the DATA moves and the doc goes
   stale? A drift test that only catches one direction (or neither) would
   let the published table silently diverge from what it claims to render
   -- exactly the failure PLAN D8 exists to prevent.
2. Does the model-order check detect a REORDERING, or only that the nine
   ids are present somewhere?
3. Is the marker extraction robust to a missing begin marker, a missing end
   marker, or an empty-but-present region -- does it fail loudly (an error
   or a real assertion failure) rather than silently passing on a
   malformed doc?

Two checks on the doc's own factual content (T8 acceptance: the doc's
content is pinned, not free prose):

4. Section 6's "seven finding codes" must match what bin/primitives.py's
   validate() pipeline actually raises, not a hand-typed list liable to
   drift from the implementation.
5. Section 5's TOML excerpt must be real content transcribed from
   copilot/aesop.toml, not invented boilerplate.

One check on the T8 amendment (the four/one census-bump assertions in
tests/test_docs_build_adversarial.py and tests/test_docs_build_cli.py): are
the bumped hardcoded counts correct for the real tree, and do they still
fail if one more undocumented doc were added -- i.e. are they still real
tripwires, not accidentally made unfalsifiable by the bump?

A gap noted along the way, not one of the numbered probes above: T8's own
acceptance line ("no dollar sign followed by a digit ... no ](docs/ link
form ... no absolute paths ... no dates other than the aesop provenance
commit") is currently enforced only by the manual bash `Verify:` block in
TASKS.md, not by any test the suite discovers -- a later hand-edit to
docs/PRIMITIVES.md could violate it silently. DocHygieneAcceptanceTests
closes that gap directly from the acceptance line's own wording.
"""

import hashlib
import importlib.util
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = REPO_ROOT / "bin"
PRIMITIVES_DIR = REPO_ROOT / "primitives"
DOC_PATH = REPO_ROOT / "docs" / "PRIMITIVES.md"
MKDOCS_YML = REPO_ROOT / "mkdocs.yml"
REAL_TEST_MODULE = REPO_ROOT / "tests" / "test_primitives_doc.py"
TOML_MANIFEST = REPO_ROOT / "copilot" / "aesop.toml"

BEGIN_MARKER = "<!-- primitives:matrix:begin -->"
END_MARKER = "<!-- primitives:matrix:end -->"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    original_flag = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = original_flag
    return mod


def _copy_real_tree_into(tmp):
    """Copy the real bin/primitives.py, primitives/*.json, docs/PRIMITIVES.md,
    mkdocs.yml, and tests/test_primitives_doc.py into tmp, mirroring the
    layout test_primitives_doc.py's own REPO_ROOT/BIN_DIR/DOC_PATH/MKDOCS_YML
    resolution expects once the module lives under tmp/tests/. Never touches
    the tracked tree."""
    (tmp / "bin").mkdir(parents=True)
    shutil.copy2(BIN_DIR / "primitives.py", tmp / "bin" / "primitives.py")
    shutil.copytree(PRIMITIVES_DIR, tmp / "primitives")
    (tmp / "docs").mkdir(parents=True)
    shutil.copy2(DOC_PATH, tmp / "docs" / "PRIMITIVES.md")
    shutil.copy2(MKDOCS_YML, tmp / "mkdocs.yml")
    (tmp / "tests").mkdir(parents=True)
    shutil.copy2(REAL_TEST_MODULE, tmp / "tests" / "test_primitives_doc.py")


def _load_real_test_module(tmp):
    return _load("_t8_doc_under_test", tmp / "tests" / "test_primitives_doc.py")


def _run(module, method_name):
    """Run one test method from whichever TestCase in `module` exposes it,
    inside a TestSuite (not case.run() directly) so any class-level fixture
    would still execute."""
    for obj in vars(module).values():
        if isinstance(obj, type) and issubclass(obj, unittest.TestCase) and hasattr(obj, method_name):
            case = obj(method_name)
            result = unittest.TestResult()
            unittest.TestSuite([case]).run(result)
            return result
    raise AssertionError(f"no TestCase in {module} exposes {method_name!r}")


def _is_clean(result):
    return not result.errors and not result.failures


class DriftTestCatchesBothDirectionsTests(unittest.TestCase):
    """PLAN D8: 'the doc cannot silently drift from the data.' Proves it by
    running the REAL test_marker_region_matches_render_matrix_markdown
    against three temp copies: unmutated (must pass), doc-side divergence
    (must fail), and data-side divergence (must fail)."""

    def test_unmutated_copy_passes(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            _copy_real_tree_into(tmp)
            module = _load_real_test_module(tmp)
            result = _run(module, "test_marker_region_matches_render_matrix_markdown")
            self.assertTrue(_is_clean(result), f"unmutated copy should pass: {result.errors + result.failures}")

    def test_doc_side_matrix_cell_divergence_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            _copy_real_tree_into(tmp)
            doc_path = tmp / "docs" / "PRIMITIVES.md"
            text = doc_path.read_text(encoding="utf-8")
            begin = text.index(BEGIN_MARKER)
            end = text.index(END_MARKER)
            region = text[begin:end]
            self.assertIn("fallback", region, "fixture assumption: at least one fallback cell in the matrix")
            mutated_region = region.replace("fallback", "native", 1)
            self.assertNotEqual(mutated_region, region)
            doc_path.write_text(text[:begin] + mutated_region + text[end:], encoding="utf-8")

            module = _load_real_test_module(tmp)
            result = _run(module, "test_marker_region_matches_render_matrix_markdown")
            self.assertFalse(_is_clean(result), "doc-side divergence (fallback->native) must fail the drift test")
            self.assertEqual(len(result.failures), 1, result.failures)

    def test_data_side_harness_matrix_divergence_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            _copy_real_tree_into(tmp)
            matrix_path = tmp / "primitives" / "harness-matrix.json"
            data = json.loads(matrix_path.read_text(encoding="utf-8"))
            cell = data["harnesses"]["cursor"]["cells"]["skill"]
            self.assertEqual(cell["support"], "fallback", "fixture assumption about the pinned matrix")
            cell["support"] = "native"
            matrix_path.write_text(json.dumps(data), encoding="utf-8")

            module = _load_real_test_module(tmp)
            result = _run(module, "test_marker_region_matches_render_matrix_markdown")
            self.assertFalse(_is_clean(result), "data-side divergence must fail the drift test (doc goes stale)")
            self.assertEqual(len(result.failures), 1, result.failures)


class ModelOrderDriftIsDetectedTests(unittest.TestCase):
    """Proves test_nine_ids_appear_in_model_order checks ORDER, not just
    presence: swap two rows of the doc's primitives table and confirm the
    real test fails."""

    def test_reordering_two_primitive_rows_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            _copy_real_tree_into(tmp)
            doc_path = tmp / "docs" / "PRIMITIVES.md"
            lines = doc_path.read_text(encoding="utf-8").splitlines(keepends=True)
            row_re = re.compile(r"^\|\s*`([a-z]+)`\s*\|")
            positions = {}
            for i, line in enumerate(lines):
                m = row_re.match(line)
                if m:
                    positions[m.group(1)] = i
            i1, i2 = positions["instructions"], positions["skill"]
            lines[i1], lines[i2] = lines[i2], lines[i1]
            doc_path.write_text("".join(lines), encoding="utf-8")

            module = _load_real_test_module(tmp)
            result = _run(module, "test_nine_ids_appear_in_model_order")
            self.assertFalse(_is_clean(result), "a swapped row pair must fail the order check")
            self.assertEqual(len(result.failures), 1, result.failures)


class MarkerExtractionRobustnessTests(unittest.TestCase):
    """A malformed doc (missing begin marker, missing end marker, or an
    empty-but-present region) must fail loudly -- an error or a genuine
    assertion failure -- never a silent pass."""

    def test_missing_begin_marker_errors_loudly(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            _copy_real_tree_into(tmp)
            doc_path = tmp / "docs" / "PRIMITIVES.md"
            text = doc_path.read_text(encoding="utf-8").replace(BEGIN_MARKER, "")
            doc_path.write_text(text, encoding="utf-8")

            module = _load_real_test_module(tmp)
            result = _run(module, "test_marker_region_matches_render_matrix_markdown")
            self.assertFalse(_is_clean(result), "a missing begin marker must not silently pass")
            self.assertEqual(len(result.errors), 1, result.errors)

    def test_missing_end_marker_errors_loudly(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            _copy_real_tree_into(tmp)
            doc_path = tmp / "docs" / "PRIMITIVES.md"
            text = doc_path.read_text(encoding="utf-8").replace(END_MARKER, "")
            doc_path.write_text(text, encoding="utf-8")

            module = _load_real_test_module(tmp)
            result = _run(module, "test_marker_region_matches_render_matrix_markdown")
            self.assertFalse(_is_clean(result), "a missing end marker must not silently pass")
            self.assertEqual(len(result.errors), 1, result.errors)

    def test_empty_region_between_present_markers_fails_not_passes(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            _copy_real_tree_into(tmp)
            doc_path = tmp / "docs" / "PRIMITIVES.md"
            text = doc_path.read_text(encoding="utf-8")
            begin = text.index(BEGIN_MARKER) + len(BEGIN_MARKER)
            end = text.index(END_MARKER)
            doc_path.write_text(text[:begin] + text[end:], encoding="utf-8")

            module = _load_real_test_module(tmp)
            result = _run(module, "test_marker_region_matches_render_matrix_markdown")
            self.assertFalse(_is_clean(result), "an empty region must fail, not silently pass")
            self.assertEqual(len(result.failures), 1, result.failures)


class FindingCodesDocMatchesImplementationTests(unittest.TestCase):
    """Section 6 lists 'seven finding codes, each independent of the
    others' -- one bullet per code. This must match the codes
    bin/primitives.py's validate() pipeline actually raises, not a
    hand-typed list liable to drift from the implementation."""

    def test_seven_codes_in_doc_equal_codes_raised_by_validate(self):
        doc_text = DOC_PATH.read_text(encoding="utf-8")
        doc_codes = re.findall(r"^- `([a-z-]+)` — ", doc_text, re.MULTILINE)
        self.assertEqual(len(doc_codes), 7, doc_codes)
        self.assertEqual(len(doc_codes), len(set(doc_codes)), "no duplicate code in the doc's list")

        impl_text = (BIN_DIR / "primitives.py").read_text(encoding="utf-8")
        impl_codes = set(re.findall(r'_finding\(\s*"([a-z-]+)"', impl_text))
        self.assertEqual(set(doc_codes), impl_codes)


class TomlExcerptIsRealManifestContentTests(unittest.TestCase):
    """Section 5's TOML excerpt must be transcribed from the real
    copilot/aesop.toml, not invented content."""

    def test_excerpt_lines_appear_verbatim_in_the_real_manifest(self):
        doc_text = DOC_PATH.read_text(encoding="utf-8")
        fence_start = doc_text.index("```toml") + len("```toml")
        fence_end = doc_text.index("```", fence_start)
        excerpt = doc_text[fence_start:fence_end]

        manifest_text = TOML_MANIFEST.read_text(encoding="utf-8")
        distinctive_lines = [
            stripped
            for stripped in (line.strip() for line in excerpt.splitlines())
            if stripped and "..." not in stripped
        ]
        self.assertTrue(len(distinctive_lines) >= 10, "the excerpt must carry substantial real content")
        missing = [line for line in distinctive_lines if line not in manifest_text]
        self.assertEqual(missing, [], f"excerpt lines not found verbatim in copilot/aesop.toml: {missing}")


class CensusBumpTripwireTests(unittest.TestCase):
    """T8's amendment hardcoded four census assertions in
    tests/test_docs_build_adversarial.py (25/27/69/70) and one in
    tests/test_docs_build_cli.py (69). Confirms those counts are correct for
    the real tree today, and that they are still real tripwires -- adding
    one more docs/*.md file in a temp copy must break them (26/28/70), not
    sail through unfalsified."""

    def test_pinned_counts_match_the_real_tree(self):
        docs_build = _load("_t8_docs_build_real", BIN_DIR / "docs_build.py")
        md_sources = sorted((REPO_ROOT / "docs").glob("*.md"))
        self.assertEqual(len(md_sources), 25)
        page_map = docs_build.deep_dive_page_map(REPO_ROOT)
        self.assertEqual(len(page_map), 27)
        self.assertEqual(len(docs_build.expected_pages(REPO_ROOT)), 69)

    def test_one_more_doc_breaks_the_pinned_counts(self):
        docs_build = _load("_t8_docs_build_copy", BIN_DIR / "docs_build.py")
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            for name in ("skills", "copilot", "codex", "docs"):
                shutil.copytree(REPO_ROOT / name, tmp / name)

            md_before = sorted((tmp / "docs").glob("*.md"))
            self.assertEqual(len(md_before), 25)
            self.assertEqual(len(docs_build.expected_pages(tmp)), 69)

            (tmp / "docs" / "ZZZ-STUB.md").write_text("# Stub\n\nStub content.\n", encoding="utf-8")

            md_after = sorted((tmp / "docs").glob("*.md"))
            self.assertEqual(len(md_after), 26, "one more doc must move the pinned 25 -> 26")
            page_map_after = docs_build.deep_dive_page_map(tmp)
            self.assertEqual(len(page_map_after), 28, "one more doc must move the pinned 27 -> 28")
            self.assertEqual(len(docs_build.expected_pages(tmp)), 70, "one more doc must move the pinned 69 -> 70")


class DocHygieneAcceptanceTests(unittest.TestCase):
    """T8's acceptance line, checked directly (not just by the manual bash
    `Verify:` block in TASKS.md, which no discovered test runs): no dollar
    sign followed by a digit, no `](docs/` link form, no absolute/home
    paths, and no date other than the aesop provenance commit reference."""

    def test_no_dollar_digit(self):
        doc_text = DOC_PATH.read_text(encoding="utf-8")
        self.assertNotRegex(doc_text, r"\$[0-9]")

    def test_no_docs_prefixed_link_form(self):
        doc_text = DOC_PATH.read_text(encoding="utf-8")
        self.assertNotIn("](docs/", doc_text)

    def test_no_absolute_or_home_path(self):
        doc_text = DOC_PATH.read_text(encoding="utf-8")
        for needle in ("/Users/", "/home/", "~/"):
            self.assertNotIn(needle, doc_text)

    def test_no_iso_date_outside_the_provenance_commit_reference(self):
        doc_text = DOC_PATH.read_text(encoding="utf-8")
        self.assertNotRegex(doc_text, r"\b20\d{2}-\d{2}-\d{2}\b")


class TrackedTreeUntouchedTests(unittest.TestCase):
    """Sanity check mirroring test_primitives_data_adversarial.py's own:
    if any mutation helper above ever wrote to a real tracked path instead
    of a temp copy, one of these would be the first thing to drift."""

    def test_real_doc_and_primitives_are_unmodified_by_this_module(self):
        doc_text = DOC_PATH.read_text(encoding="utf-8")
        self.assertIn(BEGIN_MARKER, doc_text)
        self.assertIn(END_MARKER, doc_text)
        self.assertTrue(doc_text.startswith("# AI primitives"))

        digest = hashlib.sha256((PRIMITIVES_DIR / "aesop.schema.v1.json").read_bytes()).hexdigest()
        self.assertEqual(digest, "a8b5ce94dda62c547728fea03335b22bb877c70426b1ce2eee9cce23f62b2f4f")

        matrix = json.loads((PRIMITIVES_DIR / "harness-matrix.json").read_text(encoding="utf-8"))
        self.assertEqual(matrix["harnesses"]["cursor"]["cells"]["skill"]["support"], "fallback")

        self.assertEqual(MKDOCS_YML.read_text(encoding="utf-8").count("deep-dives/primitives.md"), 1)


if __name__ == "__main__":
    unittest.main()
