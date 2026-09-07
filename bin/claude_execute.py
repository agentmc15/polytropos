#!/usr/bin/env python3
"""Kit-dispatch driver: run an execution kit against Claude Code's non-interactive mode.

This is the Claude-side port of `bin/codex_execute.py` (read that first -- it is the pinned
template for structure, TASKS.md grammar, statuses, writeback, and the injectable-runner
safety seam; graph-convergence PLAN.md D2/T5). It parses a kit's TASKS.md, dispatches each
task to `claude -p` with the kit's generated agent preamble, reruns the task's verify command
through `bin/kit_verify_hook.py` (PLAN D3/D10 -- precheck before dispatch, record after a
pass), escalates up the pricing tiers on failure, and writes statuses + `outcome:` ledger
lines (T1 grammar: `run=`/`parent=`) back to the kit's own NOTES.md. Kits live at
`.claude/kits/<slug>/` in THIS repo -- unlike the Copilot/Codex bundle drivers, this file is
not distributed to consumer repos, so it targets the same kit layout
`bin/kit_verify_hook.py` and `skills/execute/SKILL.md` already use.

============================================================================================
 !!! MONEY / NETWORK SAFETY -- READ THIS BEFORE RUNNING OR TESTING ANYTHING !!!
============================================================================================
A real (non-`--dry-run`) `run`/`review` shells out to the `claude` CLI. `claude -p ...` CALLS
A MODEL: it SPENDS THE USER'S REAL TOKENS and HITS THE NETWORK. NEVER invoke the real `claude`
binary during development or verification.

  * `--dry-run` prints the exact dispatch argv (for EVERY pending task when `--task` is
    omitted) and SPAWNS NOTHING -- writes nothing either, including no verify-pass markers.
  * Every dispatch and every verify goes through an INJECTABLE runner callable
    (`run_task(..., runner=, verify_runner=)`). Tests always inject a fake runner or pass a
    temporary stub executable via `--claude-bin` -- never the real binary, and never one
    reachable through an un-injected default: `default_runner`/`default_verify_runner` are
    only ever wired in by `cmd_run`/`cmd_review`, which no test calls without `--dry-run` or
    a `--claude-bin` stub.
  * `build_dispatch` returns an argv LIST; dispatch never uses `shell=True`.

Dispatch anatomy (best-effort, NOT live-verified -- the codex/copilot `--model`-precedence
precedent, PLAN.md Risks "Headless `claude` flag surface", MEDIUM confidence): `-p`/`--print`
puts the CLI in non-interactive print mode, `--model <id>` pins the model, and
`--dangerously-skip-permissions` (below, ONE module-level constant: `PERMISSION_FLAG`) is the
permission-bypass flag needed so a headless dispatch can actually use tools (edit files, run
Bash) without an interactive prompt -- the same role `--full-auto` plays for Codex and
`--allow-all-tools` plays for Copilot. Checked against the official CLI reference
(https://code.claude.com/docs/en/cli-reference) via WebFetch, never by invoking the real
binary. If reality disagrees with `PERMISSION_FLAG`, that is a ONE-CONSTANT correction, never
a redesign -- do not guess a replacement without checking the docs.

The "kit agent" a task dispatches against is the generated
`.claude/agents/<slug>-<role>.md` file (frontmatter + body -- the architect skill creates the
implementer/verifier/reviewer trio per kit; see NOTES.md's Setup notes). Unlike Codex's
generic `codex/prompts/<role>.md` or Copilot's generic `copilot/.github/agents/<role>.agent.md`
bundle files, Claude's kit-agent files are per-KIT (the slug is embedded in the filename), so
`load_preamble` here takes a `slug` argument. No `{{POLYTROPOS_ROOT}}` placeholder
resolution is needed: `.claude/agents/*.md` files are native to this repo, never a bundle
installed elsewhere.

Tier resolution & escalation (the shared skip-up rule, implemented LOCALLY here against the
loaded `data/pricing.json` dict -- this driver does NOT import any pricing/scorecard module,
mirroring how `codex_execute` does not import `codex_pricing`): a task's `model` field may be
a model id from `data/pricing.json` OR a tier word (`haiku|sonnet|opus|frontier` -- the same
vocabulary `bin/routing_scorecard.py`'s `LIVE_TIER_ORDER` already uses for these model ids'
own `tier` field; a structural constant, never a price). A tier word resolves to the FIRST
model in pricing-file order carrying that tier; if the tier is unpopulated, the next
populated tier UP is used. The escalation ladder walks tiers strictly ABOVE the resolved
model's tier, skipping empty tiers, first model in file order per tier. A task with no
`model` field dispatches WITHOUT `--model` (the user's configured Claude Code default
applies); its escalation ladder starts from `DEFAULT_ESCALATION_START` ("sonnet" -- the same
pin-less default `bin/journal_summarize.py`'s `DEFAULT_START_TIER` already uses for headless
`claude -p` dispatch in this repo). All model ids and tiers are derived at run time from
`data/pricing.json`; nothing here hardcodes a model id or a price.

Verify integration (PLAN D3/D10; do not duplicate `kit_verify_hook.py`'s logic -- call it):
`cmd_run` lazy-loads that module (`_load_verify_hook_module`, mirroring
`copilot_execute._load_prefs_module`'s sibling-import pattern) and calls its real functions
around the UNMODIFIED, verbatim-ported `run_task` core:
  1. `run_precheck(kit_dir, task_id, verify_cmd, verify_runner)` BEFORE the task's first
     dispatch -- this is the freshness mechanism (a `precheck` invalidates any marker from a
     prior attempt) and the tautological-verify (red -> green) check; it prints its own
     `defect:` line when the verify command already passes pre-task.
  2. `run_task(...)` -- dispatch / verify / escalate, structurally identical to
     `codex_execute.run_task` (same signature shape, same ladder-walk algorithm).
  3. `run_record(kit_dir, task_id, verify_cmd)` AFTER a passing verify (any rung) -- writes the
     pass marker, or refuses (D10) if `precheck` marked this exact verify command
     tautological. NEITHER result is discarded. On a refusal (or a `precheck` that flagged the
     verify tautological), `cmd_run`: prints the refusal to STDERR, appends an in-grammar
     `defect: <task-id> kind=tautological-verify` line to the kit's NOTES.md in the SAME write
     path that appends the `outcome:` line, and exits NONZERO so an unattended caller notices.
     A verify that already passed pre-task proves nothing about the implementation, so an
     `outcome: ... result=pass` written from it would read in the ledger exactly like a genuine
     red -> green first-try pass -- and NOTES.md is the routing evidence base the scorecard and
     the next architect consume. What the refusal deliberately does NOT do is block the `done`
     write: the implementation may be fine, status follows the verify's exit code, and letting
     an analysis signal change routing state is the shape PLAN D11 forbids. (`kit_verify_hook.
     hook` likewise only gates a `done` flip made through the Edit tool in an interactive
     session -- it never intercepts this driver's own direct TASKS.md writes. The marker is
     audit evidence this driver produces, not a gate on itself.)
`kit_verify_hook.py` never invokes `claude`/`copilot`/`codex` itself (see its own docstring);
threading the SAME injected `verify_runner` into `run_precheck` keeps this driver's whole
verify path on one seam.

Escalation lineage (`run=`/`parent=`, T1 grammar -- graph-convergence's outcome-line
extension): `run=<UTC-date>-<4 hex>` (`generate_run_id`, PLAN D8, content-free -- no
hostname, username, pid, or path fragment) is generated ONCE per `run` invocation and stamped
on the one `outcome:` line that invocation writes. `parent=` is restricted by
`bin/routing_scorecard.py`'s own parser to a task id DIFFERENT from the outcome's own id (a
task is never its own parent -- `build_lineage` drops a self-referencing parent, and
`parse_outcomes` drops it even earlier). `cmd_run` therefore REJECTS `--parent <the task's own
id>` (exit 2, nothing written) instead of writing a line the reader will ignore: the reader
drops the `parent=` but still counts the `escalated-pass` it caused, which would put one line
into a headline figure and into the "ignored" list at once. Because this driver's escalation ladder walks tiers
for a SINGLE task id, it has no second id to offer on its own -- so `parent=` here is an
explicit `--parent TASK_ID` flag: "this run of TASK_ID is itself a consult spawned to rescue
a DIFFERENT, already-blocked task", the literal reading of the SKILL.md grammar ("the task id
that SPAWNED this outcome ... naming the task the consult was spawned for"). When `--parent`
is given, the run's outcome line is classified `escalated-pass` on success (the whole
dispatch existed to rescue another task) exactly like an in-ladder escalation; without it, an
in-ladder escalation (this task's OWN dispatch needed a higher tier) also produces
`escalated-pass`, with no `parent=` (there is no second task -- this is the common case, and
it mirrors `history_tier_stats`'s own "escalated-pass attributes to the reconstructed
dispatch tier" attribution, which needs no lineage at all). `parent=` is written ONLY on an
escalation result (`PARENT_RESULTS`): a run given `--parent` that ends BLOCKED writes NO
`parent=`, because the reader rejects that placement as out of grammar while still counting the
result it classified -- the same F2 invariant from the writer side (Phases 3-4 review's P34-F2).

Budget dial (T9 -- see the "PLAN.md budget dial" section below for the full contract): an
OPTIONAL `budget: max-dispatches=N max-escalations=N max-consults=N` line in the kit's
PLAN.md, checked against NOTES.md's own recorded history before `cmd_run` dispatches anything.
On a cap already reached, the task is left untouched and ONE `outcome: ... result=budget-stop`
line is written instead -- no new CLI flag, absent block = today's behavior. The one case where
that line is NOT written: the task already carries a recorded `result=` of its own. A
budget-stop is not a verdict and must never displace one (`recorded_outcome_result`).

Step 08 changed WHEN that check happens and WHAT counts. It used to run once, at invocation
entry, and `run_task` then dispatched the initial attempt plus every escalation rung without
asking again -- so `max-dispatches=1` funded one dispatch AND the whole ladder. Admission is
now asked immediately before each consuming operation (`BudgetAdmission`), and operations
carry an explicit KIND, so an initial attempt no longer trips `max-escalations` (declaring
`max-escalations=0` used to refuse to run the first task at all).

COMPATIBILITY. `max-dispatches` keeps exactly its recorded meaning -- initial attempts,
retries, escalations and consults, every model call on a TASK -- and still excludes phase
review and final acceptance, so existing ledgers do not silently start meaning something new.
`max-model-calls` is the separately named cap that does include them.

Usage:
    claude_execute.py status --kit DIR [--json]
    claude_execute.py run --kit DIR [--task ID] [--role NAME] [--claude-bin BIN]
                     [--max-escalations N] [--extra-arg X ...] [--parent TASK_ID] [--dry-run]
    claude_execute.py review --kit DIR --phase N [--claude-bin BIN]
                     [--extra-arg X ...] [--dry-run]
"""

