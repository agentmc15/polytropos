# per-task-dollars — kit guardrails

Relocated verbatim from the global CLAUDE.md by the context-rules kit (2026-07-24).
Kit-scoped: these fences bind this kit's tasks only. Global invariants live in CLAUDE.md.

  For `per-task-dollars` specifically: the architect/execute shared kit contract stays
  byte-intact — the ONLY skill edited is `skills/execute/SKILL.md`, BODY-only (frontmatter
  untouched; the plugin is live), `skills/architect/SKILL.md` is NEVER edited (audited
  byte-unchanged — any diff in it is a defect), every pinned contract element survives in
  BOTH skills including the Tier-2 runtime-override clause verbatim, and no new REQUIRED
  task field anywhere (the `agent:` line is a fourth OPTIONAL, execute-owned NOTES.md line —
  precedent `outcome:`/`reroute:`/`session:`; grammar `agent: <task-id> id=<agent-id>
  role=<implementer|verifier|escalation> model=<model>`; `parse_tasks` needs no change; the
  orchestrator records it at dispatch return, never any script, phase reviewers/scouts
  deliberately unrecorded); the HONESTY BOUNDARY is absolute — the orchestrator's
  main-session transcript is ONE un-attributable line NEVER split per task by any heuristic,
  a warm-cluster shared transcript (same agent id on several tasks) is attributed to the
  CLUSTER as a unit and never divided, a recorded agent id whose `*.output` is gone prices
  null + a note (never a zero or a guess), a per-task figure is only ever the sum of
  transcripts that actually exist, unattributed transcripts get one honest line (never
  silently dropped or assigned to a task), coverage is labeled full/partial/null, kits with
  no `agent:` lines degrade to n/a with the whole-kit `--session` dollars unchanged, and the
  parts-vs-whole reconciliation is a note, never an adjustment; `bin/routing_scorecard.py`
  is extended ADDITIVELY a FOURTH time — existing flags, signatures, output shapes, exit
  codes, and all THREE prior demos' numbers (`--demo`, `--demo --live`, `--demo --history`)
  stay byte-stable, `--by-task` REQUIRES `--session` and without the flag the `--session`
  output is byte-identical (no `by_task` key, `MD_H2S` and `build_scorecard` untouched), and
  `tests/test_routing_scorecard.py` + `tests/test_reroute_live.py` +
  `tests/test_routing_history.py` stay byte-untouched (new tests go in
  `tests/test_per_task_dollars.py`); `bin/cost_report.py`, `bin/session_cost.py`, and
  `bin/copilot_execute.py` stay reuse-only via importlib, never edited — every transcript is
  priced through `sc.collect`, never a re-implementation; every test/verify uses synthetic
  kits, transcripts, and `*.output` fixtures in temp dirs
  (`--kits-dir`/`--projects-dir`/`--tasks-dir` always overridden — never the real `~/.claude`
  or the real tmp tasks scratch), zero `Path.home()` in new/edited Python; no hardcoded
  prices or real model ids (tier vocabulary, the `fable`→`frontier` alias,
  `BYTASK_SCHEMA_VERSION`, `AGENT_ROLES`, the `DEMO_BYTASK_VOLUMES` token counts, the
  half-cent reconciliation epsilon, and synthetic fixtures are the sanctioned literals —
  demo/test transcript ids are computed from `data/pricing.json` at run time); sanctioned
  edit targets are ONLY `bin/routing_scorecard.py`, `skills/execute/SKILL.md`,
  `docs/ROUTING-HISTORY.md`'s pinned pointer paragraph, and CLAUDE.md's pinned T6 run-line,
  with new files `tests/test_per_task_dollars.py` and `docs/PER-TASK-DOLLARS.md`; no README
  changes, no new skills, no Copilot-side changes, no changes to
  `/route`/`/escalate`/`/fable-check`, no estimated splitting under any label, no per-task
  dollars in `--history`, no auto-pin/auto-downgrade, no cross-kit or time-series per-task
  aggregation, no main-session model switching.
