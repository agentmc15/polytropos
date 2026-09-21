# Decision and improvement — Release 1 handoff

This is the handoff for Release 1 of the decision and improvement work: what the branch actually
contains, which of it has been exercised and which of it has only been built, what an operator
still has to do, and what was deliberately left out.

**This document is a report, not authorization.** It grants nothing, activates nothing, moves no
capability row, promotes no candidate, and takes no release action. Reading it does not authorize a
live trial, a collection run, a training run, an install, a push or a merge. Where it names an act
that would close a gap, naming the act is not permission to take it — the standing rule in this
repository is that an authorization is something a person gives in their own words, and a planning
or reporting document is never one.

It is also not a record. Nothing here was captured by a running engine. Every figure below is
either read out of the tree at the moment you re-run the command beside it, or relayed from a
document another task already wrote and another test already keeps honest. Nothing was
reconstructed from prose.

## The accepted commit

| Fact | Value |
| --- | --- |
| Commit | `812a76e0f6caa712c15124a8a0ba4bd3872a4ca3` |
| Subject | feat(release): report conformance in three outcomes, and refuse a report that establishes nothing |
| Date | 2026-09-20 |
| Branch | `codex/decision-improvement-plan` |
| Position | 47 commits ahead of `main` (`8d1b7be`), **not merged and not pushed** |

Everything this document describes is a property of that commit on that branch. None of it is a
property of `main`, and no statement here describes a released or installed artifact. The kit's own
execution ledger is `.claude/kits/decision-improvement-v1/TASKS.md`; its working notes, including
every phase review this document relays, are `.claude/kits/decision-improvement-v1/NOTES.md`.

## How to read a claim here

Three words are used precisely, and they are not interchangeable.

- **mechanical** — the code exists, it is exercised by tests, and the tests construct their own
  inputs. A mechanical claim says a unit behaves as described. It says nothing about whether the
  mechanism helps, and nothing about whether any production path calls it.
- **live-ready** — nothing in this release is live-ready, and the section below says so in detail
  rather than leaving it to be inferred.
- **unknown** — nobody has run the thing. In `primitives/harness-capabilities.json`, `unknown`
  means **no**: `harness_adapter.requires` refuses an unrun row exactly as it refuses an absent
  one. A row becomes `supported` only when a person runs the client, records `verified_on` and
  `client_version` in the row, and commits that edit by hand.

A fourth word appears in the conformance report and is explained there: `unavailable` is a third
outcome, neither a pass nor a fail, meaning no evidence was produced because producing it needs
something this host does not have and must not acquire.

## What Release 1 ships

Eight phases, thirty-four tasks. The table is the inventory, not a quality claim; each row's
evidence is the test module beside it, and the kit's TASKS.md carries the per-task verify command
that was actually run.

