---
name: execute
description: Run an execution kit produced by /polytropos:architect — loop through TASKS.md, dispatching each task to the kit's model-pinned subagents, verifying, and updating state. Use when the user says to execute/continue/resume a kit or plan. Args: the kit slug (optional if only one kit is active).
---

# Kit execution loop

You are the orchestrator, running on the daily-driver model. The expensive thinking is already done — your job is faithful dispatch, verification, and state-keeping. Do not re-litigate the plan.

## Setup

1. Locate the kit: `.claude/kits/<slug>/` (from args, or auto-detect the single kit with pending tasks; if several, ask which).
2. Read `PLAN.md` (goal, constraints, tripwires), the kit's `GUARDRAILS.md` when present (kit-scoped fences — binding for every task in this kit, and passed along to implementers by reference), and `TASKS.md`. This Setup read is the FIRST read of the fences, not the only one — see **Re-reading the fences — phase starts guaranteed, compaction best-effort** below. Read the autonomy dial once here: an explicit user instruction at invocation ("execute <slug> autonomously" / "advisory") wins for this run, else PLAN.md's optional `autonomy:` line (`advisory` or `auto`), else `advisory` (see **Live re-routing — upgrade-only, autonomy-gated** below). Also read PLAN.md's optional `budget:` line once here (see **Budget dial — optional dispatch/escalation/consult cap** below) — absent means unbounded, today's behavior — and its optional `roles:` line once here too (see **Roles roster — optional extended roles, measured** below) — absent means the standing trio, today's behavior.
3. If the target project is aesop-managed (`aesop.yaml` at its root, or an `<!-- aesop:begin` fence in `CLAUDE.md`/`AGENTS.md`): treat those compiled files as read-only. Any guardrail change a task needs goes into `aesop.yaml` (`primitives.instructions.blocks`) followed by `aesop compile` — never a hand-edit of a fenced file. Kit files (`PLAN.md`, `TASKS.md`, `NOTES.md`) and kit-prefixed agents are outside aesop's management and are updated normally.

## Operating rule — lean driver

Your own context is the single most expensive artifact of the run — it is priced, cached,
and re-sent on every subsequent turn, and every inline read brings compaction closer. Take
minimal actions:

- Read only kit state — PLAN.md, GUARDRAILS.md, TASKS.md, NOTES.md — plus the output of verify
  commands you run. Do not inline-read source files, implementer diffs, or logs to "get oriented".
- Delegate every exploratory read, grep, and "what does this file look like now" question to
  a cheap scout subagent (Agent tool, `model: haiku`) that returns a few-line conclusion —
  never file dumps.
