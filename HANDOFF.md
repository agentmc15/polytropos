# Handoff — roadmap implementation, steps 01–17

**As of 2026-09-07.** Steps 01–15 are committed as a single change set on top of `fb40925`:
66 files modified, 17 added, +5,485 / −1,860 lines. Full suite green: **3,727 tests, OK
(2 skipped)**, ~3 minutes.

They landed as one commit rather than fourteen. Splitting them after the fact would have meant
fourteen intermediate states nobody ever ran the suite against, and a bisect that lands inside a
half-migrated driver is worse than one that lands on a green boundary.

Source of work: `/Users/michaelcave/Downloads/polytropos-master-implementation-roadmap.md` — an
outside audit consolidated into 26 ordered implementation steps.

**Committed on top of `dc67555` on 2026-09-12** as `097b84e`, then the commit rule below as
its own commit, each with the full suite green and both doc generators' `check` clean first:

- `primitives/harness-capabilities.json` — three codex rows for API primitives a circulated
  "graph engineering" note leans on (`async_tools`, `mid_turn_steering`, `effort_per_turn`),
  all `product=unknown` / `implemented=unsupported` / `verified=unknown`, so steps 19 and 24
  cannot assume them. The copilot `tool_pin` note was corrected: it still said review carries a
  full grant, which step 06 made false.
- `SECURITY.md` — new section "Where the approval line sits" naming the reversible /
  consequential / irreversible lanes against the flags that enforce them. Also corrected the
  "Role names are not permissions" bullet, which still claimed Claude and Copilot review carry a
  blanket grant; both default to `restricted` since step 06.
- `HANDOFF.md` — the step-24 amendment below.

The note's "operator block" was deliberately **not** brought into the plugin: it is per-user
model tuning, and three of its lines contradict repo invariants (skip tests on small changes;
user instructions outrank rule files; delegate in parallel by default).

---

## Where things stand

**Steps 01–17 are done.** That is all of Phase A (input/artifact/acceptance boundaries), all of
Phase B (the execution boundary and the P0/P1 security remediation), and the first three steps
of Phase C (the shared runtime). Steps 16 and 17 landed on 2026-09-12 on branch
`harden/roadmap-steps-16-26`, one commit each.

| Step | What it closed |
|---|---|
| 01 | Acceptance depends on a typed JSONL ledger, not prose; fails closed on absent/malformed/conflicting verdicts |
| 02 | Benchmark patch, reference-test, and artifact filesystem escapes |
| 03 | Git metadata parsing; "read-only" git verbs that weren't |
| 04 | Journal commands rendered as literal argv, not shell strings |
| 05 | OS execution boundary for verify commands (`bin/exec_policy.py`, macOS Seatbelt) |
| 06 | Native role permissions preserved through dispatch |
| 07 | Dispatch success separated from dependency readiness |
| 08 | Pre-dispatch admission for every consuming operation |
| 09 | Completion bound to current, task-appropriate evidence |
| 10 | One path-containment helper (`bin/safe_paths.py`); no check-then-use races |
| 11 | Ownership-aware installs; stale plans fail safe; rollback preserves concurrent edits |
| 12 | Subprocess lifetime/output/env/cwd bounded (`bin/proc_runner.py`) |
| 13 | Private-data scope, redaction, isolated summaries, memory provenance |
| 14 | Build supply chain pinned; deploy credentials scoped; unsafe link schemes rejected |
| 15 | One kit contract (`bin/kit_contract.py`) + adapter seam + capability registry |
| 16 | Durable attempts (`bin/attempt_ledger.py`): recorded before/after every dispatch, resume without replay, budget carried across runs, failure classes, real progress detection, task claims, fresh-read projection |
| 17 | Cross-harness evidence (`bin/attempt_history.py` + `bin/model_registry.py`): one record per attempt over ledger + NOTES.md + role-use, unknowns kept, history never collapsed, failed consults keep lineage, cost per basis; reviews recorded on all three drivers; concrete ids resolve to tiers; telemetry `attempts` source |

### New modules, and what each is the *one place* for

