---
name: bench-routing
description: Compare benchmark priors with central Codex worker-role assignments.
---

# Benchmark-informed Codex routing

Resolve `POLYTROPOS_ROOT` from this skill's location. In a managed copy use `POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`; reject the literal placeholder. Confirm pricing data, `bin/bench_routing.py`, and `bin/codex_policy.py` exist. Otherwise stop and use `python3 bin/harness_select.py doctor --harness codex`.

Use the engine rather than recreating its ranking logic:

```bash
python3 "$POLYTROPOS_ROOT/bin/bench_routing.py" roles --harness codex
python3 "$POLYTROPOS_ROOT/bin/bench_routing.py" rank
python3 "$POLYTROPOS_ROOT/bin/bench_routing.py" compare
python3 "$POLYTROPOS_ROOT/bin/bench_routing.py" demo
```

`compare` has no `--harness` flag of its own. `compare` joins the benchmark prior with Claude-harness implementer evidence. There is no per-role outcome data for Codex, so the Codex recommendation stands unchallenged rather than borrowing Claude outcomes as Codex proof.

The Intelligence Index is a general-capability composite transcribed from a screenshot. It is a prior, not proof of Codex task performance, availability, cost, or observed use. Benchmark workload estimates are not this repository's pricing, a bill, or routing certainty, and a recommendation is not a guaranteed winner.

Use central policy for assignments: Luna for cheap work, Terra for routine work, Sol for hard, security, integration, and independent verification, and Astra for coordination and final acceptance. Never turn benchmark preference into a direct model pin, freehand dispatch, or recovery evidence. Compare conclusions with the driver's separate planned, dispatched, observed, and verification records.
