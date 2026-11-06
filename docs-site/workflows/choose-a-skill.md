# Choose a skill

**Goal:** find the skill that fits the situation you are in, and the one or two that usually go
with it.

Every skill has its own page with a worked example, failure modes, and cost notes; this page
is the map. The **On** column links each harness's version of a skill. A skill missing from a
harness is usually deliberate, and the [parity matrix](../skills/index.md) says why.

## Decide before you run

| Skill | On | Reach for it when | Pairs well with |
|---|---|---|---|
| **route** | [Claude](../skills/claude/route.md) · [Copilot](../skills/copilot/route.md) · [Codex](../skills/codex/route.md) | Before anything expensive or long-running, to see which tier the task needs and what it will cost. | [fable-check](../skills/claude/fable-check.md), [frontier-check](../skills/copilot/frontier-check.md), [escalate](../skills/claude/escalate.md), [architect](../skills/claude/architect.md) |
| **fable-check** | [Claude](../skills/claude/fable-check.md) | Route points at the frontier tier and you want a go/no-go, plus the effort level and task framing to run it well. | [route](../skills/claude/route.md), [escalate](../skills/claude/escalate.md), [architect](../skills/claude/architect.md) |
| **frontier-check** | [Copilot](../skills/copilot/frontier-check.md) · [Codex](../skills/codex/frontier-check.md) | The same question on those harnesses: does this task need the top tier, or will a strong or policy-selected worker do. | [route](../skills/copilot/route.md), [escalate](../skills/copilot/escalate.md), [architect](../skills/copilot/architect.md) |
| **effort** | [Copilot](../skills/copilot/effort.md) · [Codex](../skills/codex/effort.md) | The model is right but the reasoning level is not: raise it on evidence, lower it for routine work. | [route](../skills/copilot/route.md), [escalate](../skills/copilot/escalate.md) |
| **bench-routing** | [Claude](../skills/claude/bench-routing.md) · [Copilot](../skills/copilot/bench-routing.md) · [Codex](../skills/codex/bench-routing.md) | Someone proposes moving a role to a newer or higher-tier model and you want that checked against published benchmarks and, where the ledger has them, this repository's own outcomes. | [repo-bench](../skills/claude/repo-bench.md), [route](../skills/claude/route.md), [execute](../skills/claude/execute.md) |
| **repo-bench** | [Claude](../skills/claude/repo-bench.md) · [Codex](../skills/codex/repo-bench.md) | You want models measured on this repository's own real work before re-tiering or picking a daily driver. Plan-only on Codex. | [bench-routing](../skills/claude/bench-routing.md), [route](../skills/claude/route.md), [execute](../skills/claude/execute.md) |

## Plan and build

| Skill | On | Reach for it when | Pairs well with |
|---|---|---|---|
| **architect** | [Claude](../skills/claude/architect.md) · [Copilot](../skills/copilot/architect.md) · [Codex](../skills/codex/architect.md) | The work is big enough that one wrong early decision compounds: plan once at the top tier and get a kit cheaper models can run. | [execute](../skills/claude/execute.md), [graphify](../skills/claude/graphify.md), [repo-bench](../skills/claude/repo-bench.md) |
| **execute** | [Claude](../skills/claude/execute.md) · [Copilot](../skills/copilot/execute.md) · [Codex](../skills/codex/execute.md) | A kit exists and its tasks need dispatching, independent verification, and a record of what happened. | [architect](../skills/claude/architect.md), [escalate](../skills/claude/escalate.md), [budget](../skills/copilot/budget.md) |
| **escalate** | [Claude](../skills/claude/escalate.md) · [Copilot](../skills/copilot/escalate.md) · [Codex](../skills/codex/escalate.md) | One task with a machine-checkable outcome: try the cheapest sufficient model and climb only when the check fails. | [route](../skills/claude/route.md), [fable-check](../skills/claude/fable-check.md), [frontier-check](../skills/copilot/frontier-check.md) |
| **goliath** | [Copilot](../skills/copilot/goliath.md) | A single Copilot session should run the fullest multi-role review pipeline rather than the base trio. | [architect](../skills/copilot/architect.md), [execute](../skills/copilot/execute.md) |
| **budget** | [Copilot](../skills/copilot/budget.md) | AI Credits are the binding constraint on a kit of routine tasks whose verify commands are strong. | [execute](../skills/copilot/execute.md), [usage](../skills/copilot/usage.md) |
| **graphify** | [Claude](../skills/claude/graphify.md) · [Codex](../skills/codex/graphify.md) | You need repository structure — callers, dependents, impact — before planning or after a change. Needs the external graphify CLI. | [architect](../skills/claude/architect.md), [context-weight](../skills/claude/context-weight.md) |
| **assess-improvement** | [Claude](../skills/claude/assess-improvement.md) · [Codex](../skills/codex/assess-improvement.md) | You want an evidence-backed answer to where a codebase could improve, with handoff briefs and nothing changed. | [architect](../skills/claude/architect.md), [graphify](../skills/claude/graphify.md) |

## See what happened