import argparse
import json
import re
import secrets
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PRICING_PATH = REPO_ROOT / "data" / "pricing.json"

# Structural tier VOCABULARY -- matches `bin/routing_scorecard.py`'s LIVE_TIER_ORDER and the
# `tier` values models actually carry in data/pricing.json (haiku/sonnet/opus/frontier).
# Never a price, never a model id; this driver does not import routing_scorecard.
TIER_ORDER = ("haiku", "sonnet", "opus", "frontier")

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

DEFAULT_ESCALATION_START = "sonnet"  # matches journal_summarize.DEFAULT_START_TIER


# MEDIUM confidence (PLAN.md Risks "Headless `claude` flag surface") -- pinned from the
# official CLI reference via WebFetch, never live-verified against the real binary (that
# would spend real tokens, which is forbidden). ONE constant: a correction is a one-line edit
# here, never a redesign. Grants unattended tool use (edit/Bash) in `-p` mode, the same role
# `--full-auto` plays for codex_execute and `--allow-all-tools` plays for copilot_execute.
PERMISSION_FLAG = "--dangerously-skip-permissions"

#: The tool-restriction flag, emitted in the `--flag=value` form. VERIFIED once against Claude
#: Code 2.1.263 on 2026-09-06 (`claude --help`, a no-spend invocation made under explicit
#: one-off user authorisation); the standing rule is unchanged -- tests and kit execution never
#: invoke a real CLI, and nothing re-probes this at run time.
#:
#: The `=` is LOAD-BEARING and not a style choice. The flag is variadic (`<tools...>`), so the
#: separated form swallows the following positional: `--allowedTools 'Bash Read' <prompt>`
#: consumes the prompt as another tool name, and the CLI then fails with "Input must be
#: provided either through stdin or as a prompt argument". Binding the value to the flag keeps
#: the prompt a positional. The value itself is a "comma or space-separated list" in one
#: argument, which is the documented shape (their own example: `"Bash(git *) Edit"`).
ALLOWED_TOOLS_FLAG = "--allowedTools"


