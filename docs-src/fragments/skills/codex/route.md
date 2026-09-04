### What it does

Model ids on this roster are best-effort for a preview generation, so this skill
never shows one — recommendations here are tier words plus a live estimate, priced
fresh from data each time, in whichever framing matches how you pay: burn under a
ChatGPT plan, real dollars under an API key.

### When to reach for it

- Before running anything non-trivial, to see a cost or burn estimate and a tier
  recommendation first.
- Deciding whether a cheaper tier or a faster mode would do just as well.
- Writing code that dispatches a Codex model and needs the right tier plus the
  actual invocation surface.
- **Not** a spend report — that's [usage](usage.md); this only estimates what a task
  is about to cost or burn, before it runs.

### Worked example

```bash
python3 bin/codex_pricing.py est <PROFILE> <MODEL_OR_TIER>
python3 bin/codex_pricing.py models --profile <PROFILE>
```

Map the task to a size, run two or three candidates in the chosen tier plus one lane
cheaper as a sanity check, then give a single action:

| Goal | Mechanism |
|---|---|
| one-shot dispatch | `codex exec "<task>" --model <model-id>` |
| interactive switch | `/model` picker in the Codex TUI |
| session start | `codex --model <model-id>` |
| persistent default | `model = "<model-id>"` in `~/.codex/config.toml` |
| named profile | `[profiles.<name>]` in `config.toml`, via `codex --profile <name>` |
| reasoning effort | `-c model_reasoning_effort=<level>` |

### Failure modes & fallbacks

- **This roster's `strong` tier is unpopulated.** Asking for `strong` resolves
  upward to frontier — there's no intermediate rung to try first.
- **`/model` doesn't list a frontier candidate.** The plan doesn't have it yet
  (limited preview) — route among what's actually listed.
- **A model id gets named from memory.** Don't — show no id on the page and
  re-derive fresh each time.

### Cost & safety

Under a ChatGPT sign-in, lead with the burn index — any dollar figure is a labeled
API-equivalent proxy, never a bill. Under `OPENAI_API_KEY` auth, the token-metered
dollars are real and authoritative. Speed facts (the cheap tier's low latency, a
frontier model's noted fast-inference availability) come from the data's own notes,
never invented; `fast` mode exists but its CLI surface is unpublished, so point at
release notes instead of guessing a flag.

### Related

- [effort](effort.md) — tunes how hard the picked model thinks, once you've chosen
  it.
- [escalate](escalate.md) — the verify-gated ladder for when the picked tier isn't
  enough.
- [frontier-check](frontier-check.md) — the deeper go/no-go once frontier becomes
  the question.
