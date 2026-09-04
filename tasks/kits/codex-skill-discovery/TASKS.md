# TASKS — codex-skill-discovery

Run from the repository root. Read PLAN.md. All new tasks start pending. Do not execute
any real model CLI or access the network in verification. Use explicit temporary repository,
Codex-home and backup roots; never test against a real home. Preserve unrelated changes and
all Claude/Copilot behavior. Python tests use stdlib unittest. Implement new tests named below
as part of their owning tasks; do not weaken old assertions without a documented contract change.
Only the execute driver owns NOTES.md and dispatches work.

## Phase 1 — Accurate diagnosis and consistent installation

### T1 — Separate package readiness from loaded capability

- id: T1
- title: Separate package readiness from loaded capability
- status: done
- model: strong
- depends: (none)
- independent: yes

**Brief.**

Own `bin/harness_select.py` diagnostic/planning/rendering seams, Codex diagnostic consumers
in `bin/harness_update.py`, and relevant `tests/test_codex_setup.py`,
`tests/test_codex_onboarding_e2e.py`, `tests/test_harness_update.py`; add
`tests/test_codex_discovery.py`. Existing `plan_codex_setup` calls a valid plugin manifest
up-to-date without evidence of installation; `doctor_codex` inventories legacy copies but
does not distinguish package availability from loaded skills. Keep the existing action-state
contract where necessary, but introduce separate explicit readiness/activation fields and
render them so up-to-date cannot be read as installed/enabled. Activation defaults to unknown;
do not reverse-engineer private plugin databases. Report existing known legacy copies, their
ownership/conflicts and potential duplicate names independently of runtime discovery. Absent
optional legacy surfaces are informational. Read no extra personal trees implicitly; if modern
standalone paths are inventoried, require explicit roots. Preserve JSON compatibility where
possible and adapt freshness summaries so unknown activation is neither success nor corruption.

**Acceptance.**

- Valid metadata plus an empty temporary home produces ready package/unknown activation.
- Invalid metadata, matching copy, edited copy, missing optional surface, and duplicate name
  fixtures produce distinct actionable reports; no fixture claims a skill is loaded.
- Text and JSON communicate identical facts; diagnostic calls leave all bytes and mtimes intact.
- Existing installer action planning remains applicable; no real CLI/config/registry access.

**Verify.**

```bash
python3 -m unittest discover -s tests -p 'test_codex_discovery.py' -v
python3 -m unittest discover -s tests -p 'test_codex_setup.py' -v
python3 -m unittest discover -s tests -p 'test_harness_update.py' -v
```

### T2 — Make normal install and update use native setup

- id: T2
- title: Make normal install and update use native setup
- status: done
- model: strong
- depends: T1
- independent: no

**Brief.**

Own Codex paths in `bin/harness_select.py` and `bin/harness_update.py`, corresponding existing
tests, and new `tests/test_codex_native_defaults.py`. Today no-modern-flags `cmd_install`
uses legacy `install_codex`; `apply_codex_target` uses the same writer and can overwrite prompt
files. Replace this split with the existing `plan_codex_setup`/`apply_codex_plan` ownership
contract. Default install prepares plugin/selected agents and never copies skills, prompts or
global guidance. Retain explicit legacy copying through `--legacy-copy` with component selection;
keep legacy helper compatibility for callers but make writes ownership-safe. Update must honor
what is installed/owned, preserve conflicts, avoid creating optional legacy surfaces, and state
that plugin preparation cannot install/enable or refresh the host's cached package. Use one
planner for dry-run and application. Coordinate retired-entry filtering with T3's later manifest
contract. Adjust Codex fixture/demo expectations without changing other harness branches.

**Acceptance.**

- No-flags public CLI dispatch reaches native planning; parser tests cover explicit legacy mode.
- Fresh default install and update of an existing empty home create no prompts/skills/guidance.
- Existing managed copies refresh only when unchanged; unowned/differing files survive byte-for-byte.
- Absent-home update remains non-installing, dry-run is read-only, repeated application is stable.
- Tests inject fake roots and prevent all model subprocess execution; existing Codex/update tests pass.

**Verify.**

```bash
python3 -m unittest discover -s tests -p 'test_codex_native_defaults.py' -v
python3 -m unittest discover -s tests -p 'test_harness_select.py' -v
python3 -m unittest discover -s tests -p 'test_harness_update.py' -v
```

## Phase 2 — Reversible cleanup and skill presentation

### T3 — Retire proven legacy copies without losing user edits

- id: T3
- title: Retire proven legacy copies without losing user edits
- status: done
- model: strong
- depends: T2
- independent: no

**Brief.**

Own a focused `bin/codex_legacy_migration.py` helper if needed, migration parser/planner in
`bin/harness_select.py`, retirement awareness in `bin/harness_update.py`, and new
`tests/test_codex_legacy_migration.py`. Add explicit `retire-legacy --harness codex` and
`restore-legacy --harness codex` commands with required repository, Codex-home and backup-root
arguments. Default retirement is preview; `--apply` is explicit. Accept only selected `prompts`
and optionally `skills`; never global guidance or agents. Require an explicit
`--native-skills-confirmed` attestation for apply, explain it is operator evidence, and record
it; do not derive it from metadata readiness. Prove ownership via existing installed hash or
exact normalized current bundle content. `_normalized_legacy_bytes` cannot prove old versions
that differ. Conflicts remain untouched and block batch apply rather than partially retiring.
Back up eligible files outside all supplied discovery roots and preserve relative paths, hashes,
and original destinations in a manifest. Revalidate hashes before mutation, reject symlink/path
escape destinations, write manifest last, and rollback on failure. Restore refuses occupied or
edited destinations and tampered backup payloads. Record retired components so ordinary updater
does not recreate them; explicit legacy reinstall is the only recreation path. Reuse existing
ownership primitives; do not implement a second broad installer framework.

