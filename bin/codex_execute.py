#!/usr/bin/env python3
"""Kit-dispatch driver: run an execution kit against OpenAI Codex CLI's non-interactive mode.

This is the Codex-side port of `bin/copilot_execute.py` (read that first — it is the template
for structure, TASKS.md grammar, statuses, writeback, and the injectable-runner safety seam).
It parses a kit's TASKS.md, dispatches each task to `codex exec` with a role preamble, reruns
the task's verify command, escalates up the pricing tiers on failure, and writes statuses /
NOTES back. Kits live at `tasks/kits/<slug>/` in consumer repos.

============================================================================================
 !!! QUOTA / NETWORK SAFETY — READ THIS BEFORE RUNNING OR TESTING ANYTHING !!!
============================================================================================
A real (non-`--dry-run`) `run`/`review` shells out to the `codex` CLI. `codex exec ...` CALLS
A MODEL: it SPENDS THE USER'S REAL ChatGPT-subscription usage limits (or API dollars) and HITS
THE NETWORK, and the user has a live `~/.codex`. NEVER invoke the real `codex` binary during
development or verification.

  * `--dry-run` prints the exact dispatch argv and SPAWNS NOTHING (writes nothing either).
  * Every dispatch and every verify goes through an INJECTABLE runner callable
    (`run_task(..., runner=, verify_runner=)`). Tests always inject a fake runner or pass a
    temporary stub executable via `--codex-bin` — never the real binary.
  * `build_dispatch` returns an argv LIST; dispatch never uses `shell=True`.

Dispatch anatomy: `codex exec --model ... --sandbox workspace-write -c
model_reasoning_effort=...`. OpenAI's CLI 0.147.0 changelog replaced the removed
`--full-auto` flag with `--sandbox workspace-write`:
https://learn.chatgpt.com/docs/changelog
This selects the workspace sandbox without enabling automatic approval review or bypassing
permissions. An explicit --sandbox/-s option in extra_args replaces the default. Argument
contracts are tested with injected runners/stubs, never a live model dispatch. If current CLI
documentation contradicts this contract, report the mismatch rather than guessing a flag.

Central assignment and recovery policy lives in `bin/codex_policy.py` and reads only
`data/pricing.codex.json`. Ordinary task pins resolve within the configured cheap/mid/strong
worker tiers; a missing legacy pin uses the configured default worker, and a legacy frontier
pin migrates at dispatch to the maximum worker without rewriting the kit. Worker escalation
never enters the reserved orchestration tier. Only driver-observed failed dispatch/verify
attempts can unlock one scoped Astra recovery attempt. Review uses the configured independent
verification worker, while `accept` uses the orchestrator in a read-only acceptance role.
The sequential driver has no warm-agent pool, so Astra is represented as a reserved target and
is instantiated only for orchestration, acceptance, or evidence-gated recovery.

Every dispatch requests Codex JSON output. When that output provides a thread id, the production
runner correlates it to a fresh rollout `turn_context` before recording an observed model;
otherwise actual model/role stay `unknown`. Planned, dispatched, and observed fields are never
collapsed. Model ids, availability, effort levels, and prices are never hardcoded here.

Dispatch stays strictly SEQUENTIAL (PLAN D5) — one task, one dispatch, one verify, at a time;
no fan-out, no concurrency. This was cut from scope deliberately: fan-out on a paid/
quota-limited harness only buys wall-clock time while multiplying real spend, and this kit's
priority is accuracy and cost, not speed. `run_task` below issues its dispatches in a
single-threaded loop and never spawns more than one `runner`/`verify_runner` call in flight.

Id stamping + lineage (T1 grammar — graph-convergence's outcome-line extension, PLAN D8; ported
here in shape from `bin/copilot_execute.py`'s T7, the grammar template per its own docstring):
`cmd_run` generates ONE `run=<UTC-date>-<4 hex>` id per invocation (`generate_run_id`,
content-free — no hostname, username, pid, or path fragment) and:
  * embeds `[kit=<slug> run=<run id> task=<task id>]` as a bracketed preamble line at the FRONT
    of the dispatch prompt sent to `codex exec` — the codex analogue of T7's dispatch preamble
    (visible in `--dry-run`'s printed argv). A bare call to `run_task`/`build_dispatch` with no
    `prompt` supplied dispatches exactly what it always has (PLAN D6 — `run_task` falls back to
    the raw `task["brief"]`); `cmd_run` itself always supplies ids on a real or dry-run `run`
    invocation, the same "always on at the CLI, optional at the function level" shape T7
    established for `copilot_execute.py`.
  * stamps `run=` on the ONE `outcome:` ledger line the invocation writes (every outcome line,
    a clean pass included — Phase 1 review F1's resolved reading).
  * accepts an explicit `--parent TASK_ID` flag: this run of the SELECTED task is itself a
    consult spawned to rescue a DIFFERENT, already-blocked task. Because the escalation ladder
    here walks tiers for a SINGLE task id, an in-ladder escalation has no second id to name —
    `--parent` is the only way to write the lineage grammar's `parent=` field (same shape as
    `bin/copilot_execute.py`'s T7 flag and `bin/claude_execute.py`'s T5 flag; the acceptance
    bullet "escalation outcomes carry parent=" is otherwise unsatisfiable, a brief defect T5
    recorded first and T7/T8 inherit rather than re-deriving). `--parent` equal to the task
    actually being run is REJECTED at the writer (exit 2, nothing written, nothing dispatched)
    — `bin/routing_scorecard.py` drops a self-referencing `parent=` with a note while still
    counting the `escalated-pass` it caused, so writing one would put a single line into a
    headline figure and into the "ignored" list at once (Phase 1 review's F2 invariant; Phase 2
    review's F-E finding against an earlier driver that shipped without this guard). `parent=`
    is written ONLY on an escalation result (`PARENT_RESULTS`): a run given `--parent` that ends
    BLOCKED writes NO `parent=`, because the reader rejects that placement as out of grammar
    while still counting the result it classified — the same F2 invariant from the writer side
    (Phases 3-4 review's P34-F2).

Budget dial (T9 -- see the "PLAN.md budget dial" section below for the full contract): an
OPTIONAL `budget: max-dispatches=N max-escalations=N max-consults=N` line in the kit's
PLAN.md, checked against NOTES.md's own recorded history before `cmd_run` dispatches anything.
On a cap already reached, the task is left untouched and ONE `outcome: ... result=budget-stop`
line is written instead -- no new CLI flag, absent block = today's behavior. The one case where
that line is NOT written: the task already carries a recorded `result=` of its own. A
budget-stop is not a verdict and must never displace one (`recorded_outcome_result`).

Usage:
    codex_execute.py status --kit DIR [--json]
    codex_execute.py run --kit DIR [--task ID] [--role NAME] [--codex-bin BIN]
                     [--effort E] [--max-escalations N] [--extra-arg X ...]
                     [--parent TASK_ID] [--dry-run]
    codex_execute.py review --kit DIR --phase N [--codex-bin BIN]
                     [--extra-arg X ...] [--dry-run]
"""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PRICING_PATH = REPO_ROOT / "data" / "pricing.codex.json"
PLACEHOLDER = "{{POLYTROPOS_ROOT}}"

TIER_ORDER = ("cheap", "mid", "strong", "frontier")
STATUSES = ("pending", "in-progress", "done", "blocked")
DEFAULT_ESCALATION_START = "mid"

