### What it does

A skill is just text loaded into the window — it can't remove anything from the message
array a call submits. This one measures instead: how heavy each call has been, what filled
that weight, and which of three levers — prevent, prune, or measure — applies right now.
Only the harness (compaction, or context editing for API callers) can actually act on what
it finds.

### When to reach for it

- Context feels huge, you're closing in on the window limit, or you're wondering whether to
  `/compact`.
- Cache-read tokens dominate a cost report and you want to know whether that's a problem.
- Before a long task, to pick which of the five habits in `references/practices.md` applies.
- **Not** a fix by itself — expecting the window to shrink on its own is the most common
  misreading of this kit; it says what to act on, the harness is what acts.

### Worked example

```bash
python3 bin/context_weight.py session --harness claude
python3 bin/context_weight.py watch
```

`session` prints a growth curve and a ranked "what filled the window" table; `watch`'s
`recommendation` line moves from `no action` through `delegate new bulk reads, do not
inline` to `checkpoint decisions to disk, then compact` past roughly 60% of the window. In
one session, `watch` found a near-full window whose avoidable (tool-ingested) mass was a
small slice — most was assistant output and user input, untouched by *prevent* or *prune*.
Bash led the slice: the real size of the *prevent* opportunity, not proof prevention
dominates.

### Failure modes & fallbacks

- **Cache reads dominate the total.** Usually the cache working correctly, not a
  misconfiguration — the real driver is resident context × number of API calls; read
  `references/columns.md` before trimming a config surface instead.
- **The question is repo structure, not a file's contents.** A wide read sweeps tens of
  thousands of tokens into the window on every later call; a graphify graph answers the
  same question while pulling only a small fraction of those tokens into the window —
  reach for [graphify](graphify.md) first.
- **`watch codex` or `watch copilot`.** Both print an honest refusal and exit 0 instead of
  fabricating a number those logs can't support — use `session`/`overview` on a schedule
  instead; there's no live substitute.

### Cost & safety

Every command here is read-only measurement — nothing dispatched, nothing written. Dollar
figures are API-equivalent estimates priced from measured tokens only, each inside its own
harness section; there is no cross-harness total anywhere in this tool's output.

### Related

- [graphify](graphify.md) — the prevention-shaped alternative to a wide exploratory read.
- [execute](execute.md) — the phase-start fence re-read `constraints --kit` exists to check.
- [Deep dive: context weight](../../deep-dives/context-weight.md) — the fuller design behind
  the three levers.
