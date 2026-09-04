# docs-site — the 39-skill SKILL.md audit (D1 dispositions)

Read against PLAN.md D1 (the three-way content rule) and GUARDRAILS.md. Every one of the
39 SKILL.md files was read in full. **No skill file is edited by this task** — this is the
disposition record that T9–T14 apply.

## Method

- **Roster re-derived from the live tree**, not from the plan: 14 `skills/*/SKILL.md` +
  13 `copilot/.github/skills/*/SKILL.md` + 12 `codex/skills/*/SKILL.md` = 39.
  `copilot/goliath` post-dates the plan and gets its own entry below.
- **Budgets measured on the BODY only** (frontmatter stripped), since D1's "~900 words of
  markdown body" is a body budget. Every entry's word count below is that measurement.
  Bodies over ~900 that are not one of the three orchestration ceilings: `claude/context-weight`
  (2349), `claude/journal` (1079), `claude/graphify` (902, effectively at budget).
  The three ceiling-bound orchestration skills measure 6567 (`claude/repo-bench`),
  5998 (`claude/execute`), 2767 (`claude/architect`); `copilot/architect` (899) is the
  Copilot-side orchestration skill and sits at its own ceiling.
- **Sentinels were derived by grep, then inspected.** `grep -rlF "<name>" tests/` alone is
  noisy across harnesses (three skills are called `route`), so each candidate was confirmed by
  reading the asserting test. A crucial distinction runs through the results and every
  `relocate` below depends on it:
  - **Direct pins** — a test opens the SKILL.md and asserts a substring. These exist almost
    exclusively on the **Copilot and Codex** bundles (`tests/test_copilot_bundle.py`,
    `tests/test_codex_bundle.py`, `tests/test_codex_core_skills.py`,
    `tests/test_codex_analysis_skills.py`, `tests/test_codex_memory_skill.py`,
    `tests/test_codex_surfaces.py`). **Not one test reads a `skills/*/SKILL.md` body.**
  - **Quotation coupling** — the skill quotes a string that a test pins as *engine output*
    (e.g. `checkpoint decisions to disk, then compact` is pinned in
    `tests/test_context_weight.py` against `bin/context_weight.py`, not against the skill).
    Moving such a line between files breaks nothing, but **rewording it desyncs the skill from
    the engine it is quoting** — so a moved quotation must land byte-identical.
  - **Path references** — a test names the skill's PATH without reading its body
    (`tests/test_lessons_promote.py`, `tests/test_privacy_layout.py`,
    `tests/test_guardrails_layout.py`).
- **The generator strips a leading h1 from 30 of the 39 bodies** (all 14 Claude, all 12 Codex,
  and 4 of 13 Copilot — `bench-routing`, `context-weight`, `goliath`, `lessons-loop`). Each
  stripped h1 is the skill's own one-line self-description; where it says something the
  frontmatter `description` does not, the fragment's `### What it does` is the place to
  reconcile them. The 9 Copilot skills with no h1 lead straight into a second-person mission
  sentence, which is already the reconciled form.
- **Off-limits throughout, named descriptively so nothing here reads as a proposal to touch
  them:** the two `sync_pricing_refs`-generated pricing mirrors shipped beside `claude/route`
  and `claude/fable-check`, and the seven role templates shipped beside `claude/architect`.
  No entry proposes editing any of them.

## Disposition summary

33 `keep`, 3 `enrich`, 3 `relocate` — the expected shape. The robustness the user asked for
lands in fragments and reference files, not in fatter skill cards.

- `enrich` (a missing ACTING fact, nothing else): `claude/cost-report`, `copilot/journal`,
  `codex/bench-routing`.
- `relocate` (content that fails the D1 litmus, moved with a pointer):
  `claude/context-weight`, `claude/journal`, `claude/setup`.

Each entry's fields are, in order: the verdict; the specific SKILL.md additions or moves;
the reference files to create with their one-line charters; what the site fragment must cover;
and the sentinel exposure.

## claude

### claude/architect
- verdict: keep
- skill-md: unchanged (2767-word body; orchestration ceiling — may only shrink). Every long
  block is emitted-artifact grammar the architect must reproduce exactly: the PLAN.md
  `autonomy:` / `budget:` / `roles:` line families, the `id`/`title`/`status`/`model`/brief/
  acceptance/verify task-field contract, the read-only `tools:` pin paired with the
  damage-restore practice, and the aesop-managed branch. Without them the architect writes
  kits that the execute loop and `bin/routing_scorecard.py` cannot parse — the litmus fails in
  the direction that keeps the text. Considered and declined: relocating the `roles:`
  evidence-ladder bullet (R3/R5/R7/R10) — it is the only statement of the roster grammar
  together with its measurement discipline, and CLAUDE.md's architect↔execute contract
  invariant makes splitting it across files a sync hazard.
- references: none new. The seven role templates already shipped beside this skill are its
  instantiation source and are off-limits to this kit; the fragment links them on GitHub
  rather than copying or editing them.
- fragment-notes:
  - The human story the card cannot afford: Fable runs once at the start, its judgment
    persists as scaffolding. Show kit anatomy — PLAN.md / TASKS.md / GUARDRAILS.md are
    architect-owned, NOTES.md is execute-owned — as a diagram or table.
  - Walk the two entry modes (dispatch a `model: fable` subagent from a daily-driver session
    vs. native `/model fable`) and say why dispatch mode is the normal one.
  - Explain the three optional PLAN.md dials in plain language and point at
    `python3 bin/routing_scorecard.py --roles` and `--history` as the evidence to consult
    before declaring a roster or a budget. Ground the flags in `bin/routing_scorecard.py`'s
    argparse, not in prose.
  - Gotcha worth its own callout: `autonomy:` / `budget:` / `roles:` are PLAN.md lines, never
    task fields. A reader who writes them onto a task breaks nothing and measures nothing.
  - Related: `execute` (the other half of one contract), `repo-bench`, `graphify`.
- sentinels: none found on the body — no test reads it. `tests/test_lessons_promote.py` names
  the path `skills/architect/SKILL.md` as an authored display constant and asserts it appears
  only there; `tests/test_guardrails_layout.py` pins a per-task-dollars kit fence that names
  the same path (kit-scoped, not binding here). CLAUDE.md's architect↔execute sync invariant
  binds any edit to either skill.

### claude/bench-routing
- verdict: keep
- skill-md: unchanged (679). The four subcommands, the lead-with-`compare` rule, the
  `no_role_evidence` rule, and the never-borrow-implementer's-rate rule are all acting facts —
  each one names a specific way the answer goes wrong without it.
- references: none
- fragment-notes:
  - Frame the three legs of routing evidence — published prior (this skill), observed ledger
    (`routing_scorecard`), measured-on-this-repo (`repo-bench`) — and state that they are read
    side by side, never averaged.
  - Worked example: `compare` returning `not_supported` on a nominally-positive gain, and why
    "measured outcomes win" over a benchmark delta of a few points.
  - Ground every command in `bin/bench_routing.py`'s argparse (`rank` / `roles` / `compare` /
    `demo`; `compare` takes `--benchmarks`, `--pricing-dir`, `--kits-dir`, `--floor`, `--json`
    and has **no** `--harness` flag) and in `data/benchmarks.aa.json`'s own provenance fields.
    Show no index number and no `usd_per_task` figure on the page.
  - Gotcha: the Intelligence Index is a general-capability composite. Coding and Agentic
    boards are separate and are not in this data — say so before any agentic-role advice.
- sentinels: none found on the body. `no_role_evidence` is pinned as engine output in
  `tests/test_bench_routing.py`; the skill quotes it, so keep that token byte-identical.

### claude/context-weight
- verdict: relocate
- skill-md: 2349-word body against a ~900 budget — 2.6x over, and this is not one of the three
  orchestration ceilings, so it is the roster's clearest D1 failure. Apply the rule three ways
  rather than just shortening:
  (1) **MOVE to `references/columns.md`** the "What the columns mean" glossary (weight / est. /
  measured / inferred / session-average, ~400 words). It is a schema read on demand, not on a
  typical run. The `est.`-is-never-priced and Copilot-has-no-curve semantics survive in the
  skill because the closing "Honesty rules this tool holds" section already restates them —
  verify that before cutting, and if any honesty claim exists ONLY in the glossary, keep that
  sentence in the skill.
  (2) **MOVE to `references/practices.md`** the "Five practices, each tied to a metric this
  tool reports" section (~500 words). The three levers above it already carry the priority
  order; the five practices are the on-demand expansion.
  (3) **MOVE to the site fragment** (not to references — it is human-only rationale per D1.3):
  the cache-read reframe paragraph, the measured `watch` anecdote (`peak 99% of window …
  avoidable (tool-ingested) mass`), and the graphify compression measurement (8.4MB → ~450
  tokens). Leave a one-line pointer in the skill: for a wide read whose question is repo
  structure, reach for `/polytropos:graphify` first.
  (4) **ADD one missing acting fact while it is open:** the engine ships **six** subcommands —
  `session`, `overview`, `audit`, `watch`, `constraints`, `demo` (confirmed against
  `python3 bin/context_weight.py --help`) — and the skill documents five, omitting
  `constraints` entirely. `constraints --kit KIT [--harness …] [--session …] [--json]` answers
  "is this kit's GUARDRAILS.md still resident in the reconstructed window", which is exactly
  the question `claude/execute`'s phase-start fence re-read exists to force. Add the command
  and fix the now-wrong "All five take `--json`" line to name six.
  MUST NOT move: "What this skill cannot do" (the single most likely misreading of the whole
  kit), the three levers with their priority order, "Checkpoint before compacting" with its
  safe/dangerous split, the `watch`-is-Claude-only refusal, and the closing honesty rules.
- references:
  - `references/columns.md` — read when you must explain or defend a number in a `session` /
    `overview` card: the weight / est. / measured / inferred / session-average glossary.
  - `references/practices.md` — read when the user asks "so what do I actually change": the
    five habits, each tied to the metric and the command that measures it.
- fragment-notes:
  - Lead with the correction the skill leads with: this cannot shrink your window; only the
    harness can. Then the reframe — a high cache-read line is the cheap path working, and the
    real driver is resident context x number of calls.
  - Carry the relocated narrative: the measured `watch` session (7% avoidable mass of a
    993,900-token peak) and the graphify compression figure, both as illustrations of PREVENT.
    Quote them exactly as the skill states them; do not round or re-derive.
  - Show the six subcommands with one honest sentence each, and state per-harness fidelity
    plainly: Copilot gets a session-average and never a growth curve; Codex gets a byte-share
    by record type and never content attribution; `watch` and `constraints` are Claude-only.
    Ground in `bin/context_weight.py --help` and each subparser's `--help`.
  - Gotcha for the page: every dollar figure this tool prints is an API-equivalent estimate
    inside one harness's own section — there is no cross-harness dollar total anywhere in it.
