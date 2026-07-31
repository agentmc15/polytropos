#!/usr/bin/env python3
"""Verify-proof marker + enforcement hook for this repo's OWN execution kits
(`.claude/kits/<slug>/TASKS.md`) -- graph-convergence kit T4, PLAN.md D3/D10.

Three roles, stdlib-only, ZERO `Path.home()` calls anywhere in this module -- every path this
module touches comes from an explicit `--kit-dir` argument (record/precheck) or from the
PostToolUse payload's own `cwd`/`tool_input.file_path` fields (hook); nothing here ever reads
or writes a home directory.

  (a)  `record`   -- called by the verify path (the execute skill, or a driver) AFTER a task's
       own verify command exits 0. Writes a timestamped, gitignored marker at
       `<kit-dir>/verify-pass/<task-id>` that carries BOTH the timestamp AND the exact
       verify-command text it certified. Refuses to write the marker (nonzero exit, one-line
       reason, nothing written) when a `precheck` record for the SAME task id and the SAME
       verify-command text marked it tautological -- the verify command already passed BEFORE
       any implementation happened, so a later pass proves nothing (PLAN D10, red -> green
       discipline). The refusal lifts the moment the verify-command text changes.

  (a2) `precheck` -- run BEFORE implementation starts (right after a task flips to
       `in-progress`). FIRST deletes any existing verify-pass marker for the task id (see
       FRESHNESS NOTE below -- this is the freshness mechanism). Then runs the task's own
       verify command AGAINST THE PRE-TASK TREE through an injectable runner callable -- never
       a real `claude`/`copilot`/`codex` dispatch; the command is whatever the task's
       `- Verify:` line says, typically a `python3 -m unittest ...` invocation. If it already
       exits 0, this is a `tautological-verify` defect: precheck prints a `defect:` line and
       persists the fact so `record` (a) can refuse the pass marker until the command changes.
       If it exits nonzero, precheck persists a clean (non-tautological) result.

  (b)  `hook`     -- a PostToolUse command-hook entrypoint. Reads the hook event JSON on stdin
       (see PAYLOAD PROVENANCE below) and, when the edited file is a kit TASKS.md AND the edit
       flips a task's `- status:` line to `done`, exits nonzero with a one-line reason on
       stderr UNLESS (1) a verify-pass marker already exists for that task id AND (2) either
       the current verify command for that task in TASKS.md cannot be parsed (either dialect --
       see DIALECT COVERAGE below), or it matches the verify-command text the marker certified.
       Every other event (unrelated file,
       unrelated tool, an edit that never touches a `- status:` line, or one that doesn't
       introduce `done`) is a silent no-op -- exit 0, nothing printed.

PAYLOAD PROVENANCE (the PLAN.md "hook event surface" tripwire -- resolved, not guessed):
Checked 2026-07-26 against the official Claude Code hooks reference
(https://code.claude.com/docs/en/hooks, "PostToolUse input" section), fetched via WebFetch --
never by invoking the real `claude` binary. For the two tools that can write a file,
PostToolUse's `tool_input` is:
  - Edit:  {"file_path": ..., "edits": [{"operation": "str_replace", "old_str": ...,
            "new_str": ...}, ...]}
  - Write: {"file_path": ..., "file_contents": <the entire NEW file>}
Edit's `old_str`/`new_str` pair IS the diff already -- no separate diffing is required, so the
Edit path is fully supported below. Write's payload carries ONLY the new full-file content; it
has no prior content at all, so a genuine before/after status flip cannot be established for a
Write-based rewrite of a kit TASKS.md from the PostToolUse payload alone. This is a real, narrow
payload gap (Write only), not a reason to skip the whole hook: Edit is how this repo's own
`skills/execute/SKILL.md` and every driver actually flip a single `- status:` line (a targeted,
minimal-diff change -- exactly what the Edit tool is for). `hook` below enforces the Edit path
and is a silent no-op for a Write to a kit TASKS.md; this is documented, not invented.

FRESHNESS NOTE: the brief describes blocking a `done` flip "unless a marker newer than the
task's `in-progress` flip exists." The kit TASKS.md grammar records no per-status timestamp, so
there is no persisted "in-progress flip" instant to compare a marker's mtime against without
inventing a fourth subcommand outside this task's sanctioned three (this remains a genuine
brief defect against the architect -- see NOTES.md `underivable-requirement`). Freshness IS
derivable, though, from something the kit workflow really does carry: `precheck` is the
workflow's own analogue of the `in-progress` flip -- it is the thing that runs at the start of
every attempt, before implementation. So `precheck` now DELETES any existing verify-pass
marker for its task id before it does anything else (`run_precheck`, using `read_marker_time`
to report what it invalidated). That makes "a marker exists for task X" mean EXACTLY "`record`
ran after the most recent `precheck` for task X" -- ordering, not a raw timestamp comparison,
but a real freshness guarantee derived from the format the brief actually pins. A marker
written in an earlier attempt cannot survive a later `precheck`: flipping a task
done -> in-progress -> done again forces a new `precheck`, which erases the old marker, so the
second `done` flip is unenforced by a stale marker -- it needs its own fresh `record`.

This closes the "flip done -> in-progress -> done again on the original marker" gap, but NOT
the "verify command rewritten after the marker was earned" gap -- no ordering rule catches
that, because the command could change without any precheck/record cycle running again. That
gap is closed separately: the marker now stores the exact verify-command TEXT `record`
certified (not just a timestamp), and `hook` compares it against the task's CURRENT verify
command in TASKS.md at flip time, blocking on a mismatch.

DIALECT COVERAGE (counted, not assumed -- `_task_verify_cmd`): this repo's kits write a task's
verify command in two different ways, and the check binds on both. Of 27 kits, 2 use the
single-line ``- Verify: `<cmd>``` form and 25 use a `**Verify.**`/`**Verify:**` marker; 24 of
those 25 pair the marker with a fenced block this parser reads, and the last writes a backticked
one-liner instead of a fence (a third way, not parsed -- see below). Census: the check binds on
26 of 27 kits and on 222 of 239 task blocks. Parsing only the single-line form (as this module
originally did) bound on 2 kits and 17 task blocks -- and those two kits are the pair drafted
alongside this file, so the command-match half of the enforcement was INERT on every kit this
repo had actually executed. Residual limitation: if the task id has no heading, or its block
carries neither dialect (that one kit's backticked one-liner; a handful of orchestrator-added
remediation tasks that record their verification as prose; whatever a consumer repo invents),
the command-match check is skipped and only marker existence + precheck-freshness is enforced. That is the same fail-open-on-unparseable-
format posture the rest of this module uses (see PAYLOAD PROVENANCE's Write-tool gap), and it
is the safe direction here: a false MATCH would let a rewritten verify certify a flip, while a
false MISS would block a legitimate one, so the parser requires the fence to sit directly after
the marker rather than guessing.

Installation is consent-gated: this module never writes hooks or settings itself, and never
touches a home directory. See `skills/setup/SKILL.md` for the opt-in step a user runs to wire
`hook` into their OWN `~/.claude/settings.json` PostToolUse config -- never auto-installed.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

STATUSES = ("pending", "in-progress", "done", "blocked")
EM_DASH = " — "  # the kit TASKS.md heading separator (matches skills/execute/SKILL.md, codex_execute.py)

_DONE_STATUS_RE = re.compile(r'-\s*status:\s*done\b')
_KIT_TASKS_RE = re.compile(r'(^|/)\.claude/kits/[^/]+/TASKS\.md$')
_HEADING_LINE_RE = re.compile(r'^### (\S+)' + re.escape(EM_DASH))
_VERIFY_LINE_RE = re.compile(r'^-\s*Verify:\s*`(.*)`\s*$')
# The OTHER verify dialect this repo's kits actually use: a bold marker line (`**Verify.**` or
# `**Verify:**`) followed by a fenced block. Counted across this repo's 27 kits: 2 use the
# `- Verify: `cmd`` line above, 25 carry this marker (24 of them with a fence) -- so parsing only
# the first left the command-match check inert on every kit this repo had ever executed. Both
# dialects are supported below; see DIALECT COVERAGE in the module docstring for the full census.
_VERIFY_MARKER_RE = re.compile(r'^\*\*Verify[.:]\*\*\s*$')
_FENCE_PREFIX = "```"


# ---- TASKS.md heading walk (id resolution only -- no full task-field parsing needed here) ----

def _task_headings(text):
    """[(0-based line index, task id), ...] for every `### <id> — <title>` heading in `text`."""
    out = []
    for i, line in enumerate(text.splitlines()):
        if line.startswith("### ") and EM_DASH in line:
            heading = line[len("### "):]
            task_id = heading.split(EM_DASH, 1)[0].strip()
            if task_id:
                out.append((i, task_id))
    return out


def _task_id_for_line(text, line_index):
    """The id of the task block containing 0-based `line_index` (nearest heading at or before
    it), or None if `line_index` precedes every heading."""
    best = None
    for idx, task_id in _task_headings(text):
        if idx <= line_index:
            best = task_id
        else:
            break
    return best


def _task_id_from_snippet(snippet):
    """If `snippet` (an edit's old_str or new_str) itself contains a task heading line, return
    its task id; else None. This is the PRIMARY attribution path -- Edit requires old_str to be
    unique pre-edit, so a real edit that could be ambiguous without it (e.g. more than one task
    sharing the same status text) will already carry the heading in its snippet."""
    for line in snippet.splitlines():
        m = _HEADING_LINE_RE.match(line)
        if m:
            return m.group(1)
    return None


def _has_done_status(snippet):
    return bool(_DONE_STATUS_RE.search(snippet))


def is_kit_tasks_md(file_path):
    """True if `file_path` (any separator style, absolute or relative) ends in
    `.claude/kits/<slug>/TASKS.md`."""
    return bool(_KIT_TASKS_RE.search(str(file_path).replace("\\", "/")))


def _fenced_verify_cmd(block_lines):
    """The contents of the fenced block that FOLLOWS a `**Verify.**` / `**Verify:**` marker
    inside `block_lines` (one task's lines), stripped; None if that dialect isn't present.

    Ported in approach from `claude_execute._extract_verify` (marker -> fence -> contents,
    `.strip()`ed so both sides of the comparison normalize identically -- the drivers pass
    exactly that stripped text to `record`/`precheck` as `--verify-cmd`). Not IMPORTED from
    there: `claude_execute` lazy-imports THIS module, and importing back would be circular.

    Two deliberate widenings over the sibling, each forced by what this repo's kits contain:
      * both `**Verify.**` and `**Verify:**` are accepted (22 kits use the dot form, 3 the
        colon form);
      * the fence's language tag is optional (```` ```bash ```` in 24 kits, a bare ```` ``` ````
        in one), because a language tag is decoration here -- this module never EXECUTES the
        text it extracts, it only compares it.

    One deliberate tightening: the fence must be the first non-blank content after the marker.
    The sibling scans forward for the next ```` ```bash ```` anywhere, which is safe when the
    result is only ever executed for the task it was read from; here a false positive (grabbing
    an unrelated later fence) would BLOCK a legitimate `done` flip, so adjacency is required and
    anything else falls through to None -> fail open, the posture the module docstring pins.
    """
    for i, line in enumerate(block_lines):
        if not _VERIFY_MARKER_RE.match(line.strip()):
            continue
        for j in range(i + 1, len(block_lines)):
            stripped = block_lines[j].strip()
            if not stripped:
                continue
            if not stripped.startswith(_FENCE_PREFIX):
                break  # marker followed by prose, not a fence -- not this dialect
            body = []
            for k in range(j + 1, len(block_lines)):
                if block_lines[k].strip().startswith(_FENCE_PREFIX):
                    return "\n".join(body).strip()
                body.append(block_lines[k])
            return None  # unterminated fence -- unparsable, fail open
    return None


def _task_verify_cmd(text, task_id):
    """The exact text of `task_id`'s verify command as written in `text` (a full TASKS.md), or
    None if the task id has no heading in `text`, or its block carries no parsable verify
    command. BOTH dialects this repo's kits use are supported (see `_VERIFY_MARKER_RE`'s counts):
    the single-line ``- Verify: `<cmd>``` form is tried first (unchanged behavior for a kit that
    has one), then the `**Verify.**`/`**Verify:**` + fenced-block form via
    `_fenced_verify_cmd`. Used only to detect a verify command rewritten after a pass marker was
    earned -- never to derive a command for execution (this module never runs a TASKS.md-sourced
    command itself; `precheck`/`record` always take `--verify-cmd` explicitly from the caller)."""
    headings = _task_headings(text)
    lines = text.splitlines()
    start = None
    end = len(lines)
    for i, (idx, tid) in enumerate(headings):
        if tid == task_id:
            start = idx
            end = headings[i + 1][0] if i + 1 < len(headings) else len(lines)
            break
    if start is None:
        return None
    block_lines = lines[start:end]
    for line in block_lines:
        m = _VERIFY_LINE_RE.match(line.strip())
        if m:
            return m.group(1)
    return _fenced_verify_cmd(block_lines)


# ---- marker + precheck-record storage (all under the gitignored verify-pass/ dir) ------------

def marker_dir(kit_dir):
    return Path(kit_dir) / "verify-pass"


def marker_path(kit_dir, task_id):
    return marker_dir(kit_dir) / task_id


def _precheck_path(kit_dir, task_id):
    return marker_dir(kit_dir) / f"{task_id}.precheck.json"


def write_marker(kit_dir, task_id, verify_cmd, now=None):
    """Write/overwrite the pass marker for `task_id`; return its Path. Stores BOTH the UTC
    timestamp and the exact `verify_cmd` text this pass certified (JSON payload) -- `hook`
    later compares that text against the task's CURRENT `- Verify:` line to catch a verify
    command rewritten after the marker was earned. `now` is injectable so tests never depend
    on wall-clock time."""
    now = now or datetime.now(timezone.utc)
    d = marker_dir(kit_dir)
    d.mkdir(parents=True, exist_ok=True)
    p = marker_path(kit_dir, task_id)
    payload = {
        "checked_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verify_cmd": verify_cmd,
    }
    p.write_text(json.dumps(payload, indent=2) + "\n")
    return p


def read_marker(kit_dir, task_id):
    """The full stored marker payload dict (`{"checked_at", "verify_cmd"}`) for `task_id`, or
    None if no marker exists, or it is unparsable (e.g. a legacy plain-timestamp marker from
    before this payload existed -- fails closed, same as "no marker")."""
    p = marker_path(kit_dir, task_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def read_marker_time(kit_dir, task_id):
    """The UTC timestamp recorded in `task_id`'s marker, or None if no marker exists (or it is
    unparsable). Used by `run_precheck` to report the pass it is about to invalidate -- see
    FRESHNESS NOTE."""
    payload = read_marker(kit_dir, task_id)
    if payload is None:
        return None
    try:
        return datetime.strptime(payload["checked_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except (KeyError, ValueError):
        return None


def marker_exists(kit_dir, task_id):
    return marker_path(kit_dir, task_id).exists()


# ---- (a2) precheck -----------------------------------------------------------------------

def run_precheck(kit_dir, task_id, verify_cmd, runner, now=None):
    """Run `verify_cmd` (via the injectable `runner(cmd) -> (rc, output)`) against the
    PRE-TASK tree and persist the result under `<kit_dir>/verify-pass/<task_id>.precheck.json`.

    FIRST, unconditionally deletes any existing verify-pass marker for `task_id` -- `precheck`
    is the kit workflow's own analogue of the task's `in-progress` flip (it runs once per
    attempt, before implementation), so this is the freshness mechanism described in the
    module docstring's FRESHNESS NOTE: after this call, "a marker exists for task_id" means
    exactly "`record` ran after THIS precheck". Prints one line noting what it invalidated
    (via `read_marker_time`) when a prior marker existed.

    Returns the precheck record dict. Prints an in-grammar
    `defect: <task-id> kind=tautological-verify ...` line to stdout when the command already
    exits 0 pre-task (PLAN D10) -- field order is load-bearing, see the comment at the print."""
    invalidated_at = read_marker_time(kit_dir, task_id)
    if marker_exists(kit_dir, task_id):
        marker_path(kit_dir, task_id).unlink()
        when = (
            invalidated_at.strftime("%Y-%m-%dT%H:%M:%SZ")
            if invalidated_at is not None
            else "unknown time (unparsable marker)"
        )
        print(
            f"precheck: invalidated the prior verify-pass marker for task={task_id} "
            f"(it certified a pass recorded {when}) -- precheck starts a new attempt, so a "
            f"fresh `record` pass is required before this task can flip to done again "
            f"(PLAN D3 freshness)"
        )

    rc, _output = runner(verify_cmd)
    now = now or datetime.now(timezone.utc)
    record = {
        "task_id": task_id,
        "verify_cmd": verify_cmd,
        "rc": rc,
        "tautological": rc == 0,
        "checked_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    d = marker_dir(kit_dir)
    d.mkdir(parents=True, exist_ok=True)
    _precheck_path(kit_dir, task_id).write_text(json.dumps(record, indent=2) + "\n")
    if record["tautological"]:
        # IN-GRAMMAR `defect:` ledger line -- the repo's grammar is
        # `defect: <task-id> kind=<kebab-token>` (bin/routing_scorecard.py's DEFECT_RE takes the
        # first token after `defect:` as the task id and reads `kind=` out of the rest), and
        # `tautological-verify` is an EXISTING kind (skills/execute/SKILL.md's list). Field order
        # matters: `defect: tautological-verify task=<id>` carries no `kind=` pair, so
        # `parse_defects` drops it with an "unrecognized defect line" note -- a line that looks
        # like ledger data and is silently discarded. Trailing prose after the `kind=` pair is
        # tolerated by the parser (unknown pairs are ignored), so the human reason still ships.
        print(
            f"defect: {task_id} kind=tautological-verify verify already passes on the "
            f"pre-task tree (rc 0) -- the verify command must be able to fail first "
            f"(red -> green, PLAN D10); a pass marker is refused until it changes"
        )
    return record


def read_precheck(kit_dir, task_id):
    """The stored precheck record dict for `task_id`, or None if `precheck` was never run (or
    its record is unreadable)."""
    p = _precheck_path(kit_dir, task_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


# ---- (a) record ---------------------------------------------------------------------------

def run_record(kit_dir, task_id, verify_cmd, now=None):
    """Write the pass marker for `task_id`, UNLESS a stored precheck record for the SAME
    `verify_cmd` text marked it tautological -- in which case refuse (PLAN D10) and write
    nothing. Returns (ok: bool, message: str)."""
    prev = read_precheck(kit_dir, task_id)
    if prev is not None and prev.get("tautological") and prev.get("verify_cmd") == verify_cmd:
        return False, (
            f"refused: task {task_id}'s verify command already passed on the pre-task tree "
            f"(tautological-verify) and has not changed since -- change the verify command "
            f"before it can certify a pass (red -> green, PLAN D10)"
        )
    write_marker(kit_dir, task_id, verify_cmd, now=now)
    return True, f"recorded pass marker for {task_id}"


# ---- (b) hook -----------------------------------------------------------------------------

def detect_done_flip(event):
    """Given a parsed PostToolUse event dict, return (kit_dir: Path, task_id: str) if this
    event flips a task's `- status:` line to `done` inside a kit TASKS.md, else None.

    Only the Edit tool is supported -- see the module docstring's PAYLOAD PROVENANCE note for
    why a Write cannot be diff-checked from its PostToolUse payload alone."""
    if event.get("tool_name") != "Edit":
        return None
    tool_input = event.get("tool_input") or {}
    file_path = tool_input.get("file_path")
    if not file_path or not is_kit_tasks_md(file_path):
        return None

    cwd = event.get("cwd") or "."
    abs_path = Path(file_path)
    if not abs_path.is_absolute():
        abs_path = Path(cwd) / file_path

    current_text = None  # lazily read only if the fallback attribution path needs it

    for edit in tool_input.get("edits") or []:
        old_str = edit.get("old_str", "")
        new_str = edit.get("new_str", "")
        if not (_has_done_status(new_str) and not _has_done_status(old_str)):
            continue

        task_id = _task_id_from_snippet(new_str) or _task_id_from_snippet(old_str)
        if task_id is None:
            # Fallback: the snippet alone didn't carry a heading (only possible when the
            # status text was already unique file-wide). Best-effort: locate the first matching
            # occurrence in the CURRENT on-disk file (already updated -- PostToolUse fires after
            # the tool ran) and walk backward to the nearest heading.
            if current_text is None:
                if not abs_path.exists():
                    current_text = ""
                else:
                    current_text = abs_path.read_text()
            idx = current_text.find(new_str) if current_text else -1
            if idx != -1:
                line_index = current_text.count("\n", 0, idx)
                task_id = _task_id_for_line(current_text, line_index)

        if task_id:
            return abs_path.parent, task_id
    return None


def evaluate_hook_event(event):
    """Pure decision function over one parsed PostToolUse event: (allow: bool, message: str).
    `allow=True, message=""` for every non-matching event (the overwhelming majority).

    Blocks unless BOTH hold:
      1. A verify-pass marker exists for the task id. Because `precheck` deletes any prior
         marker before it runs (see FRESHNESS NOTE), existence here already means "`record`
         ran after the most recent `precheck`" -- the freshness property, not raw existence.
      2. The marker's certified `verify_cmd` text still matches the task's CURRENT verify
         command in TASKS.md -- either dialect (``- Verify: `cmd``` or a `**Verify.**`/
         `**Verify:**` fenced block; see DIALECT COVERAGE in the module docstring). If the task
         id or its verify command can't be parsed at all, this check is skipped -- fail-open on
         an unparsable format, same posture as the rest of this module."""
    found = detect_done_flip(event)
    if found is None:
        return True, ""
    kit_dir, task_id = found

    marker = read_marker(kit_dir, task_id)
    if marker is None:
        return False, (
            f"kit-verify-hook: task {task_id} was flipped to 'done' but no verify-pass marker "
            f"exists for it -- run `precheck`, implement, then run the task's verify command "
            f"and `record` a pass before marking it done (PLAN D3). `precheck` invalidates any "
            f"marker from a prior attempt, so marker existence here is the freshness proof."
        )

    tasks_path = kit_dir / "TASKS.md"
    current_text = tasks_path.read_text() if tasks_path.exists() else ""
    current_cmd = _task_verify_cmd(current_text, task_id)
    marker_cmd = marker.get("verify_cmd")
    if current_cmd is not None and marker_cmd is not None and current_cmd != marker_cmd:
        return False, (
            f"kit-verify-hook: task {task_id}'s verify command in TASKS.md has changed since "
            f"its pass marker was recorded -- marker certifies `{marker_cmd}`, TASKS.md now "
            f"says `{current_cmd}` -- rerun precheck, verify, and record against the current "
            f"command before marking it done (PLAN D3)"
        )
    return True, ""


# ---- default runner (injectable everywhere; NEVER the real claude/copilot/codex CLI) --------

def default_runner(cmd):
    """Real-run verify runner: shell out (verify commands are repo-authored shell lines --
    same trust model as codex_execute.default_verify_runner / copilot_execute's equivalent).
    Only ever invoked on a TASK'S OWN verify command (e.g. `python3 -m unittest ...`), never a
    claude/copilot/codex dispatch."""
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


# ---- CLI ------------------------------------------------------------------------------------

def cmd_record(args):
    ok, message = run_record(args.kit_dir, args.task_id, args.verify_cmd)
    print(message)
    if not ok:
        sys.exit(1)


def cmd_precheck(args):
    run_precheck(args.kit_dir, args.task_id, args.verify_cmd, default_runner)


def cmd_hook(args):
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as e:
        # Malformed input -- fail OPEN (never block on something we can't parse); note it and
        # move on.
        print(f"kit-verify-hook: ignoring unparseable PostToolUse payload ({e})", file=sys.stderr)
        return
    allow, message = evaluate_hook_event(event)
    if not allow:
        print(message, file=sys.stderr)
        sys.exit(2)


def build_parser():
    ap = argparse.ArgumentParser(
        prog="kit_verify_hook.py",
        description=(
            "Verify-proof marker + enforcement hook for this repo's own .claude/kits/<slug> "
            "execution kits (PLAN.md D3/D10 of the graph-convergence kit)."
        ),
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p_record = sub.add_parser("record", help="write a verify-pass marker for a task")
    p_record.add_argument(
        "--kit-dir", required=True, help="kit directory, e.g. .claude/kits/<slug>"
    )
    p_record.add_argument("--task-id", required=True)
    p_record.add_argument(
        "--verify-cmd", required=True,
        help="the task's verify command text, compared against any stored precheck record",
    )
    p_record.set_defaults(func=cmd_record)

    p_precheck = sub.add_parser(
        "precheck", help="run a task's verify command against the PRE-TASK tree and record it"
    )
    p_precheck.add_argument("--kit-dir", required=True)
    p_precheck.add_argument("--task-id", required=True)
    p_precheck.add_argument("--verify-cmd", required=True)
    p_precheck.set_defaults(func=cmd_precheck)

    p_hook = sub.add_parser(
        "hook", help="PostToolUse command-hook entrypoint; reads the event JSON on stdin"
    )
    p_hook.set_defaults(func=cmd_hook)

    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
