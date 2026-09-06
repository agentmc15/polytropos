### What it does

Classifies work, estimates it from current Codex pricing data, and previews the central policy assignment. Ordinary implementation resolves among Luna, Terra, and Sol; Astra remains the orchestrator and reserved recovery target.

### When to reach for it

- Use it before a multi-file change, long agent loop, migration, or other expensive run.
- Use it to compare worker tiers and make a per-request long-context assumption explicit.
- **Not** for manufacturing recovery evidence or overriding the selected model in extra CLI arguments.

### Worked example

```bash
python3 bin/codex_pricing.py models
python3 bin/codex_pricing.py est <profile> <worker-tier>
python3 bin/codex_execute.py prepare --role implementer --model <worker-tier> --json
```

Choose `cheap` for mechanical work, `mid` for routine implementation and debugging, and `strong` for hard, security-sensitive, integration, or independent-verification work.

### Failure modes & fallbacks

An unpinned legacy task safely maps to the configured default worker. A legacy frontier pin maps to the strongest worker without mutating the kit. If Astra is missing, central policy fails clearly even for worker previews, preserving the orchestration invariant. Direct host actions outside the supported bridge cannot be attested by the driver.

### Cost & safety

Pricing and prepare commands are read-only. Under a subscription, lead with burn index and label dollars as API-equivalent proxies; show real dollars only for API-metered runs. Availability, effort levels, limits, and model identifiers come from the pricing source at runtime.

### Related

- [architect](architect.md) turns routing choices into a durable kit.
- [execute](execute.md) dispatches through the same policy.
- [usage](usage.md) reports historical observed activity.
