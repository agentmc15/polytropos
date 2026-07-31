# aesop compile round-trip — a proposal

This document specifies the aesop-side work needed to make this repo's Copilot bundle a real
`aesop compile` target and to reconcile the one deliberate emitter divergence recorded in the
copilot-harness kit. It is written to be the **input to a future `/polytropos:architect`
run executed inside the aesop repo**, under aesop's own phase-gated process — not a change to
this repo. As written, nothing here was executed and nothing aesop-side was built — see the
status note below for what has since shipped upstream.

> Every load-bearing aesop behavior claim below is pinned to aesop commit `aesop@5506617`
> (full: `55066175a5268887acad39bc859584d13fab09db`) and must be re-verified against aesop HEAD
> by the future run. Treat each pin as a snapshot, not a guarantee. This document quotes no
> prices, no credit values, and no plan allowances; numbers of that kind live only in
> `data/pricing.copilot.json`, and model ids appear only as illustrative `<id>` placeholders.

> **Status update (2026-07-02).** The *extension* half of "The divergence to reconcile" shipped
> upstream as **aesop PR #1** (`agentmc15/aesop`, branch `copilot-agent-md-extension`): the
> copilot emitter now emits `.github/agents/<name>.agent.md`, matching this repo's bundle and the
> CLI-documented form. It followed aesop's process — harness-matrix doc updated first, golden
> fixtures regenerated, **no change to the LOCKED `src/types.ts`/schema** — with build, lint, and
> its 54-test suite green. The pins below held: aesop HEAD was exactly `aesop@5506617` when the
> change was made. PR #1 **merged** to aesop `main` (rebase; commits `3f539b3` + `c88d538`) with
> CI green — including aesop's own `compile --check` self-dogfood, which caught that its
> repo's self-config had to regenerate too. Nothing in *this* repo changed. The
> *location / registry-exposure* question (Options A/B/C below) and the full compile round-trip
> remain future aesop-side work — that is what the rest of this document still specifies.

## Why this document exists

The compile round-trip is a change to aesop's emitter and federation code, not to this repo.
Three facts force that split. First, aesop's `src/types.ts` and its manifest schema are
**LOCKED** as of `aesop@5506617`: any change there needs explicit approval on the aesop side,
and it flows through aesop's doc-first harness-matrix process plus its golden-fixture process
for emitter output. Second, this repo forbids node/npm and never runs `aesop compile`, so a
round-trip could not even be verified here — the compiler is deliberately absent from this
repo's toolchain. Third, choosing between the exposure options below requires `aesop compile`
validation that only the aesop-side effort can run; building either half early would ossify an
unvalidated choice. The aesop clone that would host that work is session-scoped reference
material and may not exist, so this repo ships the spec and stops there.

"Done" end-to-end looks like this: aesop registers this repo as a registry source, resolves its
Copilot primitives through `importPrimitive`, and `aesop compile` against `copilot/aesop.yaml`
emits a `.github/` bundle that matches this repo's hand-authored `copilot/.github/` tree closely
enough that the documented diff is empty or deliberate — agents carrying the CLI-documented
`.agent.md` extension, `model:` frontmatter pins intact, the `{{POLYTROPOS_ROOT}}`
placeholder preserved, and skills under `skills/<name>/SKILL.md`. Golden fixtures for the
copilot emitter land on the aesop side, and both repos' test suites stay green. Until all of
that is validated inside the aesop repo, this repo builds nothing.

## Current state (pinned at aesop@5506617 and this repo's HEAD)

The aesop side, as of `aesop@5506617`:

- aesop is the environment compiler at `github:agentmc15/aesop`: one manifest (`aesop.yaml`)
  compiles into many harness config bundles via per-harness emitters.
- The copilot emitter emits agents as `<name>.md`, while Copilot CLI's own how-to documents
  the `<name>.agent.md` form; GitHub's config reference accepts both extensions.
- Registry lookup is `importPrimitive` in `src/federation.ts`: a SKILL resolves at
  `registry/skills/<name>`, `skills/<name>`, or `skills/*/<name>` relative to a source root,
  and AGENTS resolve analogously at `agents/<name>.md` or `registry/agents/<name>.md` at a
  source root.
- Vendoring semantics: `aesop add skill <name> --from <source>` copies the whole primitive
  directory into the consumer's `.aesop/vendor/…` with the upstream SHA pinned in the lockfile;
  `aesop update` / `aesop update --apply` is the refresh flow.
