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

import bisect
import functools
import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
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
    carries: id, title, status, model, depends, independent, evidence, brief, acceptance, verify.
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
        "acceptance": _extract_acceptance(block),
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

_FENCE_OPEN_RE = re.compile(r"`{3,}|~{3,}")


def _extract_acceptance(block):
    """Text from the `**Acceptance.**` heading to the next `**Verify.**` heading (or the block's
    end), stripped; `""` when the block has no such heading.

    Acceptance was always a named task field (`TASK_FIELDS`, `to_contract`), but nothing read it,
    so `acceptance_identity` was None for every task parsed from TASKS.md and no acceptance ever
    recorded which criteria it was reached against (PLAN D7/B1, amended during kit-preflight T8).
    Records written before this carry no reference and read as unknown; nothing is backfilled.

    A marker counts only as a heading: at the start of a line (leading whitespace allowed, text
    may follow it on that line) and outside a fenced block. Every committed kit that names a
    marker anywhere else is quoting it -- in a brief, in prose, in a fence -- and an unanchored
    search started those tasks' acceptance mid-sentence. A fence opens on a line beginning with
    three or more backticks or tildes, and closes only on a line holding nothing but a run of
    the SAME character at least as long, so a ```` fence may hold a ``` line and a ~~~ fence a
    ``` one. An unclosed fence runs to the block's end, as in Markdown (a recorded design limit,
    PLAN D7). `_extract_verify` needs no such walk: it reads the first ```bash fence after its
    marker. `_extract_brief` and `_extract_verify` are unchanged.
    """
    marker, end = "**Acceptance.**", "**Verify.**"
    fence = ""       # the open fence's run (e.g. "````" or "~~~"), or "" outside a fence
    taken = None     # the acceptance's lines once its heading is found
    for line in block.splitlines():
        s = line.lstrip()
        if fence:
            if s.startswith(fence) and not s.strip(fence[0]).strip():
                fence = ""
        elif taken is None and s.startswith(marker):
            taken = [s[len(marker):]]
            continue
        elif taken is not None and s.startswith(end):
            break
        else:
            m = _FENCE_OPEN_RE.match(s)
            if m:
                fence = m.group()
        if taken is not None:
            taken.append(line)
    return "\n".join(taken).strip() if taken is not None else ""

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
    counts toward `max-escalations` (an in-ladder escalation IS an extra dispatch) EXCEPT on a
    `result=retry-pass` line, which counts none; a line carrying `parent=` counts ONE
    `max-consults` (a run dispatched with `--parent` is a consult by definition, whether it
    passed, was blocked, or was itself a budget-stop). Returns a dict with all three
    `PLAN_BUDGET_KEYS`, always present (0 when nothing is recorded yet).

    Why `retry-pass` is the one exemption. `OPERATION_CAPS` charges `max-escalations` only for
    an `escalation` operation, never for a same-model `retry`, and `retry-pass` is the one
    result word that says every extra attempt was a retry: the execute skill writes it for a
    task that passed on a same-model retry (its only escalation, the Fable consult, writes
    `escalated-pass`), and no driver writes it at all. Charging those lines made a kit whose
    tasks each needed one retry read as over its escalation cap with nothing ever escalated.
    Every other result keeps `attempts - 1`, an upper bound, because its line cannot tell the
    two apart: a driver's `pass` can still carry an escalation from an earlier run that died
    before projecting (`ledger_attempts` spans runs, `escalations` does not), and `blocked` or
    `escalated-pass` may mix retries with rungs. Over-counting there stops a run early; the
    fix never trades that for under-counting a cap.
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
        if not re.search(r"(?:^|\s)result=retry-pass(?:\s|$)", s):
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

