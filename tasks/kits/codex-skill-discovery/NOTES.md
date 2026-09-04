# Execution notes — codex-skill-discovery

User authorized execution, commit, push, and subsequent live Codex installation on 2026-09-04. The original plan-only and no-live-rollout boundaries apply to automated implementation/tests; live installation is now authorized separately. No real model CLI is used in verification.

Interactive execute dispatch: T1 strong -> gpt-5.6-sol; T4 mid -> gpt-5.6-terra. Independent verification and phase review are required before acceptance.

T4 complete: implementer and independent verifier each passed metadata (4), surface (8), plugin (5) tests under Python 3.12. System Python 3.9 lacks tomllib; verified commands use Python 3.12 on PATH. Actual UI rendering will be checked during authorized live rollout.

T1 complete: implementer and independent verifier passed discovery (5), setup (14), updater (63) tests. Activation remains explicitly unknown without host evidence. T2 dispatched to strong/Sol.

T4 evidence strengthened after root review: relocation fixture now invokes real legacy planner/applier and checks all 12 metadata ownership records. Implementer reran all 17 tests; root independently reran the changed 4-test suite successfully.

T2 complete: independent root verification passed 7 native-default, 12 harness-select, 62 harness-update tests. Separate review agents stalled at pending_init and were interrupted; root (not the implementer) performed independent verification and Phase 1 diff review. Phase 1 accepted: native entrypoints, no-clobber updates, preserved ownership metadata, honest unknown activation. Full suite at phase boundary: 3007 tests, two failures; root fixed outdated nested-metadata inventory test (5 checks pass), generated documentation source freshness is scheduled for T5. T3 starts on strong/Sol.

T3 complete after two root review correction rounds: backup/restore symlink containment, strict restored paths, digest revalidation, rollback retaining original backups beside concurrent replacements, malformed-ownership rejection, and explicit conflict reporting. Independent root rerun: 22 migration + 7 native defaults + 62 updater tests passed. Phase 2 accepted after source review and actual-installer metadata coverage. T5 starts on mid/Terra. Live rollout remains separate from automated fixtures.

T5 complete: root independently verified Codex and harness suites, corrected the existing documentation contract, and regenerated documentation. Final full repository suite: 3034 tests, OK (2 skipped). Documentation build check passed. Phase 3 accepted after review of native setup, migration lifecycle, command examples, and generated source-hash bookkeeping. All five tasks are done.

Live rollout follows publication. Automated tests use temporary roots and do not prove the desktop UI. Computer Use cannot inspect Codex, so live verification uses supported plugin management and app-server skill discovery; a fresh user task is the final UI check.
