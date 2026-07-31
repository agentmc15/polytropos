#!/usr/bin/env python3
"""copilot-docs generator — manifest validation, marker splicing, a bounded Markdown->HTML
renderer, pure artifact planning, and (as of the docs-aic-accounting task) data-derived
generated blocks, source freshness, preference handling, and per-document AIC accounting
(schema_version "copilot-docs/v1"; AIC report schema "copilot-docs/aic-report/v1").

Every price, rate, model id, and cached date used by this module is loaded at run time from
``data/pricing.copilot.json`` via ``bin/copilot_pricing.py`` (loaded lazily by absolute path,
the house importlib convention — ``bin`` is never imported as a package). The full USD/AIC
formula, long-context choice, promo warning, and cache treatment live ONLY in
``copilot_pricing.est_cost``; this module never duplicates that math, it only supplies the
ephemeral input/output token counts for one document at a time. Pins/excludes are likewise
owned entirely by ``bin/copilot_prefs.py`` (``effective_prefs``/``resolve_tier``).

Everything in this module is deterministic and side-effect-free except the explicit I/O seams
(``write_artifacts``, the loaders, and the ``build``/``check``/``report`` CLI commands): no
random values, no ``subprocess``, no shell, no network module, no ``Path.home()``, and no
implicit current-working-directory path logic (the CLI's defaults are computed from this file's
own location, mirroring ``bin/memory_store.py`` / ``journal/``). The one exception to "no wall
clock" is deliberate and pinned: every promo-warning check inside ``copilot_pricing.est_cost``
is driven by ``today=date.fromisoformat(pricing["cached_date"])`` — the pricing snapshot's own
labeled date — never ``date.today()``, so generated output stays byte-stable.

Manifest schema (JSON)::

    {
      "schema": "copilot-docs/v1",
      "source_sets": {"name": ["repo/relative/path.py", "glob/*.py"]},
      "documents": [
        {
          "markdown": "guide.md",           # relative to copilot-docs/
          "html": "guide.html",              # relative to copilot-docs/
          "title": "Guide",
          "authoring": {"mode": "deterministic"},
          "sources": ["name"]
        },
        {
          "markdown": "estimate.md",
          "html": "estimate.html",
          "title": "Estimate",
          "authoring": {"mode": "estimated", "tier": "S", "input_profile": "small"},
          "sources": []
        }
      ]
    }

``authoring.mode`` is ``"estimated"`` or ``"deterministic"``. An estimated document additionally
carries symbolic ``tier``/``input_profile`` markers that a later task will resolve against
``data/pricing.copilot.json`` — this task stores and validates them only.

Generated-block markers are exactly ``<!-- BEGIN GENERATED: <name> -->`` /
``<!-- END GENERATED: <name> -->``; splicing is pure and rejects missing, duplicate, nested,
reversed, or mismatched markers rather than guessing.
"""

import argparse
import hashlib
import html
import importlib.util
import inspect
import json
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIRNAME = "copilot-docs"
DEFAULT_DOCS_ROOT = REPO_ROOT / DOCS_DIRNAME
DEFAULT_MANIFEST_NAME = "manifest.json"
DEFAULT_MANIFEST_PATH = DEFAULT_DOCS_ROOT / DEFAULT_MANIFEST_NAME

SCHEMA_ID = "copilot-docs/v1"
AUTHORING_MODES = ("estimated", "deterministic")
ASSET_CSS_PATH = "assets/style.css"

MARKER_BEGIN = "BEGIN GENERATED"
MARKER_END = "END GENERATED"
MARKER_RE = re.compile(r"<!-- (BEGIN|END) GENERATED: (\S+) -->")


class ManifestError(ValueError):
    """Raised with a list of human-readable validation error strings."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


class MarkerError(ValueError):
    """Raised for missing/duplicate/nested/reversed/mismatched generated-block markers."""


class MarkdownError(ValueError):
    """Raised for unsupported/ambiguous Markdown constructs (raw HTML, malformed tables, ...)."""


class ArtifactScopeError(ValueError):
    """Raised when a planned artifact path resolves outside the docs root."""


class CanonicalSourceError(ValueError):
    """Raised when a manifest document's canonical Markdown source file is missing under the
    docs root. Markdown is the canonical human-authored format (PLAN 'Canonical content' / D1)
    — a missing source is a hard error, never a synthesized stub."""


class GeneratedBlockError(ValueError):
    """Raised when a document contains a generated-block marker with no known provider, or a
    present marker needs generation context (pricing/prefs snapshot) that was not supplied."""


class PrefsResolutionError(ValueError):
    """Raised when a manifest-used tier has no resolution, or resolves to an excluded model —
    both are hard errors per the docs-aic-accounting task's pinned behavior."""


# --------------------------------------------------------------------------- manifest validation

def _is_relpath_safe(path_str):
    """``True`` iff ``path_str`` is non-empty, not absolute, and has no ``..`` component."""
    if not path_str:
        return False
    p = Path(path_str)
    if p.is_absolute():
        return False
    if any(part == ".." for part in p.parts):
        return False
    return True


def _path_within(root, relpath):
    """``True`` iff ``root / relpath`` resolves to a path under ``root`` (no traversal escape),
    without requiring either path to exist on disk."""
    root_resolved = Path(root).resolve()
    target_resolved = (Path(root) / relpath).resolve()
    try:
        target_resolved.relative_to(root_resolved)
    except ValueError:
        return False
    return True


def validate_manifest(manifest, docs_root=None, repo_root=None, check_live_tree=False):
    """Validate a parsed manifest dict. Returns a list of error strings (empty == valid).

    ``docs_root``/``repo_root`` are ``Path``-like and only required when path-scope or
    live-tree checks are requested; pure schema checks work without them.
    """
    errors = []

    if not isinstance(manifest, dict):
        return ["manifest must be a JSON object"]

    if manifest.get("schema") != SCHEMA_ID:
        errors.append(f"unknown or missing schema (expected {SCHEMA_ID!r})")

    source_sets = manifest.get("source_sets", {})
    if not isinstance(source_sets, dict):
        errors.append("source_sets must be an object")
        source_sets = {}
    else:
        for set_name, paths in source_sets.items():
            if not isinstance(paths, list):
                errors.append(f"source_sets[{set_name!r}] must be a list")
                continue
            for p in paths:
                if not isinstance(p, str) or not _is_relpath_safe(p):
                    errors.append(f"source_sets[{set_name!r}] has an invalid path: {p!r}")

    documents = manifest.get("documents")
    if not isinstance(documents, list):
        return errors + ["documents must be a list"]

    seen_markdown = set()
    seen_html = set()

    for i, doc in enumerate(documents):
        label = f"documents[{i}]"
        if not isinstance(doc, dict):
            errors.append(f"{label} must be an object")
            continue

        md_path = doc.get("markdown")
        html_path = doc.get("html")
        title = doc.get("title")
        authoring = doc.get("authoring")
        sources = doc.get("sources", [])

        if not isinstance(md_path, str) or not _is_relpath_safe(md_path):
            errors.append(f"{label}.markdown is missing or an unsafe path: {md_path!r}")
        elif not md_path.endswith(".md"):
            errors.append(f"{label}.markdown must end with .md: {md_path!r}")
        else:
            if md_path in seen_markdown:
                errors.append(f"duplicate markdown path: {md_path!r}")
            seen_markdown.add(md_path)
            if docs_root is not None and not _path_within(docs_root, md_path):
                errors.append(f"{label}.markdown resolves outside the docs root: {md_path!r}")

        if not isinstance(html_path, str) or not _is_relpath_safe(html_path):
            errors.append(f"{label}.html is missing or an unsafe path: {html_path!r}")
        elif not html_path.endswith(".html"):
            errors.append(f"{label}.html must end with .html: {html_path!r}")
        else:
            if html_path in seen_html:
                errors.append(f"duplicate html path: {html_path!r}")
            seen_html.add(html_path)
            if docs_root is not None and not _path_within(docs_root, html_path):
                errors.append(f"{label}.html resolves outside the docs root: {html_path!r}")

        if not isinstance(title, str) or not title.strip():
            errors.append(f"{label}.title is missing or empty")

        if not isinstance(authoring, dict):
            errors.append(f"{label}.authoring must be an object")
        else:
            mode = authoring.get("mode")
            if mode not in AUTHORING_MODES:
                errors.append(f"{label}.authoring.mode is unknown: {mode!r}")
            elif mode == "estimated":
                if not authoring.get("tier"):
                    errors.append(f"{label}.authoring.tier is required for estimated documents")
                if not authoring.get("input_profile"):
                    errors.append(
                        f"{label}.authoring.input_profile is required for estimated documents"
                    )

        if not isinstance(sources, list):
            errors.append(f"{label}.sources must be a list")
        else:
            for s in sources:
                if not isinstance(s, str) or s not in source_sets:
                    errors.append(f"{label}.sources references an unknown source set: {s!r}")

    if check_live_tree and docs_root is not None:
        docs_root = Path(docs_root)
        if docs_root.is_dir():
            for f in sorted(docs_root.rglob("*")):
                if not f.is_file():
                    continue
                if f.suffix not in (".md", ".html"):
                    continue
                rel = f.relative_to(docs_root).as_posix()
                if rel not in seen_markdown and rel not in seen_html:
                    errors.append(f"undeclared {f.suffix[1:]} file on disk: {rel}")

    return errors