| Task | Phase | What it delivers |
| --- | --- | --- |
| D01 | Baseline | reconciliation of the roadmap against the tree, and the ADR — `docs/DECISION-IMPROVEMENT-RECONCILIATION.md` |
| D02 | Baseline | frozen legacy goldens: each driver's existing decision path, pinned before anything was extracted |
| D03 | Baseline | the authority inventory — `docs/DECISION-IMPROVEMENT-AUTHORITY-INVENTORY.md` |
| D04 | Baseline | versioned decision/acceptance/admission provenance on the attempt ledger; absent old fields read `unknown` |
| D05 | Protected evaluation | duration coverage, with missing duration reported as unknown rather than zero |
| D06 | Protected evaluation | immutable grouped evaluation manifests and exposure history |
| D07 | Protected evaluation | protected-profile sentinels in `bin/exec_policy.py`; detecting a backend is not certifying one |
| D08 | Protected evaluation | the offline-only fence around the experiment surface |
| D09 | Contracts and policy | the strict decision contract — `bin/decision_contract.py` |
| D10 | Contracts and policy | value validation: no invalid input is normalised into validity |
| D11 | Contracts and policy | policy bundles and candidate proposals — `bin/decision_policy.py` |
| D12 | Contracts and policy | `rules` and `replay` — `bin/decision_provider.py`; replay incurs no new inference |
| D13 | Contracts and policy | current routing preserved as a named legacy bundle, with golden compatibility evidence |
| D14 | Recovery evidence | the read-only prediction-time join — `bin/decision_eval.py` |
| D15 | Recovery evidence | calibration reporting, with `insufficient-evidence` for thin or mismatched data |
| D16 | Recovery evidence | bounded context candidates — `bin/decision_context.py` |
| D17 | Recovery evidence | the context-repair policy: at most one approved repair, model and context never changed at once |
| D18 | Recovery evidence | the three-arm trial protocol (A/B/C) in `bin/workflow_eval.py` |
| D19 | Recovery evidence | predeclared outcomes, margins, ceilings and stopping rules |
| D20 | Promotion | the existing owner boundary: no second benchmark writer, no second ledger |
| D21 | Promotion | bounded, data-only candidate drafts — `bin/improvement_loop.py` |
| D22 | Promotion | exact approval bound to hashes and scope; a proposer cannot approve itself |
| D23 | Promotion | the protected activation gate, which refuses every transition to `canary` and `active` |
| D24 | Promotion | the policy evidence report, swept by `workflow_eval.assert_no_gain_claim` |
| D25 | Assessment | the reusable `assess-improvement` skill |
| D26 | Assessment | assessment fixtures, including the no-supported-intervention conclusion |
| D27 | Assessment | the whole-repository assessment — `docs/ASSESSMENTS/polytropos-decision-improvement-v1.md` |
| D31 | Training-data preparation | decision-time snapshots and the training example contract — `bin/training_data.py` |
| D32 | Training-data preparation | reviewed labels, eligibility, retention and revocation |
| D33 | Training-data preparation | grouped dataset splits and reproducible local exports |
| D34 | Training-data preparation | collection readiness and the operator runbook — `docs/TRAINING-DATA-READINESS.md` |
| D28 | V1 handoff | the Jev-free decision matrix, rendered into the generated block of `docs/RELEASE.md` |
| D29 | V1 handoff | the offline conformance report — `docs/DECISION-IMPROVEMENT-CONFORMANCE.md` |
| D30 | V1 handoff | this document |

The suite that covers them is `tests/`; the count is not quoted here, because a count in a handoff
rots. Measure it with `python3 -m unittest discover -s tests` from the repository root.

### The feature and support matrix

The matrix itself is generated, not restated. It is the decision section of the generated block in
`docs/RELEASE.md`, and it prints from:

    python3 bin/release_gate.py decision

Every cell in it is read from the constant that owns the word — `decision_policy.SELECTION_MODES`
and `DEFERRED_MODES`, `decision_provider.PROVIDER_MODES`, `workflow_eval.CONFINED_DISPATCH_WIRED`
and `RUNTIME_REASONS`, and the capability registry — never typed into the renderer. Its shape is
pinned by `test_decision_release_matrix.JevFreeMatrixTests`.

Four properties of it are worth stating in the handoff, because a reader who only skims the table
can get each of them wrong.

- **No cell carries a performance figure.** No gain, no ratio, no latency, no cost. No live trial
  has run under any of this work, and `gain_observed` is `null` in D27's assessment. A mechanism
  release is valid without one — a well-run trial that retains the baseline is a valid outcome —
  and this release makes no performance claim at all.
- **`canary` and `active` are unavailable on every harness**, and the refusal is derived rather
  than written down: `workflow_eval.CONFINED_DISPATCH_WIRED` is `False`, so D23's
  `activation_decision` refuses every transition and `runtime_activation` resolves every run to
  legacy. There is no partially available canary.
- **Two facts about confinement are linked and never merged.** `claude-code.confined_dispatch` is a
  **measured host limitation** — dated 2026-09-06, on macOS, and the only such row in the registry.
  `CONFINED_DISPATCH_WIRED` is a **design decision**, recorded once and reaching all five harnesses.
  A different host could change the first. Only a change in this repository changes the second.
