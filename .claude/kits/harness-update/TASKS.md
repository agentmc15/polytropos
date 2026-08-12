# harness-update — tasks

Dispatch preamble: T1 → T2 → T3 → T5 are strictly serial (same primary file,
`bin/harness_update.py`, all pinned sonnet) — a warm-cluster candidate for one continued
implementer. T4 is independent and can run in parallel with any of them. T6 continues the
same file but is pinned opus, so it gets a fresh dispatch. Statuses: pending | in-progress |
done | blocked.

## Phase 1 — Read-only check engine

### T1 — Engine scaffold + Claude section (reuse plugin_staleness)
- id: T1
- title: Scaffold bin/harness_update.py with the Claude-cache section
- status: done
- model: sonnet
- independent: yes

Create `bin/harness_update.py` (new file) and `tests/test_harness_update.py` (new file).
Nothing else may be created or edited by this task.

Engine shape (argparse, stdlib only, `main(argv=None)` returning an int exit code, ending
with `if __name__ == "__main__": raise SystemExit(main())` — match `bin/plugin_staleness.py`'s
general structure):

- Subcommands this task creates: `check` (flags: `--repo-root`, `--installed-manifest`,
  `--copilot-home`, `--codex-home`, `--json`). Later tasks add `apply` and `demo` — leave
  the parser easy to extend.
- Module docstring states the contract: check is strictly read-only; the engine never
  writes under `~/.claude`; home-dir defaults live only in argparse defaults / `cmd_*`
  handlers.
- Sibling-module loader: `bin/` is not a package, so load reused modules with the repo's
  established pattern — `importlib.util.spec_from_file_location` on
  `Path(__file__).resolve().parent / "<name>.py"` (see `tests/test_harness_select.py`'s
  `_load` for the canonical shape). Provide one helper, e.g. `_load_sibling(name)`, used
  for every reuse in this kit. Never copy logic out of the reused modules.
- Claude section: reuse `bin/plugin_staleness.py`. It already reads
  `.claude-plugin/plugin.json` + `marketplace.json` for identity, resolves the installed
  entry from an `installed_plugins.json` manifest (its `resolve_installed_entry` never
  raises; absent/malformed → not installed), compares repo HEAD (read from `.git/HEAD`
  directly, no git binary) against the manifest's `gitCommitSha`, diffs files under its
  `COMPARE_GLOBS`, and classifies `IN SYNC` / `SHA STALE` / `DRIFTED` with a printed
  remedy split across `_REMEDY_CLI_A`/`_REMEDY_CLI_B`. Call its functions; render its
  result as the `claude` section of the check card (human) and of the `--json` object.
  Pass `--installed-manifest` and `--repo-root` through. Never execute the remedy.
- `--json` emits one object with top-level keys `claude`, `copilot`, `codex`, `data`,
  plus `"status"` (`"fresh"` or `"drift"`) and `"exit"` (0 or 3). Sections not yet
  implemented in this task appear as `{"status": "not-implemented"}` placeholders and do
  NOT count as drift; T5 removes the placeholders and a test added in T5 proves none
  remain.
- Exit codes: 0 when nothing checked reports drift, 3 on any drift (`SHA STALE` counts as
  drift; "not installed" does not — absence is not failure).

Tests (mirror `tests/test_harness_select.py` conventions exactly): `BIN_DIR` +
`_load("harness_update")` loader; every test builds temp dirs via
`tempfile.TemporaryDirectory()`; never reads the real `~/.claude`; asserts (a) a synthetic
repo + synthetic manifest in temp dirs produces the claude section with plugin_staleness's
statuses, (b) not-installed exits 0, sha-mismatch exits 3, (c) a source-introspection guard
over the engine's pure functions (everything except the `DEFAULT_*` constants and `cmd_*`
handlers): `assertNotIn("Path.home", ...)`, `assertNotIn("subprocess", ...)`,
`assertNotIn("urlopen", ...)` — same idiom as `tests/test_codex_setup.py`.

Gotcha: `plugin_staleness.py` defaults its manifest via `os.path.expanduser`; your
argparse default may do the same, but tests must always pass the flag.

