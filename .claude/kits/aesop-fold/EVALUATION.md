# aesop-fold — evaluation record

Independent re-verification of PLAN.md's *Evaluation* table (rows E1–E19), performed 2026-09-04
by an opus checker reading the aesop source directly (PLAN D10). Observed aesop HEAD:
`9c4108ee8ca32fe7f7420a94b15b072c92a6ccf8` — identical to the SHA PLAN.md pins, so every line
count and behavior claim below was checked against exactly the tree the architect described.
Observed polytropos HEAD: `5066739c8f8dbe319e9d4b0490d2820a9f5b65ac`. Every `wc -l` cited in the
table was re-run; all 29 non-test TypeScript files total 3853 lines, matching PLAN D1. This task
read only: nothing was written to the aesop repo, no `npm`/`node`/`tsc` was invoked, and no
`data/pricing*.json` value was read (E13 checked key presence only).

### E1 — Nine-primitive model — `docs/04-primitives.md`, `src/types.ts` (153, LOCKED)

- `docs/04-primitives.md` carries exactly nine numbered sections, `## 1. Instructions` through
  `## 9. State & memory`; `## Plugins (distribution, not a primitive)` is explicitly excluded.
- `wc -l src/types.ts` = **153** (claim 153, delta 0). Line 2 reads
  `* Aesop core interfaces — LOCKED AT PHASE 0.`; aesop's own `AGENTS.md:178` repeats the lock.
- The `PrimitiveType` union in `types.ts` has exactly nine members: instructions, skill, agent,
  command, mcp, hook, permissions, loop, state — matching the doc one-for-one.
- polytropos state "none" holds: no `primitives/` directory, no `docs/PRIMITIVES.md`, and no
  hit for "nine primitive(s)" anywhere under `docs/` or the root `*.md` files.

verdict-check: confirmed

### E2 — Harness matrix incl. Cursor — `docs/03-harness-matrix.md` + each emitter's `capabilities()` and emit paths

- `docs/03-harness-matrix.md` (146 lines) ends in a "Capabilities summary (tested cell-for-cell)"
  table with one row per harness; I read all six `capabilities()` implementations and every cell
  matches (e.g. `vscode` native `mcp, state`; `antigravity` goalMode `scheduled`).
- The cursor row matches PLAN's *Cursor readiness* section exactly: `cursor.ts` returns
  `native: ["instructions", "mcp", "state"]`, fallbacks for skill/agent/command/hook/permissions/loop,
  `goalMode: "ralph"`.
- Emit paths confirmed in `cursor.ts`: `.cursor/rules/00-aesop.mdc`, `.cursor/rules/scoped-<glob>.mdc`,
  `.cursor/rules/skill-<name>.mdc`, `.cursor/mcp.json`; `shared.ts:32` emits `.aesop/roles/<name>.md`
  and `shared.ts:41` `.aesop/prompts/<name>.md` — matching PLAN D7 cell for cell.
- polytropos state "none" holds: the only "harness-matrix" hits are five lines in
  `docs/AESOP-COMPILE-PROPOSAL.md` describing aesop's doc-first *process*, not its cells.

verdict-check: confirmed

### E3 — Manifest schema — `schemas/aesop.schema.json` (LOCKED v1)

- `shasum -a 256 schemas/aesop.schema.json` =
  `a8b5ce94dda62c547728fea03335b22bb877c70426b1ce2eee9cce23f62b2f4f`, byte-identical to the sha256
  PLAN.md's definition-of-done pins for the vendored copy.
- Schema line 5 description: "v1 — LOCKED at Phase 1 (2026-06-10). Changes from here are breaking
  changes: flag and stop for approval."
- polytropos `copilot/aesop.yaml` opens `version: 1` with `project` / `harnesses` / `pathway` keys
  and a header stating "`aesop compile` is NOT run in this repo" — "conforms informally" holds.

verdict-check: confirmed

### E4 — Manifest load + validate — `src/manifest.ts` (87), doctor's static checks (`schema`, `secret`, `judge-family`, `state-dir`, TODO placeholder), `src/safety.ts` (44)

- `wc -l src/manifest.ts` = **87**, `wc -l src/safety.ts` = **44** (claims 87 / 44, delta 0).
- `manifest.ts` compiles the schema with Ajv2020 and adds the cross-field rule
  "judge.family must differ from primary.family (the maker must not grade its own work)";
  `safety.ts` supplies `isSafeName` / `assertSafeName` / `safeNameOr` / `assertWithinRepo`.
- `doctor.ts` lines 26–33 declare the `Finding.code` union; it contains `schema`, `secret`,
  `state-dir` and `judge-family` as claimed, and `doctor.ts:97` is the TODO placeholder check
  `if (!testCmd || testCmd.startsWith("TODO"))`.
