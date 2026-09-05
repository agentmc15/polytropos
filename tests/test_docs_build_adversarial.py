"""Adversarial regression suite for bin/docs_build.py, written by the docs-site
kit's test-author role.

These tests are derived from the T1 brief's ACCEPTANCE criteria and pinned
contracts in .claude/kits/docs-site/TASKS.md — not from reading
bin/docs_build.py's implementation. They target edge cases the brief calls out
explicitly: mismatched fence markers (a ``` fence must not be closed by a
stray ~~~ line, and vice versa), the h6 heading cap, rewrite_links' full
branch set (page_map hits at different source depths, blob fallback,
fragment preservation, fenced-content exemption, repo-escaping targets,
reference-style links left alone), skill_inventory's three error paths naming
the offending path, sorted+recursive references, and the tri-shape
frontmatter parse (Claude / Copilot / Codex nested `metadata:` block).

bin/ is not a package; docs_build.py is loaded via importlib by absolute path,
same convention as tests/test_harness_select.py's `_load` helper.
"""

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


db = _load("docs_build")


def _write_skill(root, harness_dir, name, frontmatter_lines, body="Body text.\n", references=None):
    """Create <root>/<harness_dir>/<name>/SKILL.md with the given frontmatter
    lines (raw lines between the --- fences) and body, plus optional
    references/ files (a dict of relative-path -> text, may include nested
    subdirectories via '/' in the key)."""
    skill_dir = root / harness_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    content = "---\n" + "\n".join(frontmatter_lines) + "\n---\n\n" + body
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    if references:
        for rel, text in references.items():
            path = skill_dir / "references" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    return skill_dir


def _make_all_roots(root):
    """Create empty roots for all three harnesses so skill_inventory never
    trips over a missing root directory when a test only populates one."""
    (root / "skills").mkdir(parents=True, exist_ok=True)
    (root / "copilot" / ".github" / "skills").mkdir(parents=True, exist_ok=True)
    (root / "codex" / "skills").mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Fence machinery: mismatched fence markers must not cross-close.
# ---------------------------------------------------------------------------


class FenceMismatchTests(unittest.TestCase):
    def test_backtick_fence_not_closed_by_tilde(self):
        text = (
            "# Top\n"
            "\n"
            "```\n"
            "~~~\n"
            "# Inside\n"
            "```\n"
            "\n"
            "# Bottom\n"
        )
        expected = (
            "## Top\n"
            "\n"
            "```\n"
            "~~~\n"
            "# Inside\n"
            "```\n"
            "\n"
            "## Bottom\n"
        )
        self.assertEqual(db.demote_headings(text), expected)

    def test_tilde_fence_not_closed_by_backtick(self):
        text = (
            "# A\n"
            "~~~\n"
            "```\n"
            "# B\n"
            "~~~\n"
            "# C\n"
        )
        expected = (
            "## A\n"
            "~~~\n"
            "```\n"
            "# B\n"
            "~~~\n"
            "## C\n"
        )
        self.assertEqual(db.demote_headings(text), expected)


# ---------------------------------------------------------------------------
# Heading demotion: cap at h6, fence-exemption.
# ---------------------------------------------------------------------------


class HeadingCapTests(unittest.TestCase):
    def test_h1_demoted_to_h2(self):
        self.assertEqual(db.demote_headings("# One\n"), "## One\n")

    def test_h6_capped_not_h7(self):
        text = "###### Six\n"
        result = db.demote_headings(text)
        self.assertEqual(result, "###### Six\n")
        self.assertNotIn("#######", result)

    def test_h5_demoted_to_h6(self):
        self.assertEqual(db.demote_headings("##### Five\n"), "###### Five\n")

    def test_heading_inside_fence_untouched(self):
        text = "```\n# Not a heading here\n```\n# Real heading\n"
        expected = "```\n# Not a heading here\n```\n## Real heading\n"
        self.assertEqual(db.demote_headings(text), expected)


# ---------------------------------------------------------------------------
# rewrite_links: full branch coverage per the T1 brief.
# ---------------------------------------------------------------------------


class RewriteLinksTests(unittest.TestCase):
    def test_external_and_mailto_and_anchor_untouched(self):
        text = (
            "[ext](https://example.com/x)\n"
            "[mail](mailto:person@example.com)\n"
            "[anchor](#section)\n"
        )
        result = db.rewrite_links(text, "docs", db.GITHUB_BLOB_BASE, {})
        self.assertEqual(result, text)

    def test_page_map_hit_from_shallow_source_dir(self):
        page_map = {"docs/GUIDE.md": "deep-dives/guide.md"}
        text = "[g](GUIDE.md)\n"
        result = db.rewrite_links(text, "docs", db.GITHUB_BLOB_BASE, page_map)
        self.assertEqual(result, "[g](deep-dives/guide.md)\n")

    def test_page_map_hit_from_deep_source_dir(self):
        """Same page_map target, reached via relative '..' traversal from a
        skill two directories deep — proves resolution is depth-independent."""
        page_map = {"docs/GUIDE.md": "deep-dives/guide.md"}
        text = "[g](../../docs/GUIDE.md)\n"
        result = db.rewrite_links(text, "skills/route", db.GITHUB_BLOB_BASE, page_map)
        self.assertEqual(result, "[g](deep-dives/guide.md)\n")

    def test_fragment_preserved_on_page_map_hit(self):
        page_map = {"docs/GUIDE.md": "deep-dives/guide.md"}
        text = "[g](GUIDE.md#install)\n"
        result = db.rewrite_links(text, "docs", db.GITHUB_BLOB_BASE, page_map)
        self.assertEqual(result, "[g](deep-dives/guide.md#install)\n")

    def test_blob_fallback_when_not_in_page_map(self):
        text = "[r](../README.md)\n"
        result = db.rewrite_links(text, "docs", db.GITHUB_BLOB_BASE, {})
        self.assertEqual(result, f"[r]({db.GITHUB_BLOB_BASE}README.md)\n")

    def test_fragment_preserved_on_blob_fallback(self):
        text = "[r](../README.md#section)\n"
        result = db.rewrite_links(text, "docs", db.GITHUB_BLOB_BASE, {})
        self.assertEqual(result, f"[r]({db.GITHUB_BLOB_BASE}README.md#section)\n")

    def test_repo_escaping_target_untouched(self):
        text = "[out](../../outside.md)\n"
        result = db.rewrite_links(text, "docs", db.GITHUB_BLOB_BASE, {})
        self.assertEqual(result, text)

    def test_fenced_link_untouched_even_when_it_would_otherwise_rewrite(self):
        page_map = {"docs/GUIDE.md": "deep-dives/guide.md"}
        text = (
            "[live](GUIDE.md)\n"
            "\n"
            "```\n"
            "[dead](GUIDE.md)\n"
            "```\n"
        )
        expected = (
            "[live](deep-dives/guide.md)\n"
            "\n"
            "```\n"
            "[dead](GUIDE.md)\n"
            "```\n"
        )
        result = db.rewrite_links(text, "docs", db.GITHUB_BLOB_BASE, page_map)
        self.assertEqual(result, expected)

    def test_reference_style_links_not_rewritten(self):
        page_map = {"docs/GUIDE.md": "deep-dives/guide.md"}
        text = (
            "See [ref link][myref] and [inline](GUIDE.md).\n"
            "\n"
            "[myref]: GUIDE.md\n"
        )
        result = db.rewrite_links(text, "docs", db.GITHUB_BLOB_BASE, page_map)
        self.assertIn("[ref link][myref]", result)
        self.assertIn("[myref]: GUIDE.md", result)
        self.assertIn("[inline](deep-dives/guide.md)", result)


