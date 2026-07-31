# PLAN — harness-parity

Bring the **Copilot** and **Codex** harness bundles to command/agent parity with the Claude
Code plugin's skill surface. The Claude side ships 8 skills; the Copilot bundle
(`copilot/.github/agents/`) and the Codex bundle (`codex/prompts/`) each ship only 5
(route, architect, implementer, verifier, reviewer). This kit ports the four missing
capabilities to BOTH harnesses — **usage** (the cost-report port), **journal**,
**frontier-check** (the fable-check port), and **escalate** — as thin, hand-authored wrappers
over bin engines that already exist. Nothing new is computed; every number and model id is
derived at run time from that harness's own pricing file.

autonomy: advisory

## Goal

Eight new bundle files (4 Copilot agents + 4 Codex prompts), the Copilot manifest and both
bundle test files extended additively, and two one-paragraph instruction-surface updates —
with the full suite green and every frozen surface byte-untouched.

**Done looks like:**

1. `copilot/aesop.yaml` `primitives.agents` lists exactly
   `route, architect, implementer, verifier, reviewer, usage, journal, frontier-check, escalate`
   and `copilot/.github/agents/` holds the matching nine `*.agent.md` files
   (`tests/test_copilot_bundle.py` set-equality green).
2. `codex/prompts/` holds the matching nine `*.md` prompts and
   `tests/test_codex_bundle.py`'s expected-stems roster matches (its Case-2 test updated).
3. Every new Copilot agent's `model:` frontmatter pin is a live key of
   `data/pricing.copilot.json` at the pinned tier (`usage` → cheap; `journal`,
   `frontier-check`, `escalate` → mid). Every new Codex prompt has a `description:` and NO
   `model:` line, and no file under `codex/` contains any real model id from
   `data/pricing.codex.json` (both pre-existing test cases stay green over the larger roster).
4. `python3 -m unittest discover -s tests -v` fully green.
5. `git diff --quiet -- bin data skills .claude-plugin docs README.md` exits 0 — the engines,
   all three pricing files, the Claude skills, the plugin manifest, and the docs are
   byte-untouched. The ten pre-existing bundle files (5 agents + 5 prompts) are byte-untouched.
6. No file under `copilot/.github/` or `codex/` contains an absolute path,
   `${CLAUDE_PLUGIN_ROOT}`, another harness's pricing path, or (under `codex/`) the string
   "fable" in any case.

## Ground truth (verified against the tree at kit-build time — pinned so no executor needs it)

**Copilot bundle mechanism.** `copilot/aesop.yaml` is the source-of-truth manifest;
`aesop compile` is NEVER run in this repo (no node; the manifest header says edit the manifest
first, then the bundle, then rerun the tests). `tests/test_copilot_bundle.py` enforces
consistency: `ManifestAgentsMatchBundleTests` asserts manifest `primitives.agents` ==
`*.agent.md` stems (set equality — so a manifest edit and its agent file MUST land in the same
task); `ModelPinLiveTests` asserts every agent frontmatter `model:` is a key of
`data/pricing.copilot.json` `models`; `WORKFLOW_AGENT_TIERS` (module-level dict, ~line 174)
pins each agent's tier via data lookup, no model-id literals; `PlaceholderDisciplineTests` and
`HarnessSeparationTests` sweep every bundle file for absolute paths / `CLAUDE_PLUGIN_ROOT` /
`data/pricing.json` mentions. Agent frontmatter format: `name`, `description`, `model`, then
body. The installer (`bin/harness_select.py install --harness copilot`) globs
`*.agent.md` — new agents install with zero installer changes.

