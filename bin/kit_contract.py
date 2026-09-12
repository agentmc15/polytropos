#!/usr/bin/env python3
"""The one kit contract: how a task is parsed, selected, admitted, and recorded.

WHY THIS FILE EXISTS, MEASURED. `claude_execute.py`, `copilot_execute.py`, and
`codex_execute.py` shared 35 top-level names. Twenty-seven of them were the SAME CODE three
times -- eighteen byte-for-byte identical, nine differing only in docstrings that said things
like "ported verbatim in shape from bin/copilot_execute.py\'s T7 function". That sentence is
the whole problem stated in the source itself: the way a task got parsed in a new driver was
by copying it out of an old one.

Nothing had diverged yet. That is the reason to act rather than a reason not to: a rule
implemented in three places is a rule that will eventually be checked three different ways,
and the drift starts with the first fix applied to two of them. `TripleImplementationTests`
now fails if a driver grows its own copy back.

WHAT STAYED IN THE DRIVERS. Eight functions genuinely differ per harness, and they are exactly
the ones that should: `build_dispatch` (each CLI\'s argv), `run_task` (each host\'s loop),
`escalation_ladder` and `load_pricing` (each harness has its own pricing file and its own
model roster, and the three pricing files never merge), plus each driver\'s CLI surface. This
file holds the decisions that must be the SAME everywhere -- what a task id is, when a task may
be dispatched, what a budget refusal means, what evidence a completed task carries -- and none
of the decisions that must not be.

ONE AUTHORITY, NOT A SECOND ONE. Budget admission lives here so there is a single place that
decides whether an operation may consume; the outcome vocabulary lives here so a run record
means the same thing whoever wrote it. Adding a parallel budget check or a second event store
elsewhere would recreate the problem this file exists to end.
"""

import json
import os
import re
import secrets
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

#: The task/run contract this module implements. A consumer that reads a normalized task or
#: result checks this before trusting the field names.
CONTRACT_VERSION = "polytropos.task/1"


# ---- shared vocabulary ----------------------------------------------------------------
EM_DASH = " — "  # spaced em dash — the required task-heading separator

STATUSES = ("pending", "in-progress", "done", "blocked")

# ---- PLAN.md budget dial (T9, graph-convergence) -----------------------------------------------
#
# `budget: max-dispatches=N max-escalations=N max-consults=N` is an OPTIONAL PLAN.md line
# FAMILY -- exactly like `autonomy:` (skills/architect/SKILL.md's "Autonomy posture (optional)"
# bullet): never a task field, the TASKS.md contract (`id`/`title`/`status`/`model`/brief/
# acceptance/verify) is untouched, and PLAN.md stays execute-owned. Absent block = today's
# behavior everywhere (unbounded, no check performed) -- PLAN D6. `bin/routing_scorecard.py`
# never parses this line itself; it only recognizes the RESULT the block may cause a driver to
# write (`result=budget-stop`, a fifth, no-verdict value in the outcome grammar -- see its
# RESULTS comment). Ported identically in shape across all three drivers (PLAN D1 convergence:
# same constant names, same parse helper shape, same stop semantics, same ledger line) -- this
# driver never imports another driver or routing_scorecard, so the shape is duplicated, not
# shared, on purpose (matches the tier-resolution precedent above).
#
# Enforcement is a START-OF-INVOCATION gate against the kit's OWN recorded history, not a
# mid-flight cutoff of this invocation's own escalation ladder (that is the existing, unrelated
# `--max-escalations` CLI flag, which caps ONE invocation's ladder walk -- the PLAN.md dial
# caps the WHOLE KIT across every invocation, past and future, resumed sessions included). A
# real (non `--dry-run`) `run` reads the kit's already-recorded `outcome:` lines from NOTES.md
# BEFORE dispatching anything; if a declared cap is already met or exceeded, the task is NEVER
# dispatched, its status is left exactly as found (pending stays pending -- "remaining tasks
# untouched" per the brief), and ONE `outcome: ... result=budget-stop` line is appended instead
# -- never folded into a fluent summary, always naming which cap was hit and how many tasks are
# left untouched (`cmd_run` below). `--dry-run` is UNAFFECTED (today's behavior): it never
# dispatches or spends anything regardless, so the gate buys no additional safety there and
# checking it would only add a second code path to keep in sync.
PLAN_BUDGET_RE = re.compile(r"^\s*budget:\s*(.+)$", re.MULTILINE)

PLAN_BUDGET_KEYS = ("max-dispatches", "max-escalations", "max-consults",
                    "max-model-calls")

#: Which caps each consuming operation draws down. Explicit KINDS exist because "a dispatch"
#: was doing the work of several different things, and a cap that cannot name what it is
#: counting cannot be checked before the thing happens.
#:
#: This mapping is also the fix for a specific bug: the old check tested EVERY cap against
#: every operation, so a kit declaring `max-escalations=0` refused to run its first task at
#: all -- `used=0 >= cap=0` is true, and nothing distinguished "this is an initial attempt"
#: from "this is an escalation". An initial attempt now simply never consults that cap.
#:
#: COMPATIBILITY POLICY. `max-dispatches` keeps exactly its historical meaning: initial
#: attempts, retries, escalations and consults -- every model call on a TASK. It has never
#: counted phase review or final acceptance, and it still does not; redefining a recorded
#: metric would make old ledgers mean something new. `max-model-calls` is the new, separately
#: named cap that does include them.
OPERATION_CAPS = {
    "initial": ("max-dispatches", "max-model-calls"),
    "retry": ("max-dispatches", "max-model-calls"),
    "escalation": ("max-dispatches", "max-escalations", "max-model-calls"),
    "consult": ("max-dispatches", "max-consults", "max-model-calls"),
    "review": ("max-model-calls",),
    "acceptance": ("max-model-calls",),
}


# ---- parsing, selection, and state ------------------------------------------------------

