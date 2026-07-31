# Daily work journal

A nightly, scheduled record of the day's AI-assisted work: a deterministic collector reads
local, read-only usage sources and writes a structured digest; a routed model then turns that
digest into three short documents you can actually read over coffee.

---

## What this is

Two stages, three outputs, one gitignored home:

- **A deterministic collector** (`bin/journal_collect.py`) — no model, no network, always runs.
  It reads the day's activity from every configured source and writes `digest.json`.
- **A scheduled model summarizer** (`bin/journal_summarize.py`) — reads that digest and writes
  `narrative.md` (the story of the day), `technical.md` (sessions, costs, models, repos), and
  `next-day.md` (what to start, what to run, to-dos), via a cheap/mid model routed from
  `data/pricing.json` with one possible escalation step.

Every output — the digest, the three documents, the inbox, and the scheduler logs — lives
under a single gitignored `journal/` tree, so personal data never lands in git.

## The pipeline

`journal_collect.py` → `journal_summarize.py` → `journal_schedule.py`, with the digest file as
the seam between the first two:

1. **Collect.** `journal_collect.py` ingests every source for a given day, pre-structures
   next-day signals, and writes `journal/<date>/digest.json`. Always runs; no model involved.
2. **Summarize.** `journal_summarize.py` reads that digest, builds three prompts from it, and
   dispatches them to a model to produce the three markdown documents plus a small
   `summary-meta.json` recording what ran.
3. **Schedule.** `journal_schedule.py` installs a macOS launchd job that runs both stages once
   a night (default ~22:00 local, configurable), and also supports a manual one-shot run.

Because the digest is a plain file, either stage is independently rerunnable per day — you can
regenerate `digest.json` for a past date, or re-summarize an existing digest against a
different model, without touching the other stage.

## Sources & the adapter contract

