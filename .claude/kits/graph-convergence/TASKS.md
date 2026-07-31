# TASKS — graph-convergence

Repo root: the polytropos checkout. Run all verify commands from there.
Read `PLAN.md` (same directory) first — decisions D1–D8, the out-of-scope fence, and
`GUARDRAILS.md`. Status vocabulary: `pending | in-progress | done | blocked`.

Dispatch rule for the orchestrator: pass each task's `model` value as the Agent tool's
`model` parameter. `depends:` lists hard ordering. **Warm-cluster candidates:** T1→T3 (both
edit `skills/architect/SKILL.md`, both opus). T6, T12 fan out fresh.

Standing rules for every task:

- **Never invoke the real `claude`/`copilot`/`codex` CLI** in any test or verify command.
  Every dispatch path goes through the injectable-runner seam; tests use stubs and temp
  `--*-home`/`--kit` fixtures only. `--dry-run` spawns nothing.
- **All new ledger fields are optional (PLAN D6).** Any parser change must leave behavior on
  field-less input byte-identical; assert this in tests.
- **No hardcoded prices, model ids, or tiers** — resolve from the pricing files at run time.
  Python stdlib-only. Do not commit or push. If a brief's pinned anchor disagrees with repo
  reality, STOP and report — never improvise.
- Full-suite verify: `python3 -m unittest discover -s tests -v` must pass before any task is
  claimed done, in addition to the task's own verify command.

---

## Phase 1 — Shared kit contract (ids + lineage)

### T1 — Extend the outcome-line grammar with `run=`, `parent=`, and `failure=`
- status: done
- model: opus
- depends: (none)
- Brief: Add three OPTIONAL key=value fields to the `outcome:` line family:
  `run=<UTC-date>-<4hex>` (one id per driver invocation, format per PLAN D8),
  `parent=<task-id>` (set only on escalation/consult outcomes, naming the task that spawned
  them), and `failure=<execution|coherence|verification>` (set only on blocked/escalated
  outcomes, per PLAN D9 — the three-class minimum from the AgentRx-style taxonomy; finer
  labels stay free text in NOTES prose). Spec lands in BOTH `skills/execute/SKILL.md` and `skills/architect/SKILL.md`
  (the CLAUDE.md sync invariant — architect's NOTES.md description must mention the new
  optional fields as execute-owned). No task-field changes; the task contract
  (`id/title/status/model/brief/acceptance/verify`) is untouched.
- Acceptance: both SKILL.md files describe `run=`/`parent=`/`failure=` as optional,
  execute-owned outcome-line fields, with the three-class failure vocabulary pinned; grammar example present in execute's SKILL.md; no change to the task
  field list in either file.
- Verify: `grep -q 'run=' skills/execute/SKILL.md && grep -q 'parent=' skills/execute/SKILL.md && grep -q 'failure=' skills/execute/SKILL.md && grep -q 'run=' skills/architect/SKILL.md && python3 -m unittest discover -s tests`

### T2 — routing_scorecard consumes ids + lineage, byte-stable on legacy kits
- status: done
- model: sonnet
- depends: T1
- Brief: `bin/routing_scorecard.py` parses optional `run=`/`parent=`/`failure=` on
  `outcome:` lines. `--history` groups escalation outcomes under their `parent=` task,
  reports a per-tier "escalations descending from cheap pins" count, AND breaks per-tier
  failures down by `failure=` class — a tier failing on `verification` argues for a stronger
  verifier pin, not a stronger implementer pin (PLAN D9); single-kit mode shows run ids when
  present. Legacy path: capture the current `--demo` and `--demo --history` outputs as
  golden strings in `tests/test_routing_scorecard.py` BEFORE editing, then assert
  byte-identical after (PLAN D6 tripwire). New synthetic-kit fixtures exercise the fields.
- Acceptance: golden-output tests pass unmodified; lineage grouping and the failure-class
  breakdown appear in `--history` only when the respective fields exist; `--json` carries the new keys only when present.
- Verify: `python3 -m unittest discover -s tests -p 'test_routing_scorecard.py' -v`

---

## Phase 2 — Claude harness

### T3 — Tool scoping in the architect's kit-agent templates
- status: done
- model: opus
- depends: T1
- Brief: In `skills/architect/SKILL.md`, the generated-agent spec gains `tools:` frontmatter
  pins (PLAN D4): `<slug>-verifier.md` → read/search + Bash only (no Write/Edit);
  `<slug>-reviewer.md` → no Write/Edit; implementer unchanged. State the rationale line in
  the skill ("a verifier that cannot patch cannot be talked into fixing") so future kits
  inherit the why.
