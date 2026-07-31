# PLAN — routing-history

autonomy: advisory

(Executes in advisory posture: re-route recommendations during this run are print-only. The
line also dogfoods the fusion-tier2 convention.)

"Scorecard over time" — the first deferred item named in `docs/FUSION-TIER2.md`'s
`## Still deferred`. fusion-tier1 gave every kit an outcome ledger (`outcome:` lines in
NOTES.md) and a per-kit scorecard; fusion-tier2 added `reroute:` lines and a live per-tier
signal. This kit aggregates ALL of it ACROSS kits into a per-tier routing track record —
quality AND dollars — plus one advisory pointer that feeds the track record back into the
architect's INITIAL model pins. Two scope decisions were made upstream and are binding:

1. **Scope A — aggregate quality + dollars.** A `--history` mode scans every kit under the
   kits dir, parses each kit's TASKS.md + NOTES.md, and aggregates per pricing tier
   (haiku/sonnet/opus/frontier): pinned tasks, outcomes (first-try / retry / escalated /
   blocked), rates, and the re-route history. Dollars ride an OPTIONAL, execute-owned
   `session: <id>` line in NOTES.md (precedent: `outcome:`/`reroute:`) — kits that carry it
   get transcript dollars vs an all-frontier counterfactual folded in; kits without it degrade
   to quality-only, and the aggregate is LABELED partial.
2. **Scope B — an ADVISORY pointer into /architect, NOT auto-pin-setting.** One pinned bullet
   in `skills/architect/SKILL.md` Step 2 telling the architect to CONSULT
   `python3 bin/routing_scorecard.py --history` when choosing initial pins. The human/Fable
   decides; nothing sets pins automatically.

The #1 invariant, again: **the architect/execute shared kit contract stays byte-intact.** Both
skill edits are BODY-only, add no required task field, and are followed by the dual-file
contract audit.

## Goal

Ship, end to end, with the full suite green, the shared kit contract provably intact, and
`bin/routing_scorecard.py` extended additively a THIRD time:

1. **`bin/routing_scorecard.py` extended** (additive only): `HISTORY_SCHEMA_VERSION` +
   `SESSION_RE`, pure tested functions (`parse_sessions`, `history_tier_stats`,
   `tally_reroutes`, `scan_kits`, `kit_cost_summary`, `build_history`,
   `render_history_markdown`), a `--history` CLI mode honoring
   `--kits-dir`/`--projects-dir`/`--no-subagents`/`--vs`/`--json`, and a `--demo --history`
   synthetic smoke (`run_history_demo`). Existing flags, output shapes, exit codes, the Tier-1
   `--demo` numbers, AND the Tier-2 `--demo --live` numbers stay byte-stable;
   `tests/test_routing_scorecard.py` and `tests/test_reroute_live.py` are byte-untouched.
2. **`tests/test_routing_history.py`** — new stdlib unittest file: pure-function coverage
   (attribution, tolerance, tallies), dollars aggregation against synthetic transcripts in
   temp dirs, degradation/never-fabricate proofs, a pricing-free proof for the
   zero-`session:`-lines path, CLI end-to-end, both prior demos' regression checks, and a
   read-only proof.
3. **`skills/execute/SKILL.md` extended** (body only): the End-of-run section records ONE
   optional `session: <session-id>` line in NOTES.md via a pinned read-only lookup, and offers
   the cross-kit history alongside the per-kit scorecard. Every existing contract element
   survives verbatim.
4. **`skills/architect/SKILL.md` synced** (body only): the Scope-B advisory bullet in Step 2 —
   then the dual-file contract audit (the CLAUDE.md invariant: touch either skill, re-check
   BOTH).
5. **`docs/ROUTING-HISTORY.md`** (new) + a pinned pointer paragraph appended to
   `docs/FUSION-TIER2.md`'s `## Still deferred` section, and one pinned CLAUDE.md run-line.

