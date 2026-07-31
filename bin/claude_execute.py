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
STATUSES = ("pending", "in-progress", "done", "blocked")
DEFAULT_ESCALATION_START = "sonnet"  # matches journal_summarize.DEFAULT_START_TIER

EM_DASH = " — "  # spaced em dash — the required task-heading separator

# MEDIUM confidence (PLAN.md Risks "Headless `claude` flag surface") -- pinned from the
# official CLI reference via WebFetch, never live-verified against the real binary (that
# would spend real tokens, which is forbidden). ONE constant: a correction is a one-line edit
# here, never a redesign. Grants unattended tool use (edit/Bash) in `-p` mode, the same role
# `--full-auto` plays for codex_execute and `--allow-all-tools` plays for copilot_execute.
PERMISSION_FLAG = "--dangerously-skip-permissions"


def load_pricing():
    """Load the Claude pricing dict (plain json.load; this driver does not import any
    pricing/scorecard module)."""
    with open(PRICING_PATH) as f:
        return json.load(f)


# ---- parsing (identical TASKS.md contract to codex_execute/copilot_execute -- PLAN D1) ------

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

def _strip_frontmatter(text):
    """Drop a leading `---`-delimited YAML frontmatter block, if present; return the body."""
    lines = text.splitlines(keepends=True)
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "".join(lines[i + 1:])
    return text


def load_preamble(role, slug, repo_root=None):
    """Read `<repo_root>/.claude/agents/<slug>-<role>.md`, strip frontmatter, return the body.

    Unlike codex/copilot's generic per-ROLE bundle files, Claude's kit-agent files are
    per-KIT (the slug is baked into the filename by the architect skill), so `slug` is
    required here. Missing agent file -> FileNotFoundError naming the expected path.
    """
    if repo_root is None:
        repo_root = REPO_ROOT
    repo_root = Path(repo_root)
    path = repo_root / ".claude" / "agents" / f"{slug}-{role}.md"
    if not path.exists():
        raise FileNotFoundError(f"no kit agent at {path}")
    return _strip_frontmatter(path.read_text()).strip()


# ---- dispatch + escalation --------------------------------------------------------------------

def build_dispatch(claude_bin, model_id, prompt, extra_args=()):
    """Build the `claude -p` dispatch argv LIST (never a joined string; never shell=True).

    [claude_bin, "-p"] + (["--model", model_id] if model_id else []) + [PERMISSION_FLAG]
        + list(extra_args) + [prompt]

    `PERMISSION_FLAG` is the non-interactive permission grant (Codex's `--full-auto`/
    Copilot's `--allow-all-tools` analogue -- MEDIUM confidence, see module docstring). A
    model_id of None omits `--model` so the user's configured Claude Code default applies.
    `--extra-arg` feeds future surfaces; no flag is invented beyond what the module docstring
    pins. Flags are best-effort, NOT live-verified -- do NOT re-run the CLI to check them.
    """
    argv = [claude_bin, "-p"]
    if model_id:
        argv += ["--model", model_id]
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


def _evidence(verify_cmd, rc, output):
    return (
        "\n\n--- ESCALATION EVIDENCE (verify failed) ---\n"
        f"verify: {verify_cmd}\n"
        f"exit: {rc}\n"
        f"{(output or '')[-2000:]}"
    )


