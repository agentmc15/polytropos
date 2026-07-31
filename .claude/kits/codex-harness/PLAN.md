# PLAN — codex-harness

Make polytropos usable for **OpenAI Codex (the Codex CLI)** as a full third harness,
mirroring the existing GitHub Copilot harness: Codex pricing data for the new **GPT-5.6 family
(Sol / Terra / Luna)**, a `route` equivalent, a workflow-agent surface + execute driver so kits
can run on Codex, a read-only usage reader, and a `codex` target in `bin/harness_select.py`.
The user's goals are **accuracy and speed**: never fabricate a dollar figure for a
subscription-limited run, and surface GPT-5.6's real speed levers (Codex **fast mode**, Luna,
Sol-on-Cerebras) instead of guessing.

Templates for everything here already exist in this repo: `data/pricing.copilot.json`,
`bin/copilot_pricing.py` / `copilot_execute.py` / `copilot_usage.py`, the `copilot/.github/`
bundle, and `bin/harness_select.py`. This kit ports the pattern; it does not redesign it.

autonomy: advisory

## Goal

Ship the Codex harness end-to-end verified, **without ever invoking the real `codex` CLI**:

1. **`data/pricing.codex.json`** — the third numeric source of truth: GPT-5.6 Sol/Terra/Luna
   API rates (from the 2026-06-26 "Previewing GPT-5.6 Sol" post, transcribed verbatim in T2's
   brief), the GPT-5.6 cache multipliers, ChatGPT plan facts with **honestly-null allowances**,
   and the new knobs (`max` reasoning effort, `ultra` mode, Codex fast mode) as data.
2. **`bin/codex_pricing.py`** — cost engine (`models` / `est` / `plans`) that always prints BOTH
   framings: real API dollars, and the subscription line (`billed_usd: null` + a labeled
   API-equivalent proxy + a burn index vs the cheapest model). No `runway` — no fixed Codex
   allowance exists to divide by.
3. **`codex/` bundle** — Codex's native config surfaces: `codex/AGENTS.md` (instructions) +
   `codex/prompts/{route,architect,implementer,verifier,reviewer}.md` (custom prompts), all
   carrying `{{POLYTROPOS_ROOT}}`, never an absolute path.
4. **`bin/harness_select.py` extended** with a `codex` harness (`--codex-home`, dry-run,
   AGENTS.md no-clobber rule). Existing `claude-code`/`copilot` behavior byte-stable.
5. **`bin/codex_execute.py`** — the kit-dispatch driver (status/run/review, injectable runners,
   `--dry-run`, tier-data-driven escalation) so execution kits can run on Codex.
6. **`bin/codex_usage.py`** — strictly read-only `~/.codex` usage report with an honesty
   ladder: price only tokens actually found in the logs; otherwise count activity, unpriced.

**Done looks like:** `python3 -m unittest discover -s tests -v` green including four new files
(`test_codex_pricing.py`, `test_codex_bundle.py`, `test_codex_execute.py`,
`test_codex_usage.py`) with every pre-existing test file byte-untouched;
`python3 bin/codex_pricing.py models --profile M` prints the roster with API-USD estimates and
burn indexes; `est` output always shows `billed_usd: null`-style subscription framing;
`harness_select.py install --harness codex --codex-home <tmp>` materializes prompts +
AGENTS.md with the placeholder resolved and skips a pre-existing differing AGENTS.md;
`codex_execute.py run --dry-run` against a fixture kit prints a `codex exec` argv and spawns
nothing; `codex_usage.py` against a synthetic `--codex-home` prints an honest report;
`docs/CODEX-HARNESS.md` exists; `.claude/kits/codex-harness/RESEARCH.md` records the T1 peek;
`data/pricing.json`, `data/pricing.copilot.json`, `bin/journal_*.py`, `skills/`, and all prior
test files are byte-identical to git HEAD.

## Ground truth: the GPT-5.6 article (2026-06-26, "Previewing GPT-5.6 Sol")

Pinned here and verbatim in T2 so no executor needs the network:

