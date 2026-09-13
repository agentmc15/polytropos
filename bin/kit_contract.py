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

# ---- the execution DAG (step 18) ----------------------------------------------------------------
#
# A `depends:` list is a graph, and until this section existed nothing looked at the graph --
# only at one task's own edges, at the moment that task was picked. Measured against the tree
# before this section was written:
#
#   - a duplicate id gave THREE answers: explicit `--task T2` took the last block (dict
#     last-wins), automatic selection took the first (list order), and `set_status` wrote the
#     first -- so a driver could dispatch one block's brief and mark the other block done;
#   - a cycle between T1 and T2 refused each with "depends on T2, which is 'pending'", a true
#     sentence that can never become false, and let an unrelated T3 dispatch;
#   - a self-dependency reported "no pending task has all dependencies done", the message for
#     a kit that is waiting, not for one that is wrong;
#   - a typo in one task's `depends:` let every other task run and left that task unreachable
#     without a word.
#
# Those are one defect: the graph was never validated, so an invalid one behaved like a valid
# one with odd luck. Now the graph is checked FIRST, as a whole, and an invalid graph selects
# nothing -- zero dispatches, zero writes -- with every finding named and the edit that clears
# it beside it. That is deliberately stricter than skipping the broken tasks: a kit with a
# cycle in it is an architect defect, and dispatching around it would mutate state on a plan
# nobody has confirmed is the plan.
#
# NOT parallel dispatch. `ready_frontier` returns every task that COULD run; sequential
# selection takes the first, and the set is what step 24's scheduler will take. Nothing here
# runs two tasks.

GRAPH_STATES = ("invalid", "complete", "ready", "interrupted", "waiting")

FINDING_KINDS = ("duplicate-id", "self-dependency", "unknown-dependency", "cycle")

#: The task state machine: from each status, the statuses a driver may write over it. A task
#: is dispatched (-> in-progress) before it is judged (-> done | blocked); nothing skips the
#: dispatch, and nothing un-judges a task except a deliberate rerun or retry, which dispatches
#: it again. `in-progress -> in-progress` is a resume: the claim decides whether the run that
#: left it there is alive. `set_status` stays the surgical text writer; `project_status` is
#: where the edge is checked, before any temporary file exists.
TRANSITIONS = {
    "pending": ("in-progress",),
    "in-progress": ("in-progress", "done", "blocked"),
    "done": ("in-progress",),
    "blocked": ("in-progress",),
}

#: How a selected task's status reads as an operation. Automatic selection only ever takes a
#: `pending` task; the other three are deliberate, explicit gestures.
SELECTION_MODES = {"pending": "fresh", "blocked": "retry", "in-progress": "resume",
                   "done": "rerun"}

#: What a task's block says beyond its status: the fields a worker's mid-run edit to TASKS.md
#: may not change silently. The driver dispatched the snapshot's brief and ran the snapshot's
#: verify command; when the file says something else at projection time, the difference is
#: reported and recorded. The status itself is `project_status`'s business.
PLAN_FIELDS = ("title", "model", "depends", "independent", "evidence", "brief", "verify")


class GraphInvalid(ValueError):
    """The task graph has structural findings; `.findings` carries them."""

    def __init__(self, findings):
        self.findings = list(findings)
        super().__init__(render_findings(self.findings))


class InvalidTransition(ValueError):
    """A status write the task state machine has no edge for."""


def _finding(kind, task, detail, fix):
    return {"kind": kind, "task": task, "detail": detail, "fix": fix}


def validate_graph(tasks):
    """Every structural defect in the task graph -> a list of findings, empty when valid.

    Pure: reads the task dicts and nothing else. Each finding is `{kind, task, detail, fix}`
    with `kind` from `FINDING_KINDS`, `detail` the sentence, and `fix` the edit that clears
    it. Every finding is reported, not just the first, so a kit is fixed in one pass.
    """
    findings = []
    ids = [t["id"] for t in tasks]
    positions = {}
    for pos, task_id in enumerate(ids, start=1):
        positions.setdefault(task_id, []).append(pos)
    for task_id, where in positions.items():
        if len(where) > 1:
            findings.append(_finding(
                "duplicate-id", task_id,
                f"task id {task_id!r} heads {len(where)} blocks "
                f"(blocks #{', #'.join(str(p) for p in where)} in file order)",
                "give every `### <id> — <title>` heading its own id; the drivers select, write "
                "status, and record outcomes by id and cannot tell the blocks apart",
            ))
    known = set(ids)
    for t in tasks:
        for dep in t["depends"]:
            if dep == t["id"]:
                findings.append(_finding(
                    "self-dependency", t["id"],
                    f"task {t['id']} depends on itself",
                    "remove the task's own id from its `- depends:` line",
                ))
            elif dep not in known:
                findings.append(_finding(
                    "unknown-dependency", t["id"],
                    f"task {t['id']} depends on unknown task {dep!r}",
                    "name only ids that head a task block in this kit, comma-separated, or "
                    "write `(none)`; prose belongs in the brief, not in `- depends:`",
                ))
    edges = {}
    for t in tasks:
        edges.setdefault(t["id"], []).extend(
            d for d in t["depends"] if d in known and d != t["id"]
        )
    for cycle in _cycles(list(positions), edges):
        findings.append(_finding(
            "cycle", cycle[0],
            "dependency cycle: " + " -> ".join(cycle),
            "remove one of these `- depends:` edges; a task cannot wait on work that waits "
            "on it",
        ))
    return findings


