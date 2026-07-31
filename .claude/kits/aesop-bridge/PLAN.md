# PLAN — aesop-bridge

Integrate polytropos with **aesop** (https://github.com/agentmc15/aesop — the user's own
TypeScript "environment compiler": one `aesop.yaml` manifest compiled into native agent config
for Claude Code, Codex, Copilot, Cursor, Antigravity, VS Code; federated content registries;
goal loops with three hard stops including `budget_usd`; pathway profiles as a cost/accuracy
dial). All behavior claims about aesop in this kit were verified against commit
`55066175a5268887acad39bc859584d13fab09db` (short: `5506617`) and are pinned to it.

## Goal

Make the two systems complementary layers with a clean boundary:

- **aesop** stays the harness-portable environment compiler — deliberately price-agnostic and
  model-version-agnostic (abstract tiers `strong|mid|cheap`, abstract `budget_usd` stops).
- **polytropos** becomes the Claude-concrete pricing/routing layer aesop can consume:
  1. this repo works as an aesop **registry** (its `skills/<name>/SKILL.md` layout already
     matches aesop's lookup), with the two portable skills self-contained after vendoring;
  2. the plugin's **architect/execute** skills behave correctly inside aesop-managed projects
     (never hand-edit compiled/fenced files);
  3. a stdlib **bridge script** turns `data/pricing.json` into the concrete numbers aesop's
     dials need (tier→model mapping, est cost per loop tick, budget runway);
  4. a **doc** explains consumption and proposes the aesop-side follow-ups (executed later, in
     the aesop repo, through aesop's own process — never from this kit).

**Done looks like:** `python3 -m unittest discover -s tests -v` green (including two new test
files); `python3 bin/sync_pricing_refs.py --check` exits 0; `route` and `fable-check` carry the
three-step pricing-resolution ladder; `python3 bin/aesop_bridge.py tiers --json` emits a mapping
whose values are all model keys in pricing.json; `docs/AESOP-INTEGRATION.md` exists with the five
required sections; architect+execute contain the aesop-managed-target rules and still satisfy the
kit contract checklist in CLAUDE.md.

## Architecture & key decisions

- **D1 — All work lands in this repo; aesop-side changes are a written proposal only.**
  Executor guardrails forbid touching anything outside this repo, and aesop has its own locked
  invariants (`src/types.ts`/schema LOCKED, doc-first harness matrix, phase-gated builds).
  Cross-repo edits from a kit would violate both sides' rails. The integration is designed so
  the aesop side needs **zero changes to work today**; proposals in the doc are improvements,
  not prerequisites.

- **D2 — Registry bridge uses the existing layout; export surface is `route` + `fable-check`
  only.** At aesop@5506617, `importPrimitive` (src/federation.ts) resolves skills at
  `registry/skills/<name>`, `skills/<name>`, or `skills/*/<name>` — this repo's `skills/route/`
  and `skills/fable-check/` already qualify, so `registries: [github:agentmc15/polytropos]`
  plus `aesop add skill route --from polytropos` works without restructuring. Not
  exported (and documented as such): `cost-report` and `setup` (depend on `bin/` scripts,
  `~/.claude` paths, statusline wiring), `architect` and `execute` (depend on Claude Code's
  Agent tool `model` parameter and this plugin's kit contract). They remain plugin-only.

- **D3 — Vendored self-containment via generated, test-enforced mirrors.** aesop's `add skill`
  vendors the *whole skill directory* (`readDirRecursive`), so a copy of pricing.json placed at
  `skills/<name>/references/pricing.json` survives vendoring into another repo; the repo-root
  `data/pricing.json` does not. Therefore: `bin/sync_pricing_refs.py` writes byte-identical
  mirrors into `skills/route/references/` and `skills/fable-check/references/`, and a unittest
  fails on any drift. `data/pricing.json` remains the **only hand-edited numeric source**; the
  mirrors are machine-written replicas. The two skills gain a third resolution step
  (`references/pricing.json`, with a `cached_date` staleness check) after the existing
  `${CLAUDE_PLUGIN_ROOT}` and relative-path steps.

- **D4 — Sequencing: the in-flight `harden-plugin` kit finishes first.** harden-plugin T6
  rewrites the exact pricing-source sentences in `route` and `fable-check` that this kit's T3
  extends. T3's brief quotes the **post-harden-plugin-T6** text as its anchor; if that text is
  not found verbatim, the implementer stops and reports (do not improvise a merge).

- **D5 — The budget bridge is copy-paste numbers, not a code dependency.**
  `bin/aesop_bridge.py` computes, from pricing.json at run time: the aesop-tier→current-model
  mapping, an estimated cost per Ralph-loop tick (aesop's runner defaults to a flat estimate
  when the agent CLI emits no cost JSON), and how many iterations a `budget_usd` buys. The user
  pastes numbers into `aesop.yaml` / goal recipes. This respects aesop's no-new-runtime-deps
  invariant and this repo's stdlib-only invariant. Convention: **"current model per tier" =
  first model with that `tier` value in pricing.json file order** (newest are listed first per
  tier; `json.load` preserves order).

- **D6 — Aesop-managed target detection and conduct (architect/execute).** A target project is
  aesop-managed iff `aesop.yaml` exists at its root **or** `CLAUDE.md`/`AGENTS.md` contains an
  `<!-- aesop:begin` fence. In such projects, fenced/compiled files are read-only: guardrails go
  into `aesop.yaml` under `primitives.instructions.blocks` followed by `aesop compile`. Kit
  directories and kit-prefixed agent files are safe to write: at aesop@5506617, `sync` diffs only
  files it computes as outputs plus lock-tracked files — files aesop never emitted are invisible
  to it. Never reuse the name of an agent listed in the manifest's `primitives.agents` (compile
  would overwrite it).

- **D7 — SHA-pinned claims.** Every statement about aesop behavior (registry lookup paths,
  vendoring, sync drift scope, Ralph cost parsing, `$0.25` default tick estimate) is true at
  `5506617`. The doc must say "as of" that commit; executors must not "verify" claims against a
  newer aesop checkout and must not report upstream drift as a task failure.

## Constraints and OUT-OF-SCOPE fence

Executors must NOT:

- **Touch anything outside this repo.** No edits under `/path/to/aesop`
  (reference-only), no `~/.claude/`, no plugin re-install.
- **Run `aesop init`/`aesop compile` in this repo or convert it to aesop management.** This
  repo's CLAUDE.md is hand-authored executor guardrails, not compiled output.
- **Edit `data/pricing.json`** — no value, key, or formatting changes. Mirrors are written only
  by `bin/sync_pricing_refs.py`.
- **Add dependencies or tooling.** Python stays stdlib-only; no npm/node anything; no new
  requirements files.
- **Restructure `skills/` into a `registry/` layout**, rename skills, or add new skills/commands.
- **Touch the `harden-plugin` kit** (its files under `.claude/kits/harden-plugin/` and its
  agents) beyond reading them.
- **Commit or push.**

## Risks & tripwires

- **Anchor text missing** (T3, T5, T6 quote current file text): if a quoted anchor is not found
  verbatim, STOP and report — most likely harden-plugin has not finished, or a file drifted.
  Do not approximate the replacement.
- **Mirror drift**: if `cmp data/pricing.json skills/route/references/pricing.json` fails after
  your change and your task didn't run the sync script, you edited a mirror by hand — revert and
  use the script.
- **Kit-contract breakage** (T5, T6): architect and execute share one kit contract (see
  CLAUDE.md invariant). After editing either skill, re-check BOTH against the checklist: kit
  layout, task fields, status vocabulary `pending | in-progress | done | blocked`, phase
  headings, `depends:`/`independent:` marking, model-field-overrides-frontmatter rule. The
  additions in this kit are append-only; if satisfying a brief seems to require altering any
  contract element, stop and report.
- **Skill bloat**: the portable skills are runtime prompts; additions are pinned verbatim in the
  briefs. If tempted to add explanatory text beyond the brief, don't.
- **Test flakiness via real dates**: `intro_pricing` comparisons use today's date. Tests must
  pass a fixed `today` to the pure functions (T7 exposes it) — never depend on the wall clock
  for an assertion.