def resolve_source_set(repo_root, patterns):
    """Expand a list of repo-relative paths/globs against ``repo_root``. Returns a sorted list
    of repo-relative posix path strings (deterministic; no ordering depends on filesystem
    iteration order)."""
    repo_root = Path(repo_root)
    resolved = set()
    for pattern in patterns:
        if any(ch in pattern for ch in "*?["):
            for match in repo_root.glob(pattern):
                if match.is_file():
                    resolved.add(match.relative_to(repo_root).as_posix())
        else:
            resolved.add(pattern)
    return sorted(resolved)


# --------------------------------------------------------------------------- generated markers

def _scan_markers(content):
    """Validate marker structure across the whole document. Returns an ordered list of
    ``(name, begin_end_index, begin_line_end, end_line_start, end_match_end)`` tuples, one per
    well-formed BEGIN/END pair, in document order. Raises ``MarkerError`` on any structural
    defect (duplicate, nested, reversed/orphan, mismatched, or unclosed marker)."""
    matches = list(MARKER_RE.finditer(content))
    stack = []
    seen_names = set()
    pairs = []
    for m in matches:
        kind, name = m.group(1), m.group(2)
        if kind == "BEGIN":
            if stack:
                raise MarkerError(
                    f"nested marker: BEGIN {name!r} found before matching END for "
                    f"{stack[-1][0]!r}"
                )
            if name in seen_names:
                raise MarkerError(f"duplicate marker name: {name!r}")
            seen_names.add(name)
            stack.append((name, m))
        else:  # END
            if not stack:
                raise MarkerError(f"reversed or orphan END marker: {name!r}")
            open_name, open_match = stack.pop()
            if open_name != name:
                raise MarkerError(
                    f"mismatched marker: BEGIN {open_name!r} closed by END {name!r}"
                )
            pairs.append((name, open_match.start(), open_match.end(), m.start(), m.end()))
    if stack:
        raise MarkerError(f"unclosed marker: BEGIN {stack[-1][0]!r} has no matching END")
    return pairs


def replace_generated_block(content, name, new_inner):
    """Replace the body between ``<!-- BEGIN GENERATED: name -->`` and
    ``<!-- END GENERATED: name -->`` with ``new_inner``, preserving the marker lines themselves.
    Pure and deterministic. Raises ``MarkerError`` if markers anywhere in ``content`` are
    malformed, or if ``name`` has no marker pair."""
    pairs = _scan_markers(content)
    for pair_name, begin_start, begin_end, end_start, end_end in pairs:
        if pair_name == name:
            before = content[:begin_end]
            after = content[end_start:]
            inner = new_inner if new_inner.startswith("\n") else "\n" + new_inner
            if not inner.endswith("\n"):
                inner = inner + "\n"
            return before + inner + after
    raise MarkerError(f"missing generated block: {name!r}")


def build_marked_block(name, inner):
    """Build a fresh ``BEGIN GENERATED``/``END GENERATED`` fenced block from scratch."""
    inner = inner if inner.endswith("\n") else inner + "\n"
    return (
        f"<!-- BEGIN GENERATED: {name} -->\n"
        f"{inner}"
        f"<!-- END GENERATED: {name} -->\n"
    )


# --------------------------------------------------------------------------- Markdown rendering

_RAW_HTML_RE = re.compile(r"<[a-zA-Z!/][^>]*>")
_INLINE_RE = re.compile(
    r"`(?P<code>[^`]+)`"
    r"|\[(?P<linktext>[^\]\[]+)\]\((?P<linkurl>[^()\s]+)\)"
    r"|\*\*(?P<strong>[^*]+)\*\*"
    r"|\*(?P<em1>[^*]+)\*"
    r"|_(?P<em2>[^_]+)_"
)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_FENCE_RE = re.compile(r"^```(\S*)\s*$")
_ORDERED_RE = re.compile(r"^(\d+)\.\s+(.*\S)\s*$")
_UNORDERED_RE = re.compile(r"^[-*]\s+(.*\S)\s*$")
_BLOCKQUOTE_RE = re.compile(r"^>\s?(.*)$")
_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$")


def slugify_heading(text, used):
    """Slug for a heading's stable id: lowercase, non-alnum runs -> ``-``, de-duplicated against
    ``used`` (a mutable set updated in place) by appending ``-2``, ``-3``, ..."""
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if not base:
        base = "section"
    slug = base
    n = 2
    while slug in used:
        slug = f"{base}-{n}"
        n += 1
    used.add(slug)
    return slug


def _check_no_raw_html(line):
    without_code_spans = re.sub(r"`[^`\n]*`", "", line)
    if _RAW_HTML_RE.search(without_code_spans):
        raise MarkdownError(f"unsupported raw HTML in source: {line!r}")


def _render_inline(text, link_rewrite=None):
    """Render inline Markdown (code spans, links, strong, emphasis) to escaped HTML. Everything
    outside a recognized inline construct is HTML-escaped. ``link_rewrite`` is an optional
    callable taking the raw url and returning the rewritten url."""
    out = []
    last = 0
    for m in _INLINE_RE.finditer(text):
        out.append(html.escape(text[last:m.start()]))
        if m.group("code") is not None:
            out.append(f"<code>{html.escape(m.group('code'))}</code>")
        elif m.group("linktext") is not None:
            url = m.group("linkurl")
            if link_rewrite is not None:
                url = link_rewrite(url)
            out.append(f'<a href="{html.escape(url)}">{html.escape(m.group("linktext"))}</a>')
        elif m.group("strong") is not None:
            out.append(f"<strong>{html.escape(m.group('strong'))}</strong>")
        elif m.group("em1") is not None:
            out.append(f"<em>{html.escape(m.group('em1'))}</em>")
        else:
            out.append(f"<em>{html.escape(m.group('em2'))}</em>")
        last = m.end()
    out.append(html.escape(text[last:]))
    return "".join(out)


