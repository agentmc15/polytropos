"""Stdlib unittest regression suite for bin/docs_build.py.

bin/ is not a package; docs_build.py is loaded via importlib by absolute path
computed from this file's own location, per PLAN.md D2 (same convention as
tests/test_harness_select.py's `_load` helper).
"""

import importlib.util
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
    """Create <root>/<harness_dir>/<name>/SKILL.md with the given frontmatter lines
    (each a raw line between the --- fences) and body, plus optional references/
    files (a dict of relative-path -> text)."""
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


def _make_empty_roots(tmp_path):
    """Create empty (no skills yet) roots for all three harnesses under tmp_path."""
    for harness_dir in ("skills", "copilot/.github/skills", "codex/skills"):
        (tmp_path / harness_dir).mkdir(parents=True, exist_ok=True)
    return tmp_path


class SkillInventoryShapeTests(unittest.TestCase):
    def test_shape_sort_order_and_references(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = _make_empty_roots(Path(tmp_s))
            _write_skill(
                tmp, "skills", "zeta",
                ["name: zeta", "description: The zeta skill."],
                body="# Zeta\n\nZeta body.\n",
            )
            _write_skill(
                tmp, "skills", "alpha",
                ["name: alpha", "description: The alpha skill."],
                body="# Alpha\n\nAlpha body.\n",
                references={"deep.md": "deep ref", "sub/other.md": "sub ref"},
            )
            _write_skill(
                tmp, "copilot/.github/skills", "widget",
                ["name: widget", "description: The widget skill."],
            )
            _write_skill(
                tmp, "codex/skills", "gadget",
                ["name: gadget", "description: The gadget skill."],
            )

            records = db.skill_inventory(tmp)

            # sorted by (harness, name): claude < codex < copilot alphabetically
            keys = [(r["harness"], r["name"]) for r in records]
            self.assertEqual(
                keys,
                [
                    ("claude", "alpha"),
                    ("claude", "zeta"),
                    ("codex", "gadget"),
                    ("copilot", "widget"),
                ],
            )

            alpha = records[0]
            self.assertEqual(alpha["skill_path"], "skills/alpha/SKILL.md")
            self.assertEqual(alpha["description"], "The alpha skill.")
            self.assertIn("Alpha body.", alpha["body"])
            self.assertNotIn("---", alpha["body"])
            self.assertEqual(
                alpha["references"],
                ["skills/alpha/references/deep.md", "skills/alpha/references/sub/other.md"],
            )

            zeta = records[1]
            self.assertEqual(zeta["references"], [])

    def test_missing_skill_root_raises(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            # only create two of the three roots
            (tmp / "skills").mkdir(parents=True)
            (tmp / "codex" / "skills").mkdir(parents=True)
            with self.assertRaises(ValueError):
                db.skill_inventory(tmp)

    def test_missing_skill_md_raises_naming_path(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = _make_empty_roots(Path(tmp_s))
            (tmp / "skills" / "broken").mkdir(parents=True)
            with self.assertRaises(ValueError) as ctx:
                db.skill_inventory(tmp)
            self.assertIn(str(tmp / "skills" / "broken" / "SKILL.md"), str(ctx.exception))

    def test_name_mismatch_raises_naming_path(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = _make_empty_roots(Path(tmp_s))
            _write_skill(
                tmp, "skills", "actual-dir-name",
                ["name: wrong-name", "description: Something."],
            )
            with self.assertRaises(ValueError) as ctx:
                db.skill_inventory(tmp)
            self.assertIn(
                str(tmp / "skills" / "actual-dir-name" / "SKILL.md"), str(ctx.exception)
            )

    def test_empty_description_raises_naming_path(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = _make_empty_roots(Path(tmp_s))
            _write_skill(tmp, "skills", "hollow", ["name: hollow", "description:"])
            with self.assertRaises(ValueError) as ctx:
                db.skill_inventory(tmp)
            self.assertIn(str(tmp / "skills" / "hollow" / "SKILL.md"), str(ctx.exception))


class FrontmatterShapeTests(unittest.TestCase):
    def test_claude_shape_name_description_allowed_tools(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = _make_empty_roots(Path(tmp_s))
            _write_skill(
                tmp, "skills", "toolful",
                [
                    "name: toolful",
                    "description: Does a thing with tools.",
                    "allowed-tools: Bash, Read",
                ],
                body="# Toolful\n\nUses tools.\n",
            )
            records = db.skill_inventory(tmp)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["description"], "Does a thing with tools.")
            self.assertIn("Uses tools.", records[0]["body"])

    def test_copilot_shape_name_description_only(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = _make_empty_roots(Path(tmp_s))
            _write_skill(
                tmp, "copilot/.github/skills", "plain",
                ["name: plain", "description: A plain Copilot skill."],
                body="Plain body.\n",
            )
            records = db.skill_inventory(tmp)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["description"], "A plain Copilot skill.")

    def test_codex_shape_nested_metadata_block(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = _make_empty_roots(Path(tmp_s))
            _write_skill(
                tmp, "codex/skills", "nested",
                [
                    "name: nested",
                    "description: Has a nested metadata block.",
                    "metadata:",
                    "  short-description: shrt",
                ],
                body="# Nested\n\nNested body.\n",
            )
            records = db.skill_inventory(tmp)
            self.assertEqual(len(records), 1)
            record = records[0]
            self.assertEqual(record["name"], "nested")
            self.assertEqual(record["description"], "Has a nested metadata block.")
            self.assertIn("Nested body.", record["body"])
            self.assertNotIn("short-description", record["body"])


class DemoteHeadingsTests(unittest.TestCase):
    def test_demotes_and_caps_and_ignores_fences(self):
        text = (
            "# Title\n"
            "## Sub\n"
            "###### Already H6\n"
            "\n"
            "```\n"
            "# not a heading, inside a fence\n"
            "```\n"
            "\n"
            "# Real heading after fence\n"
        )
        result = db.demote_headings(text)
        lines = result.splitlines()
        self.assertEqual(lines[0], "## Title")
        self.assertEqual(lines[1], "### Sub")
        self.assertEqual(lines[2], "###### Already H6")
        # fenced content untouched
        self.assertIn("# not a heading, inside a fence", result)
        self.assertNotIn("## not a heading, inside a fence", result)
        # heading after the closed fence is still demoted
        self.assertIn("## Real heading after fence", result)

    def test_tilde_fence_also_respected(self):
        text = "~~~\n# inside tilde fence\n~~~\n# outside\n"
        result = db.demote_headings(text)
        self.assertIn("# inside tilde fence", result)
        self.assertIn("## outside", result)

    def test_non_heading_hash_lines_untouched(self):
        text = "#no-space-not-a-heading\n"
        result = db.demote_headings(text)
        self.assertEqual(result, text)


class RewriteLinksTests(unittest.TestCase):
    def setUp(self):
        self.blob_base = db.GITHUB_BLOB_BASE

    def test_external_and_mailto_untouched(self):
        text = "[ext](https://example.com/x) and [mail](mailto:a@b.com)\n"
        result = db.rewrite_links(text, "docs", self.blob_base, {})
        self.assertEqual(result, text)

    def test_anchor_only_untouched(self):
        text = "[jump](#section-name)\n"
        result = db.rewrite_links(text, "docs", self.blob_base, {})
        self.assertEqual(result, text)

    def test_page_map_hit(self):
        text = "See [the guide](GUIDE.md) for more.\n"
        page_map = {"docs/GUIDE.md": "deep-dives/guide.md"}
        result = db.rewrite_links(text, "docs", self.blob_base, page_map)
        self.assertIn("[the guide](deep-dives/guide.md)", result)

    def test_blob_fallback(self):
        text = "See [pricing](../../data/pricing.json).\n"
        result = db.rewrite_links(text, "skills/route", self.blob_base, {})
        self.assertIn(f"[pricing]({self.blob_base}data/pricing.json)", result)

    def test_fragment_preserved_on_blob_fallback(self):
        text = "See [sibling step](../fable-check/SKILL.md#step-1).\n"
        result = db.rewrite_links(text, "skills/route", self.blob_base, {})
        self.assertIn(
            f"[sibling step]({self.blob_base}skills/fable-check/SKILL.md#step-1)", result
        )

    def test_fragment_preserved_on_page_map_hit(self):
        text = "[other doc](OTHER.md#anchor)\n"
        page_map = {"docs/OTHER.md": "deep-dives/other.md"}
        result = db.rewrite_links(text, "docs", self.blob_base, page_map)
        self.assertIn("[other doc](deep-dives/other.md#anchor)", result)

    def test_fenced_content_untouched(self):
        text = "```\n[not a real link](./nope.md)\n```\n"
        result = db.rewrite_links(text, "docs", self.blob_base, {})
        self.assertEqual(result, text)

    def test_repo_escaping_target_untouched(self):
        text = "[escape](../../../etc/passwd)\n"
        result = db.rewrite_links(text, "skills/route", self.blob_base, {})
        self.assertEqual(result, text)

    def test_reference_style_links_not_rewritten(self):
        text = "[text][label]\n\n[label]: GUIDE.md\n"
        page_map = {"docs/GUIDE.md": "deep-dives/guide.md"}
        result = db.rewrite_links(text, "docs", self.blob_base, page_map)
        self.assertEqual(result, text)


class LiveTreeInventoryTests(unittest.TestCase):
    def test_real_repo_counts_and_known_skills_present(self):
        records = db.skill_inventory(REPO_ROOT)
        harnesses = [r["harness"] for r in records]
        self.assertEqual(harnesses.count("claude"), 14)
        self.assertEqual(harnesses.count("copilot"), 13)
        self.assertEqual(harnesses.count("codex"), 12)
        pairs = {(r["harness"], r["name"]) for r in records}
        self.assertIn(("claude", "route"), pairs)
        self.assertIn(("copilot", "budget"), pairs)
        self.assertIn(("codex", "doctor"), pairs)


class IntrospectionGuardTests(unittest.TestCase):
    def test_no_banned_calls_anywhere_in_module_source(self):
        source = (BIN_DIR / "docs_build.py").read_text(encoding="utf-8")
        for banned in ("Path.home", "subprocess", "urlopen", "random.", "time.time", "date.today"):
            self.assertNotIn(banned, source)


def _record(harness, name, description="A skill.", body="Body text.\n", references=None):
    """Build one synthetic skill_inventory()-shaped record for the render-function
    tests below, without touching a filesystem. skill_path mirrors the real
    per-harness root layout via the module's own _HARNESS_SKILL_ROOTS constant."""
    root = "/".join(db._HARNESS_SKILL_ROOTS[harness])
    return {
        "harness": harness,
        "name": name,
        "skill_path": f"{root}/{name}/SKILL.md",
        "description": description,
        "body": body,
        "references": references or [],
    }


# ---------------------------------------------------------------------------
# F1 regression: a 4-backtick fence must not be closed by an inner 3-backtick
# line. Live shape: copilot/.github/skills/architect/SKILL.md:33 opens a
# ````markdown fence containing a **Verify.** section whose own ```bash fence
# was wrongly treated as closing the OUTER fence by the old (stripped[:3])
# implementation.
# ---------------------------------------------------------------------------


class NestedFenceLengthRegressionTests(unittest.TestCase):
    NESTED_TEXT = (
        "````markdown\n"                                              # 0
        "### T1 — Short title\n"                                      # 1
        "\n"                                                          # 2
        "**Verify.**\n"                                               # 3
        "```bash\n"                                                   # 4
        "# not a real heading, this is inside the inner fence\n"      # 5
        "[not a real link](./nope.md)\n"                              # 6
        "```\n"                                                       # 7
        "````\n"                                                      # 8
        "\n"                                                          # 9
        "# Real heading after the outer fence closes\n"                # 10
    )

    def test_fence_flags_span_the_whole_outer_fence(self):
        lines = self.NESTED_TEXT.splitlines(keepends=True)
        flags = db._fence_flags(lines)
        for i in range(0, 9):
            self.assertTrue(flags[i], f"line {i} should be in-fence: {lines[i]!r}")
        self.assertFalse(flags[9])
        self.assertFalse(flags[10])

    def test_demote_headings_ignores_everything_inside_outer_fence(self):
        result = db.demote_headings(self.NESTED_TEXT)
        # the inner "### T1 — Short title" is untouched (still h3, not h4)
        self.assertIn("### T1 — Short title", result)
        self.assertNotIn("#### T1", result)
        # the inner "#" line inside the ```bash block is not a real heading
        self.assertIn("# not a real heading, this is inside the inner fence", result)
        self.assertNotIn("## not a real heading", result)
        # only the heading AFTER the outer fence closes gets demoted
        self.assertIn("## Real heading after the outer fence closes", result)

    def test_rewrite_links_ignores_link_inside_outer_fence(self):
        result = db.rewrite_links(self.NESTED_TEXT, "docs", db.GITHUB_BLOB_BASE, {})
        self.assertIn("[not a real link](./nope.md)", result)
        self.assertNotIn(db.GITHUB_BLOB_BASE, result)


# ---------------------------------------------------------------------------
# F2: strip exactly one leading body h1 before demoting.
# ---------------------------------------------------------------------------


class StripLeadingH1Tests(unittest.TestCase):
    def test_strips_single_leading_h1(self):
        text = "# Title\n\nBody line.\n"
        self.assertEqual(db._strip_leading_h1(text), "\nBody line.\n")

    def test_strips_leading_h1_after_blank_lines(self):
        text = "\n\n# Title\n\nBody line.\n"
        self.assertEqual(db._strip_leading_h1(text), "\nBody line.\n")

    def test_no_leading_h1_returned_unchanged(self):
        text = "Some intro.\n\n## Sub\n"
        self.assertEqual(db._strip_leading_h1(text), text)

    def test_leading_h2_not_stripped(self):
        text = "## Not an h1\n\nBody.\n"
        self.assertEqual(db._strip_leading_h1(text), text)

    def test_only_the_first_h1_is_stripped(self):
        text = "# First\n\n# Second h1 stays\n"
        result = db._strip_leading_h1(text)
        self.assertNotIn("# First", result)
        self.assertIn("# Second h1 stays", result)


# ---------------------------------------------------------------------------
# render_skill_page: element order, fragment splicing, sibling links, body
# transform (leading-h1 strip + demote + rewrite), determinism.
# ---------------------------------------------------------------------------


class RenderSkillPageTests(unittest.TestCase):
    def test_element_order_without_fragment(self):
        record = _record("claude", "widget", description="Does widget things.")
        page = db.render_skill_page(record, None, [record], {})

        h1_idx = page.index("# widget — Claude Code")
        prov_idx = page.index(
            "<!-- GENERATED by bin/docs_build.py from skills/widget/SKILL.md"
        )
        desc_idx = page.index("> Does widget things.")
        source_idx = page.index("**Source:**")
        also_idx = page.index("**Also available on:**")
        card_idx = page.index("## The skill card — what the model reads")

        self.assertTrue(
            h1_idx < prov_idx < desc_idx < source_idx < also_idx < card_idx
        )
        self.assertNotIn("## In practice", page)
        # F2: no references shipped -> the whole line is omitted, never "none"
        self.assertNotIn("References shipped with the skill", page)
        self.assertTrue(page.endswith("\n"))
        self.assertFalse(page.endswith("\n\n"))

    def test_element_order_with_fragment(self):
        record = _record(
            "claude", "widget", references=["skills/widget/references/deep.md"]
        )
        fragment = "### Worked example\n\nDo the thing.\n"
        page = db.render_skill_page(record, fragment, [record], {})

        refs_idx = page.index("**References shipped with the skill:**")
        practice_idx = page.index("## In practice")
        example_idx = page.index("### Worked example")
        card_idx = page.index("## The skill card — what the model reads")

        self.assertTrue(refs_idx < practice_idx < example_idx < card_idx)
        self.assertIn("Do the thing.", page)

    def test_body_leading_h1_stripped_then_demoted_and_links_rewritten(self):
        record = _record(
            "claude", "widget",
            body="# Widget\n\nSee [pricing](../../data/pricing.json).\n\n## Sub\n",
        )
        page = db.render_skill_page(record, None, [record], {})
        # the body's own leading h1 is gone entirely -- not merely demoted
        self.assertNotIn("# Widget", page)
        self.assertNotIn("## Widget", page)
        # the body's "## Sub" is demoted one level, landing inside the section
        self.assertIn("### Sub", page)
        self.assertIn(f"[pricing]({db.GITHUB_BLOB_BASE}data/pricing.json)", page)

    def test_body_without_leading_h1_is_only_demoted(self):
        record = _record("claude", "widget", body="Some intro text.\n\n## Sub\n")
        page = db.render_skill_page(record, None, [record], {})
        self.assertIn("Some intro text.", page)
        self.assertIn("### Sub", page)

    def test_no_references_omits_the_line_entirely(self):
        """F2: 36/39 skills ship no references/ dir; a 'none' line there reads
        as a deficit on every one of those pages, so the whole fact line is
        omitted rather than shown empty."""
        record = _record("claude", "widget", references=[])
        page = db.render_skill_page(record, None, [record], {})
        self.assertNotIn("References shipped with the skill", page)
        self.assertNotIn("none", page)

    def test_references_labeled_relative_to_skill_dir(self):
        """F2: a shipped reference is labeled with its path RELATIVE TO THE
        SKILL DIRECTORY (e.g. 'references/roles/scout.md'), not a bare
        filename -- so a skill with many references reads as a catalog."""
        record = _record(
            "claude", "widget",
            references=[
                "skills/widget/references/deep.md",
                "skills/widget/references/roles/scout.md",
            ],
        )
        page = db.render_skill_page(record, None, [record], {})
        self.assertIn(
            f"[references/deep.md]({db.GITHUB_BLOB_BASE}skills/widget/references/deep.md)",
            page,
        )
        self.assertIn(
            f"[references/roles/scout.md]"
            f"({db.GITHUB_BLOB_BASE}skills/widget/references/roles/scout.md)",
            page,
        )
        self.assertNotIn("[deep.md]", page)
        self.assertNotIn("[scout.md]", page)

    def test_rendering_twice_is_byte_identical(self):
        record = _record("claude", "widget", body="# Widget\n\nBody.\n")
        first = db.render_skill_page(record, "### Example\n\nX.\n", [record], {})
        second = db.render_skill_page(record, "### Example\n\nX.\n", [record], {})
        self.assertEqual(first, second)

    def test_canonical_page_map_relativized_from_skills_harness_depth(self):
        """page_map link rewriting at the 'skills/<harness>' depth (2 levels
        under docs-site/): render_skill_page must relativize the CANONICAL
        deep-dive map itself, against 'skills/claude', before rewrite_links
        ever sees it."""
        record = _record(
            "claude", "widget", body="# Widget\n\nSee [guide](../../docs/GUIDE.md).\n"
        )
        page_map = {"docs/GUIDE.md": "deep-dives/guide.md"}
        page = db.render_skill_page(record, None, [record], page_map)
        self.assertIn("[guide](../../deep-dives/guide.md)", page)

    def test_description_angle_brackets_escaped_in_blockquote(self):
        """F1: raw '<'/'>' in a generator-emitted description (e.g. a
        placeholder like 'tasks/kits/<slug>/') is parsed as literal (and
        browser-swallowed) inline HTML by a markdown renderer -- the
        blockquote must show '&lt;slug&gt;', not a bare '<slug>'."""
        record = _record(
            "claude", "widget",
            description="Writes tasks/kits/<slug>/ for the execute driver.",
        )
        page = db.render_skill_page(record, None, [record], {})
        self.assertIn("> Writes tasks/kits/&lt;slug&gt;/ for the execute driver.", page)
        self.assertNotIn("<slug>", page)

    def test_skill_card_note_states_the_full_transform_and_links_source(self):
        """F6: the note under '## The skill card' must plainly say the body is
        TRANSFORMED (leading title removed when present, headings demoted one
        level, relative links rewritten) -- not just mention path variables --
        and point at the linked, unmodified source."""
        record = _record("claude", "widget")
        page = db.render_skill_page(record, None, [record], {})
        card_idx = page.index("## The skill card — what the model reads")
        note_segment = page[card_idx:]
        self.assertIn("leading title", note_segment)
        self.assertIn("demoted one level", note_segment)
        self.assertIn("relative links are rewritten", note_segment)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}", note_segment)
        self.assertIn("{{POLYTROPOS_ROOT}}", note_segment)
        self.assertIn(
            f"unmodified original is [skills/widget/SKILL.md]"
            f"({db.GITHUB_BLOB_BASE}skills/widget/SKILL.md)",
            note_segment,
        )


class SiblingLinksTests(unittest.TestCase):
    def test_shared_name_across_all_three_harnesses_links_both_others(self):
        claude = _record("claude", "shared")
        copilot = _record("copilot", "shared")
        codex = _record("codex", "shared")
        inventory = [claude, copilot, codex]
        page = db.render_skill_page(claude, None, inventory, {})
        self.assertIn("[GitHub Copilot CLI](../copilot/shared.md)", page)
        self.assertIn("[OpenAI Codex CLI](../codex/shared.md)", page)
        self.assertNotIn("this harness only", page)

    def test_harness_only_name_points_at_parity_matrix(self):
        solo = _record("claude", "solo")
        page = db.render_skill_page(solo, None, [solo], {})
        self.assertIn(
            "this harness only — see the [parity matrix](../index.md)", page
        )


# ---------------------------------------------------------------------------
# render_harness_index
# ---------------------------------------------------------------------------


class RenderHarnessIndexTests(unittest.TestCase):
    def test_table_sorted_by_name_filtered_to_harness_no_fragment(self):
        zeta = _record("claude", "zeta", description="Zeta desc.")
        alpha = _record("claude", "alpha", description="Alpha desc.")
        other = _record("copilot", "other")
        page = db.render_harness_index("claude", [zeta, alpha, other], None)

        self.assertEqual(page.splitlines()[0], "# Claude Code")
        self.assertIn("<!-- GENERATED by bin/docs_build.py from skills", page)
        self.assertLess(page.index("alpha"), page.index("zeta"))
        self.assertIn("[alpha](alpha.md)", page)
        self.assertIn("[zeta](zeta.md)", page)
        self.assertNotIn("other", page)
        self.assertNotIn("## Using these skills", page)

    def test_index_fragment_spliced_under_heading(self):
        record = _record("claude", "alpha")
        page = db.render_harness_index("claude", [record], "### Tips\n\nUse it.\n")
        self.assertIn("## Using these skills", page)
        self.assertIn("### Tips", page)
        self.assertLess(page.index("## Using these skills"), page.index("### Tips"))

    def test_description_angle_brackets_escaped_in_table_cell(self):
        """F1: the harness-index table's description cell must escape raw
        '<'/'>' the same way the skill-page blockquote does."""
        record = _record(
            "claude", "widget",
            description="Writes tasks/kits/<slug>/ for the execute driver.",
        )
        page = db.render_harness_index("claude", [record], None)
        self.assertIn("tasks/kits/&lt;slug&gt;/", page)
        self.assertNotIn("<slug>", page)


# ---------------------------------------------------------------------------
# render_parity_page
# ---------------------------------------------------------------------------


class RenderParityPageTests(unittest.TestCase):
    def test_matrix_cells_link_or_dash(self):
        shared_claude = _record("claude", "shared")
        shared_codex = _record("codex", "shared")
        solo = _record("claude", "solo")
        inventory = [shared_claude, shared_codex, solo]
        page = db.render_parity_page(inventory, None)

        self.assertIn("# Skills across the three harnesses", page)
        self.assertIn(
            "| Skill | Claude Code | GitHub Copilot CLI | OpenAI Codex CLI |", page
        )
        self.assertIn("[shared](claude/shared.md)", page)
        self.assertIn("[shared](codex/shared.md)", page)
        self.assertIn("[solo](claude/solo.md)", page)
        solo_row = next(
            line for line in page.splitlines() if line.startswith("| solo ")
        )
        self.assertIn("—", solo_row)
        self.assertNotIn("[solo](copilot/solo.md)", page)
        self.assertNotIn("## Why the rosters differ", page)

    def test_names_derived_from_inventory_never_hardcoded(self):
        inventory = [_record("claude", "onlyone")]
        page = db.render_parity_page(inventory, None)
        self.assertIn("onlyone", page)

    def test_fragment_spliced_under_heading(self):
        inventory = [_record("claude", "onlyone")]
        page = db.render_parity_page(inventory, "### Rationale\n\nBecause.\n")
        self.assertIn("## Why the rosters differ", page)
        self.assertIn("### Rationale", page)
        self.assertLess(
            page.index("## Why the rosters differ"), page.index("### Rationale")
        )

    def test_rendering_twice_is_byte_identical(self):
        inventory = [_record("claude", "a"), _record("copilot", "b")]
        first = db.render_parity_page(inventory, None)
        second = db.render_parity_page(inventory, None)
        self.assertEqual(first, second)


# ---------------------------------------------------------------------------
# Fragments: validation, loading, orphan detection.
# ---------------------------------------------------------------------------


class FragmentValidationTests(unittest.TestCase):
    def test_h1_outside_fence_rejected(self):
        text = "### OK heading\n\n# Not allowed\n"
        with self.assertRaises(ValueError) as ctx:
            db.validate_fragment(text, "docs-src/fragments/skills/claude/widget.md")
        self.assertIn("docs-src/fragments/skills/claude/widget.md", str(ctx.exception))

    def test_h2_outside_fence_rejected(self):
        text = "## Not allowed either\n"
        with self.assertRaises(ValueError):
            db.validate_fragment(text, "docs-src/fragments/skills/claude/widget.md")

    def test_h3_is_allowed(self):
        text = "### Fine\n\nSome text.\n"
        db.validate_fragment(text, "docs-src/fragments/skills/claude/widget.md")

    def test_h2_inside_a_fence_is_allowed(self):
        text = (
            "### Worked example\n"
            "\n"
            "```markdown\n"
            "## This is example markdown text, not a real heading\n"
            "```\n"
        )
        db.validate_fragment(text, "docs-src/fragments/skills/claude/widget.md")

    def test_setext_h1_underline_rejected(self):
        """F10: 'Title' immediately followed by a line of only '=' characters
        is a CommonMark setext h1 -- validate_fragment previously only checked
        ATX '#'/'##' and would have let this slip an h1 into '## In
        practice'."""
        text = "### OK heading\n\nTitle\n=====\n"
        with self.assertRaises(ValueError) as ctx:
            db.validate_fragment(text, "docs-src/fragments/skills/claude/widget.md")
        self.assertIn("docs-src/fragments/skills/claude/widget.md", str(ctx.exception))

    def test_setext_h2_underline_rejected(self):
        """F10: 'Title' immediately followed by a line of only '-' characters
        is a CommonMark setext h2."""
        text = "### OK heading\n\nTitle\n-----\n"
        with self.assertRaises(ValueError):
            db.validate_fragment(text, "docs-src/fragments/skills/claude/widget.md")

    def test_setext_underline_inside_a_fence_is_allowed(self):
        text = (
            "### Worked example\n"
            "\n"
            "```text\n"
            "Title\n"
            "=====\n"
            "```\n"
        )
        db.validate_fragment(text, "docs-src/fragments/skills/claude/widget.md")

    def test_thematic_break_after_blank_line_is_not_a_setext_heading(self):
        """A '---' divider preceded by a BLANK line is a thematic break (a
        common section divider inside a fragment), not a setext underline --
        CommonMark requires the underline to immediately follow non-blank
        paragraph text, and validate_fragment must not over-reject this."""
        text = "### Section one\n\nSome text.\n\n---\n\n### Section two\n"
        db.validate_fragment(text, "docs-src/fragments/skills/claude/widget.md")

    def test_load_fragment_missing_file_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = db.load_fragment(
                Path(tmp), "docs-src/fragments/skills/claude/nope.md"
            )
            self.assertIsNone(result)

    def test_load_fragment_present_validates_and_returns_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rel = "docs-src/fragments/skills/claude/widget.md"
            path = root / rel
            path.parent.mkdir(parents=True)
            path.write_text("### Fine\n\nBody.\n", encoding="utf-8")
            self.assertEqual(db.load_fragment(root, rel), "### Fine\n\nBody.\n")

    def test_load_fragment_present_but_invalid_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rel = "docs-src/fragments/skills/claude/widget.md"
            path = root / rel
            path.parent.mkdir(parents=True)
            path.write_text("# Not allowed\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                db.load_fragment(root, rel)


class FragmentOrphanTests(unittest.TestCase):
    def test_orphan_skill_fragment_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "docs-src" / "fragments" / "skills" / "claude" / "nonexistent.md"
            path.parent.mkdir(parents=True)
            path.write_text("### Fine\n", encoding="utf-8")
            inventory = [_record("claude", "widget")]
            with self.assertRaises(ValueError) as ctx:
                db.check_fragment_orphans(root, inventory)
            self.assertIn("nonexistent", str(ctx.exception))

    def test_orphan_index_unknown_harness_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "docs-src" / "fragments" / "skills" / "bogus-harness" / "index.md"
            path.parent.mkdir(parents=True)
            path.write_text("### Fine\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                db.check_fragment_orphans(root, [])

    def test_matching_fragments_do_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_path = root / "docs-src" / "fragments" / "skills" / "claude" / "widget.md"
            skill_path.parent.mkdir(parents=True)
            skill_path.write_text("### Fine\n", encoding="utf-8")
            index_path = root / "docs-src" / "fragments" / "skills" / "claude" / "index.md"
            index_path.write_text("### Fine\n", encoding="utf-8")
            inventory = [_record("claude", "widget")]
            db.check_fragment_orphans(root, inventory)

    def test_missing_fragments_dir_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            db.check_fragment_orphans(Path(tmp), [])


# ---------------------------------------------------------------------------
# T6: deep-dive mirrors (docs/*.md -> docs-site/deep-dives/*.md).
# ---------------------------------------------------------------------------


class DeepDiveSlugTests(unittest.TestCase):
    def test_lowercases_stem(self):
        self.assertEqual(db.deep_dive_slug("COPILOT-HARNESS.md"), "copilot-harness")

    def test_already_lowercase_stem_unchanged(self):
        self.assertEqual(db.deep_dive_slug("guide.md"), "guide")

    def test_mixed_case_stem(self):
        self.assertEqual(db.deep_dive_slug("GUIDE.md"), "guide")


class ExtractTitleTests(unittest.TestCase):
    def test_extracts_first_h1(self):
        text = "# The Title\n\nBody.\n"
        self.assertEqual(db._extract_title(text, fallback="fallback.md"), "The Title")

    def test_skips_h1_inside_fence(self):
        text = "```\n# Not a real heading\n```\n# Real Title\n"
        self.assertEqual(db._extract_title(text, fallback="fallback.md"), "Real Title")

    def test_falls_back_to_filename_when_no_h1(self):
        text = "Some text with no heading at all.\n\n## Only an h2\n"
        self.assertEqual(db._extract_title(text, fallback="FALLBACK.md"), "FALLBACK.md")

    def test_h1_after_leading_blank_lines(self):
        text = "\n\n# Title After Blanks\n\nBody.\n"
        self.assertEqual(db._extract_title(text, fallback="x.md"), "Title After Blanks")


class DeepDivePageMapTests(unittest.TestCase):
    def test_slug_mapping_and_html_exclusion(self):
        """slug mapping + .html-exclusion: only docs/*.md is globbed; an
        arbitrary .html file is never auto-included, but the two explicitly
        pinned .html companions (guide.html, how-it-works.html) always are,
        mapped onto their .md sibling's mirror page."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs_dir = root / "docs"
            docs_dir.mkdir()
            (docs_dir / "COPILOT-HARNESS.md").write_text(
                "# The Copilot harness\n", encoding="utf-8"
            )
            (docs_dir / "guide.html").write_text("<html></html>", encoding="utf-8")
            (docs_dir / "how-it-works.html").write_text("<html></html>", encoding="utf-8")
            (docs_dir / "OTHER.html").write_text("<html></html>", encoding="utf-8")

            page_map = db.deep_dive_page_map(root)

            self.assertEqual(
                page_map["docs/COPILOT-HARNESS.md"], "deep-dives/copilot-harness.md"
            )
            self.assertEqual(page_map["docs/guide.html"], "deep-dives/guide.md")
            self.assertEqual(
                page_map["docs/how-it-works.html"], "deep-dives/how-it-works.md"
            )
            self.assertNotIn("docs/OTHER.html", page_map)
            self.assertEqual(len(page_map), 3)  # 1 .md + 2 pinned .html companions

    def test_derived_from_glob_never_hardcoded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs_dir = root / "docs"
            docs_dir.mkdir()
            (docs_dir / "BRAND-NEW-DOC.md").write_text("# Brand new\n", encoding="utf-8")
            page_map = db.deep_dive_page_map(root)
            self.assertEqual(
                page_map["docs/BRAND-NEW-DOC.md"], "deep-dives/brand-new-doc.md"
            )


class RelativizePageMapTests(unittest.TestCase):
    """page_map link rewriting at both depths."""

    def test_from_a_two_level_skills_subdirectory(self):
        page_map = {"docs/HOW-IT-WORKS.md": "deep-dives/how-it-works.md"}
        relative = db._relativize_page_map(page_map, "skills/claude")
        self.assertEqual(
            relative["docs/HOW-IT-WORKS.md"], "../../deep-dives/how-it-works.md"
        )

    def test_from_the_one_level_deep_dives_directory(self):
        page_map = {"docs/HOW-IT-WORKS.md": "deep-dives/how-it-works.md"}
        relative = db._relativize_page_map(page_map, "deep-dives")
        self.assertEqual(relative["docs/HOW-IT-WORKS.md"], "how-it-works.md")

    def test_empty_page_map_stays_empty(self):
        self.assertEqual(db._relativize_page_map({}, "skills/claude"), {})


class RenderDeepDivePageTests(unittest.TestCase):
    def test_provenance_note_and_headings_not_demoted(self):
        source_text = "# The Title\n\nBody text.\n\n## Sub\n"
        page = db.render_deep_dive_page("docs/EXAMPLE.md", source_text, {})
        self.assertIn("<!-- GENERATED by bin/docs_build.py from docs/EXAMPLE.md", page)
        self.assertIn(
            "Mirrored from `docs/EXAMPLE.md` — edit the source, then run "
            "`python3 bin/docs_build.py build`.",
            page,
        )
        # headings are NOT demoted -- the source's own h1/h2 stay exactly as-is
        self.assertIn("# The Title", page)
        self.assertIn("## Sub", page)
        self.assertNotIn("## The Title", page)
        self.assertNotIn("### Sub", page)

    def test_element_order(self):
        """F4: the 'Mirrored from ...' note (an admonition) now sits BELOW the
        source's own h1, not above it."""
        source_text = "# Title\n\nBody.\n"
        page = db.render_deep_dive_page("docs/EXAMPLE.md", source_text, {})
        prov_idx = page.index("<!-- GENERATED")
        h1_idx = page.index("# Title")
        note_idx = page.index("!!! note")
        mirrored_idx = page.index("Mirrored from")
        body_idx = page.index("Body.")
        self.assertTrue(prov_idx < h1_idx < note_idx < mirrored_idx < body_idx)

    def test_note_is_an_indented_admonition(self):
        """F4: rendered as an `!!! note` admonition block (the extension is
        already enabled in mkdocs.yml), not a bare paragraph line."""
        source_text = "# Title\n\nBody.\n"
        page = db.render_deep_dive_page("docs/EXAMPLE.md", source_text, {})
        self.assertIn(
            "!!! note\n    Mirrored from `docs/EXAMPLE.md` — edit the source, "
            "then run `python3 bin/docs_build.py build`.",
            page,
        )

    def test_no_leading_h1_falls_back_to_note_first(self):
        source_text = "Body with no heading at all.\n"
        page = db.render_deep_dive_page("docs/EXAMPLE.md", source_text, {})
        note_idx = page.index("!!! note")
        body_idx = page.index("Body with no heading")
        self.assertLess(note_idx, body_idx)

    def test_page_map_link_rewritten_relative_to_deep_dives(self):
        source_text = "# Title\n\nSee [other](OTHER.md).\n"
        page_map = {"docs/OTHER.md": "deep-dives/other.md"}
        page = db.render_deep_dive_page("docs/EXAMPLE.md", source_text, page_map)
        self.assertIn("[other](other.md)", page)

    def test_blob_fallback_for_non_mapped_relative_link(self):
        source_text = "# Title\n\nSee [skill](../skills/route/SKILL.md).\n"
        page = db.render_deep_dive_page("docs/EXAMPLE.md", source_text, {})
        self.assertIn(f"[skill]({db.GITHUB_BLOB_BASE}skills/route/SKILL.md)", page)

    def test_self_referencing_html_companion_link_is_dropped(self):
        """F3: when THIS page is exactly what the .html companion target
        rewrites to (a self-link), the link must be dropped -- rendered as
        plain text, never left as a link to itself."""
        source_text = "# Guide\n\nStyled: [guide.html](guide.html).\n"
        page_map = {"docs/guide.html": "deep-dives/guide.md"}
        page = db.render_deep_dive_page("docs/GUIDE.md", source_text, page_map)
        self.assertIn("Styled: guide.html.", page)
        self.assertNotIn("[guide.html]", page)
        self.assertNotIn("(guide.md)", page)

    def test_html_companion_link_to_a_different_page_still_resolves(self):
        """F3's converse: a link resolving to ANOTHER page (not the one being
        rendered) is an ordinary cross-page link and must NOT be dropped."""
        source_text = "# Other\n\nSee [how-it-works.html](how-it-works.html).\n"
        page_map = {"docs/how-it-works.html": "deep-dives/how-it-works.md"}
        page = db.render_deep_dive_page("docs/OTHER.md", source_text, page_map)
        self.assertIn("[how-it-works.html](how-it-works.md)", page)

    def test_two_links_to_the_same_other_page_both_stay_linked(self):
        """F3 explicitly allows two DIFFERENT links on a page resolving to the
        SAME other mirror -- only an actual self-link is neutralized."""
        source_text = (
            "# Other\n\n"
            "See [HOW-IT-WORKS.md](HOW-IT-WORKS.md) or "
            "[how-it-works.html](how-it-works.html).\n"
        )
        page_map = {
            "docs/HOW-IT-WORKS.md": "deep-dives/how-it-works.md",
            "docs/how-it-works.html": "deep-dives/how-it-works.md",
        }
        page = db.render_deep_dive_page("docs/OTHER.md", source_text, page_map)
        self.assertIn("[HOW-IT-WORKS.md](how-it-works.md)", page)
        self.assertIn("[how-it-works.html](how-it-works.md)", page)

    def test_rendering_twice_is_byte_identical(self):
        source_text = "# Title\n\nBody.\n"
        first = db.render_deep_dive_page("docs/EXAMPLE.md", source_text, {})
        second = db.render_deep_dive_page("docs/EXAMPLE.md", source_text, {})
        self.assertEqual(first, second)


class RenderDeepDiveIndexTests(unittest.TestCase):
    def test_element_order_and_rows_sorted_by_caller(self):
        entries = [("alpha", "Alpha Title"), ("zeta", "Zeta Title")]
        page = db.render_deep_dive_index(entries)
        self.assertTrue(page.startswith("# Deep dives"))
        self.assertIn("<!-- GENERATED by bin/docs_build.py from docs/*.md", page)
        self.assertIn("[Alpha Title](alpha.md)", page)
        self.assertIn("[Zeta Title](zeta.md)", page)
        self.assertLess(page.index("Alpha Title"), page.index("Zeta Title"))

    def test_single_column_no_duplicate_title_text(self):
        """F5: collapsed to a single column whose text is the title and whose
        target is the page -- not two columns each repeating the title."""
        entries = [("alpha", "Alpha Title")]
        page = db.render_deep_dive_index(entries)
        row = next(line for line in page.splitlines() if "Alpha Title" in line)
        self.assertEqual(row.count("Alpha Title"), 1)
        self.assertEqual(row, "| [Alpha Title](alpha.md) |")

    def test_rendering_twice_is_byte_identical(self):
        entries = [("alpha", "Alpha Title")]
        first = db.render_deep_dive_index(entries)
        second = db.render_deep_dive_index(entries)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