**Codex bundle mechanism.** There is deliberately NO `codex/aesop.yaml`.
`tests/test_codex_bundle.py` IS the enforcement: `EXPECTED_PROMPT_STEMS` (line ~50) currently
`{"route", "architect", "implementer", "verifier", "reviewer"}` with an exact-set roster test
named `test_prompt_roster_is_exactly_five`; `FrontmatterDisciplineTests` requires a
`description:` line and forbids a `model:` line in every expected prompt;
`NoHardcodedRosterTests` forbids ANY real `data/pricing.codex.json` model id anywhere under
`codex/`; `PlaceholderDisciplineTests` + `HarnessSeparationTests` sweep as on the Copilot
side (plus `data/pricing.copilot.json` mentions). Prompt format: `---\ndescription: ...\n---`
then body. The installer globs `codex/prompts/*.md` — zero installer changes.

**Engines reused read-only (real flags, verified from their argparse surfaces):**

- `bin/copilot_usage.py [--days N] [--top N] [--copilot-home DIR] [--session-dir DIR]` —
  reads `<copilot-home>/session-state/*/events.jsonl` strictly read-only, prices USD + AIC
  from `data/pricing.copilot.json`, emits markdown; multi-model sessions flagged `≈`;
  `totalNanoAiu` is a labeled cross-check, never converted.
- `bin/codex_usage.py [--days N] [--top N] [--codex-home DIR] [--json]` — reads
  `session_index.jsonl`, `history.jsonl`, `sessions/YYYY/MM/DD/*.jsonl` read-only; honesty
  ladder: tokens → priced table + verbatim subscription disclaimer; activity only → counted,
  unpriced; nothing → says so. Never a fabricated dollar.
- `bin/journal_collect.py [--date D] [--print] [--repo PATH ...] [--journal-dir ...]` and
  `bin/journal_summarize.py --date D --dry-run` (prints the three prompts, spawns nothing;
  WITHOUT `--dry-run` it dispatches the Claude CLI via `--claude-bin`), plus
  `bin/journal_askpack.py --date D --print` and `bin/journal_plan.py build|prompt|check|done|defer`.
- `bin/copilot_pricing.py models [--profile P] [--json] | est <PROFILE> <MODEL_ID> [--json] |
  runway <PLAN> <PROFILE> <MODEL_ID> [--json]`.
- `bin/codex_pricing.py models [--profile P] [--json] | est <PROFILE> <MODEL_OR_TIER> [--json] |
  plans [--json]` — `est` accepts a tier word (skip-up rule).
- `bin/copilot_execute.py run --kit <dir> [--task ID] [--agent A] [--max-escalations N]
  [--dry-run]` and `bin/codex_execute.py run --kit <dir> [--task ID] [--role R] [--effort E]
  [--max-escalations N] [--dry-run]` — both implement the tier-escalation ladder: tiers
  strictly ABOVE the start model's tier in `cheap→mid→strong→frontier` order, FIRST model in
  pricing-file order per tier, empty tiers skipped.

**Pricing shape.** Both files use the shared four-value tier vocabulary
`cheap|mid|strong|frontier`. The Copilot roster has exactly one frontier-tier model; the Codex
roster has three durable tiers (`strong` unpopulated — its `tier_note` pins the skip-up rule)
plus a `non-routing` entry the resolver never selects. Frontier ids are DERIVED at run time
(`models --json`, filter `tier == "frontier"`) — never written into a bundle body.

**Dispatch surfaces (already pinned in the shipped route files — copy from them, not memory):**
Copilot one-shot `copilot -p "<task>" --model <model-id>`; Codex one-shot
`codex exec "<task>" --model <model-id>` (add `--full-auto` when it must edit files), effort
knob `-c model_reasoning_effort=<minimal|low|medium|high|max>`.

## Decisions

- **D1 — Names: `usage`, `journal`, `frontier-check`, `escalate`, identical on both
  harnesses.** `cost-report` becomes `usage` (each harness reports its OWN home's usage via its
  own engine, not Claude transcripts). `fable-check` becomes `frontier-check` — a capability
  named after a Claude model is wrong on a non-Claude harness; the check is about the
  harness's frontier TIER, whatever model occupies it in the data. The string "fable" (any
  case) never appears under `codex/`. `journal` and `escalate` are harness-agnostic and keep
  their names.