def render_markdown(source, link_rewrite=None):
    """Render a bounded Markdown subset to an HTML body fragment. Deterministic and pure.
    Raises ``MarkdownError`` on unsupported raw HTML or ambiguous/nested constructs."""
    lines = source.splitlines()
    out = []
    used_ids = set()
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        if not line.strip():
            i += 1
            continue

        fence_m = _FENCE_RE.match(line)
        if fence_m:
            lang = fence_m.group(1)
            i += 1
            code_lines = []
            closed = False
            while i < n:
                if _FENCE_RE.match(lines[i]) and lines[i].strip() == "```":
                    closed = True
                    i += 1
                    break
                code_lines.append(lines[i])
                i += 1
            if not closed:
                raise MarkdownError("unterminated fenced code block")
            cls = f' class="language-{html.escape(lang)}"' if lang else ""
            body = html.escape("\n".join(code_lines))
            out.append(f"<pre><code{cls}>{body}</code></pre>")
            continue

        heading_m = _HEADING_RE.match(line)
        if heading_m:
            hashes, text = heading_m.groups()
            level = len(hashes)
            if level > 4:
                raise MarkdownError(f"unsupported heading depth (H{level}): {line!r}")
            _check_no_raw_html(text)
            hid = slugify_heading(text, used_ids)
            out.append(f'<h{level} id="{hid}">{_render_inline(text, link_rewrite)}</h{level}>')
            i += 1
            continue

        if _BLOCKQUOTE_RE.match(line):
            quote_lines = []
            while i < n and _BLOCKQUOTE_RE.match(lines[i]):
                m = _BLOCKQUOTE_RE.match(lines[i])
                quote_lines.append(m.group(1))
                i += 1
            for ql in quote_lines:
                _check_no_raw_html(ql)
            text = " ".join(q for q in quote_lines if q.strip())
            out.append(
                f'<blockquote class="callout"><p>{_render_inline(text, link_rewrite)}</p>'
                f"</blockquote>"
            )
            continue

        if _ORDERED_RE.match(line) or _UNORDERED_RE.match(line):
            is_ordered = bool(_ORDERED_RE.match(line))
            tag = "ol" if is_ordered else "ul"
            items = []
            while i < n:
                cur = lines[i]
                if not cur.strip():
                    break
                if cur.startswith((" ", "\t")):
                    raise MarkdownError(f"unsupported nested/indented list item: {cur!r}")
                m_o = _ORDERED_RE.match(cur)
                m_u = _UNORDERED_RE.match(cur)
                if is_ordered and m_o:
                    _check_no_raw_html(m_o.group(2))
                    items.append(m_o.group(2))
                elif not is_ordered and m_u:
                    _check_no_raw_html(m_u.group(1))
                    items.append(m_u.group(1))
                elif m_o or m_u:
                    raise MarkdownError(
                        f"unsupported mixed ordered/unordered list items: {cur!r}"
                    )
                else:
                    break
                i += 1
            li = "".join(f"<li>{_render_inline(t, link_rewrite)}</li>" for t in items)
            out.append(f"<{tag}>{li}</{tag}>")
            continue

        if "|" in line and i + 1 < n and _TABLE_SEP_RE.match(lines[i + 1].strip()):
            header_cells = [c.strip() for c in line.strip().strip("|").split("|")]
            sep_cells = [c.strip() for c in lines[i + 1].strip().strip("|").split("|")]
            if len(header_cells) != len(sep_cells):
                raise MarkdownError(f"malformed table: column count mismatch at {line!r}")
            i += 2
            body_rows = []
            while i < n and "|" in lines[i] and lines[i].strip():
                row_cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if len(row_cells) != len(header_cells):
                    raise MarkdownError(
                        f"malformed table: row column count mismatch at {lines[i]!r}"
                    )
                body_rows.append(row_cells)
                i += 1
            for cell in header_cells:
                _check_no_raw_html(cell)
            thead = "".join(
                f"<th>{_render_inline(c, link_rewrite)}</th>" for c in header_cells
            )
            trows = []
            for row in body_rows:
                for cell in row:
                    _check_no_raw_html(cell)
                tds = "".join(f"<td>{_render_inline(c, link_rewrite)}</td>" for c in row)
                trows.append(f"<tr>{tds}</tr>")
            out.append(
                f"<table><thead><tr>{thead}</tr></thead><tbody>{''.join(trows)}</tbody></table>"
            )
            continue

        para_lines = []
        while i < n and lines[i].strip():
            if (
                _HEADING_RE.match(lines[i])
                or _FENCE_RE.match(lines[i])
                or _BLOCKQUOTE_RE.match(lines[i])
                or _ORDERED_RE.match(lines[i])
                or _UNORDERED_RE.match(lines[i])
            ):
                break
            para_lines.append(lines[i])
            i += 1
        text = " ".join(para_lines)
        _check_no_raw_html(text)
        out.append(f"<p>{_render_inline(text, link_rewrite)}</p>")

    return "\n".join(out)


# --------------------------------------------------------------------------- HTML shell

def build_html_shell(title, body_html, markdown_href, css_href=ASSET_CSS_PATH, lang="en"):
    """Wrap a rendered body fragment in an accessible, fully offline HTML document: doctype,
    ``lang``, UTF-8, viewport, title, a skip link, a navigation placeholder, ``<main>``, a
    companion-Markdown link, and a relative stylesheet link. No script tag, no external
    resource."""
    safe_title = html.escape(title)
    safe_md_href = html.escape(markdown_href)
    safe_css_href = html.escape(css_href)
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="{html.escape(lang)}">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"  <title>{safe_title}</title>\n"
        f'  <link rel="stylesheet" href="{safe_css_href}">\n'
        "</head>\n"
        "<body>\n"
        '  <a class="skip-link" href="#main">Skip to main content</a>\n'
        '  <nav aria-label="Primary"><!-- navigation placeholder --></nav>\n'
        '  <main id="main">\n'
        f"    <h1>{safe_title}</h1>\n"
        f"    {body_html}\n"
        f'    <p class="source-link"><a href="{safe_md_href}">View Markdown source</a></p>\n'
        "  </main>\n"
        "</body>\n"
        "</html>\n"
    )


DEFAULT_STYLE_CSS = (
    "/* generated by bin/copilot_docs.py — offline, no external resources */\n"
    ":root {\n"
    "  --bg: #faf9f6; --ink: #1e2430; --muted: #5c6470; --line: #e3ded3;\n"
    "  --accent: #b45309; --card: #ffffff; --code-bg: #efece4;\n"
    "  --pre-bg: #23262e; --pre-ink: #e8e6e1;\n"
    "  --tier-frontier: #b91c1c; --tier-strong: #b45309;\n"
    "  --tier-mid: #15803d; --tier-cheap: #0e7490;\n"
    "}\n"
    "* { box-sizing: border-box; }\n"
    "body {\n"
    "  margin: 0; background: var(--bg); color: var(--ink);\n"
    "  font: 17px/1.65 Georgia, 'Times New Roman', serif;\n"
    "}\n"
    "main {\n"
    "  display: block; max-width: 60rem; margin: 0 auto; padding: 1.5rem 1.25rem 4rem;\n"
    "}\n"
    "nav {\n"
    "  max-width: 60rem; margin: 0 auto; padding: 0.75rem 1.25rem 0;\n"
    "  color: var(--muted); font-size: 0.9em;\n"
    "}\n"
    "h1 { font-size: 2rem; line-height: 1.2; margin: 0 0 1rem; }\n"
    "h2 {\n"
    "  font-size: 1.4rem; margin: 2.5rem 0 0.8rem; padding-top: 1rem;\n"
    "  border-top: 1px solid var(--line);\n"
    "}\n"
    "h3 { font-size: 1.1rem; margin: 1.6rem 0 0.5rem; }\n"
    "a { color: var(--accent); }\n"
    "a:focus-visible, button:focus-visible, .skip-link:focus-visible {\n"
    "  outline: 3px solid var(--accent); outline-offset: 2px;\n"
    "}\n"
    "code, pre {\n"
    "  font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;\n"
    "  font-size: 0.9em;\n"
    "}\n"
    "code { background: var(--code-bg); padding: 0.1em 0.35em; border-radius: 4px; }\n"
    "pre {\n"
    "  background: var(--pre-bg); color: var(--pre-ink); padding: 1rem 1.2rem;\n"
    "  border-radius: 10px; overflow-x: auto; line-height: 1.5;\n"
    "}\n"
    "pre code { background: none; padding: 0; color: inherit; }\n"
    "table {\n"
    "  border-collapse: collapse; width: 100%;\n"
    "  background: var(--card); font-size: 0.92em; margin: 1rem 0;\n"
    "}\n"
    "th, td {\n"
    "  border: 1px solid var(--line); padding: 0.5rem 0.75rem;\n"
    "  text-align: left; vertical-align: top;\n"
    "}\n"
    "th { background: #f1eee6; }\n"
    "blockquote.callout {\n"
    "  background: #fdf6ec; border-left: 4px solid var(--accent);\n"
    "  padding: 0.8rem 1.1rem; margin: 1.2rem 0; border-radius: 0 8px 8px 0;\n"
    "}\n"
    "blockquote.callout p { margin: 0; }\n"
    ".tier-cheap { color: var(--tier-cheap); font-weight: 700; }\n"
    ".tier-mid { color: var(--tier-mid); font-weight: 700; }\n"
    ".tier-strong { color: var(--tier-strong); font-weight: 700; }\n"
    ".tier-frontier { color: var(--tier-frontier); font-weight: 700; }\n"
    ".skip-link {\n"
    "  position: absolute; left: -999px; top: 0; background: var(--card);\n"
    "  color: var(--ink); padding: 0.5rem 1rem; z-index: 10;\n"
    "}\n"
    ".skip-link:focus { left: 0.5rem; top: 0.5rem; }\n"
    ".source-link { color: var(--muted); font-size: 0.9em; margin-top: 3rem; }\n"
    "@media (max-width: 40rem) {\n"
    "  main { padding: 1rem 0.85rem 3rem; }\n"
    "  nav { padding: 0.5rem 0.85rem 0; }\n"
    "  h1 { font-size: 1.6rem; }\n"
    "  table { display: block; overflow-x: auto; white-space: nowrap; }\n"
    "}\n"
    "@media print {\n"
    "  body, main, nav, pre, code, th, blockquote.callout { background: none !important; }\n"
    "  a, a:visited { color: var(--ink); text-decoration: underline; }\n"
    "  table, th, td { border-color: #000; }\n"
    "  .skip-link { display: none; }\n"
    "}\n"
)


