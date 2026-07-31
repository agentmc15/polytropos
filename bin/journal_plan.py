#!/usr/bin/env python3
"""Next-day runbook — pure core (PLAN.md D1, D3-D7).

The runbook is a dated, checkable plan for the NEXT day, layered on the daily journal and
stored as one markdown file per due date under the gitignored ``journal/plan/`` tree. Each
planned task is a card carrying a "what to do and how" body, a deterministic ideal-harness
recommendation, and ready-to-paste commands for Claude Code, Copilot CLI, and Codex CLI.

ADVISORY ONLY. Nothing here auto-executes. This module never spawns a process, never opens a
network connection, never reads a home directory, and never opens a database — no scheduler
and no dispatch of any kind, by explicit user decision. The generator produces command TEXT a
human copies and runs; that is the whole feature.

Deterministic-signals-then-prose (the journal's split, preserved): this module writes only
the structural What/How SEEDS (exact kit paths, the resume command, ``git status`` for WIP,
the inbox/seed line verbatim). The deep, model-authored detail is added IN-SESSION via the
pinned enrichment prompt (owned by the CLI half of this file, added in a later task) — the
same "write it yourself in this paid session" flow the journal summaries already use.

Honesty rules (absolute): absent pricing/slot/digest data renders ``est n/a`` or an honest
note, never a fabricated or zeroed figure; every Codex dollar is labeled an API-equivalent
proxy, never a bill, and Codex is never the deterministic ideal pick; a rebuild preserves the
user's state (checkboxes, deferrals, ids, and possibly model-enriched What/How bodies)
byte-for-byte and only refreshes the Harness blocks.

This file holds both the PURE CORE (module constants, parsers, builders, renderers, and text
mutators — only ``collect_carry`` and ``check_cards`` touch the filesystem, read-only, under
the given plan directory; every other function is pure over its arguments) AND the CLI added
here: the reuse loads (via the ``_load`` importlib helper), the pinned in-session enrichment
prompt, and the ``build``/``check``/``done``/``defer``/``prompt`` subcommands.

Usage:
  journal_plan.py build [--for YYYY-MM-DD] [--print] [--date YYYY-MM-DD] [--utc]
                        [--journal-dir DIR]
  journal_plan.py check [--date YYYY-MM-DD] [--utc] [--journal-dir DIR]
  journal_plan.py done <id> [--date YYYY-MM-DD] [--utc] [--journal-dir DIR]
  journal_plan.py defer <id> --to YYYY-MM-DD [--date YYYY-MM-DD] [--utc] [--journal-dir DIR]
  journal_plan.py prompt [--for YYYY-MM-DD] [--date YYYY-MM-DD] [--utc] [--journal-dir DIR]

``build``, ``done``, and ``defer`` write ONLY under ``<journal-dir>/plan/`` — there is no
home-directory flag at all, and no other path is ever touched. ``prompt`` writes nothing and
spawns nothing; it prints the pinned enrichment prompt to stdout, which is how the journal
skill enriches a runbook's What/How steps IN-SESSION (the user runs the prompt in the current,
already-paid-for session, then saves the model's revised markdown back over the same plan
file by hand).
"""

import argparse
import importlib.util
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent

# ---- pinned constants ------------------------------------------------------------------------

PLAN_SCHEMA = 1
PLAN_DIRNAME = "plan"
SEED_FILENAME = "seed.md"
PLAN_STEM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SEED_MARKERS = ("- ", "* ", "[ ] ")   # read_inbox parity (journal_collect.py)
MAX_PLAN_CARDS = 100
EST_PROFILE = "M"
TIER_TO_SLOT = {"haiku": "cheap", "sonnet": "mid", "opus": "mid"}
HARNESS_ORDER = ("claude_code", "copilot_cli", "codex_cli")
ADVISORY_LINE = ("Advisory only — nothing here auto-executes; every command below is "
                 "ready-to-paste for a human to run.")
NO_SIGNAL_LINE = "- harness signals unavailable — run journal_collect.py, then rebuild"
EST_NA = "est n/a — pricing or tier unavailable"
OPUS_SLOT_NOTE = ("- note: task pinned opus — estimates show the mid slot (the advisor's "
                  "table covers cheap/mid by design)")

# ---- reuse loads (importlib, read-only; the loaded modules are never edited) ------------------

def _load(name):
    """Load a sibling ``bin/<name>.py`` module read-only (the journal_collect.py pattern)."""
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parent / f"{name}.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cr = _load("cost_report")      # data/pricing.json loader (read-only reuse)
cu = _load("copilot_usage")    # data/pricing.copilot.json loader (read-only reuse)
cxu = _load("codex_usage")     # data/pricing.codex.json loader (read-only reuse)
ja = _load("journal_advisor")  # harness routing signals (advisory-only, read-only reuse)

# ---- internal grammar helpers ----------------------------------------------------------------

_H1_PREFIX = "# Runbook — "
_TASKS_HEADING = "## Tasks"
_NOTES_HEADING = "## Notes"
_WHATHOW_HEADING = "**What/How:**"
_HARNESS_HEADING = "**Harness:**"
_CARD_HEAD_RE = re.compile(r"^### \[( |x)\] (R\d+) — (.*)$")
_IDEAL_PREFIX = "- ideal: "

