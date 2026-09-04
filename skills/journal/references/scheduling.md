# journal — inbox & schedule: running unattended

Read this when the user wants the journal to run unattended. Moved here verbatim from
`SKILL.md` — `$ROOT` is this plugin's root, resolved the same way as in `SKILL.md`
(`${CLAUDE_PLUGIN_ROOT}` if set, else `../..` relative to that file, resolved to an absolute
path).

To run the collector and summarizer automatically every night, install the schedule:

```bash
python3 "$ROOT/bin/journal_schedule.py" install
```

This writes a launchd plist (default 22:00) and prints the `launchctl bootstrap` command needed
to activate it — the installer never runs `launchctl` itself, so loading the schedule is the
user's own later, manual step. Use `uninstall` to remove the plist, `status` to check whether
it is loaded, and `run` (with `--collect-only` or `--dry-run`) for a manual one-shot in between
scheduled runs.
