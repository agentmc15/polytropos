#!/usr/bin/env python3
"""Context weight — measure what actually fills the context window, per API call.

The reframe this tool is built on (see ``.claude/kits/context-weight/PLAN.md`` for the full
architecture): a user asking "lower cache reads" is usually looking at the wrong number.
Caching is the cheap path working correctly — reading 121M cached tokens for $60.70 instead
of ~$607 uncached is a 10x win, not a misconfiguration. The real driver of API-equivalent
spend is **resident context x number of API calls**: a session that re-submits ~463K tokens
of accumulated context on every one of 262 calls burns money on repetition, not on the cache
mechanism. This tool measures that resident mass, call by call, per harness — and does NOT
re-optimize config surfaces (CLAUDE.md, AGENTS.md, copilot-instructions.md), because those are
already under 1% of the observed working set on the motivating session.

All seven subcommands are implemented (``session``, T1-T4/T13; ``overview``, T5; ``audit``, T6;
``watch``, T10; ``demo``, T7; ``constraints``, U2 of the evidence-loop kit):

  session   Per-session context-weight card for one harness: the growth curve of submitted
            context across calls, inferred compaction points (Claude), the sidechain
            (subagent) mass split out from the main curve (Claude), and a "context carry
            cost" — the session's measured usage priced with OUTPUT ZEROED, so the dollar
            figure reflects context carried forward rather than work produced.
            ``--harness copilot`` gets a session-average card instead of a curve (D3 — see
            below); it can never support a growth curve or content attribution.
  overview  Cross-session working-set table across a window of days (``--days``, default 7),
            ONE SECTION PER HARNESS, built by calling each harness's own ``session`` card
            builder once per matching transcript/rollout/session and aggregating what THOSE
            already-computed cards return (never a second, divergent implementation of curve
            or pricing math). Each section carries that harness's own carry-cost line, priced
            only from that harness's own measured usage via that harness's own pricing file
            (D5) — there is NO cross-harness dollar total anywhere in ``overview``'s output,
            because the three harnesses do not measure the same thing (D3): Claude gets a
            real per-session growth summary, Codex gets curve points without content
            provenance, Copilot gets a session-average weight with no curve at all. A harness
            whose home directory is entirely absent prints one clean "not found" line for its
            own section while the other sections still render; exit 0 either way.
  audit     Resident-surface (always-loaded file) audit against a token budget — CLAUDE.md,
            AGENTS.md, copilot-instructions.md, plus any ``--surface`` extras. Tokens only,
            NEVER dollars (D5 — these are byte-derived estimates, not measured usage). Prints a
            fixed line naming what's resident but unmeasurable from files (system prompt, tool
            schemas, plugin skill listings, MCP definitions), and prints the reframe line
            UNCONDITIONALLY, first, right under the title, so it cannot be mistaken for a
            footnote: when ``--session`` is supplied it is a COMPUTED percentage of that
            session's measured avg per-call weight; without a session (the common, bare-run
            case) it falls back to a qualitative line naming the same lever without inventing a
            number. This is the kit's founding measurement turned into a running argument
            against itself: the audit exists to stop config-tweaking
            theater, not to invite it.
  watch     The live question, Claude-only (D3/D15): current weight, percent of the model's
            context window (resolved from ``data/pricing.json``, never hardcoded), and a
            three-class split of what's currently in the window — prunable (safe to drop
            without losing anything), load-bearing (would cost accuracy if dropped), and an
            honest unknown remainder — plus a recommendation keyed to the D14 prevent/prune
            ladder. There is no ``--harness`` flag; a Codex/Copilot invocation (an optional
            ``codex``/``copilot`` positional, default ``claude``) prints the pinned refusal
            line and exits 0. Never claims to delete anything (D13) — only the harness's own
            compaction/context-editing can actually remove content.
  constraints  Whether GUARDRAILS.md content for one kit dir (``--kit``) is resident in the
            reconstructed window, at what estimated weight, and how that weight trends across
            the session's growth curve (evidence-loop kit U2, PLAN E1) — the MEASUREMENT half
            of constraint survival. The enforcement half is U1's execute-skill rule, which
            guarantees a fences re-read at every PHASE START and says plainly that the skill
            cannot detect compaction (a post-compaction re-read is an opportunistic extra,
            never coverage) — so a mid-phase compaction can legitimately show a NO here, and
            the card says so. This module never re-asserts or injects anything itself (analysis
            never becomes behavior). Claude-only, same D3 rung as ``watch`` — a
            ``--harness codex``/``copilot`` invocation prints the bespoke, subcommand-named
            ``CONSTRAINTS_REFUSAL_LINE`` (``watch``'s own precedent) and exits 0. The same
            residency computation is also available as a section of ``audit`` via its own
            ``--kit`` flag.
  demo      Synthetic, self-contained smoke across all four cards above (session/overview/
            audit — ``watch`` is a live-only view over the same fixtures and is not part of
            this smoke) plus two ``constraints`` cards (one synthetic session that reads
            GUARDRAILS.md and stays resident, one that never reads it at all) — builds a fake
            Claude transcript, Codex rollout, Copilot session, audited project, and a synthetic
            kit dir inside one throwaway temp dir (never touching a real harness home), runs the
            real pipeline against them, prints all cards in order, and exits 0. Model ids are
            resolved at run time from the three pricing files, never hardcoded.

Per-harness honesty ladder (binding, PLAN D3 — never fabricate a number the logs don't carry):
  - Claude carries full per-call usage (input / cache_read / cache_write / output) plus tool
    content, so it gets full fidelity: a real growth curve, inferred compactions, and content
    attribution (D4 — see below).
  - Codex's rollout logs carry per-turn or cumulative-snapshot token COUNTS only, no content
    provenance — curve fidelity WITHOUT attribution: ``session --harness codex`` plots a real
    growth curve (per-turn weights, or cumulative snapshots when only ``total_token_usage``
    exists) but NEVER a ranked "what filled the window" table — that would require content this
    harness's logs do not carry. Its "what's in this rollout" signal is a per-record-type
    BYTE-SHARE table (sizes, not content) under the verbatim line pinned in
    ``CODEX_NO_PROVENANCE_LINE`` below (see the Codex pure-function section).
  - Copilot's events carry per-turn OUTPUT tokens only; the full input/cache_read/cache_write
    split exists ONLY as a cumulative ``session.shutdown`` ``tokenDetails`` snapshot — no
    per-turn input/cache breakdown exists at all, so a growth curve is impossible to compute
    honestly. ``session --harness copilot`` therefore gets session-average fidelity: one
    ``session-average weight = (input + cache_read + cache_write) / assistant turns`` figure
    plus the verbatim ``COPILOT_NO_CURVE_LINE`` — never a curve, never content attribution (see
    the Copilot pure-function section).
This module implements the Claude, Codex, and Copilot rungs of that ladder.

Attribution (D4): ``attribute_growth`` ranks what actually added to the window between two
measured points — tool_result/attachment/plain-text content, sized by SERIALIZED CHARACTER
LENGTH -> ``est.`` tokens at ``EST_CHARS_PER_TOKEN``, grouped by the tool that produced it (via
the preceding ``tool_use`` block) — and reconciles that ranked total against the session's
MEASURED growth (last weight - first weight + recovered-by-compaction mass), with any gap
printed as an explicit ``unattributed growth`` row rather than silently forced to balance.
Every estimated figure is labeled ``est.`` and is NEVER priced — attribution answers "what was
biggest", never "what did it cost"; dollars stay exclusively in the carry-cost line above,
which prices only measured (not estimated) tokens.

T13 extension: every assistant reply (text, thinking, and ``tool_use`` JSON) is appended to the
message array and re-submitted on the next call, so by D2's own definition it IS context
growth — and unlike the ``est.`` rows above, it is already an EXACT ``output_tokens`` count in
the transcript, needing no byte heuristic. ``assistant output (measured)`` is therefore its own
row, labeled ``measured`` (never ``est.``, never priced), ranked INLINE by size alongside the
``est.`` rows rather than appended after them, and subtracted from ``unattributed`` before that
remainder is computed. The ``unattributed growth`` row is likewise ranked inline by its own
magnitude (keeping a ``"—"`` rank marker) instead of always printing last, so a reader never
scans a ranked list top-to-bottom only to meet a larger unknown at the bottom.

Context weight (D2): for one API call, ``weight = input + cache_read + cache_write`` — the
full prompt actually submitted for that call. Output tokens are excluded from weight (they are
generation, not carried context) but are still reported alongside it.

Compactions/clears are INFERRED (D6), never read off a reliable marker (none exists in every
transcript): a call whose weight drops by >= ``DROP_FRACTION`` from the previous call's weight
is flagged an inferred compaction/clear point. A record carrying a truthy ``isCompactSummary``
is additionally noted as a confirmed marker where present. The word "inferred" always appears
next to the former; it is never conflated with the latter.

Sidechain mass (D7): Claude records with a truthy top-level ``isSidechain``, and every record
that arrived via a delegated subagent's own transcript file, are excluded from the main curve
and averages and rolled into one separate line (call count, total weight, share of session
mass) — subagent context is disposable by design, and mixing it into the driver's curve would
hide the payoff of delegating in the first place.

Dollars (D5): the "context carry cost" line prices ONLY measured usage tokens, via
``cr.price`` against ``data/pricing.json``, with output zeroed out — never priced tokens that
were only estimated from byte length (that facility lands with content attribution in a later
task) and never a total that crosses harnesses. The label
"API-equivalent dollars — an estimate, not a bill." always accompanies it.

Reuse, never re-implement (D5/Repo facts): every byte of transcript parsing, model matching,
and pricing math is delegated to the four existing engines below via the importlib pattern in
``bin/session_cost.py`` lines 56-63 — this module is never allowed to walk
``message.usage``/rollout wrapper keys/``session.shutdown`` snapshots itself.

Strictly read-only (D8): every ingestion path here opens ``.jsonl`` files for reading only.
Nothing under this module ever opens a ``*.db``, writes outside stdout, or invokes the real
``claude``/``codex``/``copilot`` CLI. ``DEFAULT_PROJECTS_DIR``, ``DEFAULT_CODEX_HOME``, and
``DEFAULT_COPILOT_HOME`` are the ONLY ``Path.home()`` uses in this file; every test and every
verify command overrides them via ``--projects-dir``/``--codex-home``/``--copilot-home``.

Usage:
  context_weight.py session  [--harness claude|codex|copilot] [--session ID] [--top N]
                             [--projects-dir DIR] [--tasks-dir DIR ...] [--no-subagents]
                             [--codex-home DIR] [--copilot-home DIR] [--json]
  context_weight.py overview [--harness all|claude|codex|copilot] [--days N] [--top N]
                             [--projects-dir DIR] [--codex-home DIR] [--copilot-home DIR]
                             [--json]
  context_weight.py audit    [--project DIR] [--surface PATH ...] [--budget-tokens N]
                             [--session ID] [--kit DIR] [--projects-dir DIR] [--json]
  context_weight.py watch    [claude|codex|copilot] [--session ID] [--window-tokens N]
                             [--projects-dir DIR] [--tasks-dir DIR ...] [--json]
                             # Claude-only (no --harness); codex/copilot print the pinned
                             # refusal line and exit 0.
  context_weight.py constraints --kit DIR [--harness claude|codex|copilot] [--session ID]
                             [--projects-dir DIR] [--tasks-dir DIR ...] [--no-subagents]
                             [--json]
                             # Claude-only fidelity; codex/copilot print the bespoke
                             # CONSTRAINTS_REFUSAL_LINE and exit 0.
  context_weight.py demo     [--json]     # synthetic, self-contained, touches no real data
"""

import argparse
import importlib.util
import json
import os
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------------------------
# Sanctioned constants (PLAN D9). Token counts and ratios of tokens are data-design knobs;
# prices, price ratios, cache multipliers, and real model ids are NEVER hardcoded here — those
# always come from data/pricing.json (etc.) at run time via the reused engines below.

CW_SCHEMA_VERSION = 1
EST_CHARS_PER_TOKEN = 4
DROP_FRACTION = 0.5
DEFAULT_SURFACE_BUDGET_TOKENS = 5_000

# T10/D15 knobs for `watch`'s classify_prunable — same species as the four constants above
# (token counts and ratios of tokens are data-design knobs, never prices/model ids per D9).
#
# LARGE_TOOL_OUTPUT_EST_TOKENS reuses T2's own sizing heuristic (serialized bytes /
# EST_CHARS_PER_TOKEN — see attribute_growth/_serialize_len) rather than deriving a second one:
# a Bash tool_result at or above this many est. tokens is "large command output" per D15,
# classified prunable regardless of whether a later assistant message is already known to have
# acted on it.
LARGE_TOOL_OUTPUT_EST_TOKENS = 1_000

# LOAD_BEARING_MARKERS: the documented module-level constant the T10 brief requires in place of
# inline regex literals scattered through the classifier — a small, precision-biased,
# case-insensitive substring list. A match forces LOAD_BEARING, so a false positive is cheap
# (something safe just gets kept a little longer) while a false negative is not (something
# load-bearing gets offered up for pruning) — the list favors phrases that reliably STATE a
# standing decision or constraint ("never push to main", "must not ...") over words that merely
# discuss one in passing.
LOAD_BEARING_MARKERS = (
    "never ", "always ", "must not", "must never", "do not ", "don't ",
    "decided to", "decision:", "we agreed", "constraint:", "requirement:",
    "the plan is", "from now on", "going forward", "non-negotiable",
)

CARRY_COST_LABEL = "API-equivalent dollars — an estimate, not a bill."


# ---------------------------------------------------------------------------------------------
# Reuse, never re-implement: load the four existing engines by path (the session_cost.py
# _load_cost_report pattern, lines 56-63, copied verbatim in spirit).


