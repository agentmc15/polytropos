# Security policy

polytropos orchestrates coding agents: it dispatches models, runs verification commands, and
writes execution state. Much of what it does is *intentional code execution* — a kit's verify
command is a shell line the repository author wrote, and running it is the point. This document
states which boundaries are actually enforced, which are not, and how to report a problem.

## Reporting a vulnerability

Report privately through GitHub's security advisories, not a public issue:

<https://github.com/agentmc15/polytropos/security/advisories/new>

Please include the commit you tested, the reproduction, and what a successful exploit gets an
attacker. Local reproductions using temporary directories and synthetic secrets are preferred
over anything run against real credentials.

## What is enforced today

These are properties with code behind them, not conventions:

- **Target repositories are read-only by construction.** `bin/repo_bench.py` reaches a target
  repo only through `git_target`, which refuses any verb outside a read-only allowlist. Benchmark
  sandboxes are history-free tree extractions, so the reference fix is unreachable from inside a
  candidate's working directory.
- **Reference tests are withheld from candidates.** Grading substrates are constructed
  separately from the sandbox a candidate works in; the withheld test blobs are never written
  into a candidate's tree.
- **Codex review and acceptance are pinned read-only.** `bin/codex_execute.py` forces
  `--sandbox read-only` on both and rejects any attempt to override it through extra arguments.
  It also refuses extra arguments that would displace the policy-selected model or profile.
- **Cursor is identified before it is trusted, and its review is pinned read-only.** Cursor's
  CLI is a binary named `agent`, a name anything might carry. `bin/cursor_execute.py` dispatches
  to it only after `--version` or `about --format json` identifies Cursor -- by naming it, or by
  answering `about` with Cursor's own schema (a string `cliVersion` beside `latestStatus`,
  `latestVersion`, `osPlatform`), because the real CLI names itself nowhere; anything else is
  refused before a claim, a ledger entry, or a file write. `review` runs under `--mode ask`, never
  `--force`, and extra arguments that would change the mode, model, workspace, or session are
  refused. Only the version line is kept from the `about` payload. `--dry-run` spawns nothing,
  not even the identity probe.
- **A code graph is untrusted repository evidence, read within bounds.** `bin/graph_ground.py`
  accepts a graph's `source_file` only as a relative, traversal-free path under the repository
  root (rejected paths are named, never read), reads files through the confined reader, refuses
  a graph past a byte ceiling, bounds every walk by depth, node count, and a hub rule, bounds
  every search by files, hits, and bytes, and reaches git only through `bin/proc_runner.py`
  with read-only verbs. Its one write is the provenance sidecar beside the graph, written
  through `bin/safe_paths.py` at `0600`. A graph with no sidecar reports freshness `unknown`;
  no revision is ever manufactured. Graph metadata suggests reads and nothing more: it grants
  no permission, edits no acceptance criterion, and establishes no safe concurrent write.
- **Concurrent work cannot collide silently, and the merged tree is verified again.**
  `bin/kit_scheduler.py` runs ready tasks concurrently only when asked (`--max-parallel`
  above one; sequential is the default), each in its own copy of the tree outside the
  workspace. Every task in a batch is claimed atomically and admitted against the PLAN.md
  budget in one decision before anything is dispatched. What a worker changed is measured,
  never declared; a file two workers changed, or one the user changed while the batch ran,
  is a conflict that applies nothing, resets nothing, and keeps the worker's copy. Every
  integrated task's check runs again on the merged tree. A worker's copy that edits the kit
  is recorded as a violation and never integrated; a proposal to change acceptance is refused
  whole. An acceptance records the upstream artifact versions it rested on, and a dependency
  re-accepted with a different artifact makes it stale: its dependents are not scheduled
  until it is re-verified.