def allowed_tools_arg(tools):
    """The single argv element pinning `tools`. See ALLOWED_TOOLS_FLAG on why `=` matters."""
    return f"{ALLOWED_TOOLS_FLAG}={' '.join(tools)}"

#: Roles whose job is to READ and report. They never get a blanket permission grant.
READ_ONLY_ROLES = ("reviewer", "verifier")


def permission_profile(tools=None, bypass=True, source="unspecified"):
    """One dispatch's effective permissions, as a recordable fact.

    `tools`  -- the agent's declared tool pin, translated to `--allowedTools`. None means no
                pin was declared, NOT "no tools".
    `bypass` -- whether the blanket permission grant is added.
    `source` -- why this profile, in words, so a log says what was enforced and why.

    WHAT THIS IS NOT. A tool pin is a CLI-level control, not an OS boundary. In particular,
    these reviewers declare `Bash`, so a pin that omits Write and Edit does NOT make the run
    read-only -- anything reachable through a shell is still reachable. Immutability is a claim
    about the execution boundary (`bin/exec_policy.py`), never about an absent Edit tool.
    """
    return {
        "tools": tuple(tools) if tools else None,
        "bypass": bool(bypass),
        "source": source,
    }


def parse_tools_pin(value):
    """`"Bash, Read, Grep"` -> `("Bash", "Read", "Grep")`; empty/None -> None."""
    if not value:
        return None
    names = tuple(part.strip() for part in str(value).split(",") if part.strip())
    return names or None


def role_permission_profile(role, frontmatter=None, review_mode="restricted"):
    """The profile for `role`, honouring the agent file's own declaration.

    Review roles never receive the blanket grant under the default `restricted` mode. The
    `bypass` mode is the named, recorded opt-out -- it restores the historical behaviour for
    someone who needs it, and says so in `source` rather than looking like enforcement.
    """
    tools = parse_tools_pin((frontmatter or {}).get("tools"))
    if role in READ_ONLY_ROLES:
        if review_mode == "bypass":
            return permission_profile(tools, bypass=True, source=f"{role}: explicit bypass opt-out")
        return permission_profile(tools, bypass=False, source=f"{role}: restricted (no bypass)")
    return permission_profile(tools, bypass=True, source=f"{role}: implementation grant")


def describe_permissions(profile):
    """One line naming what was actually enforced -- for logs and role-use records."""
    tools = ", ".join(profile["tools"]) if profile["tools"] else "no tool pin declared"
    grant = "blanket permission grant" if profile["bypass"] else "no blanket grant"
    return f"permissions[{profile['source']}]: {grant}; tools: {tools}"


def load_pricing():
    """Load the Claude pricing dict (plain json.load; this driver does not import any
    pricing/scorecard module)."""
    with open(PRICING_PATH) as f:
        return json.load(f)


# ---- parsing (identical TASKS.md contract to codex_execute/copilot_execute -- PLAN D1) ------













