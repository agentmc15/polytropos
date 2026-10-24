# sdd-docs-refresh — tasks

Dispatch preamble. Read `PLAN.md` (D1–D11, the out-of-scope fence) and `GUARDRAILS.md` before
any task. Every verify command runs from the repo root
`/Users/michaelcave/Developer/reposV2/polytropos`. **Tasks that run `python3 bin/docs_build.py
build` rewrite every generated page — never run two of them concurrently**: T2, T4, T5, T7, T8
are strictly serial in that order. Warm-cluster candidates (serial `depends:` chain, shared
primary surface, same `model` pin): **T4 → T5** (both sonnet; `docs/GUIDE.md`/`HOW-IT-WORKS.md`
then their `.html` companions, sharing `tests/test_docs_snapshot_labels.py`). T2 → T3 is serial
but changes pin (sonnet → haiku), so T3 is a fresh dispatch. T7 (opus) and T9 (opus) are always
fresh. T1 is the only task that may start immediately. Statuses: pending | in-progress | done |
blocked. The verifier agent is `sdd-docs-refresh-verifier` (sonnet, PLAN D3/D11); the reviewer
`sdd-docs-refresh-reviewer` (opus) runs at each phase end.

Test invocation: this repo's tests load ONLY through `python3 -m unittest discover -s tests` (optionally `-p '<file>.py'` and `-k <Class>`); the `python3 -m unittest tests.test_x` form fails to import. Never pipe a unittest run into `tail` inside a verify command — the pipe hides its exit status.

Conventions that bind every task here (detail in GUARDRAILS.md): no model id, price, ratio, or
date typed into a skill, agent, or role file; snapshot labels move only with derived rows;
generated pages are rebuilt, never edited; `grep -rF` a distinctive phrase across `tests/` before
rewording any SKILL.md line; never invoke the real `claude`/`codex`/`copilot`/`agent`/`gh` CLI;
nothing under `copilot/`, `codex/`, `cursor/`, `copilot-docs/`, or the non-Claude pricing files
changes.

## Phase 1 — Inventory

### T1 — Staleness inventory of every Claude-side documentation surface
- id: T1
- title: Write INVENTORY.md listing every stale Claude-side item with its correct value and source
- status: done
- model: sonnet
- independent: yes
- evidence: red-green

Create `.claude/kits/sdd-docs-refresh/INVENTORY.md` (new file; nothing else is created or
edited by this task). It is the worklist T2–T5 and T11 consume, so every row must be concrete
enough that a model with no other context can act on it.