def _load(name):
    spec = importlib.util.spec_from_file_location(name, PLUGIN_ROOT / "bin" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cr = _load("cost_report")     # Claude transcript parsing + pricing (extract_record, price, ...)
sc = _load("session_cost")    # session scoping (find_main_transcript, discover_task_dirs, ...)
cx = _load("codex_usage")     # Codex rollout parsing + pricing (a later task's territory)
cp = _load("copilot_usage")   # Copilot event parsing + pricing (a later task's territory)


# ---------------------------------------------------------------------------------------------
# Home-directory seams. Module-level Path.home() defaults ONLY — every test/verify overrides
# these via --projects-dir / --codex-home / --copilot-home (D8).


def _default_projects_dir():
    """Transcripts live under ``<config-dir>/projects``. Honors ``CLAUDE_CONFIG_DIR`` like
    ``session_cost._default_projects_dir`` / ``cost_report._default_projects_dir``."""
    cfg = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    base = Path(cfg).expanduser() if cfg else Path.home() / ".claude"
    return base / "projects"


DEFAULT_PROJECTS_DIR = _default_projects_dir()
DEFAULT_CODEX_HOME = Path.home() / ".codex"
DEFAULT_COPILOT_HOME = Path.home() / ".copilot"


# ---------------------------------------------------------------------------------------------
# Pure-function layer — Claude, full fidelity (D1/D2/D6/D7).


def claude_call_weights(objs):
    """Iterate parsed Claude transcript JSONL objects in file order.

    For every record ``cr.extract_record`` recognizes: weight = input + cache_read +
    cache_write (D2). Records carrying a truthy top-level ``isSidechain`` are excluded from the
    main curve and folded into one running aggregate (D7); the rest are appended, in order, to
    ``calls``. Message ids are deduped exactly like ``sc.collect`` — a message seen twice (e.g.
    the same line written twice, or the same message id echoed by a subsequent record) counts
    once, first occurrence wins.

    Returns ``(calls, sidechain, notes)``:
      - ``calls``: list of ``{"weight", "input", "cache_read", "cache_write", "output",
        "timestamp", "model"}``, in file order, sidechain records excluded.
      - ``sidechain``: ``{"calls": n, "weight": total}``.
      - ``notes``: list of ``{"index", "kind"}`` for main-curve calls whose record carried a
        truthy ``isCompactSummary`` — an opportunistic CONFIRMED compaction marker (index is
        the position of that call within ``calls``), separate from the inferred drops that
        ``detect_drops`` computes from the weight curve itself.
    """
    calls = []
    sidechain = {"calls": 0, "weight": 0}
    notes = []
    seen_ids = set()
    for obj in objs:
        if not isinstance(obj, dict):
            continue
        rec = cr.extract_record(obj)
        if rec is None:
            continue
        model, u, msg_id, _tool_uses = rec
        if msg_id:
            if msg_id in seen_ids:
                continue
            seen_ids.add(msg_id)
        weight = u["input"] + u["cache_read"] + u["cache_write"]
        if obj.get("isSidechain"):
            sidechain["calls"] += 1
            sidechain["weight"] += weight
            continue
        idx = len(calls)
        calls.append({
            "weight": weight,
            "input": u["input"],
            "cache_read": u["cache_read"],
            "cache_write": u["cache_write"],
            "output": u["output"],
            "timestamp": obj.get("timestamp"),
            "model": model,
        })
        if obj.get("isCompactSummary"):
            notes.append({"index": idx, "kind": "confirmed_compact_summary"})
    return calls, sidechain, notes


def detect_drops(weights):
    """Inferred compaction/clear points (D6): a call whose weight is < the previous call's
    weight * (1 - DROP_FRACTION), i.e. a drop of at least DROP_FRACTION. Returns
    ``[{"index", "before", "after"}, ...]`` in curve order. Purely a function of the weight
    sequence — the word "inferred" belongs on the CALLER's rendering, this just detects it."""
    drops = []
    for i in range(1, len(weights)):
        before = weights[i - 1]
        after = weights[i]
        if after < before * (1 - DROP_FRACTION):
            drops.append({"index": i, "before": before, "after": after})
    return drops


_SALIENT_FILE_TOOLS = ("Read", "Edit", "Write")


def _salient_for(tool_name, tool_input):
    """Salient descriptor for a tool_use block, per D4's pinned mapping. ``tool_input`` may be
    anything JSON put there; only a dict is trusted to carry the named field."""
    inp = tool_input if isinstance(tool_input, dict) else {}
    if tool_name in _SALIENT_FILE_TOOLS:
        return inp.get("file_path") or ""
    if tool_name == "Bash":
        return str(inp.get("command") or "")[:60]
    if tool_name == "Agent":
        return str(inp.get("prompt") or "")[:60]
    return ""


def _serialize_len(content):
    """Character length used for the bytes->est.-tokens heuristic: strings are measured as-is;
    anything else (dict/list/number/None) is measured via its JSON serialization, exactly like
    a transcript viewer would show it — this is a labeled ESTIMATE, never a token count."""
    if isinstance(content, str):
        return len(content)
    return len(json.dumps(content))


def attribute_growth(objs):
    """Rank what filled the window between two measured points (D4).

    Pass 1: build ``tool_use_id -> (tool_name, salient)`` from every non-sidechain assistant
    record's ``tool_use`` content blocks (salient per ``_salient_for``).

    Pass 2: size every ADDITION to the main window — a ``user`` record's ``tool_result``
    blocks (attributed to the tool that produced them via ``tool_use_id``; an id with no entry
    in the pass-1 map is attributed to tool ``(unknown)``), a ``user`` record's plain ``text``
    blocks (attributed to ``user input``), and an ``attachment`` record's serialized payload
    (attributed to ``attachment``) — each sized by ``_serialize_len(...) / EST_CHARS_PER_TOKEN``,
    rounded. Records carrying a truthy top-level ``isSidechain`` are skipped entirely in BOTH
    passes: their content never entered the main window, so it cannot have added to it.

    Entries aggregate by ``(tool_name, salient)`` and are returned ranked descending by
    estimated tokens. ``notes`` carries one entry per ``tool_result`` whose ``tool_use_id``
    had no pass-1 mapping (informational only — the entry itself still lands under
    ``(unknown)``).

    Returns ``(entries, notes)`` where each entry is
    ``{"tool", "salient", "est_tokens"}`` (NOT priced — D4/D5) and each note is
    ``{"kind": "unmapped_tool_use_id", "tool_use_id": ...}``.
    """
    tool_map = {}
    for obj in objs:
        if not isinstance(obj, dict) or obj.get("isSidechain"):
            continue
        if obj.get("type") != "assistant":
            continue
        msg = obj.get("message") if isinstance(obj.get("message"), dict) else None
        content = msg.get("content") if msg else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not (isinstance(block, dict) and block.get("type") == "tool_use"):
                continue
            tool_use_id = block.get("id")
            if not tool_use_id:
                continue
            name = block.get("name") or "(unknown)"
            tool_map[tool_use_id] = (name, _salient_for(name, block.get("input")))

    agg = defaultdict(int)
    notes = []
    for obj in objs:
        if not isinstance(obj, dict) or obj.get("isSidechain"):
            continue
        otype = obj.get("type")
        if otype == "user":
            msg = obj.get("message") if isinstance(obj.get("message"), dict) else None
            content = msg.get("content") if msg else None
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "tool_result":
                    tool_use_id = block.get("tool_use_id")
                    tokens = round(_serialize_len(block.get("content")) / EST_CHARS_PER_TOKEN)
                    key = tool_map.get(tool_use_id)
                    if key is None:
                        key = ("(unknown)", "")
                        if tool_use_id:
                            notes.append({
                                "kind": "unmapped_tool_use_id",
                                "tool_use_id": tool_use_id,
                            })
                    agg[key] += tokens
                elif btype == "text":
                    tokens = round(_serialize_len(block.get("text") or "") / EST_CHARS_PER_TOKEN)
                    if tokens:
                        agg[("user input", "")] += tokens
        elif otype == "attachment":
            tokens = round(
                _serialize_len(obj.get("attachment", obj)) / EST_CHARS_PER_TOKEN
            )
            if tokens:
                agg[("attachment", "")] += tokens

    entries = [
        {"tool": tool, "salient": salient, "est_tokens": tokens}
        for (tool, salient), tokens in agg.items()
        if tokens
    ]
    entries.sort(key=lambda e: -e["est_tokens"])
    return entries, notes


def _reconcile_growth(calls, drops, entries):
    """D4's pinned reconciliation formula, extended by T13 to fold in measured assistant
    output. ``measured_growth`` = the last call's weight minus the first, plus the mass
    recovered by every inferred compaction (each drop's before-after). ``assistant_output_measured``
    = the summed ``output`` of ``calls`` (the main, non-sidechain calls ``claude_call_weights``
    already returns) — every assistant reply (text, thinking, and ``tool_use`` JSON) is
    appended to the message array and re-submitted on the next call, so it IS context growth by
    D2's own definition, and it is already an EXACT ``output_tokens`` count — no byte heuristic,
    never run through ``EST_CHARS_PER_TOKEN``, never priced. ``unattributed`` = measured growth
    minus the ranked (est.) attribution total minus that measured assistant-output figure,
    FLOORED AT 0 with a flag when the combined total exceeds growth (estimates are estimates —
    never forced to a tidy total that hides the gap in either direction)."""
    weights = [c["weight"] for c in calls]
    if not weights:
        measured_growth = 0
    else:
        measured_growth = weights[-1] - weights[0] + sum(d["before"] - d["after"] for d in drops)
    attributed_total = sum(e["est_tokens"] for e in entries)
    assistant_output_measured = sum(c["output"] for c in calls)
    combined_total = attributed_total + assistant_output_measured
    exceeded = combined_total > measured_growth
    unattributed = max(0, measured_growth - combined_total)
    return {
        "measured_growth": measured_growth,
        "attributed_total": attributed_total,
        "assistant_output_measured": assistant_output_measured,
        "unattributed": unattributed,
        "attribution_exceeded_growth": exceeded,
    }


# ---------------------------------------------------------------------------------------------
# `watch`'s classifier (T10, PLAN D15). A pure function, independent of `attribute_growth` (that
# ranks WHAT filled the window; this decides what's safe to drop from it) but built the same
# way: pass 1 maps tool_use_id -> (tool, salient) from assistant tool_use blocks; pass 2 walks
# the content that pass 1 makes sense of. Sidechain records are skipped — their content never
# entered the main window (D7), so it cannot be prunable, load-bearing, OR unknown from the
# main driver's point of view.
#
# Same defect class as the avoidable-mass line above (see the comment ahead of
# `_build_attribution_section`): a full transcript can span MULTIPLE compactions, so records
# before the last one describe session HISTORY, not the live window. `classify_prunable` must
# only ever classify content that is actually resident right now — `_resident_window_records`
# scopes its input to that slice before any classification happens.


def _has_load_bearing_marker(text):
    lowered = (text or "").lower()
    return any(marker in lowered for marker in LOAD_BEARING_MARKERS)


def _resident_window_records(records):
    """The subset of ``records`` at-or-after the LAST compaction/clear point — confirmed
    (``isCompactSummary``) or inferred (``detect_drops``), whichever call comes later — so a
    caller classifying "what's in the window right now" (``classify_prunable``, D15) never
    counts mass an earlier compaction already discarded (D6). A partition of the current window
    can never exceed the window itself; counting history alongside it breaks that invariant.

    Reuses ``claude_call_weights``/``detect_drops`` for the actual detection — this never
    re-derives drop math, it only slices the record stream at the boundary they already
    compute. The cutoff is located by TIMESTAMP (every call in ``claude_call_weights``' output
    carries the source record's own ``timestamp``) rather than by list position, because
    ``records`` here mixes ``user``/``assistant``/other record types that ``claude_call_weights``
    itself skips over — position in ``calls`` and position in ``records`` are not the same
    index space.

    Returns ``records`` unchanged when no compaction is detected at all (no inferred drop, no
    confirmed marker, or the cutoff call carries no timestamp to key off of) — the whole
    transcript IS the window, and callers keep their prior behavior exactly.

    Thin wrapper over ``_resident_window_slice`` (which additionally reports HOW the cutoff was
    detected); this signature and its behavior are unchanged.
    """
    return _resident_window_slice(records)[0]


def _resident_window_slice(records):
    """``(_resident_window_records(records), basis)`` — the resident slice PLUS how the cutoff
    that produced it was detected.

    ``basis`` is ``None`` when no compaction was detected (the slice is ``records`` unchanged),
    ``"confirmed"`` when the cutoff call carries an ``isCompactSummary`` marker, ``"inferred"``
    when it is only a ``detect_drops`` weight drop of at least ``DROP_FRACTION``, or
    ``"confirmed+inferred"`` when the same call is both.

    The distinction is load-bearing and must not be collapsed by callers (PLAN E4): a confirmed
    marker is a recorded FACT, a drop is an INFERENCE from the curve. ``render_session_markdown``
    already keeps them in separate "Inferred compactions" / "Confirmed compact-summary markers"
    sections; any caller that tells a reader WHY content left the window owes them the same
    distinction rather than asserting an inference as a known event.
    """
    calls, _sidechain, notes = claude_call_weights(records)
    inferred = {d["index"] for d in detect_drops([c["weight"] for c in calls])}
    confirmed = {
        nt["index"] for nt in notes if nt.get("kind") == "confirmed_compact_summary"
    }
    cutoff_call_indices = inferred | confirmed
    if not cutoff_call_indices:
        return records, None
    idx = max(cutoff_call_indices)
    cutoff_ts = calls[idx].get("timestamp")
    if not cutoff_ts:
        return records, None
    basis = "+".join(
        kind for kind, found in (("confirmed", confirmed), ("inferred", inferred))
        if idx in found
    )
    scoped = [
        o for o in records
        if isinstance(o, dict) and (o.get("timestamp") or "") >= cutoff_ts
    ]
    return scoped, basis


def classify_prunable(records):
    """Two-class-plus-honest-remainder split of what is CURRENTLY RESIDENT in the window (D15).

    Scopes ``records`` to ``_resident_window_records(records)`` first — everything at-or-after
    the last compaction/clear point — then delegates to ``_classify_prunable_over`` for the
    actual three-way split. When no compaction is detected, the scoped slice is ``records``
    unchanged, so behavior is identical to classifying the whole transcript. Kept as a thin
    wrapper (rather than folding the scoping into the walk below) so tests can call
    ``_classify_prunable_over`` directly on an UNSCOPED transcript to prove the scoping step is
    load-bearing — see ``PrunableWindowScopingTests`` in the test suite.
    """
    return _classify_prunable_over(_resident_window_records(records))


def _classify_prunable_over(records):
    """The unscoped three-way split ``classify_prunable`` performs once its input is already
    limited to the resident window (or is the whole transcript, when no compaction was found to
    scope past). Kept separate from ``classify_prunable`` purely so the window-scoping step
    above has something pure to delegate to and so regression tests can call this directly,
    unscoped, to demonstrate the bug the scoping wrapper fixes.

    Classifies three kinds of content found while walking non-sidechain ``records`` in file
    order: ``tool_result`` blocks (from ``user`` records), ``thinking`` blocks (from
    ``assistant`` records), and plain ``text`` blocks (from ``user`` records — this is the only
    unit that carries the "first message" / "decision marker" rules; assistant-authored text is
    already covered elsewhere, D2/T13's ``assistant output (measured)`` row, and is not
    reclassified here). Every item is sized the same way T2 sizes tool_result/text content
    (``_serialize_len(...) / EST_CHARS_PER_TOKEN`` — an ``est.`` figure, never priced).

    Classification order (first match wins — this is the documented precedence, not an
    accident of iteration):

      1. An error ``tool_result`` (``is_error`` truthy) with NO later ``tool_result`` for the
         SAME tool name that is NOT an error -> LOAD_BEARING ("unresolved error evidence").
      2. A ``Read`` ``tool_result`` whose ``salient`` (file_path) is the LAST read of that path
         in the transcript -> LOAD_BEARING ("most recent read of this path"). An earlier read of
         a path that IS read again later -> PRUNABLE ("superseded read").
      3. A ``Bash`` ``tool_result`` at or above ``LARGE_TOOL_OUTPUT_EST_TOKENS`` est. tokens ->
         PRUNABLE ("large command output"), regardless of rule 4 — sheer size is its own signal.
      4. Any other ``tool_result`` that has a LATER assistant record after it in the transcript
         (i.e., the conversation continued past it, so something acted on or moved past it) ->
         PRUNABLE ("acted on by a later assistant message").
      5. A ``tool_result`` with no later assistant record at all (the trailing edge of the
         transcript — not yet confirmed acted on) -> UNKNOWN.
      6. The FIRST ``user`` text block in the transcript -> LOAD_BEARING ("first user message").
      7. A later ``user`` text block containing a ``LOAD_BEARING_MARKERS`` substring ->
         LOAD_BEARING ("decision/constraint marker"). Without a marker -> UNKNOWN (an honest
         third bucket, D3/D10 — most later user turns are neither confirmed prunable nor a
         known constraint).
      8. A ``thinking`` block from any assistant call OTHER than the transcript's LAST assistant
         call -> PRUNABLE ("thinking from a completed call"). The LAST call's thinking -> UNKNOWN
         (too recent to know whether it was acted on).

    Returns ``(prunable, load_bearing, unknown)`` — three lists of
    ``{"kind", "tool", "salient", "est_tokens", "reason"}`` dicts. Never claims to delete
    anything (D13) — this is a classification, not an action; only the caller's rendering may
    say so in words, and it must say the opposite.
    """
    main = [o for o in records if isinstance(o, dict) and not o.get("isSidechain")]

    tool_map = {}
    assistant_positions = []
    for i, obj in enumerate(main):
        if obj.get("type") != "assistant":
            continue
        assistant_positions.append(i)
        msg = obj.get("message") if isinstance(obj.get("message"), dict) else None
        content = msg.get("content") if msg else None
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tid = block.get("id")
                if tid:
                    name = block.get("name") or "(unknown)"
                    tool_map[tid] = (name, _salient_for(name, block.get("input")))
    last_assistant_idx = assistant_positions[-1] if assistant_positions else None

    tool_results = []
    prunable, load_bearing, unknown = [], [], []
    first_user_message_seen = False

    for i, obj in enumerate(main):
        otype = obj.get("type")
        if otype == "user":
            msg = obj.get("message") if isinstance(obj.get("message"), dict) else None
            content = msg.get("content") if msg else None
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "tool_result":
                    tid = block.get("tool_use_id")
                    tool, salient = tool_map.get(tid, ("(unknown)", ""))
                    tokens = round(_serialize_len(block.get("content")) / EST_CHARS_PER_TOKEN)
                    tool_results.append({
                        "position": i, "tool": tool, "salient": salient,
                        "est_tokens": tokens, "is_error": bool(block.get("is_error")),
                    })
                elif btype == "text":
                    text = block.get("text") or ""
                    tokens = round(_serialize_len(text) / EST_CHARS_PER_TOKEN)
                    item = {"kind": "user_message", "tool": "user input", "salient": "",
                            "est_tokens": tokens}
                    if not first_user_message_seen:
                        first_user_message_seen = True
                        item["reason"] = "first user message of the session"
                        load_bearing.append(item)
                    elif _has_load_bearing_marker(text):
                        item["reason"] = "decision/constraint marker"
                        load_bearing.append(item)
                    else:
                        item["reason"] = "later user message, no marker"
                        unknown.append(item)
        elif otype == "assistant":
            msg = obj.get("message") if isinstance(obj.get("message"), dict) else None
            content = msg.get("content") if msg else None
            if not isinstance(content, list):
                continue
            is_last_call = (i == last_assistant_idx)
            for block in content:
                if not (isinstance(block, dict) and block.get("type") == "thinking"):
                    continue
                text = block.get("thinking") or ""
                tokens = round(_serialize_len(text) / EST_CHARS_PER_TOKEN)
                item = {"kind": "thinking", "tool": "(thinking)", "salient": "",
                        "est_tokens": tokens}
                if is_last_call:
                    item["reason"] = "most recent call — not yet confirmed acted on"
                    unknown.append(item)
                else:
                    item["reason"] = "thinking from a completed call"
                    prunable.append(item)

    last_read_position = {}
    for tr in tool_results:
        if tr["tool"] == "Read" and tr["salient"]:
            prev = last_read_position.get(tr["salient"])
            if prev is None or tr["position"] > prev:
                last_read_position[tr["salient"]] = tr["position"]

    for tr in tool_results:
        if not tr["is_error"]:
            continue
        tr["_has_retry"] = any(
            other["tool"] == tr["tool"] and other["position"] > tr["position"]
            and not other["is_error"]
            for other in tool_results
        )

    for tr in tool_results:
        item = {"kind": "tool_result", "tool": tr["tool"], "salient": tr["salient"],
                "est_tokens": tr["est_tokens"]}
        if tr["is_error"] and not tr.get("_has_retry", False):
            item["reason"] = "unresolved error — no later successful retry of this tool"
            load_bearing.append(item)
            continue
        if tr["tool"] == "Read" and tr["salient"]:
            if last_read_position.get(tr["salient"]) == tr["position"]:
                item["reason"] = "most recent read of this path"
                load_bearing.append(item)
            else:
                item["reason"] = "superseded read — a later read of the same path exists"
                prunable.append(item)
            continue
        if tr["tool"] == "Bash" and tr["est_tokens"] >= LARGE_TOOL_OUTPUT_EST_TOKENS:
            item["reason"] = (
                f"large command output (>= {LARGE_TOOL_OUTPUT_EST_TOKENS:,} est. tokens)"
            )
            prunable.append(item)
            continue
        has_later_assistant = any(pos > tr["position"] for pos in assistant_positions)
        if has_later_assistant:
            item["reason"] = "acted on by a later assistant message"
            prunable.append(item)
        else:
            item["reason"] = "most recent tool result — not yet confirmed acted on"
            unknown.append(item)

    return prunable, load_bearing, unknown


# ---------------------------------------------------------------------------------------------
# Session card assembly + rendering.


_SPARK_CHARS = "▁▂▃▄▅▆▇█"

# Phase 2-3 review addition #4: at 373 calls the un-downsampled sparkline was 373 chars wide,
# wrapped every terminal, and destroyed the plateau read that D12 practice #3 (compact when the
# curve plateaus) depends on. Capping at ~60 chars keeps the shape legible regardless of call
# count.
_SPARK_MAX_CHARS = 60


def _downsample(weights, n):
    """Bucket-average ``weights`` down to at most ``n`` points, preserving overall shape
    (plateaus, drops, ramps) while capping sparkline width. A no-op when ``weights`` already
    fits — the pinned T1 fixture (4 points) is untouched by this."""
    length = len(weights)
    if length <= n or n <= 0:
        return list(weights)
    bucket = length / n
    out = []
    for i in range(n):
        start = int(i * bucket)
        end = max(int((i + 1) * bucket), start + 1)
        chunk = weights[start:end]
        out.append(sum(chunk) / len(chunk))
    return out


def _sparkline(weights):
    if not weights:
        return ""
    sampled = _downsample(weights, _SPARK_MAX_CHARS)
    lo, hi = min(sampled), max(sampled)
    span = (hi - lo) or 1
    n = len(_SPARK_CHARS) - 1
    return "".join(_SPARK_CHARS[int((w - lo) / span * n)] for w in sampled)


def _select_row_indices(n, top):
    """Row indices for the compact table: everything when it already fits under ``top``;
    otherwise an evenly-spaced sample of ``top`` rows that always includes the first and last
    call (so a truncated table never hides where the session started or ended)."""
    if n <= 0:
        return []
    if top <= 0 or n <= top:
        return list(range(n))
    if top == 1:
        return [n - 1]
    interior = top - 2
    idxs = {0, n - 1}
    if interior > 0:
        step = (n - 1) / (interior + 1)
        for i in range(1, interior + 1):
            idxs.add(round(i * step))
    return sorted(idxs)


def _carry_cost(calls, pricing):
    """Measured usage priced with OUTPUT ZEROED (D5), grouped by pricing-matched model, summed
    across models, against the same calls' fully-priced (real output) total. Models that don't
    match any pricing.json key are simply excluded (consistent with the unpriced-model idiom
    used elsewhere in this repo) — never a crash, never a fabricated price."""
    by_model = defaultdict(lambda: {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0})
    for c in calls:
        key = cr.match_model(c["model"], pricing)
        if key is None:
            continue
        b = by_model[key]
        b["input"] += c["input"]
        b["output"] += c["output"]
        b["cache_read"] += c["cache_read"]
        b["cache_write"] += c["cache_write"]
    carry_usd = 0.0
    total_usd = 0.0
    for key, u in by_model.items():
        zeroed = dict(u)
        zeroed["output"] = 0
        carry_usd += cr.price(key, zeroed, None, pricing)
        total_usd += cr.price(key, u, None, pricing)
    pct = (carry_usd / total_usd * 100) if total_usd else 0.0
    return {
        "carry_usd": carry_usd,
        "session_total_usd": total_usd,
        "pct": pct,
        "label": CARRY_COST_LABEL,
    }


def _max_context_window(pricing):
    """Largest ``context_window`` across every model in ``pricing`` — runtime-derived from
    ``data/pricing.json``, never a literal. Used only as a best-effort fallback when a session's
    model doesn't match any pricing key (see ``_resolve_window_tokens``)."""
    windows = [m.get("context_window") or 0 for m in pricing.get("models", {}).values()]
    return max(windows) if windows else 0


def _resolve_window_tokens(pricing, model_id, override=None):
    """Context-window size in tokens, per the T10 brief: ALWAYS resolved from ``data/
    pricing.json``'s ``context_window`` field for the given model — never a hardcoded literal.
    ``override`` (the CLI ``--window-tokens`` flag) wins unconditionally when given. When
    ``model_id`` doesn't match any pricing key (unknown/missing model), falls back to the
    largest ``context_window`` present in the pricing file — still runtime-derived, just a
    best-effort choice rather than an exact match, and documented as such by the caller."""
    if override:
        return override
    key = cr.match_model(model_id, pricing) if model_id else None
    if key is not None:
        window = pricing["models"][key].get("context_window")
        if window:
            return window
    return _max_context_window(pricing)


def build_absent_session_card(harness, session_id, projects_dir):
    """Clean "nothing found" card (exit 0, never an error) for an absent projects dir or a
    session id with no matching transcript."""
    return {
        "schema_version": CW_SCHEMA_VERSION,
        "found": False,
        "harness": harness,
        "session_id": session_id,
        "message": (
            f"No {harness} transcript found for session {session_id or '(latest)'} "
            f"under {projects_dir}."
        ),
    }


ATTRIBUTION_BASIS = "bytes/4 heuristic — never priced"
UNATTRIBUTED_EXPLANATION = (
    "system overhead and tool schemas are not measurable from the transcript; "
    "assistant output (including thinking) is measured exactly and shown above."
)
ASSISTANT_OUTPUT_LABEL = "assistant output (measured)"

# Phase 2-3 review addition #3: the ranked table's top rows (assistant output, unattributed,
# user input) are all things a reader can't act on — reply, unknown-by-definition, and the
# user's own ask. What IS actionable is the tool-ingested mass underneath, so it gets pulled out
# as one derived line ABOVE the table rather than left to scroll past. "attachment" is excluded
# for the same reason as "user input": it is what the user handed over, not something a tool
# fetched that could have been capped or delegated.
_AVOIDABLE_EXCLUDED_TOOLS = {"user input", "attachment"}

# The avoidable-mass line's percentage MUST be against a WINDOW-SCALE quantity (a single call's
# resident content), never `total_submitted` (the CUMULATIVE sum of every call's fully
# resubmitted window across the whole session). Those are different units — total_submitted can
# run 100x+ larger than the window on a long session (every call resubmits the whole prompt) —
# and dividing a window-scale numerator by a cumulative-scale denominator silently rounds real,
# actionable mass down to 0%, recreating the exact "nothing to do" reading this line exists to
# fix. The peak call's weight IS the window-scale figure the card already computes elsewhere
# (`peak_weight`) — this recomputes the same max() locally so this function stays a pure
# transform of its own arguments.


def _build_attribution_section(calls, drops, entries, attr_notes, top=20):
    """The ``"attribution"`` card section (D4, extended by T13). The ranked table caps the
    (est.) tool-attribution rows at ``top``, then ALWAYS adds two more rows regardless of that
    cap: an ``ASSISTANT_OUTPUT_LABEL`` row sourced from the summed ``output`` of ``calls`` —
    labeled ``measured``, not ``est.``, because it comes straight from the transcript's own
    ``output_tokens`` count, never the byte heuristic — and the ``unattributed growth`` row.
    Both new rows are ranked INLINE by size alongside the est. rows (largest first) rather than
    appended at the end; the unattributed row keeps a ``"—"`` rank marker (it isn't a ranked
    contributor, just the reconciled remainder) but is positioned by its magnitude like every
    other row, so a reader scanning the table meets it exactly where its size puts it instead of
    only after every ranked entry. Returns ``None`` when no attribution was computed for this
    card (``entries`` is ``None``) — T1 callers that never pass attribution data keep getting a
    card with no ``"attribution"`` key at all."""
    if entries is None:
        return None
    capped = entries[: top] if (top and top > 0) else list(entries)
    recon = _reconcile_growth(calls, drops, entries)

    window_content = max((c["weight"] for c in calls), default=0)
    avoidable_entries = [e for e in entries if e["tool"] not in _AVOIDABLE_EXCLUDED_TOOLS]
    avoidable_total = sum(e["est_tokens"] for e in avoidable_entries)
    avoidable_pct = (avoidable_total / window_content * 100) if window_content else 0.0
    avoidable_top_source = (
        max(avoidable_entries, key=lambda e: e["est_tokens"])["tool"]
        if avoidable_entries else None
    )

    rows = [
        {"tool": e["tool"], "salient": e["salient"], "tokens": e["est_tokens"],
         "label": "est.", "rank_eligible": True}
        for e in capped
    ]
    rows.append({
        "tool": ASSISTANT_OUTPUT_LABEL, "salient": "",
        "tokens": recon["assistant_output_measured"], "label": "measured",
        "rank_eligible": True,
    })
    rows.append({
        "tool": "unattributed growth", "salient": "",
        "tokens": recon["unattributed"], "label": "est.",
        "rank_eligible": False,
    })
    rows.sort(key=lambda r: -r["tokens"])

    ranked = []
    next_rank = 1
    for r in rows:
        rank = next_rank if r["rank_eligible"] else "—"
        if r["rank_eligible"]:
            next_rank += 1
        ranked.append({
            "rank": rank, "tool": r["tool"], "salient": r["salient"],
            "tokens": r["tokens"], "label": r["label"],
        })

    return {
        "entries": ranked,
        "measured_growth": recon["measured_growth"],
        "attributed_total": recon["attributed_total"],
        "assistant_output_measured": recon["assistant_output_measured"],
        "unattributed": recon["unattributed"],
        "attribution_exceeded_growth": recon["attribution_exceeded_growth"],
        "unattributed_note": UNATTRIBUTED_EXPLANATION,
        "notes": attr_notes or [],
        "basis": ATTRIBUTION_BASIS,
        "avoidable_tool_ingested_est_tokens": avoidable_total,
        "avoidable_of_window_content": window_content,
        "avoidable_pct": avoidable_pct,
        "avoidable_top_source": avoidable_top_source,
    }


def build_session_card(session_id, files, calls, sidechain, notes, drops, pricing, top=20,
                        attribution_entries=None, attribution_notes=None):
    """Assemble the full Claude session card: id, files scanned, call count, avg/peak/total
    weight, a sparkline + compact table of the growth curve, inferred + confirmed compaction
    markers, the ranked "what filled the window" attribution + reconciliation (D4, only when
    ``attribution_entries`` is supplied), the sidechain line (D7), and the context carry cost
    (D5)."""
    weights = [c["weight"] for c in calls]
    n = len(calls)
    avg_weight = round(sum(weights) / n) if n else 0
    peak_weight = max(weights) if weights else 0
    total_submitted = sum(weights)
    row_idx = _select_row_indices(n, top)
    table_rows = [
        {
            "call": i + 1,
            "input": calls[i]["input"],
            "cache_read": calls[i]["cache_read"],
            "cache_write": calls[i]["cache_write"],
            "weight": calls[i]["weight"],
        }
        for i in row_idx
    ]
    confirmed = [nt["index"] for nt in notes if nt.get("kind") == "confirmed_compact_summary"]

    # Phase 2-3 review addition #2: percent-of-window is the metric that answers "at 700K, what
    # do I do?", and nothing in `session` reported it before this. Resolved against the model
    # of the PEAK call (the moment this session came closest to the ceiling) — never a
    # hardcoded window size (see `_resolve_window_tokens`).
    peak_model = None
    if weights:
        peak_idx = weights.index(peak_weight)
        peak_model = calls[peak_idx]["model"]
    window_tokens = _resolve_window_tokens(pricing, peak_model)
    peak_pct_of_window = (peak_weight / window_tokens * 100) if window_tokens else 0.0

    card = {
        "schema_version": CW_SCHEMA_VERSION,
        "found": True,
        "harness": "claude",
        "session_id": session_id,
        "files_scanned": len(files),
        "calls": n,
        "avg_weight": avg_weight,
        "peak_weight": peak_weight,
        "total_submitted": total_submitted,
        "window_tokens": window_tokens,
        "peak_pct_of_window": peak_pct_of_window,
        "sparkline": _sparkline(weights),
        "table_rows": table_rows,
        "table_truncated": bool(top) and top > 0 and n > top,
        "inferred_drops": drops,
        "confirmed_compact_indices": confirmed,
        "sidechain": sidechain,
        "carry_cost": _carry_cost(calls, pricing),
    }
    # Phase 2-3 review addition #1: `find_main_transcript` (which only `session` uses) can land
    # on a transcript that is entirely sidechain (subagents hit this) — without this note the
    # card silently renders "0 call(s)" next to a large sidechain figure, reading as "nothing
    # happened" rather than "this transcript is a subagent transcript."
    if n == 0 and sidechain["calls"] > 0:
        card["note"] = (
            f"all {sidechain['calls']} call(s) in this transcript are sidechain "
            "(subagent) — 0 main call(s), not a session with no activity"
        )
    attribution = _build_attribution_section(calls, drops, attribution_entries, attribution_notes,
                                              top=top)
    if attribution is not None:
        card["attribution"] = attribution
    return card


def render_session_markdown(card):
    if not card.get("found", True):
        return f"# Context weight — session ({card['harness']})\n\n{card['message']}\n"

    out = [f"# Context weight — session {card['session_id']} ({card['harness']})\n"]
    if card.get("note"):
        out.append(f"{card['note']}\n")
    out.append(f"Scanned {card['files_scanned']} file(s), {card['calls']} call(s).\n")
    out.append(
        f"avg weight {card['avg_weight']:,} · peak weight {card['peak_weight']:,} "
        f"· total submitted {card['total_submitted']:,}\n"
    )
    if card.get("window_tokens"):
        out.append(
            f"peak {card['peak_pct_of_window']:.0f}% of window "
            f"({card['peak_weight']:,} of {card['window_tokens']:,} tokens)\n"
        )
    if card["sparkline"]:
        out.append(f"growth curve: {card['sparkline']}\n")

    out.append("| call # | input | cache_read | cache_write | weight |")
    out.append("|---:|---:|---:|---:|---:|")
    for r in card["table_rows"]:
        out.append(
            f"| {r['call']} | {r['input']:,} | {r['cache_read']:,} "
            f"| {r['cache_write']:,} | {r['weight']:,} |"
        )
    if card["table_truncated"]:
        out.append("\n(table capped; first and last calls are always shown)")

    if card["inferred_drops"]:
        out.append("\n## Inferred compactions\n")
        for d in card["inferred_drops"]:
            out.append(
                f"- call {d['index'] + 1}: inferred compaction "
                f"({d['before']:,} → {d['after']:,})"
            )
    if card["confirmed_compact_indices"]:
        out.append("\n## Confirmed compact-summary markers\n")
        for idx in card["confirmed_compact_indices"]:
            out.append(f"- call {idx + 1}: isCompactSummary")

    attribution = card.get("attribution")
    if attribution is not None:
        if attribution["avoidable_top_source"]:
            out.append(
                f"\navoidable (tool-ingested) mass: "
                f"{attribution['avoidable_tool_ingested_est_tokens']:,} est. of "
                f"{attribution['avoidable_of_window_content']:,} "
                f"({attribution['avoidable_pct']:.0f}%) "
                f"— top source: {attribution['avoidable_top_source']}"
            )
        else:
            out.append(
                "\navoidable (tool-ingested) mass: 0 est. — no tool-ingested contributors "
                "this session"
            )
        out.append("\n## What filled the window (est.)\n")
        out.append("| rank | tool | salient | tokens |")
        out.append("|---:|---|---|---:|")
        for e in attribution["entries"]:
            out.append(
                f"| {e['rank']} | {e['tool']} | {e['salient']} | {e['tokens']:,} {e['label']} |"
            )
        out.append(f"\n{UNATTRIBUTED_EXPLANATION}")
        if attribution["attribution_exceeded_growth"]:
            out.append(
                "\nranked attribution exceeded measured growth this session — "
                "estimates are estimates; unattributed growth is floored at 0."
            )
        out.append(f"\nbasis: {ATTRIBUTION_BASIS}")

    sidechain = card["sidechain"]
    if sidechain["calls"]:
        mass = card["total_submitted"] + sidechain["weight"]
        share = (sidechain["weight"] / mass * 100) if mass else 0.0
        out.append(
            f"\nSidechain (subagents): {sidechain['calls']} call(s), "
            f"{sidechain['weight']:,} tokens ({share:.0f}% of session mass)."
        )

    cc = card["carry_cost"]
    out.append(
        f"\ncontext carry cost: ${cc['carry_usd']:,.2f} of "
        f"${cc['session_total_usd']:,.2f} session total ({cc['pct']:.0f}%)."
    )
    out.append(f"\n{cc['label']}")
    return "\n".join(out)


def build_session_json(card):
    """The JSON builder is a thin identity wrapper — ``card`` is already a plain, JSON-safe
    dict — kept as a separate name so future tasks can add fields without touching callers."""
    return card


# ---------------------------------------------------------------------------------------------
# `watch` (T10, PLAN D15) — the live view: current weight, distance to the window, and what is
# safely prunable vs load-bearing right now. Claude-only by design (D3's fidelity ladder: Codex
# has no per-call provenance and Copilot has no growth curve, so neither can support a live
# threshold) — there is deliberately no `--harness` flag; a non-Claude invocation gets the
# pinned refusal line below and exits 0.

WATCH_REFUSAL_LINE = (
    "watch: Claude sessions only — Codex has no per-call provenance and Copilot has no growth "
    "curve (see audit/session for their honest fidelity)"
)

# D14 ladder: below 40% -> prevention is still free, no action needed; 40-60% -> prevention still
# works but should start now (delegate NEW bulk reads rather than inlining them); above 60% ->
# prevention alone won't be enough before the ceiling, so checkpoint decisions to disk (D16 in
# the guide skill) BEFORE compacting, so the lossy step has a durable anchor.
_WATCH_DELEGATE_FLOOR_PCT = 40
_WATCH_CHECKPOINT_FLOOR_PCT = 60


def _watch_recommendation(pct):
    if pct < _WATCH_DELEGATE_FLOOR_PCT:
        return "no action"
    if pct <= _WATCH_CHECKPOINT_FLOOR_PCT:
        return "delegate new bulk reads, do not inline"
    return "checkpoint decisions to disk, then compact"


def _empty_watch_class():
    return {"count": 0, "est_tokens": 0, "items": []}


def _watch_class_section(items):
    return {"count": len(items), "est_tokens": sum(it["est_tokens"] for it in items),
            "items": items}


def build_absent_watch_card(session_id, projects_dir):
    """Clean "nothing found" card (exit 0, never an error) — carries the same top-level
    ``prunable``/``load_bearing``/``unknown`` keys (all empty) as a found card, so `--json`
    always validates the same way regardless of whether a session was located."""
    return {
        "schema_version": CW_SCHEMA_VERSION,
        "found": False,
        "harness": "claude",
        "session_id": session_id,
        "message": (
            f"No claude transcript found for session {session_id or '(latest)'} "
            f"under {projects_dir}."
        ),
        "prunable": _empty_watch_class(),
        "load_bearing": _empty_watch_class(),
        "unknown": _empty_watch_class(),
    }


def build_watch_card(session_id, calls, sidechain, records, pricing, window_tokens_override=None):
    """Assemble the `watch` card (D15): current (most recent) weight, the window it's being
    measured against (resolved from `data/pricing.json`'s `context_window` for the CURRENT
    call's model — never hardcoded), percent of that window, the three-class prunable/
    load-bearing/unknown mass split from `classify_prunable`, and the D14-ladder
    recommendation. `calls`/`sidechain` come from `claude_call_weights`; `records` is the full
    object list handed to `classify_prunable` (sidechain content is filtered out inside it,
    same as `attribute_growth`)."""
    current_weight = calls[-1]["weight"] if calls else 0
    current_model = calls[-1]["model"] if calls else None
    window_tokens = _resolve_window_tokens(pricing, current_model, window_tokens_override)
    pct_of_window = (current_weight / window_tokens * 100) if window_tokens else 0.0

    prunable, load_bearing, unknown = classify_prunable(records)

    card = {
        "schema_version": CW_SCHEMA_VERSION,
        "found": True,
        "harness": "claude",
        "session_id": session_id,
        "calls": len(calls),
        "current_weight": current_weight,
        "window_tokens": window_tokens,
        "pct_of_window": pct_of_window,
        "recommendation": _watch_recommendation(pct_of_window),
        "prunable": _watch_class_section(prunable),
        "load_bearing": _watch_class_section(load_bearing),
        "unknown": _watch_class_section(unknown),
        "sidechain": sidechain,
        "basis": ATTRIBUTION_BASIS,
    }
    if len(calls) == 0 and sidechain["calls"] > 0:
        card["note"] = (
            f"all {sidechain['calls']} call(s) in this transcript are sidechain "
            "(subagent) — 0 main call(s), not a session with no activity"
        )
    return card


def render_watch_markdown(card):
    if not card.get("found", True):
        return f"# Context weight — watch (claude)\n\n{card['message']}\n"

    out = [f"# Context weight — watch {card['session_id']} (claude)\n"]
    if card.get("note"):
        out.append(f"{card['note']}\n")
    out.append(
        f"current weight {card['current_weight']:,} of a {card['window_tokens']:,}-token "
        f"window ({card['pct_of_window']:.0f}%)\n"
    )
    out.append(f"recommendation: {card['recommendation']}\n")

    out.append("\n## What's safe to drop (est.)\n")
    for label, key in (
        ("prunable", "prunable"), ("load-bearing", "load_bearing"), ("unknown", "unknown"),
    ):
        section = card[key]
        out.append(
            f"- {label}: {section['count']} item(s), {section['est_tokens']:,} est. tokens"
        )

    # Coverage disclosure. The three classes enumerate discrete droppable ITEMS (tool results,
    # file reads, thinking blocks, messages) — never the whole window. On a real session they
    # come to ~10% of it, and without this line a reader cannot tell whether the other ~90% is
    # known-not-droppable or simply never examined. Same honesty rule the attribution table
    # holds when it names what is not measurable from the transcript.
    classified = sum(card[k]["est_tokens"] for k in ("prunable", "load_bearing", "unknown"))
    current = card["current_weight"]
    if current:
        out.append(
            f"\nthese classes cover discrete droppable items: {classified:,} est. of "
            f"{current:,} ({classified / current * 100:.0f}% of this window). The remainder is "
            f"assistant output and user input — carried, but no lever removes them."
        )

    sidechain = card["sidechain"]
    if sidechain["calls"]:
        out.append(
            f"\nSidechain (subagents): {sidechain['calls']} call(s), "
            f"{sidechain['weight']:,} tokens (excluded from the classes above — D7)."
        )

    out.append(f"\nbasis: {ATTRIBUTION_BASIS}")
    out.append(
        "\nThis reports what looks safe to drop; it never deletes anything itself (D13) — only "
        "the harness's own compaction/context-editing can actually remove content from the "
        "window. Checkpoint load-bearing decisions to disk before compacting."
    )
    return "\n".join(out)


def build_watch_json(card):
    """Identity wrapper, same idiom as `build_session_json`."""
    return card


# ---------------------------------------------------------------------------------------------
# Pure-function layer — Codex, curve fidelity, NO content attribution (D1/D2/D3 Codex rung).
#
# Codex's rollout logs carry per-turn or cumulative-snapshot token COUNTS via the usage
# containers cx._find_containers/_normalize_tokens already extract — enough for a growth curve
# — but they carry NO content alongside those counts, so there is no honest way to say what
# filled the window call-by-call. Per D3/PLAN, Codex therefore gets a curve but NEVER a ranked
# "what filled the window" table: Claude's attribute_growth is never called or ported here —
# porting it would be estimating provenance the logs do not record, which is the exact failure
# this kit exists to prevent. The only "what's in this rollout" signal Codex can honestly offer
# is a per-RECORD-TYPE byte-share of the raw log bytes (codex_byte_share) — sizes, not content,
# always labeled est., never priced, printed under the verbatim no-provenance line pinned below.

CODEX_NO_PROVENANCE_LINE = (
    "provenance not recorded in these logs — byte-share of rollout record types shown as a "
    "labeled estimate"
)

# `session` carries no --days flag, so there is no day-window to honor for Codex — this cutoff
# means "include every rollout regardless of age" when handed to cx.iter_rollout_files.
_NO_CUTOFF = datetime.min.replace(tzinfo=timezone.utc)


def codex_curve(lines):
    """Growth curve from one rollout's raw text lines (D3 Codex rung).

    Scans records in file order via ``cx._find_containers(obj, cx.USAGE_CONTAINER_KEYS)`` +
    ``cx._normalize_tokens``. If ANY per-turn container is found anywhere in the file (a
    container key not in ``cx.CUMULATIVE_CONTAINER_KEYS``), the curve is per-turn weights
    (``input + cache_read``) in the order their containers appear, ``kind = "per-turn"`` — this
    wins even when cumulative ``total_token_usage`` containers are ALSO present in the same
    file; the two kinds are never mixed into one curve. Only when no per-turn container exists
    anywhere and at least one cumulative ``total_token_usage`` snapshot does, the curve is
    ``input + cache_read`` per snapshot IN ORDER (each snapshot is its own curve point, not
    deduplicated/maxed — that MAX rule is ``cx.parse_rollout``'s own, for TOTALS, a separate
    concern from this curve), ``kind = "cumulative snapshots"``. When neither exists, there is
    no curve at all: ``kind = None`` and ``notes`` carries the codex_usage honesty line
    (``cx.UNPRICED_NOTE`` — activity counted, unpriced).

    Carry cost/totals are computed by the CALLER via ``cx.parse_rollout(lines)`` directly; that
    function's cumulative-wins rule for totals is untouched here — this curve's per-turn-first
    rule is a deliberately different view of the same containers, for the curve only.

    Returns ``(points, kind, notes)``.
    """
    per_turn_points = []
    cumulative_points = []
    has_per_turn = False
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        for key, container in cx._find_containers(obj, cx.USAGE_CONTAINER_KEYS):
            norm = cx._normalize_tokens(container)
            weight = norm["input"] + norm["cache_read"]
            if key in cx.CUMULATIVE_CONTAINER_KEYS:
                cumulative_points.append(weight)
            else:
                has_per_turn = True
                per_turn_points.append(weight)

    if has_per_turn:
        return per_turn_points, "per-turn", []
    if cumulative_points:
        return cumulative_points, "cumulative snapshots", []
    return [], None, [cx.UNPRICED_NOTE]


def codex_byte_share(lines):
    """Per-record-``type`` byte share of one rollout's raw lines — the ONLY "what's in this
    rollout" signal Codex can honestly offer (D3/D9): serialized line length, grouped by the
    record's top-level ``type`` field (``"(untyped)"`` when absent or non-string), summed and
    turned into a percentage of total scanned bytes. Sizes only — never content, never a file
    path, never priced; every row carries the ``est.`` label. Malformed lines are skipped, never
    raised.

    Returns ``(rows, total_bytes)`` where each row is
    ``{"type", "bytes", "pct", "label": "est."}``, ranked descending by bytes.
    """
    totals = defaultdict(int)
    total_bytes = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        length = len(stripped.encode("utf-8"))
        rtype = obj.get("type") if isinstance(obj, dict) else None
        rtype = rtype if isinstance(rtype, str) and rtype else "(untyped)"
        totals[rtype] += length
        total_bytes += length
    rows = [
        {
            "type": rtype,
            "bytes": nbytes,
            "pct": (nbytes / total_bytes * 100) if total_bytes else 0.0,
            "label": "est.",
        }
        for rtype, nbytes in totals.items()
    ]
    rows.sort(key=lambda r: -r["bytes"])
    return rows, total_bytes


def _codex_matched_model(models, pricing):
    """Best-effort model key (``cx.match_model``) + approx flag, mirroring codex_usage.py's own
    "last matched model wins, approx if more than one" idiom — never a fabricated match."""
    matched = []
    for m in models:
        key = cx.match_model(m, pricing)
        if key and key not in matched:
            matched.append(key)
    if not matched:
        return None, False
    return matched[-1], len(matched) > 1


def _codex_session_ids_in(lines):
    """Every session id ``cx._first(obj, cx.SESSION_KEYS)`` surfaces anywhere in one rollout's
    lines, best-effort (malformed/non-dict lines skipped)."""
    ids = set()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        sid = cx._first(obj, cx.SESSION_KEYS)
        if isinstance(sid, str) and sid:
            ids.add(sid)
    return ids


def _select_codex_rollout(codex_home, session_id):
    """The rollout file ``session --harness codex`` analyzes: every rollout under
    ``<codex_home>/sessions`` (no day-window — ``session`` has no ``--days`` flag), filtered to
    ``session_id`` by filename stem or discovered session id (``_codex_session_ids_in``) when
    given, else the most recently modified rollout. Returns ``None`` when nothing matches
    (absent home, empty sessions dir, or no rollout for that session id)."""
    files = list(cx.iter_rollout_files(Path(codex_home) / "sessions", _NO_CUTOFF))
    if not files:
        return None
    if not session_id:
        return max(files, key=lambda f: f.stat().st_mtime)
    for f in files:
        if f.stem == session_id:
            return f
    for f in files:
        lines = f.read_text(errors="replace").splitlines()
        if session_id in _codex_session_ids_in(lines):
            return f
    return None


def build_codex_session_card(session_id, rollout_path, lines, pricing, top=20):
    """Assemble the full Codex session card (D3 Codex rung): the curve (or, absent one, the
    codex_usage no-token honesty line), model + context carry cost priced with OUTPUT ZEROED
    via ``cx.price_tokens`` off ``cx.parse_rollout(lines)``'s totals (unmatched model -> tokens
    shown, unpriced — never a fabricated price), and the byte-share provenance table under the
    verbatim ``CODEX_NO_PROVENANCE_LINE``. NEVER a ranked content-attribution table — that
    facility is Claude-only (D3) and is neither called nor reachable from this function."""
    points, kind, curve_notes = codex_curve(lines)
    parsed = cx.parse_rollout(lines)
    n = len(points)
    avg_weight = round(sum(points) / n) if n else 0
    peak_weight = max(points) if points else 0
    row_idx = _select_row_indices(n, top)
    table_rows = [{"call": i + 1, "weight": points[i]} for i in row_idx]

    model_key, approx = _codex_matched_model(parsed["models"], pricing)
    carry_cost = None
    if model_key is not None and parsed["tokens"] is not None:
        zeroed = dict(parsed["tokens"])
        zeroed["output"] = 0
        carry_cost = {
            "carry_usd": cx.price_tokens(zeroed, model_key, pricing),
            "model": model_key,
            "display": pricing["models"][model_key]["display"],
            "approx": approx,
            "disclaimer": cx.PROXY_DISCLAIMER,
        }

    byte_share_rows, byte_share_total = codex_byte_share(lines)

    return {
        "schema_version": CW_SCHEMA_VERSION,
        "found": True,
        "harness": "codex",
        "session_id": session_id,
        "rollout_file": str(rollout_path),
        "calls": n,
        "curve_kind": kind,
        "curve_notes": curve_notes,
        "avg_weight": avg_weight,
        "peak_weight": peak_weight,
        "sparkline": _sparkline(points),
        "table_rows": table_rows,
        "table_truncated": bool(top) and top > 0 and n > top,
        "models_seen": parsed["models"],
        "tokens": parsed["tokens"],
        "carry_cost": carry_cost,
        "attribution": {
            "provenance_note": CODEX_NO_PROVENANCE_LINE,
            "byte_share": byte_share_rows,
            "total_bytes": byte_share_total,
        },
    }


def render_codex_session_markdown(card):
    if not card.get("found", True):
        return f"# Context weight — session ({card['harness']})\n\n{card['message']}\n"

    out = [f"# Context weight — session {card['session_id']} (codex)\n"]
    out.append(f"Rollout: {card['rollout_file']}\n")

    if card["curve_kind"]:
        out.append(f"{card['calls']} call(s) · curve: {card['curve_kind']}\n")
        out.append(
            f"avg weight {card['avg_weight']:,} · peak weight {card['peak_weight']:,}\n"
        )
        if card["sparkline"]:
            out.append(f"growth curve: {card['sparkline']}\n")
        out.append("| call # | weight |")
        out.append("|---:|---:|")
        for r in card["table_rows"]:
            out.append(f"| {r['call']} | {r['weight']:,} |")
        if card["table_truncated"]:
            out.append("\n(table capped; first and last calls are always shown)")
    else:
        for note in card["curve_notes"]:
            out.append(f"\n{note}")

    tokens = card["tokens"]
    if tokens is not None:
        out.append(
            f"\ntokens: input {tokens['input']:,} · cache_read {tokens['cache_read']:,} "
            f"· output {tokens['output']:,}"
        )
    if card["models_seen"]:
        out.append(f"\nModel(s) seen: {', '.join(card['models_seen'])}")

    cc = card["carry_cost"]
    if cc is not None:
        approx_note = " (approx — multiple models seen in this rollout)" if cc["approx"] else ""
        out.append(
            f"\ncontext carry cost: ${cc['carry_usd']:,.4f} — {cc['display']}{approx_note}."
        )
        out.append(f"\n{cc['disclaimer']}")
    elif tokens is not None:
        out.append("\ntokens shown, unpriced — no matching model in pricing.codex.json.")
        out.append(f"\n{cx.PROXY_DISCLAIMER}")

    out.append("\n## Provenance (est.)\n")
    out.append(f"{card['attribution']['provenance_note']}\n")
    out.append("| record type | bytes | % of file | label |")
    out.append("|---|---:|---:|---|")
    for row in card["attribution"]["byte_share"]:
        out.append(f"| {row['type']} | {row['bytes']:,} | {row['pct']:.1f}% | {row['label']} |")

    return "\n".join(out)


def build_codex_session_json(card):
    """Identity wrapper, mirrors build_session_json's naming for future-proofing."""
    return card


# ---------------------------------------------------------------------------------------------
# Pure-function layer — Copilot, session-average fidelity, NO curve, NO attribution, EVER
# (D1/D2/D3 Copilot rung — the strictest rung of the ladder).
#
# Copilot's events.jsonl carries per-turn OUTPUT tokens only (assistant.message events); the
# full input/cache_read/cache_write/output split exists ONLY as a cumulative session.shutdown
# tokenDetails snapshot. There is therefore NO per-turn input/cache figure to plot — a growth
# curve is impossible to compute honestly, full stop. This module deliberately does NOT reuse
# codex_curve (T3) against Copilot's per-turn output events: output tokens alone are not context
# weight (D2 defines weight as input + cache_read + cache_write), so plotting them as a curve
# would imply a measurement these logs cannot support. It also does NOT call attribute_growth
# (T2/D4): Copilot events carry no tool_use/tool_result content at all, so there is nothing to
# rank. The single honest signal is one session-level average — (input + cache_read +
# cache_write) // assistant turns — plus the verbatim COPILOT_NO_CURVE_LINE, always present.

COPILOT_NO_CURVE_LINE = (
    "growth curve: not available — Copilot events do not record per-turn input/cache token "
    "splits"
)


def _copilot_matched_model(parsed, pricing):
    """Best-effort pricing key for the carry-cost line, mirroring copilot_usage._attribute's
    idiom: matched pricing keys in file order; a single match is used outright; more than one
    is attributed to the session's LAST model when it matches (else the last matched key), and
    flagged approx — exactly like copilot_usage's ``≈`` marker. Never a fabricated match."""
    matched_keys = []
    for m in parsed["models"]:
        key = cp.match_model(m, pricing)
        if key and key not in matched_keys:
            matched_keys.append(key)
    if not matched_keys:
        return None, False
    if len(matched_keys) == 1:
        return matched_keys[0], False
    last_key = cp.match_model(parsed["last_model"], pricing)
    attribution = last_key if last_key in matched_keys else matched_keys[-1]
    return attribution, True


def copilot_session_card(parsed, pricing, session_id=None):
    """Assemble the Copilot session card (D3 Copilot rung).

    ``turns`` = sum of ``parsed["per_turn_output"][model]["turns"]`` across every model seen.
    When ``parsed["has_token_details"]`` (a session.shutdown was seen) AND ``turns > 0``:
    ``session_average_weight = (tokens.input + tokens.cache_read + tokens.cache_write) //
    turns``, labeled ``"session-average"``. Absent a shutdown snapshot, ``session_average_weight``
    stays ``None`` and NOTHING is fabricated in its place — the card's ``tokens_recorded`` flag
    tells the renderer to print "not recorded" rather than a zero.

    ``output_turns_table`` is the per-model output-turns view built straight from
    ``per_turn_output`` (rank descending by output tokens) — the only per-turn signal these
    events carry.

    The card carries NO ``"attribution"`` key, ever, and no curve/sparkline of any kind — only
    the verbatim ``COPILOT_NO_CURVE_LINE``, always present under ``"no_curve_line"``.

    Carry cost (D5): ``parsed["tokens"]`` with OUTPUT ZEROED, priced via ``cp.price_tokens``
    against the last matched model (``_copilot_matched_model``), converted to AIC via
    ``cp.usd_to_aic`` — only when a shutdown snapshot was seen AND a model matched pricing;
    otherwise ``carry_cost`` stays ``None`` (never a fabricated dollar figure).
    """
    per_turn = parsed["per_turn_output"]
    turns = sum(v["turns"] for v in per_turn.values())
    output_turns_table = [
        {"model": m, "turns": v["turns"], "output_tokens": v["output_tokens"]}
        for m, v in sorted(per_turn.items(), key=lambda kv: -kv[1]["output_tokens"])
    ]

    tokens_recorded = bool(parsed["has_token_details"])
    session_average_weight = None
    if tokens_recorded and turns > 0:
        tokens = parsed["tokens"]
        session_average_weight = (
            tokens["input"] + tokens["cache_read"] + tokens["cache_write"]
        ) // turns

    carry_cost = None
    if tokens_recorded:
        model_key, approx = _copilot_matched_model(parsed, pricing)
        if model_key is not None:
            zeroed = dict(parsed["tokens"])
            zeroed["output"] = 0
            carry_usd = cp.price_tokens(zeroed, model_key, pricing)
            carry_cost = {
                "carry_usd": carry_usd,
                "aic": cp.usd_to_aic(carry_usd, pricing),
                "model": model_key,
                "display": pricing["models"][model_key]["display"],
                "approx": approx,
                "label": CARRY_COST_LABEL,
            }

    return {
        "schema_version": CW_SCHEMA_VERSION,
        "found": True,
        "harness": "copilot",
        "session_id": session_id,
        "turns": turns,
        "session_average_weight": session_average_weight,
        "session_average_label": "session-average",
        "output_turns_table": output_turns_table,
        "no_curve_line": COPILOT_NO_CURVE_LINE,
        "tokens_recorded": tokens_recorded,
        "carry_cost": carry_cost,
    }


def render_copilot_session_markdown(card):
    if not card.get("found", True):
        return f"# Context weight — session ({card['harness']})\n\n{card['message']}\n"

    out = [f"# Context weight — session {card['session_id']} (copilot)\n"]
    out.append(f"{card['turns']} assistant turn(s).\n")

    if card["session_average_weight"] is not None:
        out.append(
            f"{card['session_average_label']} weight: {card['session_average_weight']:,}\n"
        )
    elif not card["tokens_recorded"]:
        out.append(
            "session-average weight: not recorded — no session.shutdown tokenDetails seen\n"
        )

    out.append(f"\n{card['no_curve_line']}\n")

    if card["output_turns_table"]:
        out.append("\n| model | turns | output tokens |")
        out.append("|---|---:|---:|")
        for row in card["output_turns_table"]:
            out.append(f"| {row['model']} | {row['turns']:,} | {row['output_tokens']:,} |")

    cc = card["carry_cost"]
    if cc is not None:
        approx_note = " (approx — multiple models seen this session)" if cc["approx"] else ""
        out.append(
            f"\ncontext carry cost: ${cc['carry_usd']:,.4f} ({cc['aic']:,.2f} AIC) "
            f"— {cc['display']}{approx_note}."
        )
        out.append(f"\n{cc['label']}")
    elif not card["tokens_recorded"]:
        out.append("\ncontext carry cost: not recorded — no session.shutdown tokenDetails seen.")

    return "\n".join(out)


def build_copilot_session_json(card):
    """Identity wrapper, mirrors build_session_json's naming for future-proofing."""
    return card


def _select_copilot_session(copilot_home, session_id):
    """The ``events.jsonl`` this ``session --harness copilot`` call analyzes: ``--session``
    selects by SESSION-STATE DIR NAME (``<copilot_home>/session-state/<id>/events.jsonl``);
    absent, the most recently modified ``events.jsonl`` under ``<copilot_home>/session-state``.
    Returns ``None`` when nothing matches (absent home, empty session-state dir, or no dir with
    that name) — never an error."""
    state_dir = Path(copilot_home) / "session-state"
    if not state_dir.is_dir():
        return None
    if session_id:
        candidate = state_dir / session_id / "events.jsonl"
        return candidate if candidate.is_file() else None
    candidates = list(state_dir.glob("*/events.jsonl"))
    if not candidates:
        return None
    return max(candidates, key=lambda f: f.stat().st_mtime)


# ---------------------------------------------------------------------------------------------
# I/O helpers.


def _read_jsonl_objs(path):
    """Read one .jsonl file, strictly for reading — malformed lines are skipped, never raised."""
    objs = []
    try:
        text = Path(path).read_text(errors="replace")
    except OSError:
        return objs
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            objs.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return objs


# ---------------------------------------------------------------------------------------------
# Pure-function layer — overview (T5): a cross-session working-set table, ONE SECTION PER
# HARNESS, never a merged table and never a cross-harness dollar total (D5).
#
# The hazard here is aggregation across unequal fidelities (D3): Claude's per-session row is a
# real summary of a real growth curve; Codex's is curve points with NO content provenance;
# Copilot's is a session AVERAGE with no curve at all. So each section builder below calls that
# harness's own EXISTING per-session card builder (build_session_card / build_codex_session_card
# / copilot_session_card) once per matching transcript/rollout/session and only AGGREGATES the
# fields those cards already computed — it never re-derives a curve or a price itself. Where a
# harness cannot supply a figure (e.g. Copilot's session-average weight with no shutdown
# snapshot), the field stays ``None`` and the renderer prints a pinned not-available phrase —
# never a ``0`` standing in for "unmeasured".

OVERVIEW_HARNESSES = ("claude", "codex", "copilot")


def _rank_limit(rows, top):
    """Cap a ranked row list at ``top`` (already sorted); ``top <= 0`` means "show all", the
    same convention ``_select_row_indices`` uses for the per-session curve table."""
    if top and top > 0:
        return rows[:top]
    return rows


def build_claude_overview_section(projects_dir, cutoff, top, pricing):
    """One row per ``*.jsonl`` file under ``projects_dir`` whose mtime is >= ``cutoff`` (D1's
    "one session, one file" reading for a cross-session table — no subagent-file merging, since
    that is `session`'s job for ONE driver transcript, not overview's job across many). Each row
    is built by feeding that file's own ``claude_call_weights``/``detect_drops`` output straight
    into the EXISTING ``build_session_card`` (no attribution — overview never needs the ranked
    "what filled the window" table) and lifting the summary fields + that session's own
    already-computed carry-cost off the returned card. Ranked by ``total_submitted`` descending
    per the brief; the window's carry-cost line sums every SCANNED session's carry cost (not
    just the ones shown after ``--top`` truncation), because dollars are exact aggregation, not
    a ranked display.

    A row whose transcript is entirely sidechain (0 main calls, nonzero sidechain calls) — the
    Phase-1-review hazard where a lone ``0 call(s)`` reads as "nothing happened" when a large
    subagent mass is sitting right next to it — carries an explicit ``note`` field instead of a
    silent zero.
    """
    projects_dir = Path(projects_dir)
    if not projects_dir.is_dir():
        return {
            "harness": "claude",
            "found": False,
            "message": f"No claude projects dir at {projects_dir}.",
            "sessions_scanned": 0,
            "sessions": [],
            "sessions_truncated": False,
            "carry_cost": None,
        }

    all_rows = []
    for f in sorted(p for p in projects_dir.rglob("*.jsonl") if p.is_file()):
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        if mtime < cutoff:
            continue
        objs = _read_jsonl_objs(f)
        calls, sidechain, notes = claude_call_weights(objs)
        drops = detect_drops([c["weight"] for c in calls])
        card = build_session_card(f.stem, [f], calls, sidechain, notes, drops, pricing)
        row = {
            "session_id": card["session_id"],
            "calls": card["calls"],
            "avg_weight": card["avg_weight"],
            "peak_weight": card["peak_weight"],
            "total_submitted": card["total_submitted"],
            "inferred_compactions": len(card["inferred_drops"]),
            "sidechain": card["sidechain"],
            "carry_cost": card["carry_cost"],
        }
        mass = row["total_submitted"] + row["sidechain"]["weight"]
        row["sidechain_share_pct"] = (row["sidechain"]["weight"] / mass * 100) if mass else 0.0
        if row["calls"] == 0 and row["sidechain"]["calls"] > 0:
            row["note"] = (
                f"all {row['sidechain']['calls']} call(s) in this transcript are sidechain "
                "(subagent) — 0 main call(s), not a session with no activity"
            )
        all_rows.append(row)

    all_rows.sort(key=lambda r: -r["total_submitted"])
    shown = _rank_limit(all_rows, top)

    carry_cost = None
    if all_rows:
        carry_usd = sum(r["carry_cost"]["carry_usd"] for r in all_rows)
        window_total_usd = sum(r["carry_cost"]["session_total_usd"] for r in all_rows)
        pct = (carry_usd / window_total_usd * 100) if window_total_usd else 0.0
        carry_cost = {
            "carry_usd": carry_usd,
            "window_total_usd": window_total_usd,
            "pct": pct,
            "label": CARRY_COST_LABEL,
        }

    return {
        "harness": "claude",
        "found": True,
        "sessions_scanned": len(all_rows),
        "sessions": shown,
        "sessions_truncated": len(shown) < len(all_rows),
        "carry_cost": carry_cost,
    }


def build_codex_overview_section(codex_home, cutoff, top, pricing):
    """One row per rollout ``cx.iter_rollout_files`` yields within ``cutoff``. Each row is built
    by feeding that rollout's lines straight into the EXISTING ``build_codex_session_card`` (the
    same builder ``session --harness codex`` uses) and lifting ``points``/``avg weight``/``kind``
    off the returned card — per D3, NEVER a content-attribution table, only curve fidelity.
    Ranked by (avg weight x points) descending as a total-mass proxy. A rollout whose card has no
    carry cost (unmatched model, or no tokens at all) is counted but excluded from the summed
    window carry-cost — never priced by fabrication (D5)."""
    codex_home = Path(codex_home)
    sessions_dir = codex_home / "sessions"
    if not sessions_dir.is_dir():
        return {
            "harness": "codex",
            "found": False,
            "message": f"No codex sessions dir at {sessions_dir}.",
            "rollouts_scanned": 0,
            "rollouts": [],
            "rollouts_truncated": False,
            "carry_cost": None,
        }

    all_rows = []
    for f in cx.iter_rollout_files(sessions_dir, cutoff):
        lines = f.read_text(errors="replace").splitlines()
        card = build_codex_session_card(f.stem, f, lines, pricing)
        all_rows.append({
            "rollout_id": card["session_id"],
            "points": card["calls"],
            "avg_weight": card["avg_weight"],
            "peak_weight": card["peak_weight"],
            "kind": card["curve_kind"] or "no tokens",
            "carry_cost": card["carry_cost"],
        })

    all_rows.sort(key=lambda r: -(r["avg_weight"] * r["points"]))
    shown = _rank_limit(all_rows, top)

    priced = [r for r in all_rows if r["carry_cost"] is not None]
    carry_cost = None
    if priced:
        carry_cost = {
            "carry_usd": sum(r["carry_cost"]["carry_usd"] for r in priced),
            "disclaimer": cx.PROXY_DISCLAIMER,
            "priced_rollouts": len(priced),
            "unpriced_rollouts": len(all_rows) - len(priced),
        }
    elif all_rows:
        carry_cost = {
            "carry_usd": 0.0,
            "disclaimer": cx.PROXY_DISCLAIMER,
            "priced_rollouts": 0,
            "unpriced_rollouts": len(all_rows),
        }

    return {
        "harness": "codex",
        "found": True,
        "rollouts_scanned": len(all_rows),
        "rollouts": shown,
        "rollouts_truncated": len(shown) < len(all_rows),
        "carry_cost": carry_cost,
    }


def build_copilot_overview_section(copilot_home, cutoff, top, pricing):
    """One row per session ``cp.collect_sessions`` returns, age-filtered by ``last_seen`` the
    same way ``copilot_usage.py``'s own ``--days`` filter works (a session with no parseable
    timestamp is KEPT, never dropped for being unfileable). Each row is built by feeding that
    session's parsed events straight into the EXISTING ``copilot_session_card`` (the same builder
    ``session --harness copilot`` uses) — per D3 the STRICTEST rung: session-AVERAGE weight only,
    ``None`` (never ``0``) when no ``session.shutdown`` ``tokenDetails`` was seen, no curve, no
    attribution, ever. Ranked by assistant turns descending (the one figure every session has)."""
    copilot_home = Path(copilot_home)
    session_dir = copilot_home / "session-state"
    if not session_dir.is_dir():
        return {
            "harness": "copilot",
            "found": False,
            "message": f"No copilot session-state dir at {session_dir}.",
            "sessions_scanned": 0,
            "sessions": [],
            "sessions_truncated": False,
            "carry_cost": None,
        }

    parsed_sessions, _errors = cp.collect_sessions(session_dir)
    kept = [
        p for p in parsed_sessions
        if p["last_seen"] is None or p["last_seen"] >= cutoff
    ]

    all_rows = []
    for parsed in kept:
        card = copilot_session_card(parsed, pricing, session_id=parsed["session_id"])
        all_rows.append({
            "session_id": card["session_id"],
            "turns": card["turns"],
            "session_average_weight": card["session_average_weight"],
            "session_average_label": card["session_average_label"],
            "carry_cost": card["carry_cost"],
        })

    all_rows.sort(key=lambda r: (-r["turns"], -(r["session_average_weight"] or 0)))
    shown = _rank_limit(all_rows, top)

    priced = [r for r in all_rows if r["carry_cost"] is not None]
    carry_cost = None
    if priced:
        carry_cost = {
            "carry_usd": sum(r["carry_cost"]["carry_usd"] for r in priced),
            "aic": sum(r["carry_cost"]["aic"] for r in priced),
            "label": CARRY_COST_LABEL,
            "priced_sessions": len(priced),
            "unpriced_sessions": len(all_rows) - len(priced),
        }
    elif all_rows:
        carry_cost = {
            "carry_usd": 0.0,
            "aic": 0.0,
            "label": CARRY_COST_LABEL,
            "priced_sessions": 0,
            "unpriced_sessions": len(all_rows),
        }

    return {
        "harness": "copilot",
        "found": True,
        "sessions_scanned": len(all_rows),
        "sessions": shown,
        "sessions_truncated": len(shown) < len(all_rows),
        "carry_cost": carry_cost,
        "no_curve_line": COPILOT_NO_CURVE_LINE,
    }


def build_overview(harness, days, top, projects_dir, codex_home, copilot_home):
    """Assemble the full ``overview`` result: ``{"schema_version", "days", "harness_filter",
    "sections"}`` where ``sections`` carries ONLY the requested harness(es) as top-level keys
    (``"claude"``/``"codex"``/``"copilot"``) — there is no other top-level key, and in
    particular NO combined/blended dollar field anywhere: each section's ``carry_cost`` is
    priced exclusively from that harness's own measured usage via that harness's own pricing
    file (D5), and this function never sums a ``carry_usd`` across sections."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    sections = {}
    if harness in ("all", "claude"):
        sections["claude"] = build_claude_overview_section(
            projects_dir, cutoff, top, cr.load_pricing()
        )
    if harness in ("all", "codex"):
        sections["codex"] = build_codex_overview_section(
            codex_home, cutoff, top, cx.load_pricing()
        )
    if harness in ("all", "copilot"):
        sections["copilot"] = build_copilot_overview_section(
            copilot_home, cutoff, top, cp.load_pricing()
        )
    return {
        "schema_version": CW_SCHEMA_VERSION,
        "days": days,
        "harness_filter": harness,
        "sections": sections,
    }


def _render_claude_overview_section(section):
    out = ["\n## Claude\n"]
    if not section["found"]:
        out.append(section["message"])
        return "\n".join(out)
    if not section["sessions_scanned"]:
        out.append("No claude sessions in this window.")
        return "\n".join(out)
    out.append(f"{section['sessions_scanned']} session(s) in window.\n")
    out.append(
        "| session | calls | avg weight | peak weight | total submitted "
        "| inferred compactions | sidechain |"
    )
    out.append("|---|---:|---:|---:|---:|---:|---|")
    for r in section["sessions"]:
        sc_ = r["sidechain"]
        sc_text = (
            f"{sc_['calls']} call(s), {sc_['weight']:,} tok ({r['sidechain_share_pct']:.0f}%)"
            if sc_["calls"] else "—"
        )
        out.append(
            f"| {r['session_id']} | {r['calls']} | {r['avg_weight']:,} "
            f"| {r['peak_weight']:,} | {r['total_submitted']:,} "
            f"| {r['inferred_compactions']} | {sc_text} |"
        )
        if r.get("note"):
            out.append(f"  - {r['session_id']}: {r['note']}")
    if section["sessions_truncated"]:
        out.append("\n(table capped by --top; ranked by total submitted)")
    cc = section["carry_cost"]
    if cc:
        out.append(
            f"\ncontext carry cost (window): ${cc['carry_usd']:,.2f} of "
            f"${cc['window_total_usd']:,.2f} ({cc['pct']:.0f}%)."
        )
        out.append(f"\n{cc['label']}")
    return "\n".join(out)


def _render_codex_overview_section(section):
    out = ["\n## Codex\n"]
    if not section["found"]:
        out.append(section["message"])
        return "\n".join(out)
    if not section["rollouts_scanned"]:
        out.append("No codex rollouts in this window.")
        return "\n".join(out)
    out.append(f"{section['rollouts_scanned']} rollout(s) in window.\n")
    out.append(f"{CODEX_NO_PROVENANCE_LINE}\n")
    out.append("| rollout | points | avg weight | peak weight | kind |")
    out.append("|---|---:|---:|---:|---|")
    for r in section["rollouts"]:
        out.append(
            f"| {r['rollout_id']} | {r['points']} | {r['avg_weight']:,} "
            f"| {r['peak_weight']:,} | {r['kind']} |"
        )
    if section["rollouts_truncated"]:
        out.append("\n(table capped by --top; ranked by avg weight x points)")
    cc = section["carry_cost"]
    if cc:
        out.append(f"\ncontext carry cost (window): ${cc['carry_usd']:,.4f}")
        if cc["unpriced_rollouts"]:
            out.append(
                f" ({cc['priced_rollouts']} of "
                f"{cc['priced_rollouts'] + cc['unpriced_rollouts']} rollout(s) priced; "
                "unmatched-model rollouts contribute tokens shown elsewhere, unpriced)."
            )
        else:
            out.append(".")
        out.append(f"\n{cc['disclaimer']}")
    return "\n".join(out)


def _render_copilot_overview_section(section):
    out = ["\n## Copilot\n"]
    if not section["found"]:
        out.append(section["message"])
        return "\n".join(out)
    out.append(f"\n{COPILOT_NO_CURVE_LINE}\n")
    if not section["sessions_scanned"]:
        out.append("No copilot sessions in this window.")
        return "\n".join(out)
    out.append(f"\n{section['sessions_scanned']} session(s) in window.\n")
    out.append("| session | turns | session-average weight |")
    out.append("|---|---:|---:|")
    for r in section["sessions"]:
        avg_text = f"{r['session_average_weight']:,}" if r["session_average_weight"] is not None \
            else "n/a — no session.shutdown tokenDetails seen"
        out.append(f"| {r['session_id']} | {r['turns']} | {avg_text} |")
    if section["sessions_truncated"]:
        out.append("\n(table capped by --top; ranked by assistant turns)")
    cc = section["carry_cost"]
    if cc:
        out.append(
            f"\ncontext carry cost (window): ${cc['carry_usd']:,.4f} ({cc['aic']:,.2f} AIC)"
        )
        if cc["unpriced_sessions"]:
            out.append(
                f" ({cc['priced_sessions']} of "
                f"{cc['priced_sessions'] + cc['unpriced_sessions']} session(s) priced)."
            )
        else:
            out.append(".")
        out.append(f"\n{cc['label']}")
    return "\n".join(out)


def render_overview_markdown(overview):
    out = [f"# Context weight — overview (last {overview['days']} day(s))\n"]
    sections = overview["sections"]
    if "claude" in sections:
        out.append(_render_claude_overview_section(sections["claude"]))
    if "codex" in sections:
        out.append(_render_codex_overview_section(sections["codex"]))
    if "copilot" in sections:
        out.append(_render_copilot_overview_section(sections["copilot"]))
    return "\n".join(out)


def build_overview_json(overview):
    """Identity wrapper, mirrors the other ``build_*_json`` names — ``overview`` is already a
    plain, JSON-safe dict with no combined dollar field anywhere in it."""
    return overview


# ---------------------------------------------------------------------------------------------
# Pure-function layer — audit (T6, PLAN D10): resident (always-loaded) surfaces vs a token
# budget, tokens only, never dollars — this section's inputs are byte-derived estimates, never
# measured usage, so D5 forbids pricing anything computed here.
#
# The founding measurement of this whole kit is that these resident surfaces are ALREADY small:
# on the motivating session CLAUDE.md/AGENTS.md/copilot-instructions together were under 1% of
# the observed ~463K-token/turn working set, and an 80% CLAUDE.md cut moved only ~2.4% of
# per-turn mass. A tool that prints "your CLAUDE.md is N tokens against a budget" invites exactly
# the wrong conclusion — that trimming config is the lever. So this audit does two things a plain
# budget-checker would not: it NAMES what it cannot measure (system prompt, tool schemas, plugin
# skill listings, MCP definitions — all resident, none of them a file this module can open), and
# when a session is supplied it PRINTS the reframe — resident surfaces as a percentage of that
# session's measured avg per-call weight — computed from real numbers, not asserted, so the
# percentage itself is the argument against re-optimizing config.

AUDIT_SURFACE_MAP = {
    "claude": ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md"),
    "codex": ("AGENTS.md",),
    "copilot": (".github/copilot-instructions.md", "AGENTS.md"),
}

AUDIT_UNMEASURABLE_LINE = (
    "system prompt, tool schemas, plugin skill listings, MCP definitions — resident but not "
    "measurable here; measure their effect with the session subcommand"
)

# D10 requires the audit to print the reframe UNCONDITIONALLY — with a real session it is a
# computed percentage; without one there is no avg weight to divide by, so fabricating a number
# would be exactly the fake precision D4/D5/D9 forbid. This qualitative line is the fallback: it
# still names the lever (working set, not config) so a bare `audit --project .` run — the common
# case — never reads as "your CLAUDE.md is eating N% of the budget, trim it."
AUDIT_QUALITATIVE_REFRAME_LINE = (
    "resident surfaces are typically a low single-digit % of per-call weight — the working set, "
    "not config, is the lever. Run with `--session <id>` to compute this against a real session."
)


def _audit_surface_entry(project_dir, rel_path, budget):
    """One surface, relative to ``project_dir``. Present: bytes (actual file size), est. tokens
    (``round(chars / EST_CHARS_PER_TOKEN)``, always labeled ``est.``), % of budget. Absent
    surfaces carry ONLY ``{"path", "present": False}`` — never a ``0`` standing in for
    "measured zero"; absence is a different fact from a zero-byte file."""
    rel_path = str(rel_path)
    full = Path(project_dir) / rel_path
    if not full.is_file():
        return {"path": rel_path, "present": False}
    raw = full.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    est_tokens = round(len(text) / EST_CHARS_PER_TOKEN)
    pct_budget = (est_tokens / budget * 100) if budget else 0.0
    return {
        "path": rel_path,
        "present": True,
        "bytes": len(raw),
        "est_tokens": est_tokens,
        "label": "est.",
        "pct_budget": pct_budget,
    }


def _audit_section(project_dir, rel_paths, budget):
    surfaces = [_audit_surface_entry(project_dir, rp, budget) for rp in rel_paths]
    total_est_tokens = sum(s["est_tokens"] for s in surfaces if s["present"])
    total_pct_budget = (total_est_tokens / budget * 100) if budget else 0.0
    return {
        "surfaces": surfaces,
        "total_est_tokens": total_est_tokens,
        "total_pct_budget": total_pct_budget,
        # "N tokens re-submitted (est.)" per 100 calls — a call-count multiplier, not a price
        # (D5): this section's resident mass is re-submitted whole on every one of those calls.
        "per_100_calls_tokens": total_est_tokens * 100,
    }


def audit_surfaces(project_dir, extra_surfaces, budget):
    """Pinned resident-surface lookup (PLAN D10), relative to ``project_dir``: claude ->
    CLAUDE.md/CLAUDE.local.md/.claude/CLAUDE.md; codex -> AGENTS.md; copilot ->
    .github/copilot-instructions.md + AGENTS.md (AGENTS.md is intentionally listed under BOTH
    codex and copilot — each harness's own section counts it in full, since each harness loads
    it independently; only the cross-harness reframe total dedupes it, per D10). ``--surface``
    extras land in their own ``extra`` section (path taken relative to ``project_dir``); a
    missing extra is a note, never an error. Returns ``(sections, notes)``."""
    project_dir = Path(project_dir)
    sections = {}
    for harness, rel_paths in AUDIT_SURFACE_MAP.items():
        sections[harness] = _audit_section(project_dir, rel_paths, budget)

    notes = []
    if extra_surfaces:
        extra_entries = [_audit_surface_entry(project_dir, rp, budget) for rp in extra_surfaces]
        for entry in extra_entries:
            if not entry["present"]:
                notes.append(f"extra surface not found: {entry['path']}")
        total_est_tokens = sum(s["est_tokens"] for s in extra_entries if s["present"])
        total_pct_budget = (total_est_tokens / budget * 100) if budget else 0.0
        sections["extra"] = {
            "surfaces": extra_entries,
            "total_est_tokens": total_est_tokens,
            "total_pct_budget": total_pct_budget,
            "per_100_calls_tokens": total_est_tokens * 100,
        }

    return sections, notes


def _audit_distinct_present_tokens(sections):
    """Combined est. tokens of all DISTINCT present surfaces across every section — a surface
    listed under two harnesses (AGENTS.md) counts once here, per D10's reframe formula."""
    seen = {}
    for section in sections.values():
        for s in section["surfaces"]:
            if s["present"]:
                seen[s["path"]] = s["est_tokens"]
    return sum(seen.values())


def build_audit_card(project_dir, sections, notes, budget, avg_weight=None, session_id=None,
                      session_note=None, constraints=None):
    """Assemble the full audit card. ``avg_weight`` (a session's measured avg per-call weight,
    from ``claude_call_weights`` — T1) is supplied only when ``--session`` resolved to a real
    session; the reframe percentage is COMPUTED from it (distinct present est. tokens / avg
    weight), never asserted. Without a session, ``session_note`` (if any) explains why the
    numeric reframe was not computed; ``qualitative_reframe_line`` is ALWAYS carried on the card
    (D10 — the audit prints the reframe unconditionally) so the renderer always has a fallback
    that names the lever without inventing a percentage. Neither path ever prices anything
    (D5 — audit is dollar-free). ``constraints`` (U2, PLAN E1), when supplied via ``--kit``, is
    the GUARDRAILS.md residency section built by ``build_audit_constraints_section`` — ``None``
    when ``--kit`` was never given, so the card key is simply absent from the rendered output."""
    distinct_present_tokens = _audit_distinct_present_tokens(sections)
    card = {
        "schema_version": CW_SCHEMA_VERSION,
        "project_dir": str(project_dir),
        "budget_tokens": budget,
        "sections": sections,
        "notes": notes,
        "distinct_present_tokens": distinct_present_tokens,
        "unmeasurable_line": AUDIT_UNMEASURABLE_LINE,
        "qualitative_reframe_line": AUDIT_QUALITATIVE_REFRAME_LINE,
        "reframe": None,
        "session_note": session_note,
        "constraints": constraints,
    }
    if avg_weight is not None and avg_weight > 0:
        pct = round(distinct_present_tokens / avg_weight * 100)
        card["reframe"] = {
            "session_id": session_id,
            "avg_weight": avg_weight,
            "distinct_present_tokens": distinct_present_tokens,
            "pct": pct,
        }
    return card


_AUDIT_SECTION_TITLES = (
    ("claude", "Claude"),
    ("codex", "Codex"),
    ("copilot", "Copilot"),
    ("extra", "Extra (--surface)"),
)


def _render_audit_section(title, section):
    out = [f"\n## {title}\n"]
    out.append("| surface | status | bytes | est. tokens | % of budget |")
    out.append("|---|---|---:|---:|---:|")
    for s in section["surfaces"]:
        if s["present"]:
            out.append(
                f"| {s['path']} | present | {s['bytes']:,} | {s['est_tokens']:,} est. "
                f"| {s['pct_budget']:.0f}% |"
            )
        else:
            out.append(f"| {s['path']} | absent | — | — | — |")
    out.append(
        f"\ntotal: {section['total_est_tokens']:,} est. tokens "
        f"({section['total_pct_budget']:.0f}% of budget) · "
        f"per 100 calls: {section['per_100_calls_tokens']:,} tokens re-submitted (est.)"
    )
    return "\n".join(out)


def render_audit_markdown(card):
    """Renders the reframe line FIRST, right under the title — before any budget table — so it
    cannot be mistaken for a footnote (per this task's brief: the reframe is the point of the
    subcommand, not an afterthought). It prints UNCONDITIONALLY (D10): with a resolved
    ``--session`` it is the computed numeric percentage; otherwise — including the bare
    ``audit --project .`` path, which is the common case — it falls back to the qualitative
    ``AUDIT_QUALITATIVE_REFRAME_LINE`` rather than fabricating a number or omitting the reframe
    entirely, because a bare run with only a per-harness token table and no reframe reads as
    "your CLAUDE.md is eating N% of the budget, trim it" — exactly the conclusion this kit
    exists to refute. The fixed unmeasurable-surfaces line always closes the output. No dollar
    figure appears anywhere in this function (D5 — audit is tokens only)."""
    out = [f"# Context weight — resident-surface audit ({card['project_dir']})\n"]

    reframe = card.get("reframe")
    if reframe:
        out.append(
            f"**resident surfaces ≈ {reframe['pct']}% of this session's avg per-call weight "
            f"({reframe['distinct_present_tokens']:,} of {reframe['avg_weight']:,} tokens) — "
            "the working set, not config, is the lever.**\n"
        )
    else:
        out.append(f"**{card['qualitative_reframe_line']}**\n")
        if card.get("session_note"):
            out.append(f"{card['session_note']}\n")

    out.append(f"budget: {card['budget_tokens']:,} tokens\n")

    for key, title in _AUDIT_SECTION_TITLES:
        section = card["sections"].get(key)
        if section is None:
            continue
        out.append(_render_audit_section(title, section))

    if card.get("constraints"):
        out.append(_render_audit_constraints_section(card["constraints"]))

    if card["notes"]:
        out.append("\n## Notes\n")
        for n in card["notes"]:
            out.append(f"- {n}")

    out.append(f"\n{AUDIT_UNMEASURABLE_LINE}")
    return "\n".join(out)


def build_audit_json(card):
    """Identity wrapper, mirrors the other ``build_*_json`` names — ``card`` is already a plain,
    JSON-safe dict with no dollar field anywhere in it (D5)."""
    return card


# ---------------------------------------------------------------------------------------------
# Pure-function layer — constraints (evidence-loop kit U2, PLAN E1): whether GUARDRAILS.md
# content for one kit is resident in the reconstructed window, at what estimated weight, and
# how that weight trends across the session's growth curve. This is the MEASUREMENT half of
# constraint survival — the evidence-loop kit's execute-skill edit (U1) guarantees a GUARDRAILS
# re-read at every PHASE START and states plainly that the skill cannot detect compaction, so a
# post-compaction re-read is an opportunistic extra and never coverage; this module only ever
# REPORTS residency, it never re-asserts, injects, or otherwise changes what is in the window
# (out-of-scope fence: analysis never becomes behavior). Claude-only, the same D3 rung as
# `watch`/content-attribution — Codex's rollout logs carry no content provenance to find a Read
# of GUARDRAILS.md in, and Copilot's events carry no tool content at all — so a non-Claude
# invocation prints `CONSTRAINTS_REFUSAL_LINE` (below) and exits 0, following `watch`'s actual
# precedent: a bespoke, subcommand-named refusal naming the question THIS subcommand cannot
# answer, never a fidelity line borrowed from a surface that answers a different question.

GUARDRAILS_FILENAME = "GUARDRAILS.md"

# Same shape as WATCH_REFUSAL_LINE, and for the same reason: a refusal must name its own
# subcommand, say which question is unanswerable on the other harnesses and why, and point the
# reader at what they CAN get. Deliberately not CODEX_NO_PROVENANCE_LINE / COPILOT_NO_CURVE_LINE
# — those two caption output this subcommand does not produce (a byte-share table; a growth
# curve) and neither one says the RESIDENCY question is the one that cannot be answered.
CONSTRAINTS_REFUSAL_LINE = (
    "constraints: Claude sessions only — GUARDRAILS.md residency cannot be answered on Codex or "
    "Copilot: neither harness's logs record the content a tool call read, so there is no way to "
    "tell whether guardrails content ever entered the window, let alone whether it survived a "
    "compaction (see `audit --kit` for the file's size on disk, and `session` for each harness's "
    "honest fidelity)"
)

CONSTRAINTS_NOT_FOUND_LINE = (
    "no read of {path} found in this transcript — GUARDRAILS.md content for this kit was never "
    "loaded into context here"
)

# Why a NO verdict is not, by itself, an indictment of the orchestrator (U1's landed contract).
# The execute skill guarantees a fences re-read at every PHASE START and explicitly declines to
# guarantee one per compaction ("this skill cannot detect compaction ... treat it as an
# opportunistic extra, never as coverage"). This card measures against compaction events, so a
# loop honoring U1 perfectly still shows NO whenever a compaction lands mid-phase — legitimate
# coarseness on both sides, not a violation, and the reader is owed that context next to the
# verdict rather than left to infer a failure that did not happen.
CONSTRAINTS_PHASE_ANCHOR_NOTE = (
    "note: the execute skill's re-read guarantee is anchored to PHASE STARTS, not to compaction "
    "(it cannot detect compaction at all), so a compaction landing mid-phase can legitimately "
    "show NO here until the next phase boundary re-reads the fences — see `session` for this "
    "transcript's compaction detail."
)


def _constraints_eviction_phrase(compaction_basis):
    """How to word the not-resident case for a given ``_resident_window_slice`` basis, so an
    INFERRED compaction always reads as an inference and a confirmed one always reads as the
    recorded marker it is (PLAN E4). ``DROP_FRACTION`` is rendered from the constant, never
    restated as a literal."""
    drop = f"{DROP_FRACTION:.0%}"
    if compaction_basis == "confirmed":
        return (
            "evicted by a confirmed compaction — an isCompactSummary marker recorded in the "
            "transcript — with no re-read since"
        )
    if compaction_basis == "inferred":
        return (
            f"evicted by an INFERRED compaction — a weight drop of at least {drop}, inferred "
            "from the curve rather than read off a recorded marker — with no re-read since"
        )
    if compaction_basis == "confirmed+inferred":
        return (
            "evicted by a confirmed compaction — an isCompactSummary marker, also visible as a "
            f"weight drop of at least {drop} — with no re-read since"
        )
    return "no longer in the reconstructed window, and no re-read since"


def _guardrails_path_matches(salient, guardrails_path):
    """True when a Read tool_result's ``salient`` (the ``file_path`` recorded on that Read's
    ``tool_use`` block) refers to the SAME file as ``guardrails_path``. Two-tier match:

    Tier 1 — LEXICAL, always tried first: ``os.path.abspath`` on both sides (``normpath``
    composed with a join onto the current working directory for a relative input), touching
    no filesystem (no stat, no symlink walk, no existence check). This is the load-bearing
    tier for testability: it remains exactly as checkable against a fictional path as a real
    one, which is what every test above this one exercises.

    The cwd join is the load-bearing part of tier 1, not an incidental upgrade over
    ``normpath``. Claude Code records ``file_path`` as an ABSOLUTE path, while ``--kit`` is
    routinely given relatively (the form CLAUDE.md uses throughout). Under a bare ``normpath``
    those two spellings of the same file never compare equal, so a relative ``--kit`` produced
    a confident ``CONSTRAINTS_NOT_FOUND_LINE`` — "never loaded into context here" — for a
    session that demonstrably DID read the fences. That line states a fact about the SESSION;
    it must never be reachable by a fact about the ARGUMENT.

    Tier 2 — INODE IDENTITY, only when tier 1 fails AND both paths exist on disk:
    ``os.path.samefile``, which stats both paths and compares ``st_dev``/``st_ino``. This
    reconciles a path reached through a symlink, and (on a case-insensitive filesystem) the
    same path spelled in different case — neither of which a lexical compare can ever see.
    Note ``os.path.realpath`` does NOT close this gap: on macOS it preserves the given case, so
    two differently-cased spellings of the same file still disagree after ``realpath``.
    ``samefile`` is stat-based identity, not path rewriting, so it succeeds where ``realpath``
    would not. Any ``OSError`` from the stat (permission denied, race where a path vanishes
    between the ``exists()`` check and the stat, etc.) degrades to "no match" rather than
    raising — a residency card must never crash on a stat.

    What this still cannot do: match a path that does not exist on disk. A fictional path (the
    shape every test above this one uses) never reaches tier 2 — the ``exists()`` guard sends
    it straight to "no match" if tier 1 didn't already resolve it — so those tests keep passing
    unchanged and stay real filesystem-free.
    """
    if not salient:
        return False
    a = os.path.abspath(str(salient))
    b = os.path.abspath(str(guardrails_path))
    if a == b:
        return True
    if not (os.path.exists(a) and os.path.exists(b)):
        return False
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def find_guardrails_reads(records, guardrails_path):
    """Every Read of ``guardrails_path`` found in ``records``, in file order.

    Reuses the SAME tool_use_id -> (tool, salient) mapping idiom ``attribute_growth``/
    ``classify_prunable`` already build (never a third derivation of it), then walks ``user``
    tool_result blocks whose mapped tool is ``"Read"`` and whose salient matches
    ``guardrails_path`` (``_guardrails_path_matches``). Sidechain records are skipped in both
    passes (D7) — a subagent's own read never entered the DRIVER's window, so it cannot make
    GUARDRAILS content resident for the session being measured here.

    Returns a list of ``{"record", "timestamp", "est_tokens"}`` dicts, oldest first. ``record``
    is the raw parsed ``user`` object itself (not a copy), so residency can be checked against
    ``_resident_window_records``'s own output by object identity. ``est_tokens`` is the
    ``_serialize_len(...) / EST_CHARS_PER_TOKEN`` heuristic (the same sizing rule
    ``attribute_growth`` uses) — an ``est.`` figure, never a measured token count.
    """
    tool_map = {}
    for obj in records:
        if not isinstance(obj, dict) or obj.get("isSidechain"):
            continue
        if obj.get("type") != "assistant":
            continue
        msg = obj.get("message") if isinstance(obj.get("message"), dict) else None
        content = msg.get("content") if msg else None
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tid = block.get("id")
                if tid:
                    name = block.get("name") or "(unknown)"
                    tool_map[tid] = (name, _salient_for(name, block.get("input")))

    reads = []
    for obj in records:
        if not isinstance(obj, dict) or obj.get("isSidechain"):
            continue
        if obj.get("type") != "user":
            continue
        msg = obj.get("message") if isinstance(obj.get("message"), dict) else None
        content = msg.get("content") if msg else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not (isinstance(block, dict) and block.get("type") == "tool_result"):
                continue
            tool, salient = tool_map.get(block.get("tool_use_id"), ("(unknown)", ""))
            if tool != "Read" or not _guardrails_path_matches(salient, guardrails_path):
                continue
            est_tokens = round(_serialize_len(block.get("content")) / EST_CHARS_PER_TOKEN)
            reads.append({
                "record": obj, "timestamp": obj.get("timestamp"), "est_tokens": est_tokens,
            })
    return reads


def _constraints_residency(records, calls, guardrails_path):
    """Core residency computation, shared verbatim by the standalone ``constraints`` card and
    the ``audit`` section below so the two never drift into two different notions of "resident".

    Reuses ``_resident_window_slice`` (the T10/D15 cutoff, UNCHANGED in behavior) to find the
    currently reconstructed window — never a second cutoff derivation — and checks, by object
    identity, whether the MOST RECENT ``find_guardrails_reads`` hit (if any) survived into that
    slice: that is the resident/not-resident verdict. "Trend" is one row per read found ANYWHERE
    in the transcript (not just the current window), each positioned against the session's own
    growth curve by locating the last ``calls`` entry at or before that read's own timestamp —
    so a reader can see guardrails content enter the window, and whether it was still there
    after any compaction since (the exact decay this measurement exists to catch).

    ``compaction_basis`` carries the slice's own ``"confirmed"``/``"inferred"``/
    ``"confirmed+inferred"``/``None`` fact straight through to both renderings and to the JSON,
    so the not-resident case can say whether the compaction that evicted the content was a
    recorded marker or an inference from the weight curve. Asserting an inferred compaction as a
    known one is exactly the confidence overreach PLAN E4 forbids — and this card's entire
    subject is compaction, so it is the last place to collapse the distinction.
    """
    reads = find_guardrails_reads(records, guardrails_path)
    resident_records, compaction_basis = _resident_window_slice(records)
    resident_ids = {id(o) for o in resident_records}
    call_timestamps = [c.get("timestamp") for c in calls]

    trend = []
    for r in reads:
        ts = r["timestamp"]
        eligible = [i for i, cts in enumerate(call_timestamps) if cts and ts and cts <= ts]
        call_index = eligible[-1] if eligible else None
        trend.append({
            "call_index": call_index,
            "timestamp": ts,
            "est_tokens": r["est_tokens"],
            "resident_now": id(r["record"]) in resident_ids,
        })

    last = reads[-1] if reads else None
    resident = bool(last) and id(last["record"]) in resident_ids
    current_weight = last["est_tokens"] if resident else None

    return {
        "reads": len(reads),
        "resident": resident,
        "current_weight_est_tokens": current_weight,
        "weight_label": "est." if current_weight is not None else None,
        "compaction_basis": compaction_basis,
        "trend": trend,
        "not_found_line": (
            None if reads else CONSTRAINTS_NOT_FOUND_LINE.format(path=guardrails_path)
        ),
    }


def build_constraints_card(kit_dir, records, calls, session_id=None):
    """Assemble the standalone ``constraints`` card: whether GUARDRAILS.md content for
    ``kit_dir`` is resident in the reconstructed window, at what estimated weight, and how that
    weight trends across this session's growth curve. Measurement only — see the section
    comment above for the enforcement/measurement split this belongs to."""
    guardrails_path = str(Path(kit_dir) / GUARDRAILS_FILENAME)
    residency = _constraints_residency(records, calls, guardrails_path)
    return {
        "schema_version": CW_SCHEMA_VERSION,
        "found": True,
        "harness": "claude",
        "session_id": session_id,
        "kit_dir": str(kit_dir),
        "guardrails_path": guardrails_path,
        "file_exists_now": Path(guardrails_path).is_file(),
        **residency,
    }


def build_absent_constraints_card(kit_dir, session_id, projects_dir):
    """Clean "nothing found" card (exit 0, never an error) for an absent projects dir or a
    session id with no matching transcript — mirrors ``build_absent_session_card``."""
    return {
        "schema_version": CW_SCHEMA_VERSION,
        "found": False,
        "harness": "claude",
        "session_id": session_id,
        "kit_dir": str(kit_dir),
        "message": (
            f"No claude transcript found for session {session_id or '(latest)'} "
            f"under {projects_dir}."
        ),
    }


def render_constraints_markdown(card):
    if not card.get("found", True):
        return f"# Context weight — constraints ({card['kit_dir']})\n\n{card['message']}\n"

    out = [f"# Context weight — constraints {card['session_id']} ({card['kit_dir']})\n"]
    out.append(f"guardrails file: {card['guardrails_path']}\n")
    if not card["file_exists_now"]:
        out.append(
            "(note: this path does not exist on disk right now — reporting on what the "
            "transcript recorded, which may be stale)\n"
        )

    if card["reads"] == 0:
        out.append(f"\n{card['not_found_line']}")
        return "\n".join(out)

    if card["resident"]:
        out.append(
            f"resident: YES — {card['current_weight_est_tokens']:,} est. tokens currently in "
            "the reconstructed window\n"
        )
    else:
        out.append(
            "resident: NO — read earlier this session but not in the current reconstructed "
            f"window ({_constraints_eviction_phrase(card.get('compaction_basis'))})\n"
        )
        out.append(f"{CONSTRAINTS_PHASE_ANCHOR_NOTE}\n")
    out.append(f"{card['reads']} read(s) of this file found in the transcript.\n")

    out.append("\n## Weight trend across the growth curve (est.)\n")
    out.append("| call # | still resident now | est. tokens |")
    out.append("|---:|---|---:|")
    for t in card["trend"]:
        call_label = (t["call_index"] + 1) if t["call_index"] is not None else "—"
        resident_label = "yes" if t["resident_now"] else "no"
        out.append(f"| {call_label} | {resident_label} | {t['est_tokens']:,} est. |")

    out.append(f"\nbasis: {ATTRIBUTION_BASIS}")
    return "\n".join(out)


def build_constraints_json(card):
    """Identity wrapper, mirrors the other ``build_*_json`` names."""
    return card


def build_audit_constraints_section(kit_dir, budget, records=None, calls=None,
                                     session_note=None):
    """The ``"constraints"`` section added to the ``audit`` card by its own ``--kit`` flag:
    reuses ``_audit_surface_entry`` (never a second file-size reader) for the GUARDRAILS.md
    file's own present/bytes/est_tokens/pct_budget row, plus — only when ``records``/``calls``
    were also supplied (i.e. ``--session`` resolved too) — the SAME ``_constraints_residency``
    computation the standalone ``constraints`` card uses. Without a session, ``residency`` stays
    ``None`` and ``session_note`` (e.g. "residency requires --session — omitted") explains why,
    never a fabricated resident/not-resident verdict."""
    guardrails_path = str(Path(kit_dir) / GUARDRAILS_FILENAME)
    section = {
        "kit_dir": str(kit_dir),
        "guardrails_path": guardrails_path,
        "file": _audit_surface_entry(kit_dir, GUARDRAILS_FILENAME, budget),
        "residency": None,
        "session_note": session_note,
    }
    if records is not None and calls is not None:
        section["residency"] = _constraints_residency(records, calls, guardrails_path)
    return section


def _render_audit_constraints_section(section):
    out = ["\n## Constraints (GUARDRAILS.md residency)\n"]
    f = section["file"]
    if f["present"]:
        out.append(
            f"guardrails file: {section['guardrails_path']} — {f['bytes']:,} bytes, "
            f"{f['est_tokens']:,} est. tokens ({f['pct_budget']:.0f}% of budget)\n"
        )
    else:
        out.append(f"guardrails file: {section['guardrails_path']} — absent\n")

    residency = section["residency"]
    if residency is None:
        out.append(f"\n{section['session_note'] or 'residency requires --session — omitted'}")
        return "\n".join(out)

    if residency["reads"] == 0:
        out.append(f"\n{residency['not_found_line']}")
        return "\n".join(out)

    if residency["resident"]:
        out.append(
            f"\nresident: YES — {residency['current_weight_est_tokens']:,} est. tokens "
            "currently in the reconstructed window"
        )
    else:
        out.append(
            "\nresident: NO — read earlier this session but not in the current reconstructed "
            f"window ({_constraints_eviction_phrase(residency.get('compaction_basis'))})"
        )
        out.append(f"\n{CONSTRAINTS_PHASE_ANCHOR_NOTE}")
    out.append(f"\n{residency['reads']} read(s) of this file found in the transcript.")
    return "\n".join(out)


# ---------------------------------------------------------------------------------------------
# Synthetic demo fixtures (PLAN D11, T7). Moved here from tests/test_context_weight.py (the one
# sanctioned test-file refactor named in T7's brief) because ``demo`` builds these fixtures at
# run time and this module cannot import the test file. Every value below reproduces, byte for
# byte in substance, the pinned fixtures T1 (Claude), T3 (Codex), T4 (Copilot), and T6 (audit)
# already established and pinned tests against — this is the SAME fixture content, not a new
# one. Model ids are NEVER hardcoded here: every caller passes in a model id resolved at run
# time from that harness's own pricing file (see ``cmd_demo`` below).


def _demo_ts(n):
    base = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(minutes=n)).isoformat().replace("+00:00", "Z")


