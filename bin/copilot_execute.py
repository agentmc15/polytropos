#!/usr/bin/env python3
"""Kit-dispatch driver: run an execution kit against Copilot CLI's custom agents.

This is the Copilot-side port of the Claude plugin's architect -> execute -> verify ->
escalate workflow (PLAN.md D1-D3, D5). It parses a kit's TASKS.md, dispatches each task to a
Copilot custom agent, reruns the task's verify command, escalates up the pricing tiers on
failure, and writes statuses/NOTES back.

============================================================================================
 !!! AI-CREDIT / NETWORK SAFETY — READ THIS BEFORE RUNNING OR TESTING ANYTHING !!!
============================================================================================
A real (non-`--dry-run`) `run`/`review` shells out to the `copilot` CLI. `copilot -p` /
`copilot --agent ...` CALLS A MODEL: it SPENDS THE USER'S REAL AI CREDITS and HITS THE
NETWORK, and the user has a live `~/.copilot` install. NEVER invoke the real `copilot` binary
during development or verification.

  * `--dry-run` prints the exact dispatch argv and SPAWNS NOTHING (writes nothing either).
  * Every dispatch and every verify goes through an INJECTABLE runner callable
    (`run_task(..., runner=, verify_runner=)`). Tests always inject a fake runner or pass a
    temporary stub executable via `--copilot-bin` — never the real binary.
  * `build_dispatch` returns an argv LIST; dispatch never uses `shell=True`.

--model vs. agent frontmatter precedence (kit-contract rule; NOT live-verified):
A task's `model` field is passed as the CLI `--model` flag, which is INTENDED to override the
executing agent's `.agent.md` frontmatter `model:` pin. GitHub documents both mechanisms but
not their interaction; verifying it live would spend AI Credits, so this driver asserts the
kit-contract rule and always passes `--model` when a task pins one (a task with no `model`
dispatches without `--model`, so the agent's frontmatter pin applies). See PLAN.md Risks.

All model ids and tiers are derived at run time from `data/pricing.copilot.json`: the tier
ladder and every dispatch model come from the `models` tier map via this file's own
`load_pricing`, and budget mode's cost math comes from `bin/copilot_pricing.py`, which this
driver DOES import (lazily, via `_load_pricing_module` below, the single home for that math —
`budget_report` calls its `est_cost`, reached from `cmd_run` when `--budget` is given).
Nothing here hardcodes a model id or a price.
(An earlier version of this sentence claimed the driver "does not import `copilot_pricing`" —
false since budget mode landed; see NOTES.md's `stale-plan-decision` entry, which records the
same correction already applied in `bin/codex_execute.py`'s docstring.)

Dispatch stays strictly SEQUENTIAL (PLAN D5) — one task, one dispatch, one verify, at a time;
no fan-out, no concurrency. This was cut from scope deliberately: fan-out on a paid harness
only buys wall-clock time while multiplying real AI-Credit spend, and this kit's priority is
accuracy and cost, not speed. `run_task` below issues its dispatches in a single-threaded loop
and never spawns more than one `runner`/`verify_runner` call in flight.

Id stamping + lineage (T1 grammar — graph-convergence's outcome-line extension, PLAN D8/T7):
`cmd_run` generates ONE `run=<UTC-date>-<4 hex>` id per invocation (`generate_run_id`,
content-free — no hostname, username, pid, or path fragment) and:
  * embeds `kit=<slug> run=<run id> task=<task id>` as a bracketed preamble line at the FRONT
    of the dispatch prompt `build_dispatch` sends to `-p` (visible in `--dry-run`'s printed
    argv) — every dispatch this run makes (initial + each escalation rung) carries the SAME
    run id and task id, so a transcript alone identifies which invocation and which task
    produced it. Absent `kit`/`run_id`/`task_id`, `build_dispatch` builds the exact prompt it
    always has — the preamble is purely additive (PLAN D6).
  * stamps `run=` on the ONE `outcome:` ledger line the invocation writes (every outcome line,
    a clean pass included — Phase 1 review F1's resolved reading).
  * accepts an explicit `--parent TASK_ID` flag: this run of the SELECTED task is itself a
    consult spawned to rescue a DIFFERENT, already-blocked task. Because the escalation ladder
    here walks tiers for a SINGLE task id, an in-ladder escalation has no second id to name —
    `--parent` is the only way to write the lineage grammar's `parent=` field (same shape as
    `bin/claude_execute.py`'s T5 flag; the acceptance bullet "escalation outcomes carry
    parent=" is otherwise unsatisfiable, a brief defect T5 recorded first). `--parent` equal
    to the task actually being run is REJECTED at the writer (exit 2, nothing written, nothing
    dispatched) — `bin/routing_scorecard.py` drops a self-referencing `parent=` with a note
    while still counting the `escalated-pass` it caused, so writing one would put a single
    line into a headline figure and into the "ignored" list at once (Phase 1 review's F2
    invariant; Phase 2 review's F-E finding against an earlier driver that shipped without
    this guard). `parent=` is written ONLY on an escalation result (`PARENT_RESULTS`): a run
    given `--parent` that ends BLOCKED writes NO `parent=`, because the reader rejects that
    placement as out of grammar while still counting the result it classified — the same F2
    invariant from the writer side (Phases 3-4 review's P34-F2).
This driver has no verify-marker/hook integration today (unlike `bin/claude_execute.py`'s
`kit_verify_hook.py` wiring) — none is added here; that would be new scope.

Budget dial (T9 -- see the "PLAN.md budget dial" section below for the full contract, and its
own banner distinguishing it from this driver's pre-existing `--budget`/`cmd_budget`
dollar-savings mode): an OPTIONAL `budget: max-dispatches=N max-escalations=N
max-consults=N` line in the kit's PLAN.md, checked against NOTES.md's own recorded history
before `cmd_run` dispatches anything. On a cap already reached, the task is left untouched and
ONE `outcome: ... result=budget-stop` line is written instead -- no new CLI flag, absent block
= today's behavior. The one case where that line is NOT written: the task already carries a
recorded `result=` of its own. A budget-stop is not a verdict and must never displace one
(`recorded_outcome_result`).

Usage:
    copilot_execute.py status --kit DIR [--json]
    copilot_execute.py run --kit DIR [--task ID] [--agent NAME] [--copilot-bin BIN]
                        [--max-escalations N] [--extra-arg X ...]
                        [--pin TIER=MODEL_ID ...] [--exclude MODEL_ID ...] [--prefs FILE]
                        [--no-prefs] [--parent TASK_ID] [--dry-run]
    copilot_execute.py review --kit DIR --phase N [--copilot-bin BIN]
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

PRICING_PATH = Path(__file__).resolve().parent.parent / "data" / "pricing.copilot.json"

TIER_ORDER = ("cheap", "mid", "strong", "frontier")
STATUSES = ("pending", "in-progress", "done", "blocked")
DEFAULT_ESCALATION_START = "mid"

EM_DASH = " — "  # spaced em dash — the required task-heading separator


def load_pricing():
    """Load the Copilot pricing dict (plain json.load; only the models tier map is used)."""
    with open(PRICING_PATH) as f:
        return json.load(f)


_prefs_mod = None


def _load_prefs_module():
    """Lazy-load bin/copilot_prefs.py (the single home for prefs logic) via importlib."""
    global _prefs_mod
    if _prefs_mod is None:
        import importlib.util
        path = Path(__file__).resolve().parent / "copilot_prefs.py"
        spec = importlib.util.spec_from_file_location("copilot_prefs", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _prefs_mod = mod
    return _prefs_mod


_pricing_mod = None


def _load_pricing_module():
    """Lazy-load bin/copilot_pricing.py (the single home for cost math) via importlib."""
    global _pricing_mod
    if _pricing_mod is None:
        import importlib.util
        path = Path(__file__).resolve().parent / "copilot_pricing.py"
        spec = importlib.util.spec_from_file_location("copilot_pricing", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _pricing_mod = mod
    return _pricing_mod


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
            # Tolerance: an architect model may backtick-format the pin (`- model: `id``);
            # strip a single surrounding backtick pair so the natural drift still parses.
            if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
                value = value[1:-1].strip()
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


# ---- dispatch + escalation ------------------------------------------------------------------

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


def build_dispatch(agent, brief, model=None, copilot_bin="copilot", extra_args=(),
                    kit=None, run_id=None, task_id=None):
    """Build the dispatch argv LIST (never a joined string; dispatch never uses shell=True).

    [copilot_bin, "--agent", agent] + (["--model", model] if model else [])
        + ["--allow-all-tools"] + list(extra_args) + ["-p", prompt]

    `prompt` is `brief` unless one of `kit`/`run_id`/`task_id` is given, in which case it is
    `build_id_preamble(kit, run_id, task_id) + "\\n\\n" + brief` — the T7 lineage preamble
    (PLAN D8), visible to both the dispatched agent and `--dry-run`'s printed argv. Absent all
    three, `prompt == brief` exactly as before this feature existed (PLAN D6).

    Flags are confirmed from `copilot --help` and pinned in PLAN.md — do NOT re-run the CLI.
    """
    preamble = build_id_preamble(kit=kit, run_id=run_id, task_id=task_id)
    prompt = f"{preamble}\n\n{brief}" if preamble else brief
    argv = [copilot_bin, "--agent", agent]
    if model:
        argv += ["--model", model]
    argv += ["--allow-all-tools"]
    argv += list(extra_args)
    argv += ["-p", prompt]
    return argv


def escalation_ladder(pricing, model_id=None, prefs=None):
    """Model ids to escalate through, in ascending tier order, computed from the pricing dict.

    Start tier = the tier of `model_id` in `pricing["models"]` (unknown/None ->
    DEFAULT_ESCALATION_START). For each tier strictly above the start tier in TIER_ORDER,
    take the FIRST model id in file order carrying that tier; tiers with no models are
    skipped. No model ids are hardcoded — all come from the dict.

    `prefs=None` is byte-equivalent to today (same code path, same result). With `prefs` (a
    dict shaped like `copilot_prefs.effective_prefs`'s return value): a tier's rung is
    `prefs["pins"][tier]` when that tier is pinned (the pin wins outright, no file-order
    scan), else the first model in file order carrying that tier which is NOT in
    `prefs["excludes"]`; a tier yielding nothing — emptied by exclusion, or simply absent
    from the roster — is skipped exactly like today's empty-tier case (an emptied frontier
    with no replacing pin means the ladder tops out lower, never a fabricated rung). A rung
    that would equal `model_id` or an earlier rung already added is skipped too (no
    pointless re-dispatch to the model already running).
    """
    models = pricing["models"]
    start_tier = DEFAULT_ESCALATION_START
    if model_id is not None and model_id in models:
        tier = models[model_id].get("tier")
        if tier in TIER_ORDER:
            start_tier = tier
    start_idx = TIER_ORDER.index(start_tier)

    if prefs is None:
        ladder = []
        for tier in TIER_ORDER[start_idx + 1:]:
            for mid, info in models.items():
                if info.get("tier") == tier:
                    ladder.append(mid)
                    break
        return ladder

    pins = prefs.get("pins") or {}
    excludes = set(prefs.get("excludes") or [])
    seen = {model_id} if model_id is not None else set()
    ladder = []
    for tier in TIER_ORDER[start_idx + 1:]:
        rung = pins.get(tier)
        if rung is None:
            for mid, info in models.items():
                if info.get("tier") == tier and mid not in excludes:
                    rung = mid
                    break
        if rung is None or rung in seen:
            continue
        ladder.append(rung)
        seen.add(rung)
    return ladder


def budget_demote(pricing, model_id=None, prefs=None):
    """Compute the ONE-rung budget demotion for a dispatch (PLAN D3/D6).

    Returns a dict `{"standard_model", "standard_tier", "target_tier", "dispatched_model",
    "demoted", "notes"}`. Tier->model resolution is done ONLY via
    `copilot_prefs.resolve_tier(pricing, target_tier, prefs)` -- never a re-implemented scan.

    - `model_id is None` (pin-less task): `standard_tier = DEFAULT_ESCALATION_START`,
      `standard_model = None`, a note stating the assumption, then demotion proceeds from
      that tier exactly like a pinned task would.
    - `model_id` not a key of `pricing["models"]`, or its tier not in `TIER_ORDER`: no
      demotion -- `dispatched_model = model_id`, `demoted = False`, `target_tier = None`,
      with a "cannot demote" note.
    - `standard_tier == TIER_ORDER[0]` (already the floor): no demotion, floor note.
    - Otherwise `target_tier` is the tier directly below `standard_tier` in `TIER_ORDER`;
      `resolve_tier(pricing, target_tier, prefs)` either wins outright (a pin), resolves to
      nothing (empty/fully excluded tier -- no demotion, never a two-rung jump), resolves
      back to `model_id` (no-op), resolves to a model whose OWN recorded tier is not
      strictly below `standard_tier` (a cross-tier pin overreaching -- no demotion, it did
      not actually demote anything), or resolves to a genuinely different, genuinely lower
      model (demoted).
    - In every no-demotion case, `dispatched_model` is `model_id` (which may be `None` ->
      dispatch without `--model`, agent default).
    """
    models = pricing["models"]
    notes = []

    if model_id is None:
        standard_model = None
        standard_tier = DEFAULT_ESCALATION_START
        notes.append(
            f"task has no model pin — standard tier assumed {DEFAULT_ESCALATION_START} "
            "(agent default)"
        )
    else:
        standard_model = model_id
        if model_id not in models:
            notes.append(
                f"cannot demote {model_id} — not a live pricing id; dispatching as pinned"
            )
            return {
                "standard_model": standard_model,
                "standard_tier": None,
                "target_tier": None,
                "dispatched_model": model_id,
                "demoted": False,
                "notes": notes,
            }
        tier = models[model_id].get("tier")
        if tier not in TIER_ORDER:
            notes.append(
                f"cannot demote {model_id} — has no recognized tier; dispatching as pinned"
            )
            return {
                "standard_model": standard_model,
                "standard_tier": None,
                "target_tier": None,
                "dispatched_model": model_id,
                "demoted": False,
                "notes": notes,
            }
        standard_tier = tier

    if standard_tier == TIER_ORDER[0]:
        notes.append(f"already at the {TIER_ORDER[0]} floor — no demotion")
        return {
            "standard_model": standard_model,
            "standard_tier": standard_tier,
            "target_tier": None,
            "dispatched_model": model_id,
            "demoted": False,
            "notes": notes,
        }

    target_tier = TIER_ORDER[TIER_ORDER.index(standard_tier) - 1]
    candidate = _load_prefs_module().resolve_tier(pricing, target_tier, prefs)

    if candidate is None:
        notes.append(
            f"tier {target_tier!r} resolves to nothing (empty or fully excluded) — no "
            "demotion, never a two-rung jump"
        )
        return {
            "standard_model": standard_model,
            "standard_tier": standard_tier,
            "target_tier": target_tier,
            "dispatched_model": model_id,
            "demoted": False,
            "notes": notes,
        }

    if candidate == model_id:
        notes.append(f"tier {target_tier!r} resolves back to {model_id} — no demotion")
        return {
            "standard_model": standard_model,
            "standard_tier": standard_tier,
            "target_tier": target_tier,
            "dispatched_model": model_id,
            "demoted": False,
            "notes": notes,
        }

    # A3 fix: a pin can point `target_tier` at a model whose OWN recorded tier is not
    # strictly below `standard_tier` (e.g. a `cheap` pin resolving to a `strong` model).
    # Dispatching it would not actually be a demotion, so don't claim one.
    cand_tier = models.get(candidate, {}).get("tier")
    if cand_tier not in TIER_ORDER or TIER_ORDER.index(cand_tier) >= TIER_ORDER.index(standard_tier):
        notes.append(
            f"tier {target_tier!r} is pinned to {candidate} (tier {cand_tier}) — not below "
            f"{standard_tier}; no demotion"
        )
        return {
            "standard_model": standard_model,
            "standard_tier": standard_tier,
            "target_tier": target_tier,
            "dispatched_model": model_id,
            "demoted": False,
            "notes": notes,
        }

    notes.append(f"demoted {standard_tier} -> {target_tier}: {candidate}")
    return {
        "standard_model": standard_model,
        "standard_tier": standard_tier,
        "target_tier": target_tier,
        "dispatched_model": candidate,
        "demoted": True,
        "notes": notes,
    }


def budget_report(pricing, binfo, escalations, profile, prefs=None):
    """Estimate actual-vs-standard cost of a budget run (PLAN D5 — estimates only, labeled).

    `binfo` is a `budget_demote` result dict; `escalations` is the run's escalation chain
    (model ids, in order). The "actual" chain is `[binfo["dispatched_model"]] +
    list(escalations)` -- every dispatch that really happened. The "standard" side is
    `binfo["standard_model"]`, or -- for a pin-less task -- `resolve_tier(pricing,
    binfo["standard_tier"], prefs)` (via `copilot_prefs.resolve_tier`, the ONLY tier->model
    resolution used here), labeled `f"assumed-{standard_tier}"`.

    Cost math is ONLY ever `_load_pricing_module().est_cost(...)` -- never re-implemented.
    Any chain entry of `None` (an agent-default dispatch the driver cannot price), a standard
    tier that resolves to nothing, or an `est_cost` `KeyError` (unknown profile/model id)
    degrades to an unpriced result -- dollars are never fabricated.

    T8 item 2: a run that made NO demotion (`binfo["demoted"]` is falsy -- floor-pinned,
    unknown-id, or an empty/fully-excluded target tier) dispatches the identical chain
    standard would have, so pricing it against a single first-try standard dispatch and
    calling any escalation-driven cost growth `BACKFIRED` would blame budget mode for a
    difference it never caused. Such a run is never priced at all -- it short-circuits to
    `{"priced": False, "not_counted": True, "reason", "profile"}` BEFORE any chain/cost work.

    Returns `{"priced": True, "standard_label", "standard_usd", "standard_aic", "actual_usd",
    "actual_aic", "dispatches", "delta_usd", "profile"}`, `{"priced": False, "not_counted":
    True, "reason", "profile"}` (no demotion occurred), or `{"priced": False, "reason",
    "profile"}` (unpriceable for some other reason) -- never more than one shape at once.
    """
    if not binfo.get("demoted"):
        return {
            "priced": False,
            "not_counted": True,
            "reason": "no demotion — budget mode changed nothing this run",
            "profile": profile,
        }

    chain = [binfo["dispatched_model"]] + list(escalations)
    if any(model_id is None for model_id in chain):
        return {
            "priced": False,
            "reason": "dispatched at agent default — model unknown to the driver",
            "profile": profile,
        }

    standard = binfo["standard_model"]
    if standard is None:
        standard_tier = binfo["standard_tier"]
        standard = _load_prefs_module().resolve_tier(pricing, standard_tier, prefs)
        standard_label = f"assumed-{standard_tier}"
        if standard is None:
            return {
                "priced": False,
                "reason": f"no model resolves for the assumed standard tier {standard_tier!r}",
                "profile": profile,
            }
    else:
        standard_label = standard

    pricing_mod = _load_pricing_module()
    try:
        standard_cost = pricing_mod.est_cost(pricing, profile, standard)
        actual_usd = 0.0
        actual_aic = 0.0
        for model_id in chain:
            leg = pricing_mod.est_cost(pricing, profile, model_id)
            actual_usd += leg["usd"]
            actual_aic += leg["aic"]
    except KeyError as e:
        return {
            "priced": False,
            "reason": str(e),
            "profile": profile,
        }

    standard_usd = standard_cost["usd"]
    standard_aic = standard_cost["aic"]

    return {
        "priced": True,
        "standard_label": standard_label,
        "standard_usd": standard_usd,
        "standard_aic": standard_aic,
        "actual_usd": actual_usd,
        "actual_aic": actual_aic,
        "dispatches": len(chain),
        "delta_usd": standard_usd - actual_usd,
        "profile": profile,
    }


def _evidence(verify_cmd, rc, output):
    return (
        "\n\n--- ESCALATION EVIDENCE (verify failed) ---\n"
        f"verify: {verify_cmd}\n"
        f"exit: {rc}\n"
        f"{(output or '')[-2000:]}"
    )


def _effective_task_model(task, pricing, prefs):
    """Resolve the model the INITIAL dispatch should actually use, honoring `prefs`.

    `prefs=None` is a pure passthrough: returns `(task.get("model"), [])` — no substitution
    logic engaged, byte-equivalent to pre-prefs behavior. This is the ONE place the
    task-model-vs-excludes substitution lives; both `run_task` and `cmd_run`'s dry-run path
    call it so the logic exists once.

    With `prefs`: if the task pins a model AND that model id is in `prefs["excludes"]`,
    substitute `copilot_prefs.resolve_tier(pricing, own_tier, prefs)`, where `own_tier` is
    the pinned model's own tier (`pricing["models"][task_model]["tier"]`). If the task's
    model is not itself a live pricing key, there is nothing to resolve — no substitution.
    A substitution appends one note to the returned list. If nothing resolves for that tier
    (prefs pin wins, else next in file order, else nothing), the initial dispatch never
    silently jumps tiers — raises:
    `ValueError(f"task pins {task_model}, which is excluded, and nothing else resolves for
    tier {own_tier!r} — un-exclude a model or add a --pin for that tier")`.
    """
    model = task.get("model")
    if prefs is None or model is None:
        return model, []

    excludes = prefs.get("excludes") or []
    if model not in excludes:
        return model, []

    models = pricing["models"]
    if model not in models:
        return model, []

    own_tier = models[model].get("tier")
    substitute = _load_prefs_module().resolve_tier(pricing, own_tier, prefs)
    if substitute is None:
        raise ValueError(
            f"task pins {model}, which is excluded, and nothing else resolves for tier "
            f"{own_tier!r} — un-exclude a model or add a --pin for that tier"
        )
    return substitute, [f"task pinned {model} (excluded) — dispatching {substitute} instead"]


def run_task(task, pricing, runner, verify_runner, agent="implementer",
             max_escalations=None, copilot_bin="copilot", extra_args=(), prefs=None,
             budget=False, kit=None, run_id=None):
    """Orchestrate one task: dispatch, verify, escalate up the tier ladder on failure.
    Strictly SEQUENTIAL (PLAN D5) — one dispatch in flight at a time, never fanned out.

    `runner(argv) -> (returncode, output)` and `verify_runner(cmd) -> (returncode, output)`
    are injected callables (the AIC-safety seam — never construct a real command in tests).

    Flow: dispatch at the task's pinned model, run verify; rc 0 -> `done`. Otherwise walk
    `escalation_ladder(pricing, task["model"])` (truncated to `max_escalations` if given),
    each rung re-dispatching the SAME brief with the verify-failure evidence appended at that
    rung's model, then re-verifying. First passing verify -> `done`; ladder exhausted ->
    `blocked`.

    `prefs=None` is byte-equivalent to today (same initial model, same ladder, same result
    keys). With `prefs`: the initial dispatch model is
    `_effective_task_model(task, pricing, prefs)` (substitutes an excluded task pin — see its
    docstring; raises `ValueError` if nothing resolves), and the ladder call becomes
    `escalation_ladder(pricing, effective_model, prefs=prefs)`. The result gains ONE
    additive key, `prefs_notes` (the substitution notes list), ONLY when `prefs is not None`.

    `budget=False` (default) is byte-identical behavior and result keys to today. With
    `budget=True`: after resolving the effective model, `budget_demote(pricing, model, prefs)`
    computes a one-rung-lower dispatch (PLAN D3); the initial dispatch and the escalation
    ladder both start from `binfo["dispatched_model"]` (so the first escalation rung is the
    standard tier the task would have started at). The result gains ONE additive key,
    `"budget"` (the `budget_demote` dict), ONLY when `budget` is true.

    `kit`/`run_id` (T7, PLAN D8) thread through to EVERY `build_dispatch` call this function
    makes -- initial dispatch and every escalation rung -- as the `kit=`/`run_id=`/`task_id=`
    id-preamble arguments; `task_id` is `task["id"]` whenever `kit` or `run_id` is given, else
    `None` (a bare call with neither -- every pre-T7 caller -- dispatches the exact prompt it
    always has; PLAN D6). Both `kit`/`run_id` default to `None`.

    Returns {"id", "status", "model_used", "escalations", "verify_rc"} (plus `prefs_notes`
    when `prefs is not None`, plus `budget` when `budget` is true).
    """
    # `task_id` only rides into the id preamble when the caller is actually using the T7
    # lineage feature (`kit` or `run_id` given) -- a bare `run_task(...)` call with neither
    # (every pre-T7 test, and any future direct caller that doesn't care about ids) dispatches
    # the EXACT prompt it always has, no surprise `[task=...]` prefix (PLAN D6).
    task_id = task["id"] if (kit is not None or run_id is not None) else None
    brief = task["brief"]
    verify_cmd = task.get("verify")
    model, prefs_notes = _effective_task_model(task, pricing, prefs)

    binfo = None
    if budget:
        binfo = budget_demote(pricing, model, prefs)
        model = binfo["dispatched_model"]

    escalations = []
    model_used = model

    argv = build_dispatch(
        agent, brief, model, copilot_bin=copilot_bin, extra_args=extra_args,
        kit=kit, run_id=run_id, task_id=task_id,
    )
    runner(argv)
    rc, output = verify_runner(verify_cmd)

    if rc != 0:
        if budget and binfo["standard_model"] is not None and binfo["standard_model"] != model:
            # B1 fix (PLAN D4 -- "standard + one cheap attempt" bound): the first escalation
            # rung under budget MUST be the task's OWN pinned standard model, never a tier
            # rescan. escalation_ladder seeds its dedup set from the model it's given, so
            # computing it from the demoted model (as before) drops the standard model out of
            # that set -- it can then reappear AND the tier scan can resolve to a different
            # model than the task's own pin, growing the chain by two instead of one. Prepend
            # the exact pin, then continue the ladder as if standard_model had been the
            # initial dispatch (its own seed excludes it, so no duplicate).
            ladder = [binfo["standard_model"]] + escalation_ladder(
                pricing, binfo["standard_model"], prefs=prefs
            )
        else:
            ladder = escalation_ladder(pricing, model, prefs=prefs)
        if max_escalations is not None:
            ladder = ladder[:max_escalations]
        for rung in ladder:
            escalated_brief = brief + _evidence(verify_cmd, rc, output)
            argv = build_dispatch(
                agent, escalated_brief, rung, copilot_bin=copilot_bin, extra_args=extra_args,
                kit=kit, run_id=run_id, task_id=task_id,
            )
            runner(argv)
            escalations.append(rung)
            model_used = rung
            rc, output = verify_runner(verify_cmd)
            if rc == 0:
                break

    result = {
        "id": task["id"],
        "status": "done" if rc == 0 else "blocked",
        "model_used": model_used,
        "escalations": escalations,
        "verify_rc": rc,
    }
    if prefs is not None:
        result["prefs_notes"] = prefs_notes
    if budget:
        result["budget"] = binfo
    return result


# ---- run ids (PLAN D8 -- content-free, one per driver invocation) -----------------------------

def generate_run_id(now=None):
    """One content-free `run=` id per driver invocation: `<UTC-date>-<4 hex>` (PLAN D8).

    Ported verbatim in shape from `bin/claude_execute.py`'s T5 function (the resolved,
    reviewed design for this exact requirement — PLAN D8 pins the format, T7 inherits it
    rather than re-deriving it). `secrets.token_hex(2)` supplies the four hex characters from
    2 cryptographically random bytes -- never a hostname, username, pid, or path fragment
    (NOTES.md is committed in consumer repos, so nothing content-bearing may enter it). `now`
    is injectable so tests can pin the date segment without touching wall-clock time; the hex
    segment is always freshly random.
    """
    now = now or datetime.now(timezone.utc)
    return f"{now.strftime('%Y-%m-%d')}-{secrets.token_hex(2)}"


# ---- outcome ledger (T1 grammar: run=/parent=) -------------------------------------------------

def outcome_result(status, escalations, parent):
    """Classify a finished `run_task` result into the T1 `result=` vocabulary.

    `blocked` when the task never passed. Otherwise `escalated-pass` when the ladder needed a
    rung beyond the task's own pinned tier (`escalations` non-empty) OR this run was itself a
    consult for a different task (`parent` given). Otherwise plain `pass`.
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
# same constant names, same parse helper shape, same stop semantics, same ledger line).
#
# NOT to be confused with this driver's PRE-EXISTING `--budget`/`--budget-profile` CLI flags
# and `cmd_budget` subcommand (PLAN D5, a completely different feature: a one-tier-cheaper
# dispatch ladder plus a dollar-savings estimate, local to THIS driver, with its own `budget:`
# NOTES.md line prefix and its own `-budget`-named locals/constants throughout the file). The
# PLAN.md dial below intentionally uses a `plan_budget`-prefixed vocabulary everywhere (never a
# bare `budget` local or constant) so the two concepts never collide in this file's namespace,
# even though they happen to share an English word.
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
    compatible, matching the outcome-ledger's own unknown-`key=value` tolerance). NOT the same
    thing as this driver's `--budget`/`cmd_budget` dollar-savings feature -- see the section
    banner above.
    """
    if not text:
        return None
    m = PLAN_BUDGET_RE.search(text)
    if not m:
        return None
    parsed = dict(re.findall(r"(max-dispatches|max-escalations|max-consults)=(\d+)", m.group(1)))
    return {k: int(v) for k, v in parsed.items()} or None


def count_plan_budget_usage(notes_text):
    """Count dispatches/escalations/consults already recorded in a kit's NOTES.md ledger.

    A minimal re-implementation of `routing_scorecard`'s own `outcome:` grammar, read-only
    over `notes_text` (this is a SEPARATE parse from `cmd_budget`'s own `- budget: ...` line
    scan -- different line family, different purpose). Per `outcome:` line: `attempts=`
    (default 1 when absent or non-integer, mirroring `routing_scorecard.parse_outcomes`)
    counts toward `max-dispatches`; `attempts - 1` counts toward `max-escalations` (an
    in-ladder escalation IS an extra dispatch); a line carrying `parent=` counts ONE
    `max-consults` (a run dispatched with `--parent` is a consult by definition, whether it
    passed, was blocked, or was itself a budget-stop). Returns a dict with all three
    `PLAN_BUDGET_KEYS`, always present (0 when nothing is recorded yet).
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
                                  agent):
    """Append ONE budget-stop block to the kit's NOTES.md -- the T9 "never hide the stop
    behind a fluent summary" contract. No dispatch happened: `attempts=0`, no escalations, no
    model was actually used (the task's OWN pin, or `unpinned`, labels the line). The block
    states plainly which PLAN.md budget cap was hit, the used/cap counts, and how many pending
    tasks (including this one -- none of them were touched) remain, as its own bullet lines --
    never folded into prose. Structurally the same append-only block shape as `append_note`
    (created if missing, one blank-line-separated block appended), and the SAME
    `build_outcome_line` -- carries `run=` (always, since `cmd_run` always generates one) and
    never `parent=` (a budget-stopped run is not counted as lineage; see `PARENT_RESULTS`,
    which `budget-stop` is deliberately not a member of). `agent` (not `role` -- this driver
    labels its dispatch role `- agent:`, matching `append_note`'s own convention) is the
    Copilot agent name (`args.agent`).
    """
    notes_path = Path(notes_path)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    task_id = task["id"]
    model_label = task.get("model") or "unpinned"
    block_lines = [
        f"## {ts}{EM_DASH}{task_id}",
        f"- agent: {agent}",
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


def append_note(notes_path, result, task, run_id=None, parent=None):
    """Append a run block to the kit's NOTES.md (created if missing).

    Block: `## <UTC ISO timestamp> — <task id>` then bullet lines for agent, model used (or
    `agent default`), escalation chain (`(none)` when empty), and `verify: exit <rc>`. When
    `result` carries both `"budget"` and `"budget_report"` (PLAN D5), ONE further
    `- budget: ...` line lands directly after the verify line (see `_load_pricing_module`'s
    caller in `cmd_run` for how those keys get set) — absent either key, this block is
    byte-identical to today. Only when escalations occurred, a further line beginning
    `lesson-candidate (routing): ...` (the line D7 wires into the lessons-loop skill). Finally
    ONE machine-readable `outcome:` ledger line is ALWAYS appended (T1 grammar,
    `build_outcome_line` above -- ported in shape from `bin/claude_execute.py`'s T5
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
    agent = result.get("agent", "implementer")
    model_used = result.get("model_used")
    model_used_label = model_used if model_used else "agent default"
    escalations = result.get("escalations") or []
    chain = " -> ".join(escalations) if escalations else "(none)"
    rc = result.get("verify_rc")

    block_lines = [
        f"## {ts}{EM_DASH}{task_id}",
        f"- agent: {agent}",
        f"- model used: {model_used_label}",
        f"- escalations: {chain}",
        f"- verify: exit {rc}",
    ]
    if "budget" in result and "budget_report" in result:
        binfo = result["budget"]
        report = result["budget_report"]
        standard_token = binfo["standard_model"] or f"assumed-{binfo['standard_tier']}"
        # A5 fix: render an agent-default leg (`None`) as the literal token `agent-default`
        # in place, instead of filtering it out -- an `if m` filter silently shortened a
        # three-dispatch chain to two tokens.
        full_chain = [binfo["dispatched_model"]] + escalations
        dispatch_chain = [m if m else "agent-default" for m in full_chain]
        chain_token = "+".join(dispatch_chain)
        profile = report["profile"]
        # A4 fix: a blocked run must never be credited with a saving in the kit ledger, so
        # every budget line carries the task's own status as a seventh token.
        status_token = result.get("status", "unknown")
        if report.get("not_counted"):
            # T8 item 2: no demotion happened -- the literal `not-counted` delta_usd token
            # tells `cmd_budget` to skip this row from every total (priced or unpriced).
            block_lines.append(
                f"- budget: standard={standard_token} actual={chain_token} "
                f"profile={profile} est_standard_usd=not-counted "
                f"est_actual_usd=not-counted delta_usd=not-counted status={status_token}"
            )
        elif report["priced"]:
            block_lines.append(
                f"- budget: standard={standard_token} actual={chain_token} "
                f"profile={profile} est_standard_usd={report['standard_usd']:.4f} "
                f"est_actual_usd={report['actual_usd']:.4f} "
                f"delta_usd={report['delta_usd']:+.4f} status={status_token}"
            )
        else:
            block_lines.append(
                f"- budget: standard={standard_token} actual={chain_token} "
                f"profile={profile} est_standard_usd=unpriced est_actual_usd=unpriced "
                f"delta_usd=unpriced status={status_token}"
            )
    if escalations:
        pinned = task.get("model") or "agent default"
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

    !!! Invoking this with a real `copilot` argv spends AI Credits and hits the network. !!!
    """
    proc = subprocess.run(argv, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def default_verify_runner(cmd):
    """Verify runner for real runs: shell out (verify commands are repo-authored shell lines).

    Same trust model as the kit contract: `subprocess.run(cmd, shell=True, ...)`.
    """
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


# ---- CLI ------------------------------------------------------------------------------------

def _format_prefs_line(prefs):
    """Render `prefs`'s pins/excludes as the `prefs:` dry-run line body (`(none)` per side)."""
    pins = prefs.get("pins") or {}
    excludes = prefs.get("excludes") or []
    pins_str = ",".join(f"{tier}={model_id}" for tier, model_id in pins.items()) or "(none)"
    excludes_str = ",".join(excludes) or "(none)"
    return f"pins={pins_str} excludes={excludes_str}"


def _format_budget_line(binfo):
    """Render a `budget_demote` result dict as the `budget:` dry-run/run summary line."""
    if binfo["demoted"]:
        standard_label = (
            binfo["standard_model"] or f"agent default (assumed {DEFAULT_ESCALATION_START})"
        )
        return (
            f"budget: demoted {binfo['standard_tier']} -> {binfo['target_tier']} — "
            f"dispatching {binfo['dispatched_model']} (standard: {standard_label})"
        )
    return f"budget: no demotion — {'; '.join(binfo['notes'])}"


def _format_budget_report_line(report):
    """Render a `budget_report` result dict as the `budget est.:` verdict line (PLAN D5)."""
    if report.get("not_counted"):
        # T8 item 2: no demotion happened, so nothing was priced -- never say BACKFIRED.
        return "budget est.: no demotion this run — budget mode changed nothing; not counted"
    if not report["priced"]:
        return f"budget est.: unpriced — {report['reason']} (no dollars fabricated)"

    delta_usd = report["delta_usd"]
    actual_usd = report["actual_usd"]
    actual_aic = report["actual_aic"]
    standard_usd = report["standard_usd"]
    standard_aic = report["standard_aic"]
    dispatches = report["dispatches"]
    profile = report["profile"]

    if delta_usd >= 0:
        return (
            f"budget est.: saved ${delta_usd:.4f} — actual ${actual_usd:.4f} "
            f"({actual_aic:.1f} AIC) across {dispatches} dispatch(es) vs standard "
            f"${standard_usd:.4f} ({standard_aic:.1f} AIC, single dispatch, assumes "
            f"first-try) [profile {profile} estimate — not a bill]"
        )
    return (
        f"budget est.: BACKFIRED — overspent ${-delta_usd:.4f} — actual ${actual_usd:.4f} "
        f"({actual_aic:.1f} AIC) across {dispatches} dispatch(es) vs standard "
        f"${standard_usd:.4f} ({standard_aic:.1f} AIC, single dispatch, assumes "
        f"first-try) [profile {profile} estimate — not a bill]"
    )


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


def cmd_run(args):
    kit = Path(args.kit)
    slug = kit.name
    tasks_path = kit / "TASKS.md"
    text = _read_tasks_text(kit)
    tasks = parse_tasks(text)
    task = _select_task(tasks, args.task)
    if task is None:
        if args.task:
            print(f"no task with id {args.task!r} in {tasks_path}", file=sys.stderr)
        else:
            print(
                f"no eligible pending task (all deps done) in {tasks_path}", file=sys.stderr
            )
        sys.exit(2)

    # One content-free `run=` id per invocation (T7, PLAN D8) -- generated unconditionally
    # (including under --dry-run, so the preview shows the same id preamble a real run would
    # dispatch with) since generating a random hex string spawns nothing and costs nothing.
    run_id = generate_run_id()

    extra_args = tuple(args.extra_arg or ())

    pin_flags = tuple(args.pin or ())
    exclude_flags = tuple(args.exclude or ())
    prefs_flags_given = bool(pin_flags or exclude_flags or args.prefs or args.no_prefs)

    pricing = None
    prefs = None
    if prefs_flags_given or (
        not args.no_prefs and _load_prefs_module().DEFAULT_PREFS_PATH.exists()
    ):
        pricing = load_pricing()
        prefs_mod = _load_prefs_module()
        prefs = prefs_mod.effective_prefs(
            pricing, prefs_path=args.prefs, no_prefs=args.no_prefs,
            pin_flags=pin_flags, exclude_flags=exclude_flags,
        )
        if prefs_mod.is_empty(prefs) and not prefs["notes"]:
            prefs = None

    if args.budget:
        if pricing is None:
            pricing = load_pricing()
        if args.budget_profile not in pricing.get("task_profiles", {}):
            raise ValueError(
                f"unknown task profile {args.budget_profile!r}; valid choices: "
                f"{sorted(pricing.get('task_profiles', {}))}"
            )

    if args.dry_run:
        effective_model, _dispatch_notes = _effective_task_model(task, pricing, prefs)
        dispatch_model = effective_model
        binfo = None
        if args.budget:
            binfo = budget_demote(pricing, effective_model, prefs)
            dispatch_model = binfo["dispatched_model"]
        argv = build_dispatch(
            args.agent, task["brief"], dispatch_model,
            copilot_bin=args.copilot_bin, extra_args=extra_args,
            kit=slug, run_id=run_id, task_id=task["id"],
        )
        if prefs is not None:
            print(f"prefs: {_format_prefs_line(prefs)}")
            for note in prefs.get("notes") or []:
                print(f"note: {note}")
        if args.budget:
            print(_format_budget_line(binfo))
        print(f"task: {task['id']}")
        print(f"dispatch: {shlex.join(argv)}")
        print(f"verify: {task['verify']}")
        return

    # A task is never its own parent. `bin/routing_scorecard.py` DROPS a self-referencing
    # `parent=` with a note ("parent cannot be its own task id -- ignored") while still counting
    # the `escalated-pass` that `parent=` caused (see `outcome_result`) -- so writing one would
    # put a line into a headline figure and into the ignored list at once, the exact invariant
    # the Phase 1 review adopted (NOTES.md F2) and the Phase 2 review flagged as missing on an
    # earlier driver (F-E). Rejected here at the WRITER, before anything is written or
    # dispatched, rather than left for the reader to drop.
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
    # this gate only ever stops a REAL run. See the module's "PLAN.md budget dial" section
    # (NOT the same as this driver's own `--budget` dollar-savings mode).
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
                    remaining, agent=args.agent,
                )
            sys.exit(1)

    text = set_status(text, task["id"], "in-progress")
    tasks_path.write_text(text)

    if pricing is None:
        pricing = load_pricing()

    result = run_task(
        task, pricing, default_runner, default_verify_runner,
        agent=args.agent, max_escalations=args.max_escalations,
        copilot_bin=args.copilot_bin, extra_args=extra_args, prefs=prefs,
        budget=args.budget, kit=slug, run_id=run_id,
    )

    text = set_status(text, task["id"], result["status"])
    tasks_path.write_text(text)

    result["agent"] = args.agent

    if args.budget:
        try:
            report = budget_report(
                pricing, result["budget"], result["escalations"], args.budget_profile, prefs
            )
        except Exception as e:  # a cost-report failure never changes status/exit code (D5)
            report = {"priced": False, "reason": str(e), "profile": args.budget_profile}
        result["budget_report"] = report

    append_note(kit / "NOTES.md", result, task, run_id=run_id, parent=args.parent)

    escalations = result["escalations"] or "(none)"
    print(
        f"task {result['id']}: {result['status']} "
        f"(model_used={result['model_used'] or 'agent default'}, "
        f"escalations={escalations}, verify_rc={result['verify_rc']}, run={run_id})"
    )
    if args.budget:
        print(_format_budget_line(result["budget"]))
        print(_format_budget_report_line(result["budget_report"]))
    for note in result.get("prefs_notes") or []:
        print(f"note: {note}")
    if result["status"] == "blocked":
        sys.exit(1)


_BUDGET_LINE_PREFIX = "- budget: "
_REQUIRED_BUDGET_KEYS = {
    "standard", "actual", "profile", "est_standard_usd", "est_actual_usd", "delta_usd",
}


def _render_money(total, n_priced, n_total):
    """Render an estimates figure, or say plainly that there is nothing to total.

    T9 root-cause fix: every dollar line in `cmd_budget` renders through this ONE helper, so
    "no data" and "data that sums to zero" can never print the same figure again. Returns a
    string that NEVER contains a currency figure when `n_priced == 0`, and that discloses
    partial coverage when `0 < n_priced < n_total`. The label is unconditional.
    """
    if n_priced == 0:
        return "no priced runs to total"
    if n_priced == n_total:
        return f"est. net ${total:+.4f} [estimates — not a bill]"
    return f"est. net ${total:+.4f} over {n_priced} of {n_total} priced [estimates — not a bill]"


def cmd_budget(args):
    """Total a kit's recorded `- budget:` NOTES.md lines into a ledger + verdict (PLAN D5).

    Read-only over `<kit>/NOTES.md` -- no dispatch, no writes, no pricing math, no prefs
    loaded (the dollars were already recorded by earlier `run --budget` calls). Every
    degradation path (no NOTES.md, no budget lines, a malformed line) prints an honest line
    and exits 0; only PRICED `done` rows enter the headline net total.

    T8 item 1 (BLOCKING): rows whose `status` token is not `done` are excluded from the
    headline net (a run that never landed should not be credited or debited against budget
    mode's effectiveness), but their OWN net is computed and printed on a mandatory labeled
    line whenever any row is excluded -- never silently dropped, because a blocked run is the
    maximum-cost case and hiding its overspend would bias the ledger toward optimism. When the
    completed-work net is positive but the combined (completed + excluded) net is negative,
    the optimistic SAVING verdict is suppressed in favor of a line that states both halves.

    T8 item 2: a row whose `delta_usd` is the literal `not-counted` token (the run made no
    demotion, so budget mode changed nothing about it) is skipped from every total -- priced,
    unpriced, and excluded alike -- and counted separately.

    T9 (root-cause fix): every dollar-bearing line -- the headline totals line AND the
    `excluded runs:` line -- is produced by the single `_render_money` helper, which cannot
    print a currency figure when nothing was priced, so "no data" and "data summing to zero"
    can never render identically again. Unpriced rows are counted across EVERY status, not
    only `done` (T9 item 2). The suppression guard above is `>= 0`, not `> 0` (T9 item 3), so
    an exactly-zero `done` net beside a large excluded overspend still gets the two-halves
    treatment instead of a bare "break-even". Any verdict is qualified with a trailing
    " (some blocked runs are unpriced — the overall figure is incomplete)" whenever an
    excluded row could not be priced, since an unpriceable excluded overspend can never trip
    the suppression guard on its own (T9 item 4).
    """
    notes_path = Path(args.kit) / "NOTES.md"
    if not notes_path.exists():
        print(f"no NOTES.md under kit dir {args.kit} — no budget runs recorded.")
        return

    lines = notes_path.read_text().splitlines()
    heading_idxs = [i for i, ln in enumerate(lines) if ln.startswith("## ")]

    rows = []  # list of (task_id, tokens dict)
    for pos, start in enumerate(heading_idxs):
        heading = lines[start][len("## "):].strip()
        if EM_DASH not in heading:
            continue
        task_id = heading.split(EM_DASH)[-1].strip()
        end = heading_idxs[pos + 1] if pos + 1 < len(heading_idxs) else len(lines)
        for ln in lines[start:end]:
            if not ln.startswith(_BUDGET_LINE_PREFIX):
                continue
            tokens = {}
            for tok in ln[len(_BUDGET_LINE_PREFIX):].split():
                key, sep, value = tok.partition("=")
                if sep:
                    tokens[key] = value
            if not _REQUIRED_BUDGET_KEYS.issubset(tokens.keys()):
                print(f"note: skipped malformed budget line: {ln}")
                continue
            rows.append((task_id, tokens))

    if not rows:
        print(f"no budget runs recorded in {notes_path} — nothing to report.")
        return

    print(f"# Budget ledger — {args.kit}")
    # B2 fix: every dollar figure this command prints must carry the honesty label.
    print("All figures are labeled estimates recorded at run time — not a bill.")
    print()
    for task_id, tokens in rows:
        print(
            f"{task_id}  delta_usd={tokens['delta_usd']}  standard={tokens['standard']}  "
            f"actual={tokens['actual']}  status={tokens.get('status', 'unknown')}"
        )

    # A4 fix: a blocked (non-`done`) run must never be credited with a saving -- exclude it
    # from the net entirely rather than folding its delta_usd into the total. T8 item 2: a row
    # whose delta_usd is the literal `not-counted` token (no demotion happened) is skipped from
    # EVERY total -- not priced, not unpriced, not excluded -- and gets its own count.
    #
    # T9 root-cause fix: this loop tracks priced/unpriced COUNTS as well as sums, for both the
    # `done` bucket and the excluded bucket, so every dollar line below can be produced by
    # `_render_money` -- the single renderer that cannot print a currency figure when nothing
    # was priced, and that discloses partial coverage rather than pretending completeness.
    done_total = 0.0
    done_n_priced = 0
    done_n_unpriced = 0
    excluded_ids = []
    excluded_total = 0.0
    excluded_n_priced = 0
    excluded_n_unpriced = 0
    n_not_counted = 0
    for task_id, tokens in rows:
        if tokens.get("delta_usd") == "not-counted":
            n_not_counted += 1
            continue
        try:
            delta = float(tokens["delta_usd"])
            priced = True
        except ValueError:
            delta = 0.0
            priced = False
        if tokens.get("status") != "done":
            excluded_ids.append(task_id)
            if priced:
                excluded_total += delta
                excluded_n_priced += 1
            else:
                excluded_n_unpriced += 1
            continue
        if priced:
            done_total += delta
            done_n_priced += 1
        else:
            done_n_unpriced += 1

    # T9 item 2: unpriced rows are counted across EVERY status, not only `done` -- an unpriced
    # BLOCKED row was previously reported nowhere at all, making this count simply false.
    total_unpriced = done_n_unpriced + excluded_n_unpriced
    done_n_total = done_n_priced + done_n_unpriced

    print()
    print(f"priced runs: {done_n_priced} — {_render_money(done_total, done_n_priced, done_n_total)}")
    print(f"unpriced runs: {total_unpriced} (excluded from the total)")
    print(f"not-counted runs: {n_not_counted}")
    if excluded_ids:
        # T8 item 1 (BLOCKING): excluding non-`done` rows from the headline net must not also
        # erase THEIR net -- a blocked run is the maximum-cost case, so hiding its overspend
        # biases the ledger toward optimism. This line is mandatory whenever any row is
        # excluded, and (T9) always renders through `_render_money` so an all-unpriced excluded
        # bucket prints no currency figure at all rather than a fabricated zero total.
        excluded_n_total = excluded_n_priced + excluded_n_unpriced
        print(
            f"excluded runs: {len(excluded_ids)} (not done — {', '.join(excluded_ids)}); "
            f"their recorded net: {_render_money(excluded_total, excluded_n_priced, excluded_n_total)}"
        )

    if done_n_priced == 0:
        verdict = (
            f"verdict: no priced budget runs — nothing to total (unpriced runs: {total_unpriced})"
        )
    elif done_total >= 0 and (done_total + excluded_total) < 0:
        # T8 item 1 (BLOCKING) / T9 item 3: the completed-work net is non-negative, but folding
        # in what the excluded (non-`done`) rows actually cost flips the combined figure
        # negative -- an unqualified SAVING (or bare break-even) verdict here would be exactly
        # the bias A4 was written to remove, reintroduced from the other side. The guard is
        # `>= 0`, not `> 0`: a `done` net of exactly 0.0 beside a large excluded overspend must
        # not read as a bare "break-even" either. Say both halves plainly instead.
        if done_total > 0:
            verdict = (
                "verdict: budget mode is SAVING on completed work but LOSING overall once "
                "blocked runs are counted — consider dropping --budget"
            )
        else:
            verdict = (
                "verdict: budget mode is break-even on completed work but LOSING overall once "
                "blocked runs are counted — consider dropping --budget"
            )
    elif done_total > 0:
        verdict = "verdict: budget mode is SAVING money on this kit"
    elif done_total < 0:
        verdict = "verdict: budget mode is LOSING money on this kit — consider dropping --budget"
    else:
        verdict = "verdict: break-even"

    if excluded_n_unpriced > 0:
        # T9 item 4: an unpriceable excluded overspend contributes nothing to `excluded_total`,
        # so it can never trip the suppression guard above -- whichever verdict was chosen must
        # say the figure is incomplete rather than imply a completeness it does not have.
        verdict += " (some blocked runs are unpriced — the overall figure is incomplete)"
    print(verdict)


def cmd_review(args):
    extra_args = tuple(args.extra_arg or ())
    prompt = (
        f"Review phase {args.phase} of the execution kit at {args.kit}. Read "
        f"{args.kit}/PLAN.md (goal, decisions, out-of-scope fence, tripwires) and the tasks "
        f"under '## Phase {args.phase}' in {args.kit}/TASKS.md, then review the actual changes "
        f"for drift, scope creep, and contract breakage. Report findings; change nothing."
    )
    argv = build_dispatch(
        "reviewer", prompt, None, copilot_bin=args.copilot_bin, extra_args=extra_args
    )
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
        prog="copilot_execute.py",
        description=(
            "Run an execution kit against Copilot CLI's custom agents: parse TASKS.md, "
            "dispatch each task, verify, escalate up the pricing tiers, write state back. "
            "Real runs spend AI Credits; --dry-run spawns nothing."
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
    p_run.add_argument("--agent", default="implementer", help="Copilot agent to dispatch to")
    p_run.add_argument("--copilot-bin", default="copilot", help="Copilot CLI binary to invoke")
    p_run.add_argument("--max-escalations", type=int, default=None,
                       help="cap the number of escalation rungs")
    p_run.add_argument("--extra-arg", action="append",
                       help="extra dispatch flag (repeatable), e.g. --extra-arg=--deny-tool=...")
    p_run.add_argument("--pin", action="append", metavar="TIER=MODEL_ID",
                       help="resolve TIER to MODEL_ID (repeatable; overrides the prefs file's pin for that tier)")
    p_run.add_argument("--exclude", action="append", metavar="MODEL_ID",
                       help="never dispatch this model (repeatable; unions with the prefs file's excludes)")
    p_run.add_argument("--prefs", default=None, metavar="FILE",
                       help="prefs file to read (default: <repo>/prefs/copilot.json)")
    p_run.add_argument("--no-prefs", action="store_true",
                       help="ignore the prefs file entirely (--pin/--exclude flags still apply)")
    p_run.add_argument(
        "--parent", default=None,
        help="mark this run as a consult spawned to rescue TASK_ID (adds parent= to the "
             "outcome line on success; TASK_ID must differ from the task being run -- a value "
             "equal to the task's own id is REJECTED with exit 2, nothing written)",
    )
    p_run.add_argument("--dry-run", action="store_true",
                       help="print the dispatch argv and verify command; spawn/write nothing")
    p_run.add_argument("--budget", action="store_true",
                       help="dispatch one tier lower than the task's pin (floor: cheapest "
                            "tier) and report est. actual-vs-standard cost")
    p_run.add_argument("--budget-profile", default="M", metavar="PROFILE",
                       help="task profile for the budget cost estimate (a task_profiles key "
                            "in data/pricing.copilot.json)")
    p_run.set_defaults(func=cmd_run)

    p_review = sub.add_parser("review", help="dispatch the reviewer agent for a phase")
    p_review.add_argument("--kit", required=True, help="kit directory (contains PLAN.md)")
    p_review.add_argument("--phase", required=True, help="phase number to review")
    p_review.add_argument("--copilot-bin", default="copilot", help="Copilot CLI binary")
    p_review.add_argument("--extra-arg", action="append",
                          help="extra dispatch flag (repeatable)")
    p_review.add_argument("--dry-run", action="store_true",
                          help="print the dispatch argv; spawn nothing")
    p_review.set_defaults(func=cmd_review)

    p_budget = sub.add_parser(
        "budget", help="total a kit's recorded --budget runs into a ledger + verdict"
    )
    p_budget.add_argument("--kit", required=True,
                          help="kit directory (reads NOTES.md; no dispatch, no spend)")
    p_budget.set_defaults(func=cmd_budget)

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
