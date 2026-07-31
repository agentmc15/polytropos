# PLAN — copilot-skills-parity

Match the Claude Code plugin experience in GitHub Copilot CLI: the plugin's user-invocable
slash-command skills (`/polytropos:route`, `:architect`, `:execute`, …) get Copilot
skill twins invocable as `/route`, `/architect`, `/execute`, … . The capability layer already
exists on the Copilot side as ten custom AGENTS (`copilot/.github/agents/*.agent.md`); what is
missing is the `/name`-invocable SKILL surface — today `lessons-loop` is the lone Copilot
skill. The Codex bundle already did exactly this parity add (`codex/skills/<name>/SKILL.md`,
7 skills) — this kit mirrors that discipline on the Copilot side.

autonomy: advisory

## Goal

Eight new Copilot skills land under `copilot/.github/skills/<name>/SKILL.md` — `route`,
`usage`, `journal`, `frontier-check`, `escalate`, `effort`, `architect`, `execute` — each a
self-contained `/name`-invocable instruction surface that shells to the repo's engines,
carries the established honesty rails, and points at the same-named custom agent as the
persona alternative. Each lands atomically with its `copilot/aesop.yaml` `primitives.skills`
entry and its additive `tests/test_copilot_bundle.py` seam. A parity-map doc shows the user
the matched experience explicitly.

**Done looks like:**

1. `copilot/.github/skills/` contains exactly nine skill dirs (`lessons-loop` + the eight
   new), each with a SKILL.md whose frontmatter is `name` + `description` ONLY (no `model:`
   line, no unquoted `: ` in any frontmatter value), and `copilot/aesop.yaml`
   `primitives.skills` lists exactly those nine names (set-equality test green).
2. Every new skill body: shells to the correct engine(s) via `{{POLYTROPOS_ROOT}}`,
   quotes only real argparse flags, derives vocabularies/numbers at run time (never
   enumerates the effort ladder, never hardcodes a pricing-key model id), keeps the
   AIC-are-real-money framing, and closes with the same-named-agent pointer plus the
   not-installed placeholder paragraph.
3. The `effort` skill teaches the interactive `/model` picker only and says "unconfirmed"
   about headless control; `grep -rn -e '--effort' -e 'model_reasoning_effort' copilot/`
   stays empty. The `execute` skill teaches driving `bin/copilot_execute.py`
   (status/run/review) + `--agent` dispatches and states plainly what Copilot does NOT have
   (Claude Code's parallel Agent-tool fan-out / warm SendMessage clusters).
4. `tests/test_copilot_bundle.py` gains the generic skill sweeps (frontmatter discipline,
   YAML-colon safety over skills, no-model-id-in-skill-bodies) plus one contract class per
   new skill; every pre-existing class/method/constant byte-intact;
   `python3 -m unittest discover -s tests -v` fully green.
5. `bin/harness_select.py` is byte-untouched — its `install_copilot` already materializes
   every file under `copilot/.github/skills/` into `<home>/skills/` with placeholder
   resolution (verified in-tree; `InstallCopilot*` tests already cover it).
6. `docs/COPILOT-PARITY.md` maps every Claude slash command to its Copilot equivalent
   (skill `/name` and/or `--agent name`), including install/reload steps and the statusline
   note. One pinned sentence lands in `copilot/aesop.yaml`'s instructions block AND verbatim
   in `copilot/.github/copilot-instructions.md`.
7. `git diff --quiet -- skills codex bin data .claude-plugin README.md copilot/.github/agents copilot/.github/skills/lessons-loop` exits 0.

## Ground truth (researched 2026-07-18 from GitHub's official docs — pinned; do NOT
re-research, executors have no network)

- **Copilot CLI agent skills are near-twins of Claude Code skills.** A skill is a directory
  containing `SKILL.md` with YAML frontmatter — `name` (required; lowercase, hyphens) and
  `description` (required; what it does AND when Copilot should use it) — plus a markdown
  body of instructions. Additional files in the skill dir are auto-discovered when invoked.
- **Slash invocation EXISTS for skills**: the user types the skill name preceded by a
  forward slash in the prompt (e.g. `/route pick me a model`). Copilot ALSO auto-loads a
  skill when the prompt matches its description. `/skills` lists/manages skills;
  `/skills reload` picks up changes in-session; `/skills info <name>` shows one.
- **Skill locations**: personal/global = `~/.copilot/skills/<name>/SKILL.md` (also
  `~/.agents/skills`); project = `.github/skills`, `.claude/skills`, or `.agents/skills`.
  This repo's bundle ships `copilot/.github/skills/` and installs globally via
  `bin/harness_select.py` — nothing lands in a repo-root `.claude/skills`.
