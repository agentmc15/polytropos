# PLAN — copilot-model-prefs

Give the Copilot CLI side of the optimizer — and ONLY the Copilot side — user model
preferences: **pin which model a tier resolves to** and/or **exclude models from
consideration**, enforced mechanically by the bin engines and honored by the recommending
skills/agents. Mechanism: per-run CLI flags on `bin/copilot_execute.py run` PLUS a
persistent, gitignored prefs file the engines read as the default; flags override the file.
The concrete motivating case: the roster's sole frontier-tier model can be swapped out — a
pin like `frontier=<some-other-live-id>` makes that id the frontier pick everywhere the
driver resolves the frontier tier, and an exclude removes a model from recommendations and
from the escalation ladder. This is NOT a force-frontier switch (explicitly out of scope):
a pin changes WHICH model a tier resolves to, never WHEN a tier is used.

autonomy: advisory

## Goal

`bin/copilot_execute.py run` accepts repeatable `--pin TIER=MODEL_ID` and
`--exclude MODEL_ID` (plus `--prefs FILE` / `--no-prefs`), enforcing them in initial
dispatch and the escalation ladder; `bin/copilot_pricing.py` gains a `prefs` subcommand
showing the active pins/excludes and what each tier now resolves to; a new shared module
`bin/copilot_prefs.py` owns all prefs logic (both engines reuse it via importlib — never
duplicated); the `route`/`architect`/`escalate`/`frontier-check` Copilot skills AND their
same-named agents teach honoring pins/excludes (plus one sentence in the `execute` skill);
the prefs file `prefs/copilot.json` is gitignored user data; `docs/COPILOT-PINS.md`
documents the feature.

**Done looks like:**

1. `python3 bin/copilot_pricing.py prefs` exits 0 with no prefs file, printing the honest
   default resolution per tier; with a prefs file or flags it shows pins, excludes, notes,
   and the per-tier resolution (pinned entries marked; a tier emptied by exclusion rendered
   honestly, never invented). Every pre-existing `copilot_pricing.py` subcommand's output is
   byte-identical to today.
2. `python3 bin/copilot_execute.py run --dry-run` with active prefs prints the effective
   (substituted) dispatch plus a `prefs:` line and notes; without flags and without a prefs
   file, output is byte-identical to today. Pin/exclude/conflict errors exit 2 with messages
   listing the valid vocabulary. A pinned id wins its tier outright in the ladder; excluded
   ids are skipped; an emptied tier is skipped; an emptied frontier with no replacing pin
   means the ladder tops out lower — stated, never fabricated.
3. `tests/test_copilot_prefs.py` (new) covers load/merge/validate/resolve/conflict;
   additive test classes land at pinned append seams in `tests/test_copilot_execute.py`,
   `tests/test_copilot_pricing.py`, and `tests/test_copilot_bundle.py`; every pre-existing
   test class/method/constant stays byte-intact; `python3 -m unittest discover -s tests`
   fully green.
4. The four skills + four agents each carry a short, **id-free** pins/excludes paragraph
   (BODY-only edits — frontmatter byte-intact); the `execute` skill gains one pinned
   sentence; `SkillNoModelIdTests` and both YAML-safety sweeps stay green.
5. `.gitignore` carries a root-anchored `/prefs/` entry; no prefs file (not even a sample)
   is committed; `docs/COPILOT-PINS.md` exists and contains no live pricing-key model id.
6. `git diff --quiet -- skills codex data .claude-plugin README.md copilot/aesop.yaml copilot/.github/copilot-instructions.md copilot/.github/skills/lessons-loop` exits 0, and the
   only modified pre-existing files are `bin/copilot_execute.py`, `bin/copilot_pricing.py`,
   the three touched test files, the eight bundle teaching files + the execute skill,
   `.gitignore`, and the architect-premade CLAUDE.md lines.

## Ground truth (verified in-tree 2026-07-18 — pinned; executors do NOT re-derive)

- **`bin/copilot_execute.py` has NO `resolve_tier` function today.** Tier mechanics live in
  `escalation_ladder(pricing, model_id=None)`: start tier = `pricing["models"][model_id]["tier"]`
  (unknown/None → `DEFAULT_ESCALATION_START = "mid"`); for each tier strictly above the start
  in `TIER_ORDER = ("cheap", "mid", "strong", "frontier")`, take the FIRST model id in
  pricing-file order carrying that tier; empty tiers skipped. `run_task(task, pricing,
  runner, verify_runner, agent="implementer", max_escalations=None, copilot_bin="copilot",
  extra_args=())` returns exactly `{"id", "status", "model_used", "escalations",
  "verify_rc"}`. The `run` subparser today has exactly `--kit --task --agent --copilot-bin
  --max-escalations --extra-arg --dry-run`. `main` catches
  `(ValueError, FileNotFoundError, KeyError)` → stderr + exit 2. Dry-run prints exactly
  three lines (`task:`, `dispatch:`, `verify:`) and loads no pricing.