- **A routing default changes only through a reviewed, versioned, reversible proposal.**
  `bin/workflow_eval.py` measures complete workflows on held-out tasks with the tests oracle
  as the only source of `solved`; a reviewer's verdict, the kit's own check, and a person's
  adjudication are recorded beside it, and an acceptance the oracle contradicts is counted
  as an incorrect acceptance rather than averaged away. `prefs/routing-policy.json` is
  written only by `apply`, which refuses a proposal below the evidence floor, from a single
  repeat, from tasks that already backed the policy in force, without a named reviewer's
  acceptance, or against a file that changed since the proposal was made; every version is
  kept and `rollback` restores one. Nothing reads that file automatically.
- **A declared role a driver cannot run is refused or disclosed, never skipped.** Every driver
  reads a kit's PLAN.md `roles:` and `workflow:` lines through the one grammar in
  `bin/kit_contract.py` before it previews or claims anything; a role the driver cannot
  sequence (`ROLE_SUPPORT`) stops the run by default, and `--roster-gap disclose` proceeds only
  with the gap printed and recorded in the attempt ledger. Each role's scope, hook, assurance,
  capabilities, and result fields are stated as data (`ROLE_CONTRACTS`), separate from whether
  an agent is spawned for it; no role runs because its name exists.
- **Routing policy is an explicit selection, never a learned one.** Which policy routes a
  Codex task (`reserved`, the default, or the opt-in `adaptive`) comes only from a `--policy`
  flag or a kit's PLAN.md `routing:` line, both validated before anything is dispatched.
  `bin/routing_policy.py` decides from the pricing catalog, the task's own fields, the attempt
  ledger's count of prior failures, and the capability registry — never from memory facts,
  lessons, usage claims, or model output — and hard filters (availability, an explicit pin, an
  exclusion, an unsupported effort, the budget) apply before any preference is weighed. No
  observation promotes a new default; installed defaults change only by an explicit edit.
- **Benchmark spending is ceiling-gated.** No dispatch happens without an explicit `--max-usd`,
  validated finite and non-negative on every check; `plan` and `demo` spend nothing.
- **Release claims are computed from the evidence, never typed, and a stub pass is never
  written as installed-client verification.** `bin/release_gate.py` renders the supported
  matrix in `docs/RELEASE.md` from the capability registry, the contract versions, the
  manifests, and a map from each shared contract to the tests that prove it through a stub;
  the registry's `verified` column and its date stand beside those tests, never merged with
  them. `check` fails on a drifted block, a malformed registry row, a test id that no longer
  exists, a private store without its root-anchored ignore rule, a tracked file under one, an
  unpinned workflow action, or a renamed command the checklist cites. `reverify` lists what a
  client release invalidates and edits nothing.
- **Personal data stays local and gitignored.** The memory, telemetry, journal, benchmark, and
  training stores are gitignored, written only by their own engines, and never bulk-injected
  into a session's context. Journal and usage collection read home directories strictly
  read-only.

- **Installation does not overwrite what it does not own.** Every Copilot, Codex, and Cursor destination
  is classified before a byte is written — absent, already identical, written by this installer
  and unchanged, or something else — and that last case is preserved and reported rather than
  replaced. Overwriting it takes an explicit flag that also keeps the prior bytes. Ownership
  lives in a manifest under each harness home; a manifest that cannot be parsed owns nothing,
  so unreadable state preserves files rather than claiming them.
- **Installers restate their preconditions at the moment they write.** A plan is a snapshot, so
  `install` creates with `O_EXCL` (absence asserted by the kernel, in the same operation as the
  write) and a managed refresh re-reads the destination immediately before replacing it. Either
  refuses rather than applying a stale plan. Rollback after a partial failure takes back only
  the bytes that run actually wrote: a destination something else changed in the meantime is
  left as found and named in the error.
- **Runtime data is kept out of the distributable tree and created private.** Stores resolve
  to a per-user application-data directory, namespaced per checkout, created `0700` with `0600`
  files. An existing in-tree store keeps being used rather than being relocated silently, and
  migration copies without ever deleting the original.
- **User free text is redacted and bounded before it is persisted or dispatched.** Inbox lines
  pass through `bin/redact.py` on the way into the journal digest and on the way to a model.
- **The journal summary runs isolated, and is checked for having stayed a text transformation.**
  It executes in an empty temp directory, so the repository's own instructions, hooks, and MCP
  config are out of scope, with a reduced environment; if it writes anything into that
  directory the summary is rejected rather than accepted.
