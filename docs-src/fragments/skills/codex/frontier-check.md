### What it does

Decides whether a task actually justifies the frontier tier on this roster, and if
so, how to run it well — never by naming a specific model id, because ids here are
best-effort for a preview generation and corrections land only in the pricing data's
own note.

### When to reach for it

- Long-horizon autonomous work expected to finish without correction.
- A concrete failure by the mid tier on this exact task — the strongest signal
  available, since this roster ships no populated `strong` tier to try first.
- The deepest reasoning or multi-source synthesis, not routine lookup.
- **Not** for routine coding, well-known solutions, or low-latency work — the cheap
  tier is the speed lane; frontier burns usage limits fastest of anything on the
  roster.

### Worked example

```bash
python3 bin/codex_pricing.py models --json
python3 bin/codex_pricing.py est <PROFILE> frontier
python3 bin/codex_pricing.py est <PROFILE> mid
```

`est` accepts a tier word directly, so the frontier candidate never has to be
hardcoded — run it once for frontier and once for mid to build today's actual ratio.
Recommend, then give the one action:

| Goal | Mechanism |
|---|---|
| one-shot dispatch | `codex exec "<task>" --model <model-id>` (`--full-auto` if it must edit files) |
| interactive switch | `/model` picker in the Codex TUI |
| persistent default | `model = "<model-id>"` in `~/.codex/config.toml` |
| reasoning effort | `-c model_reasoning_effort=<level>` |

### Failure modes & fallbacks

- **The frontier model refuses.** Vendor safety classifiers can decline cyber/bio-
  adjacent requests — check its `notes` field, then fall back to the mid tier instead
  and say why.
- **`/model` doesn't list a frontier candidate.** The plan doesn't have it yet
  (limited preview) — route among what's actually listed and say so plainly.
- **A model id gets quoted from memory.** Don't — this file must never contain a real
  model id; derive it fresh from the engine's output every time.

### Cost & safety

Under a ChatGPT plan, lead with the burn index, not dollars — any dollar figure shown
is a labeled API-equivalent proxy, never a bill; under `OPENAI_API_KEY` auth the
token-metered dollars are real and authoritative. `fast` mode exists but its CLI
surface is unpublished — point at release notes rather than inventing a flag.

### Related

- [route](route.md) — which model overall, before frontier becomes the question.
- [escalate](escalate.md) — the verify-gated ladder for one task, frontier as its
  last rung.
- [architect](architect.md) — for multi-task frontier-class work, so the spend
  concentrates in planning.
