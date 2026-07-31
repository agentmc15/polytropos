# Skills reference

A skill is a bundle of instructions installed under a Copilot home's `skills/` directory,
identified by a `name:` and a `description:` in its frontmatter. Skills are not a separate
program: they steer the current session, running on whatever model that session already has
selected. A skill file never carries a model pin of its own, so a skill's output quality moves
with whichever model you (or a task's `--model` override) have chosen for the session — the
same skill can read very differently on a cheap model than on a frontier one.

There are two ways a skill starts running in a session:

- **Explicit request** — typing something like "use the `/name` skill" (or otherwise naming it) in a prompt tells Copilot to load that specific skill.
- **Auto-load from description** — Copilot can also load a skill on its own when a request's wording matches that skill's `description:` frontmatter closely enough, with no explicit name typed at all.

Neither path makes a skill a true custom slash command the way some other tools' registries
work: there is no user-defined `/name` command grammar underneath, only a description Copilot
matches against, or an explicit mention it recognizes. Treat every skill name in this guide as
"the concept a description names," not as a guaranteed native command.

Useful in-session commands for managing installed skills:

- `/skills reload` — pick up newly installed or changed skills without restarting the session.
- `/skills` — open the skills management view to toggle installed skills on or off.
- `/skills list` — list every currently installed skill.
- `/skills info NAME` — show one installed skill's frontmatter and source path (`NAME` is a placeholder for an installed skill's name).

### Live inventory

The table below is generated directly from the skill files on disk at build time — it is never
hand-typed, so it can never drift from what is actually installed.

<!-- BEGIN GENERATED: skills-inventory -->
Snapshot: `data/pricing.copilot.json` (cached_date 2026-07-25) — pricing sha256 `0e787ee9bdb2a76d74689ab5bbba7d8efea12054b6643c764932564f57b67bb1`, roster sha256 `774e2d66ae13ff6a869f7915c264790802b15be56bb03d9e5355aa0d58363b71`.

| Skill | Description | Source |
|---|---|---|
| `architect` | Do the expensive planning once — deep-plan a complex task and write an execution kit (PLAN.md + TASKS.md with model-pinned, self-contained briefs) under tasks/kits/`<slug>`/ for the execute driver to dispatch on cheaper models. Use when the user says "architect this", "plan this big task", or asks for an execution kit. | `copilot/.github/skills/architect/SKILL.md` |
| `bench-routing` | Decide whether a new or higher model should replace what a role currently runs on — a benchmark-informed routing recommendation. Use when the user asks "should we upgrade X to Y for this role" or wants a benchmark-backed routing check. | `copilot/.github/skills/bench-routing/SKILL.md` |
| `budget` | Run an execution kit on a cheaper ladder of models when the AI-Credits budget is tight — one-tier-lower dispatch with honest actual-vs-standard cost reporting. Use when the user says budget mode, run this cheaply, low on credits, or wants the savings measured. | `copilot/.github/skills/budget/SKILL.md` |
| `context-weight` | Reach for this when your context is huge, cache reads are high, you're asking should I compact, or you want to know what filled the window — it explains what this skill can and cannot do, ranks prevent/prune/measure in priority order, and gives the checkpoint move before you compact. | `copilot/.github/skills/context-weight/SKILL.md` |
| `effort` | Control the reasoning-effort dial for Copilot models — Copilot's per-model "Reasoning" setting, covering which models have it, how to set it, and when to turn it up or down. Use when the user asks to raise/lower reasoning effort, run at extra-high, or make a model think harder or cheaper. | `copilot/.github/skills/effort/SKILL.md` |
| `escalate` | Run one task on the cheapest sufficient model behind a machine-checkable success check, escalating to a stronger tier — frontier last — only if the check fails. Use for "try it cheap first, fall back to the top model if it doesn't work". | `copilot/.github/skills/escalate/SKILL.md` |
| `execute` | Run an execution kit under tasks/kits/`<slug>`/ — drive bin/copilot_execute.py task by task, verify each result, and climb the pricing tiers only on failure. Use when the user says to execute, continue, or resume a kit or plan. | `copilot/.github/skills/execute/SKILL.md` |
| `frontier-check` | Decide whether a task is worth the harness's frontier-tier model versus a strong or mid model, and how to run it optimally — effort, task spec, refusal fallbacks. Use when the user asks "is the top model worth it here" or how to get the most out of it. | `copilot/.github/skills/frontier-check/SKILL.md` |
| `journal` | Generate the daily work journal — collect today's AI usage across Claude Code, Copilot CLI, and Codex CLI plus git activity into a digest, then write the narrative, technical, and next-day-plan summaries. Use when the user asks for their work journal, daily summary, "what did I do today", or to plan tomorrow. | `copilot/.github/skills/journal/SKILL.md` |
| `lessons-loop` | Capture a durable lesson every time the human corrects the agent — or a task escalates models — so the same mistake doesn't recur. Use immediately after any user correction and after any model escalation. Also use at session start to load relevant past lessons. | `copilot/.github/skills/lessons-loop/SKILL.md` |
| `route` | Pick the right Copilot model for a task and estimate its cost in AI Credits before running it. Use when the user asks which model to use, what a task will cost, whether a cheaper model would do, or how much of their plan allowance a job will burn. | `copilot/.github/skills/route/SKILL.md` |
| `usage` | Analyze historical Copilot CLI spend from local session logs — spend by model and session in USD and AI Credits, read-only. Use when the user asks what they've spent, which models they've been using, or where they could save. | `copilot/.github/skills/usage/SKILL.md` |
<!-- END GENERATED: skills-inventory -->