- polytropos state holds: `tests/test_copilot_bundle.py:3` self-describes as "the enforcement
  mechanism standing in for `aesop compile`" and parses the manifest as plain text via
  `_extract_yaml_list_block`.

verdict-check: confirmed

### E5 — Capability planning — the `compile --verbose` per-harness native/fallback listing

- `compile.ts:110-114` is the whole of `--verbose`: `for (const [prim, why] of
  Object.entries(emitter.capabilities().fallback)) notes.push(...)`. It emits **fallback lines
  only** — no native primitive is ever printed by `compile`.
- The actual per-harness native/fallback listing lives in a different command:
  `doctor.ts:180-186` (`aesop doctor --matrix`) renders
  `${h}: goal=${caps.goalMode} native=[...] fallback=[...]` for each declared harness.
- Grep for "native" across `src/commands/` and `src/index.ts` returns only doc strings otherwise,
  so `compile --verbose` has no second native-printing path I missed.
- polytropos state "none" holds: `bin/primitives.py` does not exist and no equivalent surface does.

verdict-check: contradicted — the native/fallback listing is `doctor --matrix` (`doctor.ts:180-186`), not `compile --verbose`, which prints fallback lines only; the source citation is wrong even though the capability exists in aesop and the *fold now* verdict is unaffected.

### E6 — Emitters — `src/emitters/{claude-code 167, codex 89, antigravity 87, copilot 82, cursor 81, vscode 57, shared 68}`

- `wc -l` re-run on all seven: claude-code **167**, codex **89**, antigravity **87**, copilot **82**,
  cursor **81**, vscode **57**, shared **68** — every count exact, delta 0.
- polytropos state holds on the hand-authored side: `copilot/.github/` contains `agents/`,
  `skills/`, `copilot-instructions.md`; `codex/` contains `AGENTS.md`, `agents/`, `prompts/`, `skills/`.
- The unittest enforcement is real: `tests/test_copilot_bundle.py` plus eighteen
  `tests/test_codex_*.py` files.

verdict-check: confirmed

### E7 — Fences, lockfile, `sync`, `--write-back` — `src/render.ts` (198), `src/commands/sync.ts` (178), lock handling in `compile.ts` (200)

- `wc -l`: render.ts **198**, sync.ts **178**, compile.ts **200** — all exact, delta 0.
- `render.ts:1` is "Shared rendering: the canonical AGENTS.md, goal recipes, and fence handling for
  managed files"; the fence regex is `<!-- aesop:begin v1 sha256:[0-9a-f]{64} -->…<!-- aesop:end -->`.
- Lock handling is in `compile.ts:151-178`: it builds a `lockFiles` path→sha256 map and writes
  `.aesop/lock.json`.
- `sync.ts:2` documents "`--write-back` lifts in-fence AGENTS.md edits into the manifest", and
  `sync.ts:108` implements it. polytropos has no compiled output to fence — claim holds.

verdict-check: confirmed

### E8 — Doctor dynamic checks — run the test command, MCP handshake, YOLO scan, harness-version freshness (`doctor.ts` 205 minus E4's static part)

- `wc -l src/commands/doctor.ts` = **205** (claim 205, delta 0), and the test command really is
  executed: `doctor.ts:103` `await exec(testCmd, {…, shell: true})` behind `--no-exec`.
- "MCP handshake" is not implemented. `doctor.ts:109` says so in the code itself: "MCP health
  (binary resolution; a real handshake probe arrives with federation, Phase 5)"; the check is a
  `command -v` / `where` PATH lookup for the server binary (`doctor.ts:112-123`).
- "harness-version freshness" does not exist anywhere in `doctor.ts`. The only `--matrix` code
  (`doctor.ts:180-186`) prints `capabilities()` under the header "compare against
  docs/03-harness-matrix.md" — it reads no harness version and applies no age threshold. The
  90-day freshness behavior is promised only by `docs/03-harness-matrix.md`, not built.
- polytropos state holds: `bin/harness_update.py` is a read-only freshness `check` across the
  three harnesses (exit 3 on drift).