- **Recalled memory carries its provenance, and out-of-scope facts are withheld.** Source,
  project, trust level, observation time, expiry, and provider eligibility survive recall; a
  fact scoped to another project or another provider is not returned at all, and an imported or
  model-derived observation is labelled as reported text rather than a directive.
- **External processes are bounded and cannot outlive their run.** Every dispatch, verify
  command, benchmark job, and summary subprocess starts through `bin/proc_runner.py`: a
  validated working directory, a wall-clock limit, and an output ceiling that keeps draining so
  a noisy process cannot deadlock the engine by filling a pipe nobody is reading. Each runs in
  its own session, so termination reaches the whole process group and a command's children do
  not survive it. A run ends when the command ends, not when its pipes close.
- **Every dispatch is recorded before it is made and after it returns, outside the tree.**
  `bin/attempt_ledger.py` is an append-only record under the per-user data root, one per kit or
  Ralph goal. An attempt with no result is closed as unknown by the next run, never as success,
  and never replayed; prior attempts count against the kit's budget before `NOTES.md` has
  summarised them; a task is claimed with `O_EXCL` so two runs cannot hold it; and the final
  status is written from a fresh read of `TASKS.md`, never from the snapshot taken before a
  model spent minutes editing the tree. A logged-out CLI, a missing binary, or an unknown flag
  is classified as such and stops the run rather than escalating to a costlier model.
- **A dispatch carries only its own provider's credentials.** The environment handed to a
  harness CLI is a base set plus that provider's own variables. The machine's other providers'
  keys, and its unrelated credentials, are not forwarded to a coding agent.
- **Paths are contained by one helper, without a check-then-use race.** Every store, marker, and
  install destination is reached through `bin/safe_paths.py`, which walks each path
  directory-relative with `O_NOFOLLOW`, so a symlink swapped in mid-operation has nothing to
  redirect. Where the runtime lacks directory-relative file operations it refuses rather than
  falling back to the racy form.

- **Verification runs inside an OS boundary, on macOS.** The kit drivers and the verify hook
  run each verify command under `sandbox-exec` (`bin/exec_policy.py`): writes limited to the
  workspace and a run-scoped scratch directory, network denied, credential stores unreadable,
  and the environment reduced to an allowlist. It is the default (`--exec-mode enforced`) and
  it refuses to run rather than falling back when no backend is available. `--exec-mode
  trusted-host` is the named opt-out and reports itself as such.

  **Linux and Windows have no backend implemented**, so `enforced` refuses there and only the
  explicit trusted-host mode runs. That is an honest gap, not a silent downgrade.

## What is NOT a boundary

Do not rely on any of the following. Each is a known gap, not a subtlety:

- **The model dispatch itself is not confined, and cannot be while you use subscription auth.**
  Measured on macOS: `sandbox-exec` blocks Keychain access, and Claude Code keeps subscription
  credentials in the Keychain, so a confined `claude -p` simply reports "Not logged in".
  Granting `mach-lookup`, `authorization-right-obtain` and write access to
  `~/Library/Keychains` does not change it — Keychain access is gated by entitlements, not
  profile rules. It would work under API-key auth, but a boundary whose existence depends on
  how you happened to log in is not one we will claim. Verification is confined because a
  verify command authenticates to nothing.
- **A scheduler's copy is not a sandbox either.** The scheduler separates *writes*: a worker
  cannot touch the main tree or another worker's copy, and only measured, non-conflicting
  write sets are applied. Workers still share the machine, the network, and the credentials
  the dispatch environment carries; a worker that reads a file another worker is changing
  is not detected, only conflicting writes are.
- **A worktree is not a sandbox.** Separate directories separate *files*. They do not separate
  privileges, credentials, network access, or the rest of your home directory.
