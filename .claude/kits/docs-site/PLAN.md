# docs-site — robust per-skill documentation across all three harnesses + a generated GitHub Pages manual

autonomy: advisory
budget: max-dispatches=84 max-escalations=4 max-consults=4
roles: test-author docs-editor

## Goal

> Amendment (run 2026-08-29-c45c, executor): counts were re-derived from the live tree — `copilot/goliath` (commit 85cccaa, after this plan was written) makes it 14 + 13 + 12 = 39 skills and 68 generated files. T13 gains `goliath.md`. Nothing else in the plan changed.

Make the documentation for every skill in every harness (14 Claude + 13 Copilot + 12 Codex
= 39 skills) substantially more robust WITHOUT taxing model context, and ship a public,
GitHub-Pages-hosted manual (MkDocs Material) that takes a human from "what is this?" to
running their first skill — with every skill-reference page **generated from the actual
skill files** and a drift test that fails the suite when the site is stale.

"Done" is checkable:

- `python3 -m unittest discover -s tests -v` is green (baseline before this kit:
  2639 tests, OK). **Executor amendment (P4 review, carry-forward 8):** this criterion as
  written is now unmeetable regardless of the kit's work. The live baseline is **2953 tests
  with exactly 10 errors**, all `LedgerJoinTests` in `tests/test_copilot_usage.py` (6) and
  `tests/test_codex_usage.py` (4) — pre-existing calendar rot, not this kit's doing: those
  fixtures hardcode `WHEN = datetime(2026, 7, 26)` and query a 30-day window, so they began
  failing when the clock passed ~2026-08-25. "Green" for this kit means **zero failures and
  no 11th error** — including two new files, `tests/test_docs_build.py` and
  `tests/test_docs_site.py`.
- `python3 bin/docs_build.py check` exits 0 against the committed tree, and exits
  non-zero when any SKILL.md, `docs/*.md`, or fragment is edited without a rebuild
  (provable on a temp copy — see GUARDRAILS.md for the safe recipe).
- Every generated page is committed: 39 per-skill pages under
  `docs-site/skills/{claude,copilot,codex}/`, 3 harness index pages, 1 parity page
  (`docs-site/skills/index.md`), 24 deep-dive mirrors + 1 index under
  `docs-site/deep-dives/` — 68 generated files total, all covered by `mkdocs.yml` nav
  (test-enforced in both directions).
- Every one of the 39 skills has a hand-authored "In practice" fragment under
  `docs-src/fragments/skills/<harness>/<name>.md` carrying the six pinned template
  sections.
- The SKILL.md audit (`.claude/kits/docs-site/AUDIT.md`) exists and its dispositions are
  applied: the seven thin skills addressed, no SKILL.md grown past its budget, zero
  sentinel lines removed (full suite proves it).
- `.github/workflows/docs-site.yml` exists and a local venv smoke build
  (`mkdocs build --strict`) passed — or is honestly recorded as blocked-on-network in
  NOTES.md, never silently skipped.
- README.md and SETUP.md link the published site
  (`https://agentmc15.github.io/polytropos/`); CLAUDE.md stays under its 16000-byte
  tripwire (`tests/test_guardrails_layout.py`).

## Constraints and out-of-scope

- **Do not bloat SKILL.md bodies.** SKILL.md is loaded into model context at runtime
  (this repo ships `context-weight` about exactly this). Depth goes to `references/` or
  the site, per D1 below. No SKILL.md may grow past its D1 budget.
- **Do not remove or reword safety/honesty lines in any skill** — root-proof blocks,
  "read-only" declarations, placeholder-reject lines, "never invent"/"never from memory"
  rules, refusal fallbacks. Dozens of tests pin skill text verbatim
  (`tests/test_codex_bundle.py`, `test_codex_core_skills.py`,
  `test_codex_analysis_skills.py`, `test_codex_memory_skill.py`, `test_codex_docs.py`,
  `test_copilot_bundle.py`, …). Before deleting or rewording ANY existing skill line, run
  `grep -rF '<distinctive phrase>' tests/` — a hit means it is a contract; keep it.
- **`data/pricing.json`, `data/pricing.copilot.json`, `data/pricing.codex.json` are
  untouched**, as are their generated mirrors under `skills/*/references/pricing.json`.
  No price, ratio, plan allowance, model id, or cached date is ever hardcoded into a site
  page, fragment, or the generator — link the data file or show the engine command that
  prints numbers.
- **`bin/` is not restructured.** One new script (`bin/docs_build.py`) is added; nothing
  existing moves or is rewritten.
- **The 58 existing test files must stay green.** Full-suite run before claiming any task
  done (house law).
- **`copilot-docs/` is untouched** — it is a shipped artifact with its own generator
  (`bin/copilot_docs.py`) and AIC accounting. The site links to it; it is never mirrored
  or absorbed.
