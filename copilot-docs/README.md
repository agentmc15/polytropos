# GitHub Copilot CLI documentation center

This is the documentation center for using the **polytropos** repository through the
GitHub Copilot CLI. It explains what gets installed, what each skill and agent does, how
model tiers and pricing work, and where the safety boundaries are — for a first-time user
and for maintainers.

## Start here

1. Read [`INSTALL.md`](INSTALL.md) ([HTML](install.html)) and run the install preview command before installing anything for real.
2. Read [`SAFETY.md`](SAFETY.md) ([HTML](safety.html)) so you know which operations can spend AI Credits and which are free.
3. Come back here and use the table below to find the guide you need next.

## Choose a guide

| Guide | Markdown | HTML | What it covers |
|---|---|---|---|
| Documentation center home | README.md | [index.html](index.html) | This page. |
| Install | [INSTALL.md](INSTALL.md) | [install.html](install.html) | Installing and refreshing the bundle, in-session discovery. |
| Safety | [SAFETY.md](SAFETY.md) | [safety.html](safety.html) | Cost boundaries, test isolation, honesty rules. |
| AIC report | [AIC-REPORT.md](AIC-REPORT.md) | [aic-report.html](aic-report.html) | The machine-generated estimated-cost report for every document in this center (`aic-report.json` is the machine-readable authority). |

Additional guides covering skills, agents, model tiers, and cost accounting in depth are
added to this table as they are written.

## Skills versus agents

> This bundle ships two different Copilot CLI capability surfaces, and they are not the
> same thing. A skill can be requested explicitly by typing `/name` in a prompt, and
> Copilot can also auto-load a skill when a request's wording matches its description —
> but this is **not** a true custom slash-command registry the way Claude Code's
> `/polytropos:NAME` commands are. An agent is an isolated persona you switch into
> (through the `/agent` picker or a one-shot dispatch) that can carry its own model pin;
> a skill runs on whatever model the current session already has selected.

## Cost labels

Two different kinds of "cost" appear across these guides, and they are never mixed:

- **Estimated document AIC** — a prospective authoring-cost estimate for one Markdown document in this center, computed from an assumed task-size profile and the currently resolved model for that document's tier. See `AIC-REPORT.md` for the full breakdown.
- **Usage history** — an accounting of AI Credits actually spent in past Copilot CLI sessions, produced by `bin/copilot_usage.py` and covered in a later guide.

Neither figure is a bill. Only GitHub's own account usage page is the bill of record.

## Sources and freshness

Every price, model id, and reasoning-effort fact in this center is read at run time from
`data/pricing.copilot.json` — never copied into authored prose. That file carries its own
`cached_date` field, and `AIC-REPORT.md` / `aic-report.json` record the pricing and
preference snapshot that produced the current report. To check whether this center is
still fresh against the repository's current state, run:

```bash
python3 bin/copilot_docs.py check
```

## Guides and their HTML companions

Every Markdown guide in this center has a matching, offline, styled HTML companion sharing
the same base name (for example `INSTALL.md` and `install.html`). The HTML pages link back
to their Markdown source, and links between guides are rewritten automatically between the
two forms. Open any `.html` file directly in a browser — no server, network access, or
build step is required to read them.
