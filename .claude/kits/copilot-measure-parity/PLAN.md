# copilot-measure-parity — port context-weight and bench-routing to the Copilot bundle

## Goal

Close the two genuine parity gaps between the Claude-side skill roster and the Copilot
bundle: `context-weight` and `bench-routing`. Both landed (commit `6164ebc`, #11) after the
copilot-skills-parity kit shipped its roster, and both engines already support
`--harness copilot` — the only missing piece is the surface pair each capability needs on
the Copilot side.

**Done means:** `copilot/.github/skills/context-weight/SKILL.md`,
`copilot/.github/skills/bench-routing/SKILL.md`, `copilot/.github/agents/context-weight.agent.md`,
and `copilot/.github/agents/bench-routing.agent.md` exist and follow the copilot-skills-parity
D2 condensed-twin pattern; `copilot/aesop.yaml` lists both new names in its `skills:` and
`agents:` blocks; `tests/test_copilot_bundle.py` carries per-skill contract classes for both;
the copilot-docs center is rebuilt (its manifest globs `copilot/.github/skills/*/SKILL.md` as
a source, so the freshness check fails until rebuilt); and the FULL test suite is green.

## Constraints and out-of-scope (executors must NOT)

- **Do not touch the engines or data.** `bin/context_weight.py`, `bin/bench_routing.py`,
  `bin/copilot_pricing.py`, `bin/harness_select.py`, `data/benchmarks.aa.json`, and all three
  pricing files are FROZEN for this kit. The engines already do everything the new surfaces
  teach; if a brief seems to require an engine change, the brief is wrong — stop and report.
- **Do not touch the Claude-side skills** (`skills/`), the Codex bundle (`codex/`), or any
  existing Copilot skill/agent file. Codex-side ports are a separate future kit.
- **No memory or setup ports.** `memory` stays a FUTURE kit per the memory-skill fence;
  `setup` stays excluded per copilot-skills-parity D1.
- **Never invoke the real `copilot` CLI** and never read or write the real `~/.copilot` —
  standing repo invariant; tests use repo files only (these are text-contract tests; no
  temp-home fixtures are even needed).
- **Do not commit or push.**

## Architecture & key decisions

- **D1 — The roster grows by exactly two names, each on both surfaces.** Skill + same-named
  agent for `context-weight` and `bench-routing`, mirroring how every other ported capability
  ships. Both names are already harness-neutral (no `fable*`, no `cost-report`), so no rename
  is needed — the copilot-skills-parity naming rule is satisfied by the Claude-side names
  themselves.
- **D2 — The copilot-skills-parity D2 pattern applies unchanged.** A skill is a SELF-CONTAINED
  condensed operative twin (~40–70 lines): frontmatter is `name:` + `description:` ONLY (no
  `model:` — `SkillFrontmatterTests` enforces this), engine commands use the
  `{{POLYTROPOS_ROOT}}` placeholder, and every skill closes with the same two pinned
  paragraphs: (a) **Same-named agent** — persona-isolated runs via the `/agent` picker or
  `copilot --agent <name> -p "<task>"`; (b) **Installed?** — the literal-placeholder check
  pointing at `python3 bin/harness_select.py install --harness copilot` and `/skills reload`.
  The agent file carries the long-form persona plus the `model:` pin. Copy the paragraph
  wording from `copilot/.github/skills/usage/SKILL.md` — drift in those shared paragraphs is
  what the contract tests exist to catch.
- **D3 — Honesty IS the content; fidelity limits are stated, never papered over.**
  - `context-weight`: teaches `session --harness copilot` and `overview --harness copilot` at
    Copilot's honest fidelity — **session-average weight only, no growth curve** (Copilot's
    logs record no per-turn input/cache split), plus `audit` (which sizes
    `copilot-instructions.md` among the resident surfaces) and `demo`. It states plainly that
    `watch` is Claude-only and that `watch copilot` prints an honest refusal — there is no
    live threshold on this harness, so the three levers (prevent / prune / measure) and the
    checkpoint-before-compacting habit are applied on a schedule, not on a threshold.
  - `bench-routing`: teaches `rank` and `roles --harness copilot` (availability derived at run
    time from `data/pricing.copilot.json`; entries matching no dispatchable model are reported
    UNAVAILABLE, never dropped). It is honest about `compare`: the measured-outcome join reads
    this repo's Claude-harness kit ledger and evidences the implementer role only — from the
    Copilot side the benchmark prior stands unchallenged, and the skill says so instead of
    borrowing Claude-side evidence. `usd_per_task` is a ranking ratio, never a bill; the
    Intelligence Index is a general composite (say so before any agentic-role recommendation);
    the dataset is screenshot-transcribed (name the provenance and `cached_date`).
- **D4 — No prefs teaching in either new skill, deliberately.** `bin/bench_routing.py` and
  `bin/context_weight.py` do not consume `prefs/copilot.json`. The prefs paragraphs on
  route/frontier-check/escalate/architect teach a mechanism their engines actually honor;
  adding the same paragraphs here would fake a capability — exactly what the parity verifier
  hunts. If prefs support ever lands in these engines, the paragraphs come with it.
