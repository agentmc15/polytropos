# Agents reference

An agent is a persona-isolated capability surface: a separate context you switch a session
into, either through the `/agent` picker or a one-shot dispatch from the command line, rather
than an instruction bundle layered onto whatever session you already have open. Unlike a
skill, an agent's frontmatter can pin a specific model, so an agent's behavior is more
predictable across runs than a skill's — though not absolutely fixed, for two reasons:

- The `execute` skill's driver may pass its own `--model` for a specific kit task, and per the architect/execute kit contract that task-level model overrides whatever the dispatched implementer persona's own frontmatter pins.
- Active repository model preferences (pins/excludes) never rewrite an agent's frontmatter file on disk — they only affect which model a *tier* resolves to elsewhere in this bundle. An agent's own configured model pin is a literal value in its file, not a tier reference, so preferences act on it only insofar as it happens to be excluded (see the inventory below).

One more precedence rule worth knowing before you install anything: Copilot CLI reads custom
agents from both a project's own `.github/agents/` and the user-level Copilot home's `agents/`
directory, and on a name collision the **user-level (home-dir) copy wins**. If you already have
a personal agent with the same name as one of these, installing this bundle will not override
it — your personal copy shadows it everywhere that Copilot home is active.

Several of the agents below (`implementer`, `reviewer`, `verifier`) are internal workflow
personas. They exist to be dispatched by the `execute` skill's driver as it works through a
kit, and are only occasionally invoked by hand.

### Live inventory

The table below is generated directly from the agent files on disk at build time, combined
with the current pricing/preferences snapshot — it is never hand-typed. The **Excluded**
column shows whether that agent's own configured model pin is currently on the active exclude
list; a "yes" there is a **disclosure only** — a flag that this configured pin should not be
dispatched blindly, not a recommendation to swap it for something else. The **Matches active**
column shows whether the agent's configured model happens to be the same model its tier would
currently resolve to elsewhere in this bundle — a "no" is informational, not itself a problem.

<!-- BEGIN GENERATED: agents-inventory -->
Snapshot: `data/pricing.copilot.json` (cached_date 2026-07-25) — pricing sha256 `0e787ee9bdb2a76d74689ab5bbba7d8efea12054b6643c764932564f57b67bb1`, roster sha256 `774e2d66ae13ff6a869f7915c264790802b15be56bb03d9e5355aa0d58363b71`.

| Agent | Description | Model | Tier | Excluded | Matches active |
|---|---|---|---|---|---|
| `architect` | Do the expensive planning once on the frontier model — deep-plan a complex task and write an execution kit (PLAN.md + TASKS.md with model-pinned, self-contained briefs) under tasks/kits/`<slug>`/ for the execute driver to dispatch on cheaper models. Use when the user says "architect this", "plan this big task", or asks for an execution kit. | `claude-fable-5` | frontier | no | yes |
| `bench-routing` | Decide whether a new or higher model should replace what a role currently runs on — a benchmark-informed routing recommendation. Use when the user asks "should we upgrade X to Y for this role" or wants a benchmark-backed routing check. | `claude-sonnet-5` | mid | no | yes |
| `context-weight` | Reach for this when context is huge, cache reads are high, someone's asking should I compact, or you want to know what filled the window — a read-only, isolated report on session-average weight and the prevent/prune/measure levers. | `claude-haiku-4.5` | cheap | no | yes |
| `effort` | Control the reasoning-effort dial for Copilot models — Copilot's per-model "Reasoning" setting, covering which models have it, how to set it, and when to turn it up or down. Use when the user asks to raise/lower reasoning effort, run at extra-high, or make a model think harder or cheaper. | `claude-sonnet-5` | mid | no | yes |
| `escalate` | Run one task on the cheapest sufficient model behind a machine-checkable success check, escalating to a stronger tier — frontier last — only if the check fails. Use for "try it cheap first, fall back to the top model if it doesn't work". | `claude-sonnet-5` | mid | no | yes |
| `frontier-check` | Decide whether a task is worth the harness's frontier-tier model versus a strong or mid model, and how to run it optimally — effort, task spec, refusal fallbacks. Use when the user asks "is the top model worth it here" or how to get the most out of it. | `claude-sonnet-5` | mid | no | yes |
| `implementer` | Execute exactly one task brief from a kit's TASKS.md under tasks/kits/`<slug>`/. Dispatched non-interactively by the execute driver with the task's model as --model (overriding this pin); do one task per invocation and prove it with the task's verify command. | `claude-sonnet-5` | mid | no | yes |
| `journal` | Generate the daily work journal — collect today's AI usage across Claude Code, Copilot CLI, and Codex CLI plus git activity into a digest, then write the narrative, technical, and next-day-plan summaries. Use when the user asks for their work journal, daily summary, "what did I do today", or to plan tomorrow. | `claude-sonnet-5` | mid | no | yes |
| `reviewer` | Phase-boundary review of an execution kit. Read the kit's PLAN.md and the completed phase's tasks, then review the actual diff for drift, scope creep, and contract breakage. Report findings; change nothing. | `claude-opus-4.8` | strong | no | yes |
| `route` | Pick the right Copilot model for a task and estimate its cost in AI Credits before running it. Use when the user asks which model to use, what a task will cost, whether a cheaper model would do, or how much of their plan allowance a job will burn. | `claude-sonnet-5` | mid | no | yes |
| `usage` | Analyze historical Copilot CLI spend from local session logs — spend by model and session in USD and AI Credits, read-only. Use when the user asks what they've spent, which models they've been using, or where they could save. | `claude-haiku-4.5` | cheap | no | yes |
| `verifier` | Fresh-context adversarial verification of one completed kit task. Rerun the task's verify command yourself and check every acceptance bullet against the actual files; never trust the implementer's claims. | `claude-haiku-4.5` | cheap | no | yes |
<!-- END GENERATED: agents-inventory -->