def _demo_assistant_record(msg_id, model, in_, cache_read, cache_write, out, minute,
                            tool_use=None, is_sidechain=False):
    content = []
    if tool_use:
        content.append({
            "type": "tool_use",
            "id": tool_use["id"],
            "name": tool_use["name"],
            "input": tool_use["input"],
        })
    rec = {
        "type": "assistant",
        "timestamp": _demo_ts(minute),
        "message": {
            "id": msg_id,
            "model": model,
            "usage": {
                "input_tokens": in_,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_write,
                "output_tokens": out,
            },
            "content": content,
        },
    }
    if is_sidechain:
        rec["isSidechain"] = True
    return rec


def _demo_user_tool_result(tool_use_id, content_text, minute):
    return {
        "type": "user",
        "timestamp": _demo_ts(minute),
        "message": {
            "content": [
                {"type": "tool_result", "tool_use_id": tool_use_id, "content": content_text},
            ],
        },
    }


def demo_claude_fixture_lines(model_id):
    """The pinned Claude demo fixture (T1's brief; PLAN D11), as JSONL text lines. Weights
    ``[10000, 20000, 30000, 8000]``, avg ``17000``, peak ``30000``, total ``68000``, one inferred
    compaction (``30000`` -> ``8000``), sidechain ``1`` call / ``5000`` tokens; attribution ranks
    Bash ``5000 est.`` then Read ``/workspace/demo.txt`` ``2000 est.``, assistant output
    (measured) ``750``, unattributed ``12250 est.`` (measured growth ``20000`` minus attributed
    ``7000`` minus measured assistant output ``750``, per T13)."""
    records = [
        _demo_assistant_record("m1", model_id, 9000, 0, 1000, 200, 0,
                                tool_use={"id": "toolu_d1", "name": "Bash",
                                          "input": {"command": "ls -la"}}),
        _demo_user_tool_result("toolu_d1", "x" * 20000, 1),
        _demo_assistant_record("m2", model_id, 1000, 10000, 9000, 300, 2,
                                tool_use={"id": "toolu_d2", "name": "Read",
                                          "input": {"file_path": "/workspace/demo.txt"}}),
        _demo_user_tool_result("toolu_d2", "y" * 8000, 3),
        _demo_assistant_record("m3", model_id, 1000, 20000, 9000, 150, 4),
        _demo_assistant_record("m4", model_id, 8000, 0, 0, 100, 5),
        _demo_assistant_record("m5", model_id, 4000, 1000, 0, 50, 6, is_sidechain=True),
    ]
    return [json.dumps(r) for r in records]


