"""Stdlib unittest regression suite for bin/copilot_docs.py (copilot-docs generator, T1 —
non-pricing foundation).

SAFETY CONTRACT: every test here uses a fresh ``tempfile.TemporaryDirectory()`` for any docs
root it touches; none reads or writes the real (not-yet-created) ``copilot-docs/`` directory at
the plugin root. ``bin/`` is not a package, so ``copilot_docs.py`` is loaded via importlib by
absolute path computed from this file's own location (``BIN_DIR``), mirroring
``tests/test_memory_store.py``.

Originally this suite was scoped to the non-pricing foundation only (manifest validation,
generated-block marker splicing, the bounded Markdown renderer, the HTML shell, link rewriting,
and pure artifact planning/writing/checking). The docs-aic-accounting task extends it with
pricing/prefs reuse, source-freshness hashing, generated-block providers, and per-document AIC
accounting — every fake model id/rate/prefs fixture below is synthetic; the only test that reads
the real ``data/pricing.copilot.json`` is the no-live-model-id-leak sweep.
"""

import importlib.util
import re
import tempfile
import unittest
from datetime import date
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cd = _load("copilot_docs")


def _minimal_manifest(**overrides):
    manifest = {
        "schema": "copilot-docs/v1",
        "source_sets": {"core": ["bin/copilot_docs.py"]},
        "documents": [
            {
                "markdown": "guide.md",
                "html": "guide.html",
                "title": "Guide",
                "authoring": {"mode": "deterministic"},
                "sources": ["core"],
            }
        ],
    }
    manifest.update(overrides)
    return manifest


class ManifestValidationTests(unittest.TestCase):
    def test_valid_minimal_manifest_round_trips_clean(self):
        with tempfile.TemporaryDirectory() as d:
            docs_root = Path(d) / "copilot-docs"
            errors = cd.validate_manifest(
                _minimal_manifest(), docs_root=docs_root, repo_root=Path(".")
            )
            self.assertEqual(errors, [])

    def test_rejects_absolute_markdown_path(self):
        manifest = _minimal_manifest()
        manifest["documents"][0]["markdown"] = "/etc/guide.md"
        errors = cd.validate_manifest(manifest)
        self.assertTrue(any("markdown" in e for e in errors))

    def test_rejects_absolute_html_path(self):
        manifest = _minimal_manifest()
        manifest["documents"][0]["html"] = "/etc/guide.html"
        errors = cd.validate_manifest(manifest)
        self.assertTrue(any("html" in e for e in errors))

    def test_rejects_dotdot_traversal_in_markdown(self):
        manifest = _minimal_manifest()
        manifest["documents"][0]["markdown"] = "../escape.md"
        errors = cd.validate_manifest(manifest)
        self.assertTrue(any("markdown" in e for e in errors))

    def test_rejects_dotdot_traversal_in_source_set(self):
        manifest = _minimal_manifest()
        manifest["source_sets"]["core"] = ["../../etc/passwd"]
        errors = cd.validate_manifest(manifest)
        self.assertTrue(any("source_sets" in e for e in errors))

    def test_rejects_duplicate_markdown_paths(self):
        manifest = _minimal_manifest()
        second = dict(manifest["documents"][0])
        second["html"] = "guide2.html"
        manifest["documents"].append(second)
        errors = cd.validate_manifest(manifest)
        self.assertTrue(any("duplicate markdown" in e for e in errors))

    def test_rejects_duplicate_html_paths(self):
        manifest = _minimal_manifest()
        second = dict(manifest["documents"][0])
        second["markdown"] = "guide2.md"
        manifest["documents"].append(second)
        errors = cd.validate_manifest(manifest)
        self.assertTrue(any("duplicate html" in e for e in errors))

    def test_rejects_markdown_path_not_ending_md(self):
        manifest = _minimal_manifest()
        manifest["documents"][0]["markdown"] = "guide.txt"
        errors = cd.validate_manifest(manifest)
        self.assertTrue(any("must end with .md" in e for e in errors))

    def test_rejects_html_path_not_ending_html(self):
        manifest = _minimal_manifest()
        manifest["documents"][0]["html"] = "guide.htm"
        errors = cd.validate_manifest(manifest)
        self.assertTrue(any("must end with .html" in e for e in errors))

    def test_rejects_missing_title(self):
        manifest = _minimal_manifest()
        del manifest["documents"][0]["title"]
        errors = cd.validate_manifest(manifest)
        self.assertTrue(any("title" in e for e in errors))

    def test_rejects_empty_title(self):
        manifest = _minimal_manifest()
        manifest["documents"][0]["title"] = "   "
        errors = cd.validate_manifest(manifest)
        self.assertTrue(any("title" in e for e in errors))

    def test_rejects_unknown_authoring_mode(self):
        manifest = _minimal_manifest()
        manifest["documents"][0]["authoring"] = {"mode": "freeform"}
        errors = cd.validate_manifest(manifest)
        self.assertTrue(any("authoring.mode" in e for e in errors))

    def test_estimated_mode_requires_tier_and_input_profile(self):
        manifest = _minimal_manifest()
        manifest["documents"][0]["authoring"] = {"mode": "estimated"}
        errors = cd.validate_manifest(manifest)
        self.assertTrue(any("tier" in e for e in errors))
        self.assertTrue(any("input_profile" in e for e in errors))

    def test_estimated_mode_with_tier_and_profile_is_valid(self):
        manifest = _minimal_manifest()
        manifest["documents"][0]["authoring"] = {
            "mode": "estimated",
            "tier": "S",
            "input_profile": "small",
        }
        errors = cd.validate_manifest(manifest)
        self.assertEqual(errors, [])

    def test_rejects_malformed_source_set_reference(self):
        manifest = _minimal_manifest()
        manifest["documents"][0]["sources"] = ["does-not-exist"]
        errors = cd.validate_manifest(manifest)
        self.assertTrue(any("unknown source set" in e for e in errors))

    def test_rejects_path_outside_docs_root(self):
        manifest = _minimal_manifest()
        manifest["documents"][0]["markdown"] = "sub/../../outside.md"
        errors = cd.validate_manifest(manifest)
        # caught either as an unsafe (..) path or as outside-docs-root
        self.assertTrue(errors)

    def test_live_tree_check_flags_undeclared_markdown_file(self):
        with tempfile.TemporaryDirectory() as d:
            docs_root = Path(d) / "copilot-docs"
            docs_root.mkdir()
            (docs_root / "guide.md").write_text("# Guide\n")
            (docs_root / "guide.html").write_text("<html></html>")
            (docs_root / "rogue.md").write_text("# Rogue\n")
            errors = cd.validate_manifest(
                _minimal_manifest(),
                docs_root=docs_root,
                repo_root=Path("."),
                check_live_tree=True,
            )
            self.assertTrue(any("rogue.md" in e for e in errors))

    def test_live_tree_check_passes_when_all_files_declared(self):
        with tempfile.TemporaryDirectory() as d:
            docs_root = Path(d) / "copilot-docs"
            docs_root.mkdir()
            (docs_root / "guide.md").write_text("# Guide\n")
            (docs_root / "guide.html").write_text("<html></html>")
            errors = cd.validate_manifest(
                _minimal_manifest(),
                docs_root=docs_root,
                repo_root=Path("."),
                check_live_tree=True,
            )
            self.assertEqual(errors, [])

    def test_rejects_missing_schema(self):
        manifest = _minimal_manifest()
        del manifest["schema"]
        errors = cd.validate_manifest(manifest)
        self.assertTrue(any("schema" in e for e in errors))

    def test_rejects_wrong_schema(self):
        manifest = _minimal_manifest(schema="copilot-docs/v99")
        errors = cd.validate_manifest(manifest)
        self.assertTrue(any("schema" in e for e in errors))


