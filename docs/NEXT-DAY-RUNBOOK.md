# Next-day runbook

A dated, checkable plan for tomorrow, layered on the daily journal.

---

## What this is

The daily journal already collects a digest of open kit tasks, uncommitted work (WIP), and
your inbox, and turns them into prose in `next-day.md`. The runbook (`bin/journal_plan.py`)
turns the same signals into a **dated, checkable file** instead: one card per planned task,
each with a concrete What/How, a recommended harness, and ready-to-paste commands for all
three harnesses.

There is **no scheduler and no auto-execution, by design** — the user explicitly tabled
scheduling this work. Everything here is user-invoked: you run `build` when you want a plan,
you run `check` when you want to see what's due, and you run `done`/`defer` (or just hand-edit
the checkboxes) to track it. `journal_plan.py` never spawns a process, never opens a network
connection, and never reads a home directory — it only ever writes under
`<journal-dir>/plan/`. The commands it prints are text for a human to copy and run; the tool
itself never runs them.

## The flow

1. **Collect** the day's digest as usual: `python3 bin/journal_collect.py`.
2. **Build** tomorrow's runbook from it: `python3 bin/journal_plan.py build`. The default
   target date is the day after `--date` (today, unless overridden), so a plain `build` right
   after collecting today's digest writes tomorrow's plan. Pass `--for YYYY-MM-DD` to target a
   specific date instead.
3. **Enrich** the What/How steps in-session: `python3 bin/journal_plan.py prompt` prints a
   pinned prompt asking a model to rewrite each open card's What/How into 2-6 concrete,
   numbered steps, using only facts already present in the runbook and digest — never invented
   files, flags, model ids, or costs. Run that prompt in your current (already-paid-for)
   session, then save the model's revised markdown back over the same `journal/plan/<date>.md`
   path by hand. `prompt` itself writes nothing and spawns nothing.
4. **On the day tasks are due**, run `python3 bin/journal_plan.py check` to see what's due or
   overdue, then `python3 bin/journal_plan.py done <id> --date <file-date>` to check a card off
   or `python3 bin/journal_plan.py defer <id> --to <date> --date <file-date>` to push it out —
   or just edit the checkbox in the markdown yourself; the file is yours.
5. **Unchecked, undeferred cards carry forward** into later builds automatically, so nothing
   quietly falls off a stale dated file.

## The store

Each due date gets one flat markdown file: `journal/plan/<YYYY-MM-DD>.md`, under the same
gitignored `journal/` tree as the rest of the journal, human-editable (check a box by hand) and
machine-parseable (a pinned card grammar with a parse/render round-trip). A file opens with a
schema line, a `built-from:` line naming the digest date it drew signals from (or `no digest`
when none was available), and the advisory line, before the `## Tasks` section:

```
# Runbook — 2026-07-11

- schema: 1
- built-from: digest 2026-07-10

Advisory only — nothing here auto-executes; every command below is ready-to-paste for a human to run.

## Tasks

### [ ] R1 — Wire the widget

- source: kit:demo-kit/T9
- due: 2026-07-11
- first-planned: 2026-07-11
- model-hint: sonnet

**What/How:**
1. Open `.claude/kits/demo-kit/TASKS.md` and read the T9 brief — it is authoritative.
2. Resume the kit: `/polytropos:execute demo-kit` (Claude Code), or paste a harness command from below.
3. Run the task's verify command from the repo root before calling it done.

**Harness:**
- ideal: claude_code — kit tasks run via /polytropos:execute in Claude Code
- claude_code (<model-id>, est M ~$<x>): `claude -p --model <model-id> "Wire the widget"`
- copilot_cli (<model-id>, est M ~$<x> / ~<y> AIC): `copilot --model <model-id> -p "Wire the widget"`
- codex_cli (<model-id>, est M ~$<x> API-equivalent — not a bill): `codex exec --model <model-id> --full-auto "Wire the widget"`
```

(Real files carry actual pricing-file model ids and run-time cost estimates in place of the
`<model-id>` and `~$<x>` placeholders — the placeholders here are deliberate; the tool
never guesses or hardcodes one.) A card's checkbox (`[ ]`/`[x]`) is the
authoritative done/not-done marker; a `- deferred-to:` field line marks a deferral. Card ids
(`R1`, `R2`, ...) are scoped to their file and stable — a rebuild never renumbers them.

