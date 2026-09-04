### Installing

polytropos ships to Claude Code as a plugin, served from the local marketplace this
repository provides. From a checkout:

```
/plugin marketplace add /path/to/polytropos
/plugin install polytropos@polytropos-local
```

The non-interactive equivalents are `claude plugin marketplace add /path/to/polytropos`
and `claude plugin install polytropos@polytropos-local`. For a throwaway session — testing
a change without a persistent install — start Claude Code with
`claude --plugin-dir /path/to/polytropos` instead.

### Invoking a skill

Every skill above is a slash command namespaced to the plugin: `/polytropos:<name>`, with
the skill's arguments following it directly, as in
`/polytropos:route add input validation to the signup handler`. Several skills also accept
leading flags — `route`, for instance, takes `--api` / `--sub` to force a billing framing
before the task description.

### What a skill can and cannot do

A skill is instructions loaded into the session you are already in. It runs on whatever
model that session has selected, and **nothing in Claude Code can switch the main session's
model programmatically — only you can, through `/model`.** That is why the routing skills
end with either an offer to dispatch (the Agent tool takes a per-dispatch `model`, so
delegated work can run on a cheaper model than you are on) or an exact `/model` line for
you to paste. Treat the recommendation as advisory for your own session and operational for
anything it can delegate.

Most of these skills are a thin, safety-checked layer over an engine under `bin/` that you
can also run yourself from a shell — the skill exists to choose the right invocation, read
the output honestly, and stop before anything that spends money or writes files without
your say-so.

### Where to go next

- [route](route.md) is the front door: one task in, a model and a cost estimate out.
- [Parity matrix](../index.md) — the same skills across all three harnesses, and why the
  rosters differ.
- [Deep dive: how it works](../../deep-dives/how-it-works.md) — the architecture behind the
  roster.
- [Deep dive: guide & cookbook](../../deep-dives/guide.md) — every skill in narrative form,
  with worked examples.