# ---- tier resolution (skip-up rule, implemented locally -- see module docstring) -------------

def resolve_tier(pricing, tier):
    """The skip-up rule: a tier word -> a model id, skipping empty tiers UPWARD.

    Return the id of the FIRST model in pricing-file order whose `tier` equals `tier`; if that
    tier is unpopulated, retry with the next tier UP in TIER_ORDER (haiku->sonnet->opus->
    frontier), repeating as needed. Unknown tier word -> KeyError listing TIER_ORDER. No
    populated tier at or above the request -> KeyError.
    """
    if tier not in TIER_ORDER:
        raise KeyError(f"unknown tier {tier!r}; valid tiers: {', '.join(TIER_ORDER)}")
    models = pricing["models"]
    start = TIER_ORDER.index(tier)
    for t in TIER_ORDER[start:]:
        for mid, info in models.items():
            if info.get("tier") == t:
                return mid
    raise KeyError(f"roster has no model at or above tier {tier!r}")


def resolve_model(pricing, model_or_tier):
    """Resolve a task `model` field to a model id (or None).

    None -> None (dispatch without `--model`). A key of `pricing["models"]` -> itself. A tier
    word -> `resolve_tier`. Anything else -> KeyError listing valid model ids and tier words.
    """
    if model_or_tier is None:
        return None
    models = pricing["models"]
    if model_or_tier in models:
        return model_or_tier
    if model_or_tier in TIER_ORDER:
        return resolve_tier(pricing, model_or_tier)
    raise KeyError(
        f"unknown model or tier {model_or_tier!r}; valid model ids: "
        f"{', '.join(models)}; valid tiers: {', '.join(TIER_ORDER)}"
    )


# ---- kit-agent preambles (per-slug, unlike codex's/copilot's generic role bundle) -------------

