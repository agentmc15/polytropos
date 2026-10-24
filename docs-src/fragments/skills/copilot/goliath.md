### What it does

A plain kit run gives you an implementer, a verifier, and a reviewer; this policy runs the
repo's full R10 role tier (`docs/ROLE-EXPERIMENT.md`) instead — ten execution roles plus the
architect planning first — with one pinned model per role at Max effort (never Grok, never
Gemini here) and the implementer's own model as every role's fallback.

### When to reach for it

- A single Copilot session should run the fullest review pipeline this repo defines, not
  just the base implementer/verifier/reviewer trio.
- You want role-by-role model resolution with an explicit fallback instead of a silent
  substitution — frontier for the planner and final reviewer, strong for the implementer,
  security-auditor, and red-team, cheap for the rest.
- Multi-role rigor like `claude/architect` + `claude/execute`, as a policy one session
  follows, not a driver.
- **Not** a fan-out mechanism — roles run one at a time, the same serial constraint every
  Copilot skill in this roster shares.

### Worked example

```bash
python3 bin/copilot_pricing.py models --json
```

Before an expensive run, confirm each role's chosen id is still exposed by the live `/model`
picker, resolving every id from the pricing data rather than memory. If a role's primary and
fallback are both unavailable, stop and name the missing role rather than reach outside that
role's row. Dispatch each role directly (`copilot -p ... --model ... --effort=max`);
`copilot_execute.py` does not forward reasoning-effort flags.

### Failure modes & fallbacks

- **The shared fallback is unavailable.** The implementer and security-auditor then have no
  candidate at all — stop and name them rather than improvise a substitute.
- **A checker shares the implementer's model.** The security-auditor always does, as does any
  checker that falls back; only fresh context keeps it independent.
- **The red-team role is skipped or softened.** It's mandatory; a confirmed break means
  the work isn't accepted yet, no matter what the other roles reported.
- **A role tries to replace the architect as planner.** Only the architect plans; the
  reviewer coordinates acceptance but never re-plans.

### Cost & safety

The red-team role must not rewrite tracked files while it reviews, and work is accepted
only once all ten roles report success against the architect's plan. Never invoke the real
Copilot CLI from a test or verify command — use `--dry-run`, injected runners, or synthetic
fixtures instead.

### Related

- [architect](architect.md) — the single-role planning skill; goliath's own architect
  role shares the same instinct but is a separate mechanism, with its own fallback table.
- [execute](execute.md) — the plain three-role driver (implementer, verifier, reviewer);
  goliath's ten roles are an independent policy, not an extension of this driver.
- [Parity matrix](../index.md) — why this page has no sibling on either other harness.