## architect

**When to use it.** You have a complex, multi-step task and want a durable, reusable execution
plan instead of working it out live in the current session.

**How to request it.** Ask for the plan explicitly (for example, "architect this task") so the
skill's description matches, or type `/architect` in a prompt.

**What it does.** It plans only — it never implements anything itself. It writes an execution
kit (a `PLAN.md` plus a `TASKS.md` of self-contained, model-pinned task briefs) under
`tasks/kits/<slug>/` for a later run of the `execute` skill (or the equivalent driver) to
dispatch, task by task, on whichever models each brief pins. It checks active model
preferences before choosing each task's pinned model, so a pin an operator has excluded is
never baked into a new kit. It never creates the kit's `NOTES.md` — that file belongs to the
execute-side driver, not the planner.

**Safety and cost notes.** Producing a plan is authoring work, not code execution — no task in
the kit actually runs until a later `execute` pass dispatches it. Because planning quality
matters most here, run this skill on the strongest model preferences currently allow.

**Same-named agent.** Yes — an isolated `architect` agent exists with the same planning-only
scope; see `AGENTS.md`.

## bench-routing

**When to use it.** You're deciding whether a new or higher model should replace what a role
currently runs on, or you want a benchmark-informed routing recommendation before changing a
default.

**How to request it.** Ask something like "should we upgrade X to Y for this role" or request a
benchmark-backed routing check, so the description matches, or type `/bench-routing`.

**What it does.** It ranks entries from a screenshot-transcribed snapshot of the Artificial
Analysis Intelligence Index (the snapshot carries its own `cached_date` and provenance note,
flagged as re-verify-worthy if stale) and recommends a per-role pick from what this harness can
actually dispatch — availability is derived at run time from `data/pricing.copilot.json`, and a
benchmark entry matching no dispatchable model is never silently dropped: the text card counts
it out of the `N/M benchmark entries dispatchable` total, and `--json` lists it by name under
the `unavailable` key. Its `compare` mode joins that benchmark prior against this repo's
measured kit ledger, but the ledger is Claude-harness evidence covering the implementer role
only — from the Copilot side there is no measured per-role outcome data, so the benchmark's
recommendation stands unchallenged here rather than being backed by borrowed Claude-side
evidence; anyone who wants the measured check should go to the Claude harness. `usd_per_task`
is a ranking ratio computed from the benchmark workload, never a bill and never added to real
spend figures, and the Intelligence Index is a general-capability composite, not a coding or
agentic board, so a routing change for an agentic role needs that caveat stated up front.

**Safety and cost notes.** Read-only over the bundled benchmark snapshot and the pricing file;
it spends nothing and never edits the dataset it reads from.

**Same-named agent.** Yes — an isolated `bench-routing` agent produces the same
benchmark-informed recommendation; see `AGENTS.md`.

## budget

**When to use it.** You're running an execution kit and your AI-Credits budget is tight, or
you just want to see whether a cheaper dispatch ladder would still get the kit done.

**How to request it.** Type `/budget`, or ask to run the kit cheaply, in budget mode, or on a
low-credits ladder, so the description matches.

**What it does.** It demotes the implementer dispatch exactly one tier lower than the task's
standard pin (floor: the cheapest tier), enforced by the driver's `run --budget` flag; the
escalation ladder above that demoted start is completely unchanged, so a verified failure
still climbs back to the tier the task would have started at under standard dispatch. The
reviewer and verifier stay at their standard strength — reviews run at full
strength by design, because a cheap implementer makes that strong-tier review MORE valuable,
not less. The planner's own drop is taught here rather than enforced, since the driver never
dispatches the architect itself; picking its model is left to the person kicking off that run.

