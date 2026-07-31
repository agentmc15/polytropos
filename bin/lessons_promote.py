#!/usr/bin/env python3
"""bin/lessons_promote.py — draft-only lesson/defect promotion tool (PLAN.md E2, evidence-loop
kit).

Scans two READ-ONLY evidence sources:

  1. Every kit's ``NOTES.md`` under ``--kits-dir`` for ``defect:`` ledger lines (D1/D4
     grammar), reusing ``routing_scorecard.parse_defects`` via the lazy sibling-import idiom
     (``bin/`` is not a package) rather than re-implementing the grammar — a second regex
     could drift from the source of truth.
  2. The repo's ``tasks/lessons.md``. Despite the ``.md`` extension it is NOT prose: it is
     newline-delimited JSON objects, one per line, shaped
     ``{"date", "failure_pattern", "lesson", "applies_to": [...]}``. A malformed line is
     skipped with a note, never a crash — the file is hand-appended.

Clustering is on EXACT ``defect:`` kind tokens only — no fuzzy matching, no stemming, no
substring matching (PLAN.md tripwire: a coined synonym must never silently aggregate with an
established kind, which would destroy the very recurrence signal this tool exists to surface).
A candidate requires recurrence across >= RECURRENCE_GATE distinct kits (gate 1 — the ONE
pinned constant in this tool; no other hardcoded threshold exists here). Everything that does
not clear gate 1 is reported VERBATIM as residue, never guessed into a neighbouring cluster.

``tasks/lessons.md`` entries carry no kit attribution at all (only a date and free-text
``applies_to`` tags drawn from a different vocabulary than ``defect:`` kind tokens) — they
structurally cannot satisfy a kit-recurrence gate, and attempting to fold them into a
defect-kind cluster by matching against ``applies_to`` would itself be exactly the fuzzy
cross-vocabulary merge this tool refuses to do. So they are read, reported verbatim in their
own informational section, and never clustered or promoted.

Output is a DRAFT for a human (PLAN E2 gate 2 is the human, not this tool): every candidate
carries its evidence (kit, task, kind) so a reader can check it, and nothing here reads as a
decided rule.

WHERE OUTPUT GOES, stated as the guarantee this tool can actually enforce. ``--print`` writes
the draft to stdout and touches no file. Without ``--print`` the draft is written to exactly
one file, ``<--output-dir>/<--now>.md``. The DEFAULT ``--output-dir`` is the gitignored
``journal/promotions/`` path (the repo's root-anchored ``/journal/`` rule already covers it —
this tool adds no gitignore entry). ``--output-dir`` is OPERATOR-SUPPLIED, so the tool cannot
claim that every write it performs lands on an untracked path; it makes the narrower,
enforced claim instead:

  * ``--now`` must be a bare date-shaped token — a value carrying a path separator or ``..``
    is refused with a nonzero exit before anything is created (``validate_now_token``);
  * the final output path is RESOLVED and must lie inside the RESOLVED ``--output-dir``, or
    the run is refused with a nonzero exit having written and created nothing
    (``resolve_output_path``). Containment is the load-bearing check: it holds whatever
    ``--now`` contains, and it also catches an output name that is a symlink pointing out of
    the directory;
  * the confirmation line prints the RESOLVED path, so an operator's log shows where the file
    actually landed rather than an unresolved string that may traverse elsewhere.

No other path is opened for writing anywhere in this module.

``tasks/lessons.md`` is LIVE ROUTING INPUT — ``copilot/.github/skills/lessons-loop/SKILL.md``
and ``copilot/.github/agents/route.agent.md`` read it at session start. This tool opens it
STRICTLY READ-ONLY and never appends to it: promoting a lesson into that file is a human's
edit made after gate 2, never this tool's side effect.

Imports nothing that dispatches: no ``subprocess``, no harness-execute modules, no network.
Analysis never becomes behavior — this tool changes no routing, pin, or escalation logic
anywhere; it only reads ledgers and prints/writes a draft.
"""

import argparse
import importlib.util
import json
import os
import sys
from datetime import date
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_KITS_DIR = PLUGIN_ROOT / ".claude" / "kits"
DEFAULT_LESSONS_FILE = PLUGIN_ROOT / "tasks" / "lessons.md"
DEFAULT_OUTPUT_DIR = PLUGIN_ROOT / "journal" / "promotions"

# PLAN E2 gate 1 — the ONE pinned constant this tool hardcodes. No recurrence score, no
# confidence weighting, no other cutoff belongs here (GUARDRAILS.md: "thresholds come from
# data or don't exist").
RECURRENCE_GATE = 2