def _cycles(order, edges):
    """Every dependency cycle reachable in `edges`, each as a closed id path, in file order.

    Depth-first with the usual three colours: an edge into a node still on the stack closes a
    cycle, and the cycle is the stack from that node down plus the node again.
    """
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {n: WHITE for n in order}
    found = []
    stack = []

    def visit(node):
        colour[node] = GREY
        stack.append(node)
        for dep in edges.get(node, ()):
            if colour[dep] == GREY:
                found.append(stack[stack.index(dep):] + [dep])
            elif colour[dep] == WHITE:
                visit(dep)
        stack.pop()
        colour[node] = BLACK

    for node in order:
        if colour[node] == WHITE:
            visit(node)
    return found


def render_findings(findings):
    """The findings as the operator sees them: one line each, the fix indented under it."""
    lines = [
        f"graph: invalid -- {len(findings)} finding(s); nothing is dispatched and nothing is "
        f"written until TASKS.md is fixed:"
    ]
    for f in findings:
        lines.append(f"  {f['kind']} [{f['task']}]: {f['detail']}")
        lines.append(f"    fix: {f['fix']}")
    return "\n".join(lines)


def ready_frontier(tasks):
    """Every pending task whose dependencies are all done, in file order.

    Assumes a valid graph (`validate_graph` returned nothing). Sequential selection takes the
    first id; the whole list is what a scheduler would take, and none exists yet.
    """
    status = {t["id"]: t["status"] for t in tasks}
    return [
        t["id"] for t in tasks
        if t["status"] == "pending" and all(status.get(d) == "done" for d in t["depends"])
    ]


def graph_state(tasks, findings=None):
    """Where the kit stands as a whole -> a dict whose `state` is one of `GRAPH_STATES`.

      invalid      findings exist; nothing is selectable until they are fixed.
      complete     every task is done (an empty kit counts).
      interrupted  a task is in-progress: a run holds it, or died on it. Sequential execution
                   dispatches nothing else on its own; naming the task resumes it.
      ready        a pending task has all its dependencies done and nothing is in-progress.
      waiting      pending or blocked tasks remain, none is ready, nothing is in-progress:
                   every pending task waits, through its chain, on a blocked one.

    `frontier` is the ready set (empty unless the graph is valid), `waiting_on` maps each
    pending-but-not-ready task to the `(dependency, status)` pairs holding it, and the four
    status lists say which tasks are where. Pure; the ledger is not consulted, so
    `interrupted` cannot say whether the run is alive -- the claim taken at dispatch can.
    """
    if findings is None:
        findings = validate_graph(tasks)
    status = {t["id"]: t["status"] for t in tasks}
    by_status = {s: [t["id"] for t in tasks if t["status"] == s] for s in STATUSES}
    frontier = ready_frontier(tasks) if not findings else []
    waiting_on = {
        t["id"]: [(d, status.get(d)) for d in t["depends"] if status.get(d) != "done"]
        for t in tasks if t["status"] == "pending" and t["id"] not in frontier
    }
    if findings:
        state = "invalid"
    elif all(t["status"] == "done" for t in tasks):
        state = "complete"
    elif by_status["in-progress"]:
        state = "interrupted"
    elif frontier:
        state = "ready"
    else:
        state = "waiting"
    return {
        "state": state,
        "frontier": frontier,
        "pending": by_status["pending"],
        "in_progress": by_status["in-progress"],
        "done": by_status["done"],
        "blocked": by_status["blocked"],
        "waiting_on": waiting_on,
        "findings": findings,
    }


def render_graph_state(graph):
    """One `graph:` line (or the findings block) for `cmd_status` and the `graph` command."""
    state = graph["state"]
    if state == "invalid":
        return render_findings(graph["findings"])
    if state == "complete":
        return "graph: complete -- every task is done"
    if state == "ready":
        return (
            f"graph: ready -- frontier: {', '.join(graph['frontier'])} "
            f"(sequential: {graph['frontier'][0]} runs next)"
        )
    if state == "interrupted":
        line = (
            f"graph: interrupted -- in-progress: {', '.join(graph['in_progress'])}; resume "
            f"with --task <id>"
        )
        if graph["frontier"]:
            line += f" (also ready, by explicit --task only: {', '.join(graph['frontier'])})"
        return line
    holds = "; ".join(
        f"{tid} waits on " + ", ".join(f"{d} [{s}]" for d, s in deps)
        for tid, deps in graph["waiting_on"].items()
    )
    line = "graph: waiting -- nothing is ready"
    if holds:
        line += f": {holds}"
    if graph["blocked"]:
        line += f"; retry a blocked task with --task <id> (blocked: {', '.join(graph['blocked'])})"
    return line


