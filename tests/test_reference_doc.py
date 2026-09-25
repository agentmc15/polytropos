"""The reference page carries a snapshot of every pricing file; keep it from going stale quietly.

`docs/REFERENCE.md` is the long-form page that was `README.md` until 2026-09-24. Its model tables
are labeled snapshots of `data/pricing*.json`, each at its file's own `cached_date`. The partner-doc
check in `bin/harness_update.py` (`DOCS_LABEL_MAP`) watches `README.md` and
`docs/COPILOT-HARNESS.md` only, so without this file nothing would notice the reference page
falling behind a pricing refresh. Reads the real tree only -- never writes, never uses a fixture --
in the manner of `tests/test_harness_update.py`'s `LiveTreeFreshnessTests`.
"""

import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REFERENCE = REPO_ROOT / "docs" / "REFERENCE.md"
PRICING_FILES = (
    "data/pricing.json",
    "data/pricing.codex.json",
    "data/pricing.copilot.json",
    "data/pricing.cursor.json",
)


def label_dates(text, rel):
    """Every date the page labels `rel` with, from the form '`<rel>`, `cached_date` **YYYY-MM-DD**'."""
    return re.findall(re.escape(f"`{rel}`, `cached_date` **") + r"(\d{4}-\d{2}-\d{2})\*\*", text)


def model_ids(rel):
    models = json.loads((REPO_ROOT / rel).read_text(encoding="utf-8")).get("models") or {}
    return sorted(models) if isinstance(models, dict) else sorted(m["id"] for m in models)


class ReferenceSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.text = REFERENCE.read_text(encoding="utf-8")

    def test_each_pricing_file_is_labeled_once_with_its_own_cached_date(self):
        for rel in PRICING_FILES:
            with self.subTest(file=rel):
                cached = json.loads((REPO_ROOT / rel).read_text(encoding="utf-8"))["cached_date"]
                dates = label_dates(self.text, rel)
                self.assertEqual(
                    len(dates), 1,
                    f"docs/REFERENCE.md labels {rel} {len(dates)} time(s); expected exactly one")
                self.assertEqual(
                    dates[0], cached,
                    f"{rel} is cached {cached} but docs/REFERENCE.md still labels it {dates[0]}: "
                    "regenerate that table in the same edit as the file")

    def test_every_model_id_in_every_pricing_file_appears_on_the_page(self):
        for rel in PRICING_FILES:
            for mid in model_ids(rel):
                with self.subTest(file=rel, model=mid):
                    self.assertTrue(
                        f"`{mid}`" in self.text,
                        f"{rel} carries {mid} but docs/REFERENCE.md does not show it")


if __name__ == "__main__":
    unittest.main()