def demo_codex_fixture_records(model):
    """The pinned Codex demo fixture (T3's brief; PLAN D11): one ``turn_context`` record, then
    three per-turn ``last_token_usage`` containers -> weights ``[3000, 8000, 13000]``, avg
    ``8000``, curve kind ``"per-turn"``."""
    return [
        {"type": "turn_context", "payload": {"model": model}},
        {"type": "event_msg", "payload": {"info": {"last_token_usage": {
            "input_tokens": 3000, "cached_input_tokens": 0, "output_tokens": 100}}}},
        {"type": "event_msg", "payload": {"info": {"last_token_usage": {
            "input_tokens": 2000, "cached_input_tokens": 6000, "output_tokens": 200}}}},
        {"type": "event_msg", "payload": {"info": {"last_token_usage": {
            "input_tokens": 1000, "cached_input_tokens": 12000, "output_tokens": 300}}}},
    ]


def demo_copilot_fixture_lines(model):
    """The pinned Copilot demo fixture (T4's brief; PLAN D11), as JSONL text lines: two
    ``assistant.message`` events (outputTokens ``100``, ``200``) plus one ``session.shutdown``
    carrying ``tokenDetails`` (input ``10000``, cache_read ``30000``, cache_write ``2000``,
    output ``300``) -> ``2`` turns, session-average weight ``21000`` (``(10000 + 30000 + 2000)
    // 2``)."""
    records = [
        {"type": "session.start", "timestamp": "2026-06-30T10:00:00Z",
         "data": {"selectedModel": model}},
        {"type": "assistant.message", "timestamp": "2026-06-30T10:01:00Z",
         "data": {"model": model, "outputTokens": 100, "apiCallId": "cw-a1"}},
        {"type": "assistant.message", "timestamp": "2026-06-30T10:02:00Z",
         "data": {"model": model, "outputTokens": 200, "apiCallId": "cw-a2"}},
        {"type": "session.shutdown", "timestamp": "2026-06-30T10:03:00Z", "data": {
            "totalNanoAiu": 1_000_000, "totalPremiumRequests": 1, "currentModel": model,
            "tokenDetails": {
                "input": {"tokenCount": 10000}, "cache_read": {"tokenCount": 30000},
                "cache_write": {"tokenCount": 2000}, "output": {"tokenCount": 300},
            },
        }},
    ]
    return [json.dumps(r) for r in records]


