---
name: repo-bench
description: Plan Codex model benchmarks against real work mined from a repository, with subscription-safe burn and API-equivalent proxy reporting.
---

# Codex repo bench

Resolve `POLYTROPOS_ROOT` from this skill's location. In a managed copy use `POLYTROPOS_ROOT="{{POLYTROPOS_ROOT}}"`; reject the literal placeholder. Confirm `bin/codex_repo_bench.py`, `bin/repo_bench.py`, and `data/pricing.codex.json` exist. Otherwise stop and use `python3 bin/harness_select.py doctor --harness codex`.

Always plan first:

```bash
python3 "$POLYTROPOS_ROOT/bin/codex_repo_bench.py" plan --repo <path> --models <ids-or-tiers>
```

The plan mines real issue-fix or mutation-repair tasks without dispatching a model. Present the burn index first. Every dollar is an **API-equivalent proxy**, never a ChatGPT-plan bill or quota conversion.

Live execution is intentionally unavailable in this Codex port. The existing live benchmark engine enforces a Claude API-dollar ceiling, but ChatGPT-plan usage is opaque and not token-billed. Do not invoke the Claude engine for Codex models and do not treat proxy dollars as a safety ceiling. `run` prints the plan and refuses without dispatching. A future live port must add an explicit dispatch-count ceiling and a Codex-native result ledger before it can be enabled safely.

When interpreting acquisition and oracle semantics, use the root `skills/repo-bench/references/` material. Preserve its honesty labels: `solved` comes only from the tests oracle; unavailable evidence is `n/a`; similarity is not correctness; below-floor evidence cannot change routing. Never run a target repository's tests unless the user explicitly supplied `--test-cmd` and would run that code by hand.
