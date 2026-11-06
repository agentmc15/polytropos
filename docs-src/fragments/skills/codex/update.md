### What it does

After a pull or a merge, tells you whether what is installed still matches the repository:
harness installs, bundle files, and generated mirrors, on one card. Checking only reads.
Refreshing is a separate step that runs only when you ask for it in the current
conversation.

### When to reach for it

- Use it after pulling or merging changes into a Polytropos checkout.
- Use it when a skill or prompt behaves like an older version of itself.
- **Not** as permission to write: a freshness question is not authorization, and when the
  intent is unclear the skill shows the dry run instead.

### Worked example

```bash
python3 "$POLYTROPOS_ROOT/bin/harness_update.py" check --repo-root "$POLYTROPOS_ROOT"
python3 "$POLYTROPOS_ROOT/bin/harness_update.py" apply --repo-root "$POLYTROPOS_ROOT" --dry-run
```

The first line always runs first. Exit 3 means drift was found, not that the checker
crashed. Read the card's vocabulary literally:

| On the card | Read it as |
|---|---|
| “not installed” | absence, not a failure |
| `unmanaged` | a warning |
| `conflict`, `managed-update` | actionable Codex drift |
| `not applicable here (install source)` | not drift: project agents belong in the checkout where Codex works |

### Failure modes & fallbacks

- **`apply` reports `error`.** Stop and report it; a writer is never retried blindly.
- **A differing `AGENTS.md` or skill directory.** Those destinations are no-clobber: the
  copy is reported as `skip-differs` and preserved, and it needs your own decision.
- **Project agents or the modern plugin look stale.** They are outside this updater's
  apply scope; use the repository's Codex installer workflow when you want those surfaces
  refreshed.
- **A stale Claude plugin cache.** The updater never writes `~/.claude`. It may print a
  remedy, which runs only after separate explicit approval.

### Cost & safety

`check` and `--dry-run` write nothing and dispatch no model. A real `apply` may overwrite
Copilot bundle-owned files and Codex generated compatibility prompts, listing the ones that
differed; unknown files stay untouched. Pricing values and documentation snapshot tables are
never refreshed by this engine. The JSON modes and the human apply card can contain absolute
home paths, so scrub local paths before sharing output.

### Related

- [doctor](doctor.md) gives the per-component detail behind the Codex section of the card.
- [setup](setup.md) configures the native status line, which this updater does not touch.
- [Deep dive: Codex harness](../../deep-dives/codex-harness.md) covers what loads where and
  the ownership rules that keep your edits.