# Field lines rendered under each card header, in this exact order. Every prefix is distinct
# and none is a prefix of another, so a plain ``startswith`` scan is unambiguous.
_FIELD_PREFIXES = (
    ("- source: ", "source"),
    ("- due: ", "due"),
    ("- first-planned: ", "first_planned"),
    ("- model-hint: ", "model_hint"),
    ("- deferred-to: ", "deferred_to"),
)


def _id_num(card_id):
    """The integer ``n`` of an ``R<n>`` id, or None for anything else."""
    if isinstance(card_id, str) and card_id.startswith("R") and card_id[1:].isdigit():
        return int(card_id[1:])
    return None


def _new_card(title, source, model_hint, how, for_date):
    """A fresh (id-less) card dict with the pinned key set."""
    return {
        "id": None,
        "checked": False,
        "title": title,
        "source": source,
        "due": for_date,
        "first_planned": for_date,
        "model_hint": model_hint,
        "deferred_to": None,
        "how": how,
        "harness": "",
    }


def _line_seed(line):
    """The pinned inbox/seed What/How seed body (2 numbered steps, the line verbatim)."""
    return (
        f"1. {line}\n"
        "2. Refine this card during enrichment, then check it off once finished."
    )


# ---- title + key helpers ---------------------------------------------------------------------

def sanitize_title(title):
    """Strip every ``"`` and backtick, collapse internal whitespace runs to single spaces,
    strip ends. This is what flows into a ready-to-paste shell command (the injection guard)."""
    cleaned = (title or "").replace('"', "").replace("`", "")
    return " ".join(cleaned.split()).strip()


def dedup_key(card):
    """Dedup key: the ``source`` token when it starts ``kit:`` or ``wip:`` (structural,
    stable); else the casefolded, whitespace-collapsed title."""
    source = card.get("source") or ""
    if source.startswith("kit:") or source.startswith("wip:"):
        return source
    title = card.get("title") or ""
    return " ".join(title.split()).casefold()


# ---- parsing ---------------------------------------------------------------------------------

def _parse_card_block(block):
    """Parse one ``### ``-headed card block -> ``(card, None)`` or ``(None, note)``.

    Tolerant: a malformed block (bad header, missing What/How or Harness section) returns
    ``(None, <note>)`` and never raises."""
    block = list(block)
    while block and block[-1] == "":
        block.pop()
    if not block:
        return None, "skipped an empty card block"
    m = _CARD_HEAD_RE.match(block[0])
    if not m:
        return None, f"skipped malformed card header: {block[0][:60]!r}"
    checked = m.group(1) == "x"
    card_id = m.group(2)
    title = m.group(3)

    wh_idx = None
    hn_idx = None
    for i, line in enumerate(block):
        if line == _WHATHOW_HEADING and wh_idx is None:
            wh_idx = i
        elif line == _HARNESS_HEADING and hn_idx is None:
            hn_idx = i
    if wh_idx is None or hn_idx is None or hn_idx < wh_idx:
        return None, f"skipped malformed card {card_id}: missing What/How or Harness section"

    fields = {}
    for line in block[1:wh_idx]:
        for prefix, key in _FIELD_PREFIXES:
            if line.startswith(prefix):
                fields[key] = line[len(prefix):]
                break

    how_lines = block[wh_idx + 1:hn_idx]
    while how_lines and how_lines[-1] == "":
        how_lines.pop()
    harness_lines = block[hn_idx + 1:]
    while harness_lines and harness_lines[-1] == "":
        harness_lines.pop()

    card = {
        "id": card_id,
        "checked": checked,
        "title": title,
        "source": fields.get("source", ""),
        "due": fields.get("due", ""),
        "first_planned": fields.get("first_planned", ""),
        "model_hint": fields.get("model_hint", "none"),
        "deferred_to": fields.get("deferred_to"),
        "how": "\n".join(how_lines),
        "harness": "\n".join(harness_lines),
    }
    return card, None


def parse_plan(text):
    """Parse a rendered runbook file -> ``{"date", "cards", "notes"}`` (tolerant).

    ``date`` is the H1 due-date (or None). ``cards`` is a list of card dicts with the pinned
    key set; a malformed card is skipped with one entry appended to ``notes`` — never an
    exception. ``render_plan`` of the parsed cards reproduces the file byte-for-byte."""
    lines = text.split("\n")

    date = None
    for line in lines:
        if line.startswith(_H1_PREFIX):
            date = line[len(_H1_PREFIX):].strip() or None
            break

    tasks_idx = None
    notes_idx = None
    for i, line in enumerate(lines):
        if line == _TASKS_HEADING and tasks_idx is None:
            tasks_idx = i
        elif line == _NOTES_HEADING and notes_idx is None:
            notes_idx = i

    notes = []
    if notes_idx is not None:
        for line in lines[notes_idx + 1:]:
            if line.startswith("- "):
                notes.append(line[2:])

    cards = []
    if tasks_idx is not None:
        region_end = notes_idx if notes_idx is not None else len(lines)
        region = lines[tasks_idx + 1:region_end]
        blocks = []
        current = None
        for line in region:
            if line.startswith("### "):
                if current is not None:
                    blocks.append(current)
                current = [line]
            elif current is not None:
                current.append(line)
        if current is not None:
            blocks.append(current)
        for block in blocks:
            card, note = _parse_card_block(block)
            if card is None:
                notes.append(note)
            else:
                cards.append(card)

    return {"date": date, "cards": cards, "notes": notes}


