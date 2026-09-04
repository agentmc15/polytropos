### What it does

Same idea as Claude's architect skill — spend the expensive planning once, on the
strongest tier, then hand a cheaper tier a kit it can execute task by task — but the
mechanics here are Copilot-specific: kits live at `tasks/kits/<slug>/`, and
`bin/copilot_execute.py` actually PARSES `TASKS.md`, so the task skeleton's punctuation is
load-bearing, not just tidy formatting.

### When to reach for it

- A task big enough that one wrong early call would compound across many later steps.
- Before running `/execute` on anything with more than a task or two.
- You want a kit a mid-tier model can run without re-deciding what the top tier already
  settled.
- **Not** for execution — this skill writes the kit and stops; `/execute` runs it.

### Worked example

````markdown
### T1 — Short title

- status: pending
- model: <model-id>
- depends: (none)
- independent: yes

**Brief.** The self-contained brief text.

**Acceptance.** The checkable criteria.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_something.py'
```
````

Before handing off, self-check:
`python3 bin/copilot_execute.py status --kit tasks/kits/<slug>` — every task should list
with its status and no parse error, because a drifting task block makes the kit
undispatchable, not just untidy.

### Failure modes & fallbacks

- **A verify command would invoke the real Copilot CLI.** Never write one that does —
  dispatch loops are `/execute`'s job, and a live call spends real AI Credits.
- **A tier looks wrong for the work.** Re-derive it from `copilot_pricing.py models`,
  never from memory — the roster changes underneath a remembered pin.
- **The literal `{{POLYTROPOS_ROOT}}` text appears on the card.** The bundle isn't
  installed — run `python3 bin/harness_select.py install --harness copilot`, then
  `/skills reload`.

### Cost & safety

Planning is the expensive part, by design — spending frontier-tier judgment once so
execution runs cheap afterward is the whole premise of this skill. Doing that planning is
a real, paid dispatch: either this session switches to the frontier tier itself, or the
whole job goes to `copilot --agent architect`, whose frontmatter pin runs it there.
Reading the pricing data (`models`, `prefs`) and the self-check (`copilot_execute.py
status`) before handing off cost nothing; use tier words only, never a specific model id,
when writing a kit's own task pins.

### Related

- [execute](execute.md) — runs the kit this skill writes.
- [budget](budget.md) — a cheaper dispatch ladder for the kit `/execute` runs.
- [Parity matrix](../index.md) — the Claude sibling this mirrors, and where the mechanics
  differ.
