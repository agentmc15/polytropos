# journal — external tools (Teams / Outlook / Copilot Studio)

Read this when the user wants Teams / Outlook / Copilot Studio context folded into the journal.
Moved here verbatim from `SKILL.md` — `$ROOT` is this plugin's root, resolved the same way as in
`SKILL.md` (`${CLAUDE_PLUGIN_ROOT}` if set, else `../..` relative to that file, resolved to an
absolute path). The no-network/no-OAuth/no-Graph/no-MCP declaration this feature is built on
stays in `SKILL.md` itself, even though the command below moved here.

The journal has no Graph/OAuth/MCP connectors and never will by default — instead it generates
an offline **ask-the-tools** pack you run yourself, in your own Microsoft tools, two passes:

```bash
python3 "$ROOT/bin/journal_askpack.py" --date <date> --print
```

This writes `journal/<date>/ask-the-tools.md` with one ready-to-paste prompt per tool
(Copilot Studio, Teams, Outlook) and also prints them to stdout. Run each printed prompt
inside that tool's own AI, then paste the bullet results it gives you back into
`journal/inbox.md`. Re-run the collector and redo the summaries so the enriched inbox flows
into the digest. This is offline text generation only: the journal never adds network,
OAuth, Graph, or MCP calls to fetch this content — you carry it over by hand. Each prompt
asks for at most 15 subject-level bullets per tool (titles, people, decisions, action
items — no message bodies).
