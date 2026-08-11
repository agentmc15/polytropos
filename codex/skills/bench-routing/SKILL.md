---
name: bench-routing
description: Compare benchmark priors with Codex-dispatchable roles while preserving benchmark uncertainty. Use to rank candidates, inspect Codex role recommendations, or run the synthetic routing demo.
---

# Benchmark-informed Codex routing

## Resolve the plugin root before running commands

Set `POLYTROPOS_ROOT` from this file's real location: in plugin mode, this file is
`<root>/codex/skills/bench-routing/SKILL.md`, so ascend to `<root>`; in a managed copied install,
use the installer-resolved `POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`. Reject a literal placeholder.
Before shelling out, verify `$POLYTROPOS_ROOT/data/pricing.codex.json` and
`$POLYTROPOS_ROOT/bin/bench_routing.py` exist. If proof fails, stop and direct the user to
`python3 bin/harness_select.py doctor --harness codex`; never run a guessed or stale path.

Use the engine rather than reproducing its ranking logic:

```bash
python3 "$POLYTROPOS_ROOT/bin/bench_routing.py" roles --harness codex
python3 "$POLYTROPOS_ROOT/bin/bench_routing.py" rank
python3 "$POLYTROPOS_ROOT/bin/bench_routing.py" demo
```

The Intelligence Index is a general-capability composite transcribed from a benchmark screenshot,
not measured Codex task performance. Benchmark workload cost estimates are not this repository's
pricing, a bill, or routing certainty. Preserve every transcription/coverage limitation and use
the repo's measured comparison surface when evidence exists. Recommend a role assignment as a
prior to verify, not a guaranteed winner.
