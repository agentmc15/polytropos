### What it does

The only confirmed way to change a model's reasoning effort on Copilot is interactive,
inside the `/model` picker — there is no headless flag, and this skill is as clear about
what does NOT exist as it is about what does.

### When to reach for it

- The user wants a model to think longer on a hard problem, or wants to cut latency on
  routine work.
- Before assuming a `copilot -p` flag controls this — it doesn't, and this skill says so
  plainly.
- Checking which models even have a reasoning dial before promising one.
- **Not** for picking which model to use at all — that's [route](route.md); this only
  tunes the model you're already on.

### Worked example

```bash
python3 bin/copilot_pricing.py knobs
```

Relay exactly what it prints — the confirmed level names and every mechanism note, never
enumerated from memory. To actually change it: open `/model`, select the row, then use the
left/right arrow keys to cycle its Reasoning value — the picker footer literally names this
control. Some rows show a dash and have no dial at all.

### Failure modes & fallbacks

- **A scripted or headless run needs effort control.** There is no confirmed `copilot -p`
  flag or settings key for it — say the limitation plainly rather than guessing one, and
  point at `knobs.reasoning_efforts_note` as where a future surface would be recorded.
- **Mixing vocabularies.** Copilot's picker shows Title-Case display words; never mix them
  with another CLI's lowercase effort tokens.
- **Jumping straight to the top level "just in case."** Step up one level at a time, only
  on concrete failure evidence.

### Cost & safety

Higher effort means longer thinking and more output tokens — AI Credits are real money,
not a bill-free unit. Size the stakes first with `python3 bin/copilot_pricing.py est
<PROFILE> <MODEL_ID>` and treat that number as a floor, not a ceiling, once effort is
raised.

### Related

- [route](route.md) — which model to use; this dial only tunes the one you picked.
- [escalate](escalate.md) — a capability gap calls for a tier jump, not a deeper effort
  setting.
- [Parity matrix](../index.md) — the Claude sibling folds this guidance into `route`
  instead of a skill of its own.
