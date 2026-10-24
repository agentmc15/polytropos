"""Live-tree guard for docs/spec-driven-pitch.html, the printable elevator pitch.

The pitch is the short, persuasive form of docs/SPEC-DRIVEN.md. A persuasive page is
exactly where a claim can outrun the code, so this test enforces the parts of "true" that a
machine can check:

- Structure: self-contained (one inline <style>, no script, no external stylesheet, font or
  import), a dark-mode palette, and print rules that break after every
  <section class="page">.
- Length: page count is not computable from HTML with the stdlib, so the test enforces a
  stated proxy (PLAN D6 of the sdd-docs-refresh kit): 3-5 page sections, each at most 650
  words of visible text, the whole document 1400-2800 words.
- Truth: every bin/<name>.py and every repo path it names exists; every /polytropos:<skill>
  is a real skill; no model id; no rotting counts or percentages; any dollar figure sits
  beside data/pricing.json's cached_date.

The checks are module-level functions taking (text, repo_root) so the live test and the
synthetic negative fixtures share one implementation; NegativeFixtureTests proves each check
can fail. The test reads the real tree and writes nothing.
"""
import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PITCH = REPO_ROOT / "docs" / "spec-driven-pitch.html"

MIN_PAGES, MAX_PAGES = 3, 5
MAX_SECTION_WORDS = 650
MIN_TOTAL_WORDS, MAX_TOTAL_WORDS = 1400, 2800
MAX_TITLE_CHARS = 60

# The kit layout the architect skill defines; any other bare *.md name must be a real file.
KIT_FILE_NAMES = {"PLAN.md", "TASKS.md", "GUARDRAILS.md", "NOTES.md"}

SECTION_OPEN = '<section class="page"'
MODEL_ID = re.compile(r"claude-(fable|opus|sonnet|haiku)-\d")
BIN_SCRIPT = re.compile(r"bin/([a-z_]+\.py)")
SKILL_CMD = re.compile(r"/polytropos:([a-z-]+)")
REPO_PATH = re.compile(r"(?<![\w./-])((?:skills|docs|bin|data|tests)/[A-Za-z0-9_./-]*[A-Za-z0-9_])")
BARE_MD = re.compile(r"(?<![\w./-])([A-Z][A-Z-]*\.md)\b")
ROTTING_COUNT = re.compile(r"\b\d+ (kits|tasks|tests)\b")
PERCENT = re.compile(r"\d+%")
DOLLAR_FIGURE = re.compile(r"\$\d")


