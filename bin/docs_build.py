#!/usr/bin/env python3
"""Generate the docs-site skill-reference pages and deep-dive mirrors.

This module is deterministic, byte-stable, and offline: every run reads only
committed repository content and produces identical output given identical
input, with no reliance on the wall clock, ambient identity, network access,
process execution, or any other nondeterministic source.

`bin/` is not a package; sibling scripts are loaded via
`importlib.util.spec_from_file_location`, per this repo's established convention
(see `tests/test_harness_select.py`'s `_load` helper). This module reuses
`sync_codex_surfaces._frontmatter` for frontmatter parsing rather than
re-implementing it.
"""

import argparse
import importlib.util
import posixpath
import re
import sys
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = Path(__file__).resolve().parent

GITHUB_BLOB_BASE = "https://github.com/agentmc15/polytropos/blob/main/"

# Harness name -> path components (relative to a repo root) of its skills directory.
_HARNESS_SKILL_ROOTS = {
    "claude": ("skills",),
    "copilot": ("copilot", ".github", "skills"),
    "codex": ("codex", "skills"),
}


def _load_sync_codex_surfaces():
    """Load bin/sync_codex_surfaces.py as a sibling module (this file's own bin/,
    not any repo_root passed by a caller — the generator script itself is fixed)."""
    path = BIN_DIR / "sync_codex_surfaces.py"
    spec = importlib.util.spec_from_file_location("sync_codex_surfaces", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_sync_codex_surfaces = _load_sync_codex_surfaces()
_frontmatter = _sync_codex_surfaces._frontmatter


def skill_inventory(repo_root=REPO_ROOT):
    """Return one dict per skill across all three harnesses, sorted by (harness, name).

    Each record: harness ("claude"/"copilot"/"codex"), name (directory name),
    skill_path (repo-relative POSIX path to SKILL.md), description (frontmatter),
    body (frontmatter-stripped markdown), references (sorted repo-relative POSIX
    paths of files anywhere under the skill's references/ dir, or []).

    Every immediate subdirectory of a harness root is a skill and MUST contain a
    SKILL.md whose frontmatter `name` equals the directory name and whose
    `description` is non-empty; any violation raises ValueError naming the path.
    """
    root = Path(repo_root)
    records = []
    for harness, parts in _HARNESS_SKILL_ROOTS.items():
        harness_root = root.joinpath(*parts)
        if not harness_root.is_dir():
            raise ValueError(f"missing skill root: {harness_root}")
        for entry in sorted(harness_root.iterdir(), key=lambda p: p.name):
            if not entry.is_dir():
                continue
            name = entry.name
            skill_md = entry / "SKILL.md"
            if not skill_md.is_file():
                raise ValueError(f"missing SKILL.md: {skill_md}")
            fields, body = _frontmatter(skill_md)
            if fields.get("name") != name:
                raise ValueError(f"frontmatter name mismatch: {skill_md}")
            description = fields.get("description") or ""
            if not description.strip():
                raise ValueError(f"empty description: {skill_md}")
            references_dir = entry / "references"
            references = []
            if references_dir.is_dir():
                references = sorted(
                    p.relative_to(root).as_posix()
                    for p in references_dir.rglob("*")
                    if p.is_file()
                )
            records.append(
                {
                    "harness": harness,
                    "name": name,
                    "skill_path": skill_md.relative_to(root).as_posix(),
                    "description": description,
                    "body": body,
                    "references": references,
                }
            )
    records.sort(key=lambda r: (r["harness"], r["name"]))
    return records


def _fence_flags(lines):
    """Return one bool per line: True iff that line is a fence delimiter or lies
    inside a fenced code block (and so must be left untouched by heading/link
    transforms). Shared by demote_headings and rewrite_links.

    A line whose stripped form starts with a run of 3+ backticks or 3+ tildes
    opens a fence, recording BOTH the fence character and the length of that
    opening run. Per CommonMark, the fence closes only on a later line whose
    stripped form starts with a run of the SAME character that is AT LEAST AS
    LONG as the opening run — a longer or equal-length run of the same
    character closes it; a shorter run of the same character (e.g. a nested
    3-backtick line inside a 4-backtick-opened fence), or any run of the other
    character, does not.
    """
    flags = []
    fence_char = None
    fence_len = 0
    for line in lines:
        stripped = line.strip()
        if fence_char is None:
            char = stripped[:1]
            if char in ("`", "~"):
                run_len = len(stripped) - len(stripped.lstrip(char))
                if run_len >= 3:
                    fence_char = char
                    fence_len = run_len
                    flags.append(True)
                    continue
            flags.append(False)
        else:
            flags.append(True)
            char = stripped[:1]
            if char == fence_char:
                run_len = len(stripped) - len(stripped.lstrip(char))
                if run_len >= fence_len:
                    fence_char = None
                    fence_len = 0
    return flags


_HEADING_RE = re.compile(r"^(#{1,6})(?=\s|$)(.*)$")


def demote_headings(text):
    """Give every ATX heading line outside fenced code blocks one more '#'
    (capped at 6). Fence-aware via _fence_flags."""
    lines = text.splitlines(keepends=True)
    flags = _fence_flags(lines)
    out = []
    for line, in_fence in zip(lines, flags):
        if in_fence:
            out.append(line)
            continue
        newline = ""
        content = line
        if content.endswith("\r\n"):
            newline = "\r\n"
            content = content[:-2]
        elif content.endswith("\n"):
            newline = "\n"
            content = content[:-1]
        match = _HEADING_RE.match(content)
        if match:
            hashes, rest = match.group(1), match.group(2)
            content = ("#" * min(len(hashes) + 1, 6)) + rest
        out.append(content + newline)
    return "".join(out)


def _resolve_repo_relative(source_dir, path_part):
    """Resolve path_part against source_dir (a repo-relative POSIX dir), collapsing
    '.' and '..'. Returns the resolved repo-relative POSIX string, or None if the
    target escapes the repo root."""
    if path_part.startswith("/"):
        raw_parts = [p for p in path_part.split("/") if p]
    else:
        raw_parts = list(PurePosixPath(source_dir).parts) + path_part.split("/")
    parts = []
    for part in raw_parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _rewrite_target(target, source_dir, blob_base, page_map):
    if target.startswith("http://") or target.startswith("https://") or target.startswith("mailto:"):
        return target
    if target.startswith("#"):
        return target
    if "#" in target:
        path_part, frag = target.split("#", 1)
        frag = "#" + frag
    else:
        path_part, frag = target, ""
    if not path_part:
        return target
    resolved = _resolve_repo_relative(source_dir, path_part)
    if resolved is None:
        return target
    if resolved in page_map:
        return page_map[resolved] + frag
    return blob_base + resolved + frag


_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
_TARGET_RE = re.compile(r"^(\s*)(\S+)(.*)$", re.DOTALL)


def _rewrite_link_match(match, source_dir, blob_base, page_map, self_path=None):
    text_part, inner = match.group(1), match.group(2)
    target_match = _TARGET_RE.match(inner)
    if target_match is None:
        return match.group(0)
    leading, target, trailing = target_match.groups()
    wrapped = len(target) >= 2 and target.startswith("<") and target.endswith(">")
    raw_target = target[1:-1] if wrapped else target
    new_raw = _rewrite_target(raw_target, source_dir, blob_base, page_map)
    if self_path is not None and new_raw.split("#", 1)[0] == self_path:
        # F3: a page must never link to itself -- e.g. an .html companion
        # target that rewrites onto the very mirror page being rendered.
        # Drop the link syntax entirely and keep just its visible text.
        return text_part
    new_target = f"<{new_raw}>" if wrapped else new_raw
    return f"[{text_part}]({leading}{new_target}{trailing})"


def rewrite_links(text, source_dir, blob_base, page_map, self_path=None):
    """Rewrite every INLINE markdown link target outside fenced code blocks.

    Absolute http(s):// and mailto: targets, and pure-anchor (#...) targets, are
    left untouched. Otherwise the target (minus any #fragment, which is preserved
    on the rewritten URL) is resolved against source_dir (a repo-relative POSIX
    dir): if the resolved repo-relative path is a key in page_map it is rewritten
    to that value; else if it resolves inside the repo it is rewritten to
    blob_base + resolved_path; if it escapes the repo root it is left unchanged.

    `self_path`, when given, is the rewritten (post-page_map, pre-fragment)
    form that represents the page currently being rendered — any link whose
    rewritten target (ignoring any #fragment) equals it is a self-reference
    and is neutralized: the link syntax is dropped and only its visible text
    survives (F3 — "a page must never link to itself"). Two DIFFERENT links on
    a page resolving to the SAME other page is unaffected and stays linked.

    Reference-style links ([text][label]) are deliberately NOT rewritten — only
    inline [text](target) links are matched.
    """
    lines = text.splitlines(keepends=True)
    flags = _fence_flags(lines)
    out = []
    for line, in_fence in zip(lines, flags):
        if in_fence:
            out.append(line)
            continue
        out.append(
            _LINK_RE.sub(
                lambda m: _rewrite_link_match(m, source_dir, blob_base, page_map, self_path),
                line,
            )
        )
    return "".join(out)


# ---------------------------------------------------------------------------
# Page renderers (T4): pure functions over records/fragments/page_map handed in
# by the caller. The build/check CLI that reads sources and writes files lands
# in T5 — nothing here touches the filesystem except load_fragment, which is
# explicitly the fragment loader, not a renderer.
# ---------------------------------------------------------------------------

# Harness labels, used verbatim in every generated page's h1 and in the parity
# matrix's column headers. Order matters for the parity table's column order.
_HARNESS_LABELS = {
    "claude": "Claude Code",
    "copilot": "GitHub Copilot CLI",
    "codex": "OpenAI Codex CLI",
}


def _escape_generator_text(text):
    """Escape '<' and '>' as HTML entities in generator-EMITTED prose (never
    source content): raw text like 'tasks/kits/<slug>/', copied verbatim from a
    skill's frontmatter description into a blockquote or a table cell the
    generator itself composes, would otherwise be parsed as literal (and
    silently browser-swallowed) inline HTML by a markdown renderer -- e.g.
    'tasks/kits/<slug>/' rendering as 'tasks/kits//'. Never applied to an
    embedded skill-card BODY, which is source content the generator transforms
    but does not compose."""
    return text.replace("<", "&lt;").replace(">", "&gt;")


def _provenance_comment(source):
    """One-line HTML comment naming `source` as the generated page's origin, plus
    the exact rebuild command — identical template across all three page kinds."""
    return (
        f"<!-- GENERATED by bin/docs_build.py from {source} — do not edit; "
        "edit the source and run: python3 bin/docs_build.py build -->"
    )


def _strip_leading_h1(text):
    """Remove ONE leading top-level (#) heading line from text, if the first
    non-blank line is an h1 (any leading blank lines are dropped along with it).
    30/39 SKILL.md bodies open with an h1; embedding that body verbatim under
    demote_headings would turn it into a stray h2 — a sibling of the page's own
    '## The skill card' heading, escaping that section. Bodies with no leading h1
    are returned unchanged. Not fence-aware by design: only the first non-blank
    LINE is ever inspected, and a fence-opening line never matches the heading
    pattern (fences start with a backtick/tilde, not '#')."""
    lines = text.splitlines(keepends=True)
    idx = 0
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    if idx >= len(lines):
        return text
    content = lines[idx].rstrip("\r\n")
    match = _HEADING_RE.match(content)
    if match and len(match.group(1)) == 1:
        return "".join(lines[idx + 1 :])
    return text


def _sibling_records(record, inventory):
    """Records for the same skill `name` in the OTHER two harnesses, sorted by
    harness name — used to build a page's 'Also available on' links."""
    name = record["name"]
    harness = record["harness"]
    return sorted(
        (r for r in inventory if r["name"] == name and r["harness"] != harness),
        key=lambda r: r["harness"],
    )


def _facts_block(record, inventory):
    """The facts list shared by every skill page: source link, sibling links (or
    a harness-only note pointing at the parity matrix), and — ONLY when the
    skill ships any — a references line. 33/39 skills ship no references/ dir
    at all; a 'none' line there reads as a deficit, so the whole line is
    omitted rather than shown empty. When references DO exist, each is labeled
    with its path relative to the skill's own directory (e.g.
    'references/roles/scout.md', not a bare 'scout.md') so a skill with many
    references (e.g. claude/architect's seven role files) reads as a catalog,
    not a flat list of same-looking filenames. Still plain blob links only —
    never described as reading material, since some (e.g.
    skills/route/references/pricing.json) are generated mirrors, not prose."""
    skill_path = record["skill_path"]
    skill_dir = PurePosixPath(skill_path).parent.as_posix()
    siblings = _sibling_records(record, inventory)
    if siblings:
        also_available = ", ".join(
            f"[{_HARNESS_LABELS[r['harness']]}](../{r['harness']}/{r['name']}.md)"
            for r in siblings
        )
    else:
        also_available = "this harness only — see the [parity matrix](../index.md)"

    lines = [
        f"- **Source:** [{skill_path}]({GITHUB_BLOB_BASE}{skill_path})",
        f"- **Also available on:** {also_available}",
    ]

    references = record["references"]
    if references:
        shipped = ", ".join(
            f"[{posixpath.relpath(ref, start=skill_dir)}]({GITHUB_BLOB_BASE}{ref})"
            for ref in references
        )
        lines.append(f"- **References shipped with the skill:** {shipped}")

    return "\n".join(lines)


def _relativize_page_map(page_map, from_dir):
    """Return `page_map` with every value rewritten from a CANONICAL, docs_dir-
    relative site path (e.g. 'deep-dives/how-it-works.md') to a path RELATIVE
    to `from_dir` (the docs_dir-relative directory the rendering page itself
    will live in, e.g. 'skills/claude' or 'deep-dives') — e.g. from
    'skills/claude' to 'deep-dives/how-it-works.md' becomes
    '../../deep-dives/how-it-works.md'; from 'deep-dives' to the same target
    becomes 'how-it-works.md'. Implemented once here; every renderer that
    embeds cross-doc links (render_skill_page, render_deep_dive_page) calls
    this itself against its own site_dir — callers of those renderers always
    pass the canonical map, never a pre-relativized one."""
    return {
        source_path: posixpath.relpath(canonical, start=from_dir)
        for source_path, canonical in page_map.items()
    }


def render_skill_page(record, fragment_text, inventory, page_map):
    """Render one generated per-skill reference page (str). Pure: `record` is one
    skill_inventory() entry, `fragment_text` is its already-loaded 'In practice'
    fragment (or None), `inventory` is the full roster (for sibling lookups), and
    `page_map` is the CANONICAL deep-dive link-rewrite map (deep_dive_page_map()'s
    return value, docs_dir-relative, e.g. 'deep-dives/how-it-works.md'; {} is also
    valid — every relative link then falls back to a GITHUB_BLOB_BASE URL). This
    function relativizes page_map itself (via _relativize_page_map, against this
    page's own site directory 'skills/<harness>') before handing it to
    rewrite_links — callers never pre-relativize.

    Element order (pinned by TASKS.md T4 / PLAN.md D5): h1, provenance comment,
    description blockquote, facts block, optional '## In practice' + fragment,
    then '## The skill card — what the model reads' + a note about the
    install-time path variables + the body (leading h1 stripped, headings
    demoted, links rewritten)."""
    harness = record["harness"]
    name = record["name"]
    label = _HARNESS_LABELS[harness]
    skill_path = record["skill_path"]

    blocks = [
        f"# {name} — {label}",
        _provenance_comment(skill_path),
        f"> {_escape_generator_text(record['description'].strip())}",
        _facts_block(record, inventory),
    ]

    if fragment_text is not None:
        blocks.append("## In practice")
        blocks.append(fragment_text.strip("\n"))

    blocks.append("## The skill card — what the model reads")
    blocks.append(
        "This is the SKILL.md body the model reads, transformed for this page: "
        "the source's own leading title, if it had one, is removed; every "
        "remaining heading is demoted one level to nest under this section; "
        "and relative links are rewritten to site or GitHub URLs. "
        "`${CLAUDE_PLUGIN_ROOT}` and `{{POLYTROPOS_ROOT}}` are install-time "
        "path variables, left intact exactly as the model sees them. The "
        f"unmodified original is [{skill_path}]({GITHUB_BLOB_BASE}{skill_path})."
    )
    source_dir = PurePosixPath(skill_path).parent.as_posix()
    site_dir = f"skills/{harness}"
    transformed_body = rewrite_links(
        demote_headings(_strip_leading_h1(record["body"])),
        source_dir,
        GITHUB_BLOB_BASE,
        _relativize_page_map(page_map, site_dir),
    )
    blocks.append(transformed_body.strip("\n"))

    return "\n\n".join(blocks) + "\n"


def render_harness_index(harness, inventory, fragment_text):
    """Render one harness's index page (str): h1, provenance comment (source = the
    harness's skills root), a `skill | description | page link` table sorted by
    name, then an optional '## Using these skills' + fragment. `inventory` may be
    the full cross-harness roster or one already filtered to `harness` — this
    function filters to `harness` itself either way."""
    label = _HARNESS_LABELS[harness]
    source = "/".join(_HARNESS_SKILL_ROOTS[harness])
    records = sorted(
        (r for r in inventory if r["harness"] == harness), key=lambda r: r["name"]
    )

    table_lines = ["| Skill | Description | Page |", "| --- | --- | --- |"]
    for r in records:
        table_lines.append(
            f"| {r['name']} | {_escape_generator_text(r['description'].strip())} | "
            f"[{r['name']}]({r['name']}.md) |"
        )

    blocks = [
        f"# {label}",
        _provenance_comment(source),
        "\n".join(table_lines),
    ]

    if fragment_text is not None:
        blocks.append("## Using these skills")
        blocks.append(fragment_text.strip("\n"))

    return "\n\n".join(blocks) + "\n"


def render_parity_page(inventory, fragment_text):
    """Render the cross-harness parity matrix page (str): h1, provenance comment,
    a matrix table (one row per name in the sorted union of all skill names,
    columns Claude Code / GitHub Copilot CLI / OpenAI Codex CLI, each cell a
    relative page link or '—'), then an optional '## Why the rosters differ' +
    fragment. The name set is always derived from `inventory` — never hardcoded."""
    names = sorted({r["name"] for r in inventory})
    by_name_harness = {(r["name"], r["harness"]): r for r in inventory}
    harness_order = tuple(_HARNESS_SKILL_ROOTS)  # claude, copilot, codex

    header = "| Skill | " + " | ".join(_HARNESS_LABELS[h] for h in harness_order) + " |"
    sep = "| --- | " + " | ".join("---" for _ in harness_order) + " |"
    table_lines = [header, sep]
    for name in names:
        cells = [name]
        for h in harness_order:
            if (name, h) in by_name_harness:
                cells.append(f"[{name}]({h}/{name}.md)")
            else:
                cells.append("—")
        table_lines.append("| " + " | ".join(cells) + " |")

    source = "the skills/, copilot/.github/skills/, and codex/skills/ rosters"
    blocks = [
        "# Skills across the three harnesses",
        _provenance_comment(source),
        "\n".join(table_lines),
    ]

    if fragment_text is not None:
        blocks.append("## Why the rosters differ")
        blocks.append(fragment_text.strip("\n"))

    return "\n\n".join(blocks) + "\n"


# ---------------------------------------------------------------------------
# Deep-dive mirrors (T6): docs/*.md -> docs-site/deep-dives/*.md.
# ---------------------------------------------------------------------------

# docs/*.html companions that are NOT mirrored (PLAN.md D6) but whose sibling
# .md file IS — a link to one of these from a mirrored .md source must still
# resolve, to the SAME mirror page as its .md counterpart.
_UNMIRRORED_HTML_TARGETS = {
    "docs/guide.html": "deep-dives/guide.md",
    "docs/how-it-works.html": "deep-dives/how-it-works.md",
}


def _extract_title(text, fallback):
    """Return the text of the first ATX h1 line ('# ...') found outside a
    fenced code block in `text`, with the leading '#' and surrounding
    whitespace stripped. Returns `fallback` (e.g. a filename) if no h1 line is
    found anywhere in the text."""
    lines = text.splitlines(keepends=True)
    flags = _fence_flags(lines)
    for line, in_fence in zip(lines, flags):
        if in_fence:
            continue
        content = line.rstrip("\r\n")
        match = _HEADING_RE.match(content)
        if match and len(match.group(1)) == 1:
            return match.group(2).strip()
    return fallback


def _split_leading_h1(text):
    """Split text into (h1_line, remainder): h1_line is the exact text (no
    trailing newline) of the first ATX h1 line found OUTSIDE a fenced code
    block — fence-aware via the same _fence_flags machinery _extract_title
    uses, so a '# ...'-shaped line INSIDE a fence (a decoy, or any leading
    fenced content) is never mistaken for the real title; remainder is
    everything after that line. Any text before the found h1 (leading blank
    lines, or — only in a synthetic/adversarial case — a fenced block
    preceding it) is dropped, same as _strip_leading_h1's own convention.
    Returns (None, text) unchanged if no h1 line exists outside any fence
    anywhere in the text. Used by render_deep_dive_page (F4) to move the
    'Mirrored from ...' note below the source's own h1 rather than above it."""
    lines = text.splitlines(keepends=True)
    flags = _fence_flags(lines)
    for i, (line, in_fence) in enumerate(zip(lines, flags)):
        if in_fence:
            continue
        content = line.rstrip("\r\n")
        match = _HEADING_RE.match(content)
        if match and len(match.group(1)) == 1:
            return content, "".join(lines[i + 1 :])
    return None, text


def deep_dive_slug(md_filename):
    """The deep-dive slug for a docs/*.md filename (e.g. 'COPILOT-HARNESS.md' ->
    'copilot-harness'): the lowercased filename stem."""
    return PurePosixPath(md_filename).stem.lower()


def deep_dive_page_map(repo_root=REPO_ROOT):
    """The CANONICAL (docs_dir-relative, NOT relativized to any one page)
    deep-dive link-rewrite map: every 'docs/<NAME>.md' -> 'deep-dives/<slug>.md'
    (slug = deep_dive_slug), derived from an actual docs/*.md glob — never a
    hardcoded list, so a future doc auto-joins — plus the two .html companions
    that are not themselves mirrored but must still resolve to their .md
    sibling's mirror page (PLAN.md D6). This is the single map both
    render_skill_page and render_deep_dive_page relativize (via
    _relativize_page_map) against their own site directory."""
    root = Path(repo_root)
    mapping = {}
    for md_path in sorted((root / "docs").glob("*.md")):
        mapping[f"docs/{md_path.name}"] = f"deep-dives/{deep_dive_slug(md_path.name)}.md"
    mapping.update(_UNMIRRORED_HTML_TARGETS)
    return mapping


def render_deep_dive_page(source_rel_path, source_text, page_map):
    """Render one docs/*.md deep-dive mirror page (str). Pure: `source_rel_path`
    is the repo-relative POSIX path of the source (e.g. 'docs/GUIDE.md'),
    `source_text` is that file's raw text (read by the caller — this function
    does no I/O), and `page_map` is the CANONICAL deep_dive_page_map() (this
    function relativizes it itself, against 'deep-dives', before calling
    rewrite_links — the caller never pre-relativizes). Headings are NOT
    demoted: every docs/*.md source already carries exactly one h1, which
    stays exactly where it is and remains this page's h1.

    Element order: provenance comment, the source's own h1 (if it has one),
    a 'Mirrored from ...' note rendered as an admonition BELOW that h1, then
    the rest of the source body with only its links rewritten. A source with
    no leading h1 falls back to the note appearing first, as before.

    F3: any link whose rewritten target resolves to THIS very page (e.g. its
    own .html companion) is neutralized — the link is dropped and only its
    visible text survives — via rewrite_links' self_path parameter."""
    slug = deep_dive_slug(PurePosixPath(source_rel_path).name)
    self_canonical = f"deep-dives/{slug}.md"
    relative_page_map = _relativize_page_map(page_map, "deep-dives")
    self_path = posixpath.relpath(self_canonical, start="deep-dives")

    transformed = rewrite_links(
        source_text, "docs", GITHUB_BLOB_BASE, relative_page_map, self_path=self_path
    )
    note = (
        f"Mirrored from `{source_rel_path}` — edit the source, then run "
        "`python3 bin/docs_build.py build`."
    )
    admonition = "!!! note\n    " + note

    h1_line, rest = _split_leading_h1(transformed)
    blocks = [_provenance_comment(source_rel_path)]
    if h1_line is not None:
        blocks.append(h1_line)
        blocks.append(admonition)
        blocks.append(rest.strip("\n"))
    else:
        blocks.append(admonition)
        blocks.append(transformed.strip("\n"))

    return "\n\n".join(blocks) + "\n"


def render_deep_dive_index(entries):
    """Render docs-site/deep-dives/index.md (str): h1, provenance comment, a
    single-column table whose cell text is the title and whose link target is
    the page (no separate, duplicate 'Title' text column). `entries` is a
    list of (slug, title) pairs, already sorted by slug by the caller
    (expected_pages) — each row links to '<slug>.md' (same directory)."""
    table_lines = ["| Deep dive |", "| --- |"]
    for slug, title in entries:
        table_lines.append(f"| [{title}]({slug}.md) |")

    blocks = [
        "# Deep dives",
        _provenance_comment("docs/*.md"),
        "\n".join(table_lines),
    ]
    return "\n\n".join(blocks) + "\n"


# ---------------------------------------------------------------------------
# Fragments: location constants, validation, loading, orphan detection.
# ---------------------------------------------------------------------------

FRAGMENTS_ROOT = "docs-src/fragments"


def skill_fragment_rel_path(harness, name):
    """Repo-relative POSIX path of a per-skill 'In practice' fragment."""
    return f"{FRAGMENTS_ROOT}/skills/{harness}/{name}.md"


def harness_index_fragment_rel_path(harness):
    """Repo-relative POSIX path of a per-harness index 'Using these skills'
    fragment."""
    return f"{FRAGMENTS_ROOT}/skills/{harness}/index.md"


PARITY_FRAGMENT_REL_PATH = f"{FRAGMENTS_ROOT}/parity.md"


_SETEXT_UNDERLINE_RE = re.compile(r"^(=+|-+)\s*$")


def validate_fragment(text, rel_path):
    """Raise ValueError naming rel_path if any line outside a fenced code block
    is a reserved h1/h2 heading, in EITHER heading syntax CommonMark supports:

    - ATX: '#'/'##' (per CommonMark's required trailing space-or-end-of-line).
    - Setext: a non-blank paragraph line immediately followed (no blank line
      between, both outside any fence) by an underline of only '=' characters
      (h1) or only '-' characters (h2) — setext syntax can ONLY ever produce
      an h1 or h2, so any match is automatically a reserved-heading violation
      here; there is no setext h3+ to allow. A bare '---'/'===' preceded by a
      BLANK line is a thematic break/list content, not a heading, and is left
      alone.

    Fragments are always spliced under a page-owned h1 and h2, so they may
    only use ATX h3+. A heading-looking line INSIDE a fence is fine (a worked
    example may legitimately show markdown source containing headings)."""
    lines = text.splitlines(keepends=True)
    flags = _fence_flags(lines)
    for i, (line, in_fence) in enumerate(zip(lines, flags)):
        if in_fence:
            continue
        content = line.rstrip("\r\n")
        match = _HEADING_RE.match(content)
        if match and len(match.group(1)) <= 2:
            raise ValueError(
                f"fragment {rel_path} uses a reserved h1/h2 heading (the page "
                f"owns h1/h2; fragments use h3+ only): {content!r}"
            )
        if i > 0 and not flags[i - 1]:
            prev_content = lines[i - 1].rstrip("\r\n")
            if prev_content.strip() and _SETEXT_UNDERLINE_RE.match(content.strip()):
                raise ValueError(
                    f"fragment {rel_path} uses a reserved setext h1/h2 heading "
                    f"(the page owns h1/h2; fragments use ATX h3+ only): "
                    f"{prev_content!r} / {content!r}"
                )


def load_fragment(repo_root, rel_path):
    """Return the text of repo_root/rel_path (UTF-8), or None if the file does not
    exist. Validates the fragment (see validate_fragment) before returning it, so
    every caller gets an already-checked fragment or a raised ValueError — never a
    silently-invalid one."""
    path = Path(repo_root) / rel_path
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    validate_fragment(text, rel_path)
    return text


def check_fragment_orphans(repo_root, inventory):
    """Raise ValueError naming any file under docs-src/fragments/skills/ whose
    <harness>/<name> matches no inventory record (an index.md fragment's
    <harness> must be one of the three known harness keys) — catches a typo'd
    skill or harness name in a fragment path rather than silently never splicing
    it into any page. No-op if the fragments/skills/ directory does not exist."""
    skills_fragments_root = Path(repo_root) / FRAGMENTS_ROOT / "skills"
    if not skills_fragments_root.is_dir():
        return
    valid_names = {(r["harness"], r["name"]) for r in inventory}
    known_harnesses = set(_HARNESS_SKILL_ROOTS)
    for path in sorted(skills_fragments_root.rglob("*.md")):
        rel = path.relative_to(Path(repo_root)).as_posix()
        parts = PurePosixPath(rel).parts
        # docs-src/fragments/skills/<harness>/<name-or-index>.md
        if len(parts) != 5:
            raise ValueError(f"unexpected fragment path shape: {rel}")
        harness = parts[3]
        stem = PurePosixPath(parts[4]).stem
        if stem == "index":
            if harness not in known_harnesses:
                raise ValueError(f"orphan fragment (unknown harness): {rel}")
            continue
        if (harness, stem) not in valid_names:
            raise ValueError(f"orphan fragment (no matching skill): {rel}")


# ---------------------------------------------------------------------------
# build/check CLI (T5): the only layer that touches the filesystem for real.
# ---------------------------------------------------------------------------

# Roots the generator owns outright: every file under them must be one this
# module produced. docs-site/deep-dives/ does not exist until T6 lands (its
# entry here is forward-declared and simply has nothing to scan until then —
# `check_site` skips any root that is not yet a directory).
_GENERATOR_OWNED_ROOTS = ("docs-site/skills", "docs-site/deep-dives")

REBUILD_REMEDY = "python3 bin/docs_build.py build"


def _normalize_bytes(text):
    """Encode `text` as UTF-8 with LF line endings and exactly one trailing
    newline — the byte-stability contract every generated page must meet."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return (normalized.rstrip("\n") + "\n").encode("utf-8")


def expected_pages(repo_root=REPO_ROOT):
    """Return every page this repo's docs-site/skills/ and docs-site/deep-dives/
    trees should contain, as a dict mapping repo-relative POSIX path (e.g.
    'docs-site/skills/claude/route.md', 'docs-site/deep-dives/guide.md') to its
    expected UTF-8 bytes. The single source of truth for both `build` and
    `check`: derives the inventory, validates+loads every fragment (raising
    ValueError on a malformed skill/fragment or an orphan fragment path — never
    silently skipped), builds the canonical deep_dive_page_map(), and renders
    every page (each renderer relativizes that map itself, against its own
    site directory)."""
    root = Path(repo_root)
    inventory = skill_inventory(root)
    check_fragment_orphans(root, inventory)
    page_map = deep_dive_page_map(root)

    pages = {}

    for record in inventory:
        harness, name = record["harness"], record["name"]
        fragment_text = load_fragment(root, skill_fragment_rel_path(harness, name))
        text = render_skill_page(record, fragment_text, inventory, page_map)
        pages[f"docs-site/skills/{harness}/{name}.md"] = _normalize_bytes(text)

    for harness in _HARNESS_SKILL_ROOTS:
        fragment_text = load_fragment(root, harness_index_fragment_rel_path(harness))
        text = render_harness_index(harness, inventory, fragment_text)
        pages[f"docs-site/skills/{harness}/index.md"] = _normalize_bytes(text)

    parity_fragment = load_fragment(root, PARITY_FRAGMENT_REL_PATH)
    parity_text = render_parity_page(inventory, parity_fragment)
    pages["docs-site/skills/index.md"] = _normalize_bytes(parity_text)

    index_entries = []
    for md_path in sorted((root / "docs").glob("*.md")):
        source_rel_path = f"docs/{md_path.name}"
        source_text = md_path.read_text(encoding="utf-8")
        slug = deep_dive_slug(md_path.name)
        title = _extract_title(source_text, fallback=md_path.name)
        index_entries.append((slug, title))
        mirror_text = render_deep_dive_page(source_rel_path, source_text, page_map)
        pages[f"docs-site/deep-dives/{slug}.md"] = _normalize_bytes(mirror_text)

    index_entries.sort(key=lambda entry: entry[0])
    index_text = render_deep_dive_index(index_entries)
    pages["docs-site/deep-dives/index.md"] = _normalize_bytes(index_text)

    return pages


def build_site(repo_root=REPO_ROOT):
    """Write every expected_pages() entry to disk (mkdir -p as needed). Returns
    (written, unchanged) counts — 'written' covers both newly-created files and
    ones whose bytes differed from what is already committed."""
    root = Path(repo_root)
    pages = expected_pages(root)
    written = 0
    unchanged = 0
    for rel_path, payload in sorted(pages.items()):
        path = root / rel_path
        if path.is_file() and path.read_bytes() == payload:
            unchanged += 1
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        written += 1
    return written, unchanged


def check_site(repo_root=REPO_ROOT):
    """Return (stale, unknown) sorted repo-relative-path lists: `stale` is every
    expected page that is missing or byte-differs from what expected_pages()
    says it should be; `unknown` is every file under a generator-owned root
    (docs-site/skills/, docs-site/deep-dives/) that is NOT a key of
    expected_pages() — i.e. drift the generator does not know about."""
    root = Path(repo_root)
    pages = expected_pages(root)
    stale = [
        rel_path
        for rel_path, payload in pages.items()
        if not (root / rel_path).is_file() or (root / rel_path).read_bytes() != payload
    ]

    expected_set = set(pages)
    unknown = []
    for owned_root in _GENERATOR_OWNED_ROOTS:
        owned_dir = root / owned_root
        if not owned_dir.is_dir():
            continue
        for path in owned_dir.rglob("*"):
            if path.is_file():
                rel = path.relative_to(root).as_posix()
                if rel not in expected_set:
                    unknown.append(rel)

    return sorted(stale), sorted(unknown)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "check"))
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.mode == "build":
            written, unchanged = build_site(args.repo_root)
            print(f"written {written} / unchanged {unchanged}")
            return 0
        stale, unknown = check_site(args.repo_root)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if stale or unknown:
        if stale:
            print("stale (missing or differing): " + ", ".join(stale), file=sys.stderr)
        if unknown:
            print(
                "unknown (present but not generator-expected): " + ", ".join(unknown),
                file=sys.stderr,
            )
        print(f"remedy: {REBUILD_REMEDY}", file=sys.stderr)
        return 1
    print("docs-site pages are up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