- **`docs/*.md` sources are never moved, renamed, or absorbed** (D6). The kit only ADDS
  a README/SETUP pointer paragraph; `tests/test_harness_update.py` asserts pricing
  `cached_date` strings appear in README/docs — never remove those.
- **Never invoke the real `claude`/`copilot`/`codex`/`gh` CLI** from any task, test, or
  verify command. The generator and all new tests are stdlib-only, offline, and never
  read a home directory.
- **pip is allowed in exactly one place**: a throwaway venv in a temp/scratch dir for the
  T17 mkdocs smoke build and in CI. Never into system Python, never a dependency of
  `bin/` or `tests/` code (those stay stdlib-only per CLAUDE.md).
- **Do not commit or push** unless the user explicitly asks. Do not touch `~/.claude` or
  anything outside this repo. Do not re-install or refresh any harness.
- Out of scope: deleting or redirecting `docs/guide.html` / `docs/how-it-works.html`
  (left as-is, see D6); translating docs; screenshots/video; a custom theme; analytics;
  a versioned-docs setup (mike); enabling GitHub Pages in repo settings (user action —
  Settings → Pages → Source: "GitHub Actions"; the kit's final report must remind them).

## Architecture & key decisions

### D1 — The three-way content rule (SKILL.md / references / site-only)

Executors apply this rule 39 times; apply it identically. The litmus is: *who needs this
sentence, and when?*

1. **SKILL.md** — only what the model needs to ACT correctly on a typical invocation:
   trigger conditions (the `description`), root/path resolution proofs, the procedure,
   real commands with real flags, output shape, safety rails, honesty labels, and the
   escalation/fallback signal. Test: "would a competent model acting WITHOUT this line do
   the wrong thing on a normal run?" If no — it does not belong here. Budgets: an
   engine-wrapper skill stays ≤ ~900 words of markdown body; an orchestration skill
   (architect, execute, repo-bench) stays at or below its CURRENT length — those three
   are the ceiling and may only shrink. **Executor amendment (P4 review Finding 2):** the
   ~900 figure is unreachable for `claude/context-weight` — AUDIT's own MUST-NOT-MOVE
   sections plus the procedural section account for essentially its whole post-relocate body,
   and the P4 reviewer independently confirmed that even removing the one paragraph that does
   fail the litmus (~105 words of self-referential design history) lands at ~1233, still 37%
   over. Recorded exceptions, all of which SHRANK or held rather than grew:
   `context-weight` 1370 (from 2349), `journal` 950 (from 1079), `graphify` 902 (pre-existing
   `keep`). The binding rule remains that no skill may GROW past its budget. Nothing in the
   repo enforces the ~900 figure by test. **Thin is not deficient**: the thin Codex skills
   (doctor, memory, context-weight, bench-routing, execute) are dense and safety-complete;
   enrichment means adding a missing *acting* fact (a knob, a failure signal, a fallback),
   never prose.
2. **`references/*.md` beside the SKILL.md** — what the model needs OCCASIONALLY, on
   demand: extended schemas, edge-case playbooks, rare-flag catalogs, long worked
   transcripts. Every reference file must be named from its SKILL.md with a one-line
   "read `references/<file>` when X" trigger — an unpointed reference is dead weight.
   Content is MOVED there, never duplicated.
3. **Site-only (`docs-site/` + `docs-src/fragments/`)** — what a HUMAN needs and a model
   never should load: rationale and design history, tutorials, worked walkthroughs,
   when-NOT-to-use narrative, comparisons, install guides, FAQ. Enforced mechanically:
   **no SKILL.md may ever contain the string `docs-site`** (a live-tree test in
   `tests/test_docs_site.py` asserts this), so site content can never leak back into
   model context via a skill pointer.

### D2 — Generator + drift test, mirroring the house pattern

`bin/docs_build.py` (new, stdlib-only) derives every page under the two generator-owned
roots `docs-site/skills/` and `docs-site/deep-dives/` from the actual sources: the 39
SKILL.md files (all three frontmatter shapes), the 24 `docs/*.md` deep-dives, and the
hand-authored fragments under `docs-src/fragments/`. This mirrors
`bin/sync_pricing_refs.py` / `bin/sync_codex_surfaces.py` + their drift tests, not the
marker-splicing style of `bin/copilot_docs.py` (full-page generation is simpler and the
committed page IS the artifact). Contract details are pinned in T1/T4/T5 briefs:
`build`/`check` CLI with `--repo-root`, exit 0/1/2, deterministic byte-stable output (no
wall clock, no randomness, sorted iteration, LF, UTF-8), an introspection-tested ban on
`Path.home`/`subprocess`/`urlopen`, and reuse of `sync_codex_surfaces._frontmatter` via
the importlib sibling-loader idiom. What is derived: page skeletons, provenance lines,
roster/parity tables, transformed SKILL.md bodies (headings demoted one level,
relative links rewritten — both fence-aware), deep-dive mirrors with rewritten links.
What stays hand-authored: fragments (spliced verbatim under pinned headings), all pages
outside the two generated roots, and `mkdocs.yml`.

### D3 — Generated markdown is COMMITTED; HTML is CI-built and never committed

The committed artifact is the generated *markdown* (like every other generated mirror in
this repo); `tests/test_docs_site.py` regenerates expected bytes in-process and compares
against the committed files — so the drift test needs **zero network and zero non-stdlib
dependency**, and a local contributor keeps the whole suite green offline. The rendered
HTML (`site-build/`, gitignored) is produced only by `mkdocs build --strict` — in CI on
every push to main, and optionally locally via a throwaway venv. The MkDocs Material
dependency is declared in exactly one place, `docs-src/requirements.txt`
(`mkdocs-material>=9.5,<10` — a bounded range, not an exact pin, so the workflow doesn't
rot), consumed by both CI and the local venv recipe. Offline substitute for `--strict`'s
link checking: a stdlib test walks every `docs-site/**/*.md` and asserts every relative
link target resolves to an existing file (anchors not validated — stated limitation).

### D4 — Site information architecture

`mkdocs.yml` at the repo root; `docs_dir: docs-site`, `site_dir: site-build`
(gitignored), `site_url: https://agentmc15.github.io/polytropos/`,
`repo_url: https://github.com/agentmc15/polytropos`, Material theme with light/dark
palette toggle. The newcomer funnel is: **Home** (the one idea, in one screen) →
**Getting started** (pick your harness: Claude Code plugin / Copilot CLI bundle / Codex
CLI bundle — install + first `/route`) → **Concepts** (billing modes, the one hard
constraint, architect→execute→measure, effort dials) → **Skills reference** (generated)
→ **Workflows** (task-oriented cookbook) → **Deep dives** (generated mirrors of
`docs/*.md`). Skill pages are organized **by harness** (that is how a user actually
holds the tool — one harness at a time), with the **parity matrix page**
(`docs-site/skills/index.md`) as the cross-cutting view: rows are the union of skill
names, columns the three harnesses, each cell a link or "—", followed by a hand-authored
fragment explaining every intentional harness-only skill (`repo-bench` is Claude-only
because it dispatches Claude models; `budget`/`lessons-loop` are Copilot-only;
`doctor` is Codex-only; …) so a dash reads as a design decision, not an omission. Each
per-skill page also carries generated "Also available on" links to its siblings.
Navigation lives statically in `mkdocs.yml` (no nav plugins); a live-tree test asserts
every generated page path appears in the nav exactly once AND every
`skills/…`/`deep-dives/…` path named in the nav is a real generated page — adding a
skill later fails the test until the nav line is added.

### D5 — Per-skill page anatomy (the template proven before it is applied 39 times)

Every generated skill page = (1) title + harness label; (2) a provenance comment naming
the source and the rebuild command; (3) the frontmatter description as a blockquote;
(4) generated facts: GitHub source link, sibling-harness links, shipped references list;
(5) `## In practice` — the hand-authored fragment, spliced verbatim (h3-only headings,
generator-validated); (6) `## The skill card — what the model reads` — the SKILL.md body
verbatim-but-transformed (headings demoted one level, relative links rewritten to site
pages or GitHub blob URLs, `{{POLYTROPOS_ROOT}}`/`${CLAUDE_PLUGIN_ROOT}` left intact
with an explanatory note line). Embedding the real body is deliberate: it is honest
("this is exactly what the model reads"), it can never drift (generated), and it frees
the fragment to be purely human-facing. The fragment template (six pinned h3 sections:
`### What it does`, `### When to reach for it`, `### Worked example`,
`### Failure modes & fallbacks`, `### Cost & safety`, `### Related`) is proven in Phase
3 on three deliberately-diverse pilots — `claude/route` (rich, has references),
`copilot/budget` (harness-only), `codex/doctor` (thin, safety-heavy) — and reviewed
before Phases 4–5 apply it at scale. A wrong template applied 39 times is this kit's
expensive failure mode; the Phase 3 review gate exists to prevent it.

### D6 — Fate of the existing hand-written docs

- **`docs/*.md` (24 files) stay exactly where they are, as the canonical, hand-edited
  sources.** They are *mirrored* to the site (`docs-site/deep-dives/<slug>.md`, slug =
  lowercased filename stem) by the generator, with a provenance banner and
  deterministically rewritten links (doc→doc links become sibling deep-dive links;
  `guide.html`/`how-it-works.html` links become links to the `guide`/`how-it-works`
  mirror pages; any other relative repo link becomes a
  `https://github.com/agentmc15/polytropos/blob/main/…` URL; external links untouched;
  nothing inside code fences is rewritten). Rationale: many tests and skills reference
  `docs/…` paths, README links them, and `test_harness_update.py` gates on their
  snapshot labels — moving them buys readers nothing and risks everything. A content fix
  to a deep-dive page is ALWAYS made in `docs/*.md`, then rebuilt.
- **`docs/guide.html` and `docs/how-it-works.html` are left alone** — repo-local styled
  conveniences, not mirrored (the site renders the .md sources with a better theme).
  Whether to eventually retire them is deliberately left to the user, post-launch.
- **`copilot-docs/` is linked, never absorbed** (owned by its own generator).
- README.md keeps all current links and gains the site link as the lead pointer.

### D7 — CI/deploy shape

`.github/workflows/docs-site.yml` (this repo currently has NO `.github/` directory — the
one under `copilot/` is bundle payload, not CI). Two jobs on push-to-main +
`workflow_dispatch`: **build** (checkout, Python 3.12, `pip install -r
docs-src/requirements.txt`, run `test_docs_*.py` as the drift gate, `mkdocs build
--strict`, upload Pages artifact from `site-build/`) and **deploy**
(`actions/deploy-pages`) with `permissions: contents: read, pages: write, id-token:
write`. Deploys therefore fail rather than publish a stale or link-broken site. The
workflow cannot be executed locally; its local proxies are the stdlib tests plus the T17
venv smoke build.

### D8 — Model & roles posture (evidence-based)

Implementer sonnet, verifier **sonnet** (not haiku: ledger shows verifier@haiku 60%
precision vs verifier@sonnet 92% over 66 measured events, and this kit's acceptance is
largely prose/structure quality — exactly where a weak verifier hurts), reviewer opus
(81% precision, the phase gate for template fidelity and fabricated-fact hunting).
Task pins: opus only where frontier judgment shapes everything downstream (T7 pilot
template, T8 audit, T15 front-door prose); haiku for the one fully-pinned mechanical
edit (T16); sonnet everywhere else. **Two optional roles are declared to TEST them** (no
optional role has ever been dispatched in this repo — `routing_scorecard.py --roles` has
no per-role evidence yet):

- `test-author` (sonnet) — this kit's load-bearing guard is a test (the drift test), and
  the generator has adversarial edge cases (malformed frontmatter, fenced-code
  rewriting, orphan generated files, fragment heading violations). Expected catches:
  brief-derived edge cases the implementer's own tests miss. On prose-only tasks
  (fragments, hand pages) it should report "no new test surface" rather than force a
  test — that null report is itself measurement data.
- `docs-editor` (haiku) — its ground is literally this kit's subject. Expected catches:
  stale cross-references in README/`docs/*.md`/docstrings after 39 skill-card edits and
  the site landing. Its kit-specific fence: generated pages are off-limits (fix the
  source + rebuild), and SKILL.md files remain runtime behavior, outside its scope.

## Risks & tripwires

1. **Sentinel-pinned skill text.** Any full-suite failure naming a string you changed →
   restore the exact line, relocate depth to references/ or the fragment instead. Never
   edit the asserting test to make an edit fit.
2. **Codex prompt mirrors.** Editing any of the 7 mirrored Codex stems (architect,
   effort, escalate, frontier-check, journal, route, usage) stales `codex/prompts/` →
   run `python3 bin/sync_codex_surfaces.py build` and commit the mirrors together;
   `tests/test_codex_surfaces.py` is the tripwire.
3. **Embedded bodies breaking `--strict`.** If T17's smoke build fails on a construct
   the link rewriter missed, fix `bin/docs_build.py` and rebuild — NEVER hand-patch a
   generated page.
4. **No network for the smoke build.** If `pip` cannot reach an index from the executor
   environment, mark T17 blocked with the exact error in NOTES.md; the user runs the
   venv recipe or lets the first CI run prove it. Never claim the site builds without a
   build.
5. **CLAUDE.md byte ceiling.** 16000 bytes, test-enforced; the docs-site invariant is
   already in place (~15.3k total). Nothing in this kit may add more there.
6. **Parallel rebuild collisions.** Every task that runs `docs_build.py build` rewrites
   ALL generated pages — those tasks are strictly serialized in TASKS.md; never
   parallelize them even if a dispatch loop thinks it can.
7. **Fabricated facts in fragments.** A flag, subcommand, or invocation form that
   appears in a fragment must exist in that skill's SKILL.md, the named engine's source,
   or the harness doc (`docs/COPILOT-HARNESS.md` / `docs/CODEX-HARNESS.md` /
   README/GUIDE). Verifier spot-checks by grep; a fabricated fact is a fail, not a nit.
8. **Nav drift.** Adding/removing any generated page without the matching `mkdocs.yml`
   nav line fails `tests/test_docs_site.py` — fix the nav, not the test.