Surfaces to sweep (Claude-side only — do not list Copilot/Codex/Cursor items even if you see
them): `README.md` (Claude rows and paragraphs only), `SETUP.md`, `SECURITY.md`, `docs/GUIDE.md`,
`docs/HOW-IT-WORKS.md`, `docs/REFERENCE.md` (Claude table and prose only), `docs/guide.html`,
`docs/how-it-works.html`, `docs/AESOP-INTEGRATION.md`, `docs/ROUTING-HISTORY.md`,
`docs/EVIDENCE-LOOP.md`, every `skills/*/SKILL.md` and `skills/*/references/*.md` (NOT the two
generated `references/pricing.json` mirrors), `skills/architect/references/roles/*.md`,
`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, and the hand-authored site pages
`docs-site/index.md`, `docs-site/concepts/*.md`, `docs-site/getting-started/claude.md`,
`docs-site/workflows/*.md`. Generated pages (`docs-site/skills/**`, `docs-site/deep-dives/**`,
`docs/RELEASE.md`'s marked block) are NOT inventoried — they follow their sources.

What counts as stale (each with its source of truth):
1. **Roster facts** — any sentence that names a model as the current default of a tier when
   `data/pricing.json` says otherwise. Derive the truth, do not recall it:
   `python3 -c "import json;d=json.load(open('data/pricing.json'));print(d['cached_date']);[print(k,v['tier'],v['display']) for k,v in d['models'].items()]"`
   and `python3 bin/aesop_bridge.py tiers`. The FIRST row of a tier is its current default.
   Today that is Fable 5.1 / Opus 5.5 / Sonnet 5.5 / Haiku 4.5; Haiku 5.5 is priced but
   deliberately second (read its note and Haiku 4.5's note — PLAN D2). "Sonnet 5" standing for
   the workhorse, "Opus 4.8" standing for the daily driver, and "Fable 5" standing for the current
   frontier model are stale; the quotation "Fable 5 runs once, at the start; its judgment persists
   as scaffolding" is NOT (PLAN D8) and must not be listed.
2. **Snapshot labels and tables** — any "cached `YYYY-MM-DD`" / "Prices cached …" label that is
   not `data/pricing.json`'s `cached_date`, and any price table whose rows disagree with the file
   (missing Sonnet 5.5 / Haiku 5.5 rows, Sonnet "intro" rates, Opus 4.8 at $5 shown as current).
3. **Claims about skill behavior the skill no longer states** — compare each doc sentence of the
   form "the skill does X" against the SKILL.md. Known case to confirm: `docs/GUIDE.md` (~lines
   256 and 262), `docs/HOW-IT-WORKS.md` (~line 220), `docs/guide.html` (~303) and
   `docs/how-it-works.html` (~184) describe a Fable "refusal fallback to Opus 4.8"; `grep -rn
   refusal skills/escalate skills/fable-check skills/route` finds nothing. Also
   `docs/HOW-IT-WORKS.md` ~lines 41–44 claims `skills/route/SKILL.md` and `skills/fable-check/
   SKILL.md` "still name Opus 4.8" — check what they name today.
4. **Role defaults** — where a doc or skill states the verifier agent's default model as `haiku`
   (PLAN D3 moves the default to `sonnet`; known sites: `skills/architect/SKILL.md` Step 2,
   `docs/HOW-IT-WORKS.md` §4.3 table, `docs/GUIDE.md` architect bullet "(sonnet / haiku / opus)").
5. **Rotting numbers** — kit counts, task tallies, test counts, percentages presented as current
   facts (known: `docs/how-it-works.html` callout "11 execution kits … 32 of 32 tasks"). Numbers
   inside a sentence that dates them ("as of", "measured on", "snapshot") are fine.
6. **Stale example output** — a pasted command output that the command no longer prints (known:
   `docs/AESOP-INTEGRATION.md` ~134–137 `tiers` example showing `claude-sonnet-5`).

Required file shape (markdown; keep the headings exactly — T11 parses them by eye, the
verifier by grep):

```
# sdd-docs-refresh — staleness inventory
Swept: <date> against data/pricing.json cached_date <date from the file>

## Stale items
| # | File | Line | Stale text (verbatim, trimmed) | Correct value | Source of truth | Kind | Fix in |
|---|---|---|---|---|---|---|---|
| 1 | docs/GUIDE.md | 58 | cached `2026-09-24` | cached `2026-10-07` | data/pricing.json cached_date | label | T4 |
...

## Checked and current (do not touch)
- README.md:50 — names Sonnet 5.5 and the Haiku 5.5 caveat; carries 2026-10-07
...

## Out of scope seen but not listed
- <one line per non-Claude item you noticed, so the reviewer knows you saw it>
```

`Kind` ∈ `roster | label | table | behavior-claim | role-default | rotting-number | example`.
`Fix in` ∈ `T2` (skills), `T3` (plugin manifests), `T4` (`docs/*.md`), `T5` (the two `.html`
companions), `T8` (hand site pages / pointers), or `defer: <reason>` when the fix is out of this
kit's scope (say why). Line numbers are a courtesy; the verbatim stale text is what later tasks
grep for, so copy it exactly. Include every known item named above once you have confirmed it
against the live file (if one is already current, move it to "Checked and current" and say so).

Acceptance:
- `INVENTORY.md` exists with the three `##` sections and a `Swept:` line carrying the file's
  real `cached_date`.
- At least the six known kinds appear, and every known site named in this brief is either a row
  or a "checked and current" bullet.
- Every row's "Correct value" cites a source of truth that exists (a `pricing.json` field, a
  command, a SKILL.md path, a test).
- No row targets a Copilot/Codex/Cursor surface or a generated page.
- `git status --porcelain` shows exactly one new path: the inventory file.

Verify:
```
test -f .claude/kits/sdd-docs-refresh/INVENTORY.md && grep -q '^## Stale items' .claude/kits/sdd-docs-refresh/INVENTORY.md && grep -q '^## Checked and current' .claude/kits/sdd-docs-refresh/INVENTORY.md && grep -q "Swept: .*$(python3 -c "import json;print(json.load(open('data/pricing.json'))['cached_date'])")" .claude/kits/sdd-docs-refresh/INVENTORY.md && for k in roster label table behavior-claim role-default rotting-number example; do grep -q "| $k |" .claude/kits/sdd-docs-refresh/INVENTORY.md || { echo "missing kind $k"; exit 1; }; done && ! grep -nE '^\| [0-9]+ \| (copilot/|codex/|cursor/|copilot-docs/|docs-site/skills/|docs-site/deep-dives/)' .claude/kits/sdd-docs-refresh/INVENTORY.md && echo INVENTORY-OK
```

## Phase 2 — Claude roster currency

### T2 — Skills name the current tier defaults; verifier default re-tiered; roster guard added
- id: T2
- title: Refresh route/fable-check/escalate/cost-report/architect skill text and add tests/test_roster_currency.py
- status: done
- model: sonnet
- depends: T1
- evidence: red-green

Files: `skills/route/SKILL.md`, `skills/fable-check/SKILL.md`, `skills/escalate/SKILL.md`,
`skills/cost-report/SKILL.md`, `skills/architect/SKILL.md`, new `tests/test_roster_currency.py`,
plus the docs-site rebuild (SKILL.md files are generator inputs). Consult
`.claude/kits/sdd-docs-refresh/INVENTORY.md` rows marked `T2`; this brief names the known ones.

Why: the skills still describe Sonnet 5 as the workhorse although `data/pricing.json` (and
`bin/claude_execute.py::resolve_tier`, first-row-of-tier) make Sonnet 5.5 the sonnet default;
and the architect skill's verifier default (`haiku`) is contradicted by the ledger (PLAN D3:
haiku verifiers 60% precision over 28 events vs sonnet 94% over 85). Skills must keep deriving
models from data — so the edits name tiers and current display names as glosses, never ids.

Edits (additive-first; before rewording ANY existing line run
`grep -rF '<6+ word phrase of it>' tests/` and keep a hit verbatim):

1. `skills/route/SKILL.md` tier table (~lines 25–28): the sonnet row reads "Sonnet 5.5" (keep its
   "speed-and-intelligence workhorse" wording); the Opus row's "when Sonnet 5 at high effort
   falls short" → "Sonnet 5.5"; the Haiku row keeps Haiku 4.5 as the dispatch default and gains
   one clause: Haiku 5.5 is priced in `pricing.json` with a separate rate for single prompts over
   its `long_context.threshold_input_tokens`, and becomes the haiku default when its row leads
   its tier — do not type the threshold number or the rates. Subscription posture (~line 40):
   "Drop to Sonnet 5" → "Drop to the sonnet tier (Sonnet 5.5 today)". The existing sentence "The
   first row in each tier of `pricing.json` is the current default" (~line 32) stays — it is the
   rule the table glosses.
2. `skills/fable-check/SKILL.md`: description "vs Opus 5.5 / Sonnet 5" → "vs Opus 5.5 / Sonnet
   5.5"; line ~19 "anything Sonnet 5 or Opus 5.5 can handle" → "Sonnet 5.5".
3. `skills/escalate/SKILL.md` ~line 22: "typically Sonnet 5 for routine coding/edits" → "typically
   the sonnet tier (Sonnet 5.5 today)".
4. `skills/cost-report/SKILL.md` ~lines 24 and 33: the parenthetical roster list names the current
   defaults from the file; "would have cost $X.XX less on Sonnet 5" → "on the Sonnet tier" — the
   engine's `DOWNGRADE_TARGET` is `claude-sonnet-5` by `9b5da6d`'s deliberate choice (same price),
   so do not claim the re-pricing is at Sonnet 5.5; "the Sonnet tier" is true either way.
5. `skills/architect/SKILL.md` Step 2 trio line for the verifier (~line 56): change
   "`model: haiku` (or sonnet if judgment needed)" to "`model: sonnet` by default (haiku only when
   every check is mechanical — a command exit code, a byte comparison); the routing history's
   Role quality card shows why" — one sentence, no numbers (numbers rot; the card is the source).
   Also the `description` (line 3) and Step 0 heading (line 10) may say "the frontier tier
   (Fable 5.1 today)" instead of "Fable 5" IF the word-count stays ≤ 2800 and no test pins them
   (`grep -rF "Plan a complex task once on Fable 5" tests/` and `grep -rF "Get onto Fable 5"
   tests/` were empty on 2026-10-23 — re-check). Line 8's quotation is untouchable (PLAN D8).
   Do NOT touch `skills/architect/references/roles/*.md` (their `model:` pins stand per D3) or
   `references/routing-evidence.md`.
6. New `tests/test_roster_currency.py` (stdlib `unittest`, live-tree, no fixtures written to the
   repo). Derive from `data/pricing.json`: for each of the tiers `sonnet` and `opus`, the first
   row's `display` is CURRENT and every later row's `display` is SUPERSEDED. Assert:
   (a) for every `skills/*/SKILL.md` except `skills/setup/SKILL.md`, no line contains a
   superseded display name as a standalone token — regex built from the name with
   `re.escape(name) + r"\b(?![.\d])"` so "Sonnet 5" does not match "Sonnet 5.5" — unless that
   line also contains one of `superseded`, `historical`, `retained`, `older`;
   (b) `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` `description` fields
   contain NO display name from any tier of the file (so T3 is red until it lands — that is
   intended; T2's verify runs only test (a) by name, see below);
   (c) a synthetic negative: the same checker over an in-memory string "use Sonnet 5 for edits"
   with a fake pricing dict where Sonnet 5 is superseded raises `AssertionError` — proving the
   guard is not vacuous. Name the test classes `SkillRosterCurrencyTests` (a, c) and
   `ManifestDescriptionTests` (b). Module docstring: what it guards and why haiku/frontier tiers
   are excluded (PLAN D2, D8).
7. `python3 bin/docs_build.py build` — the skill cards are generator inputs; stage the rebuilt
   pages with the skill edits. `python3 bin/docs_build.py check` must then exit 0.

Shared-contract re-check (binding because `skills/architect/SKILL.md` is touched): read both
`skills/architect/SKILL.md` and `skills/execute/SKILL.md` and confirm the following still read
identically in both — kit layout `.claude/kits/<slug>/PLAN.md` + `TASKS.md` + `GUARDRAILS.md`
(+ `NOTES.md` owned by execute); task fields `id`, `title`, `status`, `model`, brief, acceptance,
verify; status vocabulary exactly `pending | in-progress | done | blocked`; `## Phase N` headings;
`depends:`/`independent:` marking; the task `model` field overriding the agent frontmatter at
dispatch. Record "contract re-checked: unchanged" (or what differed and how you reconciled it)
in your report.

