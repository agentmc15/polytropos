"""Live-tree regression suite for the docs-site generator's OUTPUT (T5 of the
docs-site kit), in the style of tests/test_guardrails_layout.py: it asserts
against the real, committed repo -- no fixtures. Unlike tests/test_docs_build.py
(which exercises the generator's pure render functions on synthetic records),
this file proves the committed docs-site/ tree and mkdocs.yml are exactly what
bin/docs_build.py's own expected_pages()/nav actually require, right now.

bin/ is not a package; docs_build.py is loaded via importlib by absolute path,
same convention as tests/test_harness_select.py's `_load` helper. Test group 3
(link integrity) reuses the loaded module's own fence-detection and inline-link
regexes rather than re-implementing that parsing here.
"""

import importlib.util
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = REPO_ROOT / "bin"
MKDOCS_YML = REPO_ROOT / "mkdocs.yml"
DOCS_SITE_ROOT = REPO_ROOT / "docs-site"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


db = _load("docs_build")


# ---------------------------------------------------------------------------
# Group 1: drift -- the committed tree must equal expected_pages(), and no file
# may exist under a generator-owned root that expected_pages() does not name.
# Gotcha: this makes the committed tree and the generator inseparable -- that
# is the point. A failure here is fixed by running
# `python3 bin/docs_build.py build`, never by hand-editing a generated page.
# ---------------------------------------------------------------------------


class DriftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expected = db.expected_pages(REPO_ROOT)

    def test_every_expected_page_matches_committed_bytes(self):
        stale = []
        for rel_path, payload in self.expected.items():
            path = REPO_ROOT / rel_path
            if not path.is_file() or path.read_bytes() != payload:
                stale.append(rel_path)
        self.assertEqual(
            sorted(stale),
            [],
            "stale generated page(s) -- run `python3 bin/docs_build.py build`: "
            + ", ".join(sorted(stale)),
        )

    def test_no_unexpected_files_under_generator_owned_roots(self):
        expected_set = set(self.expected)
        unknown = []
        for owned_root in db._GENERATOR_OWNED_ROOTS:
            owned_dir = REPO_ROOT / owned_root
            if not owned_dir.is_dir():
                continue
            for path in owned_dir.rglob("*"):
                if path.is_file():
                    rel = path.relative_to(REPO_ROOT).as_posix()
                    if rel not in expected_set:
                        unknown.append(rel)
        self.assertEqual(
            sorted(unknown),
            [],
            "unexpected file(s) under a generator-owned root -- run "
            "`python3 bin/docs_build.py build` (fix the source if one truly "
            "should not exist): " + ", ".join(sorted(unknown)),
        )


class DeepDiveCoverageTests(unittest.TestCase):
    """T6: every docs/*.md source must have a corresponding
    deep-dives/<slug>.md entry in expected_pages() -- derived from a live
    docs/ glob, never a hardcoded list, so a future doc is caught the moment
    it is added without its mirror landing in expected_pages()."""

    def test_every_docs_md_file_has_a_deep_dive_entry(self):
        expected = db.expected_pages(REPO_ROOT)
        missing = []
        for md_path in sorted((REPO_ROOT / "docs").glob("*.md")):
            slug = db.deep_dive_slug(md_path.name)
            rel_path = f"docs-site/deep-dives/{slug}.md"
            if rel_path not in expected:
                missing.append(f"docs/{md_path.name} -> {rel_path}")
        self.assertEqual(
            missing,
            [],
            f"docs/*.md source(s) with no deep-dive mirror in expected_pages(): "
            f"{missing!r}",
        )


# ---------------------------------------------------------------------------
# Group 2: nav coverage, both directions.
# ---------------------------------------------------------------------------

_NAV_PAGE_TOKEN_RE = re.compile(r"(?:skills|deep-dives)/[A-Za-z0-9._/-]+\.md")


class NavCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nav_text = MKDOCS_YML.read_text(encoding="utf-8")
        cls.expected = db.expected_pages(REPO_ROOT)
        # mkdocs nav entries are relative to docs_dir (docs-site/), so strip
        # that prefix from expected_pages()'s repo-relative keys before
        # comparing against nav text.
        cls.expected_nav_paths = {
            rel_path[len("docs-site/") :] for rel_path in cls.expected
        }

    def test_every_expected_page_appears_exactly_once_in_nav(self):
        wrong = {
            nav_path: self.nav_text.count(nav_path)
            for nav_path in self.expected_nav_paths
            if self.nav_text.count(nav_path) != 1
        }
        self.assertEqual(
            wrong,
            {},
            f"expected page(s) not appearing exactly once in mkdocs.yml nav "
            f"(path -> occurrence count): {wrong!r}",
        )

    def test_every_nav_generated_path_token_is_an_expected_page(self):
        tokens = set(_NAV_PAGE_TOKEN_RE.findall(self.nav_text))
        extra = sorted(tokens - self.expected_nav_paths)
        self.assertEqual(
            extra,
            [],
            "mkdocs.yml nav references a skills/ or deep-dives/ path that is not "
            f"a generator-expected page -- those roots are generator-owned, so a "
            f"hand page may never live there: {extra!r}",
        )


# ---------------------------------------------------------------------------
# Group 3: offline link integrity. Anchors (#section) are NOT validated -- only
# that the target FILE resolves to something that actually exists under
# docs-site/. Reuses the loaded module's own fence-flag / link-match machinery
# rather than re-implementing markdown parsing here.
# ---------------------------------------------------------------------------


def _iter_inline_link_targets(text):
    """Yield the raw target string of every inline [text](target) markdown link
    that lies outside a fenced code block, using db._fence_flags/_LINK_RE/
    _TARGET_RE directly (the same machinery rewrite_links itself uses)."""
    lines = text.splitlines(keepends=True)
    flags = db._fence_flags(lines)
    for line, in_fence in zip(lines, flags):
        if in_fence:
            continue
        for match in db._LINK_RE.finditer(line):
            inner = match.group(2)
            target_match = db._TARGET_RE.match(inner)
            if target_match is None:
                continue
            _leading, target, _trailing = target_match.groups()
            wrapped = len(target) >= 2 and target.startswith("<") and target.endswith(">")
            yield target[1:-1] if wrapped else target


class OfflineLinkIntegrityTests(unittest.TestCase):
    """Anchors are not validated -- only that a link's file target (the part
    before any #fragment) resolves to an existing file under docs-site/."""

    def test_every_relative_link_target_resolves_under_docs_site(self):
        docs_site_resolved = DOCS_SITE_ROOT.resolve()
        broken = []
        for md_path in sorted(DOCS_SITE_ROOT.rglob("*.md")):
            text = md_path.read_text(encoding="utf-8")
            for target in _iter_inline_link_targets(text):
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                if target.startswith("#"):
                    continue
                path_part = target.split("#", 1)[0]
                if not path_part:
                    continue
                resolved = (md_path.parent / path_part).resolve()
                try:
                    resolved.relative_to(docs_site_resolved)
                    under_site = True
                except ValueError:
                    under_site = False
                if not (under_site and resolved.is_file()):
                    broken.append(
                        f"{md_path.relative_to(REPO_ROOT).as_posix()} -> {target}"
                    )
        self.assertEqual(
            broken, [], f"broken relative link(s) under docs-site/: {broken!r}"
        )


# ---------------------------------------------------------------------------
# Group 4: context-leak fence (PLAN.md D1) -- site content must never be
# loadable from a skill.
# ---------------------------------------------------------------------------


class ContextLeakFenceTests(unittest.TestCase):
    def test_no_skill_md_mentions_docs_site(self):
        harness_roots = (
            REPO_ROOT / "skills",
            REPO_ROOT / "copilot" / ".github" / "skills",
            REPO_ROOT / "codex" / "skills",
        )
        offenders = []
        for root in harness_roots:
            for skill_md in sorted(root.glob("*/SKILL.md")):
                if "docs-site" in skill_md.read_text(encoding="utf-8"):
                    offenders.append(str(skill_md.relative_to(REPO_ROOT)))
        self.assertEqual(
            offenders, [], f"SKILL.md contains the string 'docs-site': {offenders!r}"
        )


if __name__ == "__main__":
    unittest.main()
