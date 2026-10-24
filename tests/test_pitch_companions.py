"""Live-tree guard for the companions of the printable pitch, under docs/pitch/.

- docs/pitch/spec-driven-pitch.md is the Markdown form of docs/spec-driven-pitch.html. It must
  carry every heading of the HTML deck, so the two cannot drift apart silently.
- docs/pitch/core-four.md maps Spec Kit's four core phases to polytropos, and
  docs/pitch/core-four.html is its printable form. The two must carry the same headings, and
  the HTML must meet the same structure and length rules as the deck.

All three files go through the deck's truth checks (tests/test_spec_driven_pitch.py): every
bin script, skill and repo path they name exists, there are no model ids, no rotting counts
or percentages, and no unlabeled dollar figures. The checks are imported from that module,
not copied. docs/pitch/ is a subdirectory on purpose: bin/docs_build.py mirrors only
docs/*.md, so these files add no generated page. The test reads the real tree and writes
nothing.
"""
import html
import re
import unittest
from pathlib import Path

import test_spec_driven_pitch as pitch

REPO_ROOT = Path(__file__).resolve().parent.parent
DECK_HTML = REPO_ROOT / "docs" / "spec-driven-pitch.html"
DECK_MD = REPO_ROOT / "docs" / "pitch" / "spec-driven-pitch.md"
MAP_MD = REPO_ROOT / "docs" / "pitch" / "core-four.md"
MAP_HTML = REPO_ROOT / "docs" / "pitch" / "core-four.html"

CORE_FOUR = ("Specify", "Plan", "Tasks", "Implement")
HTML_HEADING = re.compile(r"<h([1-3])\b[^>]*>(.*?)</h\1>", re.DOTALL)
MD_HEADING = re.compile(r"^#{1,3} (.+)$", re.MULTILINE)
# The Markdown deck numbers its pages in the heading ("2 · The spec ..."); the HTML does not.
PAGE_NUMBER = re.compile(r"^\d+ · ")


def _norm(s):
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    s = s.replace("`", "").replace("**", "").replace("*", "")
    s = PAGE_NUMBER.sub("", s.strip())
    return " ".join(s.split()).casefold()


def html_headings(text):
    return [_norm(m.group(2)) for m in HTML_HEADING.finditer(text)]


def md_headings(text):
    return [_norm(m) for m in MD_HEADING.findall(text)]


def check_headings_carried(html_text, md_text, both_ways=False):
    """Every heading of the HTML must appear in the Markdown (and the reverse if both_ways)."""
    in_md = set(md_headings(md_text))
    missing = [h for h in html_headings(html_text) if h not in in_md]
    if missing:
        raise AssertionError(f"headings missing from the Markdown form: {missing}")
    if both_ways:
        in_html = set(html_headings(html_text))
        extra = [h for h in md_headings(md_text) if h not in in_html]
        if extra:
            raise AssertionError(f"headings missing from the HTML form: {extra}")


def _read(path):
    return path.read_text(encoding="utf-8")


class FilesExistTests(unittest.TestCase):
    def test_files_exist(self):
        for path in (DECK_MD, MAP_MD, MAP_HTML):
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file(), f"{path} is missing")


class DeckMarkdownTests(unittest.TestCase):
    def test_carries_every_deck_heading(self):
        check_headings_carried(_read(DECK_HTML), _read(DECK_MD))

    def test_carries_the_ledger_sample_and_run_commands(self):
        md = _read(DECK_MD)
        for line in ("outcome: T3 model=sonnet attempts=1 result=pass review=clean",
                     "defect: T5 kind=tautological-verify",
                     "python3 bin/routing_scorecard.py --history"):
            self.assertIn(line, md)

    def test_names_its_html_twin(self):
        self.assertIn("docs/spec-driven-pitch.html", _read(DECK_MD))

    def test_truth(self):
        pitch.check_truth(_read(DECK_MD), REPO_ROOT)


class CoreFourTests(unittest.TestCase):
    def test_html_structure_and_length(self):
        text = _read(MAP_HTML)
        pitch.check_structure(text, REPO_ROOT)
        pitch.check_lengths(text, REPO_ROOT)

    def test_html_and_markdown_carry_the_same_headings(self):
        check_headings_carried(_read(MAP_HTML), _read(MAP_MD), both_ways=True)

    def test_each_core_phase_has_its_own_section(self):
        heads = md_headings(_read(MAP_MD))
        for phase in CORE_FOUR:
            with self.subTest(phase=phase):
                self.assertTrue(any(h.endswith(phase.casefold()) for h in heads),
                                f"no section heading for {phase}")

    def test_truth(self):
        for path in (MAP_MD, MAP_HTML):
            with self.subTest(path=path.name):
                pitch.check_truth(_read(path), REPO_ROOT)


class NegativeFixtureTests(unittest.TestCase):
    """The heading check must be able to fail; otherwise the live pass proves nothing."""

    def test_missing_heading_fails(self):
        with self.assertRaisesRegex(AssertionError, "missing from the Markdown"):
            check_headings_carried("<h2>The <em>ledger</em></h2><h3>Gone</h3>",
                                   "## The ledger\n")

    def test_extra_markdown_heading_fails_both_ways(self):
        with self.assertRaisesRegex(AssertionError, "missing from the HTML"):
            check_headings_carried("<h2>One</h2>", "## One\n## Two\n", both_ways=True)

    def test_matching_headings_pass(self):
        check_headings_carried("<h2>The <code>ledger</code> &amp; more</h2>",
                               "## The `ledger` & more\n", both_ways=True)


if __name__ == "__main__":
    unittest.main()