def check_transition(previous, new_status):
    """Refuse a status write the task state machine has no edge for.

    `previous` is the status the DRIVER holds the task in -- what it wrote last, or what it
    read when nothing has been written yet. A worker's edit to the file is not a transition
    the driver made; `project_status` reports that separately and the driver's verdict wins.
    """
    if new_status not in STATUSES:
        raise ValueError(
            f"invalid status {new_status!r}; valid: {' | '.join(STATUSES)}"
        )
    if previous is None:
        return
    allowed = TRANSITIONS.get(previous, ())
    if new_status not in allowed:
        raise InvalidTransition(
            f"task status {previous!r} -> {new_status!r} is not a transition the driver makes; "
            f"{previous!r} may only become {' | '.join(allowed)}. A task is dispatched "
            f"(-> in-progress) before it is judged (-> done | blocked); nothing skips the "
            f"dispatch, and a finished task is only reopened by a deliberate --rerun or retry."
        )


def plan_drift(before, after):
    """The `PLAN_FIELDS` on which a fresh read of a task differs from the driver's snapshot."""
    return [f for f in PLAN_FIELDS if before.get(f) != after.get(f)]


def readiness(tasks, task_id=None, allow_rerun=False):
    """ONE readiness rule for explicit and automatic selection -> a dict.

      task    the task to run, or None
      reason  the sentence naming what stopped the run (None when `task` is set)
      mode    fresh | retry | resume | rerun, from `SELECTION_MODES` (None when `task` is None)
      graph   `graph_state(tasks)`, so the caller can report where the kit stands

    Order of checks: the graph as a whole (an invalid graph selects nothing, whatever was
    named), then the named task's existence and prerequisites, then its status. Automatic
    selection takes the first of the ready frontier and refuses while any task is in-progress,
    because two tasks running at once is scheduling, which nothing here does; naming a task
    is the deliberate way past that, and past `blocked` and (with `allow_rerun`) `done`.

    The defect this rule replaced was that naming a task skipped the dependency check
    entirely: `--task T5` ran while T4 was still pending and T5's brief assumed T4's output
    existed. Explicit and automatic selection now ask the same questions of the same graph.
    """
    graph = graph_state(tasks)

    def answer(task=None, reason=None, mode=None):
        return {"task": task, "reason": reason, "mode": mode, "graph": graph}

    if graph["state"] == "invalid":
        return answer(reason=render_findings(graph["findings"]))

    by_id = {t["id"]: t for t in tasks}
    status = {t["id"]: t["status"] for t in tasks}

    if task_id is not None:
        task = by_id.get(task_id)
        if task is None:
            return answer(reason=f"no task with id {task_id!r} in this kit")
        for dep in task["depends"]:
            if status.get(dep) != "done":
                return answer(reason=(
                    f"task {task_id} depends on {dep}, which is {status.get(dep)!r} rather "
                    f"than done"
                ))
        if task["status"] == "done" and not allow_rerun:
            return answer(reason=(
                f"task {task_id} is already done -- pass --rerun to repeat it deliberately "
                f"rather than silently redoing completed work"
            ))
        return answer(task=task, mode=SELECTION_MODES[task["status"]])

    if graph["state"] == "ready":
        return answer(task=by_id[graph["frontier"][0]], mode="fresh")
    if graph["state"] == "interrupted":
        held = graph["in_progress"]
        reason = (
            f"task {held[0]} is in-progress -- a run holds it or died on it. Resume it with "
            f"--task {held[0]} (a dead run's attempts are settled from the ledger; nothing is "
            f"replayed), or wait for the live run; sequential execution dispatches nothing "
            f"else on its own"
        )
        if len(held) > 1:
            reason += f" (also in-progress: {', '.join(held[1:])})"
        if graph["frontier"]:
            reason += f". Ready, by explicit --task only: {', '.join(graph['frontier'])}"
        return answer(reason=reason)
    if graph["state"] == "complete":
        return answer(reason="no pending task in this kit")
    hint = ""
    if graph["blocked"]:
        hint = (
            f"; retry a blocked task with --task <id> (blocked: "
            f"{', '.join(graph['blocked'])})"
        )
    if not graph["pending"]:
        return answer(reason=f"no pending task in this kit{hint}")
    return answer(reason=(
        f"no pending task has all dependencies done (pending: "
        f"{', '.join(graph['pending'])}){hint}"
    ))