- sentinels: **none found** — no test reads this SKILL.md. Every distinctive phrase probed
  (`session-average`, `avoidable (tool-ingested) mass`, `assistant output (measured)`,
  `inferred compaction`, `resident surfaces`, `checkpoint decisions to disk, then compact`)
  is pinned in `tests/test_context_weight.py` as **engine output** from `bin/context_weight.py`,
  never as skill text. The moves are therefore sentinel-safe, but the quotation coupling is
  real: every moved string must land **byte-identical** in its new file, and the honesty block
  and the `watch` refusal must not move at all. Run the full suite after the split anyway —
  quotation coupling is exactly the class of breakage a grep does not catch.

### claude/cost-report
- verdict: enrich
- skill-md: 240-word body — the thinnest Claude skill, and **thin here is genuinely
  incomplete**, not deliberate density. Two acting facts are missing, both confirmed against
  `bin/cost_report.py`'s own argparse and `main()`:
  (1) **Two real flags are undocumented:** `--json` (prints the report payload instead of
  markdown) and `--projects-dir DIR` (point the walk at a non-default transcript directory —
  the only way to run this against anything but the live home).
  (2) **The no-data branch is unstated, and it is the most likely first-run outcome.** The
  engine distinguishes two cases the skill never mentions: a **missing** directory exits with
  `No transcript directory at <path>` and renders nothing; a **present-but-empty** directory
  still renders the full report with a `no transcripts in window: <dir>` label — a zero-row
  report is honest output, not a failure. Without this, a model meets an empty window and
  either reports the tool broken or presents zeros as measured spend. Add one short branch
  beside the existing "if the script errors, show the error and the file it choked on" line —
  which is a safety/honesty line and stays verbatim.
  Net addition ~60 words; the body stays far inside budget. No other change: the
  `${CLAUDE_PLUGIN_ROOT}` resolution proof, the api-vs-subscription framing split, and the
  downgrade-candidate presentation rules are all correct and complete.
- references: none — even enriched this is a ~300-word card.
- fragment-notes:
  - `### Worked example` should show the real shape: run over 30 days, read the by-model
    table, then read the downgrade-candidate rows, and end on the one recommendation the skill
    demands. Use a sanitized example — never a real transcript path or a real dollar figure.
  - Make the two framings the centerpiece: in `api` mode the delta is savings; in
    `subscription` mode the same number is rate-limit burn share and is **not** money spent.
    That distinction is the whole point of the skill and the most common misreading.
  - Cover the enriched branch for humans too: an empty report on a fresh machine means no
    transcripts in the window, not a broken tool.
  - Ground every flag in `bin/cost_report.py` (`--days`, `--mode`, `--top`, `--json`,
    `--projects-dir`). Print no price and no `cached_date` on the page — point at
    `data/pricing.json` on GitHub instead.
- sentinels: none found — no test reads this SKILL.md, and no test pins its engine's
  output strings. The additions are purely additive regardless.

### claude/escalate
- verdict: keep
- skill-md: unchanged (837). The five steps, the "nothing can switch the main session's model"
  constraint that shapes the whole design, the scope-before-effort lever ordering with its
  honest note that the Agent tool takes no effort parameter, and the `stop_reason: "refusal"`
  fallback are all acting facts. The refusal fallback is a safety line and is untouchable.
- references: none
- fragment-notes:
  - The mechanism a human needs first: the orchestrator never changes its own model; it
    dispatches subagents and grades them. Draw the ladder.
  - `### Worked example`: pin a verify command, attempt on Sonnet, fail, retry with the
    failure output, fail, escalate to Fable carrying both failures as evidence — and stress
    that the orchestrator reruns the check itself at every step.
  - `### Failure modes & fallbacks`: no machine-checkable outcome (say so, don't fake a
    verify); a Fable refusal on cyber/bio-adjacent work (fall back to Opus at high effort);
    even-Fable-fails (stop and report, never climb past `xhigh`).
  - Relationship to name explicitly: this is the per-task sibling of `execute`'s blocked-task
    valve — for multi-task work, a kit beats calling this in a loop.
- sentinels: none found.

### claude/execute
- verdict: keep
- skill-md: unchanged (5998-word body; orchestration ceiling — may only shrink). This is the
  most contract-dense file in the repo and almost none of it is narrative: the six machine-read
  NOTES.md line families and their exact grammar, the backtick rule that stops prose from
  parsing as evidence, the `budget-stop`-is-not-a-verdict rule, the `parent=`-only-on-
  `escalated-pass` rule, the three-value `failure=` vocabulary, the marginal-adjudication
  pipeline order, and the `session:` id lookup with its explicit "do NOT derive from `pwd`"
  warning. Each is a line a model acting without it gets wrong in a way that corrupts the
  ledger. Considered and declined: relocating the roster hook-points and consequence rules —
  they are the dispatch procedure itself, not reference material.
- references: none
- fragment-notes:
  - Give humans the loop as a picture: mark → dispatch → verify independently → pass/fail →
    phase review, with the fence re-read shown as a guaranteed phase-start step and a
    best-effort post-compaction step.
  - Explain the ledger for a reader, not a parser: what `outcome:` / `agent:` / `reviewer:` /
    `defect:` / `reroute:` / `session:` are FOR, and which report each one feeds
    (`routing_scorecard` with `--history`, `--by-task`, `--roles`).
  - Cover the three dials from the operator's side — advisory vs auto, a budget cap that stops
    cleanly mid-run, a declared roster — and state the counterintuitive fact plainly: a
    declared roster structurally raises `attempts=`, and that dip in first-try rate is the
    roster working, not the implementer regressing.
  - Gotchas to call out: warm clusters cap at ~4 tasks and always end on a model-pin change;
    verification is never warmed; re-routing is upgrade-only, one rung, never to frontier.
  - Ground every command in `bin/routing_scorecard.py`'s argparse; never invent a NOTES.md
    field.
- sentinels: none found on the body, but the **quotation coupling here is the heaviest in the
  repo**: the ledger grammar this skill defines is parsed by `bin/routing_scorecard.py` and
  pinned in `tests/test_routing_scorecard.py`, `tests/test_role_ledger.py`,
  `tests/test_routing_history.py`, `tests/test_per_task_dollars.py`,
  `tests/test_claude_execute.py`, and the two headless-driver suites (`budget-stop` and
  `marginal=` both hit). Treat every token in it as frozen. CLAUDE.md's architect↔execute sync
  invariant binds any edit here.

### claude/fable-check
- verdict: keep
- skill-md: unchanged (594). Compact and complete: the derive-ratios-never-recall rule, the
  worth-it / not-worth-it split with the security-analysis carve-out, four caveats that are
  each a real failure mode (`stop_reason: "refusal"`, long turns, the 30-day retention 400,
  the always-on thinking 400), and the standing architect-first posture.
- references: none new. The one reference this skill already ships is the
  `sync_pricing_refs`-generated pricing mirror — regenerated by its own script, never
  hand-edited, and out of scope here. The fragment may say the vendored snapshot exists and
  that its `cached_date` gates a staleness warning; it must not reproduce any number from it.
- fragment-notes:
  - The decision the page must make easy: Fable's gains are on work above what prior models
    can do — long-horizon autonomous runs, problems Opus already failed on, deepest reasoning,
    heavy sub-agent orchestration.
  - Give the counter-list equal weight, including the non-obvious one: security-analysis-heavy
    work goes to Opus, because Fable's classifiers refuse much of it.
  - `### Cost & safety`: the three-tier resolution order for pricing and the 60-day staleness
    rule on the vendored snapshot; no prices, no ratios, no dates on the page — link
    `data/pricing.json` on GitHub and show the engine command instead.
  - `### Related`: `route` (which model), `escalate` (verify-gated ladder), `architect` (the
    default escalation path for anything with an execution phase).
- sentinels: none found on the body. `tests/test_pricing_refs.py` and
  `tests/test_harness_update.py` guard the generated mirror beside it, not the card.

### claude/graphify
- verdict: keep
- skill-md: unchanged (902 — effectively at budget, so any future addition must displace
  something). The availability gate, the binding allowlist of offline subcommands with the
  explicit never-run list, the extraction recipe, the reading order, and the three measured
  limits are all acting facts; the measured-limits section in particular is what stops the
  model from treating a missing edge as proof of no dependency. Considered and declined:
  relocating section 5 (measured limits) — it is honesty content about what the tool cannot
  see, and CLAUDE.md pins the external/never-invoked posture.
- references: none
- fragment-notes:
  - State the posture up front: graphify is an external, user-installed CLI (`uv tool install
    graphifyy`), never vendored, never auto-installed, never invoked by tests or kit
    execution. Absence of the binary is not a failure.
  - Show the offline-only allowlist as a table with the reason each excluded surface is
    excluded (network, spend, daemon, or config-writing) — this is the fence readers most need
    to understand rather than obey blindly.
  - `### Worked example`: the `git archive` clean-tree recipe, then brief → explain →
    god-nodes → affected → path → query, in that order, with `query` labelled honestly as
    adjacency rather than answers.
  - `### Failure modes`: dynamic loaders are invisible to AST extraction (this repo's own
    `importlib` spine is missing from its own graph); the "excluding tests/" hub list is a
    top-level-prefix match only and silently filters nothing in a `test/` or `src/tests/`
    layout.
  - Ground commands in `skills/graphify/SKILL.md` and `bin/graph_brief.py`; never show a
    graphify subcommand outside the skill's allowlist.
- sentinels: none found. `tests/test_graph_brief.py` covers the engine, not the card.

### claude/journal
- verdict: relocate
- skill-md: 1079-word body against ~900 — over budget, and the overflow is two clearly
  separable sub-capabilities that a typical invocation ("write my journal") never reaches.
  (1) **MOVE to `references/scheduling.md`** the "Inbox & schedule" launchd block —
  `journal_schedule.py install|uninstall|status|run` plus the note that the installer never
  runs `launchctl` itself. Leave in the skill a one-line pointer plus the inbox sentence
  (dropping plain lines into `journal/inbox.md` IS part of a normal run; installing a nightly
  schedule is not).
  (2) **MOVE to `references/ask-the-tools.md`** the External tools (Teams / Outlook / Copilot
  Studio) block — `journal_askpack.py --date <date> --print`, the two-pass paste-back loop,
  and the 15-bullets-per-tool cap. Leave a pointer: read it when the user wants meeting or
  mail context folded in.
  These two moves land the body at roughly 880. **Honesty lines that must NOT move with them:**
  the privacy paragraph stays whole in the skill, including the sentence that pasted
  ask-the-tools bullets become inbox text and therefore travel to the model; and the
  no-network / no-OAuth / no-Graph / no-MCP declaration stays in the skill even though the
  command it describes moves. Everything else — collect, the telemetry snapshot, the two
  summary modes, the next-day runbook — stays: each is reachable on a normal invocation.
