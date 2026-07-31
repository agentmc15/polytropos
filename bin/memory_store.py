#!/usr/bin/env python3
"""memory-skill durable fact store CLI (schema_version 1).

The store is GITIGNORED USER DATA: one markdown file per fact under
``<memory-dir>/facts/<slug>.md`` (flat ``key: value`` frontmatter between ``---`` fences, then a
free-text markdown body) plus a fully DERIVED ``<memory-dir>/index.md`` regenerated on every
mutation. Fact files are the only source of truth; the index is disposable.

The ONLY writes this tool ever performs are under ``--memory-dir`` (default
``PLUGIN_ROOT / "memory"``, exactly how ``journal/`` works) — ``add``/``update``/``remove``
mutate fact files and regenerate the index; nothing else on disk is ever touched. This file
resolves no per-user home directory anywhere (the memory feature has no legitimate need to read
one) and spawns no child process of any kind (that one sanctioned exception lives only in this
kit's test file, as a self-invocation smoke). This tool prices NOTHING: no pricing file is read,
imported, or edited, and no price or model id appears anywhere below.

There is no YAML library in the stdlib, so frontmatter is parsed by a deliberately trivial
~15-line grammar: each line between the ``---`` fences is split on the FIRST ``": "``; unknown
keys round-trip unchanged. Slugs are validated against ``SLUG_RE`` BEFORE any path is composed
(the ``routing_scorecard.py`` snapshot date-grammar precedent) so nothing can ever escape the
facts directory.

``bin/memory_recall.py`` loads this module read-only via ``importlib`` (``bin/`` is not a
package) to reuse the schema functions — never re-implementing them.
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MEMORY_DIR = PLUGIN_ROOT / "memory"

SCHEMA_VERSION = 1
FACT_TYPES = ("user", "feedback", "project", "reference", "decision")
CONFIDENCE_LEVELS = ("high", "medium", "low")
DEDUP_JACCARD = 0.5
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
FACTS_SUBDIR = "facts"
INDEX_NAME = "index.md"

# PLAN.md D7 — projects churn fastest, user preferences endure. Unknown type -> 180 (the
# reference/decision default), never a crash.
TYPE_TTL_DAYS = {
    "user": 365, "feedback": 365, "project": 90, "reference": 180, "decision": 180,
}

FRONTMATTER_FENCE = "---"

# Fields written on every fact, in this pinned order (unknown keys append after these,
# preserving whatever order they were first read in).
CORE_FIELDS = (
    "schema", "name", "description", "type", "tags",
    "created", "last_verified", "expires", "confidence", "source",
)


# --------------------------------------------------------------------------- slug / path

def validate_slug(slug):
    """``True`` iff ``slug`` matches ``SLUG_RE`` exactly."""
    return bool(SLUG_RE.match(slug or ""))


def slugify(name):
    """Derive a slug from a free-text ``name``: lowercase, non-alnum runs -> ``-``, strip
    leading/trailing ``-``, collapse repeats, truncate to 64 chars. Falls back to ``"fact"``
    if nothing alnum survives (so the result always satisfies ``SLUG_RE``)."""
    lowered = (name or "").lower()
    collapsed = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    collapsed = re.sub(r"-{2,}", "-", collapsed)
    slug = collapsed[:64].strip("-")
    if not slug:
        slug = "fact"
    if not validate_slug(slug):
        # Truncation could leave a leading digit run fine (digits are valid leads) but a
        # trailing "-" after the cut is possible; strip once more defensively.
        slug = slug.strip("-") or "fact"
    return slug


def fact_path(memory_dir, slug):
    """``<memory_dir>/facts/<slug>.md``. Validates ``slug`` FIRST — an invalid slug raises
    ``ValueError`` before any path is composed (nothing can escape the facts dir)."""
    if not validate_slug(slug):
        raise ValueError(f"invalid slug {slug!r} — expected {SLUG_RE.pattern}")
    return Path(memory_dir) / FACTS_SUBDIR / f"{slug}.md"


# --------------------------------------------------------------------------- frontmatter parse/render

def parse_fact(text):
    """Parse a fact file's text into ``(meta, body)``.

    ``meta`` is a dict preserving unknown keys and their original textual order. The
    frontmatter is the region between the first two ``---`` fence lines; each line inside is
    split on the FIRST ``": "`` into key/value (a fence-region line with no ``": "`` is
    skipped rather than crashing). A missing opening or closing fence raises ``ValueError``.
    The body is everything after the closing fence's newline, with at most one leading blank
    line stripped (round-trip symmetry with ``render_fact``).
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != FRONTMATTER_FENCE:
        raise ValueError("missing opening frontmatter fence")
    close_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == FRONTMATTER_FENCE:
            close_idx = i
            break
    if close_idx is None:
        raise ValueError("missing closing frontmatter fence")

    meta = {}
    for line in lines[1:close_idx]:
        if not line.strip():
            continue
        if ": " in line:
            key, _, value = line.partition(": ")
            meta[key.strip()] = value.strip()
        elif line.endswith(":"):
            meta[line[:-1].strip()] = ""
        # else: unparseable frontmatter line — skipped, never a crash.

    body_lines = lines[close_idx + 1:]
    if body_lines and body_lines[0] == "":
        body_lines = body_lines[1:]
    body = "\n".join(body_lines)
    return meta, body