- **D2 — Copilot ports are AGENTS, not skills.** They are invocable, model-pinnable surfaces
  like the existing five; `primitives.skills` stays `[lessons-loop]`. Every Copilot capability
  lands as ONE task doing the three-step atomically: manifest `primitives.agents` entry +
  hand-authored `.agent.md` + additive test extension — because the roster test is set
  equality, splitting the steps would leave the suite red between tasks.
- **D3 — Codex ports are PROMPTS + the roster test, atomically.** Same reasoning:
  `EXPECTED_PROMPT_STEMS` is an exact set, so each new prompt file and its stems-entry land in
  one task. `codex/AGENTS.md` is touched only by T9's pinned paragraph.
- **D4 — Thin wrappers; engines never edited, never re-implemented.** Each bundle file
  instructs shelling to the existing engine with its REAL flags (pinned above) and interprets
  the output. No new math in prose, no new scripts, no `bin/harness_select.py` changes (its
  globs already install new files).
- **D5 — Frontier derivation at run time; one sanctioned model-id literal.** Bodies instruct
  `models --json` / `est <PROFILE> frontier` and never name the frontier model statically. The
  ONE sanctioned model-id literal in this kit is the Copilot `.agent.md` frontmatter `model:`
  pin — required by the format, kept live by `ModelPinLiveTests`, and always NON-frontier here
  (usage → cheap tier; journal/frontier-check/escalate → mid tier, matching the existing
  route/implementer precedent). Implementers read the pin's id from
  `data/pricing.copilot.json` at implementation time (first model in file order carrying the
  tier), never from this kit's text.
- **D6 — The ported journal is the in-session two-pass flow ONLY.** Collect →
  `journal_summarize.py --date <d> --dry-run` → the harness's own model writes the three
  documents itself. Headless `journal_summarize.py` (no `--dry-run`) dispatches the CLAUDE
  CLI — a cross-harness spend a Copilot/Codex bundle file must never recommend. The engine
  itself is harness-agnostic (reads all three homes read-only), so the journal produced is the
  same cross-harness journal.
- **D7 — The ported escalate mirrors the execute drivers' ladder.** Verify command first;
  cheapest sufficient tier; one same-model retry carrying the exact failure output; then climb
  the ladder exactly as `copilot_execute.py`/`codex_execute.py` do (strictly-above tiers,
  first-in-file-order, skip empty), derived from the pricing data at run time; frontier last,
  evidence-carrying. For kit tasks the bundle file points at the execute driver itself. The
  `copilot -p`/`codex exec` lines are RUNTIME instructions inside bundle text — no test or
  verify command in this kit ever executes them.
- **D8 — Test evolution is additive at pinned seams only.** Copilot: new entries in
  `WORKFLOW_AGENT_TIERS` + one new `PortedAgentContractTests` class grown across T1/T3/T5/T7.
  Codex: a new module-level `PORTED_PROMPT_STEMS` tuple folded into `EXPECTED_PROMPT_STEMS`,
  the roster test renamed ONCE (T2) to `test_prompt_roster_matches_expected_stems` (the old
  name hardcodes "five"), + one new `PortedPromptContractTests` class grown across
  T2/T4/T6/T8. Every other class/method stays byte-intact.
- **D9 — Executor pins: sonnet authors, haiku does the mechanical closeout.** Routing
  evidence across 14 kits (62/63 first-try; the sibling copilot-harness/codex-harness kits ran
  clean on the standard mix): sonnet for the eight authoring tasks (T1–T8), haiku for the
  pinned-verbatim instruction insertions (T9) and the final audit (T10). No opus task — the
  hard judgment (ladder semantics, frontier derivation, honesty framing) is pinned in the
  briefs; the per-task escalation valve covers surprises.
- **D10 — Instruction surfaces get one pinned sentence each, manifest-first.** The Copilot
  sentence lands in `copilot/aesop.yaml`'s instructions block AND verbatim in
  `copilot/.github/copilot-instructions.md` (the manifest is source of truth; the bundle
  mirrors it). The Codex paragraph lands in `codex/AGENTS.md`. Append-only; the two doctrine
  sentences stay byte-intact (test-enforced).

