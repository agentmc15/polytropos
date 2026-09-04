### What it does

This never calls the `copilot` CLI to gather your spend — the logs already sitting on
disk are the source, so checking your own numbers costs nothing and touches no network.
What comes back is the same shape as the Claude cost report: total spend, which model
dominated, and specific sessions where a cheaper tier likely would have done just as well.

### When to reach for it

- You want to know what you've actually spent, not what you assume you spent.
- Checking which sessions used an expensive tier for a small amount of work.
- Deciding whether a default-model change would have saved credits over a recent window.
- **Not** for "what should I use next" — that's [route](route.md); this only looks
  backward.

### Worked example

```bash
python3 bin/copilot_usage.py --days 30
```

Read it top to bottom: a headline total in USD and AIC and the dominant model, a
by-model table, then downgrade-candidate sessions with the script's own
estimated-savings figure — relay that number rather than restating it yourself. Add
`--top N` for more or fewer sessions, or `--copilot-home DIR` / `--session-dir DIR` to
point at a non-default home.

### Failure modes & fallbacks

- **A session mixed models.** Its whole token split is attributed to the LAST model and
  flagged `≈` — the logs carry no per-model split to attribute more precisely, so never
  present a flagged figure as exact.
- **`totalNanoAiu` shows up in the output.** That's Copilot's own reported consumption
  unit, shown only as a labeled cross-check — never convert it to USD or AIC yourself;
  the authoritative estimate is token counts priced through the pricing file.
- **Logs are missing or empty.** Report that plainly rather than guessing a number; if
  the script errors, show the error and the file it choked on.

### Cost & safety

Strictly read-only over `<copilot-home>/session-state/*/events.jsonl` — never the `*.db`
stores, and never a live `copilot` call, because that would spend real credits and hit
the network for a report that's supposed to be free. Every dollar and credit figure is
priced from the pricing file at run time, never quoted from memory.

### Related

- [route](route.md) — the forward-looking sibling: estimate a task before running it.
- [bench-routing](bench-routing.md) — a benchmark-informed routing check, not a spend
  report.
- [Deep dive: Copilot cost visibility](../../deep-dives/copilot-costviz.md) — the fuller
  design behind this report and its runway math.
