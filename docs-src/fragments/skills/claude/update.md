### What it does

You've pulled changes or merged a PR, and now you don't know whether what's actually
installed — the Claude plugin cache, the Copilot and Codex bundles, the pricing mirrors,
the docs snapshot — still matches what's in the repo right now. One command answers that
across all four at once, and only ever by reading; `apply` is a separate, later step that's
the one that actually writes anything.

### When to reach for it

- After pulling or merging changes into this repo.
- Before trusting a Copilot or Codex install to reflect what's actually in the plugin.
- The user asks whether an install or the pricing docs are stale.
- **Not** a fix for a stale Claude plugin cache — `~/.claude` is never written by this
  skill; it only ever prints the remedy for you to run yourself.

### Worked example

```bash
python3 bin/harness_update.py check
python3 bin/harness_update.py apply --dry-run
```

`check` always runs first, no matter why the skill was invoked — its card names which of
four sections (claude / copilot / codex / data) drifted, and exit code 3 means drift
somewhere. Only run `apply` for real once the user has explicitly asked for a refresh in
this conversation; when it's unclear, show the `--dry-run` plan instead of guessing either
way.

| Home | What `apply` does |
|---|---|
| Copilot | overwritten in place — not a no-clobber channel |
| Codex prompts | plugin-generated mirrors, overwritten unconditionally |
| Codex `AGENTS.md` / skill dirs | no-clobber — a differing copy is preserved and reported |
| `~/.claude` | never written, in any mode |

### Failure modes & fallbacks

- **"not installed"** is an absence, not a failure — report it as such, not as something
  broken.
- **`unmanaged` on codex** is a warning worth mentioning, not an alarm; a codex `conflict`
  is real drift worth naming plainly.
- **`status: error` / exit 1.** A writer raised; the card carries the error verbatim —
  report it and stop, never retry blind.

### Cost & safety

Both the JSON envelopes and the human `apply` card embed absolute home paths — scrub them
before pasting either one anywhere outward. Pricing numbers and docs snapshot tables are
never auto-edited by this engine; a stale figure is a human refresh from the source data,
both changed together in one edit.

### Related

- [Deep dive: how it works](../../deep-dives/how-it-works.md) — what each harness install
  actually contains.
- [doctor](../codex/doctor.md) — the Codex-only per-component detail this card's codex
  section summarizes.
- [Parity matrix](../index.md) — why this one check covers all three harnesses at once.