- references:
  - `references/scheduling.md` — read when the user wants the journal to run unattended: the
    launchd install/uninstall/status/run surface and the manual `launchctl` step it never
    performs for them.
  - `references/ask-the-tools.md` — read when the user wants Teams / Outlook / Copilot Studio
    context in the journal: the offline prompt pack and the manual paste-back loop.
- fragment-notes:
  - Show the whole pipeline once as a flow: collect → snapshot → summarize (in-session by
    default) → runbook, and say which step writes where under gitignored `journal/`.
  - `### Cost & safety` is the load-bearing section here: the collector is model-free and
    read-only over three homes; the digest is metadata-only (counts, ids, titles — never
    transcript text); writing the summaries is what sends the digest to a model.
  - State the Codex burn-proxy rule verbatim in substance: Codex figures are labeled
    API-equivalent relative-burn proxies, `billed_usd` stays null, and they never enter priced
    totals. This is a CLAUDE.md invariant and the fragment must not soften it.
  - Cover the two relocated capabilities for humans in full — the nightly schedule and the
    ask-the-tools pack are exactly the kind of "worth knowing, rarely needed" material the
    site is for. Ground the flags in `bin/journal_schedule.py`, `bin/journal_askpack.py`
    (`--date`, `--utc`, `--journal-dir`, `--digest`, `--print`), and `bin/journal_plan.py`
    (`build` / `check` / `done` / `defer` / `prompt`).
  - Gotcha: the runbook is advisory — it prepares and tracks, and there is no scheduler in it
    by design.
- sentinels: none found on the body. `tests/test_privacy_layout.py` asserts that
  `skills/journal` stays git-TRACKED under the root-anchored ignore rules — a path check, not
  a text pin, and unaffected by adding files under `skills/journal/references/`. No test reads
  this SKILL.md, and none of its phrases (`journal_askpack.py`, `launchctl bootstrap`,
  `ask-the-tools`, `journal/plan/seed.md`) appear in tests as skill text — the hits for the
  first three are engine tests. Full suite after the move regardless.

### claude/memory
- verdict: keep
- skill-md: unchanged (574). Dense and complete: the keyword-derivation rule, the
  empty-recall-is-success rule with its explicit "do not loosen the query" instruction, the
  effectiveness contract (never bulk-inject), the exit-2 duplicate branch with the
  update-over-duplicate rule, and the privacy statement. The effectiveness contract and the
  privacy paragraph are safety lines.
- references: none
- fragment-notes:
  - Lead with the design claim and defend it: recall is pull-only, relevance-gated, and
    budget-capped (at most 5 facts / 4000 chars by default) — memory that could degrade an
    answer is the failure this design exists to prevent.
  - Make the counterintuitive rule vivid: `no memory above the relevance gate for this query`
    is a SUCCESS. Broadening the query to force a hit is the anti-pattern.
  - `### Worked example`: save a decision with meaningful `--tags`, hit the duplicate exit,
    update instead of forcing, then recall it later from a different phrasing — which is
    exactly what the tags are for.
  - `### Cost & safety`: the store is gitignored user data at the repo root, never committed;
    runtime code reaches it only through the explicit `--memory-dir` seam; tests use temp
    fixtures with an explicit `--now`.
  - Ground flags in `bin/memory_recall.py` and `bin/memory_store.py`.
- sentinels: none found on the body. `— STALE, verify before relying` is pinned in
  `tests/test_memory_recall.py` as engine output that this skill quotes — keep it
  byte-identical. `tests/test_privacy_layout.py` guards `skills/memory`'s git-tracking by path.

### claude/repo-bench
- verdict: keep
- skill-md: unchanged (6567-word body — the longest in the repo; orchestration ceiling, may
  only shrink). This is the skill where a wrong reading spends real money or re-routes real
  work, and nearly every long passage is the honesty contract governing how results are
  RELAYED, which is this skill's actual output: plan-first law, the `solved`-means-tests-only
  rule, the four-oracle separation, the constructed-substrate guarantee with its deliberately
  visible false negatives, the diagnostic-is-forgeable-and-feeds-nothing rule, the evidence
  floor, the three legs, and apply-is-a-separate-action.
  Two sections were examined honestly as relocation candidates and both were declined:
  - The `--with-gh` section (~700 words on one opt-in flag) reads like D1's "rare-flag
    catalog", but its core is a safety finding — GitHub shares one number namespace between
    issues and PRs, so a PR body would be a worse leak than the commit message — and the
    `--gh-repo` refusal exists precisely because the degraded path is indistinguishable from a
    correct result. Splitting the flag from the reason it refuses is how a future reader
    "simplifies" the refusal away.
  - The worked cost anecdote (a 10-task matrix planned at $17.22 that would have cost
    $100–200) reads like design history, but it is the only thing that stops a user from
    sizing a ceiling against a number that has measured ~10x low. The rule without its
    evidence is a rule people round off.
  If a future task must shrink this file, the honest first cut is the `--setup-key`
  soundness-verification mechanics — but not in this kit.
- references: none
- fragment-notes:
  - The page must open on plan-first: the default invocation prices a matrix and spends
    nothing; `--live --max-usd` is only ever constructed after the user confirms a ceiling in
    that conversation. Never show a copy-pasteable `--live` command without that framing.
  - Explain the four oracles as four separate columns that are never blended, and give
    `solved` its exact meaning: tests passed, nothing else, ever.
  - The concept most worth a diagram: the constructed grade substrate — base state (+ setup
    artifacts) + the candidate's in-scope patch + the withheld test blobs, and nothing else —
    plus the false negative that construction deliberately buys, and the full-patch diagnostic
    reported as an interval whose upper bound is forgeable.
  - `### Failure modes`: `BELOW EVIDENCE FLOOR` (not "preliminary"), `partial (cost-ceiling)`
    and when `regrade` is the answer, `DISAGREEMENT — signal, not error`, and the naive
    substring test-path match that can misclassify a file like `contest_data.py`.
  - Ground everything in `skills/repo-bench/SKILL.md` and `bin/repo_bench.py`; never show a
    dollar figure, in prose or inside a fence — state the worked cost anecdote's lesson
    (a ceiling sized without it can measure ~10x low) and let the reader find the number on
    the skill card below.
- sentinels: none found on the body. Quotation coupling is partial and worth stating
  precisely: `BELOW EVIDENCE FLOOR`, `statement from commit message`, `gh enrichment`, and
  `false-negative bound` are pinned as engine output in `tests/test_repo_bench.py`; other
  labels this skill quotes (`partial (cost-ceiling)`, `DISAGREEMENT — signal, not error`,
  `n/a (unparseable)`, `STALE VERDICT`) are not pinned anywhere — which makes them easier to
  reword by accident and no less load-bearing.

### claude/route
- verdict: keep
- skill-md: unchanged (859). Four tight steps plus the optional measured-tier-map block. The
  billing-mode split (session routing vs the app being built), the never-use-prices-from-memory
  rule, the three-tier pricing resolution order, the "only the user can switch the main
  session's model" constraint, and the architect-instead-of-plain-Fable-dispatch rule are all
  acting facts. The repo-bench prefs block already carries its own staleness guard.
- references: none new. The `sync_pricing_refs`-generated pricing mirror shipped beside this
  skill is regenerated by its own script and is out of scope here; the fragment may say the
  vendored snapshot is the last-resort fallback and that a `cached_date` older than 60 days
  triggers a staleness flag, without reproducing anything from it.
- fragment-notes:
  - This is one of the three Phase 3 pilot pages — the template proven here is applied 35 more
    times, so it carries extra weight. Make `### Worked example` genuinely worked: a task
    description in, a mode decision with its one-sentence justification, a candidate table,
    and the single action (dispatch vs `/model sonnet` vs paste-into-your-app).
  - The two modes are the whole page: `api` is dollar-optimized (cheapest sufficient wins);
    `subscription` is capability-first and burn-aware, where the dollar figure is
    API-equivalent burn and not money spent.
  - State the hard constraint clearly: nothing can switch the main session's model except the
    user — a dispatched subagent shares none of the conversation, so the brief must be
    self-contained.
  - `### Cost & safety`: no price, ratio, or `cached_date` on the page. Link
    `data/pricing.json` on GitHub and show the resolution order instead.
  - `### Related`: `fable-check`, `escalate`, `architect`, `repo-bench` (the optional measured
    tier map this skill will prefer when `prefs/repo-bench.json` matches the project).
- sentinels: none found on the body. `prefs/repo-bench.json`, `daily_driver` and the `tiers`
  schema are pinned in `tests/test_repo_bench.py` against the engine that writes the file —
  the skill's description of that schema must stay consistent with it.
  `tests/test_harness_update.py` and `tests/test_pricing_refs.py` guard the generated mirror
  beside the skill, not the card. `tests/test_docs_build*.py` use `skills/route/SKILL.md` as a
  link-rewriting fixture path.