def parse_seeds(text):
    """Parse ``seed.md`` with the inbox grammar (``read_inbox`` parity): skip blank lines and
    lines starting ``#``; strip ONE leading ``SEED_MARKERS`` marker; strip whitespace."""
    items = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        for marker in SEED_MARKERS:
            if line.startswith(marker):
                line = line[len(marker):].strip()
                break
        items.append(line)
    return items


# ---- card building ---------------------------------------------------------------------------

def cards_from_digest(digest, for_date):
    """New (id-less) cards from a digest's next-day signals, in the pinned order:
    ``signals.kit_tasks`` (digest order), then ``signals.wip``, then ``signals.inbox.items``.

    Tolerant of a missing/None digest or any missing signals key (``.get`` all the way) -> the
    empty list. Content is TITLES / user lines only — no brief text, matching the digest's own
    hygiene."""
    cards = []
    if not isinstance(digest, dict):
        return cards
    signals = digest.get("signals")
    if not isinstance(signals, dict):
        return cards

    for task in signals.get("kit_tasks") or []:
        if not isinstance(task, dict):
            continue
        kit = task.get("kit")
        task_id = task.get("id")
        model = task.get("model")
        model_hint = model if model in TIER_TO_SLOT else "none"
        title = f"{kit}/{task_id} — {task.get('title')}"
        source = f"kit:{kit}/{task_id}"
        how = (
            f"1. Open `.claude/kits/{kit}/TASKS.md` and read the {task_id} brief — "
            "it is authoritative.\n"
            f"2. Resume the kit: `/polytropos:execute {kit}` (Claude Code), or paste a "
            "harness command from below.\n"
            "3. Run the task's verify command from the repo root before calling it done."
        )
        cards.append(_new_card(title, source, model_hint, how, for_date))

    for entry in signals.get("wip") or []:
        if not isinstance(entry, dict):
            continue
        repo = entry.get("repo")
        branch = entry.get("branch")
        dirty = entry.get("dirty_files")
        untracked = entry.get("untracked")
        title = f"Resume uncommitted work in {repo} ({branch})"
        source = f"wip:{repo}"
        how = (
            f"1. Open the {repo} repo (branch {branch}) — {dirty} dirty and {untracked} "
            "untracked files await.\n"
            "2. Review with `git status`; commit, stash, or continue the work."
        )
        cards.append(_new_card(title, source, "none", how, for_date))

    inbox = signals.get("inbox")
    items = inbox.get("items") if isinstance(inbox, dict) else None
    for item in items or []:
        cards.append(_new_card(item, "inbox", "none", _line_seed(item), for_date))

    return cards


def card_from_seed(line, for_date):
    """A ``seed``-source card from a hand-added seed.md line (like an inbox card)."""
    return _new_card(line, "seed", "none", _line_seed(line), for_date)


def collect_carry(plan_dir, for_date):
    """Scan ``<plan_dir>/*.md`` for cards to carry forward into ``for_date`` -> ``(cards, notes)``.

    Only stems matching ``PLAN_STEM_RE`` AND ``stem < for_date`` are considered (ISO strings
    compare correctly; a non-date file other than ``seed.md`` gets one note each; an unreadable
    file gets one note). All cards are deduped by ``dedup_key`` keeping the occurrence from the
    LATEST stem (the authoritative state), then the survivors that are unchecked and either not
    deferred or deferred to ``<= for_date`` carry forward. A carried card keeps ``title``,
    ``source``, ``model_hint``, ``first_planned``, and ``how``, and takes ``due = for_date``,
    ``deferred_to = None``, ``checked = False``, ``id = None``. Historical files are NEVER
    written."""
    plan_dir = Path(plan_dir)
    notes = []
    chosen = {}   # dedup_key -> (stem, card)
    for path in sorted(plan_dir.glob("*.md")):
        if path.name == SEED_FILENAME:
            continue
        stem = path.stem
        if not PLAN_STEM_RE.match(stem):
            notes.append(f"skipped non-date file in plan dir: {path.name}")
            continue
        if not (stem < for_date):
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError as e:
            notes.append(f"unreadable plan file {path.name}: {e}")
            continue
        for card in parse_plan(text)["cards"]:
            key = dedup_key(card)
            if key not in chosen or stem > chosen[key][0]:
                chosen[key] = (stem, card)

    carried = []
    for stem, card in chosen.values():
        if card["checked"]:
            continue
        deferred_to = card["deferred_to"]
        if deferred_to is not None and not (deferred_to <= for_date):
            continue
        carried.append({
            "id": None,
            "checked": False,
            "title": card["title"],
            "source": card["source"],
            "due": for_date,
            "first_planned": card["first_planned"],
            "model_hint": card["model_hint"],
            "deferred_to": None,
            "how": card["how"],
            "harness": "",
        })
    carried.sort(key=lambda c: (c["first_planned"], c["title"]))
    return carried, notes


