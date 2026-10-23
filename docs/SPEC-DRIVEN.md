# Spec-driven development, the polytropos way

## The claim

Spec-driven development usually means three moves: write the spec, build against it, verify
against it. polytropos makes all three, and the shape is specific. The spec is an *execution
kit*, a small directory of Markdown files that `/polytropos:architect` writes once on the
frontier tier (`skills/architect/SKILL.md`). `/polytropos:execute` runs it on cheaper pinned
tiers (`skills/execute/SKILL.md`). Verification is run against the kit's own acceptance criteria
and verify commands, never against what an implementer says it did. And the results go into a
ledger that grades the spec as well as the executors (`bin/routing_scorecard.py --history`).
This page goes through each step and names the file or command that makes it true. Where the
repo deliberately does not do something, it says so: those limits are part of the discipline.

## The spec is three files

A kit lives at `.claude/kits/<slug>/`. The architect skill names what each file must pin down.

| File | Pins | Read by |
|---|---|---|
| `PLAN.md` | goal and a checkable "done"; constraints and an explicit out-of-scope fence; architecture decisions *with rationale*; risks with tripwires; optional `autonomy:`, `budget:`, `roles:` and `workflow:` lines | execute at Setup; at every phase start it re-reads `GUARDRAILS.md` and the constraints and out-of-scope section of `PLAN.md` |
| `TASKS.md` | one block per task: `id`, `title`, `status` (`pending`/`in-progress`/`done`/`blocked`), `model`, a self-contained brief, acceptance criteria, a verify command, optional `evidence:` (`red-green` default, `regression`, `precondition`); `## Phase N` headings; `depends:` or `independent:` on every task | execute's loop and `bin/kit_contract.py` |
| `GUARDRAILS.md` | kit-scoped fences: forbidden shortcuts, conventions, "always run X before claiming done" | execute at Setup and at every phase start |

The brief is the core of the spec. The skill requires every task to be "executable by a model
with **zero access to this conversation**". That means files, conventions, exact interfaces,
known gotchas, and the *why* behind the approach. The calibration rule is "pin down contracts
and interfaces precisely; leave implementation judgment open". `GUARDRAILS.md` is mandatory even
when it is short. The skill explains that "an absent file is indistinguishable from a forgotten
one", and `tests/test_guardrails_layout.py` fails the suite for any kit with a `PLAN.md` but no
`GUARDRAILS.md`. Execute writes a fourth file, `NOTES.md`, while the kit runs. The architect
never creates it. It is the run's record, not part of the spec.

## Who writes it, who runs it

The architect runs once. In dispatch mode the skill spawns the planning work as a subagent with
`model: fable`, and "the main session never leaves the daily driver". That is a deliberate
limit: polytropos never switches the main session's model. The alternative is native mode,
where the user switches the model themselves with `/model fable`.

Execution happens on cheaper tiers. The architect writes model-pinned agents into
`.claude/agents/`. The implementer runs on `sonnet` and "stops and reports rather than
improvising when the brief is wrong". The verifier runs on `sonnet` by default, and on `haiku`
only when every check is mechanical, such as an exit code or a byte comparison. The reviewer
runs on `opus`. Each task's `model` field (`sonnet` by default, `opus` for genuinely hard work,
`haiku` for trivial mechanical work) is authoritative at dispatch. Execute passes it as the
Agent tool's `model` parameter, which overrides the agent file's frontmatter.

Pins are tier aliases, never model ids. Claude Code resolves an alias to its tier's current
default. The headless driver `bin/claude_execute.py` resolves it to the first row of that tier
in `data/pricing.json` (`resolve_tier`). `python3 bin/aesop_bridge.py tiers` prints what each
tier resolves to today. Putting an id into a skill or a kit would freeze a choice the data file
already makes.

## Verification is against the spec, not the claim

The execute skill states the rule in one line: "The implementer's claim of success is not
evidence." For each task, the orchestrator runs the verify command itself. For non-trivial tasks
it also dispatches the kit's verifier in a fresh context, with instructions to be adversarial.
At each phase end the reviewer checks the phase against `PLAN.md` for drift.

The `evidence:` field closes the most common gap in spec-driven work, a check that could never
have failed. Under `red-green`, the default, a verify command that already passed on the
pre-task tree means "the required proof failed and the task is **blocked, not done**". This
holds whatever the command exits afterwards.

Failure follows a fixed path. A failed task is retried once with the failure output. A second
failure marks it `blocked`. The escalation valve then offers a single-task consult (made without
asking only under `autonomy: auto`) on `model: fable` carrying only that brief, the failure evidence and the relevant `PLAN.md`
excerpts, and asks it to fix the task or rewrite the brief.

The read-only roles get a `tools: Bash, Read, Grep, Glob` pin. The architect skill is candid
that this "removes the *casual* path, not the capability": a role is not a permission. So both
read-only agent prompts also carry a damage-restore practice. They mutate only temp copies,
restore anything they touch byte for byte, and close with `git status --porcelain`.