- Acceptance: template descriptions for verifier and reviewer each specify a `tools:` pin;
  implementer spec unchanged; wording makes the pin mandatory for newly generated kits.
- Verify: `grep -q 'tools:' skills/architect/SKILL.md && python3 -m unittest discover -s tests`

### T4 — Verify-proof marker + enforcement hook
- status: done
- model: sonnet
- depends: T1
- Brief: New `bin/kit_verify_hook.py` (stdlib-only). Three roles per PLAN D3/D10: (a) a
  `record` subcommand the verify path invokes to write a timestamped marker
  `.claude/kits/<slug>/verify-pass/<task-id>` (gitignored; add the ignore entry); (a2) a
  `precheck` subcommand run BEFORE implementation that executes the task's verify command
  against the pre-task tree and records its result — a verify that already PASSES pre-task
  is tautological by construction: precheck flags it (`tautological-verify` defect line)
  and `record` refuses a pass marker for that task until the verify command changes (red →
  green discipline, PLAN D10); (b) a
  hook entrypoint reading the PostToolUse JSON on stdin — when the edited file is a kit
  TASKS.md and the diff flips a task to `done`, exit nonzero with a one-line reason unless a
  marker newer than the task's `in-progress` flip exists. Installation is consent-gated via
  the setup-skill pattern (extend `skills/setup/SKILL.md` with an opt-in step; NEVER
  auto-write `~/.claude/settings.json`). Tripwire per PLAN Risks: if PostToolUse provably
  lacks the needed payload, STOP, write a `defect:` line, ship marker+`record` only.
- Acceptance: marker write/read round-trips in temp kit fixtures; `precheck` on a
  passing-pre-task verify emits the defect line and blocks the pass marker; hook blocks a
  marker-less `done` flip and passes a fresh-marker flip; no `Path.home()` in the new
  module; setup skill documents consent flow.
- Verify: `python3 -m unittest discover -s tests -p 'test_kit_verify_hook.py' -v`

### T5 — bin/claude_execute.py headless kit driver
- status: done
- model: sonnet
- depends: T1, T4
- Brief: Port `bin/codex_execute.py`'s structure (read it first — it is the template, as it
  was for Copilot) to a headless Claude driver: parse TASKS.md, dispatch each task via
  non-interactive `claude` invocation with the kit agent + task brief, pass the task's
  `model` pin, rerun the verify command via `kit_verify_hook.py record`, escalate blocked
  tasks one tier per the pricing.json tier order, write statuses + `outcome:` lines carrying
  `run=`/`parent=` (T1 grammar). Injectable `runner=`/`verify_runner=`, `--dry-run` prints
  argv and spawns nothing, argv lists never `shell=True`, `--claude-bin` for stubs. Dispatch
  flag surface pinned at MEDIUM confidence per PLAN Risks — one-constant correction rule.
- Acceptance: `status`/`run`/`review` subcommands mirror the sibling drivers; `--dry-run` on
  a synthetic kit prints dispatches for every pending task and writes nothing; real-dispatch
  path unreachable from tests; outcome lines carry `run=`, escalation outcomes carry
  `parent=`.
- Verify: `python3 -m unittest discover -s tests -p 'test_claude_execute.py' -v`

---

## Phase 3 — Copilot harness

### T6 — Tool scoping in the Copilot agent bundle
- status: done
- model: sonnet
- independent: yes
- Brief: Add `tools:` frontmatter pins to `copilot/.github/agents/verifier.agent.md` (read +
  shell only) and `reviewer.agent.md` (no write/edit tools), per PLAN D4/D7: cite the GitHub
  custom-agent frontmatter doc line in a comment, label the pin best-effort/NOT
  live-verified (the `--model`-precedence precedent), never invoke the real CLI to check.
  Update `tests/test_copilot_docs.py`-adjacent content checks if they assert agent file
  shape.
- Acceptance: both agent files carry a `tools:` pin + provenance comment; no other agent
  files changed; content tests updated and green.
- Verify: `python3 -m unittest discover -s tests -p 'test_copilot_docs*.py' -v`

### T7 — Id stamping + lineage in copilot_execute
- status: done
- model: sonnet
- depends: T1
- Brief: `bin/copilot_execute.py` generates one `run=` id per invocation (PLAN D8 format),
  includes `kit/run/task` ids in the dispatch prompt preamble built by `build_dispatch`, and
  writes `run=` on every `outcome:` line + `parent=<task-id>` on escalation outcomes. Ledger
  writeback stays within the T1 grammar; nothing required, everything optional.