- Guardrails: `src/types.ts` and the schema are **LOCKED**; emitter output changes go through a
  doc-first harness-matrix process and a golden-fixture process.

This repo's side, at its current HEAD:

- `copilot/aesop.yaml` is the manifest — the declared source of truth for what the Copilot
  bundle contains (harnesses, invariants, the shared instruction block, the agent list, the
  vendored skill list).
- The hand-authored bundle lives under `copilot/.github/`: agents at
  `copilot/.github/agents/*.agent.md`, instructions at `copilot/.github/copilot-instructions.md`,
  and skills at `copilot/.github/skills/<name>/SKILL.md`. The tree is authored in the formats
  aesop's copilot emitter produces as of `aesop@5506617`, with `.agent.md` used deliberately.
- `tests/test_copilot_bundle.py` enforces manifest ↔ bundle consistency by unittest instead of
  by running the compiler: every manifest-named agent exists as a bundle file, the shared
  doctrine sentence appears verbatim in both places, and each agent's `model:` pin is validated
  by TIER against `data/pricing.copilot.json`.
- Bundle files carry the `{{POLYTROPOS_ROOT}}` placeholder; `bin/harness_select.py`
  resolves it to an absolute path only at install time (Copilot has no run-time plugin-root
  variable). No absolute path lives inside `copilot/.github/`.
- The Claude-side export already qualifies for aesop's lookup: this repo's TOP-LEVEL
  `skills/route` and `skills/fable-check` match the `skills/<name>` form directly, which is the
  existing registry export documented in `docs/AESOP-INTEGRATION.md`.

## The divergence to reconcile

Two coupled questions, stated precisely.

**Extension.** As of `aesop@5506617` the copilot emitter writes `<name>.md`; Copilot CLI's
documented form is `<name>.agent.md`. This repo pinned `.agent.md` on purpose (recorded in the
copilot-harness kit, PLAN.md D2), because it is the CLI-documented form and GitHub's config
reference accepts it. **This repo's position: `.agent.md` should win.** The emitter — and any
lookup path that has to find these agents — should follow the CLI-documented extension, not the
other way around. "Fixing" the bundle back to `.md` to match the current emitter would be drift
against a deliberate decision.

**Location.** aesop's `importPrimitive` resolves agents at `agents/<name>.md` or
`registry/agents/<name>.md` and skills at `skills/<name>` (or the `registry/` and `skills/*/`
variants) relative to a source root, as of `aesop@5506617`. This repo's Copilot primitives do
NOT sit at any of those roots: its agents live at `copilot/.github/agents/*.agent.md` (wrong
root AND wrong extension for the lookup) and its skills at
`copilot/.github/skills/<name>/SKILL.md` (wrong root). So the Copilot bundle is currently
invisible to `importPrimitive`, even though the top-level Claude-side `skills/route` and
`skills/fable-check` already resolve. The reconciliation has to answer both the extension and
the location question together.

## Registry exposure — the options

**Option A — a registry-shaped mirror in THIS repo.** Generate a top-level tree the lookup
already understands (e.g. an `agents/`-style directory and a `skills/<name>` layout matching
`importPrimitive` from `aesop@5506617`), mirroring the Copilot primitives out of
`copilot/.github/`.
- Pros: zero aesop change; the lookup resolves the mirror as-is.
- Cons: it duplicates bundle content, so it needs a sync mechanism and becomes a second source
  of truth this repo's invariants dislike (`copilot/aesop.yaml` is meant to be the one source
  of truth). It also still fights the extension question — a mirror shaped for `agents/<name>.md`
  reintroduces `.md`, contradicting the `.agent.md` decision above.

**Option B — an aesop-side change (recommended).** Teach the copilot emitter to emit
`.agent.md`, and/or teach the lookup to accept configurable source roots plus the `.agent.md`
form, so a consumer can point aesop at `copilot/.github/` and have primitives resolve there with
the CLI-documented extension.
- Pros: fixes the extension and the location for every consumer at the root, with no duplicated
  content in this repo and no second source of truth. It is the reconciliation the copilot-harness
  kit deferred to aesop's repo in the first place.
- Cons: it touches LOCKED-adjacent code, so it needs aesop's approval flow, doc-first
  harness-matrix updates, and new golden fixtures for the copilot emitter.

