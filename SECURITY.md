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
- **Benchmark spending is ceiling-gated.** No dispatch happens without an explicit `--max-usd`,
  validated finite and non-negative on every check; `plan` and `demo` spend nothing.
- **Personal data stays local and gitignored.** The memory, telemetry, journal, and benchmark
  stores are gitignored, written only by their own engines, and never bulk-injected into a
  session's context. Journal and usage collection read home directories strictly read-only.

- **Installation does not overwrite what it does not own.** Every Copilot and Codex destination
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
- **A worktree is not a sandbox.** Separate directories separate *files*. They do not separate
  privileges, credentials, network access, or the rest of your home directory.
- **Benchmark candidates and judges are not yet confined.** `bin/repo_bench.py` builds
  history-free sandboxes and withholds reference tests structurally, but candidate and judge
  dispatch does not yet run under `exec_policy`. Its setup and test commands run with the
  driver's privileges.
- **Role names are not permissions.** A prompt that says "read-only reviewer" does not make a
  reviewer read-only. Review dispatch no longer carries a blanket permission grant by default on
  any harness (`--review-permissions bypass` is the named opt-out on Claude and Copilot, and
  reports itself), and Claude translates the reviewer's declared tool pin to `--allowedTools`.
  But a pin that includes `Bash` reaches everything a shell reaches; Copilot has no citable
  per-tool flag, so its restricted mode is only the absence of the grant; and only Codex pins
  review to a read-only sandbox. The OS boundary above covers verification, not review.
- **Execution state is not tamper-resistant.** Run records, budgets, and acceptance evidence live
  in files the worker can write. They are bookkeeping, not an authority a lower-trust process is
  prevented from forging.
- **Estimated spend is not a provider-enforced cap.** Budget dials and `--max-usd` stop
  *polytropos* from dispatching. They cannot stop a provider from billing, and they do not bound
  spend that has already been incurred.
- **A capability nobody has run is not a control.** `primitives/harness-capabilities.json`
  records product support, polytropos implementation, and runtime verification separately,
  because collapsing them is how a driver comes to believe it holds a control it does not.
  `--allowedTools` was documented and implemented and silently swallowed the prompt until
  someone ran it. Most rows there say `unknown`, and that is the honest state, not a gap to
  fill in optimistically.
- **Redaction is shape-matching, not a guarantee of absence.** `bin/redact.py` catches
  strings that look like published credential formats and secret-named assignments. A password
  that reads as an ordinary word, a customer name, an address — none of those have a shape and
  none are caught. Treat the inbox as text you are choosing to send to a model.
- **Isolating the summary is not proof the model had no tools.** What is enforced is that it
  ran outside the project, with a reduced environment, and demonstrably did not write where it
  was placed. No tool-restricting flag is passed: this repo pins CLI flags as best-effort and
  not live-verified, and guessing at one on the daily path would risk breaking it to gain a
  control that could not be confirmed.
- **Bounding a process is not exactly-once execution.** A process terminated at its limit may
  already have had its external effect — a model call billed, a file written. After a crash,
  nothing here knows what ran. Reconciling that is durable-lifecycle work that does not exist
  yet; a timeout tells you this engine stopped waiting, not that nothing happened.
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