- **Two facts about Cursor are linked and never merged.** Cursor's *adaptive profile* is
  `unsupported` pending independent proof. Cursor's *current CLI implementation* is present and
  verified — six dated `verified: supported` rows against a named client version — and nothing in
  this release retires it, reimplements it or reports it as absent. Concurrency is likewise intact:
  what is deferred is new adaptive extension, never the implementation that already exists.

### What is mechanical, and what is not live-ready

Everything in the table above is mechanical. Nothing in it is live-ready, and these are the reasons:

- No vendor client has been run by any test, verify command or gate. Stub conformance is what this
  host can produce.
- No protected profile has been certified. `exec_policy.certify_profile` certifies nothing without
  a sentinel report, and no sentinel report exists, because producing one means spawning sandboxed
  processes and binding a loopback port. Detecting a sandbox backend on this host is a statement
  about a binary being present, never about what it denied.
- No confining, ledgered dispatch path exists. Every check of a *running* state in this release is
  therefore a check of a refusal.
- No trial has been declared by an operator, so no trial plan is complete. Until an operator
  supplies the endpoint, the practical margin, the allowed quality regression, the resource
  ceilings and the stopping rules, the plan is incomplete for live promotion and the system says so
  by name (`trial-plan-incomplete`).
- No approval has bound anything, because there is nothing evaluated to bind.

## Conformance

D29 ran the offline conformance report at this checkout: **17 pass, 0 fail, 6 unavailable across 23
checks**, covering all twelve concerns Release 1 names. The report, the reason for every
unavailable check and the act that would produce its missing evidence are in
`docs/DECISION-IMPROVEMENT-CONFORMANCE.md`; the registry and the runners are beside
`test_decision_release_matrix.JevFreeConformanceTests`, which asserts that the document and the run
agree on ids, areas, outcomes and counts.

Two structural properties of that report matter here and are enforced rather than described. A
report in which nothing passed is **refused** rather than returned, because a registry of checks
that may each answer `unavailable` is satisfiable by one that runs nothing at all and reads
identically. And a check whose runner raises is a **fail**, never an honest gap — a broken probe
cannot wear the same word as something nobody could test.

The six checks that produced no evidence:

| Check | What is missing |
| --- | --- |
| `contracts.installed-client-conformance` | whether the shared contracts hold against an installed vendor client; nothing here runs one |
| `caps.os-enforcement-sentinels` | whether a protected profile actually denies the five things it must deny on this host |
| `caps.confining-ledgered-dispatch` | whether a confining, ledgered dispatch path exists. It does not |
| `rollback.live-rollback-of-a-running-pointer` | whether rolling back moves a run that was actually following a bundle |
| `private-store.install-time-copy` | whether an install leaves a legacy in-tree store behind in the installed copy |
| `docs.site-build-strict` | whether `mkdocs build --strict` succeeds; that toolchain is hash-locked and installed only in CI |

**Conformance is established for this checkout only** — one platform, one Python, no installed copy
of the plugin. A different platform, a different interpreter or an installed copy is a different
subject, and nothing here has been run against one.

## Capability posture

The capability census on 2026-09-20 was **23 supported, 3 unsupported, 36 unknown**. That is a
dated observation and it is asserted by nothing, deliberately: a number that rots inside a gate is
a gate nobody can keep green honestly. Re-derive it with `python3 bin/harness_adapter.py`.

The direction of the last change is worth recording. The unknown count went **up** by five when
D28 added the `adaptive_decisions` rows — one per harness, every one `verified: unknown` with
`verified_on: null`. Supported and unsupported did not move. That is the correct direction: a new
capability nobody has run arrives as `unknown`, and the way to reduce the count is to run something
and record it, never to assert it.

