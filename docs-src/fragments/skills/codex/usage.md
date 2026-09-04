### What it does

Reads local Codex session logs and reports exactly one of three honest outcomes —
priced activity, unpriced activity, or nothing found — never inventing a number to
fill a gap the logs don't support.

### When to reach for it

- You want to know what you've actually used or burned, not a guess.
- Checking which model dominated a recent window before changing a default.
- Deciding whether cheap-tier work has quietly been running on a pricier model.
- **Not** for "what should I use next" — that's [route](route.md); this only looks
  backward.

### Worked example

```bash
python3 bin/codex_usage.py --days 30
```

Present exactly the branch the engine returns, never upgraded or downgraded:

| Branch | What it means |
|---|---|
| Tokens found | a priced per-model table, plus the proxy disclaimer, relayed verbatim |
| Activity, no tokens | counts only — sessions, records, models seen — unpriced, said plainly |
| Nothing found | the logs are empty; never fabricate or zero-fill a figure |

Add `--top N` for more or fewer rollouts listed, or `--codex-home DIR` to point at a
non-default home.

### Failure modes & fallbacks

- **A rollout mixed models.** Its whole token count is attributed to the LAST model
  seen in that file and flagged `≈` — never fabricate a per-model split the logs
  don't record.
- **A malformed line or an unpriced model turns up.** Call it out rather than
  silently dropping it from the totals.
- **The billing mode is unclear.** Ask before presenting a figure as either a real
  bill or a burn proxy.

### Cost & safety

Strictly read-only over local JSONL logs — never a `*.db` file, and never a live
`codex` call to gather this. Under a ChatGPT plan every dollar figure is a labeled
API-equivalent relative-burn proxy and a routing aid, never a bill; only under
`OPENAI_API_KEY`-metered use are the dollars real.

### Related

- [route](route.md) — the forward-looking sibling: estimate a task before running
  it.
- [journal](journal.md) — folds this same activity into a daily cross-harness
  record.
- [Deep dive: how it works](../../deep-dives/how-it-works.md) — the billing-mode
  framing this report's figures come from.
