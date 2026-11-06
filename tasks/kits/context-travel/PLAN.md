# Context travel — Phase 1

## Goal

Carry versioned intent, context, and evidence between agents and surfaces without
changing the authorities that own tasks, execution, permissions, or acceptance.
CT1 and CT2 are complete: the bounded briefing contract and explicit source
observations have passed their offline gates. The user requested continuation and
chose the original CT1 -> CT2 -> CT3 -> CT4 -> CT5 -> CT6 order on 2026-11-01.
The user requested continuation after CT2; CT3 is complete as the read-only
lifecycle projection and role-briefing task. Its 39 targeted tests, independent
review, documentation checks and 6,568-test full suite passed (two skips).
On 2026-11-05 CT4 completed its offline scope: 48 targeted tests, independent
review, release/documentation checks and 6,616 full-suite tests passed (two skips).
The first full run's harness-only errors and correction remain in CT4-EVIDENCE.md.
The user also
required one shared codebase across private poly-auto and public polytropos,
and chose to finish CT4 before preparing a reviewed local synchronization.
Repository visibility and enabled GitHub capabilities may differ; product and
workflow definitions should remain in parity, with private-only execution gated.
The alternative Claude-first pilot is not adopted.

## Scope and decisions

- CT1 adds data validation, identity construction, canonical bytes/digests,
  correlated request/briefing validation, documentation, and offline tests.
- CT2 adds explicit, selected-source observations through a bounded read boundary.
  Reuse existing parsing/provenance/privacy authorities; introduce only the narrow
  read and pure-parser seams needed to avoid implicit or repeated reads. No task
  readiness decision, graph extraction, source search, or evidence join is added.
- CT3 composes in-memory requests and observations into versioned projections,
  role briefs, explanation traces and comparisons. Its own contract represents
  partial views without inventing missing CT1 task criteria. It performs no I/O,
  builds no new acceptance/readiness engine, and preserves uncertain applicability.
- CT4 adds a shared query/config boundary plus stdlib CLI and MCP stdio adapters.
  Startup configuration alone authorizes repository/kit/file selections. Queries
  can consume supplied immutable projections without rereading sources. MCP is
  pinned to the published 2025-11-25 protocol, with bounded synchronous requests.
- Repository identities are explicit caller-supplied identifiers. Never infer
  equivalence from local directory names, remotes, or credentials.
- Preserve existing task IDs; namespace them by repository ID and relative kit
  path. Track checkout/revision applicability separately from stable task identity.
- `bin/kit_contract.py` remains the sole owner of task parsing, readiness, status,
  acceptance, and execution semantics. `bin/attempt_ledger.py` owns provenance
  reference shape. The new contract composes those identities, never rewrites them.
- Briefings are advisory data. Schema validity and a matching content digest
  establish structure and identity, not correctness, freshness, permission, or
  acceptance. Declared freshness remains explicitly reported evidence.
- No implicit home, repository, ledger, clock, model, surface, or provider lookup.
  Unknown provenance is represented explicitly. No transport telemetry in the
  canonical briefing body; callers record it separately in a later phase.
- All fields and collections are bounded. Reject an oversized mandatory payload;
  never silently truncate criteria. Canonical JSON ignores object insertion order
  but preserves meaningful array order. Document any normalization performed.
- Free text passes through the existing redaction engine before it could be
  exported, with redaction counts and limitations disclosed. Machine identifiers
  that contain credential shapes are refused rather than rewritten.

## Future work, outside the current task

CT5 skill integration across Codex desktop/CLI, Claude
desktop/CLI, and GitHub Copilot desktop/CLI; CT6 independent comparative evaluation.
Incremental indexes, provider integrations, PRs, merges, deployments, and live
client verification are outside CT4. Claude desktop chat and Code modes will
need separate capability records. Nothing in CT1 claims surface compatibility.

## Done and evidence

CT1 is complete when strict request/briefing schemas round-trip deterministically;
different repositories and kit paths do not alias existing task IDs; stale or
misbound responses and changed content are rejected; unknown references survive;
malformed, oversized, and unauthorized-shaped payloads are refused; and meaningful
offline tests pass. Tests use synthetic data and temporary directories, no
installed model clients, network, personal stores, or installations.

Run targeted tests first, then the repository-required full unittest suite and
stdlib documentation/release generators. Keep results and limitations in NOTES.md.
Independent verification and coordinator acceptance are separate activities.

CT2 is complete only when selected reads are confined, denied before content
access, bounded in aggregate, and checked for within-read changes. Repository and
kit identities are explicit; evidence selection never resolves a personal default.
Missing, corrupt, forbidden, inconsistent and incomplete sources remain distinct.
Graph freshness and unproven legacy evidence bindings stay unknown. Tests use both
kit layouts, multiple repositories, duplicate kit names, graph-present negative
cases, and temporary filesystem/stub fixtures. The critique's findings strengthen
these gates without changing phase order or removing later surfaces/providers.

## Execution policy

CT1–CT4 worker intent: strong. CT4's preliminary mid-tier preview resolved to a
model unavailable in this app's worker pool; transport and access-boundary work
also meets the routing skill's strong integration/security category. The strong
preview selected the configured ordinary worker without frontier recovery.
Central Codex policy selects the actual worker from
repository data. No live driver runs or model-client probes are authorized.
The user authorized isolated implementation, then continuation on 2026-11-01.
All work remains on this isolated branch. The separate critique checkout and the
attached public polytropos checkout are not modified during CT4 implementation.
After CT4, prepare local synchronization in isolation without publication or
overwriting the active public checkout. Record exact tracked-tree parity and
remaining release gates; never equate local preparation with public availability.
