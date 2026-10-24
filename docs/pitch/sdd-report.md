# Spec-driven development, and where polytropos stands

**A field report on spec-driven development: what it is, how the main tools practice it, the
principles they share, and how polytropos maps to each one.**

> Companions: `docs/pitch/core-four.md` maps Spec Kit's four phases one by one;
> `docs/SPEC-DRIVEN.md` is the long form of how polytropos works; `docs/spec-driven-pitch.html`
> is the short pitch. Claims about other tools come from the sources listed at the end, most of
> them secondary write-ups; each tool's own documentation is the authority on its current
> behavior. Claims about polytropos name the file that makes them true.

## Summary

**Spec-driven development (SDD)** is the practice of writing down what a change must do, and how
it will be checked, before an AI agent writes the code, then holding the agent's work to that
written spec instead of to the conversation that produced it. The idea is old: it echoes
contract-first design and test-first development. What is new is the executor. When the
implementer is a model that can produce a lot of plausible code quickly, the spec becomes the one
fixed point that every step is checked against.

The tools that define the field in 2026, GitHub's Spec Kit, AWS's Kiro, Tessl, OpenSpec and the
BMAD method, share a chain of artifacts: standing project rules, then requirements, then a design,
then a task list, then implementation. They differ in how much ceremony they impose and in how
long the spec lives after the code ships.

**Where polytropos stands.** polytropos is a spec-first SDD system for Claude Code with three
properties the field's tools mostly lack:

1. **Verification is independent of the builder.** The spec carries a verify command and an
   evidence rule for every task, and the orchestrator, a fresh-context verifier and a phase
   reviewer check the work against it. "The implementer's claim of success is not evidence."
2. **The spec is priced.** Every task names the model tier it runs on, so the expensive model
   writes the spec once and cheaper models build against it.
3. **The spec is graded.** A ledger records when a brief itself was wrong, and the next planner
   is told to read those records as evidence about its own briefs.

Its main gaps against the field are a missing cross-artifact consistency pass before the run, no
structured requirements notation, and no living spec that is kept in sync after a change ships.
The last section lists them with a suggested fix for each.

<!-- page -->

## What spec-driven development is

### The problem it answers

An agent given a prompt builds what it understood from the prompt, and reports success in the
same voice whether it succeeded or not. Without a written spec there is nothing outside the
conversation to check the result against, so review falls back to reading the code and trusting
the summary. The usual name for the alternative is "vibe coding": iterate on prompts until the
output looks right.

SDD moves the decisions out of the conversation and into files. Intent, constraints and
acceptance criteria are written before implementation and kept in the repository, where they can
be reviewed like code, read by every agent that touches the change, and checked after the fact.

### The three levels

Birgitta Böckeler's widely cited analysis on martinfowler.com sorts SDD tools into three levels by
how long the spec lives and who edits it:

| Level | What happens to the spec | Example |
|---|---|---|
| **Spec-first** | Written for a change, used to build it, then set aside. | Kiro; Spec Kit in practice |
| **Spec-anchored** | Kept and maintained alongside the code for the feature's lifetime, and used to detect drift. | Spec Kit's stated aim |
| **Spec-as-source** | The only thing people edit; code is regenerated from it. | Tessl (reported as in beta) |

Her finding, as summarized by several sources, is that most tools claim the higher levels and
deliver spec-first. Spec-as-source remains the minority position. Spec-anchored with drift
detection is widely called the defensible middle.

### The artifact chain

Across tools the artifacts line up in the same order, under different names:

| Stage | Purpose | Spec Kit | Kiro | polytropos |
|---|---|---|---|---|
| Standing rules | Rules every change obeys | `constitution.md` | steering files | `CLAUDE.md` invariants; each kit's `GUARDRAILS.md` |
| Requirements | What and why, no design | spec (stories, scenarios) | `requirements.md` (EARS) | the spec half of `PLAN.md` |
| Design | How, with reasons | plan plus research, data model, contracts | `design.md` | the design half of `PLAN.md` |
| Tasks | Ordered, checkable work | tasks with ids and parallel markers | `tasks.md` | `TASKS.md` |
| Implementation | Build against the tasks | implement | run tasks | `/polytropos:execute` |
| Verification | Prove it matches | checklists; analyze | hooks, tests | verify command, verifier, reviewer, red-green rule |
| Feedback | Learn from the run | none | none | the `NOTES.md` ledger and `bin/routing_scorecard.py` |

<!-- page -->

## The landscape