That same five-row change is why D27's assessment quotes different digits. Its capability tallies
(`13 of 19` cursor rows unknown, `4 of 11` for Claude, `31 of 57` overall) were exactly right when
counted, and it pins the revision it counted them at in `assessed_revision` and labels them
"counted at this revision". D28 then added one `adaptive_decisions` row to every harness, so the
current tree reads 14 of 20, 5 of 12 and 36 of 62 — the same `+1` per harness, five in total. The
assessment is a dated artifact and is deliberately NOT being edited to match a later tree; its
qualitative finding (cursor carries proportionally more unknown rows than Claude) still holds.
Read its numbers against the revision it names, not against this one.

## Training data: shipped setup, no authorized collection, no training

These are three different things and the distinction is the one most easily blurred.

**What shipped** is the code in `bin/training_data.py`: decision-time snapshots, the cause
taxonomy, reviewed labels, eligibility and retention, revocation, grouped dataset splits,
reproducible local export and the readiness report. Its runbook is
`docs/TRAINING-DATA-READINESS.md`. It is mechanical, and its mechanics are covered by
`test_training_data.SnapshotTests`, `test_training_data.LabelEligibilityTests`,
`test_training_data.DatasetExportTests` and `test_training_data.ReadinessTests`.

**What was not authorized** is collection. No collection scope has been declared and no eligible
run has been collected from.

**What has not happened** is training. There is no trainer in this repository, nothing downloads,
uploads, fine-tunes or evaluates a model, and no checkpoint exists.

### Capture configuration, as it ships

| Fact | Value | What it means on its own |
| --- | --- | --- |
| `training_data.COLLECTION_ENABLED` | `False` | the switch is shut, and every entry point re-derives it at call time |
| `training_data.CAPTURE_WIRED` | `False` | a statement that no production path calls the hook — a different fact from the switch |
| a declared scope's `eligibility` | defaults to `"unknown"` | unknown use rights cannot persist a byte; only `"approved"` may |
| `build_dataset` | requires an explicit `store_dir` | no export has a default location to fall into |

Two of those are runtime gates: `COLLECTION_ENABLED` and the eligibility default are read at call
time and fail closed. `CAPTURE_WIRED` is **not branched on in production at all** — its one
branching use is the readiness gate's own ternary. What actually keeps the hook uncalled is a
structural fact, not a constant: **there is no call site anywhere in the tree**, and
`test_training_data.SnapshotTests.test_no_production_path_calls_the_capture_hook` is what keeps it
that way. So: two runtime gates plus one externally verified structural fact — not "three locks".

It follows that **"zero examples collected" is the absence of a call site.** It is not a gate met
and it is not a privacy achievement. Likewise `| training/ | present |` in the packaging table
means the store's root-anchored ignore rule is present — never that a record, a dataset or an
export manifest exists. Five `release_gate.VERSION_SOURCES` rows are training schema versions with
zero stored objects behind them.

### Why the readiness gates are not the evidence

`python3 bin/training_data.py readiness` prints eleven gates, and it is tempting to read their
tally as proof that nothing is ready to train. **Do not.** The tally is a property of the input
shape, not of the mechanism. The standing report — no records, an empty store — reads 0 met, 4
unmet, 7 unknown. The *same* report over fixture records reads more gates met after a
capture-and-adjudicate walk, and more still after an export, because most of these gates are
answers about the material they were handed. A gate that reads `met` over fixture records is a gate
the fixtures opened.

What denies readiness unconditionally is `training_data.readiness_codes()` — ten codes that ride on
every report shape, including the one with eight gates met:

    access-not-enforced
    checkpoint-link-is-a-forward-declaration
    digest-identifies-content-not-provenance
    exposure-not-recorded-in-the-eval-store
    label-agreement-counted-not-calibrated
    no-transfer-and-no-training-performed
    readiness-is-a-report-not-an-authorization
    sampling-bias-not-estimable
    synthetic-fixtures-are-not-readiness
    training-sufficiency-not-established

No branch can discharge one of them. Cite the codes; never cite the tally.

