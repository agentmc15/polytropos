# PLAN — context-rules

Apply Anthropic's "The new rules of context engineering for Claude 5 generation models"
(July 24 2026, Thariq Shihipar) to two repos: this one (`polytropos`, primary) and
`/path/to/aesop` (secondary, aesop-managed).

autonomy: advisory

Rationale for advisory: the kit edits the live plugin's always-loaded CLAUDE.md and the two
contract-bearing skills. Every task is heavily machine-verified, but a wrong change here alters
runtime behavior for every future session — recommendations get printed, the human decides.
Routing evidence (`python3 bin/routing_scorecard.py --history`, run 2026-07-24): sonnet 99%
first-try over 107 pinned tasks, haiku 100%/19, opus 100%/17, zero escalations — sonnet-default
pins are safe; opus is reserved for the one contract-sensitive skills task.

---

## Goal

Cut the always-loaded context of polytropos by ~80% and stop the regrowth at the source,
with zero loss of safety-critical content; make one surgical progressive-disclosure fix in the
aesop repo through its compiler. "Done" is checkable:

1. `CLAUDE.md` here is ≤ 11,000 bytes (was 54,377), and every one of the 19
   `For \`<kit>\` specifically:` blocks lives verbatim in `.claude/kits/<kit>/GUARDRAILS.md`.
2. A migration `check` proves byte-level content survival (no safety string dropped), and a
   permanent test (`tests/test_guardrails_layout.py`) enforces the layout + pinned safety
   sentinels forever after.
3. `skills/architect/SKILL.md` and `skills/execute/SKILL.md` route future kit guardrails to
   `.claude/kits/<slug>/GUARDRAILS.md` instead of appending to global CLAUDE.md, with the
   shared kit contract intact in both.
4. Full suite green before and after every task: `python3 -m unittest discover -s tests`
   (baseline 2026-07-24: **1017 tests, OK**).
5. In the aesop repo: the compiled instruction block no longer mandates reading `PLAN.md`
   (24 KB) + `docs/01–08` at session start; change made ONLY via `aesop.yaml` →
   `node dist/index.js compile`, and `node dist/index.js sync` reports
   `clean: disk matches the manifest.` (baseline verified clean 2026-07-24); `npm test` green.

## Byte budget (measured 2026-07-24)

| Region | Lines | Bytes |
|---|---|---:|
| CLAUDE.md total | 1–594 | 54,377 |
| Head to keep (title, Invariants, How to run, kit-task preamble) | 1–81 | 10,271 |
| 19 kit blocks to relocate | 82–594 | 44,106 |

Expected final CLAUDE.md: ~10.7 KB (head + pointer paragraph + one contract-line edit).
**Honest deviation from the ~7 KB target:** the remaining floor is the Invariants section —
L18–21 alone are 3,350 bytes of money/CLI/user-data protections that decision #1 requires to
survive VERBATIM. Reaching 7 KB would mean compressing those. Do not. ~10.7 KB is an ~80%
cut and every removed byte is kit-scoped; that satisfies the intent.

Expected savings: ~44 KB (~10–11k tokens) off EVERY session in this repo — CLAUDE.md is
auto-loaded and re-sent across the cache lifecycle. Generator fix prevents the measured
~2.3 KB/kit regrowth (44,106 bytes / 19 kits). Aesop side: session-start mandated reading of
24 KB PLAN.md + 8 docs chapters becomes read-on-demand.

---

## Audit — the six shifts against both repos (verified file:line)

### polytropos

**Shift 3 (upfront → progressive disclosure) — the dominant offense.**
`CLAUDE.md:75-594`: the `## When executing a kit task` section carries 19 kit-scoped fence
blocks (starts at lines 82, 84, 88, 94, 102, 113, 126, 149, 174, 208, 249, 289, 319, 361, 403,
448, 476, 512, 549) — 44,106 bytes, 87% of the file, loaded into every session although ALL 19
kits are complete (`--history`: 19 kits, 104/105 first-try). These are per-kit law that should
load only when that kit runs.

**Shift 1 (rules → judgement) — mostly NOT applicable here, deliberately.** 122
never/always/must/do-not instances, but nearly all protect real money (live `~/.copilot` AI
Credits, live `~/.codex` — CLAUDE.md:20, 21, 289), user data (CLAUDE.md:37-44), or a live
plugin contract (CLAUDE.md:27-33). Per the article, those are exactly the absolutes that stay.
The judgement shift is applied at the GENERATOR instead: architect/SKILL.md gains "prefer
principles that name the signal; absolutes only for money/CLIs/user data".