def run_task(task, pricing, runner, verify_runner, prompt=None, role="implementer",
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

    argv = build_dispatch(claude_bin, model_id, prompt, extra_args=extra_args)
    runner(argv)
    rc, output = verify_runner(verify_cmd)

    if rc != 0:
        ladder = escalation_ladder(pricing, model_id)
        if max_escalations is not None:
            ladder = ladder[:max_escalations]
        for rung in ladder:
            escalated_prompt = prompt + _evidence(verify_cmd, rc, output)
            argv = build_dispatch(claude_bin, rung, escalated_prompt, extra_args=extra_args)
            runner(argv)
            escalations.append(rung)
            model_used = rung
            rc, output = verify_runner(verify_cmd)
            if rc == 0:
                break

    return {
        "id": task["id"],
        "status": "done" if rc == 0 else "blocked",
        "model_used": model_used,
        "escalations": escalations,
        "verify_rc": rc,
    }


# ---- run ids (PLAN D8 -- content-free, one per driver invocation) -----------------------------

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


def build_defect_line(task_id, kind):
    """One `defect:` ledger line in the repo's EXISTING grammar: `defect: <task-id> kind=<kebab>`
    (`bin/routing_scorecard.py`'s `DEFECT_RE`/`parse_defects`; the kinds live in
    `skills/execute/SKILL.md`). No grammar change -- same line family, same field order, an
    already-sanctioned kind. Field order is load-bearing: a line whose first token after
    `defect:` is the kind carries no `kind=` pair and `parse_defects` drops it with an
    "unrecognized defect line" note."""
    return f"defect: {task_id} kind={kind}"


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

def default_runner(argv):
    """Dispatch runner for real runs: `subprocess.run(argv, ...)` -> (rc, stdout+stderr).

    !!! Invoking this with a real `claude` argv spends the user's real tokens and hits the
    network. !!!
    """
    proc = subprocess.run(argv, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def default_verify_runner(cmd):
    """Verify runner for real runs: shell out (verify commands are repo-authored shell lines).

    Same trust model as the kit contract: `subprocess.run(cmd, shell=True, ...)`.
    """
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


# ---- CLI ----------------------------------------------------------------------------------------

def _read_tasks_text(kit_dir):
    path = Path(kit_dir) / "TASKS.md"
    if not path.exists():
        raise FileNotFoundError(f"no TASKS.md under kit dir {kit_dir}")
    return path.read_text()


def _select_task(tasks, task_id=None):
    if task_id is not None:
        for t in tasks:
            if t["id"] == task_id:
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
    preamble = load_preamble(args.role, slug, REPO_ROOT)

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
        task = _select_task(tasks, args.task)
        if task is None:
            print(f"no task with id {args.task!r} in {tasks_path}", file=sys.stderr)
            sys.exit(2)
        model_id = resolve_model(pricing, task["model"])
        prompt = preamble + "\n\n---\n\n" + task["brief"]
        _print_dispatch_preview(task, args.claude_bin, model_id, prompt, extra_args)
        return

    task = _select_task(tasks, args.task)
    if task is None:
        if args.task:
            print(f"no task with id {args.task!r} in {tasks_path}", file=sys.stderr)
        else:
            print(
                f"no eligible pending task (all deps done) in {tasks_path}", file=sys.stderr
            )
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

    verify_cmd = task.get("verify")
    vh = _load_verify_hook_module()
    precheck = vh.run_precheck(str(kit), task["id"], verify_cmd, default_verify_runner)

    result = run_task(
        task, pricing, default_runner, default_verify_runner,
        prompt=prompt, role=args.role, max_escalations=args.max_escalations,
        claude_bin=args.claude_bin, extra_args=extra_args,
    )

    # Neither `run_precheck`'s record nor `run_record`'s refusal may be discarded: a verify
    # command that already passed on the pre-task tree proves nothing about the implementation
    # (PLAN D10), so an `outcome: ... result=pass` written from it would be indistinguishable
    # in the ledger from a genuine red -> green first-try pass -- and NOTES.md is the routing
    # evidence base the scorecard and the next architect read. The refusal therefore (1) rides
    # into NOTES.md as an in-grammar `defect:` line in the same write path as the `outcome:`
    # line, (2) goes to stderr, and (3) makes this command exit nonzero for an unattended
    # caller. It deliberately does NOT block the `done` write: the implementation may be
    # perfectly fine, status follows the verify's exit code, and letting an analysis signal
    # change routing state is the shape PLAN D11 forbids. The ledger carries the honesty label.
    tautological = bool((precheck or {}).get("tautological"))
    refused = False

    if result["status"] == "done":
        ok, message = vh.run_record(str(kit), task["id"], verify_cmd)
        if ok:
            print(message)
        else:
            refused = True
            print(message, file=sys.stderr)

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
    preamble = load_preamble("reviewer", slug, REPO_ROOT)
    body = (
        f"Review phase {args.phase} of the execution kit at {args.kit}. Read "
        f"{args.kit}/PLAN.md (goal, decisions, out-of-scope fence, tripwires) and the tasks "
        f"under '## Phase {args.phase}' in {args.kit}/TASKS.md, then review the actual changes "
        f"for drift, scope creep, and contract breakage. Report findings; change nothing."
    )
    prompt = preamble + "\n\n---\n\n" + body
    argv = build_dispatch(args.claude_bin, None, prompt, extra_args=extra_args)
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
    p_run.add_argument("--dry-run", action="store_true",
                       help="print the dispatch argv and verify command; spawn/write nothing")
    p_run.set_defaults(func=cmd_run)

    p_review = sub.add_parser("review", help="dispatch the reviewer role for a phase")
    p_review.add_argument("--kit", required=True, help="kit directory (contains PLAN.md)")
    p_review.add_argument("--phase", required=True, help="phase number to review")
    p_review.add_argument("--claude-bin", default="claude", help="Claude Code CLI binary")
    p_review.add_argument("--extra-arg", action="append",
                          help="extra dispatch flag (repeatable)")
    p_review.add_argument("--dry-run", action="store_true",
                          help="print the dispatch argv; spawn nothing")
    p_review.set_defaults(func=cmd_review)

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