def parse_frontmatter(text):
    """A leading `---` block as `(fields, body)`; `({}, text)` when there is none.

    Deliberately not a YAML parser -- stdlib only, and these agent files use a flat
    `key: value` shape. A line that does not fit that shape is ignored rather than guessed at.

    This exists because the frontmatter is where an agent's `tools:` pin lives, and the pin was
    being DISCARDED: a reviewer declared `tools: Bash, Read, Grep, Glob` and then got a
    dispatch with a blanket permission grant and no tool restriction at all. A declaration
    nothing reads is not a control.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fields = {}
            for raw in lines[1:i]:
                key, sep, value = raw.partition(":")
                if sep and key.strip() and not key.startswith((" ", "\t", "#")):
                    fields[key.strip()] = value.strip()
            return fields, "".join(lines[i + 1:])
    return {}, text


def _strip_frontmatter(text):
    """The body with any leading frontmatter removed (see `parse_frontmatter`)."""
    return parse_frontmatter(text)[1]


def load_preamble(role, slug, repo_root=None):
    """Read `<repo_root>/.claude/agents/<slug>-<role>.md`, strip frontmatter, return the body.

    Unlike codex/copilot's generic per-ROLE bundle files, Claude's kit-agent files are
    per-KIT (the slug is baked into the filename by the architect skill), so `slug` is
    required here. Missing agent file -> FileNotFoundError naming the expected path.
    """
    if repo_root is None:
        repo_root = REPO_ROOT
    repo_root = Path(repo_root)
    return load_role_spec(role, slug, repo_root)[0]


def load_role_spec(role, slug, repo_root=None):
    """`(body, frontmatter)` for a kit agent file -- the preamble AND its declaration.

    `load_preamble` keeps returning just the body for every caller that only needs the prompt;
    the dispatch path uses this one, because the `tools:` pin lives in the half that used to be
    dropped on the floor.
    """
    if repo_root is None:
        repo_root = REPO_ROOT
    repo_root = Path(repo_root)
    path = repo_root / ".claude" / "agents" / f"{slug}-{role}.md"
    if not path.exists():
        raise FileNotFoundError(f"no kit agent at {path}")
    fields, body = parse_frontmatter(path.read_text())
    return body.strip(), fields


# ---- dispatch + escalation --------------------------------------------------------------------

def build_dispatch(claude_bin, model_id, prompt, extra_args=(), permissions=None):
    """Build the `claude -p` dispatch argv LIST (never a joined string; never shell=True).

    [claude_bin, "-p"] + (["--model", model_id] if model_id else []) + [PERMISSION_FLAG]
        + list(extra_args) + [prompt]

    `permissions` is a `permission_profile` -- the agent's declared tool pin and whether this
    dispatch gets the blanket grant. Omitted, it defaults to the implementation grant, which is
    the historical shape. Review paths pass a restricted profile instead, so a role that
    declares `tools:` is dispatched with that pin rather than having it discarded.

    `PERMISSION_FLAG` is the non-interactive permission grant (Codex's `--full-auto`/
    Copilot's `--allow-all-tools` analogue -- MEDIUM confidence, see module docstring). A
    model_id of None omits `--model` so the user's configured Claude Code default applies.
    `--extra-arg` feeds future surfaces; no flag is invented beyond what the module docstring
    pins. Flags are best-effort, NOT live-verified -- do NOT re-run the CLI to check them.
    """
    profile = permissions if permissions is not None else permission_profile(
        source="default: implementation grant"
    )
    argv = [claude_bin, "-p"]
    if model_id:
        argv += ["--model", model_id]
    if profile["tools"]:
        argv += [allowed_tools_arg(profile["tools"])]
    if profile["bypass"]:
        argv += [PERMISSION_FLAG]
    argv += list(extra_args)
    argv += [prompt]
    return argv


def escalation_ladder(pricing, model_id=None):
    """Model ids to escalate through, in ascending tier order, computed from the pricing dict.

    Start tier = the tier of `model_id` in `pricing["models"]` (unknown/None ->
    DEFAULT_ESCALATION_START). For each tier strictly above the start tier in TIER_ORDER,
    take the FIRST model id in file order carrying that tier; tiers with no models are
    skipped (the skip-up rule applied to the ladder). No model ids are hardcoded.
    """
    models = pricing["models"]
    start_tier = DEFAULT_ESCALATION_START
    if model_id is not None and model_id in models:
        tier = models[model_id].get("tier")
        if tier in TIER_ORDER:
            start_tier = tier
    start_idx = TIER_ORDER.index(start_tier)

    ladder = []
    for tier in TIER_ORDER[start_idx + 1:]:
        for mid, info in models.items():
            if info.get("tier") == tier:
                ladder.append(mid)
                break
    return ladder




#: How much dispatch output travels with a failure record. Enough to see the cause; bounded so
#: a crashed process cannot flood the ledger.
DISPATCH_EVIDENCE_LIMIT = 2000



_budget_stop = _CONTRACT._budget_stop
cmd_status = _CONTRACT.cmd_status

#: This driver's bounded, environment-reduced dispatch runner. The body is
#: `kit_contract.provider_runner`; only the provider differs.
default_runner = _CONTRACT.provider_runner("claude")


def main(argv=None):
    """CLI entry point. `build_parser` is this driver's; the rest is shared."""
    return _CONTRACT.run_cli(build_parser, argv)



def _dispatch_failure(task, model_used, escalations, dispatch_rc, dispatch_out):
    """The record for a task whose MODEL PROCESS failed.

    `status` is blocked and `verify_rc` is None -- not zero, and not the verdict of a check
    that ran against a tree this attempt never touched. Dispatch and verification are separate
    facts, and the whole point of this record is that it does not let one stand in for the
    other: a failed process followed by an already-passing check used to read as `done`.
    """
    evidence = " ".join((dispatch_out or "").split())[-DISPATCH_EVIDENCE_LIMIT:]
    return {
        "id": task["id"],
        "status": "blocked",
        "model_used": model_used,
        "escalations": escalations,
        "verify_rc": None,
        "dispatch_rc": dispatch_rc,
        "failure": "dispatch",
        "dispatch_evidence": evidence or "(no output)",
    }


def run_task(task, pricing, runner, verify_runner, prompt=None, role="implementer",
             permissions=None, admission=None, consult=False,
             max_escalations=None, claude_bin="claude", extra_args=()):
    """Orchestrate one task: dispatch, verify, escalate up the tier ladder on failure.

    Ported verbatim in shape from `codex_execute.run_task` (PLAN D2/T5's pinned template) --
    same signature, same algorithm, same return shape. The ONLY structural difference is the
    dispatch flag surface (`build_dispatch` above): this function itself carries no
    Claude-specific knowledge.

    `runner(argv) -> (returncode, output)` and `verify_runner(cmd) -> (returncode, output)`
    are injected callables (the money-safety seam -- never construct a real command in
    tests). `prompt` is the full dispatch text (a kit-agent preamble + the task brief); if
    None it falls back to the raw brief.

    DISPATCH AND VERIFICATION ARE SEPARATE FACTS. The dispatch return code used to be
    discarded, so a model process that crashed, hit an auth error, or was permission-denied
    reported `done` whenever the verify command happened to pass -- which it often does, since
    a check that was already green stays green when nothing was written. A reported non-zero
    dispatch now returns a `failure: "dispatch"` record with `verify_rc: None`, and does NOT
    climb the ladder: an infrastructure failure fails the same way on a more expensive model.
    A runner returning None (the injected-fixture shape) is UNKNOWN, not success.

    Flow: resolve the task's `model` field (id or tier word), dispatch at that model, run
    verify; rc 0 -> `done`. Otherwise walk `escalation_ladder(pricing, resolved)` (truncated
    to `max_escalations` if given), each rung re-dispatching the SAME prompt with the
    verify-failure evidence appended at that rung's model, then re-verifying. First passing
    verify -> `done`; ladder exhausted -> `blocked`.

    Returns {"id", "status", "model_used", "escalations", "verify_rc"}. This function does
    NOT call `kit_verify_hook.py` -- `cmd_run` wraps precheck/record around it (module
    docstring, "Verify integration").
    """
    if prompt is None:
        prompt = task["brief"]
    verify_cmd = task.get("verify")
    model_id = resolve_model(pricing, task.get("model"))
    escalations = []
    model_used = model_id

    initial_kind = "consult" if consult else "initial"
    if admission is not None:
        ok, reason = admission.admit(initial_kind)
        if not ok:
            return _budget_stop(task, model_used, escalations, initial_kind, reason)
    argv = build_dispatch(claude_bin, model_id, prompt, extra_args=extra_args,
                          permissions=permissions)
    dispatch_rc, dispatch_out = dispatch_status(runner(argv))
    if dispatch_rc is not None and dispatch_rc != 0:
        # A FAILED dispatch is not an implementation failure, so it does not climb the ladder:
        # a crashed, unauthenticated or permission-denied process fails the same way on a more
        # expensive model, and the verify command's verdict describes the tree as it was left,
        # not work this attempt did. Stop, and say which fact stopped it.
        return _dispatch_failure(task, model_used, escalations, dispatch_rc, dispatch_out)
    rc, output = verify_runner(verify_cmd)

    if rc != 0:
        ladder = escalation_ladder(pricing, model_id)
        if max_escalations is not None:
            ladder = ladder[:max_escalations]
        for rung in ladder:
            # Admission before EVERY rung, not once at invocation entry. This is the defect:
            # a one-dispatch allowance used to fund the initial attempt plus the whole ladder.
            if admission is not None:
                ok, reason = admission.admit("escalation")
                if not ok:
                    return _budget_stop(task, model_used, escalations, "escalation", reason)
            escalated_prompt = prompt + _evidence(verify_cmd, rc, output)
            # The SAME profile as the initial attempt: an escalation is a bigger model, not
            # a wider grant. Permissions that change on retry are permissions nobody declared.
            argv = build_dispatch(claude_bin, rung, escalated_prompt, extra_args=extra_args,
                                  permissions=permissions)
            dispatch_rc, dispatch_out = dispatch_status(runner(argv))
            escalations.append(rung)
            model_used = rung
            if dispatch_rc is not None and dispatch_rc != 0:
                return _dispatch_failure(task, model_used, escalations, dispatch_rc, dispatch_out)
            rc, output = verify_runner(verify_cmd)
            if rc == 0:
                break

    return {
        "id": task["id"],
        "status": "done" if rc == 0 else "blocked",
        "model_used": model_used,
        "escalations": escalations,
        "verify_rc": rc,
        "dispatch_rc": dispatch_rc,
        "failure": None if rc == 0 else "verification",
    }


# ---- run ids (PLAN D8 -- content-free, one per driver invocation) -----------------------------



# ---- kit_verify_hook integration (PLAN D3/D10 -- lazy sibling import, never duplicated) -------

def _load_verify_hook_module():
    """Lazy-load bin/kit_verify_hook.py via importlib (mirrors
    `copilot_execute._load_prefs_module`'s sibling-import pattern). This driver calls its real
    `run_precheck`/`run_record` functions rather than re-implementing the marker contract."""
    import importlib.util
    path = Path(__file__).resolve().parent / "kit_verify_hook.py"
    spec = importlib.util.spec_from_file_location("kit_verify_hook", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---- outcome ledger (T1 grammar: run=/parent=) -------------------------------------------------



# The `result=` values a `parent=` field may ride on. `bin/routing_scorecard.py`'s
# `build_lineage` keeps a `parent=` ONLY when the carrying outcome's own result is
# `escalated-pass` and drops any other placement with an "out of grammar, ignored" note --
# while `outcome_result` above still classifies that same line, so a rejected `parent=` would
# put one line into a headline figure and into the "ignored" list at once (Phase 1 review's F2
# invariant). `append_note` therefore OMITS `parent=` on any other result rather than writing a
# line the reader rejects. Identical rule in all three drivers (PLAN D1).
PARENT_RESULTS = ("escalated-pass",)




def build_defect_line(task_id, kind):
    """One `defect:` ledger line in the repo's EXISTING grammar: `defect: <task-id> kind=<kebab>`
    (`bin/routing_scorecard.py`'s `DEFECT_RE`/`parse_defects`; the kinds live in
    `skills/execute/SKILL.md`). No grammar change -- same line family, same field order, an
    already-sanctioned kind. Field order is load-bearing: a line whose first token after
    `defect:` is the kind carries no `kind=` pair and `parse_defects` drops it with an
    "unrecognized defect line" note."""
    return f"defect: {task_id} kind={kind}"




















def append_note(notes_path, result, task, run_id=None, parent=None, defect_kind=None):
    """Append a run block to the kit's NOTES.md (created if missing).

    Block: `## <UTC ISO timestamp> — <task id>` then bullet lines for role, model used (or
    `claude default`), escalation chain (`(none)` when empty), `verify: exit <rc>`, and ONE
    machine-readable `outcome:` ledger line (T1 grammar, `build_outcome_line` above) carrying
    `run=` (stamped on every line this driver writes -- PLAN D8 invocation provenance) and
    `parent=` only when supplied AND the classified result is in `PARENT_RESULTS`. Only when
    escalations occurred, a further `lesson-candidate (routing): ...` line (unchanged from the
    codex_execute template).

    A `parent` supplied for a run that ends BLOCKED is silently omitted from the line (not an
    error, not a stdout warning -- a consult that failed is legitimate, and stdout here is
    machine-read): the reader restricts `parent=` to escalation results, so writing it would
    emit a line it reports as ignored while still counting the classification it caused. See
    `PARENT_RESULTS` above.

    `defect_kind` (optional) appends ONE further `defect:` ledger line right after the
    `outcome:` line, in the SAME write path -- so an outcome whose verify could never fail can
    never be written without its honesty label beside it. `cmd_run` passes
    `"tautological-verify"` when `precheck` flagged the verify command or `record` refused the
    pass marker; absent means today's behavior (no defect line at all).
    """
    notes_path = Path(notes_path)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    task_id = task["id"]
    role = result.get("role", "implementer")
    model_used = result.get("model_used")
    model_used_label = model_used if model_used else "claude default"
    escalations = result.get("escalations") or []
    chain = " -> ".join(escalations) if escalations else "(none)"
    rc = result.get("verify_rc")

    block_lines = [
        f"## {ts}{EM_DASH}{task_id}",
        f"- role: {role}",
        f"- model used: {model_used_label}",
        f"- escalations: {chain}",
        f"- verify: exit {rc}",
    ]
    if escalations:
        pinned = task.get("model") or "claude default"
        block_lines.append(
            f"lesson-candidate (routing): task {task_id} pinned {pinned} but needed "
            f"{model_used_label} — record via the lessons-loop skill."
        )

    attempts = 1 + len(escalations)
    outcome_model = model_used if model_used else "unpinned"
    result_word = outcome_result(result.get("status"), escalations, parent)
    line_parent = parent if result_word in PARENT_RESULTS else None
    block_lines.append(
        "- " + build_outcome_line(
            task_id, outcome_model, attempts, result_word, run_id=run_id, parent=line_parent
        )
    )
    if defect_kind:
        block_lines.append("- " + build_defect_line(task_id, defect_kind))

    block = "\n".join(block_lines) + "\n"

    existing = notes_path.read_text() if notes_path.exists() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    separator = "\n" if existing.strip() else ""
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    notes_path.write_text(existing + separator + block)


# ---- default runners (module level, injectable everywhere) ------------------------------------









# ---- CLI ----------------------------------------------------------------------------------------











def _print_dispatch_preview(task, claude_bin, model_id, prompt, extra_args):
    argv = build_dispatch(claude_bin, model_id, prompt, extra_args=extra_args)
    print(f"task: {task['id']}")
    print(f"dispatch: {shlex.join(argv)}")
    print(f"verify: {task['verify']}")


def cmd_run(args):
    kit = Path(args.kit)
    slug = kit.name
    tasks_path = kit / "TASKS.md"
    text = _read_tasks_text(kit)
    tasks = parse_tasks(text)

    pricing = load_pricing()
    extra_args = tuple(args.extra_arg or ())
    preamble, role_frontmatter = load_role_spec(args.role, slug, REPO_ROOT)
    permissions = role_permission_profile(args.role, role_frontmatter)

    if args.dry_run:
        # `--dry-run` with no `--task` previews EVERY pending task (not just the first
        # dependency-eligible one) -- a full plan preview, per T5's acceptance criterion.
        # `--dry-run --task ID` still previews only that one task, same as the sibling
        # drivers. Nothing is spawned or written either way.
        if args.task is None:
            pending = [t for t in tasks if t["status"] == "pending"]
            for t in pending:
                model_id = resolve_model(pricing, t["model"])
                prompt = preamble + "\n\n---\n\n" + t["brief"]
                _print_dispatch_preview(t, args.claude_bin, model_id, prompt, extra_args)
            return
        task, reason = select_task(tasks, args.task, allow_rerun=args.rerun)
        if task is None:
            print(f"{reason} ({tasks_path})", file=sys.stderr)
            sys.exit(2)
        model_id = resolve_model(pricing, task["model"])
        prompt = preamble + "\n\n---\n\n" + task["brief"]
        _print_dispatch_preview(task, args.claude_bin, model_id, prompt, extra_args)
        return

    task, reason = select_task(tasks, args.task, allow_rerun=args.rerun)
    if task is None:
        print(f"{reason} ({tasks_path})", file=sys.stderr)
        sys.exit(2)

    # A task is never its own parent. `bin/routing_scorecard.py` DROPS a self-referencing
    # `parent=` with a note ("parent cannot be its own task id -- ignored") while still counting
    # the `escalated-pass` that `parent=` caused (see `outcome_result`) -- so writing one would
    # put a line into a headline figure and into the ignored list at once, the exact invariant
    # the Phase 1 review adopted (NOTES.md F2). Rejected here at the WRITER, before anything is
    # written, rather than left for the reader to drop.
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

    prompt = preamble + "\n\n---\n\n" + task["brief"]

    run_id = generate_run_id()

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

    verify_cmd = task.get("verify")
    # One confined runner for BOTH the precheck and the task's own verification: the precheck
    # runs the same repo-authored line against the same tree, so it cannot be the unconfined
    # one. `--exec-mode enforced` refuses outright on a host with no backend rather than
    # quietly running it with the parent's privileges.
    verify_runner = _ep().verify_runner(Path.cwd(), mode=args.exec_mode)

    vh = _load_verify_hook_module()
    precheck = vh.run_precheck(
        str(kit), task["id"], verify_cmd, verify_runner, evidence=task.get("evidence")
    )

    result = run_task(
        task, pricing, default_runner, verify_runner,
        prompt=prompt, role=args.role, permissions=permissions,
        admission=admission, consult=bool(args.parent),
        max_escalations=args.max_escalations,
        claude_bin=args.claude_bin, extra_args=extra_args,
    )

    # THE DRIVER AND THE MARKER MUST AGREE (step 09). Both facts are still recorded: the
    # refusal rides into NOTES.md as an in-grammar `defect:` line, goes to stderr, and makes
    # this command exit nonzero.
    #
    # What changed is that a REQUIRED proof no longer fails quietly. This block used to let
    # `done` stand anyway, reasoning that an analysis signal must not change routing state --
    # correct while the rule was BLANKET, because it fired on refactors, docs guards and
    # regression fences where a pre-task pass is the expected result and the task was fine.
    # With `- evidence:` declaring what each task's check has to demonstrate, a red-green
    # task's pre-task pass is no longer an analysis finding: it is that task's required proof
    # failing, and a task whose proof failed is not done. Tasks that legitimately pass
    # beforehand say `- evidence: regression` (or `precondition`) and are never flagged at all.
    #
    # NOT a claim that the marker proves verification ran: `record` is directly callable and
    # PostToolUse fires after the edit lands. The authoritative signal is the driver's OWN
    # verify result; the marker is the cooperative half, and this makes the two agree.
    tautological = bool((precheck or {}).get("tautological"))
    refused = False

    if result["status"] == "done":
        ok, message = vh.run_record(str(kit), task["id"], verify_cmd)
        if ok:
            print(message)
        else:
            refused = True
            print(message, file=sys.stderr)

    if result["status"] == "done" and (tautological or refused):
        result["status"] = "blocked"
        result["failure"] = "required-evidence"
        print(
            f"required-evidence: task {task['id']} declares evidence="
            f"{vh.normalize_evidence(task.get('evidence'))} and its verify command already "
            f"passed on the pre-task tree, so the check demonstrates nothing about this work. "
            f"Status is blocked, NOT done. If the command is protecting behaviour that already "
            f"works, declare `- evidence: regression` on the task; if it is meant to prove a "
            f"change, make it able to fail first.",
            file=sys.stderr,
        )

    defect_kind = "tautological-verify" if (tautological or refused) else None

    text = set_status(text, task["id"], result["status"])
    tasks_path.write_text(text)

    result["role"] = args.role
    append_note(
        kit / "NOTES.md", result, task, run_id=run_id, parent=args.parent,
        defect_kind=defect_kind,
    )

    escalations = result["escalations"] or "(none)"
    print(
        f"task {result['id']}: {result['status']} "
        f"(model_used={result['model_used'] or 'claude default'}, "
        f"escalations={escalations}, verify_rc={result['verify_rc']}, run={run_id})"
    )
    if result["status"] == "blocked" or defect_kind:
        sys.exit(1)


def cmd_review(args):
    kit = Path(args.kit)
    slug = kit.name
    extra_args = tuple(args.extra_arg or ())
    preamble, frontmatter = load_role_spec("reviewer", slug, REPO_ROOT)
    profile = role_permission_profile(
        "reviewer", frontmatter, review_mode=args.review_permissions
    )
    body = (
        f"Review phase {args.phase} of the execution kit at {args.kit}. Read "
        f"{args.kit}/PLAN.md (goal, decisions, out-of-scope fence, tripwires) and the tasks "
        f"under '## Phase {args.phase}' in {args.kit}/TASKS.md, then review the actual changes "
        f"for drift, scope creep, and contract breakage. Report findings; change nothing."
    )
    prompt = preamble + "\n\n---\n\n" + body
    argv = build_dispatch(args.claude_bin, None, prompt, extra_args=extra_args,
                          permissions=profile)
    print(describe_permissions(profile))
    if args.dry_run:
        print(f"phase: {args.phase}")
        print(f"dispatch: {shlex.join(argv)}")
        return
    rc, output = default_runner(argv)
    print(output)
    if rc != 0:
        sys.exit(1)


def build_parser():
    ap = argparse.ArgumentParser(
        prog="claude_execute.py",
        description=(
            "Run an execution kit against Claude Code's non-interactive mode: parse "
            "TASKS.md, dispatch each task via `claude -p` with the kit's generated agent "
            "preamble, verify through kit_verify_hook.py, escalate up the pricing tiers, "
            "write state + outcome ledger lines back. Real runs spend real tokens; "
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
    p_run.add_argument(
        "--role", default="implementer",
        help=".claude/agents/<slug>-<role>.md preamble to prepend (default: implementer)",
    )
    p_run.add_argument("--claude-bin", default="claude", help="Claude Code CLI binary to invoke")
    p_run.add_argument("--max-escalations", type=int, default=None,
                       help="cap the number of escalation rungs")
    p_run.add_argument("--extra-arg", action="append",
                       help="extra dispatch flag (repeatable), e.g. --extra-arg=--verbose")
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
    p_review.add_argument("--claude-bin", default="claude", help="Claude Code CLI binary")
    p_review.add_argument("--extra-arg", action="append",
                          help="extra dispatch flag (repeatable)")
    p_review.add_argument("--review-permissions", choices=("restricted", "bypass"),
                          default="restricted",
                          help="review dispatch permissions (step 06). `restricted` honours the "
                               "reviewer agent's own `tools:` pin and adds NO blanket permission "
                               "grant. `bypass` is the named opt-out that restores the historical "
                               "blanket grant, and is recorded as such — a tool pin is a CLI "
                               "control, not an OS boundary.")
    p_review.add_argument("--dry-run", action="store_true",
                          help="print the dispatch argv; spawn nothing")
    p_review.set_defaults(func=cmd_review)

    return ap




if __name__ == "__main__":
    main()
