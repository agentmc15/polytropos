---
name: escalate
description: Run one task on the cheapest sufficient model behind a machine-checkable success check, escalating to a stronger tier — frontier last — only if the check fails. Use for "try it cheap first, fall back to the top model if it doesn't work".
---

You run ONE task through a cost-ascending ladder of models, promoting to the next tier only
when a machine-checkable check FAILS — so the frontier tier is spent on genuine difficulty,
never on routine work. You dispatch each attempt and verify it yourself; a dispatched run's own
claim of success is never evidence.

## Step 0 — Pin the trigger

Before dispatching anything, pin a machine-checkable success condition: a test command, a
build, a lint, a script that exits non-zero on failure. If the task genuinely has no checkable
outcome (open-ended writing, a judgment call), say so plainly — automatic escalation can't fire
reliably here. Don't pretend a vibe is a verify.

## Step 1 — Pick the first (cheapest sufficient) tier

Default to the cheapest tier you'd actually trust for this task, from the data's four-value
vocabulary (`cheap|mid|strong|frontier`):

```bash
python3 {{POLYTROPOS_ROOT}}/bin/copilot_pricing.py models --json
```

Pick a candidate model id from that tier's rows in the data at run time — never from memory.

## Step 2 — Dispatch

```bash
copilot -p "<self-contained brief>" --model <model-id>
```

The dispatched run sees nothing of this session, so the brief must be self-contained: the task,
the context it needs, and the verify command with an explicit instruction to run it and report
the output.

## Step 3 — Verify independently

Run the verify command YOURSELF, from the correct working directory — the dispatched run's
success claim is not evidence.

- **Passes** → done. Note it never needed the frontier tier.
- **Fails** → retry ONCE on the same model, handing it the exact failure output. Re-run the
  verify command.
- **Fails again** → escalate (Step 4).

## Step 4 — Climb the ladder

Exactly the rule `bin/copilot_execute.py` implements for kit tasks: tiers strictly ABOVE the
current model's tier, in `cheap → mid → strong → frontier` order; take the FIRST model in
pricing-file order carrying each tier; tiers with no models on the roster are skipped. Derive
the ladder from the data at run time (`models --json`) — never from memory. Each hop carries
evidence only: what was tried and the exact verify output from the failed rung.

The frontier rung is last. When you reach it, say what makes this task frontier-worthy (see the
`frontier-check` skill for that judgment). If the frontier model declines the request (vendor
safety classifiers — check its `notes` field in the data), fall back to a strong-tier hop
instead and say why. If the top rung still fails, stop and report honestly: what each tier
tried, the final verify output, and whether the task looks mis-specified. Never keep climbing
past the frontier rung. AI Credits are money — always report which rung ultimately passed the
verify command, so the ladder's savings are visible.

## Kit tasks

For a task that lives in a `tasks/kits/<slug>/` kit, prefer the driver itself over dispatching
by hand — it implements this same ladder with statuses and an escalation cap:

```bash
python3 {{POLYTROPOS_ROOT}}/bin/copilot_execute.py run --kit <dir> --task <id> --max-escalations <N>
```

This skill is for one-off tasks outside a kit. For multi-task frontier-class work, prefer
`/architect` + `/execute` over calling this skill in a loop.

## User model prefs (pins & excludes)

The user can pin which model a tier resolves to, or exclude models from consideration —
via the gitignored prefs file (`prefs/copilot.json` at the optimizer repo root) or the
driver's per-run flags. Check what is active before recommending anything:

```bash
python3 {{POLYTROPOS_ROOT}}/bin/copilot_pricing.py prefs
```

Honor it: never recommend an excluded model — if the natural pick is excluded, say so and
name the next candidate from the `prefs` output's tier resolution. When a tier is pinned,
the pinned model IS that tier's pick (a cross-tier pin is a deliberate user override,
priced at the pinned model's own rates — `est` it directly). Pins or excludes the user
states in the prompt count the same as the file.

The driver enforces these mechanically: `bin/copilot_execute.py run` takes repeatable
`--pin TIER=MODEL_ID` and `--exclude MODEL_ID` flags (flags override the file;
`--no-prefs` ignores the file). On the ladder, excluded models are skipped in favor of
the next model in pricing-file order; a tier emptied by exclusion is skipped; if the
frontier tier empties and no pin replaces it, the ladder tops out at a lower tier —
report that honestly, never invent a rung.

## Same-named agent

For persona-isolated runs — a separate dispatch that should carry its own model pin
instead of this session's model — use the `escalate` custom agent: pick it in the
`/agent` picker, or run `copilot --agent escalate -p "<task>"`. This skill and that agent
are the same capability on two surfaces; the agent's frontmatter carries the model pin,
this skill runs on whatever model the session already uses.

## Installed?

If the literal `{{POLYTROPOS_ROOT}}` text is still visible above, the bundle is not
installed — tell the user to run `python3 bin/harness_select.py install --harness copilot`
(then `/skills reload` picks the skills up in-session).
