"""Stdlib unittest regression suite for T2 of the docs-site kit: the site
skeleton (mkdocs.yml, docs-src/requirements.txt, docs-site/index.md, the
.gitignore append).

These tests are derived from the T2 brief in .claude/kits/docs-site/TASKS.md,
not from reading bin/docs_build.py or any generator output — T2 hand-authors
config/prose files, it does not touch the generator. The task's own verify
command (a chain of greps) already proves a subset of the pinned keys exist;
this file targets the parts of the brief that verify command does NOT cover:
exact pinned values, "exactly one nav entry" (not pre-added future pages),
two-space indentation as a specific unit (not just "no tabs"), the
docs-site-kit-wide no-hardcoded-model-id rule applied to a hand-authored site
page (GUARDRAILS.md, "Numbers, facts, and honesty"), the landing page's word
count band and dead-link freedom, and the .gitignore append-only property.

No YAML parser is used (acceptance says mkdocs.yml parsing is not locally
checkable — stdlib has no YAML): every check here is line/regex-based against
the raw text, matching the brief's own "acceptance is structural" framing.
"""
import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MKDOCS_YML = REPO / "mkdocs.yml"
REQUIREMENTS_TXT = REPO / "docs-src" / "requirements.txt"
INDEX_MD = REPO / "docs-site" / "index.md"
GITIGNORE = REPO / ".gitignore"

# Model names/ids this repo prices (data/pricing.json) — a hand-authored site
# page or mkdocs.yml value must never hardcode one of these (GUARDRAILS.md:
# "No price, ratio, plan allowance, model id, or cached date is ever
# hardcoded into the generator, a fragment, or a hand-authored site page.").
# The T2 brief itself pins the paraphrase "keeps the frontier model for work
# that needs it" rather than naming a specific model — evidence this is a
# deliberate requirement, not just a style nit.
HARDCODED_MODEL_NAME_PATTERNS = (
    r"\bfable\s*5\b",
    r"\bopus\s*5\b",
    r"\bopus\s*4\.8\b",
    r"\bopus\s*4\.7\b",
    r"\bsonnet\s*5\b",
    r"\bsonnet\s*4\.6\b",
    r"\bhaiku\s*4\.5\b",
    r"claude-fable-5",
    r"claude-opus-5",
    r"claude-opus-4-8",
    r"claude-opus-4-7",
    r"claude-sonnet-5",
    r"claude-sonnet-4-6",
    r"claude-haiku-4-5",
)


def _find_hardcoded_model_names(text):
    hits = []
    for pat in HARDCODED_MODEL_NAME_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            hits.append(pat)
    return hits


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True
    )


def _block(text, start_key, next_keys):
    """Return the text of a top-level YAML-ish block starting at a line
    beginning with start_key (e.g. "nav:") up to (but excluding) the next
    top-level key line, or EOF. Purely line-based; no YAML parsing."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.rstrip() == start_key or line.startswith(start_key + " "):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if line and not line[0].isspace() and line.strip() != "":
            # a new top-level key (no leading whitespace)
            end = i
            break
    return "\n".join(lines[start:end])


class MkdocsYmlExistsTests(unittest.TestCase):
    def test_file_exists(self):
        self.assertTrue(MKDOCS_YML.is_file(), "mkdocs.yml must exist at repo root")


@unittest.skipUnless(MKDOCS_YML.is_file(), "mkdocs.yml missing")
class MkdocsYmlPinnedValuesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = MKDOCS_YML.read_text(encoding="utf-8")

    def test_site_name_exact(self):
        self.assertRegex(self.text, r"(?m)^site_name:\s*polytropos\s*$")

    def test_site_url_exact(self):
        self.assertRegex(
            self.text,
            r"(?m)^site_url:\s*https://agentmc15\.github\.io/polytropos/\s*$",
        )

    def test_repo_url_exact(self):
        self.assertRegex(
            self.text,
            r"(?m)^repo_url:\s*https://github\.com/agentmc15/polytropos\s*$",
        )

    def test_site_description_present_and_not_empty(self):
        m = re.search(r"(?m)^site_description:\s*(.+)$", self.text)
        self.assertIsNotNone(m, "site_description key must be present")
        self.assertTrue(m.group(1).strip(), "site_description must not be empty")

    def test_site_description_carries_readme_framing_keywords(self):
        """Brief: 'one sentence from README's own framing (picks the right
        model per task, estimates cost, keeps the frontier model for work
        that needs it)'."""
        m = re.search(r"(?m)^site_description:\s*(.+)$", self.text)
        self.assertIsNotNone(m)
        desc = m.group(1).lower()
        self.assertIn("model", desc)
        self.assertIn("cost", desc)

    def test_site_description_does_not_hardcode_a_model_name(self):
        """Brief pins the framing as 'keeps the frontier model for work that
        needs it' — not a specific model id. A hand-authored site value that
        names a specific frontier model (e.g. copying README's 'Fable 5'
        verbatim) goes stale the moment that name changes, and GUARDRAILS.md
        bans hardcoded model ids in hand-authored site content outright."""
        m = re.search(r"(?m)^site_description:\s*(.+)$", self.text)
        self.assertIsNotNone(m)
        hits = _find_hardcoded_model_names(m.group(1))
        self.assertEqual(
            hits, [],
            f"site_description hardcodes a specific model name {hits!r}: "
            f"{m.group(1)!r} — brief's own paraphrase is 'the frontier model', "
            "not a named model.",
        )

    def test_docs_dir_and_site_dir(self):
        self.assertRegex(self.text, r"(?m)^docs_dir:\s*docs-site\s*$")
        self.assertRegex(self.text, r"(?m)^site_dir:\s*site-build\s*$")