Acceptance:
- Every edit above applied; `grep -nE "Sonnet 5([^.0-9]|$)" skills/route/SKILL.md
  skills/fable-check/SKILL.md skills/escalate/SKILL.md skills/cost-report/SKILL.md` is empty
  (ERE has no lookahead — this form excludes "Sonnet 5.5" and "Sonnet 50").
- `grep -rnE "claude-(sonnet|haiku|opus|fable)-[0-9]" skills/*/SKILL.md` shows nothing new
  versus `git stash`-free comparison `git diff -U0 skills | grep '^+' | grep -E "claude-(sonnet|haiku|opus|fable)-[0-9]"` → empty.
- `tests/test_roster_currency.py::SkillRosterCurrencyTests` passes and was red before the skill
  edits (execute's gate checks this; if you need to see it yourself, run the test module on a
  temp copy of the pre-edit tree, never by reverting tracked files in place).
- Architect body ≤ 2800 words; `python3 -m unittest discover -s tests -p 'test_docs_skill_dispositions.py' -q`,
  `-p 'test_skill_entrypoints.py'`, and `-p 'test_lessons_promote.py'` all green (this repo's tests load
  only through `discover -s tests`; `python3 -m unittest tests.test_x` fails to import).
- `python3 bin/docs_build.py check` exits 0; `python3 bin/sync_pricing_refs.py --check` exits 0.
- No file under `copilot/`, `codex/`, `cursor/`, `copilot-docs/`, `data/` changed.

Verify:
```
test -f tests/test_roster_currency.py && python3 -m unittest discover -s tests -p 'test_roster_currency.py' -k SkillRosterCurrencyTests -q && python3 -m unittest discover -s tests -p 'test_docs_skill_dispositions.py' -q && python3 -m unittest discover -s tests -p 'test_skill_entrypoints.py' -q && python3 -m unittest discover -s tests -p 'test_lessons_promote.py' -q && ! grep -nE "Sonnet 5([^.0-9]|$)" skills/route/SKILL.md skills/fable-check/SKILL.md skills/escalate/SKILL.md skills/cost-report/SKILL.md && python3 bin/docs_build.py check && python3 bin/sync_pricing_refs.py --check && git diff --quiet -- copilot codex cursor copilot-docs data && echo T2-OK
```

### T3 — Plugin manifests describe tiers, not a model list
- id: T3
- title: Replace the model roster in plugin.json and marketplace.json descriptions with tier words
- status: done
- model: haiku
- depends: T2
- evidence: red-green

