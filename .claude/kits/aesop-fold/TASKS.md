# aesop-fold — tasks

Dispatch preamble. Repo root for every path below: `/path/to/polytropos`
(all repo-relative paths are relative to it). The aesop repo is
`/path/to/aesop` and is READ-ONLY for every task; its HEAD at
architect time was `9c4108ee8ca32fe7f7420a94b15b072c92a6ccf8`. Read `PLAN.md` (decisions D1–D10,
the fence, risks R1–R9) and `GUARDRAILS.md` before any task. **T1, T2, T3 are independent and
safe to run in parallel** (disjoint files: T1 writes only the kit dir; T2 `SETUP.md` + one new
test; T3 new files under `primitives/` + one new test). Warm-cluster candidates (serial
`depends:` chains sharing a primary file and one `model` pin): **T4→T5** (both sonnet, primary
file `bin/primitives.py` + `tests/test_primitives.py`); **T6→T7** (both sonnet, the
`copilot/aesop.toml` rename and its reference ripple). **T7 and T8 both run
`python3 bin/docs_build.py build` and are strictly serial — never concurrent.** T1 is opus and
always a fresh dispatch; T9 is haiku. Statuses: pending | in-progress | done | blocked.

Before the first dispatch, record the full-suite baseline in NOTES.md (`python3 -m unittest
discover -s tests 2>&1 | tail -3`, plus any `FAIL:`/`ERROR:` lines) — PLAN R1.

## Phase 1 — Evaluate, and correct the floor

### T1 — Independent re-verification of the aesop evaluation table
- id: T1
- title: Re-check PLAN.md's 19 evaluation rows against the aesop source; write EVALUATION.md
- status: done
- model: opus
- independent: yes

Create exactly one file: `.claude/kits/aesop-fold/EVALUATION.md`. Edit nothing else — not
PLAN.md, not any file under `/path/to/aesop`.

Why: PLAN.md's *Evaluation* table is the architect's claim about what each aesop capability
is, how big it is, and what already covers it in this repo. The user will decide aesop's fate
from this record, so a different model must check every row against the files themselves
(PLAN D10). You are that checker. Do not trust the table; open the sources.

Procedure, per row E1–E19 of the table in `.claude/kits/aesop-fold/PLAN.md`:
1. Open every aesop file the row cites (paths are relative to
   `/path/to/aesop`; run `wc -l` on each `.ts` file cited with a
   line count and compare — a difference of more than 2 lines is a contradiction).
2. Confirm the behavior claim by reading the code/doc (e.g. E6: each emitter's `capabilities()`
   really lists what PLAN's *Cursor readiness* section says; E11: `bin/copilot_ralph.py`'s
   docstring really records the aesop provenance; E12: `bin/lessons_promote.py` really reads
   JSONL `tasks/lessons.md`).
3. Confirm the "polytropos state" claim by opening the named polytropos file(s).
4. Record `git -C /path/to/aesop rev-parse HEAD` in the header; if it
   differs from the pinned SHA, say so in the header and still evaluate against HEAD.

Output format (pinned — a verify command counts these):
- Line 1: `# aesop-fold — evaluation record`; then a header paragraph with the date, the aesop
  HEAD SHA you observed, and the polytropos HEAD (`git rev-parse HEAD`).
- Then, in order E1…E19, one section each headed exactly `### E<n> — <capability title copied
  from the table>` containing: 2–6 lines of evidence (paths, `wc -l` numbers, the sentence or
  identifier you saw), and exactly one line of the form `verdict-check: confirmed` or
  `verdict-check: contradicted — <one-sentence reason>`. A row is *contradicted* when a cited
  file is missing, a line count is off by more than 2, a described behavior is not what the
  code does, or the polytropos-state claim is false. You judge evidence, not the verdict's
  wisdom — if the facts hold but you disagree with the fold/drop call, write `confirmed` and
  add a line beginning `note:` with your dissent.
- Close with `## Summary`: counts of confirmed / contradicted, and a list of contradicted ids.

Gotchas: `wc -l` counts in the table exclude `*.test.ts`. The aesop `npm test` cannot run here
(no `tsc` on PATH) — do not try; this task is reading only. Do not run `npm`/`node`.

Acceptance:
- `EVALUATION.md` exists with exactly 19 `### E<n>` sections and exactly 19 `verdict-check:`
  lines, in order E1..E19.