**The motivating example of why the leak is harmful:** CLAUDE.md:210 says
"`skills/architect/SKILL.md` is NEVER edited (audited byte-unchanged — any diff in it is a
defect)". That line is a KIT-SCOPED constraint of the completed `per-task-dollars` kit (block
starts L208). Stranded in global CLAUDE.md it reads as global law and would wrongly block this
very kit's T5 — and any legitimate future edit — forever. The actual global invariant
(CLAUDE.md:27-33) says only: architect and execute share one kit contract; touch either,
re-check both. Relocation makes the scope explicit again.

**Shift 4 (repetition → instructions live with the tool).** The kit blocks duplicate, at lower
fidelity, what each kit's own PLAN.md out-of-scope fence already says (e.g. compare
CLAUDE.md:82-83 with `.claude/kits/harden-plugin/PLAN.md`) — CLAUDE.md:81 even instructs
reading the kit PLAN.md. Relocation to the kit dir collapses the duplication to one
kit-local surface. Generator source of the leak: `skills/architect/SKILL.md:55` ("Add (or
append to) the target project's `CLAUDE.md` …") — this is the line that must change or the
bloat returns at ~2.3 KB/kit.

**Shift 5 (CLAUDE.md memory → auto-memory).** Audited: the repo already complies. Global
CLAUDE.md holds contracts and gotchas, not durable user facts, and `skills/memory` +
`bin/memory_*.py` already implement the article's model (pull-only, relevance-gated,
budget-capped). Dated capture facts ("observed on Copilot CLI v1.0.68" L103, "pinned
2026-07-18 capture" L490) are historical kit pins that relocate with their blocks. No forced
moves — do not invent memory tasks.

**Shift 2 (examples → interface design) & Shift 6 (specs → code/rubrics).** Applied inside
this kit: the relocation is a scripted interface (`plan|apply|check` subcommands) rather than
19 hand edits, and the "no safety string dropped" claim is code-as-spec — a permanent unittest
with a pinned sentinel table, not prose.

**Deferred to `/doctor` (do NOT hand-do):** rightsizing `skills/execute/SKILL.md` (14,516 B)
and `skills/journal/SKILL.md` (6,822 B) into split reference trees. The article says
`claude doctor` rightsizes skills and CLAUDE.md automatically; after this kit lands, run
`/doctor` and take its recommendations rather than hand-splitting. This kit's only skill edits
are the two surgical generator changes (T5).

### aesop

**Already compliant where it looked guilty.** The instruction text duplicated across
`CLAUDE.md`/`AGENTS.md`/`.github/copilot-instructions.md`/`.codex/`/`.cursor/rules/*` is
COMPILED output from one source (`aesop.yaml` → `aesop compile`; every file fenced
`<!-- aesop:begin v1 sha256:… -->`). Shift 4's "delete all but one copy" is satisfied by
design — each harness loads only its own file. No action.

**The one real offender — shift 3:** `aesop.yaml:50` compiles to `AGENTS.md:161-162`
("Read `PLAN.md` first, then `docs/01–08`"), mandating a 24 KB historical build plan plus
eight docs chapters as session-start reading for a project whose build is complete
(v0.1.0 shipped; `tasks/todo.md` shows the last phase + security audit closed 2026-06-11,
54 tests green). Fix: rewrite that block to point-at-need (roadmap for status, read only the
chapter your change touches) — via `aesop.yaml` only (T6).

**Out of reach, on purpose:** the AGENTS.md doctrine absolutes (e.g. AGENTS.md:76 "Never mark
a task complete", the Safety block AGENTS.md:116-132) come from the builtin template
(`builtin:AGENTS.template` — aesop source + golden fixtures under `fixtures/compile/*/expected/`
are the compiler's contract). They are (a) mostly safety/verification, hence load-bearing, and
(b) product-level: changing the template changes every aesop user's output and the goldens.
Recorded as a product suggestion, not a task. `GUARDRAILS.md` (1,847 B) is fenced
(aesop:begin L1 / aesop:end L39) — hand-edits forbidden; content is lean safety tiers, keep.
`PLAN.md` (24 KB) is NOT auto-loaded once T6 lands; leave the file alone. `.claude/skills/*`
(1.2–1.4 KB each) already lean — no action.

---

## Constraints

- **Safety rails survive VERBATIM.** Every relocated block is byte-identical to its CLAUDE.md
  original (below the pinned two-line provenance header). No rewording of anything protecting
  money, live CLIs, or user data — anywhere, in either repo.
- **Python is stdlib-only** (no pip/pytest). Verify commands use
  `python3 -m unittest discover -s tests [-p '<file>.py']` — the dotted-module form is broken
  on this machine.
- **The plugin is LIVE.** Skill edits are BODY-only; YAML frontmatter of every skill stays
  byte-identical. The architect/execute shared kit contract (CLAUDE.md:27-33) must survive in
  BOTH files: layout, task fields (`id`,`title`,`status`,`model`, brief, acceptance, verify),
  status vocabulary exactly `pending | in-progress | done | blocked`, phase headings,
  `depends:`/`independent:`, model-field-overrides-frontmatter.
- **Aesop-managed files are read-only to hands.** In `/path/to/aesop`,
  `CLAUDE.md`, `AGENTS.md`, `GUARDRAILS.md`, `.github/`, `.codex/`, `.cursor/`, `.vscode/`,
  `.claude/` are compiled output. The ONLY edit surface is `aesop.yaml`; then
  `node dist/index.js compile`; then `node dist/index.js sync` must print
  `clean: disk matches the manifest.`
- **Never invoke the real `copilot`/`codex`/`claude` CLI** from any task, test, or verify
  command. Never read/write `~/.claude`, `~/.copilot`, `~/.codex`. Do not re-install the plugin.
- **No commit, no push, in either repo.**

## OUT OF SCOPE (executors: touching these is a defect, stop and report)

- Deleting or rewording any money/CLI/user-data rule (relocation is the only sanctioned move).
- Compressing or rewriting CLAUDE.md L7-45 Invariants or L46-74 How-to-run beyond T3's two
  pinned edits.
- Splitting/rewriting any skill other than the two T5 surgical edits (defer to `/doctor`).
- New memory facts, memory-engine changes, pricing-file changes, README/docs changes.
- Hand-editing any aesop-fenced file; `aesop init`; `aesop eject`; npm installs; registry
  updates; touching `src/`, `schemas/`, `fixtures/` in aesop.
- Editing the 19 completed kits' PLAN/TASKS/NOTES files (writing their new GUARDRAILS.md is
  the one sanctioned addition to those dirs).
- `~/.claude/` and anything outside the two named repos.

---

## Architecture & key decisions (each with rationale)

**D1 — One scripted relocation, not 19 hand edits.** A kit-local migration script
(`.claude/kits/context-rules/split_guardrails.py`) with `plan | apply | check` subcommands
does the whole split. Rationale: 19 sequential Edit-tool passes over one 54 KB file is a
merge-conflict and partial-failure trap, and "verbatim survival" is unprovable by eyeball. A
script is the article's shift-2 move — invest in the interface: `plan` previews boundaries,
`apply` is one atomic pass with a backup, `check` mechanically proves zero loss and is
re-runnable. Boundaries are detected by regex (`^  For \`([a-z0-9-]+)\` specifically:`), not
hardcoded line numbers, so the script is robust to drift between kit-build time and run time.

**D2 — Verbatim blocks + pinned provenance header.** Each `GUARDRAILS.md` = two-line header
(what it is, where it came from, its scope) + the original block bytes untouched (original
two-space indentation included). Rationale: decision #1 ("relocate, don't delete; safety rails
verbatim") and provability — `check` can assert exact substring containment against the backup.
Scope line in the header is what fixes the L210 class of bug: the file itself says it binds
only this kit's tasks.

**D3 — The slim CLAUDE.md keeps L1-81 unchanged plus one pointer paragraph.** No compression
of Invariants or the command cheatsheet in the same pass as the mechanical split. Rationale:
one mechanical, checkable change per task; the ~7 KB stretch target is refused (see Byte
budget) because its cost would be reworded money/data rules.

**D4 — A permanent layout+sentinel test is the "no measurable loss" eval.** 
`tests/test_guardrails_layout.py` asserts: every kit dir has a non-trivial GUARDRAILS.md; no
`For \`<kit>\` specifically:` block ever reappears in CLAUDE.md; CLAUDE.md stays under a
16,000-byte tripwire ceiling; and a pinned table of 19 kit-scoped + 9 global safety sentinel
strings each still exists in its required file. Rationale: the article's evidence standard was
"no measurable loss on evals" — this is the checkable analogue, and it keeps failing loudly if
anyone ever deletes a guardrail or re-bloats CLAUDE.md. The suite (1017 tests) green
before/after every task is the behavioral-regression backstop.

**D5 — Generator fix is one task editing BOTH skills.** architect §Harness-guardrails now
writes `.claude/kits/<slug>/GUARDRAILS.md`; execute Setup step 2 reads it. Done as a single
opus-pinned task because CLAUDE.md:27-33 makes the two files one contract — split tasks could
land one side and leave the contract torn. Opus because the edit must thread the needle of
changing layout wording without disturbing any other pinned contract element in two dense
files. The kit-layout contract line in CLAUDE.md itself is updated in T3 to match.

**D6 — GUARDRAILS.md becomes a standard kit file: architect-owned, execute-read, optional on
read.** Execute treats a missing file as "no kit fences" (old kits mid-migration, third-party
kits). Rationale: backward compatible; the permanent test is what makes it required going
forward in THIS repo.

**D7 — Aesop change rides the compiler, minimal by design.** One `aesop.yaml` block rewrite,
then compile + sync-clean + `npm test`. Rationale: sync was verified clean before this kit
(2026-07-24), so any post-compile drift is caused by us and the check is meaningful; everything
else in that repo is either already-compliant, template-owned (product-level), or not
auto-loaded.

**D8 — This kit practices what it preaches.** Its own fences live in
`.claude/kits/context-rules/GUARDRAILS.md`, NOT appended to global CLAUDE.md.

---

## Risks & tripwires

- **R1 — Block extraction mis-splits (regex catches a stray line).** Tripwire: `plan` must
  report exactly 19 blocks with the pinned slug sequence and byte total 44,106 (sum of blocks)
  before `apply` is allowed; `check` must pass after. On mismatch: STOP, report, change
  nothing. Recovery from a bad `apply`: `git checkout -- CLAUDE.md` + delete the generated
  `GUARDRAILS.md` files (backup also at `.claude/kits/context-rules/CLAUDE.md.orig`).
- **R2 — A future session reads a relocated fence as global again.** Mitigated by D2's scope
  header and the CLAUDE.md pointer paragraph naming the load rule.
- **R3 — Skill edit tears the kit contract or frontmatter.** Tripwire: T5 verify greps prove
  frontmatter untouched (`git diff` over `skills/` shows no `name:`/`description:` line
  changes) and every pinned contract element still present in both files. Reviewer checks the
  contract list item-by-item at phase end.
- **R4 — `aesop compile` rewrites more than the instruction block** (e.g. registry drift since
  last compile). Tripwire: `git -C <aesop> diff --name-only` after compile may list only
  instruction-derived files (AGENTS.md, CLAUDE.md, GUARDRAILS.md, `.github/copilot-instructions.md`,
  `.codex/`, `.cursor/`, `.vscode/`, `.claude/` outputs) — anything under `src/`, `schemas/`,
  `fixtures/`, `dist/`, `registry/` changing means STOP, `git -C <aesop> checkout -- .`, report.
- **R5 — Suite red after any task.** Never proceed on red; retry once with the failure output,
  then mark blocked. The baseline is 1017 OK — any drop is caused by the task at hand.
- **R6 — Live plugin skew mid-kit** (CLAUDE.md slimmed while skills still say "append to
  CLAUDE.md"). Accepted for the minutes between T2 and T5 within one run; the kit is designed
  to complete in a single execute pass — do not pause the run between Phase 1 and Phase 3.

## Verification story (the whole kit)

1. **Before/after suite:** `python3 -m unittest discover -s tests` green at every task
   boundary (baseline 1017 OK).
2. **Byte metric:** `wc -c CLAUDE.md` captured in T2's verify (≤ 11,000) and enforced forever
   by the test's 16,000 tripwire ceiling.
3. **Content-survival proof:** `split_guardrails.py check` — every original block byte-for-byte
   present in its kit's GUARDRAILS.md, slim head byte-identical to the original L1-81 (strict
   mode), pointer paragraph exact.
4. **Reach-the-executor proof:** execute SKILL.md reads kit GUARDRAILS.md at Setup (T5), and
   `tests/test_guardrails_layout.py` asserts every kit has one with its safety sentinel intact.
5. **Aesop:** `node dist/index.js sync` prints `clean: disk matches the manifest.` and
   `npm test` green, from the aesop root.
6. **Overall done check:** run the five Goal items top to bottom.