# ---------------------------------------------------------------------------
# skill_inventory: error paths, sorting, recursive references, tri-shape.
# ---------------------------------------------------------------------------


class SkillInventoryErrorTests(unittest.TestCase):
    def test_missing_skill_md_names_the_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_all_roots(root)
            (root / "skills" / "orphan").mkdir(parents=True)
            (root / "skills" / "orphan" / "notes.txt").write_text("stray file\n")
            with self.assertRaises(ValueError) as cm:
                db.skill_inventory(root)
            self.assertIn("orphan", str(cm.exception))

    def test_name_mismatch_names_the_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_all_roots(root)
            _write_skill(
                root, "skills", "foo",
                ["name: bar", "description: A thing."],
            )
            with self.assertRaises(ValueError) as cm:
                db.skill_inventory(root)
            self.assertIn("foo", str(cm.exception))

    def test_empty_description_names_the_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_all_roots(root)
            _write_skill(
                root, "skills", "foo",
                ["name: foo", 'description: ""'],
            )
            with self.assertRaises(ValueError) as cm:
                db.skill_inventory(root)
            self.assertIn("foo", str(cm.exception))


class SkillInventoryShapeTests(unittest.TestCase):
    def test_sorted_by_harness_then_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_all_roots(root)
            _write_skill(root, "skills", "zeta", ["name: zeta", "description: Z."])
            _write_skill(root, "skills", "alpha", ["name: alpha", "description: A."])
            _write_skill(root, "codex/skills", "mid", ["name: mid", "description: M."])
            _write_skill(root, "copilot/.github/skills", "mid", ["name: mid", "description: M."])
            records = db.skill_inventory(root)
            pairs = [(r["harness"], r["name"]) for r in records]
            self.assertEqual(pairs, sorted(pairs))
            self.assertIn(("claude", "alpha"), pairs)
            self.assertIn(("claude", "zeta"), pairs)

    def test_references_recursive_and_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_all_roots(root)
            _write_skill(
                root, "skills", "foo",
                ["name: foo", "description: A thing."],
                references={
                    "b_top.md": "top",
                    "sub/a_nested.md": "nested",
                    "sub/nested2/c_deep.md": "deep",
                },
            )
            records = db.skill_inventory(root)
            rec = next(r for r in records if r["name"] == "foo")
            self.assertEqual(
                rec["references"],
                [
                    "skills/foo/references/b_top.md",
                    "skills/foo/references/sub/a_nested.md",
                    "skills/foo/references/sub/nested2/c_deep.md",
                ],
            )

    def test_no_references_dir_yields_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_all_roots(root)
            _write_skill(root, "skills", "foo", ["name: foo", "description: A thing."])
            records = db.skill_inventory(root)
            rec = next(r for r in records if r["name"] == "foo")
            self.assertEqual(rec["references"], [])

    def test_tri_shape_frontmatter_all_parse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_all_roots(root)
            _write_skill(
                root, "skills", "cskill",
                ["name: cskill", "description: Claude shape.", "allowed-tools: Bash, Read"],
                body="# Claude body\n",
            )
            _write_skill(
                root, "copilot/.github/skills", "pskill",
                ["name: pskill", "description: Copilot shape."],
                body="# Copilot body\n",
            )
            _write_skill(
                root, "codex/skills", "xskill",
                ["name: xskill", "description: Codex shape.", "metadata:", "  short-description: short."],
                body="# Codex body\n",
            )
            records = {r["name"]: r for r in db.skill_inventory(root)}

            self.assertEqual(records["cskill"]["harness"], "claude")
            self.assertEqual(records["cskill"]["description"], "Claude shape.")
            self.assertIn("# Claude body", records["cskill"]["body"])

            self.assertEqual(records["pskill"]["harness"], "copilot")
            self.assertEqual(records["pskill"]["description"], "Copilot shape.")
            self.assertIn("# Copilot body", records["pskill"]["body"])

            self.assertEqual(records["xskill"]["harness"], "codex")
            self.assertEqual(records["xskill"]["description"], "Codex shape.")
            self.assertIn("# Codex body", records["xskill"]["body"])
            # The nested metadata: block must not leak into the body.
            self.assertNotIn("short-description", records["xskill"]["body"])
            self.assertNotIn("metadata:", records["xskill"]["body"])


class LiveTreeInventoryTests(unittest.TestCase):
    def test_real_repo_counts_and_known_skills_present(self):
        records = db.skill_inventory(REPO_ROOT)
        pairs = {(r["harness"], r["name"]) for r in records}
        counts = {"claude": 0, "copilot": 0, "codex": 0}
        for r in records:
            counts[r["harness"]] += 1
        self.assertEqual(counts["claude"], 14)
        self.assertEqual(counts["copilot"], 13)
        self.assertEqual(counts["codex"], 12)
        self.assertIn(("claude", "route"), pairs)
        self.assertIn(("copilot", "budget"), pairs)
        self.assertIn(("codex", "doctor"), pairs)


# ---------------------------------------------------------------------------
# T4 additions below: render_skill_page / render_harness_index /
# render_parity_page / fragment loading + orphan detection.
#
# Derived from the T4 brief (.claude/kits/docs-site/TASKS.md "### T4 — Page
# renderers...") plus PLAN.md D4/D5 and the Phase 1->2 carry-forward in
# NOTES.md (F1: fence run-length regression; F2: strip one leading body h1
# before demoting; F7: references block only when non-empty). These target
# gaps a straightforward implementation would miss and that the implementer's
# own tests/test_docs_build.py does not already cover: a name shared by
# EXACTLY two of the three harnesses (existing tests only cover "all three"
# and "harness-only"), a page_map hit reached through a link embedded INSIDE
# the SKILL.md body (existing tests only exercise the blob-fallback branch
# there), a second fence run-length pair (5-tick outer / 4-tick inner, plus
# the "longer run also closes" direction), the provenance-comment template
# being byte-identical in shape ACROSS the three different page kinds (not
# just present on each individually), the install-time-path-variable note
# line's presence and position, parity-matrix column POSITION correctness
# (not just substring presence), and a fragment path with a stray nested
# subdirectory under a harness.
# ---------------------------------------------------------------------------