- Three **durable capability tiers** (number = generation, name = tier):
  **Sol** — flagship/most capable, **$5 / 1M input, $30 / 1M output**;
  **Terra** — balanced everyday model (competitive with GPT-5.5 at 2× cheaper),
  **$2.50 / 1M input, $15 / 1M output**;
  **Luna** — fast & affordable, **$1 / 1M input, $6 / 1M output**.
- **Caching (GPT-5.6 and later):** explicit cache breakpoints, 30-minute minimum cache life;
  cache **writes 1.25×** the uncached input rate; cache **reads 0.1×** (the 90% discount).
- **New knobs:** `max` reasoning effort (deepest); `ultra` mode (subagent acceleration);
  Codex **fast mode** for priority/time-sensitive processing (the article's speed lever).
- **Availability:** limited preview "through the API and Codex to a select group of trusted
  partners"; broader ChatGPT/Codex/API availability "soon". Sol also launches on Cerebras at up
  to 750 tokens/sec.
- The article gives **no model id strings** and **no subscription quota numbers**. Both are
  therefore pinned as UNCONFIRMED (see Risks) — never as fact.

## Codex CLI config surface (architect findings, confidence-labeled)

Pinned from Codex CLI public docs/source knowledge; **NOT live-verified** (verification would
spend the user's quota — forbidden). T1's sanctioned read-only peek is the one confirm step.

- **Confirmed-by-repo (this machine):** `~/.codex/session_index.jsonl`
  (`id`/`thread_name`/`updated_at`) and `~/.codex/history.jsonl` (`session_id`/`ts`/`text`)
  carry session id + timestamp + free text only — no model, no cwd, no token usage. Source:
  `bin/journal_sources.py` lines ~307–336 (the daily-journal kit's sanctioned research).
- **High confidence:** `~/.codex/config.toml` is the config file (`model`,
  `model_reasoning_effort`, `[profiles.<name>]`, approval/sandbox settings; `$CODEX_HOME`
  overrides `~/.codex`); `AGENTS.md` is the instructions surface (global `~/.codex/AGENTS.md`,
  plus project-root and subdirectory files); `~/.codex/prompts/*.md` are custom prompts invoked
  as `/name` in the TUI; `codex exec "<prompt>"` is non-interactive mode with `--model`,
  `-c key=value` overrides, `--full-auto`, `--sandbox <mode>`, `--json`, `-C <dir>`,
  `--profile <name>`; sessions are rollout JSONL files under `~/.codex/sessions/YYYY/MM/DD/`.
- **Medium confidence (T1 confirms):** rollout records include `session_meta` /
  `turn_context` (model, cwd) / `event_msg` records where `token_count` payloads carry
  `info.total_token_usage` / `last_token_usage` (`input_tokens`, `cached_input_tokens`,
  `output_tokens`, `reasoning_output_tokens`). This is the usage surface `codex_usage.py`
  targets; it degrades honestly if absent.
- **Known differences from Copilot that shape the port:** Codex has **no custom-agent files**
  and **no per-prompt `model:` pin** — model choice per dispatch is only the CLI/`-c`/profile
  surface; and home-level `AGENTS.md` is a **single shared file** (installing it can clobber a
  user's own global instructions — hence D6's no-clobber rule), unlike Copilot's per-file
  namespaced `agents/` dir.
- **Unknown / flagged:** exact GPT-5.6 model id strings; whether the user's ChatGPT plan
  includes GPT-5.6 during the limited preview; the CLI surface for **fast mode** and **ultra**
  (no flag is invented anywhere); whether custom prompts tolerate frontmatter in the user's
  installed version (D5 keeps it minimal and cosmetic-if-wrong).

## Architecture & key decisions

- **D1 — Additive layout, mirroring the Copilot side; nothing moves.** New trees only:
  `data/pricing.codex.json`; `bin/codex_pricing.py`, `bin/codex_execute.py`,
  `bin/codex_usage.py`; the `codex/` bundle (`AGENTS.md` + `prompts/`); four new test files;
  `docs/CODEX-HARNESS.md`; `.claude/kits/codex-harness/RESEARCH.md`. The ONLY existing files
  edited are `bin/harness_select.py` (D6), `README.md` and `CLAUDE.md` (pinned insertions).
  Rationale: the Claude plugin is live-installed from this directory and the Copilot harness is
  shipped and tested — the cheapest correct port is a sibling tree with the same conventions.

- **D2 — `data/pricing.codex.json` schema: mirror `pricing.copilot.json` where it helps,
  diverge where OpenAI's billing demands.** Shared fields: `cached_date`, `update_from`,
  `model_ids_note`, `models` (with `display`/`vendor`/`tier`/`input_per_mtok`/
  `output_per_mtok`/`notes`), `task_profiles` (XS–XL duplicated — task-size conventions, not
  prices; every pricing file is self-contained). Divergences, each with a reason:
  - **`billing_modes` object instead of Copilot's `billing_unit`.** OpenAI has two disjoint
    ways to pay for Codex: API metering (dollars per token — the article's numbers) and ChatGPT
    subscription plans (opaque usage/rate limits — NOT dollars). There is no AIC-like published
    conversion between them, so the file encodes both modes with honest notes instead of
    inventing a unit.
  - **Global cache multipliers, not absolute cached rates.** The article publishes
    generation-wide multipliers (reads 0.1×, writes 1.25×, 30-min minimum life), so the file
    carries top-level `cache_read_multiplier` / `cache_write_multiplier` /
    `cache_min_life_minutes` (the `data/pricing.json` style), and the engine computes cached
    rates at run time. Copilot stores absolute cached rates only because GitHub publishes them
    that way.
  - **`plans` with `included_usage: null` everywhere.** ChatGPT Plus/Pro/Business/Enterprise
    have usage limits, not token allowances; no fixed number exists to encode. Known monthly
    prices are data; allowances are null with notes. A fabricated allowance would be exactly
    the wrong answer this kit exists to avoid.
  - **A `knobs` object** for `reasoning_efforts` (including the new `max`), `ultra`, and
    `fast` mode — capability facts the route surface must surface for the speed goal, kept as
    data so prose never hardcodes them. No pricing is attached to fast/ultra (unpublished).
  - **Roster = exactly the three GPT-5.6 models.** Only their rates are authoritative (the
    article). Padding the roster with guessed rates for other Codex-selectable models would
    violate accuracy; `model_ids_note` says the roster is minimal by design and how to extend.

- **D3 — Subscription vs API cost representation (THE central decision): dual framing, always
  both, never a fabricated bill.** Codex under a ChatGPT plan draws down usage limits; the
  $5/$30-style numbers are API-metered prices. So `codex_pricing.py est` has **no `--mode`
  flag** and always prints BOTH framings:
  - `api`: the real dollar estimate (authoritative for API-key users).
  - `subscription`: `billed_usd: null` (subscription runs are not token-billed) + the same
    dollar figure explicitly labeled **"API-equivalent (relative-burn proxy, not a bill)"** +
    a **burn index** = this estimate ÷ the cheapest same-profile estimate on the roster
    (computed from the data at run time; with today's roster the divisor is Luna).
  Rationale: for routing decisions a subscription user needs *relative* consumption (a Sol run
  burns limits roughly like its relative compute), and API dollars are the only published
  proxy for that — legitimate when labeled, a lie when presented as a bill. The route prompt
  must first establish which mode the user is in (ChatGPT sign-in vs `OPENAI_API_KEY`) and
  lead with the matching framing. **No `runway` subcommand**: there is no fixed allowance to
  divide by; a `plans` subcommand prints the plan facts + notes instead. Tripwire: if OpenAI
  publishes quantified Codex allowances, add runway THEN (new kit), never before.

- **D4 — Tier map: `sol=frontier`, `terra=mid`, `luna=cheap`; `strong` deliberately
  unpopulated; empty tiers are SKIPPED upward.** The four-value tier vocabulary
  (`cheap|mid|strong|frontier`) is shared across all three harnesses so kits and routing prose
  port unchanged; OpenAI ships three durable tiers, so one vocabulary slot stays empty. Sol is
  the roster's reach-for-it-deliberately model (5× Luna on input) → frontier; Terra is the
  everyday workhorse → mid; Luna → cheap. Consequence, pinned as one rule implemented in BOTH
  `codex_pricing.py` (`resolve_tier`) and `codex_execute.py`: **resolving a tier to a model
  takes the first model in pricing-file order carrying that tier, and if the tier is
  unpopulated, the next populated tier UP** (`strong` → Sol today); the escalation ladder
  likewise skips empty tiers. Tested against a synthetic roster with a different empty tier so
  the rule, not today's data, is what's proven.

- **D5 — Bundle shape: `AGENTS.md` + `prompts/`, roles as custom prompts, model pins live in
  the driver/data — never in prompt files; no `config.toml` is ever written; no `aesop.yaml`.**
  Codex has no `.agent.md` equivalent, so the five role surfaces are custom prompts
  (`/route`, `/architect`, `/implementer`, `/verifier`, `/reviewer` interactively) whose bodies
  double as the execute driver's dispatch preambles (one authored source, two consumers).
  Because prompts cannot pin models, per-role models are expressed as TIERS resolved from
  `data/pricing.codex.json` at run time (D4 rule): route/implementer → `mid`, verifier →
  `cheap`, reviewer → `strong` (resolves upward to Sol while strong is empty), architect →
  `frontier`. Rationale for the pins: identical role→tier judgment to the Copilot side
  (architect=frontier, implementer=mid workhorse, verifier=cheap mechanical, reviewer=strong
  judgment). Prompt files carry at most a `description:` frontmatter line (documented Codex
  feature; cosmetic if an older CLI renders it literally — accepted risk). The installer NEVER
  touches `config.toml` (a live user file; TOML merging is invasive) — users who want
  `[profiles.*]` pins get the exact lines from `codex_pricing.py models` output + docs. No
  `codex/aesop.yaml`: aesop@5506617 has no codex emitter, so the manifest would assert a
  compile target that cannot exist; `tests/test_codex_bundle.py` carries the consistency
  enforcement directly.

- **D6 — Installer: extend `bin/harness_select.py` (not a separate script), with an AGENTS.md
  no-clobber rule.** One installer already owns "materialize a bundle into a harness home,
  resolving `{{POLYTROPOS_ROOT}}`"; a second script would fork that logic. Extension is
  additive: `detect()` gains a `"codex"` key (`shutil.which("codex")`); `install --harness
  codex [--codex-home PATH] [--dry-run]` copies `codex/prompts/*.md` →
  `<home>/prompts/<name>.md` (placeholder → absolute repo root, exactly the Copilot mechanism)
  and handles `codex/AGENTS.md` → `<home>/AGENTS.md` specially: **write if absent; if present
  and byte-identical (post-resolution) report up-to-date; if present and different, SKIP with a
  printed manual-merge instruction — never overwrite.** Rationale: `~/.codex/AGENTS.md` is a
  single shared file that may hold the user's own global instructions; Copilot's per-file
  namespacing made overwriting safe, Codex's sharing makes it destructive. Existing
  claude-code/copilot code paths stay byte-identical in behavior; new installer tests live in
  `tests/test_codex_bundle.py`, and the ONLY pre-existing-test change anywhere in the kit is
  T7's pinned surgery on `test_detect_key_and_boolean_combinations` in
  `tests/test_harness_select.py` (its hardcoded two-key `detect()` expectations must learn the
  `codex` key).

- **D7 — Execute driver: `bin/codex_execute.py`, a close port of `bin/copilot_execute.py` with
  three Codex adaptations.** Same shape: `status`/`run`/`review` subcommands, kit parsing
  (`tasks/kits/<slug>/` in consumer repos, same TASKS.md grammar and
  `pending|in-progress|done|blocked` vocabulary), injectable `runner`/`verify_runner`
  callables, `--dry-run` prints argv and spawns nothing, argv lists never `shell=True`,
  statuses/NOTES writeback owned by the driver. Adaptations:
  1. **Dispatch anatomy** (best-effort, labeled not-live-verified exactly like
     copilot_execute's `--model` precedence note): `[codex_bin, "exec", "--model", <id>,
     "--full-auto"] + (["-c", "model_reasoning_effort=" + effort] if --effort given) +
     extra_args + [<preamble + brief>]`. `--full-auto` is the non-interactive permission grant
     (Copilot's `--allow-all-tools` analogue); a repeatable `--extra-arg` covers
     `--sandbox`/`--skip-git-repo-check`/future fast-mode flags. **No fast/ultra flag is
     invented** — when OpenAI publishes the surface it arrives via `--extra-arg` or a new kit.
  2. **Role preambles replace `--agent`:** Codex has no custom-agent dispatch, so the driver
     prepends the role's prompt body (read from the repo bundle `codex/prompts/<role>.md`,
     frontmatter stripped, placeholder resolved in memory at run time) to the task brief.
  3. **The task `model` field accepts a model id OR a tier word** (`cheap|mid|strong|
     frontier`, resolved via the D4 rule). Rationale: GPT-5.6 ids are unconfirmed; tier words
     let kits survive an id correction that lands only in the pricing file. Escalation ladder:
     strictly-above tiers of the pinned/resolved model, skipping empty tiers, first model in
     file order per tier, evidence (verify command, exit code, output tail) appended on
     re-dispatch, ladder exhausted ⇒ `blocked` — the copilot D3 semantics verbatim.

- **D8 — Usage reader: `bin/codex_usage.py`, standalone, with an honesty ladder.** Reads,
  strictly read-only and JSONL-text-only, under `--codex-home` (runtime default `~/.codex`;
  tests always override): `session_index.jsonl`, `history.jsonl`, and rollout files under
  `sessions/` (date-pruned via the `YYYY/MM/DD` path layout before opening; never a `*.db`).
  Tolerant candidate-key extraction owns its OWN constants (a superset of
  `journal_sources.py`'s `CODEX_*` lists plus the rollout candidates from T1's peek) — the
  journal adapter is deliberately NOT imported or edited: the journal's "Codex counted, never
  priced" invariant stays frozen, and this reader is the one place Codex tokens may be priced.
  Honesty ladder, in order: tokens found → price them from `pricing.codex.json` under the D3
  dual framing (tokens + API-USD + the standing subscription disclaimer; cache reads priced at
  the read multiplier when cached-token counts exist); no tokens found → activity counts
  (sessions/records/models seen) plus the explicit note "no token usage found in these logs —
  activity counted, unpriced"; no home/no files → say so. Never a fabricated or zeroed dollar
  stand-in.

- **D9 — Research protocol: exactly ONE sanctioned read-only peek at the real `~/.codex`
  (T1), findings pinned in `RESEARCH.md`.** Precedent: the daily-journal kit's D1-sanctioned
  peek. Bounds: `ls`-level listings, `head -c`-bounded reads of at most one rollout file,
  `config.toml`, `session_index.jsonl`, `history.jsonl`; text/JSONL/TOML only; never a `*.db`;
  never a write; never the `codex` binary; never from a test. Findings go in
  `.claude/kits/codex-harness/RESEARCH.md` (a task-owned kit file — distinct from NOTES.md,
  which execute owns) recording key NAMES/shapes and model-id strings only — no prompt or
  transcript text (journal-style content hygiene). T2 (pricing ids), T9 (dispatch anatomy
  notes), and T11 (usage keys) consume it. Everything else in the kit uses synthetic fixtures
  in temp `--codex-home` dirs.

- **D10 — Conventions: stdlib-only, frozen prior tests, same `bin/`/`tests/` idioms.** New
  scripts follow the house pattern (module docstring stating sources of truth and safety
  rules, pure functions taking the pricing dict / explicit roots, `main(argv=None)`, argparse
  subcommands, `--json`, KeyError → stderr + exit 2). New tests: stdlib `unittest`, importlib
  `_load` off `BIN_DIR`, synthetic fixtures with deliberately fake round numbers (e.g. a
  fixture cache multiplier ≠ 0.1 proves nothing is hardcoded), no wall-clock assertions,
  discovery form `python3 -m unittest discover -s tests` only (dotted-module form is broken on
  this machine). Every pre-existing test file stays byte-untouched.

## Constraints and OUT-OF-SCOPE fence

Executors must NOT:

- **Invoke the real `codex` CLI in ANY form** — it spends the user's real subscription
  quota/API dollars and hits the network, and a live `~/.codex` exists. Every dispatch goes
  through an injectable runner; tests stub or mock every dispatch (temp stub executables and
  temp `--codex-home` dirs only); `--dry-run` / `--demo` are the only sanctioned CLI smoke
  paths. Same rule as the copilot kits, same severity.
- **Read or write the real `~/.codex` from any test or verify command.** The ONE exception is
  T1's bounded read-only research peek (D9), performed once, by that task only. At run time the
  shipped scripts read `~/.codex` strictly read-only, JSONL/TOML text only — never a
  `*.db`/SQLite open, never a write. The installer runs only against temp `--codex-home` dirs
  during this kit and never writes `config.toml` anywhere, ever.
- **Touch `~/.claude/`, `~/.copilot/`, or anything outside this repo.** No plugin re-install.
- **Edit `data/pricing.json` or `data/pricing.copilot.json`.** The three pricing files never
  merge and no harness reads another harness's file. `data/pricing.codex.json` is created by T2
  and edited by no other task.
- **Touch `bin/journal_*.py` or the journal invariant.** The daily journal keeps counting Codex
  and NEVER pricing it — `pricing.codex.json` is for the codex harness only and must not be
  retrofitted into any journal script, skill, or test.
- **Hardcode prices, plan facts, quota values, multipliers, or model ids** into `codex/`
  bundle content or `bin/` scripts — derive from `data/pricing.codex.json` at run time. The
  four-value tier vocabulary, the D4 skip-up rule, and synthetic test fixtures are the
  sanctioned literals. Docs tables are labeled snapshots tied to the file's `cached_date`.
- **Present a subscription run with an unlabeled dollar figure.** Every subscription-framing
  number is `billed_usd: null` plus a proxy explicitly labeled as such (D3).
- **Write an absolute path into `codex/`** — bundle files carry `{{POLYTROPOS_ROOT}}`;
  only the installer resolves it (into installed copies / in-memory), never into the bundle.
- **Edit existing files beyond the sanctioned set**: `bin/harness_select.py` (T7, additive),
  `README.md` (T13 pinned insertion), `CLAUDE.md` (T14 pinned insertions), and — the ONE
  pre-existing-test exception — the single method
  `test_detect_key_and_boolean_combinations` in `tests/test_harness_select.py` (T7's pinned
  surgery: it hardcodes two-key `detect()` expectations that the additive `codex` key breaks;
  every other line of that file and every other pre-existing test file stays byte-untouched —
  codex installer tests go in `tests/test_codex_bundle.py`). `skills/`, `.claude-plugin/`,
  and the completed kits and their agents stay byte-untouched.
- **Invent unknowns**: no fabricated GPT-5.6 model ids beyond the pinned best-effort strings
  (correctable in ONE place, `data/pricing.codex.json`), no invented fast/ultra CLI flags or
  price multipliers, no invented plan allowances or post-preview availability claims, no
  `runway` subcommand.
- **Add node/npm/aesop work, new Claude Code skills, or any dependency.** Python stays
  stdlib-only; no `codex/aesop.yaml` (D5).
- **Commit or push.**

## Risks & tripwires

- **Unconfirmed GPT-5.6 model ids (the big one).** The article names tiers, not ids. T2 pins
  `gpt-5.6-sol` / `gpt-5.6-terra` / `gpt-5.6-luna` (the lowercase-dot-version convention the
  Copilot file's doc-confirmed `gpt-5.3-codex` follows), flagged UNCONFIRMED in
  `model_ids_note`. T1's peek may surface real id strings from `config.toml` or rollout
  `turn_context` records — if it does, T2 uses those and records the substitution. Tripwire:
  any executor finding authoritative ids that contradict the data file STOPS and reports;
  corrections land only in `data/pricing.codex.json` (and the docs snapshot with it), never
  silently, never in prose.
- **Subscription inclusion of GPT-5.6 is unconfirmed.** The preview is gated to "trusted
  partners"; "included with the subscription" is the user's expectation, not a published fact.
  Encoded as a note on `billing_modes.subscription` + surfaced by the route prompt ("if
  `/model` doesn't list GPT-5.6, your plan doesn't have it yet — route among what it lists").
  Tripwire: no task may claim plan inclusion as fact.
- **Thin `~/.codex` usage data.** The confirmed index/history files carry no tokens; rollout
  token records are medium-confidence. `codex_usage.py` is built to degrade (D8 honesty
  ladder) and its tests prove BOTH branches on synthetic fixtures. Tripwire: if T1 finds no
  usage fields anywhere, the usage report still ships — as an activity counter with the honest
  note — and nobody bolts on an estimate.
- **Dispatch anatomy not live-verified.** `codex exec` flags are pinned at medium confidence
  and asserted as a kit contract (the copilot_execute precedent). Tripwire: if T1's peek or
  repo reality contradicts a pinned flag, stop and report — do not guess a replacement; the
  injectable-runner design means a flag fix is a one-constant change later.
- **AGENTS.md clobber hazard.** `<home>/AGENTS.md` may be the user's own file. D6's no-clobber
  rule is mandatory and test-enforced (pre-seeded differing file survives an install
  byte-identical). Tripwire: any install code path that overwrites a differing AGENTS.md is a
  blocking defect.
- **Empty `strong` tier.** Three models, four tier slots. The D4 skip-up rule is implemented
  twice (engine + driver) — tests must exercise a synthetic roster with a DIFFERENT empty tier
  so the rule generalizes. Tripwire: a reviewer finding either implementation hardcoding
  "strong→sol" by id fails the phase.
- **Fast mode is the user's speed lever but its surface is unpublished.** It lives in the data
  (`knobs.modes.fast`, note-only) and in route-prompt prose telling the user it exists and to
  check release notes; Luna and Sol-on-Cerebras are the speed facts we CAN state. Tripwire: no
  invented flag, id suffix, or price multiplier for fast/ultra anywhere.
- **Custom-prompt frontmatter tolerance.** `description:` frontmatter is documented but older
  CLIs might render it literally — cosmetic, accepted (D5). Tripwire: nothing functional may
  live in prompt frontmatter.
- **Docs churn.** Codex CLI ships fast. Every capability claim above is confidence-labeled;
  `cached_date` dates the prices; `update_from` names where to re-check. Executors stop and
  report contradictions rather than improvising.
- **Live-install hazard.** Any stray edit under `skills/` or `.claude-plugin/` changes the
  user's live Claude Code behavior immediately. The verifier sweeps `git status` on every task.
- **Site-packages `tests` shadowing.** Verify commands use
  `python3 -m unittest discover -s tests [-p '<file>.py']` — never the dotted-module form.

## Deferred (designed, not built)

1. **Runway/quota tracking** — the moment OpenAI publishes quantified Codex allowances or a
   local rate-limit surface appears in `~/.codex`, port `runway` + a statusline-style burn
   gauge.
2. **Fast/ultra dispatch wiring** — when the CLI surface is published, add a driver flag and a
   priced entry (if priced) to the data file.
3. **Journal Codex pricing** — deliberately NEVER, unless the user explicitly reverses the
   "counted, unpriced" invariant; not this kit's call.
4. **A Ralph-loop port for Codex** — `bin/copilot_ralph.py` is the template; wait until the
   execute driver has real mileage.
5. **Roster expansion** — other Codex-selectable models (GPT-5.5 etc.) once authoritative
   Codex-side rates are captured; the schema already accommodates them.