- Acceptance: `--dry-run` argv shows the id preamble; synthetic-run tests assert `run=` on
  all outcome lines and `parent=` only on escalations; a no-op diff for kits executed with
  `--dry-run` (writes nothing) preserved.
- Verify: `python3 -m unittest discover -s tests -p 'test_copilot_execute.py' -v`

---

## Phase 4 — Codex harness

### T8 — Id stamping + lineage in codex_execute
- status: done
- model: sonnet
- depends: T7
- Brief: Port T7 verbatim in shape to `bin/codex_execute.py` (copilot_execute is the
  grammar template, per its own docstring): `run=` id per invocation, ids in the `codex
  exec` role preamble, `run=`/`parent=` on outcome writeback. No agent files; dispatch stays
  strictly sequential per PLAN D5 (state this in the docstring).
- Acceptance: mirrors T7's assertions against the codex driver's synthetic fixtures;
  sequential-only per D5 documented.
- Verify: `python3 -m unittest discover -s tests -p 'test_codex_execute.py' -v`

---

## Phase 5 — Budget, joins, docs

### T9 — Optional `budget:` block in the PLAN.md contract
- status: done
- model: sonnet
- depends: T1, T5, T7, T8
- Brief: Spec an optional PLAN.md block (like `autonomy:` — a PLAN line family, never a task
  field): `budget: max-dispatches=N max-escalations=N max-consults=N`. All three drivers +
  `skills/execute/SKILL.md` honor it when present: on exhaustion, stop cleanly, mark
  remaining tasks untouched, write one `outcome: result=budget-stop` line (with `run=`),
  never hide the stop behind a fluent summary. Absent block = today's behavior everywhere.
- Acceptance: each driver's synthetic test proves the stop at the cap and the
  `budget-stop` ledger line; execute SKILL.md documents the block; architect SKILL.md
  mentions it as optional PLAN content (sync invariant).
- Verify: `python3 -m unittest discover -s tests -p 'test_*_execute.py' -v && grep -q 'budget:' skills/execute/SKILL.md`

### T10 — Usage reports join the ledger by run id
- status: done
- model: sonnet
- depends: T7, T8
- Brief: `bin/copilot_usage.py` and `bin/codex_usage.py` gain an optional `--kits-dir` join:
  where a session's time window overlaps a ledger `run=` id's outcomes, annotate the session
  row with kit/task attribution — honestly labeled `(ledger join, time-window match)` and
  degrading to today's output when no ledger or no overlap exists. Strictly read-only over
  home dirs as today; ledger read is the only new input.
- Acceptance: synthetic fixtures with and without matching ledgers produce annotated and
  unannotated rows respectively; no home-dir writes; labels present verbatim.
- Verify: `python3 -m unittest discover -s tests -p 'test_copilot_usage.py' -v && python3 -m unittest discover -s tests -p 'test_codex_usage.py' -v`

### T11 — Escalation-rate alarm in scorecard trend + statusline
- status: done
- model: sonnet
- depends: T2
- Brief: Per PLAN D11, escalation rate is a live cost variable — a drifting verify command
  can silently escalate everything up the ladder. `routing_scorecard --trend` computes a
  trailing escalation-rate baseline from history and flags a current kit whose rate exceeds
  it by a data-derived threshold (no hardcoded constant — derive from history variance;
  degrade honestly with a "insufficient history" line when too few kits exist).
  `bin/statusline.py` gains an optional compact alarm segment sourced from the same
  computation (read-only; appears only when a live kit trips the threshold). No behavior
  change to routing or escalation — alarm and evidence only.
- Acceptance: synthetic multi-kit fixtures with a spiking kit trip the alarm; stable
  fixtures don't; sparse history prints the honest fallback; statusline segment renders
  only on trip; no new hardcoded thresholds.
- Verify: `python3 -m unittest discover -s tests -p 'test_routing_scorecard.py' -v && python3 -m unittest discover -s tests -p 'test_statusline.py' -v`

### T12 — docs/GRAPH-ENGINEERING.md positioning doc
- status: done
- model: haiku
- independent: yes
- Brief: One doc mapping the repo to the graph-engineering vocabulary: the four graph types
  vs repo components; the harness convergence table from PLAN.md; what was deliberately
  rejected (knowledge graph, framework port, driver fan-out) and why; pointers into
  HOW-IT-WORKS.md. Add a one-line README pointer next to the other doc links. Prose, no
  prices, no model ids.
- Acceptance: doc exists, README links it, no pricing content, cross-links resolve.
- Verify: `test -f docs/GRAPH-ENGINEERING.md && grep -q 'GRAPH-ENGINEERING' README.md && python3 -m unittest discover -s tests`