def exit_if_invalid_graph(tasks, tasks_path):
    """Print the findings and exit 2 when the graph is invalid; return the findings otherwise.

    For the one driver path that previews without selecting (`--dry-run` with no `--task`
    lists every pending task): a preview of a run that would refuse should refuse the same way.
    """
    findings = validate_graph(tasks)
    if findings:
        print(f"{render_findings(findings)} ({tasks_path})", file=sys.stderr)
        sys.exit(2)
    return findings


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

    The driver-facing shape of `readiness`, which holds the rule; see it for the order of
    checks. `reason` is a sentence naming what stopped the run. "No eligible task" covers
    seven situations -- invalid graph, unknown id, unfinished dependency, already done, a task
    in-progress, nothing pending, everything waiting on a blocked task -- and an operator has
    to know which one they are looking at.
    """
    r = readiness(tasks, task_id=task_id, allow_rerun=allow_rerun)
    return r["task"], r["reason"]

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


# ---- PLAN.md routing line (step 19) ----------------------------------------------------------------
#
# `routing: policy=adaptive preference=cost profile=M` is an OPTIONAL PLAN.md line family in
# the same shape as `budget:` -- never a task field, so the TASKS.md contract is untouched.
# It names which routing policy a kit opts into; a driver's own `--policy` flag outranks it,
# and neither being given means the harness's default, which is the reserved policy on Codex.
# Values are words; which words are valid is `bin/routing_policy.py`'s vocabulary, checked by
# the driver at run time so an unknown word stops the run before anything is dispatched.
PLAN_ROUTING_RE = re.compile(r"^\s*routing:\s*(.+)$", re.MULTILINE)

PLAN_ROUTING_KEYS = ("policy", "preference", "profile")


def parse_plan_routing(text):
    """Read the kit's optional PLAN.md `routing:` line -> dict or `None`.

    Any subset of `PLAN_ROUTING_KEYS` as `key=word`; no line, no recognised key, or no
    PLAN.md -> `None` (the harness default, unchanged). Unrecognised tokens are ignored, as
    the budget line's are.
    """
    if not text:
        return None
    m = PLAN_ROUTING_RE.search(text)
    if not m:
        return None
    keys = "|".join(re.escape(k) for k in PLAN_ROUTING_KEYS)
    found = dict(re.findall(rf"({keys})=([A-Za-z0-9_.-]+)", m.group(1)))
    return found or None


# ---- the role contract (step 20) -----------------------------------------------------------------
#
# WHAT WAS MEASURED before this section existed. The interactive execute skill reads a kit's
# PLAN.md `roles:` line and sequences each declared role at its hook; no headless driver read
# that line at all (`grep roles: bin/` found only the scorecard), so a kit declaring
# `roles: test-author red-team` ran headlessly with neither, and nothing said so. The role
# templates the architect copies into a TARGET repository named this repository's own path
# (`/path/to/polytropos`) and this repository's own development fences (stdlib-only tests, no
# real `copilot`/`codex` CLI, the pricing-file convention), which are not a consumer's
# constraints. And a role's RESPONSIBILITY -- what assurance it adds, at what scope, with what
# capabilities, reporting what -- lived only in prose, so nothing could ask whether a
# workflow with fewer agents still carried the assurance the kit needed.
#
# This section states the contract as data: each role's responsibility, scope, hook,
# assurance kind, required artifacts, allowed capabilities, and result fields, SEPARATE from
# whether another agent is spawned to provide it; three workflows (`direct`, `reviewed`,
# `extended`) with the assurance each carries; one grammar for the PLAN.md `roles:` and
# `workflow:` lines that the interactive skill and every driver parse the same way; and what
# each headless driver can actually execute, so a declared role a driver cannot run is refused
# or disclosed BEFORE anything is dispatched, never skipped. Nothing here spawns a role
# because its name exists: a role runs because a kit declared it and the executor can run it.

STANDING_ROLES = ("implementer", "verifier", "reviewer")

OPTIONAL_ROLES = ("scout", "test-author", "second-verifier", "red-team", "security-auditor",
                  "docs-editor", "synthesizer")

ALL_ROLES = STANDING_ROLES + OPTIONAL_ROLES

#: The canonical pipeline order: a finding raised by an earlier layer is never marginal for a
#: later one. This is the order `marginal=` is adjudicated against and the order a roster is
#: rendered in.
PIPELINE_ORDER = ("scout", "implementer", "test-author", "verifier", "second-verifier",
                  "red-team", "reviewer", "security-auditor", "docs-editor", "synthesizer")

ROLE_SCOPES = ("task", "phase", "run")

#: What a role ADDS, named separately from the agent that adds it.
ASSURANCE_KINDS = ("deterministic-check", "independent-verification", "independent-review",
                   "adversarial-test", "fence-audit", "grounding", "documentation", "synthesis")

#: Capability grants a role may hold. A grant is what the template's tools pin and scoped-write
#: law allow; `shell` is named because a shell can still write anything, which every read-only
#: template says in words.
CAPABILITY_GRANTS = ("read", "search", "shell", "write-code", "write-tests", "write-docs",
                     "write-notes")

READ_ONLY_GRANTS = ("read", "search", "shell")

#: Every recorded role result carries these beside the role's own fields, so a later reader can
#: tell what ran, where, on what, at what cost, and what stayed unknown.
RESULT_ENVELOPE = ("role", "scope", "scope_id", "model", "dispatched", "artifacts",
                   "cost_basis", "latency_s", "unknown")


def _contract(responsibility, scope, hook, assurance, artifacts, capabilities,
              produces_findings, result):
    return {
        "responsibility": responsibility, "scope": scope, "hook": hook,
        "assurance": assurance, "artifacts": tuple(artifacts),
        "capabilities": tuple(capabilities), "produces_findings": produces_findings,
        "result": tuple(result),
    }


ROLE_CONTRACTS = {
    "implementer": _contract(
        "make the task's change so its verify command passes",
        "task", "the task's own dispatch", None,
        ("the change", "a passing verify command"),
        ("read", "search", "shell", "write-code", "write-tests", "write-docs"),
        False, ("status", "verify_rc", "dispatch_rc", "model_used", "escalations"),
    ),
    "verifier": _contract(
        "re-derive the task's verdict from repo state against its acceptance, trusting "
        "nothing the implementer claimed",
        "task", "after the implementer reports done", "independent-verification",
        ("rerun verify output", "per-acceptance-line evidence"), READ_ONLY_GRANTS,
        True, ("verdict", "findings", "confirmed", "marginal"),
    ),
    "reviewer": _contract(
        "judge a completed phase against PLAN.md for drift, scope creep, and contract "
        "breakage",
        "phase", "phase end", "independent-review",
        ("findings with file:line evidence", "a phase verdict"), READ_ONLY_GRANTS,
        True, ("verdict", "findings", "confirmed"),
    ),
    "scout": _contract(
        "ground the implementer in actual repo state before it starts",
        "task", "before the implementer, per opted-in task", "grounding",
        ("a grounding brief", "brief-vs-repo discrepancies"), READ_ONLY_GRANTS,
        False, ("grounding_brief", "discrepancies"),
    ),
    "test-author": _contract(
        "write tests from the brief's acceptance, never from the implementation",
        "task", "after the implementer, before the verifier", "adversarial-test",
        ("test files under the repo's test path",), ("read", "search", "shell", "write-tests"),
        True, ("files", "findings", "confirmed", "marginal"),
    ),
    "second-verifier": _contract(
        "verify functional reality with a lens the first verifier did not use",
        "task", "in parallel with the verifier", "independent-verification",
        ("rerun verify output", "exercised-behaviour evidence"), READ_ONLY_GRANTS,
        True, ("verdict", "findings", "confirmed", "marginal"),
    ),
    "red-team": _contract(
        "break the verified deliverable with what the acceptance never anticipated",
        "task", "after the verifier passes, before done", "adversarial-test",
        ("reproducible breaks",), READ_ONLY_GRANTS,
        True, ("findings", "confirmed", "marginal"),
    ),
    "security-auditor": _contract(
        "check the phase against the kit's fences and leak surfaces, and nothing else",
        "phase", "phase end, in parallel with the reviewer", "fence-audit",
        ("fence findings with file:line evidence",), READ_ONLY_GRANTS,
        True, ("findings", "confirmed", "marginal"),
    ),
    "docs-editor": _contract(
        "make documentation and comments say what the code now does",
        "phase", "phase end, after findings are adjudicated", "documentation",
        ("edited docs and comments",), ("read", "search", "shell", "write-docs"),
        False, ("files", "gaps"),
    ),
    "synthesizer": _contract(
        "distil the run's cross-task learnings into NOTES.md prose",
        "run", "end of run", "synthesis",
        ("NOTES.md prose",), ("read", "search", "write-notes"),
        False, ("prose",),
    ),
}

WORKFLOWS = ("direct", "reviewed", "extended")
DEFAULT_WORKFLOW = "reviewed"

#: The roles each workflow runs. `extended` is `reviewed` plus whatever the kit declared.
WORKFLOW_ROLES = {
    "direct": ("implementer",),
    "reviewed": STANDING_ROLES,
    "extended": STANDING_ROLES,
}

#: The assurance each workflow carries before any declared role adds its own. `direct` is the
#: task's own deterministic check and nothing independent; it must be asked for by name.
WORKFLOW_ASSURANCE = {
    "direct": ("deterministic-check",),
    "reviewed": ("deterministic-check", "independent-verification", "independent-review"),
    "extended": ("deterministic-check", "independent-verification", "independent-review"),
}

PLAN_ROLES_RE = re.compile(r"^\s*roles:[ \t]*(.*)$", re.MULTILINE)
PLAN_WORKFLOW_RE = re.compile(r"^\s*workflow:[ \t]*(\S*)", re.MULTILINE)

#: What each executor can do with a role. `sequenced`: it runs the role at the role's hook;
#: `partial`: the role's assurance is provided another way, named in the note; `unsupported`:
#: nothing runs it; `unknown`: nobody has checked. The three headless drivers run one task per
#: invocation (`run`) and one phase review (`review`); none sequences a per-task agent beside
#: the implementer, which is why the optional roles are `unsupported` there today and a kit
#: that declares one is refused or disclosed before dispatch. Tested against the drivers' own
#: parsers, not asserted from memory.
ROLE_SUPPORT = {
    "interactive": {role: ("sequenced", "the execute skill's loop") for role in ALL_ROLES},
    "claude-code": {
        "implementer": ("sequenced", "run"),
        "verifier": ("partial", "run executes the verify command; no verifier agent is "
                                "dispatched per task"),
        "reviewer": ("sequenced", "review"),
        **{role: ("unsupported", "run is one task, one role; no hook sequencing")
           for role in OPTIONAL_ROLES},
    },
    "copilot": {
        "implementer": ("sequenced", "run"),
        "verifier": ("partial", "run executes the verify command; no verifier agent is "
                                "dispatched per task"),
        "reviewer": ("sequenced", "review"),
        **{role: ("unsupported", "run is one task, one agent; no hook sequencing")
           for role in OPTIONAL_ROLES},
    },
    "codex": {
        "implementer": ("sequenced", "run"),
        "verifier": ("partial", "run executes the verify command; review dispatches an "
                                "independent verifier per phase, not per task"),
        "reviewer": ("sequenced", "review, then accept"),
        **{role: ("unsupported", "run refuses any role but implementer")
           for role in OPTIONAL_ROLES},
    },
    "cursor": {role: ("unknown", "no adapter yet") for role in ALL_ROLES},
}

EXECUTORS = tuple(ROLE_SUPPORT)

GAP_MODES = ("stop", "disclose")


class RosterError(ValueError):
    """A PLAN.md roster the contract cannot act on: an unknown role or workflow word, or a
    contradiction between them."""


def parse_plan_roles(text):
    """The kit's optional PLAN.md `roles:` line -> a list of optional-role tokens, or None.

    No line, or an empty one, -> None (the standing trio). An unknown token or a repeated one
    raises `RosterError`: the architect skill says anything outside the seven is out of
    grammar, and a driver that guessed would dispatch something the kit never asked for.
    """
    if not text:
        return None
    m = PLAN_ROLES_RE.search(text)
    if not m:
        return None
    tokens = m.group(1).split()
    if not tokens:
        return None
    seen = []
    for token in tokens:
        if token not in OPTIONAL_ROLES:
            hint = ("is a standing role, always present" if token in STANDING_ROLES
                    else "is not a role")
            raise RosterError(
                f"roles: {token!r} {hint}; the optional roles are "
                f"{', '.join(OPTIONAL_ROLES)}"
            )
        if token in seen:
            raise RosterError(f"roles: {token!r} is declared twice")
        seen.append(token)
    return seen


def parse_plan_workflow(text):
    """The kit's optional PLAN.md `workflow:` line -> one of `WORKFLOWS`, or None."""
    if not text:
        return None
    m = PLAN_WORKFLOW_RE.search(text)
    if not m:
        return None
    word = m.group(1)
    if word not in WORKFLOWS:
        raise RosterError(
            f"workflow: {word!r} is not a workflow; valid: {', '.join(WORKFLOWS)}"
        )
    return word