| Skill | On | Reach for it when | Pairs well with |
|---|---|---|---|
| **cost-report** | [Claude](../skills/claude/cost-report.md) | You want what was actually spent, by model and session, and where a cheaper model would have sufficed. | [route](../skills/claude/route.md), [dashboard](../skills/claude/dashboard.md), [journal](../skills/claude/journal.md) |
| **usage** | [Copilot](../skills/copilot/usage.md) · [Codex](../skills/codex/usage.md) | The same look backward on those harnesses, read from their own local session logs. | [route](../skills/copilot/route.md), [budget](../skills/copilot/budget.md), [journal](../skills/copilot/journal.md) |
| **dashboard** | [Claude](../skills/claude/dashboard.md) | You want one offline page over the attempt ledger, the routing scorecard, and telemetry before deciding what to check next. | [journal](../skills/claude/journal.md), [cost-report](../skills/claude/cost-report.md), [update](../skills/claude/update.md) |
| **journal** | [Claude](../skills/claude/journal.md) · [Copilot](../skills/copilot/journal.md) · [Codex](../skills/codex/journal.md) | End of day: record what happened across harnesses and plan tomorrow. | [memory](../skills/claude/memory.md), [cost-report](../skills/claude/cost-report.md), [usage](../skills/copilot/usage.md) |
| **context-weight** | [Claude](../skills/claude/context-weight.md) · [Copilot](../skills/copilot/context-weight.md) · [Codex](../skills/codex/context-weight.md) | The context window is heavy and you are deciding what to prevent, prune, or measure before compacting. | [graphify](../skills/claude/graphify.md), [execute](../skills/claude/execute.md) |
| **memory** | [Claude](../skills/claude/memory.md) · [Codex](../skills/codex/memory.md) | A fact, preference, or correction should outlive the session, or you want one recalled under a budget. Recall and review only on Codex. | [journal](../skills/claude/journal.md) |
| **lessons-loop** | [Copilot](../skills/copilot/lessons-loop.md) | Right after a correction or an escalation, and at session start to load what applies. | [route](../skills/copilot/route.md), [execute](../skills/copilot/execute.md), [escalate](../skills/copilot/escalate.md) |

## Keep the install healthy

| Skill | On | Reach for it when | Pairs well with |
|---|---|---|---|
| **setup** | [Claude](../skills/claude/setup.md) · [Codex](../skills/codex/setup.md) | You want model, cost, and context visible in the status line. | [update](../skills/claude/update.md), [cost-report](../skills/claude/cost-report.md), [usage](../skills/codex/usage.md) |
| **update** | [Claude](../skills/claude/update.md) · [Codex](../skills/codex/update.md) | After pulling changes, to check every harness install for drift; read-only until you ask for a refresh. | [setup](../skills/claude/setup.md), [doctor](../skills/codex/doctor.md) |
| **doctor** | [Codex](../skills/codex/doctor.md) | A Codex skill is missing, stale, or pointing at an old plugin cache. | [update](../skills/codex/update.md), [setup](../skills/codex/setup.md), [route](../skills/codex/route.md) |

On Claude Code the effort dial is a session setting, and the guidance for it rides inside
[route](../skills/claude/route.md) rather than in a skill of its own.

## Sequences that come up often

- **One expensive task.** Start with [route](../skills/claude/route.md). When it points at the top tier,
  [fable-check](../skills/claude/fable-check.md) or [frontier-check](../skills/copilot/frontier-check.md) decides whether that is warranted. When the task has
  a check that can fail, hand it to [escalate](../skills/claude/escalate.md). [Route one task](first-route.md) walks through
  it.
- **Work too big for one dispatch.** Optionally [graphify](../skills/claude/graphify.md) for a map of the repository, then
  [architect](../skills/claude/architect.md) writes the kit and [execute](../skills/claude/execute.md) runs it. [Run a kit](run-a-kit.md) walks through
  it.
- **Choosing or changing the model mix.** [bench-routing](../skills/claude/bench-routing.md) weighs published benchmarks and
  [repo-bench](../skills/claude/repo-bench.md) measures on your own repository. On Claude Code, [route](../skills/claude/route.md) then uses an
  applied tier map ahead of its own defaults.
- **Tight on Copilot credits.** [route](../skills/copilot/route.md) for the estimate, [budget](../skills/copilot/budget.md) with
  [execute](../skills/copilot/execute.md) for the run, [usage](../skills/copilot/usage.md) afterwards.
- **After the work.** [cost-report](../skills/claude/cost-report.md) or [usage](../skills/copilot/usage.md) for spend, [dashboard](../skills/claude/dashboard.md) for the whole
  picture on Claude Code, [journal](../skills/claude/journal.md) for the day.
  [Measure the savings](measure-the-savings.md) walks through it.
- **What should outlive the session.** [memory](../skills/claude/memory.md) on Claude Code and Codex. Copilot has no
  memory skill yet; [lessons-loop](../skills/copilot/lessons-loop.md) covers the adjacent need there — corrections written down
  so they are not relearned.
- **Housekeeping.** [update](../skills/claude/update.md) after pulling changes, [doctor](../skills/codex/doctor.md) when a Codex skill is
  missing, [setup](../skills/claude/setup.md) once per machine.

## What this page is not

The pairings are suggestions, not rules. Two skills are paired only where at least one harness
carries both, and a pairing links to that harness's page. The skill page is the authority on
what a skill does, what it writes, and what it spends. Cursor's headless harness carries
`assess-improvement` and its own kit driver outside this three-harness matrix; the
[Cursor harness deep dive](../deep-dives/cursor-harness.md) covers it.
