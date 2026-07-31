# polytropos — Copilot harness

This bundle is the GitHub Copilot side of the polytropos monorepo: a cross-vendor model
router and cost estimator for Copilot CLI. The Claude Code plugin at the repository root is a
separate harness surface with its own instructions and its own pricing data — the two never mix.

Derive every number from `data/pricing.copilot.json` at run time — it is the single source of truth for Copilot-side pricing; never quote prices, credit values, or model ids from memory.

Before any expensive run — a multi-file change, a long agentic loop, a migration — invoke the
`route` agent first. It classifies the task into a tier, estimates the cost in USD and AI Credits
from the pricing data, and prints the exact command to run the chosen model. Routing a task costs
almost nothing; guessing the model can cost a lot.

Beyond routing, six ported agents complete the optimizer surface: the usage agent (historical Copilot spend from local logs, read-only), the context-weight agent (measures what filled the context window), the bench-routing agent (checks a benchmark-informed routing recommendation against measured outcomes), the journal agent (the daily work journal), the frontier-check agent (is a task worth the frontier tier), and the escalate agent (verify-gated dispatch that climbs the tiers only on failure).

The effort agent controls the reasoning-effort dial: Copilot's "Reasoning" setting is adjusted interactively in the /model picker with the left/right arrow keys (a per-model property — rows showing a dash have no dial; no headless flag is confirmed), and the level names are derived at run time from the pricing data's knobs, never from memory.

Every optimizer capability is also invocable as a skill — type /route, /usage, /context-weight, /bench-routing, /journal, /frontier-check, /escalate, /effort, /architect, /execute, or /budget in the prompt (or let Copilot auto-load one when the request matches its description); the same-named custom agents remain the persona surface for isolated --agent runs, and /skills reload picks up newly installed skills in-session.
