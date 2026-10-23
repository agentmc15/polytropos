# sdd-docs-refresh — Claude-side roster refresh, re-tier by evidence, and the spec-driven-development story

autonomy: advisory
budget: max-dispatches=30 max-escalations=3 max-consults=3

Written 2026-10-23 on branch `feat/route-experiment` at HEAD `9b5da6d` ("feat(pricing): price
Sonnet 5.5 and Haiku 5.5, with Haiku's long-prompt rate per request"). No `roles:` line: this
kit runs the standing trio (`workflow: reviewed`). The rationale is in D11.

## Goal

Bring every **Claude Code-side** surface of this repo current with the roster `data/pricing.json`
now carries (Sonnet 5.5 and Haiku 5.5 priced; `cached_date` 2026-10-07), re-tier role defaults
only where the ledger supports it, and add durable documentation — a source doc, a generated
site page, and a printable HTML elevator pitch — that explains polytropos as **spec-driven
development**: the architect writes the spec, cheaper pinned models execute against it, the
verifier and reviewer check against the spec rather than the implementer's claims, and the
ledger measures the result.

"Done" is checkable:

1. `python3 -m unittest discover -s tests` is green from the repo root (baseline recorded in
   `9b5da6d`'s body: 5745 tests OK, skipped=2; re-measure, never quote forward).
2. `python3 bin/docs_build.py check`, `python3 bin/copilot_docs.py check`,
   `python3 bin/sync_pricing_refs.py --check`, and `python3 bin/release_gate.py check` all exit 0.
3. Two new live-tree guards exist and pass — `tests/test_roster_currency.py` (Claude skills and
   plugin manifests name no superseded sonnet/opus default as current) and
   `tests/test_docs_snapshot_labels.py` (`docs/GUIDE.md`, `docs/HOW-IT-WORKS.md`,
   `docs/guide.html`, `docs/how-it-works.html` carry `data/pricing.json`'s `cached_date`) — and
   each was red against the tree before its fixing task ran (execute's red-green gate).
4. `docs/SPEC-DRIVEN.md` exists, is mirrored at `docs-site/deep-dives/spec-driven.md` by the
   generator, is listed once in `mkdocs.yml` nav, and is pointed at from `README.md`,
   `docs/GUIDE.md`, `docs/HOW-IT-WORKS.md`, and
   `docs-site/concepts/architect-execute-measure.md`.
5. `docs/spec-driven-pitch.html` exists and `tests/test_spec_driven_pitch.py` passes: 3–5
   print pages, self-contained, light/dark, every command and file it names exists in the tree,
   and any dollar figure sits under a snapshot label carrying `pricing.json`'s `cached_date`.
6. `.claude/kits/sdd-docs-refresh/INVENTORY.md` lists every stale item T1 found, and every row
   is marked `fixed (T<n>)` or `deferred: <reason>` by the closeout task — no silent drops.
7. Each phase ended in a commit on `feat/route-experiment` in the user's commit convention;
   `git status --porcelain` is empty at the end.

What this kit does NOT produce: the claude.ai artifact of the pitch. The main session publishes
`docs/spec-driven-pitch.html` as a private artifact after the kit finishes; the kit only writes
the file.

## Constraints and out-of-scope

- **Claude Code only.** Do not edit `copilot/`, `codex/`, `cursor/`, `copilot-docs/`,
  `data/pricing.copilot.json`, `data/pricing.codex.json`, `data/pricing.cursor.json`,
  `docs/COPILOT-*.md`, `docs/CODEX-HARNESS.md`, `docs/CURSOR-HARNESS.md`, or the Copilot/Codex
  sections of shared docs (`README.md` rows for Copilot/Codex, `docs/REFERENCE.md` Copilot/Codex
  tables, `docs/GUIDE.md` §7 "The other three harnesses"). When a shared file has per-harness
  sections, only the Claude text moves.
- **No pricing numbers move.** `data/pricing.json` is read, never written: not a price, not a
  note, not a row order (D2 explains why the Haiku row order stays). The generated mirrors under
  `skills/{route,fable-check}/references/pricing.json` are therefore untouched too — if
  `python3 bin/sync_pricing_refs.py --check` ever reports drift during this kit, something
  violated this fence.
- **Snapshot discipline (repo invariant).** A docs table that carries prices is a labeled
  snapshot tied to `pricing.json`'s `cached_date`. Moving a label to `2026-10-07` is allowed
  ONLY in the same edit that makes the table's rows agree with the file: derive the rows with a
  one-liner over the JSON (T4's brief has it), never retype from memory. No price, ratio, model
  id, or date is hardcoded into any SKILL.md, agent file, role template, or generator.
- **Skills are runtime behavior.** Before deleting or rewording any existing SKILL.md line, run
  `grep -rF '<distinctive 6+ word phrase>' tests/` — a hit means the line is a contract; keep it
  verbatim. The architect entry point stays under its 2800-word ceiling and execute under 3200
  (`tests/test_docs_skill_dispositions.py::EntryPointContractTests`); `skills/setup/SKILL.md`'s
  example JSON (`"claude-fable-5"`, `"Fable 5"`) is test-pinned and stays. The string
  `docs-site` never enters a SKILL.md.
- **Generated content is never hand-edited.** `docs-site/skills/**`, `docs-site/deep-dives/**`
  (`bin/docs_build.py build`), `copilot-docs/**` (`bin/copilot_docs.py build`), the marked block
  of `docs/RELEASE.md` (`bin/release_gate.py build`), and both pricing mirrors
  (`bin/sync_pricing_refs.py`). Hand pages under `docs-site/{index.md,concepts,getting-started,
  workflows}` ARE editable, and they must contain no model display names
  (`tests/test_docs_site_skeleton.py::HARDCODED_MODEL_NAME_PATTERNS` bans them).
- **Never invoke the real `claude`, `codex`, `copilot`, `agent`, or `gh` CLI** from any task,
  test, or verify command. The dispatchability of Haiku 5.5 therefore cannot be re-checked by
  this kit (D2); the pricing file's own note is the evidence of record.
- **Stdlib-only Python; `unittest` only; no pip.** New tests follow the live-tree pattern of
  `tests/test_harness_update.py::LiveTreeFreshnessTests` (reads the real tree, never writes,
  proves its own assertion is not vacuous on a synthetic fixture).
- **Never touch `~/.claude` or anything outside this repo; never re-install the plugin.** Do not
  bump `.claude-plugin/plugin.json`'s `version` — a release act the user takes separately.
- **Commit at green boundaries on `feat/route-experiment`; never push, never merge, never
  commit on `main`.** Subject `type(scope): outcome`, prose body (why the old state was wrong,
  what proves the new state, what is deliberately unfinished), trailer exactly as the executing
  session's harness mandates (the system reminder in that session names it — do not invent one).
- Out of scope: Haiku 5.5 as a dispatch default (D2); any change to `cost_report.DOWNGRADE_TARGET`
  (`9b5da6d` deliberately left it at `claude-sonnet-5`, same price); a rewrite of
  `docs/guide.html` / `docs/how-it-works.html` beyond the bounded refresh in D7; new skills; a
  plugin version bump; publishing the artifact; editing `CLAUDE.md`.

## Architecture & key decisions

### D1 — Pins stay tier aliases; concrete ids are derived, never typed

Every `model:` field in TASKS.md, every agent frontmatter, and every role template keeps using
the alias words `haiku` / `sonnet` / `opus` / `fable`. Two mechanisms already make an alias mean
"the current default of that tier": Claude Code's Agent tool resolves the alias itself, and the
headless driver resolves it to the FIRST row of that tier in `data/pricing.json`
(`bin/claude_execute.py::resolve_tier`, which is why `9b5da6d` placed Sonnet 5.5 above Sonnet 5
— "kits pinned `sonnet` now dispatch claude-sonnet-5-5"). Writing `claude-sonnet-5-5` into a skill
or agent would freeze a choice the data file already makes, and violate the single-source
invariant. Docs may NAME the current default ("the sonnet tier — Sonnet 5.5 today") only beside a
snapshot label or a derivation command (`python3 bin/aesop_bridge.py tiers`).

### D2 — Haiku 5.5 is priced, not the dispatch default; this kit does not flip it

`data/pricing.json` lists `claude-haiku-4-5` ABOVE `claude-haiku-5-5` on purpose. Its note:
"Listed before Haiku 5.5 so the haiku tier word keeps resolving here until Claude Code can
dispatch Haiku 5.5; move Haiku 5.5 above this row to make it the tier default." `9b5da6d`'s body
records why: the Claude Code on this machine (2.1.293 on 2026-10-07) listed Haiku 5.5 as needing
an update, so making it the default "would send kits a model the CLI refuses." The kit cannot
re-verify that (no real-CLI invocations), so the user's premise "Haiku 5.5 is available" is TRUE
for pricing and NOT YET TRUE for dispatch as far as the repo knows. Consequences:

- No role, skill, or doc is re-tiered onto Haiku 5.5. Docs say exactly: the haiku tier resolves
  to Haiku 4.5 today; Haiku 5.5 is priced (with its prompt-length rate above 100K input tokens)
  and becomes the default the day its row moves up — "moving the row up is the whole switch."
- The row flip is a one-line, user-initiated edit to `data/pricing.json` (plus
  `python3 bin/sync_pricing_refs.py`, the REFERENCE/README labels, and the goldens). It is out of
  scope here and must be named in the final report as the user's next decision, after they
  confirm their Claude Code lists Haiku 5.5 as selectable.

### D3 — Re-tier decisions, with the evidence (`python3 bin/routing_scorecard.py --history`, 2026-10-23)

The ledger aggregates by TIER WORD, not model version, so nothing in it distinguishes Sonnet 5
from Sonnet 5.5 or Haiku 4.5 from 5.5. Every decision below is therefore about the tier a role
runs on, and the Haiku rows are evidence about Haiku 4.5 only.

| Role / surface | Today | Decision | Evidence |
|---|---|---|---|
| Implementer (kit default, architect skill, HOW-IT-WORKS §4.3) | `sonnet` | **Keep.** | 35 kits: sonnet 168/187 first-try (90%), 0 escalations. No signal to move. |
| Verifier default (architect skill says `haiku`, "or sonnet if judgment needed"; HOW-IT-WORKS §4.3 and GUIDE say `haiku`) | `haiku` | **Re-tier the DEFAULT to `sonnet`; haiku only for purely mechanical checks.** | Role quality: haiku verifiers 28 events, 5 findings, 3 confirmed, 60% precision; sonnet verifiers 85 events, 31 findings, 29 confirmed, 94% precision. Haiku raised one finding per ~5.6 dispatches at 60% precision; sonnet one per ~2.7 at 94%. The verifier's whole value is catching what the implementer missed; the cheap tier mostly did not. The repo's recent kits already pin sonnet (`.claude/agents/docs-site-verifier.md`), so this records practice. |
| Reviewer | `opus` | **Keep.** | 45 events, 337 findings, 276 confirmed, 82% precision. |
| Scout template (`skills/architect/references/roles/scout.md`) | `haiku` | **Keep; no evidence either way.** | `--roles` shows no scout dispatches recorded anywhere. Grounding briefs are not adjudicable; a haiku scout is the cheap default by design. |
| Docs-editor template | `haiku` | **Keep; decline to re-tier on 4 dispatches.** | 4 dispatches, 6 findings, 1 confirmed (17%), marked "insufficient sample". Too thin to move a default in either direction; say so. |
| Synthesizer / test-author / second-verifier / red-team / security-auditor templates | as written | **Keep.** | test-author 22 dispatches 88% precision, 82% marginal rate — earning its pin. The others have no recorded dispatches. |
| `/route` subscription posture ("Opus 5.5 is the daily driver … drop to Sonnet 5") | names Sonnet 5 | **Rename to the current sonnet default; posture unchanged.** | `pricing.json` note: Sonnet 5.5 is "successor to Sonnet 5 at the same per-token price"; nothing in the ledger argues for moving the daily driver. |
| `/escalate` ladder, `/fable-check`, `/cost-report` prose | name Sonnet 5 | **Rename only.** | Same as above. The ladder's shape (cheapest trusted → verify → Fable) is unchanged. |
| `bin/cost_report.py` `DOWNGRADE_TARGET` | `claude-sonnet-5` | **Untouched (out of scope).** | `9b5da6d` chose this deliberately: same price, so the counterfactual dollars are identical. A docs sentence may say "re-priced at the Sonnet tier". |

Where a decision above touches `skills/architect/SKILL.md`, the shared kit contract with
`skills/execute/SKILL.md` must be re-checked in the same task (T2's acceptance lists the items).

### D4 — What "stale" means, and the inventory that makes it concrete

T1 writes `.claude/kits/sdd-docs-refresh/INVENTORY.md` — one row per stale item with file,
line, the stale text, the correct value, and the SOURCE of the correct value (a `pricing.json`
field, a command's output, a test). The architect already found these; T1 confirms them and
sweeps for more:

- `docs/GUIDE.md` §2 and `docs/HOW-IT-WORKS.md` §1: lineup tables lack Sonnet 5.5 / Haiku 5.5,
  labels say `2026-09-24` (file says `2026-10-07`).
- `docs/guide.html` and `docs/how-it-works.html`: label `2026-07-01`; tables show Opus 4.8 as
  daily driver and Sonnet 5 "intro" pricing; how-it-works.html carries a rotting callout
  ("11 execution kits … 32 of 32 tasks"); both say "Fable 5" where the frontier default is 5.1.
- `docs/HOW-IT-WORKS.md` ~line 41–44 claims `skills/route/SKILL.md` and `skills/fable-check/
  SKILL.md` "still name Opus 4.8" — they name Opus 5.5 now; the sentence is stale about itself.
  Lines 216/220 and `docs/GUIDE.md` 256/262 still name Opus 4.8 as the refusal fallback — check
  what `/escalate` and `/fable-check` actually say today and make the docs match them.
- `docs/AESOP-INTEGRATION.md` ~line 134–137: example `tiers` output shows `mid: claude-sonnet-5`,
  labeled 2026-09-24; `python3 bin/aesop_bridge.py tiers` prints `claude-sonnet-5-5` today.
- `skills/route/SKILL.md` table (Sonnet 5 as workhorse; no Haiku 5.5 mention),
  `skills/fable-check/SKILL.md` description ("vs Opus 5.5 / Sonnet 5"), `skills/escalate/SKILL.md`
  ("typically Sonnet 5"), `skills/cost-report/SKILL.md` ("less on Sonnet 5").
- `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` descriptions name
  "Fable 5 / Opus 5 / Sonnet 5 / Haiku 4.5".
- `docs/HOW-IT-WORKS.md` §4.3 and `docs/GUIDE.md` architect bullet: verifier shown as `haiku`
  (D3 moves the default).
- NOT stale, do not touch: `README.md` line ~50 (already current, carries `2026-10-07`),
  `docs/REFERENCE.md` (current; `tests/test_reference_doc.py` guards it), `docs/RELEASE.md`
  (generated block).

### D5 — The spec-driven-development doc lives at `docs/SPEC-DRIVEN.md`

A new `docs/*.md` is the right home because the generator auto-mirrors it
(`bin/docs_build.py::deep_dive_page_map` globs `docs/*.md`; the slug is the lowercased stem, so
`docs/SPEC-DRIVEN.md` → `docs-site/deep-dives/spec-driven.md`). Three mechanical consequences the
writing task owns: add one nav line under "Deep dives" in `mkdocs.yml`
(`tests/test_docs_site.py` checks nav coverage in both directions), bump
`tests/test_docs_build_adversarial.py::test_page_map_has_current_expected_entries` from 40 to 41
and append the lineage sentence to its docstring (that is the test's own precedent), and run
`python3 bin/docs_build.py build`. The doc is narrative but every claim traces to a file: the
architect's PLAN/TASKS/GUARDRAILS contract (`skills/architect/SKILL.md`), the execute loop
(`skills/execute/SKILL.md`: the orchestrator runs the verify command itself; the verifier is fresh
context; `evidence:` red-green blocks a task whose verify already passes), the one kit contract
(`bin/kit_contract.py graph/roster/freshness`), the attempt ledger and execution boundary
(`bin/attempt_ledger.py`, `bin/exec_policy.py`), and measurement (`bin/routing_scorecard.py
--history`, including the architect's own brief-defect kinds — the spec is audited too). Numbers
are commands, not figures (`docs/GUIDE.md` §6 "The track record is a command, not a number").
Pointers land in `README.md` ("What you get" paragraph), `docs/GUIDE.md` (architect section),
`docs/HOW-IT-WORKS.md` (§4.3), and the hand page `docs-site/concepts/architect-execute-measure.md`
("Related" list, linking `../deep-dives/spec-driven.md`).

### D6 — The pitch: one self-contained HTML file, verified by a stdlib test

`docs/spec-driven-pitch.html` follows the conventions of `docs/guide.html`: inline `<style>`,
the same CSS custom properties (`--bg --ink --muted --line --accent --fable --opus --sonnet
--haiku`), Georgia body, `.wrap` at 860px, `.callout`, `.kicker`, tier color classes, no
`<script>`, no external stylesheet or font. Two additions the user asked for that the existing
files lack: a `@media (prefers-color-scheme: dark)` block that redefines the same tokens, and
print rules — `@media print { .page { break-after: page; page-break-after: always; } }` with the
last page exempt, so the file prints as exactly as many pages as it has `<section class="page">`
elements. Page count is not computable from HTML in stdlib, so the test enforces a proxy stated
as one: 3–5 `<section class="page">` elements, each at most 650 words of visible text, the whole
file 1400–2800 words (at 17px Georgia in an 860px column, one US-Letter page holds roughly
450–550 words with headings). The test also enforces truth: every `bin/<name>.py` it mentions
exists; every `/polytropos:<skill>` names a directory under `skills/`; every
`PLAN.md`/`TASKS.md`/`GUARDRAILS.md`/`NOTES.md` it names is in the architect skill's contract; no
`claude-<family>-<n>` model id appears; if the text contains `$`, a snapshot label containing
`pricing.json`'s `cached_date` appears too. The generator ignores the file (not in
`_UNMIRRORED_HTML_TARGETS`); a link to it from `docs/SPEC-DRIVEN.md` rewrites to a GitHub blob
URL, which is acceptable.

### D7 — The two legacy HTML companions get a bounded refresh, not a rewrite

`docs/guide.html` and `docs/how-it-works.html` were last touched in `71b9fdf` and are stale in
their lineup tables, labels, and daily-driver names. The docs-site kit left them as-is (its D6),
and a rewrite is out of proportion. T5 changes only: the lineup table rows and the snapshot label
(to match `pricing.json`, derived); "Opus 4.8" as daily driver → the Opus tier's current
default; "Fable 5" where it means the current frontier default → "Fable 5.1" (leave the slogan
"Fable 5 runs once…" alone — see D8); Sonnet "intro pricing" cells → the file's current rates;
the rotting "11 kits … 32 of 32" callout → a sentence pointing at `python3 bin/routing_scorecard.py
--history`. Everything else stays byte-identical. The new `tests/test_docs_snapshot_labels.py`
covers both files so they cannot silently rot again.

### D8 — The slogan "Fable 5 runs once, at the start; its judgment persists as scaffolding" stays

It appears verbatim in `skills/architect/SKILL.md`, `docs/HOW-IT-WORKS.md` §4.3,
`docs/REFERENCE.md` ("Its own words"), both HTML companions, and is the "scaffolding note"
`bin/lessons_promote.py` names (`SCAFFOLDING_NOTE_SOURCE = "skills/architect/SKILL.md"`;
`tests/test_lessons_promote.py`). It is a quotation, not a roster claim. Do not edit it; where a
doc needs the current frontier name beside it, add "(the frontier tier — Fable 5.1 today)" rather
than changing the quote. `docs/GUIDE.md` already renders it as "Fable 5.1 runs once" — leave that
too; it is not test-pinned and is not wrong.

### D9 — Plugin manifests describe tiers, not models

`.claude-plugin/plugin.json` and `marketplace.json` descriptions move to "pick the right tier
(frontier / Opus / Sonnet / Haiku)" — a roster-free description cannot rot, matching
`mkdocs.yml`'s `site_description` rule in `tests/test_docs_site_skeleton.py`. `version` is not
bumped (out of scope). `python3 bin/release_gate.py check` must stay at `verdict: OK`.

### D10 — Two new live-tree guards, each red before its fixing task

`tests/test_roster_currency.py` derives from `data/pricing.json` the CURRENT and SUPERSEDED
display names of the sonnet and opus tiers (first row vs later rows of each tier) and asserts
that no `skills/*/SKILL.md` except `skills/setup/SKILL.md` names a superseded one as a standalone
word (`\bSonnet 5\b(?!\.)`, `\bOpus 5\b(?!\.)`) on a line that lacks `superseded`, `historical`,
`retained`, or `older`; and that neither plugin manifest description contains any display name.
The haiku and frontier tiers are deliberately excluded: Haiku 5.5 is second in its tier without
being superseded (D2), and "Fable 5" is a protected quotation (D8).
`tests/test_docs_snapshot_labels.py` asserts the four docs in D7/D4 contain `cached_date`, and
that each lineup table names the first-row display of every tier. Both tests include a synthetic
negative fixture proving the assertion can fail (`test_same_assertion_shape_fails_on_a_synthetic_
stale_tree` precedent).

### D11 — No optional roles; sonnet verifier; opus reviewer

The kit's implementers ARE documentation editors, so a phase-end `docs-editor` would re-do their
work with a template whose only evidence is 17% precision on 4 dispatches. A `scout` would
duplicate T1. Red-team and security-auditor have no attack surface here (prose, one test file,
one HTML file, no runtime path). Per D3 the verifier agent pins `sonnet` — it must judge whether
a sentence is true of the code, not just whether a command exits 0.

## Risks and tripwires

| Risk | Tripwire | Response |
|---|---|---|
| An executor "fixes" a stale number in a generated page | `python3 bin/docs_build.py check` or `bin/copilot_docs.py check` non-zero; a diff under `docs-site/skills|deep-dives` or `copilot-docs/` with no source change | Revert the generated file, fix the source, rebuild. |
| A model id or price lands in a SKILL.md, agent, or role template | `grep -rnE "claude-(sonnet|haiku|opus|fable)-[0-9]" skills/*/SKILL.md .claude/agents/sdd-docs-refresh-*.md` returns anything new; `tests/test_roster_currency.py` | Replace with the tier word plus a derivation command. |
| `skills/architect/SKILL.md` edit breaks the shared kit contract or the ceiling | `EntryPointContractTests` fails; or the contract items in CLAUDE.md (layout, task fields, status vocabulary, phase headings, `depends:`/`independent:`, model-field override) no longer read the same in both skills | T2's acceptance requires reading both skills against the list; fix before commit. |
| A docs table label moves without its rows | `tests/test_docs_snapshot_labels.py` row assertions; a human diff showing only the date changed | Derive rows from the JSON in the same edit. |
| Haiku 5.5 written as a default anywhere | grep `Haiku 5.5` in the diff: every hit must sit in a sentence that says it is priced and NOT yet the tier default | Reword per D2. |
| The pitch claims a feature that does not exist | `tests/test_spec_driven_pitch.py` existence checks; the reviewer's read with `skills/execute/SKILL.md` open | Cut the claim or cite the file:line that makes it true. |
| Rotting numbers reappear ("N kits", "N of N tasks", test counts) | Reviewer grep for `\b\d+ (kits|tasks|tests)\b` in new prose | Replace with the command that prints it. |
| Page-map count test breaks when `docs/SPEC-DRIVEN.md` lands | `tests/test_docs_build_adversarial.py` fails on 40 vs 41 | Bump to 41 with the lineage sentence (precedent in the docstring). |
| A verifier mutates a tracked file to prove a guard fires | `git status --porcelain` non-empty after a read-only dispatch | Verifier restores byte-for-byte and reports its own defect; use the temp-copy recipe in GUARDRAILS.md. |
| Commit lands on `main` or gets pushed | `git branch --show-current` ≠ `feat/route-experiment`; any `git push` | Never; stop and report. |
