### What it does

Explains whether work belongs to ordinary Luna, Terra, or Sol implementation, Astra orchestration, or the narrow Astra recovery path. It preserves Astra for planning, coordination, integration decisions, final acceptance, and corrections backed by machine-visible failure evidence.

### When to reach for it

- Use it when deciding whether a hard task needs Sol or only Astra's coordination.
- Use it when reviewing whether recorded evidence actually opens the recovery gate.
- **Not** for promoting an ordinary task because someone asked for the most capable model.

### Worked example

```bash
python3 bin/codex_execute.py prepare --role implementer --model strong --json
python3 bin/codex_execute.py status --kit tasks/kits/<slug> --json
```

The preview should resolve an ordinary hard implementation to the strongest eligible worker. Status shows Astra as reserved until the driver records accepted recovery evidence.

### Failure modes & fallbacks

Planned or dispatched identity does not prove actual runtime use. If attestation is missing, preserve `unknown`; if it contradicts policy, block the result. Missing Astra also fails closed. Legacy frontier task pins migrate to the strongest worker without rewriting the original kit.

### Cost & safety

These previews do not dispatch. Use runtime pricing data for burn and API-equivalent estimates, and keep request-size assumptions explicit for long-context rates. Astra recovery is not a general escalation rung and cannot be unlocked by preferences or routine review failure.

### Related

- [route](route.md) previews ordinary worker routing.
- [escalate](escalate.md) defines qualifying recovery evidence.
- [execute](execute.md) records and verifies the actual attempt.