**Done looks like:** `python3 -m unittest discover -s tests` green (baseline 350 tests, plus
`tests/test_routing_history.py`); `python3 bin/sync_pricing_refs.py --check` exits 0;
`python3 bin/routing_scorecard.py --demo --json` still yields the Tier-1 pinned numbers
(quality 6/6/3/1/1/1, mix {haiku 1, sonnet 4, fable 1}, survival 0.75);
`python3 bin/routing_scorecard.py --demo --live --json` still yields the Tier-2 pinned numbers
(one recommendation, sonnet→opus, tasks L5+L6, budget 0/2 applied, autonomy advisory);
`python3 bin/routing_scorecard.py --demo --history --json` yields the D9 pinned history
numbers; the T4 dual-file contract grep passes (every pinned element in BOTH skills,
frontmatter intact); `git status` shows changes ONLY to sanctioned targets (edits:
`bin/routing_scorecard.py`, `skills/execute/SKILL.md`, `skills/architect/SKILL.md`,
`docs/FUSION-TIER2.md`, `CLAUDE.md`; new: `tests/test_routing_history.py`,
`docs/ROUTING-HISTORY.md`, this kit + its agents); and `git diff --quiet --
tests/test_routing_scorecard.py tests/test_reroute_live.py bin/cost_report.py
bin/session_cost.py bin/copilot_execute.py data` stays clean throughout.

## Repo facts (confirmed by the architect — trust these, do not re-derive)

- **The shared kit contract** (CLAUDE.md invariant; both skills must keep expressing it):
  layout `.claude/kits/<slug>/PLAN.md` + `TASKS.md` (+ `NOTES.md`, owned by execute); task
  fields `id`, `title`, `status`, `model`, brief, acceptance, verify; status vocabulary
  exactly `pending | in-progress | done | blocked`; `## Phase N — <name>` headings;
  `depends:`/`independent:` marking; the rule that a task's `model` field overrides the
  implementer agent's frontmatter at dispatch — including the Tier-2 runtime-override clause
  ("execute may layer a logged, upgrade-only runtime override on top at dispatch (one tier
  step, never to frontier) — the field itself is never rewritten and stays the dispatch
  default"), which must be preserved verbatim. This kit adds NO new required task field; the
  only new kit-file convention is the OPTIONAL NOTES.md `session:` line.
  `copilot_execute.parse_tasks` needs no change.
- **This plugin is installed LIVE** from this directory — skill files are runtime behavior.
  Their YAML frontmatter must never be touched by this kit.