class MarkerSplicingTests(unittest.TestCase):
    def test_replace_generated_block_success(self):
        content = (
            "before\n"
            "<!-- BEGIN GENERATED: sec -->\n"
            "old body\n"
            "<!-- END GENERATED: sec -->\n"
            "after\n"
        )
        result = cd.replace_generated_block(content, "sec", "new body")
        self.assertIn("new body", result)
        self.assertNotIn("old body", result)
        self.assertIn("before", result)
        self.assertIn("after", result)
        self.assertEqual(result.count("BEGIN GENERATED: sec"), 1)
        self.assertEqual(result.count("END GENERATED: sec"), 1)

    def test_replace_is_pure_and_deterministic(self):
        content = (
            "<!-- BEGIN GENERATED: sec -->\nold\n<!-- END GENERATED: sec -->\n"
        )
        r1 = cd.replace_generated_block(content, "sec", "new")
        r2 = cd.replace_generated_block(content, "sec", "new")
        self.assertEqual(r1, r2)
        # original content untouched
        self.assertIn("old", content)

    def test_missing_marker_raises(self):
        content = "no markers here\n"
        with self.assertRaises(cd.MarkerError):
            cd.replace_generated_block(content, "sec", "new")

    def test_duplicate_marker_name_raises(self):
        content = (
            "<!-- BEGIN GENERATED: sec -->\na\n<!-- END GENERATED: sec -->\n"
            "<!-- BEGIN GENERATED: sec -->\nb\n<!-- END GENERATED: sec -->\n"
        )
        with self.assertRaises(cd.MarkerError):
            cd.replace_generated_block(content, "sec", "new")

    def test_nested_marker_raises(self):
        content = (
            "<!-- BEGIN GENERATED: outer -->\n"
            "<!-- BEGIN GENERATED: inner -->\n"
            "x\n"
            "<!-- END GENERATED: inner -->\n"
            "<!-- END GENERATED: outer -->\n"
        )
        with self.assertRaises(cd.MarkerError):
            cd.replace_generated_block(content, "outer", "new")

    def test_reversed_marker_raises(self):
        content = "<!-- END GENERATED: sec -->\nx\n<!-- BEGIN GENERATED: sec -->\n"
        with self.assertRaises(cd.MarkerError):
            cd.replace_generated_block(content, "sec", "new")

    def test_mismatched_marker_raises(self):
        content = "<!-- BEGIN GENERATED: a -->\nx\n<!-- END GENERATED: b -->\n"
        with self.assertRaises(cd.MarkerError):
            cd.replace_generated_block(content, "a", "new")

    def test_unclosed_marker_raises(self):
        content = "<!-- BEGIN GENERATED: a -->\nx\n"
        with self.assertRaises(cd.MarkerError):
            cd.replace_generated_block(content, "a", "new")

    def test_never_appends_when_marker_missing(self):
        content = "static content only\n"
        with self.assertRaises(cd.MarkerError):
            cd.replace_generated_block(content, "sec", "new")
        # confirm nothing was silently appended by re-reading unchanged content
        self.assertEqual(content, "static content only\n")


class MarkdownHeadingIdTests(unittest.TestCase):
    def test_stable_unique_ids_for_duplicate_headings(self):
        src = "# Intro\n\n## Intro\n\n## Intro\n"
        rendered = cd.render_markdown(src)
        self.assertIn('id="intro"', rendered)
        self.assertIn('id="intro-2"', rendered)
        self.assertIn('id="intro-3"', rendered)

    def test_heading_levels_h1_to_h4_supported(self):
        src = "# One\n\n## Two\n\n### Three\n\n#### Four\n"
        rendered = cd.render_markdown(src)
        for level in (1, 2, 3, 4):
            self.assertIn(f"<h{level}", rendered)

    def test_heading_deeper_than_h4_rejected(self):
        with self.assertRaises(cd.MarkdownError):
            cd.render_markdown("##### Too Deep\n")


class MarkdownEscapingTests(unittest.TestCase):
    def test_escapes_ampersand_in_plain_paragraph_text(self):
        rendered = cd.render_markdown('A "quote" & more text\n')
        self.assertIn("&amp;", rendered)
        self.assertIn("&quot;", rendered)

    def test_raw_html_tag_in_paragraph_is_a_hard_error_not_silently_rendered(self):
        with self.assertRaises(cd.MarkdownError):
            cd.render_markdown("A <b>bold</b> paragraph.\n")

    def test_escapes_code_span_content(self):
        rendered = cd.render_markdown("Use `x < y` carefully.\n")
        self.assertIn("<code>x &lt; y</code>", rendered)

    def test_escapes_link_text_and_url(self):
        rendered = cd.render_markdown('See [a and b](http://example.com/?x=1&y=2).\n')
        self.assertIn("a and b", rendered)
        self.assertIn("&amp;", rendered)


class MarkdownBlockTests(unittest.TestCase):
    def test_paragraph_block(self):
        rendered = cd.render_markdown("Just a paragraph.\n")
        self.assertIn("<p>Just a paragraph.</p>", rendered)

    def test_inline_code_emphasis_strong(self):
        rendered = cd.render_markdown("Some **strong**, *em*, and `code`.\n")
        self.assertIn("<strong>strong</strong>", rendered)
        self.assertIn("<em>em</em>", rendered)
        self.assertIn("<code>code</code>", rendered)

    def test_markdown_link(self):
        rendered = cd.render_markdown("[hello](https://example.com)\n")
        self.assertIn('<a href="https://example.com">hello</a>', rendered)

    def test_fenced_code_block(self):
        rendered = cd.render_markdown("```python\nprint('hi')\n```\n")
        self.assertIn('<pre><code class="language-python">', rendered)
        self.assertIn("print(&#x27;hi&#x27;)", rendered)

    def test_blockquote_renders_as_callout(self):
        rendered = cd.render_markdown("> A quote.\n")
        self.assertIn('<blockquote class="callout">', rendered)
        self.assertIn("A quote.", rendered)

    def test_unordered_list(self):
        rendered = cd.render_markdown("- one\n- two\n")
        self.assertIn("<ul><li>one</li><li>two</li></ul>", rendered)

    def test_ordered_list(self):
        rendered = cd.render_markdown("1. one\n2. two\n")
        self.assertIn("<ol><li>one</li><li>two</li></ol>", rendered)

    def test_simple_pipe_table(self):
        src = "| A | B |\n| --- | --- |\n| 1 | 2 |\n"
        rendered = cd.render_markdown(src)
        self.assertIn("<table>", rendered)
        self.assertIn("<th>A</th>", rendered)
        self.assertIn("<td>1</td>", rendered)

    def test_table_column_mismatch_rejected(self):
        src = "| A | B |\n| --- | --- |\n| 1 |\n"
        with self.assertRaises(cd.MarkdownError):
            cd.render_markdown(src)

    def test_unterminated_fence_rejected(self):
        with self.assertRaises(cd.MarkdownError):
            cd.render_markdown("```python\nprint('x')\n")


class MarkdownUnsupportedConstructTests(unittest.TestCase):
    def test_raw_html_in_paragraph_rejected(self):
        with self.assertRaises(cd.MarkdownError):
            cd.render_markdown("A paragraph with <div>raw html</div> inline.\n")

    def test_raw_html_block_rejected(self):
        with self.assertRaises(cd.MarkdownError):
            cd.render_markdown("<div>\nblock html\n</div>\n")

    def test_indented_nested_list_item_rejected(self):
        with self.assertRaises(cd.MarkdownError):
            cd.render_markdown("- one\n  - nested\n")


class LinkRewriteTests(unittest.TestCase):
    def _manifest(self):
        return {
            "documents": [
                {"markdown": "a.md", "html": "a.html", "title": "A"},
                {"markdown": "b.md", "html": "b.html", "title": "B"},
            ]
        }

    def test_rewrites_link_to_manifest_document(self):
        rewrite = cd.make_link_rewriter(self._manifest())
        rendered = cd.render_markdown("[see a](a.md)\n", link_rewrite=rewrite)
        self.assertIn('href="a.html"', rendered)

    def test_preserves_fragment_when_rewriting(self):
        rewrite = cd.make_link_rewriter(self._manifest())
        rendered = cd.render_markdown("[see a](a.md#section)\n", link_rewrite=rewrite)
        self.assertIn('href="a.html#section"', rendered)

    def test_preserves_external_link(self):
        rewrite = cd.make_link_rewriter(self._manifest())
        rendered = cd.render_markdown(
            "[ext](https://example.com/page)\n", link_rewrite=rewrite
        )
        self.assertIn('href="https://example.com/page"', rendered)

    def test_preserves_repo_link_not_in_manifest(self):
        rewrite = cd.make_link_rewriter(self._manifest())
        rendered = cd.render_markdown("[other](other.md)\n", link_rewrite=rewrite)
        self.assertIn('href="other.md"', rendered)