Files: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` — the `description`
string in each (and only that string; `version`, `name`, `author` are untouched). Today both read
"… pick the right model (Fable 5 / Opus 5 / Sonnet 5 / Haiku 4.5), …" which is stale twice over
and will rot again. Replace the parenthetical with tier words, e.g. "pick the right tier
(frontier / Opus / Sonnet / Haiku) per task" — no model display names, no ids, no dates
(PLAN D9). Keep the rest of the sentence. Keep JSON valid, 2-space indentation as found, trailing
newline as found.

Acceptance:
- `tests/test_roster_currency.py::ManifestDescriptionTests` passes (it was red before this task).
- `python3 -c "import json;json.load(open('.claude-plugin/plugin.json'));json.load(open('.claude-plugin/marketplace.json'))"` succeeds.
- `python3 bin/release_gate.py check` still prints `verdict: OK`.
- `git diff --stat` touches only the two manifest files.

Verify:
```
python3 -m unittest discover -s tests -p 'test_roster_currency.py' -q && python3 -c "import json;json.load(open('.claude-plugin/plugin.json'));json.load(open('.claude-plugin/marketplace.json'))" && python3 bin/release_gate.py check | grep -q 'verdict: OK' && echo T3-OK
```

### T4 — GUIDE.md, HOW-IT-WORKS.md and AESOP-INTEGRATION.md current, with a snapshot-label guard
- id: T4
- title: Refresh the Claude docs' lineup tables, labels, role defaults and behavior claims; add tests/test_docs_snapshot_labels.py
- status: done
- model: sonnet
- depends: T1, T2
- evidence: red-green

Files: `docs/GUIDE.md`, `docs/HOW-IT-WORKS.md`, `docs/AESOP-INTEGRATION.md`, new
`tests/test_docs_snapshot_labels.py`, docs-site rebuild. Work from the `T4` rows of
`INVENTORY.md`; the known ones are below. Only Claude sections move: `docs/GUIDE.md` §7 "The
other three harnesses" and anything describing Copilot/Codex/Cursor stays byte-identical.

1. **Lineup tables and labels.** `docs/GUIDE.md` §2 (label ~line 58, table ~60–66; also the
   footer label ~line 985 "snapshot cached `2026-09-24`") and `docs/HOW-IT-WORKS.md` §1 (table
   ~9–17, label ~19). Derive rows, never retype:
   `python3 -c "import json;d=json.load(open('data/pricing.json'));print(d['cached_date']);[print(k,v['display'],v['tier'],v['input_per_mtok'],v['output_per_mtok'],v.get('long_context')) for k,v in d['models'].items()]"`.
   Table rows: one per model the table ALREADY lists plus Sonnet 5.5 and Haiku 5.5 (keep the
   tables' existing shape and columns; do not add every historical row). Sonnet 5.5's "Best
   for"/"Relative cost" cell says successor to Sonnet 5 at the same rate; Haiku 5.5's cell says
   "priced for prompts up to its threshold, higher rate above it; not the haiku default yet (row
   order in pricing.json)" — you may show the base rates since the table is a labeled snapshot,
   and must say the long-context rate exists without turning the row into two. Then and only
   then move every label in the file to the file's `cached_date`. HOW-IT-WORKS §1's "Relative
   cost" column is recomputed from the derived numbers.
2. **Behavior claims.** `docs/HOW-IT-WORKS.md` ~lines 41–44: the clause claiming
   `skills/route/SKILL.md` and `skills/fable-check/SKILL.md` "still name Opus 4.8" is false after
   T2 — rewrite to say the tier is derived (`python3 bin/aesop_bridge.py tiers`) and the skills
   name the current default as a gloss. The "refusal fallback to Opus 4.8" sentences
   (`docs/GUIDE.md` ~256 and ~262, `docs/HOW-IT-WORKS.md` ~220): no Claude SKILL.md states a
   refusal fallback (`grep -rn refusal skills/*/SKILL.md` — confirm). Rewrite each as operator
   practice, not skill behavior: "if a frontier subagent returns a `refusal` stop reason, re-run
   that hop on the Opus tier yourself — the skill does not do this for you", or drop the
   sentence. Never leave a doc attributing to a skill a step the skill's text does not contain.
   Lines ~216 "(typically Sonnet 5 for routine coding, Opus 4.8 for harder reasoning)" → tier
   words with current glosses, matching `skills/escalate/SKILL.md` after T2.
3. **Role defaults.** `docs/HOW-IT-WORKS.md` §4.3 Subagents row: verifier `model: haiku` →
   `model: sonnet` with a half-sentence "haiku only for purely mechanical checks"; `docs/GUIDE.md`
   architect bullet "model-pinned (sonnet / haiku / opus)" → "(sonnet / sonnet / opus — haiku for
   a verifier whose checks are purely mechanical)". `docs/HOW-IT-WORKS.md` §4.3 TASKS row's
   "`haiku` for mechanical ones" stays (it is about task pins, still true).
4. **Other Claude roster mentions** in these two files: "Sonnet 5" as the current workhorse →
   "Sonnet 5.5" (GUIDE ~107, ~273, ~733–741; HOW-IT-WORKS ~160, ~229); `docs/GUIDE.md` ~776/~817
   and `docs/HOW-IT-WORKS.md` example commands `check-budget 25 M claude-sonnet-5` → run
   `python3 bin/aesop_bridge.py tiers` and use the id it prints for `mid`. Leave "Fable 5 runs
   once…" quotations and GUIDE's "Fable 5.1 runs once" alone (PLAN D8). Leave `docs/GUIDE.md` §7
   and every Copilot/Codex line alone.
5. `docs/AESOP-INTEGRATION.md` ~130–137: replace the example `tiers` JSON with the current output
   of `python3 bin/aesop_bridge.py tiers --json` and re-label it with the file's `cached_date`
   ("run the command for current values" stays).
6. New `tests/test_docs_snapshot_labels.py` (live-tree; precedent
   `tests/test_harness_update.py::LiveTreeFreshnessTests`): for each of `docs/GUIDE.md`,
   `docs/HOW-IT-WORKS.md`, `docs/guide.html`, `docs/how-it-works.html` assert the file contains
   `data/pricing.json`'s `cached_date`; for the two `.md` files additionally assert the first-row
   `display` of every tier appears in the file (today Fable 5.1, Opus 5.5, Sonnet 5.5,
   Haiku 4.5 — derived at test time, never typed); include the synthetic-negative test proving
   the shape can fail. The `.html` assertions will be RED until T5 — so this task's verify runs
   only the `.md` test class by name. Class names: `MarkdownDocsLabelTests`, `HtmlDocsLabelTests`,
   `NegativeFixtureTests`.
7. `python3 bin/docs_build.py build`; stage the rebuilt deep-dive mirrors with the sources.

Acceptance:
- Every table row's numbers equal the file's (spot-checked by the verifier against the derivation
  one-liner); every label in the four edited places equals `cached_date`.
- `grep -nE "Sonnet 5([^.0-9]|$)|Opus 4\.8" docs/GUIDE.md docs/HOW-IT-WORKS.md` returns only
  lines that are historical (the "Opus 5 / historical costing" table row, or sentences
  containing superseded/historical/retained) or inside the Copilot/Codex sections — list each
  remaining hit in your report with the reason it stays.
- No sentence attributes a refusal fallback to a skill.
- `MarkdownDocsLabelTests` and `NegativeFixtureTests` pass and were red before the edits.
- `python3 bin/docs_build.py check` exits 0; `git diff --quiet -- copilot codex cursor copilot-docs data`.

Verify:
```
test -f tests/test_docs_snapshot_labels.py && python3 -m unittest discover -s tests -p 'test_docs_snapshot_labels.py' -k MarkdownDocsLabelTests -k NegativeFixtureTests -q && python3 -m unittest discover -s tests -p 'test_reference_doc.py' -q && python3 -m unittest discover -s tests -p 'test_harness_update.py' -k LiveTreeFreshnessTests -q && ! grep -rn "refusal" docs/GUIDE.md docs/HOW-IT-WORKS.md | grep -qi "skill .*fall\|falls back to an Opus" && python3 bin/docs_build.py check && git diff --quiet -- copilot codex cursor copilot-docs data && echo T4-OK
```

### T5 — Bounded refresh of docs/guide.html and docs/how-it-works.html
- id: T5
- title: Update the two legacy HTML companions' lineup tables, labels and daily-driver names; extend the label guard to them
- status: done
- model: sonnet
- depends: T4
- evidence: red-green

Files: `docs/guide.html`, `docs/how-it-works.html`, `tests/test_docs_snapshot_labels.py`
(already created by T4 — this task only makes its `HtmlDocsLabelTests` class pass; add
assertions there if the brief below needs them). The scope is PLAN D7 — bounded, not a rewrite.
Every change must be one of:

1. The lineup `<table>` in each file (guide.html ~100–105, how-it-works.html ~71–76): rows for
   the same models the markdown tables now carry after T4, numbers derived by the same one-liner,
   tier classes (`tier-fable`, `tier-opus`, `tier-sonnet`, `tier-haiku`) preserved; the Sonnet
   "intro pricing" `<span class="note">` cells are removed (the file has no intro window now —
   confirm no `intro` key exists in `data/pricing.json`).
2. The snapshot label: guide.html's `.callout` "cached `2026-07-01`" and how-it-works.html's
   `<p class="note">Prices cached 2026-07-01` → the file's `cached_date`, in the same edit as
   the tables.
3. "Opus 4.8" where it means the current daily driver (guide.html ~102, ~279, ~303;
   how-it-works.html ~73, ~87, ~147, ~180, ~203, ~247) → the Opus tier's current display
   (derive via `python3 bin/aesop_bridge.py tiers`), or the phrase "the Opus tier". Example
   bridge output lines (guide.html ~279 `strong→claude-opus-4-8, mid→claude-sonnet-5…`) are
   replaced with the command's current output.
4. "Sonnet 5" as the current workhorse (guide.html ~127, ~254–259, ~276, ~295;
   how-it-works.html ~147, ~180, ~191–192) → "Sonnet 5.5" or "the Sonnet tier"; how-it-works.html
   ~191's "Sonnet 5 intro rates applied by record date" clause goes — the engine has no intro
   windows (confirm by `grep -n intro bin/cost_report.py`).
5. "Fable 5" where it means the current frontier model (table rows, ~78 "Running Fable 5 as a
   standing default", ~249 "When Fable 5 leaves the subscription", guide.html ~93, ~101) →
   "Fable 5.1"; the slogan callouts (guide.html ~133, how-it-works.html ~153) and the
   `/polytropos:architect … Fable 5 runs ONCE` diagram line stay (PLAN D8).
6. The refusal-fallback sentences (guide.html ~303, how-it-works.html ~184) follow T4's
   rewrite: operator practice on the Opus tier, never skill behavior.
7. how-it-works.html ~248 rotting callout ("11 execution kits … 32 of 32 tasks … zero
   escalations") → one sentence: the track record is a command —
   `python3 bin/routing_scorecard.py --history` prints the cross-kit per-tier first-try and
   escalation rates for this checkout. No figure.
8. The verifier line in each file's architect section (guide.html ~49, how-it-works.html ~159):
   verifier pinned `sonnet` by default, haiku for mechanical checks (PLAN D3).

Nothing else changes: no restyling, no new sections, no dark-mode or print CSS in these two
files (that belongs to the new pitch only). Run `git diff --stat docs/guide.html
docs/how-it-works.html` and confirm the hunks map onto the eight items above.

Acceptance:
- `HtmlDocsLabelTests` passes (red before this task); the whole
  `tests/test_docs_snapshot_labels.py` module is green.
- `grep -nE "2026-07-01|intro until|Opus 4\.8|32 of 32|11 execution kits" docs/guide.html docs/how-it-works.html` is empty.
- `grep -c "Fable 5 runs once" docs/guide.html docs/how-it-works.html` is unchanged from HEAD.
- `python3 bin/docs_build.py check` exits 0 (the generator does not read these files, but the
  check must stay green anyway).

Verify:
```
python3 -m unittest discover -s tests -p 'test_docs_snapshot_labels.py' -q && ! grep -nE "2026-07-01|intro until|Opus 4\.8|32 of 32|11 execution kits" docs/guide.html docs/how-it-works.html && for f in docs/guide.html docs/how-it-works.html; do [ "$(grep -c 'Fable 5 runs once' "$f")" = "$(git show "HEAD:$f" | grep -c 'Fable 5 runs once')" ] || { echo "slogan count changed in $f"; exit 1; }; done && python3 bin/docs_build.py check && echo T5-OK
```

### T6 — Commit Phase 2 at a green boundary
- id: T6
- title: Full suite and all generator checks green, then one commit for the roster refresh
- status: done
- model: sonnet
- depends: T3, T5
- evidence: red-green

Run, from the repo root, and read the real exit statuses: `python3 -m unittest discover -s
tests` (full suite), `python3 bin/docs_build.py check`, `python3 bin/copilot_docs.py check`,
`python3 bin/sync_pricing_refs.py --check`, `python3 bin/release_gate.py check`. If anything is
red, stop and report — do not commit red. Confirm `git branch --show-current` prints
`feat/route-experiment` and that `git status --porcelain` lists only: the skill files T2 named,
the two manifests, `docs/GUIDE.md`, `docs/HOW-IT-WORKS.md`, `docs/AESOP-INTEGRATION.md`,
`docs/guide.html`, `docs/how-it-works.html`, the two new test files, rebuilt files under
`docs-site/`, and the kit's own files under `.claude/kits/sdd-docs-refresh/` and
`.claude/agents/sdd-docs-refresh-*.md` (the kit scaffolding is committed with this first
boundary). Anything else is a defect to report, not to sweep in.

Then `git add` exactly those paths and commit with ONE message in the user's convention:
subject `docs(claude): name the 5.5 defaults by tier, re-tier the verifier to sonnet, and guard
the labels` (≤ ~80 chars; adjust wording, keep the type/scope shape); a prose body, present
tense, wrapped at 80 columns, covering (a) why the old state was wrong with evidence (the
`pricing.json` row order and `9b5da6d`; the ledger's verifier precision figures AS A COMMAND,
not numbers — `python3 bin/routing_scorecard.py --history`, Role quality card), (b) what proves
the new state (`tests/test_roster_currency.py`, `tests/test_docs_snapshot_labels.py`, each
red-before-green under execute's gate; the generator checks, listed indented with their exit
codes as you actually observed them), (c) what is deliberately unfinished (Haiku 5.5 not made
the dispatch default — PLAN D2; `DOWNGRADE_TARGET` untouched; non-Claude harnesses untouched;
plugin version not bumped). Never quote a test count. End with the attribution trailer the
executing session's harness mandates — exactly as its system reminder states it, nothing
invented. Never push.

Acceptance:
- All five commands above exited 0 in this task's own run (paste the tails).
- One new commit on `feat/route-experiment`; `git status --porcelain` empty afterwards.
- `git log -1 --format=%B` shows a conventional subject, a body of prose paragraphs, and the
  mandated trailer.

Verify:
```
[ "$(git branch --show-current)" = "feat/route-experiment" ] && [ -z "$(git status --porcelain)" ] && git log -1 --format=%s | grep -qE '^(feat|fix|docs|refactor|test|chore|perf)\([a-z-]+\): ' && git log -1 --format=%B | grep -q 'Co-Authored-By:' && git diff --quiet HEAD~1 HEAD -- copilot codex cursor copilot-docs data && echo T6-OK
```

## Phase 3 — Spec-driven development, written down

### T7 — docs/SPEC-DRIVEN.md: polytropos as spec-driven development, every claim sourced
- id: T7
- title: Write docs/SPEC-DRIVEN.md, register its site page, bump the page-map test, rebuild
- status: done
- model: opus
- depends: T6
- evidence: red-green

Files: new `docs/SPEC-DRIVEN.md`; `mkdocs.yml` (one nav line); `tests/test_docs_build_adversarial.py`
(one assertion + docstring sentence); docs-site rebuild. No other file.

Audience: an engineer who knows "spec-driven development" as a phrase (write the spec, generate
or build against it, verify against the spec) and wants to know whether polytropos actually is
that or just uses the vocabulary. The answer is yes, with a specific shape, and the doc earns
that by pointing at the code at every step. Length 900–1600 words of body. Prose paragraphs
and short tables; no marketing voice; every section names the file(s) that make it true.

Read first, in this order, and quote or paraphrase only what they say:
`skills/architect/SKILL.md` (the kit: PLAN.md goal/constraints/decisions-with-rationale/
tripwires, optional `autonomy:` `budget:` `roles:` `workflow:` lines; TASKS.md fields `id` `title`
`status` `model`, self-contained brief, acceptance, verify, `evidence:` red-green/regression/
precondition, `## Phase N`, `depends:`/`independent:`; GUARDRAILS.md always written; model-pinned
agents with read-only `tools:` pins and the damage-restore practice);
`skills/execute/SKILL.md` (the orchestrator runs the verify command itself — "the implementer's
claim of success is not evidence"; verifier in fresh context; reviewer at phase ends; retry once
then `blocked`; the escalation valve carries failure evidence; the `evidence:` rule; budget
caps and `budget-stop`; NOTES.md ledger lines `outcome:` `agent:` `reviewer:` `defect:`);
`CLAUDE.md` "When executing a kit task" (the brief is authoritative; conflicts stop the task);
`bin/kit_contract.py --help` and `python3 bin/kit_contract.py demo` (one contract: graph
validation, readiness, roster, freshness of done tasks against upstream artifacts — `refresh`
re-verifies without dispatching); `python3 bin/routing_scorecard.py --history` (per-tier
first-try, Role quality, and the architect's brief-defect kinds — `contradictory-acceptance`,
`tautological-verify`, `unrunnable-verify`, `stale-pin`…: the SPEC is audited, which is the
sharpest SDD claim this repo can make); `bin/attempt_ledger.py demo` and `bin/exec_policy.py
check` (every dispatch recorded before and after; verify commands run under an execution
boundary); `docs/HOW-IT-WORKS.md` §4.3–4.4 and §6; `docs/ROLE-EXPERIMENT.md` (marginal-catch);
`docs/GUIDE.md` §6 "The track record is a command, not a number".

Required structure (h1 then h2s; the generator demotes headings, so use `#`/`##` only):

```
# Spec-driven development, the polytropos way
## The claim                      — one paragraph: what SDD means here, in the repo's own terms
## The spec is three files        — PLAN.md / TASKS.md / GUARDRAILS.md: what each pins, with the field list
## Who writes it, who runs it      — architect on the frontier tier once; implementers on pinned
                                     cheaper tiers; the task `model` field overrides the agent;
                                     aliases resolve to the tier's current default (never an id in a skill)
## Verification is against the spec, not the claim — orchestrator-run verify, fresh-context
                                     verifier, phase reviewer, red-green evidence gate, retry/blocked/escalate with evidence
## The spec itself is checked      — kit_contract graph/roster/freshness, GUARDRAILS.md layout test,
                                     brief-defect kinds in the ledger, the execution boundary and attempt ledger
## What the ledger measures         — outcome/agent/reviewer/defect lines; first-try and precision by tier;
                                     the command, not a number
## What it is not                  — no code generation from a formal spec; no claim the spec is complete;
                                     a brief that conflicts with reality stops the task; limits named honestly
## Read next                       — HOW-IT-WORKS §4.3–4.4 and §6, GUIDE §4/§6, ROLE-EXPERIMENT, the pitch
                                     (`spec-driven-pitch.html`, a printable summary of this page)
```

Honesty rules for this file: no model ids, no prices, no dates except the words "today" beside a
derivation command; no counts of kits/tasks/tests; tier words with "today"-glosses only where
needed (PLAN D1/D8); every "polytropos does X" sentence names the file or command that does it.
Where the repo deliberately does NOT do something (e.g. switch the main session's model;
auto-apply a routing change; make a role a permission), say so — those are part of the spec
discipline, not gaps to hide.

Mechanics (PLAN D5): add `    - Spec-driven development: deep-dives/spec-driven.md` under the
"Deep dives" list in `mkdocs.yml`, placed alphabetically among its neighbours (after "Routing
trends" and before "Training-data readiness"); in
`tests/test_docs_build_adversarial.py::test_page_map_has_current_expected_entries` change
`self.assertEqual(len(page_map), 40)` to 41 and append to the docstring: "then 40 -> 41 when
sdd-docs-refresh added docs/SPEC-DRIVEN.md (2026-10-23)."; run `python3 bin/docs_build.py build`
and stage `docs-site/deep-dives/spec-driven.md` and the regenerated `deep-dives/index.md`.

Acceptance:
- `docs/SPEC-DRIVEN.md` exists with exactly the eight h2 sections above (titles may be lightly
  reworded; order fixed), 900–1600 body words, and at least twelve distinct backticked
  repo paths or commands that exist (the verifier samples them).
- `grep -nE 'claude-(sonnet|haiku|opus|fable)-[0-9]|\$[0-9]|(^|[^0-9])20[0-9]{2}-[0-9]{2}-[0-9]{2}' docs/SPEC-DRIVEN.md` is empty.
- `grep -c "deep-dives/spec-driven.md" mkdocs.yml` prints 1; `python3 bin/docs_build.py check`
  exits 0; `python3 -m unittest discover -s tests -p 'test_docs_build_adversarial.py' -q` and
  `-p 'test_docs_site.py'` green (red before: the page-map count and nav coverage both failed with the new source present).

Verify:
```
test -f docs/SPEC-DRIVEN.md && [ "$(grep -c '^## ' docs/SPEC-DRIVEN.md)" = "8" ] && ! grep -nE 'claude-(sonnet|haiku|opus|fable)-[0-9]|\$[0-9]|(^|[^0-9])20[0-9]{2}-[0-9]{2}-[0-9]{2}' docs/SPEC-DRIVEN.md && [ "$(grep -c 'deep-dives/spec-driven.md' mkdocs.yml)" = "1" ] && test -f docs-site/deep-dives/spec-driven.md && python3 bin/docs_build.py check && python3 -m unittest discover -s tests -p 'test_docs_build_adversarial.py' -q && python3 -m unittest discover -s tests -p 'test_docs_site.py' -q && echo T7-OK
```

### T8 — Pointers to the spec-driven doc from README, GUIDE, HOW-IT-WORKS and the concepts page
- id: T8
- title: Link docs/SPEC-DRIVEN.md from the four entry documents and rebuild
- status: done
- model: haiku
- depends: T7
- evidence: red-green

Files: `README.md`, `docs/GUIDE.md`, `docs/HOW-IT-WORKS.md`,
`docs-site/concepts/architect-execute-measure.md`, docs-site rebuild. One sentence or bullet
each, no restatement of the doc:

1. `README.md`, "What you get" section, the paragraph beginning "The detailed mechanics, limits,
   and examples live in" — append a sentence: "Why this is spec-driven development — the
   architect writes the spec, pinned cheaper models execute it, verification is against the spec —
   is in [docs/SPEC-DRIVEN.md](docs/SPEC-DRIVEN.md)." Claude-only wording; do not touch the
   harness table or Copilot/Codex sentences.
2. `docs/GUIDE.md`, the `### /polytropos:architect <task>` section, after the bullet list of
   kit files: one line "The kit IS the spec: [SPEC-DRIVEN.md](SPEC-DRIVEN.md) explains the
   discipline end to end."
3. `docs/HOW-IT-WORKS.md` §4.3, after the artifact table: the same one-liner.
4. `docs-site/concepts/architect-execute-measure.md`, the "## Related" list: add
   `- [Deep dive: spec-driven development](../deep-dives/spec-driven.md) — the kit as a spec, and
   how verification is held to it rather than to the implementer's claims.` This is a hand page
   (editable) — it must contain no model display name (`tests/test_docs_site_skeleton.py`).
5. `python3 bin/docs_build.py build`; stage the rebuilt mirrors of GUIDE and HOW-IT-WORKS.

Acceptance:
- Each of the four files contains exactly one link to the spec-driven doc (relative path as
  given); `python3 bin/docs_build.py check` exits 0; the rebuilt
  `docs-site/deep-dives/{guide,how-it-works}.md` link to `spec-driven.md` (the generator
  rewrites `SPEC-DRIVEN.md` → `spec-driven.md`).
- `python3 -m unittest discover -s tests -p 'test_docs_site_skeleton.py' -q` and `-p 'test_docs_site_hand_pages.py'` green.

Verify:
```
[ "$(grep -c 'docs/SPEC-DRIVEN.md' README.md)" = "1" ] && [ "$(grep -c 'SPEC-DRIVEN.md' docs/GUIDE.md)" = "1" ] && [ "$(grep -c 'SPEC-DRIVEN.md' docs/HOW-IT-WORKS.md)" = "1" ] && [ "$(grep -c 'deep-dives/spec-driven.md' docs-site/concepts/architect-execute-measure.md)" = "1" ] && grep -q 'spec-driven.md' docs-site/deep-dives/guide.md && grep -q 'spec-driven.md' docs-site/deep-dives/how-it-works.md && python3 bin/docs_build.py check && python3 -m unittest discover -s tests -p 'test_docs_site_skeleton.py' -q && python3 -m unittest discover -s tests -p 'test_docs_site_hand_pages.py' -q && echo T8-OK
```

### T9 — The elevator pitch: docs/spec-driven-pitch.html, 3–5 printed pages, verified by a test
- id: T9
- title: Write the self-contained light/dark print-ready pitch and tests/test_spec_driven_pitch.py
- status: done
- model: opus
- depends: T7
- evidence: red-green

Files: new `docs/spec-driven-pitch.html`, new `tests/test_spec_driven_pitch.py`. Nothing else.
The main session publishes the file as a private claude.ai artifact afterwards; this task only
writes it (PLAN Goal).

Read `docs/SPEC-DRIVEN.md` (T7) and the same sources it cites; the pitch is the short, persuasive
form of that page and must not contradict it. Read `docs/guide.html` lines 1–70 for the house
style and copy its conventions (PLAN D6): a single inline `<style>`; the same custom properties
`--bg --ink --muted --line --accent --card --fable --opus --sonnet --haiku` on `:root`; body
`17px/1.65 Georgia, 'Times New Roman', serif`; `.wrap { max-width: 860px }`; `.kicker`,
`.callout`, `.note`, `.tier-*` classes; `<meta charset>` and viewport; `<title>` of two to four
words (e.g. "polytropos — spec-driven development"). No `<script>`, no `<link>`, no `@import`,
no external font, no image. Additions the legacy files lack and the user asked for:

- Dark mode: `@media (prefers-color-scheme: dark) { :root { … } }` redefining the same tokens
  (dark `--bg`, light `--ink`, adjusted `--line`/`--card`/code backgrounds), plus the code/table/
  callout backgrounds switched to token-based colors so both themes render legibly. Also give
  `body` an explicit `background: var(--bg)`.
- Print: `@media print { .page { break-after: page; page-break-after: always; }
  .page:last-of-type { break-after: auto; page-break-after: auto; } body { font-size: 11.5pt; }
  .wrap { max-width: none; padding: 0; } }` and `@page { margin: 18mm; }` — so the document
  prints as exactly one sheet per `<section class="page">`.
- Structure: a `<main class="wrap">` holding 4 `<section class="page">` elements (3–5 allowed;
  4 is the target): (1) the claim and the one-sentence loop — architect writes the spec, pinned
  models execute, verification against the spec, the ledger measures; (2) the spec — what
  PLAN.md / TASKS.md / GUARDRAILS.md pin, shown as a compact table and a short TASKS.md excerpt
  in a `<pre>` (fields `id`/`title`/`status`/`model`/brief/acceptance/verify/`evidence:`/
  `depends:`); (3) verification and the ledger — orchestrator-run verify, fresh-context
  verifier, phase reviewer, red-green gate, escalation with evidence, `outcome:`/`defect:` lines,
  and the sentence that the architect's own brief defects are measured; (4) why it is cheap and
  honest — frontier once, tiers by alias, "the track record is a command, not a number", the
  limits ("what it is not"), and a closing "run it" block with the three commands
  `/polytropos:architect <task>`, `/polytropos:execute <slug>`,
  `python3 bin/routing_scorecard.py --history`.
- Each section ≤ 650 words of visible text; whole document 1400–2800 visible words (the test's
  proxy for 3–5 US-Letter pages at this type size — PLAN D6).
- Truth: every `bin/<name>.py` you mention must exist; every `/polytropos:<skill>` must be a
  directory under `skills/`; the only kit file names are `PLAN.md`, `TASKS.md`, `GUARDRAILS.md`,
  `NOTES.md`; no model id (`claude-…`); tier words, with at most one "today" gloss naming the
  current tier defaults, and if that gloss or anything else carries a `$` figure, the same
  section carries the sentence "Prices are a labeled snapshot of `data/pricing.json` (cached
  <cached_date>)". The simplest honest choice: no dollar figures at all, and say the costs are
  computed at run time. No kit/task/test counts, no percentages.
- A visible footer line: "Long form: docs/SPEC-DRIVEN.md · Source: github.com/agentmc15/polytropos".

`tests/test_spec_driven_pitch.py` (stdlib; `html.parser` to extract visible text; live-tree):
- `StructureTests`: file exists; `<!DOCTYPE html>` and `<meta charset`; exactly one `<style>`;
  no `<script`, `<link`, `@import`, `url(` with `http`; contains `prefers-color-scheme: dark`,
  `@media print`, `break-after: page`; the count of `<section class="page"` is between 3 and 5
  inclusive; `<title>` present and ≤ 60 chars.
- `LengthTests`: visible-text word count per section ≤ 650; total between 1400 and 2800.
- `TruthTests`: every regex match `bin/([a-z_]+\.py)` resolves to an existing file under `bin/`;
  every `/polytropos:([a-z-]+)` resolves to `skills/<name>/SKILL.md`; no match for
  `claude-(fable|opus|sonnet|haiku)-\d`; if the visible text contains `$` followed by a digit,
  the visible text also contains `data/pricing.json`'s `cached_date` (read from the file);
  no match for `\b\d+ (kits|tasks|tests)\b` or `\d+%`; the text contains `SPEC-DRIVEN.md`.
- `NegativeFixtureTests`: run the same checks over an in-memory string that (a) has 2 sections,
  (b) names `bin/does_not_exist.py`, (c) has `$5` with no label — each must raise
  `AssertionError`, proving the checks can fail. Structure the checker as module-level functions
  taking `(text, repo_root)` so both the live test and the negative fixtures share them.

Acceptance:
- `python3 -m unittest discover -s tests -p 'test_spec_driven_pitch.py' -q` passes (red before: the file did not
  exist); `python3 bin/docs_build.py check` still exits 0 (the generator ignores the file);
  `git status --porcelain` shows exactly the two new files.
- The verifier opens the file's text and confirms every "polytropos does X" sentence matches
  `skills/architect/SKILL.md` / `skills/execute/SKILL.md` / `docs/SPEC-DRIVEN.md`; any claim
  without a source is a FAIL.

Verify:
```
test -f tests/test_spec_driven_pitch.py && python3 -m unittest discover -s tests -p 'test_spec_driven_pitch.py' -q && [ "$(grep -c '<section class="page"' docs/spec-driven-pitch.html)" -ge 3 ] && [ "$(grep -c '<section class="page"' docs/spec-driven-pitch.html)" -le 5 ] && ! grep -qE '<script|<link|@import' docs/spec-driven-pitch.html && grep -q 'prefers-color-scheme: dark' docs/spec-driven-pitch.html && grep -q '@media print' docs/spec-driven-pitch.html && python3 bin/docs_build.py check && echo T9-OK
```

### T10 — Commit Phase 3 at a green boundary
- id: T10
- title: Full suite and generator checks green, then one commit for the spec-driven docs and pitch
- status: done
- model: sonnet
- depends: T8, T9
- evidence: red-green

Same procedure as T6: run the full suite and the four generator/gate checks from the repo root,
read real exit statuses, stop if red. `git status --porcelain` must list only
`docs/SPEC-DRIVEN.md`, `docs/spec-driven-pitch.html`, `mkdocs.yml`,
`tests/test_docs_build_adversarial.py`, `tests/test_spec_driven_pitch.py`, `README.md`,
`docs/GUIDE.md`, `docs/HOW-IT-WORKS.md`, `docs-site/concepts/architect-execute-measure.md`,
rebuilt files under `docs-site/deep-dives/`, and the kit's own `TASKS.md`/`NOTES.md` under
`.claude/kits/sdd-docs-refresh/`. One commit, subject on the pattern
`docs(sdd): document polytropos as spec-driven development, with a printable pitch`; body: why
(the framing existed only implicitly across HOW-IT-WORKS/GUIDE; the new page sources every claim),
what proves it (`tests/test_spec_driven_pitch.py` — what it asserts, including the page-count
proxy and the truth checks; the page-map test moved 40 → 41; `docs_build.py check` exit 0), what
is unfinished (the artifact is published by the main session, not the repo; the page-count
check is a word-count proxy, not a render). Mandated trailer only. Never push.

Acceptance and verify: as T6.

Verify:
```
[ "$(git branch --show-current)" = "feat/route-experiment" ] && [ -z "$(git status --porcelain)" ] && git log -1 --format=%s | grep -qE '^(feat|fix|docs|refactor|test|chore|perf)\([a-z-]+\): ' && git log -1 --format=%B | grep -q 'Co-Authored-By:' && git diff --quiet HEAD~1 HEAD -- copilot codex cursor copilot-docs data && echo T10-OK
```

## Phase 4 — Closeout

### T11 — Reconcile the inventory and leave the tree green and clean
- id: T11
- title: Mark every INVENTORY.md row fixed or deferred, run every check once more, commit if anything moved
- status: done
- model: sonnet
- depends: T10
- evidence: red-green

Open `.claude/kits/sdd-docs-refresh/INVENTORY.md` and, for every row under "## Stale items",
confirm against the live file that the stale text is gone (`grep -nF '<stale text>' <file>` must
be empty, or the line must now sit in an explicitly historical sentence) and append a new last
column `Status` with `fixed (T<n>)`; where it was not fixed, `deferred: <reason>` — the only
acceptable reasons are PLAN's out-of-scope items (non-Claude surface, pricing row order,
`DOWNGRADE_TARGET`, plugin version) or a test pin you name. A row with neither is a defect:
fix it in the right source (respecting every fence) or report it as blocked. Then add a final
section `## Closeout` listing: the commands you ran and their exit codes (indented), the
branch, and the two or three commit shas this kit produced.

Then run, from the repo root: `python3 -m unittest discover -s tests`, `python3 bin/docs_build.py
check`, `python3 bin/copilot_docs.py check`, `python3 bin/sync_pricing_refs.py --check`,
`python3 bin/release_gate.py check`, `python3 bin/harness_update.py check` (read-only; its `data`
section must say the README label is `ok`; `claude`/`copilot` install drift is pre-existing and
not this kit's concern — report it, do not act on it), and
`python3 bin/kit_contract.py graph --kit .claude/kits/sdd-docs-refresh`. If any source file moved
during reconciliation, rebuild and commit once more (`chore(sdd-docs-refresh): close the
inventory …`), same convention and trailer rules as T6. If nothing moved but INVENTORY.md and
the kit's own state, commit that as the closing boundary. Never push.

Acceptance:
- Every "## Stale items" row carries a `Status` of `fixed (T<n>)` or `deferred: <reason>`; no
  other value; `grep -c 'deferred:'` count is stated in the report with each reason.
- All seven commands above exited as expected (0, or 3 for `harness_update` with only the
  pre-existing install drift named) — paste the tails.
- `git status --porcelain` empty; branch `feat/route-experiment`; nothing pushed.

Verify:
```
grep -q '^## Closeout' .claude/kits/sdd-docs-refresh/INVENTORY.md && ! grep -nE '^\| [0-9]+ \|' .claude/kits/sdd-docs-refresh/INVENTORY.md | grep -vE 'fixed \(T[0-9]+\)|deferred: ' && [ -z "$(git status --porcelain)" ] && [ "$(git branch --show-current)" = "feat/route-experiment" ] && python3 bin/docs_build.py check && python3 bin/copilot_docs.py check && python3 bin/sync_pricing_refs.py --check && python3 bin/release_gate.py check | grep -q 'verdict: OK' && echo T11-OK
```