**Safety and cost notes.** Every dollar this mode reports is a labeled estimate under a named
task profile — never a bill. A run whose escalations cost more than the demotion saved is
called out as `BACKFIRED`, in the same estimated-dollar terms, rather than being buried in an
otherwise-cheerful summary; a kit-level ledger command totals the recorded runs into one of
a small set of honest verdicts, including a plain statement that budget mode is losing money
on that kit if the numbers say so. That headline net covers only completed (`done`) runs —
blocked runs and runs that made no demotion are reported separately, on their own labeled
lines, never folded into or silently dropped from the net. Preview any real dispatch with a
dry run before spending anything.

**Same-named agent.** No — budget is a skill-only capability in this bundle.

## context-weight

**When to use it.** Your context is huge, cache reads are high, you're wondering whether to
compact, or you want to know what actually filled the window.

**How to request it.** Ask about context size, cache reads, or compaction, or type
`/context-weight`.

**What it does.** It cannot remove anything from a context window itself — skills and agents
are text the model reads, with no mechanism to mutate the message array a call submits; only
the harness can do that. Its job is to tell you when to act and what to act on. On this harness
the underlying engine reports a session-average weight rather than a per-call growth curve,
because Copilot's session logs carry no per-turn input/cache split — that average is the honest
substitute, not a curve in disguise. A live watch threshold is Claude-only; asking for it here
returns an honest refusal instead of a fabricated number, so on this harness you apply its
guidance on a schedule rather than at a threshold. It ranks three levers in priority order —
preventing bulk context from ever entering the window (free and lossless), pruning it after the
fact through compaction (cheap but lossy), and measuring to tell you which of those two is the
right move right now — and it recommends checkpointing decisions and open questions to a notes
file before you compact, since a compaction summary written afterward can only summarize what
survived.

**Safety and cost notes.** Read-only over your own local session logs; it spends nothing and
never mutates anything it reads.

**Same-named agent.** Yes — an isolated `context-weight` agent produces the same read-only
report; see `AGENTS.md`.

## effort

**When to use it.** You want a model to think harder (or more cheaply) on a specific piece of
work, or you're unsure whether the current reasoning setting is worth its cost.

**How to request it.** Ask to raise or lower reasoning effort, or mention running "at extra
high," so the description matches, or type `/effort`.

**What it does.** It reads the reasoning-effort facts straight from
`bin/copilot_pricing.py knobs` and teaches the interactive `/model` picker's left/right
"Reasoning" control — the confirmed way to change a model's effort level. There is no
confirmed headless (non-interactive) flag for this control, so the skill never invents one. It
recommends stepping the effort level up only when there's actual evidence the current level is
struggling (a wrong answer, a missed edge case) — never as a default habit.

**Safety and cost notes.** Higher reasoning effort costs more per turn on models that support
it; the skill only ever nudges the dial, it never silently raises it without telling you.

**Same-named agent.** Yes — an isolated `effort` agent exists with the same advisory scope; see
`AGENTS.md`.

## escalate

**When to use it.** You have exactly one task, a cheapest-plausible model to try first, and a
way to machine-check whether the attempt actually worked.

**How to request it.** Ask to "try it cheap first, fall back to the top model if it doesn't
work," or type `/escalate`.

**What it does.** It requires a genuinely machine-checkable success condition up front (a test
command, a lint, an assertion) — not a subjective judgment call. On failure it retries once on
the same tier before climbing to the next tier, reserving the frontier tier for last. This
skill is for one standalone task; for a whole kit of tasks under `tasks/kits/<slug>/`, use the
`execute` skill's driver instead, which already climbs tiers per task on failure.

**Safety and cost notes.** Every escalation step is triggered by an actual failed check, never
by a hunch — so cost only grows when the cheaper tier demonstrably couldn't do the job.

**Same-named agent.** Yes — an isolated `escalate` agent runs the same one-task, verify-gated
ladder; see `AGENTS.md`.

## execute

**When to use it.** An execution kit already exists under `tasks/kits/<slug>/` (usually written
by `architect`) and you want to drive it to completion.

**How to request it.** Ask to execute, continue, or resume a kit or plan, or type `/execute`.

**What it does.** It drives `bin/copilot_execute.py status/run/review` task by task, and it
runs tasks **serially**, never in parallel. Per the kit contract shared with `architect`, each
task's own `model` field in `TASKS.md` overrides whatever model an implementer persona's
frontmatter might otherwise pin — the task brief always wins. It verifies each task's result
against that task's own verify command before moving on, and climbs tiers only after a
verified failure. There is **no** same-named `execute` agent: this driver role only exists as a
skill.