class HtmlShellTests(unittest.TestCase):
    def test_shell_is_accessible_and_offline(self):
        shell = cd.build_html_shell("Title", "<p>body</p>", markdown_href="guide.md")
        self.assertTrue(shell.startswith("<!DOCTYPE html>"))
        self.assertIn('lang="en"', shell)
        self.assertIn('charset="utf-8"', shell)
        self.assertIn("viewport", shell)
        self.assertIn("<title>Title</title>", shell)
        self.assertIn('class="skip-link"', shell)
        self.assertIn("<nav", shell)
        self.assertIn("<main", shell)
        self.assertIn('href="guide.md"', shell)
        self.assertIn("assets/style.css", shell)
        self.assertNotIn("<script", shell)
        self.assertNotIn("http://", shell)
        self.assertNotIn("https://", shell)


class DefaultStyleCssTests(unittest.TestCase):
    """Focused regressions for the pinned rich-stylesheet contract (Phase 2 T3 follow-up):
    warm neutral palette, serif body / monospace code, centered responsive width, bordered
    tables with narrow-screen overflow, visible callouts, visible focus states, responsive
    nav/spacing, print rules, generic tier accents, and zero network/JS dependency."""

    def test_warm_neutral_background_and_dark_ink(self):
        css = cd.DEFAULT_STYLE_CSS
        self.assertIn("--bg:", css)
        self.assertIn("--ink:", css)
        self.assertIn("background: var(--bg)", css)
        self.assertIn("color: var(--ink)", css)

    def test_serif_body_and_monospace_code(self):
        css = cd.DEFAULT_STYLE_CSS
        self.assertIn("serif", css)
        self.assertIn("monospace", css)

    def test_centered_responsive_content_width(self):
        css = cd.DEFAULT_STYLE_CSS
        self.assertIn("max-width: 60rem", css)
        self.assertIn("margin: 0 auto", css)
        self.assertIn("@media (max-width: 40rem)", css)

    def test_bordered_tables_with_narrow_screen_overflow(self):
        css = cd.DEFAULT_STYLE_CSS
        self.assertIn("border: 1px solid var(--line)", css)
        self.assertIn("table { display: block; overflow-x: auto", css)

    def test_visible_callout_treatment(self):
        css = cd.DEFAULT_STYLE_CSS
        self.assertIn("blockquote.callout", css)
        self.assertIn("border-left:", css)

    def test_visible_keyboard_focus_states(self):
        css = cd.DEFAULT_STYLE_CSS
        self.assertIn(":focus-visible", css)
        self.assertIn(".skip-link:focus", css)

    def test_responsive_navigation_and_spacing(self):
        css = cd.DEFAULT_STYLE_CSS
        self.assertIn("nav {", css)
        self.assertIn("main {", css)

    def test_print_rules_remove_backgrounds_and_keep_links_and_tables_readable(self):
        css = cd.DEFAULT_STYLE_CSS
        self.assertIn("@media print", css)
        print_block = css.split("@media print")[1]
        self.assertIn("background: none", print_block)
        self.assertIn("a, a:visited", print_block)
        self.assertIn("table, th, td", print_block)

    def test_generic_tier_accents_with_no_model_specific_names(self):
        css = cd.DEFAULT_STYLE_CSS
        for cls in (".tier-cheap", ".tier-mid", ".tier-strong", ".tier-frontier"):
            self.assertIn(cls, css)
        for banned in ("fable", "opus", "sonnet", "haiku", "gpt", "gemini", "claude"):
            self.assertNotIn(banned, css.lower())

    def test_no_network_js_font_image_or_analytics_dependency(self):
        css = cd.DEFAULT_STYLE_CSS
        self.assertNotIn("http://", css)
        self.assertNotIn("https://", css)
        self.assertNotIn("@import", css)
        self.assertNotIn("url(", css)
        self.assertNotIn("<script", css)

    def test_generated_asset_matches_default_style_css(self):
        manifest = _minimal_manifest()
        with tempfile.TemporaryDirectory() as d:
            docs_root = Path(d) / "copilot-docs"
            _write_canonical(docs_root, "guide.md", "# Guide\n\nAuthored guide body.\n")
            plan = cd.plan_artifacts(manifest, Path("."), docs_root)
        self.assertEqual(plan[cd.ASSET_CSS_PATH], cd.DEFAULT_STYLE_CSS.encode("utf-8"))


def _write_canonical(docs_root, relpath, content):
    """Write ``content`` as the canonical Markdown source for ``relpath`` under ``docs_root``,
    creating parent directories as needed."""
    docs_root = Path(docs_root)
    target = docs_root / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


class ArtifactPlanningTests(unittest.TestCase):
    def test_plan_is_deterministic_across_identical_trees(self):
        manifest = _minimal_manifest()
        with tempfile.TemporaryDirectory() as d:
            docs_root = Path(d) / "copilot-docs"
            _write_canonical(docs_root, "guide.md", "# Guide\n\nAuthored guide body.\n")
            plan1 = cd.plan_artifacts(manifest, Path("."), docs_root)
            plan2 = cd.plan_artifacts(manifest, Path("."), docs_root)
            self.assertEqual(plan1, plan2)

    def test_plan_contains_declared_paths_and_css(self):
        manifest = _minimal_manifest()
        with tempfile.TemporaryDirectory() as d:
            docs_root = Path(d) / "copilot-docs"
            _write_canonical(docs_root, "guide.md", "# Guide\n\nAuthored guide body.\n")
            plan = cd.plan_artifacts(manifest, Path("."), docs_root)
        self.assertIn("guide.md", plan)
        self.assertIn("guide.html", plan)
        self.assertIn(cd.ASSET_CSS_PATH, plan)
        for value in plan.values():
            self.assertIsInstance(value, bytes)

    def test_writer_writes_only_under_docs_root(self):
        manifest = _minimal_manifest()
        with tempfile.TemporaryDirectory() as src_d:
            src_docs_root = Path(src_d) / "copilot-docs"
            _write_canonical(src_docs_root, "guide.md", "# Guide\n\nAuthored guide body.\n")
            plan = cd.plan_artifacts(manifest, Path("."), src_docs_root)
        with tempfile.TemporaryDirectory() as d:
            docs_root = Path(d) / "copilot-docs"
            cd.write_artifacts(plan, docs_root)
            for relpath in plan:
                self.assertTrue((docs_root / relpath).is_file())

    def test_writer_rejects_path_escaping_docs_root(self):
        with tempfile.TemporaryDirectory() as d:
            docs_root = Path(d) / "copilot-docs"
            docs_root.mkdir()
            bad_plan = {"../escape.txt": b"pwned"}
            with self.assertRaises(cd.ArtifactScopeError):
                cd.write_artifacts(bad_plan, docs_root)
            self.assertFalse((Path(d) / "escape.txt").exists())

    def test_checker_reports_missing_and_stale_without_writing(self):
        manifest = _minimal_manifest()
        with tempfile.TemporaryDirectory() as src_d:
            src_docs_root = Path(src_d) / "copilot-docs"
            _write_canonical(src_docs_root, "guide.md", "# Guide\n\nAuthored guide body.\n")
            plan = cd.plan_artifacts(manifest, Path("."), src_docs_root)
        with tempfile.TemporaryDirectory() as d:
            docs_root = Path(d) / "copilot-docs"
            # nothing written yet: everything should be reported missing
            stale = cd.check_artifacts(plan, docs_root)
            self.assertEqual(set(stale), set(plan.keys()))
            self.assertFalse(docs_root.exists())

    def test_checker_is_read_only_before_after_snapshot(self):
        manifest = _minimal_manifest()
        with tempfile.TemporaryDirectory() as src_d:
            src_docs_root = Path(src_d) / "copilot-docs"
            _write_canonical(src_docs_root, "guide.md", "# Guide\n\nAuthored guide body.\n")
            plan = cd.plan_artifacts(manifest, Path("."), src_docs_root)
        with tempfile.TemporaryDirectory() as d:
            docs_root = Path(d) / "copilot-docs"
            cd.write_artifacts(plan, docs_root)

            before = {
                p: (p.read_bytes(), p.stat().st_mtime_ns)
                for p in sorted(docs_root.rglob("*"))
                if p.is_file()
            }
            stale = cd.check_artifacts(plan, docs_root)
            after = {
                p: (p.read_bytes(), p.stat().st_mtime_ns)
                for p in sorted(docs_root.rglob("*"))
                if p.is_file()
            }

            self.assertEqual(stale, [])
            self.assertEqual(before, after)

    def test_checker_detects_modified_file_as_stale(self):
        manifest = _minimal_manifest()
        with tempfile.TemporaryDirectory() as src_d:
            src_docs_root = Path(src_d) / "copilot-docs"
            _write_canonical(src_docs_root, "guide.md", "# Guide\n\nAuthored guide body.\n")
            plan = cd.plan_artifacts(manifest, Path("."), src_docs_root)
        with tempfile.TemporaryDirectory() as d:
            docs_root = Path(d) / "copilot-docs"
            cd.write_artifacts(plan, docs_root)
            (docs_root / "guide.md").write_bytes(b"tampered")
            stale = cd.check_artifacts(plan, docs_root)
            self.assertIn("guide.md", stale)