verdict-check: contradicted — two of the four enumerated dynamic checks are absent from `doctor.ts`: there is no MCP handshake (the code comment defers it to Phase 5; it is a PATH lookup) and no harness-version freshness check at all (only aesop's matrix doc promises it); the *drop* verdict is unaffected.

### E9 — Init / detect / interview / `importExisting` — `init.ts` 173, `detect.ts` 210, `interview.ts` 97, per-emitter importers

- `wc -l`: init.ts **173**, detect.ts **210**, interview.ts **97** — all exact, delta 0.
- `importExisting` is defined in all six emitters (grep -l over `src/emitters/*.ts` returns
  claude-code, codex, copilot, antigravity, vscode, cursor), so "per-emitter importers" holds.
- The Cursor-kit reference the row flags is real: `cursor.ts` `importExisting` reads
  `.cursor/rules/*.mdc` files back into `{ primitives: { instructions: { blocks } } }`.
- polytropos state "none" holds: no detect/init/interview surface exists in `bin/`.

verdict-check: confirmed

### E10 — Federation / registry / add / remove / list / update — `federation.ts` 264, `registry.ts` 166, `add.ts` 181, `update.ts` 114

- `wc -l`: federation.ts **264**, registry.ts **166**, add.ts **181**, update.ts **114** — all exact.
- `federation.ts:1-3` confirms the vendoring model the rationale rejects: "vendor the result into
  the project (.aesop/vendor/ — tracked, reviewable, SHA-pinned)".
- polytropos state holds: `bin/harness_select.py` documents
  `install --harness {claude-code,copilot,codex}` as the bundle installer.
- The skills-layout claim holds: `skills/<name>/SKILL.md` (14 skills, e.g. `skills/architect/SKILL.md`,
  `skills/route/SKILL.md`) is the same shape aesop's registry resolves.

verdict-check: confirmed

### E11 — Loops — `src/loops/ralph.ts` (126), `commands/goal.ts` (106), `registry/loops/`

- `wc -l`: loops/ralph.ts **126**, commands/goal.ts **106** — exact; `registry/loops/` holds
  `goal/`, `orchestration/`, `ralph/`.
- polytropos provenance is recorded verbatim in `bin/copilot_ralph.py:4`: "Provenance: adapted from
  aesop@5506617 `registry/loops/ralph/`", and it is pricing-fed — the flat per-tick cost default is
  replaced by `bin/copilot_pricing.py`'s `est_cost` / `plan_runway`.
- The three-stops claim that folds into E4 is real: `$defs.goalRecipe` requires `stops`, and `stops`
  requires `max_iterations`, `no_progress_after`, `budget_usd`, described as "All three hard stops
  are required."
- `goal.ts` matches the drop rationale: `goalNew` writes the manifest via `serializeManifest`,
  `goalShow` renders a doc, `goalList` reads recipes back.

verdict-check: confirmed

### E12 — Lessons — `commands/lessons.ts` (45)

- `wc -l src/commands/lessons.ts` = **45** (claim 45, delta 0). It appends a prose bullet
  `- <date> — <text>` to `<state.dir>/lessons.md`, and `--promote` pushes the text into a manifest
  instruction block and recompiles.
- polytropos state holds exactly: `bin/lessons_promote.py:11-14` — "The repo's ``tasks/lessons.md``.
  Despite the ``.md`` extension it is NOT prose: it is newline-delimited JSON objects, one per line".
- The kit-recurrence gate is real: `RECURRENCE_GATE` requires a defect kind to recur across
  distinct kits, and lessons entries are reported verbatim but never clustered or promoted.
- "Different and richer semantics" is supported: aesop appends free text; polytropos clusters
  `defect:` ledger evidence into a human-gated draft.

verdict-check: confirmed

### E13 — Pathway profiles — `src/profile.ts` (125), `profiles/*.yaml`, `docs/05-pathways.md`

- `wc -l src/profile.ts` = **125** (claim 125, delta 0); `profiles/` holds exactly
  `accuracy-max.yaml`, `balanced.yaml`, `token-lean.yaml`; `docs/05-pathways.md` exists (49 lines).
- The "fixed calibrations" characterization is accurate: `profiles/balanced.yaml` hardcodes
  `max_iterations: 40`, `no_progress_stop: 3`, `budget_usd: 25.0`, and `docs/05-pathways.md` renders
  the same three columns as a static table.
- polytropos state holds: `docs/EFFORT-DIAL.md` exists, `skills/route/SKILL.md` manages burn "via
  **effort level**, not model downgrades", and `bin/routing_scorecard.py` is the measured ledger
  (`--history` aggregates every kit's TASKS.md + NOTES.md).
- `task_profiles` is present in all three `data/pricing*.json` files with keys XS/S/M/L/XL — key
  presence only; no value was read, per the kit guardrail.

verdict-check: confirmed

### E14 — Bundle — `commands/bundle.ts` (96)

- `wc -l src/commands/bundle.ts` = **96** (claim 96, delta 0). Its docstring names the three
  wrappers: "a Claude Code plugin (+marketplace), a Copilot-style plugin dir, or a plain tarball".
- polytropos state holds: `.claude-plugin/` contains both `plugin.json` and `marketplace.json`, so
  the repo already IS a Claude plugin.
- The Copilot and Codex bundles exist alongside it (`copilot/`, `codex/`), so per-harness
  distribution is genuinely already solved here.

verdict-check: confirmed

### E15 — MCP server mode — `commands/mcp.ts` (118)

- `wc -l src/commands/mcp.ts` = **118** (claim 118, delta 0). Its docstring: "`aesop mcp serve` —
  the CLI surface as an MCP server (stdio, newline-delimited JSON-RPC)", hand-rolled over the
  `initialize` / `tools/list` / `tools/call` subset.
- polytropos state "none" holds: no file under `bin/` matches "mcp serve", "MCP server", or
  "tools/list".

verdict-check: confirmed

### E16 — Eject — `commands/eject.ts` (33)

- `wc -l src/commands/eject.ts` = **33** (claim 33, delta 0).
- Behavior matches: it strips the `aesop:begin`/`aesop:end` fence lines, removes `aesop.yaml` and
  `.aesop/`, and requires `--force` as "the one deliberately destructive command".
- polytropos state "none" holds — there is no fenced or compiled output in this repo to eject,
  which is the same fact E7 established.

verdict-check: confirmed

### E17 — Registry content seeds — `registry/instructions/AGENTS.template.md` (161 lines), 8 agents, 4 commands, 2 hook specs, skills

- `wc -l registry/instructions/AGENTS.template.md` = **161** (claim 161, delta 0).
- Counts are exact: 8 agent files (code-simplifier, critic, explorer, implementer, researcher,
  security-reviewer, spec-reviewer, verify-app), 4 commands (add-learning, commit-pr, fix-ci,
  techdebt), 2 hook specs, 7 skills plus a `_TEMPLATE`.
- The two hook specs are named as PLAN claims: `registry/hooks/block-dangerous-commands.yaml`
  (`name: block-dangerous-commands`) and `registry/hooks/format-on-write.yaml`
  (`name: format-on-write`), both self-described as canonical specs emitters translate per harness.
- polytropos state holds: `skills/` carries 14 of this repo's own skills and `CLAUDE.md` carries its
  own doctrine.

verdict-check: confirmed

### E18 — Provenance already crossed — Ralph runner port note in `bin/copilot_ralph.py`; tier/tick/runway math in `bin/aesop_bridge.py`

- `bin/copilot_ralph.py` records the port in its module docstring (quoted under E11) and again at
  lines 51, 60, 63, 103 and 167, each naming `aesop@5506617`.
- `bin/aesop_bridge.py` implements exactly the three named computations as subcommands: `tiers`
  (`tier_map`), `est-tick` (`est_tick`), `runway` (`plan_runway`-style tick math).
- "imports nothing" holds literally: its only imports are `argparse`, `json`, `math`, `os`, `sys`
  and `datetime.date`, and its docstring states "It is copy-paste output, not a runtime dependency
  — nothing here imports or calls aesop."
- The tier mapping is computed from `data/pricing.json` at run time, with `frontier` added as
  polytropos's own extension to aesop's strong|mid|cheap dial.

verdict-check: confirmed

### E19 — CLI shell — `src/index.ts` (303)

- `wc -l src/index.ts` = **303** (claim 303, delta 0). It is a pure shell: a `COMMANDS` record of 13
  subcommands (init, compile, sync, doctor, add, remove, list, goal, bundle, update, lessons,
  profile, eject, mcp) plus flag parsing and the only `process.exit` calls.
- The *drop* verdict is well-founded — nothing in `index.ts` carries behavior that E1–E5 do not
  already cover.
- The polytropos-state cell names `bin/primitives.py`, which does **not** exist at polytropos HEAD
  `5066739`; the cell is forward-looking to the engine E4/E5 mark *fold now* in this same kit,
  not a description of the tree today.

verdict-check: confirmed
note: E19's "polytropos state" cell is the only one in the table that names an artifact this kit has yet to build; read together with E4/E5 the intent is unambiguous, but a reader scanning the column alone could take it as an existing file.

## Summary

- confirmed: **17**
- contradicted: **2**
- contradicted ids: **E5**, **E8**

Both contradictions are source-citation/behavior-enumeration errors in the table's first column,
not errors in the verdicts: E5's *fold now* and E8's *drop* both still follow from the evidence.
E5 cites `compile --verbose` for a native/fallback listing that only `doctor --matrix` produces.
E8 enumerates an MCP handshake and a harness-version freshness check that `doctor.ts` does not
implement — the latter is promised by aesop's own `docs/03-harness-matrix.md` but never built,
which is a doc-vs-code gap in aesop worth recording independently of this kit.