_HARNESS_ROOT_PARTS = {
    "claude": ("skills",),
    "copilot": ("copilot", ".github", "skills"),
    "codex": ("codex", "skills"),
}


def _record(harness, name, description="A skill.", body="Body text.\n", references=None, skill_path=None):
    """Build a skill_inventory()-shaped record dict directly in memory (no
    filesystem) for exercising the T4 render functions in isolation. Skill
    roots mirror the T1-pinned harness roots so skill_path/source_dir
    resolution behaves exactly as it would for a real inventory record."""
    if skill_path is None:
        parts = _HARNESS_ROOT_PARTS[harness] + (name, "SKILL.md")
        skill_path = "/".join(parts)
    return {
        "harness": harness,
        "name": name,
        "skill_path": skill_path,
        "description": description,
        "body": body,
        "references": references or [],
    }


# ---------------------------------------------------------------------------
# F1 carry-forward: a second fence run-length pair distinct from the
# 4-backtick/3-backtick shape already regression-tested in
# tests/test_docs_build.py -- a 5-backtick fence containing a 4-backtick
# fence, plus the "closes on a longer run too" direction.
# ---------------------------------------------------------------------------


class FenceRunLengthVariantTests(unittest.TestCase):
    FIVE = "`" * 5
    FOUR = "`" * 4
    TEXT = (
        f"{FIVE}\n"
        f"{FOUR}\n"
        "# Not a real heading -- inside the outer 5-tick fence\n"
        "[not a real link](./nope.md)\n"
        f"{FOUR}\n"
        f"{FIVE}\n"
        "\n"
        "# Real heading after the outer fence closes\n"
    )

    def test_four_tick_inner_does_not_close_five_tick_outer(self):
        lines = self.TEXT.splitlines(keepends=True)
        flags = db._fence_flags(lines)
        for i in range(0, 6):
            self.assertTrue(flags[i], f"line {i} should be in-fence: {lines[i]!r}")
        self.assertFalse(flags[6])
        self.assertFalse(flags[7])

    def test_demote_headings_leaves_inner_heading_untouched(self):
        result = db.demote_headings(self.TEXT)
        self.assertIn(
            "# Not a real heading -- inside the outer 5-tick fence", result
        )
        self.assertNotIn("## Not a real heading", result)
        self.assertIn("## Real heading after the outer fence closes", result)

    def test_rewrite_links_leaves_inner_link_untouched(self):
        result = db.rewrite_links(self.TEXT, "docs", db.GITHUB_BLOB_BASE, {})
        self.assertIn("[not a real link](./nope.md)", result)
        self.assertNotIn(db.GITHUB_BLOB_BASE, result)

    def test_longer_closing_run_also_closes_the_fence(self):
        # "at least as long as the opener" means a run LONGER than the opener
        # closes it too -- six backticks closing a five-tick open.
        text = "`````\n# inside\n``````\n# outside\n"
        result = db.demote_headings(text)
        self.assertIn("# inside", result)
        self.assertNotIn("## inside", result)
        self.assertIn("## outside", result)


# ---------------------------------------------------------------------------
# Sibling links: the middle case between "all three harnesses" and
# "harness-only" that tests/test_docs_build.py does not cover -- a name
# present on EXACTLY two of the three harnesses.
# ---------------------------------------------------------------------------


class SiblingLinksExactlyTwoHarnessesTests(unittest.TestCase):
    def test_missing_third_harness_shows_one_sibling_only(self):
        claude = _record("claude", "dualskill")
        codex = _record("codex", "dualskill")
        inventory = [claude, codex]
        page = db.render_skill_page(claude, None, inventory, {})
        self.assertIn("[OpenAI Codex CLI](../codex/dualskill.md)", page)
        self.assertNotIn("copilot/dualskill.md", page)
        self.assertNotIn("this harness only", page)

    def test_rendering_the_other_side_links_back(self):
        claude = _record("claude", "dualskill")
        codex = _record("codex", "dualskill")
        inventory = [claude, codex]
        page = db.render_skill_page(codex, None, inventory, {})
        self.assertIn("[Claude Code](../claude/dualskill.md)", page)
        self.assertNotIn("copilot/dualskill.md", page)
        self.assertNotIn("this harness only", page)


# ---------------------------------------------------------------------------
# page_map hit reached through a link embedded INSIDE the SKILL.md body --
# proves render_skill_page wires source_dir (the skill's own directory) into
# rewrite_links correctly, not just the blob-fallback branch.
# ---------------------------------------------------------------------------


class PageMapHitInsideEmbeddedBodyTests(unittest.TestCase):
    def test_page_map_hit_resolves_from_skill_directory(self):
        """T6 update: render_skill_page relativizes the CANONICAL page_map it is
        handed against its own site directory ('skills/<harness>') before
        rewrite_links ever sees it -- brief-pinned example: from
        'skills/claude/route.md', 'docs/HOW-IT-WORKS.md' ->
        '../../deep-dives/how-it-works.md'. A T4-era version of this test
        expected the page_map value used verbatim ('deep-dives/guide.md'); T6's
        brief explicitly introduces per-page relative resolution, so the
        correct link from this claude-harness page is now relative to
        'skills/claude', i.e. '../../deep-dives/guide.md'."""
        record = _record(
            "claude", "widget",
            body="See the [full guide](../../docs/GUIDE.md) for background.\n",
        )
        page_map = {"docs/GUIDE.md": "deep-dives/guide.md"}
        page = db.render_skill_page(record, None, [record], page_map)
        self.assertIn("[full guide](../../deep-dives/guide.md)", page)
        self.assertNotIn(f"{db.GITHUB_BLOB_BASE}docs/GUIDE.md", page)

    def test_non_matching_page_map_still_falls_back_to_blob(self):
        record = _record(
            "claude", "widget",
            body="See [something else](../../docs/OTHER.md).\n",
        )
        page_map = {"docs/GUIDE.md": "deep-dives/guide.md"}
        page = db.render_skill_page(record, None, [record], page_map)
        self.assertIn(
            f"[something else]({db.GITHUB_BLOB_BASE}docs/OTHER.md)", page
        )


# ---------------------------------------------------------------------------
# The install-time path-variable note line (T4 brief element (f)): present,
# and positioned between the '## The skill card' heading and the transformed
# body -- not asserted anywhere in tests/test_docs_build.py.
# ---------------------------------------------------------------------------