def demo_audit_fixture(project_dir):
    """The pinned audit demo fixture (T6's brief; PLAN D11): ``CLAUDE.md`` 2000 chars,
    ``AGENTS.md`` 1200 chars, ``.github/copilot-instructions.md`` 800 chars -> est. tokens
    ``500``/``300``/``200`` = ``10%``/``6%``/``4%`` of the ``5000``-token default budget.
    Creates the files under ``project_dir`` and returns it as a ``Path``."""
    d = Path(project_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / "CLAUDE.md").write_text("a" * 2000)
    (d / "AGENTS.md").write_text("b" * 1200)
    gh = d / ".github"
    gh.mkdir(parents=True, exist_ok=True)
    (gh / "copilot-instructions.md").write_text("c" * 800)
    return d


def demo_constraints_with_lines(model_id, kit_dir):
    """The pinned constraints-WITH-guardrails demo fixture (U2 brief; PLAN E1/E4): one Read of
    ``<kit_dir>/GUARDRAILS.md`` (content 400 chars -> 100 est. tokens) followed by one more call
    with no weight drop, so ``_resident_window_records`` never scopes past the read — the
    content stays resident through to the end of the session."""
    guardrails_path = str(Path(kit_dir) / GUARDRAILS_FILENAME)
    records = [
        _demo_assistant_record(
            "cw1", model_id, 1000, 0, 0, 50, 0,
            tool_use={"id": "toolu_g1", "name": "Read", "input": {"file_path": guardrails_path}},
        ),
        _demo_user_tool_result("toolu_g1", "g" * 400, 1),
        _demo_assistant_record("cw2", model_id, 1200, 1000, 400, 60, 2),
    ]
    return [json.dumps(r) for r in records]