@unittest.skipUnless(MKDOCS_YML.is_file(), "mkdocs.yml missing")
class MkdocsYmlThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = MKDOCS_YML.read_text(encoding="utf-8")
        cls.theme_block = _block(cls.text, "theme:", None) or ""

    def test_theme_name_material(self):
        self.assertIn("name: material", self.theme_block)

    def test_palette_has_light_and_dark_media_queries(self):
        self.assertRegex(
            self.theme_block, r'media:\s*"?\(prefers-color-scheme:\s*light\)"?'
        )
        self.assertRegex(
            self.theme_block, r'media:\s*"?\(prefers-color-scheme:\s*dark\)"?'
        )

    def test_palette_has_manual_toggle(self):
        self.assertIn("toggle:", self.theme_block)

    def test_features_pinned_set_present(self):
        for feature in ("navigation.sections", "navigation.top", "content.code.copy"):
            self.assertIn(
                feature, self.theme_block, f"theme.features missing {feature!r}"
            )


@unittest.skipUnless(MKDOCS_YML.is_file(), "mkdocs.yml missing")
class MkdocsYmlMarkdownExtensionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = MKDOCS_YML.read_text(encoding="utf-8")
        cls.block = _block(cls.text, "markdown_extensions:", None) or ""

    def test_pinned_extensions_present(self):
        for ext in ("admonition", "pymdownx.superfences", "pymdownx.details"):
            self.assertIn(ext, self.block, f"markdown_extensions missing {ext!r}")

    def test_toc_has_permalink_true(self):
        self.assertRegex(self.block, r"toc:\s*\n\s*permalink:\s*true")


@unittest.skipUnless(MKDOCS_YML.is_file(), "mkdocs.yml missing")
class MkdocsYmlNavTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = MKDOCS_YML.read_text(encoding="utf-8")
        cls.nav_block = _block(cls.text, "nav:", None) or ""

    def test_nav_block_exists(self):
        self.assertTrue(self.nav_block, "nav: block must be present")

    def _top_level_entries(self):
        """Top-level nav entries only (2-space indent, matching this file's
        established '- Home: index.md' convention) — excludes every nested
        Skills/harness/skill-page line added by T5+, which live at deeper
        indentation."""
        entries = []
        for line in self.nav_block.splitlines()[1:]:
            if not line.strip():
                continue
            leading = len(line) - len(line.lstrip(" "))
            if leading == 2 and line.lstrip(" ").startswith("- "):
                entries.append(line.strip())
        return entries

    def test_nav_has_home_then_skills_top_level_entries(self):
        """Relaxed for T5 (docs-site kit, Phase 2): the original assertion here
        pinned 'exactly one entry: Home' for the pre-T5 skeleton window only —
        its own docstring said so explicitly ('T5/T6/T15 haven't run yet, so
        anything beyond Home would point at a page that doesn't exist'). T5 has
        now landed the Skills section (43 real generated pages), so a second
        top-level entry pointing at real pages is expected, not drift. What
        stays pinned: Home remains first. Full coverage of every generated
        page in the nav text is enforced by tests/test_docs_site.py's
        NavCoverageTests, not here."""
        top_level = self._top_level_entries()
        self.assertEqual(top_level[0], "- Home: index.md")
        self.assertIn("- Skills:", top_level)

    def test_nav_entry_is_home_index(self):
        top_level = self._top_level_entries()
        self.assertEqual(top_level[0], "- Home: index.md")


@unittest.skipUnless(MKDOCS_YML.is_file(), "mkdocs.yml missing")
class MkdocsYmlIndentationTests(unittest.TestCase):
    """Acceptance: 'every pinned key present, two-space indentation, no
    tabs.' The verify command's grep only checks for the absence of a literal
    tab character, which a 4-space-indented file would also pass — these
    checks require the specific two-space UNIT the brief pins."""

    @classmethod
    def setUpClass(cls):
        cls.lines = MKDOCS_YML.read_text(encoding="utf-8").splitlines()

    def test_no_tab_characters(self):
        for line in self.lines:
            self.assertNotIn("\t", line)

    def test_all_indentation_is_a_multiple_of_two_spaces(self):
        for line in self.lines:
            if not line.strip():
                continue
            leading = len(line) - len(line.lstrip(" "))
            self.assertEqual(
                leading % 2, 0,
                f"non-2-space indentation unit on line: {line!r}",
            )

    def test_theme_child_key_is_two_spaces_not_four(self):
        self.assertIn("\n  name: material", "\n" + "\n".join(self.lines))

    def test_nav_entry_is_two_spaces_not_four(self):
        self.assertIn("\n  - Home: index.md", "\n" + "\n".join(self.lines))


