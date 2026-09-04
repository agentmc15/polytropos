### What it does

Builds the same cross-harness work journal the Claude and Copilot versions do — the
collector already reads all three homes read-only — but on Codex there is exactly one
sanctioned way to write the summaries: print the prompts and write the documents
yourself, in this session, because the headless path dispatches the Claude CLI
directly.

### When to reach for it

- End of day, to turn today's Claude Code, Copilot CLI, and Codex CLI activity into a
  written record.
- Building tomorrow's runbook from open kit tasks, WIP repos, and the inbox.
- Folding a Teams/Outlook/Copilot Studio note into the journal without a real
  connector.
- **Not** a source of headless, unattended summaries from this harness — that mode
  exists in the engine but dispatches the Claude CLI, a cross-harness spend this
  bundle must never trigger.

### Worked example

```bash
python3 bin/journal_collect.py --print
python3 bin/journal_summarize.py --date <date> --dry-run
python3 bin/journal_plan.py build
```

`--dry-run` prints the three prompts and spawns nothing — write the documents
yourself from `journal/<date>/digest.json`. `journal_plan.py build` writes a dated,
checkable next-day plan with ready-to-paste commands for all three harnesses, priced
from each harness's own pricing file (Codex figures there are API-equivalent proxies,
never a bill); `prompt` enriches its What/How bodies the same in-session way.

### Failure modes & fallbacks

- **`journal_summarize.py` run without `--dry-run`.** Its headless mode dispatches
  the Claude CLI to write the documents — never do this from Codex; the two-pass flow
  above is the only sanctioned path here.
- **Teams/Outlook/Copilot Studio context is wanted.** `journal_askpack.py --date
  <date> --print` generates an offline prompt per tool — no network, OAuth, Graph, or
  MCP call is ever added to fetch that content; paste the results back into
  `journal/inbox.md` yourself.
- **The digest looks thin.** The collector is deterministic and read-only; little
  activity means little to summarize, not a broken tool.

### Cost & safety

Collecting is free, model-free, and strictly read-only over the three homes; it
writes only under the gitignored `journal/` directory. Writing the summaries is what
sends the metadata-only digest — never transcript or message text — to a model.

### Related

- [Deep dive: daily journal](../../deep-dives/daily-journal.md) — the full pipeline
  and privacy model.
- [usage](usage.md) — Codex's own historical activity, versus this journal's
  cross-harness digest.
- [Parity matrix](../index.md) — the Claude and Copilot journal skills, and where
  this one differs.