- `bin/safe_paths.py` — whether a path is safe to write, read, or delete. Directory-relative,
  `O_NOFOLLOW`, refuses rather than falling back.
- `bin/exec_policy.py` — the OS execution boundary for verify commands.
- `bin/proc_runner.py` — starting an external process: wall clock, output ceiling, validated
  cwd, own process group, named outcome for every failure mode.
- `bin/redact.py` — what may not leave the machine in plain text.
- `bin/runtime_data.py` — where personal stores live (outside the plugin tree).
- `bin/kit_contract.py` — parsing, readiness, budget admission, outcome vocabulary.
- `bin/harness_adapter.py` + `primitives/harness-capabilities.json` — what a host can actually
  do, with `unknown` as a first-class answer.
- `bin/attempt_ledger.py` — what a run did, recorded before and after it did it, outside the
  tree. Claims, failure classes, normalized progress signatures, bounded retry context. The
  drivers reach it only through `kit_contract.TaskRun` / `start_task_lifecycle` /
  `reconcile_task` / `finish_task_projection` / `record_role_dispatch`; Ralph reaches it
  directly.
- `bin/model_registry.py` — which harness knows a model id and what tier it sits in there.
  Reads ids and tiers from the three pricing files, never a price; refuses to guess between
  harnesses that disagree. `routing_scorecard.tier_for` and `bench_routing` resolve through it.
- `bin/attempt_history.py` — one record per attempt over the ledger, `NOTES.md` outcome lines
  and Codex `role-use.jsonl`; unknowns kept and counted; latest state a separate projection;
  lineage including failed consults; cost per basis. Captured daily as telemetry's `attempts`
  source.

---

## Next: step 18 — validate the execution DAG and centralize sequential readiness

`kit_contract.select_task` already holds the one readiness rule (step 07/15). Step 18 adds a
pure DAG validator (duplicate ids, missing dependencies, cycles, self-dependencies, invalid
transitions) that runs BEFORE any dispatch or mutation, a ready-frontier selector for a diamond
DAG, and actionable diagnostics for an invalid graph. It is explicitly NOT parallel dispatch;
that is step 24. The three drivers' `cmd_run` call `select_task` from the same place, so the
validator slots in beside it.

Remaining after that: **19–24** routing / roles / graph context / skills / the Cursor adapter /
scheduling, **25–26** evaluation and the release matrix.

### Step 17's own deliberate limits

- **`billed` cost is never populated by the history.** Pricing a Claude session needs its
  transcript, which stays `routing_scorecard --history`'s job through `session:` lines. The
  history carries what the records themselves held: Copilot `- budget:` estimates and Ralph
  ticks (`estimated`, or `model-reported` when the model wrote the number). Codex subscription
  proxies appear in no per-attempt record yet, so they are absent, not zero.
- **An infrastructure-class dispatch failure still writes `result=blocked`** to the outcome
  line; the class rides beside it (`- failure-class:`) and in the ledger, and the history's
  `failure_classes` counts it. The scorecard's `failure=` vocabulary was left alone: adding a
  value the reader drops would be a line the reader has to ignore.
- **A chain's `attempts` mixes granularities**: ledger records count one each, a `NOTES.md`
  line without ledger twins counts its own `attempts=`. Stated in the field's docstring.
- **The scorecard's Claude-oriented per-tier stats now count a Codex `frontier` pass under
  `frontier`** because the tier word is the same; `mid`/`strong`/`cheap` still fall outside
  `LIVE_TIER_ORDER` with the existing note. Per-harness tier stats live in the history card,
  not the scorecard.
- **`--demo --alarm` changed meaning deliberately**: `driver-blind` now HAS evidence (its
  concrete id resolves) and a new `pin-unknown` kit carries the no-evidence path. The test says
  so in a comment.

### Step 16's own deliberate limits

- A resume **restarts the ladder at the task's pinned model**, not at the rung the dead run had
  reached. The retry context tells the model what rungs were tried; the driver does not skip them.
- Automatic task selection picks `pending` tasks, so **resuming an `in-progress` task means
  naming it** (`--task E1`). The status says which one.