- **True custom slash COMMANDS (VS Code-style `.prompt.md`) are NOT supported in Copilot
  CLI** (open feature requests github/copilot-cli #618, #1113). The emerging "extensions"
  SDK with custom slash commands is a separate surface — OUT OF SCOPE; invent no extension
  code. The honest mapping for "slash commands" is skill `/name` invocation.
- **Agents and skills COEXIST**: an agent (`~/.copilot/agents/*.agent.md`, via the `/agent`
  picker or `copilot --agent <name> -p "..."`) is a persona/config Copilot switches into,
  with a frontmatter `model:` pin; a skill is injectable instructions invocable via `/name`
  on the CURRENT session model. The user's Copilot CLI is v1.0.71; the statusline is already
  wired (`bin/copilot_statusline.py` via settings.json `statusLine`).

**Repo mechanics (verified in-tree).** `bin/harness_select.py` `install_copilot` copies
every file under `copilot/.github/skills/` (recursive rglob) to `<home>/skills/<same rel
path>` with `{{POLYTROPOS_ROOT}}` resolved — new skill dirs install with ZERO
installer changes; a missing/empty skills dir is tolerated, so no test there needs touching.
`tests/test_copilot_bundle.py`'s `ManifestSkillsMatchBundleTests` enforces manifest
`primitives.skills` == skill-dir names (set equality, each with a SKILL.md);
`_iter_bundle_files()` rglobs ALL of `copilot/.github/`, so the absolute-path and
harness-separation sweeps cover new skill files automatically; `FrontmatterYamlSafetyTests`
scans AGENT frontmatter only (skills need their own additive twin); `_frontmatter()` splits
on `---` and takes parts[1], so a `---` horizontal rule in a body is harmless. The manifest
parser is line-oriented — `- <name>` entries must match the existing `- lessons-loop`
indentation exactly. `bin/copilot_execute.py`'s REAL argparse surface (quote no other
flags): `status --kit [--json]`; `run --kit [--task] [--agent] [--copilot-bin]
[--max-escalations] [--extra-arg] [--dry-run]`; `review --kit --phase [--copilot-bin]
[--extra-arg] [--dry-run]`. `bin/copilot_pricing.py` subcommands: `models`, `est`, `runway`,
`knobs`. `bin/copilot_usage.py`: `--days`, `--top`, `--copilot-home`, `--session-dir`.
`bin/journal_collect.py --print` / `bin/journal_summarize.py --date <d> --dry-run` are the
journal surface a non-Claude harness may teach (in-session two-pass only — headless
summarize dispatches the Claude CLI and is never recommended from a Copilot file).

## Decisions

- **D1 — The roster is eight skills: the seven Codex-parity capabilities plus `execute`.**
  `route`, `usage`, `journal`, `frontier-check`, `escalate`, `effort`, `architect` mirror
  the codex/skills precedent one-for-one (same names as the Copilot agents — `usage` is the
  Copilot twin of Claude's `/cost-report`, `frontier-check` of `/fable-check`; the
  harness-parity naming rule stands — never `fable*` or `cost-report` on a non-Claude
  harness). `execute` is Copilot-only-extra relative to Codex because Copilot has the full
  kit driver (`bin/copilot_execute.py`) AND the architect/implementer/verifier/reviewer
  agent set — the Claude `/execute` experience is honestly portable here. NOT in the
  roster: `setup` (the statusline is already wired for this user; reinstall steps live in
  the parity doc — a skill would duplicate `harness_select.py`), `memory` (cross-harness
  memory parity is a FUTURE kit per the memory-skill fence), `lessons-loop` (already
  exists, untouched).
- **D2 — The skill↔agent pattern, decided ONCE for all eight: condensed operative twin +
  agent pointer.** A skill is a SELF-CONTAINED instruction surface (~40–70 lines) carrying
  the operative core of the same-named agent — the engine commands, the honesty rails, the
  decision guidance — so `/name` works inline on the session's current model. It is NEVER a
  bare pointer (that would make `/name` useless as instructions) and NEVER a verbatim copy
  of the 80-line agent body (agents keep the long-form persona). Every skill closes with
  the same two pinned paragraphs: (a) "Same-named agent" — for persona-isolated runs use
  the `/agent` picker or `copilot --agent <name> -p "..."`, which carries that agent's
  `model:` pin (skills have NO pin; frontmatter is `name` + `description` only, per the
  lessons-loop and codex-skill precedent); (b) the not-installed placeholder paragraph
  (`python3 bin/harness_select.py install --harness copilot`). Shared essentials are
  contract-tested on both surfaces so they cannot silently drift.
