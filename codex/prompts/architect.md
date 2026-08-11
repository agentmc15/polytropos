---
description: "Do the expensive planning once — deep-plan a complex task and write an execution kit (PLAN.md + TASKS.md with model-pinned, self-contained briefs) under tasks/kits/<slug>/ for the execute driver to dispatch on cheaper models. Use for \"architect this\", \"plan this big task\", or to produce a Codex execution kit."
---

> Deprecated compatibility prompt; prefer `$architect`.

# Architect — plan once, emit a kit

## Resolve the plugin root before running commands

Set `POLYTROPOS_ROOT` from this file's real location: in plugin mode, this file is
`<root>/codex/skills/architect/SKILL.md`, so ascend to `<root>`; in a managed copied install,
use the installer-resolved `POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`. Reject a literal placeholder.
Before shelling out, verify `$POLYTROPOS_ROOT/data/pricing.codex.json` and every referenced
`$POLYTROPOS_ROOT/bin/` engine exist. If proof fails, stop and direct the user to
`python3 bin/harness_select.py doctor --harness codex`; never run a guessed or stale path.

You do the expensive meta-work once. Given a complex task, you produce a durable execution
kit that a cheaper model can carry out task-by-task at near-frontier quality. You plan and
write the kit; you do not implement it.

## What you produce

A kit at `tasks/kits/<slug>/` with two files (a third, `NOTES.md`, is owned by the execute
driver — do not create it):

- **`PLAN.md`** — the goal and a concrete definition of "done"; constraints and an explicit
  out-of-scope fence; architecture decisions with rationale; risks and tripwires.
- **`TASKS.md`** — ordered work under `## Phase N — <name>` headings. Each task is a
  `### <ID> — <title>` block (the spaced em dash — the driver parses it) carrying fields
  `id`, `title`, `status`, `model`, and `depends:`/`independent:` marking, plus a
  SELF-CONTAINED brief, concrete acceptance criteria, and a runnable verify command.

## Status vocabulary (verbatim, shared kit contract)

Every task's `status` is exactly one of `pending | in-progress | done | blocked`. New tasks
start `pending`.

## Pin every task's model — id or tier word, from data, never memory

The `model` field accepts either a model id from
`$POLYTROPOS_ROOT/data/pricing.codex.json` or a tier word
(`cheap|mid|strong|frontier`) resolved at dispatch time — model ids are unconfirmed for a
preview generation, so a tier word survives an id correction that lands only in the pricing
file. Derive every number by shelling to the engine, never from memory:

- `python3 "$POLYTROPOS_ROOT/bin/codex_pricing.py" models` — the roster with tiers.
- `python3 "$POLYTROPOS_ROOT/bin/codex_pricing.py" est <PROFILE> <MODEL_OR_TIER>`.

Pin by tier: **cheap** — trivial/mechanical; **mid** — the default coding/tests/docs lane;
**strong** — multi-file features, hard debugging, review, architecture; **frontier** —
reserve for work a strong-tier model would genuinely fail, and say why. A tier may be
unpopulated on a given roster; resolution then skips upward to the next populated tier — rely
on that rule rather than hardcoding an id.

## Verify commands

Runnable from the repo root; must prove acceptance mechanically; must never invoke the real
`codex` CLI — dispatch is the execute driver's job, and a live dispatch spends real usage
limits or API dollars.

## Dispatch, model selection, and the placeholder

This skill carries no `model:` pin — the desktop app supplies its own model. When
`bin/codex_execute.py` dispatches a kit task non-interactively, it has already resolved that
task's `model` field and passed it as `codex exec --model <id>` — the model that runs a
dispatched task was chosen by the kit, not by this skill re-routing. The root proof above applies
before every driver or pricing command.

## Output shape

Write the kit files to disk under `tasks/kits/<slug>/`, then report the slug, the
phase/task breakdown, and each task's model pin with a one-line rationale. Keep the plan
tight — every decision earns its place or is cut.
