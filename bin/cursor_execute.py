#!/usr/bin/env python3
"""Run an execution kit through Cursor's CLI, on the shared runtime (step 23).

    cursor_execute.py probe  [--cursor-bin BIN] [--models]
    cursor_execute.py status --kit DIR [--json]
    cursor_execute.py run    --kit DIR [--task ID] [--model ID] [--cursor-bin BIN] [--dry-run] ...
    cursor_execute.py review --kit DIR --phase N [--model ID] [--dry-run]

WHAT IS SHARED, AND WHAT IS NOT. Everything that must mean the same thing on every harness
comes from `bin/kit_contract.py`: task parsing, the graph and roster checks, selection, the
attempt lifecycle, the budget gate, projection from a fresh read, the outcome grammar. What
this file adds is only what Cursor's CLI makes different: the identity probe before any
dispatch, the `agent -p` argv, and what its JSON output can and cannot say.

WHAT THIS DRIVER DOES NOT DO. There is no escalation ladder: `data/pricing.cursor.json`
records no tiers or rates, so a failed verification leaves the task `blocked` after one
attempt and says so. There is no cost figure: the CLI reports none, and none is invented.
The observed model is whatever the CLI's own output names, or unknown. A dispatch to a
binary that did not identify itself as Cursor is refused before anything is written.

`--dry-run` prints the argv and spawns nothing -- not even the identity probe, which would
run the binary. A real run spends the user's Cursor allowance.
"""

import argparse
import importlib.util
import json
import shlex
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PRICING_PATH = REPO_ROOT / "data" / "pricing.cursor.json"
ACTOR = "cursor"
DISPATCH_TIMEOUT_SECONDS = 3600

_KIT_CONTRACT = None


