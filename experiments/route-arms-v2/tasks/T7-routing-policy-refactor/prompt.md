# Refactor routing policy catalog lookup and candidate filtering

## Context
`bin/routing_policy.py` is intentionally behaviour-sensitive: callers rely on exact decision dictionaries, exact `RoutingError` messages, and exact `explain()` / CLI output. The base module has two kinds of tangled logic that should be refactored without changing behaviour:

1. Catalog rows are looked up by model id in multiple places (`_floor`, `decide`'s chosen-model path, and `_estimate`).
2. `decide()` owns a long inline hard-filter chain while also handling refusal text, preference ranking, effort, ladder, estimates, and the return payload.

This task is a refactor only. Correctness means the public surface behaves exactly as it did before.

## Required behaviour
1. Add a private helper named `_catalog_by_id(catalog)` in `bin/routing_policy.py`.
   - It must build the id-to-row mapping exactly once using catalog row `"id"` values.
   - `_floor`, `decide`, and `_estimate` must each use this helper for their model-id lookup needs.
   - `_floor`, `decide`, and `_estimate` must not rebuild their own `{row["id"]: row ...}` mapping.
   - `decide` must not scan candidates with `next(... if c["id"] == chosen ...)` for the chosen-model path; use the shared lookup instead.
2. Add a private helper named `_candidate_filter_reason(entry, floor, request, rules, excludes, explicit_effort, budget)`.
   - It must return exactly one of the existing hard-filter reason strings (`"not-routable"`, `"unavailable"`, `"pinned-elsewhere"`, `"excluded"`, `"reserved"`, `"effort-unsupported"`, `"below-floor"`, `"over-budget"`) or `None` when the row is eligible.
   - It must preserve the base hard-filter order exactly: not-routable, unavailable, pinned-elsewhere, excluded, reserved, effort-unsupported, below-floor, over-budget.
   - It must not mutate a reasons list; it returns the reason and the caller builds the list.
3. `decide()` must construct candidates by calling `_candidate_filter_reason` once per catalog entry.
   - Do not leave duplicate inline checks for not-routable, unavailable, pinned-elsewhere, excluded, reserved, below-floor, or over-budget inside `decide()`.
   - It is OK for `decide()` to continue referring to `"effort-unsupported"` for the existing supporter-list refusal text and to `"ranked-lower"` for preference annotation.
4. Preserve all public behaviour exactly:
   - `CONTRACT_VERSION`, vocabulary tuples, policy rules, and constants remain unchanged.
   - `catalog_entry()` and `catalog_from_pricing()` return the same dictionaries in the same order.
   - `decide()` returns the same dictionary keys and values for every request, including candidate reason lists, floor basis strings, migrated tuples, ladder order, estimate shape/status/rounding, capability fields, uncertainty, and refusal text.
   - `explain()` output is byte-for-byte unchanged for the same decision.
   - `python3 bin/routing_policy.py demo` output and exit status are unchanged.
   - `python3 bin/routing_policy.py decide ...` JSON/text output, stderr, and exit statuses are unchanged.
5. Edge cases that must stay pinned include: unknown planned model/tier errors; non-routable model pins; missing `chosen` models; explicit pins overriding preferences; unsupported efforts; budget refusal before ranking; reserved policy frontier migration; prior-failure floor raising; shape fallback notes; missing review/acceptance estimate stages; latency preference notes; and one-ladder-entry-per-higher-rank behaviour.

## Scope and rules
- Change only `bin/routing_policy.py` and tests under `tests/`.
- This is a refactor: do not add features, rename public functions, change CLI flags, or change public output formats.
- Python stdlib only; do not add dependencies.
- Do not invoke real `copilot`, `codex`, `claude`, Cursor `agent`, network services, or user home data.
- Do not hardcode real model ids, prices, plan facts, credit values, or pricing dates.
- Add or update unit tests for the refactor, but keep existing regression tests green.

## Regression commands
Run from the repo root:

```bash
python3 -m unittest discover -s tests -p test_routing_policy.py
python3 bin/routing_policy.py demo
```
