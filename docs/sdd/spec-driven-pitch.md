# Plan once on the frontier. Build cheaply against the spec.

**polytropos** · spec-driven development · a Claude Code plugin

A short case for spec-driven development as polytropos practices it: who writes the spec, who
builds against it, who checks the work, and how the whole loop is measured.

> This is the Markdown form of the printable deck `docs/spec-driven-pitch.html`; the two carry
> the same text. The long form is `docs/SPEC-DRIVEN.md`.

---

## 1 · The claim

### The problem

The strongest model makes the best decisions, and it costs the most per token. Run every step of
a large change on it and you pay frontier rates for typing. Run everything on a cheaper model and
the bill drops, but judgment goes with it: the plan drifts, shortcuts creep in, and the report at
the end says "done" whether or not it is. Most agent workflows then believe the report.

### The claim

polytropos splits the work by what each part needs. Judgment is spent once, up front, and written
down as a spec. Execution runs on cheaper tiers, pinned task by task. Nothing is accepted on the
executor's word. In one sentence: **the architect writes the spec, pinned models execute it,
verification runs against the spec, and the ledger measures the result.**

1. **The architect writes the spec** — *step 1 · fable.* `/polytropos:architect` runs once on the
   frontier tier and writes an execution kit: `PLAN.md`, `TASKS.md`, `GUARDRAILS.md`, and
   model-pinned agents.
2. **Pinned models execute** — *step 2 · sonnet · opus · haiku.* `/polytropos:execute` dispatches
   each task to its pinned tier: `sonnet` by default, `opus` for the genuinely hard ones, `haiku`
   for trivial mechanical work.
3. **Verification against the spec** — *step 3 · verify.* The orchestrator runs every verify
   command itself. A fresh-context verifier and a phase reviewer check the work against the kit,
   never against the implementer's report.
4. **The ledger measures** — *step 4 · measure.* Each result lands as a machine-read line in the
   kit's `NOTES.md`. `bin/routing_scorecard.py --history` grades the tiers, the review roles, and
   the spec itself across every kit.

> "The implementer's claim of success is not evidence."
>
> One line from `skills/execute/SKILL.md`, and the whole discipline. The next three pages are the
> machinery that makes it hold.

**Why a spec, and not a better prompt?** A prompt is read once, by one model. A spec is read by
every role that touches the work: the implementer builds from it, the verifier checks against it,
the reviewer measures drift from it, and the ledger records how well it held. That reuse is what
makes frontier judgment worth its price, paid once.

---

## 2 · The spec is three files and a contract

A kit lives at `.claude/kits/<slug>/`. The architect skill (`skills/architect/SKILL.md`) names
what each file must pin down, and the execute skill reads all three before the first dispatch.

| File | What it pins |
|---|---|
| `PLAN.md` | The goal and a checkable "done"; constraints and an explicit out-of-scope fence; architecture decisions *with their rationale*; risks with tripwires. |
| `TASKS.md` | One block per task: `id`, `title`, `status`, `model`, a self-contained brief, acceptance criteria, and a verify command. Tasks sit under phase headings and each one carries `depends:` or `independent:`. |
| `GUARDRAILS.md` | Kit-scoped fences: forbidden shortcuts, conventions, "always run X before claiming done". Required even when short. |

A task block, abridged:

```text
### T3 — Guard the snapshot labels
- id: T3
- title: Fail the suite when a price table loses its label
- status: pending
- model: sonnet
- depends: T1
- evidence: red-green

Brief: the files, the exact interface, the known gotchas,
and why this approach rather than the obvious one.

Acceptance:
- the new guard passes, and it was red before the change

Verify:
  python3 -m unittest discover -s tests -p 'test_labels.py'
```

**The brief is the core of the spec.** The skill requires every task to be executable by a model
with *zero access to this conversation*: files, conventions, interfaces pinned exactly, known
gotchas, and the *why*. Its calibration rule: "Pin down contracts and interfaces precisely; leave
implementation judgment open where any competent model would do fine."

`GUARDRAILS.md` exists even when it has little to say, because "an absent file is
indistinguishable from a forgotten one"; `tests/test_guardrails_layout.py` fails the suite for
any kit that skips it. Execute writes a fourth file, `NOTES.md`, as the kit runs. That file is the
run's record, not part of the spec.

The task graph is checked before anything runs. `bin/kit_contract.py graph` rejects a duplicate
id, an unknown or self dependency, or a cycle, and names the fix for each; execute will not route
around an invalid plan.

---

## 3 · Checked against the spec, not the story

Five layers stand between an implementer saying "done" and the task being marked `done`. Each is
written into `skills/architect/SKILL.md` and `skills/execute/SKILL.md`.