def _last_outcome_line(notes_text, task_id):
    """The text of the LAST `outcome:` line for `task_id` that carries a `result=`, or `None`.

    Read-only. The minimal `outcome:` grammar shared with `count_plan_budget_usage` above: an optional
    `- ` bullet, the id as the first token, then `key=value` pairs. Later lines win,
    mirroring `routing_scorecard.parse_outcomes`'s last-wins rule.
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
        if re.search(r"(?:^|\s)result=\S+", s):
            found = s
    return found


def recorded_outcome_result(notes_text, task_id):
    """The LAST `result=` already recorded for `task_id` in `notes_text`, or `None`.

    Read-only over the kit's NOTES.md, through `_last_outcome_line`. Its callers are the
    budget gate (`budget_gate` below and the three original drivers' inline copies of it) and
    `accept_task`: a `budget-stop` is not a verdict, so writing one
    for a task that ALREADY carries a real verdict would append a ledger line that supersedes
    (or, once the reader's precedence rule drops it, contradicts) recorded evidence. Rejected
    at the WRITER, before anything is written -- the same precedent as the self-`--parent`
    guard in `cmd_run`, and the same reasoning as the Phase 1 review's F2 invariant: nothing
    may write a line the reader has to ignore. `accept_task` reads it to refuse any task whose
    latest line is not a pass.
    """
    line = _last_outcome_line(notes_text, task_id)
    if line is None:
        return None
    m = re.search(r"(?:^|\s)result=(\S+)", line)
    return m.group(1) if m else None


def recorded_outcome_run(notes_text, task_id):
    """The `run=` id on the line `recorded_outcome_result` reads, or `None` when it has none."""
    line = _last_outcome_line(notes_text, task_id)
    if line is None:
        return None
    m = re.search(r"(?:^|\s)run=(\S+)", line)
    return m.group(1) if m else None

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


RUN_ID_RE = re.compile(r"\d{4}-\d{2}-\d{2}-[0-9a-f]{4}")


def _valid_run_id(run_id):
    """`<UTC-date>-<4 hex>` with a real calendar date (the one date rule; nothing else)."""
    if not RUN_ID_RE.fullmatch(run_id):
        return False
    try:
        datetime.strptime(run_id[:10], "%Y-%m-%d")
    except ValueError:
        return False
    return True


_PASS_RESULTS = ("pass", "retry-pass", "escalated-pass")


def accept_task(kit_dir, task, run_id, actor="interactive", store=None, workspace=None,
                note="", now=None):
    """Record the acceptance a kit's `outcome:` line already states -> a summary dict (PLAN D6).

    A projection, not an attempt: no `begin()` (no claim is taken) and no `end()`. It writes
    only the ledger, outside the tree, through the same `TaskRun.project` the headless drivers
    use, so the artifact, upstream versions and `acceptance_ref` come from the tree and the
    ledger as they are now. Nothing is supplied by the caller and nothing is reconstructed:
    it refuses a task that is not `done`, and one whose NOTES.md carries no passing `outcome:`
    line, so there is no backfill path. NOTES.md and TASKS.md are read, never written.

    The guard (PLAN D6/B1, amended 2026-10-24 after the Phase 3 review): that line must carry
    `run=` equal to `run_id`, and `run_id`'s date must be today or yesterday in UTC, so a
    finished kit's old lines cannot be accepted even by quoting their old run id. `now` is the
    clock, an aware UTC datetime; it exists so unit tests can pin the window, and the command
    line deliberately offers no way to set it -- a settable clock in production would be a
    backfill door. Every refusal is a `ValueError` carrying the reason.
    """
    kit_dir = Path(kit_dir)
    if task["status"] != "done":
        raise ValueError(f"task {task['id']} is {task['status']}, not done; accept records an "
                         f"acceptance and there is none")
    notes_path = kit_dir / "NOTES.md"
    try:
        notes_text = notes_path.read_text() if notes_path.exists() else ""
    except UnicodeDecodeError:
        raise ValueError("NOTES.md is not UTF-8 text") from None
    result = recorded_outcome_result(notes_text, task["id"])
    if result not in _PASS_RESULTS:
        raise ValueError(f"no passing outcome: line for {task['id']} in NOTES.md; write the "
                         f"outcome line first \u2014 accept records what the ledger already states")
    line_run = recorded_outcome_run(notes_text, task["id"])
    if line_run is None:
        raise ValueError(f"the outcome: line for {task['id']} carries no run=; accept records "
                         f"only a line stamped with the run id you pass")
    if line_run != run_id:
        raise ValueError(f"the outcome: line for {task['id']} carries run={line_run}, not "
                         f"--run {run_id}; accept records only the run that wrote the line")
    today = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).date()
    run_date = datetime.strptime(run_id[:10], "%Y-%m-%d").date()
    if (today - run_date).days not in (0, 1):
        raise ValueError(f"run {run_id} is dated {run_date.isoformat()}, but today is "
                         f"{today.isoformat()} (UTC); accept records only a run from today or "
                         f"yesterday, never an older finished one")
    workspace = Path(workspace) if workspace else _al().kit_repo_root(kit_dir)
    ledger = open_ledger(kit_dir, store=store)
    # The note is user free text: redacted and bounded (bin/redact.py) before it is persisted.
    clean = _al()._rd().redact(note or "")
    lifecycle = TaskRun(ledger, run_id, task, workspace=workspace, actor=actor)
    lifecycle.project("done", result=result, outcome_line=True, note=clean["text"])
    acc = ledger.latest_acceptance(task["id"]) or {}
    return {
        "id": task["id"],
        "artifact": ledger.latest_artifact(task["id"]),
        "upstream": {dep: ledger.latest_artifact(dep) for dep in (task.get("depends") or [])},
        "acceptance_ref": acc.get("acceptance_ref"),
        "result": result,
        "note_report": {"redactions": clean["redactions"],
                        "truncated": 1 if clean["truncated"] else 0},
    }


def render_accept(summary):
    def short(v):
        return str(v)[:12] if v else "unknown"
    up = summary["upstream"]
    ups = ",".join(f"{d}:{short(v)}" for d, v in up.items()) if up else "none"
    return (f"accept: {summary['id']} result={summary['result']} "
            f"artifact={short(summary['artifact'])} upstream={ups}")


# ---- the static pre-run check: `analyze` (kit-preflight T4) -------------------------------------
#
# WHAT WAS WRONG. The brief-defect ledger's most frequent kinds -- a verify command naming a
# script no task writes, a verify block in a dialect the drivers never read, a brief anchored on
# a path that is not there -- were each found AFTER a dispatch had been paid for. Every one of
# them is visible from TASKS.md's text plus a stat of the tree, so that is all this reads.
#
# STATIC BY CONSTRUCTION, NOT BY DISCIPLINE (PLAN D2). `analyze_kit` has no runner parameter.
# Nothing in this section calls `_pr`, `_ep`, `subprocess`, or any CLI; its only contact with
# the world is `Path.exists` (a stat) and `shutil.which` (a PATH lookup). The one module it
# loads, `kit_verify_hook`, is asked to PARSE text, never to run it. `tests/test_kit_analyze.py`
# makes every spawning seam raise and calls it anyway.
#
# THE RULES ARE PLAN D3's, as amended seven times (PLAN.md lists each): before T4 (quote-aware splitting; `test`/`[`
# operands are values); during T4 after a survey of every committed kit (`[[`, `source`, `.`,
# `:` are builtins; a quoted argument, a `NAME=value` word and a `rev:path` git object are
# values; a path an earlier command of the same verify writes is created by the task); during
# T4 on the red-team's findings, "block only on what can't start" (a verify path is a finding
# only in the four positions where a missing one stops the verify from starting -- the command
# word, an interpreter's script, the `-m`/`discover` test mappings, a literal `cd` -- and every
# other path argument is resolved and reported); and after the second red-team round, "only
# sure things block", then the seventh amendment ("only unparseable blocks"): a plain run exits 3
# only on `verify-unparseable`; `verify-missing-executable`, `verify-missing-path` and
# `brief-missing-path` are printed warnings that fail only under `strict`. Where D3 is silent the code does the conservative thing -- it does not check
# the token -- and says so at the line that does it.

ANALYZE_FINDINGS = ("verify-unparseable", "verify-missing-executable", "verify-missing-path",
                    "brief-missing-path")
#: The one finding that fails a kit (D3's seventh amendment, "only unparseable blocks"): the
#: drivers cannot read the verify, or its fence is empty. `verify-missing-executable` (whose
#: refusing-vs-warned reading now only shapes its detail), `verify-missing-path` and
#: `brief-missing-path` are printed warnings that fail only under `strict`.
_FAILING_FINDINGS = ("verify-unparseable",)
_WARNING_FINDINGS = ("verify-missing-executable", "verify-missing-path", "brief-missing-path")

PATH_STATES = ("exists", "created-by", "missing")

VERIFY_UNPARSEABLE_HINT = ("uses a dialect (`Verify:` or a bare fence) that `kit_contract` "
                           "does not read")

_BRIEF_PATH_EXTS = (".py", ".md", ".json", ".toml", ".yml", ".yaml", ".txt", ".html", ".sh",
                    ".css", ".js")
_BRIEF_SKIP_PREFIXES = ("-", "$", "~", "<", "{", "http")
_BRIEF_SKIP_PARTS = ("*", "?", "[", "]", "{", "}", "(", ")", "<", ">", "::")
_LINE_SUFFIX_RE = re.compile(r":\d+$")

#: D3's third amendment, rule 5: the creation words, each with its `-s`/`-ed`/`-ing` forms and
#: the irregular `built`, `made`, `written`. The forms are generated generously (`emitted`,
#: `splitting`, `created`; also harmless non-words such as `newed`): a spare form can only add a
#: disclosed `created-by`, never a finding.
_CREATION_BASES = ("new", "create", "add", "write", "implement", "build", "make", "generate",
                   "scaffold", "author", "draft", "introduce", "produce", "save", "emit",
                   "output", "put", "extract", "move", "rename", "split")


def _creation_forms(bases):
    forms = {"built", "made", "written"}
    for w in bases:
        forms.update((w, w + "s", w + "ed", w + "ing"))
        if w.endswith("e"):
            forms.update((w + "d", w[:-1] + "ing"))
        if len(w) >= 3 and w[-1] not in "aeiouwy" and w[-2] in "aeiou" and w[-3] not in "aeiou":
            forms.update((w + w[-1] + "ed", w + w[-1] + "ing"))  # emitted, putting, splitting
    return forms


_CREATION_WORD_RE = re.compile(
    r"\b(?:" + "|".join(sorted(_creation_forms(_CREATION_BASES), key=len, reverse=True)) + r")\b",
    re.IGNORECASE)
#: The creation word must END within this many characters before the path (third amendment).
_CREATION_WINDOW = 80

#: Every bash builtin and reserved word (third amendment, rule 2; D3's own list, the second
#: amendment's `[[`/`source`/`.`/`:` among them). A first word in it is not looked up on PATH,
#: and what follows it is argument, never a blocking position.
VERIFY_BUILTINS = frozenset((
    # builtins (bash 5)
    ":", ".", "[", "alias", "bg", "bind", "break", "builtin", "caller", "cd", "command",
    "compgen", "complete", "compopt", "continue", "declare", "dirs", "disown", "echo", "enable",
    "eval", "exec", "exit", "export", "false", "fc", "fg", "getopts", "hash", "help", "history",
    "jobs", "kill", "let", "local", "logout", "mapfile", "popd", "printf", "pushd", "pwd",
    "read", "readarray", "readonly", "return", "set", "shift", "shopt", "source", "suspend",
    "test", "times", "trap", "true", "type", "typeset", "ulimit", "umask", "unalias", "unset",
    "wait",
    # reserved words
    "!", "case", "coproc", "do", "done", "elif", "else", "esac", "fi", "for", "function", "if",
    "in", "select", "then", "time", "until", "while", "{", "}", "[[", "]]",
))
#: Their operands are values being compared, not files being read (D3's amendments: `test` and
#: `[` first, `[[` second).
_TEST_COMMANDS = frozenset(("test", "[", "[["))
#: Commands every operand of which a verify WRITES (second amendment, rule 5). A later simple
#: command in the same verify reading one of those paths finds it `created-by` the task itself.
_WRITING_COMMANDS = frozenset(("tee", "touch", "mkdir"))
#: Commands whose LAST operand is written (third amendment, rule 4); their others are read.
_LAST_OPERAND_WRITERS = frozenset(("cp", "mv", "ln", "install"))
#: Interpreters whose script operand is a blocking position (third amendment, rule 1), and the
#: endings that make a bare script name checkable there.
_INTERPRETERS = frozenset(("python", "python3", "bash", "sh", "zsh", "node", "ruby", "perl"))
_SCRIPT_EXTS = (".py", ".sh", ".js", ".mjs", ".rb", ".pl")
#: Words after which bash's grammar puts the COMMAND WORD again (third amendment, rule 1): the
#: reserved words `if then else elif while until do ! {`, `time` (it introduces a pipeline) and
#: the builtin `exec` (it runs its operand as the command). `_command_targets` skips them and any
#: assignment words after them and takes the next word as the command word -- a blocking
#: position, and the `test`/`[`/`[[` exemption when it is one of those. `verify_tokens` also
#: consults them to find a `[[`/`((`/`case` that starts a command.
_PREFIX_KEYWORDS = frozenset(("!", "if", "then", "else", "elif", "while", "until", "do", "time",
                              "{", "exec"))
#: Operators, longest first, that an unquoted run of operator characters splits into.
_OPERATORS = ("&>>", "<<<", ";;&", "&&", "||", ";;", ";&", "((", "))", "()", ">>", "<<", "&>",
              ">&", "<&", ">|", "|&", "<>", ";", "|", "&", "(", ")", "<", ">")
#: The ones that end a simple command (D3: `&&`, `||`, `;`, `|`; the rest are their `case` and
#: `|&` spellings). A lone `&` is not in D3's list: the word after it is read as an argument.
_SEPARATORS = frozenset(("&&", "||", ";", "|", "|&", ";;", ";&", ";;&"))

_SHELL_OPS = "();<>|&"
#: An operator character inside quotes, or escaped, is a word character to the shell. shlex's
#: token list cannot say which a lone `;` was, so those are swapped for private-use stand-ins
#: before tokenizing and swapped back after.
_OP_STANDIN = {c: chr(0xE000 + i) for i, c in enumerate(_SHELL_OPS)}
_OP_RESTORE = str.maketrans({v: k for k, v in _OP_STANDIN.items()})
_STANDIN_TABLE = str.maketrans(_OP_STANDIN)
#: Runs the sanitizer copies whole: inside double quotes, nothing that ends or escapes the quote
#: or substitutes; unquoted, nothing that quotes, escapes, substitutes, redirects, separates or
#: ends a line. Taking them whole keeps analysis linear in the verify's size (fourth amendment).
_DQUOTED_RUN_RE = re.compile(r'[^"\\$`]+')
_UNQUOTED_RUN_RE = re.compile(r"[^ \t\r\n\\'\"`$<>()|&;]+")
_BLANK_RUN_RE = re.compile(r"[ \t\r]+")
#: Fourth amendment (3): digits right before a redirect operator are a file-descriptor number.
_FD_NUMBER_RE = re.compile(r"[0-9]+(?=[<>])")
#: Sixth amendment (4): `{name}` right before a redirect operator names an fd to allocate.
_FD_NAME_RE = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}(?=[<>])")
#: Fourth amendment (3): `NAME=(...)` / `NAME+=(...)` is an array assignment.
_ARRAY_ASSIGN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\+?=\(")
#: D3's fifth amendment: the features that make a verify non-simple, matched on words.
_CASE_WORD_RE = re.compile(r"\bcase\b")
_INSTALL_WORD_RE = re.compile(r"\binstall\b")
_PATH_ASSIGN_RE = re.compile(r"PATH\+?=")
_PROBE_FLAG_RE = re.compile(r"-[A-Za-z]*[vV]")  # `command -v`, `-V`, `-pv`: a tool probe
_PROBE_IN_TEXT_RE = re.compile(r"\bcommand\s+(?:-[A-Za-z]+\s+)*-[A-Za-z]*[vV]\b|\b(?:type|hash|which)\b")
_PACKAGE_MANAGERS = frozenset(("npm", "pnpm", "yarn", "bun", "pip", "pip3", "uv", "cargo", "gem",
                               "brew", "go"))
#: Planted inside every quoted or backslash-escaped stretch before tokenizing, so a token can
#: still say afterwards that it was written with quotes (D3's second amendment, rule 2) once
#: shlex has removed them. A backslash counts as quoting: POSIX lists it as one of the three.
_QUOTED_MARK = chr(0xE010)
#: What a dropped `$(...)`, backtick or `<(...)` substitution leaves behind. It reads as a `$`
#: token, which every rule below already skips, so `"$(git rev-parse --show-toplevel)/bin/x"`
#: is not misread as the absolute path `/bin/x`.
_SUBSTITUTED = "$_"
#: Glob characters, plus brace expansion (D3 silent; a `{a,b}` token names no single file).
_GLOB_CHARS = "*?[]{}"
_ARG_SKIP_PREFIXES = ("-", "$", "~", "http")
_DOTTED_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+$")
_PYTHON_RE = re.compile(r"^(?:python|pypy)[0-9.]*$")


_WORD_CHARS_RE = re.compile(r"\w*")       # matched with fullmatch: one pass, no backtracking
_WORD_OR_DASH_RE = re.compile(r"[\w-]+")
_SHOPT_RE = re.compile(r"\bshopt(?=\s)")
_TOKEN_RE = re.compile(r"\S+")


def _is_dynamic_name_assignment(word):
    """Exactly `re.match(r"[^=/\\s]*\\$[^=/\\s]*\\+?=", word)`, in one pass: an assignment whose
    name holds a `$` (`export $VAR=bin`), the name -- everything before the first `=` -- having
    no `/` and no whitespace. The regex form backtracked quadratically on one long word full of
    `$` and no `=` (the last red-team pass's `${${${...` hang), so it is computed instead."""
    eq = word.find("=")
    if eq <= 0:
        return False
    name = word[:eq]
    return "$" in name and "/" not in name and not any(c.isspace() for c in name)


def _extglob_on(text):
    """Exactly `re.search(r"\\bshopt\\s+(?:-\\w+\\s+)*-\\w*s\\w*\\s+(?:[\\w-]+\\s+)*extglob\\b", text)`,
    computed over whitespace-separated tokens in linear time (the regex's ambiguous `\\w*s\\w*`
    is quadratic on a long `-sss...` word). After a `shopt` that ends a word: a run of `-\\w+`
    flags of which one holds an `s`, then `[\\w-]+` words, then a token starting `extglob` and
    not followed by a word character."""
    toks = [(m.start(), m.group()) for m in _TOKEN_RE.finditer(text)]
    if not toks:
        return False
    starts = [t[0] for t in toks]
    n = len(toks)
    # reach[k]: from token k on, `[\w-]+` tokens lead to one starting `extglob` + boundary.
    reach = [False] * (n + 1)
    for k in range(n - 1, -1, -1):
        tok = toks[k][1]
        ext = tok.startswith("extglob") and (len(tok) == 7 or not _WORD_CHARS_RE.fullmatch(tok[7]))
        reach[k] = ext or (bool(_WORD_OR_DASH_RE.fullmatch(tok)) and reach[k + 1])
    for m in _SHOPT_RE.finditer(text):
        k = bisect.bisect_left(starts, m.end())  # the first token after the whitespace
        flag_seen = False
        while k < n:
            tok = toks[k][1]
            if not (len(tok) >= 2 and tok[0] == "-" and _WORD_CHARS_RE.fullmatch(tok[1:])):
                break
            flag_seen = flag_seen or "s" in tok[1:]
            if flag_seen and reach[k + 1]:
                return True
            k += 1
    return False


def _strip_line_suffix(path):
    """Exactly the old loop -- strip trailing `.,:;` and a `:<digits>` line suffix, again until
    nothing changes -- with an end index instead of a new string per round, so a span with many
    `:12` suffixes is linear, not quadratic. (A path with a newline, which a brief path never
    has, keeps the regex loop: there `re`'s `$` also matches before a final newline.)"""
    if "\n" in path:
        while True:
            stripped = _LINE_SUFFIX_RE.sub("", path.rstrip(".,:;"))
            if stripped == path:
                return path
            path = stripped
    end = len(path)
    while True:
        e = end
        while e > 0 and path[e - 1] in ".,:;":
            e -= 1
        d = e
        while d > 0 and path[d - 1].isdecimal():
            d -= 1
        if d < e and d > 0 and path[d - 1] == ":":
            e = d - 1
        if e == end:
            return path[:end]
        end = e


class _Op(str):
    """An unquoted shell operator token (`>`, `2>&`, `<<`, `&`) -- never a word."""


class _Quoted(str):
    """A word written with quotes (or a backslash) somewhere in the verify source. As an
    argument it is a value, never path-checked; the first word and the `-m`/`-p` mappings
    still read it (D3's second amendment, rule 2)."""


_KIT_VERIFY_HOOK = None


def _kvh():
    """Lazy-load bin/kit_verify_hook.py for its PARSER only (`_task_verify_cmd`). Cached."""
    global _KIT_VERIFY_HOOK
    if _KIT_VERIFY_HOOK is None:
        import importlib.util
        path = Path(__file__).resolve().parent / "kit_verify_hook.py"
        spec = importlib.util.spec_from_file_location("kit_verify_hook", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _KIT_VERIFY_HOOK = mod
    return _KIT_VERIFY_HOOK


def _task_blocks(text):
    """TASKS.md text -> `{id: block_text}`, split heading to heading exactly as `parse_tasks`
    splits it (a `### ` heading without the spaced em dash bounds a block but is not one). The
    first block wins on a duplicate id; a duplicate is an invalid graph, refused before this."""
    lines = text.splitlines()
    heading_idxs = [i for i, ln in enumerate(lines) if ln.startswith("### ")]
    blocks = {}
    for pos, start in enumerate(heading_idxs):
        heading = lines[start][len("### "):].strip()
        if EM_DASH not in heading:
            continue
        end = heading_idxs[pos + 1] if pos + 1 < len(heading_idxs) else len(lines)
        blocks.setdefault(heading.split()[0], "\n".join(lines[start:end]))
    return blocks


def _code_spans(text):
    """Every single-backticked span in `text`, in order. A run of N backticks closes only at the
    next run of exactly N (CommonMark), so a ``double`` span and a fenced block are skipped
    whole and the single backticks inside them are never paired with each other. The runs are
    found once and each opener looks up the next run of its own length by bisection, so a text
    full of unmatched backticks is not quadratic."""
    runs = [(m.start(), m.end() - m.start()) for m in _BACKTICK_RUN_RE.finditer(text)]
    by_len = {}
    for idx, (_start, length) in enumerate(runs):
        by_len.setdefault(length, []).append(idx)
    spans, r = [], 0
    while r < len(runs):
        start, length = runs[r]
        same = by_len[length]
        pos = bisect.bisect_right(same, r)
        if pos == len(same):
            r += 1  # an unmatched opener is literal backticks
            continue
        close = same[pos]
        if length == 1:
            spans.append(text[start + 1:runs[close][0]])
        r = close + 1
    return spans


def brief_paths(task_block_text):
    """The repo paths a task block names in single backticks before `**Verify.**` (PLAN D3).

    A span qualifies when it has no whitespace and contains `/` or ends with one of the listed
    extensions; it is skipped when it starts with `-`, `$`, `~`, `<`, `{`, `http` or contains
    any of `* ? [ ] { } ( ) < > ::`; then trailing `.,:;` and a `:<digits>` line suffix are
    stripped (`bin/x.py:42` -> `bin/x.py`). Ordered, deduplicated. With no `**Verify.**` marker
    (the other dialect) the whole block is read; its fenced verify is skipped as a fence.
    """
    text = task_block_text or ""
    cut = text.find("**Verify.**")
    if cut != -1:
        text = text[:cut]
    out, seen = [], set()
    for span in _code_spans(text):
        if not span or any(ch.isspace() for ch in span):
            continue
        if "/" not in span and not span.endswith(_BRIEF_PATH_EXTS):
            continue
        if span.startswith(_BRIEF_SKIP_PREFIXES) or any(p in span for p in _BRIEF_SKIP_PARTS):
            continue
        path = _strip_line_suffix(span)
        if path and path not in seen:
            seen.add(path)
            out.append(path)
    return out


_BACKTICK_RUN_RE = re.compile(r"`+")


@functools.lru_cache(maxsize=256)
def _creation_word_ends(text):
    """The sorted end offsets of every creation word in `text`: computed once per text, so
    classifying many paths against one brief is not quadratic."""
    return tuple(m.end() for m in _CREATION_WORD_RE.finditer(text))


def _claims_creation(path, text):
    """Whether `text` names `path` with a creation word (`_CREATION_WORD_RE`: whole word, any
    case) ending within the 80 characters before it (PLAN D3, third amendment rule 5). The
    caller passes only the block before `**Verify.**`: a verify's own words never claim.

    "The same path" means the same path: an occurrence inside a longer one (`old/bin/x.py`,
    `bin/x.py.bak`) does not count, though sentence punctuation after it does."""
    if not path or not text:
        return False
    ends = _creation_word_ends(text)
    if not ends:
        return False
    needles = [path] + ([path[2:]] if path.startswith("./") and len(path) > 2 else [])
    for needle in needles:
        start = text.find(needle)
        while start != -1:
            end = start + len(needle)
            before = text[start - 1] if start else ""
            if before == "/" and text[start - 2:start] == "./":
                # `./spike/run.py` in the brief is the same path as `spike/run.py` in the verify
                before = text[start - 3] if start >= 3 else ""
            after = text[end] if end < len(text) else ""
            after2 = text[end + 1] if end + 1 < len(text) else ""
            # The start and the end of the text are boundaries: `"" in "_-/"` is True in
            # Python, so an empty neighbour is tested explicitly, not by membership.
            bounded = (not (before and (before.isalnum() or before in "_-./~$"))
                       and not (after and (after.isalnum() or after in "_-/"))
                       and not (after == "." and (after2.isalnum() or after2 == "_")))
            if bounded:
                k = bisect.bisect_left(ends, start - _CREATION_WINDOW)
                if k < len(ends) and ends[k] <= start:
                    return True
            start = text.find(needle, start + 1)
    return False


def _is_path_char(c):
    """A character `_claims_creation` treats as part of a path, before or after it."""
    return c.isalnum() or c in "_-./~$"


#: Runs longer than this enumerate only themselves as claimable candidates: a path that long
#: is not a real path, and enumerating its internal end points would make a pathological
#: brief quadratic. A missed claim there only leaves a path `missing` -- a warning.
_CLAIM_RUN_CAP = 4096


def _claim_candidates(text):
    """Every path string `_claims_creation` would say `text` claims to create -> a set.

    Equivalent by construction for paths made only of path characters: an occurrence passes
    `_claims_creation`'s boundary test exactly when it starts where a maximal run of path
    characters starts (or two in, after a leading `./`) and ends at the run's end or before an
    internal `~`, `$`, or a `.` that is not followed by a letter, digit or `_`; and it claims
    when a creation word ends within the window before that start. Computed once per text."""
    ends = _creation_word_ends(text)
    out = set()
    if not ends:
        return out
    n, i = len(text), 0
    while i < n:
        if not _is_path_char(text[i]):
            i += 1
            continue
        j = i
        while j < n and _is_path_char(text[j]):
            j += 1
        starts = [i] + ([i + 2] if text.startswith("./", i) and j - i > 2 else [])
        for s in starts:
            k = bisect.bisect_left(ends, s - _CREATION_WINDOW)
            if not (k < len(ends) and ends[k] <= s):
                continue
            out.add(text[s:j])
            if j - s > _CLAIM_RUN_CAP:
                continue
            for e in range(s + 1, j):
                c = text[e]
                if c in "~$" or (c == "." and not (e + 1 < n and (text[e + 1].isalnum()
                                                                  or text[e + 1] == "_"))):
                    out.add(text[s:e])
        i = j
    return out


class _Creators:
    """The created-by question answered by index, for `analyze_kit` (D3, seventh amendment's
    linear-chain fix). `classify_path` given a `{id: text}` dict scans every eligible creator
    per path, and a long `depends:` chain made that roughly cubic. This builds, once per kit,
    a map from every path a task's claim text claims to the tasks claiming it (file order), and
    each task's upstream set as an integer bitset; `claimant` then reads both. Same answer as
    the scan: the first claiming task upstream in file order, else the task itself. A path with
    a character outside `_is_path_char` (a quoted `my dir/x`) falls back to the scan."""

    def __init__(self, order, claim_of, depends_of):
        self.order = list(dict.fromkeys(order))
        self.index_of = {tid: k for k, tid in enumerate(self.order)}
        self.claim_of = claim_of
        self.claims = {}
        for tid in self.order:
            for cand in _claim_candidates(claim_of.get(tid, "")):
                self.claims.setdefault(cand, []).append(tid)
        self.up = self._upstream_bits(depends_of)

    def _upstream_bits(self, depends_of):
        """Each task's transitive upstream as a bitset over `self.order`. One post-order pass
        when the graph is acyclic (every valid kit); a cycle -- an invalid graph, which the CLI
        refuses before analysing but a direct caller may still pass -- falls back to an exact
        closure per task, so the answer always matches the plain transitive closure."""
        bits, state, cyclic = {}, {}, False
        for root in self.order:
            if root in state:
                continue
            stack = [root]
            while stack:
                t = stack[-1]
                if t not in state:
                    state[t] = 0  # visiting
                    for d in depends_of.get(t, ()):
                        if d not in self.index_of or d == t:
                            continue
                        if d not in state:
                            stack.append(d)
                        elif state[d] == 0:
                            cyclic = True
                    continue
                stack.pop()
                if state[t] == 1:
                    continue
                b = 0
                for d in depends_of.get(t, ()):
                    if d in self.index_of and d != t:
                        b |= (1 << self.index_of[d]) | bits.get(d, 0)
                bits[t] = b
                state[t] = 1
        if not cyclic:
            return bits
        for t in self.order:  # exact, quadratic only on an invalid (cyclic) graph
            seen, stack = set(), list(depends_of.get(t, ()))
            while stack:
                d = stack.pop()
                if d in seen or d == t or d not in self.index_of:
                    continue
                seen.add(d)
                stack.extend(depends_of.get(d, ()))
            bits[t] = sum(1 << self.index_of[d] for d in seen)
        return bits

    def is_upstream(self, task_id, other):
        k = self.index_of.get(other)
        return k is not None and other != task_id and bool((self.up.get(task_id, 0) >> k) & 1)

    def claimant(self, path, task_id):
        if not path:
            return None
        if not all(_is_path_char(c) for c in path):
            for u in self.order:  # rare: fall back to the scan, over the same eligible set
                if self.is_upstream(task_id, u) and _claims_creation(path, self.claim_of[u]):
                    return u
            mine = self.claim_of.get(task_id)
            return task_id if mine is not None and _claims_creation(path, mine) else None
        names = list(self.claims.get(path, ()))
        if path.startswith("./") and len(path) > 2:
            names += self.claims.get(path[2:], ())
        best = None
        for u in names:
            if self.is_upstream(task_id, u) and (best is None
                                                 or self.index_of[u] < self.index_of[best]):
                best = u
        if best is not None:
            return best
        return task_id if task_id in names else None


def classify_path(path, repo_root, task_id, creators):
    """`path` -> `{"path", "state", "by"}` with state `exists | created-by | missing`.

    `exists` when the path, absolute or relative to `repo_root`, exists now. Otherwise
    `created-by` when a task in `creators` (`{id: block_text}`, the caller's eligible set: the
    tasks upstream of `task_id`, transitively, and `task_id` itself) names it after a creation
    word -- upstream tasks first, in their given order, then `task_id`, because the earliest
    writer is the one that creates it. Otherwise `missing`. A stat and a text search: nothing
    is opened or run.
    """
    p = Path(path)
    full = p if p.is_absolute() else Path(repo_root) / p
    try:
        exists = full.exists()
    except (OSError, ValueError):
        exists = False
    if exists:
        return {"path": path, "state": "exists", "by": None}
    if isinstance(creators, _Creators):
        by = creators.claimant(path, task_id)  # the same answer, by index (linear, amendment 7)
        if by is not None:
            return {"path": path, "state": "created-by", "by": by}
        return {"path": path, "state": "missing", "by": None}
    creators = creators or {}
    order = [tid for tid in creators if tid != task_id]
    if task_id in creators:
        order.append(task_id)
    for tid in order:
        if _claims_creation(path, creators[tid]):
            return {"path": path, "state": "created-by", "by": tid}
    return {"path": path, "state": "missing", "by": None}


def _skip_substitution(text, i):
    """`text[i]` opens `$(`, `<(`, `>(` or a backtick -> the index just past its close.

    Nested parentheses, quotes and backslashes inside are honored; an unclosed one runs to the
    end (everything after it is then unread, the conservative outcome)."""
    n = len(text)
    if text[i] == "`":
        j = i + 1
        while j < n:
            if text[j] == "\\":
                j += 2
                continue
            if text[j] == "`":
                return j + 1
            j += 1
        return n
    j, depth = i + 2, 1
    while j < n:
        c = text[j]
        if c == "\\":
            j += 2
            continue
        if c == "'":
            k = text.find("'", j + 1)
            j = n if k == -1 else k + 1
            continue
        if c == '"':
            j += 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            j += 1
            continue
        if c == "`":
            j = _skip_substitution(text, j)
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return n


def _heredoc_tag(text, i):
    """`text[i:]` starts with `<<` (not `<<<`) -> `(tag, strip_tabs, end, quoted)` or None.

    The delimiter is read as bash reads it: one word up to a blank or an operator, its quotes
    and backslashes removed (`E"O"F` is `EOF`), and `quoted` when any part was quoted -- which
    decides whether a backslash-newline in the body joins lines (sixth-round conformance)."""
    n = len(text)
    j = i + 2
    dash = text.startswith("-", j)
    if dash:
        j += 1
    while j < n and text[j] in " \t":
        j += 1
    parts, quoted, start = [], False, j
    while j < n and text[j] not in " \t\r\n;&|<>()":
        c = text[j]
        if c == "'":
            k = text.find("'", j + 1)
            if k == -1:
                return None
            parts.append(text[j + 1:k])
            quoted, j = True, k + 1
        elif c == '"':
            k = j + 1
            while k < n and text[k] != '"':
                k += 2 if text[k] == "\\" else 1
            if k >= n:
                return None
            parts.append(re.sub(r'\\([$`"\\\n])', r"\1", text[j + 1:k]))
            quoted, j = True, k + 1
        elif c == "\\" and j + 1 < n:
            parts.append(text[j + 1])
            quoted, j = True, j + 2
        else:
            parts.append(c)
            j += 1
    if j == start:
        return None
    return "".join(parts), dash, j, quoted


def _skip_heredoc_body(text, i, tag, strip_tabs, quoted=False):
    """Index just past the heredoc body starting at `i`: through the line that is exactly
    `tag` (leading tabs removed for `<<-`), or to the end when it never comes. With an
    unquoted delimiter a backslash-newline joins two body lines first, as in bash, so the line
    after `line \\` is never the terminator."""
    n = len(text)
    while i < n:
        logical = ""
        while True:
            j = text.find("\n", i)
            line = text[i:n if j == -1 else j].rstrip("\r")
            if strip_tabs:
                line = line.lstrip("\t")
            i = n if j == -1 else j + 1
            trailing = len(line) - len(line.rstrip("\\"))
            if not quoted and trailing % 2 == 1 and i < n:
                logical += line[:-1]  # an unquoted body: backslash-newline continues the line
                continue
            logical += line
            break
        if logical == tag:
            break
    return i


def _substitution_features(body, features):
    """D3's fifth amendment: what a skipped command substitution's text makes non-simple -- it
    spans lines, or holds a heredoc (`<<`) or a `case` -- plus, read generously where the
    amendment is silent (the body is not lexed, so this is the ambiguous, non-blocking reading),
    an `install` word inside it."""
    if features is None:
        return
    if "\n" in body or "<<" in body or _CASE_WORD_RE.search(body):
        features.add("a command substitution spanning lines or holding `<<` or `case`")
    if _INSTALL_WORD_RE.search(body):
        features.add("an install step")
    if _PROBE_IN_TEXT_RE.search(body):
        # Sixth amendment (6): a tool probe inside a substitution (`x="$(command -v t)"`) is a
        # probe; read on the unlexed body, as generously as `install` above.
        features.add("a tool probe")


def _shell_lines(text, features=None):
    """Verify text -> its logical command lines, with what must not be tokenized removed.

    PLAN D3's first steps, done in one quote-aware pass so a quote decides everything at once:
    heredoc bodies are dropped (the `<<TAG` line itself stays and is read); `$(...)`, backtick
    and `<(...)` substitutions become `$_`; operator characters inside quotes or after a
    backslash become stand-ins; a backslash-newline joins two lines (D3 silent -- one command);
    a `#` that begins a word starts a comment (bash's rule, D3 silent); and an unquoted newline
    ends a line, so a quoted string spanning lines stays one command (D3 splits on newlines;
    the amendment's point is that a separator inside quotes is not one).

    `features`, when given, collects the fifth amendment's non-simple features this pass alone
    can see: a `${` outside single quotes, and a command substitution's own text.
    """
    lines, cur, pending = [], [], []
    # A NUL byte is dropped: bash discards NUL bytes from its input, and no argv can carry one,
    # so a word with one in it is not a sure missing command (D3 silent; the conservative read).
    text = text.replace("\x00", "")
    # Seventh amendment (4): once the verify runs `shopt -s extglob`, `@(...)`, `+(...)`,
    # `?(...)`, `*(...)` and `!(...)` are one word each. Turned on for the whole verify when the
    # `shopt` appears anywhere in it (bash needs it a line earlier; reading it everywhere is
    # the generous side, and an extglob word never refuses).
    extglob = _extglob_on(text)
    state, i, n = None, 0, len(text)
    while i < n:
        c = text[i]
        if state == "'":
            j = text.find("'", i)  # the whole quoted stretch at once (linear time)
            end = n if j == -1 else j
            if end > i:
                cur.append(text[i:end].translate(_STANDIN_TABLE))
            if j == -1:
                i = n
                continue
            cur.append("'")
            state = None
            i = j + 1
            continue
        if state == '"':
            m = _DQUOTED_RUN_RE.match(text, i)
            if m:
                cur.append(m.group().translate(_STANDIN_TABLE))
                i = m.end()
                continue
            if c == "\\" and i + 1 < n:
                nxt = text[i + 1]
                if nxt == "\n":
                    i += 2
                    continue
                if nxt in '"\\$`':
                    cur.append(c + nxt)
                    i += 2
                    continue
            if c == '"':
                state = None
                cur.append(c)
                i += 1
                continue
            if c == "`" or text.startswith("$(", i):
                end = _skip_substitution(text, i)
                _substitution_features(text[i:end], features)
                i = end
                cur.append(_SUBSTITUTED)
                continue
            if features is not None and text.startswith("${", i):
                # Fifth amendment: `${`. Counted inside double quotes too, where the amendment
                # says "unquoted": a `${...}` there may nest quotes this reader does not model,
                # so it is ambiguous, and the non-blocking reading is taken.
                features.add("`${`")
            cur.append(_OP_STANDIN.get(c, c))
            i += 1
            continue
        # unquoted
        if c == "\\":
            if i + 1 >= n:
                i += 1  # a trailing lone backslash escapes nothing
                continue
            nxt = text[i + 1]
            if nxt != "\n":
                cur.append(_QUOTED_MARK + (_OP_STANDIN[nxt] if nxt in _OP_STANDIN else c + nxt))
            i += 2
            continue
        if c in "'\"":
            state = c
            cur.append(c + _QUOTED_MARK)
            i += 1
            continue
        if c in " \t\r":
            m = _BLANK_RUN_RE.match(text, i)  # blanks taken whole (linear time)
            cur.append(m.group())
            i = m.end()
            continue
        prev = cur[-1][-1:] if cur else ""
        word_start = prev == "" or prev in " \t\r" or prev in _SHELL_OPS
        if c == "#" and word_start:
            j = text.find("\n", i)
            i = n if j == -1 else j
            continue
        if word_start and c.isdigit():
            m = _FD_NUMBER_RE.match(text, i)
            if m:
                i = m.end()  # fourth amendment (3): `2>&1`, `3<file` -- an fd number, not a word
                continue
        if word_start and c == "{":
            m = _FD_NAME_RE.match(text, i)
            if m:
                i = m.end()  # sixth amendment (4): `exec {fd}>file`, `{fd}<x`: a redirection
                continue
        if word_start and (c.isalpha() or c == "_"):
            m = _ARRAY_ASSIGN_RE.match(text, i)
            if m:
                # Fourth amendment (3): `NAME=(a b c)` is an array assignment; its elements are
                # values, never command words. It reads as the assignment `NAME=$_`.
                eq = m.end() - 2
                cur.append(text[i:eq + 1] + _SUBSTITUTED)
                i = _skip_substitution(text, eq)
                continue
        if c == "`" or (c in "$<>" and text.startswith("(", i + 1)):
            end = _skip_substitution(text, i)
            _substitution_features(text[i:end], features)  # `<(...)` read the same way (silent)
            i = end
            cur.append(_SUBSTITUTED)
            continue
        if features is not None and text.startswith("${", i):
            features.add("`${`")  # fifth amendment: an unquoted `${`
        if text.startswith("<<<", i):
            cur.append("<<<")
            i += 3
            continue
        if text.startswith("<<", i):
            found = _heredoc_tag(text, i)
            if found:
                tag, strip_tabs, end, quoted = found
                pending.append((tag, strip_tabs, quoted))
                cur.append(text[i:end])
                i = end
                continue
        if c == "\n":
            lines.append("".join(cur))
            cur = []
            i += 1
            for tag, strip_tabs, quoted in pending:
                i = _skip_heredoc_body(text, i, tag, strip_tabs, quoted)
            pending = []
            continue
        if extglob and c == "(" and i > 0 and text[i - 1] in "@+?*!":
            end = _skip_substitution(text, i - 1)  # the `(` at i, matched with nesting
            cur.append(text[i:end].translate(_STANDIN_TABLE))  # `|` inside is not a pipe
            i = end
            continue
        m = _UNQUOTED_RUN_RE.match(text, i)
        if m:  # a run with nothing special in it, taken whole (linear time, fourth amendment)
            cur.append(m.group())
            i = m.end()
            continue
        cur.append(c)
        i += 1
    lines.append("".join(cur))
    return [ln for ln in lines if ln.strip()]


def _split_operators(run):
    """An unquoted run of operator characters -> its operators, longest match first."""
    out, i = [], 0
    while i < len(run):
        for op in _OPERATORS:
            if run.startswith(op, i):
                out.append(op)
                i += len(op)
                break
        else:  # pragma: no cover - every operator character is itself in _OPERATORS
            out.append(run[i])
            i += 1
    return out


_LEX_SPACE_RE = re.compile(r"[ \t\r\n]+")
_LEX_OPS_RE = re.compile(r"[();<>|&]+")
_LEX_PLAIN_RE = re.compile(r"[^ \t\r\n();<>|&'\"\\]+")
_LEX_DQ_STOP_RE = re.compile(r'["\\]')


def _lex(line):
    """One logical line -> `(tokens, fallback)`: D3's reading, `shlex.shlex(line, posix=True,
    punctuation_chars=True)` with `whitespace_split=True` (and `commenters=""`: comments were
    removed in `_shell_lines` by bash's word-start rule), with `ValueError` falling back to a
    whitespace split.

    Implemented here rather than by calling shlex, because shlex grows each token one character
    at a time (`self.token = self.token + nextchar`), which is quadratic in a token's length: a
    3 MB verify word took minutes, and the fourth amendment requires linear time. The reading is
    shlex's exactly -- runs of `();<>|&` are one token, whitespace is ` \\t\\r\\n`, single quotes
    are literal, a backslash in double quotes escapes only `"` and itself, an unquoted backslash
    escapes any character, an unclosed quote or a trailing backslash raises -- and
    `tests/test_kit_analyze.py` checks it against shlex token for token."""
    tokens, buf, in_word = [], [], False
    i, n = 0, len(line)
    try:
        while i < n:
            c = line[i]
            if c in " \t\r\n":
                if in_word:
                    tokens.append("".join(buf))
                    buf, in_word = [], False
                i = _LEX_SPACE_RE.match(line, i).end()
            elif c in _SHELL_OPS:
                if in_word:
                    tokens.append("".join(buf))
                    buf, in_word = [], False
                m = _LEX_OPS_RE.match(line, i)
                tokens.append(m.group())
                i = m.end()
            elif c == "'":
                j = line.find("'", i + 1)
                if j == -1:
                    raise ValueError("No closing quotation")
                buf.append(line[i + 1:j])
                in_word, i = True, j + 1
            elif c == '"':
                j, parts = i + 1, []
                while True:
                    m = _LEX_DQ_STOP_RE.search(line, j)
                    if m is None:
                        raise ValueError("No closing quotation")
                    k = m.start()
                    parts.append(line[j:k])
                    if line[k] == '"':
                        break
                    if k + 1 >= n:
                        raise ValueError("No closing quotation")
                    nxt = line[k + 1]
                    parts.append(nxt if nxt in '"\\' else "\\" + nxt)
                    j = k + 2
                buf.append("".join(parts))
                in_word, i = True, k + 1
            elif c == "\\":
                if i + 1 >= n:
                    raise ValueError("No escaped character")
                buf.append(line[i + 1])
                in_word, i = True, i + 2
            else:
                m = _LEX_PLAIN_RE.match(line, i)
                buf.append(m.group())
                in_word, i = True, m.end()
        if in_word:
            tokens.append("".join(buf))
        return tokens, False
    except ValueError:
        return line.split(), True


def verify_tokens(verify_text, features=None, seps=None):
    """Verify text -> its simple commands, each a list of tokens (PLAN D3).

    Tokenized per line with `shlex.shlex(line, posix=True, punctuation_chars=True)` and
    `whitespace_split=True`, so `&&`, `||`, `;` and `|` split commands only where they stand
    outside quotes. Words are `str`, or `_Quoted` (a `str` subclass) when any part was written
    with quotes or a backslash; other unquoted operators are `_Op` (`>`, `<<`, `&`, a subshell's
    `(`/`)`, a function's `()`, an arithmetic `((`). Third amendment, rules 2 and 3: inside
    `[[ ... ]]`, `&&`/`||`/`<`/`>` are test operators and stay in the command as plain words;
    a `((...))` command keeps only its `((` marker; and every line from one whose command word is
    `case` through the line holding `esac` is dropped. On `ValueError` (an unterminated quote)
    the line falls back to a whitespace split, and a fallback token still carrying a quote
    character is read as `$_` (unreadable, so unchecked).

    `features`, when given, collects D3's fifth-amendment features seen in the lexed text: a
    function definition (`function`, or a word followed by `(` `)`, spaced or not), the reserved
    word `case`, a `PATH` assignment, and the word `install` -- plus, through `_shell_lines`, a
    `${` and a non-simple command substitution. Quoted text and heredoc bodies are never
    lexed as words here, so a `case` in them is not the feature.

    `seps`, when given, receives one entry per returned command: the separator that ended it
    (`&&`, `||`, `|`, `|&`, `;`, `;;`, a newline, or "" at the end) -- what the sixth
    amendment's `||` rule reads. Inside `[[ ... ]]` and `(( ... ))` a newline is not a
    separator: those keep their mode across lines (sixth amendment, (4)).
    """
    commands, in_case = [], False
    cmd, mode = [], None  # mode: None | "test" (in [[ ]]) | "arith" (in (( ))), across lines
    # Whether the next token is in command-word position: nothing yet but `(`, reserved
    # prefixes (`if`, `!`, `{`, ...) and assignments. Kept incrementally, so a long run of
    # words costs linear time (fourth amendment).
    at_cmd = True
    out_seps = []
    for line in _shell_lines(verify_text or "", features):
        raw, fallback = _lex(line)
        line_cmds = []  # (command, the separator that ended it)
        saw_case = saw_esac = False
        for tok in raw:
            if tok and all(ch in _SHELL_OPS for ch in tok):
                for op in _split_operators(tok):
                    if mode == "arith":
                        if op == "))":
                            mode = None
                        continue
                    if mode == "test":
                        cmd.append(op)  # a test operator inside [[ ]], not a separator (rule 3)
                        continue
                    if op == "((" and (at_cmd or cmd[-1:] == ["for"]):
                        mode = "arith"
                        cmd.append(_Op("(("))
                        at_cmd = False
                    elif op in _SEPARATORS:
                        if cmd:
                            line_cmds.append((cmd, op))
                        cmd, at_cmd = [], True
                    elif op in ("((", "))"):
                        cmd.extend((_Op(op[0]), _Op(op[0])))  # two subshell parens, not arithmetic
                        at_cmd = at_cmd and op == "(("
                    else:
                        defines = ((op == "()" and cmd and _is_word(cmd[-1]))
                                   or (op == ")" and len(cmd) >= 2 and isinstance(cmd[-1], _Op)
                                       and cmd[-1] == "(" and _is_word(cmd[-2])))
                        if defines and features is not None:
                            features.add("a function definition")  # `f()`, `f ()`, `f ( )`
                        cmd.append(_Op(op))
                        # After a function's `()` its body starts: command position again, so
                        # `f() { case ...` sees its `case` (and drops the case line).
                        at_cmd = defines or (at_cmd and op == "(")
                continue
            if mode == "arith":
                continue
            quoted = _QUOTED_MARK in tok
            word = tok.replace(_QUOTED_MARK, "").translate(_OP_RESTORE)
            if fallback and ("'" in word or '"' in word):
                word, quoted = _SUBSTITUTED, False
            if mode == "test":
                cmd.append(word)
                if word == "]]" and not quoted:
                    mode = None
                continue
            if not quoted:
                if word == "esac":
                    saw_esac = True
                if at_cmd:
                    if word == "[[":
                        mode = "test"
                    elif word == "case":
                        saw_case = True
            if features is not None and not quoted:
                # `case` and `function` count wherever they stand unquoted, not only where this
                # reader tracks command position: a missed position would wrongly make the verify
                # simple, and counting a stray word errs toward present (the non-blocking side).
                if word == "case":
                    features.add("`case`")
                elif word == "function":
                    features.add("a function definition")
            if features is not None:
                if _PATH_ASSIGN_RE.match(word) or word == "PATH" or _is_dynamic_name_assignment(word):
                    # A prefix, plain, or `export` assignment -- and, read generously because
                    # bash has more ways than `PATH=`: `printf -v PATH`, `read PATH`, and an
                    # assignment whose name is computed (`export $VAR=bin`).
                    features.add("a PATH assignment")
                elif "install" in word.lower() or "bootstrap" in word.lower():
                    # `install` quoted or not, and inside a word (`./install.sh`,
                    # `scripts/bootstrap.sh`): a script by that name may put tools on PATH, so
                    # the ambiguous, non-blocking reading is taken.
                    features.add("an install step")
            cmd.append(_Quoted(word) if quoted else word)
            at_cmd = (at_cmd and not quoted
                      and (word in _PREFIX_KEYWORDS or _is_assignment(word)))
        if cmd and mode is None:
            line_cmds.append((cmd, "\n"))  # an unquoted newline ends a command
            cmd, at_cmd = [], True
        if in_case or saw_case:
            # Rule 2: the lines from `case` through `esac` are not checked, whole lines.
            in_case = not saw_esac
            continue
        for c, sep in line_cmds:
            commands.append(c)
            out_seps.append(sep)
    if cmd and not in_case:
        commands.append(cmd)  # an unclosed `[[` or `((` runs to the end (bash: a syntax error)
        out_seps.append("")
    if seps is not None:
        seps.extend(out_seps)
    return commands


def _is_assignment(tok):
    """D3: a token containing `=` before any `/` is an assignment, skipped as a first word."""
    eq = tok.find("=")
    slash = tok.find("/")
    return eq != -1 and (slash == -1 or eq < slash)


def _is_dynamic(tok):
    """A token whose value the shell computes: it starts with `$`, or a `/`-component does."""
    return tok.startswith("$") or any(part.startswith("$") for part in tok.split("/"))


def _is_object_name(tok):
    """D3's second amendment, rule 4: a `:` before the first `/` (`HEAD:docs/x.md`) is a git
    object name, not a path. (It also leaves `user@host:dir/x` and `ftp://...` unread.)"""
    colon, slash = tok.find(":"), tok.find("/")
    return colon != -1 and slash != -1 and colon < slash


def _path_shaped(tok):
    """D3's path shape: contains `/`, no glob characters, does not start with `-`, `$`, `~` or
    `http`, no component starts with `$`, and it is not a git object name."""
    return ("/" in tok and not any(ch in _GLOB_CHARS for ch in tok)
            and not tok.startswith(_ARG_SKIP_PREFIXES) and not _is_dynamic(tok)
            and not _is_object_name(tok))


def _arg_is_path(tok):
    """Whether an ARGUMENT is checked for existence: path-shaped, written without quotes
    (second amendment, rule 2), and not a `NAME=value` word (rule 3)."""
    return (not isinstance(tok, (_Quoted, _Op)) and _path_shaped(tok)
            and not _is_assignment(tok))


def _redirect_targets(cmd, j):
    """`("write", target)` for every `>`/`>>` from `cmd[j]` on. Everything after the first one is
    output and is not checked (D3); its targets are what the verify writes (second amendment,
    rule 5). Any operator holding `>` counts (`&>`, `>|`, `2>`): D3 names `>`/`>>` only, and
    recording a write can only clear a later finding, never raise one. A `>&2` target is an fd
    number, recorded harmlessly."""
    out = []
    while j < len(cmd):
        if isinstance(cmd[j], _Op) and ">" in cmd[j] and j + 1 < len(cmd) \
                and not isinstance(cmd[j + 1], _Op):
            out.append(("write", cmd[j + 1]))
            j += 2
            continue
        j += 1
    return out


def _is_python(tok):
    """Whether `tok` names a Python interpreter (`python3`, `python3.12`, `.venv/bin/python`)."""
    return bool(_PYTHON_RE.match(tok.rsplit("/", 1)[-1]))


def _module_candidates(tok, repo_root):
    """`-m`'s dotted module -> the files it may name, longest first; [] when not under the repo.

    D3 maps `tests.test_x` to `tests/test_x.py`. Two places D3 is silent, read conservatively:
    a module whose first segment is not a directory under the repo root (`json.tool`,
    `http.server`) is not checked -- `analyze` cannot tell a stdlib or installed module from a
    missing one without importing it, and importing is execution; and a trailing class or
    method (`tests.test_x.Case.test_y`) is allowed by accepting the longest prefix that
    resolves, as a `.py` file or a package directory."""
    if repo_root is None:
        return []  # relative checks have stopped (a dynamic `cd`): nothing to resolve against
    parts = tok.split(".")
    try:
        under_repo = (Path(repo_root) / parts[0]).is_dir()
    except (OSError, ValueError):
        under_repo = False
    if not under_repo:
        return []
    out = []
    for k in range(len(parts), 1, -1):
        stem = "/".join(parts[:k])
        out.extend((stem + ".py", stem))
    return out


def _is_word(tok):
    return not isinstance(tok, _Op)


def _script_checkable(tok):
    """An interpreter's script operand is checked when it contains `/` or ends in a script
    extension (third amendment, rule 1) -- written without quotes (the second amendment's
    trade stands: `python3 "bin/x.py"` is not checked), and not computed, a home path, a glob,
    a URL or a git object."""
    return (not isinstance(tok, (_Quoted, _Op)) and bool(tok)
            and ("/" in tok or tok.endswith(_SCRIPT_EXTS))
            and not tok.startswith(_ARG_SKIP_PREFIXES) and not _is_dynamic(tok)
            and not any(ch in _GLOB_CHARS for ch in tok) and not _is_object_name(tok)
            and not _is_assignment(tok))


def _cd_targets(args):
    """`cd`'s operand -> `[("cd", D, True)]` for a literal one, else `[("cd-unknown", ...)]`.

    Third amendment, rule 4: a bare `cd`, `cd -`, or a dynamic operand (`$`, a substitution)
    stops relative checks. Read the same way where the amendment is silent: an operand written
    with quotes (the second amendment makes it a value, never checked), one starting with `~`
    (home, which `analyze` never stats), or a glob."""
    words = [t for t in args if _is_word(t)]
    operand = next((t for t in words if t == "-" or not t.startswith("-")), None)
    if (operand is None or operand == "-" or isinstance(operand, _Quoted) or "$" in operand
            or operand.startswith("~") or any(ch in _GLOB_CHARS for ch in operand)):
        return [("cd-unknown", None, False)]
    return [("cd", str(operand), True)]


def _git_writes(args):
    """The directory operands `git init`, `git clone` and `git worktree add` write (third
    amendment, rule 4) -> `(writes, consumed_indices)`. Where the amendment is silent the read is
    generous: every non-option operand after `init` or `worktree add` (an option's value such as
    `-b main` is recorded too -- a spare write can only clear a later finding); `clone`'s last
    operand, or the directory git derives from a lone repository argument."""
    words = [(k, t) for k, t in enumerate(args) if _is_word(t)]
    names = [str(t) for _k, t in words]
    writes, consumed = [], set()

    def operands_after(pos):
        return [(k, t) for k, t in words[pos + 1:] if not t.startswith("-")]

    if "init" in names:
        for k, t in operands_after(names.index("init")):
            writes.append(str(t))
            consumed.add(k)
    if "worktree" in names:
        w = names.index("worktree")
        if w + 1 < len(names) and names[w + 1] == "add":
            for k, t in operands_after(w + 1):
                writes.append(str(t))
                consumed.add(k)
    if "clone" in names:
        ops = operands_after(names.index("clone"))
        if len(ops) >= 2:
            k, t = ops[-1]
            writes.append(str(t))
            consumed.add(k)
        elif len(ops) == 1:
            derived = str(ops[0][1]).rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
            if derived.endswith(".git"):
                derived = derived[:-4]
            if derived:
                writes.append(derived)
    return writes, consumed


def _command_targets(cmd, repo_root, defined=()):
    """One simple command -> what it asks of the tree, in order, as `(kind, value, blocking)`:

    - `("exec", word, True)`: a command word looked up on PATH;
    - `("path", p, blocking)`: a path. Blocking -- a missing one is a finding -- only in the
      third amendment's positions: the command word, an interpreter's script operand, the
      `-m`/`discover -s/-p` mappings. Every other path-shaped argument is non-blocking:
      resolved and reported, never failed;
    - `("module", [candidate, ...], True)`: a dotted `-m` module;
    - `("cd", D, True)` / `("cd-unknown", None, False)`: a literal `cd` (its operand blocking)
      or one that stops relative checks;
    - `("write", p, False)`: a path this command writes (a `>`/`>>` target; a `tee`/`touch`/
      `mkdir` operand; the last operand of `cp`/`mv`/`ln`/`install`; what `git init`/`clone`/
      `worktree add` creates), which the caller applies to LATER simple commands only;
    - `("define", name, False)`: a shell function this command defines.

    `repo_root` is the directory relative names resolve against for the `-m` first-segment rule
    (the repo root, or a literal `cd`'s target); None when relative checks have stopped.
    `defined` names the verify's functions so far: as command words they are not looked up."""
    out, cmd = [], list(cmd)
    own = None  # the function this command defines (`defined` itself is never copied: linear)
    # Rule 2: `f() {` or `function f` defines `f`; what follows on the line is a command.
    if len(cmd) >= 2 and _is_word(cmd[0]) and not isinstance(cmd[0], _Quoted) \
            and isinstance(cmd[1], _Op) and cmd[1] == "()":
        own = str(cmd[0])
        out.append(("define", own, False))
        cmd = cmd[2:]
    elif len(cmd) >= 2 and cmd[0] == "function" and not isinstance(cmd[0], _Quoted) \
            and _is_word(cmd[1]):
        name = str(cmd[1])
        own = name[:-2] if name.endswith("()") else name
        out.append(("define", own, False))
        cmd = cmd[2:]
        if cmd and isinstance(cmd[0], _Op) and cmd[0] == "()":
            cmd = cmd[1:]

    n, i, word = len(cmd), 0, None

    def is_word(k):
        return k < n and _is_word(cmd[k])

    while i < n:
        tok = cmd[i]
        if isinstance(tok, _Op):
            if tok == "((":
                return out  # rule 2: an arithmetic `((...))` command is not checked
            if ">" in tok:
                return out + [(kind, value, False) for kind, value in _redirect_targets(cmd, i)]
            if tok == "<" and is_word(i + 1):
                if _arg_is_path(cmd[i + 1]):
                    out.append(("path", cmd[i + 1], False))  # an input file: an argument
                i += 2
            elif "<" in tok:
                i += 2  # `<<TAG`, `<<<word`, `<&N`: a value, not a file (D3 silent)
            else:
                i += 1  # `(`/`)` (a subshell; the caller tracks its `cd`), `&`
            continue
        if _is_assignment(tok):
            i += 1
            continue
        word = tok
        i += 1
        break
    if word is None:
        return out
    # Rule 1: after `if then else elif while until do ! {`, `time` and `exec`, bash's grammar
    # puts the command word again. Skip assignment words (and a subshell's `(`) and take the
    # next word as the command word. A quoted `"if"` is not a reserved word and is not walked.
    while word in _PREFIX_KEYWORDS and not isinstance(word, _Quoted):
        j = i
        while j < n and ((isinstance(cmd[j], _Op) and cmd[j] == "(")
                         or (_is_word(cmd[j]) and _is_assignment(cmd[j]))):
            j += 1
        if word == "time" and j < n and _is_word(cmd[j]) and cmd[j] == "-p":
            j += 1  # POSIX `time -p cmd`
        if j >= n or not _is_word(cmd[j]):
            break  # nothing follows (`then` at a line end) or a redirect (`exec >log 2>&1`)
        if word == "exec" and cmd[j].startswith("-"):
            break  # `exec -a name cmd`: an option that takes a value -- not read (D3 silent)
        word = cmd[j]
        i = j + 1
    args = cmd[i:]
    out.append(("command", str(word), False))  # the caller notes `source`/`.`/`eval` (amendment 4)

    if word == "cd":
        return out + _cd_targets(args)
    if word in ("pushd", "popd"):
        # Third amendment silent; they move the directory like `cd`, so read them as a dynamic
        # one: relative checks stop.
        return out + [("cd-unknown", None, False)]

    exempt = word in _TEST_COMMANDS  # also after a walked prefix: `if [[ ... ]]`, `! [ ... ]`
    if word in VERIFY_BUILTINS or word in defined or word == own:
        pass  # a builtin, reserved word or the verify's own function: never looked up on PATH
    elif "$" in word:
        pass  # fifth amendment (2): `$` anywhere (`python${V}`, `python$(echo 3)`) is dynamic
    elif "/" in word:
        if _path_shaped(word):
            # Rule 1: a command word with `/` is a path that must exist -- quoted or not; the
            # second amendment exempts quoted ARGUMENTS only.
            out.append(("path", str(word), True))
        # else (`~/x`, a glob, `a:b/c`): not checked, applied conservatively
    else:
        out.append(("exec", str(word), True))
    if exempt:
        return out  # D3's amendments: `test`/`[`/`[[` operands are values, not files

    base = str(word).rsplit("/", 1)[-1]
    if word in VERIFY_BUILTINS:
        base = None  # `command python3 x.py`, `eval bash y.sh`: a builtin's words stay arguments
    # Rule 1: an interpreter's script operand is the first argument not starting with `-`,
    # unless `-c`, `-m` or `-` comes first.
    script_at = None
    if base in _INTERPRETERS:
        k = 0
        while k < len(args):
            tok = args[k]
            if isinstance(tok, _Op):
                if ">" in tok:
                    break
                k += 2 if "<" in tok else 1  # an input file or heredoc tag is not the script
                continue
            if tok in ("-c", "-m", "-"):
                break
            if not tok.startswith("-"):
                script_at = k
                break
            k += 1
    last_operand = None
    if base in _LAST_OPERAND_WRITERS:
        operands = [k for k, t in enumerate(args) if _is_word(t) and not t.startswith("-")]
        last_operand = operands[-1] if len(operands) >= 2 else None
    git_written, git_consumed = _git_writes(args) if base == "git" else ([], set())
    out.extend(("write", w, False) for w in git_written)

    # D3's `-m` rule is python's `-m`. Which tokens after it name modules, D3 leaves to its
    # example (`-m unittest tests.test_x`); read conservatively: the module right after a
    # python `-m`, and `unittest`'s positional test names -- not `git commit -m msg.txt`, and
    # not `python3 -m json.tool data.json`'s file argument.
    s_value = None
    for k, tok in enumerate(args):
        if isinstance(tok, _Op) and ">" in tok:
            break
        if tok == "-s" and not isinstance(tok, _Op) and k + 1 < len(args) \
                and _is_word(args[k + 1]):
            s_value = args[k + 1]
            break
    python_seen = _is_python(word)
    module = None
    expect_module = False
    seen_discover = False
    prev = None
    k = 0
    while k < len(args):
        tok = args[k]
        if isinstance(tok, _Op):
            if ">" in tok:
                out.extend((kind, value, False) for kind, value in _redirect_targets(args, k))
                break  # D3: everything after it is output
            expect_module = False
            prev = None
            k += 2 if (tok != "<" and "<" in tok) else 1
            continue
        if k == script_at:
            if _script_checkable(tok):
                out.append(("path", str(tok), True))
        elif k in git_consumed:
            pass  # written by git, recorded above
        elif base in _WRITING_COMMANDS:
            if not tok.startswith("-"):
                out.append(("write", str(tok), False))
        elif k == last_operand:
            out.append(("write", str(tok), False))
        elif expect_module:
            expect_module = False
            module = tok
            if _DOTTED_RE.match(tok):
                candidates = _module_candidates(tok, repo_root)
                if candidates:
                    out.append(("module", candidates, True))
            elif _arg_is_path(tok):
                out.append(("path", str(tok), False))
        elif tok == "-m" and python_seen and module is None:
            expect_module = True
        elif tok == "discover":
            seen_discover = True
        elif tok == "-p" and seen_discover and k + 1 < len(args) and _is_word(args[k + 1]):
            pattern = args[k + 1]
            k += 2
            prev = pattern
            # D3: after `-p` following a `discover`, a glob-free pattern maps to
            # `<-s value or tests>/<pattern>` -- a blocking position (third amendment).
            if pattern and not any(ch in _GLOB_CHARS for ch in pattern) \
                    and not pattern.startswith(_ARG_SKIP_PREFIXES) and not _is_dynamic(pattern):
                base_dir = s_value if s_value and not _is_dynamic(s_value) else "tests"
                out.append(("path", base_dir.rstrip("/") + "/" + pattern, True))
            continue
        elif module == "unittest" and prev != "-k" and _DOTTED_RE.match(tok) \
                and not tok.endswith(".py"):
            candidates = _module_candidates(tok, repo_root)
            if candidates:
                out.append(("module", candidates, True))
        elif _arg_is_path(tok):
            out.append(("path", str(tok), False))  # rule 1: resolved and reported, never failed
        elif not python_seen and _is_python(tok):
            python_seen = True  # `uv run python -m ...`, `env X=1 python3 -m ...`
        prev = tok
        k += 1
    return out


def _norm_written(path):
    """A written path in the one spelling compared (`os.path.normpath`; the root as "")."""
    if not path:
        return ""
    norm = os.path.normpath(path)
    return "" if norm == "." else norm


def _written_earlier(path, written):
    """Whether an earlier simple command of the same verify wrote exactly `path` (second
    amendment, rule 5), compared without a leading `./` or trailing `/`. A file BENEATH a
    `mkdir` operand is not one: the amendment defines "writes" as the operand itself, and
    widening it would clear `mkdir -p bin && python3 bin/missing.py`."""
    norm = _norm_written(path)
    return bool(norm) and norm in written


_VERIFY_MARKER_LINE_RE = re.compile(r"^[ \t]*(?:\*\*Verify[.:]\*\*|-?[ \t]*Verify:)",
                                    re.MULTILINE)


def _claim_text(block_text):
    """The part of a task block that may claim to create a path: everything before its verify
    (third amendment, rule 5: the brief and the acceptance; a verify's own words never claim).
    The cut is at `**Verify.**`, or -- for the dialects `kit_contract` does not read, where the
    amendment is silent -- at their own verify marker line, so that rule holds for them too."""
    text = block_text or ""
    cut = text.find("**Verify.**")
    if cut == -1:
        m = _VERIFY_MARKER_LINE_RE.search(text)
        cut = m.start() if m else -1
    return text if cut == -1 else text[:cut]


def _defines(cmd):
    """The function a simple command defines (`f() ...` or `function f ...`), or None."""
    if len(cmd) >= 2 and _is_word(cmd[0]) and not isinstance(cmd[0], _Quoted) \
            and isinstance(cmd[1], _Op) and cmd[1] == "()":
        return str(cmd[0])
    if len(cmd) >= 2 and cmd[0] == "function" and not isinstance(cmd[0], _Quoted) \
            and _is_word(cmd[1]):
        name = str(cmd[1])
        return name[:-2] if name.endswith("()") else name
    return None


_GROUP_OPENERS = frozenset(("{", "if", "while", "until", "for", "select"))
_GROUP_CLOSERS = frozenset(("}", "fi", "done"))


def _group_events(cmd):
    """One simple command -> its group opens and closes, in order: `(kind, True)` for `{`,
    `(` and a leading `if`/`while`/`until`/`for`/`select`, `(kind, False)` for `}`, `)`,
    `fi` and `done`. Reserved words count only where they are reserved -- the leading words of
    the command (after `(`, prefixes such as `!`/`then`/`do`, and assignments); a `)` counts
    anywhere, since a subshell closes at the end of the command it is in."""
    events = []
    leading = True
    for t in cmd:
        if isinstance(t, _Op):
            if t == "(":
                events.append(("(", True))
            elif t == ")":
                events.append((")", False))
            continue
        if not leading or isinstance(t, _Quoted):
            leading = False
            continue
        if t in _GROUP_OPENERS:
            events.append((str(t), True))
            if t in ("for", "select"):
                leading = False  # what follows is a variable and a word list, not a command
            continue
        if t in _GROUP_CLOSERS:
            events.append((str(t), False))
            continue
        if t in _PREFIX_KEYWORDS or _is_assignment(t):
            continue
        leading = False
    return events


def _check_verify(cmd, root, tid, creators):
    """One parseable verify -> `(executables, paths, findings)` (PLAN D3, as amended).

    Walks the simple commands in order, carrying what the verify itself changes: the directory
    a literal `cd` moved to (rule 4; a dynamic or bare one stops relative checks for the rest of
    the verify), a subshell's `(`...`)` undoing a literal `cd` made inside it, the functions it
    has defined (rule 2), and the paths an earlier command wrote (second amendment rule 5; third
    amendment rule 4). Every path is resolved and recorded with its state; only a missing one in
    a blocking position is a finding (third amendment, rule 1), and since the fourth amendment
    that finding is a warning -- only `verify-missing-executable` fails a run.

    D3's fifth amendment bounds that one too: it refuses only in a SIMPLE verify, one whose
    fence uses none of the features this reader does not model (a function definition, `case`,
    `${`, a multi-line or heredoc or `case` command substitution, a PATH assignment, `source`,
    `.` or `eval`, an install step). In any other verify every `verify-missing-executable` is
    marked `_warn` (the caller strips the mark and does not let it refuse) and its detail names
    the features."""
    executables, paths, findings = [], [], []
    recorded, failed = set(), set()
    exec_state, exec_finding = {}, {}  # word -> "exists"/"missing"; word -> its finding
    written, defined = set(), set()
    features = set()  # fifth amendment: the non-simple features this verify uses
    exec_findings = []
    cache = {}  # path -> classify_path result: a repeated path is stat'ed once (linear time)
    cwd, stack = "", []  # "" = the repo root; a repo-relative or absolute dir; None = unknown

    def effective(p):
        if os.path.isabs(p):
            return os.path.normpath(p)
        if cwd is None:
            return None  # rule 4: relative paths are not checked after a dynamic or bare `cd`
        return os.path.normpath(os.path.join(cwd, p)) if cwd else p

    def resolve(p):
        r = cache.get(p)
        if r is None:
            r = cache[p] = classify_path(p, root, tid, creators)
        if r["state"] == "missing" and _written_earlier(p, written):
            r = {"path": p, "state": "created-by", "by": tid}  # written by an earlier command
        return r

    def record(r, blocking):
        key = (r["path"], r["state"], r["by"])
        if key not in recorded:
            recorded.add(key)
            paths.append(r)
        if blocking and r["state"] == "missing" and r["path"] not in failed:
            failed.add(r["path"])
            findings.append({"task": tid, "kind": "verify-missing-path",
                             "detail": f"`{r['path']}` does not exist and no task at or upstream "
                                       f"of {tid} says it creates it"})

    seps = []
    commands = verify_tokens(cmd, features, seps)
    # Sixth amendment (1): a command word in the LEFT operand of `||` is expected to fail. And-or
    # lists bind left to right, so every pipeline before a `||` in the same list is inside its
    # left operand (`a && b || c`: both `a` and `b`). Computed backwards: `||` sets it, `&&` and
    # `|` carry it from the right, and `;`, a newline or the end start a new list.
    or_left = [False] * len(commands)
    following = False
    for k in range(len(commands) - 1, -1, -1):
        sep = seps[k] if k < len(seps) else ""
        following = sep == "||" or (sep in ("&&", "|", "|&") and following)
        or_left[k] = following
    # Sixth amendment (6): a GROUP that is the left operand of `||` -- `{ ... }`, `( ... )`,
    # `if ... fi`, a `while`/`until`/`for`/`select ... done` loop -- makes every command in it
    # a left operand. The group's place in its and-or list is that of the command that closes
    # it, so when that command is a left operand the whole span is. (`case ... esac` lines are
    # dropped unread.) One pass with a stack: linear.
    open_groups, marked_spans = [], []
    for k, simple in enumerate(commands):
        for kind, opens in _group_events(simple):
            if opens:
                open_groups.append(k)
            elif open_groups:
                start = open_groups.pop()
                if or_left[k]:
                    marked_spans.append((start, k))
    # Fill the spans with a difference array, so nested spans cost linear time, not their sum.
    if marked_spans:
        delta = [0] * (len(commands) + 1)
        for start, end in marked_spans:
            delta[start] += 1
            delta[end + 1] -= 1
        depth = 0
        for j in range(len(commands)):
            depth += delta[j]
            if depth > 0:
                or_left[j] = True
        # And a command joined by `&&`/`|` to a marked group's first command is in the same
        # left operand (`x && { b; } || c`): carry the marks back once more.
        for k in range(len(commands) - 2, -1, -1):
            sep = seps[k] if k < len(seps) else ""
            if sep in ("&&", "|", "|&") and or_left[k + 1]:
                or_left[k] = True
    # A command word inside a function BODY is resolved when the function is called, not where
    # its text stands, so there every function the verify defines anywhere counts (`main() {
    # helper; }` before `helper() {...}`). At top level only an earlier definition counts: a call
    # before its definition is a sure failure. (Rule 2 says "later command words"; bodies are
    # where the amendment is silent, and this is the reading that refuses only sure things.)
    all_defined = {name for c in commands for name in [_defines(c)] if name}
    frames = []  # open `{` groups: "body" for a function's, "group" otherwise
    bodies = 0  # how many "body" frames are open: counted, not scanned (linear time)

    for idx, simple in enumerate(commands):
        opens = sum(1 for t in simple if isinstance(t, _Op) and t == "(")
        closes = sum(1 for t in simple if isinstance(t, _Op) and t == ")")
        stack.extend([cwd] * opens)
        body_open = _defines(simple) is not None
        for t in simple:
            if _is_word(t) and not isinstance(t, _Quoted) and t == "{":
                frames.append("body" if body_open else "group")
                bodies += body_open
                body_open = False
        in_body = bodies > 0
        base_dir = None if cwd is None else (Path(cwd) if os.path.isabs(cwd) else root / cwd)
        # all_defined holds every name `defined` will ever hold, so no union is needed
        targets = _command_targets(simple, base_dir, all_defined if in_body else defined)
        for t in simple:
            if _is_word(t) and not isinstance(t, _Quoted) and t == "}" and frames:
                bodies -= frames.pop() == "body"
        for kind, value, blocking in targets:
            if kind == "define":
                defined.add(value)
            elif kind == "exec":
                if value not in exec_state:
                    exec_state[value] = "exists" if shutil.which(value) else "missing"
                    executables.append({"word": value, "state": exec_state[value]})
                if exec_state[value] != "missing":
                    continue
                prior = exec_finding.get(value)
                if prior is None:
                    finding = {"task": tid, "kind": "verify-missing-executable",
                               "detail": f"`{value}` is not on PATH"}
                    if or_left[idx]:
                        finding["_or"] = True
                    findings.append(finding)
                    exec_findings.append(finding)
                    exec_finding[value] = finding
                elif not or_left[idx]:
                    prior.pop("_or", None)  # also used outside a `||` guard: that use refuses
            elif kind == "path":
                eff = effective(value)
                if eff is not None:
                    record(resolve(eff), blocking)
            elif kind == "module":
                effs = [effective(c) for c in value]
                if all(e is not None for e in effs):
                    results = [resolve(e) for e in effs]
                    record(next((r for r in results if r["state"] != "missing"), results[0]),
                           True)
            elif kind == "cd":
                eff = effective(value)
                if eff is None:
                    continue
                r = resolve(eff)
                record(r, True)
                target = Path(eff) if os.path.isabs(eff) else root / eff
                try:
                    is_dir = r["state"] == "exists" and target.is_dir()
                except (OSError, ValueError):
                    is_dir = False
                # A `cd` into what the tree lacks -- missing (already a finding) or made by the
                # verify itself -- stops relative checks: nothing under it can be read statically
                # (rule 4 is silent here; this is the conservative read).
                cwd = _norm_written(eff) if is_dir else None
            elif kind == "cd-unknown":
                cwd = None
        for kind, value, _blocking in targets:
            if kind == "write":
                eff = effective(value)
                if eff:
                    norm = _norm_written(eff)
                    if norm:
                        written.add(norm)
            elif kind == "command":
                if value in ("source", ".", "eval"):
                    features.add(f"`{value}`")
                elif value.rsplit("/", 1)[-1] in _PACKAGE_MANAGERS:
                    features.add("an install step")  # a package manager as the command word
                elif value in ("alias", "enable"):
                    # An alias (with `expand_aliases`) or a builtin loaded by `enable -f` defines
                    # a command word this reader cannot see (sixth-round conformance).
                    features.add("an alias or a loaded builtin")
                elif value in ("type", "hash", "which") or (
                        value == "command" and any(_is_word(t) and _PROBE_FLAG_RE.match(t)
                                                   for t in simple)):
                    features.add("a tool probe")  # sixth amendment (1): `command -v`, `type`, ...
        for _ in range(closes):
            restored = stack.pop() if stack else cwd
            # The subshell's literal `cd` ends with it; a stop stays a stop ("for the rest of
            # the verify", rule 4).
            cwd = None if cwd is None or restored is None else restored
    why = ", ".join(sorted(features))
    for finding in exec_findings:
        guarded = finding.pop("_or", False)
        if features:
            finding["_warn"] = True
            finding["detail"] += (f" -- a warning, not a refusal: this verify uses {why}, which "
                                  f"analyze does not model (D3, fifth amendment)")
        elif guarded:
            finding["_warn"] = True
            finding["detail"] += (" -- a warning, not a refusal: it is the left operand of `||`, "
                                  "so the verify expects it may fail (D3, sixth amendment)")
    return executables, paths, findings


def analyze_kit(kit_dir, tasks, strict=False, repo_root=None):
    """The kit checked against itself and the tree, without running anything -> the result.

    Every task is reported, whatever its status (sixth amendment, (2): the status filter lives
    in the drivers' gate, `exit_if_unsound_kit`)."""
    return _analyze_kit(kit_dir, tasks, strict=strict, repo_root=repo_root)[0]


def _analyze_kit(kit_dir, tasks, strict=False, repo_root=None):
    """`analyze_kit`'s work -> `(result, refusing)`, `refusing` the ids of the tasks holding a
    finding that refuses -- since D3's seventh amendment only a `verify-unparseable`. Kept apart
    so the result's shape stays exactly the briefed one.

    `{"v", "kit", "strict", "exit": 0|3, "findings": [{"task", "kind", "detail"}],
    "paths": {task: [{"path", "state", "by"}]}, "verify": {task: {"parseable", "hint",
    "executables": [{"word", "state"}], "paths": [{"path", "state", "by"}]}}}`.

    Per task: the paths its brief names (`brief_paths`), and its verify command's parseability
    and runnability -- every first word on PATH, every path-shaped argument present or created
    by this task or one upstream of it (PLAN D3). `exit` is 3 when a `verify-unparseable` occurs
    (an empty fence included) -- the only finding that refuses since D3's seventh amendment --
    or, under `strict`, when there is any finding at all; otherwise 0, with every warning
    listed. A `verify-missing-executable` still says in its detail whether the verify was simple
    and unguarded, but it is a warning either way. The repo root defaults to the checkout that holds the kit
    (`attempt_ledger.kit_repo_root`), so a fixture kit resolves against its own temp tree.
    Validating the graph is `exit_if_invalid_graph`'s job, done by every caller first.
    """
    kit_dir = Path(kit_dir)
    root = Path(repo_root) if repo_root is not None else _al().kit_repo_root(kit_dir)
    try:
        tasks_text = (kit_dir / "TASKS.md").read_text()
    except (OSError, UnicodeDecodeError):
        tasks_text = ""
    blocks = _task_blocks(tasks_text)
    order = [t["id"] for t in tasks]
    text_of = {t["id"]: blocks.get(t["id"], t.get("brief") or "") for t in tasks}
    depends_of = {t["id"]: list(t.get("depends") or []) for t in tasks}

    # Third amendment, rule 5: a creation claim is read from the block before its verify only.
    claim_of = {tid: _claim_text(text) for tid, text in text_of.items()}
    index = _Creators(order, claim_of, depends_of)  # built once: linear over a long chain

    findings, paths, verify = [], {}, {}
    refusing_tasks = set()
    warned_exec = False
    for t in tasks:
        tid = t["id"]
        creators = index  # upstream (transitively) and "self" alike, for brief and verify (D3)

        entries = [classify_path(p, root, tid, creators) for p in brief_paths(text_of[tid])]
        paths[tid] = entries
        for e in entries:
            if e["state"] == "missing":
                findings.append({"task": tid, "kind": "brief-missing-path",
                                 "detail": f"`{e['path']}` does not exist and no task at or "
                                           f"upstream of {tid} says it creates it"})

        cmd = t.get("verify")
        entry = {"parseable": bool(cmd and cmd.strip()), "hint": None, "executables": [],
                 "paths": []}
        verify[tid] = entry
        if cmd is not None and not cmd.strip():
            # Sixth amendment (3): a `**Verify.**` fence that is empty or only whitespace has
            # nothing to run (`_extract_verify` returns "" for it, not None).
            findings.append({"task": tid, "kind": "verify-unparseable",
                             "detail": "the **Verify.** fence is empty: there is nothing to run"})
            refusing_tasks.add(tid)
            continue
        if cmd is None:
            try:
                # The task's own block, not the whole TASKS.md: `_task_verify_cmd` reads only the
                # block under the task's heading anyway, and handing it the full text made this
                # quadratic over a kit of many unparseable tasks (fifth amendment, (2)).
                block = blocks.get(tid)
                other = _kvh()._task_verify_cmd(block, tid) if block else None
            except Exception:  # the hint is advice; failing to compute it changes no finding
                other = None
            if other is not None:
                entry["hint"] = VERIFY_UNPARSEABLE_HINT
            detail = "no **Verify.** marker followed by a ```bash fence"
            if entry["hint"]:
                detail += f"; {entry['hint']}"
            findings.append({"task": tid, "kind": "verify-unparseable", "detail": detail})
            refusing_tasks.add(tid)
            continue

        executables, vpaths, vfindings = _check_verify(cmd, root, tid, creators)
        entry["executables"].extend(executables)
        entry["paths"].extend(vpaths)
        for f in vfindings:
            if f.pop("_warn", False):
                warned_exec = True  # fifth/sixth amendment: not a simple verify, or `||`-guarded
            elif f["kind"] in _FAILING_FINDINGS:
                refusing_tasks.add(tid)
        findings.extend(vfindings)

    warned = warned_exec or any(f["kind"] in _WARNING_FINDINGS for f in findings)
    result = {
        "v": CONTRACT_VERSION, "kit": kit_dir.resolve().name, "strict": bool(strict),
        "exit": 3 if refusing_tasks or (strict and warned) else 0,
        "findings": findings, "paths": paths, "verify": verify,
    }
    return result, refusing_tasks


def render_analyze(result):
    """`analyze_kit`'s result as terse text an executor can paste into its context: one line
    per finding, one per path not found in the tree (`created-by <id>` or `missing`), then
    `analyze: sound` or `analyze: <n> finding(s)`."""
    lines = [f"analyze: {f['task']} {f['kind']} -- {f['detail']}" for f in result["findings"]]
    seen = set()
    for tid, entries in result["paths"].items():
        for e in entries + result["verify"].get(tid, {}).get("paths", []):
            if e["state"] == "exists":
                continue
            line = f"analyze: {tid} path {e['path']} {e['state']}"
            if e.get("by"):
                line += f" {e['by']}"
            if line not in seen:
                seen.add(line)
                lines.append(line)
    n = len(result["findings"])
    lines.append("analyze: sound" if n == 0 else f"analyze: {n} finding(s)")
    return "\n".join(lines)


def exit_if_unsound_kit(kit_dir, tasks, out=None, selected=None):
    """The drivers' pre-dispatch seat for `analyze` (PLAN D5): print the report to `out`
    (default: `sys.stderr` as it is at call time) and exit 3 when the drivers cannot read a
    verify (or its fence is empty), so no dispatch could prove the task; otherwise return the
    result. Static and free, so there is no opt-out; every other finding -- missing paths and
    missing executables alike -- is printed and never fails a run (D5, as amended with D3's
    fourth and seventh amendments).

    It checks only what the run will run (D3/D5 sixth and seventh amendments): only a task whose
    status is `pending` or `in-progress` can refuse; a `done` or `blocked` task's findings are
    printed but never exit. The one exception (PLAN D5, amended during T5): the task whose id is
    `selected` -- the one the run was told to run (`--task`, which may be a `done` task under
    `--rerun` or a `blocked` retry) -- refuses whatever its status. An invalid graph is
    `exit_if_invalid_graph`'s, called before this."""
    if validate_graph(tasks):
        # An invalid graph is `exit_if_invalid_graph`'s to refuse (exit 2) and the driver's own
        # graph check comes after this call in some drivers: analysing a graph with a duplicate
        # id would only misattribute findings, and could exit 3 before that exit 2 is reached.
        return None
    result, refusing = _analyze_kit(kit_dir, tasks, strict=False)
    print(render_analyze(result), file=out if out is not None else sys.stderr)
    status = {t["id"]: t.get("status") for t in tasks}
    # Seventh amendment (3): only a task the run may dispatch can refuse it -- `pending` or
    # `in-progress`; `done` and `blocked` never do.
    if any(status.get(tid) in ("pending", "in-progress") or (selected is not None and tid == selected)
           for tid in refusing):
        sys.exit(3)
    return result


# ---- re-checking finished work against today's tree: `drift` (kit-preflight T8) -----------------
#
# WHAT WAS MISSING. A `done` task stayed done whatever happened to the tree after it was accepted,
# and the one operation that re-ran a finished task's check, `refresh`, re-binds ONE task's
# evidence and moves it to `blocked` on failure -- it changes kit state on purpose, under an
# operator's explicit task argument (PLAN D8). Nothing could ask "which finished tasks still hold
# today?" without changing the answer's subject. `drift` is that survey.
#
# A REPORT, NOT A VERDICT (PLAN B3, D7). It runs each done task's verify through the runner it is
# handed -- on the command line, `exec_policy.verify_runner`, `enforced` unless the operator names
# `trusted-host`, and the report's first line says which -- and it changes no status, writes
# nothing in TASKS.md or NOTES.md, dispatches nothing, and writes nothing under the kit dir. Its
# one write is an `evidence.drift` event per checked task in the attempt ledger, outside the tree,
# carrying the state, exit code and digests and never the verify's output, which may hold paths.
# `tests/test_kit_evidence.py` reads this function's source for every status-writing helper's name.
#
# `unrunnable` MEANS ONE THING (D7 as amended after the Phase 2 review): the drivers cannot read
# the verify (`verify-unparseable`, an empty fence included). Every other done task is run and
# judged by its exit code; its `verify-missing-*` warnings ride along so a `drifted` caused by a
# missing tool says so. The state is never read from `analyze`'s per-path entry states, which
# record non-blocking arguments (`origin/main`, `s/a/b/`, an `--out` target) as `missing`.

#: Per checked task: its verify passed now, failed now, or cannot be read and was not run.
DRIFT_STATES = ("holds", "drifted", "unrunnable")
#: The task's acceptance identity now against the one its latest recorded acceptance carried.
ACCEPTANCE_STATES = ("unchanged", "changed", "unknown")


def drift_kit(kit_dir, tasks, runner, store=None, workspace=None, run_id=None, record=True,
              confinement=None):
    """Each done task's verify, re-run against the tree as it is now -> the report (PLAN D7).

    `runner(cmd) -> (rc, output)` is the only way anything executes; the output is discarded.
    `analyze_kit` is called once first: a task holding a `verify-unparseable` finding is
    `unrunnable` and is not run. Every other done task's stripped verify text runs once per
    distinct text -- a later task with the same text reuses that exit code and names the task
    whose run it is in `shared_with` -- and reads `holds` on exit 0, `drifted` otherwise (a
    runner that cannot start the process counts as 126, as in `refresh`). `acceptance` compares
    the latest recorded acceptance's `acceptance_ref` with `acceptance_identity(task)` now:
    `unknown` when either side is missing. Tasks in any other status are absent from the report.

    `workspace` is the root the static check resolves paths against (default: the checkout that
    holds the kit). `confinement` labels the boundary the runner applies, as a value or as a
    zero-argument callable read after each run (the command line passes what
    `exec_policy.verify_runner`'s `on_result` reported). When `record`, one `evidence.drift`
    event per checked task is appended to the kit's ledger with exactly `run`, `task`, `state`,
    `rc`, `acceptance`, `verify_sha`, `confinement` and `shared_with`; a `run_id` of None then
    gets a fresh content-free one so the events still correlate.

    Returns `{"v", "kit", "confinement", "tasks": {id: {"state", "rc", "acceptance",
    "verify_sha", "shared_with", "warnings"[, "reason"]}}, "exit": 0|3}`, `exit` 3 when any task
    is `drifted` or `unrunnable`.
    """
    al = _al()
    kit_dir = Path(kit_dir)
    root = Path(workspace) if workspace is not None else al.kit_repo_root(kit_dir)
    static = analyze_kit(kit_dir, tasks, repo_root=root)
    findings_of = {}
    for f in static["findings"]:
        findings_of.setdefault(f["task"], []).append(f)
    ledger = open_ledger(kit_dir, store=store)
    if record and run_id is None:
        run_id = generate_run_id()
    done = [t for t in tasks if t.get("status") == "done"]
    # Acceptances are read before this run appends anything, so its own events never lengthen
    # the reads (each `latest_acceptance` scans the whole stream), and only for a task with an
    # identity now: without one the answer is `unknown` whatever the ledger holds.
    accepted = {t["id"]: ledger.latest_acceptance(t["id"]) for t in done
                if acceptance_identity(t) is not None}

    ran = {}  # stripped verify text -> {"rc": the one run's exit code, "by": the task that ran it}
    report = {}
    for t in done:
        tid = t["id"]
        mine = findings_of.get(tid, [])
        cmd = (t.get("verify") or "").strip()
        unparseable = [f for f in mine if f["kind"] == "verify-unparseable"]
        shared_with = []
        if unparseable:
            state, rc = "unrunnable", None
        else:
            if cmd in ran:
                # The task whose run this result is. One id, not every earlier sharer, so the
                # event stays bounded however many tasks repeat one verify text.
                shared_with = [ran[cmd]["by"]]
            else:
                try:
                    rc = runner(cmd)[0]  # the output is discarded: never stored, never reported
                except OSError:
                    rc = 126  # could not start: a failed check, as `refresh` records it
                ran[cmd] = {"rc": rc, "by": tid}
            rc = ran[cmd]["rc"]
            state = "holds" if rc == 0 else "drifted"

        then = al.read_ref((accepted.get(tid) or {}).get("acceptance_ref"))
        now = acceptance_identity(t)
        if not (then and now and then.get("sha") and now.get("sha")):
            acceptance = "unknown"
        else:
            acceptance = "unchanged" if then["sha"] == now["sha"] else "changed"

        verify_sha = al._sha(cmd) if cmd else None
        entry = {"state": state, "rc": rc, "acceptance": acceptance, "verify_sha": verify_sha,
                 "shared_with": shared_with,
                 "warnings": [{"kind": f["kind"], "detail": f["detail"]} for f in mine
                              if f["kind"].startswith("verify-missing-")]}
        if unparseable:
            entry["reason"] = unparseable[0]["detail"]
        report[tid] = entry
        if record:
            label = confinement() if callable(confinement) else confinement
            ledger.append("evidence.drift", run=run_id, task=tid, state=state, rc=rc,
                          acceptance=acceptance, verify_sha=verify_sha, confinement=label,
                          shared_with=shared_with)

    return {
        "v": CONTRACT_VERSION,
        "kit": kit_dir.resolve().name,
        "confinement": confinement() if callable(confinement) else confinement,
        "tasks": report,
        "exit": 3 if any(e["state"] in ("drifted", "unrunnable") for e in report.values()) else 0,
    }


def render_drift(result):
    """`drift_kit`'s report as text: the boundary first, so a `trusted-host` run never reads as
    enforced; one line per checked task; the tally last."""
    lines = [f"drift: {result['kit']} confinement={result.get('confinement') or 'unknown'}"]
    counts = {state: 0 for state in DRIFT_STATES}
    for tid, entry in result["tasks"].items():
        counts[entry["state"]] = counts.get(entry["state"], 0) + 1
        line = f"drift: {tid} {entry['state']} acceptance={entry['acceptance']}"
        if entry.get("shared_with"):
            line += f" shared-with {','.join(entry['shared_with'])}"
        lines.append(line)
    lines.append(f"drift: {counts['holds']} hold, {counts['drifted']} drifted, "
                 f"{counts['unrunnable']} unrunnable")
    return "\n".join(lines)


def _drift_cli(args):
    """`drift`'s command line -> its exit code, never 1: drift is a report, not a failure
    (PLAN B3).

    - 0: every kit was checked and every checked task holds, or `--all` found no kit at all
      (`drift: no kit under <dir>`).
    - 3: any checked task drifted or cannot be read, or, under `--all`, any kit was reported but
      not checked -- a TASKS.md that fails to parse, an invalid graph, a slug the ledger refuses
      (PLAN D7, amended after T8's red-team: a check that cannot run is not a hold).
    - 2: a refusal before or instead of the report -- under `--kit`, an unreadable TASKS.md, an
      invalid graph or a slug the ledger refuses; under either, a missing `--kits-dir`, no
      boundary in `enforced` mode, or a ledger that cannot be written (which stops the run).

    `--json`'s top-level `exit` under `--all` is this same code."""
    if args.all:
        kits_dir = Path(args.kits_dir)
        if not kits_dir.is_dir():
            print(f"drift: no kits dir at {kits_dir}", file=sys.stderr)
            return 2
        kits = sorted({p.parent for p in kits_dir.glob("*/TASKS.md")}, key=lambda p: p.name)
    else:
        kits = [Path(args.kit)]
    run_id = generate_run_id()
    fallback = "trusted-host" if args.exec_mode == "trusted-host" else None
    ep = _ep()
    sections, payload, worst = [], [], 0
    refusal = None
    skipped = 0  # kits reported but not checked under --all: each makes the exit 3
    for kit in kits:
        try:
            tasks = parse_tasks(_read_tasks_text(kit))
        except (OSError, ValueError) as exc:
            reason = " ".join(str(exc).split())
            if not args.all:
                print(f"drift: {reason}", file=sys.stderr)
                return 2
            sections.append(f"kit: {kit.name} unparseable -- {reason}")
            payload.append({"kit": kit.name, "unparseable": reason})
            skipped += 1
            continue
        if not args.all:
            exit_if_invalid_graph(tasks, kit / "TASKS.md")
        else:
            graph_findings = validate_graph(tasks)
            if graph_findings:
                reason = " ".join(render_findings(graph_findings).split())
                sections.append(f"kit: {kit.name} invalid graph -- {reason}")
                payload.append({"kit": kit.name, "invalid": reason})
                skipped += 1
                continue
        box = {}
        repo_root = _al().kit_repo_root(kit)
        try:
            runner = ep.verify_runner(
                repo_root, mode=args.exec_mode,
                on_result=lambda r, box=box: box.update(
                    confinement=r.get("confinement") if isinstance(r, dict) else None))
            result = drift_kit(kit, tasks, runner, store=args.attempt_store,
                               workspace=repo_root, run_id=run_id, record=not args.no_record,
                               confinement=lambda box=box: box.get("confinement") or fallback)
        except ValueError as exc:
            # A name the ledger refuses as a namespace (a dot-prefixed kit dir, say) is this
            # kit's problem: under --all it is reported and skipped like an unparseable one.
            reason = " ".join(str(exc).split())
            if not args.all:
                refusal = f"drift: {kit.name} -- {reason}"
                break
            sections.append(f"kit: {kit.name} skipped -- {reason}")
            payload.append({"kit": kit.name, "skipped": reason})
            skipped += 1
            continue
        except (OSError, RuntimeError) as exc:
            # `SandboxUnavailable` (no boundary in `enforced` mode) and `LedgerError` are both
            # RuntimeErrors; with an unwritable store they hold for every kit, so the run stops.
            refusal = f"drift: {kit.name} -- {' '.join(str(exc).split())}"
            break
        for tid, entry in result["tasks"].items():
            # D7 as amended: a `drifted` caused by a missing tool is labelled as such. On stderr,
            # so the report's own lines keep the briefed shape.
            if entry.get("reason"):
                print(f"drift: {result['kit']} {tid} unrunnable -- {entry['reason']}",
                      file=sys.stderr)
            for w in entry["warnings"]:
                print(f"drift: {result['kit']} {tid} warning {w['kind']} -- {w['detail']}",
                      file=sys.stderr)
        sections.append(render_drift(result))
        payload.append(result)
        worst = max(worst, result["exit"])
    rc = 2 if refusal else (3 if worst or skipped else 0)
    try:
        if args.json:
            body = payload[0] if (not args.all and payload) else {
                "v": CONTRACT_VERSION, "kits": payload, "exit": rc}
            print(json.dumps(body, indent=2, sort_keys=True))
        elif sections:
            print("\n\n".join(sections))
        elif args.all and not refusal:
            print(f"drift: no kit under {args.kits_dir}")
        sys.stdout.flush()
    except BrokenPipeError:
        # stdout closed early (`| head`): exit quietly with drift's own code, as `analyze` does.
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
            os.close(devnull)
        except (OSError, ValueError):
            pass
    if refusal:
        print(refusal, file=sys.stderr)
    return rc


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
                    "its ready frontier; `analyze` checks a kit's brief paths and verify "
                    "commands statically, before any dispatch, running nothing; `drift` re-runs "
                    "done tasks' verify commands inside the execution boundary and reports. "
                    "`drift` itself writes nothing in the tree or the kit dir, but the verifies "
                    "it runs may, because the workspace is writable under the policy, and "
                    "`trusted-host` confines nothing; `demo` walks synthetic graphs and spends "
                    "nothing.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_graph = sub.add_parser("graph", help="validate TASKS.md's DAG; exit 2 when invalid")
    p_graph.add_argument("--kit", required=True, help="kit directory holding TASKS.md")
    p_graph.add_argument("--json", action="store_true", help="the graph_state dict as JSON")
    p_graph.add_argument("--attempt-store", default=None,
                         help="ledger root for artifact bindings (default: the data root)")
    p_analyze = sub.add_parser("analyze", help="static pre-run check: paths a brief names, "
                                               "verify parseability and runnability; runs and "
                                               "writes nothing; exit 3 only on a verify the "
                                               "drivers cannot read (or an empty one), 2 on an "
                                               "invalid graph")
    p_analyze.add_argument("--kit", required=True, help="kit directory holding TASKS.md")
    p_analyze.add_argument("--strict", action="store_true",
                           help="a missing path or executable, in a brief or a verify, also fails (exit 3)")
    p_analyze.add_argument("--json", action="store_true", help="the analyze result as JSON")
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
    p_accept = sub.add_parser("accept", help="record the acceptance a done task's outcome: line "
                                              "already states, in the ledger outside the tree; "
                                              "the line must carry run= equal to --run, a run "
                                              "from today or yesterday (UTC); exit 2 on refusal",
                              allow_abbrev=False)  # `--at` must not resolve to --attempt-store
    p_accept.add_argument("--kit", required=True)
    p_accept.add_argument("--task", required=True)
    p_accept.add_argument("--run", required=True, help="run id, <UTC-date>-<4 hex>")
    p_accept.add_argument("--attempt-store", default=None)
    p_accept.add_argument("--note", default="")
    p_drift = sub.add_parser("drift", help="re-run each done task's verify against the tree as "
                                            "it is now, inside the execution boundary; changes "
                                            "no status, and itself writes nothing in the tree "
                                            "(the verifies it runs may); exit 3 when "
                                            "a task drifted or cannot be read, never 1",
                             allow_abbrev=False)
    p_drift_which = p_drift.add_mutually_exclusive_group(required=True)
    p_drift_which.add_argument("--kit", help="kit directory holding TASKS.md")
    p_drift_which.add_argument("--all", action="store_true",
                               help="every <kits-dir>/*/TASKS.md, one section per kit")
    p_drift.add_argument("--kits-dir", default=".claude/kits",
                         help="where --all looks (default: .claude/kits)")
    p_drift.add_argument("--attempt-store", default=None,
                         help="ledger root for acceptances and evidence.drift (default: the "
                              "data root)")
    p_drift.add_argument("--exec-mode", choices=("enforced", "trusted-host"), default="enforced",
                         help="enforced (default) needs an OS boundary; trusted-host runs with "
                              "none and the report's first line says so")
    p_drift.add_argument("--json", action="store_true", help="the drift report as JSON")
    p_drift.add_argument("--no-record", action="store_true",
                         help="append no evidence.drift event to the ledger")
    sub.add_parser("demo", help="a diamond DAG walked to completion, invalid graphs, rosters")
    args = parser.parse_args(argv)

    if args.cmd == "demo":
        _demo()
        return 0
    if args.cmd == "analyze":
        try:
            tasks = parse_tasks(_read_tasks_text(args.kit))
        except (OSError, ValueError) as exc:
            print(f"analyze: {exc}", file=sys.stderr)
            return 2
        exit_if_invalid_graph(tasks, Path(args.kit) / "TASKS.md")
        result = analyze_kit(args.kit, tasks, strict=args.strict)
        try:
            if args.json:
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                print(render_analyze(result))
            sys.stdout.flush()
        except BrokenPipeError:
            # Seventh amendment (4): stdout closed early (`| head`). Exit quietly with
            # analyze's own code; pointing stdout at /dev/null stops the interpreter's final
            # flush from printing "Exception ignored" on the way out.
            try:
                devnull = os.open(os.devnull, os.O_WRONLY)
                os.dup2(devnull, sys.stdout.fileno())
                os.close(devnull)
            except (OSError, ValueError):
                pass
        return result["exit"]
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
    if args.cmd == "accept":
        if not _valid_run_id(args.run):
            print(f"accept: --run {args.run!r} is not a run id (<UTC-date>-<4 hex>)",
                  file=sys.stderr)
            return 2
        tasks = parse_tasks(_read_tasks_text(args.kit))
        exit_if_invalid_graph(tasks, Path(args.kit) / "TASKS.md")
        task = next((t for t in tasks if t["id"] == args.task), None)
        if task is None:
            print(f"no task with id {args.task!r} in this kit", file=sys.stderr)
            return 2
        try:
            summary = accept_task(args.kit, task, args.run, store=args.attempt_store,
                                  note=args.note)
        except (ValueError, OSError) as exc:
            reason = " ".join(str(exc).split())
            print(f"accept: {reason}", file=sys.stderr)
            return 2
        print(render_accept(summary))
        caught = _al()._rd().describe(summary["note_report"])
        if caught:
            print(f"accept: note {caught}", file=sys.stderr)
        return 0
    if args.cmd == "drift":
        return _drift_cli(args)
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