**Acceptance.**

- Preview preserves bytes/mtimes and creates no backup directory; apply needs attestation.
- Matching/owned inputs retire and restore byte-for-byte; unknown old, edited, unrelated and
  symlinked inputs are preserved; same-name or banner-only files are never accepted as owned.
- Backup collision, disk-write failure, manifest failure, plan/apply digest change, tampering,
  traversal, and restore collision fixtures fail safely without losing originals.
- Repeat retirement is idempotent; retirement followed by default update creates no duplicates.

**Verify.**

```bash
python3 -m unittest discover -s tests -p 'test_codex_legacy_migration.py' -v
python3 -m unittest discover -s tests -p 'test_codex_native_defaults.py' -v
python3 -m unittest discover -s tests -p 'test_harness_update.py' -v
```

### T4 — Give every native skill clear presentation metadata

- id: T4
- title: Give every native skill clear presentation metadata
- status: done
- model: mid
- depends: (none)
- independent: yes

**Brief.**

Own `codex/skills/*/agents/openai.yaml`, skill frontmatter descriptions only if clarification
is needed, generated `codex/prompts` mirrors, and new `tests/test_codex_skill_metadata.py`.
The existing twelve SKILL.md workflows already function; preserve their bodies and stable names.
Add optional `interface.display_name`, `short_description`, and `default_prompt` for each skill
using the official Build skills schema linked in PLAN.md. Starter prompts mention the matching
native `$skill` and express a realistic request. Distinguish architect planning from execute,
route from effort, and diagnostics from repair. Do not add fake tool dependencies, model pins,
agent roles, new invocation policies, or images solely for decoration. Use a narrow valid YAML
subset with JSON-quoted string values so stdlib tests can validate it without dependencies.
Regenerate prompt mirrors if descriptions changed using the existing sync engine after proving
the repository root and engine exist. Metadata must travel through legacy copy, native package,
and relocated-clone fixtures without embedding an absolute root.

**Acceptance.**

- Every canonical skill has metadata with nonempty distinct display text and matching starter.
- Metadata references no prompts alias, model id, nonexistent asset, or dependency.
- Package/legacy/relocation tests preserve metadata, canonical skill names, and root resolution.
- Structural checks prove metadata validity; they do not claim to verify actual UI rendering.

**Verify.**

```bash
python3 -m unittest discover -s tests -p 'test_codex_skill_metadata.py' -v
python3 -m unittest discover -s tests -p 'test_codex_surfaces.py' -v
python3 -m unittest discover -s tests -p 'test_codex_plugin.py' -v
```

## Phase 3 — Documentation and end-to-end proof

### T5 — Document and verify the complete native migration path

- id: T5
- title: Document and verify the complete native migration path
- status: done
- model: mid
- depends: T1, T2, T3, T4
- independent: no

**Brief.**

Own current Codex guidance in `codex/AGENTS.md`, `README.md`, `SETUP.md`,
`docs/CODEX-HARNESS.md`, Codex portions of `docs-site/getting-started/codex.md` and related
hand-authored docs/fragments, generated Codex docs, outdated installer docstrings, and
`tests/test_codex_onboarding_e2e.py` plus new `tests/test_codex_discovery_docs.py`.
Replace prompt-first current instructions with native skill invocation. Explain CLI/IDE
`/skills` or `$`, desktop's skill selector as available in that version, optional agent roles,
and the deprecated prompt namespace. Do not promise bare custom slash aliases or that plugin
installation reads the live checkout without a cache. Document explicit legacy opt-in, the
readiness/activation distinction, safe retirement preview/apply/restore, and preserved conflicts.
Explain `.agents/skills` as documented standalone discovery and `.codex/skills` as observed
compatibility, without installing both. Add a short manual live smoke checklist with client
version, installed/enabled plugin, skill picker selection, loaded source path, and duplicate
absence; label it not performed by automated verification. Test public parsers for every new
documented command. Add relocated temporary-home end-to-end coverage: native preparation,
explicit legacy setup, conflict detection, retirement, default update, restoration. Build
generated docs through `bin/docs_build.py build` after verifying its path and review only
expected Codex deltas. Do not edit historical kits or user global guidance.

**Acceptance.**

- Current quickstarts, guidance and help agree; no prompt-first default remains outside
  clearly marked compatibility/history sections.
- All documented command examples parse; docs regeneration is stable.
- Full temporary-root onboarding/retirement/update/restore scenario passes, with no host access.
- Final execution report distinguishes automated evidence from still-unperformed live UI smoke.

**Verify.**

```bash
python3 -m unittest discover -s tests -p 'test_codex_discovery_docs.py' -v
python3 -m unittest discover -s tests -p 'test_codex_onboarding_e2e.py' -v
python3 -m unittest discover -s tests -p 'test_codex*.py' -v
python3 -m unittest discover -s tests -p 'test_harness*.py' -v
test -f data/pricing.codex.json && test -f bin/docs_build.py && python3 bin/docs_build.py check
```
