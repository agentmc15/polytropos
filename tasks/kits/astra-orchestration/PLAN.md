# Astra orchestration and recovery

## Goal and acceptance

Enforce role-aware Codex routing centrally: Astra orchestrates and accepts work; Luna, Terra, and Sol implement according to difficulty; only recorded machine-visible failure unlocks corrective Astra dispatch. Verify retry evidence, task-scoped recovery, return to workers, independent observed-use records, safe legacy-kit migration, explicit unavailable-model failures, and harness isolation. Update the live Codex plugin and application defaults after reviewed tests and publication.

## Decisions

- Keep model identities, availability, efforts, rates, thresholds, and role bindings in the Codex pricing source of truth. Use the user-supplied 2026-09-05 pricing screenshot; retain provenance and uncertainty for models or request context not observed. Copilot has independently updated applicable rates; Claude pricing is unchanged.
- Use a central policy module from pricing, execution, and app integration. Task pins are intent, not evidence of actual use. Legacy missing pins receive an explicit worker default; legacy frontier pins map to the highest worker. Explicit orchestration model pins cannot authorize ordinary implementation.
- The sequential CLI driver has no warm pool: reserve Astra for recovery instead of pre-spawning it. Any future warm pool must keep recovery agents out of worker allocation.
- Record dispatch return codes and independent verification results. Recovery records identify prior attempts, failure evidence, bounded correction scope, and verification. Never infer runtime model identity from a planned pin or arbitrary prose.
- Application settings prevent accidental parent-model inheritance, while the dispatch gate enforces Polytropos workflows. Arbitrary user-selected models and direct host tools outside that gate remain a host boundary, not a claimed enforcement guarantee.

## Constraints and risks

No live model calls in tests. No fabricated pricing, quotas, effort support, or warm-pool capability. Preserve unrelated work and user configuration. Do not rewrite historical task pins or commit history. Validate per-request long-context thresholds separately from aggregate session token totals.
