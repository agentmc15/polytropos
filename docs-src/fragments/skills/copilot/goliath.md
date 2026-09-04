### What it does

A plain kit run gives you an implementer, a verifier, and a reviewer; this policy adds two
more checks on top — a dedicated test-author and a mandatory red-team pass — turning one
Copilot session into a fuller five-role pipeline, with the architect always planning first
and a named fallback model for every role if its first choice isn't available. It's a
policy the session follows, not a separate driver: nothing here dispatches on its own.

### When to reach for it

- A single Copilot session should run a fuller review pipeline than one implementer plus
  one reviewer.
- You want role-by-role model resolution with an explicit fallback instead of a silent
  substitution.
- Comparable multi-role rigor to `claude/architect` + `claude/execute`, but as a policy the
  session follows rather than a driver that dispatches.
- **Not** a fan-out mechanism — roles still run one at a time, the same serial constraint
  every Copilot skill in this roster shares.

### Worked example

```bash
python3 bin/copilot_pricing.py models --json
```

Inspect the active roster before an expensive run and confirm each role's chosen id is
still exposed by the live `/model` picker. Every role has a primary pick plus one or two
named fallbacks (see the card below for today's roster) — resolve them from the pricing
data at run time, never invent or hardcode an id. If every candidate for a role is
unavailable, stop and report the missing role; never substitute another role's model.

### Failure modes & fallbacks

- **A role's whole fallback chain is unavailable.** Stop and name the missing role — do
  not quietly hand its work to a different role's model.
- **The red-team role is skipped or softened.** It's mandatory, and a confirmed break
  means the work isn't accepted yet, no matter what the other four roles reported.
- **A role tries to replace the architect as planner.** Only the architect plans; the
  orchestrator/reviewer coordinates the rest but never re-plans.

### Cost & safety

The red-team role must not rewrite tracked files while it reviews, and work is accepted
only once all five execution roles report success against the architect's plan. Never
invoke the real Copilot CLI from a test or verify command — use `--dry-run`, injected
runners, or synthetic fixtures instead.

### Related

- [architect](architect.md) — the single-role planning skill; goliath's own architect
  role shares the same instinct but is a separate mechanism, with its own fallback table.
- [execute](execute.md) — the plain three-role driver (implementer, verifier, reviewer);
  goliath's five roles are an independent policy, not an extension of this driver.
- [Parity matrix](../index.md) — why this page has no sibling on either other harness.