## architect

**When to use it.** The same situations as the `architect` skill: a complex task that needs a
durable, written execution plan before any implementation begins.

**How to invoke it.** Switch into it with `/agent`, or dispatch it one-shot from the command
line.

**What it does.** It is isolated to planning only — it never implements a task itself. It
writes `PLAN.md` and `TASKS.md` under `tasks/kits/<slug>/`, exactly like the `architect` skill,
and it carries its own configured model pin in frontmatter. That pin is a direct, literal model
id in the agent file, so if that specific model id is ever on the active exclude list, treat it
as a disclosure to review before dispatching this agent — not as a silent substitution the
bundle will make for you.

**Same-named skill.** Yes — see `SKILLS.md`.

## bench-routing

**When to use it.** Deciding, in isolation, whether a new or higher model should replace what
a role currently runs on — a benchmark-informed routing recommendation rather than a live
inline judgment call.

**How to invoke it.** Switch into it with `/agent`, or dispatch it one-shot.

**What it does.** The same benchmark-informed recommendation as the `bench-routing` skill: it
ranks entries from a screenshot-transcribed snapshot of the Artificial Analysis Intelligence
Index, picks a per-role candidate from what this harness can actually dispatch (availability
derived at run time from `data/pricing.copilot.json`, with a benchmark entry matching no
dispatchable model never dropped — the text card counts it out of the dispatchable total and
`--json` lists it by name under the `unavailable` key), and is honest that its
measured-outcome check — the `compare` join against this repo's kit ledger — is Claude-harness
evidence covering the implementer role only, so on the Copilot side the benchmark
recommendation stands unchallenged rather than being backed by borrowed Claude-side evidence.
It never treats `usd_per_task` as a bill, and it caveats that the Intelligence Index is a
general-capability composite before recommending a change for an agentic role.

**Same-named skill.** Yes — see `SKILLS.md`.

## context-weight

**When to use it.** A cheap, read-only, isolated look at context weight — context is huge,
cache reads are high, or someone's asking whether to compact — run in its own dispatch rather
than the current session.

**How to invoke it.** Switch into it with `/agent`, or dispatch it one-shot.

**What it does.** The same measurement-only reporter as the `context-weight` skill: it cannot
remove anything from a context window itself — only the harness can do that. On this harness it
reports a session-average weight rather than a per-call growth curve, because Copilot's logs
carry no per-turn input/cache split, and a live watch threshold is Claude-only, so it applies
its prevent/prune/measure guidance on a schedule rather than at a threshold. Because the work is
mechanical log-reading rather than judgment-heavy analysis, this role is configured for a cheap
model.

**Same-named skill.** Yes — see `SKILLS.md`.

## effort

**When to use it.** Deciding whether to raise or lower a model's reasoning-effort setting for
upcoming work, isolated from whatever else the main session is doing.

**How to invoke it.** Switch into it with `/agent`, or dispatch it one-shot.

**What it does.** Same advisory scope as the `effort` skill: it reads the reasoning-effort
facts from the pricing engine and teaches the interactive `/model` picker's Reasoning control,
recommending a step up only when there is real evidence the current level is insufficient.

**Same-named skill.** Yes — see `SKILLS.md`.

## escalate

**When to use it.** One task, a machine-checkable success condition, and a wish to try the
cheapest plausible model before climbing tiers — run as an isolated persona rather than inline
in the current session.

**How to invoke it.** Switch into it with `/agent`, or dispatch it one-shot.

**What it does.** The same verify-gated, tier-climbing ladder as the `escalate` skill: retry
once on the same tier after a failed check, then climb, frontier last, all driven by an actual
machine-checkable result rather than a subjective call.

**Same-named skill.** Yes — see `SKILLS.md`.

## frontier-check

**When to use it.** Judging, in isolation, whether a task genuinely needs the frontier tier
versus a strong or mid-tier model.

**How to invoke it.** Switch into it with `/agent`, or dispatch it one-shot.

