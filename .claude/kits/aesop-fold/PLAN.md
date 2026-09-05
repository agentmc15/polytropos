# aesop-fold — evaluate aesop, fold its durable core into polytropos as the AI-primitive foundation

autonomy: advisory
budget: max-dispatches=24 max-escalations=2 max-consults=2
roles: test-author

## Goal

aesop (`/path/to/aesop`, TypeScript, idle since 2026-07-30, never
published to npm, zero runtime coupling with this repo in either direction) was built as an
"environment compiler" — but its enduring idea, the one the user named as the original plan, is
the **AI primitive management system**: nine converged primitives (instructions, skills,
subagents, commands, MCP, hooks, permissions, loops/goals, state), one manifest describing them,
and a per-harness matrix saying what each harness supports natively and what needs a fallback.

This kit does three things, in this order of weight:

1. **Evaluate** aesop capability by capability and record a fold / defer / port-the-research /
   drop verdict for each (the table in *Evaluation* below), independently re-verified against
   the aesop source at execution time (T1). The user has NOT decided aesop's fate; this record
   is what lets them decide.
2. **Fold the durable core** into polytropos as stdlib Python + data: the nine-primitive model,
   the six-harness matrix (Cursor column included, so the later Cursor work is a data-driven
   port), aesop's locked manifest schema (vendored verbatim), and a read-only engine
   `bin/primitives.py` that validates a manifest and previews what each harness would get.
3. **Resolve the manifest format**: TOML via stdlib `tomllib`, which means correcting the
   documented Python floor from 3.8 to 3.11 (a doc correction — shipped code already requires
   3.11) and converting this repo's one manifest, `copilot/aesop.yaml`, to `copilot/aesop.toml`.

Explicitly NOT this kit: building Cursor support (user: "not now"), porting the six emitters,
the fence/lock/sync machinery, federation, or any edit to the aesop repo.

## Definition of done (every line checkable)

- `python3 -m unittest discover -s tests` — baseline at architect time: **3034 tests**; two
  consecutive full runs, the first with 1 failure and the second fully clean, so the baseline is
  green with one transient failure on record (see *Risks* R1). Done = no new failure or error,
  and every new test file green.
- `.claude/kits/aesop-fold/EVALUATION.md` exists with 19 `### E<n>` sections, each carrying a
  `verdict-check:` line written by an opus re-verifier that read the aesop source itself.
- `SETUP.md` states `python3` `3.11+`; `tests/test_python_floor.py` exists and passes; no
  tracked doc/skill/bundle file mentions a 3.8 or 3.10 floor.
- `primitives/model.json`, `primitives/harness-matrix.json`, `primitives/aesop.schema.v1.json`
  exist; the schema copy's sha256 is
  `a8b5ce94dda62c547728fea03335b22bb877c70426b1ce2eee9cce23f62b2f4f` (byte-identical to aesop
  `schemas/aesop.schema.json` at commit `9c4108ee8ca32fe7f7420a94b15b072c92a6ccf8`).
- `python3 bin/primitives.py check copilot/aesop.toml` exits 0; the adversarial fixtures in
  `tests/test_primitives.py` each exit 2 with the pinned finding code.
- `python3 bin/primitives.py plan copilot/aesop.toml --harness cursor` prints all nine
  primitives with cursor support values matching aesop's `cursor.ts` `capabilities()`
  (native: instructions, mcp, state; everything else fallback; goal mode ralph).
- `copilot/aesop.yaml` no longer exists; `copilot/aesop.toml` does; `tests/test_copilot_bundle.py`
  parses it with `tomllib` and every one of its original test methods still exists and passes.
- `docs/PRIMITIVES.md` exists, is in `mkdocs.yml` nav, embeds the matrix between
  `<!-- primitives:matrix:begin -->` / `<!-- primitives:matrix:end -->` markers byte-equal to
  `python3 bin/primitives.py matrix --markdown`, and `python3 bin/docs_build.py check` exits 0.
- `python3 bin/copilot_docs.py check` exits 0 (its manifest lists the renamed bundle file).
- `CLAUDE.md` carries one `bin/primitives.py` run line and stays ≤ 16000 bytes.
- `git -C /path/to/aesop status --porcelain` is empty at the end of
  every task (aesop untouched).

## Constraints and out-of-scope fence

- **No Cursor implementation.** No `cursor/` bundle dir, no `.cursor/rules` emission, no `.mdc`
  writer, no Cursor install path in `bin/harness_select.py`. The matrix's cursor column and
  `plan --harness cursor` are the whole of this kit's Cursor deliverable.