- **An evaluation's ranking is evidence about one run, not a universal.** A workflow that
  ranks first on one repository, one instruction version, and one harness has been measured
  there and nowhere else; the card refuses to state an order below the evidence floor or
  from a single repeat, and a live plan's figures are estimates a ceiling bounds only at the
  next dispatch, never a provider-side guarantee. One evaluation has now been run live from
  here, on the Claude adapter, and its record is the `workflow_evaluation` row in
  `primitives/harness-capabilities.json`: every variant in it fell below the evidence floor and
  is labelled so, which makes it a verification that the pipeline runs and *not* a ranking of
  anything. The Codex, Copilot and Cursor adapters have still never been run live.
- **Benchmark candidates and judges are not yet confined.** `bin/repo_bench.py` builds
  history-free sandboxes and withholds reference tests structurally, but candidate and judge
  dispatch does not yet run under `exec_policy`. Its setup and test commands run with the
  driver's privileges.

  A protected-experiment *profile* now exists in `bin/exec_policy.py` — `exec_policy.py profile`
  reports whether this host can enforce one, and `exec_policy.py sentinels` attempts every
  forbidden operation for real and prints what the kernel returned. It separates the setup,
  candidate, test and judge roles from the controller's rules, labels, withheld answers and
  accepted state, and each denial is attributed by an unconfined control run that had to
  succeed plus a permission-class errno, because a non-zero exit is not a refusal. **Nothing
  dispatches through it yet**: it is an available boundary, not a wired one, and `repo_bench`
  is unchanged. Where a host cannot apply a profile it reports `unavailable` with its
  prerequisites named and certifies nothing — there is no trusted-host fallback for a protected
  experiment — and a certification covers the named sentinel operations only, with
  `exec_policy.SENTINEL_NOT_PROVEN` listing what it does not cover.
- **Role names are not permissions.** A prompt that says "read-only reviewer" does not make a
  reviewer read-only. Review dispatch no longer carries a blanket permission grant by default on
  any harness (`--review-permissions bypass` is the named opt-out on Claude and Copilot, and
  reports itself), and Claude translates the reviewer's declared tool pin to `--allowedTools`.
  But a pin that includes `Bash` reaches everything a shell reaches; Copilot has no citable
  per-tool flag, so its restricted mode is only the absence of the grant; and only Codex pins
  review to a read-only sandbox. The OS boundary above covers verification, not review.
- **Execution state is not tamper-proof.** The attempt ledger lives outside the workspace, so a
  verify command confined by `bin/exec_policy.py` cannot reach it and a committed or synced tree
  never carries it. But a dispatch is not confined (above), and a worker running with the user's
  own privileges can write anywhere the user can. `TASKS.md`, `NOTES.md`, and the verify-pass
  markers are still in the tree a worker edits; the driver writes its verdict over a status the
  worker changed, and says so, which is a report, not a prevention. The same holds for the rest
  of a task's block: a worker that rewrites its own brief, verify command, or dependencies
  mid-run is detected at projection time from a fresh read, reported, and recorded in the
  ledger as `plan.drift`, and the verdict stays the one for the plan the run started with. The
  file is not restored; the edit is named for the architect to judge. The task graph itself is
  validated before any dispatch, so a plan with a cycle, a duplicate id, or a dependency on no
  task runs nothing rather than something — but that is validation of structure, not
  authentication of who wrote it.
- **Estimated spend is not a provider-enforced cap.** Budget dials and `--max-usd` stop
  *polytropos* from dispatching. They cannot stop a provider from billing, and they do not bound
  spend that has already been incurred.
- **A capability nobody has run is not a control.** `primitives/harness-capabilities.json`
  records product support, polytropos implementation, and runtime verification separately,
  because collapsing them is how a driver comes to believe it holds a control it does not.
  `--allowedTools` was documented and implemented and silently swallowed the prompt until
  someone ran it. Most rows there say `unknown`, and that is the honest state, not a gap to
  fill in optimistically.
