### What it does

Drives a prepared kit through to done, task by task — with the same real limit as the
other non-Claude harness: no parallel fan-out, no warm agent clusters. The driver's own
tier-climbing ladder is the whole escalation mechanism; there's no separate
session-side valve.

### When to reach for it

- The user says execute, continue, or resume a kit `$architect` already wrote.
- You want to inspect a kit's state or preview a dispatch before spending anything.
- Reviewing a completed phase against `PLAN.md` for drift.
- **Not** for parallel dispatch — kit tasks run one `run` invocation at a time,
  regardless of `independent:` markings.

### Worked example

```bash
python3 bin/codex_execute.py status --kit tasks/kits/<slug>
python3 bin/codex_execute.py run --kit tasks/kits/<slug> --dry-run
python3 bin/codex_execute.py run --kit tasks/kits/<slug> --task <id>
```

`status` and `--dry-run` inspect without dispatching — the dry run prints the next
dispatch and verify plan and never launches Codex. A real `run` (or a non-dry
`review`) launches headless Codex and spends subscription usage or API-metered funds;
get the user's authority first, and never represent a dry run as a real dispatch.

### Failure modes & fallbacks

- **A task reports done.** Rerun its verify command independently before accepting
  completion — a driver's own claim of success is never evidence.
- **Interactive delegation is wanted.** The canonical `kit-implementer`,
  `kit-verifier`, and `phase-reviewer` agents are preferred when available, but
  plugin install does NOT install them — the headless driver is the functional
  fallback either way.
- **A completed phase drifted from the plan.** Review it against `PLAN.md` before
  continuing; don't assume a passing verify command means the plan was honored.

### Cost & safety

`status` and `--dry-run` are read-only previews that spend nothing. A real `run` or
non-dry `review` launches headless Codex against whatever model the task's `model`
field resolves to — a genuine dispatch against usage limits or API-metered dollars,
never a preview.

### Related

- [architect](architect.md) — writes the kit this skill runs.
- [escalate](escalate.md) — the same tier-climbing ladder, for a single task outside
  any kit.
- [doctor](doctor.md) — the root-resolution check this skill depends on before
  shelling out.
