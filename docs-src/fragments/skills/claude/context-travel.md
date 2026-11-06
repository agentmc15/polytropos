### What it does

Picking up one kit task cold — as a second agent, a reviewer, or yourself in another
window — usually means re-reading the plan, the task list and the notes just to learn
where that task stands. This skill asks for a briefing instead. Through a config the
operator wrote, it reads only the files that config selects and returns one bounded
record: the task's recorded status, its acceptance text, what each source did and did not
show, and the limits of that picture. It never edits the kit and never decides anything.

### When to reach for it

- You are handed one task and want its criteria and recorded state without loading the
  whole kit, a graph, or a transcript into the window.
- A briefing arrived from another surface and you want it explained, or two of them
  compared to see what changed.
- **Not** without an operator-supplied absolute `--config` and an explicit repository,
  kit, checkout, assignment, role and question. Nothing is guessed from the current
  directory, a home directory or Git.
- **Not** a substitute for the kit: the briefing is advisory, and the task's own files and
  its verify command still decide.

### Worked example

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/context_travel_cli.py" \
  --config /ABSOLUTE/CONFIG.json --format json brief < assignment.json > query.json
```

`assignment.json` is one JSON object whose `assignment` names `repository_id`,
`checkout_id`, `revision`, `kit_path`, `task_id`, `assignment_id`, `assignment_role` and
`question`. The result is a single line: an envelope with `v`, `operation` and `data`.
Keep `data` — it is the projection you pass back as `view` to `explain`, or as `before`
and `after` to `changes`. The remaining operations are `overview` and `capabilities`.

### Failure modes & fallbacks

| What you see | What it means |
|---|---|
| `context travel query failed` on stderr, exit status 2 | Refused or malformed; never an empty success |
| A source state of `missing`, `forbidden`, `corrupt`, `inconsistent`, `over-limit` or `unavailable` | That file was not read cleanly, so coverage is incomplete |
| A refusal with no brief | The whole projection did not fit the output bound; nothing is cut to fit |

Report each as it is. In Claude Desktop chat a briefing arrives as a bounded handoff;
without a trusted executor to validate it, mark it unvalidated and advisory. With no
authorized config, say context travel is unavailable and carry on with the ordinary
workflow, verification included.

### Cost & safety

Read-only and offline: it opens only the files the config selects, dispatches no model,
and writes nothing itself — its one result goes to stdout. The plugin registers no MCP
server; the stdio adapter needs its own explicit configuration and authorization. A
matching digest shows the bytes did not change, not that they are current, authentic or
accepted. Installed-client support stays recorded as unknown until a specific client is
checked.

### Related

- [execute](execute.md) — uses a brief to focus its reads, then the task's own files and
  verify command.
- [architect](architect.md) — records only supplied references in the kit it writes.
- [Context travel contract](../../deep-dives/context-travel.md) — the record formats and
  their bounds.
- [Context travel across surfaces](../../deep-dives/context-travel-surfaces.md) — which
  transport each client mode may use.