- **aesop is read-only.** Tasks may read any file under `/path/to/aesop`
  and copy content into this repo with provenance; nothing writes there. Aesop-side changes
  are proposals in *Proposals for the aesop repo* below, never tasks.
- **Python is stdlib-only** in `bin/` and `tests/` — `tomllib` and `json` are the parsers; no
  YAML library exists or is added; no pip, no requirements, no pytest.
- **No emitters, no fences, no lockfile, no `sync`, no federation, no `init`/`detect`.** Only
  what the evaluation table marks *fold now* lands as code.
- **Every invariant in `/path/to/polytropos/CLAUDE.md` binds**,
  notably: pricing files are the only numeric truth (this kit never reads or writes any
  `data/pricing*.json` and hardcodes no price, model id, or date into code); never invoke the
  real `claude`/`copilot`/`codex`/`gh` CLI; never touch `~/.claude` or anything outside this
  repo; do not commit or push; generated docs pages are never hand-edited — edit the source and
  run `python3 bin/docs_build.py build`; the architect/execute kit contract is untouched.
- **Root `/AGENTS.md` is gitignored in this repo** (Codex install destination). Never create one.
- **`README.md` is not edited by this kit** (it carries uncommitted user work at architect time;
  `docs/PRIMITIVES.md` plus the mkdocs nav are the discovery surface).
- **`anthro-optimizer/copilot/aesop.yaml` is out of scope entirely** — a different, dead repo.
- **`aesop`'s own YAML manifests stay YAML.** aesop reads YAML; this repo never runs aesop; the
  TOML dialect is this repo's authoring form for the same v1 schema.

## Architecture and key decisions

**D1 — Fold the model, not the compiler.** aesop's 3,853 lines split into (a) a primitive
model + schema + harness matrix — pure spec, ~zero code — and (b) machinery that turns a manifest
into native files and keeps them in sync (emitters 631 lines, render/sync/compile/lock ~576,
federation/registry/add/update ~725, init/detect/interview ~480, CLI shell 303). Nobody consumes
(b): this repo hand-authors its Copilot and Codex bundles and enforces manifest ↔ bundle
consistency by unittest (`tests/test_copilot_bundle.py`, `tests/test_codex_*.py`), and that
pattern has held across five kits. (a) is what the user called the original plan. So (a) lands
as data under `primitives/` plus a read-only engine, and (b) is deferred or dropped per the
table. Why data and not a Python class hierarchy: the model must be readable by a human, a
test, a docs generator, and a future Cursor emitter alike — JSON is the one form all four share.

**D2 — Manifest format is TOML via stdlib `tomllib`; the Python floor is 3.11 (user decision,
2026-09-04: "lets raise the floor from 3.8 to 3.11").** This is a documentation correction, not
a new constraint — every claim below was re-checked in the tree at architect time:
`bin/sync_codex_surfaces.py` raises `RuntimeError("Python 3.11+ tomllib is required to generate
agent prompt mirrors")` when `tomllib` is missing; `bin/harness_select.py` imports `tomllib`
with a fallback commented "Python 3.11+ in supported Codex environments";
`docs/CODEX-HARNESS.md`, `docs-site/deep-dives/codex-harness.md`, and
`docs-site/getting-started/codex.md` all instruct "Use Python 3.11 or newer";
`.github/workflows/docs-site.yml` pins `python-version: "3.12"`;
`tasks/kits/codex-skill-discovery/NOTES.md` records "System Python 3.9 lacks tomllib; verified
commands use Python 3.12 on PATH"; the local interpreter is 3.12.7. The ONLY 3.8 mention in the
tracked tree is `SETUP.md:16` (`| \`python3\` (3.8+) |`), which contradicts shipped code.
Raising the floor also unlocks the one stdlib structured-config parser that carries comments,
nested tables, arrays of tables, and multi-line strings — everything aesop's v1 schema needs.
`tests/test_python_floor.py` makes the floor loud (the suite fails on < 3.11 with a message
naming SETUP.md) and sweeps for stale floor claims.

