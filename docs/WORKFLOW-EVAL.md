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
python3 bin/workflow_eval.py list [--store-dir DIR] [--json]                   # every run in the evals store
python3 bin/workflow_eval.py propose --run ID --set workflow=reviewed --by "your name" \
    [--task-class CLASS] [--manifest MANIFEST_ID]
python3 bin/workflow_eval.py review  --proposal prop-... --by "a reviewer" --decision accept [--note ...]
python3 bin/workflow_eval.py apply   --proposal prop-...
python3 bin/workflow_eval.py rollback [--to N]
python3 bin/workflow_eval.py approve --case CASE.json --by "a reviewer" --decision accept \
    --scope SCOPE.json [--note ...]                                            # bind a decision to exact bytes
python3 bin/workflow_eval.py approvals   [--prefs-dir DIR] [--json]            # every approval, granted or refused
python3 bin/workflow_eval.py activation  [--prefs-dir DIR] [--json]            # read-only: what a run starting now resolves to
python3 bin/workflow_eval.py policy
```

`list` reads the evals store and says what is in it: one row per run whose `results.json` parses
at this evaluator's envelope version, and a named note for every entry that is not one, rather
than a silent omission. `approve`, `approvals`, and `activation` are the promotion surface the
decision-improvement work added, described in "Exact approval, protected activation" below.
Every subcommand that touches a store takes `--store-dir`, `--prefs-dir`, or both, so a test or a
walkthrough points at a temporary one instead of the real one; `plan` touches neither store, and
`demo` builds its own inside a `tempfile.TemporaryDirectory` it discards. Where the real stores
resolve is `python3 bin/runtime_data.py where`, never a path in this tree.

One harness has run a workflow live from here — Claude Code, once, on 2026-09-16; see "The live
plan, and the first run" below. Read which harnesses that is off the registry rather than off
this sentence: each harness's `workflow_evaluation` row in `primitives/harness-capabilities.json`
carries its own `verified` and `verified_on`, and `python3 bin/harness_adapter.py` prints them.
`unknown` there means no. `plan`, `card`, `list`, `demo`, `policy`, `approvals`, `activation`, and
every test spend nothing; `run` dispatches only behind both `--live` and `--max-usd`.

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

## Changing a routing default — the legacy file

`routing-policy.json` in the `prefs` store records the workflow and policy defaults an operator
has adopted, overall or per task class. It is written only by `apply`.

1. **`propose`** names one change (`--set workflow=…`, `--set policy=…`, repeatable, and
   optionally `--task-class`) and the run whose evidence supports it. It refuses when the run
   measured no such variant, when that variant is below the evidence floor, when the run has a
   single repeat, or when the run's tasks already backed the policy in force: evaluation tasks
   stay reserved from the tuning they fed. The proposal records the base version it was made
   against. `--manifest` additionally records a reference to an evaluation manifest in the store
   — the manifest is read and re-digested first, so the reference names content rather than a
   name.
2. **`review`** is a named person's decision. There is no `--yes`.
3. **`apply`** refuses an unreviewed, rejected, or already-applied proposal, and one whose base
   no longer matches the file in force. It writes the next version atomically and keeps the
   previous bytes under `routing-policy.history/` beside it.
4. **`rollback`** restores an earlier version (`--to N`) and keeps the one it replaced; `policy`
   shows the version in force, the history, and every proposal. Every step is journalled.

Consumption is pull-only. No driver reads this file; a kit's PLAN.md `workflow:` and `routing:`
lines still decide, and wiring the applied default into a driver is a deliberate change, not a
side effect of `apply`. `repo_bench apply` remains the writer of the tier map in
`repo-bench.json` under the same store with its own refusals, and is not versioned by this
process.

## Policy bundles, beside the legacy file

The four steps above are now the **legacy** path, and they stay exactly as described: that file
is still the thing `apply` writes and `policy` reads. What sits beside them is a second, richer
way to say "these parameters are in force", introduced by the decision-improvement work and not
yet reachable in a running state.

`bin/decision_contract.py` owns the RECORD — what a policy bundle and a candidate proposal are,
and every refusal that makes one well formed. It is a library with no CLI: it starts no process,
opens no store, and reads no home directory. `bin/decision_policy.py` owns the SELECTION over
those records, and is pure in the same way — it opens no file, writes nothing, and every fact it
reasons about arrives as an argument.

`decision_policy.resolve_bundle(pin, bundles, runtime)` answers which bundle's data parameters
apply. Given a pin, a catalog of bundle payloads, and what a runtime can establish about itself,
it walks the bundle's own declared fallback chain — bounded by `MAX_FALLBACK_DEPTH`, refusing a
cycle — and ends at legacy, which is reachable from everywhere and needs nothing, so there is no
input for which it has no answer. With no pin it returns legacy with the reason `no-pin`. Three
failures stop the walk instead of following the fallback, because a bundle whose content moved
has a fallback pointer written by whoever moved it: an unknown id (`bundle-unknown`), a payload
that will not parse (`bundle-invalid`), and content whose digest does not match the pin that
named it (`bundle-content-mismatch`). Every reason it can give is a member of
`RESOLUTION_REASONS`, and the module's docstring is explicit that selecting a bundle is not an
approval, a permission, a budget, an admission, or an activation.

Two mode vocabularies keep the two halves apart:

| Constant | Members | What it means |
|---|---|---|
| `decision_policy.SELECTION_MODES` | `legacy`, `shadow` | the two modes this module implements. `legacy` is the frozen existing behaviour and the default everywhere; `shadow` additionally records the advice and compares it to the baseline. Neither acts on advice. |
| `decision_policy.DEFERRED_MODES` | `canary`, `active` | the two it deliberately does not implement, because they are a runtime activation. A selection that quietly downgraded one of them to shadow would hide the fact that the transition never happened. |

So the relationship between the two models is: the legacy file is a preference an operator
adopted and a driver may be wired to read; a bundle is a set of data parameters a run could be
pinned to. Nothing mints such a pin today (see below), every run resolves to legacy, and neither
model consumes the other — `apply` writes no bundle, and `resolve_bundle` never reads
`routing-policy.json`.

## Exact approval, protected activation, and what they refuse

This is what the decision-improvement work put into this engine. All of it is mechanism, and
every running state it describes is a state it refuses; the authority for that reading is
[`docs/DECISION-IMPROVEMENT-V1-HANDOFF.md`](DECISION-IMPROVEMENT-V1-HANDOFF.md), with the
offline conformance run in
[`docs/DECISION-IMPROVEMENT-CONFORMANCE.md`](DECISION-IMPROVEMENT-CONFORMANCE.md).

### Exact approval — `approve`, `approvals`

An approval binds a decision to the exact bytes it was taken over. `approve --case CASE.json`
reads a case whose keys are `candidate`, `in_force`, `manifest`, `run`, `partition` and
`proposed_by`; `decide_approval` then produces a record with four bindings — the candidate
proposal through the contract's own parser and digest, the immutable evaluation manifest, the
exact held-out partition inside that manifest the result was read over, and the source run's
result envelope. `approval_holds` re-derives all four **at check time**, each by the same
function that derived it in the first place, and reports which slot moved rather than raising.
Three rules do the work: a slot that raises on re-derivation counts as moved, a slot that was
never bound counts as moved, and `holds` is False as soon as one slot moved. Every binding row
carries `re_derived_by`, naming the function that actually re-derived it, so a row cannot say
`satisfied` over evidence nobody consulted.

`decide_approval` runs all four of its gates every time rather than stopping at the first, so a
caller is told the whole reason. One of them is `self-approval`: a proposer cannot approve its
own candidate, refused by comparing the approving name against the case's `proposed_by`. Nothing
refused is `approved`; `partial` alone is `insufficient-evidence`, which means the evidence was
too thin to score and is a different fact from a verdict against the candidate; anything else is
`rejected`. A refused record is written and listed by `approvals` exactly like a granted one,
because a refusal nobody can read is a refusal nobody can review. `approve` exits 0 when the
approval was granted and 3 when it was not.

What it refuses to claim is machine-readable and unconditional. `APPROVAL_UNPROVEN` —
`actor-not-authenticated`, `isolation-not-demonstrated`, `origin-not-dereferenced` — rides on
every record whatever its state, and no check in the section can discharge any of them. Binding
gives integrity: the thing evaluated is the thing approved, and a later re-derivation notices
any of it moving. Binding is not authority — `by` is a string checked for being non-empty and
for differing from `proposed_by`, so four correct digests prove the content did not move and
prove nothing about who typed the name. Binding is not isolation: a content hash detects change
and prevents nothing. Downstream, `PROMOTION_APPROVAL_BLOCKERS` keeps `exact-approval-missing`
and `exact-approval-not-re-derived` as two codes rather than one, on the rule the whole file
runs on — an unmade check is not a passed one.

### Protected activation — `activation`

`activation_decision` answers whether a runtime would be permitted to move to `canary` or
`active`. It does read — `require_held_out` opens the evals store's exposure log, which is the
whole point of the manifest gate — and it writes nothing, creates nothing, starts nothing,
dispatches nothing and mints nothing. Like `decide_approval` it evaluates every row so the
caller gets the blocker SET, and `permitted` is the conjunction of all of them. Today it is
False by construction: `CONFINED_DISPATCH_WIRED` is `False`, so the dispatch row is unsatisfied
and every transition is refused. That constant is one fact with two halves deliberately joined —
`gate_protected_dispatch` applies no confinement of its own, and records nothing in
`bin/attempt_ledger.py`, which this repository requires of every dispatch before and after it
runs — so whoever wires a live protected trial flips it in the same edit that adds both.

`runtime_activation(prefs_dir, scope)` is the read side, and it resolves every run to legacy. An
absent pointer is legacy with reason `no-pointer`, and that is not an error; so is an unreadable
pointer, a retired one, a rolled-back one, one whose gate block contradicts
`CONFINED_DISPATCH_WIRED`, and one whose declared eligibility this run falls outside. Every exit
that is not a live running state is legacy, and `reasons` says which, out of the closed
`RUNTIME_REASONS` vocabulary. A run reads the pointer once, at the start, and carries that
answer for its whole life: nothing in this repository re-reads a pointer mid-run, so a run that
began under generation 4 keeps generation 4's bundle after generation 5 lands. `activation` is
read-only, and there is deliberately no command that activates anything: a command offering the
transition would offer something that cannot happen, and if one day it can, the edit that wires
it has to add the command in the same change.

**Where each digest is re-derived, which is easy to get backwards.** The pointer swap is a
compare-and-swap and nothing more. `swap_activation` writes generation `expected + 1` through
`safe_paths.confined_create_bytes`, whose `O_EXCL` makes "is this name free" and "write these
bytes" one kernel operation; there is deliberately no re-read of the directory first, because a
check followed by a write has a window and this has none. A stale expectation fails on the
kernel's own answer — the name it would write is already taken — and the loser writes nothing at
all rather than half of something. The swap **decides** nothing, and in particular it does not
check that a bundle's content still matches its pin. That comparison happens at RESOLUTION time,
inside `decision_policy.resolve_bundle` via `matches_ref`, and reports
`bundle-content-mismatch`. Two different moments, two different functions.

### The trial protocol, and the policy evidence report

`build_trial_protocol` produces a three-arm (`ARMS` = `A`, `B`, `C`) recovery-trial
**specification**: content-addressed, immutable, and explicitly not a run. Nothing in it
dispatches, grades, mines, or writes. What it produces is a document saying, in a closed
vocabulary, exactly what would have to be true before the experiment could run — and the closed
vocabulary is `PROTOCOL_BLOCKERS`:

| Blocker | What is missing |
|---|---|
| `manifest-unverified` | a manifest that does not match its own digest. A forgery finding; nothing may be read out of it |
| `no-held-out-evidence` | a manifest that verifies and whose partition is simply empty. An honest document with nothing in it |
| `cohort-not-frozen` | no immutable manifest was supplied, so the cohort is not frozen |
| `protected-profile-uncertified` | `exec_policy.certify_profile` has no sentinel report to certify over |
| `confining-dispatch-unwired` | `CONFINED_DISPATCH_WIRED` is `False` |
| `full-task-study-not-run` | no whole-task study has run; a checkpoint study conditions on having already failed once and cannot answer the rollout population's question |
| `operator-declaration-missing` | one named operator declaration per missing item, never one code for all of them |

The first two are two codes rather than one on purpose: a reader who could not tell them apart
would read a fabricated cohort as a thin one.

`policy_evidence_report` assembles what the surrounding modules already computed — lineage,
scope, interventions, resource bases, quality, monitoring, escaped defects — and computes none
of it itself. Its refusal is the one that matters here: it ends by calling
`assert_no_gain_claim` over the assembled document, `notes` included, which is where caller
prose enters. That sweep matches every string in the document, keys and values alike, against
`GAIN_TOKENS` after lowercasing and dropping non-alphanumeric characters, so "a 12% Win-Rate
improvement" is caught twice. It also names exactly what it does not prove: it is a token match,
shape-matching cannot establish absence, and `NO_GAIN_CLAIM` lists spellings it misses
(`outperform`, `uplift`, `lift`, `beat the baseline`, `better than`, `efficiency`, `reduction`)
rather than implying it caught them. It can refuse an honest document whose relayed data happens
to carry a token — an arm named `improved-repair`, say — and that is the direction it prefers: a
loud refusal over a silent claim. `POLICY_EVIDENCE_UNPROVEN` rides on the report
unconditionally: `mechanics-not-performance`, `no-live-outcome-observed`,
`monitoring-not-authority`.

### The sibling modules

Four modules sit beside this engine. None of them is wired into a driver.

- **`bin/decision_eval.py`** — the read-only prediction-time join: one row per decision, placing
  every fact in time against the prediction instant, so what a decision was taken on is never
  mixed with what only became true later. It also reports calibration, with
  `insufficient-evidence` for thin or mismatched data, and refuses a key spelled like one of
  `CAUSAL_TOKENS`. It opens no file and takes no path.
- **`bin/decision_context.py`** — bounded context-repair candidates: which files a failed
  attempt was not shown, as a deterministic, versioned manifest with the navigation evidence
  that found each one. A graph edge is navigation evidence and never a dependency claim;
  `CANDIDATE_KINDS` has no dependency member, so there is no field a dependency could live in.
- **`bin/improvement_loop.py`** — bounded candidate drafts. An orchestrator with zero write
  primitives: no envelope, no proposal file, no preference file, no manifest, no store, no
  second ledger. A draft is a payload in memory and on stdout, so `draft --job ...` run a
  thousand times changes nothing on disk. Neither drafting mode asks a model anything, and the
  optional model proposer is declared and not wired — `PROPOSER_WIRED` is `False`, there is no
  runner parameter anywhere in the module to hand a dispatcher through, and asking for it
  refuses.
- **`bin/decision_provider.py`** — the two providers that can answer a decision request.
  `PROVIDER_MODES` is `rules` and `replay`: `rules` is a deterministic local computation over
  the request's own declared state, shipping with an empty default rule table on purpose, and
  `replay` is a lookup into a content-addressed store of prior results. Each abstains on a miss
  rather than guessing, and `replay` incurs no new inference.

### What the handoff says is deliberately unfinished

Two things, and the handoff keeps them apart because merging them would misread both.

- **`canary` and `active` are unavailable on every harness, and no live trial has run.** The
  refusal is derived, not written down: `CONFINED_DISPATCH_WIRED` is `False`, so
  `activation_decision` refuses every transition and `runtime_activation` resolves every run to
  legacy. There is no partially available canary. No vendor client has been run by any test,
  verify command or gate; no protected profile has been certified, because producing a sentinel
  report means spawning sandboxed processes and binding a loopback port; no confining, ledgered
  dispatch path exists, so every check of a *running* state here is a check of a refusal; no
  operator has declared the trial inputs, so the plan is `trial-plan-incomplete` by name; and no
  approval has bound anything, because there is nothing evaluated to bind. The assessment's
  `gain_observed` is `null`, and the release makes no performance claim at all.
- **Cursor's adaptive profile is `unsupported` pending independent proof — which says nothing
  about Cursor's current CLI implementation.** That implementation is present and verified, with
  dated `verified: supported` rows against a named client version, and nothing in this work
  retires, reimplements or reports it as absent. What is deferred is new adaptive extension. The
  same distinction holds for concurrency: the existing implementation is intact and out of
  scope.

## What remains untested

Every card carries this list, from `workflow_eval.UNTESTED_CLAIMS`:

- no universal superiority of a workflow, policy, model, or harness is supported: a variant
  ranks within one run, one repository, one instruction version;
- repricing an observed trace at another harness's rates is a hypothetical comparison, not
  evidence that harness would have produced the same result;
- graph-grounded versus targeted-search prompting is not a variant axis here;
- lesson versions are not a variant axis here; instruction versions are;
- the reviewer's read-only mode is the CLI's documented flag, not an OS boundary; only the kit
  workflow's check runs under `bin/exec_policy.py`.

Ahead of that list, `untested_claims()` prepends one more sentence naming which harnesses have
still never run live — and it names them from the registry's `workflow_evaluation` rows, not from
a constant. That is a correction, not a refinement: on 2026-09-16 the first live run on Claude
Code left the flat sentence "no workflow has been run live from this repository on any harness" in
its own results envelope, because the claim was a constant. It is now derived per harness, so it
cannot go stale the same way.
