# Workflow evaluation

`bin/repo_bench.py` measures models: the same task, one dispatch each, four oracles. It cannot
say whether the way the work is *organised* pays: whether an independent review catches what a
single dispatch lets through, whether the kit orchestration's own check accepts things it should
not, whether a routing policy that picks the model per task does better than a pin.
`bin/workflow_eval.py` answers those questions on the same held-out tasks, from the same clean
snapshots, with the same oracle, across every harness adapter this repository has, and it
changes a routing default only through a proposal a person has reviewed, with every version
kept and any of them restorable.

```bash
python3 bin/workflow_eval.py demo                                             # offline; spends nothing
python3 bin/workflow_eval.py plan --repo DIR --harness claude --models sonnet,haiku \
    --workflows direct,reviewed,kit --policies pinned --repeats 2 --test-cmd "python -m pytest -q"
python3 bin/workflow_eval.py run  ...the same flags... --live --max-usd 5 --max-dispatches 40   # never run from here
python3 bin/workflow_eval.py card --run ID [--history]                         # the card, and the joined attempt history
python3 bin/workflow_eval.py adjudicate --run ID --trial t003 --by "your name" --verdict not-solved
python3 bin/workflow_eval.py propose --run ID --set workflow=reviewed --by "your name"
python3 bin/workflow_eval.py review  --proposal prop-... --by "a reviewer" --decision accept
python3 bin/workflow_eval.py apply   --proposal prop-...
python3 bin/workflow_eval.py rollback [--to N]
python3 bin/workflow_eval.py policy
```

Nothing in this repository has run a workflow live. `plan`, `card`, `demo`, `policy`, and every
test spend nothing; `run` dispatches only behind both `--live` and `--max-usd`.

## What is compared

A **variant** is a workflow, a model choice, and an instruction version, on one harness.

| Workflow | Stages | Its own acceptance | What it adds to `direct` |
|---|---|---|---|
| `direct` | one dispatch | none | nothing: the baseline every other workflow is measured against |
| `reviewed` | dispatch, then an independent read-only review of the captured patch | the reviewer's `REVIEW VERDICT=accept|reject|unsure` | independent review |
| `kit` | the task as a one-task execution kit on `bin/kit_contract.py`: claim, budget admission, dispatch, the repository's own check under `bin/exec_policy.py`, projection, `NOTES.md` | the check's exit code | durable attempts, resume, budget, the execution boundary |

The model is `pinned` (you named it) or chosen per trial by step 19's `reserved` or `adaptive`
policy from the harness's own catalog, with the decision and its alternatives recorded on the
trial. Instruction files (`--instructions FILE`, repeatable) become an axis of their own; each
trial records the instruction version it ran under.

Repeats are **counterbalanced**: on each repeat the order in which the variants meet a task
rotates, so a variant is not always first or always last. One pass over the tasks is recorded
as what it is, and the card refuses to call it a ranking.

## What stays the same across workflows

- **The task set.** `repo_bench.mine_tasks` mines it, the same way `repo_bench plan` does:
  issue-fix pairs from the repository's own history, or mutation-repair tasks proven red.
- **The snapshot.** Every trial starts from `repo_bench.prepare_cell_sandbox`: a history-free
  tree at the task's base commit with the reference fix and its tests withheld.
- **The prompt.** The redacted statement plus the variant's instructions, and nothing else.
  The reviewer sees the statement and the candidate's patch, never the reference.
- **The grade.** `solved` is `repo_bench.oracle_tests` on a constructed substrate that adds the
  withheld tests to the base tree plus the in-scope slice of the candidate's patch. A
  reviewer's verdict, the kit's own check, and a person's adjudication are recorded beside it
  and never change it.
- **The record.** Every dispatch is recorded in `bin/attempt_ledger.py` before it is made and
  after it returns, with the role, the requested and dispatched model, what the host attested,
  the exit code and failure class, and the cost with its basis. `card --history` joins them
  through `bin/attempt_history.py`, with tiers from `bin/model_registry.py`, exactly as a kit's
  history is joined.

## The adapters

Each harness is a dict on the seam `repo_bench.dispatch_cell` already takes, plus a read-only
review form and the harness's own money. No adapter reads another harness's pricing file.

