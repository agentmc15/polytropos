### What it does

Turns a complex change into a durable execution kit while Astra owns planning, decomposition, dependencies, routing decisions, coordination, and final acceptance. Kit tasks express worker intent as `cheap`, `mid`, or `strong`; central policy resolves an available Luna, Terra, or Sol model when execution begins.

### When to reach for it

- Use it when several tasks need explicit ordering, integration decisions, or independent verification.
- Use it when another agent should be able to resume from files instead of conversational history.
- **Not** for a small edit whose scope, check, and owner are already obvious.

### Worked example

```bash
python3 bin/codex_execute.py status --kit tasks/kits/<slug> --json
python3 bin/codex_execute.py run --kit tasks/kits/<slug> --task <id> --dry-run
```

The plan keeps Astra in the orchestration role and gives normal implementation to the cheapest sufficient worker.

### Failure modes & fallbacks

If pricing, policy, or driver files cannot be proven, stop and use [doctor](doctor.md). Legacy unpinned tasks safely resolve to the default worker; a legacy frontier pin migrates at dispatch to the strongest worker. Neither case rewrites kit history. Recovery remains unavailable until the driver records qualifying failure evidence.

### Cost & safety

Creating the plan does not invoke `codex exec`. Real worker spend occurs later when `codex_execute.py` resolves a task and dispatches `codex exec` with the policy-selected model. Treat planned, dispatched, and observed identities as separate facts; an unattested runtime identity remains unknown.

### Related

- [execute](execute.md) runs and records the kit.
- [route](route.md) previews worker assignment and estimates its burn.
- [doctor](doctor.md) checks the installation without changing it.