def assemble_cards(digest, seeds, carried, for_date):
    """Combine carried + digest + seed cards into the day's candidate list -> ``(cards, notes)``.

    Pinned order: carried first, then ``cards_from_digest``, then a ``card_from_seed`` per seed
    line. Deduped by ``dedup_key`` with the FIRST occurrence winning (so a carried card beats a
    digest duplicate, preserving its enriched ``how`` and ``first_planned``). Capped at
    ``MAX_PLAN_CARDS`` with a note when exceeded."""
    ordered = list(carried)
    ordered.extend(cards_from_digest(digest, for_date))
    for line in seeds or []:
        ordered.append(card_from_seed(line, for_date))

    seen = set()
    result = []
    for card in ordered:
        key = dedup_key(card)
        if key in seen:
            continue
        seen.add(key)
        result.append(card)

    notes = []
    if len(result) > MAX_PLAN_CARDS:
        notes.append(
            f"card cap reached — {len(result)} candidate cards trimmed to {MAX_PLAN_CARDS}"
        )
        result = result[:MAX_PLAN_CARDS]
    return result, notes


def merge_cards(existing, new):
    """Merge freshly-computed ``new`` cards into an existing file's ``existing`` cards (D6).

    Existing cards keep their id, order, ``checked``, ``deferred_to``, ``first_planned``,
    ``model_hint``, and ``how`` byte-intact. A new card whose key matches an existing card
    contributes nothing except marking that existing card for a Harness refresh. Existing cards
    with no new match are preserved (NOT refreshed — their old ``harness`` text is kept
    verbatim). Unmatched new cards append in order with the next free ``R<n>`` ids (n = 1 + the
    highest existing numeric id) and are marked for refresh. Returns ``(cards, refresh_ids)``."""
    existing_keys = set()
    max_id = 0
    for card in existing:
        existing_keys.add(dedup_key(card))
        n = _id_num(card.get("id"))
        if n is not None and n > max_id:
            max_id = n

    new_keys = {dedup_key(c) for c in new}

    refresh = set()
    result = list(existing)
    for card in existing:
        if dedup_key(card) in new_keys:
            refresh.add(card["id"])

    next_id = max_id + 1
    for card in new:
        if dedup_key(card) in existing_keys:
            continue
        card_id = f"R{next_id}"
        next_id += 1
        appended = dict(card)
        appended["id"] = card_id
        result.append(appended)
        refresh.add(card_id)

    return result, refresh


# ---- harness composition ---------------------------------------------------------------------

def pick_slot(card):
    """The advisor est slot for this card's model-hint (default ``mid``)."""
    return TIER_TO_SLOT.get(card.get("model_hint"), "mid")


def pick_ideal(card, slot_entries):
    """The deterministic, honest ideal-harness pick + one-line reason (D4).

    ``slot_entries`` maps harness name -> its est slot entry (dict or None) for this card's
    slot. (i) a ``kit:`` source is structurally a Claude Code execution kit. (ii) else compare
    the real-dollar ``usd_est`` of claude_code vs copilot_cli — the lower wins, naming both
    figures; Codex is excluded from the ranking because its figure is an API-equivalent proxy,
    not a bill. (iii) only one real-dollar est -> that harness. (iv) none -> claude_code.
    ``codex_cli`` is NEVER returned."""
    source = card.get("source") or ""
    if source.startswith("kit:"):
        return ("claude_code",
                "kit tasks run via /polytropos:execute in Claude Code")

    claude = slot_entries.get("claude_code")
    copilot = slot_entries.get("copilot_cli")
    claude_usd = claude.get("usd_est") if isinstance(claude, dict) else None
    copilot_usd = copilot.get("usd_est") if isinstance(copilot, dict) else None

    if claude_usd is not None and copilot_usd is not None:
        if claude_usd <= copilot_usd:
            winner, a, b = "claude_code", claude_usd, copilot_usd
        else:
            winner, a, b = "copilot_cli", copilot_usd, claude_usd
        reason = (
            f"cheapest real-dollar est for profile {EST_PROFILE} "
            f"(${a:.4f} vs ${b:.4f}); codex excluded from cost ranking "
            "(API-equivalent proxy, not a bill)"
        )
        return (winner, reason)
    if claude_usd is not None:
        return ("claude_code", "only harness with a real-dollar estimate")
    if copilot_usd is not None:
        return ("copilot_cli", "only harness with a real-dollar estimate")
    return ("claude_code", "default — no estimates available")


def _est_text(harness, entry):
    """The pinned est label for one harness slot entry, or None when a required figure is
    absent (a missing figure is never fabricated). ``est M`` label is built from ``EST_PROFILE``."""
    label = f"est {EST_PROFILE}"
    try:
        if harness == "claude_code":
            return f"{label} ~${entry['usd_est']:.4f}"
        if harness == "copilot_cli":
            return f"{label} ~${entry['usd_est']:.4f} / ~{entry['aic_est']:.1f} AIC"
        return f"{label} ~${entry['usd_api_equivalent']:.4f} API-equivalent — not a bill"
    except (KeyError, TypeError):
        return None


