### What it does

Runs a task through the central worker ladder behind a machine-checkable result. Luna, Terra, and Sol remain the implementation tiers; Astra is a reserved recovery target and becomes eligible only after qualifying failure evidence recorded by the execution driver.

### When to reach for it

- Use it when a task has a runnable verification command and a cheaper worker may succeed.
- Use it when failure should trigger a bounded, auditable correction path.
- **Not** for a subjective preference such as “use the best model” or for routine verification.

### Worked example

```bash
python3 bin/codex_execute.py run --kit tasks/kits/<slug> --task <id> --dry-run
python3 bin/codex_execute.py run --kit tasks/kits/<slug> --task <id>
```

The driver records each requested, dispatched, and observed identity separately, runs verification, and advances only through eligible worker tiers.

### Failure modes & fallbacks

A nonzero dispatch is a dispatch failure, not a verification result. Astra recovery requires a recorded nonzero verification, an unresolved named integration conflict, or a failed lower-tier correction with prior attempts. The recovery record includes evidence, attempts, correction scope, and verification outcome. Later tasks return to the cheapest sufficient worker.

### Cost & safety

Dry-run is read-only; execution consumes usage. The CLI has no warm-agent pool, so Astra is represented as reserved and instantiated only when the gate opens. A missing or unavailable Astra fails closed rather than routing ordinary work to it or weakening verification.

### Related

- [execute](execute.md) owns the supported recovery and audit path.
- [effort](effort.md) changes validated reasoning effort.
- [frontier check](frontier-check.md) explains the reserved tier.