- Delegate independent verification the same way (the kit's verifier agent): you consume
  verdicts, not evidence dumps.
- You still run each task's verify command yourself — its exit status is orchestrator-owned
  evidence — but keep only the decisive tail of long output, and hand failure investigation
  to a scout instead of digging inline.
- Keep NOTES.md terse: outcomes and learnings, never transcripts.

Default posture: delegate and monitor. You touch files directly only to keep TASKS.md and
NOTES.md state current.

## The loop

For each task in order (skip `done`, stop at `blocked` deps):

1. **Mark** it `in-progress` in TASKS.md.
2. If PLAN.md declared a **Budget dial** (below), check it FIRST — a cap already reached stops here, before dispatch. Otherwise, **Dispatch** to the kit's implementer agent, passing the task's `model` value as the Agent tool's `model` parameter — that parameter overrides the agent's frontmatter default, so the task's pin wins. If the kit has no implementer agent, use the Agent tool directly with that model. Pass the task's self-contained brief verbatim plus nothing else — the brief is designed to be sufficient. Do not pad it with your own interpretation. Choose the dispatch mode per **Dispatch modes — fresh fan-out vs warm sidekick** below. When a logged `mode=applied` re-route covers this task, pass the upgraded alias as the `model` parameter instead — the task's `model` field stays the dispatch default and is never rewritten (see **Live re-routing — upgrade-only, autonomy-gated** below).
3. **Verify independently**: run the task's verify command yourself, and for non-trivial tasks also dispatch the kit's verifier agent (fresh context, adversarial). The implementer's claim of success is not evidence. Stay lean while verifying (see **Operating rule — lean driver**): take the verifier's verdict, not its evidence dumps.
4. **On pass**: mark `done`, note anything learned that later tasks need (append to a `NOTES.md` in the kit dir), and append the task's `outcome:` line (see **Outcome ledger** below). A fresh outcome line is a fresh signal — consult **Live re-routing — upgrade-only, autonomy-gated** below before the next dispatch.
5. **On fail**: retry once, giving the implementer the failure output. If it fails again, mark `blocked` with the failure details, append its `outcome:` line (`result=blocked`), and move to the next independent task.
6. **Phase boundaries**: when TASKS.md marks a phase end, dispatch the kit's reviewer agent (opus) to check the phase against PLAN.md before continuing, then adjudicate its findings and append the phase's `reviewer:` line (see **Role ledger — reviewer verdicts and brief defects**). Every phase end is also the next phase's start: before step 1 of that phase's first task, re-read the fences (see **Re-reading the fences — phase starts guaranteed, compaction best-effort** below).

Run parallel dispatches for tasks TASKS.md marks as independent — one message, multiple Agent calls.

## Re-reading the fences — phase starts guaranteed, compaction best-effort

Constraints are the first content compaction erases: the kit's `GUARDRAILS.md` and PLAN.md's
out-of-scope fence are read once at Setup and contribute nothing to any later turn's output,
so a context rewrite drops them long before it drops the code you were just editing — and
accumulation does the same job slowly, as a carry-forward warning gets buried in a NOTES.md
that has grown past what anyone re-reads. So **re-READ the fences from disk; remembering them
is the part that fails.**

Two anchors, and they are NOT equally strong. Say which one you are honoring rather than
implying the finer one:

- **Every phase start — a guarantee.** Before dispatching the first task of each phase
  (including phase 1, right after Setup), re-read the kit's `GUARDRAILS.md` and PLAN.md's
  constraints/out-of-scope section from disk. A phase boundary is marked in TASKS.md, so you
  can always detect it: this anchor is unconditional, and no phase begins on remembered
  fences. These two small kit files are kit state, which the **Operating rule — lean driver**
  posture above reads directly rather than delegating — never hand this read to a scout, and
  never let "I read GUARDRAILS.md at Setup" stand in for it.
- **Any point you observe your context was compacted — best-effort.** This skill cannot
  detect compaction: nothing notifies the loop when a rewrite happens, so this anchor fires
  only when you happen to notice the evidence (a summarized transcript, earlier detail you
  can no longer see, a compaction notice in your own context). Treat it as an opportunistic
  extra, never as coverage — if compaction lands mid-phase and you miss it, the phase-start
  re-read above is what catches it.

The coarser guarantee is deliberate: an honest phase-boundary rule the loop can always honor
beats a compaction-triggered one it would only appear to honor.

## Dispatch modes — fresh fan-out vs warm sidekick

Fresh, parallel subagents remain the default for tasks marked `independent:` with disjoint
files — one message, multiple Agent calls, no shared state (this rule is unchanged).

For a **cohesive cluster**, keep ONE warm implementer instead of paying N cold prompt-cache
starts: spawn it for the cluster's first task, then for each subsequent task continue the
SAME agent via SendMessage with the next brief — a continued agent keeps its context, and its
already-read files, intact, so the cluster's shared files are read and cached once. A
cohesive cluster is a maximal run of tasks that:

- form a serial `depends:` chain within one phase (each task depends on the previous), and
- share a primary file or subsystem — the same file named in their briefs, or the TASKS.md
  preamble flagging them as a same-file/serial chain (the architect leaves these hints), and
- carry the SAME `model` value. A continued agent keeps its spawn model and SendMessage
  cannot override it, so a model-pin change ALWAYS ends the cluster — the task's `model`
  field stays authoritative at dispatch; never serve an `opus`-pinned task with a warm
  `sonnet` agent, or vice versa.

The trade-off to respect: a warm agent accumulates context and eventually needs compaction,
which destroys the cache advantage — warmth is for clusters, not universal. Cap a warm
sidekick at ~4 tasks, end it early if its replies degrade or it reports context pressure, and
start the next cluster fresh. Each continuation message is still the next task's
self-contained brief verbatim, prefixed only with "Previous cluster task is done; next task:".
Verification is NEVER warmed: the verifier agent is always a fresh spawn — its value
IS the adversarial fresh context. Record warm-cluster use in NOTES.md (which tasks shared one
agent) so later phases and the scorecard can see it.

## Outcome ledger — one line per finished task

NOTES.md carries SIX machine-read line families — `outcome:`, `agent:`, `reroute:`,
`session:`, `reviewer:`, `defect:` — specified here and in the two sections below. **Always
backtick any of those six tokens when you quote ledger grammar in NOTES.md prose.** A line
that merely *starts* with one of them parses as real data whether it is plain, bulleted, or
indented, so unbackticked grammar in prose becomes fabricated evidence in the scorecard. The
rule is stated once, here, and binds all six families.

The moment a task reaches `done` or `blocked`, append ONE machine-readable line to NOTES.md —
this is the input `bin/routing_scorecard.py` turns into the kit's routing-quality scorecard:

    `outcome: <task-id> model=<model> attempts=<n> result=<result> review=<review>`

- `model` — what the task actually ran on: its `model` pin, or the escalation target when a
  Fable consult did the fixing.
- `attempts` — implementer dispatches, counting retries and escalation (clean first try = 1).
- `result` — exactly one of `pass` (first dispatch, verify passed) | `retry-pass` (passed on
  the retry) | `escalated-pass` (passed only via the escalation valve) | `blocked` |
  `budget-stop` (the run stopped cleanly at a declared **Budget dial** cap before any dispatch
  happened — see below; it carries no verdict about the task and is excluded from first-try/
  escalation-rate signals for exactly that reason).
- `review` — exactly one of `clean` (verifier/reviewer accepted the work unchanged) |
  `revised` (changes were required after the implementer claimed done) | `none` (no
  independent review beyond the verify command).

Three further fields are OPTIONAL and ride that same line. They are execute-owned, and
**absent means today's behavior**: a line without them parses and scores exactly as it always
has, so every kit already executed stays valid routing evidence. Never add them to the task
contract — like the whole ledger, they are a NOTES.md line format, not task fields:

    `outcome: <task-id> model=<model> attempts=<n> result=<result> review=<review> [run=<run-id>] [parent=<task-id>] [failure=<class>]`

- `run` (optional) — the id of the driver invocation that produced this line, formatted
  `<UTC-date>-<4 hex>`, e.g. `run=2026-07-26-9f3a`. ONE id per driver invocation, stamped on
  every outcome line that invocation writes, so a resumed kit's lines separate by run. Run ids
  are CONTENT-FREE by rule: a UTC date plus four hex characters, never a hostname, username,
  path fragment, or transcript text — NOTES.md is committed in consumer repos.
- `parent` (optional) — the task id that SPAWNED this outcome, set ONLY on `result=escalated-pass`
  outcomes and naming the task the consult was spawned for. It records lineage (what spawned
  what) so an escalation can be grouped under its parent task. Ordinary outcomes omit it, and
  a task is never its own parent. **A consult that did NOT succeed carries no `parent=`** — a
  blocked consult writes `result=blocked` and nothing else, because `escalated-pass` is the only
  value in the vocabulary that means "an escalation resolved this". `bin/routing_scorecard.py`
  and all three drivers enforce exactly that: a `parent=` on any other result is dropped with
  an "out of grammar, ignored" note, taking the line's `failure=` class down with it.
- `failure` (optional) — set ONLY on `blocked` or escalated outcomes: exactly one of
  `execution` (the work itself failed — a crash, a bad edit, a tool error) | `coherence` (the
  agent lost the plot — drifted from the brief, contradicted itself, looped) | `verification`
  (the verify step was the failure — it never ran, could not fail, or passed work that was
  wrong). Those three classes are the ENTIRE vocabulary; a finer-grained label stays free text
  in NOTES.md prose and never enters the line, because a coined fourth class aggregates with
  nothing.

Of the three, `run=` is invocation provenance, not an escalation signal: it belongs on EVERY
outcome line a driver invocation writes, clean pass included. `parent=` and `failure=` are the
two that are restricted — present only on `escalated-pass` and on blocked/escalated outcomes
respectively — so a clean pass carries `run=` but omits both of those. A fully-loaded line
looks like:

    `outcome: T7 model=fable attempts=3 result=escalated-pass review=clean run=2026-07-26-9f3a parent=T4 failure=verification`

These fields belong to the `outcome:` family, so the backtick rule stated above for the six
machine-read line families binds them too: quote a whole `outcome:` line in NOTES.md prose
without backticks and it parses as real data, run id and lineage included.

Unknown `key=value` pairs are ignored by the parser, and re-running a task just appends a
fresh line — the scorecard takes the LAST line per task id.

## Agent ledger — one line per per-task subagent

Per-task dollar attribution rides on knowing which subagent transcript served which task. The moment any per-task dispatch returns — the implementer (step 2), a retry, the verifier (step 3), or the Fable escalation consult — append ONE machine-readable line to NOTES.md recording the agent id the Agent tool reported:

    `agent: <task-id> id=<agent-id> role=<implementer|verifier|escalation|scout|test-author|second-verifier|red-team|security-auditor|docs-editor|synthesizer> model=<model> [findings=<n> confirmed=<n>] [result=<accepted|revised|blocked>]`

- `id` — the agent id from the Agent tool's result. The subagent's transcript is the `<agent-id>.output` file in the session's tasks scratch dir — the file `--by-task` prices.
- `role` — exactly one of `implementer` (retries included — each retry dispatch appends its own line with its own agent id) | `verifier` | `escalation` (the Fable consult).
- `model` — the alias the dispatch actually ran on: the task's pin, an applied re-route's upgraded alias, or the escalation target.
- `findings` / `confirmed` (optional, only meaningful together, and meaningful only for the finding-producing roles — `verifier`, `test-author`, `second-verifier`, `red-team`, `security-auditor`; an `escalation` line carries `result=` alone, because a consult delivers a fix rather than a verdict and the scorecard reads no escalation precision, and the no-findings roles `scout`, `docs-editor`, and `synthesizer` record no quality counts at all) — the dispatch's ADJUDICATED outcome. `findings` is the number of distinct defects the dispatch's verdict raised: count the verdict's distinct claims exactly as the verdict itself presented them — never re-bundle or split them to flatter the ratio. `confirmed` is how many you, the orchestrator, adjudicated as real, and a finding is real only when it produced a concrete artifact: a code or doc change, a claim reverted, a `defect:` line recorded, a task blocked. A finding you acknowledged but changed nothing for is NOT confirmed, and when you are unsure whether a finding is real it is NOT confirmed. Adjudicate at the moment the verdict is resolved and never revisit that adjudication — appending a later enriched line (below) for evidence that lands afterwards is the sanctioned mechanism and is NOT a backfill; backfilling means altering an adjudication already made.
- `result` (optional) — the fate of the dispatch's product under downstream scrutiny: `accepted` (stood as delivered) | `revised` (materially overturned or corrected) | `blocked`.
- Timing: append the bare line the moment the dispatch returns, exactly as before. When adjudication lands later, append a SECOND full line for the same task id + agent id carrying the quality fields — the scorecard keeps the LAST line per `(task-id, agent-id)`, so the enriched line wins: `agent: T7 id=a1b2c3 role=verifier model=sonnet findings=3 confirmed=1 result=revised`
- Implementer lines normally OMIT the quality fields: implementer quality already lives in the `outcome:` ledger, and the scorecard ignores an implementer `result=` — one number, one home.
- A warm sidekick serving a cluster gets one line PER TASK it serves, all carrying the SAME agent id — the shared id is what lets the scorecard attribute the one shared transcript to the cluster as a unit instead of faking a per-task split.
- Do NOT record ad-hoc scouts or phase reviewers here, and the two exceptions are narrow in DIFFERENT ways. An ad-hoc scout — the "let me look around first" read a lean driver does on its own — stays off the ledger entirely, exactly as before; but a `scout` DECLARED on PLAN.md's `roles:` line is a per-task dispatch and IS recorded, as an `agent:` line with `role=scout` (see **Roles roster — optional extended roles, measured** below). A phase REVIEWER is still never an `agent:` line — its verdict is recorded by its own `reviewer:` family, exactly as before; but the declared phase-scoped roster roles (`security-auditor`, `docs-editor`) ARE recorded as `agent:` lines, carrying the phase token in the task slot. What holds for every one of them is the never-split law: a per-phase or per-run transcript deliberately lands in the breakdown's unattributed line and is never split per task — which is why those roles' dollars read n/a in the `--roles` card even though their dispatches are recorded.
- The line is OPTIONAL and execute-owned (precedent: `outcome:`/`reroute:`/`session:` — a NOTES.md line format, not a task field). Unknown `key=value` pairs are ignored, a repeated task-id + agent-id pair takes the LAST line, and a kit with no `agent:` lines simply degrades to whole-kit dollars — never record a guessed agent id.

## Role ledger — reviewer verdicts and brief defects

Two more OPTIONAL, execute-owned NOTES.md line families (same precedent as above:
`outcome:`/`reroute:`/`session:`/`agent:` are line formats, not task fields).

**Phase reviewers** get their own family. After the step-6 reviewer returns and you
adjudicate its findings, append ONE line per phase:

`reviewer: <phase> model=<model> findings=<n> confirmed=<n> [result=<accepted|revised|blocked>]`

for example `reviewer: P1 model=opus findings=2 confirmed=2 result=accepted`. `findings` and
`confirmed` carry exactly the counting and adjudication rules defined for the agent ledger
above. `result` is the fate of the REVIEW itself, never of the phase: `accepted` when the
verdict stood as delivered (you confirmed its findings), `revised` when the verdict was
materially overturned or withdrawn, `blocked` when it could not be adjudicated at all. A
reviewer `result=` therefore never says whether the phase passed — the phase's outcome is
already recorded in its tasks' `outcome:` lines. `model=`, `findings=`, and `confirmed=` are
all MANDATORY here: an incomplete or self-contradictory (`confirmed` > `findings`) reviewer
line is DISCARDED WHOLE with a note, losing that phase's entire review record — unlike an
`agent:` line, where a bad quality field degrades to nothing-recorded in place and the line
itself survives. Re-running a phase review appends a fresh line; the last line per phase
token wins.

**Architect brief defects** are recorded the moment a task brief's defect is CONFIRMED
against repo reality — an implementer stop-and-report you verified, a verify clause that
could never fail or that contradicts its own acceptance, a pinned anchor or line number
proven stale, a helper invoked that no task creates, an escalation consult forced to rewrite
the brief. Append:

`defect: <task-id> kind=<kebab-case-token>`

for example `defect: T3 kind=stale-pin`. Use the task token `-` for kit-level defects (a
stale PLAN decision, say). The kinds: `stale-pin`, `tautological-verify`, `missing-helper`,
`unspecified-path`, `contradictory-acceptance`, `stale-plan-decision`. Reuse an existing kind
whenever one fits and coin a new one ONLY when none does — the architect reads which kinds
RECUR across tasks and kits, and a coined synonym never aggregates with its neighbour. For
the same reason, a second defect of the same kind in the same task repeats that same kind
verbatim on its own line: the scorecard keeps the first and notes the repeat, so one kind
counts once per task, by design. Never suffix a kind (`stale-pin-2`) to force a second
count — a suffix is a new key that hides the very recurrence it was meant to show. This
ledger measures the ARCHITECT, and you, the executor,
are its honest recorder: log the defect even when — especially when — the fix was easy.

## Live re-routing — upgrade-only, autonomy-gated

The outcome ledger doubles as a live routing signal. The moment any `outcome:` line lands
(step 4 or 5), consult the kit's running per-tier first-try rate:

    python3 bin/routing_scorecard.py <slug> --live

`--live` reads TASKS.md plus the NOTES.md ledger so far (read-only — it never writes) and
recommends an upgrade only when a tier's live first-try rate falls below its threshold over a
minimum sample of that tier's finished tasks. Recommendations are UPGRADE-ONLY and move
exactly one step up the tier ladder (haiku→sonnet, sonnet→opus) — never down, never skipping
a rung, and NEVER to frontier/Fable: Fable is reached exclusively through the per-task,
evidence-carrying escalation valve below. When the struggling tier sits one rung under
frontier, `--live` reports the signal but locks the recommendation — the valve is the only
path up from there.

A re-route is a **runtime dispatch override, never a TASKS.md rewrite**. The task's `model`
field stays the dispatch default and is never edited; an applied upgrade changes only the
alias you pass as the Agent tool's `model` parameter for the remaining PENDING tasks it
names (never an in-progress task), and it ends any warm cluster serving those tasks — a
model change always ends a cluster. Every recommendation you act on or announce is logged to
NOTES.md as one machine-readable line (the budget below is counted from these):

    `reroute: <from-tier> to=<to-tier> mode=<advisory|applied> tasks=<id,id,...> rate=<passed>/<completed>`

The autonomy dial decides what you may do with a recommendation:

- **advisory (the default)** — PRINT the recommendation to the user and change nothing:
  every task keeps dispatching on its pinned `model`. Log the printed recommendation once
  (`mode=advisory`) so an unchanged signal is not re-announced. The human decides.
- **auto** — apply it yourself: dispatch the named pending tasks on the upgraded alias, log
  `mode=applied`, and say so in your report. Respect the `budget` block in the `--live`
  output — `mode=applied` events are capped per run, and when `remaining` hits 0 you fall
  back to advisory printing. Auto also arms the escalation valve: a task `blocked` after
  retry goes straight to the Fable consult without pausing to ask.

Downgrades are never automatic in either mode — if a tier looks over-provisioned, say so in
the end-of-run report and let the human re-pin the next kit.

## Escalation valve — blocked tasks go back to Fable, one at a time

When a task is `blocked` after retry, offer (or, when the autonomy dial is `auto`, do without pausing to ask — see **Live re-routing — upgrade-only, autonomy-gated**) a **targeted Fable consult**: dispatch a subagent with `model: fable` carrying only that task's brief, the failure evidence, and the relevant PLAN.md excerpts. Ask it to either fix the task directly or rewrite the brief so the implementer can. This keeps Fable spend proportional to genuine difficulty — you never pay Fable prices for routine execution. When the consult unblocks the task, record `result=escalated-pass` (with the consult's model) in its `outcome:` line.