def _fake_pricing(**overrides):
    pricing = {
        "cached_date": "2026-01-01",
        "billing_unit": {"name": "AIC", "usd_per_credit": 0.01},
        "knobs": {
            "reasoning_efforts": ["Low", "Medium", "High"],
            "reasoning_efforts_note": "fake ladder note for arithmetic tests only",
        },
        "task_profiles": {
            "S": {"label": "Small fake task", "input_tokens": 1000, "output_tokens": 100},
        },
        "models": {
            "fake-cheap-1": {
                "display": "Fake Cheap One",
                "vendor": "fakevendor",
                "tier": "cheap",
                "input_per_mtok": 1.0,
                "cached_input_per_mtok": 0.1,
                "output_per_mtok": 2.0,
                "notes": "cheap fake model for arithmetic tests",
            },
            "fake-mid-1": {
                "display": "Fake Mid One",
                "vendor": "fakevendor",
                "tier": "mid",
                "input_per_mtok": 5.0,
                "cached_input_per_mtok": 0.5,
                "output_per_mtok": 10.0,
                "notes": "mid fake model for arithmetic tests",
            },
        },
    }
    pricing.update(overrides)
    return pricing


def _fake_prefs(pins=None, excludes=None, notes=None, source=None):
    return {
        "pins": dict(pins or {}),
        "excludes": list(excludes or []),
        "notes": list(notes or []),
        "source": source,
    }


def _estimated_manifest(tier="cheap", input_profile="S", **overrides):
    manifest = {
        "schema": "copilot-docs/v1",
        "source_sets": {},
        "documents": [
            {
                "markdown": "estimate.md",
                "html": "estimate.html",
                "title": "Estimate",
                "authoring": {"mode": "estimated", "tier": tier, "input_profile": input_profile},
                "sources": [],
            }
        ],
    }
    manifest.update(overrides)
    return manifest


def _make_block_context(pricing, prefs, repo_root, pricing_path=None):
    """Build a synthetic ``block_context`` for ``apply_generated_blocks``/``plan_artifacts``
    tests, mirroring the shape ``build_aic_report`` assembles internally."""
    pricing_path = pricing_path if pricing_path is not None else Path("data/pricing.copilot.json")
    pricing_snapshot = cd.build_pricing_snapshot(pricing, pricing_path, repo_root)
    prefs_snapshot = {
        "source": prefs.get("source"),
        "pins": dict(prefs.get("pins", {})),
        "excludes": list(prefs.get("excludes", [])),
        "notes": list(prefs.get("notes", [])),
        "resolved": {},
        "resolved_via": {},
    }
    return {
        "pricing": pricing,
        "prefs": prefs,
        "pricing_snapshot": pricing_snapshot,
        "prefs_snapshot": prefs_snapshot,
        "repo_root": Path(repo_root),
    }