def demo_constraints_without_lines(model_id):
    """The pinned constraints-WITHOUT-guardrails demo fixture (U2 brief; PLAN E1/E4): a normal
    working session that never reads GUARDRAILS.md at all — exercises the honest
    ``CONSTRAINTS_NOT_FOUND_LINE`` fallback rather than inventing a resident/not-resident
    verdict the transcript doesn't support."""
    records = [
        _demo_assistant_record(
            "cw3", model_id, 1000, 0, 0, 50, 0,
            tool_use={"id": "toolu_g2", "name": "Bash", "input": {"command": "pytest"}},
        ),
        _demo_user_tool_result("toolu_g2", "ok" * 10, 1),
        _demo_assistant_record("cw4", model_id, 900, 500, 0, 40, 2),
    ]
    return [json.dumps(r) for r in records]


DEMO_HEADER = (
    "# Context weight — demo\n\n"
    "Synthetic smoke across all three harnesses plus the resident-surface audit and the "
    "GUARDRAILS.md constraint-residency card. Every fixture below is generated fresh inside a "
    "throwaway temp directory and discarded when this command exits — no real `~/.claude`, "
    "`~/.codex`, or `~/.copilot` data is read or written."
)


def _first_sonnet_model_id(pricing):
    for key, v in pricing["models"].items():
        if v.get("tier") == "sonnet":
            return key
    raise SystemExit("no sonnet-tier model found in data/pricing.json")