- **Current `skills/execute/SKILL.md` section order** (unchanged by this kit — only the
  End-of-run paragraph's final sentence is replaced): `## Setup` → `## Operating rule — lean
  driver` → `## The loop` → `## Dispatch modes — fresh fan-out vs warm sidekick` →
  `## Outcome ledger — one line per finished task` → `## Live re-routing — upgrade-only,
  autonomy-gated` → `## Escalation valve — blocked tasks go back to Fable, one at a time` →
  `## End of run`. The End-of-run paragraph currently ends with the exact sentence:
  `Then offer the routing-quality scorecard: `python3 bin/routing_scorecard.py <slug>`
  (first-try pass rate, model mix, cheap-model review survival, and — with `--session` —
  dollars vs an all-frontier counterfactual).` — the T3 anchor.
- **Current `skills/architect/SKILL.md` Step-2 model bullet** (the T4 anchor — one line,
  ends): `…execute may layer a logged, upgrade-only runtime override on top at dispatch (one
  tier step, never to frontier) — the field itself is never rewritten and stays the dispatch
  default.`
- **`bin/routing_scorecard.py` today** (all reusable in place — extend, never fork; NEVER
  re-implement any of these): `_load(name)` importlib loader with `ce = _load("copilot_execute")`,
  `sc = _load("session_cost")`, `cr = sc.cr`; `TASK_MODEL_TIERS = {"fable": "frontier"}` and
  `tier_for(alias)`; `OUTCOME_RE`/`PAIR_RE` + `parse_outcomes(text) -> (outcomes, notes)`
  (tolerant, last-line-wins per task id); `REROUTE_RE` + `parse_reroutes(text) -> (events,
  notes)` (events carry `from`/`to`/`mode`/`tasks`/`rate`, file order); `parse_autonomy`;
  `effective_alias(task, applied_events)` (pin overridden by the LAST applied event naming the
  task); `live_tier_stats`/`upgrade_decision`/`build_live_card`/`render_live_markdown`;
  `build_scorecard`; `session_cost_summary(session_id, projects_dir, tasks_dirs, includes,
  no_subagents, vs, pricing) -> (cost_or_None, notes)`; `_rate_pct(rate)` (`n/a` on None);
  `_first_model_of_tier(pricing, tier)`; `DEMO_VOLUMES` (per-tier token volumes);
  `run_demo(as_json)` / `run_live_demo(as_json)` (each builds fixtures in ONE
  `tempfile.TemporaryDirectory` — the live demo calls `main(argv)` against them);
  `_resolve_kit_dir(kit, kits_dir)`; `DEFAULT_KITS_DIR = PLUGIN_ROOT / ".claude" / "kits"`
  (repo-local, NOT under `~`); `main()` argparse with `kit` positional, `--kits-dir`,
  `--session`, `--projects-dir` (default `str(sc.DEFAULT_PROJECTS_DIR)`), `--tasks-dir`,
  `--include`, `--no-subagents`, `--vs`, `--json`, `--demo`, `--live`, `--live-threshold`,
  `--live-min-sample`, `--live-max-auto`. Existing main() check order: the
  `--live`+`--session` rejection, then the `--demo` block, then the kit-required check, then
  kit resolution.
- **`bin/session_cost.py` reusables:** `find_main_transcript(session_id, projects_dir)`
  (rglob `<session_id>.jsonl`, None when absent), `discover_task_dirs(session_id)`
  (best-effort tmp glob; returns `[]` for synthetic ids), `gather_files(main_transcript,
  task_dirs, includes)` — **its first argument may be `None`** (it appends only if truthy) and
  `includes` accepts explicit file paths as strings, `collect(files, pricing)` — **dedupes by
  message id GLOBALLY within one call** (the lever D5 uses against double counting),
  `resolve_counterfactual_model(vs, pricing)` (raises ValueError on a bad `--vs`),
  `build_report(data, cf_key, pricing, mode)` (`actual_total`, `cf_total`, `savings`,
  `ratio`, `cf_key`, `cf_display`), `DEFAULT_PROJECTS_DIR`.
- **`ce.parse_tasks(text)`** returns dicts `{id, title, status, model, depends, independent,
  brief, verify}`; task headings are `### <id> — <title>` with a spaced em dash; it raises
  ValueError on a malformed status (scan_kits must catch this per kit).
- **Transcript layout:** the main transcript of a session is
  `<projects-dir>/<project-slug>/<session-id>.jsonl`; the session id is the filename stem;
  the project slug is the project's absolute path with every non-alphanumeric character
  replaced by `-` (observed for this repo: `-path-to-polytropos`).
- **pricing.json tier vocabulary:** `frontier`, `opus`, `sonnet`, `haiku`; task `model` values
  are the Agent-tool aliases `fable | opus | sonnet | haiku`; alias→tier is identity except
  `fable → frontier`.
- **Suite:** `python3 -m unittest discover -s tests [-p '<file>.py']` — never the dotted-module
  form (broken on this machine). Baseline 350 tests, green.
  `python3 bin/sync_pricing_refs.py --check` must stay exit 0.

## Architecture & key decisions

- **D1 — The history lives in `bin/routing_scorecard.py` as a THIRD additive mode, not a new
  script.** Same rationale that put `--live` there (fusion-tier2 D8): the history consumes
  exactly the inputs the scorecard already parses (`ce.parse_tasks`, `parse_outcomes`,
  `parse_reroutes`) and the same alias machinery (`TASK_MODEL_TIERS`, `tier_for`,
  `effective_alias`), plus the dollars plumbing `session_cost_summary` already wraps — a
  separate script would duplicate or importlib-load all of it anyway, and one script keeps ONE
  surface for skills to shell out to (`--live` mid-run, plain scorecard at end of kit,
  `--history` across kits). Unlike `--live`, the history is DESCRIPTIVE, not prescriptive: it
  recommends nothing and therefore needs NO policy knobs — the only new constant is
  `HISTORY_SCHEMA_VERSION = 1` (plus `SESSION_RE` and `DEMO_HIST_*` fixtures). ADDITIVE means:
  new constants, new pure functions, new argparse flag, new render path — zero changes to
  existing function signatures, outputs, exit codes, or either prior demo's numbers, and BOTH
  existing scorecard test files stay byte-untouched (enforced by `git diff --quiet` in every
  verify; new tests live in `tests/test_routing_history.py`).
- **D2 — The per-tier aggregation shape, with the Tier-2 attribution rule reused verbatim.**
  For every tier in `LIVE_TIER_ORDER`, over ALL scanned kits:
  `pinned` = tasks whose `tier_for(task["model"])` is that tier (the architect's pins — kept
  as raw pins on purpose, since pins-vs-outcomes is the comparison the architect needs; tasks
  with no pin or an off-ladder pin are counted in a per-kit note, never guessed);
  `with_outcome` = recognized outcomes attributed to the tier; `first_try` (`result=pass`),
  `retry_pass`, `escalated_pass`, `blocked`; `first_try_rate = first_try / with_outcome` and
  `escalation_rate = escalated_pass / with_outcome` (both None when `with_outcome` is 0 —
  never a fabricated 0%). **Attribution is fusion-tier2 D1, unchanged:** `pass` /
  `retry-pass` / `blocked` attribute to `tier_for(outcome["model"])` (the ledger's `model=`
  is what the task ran on); `escalated-pass` attributes to `tier_for(effective_alias(task,
  applied_events))` — the reconstructed DISPATCH tier — because the ledger's `model=` on an
  escalated line names the Fable fixer, and crediting frontier with a cheap tier's failure
  would pollute frontier's stats and hide the struggling tier's history. Implemented in a new
  `history_tier_stats(tasks, outcomes, applied_events)` that CALLS `tier_for` and
  `effective_alias` (it may not re-implement them); it is a superset of `live_tier_stats`'
  counting (the 4-way result split) and deliberately does not disturb that function.
  Re-route history: `tally_reroutes(events)` counts EVENTS (one event = one logged decision)
  → totals `{events, applied, advisory}` plus per-tier
  `{applied_from, applied_to, advisory_from, advisory_to}` for every ladder tier.
- **D3 — Dollars ride an OPTIONAL, execute-owned `session:` NOTES.md line — the
  contract-safe attribution channel.** Grammar (pinned; the skill text and `parse_sessions`
  must match): `session: <session-id>` — one whitespace-free token, nothing else on the line
  (optional `-`/`*` bullet tolerated, mirroring `OUTCOME_RE`/`REROUTE_RE`):
  `SESSION_RE = re.compile(r"^\s*(?:[-*]\s+)?session:\s+(\S+)\s*$")`. No id-format validation
  — the id's shape is harness-owned, not ours. NOTES.md is execute-owned, so a third line
  format inside it is NOT a contract change (precedent: `outcome:` in Tier 1, `reroute:` in
  Tier 2); `OUTCOME_RE` and `REROUTE_RE` cannot match a `session:` line, so all prior
  consumers are unaffected; nothing in TASKS.md changes shape and `parse_tasks` needs no
  modification. A kit executed across several runs legitimately carries several `session:`
  lines — `parse_sessions` returns them in file order, deduped, and the dollars fold in ALL
  of them (D5). The line is appended by the ORCHESTRATOR at end of run; no script ever writes
  it (`--history` is read-only like `--live`).
- **D4 — How `/execute` obtains its own session id: the transcript-stem lookup, read-only, at
  end of run.** The run's main transcript is being written to
  `<projects-dir>/<project-slug>/<session-id>.jsonl` for the whole session, so at END of run
  the most recently modified `*.jsonl` in the project's transcript dir is the current
  session's file, and its filename stem is the id — the exact heuristic
  `session_cost.find_main_transcript` already uses for its "latest" default. The skill pins
  one example command (project slug = absolute project path with every non-alphanumeric
  character replaced by `-`):
  `ls -t "$HOME/.claude/projects/$(pwd | sed 's|[^A-Za-z0-9]|-|g')"/*.jsonl | head -1`.
  Rules pinned in the skill text: the lookup is READ-ONLY and BEST-EFFORT; recording happens
  once, at end of run (never mid-run — end-of-run mtime freshness is what makes the heuristic
  sound); if the lookup finds nothing or the orchestrator cannot resolve it unambiguously
  (e.g. a concurrent session in the same project), SKIP the line — the history degrades to
  quality-only for this kit, and a guessed id is worse than no id; a resumed kit appends one
  line per run. Accepted approximation (named, not hidden): a concurrent same-project session
  could win the mtime race — mitigated by end-of-run timing, the skip-when-ambiguous rule,
  and the line being human-auditable plain text in NOTES.md. If the harness ever exposes the
  session id directly, the orchestrator may use that instead — the NOTES grammar doesn't care
  where the id came from.
- **D5 — Dollars aggregation: one `collect()` per scope over unique transcripts — never a
  fabricated number.** New helper `kit_cost_summary(session_ids, projects_dir, no_subagents,
  vs, pricing) -> (cost_or_None, transcripts, notes)`: resolve each id via
  `sc.find_main_transcript` (missing → note, id skipped — NEVER invented); union the
  best-effort `sc.discover_task_dirs(sid)` results unless `no_subagents`; build the file list
  with `sc.gather_files(None, task_dirs, [str(t) for t in transcripts])` (its first arg may
  be None; explicit paths ride `includes`); ONE `sc.collect(files, pricing)` call so the
  global message-id dedupe absorbs any overlap between a kit's several sessions (a resumed
  transcript can embed prior messages — summing per-session reports would double count;
  collecting once cannot); price via `sc.resolve_counterfactual_model` +
  `sc.build_report`. Per-kit cost dict: `{actual_usd, counterfactual_usd, delta_usd, ratio,
  sessions_priced, files_scanned}`; a kit whose sessions all lack transcripts → cost None +
  note. The AGGREGATE runs the same helper once over the ordered-unique union of ALL kits'
  session ids — so a session id recorded by two kits (one session executed two kits) is
  priced ONCE in the aggregate (a note flags the shared id; per-kit rows still each carry
  their own full number, and the markdown says per-kit rows may overlap when ids are shared).
  Degradation ladder (pinned): zero `session:` lines anywhere → `dollars: null`, the note
  `no session: lines found — dollars n/a (quality-only history)`, and `cr.load_pricing()` is
  NEVER called (the quality-only path is pricing-free, like `--live`; T2 proves it by
  stubbing `load_pricing` to raise); session lines exist but none resolve to a transcript →
  pricing loads, `dollars: null` + note — never a $0.00 that looks real; some kits lack
  lines or some ids lack transcripts → dollars present with `coverage: "partial"`; every kit
  has ≥1 line and every id priced → `coverage: "full"`. The counterfactual model comes from
  `resolve_counterfactual_model(vs, pricing)` at run time — no hardcoded model id; a bad
  `--vs` propagates ValueError → `sys.exit` (mirror the existing `--session` path).
  `--tasks-dir`/`--include` are single-session affordances and are IGNORED by `--history`
  (folding one explicit dir into N sessions would double count); when passed together with
  `--history` a note says so.