class CanonicalMarkdownIntegrationTests(unittest.TestCase):
    """Covers the T3a gap: ``plan_artifacts`` must read canonical, hand-authored Markdown from
    ``docs_root`` and splice only known generated-block bodies into it, never synthesize a
    title/tier/profile stub (PLAN 'Canonical content' / D1)."""

    def _manifest_for(self, markdown="doc.md", html="doc.html", **authoring_overrides):
        authoring = {"mode": "deterministic"}
        authoring.update(authoring_overrides)
        return {
            "schema": "copilot-docs/v1",
            "source_sets": {},
            "documents": [{
                "markdown": markdown, "html": html, "title": "Doc",
                "authoring": authoring, "sources": [],
            }],
        }

    def test_authored_markdown_with_no_markers_survives_unchanged(self):
        manifest = self._manifest_for()
        content = "# Doc\n\nHand-authored prose. Nothing generated here at all.\n"
        with tempfile.TemporaryDirectory() as d:
            docs_root = Path(d) / "copilot-docs"
            _write_canonical(docs_root, "doc.md", content)
            plan = cd.plan_artifacts(manifest, Path("."), docs_root)
        self.assertEqual(plan["doc.md"].decode("utf-8"), content)

    def test_text_before_and_after_generated_block_is_byte_preserved(self):
        manifest = self._manifest_for()
        content = (
            "# Doc\n\nBefore-marker authored text.\n\n"
            "<!-- BEGIN GENERATED: task-profiles -->\nstale stub\n<!-- END GENERATED: task-profiles -->\n\n"
            "After-marker authored text.\n"
        )
        pricing = _fake_pricing()
        prefs = _fake_prefs()
        with tempfile.TemporaryDirectory() as d:
            repo_root = Path(d)
            docs_root = repo_root / "copilot-docs"
            _write_canonical(docs_root, "doc.md", content)
            ctx = _make_block_context(pricing, prefs, repo_root)
            plan = cd.plan_artifacts(manifest, repo_root, docs_root, block_context=ctx)
        spliced = plan["doc.md"].decode("utf-8")
        self.assertIn("Before-marker authored text.", spliced)
        self.assertIn("After-marker authored text.", spliced)
        self.assertNotIn("stale stub", spliced)
        expected_body = cd.render_task_profiles_block(ctx["pricing_snapshot"], pricing["task_profiles"])
        self.assertIn(expected_body, spliced)

    def test_multiple_known_blocks_splice_deterministically(self):
        manifest = self._manifest_for()
        content = (
            "# Doc\n\nIntro.\n\n"
            "<!-- BEGIN GENERATED: task-profiles -->\nold\n<!-- END GENERATED: task-profiles -->\n\n"
            "Middle authored text.\n\n"
            "<!-- BEGIN GENERATED: reasoning-knobs -->\nold\n<!-- END GENERATED: reasoning-knobs -->\n\n"
            "Outro.\n"
        )
        pricing = _fake_pricing()
        prefs = _fake_prefs()
        with tempfile.TemporaryDirectory() as d:
            repo_root = Path(d)
            docs_root = repo_root / "copilot-docs"
            _write_canonical(docs_root, "doc.md", content)
            ctx = _make_block_context(pricing, prefs, repo_root)
            plan1 = cd.plan_artifacts(manifest, repo_root, docs_root, block_context=ctx)
            plan2 = cd.plan_artifacts(manifest, repo_root, docs_root, block_context=ctx)
        self.assertEqual(plan1, plan2)
        spliced = plan1["doc.md"].decode("utf-8")
        self.assertIn("Middle authored text.", spliced)
        self.assertIn(
            cd.render_task_profiles_block(ctx["pricing_snapshot"], pricing["task_profiles"]), spliced
        )
        self.assertIn(
            cd.render_reasoning_knobs_block(ctx["pricing_snapshot"], pricing["knobs"]), spliced
        )

    def test_unknown_marker_name_is_a_hard_error(self):
        manifest = self._manifest_for()
        content = "<!-- BEGIN GENERATED: not-a-real-block -->\nx\n<!-- END GENERATED: not-a-real-block -->\n"
        pricing, prefs = _fake_pricing(), _fake_prefs()
        with tempfile.TemporaryDirectory() as d:
            repo_root = Path(d)
            docs_root = repo_root / "copilot-docs"
            _write_canonical(docs_root, "doc.md", content)
            ctx = _make_block_context(pricing, prefs, repo_root)
            with self.assertRaises(cd.GeneratedBlockError):
                cd.plan_artifacts(manifest, repo_root, docs_root, block_context=ctx)

    def test_known_marker_without_context_is_a_hard_error(self):
        manifest = self._manifest_for()
        content = "<!-- BEGIN GENERATED: task-profiles -->\nx\n<!-- END GENERATED: task-profiles -->\n"
        with tempfile.TemporaryDirectory() as d:
            docs_root = Path(d) / "copilot-docs"
            _write_canonical(docs_root, "doc.md", content)
            with self.assertRaises(cd.GeneratedBlockError):
                cd.plan_artifacts(manifest, Path("."), docs_root)

    def test_malformed_duplicated_nested_reversed_mismatched_markers_fail(self):
        bad_bodies = {
            "duplicated": (
                "<!-- BEGIN GENERATED: task-profiles -->\na\n<!-- END GENERATED: task-profiles -->\n"
                "<!-- BEGIN GENERATED: task-profiles -->\nb\n<!-- END GENERATED: task-profiles -->\n"
            ),
            "nested": (
                "<!-- BEGIN GENERATED: outer -->\n"
                "<!-- BEGIN GENERATED: task-profiles -->\nx\n<!-- END GENERATED: task-profiles -->\n"
                "<!-- END GENERATED: outer -->\n"
            ),
            "reversed": "<!-- END GENERATED: task-profiles -->\nx\n<!-- BEGIN GENERATED: task-profiles -->\n",
            "mismatched": "<!-- BEGIN GENERATED: task-profiles -->\nx\n<!-- END GENERATED: reasoning-knobs -->\n",
            "unclosed": "<!-- BEGIN GENERATED: task-profiles -->\nx\n",
        }
        pricing, prefs = _fake_pricing(), _fake_prefs()
        for label, content in bad_bodies.items():
            with self.subTest(label=label):
                manifest = self._manifest_for(markdown=f"{label}.md", html=f"{label}.html")
                with tempfile.TemporaryDirectory() as d:
                    repo_root = Path(d)
                    docs_root = repo_root / "copilot-docs"
                    _write_canonical(docs_root, f"{label}.md", content)
                    ctx = _make_block_context(pricing, prefs, repo_root)
                    with self.assertRaises(cd.MarkerError):
                        cd.plan_artifacts(manifest, repo_root, docs_root, block_context=ctx)

    def test_missing_canonical_markdown_fails_clearly(self):
        manifest = self._manifest_for()
        with tempfile.TemporaryDirectory() as d:
            docs_root = Path(d) / "copilot-docs"
            with self.assertRaises(cd.CanonicalSourceError):
                cd.plan_artifacts(manifest, Path("."), docs_root)

    def test_html_is_rendered_from_post_splice_markdown(self):
        manifest = self._manifest_for()
        content = (
            "# Doc\n\n"
            "<!-- BEGIN GENERATED: task-profiles -->\nstale\n<!-- END GENERATED: task-profiles -->\n"
        )
        pricing, prefs = _fake_pricing(), _fake_prefs()
        with tempfile.TemporaryDirectory() as d:
            repo_root = Path(d)
            docs_root = repo_root / "copilot-docs"
            _write_canonical(docs_root, "doc.md", content)
            ctx = _make_block_context(pricing, prefs, repo_root)
            plan = cd.plan_artifacts(manifest, repo_root, docs_root, block_context=ctx)
        html_out = plan["doc.html"].decode("utf-8")
        self.assertNotIn("stale", html_out)
        for profile_name in pricing["task_profiles"]:
            self.assertIn(profile_name, html_out)

    def test_aic_measurement_uses_post_splice_markdown_and_excludes_generated_bodies(self):
        manifest = self._manifest_for(mode="estimated", tier="cheap", input_profile="S")
        content = (
            "# Doc\n\nAuthored prose that should count toward ai_output_lexemes.\n\n"
            "<!-- BEGIN GENERATED: task-profiles -->\nstale\n<!-- END GENERATED: task-profiles -->\n"
        )
        pricing, prefs = _fake_pricing(), _fake_prefs()
        with tempfile.TemporaryDirectory() as d:
            repo_root = Path(d)
            docs_root = repo_root / "copilot-docs"
            _write_canonical(docs_root, "doc.md", content)
            report, plan = cd.build_aic_report(
                manifest, repo_root, docs_root, pricing, Path("data/pricing.copilot.json"), prefs,
            )
        spliced_text = plan["doc.md"].decode("utf-8")
        self.assertNotIn("stale", spliced_text)
        row = next(r for r in report["documents"] if r["path"] == "doc.md")
        self.assertEqual(row["measurement"]["ai_output_lexemes"], cd.ai_output_lexemes(spliced_text))
        self.assertLess(row["measurement"]["ai_output_lexemes"], cd.count_lexemes(spliced_text))

    def test_writer_updates_only_generated_bodies_and_generator_owned_outputs(self):
        manifest = self._manifest_for()
        original = (
            "# Doc\n\nAuthored intro, never touched by the generator.\n\n"
            "<!-- BEGIN GENERATED: task-profiles -->\nstale\n<!-- END GENERATED: task-profiles -->\n\n"
            "Authored outro, never touched by the generator.\n"
        )
        pricing, prefs = _fake_pricing(), _fake_prefs()
        with tempfile.TemporaryDirectory() as d:
            repo_root = Path(d)
            docs_root = repo_root / "copilot-docs"
            _write_canonical(docs_root, "doc.md", original)
            ctx = _make_block_context(pricing, prefs, repo_root)

            plan1 = cd.plan_artifacts(manifest, repo_root, docs_root, block_context=ctx)
            cd.write_artifacts(plan1, docs_root)
            first_pass = (docs_root / "doc.md").read_text(encoding="utf-8")
            self.assertIn("Authored intro, never touched by the generator.", first_pass)
            self.assertIn("Authored outro, never touched by the generator.", first_pass)
            self.assertNotIn("stale", first_pass)

            # A second build from the now-updated canonical file is a byte-stable no-op: the
            # freshly-written generated body already matches what the providers would produce.
            plan2 = cd.plan_artifacts(manifest, repo_root, docs_root, block_context=ctx)
            self.assertEqual(plan1, plan2)

    def test_checker_detects_stale_generated_bodies_and_html_read_only(self):
        manifest = self._manifest_for()
        content = (
            "# Doc\n\n"
            "<!-- BEGIN GENERATED: task-profiles -->\nstale\n<!-- END GENERATED: task-profiles -->\n"
        )
        pricing, prefs = _fake_pricing(), _fake_prefs()
        with tempfile.TemporaryDirectory() as d:
            repo_root = Path(d)
            docs_root = repo_root / "copilot-docs"
            _write_canonical(docs_root, "doc.md", content)
            ctx = _make_block_context(pricing, prefs, repo_root)
            plan = cd.plan_artifacts(manifest, repo_root, docs_root, block_context=ctx)
            cd.write_artifacts(plan, docs_root)

            # Simulate drift: pricing changed since the last build (no re-build happened), so
            # a fresh plan computed from the SAME on-disk canonical file with the NEW pricing
            # now disagrees with what's still on disk.
            drifted_pricing = _fake_pricing()
            drifted_pricing["task_profiles"]["S"]["label"] = "Changed label after drift"
            drifted_ctx = _make_block_context(drifted_pricing, prefs, repo_root)
            fresh_plan = cd.plan_artifacts(manifest, repo_root, docs_root, block_context=drifted_ctx)

            before_md = (docs_root / "doc.md").read_bytes()
            before_html = (docs_root / "doc.html").read_bytes()

            stale = cd.check_artifacts(fresh_plan, docs_root)
            self.assertIn("doc.md", stale)
            self.assertIn("doc.html", stale)
            # read-only: check_artifacts never rewrites anything on disk
            self.assertEqual((docs_root / "doc.md").read_bytes(), before_md)
            self.assertEqual((docs_root / "doc.html").read_bytes(), before_html)


class NoPublicPathOverrideTests(unittest.TestCase):
    def test_cli_commands_use_only_fixed_default_paths(self):
        source = (BIN_DIR / "copilot_docs.py").read_text(encoding="utf-8")
        for fn_name in ("cmd_build", "cmd_check", "cmd_report"):
            start = source.index(f"def {fn_name}(")
            end = source.index("\ndef ", start + 1)
            body = source[start:end]
            self.assertIn("DEFAULT_MANIFEST_PATH", body)
            self.assertIn("DEFAULT_DOCS_ROOT", body)
            self.assertNotIn("args.root", body)
            self.assertNotIn("args.docs_root", body)
            self.assertNotIn("args.manifest", body)

    def test_build_parser_subcommands_take_no_arguments(self):
        parser = cd.build_parser()
        args = parser.parse_args(["build"])
        # only the argparse-internal dest/func attributes should be present — no manifest/root
        # override made it onto the parsed namespace.
        self.assertEqual(vars(args).keys(), {"command", "func"})


