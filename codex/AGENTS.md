# polytropos — Codex harness

This bundle is the OpenAI Codex (Codex CLI) side of the polytropos monorepo: a model
router and cost estimator for the GPT-5.6 family. The Claude Code plugin at the repository root
and the GitHub Copilot bundle are separate harness surfaces, each with its own instructions and
its own pricing file — the three never mix, and no harness reads another's numbers.

Derive every number from `data/pricing.codex.json` at run time — it is the single source of truth for Codex-side pricing; never quote prices, plan limits, or model ids from memory.

Before any expensive run — a multi-file change, a long agentic loop, a migration — invoke the
`/route` prompt first. It establishes your billing mode, classifies the task into a tier,
estimates the cost from the pricing data, and prints the exact `codex` command for the chosen
model. Routing a task costs almost nothing; guessing the model can cost a lot.

Be honest about billing. Under a ChatGPT plan the Codex CLI is usage-limited, not token-billed:
OpenAI publishes no token-to-quota conversion, so any dollar figure shown for a subscription run
is an API-equivalent relative-burn proxy — a routing aid, never a bill. Present real dollars only
for `OPENAI_API_KEY` (API-metered) runs; for subscription runs lead with the burn index and label
every dollar figure as a proxy.

Beyond /route, four ported prompts complete the optimizer surface: /usage (historical Codex activity from local logs, read-only — priced only when the logs carry tokens, and then only as a labeled API-equivalent proxy), /journal (the daily work journal), /frontier-check (is a task worth the frontier tier), and /escalate (verify-gated dispatch that climbs the tiers only on failure).

The /effort prompt makes the reasoning-effort dial a first-class surface: levels come at run time from the pricing data's knobs.reasoning_efforts (never from memory), are applied per run via the -c model_reasoning_effort=<level> override (or --effort on bin/codex_execute.py kit runs), and are stepped up one level at a time only on failure evidence — deeper effort burns subscription usage faster, and any dollar figure shown for it is a labeled API-equivalent proxy, never a bill.
