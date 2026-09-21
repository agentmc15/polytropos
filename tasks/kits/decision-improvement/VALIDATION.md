# Planning-artifact validation

This receipt validates the planning delivery, not the future implementation or any model-quality gain. All implementation tasks remain pending.

## Baseline and scope

- Main and freshly fetched origin/main matched `aab755378975e9191db6ced16ee07a27a414af21` during preparation; the plan preserves completed steps 16–26.
- Artifacts were prepared on `codex/decision-improvement-plan` in an isolated worktree. The existing working branch and unrelated edits were preserved.
- Changes are Markdown plans, task briefs, scoped agents and a staged assessment skill. No runtime modules, installed plugin, provider configuration or active policy changed.

## Checks actually run

- Native kit parsing and DAG validation: 30 V1 tasks, 4 V2 tasks, plus a matching 30-task Codex planning projection; all pending.
- Optional task parsing/DAG: 4 advice tasks. All 38 distinct task verify commands pass Bash syntax checking. These are future checks; proposed implementation test classes were not falsely reported as already present.
- Interactive roster checks pass for both native kits. Claude and Codex dry runs dispatch nothing and expose their headless independent-verification gaps; the handoff selects the interactive Claude workflow.
- A one-off stdlib artifact check verified required fields, task/mirror consistency, skill frontmatter/reference resolution, six agent tool postures, absence of machine-local paths, and byte-identical reconstruction plus SHA-256 of all 18 embedded files in the standalone handoff.
- The skill-creator validator was unavailable because PyYAML was absent. No dependency was installed; structural validation used the stdlib check. This is not behavioral proof of the skill's effectiveness; D26 provides that evaluation scope.
- Both documentation mirrors were rebuilt; docs_build, copilot_docs, sync_codex_surfaces and release_gate checks passed. The release gate resolved mapped test IDs; its separate --run option was not invoked because the full suite was run.
- Final full suite: `python3 -m unittest discover -s tests`, Python 3.12.7, **4,203 tests in 218.946 seconds, OK (2 skipped)**. No live model CLI/provider calls were made.

## Environment and baseline findings

The system Python was 3.9; current main uses syntax requiring 3.12. Validation selected an existing 3.12 interpreter and installed nothing. The nested Codex sandbox prevents the repository's macOS sandbox tests from exercising their intended boundary; after a focused 109-test executor suite passed outside it, full validation also ran outside that nested sandbox with stub runners.

The first such full run exposed two existing issues: the lessons-promotion test assumes a legacy journal path in a fresh worktree, and a concurrent scheduler snapshot can race an atomic TASKS temporary file. Both passed on focused rerun; the final suite passed after preparing an empty ignored `journal/promotions/` fixture. The synthetic output accidentally sent to this worktree's external namespace by the legacy-path test was removed through runtime_data after checking that it was the only file in that journal store. Empty in-tree fixture directories were removed after validation.

Neither the passing rerun nor these environment accommodations repair the underlying test assumption or concurrency race. They are explicitly recorded in the architecture and whole-repository assessment for D01 reconciliation. No runtime code was changed to obtain the pass.

Planning helpers were requested through host subagents using policy-selected worker tiers. This was outside the execution driver's enforcement boundary; requested assignments are not independently observed runtime identity. No task outcome or attempt ledger was fabricated for planning.

## Training-data planning extension validation

The earlier checks above describe the original delivery. After the RSI and training-data plan extensions, V1 contains 34 pending tasks in eight phases; D31–D34 run before the original release tasks, with D28 depending on D34. The standalone document now contains 21 source blocks.

For this documentation-only extension, native V1, its Codex planning mirror and the RSI research task graphs validated; the interactive V1 roster retained independent verification and review. The 34-task native/mirror identity, status and dependency records match. All native/mirror verification commands passed shell syntax checks. All 21 embedded sources matched their files and SHA-256 entries, and git diff --check passed. No proposed runtime tests were executed, no data was collected/exported, and no training was run. The original full-suite result above is not validation of these future features.
