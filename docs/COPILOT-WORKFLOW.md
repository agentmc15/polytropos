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
- **One skill** in `copilot/.github/skills/lessons-loop/SKILL.md` — a durable-lesson pattern
  vendored from aesop, with a routing category wired into the `route` agent.
- **Two drivers** in `bin/`: `copilot_execute.py` (dispatches kit tasks and escalates on
  failure) and `copilot_ralph.py` (the goal loop).

Each agent's `model:` frontmatter pin is a tier choice, not a free-standing id: the test suite
checks it against the live tier for that id in `data/pricing.copilot.json`, so a future roster
change fails loudly instead of silently going stale. As a labeled snapshot tied to that file's
`cached_date` **2026-07-01**, the pins were: `architect` → `claude-fable-5` (frontier — kit
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

`status` prints each task's state; `run` dispatches the next eligible task (or `--task ID`) to
an agent and reruns its verify command; `review` dispatches the `reviewer` agent at a phase
boundary. One dispatch has this anatomy:

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
with no reported progress), and a budget cap in USD. They come in three named profiles — pinned
from aesop commit `5506617`'s Ralph guardrails, loop knobs rather than prices:

| profile | max iterations | no-progress stop | budget cap |
|---|---:|---:|---:|
| token-lean | 20 | 2 | $5 |
| balanced | 40 | 3 | $25 |
| accuracy-max | 80 | 4 | $100 |

Any of the three can be overridden per run with `--max-iterations` / `--no-progress-stop` /
`--budget-usd`. Per-tick cost is parsed straight out of that tick's output when the CLI reports a
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
with a Copilot-harness routing category added. Lessons live in `tasks/lessons.md` as durable,
project-scoped entries; a routing lesson carries `"applies_to": ["routing"]` and states a
task-shape → tier rule.

The execute driver writes these candidates for you: whenever a task escalates, `run`'s NOTES.md
block gets an extra `lesson-candidate (routing): ...` line naming the task, the tier it was
pinned at, and the tier that actually finished it. The `route` agent reads `tasks/lessons.md` at
the start of every session and lets any matching `routing` entry override its default tier
heuristics — so a misroute recorded once stops recurring instead of getting re-diagnosed from
scratch each time.

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