def _kc():
    """Load the shared contract by path (bin/ is not a package)."""
    global _KIT_CONTRACT
    if _KIT_CONTRACT is None:
        path = Path(__file__).resolve().with_name("kit_contract.py")
        spec = importlib.util.spec_from_file_location("kit_contract", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _KIT_CONTRACT = module
    return _KIT_CONTRACT


_CONTRACT = _kc()
CONTRACT_VERSION = _CONTRACT.CONTRACT_VERSION
TASK_FIELDS = _CONTRACT.TASK_FIELDS
STATUSES = _CONTRACT.STATUSES
parse_tasks = _CONTRACT.parse_tasks
select_task = _CONTRACT.select_task
_select_task = _CONTRACT._select_task
_read_tasks_text = _CONTRACT._read_tasks_text
set_status = _CONTRACT.set_status
project_status = _CONTRACT.project_status
cmd_status = _CONTRACT.cmd_status
generate_run_id = _CONTRACT.generate_run_id
build_id_preamble = _CONTRACT.build_id_preamble
dispatch_status = _CONTRACT.dispatch_status
outcome_result = _CONTRACT.outcome_result
start_task_lifecycle = _CONTRACT.start_task_lifecycle
reconcile_task = _CONTRACT.reconcile_task
finish_task_projection = _CONTRACT.finish_task_projection
record_role_dispatch = _CONTRACT.record_role_dispatch
roster_for_run = _CONTRACT.roster_for_run
record_roster = _CONTRACT.record_roster
GAP_MODES = _CONTRACT.GAP_MODES
exit_if_invalid_graph = _CONTRACT.exit_if_invalid_graph
budget_gate = _CONTRACT.budget_gate
append_run_note = _CONTRACT.append_run_note

_ADAPTER = None


def _ca():
    global _ADAPTER
    if _ADAPTER is None:
        path = Path(__file__).resolve().with_name("cursor_adapter.py")
        spec = importlib.util.spec_from_file_location("polytropos_cursor_adapter", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _ADAPTER = module
    return _ADAPTER


BINARY = _ca().BINARY
IdentityError = _ca().IdentityError
identify = _ca().identify
require_cursor = _ca().require_cursor
build_dispatch = _ca().build_dispatch
parse_output = _ca().parse_output


def load_pricing():
    """Cursor's own pricing file, which records no model or rate; never another harness's."""
    with open(PRICING_PATH) as fh:
        return json.load(fh)


def load_preamble(role, repo_root=None):
    """The bundled subagent body for `role` (frontmatter stripped) -> the prompt preamble."""
    root = Path(repo_root or REPO_ROOT)
    path = root / "cursor" / "agents" / f"polytropos-{role}.md"
    if not path.exists():
        raise FileNotFoundError(f"no Cursor role prompt at {path}")
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "".join(lines[i + 1:]).strip()
    return text.strip()


def default_runner(argv, cwd=None, timeout=None):
    """Start `agent` through the process runner -> `(rc, output, raw)`; never a shell."""
    pr = _CONTRACT._pr()
    result = pr.run(argv, cwd=cwd or Path.cwd(), timeout=timeout or DISPATCH_TIMEOUT_SECONDS,
                    name="cursor dispatch", env=pr.dispatch_env("cursor"))
    output = result.get("stdout") or ""
    if result.get("stderr"):
        output = output + ("\n" if output else "") + result["stderr"]
    return result.get("rc"), output, result


def _unpack(raw):
    """A runner's answer in any of its shapes -> `(rc, output, process_result)`."""
    if raw is None:
        return None, "", {}
    if len(raw) == 3:
        rc, output, proc = raw
        return rc, output or "", proc if isinstance(proc, dict) else {}
    rc, output = raw
    return rc, output or "", {}


def run_task(task, runner, verify_runner, prompt=None, model=None, cursor_bin=BINARY,
             workspace=None, extra_args=(), admission=None, consult=False, lifecycle=None,
             resume=False):
    """One dispatch, one verification -> the result dict.

    The dispatch is recorded before and after through `lifecycle` (step 16). A non-zero
    dispatch exit is a dispatch failure with its class and no verdict; a failed verification
    is `blocked` after this one attempt, because Cursor has no tier ladder to climb.
    """
    if prompt is None:
        prompt = task["brief"]
    verify_cmd = task.get("verify")
    if not isinstance(verify_cmd, str) or not verify_cmd.strip():
        raise ValueError(f"task {task.get('id')!r} has no runnable verify command")
    model_id = model or task.get("model")
    kind = "consult" if consult else ("retry" if resume else "initial")
    if admission is not None:
        ok, reason = admission.admit(kind)
        if not ok:
            return _CONTRACT._budget_stop(task, model_id, [], kind, reason)
    argv = build_dispatch(task, model_id=model_id, prompt=prompt, cursor_bin=cursor_bin,
                          workspace=workspace, extra_args=extra_args)
    attempt = lifecycle.attempt_started(kind, model_id, prompt, verify_cmd) if lifecycle else None
    try:
        raw = runner(argv)
    except OSError as exc:
        raw = (126, f"dispatch failed: {exc}", {"outcome": "start-failed"})
    rc, output, proc = _unpack(raw)
    parsed = parse_output(output)
    observed = parsed["observed_model"]
    if lifecycle:
        cls = lifecycle.attempt_finished(attempt, rc, output, proc_outcome=proc.get("outcome"),
                                         duration_s=proc.get("duration_s"),
                                         observed_model=observed)
    else:
        cls = (_CONTRACT._al().classify_dispatch(rc, output, proc_outcome=proc.get("outcome"))
               if rc not in (None, 0) else None)
    base = {
        "id": task["id"], "model_used": model_id, "planned_model": task.get("model"),
        "observed_model": observed, "escalations": [], "dispatch_rc": rc, "usd": None,
        "output_parsed": parsed["parsed"],
    }
    if rc is not None and rc != 0:
        return {**base, "status": "blocked", "verify_rc": None, "failure": "dispatch",
                "class": cls, "dispatch_evidence": " ".join(output.split())[-2000:] or "(no output)"}
    try:
        vrc, vout = verify_runner(verify_cmd)
    except OSError as exc:
        vrc, vout = 126, f"verify failed to start: {exc}"
    if lifecycle:
        lifecycle.verify_finished(attempt, vrc, vout)
    return {**base, "status": "done" if vrc == 0 else "blocked", "verify_rc": vrc,
            "failure": None if vrc == 0 else "verification", "class": None,
            "verify_evidence": " ".join((vout or "").split())[-2000:]}


def cmd_run(args):
    kit = Path(args.kit)
    slug = kit.name
    tasks_path = kit / "TASKS.md"
    text = _read_tasks_text(kit)
    tasks = parse_tasks(text)
    workspace = Path.cwd()

    plan_text = (kit / "PLAN.md").read_text() if (kit / "PLAN.md").exists() else ""
    roster, roster_support = roster_for_run(plan_text, "cursor", args.roster_gap, slug=slug)

    task, reason = select_task(tasks, args.task, allow_rerun=args.rerun,
                               freshness=_CONTRACT.kit_freshness(kit, tasks, store=args.attempt_store))
    if task is None:
        print(f"{reason} ({tasks_path})", file=sys.stderr)
        sys.exit(2)
    if args.parent and args.parent == task["id"]:
        print(f"--parent {args.parent!r} is the task being run -- a task cannot be its own "
              f"parent; name the other task's id or drop --parent.", file=sys.stderr)
        sys.exit(2)

    extra_args = tuple(args.extra_arg or ())
    run_id = generate_run_id()
    preamble = load_preamble("implementer", REPO_ROOT)
    prompt = preamble + "\n\n---\n\n" + task["brief"]
    id_preamble = build_id_preamble(kit=slug, run_id=run_id, task_id=task["id"])
    if id_preamble:
        prompt = f"{id_preamble}\n\n{prompt}"
    model_id = args.model or task.get("model")
    argv = build_dispatch(task, model_id=model_id, prompt=prompt, cursor_bin=args.cursor_bin,
                          workspace=workspace, extra_args=extra_args)

    if args.dry_run:
        print(f"task: {task['id']}")
        print(f"identity: not probed under --dry-run (nothing is spawned)")
        print(f"model: {model_id or 'host default (no --model)'}; usd: null (Cursor reports "
              f"no usage)")
        print(f"dispatch: {shlex.join(argv)}")
        print(f"verify: {task['verify']}")
        return

    # IDENTITY BEFORE TRUST (step 23): a generically named binary is dispatched to only after
    # it says it is Cursor. Refused here, before the claim, before any write.
    try:
        identity = require_cursor(identify(args.cursor_bin, cwd=workspace))
    except IdentityError as exc:
        print(f"cursor: {exc}", file=sys.stderr)
        sys.exit(2)
    print(f"cursor: {identity['identity']} ({identity.get('version') or 'version unknown'})",
          file=sys.stderr)

    lifecycle, begin_info = start_task_lifecycle(
        kit, task, run_id, actor=ACTOR, store=args.attempt_store,
        break_claim=args.break_claim, workspace=workspace, role="implementer",
        parent=args.parent,
    )
    record_roster(lifecycle, roster, roster_support, args.roster_gap)
    admission = budget_gate(kit, tasks, task, run_id, lifecycle, consult=bool(args.parent))

    text, _previous = project_status(tasks_path, task["id"], "in-progress")
    verify_runner = _CONTRACT._ep().verify_runner(workspace, mode=args.exec_mode)

    recon = reconcile_task(lifecycle, begin_info, verify_runner, task.get("verify"))
    if recon["mode"] == "resolved":
        result = recon["result"]
        result.update({"planned_model": task.get("model"), "observed_model": None, "usd": None})
        print(f"resume: task {task['id']}'s check passes on the tree that "
              f"{result['reconciled']} earlier attempt(s) left; nothing was re-dispatched",
              file=sys.stderr)
    else:
        if recon["mode"] == "retry":
            prompt = prompt + recon["context"]
            print(f"resume: task {task['id']} has earlier attempts and its check still fails "
                  f"(exit {recon['verify_rc']}); dispatching once more with their evidence",
                  file=sys.stderr)
        result = run_task(
            task, default_runner, verify_runner, prompt=prompt, model=args.model,
            cursor_bin=args.cursor_bin, workspace=workspace, extra_args=extra_args,
            admission=admission, consult=bool(args.parent), lifecycle=lifecycle,
            resume=(recon["mode"] == "retry"),
        )
        if result.get("failure") == "budget":
            print(f"budget-stop: {result['budget_stop']['reason']}", file=sys.stderr)

    text = finish_task_projection(lifecycle, tasks_path, task, result)
    result["role"] = "implementer"
    append_run_note(kit / "NOTES.md", result, task, run_id=run_id, parent=args.parent,
                    actor=ACTOR)
    lifecycle.project(result["status"], outcome_result(result["status"], result["escalations"],
                                                       args.parent), outcome_line=True)
    lifecycle.end()
    print(f"task {result['id']}: {result['status']} (model_used="
          f"{result['model_used'] or 'cursor default'}, observed="
          f"{result.get('observed_model') or 'unknown'}, verify_rc={result['verify_rc']}, "
          f"usd=null, run={run_id})")
    if result["status"] == "blocked":
        sys.exit(1)


def cmd_review(args):
    kit = Path(args.kit)
    workspace = Path.cwd()
    extra_args = tuple(args.extra_arg or ())
    preamble = load_preamble("verifier", REPO_ROOT)
    body = (
        f"Review phase {args.phase} of the execution kit at {kit}. Read {kit}/PLAN.md (goal, "
        f"decisions, out-of-scope fence, tripwires) and the tasks under '## Phase {args.phase}' "
        f"in {kit}/TASKS.md, then review the actual changes for drift, scope creep, and "
        f"contract breakage. Report findings; change nothing."
    )
    prompt = preamble + "\n\n---\n\n" + body
    argv = build_dispatch({"id": f"phase-{args.phase}"}, model_id=args.model, prompt=prompt,
                          cursor_bin=args.cursor_bin, workspace=workspace, read_only=True,
                          extra_args=extra_args)
    if args.dry_run:
        print(f"phase: {args.phase}")
        print(f"dispatch: {shlex.join(argv)}")
        return
    try:
        require_cursor(identify(args.cursor_bin, cwd=workspace))
    except IdentityError as exc:
        print(f"cursor: {exc}", file=sys.stderr)
        sys.exit(2)
    rc, output, proc = _unpack(default_runner(argv))
    parsed = parse_output(output)
    record_role_dispatch(kit, generate_run_id(), "reviewer", args.phase, args.model, rc, output,
                         actor=ACTOR, store=args.attempt_store,
                         observed_model=parsed["observed_model"],
                         proc_outcome=proc.get("outcome"),
                         duration_s=proc.get("duration_s"))
    print(output)
    if rc != 0:
        sys.exit(1)


def cmd_probe(args):
    report = identify(args.cursor_bin, cwd=Path.cwd())
    print(f"cursor identity: {report['identity']} -- {report['reason']}")
    if args.models and report["identity"] == "cursor":
        models = _ca().list_models(args.cursor_bin, cwd=Path.cwd())
        print("models: " + (", ".join(models["models"]) if models["available"]
                            else f"unknown -- {models['reason']}"))
    return None if report["identity"] == "cursor" else sys.exit(3)


def build_parser():
    ap = argparse.ArgumentParser(
        prog="cursor_execute.py",
        description="Run an execution kit against Cursor's headless CLI (`agent -p`) on the "
                    "shared kit contract: parse TASKS.md, dispatch one task, verify it inside "
                    "the execution boundary, write state back. A real run spends the user's "
                    "Cursor allowance; --dry-run spawns nothing.",
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="print each task's status from a kit's TASKS.md")
    p_status.add_argument("--kit", required=True)
    p_status.add_argument("--json", action="store_true")
    p_status.set_defaults(func=cmd_status)

    p_probe = sub.add_parser("probe", help="is --cursor-bin Cursor? read-only; exit 3 if not")
    p_probe.add_argument("--cursor-bin", default=BINARY)
    p_probe.add_argument("--models", action="store_true",
                         help="also list the account's models (`agent models`; network)")
    p_probe.set_defaults(func=cmd_probe)

    p_run = sub.add_parser("run", help="dispatch one task and verify it")
    p_run.add_argument("--kit", required=True)
    p_run.add_argument("--task", help="task id to run (default: first ready pending task)")
    p_run.add_argument("--model", default=None,
                       help="passed to `agent --model` as written; default: the task's pin, "
                            "else the host default. Never resolved through a price list.")
    p_run.add_argument("--cursor-bin", default=BINARY, help="the Cursor CLI binary")
    p_run.add_argument("--extra-arg", action="append",
                       help="extra `agent` flag (repeatable); identity, mode, model, "
                            "workspace, and session flags are refused")
    p_run.add_argument("--parent", default=None,
                       help="mark this run as a consult spawned to rescue TASK_ID")
    p_run.add_argument("--exec-mode", choices=("enforced", "trusted-host"), default="enforced",
                       help="verification confinement (step 05)")
    p_run.add_argument("--rerun", action="store_true", help="allow a task already done")
    p_run.add_argument("--attempt-store", default=None, help="root of the attempt ledger")
    p_run.add_argument("--roster-gap", choices=GAP_MODES, default="stop",
                       help="stop (default) or disclose when PLAN.md declares a role this "
                            "driver cannot run")
    p_run.add_argument("--break-claim", action="store_true",
                       help="clear a claim another run holds on this task; recorded")
    p_run.add_argument("--dry-run", action="store_true",
                       help="print the dispatch argv and verify command; spawn nothing")
    p_run.set_defaults(func=cmd_run)

    p_review = sub.add_parser("review", help="dispatch a read-only phase review (--mode ask)")
    p_review.add_argument("--kit", required=True)
    p_review.add_argument("--phase", required=True)
    p_review.add_argument("--model", default=None)
    p_review.add_argument("--cursor-bin", default=BINARY)
    p_review.add_argument("--extra-arg", action="append")
    p_review.add_argument("--attempt-store", default=None)
    p_review.add_argument("--dry-run", action="store_true")
    p_review.set_defaults(func=cmd_review)
    return ap


def main(argv=None):
    """CLI entry point. `build_parser` is this driver's; the rest is shared."""
    return _CONTRACT.run_cli(build_parser, argv)


if __name__ == "__main__":
    main()