def render_fact(meta, body):
    """Render ``(meta, body)`` back to fact-file text. Emits ``CORE_FIELDS`` first (in pinned
    order, only the ones present in ``meta``), then any remaining unknown keys in their
    ``meta`` dict order, so ``parse_fact(render_fact(m, b)) == (m, b)`` for canonical input."""
    out = [FRONTMATTER_FENCE]
    emitted = set()
    for key in CORE_FIELDS:
        if key in meta:
            out.append(f"{key}: {meta[key]}")
            emitted.add(key)
    for key, value in meta.items():
        if key not in emitted:
            out.append(f"{key}: {value}")
    out.append(FRONTMATTER_FENCE)
    out.append("")
    out.append(body)
    return "\n".join(out)


# --------------------------------------------------------------------------- store load

def load_store(memory_dir):
    """Load every fact under ``<memory_dir>/facts/*.md`` -> ``(facts, notes)``.

    ``facts`` is a list of ``(slug, meta, body)`` tuples sorted by slug. Unreadable or
    malformed files are skipped with a note appended to ``notes`` — never a crash. A missing
    facts dir yields ``([], [])``.
    """
    facts_dir = Path(memory_dir) / FACTS_SUBDIR
    facts = []
    notes = []
    if not facts_dir.is_dir():
        return facts, notes
    for path in sorted(facts_dir.glob("*.md")):
        slug = path.stem
        try:
            text = path.read_text(errors="replace")
        except OSError as e:
            notes.append(f"{path.name}: unreadable ({e})")
            continue
        try:
            meta, body = parse_fact(text)
        except ValueError as e:
            notes.append(f"{path.name}: malformed ({e})")
            continue
        facts.append((slug, meta, body))
    facts.sort(key=lambda t: t[0])
    return facts, notes


# --------------------------------------------------------------------------- dedup / similarity

def token_set(text):
    """``re.findall(r"[a-z0-9]+", text.lower())`` as a set, dropping 1-char tokens."""
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 1}


def jaccard(a, b):
    """Jaccard similarity of two token sets. Empty/empty -> ``0.0`` (never a ZeroDivisionError,
    never a false "identical")."""
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _fact_tokens(name, description, body):
    return token_set(f"{name} {description} {body}")


# --------------------------------------------------------------------------- freshness (PLAN.md D7)

def _parse_date(s):
    """``YYYY-MM-DD`` -> ``datetime.date``, or ``None`` on anything unparseable — never a
    crash (callers treat ``None`` as "can't verify freshness from this string")."""
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def staleness_state(meta, today):
    """``"fresh" | "stale" | "expired"`` for a fact's ``meta`` as of ``today`` (a
    ``datetime.date`` or a ``YYYY-MM-DD`` string — all date math flows through this seam).

    ``expired`` if ``meta["expires"]`` parses as a date <= ``today`` (the literal string
    ``"never"`` never expires; an unparseable non-``"never"`` value is treated as not
    determinable and never gates expiry — it is not silently a crash). Else ``stale`` if
    ``last_verified`` (fallback ``created``) is more than ``TYPE_TTL_DAYS[type]`` days before
    ``today`` (unknown type -> 180); a missing or unparseable date counts as ``stale`` — never
    a crash, and never mistaken for fresh. Else ``fresh``.
    """
    if isinstance(today, str):
        today = date.fromisoformat(today)

    expires = meta.get("expires", "never")
    if expires and expires != "never":
        expires_date = _parse_date(expires)
        if expires_date is not None and expires_date <= today:
            return "expired"

    ttl_days = TYPE_TTL_DAYS.get(meta.get("type", ""), 180)
    verified_str = meta.get("last_verified") or meta.get("created")
    verified_date = _parse_date(verified_str)
    if verified_date is None:
        return "stale"
    if (today - verified_date).days > ttl_days:
        return "stale"
    return "fresh"