class InstallTimeVariableNoteTests(unittest.TestCase):
    def test_note_mentions_both_variables_before_the_body(self):
        record = _record(
            "claude", "widget",
            body="SENTINEL_BODY_TEXT uses ${CLAUDE_PLUGIN_ROOT} internally.\n",
        )
        page = db.render_skill_page(record, None, [record], {})
        card_idx = page.index("## The skill card — what the model reads")
        segment_after_card = page[card_idx:]
        body_start_idx = segment_after_card.index("SENTINEL_BODY_TEXT")
        note_segment = segment_after_card[:body_start_idx]
        self.assertIn("${CLAUDE_PLUGIN_ROOT}", note_segment)
        self.assertIn("{{POLYTROPOS_ROOT}}", note_segment)


# ---------------------------------------------------------------------------
# Provenance comment: must be the same TEMPLATE (not just present) across all
# three different page kinds -- skill page, harness index, parity page.
# ---------------------------------------------------------------------------


class ProvenanceTemplateConsistencyTests(unittest.TestCase):
    _PREFIX = "<!-- GENERATED by bin/docs_build.py from "
    _SUFFIX = (
        " — do not edit; edit the source and run: "
        "python3 bin/docs_build.py build -->"
    )

    def _provenance_line(self, page):
        return next(
            line for line in page.splitlines() if line.startswith(self._PREFIX)
        )

    def test_skill_page_provenance_matches_template(self):
        record = _record("claude", "widget")
        page = db.render_skill_page(record, None, [record], {})
        line = self._provenance_line(page)
        self.assertTrue(line.endswith(self._SUFFIX))

    def test_harness_index_provenance_matches_template(self):
        record = _record("claude", "widget")
        page = db.render_harness_index("claude", [record], None)
        line = self._provenance_line(page)
        self.assertTrue(line.endswith(self._SUFFIX))

    def test_parity_page_provenance_matches_template(self):
        record = _record("claude", "widget")
        page = db.render_parity_page([record], None)
        line = self._provenance_line(page)
        self.assertTrue(line.endswith(self._SUFFIX))


# ---------------------------------------------------------------------------
# Determinism for render_harness_index (already covered for render_skill_page
# and render_parity_page in tests/test_docs_build.py, but not this one).
# ---------------------------------------------------------------------------


class DeterminismHarnessIndexTests(unittest.TestCase):
    def test_rendering_harness_index_twice_with_fragment_is_byte_identical(self):
        record = _record("claude", "alpha")
        fragment = "### Tips\n\nUse it well.\n"
        first = db.render_harness_index("claude", [record], fragment)
        second = db.render_harness_index("claude", [record], fragment)
        self.assertEqual(first, second)


# ---------------------------------------------------------------------------
# Parity matrix: cell correctness by COLUMN POSITION, not just substring
# presence -- catches a column-order bug a loose assertIn/assertNotIn check
# would miss (a dash landing in the wrong column while a link for that name
# still appears somewhere else on the page).
# ---------------------------------------------------------------------------


class RenderParityPageColumnPositionTests(unittest.TestCase):
    def _harness_cells(self, page, name):
        row = next(
            line for line in page.splitlines() if line.startswith(f"| {name} ")
        )
        parts = [c.strip() for c in row.split("|")][1:-1]
        return parts[1:]  # drop the leading name cell -> [claude, copilot, codex]

    def test_exactly_two_harnesses_dash_lands_in_missing_column(self):
        claude = _record("claude", "dualskill")
        codex = _record("codex", "dualskill")
        page = db.render_parity_page([claude, codex], None)
        cells = self._harness_cells(page, "dualskill")
        self.assertEqual(cells[0], "[dualskill](claude/dualskill.md)")
        self.assertEqual(cells[1], "—")
        self.assertEqual(cells[2], "[dualskill](codex/dualskill.md)")

    def test_copilot_only_skill_dash_lands_in_claude_and_codex_columns(self):
        copilot = _record("copilot", "soloskill")
        page = db.render_parity_page([copilot], None)
        cells = self._harness_cells(page, "soloskill")
        self.assertEqual(cells[0], "—")
        self.assertEqual(cells[1], "[soloskill](copilot/soloskill.md)")
        self.assertEqual(cells[2], "—")


# ---------------------------------------------------------------------------
# Fragment path shape: a stray nested subdirectory under a harness (not
# exercised by tests/test_docs_build.py's orphan tests, which only cover a
# nonexistent skill name and an unknown harness for index.md).
# ---------------------------------------------------------------------------


class FragmentPathShapeTests(unittest.TestCase):
    def test_nested_subdirectory_under_harness_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = (
                root / "docs-src" / "fragments" / "skills" / "claude" / "sub"
                / "widget.md"
            )
            path.parent.mkdir(parents=True)
            path.write_text("### Fine\n", encoding="utf-8")
            inventory = [_record("claude", "widget")]
            with self.assertRaises(ValueError) as cm:
                db.check_fragment_orphans(root, inventory)
            self.assertIn(
                "claude/sub/widget.md", str(cm.exception).replace("\\", "/")
            )


# ---------------------------------------------------------------------------
# T6 additions below: deep_dive_slug / _extract_title / deep_dive_page_map /
# _relativize_page_map / render_deep_dive_page / render_deep_dive_index.
#
# Derived from the T6 brief (.claude/kits/docs-site/TASKS.md "### T6 --
# Deep-dive mirrors: 24 docs/*.md onto the site") and PLAN.md D6 -- written
# from the brief's pinned contracts (slug = lowercased filename stem; title =
# source's first h1, falling back to the filename; page_map maps
# docs/<NAME>.md -> deep-dives/<slug>.md plus the two .html companions;
# page_map values are resolved to a RELATIVE link per rendered page depth;
# mirror pages transform the body with rewrite_links ONLY, headings NOT
# demoted; glob-derivation means a new docs/*.md file auto-joins the set) --
# not from reading bin/docs_build.py's implementation. Only `def` signature
# lines were consulted to call these functions correctly:
#   _relativize_page_map(page_map, from_dir)
#   _extract_title(text, fallback)
#   deep_dive_slug(md_filename)
#   deep_dive_page_map(repo_root=REPO_ROOT)
#   render_deep_dive_page(source_rel_path, source_text, page_map)
#   render_deep_dive_index(entries)
# ---------------------------------------------------------------------------


def _copy_real_dirs(tmp_path, names):
    """Copy the named real repo directories into tmp_path (the GUARDRAILS.md
    temp-copy recipe) -- never mutates anything under REPO_ROOT itself."""
    dest = Path(tmp_path)
    for name in names:
        shutil.copytree(REPO_ROOT / name, dest / name)
    return dest


