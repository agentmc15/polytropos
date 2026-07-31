---
name: bench-routing
description: Decide whether a new or higher model should replace what a role currently runs on — a benchmark-informed routing recommendation. Use when the user asks "should we upgrade X to Y for this role" or wants a benchmark-backed routing check.
---

# Bench routing

You decide whether a role should route to a new or higher model, grounded in published
benchmark evidence and checked against what this harness can actually dispatch.

## Run the engine

```bash
python3 {{POLYTROPOS_ROOT}}/bin/bench_routing.py rank --top 10             # ranked benchmark tables
python3 {{POLYTROPOS_ROOT}}/bin/bench_routing.py roles --harness copilot   # per-role picks this harness can dispatch
python3 {{POLYTROPOS_ROOT}}/bin/bench_routing.py demo                      # synthetic smoke, no real data touched
```

This is the real argparse surface — confirm against `python3 bin/bench_routing.py --help`
before assuming any other flag exists; do not invent one. The dataset behind every command is
`{{POLYTROPOS_ROOT}}/data/benchmarks.aa.json`, a screenshot-transcribed snapshot of the
Artificial Analysis Intelligence Index. It carries its own `cached_date` and provenance note —
read those off the file (or the command's own header) and flag the recommendation as
re-verify-worthy if that date looks stale. Never edit that file from this skill.

## What `roles --harness copilot` means

Availability is derived at run time from `data/pricing.copilot.json`. An entry that matches no
model this harness can actually dispatch is never silently dropped: the text card counts it out
of the `N/M benchmark entries dispatchable` total, and `--json` lists it by name under the
`unavailable` key — a bare list of display names, not a per-entry label field; the text output
only ever shows the aggregate count. Role floors (the minimum index a pick must clear) are this
repo's own editorial judgement, not published data, and are overridable with repeatable
`--floor "role=N"`.

## The `compare` honesty

This is the load-bearing section. `compare` joins the benchmark prior against this repo's
measured kit ledger — but that ledger is CLAUDE-harness evidence, and it only covers the
implementer role. From the Copilot side there is no measured per-role outcome data, so the
benchmark's recommendation stands unchallenged here: say that plainly rather than borrowing
Claude-side evidence to back a Copilot-side pick. `compare` has no `--harness` flag of its own —
never imply one exists. Anyone who wants the measured check should be pointed at the Claude
harness, where the ledger comparison actually applies.

## Presentation rules

- `usd_per_task` is a ranking ratio computed from the benchmark workload — never a bill, and
  never added to real spend figures (that's what the `usage` skill reports).
- The Intelligence Index is a general-capability composite, not a coding or agentic board.
  Say so before recommending a routing change for an agentic role — strength here does not
  imply strength at tool use.
- Speak in tier words only (e.g. "the frontier tier," "a mid tier"), never a specific model id.
  The roster behind a tier changes over time; the tier does not.

## Same-named agent

For persona-isolated runs — a separate dispatch that should carry its own model pin
instead of this session's model — use the `bench-routing` custom agent: pick it in the
`/agent` picker, or run `copilot --agent bench-routing -p "<task>"`. This skill and that
agent are the same capability on two surfaces; the agent's frontmatter carries the model
pin, this skill runs on whatever model the session already uses.

## Installed?

If the literal `{{POLYTROPOS_ROOT}}` text is still visible above, the bundle is not
installed — tell the user to run `python3 bin/harness_select.py install --harness copilot`
(then `/skills reload` picks the skills up in-session).
