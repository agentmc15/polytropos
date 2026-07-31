# TASKS — aesop-bridge

Repo root: `/path/to/polytropos`. Run all verify commands from
there. Read `PLAN.md` (same directory) first — especially the OUT-OF-SCOPE fence and decisions
D1–D7. Status vocabulary: `pending | in-progress | done | blocked`.

Dispatch rule for the orchestrator: pass each task's `model` value as the Agent tool's `model`
parameter when dispatching to `aesop-bridge-implementer` (the parameter overrides the agent's
frontmatter default). Tasks marked `independent: yes` within the same phase may run in parallel;
`depends:` lists hard ordering. Dispatch `aesop-bridge-reviewer` at each phase end.

**Kit precondition:** the `harden-plugin` kit should be completed first. Hard requirement only
for T3 (its anchor text is harden-plugin T6's output); every other task is safe to run either
way, but finish harden-plugin first to avoid interleaved diffs in the same files.

---

## Phase 1 — Pricing portability (registry-consumable skills)

### T1 — Create bin/sync_pricing_refs.py (mirror generator)
- status: done
- model: sonnet
- depends: (none)
- independent: no (T2 imports its functions; T3–T4 reference its output)

**Brief.** Per PLAN.md D3: aesop vendors a whole skill directory, so the portable skills need an
adjacent copy of pricing.json that survives vendoring, while `data/pricing.json` stays the only
hand-edited numeric source. Create `bin/sync_pricing_refs.py`, Python stdlib only (this repo
forbids pip/requirements), following the conventions of the existing `bin/` scripts (module
docstring, `main()` entry, `if __name__ == "__main__":` guard).

Contract:

- Module constants: `REPO_ROOT = Path(__file__).resolve().parent.parent`;
  `SOURCE = REPO_ROOT / "data" / "pricing.json"`; `PORTABLE_SKILLS = ("route", "fable-check")`.
- `sync(root=None) -> list` — `root` defaults to `REPO_ROOT`. Reads
  `<root>/data/pricing.json` **as bytes** and writes byte-identical copies to
  `<root>/skills/<name>/references/pricing.json` for each portable skill (creating
  `references/` dirs as needed). Returns the list of paths written. Byte copy, NOT a
  json load/dump round-trip — byte identity is the contract.
- `check(root=None) -> list` — returns the list of mirror paths that are missing or not
  byte-identical to the source. Never writes anything.
- `main(argv=None)` — argparse with a single optional flag `--check`. Default mode: run
  `sync()`, print one `synced <relative path>` line per file, exit 0. With `--check`: run
  `check()`; if empty, exit 0 silently or with an `ok` line; otherwise print each stale path to
  stderr and exit 1.
- Docstring must state: `data/pricing.json` is the single hand-edited source of truth; these
  mirrors exist so aesop-vendored copies of the skills stay self-contained; never edit mirrors
  by hand; `tests/test_pricing_refs.py` fails on drift.

Run the script once after writing it so the two mirrors exist in the working tree (T2's test and
T3's ladder reference them).

**Acceptance.**
- `python3 bin/sync_pricing_refs.py` creates both mirrors, byte-identical to `data/pricing.json`,
  and is idempotent (second run rewrites the same bytes).
- `python3 bin/sync_pricing_refs.py --check` exits 0 immediately after a sync.
- `sync`/`check` accept a `root` argument so tests can run against a temp tree.
- `data/pricing.json` itself is untouched (byte-identical to git HEAD).

**Verify.**
```bash
cd /path/to/polytropos && python3 bin/sync_pricing_refs.py && cmp data/pricing.json skills/route/references/pricing.json && cmp data/pricing.json skills/fable-check/references/pricing.json && python3 bin/sync_pricing_refs.py --check && git diff --quiet data/pricing.json && echo 'T1 OK'
```

---

### T2 — Regression tests for the mirror generator
- status: done
- model: sonnet
- depends: T1
- independent: no

**Brief.** Create `tests/test_pricing_refs.py`, stdlib `unittest` only, mirroring the conventions
of `tests/test_cost_report.py`: module docstring; `bin/` loaded via
`importlib.util.spec_from_file_location` from a `BIN_DIR` computed off `Path(__file__)` (bin/ is
not a package); no pytest.

Test cases (minimum):

1. **Live-tree guard (the drift tripwire):** for each of
   `skills/route/references/pricing.json` and `skills/fable-check/references/pricing.json`, the
   file exists and its bytes equal `data/pricing.json`'s bytes. This is the test that fails if
   anyone edits either the source or a mirror without rerunning the sync script.
2. **`sync()` against a temp tree:** build a temp dir containing `data/pricing.json` (any small
   JSON bytes — deliberately fake content, e.g. `{"models": {}}`, so nothing here needs updating
   when real prices change) plus empty `skills/route/` and `skills/fable-check/` dirs; call
   `sync(root=tmp)`; assert both mirrors exist, are byte-identical, and the returned list has
   both paths.
3. **`check()` catches corruption:** after the sync in (2), append a byte to one mirror; assert
   `check(root=tmp)` returns exactly that path; assert the other mirror is not reported.
4. **`check()` catches a missing mirror:** delete one mirror; assert `check(root=tmp)` reports it.

**Acceptance.** All new tests pass; the full suite stays green; no network, no writes outside
tempfile dirs (except none), no real price literals in the fixture.

**Verify.**
```bash
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_pricing_refs.py' -v && python3 -m unittest discover -s tests && echo 'T2 OK'
```

*(Verify command amended during execution: the original `python3 -m unittest tests.test_pricing_refs`
dotted-module form is shadowed by a pre-existing site-packages package named `tests` on this
machine — PEP 420 gives the regular package priority over this repo's namespace-style `tests/`
dir. Discovery with `-p` resolves locally and tests the same thing.)*

---

### T3 — Extend the pricing-resolution ladder in route + fable-check
- status: done
- model: sonnet
- depends: T1; PLUS harden-plugin T6 must be `done` (see PLAN.md D4)
- independent: no

**Brief.** The two portable skills currently resolve pricing in two steps
(`${CLAUDE_PLUGIN_ROOT}` → relative path). Vendored copies (aesop `.aesop/vendor/`, compiled to
other repos' `.claude/skills/`) have neither — they need the adjacent `references/pricing.json`
mirror from T1 as a third step. Two pinned text replacements — make exactly these, nothing else.

**Precondition check first:** the "current" sentences below are the output of harden-plugin T6.
If either is not found verbatim in its file, STOP and report (do not improvise a merge; the
likely cause is harden-plugin not finished).

(1) `skills/route/SKILL.md` — the pricing-source sentence currently reads:
> Read the plugin's `data/pricing.json` (`${CLAUDE_PLUGIN_ROOT}/data/pricing.json`; if that variable is unset, resolve `../../data/pricing.json` relative to this SKILL.md) for all prices, model notes, and task-size profiles.

Replace with:
> Read the plugin's `data/pricing.json` for all prices, model notes, and task-size profiles — resolve in order: `${CLAUDE_PLUGIN_ROOT}/data/pricing.json`; if that variable is unset, `../../data/pricing.json` relative to this SKILL.md; if neither exists, `references/pricing.json` beside this SKILL.md (a vendored snapshot — check its `cached_date` and flag prices as possibly stale if it is more than 60 days old).

(2) `skills/fable-check/SKILL.md` — the opening pricing sentence currently reads:
> Read the plugin's `data/pricing.json` (`${CLAUDE_PLUGIN_ROOT}/data/pricing.json`; if that variable is unset, resolve `../../data/pricing.json` relative to this SKILL.md) for current prices, and derive the Fable-vs-Opus and Fable-vs-Sonnet cost ratios from those rates — never quote ratios from memory.

Replace with:
> Read the plugin's `data/pricing.json` for current prices — resolve in order: `${CLAUDE_PLUGIN_ROOT}/data/pricing.json`; if that variable is unset, `../../data/pricing.json` relative to this SKILL.md; if neither exists, `references/pricing.json` beside this SKILL.md (a vendored snapshot — check its `cached_date` and flag prices as possibly stale if it is more than 60 days old). Derive the Fable-vs-Opus and Fable-vs-Sonnet cost ratios from those rates — never quote ratios from memory.

WHY: the ladder order matches the CLAUDE.md invariant (plugin var first, relative fallback); the
`references/` step is last because inside this repo/plugin it is a mirror, and it only "wins" in
a vendored context where the first two are absent. The 60-day staleness threshold is a judgment
constant pinned here so both skills say the same thing.

**Acceptance.** Both replacements applied verbatim; `references/pricing.json` and `cached_date`
each appear exactly once per file; `CLAUDE_PLUGIN_ROOT` still present in both; no other lines
changed in either file (git diff shows only these two sentence rewrites).

**Verify.**
```bash
cd /path/to/polytropos && [ "$(grep -c 'references/pricing.json' skills/route/SKILL.md)" = "1" ] && [ "$(grep -c 'references/pricing.json' skills/fable-check/SKILL.md)" = "1" ] && grep -q 'cached_date' skills/route/SKILL.md && grep -q 'cached_date' skills/fable-check/SKILL.md && grep -q 'CLAUDE_PLUGIN_ROOT' skills/route/SKILL.md && grep -q 'CLAUDE_PLUGIN_ROOT' skills/fable-check/SKILL.md && echo 'T3 OK'
```

---

### T4 — Guardrails: mirror rule in CLAUDE.md + README price-update step
- status: done
- model: sonnet
- depends: T1, T2, T3
- independent: no

**Brief.** Two pinned insertions so future editors (human or agent) can't drift the mirrors.

(1) `CLAUDE.md` — the first invariant bullet ends with the sentence:
> A gloss directly beside its field name (e.g. "`cache_read_multiplier` (0.1×)") is acceptable in skills; a standalone literal is not.

Immediately after that sentence, in the same bullet, append:
> Generated mirrors `skills/route/references/pricing.json` and `skills/fable-check/references/pricing.json` keep aesop-vendored copies of those skills self-contained — never edit a mirror by hand; regenerate with `python3 bin/sync_pricing_refs.py` whenever `data/pricing.json` changes (`tests/test_pricing_refs.py` fails on drift).

(2) `README.md` — the "## Updating prices" section ends with the sentence:
> Bump `cached_date`.

Append immediately after it, same paragraph:
> Then run `python3 bin/sync_pricing_refs.py` to refresh the generated mirrors under `skills/*/references/` — the test suite fails if they drift.

Change nothing else in either file.

**Acceptance.** Both insertions present verbatim at the specified anchors; git diff shows only
those two additions.

**Verify.**
```bash
cd /path/to/polytropos && grep -q 'sync_pricing_refs.py' CLAUDE.md && grep -q 'never edit a mirror by hand' CLAUDE.md && grep -q 'sync_pricing_refs.py' README.md && python3 -m unittest discover -s tests && echo 'T4 OK'
```

---

*Phase 1 end — dispatch `aesop-bridge-reviewer` before starting Phase 2.*

---

## Phase 2 — Aesop-aware architect/execute

### T5 — Architect skill: rules for aesop-managed target projects
- status: done
- model: opus
- depends: (none within this kit)
- independent: no (T6 must match this task's output; keep serialized)

**Brief.** `skills/architect/SKILL.md` Step 2 tells the architect to add harness guardrails by
appending to the target project's `CLAUDE.md`. In an aesop-managed project that is wrong:
`CLAUDE.md`/`AGENTS.md` there are compiled output with `<!-- aesop:begin … -->` fences —
`aesop sync` flags in-fence hand-edits as drift and `aesop compile` overwrites them. Guardrails
belong in the project's `aesop.yaml` manifest instead. (Verified at aesop@5506617; see PLAN.md
D6–D7.)

In `skills/architect/SKILL.md`, the "### Harness guardrails" subsection currently consists of
this paragraph:
> Add (or append to) the target project's `CLAUDE.md`: conventions, invariants, "always run X before claiming done", forbidden shortcuts. If a procedure is complex enough, make it a project skill (`.claude/skills/<name>/SKILL.md`) instead. These are the Fable-judgment rails the executors run on.

Append this as a NEW paragraph directly after it (do not modify the existing paragraph):
> **Aesop-managed target?** If the target project has an `aesop.yaml` at its root, or an `<!-- aesop:begin` fence in its `CLAUDE.md`/`AGENTS.md`, those files are compiled output — hand-edits get flagged as drift by `aesop sync` and overwritten by `aesop compile`. Put the guardrails in `aesop.yaml` under `primitives.instructions.blocks` (scope: project) instead, then run `aesop compile` and confirm `aesop sync` reports no drift. Kit directories (`.claude/kits/…`) and kit-prefixed agent files are safe to write directly — aesop tracks only files it emits — but never reuse the name of an agent listed in the manifest's `primitives.agents`.

After editing, re-check BOTH `skills/architect/SKILL.md` and `skills/execute/SKILL.md` against
the kit-contract checklist in this repo's CLAUDE.md (layout, task fields, status vocabulary,
phase headings, `depends:`/`independent:`, model-override rule). This addition is append-only
and must not alter any contract element — if it seems to, stop and report.

**Acceptance.** New paragraph present verbatim after the existing one; no other changes in the
file; kit-contract markers still present in both skills.

**Verify.**
```bash
cd /path/to/polytropos && grep -q 'Aesop-managed target?' skills/architect/SKILL.md && grep -q 'primitives.instructions.blocks' skills/architect/SKILL.md && grep -q 'aesop:begin' skills/architect/SKILL.md && grep -q 'Add (or append to) the target project' skills/architect/SKILL.md && grep -q 'pending/in-progress/done/blocked' skills/architect/SKILL.md && grep -qi 'independent' skills/architect/SKILL.md && grep -q 'NOTES.md' skills/execute/SKILL.md && echo 'T5 OK'
```

---

### T6 — Execute skill: read-only rule for aesop-compiled files
- status: done
- model: sonnet
- depends: T5
- independent: no

**Brief.** Mirror T5 on the execution side. In `skills/execute/SKILL.md`, the `## Setup` section
currently has two numbered items (locate the kit; read PLAN.md and TASKS.md). Append a third item
to that numbered list, exactly:
> 3. If the target project is aesop-managed (`aesop.yaml` at its root, or an `<!-- aesop:begin` fence in `CLAUDE.md`/`AGENTS.md`): treat those compiled files as read-only. Any guardrail change a task needs goes into `aesop.yaml` (`primitives.instructions.blocks`) followed by `aesop compile` — never a hand-edit of a fenced file. Kit files (`PLAN.md`, `TASKS.md`, `NOTES.md`) and kit-prefixed agents are outside aesop's management and are updated normally.

Wording must stay consistent with the paragraph T5 added to the architect skill (same detection
rule, same manifest destination) — read T5's output first. Change nothing else. After editing,
re-check both skills against the CLAUDE.md kit-contract checklist (append-only; contract
untouched).

**Acceptance.** Item 3 present verbatim in `## Setup`; no other changes; contract markers intact
in both files.

**Verify.**
```bash
cd /path/to/polytropos && grep -q 'aesop-managed' skills/execute/SKILL.md && grep -q 'primitives.instructions.blocks' skills/execute/SKILL.md && grep -q 'aesop:begin' skills/execute/SKILL.md && grep -q 'NOTES.md' skills/execute/SKILL.md && grep -qi 'overrides the' skills/execute/SKILL.md && grep -q 'Aesop-managed target?' skills/architect/SKILL.md && echo 'T6 OK'
```

---

*Phase 2 end — dispatch `aesop-bridge-reviewer` before starting Phase 3.*

---

## Phase 3 — Budget bridge

### T7 — Create bin/aesop_bridge.py (numbers for aesop's dials)
- status: done
- model: sonnet
- depends: (none within this kit)
- independent: no (T8 tests its functions)

**Brief.** Per PLAN.md D5: aesop's dials are abstract (tiers `strong|mid|cheap`, flat
`budget_usd` stops, a flat per-tick cost estimate when the agent CLI emits no cost JSON); this
script computes the concrete numbers from `data/pricing.json` at run time so the user can paste
them into `aesop.yaml` or a goal recipe. Python stdlib only; follow `bin/` conventions
(docstring, `main()`, `__main__` guard). Load pricing exactly like `bin/agent_tracker.py` does
(path relative to `__file__` → `data/pricing.json`).

Pure functions (unit-testable, no I/O besides the pricing dict passed in):

- `tier_map(pricing) -> dict` — maps aesop tier names to current model ids:
  `{"frontier": …, "strong": …, "mid": …, "cheap": …}` where `frontier` = first model in
  `pricing["models"]` file order whose `tier` is `"frontier"`, `strong` → first `"opus"`,
  `mid` → first `"sonnet"`, `cheap` → first `"haiku"`. Omit a key if no model has that tier.
  (Convention per PLAN.md D5: first-in-file-order per tier = current; `json.load` preserves
  order. Model ids are computed, never hardcoded.)
- `est_tick(pricing, profile, model_id, cache_hit=0.8, today=None) -> float` — estimated USD for
  one loop tick: look up `task_profiles[profile]` (`input_tokens`, `output_tokens`) and the
  model's rates; cost = `input_tokens × (1 − cache_hit + cache_hit × cache_read_multiplier) / 1e6
  × input_per_mtok + output_tokens / 1e6 × output_per_mtok`. If the model has `intro_pricing` and
  `today` (a `datetime.date`, defaulting to `date.today()`) ≤ its `until` date, use the intro
  rates. Unknown profile or model id → raise `KeyError` with a message listing valid choices.
- `check_budget(pricing, usd, profile, model_id, cache_hit=0.8, today=None) -> dict` — returns
  `{"est_tick_usd": …, "iterations": floor(usd / est_tick), "warning": <str or None>}`; warning
  is set when iterations < 10: `"fewer than 10 iterations of runway — raise budget_usd or shrink
  the task profile"`.

CLI (`argparse` subcommands, each with `--json` for machine-readable output; JSON floats rounded
to 4 decimals, human-readable dollars to 2):

- `tiers [--json]` — human mode: one aligned line per tier, e.g.
  `strong → <model-id> (<display>, $<in> in / $<out> out per MTok)`, rates from the pricing dict.
- `est-tick PROFILE MODEL_ID [--cache-hit 0.8] [--json]` — prints the estimate and its inputs.
  When `pricing["billing_mode"] == "subscription"`, append the note: `billing_mode is
  subscription — read this as API-equivalent burn, not dollars.`
- `check-budget USD PROFILE MODEL_ID [--cache-hit 0.8] [--json]` — prints est-tick, iterations
  bought, and the warning when present.
- `KeyError` from the pure functions → message on stderr, exit 2.

Docstring must state the purpose (feed aesop's abstract dials with numbers computed from
pricing.json — copy-paste, not a dependency), the first-in-file-order tier convention, and that
nothing here hardcodes a price or model id.

**Acceptance.**
- `python3 bin/aesop_bridge.py tiers --json` outputs a JSON object whose values are all keys of
  `pricing["models"]` and whose keys include `strong`, `mid`, `cheap`, `frontier`.
- `python3 bin/aesop_bridge.py est-tick S claude-sonnet-5` prints a positive dollar figure and
  the subscription note (current `billing_mode` is `subscription`).
- `python3 bin/aesop_bridge.py check-budget 25 M claude-sonnet-5` prints an iterations count.
- Unknown model exits 2 with a helpful message.
- Existing test suite still green; `data/pricing.json` untouched.

**Verify.**
```bash
cd /path/to/polytropos && python3 bin/aesop_bridge.py tiers --json | python3 -c "import json,sys; m=json.load(sys.stdin); p=json.load(open('data/pricing.json'))['models']; assert set(m) >= {'strong','mid','cheap','frontier'} and all(v in p for v in m.values()), m; print('tiers ok')" && python3 bin/aesop_bridge.py est-tick S claude-sonnet-5 && python3 bin/aesop_bridge.py check-budget 25 M claude-sonnet-5 && ! python3 bin/aesop_bridge.py est-tick S not-a-model 2>/dev/null && python3 -m unittest discover -s tests && git diff --quiet data/pricing.json && echo 'T7 OK'
```

---

### T8 — Regression tests for the budget bridge
- status: done
- model: sonnet
- depends: T7
- independent: no

**Brief.** Create `tests/test_aesop_bridge.py`, stdlib unittest, same conventions as
`tests/test_cost_report.py` (importlib `_load` off `BIN_DIR`; module docstring). Build a
**synthetic pricing fixture dict** in the test module — deliberately fake round numbers (e.g.
input 1.0, output 2.0, cache_read_multiplier 0.1) so the fixture never needs updating when real
prices change and can't be mistaken for real prices; include: two models sharing tier `"opus"`
(to prove first-wins), one `"frontier"`, one `"sonnet"` with `intro_pricing` (until
`"2099-01-01"` in one case and a past date in another — or vary `today`), one `"haiku"`, and a
`task_profiles` entry with round token counts.

Test cases (minimum):

1. `tier_map` returns the FIRST model per tier in insertion order and includes
   frontier/strong/mid/cheap; a fixture without a frontier model omits the key.
2. `est_tick` exact math: hand-compute the expected float for the fixture (assertAlmostEqual);
   cover `cache_hit=0.8` and `cache_hit=0` paths.
3. `intro_pricing` boundary via the `today` parameter: `today` == `until` applies intro rates;
   `today` one day after does not. No test may call the real clock for an assertion.
4. `check_budget`: iterations is the floor; warning present when iterations < 10 and `None`
   otherwise.
5. Unknown model id and unknown profile raise `KeyError` (message mentions valid choices).
6. One CLI smoke test: run `main(["tiers", "--json"])` against the REAL pricing.json (module
   default), capture stdout, assert it parses as JSON — no price value assertions.

**Acceptance.** All new tests pass; full suite green; no real price literals asserted anywhere.

**Verify.**
```bash
cd /path/to/polytropos && python3 -m unittest discover -s tests -p 'test_aesop_bridge.py' -v && python3 -m unittest discover -s tests && echo 'T8 OK'
```

*(Verify command amended during execution for the same site-packages `tests` shadowing issue as
T2 — dotted-module form replaced with pattern discovery.)*

---

*Phase 3 end — dispatch `aesop-bridge-reviewer` before starting Phase 4.*

---

## Phase 4 — Docs + handoff

### T9 — Write docs/AESOP-INTEGRATION.md
- status: done
- model: opus
- depends: T1–T8 (documents their output)
- independent: no

**Brief.** Create `docs/AESOP-INTEGRATION.md` — the user-facing integration guide AND the
proposal for aesop-side follow-ups. Read PLAN.md in full first; every aesop behavior claim must
carry the pin "as of aesop commit `5506617`" (state it once prominently, near the top). Do not
state current prices as facts anywhere — show commands, describe outputs generically, or label
example output as example. Required sections, exactly these five H2 headings:

1. `## Two layers, one boundary` — aesop = harness-portable environment compiler, deliberately
   price- and model-version-agnostic (tiers, pathways, budget stops); polytropos = the
   Claude-concrete pricing/routing layer (concrete model ids, live rates in `data/pricing.json`,
   task-size cost math, the Fable architect/execute posture). Integration = aesop consumes this
   repo; nothing here imports aesop.
2. `## Consume this repo as an aesop registry` — this repo's `skills/<name>/SKILL.md` layout
   already matches aesop's registry lookup. Show the `aesop.yaml` snippet
   (`registries:` with `github:agentmc15/polytropos`, and the `path:` variant
   `path:/path/to/polytropos` for local use) and the add
   commands (`aesop add skill route --from polytropos`, same for `fable-check`). Explain
   what vendoring does (copy into `.aesop/vendor/…`, upstream SHA pinned, the
   `references/pricing.json` snapshot rides along because aesop vendors the whole skill dir) and
   the refresh flow (`aesop update` → review diff → `--apply`; the snapshot refreshes when this
   repo re-runs `bin/sync_pricing_refs.py` and the consumer updates). Include the export-surface
   table: `route`, `fable-check` exported; `cost-report`, `setup` plugin-only (depend on `bin/`
   scripts, `~/.claude` paths, statusline wiring); `architect`, `execute` plugin-only (depend on
   Claude Code's Agent-tool `model` parameter and this plugin's kit contract) — one-line why
   each. Note: on this machine the plugin is already installed at user scope in Claude Code, so
   the registry path matters mainly for other harnesses (Codex, Cursor, Copilot…) and other
   people/teams.
3. `## Feed aesop's dials with real numbers` — `bin/aesop_bridge.py` recipes with example
   command lines: `tiers` (concrete model per aesop tier, for pinning models in profiles or
   agent frontmatter), `est-tick` (a per-iteration estimate for a goal recipe / the Ralph
   runner, whose default per-tick estimate is a flat $0.25 as of the pinned commit when the
   agent CLI emits no cost JSON), `check-budget` (how many iterations a profile's `budget_usd`
   actually buys — runway sanity check). Show a short "paste into aesop.yaml" example (a
   `loops:` entry with `stops:`) with placeholder numbers clearly marked as computed-at-your-desk
   values, plus the rule: numbers are computed from pricing.json at run time — recompute after
   any pricing.json update rather than treating pasted values as durable.
4. `## Kits in aesop-managed projects` — summarize the Phase-2 rules: detection (`aesop.yaml` at
   root or `<!-- aesop:begin` fence), compiled files are read-only, guardrails go to
   `aesop.yaml` `primitives.instructions.blocks` + `aesop compile`, kit dirs and kit-prefixed
   agents are safe because aesop tracks only files it emits, never reuse a manifest-listed agent
   name. Point at `skills/architect/SKILL.md` and `skills/execute/SKILL.md` as the operative
   text.
5. `## Proposed aesop-side follow-ups (live in the aesop repo, not here)` — numbered proposals,
   each with 1–2 sentences of rationale, explicitly flagged as changes for the aesop repo via
   its own phase-gated process: (a) extend the claude-code emitter's `MODEL_MAP` and
   federation's `CLAUDE_MODEL_MAP` (currently opus/sonnet/haiku ↔ strong/mid/cheap at the pinned
   commit) for the Claude 5 family, including whether Fable warrants a `frontier` tier — noting
   aesop's `src/types.ts`/schema are LOCKED and need explicit approval there; (b) allow
   profiles/manifest to pin concrete model ids per tier so `strong` can mean a specific model
   explicitly; (c) calibrate the Ralph runner's `estCostPerIterationUsd` default via
   `aesop_bridge.py est-tick` instead of the flat constant; (d) a `doctor` check comparing a
   goal's `budget_usd` against the estimated tick cost — runway warning, mirroring
   `check-budget`; (e) list polytropos in `registry/plugins/` as a worked claude-plugin
   example. Close the section with: these proposals are the natural input to running
   `/polytropos:architect` **in the aesop repo** as a separate kit.