- **D6 — Scan tolerance and determinism.** `scan_kits(kits_dir) -> (records, notes)`:
  subdirectories in sorted-by-name order (deterministic output); a subdir with no TASKS.md →
  skipped + note; a TASKS.md that makes `ce.parse_tasks` raise ValueError → kit skipped +
  note (never a crash); missing NOTES.md → empty outcomes/events/sessions + the status-only
  note (`<kit>: no outcome ledger — status-only`); NOTES.md read ONCE per kit, feeding
  `parse_outcomes`, `parse_reroutes`, AND `parse_sessions` (their own tolerance notes are
  carried through, prefixed `<kit>: `). Every kit predating the ledger therefore contributes
  its pins to `pinned` and nothing to the outcome counters — visible, never invented. Each
  record: `{"kit", "tasks", "outcomes", "events", "sessions", "notes"}`. A kits dir that does
  not exist → `sys.exit` with the path; an existing kits dir with zero kit records → exit 0
  with an empty card + note (degraded, not an error).
- **D7 — The `--history` CLI and card contracts (pinned).** Invocation:
  `python3 bin/routing_scorecard.py --history [--kits-dir DIR] [--projects-dir DIR]
  [--no-subagents] [--vs MODEL_ID] [--json]`. Errors (checked before the `--demo` block,
  after the existing `--live`+`--session` check): `--history` + `--live` →
  `sys.exit("--history and --live are mutually exclusive")`; `--history` + `--session` →
  `sys.exit("--history takes no --session — dollars come from NOTES.md session: lines")`;
  `--history` + a kit positional → `sys.exit("--history takes no kit argument")`. The
  non-demo history branch runs BEFORE the `if not args.kit` check. JSON top-level keys
  EXACTLY: `schema_version` (`HISTORY_SCHEMA_VERSION = 1`), `generated_at` (same style as
  `build_scorecard`), `kits_dir` (string), `kits` (list, sorted by kit name), `tiers`,
  `reroutes` (`{events, applied, advisory}`), `dollars` (dict or None), `notes`. `tiers` maps
  EVERY tier in `LIVE_TIER_ORDER` to `{pinned, with_outcome, first_try, retry_pass,
  escalated_pass, blocked, first_try_rate, escalation_rate, reroutes: {applied_from,
  applied_to, advisory_from, advisory_to}}`. Each `kits` row:
  `{kit, tasks, with_outcome, first_try_pass, retry_pass, escalated_pass, blocked, sessions,
  cost}` (`cost` = the D5 per-kit dict or None). `dollars` (when not None):
  `{kits_with_sessions, kits_total, sessions_found, sessions_priced, actual_usd,
  counterfactual_usd, delta_usd, ratio, counterfactual_model: {key, display}, coverage,
  pricing_cached}`. Markdown: H1 `# Routing history — cross-kit per-tier track record`, then
  EXACTLY these five H2s in order: `## Verdict` (one bold line: kit count, overall first-try
  `<p>/<n>` or n/a, and a dollars segment — the aggregate with its coverage label, or
  `dollars n/a (no session: lines)`), `## Per-tier track record` (one table row per ladder
  tier; None rates render `n/a` via `_rate_pct`), `## Re-route history` (event totals + only
  the tiers with nonzero tallies, or `no re-route events recorded`), `## Kits` (one row per
  kit: tasks, outcome counts, sessions count, actual $ or `n/a`), `## Dollars` (the aggregate
  block with `coverage`, or the n/a sentence), then a `Notes:` bullet list when notes exist
  (mirror `render_markdown`). Exit 0 on success including every degraded shape.