- **The orchestrator runs the verify command itself.** Every task, every time; the implementer's
  claim of success is not evidence.
- **A fresh-context verifier.** For non-trivial tasks a separate, adversarial agent re-checks the
  acceptance criteria against the files. It runs on `sonnet` by default, and on `haiku` only when
  every check is mechanical.
- **A phase reviewer.** At each phase end an `opus` reviewer checks the phase against `PLAN.md`
  for drift.
- **The red-green gate.** Under `evidence: red-green`, the default, a verify command that already
  passed on the pre-task tree means the task is *blocked, not done*. A check that could never have
  failed proves nothing.
- **Escalation with evidence.** A failed task is retried once with the failure output. A second
  failure marks it `blocked`, and execute offers a `fable` consult (made unasked only under
  `autonomy: auto`) that receives only that brief, the failure evidence, and the relevant
  `PLAN.md` excerpts. Frontier spend stays proportional to genuine difficulty.

The verifier and reviewer are pinned to `tools: Bash, Read, Grep, Glob`. The architect skill is
candid that this removes the casual path to editing, not the capability, so both prompts also
carry a restore-what-you-touch practice. The headless drivers (`bin/claude_execute.py` and its
peers) add two guarantees of their own: verify commands run inside the `bin/exec_policy.py`
execution boundary, and `bin/attempt_ledger.py` records every dispatch before and after it runs.
The interactive execute skill runs verify commands in the session's own shell. `SECURITY.md`
states what each guarantee does and does not promise.

### The ledger

Every finished task, dispatch, and phase review appends one machine-read line to `NOTES.md`, in
the grammar of `skills/execute/references/ledger.md`:

```text
outcome: T3 model=sonnet attempts=1 result=pass review=clean
agent: T3 id=<agent-id> role=verifier model=sonnet findings=1 confirmed=1
reviewer: 1 model=opus findings=4 confirmed=3
defect: T5 kind=tautological-verify
```

> **The spec is graded too.** When execute confirms mid-run that a brief itself was wrong (a stale
> pin, a verify that could not fail, an unspecified path, contradictory acceptance), it writes a
> `defect:` line instead of widening the task until it passes. The scorecard totals those kinds as
> the architect's brief-defect floor, and the architect's routing guidance tells the next planner
> to read them "as evidence about YOUR OWN briefs". Grading the executors is common. Grading the
> spec is the point.

---

## 4 · Why it is cheap, and why you can believe it

### Frontier once

The architect runs on the frontier tier once. In dispatch mode it is a subagent, so "the main
session never leaves the daily driver". After that, the interactive execute skill reaches the
frontier tier only through a blocked task's evidence-carrying consult (its automatic re-route
stops one rung below); the headless drivers' `escalation_ladder` in `bin/claude_execute.py` walks
every tier above a failed task's, frontier included.

### Tiers by alias

Every pin is a tier word (`fable`, `opus`, `sonnet`, `haiku`), never a model id. Claude Code
resolves the alias to its tier's current default; the headless driver resolves it to the first
row of that tier in `data/pricing.json`. `python3 bin/aesop_bridge.py tiers` prints today's
answer.

### Costs are computed, not quoted

This page carries no prices. `/polytropos:route` estimates a task's cost before it runs, and
`python3 bin/routing_scorecard.py <slug> --session <id>` prices a finished kit against an
all-frontier counterfactual, both from `data/pricing.json`.

### The track record is a command, not a number

A tally written into prose is wrong by the next kit. `python3 bin/routing_scorecard.py --history`
prints first-try, retry, escalated, and blocked counts per tier, findings against confirmed
findings per review role, and the brief-defect kinds. Missing data shows as `n/a`, never as zero.

### What it is not

- **Not code generation from a formal spec.** The spec is prose plus shell commands; a model reads
  the brief and writes the change.
- **Not proof the spec is complete.** The checks cover what the architect thought to check.
- **Not a license to improvise.** When a brief conflicts with the repo, the executor stops and
  reports. Nobody changes a task's scope or acceptance to make it pass.
- **Not an automatic re-router.** The live re-route signal is advisory by default. Under
  `autonomy: auto` it moves pending tasks one tier up, never down, never to the frontier, and it
  never rewrites a task's `model` field.

### Run it

```text
/polytropos:architect <task>                # plan once, on the frontier tier
/polytropos:execute <slug>                  # run the kit on its pinned tiers
python3 bin/routing_scorecard.py --history  # the track record, live
```

---

Long form: docs/SPEC-DRIVEN.md · Source: github.com/agentmc15/polytropos
