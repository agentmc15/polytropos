"""Snapshot-label guard for the Claude docs' lineup tables.

``docs/GUIDE.md``, ``docs/HOW-IT-WORKS.md`` and their HTML companions
(``docs/guide.html``, ``docs/how-it-works.html``) carry price tables that are
labeled snapshots of ``data/pricing.json``. This module reads the REAL tree,
read-only, and asserts that each file carries the file's current ``cached_date``;
every doc, HTML included, must additionally name the first-row display name of every
tier (the current default of that tier -- the rule ``bin/claude_execute.py::
resolve_tier`` uses), derived at test time and never typed here.

``NegativeFixtureTests`` runs the identical assertion shapes against a synthetic
stale text and proves they can fail. Nothing is written into the repo.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MD_DOCS = ("docs/GUIDE.md", "docs/HOW-IT-WORKS.md")
HTML_DOCS = ("docs/guide.html", "docs/how-it-works.html")


def _pricing() -> dict:
    return json.loads((ROOT / "data" / "pricing.json").read_text(encoding="utf-8"))


def _rows(pricing: dict) -> list:
    models = pricing["models"]
    return list(models.values()) if isinstance(models, dict) else list(models)


def tier_defaults(pricing: dict) -> dict:
    """First-row display name per tier, in file order."""
    out: dict = {}
    for row in _rows(pricing):
        out.setdefault(row["tier"], row["display"])
    return out


def missing_label(text: str, pricing: dict) -> bool:
    return pricing["cached_date"] not in text


def missing_tier_names(text: str, pricing: dict) -> list:
    return [d for d in tier_defaults(pricing).values() if d not in text]


class MarkdownDocsLabelTests(unittest.TestCase):
    def test_label_matches_cached_date(self):
        pricing = _pricing()
        for rel in MD_DOCS:
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertFalse(missing_label(text, pricing),
                             f"{rel} lacks cached_date {pricing['cached_date']}")

    def test_no_stale_snapshot_date_survives(self):
        pricing = _pricing()
        for rel in MD_DOCS:
            text = (ROOT / rel).read_text(encoding="utf-8")
            for line in text.splitlines():
                if re.search(r"cached\W+\d{4}-\d{2}-\d{2}", line):
                    self.assertIn(pricing["cached_date"], line,
                                  f"{rel}: snapshot label line lags pricing.json: {line.strip()}")

    def test_every_tier_default_is_named(self):
        pricing = _pricing()
        for rel in MD_DOCS:
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertEqual(missing_tier_names(text, pricing), [],
                             f"{rel} does not name every tier's current default")


class HtmlDocsLabelTests(unittest.TestCase):
    def test_label_matches_cached_date(self):
        pricing = _pricing()
        for rel in HTML_DOCS:
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertFalse(missing_label(text, pricing),
                             f"{rel} lacks cached_date {pricing['cached_date']}")

    def test_every_tier_default_is_named(self):
        pricing = _pricing()
        for rel in HTML_DOCS:
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertEqual(missing_tier_names(text, pricing), [],
                             f"{rel} does not name every tier's current default")


class NegativeFixtureTests(unittest.TestCase):
    def test_label_check_fails_on_a_synthetic_stale_doc(self):
        pricing = {"cached_date": "2030-01-01", "models": {}}
        self.assertTrue(missing_label("snapshot cached 2020-01-01", pricing))
        self.assertFalse(missing_label("snapshot cached 2030-01-01", pricing))

    def test_tier_check_fails_on_a_synthetic_stale_doc(self):
        pricing = {"cached_date": "2030-01-01", "models": {
            "a-2": {"tier": "sonnet", "display": "Sonnet 9"},
            "a-1": {"tier": "sonnet", "display": "Sonnet 8"},
            "b-1": {"tier": "haiku", "display": "Haiku 9"}}}
        self.assertEqual(tier_defaults(pricing), {"sonnet": "Sonnet 9", "haiku": "Haiku 9"})
        self.assertEqual(missing_tier_names("| Sonnet 8 | Haiku 9 |", pricing), ["Sonnet 9"])
        self.assertEqual(missing_tier_names("| Sonnet 9 | Haiku 9 |", pricing), [])
        html = '<td class="tier-haiku">Haiku 9</td><td>Sonnet 8</td>'
        self.assertEqual(missing_tier_names(html, pricing), ["Sonnet 9"])
        html_ok = '<td class="tier-sonnet">Sonnet 9</td><td class="tier-haiku">Haiku 9</td>'
        self.assertEqual(missing_tier_names(html_ok, pricing), [])


if __name__ == "__main__":
    unittest.main()