- **D8 — Scope B is ONE advisory bullet, and that is the whole /architect change.** Inserted
  in Step 2 immediately after the model-authoritative bullet (the natural home — it is
  model-pin guidance): consult `python3 bin/routing_scorecard.py --history` when choosing
  initial `model` pins; the history is EVIDENCE (first-try rate, escalation rate, upgrade
  frequency, dollars where present), the architect weighs it and decides. No skill text may
  describe automatic pin adjustment from history — pins remain human/Fable judgment, exactly
  as auto-downgrade stayed human judgment in Tier 2. Contract safety: a new advisory bullet
  adds guidance, removes nothing, changes no task field, and is followed by the T4 dual-file
  audit.
- **D9 — The demo contract (pinned).** `--demo --history` builds a synthetic kits root + a
  synthetic projects dir in ONE `tempfile.TemporaryDirectory` and runs the normal history
  path against them via `main(["--history", "--kits-dir", …, "--projects-dir", …,
  "--no-subagents", …])` (the `run_live_demo` pattern; `--no-subagents` keeps the demo
  hermetic — no tmp-dir discovery). Fixtures (module constants prefixed `DEMO_HIST_`;
  headings use the spaced em dash; all ids/values synthetic):
  * kit `hist-alpha` — tasks A1 haiku done, A2 sonnet done, A3 sonnet done, A4 opus done,
    A5 **sonnet** done; NOTES ledger `A1 model=haiku result=pass review=clean` /
    `A2 model=sonnet result=pass review=clean` /
    `A3 model=sonnet attempts=2 result=retry-pass review=revised` /
    `A4 model=opus result=pass review=clean` /
    `A5 model=fable attempts=3 result=escalated-pass review=clean` (exercises the
    escalated→dispatch-tier attribution: counts against SONNET) + one line
    `session: hist-alpha-session`. Transcript
    `<projects>/-demo/hist-alpha-session.jsonl` with one message per tier — model ids
    COMPUTED via `_first_model_of_tier(pricing, tier)` at run time, token volumes from the
    existing `DEMO_VOLUMES` (reused read-only; never new hardcoded ids).
  * kit `hist-beta` — tasks B1 haiku done, B2 haiku done, B3 sonnet done, B4 sonnet blocked;
    NOTES ledger `B1 model=haiku result=pass review=clean` /
    `B2 model=haiku attempts=2 result=retry-pass review=clean` /
    `B3 model=sonnet result=pass review=clean` /
    `B4 model=sonnet attempts=2 result=blocked review=none` +
    `reroute: haiku to=sonnet mode=advisory tasks=B2 rate=1/2`. NO `session:` line → per-kit
    dollars n/a.
  * kit `hist-gamma` — a pre-ledger kit: tasks C1 sonnet done, C2 opus done, C3 fable
    pending; NO NOTES.md at all → status-only note, contributes pins only.
  * `not-a-kit` — a subdir with no TASKS.md → skipped + note.
  Pinned expectations (the T1 verify asserts): tiers.haiku `{pinned 3, with_outcome 3,
  first_try 2, retry_pass 1, escalated_pass 0, blocked 0}` (rate 2/3); tiers.sonnet
  `{pinned 6, with_outcome 5, first_try 2, retry_pass 1, escalated_pass 1, blocked 1}`
  (rate 0.4, escalation_rate 0.2); tiers.opus `{pinned 2, with_outcome 1, first_try 1}`
  (rate 1.0); tiers.frontier `{pinned 1, with_outcome 0}` (rates None → `n/a` in markdown);
  reroutes `{events 1, applied 0, advisory 1}` with haiku `advisory_from 1` and sonnet
  `advisory_to 1`; kits rows alpha 5/5, beta 4/4, gamma 3/0; dollars present with
  `kits_total 3, kits_with_sessions 1, sessions_found 1, sessions_priced 1,
  coverage "partial"` and `actual_usd > 0` — the dollar VALUES are computed from
  pricing.json at run time and are deliberately NOT pinned (only structure and coverage are).