- **D5 — Agent model pins from bundle precedent + routing history.**
  `context-weight.agent.md` pins `claude-haiku-4.5` (read-only reporter — the `usage` and
  `verifier` precedent; haiku's cross-kit first-try rate is 100%).
  `bench-routing.agent.md` pins `claude-sonnet-5` (decision aid — the `route` and
  `frontier-check` precedent). Both ids are live `data/pricing.copilot.json` keys, which
  `ModelPinLiveTests` enforces. Model ids appear ONLY in agent frontmatter — skill text stays
  tier-worded and id-free (`SkillNoModelIdTests` sweeps every skill automatically).
- **D6 — Manifest and bundle move atomically, and every task rebuilds the docs center.**
  `ManifestSkillsMatchBundleTests` / `ManifestAgentsMatchBundleTests` assert set-equality
  between `copilot/aesop.yaml` blocks and the directory contents, so a bundle file and its
  manifest line MUST land in the same task — in either order alone, the full suite is red.
  Likewise `copilot-docs/manifest.json` globs `copilot/.github/skills/*/SKILL.md` as a build
  source, so any task that adds a skill file ends with `python3 bin/copilot_docs.py build`
  (idempotent, deterministic) before running the suite.
- **D7 — Tests extend `tests/test_copilot_bundle.py`; no new test file.** All bundle text
  contracts live in that one file by precedent. The generic sweeps (frontmatter discipline,
  YAML safety, no-model-id, manifest equality, placeholder discipline, harness separation)
  cover the new files automatically the moment they exist; the new work is two per-skill
  contract classes pinning each skill's operative anchors, mirroring the existing
  `UsageSkillContractTests` shape.
- **D8 — The docs-coverage tripwire is updated in lockstep (amended mid-run, 2026-07-25).**
  `tests/test_copilot_docs_content.py` pins `EXPECTED_SKILLS` and `EXPECTED_AGENTS` as
  HARDCODED rosters and asserts a three-way equality: `discover_skills()` output ==
  docs headings == the hardcoded set. The first two legs move on their own (the builder
  regenerates `SKILLS.md`/`AGENTS.md` from discovery), so the hardcoded set is a deliberate
  tripwire that forces a human to acknowledge any roster change. Adding a surface therefore
  REQUIRES adding its name to the corresponding constant — that update IS the acknowledgment
  the tripwire exists to force, not a workaround of it. Do NOT derive these constants from
  the directory: that would delete the tripwire the copilot-docs kit deliberately built.
  The atomic-wiring rule of D6 extends to this file — bundle file, manifest line, and roster
  constant land in the SAME task. (Original scope froze this file; that omission is recorded
  as an architect brief defect in NOTES.md.)
- **D9 — Each new surface ships its authored docs-guide section (amended mid-run,
  2026-07-25).** `copilot-docs/SKILLS.md` and `copilot-docs/AGENTS.md` are NOT generated
  output: each is a hand-authored guide carrying ONE builder-spliced inventory block
  (`<!-- BEGIN GENERATED: skills-inventory -->` / `agents-inventory`), with per-surface
  `## <name>` prose sections below it that the builder never writes (the manifest marks these
  documents `authoring.mode: estimated`, `tier: strong` — authored by a model, not emitted).
  `SkillCoverageTests`/`AgentCoverageTests` assert the H2 headings equal the roster AND that
  every section carries its required subsections, so a new surface without its guide section
  fails the suite. Therefore each surface task authors its own section in alphabetical
  position, in the existing voice: SKILLS.md sections carry **When to use it.** /
  **How to request it.** / **What it does.** / **Safety and cost notes.** / **Same-named
  agent.**; AGENTS.md sections carry **When to use it.** / **How to invoke it.** /
  **What it does.** / **Same-named skill.** The original guardrail claimed all of
  `copilot-docs/` was builder-only; that was factually wrong and is recorded as an architect
  brief defect in NOTES.md.

- **D10 — The resident roster prose is corrected here (amended 2026-07-25, after the final
  review).** `copilot/.github/copilot-instructions.md` and its mirrored `instructions.blocks`
  in `copilot/aesop.yaml` enumerate the pre-parity roster, so shipping the new surfaces without
  touching them leaves a false-by-omission claim on the file loaded into EVERY Copilot call —
  the highest-leverage wrong sentence in the bundle, and the reason a user would never learn
  the new skills exist. The original scope froze that file; this decision narrowly unfreezes
  the two roster sentences (and their mirror) and nothing else in it.
  Constraints that make this safe and cheap:
  - **Mirror discipline.** The two files carry the same prose; edit BOTH so they stay in sync.
    `DoctrineSentenceSyncTests` requires one specific doctrine sentence verbatim in both — do
    not touch that sentence.
  - **Resident-token economy.** This surface is resubmitted on every call, so the edit adds
    names, not descriptions. The `context-weight` skill this kit just shipped teaches "keep
    resident config surfaces lean, but proportionate" — violating that in the same kit that
    ships it would be self-refuting. Net growth should be a handful of words, not a paragraph.

## Risks & tripwires

- **A red suite mid-task that isn't yours:** if `python3 -m unittest discover -s tests` fails
  on a manifest or docs-freshness test while you are mid-edit, the cause is almost certainly
  D6 ordering (bundle file without manifest line, or missing docs rebuild) — fix within the
  task rather than reporting blocked.
- **Fidelity drift:** if a draft sentence promises Copilot a growth curve, a live watch
  threshold, or ledger-backed role evidence, it contradicts the engines — delete the sentence,
  don't soften it. Run the engine commands yourself if unsure what they actually print.
- **Anchor strings are contracts:** T5's test classes grep for exact strings the T1–T4 briefs
  pin. If a string in a brief conflicts with what the engine actually prints, the ENGINE wins —
  stop and report the discrepancy rather than shipping a test that pins a falsehood.