| Tool | Shape | Level | Distinctive |
|---|---|---|---|
| **GitHub Spec Kit** | Open-source toolkit of slash commands and templates for many agents | spec-first, aiming at anchored | A project constitution; Specify, Plan, Tasks, Implement, with optional clarify and analyze steps |
| **Kiro (AWS)** | An agentic IDE with specs built in | spec-first | Requirements in EARS notation ("WHEN … THE SYSTEM SHALL …"); approval gates between phases; steering files; agent hooks on file events |
| **Tessl** | A framework and registry built around specs | anchored, aiming at as-source | One spec per file; generated code marked as not to be edited |
| **OpenSpec** | A lightweight, tool-neutral spec format | spec-anchored | Change proposals written as deltas (added, modified, removed) against a living spec; suited to brownfield work |
| **BMAD method** | A full methodology with specialized agent personas | spec-first | Analyst, product, architect and developer roles hand work along a phase pipeline; heavy, aimed at greenfield and regulated work |
| **polytropos** | A Claude Code plugin with headless drivers for other harnesses | spec-first, with the record kept | Model tier pinned per task; independent verification; a ledger that grades the spec and the models |

Practitioner comparisons consistently place these tools on a ceremony scale, with OpenSpec
lightest, Spec Kit in the middle and BMAD heaviest, and report run time and cost growing with the
ceremony. Those comparisons are single-author trials with their own rubrics, not controlled
benchmarks.

polytropos sits nearest Spec Kit and Kiro in shape: a spec, a design and a task list, written
once per change. It differs from all of them in where it puts its effort. The others concentrate
on producing a good spec. polytropos assumes a good spec and concentrates on the part after it:
who builds against it, at what price, and how the result is proved and measured.

<!-- page -->

## The principles, and how polytropos meets them

These ten principles recur across the tools, Böckeler's analysis and the practitioner literature.
Each is mapped to the polytropos mechanism that meets it, or marked where it does not.

| # | Principle | polytropos | Rating |
|---|---|---|---|
| P1 | **Intent before implementation.** The what and why are written before any design or code. | `PLAN.md` opens with the spec: the goal, a checkable "done", constraints and an out-of-scope fence, under the rule "what and why, no design yet" (`skills/architect/SKILL.md`). | Strong |
| P2 | **A human approves the spec.** Requirements are signed off before design starts. | The architect's approval pause: it shows the spec draft and writes nothing to disk until the user approves. Skipping it must be asked for and is disclosed in the handoff. | Strong |
| P3 | **Standing rules.** Project-wide constraints apply to every change. | `CLAUDE.md` holds always-on invariants. Each kit's `GUARDRAILS.md` holds rules for that change only, re-read from disk at every phase start. | Strong |
| P4 | **Testable acceptance.** Each requirement can be checked. | Every task carries acceptance criteria and a shell verify command. The `red-green` evidence rule rejects a check that could never have failed. | Strong at task level; no notation for requirements |
| P5 | **Design with reasons.** Decisions are recorded with their rationale. | `PLAN.md` decisions carry rationale "so a cheaper model can make consistent micro-decisions later", plus risks with tripwires. | Strong |
| P6 | **Small, ordered, traceable tasks.** | `TASKS.md` blocks with ids, phases and `depends:`/`independent:`; `bin/kit_contract.py graph` rejects duplicates, unknown or self dependencies, and cycles. | Strong; no requirement-to-task ids |
| P7 | **Build against the spec, verified independently.** | The orchestrator runs every verify command itself; a fresh-context verifier and an `opus` phase reviewer check the work against the kit, never against the implementer's report. | Strongest in the field |
| P8 | **Keep spec and code in sync.** Drift is detected. | During a run, the phase reviewer checks for drift from `PLAN.md`. After a kit is done, nothing keeps its spec in sync with later changes. | Partial |
| P9 | **Change management.** Changes to existing behavior are specified as changes. | A kit is one change, and its out-of-scope fence bounds it. There is no delta format against a standing spec. | Partial |
| P10 | **Right-sized ceremony.** Small changes do not pay for a full spec. | `/polytropos:route` picks a model for a single task without a kit, and `workflow: direct` drops independent review for low-risk kits. There is no rule for when a change needs a kit. | Partial |

Two further principles are rarely stated by the other tools and are central to polytropos:

- **P11 · Spend judgment where it pays.** The spec is written once on the frontier tier, and each
  task is pinned to the cheapest tier that can do it: `sonnet` by default, `opus` for the hard
  ones, `haiku` for mechanical ones. After planning, the frontier is reached only when a task
  fails: interactively, through a consult that carries that task's brief and failure evidence;
  headless, through the driver's escalation ladder.
- **P12 · Measure the spec, not just the code.** Every outcome, review and confirmed brief defect
  lands in `NOTES.md` in the grammar of `skills/execute/references/ledger.md`.
  `python3 bin/routing_scorecard.py --history` reports per-tier and per-role quality across every
  kit, and the architect is told to read recurring defect kinds "as evidence about YOUR OWN
  briefs".

<!-- page -->

## Framework by framework

### Spec Kit