class HashingTests(unittest.TestCase):
    def test_hash_file_bytes_matches_sha256_of_exact_bytes(self):
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.txt"
            p.write_bytes(b"hello world")
            self.assertEqual(cd.hash_file_bytes(p), hashlib.sha256(b"hello world").hexdigest())

    def test_roster_hash_changes_when_model_rate_changes(self):
        p1 = _fake_pricing()
        p2 = _fake_pricing()
        p2["models"]["fake-cheap-1"]["input_per_mtok"] = 999.0
        self.assertNotEqual(cd.roster_hash(p1), cd.roster_hash(p2))

    def test_roster_hash_stable_for_identical_roster_data(self):
        self.assertEqual(cd.roster_hash(_fake_pricing()), cd.roster_hash(_fake_pricing()))

    def test_roster_hash_ignores_non_roster_metadata(self):
        p1 = _fake_pricing(cached_date="2026-01-01")
        p2 = _fake_pricing(cached_date="2027-06-06")
        self.assertEqual(cd.roster_hash(p1), cd.roster_hash(p2))

    def test_source_set_hash_deterministic_and_sensitive_to_content(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "a.txt").write_text("one")
            (root / "b.txt").write_text("two")
            h1 = cd.source_set_hash(root, ["a.txt", "b.txt"])
            h2 = cd.source_set_hash(root, ["b.txt", "a.txt"])  # order-independent
            self.assertEqual(h1, h2)
            (root / "a.txt").write_text("one-changed")
            h3 = cd.source_set_hash(root, ["a.txt", "b.txt"])
            self.assertNotEqual(h1, h3)


class PrefsResolutionTests(unittest.TestCase):
    def test_pin_wins_over_roster_default(self):
        pricing = _fake_pricing()
        manifest = _estimated_manifest(tier="cheap")
        prefs = _fake_prefs(pins={"cheap": "fake-mid-1"})
        snap = cd.resolve_prefs_snapshot(pricing, prefs, manifest, repo_root=Path("."))
        self.assertEqual(snap["resolved"]["cheap"], "fake-mid-1")
        self.assertEqual(snap["resolved_via"]["cheap"], "pin")

    def test_exclude_skips_roster_default_and_falls_through(self):
        pricing = _fake_pricing()
        pricing["models"]["fake-cheap-2"] = dict(pricing["models"]["fake-cheap-1"])
        pricing["models"] = {
            "fake-cheap-1": pricing["models"]["fake-cheap-1"],
            "fake-cheap-2": pricing["models"]["fake-cheap-2"],
            "fake-mid-1": pricing["models"]["fake-mid-1"],
        }
        manifest = _estimated_manifest(tier="cheap")
        prefs = _fake_prefs(excludes=["fake-cheap-1"])
        snap = cd.resolve_prefs_snapshot(pricing, prefs, manifest, repo_root=Path("."))
        self.assertEqual(snap["resolved"]["cheap"], "fake-cheap-2")
        self.assertEqual(snap["resolved_via"]["cheap"], "roster-default")

    def test_cross_tier_note_preserved(self):
        pricing = _fake_pricing()
        manifest = _estimated_manifest(tier="cheap")
        prefs = _fake_prefs(
            pins={"cheap": "fake-mid-1"},
            notes=["pin cheap=fake-mid-1 is a cross-tier override (model's own tier: mid)"],
        )
        snap = cd.resolve_prefs_snapshot(pricing, prefs, manifest, repo_root=Path("."))
        self.assertIn(
            "pin cheap=fake-mid-1 is a cross-tier override (model's own tier: mid)",
            snap["notes"],
        )

    def test_unresolved_tier_is_a_hard_error(self):
        pricing = _fake_pricing()
        pricing["models"] = {}
        manifest = _estimated_manifest(tier="cheap")
        prefs = _fake_prefs()
        with self.assertRaises(cd.PrefsResolutionError):
            cd.resolve_prefs_snapshot(pricing, prefs, manifest, repo_root=Path("."))

    def test_excluded_selection_is_rejected(self):
        pricing = _fake_pricing()
        manifest = _estimated_manifest(tier="cheap")
        # A malformed/reconstructed prefs object where a pin also appears in excludes (the
        # normal effective_prefs() path would already reject this at build time — this proves
        # the defensive check inside resolve_prefs_snapshot itself, e.g. for a check-mode
        # reconstruction from a tampered/incoherent snapshot).
        prefs = _fake_prefs(pins={"cheap": "fake-cheap-1"}, excludes=["fake-cheap-1"])
        with self.assertRaises(cd.PrefsResolutionError):
            cd.resolve_prefs_snapshot(pricing, prefs, manifest, repo_root=Path("."))

    def test_source_normalized_to_repo_relative_path(self):
        pricing = _fake_pricing()
        manifest = _estimated_manifest(tier="cheap")
        with tempfile.TemporaryDirectory() as d:
            repo_root = Path(d)
            prefs_file = repo_root / "prefs" / "copilot.json"
            prefs_file.parent.mkdir()
            prefs_file.write_text("{}")
            prefs = _fake_prefs(source=str(prefs_file))
            snap = cd.resolve_prefs_snapshot(pricing, prefs, manifest, repo_root=repo_root)
            self.assertEqual(snap["source"], "prefs/copilot.json")


class CostAccountingTests(unittest.TestCase):
    def test_est_cost_is_called_and_drives_the_result(self):
        pricing = _fake_pricing()
        prefs = _fake_prefs()
        calls = []
        pricing_mod = cd._pricing_module()
        real_est_cost = pricing_mod.est_cost

        import functools

        @functools.wraps(real_est_cost)
        def wrapped(*args, **kwargs):
            calls.append((args, kwargs))
            return real_est_cost(*args, **kwargs)

        pricing_mod.est_cost = wrapped
        try:
            result = cd.estimate_document_cost(
                pricing, prefs, "cheap", "S", "# Title\n\nSome authored prose here.",
                today=cd.date.fromisoformat(pricing["cached_date"]),
            )
        finally:
            pricing_mod.est_cost = real_est_cost
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["model_id"], "fake-cheap-1")
        self.assertGreater(result["usd"], 0)
        self.assertGreater(result["aic"], 0)

    def test_report_values_follow_mutated_fake_rates_and_billing_unit(self):
        pricing = _fake_pricing()
        prefs = _fake_prefs()
        text = "# T\n\nauthored words go here for lexeme counting purposes."
        base = cd.estimate_document_cost(pricing, prefs, "cheap", "S", text)

        pricing2 = _fake_pricing()
        pricing2["models"]["fake-cheap-1"]["output_per_mtok"] *= 10
        higher = cd.estimate_document_cost(pricing2, prefs, "cheap", "S", text)
        self.assertGreater(higher["usd"], base["usd"])

        pricing3 = _fake_pricing()
        pricing3["billing_unit"]["usd_per_credit"] = pricing3["billing_unit"]["usd_per_credit"] / 2
        cheaper_credit = cd.estimate_document_cost(pricing3, prefs, "cheap", "S", text)
        # halving usd_per_credit means the same USD cost is worth MORE AIC
        self.assertGreater(cheaper_credit["aic"], base["aic"])

    def test_no_duplicated_rate_formula_source_pattern(self):
        source = (BIN_DIR / "copilot_docs.py").read_text(encoding="utf-8")
        self.assertNotIn("input_per_mtok\"] *", source)
        self.assertNotIn("output_per_mtok\"] *", source)

    def test_uses_pricing_cached_date_never_wall_clock_for_promo(self):
        source = (BIN_DIR / "copilot_docs.py").read_text(encoding="utf-8")
        code_only = re.sub(r'"""(?:.|\n)*?"""', "", source)
        code_only = re.sub(r"(?m)#.*$", "", code_only)
        self.assertNotIn("date.today(", code_only)


class MeasurementTests(unittest.TestCase):
    def test_word_and_lexeme_counts(self):
        text = "Hello, world! Cost: $1.23 (yes)."
        self.assertGreater(cd.count_lexemes(text), cd.count_words(text))

    def test_ai_output_lexemes_excludes_generated_marker_bodies(self):
        content = (
            "Authored intro text here.\n\n"
            "<!-- BEGIN GENERATED: model-roster -->\n"
            "| a | b |\n|---|---|\n| x | y |\n"
            "<!-- END GENERATED: model-roster -->\n\n"
            "Authored outro text here."
        )
        stripped = cd.strip_generated_blocks(content)
        self.assertNotIn("| x | y |", stripped)
        self.assertEqual(cd.ai_output_lexemes(content), cd.count_lexemes(stripped))
        self.assertLess(cd.ai_output_lexemes(content), cd.count_lexemes(content))