Acceptance: `check --json` on a synthetic fixture yields the four top-level section keys +
`status`/`exit`; read-only proven (fixture tree byte-identical before/after check — assert
with a recursive digest in the test, not by trust); introspection guard present and green.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && python3 -m unittest discover -s tests -p 'test_harness_update.py' -v
```

### T2 — Copilot install-state section
- id: T2
- title: Read-only Copilot bundle comparator
- status: done
- model: sonnet
- depends: T1

Edit only `bin/harness_update.py` and `tests/test_harness_update.py`.

Add the `copilot` section to `check`. Semantics mirror `harness_select.install_copilot`'s
inventory WITHOUT writing: sources are `copilot/.github/agents/*.agent.md` (required core —
if the repo bundle's agents dir is missing/empty, report a repo-side error state, mirroring
install_copilot's `FileNotFoundError` contract, and count it as drift) and every file under
`copilot/.github/skills/` (rglob; missing/empty tolerated). For each source file, compute
the placeholder-resolved content — reuse `harness_select`'s `PLACEHOLDER` constant and its
resolution helper (`_resolved_bytes(source, repo_root)`; if you find the legacy text-replace
form is what `install_copilot` uses, match whichever helper resolves bytes — the reused
module is authoritative) — then compare against `<copilot-home>/agents/<filename>` or
`<copilot-home>/skills/<relative-path>`:

- destination missing → `missing`
- byte-equal to resolved source → `up-to-date`
- else → `differs`

A `<copilot-home>` that doesn't exist at all → section status `not installed` (exit 0
contribution). Any `missing`/`differs` → drift (exit 3). Report counts per state plus the
per-file list in `--json`; the human card prints counts and up to a handful of example
paths, not the full list.

Tests: reuse the fixture idiom from `tests/test_harness_select.py` — module-level fake
agent/skill text containing `{{POLYTROPOS_ROOT}}` twice plus surrounding text, builders
like `_make_fake_repo_root` / `_add_fake_skill` (define local copies in the new test file;
do not import another test module). Cover: fresh install → all `up-to-date`, exit 0; edited
destination → `differs`, exit 3; extra destination file the bundle doesn't know → ignored
(the comparator audits the bundle's files, not the user's whole home); absent home → `not
installed`, exit 0; and the read-only digest assertion extended over the copilot home.

Acceptance: all four states reachable in tests; zero writes proven; placeholder resolution
comes from `harness_select` by import (grep proves no second `{{POLYTROPOS_ROOT}}` literal
constant is defined in `harness_update.py` — reference the imported one).

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && python3 -m unittest discover -s tests -p 'test_harness_update.py' -v
```

### T3 — Codex section (reuse doctor_codex)
- id: T3
- title: Codex install-state via harness_select.doctor_codex
- status: done
- model: sonnet
- depends: T2

Edit only `bin/harness_update.py` and `tests/test_harness_update.py`.

Add the `codex` section: call `harness_select.doctor_codex` (read-only by construction —
it runs `plan_codex_setup` over all components with `legacy_copy=True,
refresh_managed=False`) with the `--codex-home` and `--repo-root` seams. Summarize its
action states (`install` / `up-to-date` / `managed-update` / `unmanaged` / `conflict`) as
counts, surface its `ownership_manifest` field (`present` / `absent` / `invalid`), and pass
through its session note. Drift mapping: any `install`, `managed-update`, or `conflict` →
drift; `unmanaged` alone is a warning, not drift (it is doctor's "managed copy matches, no
refresh requested" / non-canonical-file state — report it plainly, never hide it); an
absent codex home → `not installed`, exit 0. If `doctor_codex`'s actual return shape
differs from this description, the function is authoritative — adapt the summary, keep the
drift mapping's spirit (writes-pending or conflicts = drift), and note the delta in
NOTES.md.

Tests: build a temp codex home + temp repo root with a minimal codex bundle (reuse the
fixture approach of `tests/test_codex_setup.py` — `_write`/`_fake_repo` style local
helpers). Cover: fresh (nothing installed) → drift with `install` actions counted; fully
installed and matching → exit 0; a `conflict` (e.g. unresolved `{{POLYTROPOS_ROOT}}`
literal in a destination, or an edited managed file) → drift; absent home → `not
installed`, exit 0. Extend the read-only digest assertion over the codex home.

Acceptance: section renders in human and `--json` forms; drift mapping as above; no logic
copied out of `harness_select.py`.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && python3 -m unittest discover -s tests -p 'test_harness_update.py' -v
```

### T4 — Bring docs/COPILOT-HARNESS.md snapshot current (found drift)
- id: T4
- title: Refresh the Copilot pricing snapshot docs to cached_date 2026-08-11
- status: done
- model: sonnet
- independent: yes

Real drift found 2026-08-11: `data/pricing.copilot.json` has `"cached_date":
"2026-08-11"` (Luna repriced ~5x down, Terra ~20% down, cache-write rates added across the
GPT-5.6 family, Sol long-context cache-write added), but `docs/COPILOT-HARNESS.md` still
says its table is "a **snapshot of `data/pricing.copilot.json`, cached `2026-07-25`**" and
its hand-maintained table (starting around the section that label introduces) still carries
the old numbers. `docs/COPILOT-WORKFLOW.md` also carries snapshot prose near its top —
check whether it names a date or stale numbers and update it the same way if so.

Task: regenerate the hand-maintained snapshot label + table in `docs/COPILOT-HARNESS.md`
so that (a) the label names `2026-08-11`, and (b) every numeric cell equals the
corresponding field in `data/pricing.copilot.json` AS IT IS NOW — read the data file and
derive each cell; never type a price from memory or from this brief. Keep the table's
existing column structure and any surrounding honesty prose (the "snapshot, not a source
of truth" framing and the refresh runbook) intact. Do not touch `data/pricing.copilot.json`
itself, any other pricing file, or `copilot-docs/` generated files. If a table cell exists
that has no corresponding data-file field (or vice versa in a row the table clearly means
to show), stop and report rather than inventing a value.

RATIFIED MID-RUN (architect, 2026-08-11, after `defect:` T4 contradictory-acceptance was
logged): the "do not touch `copilot-docs/` generated files" fence above meant no HAND-edits.
Editing this doc changes a copilot-docs source set, so re-running the sanctioned generator
(`python3 bin/copilot_docs.py`) to refresh `sources_sha256` hashes is IN scope for this task
and for any later adjudicated edit to this doc — that is what "full suite green" requires.

Acceptance: the string `2026-07-25` no longer appears as this snapshot's label in
`docs/COPILOT-HARNESS.md`; the string `2026-08-11` does; spot-checkable equality — the
implementer's report must include a cell-by-cell trace (data-file field → table cell) for
at least Luna and Terra rows; full suite green (the copilot docs-content tests must still
pass).

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && grep -n "2026-08-11" docs/COPILOT-HARNESS.md && ! grep -n "cached \`2026-07-25\`" docs/COPILOT-HARNESS.md && python3 -m unittest discover -s tests -q
```

### T5 — Data-surfaces section, aggregate card, demo, live-tree gate
- id: T5
- title: Data freshness section + aggregate + demo + live-tree label gate
- status: done
- model: sonnet
- depends: T3, T4

Edit only `bin/harness_update.py` and `tests/test_harness_update.py`.

Add the `data` section to `check`, the final aggregate, and the `demo` subcommand:

1. **Pricing ages.** For each of `data/pricing.json`, `data/pricing.copilot.json`,
   `data/pricing.codex.json` (under `--repo-root`): read `cached_date`, report age in days
   against today's date. Age is a fact; older than 60 days additionally prints
   "re-verify against source" (the route skill's vendored-snapshot threshold — a flag,
   never an auto-refresh, and NOT drift for exit-code purposes).
2. **Generated mirrors.** Reuse by import: `sync_pricing_refs.check(root)` semantics
   (stale list; its CLI exits 1 on drift — call the pure function, not the CLI) and
   `sync_codex_surfaces.sync(root, "check")` (returns the stale list; source errors raise —
   surface them as section errors). Any stale mirror → drift.
3. **Docs snapshot labels (PLAN D7).** `data/pricing.json`'s `cached_date` string must
   appear in `README.md`; `data/pricing.copilot.json`'s in `docs/COPILOT-HARNESS.md`.
   Missing → drift, reported as "docs snapshot label stale — update the doc together with
   the data file (CLAUDE.md rule)". `data/pricing.codex.json` gets the verbatim line
   "codex partner doc carries no numeric snapshot by design — nothing to check", never a
   drift flag.
4. **Aggregate.** Remove the T1 placeholders; `status: fresh|drift` derives from the four
   sections; human card prints the four sections then one verdict line naming which
   sections drifted. Add a test asserting the JSON contains no `"not-implemented"` value
   anywhere.
5. **`demo` subcommand.** Synthetic smoke in a `tempfile.mkdtemp` tree it builds and
   removes itself: a fake repo root (minimal pricing files with `cached_date`, a fake
   copilot/codex bundle) plus fake homes, shown twice — once fresh (exit-0 card) and once
   with seeded drift (stale label + edited copilot file), printing both cards. No real
   repo, no real homes, exit 0 always. This is the CLAUDE.md run-line smoke.
6. **Live-tree gate (test, not engine).** In `tests/test_harness_update.py`, a
   `LiveTreeFreshnessTests` class (precedent: `tests/test_pricing_refs.py`'s
   `LiveTreeMirrorTests`) asserting against the REAL repo tree: each pricing file's
   `cached_date` appears in its partner doc per D7. This is the permanent regression gate
   for the T4 drift — it must FAIL if someone bumps a `cached_date` without touching the
   partner doc. It reads the live tree only; it never writes.

Tests for 1–5 use synthetic temp trees as in T1–T3; date-dependent age tests inject a fixed
today (pass a `now`/`today` parameter into the pure function — never mock global time).

Acceptance: all four sections real; exit 3 iff any section drifts; demo runs clean with no
real-file access (digest-check the real repo root is untouched is NOT needed — demo never
receives real paths by construction; assert its default root is the temp tree);
live-tree gate green on the current tree and proven able to fail (temporarily broken
fixture variant of the same assertion logic run against a synthetic stale tree).

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && python3 -m unittest discover -s tests -p 'test_harness_update.py' -v && python3 bin/harness_update.py demo && python3 -m unittest discover -s tests -q
```

## Phase 2 — Apply

### T6 — apply subcommand (delegated writers only)
- id: T6
- title: apply — refresh Copilot/Codex homes and repo mirrors, print Claude remedy
- status: done
- model: opus
- depends: T5

Edit only `bin/harness_update.py` and `tests/test_harness_update.py`.

Add `apply` with flags `--repo-root`, `--copilot-home`, `--codex-home`, `--dry-run`,
`--only {claude,copilot,codex,mirrors}` (repeatable; default = all four), `--json`.

Per target, delegation only (PLAN D3/D4 — every write goes through the existing writer;
`harness_update.py` itself contains zero new file-write logic for homes):

- **copilot**: call `harness_select.install_copilot` with the resolved home/repo-root
  (honoring its dry-run parameter if it has one — read the signature; if its dry-run is
  flag-level not parameter-level, gate the call behind `--dry-run` yourself and compute
  the would-write list via the T2 comparator instead). Report the dest list. State in the
  human output that copilot installs overwrite in place (inherited, documented behavior).
- **codex**: call the legacy `install_codex` (no-clobber semantics; returns
  `(dest, action)` tuples with `action ∈ {install, up-to-date, skip-differs}`). Report
  counts per action; every `skip-differs` path is listed explicitly with the line
  "preserved — user file differs; resolve via harness_select install --harness codex if
  intended". Never force, never delete.
- **mirrors**: `sync_pricing_refs.sync(root)` and `sync_codex_surfaces.sync(root,
  "build")`; report which files were rewritten (both return/print their touched sets —
  capture and count).
- **claude**: NEVER a write. Print the same remedy `check` prints (from
  `plugin_staleness`), plus "(restart to apply)". In `--json`, the claude target carries
  `{"action": "remedy-printed"}` — grep-proof that no branch of apply writes under any
  path containing `.claude`.
- `--dry-run`: no target writes anything; print the would-do plan. Prove with the digest
  idiom over both temp homes and the repo fixture.

Exit code: 0 on success (including "nothing to do"), 1 on any raised writer error
(surfaced, not swallowed).

Tests: temp fixture homes + fixture repo as before. Cover: full apply on a drifted fixture
brings a follow-up `check` to exit 0 EXCEPT claude (assert claude still reports its drift
and the remedy was printed — apply must not have "fixed" it); skip-differs preserved
byte-for-byte; dry-run writes nothing; `--only mirrors` touches neither home (digest);
apply never creates any path under a fixture `.claude` dir seeded as a canary in the temp
tree (assert the canary's digest unchanged).

Acceptance: check→apply→check round-trip on fixtures goes drift→fresh for
copilot/codex/mirrors while claude stays print-only; introspection guard still green; the
string `.claude` appears in apply's code only in the remedy/reporting strings, never in a
write path (verifier will grep).

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && python3 -m unittest discover -s tests -p 'test_harness_update.py' -v && python3 -m unittest discover -s tests -q
```

## Phase 3 — Skill surface and wiring

### T7 — skills/update/SKILL.md
- id: T7
- title: The /polytropos:update skill
- status: done
- model: sonnet
- depends: T6

Create `skills/update/SKILL.md` only. Frontmatter exactly two-or-three fields per repo
convention (no `model:` pin ever):

```yaml
---
name: update
description: Check and refresh everything this repo installs into its harnesses — Claude plugin cache staleness, Copilot and Codex bundle drift, generated pricing mirrors, and docs snapshot freshness. Use when the user asks to update or refresh the plugin or a harness install, asks whether installs or pricing docs are stale, or after pulling or merging changes into this repo. Args: optional "apply" to refresh after checking (check-only is the default).
allowed-tools: Bash, Read
---
```

Body must state, in this order:

1. Engine resolution, engine form (the `skills/repo-bench/SKILL.md` wording): use
   `${CLAUDE_PLUGIN_ROOT}/bin/harness_update.py`; if the variable is unset, resolve
   `../../bin/harness_update.py` relative to this SKILL.md to an absolute path before
   shelling out (bash cwd is not the skill dir).
2. **Check-first law (PLAN D8), stated as binding:** always run `check` first and report
   its card. Run `apply` only when the user has explicitly asked for a refresh in this
   conversation — being invoked to look is not consent to write. `--dry-run` is the
   preview when intent is unclear.
3. What apply can and cannot do: refreshes Copilot home (overwrite-in-place, stated),
   Codex home — PER-CHANNEL (corrected at P2 review; this wording is load-bearing):
   `~/.codex/prompts/*.md` are plugin-generated mirrors, OVERWRITTEN in place with every
   differing rewrite listed; `AGENTS.md` and skill dirs are no-clobber (`skip-differs`
   preserved and listed, only when something actually was preserved); project-scope agent
   TOMLs and the modern plugin component are OUTSIDE apply's reach — the card names this
   coverage limit and points at `harness_select install --harness codex` — and repo
   generated mirrors; NEVER writes under `~/.claude`. For a stale Claude plugin cache,
   relay the framing line AND the remedy commands the engine prints TOGETHER (never the
   remedy alone — its text opens "stale install", and only the framing line makes it
   conditional on what check actually found; apply itself determines nothing), note they
   take effect on restart, and run them via Bash only on the user's explicit go-ahead.
   Card-reading gloss the skill must give: the codex `install:` count comes from
   install_codex's own return shape and includes overwrites — the real overwrite signal
   is the `prompts differing before this run: N` line beneath it.
4. What check cannot do: pricing NUMBERS and docs snapshot TABLES are never auto-edited —
   a stale `cached_date` or docs label means a human refresh from the source, together in
   one change (CLAUDE.md rule). Point at the refresh runbooks (`README.md` for
   pricing.json, `docs/COPILOT-HARNESS.md`'s own runbook lines for the copilot file).
5. Reading the card: exit 3 = drift somewhere (the card names which section); "not
   installed" is absence, not failure; `unmanaged` on codex is a warning to mention, not
   an alarm.
6. Two consumer warnings (added at P2 re-review): `check --json` and `apply --json` are
   DIFFERENT envelopes (check: four sections + status/exit; apply: dry_run/targets/
   results/errors/status/exit — two parsers, by design), and BOTH embed absolute home
   paths (install_path, codex destinations, prompts_overwritten, skip_differs) — scrub
   before pasting either one anywhere outward.

Acceptance: file exists with exactly the frontmatter fields above; body covers points 1–5;
no absolute home paths, no prices, no model ids anywhere in it; suite green.

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && python3 -c "
import re,sys; t=open('skills/update/SKILL.md').read()
fm=re.match(r'---\n(.*?)\n---\n', t, re.S); assert fm, 'no frontmatter'
keys=[l.split(':')[0] for l in fm.group(1).splitlines() if ':' in l]
assert keys==['name','description','allowed-tools'], keys
assert 'CLAUDE_PLUGIN_ROOT' in t and 'check' in t and 'apply' in t
assert '/Users/' not in t, 'home path leak'
print('skill shape ok')" && python3 -m unittest discover -s tests -q
```

### T8 — CLAUDE.md run-lines + invariant, KIT_SENTINELS entry
- id: T8
- title: Wire harness-update into CLAUDE.md and the guardrails layout test
- status: done
- model: haiku
- depends: T7

Three small edits, nothing else:

1. `CLAUDE.md` "How to run things" block — add exactly two lines, matching the block's
   existing comment style:
   `python3 bin/harness_update.py check           # all-harness freshness card (read-only; exit 3 on drift; lands with the harness-update kit)`
   `python3 bin/harness_update.py demo            # synthetic check/apply smoke — temp trees only, no real homes`
2. `CLAUDE.md` Invariants — add one bullet, verbatim:
   `**\`bin/harness_update.py\` check is strictly read-only; apply writes only the Copilot/Codex homes via \`harness_select\`'s own writers plus the repo's generated mirrors — never \`~/.claude\` (the remedy is printed, never executed), never pricing numbers or docs tables.** Tests use temp fixture homes only.`
3. (Added at P2 remediation, cosmetic; location corrected at P2 re-review) In
   `bin/harness_update.py`, the stale text is in the APPLY SUBPARSER'S OWN `help=` string
   (the `add_parser("apply", help=...)` call, around line 1290 — NOT `--codex-home`'s
   help, which correctly reads "Codex home directory (default: ~/.codex)"). Change its
   "Codex home (no-clobber)" phrase to "Codex home (prompts overwrite in place;
   AGENTS.md/skills no-clobber)". Rerun
   `python3 -m unittest discover -s tests -p 'test_harness_update.py' -q` after.
4. `tests/test_guardrails_layout.py` `KIT_SENTINELS` dict — add the entry:
   `"harness-update": "never a write under \`~/.claude\` — the remedy is printed, never executed",`
   (This substring already exists verbatim in `.claude/kits/harness-update/GUARDRAILS.md`;
   do not edit GUARDRAILS.md.)

Constraint: `CLAUDE.md` must stay ≤ 16,000 bytes (`ClaudeMdBudgetTests` enforces; it was
13,181 before this kit). If over, shorten the two run-line comments only.

Acceptance: both files edited exactly as above; `wc -c CLAUDE.md` ≤ 16000; full suite
green (which proves the sentinel matches GUARDRAILS.md and the byte budget holds).

Verify:
```bash
cd "$(git rev-parse --show-toplevel)" && grep -c "harness_update.py" CLAUDE.md | grep -qx 3 && grep -q 'harness-update' tests/test_guardrails_layout.py && python3 -m unittest discover -s tests -q
```
