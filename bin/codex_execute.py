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

Authoritative role-use evidence is TYPED and lives in `<kit>/role-use.jsonl`, one JSON object
per dispatch, written by the driver only: the exact integer dispatch return code, phase/role/
run/attempt identity, the evidence fingerprint, and the report's DIGEST -- never its text.
NOTES.md keeps the readable view, report and all, and is no longer read by any gate. The two
were one file once, and a substring search over that file could not tell a field the driver
wrote from the same characters quoted inside a model's report -- reports quote this repository's
own source routinely, so that was an accident waiting to happen, not only an attack. Legacy
NOTES.md blocks import as `provable: False`: unknown, never success (`import_legacy_role_use`).

The final acceptance verdict is read ONLY from a correlated terminal assistant message in a
completed turn on STDOUT (`parse_acceptance_result`). Tool events, reasoning items, intermediate
messages, stderr, failed turns, interrupted streams, and messages naming both verdicts all fail
closed with a stated reason. `DispatchOutput` keeps the two streams separable for exactly this;
once they are concatenated no consumer can tell which one a line came from.

Neither is a tamper-proof boundary: both files sit in a tree a worker can write. They fix
provenance -- what a field MEANS and where it came from -- not authority. Authority needs the
execution boundary, not a file format.

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

#: Wall clock for the local `git` reads that fingerprint a workspace. Short: these are local
#: metadata reads, and one that does not return in a minute is stuck, not slow.
GIT_PROBE_TIMEOUT_SECONDS = 60
PRICING_PATH = REPO_ROOT / "data" / "pricing.codex.json"
PLACEHOLDER = "{{POLYTROPOS_ROOT}}"

TIER_ORDER = ("cheap", "mid", "strong", "frontier")

# ---- the shared kit contract ---------------------------------------------------------------
#
# Everything below is DEFINED ONCE in `bin/kit_contract.py` and re-exported here. These names
# used to be written out in full in each of the three drivers, identically; see that module's
# docstring for the measurement. Re-exporting rather than importing-and-renaming keeps this
# module's surface exactly what it was, so callers -- this file, its tests, and
# `bin/journal_collect.py`, which uses `parse_tasks` as the kit-task format authority -- are
# unaffected, and a test that patches one of these names on this module still works.

_KIT_CONTRACT = None


