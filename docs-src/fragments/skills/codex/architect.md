### What it does

Same instinct as the other harnesses' architect skill — plan once, then hand a cheaper
tier a kit to execute task by task — but a task's `model` field here can be either a
real model id or a tier word (`cheap|mid|strong|frontier`) resolved at dispatch time,
because ids are unconfirmed for this preview-generation roster and a tier word survives
a correction that lands only in the pricing data.

### When to reach for it

- A task big enough that one wrong early call would compound across many later steps.
- Before running `$execute` on anything with more than a task or two.
- Writing a kit you want a cheaper tier to run without re-deciding what already got
  settled.
- **Not** for execution — this skill writes the kit and stops; `$execute` runs it.

### Worked example

Invoke explicitly with `$architect`, or let Codex match it from your request:

```bash
python3 bin/codex_pricing.py models
python3 bin/codex_pricing.py est <PROFILE> <MODEL_OR_TIER>
```

Pin each task's `model` field from that roster — an id or a tier word, never a guess. A
tier left unpopulated on today's roster resolves upward to the next populated one at
dispatch, so relying on that rule beats hardcoding an id a future correction would
silently invalidate.

### Failure modes & fallbacks

- **The plugin root can't be proven.** Every Codex skill checks this before shelling
  out; a literal `{{POLYTROPOS_ROOT}}` or a missing engine means stop and point at
  [doctor](doctor.md) rather than guessing a path.
- **A verify command would invoke the real `codex` CLI.** Never write one that does —
  dispatch is `$execute`'s job, and a live run spends real usage limits or API dollars.
- **A tier looks wrong for the work.** Re-derive it from `codex_pricing.py models`,
  never from memory — ids on this roster are best-effort for a preview generation.

### Cost & safety

Writing the kit doesn't dispatch anything on its own — the session already running
this skill is whatever model the desktop app or CLI is currently on, and nothing here
re-routes it. The real spend comes later: when `$execute` runs a kit task,
`bin/codex_execute.py` passes that task's resolved model straight to `codex exec
--model <id>`, a real dispatch against usage limits or API dollars. Read the pricing
data (`models`, `est`) before pinning any task — never from memory.

### Related

- [execute](execute.md) — runs the kit this skill writes.
- [doctor](doctor.md) — the root-resolution check every Codex skill depends on.
- [Parity matrix](../index.md) — the Claude and Copilot siblings, and where the
  mechanics differ.