Tone/format: match `docs/HOW-IT-WORKS.md` (plain markdown, tables where they earn it). Length
target 120–200 lines — complete but not padded.

**Acceptance.** File exists with exactly the five required H2 headings (verbatim); `5506617`
appears; referenced paths (`bin/aesop_bridge.py`, `bin/sync_pricing_refs.py`,
`skills/route/references/pricing.json`) exist in the repo; no current-price literals stated as
facts.

**Verify.**
```bash
cd /path/to/polytropos && grep -q '^## Two layers, one boundary' docs/AESOP-INTEGRATION.md && grep -q '^## Consume this repo as an aesop registry' docs/AESOP-INTEGRATION.md && grep -q "^## Feed aesop's dials with real numbers" docs/AESOP-INTEGRATION.md && grep -q '^## Kits in aesop-managed projects' docs/AESOP-INTEGRATION.md && grep -q '^## Proposed aesop-side follow-ups' docs/AESOP-INTEGRATION.md && grep -q '5506617' docs/AESOP-INTEGRATION.md && ls bin/aesop_bridge.py bin/sync_pricing_refs.py skills/route/references/pricing.json >/dev/null && echo 'T9 OK'
```

---

### T10 — README cross-link
- status: done
- model: sonnet
- depends: T9
- independent: no

**Brief.** `README.md` line 5 currently reads:
> **In-depth architecture guide:** [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md) (Markdown) · [docs/how-it-works.html](docs/how-it-works.html) (styled HTML — open in a browser).

Insert directly after it, as its own paragraph:
> **Aesop integration:** [docs/AESOP-INTEGRATION.md](docs/AESOP-INTEGRATION.md) — consume `route`/`fable-check` from [aesop](https://github.com/agentmc15/aesop) registries, and feed aesop's budget dials with numbers computed from `data/pricing.json` (`bin/aesop_bridge.py`).

Change nothing else. (If the Install/README sections have shifted since this brief was written —
harden-plugin edits README too — anchor on the architecture-guide line, which harden-plugin does
not touch; if it is gone, stop and report.)

**Acceptance.** The line is present verbatim after the architecture-guide line; git diff shows
only this addition.

**Verify.**
```bash
cd /path/to/polytropos && grep -q 'AESOP-INTEGRATION.md' README.md && grep -q 'aesop_bridge.py' README.md && echo 'T10 OK'
```

---

*Phase 4 end — dispatch `aesop-bridge-reviewer` for the final review, then run the overall
"done" check from PLAN.md.*