**D3 — `tomllib` is read-only, and so is this kit's engine; manifests are hand-authored and
never written by code.** There is no stdlib TOML writer. Rather than hand-roll a serializer, the
design guarantees writes never happen: `bin/primitives.py` has no command that modifies a
manifest; its machine-readable output is `--json` on stdout. Comments survive precisely because
the file is only ever read — the load-bearing header of `copilot/aesop.yaml` becomes `#`
comments in `copilot/aesop.toml`, preserved verbatim by the human who converts it (T6). A future
kit that needs to write manifests (an `add`-style command) must hand-roll a serializer for the
v1 subset and round-trip-test it against comments; that is recorded here so no executor
improvises one now.

**D4 — Convert `copilot/aesop.yaml` to `copilot/aesop.toml` in this kit; same v1 schema, TOML
dialect.** The engine can only read TOML, and a primitive-management system that cannot read
the repo's one manifest would be a demo. `tests/test_copilot_bundle.py` — self-described as
"the enforcement mechanism standing in for `aesop compile`" — keeps every test method and
assertion but loads the manifest with `tomllib`, deleting its line-oriented YAML text helper
(`_extract_yaml_list_block`; no other file uses it). The name keeps `aesop` because the schema
is aesop's v1 (vendored, D5); the extension signals the dialect. References to the file in
`docs/COPILOT-PARITY.md`, `docs/COPILOT-HARNESS.md`, `docs/HOW-IT-WORKS.md`, and
`copilot-docs/manifest.json` (whose `bundle` source list is existence-checked by
`bin/copilot_docs.py`) are renamed; generic references to aesop's root `aesop.yaml` concept
(`docs/GUIDE.md`, `skills/architect/SKILL.md`, `skills/execute/SKILL.md`, `bin/aesop_bridge.py`)
are NOT touched — they describe aesop, not this file. Historical kit records under
`.claude/kits/*` and `tasks/kits/*` are never rewritten.

**D5 — Vendor aesop's LOCKED schema verbatim and make the validator read it.** The engine has no
JSON-Schema validator (none in stdlib), so `check` is a hand-written rule set — but its enums and
regex patterns (harness ids, tiers, effort levels, transport, trust, unattended, scope pattern,
name patterns) are read from `primitives/aesop.schema.v1.json` at run time, not retyped. A test
pins the vendored file's sha256 so nobody edits the locked schema by accident, and the rules that
aesop enforces in code rather than schema (judge family ≠ primary family, three hard stops never
defaulted, env var NAMES only, path-safe names, secret patterns) are pinned in T4's brief.

**D6 — Exit codes mirror aesop's: 0 ok · 1 usage/IO error · 2 validation findings.** Same
convention the user already knows from `aesop`, and `2` for "the manifest is wrong" keeps CI
scripts simple. `plan` and `matrix` never exit 2 except for an unknown `--harness`.

**D7 — Cursor-ready, not Cursor-built.** The matrix's cursor column is pinned cell-for-cell to
aesop `src/emitters/cursor.ts` `capabilities()` and its emit paths (`.cursor/rules/00-aesop.mdc`,
`.cursor/rules/scoped-<glob>.mdc`, `.cursor/rules/skill-<name>.mdc`, `.cursor/mcp.json`;
fallbacks `.aesop/roles/<name>.md`, `.aesop/prompts/<name>.md`). `plan --harness cursor` works on
any manifest even when cursor is not declared, so the user can see today what Cursor would get.
The future Cursor kit then has a defined shape: a `cursor/` bundle dir following the `copilot/`
and `codex/` pattern, targets taken from the matrix, an install path in `harness_select.py`, and
— only if wanted — an 81-line port of `cursor.ts`. None of that is here.

**D8 — `docs/PRIMITIVES.md` is the human surface, with a drift test.** Every `docs/*.md` is
mirrored by `bin/docs_build.py` into the public site and must appear in `mkdocs.yml` nav
(`tests/test_docs_site.py` enforces both), so a docs task always ends with `docs_build.py build`
staged together. The matrix table inside the doc is generated by `matrix --markdown` and
compared byte-for-byte by a test — the doc cannot silently drift from the data.

**D9 — Role pins come from this repo's own ledger, not the skill defaults.**
`python3 bin/routing_scorecard.py --history`: 224/249 first-try across 32 kits, zero escalations
at every tier. Role precision: verifier on haiku 60% (26 events) vs verifier on sonnet 89% (60
events) → the verifier is pinned **sonnet**, overriding the skill's haiku default. Reviewer on
opus 81% precision (34 events, 211/260 confirmed) → reviewer stays **opus**. `--roles`:
test-author 16 dispatches, 83% precision, 88% marginal rate → `roles: test-author` is declared.
docs-editor (17% precision, insufficient sample) is not declared; scout / second-verifier /
red-team / security-auditor / synthesizer have zero recorded dispatches and nothing in this kit
specifically tests them, so none is declared.

