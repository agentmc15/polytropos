---
name: route
description: Estimate a Codex task and preview its central policy worker assignment.
metadata:
  short-description: Estimate and preview a policy-routed worker
---

# Route Codex work

## Resolve the plugin root before running commands

Resolve `POLYTROPOS_ROOT` from this skill's location. In a managed copy use `POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`. Reject a literal placeholder. Confirm pricing data, `bin/codex_pricing.py`, `bin/codex_policy.py`, and `bin/codex_execute.py` exist. If not, stop and use `python3 bin/harness_select.py doctor --harness codex`.

Use the pricing engine for every estimate; it is the only source for availability, identities, effort levels, request-size rules, and prices. Under a ChatGPT plan, lead with burn index and call every dollar figure an API-equivalent proxy. With API-key billing, the engine's estimate is token-metered. State the per-request size assumption and keep aggregate session totals separate.

```bash
python3 "$POLYTROPOS_ROOT/bin/codex_pricing.py" models --profile <PROFILE>
python3 "$POLYTROPOS_ROOT/bin/codex_pricing.py" est <PROFILE> <worker-tier>
python3 "$POLYTROPOS_ROOT/bin/codex_execute.py" prepare --role implementer --model <worker-tier>
```

Choose `cheap` for mechanical work, `mid` for routine work, and `strong` for difficult, security, integration, or independent verification work. The policy maps each to an available worker. Astra is reserved for planning, coordination, final acceptance, and evidence-gated recovery; never recommend it as an ordinary implementation pin. `prepare` is a plan, not runtime proof: retain distinct planned, dispatched, and observed fields, with unknown observations left unknown.

For multi-task work use `$architect` and `$execute`; for a one-off, prepare through central policy rather than a custom dispatch recipe.
