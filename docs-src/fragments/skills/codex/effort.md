### What it does

Chooses a supported reasoning-effort level from current Codex pricing and capability data. Effort changes how a selected model works; it does not replace the central worker assignment or turn Astra into an ordinary implementer.

### When to reach for it

- Use it when a task has concrete evidence that the current reasoning level is insufficient.
- Use it to inspect which levels the policy-selected model actually supports.
- **Not** for expressing a vague request to use the best model or bypassing recovery gates.

### Worked example

```bash
python3 bin/codex_pricing.py knobs
python3 bin/codex_execute.py run --kit tasks/kits/<slug> --task <id> --effort <level>
```

The driver validates the level for every possible worker rung before dispatch, so escalation cannot fail halfway through because a later model rejects the chosen effort.

### Failure modes & fallbacks

If a level is unavailable, omit the override or choose a supported level reported by current data. Increase one rung only after useful failure evidence. Never smuggle model or profile changes through extra command arguments; the driver rejects configuration overrides that could weaken policy.

### Cost & safety

Listing knobs is read-only. A kit run may consume subscription usage or API tokens, so preview its assignment first and keep dollar figures labeled as API-equivalent proxies unless the run is API-metered. Availability and levels are resolved at runtime rather than copied into prose.

### Related

- [route](route.md) selects and estimates the worker.
- [execute](execute.md) validates and records the dispatched effort.
- [escalate](escalate.md) handles evidence-based worker escalation.