### What redaction covers, and what it does not

`training_data.REDACTED_FIELDS` names **two** fields that go through `bin/redact.py`: an input
entry's text, and a revocation's reason. `training_data.NOT_REDACTED_FIELDS` names **ten** that do
not, and the first two of those are the question's wording and its rubric — which are copied
verbatim into `payload.jsonl`, the model's input file, because `QuestionSpec.digest()` is taken
over the complete wording and a redacted copy would no longer be identified by the digest stored
beside it.

A credential shape typed into a question wording is therefore stored and exported as typed, while
`record["redaction"]["redactions"]` reads `{}` for it. That gap is not described, it is
demonstrated:
`test_training_data.SnapshotTests.test_a_credential_shape_in_the_question_wording_is_not_redacted_and_the_record_says_so`
drives a synthetic credential shape through the sanctioned API, asserts it reaches the payload
line, and names the field in `not_redacted`. Findings ride on every record by **kind and count**,
never by value.

**No sentence here says that no secret can get through.** Shape-matching cannot prove absence — a
password that looks like a word, a customer name or an address has no shape and is not caught, and
that is true even of the two fields redaction does reach. The option that was considered and not
taken is named rather than hidden: refusing a credential shape at capture time.

### Revocation reach

Read from `training_data.REVOCATION_REACH`, never restated from memory:

| Downstream artifact | Reach |
| --- | --- |
| `export-manifest` | `invalidated` |
| `derived-dataset` | `invalidated` |
| `readiness-report` | `invalidated` |
| `trained-checkpoint` | `identified-only` |

**Revocation removes nothing from a model.** `identified-only` means the checkpoint is named. Weights
are not unlearned, exported copies are not recalled, downstream artifacts are not rebuilt, and byte
erasure is not proven — deleting a file is not an erasure proof in a tree that is distributed,
cached and often backed up. All four of those denials ride on every tombstone unconditionally.

## Rollback and migration

The authority for this is `release_gate.MIGRATION_NOTES`, rendered into the generated block of
`docs/RELEASE.md` by `python3 bin/release_gate.py build` and resolved by
`python3 bin/release_gate.py check`. The four surfaces this release touches:

| Surface | Forward | Back |
| --- | --- | --- |
| Runtime decision activation (`workflow_eval.POLICY_ACTIVATION` generations under the `prefs` store) | nothing to do and nothing that could be done: no pointer exists, an absent pointer means legacy, and `activation_decision` refuses every transition while `CONFINED_DISPATCH_WIRED` is `False` | `python3 bin/workflow_eval.py activation` reports what is in force; `python3 bin/workflow_eval.py rollback` appends a generation, deletes nothing, and every future run reads legacy whatever fallback it named |
| Routing policy (`workflow_eval.POLICY_FILE` under the `prefs` store) | `python3 bin/workflow_eval.py propose`, then `review`, then `apply`; every version kept | `python3 bin/workflow_eval.py rollback --version N`; the replaced version is kept too |
| Training-data collection | declare an approved scope, switch it on at the call site, write the caller, then record the export's exposure in the evaluation store yourself | set both constants back to `False` and remove the call site; nothing is deleted and no record is rewritten. `python3 bin/runtime_data.py forget --store training` lists before it deletes and deletes only with `--apply` |
| Runtime stores (`memory`, `telemetry`, `journal`, `benchruns`, `prefs`, `trends`, `attempts`, `evals`, `training`) | `python3 bin/runtime_data.py where`; an in-tree store keeps being used; `migrate --store NAME --apply` copies it out | delete the copy; the original was never touched |

Four properties of rollback hold across all of them and are the reason this section is short.

- **A rollback appends, it never deletes.** Two rollbacks append generations 1 and 2 and generation
  1 stays byte-identical. A swap that lost a race writes nothing rather than half of something.
- **An absent pointer is legacy, and that is not an error.** No store, no directory and no
  generation all answer legacy with reason `no-pointer`. None raises and none mints a pin.