**D10 — The evaluation is checked by a different model than the one that wrote it.** The table
below is the architect's claim. T1 (opus, read-only against aesop) re-verifies every row and
writes `EVALUATION.md`; a `contradicted` row is a `stale-plan-decision` finding for the
orchestrator, and the user reads EVALUATION.md, not this table, when deciding aesop's fate.

## Evaluation — aesop capability by capability

All line counts are `wc -l` of non-test TypeScript at aesop commit `9c4108ee8ca32fe7f7420a94b15b072c92a6ccf8`
(2026-07-30). Verdict vocabulary: **fold now** · **fold later** · **port research** · **already
present** · **drop**. "polytropos state" names the file that already covers the ground, if any.

| id | aesop capability (source, lines) | polytropos state | verdict | rationale |
|---|---|---|---|---|
| E1 | Nine-primitive model — `docs/04-primitives.md`, `src/types.ts` (153, LOCKED) | none | **fold now** → `primitives/model.json`, `docs/PRIMITIVES.md` | The original plan; pure spec; no TypeScript needed to carry it. |
| E2 | Harness matrix incl. Cursor — `docs/03-harness-matrix.md` + each emitter's `capabilities()` and emit paths | none | **fold now** → `primitives/harness-matrix.json` | The highest-value portable research for the user's Cursor goal; data, not code. |
| E3 | Manifest schema — `schemas/aesop.schema.json` (LOCKED v1) | `copilot/aesop.yaml` conforms informally | **fold now** → vendored verbatim as `primitives/aesop.schema.v1.json` | The contract every manifest already follows; vendoring keeps enums/patterns authoritative. |
| E4 | Manifest load + validate — `src/manifest.ts` (87), doctor's static checks (`schema`, `secret`, `judge-family`, `state-dir`, TODO placeholder), `src/safety.ts` (44) | `tests/test_copilot_bundle.py` (plain-text parse, bundle-specific) | **fold now** → `bin/primitives.py check` | Validation is what makes a manifest a management system rather than a note; stdlib `tomllib` + hand rules suffice. |
| E5 | Capability planning — the `compile --verbose` per-harness native/fallback listing | none | **fold now** → `bin/primitives.py plan` | Answers "what would Cursor get?" today without emitting a byte. |
| E6 | Emitters — `src/emitters/{claude-code 167, codex 89, antigravity 87, copilot 82, cursor 81, vscode 57, shared 68}` | hand-authored `copilot/.github/`, `codex/` + unittest enforcement | **fold later** (Cursor kit decides) | This repo's proven model is hand-author + test-enforce; when Cursor arrives, `cursor.ts` is an afternoon's port from the matrix data. |
| E7 | Fences, lockfile, `sync`, `--write-back` — `src/render.ts` (198), `src/commands/sync.ts` (178), lock handling in `compile.ts` (200) | drift caught by unittest instead | **drop** | polytropos never had compiled output to fence; a lockfile without a compiler is dead weight. |
| E8 | Doctor dynamic checks — run the test command, MCP handshake, YOLO scan, harness-version freshness (`doctor.ts` 205 minus E4's static part) | `bin/harness_update.py check` covers install freshness | **drop** | CLAUDE.md forbids CLI invocation from verify paths; the static half is E4. |
| E9 | Init / detect / interview / `importExisting` — `init.ts` 173, `detect.ts` 210, `interview.ts` 97, per-emitter importers | none | **drop** (note `cursor.importExisting` as Cursor-kit reference) | Manifests here are authored, not detected; one manifest exists. |
| E10 | Federation / registry / add / remove / list / update — `federation.ts` 264, `registry.ts` 166, `add.ts` 181, `update.ts` 114 | `bin/harness_select.py` installs bundles; `skills/<name>` layout stays aesop-lookup-compatible for free | **drop** | No registry consumer exists on this machine; vendoring content into `.aesop/vendor/` solves a problem this repo does not have. |
| E11 | Loops — `src/loops/ralph.ts` (126), `commands/goal.ts` (106), `registry/loops/` | `bin/copilot_ralph.py` (ported from aesop@5506617, pricing-fed) | **already present**; goal-recipe validation (three stops) folds into E4 | `goal new/show/list` are manifest editing (D3 forbids writes) and doc rendering — dropped. |
| E12 | Lessons — `commands/lessons.ts` (45) | `bin/lessons_promote.py` (JSONL `tasks/lessons.md`, kit-recurrence gate) | **already present** | Different and richer semantics here; nothing to fold. |
| E13 | Pathway profiles — `src/profile.ts` (125), `profiles/*.yaml`, `docs/05-pathways.md` | routing tiers, effort dial, `task_profiles` in pricing data, measured by the ledger | **port research** (one paragraph in `docs/PRIMITIVES.md`) | Fixed calibrations lose to measured routing; keep the idea (cost/accuracy dial with stops that never switch off), not the YAML. |
| E14 | Bundle — `commands/bundle.ts` (96) | this repo IS a Claude plugin (`.claude-plugin/`), plus Copilot/Codex bundles | **drop** | Distribution already exists per harness. |
| E15 | MCP server mode — `commands/mcp.ts` (118) | none | **drop** | Nothing to expose; `--json` on the engine is the agent-facing surface. |
| E16 | Eject — `commands/eject.ts` (33) | none | **drop** | Nothing compiled to eject. |
| E17 | Registry content seeds — `registry/instructions/AGENTS.template.md` (161 lines), 8 agents, 4 commands, 2 hook specs, skills | own `skills/`, own `CLAUDE.md` doctrine | **fold later**, selectively | The hook specs (`block-dangerous-commands`, `format-on-write`) are the best candidates for a future hooks/permissions primitive task; the instruction template duplicates CLAUDE.md. |
| E18 | Provenance already crossed — Ralph runner port note in `bin/copilot_ralph.py`; tier/tick/runway math in `bin/aesop_bridge.py` | present | **already present** | `aesop_bridge.py` stays as is: it computes from pricing data and imports nothing. |
| E19 | CLI shell — `src/index.ts` (303) | `bin/primitives.py` argparse | **drop** | Replaced by the four subcommands in E4/E5 plus `model`/`matrix`. |

**Net:** five rows fold now (E1–E5), two fold later (E6, E17), one ports research (E13), three
are already present (E11, E12, E18), eight drop. Lines that land as new code: one engine file
(target ≤ ~450 lines) plus tests and three data files — not a compiler.

### Documents this kit supersedes

- `docs/AESOP-COMPILE-PROPOSAL.md` — **superseded.** It specified making `copilot/aesop.yaml` an
  `aesop compile` target with golden fixtures on the aesop side, naming a future architect run in
  the aesop repo as its consumer. This kit's direction folds validation into polytropos and never
  compiles; the extension question it argued (`.agent.md`) was already settled upstream (aesop PR
  #1) and is moot here. T7 adds a dated status note at its top; the body stays as history.
- `docs/AESOP-INTEGRATION.md` — **partially superseded.** Registry consumption of `route` /
  `fable-check` and `bin/aesop_bridge.py` remain accurate for anyone still running aesop; the
  "Kits in aesop-managed projects" rules remain in force (a root `aesop.yaml` still marks a
  managed target). Its "Proposed aesop-side follow-ups" are deprioritized by the verdict table.
  T7 adds a dated status note pointing to `docs/PRIMITIVES.md` and the manifest rename.

### What this leaves for the user to decide about aesop

After this kit, aesop's remaining unique value is exactly the machinery marked *fold later* or
*drop* — emitters, sync, federation — none of which has a consumer. Three coherent options, none
pre-empted here: **freeze** (no new phases; keep as the reference for the Cursor kit's optional
emitter port — recommended until that kit is planned), **archive** (README pointer to
`docs/PRIMITIVES.md`; safe once EVALUATION.md confirms E1–E5 landed), or **keep building** (only
worth it if a second consumer appears). `EVALUATION.md` is the document to read before choosing.

## Proposals for the aesop repo (not tasks — the user approves separately)

1. If aesop is kept: add a `README.md` line pointing to `polytropos/docs/PRIMITIVES.md` as the
   primitive model's living home, and mark `docs/08-roadmap.md` frozen at Phase 7.
2. If aesop is kept and Cursor support is later built here: nothing — this repo owns the port.
3. `.cursor/rules/00-aesop.mdc` in aesop's own compiled output is the only real Cursor artifact
   on this machine; keep it unmodified as the reference sample the Cursor kit will compare
   against.

## Cursor readiness (recorded for the later kit; nothing here is built now)

From the matrix (aesop `cursor.ts`, pinned July 2026): instructions native as
`.cursor/rules/*.mdc` (frontmatter `description`, `globs`, `alwaysApply`; path-scoped via
`globs`); MCP native as `.cursor/mcp.json` (`mcpServers` key, Claude-style shape); state native
(`tasks/`); skills → fallback rule `.cursor/rules/skill-<name>.mdc` using the description as the
trigger; subagents → fallback role prompts `.aesop/roles/<name>.md`; commands → fallback
`.aesop/prompts/<name>.md`; hooks → unpinned, fallback; permissions → app settings, not emitted;
loops → no `/goal`, Ralph runner. The future kit's shape: `cursor/` bundle dir (pattern:
`copilot/`, `codex/`), `bin/harness_select.py install --harness cursor`, a
`tests/test_cursor_bundle.py` enforcing manifest ↔ bundle exactly as the Copilot one does, and a
`copilot_ralph.py`-style driver only if Cursor exposes a headless CLI worth driving (insufficient
evidence today — verify before planning).

## Risks and tripwires

- **R1 — In-flight uncommitted work in the working tree.** At architect time `git status` showed
  modifications to `README.md`, `SETUP.md`, `bin/harness_select.py`, `bin/harness_update.py`,
  `codex/AGENTS.md`, `docs/CODEX-HARNESS.md`, two `docs-site/` Codex pages, and
  `tests/test_codex_core_skills.py` / `tests/test_codex_onboarding_e2e.py`; one full-suite run
  showed a single transient failure and the next was clean. Tripwire: before editing any file, run `git status --porcelain -- <file>`;
  if it is already modified, make only the surgical edit the brief names and REPORT the
  pre-existing modification in the done report. Never `git stash`, `checkout`, `reset`, or
  otherwise alter another change. Record the suite baseline (count + named failures) in
  NOTES.md at run start; "green" for this kit means no new failure/error.
- **R2 — TOML table ordering.** In TOML a table cannot be reopened: every plain key of
  `[primitives]` (`skills`, `agents`, `commands`, `hooks`, `mcp = []`, `loops = []`) must be
  written BEFORE any `[primitives.instructions]` / `[[primitives.instructions.blocks]]` /
  `[[primitives.mcp]]` / `[primitives.permissions]` / `[[primitives.loops]]` section. Tripwire:
  `tomllib.TOMLDecodeError` mentioning "Cannot declare ... twice" → reorder, do not restructure.
- **R3 — docs drift.** Any edit to `docs/*.md` or `mkdocs.yml` without `python3 bin/docs_build.py
  build` fails `tests/test_docs_site.py`. Tripwire: `docs_build.py check` nonzero → run `build`
  in the same task and stage the generated pages together. Never hand-edit `docs-site/skills/**`
  or `docs-site/deep-dives/**`. Two docs-touching tasks must never run concurrently.
- **R4 — Interpreter on PATH.** `python3` here is 3.12.7. If a runner's `python3` is < 3.11,
  `tests/test_python_floor.py` fails by design; the remedy is a 3.11+ interpreter, never a test
  edit. Do not add `try: import tomllib` fallbacks to new code.
- **R5 — CLAUDE.md byte ceiling.** 15568 of 16000 bytes used at architect time. T9's single line
  must keep the file ≤ 16000 (`tests/test_guardrails_layout.py`). Nothing else in this kit
  touches CLAUDE.md.
- **R6 — Stale pins.** This plan pins content and counts, not line numbers, except where a brief
  quotes a line for identification. If a quoted anchor is not found verbatim, stop and report
  (`stale-pin`), do not guess a neighbor.
- **R7 — Name collisions.** Agent files are `aesop-fold-*`; the aesop manifests on this machine
  list agents `explorer`, `verify-app`, `spec-reviewer` (aesop's own) and `route`, `architect`,
  `implementer`, `verifier`, `reviewer`, `usage`, `context-weight`, `bench-routing`, `journal`,
  `frontier-check`, `escalate`, `effort` (this repo's Copilot manifest). None collides.
- **R8 — `tests/fixtures/` is new.** unittest discovery only loads `test_*.py`, so a fixtures
  directory is inert; keep fixture files small and free of prices, model ids, home paths.
- **R9 — Secret-pattern false positives.** The `check` secret scan (aesop's four regexes) runs
  over the raw manifest text; a doc-like comment containing `sk-` + 20 chars would trip it. The
  converted `copilot/aesop.toml` must not contain such strings — if `check` reports `secret` on
  it, fix the comment wording, never weaken the pattern.
