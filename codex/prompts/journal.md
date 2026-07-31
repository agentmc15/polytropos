---
description: Generate the daily work journal — collect today's AI usage across Claude Code, Copilot CLI, and Codex CLI plus git activity into a digest, then write the narrative, technical, and next-day-plan summaries. Use when the user asks for their work journal, daily summary, "what did I do today", or to plan tomorrow.
---

You generate the daily work journal — a read-only digest of what happened today across Claude
Code, Copilot CLI, and Codex CLI, plus git activity, turned into three plain-language summaries.
The collector engine is harness-agnostic: it already reads `~/.claude`, `~/.copilot`, and
`~/.codex` read-only, so running it from here produces the same cross-harness journal Claude
Code or Copilot CLI would produce.

## Collect the digest

```bash
python3 {{POLYTROPOS_ROOT}}/bin/journal_collect.py --print
```

Flags (the real argparse surface — do not invent others): `--date YYYY-MM-DD` for a specific
day (default: today), `--repo PATH` (repeatable) to add a git repo to scan, `--journal-dir DIR`
to override where it writes. The collector is deterministic and read-only over the three
homes — it never calls a model and never touches the network. It writes only under the
gitignored `journal/<date>/` directory (`digest.json`), nowhere else.

## Write the summaries in-session — the ONLY mode from this harness

Print today's three prompts without dispatching anything:

```bash
python3 {{POLYTROPOS_ROOT}}/bin/journal_summarize.py --date <date> --dry-run
```

Read `journal/<date>/digest.json` for the facts, follow each printed prompt's required
headings exactly, and write the three documents YOURSELF — this session is already paid for,
so there is no reason to spawn a nested call. Save your drafts to
`journal/<date>/narrative.md`, `journal/<date>/technical.md`, and `journal/<date>/next-day.md`,
using digest facts only — no invented details, no transcript text. When done, summarize the
three documents for the user and link their paths — do not paste full drafts into chat.

**Never run `journal_summarize.py` without `--dry-run` from this harness.** Its headless mode
dispatches the Claude CLI directly — a cross-harness spend this bundle must never trigger.
`--dry-run` is the only sanctioned invocation of this script here.

## Inbox & ask-the-tools

Drop meeting notes or to-dos into `journal/inbox.md` as plain lines; the next collection folds
them into the digest. For Microsoft tools with no connector here (Copilot Studio, Teams,
Outlook):

```bash
python3 {{POLYTROPOS_ROOT}}/bin/journal_askpack.py --date <date> --print
```

This generates one ready-to-paste prompt per tool — run each inside that tool's own AI, then
paste the bullet results back into `journal/inbox.md` and re-collect. This is offline text
generation only: no network, OAuth, Graph, or MCP call is ever added to fetch this content.

## Next-day runbook

```bash
python3 {{POLYTROPOS_ROOT}}/bin/journal_plan.py build
```

writes a dated, checkable next-day plan at `journal/plan/<date>.md` — one card per planned
task, drawn from open kit tasks, WIP repos, the inbox, and `journal/plan/seed.md`, each with a
What/How, an ideal-harness line, and ready-to-paste commands for Claude Code, Copilot CLI, and
Codex CLI, priced from the pricing data files (Codex figures there are API-equivalent proxies,
never a bill). Enrich the What/How bodies in-session (the summaries precedent — this session is
already paid for):

```bash
python3 {{POLYTROPOS_ROOT}}/bin/journal_plan.py prompt
```

follow the printed prompt exactly (rewrite ONLY the What/How bodies; keep every other line
byte-identical), then save the revised document back over the same path. Track cards with
`check`, `done <id>`, and `defer <id> --to <date>`. Advisory only — the runbook prepares and
tracks; it never schedules or executes anything.

## Privacy

The digest is metadata-only — project and repo names, commit subjects, kit task titles, and
any inbox text, never transcript or message text. Everything the journal produces stays under
the gitignored `journal/` directory; nothing here is committed to git.

## If the bundle isn't installed

`{{POLYTROPOS_ROOT}}` is rewritten to this repo's absolute path when the bundle is
installed by `bin/harness_select.py`. If you still see the literal `{{POLYTROPOS_ROOT}}`
text, the bundle is not installed — tell the user to run
`python3 bin/harness_select.py install --harness codex`.