# --------------------------------------------------------------------------- index

def rebuild_index(memory_dir, now):
    """Fully regenerate ``<memory_dir>/index.md`` from the fact files on disk (the derived
    artifact — fact files are the source of truth). ``now`` drives each line's staleness
    ``state`` (PLAN.md D7) via ``staleness_state``, computed fresh on every rebuild."""
    memory_dir = Path(memory_dir)
    facts, _notes = load_store(memory_dir)
    lines = ["# Memory index (generated — facts/ is the source of truth)", ""]
    for slug, meta, _body in facts:
        name = meta.get("name", slug)
        description = meta.get("description", "")
        ftype = meta.get("type", "")
        state = staleness_state(meta, now)
        lines.append(f"- [{name}](facts/{slug}.md) — {description} ({ftype}, {state})")
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / INDEX_NAME).write_text("\n".join(lines) + "\n")


# --------------------------------------------------------------------------- shared CLI helpers

def _today_str():
    return date.today().isoformat()


def _parse_tags(raw):
    if raw is None:
        return None
    return ", ".join(t.strip() for t in raw.split(",") if t.strip())


def _read_body(args):
    if args.body_file:
        return Path(args.body_file).read_text(errors="replace")
    if args.body is not None:
        return args.body
    return ""


def _find_slug(facts, slug):
    for s, meta, body in facts:
        if s == slug:
            return meta, body
    return None, None


# --------------------------------------------------------------------------- subcommands

def cmd_add(args):
    memory_dir = Path(args.memory_dir)
    now = args.now

    if args.type not in FACT_TYPES:
        print(f"invalid --type {args.type!r} — expected one of {', '.join(FACT_TYPES)}")
        return 2
    confidence = args.confidence or "high"
    if confidence not in CONFIDENCE_LEVELS:
        print(f"invalid --confidence {confidence!r} — expected one of "
              f"{', '.join(CONFIDENCE_LEVELS)}")
        return 2

    slug = args.slug or slugify(args.name)
    if not validate_slug(slug):
        print(f"invalid slug {slug!r} — expected {SLUG_RE.pattern}")
        return 2

    body = _read_body(args)
    description = args.description or ""
    facts, _notes = load_store(memory_dir)

    if not args.force:
        existing_meta, _ = _find_slug(facts, slug)
        if existing_meta is not None:
            print(f"duplicate of [{slug}] — update it instead (or pass --force)")
            return 2

        new_tokens = _fact_tokens(args.name, description, body)
        for s, meta, fbody in facts:
            existing_tokens = _fact_tokens(
                meta.get("name", ""), meta.get("description", ""), fbody)
            if jaccard(new_tokens, existing_tokens) >= DEDUP_JACCARD:
                print(f"duplicate of [{s}] — update it instead (or pass --force)")
                return 2

    meta = {
        "schema": str(SCHEMA_VERSION),
        "name": args.name,
        "description": description,
        "type": args.type,
        "tags": _parse_tags(args.tags) or "",
        "created": now,
        "last_verified": now,
        "expires": args.expires or "never",
        "confidence": confidence,
        "source": args.source or "",
    }

    path = fact_path(memory_dir, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_fact(meta, body))
    rebuild_index(memory_dir, now)

    if args.json:
        print(json.dumps({"slug": slug, **meta}))
    else:
        print(slug)
    return 0


