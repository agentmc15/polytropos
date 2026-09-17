# Decision and improvement — authority inventory

This is task D03 of the `decision-improvement-v1` kit. It maps, for the decision and improvement
work, **who writes what today**, **which field a later task must add and to which event**, and
**what the existing code already guarantees** so that no task re-derives it or duplicates it.

It is an inventory of the repository as it stands, not a change to it. D03 edits no file under
`bin/`, `tests/`, `data/` or `primitives/`.

- **Revision inspected:** `71bb3aebf26544f20f9c016dba881aca6b2123e4`, branch
  `codex/decision-improvement-plan`. The working tree carried one modified file at the time
  (`.claude/kits/decision-improvement-v1/TASKS.md`, the executor's own status bookkeeping); no
  `bin/` file was dirty.
- **Method.** Every module, symbol and line cited below was opened and read. Reach claims ("X
  loads Y") were traced through the mechanism each module actually uses — `_sibling(...)`,
  `importlib.util.spec_from_file_location`, a module-level assignment — and each hit was confirmed
  to be code, not a comment. D01 was revised for exactly that mistake; this document repeats the
  check rather than the mistake.
- **Companion documents.** `docs/DECISION-IMPROVEMENT-RECONCILIATION.md` (and its JSON twin)
  classify original roadmap steps 16–26. `tasks/kits/decision-improvement/PLAN.md` is the
  architecture. This document is the authority map those two point at.

## What this document does and does not claim

**It does not claim any new field, reference, event, state or module exists.** Naming
`bin/attempt_ledger.py` as the future owner of an acceptance reference is a statement about where
that reference *belongs*; it is not a statement that the reference is there. Every row below is
marked either **exists** (read in the source at this revision) or **to add** (a later task's
deliverable, named by task id). No row is both.

**It changes nothing.** No code, no test, no pricing file, no capability row, no policy file.
The one non-`docs/` effect of adding this file is the regenerated deep-dive mirror under
`docs-site/deep-dives/`, which `bin/docs_build.py` owns and which is never hand-edited.

**Hashes identify content; they are not security.** The shared PLAN states this and this document
restates it because the inventory below is full of digests. A content hash tells you that two
things are the same bytes or that something changed. It does not authenticate an actor, isolate a
worker, or make a record tamper-evident against a process running with the user's own privileges.
`bin/attempt_ledger.py`'s own module docstring says so in the clearest terms available — the store
lives outside the workspace so that ordinary paths (a verify command confined by
`bin/exec_policy.py`, a git operation, a synced tree) do not touch it, and it states plainly that
this is "Not tamper-proof". A protected experiment therefore needs D07's executable sentinels, and
an approval needs D22's binding at the execution boundary. Neither a worktree, nor `0700` modes,
nor a digest is the boundary.

## One owner per concern

Each concern below has exactly one writing authority. Callers are listed separately; a caller is
not a second owner.

| Concern | Sole owner | What it writes | Callers that reach it |
| --- | --- | --- | --- |
| The attempt event stream (its record shape, bounding, redaction and append) | `bin/attempt_ledger.py` (`AttemptLedger.append`) | append-only JSONL, one event per line, stamped `LEDGER_VERSION` | `kit_contract.open_ledger`, `copilot_ralph`, `workflow_eval`, `kit_scheduler` |
| A driver's write path into that stream | `bin/kit_contract.py` (`TaskRun`, plus the module-level `record_roster`) | `begin` / `precheck` / `attempt_started` / `attempt_finished` / `verify_finished` / `project` / `end`, and `record_roster` — which appends through `lifecycle.ledger` directly rather than through a `TaskRun` method | all four native drivers, `workflow_eval`, `kit_scheduler` |
| Reading those events back as one record per attempt | `bin/attempt_history.py` | nothing — read-only join and projection | `workflow_eval.history_records`, the `attempt_history` CLI |
| Task grammar, readiness, DAG validation, status transitions, run ids | `bin/kit_contract.py` | `TASKS.md` status lines, `NOTES.md` blocks | all four drivers, `kit_scheduler`, `attempt_history` |
| Budget admission (which cap an operation draws down, and refusal before spend) | `bin/kit_contract.py` (`OPERATION_CAPS`, `BudgetAdmission`, `budget_gate`) | in-memory grants; a `budget-stop` NOTES line on refusal | all four drivers, `kit_scheduler`, `workflow_eval` |
| Acceptance evidence (which artifact a verdict was reached on, and its upstream versions) | `bin/attempt_ledger.py` (`record_projected`, via `TaskRun.project`) | the `task.projected` event's `artifact` and `upstream` | read back by `kit_contract.evidence_freshness` |
| The deterministic routing decision | `bin/routing_policy.py` (`decide`, `explain`) | nothing durable — it returns a dict | `codex_policy`, `workflow_eval`, `release_gate` (version constant only) |
| Codex's policy resolution and catalog | `bin/codex_policy.py` | nothing durable | `codex_execute` |
| Evaluation envelopes, the policy file and its proposal lifecycle | `bin/workflow_eval.py` | the `evals` store (`results.json`, `plan.json`, per-trial JSON) and the `prefs` store (`routing-policy.json`, history, proposals, journal) | its own CLI |
| Benchmark run store, task mining, sandboxes, the four oracles | `bin/repo_bench.py` | the `benchruns` store — its source says of that store, "this module is its only writer" | `workflow_eval` (mining, oracles, ceiling arithmetic) |
| Where every private store lives, and its `0700`/`0600` posture | `bin/runtime_data.py` | store directories only | every store-owning engine |
| Starting an external process, and measuring how long it took | `bin/proc_runner.py` (`run`, `_result`) | nothing persistent — it returns a result dict | every dispatcher and verify runner |
| Confinement of a write/read/delete into a caller-selected root | `bin/safe_paths.py` | nothing of its own | the ledger, the scheduler manifest, the installers |
| The execution boundary a verify command runs under | `bin/exec_policy.py` | nothing persistent | drivers, `workflow_eval` |
| The declared set of contract version constants for the release surface | `bin/release_gate.py` (`VERSION_SOURCES`) | the marked block of `docs/RELEASE.md`, via its own `build` | its own CLI |
| Report projection over `NOTES.md` grammar lines | `bin/routing_scorecard.py` | nothing — read-only | its own CLI |
| Native dispatch loops, escalation ladders and per-harness argv | the four `*_execute.py` drivers | through `TaskRun` only | — |

Two consequences worth stating, because both are easy to get wrong:

- **`workflow_eval` is not a second ledger.** It opens `attempt_ledger.AttemptLedger` against its
  own per-run directory (`self.run_dir / "attempts"`, `workflow_eval.py:804`) and against a
  synthetic kit through `kit_contract.open_ledger` (`workflow_eval.py:1001`). Same writer, same
  event shape, different store location. Adding a reference to the ledger therefore reaches the
  evaluation's own dispatches for free — and adding one *only* to the kit path would silently miss
  them.
- **`kit_scheduler` writes to the kit's ledger too**, through `_record` → `ledger.append`, under
  its own lock. Its kinds are `scheduler.*`, `integration.*` and `plan.*`. It is a caller of the
  owner, not a competing owner.

## The four native drivers, precisely

| Driver | Dispatch runner it binds | Shape that runner returns | Extra fields it passes to `attempt_finished` | Reaches `routing_policy`? |
| --- | --- | --- | --- | --- |
| `bin/claude_execute.py` | `_CONTRACT.provider_runner("claude")` (line 544) | `(rc, output)` | none | **No.** Zero occurrences of `routing_policy`, `codex_policy` or `_sibling` in the file. |
| `bin/codex_execute.py` | its own `default_runner` (line 839) | `(rc, DispatchOutput, telemetry)` where telemetry is model **attestation** | `observed_model` | **Yes, transitively**: `_ROUTING = _POLICY._rp()` at line 231, resolved in `codex_policy._rp` at line 279. |
| `bin/copilot_execute.py` | `_CONTRACT.provider_runner("copilot")` (line 244) | `(rc, output)` | none | **No.** Same zero-occurrence check as Claude. |
| `bin/cursor_execute.py` | its own `default_runner` (line 121) | `(rc, output, result)` — the whole `proc_runner` result dict | `proc_outcome`, `observed_model` | **No.** |

Only the Codex driver dispatches under a routing decision. The other three direct loaders of
`bin/routing_policy.py` are `bin/workflow_eval.py:197` and `bin/release_gate.py:143` (the version
constant only). This is load-bearing for D13's seam and for D18's arm design: a policy change
observed on Claude, Copilot or Cursor today is a change to something nothing consults.

## Which event owns each new reference

Every reference below is **to add**. None exists at this revision.

| Reference | Owning event | Written through | Correlation | Schema version | Owning task |
| --- | --- | --- | --- | --- | --- |
| `acceptance_ref` — the identity of the acceptance criteria the attempt was dispatched against | `attempt.started` at request time, and `task.projected` at acceptance time | `TaskRun.attempt_started` / `TaskRun.project` | `(namespace, run, task, attempt)` | its own constant, not the ledger's | D04 |
| `policy_ref` — the bundle id and content hash the run is pinned to | `attempt.started` | `TaskRun.attempt_started` | as above, plus the bundle's own immutable id | the bundle contract's version | D04, defined by D11 |
| `decision_ref` — the id and content hash of the decision record that produced the selection | `attempt.started` | `TaskRun.attempt_started` | its own decision id; one decision may precede several attempts, so the id cannot be derived from the attempt id | the decision contract's version | D04, defined by D09 |
| `admission_ref` — the identity of the grant that admitted this operation | `attempt.started` | `TaskRun.attempt_started`, minted by `BudgetAdmission.admit` | `(namespace, run, task, attempt)`; the grant is issued immediately before the attempt id exists, so the mint must precede the record | `kit_contract.CONTRACT_VERSION` | D04 |
| `duration_s` and its basis | `attempt.finished` | `TaskRun.attempt_finished` (the parameter already exists) | as above | `LEDGER_VERSION` — no new constant | D05 |
| partition / exposure manifest refs | the evaluation envelope | `workflow_eval` | `run_id` plus the manifest's content id | `MANIFEST_VERSION` | D06 |
| lifecycle and approval binding | the proposal and policy files | `workflow_eval` | proposal id, policy version | `PROPOSAL_VERSION`, `POLICY_VERSION` | D20, D22, D23 |

Three rules govern that table.

**The ledger stores a reference, never the payload.** `AttemptLedger.append` refuses any line over
`MAX_LINE_BYTES` (16 KiB, `attempt_ledger.py:67`) and says explicitly that exceeding it means a
caller bypassed the bounding. Free text that does reach the ledger is bounded and redacted first
(`bounded_tail`, `TAIL_CHARS`, `REPORT_CHARS`). A decision payload, a rubric or a state snapshot
therefore belongs in its own owner's store, with only its id and content hash on the event.

**The correlation ids are content-free and must stay so.** `kit_contract.generate_run_id` produces
`<UTC-date>-<4 hex>` from `secrets.token_hex(2)` and its docstring states why: `NOTES.md` is
committed in consumer repositories, so nothing content-bearing may enter it.
`attempt_ledger.new_attempt_id` says the same — "never a pid, path, hostname or timestamp". A new
reference id must follow that rule or it leaks through the same surface.

**The event `kind` vocabulary is not declared anywhere.** `AttemptLedger.append(kind, **fields)`
validates the line size and nothing else; each caller supplies a string. Twenty-six kinds are in
use at this revision, enumerated by walking every `append` and `_record` call in `bin/` for a
string-literal kind argument rather than by grepping for a pattern — a kind whose literal sits on
the line after the `append(` is invisible to the obvious grep, which is how `roster.checked` was
missed in this document's first draft:

- from `attempt_ledger`: `claim.taken`, `claim.released`, `claim.broken`, `attempt.started`,
  `attempt.finished`, `verify.finished`, `task.projected`;
- from `kit_contract`: `run.started`, `run.finished`, `verify.precheck`, `roster.checked`,
  `plan.drift`, `evidence.refreshed` — `run.started` and `run.finished` are also written by
  `copilot_ralph` for a goal loop that has no kit, so a kind is not owned by one write site;
- from `workflow_eval`: `eval.started`, `eval.finished`;
- from `kit_scheduler`: `scheduler.batch`, `scheduler.admission`, `scheduler.cancelled`,
  `security.violation`, `integration.manifest`, `integration.conflict`, `integration.applied`,
  `integration.verified`, `plan.revision-refused`, `plan.revision-proposed`, `plan.revised`.

A task that adds a kind adds it to no registry today, and nothing fails if two callers pick the
same word for different things.

## Missing fields, named

Each of these is absent at this revision. The point of naming them precisely is that several look
present and are not.

1. **`attempt.started` carries no acceptance, policy, decision or admission reference.** What it
   does carry (`AttemptLedger.record_started`, plus what `TaskRun.attempt_started` supplies):
   `run`, `task`, `attempt`, `op`, `model`, `prompt_sha`, `verify_sha`, `artifact`, `role`,
   `parent`, `requested_model`, `effort`, `actor`.
2. **`AttemptLedger.record_started` accepts `**extra`; `TaskRun.attempt_started` does not forward
   it.** `TaskRun.attempt_started` (`kit_contract.py:1854`) has a fixed keyword signature. So the
   ledger side is already extensible and the driver side is not: D04 must widen the `TaskRun`
   signature, which is the one shared module every driver calls. That is a serial edit by the kit
   PLAN's own rule.
3. **`AttemptLedger.record_projected` has no `**extra` at all** (`attempt_ledger.py:372`). Its
   parameters are exactly `run, task, status, result, outcome_line, note, artifact, upstream`. An
   acceptance identity on the projection requires a signature change here as well as in
   `TaskRun.project`.
4. **`attempt.finished` has a `duration_s` parameter that no native driver fills.** See the next
   section.
5. **`attempt_history.RECORD_FIELDS` has no field for duration, acceptance, policy, decision,
   admission, or the process outcome.** This is not merely an omission: `attempt_history.observe`
   raises `KeyError` for any key not in `RECORD_FIELDS`. A reference written to the ledger and not
   added to that tuple cannot be projected at all — the projection will refuse it.
6. **`attempt_history.summarize`'s `unknown` counter covers four fields** — `harness`, `tier`,
   `observed_model`, `cost`. A new reference is not counted as unknown until it is added there, so
   its absence would be invisible in the card rather than disclosed.
7. **A routing decision has no identity and no durable home.** `routing_policy.decide` returns a
   dict stamped `"v": CONTRACT_VERSION` with `task_id`, `policy`, `preference`, `shape`, `model`,
   `candidates`, `ladder`, `estimate` and `refusal` — and no id, no hash, and no writer. The only
   place a decision is durably recorded anywhere in this repository is the evaluation trial
   record, where `workflow_eval` stores `rp.explain(decision)` — the **rendered operator
   explanation**, prose, not a structured record (`workflow_eval.py:902` and `:958`). No attempt
   record references a decision.
8. **An admission has no identity.** `BudgetAdmission` counts grants in `self.granted` in memory.
   The only durable traces of admission are indirect: an attempt exists, therefore it was admitted;
   or a `budget-stop` NOTES line exists, therefore it was refused. `kit_scheduler` writes a
   `scheduler.admission` event, but only inside its `if refused:` branch
   (`kit_scheduler.py:659`), batch-scoped, listing task ids — not an admission id, and not
   correlated to an attempt.
9. **There is no acceptance identity.** `kit_contract.to_contract` carries `acceptance` as free
   text alongside `brief` and `verify`; `TASK_FIELDS` (`kit_contract.py:1427`) has no acceptance
   version or hash. `evidence_freshness` pins the *artifact* a verdict was reached on, not the
   *criteria* it was judged against.
10. **The evaluation envelope has no grouped, content-addressed partitions.** Its `holdout` is
    `{"tasks": sorted(...), "reserved_from": "routing tuning"}` (`workflow_eval.py:1126`) — a flat
    list with no grouping of related defect variants, no content identity, and no exposure or
    retirement record. That is D06's gap, and `repo_bench` already owns the content identities the
    manifest would cite.

    **Correction, D08 phase-2 review, 2026-09-16.** Item 10 is no longer true and its citation has rotted. D06 implemented exactly this: `build_manifest`/`verify_manifest` content-address the pool into grouped partitions, `MANIFEST_VERSION` sits on the referenced object, and manifests persist under `<run_dir>/manifests/` rather than the evaluation-store root. The `workflow_eval.py:1126` citation points at the pre-D06 revision this document stamps (`71bb3ae`) and is off by roughly 1200 lines against HEAD. The gap is closed; the numbered item is kept because this is an inventory of a stamped revision, not a live description.
11. **The proposal lifecycle has four states**, set in `build_proposal`, `review_proposal` and
    `apply_proposal`: `proposed`, `accepted`, `rejected`, `applied`. The shared PLAN's vocabulary —
    draft, offline-valid, evaluated, approved, canary, active, retired, rolled-back,
    insufficient-evidence — is D20/D22/D23 work, and `read_proposal` rejects any file whose `v` is
    not `PROPOSAL_VERSION`, so the migration is explicit, not incidental.

## Duration coverage

**No duration fix has landed anywhere in this repository.** D01 checked this specifically so that
D05 would know whether to deduplicate, and this task re-derived it by reading every call site.
There is nothing for D05 to deduplicate; what follows is the map of what it will have to change.

Duration *is* measured. `proc_runner._result` computes `duration_s` for every process it starts
(`proc_runner.py:290`, rounded at `:304`), in the same dict as `outcome`, `terminal`, `timed_out`
and `rc`. The outcome vocabulary that distinguishes a timeout from a cancellation from a missing
executable is already there: `ok`, `failed`, `timeout`, `cancelled`, `missing-executable`,
`not-permitted`, `bad-workdir`, `start-failed` (`proc_runner.py:65`–`72`).

It dies at four specific boundaries:

1. **`kit_contract.provider_runner`'s `default_runner` returns `(rc, output)`**
   (`kit_contract.py:1559`–`1571`). It receives the full `proc_runner` result and discards the
   timing, the outcome and the timeout flag. `bin/claude_execute.py:544` and
   `bin/copilot_execute.py:244` both bind this runner, so **two of the four native drivers cannot
   record a duration without widening this shared contract.** This is the structural cause, and
   fixing it is a shared-module edit, not a per-driver one.
2. **`codex_execute.default_runner` returns `(rc, DispatchOutput, telemetry)`** where the third
   element is runtime model attestation, not the process result. Timing is dropped in the same
   function that measured it.
3. **`cursor_execute.default_runner` returns the whole result dict as its third element**, so
   `run_task` has `proc["duration_s"]` in hand — and passes only `proc_outcome=proc.get("outcome")`
   to `attempt_finished` (`cursor_execute.py:174`). Cursor is the cheapest of the four to fix and
   the one whose omission is purely a call-site omission.
4. **`attempt_history` has no duration field whatsoever.** Even where a duration *is* recorded, it
   cannot reach a report: `RECORD_FIELDS` has no slot for it, `observe` would raise on one, and
   `workflow_eval.history_records` projects through exactly that function.

Two writers do record it today, each from its own clock rather than `proc_runner`'s:

- `workflow_eval.Evaluation._dispatch` measures `time.monotonic()` around the dispatch and passes
  `duration_s=round(wall, 3)` on both its lifecycle path and its direct-ledger path
  (`workflow_eval.py:850`, `:859`), and keeps `wall_seconds` on the stage record.
- `copilot_ralph` passes `duration_s=round(clock() - tick_started, 3)` per tick
  (`copilot_ralph.py:383`).

Two places already coerce a missing duration to zero, which D05 must not preserve:

- `copilot_ralph._prior_state` sums `float(fin.get("duration_s") or 0.0)` across resumed history
  at `copilot_ralph.py:227`, immediately BELOW the line that does the same for `cost_usd` at
  `copilot_ralph.py:226`. Both coercions matter: an attempt nobody timed contributes zero to a
  total presented as elapsed time, and an attempt nobody priced contributes zero to one presented
  as cost.
- `workflow_eval` accumulates `rec["wall_seconds"] += stage.get("wall_seconds") or 0.0` (lines 931,
  943, 1170) from a field initialized to `0.0` rather than `None` (line 899). The resulting
  `wall_seconds` and `mean_wall_seconds` cannot distinguish a stage that took no time from one that
  was never measured.

Finally, nothing recovers a duration from a harness's own output. `cursor_adapter.parse_output`
accepts exactly one field as an observed model (a string `model`) and one of
`result`/`text`/`response`/`content` as result text; it reads no timing key from the CLI's JSON,
whatever that JSON contains.

For D05, the bases that must stay separate: the **process wall duration** measured by
`proc_runner`, the **decision latency** of a selection made before dispatch, and any
**model-reported** figure parsed out of an output. They are different facts measured by different
clocks, and the repository's existing rule for cost bases — `attempt_history.cost_totals` returns
the note "bases are separate facts and are never summed together" — is the precedent to follow.

## The unknown migration for historical records

Old records lack the new fields. They must load, and they must load as **unknown** — not zero, not
false, not inferred.

The repository already implements this rule three times, and the migration should be the fourth
instance of the same pattern rather than a new mechanism:

- **`attempt_history.observe` refuses to record a `None` as an observation.** Every record field is
  either observed or `None`, and the `observed` list names which. A field that was never written
  stays absent from `observed`, and `summarize` counts it.
- **`kit_contract.evidence_freshness` returns `unknown` with a reason** when the comparison cannot
  be made — literally `"accepted before upstream artifact versions were recorded"` for a task
  accepted before that field existed. This is the exact shape D04's migration needs: the reader
  distinguishes *no upstream recorded* from *upstream recorded and unchanged*, and its docstring
  states the rule — "Unknown is disclosed, never rounded either way".
- **`AttemptLedger.reconcile_open` closes a dead attempt as `OUTCOME_UNKNOWN`** with `cls="unknown"`
  and a note saying why no result exists, and `recovery_for("unknown")` is `stop`. An unknown
  external outcome is not a free retry, and the allowance it consumed stays consumed.

Two hard constraints govern how the migration may be implemented:

**`LEDGER_VERSION` must not be bumped for additive optional fields.** `AttemptLedger.events()`
skips and counts as corrupt every line whose `v` does not equal `LEDGER_VERSION`. Bumping the
constant would make every historical event in every user's store unreadable — and silently, as a
corruption count. Additive, optional, absent-means-unknown fields therefore keep
`polytropos.attempts/1`. The same reasoning applies to exactly two other constants, because those
are the two that gate a read: `EVAL_VERSION`, which `workflow_eval.list_runs` checks before
accepting an envelope (it notes and skips a mismatch), and `PROPOSAL_VERSION`, which
`read_proposal` raises on. It does **not** apply to `attempt_history.HISTORY_VERSION`, and saying
so matters because overstating a hazard misdirects D04 exactly as hiding one would. That constant
occurs three times in `bin/` — its definition at `attempt_history.py:34`, the `"schema"` stamp on
`summarize`'s output dict at `attempt_history.py:518`, and its row in
`release_gate.VERSION_SOURCES` — and nothing anywhere reads a persisted history file and checks
it. `attempt_history` writes nothing, so there is no store for a bump to render unreadable: it is
a stamp with no reader, and it carries no migration hazard today.

**Correction, D06, 2026-09-16.** The table row above said `EVAL_VERSION`, which contradicted this very rule. `list_runs` gates envelope reads on `EVAL_VERSION` (`workflow_eval.py:2445`), so stamping the manifest with it would force a future incompatible manifest shape to either bump `EVAL_VERSION` -- making every stored `results.json` unreadable, D04's documented trap -- or lie. D06 therefore added `MANIFEST_VERSION` on the referenced object, registered it in `release_gate.VERSION_SOURCES`, and regenerated `docs/RELEASE.md` through its generator. The row now says so.

Where a genuinely incompatible shape is needed,
the new version belongs on the *referenced object's* contract, not on the ledger line that points
at it — and that new constant must be added to `release_gate.VERSION_SOURCES`, or the release
report will not name it.

**The migration is read-time, never rewrite-time.** No backfill, no reconstruction from prose, no
backdating. A stored record is never hand-authored; capturing a still-existing source late is fine,
fabricating an evaporated one is not. An attempt recorded before decision references existed has no
decision reference and never acquires one.

## `workflow_eval` is pull-only, and what that limits

`bin/workflow_eval.py` owns the policy file lifecycle end to end: `build_proposal`,
`write_proposal`, `review_proposal`, `apply_proposal`, `rollback_policy`, `policy_report`, over the
`prefs` store (`routing-policy.json`, `routing-policy.history/`, `routing-policy.proposals/`,
`routing-policy.journal.jsonl`).

The file it writes says so in its own bytes. `apply_proposal` sets
`"consumption": "pull-only: no driver reads this file until wired on purpose"`
(`workflow_eval.py:1535`), and `policy_report` returns `"consumption": "pull-only"` (line 1592).

That claim is true at this revision, verified by reading rather than by trusting the string:
`prefs/routing-policy.json` is read only by `workflow_eval.read_policy` and `policy_base`. No
driver consumes it. `claude_execute`, `copilot_execute` and `cursor_execute` contain zero
occurrences of `routing_policy`, `codex_policy` or `_sibling`; `codex_execute` reaches routing
through `codex_policy` only, and `codex_policy` never reads the preference file.

Three limitations follow, and they bound what V1 can honestly claim:

- **Applying a proposal changes no runtime behavior.** `apply_proposal` versions a file, archives
  the previous version, journals the event, and that is the whole effect. Any statement that an
  applied policy is in force would be false.
- **Activation is a separate, explicit, versioned opt-in** — D23's work, gated on D07's profile,
  D06's manifests, D19's predeclared endpoint and D22's exact approval. An existing preference file
  must never become an executable policy bundle by being read differently.
- **Only Codex dispatches under a routing decision at all.** Even after activation, a policy that
  reaches only the Codex driver is measuring one harness. D18's arms and D24's report must say
  which harness an effect was observed on, and the absence of a routing seam on the other three is
  a fact about coverage, not a null result.

`apply_proposal` also already enforces two things later tasks should extend rather than replace: it
refuses a proposal whose `base` does not match the current `policy_base(prefs_dir)` — a
compare-and-swap on content identity — and `build_proposal` refuses evidence below
`repo_bench.MIN_EVIDENCE_TASKS`, from a single repeat, or drawn from tasks that already backed the
policy in force.

## The report projection

A reference is not usable until it can be read back, and in this repository reading back is a
distinct, read-only layer:

| Projection | Module | Input | Output |
| --- | --- | --- | --- |
| One record per attempt, unknowns counted | `attempt_history.join_kit` / `join_kits` / `summarize` / `render_markdown` | the ledger, `NOTES.md` outcome lines, Codex `role-use.jsonl` | the history card |
| The same, scoped to one evaluation run | `workflow_eval.history_records` | that run's own `attempts/` store | records plus a summary |
| Variant-level evaluation results | `workflow_eval.build_card` / `render_card_markdown` | the envelope | the evaluation card |
| Outcome-line evidence across kits | `bin/routing_scorecard.py` | `NOTES.md` grammar lines | the routing scorecard |
| Task acceptance staleness | `kit_contract.evidence_freshness` / `kit_freshness` | the ledger | per-task `fresh`/`stale`/`unknown` |

The rules a new reference must satisfy to appear in a report: add it to
`attempt_history.RECORD_FIELDS` (or `observe` raises), populate it only from what was actually
recorded, count its absence in `summarize`'s `unknown` block rather than defaulting it, and render
it last. **A projection never becomes a writer** — `attempt_history` writes nothing, and
`workflow_eval.history_records` reads a store it did not create.

One existing behavior worth preserving verbatim: `attempt_history` keeps **every** `outcome:` line
rather than the last one per task, because the scorecard's older reader kept only the last and a
failure followed by a passing rerun read as if the failure had never happened. `latest_state` is
computed beside the history, never instead of it.

## Vocabulary drift hazards (inventoried, not fixed)

None of these is D03's to repair. They are recorded because a later task that adds a reference near
one of them will otherwise widen it.

- **`kit_contract.parse_plan_routing` validates nothing against `routing_policy`.** It checks a
  PLAN.md `routing:` line against its own `PLAN_ROUTING_KEYS = ("policy", "preference", "profile")`
  (`kit_contract.py:835`), which are key *names*. The comment above it (line 831) says the values
  are `routing_policy`'s vocabulary, "checked by the driver at run time" — that is a claim about a
  driver, not about this function. The two vocabularies can drift and nothing here fails.
- **`workflow_eval.POLICIES` is `("pinned", "reserved", "adaptive")`; `routing_policy.POLICIES` is
  `("reserved", "adaptive")`.** This is not a bug: `route_stage` handles `pinned` by returning the
  pin before `routing_policy` is loaded at all (`workflow_eval.py:547`). It is a superset that must
  stay a deliberate one.
- **Cost bases differ between the two modules that carry them.**
  `attempt_history.COST_BASES` is `("billed", "credits", "estimated", "proxy", "model-reported")`;
  `workflow_eval.BASES` is `("model-reported", "estimated", "proxy", "credits", "unpriced")`.
  `billed` exists only in the first, `unpriced` only in the second.
- **`attempt_ledger.OPERATIONS` includes `tick`, which `kit_contract.OPERATION_CAPS` does not.**
  Ralph has no kit and no ladder; `AttemptLedger.usage` counts a `tick` against `max-dispatches`
  and `max-model-calls` anyway. The two tuples are deliberately not identical and the ledger's own
  comment says so.

## Handoffs

| Task | What this inventory hands it |
| --- | --- |
| D04 | The two signature changes that gate everything (`TaskRun.attempt_started`, `TaskRun.project`/`record_projected`), the four references and their owning events, the `**extra` asymmetry, and the `LEDGER_VERSION` constraint. |
| D05 | The four boundaries where duration dies, the two writers that already record it, the two zero-coercions to fix, the missing projection field, and the confirmation that **nothing has landed to deduplicate**. |
| D06 | The envelope's flat `holdout`, and `repo_bench` as the existing owner of content identities and the run store. |
| D09–D11 | That the ledger stores references and hashes, never payloads, bounded at 16 KiB. |
| D13 | That only Codex reaches `routing_policy`, through `codex_policy`. |
| D20, D22, D23 | The four-state proposal lifecycle in force, the content-identity compare-and-swap `apply_proposal` already performs, and the pull-only guarantee that must survive until activation is explicit. |
| D24 | The projection layer's boundaries and the never-sum-across-bases rule. |
| D28, D29 | `release_gate.VERSION_SOURCES` as the place a new contract version must be declared. |