- Copilot and Codex have no precheck, so their resume never has to distinguish a tautological
  pass; Claude's does, from the precheck the first run recorded in the ledger.
- The claim uses the pid: a recycled pid reads as alive and the run refuses. `--break-claim` is
  the deliberate way past it, recorded as such.

---

## Roadmap amendments recorded here

The roadmap file lives outside the repo and is the user's document; amendments agreed in a
session are recorded here so the implementer of the affected step sees them without depending
on that file having been edited. Paste-ready text for the roadmap is in each entry.

### Step 24 — bound the integration step by the model's own long-context threshold

Agreed 2026-09-11, from reading a circulated engineering note on running agents as a graph:
its one idea polytropos had as principle but not as data was "workers write files, the root
reads a manifest, because the merging root hits the long-context cliff first." Add to step 24's
implementation prompt:

~~~text
The central integration step reads a manifest, not the corpus: artifact paths, verdicts, and
bounded diagnostics, never worker transcripts or evidence dumps. Size that manifest under the
long-context threshold of the model dispatched to integrate, read at run time from the
integrating harness's own pricing file under that file's own field name:
`long_context.threshold_input_tokens` in data/pricing.codex.json,
`long_context.threshold_tokens` in data/pricing.copilot.json, and `context_window` in
data/pricing.json, which carries no separate long-context tier. Do not introduce a shared
schema across the three files to do this; they never merge. Estimate the manifest's size with
the repo's one estimator (`EST_CHARS_PER_TOKEN` in bin/context_weight.py), label the figure
est., and do not add a second estimator. When the model carries no threshold, the manifest is
unbounded and the run's report says so rather than assuming one.

Test a manifest that exceeds the threshold (the run refuses, or trims with a recorded note;
never silent truncation), a model with no threshold, and that no worker output reaches the
integrator except through the manifest.
~~~

Not added to step 16: its "bounded diagnostics" are verifier output sized for the next attempt's
prompt, orders of magnitude below any long-context threshold, so that bound belongs to the
threshold's own scale, not this one.

---

## Traps this work hit — read before editing

These cost real time to discover. All are still live.

1. **Generated doc mirrors fail the suite on drift.** `README.md`, `SECURITY.md`, `docs/*.md`
   and every `SKILL.md` feed generators. After editing any of them run **both**:
   `python3 bin/copilot_docs.py build` and `python3 bin/docs_build.py build`. Drift here caught
   me twice. (Measured 2026-09-11: a `SECURITY.md`-only edit rebuilt both mirrors byte-identical,
   so that file is not currently a mirror source — run both builds anyway; it is cheap.)
2. **`CLAUDE.md` has a 16,000-byte ceiling** (`tests/test_guardrails_layout.py`). Measure it
   with `wc -c CLAUDE.md`; after step 16 the headroom is under 200 bytes. The next rule that
   needs adding has to displace words, not join them. It was rebalanced once already by
   consolidating repeated rules; that is the move to repeat.
3. **Never invoke a real `claude` / `copilot` / `codex` CLI** from tests, verify commands, or
   kit execution. One live invocation was authorized in step 06, scoped to that single test, and
   was never wired into the suite.
4. **Commit at every green boundary; never push, merge, or commit on `main` without being
   asked** (rule adopted 2026-09-12, replacing "do not commit unless asked"). A dirty tree at
   session end is now a defect, not an expected state. `tests/test_guardrails_layout.py` pins
   the sentence.
5. **Byte-stability and key-set guards exist** on ledgers, budget result keys, demo output and
   docs. When one fires it is usually correct — update it deliberately with a comment saying
   why, never loosen it to make a run pass.
6. **`tests/test_kit_contract.py` fails if two drivers share an implementation** above 85%
   similarity. If you add a function to one driver, it probably belongs in `kit_contract.py`.
7. **Every test module that drives a real `cmd_run`/`main` path patches `POLYTROPOS_DATA_HOME`**
   to a temp dir at module level (`setUpModule` in the three driver tests, the Ralph tests, and
   `test_attempt_ledger.py`). The drivers default the attempt ledger to the per-user data root;
   a new test file that forgets the patch writes into the real store. Copy the block.