# AUTHORED TEXT, not a run-time read. `skills/architect/SKILL.md` already instructs the
# architect to write against recurring brief-defect kinds and names these by name, so part of
# what this draft surfaces is ALREADY in the scaffolding — a gate-2 reader needs to know that
# before treating an entry as a new rule to add.
#
# This is deliberately a hand-checked constant rather than a parse of that skill file: this
# tool must not read, depend on, or couple itself to routing scaffolding at run time
# (GUARDRAILS: analysis never becomes behavior). The cost of that choice is that the list can
# go stale silently, so the draft labels it as an authored claim to re-check and carries the
# date it was checked — it never presents it as a live fact.
SCAFFOLDING_NOTE_CHECKED = "2026-07-26"
ALREADY_IN_SCAFFOLDING = ("stale-pin", "tautological-verify", "missing-helper")
SCAFFOLDING_NOTE_SOURCE = "skills/architect/SKILL.md"


def validate_now_token(now):
    """Return an error string if ``now`` is not a bare date-shaped token, else ``None``.

    ``--now`` names the output FILE, so a value carrying a path separator or ``..`` is a
    traversal, not a date. Containment (``resolve_output_path``) is the guarantee that
    actually holds regardless of this check; this one exists because it fails earlier and
    with a message that names the real problem.
    """
    if now is None or not now.strip():
        return "--now must not be empty"
    seps = {"/", "\\", os.sep}
    if os.altsep:
        seps.add(os.altsep)
    if any(s in now for s in seps):
        return (f"--now must be a bare date-shaped token naming one file, not a path: "
                f"{now!r} contains a path separator")
    if ".." in now:
        return (f"--now must be a bare date-shaped token naming one file: {now!r} contains "
                f"'..'")
    return None


def resolve_output_path(output_dir, now):
    """``(path, error)`` — the resolved draft path, or an error string and no path.

    The load-bearing fence of this tool (GUARDRAILS: "draft-only means zero writes to
    scaffolding"). Both the directory and the final file path are RESOLVED and the file is
    required to lie inside the directory, so no ``--now`` value can escape ``--output-dir``
    and a final component that is a symlink out of the directory is refused too. Creates
    nothing — the caller makes the directory only after this returns a path.
    """
    err = validate_now_token(now)
    if err:
        return None, err
    out_dir = Path(output_dir).resolve()
    candidate = (out_dir / f"{now}.md").resolve()
    try:
        candidate.relative_to(out_dir)
    except ValueError:
        return None, (f"refusing to write outside --output-dir: resolved output path "
                      f"{candidate} is not inside resolved --output-dir {out_dir}")
    return candidate, None