class RequirementsTxtTests(unittest.TestCase):
    def test_file_exists(self):
        self.assertTrue(REQUIREMENTS_TXT.is_file())

    def _lines(self):
        return REQUIREMENTS_TXT.read_text(encoding="utf-8").splitlines()

    def test_every_package_is_pinned_exactly_and_hashed(self):
        """Since step 14 this is a LOCK, not a requirement.

        It used to be the single line `mkdocs-material>=9.5,<10`, which pinned neither a
        version nor a transitive set: two CI runs a week apart could install different code,
        and nothing verified that what arrived was what the author of that version published.
        """
        text = REQUIREMENTS_TXT.read_text(encoding="utf-8")
        pins = re.findall(r"(?m)^([A-Za-z0-9._-]+)==([^\s\\]+)", text)
        self.assertGreater(len(pins), 10, "a lock without transitives is not a lock")
        self.assertEqual(len(pins), text.count("--hash=sha256:"),
                         "every pinned package needs exactly one recorded hash")
        # mkdocs-material is still the reason this file exists.
        self.assertIn("mkdocs-material", [name.lower() for name, _ in pins])
        # And no unpinned range survives anywhere.
        self.assertNotRegex(text, r"(?m)^[A-Za-z0-9._-]+\s*[><~!]")

    def test_the_lock_records_how_to_regenerate_itself(self):
        # A lock nobody can rebuild is a lock nobody will update.
        comments = " ".join(l for l in self._lines() if l.strip().startswith("#")).lower()
        self.assertIn("regenerate", comments)
        self.assertIn("--platform", comments)

    def test_has_stdlib_only_comment(self):
        comment_lines = [
            line for line in self._lines() if line.strip().startswith("#")
        ]
        self.assertTrue(comment_lines, "requirements.txt must carry an explanatory comment")
        joined = " ".join(comment_lines).lower()
        self.assertIn("stdlib", joined)


class LandingPageTests(unittest.TestCase):
    def test_file_exists(self):
        self.assertTrue(INDEX_MD.is_file())

    def test_word_count_in_brief_band(self):
        """Brief: '~250-450 words'. Allow a little slack past the literal
        band for the stated '~', but not an unbounded amount — this should
        still catch a stub page or a runaway one."""
        words = INDEX_MD.read_text(encoding="utf-8").split()
        self.assertTrue(
            200 <= len(words) <= 500,
            f"index.md word count {len(words)} is far outside the brief's ~250-450 band",
        )

    def test_mentions_all_three_harnesses(self):
        text = INDEX_MD.read_text(encoding="utf-8")
        self.assertIn("Claude Code", text)
        self.assertRegex(text, r"Copilot")
        self.assertRegex(text, r"Codex")

    def test_no_relative_links_to_nonexistent_site_pages(self):
        """Brief: 'No relative links to site pages that don't exist yet —
        external links to the GitHub repo are fine.'"""
        text = INDEX_MD.read_text(encoding="utf-8")
        # Strip fenced code blocks before scanning for links (fence-aware,
        # matching the kit's own convention for its link rewriter).
        text_no_fences = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        for m in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", text_no_fences):
            target = m.group(1).strip()
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            # any other relative target must resolve to a real file under
            # docs-site/ (fragment stripped)
            target_path = target.split("#", 1)[0]
            resolved = (INDEX_MD.parent / target_path).resolve()
            self.assertTrue(
                resolved.is_file(),
                f"index.md links to a relative target that doesn't exist yet: {target!r}",
            )

    def test_no_hardcoded_model_name_in_landing_page(self):
        """Same GUARDRAILS.md rule as the mkdocs.yml site_description check,
        applied to the other hand-authored site page this task creates."""
        text = INDEX_MD.read_text(encoding="utf-8")
        hits = _find_hardcoded_model_names(text)
        self.assertEqual(
            hits, [],
            f"docs-site/index.md hardcodes a specific model name {hits!r}",
        )


class GitignoreAppendOnlyTests(unittest.TestCase):
    def test_gitignore_exists(self):
        self.assertTrue(GITIGNORE.is_file())

    def test_site_build_line_present(self):
        lines = GITIGNORE.read_text(encoding="utf-8").splitlines()
        self.assertIn("/site-build/", lines)

    def test_working_tree_diff_is_additions_only(self):
        """Brief: '.gitignore diff is append-only'. Compares the current
        working tree against HEAD (git plumbing on the repo's own tree —
        sanctioned by the same convention as test_privacy_layout.py). If T2's
        change is already committed by the time this runs, HEAD already
        contains it and the diff is empty — that is not a failure, it is the
        append already having landed cleanly."""
        r = _git("diff", "--unified=0", "--", ".gitignore")
        self.assertEqual(r.returncode, 0, r.stderr)
        removed = [
            line for line in r.stdout.splitlines()
            if line.startswith("-") and not line.startswith("---")
        ]
        self.assertEqual(
            removed, [],
            f".gitignore diff removes or reorders existing lines: {removed!r}",
        )


if __name__ == "__main__":
    unittest.main()