def parse_tasks(text):
    """Parse a kit TASKS.md into a list of task dicts.

    Task blocks start at `### <id>{em dash}<title>` headings (the spaced em dash ` — ` is
    required; the id is the first whitespace-free token). A `### ` heading without the spaced
    em dash is not a task and is skipped, but it still bounds the preceding block. Each dict
    carries: id, title, status, model, depends, independent, brief, verify.
    """
    lines = text.splitlines()
    heading_idxs = [i for i, ln in enumerate(lines) if ln.startswith("### ")]
    tasks = []
    for pos, start in enumerate(heading_idxs):
        heading = lines[start][len("### "):].strip()
        if EM_DASH not in heading:
            continue
        task_id = heading.split()[0]
        title = heading.split(EM_DASH, 1)[1].strip()
        end = heading_idxs[pos + 1] if pos + 1 < len(heading_idxs) else len(lines)
        block = "\n".join(lines[start:end])
        tasks.append(_parse_block(task_id, title, block))
    return tasks

def _parse_block(task_id, title, block):
    status = None
    model = None
    depends = []
    independent = False
    # OPTIONAL. Absent -> `red-green`, which is exactly the historical rule, so every kit
    # written before this field keeps behaving as it did.
    evidence = None
    for line in block.splitlines():
        s = line.strip()
        if status is None and s.startswith("- status:"):
            status = s[len("- status:"):].strip()
        elif model is None and s.startswith("- model:"):
            value = s[len("- model:"):].strip()
            # A model pin written as `` `model-id` `` is the natural Markdown form and was
            # already tolerated by `copilot_execute`'s copy of this parser and by neither of
            # the other two -- so the same TASKS.md line meant a different model depending on
            # which driver read it. Tolerating it everywhere is the resolution; the alternative
            # would have been silently dropping a behaviour one driver's tests depend on.
            if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
                value = value[1:-1].strip()
            model = value or None
        elif s.startswith("- depends:"):
            depends = _parse_depends(s[len("- depends:"):])
        elif s.startswith("- independent:"):
            independent = s[len("- independent:"):].strip().lower() == "yes"
        elif evidence is None and s.startswith("- evidence:"):
            evidence = s[len("- evidence:"):].strip() or None
    if status not in STATUSES:
        raise ValueError(
            f"task {task_id}: '- status:' is required and must be one of "
            f"{' | '.join(STATUSES)} (got {status!r})"
        )
    return {
        "id": task_id,
        "title": title,
        "status": status,
        "model": model,
        "depends": depends,
        "independent": independent,
        "evidence": evidence,
        "brief": _extract_brief(block),
        "verify": _extract_verify(block),
    }

def _extract_brief(block):
    """Text between `**Brief.**` and the next `**Acceptance.**` (or `**Verify.**`), stripped."""
    marker = "**Brief.**"
    i = block.find(marker)
    if i == -1:
        return ""
    rest = block[i + len(marker):]
    for end_marker in ("**Acceptance.**", "**Verify.**"):
        j = rest.find(end_marker)
        if j != -1:
            return rest[:j].strip()
    return rest.strip()

def _extract_verify(block):
    """Contents of the first ```bash fence after `**Verify.**`, stripped; None if absent."""
    marker = "**Verify.**"
    i = block.find(marker)
    if i == -1:
        return None
    rest = block[i + len(marker):]
    fence = "```bash"
    j = rest.find(fence)
    if j == -1:
        return None
    after = rest[j + len(fence):]
    nl = after.find("\n")
    if nl == -1:
        return None
    close = after.find("```", nl + 1)
    if close == -1:
        return None
    return after[nl + 1:close].strip()

def _parse_depends(value):
    value = value.strip()
    if not value or value == "(none)":
        return []
    return [d.strip() for d in value.split(",") if d.strip()]

def _read_tasks_text(kit_dir):
    path = Path(kit_dir) / "TASKS.md"
    if not path.exists():
        raise FileNotFoundError(f"no TASKS.md under kit dir {kit_dir}")
    return path.read_text()

def _select_task(tasks, task_id=None):
    """`select_task`'s answer without the reason -> the task, or None.

    DELEGATES, so there is one readiness rule rather than two. It used to be a second
    implementation, and the two had already drifted: `codex_execute`'s copy refused an
    explicitly named task whose dependencies were unfinished, while `claude_execute`'s and
    `copilot_execute`'s returned it. `cmd_run` calls THIS one, so on two of the three drivers
    `--task T5` dispatched while T4 was still pending and T5's brief assumed T4's output
    existed. Automatic selection had always checked; naming a task was the way around it.

    Kept as a name because the three drivers' `cmd_run` functions call it and word their own
    operator messages; what it must not be again is a separate answer to the same question.
    """
    task, _reason = select_task(tasks, task_id=task_id, allow_rerun=True)
    return task


def select_task(tasks, task_id=None, allow_rerun=False):
    """The task to run -> `(task, reason)`, exactly one of which is None.

    ONE readiness rule for BOTH explicit and automatic selection. The defect this replaces was
    that naming a task skipped the dependency check entirely: `--task T5` ran while T4 was
    still pending, and T5's brief assumed T4's output existed. Automatic selection had always
    checked; naming a task was simply the way around it.

    `reason` is a sentence naming the rule that stopped the run. "No eligible task" covers five
    different situations -- unknown id, unknown dependency, unfinished dependency, already
    done, nothing pending -- and an operator has to know which one they are looking at.
    """
    by_id = {t["id"]: t for t in tasks}
    status_by_id = {t["id"]: t["status"] for t in tasks}

    def unmet(task):
        for dep in task["depends"]:
            if dep not in by_id:
                return f"depends on unknown task {dep!r}"
            if status_by_id.get(dep) != "done":
                return f"depends on {dep}, which is {status_by_id.get(dep)!r} rather than done"
        return None

    if task_id is not None:
        task = by_id.get(task_id)
        if task is None:
            return None, f"no task with id {task_id!r} in this kit"
        blocker = unmet(task)
        if blocker is not None:
            return None, f"task {task_id} {blocker}"
        if task["status"] == "done" and not allow_rerun:
            return None, (
                f"task {task_id} is already done -- pass --rerun to repeat it deliberately "
                f"rather than silently redoing completed work"
            )
        return task, None

    for task in tasks:
        if task["status"] == "pending" and unmet(task) is None:
            return task, None
    pending = [t["id"] for t in tasks if t["status"] == "pending"]
    if not pending:
        return None, "no pending task in this kit"
    return None, (
        f"no pending task has all dependencies done (pending: {', '.join(pending)})"
    )