def compose_harness_block(card, signal):
    """Render a card's ``**Harness:**`` body from a ``build_harness_signal`` result (D3).

    ``signal`` None, or a signal whose three ``est`` values are all None -> exactly
    ``NO_SIGNAL_LINE`` as the whole block. Else: an ``- ideal:`` line from ``pick_ideal``, then
    one line per harness in ``HARNESS_ORDER``. A present slot entry renders the model id, the
    command (its ``command_template`` with ``{model}`` and ``<task>`` filled — ``<task>`` is
    the sanitized title), and the est text; a None entry renders ``- <harness>: <EST_NA>`` with
    NO command and NO model id (never guessed). An ``opus`` model-hint appends
    ``OPUS_SLOT_NOTE`` as the block's last line."""
    if signal is None:
        return NO_SIGNAL_LINE
    harnesses = signal.get("harnesses") or {}

    if all((harnesses.get(h) or {}).get("est") is None for h in HARNESS_ORDER):
        return NO_SIGNAL_LINE

    slot = pick_slot(card)
    entries = {}
    for h in HARNESS_ORDER:
        entry = None
        est = (harnesses.get(h) or {}).get("est")
        if isinstance(est, dict):
            profile = est.get(EST_PROFILE)
            if isinstance(profile, dict):
                entry = profile.get(slot)
        entries[h] = entry if isinstance(entry, dict) else None

    harness, reason = pick_ideal(card, entries)
    lines = [f"{_IDEAL_PREFIX}{harness} — {reason}"]

    task = sanitize_title(card.get("title"))
    for h in HARNESS_ORDER:
        entry = entries[h]
        est_text = _est_text(h, entry) if entry is not None else None
        model = entry.get("model") if isinstance(entry, dict) else None
        if entry is None or est_text is None or model is None:
            lines.append(f"- {h}: {EST_NA}")
            continue
        template = (harnesses.get(h) or {}).get("command_template") or ""
        command = template.replace("{model}", str(model)).replace("<task>", task)
        lines.append(f"- {h} ({model}, {est_text}): `{command}`")

    if card.get("model_hint") == "opus":
        lines.append(OPUS_SLOT_NOTE)

    return "\n".join(lines)


# ---- rendering -------------------------------------------------------------------------------

def render_plan(for_date, as_of, cards, notes, signal, refresh_ids=None):
    """Render the pinned runbook file (D1). Deterministic: identical inputs -> identical bytes,
    with NO timestamp anywhere.

    ``as_of`` None -> ``- built-from: no digest``. Cards whose id is None get sequential
    ``R<n>`` ids continuing after the highest existing numeric id (a fresh build starts at
    ``R1``); cards with ids keep them. A card's Harness block is recomposed via
    ``compose_harness_block`` when it is new (id was None), or ``refresh_ids`` is None (refresh
    all), or its id is in ``refresh_ids`` — but only when ``signal`` is not None; otherwise its
    existing ``harness`` text is kept verbatim (a None signal never downgrades an existing
    block; a new card under a None signal gets ``NO_SIGNAL_LINE``). ``## Notes`` renders only
    when ``notes`` is non-empty."""
    max_id = 0
    for card in cards:
        n = _id_num(card.get("id"))
        if n is not None and n > max_id:
            max_id = n
    next_id = max_id + 1

    prepared = []
    for card in cards:
        c = dict(card)
        was_new = c.get("id") is None
        if was_new:
            c["id"] = f"R{next_id}"
            next_id += 1
        recompose = signal is not None and (
            was_new or refresh_ids is None or c["id"] in refresh_ids
        )
        if recompose:
            c["harness"] = compose_harness_block(c, signal)
        elif was_new and signal is None:
            c["harness"] = NO_SIGNAL_LINE
        prepared.append(c)

    lines = [f"{_H1_PREFIX}{for_date}", ""]
    lines.append(f"- schema: {PLAN_SCHEMA}")
    if as_of is None:
        lines.append("- built-from: no digest")
    else:
        lines.append(f"- built-from: digest {as_of}")
    lines.append("")
    lines.append(ADVISORY_LINE)
    lines.append("")
    lines.append(_TASKS_HEADING)
    lines.append("")

    for c in prepared:
        box = "[x]" if c["checked"] else "[ ]"
        lines.append(f"### {box} {c['id']} — {c['title']}")
        lines.append("")
        lines.append(f"- source: {c['source']}")
        lines.append(f"- due: {c['due']}")
        lines.append(f"- first-planned: {c['first_planned']}")
        lines.append(f"- model-hint: {c['model_hint']}")
        if c.get("deferred_to"):
            lines.append(f"- deferred-to: {c['deferred_to']}")
        lines.append("")
        lines.append(_WHATHOW_HEADING)
        lines.extend((c["how"] or "").split("\n"))
        lines.append("")
        lines.append(_HARNESS_HEADING)
        lines.extend((c["harness"] or "").split("\n"))
        lines.append("")

    if notes:
        lines.append(_NOTES_HEADING)
        for note in notes:
            lines.append(f"- {note}")
        lines.append("")

    return "\n".join(lines)


# ---- single-card text mutations --------------------------------------------------------------

def mark_done(text, card_id):
    """Flip exactly ``card_id``'s ``### [ ]`` to ``### [x]`` -> new text. An unknown id or an
    already-done card raises ``ValueError`` naming the id."""
    lines = text.split("\n")
    unchecked = f"### [ ] {card_id} — "
    checked = f"### [x] {card_id} — "
    for i, line in enumerate(lines):
        if line.startswith(unchecked):
            lines[i] = "### [x] " + line[len("### [ ] "):]
            return "\n".join(lines)
        if line.startswith(checked):
            raise ValueError(f"card {card_id} is already done")
    raise ValueError(f"card {card_id} not found")


