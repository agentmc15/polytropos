# polytropos × aesop integration

How to consume this plugin from [aesop](https://github.com/agentmc15/aesop) — the user's
harness-portable "environment compiler" — and a proposal for the aesop-side follow-ups that
would make the fit tighter. This is both a user guide (sections 1–4) and a proposal document
(section 5). Companion background: [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md).

> **All aesop behavior described here is pinned to aesop commit `5506617`** (full:
> `55066175a5268887acad39bc859584d13fab09db`) and was verified at that commit. A newer aesop
> checkout may resolve paths, vendor, or default differently — treat every "as of `5506617`"
> claim as a snapshot, not a guarantee, and do not report upstream drift as a bug here.
>
> This document never states a current price as fact. Prices live in `data/pricing.json`; where a
> number would help, it shows the command that computes it or labels the output as an example.

---

## Two layers, one boundary

The two systems are complementary layers that meet at a one-directional boundary.

**aesop is the harness-portable environment compiler.** One `aesop.yaml` manifest compiles into
native agent config for Claude Code, Codex, Copilot, Cursor, Antigravity, and VS Code. It is
deliberately **price-agnostic and model-version-agnostic**: model tiers are abstract
(`strong | mid | cheap`), pathway profiles are an abstract cost/accuracy dial, and its goal loops
stop on abstract `budget_usd` (one of three hard stops). aesop never names a concrete model rate.

**polytropos is the Claude-concrete pricing/routing layer.** It carries concrete model ids,
live per-token rates in `data/pricing.json` (the single hand-edited source of truth), task-size
cost math, and the Fable architect/execute posture (plan once on the frontier model, execute on
cheaper ones). It answers the questions aesop deliberately leaves open: *which* model is `strong`
today, and *how many dollars* a loop tick costs.

**The boundary runs one way: aesop consumes this repo; nothing here imports aesop.** The bridge
script emits copy-paste numbers, the portable skills vendor into an aesop project, and the
architect/execute skills know how to behave inside an aesop-managed target — but no code in this
repo calls, requires, or version-couples to aesop.

| Concern | aesop | polytropos |
|---|---|---|
| Job | compile one manifest → many harnesses | route/price Claude work concretely |
| Model identity | abstract tiers (`strong/mid/cheap`) | concrete ids + live rates in `data/pricing.json` |
| Cost | abstract `budget_usd` stop | task-size dollar math, per-tick estimates |
| Dependency direction | consumes this repo | imports nothing from aesop |

## Consume this repo as an aesop registry

This repo's `skills/<name>/SKILL.md` layout already matches aesop's registry lookup. As of
`5506617`, aesop's `importPrimitive` (`src/federation.ts`) resolves a skill at
`registry/skills/<name>`, `skills/<name>`, or `skills/*/<name>` — so `skills/route/` and
`skills/fable-check/` qualify directly through the `skills/<name>` form, with no restructuring.

Register the repo as a source in `aesop.yaml`:

```yaml
registries:
  - github:agentmc15/polytropos
  # For local development against a checkout on this machine, use the path: variant instead:
  # - path:/path/to/polytropos
```

Then pull in the two portable skills:

```bash
aesop add skill route --from polytropos
aesop add skill fable-check --from polytropos
```

**What vendoring does (as of `5506617`).** `aesop add skill` copies the *whole skill directory*
into the consumer's `.aesop/vendor/…`, with the upstream SHA pinned in the lockfile. Because it
vendors the entire directory, `skills/<name>/references/pricing.json` — the machine-written
mirror of `data/pricing.json` — **rides along automatically**, so the vendored `route` and
`fable-check` are self-contained: they resolve their pricing snapshot from `references/` without
needing this repo's root `data/pricing.json` (see the third resolution step inside each skill).

**Refresh flow.** Run `aesop update` to fetch upstream changes, review the diff, then
`aesop update --apply` to accept. The vendored pricing snapshot changes only when this repo
re-runs `bin/sync_pricing_refs.py` (which rewrites the mirrors from `data/pricing.json`) **and**
the consumer updates — so a stale snapshot is a visible, opt-in state, never a silent one.

**Export surface.** Only the two portable skills are meant to be consumed as a registry; the rest
are plugin-only because they bind to Claude Code internals or local paths:

| Skill | Exported? | Why |
|---|---|---|
| `route` | yes | self-contained after vendoring; pricing snapshot rides along in `references/` |
| `fable-check` | yes | portable judgment + the same pricing snapshot; no local-path deps |
| `cost-report` | plugin-only | depends on `bin/cost_report.py` and `~/.claude` transcript paths |
| `setup` | plugin-only | wires the statusline into `~/.claude/settings.json` |
| `architect` | plugin-only | depends on Claude Code's Agent-tool `model` parameter and this plugin's kit contract |
| `execute` | plugin-only | same kit contract; orchestrates model-pinned subagents |

Note: on this machine the plugin is already installed at user scope in Claude Code, so the
registry path matters mainly for **other harnesses** (Codex, Cursor, Copilot, …) and for **other
people or teams** who want `route`/`fable-check` without installing the full plugin.

## Feed aesop's dials with real numbers

`bin/aesop_bridge.py` turns `data/pricing.json` into the concrete numbers aesop's abstract dials
need. It is copy-paste output, not a runtime dependency — nothing it prints imports aesop, and it
hardcodes no price or model id. Three recipes:

```bash
# 1. tiers — which concrete model is each aesop tier right now?
#    Use it to pin models in aesop profiles or agent frontmatter.
python3 bin/aesop_bridge.py tiers --json
```

Example output (labeled example — run the command for current values):

```json
{ "frontier": "claude-fable-5", "strong": "claude-opus-4-8",
  "mid": "claude-sonnet-5", "cheap": "claude-haiku-4-5" }
```

```bash
# 2. est-tick — estimated cost of one agent-loop iteration, for a goal recipe / the Ralph runner.
#    PROFILE is a task-size key (XS S M L XL); MODEL_ID comes from `tiers`.
python3 bin/aesop_bridge.py est-tick M claude-opus-4-8      # add --json for a machine map

# 3. check-budget — how many iterations a profile's budget_usd actually buys (runway sanity check).
python3 bin/aesop_bridge.py check-budget 25 M claude-opus-4-8
```

`est-tick` exists because aesop's Ralph-style loop runner falls back to a **flat per-tick cost
estimate — `$0.25` as of `5506617`** — whenever the agent CLI it drives emits no cost JSON. That
constant is an aesop-side default at the pinned commit, not a live figure from this repo; `est-tick`
gives you a Claude-concrete number to replace it with. (On a subscription, both `est-tick` and
`check-budget` print a reminder that the figure is API-equivalent burn, not dollars.)

Paste the computed numbers into an aesop goal recipe — the values below are **placeholders you
compute at your desk**, not durable constants:

```yaml
loops:
  build-feature:
    goal: "…"
    stops:
      budget_usd: 25.00                 # your chosen cap
      max_iterations: 42                # ← from `check-budget 25 M <model>` (iterations)
    est_cost_per_iteration_usd: 0.58    # ← from `est-tick M <model>` (recompute on price change)
```

**Rule:** every number here is computed from `data/pricing.json` at run time. After any
`data/pricing.json` update (and its `bin/sync_pricing_refs.py` mirror sync), **recompute** —
never treat a pasted value as durable. Field names above are illustrative; match them to your
aesop version's schema.

## Kits in aesop-managed projects

When `/polytropos:architect` or `/polytropos:execute` operates on a project that
aesop already manages, the compiled files must not be hand-edited. The Phase-2 rules baked into
the skills:

- **Detection.** A target is aesop-managed iff it has an `aesop.yaml` at its root **or** an
  `<!-- aesop:begin` fence in its `CLAUDE.md`/`AGENTS.md`.
- **Compiled files are read-only.** Fenced/compiled files get overwritten by `aesop compile` and
  flagged by `aesop sync` — never hand-edit them.
- **Guardrails go through aesop.** Put any guardrail change into `aesop.yaml` under
  `primitives.instructions.blocks`, then run `aesop compile`.
- **Kit dirs and kit-prefixed agents are safe.** As of `5506617`, aesop tracks only files it
  emits (its computed outputs plus lock-tracked files), so `.claude/kits/…` and kit-prefixed
  agent files are invisible to `aesop sync` and safe to write directly. **Never reuse the name of
  an agent listed in the manifest's `primitives.agents`** — `aesop compile` would overwrite it.

The operative text lives in [`skills/architect/SKILL.md`](../skills/architect/SKILL.md) (the
"Aesop-managed target?" paragraph) and [`skills/execute/SKILL.md`](../skills/execute/SKILL.md)
(setup step for aesop-managed targets).

## Proposed aesop-side follow-ups (live in the aesop repo, not here)

These are improvements to make on the **aesop side**, through aesop's own phase-gated build
process — *not* changes to this repo, and not prerequisites (the integration above works today
with zero aesop changes). They are listed here as a starting point.

1. **Extend the Claude model maps for the Claude 5 family.** The claude-code emitter's `MODEL_MAP`
   and federation's `CLAUDE_MODEL_MAP` map opus/sonnet/haiku ↔ strong/mid/cheap as of `5506617`;
   they should cover the current Claude 5 lineup, including whether Fable warrants a new
   `frontier` tier above `strong`. Note: aesop's `src/types.ts`/schema are **LOCKED** and any tier
   addition needs explicit approval there.
2. **Let profiles/manifest pin concrete model ids per tier.** Allow a profile or the manifest to
   say `strong` means a specific model id explicitly, so a project can lock the exact model rather
   than inheriting whatever the tier default resolves to.
3. **Calibrate the Ralph runner's default tick cost.** Replace the flat `estCostPerIterationUsd`
   constant with a value sourced from `aesop_bridge.py est-tick`, so runway math tracks real
   Claude rates instead of a fixed guess.
4. **Add a `doctor` runway check.** Compare a goal's `budget_usd` against the estimated tick cost
   and warn when the runway is short — mirroring `check-budget`, so misconfigured budgets surface
   before a loop starts.
5. **List polytropos in `registry/plugins/`.** Add this repo as a worked claude-plugin
   example, documenting the `route`/`fable-check` export surface for other consumers.

These proposals are the natural input to running **`/polytropos:architect` in the aesop
repo** as a separate kit — planned and built there, under aesop's own process, never from this
one.