def resolve_roster(text):
    """The kit's roster from PLAN.md -> a dict: workflow, roles in pipeline order, declared
    optional roles, the assurance the workflow carries, and each role's hook.

    No `workflow:` line means `reviewed` (the standing trio, every kit ever written) or
    `extended` when roles are declared. `direct` must be named, because it drops independent
    review, and it cannot coexist with declared roles; `reviewed` with declared roles is a
    contradiction too -- say `extended`, or drop the line.
    """
    declared = parse_plan_roles(text) or []
    workflow = parse_plan_workflow(text)
    if workflow is None:
        workflow = "extended" if declared else DEFAULT_WORKFLOW
    elif workflow != "extended" and declared:
        raise RosterError(
            f"workflow: {workflow} cannot declare roles ({', '.join(declared)}); "
            f"a kit with declared roles is `extended`"
        )
    elif workflow == "extended" and not declared:
        raise RosterError("workflow: extended declares no roles; add a `roles:` line or say "
                          "`reviewed`")
    roles = [r for r in PIPELINE_ORDER if r in WORKFLOW_ROLES[workflow] or r in declared]
    assurance = list(WORKFLOW_ASSURANCE[workflow])
    for role in declared:
        kind = ROLE_CONTRACTS[role]["assurance"]
        if kind and kind not in assurance:
            assurance.append(kind)
    return {
        "workflow": workflow,
        "roles": roles,
        "declared": declared,
        "assurance": assurance,
        "hooks": {role: ROLE_CONTRACTS[role]["hook"] for role in roles},
        "binding_review": workflow != "direct",
    }


