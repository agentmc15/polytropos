### What it does

Walks your local Claude Code transcripts and turns raw usage into a spend report: total
cost over a window, which model dominated it, and — the part worth acting on — sessions
where a cheaper model would plainly have sufficed. It reads only what's already on disk;
nothing is sent anywhere and nothing is dispatched.

### When to reach for it

- You want to know what you've actually spent, not what you assume you spent.
- Deciding whether your daily-driver default is costing more than the work needs.
- Comparing a period after a routing change against one before it.
- **Not** a live estimate for a task you haven't run yet — that's [route](route.md); this
  only reads history.

### Worked example

```bash
python3 bin/cost_report.py --days 30
```

Read it top to bottom: a headline total and dominant model, a by-model table, then
downgrade-candidate sessions — small-footprint runs on Fable or Opus that a lighter model
likely would have handled — ending on one recommendation drawn from what the data actually
shows. The framing of that delta depends on billing mode: in `api` mode it's savings; in
`subscription` mode the same number is rate-limit burn share, never money spent. Add
`--mode api|subscription` to force a framing, `--top N` for more or fewer sessions listed,
`--json` for the payload instead of markdown, and `--projects-dir DIR` to point the walk at
a non-default transcript directory.

### Failure modes & fallbacks

- **An empty report on a fresh machine.** A present-but-empty transcript directory still
  renders the full report labeled `no transcripts in window: <dir>` — a zero-row report is
  honest output, not a broken tool, and its zeros are not measured spend.
- **A missing transcript directory entirely** prints `No transcript directory at <path>`
  and renders nothing — a distinct, more specific outcome than the empty case above.
- **An unexpected transcript format.** The script surfaces the error and the file it choked
  on rather than silently skipping it — relay both, don't paper over either.

### Cost & safety

Reading transcripts is free and read-only; nothing is dispatched and nothing is written.
Every dollar is priced from
[`data/pricing.json`](https://github.com/agentmc15/polytropos/blob/main/data/pricing.json)
at run time, including any dated intro-pricing window the file defines — never a number
hardcoded here.

### Related

- [route](route.md) — the forward-looking sibling: estimate a task before running it.
- [execute](execute.md) — its own scorecard covers dollars for one kit run instead of a
  rolling window.
- [Deep dive: how it works](../../deep-dives/how-it-works.md) — the billing-mode framing
  this report's two readings come from.