# --------------------------------------------------------------------------- link rewriting

def _document_by_markdown(manifest):
    return {doc["markdown"]: doc for doc in manifest.get("documents", []) if "markdown" in doc}


def make_link_rewriter(manifest):
    """Return a ``link_rewrite`` callable for ``render_markdown``: a link whose target matches
    another document's declared Markdown path (optionally with a ``#fragment``) is rewritten to
    that document's HTML path (fragment preserved); every other link (external, or a repo-
    relative link not in the manifest, or a bare ``#fragment``) passes through unchanged."""
    by_markdown = _document_by_markdown(manifest)

    def _rewrite(url):
        target, sep, fragment = url.partition("#")
        if target in by_markdown:
            new_url = by_markdown[target]["html"]
            return new_url + (sep + fragment if sep else "")
        return url

    return _rewrite


# --------------------------------------------------------------------------- artifact planning

def apply_generated_blocks(source_text, block_context):
    """Splice every generated-block marker present in ``source_text`` using
    ``GENERATED_BLOCK_PROVIDERS``, in document order, preserving every authored byte outside the
    marker bodies. Structural marker validity (missing pairs, duplicates, nesting, reversal,
    mismatches) is enforced by ``_scan_markers`` — a defect there raises ``MarkerError``.
    Content with no markers at all is returned unchanged (never touched).

    Raises ``GeneratedBlockError`` for a marker name with no known provider, or when a present
    marker needs ``block_context`` (the pricing/prefs snapshot data the providers read) but none
    was supplied."""
    pairs = _scan_markers(source_text)
    if not pairs:
        return source_text
    spliced = source_text
    for name, _begin_start, _begin_end, _end_start, _end_end in pairs:
        provider = GENERATED_BLOCK_PROVIDERS.get(name)
        if provider is None:
            raise GeneratedBlockError(f"unknown generated block marker: {name!r}")
        if block_context is None:
            raise GeneratedBlockError(
                f"generated block {name!r} requires generation context "
                "(pricing/prefs snapshot) but none was supplied"
            )
        spliced = replace_generated_block(spliced, name, provider(block_context))
    return spliced


def strip_marker_comment_lines(text):
    """Drop every marker comment line (``<!-- BEGIN/END GENERATED: name -->``) from ``text``.
    Marker lines are structural bookkeeping for the canonical Markdown source, not reader-facing
    prose, and the existing bounded renderer's raw-HTML guard (by design) rejects any
    HTML-comment-shaped line — so HTML is rendered from this marker-free view of the post-splice
    Markdown, while the ``.md`` artifact itself keeps the marker lines verbatim."""
    return "\n".join(
        line for line in text.splitlines() if not MARKER_RE.fullmatch(line.strip())
    )


def plan_artifacts(manifest, repo_root, docs_root, block_context=None):
    """Pure artifact planner: returns a dict mapping docs-root-relative POSIX path strings to
    the exact bytes that should exist there. Never writes to disk, but DOES read each
    document's canonical Markdown from ``docs_root`` — Markdown is the canonical
    human-authored source (PLAN 'Canonical content' / D1); this planner never synthesizes a
    title/tier/profile stub. A document whose canonical Markdown file is missing under
    ``docs_root`` raises ``CanonicalSourceError``. Every generated-block marker actually present
    in a document's canonical Markdown is spliced via ``apply_generated_blocks``; HTML is then
    rendered from the resulting post-splice Markdown bytes (marker comment lines themselves
    excluded — see ``strip_marker_comment_lines``). Deterministic across identical inputs (no
    wall clock, no random values, stable iteration order)."""
    repo_root = Path(repo_root)
    docs_root = Path(docs_root)
    rewrite = make_link_rewriter(manifest)
    plan = {}

    for doc in manifest.get("documents", []):
        title = doc["title"]
        md_relpath = doc["markdown"]
        canonical_path = docs_root / md_relpath
        if not canonical_path.is_file():
            raise CanonicalSourceError(
                f"missing canonical Markdown source for {md_relpath!r}: {canonical_path}"
            )
        source_text = canonical_path.read_text(encoding="utf-8")
        markdown_text = apply_generated_blocks(source_text, block_context)

        plan[md_relpath] = markdown_text.encode("utf-8")

        html_source = strip_marker_comment_lines(markdown_text)
        body_html = render_markdown(html_source, link_rewrite=rewrite)
        full_html = build_html_shell(title, body_html, markdown_href=Path(md_relpath).name)
        plan[doc["html"]] = full_html.encode("utf-8")

    plan[ASSET_CSS_PATH] = DEFAULT_STYLE_CSS.encode("utf-8")
    return plan


def _assert_in_scope(docs_root, relpath):
    if not _path_within(docs_root, relpath):
        raise ArtifactScopeError(f"refusing to write outside the docs root: {relpath!r}")


def write_artifacts(plan, docs_root):
    """Write every ``plan`` entry under ``docs_root``. May only create/replace paths that
    resolve under ``docs_root``; raises ``ArtifactScopeError`` (writing nothing for that entry)
    if a path would escape it."""
    docs_root = Path(docs_root)
    for relpath, data in plan.items():
        _assert_in_scope(docs_root, relpath)
        target = docs_root / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def check_artifacts(plan, docs_root):
    """Read-only comparison of ``plan`` against what's on disk under ``docs_root``. Returns a
    sorted list of relpath strings that are missing or whose on-disk bytes differ from the
    plan. Never writes anything."""
    docs_root = Path(docs_root)
    stale = []
    for relpath, data in plan.items():
        target = docs_root / relpath
        if not target.is_file():
            stale.append(relpath)
            continue
        if target.read_bytes() != data:
            stale.append(relpath)
    return sorted(stale)


# --------------------------------------------------------------------------- sibling module loading

_pricing_mod = None
_prefs_mod = None