The closest match, mapped phase by phase in `docs/pitch/core-four.md`. Specify becomes the spec
half of `PLAN.md` with the approval pause. Plan becomes the design half. Tasks becomes `TASKS.md`.
Implement becomes the execute loop. The constitution splits between `CLAUDE.md` and
`GUARDRAILS.md`. Clarify becomes the scoping questions and the open questions listed under the
spec draft. Analyze has only a structural counterpart, the graph check, plus after-the-fact drift
review.

### Kiro

Kiro's `requirements.md`, `design.md` and `tasks.md` correspond to the two halves of `PLAN.md`
and to `TASKS.md`. Its approval gates between phases correspond to the approval pause, though
polytropos gates only once, after the spec, not after the design. Steering files correspond to
`CLAUDE.md` and `GUARDRAILS.md`. Kiro's hooks run agent actions on file events. polytropos has no
file-event hooks; its checks run at fixed points in the loop instead: after each task, at each
phase end, and at each phase start. Kiro's EARS notation has no polytropos counterpart.
Acceptance in polytropos is written as checkable prose plus a command.

### OpenSpec

OpenSpec keeps a living spec and writes each change as a delta against it. polytropos writes a
fresh, self-contained spec per change and keeps the finished kit in the repository as a record,
not as a living spec. For brownfield work this is the largest structural difference. In
polytropos the "current spec" of the system is the code plus `CLAUDE.md`, not an accumulated
spec document.

### BMAD

BMAD hands work between persona agents (analyst, product manager, architect, developer, QA).
polytropos has a role pipeline too: the standing implementer, verifier and reviewer, and seven
optional roles declared on a `roles:` line (`scout`, `test-author`, `second-verifier`, `red-team`,
`security-auditor`, `docs-editor`, `synthesizer`). The difference is that polytropos roles are
opt-in per kit and measured. `python3 bin/routing_scorecard.py --roles` reports each role's
findings, confirmed findings and marginal catches, and the routing guidance says to keep a role
only "when its measured marginal value earns its measured cost".

### Tessl

Tessl aims at spec-as-source: people edit specs and code is regenerated. polytropos explicitly
does not. Its own pitch says it is "not code generation from a formal spec": the spec is prose
plus shell commands, and a model reads the brief and writes the change. What polytropos offers
instead of determinism is verification. A rerun may write different code, and the same verify
commands, evidence rule and reviewers judge it either way.

<!-- page -->

## What polytropos adds to the field

- **Independent verification as part of the contract.** Most tools check work with tests the
  agent itself writes or runs. polytropos makes the orchestrator run each verify command itself,
  dispatches a fresh-context verifier with read-only tools, and gates each phase on an `opus`
  review against `PLAN.md`. Under `evidence: red-green`, a verify that already passed before the
  work means the task is blocked, not done.
- **A stop-and-report rule.** When a brief conflicts with the repo, the executor stops and
  reports instead of improvising. Nobody changes a task's scope or acceptance to make it pass;
  the conflict becomes a `defect:` line and a question for the user.
- **Cost-tiered execution.** The spec names a model tier per task. `/polytropos:route` estimates
  cost before a run, and `python3 bin/routing_scorecard.py <slug> --session <id>` prices a
  finished kit against an all-frontier counterfactual, both from `data/pricing.json`.
- **A graded spec.** The `defect:` ledger records each confirmed brief defect by kind, such as
  `stale-pin`, `tautological-verify`, `unspecified-path` and `contradictory-acceptance`. The
  architect reads which kinds recur before writing the next kit.
- **Bounded autonomy.** Re-routing is advisory by default. Under `autonomy: auto` it moves
  pending tasks up one tier, never down and never to the frontier. A `budget:` line caps
  dispatches and consults, and a run that hits a cap stops and says so.
- **One spec, several harnesses.** The same kit runs interactively in Claude Code or headless
  through `bin/claude_execute.py`, `bin/copilot_execute.py`, `bin/codex_execute.py` and
  `bin/cursor_execute.py`. The headless drivers run verify commands inside `bin/exec_policy.py`
  and record every dispatch in `bin/attempt_ledger.py`.

## The criticisms of SDD, and how polytropos answers them

