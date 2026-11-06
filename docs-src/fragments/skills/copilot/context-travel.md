### What it does

A Copilot session that takes over one kit task normally spends its first turns re-reading
`PLAN.md`, `TASKS.md` and the notes to find out where that task stands. This skill gets
the same picture as one bounded record: the task's recorded status, its acceptance text,
what each selected source showed, and what could not be established. It reads through a
config the operator wrote and changes nothing — the kit, the routing and the verify
commands stay exactly as they were.

### When to reach for it

- One task from a kit is yours and you want its criteria and state without preloading
  the kit, a graph, or a transcript.
- A view was handed over from another surface and you want it explained, or two views
  compared.
- **Not** without an operator-supplied absolute `--config` and an explicit repository,
  kit, checkout, task, assignment, role and question.
- **Not** when the installed bundle still shows a literal, unresolved root placeholder;
  the skill rejects that rather than guessing a path.
- **Not** a grant of authority: a briefing neither assigns the task nor proves it is
  current.

### Worked example

With the bundle installed, so its root is already an absolute path:

```bash
python3 {{POLYTROPOS_ROOT}}/bin/context_travel_cli.py \
  --config /ABSOLUTE/CONFIG.json --format json brief < assignment.json > query.json
```

`assignment.json` holds one `assignment` object naming `repository_id`, `checkout_id`,
`revision`, `kit_path`, `task_id`, `assignment_id`, `assignment_role` and `question`.
One line comes back: an envelope with `v`, `operation` and `data`. `data` is the view to
keep and to pass to `explain` or `changes` later; `overview` and `capabilities` are the
other operations.

### Failure modes & fallbacks

| What you see | What to do |
|---|---|
| `context travel query failed`, exit status 2 | Say the query failed; it is never an empty success |
| A source state such as `missing`, `forbidden`, `over-limit` or `unavailable` | Keep the caveat attached to whatever you report |
| This mode cannot run a local command | Use a supplied handoff only if it validates against the configured subject; otherwise it is advisory |
| No authorized config | Report context unavailable and continue the ordinary kit workflow, verification included |

### Cost & safety

Read-only: it opens only the files the config selects, dispatches no model and spends
nothing. The bundle carries no MCP registration, so the stdio adapter is usable only with
separate, explicit configuration and authorization. Whether the Copilot desktop app can
run the command is recorded as unknown until that client is checked — the CLI's behaviour
is not evidence for the app.

### Related

- [execute](execute.md) — the kit driver; a brief only narrows what it reads first.
- [route](route.md) — may use a brief for scope, never for the model or the estimate.
- [escalate](escalate.md) — still needs its own failure evidence; a briefing is not
  that.
- [Context travel across surfaces](../../deep-dives/context-travel-surfaces.md) — the
  per-mode transport table.
