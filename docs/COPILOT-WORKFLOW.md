# The Copilot workflow layer

Phase 2 of the [Copilot harness](COPILOT-HARNESS.md): the architect → execute → verify →
escalate workflow, a budget-capped Ralph goal loop, and a vendored lessons-loop skill, all
ported from this plugin's own Claude-side patterns onto GitHub Copilot CLI's agent/model
mechanics.

---

## What this is

Three pieces were added:

- **Four workflow agents** in `copilot/.github/agents/`: `architect` (plans a task and writes an
  execution kit), `implementer` (executes one kit task per dispatch), `verifier` (reruns a
  task's verify command adversarially), `reviewer` (phase-boundary drift review). These sit
  alongside the pre-existing `route` agent.
- **One skill** in `copilot/.github/skills/lessons-loop/SKILL.md` — a scoped-lessons pattern
  vendored from aesop and rebuilt around `bin/lessons_store.py` (observations with provenance
  and expiry; rules only by recurrence or by ask), with a routing category wired into the
  `route` agent.
- **Two drivers** in `bin/`: `copilot_execute.py` (dispatches kit tasks and escalates on
  failure) and `copilot_ralph.py` (the goal loop).

Each agent's `model:` frontmatter pin is a tier choice, not a free-standing id: the test suite
checks it against the live tier for that id in `data/pricing.copilot.json`, so a future roster
change fails loudly instead of silently going stale. As a labeled snapshot tied to that file's
`cached_date` **2026-08-11**, the pins were: `architect` → `claude-fable-5` (frontier — kit
planning is the expensive meta-work done once), `implementer` → `claude-sonnet-5` (mid — the
day-to-day workhorse), `verifier` → `claude-haiku-4.5` (cheap — rerunning a verify command is
mechanical), `reviewer` → `claude-opus-4.8` (strong — drift review is judgment work). Read
`data/pricing.copilot.json` itself for current ids; don't assume this snapshot updates.

## Architect → execute → verify → escalate

A kit lives at `tasks/kits/<slug>/`: `PLAN.md` + `TASKS.md`, plus a `NOTES.md` the execute
driver owns and appends to. Every task in `TASKS.md` carries a `status` from the same four-value
vocabulary the Claude-side kits use — `pending | in-progress | done | blocked`.

Produce a kit by asking the `architect` agent to plan a task; it writes the kit files under
`tasks/kits/<slug>/` the same way this plugin's own `/polytropos:architect` does for
Claude Code.

Drive it with `bin/copilot_execute.py`:

```bash
python3 bin/copilot_execute.py status --kit tasks/kits/<slug>
python3 bin/copilot_execute.py run --kit tasks/kits/<slug> --dry-run   # prints the argv, spawns nothing
python3 bin/copilot_execute.py run --kit tasks/kits/<slug>            # dispatches for real — spends AI Credits
python3 bin/copilot_execute.py review --kit tasks/kits/<slug> --phase 1
```

`status` prints each task's state and ends with the graph's verdict; `run` dispatches the next
eligible task (or `--task ID`) to an agent and reruns its verify command; `review` dispatches
the `reviewer` agent at a phase boundary. Before either selection, the whole task graph is
validated by the shared kit contract: a duplicate id, a dependency on no task, a task that
depends on itself, or a cycle exits 2 with every finding and its fix, and nothing is dispatched
or written. While any task is `in-progress`, `run` without `--task` refuses and names the task
to resume; naming a task is the deliberate way to resume, retry, or (with `--rerun`) repeat it.
One dispatch has this anatomy:

```
copilot --agent implementer --model <id> --allow-all-tools -p "<brief>"
```

A task's `model` field is passed as `--model`, which is intended to override the dispatched
agent's own frontmatter `model:` pin — GitHub documents both mechanisms but not how they
interact when both are present, so the driver asserts this as a kit-contract convention rather
than a live-verified CLI behavior (see the kit PLAN's Risks section for the caveat). A task with
no pinned `model` dispatches without `--model`, so the agent's frontmatter pin applies.

When a dispatched task fails its verify command, the driver walks a tier-data-driven escalation
ladder — `cheap < mid < strong < frontier`, read from `data/pricing.copilot.json`, never
hardcoded — re-dispatching the *same* brief with the verify failure's command, exit code, and
output tail appended, at each rung strictly above the task's starting tier. The first rung whose
verify passes wins; an exhausted ladder marks the task `blocked`.

**Precedence gotcha, restated for generic names:** these agents are named `architect`,
`implementer`, `verifier`, `reviewer` — plain enough that a personal Copilot home is likely to
already have same-named agents. `~/.copilot/agents/implementer.agent.md` shadows a repo-level
`copilot/.github/agents/implementer.agent.md` of the same name, so a stale installed copy
silently overrides an updated bundle until you reinstall.

## The Ralph goal loop

A Ralph loop re-feeds one fixed anchor prompt every tick, with conversation history reset each
time — the model reads the goal and a state summary fresh, rather than accumulating context
across a long run. `bin/copilot_ralph.py` drives it against `copilot -p` (no `--agent`; the goal
loop dispatches plain prompts).

```bash
python3 bin/copilot_ralph.py --demo                                       # fully mocked, no network, no AIC
python3 bin/copilot_ralph.py --goal "..." --verify-cmd "..." --model <id> --stop-profile balanced
```

Three hard stops bound every run: an iteration ceiling, a no-progress window (consecutive ticks
that made no progress), and a budget cap in USD. They come in three named profiles — pinned
from aesop commit `5506617`'s Ralph guardrails, loop knobs rather than prices:

| profile | max iterations | no-progress stop | budget cap |
|---|---:|---:|---:|
| token-lean | 20 | 2 | $5 |
| balanced | 40 | 3 | $25 |
| accuracy-max | 80 | 4 | $100 |

Any of the three can be overridden per run with `--max-iterations` / `--no-progress-stop` /
`--budget-usd`, and `--max-elapsed-seconds` adds an optional wall-clock cap.

"Progress" is not "the log changed". The loop reads the verify runner's own failure tally where
it prints one (`FAILED (failures=3)`, `2 failed`, `--- FAIL:`): fewer failures is progress, the
same count is not, whatever else the output says. Without a tally it hashes the output with
timestamps, durations, temp paths and addresses stripped, and a changed hash counts only if the
tree changed too. So a test runner's changing timings no longer defeat the detector, and a
genuine fix with a similar log no longer trips it.

Every tick is recorded before and after it runs in the attempt ledger (`bin/attempt_ledger.py`,
under the per-user data root, `--attempt-store` to point elsewhere), keyed by goal and verify
command. Rerunning the same goal RESUMES: the iteration count, spend, elapsed time, no-progress
streak and the last verify diagnostics carry over, and the anchor prompt's state summary tells
the model what earlier ticks tried, what the check said, and whether the tree changed. A tick
whose process died with no result is closed as unknown, never replayed. A tick that fails
because the CLI is logged out, missing, or given an unknown flag halts the loop with that class
named (`halt: environment`) rather than spending the next tick the same way, and two loops on
one goal cannot run at once. Per-tick cost is parsed straight out of that tick's output when the CLI reports a
`total_cost_usd`/`cost_usd` JSON line; otherwise it falls back to an estimate from
`bin/copilot_pricing.py`'s cost math for the run's `--tick-profile` size against the pinned
model. Either way, the loop prints a runway line each tick — remaining budget divided by the
per-tick estimate, i.e. roughly how many ticks are left — and `--plan` can print that runway once
before the loop starts.

Every tick that is neither `--demo` nor `--dry-run` shells out to the real `copilot` CLI and
spends the user's real AI Credits over the network — treat a real Ralph run with the same care as
any other real dispatch.

## Lessons-loop

`copilot/.github/skills/lessons-loop/SKILL.md` is vendored from aesop's own lessons-loop skill,
with a Copilot-harness routing category added, and rebuilt by roadmap step 22 around
`bin/lessons_store.py`. Lessons still live in `tasks/lessons.md` as project-scoped JSON lines,
but every entry now has a kind. An **observation** is what one correction or one escalation
taught, with provenance (source, kit, task, run), scope (project, provider, task shape), and an
expiry (90 days by default); it is recalled as a labelled candidate and never applied as a
rule. A **rule** is made only by `promote`, which either records an explicit user requirement
or finds recurrence — the same lesson observed in at least two distinct kits or tasks, every
one cited as evidence. A **contest** records evidence against a rule and withholds it at recall
until a human re-promotes it. Entries written before kinds existed are **legacy**: candidates,
never rules, so a startup rule that never had evidence stops being one without anyone editing
history.

The execute driver still names the escalations for you: whenever a task escalates, `run`'s
NOTES.md block gets an extra `lesson-candidate (routing): ...` line naming the task, the tier
it was pinned at, and the tier that actually finished it — one observation to record. The
`route` agent recalls `tasks/lessons.md` at the start of every session through
`lessons_store.py recall`, which returns only entries eligible for this project and provider
(the same rule the memory store uses), not expired, not contested, matching the asked topic
and task shape, and within a budget of entries and characters; rules first, then candidates,
each with its provenance in the header. Only a rule for the task's shape overrides the default
tier heuristics. A single escalation therefore never becomes a universal tier rule: it is an
anecdote until it recurs, and the engine refuses to promote it on its own.

## Cost safety

- Any real dispatch — a `copilot_execute.py run`/`review` without `--dry-run`, or a
  `copilot_ralph.py` tick that is neither `--demo` nor `--dry-run` — shells out to the real
  `copilot` CLI and spends AI Credits over the network.
- `--dry-run` and `--demo` are the only sanctioned smoke paths: both print what would happen
  (argv, stops, estimate, runway) and spawn nothing.
- This repo's own test suite never invokes the real CLI; every dispatch and verify call is an
  injected callable, and tests pass fakes or temporary stub executables instead.
- Budget caps in the Ralph profiles are halt conditions, not billing controls — the loop checks
  spend *between* ticks, so the tick that crosses the cap has already run and already spent
  before the loop stops on the next check.

## Deferred to Phase 3

Phase 3 landed with the copilot-costviz kit — see [COPILOT-COSTVIZ.md](COPILOT-COSTVIZ.md) for
the usage report (`bin/copilot_usage.py`) and the pooled-AIC runway
(`bin/copilot_pricing.py runway --pool-aic`). The aesop compile round-trip is written up as a
proposal for a future architect run inside the aesop repo
([AESOP-COMPILE-PROPOSAL.md](AESOP-COMPILE-PROPOSAL.md)); feeding real per-tick costs back
into the Ralph loop remains deferred — events.jsonl is written at session shutdown, not per
tick (see `.claude/kits/copilot-costviz/PLAN.md`).