def set_status(text, task_id, new_status):
    """Return `text` with exactly one change: the `- status:` line inside `task_id`'s block.

    Surgical: find the `### <id>{em dash}...` heading, then replace the FIRST `- status:` line
    that appears before the next `### ` heading. Everything else stays byte-identical. Raises
    ValueError on an unknown id or an invalid status.
    """
    if new_status not in STATUSES:
        raise ValueError(
            f"invalid status {new_status!r}; valid: {' | '.join(STATUSES)}"
        )
    lines = text.splitlines(keepends=True)
    heading_idx = None
    for i, ln in enumerate(lines):
        stripped = ln.rstrip("\n")
        if stripped.startswith("### "):
            heading = stripped[len("### "):].strip()
            if EM_DASH in heading and heading.split()[0] == task_id:
                heading_idx = i
                break
    if heading_idx is None:
        raise ValueError(f"unknown task id {task_id!r}")

    end = len(lines)
    for i in range(heading_idx + 1, len(lines)):
        if lines[i].rstrip("\n").startswith("### "):
            end = i
            break

    for i in range(heading_idx, end):
        raw = lines[i]
        if raw.strip().startswith("- status:"):
            leading = raw[: len(raw) - len(raw.lstrip())]
            newline = "\n" if raw.endswith("\n") else ""
            lines[i] = f"{leading}- status: {new_status}{newline}"
            return "".join(lines)
    raise ValueError(f"no '- status:' line in task {task_id!r}")

def dispatch_status(value):
    """Normalise what a dispatch runner returned -> `(rc, output)`.

    `(rc, output)` is the production contract (`default_runner` always returns one) and `rc` is
    then AUTHORITATIVE: a non-zero exit is a failed dispatch, whatever a later check says.

    `None` means the runner declined to report -- the shape injected fixtures use. That is
    recorded as UNKNOWN (`rc is None`), never as success. Unknown does not by itself block
    completion, because a fixture that reports nothing is not evidence of failure; a reported
    non-zero exit is.
    """
    if value is None:
        return None, ""
    rc, output = value
    return rc, output or ""

def generate_run_id(now=None):
    """One content-free `run=` id per driver invocation: `<UTC-date>-<4 hex>` (PLAN D8).

    `secrets.token_hex(2)` supplies the four hex characters from 2 cryptographically random
    bytes -- never a hostname, username, pid, or path fragment (NOTES.md is committed in
    consumer repos, so nothing content-bearing may enter it). `now` is injectable so tests
    can pin the date segment without touching wall-clock time; the hex segment is always
    freshly random.
    """
    now = now or datetime.now(timezone.utc)
    return f"{now.strftime('%Y-%m-%d')}-{secrets.token_hex(2)}"

class BudgetAdmission:
    """Pre-dispatch admission: every consuming operation asks BEFORE it happens.

    The gate used to run once, at invocation entry, and `run_task` then dispatched the initial
    attempt plus every escalation rung without asking again -- so a kit declaring
    `max-dispatches=1` performed one dispatch AND the whole ladder. Grants are counted here as
    they are issued, on top of the usage already recorded in the kit's ledger, so the ladder is
    bounded by the same numbers the entry check reads.

    Reservations are counted at GRANT time, not at completion: an attempt that crashes has
    still consumed its allowance, because the money is spent when the call is made. A failed
    consult therefore consumes consult allowance, which is the point -- an operation that can
    fail for free is an operation nobody is counting.
    """

    def __init__(self, plan_budget, used=None):
        self.budget = dict(plan_budget or {})
        self.used = {k: int(v) for k, v in (used or {}).items()}
        self.granted = []

    def check(self, kind):
        """`(ok, reason)` without consuming anything."""
        key = blocking_cap(self.budget, self.used, kind)
        if key is None:
            return True, None
        return False, (
            f"PLAN.md budget {key}={self.budget[key]} already reached "
            f"(used={self.used.get(key, 0)}) -- refusing the {kind} operation before it spends"
        )

    def admit(self, kind):
        """`(ok, reason)`; on success the grant is counted against every cap it draws down."""
        ok, reason = self.check(kind)
        if not ok:
            return False, reason
        for key in OPERATION_CAPS.get(kind, ()):
            self.used[key] = self.used.get(key, 0) + 1
        self.granted.append(kind)
        return True, None

def blocking_cap(plan_budget, used, kind):
    """The first cap that would refuse an operation of `kind`, or None.

    A cap is "reached" at `used[key] >= cap` -- the recorded usage already consumed the last
    unit the budget allowed, so the operation in front of this call must not add one more.
    Checked in `OPERATION_CAPS[kind]` order, so `max-dispatches` wins ties -- arbitrary but
    stable and reproducible.
    """
    if not plan_budget:
        return None
    for key in OPERATION_CAPS.get(kind, ()):
        cap = plan_budget.get(key)
        if cap is None:
            continue
        if used.get(key, 0) >= cap:
            return key
    return None

def plan_budget_exhausted(plan_budget, used, is_consult):
    """Back-compat entry check -> the first cap blocking this invocation's FIRST operation.

    Kept for callers that ask the question the old way. It now asks about a specific operation
    kind rather than testing every cap blindly, which is why `max-escalations=0` no longer
    blocks an initial attempt.
    """
    return blocking_cap(plan_budget, used, "consult" if is_consult else "initial")

