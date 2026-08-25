---
name: goliath
description: Run Copilot CLI work through the Goliath five-role pipeline, with the architect as planner and explicit model fallbacks for implementation, test authoring, verification, review, and red-team checks.
---

# Goliath

Goliath is a Copilot CLI-only orchestration policy. Every run uses the architect as planner and
the same five execution roles: implementer, test-author, verifier, reviewer/orchestrator, and
red-team. It does not configure or invoke the Claude Code harness, and it does not silently
substitute a different role or model.

## Role roster and fallback order

Use the first model in each row that is available in the current Copilot `/model` picker and
documented by `data/pricing.copilot.json`. If a requested model is unavailable, try the next
model in that row. Model IDs must be resolved from the pricing data at run time; do not invent
IDs or hardcode prices.

| Role | Primary | Fallback 1 | Fallback 2 |
|---|---|---|---|
| Architect | Claude Fable 5 | GPT-5.6 Sol | — |
| Implementer | Grok 4.6 | Claude Sonnet 5 | — |
| Test-author | Gemini 3.7 Flash | Claude Sonnet 5 | — |
| Verifier | GPT-5.6 Luna | Gemini 3.7 Flash | — |
| Orchestrator / reviewer | GPT-5.6 Sol | Claude Opus 5 | — |
| Red-team | Grok 4.6 | Gemini 3.7 Flash | Claude Sonnet 5 |

The architect is always the planner and runs before the five execution roles. The
orchestrator/reviewer is the Copilot-side coordination role. It owns sequencing, passes the
architect's plan to the implementer and test-author, requires an independent verifier result,
and then dispatches the red-team check before accepting the work.

## Execution protocol

1. Inspect the active roster before an expensive run:

   ```bash
   python3 {{POLYTROPOS_ROOT}}/bin/copilot_pricing.py models --json
   ```

   Confirm the selected IDs are also exposed by the current `/model` picker. If a primary is
   absent, use that role's fallback order. If every candidate for a role is unavailable, stop
   and report the missing role; do not substitute a different role's model.

2. The architect creates the durable plan and acceptance criteria before any execution role.
   Do not use the implementer, reviewer, or another role as the planner.

3. The implementer changes files against the approved plan. It must report changed paths,
   assumptions, and the exact validation it ran.

4. The test-author writes adversarial tests from the architect's plan and acceptance criteria.
   It may change tests only and must not implement the feature itself.

5. The verifier starts from fresh context and independently checks the acceptance criteria.
   It must rerun the relevant checks, never trust the implementer's success claim, and must
   report failures explicitly.

6. The orchestrator/reviewer compares the result with the plan, checks scope and integration,
   and coordinates the final review. It must not replace the architect as planner.

7. The red-team role is mandatory and attempts to break the implementation beyond the
   verifier's ordinary checks, focusing on edge cases, misuse, regressions, and unsafe
   assumptions. It must not rewrite tracked files while reviewing.

8. Accept the work only when all five execution roles report success and the architect's plan
   is satisfied. On failure, send the exact evidence back to the responsible role and rerun
   only the failed stage or its necessary dependency.

## Dispatch

For an isolated role dispatch, use the selected model explicitly:

```bash
copilot -p "<self-contained role brief>" --model <resolved-model-id>
```

Resolve the display name to its current model ID with the pricing engine before dispatching;
the examples above intentionally do not embed live pricing-key IDs.

Never invoke the real Copilot CLI from tests or verify commands. Use `--dry-run`, injected
runners, or synthetic fixtures when validating orchestration logic.

## Reporting

End with a compact ledger containing the architect planner plus all five execution roles,
selected models, availability fallbacks used, files changed, verification commands and
results, reviewer decision, red-team findings, and any unresolved blocker. Do not claim
success when a required role could not run.

## Installed?

If `{{POLYTROPOS_ROOT}}` is still literal, the Copilot bundle is not installed. Install it with
`python3 bin/harness_select.py install --harness copilot`, then reload skills in Copilot CLI.
