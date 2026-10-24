"""Render the docs/sdd/ Markdown documents to their printable HTML forms.

    python3 docs/sdd/render.py build    # rewrite every report's .html from its .md
    python3 docs/sdd/render.py check    # exit 1 if any .html differs from a fresh render

The Markdown is the source; the .html beside it is generated and never hand-edited
(tests/test_sdd_docs.py fails on drift). The page style is taken from the printable deck,
docs/spec-driven-pitch.html, so the reports print and theme the same way. The deck itself is
hand-written HTML and is not rendered here; docs/sdd/spec-driven-pitch.md is its Markdown twin.

Only the Markdown subset the reports use is supported: # to ### headings, paragraphs, - and 1.
lists with indented continuation lines, pipe tables, ``` fences, > quotes, ---, inline
`code`/**bold**/*italic*/[links](url), and a `<!-- page -->` line that starts a new printed page.
Stdlib only; reads and writes only files under docs/.
"""
import html
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent
DECK = DOCS / "spec-driven-pitch.html"
# Each report: (markdown source, the kicker line printed above its title).
REPORTS = {
    "guide.md": "a guide",
    "core-four.md": "a mapping",
}
PAGE = "<!-- page -->"
BLOCK_START = re.compile(r"(#{1,3} |\||```|- |\d+\. |---|> |" + re.escape(PAGE) + ")")
LIST_ITEM = re.compile(r"(- |\d+\. )")
EXTRA_STYLE = (
    "  table.grid td:first-child { white-space: normal; }\n"
    "  .src { font-size: .85em; color: var(--muted); }\n"
    "  blockquote { margin: 1rem 0; padding: .6rem 1rem; border-left: 4px solid var(--line);"
    " color: var(--muted); }\n"
    "  blockquote p { margin: .3rem 0; }\n"
)


def deck_style():
    text = DECK.read_text(encoding="utf-8")
    start, end = text.index("<style>"), text.index("</style>")
    return text[start:end] + EXTRA_STYLE + "</style>"


def inline(s):
    s = html.escape(s, quote=False)
    codes = []

    def stash(m):
        codes.append("<code>" + m.group(1) + "</code>")
        return f"\x00{len(codes) - 1}\x00"

    s = re.sub(r"`([^`]+)`", stash, s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![*\w])\*([^*]+?)\*(?!\*)", r"<em>\1</em>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], s)
    return s.replace("—", "&mdash;").replace("·", "&middot;").replace("→", "&rarr;")


def render(md, kicker):
    lines = md.split("\n")
    body = []
    i = 0
    title = None
    after_title = False
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.strip() == PAGE:
            body.append('</section>\n\n<section class="page">')
            i += 1
            continue
        m = re.match(r"(#{1,3}) (.+)$", line)
        if m:
            level = len(m.group(1))
            if level == 1:
                title = m.group(2).strip()
                body.append(f'<p class="kicker"><b>polytropos</b> &middot; spec-driven development'
                            f' &middot; {kicker}</p>\n<h1>{inline(title)}</h1>')
                after_title = True
            else:
                body.append(f"<h{level}>{inline(m.group(2).strip())}</h{level}>")
            i += 1
            continue
        if line.startswith("---"):
            i += 1
            continue
        if line.startswith("```"):
            j = i + 1
            buf = []
            while not lines[j].startswith("```"):
                buf.append(html.escape(lines[j], quote=False))
                j += 1
            code = re.sub(r"(#[^\n]*)", r'<span class="dim">\1</span>', "\n".join(buf))
            body.append(f"<pre><code>{code}</code></pre>")
            i = j + 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            head = "".join(f"<th>{inline(c)}</th>" for c in rows[0])
            rest = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>"
                           for r in rows[2:])
            body.append(f'<table class="grid"><thead><tr>{head}</tr></thead>'
                        f"<tbody>{rest}</tbody></table>")
            continue
        if line.startswith("> "):
            paras = [[]]
            while i < len(lines) and lines[i].startswith(">"):
                text = lines[i][1:].strip()
                if text:
                    paras[-1].append(text)
                else:
                    paras.append([])
                i += 1
            inner = "".join(f"<p>{inline(' '.join(p))}</p>" for p in paras if p)
            body.append(f"<blockquote>{inner}</blockquote>")
            continue
        if LIST_ITEM.match(line):
            tag = "ul" if line.startswith("- ") else "ol"
            items = []
            while i < len(lines) and lines[i].strip() and (
                    LIST_ITEM.match(lines[i]) or lines[i].startswith("  ")):
                if LIST_ITEM.match(lines[i]):
                    items.append(LIST_ITEM.sub("", lines[i], count=1).strip())
                else:
                    items[-1] += " " + lines[i].strip()
                i += 1
            body.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
            continue
        buf = []
        while i < len(lines) and lines[i].strip() and not BLOCK_START.match(lines[i]):
            buf.append(lines[i].strip())
            i += 1
        text = " ".join(buf)
        if after_title:
            body.append(f'<p class="sub">{inline(text)}</p>')
        elif text.startswith("Long form for polytropos:"):
            body.append(f"<footer>{inline(text)}</footer>")
        elif text.startswith("Sources for") or text.startswith("On "):
            body.append(f'<p class="src">{inline(text)}</p>')
        else:
            body.append(f"<p>{inline(text)}</p>")
        after_title = False
    if title is None:
        raise ValueError("report has no # title")
    plain_title = html.escape(re.sub(r"[*`]", "", title), quote=False)
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"UTF-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
        f"<title>{plain_title}</title>\n{deck_style()}\n</head>\n<body>\n<main class=\"wrap\">\n\n"
        "<!-- Generated from the .md beside this file by docs/sdd/render.py; edit the .md. -->\n"
        "<section class=\"page\">\n" + "\n".join(body) + "\n</section>\n\n</main>\n</body>\n</html>\n"
    )


def rendered():
    """{html path: fresh render} for every report."""
    out = {}
    for name, kicker in REPORTS.items():
        md_path = HERE / name
        out[md_path.with_suffix(".html")] = render(md_path.read_text(encoding="utf-8"), kicker)
    return out


def main(argv):
    if len(argv) != 1 or argv[0] not in ("build", "check"):
        print(__doc__.strip().splitlines()[0])
        print("usage: python3 docs/sdd/render.py build|check")
        return 2
    stale = []
    for path, text in rendered().items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current != text:
            if argv[0] == "build":
                path.write_text(text, encoding="utf-8")
                print(f"wrote {path.relative_to(DOCS.parent)}")
            else:
                stale.append(path.relative_to(DOCS.parent))
    if stale:
        for p in stale:
            print(f"stale: {p} (run python3 docs/sdd/render.py build)")
        return 1
    if argv[0] == "check":
        print("docs/sdd: every report's HTML matches its Markdown")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