- **D10 — Sanctioned literals.** `HISTORY_SCHEMA_VERSION = 1` (same species as
  `SCHEMA_VERSION`/`LIVE_SCHEMA_VERSION`), the tier vocabulary and `LIVE_TIER_ORDER`, the
  `TASK_MODEL_TIERS = {"fable": "frontier"}` alias map, and synthetic fixture ids/values in
  tests and the demo. NO new policy constants (the history judges nothing), no hardcoded
  prices, price ratios, real model ids, or pricing dates anywhere in new or edited files; the
  zero-`session:`-lines path never loads pricing.json.

## Constraints and OUT-OF-SCOPE fence

Executors must NOT:

- **Break the architect/execute shared kit contract.** No new required task field, no status
  vocabulary change, no removal/rewording of any pinned contract element (the T4 grep list)
  in EITHER skill — including the Tier-2 runtime-override clause, preserved verbatim. The
  `session:` line is an OPTIONAL, execute-owned NOTES.md line; nothing in TASKS.md changes
  shape; `copilot_execute.parse_tasks` needs no modification. Skill edits are BODY-only —
  never touch the YAML frontmatter of any `skills/*/SKILL.md` (the plugin is installed
  live). If a brief's anchor text is not present verbatim, STOP and report — do not
  approximate.
