# polytropos — Codex harness

This bundle is the OpenAI Codex side of the polytropos monorepo. The Claude Code plugin at
the repository root and the GitHub Copilot bundle are separate harnesses with separate
instructions and pricing data; no harness reads another harness's numbers.

Invoke the native `$route` skill before an expensive run such as a multi-file change, a long
agentic loop, or a migration. In Codex CLI and supported IDE clients, use `/skills` or `$route`;
other clients may expose the skill selector in their version-specific UI. `$route` establishes
the billing mode, classifies the task, derives the estimate from pricing data, and previews the
central policy assignment. Do not rely on a bare custom `/route` alias or a custom dispatch loop.

Derive every number from `data/pricing.codex.json` at run time — it is the single source of truth for Codex-side pricing; never quote prices, plan limits, or model ids from memory.
Under a ChatGPT plan, Codex is usage-limited rather than token-billed:
present the burn index first and label every dollar number as an API-equivalent proxy. Present
real dollars only for `OPENAI_API_KEY` API-metered runs.

The native skills are `$usage` (read-only local usage), `$journal`, `$frontier-check`,
`$escalate`, and `$effort`, plus the other workflows shown by `/skills`. `$effort` reads the
available levels from `data/pricing.codex.json` and applies them with
`-c model_reasoning_effort=<level>` (or `--effort` for `bin/codex_execute.py` kit runs). Step
effort up only after failure evidence.

`codex/prompts/` is a deprecated compatibility namespace. It is not the default workflow source;
use an explicit legacy copy only when compatibility is required.

The central policy reserves Astra for planning, coordination, final acceptance, and recovery
after driver-recorded machine failure. Luna performs cheap mechanical work; Terra is the routine
worker; Sol handles hard, security, integration, and independent-verification work. The driver
creates no warm pool. Keep planned pins, dispatched assignments, and independently observed
model-role use separate; missing observation is `unknown`. A direct host tool or a model selected
outside this policy boundary remains outside its enforcement scope and must be disclosed as such.
