# harness-update — one update skill for all three harnesses

autonomy: advisory

## Goal

A single Claude-side skill (`/polytropos:update`) plus one engine (`bin/harness_update.py`)
that answers "is anything I installed or published from this repo stale?" across all three
harnesses and the repo's data surfaces — and, on explicit ask, refreshes everything it is
allowed to write. "Done" looks like:

- `python3 bin/harness_update.py check` prints one freshness card with four sections
  (claude / copilot / codex / data), exits 0 when everything is fresh and 3 on any drift,
  and never writes a byte anywhere.
- `python3 bin/harness_update.py apply` refreshes exactly the writable targets (Copilot
  home files, Codex home files, repo generated mirrors), prints the Claude-side remedy
  commands instead of running them, and reports what changed with counts.
- `python3 bin/harness_update.py demo` exercises both paths against synthetic temp trees,
  touching no real data.
- The drift that motivated this kit is fixed and gated: `docs/COPILOT-HARNESS.md` still
  labeled its snapshot `2026-07-25` while `data/pricing.copilot.json` said `2026-08-11` —
  after this kit, a live-tree test fails whenever a pricing file's `cached_date` no longer
  appears in its partner doc.

## Why now (evidence)

On 2026-08-11 the live Claude install was found stale by hand: plugin cache built at
`39bad91`, repo HEAD at `d08b5a1` (the Codex merge landed after the last refresh). The
COPILOT-HARNESS.md label drift above was found the same day. Both are exactly the class of
rot a check-first updater catches mechanically.

## Constraints and out-of-scope

- **Out of scope:** any write under `~/.claude` (the standing repo rule "repo code never
  touches `~/.claude`" holds — the engine prints `bin/plugin_staleness.py`'s remedy, the
  user or session runs it); auto-editing pricing NUMBERS or docs snapshot TABLES from the
  engine (those need source data — `check` reports staleness only; T4 fixes today's drift
  by hand, once, from the data file); the modern Codex setup flags (`--components`,
  `--agent-scope`, `--legacy-copy`, `--refresh-managed` stay `harness_select.py`'s
  surface — `apply` uses the legacy writers only, whose per-channel semantics D3 states);
  shipping this skill into the
  copilot/codex bundles (user chose one Claude-side skill — so `EXPECTED_SKILL_STEMS`,
  `copilot/aesop.yaml`, and the 12-count codex roster tests are all untouched); network
  access of any kind; scheduling/unattended runs.
- Stdlib-only Python, unittest only, no pytest.
- Never invoke the real `claude`/`copilot`/`codex`/`gh` CLI from any code path, test, or
  verify command.
- Tests never read or write the real `~/.claude`, `~/.copilot`, or `~/.codex` — temp
  fixture homes behind explicit flags only.

## Architecture & key decisions

- **D1 — One engine, one skill.** `bin/harness_update.py` + `skills/update/SKILL.md`
  (skill name `update`). No bundle variants. *Why:* the user picked single-source; it also
  keeps three roster tests and the aesop manifest out of the blast radius.
- **D2 — `check` is strictly read-only and aggregates four sections.**
  claude: reuse `bin/plugin_staleness.py` (its `IN SYNC` / `SHA STALE` / `DRIFTED`
  statuses and remedy strings). copilot: a new read-only per-file comparator that mirrors
  `install_copilot`'s inventory and placeholder resolution. codex: reuse
  `harness_select.doctor_codex`. data: pricing `cached_date` ages, both sync scripts'
  check modes, and the docs snapshot-label checks (D7). Exit 0 fresh / 3 drift — the
  plugin_staleness exit-3 precedent. *Why read-only:* check must be safe to run reflexively,
  including from the skill's default path.
- **D3 — `apply` writes only three target families.** (a) Copilot home via
  `harness_select.install_copilot` (its existing unconditional-overwrite semantics,
  inherited and stated in the report); (b) Codex home via legacy `install_codex`, whose
  channels differ and whose report must say so: `~/.codex/prompts/*.md` are
  plugin-generated deprecated mirrors and install_codex OVERWRITES them in place (every
  rewrite of a differing destination listed and labeled, never silent), while `AGENTS.md`
  and `codex/skills/<name>/` are user-editable and no-clobber (`skip-differs` surfaced,
  never forced); project-scope agent TOMLs and the modern `plugin` component are OUTSIDE
  apply's reach — the report names that coverage limit and points at
  `harness_select install --harness codex` rather than claiming completion over drift it
  cannot touch; (c) repo generated mirrors via `sync_pricing_refs.sync` and
  `sync_codex_surfaces` build mode. The Claude section only prints the remedy, framed
  conditionally (apply makes no freshness determination of its own). *Why:* every writer
  already exists — apply is delegation plus honest reporting, never a new write path.
  [CORRECTED at P2 review: the original D3(b) said legacy install_codex was no-clobber
  wholesale — false for prompts; `defect:` kind=stale-plan-decision logged.]