- **Build auto-pin-setting anywhere.** The /architect change is ONE advisory bullet — consult
  and decide. No skill or script text may adjust, rewrite, or recommend rewriting a task
  `model` field from history data; no auto-downgrade; the live re-routing and escalation-valve
  mechanisms are untouched.
- **Fabricate dollars.** Aggregate only over kits carrying `session:` lines; label coverage
  (`partial`/`full`); a missing transcript is a note and a skipped id, never an invented or
  zeroed figure presented as real; per-kit dollars are `null`/`n/a` when absent;
  zero-denominator rates render None/`n/a`, never 0%. Ledger-free kits degrade to
  status-only. With zero `session:` lines, `--history` never calls `cr.load_pricing()`.
- **Break `bin/routing_scorecard.py`'s existing behavior.** Additive only: existing flags,
  functions, output shapes, exit codes, the Tier-1 `--demo` numbers, and the Tier-2
  `--demo --live` numbers stay byte-stable; `tests/test_routing_scorecard.py` AND
  `tests/test_reroute_live.py` are never edited (`git diff --quiet` on both in every verify —
  new tests go in `tests/test_routing_history.py`). Never edit `bin/cost_report.py`,
  `bin/session_cost.py`, `bin/copilot_execute.py`, any other existing `bin/`/`tests/` file,
  `data/` (either pricing file), `.claude-plugin/`, `copilot/`, `README.md`, the generated
  `skills/*/references/` mirrors, any skill other than execute/architect, or the completed
  kits and their agents. Never re-implement `parse_tasks`/`parse_outcomes`/`parse_reroutes`/
  `tier_for`/`effective_alias`/the `session_cost` pipeline — call them.
- **Hardcode prices, price ratios, or real model ids** in any new or edited file. Sanctioned
  exceptions: the D10 list. Demo transcript model ids are computed from `data/pricing.json`
  at run time via `_first_model_of_tier`.
- **Read the real `~/.claude` from any test or verify command.** Every test/verify passes
  explicit temp `--kits-dir`/`--projects-dir` fixtures (the repo-local `.claude/kits` default
  is acceptable ONLY with `--projects-dir` pointed at a temp dir, and only in a verify).
  `Path.home()` count in `tests/test_routing_history.py` and in the
  `bin/routing_scorecard.py` diff: ZERO (the runtime projects default stays the borrowed
  `str(sc.DEFAULT_PROJECTS_DIR)` already in the argparse line). Never write outside this repo
  and temp dirs; the only run-time writer is the demo's own temp dir. No network. No plugin
  re-install. Never invoke a real `claude`/`copilot` CLI.
- **Add dependencies or tooling.** Python stdlib-only; no pip/pytest/requirements; no
  Copilot-side changes; no changes to `/route`/`/escalate`/`/fable-check`; no new skills; no
  README changes.