9. **`tests/test_telemetry_snapshot.py` counts sources as `len(ts.SOURCES)`**, not a literal,
   since step 17 added the sixth. Its `--days 5` assertion is a literal 5 that has nothing to
   do with the count; a blanket replace there is the mistake this line exists to prevent.
8. **`kit_contract._al()` caches the loaded module, and must.** The other lazy loaders reload
   per call; this one cannot, because `ClaimHeld` is caught by class identity, and a ledger
   opened by one load raising past an `except` naming another load's class was an uncaught
   exception where a refusal was meant. Tests loading `attempt_ledger` themselves hold a
   third copy; they never compare its classes with the contract's.

---

## Known gaps, deliberately left open

Each is recorded in `SECURITY.md` rather than hidden. None is a surprise; all are honest limits.

- **Model dispatch is not confined and cannot be under subscription auth.** Measured: Seatbelt
  blocks Keychain access, so a confined `claude -p` reports "Not logged in". Entitlement-gated,
  not fixable by profile rules.
- **No Linux or Windows sandbox backend.** `--exec-mode enforced` refuses there rather than
  downgrading silently.
- **Benchmark candidates and judges are not confined.** `repo_bench` builds history-free
  sandboxes and withholds reference tests structurally, but dispatch runs with driver privileges.
- **Role names are not permissions on Claude and Copilot.** Review dispatch carries a full
  permission grant; no citable per-tool flag was found for Copilot and inventing one was refused.
- **Execution state is not tamper-proof.** The attempt ledger is outside the workspace, so the
  confined verify path cannot reach it; a dispatch is unconfined and a worker with the user's
  privileges can write anywhere the user can. `TASKS.md`/`NOTES.md`/markers stay in the tree; a
  worker's own status flip is overwritten by the driver's verdict and reported, not prevented.
- **The ledger is not exactly-once.** It knows a call was made, closes a resultless one as
  unknown, never replays it, and cannot know whether the provider billed it.
- **`evidence:` gating is wired into Claude's driver only.** Copilot and Codex parse the field
  but do not gate on it.
- **`mkdocs build --strict` was never run locally.** The lock targets Linux and the toolchain is
  not installed here. The drift gate that runs before it passes; the build itself is unexercised
  until CI runs it.

---

## Waiting on you

- **Private vulnerability reporting** — you enabled it; `SECURITY.md`'s callout was removed.
  ✅ done.
- **GitHub repo settings the code cannot touch**, now named in `SECURITY.md`: Pages source set to
  "GitHub Actions", Dependabot (nothing auto-updates now that actions are SHA-pinned and the
  toolchain is hash-locked), and secret scanning / push protection.
- **Existing Copilot users will see conflicts on their first update** after step 11. Files
  installed before the ownership manifest existed classify as unmanaged if they differ from the
  current bundle. `harness_select install --harness copilot --adopt-existing` clears it in one
  run, keeping a `.polytropos-bak` of each. That is the honest cost of no longer overwriting
  silently, but it is visible and worth expecting.
- **Merged.** `harden/roadmap-steps-01-15` was fast-forwarded into `main` and pushed on
  2026-09-12. Step 16 starts on a fresh branch off `main`; the commit rule forbids committing on
  `main` directly.

---

## Resuming

```bash
cd /Users/michaelcave/Developer/reposV2/polytropos
python3 -m unittest discover -s tests          # expect 3727 OK, ~3 min
git log --oneline -2                           # the roadmap commit sits on fb40925
python3 bin/runtime_data.py where              # where your stores resolved to
python3 bin/harness_adapter.py                 # what each harness can actually do
python3 bin/attempt_ledger.py demo             # crash / resume / progress walkthrough, temp dir only
python3 bin/attempt_history.py demo            # the cross-harness join, temp dir only
```

Then read step 18 in the roadmap and continue. The pattern that has worked: verify the step's
claims against HEAD first, implement, run the affected suites, then the full suite, then update
`SECURITY.md` / `CLAUDE.md` / the doc mirrors together.
