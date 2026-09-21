# ADR: decision and improvement, Release 1

- **Status:** accepted for Release 1 scope; superseded only by a later ADR, never by a task brief.
- **Date:** 2026-09-16.
- **Observed revision:** `e6cf4bd6c86daac53ac99d4d484c4bb802b84bb5`.
- **Kit baseline:** `aab755378975e9191db6ced16ee07a27a414af21`.
- **Kit:** `.claude/kits/decision-improvement-v1`, architecture in
  `tasks/kits/decision-improvement/PLAN.md`.
- **Companion:** `docs/DECISION-IMPROVEMENT-RECONCILIATION.md` and its JSON twin carry the evidence
  this decision rests on. This document records the decision; that one records the facts.

## Context

Original roadmap steps 16 through 26 are implemented foundations at the observed revision, not work
to be rebuilt. The reconciliation classifies them: seven implemented (16, 17, 18, 20, 22, 23, 26),
three partial (19, 21, 25), one unverified (24), none pending. The steps are named rather than only
counted, so this sentence cannot drift out of agreement with the JSON that decides it.
Between the kit's baseline and this HEAD, six commits landed — three Claude and Cursor
verification commits the plan had recorded as living on a separate branch, plus a Codex fingerprint
fix, an evaluation plan, and the first live workflow evaluation. All four installed clients now carry
dated verification rows. That is a materially better evidence position than the plan assumed, and it
must not be rolled back to the snapshot.

What the repository does **not** have is a way to ask whether a small change to how it decides things
actually helped. Attempt records do not identify the policy bundle, acceptance version, admission or
component provenance that produced them, so outcomes cannot be attributed. `bin/workflow_eval.py` can
compare whole workflows, but its one live run mined a single task and fell below its own evidence
floor, so it has verified a pipeline and ranked nothing. `SECURITY.md` explicitly disclaims
confinement of candidates, judges and controller state, so no live comparison can yet be called
protected. Meanwhile `bin/routing_policy.py` has no caller in two of four drivers and
`bin/graph_ground.py` has no driver caller at all, so two capabilities that look available are not
actually wired to anything in production.

An improvement loop built on top of that would measure its own noise.

## Decision

Build a Jev-free, human-gated, data-only method for testing and retaining small improvements, in that
order of prerequisite: evidence first, isolation second, typed decisions third, and a falsifiable
experiment only after those hold.

**Jev-free.** Release 1 must start, work and roll back with every optional provider absent. No
endpoint, SDK, model identifier, credential or price for an unpublished provider is assumed anywhere.
An optional provider is a Release 2 decision behind its own gate, reached through the same contracts,
and its absence is the normal case rather than a degraded one. Research statements supplied as design
motivation are motivation; they are not revalidated API contracts and none is treated as measured.

**Human-gated.** A model's judgment is bounded, typed advice. Deterministic policy chooses the
action, existing runtime authorities enforce the constraint, and independent evaluation decides
whether anything helped. A provider cannot execute a tool, grant a permission, raise a budget, modify
the task graph, remove mandatory review, accept an artifact, alter controller logic or approve a
candidate — none of that authority lives in candidate data. Eligibility, capability, privacy and
atomic admission are rechecked immediately before the action they gate. Invalid or unavailable advice
takes an approved fallback or stops; it never routes around a denial. A proposer cannot approve
itself, and `canary` and `active` machine-refuse without a verified named protected profile,
immutable grouped partitions with exposure history, complete predeclared trial inputs, and approval
bound to exact hashes and scope.

**Data-only.** Candidates are bounded, allowlisted data diffs. No candidate edits arbitrary Python,
shell, module paths, acceptance criteria, permissions, pricing, skills, lessons, the improvement
procedure or hidden evaluation rules. Policy bundles are immutable data. Hashes identify content;
they protect nothing against an unrestricted worker, and this design never treats one as a boundary.

**Legacy is the default and stays that way.** Current deterministic behaviour is wrapped as a named
legacy bundle, `reserved` remains the default, and an absent active pointer means existing behaviour
continues. `prefs/routing-policy.json` is read by `bin/workflow_eval.py` and by no driver; it stays
pull-only until an explicit, versioned opt-in lands. No existing preference file becomes executable
policy by being renamed.