class DeepDiveSlugEdgeCaseTests(unittest.TestCase):
    """Brief: 'slug = lowercased filename stem: COPILOT-HARNESS.md ->
    copilot-harness.md' -- a stem, so the .md extension is stripped, not just
    lowercased in place. Edge cases the brief's single worked example doesn't
    exercise: a stem that is ALREADY lowercase (must not be mangled), and a
    stem containing interior dots (only the trailing .md suffix comes off --
    a naive `name.split('.')[0]` implementation would wrongly truncate at the
    FIRST dot)."""

    def test_uppercase_stem_lowercased(self):
        self.assertEqual(db.deep_dive_slug("COPILOT-HARNESS.md"), "copilot-harness")

    def test_already_lowercase_stem_unchanged(self):
        self.assertEqual(db.deep_dive_slug("guide.md"), "guide")

    def test_stem_with_interior_dots_preserves_them(self):
        self.assertEqual(db.deep_dive_slug("SOME.THING.V2.md"), "some.thing.v2")


class ExtractTitleFenceTests(unittest.TestCase):
    """Brief: 'title = the text of the source's first h1 line, falling back
    to the filename'. Adversarial case: the first '# ' line in the document
    is INSIDE a fenced code block -- that is not a real heading, so title
    extraction must either skip it and find the real h1 that follows, or (if
    no real h1 exists anywhere) fall back to the filename -- never return the
    fenced text as the title."""

    def test_extracts_first_real_h1(self):
        text = "# My Real Title\n\nSome body text.\n"
        self.assertEqual(db._extract_title(text, "fallback.md"), "My Real Title")

    def test_h1_inside_fence_skipped_finds_real_h1_after_it(self):
        text = (
            "```\n"
            "# Not a real title\n"
            "```\n"
            "\n"
            "# Real Title\n"
        )
        self.assertEqual(db._extract_title(text, "fallback.md"), "Real Title")

    def test_h1_only_inside_fence_falls_back_to_filename(self):
        text = "```\n# Only Here, Inside A Fence\n```\n\nNo real heading.\n"
        self.assertEqual(db._extract_title(text, "ONLY.md"), "ONLY.md")

    def test_no_h1_anywhere_falls_back_to_filename(self):
        text = "Just a paragraph, no heading at all.\n"
        self.assertEqual(db._extract_title(text, "NOTITLE.md"), "NOTITLE.md")


class DeepDivePageMapRealTreeTests(unittest.TestCase):
    """Live-tree checks against deep_dive_page_map(REPO_ROOT) -- the brief's
    'docs/<NAME>.md -> deep-dives/<slug>.md for every mirrored source, plus
    docs/guide.html -> deep-dives/guide.md and docs/how-it-works.html ->
    deep-dives/how-it-works.md'."""

    def test_every_real_docs_md_source_is_mapped_with_lowercased_slug(self):
        page_map = db.deep_dive_page_map(REPO_ROOT)
        md_sources = sorted((REPO_ROOT / "docs").glob("*.md"))
        self.assertEqual(len(md_sources), 25)
        for path in md_sources:
            key = f"docs/{path.name}"
            expected_value = f"deep-dives/{path.stem.lower()}.md"
            self.assertIn(key, page_map)
            self.assertEqual(page_map[key], expected_value)

    def test_html_companions_map_to_md_mirror_pages(self):
        page_map = db.deep_dive_page_map(REPO_ROOT)
        self.assertEqual(page_map.get("docs/guide.html"), "deep-dives/guide.md")
        self.assertEqual(
            page_map.get("docs/how-it-works.html"), "deep-dives/how-it-works.md"
        )

    def test_no_page_map_value_ever_points_at_an_html_page(self):
        """The two .html sources are NOT mirrored as their own pages -- every
        page_map VALUE must end in .md, never .html, including for the two
        companion keys themselves."""
        page_map = db.deep_dive_page_map(REPO_ROOT)
        for value in page_map.values():
            self.assertTrue(value.endswith(".md"), f"non-.md page_map value: {value!r}")

    def test_page_map_has_exactly_27_entries(self):
        """25 docs/*.md sources + 2 .html companions = 27 keys; the .html
        files themselves never get an extra mirror page (26 pages: 25
        mirrors + 1 index, per the brief's 'Currently 24 sources -> 25
        pages')."""
        page_map = db.deep_dive_page_map(REPO_ROOT)
        self.assertEqual(len(page_map), 27)


class DeepDivesNeverMirrorHtmlFilesLiveTreeTests(unittest.TestCase):
    """Brief (PLAN D6): 'docs/guide.html and docs/how-it-works.html are left
    alone ... not mirrored'. Read-only check against the committed
    docs-site/deep-dives/ tree -- never mutates it."""

    def test_no_html_file_exists_under_deep_dives(self):
        deep_dives_dir = REPO_ROOT / "docs-site" / "deep-dives"
        html_files = list(deep_dives_dir.glob("*.html"))
        self.assertEqual(html_files, [])
        self.assertFalse((deep_dives_dir / "guide.html").exists())
        self.assertFalse((deep_dives_dir / "how-it-works.html").exists())


class RelativizePageMapDepthTests(unittest.TestCase):
    """Brief: 'page_map values must be resolved to correct RELATIVE links per
    rendered page (e.g. from deep-dives/guide.md, docs/HOW-IT-WORKS.md ->
    how-it-works.md; from skills/claude/route.md ->
    ../../deep-dives/how-it-works.md)' -- both pinned worked examples,
    verified directly against _relativize_page_map."""

    PAGE_MAP = {
        "docs/HOW-IT-WORKS.md": "deep-dives/how-it-works.md",
        "docs/GUIDE.md": "deep-dives/guide.md",
    }

    def test_relativize_from_deep_dives_depth_yields_bare_sibling_filename(self):
        result = db._relativize_page_map(self.PAGE_MAP, "deep-dives")
        self.assertEqual(result["docs/HOW-IT-WORKS.md"], "how-it-works.md")
        self.assertEqual(result["docs/GUIDE.md"], "guide.md")

    def test_relativize_from_skills_claude_depth_climbs_two_levels(self):
        result = db._relativize_page_map(self.PAGE_MAP, "skills/claude")
        self.assertEqual(
            result["docs/HOW-IT-WORKS.md"], "../../deep-dives/how-it-works.md"
        )
        self.assertEqual(result["docs/GUIDE.md"], "../../deep-dives/guide.md")