class _VisibleText(HTMLParser):
    """Collect visible body text, overall and per <section class="page">."""

    _HIDDEN = {"style", "script", "head", "title"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden_depth = 0
        self.section_depth = 0
        self.all_parts = []
        self.sections = []

    def handle_starttag(self, tag, attrs):
        if tag in self._HIDDEN:
            self.hidden_depth += 1
        if tag == "section":
            if self.section_depth == 0 and ("class", "page") in attrs:
                self.sections.append([])
                self.section_depth = 1
            elif self.section_depth:
                self.section_depth += 1

    def handle_endtag(self, tag):
        if tag in self._HIDDEN and self.hidden_depth:
            self.hidden_depth -= 1
        if tag == "section" and self.section_depth:
            self.section_depth -= 1

    def handle_data(self, data):
        if self.hidden_depth:
            return
        self.all_parts.append(data)
        if self.section_depth:
            self.sections[-1].append(data)


def _fail(msg):
    raise AssertionError(msg)


def visible(text):
    parser = _VisibleText()
    parser.feed(text)
    parser.close()
    whole = " ".join(parser.all_parts)
    sections = [" ".join(parts) for parts in parser.sections]
    return whole, sections


def words(s):
    return len(s.split())


def cached_date(repo_root):
    data = json.loads((Path(repo_root) / "data" / "pricing.json").read_text(encoding="utf-8"))
    value = data.get("cached_date")
    if not value:
        _fail("data/pricing.json has no cached_date")
    return value


def check_structure(text, repo_root, min_pages=MIN_PAGES, max_pages=MAX_PAGES):
    if not text.lstrip().upper().startswith("<!DOCTYPE HTML>"):
        _fail("missing <!DOCTYPE html>")
    if "<meta charset" not in text.lower():
        _fail("missing <meta charset>")
    if text.count("<style") != 1:
        _fail(f"expected exactly one <style>, found {text.count('<style')}")
    for banned in ("<script", "<link", "@import"):
        if banned in text.lower():
            _fail(f"self-containment broken: {banned!r} present")
    if re.search(r"url\(\s*['\"]?https?:", text, re.IGNORECASE):
        _fail("self-containment broken: url() points at the network")
    if re.search(r"<img\b", text, re.IGNORECASE):
        _fail("self-containment broken: an <img> is present")
    for required in ("prefers-color-scheme: dark", "@media print", "break-after: page"):
        if required not in text:
            _fail(f"missing {required!r}")
    pages = text.count(SECTION_OPEN)
    if not min_pages <= pages <= max_pages:
        _fail(f"{pages} page sections; need {min_pages}-{max_pages}")
    m = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
    if not m or not m.group(1).strip():
        _fail("missing or empty <title>")
    if len(m.group(1).strip()) > MAX_TITLE_CHARS:
        _fail(f"<title> longer than {MAX_TITLE_CHARS} chars")


def check_lengths(text, repo_root, min_total=MIN_TOTAL_WORDS, max_total=MAX_TOTAL_WORDS):
    whole, sections = visible(text)
    if not sections:
        _fail('no <section class="page"> found')
    for i, sec in enumerate(sections, 1):
        n = words(sec)
        if n > MAX_SECTION_WORDS:
            _fail(f"section {i} has {n} visible words; max {MAX_SECTION_WORDS}")
    total = words(whole)
    if not min_total <= total <= max_total:
        _fail(f"{total} visible words; need {min_total}-{max_total}")


def check_truth(text, repo_root):
    root = Path(repo_root)
    whole, _ = visible(text)
    for name in sorted(set(BIN_SCRIPT.findall(text))):
        if not (root / "bin" / name).is_file():
            _fail(f"names bin/{name}, which does not exist")
    for skill in sorted(set(SKILL_CMD.findall(text))):
        if not (root / "skills" / skill / "SKILL.md").is_file():
            _fail(f"names /polytropos:{skill}, which is not a skill")
    for path in sorted(set(REPO_PATH.findall(whole))):
        if not (root / path).exists():
            _fail(f"names {path}, which does not exist")
    for name in sorted(set(BARE_MD.findall(whole))):
        if name in KIT_FILE_NAMES:
            continue
        if not ((root / name).is_file() or (root / "docs" / name).is_file()):
            _fail(f"names {name}, which is neither a kit file nor a repo doc")
    if MODEL_ID.search(text):
        _fail(f"model id present: {MODEL_ID.search(text).group(0)!r}")
    if DOLLAR_FIGURE.search(whole):
        date = cached_date(root)
        if date not in whole or "data/pricing.json" not in whole:
            _fail(f"dollar figure without the snapshot label (data/pricing.json, cached {date})")
    m = ROTTING_COUNT.search(whole)
    if m:
        _fail(f"rotting count in prose: {m.group(0)!r}")
    m = PERCENT.search(whole)
    if m:
        _fail(f"percentage in prose: {m.group(0)!r}")
    if "SPEC-DRIVEN.md" not in whole:
        _fail("does not point at the long form, docs/SPEC-DRIVEN.md")


def _live_text():
    return PITCH.read_text(encoding="utf-8")


class StructureTests(unittest.TestCase):
    def test_file_exists(self):
        self.assertTrue(PITCH.is_file(), f"{PITCH} is missing")

    def test_structure(self):
        check_structure(_live_text(), REPO_ROOT)

    def test_page_rule_exempts_last_page(self):
        text = _live_text()
        self.assertIn(".page:last-of-type", text)
        self.assertIn("page-break-after: always", text)


class LengthTests(unittest.TestCase):
    def test_lengths(self):
        check_lengths(_live_text(), REPO_ROOT)


class TruthTests(unittest.TestCase):
    def test_truth(self):
        check_truth(_live_text(), REPO_ROOT)

    def test_footer_names_long_form_and_source(self):
        whole, _ = visible(_live_text())
        self.assertIn("Long form: docs/SPEC-DRIVEN.md", whole)
        self.assertIn("github.com/agentmc15/polytropos", whole)

    def test_run_it_commands_present(self):
        whole, _ = visible(_live_text())
        for cmd in ("/polytropos:architect", "/polytropos:execute",
                    "python3 bin/routing_scorecard.py --history"):
            self.assertIn(cmd, whole)


def _fixture(sections=4, body="Plain words about the spec and the ledger. "):
    filler = body * 50
    pages = "".join(
        f'<section class="page"><h2>Page {i}</h2><p>{filler}</p></section>'
        for i in range(sections)
    )
    return (
        "<!DOCTYPE html><html><head><meta charset=\"UTF-8\"><title>t</title>"
        "<style>@media (prefers-color-scheme: dark){} @media print{.page{break-after: page;}}"
        "</style></head><body><main class=\"wrap\">"
        f"{pages}<p>Long form: docs/SPEC-DRIVEN.md</p></main></body></html>"
    )


class NegativeFixtureTests(unittest.TestCase):
    """Each check must be able to fail; otherwise the live pass proves nothing."""

    def test_baseline_fixture_passes(self):
        text = _fixture()
        check_structure(text, REPO_ROOT)
        check_lengths(text, REPO_ROOT)
        check_truth(text, REPO_ROOT)

    def test_two_sections_fail_structure(self):
        with self.assertRaisesRegex(AssertionError, "page sections"):
            check_structure(_fixture(sections=2), REPO_ROOT)

    def test_missing_script_fails_truth(self):
        text = _fixture(body="Run bin/does_not_exist.py to see. ")
        with self.assertRaisesRegex(AssertionError, "does_not_exist"):
            check_truth(text, REPO_ROOT)

    def test_unlabeled_dollar_fails_truth(self):
        text = _fixture(body="It costs $5 a run. ")
        with self.assertRaisesRegex(AssertionError, "snapshot label"):
            check_truth(text, REPO_ROOT)

    def test_model_id_and_counts_fail_truth(self):
        for body, pattern in (("Runs on claude-sonnet-5 now. ", "model id"),
                              ("We shipped 12 kits so far. ", "rotting count"),
                              ("First-try rate is 90% today. ", "percentage"),
                              ("Run /polytropos:nonexistent today. ", "not a skill")):
            with self.subTest(body=body):
                with self.assertRaisesRegex(AssertionError, pattern):
                    check_truth(_fixture(body=body), REPO_ROOT)

    def test_overlong_section_fails_lengths(self):
        text = _fixture(sections=3, body="word " * 20)
        with self.assertRaisesRegex(AssertionError, "section 1"):
            check_lengths(text, REPO_ROOT)


if __name__ == "__main__":
    unittest.main()