**One owner per concern.** The five proposed modules are boundaries, not a framework to impose.
Existing authorities keep their jobs: `bin/kit_contract.py` for task grammar, readiness, roles and
admission; `bin/attempt_ledger.py` and `bin/attempt_history.py` for durable events and their
projections; `bin/proc_runner.py`, `bin/safe_paths.py` and `bin/exec_policy.py` for process, path and
execution confinement; `bin/repo_bench.py` for mining, sandboxes and oracles; `bin/workflow_eval.py`
as the sole evaluation envelope writer and the sole policy-persistence owner; `bin/runtime_data.py`
and `bin/redact.py` for private storage and redaction; `bin/release_gate.py` with
`primitives/harness-capabilities.json` for release claims. The improvement workbench writes no
benchmark result and no attempt event directly. If equivalent functionality lands before a task runs,
that task extends it instead of adding a second copy.

**Honesty about what has not been shown.** An offline edition may ship with protected live
experiments unavailable, and that is an offline, advisory edition rather than a claim that the
protected gate passed. No performance gain is required for a valid mechanism release: a well-run
trial that retains the baseline is a valid outcome. Cost per accepted task includes failures in its
numerator and is undefined at zero accepted tasks. `unknown` in the capability registry means no.

## Consequences

**Accepted costs.** Evidence and isolation work comes before any measured improvement, so the first
visible result of this kit is better bookkeeping rather than a faster or cheaper run. Two of the
prerequisites this kit would most like to lean on are not wired into production — routing decisions
reach only the Codex driver, and grounded prompts reach no driver — so the context-repair hypothesis
has to build its own seam before it can test anything. Concurrency stays off by default; sequential
execution remains the rule and no parallel mutation happens in one checkout.

**What is gained.** Outcomes become attributable, because every attempt will carry the policy,
decision, admission and acceptance identity that produced it, with historical omissions loaded as
`unknown` rather than backfilled. A proposal becomes falsifiable, because it must carry supporting
and contradicting attempts, an expected tradeoff and a falsification test. Promotion becomes
reversible, because rollback selects a previously approved compatible bundle for future runs without
contacting any optional provider, while in-flight runs finish under their pin.

**What this does not promise.** Nothing here makes dispatch confined, makes execution state
tamper-proof, or makes an attempt exactly-once. The ledger knows a call was made, closes a resultless
one as `unknown`, never replays it, and cannot know whether the provider billed it. Rollback never
resets a user's workspace, erases evidence, reverses an external effect or refunds a call. A worktree
is not a sandbox and neither is a scheduler's copy.

## Alternatives considered

- **Extract a general decision framework first, then find uses for it.** Rejected: it would add a
  second copy of logic `bin/kit_contract.py` and `bin/workflow_eval.py` already own, and a framework
  with no measured pain signal is machinery, not improvement.
- **Run the first live experiment now, on the evidence that exists.** Rejected: the one live
  evaluation admitted a single task and sat below its own evidence floor, and the protected profile
  is unverified. A comparison run under those conditions produces a number nobody may act on.
- **Let an applied preference file become active policy.** Rejected: it converts a deliberately
  pull-only artifact into runtime authority without an approval, an evaluation or a rollback target.
- **Assume the optional provider and treat its absence as degraded.** Rejected: it makes Release 1
  depend on something unpublished and turns every honest `unknown` into an optimistic default.
- **Repair the two baseline test limitations inside this kit.** Rejected: one is a test assumption
  about checkout shape owned by the lessons and journal surface, the other is a latent scheduler race
  that did not reproduce at this HEAD. Both are recorded in the reconciliation with their exact
  mechanism and left to their owners; folding an unrelated repair into a decision task would hide it.

## Compliance

This ADR and its companion reconciliation are documentation. They changed nothing under `bin/`,
`tests/`, `data/` or `primitives/`, edited no capability row, rescheduled no completed work, and
downgraded no live evidence. Two genuinely stale planning paragraphs were revised as documented plan
revisions and are listed in the reconciliation; dated delivery receipts were deliberately left
untouched.