def set_deferred(text, card_id, to_date):
    """Add or update ``card_id``'s ``- deferred-to: <to_date>`` line, placed immediately after
    the card's last field line -> new text. An unknown id raises ``ValueError`` naming the id."""
    lines = text.split("\n")
    header_idx = None
    for i, line in enumerate(lines):
        if (line.startswith(f"### [ ] {card_id} — ")
                or line.startswith(f"### [x] {card_id} — ")):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError(f"card {card_id} not found")

    field_end = None       # index just after the card's last field line
    deferred_idx = None
    i = header_idx + 1
    while i < len(lines):
        line = lines[i]
        if line.startswith("### ") or line.startswith("## ") or line.startswith("**"):
            break
        if line.startswith("- "):
            field_end = i + 1
            if line.startswith("- deferred-to: "):
                deferred_idx = i
        i += 1

    new_line = f"- deferred-to: {to_date}"
    if deferred_idx is not None:
        lines[deferred_idx] = new_line
    elif field_end is not None:
        lines.insert(field_end, new_line)
    else:
        lines.insert(header_idx + 1, new_line)
    return "\n".join(lines)


# ---- check / carry read-only scans -----------------------------------------------------------

def _parse_ideal(harness_text):
    """The ideal harness name parsed from a card's harness body: the text after ``- ideal: ``
    up to the ` — ` separator when that line exists, else None."""
    for line in (harness_text or "").split("\n"):
        if line.startswith(_IDEAL_PREFIX):
            rest = line[len(_IDEAL_PREFIX):]
            if " — " in rest:
                return rest.split(" — ", 1)[0].strip()
            return rest.strip()
    return None


def check_cards(plan_dir, today):
    """Scan ``<plan_dir>/*.md`` (ALL valid-stem dates) for cards due on/before ``today`` ->
    ``(rows, notes)`` (D5).

    Cards are deduped by ``dedup_key`` keeping the LATEST-stem occurrence (the authoritative
    state — the double-reporting guard). For each survivor ``effective_due = deferred_to or the
    file stem``; unchecked cards with ``effective_due <= today`` become rows
    ``{"handle": "<stem>/<id>", "title", "effective_due", "overdue": effective_due < today,
    "ideal": <harness-or-None>}`` sorted by ``(effective_due, handle)``. A non-date file other
    than ``seed.md`` gets one note each."""
    plan_dir = Path(plan_dir)
    notes = []
    chosen = {}   # dedup_key -> (stem, card)
    for path in sorted(plan_dir.glob("*.md")):
        if path.name == SEED_FILENAME:
            continue
        stem = path.stem
        if not PLAN_STEM_RE.match(stem):
            notes.append(f"skipped non-date file in plan dir: {path.name}")
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError as e:
            notes.append(f"unreadable plan file {path.name}: {e}")
            continue
        for card in parse_plan(text)["cards"]:
            key = dedup_key(card)
            if key not in chosen or stem > chosen[key][0]:
                chosen[key] = (stem, card)

    rows = []
    for stem, card in chosen.values():
        if card["checked"]:
            continue
        effective_due = card["deferred_to"] or stem
        if not (effective_due <= today):
            continue
        rows.append({
            "handle": f"{stem}/{card['id']}",
            "title": card["title"],
            "effective_due": effective_due,
            "overdue": effective_due < today,
            "ideal": _parse_ideal(card["harness"]),
        })
    rows.sort(key=lambda r: (r["effective_due"], r["handle"]))
    return rows, notes


# ---- enrichment prompt (in-session; this module never dispatches it) -------------------------

ENRICH_HEADER = (
    "You are enriching a next-day runbook for a human operator. Rewrite ONLY the content\n"
    "under each open card's **What/How:** heading into 2-6 concrete, numbered steps: what\n"
    "to do, which file or path to start in, the exact command to run first, and how to\n"
    "verify it worked. Use ONLY facts present in the runbook and digest below — do not\n"
    "invent files, flags, model ids, or costs; where a fact is absent, keep the step\n"
    "general rather than guessing. Reproduce every other line byte-identical: the H1, all\n"
    "headings, checkboxes, field lines (source/due/first-planned/model-hint/deferred-to),\n"
    "and every **Harness:** block including its commands and estimates. Do not add,\n"
    "remove, or reorder cards. Nothing here auto-executes — the runbook is instructions a\n"
    "human chooses to run.\n"
)


def build_enrich_prompt(plan_text, digest):
    """Build the pinned in-session enrichment prompt (pure) -> str.

    Printed by the ``prompt`` subcommand; NEVER dispatched (this module never spawns a
    process at all). ``digest`` is a dict (its compact JSON is embedded for extra context) or
    None (an honest "no digest" line takes its place)."""
    text = ENRICH_HEADER + "\nRunbook:\n```markdown\n" + plan_text + "\n```\n\n"
    if isinstance(digest, dict):
        compact = json.dumps(digest, indent=None, separators=(",", ":"))
        text += "Digest (JSON):\n```json\n" + compact + "\n```\n\n"
    else:
        text += "No digest is available for extra context.\n\n"
    text += "Respond with ONLY the full revised markdown document.\n"
    return text


# ---- date helpers (journal_summarize.py semantics, replicated by copy) ------------------------

