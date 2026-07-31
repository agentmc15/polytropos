#!/usr/bin/env python3
"""Offline ask-the-tools prompt pack (PLAN.md D1, journal-augment kit).

The daily journal reads only Claude Code, Copilot CLI, Codex CLI, and git activity — it has
no view into Microsoft Teams, Outlook, or Copilot Studio. This script closes that gap WITHOUT
adding any network call, OAuth flow, Graph API, or MCP connector: it is pure, deterministic
TEXT GENERATION that writes ready-to-paste prompts for the user to run inside their OWN
Microsoft tools.

Two-pass flow:
  1. ``bin/journal_collect.py`` collects the day's AI-assisted work into ``digest.json``.
  2. This script renders ``journal/<date>/ask-the-tools.md`` — one prompt per tool (Copilot
     Studio, Microsoft Teams, Outlook) asking that tool's own AI to summarize the date's
     activity as short bullet lines.
  3. The user copies each prompt into the matching tool, then pastes the bullet results back
     into ``journal/inbox.md`` — the plain-text return path ``journal_collect.py``'s
     ``read_inbox`` already ingests.
  4. Re-running the collector (and then the summaries) folds the enriched inbox into the
     digest.

Content hygiene (the ask-pack's own tripwire): every prompt caps the requested reply at
``MAX_ASK_BULLETS`` short, subject-level-only bullet lines (titles, people, decisions, action
items) and explicitly forbids message bodies, attachments, or confidential excerpts — so
whatever gets pasted back can never bloat the digest with raw transcript text. When a digest
is supplied, the only thing it contributes to a prompt is the sorted union of project NAMES
already recorded by the other adapters — nothing else from the digest ever reaches a prompt.

The Graph/OAuth/MCP connector paths for Teams/Outlook/Copilot Studio remain deferred BY
DESIGN; this pack is the fully offline stand-in.

Usage:
  journal_askpack.py [--date YYYY-MM-DD] [--utc] [--journal-dir DIR] [--digest PATH] [--print]
"""

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent

# 3 tools x MAX_ASK_BULLETS stays well under journal_collect.py's MAX_INBOX_ITEMS (100).
MAX_ASK_BULLETS = 15

TOOLS = ("copilot_studio", "teams", "outlook")
TOOL_TITLES = {
    "copilot_studio": "Copilot Studio",
    "teams": "Microsoft Teams",
    "outlook": "Outlook",
}

# One sentence per tool, own the wording (PLAN.md D1) — {date} is filled with date_str.
_TOOL_ASK_SENTENCE = {
    "teams": "Summarize {date}'s meetings and chat threads.",
    "outlook": "Summarize {date}'s sent and received email, flagged items, and action items.",
    "copilot_studio": (
        "Summarize {date}'s agent/copilot sessions: which agents, topics, and outcomes."
    ),
}

# Pinned hygiene bound: caps the reply length and forbids anything but subject-level facts.
_BULLET_RULE = (
    "Reply with at most {n} short bullet lines, each line starting with \"- \". Keep every "
    "bullet subject-level only (titles, people, decisions, action items) — no message "
    "bodies, no attachments, no confidential excerpts."
).format(n=MAX_ASK_BULLETS)

# Pinned closing sentence — reproduced verbatim in every prompt.
_PASTE_BACK = "I will paste these bullets into my daily journal's plain-text inbox."


def _project_union(digest):
    """Sorted union of every source report's ``projects`` list in ``digest["sources"]``.

    Tolerant of a missing/malformed digest or missing keys — returns ``[]``. This is the ONLY
    digest content that ever reaches a prompt (project NAMES, nothing else — PLAN.md D1
    hygiene bound / the "ask-pack bloat" tripwire).
    """
    if not isinstance(digest, dict):
        return []
    sources = digest.get("sources")
    if not isinstance(sources, dict):
        return []
    projects = set()
    for report in sources.values():
        if not isinstance(report, dict):
            continue
        for p in report.get("projects") or []:
            if isinstance(p, str):
                projects.add(p)
    return sorted(projects)