def build_demo_cards():
    """Build all six demo cards (Claude session, Codex session, Copilot session, audit, and two
    ``constraints`` cards — one session that reads GUARDRAILS.md and stays resident, one that
    never reads it) inside ONE ``tempfile.TemporaryDirectory()`` (precedent:
    ``routing_scorecard.run_demo``) and return them as plain dicts — the temp dir is gone by the
    time this function returns, per D8/D11. Model ids are resolved at run time (never
    hardcoded): the first sonnet-tier key of ``data/pricing.json`` for Claude, the first model
    key of ``pricing.codex.json`` for Codex, the first model key of ``pricing.copilot.json`` for
    Copilot."""
    claude_pricing = cr.load_pricing()
    codex_pricing = cx.load_pricing()
    copilot_pricing = cp.load_pricing()
    claude_model = _first_sonnet_model_id(claude_pricing)
    codex_model = next(iter(codex_pricing["models"]))
    copilot_model = next(iter(copilot_pricing["models"]))

    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)

        # -- Claude ---------------------------------------------------------------------------
        projects_dir = tmp / "projects"
        proj_dir = projects_dir / "demo-proj"
        proj_dir.mkdir(parents=True)
        claude_file = proj_dir / "demo-claude.jsonl"
        claude_file.write_text("\n".join(demo_claude_fixture_lines(claude_model)) + "\n")

        main_transcript = sc.find_main_transcript(None, projects_dir)
        claude_session_id = main_transcript.stem
        files = sc.gather_files(main_transcript, [], [])
        main_objs = _read_jsonl_objs(files[0]) if files else []
        calls, sidechain, notes = claude_call_weights(main_objs)
        drops = detect_drops([c["weight"] for c in calls])
        attribution_entries, attribution_notes = attribute_growth(main_objs)
        claude_card = build_session_card(
            claude_session_id, files, calls, sidechain, notes, drops, claude_pricing, top=20,
            attribution_entries=attribution_entries, attribution_notes=attribution_notes,
        )

        # -- Codex ------------------------------------------------------------------------------
        codex_home = tmp / "codex-home"
        codex_dir = codex_home / "sessions" / "2026" / "07" / "01"
        codex_dir.mkdir(parents=True)
        codex_lines = [json.dumps(r) for r in demo_codex_fixture_records(codex_model)]
        codex_file = codex_dir / "rollout-demo.jsonl"
        codex_file.write_text("\n".join(codex_lines) + "\n")

        rollout_path = _select_codex_rollout(codex_home, None)
        codex_session_id = rollout_path.stem
        codex_card = build_codex_session_card(
            codex_session_id, rollout_path, codex_lines, codex_pricing, top=20,
        )

        # -- Copilot ----------------------------------------------------------------------------
        copilot_home = tmp / "copilot-home"
        copilot_dir = copilot_home / "session-state" / "demo-copilot-sess"
        copilot_dir.mkdir(parents=True)
        copilot_lines = demo_copilot_fixture_lines(copilot_model)
        (copilot_dir / "events.jsonl").write_text("\n".join(copilot_lines) + "\n")

        events_path = _select_copilot_session(copilot_home, None)
        copilot_parsed = cp.parse_events(copilot_lines)
        copilot_session_id = events_path.parent.name
        copilot_card = copilot_session_card(
            copilot_parsed, copilot_pricing, session_id=copilot_session_id,
        )

        # -- Audit (wired to the Claude fixture so the reframe line shows) ----------------------
        audit_project_dir = tmp / "audit-proj"
        demo_audit_fixture(audit_project_dir)
        budget = DEFAULT_SURFACE_BUDGET_TOKENS
        sections, audit_notes = audit_surfaces(audit_project_dir, [], budget)
        audit_card = build_audit_card(
            audit_project_dir, sections, audit_notes, budget,
            avg_weight=claude_card["avg_weight"], session_id=claude_card["session_id"],
        )

        # -- Constraints (evidence-loop kit U2, PLAN E1) -----------------------------------------
        kit_dir = tmp / "demo-kit"
        kit_dir.mkdir(parents=True)
        (kit_dir / GUARDRAILS_FILENAME).write_text(
            "Kit-scoped guardrails fixture text for the constraints demo — not this repo's own "
            "GUARDRAILS.md."
        )

        with_objs = [json.loads(ln) for ln in demo_constraints_with_lines(claude_model, kit_dir)]
        with_calls, _with_sc, _with_notes = claude_call_weights(with_objs)
        constraints_with_card = build_constraints_card(
            kit_dir, with_objs, with_calls, session_id="demo-constraints-with",
        )

        without_objs = [json.loads(ln) for ln in demo_constraints_without_lines(claude_model)]
        without_calls, _wo_sc, _wo_notes = claude_call_weights(without_objs)
        constraints_without_card = build_constraints_card(
            kit_dir, without_objs, without_calls, session_id="demo-constraints-without",
        )

    # Every card is plain, JSON-safe data by here — the temp dir above is already gone.
    return (
        claude_card, codex_card, copilot_card, audit_card,
        constraints_with_card, constraints_without_card,
    )