def _load_scorecard_module():
    """Lazy sibling import of bin/routing_scorecard.py (mirrors the established pattern in
    ``bin/codex_usage.py``/``bin/copilot_usage.py`` for cross-``bin/`` reuse without a
    package). Used ONLY for its ``parse_defects`` ledger-line parser.
    """
    path = Path(__file__).resolve().parent / "routing_scorecard.py"
    spec = importlib.util.spec_from_file_location("routing_scorecard", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def discover_kits(kits_dir):
    """Sorted list of kit directories under ``kits_dir`` that carry a ``NOTES.md``. Read-only;
    a missing ``kits_dir`` yields an empty list rather than an error.
    """
    p = Path(kits_dir)
    if not p.is_dir():
        return []
    return sorted(
        (d for d in p.iterdir() if d.is_dir() and (d / "NOTES.md").is_file()),
        key=lambda d: d.name,
    )


def collect_defect_evidence(kits_dir, parse_defects):
    """Scan every kit's NOTES.md for ``defect:`` lines -> ``(evidence, notes)``.

    ``evidence``: list of ``{"kit", "task", "kind"}`` dicts, one per defect event, in
    kit-name order then file order. ``notes``: parser notes prefixed with the owning kit name
    so a malformed line is never silently dropped.
    """
    evidence = []
    notes = []
    for kit_dir in discover_kits(kits_dir):
        text = (kit_dir / "NOTES.md").read_text(encoding="utf-8")
        events, kit_notes = parse_defects(text)
        for ev in events:
            evidence.append({"kit": kit_dir.name, "task": ev["task"], "kind": ev["kind"]})
        for n in kit_notes:
            notes.append(f"{kit_dir.name}: {n}")
    return evidence, notes


def cluster_defects(evidence):
    """Cluster defect evidence on EXACT kind tokens (no fuzzy matching — PLAN tripwire).

    Returns ``(candidates, residue)``, both ``{kind: {"kits": [...], "evidence": [...]}}``.
    A kind lands in ``candidates`` only when its evidence spans
    ``>= RECURRENCE_GATE`` distinct kit names; otherwise it lands in ``residue`` verbatim —
    never merged into a neighbouring kind. Deterministic: kinds sorted alphabetically,
    evidence sorted by ``(kit, task)``.
    """
    by_kind = {}
    for ev in evidence:
        by_kind.setdefault(ev["kind"], []).append(ev)

    candidates = {}
    residue = {}
    for kind in sorted(by_kind):
        items = sorted(by_kind[kind], key=lambda e: (e["kit"], e["task"]))
        kits = sorted({e["kit"] for e in items})
        bucket = candidates if len(kits) >= RECURRENCE_GATE else residue
        bucket[kind] = {"kits": kits, "evidence": items}
    return candidates, residue


def load_lessons(lessons_file):
    """Parse ``tasks/lessons.md`` as JSONL -> ``(lessons, notes)``.

    NOT prose despite the ``.md`` extension: newline-delimited JSON objects
    ``{"date", "failure_pattern", "lesson", "applies_to": [...]}``. A missing file, a blank
    line, a line that fails to parse as JSON, or an object missing a required field is
    skipped with a note rather than raising — the file is hand-appended.
    """
    p = Path(lessons_file)
    lessons = []
    notes = []
    if not p.is_file():
        notes.append(f"lessons file not found: {p}")
        return lessons, notes
    for i, raw in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            notes.append(f"tasks/lessons.md line {i}: malformed JSON, skipped ({e})")
            continue
        if not isinstance(obj, dict) or "failure_pattern" not in obj or "lesson" not in obj:
            notes.append(f"tasks/lessons.md line {i}: missing required field(s), skipped")
            continue
        lessons.append(obj)
    return lessons, notes


def _evidence_line(ev):
    return f"  - kit={ev['kit']} task={ev['task']} kind={ev['kind']}"


def _all_evidence(candidates, residue):
    """Every defect event across both buckets, in kind-then-(kit, task) order."""
    events = []
    for bucket in (candidates, residue):
        for kind in sorted(bucket):
            events.extend(bucket[kind]["evidence"])
    return events


def per_kit_evidence_counts(candidates, residue):
    """``{kit: defect-evidence-line count}`` over every kit that recorded ANY defect line.

    The gate-1 denominator lives here: a kit with a NOTES.md but no ``defect:`` line
    contributes nothing to clustering and must not be counted as if it had.
    """
    counts = {}
    for ev in _all_evidence(candidates, residue):
        counts[ev["kit"]] = counts.get(ev["kit"], 0) + 1
    return counts


def _scaffolding_suffix(kind):
    """Authored, hand-checked marker — never a run-time read of the skill file."""
    if kind in ALREADY_IN_SCAFFOLDING:
        return f" — ALREADY named in {SCAFFOLDING_NOTE_SOURCE} (authored note)"
    return ""


def render_draft(candidates, residue, lessons, notes, *, kits_scanned, today, self_kit=None):
    """Render the full draft text shared by both ``--print`` and the file-write path."""
    lines = []
    lines.append(f"# Lesson/defect promotion draft — {today}")
    lines.append("")
    lines.append(
        "Generated by bin/lessons_promote.py. This is a DRAFT for human review (PLAN.md E2 "
        "gate 2 is the human) — it edits nothing. Gate 1 implemented here: a defect-kind "
        "candidate requires recurrence across >= "
        f"{RECURRENCE_GATE} distinct kits, clustered on EXACT kind tokens only (no fuzzy "
        "matching). Nothing below is a decided rule; every candidate carries the evidence a "
        "reviewer needs to check it.")
    lines.append("")
    lines.append(
        "**What clearing gate 1 does NOT establish.** Recurrence is not importance — a kind "
        "that recurs cheaply and is caught every time may matter far less than one that "
        "appeared once and cost a day. A candidate at the gate's minimum rests on a SINGLE "
        "recurrence, which is two observations, not a trend. And a kind may already be "
        "covered by existing scaffolding, in which case its presence here is evidence that "
        "the existing rule is not landing — an argument for changing that rule, not for "
        "adding a new one. Gate 1 filters out what is provably one-off; it decides nothing "
        "about what is worth writing down.")
    lines.append("")
    lines.append(
        f"**Part of this list is already in the scaffolding.** {SCAFFOLDING_NOTE_SOURCE} "
        "already instructs the architect to write against recurring brief-defect kinds and "
        "names " + ", ".join(f"`{k}`" for k in ALREADY_IN_SCAFFOLDING) + " by name. Entries "
        "below carrying that marker are therefore not new proposals. This is an AUTHORED "
        f"note hand-checked on {SCAFFOLDING_NOTE_CHECKED} — the tool does not read that file "
        "at run time (it must not couple itself to routing scaffolding), so treat it as a "
        "claim to re-check, not a live fact.")
    lines.append("")

    per_kit = per_kit_evidence_counts(candidates, residue)
    kits_with_defects = len(per_kit)
    total_defect_evidence = sum(per_kit.values())

    lines.append("## Evidence base")
    lines.append("")
    lines.append(f"- Kits with a NOTES.md (scanned): {kits_scanned}")
    lines.append(
        f"- Kits that recorded ANY `defect:` line: {kits_with_defects} — **this, not the "
        "scanned count, is the gate-1 denominator**; the other "
        f"{max(kits_scanned - kits_with_defects, 0)} contribute no defect evidence at all.")
    lines.append(f"- Defect evidence lines: {total_defect_evidence}")
    lines.append(f"- tasks/lessons.md entries: {len(lessons)} (read-only; never appended to)")
    lines.append("")
    lines.append(
        "**Not scanned by this tool:** `reviewer:` lines, `outcome:` results (including "
        "retry-passes — the only failures this repo has actually recorded), and the NOTES "
        "prose, which is where most of this repo's adjudication is written down. A kit can "
        "carry thousands of words of hard-won lessons and still contribute zero `defect:` "
        "lines. Absence from this draft is therefore not absence of a lesson, and the "
        "coverage figure above is coverage of one ledger field, not of the corpus.")
    lines.append("")
    if per_kit:
        lines.append("Per-kit defect evidence (every contributing kit):")
        for kit in sorted(per_kit):
            lines.append(f"  - {kit}: {per_kit[kit]}")
        lines.append("")
    lines.append(
        "**Self-reference.** This corpus is not a closed past: a kit's own NOTES.md is "
        "scanned while that kit is still running, so a run can raise the counts of the very "
        "kinds it is reasoning about. That is deliberate — excluding the live kit would "
        "discard the freshest evidence and invite gaming — but it is self-amplifying and "
        "invisible from inside, so the per-kit contributions above are printed to be "
        "discounted against.")
    if self_kit is not None:
        contributed = per_kit.get(self_kit, 0)
        if contributed:
            kinds_here = sorted(
                {ev["kind"] for ev in _all_evidence(candidates, residue)
                 if ev["kit"] == self_kit})
            lines.append("")
            lines.append(
                f"This run names `{self_kit}` as the currently-executing kit: it contributed "
                f"{contributed} of {total_defect_evidence} defect evidence lines, across "
                + ", ".join(f"`{k}`" for k in kinds_here) + ".")
        else:
            lines.append("")
            lines.append(
                f"This run names `{self_kit}` as the currently-executing kit; it recorded no "
                "`defect:` line in this scan, so it contributed nothing to the figures above.")
    lines.append("")
    lines.append(
        "**Exposure, and the denominator this tool cannot compute.** Each entry below carries "
        f"its `N of {kits_with_defects} defect-recording kits` denominator, because a kind "
        "seen in 2 of many is weaker evidence than one seen in nearly all. The sharper figure "
        "— how many kits recorded defects AFTER a kind was first coined, which is what "
        "separates \"did not recur\" from \"could not yet have recurred\" — is NOT computed "
        "here: the ledger records no kit chronology, so this tool has no data-derived "
        "ordering of kits and will not invent one. Consequence a reader must carry: a kind "
        "coined in the newest kit looks identical to a kind that sat exposed across every "
        "kit and never came back. Low counts below are ambiguous between those two cases.")
    lines.append("")

    lines.append(f"## Candidates (recurrence >= {RECURRENCE_GATE} distinct kits)")
    lines.append("")
    if not candidates:
        lines.append(
            f"No defect kind met the >= {RECURRENCE_GATE}-kit recurrence gate on this scan.")
    else:
        for kind in sorted(candidates):
            entry = candidates[kind]
            lines.append(
                f"### `{kind}` — DRAFT candidate, recurs across {len(entry['kits'])} of "
                f"{kits_with_defects} defect-recording kits "
                f"({', '.join(entry['kits'])}) — NOT a decided rule, human review required"
                f"{_scaffolding_suffix(kind)}")
            lines.append("")
            lines.append("Evidence:")
            for ev in entry["evidence"]:
                lines.append(_evidence_line(ev))
            lines.append("")
    lines.append("")

    lines.append("## tasks/lessons.md entries (informational)")
    lines.append("")
    lines.append(
        "These carry no kit attribution (only a date and free-text `applies_to` tags drawn "
        "from a different vocabulary than defect kind tokens), so they structurally cannot "
        "satisfy the kit-recurrence gate above. Listed verbatim for human review — never "
        "clustered or promoted.")
    lines.append("")
    if not lessons:
        lines.append("No entries.")
    else:
        for entry in lessons:
            applies_to = entry.get("applies_to", [])
            lines.append(
                f"- date={entry.get('date', '?')} applies_to={applies_to}")
            lines.append(f"  failure_pattern: {entry.get('failure_pattern', '')}")
            lines.append(f"  lesson: {entry.get('lesson', '')}")
    lines.append("")

    lines.append("## Residue (single-kit or below the recurrence gate — verbatim, unclustered)")
    lines.append("")
    lines.append(
        "Below the gate is NOT a verdict of \"did not recur\". With no kit chronology in the "
        "ledger this tool cannot tell a kind that was exposed across many later kits and "
        "never came back from one coined in the most recent kit that has had barely any "
        "chance to recur. Both land here looking the same. Read a residue entry as "
        "\"insufficient evidence either way\", never as \"cleared\".")
    lines.append("")
    if not residue:
        lines.append("No residue.")
    else:
        for kind in sorted(residue):
            entry = residue[kind]
            lines.append(
                f"### `{kind}` — {len(entry['kits'])} of {kits_with_defects} "
                f"defect-recording kits ({', '.join(entry['kits'])}) — below the gate; "
                f"exposure unknown{_scaffolding_suffix(kind)}")
            for ev in entry["evidence"]:
                lines.append(_evidence_line(ev))
    lines.append("")

    if notes:
        lines.append("## Parse notes")
        lines.append("")
        for n in notes:
            lines.append(f"- {n}")
        lines.append("")

    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Draft-only lesson/defect promotion candidates (PLAN.md E2) — gate 2 is "
                    "the human. Reads kits and tasks/lessons.md strictly read-only and never "
                    "appends to them. Writes exactly one file: --print goes to stdout, "
                    "otherwise <--output-dir>/<--now>.md, whose resolved path must lie inside "
                    "the resolved --output-dir (the default output dir is gitignored).")
    ap.add_argument("--kits-dir", default=str(DEFAULT_KITS_DIR),
                    help="directory holding one subdir per kit, each with a NOTES.md "
                        f"(default: {DEFAULT_KITS_DIR})")
    ap.add_argument("--lessons-file", default=str(DEFAULT_LESSONS_FILE),
                    help=f"path to the JSONL lessons ledger (default: {DEFAULT_LESSONS_FILE})")
    ap.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR),
                    help="dir the draft is written under when --print is absent; the default "
                        "is gitignored, an operator-supplied one is containment-checked but "
                        f"cannot be known to be untracked (default: {DEFAULT_OUTPUT_DIR})")
    ap.add_argument("--now", default=date.today().isoformat(),
                    help="YYYY-MM-DD (default: today) — names the output file; must be a "
                        "bare token with no path separator and no '..'")
    ap.add_argument("--self-kit", dest="self_kit", default=None,
                    help="name of the kit whose run is producing this draft, so the draft can "
                        "label its own contribution to the corpus (the currently-executing "
                        "kit is scanned like any other and is never excluded)")
    ap.add_argument("--print", dest="do_print", action="store_true",
                    help="print the draft to stdout and write nothing")
    args = ap.parse_args(argv)

    now_err = validate_now_token(args.now)
    if now_err:
        print(f"lessons_promote: {now_err}", file=sys.stderr)
        return 2

    scorecard = _load_scorecard_module()
    defect_evidence, defect_notes = collect_defect_evidence(args.kits_dir, scorecard.parse_defects)
    candidates, residue = cluster_defects(defect_evidence)
    lessons, lesson_notes = load_lessons(args.lessons_file)
    notes = defect_notes + lesson_notes

    draft = render_draft(
        candidates, residue, lessons, notes,
        kits_scanned=len(discover_kits(args.kits_dir)), today=args.now,
        self_kit=args.self_kit)

    if args.do_print:
        print(draft, end="")
        return 0

    # Containment BEFORE creation: a refused run must leave no directory behind either.
    out_path, err = resolve_output_path(args.output_dir, args.now)
    if err:
        print(f"lessons_promote: {err}", file=sys.stderr)
        return 2
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(draft, encoding="utf-8")
    # RESOLVED path, so the operator's log records where the file actually landed.
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
