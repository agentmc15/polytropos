# NOTES — observability-dashboard

Cross-task learnings and the machine-read ledger for this kit. Ledger tokens quoted in prose
are always backticked.

## Run 2026-09-25-7e3a (interactive, autonomy advisory)

- Branch `kit/observability-dashboard`. The test-isolation fix (`fix/tests-isolate-data-home`,
  4c86459) is merged locally at 0d47a47 so the data-home canary guards every new test module;
  it still reaches `main` through its own PR.
- Dispatch vehicle: the session had registered its agent types before the kit's
  `.claude/agents/observability-dashboard-*.md` files existed, so T1's implementer ran as
  `general-purpose` on sonnet, told to load its agent file as operating instructions. The
  kit's agent types registered while T1 ran; every later dispatch uses them, so the
  read-only roles carry their `tools:` pin. The orchestrator still snapshots the tree before
  each read-only dispatch and compares it after; an unexpected change is that agent's defect.
- Open user decisions taken at the architect's defaults: transcript-priced scorecard dollars
  on by default (`--no-transcripts` opts out, PLAN D15); the journal panel renders the
  journal's own priced total under its own label (T6 brief, item 2).

`agent:` lines below record each dispatch as it returns.

agent: T1 id=a6ccfc1fbf532a88e role=implementer model=sonnet
agent: T1 id=afd2e482fc46f7555 role=verifier model=sonnet findings=0 confirmed=0 result=accepted
agent: T1 id=a0f6f482b86af3804 role=red-team model=sonnet findings=1 confirmed=1 marginal=1 result=accepted
defect: T1 kind=unspecified-path

- T1 red-team break (confirmed): `docs/GUIDE.md` lists the stores `runtime_data.py where`
  prints and still named nine after T1; the brief's file list never named that file, so no
  verify clause could see it. Per the roster's consequence rule a confirmed red-team break is
  a failed verify, so T1 retries with that evidence. This adds one hand-authored file
  (`docs/GUIDE.md`) and its generated mirror beyond the brief's list: an orchestrator
  adjudication that serves the task's own title, recorded here rather than silently.
agent: T1 id=a6ccfc1fbf532a88e role=implementer model=sonnet
outcome: T1 model=sonnet attempts=2 result=retry-pass review=revised run=2026-09-25-7e3a

- T2 owner-shape deltas, adapted in `bin/dashboard.py` only (no owner edited):
  `safe_paths.confined_replace` does not refuse a link at the leaf — its rename replaces the
  link and never writes through it — so `write_page` checks both leaves first
  (`safe_paths.leaf_is_regular` plus a no-follow existence test) and raises `SafePathError`
  (exit 2) before writing either, keeping the brief's "a symlinked `index.html` is refused".
  `safe_paths.confined_read_bytes(..., missing_ok=True)` raises `FileNotFoundError` when the
  root itself is absent, so `read_config` treats a missing out dir as "no config" first. The
  scorecard has no accessor for its projects-dir default; `--projects-dir` defaults to
  `routing_scorecard.sc.DEFAULT_PROJECTS_DIR`, the value its own argparse default and
  `assemble_history_card(projects_dir=None)` resolve to.
- T2 contract for later panels: a builder takes `ctx` (`model`, `data_home`, `checkouts`,
  `opts` carrying `projects_dir` / `no_transcripts` / `git`, `caps`, `now`, `notes`) and
  returns `{source, observed, notes, summary, blocks}`; blocks are `p` / `list` / `table`
  dicts rendered generically, the model is scrubbed whole before rendering, and a builder
  that raises becomes a panel note naming only the exception type. A truncating cap writes
  its note through `cap_note(caps, NAME, detail)` into THAT panel's own `notes` (PLAN D5);
  `build_model` copies every panel note, prefixed `<id>: `, into the page-wide list the
  bounds section and `build.json` show, and `caps_report` marks the hit from it. The
  namespace classification's notes ride on the `namespaces` panel. `synthetic_world(root,
  residue=30)` takes an optional residue count so the 1,500-residue scale test goes through
  the one fixture builder.
- T2 reading of "never `PLUGIN_ROOT`": the engine never adds `PLUGIN_ROOT` as a candidate and
  never uses it as a git working directory in its own right; a development clone that the
  working directory, a `--checkout` flag or `config.json` names is a candidate like any
  other, `git worktree list` included. Flagged for the verifier to adjudicate.
- T7 tripwire found during T2: `tests/test_decision_evaluation_manifest.py` and
  `tests/test_training_data.py` each assert that only `bin/runtime_data.py` and the store's
  own engine name the `evals` / `training` store, by grepping every `bin/*.py` for the quoted
  literal. The pinned panel ids `evals` and `training`, written as quoted literals in
  `bin/dashboard.py`, trip both guards: T2's first full-suite run went red on exactly that (a
  `PANEL_ORDER` tuple, since removed; the pinned order now lives in `tests/test_dashboard.py`).
  T7 registers builders under those two ids and will hit it again; it needs a decision before
  T7 dispatches, never a silent edit to either guard.

agent: T2 id=a307190263eab1cf0 role=implementer model=opus
defect: T7 kind=unspecified-path

- Orchestrator on the T7 tripwire: confirmed by reading both guards. `workflow_eval` exposes no
  public name for its store (only the import-time `DEFAULT_STORE_DIR`), so reading every
  checkout's evals store forces `bin/dashboard.py` to spell the name; re-spelling it would
  evade the guard, not satisfy it. Both guards' own comments say a new module naming the store
  "has to name itself here", so the planned resolution is to add `dashboard.py` to both
  expected lists at T7, commented as a read-only consumer. That widens T7's file list by the
  two test files, and is put to the user before T7 dispatches.
agent: T2 id=a1b99eba138799723 role=verifier model=sonnet findings=0 confirmed=0 result=accepted
agent: T2 id=acdf6423a3929781f role=red-team model=sonnet findings=5 confirmed=3 marginal=3 result=accepted

- T2 red-team adjudication. Confirmed, and sent back as T2's retry: an empty-string
  `--out-dir` collapses to the working directory and writes the private page there (inside a
  git checkout, as untracked files); an empty `--data-home` scans the working directory; and
  the write-failure message names `--out-dir` as the cause when the failure lies elsewhere.
  Not confirmed: no cap on the checkout count (GUARDRAILS exempts growth the user chose, and
  config and flags are the user's); a pre-existing `--out-dir` is not tightened to `0700`
  (re-permissioning a directory the user chose is not the engine's call, and files stay
  `0600`).
- Owner quirk, out of scope and reported to the user rather than fixed:
  `safe_paths.confined_replace` reserves its temp name with `tempfile.mkstemp(dir=os.getcwd())`
  (an empty placeholder, deleted at once; the data is written inside the confined dir), so
  every store writer fails when run from an unwritable working directory.
agent: T2 id=a307190263eab1cf0 role=implementer model=opus
outcome: T2 model=opus attempts=2 result=retry-pass review=revised run=2026-09-25-7e3a
