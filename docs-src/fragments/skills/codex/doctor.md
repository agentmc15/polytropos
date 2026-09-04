### What it does

Polytropos does not land in Codex as one thing: the plugin, the optional agents, and older
copied surfaces are separate pieces, each independently absent, current, superseded, or
edited by you. This prints one line per piece — which it is, where it lives, why — and
changes nothing.

### When to reach for it

- `/skills` does not list what you expect, or an explicit `$name` does not resolve.
- After pulling changes, moving the checkout, or a half-landed upgrade.
- Before any install or refresh, to see what a write would touch.
- **Not** a fixer — it never repairs, which is why it is safe to run first — and **not**
  for the other harnesses: `--harness codex` is the one value it accepts, and
  [update](../claude/update.md) covers all three harnesses.

### Worked example

```bash
python3 "$POLYTROPOS_ROOT/bin/harness_select.py" doctor --harness codex --repo-root "$POLYTROPOS_ROOT" --codex-home <codex-home>
```

Each line reads `<component>: <state> — <destination> (<reason>)`, then the ownership
status and a restart reminder. `--json` prints the same plan as JSON.

| State | What it means, and what you do |
|---|---|
| `install` | Destination absent; an install would create it. |
| `up-to-date` | Matches the current bundle. |
| `managed-update` | An unchanged recorded copy, refreshable — authorize it; it writes. |
| `unmanaged` | Stale, legacy, or outside the bundle. Preview, then re-run with `--refresh-managed`. |
| `conflict` | Preserved, not overwritten — your edit, an unrelated file, or an unresolved placeholder. Merge or rename, re-run. |
| `skip` | No action planned. |

Doctor never passes `--refresh-managed`, so a refreshable copy reads `unmanaged` here and
`managed-update` in a `--refresh-managed --dry-run` install preview.

### Failure modes & fallbacks

- **The root cannot be proven** — a missing engine or pricing file, or a literal
  placeholder still in the file. The skill stops rather than run a guessed path.
- **A conflict never clears itself.** The installer does not overwrite; resolve it, re-run
  doctor, start a new task.
- **Three things it never suggests**: `--force` (there is none), deleting the Codex home,
  overwriting `config.toml`.
- **Clean report, but nothing changed** — restart Codex or start a new task.

### Cost & safety

Doctor and `install … --dry-run` are byte-read-only: they hash, compare, print. No model
is dispatched, nothing written, nothing spent. An actual `install` or
`--refresh-managed` **is** a write — the skill shows the plan and gets explicit authority
first. Managed refresh touches only copies still byte-identical to what was
recorded; your edits stay preserved conflicts.

### Related

- [Deep dive: Codex harness](../../deep-dives/codex-harness.md) — what installs where.
- [update](../claude/update.md) — one freshness card across all three harnesses.
- [Parity matrix](../index.md) — why it is Codex-only.