- The header names the aesop HEAD SHA observed.
- No file in either repo other than `EVALUATION.md` changed (`git status --porcelain` in
  polytropos shows only the new file beyond the pre-existing modifications listed in PLAN R1;
  aesop's is empty).

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && f=.claude/kits/aesop-fold/EVALUATION.md && test -f "$f" && test "$(grep -c '^### E[0-9][0-9]* — ' "$f")" = "19" && test "$(grep -cE '^verdict-check: (confirmed|contradicted)' "$f")" = "19" && grep -q '^## Summary' "$f" && test -z "$(git -C /path/to/aesop status --porcelain)"
```

### T2 — Python floor: correct SETUP.md to 3.11+ and make the floor loud
- id: T2
- title: Fix SETUP.md's stale 3.8+ row; add tests/test_python_floor.py (floor + stale-claim sweep)
- status: done
- model: sonnet
- independent: yes

Edit `SETUP.md` (one table row) and create `tests/test_python_floor.py`. Nothing else.

Why: shipped code already requires Python 3.11 (`bin/sync_codex_surfaces.py` raises
`RuntimeError("Python 3.11+ tomllib is required to generate agent prompt mirrors")`;
`bin/harness_select.py` imports `tomllib`; `docs/CODEX-HARNESS.md` and the two Codex site pages
say "Use Python 3.11 or newer"; CI pins 3.12). The only tracked 3.8 claim is the `SETUP.md`
requirements row. The user decided: raise the documented floor to 3.11 (PLAN D2). This kit's
new engine uses `tomllib` with no fallback, so the floor must be visible and enforced.

SETUP.md: find the row whose text is exactly
`` | `python3` (3.8+) | polytropos — **stdlib-only**, nothing to `pip install` | ``
and replace it with
`` | `python3` (3.11+) | polytropos — **stdlib-only**, nothing to `pip install`; 3.11 is the floor because the stdlib TOML parser (`tomllib`) arrived there | ``
If that row is not found verbatim, stop and report (`stale-pin`). `SETUP.md` may already carry
unrelated uncommitted modifications (PLAN R1): make only this edit and mention that in your
report.

`tests/test_python_floor.py` (stdlib unittest; `REPO_ROOT = Path(__file__).resolve().parents[1]`;
no git subprocess, no home dir, no network):
1. `test_interpreter_meets_documented_floor`: `sys.version_info >= (3, 11)`, failure message
   naming `SETUP.md` and `tomllib`.
2. `test_tomllib_importable`: `import tomllib` succeeds (fails with a clear message otherwise).
3. `test_setup_md_declares_311_floor`: `SETUP.md` contains the substring `` `python3` (3.11+) ``
   and does NOT contain `(3.8+)`.
4. `test_no_stale_floor_claims`: walk these roots — `README.md`, `SETUP.md`, `CLAUDE.md`,
   `docs/`, `docs-src/`, `docs-site/`, `skills/`, `copilot/`, `codex/`, `copilot-docs/`, `bin/`,
   `tests/` — over files with suffix `.md`, `.py`, `.toml`, `.yaml`, `.yml`, `.json`, `.txt`;
   skip `__pycache__`, skip this test file itself; assert no file matches the regex
   `3\.8\+|Python 3\.8\b|3\.10\+|python_requires\s*=` (report every offender with path). Do
   NOT scan `.claude/kits/`, `tasks/kits/`, or `.claude/agents/` — historical kit records are
   never rewritten. Do NOT scan `site-build/` or `.git/`.
   Do not put the literal string `3.8+` anywhere in the test module except inside the regex
   pattern (the sweep excludes the test file by path, but keep the module honest anyway).

Gotcha: leave `bin/harness_select.py`'s `try: import tomllib / except ImportError` fallback
alone — pre-existing, harmless, out of scope (mention it as dead code in your report; do not
delete it).

Acceptance:
- `SETUP.md` row replaced exactly as pinned; no other line of `SETUP.md` changed by you.
- All four tests exist under those names and pass on `python3` (3.12.7 here).
- The sweep test is a real tripwire: run it once against a temp copy of the tree with a planted
  `3.8+` in a copied `docs/` file and confirm it fails (do this in a temp dir, never in the
  tracked tree) — paste that output in your report.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && grep -qF '| `python3` (3.11+) |' SETUP.md && ! grep -qF '(3.8+)' SETUP.md && python3 -m unittest discover -s tests -p 'test_python_floor.py' -v 2>&1 | tail -3 | grep -q '^OK'
```

## Phase 2 — The primitive model foundation

### T3 — Primitive model, harness matrix, and vendored schema as data
- id: T3
- title: Create primitives/model.json, primitives/harness-matrix.json, primitives/aesop.schema.v1.json + structural tests
- status: done
- model: sonnet
- independent: yes

Create four files: `primitives/model.json`, `primitives/harness-matrix.json`,
`primitives/aesop.schema.v1.json`, `tests/test_primitives_data.py`. Nothing else.

Why: this is the primitive management system's substance — the nine-primitive model and the
per-harness support table, carried over from aesop as data so a human, a test, the docs
generator, and a future Cursor emitter all read the same thing (PLAN D1, D5, D7). Provenance is
aesop commit `9c4108ee8ca32fe7f7420a94b15b072c92a6ccf8`; the sources are
`/path/to/aesop/docs/04-primitives.md`, `docs/03-harness-matrix.md`,
`src/types.ts`, and each `src/emitters/*.ts` (`capabilities()` bodies and the `path:` strings in
`emit()`). Read them; transcribe; do not paraphrase enum tokens.

**`primitives/aesop.schema.v1.json`**: a byte-identical copy of aesop
`schemas/aesop.schema.json` (`cp`, no edits, no added keys — JSON has no comments and the file
is LOCKED upstream; provenance lives in the other two files' `source` objects and in PLAN.md).
Its sha256 must be `a8b5ce94dda62c547728fea03335b22bb877c70426b1ce2eee9cce23f62b2f4f`; if the
aesop file's hash differs at execution time, stop and report (`stale-pin`).

**`primitives/model.json`** (2-space indent, sorted keys not required, trailing newline):
```
{
  "schema": "polytropos-primitives/v1",
  "source": {
    "aesop_commit": "9c4108ee8ca32fe7f7420a94b15b072c92a6ccf8",
    "aesop_docs": ["docs/04-primitives.md", "src/types.ts"],
    "note": "Transcribed from aesop; aesop's src/types.ts and schema are LOCKED upstream — this file mirrors, never extends, their vocabulary."
  },
  "primitives": [ ...nine objects, in this exact order and with these exact ids: "instructions", "skill", "agent", "command", "mcp", "hook", "permissions", "loop", "state" ... ]
}
```
Each primitive object: `id`, `order` (1–9), `title` (the `docs/04` heading text, e.g.
"Instructions", "Skills", "Subagents", "Commands / prompts", "MCP servers", "Hooks",
"Permissions", "Loops & goals", "State & memory"), `manifest_key` (`primitives.instructions`,
`primitives.skills`, `primitives.agents`, `primitives.commands`, `primitives.mcp`,
`primitives.hooks`, `primitives.permissions`, `primitives.loops`, `state`), `authored_as`
(`"inline"` for instructions/mcp/permissions/loops/state — authored in the manifest — and
`"referenced"` for skill/agent/command/hook — the manifest names them, content lives in files),
`semantics` (1–3 sentences from `docs/04`, your words allowed), and `fields`: a list of
`{"name", "type", "required", "enum"?, "note"?}` transcribed from `src/types.ts` / `docs/04`:
- instructions: `template` (string, optional), `blocks[]` of `{scope, content}` with scope enum
  pattern `global | project | path:<glob>`, `global[]` (strings, optional); note the ≤ ~250-line
  emitted-file budget.
- skill: `name`, `description` (frontmatter, required), `body`, optional `scripts/`,
  `references/`, `assets/`; note "the description is the API".
- agent: `name`, `description`, `tools[]` (default `["read"]`), `model` enum
  `strong|mid|cheap` (default mid), `effort` enum `xhigh|high|medium|fast` (default medium),
  `edits` bool (default false), `prompt` (body).
- command: `prompt` (file body), `args` (optional schema).
- mcp: `name`, `transport` enum `stdio|http`, `command` | `url`, `env[]` (NAMES only — note
  it), `scopes[]`, `trust` enum `read|write|irreversible` (default read).
- hook: `name`, `description`, `event` enum `pre-tool|post-tool|stop|session-start`,
  `matcher`, `action` (optional), `deny_patterns[]` (optional).
- permissions: `mutate_allow[]`, `irreversible[]`, `unattended` enum `devcontainer|none`
  (default none); note the three tiers read-free / mutate-policy / irreversible-human-gated.
- loop (goal recipe): `name`, `goal`, `verify`, `plan_gate` (default true), `autonomy` enum
  `high|plan-gated|supervised`, `stops.max_iterations`, `stops.no_progress_after`,
  `stops.budget_usd` — all three stops required; note "never defaulted in silently".
- state: `dir` (default `tasks/`), conventional files `todo.md`, `lessons.md`.

**`primitives/harness-matrix.json`**:
```
{
  "schema": "polytropos-harness-matrix/v1",
  "source": {"aesop_commit": "9c4108ee8ca32fe7f7420a94b15b072c92a6ccf8", "aesop_docs": ["docs/03-harness-matrix.md", "src/emitters/*.ts"], "verified": "aesop's own pin: June–July 2026"},
  "support_values": ["native", "fallback"],
  "goal_modes": ["native", "ralph", "scheduled"],
  "primitives": ["instructions","skill","agent","command","mcp","hook","permissions","loop","state"],
  "harnesses": { "<id>": {"goal_mode": "...", "cells": {"<primitive>": {"support": "...", "target": ["..."], "notes": "..."}}} }
}
```
Six harness ids, exactly the schema enum: `claude-code`, `codex`, `copilot`, `cursor`,
`antigravity`, `vscode`. Every harness has all nine cells. `support` per cell and `goal_mode`
are pinned cell-for-cell to the emitters' `capabilities()` (transcribed here from the source —
re-read the source and confirm before writing):
- claude-code — native: all nine; goal_mode native.
- codex — native: instructions, skill, agent, command, mcp, permissions, loop, state;
  fallback: hook; goal_mode native.
- copilot — native: instructions, skill, agent, command, mcp, state; fallback: hook,
  permissions, loop; goal_mode ralph.
- cursor — native: instructions, mcp, state; fallback: skill, agent, command, hook,
  permissions, loop; goal_mode ralph.
- antigravity — native: instructions, skill, state, loop; fallback: agent, command, mcp, hook,
  permissions; goal_mode scheduled.
- vscode — native: mcp, state; fallback: instructions, skill, agent, command, hook,
  permissions, loop; goal_mode ralph.
`target` lists the repo-relative path patterns the emitter writes for that cell (from the
`path:` strings; use `<name>` / `<glob>` placeholders), e.g. cursor instructions →
`[".cursor/rules/00-aesop.mdc", ".cursor/rules/scoped-<glob>.mdc", "AGENTS.md"]`, cursor skill →
`[".cursor/rules/skill-<name>.mdc"]`, cursor agent → `[".aesop/roles/<name>.md"]`, cursor
command → `[".aesop/prompts/<name>.md"]`, cursor mcp → `[".cursor/mcp.json"]`, cursor loop →
`[".aesop/goals/<name>.md", ".aesop/goals/<name>.ralph.json"]` (core-emitted), state →
`["tasks/todo.md", "tasks/lessons.md"]`; a cell with nothing emitted (e.g. cursor permissions,
antigravity mcp) has `"target": []`. `AGENTS.md` is core-emitted for every harness's
instructions cell (aesop `compile.ts` emits it unconditionally); Claude Code adds `CLAUDE.md`,
Codex adds `.codex/config.toml`, Copilot `.github/copilot-instructions.md` +
`.github/instructions/<glob>.instructions.md`, Antigravity `GUARDRAILS.md`, VS Code
`.vscode/settings.json`. `notes` carries the emitter's fallback description string verbatim for
fallback cells and a short phrase for native ones.

**`tests/test_primitives_data.py`** (stdlib unittest, reads the three JSON files from
`REPO_ROOT / "primitives"`, no temp dirs needed):
- both model and matrix parse; `schema` fields equal the pinned strings.
- model `primitives[*].id` equals the nine-id list in order; `order` is 1..9; every primitive has
  non-empty `title`, `manifest_key`, `authored_as` ∈ {inline, referenced}, `semantics`, `fields`
  list with `name`/`type`/`required` on every entry.
- matrix: harness ids set == `harnesses.items.enum` from the vendored schema; every harness has
  exactly the nine cells; every `support` ∈ `support_values`; every `goal_mode` ∈ `goal_modes`;
  every `target` is a list of strings with no absolute paths.
- pinned capability table: a dict literal in the test (transcribed from the six bullets above)
  compared to the matrix — this is the cell-for-cell pin. Include a second, separate test for
  the cursor column alone (`test_cursor_column_matches_aesop_cursor_emitter`) so a future edit
  to that column is caught by name.
- sha256 of `primitives/aesop.schema.v1.json` equals the pinned hash (module constant).
- the enum tokens in `model.json` fields (`model`, `effort`, `transport`, `trust`, `unattended`,
  `autonomy`, `event`) are subsets of the corresponding enums found in the vendored schema
  where the schema defines them (`$defs.agentRef.oneOf[1].properties.{model,effort}.enum`,
  `$defs.mcpServer.properties.{transport,trust}.enum`,
  `properties.primitives.properties.permissions.properties.unattended.enum`,
  `$defs.goalRecipe.properties.autonomy.enum`); hook `event` has no schema enum — pin it
  in the test from `src/registry.ts` `HookSpec`.

Acceptance: files exist as pinned; all tests pass; schema copy byte-identical (hash); no prices,
model ids, dates other than the provenance note, or home paths anywhere in the three files.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && test "$(shasum -a 256 primitives/aesop.schema.v1.json | cut -d' ' -f1)" = "a8b5ce94dda62c547728fea03335b22bb877c70426b1ce2eee9cce23f62b2f4f" && python3 -c "import json;m=json.load(open('primitives/model.json'));assert [p['id'] for p in m['primitives']]==['instructions','skill','agent','command','mcp','hook','permissions','loop','state'];x=json.load(open('primitives/harness-matrix.json'));assert sorted(x['harnesses'])==['antigravity','claude-code','codex','copilot','cursor','vscode'];assert x['harnesses']['cursor']['cells']['skill']['support']=='fallback'" && python3 -m unittest discover -s tests -p 'test_primitives_data.py' -v 2>&1 | tail -3 | grep -q '^OK'
```

### T4 — bin/primitives.py: load a TOML manifest, `check`, `model`, `matrix`
- id: T4
- title: Create bin/primitives.py (tomllib loader + schema-driven validator) and tests/test_primitives.py
- status: done
- model: sonnet
- depends: T3

Create `bin/primitives.py` and `tests/test_primitives.py` (plus, if you want file fixtures
rather than inline strings, `tests/fixtures/primitives/*.toml`). Nothing else.

Why: validation is what turns a manifest into a managed thing (PLAN E4). The manifest is TOML
read by stdlib `tomllib` (PLAN D2/D3) — no fallback import, no YAML anywhere. Enums and
patterns come from the vendored schema at run time (PLAN D5) so the validator cannot drift
from the locked contract. The engine is READ-ONLY: it never writes a manifest or any file.

House style (match `bin/docs_build.py` / `bin/harness_select.py`): stdlib only; module
docstring stating the contract; `REPO_ROOT = Path(__file__).resolve().parent.parent`;
`PRIMITIVES_DIR = REPO_ROOT / "primitives"`; pure functions taking explicit paths/dicts;
argparse with subparsers; `main(argv=None)` returning the exit code;
`if __name__ == "__main__": raise SystemExit(main())`. Zero `Path.home()`, zero `subprocess`,
zero network, zero wall-clock reads, no `random` (a test introspects the source for these
literal names — do not name them in comments or docstrings either).

Public API (pin these names/shapes; internals are yours):
- `load_schema(path=PRIMITIVES_DIR / "aesop.schema.v1.json") -> dict`
- `load_model(path=...) -> dict`, `load_matrix(path=...) -> dict`
- `load_manifest(path) -> dict` — `tomllib.load`; on `tomllib.TOMLDecodeError` raise
  `ManifestError(str(e))` (a module-level `class ManifestError(Exception)`); on a missing file
  raise `ManifestError("manifest not found: <path>")`.
- `validate(manifest: dict, raw_text: str, schema: dict) -> list[Finding]` where `Finding` is a
  `dict` with keys `code`, `message`, `at` (a dotted manifest path such as
  `primitives.loops[0].stops` or `""` for whole-file findings). Pure; deterministic order
  (document order of the checks below).
- `plan_stub` is NOT part of this task (T5 adds `plan`).
- CLI: `primitives.py model [--json]`, `primitives.py matrix [--harness ID] [--json]`,
  `primitives.py check MANIFEST [--json]`. Exit codes (PLAN D6): 0 ok; 1 usage / file missing
  / TOML parse error (message to stderr, prefixed `error:`); 2 one or more findings. `--json`
  for `check` prints exactly one JSON object: `{"manifest": "<path as given>", "ok": bool,
  "findings": [ {code, message, at}, ... ]}`. Text mode prints one line per finding as
  `<code>  <at>  <message>` and a final `<n> finding(s)` line, or `ok: <path>` when clean.
  `model` prints the nine primitives (id, title, manifest_key, one-line semantics); `matrix`
  prints, per harness (or the one `--harness`), the nine cells as `<primitive>  <support>
  <targets joined by ', '>`; unknown `--harness` → exit 2 with a message listing the schema's
  enum.

Validation rules — codes are pinned; each is a separate test case with a fixture that trips
ONLY that rule:
1. `schema` — `version` missing or ≠ 1; a required top-level key missing (`project`,
   `harnesses`, `pathway`, `primitives`); an unknown top-level key (the schema says
   `additionalProperties: false`); an unknown key under `primitives`; `project.name` or
   `project.commands.test` missing/empty; `harnesses` empty or containing an id not in the
   schema enum; `pathway.profile` missing; `registries[*]` not matching the schema's pattern;
   `primitives.instructions.blocks[*].scope` not matching the schema's scope pattern; `content`
   not a string; a `primitiveRef` / `agentRef` string not matching the schema's pattern, or a
   table without `name`; `agents[*].model` / `.effort` outside the enums; `mcp[*]` missing
   `name`/`transport`, or `transport`/`trust` outside enums; `permissions.unattended` outside
   its enum; `project.review_bandwidth` present but not an integer ≥ 1; `state.dir` not a
   string. (One code, many messages — the `at` path disambiguates.)
2. `stops` — a loop missing `stops` or any of `max_iterations`, `no_progress_after`,
   `budget_usd`; `max_iterations`/`no_progress_after` not integers ≥ 1; `budget_usd` not a
   number > 0. Message must include the phrase `all three hard stops are required`. Never
   default a missing stop.
3. `verify-loop` — `project.commands.test` equals `TODO: set your test command` (aesop's
   placeholder), or a loop's `verify` is empty.
4. `judge-family` — `project.models.primary.family` and `project.models.judge.family` both
   present and equal (case-sensitive).
5. `env-value` — any `mcp[*].env` entry that is not a bare env var NAME: must match
   `^[A-Za-z_][A-Za-z0-9_]*$` (so `GITHUB_TOKEN=ghp…`, `${X}`, or a value-looking string fails).
6. `unsafe-name` — any skill/agent/command/hook/loop/mcp name or manifest `project.name` that
   contains `/`, `\`, `..`, or a NUL, or equals `.` (aesop `safety.ts` `isSafeName`).
7. `secret` — the raw manifest text matches any of aesop's four patterns, copied verbatim from
   `src/commands/doctor.ts` `SECRET_PATTERNS` (GitHub token `ghp_[A-Za-z0-9]{20,}`; API key
   `sk-[A-Za-z0-9-]{20,}`; AWS `AKIA[0-9A-Z]{16}`; literal credential
   `(?:api[_-]?key|secret|token|password)["']?\s*[:=]\s*["'](?!\$\{)[^"'\s]{12,}["']`,
   case-insensitive); `at` = `line <n>`.
Enums/patterns read from the schema dict at call time — write a small helper that fetches
`harnesses.items.enum`, `$defs.modelRef.properties.tier.enum`, the agentRef object variant's
`model`/`effort` enums, `$defs.mcpServer.properties.{transport,trust}.enum`,
`permissions.unattended.enum`, `registries.items.pattern`, the `scope` pattern, the
`primitiveRef`/`agentRef`/`goalRecipe.name` string patterns. A test copies the schema to a temp
dir, removes `cursor` from the harness enum, and asserts a manifest declaring cursor now yields a
`schema` finding — proving the enums are read, not retyped.

TOML dialect the fixtures use (also the T6 conversion target — pin it in the module docstring):
top-level scalars (`version = 1`), `[project]`, `[project.commands]`, `[project.models.primary]`,
`[project.models.judge]`, `harnesses = [...]`, `[pathway]`, `registries = [...]`, `[primitives]`
holding the plain arrays `skills`, `agents`, `commands`, `hooks`, `mcp = []`, `loops = []`
FIRST, then `[primitives.instructions]` (`template = "..."`),
`[[primitives.instructions.blocks]]` (`scope = "project"`, `content = """..."""`),
`[[primitives.mcp]]`, `[primitives.permissions]`, `[[primitives.loops]]` with
`[primitives.loops.stops]`, and `[state]`. Object-form refs use inline tables:
`agents = [ "explorer", { name = "security-reviewer", model = "strong", effort = "xhigh" } ]`.

Fixtures (inline module constants or files under `tests/fixtures/primitives/`): TOML
translations of aesop's three golden manifests
(`/path/to/aesop/fixtures/compile/{minimal,full,token-lean}/aesop.yaml`)
and of aesop's own `aesop.yaml` — all four must validate clean (0 findings). Then one
adversarial fixture per rule above (at least 10), each asserting the finding list contains
exactly the expected code(s) and nothing else. Plus: missing file → `ManifestError`; malformed
TOML → `ManifestError` whose message contains tomllib's text; CLI exit codes 0/1/2 via
`main([...])` with stdout captured (`contextlib.redirect_stdout`); `--json` output parses and
has exactly the three keys; the source-introspection guard (no `Path.home`, `subprocess`,
`urlopen`, `random.`, `time.time`, `date.today` in the module source); `matrix --harness
cursor` output lists all nine primitives; `matrix --harness nope` exits 2.

Acceptance: all tests pass; module ≤ ~450 lines; zero non-stdlib imports; no `try/except
ImportError` around `tomllib`; nothing in `bin/primitives.py` reads `data/pricing*.json` or
hardcodes a price/model id.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && python3 -m unittest discover -s tests -p 'test_primitives.py' -v 2>&1 | tail -3 | grep -q '^OK' && python3 bin/primitives.py matrix --harness cursor | grep -c '^' | xargs test 9 -le && ! grep -q 'except ImportError' bin/primitives.py && ( python3 bin/primitives.py check /nonexistent.toml >/dev/null 2>&1; test $? -eq 1 )
```

### T5 — `plan` subcommand and `matrix --markdown`
- id: T5
- title: Add `plan MANIFEST [--harness ID] [--json]` and `matrix --markdown` to bin/primitives.py
- status: done
- model: sonnet
- depends: T4

Edit only `bin/primitives.py` and `tests/test_primitives.py`.

Why: `plan` shows what each harness would get natively vs by fallback, including Cursor on a
manifest that does not declare it (PLAN D7: Cursor-ready, not Cursor-built). `matrix --markdown`
is the generator for the table `docs/PRIMITIVES.md` embeds (PLAN D8).

PROVENANCE CORRECTION (Phase 1 review — read this before implementing): `plan` is a port of
NEITHER aesop command. PLAN E5's citation of `compile --verbose` is wrong — `compile.ts:110-114`
iterates `capabilities().fallback` only and prints no native listing. The real native/fallback
listing is `doctor --matrix` (`doctor.ts:180-186`) — but do NOT model `plan` on that either:
`doctor.ts:181` maps over `manifest.harnesses`, so it reports ONLY DECLARED harnesses, whereas
`plan copilot/aesop.toml --harness cursor` must work on a manifest declaring
`harnesses = ["copilot"]`. `plan` renders `primitives/harness-matrix.json` (T3's transcription of
the same `capabilities()` both aesop commands read); its output shape is a superset of doctor's.
The spec below is authoritative and already correct — this note only repairs the rationale.

`plan(manifest: dict, matrix: dict, harnesses: list[str] | None) -> dict` (pure). Harness set =
`--harness ID` if given (must be in the matrix; else exit 2 listing valid ids), otherwise
`manifest["harnesses"]`. Output shape:
`{"manifest": path, "harnesses": {"<id>": {"goal_mode": ..., "primitives": [ {"id", "declared": bool, "support", "target": [...], "notes"} × 9 ]}}}`.
`declared` semantics (pin): `instructions` → true always (aesop always emits AGENTS.md from the
template; `blocks` optional); `state` → true always; `skill`/`agent`/`command`/`hook` → the
corresponding `primitives.<key>` list is present and non-empty; `mcp`/`loop` → their list is
non-empty; `permissions` → the table is present with at least one key. Text output per
harness: a header line `## <id>  (goal mode: <goal_mode>)` then nine lines
`<id padded to 12>  <declared: "declared"|"—" padded to 9>  <support>  <targets joined ', '>`.
`plan` runs `validate` first: findings → print them and exit 2 (a plan over an invalid
manifest is misleading); a `secret`-only finding still blocks.

`matrix --markdown` (no `--harness`): print exactly
```
| Primitive | claude-code | codex | copilot | cursor | antigravity | vscode |
|---|---|---|---|---|---|---|
| instructions | native | native | ... |
```
— nine rows in model order, cell text = `support` value only (`native`/`fallback`), then a
blank line, then one line `Goal modes: claude-code=native · codex=native · copilot=ralph ·
cursor=ralph · antigravity=scheduled · vscode=ralph` derived from the matrix (never typed). LF
line endings, one trailing newline, deterministic. `--markdown` with `--harness` is a usage
error (exit 1).

Tests to add: plan over the aesop `full` fixture with `--harness cursor` → nine entries,
`support` for skill/agent/command/hook/permissions/loop = fallback, mcp/instructions/state =
native, `declared` true for skill/agent/command/mcp/hook/permissions/loop (that fixture has
all), goal_mode ralph; plan over `minimal` without `--harness` → only `claude-code`, `mcp`
declared false; plan over an invalid manifest → exit 2 and no plan output; `matrix --markdown`
byte-equal to a pinned expected string built in the test from the matrix JSON (not a
hardcoded table — the test derives it independently with its own tiny renderer so a shared
bug cannot pass); `--markdown --harness x` → exit 1.

Acceptance: all `test_primitives.py` tests pass (T4's included, unchanged); the markdown output
is byte-stable across two runs.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && python3 -m unittest discover -s tests -p 'test_primitives.py' -v 2>&1 | tail -3 | grep -q '^OK' && python3 bin/primitives.py matrix --markdown > /tmp/pt-matrix-a.md && python3 bin/primitives.py matrix --markdown > /tmp/pt-matrix-b.md && cmp -s /tmp/pt-matrix-a.md /tmp/pt-matrix-b.md && test "$(grep -c '^| ' /tmp/pt-matrix-a.md)" = "11" && rm -f /tmp/pt-matrix-a.md /tmp/pt-matrix-b.md
```

### T5b — `plan --json` must emit JSON on the error path (Phase 2 review, Q2)
- id: T5b
- title: Make cmd_plan's findings gate honor --json, matching check --json's failure shape
- status: done
- model: sonnet
- depends: T5

Edit only `bin/primitives.py` and `tests/test_primitives.py`.

Why: `plan --json` on an INVALID manifest prints plain-text finding lines and exits 2, while
`check --json` on the same input stays JSON-shaped. A consumer doing `json.loads(stdout)` gets a
`JSONDecodeError` and cannot tell "manifest invalid" from "engine crashed" — and the asymmetry
means a consumer that learned the contract from `check` gets it wrong on `plan`. T8 is about to
document this surface; fixing now means T8 describes a coherent CLI instead of an exception.
Cause: `cmd_plan`'s findings gate calls `_print_findings(findings)` unconditionally, before
`args.json` is consulted.

The change — the findings gate in `cmd_plan` becomes:

```python
if findings:
    if args.json:
        print(json.dumps({"manifest": path, "ok": False, "findings": findings}))
    else:
        _print_findings(findings)
    return 2
```

The failure object is key-for-key IDENTICAL to `check --json`'s, so one consumer parser handles
both commands.

**Do NOT add `"ok": true` to the success payload.** `plan --json`'s success shape stays exactly
`{"manifest", "harnesses"}` — an existing test asserts `set(payload.keys()) == {"manifest",
"harnesses"}`, and widening the success contract is more change than this defect warrants. The
discriminator for consumers is `"findings" in payload`.

Deliberately NOT changed: unknown `--harness` (exit 2) and missing file (exit 1) still write
nothing to stdout and put `error:` on stderr. That mirrors `check` exactly and is normal CLI
convention.

Add one test: `plan --json` on an invalid fixture → exit 2, `json.loads(stdout)` succeeds, keys
exactly `{manifest, ok, findings}`, `ok is False`. No existing test changes.

Acceptance: the new test passes; every existing `test_primitives*.py` test still passes unchanged;
`plan --json` on a VALID manifest still returns exactly `{"manifest", "harnesses"}`; the module
line count does not require raising the size threshold again (this is ~4 lines).

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && python3 -m unittest discover -s tests -p 'test_primitives*.py' 2>&1 | tail -1 | grep -q '^OK' && printf 'version = 2\nharnesses = ["copilot"]\n[project]\nname = "x"\n[project.commands]\ntest = "t"\n[pathway]\nprofile = "token-lean"\n[primitives]\nskills = []\n' > "$TMPDIR/pt-t5b.toml" && python3 bin/primitives.py plan "$TMPDIR/pt-t5b.toml" --json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert set(d)=={"manifest","ok","findings"}, d; assert d["ok"] is False' && rm -f "$TMPDIR/pt-t5b.toml"
```

## Phase 3 — Convert the one manifest

### T6 — copilot/aesop.yaml → copilot/aesop.toml; test_copilot_bundle.py reads TOML
- id: T6
- title: Convert the Copilot bundle manifest to TOML (comments preserved) and port its enforcement test to tomllib
- status: done
- model: sonnet
- depends: T4

Files: `git mv copilot/aesop.yaml copilot/aesop.toml` then rewrite its content; edit
`tests/test_copilot_bundle.py`. Nothing else (T7 handles every other reference).

Why: PLAN D4 — the engine reads only TOML, and the repo's one manifest must be a first-class
input to it. `tests/test_copilot_bundle.py` calls itself "the enforcement mechanism standing in
for `aesop compile`" and parses the YAML as plain text with a hand-rolled helper; with `tomllib`
that helper goes away and every existing assertion stays.

Conversion rules (PLAN D3: the file is hand-authored and only ever read, so comments survive
because YOU carry them):
- Every `#` header comment line of the YAML file is carried over as a `#` comment at the top of
  the TOML file, same order, with these wording updates only: `aesop.yaml` → `aesop.toml`;
  add one sentence after the first line: `# TOML dialect of aesop's v1 manifest schema
  (primitives/aesop.schema.v1.json), read by stdlib tomllib; validated by
  python3 bin/primitives.py check copilot/aesop.toml.`; the sentence "`aesop compile` is NOT
  run in this repo; tests/test_copilot_bundle.py enforces that this manifest and .github/ stay
  consistent." stays verbatim (it is still true).
- **ORDERING (corrected by the Phase 2 review — the list below is NOT source order).** In TOML a
  bare `key = value` after any `[table]` header belongs to THAT table, silently. So write the bare
  root keys FIRST: `version = 1`, `harnesses = ["copilot"]`, `registries = ["builtin"]` — all
  three BEFORE the first `[table]` header. Then `[project]` (`name`, `stack`, `invariants`),
  `[project.commands]`, `[pathway]`, `[primitives]`, `[[primitives.instructions.blocks]]`,
  `[state]`. **The authoritative dialect rule is the module docstring of `bin/primitives.py` —
  read it before writing a line.** Following the old source order put `invariants` under
  `[project.commands]` and `registries` under `[pathway]` SILENTLY (only `harnesses` failed
  loudly), and no test asserts on `invariants`, so the loss would have shipped.
- **`mcp` and `loops` are ABSENT from the YAML, not empty — write NEITHER key.** A 1:1 conversion
  omits both. Do not "helpfully" add `mcp = []` / `loops = []`: the source has no such values, and
  the docstring's array-of-tables constraint is therefore moot here.
- Values are carried 1:1: `[project]` `name`, `stack`; `[project.commands]`
  `test` (keep its trailing YAML comment as a TOML comment on the same line); `invariants`
  as a TOML array of strings — the four strings byte-verbatim (they contain backticks,
  `${CLAUDE_PLUGIN_ROOT}`, and `{{POLYTROPOS_ROOT}}`; use basic `"..."` strings and escape
  nothing else — none contains a double quote or backslash; verify with the parsed value);
  `[pathway] profile = "token-lean"`;
  `[primitives]` with `agents = [...]` and `skills = [...]` (the same 12 and 13 names in the
  same order) BEFORE `[[primitives.instructions.blocks]]` (PLAN R2); the single block:
  `scope = "project"` and `content = """` … `"""` where the content is the YAML block's text
  with its indentation removed, the doctrine sentence byte-verbatim, ending with a newline
  before the closing `"""`; `[state] dir = "tasks/"`.
- Confirm equivalence yourself before finishing: `python3 -c "import tomllib; m=tomllib.load(open('copilot/aesop.toml','rb')); print(m['primitives']['agents']); print(m['primitives']['instructions']['blocks'][0]['content'])"`
  and compare against the old YAML (`git show HEAD:copilot/aesop.yaml`).

`tests/test_copilot_bundle.py` changes: docstring: replace the plain-text-parsing sentences
with "It loads copilot/aesop.toml with stdlib tomllib (Python 3.11+; see SETUP.md) and
cross-checks it against …"; `AESOP_YAML = COPILOT_DIR / "aesop.yaml"` → `AESOP_TOML =
COPILOT_DIR / "aesop.toml"`; delete `_extract_yaml_list_block` (grep first: no other file uses
it); add a module-level `_manifest()` helper returning `tomllib.load(...)`; keep EVERY existing
test method name — rewrite bodies: `test_manifest_exists` → the TOML path;
`test_version_is_1` → `manifest["version"] == 1`; `test_harnesses_block_is_exactly_copilot` →
`manifest["harnesses"] == ["copilot"]`; `test_manifest_agent_set_equals_bundle_agent_files` →
`manifest["primitives"]["agents"]`; `test_doctrine_sentence_in_manifest` → keep the raw-text
`assertIn(DOCTRINE_SENTENCE, text)` AND add `assertIn(DOCTRINE_SENTENCE,
manifest["primitives"]["instructions"]["blocks"][0]["content"])`; every other method unchanged.
Add `test_no_yaml_manifest_remains` asserting `copilot/aesop.yaml` does not exist. Update the
"Case 1" docstring wording to say `aesop.toml`.

Acceptance:
- `copilot/aesop.yaml` gone, `copilot/aesop.toml` present, parsed agents/skills lists identical
  to the YAML's, doctrine sentence present verbatim in both raw text and parsed content, every
  original header comment idea present.
- `python3 bin/primitives.py check copilot/aesop.toml` exits 0 with `ok:`.
- `tests/test_copilot_bundle.py` passes; `grep -c "def test_" ` on it is ≥ the count before your
  edit + 1; no `_extract_yaml_list_block` anywhere in `tests/` or `bin/`.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && test ! -e copilot/aesop.yaml && test -f copilot/aesop.toml && python3 bin/primitives.py check copilot/aesop.toml && grep -qF 'Derive every number from `data/pricing.copilot.json` at run time' copilot/aesop.toml && ! grep -rq '_extract_yaml_list_block' tests bin && python3 -m unittest discover -s tests -p 'test_copilot_bundle.py' -v 2>&1 | tail -3 | grep -q '^OK'
```

### T7 — Reference sweep for the rename, status notes on the two aesop docs, rebuilds
- id: T7
- title: Point every reference to copilot/aesop.yaml at aesop.toml; add superseded/status notes; rebuild docs-site and copilot-docs checks
- status: done
- model: sonnet
- depends: T6

Edit exactly: `docs/COPILOT-PARITY.md`, `docs/COPILOT-HARNESS.md`, `docs/HOW-IT-WORKS.md`,
`copilot-docs/manifest.json`, `docs/AESOP-COMPILE-PROPOSAL.md`, `docs/AESOP-INTEGRATION.md`,
and the generated pages `python3 bin/docs_build.py build` rewrites. Nothing else — in
particular NOT `docs/GUIDE.md`, `skills/*/SKILL.md`, `bin/aesop_bridge.py`,
`tests/test_codex_bundle.py` (those name aesop's generic root `aesop.yaml`, not this file), and
never anything under `.claude/kits/*` or `tasks/kits/*` (historical records).

Why: PLAN D4 — the file moved; live docs and the copilot-docs source manifest (whose `bundle`
entries are existence-checked by `bin/copilot_docs.py`) must follow, and the two aesop docs
this kit supersedes get a dated note rather than a rewrite.

Edits (find the anchor verbatim; if absent, stop and report `stale-pin`):
- `docs/COPILOT-PARITY.md`: two occurrences of `` `copilot/aesop.yaml` `` → `` `copilot/aesop.toml` ``.
- `docs/COPILOT-HARNESS.md`: the bullet beginning `- **\`copilot/\`** — the Copilot harness bundle: \`aesop.yaml\`` → `` `aesop.toml` `` (and append ", in the TOML dialect of aesop's v1 schema" after "(the manifest, source of truth for what the bundle contains)" — one sentence, nothing more).
- `docs/HOW-IT-WORKS.md`: the tree line containing `the Copilot CLI harness bundle (aesop.yaml + .github/)` → `(aesop.toml + .github/)`.
- `copilot-docs/manifest.json`: the `bundle` source entry `"copilot/aesop.yaml"` → `"copilot/aesop.toml"`.
- `docs/AESOP-COMPILE-PROPOSAL.md`: insert, immediately after the H1 line and a blank line, this
  blockquote (verbatim, one paragraph):
  `> **Status (2026-09-04): superseded by the aesop-fold kit.** The direction changed from "make the Copilot bundle an \`aesop compile\` target" to "fold aesop's primitive model into polytropos": the manifest is now \`copilot/aesop.toml\` (TOML dialect of the same v1 schema), validated offline by \`python3 bin/primitives.py check\`, and \`aesop compile\` is not planned to run here. The specification below is kept as history; see \`docs/PRIMITIVES.md\` and \`.claude/kits/aesop-fold/PLAN.md\` (Evaluation) for the standing decision.`
- `docs/AESOP-INTEGRATION.md`: insert after the H1 line and a blank line:
  `> **Status (2026-09-04): partially superseded by the aesop-fold kit.** Registry consumption of \`route\`/\`fable-check\` and \`bin/aesop_bridge.py\` remain accurate for anyone running aesop, and the "Kits in aesop-managed projects" rules still apply to a root \`aesop.yaml\`. This repo's own Copilot manifest is now \`copilot/aesop.toml\`, and the primitive model lives in \`docs/PRIMITIVES.md\`; the aesop-side follow-ups below are deprioritized — see \`.claude/kits/aesop-fold/PLAN.md\` (Evaluation).`
- Then run `python3 bin/docs_build.py build` and `python3 bin/copilot_docs.py check`; if the
  latter reports stale artifacts, run `python3 bin/copilot_docs.py build` and stage its output
  together (report what it rewrote).

Gotcha: `docs/PRIMITIVES.md` does not exist yet (T8 creates it); the status notes may reference
it by name — the docs generator rewrites links only for `[text](path)` links, and these notes
use backticked names, not links, so no dangling-link check fires. Do NOT create
`docs/PRIMITIVES.md` here.

Acceptance:
- No `copilot/aesop.yaml` or `(aesop.yaml + .github/)` string remains in the four RENAME files
  (`docs/COPILOT-PARITY.md`, `docs/COPILOT-HARNESS.md`, `docs/HOW-IT-WORKS.md`,
  `copilot-docs/manifest.json`) or in `docs-site/deep-dives/{copilot-parity,copilot-harness,how-it-works}.md`.
  **The two AESOP-* docs keep their historical body verbatim — `docs/AESOP-COMPILE-PROPOSAL.md`
  legitimately retains its 5 occurrences of `copilot/aesop.yaml`; only the blockquote is added.**
  (Corrected by the Phase 2 review: the earlier wording said "the six named source files", which
  read literally would have rewritten a historical document. The verify command was always correct
  — it greps only the four rename files.)
- Also update the one stale in-kit reference T7's fence would otherwise miss:
  `tests/test_primitives_plan_adversarial.py` line ~132 comment `Mirrors copilot/aesop.yaml's own
  declared shape` → `aesop.toml`. This is a Phase-2 file this kit authored, not a historical
  record, so it is in scope (one word).
- Both status blockquotes present verbatim; each appears exactly once.
- `python3 bin/docs_build.py check` exits 0; `python3 bin/copilot_docs.py check` exits 0.
- `python3 -m unittest discover -s tests -p 'test_docs_*.py'` and `-p 'test_copilot_docs*.py'`
  green.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && ! grep -q 'copilot/aesop\.yaml' docs/COPILOT-PARITY.md docs/COPILOT-HARNESS.md docs/HOW-IT-WORKS.md copilot-docs/manifest.json && ! grep -q 'aesop\.yaml + \.github' docs/HOW-IT-WORKS.md && test "$(grep -c 'Status (2026-09-04): superseded by the aesop-fold kit' docs/AESOP-COMPILE-PROPOSAL.md)" = "1" && test "$(grep -c 'Status (2026-09-04): partially superseded by the aesop-fold kit' docs/AESOP-INTEGRATION.md)" = "1" && python3 bin/docs_build.py check && python3 bin/copilot_docs.py check && python3 -m unittest discover -s tests -p 'test_docs_site.py' 2>&1 | tail -1 | grep -q '^OK'
```

## Phase 4 — Surface it

### T8 — docs/PRIMITIVES.md, mkdocs nav entry, matrix drift test, site rebuild
- id: T8
- title: Write the human-facing primitive-model doc with the generated matrix embedded and drift-tested
- status: done
- model: sonnet
- depends: T5, T7

Create `docs/PRIMITIVES.md` and `tests/test_primitives_doc.py`; edit `mkdocs.yml` (one nav
line); run `python3 bin/docs_build.py build` (rewrites generated pages under `docs-site/`).

**AMENDED by the Phase 3 review — one more file is IN SCOPE, and you must edit it.**
`tests/test_docs_build_adversarial.py` hardcodes the current doc census, and adding any
`docs/*.md` breaks four assertions. Proven empirically by the reviewer against a temp copy:
adding one doc takes md sources 24 -> 25, page_map 26 -> 27, expected_pages 68 -> 69. Bump:
line ~750 `assertEqual(len(md_sources), 24)` -> `25`; line ~778 `assertEqual(len(page_map), 26)`
-> `27`; line ~949 `assertEqual(len(baseline), 68)` -> `69`; line ~956 `assertEqual(len(grown),
69)` -> `70`. Also update the two docstrings stating the arithmetic (~lines 771-776 and 938-943).
**Do NOT replace these with a glob-derived count** — they are deliberate tripwires that make
adding a doc a conscious act. Keep them hardcoded; bump them. Nothing else beyond these files.

Why: PLAN D8 — every `docs/*.md` is mirrored into the public site and must be in nav
(`tests/test_docs_site.py` enforces both); the matrix table must not drift from the data, so it
is generated and byte-compared.

`docs/PRIMITIVES.md` (~500–900 words of prose plus the tables; one H1; no prices, model ids,
credit values, or dates other than the aesop provenance commit; no absolute paths):
1. H1 `# AI primitives — the model behind every harness bundle`.
2. **What this is** — the nine-primitive model folded from aesop (commit
   `9c4108ee8ca32fe7f7420a94b15b072c92a6ccf8`, its `docs/04-primitives.md` and
   `docs/03-harness-matrix.md`); why it lives here as data (`primitives/model.json`,
   `primitives/harness-matrix.json`, `primitives/aesop.schema.v1.json` — the schema vendored
   verbatim, LOCKED upstream); what it is not (no compiler, no emitters — this repo hand-authors
   bundles and enforces them by unittest).
3. **The nine primitives** — a hand-written table, one row per primitive in model order:
   id · what it is (one line) · where it is authored (`manifest_key`, inline vs referenced).
   Keep it consistent with `primitives/model.json` (the drift test below checks ids and order).
4. **Harness matrix** — exactly this, with the generated output between the markers:
   ```
   <!-- primitives:matrix:begin -->
   ...output of `python3 bin/primitives.py matrix --markdown`, byte-for-byte...
   <!-- primitives:matrix:end -->
   ```
   followed by one paragraph: native vs fallback means what, and that the cursor column is
   pinned to aesop's Cursor emitter research — the input to the future Cursor work, which is
   not built yet.
5. **The manifest (TOML)** — the v1 schema in its TOML dialect: the table-ordering rule
   (plain arrays under `[primitives]` before any `[primitives.*]` section), a 15–25 line
   excerpt of `copilot/aesop.toml` showing `[project]`, `harnesses`, `[primitives]` arrays and
   one `[[primitives.instructions.blocks]]`, and the read-only rule: nothing in this repo
   writes a manifest; `tomllib` reads; comments survive because manifests are hand-authored.
6. **Commands** — `python3 bin/primitives.py model | matrix [--harness ID] [--markdown] |
   check MANIFEST [--json] | plan MANIFEST [--harness ID] [--json]`, exit codes 0 / 1 / 2, and
   what `check` enforces (the seven finding codes, one line each).
7. **Pathways, briefly** (PLAN E13, research only) — aesop's cost/accuracy dial idea in one
   paragraph, and why this repo replaces fixed calibrations with measured routing (link to them
   with **bare sibling filenames**, exactly `[Routing history](ROUTING-HISTORY.md)` and
   `[Role experiment](ROLE-EXPERIMENT.md)` — **no `docs/` prefix and no `./`**. AMENDED by the
   Phase 3 review, which ran the real `render_deep_dive_page`: a `docs/`-prefixed link mirrors to
   `.../blob/main/docs/docs/ROUTING-HISTORY.md` — a doubled path that 404s — and the failure is
   SILENT because `tests/test_docs_site.py`'s relative-link check skips `https://` targets, so the
   dead link would ship green to the public site.)
8. **Relationship to aesop** — three sentences: what was folded, what was deferred (emitters,
   registry seeds), what was dropped, and that the per-capability record is
   `.claude/kits/aesop-fold/EVALUATION.md` (name it in backticks, not as a link).

`mkdocs.yml`: in the `Deep dives:` nav list, insert `    - AI primitives: deep-dives/primitives.md`
as the first entry after `    - deep-dives/index.md` (labels there are alphabetical; "AI"
sorts first). Two-space indentation, no tabs.

`tests/test_primitives_doc.py` (stdlib; loads `bin/primitives.py` via the repo's
`importlib.util.spec_from_file_location` `_load` idiom, see `tests/test_harness_select.py`):
- the marker region of `docs/PRIMITIVES.md` (text strictly between the begin marker line and
  the end marker line) equals the string `bin/primitives.py`'s markdown renderer returns
  (call the pure function, not the CLI). **Note (Phase 3 review): `render_matrix_markdown` returns
  WITHOUT a trailing newline — the CLI's `print` adds it — so compare
  `region.strip("\n")` against `render_matrix_markdown(load_matrix()).strip("\n")`. A naive
  line-slice yields the region WITH a trailing newline and fails. The function takes the matrix as
  an argument; it does not load it itself.**
- the nine ids appear in the doc's primitives table in model order (regex the first column of
  the table rows).
- `mkdocs.yml` contains `deep-dives/primitives.md` exactly once.

Then `python3 bin/docs_build.py build`; confirm `docs-site/deep-dives/primitives.md` now exists
and `python3 bin/docs_build.py check` exits 0.

Acceptance: doc as pinned; nav line present; `test_primitives_doc.py` green; `test_docs_site.py`
green; `docs_build.py check` exit 0; no dollar sign followed by a digit anywhere in
`docs/PRIMITIVES.md`. **Added by the Phase 3 review:**
`python3 -m unittest discover -s tests -p 'test_docs_build_adversarial.py'` green (the census
bump above), and no `](docs/` link form anywhere in `docs/PRIMITIVES.md`.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && test -f docs/PRIMITIVES.md && grep -q '<!-- primitives:matrix:begin -->' docs/PRIMITIVES.md && test "$(grep -c 'deep-dives/primitives.md' mkdocs.yml)" = "1" && ! grep -qE '\$[0-9]' docs/PRIMITIVES.md && test -f docs-site/deep-dives/primitives.md && python3 bin/docs_build.py check && ! grep -q '](docs/' docs/PRIMITIVES.md && python3 -m unittest discover -s tests -p 'test_primitives_doc.py' -v 2>&1 | tail -3 | grep -q '^OK' && python3 -m unittest discover -s tests -p 'test_docs_site.py' 2>&1 | tail -1 | grep -q '^OK' && python3 -m unittest discover -s tests -p 'test_docs_build_adversarial.py' 2>&1 | tail -1 | grep -q '^OK'
```

### T9 — One run line in CLAUDE.md
- id: T9
- title: Add the primitives check to CLAUDE.md's "How to run things" block, within the byte ceiling
- status: done
- model: haiku
- depends: T5

Edit only `CLAUDE.md`: in the `## How to run things` fenced block, immediately after the line
that begins `python3 bin/docs_build.py check`, insert exactly one line:
`python3 bin/primitives.py check copilot/aesop.toml   # AI-primitive manifest validation (offline, read-only; exit 2 on findings; lands with the aesop-fold kit)`

Why: that block is the repo's established index of engines; the file is loaded every session,
so one line is the entire budget (PLAN R5: 15568 of 16000 bytes used before this task;
`tests/test_guardrails_layout.py` fails above 16000).

Acceptance: line present exactly once; `CLAUDE.md` byte size ≤ 16000; no other line changed;
`tests/test_guardrails_layout.py` green.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && test "$(grep -c '^python3 bin/primitives.py check copilot/aesop.toml' CLAUDE.md)" = "1" && test "$(wc -c < CLAUDE.md | tr -d ' ')" -le 16000 && python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' 2>&1 | tail -1 | grep -q '^OK'
```