def _load_sibling(name):
    """Load a sibling ``bin/<name>.py`` module by absolute path via ``importlib``, the house
    convention (``bin`` is never imported as a package)."""
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pricing_module():
    global _pricing_mod
    if _pricing_mod is None:
        _pricing_mod = _load_sibling("copilot_pricing")
    return _pricing_mod


def _prefs_module():
    global _prefs_mod
    if _prefs_mod is None:
        _prefs_mod = _load_sibling("copilot_prefs")
    return _prefs_mod


def _default_cache_hit(pricing_mod):
    """The engine's own default ``cache_hit`` for ``est_cost``, read via introspection so this
    module never copies the numeric default."""
    return inspect.signature(pricing_mod.est_cost).parameters["cache_hit"].default


# --------------------------------------------------------------------------- hashing / freshness

def sha256_hex(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def hash_file_bytes(path):
    """SHA-256 of the exact on-disk bytes at ``path``."""
    return sha256_hex(Path(path).read_bytes())


ROSTER_KEYS = ("models", "task_profiles", "knobs")


def roster_relevant_data(pricing):
    """The ordered roster-relevant subset of ``pricing`` that generated blocks actually render:
    ``models``, ``task_profiles``, ``knobs`` — in file order, nothing else (metadata such as
    ``cached_date``/``update_from``/prose notes about the file are covered by the whole-file
    pricing hash already)."""
    return {k: pricing[k] for k in ROSTER_KEYS if k in pricing}


def roster_hash(pricing):
    """SHA-256 over a canonical (insertion-ordered, since dict order round-trips through
    ``json.load``) JSON encoding of ``roster_relevant_data``."""
    canonical = json.dumps(roster_relevant_data(pricing), sort_keys=False, ensure_ascii=True)
    return sha256_hex(canonical)


def source_set_hash(repo_root, resolved_paths):
    """SHA-256 over the sorted, de-duplicated ``resolved_paths`` list combined with each file's
    own content hash — deterministic regardless of filesystem iteration order, and changes
    whenever a source file's *content* changes even if the resolved path list itself does not."""
    repo_root = Path(repo_root)
    parts = [f"{rel}:{hash_file_bytes(repo_root / rel)}" for rel in sorted(set(resolved_paths))]
    return sha256_hex("\n".join(parts))


def _relative_to_repo(path, repo_root):
    """Repo-relative POSIX path when ``path`` resolves under ``repo_root``; otherwise the given
    value unchanged (never guessed) — used so a machine-specific absolute path never gets
    serialized for an in-repo source."""
    try:
        return Path(path).resolve().relative_to(Path(repo_root).resolve()).as_posix()
    except ValueError:
        return str(path)


def build_pricing_snapshot(pricing, pricing_path, repo_root):
    """The visible pricing-snapshot facts that every generated block/report begins with."""
    return {
        "path": _relative_to_repo(pricing_path, repo_root),
        "cached_date": pricing["cached_date"],
        "pricing_sha256": hash_file_bytes(pricing_path),
        "roster_sha256": roster_hash(pricing),
    }


def snapshot_line(pricing_snapshot):
    return (
        f"Snapshot: `{pricing_snapshot['path']}` (cached_date {pricing_snapshot['cached_date']}) "
        f"— pricing sha256 `{pricing_snapshot['pricing_sha256']}`, roster sha256 "
        f"`{pricing_snapshot['roster_sha256']}`."
    )


# --------------------------------------------------------------------------- preference handling

def used_tiers(manifest):
    """Sorted set of symbolic tiers referenced by the manifest's estimated documents."""
    tiers = set()
    for doc in manifest.get("documents", []):
        authoring = doc.get("authoring", {})
        if authoring.get("mode") == "estimated":
            tiers.add(authoring["tier"])
    return sorted(tiers)


def resolve_prefs_snapshot(pricing, prefs, manifest, repo_root):
    """Resolve every manifest-used tier against ``prefs`` (an ``effective_prefs``-shaped dict:
    ``pins``/``excludes``/``notes``/``source``). Returns a JSON-safe snapshot dict recording
    ``source`` (normalized to a repo-relative path when it resolves under ``repo_root``),
    ``pins``, ``excludes``, ``notes``, ``resolved`` (tier -> model id), and ``resolved_via``
    (tier -> ``"pin"`` or ``"roster-default"``).

    Raises ``PrefsResolutionError`` for a used tier resolving to ``None``, or to a model id that
    is also in the effective excludes — both are hard errors, never silently tolerated."""
    prefs_mod = _prefs_module()
    pins = dict(prefs.get("pins") or {})
    excludes = sorted(set(prefs.get("excludes") or []))
    excludes_set = set(excludes)

    resolved = {}
    resolved_via = {}
    for tier in used_tiers(manifest):
        model_id = prefs_mod.resolve_tier(pricing, tier, prefs)
        if model_id is None:
            raise PrefsResolutionError(f"tier {tier!r} used by the manifest has no resolution")
        if model_id in excludes_set:
            raise PrefsResolutionError(
                f"tier {tier!r} resolved to excluded model {model_id!r}"
            )
        resolved[tier] = model_id
        resolved_via[tier] = "pin" if tier in pins else "roster-default"

    source = prefs.get("source")
    if source is not None:
        source = _relative_to_repo(source, repo_root)

    return {
        "source": source,
        "pins": pins,
        "excludes": excludes,
        "notes": list(prefs.get("notes") or []),
        "resolved": resolved,
        "resolved_via": resolved_via,
    }


# --------------------------------------------------------------------------- measurement

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_LEXEME_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def count_words(text):
    """Unicode word count."""
    return len(_WORD_RE.findall(text))


def count_lexemes(text):
    """Lexical unit count: a Unicode word run OR a standalone non-whitespace punctuation/symbol
    character, per the pinned regex semantics."""
    return len(_LEXEME_RE.findall(text))


def strip_generated_blocks(content):
    """Remove every well-formed generated-block BEGIN/END pair's *inner body* (keeping the
    marker lines themselves) so ``ai_output_lexemes`` measures only hand-authored prose, never
    the volatile machine-derived tables between the markers. Content with no markers at all is
    returned unchanged. Raises ``MarkerError`` for malformed markers (delegated to
    ``_scan_markers``)."""
    pairs = _scan_markers(content)
    if not pairs:
        return content
    out = []
    cursor = 0
    for _name, begin_start, begin_end, end_start, end_end in sorted(pairs, key=lambda p: p[1]):
        out.append(content[cursor:begin_end])
        cursor = end_start
    out.append(content[cursor:])
    return "".join(out)


def ai_output_lexemes(markdown_source):
    """Lexeme count of authored Markdown, excluding generated-marker bodies."""
    return count_lexemes(strip_generated_blocks(markdown_source))


def _safe_cell(text):
    """Collapse whitespace/newlines to single spaces and neutralize ``|`` so arbitrary pricing
    prose can't break the bounded pipe-table renderer's column parsing."""
    collapsed = " ".join(str(text).split()).replace("|", "/")
    return re.sub(r"(<[A-Za-z][A-Za-z0-9_.:-]*>)", r"`\1`", collapsed)


# --------------------------------------------------------------------------- cost accounting

def estimate_document_cost(pricing, prefs, tier, input_profile, markdown_source, cache_hit=None,
                            today=None):
    """Cost one estimated document. The manifest's ``input_profile`` supplies the assumed input
    tokens; this document's measured ``ai_output_lexemes`` stands in for output tokens. Exactly
    one ephemeral in-memory task profile is added to a *copy* of ``pricing`` (the real
    ``task_profiles`` on disk is never touched) and the entire USD/AIC formula is delegated to
    ``copilot_pricing.est_cost`` — no rate or formula is duplicated here.

    Raises ``PrefsResolutionError`` if ``tier`` has no resolution under ``prefs``."""
    pricing_mod = _pricing_module()
    prefs_mod = _prefs_module()

    model_id = prefs_mod.resolve_tier(pricing, tier, prefs)
    if model_id is None:
        raise PrefsResolutionError(f"tier {tier!r} has no resolution for cost estimation")

    base_profile = pricing["task_profiles"][input_profile]
    output_tokens = ai_output_lexemes(markdown_source)

    ephemeral_pricing = dict(pricing)
    ephemeral_pricing["task_profiles"] = dict(pricing["task_profiles"])
    runtime_profile_label = f"__copilot_docs__{input_profile}"
    ephemeral_pricing["task_profiles"][runtime_profile_label] = {
        "label": f"copilot-docs measured output ({input_profile} input)",
        "input_tokens": base_profile["input_tokens"],
        "output_tokens": output_tokens,
    }

    effective_cache_hit = (
        cache_hit if cache_hit is not None else _default_cache_hit(pricing_mod)
    )
    kwargs = {"cache_hit": effective_cache_hit}
    if today is not None:
        kwargs["today"] = today
    result = pricing_mod.est_cost(ephemeral_pricing, runtime_profile_label, model_id, **kwargs)

    model_info = pricing["models"][model_id]
    return {
        "model_id": model_id,
        "model_display": model_info["display"],
        "model_vendor": model_info["vendor"],
        "model_tier": model_info["tier"],
        "symbolic_tier": tier,
        "symbolic_profile": input_profile,
        "runtime_profile_label": runtime_profile_label,
        "assumed_input_tokens": base_profile["input_tokens"],
        "measured_output_lexemes": output_tokens,
        "cache_hit_assumed": effective_cache_hit,
        "rates_used": result["rates_used"],
        "warnings": list(result["warnings"]),
        "usd": result["usd"],
        "aic": result["aic"],
        "uncertainty": (
            "Prospective estimate: assumes the manifest's declared input-token convention and "
            "treats this document's own measured lexeme count as a stand-in for model output "
            "tokens — not a historical usage measurement."
        ),
    }


# --------------------------------------------------------------------------- frontmatter / inventories

_FRONTMATTER_FENCE = "---"


def parse_frontmatter(text):
    """Parse a ``---``-delimited frontmatter block into a ``(meta, body)`` pair. A line whose
    first non-whitespace character is ``#`` is a comment and is skipped before parsing; every
    remaining frontmatter line is split on the first ``:`` (unparseable lines skipped, never a
    crash). Returns ``({}, text)`` unchanged when there is no well-formed opening/closing fence
    pair."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != _FRONTMATTER_FENCE:
        return {}, text
    close_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == _FRONTMATTER_FENCE:
            close_idx = i
            break
    if close_idx is None:
        return {}, text
    meta = {}
    for line in lines[1:close_idx]:
        if line.lstrip().startswith("#"):
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    body = "\n".join(lines[close_idx + 1:])
    return meta, body


def discover_skills(repo_root):
    """Every ``copilot/.github/skills/*/SKILL.md``, sorted by directory name: ``name``,
    ``description``, and its repo-relative ``source_path``."""
    repo_root = Path(repo_root)
    skills_root = repo_root / "copilot" / ".github" / "skills"
    rows = []
    if not skills_root.is_dir():
        return rows
    for skill_dir in sorted(p for p in skills_root.iterdir() if p.is_dir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        meta, _ = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        rows.append({
            "name": meta.get("name", skill_dir.name),
            "description": meta.get("description", ""),
            "source_path": skill_md.relative_to(repo_root).as_posix(),
        })
    return rows


def discover_agents(repo_root):
    """Every ``copilot/.github/agents/*.agent.md``, sorted by filename: ``name``,
    ``description``, configured ``model``, and its repo-relative ``source_path``."""
    repo_root = Path(repo_root)
    agents_root = repo_root / "copilot" / ".github" / "agents"
    rows = []
    if not agents_root.is_dir():
        return rows
    for agent_md in sorted(agents_root.glob("*.agent.md")):
        meta, _ = parse_frontmatter(agent_md.read_text(encoding="utf-8"))
        stem = agent_md.name[:-len(".agent.md")]
        rows.append({
            "name": meta.get("name", stem),
            "description": meta.get("description", ""),
            "model": meta.get("model", ""),
            "source_path": agent_md.relative_to(repo_root).as_posix(),
        })
    return rows


def annotate_agent_rows(rows, pricing, prefs):
    """Add ``configured_tier`` (derived from pricing), ``is_excluded``, and
    ``matches_active_resolution`` to each agent row in place. Returns ``rows``."""
    prefs_mod = _prefs_module()
    models = pricing["models"]
    excludes = set(prefs.get("excludes") or [])
    for row in rows:
        info = models.get(row["model"])
        configured_tier = info["tier"] if info else None
        row["configured_tier"] = configured_tier
        row["is_excluded"] = row["model"] in excludes
        active = prefs_mod.resolve_tier(pricing, configured_tier, prefs) if configured_tier else None
        row["matches_active_resolution"] = active is not None and active == row["model"]
    return rows


# --------------------------------------------------------------------------- generated block providers

def render_skills_inventory_block(pricing_snapshot, repo_root):
    rows = discover_skills(repo_root)
    lines = [snapshot_line(pricing_snapshot), "", "| Skill | Description | Source |", "|---|---|---|"]
    for r in rows:
        lines.append(f"| `{r['name']}` | {_safe_cell(r['description'])} | `{r['source_path']}` |")
    return "\n".join(lines)


def render_agents_inventory_block(pricing, pricing_snapshot, repo_root, prefs):
    rows = annotate_agent_rows(discover_agents(repo_root), pricing, prefs)
    lines = [
        snapshot_line(pricing_snapshot), "",
        "| Agent | Description | Model | Tier | Excluded | Matches active |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['name']}` | {_safe_cell(r['description'])} | `{r['model']}` | "
            f"{r['configured_tier'] or 'n/a'} | {'yes' if r['is_excluded'] else 'no'} | "
            f"{'yes' if r['matches_active_resolution'] else 'no'} |"
        )
    return "\n".join(lines)


def render_model_preferences_block(pricing_snapshot, prefs_snapshot):
    lines = [snapshot_line(pricing_snapshot), ""]
    lines.append(f"- Prefs source: `{prefs_snapshot['source'] or '(none — defaults)'}`")
    lines.append("")
    if prefs_snapshot["pins"]:
        lines.append("| Tier | Pinned model |")
        lines.append("|---|---|")
        for tier, model_id in prefs_snapshot["pins"].items():
            lines.append(f"| {tier} | `{model_id}` |")
    else:
        lines.append("- No pins active.")
    lines.append("")
    if prefs_snapshot["excludes"]:
        lines.append("| Excluded model |")
        lines.append("|---|")
        for model_id in prefs_snapshot["excludes"]:
            lines.append(f"| `{model_id}` |")
    else:
        lines.append("- No excludes active.")
    lines.append("")
    lines.append("| Tier | Resolves to | Via |")
    lines.append("|---|---|---|")
    for tier, model_id in prefs_snapshot["resolved"].items():
        lines.append(f"| {tier} | `{model_id}` | {prefs_snapshot['resolved_via'][tier]} |")
    for note in prefs_snapshot["notes"]:
        lines.append("")
        lines.append(f"> {_safe_cell(note)}")
    return "\n".join(lines)


def render_model_roster_block(pricing, pricing_snapshot, prefs):
    excludes = set(prefs.get("excludes") or [])
    lines = [
        snapshot_line(pricing_snapshot), "",
        "| Model | Display | Vendor | Tier | Input $/MTok | Cached input $/MTok | "
        "Output $/MTok | Notes | Preference |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for model_id, info in pricing["models"].items():
        preference = "excluded" if model_id in excludes else "eligible"
        lines.append(
            f"| `{model_id}` | {info['display']} | {info['vendor']} | {info['tier']} | "
            f"{info['input_per_mtok']} | {info['cached_input_per_mtok']} | "
            f"{info['output_per_mtok']} | {_safe_cell(info.get('notes', ''))} | {preference} |"
        )
    return "\n".join(lines)


def render_reasoning_knobs_block(pricing_snapshot, knobs):
    lines = [snapshot_line(pricing_snapshot), ""]
    efforts = knobs.get("reasoning_efforts", [])
    if efforts:
        lines.append("| Reasoning effort |")
        lines.append("|---|")
        for e in efforts:
            lines.append(f"| {e} |")
    note = knobs.get("reasoning_efforts_note")
    if note:
        lines.append("")
        lines.append(_safe_cell(note))
    return "\n".join(lines)


def render_task_profiles_block(pricing_snapshot, task_profiles):
    lines = [
        snapshot_line(pricing_snapshot), "",
        "| Profile | Label | Input tokens | Output tokens |",
        "|---|---|---|---|",
    ]
    for name, p in task_profiles.items():
        lines.append(f"| {name} | {_safe_cell(p['label'])} | {p['input_tokens']} | {p['output_tokens']} |")
    return "\n".join(lines)


# A ``block_context`` dict supplies ``pricing``, ``prefs``, ``pricing_snapshot``,
# ``prefs_snapshot``, and ``repo_root`` — every provider below reads only from it, never from a
# module global, so ``apply_generated_blocks``/``plan_artifacts`` stay pure and testable with
# synthetic fixtures. Marker names are the only vocabulary a canonical Markdown document may use;
# any other name is a hard error (``GeneratedBlockError``) rather than a silent no-op.
GENERATED_BLOCK_PROVIDERS = {
    "skills-inventory": lambda ctx: render_skills_inventory_block(
        ctx["pricing_snapshot"], ctx["repo_root"]
    ),
    "agents-inventory": lambda ctx: render_agents_inventory_block(
        ctx["pricing"], ctx["pricing_snapshot"], ctx["repo_root"], ctx["prefs"]
    ),
    "model-preferences": lambda ctx: render_model_preferences_block(
        ctx["pricing_snapshot"], ctx["prefs_snapshot"]
    ),
    "model-roster": lambda ctx: render_model_roster_block(
        ctx["pricing"], ctx["pricing_snapshot"], ctx["prefs"]
    ),
    "reasoning-knobs": lambda ctx: render_reasoning_knobs_block(
        ctx["pricing_snapshot"], ctx["pricing"]["knobs"]
    ),
    "task-profiles": lambda ctx: render_task_profiles_block(
        ctx["pricing_snapshot"], ctx["pricing"]["task_profiles"]
    ),
}


# --------------------------------------------------------------------------- AIC report

AIC_REPORT_JSON = "aic-report.json"
AIC_REPORT_MD = "AIC-REPORT.md"
AIC_REPORT_HTML = "aic-report.html"
AIC_REPORT_SCHEMA_ID = "copilot-docs/aic-report/v1"
SELF_REFERENCE_NOTE = (
    "self-referential artifact: its own byte size does not exist yet when it is generated, so "
    "its measured-size fields are null/n/a and it always carries zero authoring/render cost."
)


def _doc_source_hash(manifest, repo_root, doc):
    source_sets = manifest.get("source_sets", {})
    resolved = []
    for set_name in doc.get("sources", []):
        resolved.extend(resolve_source_set(repo_root, source_sets.get(set_name, [])))
    resolved = sorted(set(resolved))
    return source_set_hash(repo_root, resolved) if resolved else None


def detect_drift(recorded_report, pricing, pricing_path, manifest, repo_root):
    """Compare a recorded ``aic-report.json`` snapshot (as produced by ``build_aic_report``)
    against *current* pricing/manifest/source files. Returns a list of human-readable drift
    descriptions (empty == no drift). Never reads a local prefs file — the recorded
    ``prefs_snapshot`` is the only prefs input; only its recorded model ids are re-validated
    against current pricing."""
    drift = []
    recorded_ps = recorded_report.get("pricing_snapshot", {})
    if recorded_ps.get("pricing_sha256") != hash_file_bytes(pricing_path):
        drift.append("pricing file bytes changed since the last build")
    if recorded_ps.get("roster_sha256") != roster_hash(pricing):
        drift.append("pricing roster (models/task_profiles/knobs) changed since the last build")

    recorded_pf = recorded_report.get("prefs_snapshot", {})
    ids_to_check = list(recorded_pf.get("pins", {}).values()) + list(recorded_pf.get("excludes", []))
    for model_id in ids_to_check:
        if model_id not in pricing["models"]:
            drift.append(f"recorded model id is no longer a live pricing id: {model_id!r}")

    for row in recorded_report.get("documents", []):
        if row.get("kind") != "markdown" or row.get("self_reference"):
            continue
        doc = next((d for d in manifest["documents"] if d["markdown"] == row["path"]), None)
        if doc is None:
            continue
        current_hash = _doc_source_hash(manifest, repo_root, doc)
        if current_hash != row.get("sources_sha256"):
            drift.append(f"source set for {row['path']!r} changed since the last build")

    return drift


def reconstruct_prefs_from_snapshot(prefs_snapshot):
    """Rebuild an ``effective_prefs``-shaped dict from a recorded ``prefs_snapshot`` — used by
    ``check`` so it never has to read a local prefs file."""
    return {
        "pins": dict(prefs_snapshot.get("pins", {})),
        "excludes": list(prefs_snapshot.get("excludes", [])),
        "notes": list(prefs_snapshot.get("notes", [])),
        "source": prefs_snapshot.get("source"),
    }


def build_aic_report(manifest, repo_root, docs_root, pricing, pricing_path, prefs, today=None):
    """Build the full AIC report dict plus the underlying document artifact plan. Pure and
    deterministic given the same manifest/docs_root contents/pricing/prefs/today; raises
    ``PrefsResolutionError`` for any manifest-used tier that fails to resolve (see
    ``resolve_prefs_snapshot``), or ``CanonicalSourceError``/``GeneratedBlockError`` if a
    document's canonical Markdown is missing or uses an unknown generated-block marker (see
    ``plan_artifacts``)."""
    repo_root = Path(repo_root)
    docs_root = Path(docs_root)
    if today is None:
        today = date.fromisoformat(pricing["cached_date"])

    pricing_snapshot = build_pricing_snapshot(pricing, pricing_path, repo_root)
    prefs_snapshot = resolve_prefs_snapshot(pricing, prefs, manifest, repo_root)

    block_context = {
        "pricing": pricing,
        "prefs": prefs,
        "pricing_snapshot": pricing_snapshot,
        "prefs_snapshot": prefs_snapshot,
        "repo_root": repo_root,
    }
    plan = plan_artifacts(manifest, repo_root, docs_root, block_context=block_context)

    doc_rows = []
    total_usd = 0.0
    total_aic = 0.0

    for doc in manifest.get("documents", []):
        md_path, html_path = doc["markdown"], doc["html"]
        authoring = doc.get("authoring", {})
        mode = authoring.get("mode")
        md_bytes = plan[md_path]
        md_text = md_bytes.decode("utf-8")
        html_bytes = plan[html_path]
        sources_sha256 = _doc_source_hash(manifest, repo_root, doc)

        measurement = {
            "bytes": len(md_bytes),
            "words": count_words(md_text),
            "lexemes": count_lexemes(md_text),
        }

        if mode == "estimated":
            cost_detail = estimate_document_cost(
                pricing, prefs, authoring["tier"], authoring["input_profile"], md_text,
                today=today,
            )
            measurement["ai_output_lexemes"] = cost_detail["measured_output_lexemes"]
            cost = {k: v for k, v in cost_detail.items() if k != "measured_output_lexemes"}
            total_usd += cost_detail["usd"]
            total_aic += cost_detail["aic"]
        else:
            measurement["ai_output_lexemes"] = None
            cost = {"usd": 0.0, "aic": 0.0, "note": "deterministic document — zero authoring cost"}

        md_row = {
            "path": md_path, "kind": "markdown", "title": doc["title"],
            "authoring_mode": mode, "sources_sha256": sources_sha256,
            "measurement": measurement, "cost": cost,
        }
        if mode == "estimated":
            md_row["resolved_model_id"] = cost_detail["model_id"]
        doc_rows.append(md_row)
        doc_rows.append({
            "path": html_path, "kind": "html", "title": doc["title"],
            "authoring_mode": mode, "markdown_source": md_path,
            "measurement": {"bytes": len(html_bytes)},
            "cost": {
                "usd": 0.0, "aic": 0.0,
                "note": "HTML is a deterministic render of its Markdown source — zero cost",
            },
        })

    for self_path, self_kind, source in (
        (AIC_REPORT_MD, "markdown", None),
        (AIC_REPORT_HTML, "html", AIC_REPORT_MD),
    ):
        row = {
            "path": self_path, "kind": self_kind, "title": "AIC Report",
            "authoring_mode": "deterministic", "self_reference": True,
            "measurement": {"bytes": None, "words": None, "lexemes": None, "ai_output_lexemes": None},
            "cost": {"usd": 0.0, "aic": 0.0, "note": SELF_REFERENCE_NOTE},
        }
        if source is not None:
            row["markdown_source"] = source
        doc_rows.append(row)

    report = {
        "schema": AIC_REPORT_SCHEMA_ID,
        "pricing_snapshot": pricing_snapshot,
        "prefs_snapshot": prefs_snapshot,
        "inputs": {
            "prefs": {
                "pins": dict(prefs_snapshot["pins"]),
                "excludes": list(prefs_snapshot["excludes"]),
            },
        },
        "documents": doc_rows,
        "totals": {"usd": total_usd, "aic": total_aic},
    }
    return report, plan


def render_aic_report_markdown(report):
    ps = report["pricing_snapshot"]
    pf = report["prefs_snapshot"]
    lines = [
        "# AIC Report", "",
        snapshot_line(ps), "",
        f"Prefs source: `{pf['source'] or '(none — defaults)'}`", "",
        "| Document | Kind | Mode | Bytes | AIC | USD | Note |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in report["documents"]:
        b = row["measurement"].get("bytes")
        b_display = b if b is not None else "n/a"
        cost = row["cost"]
        note = cost.get("note") or cost.get("uncertainty", "")
        lines.append(
            f"| `{row['path']}` | {row['kind']} | {row['authoring_mode']} | {b_display} | "
            f"{cost['aic']:.4f} | {cost['usd']:.4f} | {_safe_cell(note)} |"
        )
    totals = report["totals"]
    lines.append("")
    lines.append(
        f"**Totals (estimated Markdown only):** {totals['aic']:.4f} AIC / ${totals['usd']:.4f}"
    )
    return "\n".join(lines) + "\n"


def render_aic_report_json(report):
    return (json.dumps(report, indent=2, sort_keys=False) + "\n").encode("utf-8")


def plan_with_aic_report(manifest, repo_root, docs_root, pricing, pricing_path, prefs, today=None):
    """``build_aic_report`` plus the three generator-owned report artifacts, merged into one
    plan dict alongside every document's Markdown/HTML. Returns ``(report, plan)``."""
    report, plan = build_aic_report(
        manifest, repo_root, docs_root, pricing, pricing_path, prefs, today=today
    )
    plan = dict(plan)
    plan[AIC_REPORT_JSON] = render_aic_report_json(report)
    md = render_aic_report_markdown(report)
    plan[AIC_REPORT_MD] = md.encode("utf-8")
    body_html = render_markdown(md)
    plan[AIC_REPORT_HTML] = build_html_shell(
        "AIC Report", body_html, markdown_href=AIC_REPORT_MD
    ).encode("utf-8")
    return report, plan


# --------------------------------------------------------------------------- CLI

def _load_manifest_json(manifest_path):
    return json.loads(Path(manifest_path).read_text(encoding="utf-8"))


def _validate_or_exit(manifest_path, docs_root):
    manifest = _load_manifest_json(manifest_path)
    errors = validate_manifest(manifest, docs_root=docs_root, repo_root=REPO_ROOT)
    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        return manifest, 2
    return manifest, None


def cmd_build(args):
    """Read active repository prefs through ``effective_prefs``, resolve every manifest-used
    tier, and write every generator-owned artifact — including the AIC report, which records
    the effective preference snapshot so ``check`` never needs to touch a local prefs file."""
    manifest_path = DEFAULT_MANIFEST_PATH
    docs_root = DEFAULT_DOCS_ROOT
    manifest, err = _validate_or_exit(manifest_path, docs_root)
    if err:
        return err

    pricing_mod = _pricing_module()
    prefs_mod = _prefs_module()
    pricing = pricing_mod.load_pricing()
    try:
        prefs = prefs_mod.effective_prefs(pricing)
        _report, plan = plan_with_aic_report(
            manifest, REPO_ROOT, docs_root, pricing, pricing_mod.PRICING_PATH, prefs,
        )
    except (PrefsResolutionError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    write_artifacts(plan, docs_root)
    print(f"wrote {len(plan)} artifact(s) under {docs_root}")
    return 0


def cmd_check(args):
    """Read-only. Never reads machine-local active prefs: it loads the effective preference
    snapshot recorded in ``copilot-docs/aic-report.json`` by the last ``build``, validates every
    recorded model id against *current* pricing, reconstructs equivalent prefs in memory, and
    regenerates expected bytes. Pricing/roster/source hashes are compared to the current repo
    files so drift fails even when another machine has no personal prefs file."""
    manifest_path = DEFAULT_MANIFEST_PATH
    docs_root = DEFAULT_DOCS_ROOT
    manifest, err = _validate_or_exit(manifest_path, docs_root)
    if err:
        return err

    report_path = docs_root / AIC_REPORT_JSON
    if not report_path.is_file():
        print(f"error: {report_path} does not exist — run build first", file=sys.stderr)
        return 2
    recorded = json.loads(report_path.read_text(encoding="utf-8"))

    pricing_mod = _pricing_module()
    pricing = pricing_mod.load_pricing()

    drift = detect_drift(recorded, pricing, pricing_mod.PRICING_PATH, manifest, REPO_ROOT)
    if drift:
        for d in drift:
            print(f"drift: {d}")
        return 1

    reconstructed_prefs = reconstruct_prefs_from_snapshot(recorded.get("prefs_snapshot", {}))

    try:
        _report, plan = plan_with_aic_report(
            manifest, REPO_ROOT, docs_root, pricing, pricing_mod.PRICING_PATH, reconstructed_prefs,
        )
    except (PrefsResolutionError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    stale = check_artifacts(plan, docs_root)
    if stale:
        for relpath in stale:
            print(f"stale: {relpath}")
        return 1
    print("up to date")
    return 0


def cmd_report(args):
    """Read-only. Uses current active prefs and prints the human-readable prospective report to
    stdout without writing anything."""
    manifest_path = DEFAULT_MANIFEST_PATH
    docs_root = DEFAULT_DOCS_ROOT
    manifest, err = _validate_or_exit(manifest_path, docs_root)
    if err:
        return err

    pricing_mod = _pricing_module()
    prefs_mod = _prefs_module()
    pricing = pricing_mod.load_pricing()
    try:
        prefs = prefs_mod.effective_prefs(pricing)
        report, _plan = plan_with_aic_report(
            manifest, REPO_ROOT, docs_root, pricing, pricing_mod.PRICING_PATH, prefs,
        )
    except (PrefsResolutionError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    print(render_aic_report_markdown(report), end="")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="copilot_docs.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    build_p = sub.add_parser("build", help="render manifest documents and write them to disk")
    build_p.set_defaults(func=cmd_build)

    check_p = sub.add_parser("check", help="report stale/missing artifacts without writing")
    check_p.set_defaults(func=cmd_check)

    report_p = sub.add_parser("report", help="print a read-only prospective AIC cost report")
    report_p.set_defaults(func=cmd_report)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