- **D3 — The `execute` skill is honest about orchestration.** It teaches the real loop:
  `status` to see kit state, `run --kit <dir> [--task <id>]` per task (the driver
  dispatches the kit's pinned model via the implementer agent, verifies, and climbs the
  tier ladder on failure — `--max-escalations` caps it), `review --kit <dir> --phase <n>`
  at phase ends, `--dry-run` to preview any dispatch without spending AI Credits. It states
  plainly what Copilot does NOT have: Claude Code's parallel Agent-tool fan-out and warm
  SendMessage clusters — kit tasks run serially, one `run` invocation at a time, and
  `independent:` markings mean "safe to run in any order", not "run in parallel". Real
  `run` invocations spend real AI Credits — the skill says so.
- **D4 — Similarly honest `architect` skill.** Skills carry no model pin, so the skill says
  the honest thing: planning quality tracks the model driving it — either switch the
  session to the frontier tier first (`/model`; frontier rows from
  `copilot_pricing.py models --json`, never named from memory) or use
  `copilot --agent architect`, whose frontmatter pin carries the frontier model. Kit
  contract (layout `tasks/kits/<slug>/`, task fields, status vocabulary
  `pending | in-progress | done | blocked`, `depends:`/`independent:`) mirrors the agent
  verbatim — the driver parses it.
- **D5 — Placement & install: bundle-only edits, installer byte-untouched.** Skills live at
  `copilot/.github/skills/<name>/SKILL.md` with `{{POLYTROPOS_ROOT}}` placeholders.
  `install_copilot`'s recursive skills copy (verified, tested) installs them to
  `<home>/skills/` — extending `bin/harness_select.py` is NOT needed and it stays
  byte-untouched, as do all bin engines (read-only reuse).
- **D6 — Test seams: generic sweeps once, then one contract class per skill, all additive.**
  T1 lands three generic classes that iterate ALL skill dirs (so later skills are
  auto-swept): `SkillFrontmatterTests` (dir name == `name:`, `description:` present, NO
  `model:` line), `SkillFrontmatterYamlSafetyTests` (the unquoted-`': '` scan, twin of the
  agent-side regression guard — it shipped a real bug once), `SkillNoModelIdTests` (no key
  of `data/pricing.copilot.json` `models` appears in any skill file — ids are derived at
  test time, never literals). Each skill task adds its own `<Name>SkillContractTests`
  mirroring the codex `EffortSkillContractTests` pattern (engine mention, honesty markers,
  no invented flags, placeholder). `ManifestSkillsMatchBundleTests` (set equality) is the
  atomicity tripwire: manifest entry + skill dir + seams land in ONE task, suite green at
  every boundary. `FrontmatterYamlSafetyTests` and every other pre-existing class stay
  byte-intact.
- **D7 — Honesty rails carried into every body (established, must survive).** Effort:
  interactive picker only, the word "unconfirmed" for headless, never `--effort` or
  `model_reasoning_effort` anywhere under `copilot/`, never an enumerated ladder (shell to
  `knobs`). AIC are real money (`billing_unit.usd_per_credit`). Level/model vocabularies
  from `knobs`/pricing at run time. Never invent a CLI flag — every quoted flag is on the
  pinned argparse surfaces above. Journal: in-session `--dry-run` two-pass flow only.
  Frontier-check: tier language, never "fable-check". Skill descriptions (frontmatter) are
  pinned verbatim in the briefs and contain no unquoted `: `.
- **D8 — One pinned instructions sentence + one parity doc.** The sentence (manifest-first:
  `copilot/aesop.yaml` instructions block, then verbatim in
  `copilot/.github/copilot-instructions.md`) tells Copilot the capabilities are also
  `/name`-invocable skills. `docs/COPILOT-PARITY.md` is the user-facing parity map:
  Claude command → Copilot skill/agent, install + `/skills reload` steps, the statusline
  line, and the deferred list. Both doctrine sentences in the instructions file stay
  byte-intact (test-enforced).
- **D9 — Executor pins: sonnet authors, haiku audits, opus reviews.** Routing history
  (17 kits; harness-parity 10/10 first-try, effort-dial 9/9, memory-skill 7/7 — all
  pinned-brief bundle/test authoring on sonnet) shows this exact task shape runs clean on
  sonnet. Every authoring task pins `sonnet`; the final frozen-surface audit is mechanical
  and pins `haiku`; the kit reviewer (opus) runs at phase ends. The per-task escalation
  valve covers surprises.

## OUT-OF-SCOPE fence (do NOT build)