## OUT-OF-SCOPE fence (do NOT build)

- **No Claude-side changes**: `skills/`, `.claude-plugin/`, `bin/`, `data/` (all three pricing
  files), `docs/`, `README.md`, statusline — all byte-untouched. Parity needs no Claude edit.
- **No edits to the ten pre-existing bundle files** (five `.agent.md`, five prompt `.md`) or
  to `copilot/.github/skills/lessons-loop/`.
- **No new Copilot skills** (agents only), no Ralph-loop work, no lessons-loop changes, no
  MCP/config surfaces, no `bin/harness_select.py` changes, no new bin scripts, no new engines.
- **No `aesop compile`, no node/npm**, no network, no web fetches — every fact needed is
  pinned here or readable in-repo.
- **Never invoke the real `copilot`, `codex`, or `claude` CLI** from any task, test, or verify
  command — they spend real credits/limits and hit the network. Bundle BODIES may contain
  such command lines as runtime instructions; nothing in this kit runs them.
- **Nothing outside this repo** — `~/.copilot`, `~/.codex`, `~/.claude` included.
- No commit, no push.

## Risks & tripwires

- **Roster set-equality tripwire**: adding a manifest entry without its `.agent.md` (or vice
  versa), or a Codex prompt without its stems-entry, turns the suite red. The three-step (or
  two-step) is atomic per task; verify at every task boundary.
- **The fable→frontier naming trap**: a lazy port copies "Fable" into a non-Claude file. Under
  `codex/` this is contract-tested ("fable" absent, any case); on the Copilot side the frontier
  model IS an Anthropic model, so prose drift is likelier — new Copilot bodies say "the
  frontier-tier model in the data", never a static model name/id.
- **Hardcoded-model-id leak**: `codex/` is swept by `NoHardcodedRosterTests`; `copilot/` has no
  equivalent sweep, so the verifier must hand-audit new agent BODIES for pricing-file model
  ids (frontmatter pins excepted per D5).
- **Absolute-path / placeholder leakage**: every engine path in a bundle file is
  `{{POLYTROPOS_ROOT}}/bin/...`; a resolved path or `${CLAUDE_PLUGIN_ROOT}` fails the
  sweeps.
- **Codex proxy-not-a-bill drift**: the usage/frontier-check/escalate prompts must keep the
  billing-mode-first honesty — a subscription dollar figure is a labeled API-equivalent proxy,
  never a bill. Copy the framing from `codex/prompts/route.md` and `codex/AGENTS.md`.
- **The journal headless trap**: recommending `journal_summarize.py` WITHOUT `--dry-run` from
  a Copilot/Codex file silently dispatches the Claude CLI (D6). Contract-tested for
  `--dry-run` presence.
- **Doctrine-sentence breakage**: T9's appends must not touch the two doctrine sentences
  (byte-verbatim tests on both sides).
- **Manifest indentation**: `copilot/aesop.yaml` is parsed by a line-oriented,
  indentation-based helper — new `- <name>` entries match the existing entries' exact
  indentation, and the instructions-block sentence lands INSIDE the `content: |` block's
  indentation.

## Phases

- **Phase 1 — easy wins (engines already exist):** `usage` and `journal` on both harnesses
  (T1–T4).
- **Phase 2 — frontier adaptations:** `frontier-check` and `escalate` on both harnesses
  (T5–T8).
- **Phase 3 — closeout:** instruction surfaces (T9) + full-suite/frozen-surface audit (T10).

Two independent serial lanes run in parallel: the Copilot lane (T1→T3→T5→T7 — shared files
`copilot/aesop.yaml` + `tests/test_copilot_bundle.py`) and the Codex lane (T2→T4→T6→T8 —
shared file `tests/test_codex_bundle.py`). T9 needs both lanes done; T10 needs T9.
