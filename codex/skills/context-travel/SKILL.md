---
name: context-travel
description: Use when a kit task needs a bounded, read-only lifecycle briefing, source explanation, or comparison of supplied validated views.
metadata:
  short-description: Read bounded kit context across surfaces
---

# Context travel

Resolve `POLYTROPOS_ROOT` from this skill's location. In a managed copy use
`POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`; reject a literal placeholder. Confirm
`bin/context_travel_cli.py`, `docs/CONTEXT-TRAVEL-SURFACES.md`, and
`primitives/context-travel-surfaces.json` exist. If the root is incomplete, use
`python3 bin/harness_select.py doctor --harness codex`. Read the shared guide
on demand for exact CT4 query arguments, the Codex desktop and CLI decisions,
and fallback behavior. Do not preload graph or transcript content.

Use only an operator-supplied absolute `--config` and explicit repository, kit,
checkout, task, assignment, role, and question. Run the existing local CLI only
when that mode actually exposes execution. MCP stdio requires separate explicit
configuration and authorization; this skills-only plugin does not register it.
For an imported view, require validation against the configured subject. Treat
unvalidated handoff data as advisory.

Retain missing, partial, stale, forbidden, refused, and critical caveats. A
briefing does not grant task authority or verify freshness. Continue the native
kit, routing, pricing, permission, and mandatory verification rules if this
optional context is unavailable.
