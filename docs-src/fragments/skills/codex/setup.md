### What it does

Puts the facts you would otherwise keep asking for — model and reasoning level, an
estimated thread cost, context used, rate-limit windows, tokens — into Codex's own status
line. It uses the client's native status-line support; the Claude-only status-line script
in this repository is never installed or invoked here.

### When to reach for it

- Use it once per machine, when you want the Polytropos-style status line in Codex CLI.
- Use it to change which fields show or the order they appear in.
- **Not** without your confirmation: this skill touches user-level configuration, so it
  shows the intended fields first and writes nothing until you agree.

### Worked example

Inside Codex CLI, after confirming the field list the skill shows you:

```text
/statusline
```

Select the fields in the order you want and save. The picker is preferred because it
validates the identifiers your installed Codex version supports and leaves unrelated
configuration alone. The intended result in `~/.codex/config.toml` is:

```toml
[tui]
status_line = ["model-with-reasoning", "estimated-thread-cost", "context-used", "five-hour-limit", "weekly-limit", "used-tokens"]
status_line_use_colors = true
```

Start a new session if needed, then check the visible line.

### Failure modes & fallbacks

- **The picker cannot be operated.** A non-interactive edit is the fallback, only after you
  confirm the exact change. It merges or replaces just the two status-line keys, preserves
  every unrelated key and table, and writes valid TOML rather than a broad text
  replacement.
- **The client rejects an identifier.** Only that identifier is removed, after the
  validation result is shown.
- **A field stays empty.** It is reported as unavailable; rate-limit fields may be absent
  when the account or client does not expose them, and no value is invented.

### Cost & safety

No model is dispatched. The one write is to your own Codex configuration, behind explicit
confirmation, and the skill reports an existing `status_line` value without exposing
unrelated configuration. `estimated-thread-cost` is an estimate the client exposes when it
can — not proof of a bill.

### Related

- [update](update.md) checks whether the installed Polytropos surfaces have drifted.
- [usage](usage.md) is the fuller, read-only look at past Codex activity.
- [doctor](doctor.md) diagnoses the install when a native skill is absent or stale.