- **A store is copied, never relocated.** An existing in-tree store keeps being used before and
  after a migration; the copy is 0600, the original stays exactly where it was, and a second run
  reports a conflict rather than overwriting.
- **A rollback contacts nothing.** It names a fallback `decision_policy.resolve_bundle` already
  chose. It never resets a user workspace, erases evidence, reverses an external effect or refunds
  a call.

The mechanics above are proven on a rolled-back pointer in a temporary store, by
`test_decision_activation.ProtectedActivationGateTests` and the `rollback.*` conformance checks.
That establishes the store's behaviour. It says nothing about a live cohort, a run in flight or an
external effect already taken — which is exactly why
`rollback.live-rollback-of-a-running-pointer` is recorded as unavailable rather than as a pass.

## Remaining operator inputs

These are the things no code in this repository can do for whoever runs it.

1. **Record the export's exposure in the evaluation store.** This is the substantive one, and it is
   asymmetric, so it is stated asymmetrically. The **training** side is protected: `build_dataset`
   reads `workflow_eval`'s exposure log and emits `item-exposed-elsewhere` and `item-retired`. The
   **evaluation** side — the next held-out draw — has nothing to read, because nobody wrote the
   entry. `training_data.py` does not write that log, and should not: the evals store has exactly
   one writer, and a second one would break the rule that keeps every store honest. Every export
   manifest therefore carries `exposure-not-recorded-in-the-eval-store` and names the remedy, and
   `readiness_report(...)` prints the drawn items with no entry under
   `exposure.items_with_no_exposure_entry`. **This is an open operator obligation, not a closed
   gate.** Skip it and the next held-out draw may silently overlap material a training export
   already spent — which is where the money goes, and the one direction nothing here closes.
2. **Declare the trial inputs.** Primary endpoint, practical margin, allowed quality regression,
   resource ceilings, stopping and interim-look rules, and the independent evaluation. Sample size
   comes from pilot variation and a useful effect size, never from a universal minimum.
3. **Certify a protected profile, if one is ever wanted.** Run `exec_policy.run_sentinels` on a
   named profile and keep the report. A skipped, unavailable, inconclusive or leaked sentinel
   certifies nothing.
4. **Verify an installed client, if a row is ever to move.** Run that harness's documented smoke on
   your own account, then record `verified_on` and `client_version` in the registry row by hand. A
   failing smoke sets `verified` to `unsupported` with the date; it never deletes the row.
5. **Prune after a plugin update.** An install copies the whole directory and does not consult
   `.gitignore`, so a legacy in-tree store would be copied with it. The runbook is in
   `docs/PRIVACY.md` and it is manual by design — nothing in this repository writes `~/.claude`.
6. **Choose a collection target, if collection is ever turned on.** No minimum sample count is
   asserted anywhere and none is invented. `training_data.MAX_DATASET_EXAMPLES` is a **ceiling**
   that refuses past itself rather than trimming; there is no floor. A target comes from a pilot
   and learning curves on a separate development validation split, and nobody has run one.

## Authorized-but-unrun checks

`release_gate.PREPARED_COMMANDS` holds bounded live commands that are written down here and run by
nobody. Each spends the operator's own credits and contacts a vendor with their own credentials, so
each stays unrun until a person runs it themselves:

- the Cursor identity and read-only smoke, printed by `python3 bin/harness_select.py doctor`;
- each driver's argv, via `--dry-run`, which spawns nothing, followed by one authorised live `run`
  on a kit the operator owns;
- the bounded workflow evaluation, via `python3 bin/workflow_eval.py plan` and then the same flags
  with `run --live --max-usd N --max-dispatches N`;
- the bounded benchmark, via `python3 bin/repo_bench.py plan` and then `run --live --max-usd N`.

The offline chain, by contrast, is meant to be run and spends nothing:

    python3 -m unittest discover -s tests
    python3 bin/docs_build.py check
    python3 bin/copilot_docs.py check
    python3 bin/sync_codex_surfaces.py check
    python3 bin/release_gate.py check
    python3 bin/release_gate.py decision