def _resolve_date_str(date_arg, utc):
    """Explicit ``--date`` wins (validated); else today, in UTC when ``utc`` is set."""
    if date_arg is not None:
        try:
            return date.fromisoformat(date_arg).isoformat()
        except ValueError:
            sys.exit(f"invalid --date (want YYYY-MM-DD): {date_arg}")
    if utc:
        return datetime.now(timezone.utc).date().isoformat()
    return date.today().isoformat()


def _next_date(date_str):
    """The next calendar date after ``date_str`` (month/year rollover safe via
    ``date.fromisoformat`` + ``timedelta`` — never string arithmetic); returns the input
    unchanged if it is not a parseable date."""
    try:
        d = date.fromisoformat(str(date_str))
    except ValueError:
        return str(date_str)
    return (d + timedelta(days=1)).isoformat()


def _validate_date_stem(value, flag):
    """Validate a user-supplied date flag (``--for``/``--to``) with ``date.fromisoformat`` AND
    ``PLAN_STEM_RE`` BEFORE any path is composed from it (the ``write_snapshot`` precedent —
    nothing may escape the plan dir). Returns ``value`` unchanged on success; rejects via
    ``sys.exit`` otherwise."""
    try:
        date.fromisoformat(value)
    except ValueError:
        sys.exit(f"invalid {flag} (want YYYY-MM-DD): {value}")
    if not PLAN_STEM_RE.match(value):
        sys.exit(f"invalid {flag} (want YYYY-MM-DD): {value}")
    return value


def _list_plan_files(plan_dir):
    """Sorted plan-file names present in ``plan_dir`` (``[]`` when the dir does not exist) —
    used to build a useful error message for an unknown ``done``/``defer`` target."""
    if not plan_dir.is_dir():
        return []
    return sorted(p.name for p in plan_dir.glob("*.md"))


# ---- CLI ---------------------------------------------------------------------------------

def _add_common_args(sp):
    sp.add_argument("--journal-dir", default=str(PLUGIN_ROOT / "journal"),
                    help="journal root (writes land ONLY under <journal-dir>/plan/)")
    sp.add_argument("--date", default=None,
                    help="as-of date, YYYY-MM-DD (default: today)")
    sp.add_argument("--utc", action="store_true",
                    help="resolve the default date in UTC (tests/verifies use it)")


def _cmd_build(args):
    as_of = _resolve_date_str(args.date, args.utc)
    for_date = (_validate_date_stem(args.for_date, "--for")
                if args.for_date is not None else _next_date(as_of))

    journal_dir = Path(args.journal_dir)
    plan_dir = journal_dir / PLAN_DIRNAME
    notes = []

    digest_path = journal_dir / as_of / "digest.json"
    digest = None
    if digest_path.is_file():
        try:
            digest = json.loads(digest_path.read_text(errors="replace"))
        except (OSError, ValueError):
            digest = None
    if digest is None:
        notes.append(
            f"no digest for {as_of} — kit/inbox/wip signals unavailable; "
            "run journal_collect.py first"
        )

    pc = cr.load_pricing()
    pco = cu.load_pricing()
    pcx = cxu.load_pricing()
    try:
        signal = ja.build_harness_signal((digest or {}).get("sources") or {}, pc, pco, pcx)
    except Exception as e:  # advisory must never break a build
        signal = None
        notes.append(f"advisor failed: {e!r}")

    seed_path = plan_dir / SEED_FILENAME
    seeds = []
    if seed_path.is_file():
        try:
            seeds = parse_seeds(seed_path.read_text(errors="replace"))
        except OSError:
            seeds = []

    carried, carry_notes = collect_carry(plan_dir, for_date)
    notes.extend(carry_notes)

    new_cards, assemble_notes = assemble_cards(digest, seeds, carried, for_date)
    notes.extend(assemble_notes)

    target_path = plan_dir / f"{for_date}.md"
    built_from = as_of if digest is not None else None

    if target_path.is_file():
        existing_cards = parse_plan(target_path.read_text(errors="replace"))["cards"]
        final_cards, refresh_ids = merge_cards(existing_cards, new_cards)
        rendered = render_plan(for_date, built_from, final_cards, notes, signal,
                               refresh_ids=refresh_ids)
    else:
        final_cards = new_cards
        rendered = render_plan(for_date, built_from, final_cards, notes, signal,
                               refresh_ids=None)

    try:
        plan_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        sys.exit(f"cannot create plan dir {plan_dir}: {e}")
    try:
        target_path.write_text(rendered)
    except OSError as e:
        sys.exit(f"cannot write runbook {target_path}: {e}")

    open_n = sum(1 for c in final_cards if not c["checked"])
    done_n = sum(1 for c in final_cards if c["checked"])
    print(
        f"runbook written: {target_path} — {open_n} open ({len(carried)} carried), "
        f"{done_n} done"
    )
    if args.print:
        print(rendered)
    return 0


