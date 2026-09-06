---
name: frontier-check
description: Decide whether a task needs Astra orchestration or a policy-selected worker.
metadata:
  short-description: Check whether reserved orchestration is justified
---

# Reserved orchestration check

## Resolve the plugin root before running commands

Resolve `POLYTROPOS_ROOT` from this skill's location. In a managed copy use `POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`. Reject a literal placeholder. Confirm pricing data, `bin/codex_pricing.py`, `bin/codex_policy.py`, and `bin/codex_execute.py` exist. If not, stop and use `python3 bin/harness_select.py doctor --harness codex`.

Use central policy, not a model picker, to distinguish worker work from orchestration. Get current availability, effort support, request-size rules, and estimates from the data-backed engine:

```bash
python3 "$POLYTROPOS_ROOT/bin/codex_pricing.py" models --profile <PROFILE>
python3 "$POLYTROPOS_ROOT/bin/codex_pricing.py" est <PROFILE> <worker-tier>
python3 "$POLYTROPOS_ROOT/bin/codex_execute.py" prepare --role implementer --model <worker-tier>
```

Choose a worker for implementation: cheap for mechanical work, mid for routine work, and strong for hard, security, integration, and independent-verification work. Under subscription billing lead with burn index and label dollars as API-equivalent proxies; API-key estimates are token-metered. State a per-request context assumption; aggregate session totals are not a context threshold.

Astra is justified to create a durable multi-task plan, coordinate dependencies, perform final acceptance, or correct a failure that the driver actually recorded. It is not a normal worker, a planned pin is not actual-use evidence, and there is no warm pool. Recovery requires the driver's structured evidence, so `prepare --role recovery` is intentionally rejected.