class FrontmatterParsingTests(unittest.TestCase):
    def test_comment_line_inside_frontmatter_is_skipped_not_parsed_as_a_key(self):
        text = (
            "---\n"
            "name: verifier\n"
            "tools: read, execute\n"
            "# tools pin (PLAN.md D4/D7, graph-convergence kit): GitHub's docs say\n"
            "# execute (compatible: shell, Bash, powershell), read, edit, search\n"
            "---\n"
            "Body.\n"
        )
        meta, body = cd.parse_frontmatter(text)
        self.assertEqual(meta, {"name": "verifier", "tools": "read, execute"})
        self.assertEqual(body, "Body.\n")

    def test_comment_line_with_leading_whitespace_is_also_skipped(self):
        text = "---\nname: x\n  # indented comment: still a comment\n---\nBody.\n"
        meta, _ = cd.parse_frontmatter(text)
        self.assertEqual(meta, {"name": "x"})

    def test_no_comment_lines_behaves_as_before(self):
        text = "---\nname: x\ndescription: y\n---\nBody.\n"
        meta, body = cd.parse_frontmatter(text)
        self.assertEqual(meta, {"name": "x", "description": "y"})
        self.assertEqual(body, "Body.\n")


class GeneratedBlockProviderTests(unittest.TestCase):
    def _repo_with_skills_and_agents(self, tmp_root, skills=(), agents=()):
        repo_root = Path(tmp_root)
        skills_root = repo_root / "copilot" / ".github" / "skills"
        agents_root = repo_root / "copilot" / ".github" / "agents"
        for name, desc in skills:
            d = skills_root / name
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\nBody.\n")
        agents_root.mkdir(parents=True, exist_ok=True)
        for name, desc, model in agents:
            (agents_root / f"{name}.agent.md").write_text(
                f"---\nname: {name}\ndescription: {desc}\nmodel: {model}\n---\nBody.\n"
            )
        return repo_root

    def test_skills_inventory_reflects_add_remove_rename_deterministically(self):
        with tempfile.TemporaryDirectory() as d:
            repo_root = self._repo_with_skills_and_agents(
                d, skills=[("alpha", "Alpha desc"), ("beta", "Beta desc")]
            )
            rows1 = cd.discover_skills(repo_root)
            rows2 = cd.discover_skills(repo_root)
            self.assertEqual(rows1, rows2)
            names1 = [r["name"] for r in rows1]
            self.assertEqual(names1, ["alpha", "beta"])

            # remove beta, add gamma, rename alpha's dir to alpha-renamed
            import shutil
            shutil.rmtree(Path(repo_root) / "copilot" / ".github" / "skills" / "beta")
            shutil.move(
                str(Path(repo_root) / "copilot" / ".github" / "skills" / "alpha"),
                str(Path(repo_root) / "copilot" / ".github" / "skills" / "alpha-renamed"),
            )
            gamma_dir = Path(repo_root) / "copilot" / ".github" / "skills" / "gamma"
            gamma_dir.mkdir()
            (gamma_dir / "SKILL.md").write_text("---\nname: gamma\ndescription: Gamma desc\n---\nBody.\n")

            rows3 = cd.discover_skills(repo_root)
            names3 = sorted(r["name"] for r in rows3)
            self.assertEqual(names3, ["alpha", "gamma"])

    def test_inventory_angle_placeholder_renders_as_safe_inline_code(self):
        pricing = _fake_pricing()
        with tempfile.TemporaryDirectory() as d:
            repo_root = self._repo_with_skills_and_agents(
                d, skills=[("architect", "Write tasks/kits/<slug>/PLAN.md")]
            )
            pricing_path = Path(d) / "fake.json"
            pricing_path.write_bytes(b"{}")
            snapshot = cd.build_pricing_snapshot(pricing, pricing_path, repo_root)
            block = cd.render_skills_inventory_block(snapshot, repo_root)

            self.assertIn("`<slug>`", block)
            rendered = cd.render_markdown(block)
            self.assertIn("<code>&lt;slug&gt;</code>", rendered)
            self.assertNotIn("<slug>", rendered)

    def test_agents_inventory_tier_exclusion_and_active_match_labels(self):
        pricing = _fake_pricing()
        with tempfile.TemporaryDirectory() as d:
            repo_root = self._repo_with_skills_and_agents(
                d, agents=[("route", "Route desc", "fake-cheap-1")]
            )
            prefs = _fake_prefs(excludes=["fake-cheap-1"])
            rows = cd.annotate_agent_rows(cd.discover_agents(repo_root), pricing, prefs)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["configured_tier"], "cheap")
            self.assertTrue(rows[0]["is_excluded"])
            self.assertFalse(rows[0]["matches_active_resolution"])

            prefs2 = _fake_prefs()
            rows2 = cd.annotate_agent_rows(cd.discover_agents(repo_root), pricing, prefs2)
            self.assertTrue(rows2[0]["matches_active_resolution"])

    def test_every_generated_block_begins_with_a_snapshot_provenance_line(self):
        pricing = _fake_pricing()
        with tempfile.TemporaryDirectory() as d:
            repo_root = self._repo_with_skills_and_agents(d)
            (Path(d) / "fake.json").write_bytes(b"{}")
            snap = cd.build_pricing_snapshot(pricing, Path(d) / "fake.json", repo_root)
            prefs_snapshot = {
                "source": None, "pins": {}, "excludes": [], "notes": [],
                "resolved": {}, "resolved_via": {},
            }
            blocks = [
                cd.render_skills_inventory_block(snap, repo_root),
                cd.render_agents_inventory_block(pricing, snap, repo_root, _fake_prefs()),
                cd.render_model_preferences_block(snap, prefs_snapshot),
                cd.render_model_roster_block(pricing, snap, _fake_prefs()),
                cd.render_reasoning_knobs_block(snap, pricing["knobs"]),
                cd.render_task_profiles_block(snap, pricing["task_profiles"]),
            ]
            for block in blocks:
                self.assertTrue(block.startswith("Snapshot: "), block[:80])
                self.assertIn(snap["pricing_sha256"], block)
                self.assertIn(snap["roster_sha256"], block)

    def test_live_model_ids_absent_from_generator_source(self):
        source = (BIN_DIR / "copilot_docs.py").read_text(encoding="utf-8")
        pricing_mod = cd._pricing_module()
        real_pricing = pricing_mod.load_pricing()
        for model_id in real_pricing["models"]:
            self.assertNotIn(model_id, source, f"live model id leaked into generator: {model_id}")


