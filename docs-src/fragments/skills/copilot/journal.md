### What it does

Builds the same cross-harness work journal the Claude and Codex versions do — the
collector already reads all three homes read-only — but on Copilot there is exactly one
sanctioned way to write the summaries: print the prompts and write the documents yourself,
in this session, because the headless path would dispatch a different CLI entirely.

### When to reach for it

- End of day, to turn today's Claude Code, Copilot CLI, and Codex CLI activity into a
  written record.
- You've already run this session for other work and don't want to spend a second
  dispatch just to summarize it.
- Comparing today against an earlier day's journal.
- **Not** a source of headless, unattended summaries from this harness — that mode exists
  in the engine but dispatches the Claude CLI, a cross-harness spend this skill must never
  trigger.

### Worked example

```bash
python3 bin/journal_collect.py --print
python3 bin/journal_summarize.py --date <date> --dry-run
```

The collector writes `journal/<date>/digest.json`, read-only and model-free. `--dry-run`
prints the three prompts (narrative, technical, next-day-plan) and spawns nothing — read
the digest, follow each prompt's required headings, and write the three documents yourself
to `journal/<date>/`, then link their paths rather than pasting full drafts into chat.

### Failure modes & fallbacks

- **`journal_summarize.py` run without `--dry-run`.** Its headless mode dispatches the
  Claude CLI to write the documents — never do this from a Copilot session; the two-pass
  flow above is the only sanctioned path here.
- **The digest looks empty or thin.** The collector is deterministic and read-only; an
  empty window means little activity was found, not a broken tool.
- **A repo isn't being scanned.** Pass `--repo PATH` (repeatable) to add it explicitly.

### Cost & safety

Collecting is free, model-free, and strictly read-only over the three homes; it writes
only under the gitignored `journal/<date>/` directory. Writing the summaries is what sends
the digest — metadata only, never transcript text — to a model, and that model is
whichever one this session is already running on.

### Related

- [Deep dive: daily journal](../../deep-dives/daily-journal.md) — the full pipeline,
  including the harness-agnostic next-day planning tool this skill's own card doesn't
  cover.
- [route](route.md) — which model to run the rest of this session on, if that wasn't
  already decided.
- [Parity matrix](../index.md) — the Claude and Codex journal skills, which document that
  planning tool directly.