def parse_plan_budget(text):
    """Read the kit's optional PLAN.md `budget:` line -> dict or `None`.

    `text` is PLAN.md's content (or `None`/empty when there is no PLAN.md -- `None` right
    back, no error). Any subset of `PLAN_BUDGET_KEYS`, in any order, each a base-10
    non-negative integer: `budget: max-dispatches=5 max-consults=1`. No `budget:` line, no
    recognized key on that line, or no PLAN.md at all -> `None` (today's behavior: unbounded,
    no check performed). Unrecognized tokens on the line are silently ignored (forward-
    compatible, matching the outcome-ledger's own unknown-`key=value` tolerance).
    """
    if not text:
        return None
    m = PLAN_BUDGET_RE.search(text)
    if not m:
        return None
    keys = "|".join(re.escape(k) for k in PLAN_BUDGET_KEYS)
    budget = dict(re.findall(rf"({keys})=(\d+)", m.group(1)))
    return {k: int(v) for k, v in budget.items()} or None

def count_plan_budget_usage(notes_text):
    """Count dispatches/escalations/consults already recorded in a kit's NOTES.md ledger.

    A minimal re-implementation of `routing_scorecard`'s own `outcome:` grammar (this driver
    imports no pricing/scorecard module -- the same tier-resolution precedent above), read-only
    over `notes_text`. Per `outcome:` line: `attempts=` (default 1 when absent or non-integer,
    mirroring `routing_scorecard.parse_outcomes`) counts toward `max-dispatches`; `attempts - 1`
    counts toward `max-escalations` (an in-ladder escalation IS an extra dispatch); a line
    carrying `parent=` counts ONE `max-consults` (a run dispatched with `--parent` is a consult
    by definition, whether it passed, was blocked, or was itself a budget-stop). Returns a dict
    with all three `PLAN_BUDGET_KEYS`, always present (0 when nothing is recorded yet).
    """
    used = {k: 0 for k in PLAN_BUDGET_KEYS}
    for line in notes_text.splitlines():
        s = line.strip()
        if s.startswith("- "):
            s = s[2:]
        if not s.startswith("outcome:"):
            continue
        m = re.search(r"\battempts=(\d+)\b", s)
        try:
            attempts = int(m.group(1)) if m else 1
        except ValueError:
            attempts = 1
        used["max-dispatches"] += attempts
        # Every task dispatch is also a model call. `max-model-calls` additionally covers
        # review and acceptance, which `max-dispatches` has never counted and still does not.
        used["max-model-calls"] += attempts
        used["max-escalations"] += max(attempts - 1, 0)
        if re.search(r"(?:^|\s)parent=\S+", s):
            used["max-consults"] += 1
    return used

def append_plan_budget_stop_note(notes_path, task, run_id, exhausted_key, cap, used,
                                 remaining, role=None, agent=None):
    """Append ONE budget-stop block to the kit's NOTES.md -- the T9 "never hide the stop
    behind a fluent summary" contract. No dispatch happened: `attempts=0`, no escalations, no
    model was actually used (the task's OWN pin, or `unpinned`, labels the line). The block
    states plainly which PLAN.md budget cap was hit, the used/cap counts, and how many pending
    tasks (including this one -- none of them were touched) remain, as its own bullet lines --
    never folded into prose. Structurally the same append-only block shape as `append_note`
    (created if missing, one blank-line-separated block appended), and the SAME
    `build_outcome_line` -- carries `run=` (always, since `cmd_run` always generates one) and
    never `parent=` (a budget-stopped run is not counted as lineage; see `PARENT_RESULTS`,
    which `budget-stop` is deliberately not a member of).
    """
    # TWO NAMES FOR ONE FIELD, kept apart on purpose. `claude_execute` and `codex_execute`
    # write `- role:`; `copilot_execute` writes `- agent:`. Both forms are already in NOTES.md
    # ledgers committed in consumer repos, and `bin/routing_scorecard.py` parses `agent:` lines
    # specifically (`AGENT_RE`), so unifying the key here would silently reinterpret history
    # that has already been written. The caller states which name its ledger uses; this writes
    # exactly that one and refuses to guess.
    if (role is None) == (agent is None):
        raise ValueError(
            "append_plan_budget_stop_note: pass exactly one of role= or agent= — the two "
            "name the same field in different drivers' ledgers and only the caller knows which"
        )
    _actor_label, _actor_value = ("role", role) if role is not None else ("agent", agent)
    notes_path = Path(notes_path)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    task_id = task["id"]
    model_label = task.get("model") or "unpinned"
    block_lines = [
        f"## {ts}{EM_DASH}{task_id}",
        f"- {_actor_label}: {_actor_value}",
        f"- budget-stop: {exhausted_key}={cap} reached (used={used})",
        f"- remaining tasks untouched: {remaining}",
        "- " + build_outcome_line(task_id, model_label, 0, "budget-stop", run_id=run_id),
    ]
    block = "\n".join(block_lines) + "\n"

    existing = notes_path.read_text() if notes_path.exists() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    separator = "\n" if existing.strip() else ""
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    notes_path.write_text(existing + separator + block)

def _evidence(verify_cmd, rc, output):
    return (
        "\n\n--- ESCALATION EVIDENCE (verify failed) ---\n"
        f"verify: {verify_cmd}\n"
        f"exit: {rc}\n"
        f"{(output or '')[-2000:]}"
    )

def outcome_result(status, escalations, parent):
    """Classify a finished `run_task` result into the T1 `result=` vocabulary.

    `blocked` when the task never passed. Otherwise `escalated-pass` when the ladder needed a
    rung beyond the task's own pinned tier (`escalations` non-empty) OR this run was itself a
    consult for a different task (`parent` given -- module docstring, "Escalation lineage").
    Otherwise plain `pass`.
    """
    if status != "done":
        return "blocked"
    if escalations or parent:
        return "escalated-pass"
    return "pass"