class AicReportTests(unittest.TestCase):
    def _manifest_with_two_docs(self):
        return {
            "schema": "copilot-docs/v1",
            "source_sets": {"core": ["bin/copilot_docs.py"]},
            "documents": [
                {
                    "markdown": "estimate.md", "html": "estimate.html", "title": "Estimate",
                    "authoring": {"mode": "estimated", "tier": "cheap", "input_profile": "S"},
                    "sources": [],
                },
                {
                    "markdown": "guide.md", "html": "guide.html", "title": "Guide",
                    "authoring": {"mode": "deterministic"},
                    "sources": ["core"],
                },
            ],
        }

    def _docs_root_with_two_docs(self, docs_root):
        _write_canonical(docs_root, "estimate.md", "# Estimate\n\nAuthored estimate body.\n")
        _write_canonical(docs_root, "guide.md", "# Guide\n\nAuthored guide body.\n")

    def test_markdown_and_html_rows_are_separate_and_totals_do_not_double_count(self):
        pricing = _fake_pricing()
        prefs = _fake_prefs()
        manifest = self._manifest_with_two_docs()
        with tempfile.TemporaryDirectory() as d:
            docs_root = Path(d) / "copilot-docs"
            self._docs_root_with_two_docs(docs_root)
            report, plan = cd.build_aic_report(
                manifest, Path("."), docs_root, pricing, Path("data/pricing.copilot.json"), prefs,
                today=date.fromisoformat(pricing["cached_date"]),
            )
        paths = [(r["path"], r["kind"]) for r in report["documents"]]
        self.assertIn(("estimate.md", "markdown"), paths)
        self.assertIn(("estimate.html", "html"), paths)
        self.assertIn(("guide.md", "markdown"), paths)
        self.assertIn(("guide.html", "html"), paths)

        html_rows = [r for r in report["documents"] if r["kind"] == "html"]
        for row in html_rows:
            self.assertEqual(row["cost"]["usd"], 0.0)
            self.assertEqual(row["cost"]["aic"], 0.0)
            self.assertIn("markdown_source", row)

        det_row = next(r for r in report["documents"] if r["path"] == "guide.md")
        self.assertEqual(det_row["cost"]["usd"], 0.0)

        est_row = next(r for r in report["documents"] if r["path"] == "estimate.md")
        self.assertGreater(est_row["cost"]["usd"], 0.0)

        # totals include only the one estimated markdown row's cost
        self.assertAlmostEqual(report["totals"]["usd"], est_row["cost"]["usd"])
        self.assertAlmostEqual(report["totals"]["aic"], est_row["cost"]["aic"])

    def test_self_rows_are_zero_with_null_measured_size_and_self_reference_note(self):
        pricing = _fake_pricing()
        prefs = _fake_prefs()
        manifest = self._manifest_with_two_docs()
        with tempfile.TemporaryDirectory() as d:
            docs_root = Path(d) / "copilot-docs"
            self._docs_root_with_two_docs(docs_root)
            report, _plan = cd.build_aic_report(
                manifest, Path("."), docs_root, pricing, Path("data/pricing.copilot.json"), prefs,
            )
        self_rows = [r for r in report["documents"] if r.get("self_reference")]
        self.assertEqual(len(self_rows), 2)
        for row in self_rows:
            self.assertEqual(row["cost"]["usd"], 0.0)
            self.assertEqual(row["cost"]["aic"], 0.0)
            self.assertIsNone(row["measurement"]["bytes"])
            self.assertIn("self-referential", row["cost"]["note"])

    def test_plan_with_aic_report_is_deterministic(self):
        pricing = _fake_pricing()
        prefs = _fake_prefs()
        manifest = self._manifest_with_two_docs()
        with tempfile.TemporaryDirectory() as d:
            docs_root = Path(d) / "copilot-docs"
            self._docs_root_with_two_docs(docs_root)
            report1, plan1 = cd.plan_with_aic_report(
                manifest, Path("."), docs_root, pricing, Path("data/pricing.copilot.json"), prefs,
            )
            report2, plan2 = cd.plan_with_aic_report(
                manifest, Path("."), docs_root, pricing, Path("data/pricing.copilot.json"), prefs,
            )
        self.assertEqual(plan1, plan2)
        self.assertEqual(report1, report2)
        self.assertIn(cd.AIC_REPORT_JSON, plan1)
        self.assertIn(cd.AIC_REPORT_MD, plan1)
        self.assertIn(cd.AIC_REPORT_HTML, plan1)


class DriftDetectionTests(unittest.TestCase):
    def test_check_ignores_different_local_prefs_but_flags_pricing_drift(self):
        pricing = _fake_pricing()
        prefs = _fake_prefs()
        manifest = {
            "schema": "copilot-docs/v1", "source_sets": {},
            "documents": [{
                "markdown": "estimate.md", "html": "estimate.html", "title": "Estimate",
                "authoring": {"mode": "estimated", "tier": "cheap", "input_profile": "S"},
                "sources": [],
            }],
        }
        with tempfile.TemporaryDirectory() as d:
            docs_root = Path(d) / "copilot-docs"
            _write_canonical(docs_root, "estimate.md", "# Estimate\n\nAuthored body.\n")
            report, _plan = cd.build_aic_report(
                manifest, Path("."), docs_root, pricing, Path("data/pricing.copilot.json"), prefs,
            )

        # A totally different local prefs fixture is irrelevant to check() by design — it
        # never re-derives from a local prefs file, only from the recorded snapshot.
        unrelated_local_prefs = _fake_prefs(pins={"mid": "fake-mid-1"}, source="/somewhere/else.json")
        self.assertNotEqual(unrelated_local_prefs, prefs)

        same_pricing_drift = cd.detect_drift(
            report, pricing, Path("data/pricing.copilot.json"), manifest, Path("."),
        )
        self.assertEqual(same_pricing_drift, [])

        drifted_pricing = _fake_pricing()
        drifted_pricing["models"]["fake-cheap-1"]["input_per_mtok"] = 12345.0
        drift = cd.detect_drift(
            report, drifted_pricing, Path("data/pricing.copilot.json"), manifest, Path("."),
        )
        self.assertTrue(any("roster" in d for d in drift))

    def test_check_flags_source_set_drift(self):
        pricing = _fake_pricing()
        prefs = _fake_prefs()
        with tempfile.TemporaryDirectory() as d:
            repo_root = Path(d)
            (repo_root / "src.txt").write_text("original content")
            docs_root = repo_root / "copilot-docs"
            _write_canonical(docs_root, "guide.md", "# Guide\n\nAuthored guide body.\n")
            manifest = {
                "schema": "copilot-docs/v1", "source_sets": {"core": ["src.txt"]},
                "documents": [{
                    "markdown": "guide.md", "html": "guide.html", "title": "Guide",
                    "authoring": {"mode": "deterministic"}, "sources": ["core"],
                }],
            }
            report, _plan = cd.build_aic_report(
                manifest, repo_root, docs_root, pricing, Path("data/pricing.copilot.json"), prefs,
            )
            no_drift = cd.detect_drift(report, pricing, Path("data/pricing.copilot.json"), manifest, repo_root)
            self.assertEqual(no_drift, [])

            (repo_root / "src.txt").write_text("changed content")
            drift = cd.detect_drift(report, pricing, Path("data/pricing.copilot.json"), manifest, repo_root)
            self.assertTrue(any("source set" in d for d in drift))

    def test_reconstruct_prefs_from_snapshot_round_trips(self):
        snapshot = {
            "source": "prefs/copilot.json", "pins": {"cheap": "fake-cheap-1"},
            "excludes": ["fake-mid-1"], "notes": ["a note"],
        }
        prefs = cd.reconstruct_prefs_from_snapshot(snapshot)
        self.assertEqual(prefs["pins"], {"cheap": "fake-cheap-1"})
        self.assertEqual(prefs["excludes"], ["fake-mid-1"])
        self.assertEqual(prefs["source"], "prefs/copilot.json")


class ReadOnlyByteSnapshotTests(unittest.TestCase):
    def test_report_and_check_helpers_never_write_files(self):
        pricing = _fake_pricing()
        prefs = _fake_prefs()
        manifest = _estimated_manifest()
        with tempfile.TemporaryDirectory() as canon_d, tempfile.TemporaryDirectory() as d:
            # canonical Markdown lives in its own directory, entirely separate from repo_root,
            # so the "repo_root gained no files" assertion below stays meaningful even though
            # plan_artifacts must now read a canonical source.
            docs_root = Path(canon_d) / "copilot-docs"
            _write_canonical(docs_root, "estimate.md", "# Estimate\n\nAuthored body.\n")

            repo_root = Path(d)
            before = sorted(repo_root.rglob("*"))
            cd.build_aic_report(
                manifest, repo_root, docs_root, pricing, Path("data/pricing.copilot.json"), prefs,
            )
            cd.plan_with_aic_report(
                manifest, repo_root, docs_root, pricing, Path("data/pricing.copilot.json"), prefs,
            )
            after = sorted(repo_root.rglob("*"))
            self.assertEqual(before, after)
            self.assertEqual(before, [])


class StaticSafetyTests(unittest.TestCase):
    def test_module_has_no_process_network_or_home_primitive(self):
        source = (BIN_DIR / "copilot_docs.py").read_text(encoding="utf-8")
        # Strip triple-quoted docstrings/comments before scanning: this module's own
        # documentation intentionally *names* the primitives it avoids (e.g. "no
        # subprocess", "no ``Path.home()``") as part of describing the safety contract, and
        # those mentions must not trip this check. Only actual code matters here.
        code_only = re.sub(r'"""(?:.|\n)*?"""', "", source)
        code_only = re.sub(r"(?m)#.*$", "", code_only)
        forbidden = [
            "import subprocess",
            "os.system(",
            "import socket",
            "import urllib",
            "import http.client",
            "Path.home(",
            "random.",
            "datetime.now(",
            "time.time(",
        ]
        for token in forbidden:
            self.assertNotIn(token, code_only, f"forbidden primitive found: {token}")


if __name__ == "__main__":
    unittest.main()
