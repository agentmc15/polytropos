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

- T3 rendering toolkit, additions to the T2 contract (no owner involved -- T3 touches no
  owner, so there is no owner-shape delta to record, only a toolkit-contract one): T2's `_h`
  is renamed `esc` and gains one behaviour -- `None` now renders
  `<span class="unknown">unknown</span>` (styled italic/muted by the new `.unknown` rule)
  instead of the plain word, so every later panel gets the styled-unknown honesty rendering
  for free; nothing outside this file called `_h`, so nothing else changed. The per-panel
  dict gains an optional `refresh_hint` key (`build_model` defaults it to `None`), rendered
  by the new `panel()` toolkit function as an optional second `<p class="meta">` line --
  T6's stale-telemetry hint (PLAN D7d) is the first anticipated user. The `blocks` vocabulary
  (`p` / `list` / `table`) gains `svg_bars` / `svg_sparkline` (raw rows/points + title/desc +
  key names; rendered by `_render_block` at page-render time, AFTER the model is scrubbed --
  never call `svg_bars`/`svg_sparkline` from inside a panel builder and store the result in a
  `"p"` block, which would double-escape the markup) and `table` gains an optional `details`
  bool for the `<details>` long-table wrap. Chart `<title>`/`<desc>` element ids come from a
  module-level counter (`_chart_ids`) reset by `render_page` itself
  (`_reset_chart_sequence`) so two renders of one model stay byte-identical (PLAN D9); a
  direct `svg_bars`/`svg_sparkline` call outside `render_page` (as in a test, or the T3
  Verify probe) just keeps counting, which does not affect that one figure's own structure.
  `fmt_usd`'s `basis_label` has no default, by design: a caller that omits it fails loudly
  with `TypeError` at the call site rather than the page ever showing a bare dollar.

agent: T3 id=a63c06d92630fc56e role=implementer model=sonnet
agent: T3 id=aa1bdad7e2228c859 role=verifier model=sonnet findings=1 confirmed=0 result=accepted
agent: T3 id=a82e73acd8b5aa337 role=red-team model=sonnet findings=7 confirmed=4 marginal=4 result=accepted

- T3 red-team adjudication. Confirmed, and sent back as T3's retry:
  - Table cells re-escape formatter output, so `fmt_usd`'s basis label and the styled
    `unknown` span show up as literal markup in the very tables T4-T7 are briefed to build.
  - `fmt_seconds` and `fmt_count` raise on NaN or infinity. Plain `json.loads` yields those
    from a corrupted ledger, and the error collapses the whole panel.
  - `fmt_usd` and `fmt_credits` print `$nan` and `$inf`.
  - An empty `observed` renders blank instead of "never captured".
  Not confirmed:
  - A bare-string row splits into characters: no caller does that.
  - An all-non-positive bar series draws no bars: its table twin carries every value.
  - A future-dated observation shows a negative age: that is true, not fabricated.

- T3 retry, fixing the four confirmed breaks above -- toolkit-contract additions for T4-T7,
  all inside `bin/dashboard.py`/`tests/test_dashboard.py`, no owner touched:
  - **Typed cells**, the fix for the double-escaping break. A table cell is now either a
    plain value (still through `esc`, exactly once -- a builder can never smuggle raw HTML
    through a plain string) or a typed cell, a dict carrying `fmt`:
    `{"fmt": "usd", "value": v, "basis": label}` (the only shape with a third key),
    `{"fmt": "credits"|"count"|"seconds"|"date", "value": v}`. `CELL_FORMATS` maps each `fmt`
    to its formatter; `_render_cell` dispatches a cell and is the ONLY thing `html_table` (and
    so every `table` block) calls per cell now -- a formatter's own output is already-escaped
    HTML and is used as-is, never escaped a second time. This is the shape T4's cost-by-basis
    table (and every later panel with a dollar, credits, seconds or date cell) must build its
    `rows` from; a `fmt_usd(...)`/`fmt_credits(...)` STRING is never itself a cell value --
    that is exactly the break this replaces. `svg_bars`/`svg_sparkline` are unaffected: their
    rows carry raw numbers/`None` for the chart geometry, never typed cells.
  - **Non-finite numbers.** `_finite_float(v)` is the one place that turns `v` into a finite
    float or `None` -- `None` for anything `float()` cannot parse AND for a float that parses
    but is NaN or ±Infinity (`math.isfinite`). `fmt_usd`/`fmt_credits`/`fmt_count`/`fmt_seconds`
    all route through it and, on `None`, fall back to the SAME branch an unparsable value
    already used: the value's own escaped text, no `$`/credits/seconds suffix, `fmt_usd`'s
    basis label still beside it. A string form (`"nan"`, `"Infinity"`, `"-Infinity"`,
    `"1e400"`) renders ITSELF verbatim, never a reinterpretation -- `"1e400"` never becomes
    `"inf"` -- because the fallback is `esc(v)` on the original argument, not on the parsed
    float. `import math` added for `math.isfinite`; nothing else changed about the imports.
  - **Empty `observed`.** `panel()` now treats `None`, `""` and a whitespace-only string as
    the same absence and prints "never captured" for all three; `age_days`/`_parse_date_like`
    already did this correctly (an empty string never parsed as a date) so only `panel()`'s
    own display fallback needed the fix.
  - The stale comment above `esc` ("every string goes through `_h`") is corrected to `esc`.
agent: T3 id=a63c06d92630fc56e role=implementer model=sonnet
outcome: T3 model=sonnet attempts=2 result=retry-pass review=revised run=2026-09-25-7e3a