def build_ask_prompts(date_str, digest=None):
    """Build the three ready-to-paste prompts (pure). Returns a dict keyed exactly ``TOOLS``.

    Each prompt names ``date_str``, caps the reply at ``MAX_ASK_BULLETS`` subject-level bullet
    lines starting with ``"- "``, states the hygiene bound, and ends with the pinned
    paste-back sentence. When ``digest`` carries any ``sources.*.projects``, one extra
    project-name-only context line is appended before the closing sentence.
    """
    projects = _project_union(digest)
    context_line = ""
    if projects:
        context_line = (
            "For context, today I worked on these projects: "
            + ", ".join(projects) + ".\n\n"
        )

    prompts = {}
    for tool in TOOLS:
        ask = _TOOL_ASK_SENTENCE[tool].format(date=date_str)
        prompts[tool] = (
            f"You are my {TOOL_TITLES[tool]} AI assistant. {ask}\n\n"
            f"{_BULLET_RULE}\n\n"
            + context_line
            + _PASTE_BACK + "\n"
        )
    return prompts


def render_pack(date_str, prompts):
    """Render the pinned one-file markdown document (pure).

    Shape: H1 ``# Ask the tools — {date_str}``; ``## How to use`` with the 4-step two-pass
    flow; then one ``## {TOOL_TITLES[tool]}`` section per ``TOOLS`` entry (in that order) with
    the prompt inside a plain triple-backtick fence; a closing one-line privacy note.
    """
    lines = [f"# Ask the tools — {date_str}", ""]
    lines.append("## How to use")
    lines.append("")
    lines.append(
        "This is a two-pass, fully offline flow — no network, no OAuth, no Graph API, no "
        "MCP connector:"
    )
    lines.append("")
    lines.append(
        "1. Copy a prompt below into the matching tool's own AI (Copilot Studio, Microsoft "
        "Teams, or Outlook)."
    )
    lines.append("2. Paste the tool's bullet output into `journal/inbox.md`.")
    lines.append(
        "3. Re-run the collector — `python3 bin/journal_collect.py` or "
        "`python3 bin/journal_schedule.py run` — so the inbox folds into the digest."
    )
    lines.append("4. Re-run (or redo) the summaries to get the enriched journal.")
    lines.append("")
    for tool in TOOLS:
        lines.append(f"## {TOOL_TITLES[tool]}")
        lines.append("")
        lines.append("```")
        lines.append(prompts[tool].rstrip("\n"))
        lines.append("```")
        lines.append("")
    lines.append(
        "Privacy: pasted bullets become part of the digest and are later sent to a model by "
        "the summarizer."
    )
    lines.append("")
    return "\n".join(lines)


def _resolve_date_str(date_arg, utc):
    """Copy of journal_summarize.py's ``_resolve_date_str`` semantics: explicit ``--date``
    wins (validated); else today's date, in UTC when ``utc`` is set."""
    if date_arg is not None:
        try:
            return date.fromisoformat(date_arg).isoformat()
        except ValueError:
            sys.exit(f"invalid --date (want YYYY-MM-DD): {date_arg}")
    if utc:
        return datetime.now(timezone.utc).date().isoformat()
    return date.today().isoformat()


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Generate the offline ask-the-tools prompt pack (PLAN.md D1) — pure "
                    "text generation, spawns nothing.")
    ap.add_argument("--date", default=None,
                    help="YYYY-MM-DD (default: today; matches journal_collect.py)")
    ap.add_argument("--utc", action="store_true",
                    help="resolve the default date in UTC (tests/verifies use it)")
    ap.add_argument("--journal-dir", default=str(PLUGIN_ROOT / "journal"),
                    help="journal root (output is <journal-dir>/<date>/ask-the-tools.md)")
    ap.add_argument("--digest", default=None,
                    help="explicit digest.json path for project-name context only "
                         "(default: <journal-dir>/<date>/digest.json if present)")
    ap.add_argument("--print", action="store_true",
                    help="also print the rendered pack to stdout")
    args = ap.parse_args(argv)

    date_str = _resolve_date_str(args.date, args.utc)

    if args.digest:
        digest_path = Path(args.digest)
    else:
        digest_path = Path(args.journal_dir) / date_str / "digest.json"

    digest = None
    if digest_path.is_file():
        try:
            digest = json.loads(digest_path.read_text(errors="replace"))
        except (OSError, ValueError):
            digest = None  # tolerate a missing/unparseable digest — never crash over enrichment

    prompts = build_ask_prompts(date_str, digest=digest)
    pack = render_pack(date_str, prompts)

    out_dir = Path(args.journal_dir) / date_str
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        sys.exit(f"cannot create journal dir {out_dir}: {e}")

    out_path = out_dir / "ask-the-tools.md"
    try:
        out_path.write_text(pack)
    except OSError as e:
        sys.exit(f"cannot write ask pack {out_path}: {e}")

    print(f"ask pack written: {out_path}")
    if args.print:
        print(pack)
    return 0


if __name__ == "__main__":
    sys.exit(main())