## Budget dial — optional dispatch/escalation/consult cap

PLAN.md may declare an OPTIONAL `budget:` line — a PLAN.md line family exactly like `autonomy:`, **never a task field**, read once at Setup:

    `budget: max-dispatches=N max-escalations=N max-consults=N`

Any subset of the three keys may appear, in any order. Absent block = today's behavior everywhere: unbounded, no check performed. All three headless drivers (`bin/claude_execute.py`, `bin/copilot_execute.py`, `bin/codex_execute.py`) honor the SAME block under the same names — see their "PLAN.md budget dial" docstring sections — and this loop honors it identically, so a kit behaves the same whether it is run interactively or through a driver.

**What the three keys count, in this loop's dispatch model:**

- `max-dispatches` — every implementer/retry Agent-tool dispatch this run makes, across every task (the same `attempts=` figure already recorded on each task's `outcome:` line).
- `max-escalations` and `max-consults` — in this skill's loop, both count the SAME event: an invocation of the **Escalation valve** (the Fable consult). Unlike the headless drivers — which distinguish an in-ladder tier-walk within one task's own dispatch (`max-escalations`) from a separate `--parent` invocation spawned to rescue a DIFFERENT task (`max-consults`) — this loop has no in-ladder tier walk of its own; its only escalation mechanism IS the consult. So a kit whose PLAN.md sets either key (or both) caps the same thing here: how many Fable consults this run may make.

**Checking the cap:** before each dispatch (step 2 of the loop) and before each Escalation-valve consult, recompute usage the SAME way the drivers do — by scanning NOTES.md's own recorded `outcome:` lines (this session's own lines included, since they are already appended to NOTES.md by the time the next task is considered): sum `attempts=` for `max-dispatches`, sum `(attempts - 1)` per line for `max-escalations`, count lines carrying `parent=` for `max-consults`. This makes the check work identically whether the kit is being run fresh or resumed in a later session — NOTES.md, not an in-memory counter, is the source of truth, exactly as it is for the outcome ledger itself.

