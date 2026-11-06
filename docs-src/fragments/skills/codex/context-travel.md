### What it does

Taking over one kit task in Codex usually starts with re-reading the plan, the task list
and the notes to learn where that task stands. This skill returns that picture as one
bounded record instead: recorded status, acceptance text, what each selected source
showed, and what could not be established. An operator-written config decides which files
may be opened; the skill reads those and nothing else, and it leaves the kit, the worker
routing and the verification rules untouched.

### When to reach for it

- You hold one task and want its criteria and recorded state without preloading the kit,
  a graph, or a transcript.
- A view arrived from another surface and you want it explained, or two views compared.
- **Not** without an operator-supplied absolute `--config` and an explicit repository,
  kit, checkout, task, assignment, role and question.
- **Not** from a managed copy whose root is still a literal placeholder — the skill
  rejects it instead of guessing.
- **Not** as task authority: a briefing neither assigns the work nor verifies that it is
  current.

### Worked example

```bash
python3 "$POLYTROPOS_ROOT/bin/context_travel_cli.py" \
  --config /ABSOLUTE/CONFIG.json --format json brief < assignment.json > query.json
```

`assignment.json` holds one `assignment` object naming `repository_id`, `checkout_id`,
`revision`, `kit_path`, `task_id`, `assignment_id`, `assignment_role` and `question`.
One line comes back: an envelope with `v`, `operation` and `data`. Keep `data` — it is
the view `explain` and `changes` take later. `overview` and `capabilities` complete the
set.

### Failure modes & fallbacks

| What you see | What to do |
|---|---|
| `context travel query failed`, exit status 2 | Report the failure; it is never an empty success |
| The root is incomplete | Run `python3 bin/harness_select.py doctor --harness codex` |
| A source state such as `missing`, `forbidden` or `over-limit` | Keep the caveat with the result |
| No authorized config, or no local execution in this mode | Say context is unavailable and continue the native kit workflow |

An imported view must validate against the configured subject; one that cannot be
validated is advisory data only.

### Cost & safety

Read-only: it opens only the files the config selects, dispatches no worker and spends
nothing. The plugin advertises skills, not an MCP server, so the stdio adapter
needs separate, explicit configuration and authorization. Desktop support is not inferred
from the CLI; each mode stays unknown until that client is checked.

### Related

- [execute](execute.md) — the driver that still owns dispatch, verification and
  acceptance.
- [route](route.md) — may read a brief for scope; central policy still picks the worker.
- [doctor](doctor.md) — the read-only diagnosis when the installed root looks wrong.
- [Context travel contract](../../deep-dives/context-travel.md) — record formats and
  bounds.
