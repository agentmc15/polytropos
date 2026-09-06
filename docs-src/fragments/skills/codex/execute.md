### What it does

Executes a prepared kit task by task through central policy, enforces dependencies, independently reviews each completed phase with Sol, and reserves Astra for coordination, evidence-gated recovery, and final acceptance.

### When to reach for it

- Use it after [architect](architect.md) creates a kit with runnable verification commands.
- Use it to resume work while preserving attempts, actual-use evidence, review reports, and acceptance state.
- **Not** for freehand model dispatch or bypassing an unmet task dependency.

### Worked example

```bash
python3 bin/codex_execute.py status --kit tasks/kits/<slug>
python3 bin/codex_execute.py run --kit tasks/kits/<slug> --task <id>
python3 bin/codex_execute.py review --kit tasks/kits/<slug> --phase 1
python3 bin/codex_execute.py accept --kit tasks/kits/<slug> --phase 1
```

Worker completion and final acceptance are distinct states. A phase remains acceptance-pending until a fresh independent review succeeds and Astra records an explicit decision.

### Failure modes & fallbacks

Missing verification fails before dispatch. Failed dispatch never becomes success merely because a check passes. A stale review is invalidated by changes to the phase, plan, task attempts, Git head, or workspace. Runtime model mismatch is a policy violation and cannot unlock recovery.

### Cost & safety

Preview and status are read-only. Review and acceptance use read-only sandboxes; implementation uses the normal workspace sandbox. Records keep planned pins, dispatched roles, and runtime-attested actual use separate. Unknown remains honest when the runtime supplies no trustworthy attestation.

### Related

- [architect](architect.md) creates the kit contract.
- [escalate](escalate.md) describes the bounded worker and recovery ladder.
- [doctor](doctor.md) diagnoses installation and policy state.