**On reaching a cap:** stop cleanly, right there — do not dispatch (or do not make the consult). Leave the task's status exactly as found (pending stays pending; do NOT mark it `blocked` — a budget stop is not a verdict on the task). Append ONE `outcome: <task-id> model=<pin or unpinned> attempts=0 result=budget-stop review=none run=<run-id>` line to NOTES.md (generate a fresh `run=<UTC-date>-<4 hex>` id for this line if you have not already stamped one on an earlier line this session). State plainly in your end-of-run report which cap was hit, its used/cap counts, and how many tasks are left untouched — **never fold this into a fluent "all done" summary**; a budget stop that reads like a normal finish is exactly what this dial exists to prevent. Then STOP dispatching for the remainder of this run (do not skip ahead to a later independent task — the budget is kit-wide, not per-task).

**Never write a budget-stop line for a task that already carries a verdict.** If the task the cap stopped you on already has an `outcome:` line recording `pass`/`retry-pass`/`escalated-pass`/`blocked` (resuming an already-`blocked` task after the budget is spent is the ordinary case), report the stop in your end-of-run summary but append NO ledger line for it. A `budget-stop` is not a verdict, and later lines for the same task id normally win, so writing one would erase a real result — and its `failure=` class — from the kit card and from `--history`. `bin/routing_scorecard.py` now refuses to be overwritten this way (it keeps the verdict and notes the dropped budget-stop) and all three drivers decline the write for the same reason; do not hand it a line it has to ignore.

