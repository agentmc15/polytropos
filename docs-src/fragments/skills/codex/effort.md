### What it does

Controls how hard one Codex run thinks, independent of which model it runs on — the
level vocabulary lives only in the pricing data, and this skill is careful to
distinguish real rungs on that ladder from `ultra`/`fast`, which are separate modes
whose CLI surfaces aren't published yet.

### When to reach for it

- A run got a wrong answer or missed a constraint, and the fix might be more thinking
  time rather than a bigger model.
- Bulk, extraction, or latency-sensitive work where shallow thinking is actually the
  point.
- Before assuming `ultra` or `fast` mode has a flag you can pass today — it may not.
- **Not** for picking which model to use — that's [route](route.md) or
  [escalate](escalate.md); this only tunes the model you're already on.

### Worked example

```bash
python3 bin/codex_pricing.py knobs
```

Relay exactly what it prints — the ladder in ascending order plus its notes, never
enumerated from memory. Apply it one-shot with `-c model_reasoning_effort=<level>` on
`codex exec`, or on a kit task with `codex_execute.py run --kit <dir> --task <id>
--effort <level>` (the driver validates the level against the data and rejects an
unknown word). Omit the override for routine work; step up exactly one level only on
concrete failure evidence, and re-run.

### Failure modes & fallbacks

- **`ultra` or `fast` mode looks like a flag away.** Its CLI surface is unpublished as
  of the data's `cached_date` — point at release notes rather than inventing one.
- **Starting at the deepest level "just in case."** Step up one level at a time, only
  on a run that actually got it wrong.
- **The wrong lever gets pulled.** Effort fixes a thinking-time gap; a tier jump
  ([route](route.md), [escalate](escalate.md)) fixes a capability gap — try the
  cheaper move first.

### Cost & safety

Under a ChatGPT sign-in, deeper effort draws down usage limits faster — any dollar
figure shown is a labeled API-equivalent proxy, never a bill. Under `OPENAI_API_KEY`
auth, the token-metered dollars are real. Either way, deeper effort means more
reasoning tokens and faster burn; ask which billing mode applies before recommending a
level if it's unclear.

### Related

- [route](route.md) — which model to use; this dial only tunes the one you picked.
- [escalate](escalate.md) — a capability gap calls for a tier jump, not deeper effort.
- [Deep dive: effort dial](../../deep-dives/effort-dial.md) — the fuller design
  behind the ladder and the modes-vs-rungs distinction.
