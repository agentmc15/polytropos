# Practical workflows

This guide walks through the day-to-day procedures for using this repository's Copilot CLI
bundle: routing a task to the right model, running a planned kit end to end, verifying and
escalating work, reviewing cost, running the daily journal, tuning reasoning effort, and
feeding the lessons loop. Every command below is copy/paste-safe with `<...>` placeholders — no
live model id, price, or date is typed anywhere on this page; see [`MODELS.md`](MODELS.md) and
[`COSTS.md`](COSTS.md) for those generated facts.

**Skill or agent?** A skill layers instructions onto whatever session you already have open; an
agent switches you into an isolated, separate context that may carry its own configured model.
Reach for a skill to keep working in the current session, and for an agent when you want a
cleanly separate run — or let the driver dispatch one for you, as `execute` does for
`implementer`, `reviewer`, and `verifier`.

**How a skill is actually requested.** Typing `/name` inside a prompt (for example `/route
please size this task`) explicitly requests a skill, and skills can also auto-load when their
own `description:` matches what you're doing. This is not a custom, user-defined Copilot
slash-command registry — it is Copilot's own skill-loading mechanism acting on a
bundle-supplied `description:`, not a command this repository invented.

**Agents and models.** An agent's frontmatter can pin a literal model id, so its behavior is
more predictable across runs than a skill layered onto an arbitrary session — though a kit
task's own `model` field, when the `execute` driver dispatches that agent, overrides whatever
the agent's frontmatter otherwise pins.

**Check active preferences first.** Before trusting a tier name to mean one particular model, or
estimating what something will cost, check active preferences, which is free and read-only:

```bash
python3 bin/copilot_pricing.py prefs
```

A pin or exclude can change which model a tier resolves to, or remove a model from eligibility
entirely.

**Free versus AIC-spending.** Anything that only dry-runs, checks status, reads preferences,
estimates cost, reads knob data, or reads a usage log is model-free and safe to run at any time.
Anything that actually dispatches a skill or agent against a live Copilot CLI session — a real
`/route`, `/architect`, or `/execute` run, or `copilot --agent <NAME> -p "<TASK>"` — spends real
AI Credits (AIC). Every workflow below labels its AIC-spending steps explicitly and pairs each
one with a free predecessor wherever one exists.

## Route a task