EM_DASH = " — "  # spaced em dash — the required task-heading separator

# Load the adjacent policy module without relying on bin/ being a package or on cwd/sys.path.
_POLICY_SPEC = importlib.util.spec_from_file_location(
    "polytropos_codex_policy", Path(__file__).resolve().with_name("codex_policy.py")
)
_POLICY = importlib.util.module_from_spec(_POLICY_SPEC)
_POLICY_SPEC.loader.exec_module(_POLICY)
PolicyError = _POLICY.PolicyError
resolve_assignment = _POLICY.resolve_assignment
resolve_orchestrator = _POLICY.resolve_orchestrator
worker_ladder = _POLICY.worker_ladder


def load_pricing():
    """Load the Codex pricing dict (plain json.load; this driver does not import codex_pricing)."""
    with open(PRICING_PATH) as f:
        return json.load(f)


# ---- parsing --------------------------------------------------------------------------------

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


def _parse_block(task_id, title, block):
    status = None
    model = None
    depends = []
    independent = False
    for line in block.splitlines():
        s = line.strip()
        if status is None and s.startswith("- status:"):
            status = s[len("- status:"):].strip()
        elif model is None and s.startswith("- model:"):
            value = s[len("- model:"):].strip()
            model = value or None
        elif s.startswith("- depends:"):
            depends = _parse_depends(s[len("- depends:"):])
        elif s.startswith("- independent:"):
            independent = s[len("- independent:"):].strip().lower() == "yes"
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
        "brief": _extract_brief(block),
        "verify": _extract_verify(block),
    }


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


# ---- tier resolution (D4 skip-up rule, implemented locally — see module docstring) ----------

def resolve_tier(pricing, tier):
    """Resolve an ordinary worker tier; reserved frontier migrates to the maximum worker."""
    try:
        return resolve_assignment(pricing, planned_model=tier, role="implementer")["model_id"]
    except PolicyError as exc:
        raise KeyError(str(exc)) from exc


def resolve_model(pricing, model_or_tier):
    """Resolve an ordinary implementation assignment; never return the orchestrator."""
    try:
        return resolve_assignment(
            pricing, planned_model=model_or_tier, role="implementer"
        )["model_id"]
    except PolicyError as exc:
        raise KeyError(str(exc)) from exc


# ---- role preambles (replace Copilot's --agent; PLAN.md D7 item 2) --------------------------

def _strip_frontmatter(text):
    """Drop a leading `---`-delimited YAML frontmatter block, if present; return the body."""
    lines = text.splitlines(keepends=True)
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "".join(lines[i + 1:])
    return text


def load_preamble(role, repo_root=None):
    """Read `<repo_root>/codex/prompts/<role>.md`, strip frontmatter, resolve the placeholder.

    `{{POLYTROPOS_ROOT}}` is resolved to `str(repo_root)` IN MEMORY only — the bundle
    file on disk is never rewritten. Returns the role's prompt body, ready to prepend to a task
    brief. Missing role file -> FileNotFoundError naming the expected path.
    """
    if repo_root is None:
        repo_root = REPO_ROOT
    repo_root = Path(repo_root)
    path = repo_root / "codex" / "prompts" / f"{role}.md"
    if not path.exists():
        raise FileNotFoundError(f"no role prompt at {path}")
    body = _strip_frontmatter(path.read_text())
    return body.replace(PLACEHOLDER, str(repo_root)).strip()


# ---- dispatch + escalation ------------------------------------------------------------------

def build_dispatch(codex_bin, model_id, prompt, effort=None, extra_args=()):
    """Build the `codex exec` dispatch argv LIST (never a joined string; never shell=True).

    [codex_bin, "exec"] + (["--model", model_id] if model_id else [])
        + (["--sandbox", "workspace-write"] unless extra_args already selects a sandbox)
        + (["-c", "model_reasoning_effort=" + effort] if effort else [])
        + list(extra_args) + [prompt]

    The workspace sandbox is not an unrestricted permission grant. Approval policy remains
    with the CLI configuration; --approve-for-me is not enabled implicitly. A model_id of
    None omits --model so the user's configured Codex default applies. --effort/--extra-arg
    supply reasoning effort and explicit CLI options. Do not probe the CLI from this builder.
    """
    extra_args = list(extra_args)
    _validate_extra_args(extra_args)
    argv = [codex_bin, "exec"]
    if "--json" not in extra_args:
        argv.append("--json")
    if model_id:
        argv += ["--model", model_id]
    # The short form also accepts an attached value: -sread-only or -s=read-only.
    has_sandbox = any(
        arg == "--sandbox" or arg.startswith("--sandbox=") or arg.startswith("-s")
        for arg in extra_args
    )
    if not has_sandbox:
        argv += ["--sandbox", "workspace-write"]
    if effort:
        argv += ["-c", "model_reasoning_effort=" + effort]
    argv += extra_args
    argv += [prompt]
    return argv


def _validate_extra_args(extra_args):
    """Reject options that could override the policy-selected model or profile."""
    blocked_flags = {
        "--model", "-m", "--profile", "-p", "--config", "-c",
        "--dangerously-bypass-approvals-and-sandbox", "--yolo", "--full-auto",
        "--approve-for-me",
    }
    for arg in extra_args:
        if arg in blocked_flags:
            raise PolicyError(f"extra dispatch option {arg!r} may override routing policy")
        if arg.startswith(("--model=", "--profile=", "--config=", "-m", "-p", "-c")):
            raise PolicyError(f"extra dispatch option {arg!r} may override routing policy")


def escalation_ladder(pricing, model_id=None):
    """Return higher eligible workers only; never include reserved orchestration."""
    try:
        start = resolve_model(pricing, model_id)
        return worker_ladder(pricing, start)
    except (PolicyError, KeyError) as exc:
        raise KeyError(str(exc)) from exc


# ---- run ids (PLAN D8 -- content-free, one per driver invocation) -----------------------------

def generate_run_id(now=None):
    """One content-free `run=` id per driver invocation: `<UTC-date>-<4 hex>` (PLAN D8).

    Ported verbatim in shape from `bin/copilot_execute.py`'s T7 function (itself ported from
    `bin/claude_execute.py`'s T5 -- the resolved, reviewed design for this exact requirement;
    PLAN D8 pins the format, T8 inherits it rather than re-deriving it). `secrets.token_hex(2)`
    supplies the four hex characters from 2 cryptographically random bytes -- never a hostname,
    username, pid, or path fragment (NOTES.md is committed in consumer repos, so nothing
    content-bearing may enter it). `now` is injectable so tests can pin the date segment
    without touching wall-clock time; the hex segment is always freshly random.
    """
    now = now or datetime.now(timezone.utc)
    return f"{now.strftime('%Y-%m-%d')}-{secrets.token_hex(2)}"


def build_id_preamble(kit=None, run_id=None, task_id=None):
    """One bracketed lineage line, e.g. `[kit=fixturekit run=2026-07-26-9f3a task=T1]`, or
    `""` when none of the three ids are given (PLAN D6 — purely additive). Only the ids
    actually supplied appear; the bracket is omitted entirely rather than printed empty.
    Ported verbatim in shape from `bin/copilot_execute.py`'s T7 function."""
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


# ---- outcome ledger (T1 grammar: run=/parent=) -------------------------------------------------