def cmd_demo(args):
    (claude_card, codex_card, copilot_card, audit_card,
     constraints_with_card, constraints_without_card) = build_demo_cards()

    if args.json:
        payload = {
            "schema_version": CW_SCHEMA_VERSION,
            "demo": True,
            "claude": build_session_json(claude_card),
            "codex": build_codex_session_json(codex_card),
            "copilot": build_copilot_session_json(copilot_card),
            "audit": build_audit_json(audit_card),
            "constraints_with_guardrails": build_constraints_json(constraints_with_card),
            "constraints_without_guardrails": build_constraints_json(constraints_without_card),
        }
        print(json.dumps(payload, indent=2))
    else:
        print(DEMO_HEADER)
        print("\n" + render_session_markdown(claude_card))
        print("\n" + render_codex_session_markdown(codex_card))
        print("\n" + render_copilot_session_markdown(copilot_card))
        print("\n" + render_audit_markdown(audit_card))
        print("\n" + render_constraints_markdown(constraints_with_card))
        print("\n" + render_constraints_markdown(constraints_without_card))
    return 0


# ---------------------------------------------------------------------------------------------
# CLI.


def _cmd_session_codex(args):
    codex_home = Path(args.codex_home)
    rollout_path = _select_codex_rollout(codex_home, args.session)
    if rollout_path is None:
        card = build_absent_session_card("codex", args.session, codex_home)
    else:
        lines = rollout_path.read_text(errors="replace").splitlines()
        session_id = args.session or rollout_path.stem
        pricing = cx.load_pricing()
        card = build_codex_session_card(session_id, rollout_path, lines, pricing, top=args.top)

    if args.json:
        print(json.dumps(build_codex_session_json(card), indent=2))
    else:
        print(render_codex_session_markdown(card))
    return 0


def _cmd_session_copilot(args):
    copilot_home = Path(args.copilot_home)
    events_path = _select_copilot_session(copilot_home, args.session)
    if events_path is None:
        card = build_absent_session_card("copilot", args.session, copilot_home)
    else:
        lines = events_path.read_text(errors="replace").splitlines()
        parsed = cp.parse_events(lines)
        session_id = args.session or events_path.parent.name
        pricing = cp.load_pricing()
        card = copilot_session_card(parsed, pricing, session_id=session_id)

    if args.json:
        print(json.dumps(build_copilot_session_json(card), indent=2))
    else:
        print(render_copilot_session_markdown(card))
    return 0


def cmd_session(args):
    if args.harness == "codex":
        return _cmd_session_codex(args)
    if args.harness == "copilot":
        return _cmd_session_copilot(args)
    if args.harness != "claude":
        print(f"`session --harness {args.harness}` lands in a later task.")
        return 0

    projects_dir = Path(args.projects_dir)
    main_transcript = sc.find_main_transcript(args.session, projects_dir)
    if main_transcript is None:
        card = build_absent_session_card("claude", args.session, projects_dir)
    else:
        session_id = args.session or main_transcript.stem
        task_dirs = []
        if not args.no_subagents:
            task_dirs = [Path(d) for d in args.tasks_dir] or sc.discover_task_dirs(session_id)
        files = sc.gather_files(main_transcript, task_dirs, [])

        main_objs = _read_jsonl_objs(files[0]) if files else []
        subagent_objs = []
        for f in files[1:]:
            # Subagent *.output records are, by construction, sidechain mass from the main
            # driver's point of view (D7) — tag them so claude_call_weights routes them into
            # the sidechain aggregate regardless of their own isSidechain flag.
            for obj in _read_jsonl_objs(f):
                if isinstance(obj, dict):
                    tagged = dict(obj)
                    tagged["isSidechain"] = True
                    subagent_objs.append(tagged)

        combined_objs = main_objs + subagent_objs
        calls, sidechain, notes = claude_call_weights(combined_objs)
        drops = detect_drops([c["weight"] for c in calls])
        attribution_entries, attribution_notes = attribute_growth(combined_objs)
        pricing = cr.load_pricing()
        card = build_session_card(
            session_id, files, calls, sidechain, notes, drops, pricing, top=args.top,
            attribution_entries=attribution_entries, attribution_notes=attribution_notes,
        )

    if args.json:
        print(json.dumps(build_session_json(card), indent=2))
    else:
        print(render_session_markdown(card))
    return 0


def cmd_watch(args):
    """`watch` is Claude-only by design (D3/PLAN interfaces) — there is no `--harness` flag on
    this subcommand. A ``codex``/``copilot`` positional value is the sanctioned way (matching
    ``routing_scorecard.py``'s optional-positional idiom elsewhere in this repo) for a
    Codex/Copilot invocation to reach the pinned refusal line and still exit 0."""
    if args.harness != "claude":
        print(WATCH_REFUSAL_LINE)
        return 0

    projects_dir = Path(args.projects_dir)
    main_transcript = sc.find_main_transcript(args.session, projects_dir)
    if main_transcript is None:
        card = build_absent_watch_card(args.session, projects_dir)
    else:
        session_id = args.session or main_transcript.stem
        task_dirs = [Path(d) for d in args.tasks_dir] or sc.discover_task_dirs(session_id)
        files = sc.gather_files(main_transcript, task_dirs, [])

        main_objs = _read_jsonl_objs(files[0]) if files else []
        subagent_objs = []
        for f in files[1:]:
            # Same D7 tagging as `session` — subagent *.output records are sidechain mass from
            # the main driver's point of view regardless of their own isSidechain flag.
            for obj in _read_jsonl_objs(f):
                if isinstance(obj, dict):
                    tagged = dict(obj)
                    tagged["isSidechain"] = True
                    subagent_objs.append(tagged)

        combined_objs = main_objs + subagent_objs
        calls, sidechain, _notes = claude_call_weights(combined_objs)
        pricing = cr.load_pricing()
        card = build_watch_card(
            session_id, calls, sidechain, combined_objs, pricing,
            window_tokens_override=args.window_tokens,
        )

    if args.json:
        print(json.dumps(build_watch_json(card), indent=2))
    else:
        print(render_watch_markdown(card))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(
        prog="context_weight.py",
        description="Per-call context weight, growth curves, and honest fidelity per harness.",
    )
    sub = ap.add_subparsers(dest="command", required=True)

    session = sub.add_parser("session", help="Per-session context-weight card")
    session.add_argument("--harness", choices=["claude", "codex", "copilot"], default="claude")
    session.add_argument("--session", default=None, help="session id (default: latest)")
    session.add_argument("--top", type=int, default=20, help="max curve-table rows")
    session.add_argument("--projects-dir", default=str(DEFAULT_PROJECTS_DIR))
    session.add_argument("--tasks-dir", action="append", default=[],
                          help="dir of subagent *.output transcripts (repeatable)")
    session.add_argument("--no-subagents", action="store_true",
                          help="analyze only the main transcript")
    session.add_argument("--codex-home", default=str(DEFAULT_CODEX_HOME))
    session.add_argument("--copilot-home", default=str(DEFAULT_COPILOT_HOME))
    session.add_argument("--json", action="store_true")

    overview = sub.add_parser("overview", help="Cross-session working-set table, per harness")
    overview.add_argument(
        "--harness", choices=["all"] + list(OVERVIEW_HARNESSES), default="all"
    )
    overview.add_argument("--days", type=int, default=7)
    overview.add_argument("--top", type=int, default=10, help="max ranked rows per section")
    overview.add_argument("--projects-dir", default=str(DEFAULT_PROJECTS_DIR))
    overview.add_argument("--codex-home", default=str(DEFAULT_CODEX_HOME))
    overview.add_argument("--copilot-home", default=str(DEFAULT_COPILOT_HOME))
    overview.add_argument("--json", action="store_true")

    audit = sub.add_parser(
        "audit", help="Resident-surface audit vs a token budget — tokens only, never dollars"
    )
    audit.add_argument("--project", default=".", help="project dir to scan (default: .)")
    audit.add_argument("--surface", action="append", default=[],
                        help="extra surface path, relative to --project (repeatable)")
    audit.add_argument("--budget-tokens", type=int, default=DEFAULT_SURFACE_BUDGET_TOKENS)
    audit.add_argument("--session", default=None,
                        help="session id; when given, prints the reframe line against that "
                             "session's avg per-call weight (omit to skip the reframe line)")
    audit.add_argument("--kit", default=None,
                        help="kit dir; adds a GUARDRAILS.md residency section (bytes/est. "
                             "tokens always; the resident/not-resident verdict needs --session "
                             "too, else it's honestly omitted)")
    audit.add_argument("--projects-dir", default=str(DEFAULT_PROJECTS_DIR))
    audit.add_argument("--json", action="store_true")

    watch = sub.add_parser(
        "watch",
        help="Live weight, distance to threshold, and what's safely prunable (Claude only)",
    )
    watch.add_argument(
        "harness", nargs="?", choices=["claude", "codex", "copilot"], default="claude",
        help="Claude only — there is no --harness on watch; passing codex/copilot here "
             "prints the honest refusal line and exits 0 (default: claude)",
    )
    watch.add_argument("--session", default=None, help="session id (default: latest)")
    watch.add_argument(
        "--window-tokens", type=int, default=None,
        help="override the context-window size (default: resolved from data/pricing.json's "
             "context_window for the session's current model — never hardcoded)",
    )
    watch.add_argument("--projects-dir", default=str(DEFAULT_PROJECTS_DIR))
    watch.add_argument("--tasks-dir", action="append", default=[],
                        help="dir of subagent *.output transcripts (repeatable)")
    watch.add_argument("--json", action="store_true")

    constraints = sub.add_parser(
        "constraints",
        help="GUARDRAILS.md residency for one kit in the reconstructed window (Claude only; "
             "Codex/Copilot print their existing fidelity-limit lines verbatim)",
    )
    constraints.add_argument("--harness", choices=["claude", "codex", "copilot"],
                              default="claude")
    constraints.add_argument("--kit", required=True, help="kit dir containing GUARDRAILS.md")
    constraints.add_argument("--session", default=None, help="session id (default: latest)")
    constraints.add_argument("--projects-dir", default=str(DEFAULT_PROJECTS_DIR))
    constraints.add_argument("--tasks-dir", action="append", default=[],
                              help="dir of subagent *.output transcripts (repeatable)")
    constraints.add_argument("--no-subagents", action="store_true",
                              help="analyze only the main transcript")
    constraints.add_argument("--json", action="store_true")

    demo = sub.add_parser(
        "demo", help="Synthetic cross-harness demo — all cards, no real data touched"
    )
    demo.add_argument("--json", action="store_true")

    return ap


def cmd_overview(args):
    overview = build_overview(
        args.harness, args.days, args.top,
        Path(args.projects_dir), Path(args.codex_home), Path(args.copilot_home),
    )
    if args.json:
        print(json.dumps(build_overview_json(overview), indent=2))
    else:
        print(render_overview_markdown(overview))
    return 0


def cmd_audit(args):
    project_dir = Path(args.project)
    budget = args.budget_tokens
    sections, notes = audit_surfaces(project_dir, args.surface, budget)

    avg_weight = None
    session_id = None
    session_note = None
    session_objs = None
    session_calls = None
    if args.session:
        projects_dir = Path(args.projects_dir)
        main_transcript = sc.find_main_transcript(args.session, projects_dir)
        if main_transcript is None:
            session_note = (
                f"session {args.session!r} not found under {projects_dir} "
                "— reframe line omitted."
            )
        else:
            objs = _read_jsonl_objs(main_transcript)
            calls, _sidechain, _notes = claude_call_weights(objs)
            session_objs, session_calls = objs, calls
            if calls:
                avg_weight = round(sum(c["weight"] for c in calls) / len(calls))
                session_id = args.session
            else:
                session_note = (
                    f"session {args.session!r} has no measurable calls "
                    "— reframe line omitted."
                )

    constraints_section = None
    if args.kit:
        constraints_note = None if session_objs is not None else (
            "residency requires --session — omitted"
        )
        constraints_section = build_audit_constraints_section(
            args.kit, budget, records=session_objs, calls=session_calls,
            session_note=constraints_note,
        )

    card = build_audit_card(
        project_dir, sections, notes, budget,
        avg_weight=avg_weight, session_id=session_id, session_note=session_note,
        constraints=constraints_section,
    )
    if args.json:
        print(json.dumps(build_audit_json(card), indent=2))
    else:
        print(render_audit_markdown(card))
    return 0


def cmd_constraints(args):
    """``constraints`` is Claude-only fidelity, the same D3 rung as ``watch``/content
    attribution: Codex has no content provenance to find a Read of GUARDRAILS.md in, and
    Copilot's events carry no tool content at all. A non-Claude invocation prints
    ``CONSTRAINTS_REFUSAL_LINE`` and exits 0 — following ``watch``'s actual precedent, whose
    ``WATCH_REFUSAL_LINE`` is bespoke and names its own subcommand rather than reusing a
    per-harness fidelity line. ``CODEX_NO_PROVENANCE_LINE`` and ``COPILOT_NO_CURVE_LINE`` stay
    exactly where they belong — captioning the byte-share table and the session-average card
    that actually produce them — and are deliberately NOT reused here, where neither the table
    nor the curve is printed and neither line answers the residency question."""
    if args.harness in ("codex", "copilot"):
        print(CONSTRAINTS_REFUSAL_LINE)
        return 0

    projects_dir = Path(args.projects_dir)
    main_transcript = sc.find_main_transcript(args.session, projects_dir)
    if main_transcript is None:
        card = build_absent_constraints_card(args.kit, args.session, projects_dir)
    else:
        session_id = args.session or main_transcript.stem
        task_dirs = []
        if not args.no_subagents:
            task_dirs = [Path(d) for d in args.tasks_dir] or sc.discover_task_dirs(session_id)
        files = sc.gather_files(main_transcript, task_dirs, [])

        main_objs = _read_jsonl_objs(files[0]) if files else []
        subagent_objs = []
        for f in files[1:]:
            # Same D7 tagging as `session`/`watch` — subagent *.output records are sidechain
            # mass from the main driver's point of view regardless of their own isSidechain flag.
            for obj in _read_jsonl_objs(f):
                if isinstance(obj, dict):
                    tagged = dict(obj)
                    tagged["isSidechain"] = True
                    subagent_objs.append(tagged)

        combined_objs = main_objs + subagent_objs
        calls, _sidechain, _notes = claude_call_weights(combined_objs)
        card = build_constraints_card(args.kit, combined_objs, calls, session_id=session_id)

    if args.json:
        print(json.dumps(build_constraints_json(card), indent=2))
    else:
        print(render_constraints_markdown(card))
    return 0


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.command == "session":
        return cmd_session(args)
    if args.command == "overview":
        return cmd_overview(args)
    if args.command == "audit":
        return cmd_audit(args)
    if args.command == "watch":
        return cmd_watch(args)
    if args.command == "constraints":
        return cmd_constraints(args)
    if args.command == "demo":
        return cmd_demo(args)
    print(f"`{args.command}` lands in a later task.")
    return 0


if __name__ == "__main__":
    main()
