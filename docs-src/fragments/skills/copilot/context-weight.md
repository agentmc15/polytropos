### What it does

Same measurement instinct as the Claude version, adjusted to what Copilot's own logs can
actually support: it reports a per-session average weight instead of a call-by-call growth
curve, because Copilot's session logs carry no per-turn input/cache split to build one
from.

### When to reach for it

- Wondering whether a session is running heavy, or where a `copilot-instructions.md`
  surface sits against a token budget.
- Before a long task, to apply the prevent/prune/measure levers once rather than
  reactively.
- Comparing sessions to see whether a habit change actually lowered the average.
- **Not** a live threshold monitor — there is no growth curve to watch in real time on
  this harness; apply the levers on a schedule instead.

### Worked example

```bash
python3 bin/context_weight.py session --harness copilot
python3 bin/context_weight.py audit
```

`session` prints a session-average weight — `(input + cache_read + cache_write) /
assistant turns` — labeled plainly as the honest substitute for a curve, never a curve in
disguise. `audit` checks resident config surfaces, including `copilot-instructions.md`,
against a token budget.

### Failure modes & fallbacks

- **`watch copilot`, not `watch --harness copilot`.** `watch` takes the harness as a plain
  positional argument and has no `--harness` flag at all — that flag exists on
  `constraints`, which is an easy mix-up. Running it prints an honest refusal and exits 0
  instead of fabricating a live number.
- **A dollar figure on the `session`/`overview` cards looks like real spend.** It's always
  labeled `API-equivalent dollars — an estimate, not a bill.` — relay it with that label,
  never stripped, and never add it to [usage](usage.md)'s real numbers.
- **Expecting the window to shrink on its own.** This skill only measures; only the
  harness itself can act, via compaction.

### Cost & safety

Every command here is read-only measurement — nothing dispatched, nothing written. Dollar
figures are API-equivalent estimates priced from measured tokens through this harness's own
pricing file, always carrying their estimate label.

### Related

- [Deep dive: context weight](../../deep-dives/context-weight.md) — the fuller fidelity
  story and what the Claude harness can additionally support.
- [budget](budget.md) — the other honest-measurement-heavy Copilot page.
- [usage](usage.md) — real historical spend, versus this page's context-carry estimate.