**What it does.** The same run-time frontier/strong/mid comparison as the `frontier-check`
skill — defaulting to the strong tier unless there's genuine evidence otherwise, honoring
active pins/excludes and any data-freshness notes.

**Same-named skill.** Yes — see `SKILLS.md`.

## implementer

**When to use it.** Executing exactly one task brief from an execution kit's `TASKS.md`.

**How to invoke it.** Normally you don't invoke this one by hand at all — the `execute` skill's
driver dispatches it non-interactively, one task per invocation, passing that task's own
`model` field as an override of whatever this agent's frontmatter otherwise pins.

**What it does.** It does exactly one task: makes the brief's sanctioned changes, then runs
that task's own verify command itself and reports the verbatim result. It never writes the
kit's task status or `NOTES.md` — both belong to the driver dispatching it, not to this agent.

**Same-named skill.** No — `implementer` is an agent-only workflow role in this bundle.

## journal

**When to use it.** Producing the daily work journal, run as its own isolated persona.

**How to invoke it.** Switch into it with `/agent`, or dispatch it one-shot.

**What it does.** The same read-only-collect-then-dry-run-then-write-in-session flow as the
`journal` skill: it never launches the headless summarizer subprocess itself, only previews its
prompts and writes the actual summaries in this session.

**Same-named skill.** Yes — see `SKILLS.md`.

## reviewer

**When to use it.** At a kit's phase boundary, after a batch of tasks completes, to check the
actual diff against the kit's `PLAN.md` for drift, scope creep, or contract breakage.

**How to invoke it.** Normally driver-dispatched by whatever is running the kit at a phase
boundary; can also be invoked by hand.

**What it does.** It is strictly read-only: it reads the plan and the completed phase's tasks,
reviews the real diff, and reports findings — it changes nothing itself. Because judging drift
and scope creep well takes real reasoning, this role is configured with strong-tier judgment in
mind.

**Same-named skill.** No — `reviewer` is an agent-only workflow role in this bundle.

## route

**When to use it.** Picking a model and estimating cost for an upcoming task, run as its own
isolated persona rather than layered onto an ongoing session.

**How to invoke it.** Switch into it with `/agent`, or dispatch it one-shot.

**What it does.** The same routing-and-cost-estimate advice as the `route` skill: reads
routing lessons and preferences, classifies the tier, estimates cost via the pricing engine,
and recommends one action for one upcoming task.

**Same-named skill.** Yes — see `SKILLS.md`.

## usage

**When to use it.** A cheap, read-only look at historical Copilot CLI spend, run in isolation.

**How to invoke it.** Switch into it with `/agent`, or dispatch it one-shot.

**What it does.** The same strictly read-only reporter as the `usage` skill, over local session
text logs only — never the real Copilot CLI, never the SQLite session stores. Because the work
is mechanical log-reading rather than judgment-heavy analysis, this role is configured for a
cheap model.

**Same-named skill.** Yes — see `SKILLS.md`.

## verifier

**When to use it.** Fresh-context adversarial verification of one already-completed kit task,
after its implementer has reported success.

**How to invoke it.** Normally driver-dispatched right after an implementer reports done; can
also be invoked by hand with just the task id.

**What it does.** It reruns that task's verify command itself, from a fresh context, and checks
every acceptance bullet against the actual files on disk — never trusting the implementer's own
claim. It never applies a fix and never writes the kit's task status; it only reports pass or
fail with evidence. Because the whole point is a cheap, skeptical, mechanical recheck, this role
is configured for a cheap model.

**Same-named skill.** No — `verifier` is an agent-only workflow role in this bundle.

### Skills versus agents at a glance

| Name | Skill | Agent | Notes |
|---|---|---|---|
| `architect` | yes | yes | Planning-only in both forms; the agent adds a direct model pin. |
| `bench-routing` | yes | yes | Same benchmark-informed routing recommendation in both forms. |
| `context-weight` | yes | yes | Same context-weight reporting and levers in both forms. |
| `effort` | yes | yes | Same reasoning-effort advisory scope in both forms. |
| `escalate` | yes | yes | Same one-task, verify-gated ladder in both forms. |
| `execute` | yes | no | Driver role exists only as a skill — there is no `execute` agent. |
| `frontier-check` | yes | yes | Same frontier-worth judgment in both forms. |
| `implementer` | no | yes | Agent-only; normally dispatched by the `execute` skill's driver. |
| `journal` | yes | yes | Same collect-then-dry-run-then-write-in-session flow in both forms. |
| `lessons-loop` | yes | no | Skill-only; triggers on corrections and escalations, no agent form. |
| `reviewer` | no | yes | Agent-only; read-only phase-boundary drift and fence reviewer. |
| `route` | yes | yes | Same routing/cost advice in both forms. |
| `usage` | yes | yes | Same read-only historical reporting in both forms. |
| `verifier` | no | yes | Agent-only; fresh-context adversarial recheck of one task. |