def _cmd_check(args):
    today = _resolve_date_str(args.date, args.utc)
    plan_dir = Path(args.journal_dir) / PLAN_DIRNAME
    rows, notes = check_cards(plan_dir, today)

    lines = []
    if rows:
        lines.append(f"# Runbook check — {today}")
        lines.append("")
        for r in rows:
            tag = (f"OVERDUE since {r['effective_due']}" if r["overdue"]
                   else f"DUE {r['effective_due']}")
            ideal = r["ideal"] or "n/a"
            lines.append(f"{tag}  [{r['handle']}]  {r['title']}  (ideal: {ideal})")
        lines.append("")
        due_today = sum(1 for r in rows if not r["overdue"])
        overdue = sum(1 for r in rows if r["overdue"])
        lines.append(f"{due_today} due today, {overdue} overdue")
        lines.append("mark done: python3 bin/journal_plan.py done <id> --date <file-date>")
    else:
        lines.append(
            f"no runbook cards due for {today} — build one: python3 bin/journal_plan.py build"
        )
    for note in notes:
        lines.append(f"note: {note}")
    print("\n".join(lines))
    return 0


def _cmd_done(args):
    plan_dir = Path(args.journal_dir) / PLAN_DIRNAME
    file_date = _resolve_date_str(args.date, args.utc)
    target_path = plan_dir / f"{file_date}.md"
    existing = _list_plan_files(plan_dir)
    if not target_path.is_file():
        sys.exit(
            f"no runbook file for {file_date} at {target_path} — "
            f"plan files present: {existing}"
        )
    text = target_path.read_text(errors="replace")
    try:
        new_text = mark_done(text, args.id)
    except ValueError as e:
        sys.exit(f"{e} in {target_path} — plan files present: {existing}")
    card = next((c for c in parse_plan(text)["cards"] if c["id"] == args.id), None)
    title = card["title"] if card else ""
    target_path.write_text(new_text)
    print(f"done: [{file_date}/{args.id}] {title}")
    return 0


def _cmd_defer(args):
    _validate_date_stem(args.to_date, "--to")
    plan_dir = Path(args.journal_dir) / PLAN_DIRNAME
    file_date = _resolve_date_str(args.date, args.utc)
    target_path = plan_dir / f"{file_date}.md"
    existing = _list_plan_files(plan_dir)
    if not target_path.is_file():
        sys.exit(
            f"no runbook file for {file_date} at {target_path} — "
            f"plan files present: {existing}"
        )
    text = target_path.read_text(errors="replace")
    try:
        new_text = set_deferred(text, args.id, args.to_date)
    except ValueError as e:
        sys.exit(f"{e} in {target_path} — plan files present: {existing}")
    card = next((c for c in parse_plan(text)["cards"] if c["id"] == args.id), None)
    title = card["title"] if card else ""
    target_path.write_text(new_text)
    print(f"deferred to {args.to_date}: [{file_date}/{args.id}] {title}")
    return 0


def _cmd_prompt(args):
    as_of = _resolve_date_str(args.date, args.utc)
    for_date = (_validate_date_stem(args.for_date, "--for")
                if args.for_date is not None else _next_date(as_of))

    journal_dir = Path(args.journal_dir)
    plan_dir = journal_dir / PLAN_DIRNAME
    target_path = plan_dir / f"{for_date}.md"
    if not target_path.is_file():
        sys.exit(
            f"no runbook file at {target_path} — build one first: "
            "python3 bin/journal_plan.py build"
        )
    plan_text = target_path.read_text(errors="replace")

    digest_path = journal_dir / as_of / "digest.json"
    digest = None
    if digest_path.is_file():
        try:
            digest = json.loads(digest_path.read_text(errors="replace"))
        except (OSError, ValueError):
            digest = None

    print(build_enrich_prompt(plan_text, digest))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Next-day runbook: 'build' writes a dated, checkable plan of next-day "
                    "tasks with ready-to-paste per-harness commands; 'check'/'done'/'defer' "
                    "track it; 'prompt' prints the in-session enrichment prompt. Advisory "
                    "only — this CLI never spawns a harness, a model, or any process at all.")
    sub = ap.add_subparsers(dest="command", required=True)

    build_p = sub.add_parser(
        "build", help="build/rebuild the runbook (default target: the day after --date)")
    _add_common_args(build_p)
    build_p.add_argument("--for", dest="for_date", default=None,
                         help="due date to build for, YYYY-MM-DD (default: day after --date)")
    build_p.add_argument("--print", action="store_true",
                         help="also print the full rendered runbook")

    check_p = sub.add_parser("check", help="list runbook cards due today or overdue")
    _add_common_args(check_p)

    done_p = sub.add_parser("done", help="check off a card")
    _add_common_args(done_p)
    done_p.add_argument("id", help="card id, e.g. R1")

    defer_p = sub.add_parser("defer", help="defer a card to a later due date")
    _add_common_args(defer_p)
    defer_p.add_argument("id", help="card id, e.g. R1")
    defer_p.add_argument("--to", dest="to_date", required=True,
                         help="new due date, YYYY-MM-DD")

    prompt_p = sub.add_parser(
        "prompt", help="print the pinned in-session enrichment prompt (spawns nothing)")
    _add_common_args(prompt_p)
    prompt_p.add_argument("--for", dest="for_date", default=None,
                          help="runbook date to enrich, YYYY-MM-DD (default: day after --date)")

    args = ap.parse_args(argv)

    if args.command == "build":
        return _cmd_build(args)
    if args.command == "check":
        return _cmd_check(args)
    if args.command == "done":
        return _cmd_done(args)
    if args.command == "defer":
        return _cmd_defer(args)
    return _cmd_prompt(args)


if __name__ == "__main__":
    sys.exit(main())