class RenderDeepDivePageContractTests(unittest.TestCase):
    """render_deep_dive_page(source_rel_path, source_text, page_map) --
    exercised directly against the brief's pinned behaviors for the renderer
    layer: headings NOT demoted, page_map relativized to the deep-dives
    depth with an anchor preserved, the .html-companion rewrite, and the
    fence-exemption carried through to this new code path."""

    FULL_PAGE_MAP = {
        "docs/GUIDE.md": "deep-dives/guide.md",
        "docs/HOW-IT-WORKS.md": "deep-dives/how-it-works.md",
        "docs/guide.html": "deep-dives/guide.md",
        "docs/how-it-works.html": "deep-dives/how-it-works.md",
    }

    def test_source_h1_stays_h1_not_demoted(self):
        source_text = "# Real Title\n\nBody paragraph.\n\n## A Subheading\n"
        page = db.render_deep_dive_page(
            "docs/SOMETHING.md", source_text, self.FULL_PAGE_MAP
        )
        self.assertIn("# Real Title", page)
        self.assertNotIn("## Real Title", page)
        self.assertIn("## A Subheading", page)
        self.assertNotIn("### A Subheading", page)

    def test_cross_doc_link_with_anchor_relativized_from_deep_dives_depth(self):
        source_text = "See [the guide](GUIDE.md#install) for setup steps.\n"
        page = db.render_deep_dive_page(
            "docs/HOW-IT-WORKS.md", source_text, self.FULL_PAGE_MAP
        )
        self.assertIn("[the guide](guide.md#install)", page)
        self.assertNotIn(db.GITHUB_BLOB_BASE, page)

    def test_html_companion_link_rewritten_to_md_mirror_page(self):
        source_text = "See the [styled version](guide.html) of this page.\n"
        page = db.render_deep_dive_page(
            "docs/HOW-IT-WORKS.md", source_text, self.FULL_PAGE_MAP
        )
        self.assertIn("[styled version](guide.md)", page)
        self.assertNotIn("guide.html", page)

    def test_link_inside_fence_in_source_stays_literal(self):
        """No real docs/*.md source currently has a markdown link inside a
        fenced block (verified: none of the 24 real sources' fenced regions
        contain '](' ), so this uses realistic synthetic content styled after
        this repo's docs (a fenced example block) to prove the fence
        exemption survives the new render_deep_dive_page code path rather
        than being silently dropped by a re-implementation that doesn't
        reuse rewrite_links' fence detector."""
        source_text = (
            "# Doc Title\n"
            "\n"
            "See [the guide](GUIDE.md) for details.\n"
            "\n"
            "```\n"
            "Example text: [fake link](GUIDE.md) must stay literal in a fence.\n"
            "```\n"
        )
        page = db.render_deep_dive_page(
            "docs/HOW-IT-WORKS.md", source_text, self.FULL_PAGE_MAP
        )
        self.assertIn("[the guide](guide.md)", page)
        self.assertIn(
            "Example text: [fake link](GUIDE.md) must stay literal in a fence.", page
        )
        # The fenced copy must not have been rewritten to the relativized
        # mirror target either.
        self.assertEqual(page.count("[fake link](GUIDE.md)"), 1)


class FenceContentPreservedAcrossRealMirrorsLiveTreeTests(unittest.TestCase):
    """Real-tree complement to the synthetic fence test above: for every real
    docs/*.md source, every line the module's OWN fence-flag helper marks as
    fenced must appear byte-identical inside the committed mirror page under
    docs-site/deep-dives/ -- proving fenced content (whatever it contains) was
    never touched by the mirror pipeline against actual repo content, not
    just a synthetic fixture. Read-only; never mutates the committed tree."""

    def test_fenced_lines_are_byte_identical_in_every_real_mirror(self):
        md_sources = sorted((REPO_ROOT / "docs").glob("*.md"))
        self.assertTrue(md_sources)
        checked_any_fenced_line = False
        for source_path in md_sources:
            slug = db.deep_dive_slug(source_path.name)
            mirror_path = REPO_ROOT / "docs-site" / "deep-dives" / f"{slug}.md"
            self.assertTrue(mirror_path.exists(), f"missing mirror for {source_path.name}")
            source_text = source_path.read_text(encoding="utf-8")
            mirror_text = mirror_path.read_text(encoding="utf-8")
            lines = source_text.splitlines(keepends=True)
            flags = db._fence_flags(lines)
            for line, fenced in zip(lines, flags):
                if fenced and line.strip():
                    checked_any_fenced_line = True
                    self.assertIn(
                        line.rstrip("\n"),
                        mirror_text,
                        f"fenced line from {source_path.name} not preserved verbatim in {slug}.md",
                    )
        self.assertTrue(
            checked_any_fenced_line,
            "no fenced content found across any real docs/*.md source -- test would be vacuous",
        )


class RenderDeepDiveIndexDeterminismTests(unittest.TestCase):
    """Brief-implied (kit scope note: 'determinism of render_deep_dive_index')
    -- rendering the same entries twice must be byte-identical, matching the
    byte-stability contract (GUARDRAILS.md: 'If two consecutive build runs
    differ, that is a bug to fix before anything else')."""

    def test_rendering_twice_is_byte_identical(self):
        entries = [
            ("Guide", "guide.md"),
            ("How It Works", "how-it-works.md"),
        ]
        first = db.render_deep_dive_index(entries)
        second = db.render_deep_dive_index(entries)
        self.assertEqual(first, second)


class DeepDiveGlobDerivationExtraFileTests(unittest.TestCase):
    """Brief: 'DERIVE the set from a docs/ glob, never a hardcoded list, so a
    future doc auto-joins'. Proves it on a temp COPY of the real repo's
    skills/copilot/codex/docs directories plus one extra docs/NEW-THING.md --
    expected_pages() must grow by exactly one mirror page (26 -> 27 deep-dive
    pages; 69 -> 70 total), never touching the real tracked docs/ dir."""

    def test_extra_doc_file_yields_a_27th_mirror_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _copy_real_dirs(tmp, ("skills", "copilot", "codex", "docs"))
            baseline = db.expected_pages(root)
            self.assertEqual(len(baseline), 69)

            (root / "docs" / "NEW-THING.md").write_text(
                "# New Thing\n\nA brand-new doc.\n", encoding="utf-8"
            )

            grown = db.expected_pages(root)
            self.assertEqual(len(grown), 70)
            self.assertIn("docs-site/deep-dives/new-thing.md", grown)


# ---------------------------------------------------------------------------
# T6b additions below: the seven renderer fixes from the Phase 2 review
# (.claude/kits/docs-site/TASKS.md "### T6b -- Renderer fixes from the Phase
# 2 review"). Written from that brief's seven numbered fix descriptions --
# each test's docstring quotes the exact acceptance line it targets -- with
# only function signatures/bodies consulted afterward to wire the calls
# correctly, per this file's own stated convention above.
# ---------------------------------------------------------------------------