- **D4 — Reuse by import, never duplicate.** Load sibling `bin/` modules with the repo's
  established `importlib.util.spec_from_file_location` loader (bin/ is not a package —
  same pattern as `tests/test_harness_select.py`'s `_load`). The reused modules
  (`plugin_staleness.py`, `harness_select.py`, `sync_pricing_refs.py`,
  `sync_codex_surfaces.py`) are never edited by this kit.
- **D5 — Home seams.** `--copilot-home`, `--codex-home`, `--installed-manifest`,
  `--repo-root`; `Path.home()` / `expanduser` appear only in argparse defaults or `cmd_*`
  handlers, never in pure functions (the `codex_usage.py` convention). Source-introspection
  test enforces no `subprocess`, no `urlopen`, no `Path.home` in the pure layer.
- **D6 — Honesty rules.** Per-file states with counts; `skip-differs` reported as
  user-preserved, never silently upgraded; a missing home is "not installed", not an error;
  the Claude remedy always carries "(restart to apply)"; pricing ages are facts, and the
  >60-day flag is "re-verify against source", never an auto-refresh; the codex partner doc
  carrying no price snapshot is named as by-design, not reported as drift.
- **D7 — Docs snapshot-label check.** A pricing file is doc-fresh iff its `cached_date`
  string appears in its partner doc: `data/pricing.json` → `README.md`;
  `data/pricing.copilot.json` → `docs/COPILOT-HARNESS.md`; `data/pricing.codex.json` →
  none by design (`tests/test_codex_docs.py` forbids live numbers there). *Why substring:*
  the tables are hand-maintained prose; the date label is the one machine-checkable anchor
  that CLAUDE.md's "update them only together" rule hangs on.
- **D8 — Skill law: check first, apply on explicit ask.** The skill always runs `check`
  first and reports. It runs `apply` (or the printed `claude plugin update ...` remedy)
  only when the user has asked for the refresh in this conversation — invoking the skill
  to "see where things stand" is not consent to write.
- **D9 — Kit slug `harness-update`; skill dir `skills/update/`.** No Claude-side skill
  roster test exists, so the new dir needs no manifest entry; the kit slug gets a
  `KIT_SENTINELS` entry (T8).
- **D10 — Fix today's found drift inside this kit** (T4) and convert it into a permanent
  live-tree gate (T5). A checker that ships red on its own repo teaches people to ignore it.

## Model pins (routing-history evidence, pulled 2026-08-11)

sonnet 94% first-try (138 outcomes), opus 100% (40), haiku 93% (29) — cheap pins are safe
here; everything is sonnet except the one home-mutating task (T6, opus) and the mechanical
wiring task (T8, haiku). Verifier is **sonnet**, not haiku: recorded verifier precision is
haiku 60% vs sonnet 100%. Reviewer opus (87% precision across 156 findings). Brief-defect
floor says my own top failure modes are contradictory-acceptance, stale-plan-decision, and
unspecified-path — briefs therefore pin exact paths and content assertions, no line-number
anchors, and every verify command can actually fail.

## Risks and tripwires

- **Reused function signatures drift from this plan's description.** Tripwire: an
  implementer finding `install_copilot` / `doctor_codex` / `sync` signatures different from
  the brief stops and reports (brief-vs-reality rule) — the functions are authoritative,
  the brief's *semantics* (no-clobber, read-only) are the contract.
- **`docs/COPILOT-HARNESS.md` table values.** T4 derives every number from
  `data/pricing.copilot.json` at edit time. If any table row can't be traced to a field in
  the data file, stop and report — never interpolate a price.
- **CLAUDE.md byte budget.** 13,181 of 16,000 bytes used before this kit. T8's additions
  must keep it ≤ 16,000 (`tests/test_guardrails_layout.py` enforces). If tight, trim the
  run-line comments, not the invariant.
- **Temp-home discipline.** Any test touching a real home dir is an automatic defect, even
  if green. The verifier greps for `Path.home` outside sanctioned default-sites.
- **`skills/update/` name collision.** No gitignored store is named `update/` — but if a
  `/update/` ignore rule ever appears, `tests/test_privacy_layout.py`'s tracking guard is
  the template to extend.