def _kc():
    """Lazy-load `bin/kit_contract.py` -- the repo's ONE kit/task/run contract (step 15)."""
    global _KIT_CONTRACT
    if _KIT_CONTRACT is None:
        import importlib.util
        module_path = Path(__file__).resolve().parent / "kit_contract.py"
        spec = importlib.util.spec_from_file_location("kit_contract", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _KIT_CONTRACT = module
    return _KIT_CONTRACT


_CONTRACT = _kc()
CONTRACT_VERSION = _CONTRACT.CONTRACT_VERSION
TASK_FIELDS = _CONTRACT.TASK_FIELDS
to_contract = _CONTRACT.to_contract
BudgetAdmission = _CONTRACT.BudgetAdmission
EM_DASH = _CONTRACT.EM_DASH
OPERATION_CAPS = _CONTRACT.OPERATION_CAPS
PLAN_BUDGET_KEYS = _CONTRACT.PLAN_BUDGET_KEYS
PLAN_BUDGET_RE = _CONTRACT.PLAN_BUDGET_RE
STATUSES = _CONTRACT.STATUSES
_ep = _CONTRACT._ep
_evidence = _CONTRACT._evidence
_extract_brief = _CONTRACT._extract_brief
_extract_verify = _CONTRACT._extract_verify
_parse_block = _CONTRACT._parse_block
_parse_depends = _CONTRACT._parse_depends
_pr = _CONTRACT._pr
_read_tasks_text = _CONTRACT._read_tasks_text
_select_task = _CONTRACT._select_task
append_plan_budget_stop_note = _CONTRACT.append_plan_budget_stop_note
blocking_cap = _CONTRACT.blocking_cap
build_outcome_line = _CONTRACT.build_outcome_line
count_plan_budget_usage = _CONTRACT.count_plan_budget_usage
default_verify_runner = _CONTRACT.default_verify_runner
dispatch_status = _CONTRACT.dispatch_status
generate_run_id = _CONTRACT.generate_run_id
outcome_result = _CONTRACT.outcome_result
parse_plan_budget = _CONTRACT.parse_plan_budget
parse_tasks = _CONTRACT.parse_tasks
plan_budget_exhausted = _CONTRACT.plan_budget_exhausted
recorded_outcome_result = _CONTRACT.recorded_outcome_result
select_task = _CONTRACT.select_task
set_status = _CONTRACT.set_status

DEFAULT_ESCALATION_START = "mid"


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




build_id_preamble = _CONTRACT.build_id_preamble
cmd_status = _CONTRACT.cmd_status


def main(argv=None):
    """CLI entry point. `build_parser` is this driver's; the rest is shared."""
    return _CONTRACT.run_cli(build_parser, argv)



# ---- outcome ledger (T1 grammar: run=/parent=) -------------------------------------------------



# The `result=` values a `parent=` field may ride on. `bin/routing_scorecard.py`'s
# `build_lineage` keeps a `parent=` ONLY when the carrying outcome's own result is
# `escalated-pass` and drops any other placement with an "out of grammar, ignored" note --
# while `outcome_result` above still classifies that same line, so a rejected `parent=` would
# put one line into a headline figure and into the "ignored" list at once (Phase 1 review's F2
# invariant). `append_note` therefore OMITS `parent=` on any other result rather than writing a
# line the reader rejects. Identical rule in all three drivers (PLAN D1).
PARENT_RESULTS = ("escalated-pass",)
























class _BudgetRefused(Exception):
    """An operation refused by admission BEFORE it spent anything."""

    def __init__(self, kind, reason):
        super().__init__(reason)
        self.kind = kind
        self.reason = reason


def run_task(task, pricing, runner, verify_runner, prompt=None, role="implementer",
             max_escalations=None, codex_bin="codex", effort=None, extra_args=(),
             allow_recovery=True, admission=None, consult=False):
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

    def dispatch_and_verify(chosen_model, chosen_role, dispatch_prompt, kind="initial"):
        # THE choke point: every codex dispatch passes through here, so admission asks here
        # rather than once at invocation entry. A refused operation raises rather than
        # returning a verify-shaped tuple, so it can never be mistaken for a check result.
        if admission is not None:
            ok, reason = admission.admit(kind)
            if not ok:
                raise _BudgetRefused(kind, reason)
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

    rc, output = dispatch_and_verify(
        model_id, assignment["resolved_role"], prompt,
        kind="consult" if consult else "initial",
    )

    policy_violation = attempts[-1]["result"] == "policy-mismatch"
    if rc != 0 and assignment["resolved_role"] == "implementer" and not policy_violation:
        ladder = candidate_ladder
        for rung in ladder:
            escalated_prompt = prompt + _evidence(verify_cmd, rc, output)
            escalations.append(rung)
            model_used = rung
            rc, output = dispatch_and_verify(rung, "implementer", escalated_prompt,
                                             kind="escalation")
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
        rc, output = dispatch_and_verify(model_used, "recovery", recovery_prompt,
                                         kind="retry")
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

class DispatchOutput(str):
    """Combined `stdout + stderr` for DISPLAY, carrying the two streams separately.

    A `str` subclass so every existing consumer (`print(output)`, `output + "note"`, the
    `rc, output, telemetry = default_runner(...)` unpacking) keeps working unchanged, while
    anything that needs to reason about PROVENANCE can reach `.stdout` and `.stderr` instead
    of a concatenation it cannot un-mix. The verdict parser reads `.stdout` only: a diagnostic
    on stderr is not a model result, and once the two are joined nothing downstream can tell
    which stream a line came from.

    Note that `output + "..."` returns a plain `str` and DROPS the streams -- deliberate, since
    an annotated string is no longer the dispatch's own output. Parse before annotating.
    """

    def __new__(cls, stdout, stderr):
        obj = super().__new__(cls, (stdout or "") + (stderr or ""))
        obj.stdout = stdout or ""
        obj.stderr = stderr or ""
        return obj


def default_runner(argv, cwd=None, timeout=None):
    """Dispatch runner for real runs -> (rc, DispatchOutput, telemetry).

    !!! Invoking this with a real `codex` argv spends the user's real subscription usage
    limits / API dollars and hits the network. !!!

    Bounded since step 12: a wall clock, an output ceiling, a validated working directory, and
    its own process group -- so a dispatch that stalls or floods cannot hang the driver, and
    nothing it spawned outlives it. Failures that are not the model's verdict (a missing CLI, a
    timeout) come back as an rc of `proc_runner.INFRASTRUCTURE_RC` with the reason appended to
    the output, rather than as an exception that would strand the task in-progress.

    The environment is reduced to this provider's own variables plus the base set, so the
    machine's unrelated credentials are not handed to a coding agent. `POLYTROPOS_DISPATCH_ENV`
    (comma-separated NAMES) widens it on a host that needs a variable the list has not learned.
    """
    started = datetime.now(timezone.utc)
    pr = _pr()
    result = pr.run(
        argv,
        cwd=cwd if cwd is not None else Path.cwd(),
        env=pr.dispatch_env("codex"),
        timeout=timeout,
        name="codex dispatch",
    )
    # stdout and stderr stay separate all the way through: attestation reads the STRUCTURED
    # event stream, and diagnostics interleaved into it would be parsed as events. A runner
    # diagnostic (a missing binary, a timeout) therefore joins STDERR -- putting it on stdout
    # would feed a non-event line to the event parser.
    stderr = result["stderr"]
    if not result["terminal"] and result["detail"]:
        stderr = f"{stderr}\n{result['detail']}" if stderr else result["detail"]
    output = DispatchOutput(result["stdout"], stderr)
    telemetry = attest_runtime_model(output.stdout, started)
    return result["rc"], output, telemetry


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








#: The authoritative role-use ledger: one JSON object per line, written by the DRIVER only.
#: Separate from NOTES.md on purpose. NOTES.md interleaves driver fields with the model's own
#: free-form report inside one Markdown block, so a substring search over that block cannot
#: tell a field the driver wrote from the same characters quoted inside a report -- and the
#: report is model-authored text that routinely quotes this repository's own source. Typed
#: records carry NO free-form body, only its digest.
ROLE_USE_SCHEMA = "polytropos.role-use/1"
ROLE_USE_FILENAME = "role-use.jsonl"


def role_use_path(kit_dir):
    return Path(kit_dir) / ROLE_USE_FILENAME


def _is_exact_int(value):
    """True only for a real integer. JSON booleans deserialize to `bool`, a subclass of `int`;
    `true` is not an exit code."""
    return isinstance(value, int) and not isinstance(value, bool)


def read_role_use_records(kit_dir):
    """Every parseable typed record for `kit_dir`, in file order. Never raises: a malformed or
    truncated line is skipped, because a corrupt ledger must degrade to "cannot prove success"
    rather than to an exception that a caller might be tempted to catch and treat as success."""
    path = role_use_path(kit_dir)
    if not path.exists():
        return []
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return []
    records = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def latest_role_use_record(kit_dir, phase, role):
    """The LAST typed record for `(phase, role)`, or None. Later records supersede earlier ones,
    so a fresh failed review supersedes an older successful one rather than being outvoted."""
    found = None
    for record in read_role_use_records(kit_dir):
        if record.get("schema") != ROLE_USE_SCHEMA:
            continue
        if record.get("phase") != str(phase) or record.get("role") != role:
            continue
        found = record
    return found


def import_legacy_role_use(notes_text):
    """Read pre-typed-record NOTES.md blocks, for DISPLAY and diagnostics only.

    Every entry carries `provable: False`, always. The legacy grammar put authoritative fields
    and model-authored report text in one block with no delimiter between them, so nothing read
    back out of it can be attributed to the driver. Unprovable success is UNKNOWN -- it is not
    downgraded to failure (the review may well have passed) and it is never promoted to success.
    Re-run the role to get a record that can be checked."""
    entries = []
    for block in notes_text.split("\n## "):
        if not block.strip():
            continue
        head = block.splitlines()[0]
        match = re.search(r"phase-(\S+?)-(implementer|verifier|orchestrator|reviewer)\b", head)
        if not match:
            continue
        entries.append({
            "phase": match.group(1),
            "role": match.group(2),
            "provable": False,
            "reason": "legacy NOTES.md block predates typed role-use records",
        })
    return entries


def append_role_use(kit_dir, phase, role, planned_model, dispatched_model, dispatch_rc,
                    actual_model=None, actual_role=None, result=None, evidence_fingerprint=None,
                    report=None, run_id=None, now=None):
    """Record a non-task review/acceptance dispatch in BOTH ledgers, without ever claiming
    requested=observed.

    The typed record in `role-use.jsonl` is authoritative and carries only fields the driver
    itself produced -- the exact integer dispatch return code, role/phase/run/attempt identity,
    the evidence fingerprint, and the report's DIGEST. The NOTES.md block stays the
    human-readable view and keeps the bounded report text.

    This is a provenance boundary, not a tamper-proof one: both files sit in a tree a worker
    can write. It stops a report from being MISREAD as a driver field; it does not stop a
    sufficiently privileged process from editing the ledger outright. That needs the execution
    boundary, not a file format."""
    kit_dir = Path(kit_dir)
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    report_digest = (
        hashlib.sha256((report or "").encode()).hexdigest() if report is not None else None
    )
    attempt = 1 + sum(
        1 for r in read_role_use_records(kit_dir)
        if r.get("schema") == ROLE_USE_SCHEMA
        and r.get("phase") == str(phase) and r.get("role") == role
    )

    record = {
        "schema": ROLE_USE_SCHEMA,
        "recorded_at": stamp,
        "phase": str(phase),
        "role": role,
        "run_id": run_id,
        "attempt": attempt,
        "dispatch_rc": dispatch_rc,
        "planned_model": planned_model,
        "dispatched_model": dispatched_model,
        "actual_model": actual_model,
        "actual_role": actual_role,
        "result": result,
        "evidence_fingerprint": evidence_fingerprint,
        "report_sha256": report_digest,
    }
    path = role_use_path(kit_dir)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")

    notes_path = kit_dir / "NOTES.md"
    report_text = " ".join((report or "").split())[-2000:]
    block = (
        f"## {stamp}{EM_DASH}phase-{phase}-{role}\n"
        f"- actual-use: planned={planned_model or 'policy'} dispatched_model={dispatched_model} "
        f"dispatched_role={role} actual_model={actual_model or 'unknown'} "
        f"actual_role={actual_role or 'unknown'} dispatch_exit={dispatch_rc}"
        f"{f' result={result}' if result else ''}\n"
        f"- authority: {ROLE_USE_FILENAME} (this block is the readable view, not the record)\n"
    )
    if evidence_fingerprint:
        block += f"- evidence-fingerprint: {evidence_fingerprint}\n"
    if report is not None:
        block += f"- report-sha256: {report_digest}\n- report: {report_text or '(empty)'}\n"
    existing = notes_path.read_text() if notes_path.exists() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    notes_path.write_text(existing + ("\n" if existing.strip() else "") + block)
    return record


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


#: Codex `exec --json` event and item names this driver recognizes. BEST-EFFORT and pinned,
#: exactly like the dispatch flags in `build_dispatch`: taken from the client's documented
#: `exec --json` stream and NEVER probed at run time. Anything not named here is unrecognized,
#: and unrecognized fails closed -- a verdict is only ever read from a correlated terminal
#: assistant message, never from a tool event, a reasoning item, or stderr.
CODEX_EVENT_THREAD_STARTED = "thread.started"
CODEX_EVENT_ITEM_COMPLETED = "item.completed"
CODEX_EVENT_TURN_COMPLETED = "turn.completed"
CODEX_EVENT_TURN_FAILED = "turn.failed"
CODEX_ITEM_AGENT_MESSAGE = "agent_message"

ACCEPTANCE_RE = re.compile(r"POLYTROPOS_ACCEPTANCE:[ \t]*(accepted|rejected)\b")


def _no_verdict(reason):
    return {"verdict": None, "reason": reason, "provenance": "unproven"}


def parse_acceptance_result(output):
    """The final acceptance verdict, or a reason it could not be established.

    Returns `{"verdict": "accepted"|"rejected"|None, "reason": str, "provenance": str}`.

    FAIL CLOSED is the whole contract. A verdict is returned ONLY when all of the following
    hold, and the `reason` names the first one that did not:

      * the dispatch preserved a separate stdout stream (a bare `str` cannot, so it never
        yields a verdict -- a caller that concatenated the streams has already destroyed the
        evidence this function exists to check);
      * stdout carried a recognized structured event stream;
      * a `thread.started` correlated the stream to one thread;
      * the turn COMPLETED, and did not fail -- an interrupted or failed turn has no final
        result, whatever text it managed to emit first;
      * the last `item.completed` carrying an `agent_message` exists. Tool-originated items
        (command output, file changes, MCP calls, reasoning) are skipped entirely: they are
        things the model CAUSED, not things it CONCLUDED;
      * that message carries exactly one DISTINCT verdict. Zero is silence; two is a
        contradiction, and a contradiction resolves to nothing rather than to the last one
        seen.

    stderr is never consulted. Markers elsewhere in the stream -- an echoed prompt, a quoted
    instruction, a tool printing the token -- are structurally unreachable rather than merely
    outranked.
    """
    stdout = getattr(output, "stdout", None)
    if stdout is None:
        return _no_verdict("dispatch output did not preserve a separate stdout stream")

    thread_id = None
    terminal_message = None
    turn_completed = False
    turn_failed = False
    saw_event = False

    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        etype = event.get("type")
        if not isinstance(etype, str):
            continue
        saw_event = True
        if etype == CODEX_EVENT_THREAD_STARTED:
            tid = event.get("thread_id")
            if isinstance(tid, str) and tid:
                thread_id = tid
        elif etype == CODEX_EVENT_TURN_FAILED:
            turn_failed = True
        elif etype == CODEX_EVENT_TURN_COMPLETED:
            turn_completed = True
        elif etype == CODEX_EVENT_ITEM_COMPLETED:
            item = event.get("item")
            if not isinstance(item, dict):
                continue
            if item.get("type") != CODEX_ITEM_AGENT_MESSAGE:
                continue  # tool-originated or intermediate: never a final result
            text = item.get("text")
            if isinstance(text, str):
                terminal_message = text

    if not saw_event:
        return _no_verdict("no recognized structured event stream on stdout")
    if thread_id is None:
        return _no_verdict("no thread.started event to correlate the result to")
    if turn_failed:
        return _no_verdict("the turn failed; a failed turn has no final result")
    if not turn_completed:
        return _no_verdict("the turn never completed (interrupted or truncated stream)")
    if terminal_message is None:
        return _no_verdict("no terminal assistant message in the completed turn")

    verdicts = set(ACCEPTANCE_RE.findall(terminal_message))
    if not verdicts:
        return _no_verdict("terminal assistant message carried no acceptance marker")
    if len(verdicts) > 1:
        return _no_verdict(
            "terminal assistant message carried conflicting acceptance markers "
            f"({', '.join(sorted(verdicts))})"
        )
    return {
        "verdict": verdicts.pop(),
        "reason": "correlated terminal assistant message in a completed turn",
        "provenance": f"thread:{thread_id}",
    }


# ---- CLI ------------------------------------------------------------------------------------



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
    # Bounded, and in BYTES. Bounded because `git diff` under a configured `core.fsmonitor`
    # can block on a daemon and this is the acceptance path -- an unbounded wait here stalls a
    # run at the moment it is deciding whether the work is done. In bytes because these bytes
    # ARE the fingerprint: a binary diff decoded with `errors="replace"` is a different diff,
    # and every previously recorded fingerprint would stop matching.
    def _git(*args):
        return _pr().run(["git", "-C", *args], cwd=Path.cwd(),
                         timeout=GIT_PROBE_TIMEOUT_SECONDS, name="git probe", text=False)

    probe = _git(str(kit), "rev-parse", "--show-toplevel")
    if probe["rc"] != 0:
        raise PolicyError("final acceptance requires a git workspace to prove review freshness")
    root = Path(probe["stdout"].decode("utf-8", "replace").strip()).resolve()
    head = _git(str(root), "rev-parse", "HEAD")
    if head["rc"] != 0:
        raise PolicyError("final acceptance requires a committed HEAD for review freshness")
    notes = (kit / "NOTES.md").resolve()
    try:
        notes_rel = notes.relative_to(root).as_posix()
    except ValueError:
        notes_rel = None
    exclude = [f":(exclude){notes_rel}"] if notes_rel else []
    diff = _git(str(root), "diff", "--binary", "--no-ext-diff", "HEAD", "--", ".", *exclude)
    status = _git(str(root), "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if diff["rc"] != 0 or status["rc"] != 0:
        raise PolicyError("could not fingerprint workspace for review freshness")
    untracked = []
    for entry in status["stdout"].split(b"\0"):
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
    material = (head["stdout"].strip() + b"\0" + plan_bytes + b"\0" + match.group(0).encode()
                + b"\0" + task_notes + b"\0" + diff["stdout"] + b"\0"
                + b"\0".join(untracked))
    return hashlib.sha256(material).hexdigest()


def _role_use_succeeded(kit_dir, phase, role, evidence_fingerprint=None):
    """True only when the latest TYPED record for `(phase, role)` proves a clean dispatch
    against the CURRENT evidence fingerprint.

    Every clause is an equality check against a driver-written field, never a substring search
    over a block that also contains model-authored prose:

      * a typed record must exist -- a legacy NOTES.md block proves nothing (see
        `import_legacy_role_use`);
      * `dispatch_rc` must be the exact integer 0 (`true` is not 0, `"0"` is not 0);
      * the recorded fingerprint must EQUAL the expected one, so a review of a workspace that
        has since changed cannot certify the current one.
    """
    record = latest_role_use_record(kit_dir, phase, role)
    if record is None:
        return False
    if not _is_exact_int(record.get("dispatch_rc")) or record["dispatch_rc"] != 0:
        return False
    if evidence_fingerprint is not None:
        recorded = record.get("evidence_fingerprint")
        if not isinstance(recorded, str) or recorded != evidence_fingerprint:
            return False
    return True


def _acceptance_state(kit_dir, phase, evidence_fingerprint=None):
    """`accepted` / `rejected` / `pending` for a phase, from the typed ledger only.

    `pending` is the answer for every uncertainty -- no record, a stale fingerprint, a failed
    dispatch, or a `result` outside the closed vocabulary. An unproven acceptance is not an
    acceptance."""
    record = latest_role_use_record(kit_dir, phase, "orchestrator")
    if record is None:
        return "pending"
    if not _is_exact_int(record.get("dispatch_rc")) or record["dispatch_rc"] != 0:
        return "pending"
    if evidence_fingerprint is not None:
        recorded = record.get("evidence_fingerprint")
        if not isinstance(recorded, str) or recorded != evidence_fingerprint:
            return "pending"
    result = record.get("result")
    return result if result in ("accepted", "rejected") else "pending"










def cmd_run(args):
    kit = Path(args.kit)
    slug = kit.name
    tasks_path = kit / "TASKS.md"
    text = _read_tasks_text(kit)
    tasks = parse_tasks(text)
    task, select_reason = select_task(tasks, args.task, allow_rerun=args.rerun)
    if task is None:
        print(f"{select_reason} ({tasks_path})", file=sys.stderr)
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
    admission = None
    if plan_budget:
        notes_path = kit / "NOTES.md"
        notes_text = notes_path.read_text() if notes_path.exists() else ""
        used = count_plan_budget_usage(notes_text)
        # The entry gate below still stops a run before it writes `in-progress`. This carries
        # the same numbers INTO the run, so every escalation rung asks again instead of the
        # ladder spending freely on one entry-time grant.
        admission = BudgetAdmission(plan_budget, used)
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

    # One confined runner for BOTH the precheck and the task's own verification: the precheck
    # runs the same repo-authored line against the same tree, so it cannot be the unconfined
    # one. `--exec-mode enforced` refuses outright on a host with no backend rather than
    # quietly running it with the parent's privileges.
    verify_runner = _ep().verify_runner(Path.cwd(), mode=args.exec_mode)

    try:
        result = run_task(
            task, pricing, default_runner, verify_runner,
            prompt=prompt, role=args.role, max_escalations=args.max_escalations,
            codex_bin=args.codex_bin, effort=args.effort, extra_args=extra_args,
            admission=admission, consult=bool(args.parent),
        )
    except _BudgetRefused as refusal:
        # Refused MID-RUN, after earlier operations in this same invocation spent their
        # allowance. Nothing ran for this operation, so there is no exit code and no verdict.
        result = {
            "id": task["id"], "status": "blocked", "model_used": None, "escalations": [],
            "verify_rc": None, "dispatch_rc": None, "failure": "budget",
            "budget_stop": {"operation": refusal.kind, "reason": refusal.reason},
        }
        print(f"budget-stop: {refusal.reason}", file=sys.stderr)

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
    append_role_use(args.kit, args.phase, "verifier", None,
                    assignment["model_id"], rc, telemetry.get("actual_model"),
                    telemetry.get("actual_role"), evidence_fingerprint=evidence_fingerprint,
                    report=output, run_id=generate_run_id())
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
    evidence_fingerprint = review_evidence_fingerprint(args.kit, tasks_text, args.phase)
    if not _role_use_succeeded(
        args.kit, args.phase, "verifier", evidence_fingerprint=evidence_fingerprint
    ):
        notes_path = Path(args.kit) / "NOTES.md"
        notes_text = notes_path.read_text() if notes_path.exists() else ""
        legacy = [e for e in import_legacy_role_use(notes_text)
                  if e["phase"] == str(args.phase) and e["role"] == "verifier"]
        detail = (
            f"; {len(legacy)} legacy NOTES.md review block(s) exist for this phase but predate "
            f"typed role-use records and cannot establish success -- re-run `review`"
            if legacy else ""
        )
        raise PolicyError(
            f"phase {args.phase} has no successful independent Sol review record in "
            f"{ROLE_USE_FILENAME}; run review first{detail}"
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
        "your final message with one line reading `POLYTROPOS_ACCEPTANCE: <verdict>`, where "
        "<verdict> is accepted or rejected. Emit that marker exactly once and name only the "
        "verdict you chose -- a final message naming both verdicts is discarded as conflicting."
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
    # Parse BEFORE any annotation: `enforce_attested_assignment` may append to `output`, and
    # `DispatchOutput + str` is a plain `str` with the streams dropped.
    dispatch_output = output
    rc, output = enforce_attested_assignment(
        rc, output, telemetry, assignment["model_id"], "orchestrator"
    )
    result = (
        parse_acceptance_result(dispatch_output) if rc == 0
        else _no_verdict("dispatch did not complete cleanly")
    )
    verdict = result["verdict"]
    if rc == 0 and verdict is None:
        rc = 4
        output += (
            "\nfinal acceptance did not provide the required machine verdict: "
            f"{result['reason']}\n"
        )
    append_role_use(args.kit, args.phase, "orchestrator", None,
                    assignment["model_id"], rc, telemetry.get("actual_model"),
                    telemetry.get("actual_role"), result=verdict or "failed",
                    evidence_fingerprint=evidence_fingerprint, report=output,
                    run_id=generate_run_id())
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
    p_run.add_argument("--exec-mode", choices=("enforced", "trusted-host"), default="enforced",
                       help="verification confinement (step 05). `enforced` runs the verify "
                            "command inside an OS boundary — writes limited to the workspace, "
                            "network denied, credential stores unreadable — and REFUSES when "
                            "no backend can enforce that. `trusted-host` runs it with no "
                            "boundary at all and says so; choose it only for a host you trust.")
    p_run.add_argument("--rerun", action="store_true",
                       help="allow selecting a task already marked done (step 07). Without it, "
                            "naming a completed task is refused rather than silently repeating "
                            "finished work.")
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




if __name__ == "__main__":
    main()