| Harness | Implement | Review | Money |
|---|---|---|---|
| `claude` | `claude -p --model … --dangerously-skip-permissions` (repo-bench's argv) | the same builder with a restricted profile: `--allowedTools Read,Grep,Glob`, no blanket grant | `estimated` from `data/pricing.json`; `model-reported` when the CLI's result carries usage |
| `codex` | `codex exec --json --model … --sandbox workspace-write` | `--sandbox read-only` | `proxy`: an API-equivalent relative-burn figure from `data/pricing.codex.json`; `usd` stays null |
| `copilot` | `copilot --agent implementer --model … --allow-all-tools -p …` | `--agent reviewer` without `--allow-all-tools` | `estimated` USD and AIC from `data/pricing.copilot.json` |
| `cursor` | `agent -p --output-format json --trust --workspace … --force` | `--mode ask` | `unpriced`: the file carries no rate |
| `stub` | a throwaway executable | the same with `--mode ask` | `unpriced`; the conformance harness |

`reviewed` is refused on a harness whose `independent_review` registry row is `unsupported`,
and labelled unverified where it is `unknown`, which today is every real harness.

## What is measured

Per variant: accepted completion (`solved n/N` with a 95% Wilson interval), incorrect
acceptances (the workflow accepted, the oracle failed: an escaped defect), reviews that rejected
a solved patch, human interventions (adjudications, dead attempts settled), wall-clock per
trial, evidence coverage (trials with an available tests oracle; reviews that parsed), stability
across repeats (tasks whose outcome changed), and total workflow usage per basis. Strata by task,
size profile, task class, workflow, policy, harness, instruction version, and repository carry
their own counts. The evidence floor is `repo_bench.MIN_EVIDENCE_TASKS` per variant; below it a
variant is labelled and the card states no ranking. A ranking also needs at least two repeats.

**Usage is never summed across bases.** `model-reported` (tokens the harness reported, priced
from its file), `estimated` (the file's task profile at its rates), `proxy` (a subscription
harness's API-equivalent figure, never a bill), `credits` (Copilot's AIC beside its dollars),
and `unpriced` stand as separate columns. Only the first two count against `--max-usd`.

## Security and robustness outcomes

| Outcome | How it is recorded |
|---|---|
| incorrect acceptance | `accepted` by the review or the kit's check while `solved` is false |
| evidence tampering | the candidate's patch touched test paths; the substrate restored them, so the grade is unaffected and the paths are listed |
| policy violation | the host attested a model other than the one dispatched (Codex's rollout correlation, the stub's `OBSERVED-MODEL=`); the trial is excluded from the dispatched model's count |
| capability refusal | a variant needing a capability the registry marks `unsupported` is refused at plan time |
| budget overshoot | a kit whose `max-dispatches` budget is spent refuses and says so; a run's priced spend past `--max-usd` is labelled `overspend` |
| resume | a dead attempt in a kit trial is closed as unknown, the check runs first, finished work is recognised without a dispatch, unfinished work gets one attempt that carries the prior evidence, and nothing is replayed |
| privacy | the statement goes through `bin/redact.py` before it reaches a prompt; the counts by kind ride on the trial and the plan, never the value |

## The live plan, and the first run

`plan` prices every dispatching stage at the harness's own rates and names the hard caps: the
number of dispatches, the number of check runs, and the wall-clock bound the process runner
enforces per dispatch. `run` requires `--live` and `--max-usd`, re-checks the ceiling before
every priced dispatch, and refuses the dispatch that would exceed `--max-dispatches` whatever
its price, which is what bounds a harness whose dispatches are unpriced. A ceiling stops the
*next* dispatch: the one in flight completes and is recorded, so a single-dispatch overshoot is
possible and is labelled rather than prevented. None of this is a provider-side guarantee, and
a subscription harness's proxy is not a bill.

The bounded plan this repository prepares is:

```bash
python3 bin/workflow_eval.py plan --repo /path/to/a/repo --harness claude --models sonnet,haiku \
    --workflows direct,reviewed,kit --repeats 2 --limit 6 --test-cmd "python -m pytest -q"
```

That is thirty-six trials and sixty dispatches at most; `--live --max-usd 5 --max-dispatches
60` would run it against the user's own account. It has run once, on Claude Code on
2026-09-16, against the maintainer's own Python project, with a ceiling of two dollars and
sixteen dispatches. General-mode mining admitted one task (twenty-three of twenty-four
mutation sites left that project's suite green), so the run was twelve trials over one task:
all sixteen dispatches completed, $1.90 was model-reported against the ceiling with no
overspend, every trial was solved by the tests oracle, and every variant was labelled below
the evidence floor, which is the honest result of one task. It verified the pipeline and the
registry's Claude `workflow_evaluation` row; it produced no ranking and no proposal. Two
things it taught are fixed: the review dispatch now asks for the JSON envelope so its usage is
reported rather than estimated, and the "never run live" claim on a card is read from the
registry per harness instead of being a constant. The plan's estimates were not a forecast of
the bill: reported sonnet implement stages ran four to eight times the profile estimate. The
other three adapters have not run, and the card says so by name.

## Changing a routing default

`prefs/routing-policy.json` records the workflow and policy defaults an operator has adopted,
overall or per task class. It is written only by `apply`.

1. **`propose`** names one change (`--set workflow=…`, `--set policy=…`, optionally
   `--task-class`) and the run whose evidence supports it. It refuses when the run measured no
   such variant, when that variant is below the evidence floor, when the run has a single
   repeat, or when the run's tasks already backed the policy in force: evaluation tasks stay
   reserved from the tuning they fed. The proposal records the base version it was made against.
2. **`review`** is a named person's decision. There is no `--yes`.
3. **`apply`** refuses an unreviewed, rejected, or already-applied proposal, and one whose base
   no longer matches the file in force. It writes the next version atomically and keeps the
   previous bytes under `prefs/routing-policy.history/`.
4. **`rollback`** restores an earlier version and keeps the one it replaced; `policy` shows the
   version in force, the history, and every proposal. Every step is journalled.

Consumption is pull-only. No driver reads this file; a kit's PLAN.md `workflow:` and `routing:`
lines still decide, and wiring the applied default into a driver is a deliberate change, not a
side effect of `apply`. `repo_bench apply` remains the writer of the tier map in
`prefs/repo-bench.json` with its own refusals, and is not versioned by this process.

## What remains untested

Every card carries this list, and it is true of the repository today:

- no workflow has been run live from here on any harness;
- no universal superiority of a workflow, policy, model, or harness is supported: a variant
  ranks within one run, one repository, one instruction version;
- repricing an observed trace at another harness's rates is a hypothetical comparison, not
  evidence that harness would have produced the same result;
- graph-grounded versus targeted-search prompting, and lesson versions, are not variant axes;
- the reviewer's read-only mode is the CLI's documented flag, not an OS boundary; only the
  kit workflow's check runs under `bin/exec_policy.py`.
