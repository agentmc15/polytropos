### What it does

Turns today's Claude Code, Copilot CLI, and Codex CLI activity plus git history into a
written journal: a digest of metadata, then narrative, technical, and next-day-plan
summaries. Everything it produces lives under a gitignored folder — nothing here is ever
committed.

### When to reach for it

- End of day, to write down what actually happened instead of relying on memory later.
- Planning tomorrow from what's still open across kits, WIP repos, and the inbox.
- Folding a meeting or email to-do into tomorrow's plan without wiring up a real connector.
- **Not** a live activity monitor — it reads a snapshot of today's local logs, once, when
  you run it.

### Worked example

| Step | Command | Writes |
|---|---|---|
| Collect | `python3 bin/journal_collect.py` | `journal/<date>/digest.json` |
| Snapshot | `python3 bin/telemetry_snapshot.py` | `telemetry/` (durable, best-effort) |
| Summarize | `python3 bin/journal_summarize.py --date <date> --dry-run` | prompts only — you write the three docs in-session |
| Plan | `python3 bin/journal_plan.py build` | `journal/plan/<date>.md` |
| Track | `journal_plan.py check` / `done <id>` / `defer <id> --to <date>` | updates that same file |

`--dry-run` prints the exact prompts without dispatching anything, because the current
session is already paid for; a headless run (`journal_summarize.py --date <date>`, no
`--dry-run`) dispatches a routed model instead, escalating once before giving up.
`journal_plan.py prompt` follows the same in-session precedent for enriching a plan card's
own text.

### Failure modes & fallbacks

- **A document still fails after one escalation** in headless mode — the script exits with
  a distinct code rather than silently shipping only two of the three summaries.
- **The user wants it to run unattended.** Read `references/scheduling.md`: a launchd
  install/uninstall/status/run surface whose installer writes the schedule but never loads
  it — the activation step stays a manual one.
- **The user wants Teams/Outlook/Copilot Studio context folded in.** Read
  `references/ask-the-tools.md`: an offline prompt pack you run yourself and paste results
  back into the inbox — there is no Graph/OAuth/MCP connector, by design, ever.

### Cost & safety

Collecting and snapshotting are model-free and read-only over three local log directories;
the digest itself carries only counts, ids, titles, and short strings — never transcript
text. Writing the summaries is the one step that sends that digest to a model. Codex
figures anywhere in the journal are labeled API-equivalent relative-burn proxies, never a
bill — they never enter a priced total.

### Related

- [memory](memory.md) — durable facts across sessions, versus this skill's dated record of
  one day.
- [cost-report](cost-report.md) — the deeper spend analysis behind what the journal
  summarizes.
- [Deep dive: daily journal](../../deep-dives/daily-journal.md) — the full pipeline and
  privacy model.