## The named-unfinished register

Four items were named, adjudicated and deliberately left undone. They are not defects discovered
late; each is a place where finishing correctly needs something that does not exist yet.

1. **`attach_action` has no `outcome_basis`.** An action record accepts an `ACTION_OUTCOMES` member
   directly, so it cannot say whether its outcome was derived from the attempt result or declared
   by its caller. Rather than export a declared field as a measured one, **no action outcome is
   exported at all**: the only target the exporter writes is the adjudicated cause. Closing this
   needs an explicit basis field on the action record first. `PAYLOAD_FIELDS` and `AUDIT_FIELDS`
   are pinned so a later outcome field fails a test rather than shipping as a measurement.
2. **The operator's exposure step** — item 1 of the previous section. Open by design.
3. **No collection target**, because no pilot has run. See item 6 of the previous section.
4. **The `operational_class` basis pair.** `training_data.OPERATIONAL_CLASS_BASES` records where a
   snapshot's operational class came from, because the value alone cannot say. The default is
   `declared` — the **weaker** value — so an unstated provenance can never pass as a ledger
   reading. Without the basis, omitting a single argument turned a failed attempt into an exported
   `no-failure` negative example. The pair is present; what is unfinished is that nothing
   cross-checks a declared class against the `attempt_ref` the record carries.

Beside those, three disclosed gaps that are narrower but real:

- **An agent's verdict may file an adjudication but cannot by itself establish a review-only
  cause.** Two adjacent gaps were named and not taken: `ambiguity`'s top-level check still gates on
  any review weight, and `_reviewer` still admits `review-verdict` as the filing reviewer. Both
  facts ride on the record.
- **The question wording and rubric reach the model's input file unredacted**, as described above.
- **A readiness report generated from real material would be a separate artifact**, held by whoever
  generated it. Nothing in this repository holds one, and a revocation would mark such a report
  `invalidated` — a statement about it, never an action on it.

### Limitations inherited from D28 and D29

- The Jev-free AST scan is **per-file over two named lists, and it is not transitive**. A module
  reached only through `_sibling()` at call time is not walked unless it is listed. The behavioural
  half covers the transitive case only along the paths it actually exercises: startup, `rules`,
  `replay` and rollback.
- **The OS column is empty for codex, copilot, cursor and stub.** That is the honest state. Claude
  Code's macOS evidence was deliberately not allowed to read across to another harness.
- **Baseline conformance reuses D02's frozen goldens** rather than adding per-adapter tests. The
  new work is the per-adapter separation and the id resolution, not a second set of goldens.
- **No command prints the conformance table.** Reproducing it means running
  `test_decision_release_matrix.JevFreeConformanceTests`.
- The conformance run's network-refusal sweep **excludes two checks** that legitimately need the
  test loader and read-only git: `contracts.stub-conformance-ids-resolve` and
  `package.private-stores-are-not-packaged`.
- A guard whose only enforcement is a rendered document is not enforced. That was found by
  mutation — flipping `CONFINED_DISPATCH_WIRED` to `True` in a copy of the tree originally moved no
  check at all, and only the generated release block noticed, because it renders the constant. The
  check `fallback.a-running-state-refuses` exists because of that finding, and it is the reason to
  distrust any other claim whose enforcement turns out to be a document.

One gap D29 left to this task is now closed: `release_gate.CHECKLIST` did not cite the conformance
report, so `python3 bin/release_gate.py check` pointed no reader at it. It cites both that report
and this handoff now.

## Deferred, with entry gates

Everything below is **deferred**. None of it is queued, scheduled, implied or promised, and the
source roadmap never authorizes Release 2. Each item carries an **entry gate** — a condition that
must hold before it may start — rather than a position in a queue. An unmet gate is not a delay; it
is the reason the work is not being done.