class EscapeGeneratorTextTests(unittest.TestCase):
    """F1: 'Generator-emitted description text renders <slug> as raw inline
    HTML ... Escape < / > in the description text THE GENERATOR ITSELF emits
    -- the blockquote on skill pages and the description cells of
    harness-index and parity tables. Do NOT touch embedded skill-card
    bodies (that is source content, not generator text).'

    Note: as actually pinned by T4's render_parity_page contract, the parity
    matrix has no description column at all (cells are only a link or '--'),
    so 'the description cells of ... parity tables' in the F1 line has no
    corresponding surface to test -- see this run's final report for that
    discrepancy. The two real surfaces (skill-page blockquote, harness-index
    description cell) are covered below.
    """

    def test_angle_brackets_escaped_in_skill_page_blockquote(self):
        record = _record(
            "claude", "widget",
            description="See tasks/kits/<slug>/ for the path.",
        )
        page = db.render_skill_page(record, None, [record], {})
        self.assertIn("tasks/kits/&lt;slug&gt;/", page)
        self.assertNotIn("tasks/kits/<slug>/", page)

    def test_angle_brackets_escaped_in_harness_index_description_cell(self):
        record = _record(
            "claude", "widget",
            description="See tasks/kits/<slug>/ for the path.",
        )
        page = db.render_harness_index("claude", [record], None)
        self.assertIn("tasks/kits/&lt;slug&gt;/", page)
        self.assertNotIn("tasks/kits/<slug>/", page)

    def test_already_escaped_entity_in_description_not_double_escaped(self):
        """Adversarial: a description already containing a literal '&lt;'
        sequence must not come out as '&amp;lt;' -- the fix is pinned to
        escaping '<'/'>' only, so an unrelated '&' must never be touched."""
        record = _record(
            "claude", "widget",
            description="Shows &lt;placeholder&gt; literally.",
        )
        page = db.render_skill_page(record, None, [record], {})
        self.assertIn("&lt;placeholder&gt;", page)
        self.assertNotIn("&amp;lt;", page)
        self.assertNotIn("&amp;gt;", page)

    def test_bare_ampersand_in_description_left_alone(self):
        """Adversarial: F1 pins escaping of '<'/'>' only -- a bare '&' with
        no angle bracket nearby is outside the fix's stated scope and must
        survive unmodified rather than being mangled into '&amp;'."""
        record = _record("claude", "widget", description="Route & estimate cost.")
        page = db.render_skill_page(record, None, [record], {})
        self.assertIn("Route & estimate cost.", page)

    def test_angle_bracket_escaped_in_table_cell_alongside_a_raw_pipe(self):
        """Adversarial: a description containing both '<' and a raw '|' in
        the same harness-index cell -- the '<' escaping must still fire
        (F1's actual scope), independent of whatever happens to the '|'
        (out of F1's stated scope, not asserted here)."""
        record = _record(
            "claude", "widget",
            description="Handles a < b | c cases.",
        )
        page = db.render_harness_index("claude", [record], None)
        self.assertIn("a &lt; b", page)

    def test_embedded_skill_card_body_angle_brackets_stay_raw(self):
        """F1: 'Do NOT touch embedded skill-card bodies (that is source
        content, not generator text)' -- a body containing a literal
        placeholder like '<slug>' must render UNescaped."""
        record = _record(
            "claude", "widget",
            body="Use `tasks/kits/<slug>/` as the destination path.\n",
        )
        page = db.render_skill_page(record, None, [record], {})
        self.assertIn("tasks/kits/<slug>/", page)
        self.assertNotIn("&lt;slug&gt;", page)


class ReferencesLineFormattingTests(unittest.TestCase):
    """F2: 'Omit the "References shipped with the skill" line entirely when
    a skill ships none ... When refs exist, label each with its path
    relative to the skill dir (references/roles/scout.md, not bare
    scout.md).'"""

    def test_empty_references_omits_the_line_entirely(self):
        record = _record("claude", "foo", references=[])
        block = db._facts_block(record, [record])
        self.assertNotIn("References shipped with the skill", block)

    def test_reference_two_directories_deep_labeled_relative_to_skill_dir(self):
        record = _record(
            "claude", "foo",
            references=["skills/foo/references/a/b/file.md"],
        )
        block = db._facts_block(record, [record])
        line = next(
            l for l in block.splitlines() if l.startswith("- **References shipped")
        )
        expected_link = (
            f"[references/a/b/file.md]({db.GITHUB_BLOB_BASE}"
            "skills/foo/references/a/b/file.md)"
        )
        self.assertEqual(
            line, f"- **References shipped with the skill:** {expected_link}"
        )

    def test_exactly_one_reference_formats_cleanly_with_no_stray_comma(self):
        record = _record(
            "claude", "foo",
            references=["skills/foo/references/only.md"],
        )
        block = db._facts_block(record, [record])
        line = next(
            l for l in block.splitlines() if l.startswith("- **References shipped")
        )
        expected_link = (
            f"[references/only.md]({db.GITHUB_BLOB_BASE}"
            "skills/foo/references/only.md)"
        )
        self.assertEqual(
            line, f"- **References shipped with the skill:** {expected_link}"
        )
        self.assertNotIn(",", line)


class SelfLinkNeutralizationTests(unittest.TestCase):
    """F3: 'When an .html companion target rewrites to the page currently
    being rendered, drop the link and render its label as plain text; when
    two links on a page would resolve to the same mirror, that is
    acceptable, but a page must never link to itself.'"""

    PAGE_MAP = {"docs/guide.html": "deep-dives/guide.md"}

    def test_self_link_with_anchor_still_neutralized(self):
        """Adversarial: does an anchor on the self-link (guide.html#top)
        still count as a self-link? The fragment is a location WITHIN the
        same page, so it must still be neutralized."""
        source_text = (
            "# Guide\n\n"
            "See the [styled version](guide.html#top) of this page.\n"
        )
        page = db.render_deep_dive_page("docs/GUIDE.md", source_text, self.PAGE_MAP)
        self.assertIn("See the styled version of this page.", page)
        self.assertNotIn("](guide.html", page)
        self.assertNotIn("](guide.md#top)", page)

    def test_self_link_inside_fence_stays_literal(self):
        """Adversarial: a self-link written inside a fenced code block must
        stay completely untouched -- the fence exemption applies
        unconditionally, before self-link neutralization ever runs."""
        source_text = (
            "# Guide\n\n"
            "```\n"
            "[styled version](guide.html)\n"
            "```\n"
        )
        page = db.render_deep_dive_page("docs/GUIDE.md", source_text, self.PAGE_MAP)
        self.assertIn("[styled version](guide.html)", page)

    def test_two_links_to_same_other_page_both_stay_linked(self):
        """F3: two links resolving to the same OTHER page is acceptable and
        must not be neutralized -- only a link to the CURRENT page is."""
        page_map = {"docs/OTHER.md": "deep-dives/other.md"}
        source_text = (
            "# Guide\n\n"
            "See [the other page](OTHER.md) and also "
            "[the other page again](OTHER.md#section).\n"
        )
        page = db.render_deep_dive_page("docs/GUIDE.md", source_text, page_map)
        self.assertIn("[the other page](other.md)", page)
        self.assertIn("[the other page again](other.md#section)", page)