def roster_support(roster, executor):
    """What `executor` can do with each role in `roster` -> a dict.

      levels     {role: (level, note)}
      gap        declared optional roles the executor cannot run (the refusable gap)
      partial    roles whose assurance is provided another way (disclosed, never refused)
      unknown    roles nobody has checked on this executor
    """
    if executor not in ROLE_SUPPORT:
        raise RosterError(f"unknown executor {executor!r}; known: {', '.join(EXECUTORS)}")
    table = ROLE_SUPPORT[executor]
    levels = {role: table[role] for role in roster["roles"]}
    return {
        "executor": executor,
        "levels": levels,
        "gap": [r for r in roster["declared"] if levels[r][0] == "unsupported"],
        "partial": [r for r, (lvl, _n) in levels.items() if lvl == "partial"],
        "unknown": [r for r, (lvl, _n) in levels.items() if lvl == "unknown"],
    }


def render_roster(roster, support=None):
    """One `roster:` line, plus a line per gap or partial role when `support` is given."""
    line = (f"roster: workflow={roster['workflow']} roles={','.join(roster['roles'])} "
            f"assurance={'+'.join(roster['assurance'])}")
    if support is None:
        return line
    lines = [line + f" executor={support['executor']}"]
    for role in support["gap"]:
        lines.append(f"  gap: {role} is not executed by this driver "
                     f"({support['levels'][role][1]}); hook: {roster['hooks'][role]}")
    for role in support["partial"]:
        lines.append(f"  partial: {role} -- {support['levels'][role][1]}")
    for role in support["unknown"]:
        lines.append(f"  unknown: {role} -- {support['levels'][role][1]}")
    return "\n".join(lines)