## The spec itself is checked

A spec that nobody validates is a wish. Four mechanisms check the kit itself, separately from
the work done against it.

`bin/kit_contract.py` is the one kit contract. `graph` validates the task DAG before the first
dispatch and exits 2 on a duplicate id, an unknown or self dependency, or a cycle. It names the
fix for each, and execute refuses to "route around an invalid plan". `roster` checks the
`roles:`/`workflow:` grammar and prints the assurance level the kit declares. `freshness`
compares each done task's acceptance against the versions of the upstream artifacts it depended
on. `refresh` re-runs a stale task's verify command and dispatches nothing.
`python3 bin/kit_contract.py demo` walks all of these on synthetic graphs.

The architect's own briefs are audited. When execute confirms a brief defect against the real
repo during a run, it records a `defect: <task-id> kind=<token>` line rather than widening the
task to make it pass (`skills/execute/references/ledger.md`). The kinds include `stale-pin`,
`tautological-verify`, `unspecified-path` and `contradictory-acceptance`.
`bin/routing_scorecard.py --history` totals them on its Role quality card as the architect's
brief-defect floor. `skills/architect/references/routing-evidence.md` tells the next architect
to read them "as evidence about YOUR OWN briefs". This is the strongest spec-driven claim the
repo can make: the spec is graded, not just the code.

The headless drivers add an execution boundary and an attempt record. Their verify runner
(`default_verify_runner` in `bin/kit_contract.py`) runs each verify command under
`bin/exec_policy.py`, confined to the workspace and with network access denied, and it refuses
to run when no backend can enforce that; the one opt-out, `--exec-mode trusted-host`, reports
itself as one. `python3 bin/exec_policy.py check` reports what this
host enforces. `bin/attempt_ledger.py` records every dispatch before and after it runs, and a
resumed run closes a dispatch that died mid-run as `unknown`, never as a pass.
`python3 bin/attempt_ledger.py demo` shows a crash and resume. These guarantees belong to the
headless drivers. The interactive execute skill runs verify commands in the session's own shell.

## What the ledger measures

Execute appends machine-read lines to the kit's `NOTES.md`; `skills/execute/references/ledger.md`
is their grammar, and `skills/execute/references/roster.md` adds the `agent:` line's `marginal=`
field.

| Line | Records |
|---|---|
| `outcome:` | per task: model, attempts, `result` (`pass`/`retry-pass`/`escalated-pass`/`blocked`, or `budget-stop`), review status |
| `agent:` | per dispatch: task, agent id, role, model, and optionally adjudicated `findings=`/`confirmed=`/`marginal=` |
| `reviewer:` | per phase review: findings raised and confirmed |
| `defect:` | a brief defect confirmed mid-run, with its `kind=` |

`python3 bin/routing_scorecard.py --history` reads these lines across every kit. Per tier it
shows first-try, retry, escalated and blocked counts. Per role (verifier, reviewer, escalation)
it shows findings against confirmed findings and the precision between them. It also shows the
brief-defect kinds described above. `--roles` adds marginal catches: confirmed findings that no
earlier layer of the pipeline had caught (`docs/ROLE-EXPERIMENT.md`). The run's own figures
appear nowhere on this page. `docs/GUIDE.md` §6 explains why: "the track record is a command,
not a number", and a tally written into prose is wrong by the next kit. Run the command for
today's figures. Missing data renders as `n/a`, never as zero.

## What it is not

- **Not code generation from a formal spec.** The spec is prose plus shell commands. No schema
  compiles into code. A model reads the brief and writes the change.
- **Not a claim that the spec is complete.** Acceptance criteria and verify commands check what
  the architect thought to check. The brief-defect floor exists because the architect gets things
  wrong, and the reviewer exists to catch drift the criteria missed.
- **The spec does not overrule reality.** `CLAUDE.md`'s "When executing a kit task" says the
  brief is authoritative, and that when it conflicts with repo reality the executor stops and
  reports instead of improvising. Execute may adapt an approach and record that in `NOTES.md`,
  but it never changes a task's scope or acceptance criteria to make it pass.
- **No automatic routing change.** The live re-route signal is advisory by default. Under
  `autonomy: auto` it moves pending tasks one tier up, never down, and never to the frontier
  tier. It never rewrites a task's `model` field.
- **No guarantee from the execution boundary or the attempt ledger beyond what `SECURITY.md`
  states.** The ledger is not exactly-once execution: a process killed after its call was made
  has still made the call.

## Read next

- `docs/HOW-IT-WORKS.md` §4.3–4.4 (the kit and the loop, on one contract) and §6 (the
  measurement layer).
- `docs/GUIDE.md` §4 (each skill, architect and execute included) and §6 (the routing
  scorecard).
- `docs/ROLE-EXPERIMENT.md`: whether optional roles beyond the standing trio pay, measured by
  marginal catch.
- The pitch: `docs/spec-driven-pitch.html`, a printable summary of this page.