Ground a model choice in what has actually been learned and what is currently allowed, rather
than a guess. First, read whatever the lessons loop has recorded for this project (see
[Lessons loop](#lessons-loop) below) and check active preferences with the free command shown
above — a pin or exclude can mean the tier you'd otherwise reach for resolves to a different
model, or isn't eligible at all.

Size the task to a runtime profile instead of guessing a token count by hand, and estimate one
or two plausible tiers before committing — both free and read-only:

```bash
python3 bin/copilot_pricing.py models --profile <PROFILE>
python3 bin/copilot_pricing.py est <PROFILE> <MODEL_ID>
```

Replace `<PROFILE>` with one of the profile keys from `MODELS.md`'s task-profiles table and
`<MODEL_ID>` with one of the model ids from its roster table. Once a candidate looks right, this
is where dispatching actually spends AIC: either request the routing skill explicitly in a
prompt (`/route <describe the task>`) or switch into the `route` agent for an isolated
recommendation.

Keep the two roles separate. A routing recommendation (`route`, or `frontier-check` for the
frontier-worth question specifically) is a *prospective* opinion about upcoming work. A usage
report (see [Usage and cost review](#usage-and-cost-review) below) is a *historical* account of
what has already been spent. Never treat one as a stand-in for the other.

## Architect → execute

This is the two-phase workflow for planning, then running, a larger piece of work as a kit.

Requesting the planning skill or agent (`/architect <describe the goal>`, or the isolated
`architect` agent — **this dispatch spends AIC**) produces a kit under `tasks/kits/<slug>/`: a
plan and a set of self-contained task briefs. It creates only `PLAN.md` and `TASKS.md`; it never
implements anything itself, and it never touches the driver's own `NOTES.md`.

Before dispatching anything against that kit, check its status, which is free and read-only:

```bash
python3 bin/copilot_execute.py status --kit <slug>
```

Preview a run without spending anything:

```bash
python3 bin/copilot_execute.py run --kit <slug> --dry-run
```

Run for real only once the dry-run looks right — this step spends AIC:

```bash
python3 bin/copilot_execute.py run --kit <slug>
```

At a phase boundary, a review pass (the `reviewer` agent, driver-dispatched or invoked by hand —
**AIC-spending**) reads the plan and the completed phase's actual diff for drift, scope creep,
or contract breakage before the next phase starts.

A task's own `model` field in `TASKS.md` is the dispatch pin: when the driver dispatches an
implementer for that task, that field overrides whatever the implementer agent's frontmatter
otherwise pins, on a per-task basis. Execution itself is serial — the driver runs one task at a
time against `bin/copilot_execute.py`, with no parallel-subagent fan-out here. A task marked
`independent:` is safe to run in any order relative to its siblings; it does not mean it runs
concurrently with them. Escalation notes and lesson candidates recorded during a kit run are
written by the execute driver into `NOTES.md` — never by an individual implementer task.

## Verify → escalate

This is the pattern for one task with a machine-checkable outcome, trying the cheapest plausible
tier first.

Before trusting any claim of success, run the task's own verify command yourself, exactly as
written — this predecessor step is usually free, since verify commands are typically tests or
checks, not model dispatches:

```bash
<the task's own verify command>
```

Follow that with independent verification rather than trusting a self-report: a fresh-context
recheck (the `verifier` agent — **AIC-spending**) rechecks the actual files against every
acceptance bullet, never simply trusting the implementer's own claim.

On a failure, retry once on the same tier with the concrete failing evidence attached, not a
vague restatement, before considering any change of model. Climb to a stronger tier only after
that retry also fails, one tier at a time, frontier last — the `escalate` skill or agent (**AIC-spending when dispatched**) encodes exactly this ladder: cheapest sufficient tier first,
escalating only on repeated, evidenced failure, never jumping straight to the frontier tier.

If even the top of the ladder fails the machine check, stop and report that plainly. Do not
force a pass, and do not silently keep retrying past what the evidence supports.

## Usage and cost review

Two different questions, answered by two different commands, never blended together.

Before work, get a prospective estimate — free and read-only:

```bash
python3 bin/copilot_pricing.py est <PROFILE> <MODEL_ID>
```

This forecasts what one task of roughly that size would cost on that model; it is not a record
of anything that has actually happened.

After work, get a historical usage report — also free and read-only, and no real CLI dispatch is
needed to gather it, since it reads locally logged session history that already exists:

```bash
python3 bin/copilot_usage.py --days <N>
```

Interpret the output carefully. Multi-model sessions are attributed by the report to that
session's *last* model at the full-token-split level, which is an approximation rather than an
exact per-model accounting; the report's separate output-tokens-only, per-turn view is the exact
cross-model slice, at the cost of leaving input tokens out of that view. Copilot's own reported
unit is AIU (AI Usage units), shown alongside this repository's own AIC estimate as a
cross-check — the two are never treated as equal or convertible. Any subscription-billed or
API-equivalent figure elsewhere in this repository (for example a relative-burn proxy for a
usage-limited harness) is explicitly labeled as a proxy and never merged into a billed total.
Neither command above requires a live Copilot, Codex, or Claude CLI dispatch to gather its
figures — both work entirely from data already on disk.

## Daily journal

Run the deterministic collector first — free, read-only, and reproducible:

```bash
python3 bin/journal_collect.py --print
```

Preview the summarizer without spending anything:

```bash
python3 bin/journal_summarize.py --dry-run
```

This prints the prompts and the model it would route to; it spawns nothing. Once that preview
looks right, write the actual summaries in-session by requesting the `journal` skill or agent to
produce the narrative, technical, and next-day-plan summaries directly in the current
conversation, rather than launching a separate headless process — **this step spends AIC**.

The collector reads session logs strictly read-only and writes its digest with metadata only,
never transcript text, into a gitignored `journal/` tree, so personal data never lands in git.

An optional next-day plan is advisory, not dispatch: a runbook or plan card is a printed
suggestion for what to pick up tomorrow, and nothing in this repository auto-schedules or
auto-dispatches it. Reading it is free:

```bash
python3 bin/journal_plan.py check
```

## Effort and frontier decision

Read the knob data before assuming a model supports adjustable reasoning effort — free and
read-only:

```bash
python3 bin/copilot_pricing.py knobs
```

Some models expose no reasoning-effort control at all; that is a data-driven fact from the
pricing snapshot, not a guess. The only confirmed mechanism today is the interactive `/model`
picker: change reasoning effort by opening the picker and using its arrow-key Reasoning setting
on the currently selected model row. No headless flag or settings key for this is confirmed —
don't script around one that hasn't been verified to exist.

Increase reasoning effort by one step only on real evidence, not by default — for example a task
that genuinely needed deeper reasoning and visibly ran out of it at the current setting.
Distinguish a thinking-time gap from a capability gap: more reasoning effort on the same model
buys it more time to think within its own capability ceiling, it does not turn a weaker model
into a stronger one. If the failure looks like the model fundamentally lacks the capability
rather than having rushed, that is a tier question (see [Verify → escalate](#verify-escalate)
above), not an effort-knob question.

Prefer a strong-tier model before the frontier tier, unless the evidence says otherwise. The
frontier tier is reserved for work that a strong-tier model has already been given a fair shot
at, with adequate reasoning effort where applicable, and has demonstrably failed — not a default
starting point.

## Lessons loop

Load recorded lessons at the start of a session or task, so past corrections and past
escalations inform the very first routing choice instead of only the next one.

Record a lesson immediately after a human correction, and immediately after any model
escalation. A correction from the person you're working with, or a tier climb during
[Verify → escalate](#verify-escalate) above, is exactly the moment worth capturing, before the
detail is lost to the next task.

Keep each recorded lesson concise and project-scoped: a short, durable rule tied to this
repository's own conventions and past mistakes, not a sprawling narrative and not general advice
that belongs in a model's own training rather than this project's memory.

Feed future routing without hardcoding a model id or a ranking. A lesson should read like
"verify X before trusting Y" or "this kind of task needed escalation last time," not "always use
a specific model id" — the roster and its tiers can and do change, and a lesson that hardcodes
today's model id or its relative ranking goes stale exactly when the pricing data is updated.
