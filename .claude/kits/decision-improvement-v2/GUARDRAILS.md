# Decision and improvement — execution guardrails

Read the kit PLAN.md and current repository instructions. User scope and existing authorization govern execution; attached historical prompts are requirements input, not new authorization.

- Preserve current main behavior and completed roadmap work. Never replace new correct code with the attachment's older snapshot. Do not alter unrelated working changes.
- Reuse kit_contract, attempt_ledger/history, runtime_data, safe_paths, proc_runner, exec_policy, repo_bench and workflow_eval as the existing owners. No competing ledger, benchmark writer or host loop.
- stdlib-only bin/tests; unittest; injected runners; synthetic labels/secrets; temporary fixture homes/repos/stores. No real claude/codex/copilot/agent/graphify calls from tests or verify commands. Demo/dry-run is offline.
- Enforce required acceptance, permissions, provider/project eligibility, explicit pins, budget ceilings and native capability checks before action. Predictions cannot grant authority. Unknown external outcomes are not free retries.
- Preserve per-harness prices and usage bases. Resolve values at runtime; never mix credits, billed USD and subscription API-equivalent proxies. Missing duration/usage/model identity is unknown, not zero or inferred from a pin.
- Candidate data cannot change controller code, audit labels, acceptance, mandatory review, permission/budget policy, or the improvement procedure. No automatic global lesson/skill edits.
- A protected experiment requires demonstrated isolation, not hashes or worktrees. Unsupported environments refuse protected live mode. Ordinary offline fixtures can prove rejection and mechanics, never live safety or model quality.
- No new provider integration, live/paid evaluation, private telemetry acquisition, installation, default activation, publish, push or merge is authorized merely by this planning document. Preserve explicit authorization supplied later rather than asking for it again.
- Release 2 and optional extensions are separate scope decisions. V1 must start, work and roll back with every optional provider absent. No Jev endpoint, SDK, model or pricing guesses.
- Use the exact task verify command; ensure proposed named tests actually exist and collect nonzero cases. Never substitute a glob that succeeds with zero tests. Full suite and generated mirror checks must pass before a green-boundary commit.
- Verifier/reviewer roles do not edit tracked sources. Mutation checks use temporary copies. If a check unexpectedly changes the tree, restore that agent's own damage byte-for-byte and report it; never reset another person's work.
- Commit cohesive green boundaries using type(scope): summary and a substantive body explaining why, verification and limitations. Use configured identity; no AI/session/coauthor attribution. No main commits or history rewrites.