v1 ships six registered sources: **Claude Code**, **Copilot CLI**, and **Codex CLI** (counted,
plus a clearly-labeled API-equivalent relative-burn proxy priced from
`data/pricing.codex.json` — never a bill), **git activity** across configured repos, and
**Cursor**/**VS Code**, which are registered but deferred (see Deferred, below).

Every source is a `collect_<name>(ctx) -> report` function registered in an ordered adapter
table in `bin/journal_sources.py`. Ingestion is strictly read-only and JSONL/flat-text only —
never a SQLite file, never a shelled-out `claude`/`copilot`/`codex` CLI call. Claude Code and
Copilot CLI reuse this repo's existing, proven parsers rather than re-implementing them; the
Codex adapter is new and tolerant of an unpinned JSONL shape, skipping malformed lines instead
of guessing.

Adding a new source later is one function plus one registry row: implement `collect_<name>`
against the pinned context/report shapes, add it to the registry, and it flows through
collection, the digest, and the summarizer prompts with no other engine changes. That is
exactly the slot-in path already reserved for Cursor and VS Code.

## The digest

`digest.json` is `schema_version: 1` — a top-level date, generation timestamp, the day window,
totals, a `sources` map keyed by source name (each holding token/session counts, a priced USD
figure or `None` when the source is unpriced, project/repo names, errors, and notes), and a
`signals` block for next-day planning.

Day scoping: `--date` selects the day (default: today); the window is `[local midnight, next
local midnight)` unless `--utc` is passed, which computes the same window in UTC instead — every
test and verify run in this kit uses `--utc` so results never depend on the machine's timezone.
Each source honors this window against its own honest notion of "when did this happen" (message
timestamp, last-seen session timestamp, or commit time); records with no parseable timestamp are
excluded from the day but still counted separately, rather than silently attributed to today.

Content hygiene is part of the schema, not an afterthought: the digest carries **metadata
only** — never transcript or message text. The only free-text fields anywhere in it are commit
subjects, kit task titles, inbox lines you wrote yourself, project/repo names, and error
strings.

## Codex: deeper logs, labeled proxy

Beyond the shallow `session_index.jsonl`/`history.jsonl` read, the Codex adapter also reads the
digest day's rollout files — `~/.codex/sessions/YYYY/MM/DD/*.jsonl` — by reusing
`bin/codex_usage.py` read-only. The date-partitioned directory name is the day-membership
rule: only the one directory matching the digest's day is ever opened, never a neighboring
date or an mtime-based guess.

When those rollouts carry token usage and `data/pricing.codex.json` is loaded, the digest
carries `sources.codex_cli.extra.codex_proxy` — `billed_usd: null`, an
`api_equivalent_usd_total`, per-model figures, and the verbatim disclaimer from
`bin/codex_usage.py`'s `PROXY_DISCLAIMER` constant. The Codex report itself always stays
`priced: false` / `usd: null`, and the proxy is **never** added to `totals.usd_priced` or any
other billed figure: a relative-burn proxy is not a bill, and subscription Codex usage is
usage-limited, not token-billed. When no tokens are found, or pricing wasn't supplied to the
run, the report says so honestly instead of guessing a number.

## Next-day planning & the inbox

The digest's `signals` block pre-structures three families of forward-looking signal so the
next-day document is built from facts, not guesswork:

- **Kit tasks** — pending and in-progress tasks pulled from every execution kit's task list.
- **Inbox** — plain lines from `journal/inbox.md`, your own scratch file for anything that
  isn't captured by a tool: meeting notes, email to-dos, reminders. Blank lines and comment
  lines are skipped, and leading list markers are stripped, so you can write however you like.
- **WIP** — repos with uncommitted or untracked changes, and their current branch.

`next-day.md` turns exactly these signals into prose: what to start tomorrow, what to run and
how (concrete commands, not vague pointers), and an explicit to-do list.

The same signals also feed the **next-day runbook** — a dated, checkable plan under
`journal/plan/` with per-task harness commands, carry-forward, and a check-off surface,
built on demand by `bin/journal_plan.py` (no scheduler, no auto-execution — see
[NEXT-DAY-RUNBOOK.md](NEXT-DAY-RUNBOOK.md)).

## External tools: the ask-the-tools pack

The journal has no view into Microsoft Teams, Outlook, or Copilot Studio — there is no local
data surface to read. `bin/journal_askpack.py` closes that gap with a fully offline, two-pass
flow instead of adding any network call, OAuth flow, Graph API, or MCP connector:

1. `journal_collect.py` collects the day's AI-assisted work into `digest.json` as usual.
2. `journal_askpack.py --date <date>` renders `journal/<date>/ask-the-tools.md` — one
   ready-to-paste prompt per tool (Copilot Studio, Microsoft Teams, Outlook) asking that
   tool's own AI to summarize the date's activity.
3. You paste each prompt into the matching tool, then paste the bullet results back into
   `journal/inbox.md` — the same plain-text return path `journal_collect.py`'s `read_inbox`
   already ingests.
4. Re-running the collector (and then the summaries) folds the enriched inbox into the digest.

Every prompt caps the reply at 15 short, subject-level-only bullet lines (titles, people,
decisions, action items) and explicitly forbids message bodies, attachments, or confidential
excerpts, so whatever gets pasted back can never bloat the digest with raw transcript text.
When a digest is available, the only thing it contributes to a prompt is the sorted union of
project **names** already recorded by the other adapters — nothing else from the digest ever
reaches a prompt. This is pure, deterministic text generation: `journal_askpack.py` spawns
nothing and makes no network call of any kind; the Graph/OAuth/MCP connector paths for
Teams/Outlook/Copilot Studio remain deferred by design, and this pack is their fully offline
stand-in.

## The harness plan (advisory)

`bin/journal_advisor.py` turns the digest's per-source reports plus the three pricing files
(`data/pricing.json`, `data/pricing.copilot.json`, `data/pricing.codex.json` — never merged,
no rates hardcoded, no rates borrowed from one harness's file for another) into
`signals.harness`: for each harness (Claude Code, Copilot CLI, Codex CLI) it reports today's
actual usage plus a cheap-tier and a mid-tier task-cost estimate for two comparable task
sizes, all derived from those pricing files at run time, plus a ready-to-paste command
template for that harness. Codex figures in this signal stay labeled API-equivalent proxies
(`billed_usd: null`) — never a bill — exactly like the digest's own Codex proxy.

The next-day document's `## Harness plan` section (present only when `signals.harness`
exists) turns exactly these signals into prose: for each to-do, a recommended harness, a
model tier, a ready-to-paste command, and a one-line WHY grounded in the signals. This is
**advisory only** — nothing here dispatches, executes, or auto-pins anything; you read the
recommendation and decide.

## Scheduling

`journal_schedule.py` manages a macOS launchd job with four subcommands: `install`,
`uninstall`, `status`, and `run` (the manual one-shot — collect then summarize in one call).

`install` renders a launchd plist and writes it into the LaunchAgents directory, then **prints**
the `launchctl bootstrap`/`bootout` commands for you to run yourself — the installer never
executes `launchctl`. Loading (or unloading) the schedule is always your own, separate, manual
step. Logs from scheduled runs land under `journal/logs/`.

Outside the schedule, two manual paths exist any time: `journal_schedule.py run` for a one-shot
collect-and-summarize, or the `/polytropos:journal` skill, which runs the collector and
then drafts the three documents in your current session (no nested model spend) instead of
dispatching a separate model call.

## Privacy & safety

Every source is read strictly **read-only** — nothing under a source's home directory is ever
written to, and nothing is ever deleted or renamed. The summarizer's model call is disclosed,
not silent: sending the digest to a model means project/repo names, commit subjects, kit task
titles, and inbox text leave the machine via your own account, and this is stated in the
summarizer's own docstring, its `--dry-run` output, the skill, and here. The content-hygiene
rule above (metadata only, never transcript text) bounds what can possibly leak.

Nothing secret is ever written to the journal, its logs, or git — `journal/` is a single
gitignored entry covering the digest, the three documents, the inbox, and the logs together, so
none of it can land in a commit. This kit's own tests never touch a real source home or a real
schedule directory; every test and verify run points every source at a synthetic fixture in a
temporary directory instead.

## Deferred

**Cursor and VS Code adapters.** Both tools store usage in `state.vscdb`, an undocumented,
schema-drifting SQLite file. Opening a live SQLite database, even "read-only," can create
`-wal`/`-shm` side files next to it — exactly the risk this kit's read-only contract forbids —
so v1 ships only registered stubs for these two sources. The eventual implementation would copy
the database (and its WAL) to a temporary location first and open only that copy, never the
live file, plus per-version schema probing; the adapter contract already reserves their
registry rows so a real implementation is a pure slot-in later.

**Teams/Outlook augmentation.** No local data surface exists for either today, so v1 uses the
local `journal/inbox.md` file instead. Two paths are designed but deliberately not built: a
Microsoft Graph API integration (OAuth device-code flow, a token cache kept outside this repo,
network access at collect time) and an MCP-connector path (a Teams/Outlook MCP server queried
by the session running the journal skill, appending to the same inbox file). Either would feed
the same inbox signal with no digest schema change — no OAuth, tokens, or network exist in v1.
The ask-the-tools pack (see above) is the shipped, fully offline stand-in for both paths today.

**Weekly rollups** across multiple daily digests are not built either — the dated digest files
already provide the substrate for that later.

See `.claude/kits/daily-journal/PLAN.md` for the full reasoning behind all three deferrals.