def outcome_result(status, escalations, parent):
    """Classify a finished `run_task` result into the T1 `result=` vocabulary.

    `blocked` when the task never passed. Otherwise `escalated-pass` when the ladder needed a
    rung beyond the task's own pinned tier (`escalations` non-empty) OR this run was itself a
    consult for a different task (`parent` given). Otherwise plain `pass`. Ported verbatim in
    shape from `bin/copilot_execute.py`'s T7 function.
    """
    if status != "done":
        return "blocked"
    if escalations or parent:
        return "escalated-pass"
    return "pass"


# The `result=` values a `parent=` field may ride on. `bin/routing_scorecard.py`'s
# `build_lineage` keeps a `parent=` ONLY when the carrying outcome's own result is
# `escalated-pass` and drops any other placement with an "out of grammar, ignored" note --
# while `outcome_result` above still classifies that same line, so a rejected `parent=` would
# put one line into a headline figure and into the "ignored" list at once (Phase 1 review's F2
# invariant). `append_note` therefore OMITS `parent=` on any other result rather than writing a
# line the reader rejects. Identical rule in all three drivers (PLAN D1).
PARENT_RESULTS = ("escalated-pass",)


def build_outcome_line(task_id, model, attempts, result, review="none", run_id=None,
                        parent=None):
    """One `outcome:` ledger line (T1 grammar). `model` must be a non-whitespace token --
    callers pass `"unpinned"` (never a phrase with a space) for a task with no model pin, so
    the line still parses under `routing_scorecard.PAIR_RE` (`\\w+=\\S+`). Ported verbatim in
    shape from `bin/copilot_execute.py`'s T7 function."""
    line = (
        f"outcome: {task_id} model={model} attempts={attempts} "
        f"result={result} review={review}"
    )
    if run_id:
        line += f" run={run_id}"
    if parent:
        line += f" parent={parent}"
    return line


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
# driver imports neither another driver nor `codex_pricing`/`routing_scorecard` for this, so the
# shape is duplicated, not shared, on purpose (matches the tier-resolution precedent above).
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
PLAN_BUDGET_KEYS = ("max-dispatches", "max-escalations", "max-consults")


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
    budget = dict(re.findall(r"(max-dispatches|max-escalations|max-consults)=(\d+)", m.group(1)))
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
        used["max-escalations"] += max(attempts - 1, 0)
        if re.search(r"(?:^|\s)parent=\S+", s):
            used["max-consults"] += 1
    return used


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


def plan_budget_exhausted(plan_budget, used, is_consult):
    """The first `PLAN_BUDGET_KEYS` cap already reached by `used`, or `None`.

    A cap is "reached" at `used[key] >= cap` -- the recorded usage already consumed the last
    unit the budget allowed, so the task in front of this call must not add one more.
    `max-consults` is checked ONLY when `is_consult` is true (this run carries `--parent`): a
    plain (non-consult) run never trips on a consult cap, and a budget with no `max-consults`
    key never trips regardless of `is_consult`. Checked in `PLAN_BUDGET_KEYS` order, so
    `max-dispatches` wins ties over `max-escalations`/`max-consults` when more than one cap is
    simultaneously exhausted -- an arbitrary but stable and reproducible choice.
    """
    for key in PLAN_BUDGET_KEYS:
        cap = plan_budget.get(key)
        if cap is None:
            continue
        if key == "max-consults" and not is_consult:
            continue
        if used.get(key, 0) >= cap:
            return key
    return None