## Roles roster — optional extended roles, measured

PLAN.md may declare an OPTIONAL `roles:` line — a PLAN.md line family exactly like `autonomy:` and `budget:`, **never a task field**, read once at Setup:

    `roles: <token> <token> ...`

Tokens come from exactly seven: `scout`, `test-author`, `second-verifier`, `red-team`, `security-auditor`, `docs-editor`, `synthesizer` — the optional pipeline roles a kit adds beyond the standing trio (implementer / verifier / reviewer). Absent line = the trio, today's behavior everywhere: no extra dispatch, no extra ledger line, and every kit written before this dial existed runs exactly as it always has. Dispatch each declared role to the kit's `<slug>-<role>` agent (the architect instantiates one per declared role from its templates); if a declared role has no agent file, dispatch it with the Agent tool directly on the template's default model and say so in your report.

**Hook points, pinned.** A declared role runs at exactly one place in the loop, and nowhere else:

- `scout` — before a declared-roster task's implementer dispatch (step 2). You MAY skip it per task when the task needs no grounding; every dispatch you actually make is recorded.
- `test-author` — after the implementer claims done, before the verifier. Its failing tests are FINDINGS, not a verdict: hand them to the implementer as the retry evidence of step 5.
- `second-verifier` — in parallel with the verifier (step 3), carrying a stated different lens. Like the verifier it is always a fresh spawn, never warmed.
- `red-team` — after verify passes, before the task is marked `done` (step 4).
- `security-auditor` — phase end (step 6), in parallel with the reviewer.
- `docs-editor` — phase end, after the review's findings are adjudicated.
- `synthesizer` — end of run, before you write the report.