def roster_for_run(plan_text, executor, gap_mode="stop", slug="<slug>"):
    """The roster check every driver runs BEFORE dispatch -> `(roster, support)`.

    Prints the roster to stderr. A grammar error exits 2. A declared role this executor
    cannot run exits 2 under `stop` (the default), naming the role, its hook, and the three
    supported alternatives; under `disclose` the run proceeds with the gap printed and, once
    the ledger is open, recorded (`record_roster`). Partial standing roles are disclosed and
    never stop: every kit ever written runs `reviewed`, and the drivers have always provided
    its independent review at phase end rather than per task.
    """
    if gap_mode not in GAP_MODES:
        raise RosterError(f"unknown roster gap mode {gap_mode!r}; valid: {', '.join(GAP_MODES)}")
    try:
        roster = resolve_roster(plan_text)
    except RosterError as exc:
        print(f"roster: {exc}", file=sys.stderr)
        sys.exit(2)
    support = roster_support(roster, executor)
    print(render_roster(roster, support), file=sys.stderr)
    if support["gap"]:
        names = ", ".join(support["gap"])
        if gap_mode == "stop":
            print(
                f"roster: PLAN.md declares {names}, which this driver cannot execute, so "
                f"nothing is dispatched. Supported alternatives: run the kit interactively "
                f"(/polytropos:execute {slug}), which sequences every declared role at its "
                f"hook; remove the role from PLAN.md's roles: line; or rerun with "
                f"--roster-gap disclose to proceed with the gap recorded in the ledger.",
                file=sys.stderr,
            )
            sys.exit(2)
        print(
            f"roster: proceeding WITHOUT {names} (--roster-gap disclose); the kit's declared "
            f"assurance is not what this run provides, and the ledger records that.",
            file=sys.stderr,
        )
    return roster, support


def record_roster(lifecycle, roster, support, gap_mode):
    """Record the roster check on the run, so the history can tell a run that provided the
    kit's declared assurance from one that disclosed a gap."""
    return lifecycle.ledger.append(
        "roster.checked", run=lifecycle.run, task=lifecycle.task_id,
        workflow=roster["workflow"], roles=roster["roles"], declared=roster["declared"],
        assurance=roster["assurance"], executor=support["executor"], gap=support["gap"],
        partial=support["partial"], gap_mode=gap_mode,
    )