def cmd_update(args):
    memory_dir = Path(args.memory_dir)
    now = args.now

    facts, _notes = load_store(memory_dir)
    meta, body = _find_slug(facts, args.slug)
    if meta is None:
        print(f"unknown slug {args.slug!r}")
        return 2

    if args.type is not None:
        if args.type not in FACT_TYPES:
            print(f"invalid --type {args.type!r} — expected one of {', '.join(FACT_TYPES)}")
            return 2
        meta["type"] = args.type
    if args.confidence is not None:
        if args.confidence not in CONFIDENCE_LEVELS:
            print(f"invalid --confidence {args.confidence!r} — expected one of "
                  f"{', '.join(CONFIDENCE_LEVELS)}")
            return 2
        meta["confidence"] = args.confidence
    if args.name is not None:
        meta["name"] = args.name
    if args.description is not None:
        meta["description"] = args.description
    if args.tags is not None:
        meta["tags"] = _parse_tags(args.tags) or ""
    if args.expires is not None:
        meta["expires"] = args.expires
    if args.source is not None:
        meta["source"] = args.source
    if args.body_file is not None:
        body = Path(args.body_file).read_text(errors="replace")
    elif args.body is not None:
        body = args.body

    meta["last_verified"] = now  # an update IS a verification (PLAN D7)

    path = fact_path(memory_dir, args.slug)
    path.write_text(render_fact(meta, body))
    rebuild_index(memory_dir, now)

    if args.json:
        print(json.dumps({"slug": args.slug, **meta}))
    else:
        print(args.slug)
    return 0


def cmd_remove(args):
    memory_dir = Path(args.memory_dir)
    facts, _notes = load_store(memory_dir)
    meta, _body = _find_slug(facts, args.slug)
    if meta is None:
        print(f"unknown slug {args.slug!r}")
        return 2

    path = fact_path(memory_dir, args.slug)
    path.unlink(missing_ok=True)
    rebuild_index(memory_dir, args.now)
    print(f"removed {args.slug}")
    return 0


def cmd_list(args):
    memory_dir = Path(args.memory_dir)
    facts, notes = load_store(memory_dir)

    if args.json:
        out = {
            "schema_version": SCHEMA_VERSION,
            "facts": [dict(meta, slug=slug) for slug, meta, _body in facts],
            "notes": notes,
        }
        print(json.dumps(out, indent=2))
        return 0

    if not facts:
        print("no facts stored yet")
        for note in notes:
            print(f"note: {note}")
        return 0

    for slug, meta, _body in facts:
        name = meta.get("name", slug)
        description = meta.get("description", "")
        ftype = meta.get("type", "")
        confidence = meta.get("confidence", "")
        state = staleness_state(meta, args.now)
        print(f"[{slug}] {name} — {description} ({ftype}, {confidence}, {state})")
    for note in notes:
        print(f"note: {note}")
    return 0


def cmd_verify(args):
    """Bump ``last_verified`` to ``--now`` (an update-free verification — PLAN.md D7) and
    regenerate the index. Unknown slug -> exit 2."""
    memory_dir = Path(args.memory_dir)
    now = args.now

    facts, _notes = load_store(memory_dir)
    meta, body = _find_slug(facts, args.slug)
    if meta is None:
        print(f"unknown slug {args.slug!r}")
        return 2

    meta["last_verified"] = now
    path = fact_path(memory_dir, args.slug)
    path.write_text(render_fact(meta, body))
    rebuild_index(memory_dir, now)

    ttl_days = TYPE_TTL_DAYS.get(meta.get("type", ""), 180)
    print(f"verified [{args.slug}] — fresh until +{ttl_days}d")
    return 0


def _review_line(slug, meta, state):
    name = meta.get("name", slug)
    last_verified = meta.get("last_verified") or meta.get("created") or ""
    ttl_days = TYPE_TTL_DAYS.get(meta.get("type", ""), 180)
    return (f"[{slug}] {name} — {state} (last_verified {last_verified}, ttl {ttl_days}d) "
            f"→ verify, update, or remove")


def _review_json_entry(slug, meta):
    return {
        "slug": slug,
        "name": meta.get("name", slug),
        "last_verified": meta.get("last_verified") or meta.get("created") or "",
        "ttl_days": TYPE_TTL_DAYS.get(meta.get("type", ""), 180),
    }