def append_plan_budget_stop_note(notes_path, task, run_id, exhausted_key, cap, used, remaining,
                                  role):
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
    notes_path = Path(notes_path)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    task_id = task["id"]
    model_label = task.get("model") or "unpinned"
    block_lines = [
        f"## {ts}{EM_DASH}{task_id}",
        f"- role: {role}",
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


def run_task(task, pricing, runner, verify_runner, prompt=None, role="implementer",
             max_escalations=None, codex_bin="codex", effort=None, extra_args=(),
             allow_recovery=True):
    """Orchestrate one task: dispatch, verify, escalate up the tier ladder on failure.

    `runner(argv) -> (returncode, output)` and `verify_runner(cmd) -> (returncode, output)`
    are injected callables (the quota-safety seam — never construct a real command in tests).
    `prompt` is the full dispatch text (a role preamble + the task brief); if None it falls
    back to the raw brief.

    Flow: resolve through the central policy, dispatch to a worker, and verify only after a
    successful dispatch. Failures walk the configured worker ladder. If those workers exhaust,
    structured driver-observed evidence unlocks one reserved orchestrator recovery attempt.
    Verification roles never enter implementation escalation or recovery.

    Returns status plus planned assignment, per-attempt dispatched/observed usage, worker
    escalations, verification result, and the recovery audit when recovery occurred.
    """
    if prompt is None:
        prompt = task["brief"]
    verify_cmd = task.get("verify")
    if not isinstance(verify_cmd, str) or not verify_cmd.strip():
        raise PolicyError(f"task {task.get('id')!r} has no runnable verify command")
    if max_escalations is not None and max_escalations < 0:
        raise PolicyError("max_escalations must be non-negative")
    assignment = resolve_assignment(pricing, task.get("model"), role=role)
    model_id = assignment["model_id"]
    escalations = []
    model_used = model_id
    attempts = []

    def validate_model_effort(chosen_model):
        supported = pricing.get("models", {}).get(chosen_model, {}).get(
            "supported_reasoning_efforts"
        )
        if effort is not None and supported is not None and effort not in supported:
            raise PolicyError(
                f"model {chosen_model!r} does not support effort {effort!r}; valid: "
                f"{', '.join(supported)}"
            )

    candidate_ladder = (
        worker_ladder(pricing, model_id)
        if assignment["resolved_role"] == "implementer" else []
    )
    if max_escalations is not None:
        candidate_ladder = candidate_ladder[:max_escalations]
    preflight_models = [model_id, *candidate_ladder]
    recovery_allowed_by_cap = max_escalations is None or len(candidate_ladder) < max_escalations
    if assignment["resolved_role"] == "implementer" and allow_recovery and recovery_allowed_by_cap:
        preflight_models.append(resolve_orchestrator(pricing))
    for candidate in preflight_models:
        validate_model_effort(candidate)

    def dispatch_and_verify(chosen_model, chosen_role, dispatch_prompt):
        validate_model_effort(chosen_model)
        argv = build_dispatch(
            codex_bin, chosen_model, dispatch_prompt, effort=effort, extra_args=extra_args
        )
        try:
            raw = runner(argv)
        except OSError as exc:
            raw = (126, f"dispatch failed: {exc}")
        if raw is None:  # Backward-compatible injected runner seam.
            dispatch_rc, dispatch_output, telemetry = 0, "", {}
        elif len(raw) == 3:
            dispatch_rc, dispatch_output, telemetry = raw
        else:
            dispatch_rc, dispatch_output = raw
            telemetry = {}
        observed_model = telemetry.get("actual_model") if isinstance(telemetry, dict) else None
        observed_role = telemetry.get("actual_role") if isinstance(telemetry, dict) else None
        observed_provenance = telemetry.get("provenance") if isinstance(telemetry, dict) else None
        mismatch = ((observed_model is not None and observed_model != chosen_model) or
                    (observed_role is not None and observed_role != chosen_role))
        if mismatch:
            effective_rc, verify_rc = 3, None
            verify_output = (
                f"runtime attestation disagrees with policy assignment: expected "
                f"{chosen_model}/{chosen_role}, observed {observed_model}/{observed_role}"
            )
            attempt_result = "policy-mismatch"
        elif dispatch_rc != 0:
            effective_rc, verify_rc, verify_output = dispatch_rc, None, dispatch_output
            attempt_result = "dispatch-failed"
        else:
            try:
                verify_rc, verify_output = verify_runner(verify_cmd)
            except OSError as exc:
                verify_rc, verify_output = 126, f"verify failed to start: {exc}"
            effective_rc = verify_rc
            attempt_result = "passed" if verify_rc == 0 else "verify-failed"
        attempts.append({
            "planned_model": task.get("model"),
            "dispatched_model": chosen_model,
            "dispatched_role": chosen_role,
            "actual_model": observed_model,
            "actual_role": observed_role,
            "actual_provenance": observed_provenance,
            "dispatch_exit_code": dispatch_rc,
            "verify_exit_code": verify_rc,
            "result": attempt_result,
            "failure_digest": " ".join((verify_output or "").split())[-500:],
        })
        return effective_rc, verify_output

    rc, output = dispatch_and_verify(model_id, assignment["resolved_role"], prompt)

    policy_violation = attempts[-1]["result"] == "policy-mismatch"
    if rc != 0 and assignment["resolved_role"] == "implementer" and not policy_violation:
        ladder = candidate_ladder
        for rung in ladder:
            escalated_prompt = prompt + _evidence(verify_cmd, rc, output)
            escalations.append(rung)
            model_used = rung
            rc, output = dispatch_and_verify(rung, "implementer", escalated_prompt)
            if attempts[-1]["result"] == "policy-mismatch":
                policy_violation = True
                break
            if rc == 0:
                break

    recovery = None
    if (rc != 0 and assignment["resolved_role"] == "implementer" and allow_recovery
            and recovery_allowed_by_cap and not policy_violation):
        evidence_kind = (
            "lower_tier_correction_failed"
            if attempts[-1]["verify_exit_code"] is None else "verify_failure"
        )
        evidence = {
            "kind": evidence_kind,
            "task_id": task["id"],
            "attempts": [
                {
                    "dispatched_model": a["dispatched_model"],
                    "dispatched_role": a["dispatched_role"],
                    "actual_model": a["actual_model"],
                    "actual_role": a["actual_role"],
                    "actual_provenance": a["actual_provenance"],
                    "result": "failed" if a["result"] != "passed" else "passed",
                    "verify_exit_code": a["verify_exit_code"],
                    "dispatch_exit_code": a["dispatch_exit_code"],
                    "failure_digest": a["failure_digest"],
                }
                for a in attempts
            ],
            "correction_scope": task.get("brief", ""),
            "verify_command": verify_cmd,
            "failure_digest": attempts[-1]["failure_digest"],
        }
        if evidence_kind == "verify_failure":
            evidence["verify_exit_code"] = rc
        recovery_assignment = resolve_assignment(
            pricing, role="recovery", evidence=evidence
        )
        recovery_prompt = prompt + _evidence(verify_cmd, rc, output)
        recovery_prompt += (
            "\n\n--- RESERVED ORCHESTRATOR RECOVERY ---\n"
            "Correct only the documented failure. Return implementation work to the cheapest "
            "sufficient worker after this attempt.\n"
        )
        model_used = recovery_assignment["model_id"]
        rc, output = dispatch_and_verify(model_used, "recovery", recovery_prompt)
        recovery = {
            "failure_evidence": evidence,
            "prior_attempts": evidence["attempts"],
            "correction_scope": evidence["correction_scope"],
            "verification_result": {
                "dispatch_exit_code": attempts[-1]["dispatch_exit_code"],
                "verify_exit_code": attempts[-1]["verify_exit_code"],
                "passed": rc == 0,
            },
        }

    return {
        "id": task["id"],
        "status": "done" if rc == 0 else "blocked",
        "model_used": model_used,
        "escalations": escalations,
        "verify_rc": rc,
        "planned_model": task.get("model"),
        "assignment": assignment,
        "attempts": attempts,
        "recovery": recovery,
    }


def append_note(notes_path, result, task, run_id=None, parent=None):
    """Append a run block to the kit's NOTES.md (created if missing).

    Block: `## <UTC ISO timestamp> — <task id>` then bullet lines for role, model used (or
    `codex default`), escalation chain (`(none)` when empty), and `verify: exit <rc>`. Only
    when escalations occurred, a further `lesson-candidate (routing): ...` line. Finally ONE
    machine-readable `outcome:` ledger line is ALWAYS appended (T1 grammar,
    `build_outcome_line` above -- ported in shape from `bin/copilot_execute.py`'s T7
    `append_note`), carrying `run=` only when `run_id` is given and `parent=` only when
    `parent` is given AND the classified result is in `PARENT_RESULTS` -- both fields are
    optional on the LINE (PLAN D6: an old ledger entry, or a call site that supplies neither,
    still parses fine), but `cmd_run` below always generates and passes a `run_id`, so every
    line this driver's `run` subcommand actually writes carries one.

    A `parent` supplied for a run that ends BLOCKED is silently omitted from the line (not an
    error, not a stdout warning -- a consult that failed is legitimate, and stdout here is
    machine-read): the reader restricts `parent=` to escalation results, so writing it would
    emit a line it reports as ignored while still counting the classification it caused. See
    `PARENT_RESULTS` above.
    """
    notes_path = Path(notes_path)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    task_id = task["id"]
    role = result.get("role", "implementer")
    model_used = result.get("model_used")
    model_used_label = model_used if model_used else "codex default"
    escalations = result.get("escalations") or []
    chain = " -> ".join(escalations) if escalations else "(none)"
    rc = result.get("verify_rc")

    block_lines = [
        f"## {ts}{EM_DASH}{task_id}",
        f"- role: {role}",
        f"- planned model: {result.get('planned_model') or 'legacy-unpinned'}",
        f"- model used: {model_used_label}",
        f"- escalations: {chain}",
        f"- verify: exit {rc}",
    ]
    for index, attempt in enumerate(result.get("attempts") or [], 1):
        block_lines.append(
            f"- actual-use: attempt={index} planned={attempt.get('planned_model') or 'unpinned'} "
            f"dispatched_model={attempt['dispatched_model']} "
            f"dispatched_role={attempt['dispatched_role']} "
            f"actual_model={attempt.get('actual_model') or 'unknown'} "
            f"actual_role={attempt.get('actual_role') or 'unknown'} "
            f"actual_provenance={attempt.get('actual_provenance') or 'none'} "
            f"dispatch_exit={attempt['dispatch_exit_code']} "
            f"verify_exit={attempt['verify_exit_code']} result={attempt['result']}"
        )
    recovery = result.get("recovery")
    if recovery:
        evidence = recovery["failure_evidence"]
        scope = " ".join((recovery["correction_scope"] or "").split())
        digest = " ".join((evidence.get("failure_digest") or "").split())
        block_lines += [
            f"- recovery evidence: kind={evidence['kind']} "
            f"verify_command={evidence.get('verify_command')!r} "
            f"verify_exit={evidence.get('verify_exit_code', 'not-run')} digest={digest}",
            f"- recovery prior attempts: {len(recovery['prior_attempts'])}",
            f"- recovery correction scope: {scope}",
            f"- recovery verification: dispatch_exit="
            f"{recovery['verification_result']['dispatch_exit_code']} verify_exit="
            f"{recovery['verification_result']['verify_exit_code']} "
            f"passed={str(recovery['verification_result']['passed']).lower()}",
        ]
    if escalations:
        pinned = task.get("model") or "codex default"
        block_lines.append(
            f"lesson-candidate (routing): task {task_id} pinned {pinned} but needed "
            f"{model_used_label} — record via the lessons-loop skill."
        )

    attempts = len(result.get("attempts") or []) or (1 + len(escalations))
    outcome_model = model_used if model_used else "unpinned"
    result_word = outcome_result(result.get("status"), escalations, parent)
    if recovery and result_word == "pass":
        result_word = "escalated-pass"
    line_parent = parent if result_word in PARENT_RESULTS else None
    block_lines.append(
        "- " + build_outcome_line(
            task_id, outcome_model, attempts, result_word, run_id=run_id, parent=line_parent
        )
    )

    block = "\n".join(block_lines) + "\n"

    existing = notes_path.read_text() if notes_path.exists() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    separator = "\n" if existing.strip() else ""
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    notes_path.write_text(existing + separator + block)


# ---- default runners (module level, injectable everywhere) ----------------------------------

def default_runner(argv):
    """Dispatch runner for real runs: `subprocess.run(argv, ...)` -> (rc, stdout+stderr).

    !!! Invoking this with a real `codex` argv spends the user's real subscription usage
    limits / API dollars and hits the network. !!!
    """
    started = datetime.now(timezone.utc)
    proc = subprocess.run(argv, capture_output=True, text=True)
    output = (proc.stdout or "") + (proc.stderr or "")
    telemetry = attest_runtime_model(output, started)
    return proc.returncode, output, telemetry


def attest_runtime_model(output, started, codex_root=None):
    """Correlate this dispatch's JSON thread id to a fresh rollout turn_context model.

    Free-form output is never trusted as model evidence. If the CLI or rollout does not expose
    a correlated structured record, the caller records actual_model=unknown.
    """
    thread_id = None
    for line in (output or "").splitlines():
        try:
            event = json.loads(line)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(event, dict) and event.get("type") == "thread.started" and isinstance(event.get("thread_id"), str):
            thread_id = event["thread_id"]
    if not thread_id:
        return {}
    if not re.fullmatch(r"[A-Za-z0-9-]+", thread_id):
        return {}
    configured_root = os.environ.get("CODEX_HOME")
    root = (Path(codex_root) if codex_root is not None else
            Path(configured_root) if configured_root else Path.home() / ".codex")
    sessions = root / "sessions"
    if not sessions.is_dir():
        return {}
    try:
        candidates = list(sessions.rglob(f"*{thread_id}*.jsonl"))
    except OSError:
        return {}
    if len(candidates) != 1:
        return {}
    observed = None
    try:
        lines = candidates[0].read_text(errors="replace").splitlines()
    except OSError:
        return {}
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        try:
            stamp = datetime.fromisoformat(record.get("timestamp", "").replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError):
            continue
        if stamp.astimezone(timezone.utc) < started.astimezone(timezone.utc):
            continue
        payload = record.get("payload")
        if record.get("type") == "turn_context" and isinstance(payload, dict):
            model = payload.get("model")
            if isinstance(model, str) and model:
                observed = model
    return {"actual_model": observed, "provenance": "correlated-rollout-turn_context"} if observed else {}


def default_verify_runner(cmd):
    """Verify runner for real runs: shell out (verify commands are repo-authored shell lines).

    Same trust model as the kit contract: `subprocess.run(cmd, shell=True, ...)`.
    """
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def append_role_use(notes_path, phase, role, planned_model, dispatched_model, dispatch_rc,
                    actual_model=None, actual_role=None, result=None, evidence_fingerprint=None,
                    report=None):
    """Record a non-task review/acceptance dispatch without claiming requested=observed."""
    notes_path = Path(notes_path)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report_text = " ".join((report or "").split())[-2000:]
    report_digest = hashlib.sha256((report or "").encode()).hexdigest() if report is not None else None
    block = (
        f"## {ts}{EM_DASH}phase-{phase}-{role}\n"
        f"- actual-use: planned={planned_model or 'policy'} dispatched_model={dispatched_model} "
        f"dispatched_role={role} actual_model={actual_model or 'unknown'} "
        f"actual_role={actual_role or 'unknown'} dispatch_exit={dispatch_rc}"
        f"{f' result={result}' if result else ''}\n"
    )
    if evidence_fingerprint:
        block += f"- evidence-fingerprint: {evidence_fingerprint}\n"
    if report is not None:
        block += f"- report-sha256: {report_digest}\n- report: {report_text or '(empty)'}\n"
    existing = notes_path.read_text() if notes_path.exists() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    notes_path.write_text(existing + ("\n" if existing.strip() else "") + block)


def enforce_attested_assignment(rc, output, telemetry, expected_model, expected_role):
    actual_model = telemetry.get("actual_model")
    actual_role = telemetry.get("actual_role")
    mismatch = ((actual_model is not None and actual_model != expected_model) or
                (actual_role is not None and actual_role != expected_role))
    if mismatch:
        return 3, output + (
            f"\npolicy mismatch: expected {expected_model}/{expected_role}, observed "
            f"{actual_model}/{actual_role}\n"
        )
    return rc, output


def parse_acceptance_verdict(output):
    matches = re.findall(r"POLYTROPOS_ACCEPTANCE:\s*(accepted|rejected)\b", output or "")
    return matches[-1] if matches else None


# ---- CLI ------------------------------------------------------------------------------------

def _read_tasks_text(kit_dir):
    path = Path(kit_dir) / "TASKS.md"
    if not path.exists():
        raise FileNotFoundError(f"no TASKS.md under kit dir {kit_dir}")
    return path.read_text()


def _phase_tasks(tasks_text, phase):
    """Return parsed tasks bounded by one exact Phase heading."""
    match = re.search(
        rf"^## Phase {re.escape(str(phase))}(?:\s|—|-).*?(?=^## Phase |\Z)",
        tasks_text, re.MULTILINE | re.DOTALL,
    )
    return parse_tasks(match.group(0)) if match else []


def review_evidence_fingerprint(kit, tasks_text, phase):
    """Hash the reviewed phase and git workspace, excluding the append-only kit NOTES file."""
    match = re.search(
        rf"^## Phase {re.escape(str(phase))}(?:\s|—|-).*?(?=^## Phase |\Z)",
        tasks_text, re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise PolicyError(f"phase {phase!r} has no tasks")
    kit = Path(kit).resolve()
    probe = subprocess.run(
        ["git", "-C", str(kit), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    )
    if probe.returncode != 0:
        raise PolicyError("final acceptance requires a git workspace to prove review freshness")
    root = Path(probe.stdout.strip()).resolve()
    head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True,
    )
    if head.returncode != 0:
        raise PolicyError("final acceptance requires a committed HEAD for review freshness")
    notes = (kit / "NOTES.md").resolve()
    try:
        notes_rel = notes.relative_to(root).as_posix()
    except ValueError:
        notes_rel = None
    exclude = [f":(exclude){notes_rel}"] if notes_rel else []
    diff = subprocess.run(
        ["git", "-C", str(root), "diff", "--binary", "--no-ext-diff", "HEAD", "--", ".", *exclude],
        capture_output=True,
    )
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        capture_output=True,
    )
    if diff.returncode != 0 or status.returncode != 0:
        raise PolicyError("could not fingerprint workspace for review freshness")
    untracked = []
    for entry in status.stdout.split(b"\0"):
        if not entry.startswith(b"?? "):
            continue
        rel = entry[3:].decode(errors="surrogateescape")
        if notes_rel and rel == notes_rel:
            continue
        path = root / rel
        try:
            untracked.append(rel.encode() + b"\0" + path.read_bytes())
        except OSError as exc:
            raise PolicyError(f"could not fingerprint untracked file {rel}: {exc}") from exc
    plan_path = kit / "PLAN.md"
    try:
        plan_bytes = plan_path.read_bytes() if plan_path.exists() else b""
        notes_text = notes.read_text(errors="replace") if notes.exists() else ""
    except OSError as exc:
        raise PolicyError(f"could not read kit evidence for review freshness: {exc}") from exc
    task_note_blocks = []
    for block in notes_text.split("\n## "):
        first = block.splitlines()[0] if block.strip() else ""
        if re.search(r"phase-\S+-(?:verifier|orchestrator)", first):
            continue
        task_note_blocks.append(block)
    task_notes = "\n## ".join(task_note_blocks).encode()
    material = (head.stdout.strip() + b"\0" + plan_bytes + b"\0" + match.group(0).encode()
                + b"\0" + task_notes + b"\0" + diff.stdout + b"\0"
                + b"\0".join(untracked))
    return hashlib.sha256(material).hexdigest()


def _role_use_succeeded(notes_text, phase, role, evidence_fingerprint=None):
    marker = f"phase-{phase}-{role}"
    blocks = notes_text.split("\n## ")
    for block in reversed(blocks):
        if not block.strip() or marker not in block.splitlines()[0]:
            continue
        if evidence_fingerprint is not None:
            return ("dispatch_exit=0" in block and
                    f"evidence-fingerprint: {evidence_fingerprint}" in block)
        return "dispatch_exit=0" in block
    return False


def _acceptance_state(notes_text, phase, evidence_fingerprint=None):
    marker = f"phase-{phase}-orchestrator"
    for block in reversed(notes_text.split("\n## ")):
        if block.strip() and marker in block.splitlines()[0]:
            match = re.search(r"\bresult=(accepted|rejected)\b", block)
            if evidence_fingerprint and f"evidence-fingerprint: {evidence_fingerprint}" not in block:
                return "pending"
            return match.group(1) if match else "pending"
    return "pending"


def _select_task(tasks, task_id=None):
    if task_id is not None:
        for t in tasks:
            if t["id"] == task_id:
                status_by_id = {item["id"]: item["status"] for item in tasks}
                if not all(status_by_id.get(dep) == "done" for dep in t["depends"]):
                    return None
                return t
        return None
    status_by_id = {t["id"]: t["status"] for t in tasks}
    for t in tasks:
        if t["status"] == "pending" and all(
            status_by_id.get(dep) == "done" for dep in t["depends"]
        ):
            return t
    return None


def cmd_status(args):
    tasks_text = _read_tasks_text(args.kit)
    tasks = parse_tasks(tasks_text)
    pricing = load_pricing()
    orchestrator = resolve_orchestrator(pricing)
    enriched = []
    for task in tasks:
        try:
            assignment = resolve_assignment(pricing, task.get("model"), role="implementer")
            policy_fields = {"effective_model": assignment["model_id"],
                             "effective_role": assignment["resolved_role"],
                             "migration": assignment["migration"]}
        except PolicyError as exc:
            policy_fields = {"effective_model": None, "effective_role": None,
                             "migration": None, "policy_error": str(exc)}
        enriched.append({**task, **policy_fields})
    notes_path = Path(args.kit) / "NOTES.md"
    notes_text = notes_path.read_text() if notes_path.exists() else ""
    phases = re.findall(r"^## Phase (\S+)", tasks_text, re.MULTILINE)
    acceptance = {}
    for phase in phases:
        try:
            fingerprint = review_evidence_fingerprint(args.kit, tasks_text, phase)
        except PolicyError:
            fingerprint = None
        acceptance[phase] = (
            _acceptance_state(notes_text, phase, fingerprint) if fingerprint else "pending"
        )
    if args.json:
        print(json.dumps({"orchestration": {"model": orchestrator, "mode": "reserved",
                                           "ordinary_implementation": False},
                          "acceptance": acceptance, "tasks": enriched}, indent=2))
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
    print(f"orchestrator: {orchestrator} (reserved; recovery requires failure evidence)")
    for phase, state in acceptance.items():
        print(f"phase {phase} final acceptance: {state}")


def cmd_run(args):
    kit = Path(args.kit)
    slug = kit.name
    tasks_path = kit / "TASKS.md"
    text = _read_tasks_text(kit)
    tasks = parse_tasks(text)
    task = _select_task(tasks, args.task)
    if task is None:
        if args.task:
            requested = next((t for t in tasks if t["id"] == args.task), None)
            if requested:
                status_by_id = {t["id"]: t["status"] for t in tasks}
                missing = [d for d in requested["depends"] if status_by_id.get(d) != "done"]
                print(
                    f"task {args.task!r} is not eligible; unfinished dependencies: "
                    f"{', '.join(missing)}",
                    file=sys.stderr,
                )
            else:
                print(f"no task with id {args.task!r} in {tasks_path}", file=sys.stderr)
        else:
            print(
                f"no eligible pending task (all deps done) in {tasks_path}", file=sys.stderr
            )
        sys.exit(2)

    if args.role != "implementer":
        raise PolicyError(
            "kit run dispatches ordinary implementation only; use review for independent "
            "verification or accept for Astra final acceptance"
        )

    # One content-free `run=` id per invocation (T8, ported in shape from T7, PLAN D8) --
    # generated unconditionally (including under --dry-run, so the preview shows the same id
    # preamble a real run would dispatch with) since generating a random hex string spawns
    # nothing and costs nothing.
    run_id = generate_run_id()

    pricing = load_pricing()

    if not task.get("verify"):
        raise PolicyError(f"task {task['id']!r} has no runnable verify command")
    if args.max_escalations is not None and args.max_escalations < 0:
        raise PolicyError("--max-escalations must be non-negative")

    if args.effort is not None:
        efforts = pricing.get("knobs", {}).get("reasoning_efforts", [])
        if args.effort not in efforts:
            print(
                f"unknown effort {args.effort!r}; valid: {', '.join(efforts)}", file=sys.stderr
            )
            sys.exit(2)

    extra_args = tuple(args.extra_arg or ())
    preamble = load_preamble(args.role, REPO_ROOT)
    prompt = preamble + "\n\n---\n\n" + task["brief"]
    # T8 id-lineage preamble (PLAN D8/T7, ported in shape) -- prefixed ahead of the role
    # preamble; `kit`/`run_id`/`task_id` are always given here, so this is non-empty on every
    # real `cmd_run` invocation (same "always on at the CLI" shape T7 established for
    # `copilot_execute.py`). `build_id_preamble`/`run_task` remain byte-identical when called
    # directly without ids (PLAN D6).
    id_preamble = build_id_preamble(kit=slug, run_id=run_id, task_id=task["id"])
    if id_preamble:
        prompt = f"{id_preamble}\n\n{prompt}"
    assignment = resolve_assignment(pricing, task["model"], role="implementer")
    model_id = assignment["model_id"]

    if args.dry_run:
        argv = build_dispatch(
            args.codex_bin, model_id, prompt, effort=args.effort, extra_args=extra_args
        )
        print(f"task: {task['id']}")
        print(f"policy: role={assignment['resolved_role']} planned={task['model'] or 'unpinned'} "
              f"dispatched={model_id} migration={assignment['migration'] or 'none'}")
        print(f"orchestrator: {resolve_orchestrator(pricing)} (reserved recovery target)")
        print(f"dispatch: {shlex.join(argv)}")
        print(f"verify: {task['verify']}")
        return

    # A task is never its own parent. `bin/routing_scorecard.py` DROPS a self-referencing
    # `parent=` with a note while still counting the `escalated-pass` that `parent=` caused
    # (see `outcome_result`) -- so writing one would put a line into a headline figure and into
    # the "ignored" list at once (Phase 1 review's F2 invariant; Phase 2 review's F-E finding
    # against an earlier driver that shipped without this guard). Rejected here at the WRITER,
    # before anything is written or dispatched.
    if args.parent and args.parent == task["id"]:
        print(
            f"--parent {args.parent!r} is the task being run -- a task cannot be its own "
            f"parent. `parent=` names a DIFFERENT, already-blocked task this run was spawned "
            f"to rescue; routing_scorecard ignores a self-referencing parent= while still "
            f"counting the escalated-pass it caused, so nothing may write one. Drop --parent "
            f"(an in-ladder escalation needs no lineage) or name the other task's id.",
            file=sys.stderr,
        )
        sys.exit(2)

    # PLAN.md budget dial (T9) -- checked against the kit's OWN recorded history before
    # anything is dispatched or written. `--dry-run` never reaches here (it returned above);
    # this gate only ever stops a REAL run. See the module's "PLAN.md budget dial" section.
    plan_path = kit / "PLAN.md"
    plan_budget = parse_plan_budget(plan_path.read_text()) if plan_path.exists() else None
    if plan_budget:
        notes_path = kit / "NOTES.md"
        notes_text = notes_path.read_text() if notes_path.exists() else ""
        used = count_plan_budget_usage(notes_text)
        exhausted_key = plan_budget_exhausted(plan_budget, used, is_consult=bool(args.parent))
        if exhausted_key:
            cap = plan_budget[exhausted_key]
            remaining = sum(1 for t in tasks if t["status"] == "pending")
            print(
                f"budget-stop: PLAN.md budget {exhausted_key}={cap} already reached "
                f"(used={used[exhausted_key]}) -- task {task['id']} was NOT dispatched; "
                f"{remaining} pending task(s) (including this one) left untouched. "
                f"See NOTES.md.",
                file=sys.stderr,
            )
            # A `budget-stop` is not a verdict, so it must never displace one. Re-running an
            # already-recorded task (resuming a `blocked` one is the natural gesture) after the
            # cap is spent reaches this gate BEFORE any status check, so without this guard the
            # driver would append a budget-stop line for a task id that already carries a real
            # `result=` -- and the reader's last-wins rule would drop the verdict and its
            # `failure=` class from the kit card and from `--history`. The reader now refuses to
            # be overwritten (`routing_scorecard.parse_outcomes`); this refuses to write the
            # line at all, so the ledger never carries a line the reader has to ignore.
            prior_result = recorded_outcome_result(notes_text, task["id"])
            if prior_result is not None and prior_result != "budget-stop":
                print(
                    f"budget-stop: NOT recorded in the ledger -- task {task['id']} already "
                    f"carries result={prior_result} and a budget-stop is not a verdict, so "
                    f"writing one would displace recorded evidence. The stop above still "
                    f"applies: nothing was dispatched.",
                    file=sys.stderr,
                )
            else:
                append_plan_budget_stop_note(
                    notes_path, task, run_id, exhausted_key, cap, used[exhausted_key],
                    remaining, role=args.role,
                )
            sys.exit(1)

    text = set_status(text, task["id"], "in-progress")
    tasks_path.write_text(text)

    result = run_task(
        task, pricing, default_runner, default_verify_runner,
        prompt=prompt, role=args.role, max_escalations=args.max_escalations,
        codex_bin=args.codex_bin, effort=args.effort, extra_args=extra_args,
    )

    text = set_status(text, task["id"], result["status"])
    tasks_path.write_text(text)

    result["role"] = args.role
    append_note(kit / "NOTES.md", result, task, run_id=run_id, parent=args.parent)

    escalations = result["escalations"] or "(none)"
    print(
        f"task {result['id']}: {result['status']} "
        f"(model_used={result['model_used'] or 'codex default'}, "
        f"escalations={escalations}, verify_rc={result['verify_rc']}, run={run_id})"
    )
    if result["status"] == "done":
        print("implementation complete; phase final acceptance remains pending until `accept`")
    if result["status"] == "blocked":
        sys.exit(1)


def cmd_review(args):
    tasks_text = _read_tasks_text(args.kit)
    phase_tasks = _phase_tasks(tasks_text, args.phase)
    if not phase_tasks:
        raise PolicyError(f"phase {args.phase!r} has no tasks")
    incomplete = [t["id"] for t in phase_tasks if t["status"] != "done"]
    if incomplete:
        raise PolicyError(
            f"phase {args.phase} is not ready for independent review; incomplete tasks: "
            f"{', '.join(incomplete)}"
        )
    evidence_fingerprint = review_evidence_fingerprint(args.kit, tasks_text, args.phase)
    pricing = load_pricing()
    assignment = resolve_assignment(pricing, role="independent_verifier")
    extra_args = tuple(args.extra_arg or ())
    if any(a == "--sandbox" or a.startswith(("--sandbox=", "-s")) for a in extra_args):
        raise PolicyError("review sandbox is fixed to read-only")
    extra_args = ("--sandbox", "read-only", *extra_args)
    preamble = load_preamble("reviewer", REPO_ROOT)
    body = (
        f"Review phase {args.phase} of the execution kit at {args.kit}. Read "
        f"{args.kit}/PLAN.md (goal, decisions, out-of-scope fence, tripwires) and the tasks "
        f"under '## Phase {args.phase}' in {args.kit}/TASKS.md, then review the actual changes "
        f"for drift, scope creep, and contract breakage. Report findings; change nothing."
    )
    prompt = preamble + "\n\n---\n\n" + body
    argv = build_dispatch(args.codex_bin, assignment["model_id"], prompt, extra_args=extra_args)
    if args.dry_run:
        print(f"phase: {args.phase}")
        print(f"dispatch: {shlex.join(argv)}")
        return
    rc, output, telemetry = default_runner(argv)
    rc, output = enforce_attested_assignment(
        rc, output, telemetry, assignment["model_id"], "verifier"
    )
    append_role_use(Path(args.kit) / "NOTES.md", args.phase, "verifier", None,
                    assignment["model_id"], rc, telemetry.get("actual_model"),
                    telemetry.get("actual_role"), evidence_fingerprint=evidence_fingerprint,
                    report=output)
    print(output)
    if rc != 0:
        sys.exit(1)


def cmd_accept(args):
    """Reserve Astra for final acceptance decisions without granting implementation scope."""
    tasks_text = _read_tasks_text(args.kit)
    phase_tasks = _phase_tasks(tasks_text, args.phase)
    if not phase_tasks:
        raise PolicyError(f"phase {args.phase!r} has no tasks")
    incomplete = [t["id"] for t in phase_tasks if t["status"] != "done"]
    if incomplete:
        raise PolicyError(
            f"phase {args.phase} is not ready for final acceptance; incomplete tasks: "
            f"{', '.join(incomplete)}"
        )
    notes_path = Path(args.kit) / "NOTES.md"
    notes_text = notes_path.read_text() if notes_path.exists() else ""
    evidence_fingerprint = review_evidence_fingerprint(args.kit, tasks_text, args.phase)
    if not _role_use_succeeded(
        notes_text, args.phase, "verifier", evidence_fingerprint=evidence_fingerprint
    ):
        raise PolicyError(
            f"phase {args.phase} has no successful independent Sol review record; run review first"
        )
    pricing = load_pricing()
    assignment = resolve_assignment(pricing, role="orchestrator")
    extra_args = tuple(args.extra_arg or ())
    if any(a == "--sandbox" or a.startswith(("--sandbox=", "-s")) for a in extra_args):
        raise PolicyError("acceptance sandbox is fixed to read-only")
    extra_args = ("--sandbox", "read-only", *extra_args)
    body = (
        f"Perform final acceptance for phase {args.phase} of the execution kit at {args.kit}. "
        "Inspect the plan, task records, independent review, verification evidence, and actual "
        "changes. Decide accepted or rejected and explain the evidence. Do not implement or "
        "modify files; corrective work requires the driver's structured recovery gate. End "
        "with exactly `POLYTROPOS_ACCEPTANCE: accepted` or `POLYTROPOS_ACCEPTANCE: rejected`."
    )
    prompt = load_preamble("reviewer", REPO_ROOT) + "\n\n---\n\n" + body
    argv = build_dispatch(
        args.codex_bin, assignment["model_id"], prompt, extra_args=extra_args
    )
    if args.dry_run:
        print(f"phase: {args.phase}")
        print(f"policy: role=orchestrator dispatched={assignment['model_id']} scope=acceptance-only")
        print(f"dispatch: {shlex.join(argv)}")
        return
    rc, output, telemetry = default_runner(argv)
    rc, output = enforce_attested_assignment(
        rc, output, telemetry, assignment["model_id"], "orchestrator"
    )
    verdict = parse_acceptance_verdict(output) if rc == 0 else None
    if rc == 0 and verdict is None:
        rc = 4
        output += "\nfinal acceptance did not provide the required machine verdict\n"
    append_role_use(notes_path, args.phase, "orchestrator", None,
                    assignment["model_id"], rc, telemetry.get("actual_model"),
                    telemetry.get("actual_role"), result=verdict or "failed",
                    evidence_fingerprint=evidence_fingerprint, report=output)
    print(output)
    if verdict == "rejected" and rc == 0:
        rc = 1
    if rc != 0:
        sys.exit(1)


def cmd_prepare(args):
    """Machine-readable assignment bridge for app/interactive orchestration."""
    pricing = load_pricing()
    if args.role == "recovery":
        raise PolicyError(
            "interactive prepare cannot unlock recovery from caller-supplied evidence; "
            "use kit run so the driver observes and records the failed attempts"
        )
    evidence = json.loads(args.evidence_json) if args.evidence_json else None
    assignment = resolve_assignment(
        pricing, planned_model=args.model, role=args.role, evidence=evidence
    )
    print(json.dumps({**assignment, "pool_mode": "reserved",
                      "actual_model": "unknown", "actual_role": "unknown"}, indent=2))


def build_parser():
    ap = argparse.ArgumentParser(
        prog="codex_execute.py",
        description=(
            "Run an execution kit against Codex CLI's non-interactive mode: parse TASKS.md, "
            "dispatch each task via `codex exec` with a role preamble, verify, escalate up the "
            "pricing tiers, write state back. Real runs spend subscription usage / API dollars; "
            "--dry-run spawns nothing."
        ),
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="print each task's status from a kit's TASKS.md")
    p_status.add_argument("--kit", required=True, help="kit directory (contains TASKS.md)")
    p_status.add_argument("--json", action="store_true", help="machine-readable output")
    p_status.set_defaults(func=cmd_status)

    p_run = sub.add_parser("run", help="dispatch one task and verify it (escalating on failure)")
    p_run.add_argument("--kit", required=True, help="kit directory (contains TASKS.md)")
    p_run.add_argument("--task", help="task id to run (default: first eligible pending task)")
    p_run.add_argument("--role", default="implementer",
                       help="codex/prompts/<role>.md preamble to prepend (default: implementer)")
    p_run.add_argument("--codex-bin", default="codex", help="Codex CLI binary to invoke")
    p_run.add_argument("--effort", default=None,
                       help="reasoning effort (validated against pricing knobs at run time)")
    p_run.add_argument("--max-escalations", type=int, default=None,
                       help="cap the number of escalation rungs")
    p_run.add_argument("--extra-arg", action="append",
                       help="extra dispatch flag (repeatable), e.g. --extra-arg=--sandbox=...")
    p_run.add_argument(
        "--parent", default=None,
        help="mark this run as a consult spawned to rescue TASK_ID (adds parent= to the "
             "outcome line on success; TASK_ID must differ from the task being run -- a value "
             "equal to the task's own id is REJECTED with exit 2, nothing written)",
    )
    p_run.add_argument("--dry-run", action="store_true",
                       help="print the dispatch argv and verify command; spawn/write nothing")
    p_run.set_defaults(func=cmd_run)

    p_review = sub.add_parser("review", help="dispatch the reviewer role for a phase")
    p_review.add_argument("--kit", required=True, help="kit directory (contains PLAN.md)")
    p_review.add_argument("--phase", required=True, help="phase number to review")
    p_review.add_argument("--codex-bin", default="codex", help="Codex CLI binary")
    p_review.add_argument("--extra-arg", action="append",
                          help="extra dispatch flag (repeatable)")
    p_review.add_argument("--dry-run", action="store_true",
                          help="print the dispatch argv; spawn nothing")
    p_review.set_defaults(func=cmd_review)

    p_accept = sub.add_parser("accept", help="dispatch Astra for acceptance-only review")
    p_accept.add_argument("--kit", required=True, help="kit directory")
    p_accept.add_argument("--phase", required=True, help="phase number to accept")
    p_accept.add_argument("--codex-bin", default="codex", help="Codex CLI binary")
    p_accept.add_argument("--extra-arg", action="append", help="extra dispatch flag")
    p_accept.add_argument("--dry-run", action="store_true", help="print argv; spawn nothing")
    p_accept.set_defaults(func=cmd_accept)

    p_prepare = sub.add_parser(
        "prepare", help="resolve a central policy assignment for an app or driver"
    )
    p_prepare.add_argument("--role", default="implementer")
    p_prepare.add_argument("--model", default=None, help="planned tier or model id")
    p_prepare.add_argument("--evidence-json", default=None,
                           help="structured recovery evidence JSON (recovery role only)")
    p_prepare.set_defaults(func=cmd_prepare)

    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    try:
        args.func(args)
    except (ValueError, FileNotFoundError, KeyError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