### claude/setup
- verdict: relocate
- skill-md: 898-word body — at budget, with a clear split between its primary job (install the
  statusline: ~5 steps) and an explicitly separate opt-in (the kit verify-pass hook: roughly
  half the file). **MOVE to `references/kit-verify-hook.md`** the second half's deep semantics —
  specifically the closing paragraph on what the marker DOES and DOES NOT prove
  (`precheck` deleting a stale marker, the stored verify-command text compared at flip time,
  the two kit dialects it parses, and the three residual limits). ~350 words.
  Leave in the skill: the whole numbered install procedure for the hook (steps 1–4 with the
  exact JSON block and the merge-don't-replace instruction), plus a compacted step 5 that
  keeps the two facts a model must state at install time — it fires only on the `Edit` tool,
  and a `done` flip performed via `Write` is a silent no-op, not a block, because the
  PostToolUse payload for `Write` carries no old content — followed by the pointer: read
  `references/kit-verify-hook.md` before telling the user what the marker proves.
  MUST NOT move or change: the literal-absolute-path rule (the command written into
  `~/.claude/settings.json` must never be `${CLAUDE_PLUGIN_ROOT}`, because that variable does
  not exist outside plugin context — this is a CLAUDE.md invariant), the
  get-explicit-confirmation-before-writing rule, the never-bundled-with-the-statusline-step
  separation, and **the sample JSON payload in step 1** (see sentinels).
- references:
  - `references/kit-verify-hook.md` — read before explaining the verify-pass hook's
    guarantees: what a marker proves, what `precheck` freshness and the verify-command match
    add, and the three things it still cannot prove.
- fragment-notes:
  - Keep the two capabilities visibly separate on the page, the way the skill keeps them: the
    statusline is the headline; the hook is a distinct opt-in that most readers will skip.
  - `### What it does` for the statusline: model (color-coded), estimated session cost,
    context %, and 5h/7d rate-limit burn — with the honest caveat that the cost figure is a
    client-side estimate, not a bill, and rate-limit fields appear on subscription sessions
    only.
  - `### Failure modes`: the change needs a restart or a new session; an existing `statusLine`
    key is replaced (the skill warns first); hook configuration loads at session start, so
    `claude --debug` is how registration is confirmed.
  - Explain the hook's real coverage boundary for humans, since it is the thing people
    misunderstand: it enforces on `Edit`, and a `Write` rewrite of TASKS.md is a silent no-op.
    Ground in `bin/kit_verify_hook.py` and the skill's own cited harness-docs URL.
  - `### Cost & safety`: this writes user-level settings — the only skill in the roster that
    does — so confirmation-before-write is the design, not politeness.
- sentinels: **one partial coupling, and it constrains the split — but less than it first
  appears.** `tests/test_statusline.py`'s `test_setup_skill_sample_payload_exact_output` never
  opens the SKILL.md; its own comment says it matches "the sample JSON in
  `skills/setup/SKILL.md`'s smoke test", and it asserts
  `self.assertEqual(out, "⬢ Fable 5 | $1.23 | ctx 42%")`. **Its payload carries only
  `model`, `cost`, and `context_window` — it omits `rate_limits` entirely.** So what is
  actually coupled is the three field VALUES the two share (`claude-fable-5` / `Fable 5`,
  `1.23`, `42`) and the pipe rendering of exactly those three segments: change any of them in
  the skill's sample and the sample stops demonstrating what the test asserts. The rate-limit
  half of the step-1 payload and the documented `5h 12% · 7d 34%` output shape are **not
  pinned by any test** — `grep -cE '12%|34%|5h 12|7d 34' tests/test_statusline.py` returns 0.
  (A different test in the same file asserts `7d 22%`, on its own unrelated payload.) Practical
  rule for T9–T14: leave step 1 alone, but for the right reason — the three shared values
  because the test's expected string depends on them, and the rate-limit half because it is what
  this skill's own `description` promises the statusline renders, not because a test guards it.
  The hook prose is unpinned: neither `kit_verify_hook.py hook` nor the cited
  `code.claude.com/docs/en/hooks` URL appears anywhere in `tests/`, and
  `tests/test_kit_verify_hook.py` covers the engine only.

### claude/update
- verdict: keep
- skill-md: unchanged (771). Every section is an acting fact and several are safety lines: the
  check-first law, the per-channel apply contract (Copilot overwritten in place; Codex split
  into unconditionally-overwritten prompt mirrors vs no-clobber `AGENTS.md` and skill dirs;
  project-scope TOMLs outside apply's reach), the `~/.claude`-is-never-written rule with its
  framing-line-plus-remedy requirement, the card-reading gloss, and the two
  scrub-before-pasting warnings. The Codex two-channel wording is explicitly marked as
  P2-review-corrected load-bearing text.
- references: none
- fragment-notes:
  - The mental model to give a human: four sections (claude / copilot / codex / data), exit 3
    means drift somewhere, and the verdict line names which section drifted.
  - Be explicit about what apply will and will not do to each home — a table is the right
    shape — and state the `~/.claude` rule as an absolute: the remedy is printed, never
    executed.
  - `### Failure modes`: "not installed" is an absence, not a failure; `unmanaged` on codex is
    a warning; a codex `conflict` is real drift; `status: error` / exit 1 means a writer
    raised — report and stop, never retry blind.
  - `### Cost & safety`: both JSON envelopes and the human apply card embed absolute home
    paths — scrub before pasting anywhere outward. Pricing numbers and docs snapshot tables
    are never auto-edited; that refresh is a human edit tied to a `cached_date`.
  - Ground in `bin/harness_update.py`; show no `cached_date` value on the page.
- sentinels: none found on the body. `skip-differs`, `managed-update` and
  `prompts differing before this run` are pinned as engine output in
  `tests/test_harness_update.py` (and the codex suites) — the skill quotes all three, so keep
  them byte-identical.

## copilot

### copilot/architect
- verdict: keep
- skill-md: unchanged (899-word body — the Copilot-side orchestration ceiling). The
  machine-parsed TASKS.md skeleton is the single most load-bearing block in the Copilot bundle:
  `bin/copilot_execute.py` parses it, and the skill spells out the punctuation as load-bearing
  (`### <id> — <title>` with a spaced em dash, bare field values, `**Brief.**` /
  `**Acceptance.**` / `**Verify.**` markers, the first ```bash fence after Verify). The
  self-check command, the never-invoke-the-real-`copilot`-CLI rule for verify commands, the
  model-honesty section, and the prefs block are all acting facts.
- references: none
- fragment-notes:
  - The parity story: this is the Copilot sibling of `claude/architect`, but kits live under
    `tasks/kits/<slug>/` and the grammar is strictly machine-parsed — a drifting task block
    makes the kit undispatchable rather than merely untidy.
  - Reproduce the task skeleton on the page as the canonical reference, and say plainly that
    `python3 bin/copilot_execute.py status --kit <dir>` is the self-check before hand-off.
  - `### Cost & safety`: verify commands must never invoke the real `copilot` CLI — a live
    dispatch spends real AI Credits. This is a CLAUDE.md invariant, not a style preference.
  - Tier words only, never model ids, on the page; point at
    `python3 bin/copilot_pricing.py models` / `prefs` for anything concrete.
  - Note the `{{POLYTROPOS_ROOT}}` placeholder convention and what an unresolved literal means
    (bundle not installed) — it recurs on 12 of the 13 Copilot pages, so decide the wording
    once here.
- sentinels: **direct pins** in `tests/test_copilot_bundle.py` — `pending | in-progress | done
  | blocked`, `tasks/kits/`, `{{POLYTROPOS_ROOT}}`, plus the roster-wide frontmatter
  discipline, no-unquoted-colon, and no-pricing-model-id checks over every skill file.
  `tests/test_copilot_docs_content.py` requires the discovered skill set to match
  `copilot-docs/SKILLS.md` headings exactly and each section to carry when/how/safety content —
  so a frontmatter `name`/`description` change here means regenerating `copilot-docs/`, which
  this kit does not touch.

### copilot/bench-routing
- verdict: keep
- skill-md: unchanged (538). The three real subcommands, the confirm-against-`--help` rule,
  the `unavailable`-is-listed-never-dropped detail, and the whole `compare` honesty section
  (the ledger is Claude-harness implementer evidence; `compare` has no `--harness` flag; never
  imply one exists) are acting facts. The tier-words-only rule is a bundle-wide invariant.
- references: none
- fragment-notes:
  - The honest headline for this page: on Copilot the benchmark prior stands unchallenged,
    because this repo's measured ledger is Claude-side. Point readers at the Claude harness for
    the measured check rather than implying parity.
  - Explain `roles --harness copilot` precisely: availability derived at run time from the
    Copilot pricing data; the text card shows an aggregate `N/M benchmark entries
    dispatchable`, and `--json` lists unavailable entries by display name.
  - `usd_per_task` is a ranking ratio from the benchmark workload — never a bill, never added
    to the `usage` skill's real spend figures.
  - Ground in `bin/bench_routing.py --help` and its subparsers; use tier words only, no model
    ids, no index numbers.
- sentinels: **direct pins** in `tests/test_copilot_bundle.py` (roster-wide frontmatter, no
  unquoted colon, no pricing model id) and `tests/test_copilot_docs_content.py` (name and
  description feed the generated `copilot-docs/SKILLS.md` heading set).

### copilot/budget
- verdict: keep
- skill-md: unchanged (603). Copilot-only by design. The ladder table with its
  taught-vs-enforced column, the exactly-one-tier / floor-cheapest / never-fabricate-a-rung
  rule, the don't-combine-with-`--max-escalations 0` warning, the `BACKFIRED` reading, and the
  reviews-stay-at-full-strength rationale are all acting facts.
- references: none
- fragment-notes:
  - This is one of the three Phase 3 pilots and the designated harness-only page — the parity
    matrix's dash for Claude and Codex must read as a design decision, and this page is where
    that decision is explained.
  - Make the ladder table the centerpiece and be explicit about the asymmetry: the implementer
    drop is enforced by `run --budget`; the planner drop is taught, because the driver never
    dispatches the architect.
  - `### Failure modes`: `BACKFIRED` means the escalations cost more than the demotion saved.
    With only two roles downgraded, a single escalation can erase a run's saving — believe the
    ledger, not the theory.
  - `### Cost & safety`: preview with `--dry-run` first; a real run spends real AI Credits.
    The headline net covers completed runs only — blocked and no-demotion runs are reported on
    their own lines and never folded in.
  - Ground in `bin/copilot_execute.py` (`run --budget --budget-profile`, `budget --kit`,
    `review`) — and note that `review` deliberately takes no budget flag.
- sentinels: **direct pins** roster-wide in `tests/test_copilot_bundle.py`;
  `tests/test_copilot_docs_content.py` pins the generated docs heading set.
  `tests/test_copilot_budget.py` is an extensive engine suite (demotion arithmetic, the
  `BACKFIRED` / break-even / losing verdict strings, the not-counted lines) — the skill quotes
  that vocabulary, so keep every quoted verdict word byte-identical to the engine's.

### copilot/context-weight
- verdict: keep
- skill-md: unchanged (581). Notably tighter than its 2349-word Claude sibling and better for
  it — the cannot-do statement, the four real subcommands with the confirm-against-`--help`
  rule, the Copilot-fidelity section (no growth curve; session-average is the honest
  substitute; `watch` is Claude-only and prints an honest refusal), the three levers, and the
  mandatory `API-equivalent dollars — an estimate, not a bill.` label are complete.
  Considered and declined: adding `constraints` (the sixth engine subcommand) — on Copilot it
  can only return the fidelity-limit line, so documenting it would add a command with no
  Copilot answer.
- references: none
- fragment-notes:
  - Lead with the honest fidelity difference rather than hiding it: Copilot gets a
    session-average, never a growth curve, because its logs carry no per-turn input/cache
    split. That is the page's most useful fact.
  - There is no live threshold here — apply the three levers on a schedule (once per session,
    or before a long task), not on a threshold crossing.
  - The `context carry cost` line always travels WITH its label
    (`API-equivalent dollars — an estimate, not a bill.`) and is never added to the `usage`
    skill's real spend.
  - Ground in `bin/context_weight.py --help`; cross-link the Claude page for the fuller
    fidelity story rather than duplicating it.
- sentinels: **direct pins** roster-wide in `tests/test_copilot_bundle.py`;
  `tests/test_copilot_docs_content.py` pins the docs heading set. `session-average` is pinned
  as engine output in `tests/test_context_weight.py` and also appears in
  `tests/test_copilot_bundle.py` — keep it byte-identical.

### copilot/effort
- verdict: keep
- skill-md: unchanged (602). This skill's whole value is being honest about a mechanism that
  barely exists: the ladder comes from `copilot_pricing.py knobs` and never from memory, the
  Title-Case display words are explicitly not the lowercase tokens other CLIs use, the
  interactive `/model` picker with left/right arrows is the only confirmed surface, and there
  is NO confirmed headless flag — with the single correctable point named. Every one of those
  is a test-pinned acting fact.
- references: none
- fragment-notes:
  - The page's job is to prevent an invented flag: say plainly that no `copilot -p` flag and
    no settings key is known to control reasoning effort, and that the pricing data's
    `knobs.reasoning_efforts_note` is where a future headless surface would be recorded.
  - Show the interactive mechanism concretely (open `/model`, select the row, arrow keys cycle
    Reasoning) and note that some rows show a dash and have no dial at all.
  - Never enumerate the level names on the page — they are data. Show the `knobs` command
    instead, and warn that Copilot's Title-Case display words must not be mixed with another
    CLI's lowercase vocabulary.
  - `### Cost & safety`: higher effort means more output tokens, and AI Credits are money.
    Show `copilot_pricing.py est <PROFILE> <MODEL_ID>` as the sizing step and say the printed
    number is a floor, not a ceiling, once effort is raised.
- sentinels: **direct pins** in `tests/test_copilot_bundle.py`: `bin/copilot_pricing.py`,
  `knobs`, `/model`, the word `arrow` (lowercased match), `unconfirmed`, plus a check that no
  borrowed or invented effort flag appears. This is among the most tightly pinned skills in
  the roster — treat every sentence in the mechanism section as contract.

### copilot/escalate
- verdict: keep
- skill-md: unchanged (825). Steps 0–4 plus the kit-task pointer and the prefs block. The
  ladder rule is stated as "exactly the rule `bin/copilot_execute.py` implements" (tiers
  strictly above, first model in pricing-file order, empty tiers skipped), which is the kind
  of coupling that must stay verbatim; the excluded-model / emptied-tier / ladder-tops-out-
  lower honesty rules are safety lines.
- references: none
- fragment-notes:
  - Show the ladder as a diagram — `cheap → mid → strong → frontier`, one rung per verified
    failure — and stress that the dispatcher verifies independently at every rung.
  - `### Worked example`: pin the check, dispatch with `copilot -p "<brief>" --model
    <model-id>`, verify yourself, retry once with the failure output, then climb carrying only
    evidence.
  - `### Failure modes`: no machine-checkable outcome (say so, don't fake a verify); a
    frontier refusal (fall back to a strong-tier hop and say why); the top rung still failing
    (stop, report which rungs tried what, never invent a rung above frontier).
  - `### Cost & safety`: AI Credits are money — always report which rung passed, so the
    ladder's savings are visible. Prefs can empty a tier; if the frontier tier empties and no
    pin replaces it, the ladder honestly tops out lower.
  - Ground in `bin/copilot_execute.py` (`run --kit --task --max-escalations`, `--pin`,
    `--exclude`, `--no-prefs`) and `bin/copilot_pricing.py models --json` / `prefs`.
- sentinels: **direct pins** in `tests/test_copilot_bundle.py`: `verify`,
  `bin/copilot_execute.py`, `copilot --agent escalate`, plus the roster-wide checks.

### copilot/execute
- verdict: keep
- skill-md: unchanged (540). Complete against the driver's real surface, and its most valuable
  section is the honest one: "What this harness does NOT have" — no parallel fan-out, no warm
  clusters, `independent:` means safe-in-any-order and not parallel, escalation lives in the
  driver's ladder rather than a session-side valve. That is precisely the kind of line that
  prevents a model from faking an orchestrator it does not have.
- references: none
- fragment-notes:
  - The parity page's most important comparison lives here: put the Claude execute loop and
    this one side by side and state the missing capabilities plainly rather than by omission.
  - Show the three commands (`status`, `run`, `review`) with what each spends: `status` is
    free, `--dry-run` previews without spending, a real `run` spends AI Credits.
  - Cover budget mode's entry point briefly and link the `budget` page rather than repeating
    it; note that `review` takes no budget flag by design.
  - `### Failure modes`: re-run the verify command yourself before trusting a `done` — a
    dispatched run's own claim of success is never evidence.
  - Ground in `bin/copilot_execute.py`'s argparse for every flag shown.
- sentinels: **direct pins** in `tests/test_copilot_bundle.py` (`pending | in-progress | done |
  blocked`, roster-wide checks); `tests/test_copilot_docs_content.py` additionally asserts
  that `execute` is NOT an agent heading in the generated docs — the "no `execute` agent"
  statement in this skill is consistent with that and must stay true.

### copilot/frontier-check
- verdict: keep
- skill-md: unchanged (768). The derive-never-recall block, the worth-it / not-worth-it split,
  the relay-the-`notes`-field rule, the four optimal-run practices, and the prefs block are all
  acting facts. The never-name-a-specific-model constraint is a bundle-wide invariant and is
  test-enforced twice over (no pricing model id in any skill file; the skill must not be named
  after a Claude model).
- references: none
- fragment-notes:
  - The page must hold the same line the skill holds: tier words only. Explain WHY — the
    roster behind a tier changes, the tier does not — so a reader understands the constraint
    instead of finding it evasive.
  - `### Worked example`: run `est` once for frontier and once each for strong and mid to
    build the ratio for THIS task's size, then decide. Show the commands, not the numbers.
  - `### When to reach for it`: long-horizon autonomous work; a concrete strong-tier failure
    on this same task (the strongest signal — if strong hasn't been tried, try it first);
    deepest reasoning; heavy sub-agent orchestration.
  - `### Failure modes`: safety-classifier refusals on cyber/bio-adjacent work — rerun on a
    strong-tier model and explain that the classifier, not capability, blocked it.
  - `### Related`: `route` (which model), `escalate` (single verify-gated task), `architect`
    (multi-task frontier-class work — the frontier spend concentrates in planning).
- sentinels: **direct pins** in `tests/test_copilot_bundle.py`: `bin/copilot_pricing.py`,
  `frontier`, `copilot --agent frontier-check`, and an explicit assertion that this skill is
  not named after Fable — plus the roster-wide no-pricing-model-id check.

### copilot/goliath
- verdict: keep
- skill-md: unchanged (646). Post-dates the plan (commit 85cccaa) and is the reason the roster
  is 39 rather than 38. It is a Copilot-only orchestration POLICY rather than an engine
  wrapper: a five-role pipeline with an architect planner, a per-role fallback table, an
  eight-step execution protocol, and a closing ledger requirement. The role table names models
  by DISPLAY name only, with the explicit instruction that model IDs are resolved from the
  pricing data at run time — which is what keeps it inside the no-hardcoded-model-id invariant
  (`tests/test_copilot_bundle.py`'s no-pricing-model-id check compares against pricing KEYS,
  and the file passes today). Two honest observations that are NOT defects and need no edit:
  it correctly ships no "Same-named agent" section, because there is no `goliath.agent.md`
  (verified against `copilot/.github/agents/`); and its "Installed?" block is worded slightly
  differently from the other twelve ("reload skills in Copilot CLI" rather than naming
  `/skills reload`) — a cosmetic divergence that costs no correct action, so it stays.
- references: none
- fragment-notes:
  - This is the newest skill in the roster and has no sibling on any other harness — the
    parity matrix's two dashes here must be explained on the parity fragment as
    "Copilot-only orchestration policy", alongside `budget` and `lessons-loop`.
  - Present the five roles plus the architect planner as a pipeline diagram, and state the two
    rules that define it: the architect always plans before any execution role, and the
    orchestrator/reviewer never replaces the architect as planner.
  - Reproduce the fallback table as a table but frame it correctly: these are display names to
    resolve, and availability is confirmed against the live `/model` picker plus
    `python3 bin/copilot_pricing.py models --json` before an expensive run. If every candidate
    for a role is unavailable, the run stops and reports the missing role — it never
    substitutes another role's model.
  - `### Cost & safety`: the red-team role is mandatory and must not rewrite tracked files
    while reviewing; work is accepted only when all five execution roles report success; never
    invoke the real Copilot CLI from tests or verify commands (use `--dry-run`, injected
    runners, or synthetic fixtures).
  - Relate it honestly to `claude/architect` + `claude/execute`: same instinct (plan once,
    execute in named roles), different mechanism — a policy the session follows, not a driver
    that dispatches.
- sentinels: **direct pins** are roster-wide rather than goliath-specific:
  `tests/test_copilot_bundle.py` covers it through `test_manifest_skills_set_equals_bundle_
  skill_dirs`, `test_each_bundle_skill_dir_has_a_skill_md`, the frontmatter-discipline and
  no-unquoted-colon checks, and `test_no_pricing_model_id_in_any_skill_file`.
  `tests/test_copilot_docs_content.py` requires it to appear as a heading in the generated
  `copilot-docs/SKILLS.md` with when/how/safety content — and it already does
  (`copilot-docs/SKILLS.md` and `skills.html` both carry it), so no docs regeneration is owed
  by this kit. It is listed in `copilot/aesop.yaml`'s `skills:` block.

### copilot/journal
- verdict: enrich
- skill-md: 426-word body — the shortest Copilot skill after `lessons-loop`, and there is one
  genuine capability gap rather than deliberate density. The Codex sibling documents the
  next-day runbook and this one does not, even though `bin/journal_plan.py` is a
  harness-agnostic engine that writes only under gitignored `journal/plan/` and spawns
  nothing. Add a short **Next-day runbook** section mirroring the Codex journal skill's
  wording: `python3 {{POLYTROPOS_ROOT}}/bin/journal_plan.py build` writes
  `journal/plan/<date>.md`; `prompt` prints the in-session enrichment prompt (rewrite only the
  What/How bodies, keep every other line byte-identical); `check` / `done <id>` /
  `defer <id> --to <date>` track the cards; advisory only — it never schedules or executes
  anything. Subcommands and behavior confirmed against `python3 bin/journal_plan.py --help`
  and its `build` subparser. ~70 words, landing the body near 500 — well inside budget.
  Nothing is removed: the collector block, the `--dry-run`-only rule with its cross-harness
  spend prohibition, the write-the-summaries-yourself instruction, the privacy paragraph, the
  agent block, and the install check all stay verbatim.
- references: none — still a short card after the addition.
- fragment-notes:
  - The most important thing on this page is a prohibition, so state it as such: **never** run
    `journal_summarize.py` without `--dry-run` from this harness, because its headless mode
    dispatches the Claude CLI — a cross-harness spend. The two-pass flow (collect, then
    print-and-write-yourself) is the only sanctioned path here.
  - Explain that the journal engine is harness-agnostic: it already reads all three homes
    read-only, so the journal produced from Copilot is the same cross-harness journal.
  - `### Cost & safety`: the digest is metadata-only (project and repo names, commit subjects,
    kit task titles, inbox text — never transcript or message text); writing the summaries is
    what sends it to a model; everything stays under gitignored `journal/`.
  - Cover the enriched runbook for humans, and repeat the advisory framing: it prepares and
    tracks, it never schedules or executes.
  - Ground flags in `bin/journal_collect.py` (`--date`, `--repo`, `--journal-dir`, `--print`)
    and `bin/journal_plan.py`.
- sentinels: **direct pins** in `tests/test_copilot_bundle.py`: `bin/journal_collect.py`,
  `--dry-run`, `copilot --agent journal`, `{{POLYTROPOS_ROOT}}` — all preserved by an additive
  edit. `tests/test_copilot_docs_content.py` pins the docs heading set (frontmatter unchanged,
  so no regeneration is owed). The addition introduces no model id, price, or invented flag.

### copilot/lessons-loop
- verdict: keep
- skill-md: unchanged (290-word body) — one of the thin seven, and **thin is correct here for
  a structural reason, not a stylistic one**: it is the only skill in the roster with no
  engine behind it. It is a vendored aesop pattern (`registry/skills/lessons-loop` at commit
  5506617) whose entire mechanism is a plain file on disk, `tasks/lessons.md`. That is also
  why it is the one Copilot skill with no `{{POLYTROPOS_ROOT}}` block, no "Same-named agent"
  section, and no "Installed?" check — there is nothing to resolve, no agent, and nothing to
  install. Adding those blocks for uniformity would state things that are not true.
  Its one repo-specific addition, the routing-lessons category, is already complete and
  **verified accurate**: the claim that the execute driver marks `lesson-candidate (routing):`
  lines in the kit's NOTES.md is real — `bin/copilot_execute.py` emits exactly that string
  (line ~1081), as do the Codex and Claude drivers. The tiers-and-ids-from-data rule and the
  project-scoping rule are the safety content and stay verbatim.
- references: none — a 290-word disk-file protocol has nothing to defer.
- fragment-notes:
  - Explain the pattern honestly as prompted Reflexion: the model forgets between runs, so
    lessons live on disk; write the rule after a correction, read them at session start,
    prune the stale ones so bad lessons do not pollute future behavior.
  - Name the aesop provenance (commit 5506617) and say what this repo added on top: the
    Copilot-harness routing category.
  - `### Worked example`: use the skill's own JSON entry shape, and show the two triggers — a
    task that escalated after its pinned model failed verify, and a grossly overprovisioned
    tier. Point at the driver's `lesson-candidate (routing):` NOTES.md line as the machine
    signal that a routing lesson is owed.
  - `### Cost & safety`: never bake a price or a model ranking into a lesson — tiers and ids
    come from the pricing data at run time; keep lessons project-scoped so one project's
    quirks do not leak into another.
  - Parity note for the matrix: Copilot-only, alongside `budget` and `goliath`.
- sentinels: **direct pins** in `tests/test_copilot_bundle.py`: the aesop provenance commit
  `5506617`, `tasks/lessons.md`, and `routing`, plus the roster-wide frontmatter checks.
  `tests/test_harness_select.py` and `tests/test_harness_update.py` use this skill's install
  destination (`<copilot-home>/skills/lessons-loop/SKILL.md`) as their fixture path.

### copilot/route
- verdict: keep
- skill-md: unchanged (780). Complete: the never-from-memory rule with the AIC unit itself
  named as data (`billing_unit.usd_per_credit`), the load-routing-lessons-first step that
  wires `lessons-loop` into routing, the four-tier vocabulary, the estimate procedure with
  `runway`, and the five-row mechanism table drawn from Copilot CLI's real control surfaces.
- references: none
- fragment-notes:
  - The AIC framing is what makes this page different from `claude/route`: AI Credits are
    money, and the page should say so while showing no rate — the unit itself is data
    (`billing_unit.usd_per_credit`).
  - Reproduce the five-row action table (one-shot `-p --model`, interactive `/model`,
    `COPILOT_MODEL` env var, the `settings.json` `"model"` key, per-agent `model:` frontmatter)
    — it is the most practically useful block on the page.
  - `### Worked example`: map the task to a `task_profiles` size, run `est` for 2–3 candidates
    plus one lane cheaper as a sanity check, present USD and AIC, then give the single command.
  - Explain the lessons hook: if `tasks/lessons.md` exists, routing entries override the
    default tier heuristics — that is the loop closing, and it is easy to miss.
  - Tier words only on the page; no model ids, no prices, no plan allowances. Ground in
    `bin/copilot_pricing.py` (`est`, `models --profile`, `runway`, `prefs`).
- sentinels: **direct pins** in `tests/test_copilot_bundle.py`: `bin/copilot_pricing.py`,
  `est`, `{{POLYTROPOS_ROOT}}`, `copilot --agent route`, `tasks/lessons.md`.
  `tests/test_copilot_docs.py` and `tests/test_harness_update.py` also reference this skill.

### copilot/usage
- verdict: keep
- skill-md: unchanged (517). Dense and complete. Its honesty rules are the reason it exists:
  the multi-model `≈` attribution rule (the whole token split goes to the LAST model because
  `events.jsonl` records no per-model split — never fabricate one), the `totalNanoAiu`
  cross-check that is never converted to USD or AIC, missing logs reported as missing, and the
  show-the-error rule. The never-invoke-the-`copilot`-CLI-to-gather-usage rule is a CLAUDE.md
  invariant.
- references: none
- fragment-notes:
  - Open on the read-only guarantee: the engine reads `<copilot-home>/session-state/*/
    events.jsonl` only, never the `*.db` stores, and never invokes the `copilot` CLI — because
    invoking it would spend real AI Credits and hit the network.
  - Explain the `≈` flag properly; it is the page's most valuable honesty note and readers
    will otherwise treat a flagged session as precise.
  - `totalNanoAiu` is Copilot's own reported consumption unit and appears only as a labeled
    cross-check; the authoritative estimate is tokens x per-MTok rates → USD → AIC.
  - Distinguish this page from `route` in one line: this is historical and read-only; "what
    should I use next" belongs to `route`.
  - Ground flags in `bin/copilot_usage.py` (`--days`, `--top`, `--copilot-home`,
    `--session-dir`); show no dollar figure or credit value.
- sentinels: **direct pins** in `tests/test_copilot_bundle.py`: `bin/copilot_usage.py`,
  `{{POLYTROPOS_ROOT}}`, `read-only`, `copilot --agent usage`.

## codex

### codex/architect
- verdict: keep
- skill-md: unchanged (537). Tight and complete: the root-resolution proof with its
  reject-a-literal-placeholder rule and doctor fallback, the two kit files with the
  driver-parsed `### <ID> — <title>` grammar, the verbatim status vocabulary, the
  id-or-tier-word model field with its rationale (ids are unconfirmed for a preview
  generation, so a tier word survives an id correction), the skip-upward rule for unpopulated
  tiers, and the never-invoke-the-real-`codex`-CLI rule for verify commands.
- references: none
- fragment-notes:
  - Explain the Codex-specific model-pin design, because it is genuinely different: a task's
    `model` may be a model id OR a tier word resolved at dispatch, and tier words survive an id
    correction that lands only in the pricing data. This is the honest response to preview-
    generation id uncertainty and deserves a paragraph.
  - Reproduce the root-resolution proof once for the whole Codex section (it opens all twelve
    Codex skills) and explain what it protects against: a guessed or stale path, and a literal
    unresolved placeholder meaning the bundle is not installed.
  - `### Cost & safety`: a verify command must never invoke the real `codex` CLI — a live
    dispatch spends subscription usage limits or API dollars.
  - Ground in `bin/codex_pricing.py` (`models`, `est <PROFILE> <MODEL_OR_TIER>`) and
    `bin/codex_execute.py`; no model ids and no prices on the page.
- sentinels: **direct pins** in `tests/test_codex_bundle.py`: `bin/codex_execute.py`,
  `bin/codex_pricing.py`, `tasks/kits/`, `pending | in-progress | done | blocked`, plus
  roster-wide checks (name matches dir, no `model:` pin in frontmatter, `{{POLYTROPOS_ROOT}}`
  present, no Fable naming, no absolute path, no cross-harness surface, no real model-id
  literal). **`architect` is one of the seven stems mirrored into `codex/prompts/`** — any
  edit requires `python3 bin/sync_codex_surfaces.py build` in the same task, staged together;
  `tests/test_codex_surfaces.py` is the tripwire.

### codex/bench-routing
- verdict: enrich
- skill-md: 152-word body — the thinnest skill in the whole roster, and one of the thin seven.
  The density is genuine and mostly right: root proof, three real commands, and four honesty
  clauses (composite index, screenshot-transcribed, benchmark cost is not this repo's pricing,
  recommend as a prior to verify). But one acting fact is missing, and it is the same one the
  Copilot sibling spends its longest section on. The skill says "use the repo's measured
  comparison surface when evidence exists" without naming it or bounding it — so a model
  reasonably runs `bin/bench_routing.py compare` and presents its numbers as Codex evidence.
  They are not: `compare` joins against this repo's Claude-harness kit ledger, that ledger
  carries per-task implementer outcomes only, and **`compare` has no `--harness` flag**
  (confirmed against `python3 bin/bench_routing.py compare --help`, whose options are
  `--benchmarks`, `--pricing-dir`, `--kits-dir`, `--floor`, `--json`). Add two sentences,
  mirroring the wording already proven in `copilot/bench-routing`: name `compare`, state that
  its ledger is Claude-side implementer evidence with no Codex per-role outcome data, state
  that it has no `--harness` flag and that implying one is a fabrication, and say the benchmark
  recommendation therefore stands unchallenged from Codex. ~50 words; the body stays the
  roster's thinnest.
  Every existing sentence stays verbatim — five of them are directly test-pinned.
- references: none — a ~200-word card has nothing to defer.
- fragment-notes:
  - The page's central honesty point is the enriched one: from Codex the benchmark prior
    stands unchallenged, because the measured ledger is Claude-side. Say it once, plainly,
    rather than implying cross-harness parity.
  - Preserve every transcription and coverage limitation: the Intelligence Index is a
    general-capability composite transcribed from a screenshot, not measured Codex task
    performance, and benchmark workload cost is neither this repo's pricing nor a bill.
  - Show `roles --harness codex`, `rank`, and `demo`; ground them in
    `python3 bin/bench_routing.py --help` and note that `demo` is synthetic and touches no
    real data.
  - Frame a role recommendation as a prior to verify, never a guaranteed winner — the skill's
    own closing phrase, and it is test-pinned.
- sentinels: **direct pins** in `tests/test_codex_analysis_skills.py`: `Intelligence Index`,
  `screenshot`, `not this repository's pricing` (whitespace-flattened),
  `not a guaranteed winner`, plus `POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`, no `model:` in
  frontmatter, no `/Users/`, and explicitly **no `data/pricing.json` and no
  `data/pricing.copilot.json` string anywhere in the file** — the enrichment must name only
  the Codex pricing data or nothing, and must not introduce either forbidden path. Also
  roster-wide pins in `tests/test_codex_bundle.py`. Not a mirrored stem, so no
  `sync_codex_surfaces` run is required.

### codex/context-weight
- verdict: keep
- skill-md: unchanged (181) — one of the thin seven, and correctly thin. Its four real Codex
  surfaces are shown with the right flags, and the rest of the file is fidelity honesty, all
  of it directly test-pinned: rollout logs give token-count growth curves and record-type byte
  shares but **not content provenance**, byte shares must never become claims about which
  prompt or tool filled the window, `watch` is Claude-only, `constraints --harness codex` can
  only return the engine's explicit fidelity-limit line, and the audit is about resident
  tokens and never dollars. That is complete for what Codex can honestly answer — this is the
  clearest case in the roster of thin meaning "bounded by the data", not "underwritten".
- references: none
- fragment-notes:
  - Build the page around the fidelity ceiling rather than around features: Codex can show how
    context grew and roughly what kind of record filled it, and cannot say which prompt,
    instruction, or tool did — and the skill refuses rather than approximating.
  - Note that `constraints` and `watch` exist on the engine but are Claude-only in substance;
    on Codex they return the fidelity-limit line. Cross-link the Claude page for the live
    threshold story instead of implying Codex has one.
  - Show the four commands with `--codex-home` and `--project` where the skill shows them;
    ground in `python3 bin/context_weight.py --help` and its subparsers.
  - `### Cost & safety`: the audit is tokens-only; no context estimate is a billing statement,
    and every estimated figure carries its label.
- sentinels: **direct pins** in `tests/test_codex_analysis_skills.py`:
  `token-count growth curves`, `not content provenance`, `` `watch` is Claude-only ``,
  `cannot answer live pruning`, `never dollars`, plus `POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`,
  no `model:` in frontmatter, no `/Users/`, and the forbidden `data/pricing.json` /
  `data/pricing.copilot.json` strings. Roster-wide pins in `tests/test_codex_bundle.py`.

### codex/doctor
- verdict: keep
- skill-md: unchanged (206) — one of the thin seven, and Codex-only by design. Every line is
  an acting fact or a safety line: the root proof, the two read-only doctor invocations with
  `--repo-root` and `--codex-home`, the `--dry-run` preview, the six component states to
  summarize (`install`, `up-to-date`, `managed-update`, `conflict`, `unmanaged`, `skip`), the
  give-the-engine's-exact-remedy rule, the three never-suggest prohibitions (`--force`,
  deleting the Codex home, overwriting `config.toml`), the explicit-authority-before-write
  rule, and the restart reminder. There is nothing here a normal run does not need.
- references: none
- fragment-notes:
  - This is the third Phase 3 pilot and the designated thin, safety-heavy page — the template
    must prove it can carry a short card without padding it. Resist inventing depth the skill
    does not have.
  - Explain the six component states in a table, one honest sentence each, and say what a
    reader does about each. That is the page's main contribution over the card.
  - `### Cost & safety`: doctor and `install --dry-run` are byte-read-only; an actual
    `install` or `--refresh-managed` is a write that needs explicit user authority. Managed
    refresh applies only to unchanged recorded copies — user-edited or unrelated destinations
    stay conflicts.
  - State the three prohibitions on the page as prominently as the skill states them: never
    `--force`, never delete the Codex home, never overwrite `config.toml`.
  - Parity note: Codex-only. The matrix's two dashes here are a design decision — Claude and
    Copilot have no equivalent install-state surface in this repo.
  - Ground in `bin/harness_select.py doctor --harness codex`.
- sentinels: **direct pins** in `tests/test_codex_core_skills.py`
  (`test_doctor_commands_parse_and_require_authority_for_writes`): the component-state tokens,
  `read-only doctor`, `explicit user`, `--refresh-managed`, plus
  `POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`, `harness_select.py doctor --harness codex`, no
  `model:` in frontmatter, and no `/Users/`. Also `tests/test_codex_bundle.py` and
  `tests/test_codex_onboarding_e2e.py`.

### codex/effort
- verdict: keep
- skill-md: unchanged (591). Complete and honest: the billing-mode-first determination, the
  ladder-from-data rule with the never-enumerate-the-levels-yourself instruction, the
  modes-are-not-rungs distinction (`ultra` / `fast` are modes with unpublished CLI surfaces —
  relay the note, never invent a flag), the one confirmed one-shot surface
  (`-c model_reasoning_effort=<level>`), the driver's `--effort` with its run-time validation,
  and the step-up-one-level-on-evidence rule.
- references: none
- fragment-notes:
  - Lead with the billing-mode split, because it changes the whole framing: under a ChatGPT
    sign-in, deeper effort is usage-limit burn and any dollar figure is a labeled
    API-equivalent proxy; under `OPENAI_API_KEY`, the dollars are real.
  - Never enumerate the effort levels on the page — show `codex_pricing.py knobs` instead, and
    explain the modes-vs-rungs distinction, which is the subtlety readers get wrong.
  - `### Worked example`: omit the override for routine work; on a concrete failure, step up
    exactly one level and re-run; step down for bulk or latency-sensitive work.
  - The relationship line worth repeating: effort fixes a thinking-time gap, a tier jump fixes
    a capability gap — try the cheaper move first.
  - Ground in `bin/codex_pricing.py knobs` and `bin/codex_execute.py run --effort`.
- sentinels: **direct pins** in `tests/test_codex_bundle.py`: `bin/codex_pricing.py`, `knobs`,
  `model_reasoning_effort`, `bin/codex_execute.py`, `--effort`, and a check that the skill
  does NOT enumerate the effort levels — plus the roster-wide checks.
  **`effort` is one of the seven mirrored stems** — any edit requires
  `python3 bin/sync_codex_surfaces.py build` in the same task.

### codex/escalate
- verdict: keep
- skill-md: unchanged (849). Every section earns its place: the root proof, the billing-mode
  determination, Step 0's don't-pretend-a-vibe-is-a-verify rule, the ladder stated as exactly
  what `bin/codex_execute.py` implements (strictly-above tiers, first model in pricing-file
  order, empty tiers skipped — with the concrete consequence that an unpopulated `strong`
  resolves upward to frontier), the reasoning-effort lever on the frontier hop, the refusal
  fallback, and the kit-task pointer.
- references: none
- fragment-notes:
  - The Codex-specific fact the page must not bury: this roster ships an unpopulated `strong`
    tier, so asking for `strong` today resolves UPWARD to the frontier model. A reader who
    misses this thinks there is a rung that is not there.
  - Draw the ladder and stress that each hop carries evidence only — what was tried and the
    exact check output. The diagnosis is what keeps the expensive hop short.
  - The extra lever here versus the other harnesses: prefer `-c model_reasoning_effort=medium`
    for the first frontier attempt and step up one level at a time, only on continued failure.
  - `### Cost & safety`: under a ChatGPT plan every hop is usage-limit burn and any dollar
    figure is a labeled proxy, never a bill; under an API key the dollars are real. Always
    report which rung passed so the ladder's savings are visible.
  - Ground in `bin/codex_pricing.py models --json` and `bin/codex_execute.py run --kit --task
    [--effort]`; show no model id.
- sentinels: **direct pins** in `tests/test_codex_bundle.py`: `codex exec`,
  `bin/codex_execute.py`, plus roster-wide checks (no real model-id literal, no Fable naming,
  placeholder present). **`escalate` is one of the seven mirrored stems** — any edit requires
  `python3 bin/sync_codex_surfaces.py build` in the same task.

### codex/execute
- verdict: keep
- skill-md: unchanged (264) — one of the thin seven, and among the most heavily test-pinned
  files in the roster relative to its length. It carries the root proof, the read-the-fences
  instruction, the exact status vocabulary, the do-not-rewrite-a-brief-to-fit-reality rule,
  the dry-run-vs-real-run distinction with an explicit spend warning and an
  obtain-authority-first rule, the never-represent-a-dry-run-as-a-real-dispatch line, and the
  honest agent note (the canonical `kit-implementer` / `kit-verifier` / `phase-reviewer`
  agents are preferred where interactive delegation exists, **plugin install does not install
  them**, and the headless driver remains the fallback). Density here is the point: this is a
  spending surface, and the file is all rails.
- references: none
- fragment-notes:
  - Contrast honestly with the Claude execute page: no parallel fan-out, no warm clusters, no
    session-side escalation valve — the driver's ladder is the escalation mechanism.
  - Make the dry-run boundary unmissable: `status` and `run --dry-run` inspect without
    dispatching; a real `run` or a non-dry `review` launches headless Codex and spends
    subscription usage or API-metered funds.
  - State the agent honesty exactly as the skill does: those three agents are preferred when
    available, plugin install does not install them, and the headless driver is the functional
    fallback. Do not let the page imply the plugin ships them.
  - `### Failure modes`: rerun the task's verify command independently before accepting
    completion, and review each completed phase for plan drift.
  - Ground in `bin/codex_execute.py` (`status`, `run --kit --task [--dry-run]`,
    `review --kit --phase`).
- sentinels: **direct pins** in `tests/test_codex_core_skills.py`
  (`test_execute_uses_real_driver_modes_and_safe_contract` and
  `test_execute_names_optional_agents_without_claiming_plugin_installs_them`):
  `tasks/kits/<slug>`, `pending | in-progress | done | blocked`, `spends subscription usage`,
  `verify command independently`, the three agent names,
  `Plugin install does not install those agents` (newline-flattened),
  `headless driver remains`, plus `POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`,
  `harness_select.py doctor --harness codex`, no `model:` in frontmatter, no `/Users/`. Also
  `tests/test_codex_bundle.py`. Not a mirrored stem.

### codex/frontier-check
- verdict: keep
- skill-md: unchanged (881 — near the ~900 budget, so future additions must displace
  something). Complete: root proof, billing-mode-first, the derive-from-data block including
  the `est <PROFILE> frontier` tier-word trick that avoids hardcoding an id, the explicit
  "this file must never contain a real model id" self-rule, the unpopulated-`strong`
  consequence, the worth-it / not-worth-it lists, the caveats (relay the model's own `notes`;
  classifier refusals fall back to mid; if `/model` lists no frontier candidate, say so), five
  optimal-run practices, the mechanism table, and the standing architect/escalate
  recommendation.
- references: none
- fragment-notes:
  - The page must hold the never-name-a-model-id line and explain why: ids are best-effort for
    a preview generation, and the pricing data's own `model_ids_note` is where corrections
    land. Show `models --json` filtered to `tier == "frontier"` instead.
  - Repeat the roster fact that shapes every decision here: `strong` is unpopulated, so asking
    for `strong` lands on frontier — there is no intermediate rung to try first, which is why
    "a concrete mid-tier failure on this same task" is the strongest available signal.
  - `### Cost & safety`: under a ChatGPT plan lead with burn, not dollars; frontier burns
    usage limits fastest of anything on the roster. `fast` mode exists but its CLI surface is
    unpublished — point at release notes, never invent a flag.
  - Reproduce the four-row mechanism table (one-shot `codex exec --model` with `--full-auto`
    where it must edit files, the `/model` picker, the `config.toml` default,
    `-c model_reasoning_effort=<level>`).
  - Ground in `bin/codex_pricing.py` (`models --json`, `est`, `plans`).
- sentinels: **direct pins** in `tests/test_codex_bundle.py`: `bin/codex_pricing.py`,
  `frontier`, plus the roster-wide no-Fable-naming and no-real-model-id-literal checks — the
  latter is exactly what the skill's own self-rule protects.
  **`frontier-check` is one of the seven mirrored stems** — any edit requires
  `python3 bin/sync_codex_surfaces.py build` in the same task.

### codex/journal
- verdict: keep
- skill-md: unchanged (618). Complete, and notably better-scoped than its Claude sibling: root
  proof, collector with its real flags, the write-in-session-only rule with the explicit
  `--dry-run`-is-the-only-sanctioned-invocation prohibition (its headless mode dispatches the
  Claude CLI — a cross-harness spend this bundle must never trigger), inbox and ask-the-tools,
  the next-day runbook with the byte-identical-except-What/How constraint, and the privacy
  paragraph. This is the version `claude/journal` should read like after its relocation.
- references: none
- fragment-notes:
  - The prohibition is the headline: never run `journal_summarize.py` without `--dry-run` from
    this harness. Explain why — the headless mode dispatches a different harness's CLI.
  - Say that the collector is harness-agnostic and reads all three homes read-only, so the
    journal produced from Codex is the same cross-harness journal.
  - `### Cost & safety`: the digest is metadata-only and never carries transcript or message
    text; everything stays under gitignored `journal/`; the ask-the-tools pack is offline text
    generation with no network, OAuth, Graph, or MCP call ever added to fetch content.
  - The Codex-specific honesty line to carry: figures for Codex in the runbook are
    API-equivalent proxies, never a bill.
  - Ground in `bin/journal_collect.py`, `bin/journal_summarize.py --dry-run`,
    `bin/journal_askpack.py`, `bin/journal_plan.py` (`build` / `prompt` / `check` / `done` /
    `defer`).
- sentinels: **direct pins** in `tests/test_codex_bundle.py`: `bin/journal_collect.py`,
  `--dry-run`, plus the roster-wide checks. **`journal` is one of the seven mirrored stems** —
  any edit requires `python3 bin/sync_codex_surfaces.py build` in the same task.

### codex/memory
- verdict: keep
- skill-md: unchanged (198) — one of the thin seven, and the most constrained file in the
  roster. Everything present is contract: pull-only recall, derive a short keyword query,
  inject only what recall returns, never dump or bulk-read the store or index, never bypass the
  relevance gate or expand the budget, preserve each winner's source/confidence/expiry/
  contradiction/staleness semantics, always require an explicit `--memory-dir`, and the
  no-automatic-write / no-background-watcher / no-network-sync / no-pricing-coupling
  declaration. Nothing is missing that a normal run needs.
  **Enrichment here is unusually constrained and any future task must know it:** the test
  suite asserts the file does NOT contain the strings `Path.home`, `subprocess`, `urlopen`,
  `codex exec`, or `pricing.json`. That last one means the file cannot even mention a pricing
  data path — the no-pricing-coupling rule is enforced lexically, not just semantically.
- references: none
- fragment-notes:
  - Build the page around the bound rather than the feature: recall is relevance-gated and
    budget-capped, and an empty recall is the system working correctly.
  - `### Cost & safety` is the main event: the store is private local user data, there is no
    automatic write, no background watcher, and no network sync; adding, updating, verifying,
    or removing a fact is a separate user-authorized store operation, while recall and review
    are read-only.
  - Explain the explicit `--memory-dir` requirement as a design seam, not a chore — it is what
    keeps every test and example off a real store, together with `--now` for deterministic
    date math.
  - Show `--demo` as the safe way to see the shape without touching a real store. Ground in
    `bin/memory_recall.py` and `bin/memory_store.py review`.
  - **T14 carry-forward (P3 finding 6).** State plainly that this card is deliberately
    recall-only: it documents `review` only, where the Claude skill documents
    add/update/remove/list/review too. Say so so the parity row reads as a scoped port, not
    a half-finished one. Verdict stays `keep`.
- sentinels: **direct pins** in `tests/test_codex_memory_skill.py`
  (`test_pull_only_privacy_and_honesty_contract` and
  `test_no_implicit_home_network_harness_or_pricing_behavior`): the phrases `pull-only`,
  `budget-capped winners`, `Never dump or bulk-read`, `source, confidence`,
  `expiry, contradiction, and staleness`, `` explicit `--memory-dir` ``, `no automatic write`,
  `background watcher`, plus `POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`, no `/Users/`, and the
  five **negative** pins listed above. Also `tests/test_codex_bundle.py`. Not a mirrored stem.

### codex/route
- verdict: keep
- skill-md: unchanged (761). Complete: root proof, three engine commands, billing-mode-first
  with the limited-preview `/model` caveat, the four-tier vocabulary with the unpopulated-
  `strong` resolve-upward note, a speed-guidance section drawn entirely from the data's `knobs`
  and model `notes`, the estimate procedure, and a six-row mechanism table covering one-shot
  dispatch, the `/model` picker, session start, the `config.toml` default, named profiles, and
  reasoning effort.
- references: none
- fragment-notes:
  - The billing-mode split is the page's spine: ChatGPT sign-in means usage-limited, not
    token-billed, and every dollar shown is a labeled API-equivalent relative-burn proxy;
    `OPENAI_API_KEY` means real token-metered dollars. Never present a subscription figure as
    a bill — this is a CLAUDE.md invariant.
  - Reproduce the six-row mechanism table; it is the most reusable block on the page, and
    `[profiles.<name>]` in `config.toml` is the one surface a reader is least likely to know.
  - Cover speed honestly: the cheap tier is the low-latency lane; the frontier model's
    Cerebras availability is a speed fact in its `notes`, not a price; `fast` mode exists but
    its CLI surface is unpublished, so point at release notes and never invent a flag.
  - Say plainly that model ids in this data are best-effort for a preview generation and that
    corrections land in the Codex pricing data and only there — then show no id on the page.
  - Ground in `bin/codex_pricing.py` (`est`, `models --profile`, `plans`).
- sentinels: **direct pins** in `tests/test_codex_bundle.py`: `bin/codex_pricing.py` and the
  dispatch surface, plus roster-wide checks. `tests/test_codex_setup.py`,
  `tests/test_codex_onboarding_e2e.py`, and `tests/test_codex_surfaces.py` all exercise this
  skill's install and mirror path. **`route` is one of the seven mirrored stems** — any edit
  requires `python3 bin/sync_codex_surfaces.py build` in the same task; the surfaces test is
  the tripwire.

### codex/usage
- verdict: keep
- skill-md: unchanged (550). Complete, and its three-branch honesty ladder is the reason it
  exists: tokens found → per-model table plus the standing proxy disclaimer with `≈` flagging
  for multi-model rollouts; activity but no tokens → counts only, unpriced, no dollar figure
  at all; nothing found → say the logs are empty. Never fabricate or zero-fill in any branch.
  The read-only declaration (JSONL only, never a `*.db`, never a `codex` invocation) is a
  CLAUDE.md invariant.
- references: none
- fragment-notes:
  - Present the three-branch ladder as the page's central structure — present exactly the
    branch the engine returns, never upgrade or downgrade it. That is the honesty design and
    it reads well as a table or a small decision diagram.
  - State the read path precisely: `~/.codex/session_index.jsonl`, `~/.codex/history.jsonl`,
    and `~/.codex/sessions/YYYY/MM/DD/*.jsonl`, strictly read-only, JSONL only, never a `*.db`,
    never a `codex` CLI invocation.
  - `### Cost & safety`: under a ChatGPT plan every dollar figure is a labeled API-equivalent
    relative-burn proxy and a routing aid, never a bill; relay the engine's disclaimer
    verbatim. Real dollars are a bill only under `OPENAI_API_KEY`-metered use.
  - Explain the `≈` flag: a multi-model rollout's whole token count is attributed to the last
    model seen in that file, because no per-model split is recorded — never fabricate one.
  - Ground flags in `bin/codex_usage.py` (`--days`, `--top`, `--codex-home`, `--json`).
- sentinels: **direct pins** in `tests/test_codex_bundle.py`: `bin/codex_usage.py`, `proxy`,
  plus roster-wide checks; `tests/test_codex_usage.py` covers the engine whose branch strings
  this skill quotes. **`usage` is one of the seven mirrored stems** — any edit requires
  `python3 bin/sync_codex_surfaces.py build` in the same task.