**Safety and cost notes.** Run a dry-run pass before any real spend so you can see what would
be dispatched and at what cost before it happens.

**Same-named agent.** No — `execute` is a skill-only capability in this bundle.

## frontier-check

**When to use it.** You're not sure whether a task actually needs the frontier-tier model, or
you want the best possible run out of the frontier tier once you've decided to use it.

**How to request it.** Ask "is the top model worth it here," or type `/frontier-check`.

**What it does.** It compares the frontier, strong, and mid tiers at run time (never from a
memorized ranking) and defaults to recommending the strong tier first unless there's genuine
evidence — real task complexity, a documented prior failure — that only the frontier tier will
do. It honors whatever model pins and excludes are active and surfaces any data-freshness notes
the pricing snapshot carries, rather than assuming the roster is unchanged.

**Safety and cost notes.** Frontier-tier runs are the most expensive available; this skill's
whole purpose is to keep that tier from being reached for granted for a task that a cheaper
tier would have handled just as well.

**Same-named agent.** Yes — an isolated `frontier-check` agent makes the same judgment; see
`AGENTS.md`.

## journal

**When to use it.** You want your daily work journal — a digest of what you worked on across
harnesses plus git activity, written up as a narrative and technical summary.

**How to request it.** Ask for your work journal, a daily summary, "what did I do today," or to
plan tomorrow, or type `/journal`.

**What it does.** It first collects the day's activity locally (read-only), then runs
`journal_summarize.py --dry-run` to see the exact prompts that would be sent for
summarization, and writes the actual narrative and technical summaries **in-session** instead.
It never launches the headless Claude-based summarizer subprocess itself from a Copilot
session — that dispatch path stays a dry-run preview only here.

**Safety and cost notes.** Collection is read-only over local session logs; the only spend is
the in-session writing itself, and the dry-run step lets you see the summarizer's prompts
before committing to that spend.

**Same-named agent.** Yes — an isolated `journal` agent runs the same in-session, dry-run-first
flow; see `AGENTS.md`.

## lessons-loop

**When to use it.** Right after a human correction, or right after a task escalates to a
stronger model than originally planned — and also once, at the start of a session, to load
prior lessons.

**How to request it.** This skill is meant to trigger automatically at those moments via its
description; it can also be invoked explicitly with `/lessons-loop`.

**What it does.** At session start it reads `tasks/lessons.md` for relevant prior lessons.
After a correction or an escalation, it appends one concise, project-scoped lesson describing
what went wrong and what to do differently — never a sprawling retrospective.

**Safety and cost notes.** This is a small, cheap append-only write to a plain text file; it
carries no model-dispatch cost of its own beyond the current session's own turn.

**Same-named agent.** No — `lessons-loop` is a skill-only capability in this bundle.

## route

**When to use it.** You want to know which model to use for an upcoming task and what it will
cost before you run it.

**How to request it.** Ask which model to use, what a task will cost, or whether a cheaper
model would do, or type `/route`.

**What it does.** It reads prior routing lessons and active model preferences, classifies the
task into a tier, estimates the cost with the repository's own pricing engine, and recommends
one concrete action — a model to use and roughly what it will cost. It is a forward-looking
decision aid for one upcoming task, not a report of what has already been spent; for that, see
`usage`.

**Safety and cost notes.** Running `route` itself is cheap; its entire purpose is to prevent
overspending on the task it's advising about.

**Same-named agent.** Yes — an isolated `route` agent gives the same advice; see `AGENTS.md`.

## usage

**When to use it.** You want to know what you've actually spent in past Copilot CLI sessions.

**How to request it.** Ask what you've spent, which models you've been using, or where you
could save, or type `/usage`.

**What it does.** It is a strictly read-only historical reporter over your own local Copilot
CLI session text logs. It never invokes the real Copilot CLI and never opens the session-state
SQLite databases — only the plain event logs. Because a session can move across several
different models over its lifetime, its per-session totals are a labeled multi-model
approximation, not an exact per-model ledger. It is also careful to keep AI Usage Units (AIU,
the raw metering unit) and AI Credits (AIC, the billed unit) visibly distinct rather than
treating them as interchangeable numbers.

**Safety and cost notes.** Read-only and offline over your own logs; it spends nothing and
never mutates anything it reads.

**Same-named agent.** Yes — an isolated `usage` agent produces the same read-only report; see
`AGENTS.md`.