**Option C — a hybrid (fallback).** A minimal, manifest-declared source-root mapping: let
`aesop.yaml` declare where a harness's primitives live (e.g. a bundle sub-root and an agent
extension), so aesop resolves them without a full mirror and without a broad emitter rewrite.
- Pros: smaller aesop surface than B; keeps `copilot/aesop.yaml` authoritative.
- Cons: still an aesop-side schema-adjacent change (the manifest gains a declaration), so it
  still routes through the LOCKED-schema approval flow and golden fixtures.

**Recommendation: B, with C as the fallback.** B solves both halves at the root and leaves this
repo with a single source of truth; if the emitter rewrite proves too large for one aesop phase,
C narrows the change to a manifest-declared mapping while preserving the same guarantees.
Option A is last-resort only — it violates this repo's single-source-of-truth invariant and
re-litigates the extension decision. Crucially, validating ANY of these options requires actual
`aesop compile` runs, which only the aesop-side effort can perform — which is exactly why this
repo built neither half and shipped this proposal instead.

## The compile round-trip, specified

Acceptance criteria for the future aesop-side effort:

1. Register this repo as an aesop registry source (via the `github:` or `path:` form
   documented in `docs/AESOP-INTEGRATION.md`), and resolve its Copilot primitives through
   `importPrimitive` under the chosen option, all against `aesop@5506617`-descended code
   re-verified at HEAD.
2. Run `aesop compile` against `copilot/aesop.yaml` and emit a `.github/` bundle that matches
   this repo's hand-authored `copilot/.github/` closely enough that a documented diff is empty
   or deliberate. Specifically the emitted output must preserve: agents written with the
   `.agent.md` extension; each agent's frontmatter `model:` pin (an illustrative
   `model: <id>` placeholder, tier-validated against `data/pricing.copilot.json`); the
   `{{POLYTROPOS_ROOT}}` placeholder (never resolved to an absolute path at compile
   time); and skills under `skills/<name>/SKILL.md`.
3. Add golden fixtures on the aesop side for the copilot emitter, capturing this bundle's shape
   so future emitter changes are diff-gated by aesop's golden-fixture process.
4. Leave BOTH repos' test suites green afterward. In particular, this repo's
   `tests/test_copilot_bundle.py` remains the harness-side enforcement of manifest ↔ bundle
   consistency; the compiler never becomes a test dependency here, and `aesop compile` is still
   never run from this repo.
5. Record any intentional diff between the emitted bundle and the hand-authored bundle as a
   documented, reviewed decision — not a silent divergence.

## Guardrails the aesop-side effort must honor

On the aesop side, as pinned at `aesop@5506617`:

- `src/types.ts` and the manifest schema are **LOCKED**; any change to them needs explicit
  approval through aesop's own flow.
- The doc-first harness-matrix process governs which harness emits what — update the matrix docs
  before the emitter.
- Emitter output changes are gated by golden fixtures; add or update the copilot emitter's
  golden fixtures alongside any change.

This repo's invariants, which the aesop-side effort must not break:

- The two pricing files are numeric sources of truth that never merge and are never edited by
  tooling work: `data/pricing.json` (Claude side) and `data/pricing.copilot.json` (Copilot
  side). No compile step may rewrite either, and no bundle content may hardcode a value from
  them — the AIC unit itself is data (`billing_unit.usd_per_credit`).
- The Copilot bundle stays under `copilot/.github/` and keeps the `{{POLYTROPOS_ROOT}}`
  placeholder; the placeholder is resolved to an absolute path only by `bin/harness_select.py`
  at install time, never checked in.
- The hand-authored `CLAUDE.md` and the Claude-side `skills/` tree are never aesop-compiled —
  aesop drives the Copilot side only; the top-level `skills/route` and `skills/fable-check`
  remain hand-authored exports, mirrored to `references/` by `bin/sync_pricing_refs.py`, not by
  a compiler.
- Nothing in this repo ever invokes the real `copilot` CLI from tests or verify commands — it
  spends real AI Credits and hits the network — and consistency is proven by unittest, not by
  dispatching the harness.

## Execution: a future architect run inside the aesop repo

This document is the INPUT to a future `/polytropos:architect` run executed **inside the
aesop repo**, through aesop's own phase-gated process (its LOCKED schema, its doc-first harness
matrix, and its golden-fixture flow). That architect run — not this repo — plans and builds the
chosen exposure option, the emitter/lookup reconciliation, and the compile round-trip. Before it
does, every `aesop@5506617` claim above must be re-verified against aesop HEAD at that time,
because the pins here are snapshots. Nothing in this document was executed here: this repo ships
the specification and stops at the boundary.