def _plan_text(kit_dir):
    path = Path(kit_dir) / "PLAN.md"
    return path.read_text() if path.exists() else ""

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
    # Step 18: the same graph verdict `run` will reach, so an operator sees an invalid kit or
    # an interrupted task from `status` rather than from a refused run.
    print(render_graph_state(graph_state(tasks)))
    # Step 20: the kit's roster and the assurance it declares, from the same grammar `run`
    # checks before dispatching.
    try:
        print(render_roster(resolve_roster(_plan_text(args.kit))))
    except RosterError as exc:
        print(f"roster: INVALID -- {exc}")


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

    The write is a transition of the task state machine (`TRANSITIONS`) and is checked as
    one, from the status the driver holds the task in: `expected` when given, else what the
    file says. An edge the machine lacks (`pending -> done`, a verdict with no dispatch) is
    refused before the temporary file exists, so nothing is mutated.
    """
    tasks_path = Path(tasks_path)
    text = tasks_path.read_text()
    previous = next((t["status"] for t in parse_tasks(text) if t["id"] == task_id), None)
    check_transition(expected if expected is not None else previous, new_status)
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
    # PLAN DRIFT (step 18). The driver dispatched the snapshot's brief and ran the snapshot's
    # verify command; a worker with write access may have changed the block underneath it.
    # Neither the verdict nor the file is changed here -- the verdict is about the work the
    # check judged, and the file is the architect's to restore -- but the edit is named on
    # stderr, recorded in the ledger, and carried in `result`, so a plan that changed under a
    # run never reads as the plan the run was judged against.
    fresh = next((t for t in parse_tasks(text) if t["id"] == task["id"]), None)
    drift = plan_drift(task, fresh) if fresh is not None else []
    result["plan_drift"] = drift
    if drift:
        lifecycle.ledger.append("plan.drift", run=lifecycle.run, task=task["id"],
                                fields=drift)
        print(
            f"plan-drift: task {task['id']}'s TASKS.md block changed while this run held it "
            f"({', '.join(drift)}); the verdict ({result['status']}) is for the brief and "
            f"verify command the run started with, not for what the file says now. A worker "
            f"may not rewrite its own acceptance; restore the block or re-plan it deliberately",
            file=sys.stderr,
        )
    return text


# ---- command line: the graph, and a demo of it --------------------------------------------------

def _demo_task(task_id, status="pending", depends=()):
    return {
        "id": task_id, "title": f"demo task {task_id}", "status": status, "model": None,
        "depends": list(depends), "independent": not depends, "evidence": None,
        "brief": f"do {task_id}", "verify": "true",
    }


def _demo(out=None):
    """A diamond DAG walked to completion, an interrupted kit, then four invalid graphs and a
    refused transition. Synthetic tasks in memory: no files, no store, no process."""
    out = out or sys.stdout

    def say(line=""):
        print(line, file=out)

    say("== a diamond: T1 -> {T2, T3} -> T4, walked sequentially ==")
    diamond = [_demo_task("T1"), _demo_task("T2", depends=["T1"]),
               _demo_task("T3", depends=["T1"]), _demo_task("T4", depends=["T2", "T3"])]
    while True:
        r = readiness(diamond)
        say(f"  {render_graph_state(r['graph'])}")
        if r["task"] is None:
            say(f"  selection: {r['reason']}")
            break
        say(f"  selection: {r['task']['id']} ({r['mode']}) -> done")
        r["task"]["status"] = "done"

    say()
    say("== interrupted: T2 is in-progress, T3 is ready ==")
    kit = [_demo_task("T1", "done"), _demo_task("T2", "in-progress", ["T1"]),
           _demo_task("T3", depends=["T1"]), _demo_task("T4", depends=["T2", "T3"])]
    r = readiness(kit)
    say(f"  {render_graph_state(r['graph'])}")
    say(f"  automatic: {r['reason']}")
    r = readiness(kit, "T2")
    say(f"  --task T2: {r['task']['id']} ({r['mode']})")
    r = readiness(kit, "T4")
    say(f"  --task T4: {r['reason']}")

    say()
    say("== invalid graphs: each selects nothing and names its fix ==")
    invalid = {
        "duplicate id": [_demo_task("T1"), _demo_task("T1")],
        "self-dependency": [_demo_task("T1", depends=["T1"])],
        "unknown dependency": [_demo_task("T1"), _demo_task("T2", depends=["T9"])],
        "cycle": [_demo_task("T1", depends=["T2"]), _demo_task("T2", depends=["T3"]),
                  _demo_task("T3", depends=["T1"]), _demo_task("T4")],
    }
    for label, tasks in invalid.items():
        r = readiness(tasks)
        say(f"  [{label}] task selected: {r['task']}")
        for line in r["reason"].splitlines():
            say(f"    {line}")

    say()
    say("== a status write with no edge is refused before anything is written ==")
    for previous, new in (("pending", "done"), ("done", "blocked"), ("in-progress", "done")):
        try:
            check_transition(previous, new)
            say(f"  {previous} -> {new}: allowed")
        except InvalidTransition as exc:
            say(f"  {previous} -> {new}: REFUSED -- {str(exc).split(';')[0]}")

    say()
    say("== three workflows, one roster grammar, and what each executor can run ==")
    plans = {
        "no line": "# plan\nbudget: max-dispatches=4\n",
        "roles: test-author red-team": "# plan\nroles: test-author red-team\n",
        "workflow: direct": "# plan\nworkflow: direct\n",
        "roles: chef": "# plan\nroles: chef\n",
    }
    for label, plan in plans.items():
        say(f"  [{label}]")
        try:
            roster = resolve_roster(plan)
        except RosterError as exc:
            say(f"    roster: INVALID -- {exc}")
            continue
        for executor in ("interactive", "codex"):
            for line in render_roster(roster, roster_support(roster, executor)).splitlines():
                say(f"    {line}")


def _cli(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        prog="kit_contract.py",
        description="The one kit contract. `graph` validates a kit's execution DAG and reports "
                    "its ready frontier; `demo` walks synthetic graphs and spends nothing.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_graph = sub.add_parser("graph", help="validate TASKS.md's DAG; exit 2 when invalid")
    p_graph.add_argument("--kit", required=True, help="kit directory holding TASKS.md")
    p_graph.add_argument("--json", action="store_true", help="the graph_state dict as JSON")
    p_roster = sub.add_parser("roster", help="PLAN.md's workflow, roles, assurance, and what "
                                             "an executor can run; exit 2 on a grammar "
                                             "error, 1 when the executor has a gap")
    p_roster.add_argument("--kit", required=True, help="kit directory holding PLAN.md")
    p_roster.add_argument("--executor", default="interactive", choices=EXECUTORS,
                          help="who would run it (default: the interactive execute skill)")
    p_roster.add_argument("--json", action="store_true",
                          help="roster, support, and every role's contract as JSON")
    sub.add_parser("demo", help="a diamond DAG walked to completion, invalid graphs, rosters")
    args = parser.parse_args(argv)

    if args.cmd == "demo":
        _demo()
        return 0
    if args.cmd == "roster":
        try:
            roster = resolve_roster(_plan_text(args.kit))
        except RosterError as exc:
            print(f"roster: {exc}", file=sys.stderr)
            return 2
        support = roster_support(roster, args.executor)
        if args.json:
            print(json.dumps({
                "v": CONTRACT_VERSION, "roster": roster, "support": support,
                "contracts": {role: ROLE_CONTRACTS[role] for role in roster["roles"]},
            }, indent=2, sort_keys=True))
        else:
            print(render_roster(roster, support))
        return 1 if support["gap"] else 0
    tasks = parse_tasks(_read_tasks_text(args.kit))
    graph = graph_state(tasks)
    if args.json:
        print(json.dumps(graph, indent=2, sort_keys=True))
    else:
        print(render_graph_state(graph))
    return 2 if graph["state"] == "invalid" else 0


if __name__ == "__main__":
    sys.exit(_cli())