def recorded_outcome_result(notes_text, task_id):
    """The LAST `result=` already recorded for `task_id` in `notes_text`, or `None`.

    Read-only over the kit's NOTES.md, same minimal `outcome:` grammar as
    `count_plan_budget_usage` above (optional `- ` bullet, id as the first token, `key=value`
    pairs). Later lines win, mirroring `routing_scorecard.parse_outcomes`'s last-wins rule.

    Its ONE caller is the budget gate below: a `budget-stop` is not a verdict, so writing one
    for a task that ALREADY carries a real verdict would append a ledger line that supersedes
    (or, once the reader's precedence rule drops it, contradicts) recorded evidence. Rejected
    at the WRITER, before anything is written -- the same precedent as the self-`--parent`
    guard in `cmd_run`, and the same reasoning as the Phase 1 review's F2 invariant: nothing
    may write a line the reader has to ignore.
    """
    found = None
    for line in notes_text.splitlines():
        s = line.strip()
        if s.startswith("- "):
            s = s[2:]
        if not s.startswith("outcome:"):
            continue
        parts = s[len("outcome:"):].split()
        if not parts or parts[0] != task_id:
            continue
        m = re.search(r"(?:^|\s)result=(\S+)", s)
        if m:
            found = m.group(1)
    return found

def build_outcome_line(task_id, model, attempts, result, review="none", run_id=None,
                        parent=None):
    """One `outcome:` ledger line (T1 grammar). `model` must be a non-whitespace token --
    callers pass `"unpinned"` (never a phrase with a space) for a task with no model pin, so
    the line still parses under `routing_scorecard.PAIR_RE` (`\\w+=\\S+`)."""
    line = (
        f"outcome: {task_id} model={model} attempts={attempts} "
        f"result={result} review={review}"
    )
    if run_id:
        line += f" run={run_id}"
    if parent:
        line += f" parent={parent}"
    return line