def cmd_review(args):
    """Read-only staleness report — never writes anything (PLAN.md D7). Expired facts first,
    then stale, each group sorted by slug; a fully-fresh store prints ``all <n> facts
    fresh``."""
    memory_dir = Path(args.memory_dir)
    now = args.now

    facts, notes = load_store(memory_dir)
    expired = []
    stale = []
    fresh_count = 0
    for slug, meta, _body in facts:
        state = staleness_state(meta, now)
        if state == "expired":
            expired.append((slug, meta))
        elif state == "stale":
            stale.append((slug, meta))
        else:
            fresh_count += 1
    expired.sort(key=lambda t: t[0])
    stale.sort(key=lambda t: t[0])

    if args.json:
        out = {
            "schema_version": SCHEMA_VERSION,
            "expired": [_review_json_entry(s, m) for s, m in expired],
            "stale": [_review_json_entry(s, m) for s, m in stale],
            "fresh_count": fresh_count,
            "notes": notes,
        }
        print(json.dumps(out, indent=2))
        return 0

    if not expired and not stale:
        print(f"all {fresh_count} facts fresh")
        for note in notes:
            print(f"note: {note}")
        return 0

    for slug, meta in expired:
        print(_review_line(slug, meta, "expired"))
    for slug, meta in stale:
        print(_review_line(slug, meta, "stale"))
    for note in notes:
        print(f"note: {note}")
    return 0


# --------------------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Durable memory-skill fact store (stdlib-only, gitignored user data).")
    sub = ap.add_subparsers(dest="command", required=True)

    def _common(p):
        p.add_argument("--memory-dir", default=str(DEFAULT_MEMORY_DIR))
        p.add_argument("--now", default=_today_str(),
                        help="YYYY-MM-DD (default: today) — all date math flows through this")

    p_add = sub.add_parser("add", help="add a new fact (dedup-gated)")
    _common(p_add)
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--type", required=True,
                        help=f"one of {', '.join(FACT_TYPES)}")
    p_add.add_argument("--description", default=None)
    p_add.add_argument("--tags", default=None, help="comma-separated")
    p_add.add_argument("--body", default=None)
    p_add.add_argument("--body-file", default=None)
    p_add.add_argument("--slug", default=None)
    p_add.add_argument("--expires", default=None, help="YYYY-MM-DD or 'never' (default: never)")
    p_add.add_argument("--confidence", default=None,
                        help=f"one of {', '.join(CONFIDENCE_LEVELS)}")
    p_add.add_argument("--source", default=None)
    p_add.add_argument("--force", action="store_true",
                        help="skip the dedup gate and exact-slug refusal")
    p_add.add_argument("--json", action="store_true")
    p_add.set_defaults(func=cmd_add)

    p_update = sub.add_parser("update", help="rewrite given fields on an existing fact")
    _common(p_update)
    p_update.add_argument("slug")
    p_update.add_argument("--name", default=None)
    p_update.add_argument("--description", default=None)
    p_update.add_argument("--tags", default=None)
    p_update.add_argument("--body", default=None)
    p_update.add_argument("--body-file", default=None)
    p_update.add_argument("--expires", default=None)
    p_update.add_argument("--confidence", default=None,
                           help=f"one of {', '.join(CONFIDENCE_LEVELS)}")
    p_update.add_argument("--type", default=None,
                           help=f"one of {', '.join(FACT_TYPES)}")
    p_update.add_argument("--source", default=None)
    p_update.add_argument("--json", action="store_true")
    p_update.set_defaults(func=cmd_update)

    p_remove = sub.add_parser("remove", help="delete a fact")
    _common(p_remove)
    p_remove.add_argument("slug")
    p_remove.set_defaults(func=cmd_remove)

    p_list = sub.add_parser("list", help="list stored facts")
    _common(p_list)
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=cmd_list)

    p_verify = sub.add_parser("verify", help="bump last_verified on a fact (a verification)")
    _common(p_verify)
    p_verify.add_argument("slug")
    p_verify.set_defaults(func=cmd_verify)

    p_review = sub.add_parser("review", help="read-only staleness report (never writes)")
    _common(p_review)
    p_review.add_argument("--json", action="store_true")
    p_review.set_defaults(func=cmd_review)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