class MirrorNotePlacementTests(unittest.TestCase):
    """F4: 'Move the "Mirrored from docs/X.md -- edit the source..." note
    BELOW the source's h1 and render it as an admonition (!!! note; the
    extension is already enabled in mkdocs.yml and unused)' -- falls back to
    note-first when a source has no h1."""

    def test_note_renders_as_admonition_below_the_h1(self):
        source_text = "# Real Title\n\nBody paragraph.\n"
        page = db.render_deep_dive_page("docs/SOMETHING.md", source_text, {})
        h1_idx = page.index("# Real Title")
        note_idx = page.index("!!! note")
        self.assertLess(h1_idx, note_idx, "note must render below the source h1")
        self.assertIn(
            "!!! note\n    Mirrored from `docs/SOMETHING.md`", page
        )

    def test_no_h1_anywhere_falls_back_to_note_first(self):
        source_text = "Just a paragraph, no heading at all.\n"
        page = db.render_deep_dive_page("docs/SOMETHING.md", source_text, {})
        note_idx = page.index("!!! note")
        body_idx = page.index("Just a paragraph")
        self.assertLess(note_idx, body_idx)

    def test_only_a_fenced_fake_h1_falls_back_to_note_first(self):
        """The document's ONLY '# ...'-shaped line is inside a fence -- that
        is not a real h1, so this must fall back to note-first exactly like
        the no-h1 case above, never mistaking fenced text for a title."""
        source_text = (
            "```\n"
            "# Fake heading, only ever appears inside this fence\n"
            "```\n"
            "\n"
            "No real heading anywhere in this document.\n"
        )
        page = db.render_deep_dive_page("docs/SOMETHING.md", source_text, {})
        note_idx = page.index("!!! note")
        body_idx = page.index("No real heading")
        self.assertLess(note_idx, body_idx)

    def test_real_h1_after_a_leading_fence_is_still_found(self):
        """Adversarial per the dispatch brief: 'a source whose first h1 [-
        shaped line] is inside a fence'. Here a FAKE heading inside a
        LEADING fence precedes the REAL h1 that follows, outside the fence.
        F4 requires the note to land below 'the source's h1' -- the genuine
        one, not the fenced decoy -- so the real h1 must still be found and
        the note must still land below it, not above everything."""
        source_text = (
            "```\n"
            "# Fake heading inside a fence, appears earlier in the raw text\n"
            "```\n"
            "\n"
            "# Real Title\n"
            "\n"
            "Body paragraph.\n"
        )
        page = db.render_deep_dive_page("docs/SOMETHING.md", source_text, {})
        real_h1_idx = page.index("# Real Title")
        note_idx = page.index("!!! note")
        self.assertLess(
            real_h1_idx, note_idx,
            "the note must render below the source's real h1, even when a "
            "fenced decoy heading appears earlier in the raw text",
        )


class DeepDiveIndexSingleColumnTests(unittest.TestCase):
    """F5: 'the deep-dive index is a single column' -- 'Collapse to a
    single column whose text is the title and whose target is the page.'"""

    def test_header_and_rows_have_exactly_one_column(self):
        entries = [("guide", "Guide"), ("how-it-works", "How It Works")]
        page = db.render_deep_dive_index(entries)
        table_lines = [l for l in page.splitlines() if l.startswith("|")]
        self.assertTrue(table_lines)
        for line in table_lines:
            cells = [c for c in line.strip("|").split("|")]
            self.assertEqual(
                len(cells), 1, f"expected exactly one column, got {line!r}"
            )
        self.assertIn("| [Guide](guide.md) |", page)


class SkillCardHonestyNoteTests(unittest.TestCase):
    """F6: 'the note line under "## The skill card -- what the model reads"
    currently mentions only path variables, but the generator also strips a
    leading h1 from 30/39 bodies, demotes every heading one level, and
    rewrites relative links. Extend the note to say so plainly and point at
    the linked source as the unmodified original.'"""

    def test_note_mentions_all_three_transforms_and_links_unmodified_source(self):
        record = _record(
            "claude", "widget",
            body="# Widget\n\nSENTINEL_BODY_TEXT with a [link](OTHER.md).\n",
        )
        page = db.render_skill_page(record, None, [record], {})
        card_idx = page.index("## The skill card")
        body_idx = page.index("SENTINEL_BODY_TEXT")
        note_segment = page[card_idx:body_idx]

        # Title strip.
        self.assertTrue(
            "leading" in note_segment
            and ("title" in note_segment or "heading" in note_segment),
            note_segment,
        )
        self.assertIn("remov", note_segment)  # removed / removes / removal
        # Heading demotion.
        self.assertIn("demot", note_segment)
        # Link rewriting.
        self.assertIn("link", note_segment)
        self.assertIn("rewrit", note_segment)
        # Points at the unmodified source.
        skill_path = record["skill_path"]
        self.assertIn(
            f"[{skill_path}]({db.GITHUB_BLOB_BASE}{skill_path})", note_segment
        )


class SetextFragmentHeadingTests(unittest.TestCase):
    """F10: 'validate_fragment rejects only ATX #/## -- a fragment using
    Title + ===== would emit an h1 inside ## In practice. Reject setext
    h1/h2 outside fences too' -- must NOT reject a thematic break (---
    preceded by a blank line) or a YAML-ish --- inside a fence."""

    def test_setext_h1_outside_fence_rejected(self):
        text = "### Intro\n\nSome Subtitle\n=====\n\nBody.\n"
        with self.assertRaises(ValueError):
            db.validate_fragment(text, "docs-src/fragments/x.md")

    def test_setext_h2_outside_fence_rejected(self):
        text = "### Intro\n\nAnother Subtitle\n-----\n\nBody.\n"
        with self.assertRaises(ValueError):
            db.validate_fragment(text, "docs-src/fragments/x.md")

    def test_dash_immediately_after_paragraph_no_blank_line_rejected(self):
        """The distinguishing adversarial case: '---' immediately after a
        paragraph line (no blank line between) is a setext h2 underline per
        CommonMark, and must be rejected."""
        text = "### Intro\n\nSome paragraph text.\n---\n\nMore text.\n"
        with self.assertRaises(ValueError):
            db.validate_fragment(text, "docs-src/fragments/x.md")

    def test_dash_after_a_blank_line_is_a_thematic_break_not_rejected(self):
        """The other half of the distinguishing case: '---' preceded by a
        BLANK line is a thematic break, not a heading, and must be allowed."""
        text = (
            "### Intro\n\nSome paragraph text.\n\n---\n\nMore text after a break.\n"
        )
        db.validate_fragment(text, "docs-src/fragments/x.md")  # must not raise

    def test_setext_markers_inside_tilde_fence_not_rejected(self):
        """A YAML-ish '---' (and setext-looking '-----' underline) inside a
        ~~~ fence must be exempt, same as ATX headings are."""
        text = (
            "### Config\n"
            "\n"
            "~~~\n"
            "Config\n"
            "-----\n"
            "~~~\n"
        )
        db.validate_fragment(text, "docs-src/fragments/x.md")  # must not raise


if __name__ == "__main__":
    unittest.main()