- **`bin/copilot_pricing.py`** subcommands: `models`, `est`, `runway`, `knobs`; the
  `cmd_<name>(args, pricing)` + `build_parser` shape; `knobs` is the additive-subcommand
  precedent (effort-dial kit). `est`'s unknown-key message shape:
  `unknown model id {id!r}; valid choices: {sorted(models)}`.
- **Roster reality**: `claude-fable-5` is the SOLE frontier-tier model in
  `data/pricing.copilot.json`; the GPT-5.6 rows are strong/mid/cheap. So "pin the frontier
  model" concretely means resolving the `frontier` tier to some other live id — the pinned
  id need NOT carry the pinned tier. That is the point, and it is a deliberate,
  noted user override priced at the pinned model's own rates (no rate mixing — `est` prices
  by model id already).
- **Tests**: stdlib unittest; `python3 -m unittest discover -s tests -p '<file>.py'` (the
  dotted-module form is broken on this machine). `tests/test_copilot_execute.py` stubs every
  dispatch (fake runners / temp stub executables via `--copilot-bin`), uses the synthetic
  `PRICING_FIXTURE` (`fake-cheap`/`fake-mid-a`/`fake-mid-b`/`fake-strong`/`fake-front`),
  and never calls `Path.home()`. `tests/test_copilot_pricing.py` patches
  `mock.patch.object(cp, "load_pricing", return_value=FIXTURE)` for CLI tests; its FIXTURE
  has NO frontier-tier model (useful for empty-tier honesty tests).
  `tests/test_copilot_bundle.py` guards manifest↔dir set equality, frontmatter YAML-colon
  safety (agents AND skills), and `SkillNoModelIdTests` (no live pricing key in ANY skill
  file — the new paragraphs must stay id-free).
- **Gitignore precedent**: root-anchored entries `/journal/`, `/trends/`, `/memory/` — the
  leading slash is load-bearing (an unanchored pattern once nearly ignored
  `skills/memory/`).