def _ep():
    """Lazy-load bin/exec_policy.py -- the OS execution boundary (step 05)."""
    import importlib.util
    path = Path(__file__).resolve().parent / "exec_policy.py"
    spec = importlib.util.spec_from_file_location("exec_policy", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def _pr():
    """Lazy-load bin/proc_runner.py -- the repo's ONE process-lifecycle helper (step 12)."""
    import importlib.util
    path = Path(__file__).resolve().parent / "proc_runner.py"
    spec = importlib.util.spec_from_file_location("proc_runner", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def default_verify_runner(cmd, workspace=None, mode="enforced"):
    """Verify runner for real runs -- the repo-authored shell line, INSIDE the boundary.

    Still a shell (`sh -c`): verify commands are shell lines by contract, and that contract is
    not what was broken. What changed is which process interprets them. This used to be
    `subprocess.run(cmd, shell=True)` in the parent, so the code a worker had just written was
    executed with the parent's filesystem access, credentials, and network -- broader than the
    worker that produced it. It now runs confined to `workspace`, with credential stores
    unreadable and network denied, and refuses outright when no backend can enforce that.
    """
    ep = _ep()
    runner = ep.verify_runner(workspace or Path.cwd(), mode=mode)
    return runner(cmd)


# ---- the normalized view -------------------------------------------------------------------

#: Fields every adapter sees for a task, whatever dialect it was written in. Named here so a
#: consumer can check the set rather than discovering it by KeyError.
TASK_FIELDS = (
    "contract", "id", "title", "status", "model", "role", "effort",
    "depends", "independent", "brief", "acceptance", "verify", "evidence",
)


def to_contract(task, role=None, effort=None, workspace=None, artifacts=None):
    """One parsed task as the versioned contract -> a plain dict.

    IDENTITY IS THE TASK\'S OWN ID, UNCHANGED. Kits are committed files with ledgers that
    reference their task ids; deriving a new identity here would break every historical record
    that names one. `contract` carries the version so a reader knows which field names apply.

    `role`, `effort`, `workspace` and `artifacts` are the REQUEST -- what the caller is asking
    for -- not a claim about what a harness will honour. What a host actually enforces is the
    adapter\'s business and is reported by its capability record, never assumed here.
    """
    return {
        "contract": CONTRACT_VERSION,
        "id": task.get("id", ""),
        "title": task.get("title", ""),
        "status": task.get("status", ""),
        "model": task.get("model") or None,
        "role": role,
        "effort": effort,
        "depends": list(task.get("depends") or ()),
        "independent": bool(task.get("independent")),
        "brief": task.get("brief", ""),
        "acceptance": task.get("acceptance", ""),
        "verify": task.get("verify", ""),
        "evidence": task.get("evidence") or None,
        "workspace": str(workspace) if workspace is not None else None,
        "artifacts": list(artifacts or ()),
    }


# ---- shared driver behaviour ----------------------------------------------------------------
#
# These are not "the contract" in the narrow sense, but they were the SAME code in more than one
# driver, which is the condition that produced every divergence this module exists to end.


def cmd_status(args):
    tasks = parse_tasks(_read_tasks_text(args.kit))
    if args.json:
        print(json.dumps(tasks, indent=2))
        return

    id_w = max((len(t["id"]) for t in tasks), default=0)
    status_w = max((len(t["status"]) for t in tasks), default=0)
    model_w = max((len(t["model"] or "-") for t in tasks), default=0)
    for t in tasks:
        print(
            f"{t['id']:<{id_w}}  {t['status']:<{status_w}}  "
            f"{(t['model'] or '-'):<{model_w}}  {t['title']}"
        )
    counts = {s: sum(1 for t in tasks if t["status"] == s) for s in STATUSES}
    print(
        f"{counts['pending']} pending / {counts['in-progress']} in-progress / "
        f"{counts['done']} done / {counts['blocked']} blocked"
    )


def _budget_stop(task, model_used, escalations, kind, reason):
    """The record for an operation REFUSED before it spent anything.

    Distinct from a dispatch failure and from a verification failure: nothing ran, so there is
    no exit code and no verdict to report. `status` stays blocked because the task is not done
    and nobody should read it as done.
    """
    return {
        "id": task["id"],
        "status": "blocked",
        "model_used": model_used,
        "escalations": escalations,
        "verify_rc": None,
        "dispatch_rc": None,
        "failure": "budget",
        "budget_stop": {"operation": kind, "reason": reason},
    }


def build_id_preamble(kit=None, run_id=None, task_id=None):
    """One bracketed lineage line, e.g. `[kit=fixturekit run=2026-07-26-9f3a task=T1]`, or
    `""` when none of the three ids are given (PLAN D6 — purely additive). Only the ids
    actually supplied appear; the bracket is omitted entirely rather than printed empty."""
    pairs = []
    if kit:
        pairs.append(f"kit={kit}")
    if run_id:
        pairs.append(f"run={run_id}")
    if task_id:
        pairs.append(f"task={task_id}")
    if not pairs:
        return ""
    return "[" + " ".join(pairs) + "]"


def provider_runner(provider, label=None):
    """Build a driver's `default_runner` for one provider -> `runner(argv, cwd, timeout)`.

    The three drivers' runners were 97% identical: the same bounded dispatch differing only in
    which provider's environment it carries and what it calls itself in a diagnostic. Both are
    parameters, so this is one implementation with two arguments rather than three
    implementations with one difference.

    !!! A runner returned here spends the user's real tokens or credits when handed a real
    harness argv. Every test injects its own; `--dry-run` / `--demo` spawn nothing. !!!

    Bounded via `bin/proc_runner.py`: a wall clock, an output ceiling, a validated working
    directory, and its own process group -- so a dispatch that stalls or floods cannot hang the
    driver, and nothing it spawned outlives it. Failures that are not the model's verdict (a
    missing CLI, a timeout) come back as `proc_runner.INFRASTRUCTURE_RC` with the reason
    appended to the output, rather than as an exception that would strand the task in-progress.

    The environment is reduced to this provider's own variables plus the base set, so the
    machine's unrelated credentials are not handed to a coding agent. `POLYTROPOS_DISPATCH_ENV`
    (comma-separated NAMES) widens it on a host that needs a variable the list has not learned.
    """
    name = label or f"{provider} dispatch"

    def default_runner(argv, cwd=None, timeout=None):
        pr = _pr()
        result = pr.run(
            argv,
            cwd=cwd if cwd is not None else Path.cwd(),
            env=pr.dispatch_env(provider),
            timeout=timeout,
            name=name,
        )
        output = result["output"]
        if not result["terminal"] and result["detail"]:
            output = f"{output}\n{result['detail']}" if output else result["detail"]
        return result["rc"], output

    return default_runner


def run_cli(build_parser, argv=None):
    """Parse and dispatch a driver's CLI -> its exit behaviour.

    The three `main` functions were byte-identical. `build_parser` is the only difference and it
    is passed in.
    """
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (ValueError, FileNotFoundError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)


# ---- the attempt lifecycle (step 16) --------------------------------------------------------
#
# WHAT A RUN LEFT BEHIND, BEFORE. `TASKS.md` said `in-progress`; `NOTES.md` said nothing until
# the task finished; the kit's budget was recomputed from `NOTES.md`, so a ladder interrupted
# after three paid escalations resumed with a budget that had never heard of them; and the
# driver wrote its final status from a copy of `TASKS.md` read before a model spent minutes
# editing the tree. Every piece of that is a snapshot standing in for a record.
#
# The record is `bin/attempt_ledger.py`. What lives HERE is the part that must mean the same
# thing whichever driver is running: when a task is claimed, what counts as an attempt, how
# usage from the ledger and from `NOTES.md` add up, and how a status is projected back into
# `TASKS.md` from a fresh read. A driver contributes its argv and its loop, as before.


_ATTEMPT_LEDGER = None


def _al():
    """Lazy-load bin/attempt_ledger.py -- the one record of attempts (step 16).

    Loaded ONCE and cached, unlike the other lazy loaders here, because this module's
    exception classes are compared by identity: a ledger opened by one load raising
    `ClaimHeld` past an `except` that names another load's `ClaimHeld` is an uncaught
    exception, not a refusal. That is exactly what happened before the cache.
    """
    global _ATTEMPT_LEDGER
    if _ATTEMPT_LEDGER is None:
        import importlib.util
        path = Path(__file__).resolve().parent / "attempt_ledger.py"
        spec = importlib.util.spec_from_file_location("attempt_ledger", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _ATTEMPT_LEDGER = mod
    return _ATTEMPT_LEDGER


def open_ledger(kit_dir, store=None, env=None):
    """The kit's attempt ledger.

    `store` is a driver's `--attempt-store` and overrides everything, which is how every test
    points at a temp dir. Otherwise the ledger lives in the per-user data root, namespaced to
    the checkout that holds the kit (`attempt_ledger.kit_repo_root`), never inside the tree a
    worker edits. The namespace within the store is the kit's directory name.
    """
    al = _al()
    kit_dir = Path(kit_dir)
    root = Path(store) if store else al.default_store(al.kit_repo_root(kit_dir), env=env)
    return al.AttemptLedger(root, kit_dir.name)


def combined_usage(notes_text, ledger):
    """`NOTES.md` usage plus the ledger's not-yet-projected attempts -> one `used` dict.

    `NOTES.md` counts finished tasks; the ledger counts what nothing has written an outcome
    line for -- an interrupted ladder, a run that died after dispatch. Neither double-counts
    the other: once a task's outcome line exists, the ledger stops counting its attempts.
    """
    used = count_plan_budget_usage(notes_text)
    for key, n in ledger.usage().items():
        used[key] = used.get(key, 0) + n
    return used


def append_block(notes_path, block):
    """Append one Markdown block to a kit's NOTES.md, separated from what is there.

    Appends with the file opened for append, so a concurrent writer's block is not lost the
    way a read-then-`write_text` loses it. The only read is one byte, to decide whether a
    newline is owed before the separator.
    """
    notes_path = Path(notes_path)
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    prefix = ""
    try:
        with open(notes_path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            if fh.tell():
                fh.seek(-1, os.SEEK_END)
                prefix = ("" if fh.read(1) == b"\n" else "\n") + "\n"
    except FileNotFoundError:
        pass
    with open(notes_path, "a", encoding="utf-8") as fh:
        fh.write(prefix + block)


def project_status(tasks_path, task_id, new_status, expected=None):
    """Write `task_id`'s status from a FRESH read of TASKS.md -> `(text, previous_status)`.

    The driver's in-memory copy of TASKS.md was read before a model spent minutes with write
    access to the tree. Writing that copy back would erase whatever changed in between, which
    is the stale-snapshot defect. So the file is re-read, exactly one line is changed, and
    the whole file is replaced in one `os.replace` so a crash mid-write cannot leave half a
    TASKS.md.

    `previous_status` is what the file said just before the write. When it differs from
    `expected` -- a worker flipped its own task to `done`, say -- the DRIVER's verdict still
    wins, because the driver holds the claim and ran the check; the caller reports the
    discrepancy rather than silently accepting either side.
    """
    tasks_path = Path(tasks_path)
    text = tasks_path.read_text()
    previous = next((t["status"] for t in parse_tasks(text) if t["id"] == task_id), None)
    text = set_status(text, task_id, new_status)
    tmp = tasks_path.with_name(f"{tasks_path.name}.{os.getpid()}.tmp")
    tmp.write_text(text)
    os.replace(tmp, tasks_path)
    return text, previous


class TaskRun:
    """One task's lifecycle in the ledger: claim, reconcile, record, project, release.

    Every consuming call a driver makes is bracketed by `attempt_started` (before) and
    `attempt_finished` (after), so the ledger always knows a call was made even when nothing
    came back. `verify_finished` records the check's verdict against the attempt it judged.
    """

    def __init__(self, ledger, run_id, task, workspace=None, actor="driver", role=None,
                 parent=None):
        self.ledger = ledger
        self.run = run_id
        self.task = task
        self.task_id = task["id"]
        self.workspace = Path(workspace) if workspace is not None else Path.cwd()
        self.actor = actor
        # Step 17: the role this run dispatches as, and the task it was spawned to rescue.
        # Recorded on every attempt, whatever the result -- a FAILED consult keeps its parent
        # here even though the NOTES.md grammar only carries `parent=` on a success.
        self.role = role
        self.parent = parent
        self._al = _al()

    def begin(self, break_claim=False):
        """Claim the task and close whatever a dead run left open -> what was found."""
        if break_claim:
            self.ledger.break_claim(self.task_id, reason=f"--break-claim by run {self.run}")
        info = self.ledger.claim(self.task_id, self.run)
        self.ledger.append("run.started", run=self.run, task=self.task_id, actor=self.actor,
                           pid=os.getpid())
        closed = self.ledger.reconcile_open(
            self.run, self.task_id,
            note="closed by a later run: the process that started this attempt recorded no "
                 "result, so whether it ran, what it changed, and whether it was billed are "
                 "all unknown",
        )
        return {
            "stale_from": info.get("stale_from"),
            "closed_unknown": closed,
            "unprojected": self.ledger.unprojected(self.task_id),
        }

    def fingerprint(self):
        return self._al.workspace_fingerprint(self.workspace)

    def precheck(self, tautological, rc=None):
        """Record the pre-task verify verdict, so a resume can tell a real pass from a
        command that passed before any work was done."""
        self.ledger.append("verify.precheck", run=self.run, task=self.task_id,
                           tautological=bool(tautological), rc=rc)

    def recorded_precheck(self):
        found = None
        for ev in self.ledger.events():
            if ev.get("kind") == "verify.precheck" and ev.get("task") == self.task_id:
                found = ev
        return found

    def attempt_started(self, op, model, prompt=None, verify_cmd=None, effort=None):
        return self.ledger.record_started(
            self.run, self.task_id, op, model, prompt=prompt, verify_cmd=verify_cmd,
            artifact=self.fingerprint(), role=self.role, parent=self.parent,
            requested_model=self.task.get("model"), effort=effort, actor=self.actor,
        )

    def attempt_finished(self, attempt, rc, output, proc_outcome=None, duration_s=None,
                         observed_model=None):
        """Record the process result -> its failure class (None when it did not fail).

        `rc is None` is the injected-fixture shape, a runner that declined to report; that is
        unknown, not failure, and is not classified as one. `observed_model` is what the host
        attested it actually ran (Codex correlates a rollout); None means nobody observed it,
        which is recorded as exactly that.
        """
        if rc is None and proc_outcome is None:
            cls = None
            outcome = "unreported"
        else:
            cls = self._al.classify_dispatch(rc, output, proc_outcome=proc_outcome)
            outcome = proc_outcome or ("ok" if rc == 0 else "failed")
        self.ledger.record_finished(self.run, self.task_id, attempt, outcome, rc, output,
                                    cls=cls, duration_s=duration_s,
                                    observed_model=observed_model)
        return cls

    def verify_finished(self, attempt, rc, output):
        return self.ledger.record_verify(self.run, self.task_id, attempt, rc, output,
                                         artifact=self.fingerprint())

    def history(self):
        return self.ledger.task_history(self.task_id)

    def retry_context(self, verify_cmd=None, include_tail=True):
        return self._al.retry_context(self.history(), verify_cmd=verify_cmd,
                                      include_tail=include_tail)

    def project(self, status, result=None, outcome_line=False, note=""):
        self.ledger.record_projected(self.run, self.task_id, status, result=result,
                                     outcome_line=outcome_line, note=note)

    def end(self, status="finished", reason=""):
        """Record the run's end and release the claim. Idempotent: a driver calls it on
        every exit path, and only the first call writes anything."""
        if getattr(self, "_ended", False):
            return
        self._ended = True
        self.ledger.append("run.finished", run=self.run, task=self.task_id, status=status,
                           reason=reason)
        self.ledger.release(self.task_id, self.run)


def start_task_lifecycle(kit_dir, task, run_id, actor, store=None, break_claim=False,
                         workspace=None, role=None, parent=None):
    """Open the ledger, claim the task, close what a dead run left -> `(lifecycle, info)`.

    Exits 2 on a claim another live run holds, naming it: two drivers on one task is the one
    situation where refusing is always right. A stale claim (its process gone) is taken over
    and said so on stderr.
    """
    ledger = open_ledger(kit_dir, store=store)
    lifecycle = TaskRun(ledger, run_id, task, workspace=workspace, actor=actor, role=role,
                        parent=parent)
    try:
        info = lifecycle.begin(break_claim=break_claim)
    except _al().ClaimHeld as exc:
        print(f"claim: {exc}", file=sys.stderr)
        sys.exit(2)
    stale = info.get("stale_from")
    if stale:
        print(
            f"claim: took over a stale claim on task {task['id']} left by run "
            f"{stale.get('run')} (pid {stale.get('pid')} is gone)",
            file=sys.stderr,
        )
    closed = info.get("closed_unknown") or []
    if closed:
        print(
            f"resume: {len(closed)} attempt(s) of task {task['id']} had no recorded result and "
            f"were closed as unknown -- the tree may carry their changes and the provider may "
            f"have billed them; the check runs before anything else is decided",
            file=sys.stderr,
        )
    return lifecycle, info


def record_role_dispatch(kit_dir, run_id, role, phase, model, rc, output, actor,
                         store=None, observed_model=None, result=None, proc_outcome=None):
    """Record a phase review or acceptance dispatch in the attempt ledger -> attempt id.

    Reviews are not tasks: nothing is claimed and nothing is projected. What was missing (step
    17) is that on Claude and Copilot a review left NOTHING behind but stdout, so a role
    dispatch never appeared in any history at all. It is recorded against the task id
    `phase-<n>` with op `review` (or `acceptance` for the orchestrator's verdict), the same
    shape as every other attempt, so the cross-harness history can join it with Codex's typed
    role-use record for the same run.
    """
    ledger = open_ledger(kit_dir, store=store)
    task_id = f"phase-{phase}"
    op = "acceptance" if role == "orchestrator" else "review"
    attempt = ledger.record_started(run_id, task_id, op, model, role=role, actor=actor,
                                    phase=str(phase))
    al = _al()
    if rc is None and proc_outcome is None:
        cls, outcome = None, "unreported"
    else:
        cls = al.classify_dispatch(rc, output, proc_outcome=proc_outcome)
        outcome = proc_outcome or ("ok" if rc == 0 else "failed")
    ledger.record_finished(run_id, task_id, attempt, outcome, rc, output, cls=cls,
                           observed_model=observed_model, result=result)
    return attempt


def reconcile_task(lifecycle, info, verify_runner, verify_cmd):
    """Do prior, unprojected attempts already settle this task? -> a decision dict.

    `{"mode": "fresh"}` when nothing is pending. Otherwise the check is run NOW, because the
    tree is the only host evidence there is: `{"mode": "resolved", "result": ...}` when it
    passes and the recorded precheck says a pass means something (a red-green task whose
    command already passed before any work is `blocked` with `required-evidence`, exactly as
    the first run would have concluded); `{"mode": "retry", "context": ...}` when it fails,
    carrying the bounded account of what was tried for the next prompt.

    Nothing is re-dispatched here. A resume never replays an attempt; it either recognises
    finished work or asks for one more attempt that knows what came before.
    """
    pending = info.get("unprojected") or []
    if not pending:
        return {"mode": "fresh"}
    rc, output = verify_runner(verify_cmd)
    lifecycle.verify_finished(pending[-1]["attempt"], rc, output)
    if rc != 0:
        return {"mode": "retry", "context": lifecycle.retry_context(verify_cmd),
                "verify_rc": rc}
    pre = lifecycle.recorded_precheck()
    tautological = bool(pre and pre.get("tautological"))
    escalations = [ev.get("model") for ev in pending if ev.get("op") == "escalation"]
    result = {
        "id": lifecycle.task_id,
        "status": "blocked" if tautological else "done",
        "model_used": pending[-1].get("model"),
        "escalations": escalations,
        "verify_rc": 0,
        "dispatch_rc": None,
        "failure": "required-evidence" if tautological else None,
        "reconciled": len(pending),
    }
    return {"mode": "resolved", "result": result, "tautological": tautological}


def finish_task_projection(lifecycle, tasks_path, task, result):
    """Write the final status from a fresh read and count attempts from the ledger -> text.

    `result["ledger_attempts"]` becomes every attempt since the task's last outcome line,
    across runs, so a resumed ladder's outcome line says how many calls the task really cost.
    (Its own key: the Codex driver's `result["attempts"]` is a list of per-attempt records.)
    """
    result["ledger_attempts"] = max(1, len(lifecycle.ledger.unprojected(task["id"])))
    text, previous = project_status(tasks_path, task["id"], result["status"],
                                    expected="in-progress")
    if previous != "in-progress":
        print(
            f"projection: TASKS.md said task {task['id']} was {previous!r} rather than "
            f"in-progress when this run finished; the driver's verdict "
            f"({result['status']}) was written over it, and this line is the record of that",
            file=sys.stderr,
        )
    return text
