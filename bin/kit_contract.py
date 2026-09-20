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

import hashlib
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

#: Step 24: whether a done task's acceptance still rests on the upstream artifact versions it
#: was verified against. `unknown` is a kit accepted before versions were recorded, or a
#: workspace git cannot fingerprint; it is disclosed, never rounded to fresh or stale.
FRESHNESS_STATES = ("fresh", "stale", "unknown")
#: The one selection mode `SELECTION_MODES` does not key by status: a done task whose evidence
#: is stale is re-verified in place (no dispatch) when named. `--rerun` still means rerun.
REFRESH_MODE = "refresh"

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


def graph_state(tasks, findings=None, freshness=None):
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

    Step 24: `freshness` (from `evidence_freshness`) names done tasks whose acceptance is
    stale because an upstream task was re-accepted with a different artifact. A task that
    depends on a stale acceptance is NOT ready -- its brief assumes upstream output that has
    since changed -- and waits on `<dep> [done (stale)]` until that task is refreshed.
    """
    if findings is None:
        findings = validate_graph(tasks)
    status = {t["id"]: t["status"] for t in tasks}
    by_status = {s: [t["id"] for t in tasks if t["status"] == s] for s in STATUSES}
    stale = sorted(tid for tid, f in (freshness or {}).items() if f.get("state") == "stale")
    stale_set = set(stale)
    frontier = ready_frontier(tasks) if not findings else []
    frontier = [tid for tid in frontier
                if not any(d in stale_set for d in next(t for t in tasks if t["id"] == tid)["depends"])]

    def holding(t):
        return [(d, "done (stale)" if d in stale_set else status.get(d))
                for d in t["depends"] if status.get(d) != "done" or d in stale_set]

    waiting_on = {
        t["id"]: holding(t)
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
        "stale": stale,
        "stale_detail": {tid: (freshness or {})[tid].get("changed", []) for tid in stale},
    }


def render_stale(graph):
    """The stale-evidence clause for a graph line, or "" (step 24)."""
    stale = graph.get("stale") or []
    if not stale:
        return ""
    parts = []
    for tid in stale:
        changed = graph.get("stale_detail", {}).get(tid) or []
        parts.append(f"{tid} (upstream {', '.join(changed)} re-accepted with a different "
                     f"artifact)" if changed else tid)
    return (f"; stale evidence: {'; '.join(parts)} -- re-verify with "
            f"`kit_contract.py refresh --task <id>`, or --rerun it")


def render_graph_state(graph):
    """One `graph:` line (or the findings block) for `cmd_status` and the `graph` command."""
    state = graph["state"]
    if state == "invalid":
        return render_findings(graph["findings"])
    if state == "complete":
        return "graph: complete -- every task is done" + render_stale(graph)
    if state == "ready":
        return (
            f"graph: ready -- frontier: {', '.join(graph['frontier'])} "
            f"(sequential: {graph['frontier'][0]} runs next)"
        ) + render_stale(graph)
    if state == "interrupted":
        line = (
            f"graph: interrupted -- in-progress: {', '.join(graph['in_progress'])}; resume "
            f"with --task <id>"
        )
        if graph["frontier"]:
            line += f" (also ready, by explicit --task only: {', '.join(graph['frontier'])})"
        return line + render_stale(graph)
    holds = "; ".join(
        f"{tid} waits on " + ", ".join(f"{d} [{s}]" for d, s in deps)
        for tid, deps in graph["waiting_on"].items()
    )
    line = "graph: waiting -- nothing is ready"
    if holds:
        line += f": {holds}"
    if graph["blocked"]:
        line += f"; retry a blocked task with --task <id> (blocked: {', '.join(graph['blocked'])})"
    return line + render_stale(graph)


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


def readiness(tasks, task_id=None, allow_rerun=False, freshness=None):
    """ONE readiness rule for explicit and automatic selection -> a dict.

      task    the task to run, or None
      reason  the sentence naming what stopped the run (None when `task` is set)
      mode    fresh | retry | resume | rerun, from `SELECTION_MODES`, or `refresh` for a
              done task whose evidence is stale (None when `task` is None)
      graph   `graph_state(tasks, freshness=...)`, so the caller can report where the kit stands

    Order of checks: the graph as a whole (an invalid graph selects nothing, whatever was
    named), then the named task's existence and prerequisites, then its status. Automatic
    selection takes the first of the ready frontier and refuses while any task is in-progress,
    because two tasks running at once is scheduling, which nothing here does; naming a task
    is the deliberate way past that, and past `blocked` and (with `allow_rerun`) `done`.

    The defect this rule replaced was that naming a task skipped the dependency check
    entirely: `--task T5` ran while T4 was still pending and T5's brief assumed T4's output
    existed. Explicit and automatic selection now ask the same questions of the same graph.
    """
    graph = graph_state(tasks, freshness=freshness)
    stale = set(graph.get("stale") or [])

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
            if dep in stale:
                changed = graph["stale_detail"].get(dep) or []
                return answer(reason=(
                    f"task {task_id} depends on {dep}, whose acceptance is stale: upstream "
                    f"{', '.join(changed) or 'task(s)'} re-accepted with a different artifact "
                    f"after {dep} was verified. Refresh {dep} first "
                    f"(`kit_contract.py refresh --task {dep}`) or --rerun it"
                ))
        if task["status"] == "done" and task_id in stale and not allow_rerun:
            return answer(task=task, mode=REFRESH_MODE)
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


def select_task(tasks, task_id=None, allow_rerun=False, freshness=None):
    """The task to run -> `(task, reason)`, exactly one of which is None.

    The driver-facing shape of `readiness`, which holds the rule; see it for the order of
    checks. `reason` is a sentence naming what stopped the run. "No eligible task" covers
    seven situations -- invalid graph, unknown id, unfinished dependency, already done, a task
    in-progress, nothing pending, everything waiting on a blocked task -- and an operator has
    to know which one they are looking at.
    """
    r = readiness(tasks, task_id=task_id, allow_rerun=allow_rerun, freshness=freshness)
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
    """Normalise what a dispatch runner returned -> `(rc, output, timing)`.

    `(rc, output, timing)` is the production contract (`default_runner` always returns one) and
    `rc` is then AUTHORITATIVE: a non-zero exit is a failed dispatch, whatever a later check
    says. `timing` is the `proc_runner` result dict when the runner supplied one
    (decision-improvement D05) -- carrying `duration_s` and the named `outcome`
    (`ok`/`failed`/`timeout`/`cancelled`/`missing-executable`/...) a caller passes on to
    `TaskRun.attempt_finished` so a timeout is recorded as a timeout rather than collapsed into
    a generic failure. A 2-tuple (the shape
    every existing test's injected runner returns) normalises to `timing={}`, which reads back
    as unmeasured -- never as a zero-second dispatch.

    `None` means the runner declined to report -- the shape injected fixtures use. That is
    recorded as UNKNOWN (`rc is None`), never as success. Unknown does not by itself block
    completion, because a fixture that reports nothing is not evidence of failure; a reported
    non-zero exit is.
    """
    if value is None:
        return None, "", {}
    if len(value) == 3:
        rc, output, timing = value
        return rc, output or "", timing if isinstance(timing, dict) else {}
    rc, output = value
    return rc, output or "", {}

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

    A GRANT NOW HAS AN IDENTITY. The only durable trace of an admission used to be indirect --
    an attempt exists, therefore something admitted it -- so nothing could say WHICH grant
    licensed which call, and a refused operation left no record at all beyond a NOTES.md line.
    `admit` now mints a grant record, and `ref_for` hands the attempt ledger a pointer to it.
    Minting is unconditional on success and impossible on refusal: a refused operation is not
    a grant, so no reference exists for it to carry. What a cap MEANS is untouched --
    `OPERATION_CAPS` still decides which caps a kind draws down, `max-dispatches` still counts
    exactly initial, retry, escalation and consult, and review and acceptance still draw only
    on `max-model-calls`.
    """

    def __init__(self, plan_budget, used=None):
        self.budget = dict(plan_budget or {})
        self.used = {k: int(v) for k, v in (used or {}).items()}
        self.granted = []
        #: One record per grant issued, in order, parallel to `granted` (which stays a list of
        #: kind words because callers and tests read it that way).
        self.grants = []
        self._claimed = set()

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
        self.grants.append(self._mint(kind))
        return True, None

    def _mint(self, kind):
        """The identity of the grant just issued -> `{"id", "kind", "sha"}`.

        Minted HERE, at admission, because the grant exists before the attempt does: an attempt
        id cannot identify the allowance that licensed it. The id is content-free
        (`secrets.token_hex`, the same rule as `generate_run_id` and `new_attempt_id`), and the
        digest covers the grant's own content -- the operation kind, the caps it drew down, the
        ceilings those caps carried and the counts AFTER this grant -- so two grants of the same
        kind at different points in a ladder are distinguishable. A digest identifies content;
        it is not a protection against anything, and nothing here treats it as one.
        """
        caps = list(OPERATION_CAPS.get(kind, ()))
        material = json.dumps(
            {
                "kind": kind,
                "caps": caps,
                "budget": {k: self.budget.get(k) for k in caps},
                "used": {k: self.used.get(k, 0) for k in caps},
            },
            sort_keys=True,
        )
        return {"id": secrets.token_hex(4), "kind": kind,
                "sha": hashlib.sha256(material.encode("utf-8")).hexdigest()}

    def ref_for(self, kind):
        """The reference for the grant that admitted a `kind` operation, or None.

        Only the most recent grant, only when it was issued for this kind, and only once. A
        grant funds exactly ONE operation, so a second attempt claiming the same grant would be
        a dispatch nobody admitted -- precisely the defect the per-operation gate exists to
        prevent -- and the reference must not paper over it. Every other case answers None,
        which reads as unknown: a correlation nobody can establish is not one to guess.
        """
        grant = self.grants[-1] if self.grants else None
        if grant is None or grant["kind"] != kind or grant["id"] in self._claimed:
            return None
        self._claimed.add(grant["id"])
        return _al().make_ref(grant["id"], sha=grant["sha"], version=CONTRACT_VERSION)


def acceptance_identity(task):
    """The content identity of what a task must satisfy -> a reference, or None.

    WHAT WAS MISSING. A task's acceptance is free text in TASKS.md beside its brief, and
    nothing recorded WHICH text a verdict was reached against. `evidence_freshness` pins the
    ARTIFACT an acceptance was reached on -- the tree -- and says nothing about the criteria, so
    a kit whose acceptance wording was edited after a task was accepted reads exactly like one
    whose was not.

    This is that identity: a digest over the task id, its acceptance text and the verify command
    that checks it, stamped with this contract's version. Both halves are in it deliberately --
    changing what the check RUNS changes what "accepted" means as surely as changing the prose
    does. A task that declares no acceptance has no identity to record and gets None, which is
    unknown.

    It is computed from the source as it stands NOW and is never reconstructed for a record
    written earlier. Capturing a still-existing source late is fine; an attempt recorded before
    acceptance identities existed simply has none.
    """
    task = task or {}
    acceptance = task.get("acceptance")
    if not acceptance or not str(acceptance).strip():
        return None
    material = json.dumps(
        {"task": task.get("id"), "acceptance": acceptance, "verify": task.get("verify"),
         "contract": CONTRACT_VERSION},
        sort_keys=True, ensure_ascii=False,
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return _al().make_ref(digest[:16], sha=digest, version=CONTRACT_VERSION)


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
    "cursor": {
        "implementer": ("sequenced", "run (agent -p --force)"),
        "verifier": ("partial", "run executes the verify command under the execution "
                                "boundary; no verifier agent is dispatched per task"),
        "reviewer": ("sequenced", "review (agent -p --mode ask)"),
        **{role: ("unsupported", "run is one task, one role; no hook sequencing")
           for role in OPTIONAL_ROLES},
    },
    # Step 24: the scheduler's conformance executor -- a throwaway stub process standing in
    # for a harness so batching, isolation, integration, and cancellation can be proven
    # without a model. It sequences the implementer (one task, one copy) and runs the
    # deterministic check; it has no review and no optional role. Never a real harness.
    "stub": {
        "implementer": ("sequenced", "kit_scheduler.py run --harness stub"),
        "verifier": ("partial", "the verify command runs under the execution boundary in the "
                                "worker's copy and again on the merged tree; no verifier agent"),
        "reviewer": ("unsupported", "the stub executor has no review; it exists for conformance"),
        **{role: ("unsupported", "the stub executor sequences nothing but the implementer")
           for role in OPTIONAL_ROLES},
    },
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
    # an interrupted task from `status` rather than from a refused run. Step 24: with the
    # ledger's artifact bindings, so stale evidence shows here before a run refuses on it.
    print(render_graph_state(graph_state(
        tasks, freshness=kit_freshness(args.kit, tasks, store=getattr(args, "attempt_store", None)))))
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

    Returns `(rc, output, timing)` -- widened from the historical `(rc, output)`
    (decision-improvement D05) so a caller can record what `proc_runner` measured without
    re-deriving it: `timing` IS the full `proc_runner` result dict (`duration_s`, `outcome`,
    `terminal`, `timed_out`, among others),
    the same shape `cursor_execute.default_runner` already returns as its third element. Every
    existing caller that unpacked `(rc, output) = runner(argv)` went through `dispatch_status`,
    which still accepts and normalises this shape (see below); nothing that only reads index 0
    or 1 is affected by the extra element.
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
        return result["rc"], output, result

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


def budget_gate(kit_dir, tasks, task, run_id, lifecycle, consult=False, role="implementer"):
    """The PLAN.md budget dial, checked against the kit's own record BEFORE anything is
    dispatched -> a `BudgetAdmission` (or None when the kit declares no budget).

    A cap already reached prints the stop, writes ONE budget-stop outcome line unless the
    task already carries a verdict (a budget stop never displaces one), ends the lifecycle,
    and exits 1 -- the task's status is left exactly as found. The three original drivers
    carry this block inline; an adapter built on the contract calls this.
    """
    kit_dir = Path(kit_dir)
    plan_path = kit_dir / "PLAN.md"
    plan_budget = parse_plan_budget(plan_path.read_text()) if plan_path.exists() else None
    if not plan_budget:
        return None
    notes_path = kit_dir / "NOTES.md"
    notes_text = notes_path.read_text() if notes_path.exists() else ""
    used = combined_usage(notes_text, lifecycle.ledger)
    admission = BudgetAdmission(plan_budget, used)
    # So every attempt this lifecycle records names the grant that admitted it. Bound before
    # the exhaustion check, because a refusal mints no grant and therefore needs no reference.
    lifecycle.bind_admission(admission)
    exhausted_key = plan_budget_exhausted(plan_budget, used, is_consult=consult)
    if not exhausted_key:
        return admission
    cap = plan_budget[exhausted_key]
    remaining = sum(1 for t in tasks if t["status"] == "pending")
    print(
        f"budget-stop: PLAN.md budget {exhausted_key}={cap} already reached "
        f"(used={used[exhausted_key]}) -- task {task['id']} was NOT dispatched; "
        f"{remaining} pending task(s) (including this one) left untouched. See NOTES.md.",
        file=sys.stderr,
    )
    prior_result = recorded_outcome_result(notes_text, task["id"])
    if prior_result is not None and prior_result != "budget-stop":
        print(
            f"budget-stop: NOT recorded in the ledger -- task {task['id']} already carries "
            f"result={prior_result} and a budget-stop is not a verdict, so writing one would "
            f"displace recorded evidence. The stop above still applies: nothing was dispatched.",
            file=sys.stderr,
        )
    else:
        append_plan_budget_stop_note(notes_path, task, run_id, exhausted_key, cap,
                                     used[exhausted_key], remaining, role=role)
    lifecycle.end("budget-stop", reason=f"{exhausted_key}={cap} reached")
    sys.exit(1)


def append_run_note(notes_path, result, task, run_id=None, parent=None, actor="driver",
                    extra=()):
    """The generic NOTES.md run block, for an adapter that has no harness-specific bullets.

    The three original drivers keep their own `append_note` (each carries a bullet the others
    do not); an adapter built on this contract writes the same block shape through this one:
    the heading, role, planned and used model, escalations, verify exit, the step-16 and
    step-19 bullets when present, any `extra` bullets, then exactly ONE outcome line. A
    `parent` rides the line only on `escalated-pass`, as everywhere else.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    task_id = task["id"]
    model_used = result.get("model_used")
    escalations = result.get("escalations") or []
    lines = [
        f"## {ts}{EM_DASH}{task_id}",
        f"- role: {result.get('role', 'implementer')}",
        f"- harness: {actor}",
        f"- planned model: {result.get('planned_model') or task.get('model') or 'unpinned'}",
        f"- model used: {model_used or f'{actor} default'}",
        f"- observed model: {result.get('observed_model') or 'unknown'}",
        f"- escalations: {' -> '.join(escalations) if escalations else '(none)'}",
        f"- verify: exit {result.get('verify_rc')}",
    ]
    if result.get("dispatch_rc") not in (None, 0):
        lines.append(f"- dispatch: exit {result['dispatch_rc']}")
    if result.get("class"):
        lines.append(f"- failure-class: {result['class']}")
    if result.get("reconciled"):
        lines.append(f"- reconciled: {result['reconciled']} earlier attempt(s) settled by "
                     f"re-running the check; nothing was re-dispatched")
    if result.get("plan_drift"):
        lines.append(f"- plan-drift: {', '.join(result['plan_drift'])}")
    if result.get("usd") is None:
        lines.append("- usd: null (unpriced; the harness reports no usage)")
    lines.extend(extra)
    attempts = result.get("ledger_attempts")
    if attempts is None:
        attempts = 1 + len(escalations)
    outcome_model = model_used if model_used else "unpinned"
    result_word = outcome_result(result.get("status"), escalations, parent)
    line_parent = parent if result_word == "escalated-pass" else None
    lines.append("- " + build_outcome_line(task_id, outcome_model, attempts, result_word,
                                           run_id=run_id, parent=line_parent))
    append_block(notes_path, "\n".join(lines) + "\n")


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

    PROVENANCE IS ATTACHED HERE, ONCE. This is the one shared object every driver holds, so the
    references an attempt carries (`attempt_ledger.PROVENANCE_REFS`) are resolved here rather
    than threaded through four ladders: the acceptance identity comes from the task itself, the
    admission reference from whatever `bind_admission` was given, and the policy and decision
    pins from this run. Each can be overridden per call; each that resolves to nothing is simply
    not written, and reads back as unknown.
    """

    def __init__(self, ledger, run_id, task, workspace=None, actor="driver", role=None,
                 parent=None, policy_ref=None, decision_ref=None):
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
        # Run-scoped provenance. `policy_ref` and `decision_ref` are pins a caller supplies:
        # nothing in this repository mints either yet, so today they are None on every run and
        # every attempt records them as unknown. That is the honest state, not a placeholder --
        # the bundle and decision contracts that would mint them do not exist at this revision.
        self.policy_ref = policy_ref
        self.decision_ref = decision_ref
        self.admission = None
        self._al = _al()

    def bind_admission(self, admission):
        """Correlate this task's attempts with the grants that admit them -> the admission.

        The grant is minted by `BudgetAdmission.admit` immediately BEFORE the attempt exists, so
        the reference can only flow admission -> attempt. Binding is how the shared contract
        picks it up without every driver threading a reference through its own ladder. A run
        that binds nothing, or a kit that declares no budget and therefore has no admission,
        records no admission reference -- which reads as unknown, never as "unadmitted".
        """
        self.admission = admission
        return admission

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

    def attempt_started(self, op, model, prompt=None, verify_cmd=None, effort=None,
                        acceptance_ref=None, policy_ref=None, decision_ref=None,
                        admission_ref=None):
        """Record an attempt before it is dispatched -> its attempt id.

        Each `*_ref` defaults to what this run can establish and is overridable per call. The
        admission reference is read from the bound admission for THIS operation kind and is
        claimed once, so an attempt cannot inherit the grant that funded the one before it.
        """
        if acceptance_ref is None:
            acceptance_ref = acceptance_identity(self.task)
        if admission_ref is None and self.admission is not None:
            admission_ref = self.admission.ref_for(op)
        if policy_ref is None:
            policy_ref = self.policy_ref
        if decision_ref is None:
            decision_ref = self.decision_ref
        return self.ledger.record_started(
            self.run, self.task_id, op, model, prompt=prompt, verify_cmd=verify_cmd,
            artifact=self.fingerprint(), role=self.role, parent=self.parent,
            requested_model=self.task.get("model"), effort=effort, actor=self.actor,
            acceptance_ref=acceptance_ref, policy_ref=policy_ref,
            decision_ref=decision_ref, admission_ref=admission_ref,
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

    def project(self, status, result=None, outcome_line=False, note="", acceptance_ref=None):
        """Record the projection; an acceptance also binds the artifact versions (step 24).

        `artifact` is this workspace's fingerprint now (None when git cannot say), and
        `upstream` is each dependency's latest accepted artifact, read from the ledger at
        this moment -- so a later re-acceptance of a dependency with a different artifact is
        detectable as stale evidence on this task.

        `acceptance_ref` completes that pair with the criteria side: the artifact says which
        tree the verdict was reached on, the reference says which acceptance text and verify
        command it was reached against. It defaults to the task's own identity now, and a task
        that declares no acceptance records none.
        """
        artifact = self.fingerprint() if outcome_line else None
        upstream = None
        if outcome_line and status == "done":
            upstream = {dep: self.ledger.latest_artifact(dep)
                        for dep in (self.task.get("depends") or [])}
        if acceptance_ref is None:
            acceptance_ref = acceptance_identity(self.task)
        self.ledger.record_projected(self.run, self.task_id, status, result=result,
                                     outcome_line=outcome_line, note=note,
                                     artifact=artifact, upstream=upstream,
                                     acceptance_ref=acceptance_ref)

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
                         workspace=None, role=None, parent=None, policy_ref=None,
                         decision_ref=None):
    """Open the ledger, claim the task, close what a dead run left -> `(lifecycle, info)`.

    Exits 2 on a claim another live run holds, naming it: two drivers on one task is the one
    situation where refusing is always right. A stale claim (its process gone) is taken over
    and said so on stderr.

    `policy_ref` and `decision_ref` are run-scoped provenance pins `TaskRun` has accepted since
    step 16 and that no caller could reach through this function until now. The pin is taken
    ONCE, here, at the moment the run starts -- `workflow_eval.pin_for_run` over
    `workflow_eval.runtime_activation` is what produces one -- and `TaskRun` then records it on
    every attempt. That is the whole of what "a run pins its bundle" means: the value cannot
    change during the run because nothing re-reads anything to change it, so a run that started
    under one activation generation keeps it after a later generation lands. Both default to
    None, which is what every existing caller passes and what every attempt then records as
    unknown -- and None is still the only value any caller in this repository can supply, since
    nothing mints an activation pointer while the protected-activation gate refuses.
    """
    ledger = open_ledger(kit_dir, store=store)
    lifecycle = TaskRun(ledger, run_id, task, workspace=workspace, actor=actor, role=role,
                        parent=parent, policy_ref=policy_ref, decision_ref=decision_ref)
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
                         store=None, observed_model=None, result=None, proc_outcome=None,
                         duration_s=None):
    """Record a phase review or acceptance dispatch in the attempt ledger -> attempt id.

    Reviews are not tasks: nothing is claimed and nothing is projected. What was missing (step
    17) is that on Claude and Copilot a review left NOTHING behind but stdout, so a role
    dispatch never appeared in any history at all. It is recorded against the task id
    `phase-<n>` with op `review` (or `acceptance` for the orchestrator's verdict), the same
    shape as every other attempt, so the cross-harness history can join it with Codex's typed
    role-use record for the same run.

    `duration_s` (decision-improvement D05) is the same optional, absent-means-unknown
    wall-clock figure every other attempt carries -- a review or acceptance dispatch is a real
    process with real timing, and it was the one dispatch shape with no way to record it at all.
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
                           observed_model=observed_model, result=result, duration_s=duration_s)
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


# ---- evidence freshness (step 24) ---------------------------------------------------------------
#
# WHAT WAS WRONG. A task accepted against its dependencies' output stayed `done` forever, even
# after a dependency was re-run and produced something else. Readiness read only statuses, so
# the downstream verdict outlived the upstream artifact it was reached on. The ledger now
# records, at every acceptance, the artifact version accepted and the upstream versions it
# rested on; this section reads those back and names what has gone stale.

def evidence_freshness(tasks, ledger):
    """Each done task's acceptance against its upstream artifact versions -> {id: verdict}.

    A verdict is `{"state": fresh|stale|unknown, "changed": [dep, ...], "reason": str}`.
    `stale` means a dependency's latest acceptance carries a different artifact than the one
    recorded when this task was accepted. `unknown` means the comparison cannot be made: no
    upstream versions were recorded (accepted before step 24), or a fingerprint is None (a
    workspace git cannot describe). Unknown is disclosed, never rounded either way; only
    `stale` changes readiness.
    """
    out = {}
    for t in tasks:
        if t["status"] != "done":
            continue
        deps = list(t.get("depends") or [])
        if not deps:
            out[t["id"]] = {"state": "fresh", "changed": [], "reason": "no upstream task"}
            continue
        acc = ledger.latest_acceptance(t["id"])
        recorded = acc.get("upstream") if acc else None
        if not isinstance(recorded, dict):
            out[t["id"]] = {"state": "unknown", "changed": [],
                            "reason": "accepted before upstream artifact versions were recorded"}
            continue
        changed, unknown = [], []
        for dep in deps:
            rec, cur = recorded.get(dep), ledger.latest_artifact(dep)
            if rec is None or cur is None:
                unknown.append(dep)
            elif rec != cur:
                changed.append(dep)
        if changed:
            out[t["id"]] = {"state": "stale", "changed": changed,
                            "reason": f"upstream {', '.join(changed)} re-accepted with a "
                                      f"different artifact after this task was verified"}
        elif unknown:
            out[t["id"]] = {"state": "unknown", "changed": [],
                            "reason": f"no artifact version recorded for {', '.join(unknown)}"}
        else:
            out[t["id"]] = {"state": "fresh", "changed": [],
                            "reason": "every upstream artifact is the version accepted against"}
    return out


def kit_freshness(kit_dir, tasks, store=None):
    """`evidence_freshness` over the kit's own ledger (read-only; an absent ledger is empty)."""
    return evidence_freshness(tasks, open_ledger(kit_dir, store=store))


def render_freshness(freshness):
    if not freshness:
        return "evidence: no accepted task with upstream to compare"
    lines = []
    for tid, f in sorted(freshness.items()):
        lines.append(f"evidence: {tid} {f['state']} -- {f['reason']}")
    return "\n".join(lines)


def refresh_task(kit_dir, task, run_id, verify_runner, actor, store=None, workspace=None,
                 freshness=None):
    """Re-verify a done task whose evidence is stale, without dispatching -> the result.

    The task's own check is run again on the tree as it is now; a pass re-binds the upstream
    versions (the acceptance is current again), a failure projects `blocked` so the graph
    stops at it. Recorded as `evidence.refreshed` with zero attempts: nothing was spent.
    Refusing to dispatch here is deliberate -- a re-dispatch is `--rerun`, an operator's
    explicit gesture, and this operation must never spend on its own.
    """
    kit_dir = Path(kit_dir)
    tasks_path = kit_dir / "TASKS.md"
    lifecycle, _info = start_task_lifecycle(kit_dir, task, run_id, actor=actor, store=store,
                                            workspace=workspace, role="implementer")
    changed = ((freshness or {}).get(task["id"]) or {}).get("changed") or []
    project_status(tasks_path, task["id"], "in-progress")
    try:
        rc, output = verify_runner(task["verify"])
    except OSError as exc:
        rc, output = 126, f"verify failed to start: {exc}"
    lifecycle.ledger.append("evidence.refreshed", run=run_id, task=task["id"], rc=rc,
                            changed=changed)
    result = {
        "id": task["id"], "status": "done" if rc == 0 else "blocked", "model_used": None,
        "planned_model": task.get("model"), "observed_model": None, "escalations": [],
        "verify_rc": rc, "dispatch_rc": None, "usd": None,
        "failure": None if rc == 0 else "verification", "class": None, "role": "implementer",
        "verify_evidence": " ".join((output or "").split())[-2000:],
    }
    finish_task_projection(lifecycle, tasks_path, task, result)
    result["ledger_attempts"] = 0
    extra = (f"- refresh: re-verified only, nothing dispatched; upstream "
             f"{', '.join(changed) or 'task(s)'} had been re-accepted with a different artifact",)
    append_run_note(kit_dir / "NOTES.md", result, task, run_id=run_id, actor=actor, extra=extra)
    lifecycle.project(result["status"], outcome_result(result["status"], [], None),
                      outcome_line=True)
    lifecycle.end()
    return result


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
    p_graph.add_argument("--attempt-store", default=None,
                         help="ledger root for artifact bindings (default: the data root)")
    p_fresh = sub.add_parser("freshness", help="each done task's acceptance against its "
                                               "upstream artifact versions (step 24)")
    p_fresh.add_argument("--kit", required=True)
    p_fresh.add_argument("--attempt-store", default=None)
    p_fresh.add_argument("--json", action="store_true")
    p_refresh = sub.add_parser("refresh", help="re-verify a done task whose evidence is stale; "
                                                "dispatches nothing; exit 1 when the check fails")
    p_refresh.add_argument("--kit", required=True)
    p_refresh.add_argument("--task", required=True)
    p_refresh.add_argument("--attempt-store", default=None)
    p_refresh.add_argument("--exec-mode", choices=("enforced", "trusted-host"), default="enforced")
    p_refresh.add_argument("--force", action="store_true",
                           help="refresh a done task even when its evidence is not stale")
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
    if args.cmd == "freshness":
        tasks = parse_tasks(_read_tasks_text(args.kit))
        fresh = kit_freshness(args.kit, tasks, store=args.attempt_store)
        if args.json:
            print(json.dumps({"v": CONTRACT_VERSION, "freshness": fresh}, indent=2,
                             sort_keys=True))
        else:
            print(render_freshness(fresh))
        return 1 if any(f["state"] == "stale" for f in fresh.values()) else 0
    if args.cmd == "refresh":
        tasks = parse_tasks(_read_tasks_text(args.kit))
        exit_if_invalid_graph(tasks, Path(args.kit) / "TASKS.md")
        fresh = kit_freshness(args.kit, tasks, store=args.attempt_store)
        task = next((t for t in tasks if t["id"] == args.task), None)
        if task is None:
            print(f"no task with id {args.task!r} in this kit", file=sys.stderr)
            return 2
        if task["status"] != "done":
            print(f"task {args.task} is {task['status']!r}, not done; refresh re-verifies an "
                  f"acceptance and there is none to refresh", file=sys.stderr)
            return 2
        state = (fresh.get(args.task) or {}).get("state")
        if state != "stale" and not args.force:
            print(f"task {args.task}'s evidence is {state or 'fresh'}, not stale; pass --force to "
                  f"re-verify it anyway", file=sys.stderr)
            return 2
        workspace = Path.cwd()
        runner = _ep().verify_runner(workspace, mode=args.exec_mode)
        result = refresh_task(args.kit, task, generate_run_id(), runner, actor="refresh",
                              store=args.attempt_store, workspace=workspace, freshness=fresh)
        print(f"task {args.task}: {result['status']} (verify_rc={result['verify_rc']}; "
              f"nothing dispatched)")
        return 0 if result["status"] == "done" else 1
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
    graph = graph_state(tasks, freshness=kit_freshness(args.kit, tasks, store=args.attempt_store))
    if args.json:
        print(json.dumps(graph, indent=2, sort_keys=True))
    else:
        print(render_graph_state(graph))
    return 2 if graph["state"] == "invalid" else 0


if __name__ == "__main__":
    sys.exit(_cli())