- **bin→bin reuse precedent**: importlib `spec_from_file_location` by absolute path
  computed from `Path(__file__)` (journal engines; every test file's `_load` helper).
- **Bundle discipline**: `copilot/aesop.yaml` is the manifest but body-only content edits
  to EXISTING skills/agents need no manifest change (roster stable);
  `bin/harness_select.py` globs install everything — zero installer changes.

## Decisions

- **D1 — Prefs file: `prefs/copilot.json` at the repo root, gitignored via root-anchored
  `/prefs/`.** A dedicated dir (not a bare root file) follows the `/journal/`-`/trends/`-
  `/memory/` pattern and leaves room for future per-harness prefs files WITHOUT new
  gitignore entries. Engines find it from their own location
  (`Path(__file__).resolve().parent.parent / "prefs" / "copilot.json"` — the `PRICING_PATH`
  pattern; zero `Path.home()`). Schema (JSON — no comments possible, so the doc carries the
  commentary):
  `{"schema_version": 1, "pins": {"<tier>": "<model-id>"}, "excludes": ["<model-id>", ...]}`.
  Unknown top-level keys are tolerated silently (forward compat); a `schema_version` newer
  than the engine's `PREFS_SCHEMA_VERSION = 1` earns a best-effort-read note. The file is
  USER DATA: never committed, never auto-created by any engine, no sample file shipped —
  the doc shows the shape.
- **D2 — Flag grammar + precedence.** On `copilot_execute.py run` (and on the new
  `copilot_pricing.py prefs`): repeatable `--pin TIER=MODEL_ID`, repeatable
  `--exclude MODEL_ID`, `--prefs FILE` (override the file location — the test seam),
  `--no-prefs` (ignore the FILE entirely; `--pin`/`--exclude` flags still apply, so a user
  can bypass a stored exclude in one run). Precedence: **pins merge per-tier** (a flag pin
  replaces only its own tier's file pin; other file pins survive) — full replacement would
  make one `--pin` silently drop unrelated stored pins; **excludes are the union** of file
  and flags (an exclude is a "never use this" statement — accumulation is the only
  non-surprising reading; the escape hatch for "use it just this once" is `--no-prefs`).
  `review` gets NO prefs flags (it dispatches the reviewer with no model resolution).
- **D3 — Validation is source-sensitive; conflict is always a hard error.** Flags were
  typed NOW → hard `ValueError` (exit 2 via the existing `main` handler): bad grammar
  (message shows `TIER=MODEL_ID`), unknown tier (message lists `TIER_ORDER`), unknown model
  id (message mirrors `est`'s `valid choices: {sorted(models)}` shape). File entries are
  stored data that must survive roster drift → structural malformation (unparseable JSON,
  non-dict `pins`, non-list `excludes`) degrades to empty prefs + an honest note;
  a semantically invalid ENTRY (unknown tier key, id no longer a live pricing key) is
  skipped with a note naming it — never a crash, never invented. After the merge, an
  effective pin whose id is in the effective excludes is a **hard error from any source**:
  `pin <tier>=<id> conflicts with exclude <id> — drop one, or use --no-prefs to bypass the
  prefs file`. Silently picking a winner is exactly the ambiguity this feature exists to
  remove.
- **D4 — Pin semantics: the pinned id wins its tier outright.** `resolve_tier(pricing,
  tier, prefs)` returns the pin when set (no file-order scan), else the first
  non-excluded model in file order carrying the tier, else `None`. A cross-tier pin (the
  pinned id's own tier differs from the slot) is legal and deliberate — `effective_prefs`
  emits a note naming both tiers, and estimates use the pinned model's own rates (already
  how `est` works — no rate mixing). NOT built: any force-frontier/tier-promotion switch —
  pins change WHICH model a tier resolves to, never WHEN the driver uses a tier.
- **D5 — Exclusion semantics in dispatch + ladder.** In the ladder, an excluded id is
  skipped in favor of the next model in file order carrying that tier; a tier emptied by
  exclusion is skipped (the pre-existing empty-tier behavior) — and if the frontier tier
  empties with no pin replacing it, the ladder simply tops out lower; the driver's output
  says so, never fabricates a rung. A rung that would equal the currently dispatched model
  or an earlier rung is skipped (no pointless re-dispatch). For the INITIAL dispatch: if
  the task's own `model` pin from TASKS.md is excluded, the driver substitutes
  `resolve_tier` of that model's tier (prefs pin wins, else next in file order) and notes
  the substitution; if nothing resolves for that tier, it is a hard `ValueError` (exit 2)
  telling the user to un-exclude or pin — the initial dispatch never silently jumps tiers
  (tier-jumping is the ladder's job, on verify failure only). Prefs do NOT reach an
  agent's own frontmatter `model:` default (a task with no `model` line still dispatches
  without `--model`) — that is Copilot-side resolution the driver never sees; the doc says
  this honestly.
- **D6 — Enforcement seam: new `bin/copilot_prefs.py`, single home, importlib reuse.**
  All prefs logic (load, merge, validate, conflict, `resolve_tier`) lives in ONE new
  stdlib-only module; `copilot_execute.py` and `copilot_pricing.py` each load it lazily via
  the house importlib pattern — never duplicated. It cannot live in `copilot_execute.py`
  (pricing importing the driver inverts the layering) nor in `copilot_pricing.py` (the
  driver's docstring pins that it does not import copilot_pricing). `copilot_prefs.py`
  declares its own `TIER_ORDER` (tier vocabulary is a sanctioned literal; a test asserts it
  equals `copilot_execute.TIER_ORDER` so the twins can never drift). Engine changes are
  additive-only: `escalation_ladder(pricing, model_id=None, prefs=None)` and
  `run_task(..., prefs=None)` — default `None` preserves byte-identical behavior and every
  existing caller/test; with prefs, `run_task`'s result gains ONE additive key
  `prefs_notes` (list of note strings; absent when `prefs is None`). When `run` is invoked
  with no prefs flags and the prefs file is absent (or `--no-prefs`), `cmd_run` passes
  `prefs=None` and — for `--dry-run` — still loads no pricing: today's outputs stay
  byte-identical.
- **D7 — Pricing surface: ONE new subcommand, `prefs`, mirroring the `knobs` precedent.**
  `copilot_pricing.py prefs [--pin TIER=MODEL_ID ...] [--exclude MODEL_ID ...]
  [--prefs FILE] [--no-prefs] [--json]` prints: the source (`(no prefs file)` /
  `(prefs file ignored: --no-prefs)` / the path), active pins and excludes, every note, and
  a per-tier resolution table over `TIER_ORDER` (pinned entries marked `(pinned)`,
  cross-tier pins annotated with the model's own tier, an unresolvable tier rendered
  `(none)` with its reason). `--json` emits exactly the keys `source`, `pins`, `excludes`,
  `resolved` (tier → id or null), `resolved_via` (tier → `"pin"`/`"default"`/null),
  `notes`. Errors exit 2. `models`/`est`/`runway`/`knobs` are NOT touched — one clean
  surface beats a flag sprinkled across four.
- **D8 — Teaching: BODY-only, id-free paragraphs on exactly nine bundle surfaces.** The
  four skills (`route`, `architect`, `escalate`, `frontier-check`) and their four
  same-named agents get a short `## User model prefs (pins & excludes)` section — check
  the `prefs` engine surface (and honor prompt-stated prefs), never recommend/pin an
  excluded model, a pinned tier's pick IS the pinned model (cross-tier = deliberate
  override at its own rates); per-surface tails: architect writes kit `model:` pins
  consistent with active prefs; escalate names the driver flags and the
  emptied-tier/tops-out-lower honesty; frontier-check evaluates the PINNED frontier
  candidate when one is set. The `execute` skill gets ONE pinned sentence (it quotes the
  driver surface, which now has the flags). No paragraph contains a live pricing-key model
  id (`SkillNoModelIdTests` sweeps skills; the same discipline is applied to the agents by
  hand) — `prefs/copilot.json` and flag grammar literals are fine. Frontmatter is
  byte-intact everywhere (both YAML-colon sweeps stay green); `copilot/aesop.yaml`,
  `copilot-instructions.md`, `lessons-loop`, and the other six agents / five skills are
  byte-untouched — no roster change. Bundle tests: two additive contract classes at the
  pinned seam.
- **D9 — Docs + gitignore.** Root-anchored `/prefs/` two-line append to `.gitignore` (own
  mechanical task — memory-skill precedent). New `docs/COPILOT-PINS.md` (effort-dial
  got its own doc — same call): the why, the file schema with PLACEHOLDER ids only (the
  repo rule "never hardcode a real model id in docs" holds — examples use
  `<model-id>`-style placeholders and point at `models --json`), flag grammar, precedence,
  conflict semantics, empty-tier honesty, the agent-frontmatter limitation (D5), and the
  deferred list. No README change.
- **D10 — Executor pins: sonnet authors, haiku audits, opus reviews.** Routing history
  (18 kits, 96/97 first-try; sonnet 62/63 first-try on exactly this pinned-brief
  engine+bundle+test shape, haiku 17/17 on mechanical audits) says sonnet-clean. Every
  authoring task pins `sonnet`; the gitignore append and final audit pin `haiku`; the kit
  reviewer (opus) runs at phase ends. The per-task escalation valve covers surprises.

## OUT-OF-SCOPE fence (do NOT build)

- **Copilot CLI only.** No changes to `codex/`, `skills/` (Claude side), `.claude-plugin/`,
  `bin/codex_*.py`, `bin/harness_select.py`, `bin/copilot_ralph.py`, `bin/copilot_usage.py`,
  or any journal/scorecard/memory engine. No Claude-side or Codex-side prefs parity (a
  future kit).
- **No force-frontier switch, no tier-promotion knob, no auto-routing change** — pins
  resolve WHICH model a tier means, never WHEN a tier is used. The escalation trigger
  (verify failure) and tier walk-order are untouched.
- **No roster changes**: no new skills or agents, `copilot/aesop.yaml` and
  `copilot/.github/copilot-instructions.md` byte-untouched, `lessons-loop` and every
  bundle file not named in D8 byte-untouched. Frontmatter of the edited files byte-intact.
- **NEVER invoke the real `copilot`/`codex`/`claude` CLI** from any task, test, or verify
  command (command lines WRITTEN into bundle bodies are runtime instructions the kit never
  executes). No network, no node/`aesop compile`.
- **The prefs file is gitignored user data**: never committed, never auto-created, no
  sample/example file committed anywhere, and no task/test/verify ever creates or reads a
  real `prefs/copilot.json` at the default path — tests use temp `--prefs` fixtures or
  `--no-prefs`, always. Nothing is applied to the real `~/.copilot` (the user reinstalls
  manually); zero `Path.home()` in any new or edited code.
- **No edits to any of the three pricing files**; no hardcoded price or real model id in
  any new code, test, skill, agent, or doc (tier vocabulary, `PREFS_SCHEMA_VERSION`, the
  `prefs` dir + `copilot.json` names, flag-grammar strings, pinned message text, and
  synthetic fixture ids are the sanctioned literals; demo/doc ids are derived from the
  pricing file at run time or shown as placeholders).
- **No prefs flags on `review`**, no `COPILOT_MODEL`/settings.json wiring, no interactive
  prompt, no prefs "set"/"write" CLI (the user edits the JSON by hand — the doc shows how).
- **No commit, no push.**

## Risks & tripwires

- **Byte-stable-outputs tripwire**: with no prefs flags and no prefs file, `run --dry-run`
  must print exactly today's three lines and load no pricing
  (`DryRunSpawnsNothingTests` and the end-to-end stub test stay byte-untouched AND green).
  All pre-existing classes in the three touched test files stay byte-intact — additions go
  ONLY at the pinned append seams.
- **Real-prefs-file bleed-through**: a user's live `prefs/copilot.json` must never change
  existing-test behavior. It can't: excludes/pins are validated against live pricing keys,
  fixture kits use `fake-*` ids, and new CLI tests always pass `--prefs <tempfile>` or
  `--no-prefs` and patch `load_pricing`. Never write a test that depends on the default
  prefs path being absent or present.
- **Pin-vs-exclude conflict**: always a hard exit-2 error after the merge, from any source
  combination — never a silent winner (D3).
- **Excluded-empties-tier honesty**: ladder skips the tier with the existing skip
  behavior; initial dispatch errors instead of silently jumping tiers; the frontier
  emptying with no pin means the ladder tops out lower and says so — a fabricated rung or
  invented id anywhere is a defect.
- **SkillNoModelIdTests vs the new paragraphs**: the sweep scans every skill file against
  live pricing keys — the teaching paragraphs are id-free by construction (tier words,
  flag grammar, `prefs/copilot.json` only). The same id-free discipline applies to the
  four agent edits even though the sweep doesn't reach agents.
- **YAML-colon tripwire**: all bundle edits are BODY-only; frontmatter stays byte-intact,
  so both `FrontmatterYamlSafetyTests` sweeps cannot trip — any frontmatter diff is a
  defect.
- **TIER_ORDER twins**: `copilot_prefs.TIER_ORDER` must equal
  `copilot_execute.TIER_ORDER` — asserted by a test in `tests/test_copilot_prefs.py`;
  `copilot_execute.py`'s own constant stays byte-identical.
- **Gitignore anchoring**: the entry is `/prefs/` with the leading slash — an unanchored
  `prefs/` would ignore any future `*/prefs/` path (the `/memory/` lesson).
- **Dotted unittest form is broken** on this machine — verify commands use
  `discover -s tests -p '<file>.py'` only.
- **Importlib load in engines**: lazy-load `copilot_prefs` inside the functions that need
  it (module-level exec at import would run on every `_load` in tests — fine, but lazy
  keeps `--help` and untouched subcommands import-clean); path is
  `Path(__file__).resolve().parent / "copilot_prefs.py"`.

## Phases

- **Phase 1 — engine core**: T1 `bin/copilot_prefs.py` + its test file; T2 prefs-aware
  `copilot_execute.py`; T3 `copilot_pricing.py prefs` subcommand.
- **Phase 2 — bundle teaching**: T4 route + frontier-check (skill+agent) + contract tests;
  T5 architect + escalate (skill+agent) + execute-skill sentence + contract tests.
- **Phase 3 — closeout**: T6 gitignore append; T7 `docs/COPILOT-PINS.md`; T8 full-suite +
  frozen-surface audit.

T2 and T3 both depend on T1 but are file-disjoint (safe in any order). T4→T5 is a strict
serial chain (both edit `tests/test_copilot_bundle.py`). Warm-cluster hint: one warm sonnet
implementer can serve T1→T2→T3 serially, a second serves T4→T5; T6 (haiku), T7 (sonnet,
fresh), and T8 (haiku) are fresh spawns, as is every verifier.

## Deferred (recorded, not built — each with its correctable point)

- Codex-side and Claude-side model prefs parity → a future kit (mirrors how
  harness-parity followed codex-harness); `docs/COPILOT-PINS.md` records the gap.
- A prefs "set"/"write" CLI or interactive editor → the JSON file is hand-edited; the doc
  shows the schema.
- Prefs-aware `models` table markers (pinned/excluded row flags) → the `prefs` subcommand
  is the one view; add markers later only if the user asks.
- Reaching an agent's frontmatter `model:` default → Copilot-side resolution the driver
  never sees; documented honestly in `docs/COPILOT-PINS.md`.