**Consequence rules — what a confirmed catch triggers.** Recording a catch is not the same as acting on one, so each finding-producing extended role has ONE pinned consequence:

- `test-author` — a failing test is FINDINGS, not a verdict: hand it to the implementer as step 5's retry evidence, exactly as its hook point above states.
- `red-team` — a confirmed break on a task that already PASSED verify is treated as a failed verify: feed it to the implementer as step 5's retry evidence, and a second failure blocks the task. A confirmed break is never recorded-and-shrugged into `done`.
- `security-auditor` — a confirmed fence violation at phase end is PHASE-BLOCKING, with the same standing as a blocking reviewer finding: fix it before the next phase's first dispatch.
- `docs-editor` — a confirmed drift rides the phase boundary: dispatch the fix, or fold it into the next task. It never blocks the run.

Stated once for all four: consequence rules change nothing about RECORDING. The `agent:` line is appended the moment the dispatch returns, whatever the catch does or does not trigger — the ledger records what ran and what it found, never what you decided to do about it.

**Recording — every declared-role dispatch appends an `agent:` line.** The seven role tokens join `implementer`/`verifier`/`escalation` in that family's `role=` vocabulary; no new line family exists for them, and NOTES.md's machine-read families stay the SIX named above. The task slot depends on the role's scope:

- per-task roles (`scout`, `test-author`, `second-verifier`, `red-team`) — the task id, exactly like an implementer or verifier line.
- phase-scoped roles (`security-auditor`, `docs-editor`) — the PHASE token (`P1`) in the task slot; the parser's task field is freeform. The never-split law above is unchanged for them: their per-phase transcripts still land in the breakdown's unattributed line, which is why their per-task dollars read n/a in the `--roles` card.
- `synthesizer` — the token `-` in the task slot (the `defect:` family's precedent for a kit-level record), because it is run-scoped.

`findings=`/`confirmed=` carry exactly the counting and adjudication rules already stated for the agent ledger: count the verdict's distinct claims as the verdict itself presented them, and a finding is confirmed only when it produced a concrete artifact. The roster adds ONE optional field to that same line:

    `agent: <task-id|phase|-> id=<agent-id> role=<role> model=<model> [findings=<n> confirmed=<n> marginal=<n>] [result=<accepted|revised|blocked>]`

- `marginal` (optional; meaningful only alongside `findings=`/`confirmed=`, and constrained `0 ≤ marginal ≤ confirmed`) — of the CONFIRMED findings, how many no EARLIER layer of the pipeline raised on that task (or on that phase, for phase-scoped roles). This is the number that answers "did this role pay?"; adjudicate it at the same moment you adjudicate `confirmed=`, and never revisit it afterwards.

**The canonical pipeline order**, written out in full here — this is what "earlier layer" means, and it is the only order `marginal=` is adjudicated against:

    scout → implementer → test-author → verifier → second-verifier → red-team → reviewer → security-auditor → docs-editor → synthesizer

Two pairs run in parallel, so state their tiebreaks the same way every time: a finding raised by both the verifier and the second-verifier is the VERIFIER's (not marginal for the second-verifier); a finding raised by both the reviewer and the security-auditor is the REVIEWER's (not marginal for the security-auditor). A finding is never counted marginal twice.

Deflationary defaults are the law of `marginal=`: unsure = not marginal; a finding with no artifact = not confirmed, hence never marginal. An absent `marginal=` means unmeasured, never zero — legacy lines carry none and the scorecard reads them as marginal-unmeasured — so never back-fill one onto an adjudication already made. And as with every ledger token, backtick `roles:`, `agent:`, `marginal=`, and the role tokens whenever you quote them in NOTES.md prose: an unbackticked line that starts with a family token parses as real data.

**The dial is measurement, not mandate.** Declared roles run in order to be MEASURED: `python3 bin/routing_scorecard.py --roles` renders the per-role value table — dispatches, findings, confirmed, marginal, precision, marginal rate over the dispatches where marginal was actually adjudicated, and dollars only where transcripts priced them — with "insufficient sample" below the evidence floor rather than a number the sample cannot support. Dropping a role that is not earning its marginal keep is the EXPECTED outcome of measuring it, not a failure of the run. That decision belongs to the human, BETWEEN kits: never add, drop, or substitute a role mid-run because the numbers look thin so far. Report what the roster measured at end of run, and let the next kit's PLAN.md act on it.

**A declared roster shifts `attempts=` — and that is not implementer regression.** Declaring `test-author` (and `red-team`, whose retry path is pinned above) structurally INCREASES `attempts=` on exactly the tasks whose defects those roles catch before `done`: a defect that would once have shipped now costs a retry instead. So per-tier first-try rates in `--history` will dip on R5+ kits at identical model quality — the dip is the roster working, not the implementer getting worse. Read those rates tier-vs-tier only across kits with the SAME roster, and never read a roster-driven dip as evidence for re-pinning a tier down.

## End of run

Report: tasks completed / blocked / remaining, verify results (with output, faithfully — failures stated plainly), and NOTES.md additions. If everything is done, run the plan's overall "done" check from PLAN.md and state the result. Then record this run's session id for the cross-kit routing history: append ONE `session: <session-id>` line to NOTES.md, where `<session-id>` is the filename stem of this session's transcript — the transcript that is still being WRITTEN right now — resolve it by write recency across the whole projects tree, not by a path-derived slug: `ls -t "$HOME/.claude/projects"/*/*.jsonl | head -1`. Do NOT derive the projects dir from `pwd`: a session that STARTED in a different directory lives under the slug of where it started, so a `pwd`-derived lookup silently returns some OTHER session's transcript. That failure mode is the dangerous one — it does not error, it returns a plausible wrong id, and the guard below never fires. Sanity-check the candidate before recording it: a live session's transcript has an mtime within a minute or two of now and is large (megabytes by the end of a kit run); a few-kilobyte file last written hours ago is a different session, so discard it and skip the line. The lookup is read-only and best-effort, and the line is OPTIONAL: if nothing passes the sanity check, or two candidates are plausibly live, skip it — the history degrades to quality-only for this kit; never record a guessed id. A resumed kit appends one `session:` line per run (the history sums a kit's sessions and dedupes ids shared across kits). Finally, offer the routing-quality scorecard: `python3 bin/routing_scorecard.py <slug>` (first-try pass rate, model mix, cheap-model review survival, and — with `--session` — dollars vs an all-frontier counterfactual) and the cross-kit track record: `python3 bin/routing_scorecard.py --history` (per-tier quality across every kit, plus aggregate dollars over the kits that carry a `session:` line, plus per-role quality), and — when this run recorded `agent:` lines — the per-task dollar breakdown: `python3 bin/routing_scorecard.py <slug> --session <session-id> --by-task` (delegated cost per task by role — implementer/verifier/escalation; a warm cluster's shared transcript is attributed to the cluster as a unit, and the orchestrator's own share is one un-split line, never divided per task), and — when this run recorded extended-role `agent:` lines — the per-role value table: `python3 bin/routing_scorecard.py --roles` (dispatches, findings, confirmed, marginal, precision, marginal rate, and dollars only where transcripts priced them, with "insufficient sample" below the evidence floor).