`journal/plan/seed.md` is the hand-seeding path for quiet days when the digest's kit/WIP/inbox
signals are thin: add plain lines in the same format as `journal/inbox.md` (blank lines and
`#` comments skipped, one leading list marker stripped), and each becomes a `seed`-source card
at the next build. `seed.md` is read-only input to the tool — it is never truncated, rewritten,
or deleted; you own it exactly like the inbox file.

Rebuilding an existing date is a merge, not an overwrite: an existing card keeps its id,
position, checkbox, `deferred-to:`, `first-planned:`, and its entire What/How body
byte-for-byte (even after you've had it model-enriched — that's paid work, and a rebuild never
clobbers it). Only the `**Harness:**` block is refreshed, so cost estimates and commands stay
current. A card with no match in the new computation is preserved verbatim rather than
silently dropped, and new cards append with the next free id.

## Harness recommendations

Every card carries a ready-to-paste command for all three harnesses — Claude Code, Copilot
CLI, and Codex CLI — composed only from the journal advisor's (`bin/journal_advisor.py`)
pinned command templates, with the recommended model id substituted and profile-M cost
estimates attached. The three pricing files (`data/pricing.json`, `data/pricing.copilot.json`,
`data/pricing.codex.json`) never merge, and no rate is ever borrowed from one harness's file
for another.

Every card also names one deterministic **ideal** pick with a one-line reason: a card sourced
from a kit task always picks Claude Code (kit tasks run via `/polytropos:execute`, a
structural fact, not a cost comparison); otherwise the cheaper of Claude Code's and Copilot
CLI's real-dollar estimate wins, naming both figures. Codex CLI is **never** the deterministic
ideal pick and is excluded from the cost ranking entirely, because its figure is an
API-equivalent relative-burn proxy, never a bill — it cannot be ranked against real dollars.
Its command is still on every card; you (or the in-session enrichment) may still choose it.

When a real-dollar estimate or model id isn't available for a harness, the line reads
`est n/a — pricing or tier unavailable` with no command and no model id — never a fabricated
or zeroed figure, and never a guessed model id. If the advisor signal itself is unavailable
(no digest yet, or the advisor call failed), the whole Harness block degrades to one honest
line telling you to run the collector and rebuild, instead of showing stale or invented
numbers.

## Check & carry-forward

`python3 bin/journal_plan.py check` scans every dated file under `journal/plan/`, dedupes
cards by their latest occurrence (so a card that was carried into a later file is never
counted twice), and reports each unchecked card whose effective due date (its `deferred-to:`
date, or its file's date) is today or earlier — tagged `DUE <date>` or
`OVERDUE since <date>`, each with a `[<file-date>/<id>]` handle you pass to `done`/`defer`.
An empty store prints an honest "no runbook cards due" line and still exits 0.

Any unchecked, undeferred card from an older dated file carries forward into the next `build`
for a later date: it keeps its original `first-planned:` date and What/How body, and takes on
the new due date. A `deferred-to:` date keeps a card out of carry-forward (and out of `check`)
until that date arrives. Historical dated files are never rewritten by `build` or `check` —
the latest-occurrence dedup rule is what prevents double-reporting a carried card.

## What it never does

- No scheduler, no automation: no launchd/`StartCalendarInterval`, no `pmset`, no cron, no
  daemon, no `launchctl` work anywhere. `bin/journal_schedule.py` is untouched by this feature
  and the runbook is never wired into the scheduled nightly run.
- No unattended dispatch: `bin/journal_plan.py` never spawns a harness, a model, or any
  subprocess — generating ready-to-paste command text is the whole feature.
- No network, OAuth, MCP, tokens, or secrets in any form.
- No SQLite — flat markdown and the existing JSON pricing/digest files only.
- No home-directory reads: the script takes no home-dir flag at all; its only inputs are
  `--journal-dir` and the committed `data/` pricing files, and its only writes are under
  `<journal-dir>/plan/`.
