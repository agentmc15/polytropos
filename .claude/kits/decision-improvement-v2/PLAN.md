# Decision and improvement — Release 2, optional Jev

autonomy: advisory
workflow: reviewed

## Start gate

This is a separate deferred release. Do not chain it automatically after Release 1. Start only when the user selects it, core V1 is accepted, real Jev access exists, current official documentation can be inspected, and approved data/transport/resource scope is known. A human-authored start request is not replaced by a worker editing a plan token. Paid probes, protected trials and production activation each require authorization covering that actual action; reuse existing authorization when it already applies.

Read the core plan at `tasks/kits/decision-improvement/PLAN.md`, its guardrails, the original release evidence, and current repository instructions. A protected-live V1 gate is needed before trusted live whole-workflow trials or promotion. An offline-only V1 edition does not pass that gate. If access or enforcement is missing, leave the relevant task blocked and retain the Jev-free system.

## Architecture

Jev is an optional provider behind the existing DecisionProvider contract. Add only a documented adapter, capability/privacy/credential configuration, strict mapper, optional dependency boundary, offline fixtures and comparative evidence. Task/attempt identities, admission, verification, hard constraints, policy lifecycle and benchmark ownership remain unchanged. Credentials, endpoints, SDK imports, model IDs, retention terms and prices must come from then-current official documentation and the configured account; none is specified by this plan.

The J01 conformance record separately lists documented and observed question kinds/cardinalities, request/response limits, model/response versioning, rate limits, retention/privacy, billing units and error semantics. A small account probe confirms only what it actually exercises; connectivity is not complete conformance.

Prefer a documented HTTP transport compatible with core stdlib rules when practical; otherwise isolate an optional bridge and explicitly review its dependency boundary. Default startup must never import an SDK or require access. Unsupported question kinds/cardinalities abstain or report unsupported; do not silently change categories to fit an API. Preserve raw distributions, vendor distribution-derived confidence and local calibration as distinct information.

## Evaluation and adoption

Compare rules, replay where appropriate, the optional current-model baseline when available, and Jev on identical frozen bounded states/questions. Replay is an evidence reproduction control, not a fresh predictor. Report absent optional baselines honestly rather than blocking a useful rules comparison. Separate fixed-policy provider substitution from provider-specific tuning; retain equivalent information/instructions and disclose necessary adaptations. Shadow prediction evaluation cannot establish whole-workflow benefit; follow with protected matched workflow trials, fixed acceptance and full usage accounting.

Predeclare endpoints, quality regression limits, resources, sample/uncertainty and stopping rules through V1. Never import vendor speedup/quality/cost ratios as measured Polytropos outcomes. Calibrate thresholds for the actual target/provider/version/domain; existing-model thresholds are not automatically valid for Jev.

Use V1's exact approval and scoped canary/rollback mechanism. Handle outages, rate limits, invalid/unsupported answers, calibration loss and version drift via bounded retries/circuit breaking, fresh admission and a validated provider-independent fallback. When no safe admitted fallback exists, stop. Record provider response/model version and policy version on every adopted decision; a version change invalidates calibration/applicability when required. Admission accounts for shared provider rate limits and total decision overhead; batch only semantically compatible questions within documented and locally measured limits, without assuming statistical independence. Disabling Jev is a configuration change and works without contacting Jev. In-flight runs retain their pin or safely cancel/reconcile. Never infer that successful connectivity authorizes promotion or all decision families.

## Exit conditions

Offline adapter/error/privacy/budget/fallback conformance, a separately authorized account probe where access exists, independent comparative evidence for any promoted scope, honest per-client support claims and demonstrated Jev-free rollback. A release may leave Jev disabled or shadow-only if it does not earn an active scope. All live observations and unrun probes must be identified separately. This kit never auto-publishes, installs, pushes or merges.