- **Cursor's IDE and cloud modes are files, not a driver.** The bundle this repository installs
  under `.cursor/` is read by Cursor's IDE agent and cloud agents as well as by its CLI, but
  only the CLI is dispatched from here. The CLI has been run live from this repository — six
  rows in `primitives/harness-capabilities.json` carry a dated `verified` — and the IDE and
  cloud modes never have; both remain `unsupported` there, and installing files an editor
  happens to read is not a driver and is not evidence that one ran. Usage and model identity
  are what the CLI's own output says or `unknown`; the editor's SQLite store is never opened
  and no browser is automated to find out more.
- **Redaction is shape-matching, not a guarantee of absence.** `bin/redact.py` catches
  strings that look like published credential formats and secret-named assignments. A password
  that reads as an ordinary word, a customer name, an address — none of those have a shape and
  none are caught. Treat the inbox as text you are choosing to send to a model.
- **The decision-training seam applies a narrower, explicit redaction contract, not the inbox's
  best-effort one.** `bin/training_data.py` passes exactly two fields through `bin/redact.py`
  (`REDACTED_FIELDS`: an input entry's text, a revocation's reason) and names ten more, including
  the question's wording and its rubric, as `NOT_REDACTED_FIELDS` — those two are stored
  byte-exact by design because `decision_contract.QuestionSpec.digest()` is taken over them, so a
  credential shape typed into either one reaches the model's own input file unredacted and the
  record names the field in `not_redacted` rather than silently passing it (see
  `docs/TRAINING-DATA-READINESS.md`). This is a documented dormant limit, not an active exposure:
  `training_data.COLLECTION_ENABLED` and `CAPTURE_WIRED` are both `False`, with no production
  call site — only the module's own offline `demo` and its tests invoke it.
- **Isolating the summary is not proof the model had no tools.** What is enforced is that it
  ran outside the project, with a reduced environment, and demonstrably did not write where it
  was placed. No tool-restricting flag is passed: this repo pins CLI flags as best-effort and
  not live-verified, and guessing at one on the daily path would risk breaking it to gain a
  control that could not be confirmed.
- **Recording an attempt is not exactly-once execution.** A process terminated at its limit, or
  killed after dispatch, may already have had its external effect — a model call billed, a file
  written. The ledger knows the call was MADE, closes it as `unknown` when no result came back,
  and never replays it. It does not know whether the provider billed it, and a resumed run's
  only evidence of what the tree now holds is the check it re-runs.
- **Kits are trusted input.** A `PLAN.md`/`TASKS.md` kit contains executable verify commands.
  Running a kit you did not write is equivalent to running its scripts.

## Where the approval line sits

The line between what runs unasked and what waits for you is reversibility, not task size.
Each lane below describes code paths, not a policy a model is asked to follow:

- **Reversible work runs without asking.** Reading, planning, checking, rehearsing: every
  engine's `demo` / `--demo` / `--dry-run` path is synthetic or spawns nothing and spends
  nothing; `bin/harness_update.py check`, `bin/exec_policy.py check`, and the two docs
  generators' `check` compare and write nothing; `bin/runtime_data.py export --to` copies a store
  to a directory you name and changes nothing else.
