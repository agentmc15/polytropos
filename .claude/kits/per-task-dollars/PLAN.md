# PLAN — per-task-dollars

autonomy: advisory

(Executes in advisory posture: re-route recommendations during this run are print-only.)

"Per-task dollar attribution" — the third item in `docs/ROUTING-HISTORY.md`'s
`## Deliberately not built`, deferred there because "transcripts price sessions, not tasks —
splitting a session's cost across the tasks it covered would be an estimate presented as a
measurement." This kit changes the DATA, not the honesty rule. `session_cost` already
partitions a session into the MAIN transcript (the orchestrator/driver) and per-subagent
`*.output` files (one per dispatched agent, filename stem = agent id). So each task's
DELEGATED cost is exactly the `*.output` transcript(s) of the subagent(s) `/execute`
dispatched for it — cleanly attributable once we know which agent served which task — while
the orchestrator's own share is the MAIN transcript, interleaved across all tasks, which is
NEVER split per task. Three scope decisions were made upstream and are binding:

1. **Scope A — the recorded datum.** `/execute` records, at dispatch return, one `agent:`
   line per per-task subagent in NOTES.md (the Agent tool reports an agent id on every
   dispatch; the subagent's transcript is `<…>/<session-id>/tasks/<agent-id>.output`).
   Grammar pinned in D2. It is a fourth OPTIONAL, execute-owned NOTES.md line (precedent:
   `outcome:` / `reroute:` / `session:`) — NOT a task field; `parse_tasks` is untouched.
2. **Scope B — attribution is FULL DELEGATION, BROKEN OUT BY ROLE.** A new `--by-task` flag
   on the plain per-kit scorecard (REQUIRES `--session`) prices each recorded agent's
   `*.output` transcript and groups per task by role — implementer (do) / verifier (check) /
   escalation (rescue) — plus a per-task total. The orchestrator's main-transcript cost is
   ONE separate, explicitly un-attributable line. Phase reviewers and scouts are per-phase /
   per-run, deliberately unrecorded, and land in an honest "unattributed" line.
3. **Scope C — the warm-cluster honesty rule.** A warm sidekick serving several tasks is ONE
   continued agent with ONE shared `*.output` transcript and the SAME agent id on multiple
   tasks' `agent:` lines. That transcript CANNOT be honestly split per task: it is attributed
   to the CLUSTER as a unit (`not split`), never divided by any heuristic.

The #1 invariant, again: **the architect/execute shared kit contract stays byte-intact.**
The execute edits are BODY-only, add no required task field, and are followed by the
dual-file contract audit. `/architect` is deliberately NOT edited (D8) — but audited anyway.

## Goal

Ship, end to end, with the full suite green, the shared kit contract provably intact, and
`bin/routing_scorecard.py` extended additively a FOURTH time:

1. **`bin/routing_scorecard.py` extended** (additive only): `BYTASK_SCHEMA_VERSION` +
   `AGENT_ROLES` + `AGENT_RE`, pure tested functions (`parse_agents`,
   `discover_agent_outputs`, `build_by_task`, `render_by_task_lines`), a `--by-task` CLI
   flag riding the existing plain `--session` path, one guarded two-line hook in
   `render_markdown`, and a `--demo --by-task` synthetic smoke (`run_by_task_demo`) whose
   fixture includes a shared warm-cluster agent AND a missing-transcript agent — the honesty
   proofs. Existing flags, function signatures, output shapes, exit codes, AND all THREE
   existing demos' numbers (`--demo`, `--demo --live`, `--demo --history`) stay byte-stable;
   `tests/test_routing_scorecard.py`, `tests/test_reroute_live.py`, and
   `tests/test_routing_history.py` are byte-untouched.
2. **`tests/test_per_task_dollars.py`** — new stdlib unittest file: grammar/tolerance
   coverage, parser-family disjointness, cluster grouping, standalone-per-file pricing
   equivalence, never-split / never-fabricate proofs, degradation ladder, CLI rejections,
   flag-off byte-stability, all three prior demos' regression checks, and a read-only proof.
3. **`skills/execute/SKILL.md` extended** (body only): a new `## Agent ledger` section
   (grammar + rules, inserted between the Outcome-ledger and Live-re-routing sections) and
   one End-of-run sentence extension offering `--by-task`. Every existing contract element
   survives verbatim.
4. **The dual-file contract audit** — `skills/architect/SKILL.md` is NOT edited (D8), but the
   CLAUDE.md invariant ("touch either skill, re-check BOTH") still applies: a dedicated audit
   task greps the full shared contract in BOTH skills and proves architect byte-unchanged.
5. **`docs/PER-TASK-DOLLARS.md`** (new) + a pinned pointer paragraph appended to
   `docs/ROUTING-HISTORY.md` (superseding its per-task-deferral bullet honestly), and one
   pinned CLAUDE.md run-line.

**Done looks like:** `python3 -m unittest discover -s tests` green (baseline 368 tests, plus
`tests/test_per_task_dollars.py`); `python3 bin/sync_pricing_refs.py --check` exits 0;
`python3 bin/routing_scorecard.py --demo --json` still yields the Tier-1 pinned numbers
(quality 6/6/3/1/1/1, mix {haiku 1, sonnet 4, fable 1}, survival 0.75);
`python3 bin/routing_scorecard.py --demo --live --json` still yields the Tier-2 pinned
numbers (one sonnet→opus recommendation for L5+L6, budget 0/2 applied, autonomy advisory);
`python3 bin/routing_scorecard.py --demo --history --json` still yields the routing-history
D9 pinned numbers (haiku (3,3,2,1,0,0), sonnet (6,5,2,1,1,1), opus (2,1,1,0,0,0), frontier
(1,0,0,0,0,0), reroutes {1,0,1}, dollars coverage "partial");
`python3 bin/routing_scorecard.py --demo --by-task --json` yields the D9 pinned by-task card;
the T4 dual-file contract audit passes (every pinned element in BOTH skills, architect
byte-unchanged, frontmatter intact); `git status` shows changes ONLY to sanctioned targets
(edits: `bin/routing_scorecard.py`, `skills/execute/SKILL.md`, `docs/ROUTING-HISTORY.md`,
`CLAUDE.md`; new: `tests/test_per_task_dollars.py`, `docs/PER-TASK-DOLLARS.md`, this kit +
its agents); and `git diff --quiet -- tests/test_routing_scorecard.py
tests/test_reroute_live.py tests/test_routing_history.py bin/cost_report.py
bin/session_cost.py bin/copilot_execute.py data skills/architect` stays clean throughout.

## Repo facts (confirmed by the architect — trust these, do not re-derive)

- **The shared kit contract** (CLAUDE.md invariant; both skills must keep expressing it):
  layout `.claude/kits/<slug>/PLAN.md` + `TASKS.md` (+ `NOTES.md`, owned by execute); task
  fields `id`, `title`, `status`, `model`, brief, acceptance, verify; status vocabulary
  exactly `pending | in-progress | done | blocked`; `## Phase N — <name>` headings;
  `depends:`/`independent:` marking; the rule that a task's `model` field overrides the
  implementer agent's frontmatter at dispatch — including the Tier-2 runtime-override clause
  ("execute may layer a logged, upgrade-only runtime override on top at dispatch (one tier
  step, never to frontier) — the field itself is never rewritten and stays the dispatch
  default"), preserved verbatim. NOTES.md already carries THREE execute-owned machine-readable
  line formats, each tolerant (optional `-`/`*` bullet, unknown keys ignored):
  `outcome: <task-id> model=<model> attempts=<n> result=<result> review=<review>` (Tier 1),
  `reroute: <from-tier> to=<to-tier> mode=<advisory|applied> tasks=<id,id,...>
  rate=<passed>/<completed>` (Tier 2), `session: <session-id>` (Tier 3). Adding a FOURTH
  format is NOT a contract change — NOTES.md is execute-owned. This kit adds NO new required
  task field; `copilot_execute.parse_tasks` needs no change.
- **This plugin is installed LIVE** from this directory — skill files are runtime behavior.
  Their YAML frontmatter must never be touched by this kit.
- **Current `skills/execute/SKILL.md` section order** (this kit inserts ONE new H2 between
  Outcome ledger and Live re-routing): `## Setup` → `## Operating rule — lean driver` →
  `## The loop` → `## Dispatch modes — fresh fan-out vs warm sidekick` →
  `## Outcome ledger — one line per finished task` → `## Live re-routing — upgrade-only,
  autonomy-gated` → `## Escalation valve — blocked tasks go back to Fable, one at a time` →
  `## End of run`. The End-of-run paragraph currently ends with the exact fragment (the T3
  anchor): `and the cross-kit track record: `python3 bin/routing_scorecard.py --history`
  (per-tier quality across every kit, plus aggregate dollars over the kits that carry a
  `session:` line).`
- **`skills/architect/SKILL.md`** already tells the architect that execute maintains NOTES.md
  ("plus one machine-readable `outcome:` line per finished task … — the architect does not
  create it") and does NOT enumerate `reroute:`/`session:` — the precedent D8 rides on.
- **`bin/routing_scorecard.py` today** (all reusable in place — extend, never fork; NEVER
  re-implement any of these): `_load(name)` importlib loader with
  `ce = _load("copilot_execute")`, `sc = _load("session_cost")`, `cr = sc.cr`;
  `TASK_MODEL_TIERS = {"fable": "frontier"}` and `tier_for(alias)`; `OUTCOME_RE`/`PAIR_RE` +
  `parse_outcomes` (tolerant, last-line-wins per task id); `REROUTE_RE` + `parse_reroutes`;
  `SESSION_RE` + `parse_sessions`; `parse_autonomy`; `effective_alias`; `live_tier_stats` /
  `upgrade_decision` / `build_live_card` / `render_live_markdown`; `history_tier_stats` /
  `tally_reroutes` / `scan_kits` / `kit_cost_summary` / `build_history` /
  `render_history_markdown`; `build_scorecard`; `session_cost_summary(session_id,
  projects_dir, tasks_dirs, includes, no_subagents, vs, pricing) -> (cost_or_None, notes)`;
  `render_markdown(card)` (H1 + the five pinned H2s `## Verdict`/`## Task outcomes`/`## Model
  mix`/`## Review survival`/`## Dollars`, then a `Notes:` block — the by-task hook lands
  between the Dollars block and the Notes block); `_rate_pct`; `_first_model_of_tier(pricing,
  tier)`; `DEMO_VOLUMES` (per-tier token volumes); `run_demo` / `run_live_demo` /
  `run_history_demo` (each builds fixtures in ONE `tempfile.TemporaryDirectory`; the live and
  history demos drive `main(argv)` against them); `_resolve_kit_dir`; `DEFAULT_KITS_DIR =
  PLUGIN_ROOT / ".claude" / "kits"`; `MD_H2S` (frozen — tests reference it; do NOT extend
  it); `main()` argparse with `kit` positional, `--kits-dir`, `--session`, `--projects-dir`
  (default `str(sc.DEFAULT_PROJECTS_DIR)`), `--tasks-dir` (append), `--include` (append),
  `--no-subagents`, `--vs`, `--json`, `--demo`, `--live`, `--history`, `--live-threshold`,
  `--live-min-sample`, `--live-max-auto`. Existing main() check order: the
  `--live`+`--session` rejection → the `--history` guardrails → the `--demo` block → the
  non-demo `--history` branch → the kit-required check → kit resolution → the `--live`
  branch → the plain path (NOTES.md read → `cr.load_pricing()` → optional
  `session_cost_summary` → `build_scorecard` → print).
- **`bin/session_cost.py` reusables:** `find_main_transcript(session_id, projects_dir)`
  (rglob `<session_id>.jsonl`, None when absent); `discover_task_dirs(session_id)`
  (best-effort tmp glob over `<base>/claude-*/*/<session-id>/tasks`; returns `[]` for
  synthetic ids); `gather_files(main_transcript, task_dirs, includes)` — first arg may be
  None, `includes` accepts explicit paths; `collect(files, pricing)` — **dedupes by message
  id GLOBALLY within one call** and returns `{"by_model": {key: {…, "cost", "msgs"}},
  "grand", "unpriced", "read_errors", "files_read", "unique_messages"}` (a per-file cost is
  `sum(b["cost"] for b in data["by_model"].values())` from a single-file collect);
  `resolve_counterfactual_model(vs, pricing)`; `build_report(...)`; `DEFAULT_PROJECTS_DIR`.
- **Transcript layout:** the main transcript of a session is
  `<projects-dir>/<project-slug>/<session-id>.jsonl`; per-subagent transcripts are
  `<base>/claude-*/<project-slug>/<session-id>/tasks/<agent-id>.output` — the filename STEM
  is the agent id. The tasks scratch dir is session-scoped tmp and may be cleaned after the
  run — a recorded `agent:` line can legitimately outlive its transcript (D6 handles it).
- **`ce.parse_tasks(text)`** returns dicts `{id, title, status, model, depends, independent,
  brief, verify}`; task headings are `### <id> — <title>` with a spaced em dash.
- **pricing.json tier vocabulary:** `frontier`, `opus`, `sonnet`, `haiku`; task `model`
  values are the Agent-tool aliases `fable | opus | sonnet | haiku`; alias→tier is identity
  except `fable → frontier`.
- **Suite:** `python3 -m unittest discover -s tests [-p '<file>.py']` — never the
  dotted-module form (broken on this machine). Baseline 368 tests, green.
  `python3 bin/sync_pricing_refs.py --check` must stay exit 0.

## Architecture & key decisions

- **D1 — Per-task dollars live in `bin/routing_scorecard.py` as a FOURTH additive mode, not
  a new script.** Same rationale that put `--live` and `--history` there: the breakdown
  consumes exactly the inputs the plain `--session` scorecard already handles (the kit's
  NOTES.md, the session's transcripts via the `session_cost` pipeline) plus one new NOTES.md
  line format; a separate script would importlib-load all of it anyway, and one script keeps
  ONE surface for the skills to shell out to (plain at end of kit, `--live` mid-run,
  `--history` across kits, `--by-task` for the per-task drill-down of one session). ADDITIVE
  means: new constants, new pure functions, one new argparse flag, one guarded two-line hook
  in `render_markdown` (D7), a flag-gated extra card key — zero changes to existing function
  signatures, outputs, exit codes, or any of the THREE prior demos' numbers, and all THREE
  existing scorecard test files stay byte-untouched (enforced by `git diff --quiet` in every
  verify; new tests live in `tests/test_per_task_dollars.py`).
- **D2 — The `agent:` grammar (pinned; the parser and the skill text must match).**
  `agent: <task-id> id=<agent-id> role=<implementer|verifier|escalation> model=<model>`
  — optional `-`/`*` bullet tolerated, mirroring the other three formats:
  `AGENT_RE = re.compile(r"^\s*(?:[-*]\s+)?agent:\s+(\S+)\s+(.+)$")`, remaining pairs via the
  existing `PAIR_RE`, roles via `AGENT_ROLES = ("implementer", "verifier", "escalation")`.
  `parse_agents(text) -> (events, notes)`: an event is kept only when `id=` is present and
  `role=` is in `AGENT_ROLES`; otherwise the whole line is skipped with an
  `unrecognized agent line` note (mirrors `parse_outcomes`). `model=` is informational —
  kept verbatim when present, `None` when absent, never validated (the alias vocabulary is
  execute-owned). Unknown `key=value` pairs are ignored (forward-compatible). Events are
  returned in FILE ORDER; a repeated (task-id, agent-id) pair REPLACES the earlier event
  (last wins, like `parse_outcomes` — re-runs append). No id-format validation — the agent
  id's shape is harness-owned. A task served by a retry-implementer, a verifier, and a Fable
  escalation legitimately carries several lines; a warm sidekick puts the SAME agent id on
  several tasks' lines (D5). **Contract safety:** the `agent:` key is disjoint from
  `outcome:`/`reroute:`/`session:` — none of the four regexes can match another's line, so
  every prior NOTES.md consumer is unaffected; nothing in TASKS.md changes shape;
  `parse_tasks` needs no modification; the line is recorded by the ORCHESTRATOR at dispatch
  return — no script ever writes it (`--by-task` is read-only like everything else here).
- **D3 — The partition: main transcript = orchestrator overhead (NEVER split); each
  `*.output` = delegated work, priced STANDALONE.** The insight the whole design rests on:
  `session_cost` already separates the main transcript from the per-agent `*.output` files.
  A task's DELEGATED cost is therefore defined as the sum of the standalone prices of its
  recorded agents' transcripts — each file priced with ONE `sc.collect([file], pricing)`
  call (per-file message-id dedupe), cost = `sum(b["cost"] for b in
  data["by_model"].values())`, a file whose `files_read` comes back 0 → cost `None` + note.
  The MAIN transcript is priced the same standalone way and reported as ONE separate line:
  `orchestrator (main session): $Y — interleaved across all tasks; never split per task`.
  No heuristic (message counts, timestamps, task markers) may ever divide it — that would be
  the estimate-presented-as-measurement the routing-history kit refused to build. Phase
  reviewers and ad-hoc scouts are dispatched per phase / per run, not per task, so `/execute`
  deliberately records NO `agent:` line for them (D8) and their transcripts land in the
  honest `unattributed subagents` line — `{count, cost_usd, agent_ids}`, one line, never
  silently dropped, never fabricated onto a task. The whole-session Dollars block (the
  existing `session_cost_summary` result, globally deduped across ALL files in one
  `collect`) remains the authoritative WHOLE and is not recomputed; because the breakdown
  prices files standalone, a message id shared across transcripts counts once in the whole
  but per-transcript in the parts — when the parts' sum differs from the whole by more than
  half a cent, `build_by_task` appends a reconciliation NOTE naming the difference and its
  two causes (shared message ids; `--include`d files outside the attribution) — a note,
  NEVER an adjustment of any figure.
- **D4 — The per-task shape: full delegation, broken out by role.** One row per task id that
  at least one kept `agent:` event names (TASKS.md order; an event naming an id that is not
  a task id is dropped at the join with an `agent line for unknown task id` note BEFORE
  grouping — its transcript, if present and referenced by no known task, lands in
  unattributed). Row shape (pinned):
  `{"id", "roles", "total_usd", "missing_agents", "shared_agent_ids"}` where `roles` maps
  ONLY the roles that have ≥1 single-task agent to `{"agents": [{"agent_id", "model",
  "cost_usd"}], "subtotal_usd"}` — `subtotal_usd` = sum over PRICED agents, `None` when the
  role has agents but none priced; `total_usd` = sum over PRICED agents across roles, `None`
  when none priced (NEVER 0 standing in for "unknown"); `missing_agents` = recorded ids with
  no transcript; `shared_agent_ids` = warm-cluster ids serving this task (their cost is in
  the cluster row, EXCLUDED from this row's roles and total — D5).
- **D5 — The warm-cluster subtlety (the honesty core).** An agent id referenced by MORE THAN
  ONE distinct known task is a shared warm agent: ONE continued agent, ONE shared `*.output`
  transcript. That transcript CANNOT be honestly split per task — attribute it to the CLUSTER
  as a unit: one row `{"agent_id", "task_ids" (TASKS.md order), "roles" (sorted unique roles
  observed), "cost_usd"}` per shared agent (rows ordered by first task position), rendered as
  ``shared warm agent `<agent-id>` across <id>, <id> (<roles>): $X (not split)`` (or
  `n/a (transcript missing)` + note). Each served task's row carries the agent id in
  `shared_agent_ids` and a `*` marker in markdown so the reader knows that task's figure
  excludes the shared transcript — an invented per-task division is a defect, not a feature.
- **D6 — Degradation ladder — never fabricate (the invariant).** Pinned rungs:
  * **No kept `agent:` events at all** (no NOTES.md, no lines, or only malformed lines) →
    the breakdown is n/a: `by_task` carries `coverage: null`, empty `tasks`/`clusters`,
    `orchestrator.cost_usd: null`, `unattributed: {count: 0, cost_usd: null, agent_ids: []}`
    (with zero events, output files are NOT enumerated — that would be a de-facto breakdown),
    and the note `no agent: lines recorded — per-task dollars n/a`; markdown renders the
    section with exactly the sentence `n/a — no agent: lines recorded in NOTES.md (the
    /execute agent ledger); the whole-kit dollars above are unaffected.` The existing
    whole-kit `--session` dollars still print unchanged.
  * **A recorded agent id with no `<agent-id>.output` file** (the tmp scratch is
    session-scoped and may be cleaned after the run) → that agent's `cost_usd: null` + a
    note naming the id — never a zero, never a guess; the task's `total_usd` is only ever
    the sum of transcripts that actually EXIST.
  * **A file that exists but cannot be read/priced** (`files_read == 0`) → same: `null` +
    note.
  * **Coverage labeled** like `--history`: `full` iff every referenced agent id priced AND
    the main transcript priced; else `partial`; `null` when there are no kept events.
  * **Missing main transcript** → `orchestrator.cost_usd: null` + note (`n/a` line in
    markdown); recorded agents still price from `--tasks-dir`/discovery — their files exist
    independently.
  * Pricing timing is UNCHANGED: `--by-task` requires `--session`, and the plain `--session`
    path already loads pricing exactly once — `--by-task` adds no new load and no load moves
    earlier. Zero-data cases render null/`n/a`, never a fabricated figure or 0%.
- **D7 — The CLI and card contracts (pinned).** Invocation: `python3
  bin/routing_scorecard.py <kit> --session ID --by-task [--kits-dir DIR] [--projects-dir DIR]
  [--tasks-dir DIR ...] [--vs MODEL_ID] [--json]`, plus `--demo --by-task [--json]`.
  New argparse flag `--by-task` (store_true; help: per-task dollar breakdown from NOTES.md
  `agent:` lines — requires `--session`). Rejections, inserted AFTER the existing
  `--history` guardrails and BEFORE the `--demo` block: `--by-task` + `--live` →
  `sys.exit("--live takes no --by-task")`; `--by-task` + `--history` →
  `sys.exit("--history takes no --by-task — per-task dollars are per-session")`;
  `--by-task` + `--no-subagents` → `sys.exit("--by-task needs subagent transcripts — drop
  --no-subagents")`; `--by-task` without `--session` (and without `--demo`) →
  `sys.exit("--by-task requires --session — per-task dollars attribute one session's
  transcripts")`. In the `--demo` block, `--demo --by-task` dispatches
  `run_by_task_demo(args.json)`. In the plain path, AFTER the existing cost computation:
  re-read NOTES.md (a second `read_text` — the existing read stays byte-identical),
  `parse_agents`, `task_dirs = args.tasks_dir or sc.discover_task_dirs(session_id)`,
  `discover_agent_outputs(task_dirs)`, `build_by_task(...)`, then `card["by_task"] = bt`
  (assigned in `main` AFTER `build_scorecard` — `build_scorecard`'s signature and output are
  untouched). `--include` remains a whole-session affordance only (it feeds the Dollars
  block as today; attribution reads task dirs only). JSON: the card gains top-level
  `by_task` ONLY when the flag is passed — key set (pinned):
  `{"schema_version" (BYTASK_SCHEMA_VERSION = 1), "coverage", "tasks", "clusters",
  "orchestrator", "unattributed", "notes"}` (by-task notes are NESTED here, never appended
  to the card's top-level `notes` — the flag-off card stays byte-identical trivially).
  Markdown: `render_markdown` gains ONE guarded block between the Dollars block and the
  Notes block — `if card.get("by_task") is not None: out.extend(render_by_task_lines(
  card["by_task"]))` — and `render_by_task_lines(bt) -> list[str]` (new pure function)
  emits: the H2 `## Per-task dollars`; the table `| Task | Implementer $ | Verifier $ |
  Escalation $ | Total $ |` (cells: `$x.xx` subtotals, `—` for an absent role, `n/a` for a
  present-but-unpriced role or total; a `*` suffix on the Task cell for rows with
  `shared_agent_ids`, footnoted `\* also served by a shared warm agent — see the cluster
  line; the shared transcript is not split into this row.`); one bullet per cluster (D5
  wording); the orchestrator bullet (D3 wording, `n/a (main transcript not found)` variant);
  the unattributed bullet `unattributed subagents (phase reviewers, scouts, unrecorded
  dispatches): <n> transcript(s), $Z` (printed only when count > 0); the coverage bullet
  `coverage: <full|partial> (<n>/<m> recorded agent transcripts priced)`; then the nested
  notes as `- <note>` lines — or, on the no-events rung, the single D6 n/a sentence. Do NOT
  touch `MD_H2S` (frozen tests reference it) — the by-task H2 is not appended to it. Exit 0
  on success including every degraded shape. Why this stays byte-stable without the flag:
  the key is assigned only under `args.by_task`, `build_scorecard` never emits it, and the
  render hook is a no-op for every card that lacks it — proven by the three frozen test
  files plus the pinned demo numbers in every verify.
- **D8 — The skill surface: TWO pinned execute edits; architect deliberately unchanged.**
  Edit 1 inserts a new `## Agent ledger — one line per per-task subagent` section
  immediately BEFORE the `## Live re-routing — upgrade-only, autonomy-gated` heading:
  grammar verbatim (matching D2 by construction), the record-at-dispatch-return rule
  (implementer, retries — each with its own line and id, verifier, escalation consult), the
  warm-sidekick same-id-per-served-task convention (what lets the scorecard attribute the
  shared transcript to the cluster as a unit), the DO-NOT-record rule for phase reviewers
  and ad-hoc scouts (per-phase/per-run — they deliberately land in the unattributed line,
  never split per task), and the OPTIONAL/execute-owned framing (precedent
  `outcome:`/`reroute:`/`session:`; never record a guessed agent id). Edit 2 extends the
  End-of-run offer sentence with the `--by-task` command. `/architect` is NOT edited:
  its NOTES.md bullet names only the `outcome:` line and was never extended for `reroute:`
  or `session:` either — NOTES.md line formats are execute-runtime mechanics, not planning
  guidance, and the agent ledger changes nothing the architect decides (no new task field,
  no pin guidance). The CLAUDE.md invariant still applies: T4 audits BOTH skills against the
  full shared contract and proves `skills/architect/SKILL.md` byte-unchanged
  (`git diff --quiet`). Skill edits are BODY-only; frontmatter never touched (the plugin is
  LIVE). If a brief's anchor text is not present verbatim, STOP and report.
- **D9 — The demo contract (pinned).** `run_by_task_demo(as_json)` builds, in ONE
  `tempfile.TemporaryDirectory`: a kit dir (`TASKS.md` = new constant `DEMO_BYTASK_TASKS_MD`
  — tasks P1 haiku done, P2 sonnet done, P3 sonnet done, P4 sonnet done, P5 sonnet done;
  spaced em-dash headings; `NOTES.md` = `DEMO_BYTASK_NOTES_MD` — outcome lines for P1–P5
  (P1 pass/clean haiku; P2 `model=fable attempts=3 result=escalated-pass review=clean`;
  P3/P4/P5 pass/clean sonnet) plus the agent ledger:
  `agent: P1 id=ag-p1-impl role=implementer model=haiku` /
  `agent: P1 id=ag-p1-verif role=verifier model=haiku` /
  `agent: P2 id=ag-p2-impl role=implementer model=sonnet` /
  `agent: P2 id=ag-p2-retry role=implementer model=sonnet` /
  `agent: P2 id=ag-p2-esc role=escalation model=fable` /
  `agent: P3 id=ag-warm role=implementer model=sonnet` /
  `agent: P4 id=ag-warm role=implementer model=sonnet` /
  `agent: P4 id=ag-p4-verif role=verifier model=sonnet` /
  `agent: P5 id=ag-ghost role=implementer model=sonnet` /
  one deliberately malformed `agent: P9 id=ag-bad role=chef model=sonnet` (exercises the
  tolerant skip)); a `projects/-demo/per-task-demo.jsonl` main transcript built like
  `run_demo`'s (one message per tier, ids `demo-bt-main-<tier>`, model ids via
  `_first_model_of_tier(pricing, tier)` with the `if model_id is None: continue` guard,
  volumes from the existing `DEMO_VOLUMES` — reused read-only); and a `tasks/` dir with one
  `<agent-id>.output` file per NON-ghost agent (`ag-p1-impl`, `ag-p1-verif`, `ag-p2-impl`,
  `ag-p2-retry`, `ag-p2-esc`, `ag-warm`, `ag-p4-verif`) plus `ag-reviewer.output` (the phase
  reviewer — referenced by NO line) and deliberately NO `ag-ghost.output` (the cleaned-tmp
  case). Each output file holds one JSONL message (id `demo-bt-<agent-id>`, model id
  computed from its tier, token volumes from the new pinned constant `DEMO_BYTASK_VOLUMES =
  {"ag-p1-impl": ("haiku", 120000, 5000), "ag-p1-verif": ("haiku", 40000, 1500),
  "ag-p2-impl": ("sonnet", 200000, 9000), "ag-p2-retry": ("sonnet", 220000, 10000),
  "ag-p2-esc": ("frontier", 30000, 4000), "ag-warm": ("sonnet", 500000, 24000),
  "ag-p4-verif": ("sonnet", 60000, 2500), "ag-reviewer": ("opus", 90000, 6000)}` — token
  COUNTS, not prices). Then it calls `main([str(kit_dir), "--session", "per-task-demo",
  "--projects-dir", …, "--tasks-dir", …, "--by-task"] + (["--json"] if as_json else []))`
  (the `run_live_demo` pattern — explicit `--tasks-dir` keeps it hermetic, no tmp
  discovery). Pinned expectations (the T1 verify asserts): `by_task` task ids exactly
  `[P1, P2, P3, P4, P5]`; P1 roles {implementer: 1 agent, verifier: 1}, `total_usd > 0`,
  empty missing/shared; P2 implementer 2 agents + escalation 1, `total_usd > 0`; P3
  `shared_agent_ids == ["ag-warm"]`, no roles, `total_usd` None; P4 `shared_agent_ids ==
  ["ag-warm"]`, verifier subtotal > 0, `total_usd > 0`; P5 `missing_agents == ["ag-ghost"]`,
  `total_usd` None; exactly one cluster `{agent_id "ag-warm", task_ids [P3, P4], roles
  [implementer], cost_usd > 0}`; orchestrator `cost_usd > 0`; unattributed `{count 1,
  agent_ids ["ag-reviewer"], cost_usd > 0}`; `coverage == "partial"`; notes include one
  naming `ag-ghost` and one `unrecognized agent line`; the whole-card Dollars block still
  present with `actual_usd > 0` and quality `with_outcome == 5`; markdown contains
  `## Per-task dollars`, `not split`, `never split per task`, `unattributed subagents`, and
  `coverage: partial`. Dollar VALUES are computed from pricing.json at run time and are
  deliberately NOT pinned (structure and relationships only).
- **D10 — Sanctioned literals.** `BYTASK_SCHEMA_VERSION = 1` (same species as the other
  three schema versions), `AGENT_ROLES = ("implementer", "verifier", "escalation")` (grammar
  vocabulary, same species as `RESULTS`/`REVIEWS`), the tier vocabulary and
  `TASK_MODEL_TIERS = {"fable": "frontier"}`, the `DEMO_BYTASK_VOLUMES` token counts, the
  half-cent reconciliation epsilon (a float-noise guard, not a price), and synthetic fixture
  ids/values in tests and the demo. NO new policy constants (the breakdown judges nothing),
  no hardcoded prices, price ratios, real model ids, or pricing dates anywhere in new or
  edited files; every demo/test transcript model id is computed from `data/pricing.json` at
  run time via `_first_model_of_tier`.

## Constraints and OUT-OF-SCOPE fence

Executors must NOT:

- **Break the architect/execute shared kit contract.** No new required task field, no status
  vocabulary change, no removal/rewording of any pinned contract element (the T4 grep list)
  in EITHER skill — including the Tier-2 runtime-override clause, verbatim. The `agent:`
  line is a fourth OPTIONAL, execute-owned NOTES.md line; nothing in TASKS.md changes shape;
  `copilot_execute.parse_tasks` needs no modification. Skill edits are BODY-only — never
  touch the YAML frontmatter of any `skills/*/SKILL.md` (the plugin is installed live).
  `skills/architect/SKILL.md` is not edited at all (D8) — T4 proves it byte-unchanged. If a
  brief's anchor text is not present verbatim, STOP and report — do not approximate.
- **Split the orchestrator/main-session cost per task — the honesty boundary.** The main
  transcript is ONE explicitly un-attributable line; no heuristic division by message count,
  timestamp windows, task mentions, or anything else. Phase reviewers/scouts are never split
  per task either — they ride the unattributed line by design.
- **Fabricate a per-task figure for a missing or shared transcript.** A warm-cluster shared
  transcript is attributed to the cluster as a unit, never divided. A recorded agent id
  whose `*.output` no longer exists prices as `null` + note, never a zero or a guess. A
  per-task figure is only ever the sum of transcripts that actually exist. Coverage is
  labeled `full`/`partial` (null when no events). Zero-data → n/a; the parts-vs-whole
  reconciliation is a NOTE, never an adjustment; zero-denominator anything renders
  null/`n/a`, never a fabricated figure.
- **Break `bin/routing_scorecard.py`'s existing behavior.** Additive only: existing flags,
  function signatures, output shapes, exit codes, the Tier-1 `--demo` numbers, the Tier-2
  `--demo --live` numbers, AND the routing-history `--demo --history` numbers stay
  byte-stable; `tests/test_routing_scorecard.py`, `tests/test_reroute_live.py`, AND
  `tests/test_routing_history.py` are never edited (`git diff --quiet` on all three in every
  verify — new tests go in `tests/test_per_task_dollars.py`). `--by-task` requires
  `--session`; WITHOUT `--by-task` the `--session` output is byte-identical to today (the
  card never carries `by_task`; `MD_H2S` is untouched). Never edit `bin/cost_report.py`,
  `bin/session_cost.py`, `bin/copilot_execute.py`, any other existing `bin/`/`tests/` file,
  `data/` (either pricing file), `.claude-plugin/`, `copilot/`, `README.md`, the generated
  `skills/*/references/` mirrors, any skill other than execute, or the completed kits and
  their agents. Never re-implement `parse_tasks`/`parse_outcomes`/`parse_reroutes`/
  `parse_sessions`/`tier_for`/`effective_alias`/the `session_cost` pipeline — call them.
- **Hardcode prices, price ratios, or real model ids** in any new or edited file. Sanctioned
  exceptions: the D10 list. Demo/test transcript model ids are computed from
  `data/pricing.json` at run time via `_first_model_of_tier`.
- **Read the real `~/.claude` (or the real tmp tasks scratch) from any test or verify
  command.** Every test/verify passes explicit temp `--kits-dir`/`--projects-dir`/
  `--tasks-dir` fixtures with synthetic `*.output`/transcript JSONL. `Path.home()` count in
  `tests/test_per_task_dollars.py` and in the `bin/routing_scorecard.py` diff: ZERO (the
  runtime projects default stays the borrowed `str(sc.DEFAULT_PROJECTS_DIR)` already in the
  argparse line). Never write outside this repo and temp dirs; the scorecard remains
  read-only — the only run-time writer is the demo family, into its own temp dir. No
  network. No plugin re-install. Never invoke a real `claude`/`copilot` CLI.
- **Add dependencies or tooling.** Python stdlib-only; no pip/pytest/requirements; no
  Copilot-side changes; no changes to `/route`/`/escalate`/`/fable-check`; no new skills; no
  README changes.
- **Build past this kit's scope.** No estimated splitting of shared or orchestrator cost
  under any labeling; no auto-anything (no auto-pin, no auto-downgrade — the fusion
  re-routing/escalation semantics are untouched); no cross-kit or time-series per-task
  aggregation (`--by-task` is per-session; `--history` is untouched); no `agent:` folding
  into `--history`; no main-session model switching (still the upstream ask).
- **Commit or push.**

Sanctioned edit targets among existing files: `bin/routing_scorecard.py` (T1, additive),
`skills/execute/SKILL.md` (T3), `docs/ROUTING-HISTORY.md` (T5, pinned pointer paragraph
only), `CLAUDE.md` (T6, pinned run-line only — the per-task-dollars fence paragraph was
already added by the architect). Sanctioned new files: `tests/test_per_task_dollars.py`,
`docs/PER-TASK-DOLLARS.md`.

## Risks & tripwires

- **Breaking the shared contract — THE #1 RISK.** Both skills are live runtime behavior.
  TRIPWIRES: any pinned grep string from the T4 verify missing from either skill; a skill
  file whose frontmatter changed; ANY diff at all in `skills/architect/SKILL.md`; any text
  weakening "the task's `model` field overrides the implementer agent's frontmatter at
  dispatch" or the Tier-2 runtime-override clause; a new REQUIRED task field or TASKS.md
  marker; `parse_tasks` needing modification; the `agent:` line described as anything but
  OPTIONAL and execute-owned. Any hit → stop, revert the edit, report.
- **Splitting the orchestrator share, or fabricating/dividing a shared or missing
  transcript.** TRIPWIRES: any arithmetic that divides the main transcript's cost across
  tasks; a cluster cost divided by its task count (or any weighting); a missing-transcript
  agent contributing `0.0` to a total instead of being excluded with `cost_usd: null`; a
  task `total_usd` of `0` where `None` is meant; reviewers/scouts assigned to a task; the
  reconciliation implemented as an adjustment instead of a note.
- **Additive-only breakage of the scorecard.** TRIPWIRES: `git diff --quiet --
  tests/test_routing_scorecard.py tests/test_reroute_live.py tests/test_routing_history.py`
  failing at any point; any of the THREE prior demos' numbers shifting; `MD_H2S` extended;
  `build_scorecard` emitting `by_task`; the render hook firing for a card without the key;
  `--by-task` accepted without `--session`, or alongside `--live`/`--history`/
  `--no-subagents`; top-level card `notes` gaining by-task notes.
- **The tmp `*.output` being gone at scorecard time (the expected case, not an error).** The
  tasks scratch dir is session-scoped tmp — by the time the user runs `--by-task` it may be
  partially or wholly cleaned. TRIPWIRES: a missing file treated as an error/exit instead of
  a `null` + note + `partial` coverage; a demo/test relying on `discover_task_dirs` against
  real tmp instead of explicit `--tasks-dir` fixtures.
- **Attribution drift at the join.** TRIPWIRES: an unknown-task `agent:` line silently
  attributed or silently dropped (must be noted, transcript to unattributed); a shared agent
  double-counted in both a task row and the cluster row; an unattributed file double-counted
  or dropped; the same agent id counted twice because a re-run appended a duplicate line
  (last-wins must dedupe).
- **Anchor drift in prose edits.** The skill briefs pin exact old/new strings. TRIPWIRE: an
  anchor not found verbatim — report, never fuzzy-match; duplicated content from re-running
  an edit (grep counts in verifies guard this: each new element must appear exactly once).
- **Suite/path quirks.** Verify with `python3 -m unittest discover -s tests
  [-p '<file>.py']` — never the dotted-module form. Paths via `Path(__file__).resolve()`,
  never `$PWD`. No `/private/tmp/` session path in any deliverable. Run
  `python3 bin/sync_pricing_refs.py --check` after skill edits.

## Still deferred after this kit (named, not built)

1. **Any estimated split of the orchestrator or a shared transcript** — not deferred,
   REFUSED by design: an estimate presented as a measurement is the failure mode this whole
   feature exists to avoid.
2. **Per-task dollars in `--history`** — the cross-kit view stays per-kit/per-session;
   folding `agent:` lines into the history aggregate is a possible future kit.
3. **Auto-pin adjustment / auto-downgrade** — unchanged; advisory by design.
4. **Upstream — main-session model switching at compaction boundaries** — unchanged; tracked
   in `docs/FUSION-TIER1.md`.
