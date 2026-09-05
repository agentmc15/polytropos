"""Drift tests for docs/PRIMITIVES.md and its mkdocs.yml nav entry (PLAN.md D8,
aesop-fold kit T8).

bin/ is not a package; primitives.py is loaded via importlib by absolute path, the same
convention as tests/test_harness_select.py's `_load` helper. The embedded harness-matrix
table is compared against `render_matrix_markdown`'s own return value (a pure function
taking the matrix as an argument, never loading it itself) rather than a CLI byte-capture,
per the Phase 3 review: the function returns WITHOUT a trailing newline (the CLI's `print`
supplies the one trailing newline), so both sides are compared with `.strip("\\n")`.
"""

import importlib.util
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = REPO_ROOT / "bin"
DOC_PATH = REPO_ROOT / "docs" / "PRIMITIVES.md"
MKDOCS_YML = REPO_ROOT / "mkdocs.yml"

BEGIN_MARKER = "<!-- primitives:matrix:begin -->"
END_MARKER = "<!-- primitives:matrix:end -->"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


primitives = _load("primitives")


def _marker_region(text):
    begin = text.index(BEGIN_MARKER) + len(BEGIN_MARKER)
    end = text.index(END_MARKER)
    return text[begin:end]


class MatrixRegionDriftTests(unittest.TestCase):
    """The embedded matrix table must never drift from the generator."""

    def test_marker_region_matches_render_matrix_markdown(self):
        doc_text = DOC_PATH.read_text(encoding="utf-8")
        region = _marker_region(doc_text)
        expected = primitives.render_matrix_markdown(primitives.load_matrix())
        self.assertEqual(region.strip("\n"), expected.strip("\n"))


class PrimitivesTableOrderTests(unittest.TestCase):
    """The nine primitives table must list every id from primitives/model.json, in
    model order, in its first column."""

    def test_nine_ids_appear_in_model_order(self):
        doc_text = DOC_PATH.read_text(encoding="utf-8")
        expected_ids = [p["id"] for p in sorted(primitives.load_model()["primitives"], key=lambda p: p["order"])]

        found_ids = []
        for line in doc_text.splitlines():
            m = re.match(r"^\|\s*`([a-z]+)`\s*\|", line)
            if m:
                found_ids.append(m.group(1))

        self.assertEqual(found_ids, expected_ids)


class MkdocsNavEntryTests(unittest.TestCase):
    """mkdocs.yml must list the new page exactly once."""

    def test_deep_dives_primitives_entry_appears_exactly_once(self):
        text = MKDOCS_YML.read_text(encoding="utf-8")
        self.assertEqual(text.count("deep-dives/primitives.md"), 1)


if __name__ == "__main__":
    unittest.main()