- **No extension-SDK slash commands, no VS Code `.prompt.md` prompt files** — the emerging
  Copilot extensions system is a separate surface; the honest slash story is skill `/name`
  invocation, and that is what ships. Do not invent extension code or an unshipped command
  registry.
- **No `codex/` changes of any kind** and **no Claude-side skill changes** (`skills/` stays
  byte-untouched — `git diff --quiet -- skills` in the audit). No new Copilot AGENTS, no
  edits to the ten existing `*.agent.md` files, no `lessons-loop` edits.
- **No `bin/` edits** — `bin/harness_select.py` included (its skills glob already installs
  the bundle skills; verified). All engines are read-only reuse. No new bin scripts.
- **No edits to any of the three pricing files**, `.claude-plugin/`, `README.md`, or any
  completed kit. No `~/.copilot`/`~/.codex`/`~/.claude` reads or writes; nothing outside
  this repo.
- **NEVER invoke the real `copilot`, `codex`, or `claude` CLI** from any task, test, or
  verify command — real runs spend real AI Credits and hit the network. Command lines
  WRITTEN into skill bodies are runtime instructions the kit never executes. Verify
  commands are unittest discovery and greps only.
- **No invented flags** — no Copilot headless effort surface, no `copilot_execute.py` flag
  beyond the pinned surface, no `/skills`-adjacent subcommand beyond
  `reload`/`info`/listing. No network, no web fetches, no node/`aesop compile`.
- **No memory-skill port, no setup/statusline skill** (deferred — see D1). No commit, no
  push.

## Risks & tripwires

- **Set-equality tripwire**: a manifest `- <name>` without its skill dir (or vice versa)
  turns `ManifestSkillsMatchBundleTests` red — every skill task is atomic; verify at every
  boundary.
- **YAML-colon tripwire (shipped a real bug once)**: an unquoted `: ` inside a frontmatter
  value makes Copilot's YAML loader reject the whole file. Descriptions are pinned verbatim
  and the new `SkillFrontmatterYamlSafetyTests` sweep enforces it forever.
- **Manifest indentation**: `copilot/aesop.yaml` is parsed line-oriented — each `- <name>`
  must match `- lessons-loop`'s exact indentation, or the block parses empty and the
  set-equality test fails confusingly.
- **Accidental model pin in a skill**: skills have NO `model:` line (the session model
  runs them); `SkillFrontmatterTests` enforces it.
- **Model-id leak into a skill body**: `SkillNoModelIdTests` sweeps every skill file
  against the live pricing keys (display names like "Fable 5" in the route agent's body
  are an AGENT-side liberty; skill bodies stay id-free and tier-worded).
- **Vocabulary cross-contamination**: Codex tokens (`model_reasoning_effort`, `--effort`,
  lowercase level words) in a Copilot file — grep-enforced in T3's and T8's verify.
- **Invented-flag relapse**: every flag quoted in a body must be on PLAN.md's pinned
  argparse surfaces — the verifier hand-checks each new body against them.
- **Doctrine-sentence breakage**: T7's instruction edits are pure appends;
  `DoctrineSentenceSyncTests` must stay green.
- **Generic-sweep collateral**: the three generic skill classes also iterate `lessons-loop`
  — it already satisfies them (verified: name matches dir, description present, no model
  line, no `: ` in values, no pricing ids); do not "fix" lessons-loop to make a sweep pass.

## Phases

- **Phase 1 — decision-aid skills**: T1 `route` + the three generic skill sweeps, T2
  `usage` + `journal`, T3 `frontier-check` + `effort`.
- **Phase 2 — workflow skills**: T4 `escalate`, T5 `architect`, T6 `execute`.
- **Phase 3 — closeout**: T7 instructions sentence + `docs/COPILOT-PARITY.md`, T8
  full-suite + frozen-surface audit.

T1→T7 form one strictly serial chain (every task edits `copilot/aesop.yaml` and
`tests/test_copilot_bundle.py`); all are `model: sonnet`, so warm implementer clusters
apply — cap ~4 tasks per warm agent (T1–T4, then T5–T7 fresh). T8 (haiku) is a fresh spawn.

## Deferred (recorded, not built — each with its correctable point)

- Extension-SDK custom slash commands → revisit when github/copilot-cli #618/#1113 ship;
  the parity doc records the gap.
- A `setup`/statusline skill → statusline already wired via settings.json `statusLine`;
  reinstall steps live in `docs/COPILOT-PARITY.md`.
- Cross-harness memory skill port → a future kit (per the memory-skill fence).
- Parallel/warm-cluster orchestration on Copilot → no CLI surface exists; the execute
  skill's honesty paragraph is the record.
