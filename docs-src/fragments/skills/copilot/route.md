### What it does

AI Credits are real money on this harness, not a synthetic score — so before dispatching
anything non-trivial, this skill prices a few candidates and shows both USD and the credit
count, read from the current pricing data rather than a remembered rate.

### When to reach for it

- Before running anything non-trivial, to see a cost estimate and a tier recommendation
  first.
- Writing code that dispatches a Copilot model and needs the right tier plus the actual
  invocation surface.
- Checking whether a cheaper lane would do just as well before spending on a stronger one.
- **Not** a spend report — that's [usage](usage.md); this only estimates what a task is
  about to cost, before it runs.

### Worked example

Map the task to a `task_profiles` size, then estimate a few candidates:

```bash
python3 bin/copilot_pricing.py est <PROFILE> <MODEL_ID>
```

Run it for two or three candidates in the chosen tier plus one lane cheaper as a sanity
check, present USD and AIC per candidate, then give a single action:

| Goal | Mechanism |
|---|---|
| one-shot dispatch | `copilot -p "<task>" --model <model-id>` |
| interactive switch | `/model` |
| session default | `COPILOT_MODEL=<model-id>` env var |
| persistent default | `"model"` key in `~/.copilot/settings.json` |
| per-agent pin | `model:` frontmatter in an agent file |

### Failure modes & fallbacks

- **`tasks/lessons.md` exists in the working repo.** Read it before classifying — a
  routing-category entry overrides the default tier heuristics below it.
- **Two tiers look equally plausible.** Pick the cheaper one and name the failure signal
  that would justify upgrading, rather than guessing up front.
- **The recommendation names a specific model from memory.** Don't — tier words plus
  engine output only; the roster changes underneath a remembered id.

### Cost & safety

Every number is read at run time from the pricing data — the AIC-to-USD rate itself is
data (`billing_unit.usd_per_credit`), never quoted from memory. If a monthly plan is
known, `runway <PLAN> <PROFILE> <MODEL_ID>` shows how much of it one task burns. Routing
itself is free; the only spend is the dispatch you actually run afterward.

### Related

- [lessons-loop](lessons-loop.md) — the routing-lesson file this skill reads before
  classifying.
- [escalate](escalate.md) — the verify-gated ladder for when the picked tier isn't
  enough.
- [budget](budget.md) — a cheaper dispatch lane for kit work specifically.