- **Consequential actions are prepared in full, then gated on one named switch.** The switch is
  a flag in code, never a judgement made at run time. Spending needs `--live` together with an
  explicit `--max-usd` (`bin/repo_bench.py`). Writing into a harness home happens only through
  `bin/harness_select.py`'s writers, reached by its own `install` and by `bin/harness_update.py
  apply`, both of them your commands, and overwriting a file it does not own takes
  `--adopt-existing`, which keeps the prior bytes. Restoring a blanket tool grant to a reviewer
  is `--review-permissions bypass`; leaving the OS boundary is `--exec-mode trusted-host`; both
  report themselves as the opt-out they are. Copying a store out of the tree is
  `bin/runtime_data.py migrate --apply`, and it copies without removing the original.
- **Irreversible actions are never taken on the engine's own initiative.** Nothing here
  relocates a store, and the one deletion, `bin/runtime_data.py forget`, is a dry run by
  default, scoped by age, and deletes only with `--apply`. Installation never overwrites what it
  does not own, and rollback takes back only the bytes that run wrote. Target repositories are
  reached through a read-only verb allowlist. `bin/harness_update.py apply` never writes
  `~/.claude`: the remedy is printed, not executed.

Model dispatch sits in the middle lane by design. A kit run is your explicit action and the
point of the tool; what the drivers add is that the run's own consequential steps (spend,
escalation, a permission or boundary opt-out) are each gated and named, so a run that took an
opt-out cannot read afterwards like one that did not.

## Supported use

polytropos is currently appropriate for repositories you control, run by the person who owns the
machine. It is **not** currently an appropriate isolation boundary for unattended execution
against untrusted repositories from a credential-rich host. An outer OS sandbox — a container, a
VM, a separate user account — is the mechanism that limits host exposure today; polytropos does
not provide one.

Which harness, client mode, and OS mode is supported, to what degree, and on what evidence is
the release matrix in `docs/RELEASE.md`, generated by `bin/release_gate.py`. It distinguishes
stub conformance (the suite) from installed-client verification (a dated run recorded in
`primitives/harness-capabilities.json`); as of this writing the latter exists for all four clients
(one live run and one read-only review each on a throwaway kit, 2026-09-16; Codex's acceptance
too). The live checks that remain unrun -- escalation, the dead-run resume path, concurrent
dispatch, Cursor's `--model` selection and its IDE and cloud modes, and the Codex, Copilot and
Cursor workflow-evaluation adapters -- are listed there as prepared, not done. The Claude
workflow-evaluation adapter is the one that has since run; read the registry rather than this
sentence for what is verified today, because this list is prose beside the evidence and will go
stale again the next time someone runs one.

## Dependencies and the build supply chain

`bin/` and `tests/` are stdlib-only by invariant, so the runtime has no third-party dependency
surface. The documentation site is the one exception, and it is pinned rather than trusted:

- **Every GitHub Action is pinned to a full commit SHA**, with the release it corresponds to in
  a trailing comment. A tag is a mutable pointer — `@v4` runs whatever it points at today, so an
  action that is compromised or simply re-pointed changes what CI executes with no commit here.
  To update one, read its release notes, then resolve and confirm the SHA:

  ```bash
  gh api repos/<owner>/<repo>/git/ref/tags/<tag> --jq .object.sha
  gh api repos/<owner>/<repo>/tags --paginate --jq '.[]|select(.commit.sha=="<sha>").name'
  ```

- **`docs-src/requirements.txt` pins every package, including transitives, with a sha256**, and
  CI installs with `--require-hashes`, so a substituted artifact fails the build rather than
  running in it. Its header carries the exact command that regenerates it for the CI platform.
  It is installed only in CI or a throwaway virtualenv, never as part of running the plugin.

- **Deploy credentials are scoped to the job that deploys.** The build job — the one that runs
  repository content through a third-party toolchain — holds `contents: read` and nothing else.
  `pages: write` and `id-token: write` (which mints an OIDC token) exist only in the deploy job,
  which runs no repository code.

- **Generated documentation rejects unsafe links.** `bin/copilot_docs.py` validates a URL's
  scheme after link rewriting against a small allowlist (`http`, `https`, `mailto`, plus
  relative paths and fragments) and refuses control characters, which browsers strip before
  resolving and which can therefore hide a scheme from a literal check. An unsupported scheme
  fails the build rather than being silently neutralized.

**On secret scanning.** Pattern scans — GitHub's, or this repo's own `bin/redact.py` — find
strings that match known credential shapes. A clean scan is not evidence that a repository or a
file contains no secret: anything without a distinctive shape is invisible to them. Treat a hit
as actionable and a miss as uninformative.

## Repository settings this code cannot configure

These are account- or repository-level switches. Code in this repository cannot enable them,
and nothing here should be read as a claim that they are on:

- **Pages source** must be set to "GitHub Actions" (Settings → Pages) for the docs workflow to
  publish; `pages: write` grants the right to deploy, not to configure.
- **Dependabot** (version and security updates) is the maintained way to learn that a pinned
  action or package has moved; pinning by SHA and hash deliberately means nothing updates on
  its own.
- **Secret scanning and push protection** are worth enabling, subject to the caveat above.
