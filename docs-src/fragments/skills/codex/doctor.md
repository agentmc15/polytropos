### What it does

Inspects the Codex plugin, native skills, managed agent roles, central policy, and application configuration without changing them. It distinguishes files owned by application policy from unmanaged conflicts and reports missing or stale installation surfaces.

### When to reach for it

- Use it when a native `$skill` is absent, stale, or points at an old plugin cache.
- Use it before applying policy after moving or updating the repository.
- **Not** for repairing files automatically; diagnosis is deliberately read-only.

### Worked example

```bash
python3 bin/harness_select.py doctor --harness codex
python3 bin/codex_app_policy.py status --repo-root . --codex-home <codex-home>
```

The first command checks package and skill discovery. The second explains the managed Astra orchestration and Luna, Terra, and Sol worker configuration.

### Failure modes & fallbacks

If a plugin root cannot be proven, run doctor from a known repository checkout rather than guessing a cache path. If managed roles conflict with user-owned files, inspect the ownership report before applying. Missing Astra fails clearly and never weakens worker-routing restrictions.

### Cost & safety

Doctor and status are local, read-only checks. They do not invoke a model, consume an implementation assignment, rewrite application configuration, or install the plugin. Review a generated plan before running the separate `apply` operation.

### Related

- [route](route.md) previews the assignment after configuration is healthy.
- [execute](execute.md) enforces the same policy at dispatch.
- [effort](effort.md) validates model-specific reasoning levels.