- **Build past this kit's scope.** No auto-pin adjustment, no scorecard-over-time trend
  charts/plots, no cross-REPO aggregation (one kits dir per invocation), no per-task dollar
  attribution (dollars are per-session/per-kit — task-level split is not reconstructable and
  will not be faked), no main-session model switching (still the upstream ask).
- **Commit or push.**

Sanctioned edit targets among existing files: `bin/routing_scorecard.py` (T1, additive),
`skills/execute/SKILL.md` (T3), `skills/architect/SKILL.md` (T4), `docs/FUSION-TIER2.md`
(T5, pinned Still-deferred pointer only), `CLAUDE.md` (T6, pinned run-line only — the
routing-history fence paragraph was already added by the architect). Sanctioned new files:
`tests/test_routing_history.py`, `docs/ROUTING-HISTORY.md`.

## Risks & tripwires

- **Breaking the shared contract — THE #1 RISK.** Both skills are live runtime behavior.
  TRIPWIRES: any pinned grep string from the T4 verify missing from either skill; a skill
  file whose frontmatter changed; any text weakening "the task's `model` field overrides the
  implementer agent's frontmatter at dispatch" or the Tier-2 runtime-override clause; a new
  REQUIRED task field or TASKS.md marker; `parse_tasks` needing modification; the `session:`
  line described as anything but OPTIONAL and execute-owned. Any hit → stop, revert the
  edit, report.
- **Fabricated or double-counted dollars.** TRIPWIRES: a `$` figure for a kit with no priced
  session; `$0.00` rendered for "no data" (must be `n/a`/null); sums taken across per-session
  reports instead of one `collect()` per scope (D5 — resumed transcripts double count that
  way); a shared session id inflating the aggregate (must be priced once); `--tasks-dir`/
  `--include` folded into the history; the zero-lines path importing pricing (the stubbed
  `load_pricing` test must stay red-proof).
- **The session-id lookup lying.** TRIPWIRES: skill text telling the orchestrator to record a
  guessed id; recording mid-run instead of at end of run; the lookup described as anything
  but read-only + best-effort + skippable; a mechanism that writes anywhere under `~/.claude`.
- **Old, ledger-free kits crashing or polluting the record.** TRIPWIRES: `scan_kits` raising
  on a malformed TASKS.md, a stray non-kit dir, or a missing NOTES.md; a status-only kit
  contributing invented outcome counts; an outcome for an unknown task id silently counted
  (skip + note); a `to=frontier` reroute line crashing the tallies (parse_reroutes already
  notes it — tallies count what parsed).
- **Additive-only breakage of the scorecard.** TRIPWIRES: `git diff --quiet --
  tests/test_routing_scorecard.py tests/test_reroute_live.py` failing at any point; the
  Tier-1 `--demo --json` or Tier-2 `--demo --live --json` numbers shifting; any existing
  flag/exit-code behavior changing; `--history` accepted alongside `--live`, `--session`, or
  a kit positional.
- **Attribution drift.** `escalated-pass` must count against the reconstructed dispatch tier
  (pin ± applied re-routes via `effective_alias`), never frontier; `pinned` counts must come
  from the raw pin. TRIPWIRE: a test fixture showing an escalated task inflating frontier's
  `with_outcome`, or an applied re-route shifting the `pinned` column.
- **Anchor drift in prose edits.** The skill briefs pin exact old/new strings. TRIPWIRE: an
  anchor not found verbatim — report, never fuzzy-match; duplicated content from re-running an
  edit (grep counts in verifies guard this: each new element must appear exactly once).
- **Suite/path quirks.** Verify with `python3 -m unittest discover -s tests
  [-p '<file>.py']` — never the dotted-module form. Paths via `Path(__file__).resolve()`,
  never `$PWD`. No `/private/tmp/` session path in any deliverable. Run
  `python3 bin/sync_pricing_refs.py --check` after skill edits.

## Still deferred after this kit (named, not built)

1. **Auto-pin adjustment** — the history stays advisory by DESIGN; the architect (human or
   Fable) reads the track record and decides the pins.
2. **Cross-repo / long-horizon trend aggregation** — one kits dir per invocation; no
   time-series store, no charts.
3. **Per-task dollar attribution** — transcripts price sessions, not tasks; a per-task split
   would be an estimate presented as a measurement, so it is not built.
4. **Upstream — main-session model switching at compaction boundaries** — unchanged; tracked
   in `docs/FUSION-TIER1.md`.