| Criticism | polytropos's answer | Still open |
|---|---|---|
| **It is waterfall again.** Specs are written up front and reality changes. | Specs are per change, not per product, and a spec that cannot hold goes back to the user instead of being rewritten silently. | The design is still fixed before tasks run. There is no mid-run re-plan step short of a stop. |
| **The ceremony outweighs small changes.** | `/polytropos:route` for single tasks; `workflow: direct` for low-risk kits; optional roles are off unless declared. | There is no stated threshold for when a change needs a kit. |
| **Specs drift from code.** | Phase-end drift review against `PLAN.md`; fences re-read from disk at every phase start. | Nothing checks a finished kit's spec against later changes. |
| **Matching a wrong spec is false confidence.** | The approval pause catches misread intent early. The `defect:` ledger records specs that turned out wrong. | The pitch says it plainly: "The checks cover what the architect thought to check." |
| **Review burden moves from code to verbose specs.** | The brief must be self-contained but not prescriptive: "pin down contracts and interfaces precisely; leave implementation judgment open". | No size limit on a kit; a large change still produces a large `TASKS.md`. |
| **Regeneration is non-deterministic.** | polytropos does not regenerate from specs. It verifies whatever was written. | Not applicable. |
| **The evidence base is thin.** | The ledger and scorecard turn every kit into recorded evidence about tiers, roles and briefs. | That evidence is per-user and per-repo, not a controlled study. |

<!-- page -->

## Gaps and recommendations

Each gap below is something a field tool does that polytropos does not. They are ordered by
expected value. None is built; each would be its own kit.

1. **A pre-run consistency check.** *Gap:* Spec Kit's analyze step checks the artifacts against
   each other before implementation, and polytropos checks only the task graph's structure.
   *Suggestion:* extend `bin/kit_contract.py` or add an architect step that checks every `PLAN.md`
   goal and constraint is covered by some task's acceptance, and that every task traces to the
   plan. It would run read-only, before the first dispatch.
2. **Traceable requirement ids.** *Gap:* Kiro and Spec Kit give requirements ids that tasks
   reference. *Suggestion:* an optional id on each `PLAN.md` goal line, and an optional
   `covers:` field on tasks. Because the task-field contract is shared by the architect and
   execute skills and `bin/kit_contract.py`, this would need all three changed together.
3. **Structured acceptance notation.** *Gap:* EARS makes requirements testable by form.
   *Suggestion:* recommend, not require, a WHEN/THEN form for the "done" line in `PLAN.md`, so
   each condition maps to one verify command.
4. **A spec-anchored afterlife.** *Gap:* finished kits are kept as records but never re-checked.
   *Suggestion:* a read-only command that re-runs a done kit's verify commands against the
   current tree and reports which no longer pass. That is a drift detector built from checks that
   already exist.
5. **Change deltas for brownfield work.** *Gap:* OpenSpec's added/modified/removed format.
   *Suggestion:* an optional `PLAN.md` section listing the behaviors the change adds, modifies
   and removes, reviewed in the approval pause.
6. **A ceremony threshold.** *Gap:* no tool, polytropos included, states when a change is too
   small for a spec. *Suggestion:* a rule in the architect or route skill, backed by
   `--history`, for routing small changes to a single dispatch instead of a kit.

## Run it

```text
/polytropos:architect <task>                # spec, approval pause, design, tasks
/polytropos:execute <slug>                  # build and verify on the pinned tiers
python3 bin/routing_scorecard.py --history  # the record across every kit
python3 bin/routing_scorecard.py --roles    # what each review role has caught
```

## Sources

On spec-driven development and its levels:
[Böckeler, "Understanding Spec-Driven-Development: Kiro, spec-kit, and Tessl" (martinfowler.com, via a summary)](https://www.alldevblogs.com/article/martin-fowler/understanding-spec-driven-development-kiro-spec-kit-and-tessl);
[Wikipedia: Spec-driven development](https://en.wikipedia.org/wiki/Spec-driven_development);
[Spec Kit vs Kiro vs Tessl (Particula)](https://particula.tech/blog/spec-driven-development-tools-spec-kit-vs-kiro-vs-tessl).
On Spec Kit:
[Augment Code practical guide](https://www.augmentcode.com/guides/github-spec-kit-practical-guide-sdd-workflow);
[Perficient core-commands guide](https://blogs.perficient.com/getting-started-with-github-spec-kit-installation-and-core-commands/).
On Kiro:
[Kiro docs: first project](https://kiro.dev/docs/getting-started/first-project/);
[Smile: Kiro, AWS's agentic IDE](https://smile.eu/en/publications-and-events/kiro-aws-s-agentic-ide-spec-driven-development).
On OpenSpec, BMAD and the criticisms:
[OpenSpec vs Spec Kit vs BMAD vs Kiro](https://openspec.pro/comparison/);
[BMAD vs OpenSpec (FAUN)](https://faun.dev/toolbox/bmad-method-vs-openspec/);
[Spec Driven Development: what it fixes (and breaks)](https://dev.to/mudassirworks/spec-driven-development-what-it-fixes-and-breaks-1co3);
[Spec-driven development in 2026 (DEV Community)](https://dev.to/krlz/spec-driven-development-in-2026-what-it-is-the-tooling-and-how-teams-actually-use-it-2fk2).

Long form for polytropos: docs/SPEC-DRIVEN.md · Source: github.com/agentmc15/polytropos