| Deferred work | Where it is specified | Entry gate |
| --- | --- | --- |
| **O01, O02** — optional current-model shadow advice | `tasks/kits/decision-improvement/OPTIONAL-TASKS.md`, both `pending` | the user selects the extension, **and** a currently documented transport can be shown to enforce tool-free mode. If none can, the honest answer is `unsupported` and rules/replay continue |
| **O03, O04** — empirical calibration and its release surface | the same file, both `pending` | O02 first, **and** a target with defensible labels, a separate fitting partition and held-out validation. Sparse or mismatched evidence is `insufficient-evidence`, not a weaker fit |
| **R08 families** — workflow/model/effort; optional roles; context strategy; skill and lesson applicability | the R08 table in the same file | **the first trial has evidence.** One family at a time, each as its own bounded kit with its own counterexample, ablation and rollback. The interface permitting all four is not a reason to implement all four |
| **Shadow and calibration as a runtime mode** | D23's gate and `decision_policy.DEFERRED_MODES` | a confining, ledgered dispatch path exists and `CONFINED_DISPATCH_WIRED` is flipped with its own evidence — plus a certified protected profile, a current grouped manifest, a complete trial plan and an exact approval. All five, not four |
| **Concurrency extensions** | `primitives/harness-capabilities.json` | independent proof per harness. The existing concurrency implementation is intact and is not in scope; only new extension is deferred |
| **Cursor adaptive profile** | the adaptive table in the generated block of `docs/RELEASE.md` | independent proof that a Cursor run can take a decision bundle in a running state. Cursor's current CLI implementation is present and verified and is not in scope |
| **J01, J02, J03, J04** — the optional Jev provider, its fixed-policy comparison, its scoped adoption and its release evidence | `.claude/kits/decision-improvement-v2/TASKS.md`, all four `pending` | **explicit later human authorization covering access, data, spending, scope and activation.** That kit's own first line calls itself a handoff stop and not a mutable authorization token; V1's admission, protected profile, partition, acceptance and approval gates stay mandatory |
| **M01** — meta-improvement research | `tasks/kits/recursive-improvement/PLAN.md` and its TASKS.md | **the fixed procedure repeatedly produces validated transferable gains.** Separately selected research, independent of Jev, and never an automatic continuation of V1 |

Three things that are **not** deferred, because they were never in scope and never removed:
existing concurrency, Cursor's shipped CLI implementation, and the four drivers' native loops. All
three are unchanged by this release.

## What this document is not

- It is **not authorization**. It authorizes no live trial, no collection, no training, no install,
  no activation, no publish, no push and no merge.
- It takes **no release action**. It moves no capability row, mints no pointer, writes no store and
  changes no default. `unknown` in the registry means no, before and after reading it.
- It is **not evidence**. Nothing here was captured by a running engine. Where a fact has evidence,
  the evidence is the command or the test named beside it, and the fact should be re-derived rather
  than quoted from here.
- It makes **no performance claim**. No trial has run under any of this work. The whole-document
  sweep `workflow_eval.assert_no_gain_claim` is deliberately not applied to this file: one of its
  token spellings is a word in the name of the work itself, so the sweep would refuse an honest
  document. That is a disclosed limitation of a token match, not an exemption widened to fit.

## How to check this document

The declared task check is a text scan and is worth exactly what a text scan is worth. The
enforcement is `test_decision_release_matrix.V1HandoffTests`, which asserts this document's claims
against the tree it describes: every file path, command and test id it names must resolve; the
constants it quotes must still hold those values; the conformance counts and the six unavailable
checks must match what `docs/DECISION-IMPROVEMENT-CONFORMANCE.md` states; the readiness codes must
be the ten the module emits; the redaction scope must be the module's; the task inventory must be
the kit's; and every deferred item must still be recorded `pending` by its own kit.

    PYTHONPATH=tests python3 -m unittest test_decision_release_matrix.V1HandoffTests

That class is why a claim here cannot rot silently. It is not why a claim here is true.
