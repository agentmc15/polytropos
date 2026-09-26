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

## Phase 1 review (reviewer opus ae70fd6f3998a5d4d, security-auditor sonnet a91561ce96a7b8719)

agent: P1 id=a91561ce96a7b8719 role=security-auditor model=sonnet findings=0 confirmed=0 marginal=0 result=accepted

- Security auditor: a clean pass. No subprocess or network path beyond the two git verbs, no
  write outside the store or `--out-dir`, no harness-home or `*.db` read, the exact CSP and
  none of the banned tokens on a fixture-built page, no injection surface yet. Its full-suite
  run hit one ERROR, `test_kit_scheduler.SecurityTests.test_a_worker_cannot_reach_the_main_tree_or_another_copy`,
  in a module this kit never touches. That test passed 34/34 in isolation three times, and the
  reviewer's full-suite run a few minutes earlier was clean. So it is recorded as a flake
  under a loaded machine (two review agents and Codex's own suite were running at once), not
  as a Phase 1 defect. Snapshots taken before and after both read-only dispatches are
  byte-identical.
- Reviewer verdict `revised` with ten findings, counted as the verdict tiered them. Its eight
  "Notes (carry forward)" are not counted. The orchestrator re-read the code for each finding
  and confirms all ten:
  - B1 (`classify_namespaces` has no complete/cut/failed state): a cut or failed listing
    renders `0` and "No namespace in this data home for …" as facts. Fixed in the P1 fix
    round.
  - B2 (a typed `usd` cell with a blank or missing basis prints a dollar): fixed in the fix
    round. This corrects the T3 line above and commit 46d3da2, whose "a caller that omits
    it fails loudly" held only for direct `fmt_usd` calls, which the typed-cell contract
    now forbids in tables.
  - B3 (T4 item 1 prescribes `attempt_history.join_kits`, which hands every kit ledger to
    `events()` in full T+1 times with no size check, against PLAN D5's `MAX_LEDGER_BYTES`):
    a brief defect, recorded below. T4 honours D5 as follows. Before calling `join_kits`
    for a kits dir, `os.stat` each kit's ledger file at `kit_contract.open_ledger(kit_dir,
    store=<ns>/attempts).events_path`; the constructor only validates the name and composes
    a path, which was verified by reading `AttemptLedger.__init__`. If any file exceeds
    `MAX_LEDGER_BYTES`, skip that whole kits dir with a note naming the kit and the size.
    `join_kits` has no per-kit exclusion, and its coverage must come from the owner, so
    rebuilding it per kit would copy owner logic.
  - B4 (T7 trips a third guard, and there is a trap): see the T7 note below.
  - S1 (`fmt_count` truncates `0.9` to `0` and `True` to `1`): fixed in the fix round.
  - S2 (`render_page` does not contain a failure, so one malformed block kills the build):
    fixed in the fix round.
  - S3 (the T4–T7 briefs say "through `fmt_usd(...)`", which predates T3's typed cells): the
    typed-cell contract in the T3 notes supersedes that wording in all four briefs, and the
    semantics (the basis always beside the dollar) are unchanged. The fix round adds a
    page-wide tripwire test that fails if a fixture-built page contains `&lt;span` or
    `&amp;lt;`.
  - S4 (chart twins print raw numbers with fixed headers; `_is_number` accepts NaN and
    infinity): fixed in the fix round with a typed-cell template for the twin's value column.
    Standing rule from here on: every figure (dollar, credits, seconds, count, date) lives in
    a table's typed cell or a chart twin, never in `p` or `list` text built with an f-string
    (PLAN R3).
  - S5 (T4 item 5's fixture wording, "finished event carries `cost` with basis
    `estimated`"): the ledger records `cost_usd` plus `cost_source`, and
    `attempt_history.ledger_records` derives the basis, with `estimated` meaning any source
    other than `parsed`. The T4 fixture writes those two fields; a literal `cost` dict
    would be silently ignored. A brief defect, recorded below.
  - S6 (PLAN D4 reads unmapped namespaces "only through the ledger owner with shallow
    stats", while the T6 and T7 briefs read telemetry, journal, evals and prefs "per read
    namespace", which T4 item 3 defines as mapped plus unmapped): the PLAN decision governs.
    T4 introduces one `read_namespaces(ctx)` helper that returns the bounded, ordered list
    (mapped first, then unmapped by name, with the `MAX_NAMESPACES_READ` note). T4's ledger
    facts use the whole list. T6 and T7 use only its mapped entries, and each of those panels
    carries a note counting the unmapped namespaces whose one shallow listing shows that
    panel's store, stating that they are not read (PLAN D4) and that adding the checkout's
    path to the dashboard's `config.json` `checkouts` list maps them. Brief defects, recorded
    below. Case variants matter here: on this machine `…/Developer/…` and `…/developer/…` hash
    to different namespaces, so the real build can show a store as unmapped.
- Three reviewer notes are cheap and plainly right, so the fix round folds them in as
  orchestrator choices (not counted as findings):
  - a known, non-zero, sub-cent dollar never renders as `$0.00`;
  - the engine's source guard also bans `webbrowser`, `os.system`, `os.popen`, `socket` and
    `urllib`;
  - the `docs/PRIVACY.md` sentence "The rule and the test are in place for the day somebody
    turns it on" moves back beside the training store it describes, instead of reading as
    though it meant the dashboard.
- T7 (B4) now faces three guards and one trap, not two:
  - `tests/test_decision_evaluation_manifest.py` and `tests/test_training_data.py` each pin
    the owners that may name the `evals` or `training` store (known since T2).
  - `tests/test_training_data.py::test_no_production_path_calls_the_capture_hook` asserts
    `release_gate.py` is the only `bin/*.py` that names `training_data` at all. T7's
    required `training_data.status(...)` call trips it.
  - The trap: `tests/test_workflow_eval.py::test_nothing_in_the_repository_reads_the_policy_file_automatically`
    fails if any other `bin/*.py` contains `workflow_eval.POLICY_FILE`. The dashboard never
    spells it, fixtures included; the owners' report functions take `prefs_dir` and resolve
    the file themselves.
  - Plan for T7, still the default put to the user: add `dashboard.py` to each guard's
    expected set with a comment. Because T7's `synthetic_world` writes evals fixtures, the
    comment says "reads every checkout's store through the owner, and writes one only as a
    temp-root fixture", not "read-only consumer". The capture-hook guard's companion
    assertions (no `capture_hook`, `collection_scope`, `persist(` or `snapshot(`) are
    extended to `dashboard.py`, so a second importer is pinned to the same read-only use.
- Budget honesty: the fix round is an implementer dispatch with no `outcome:` line, so the
  budget grammar cannot count it (the graph-convergence `P34fix` precedent). Counted by hand
  it is the run's seventh implementer dispatch against the cap of 22.
defect: T4 kind=contradictory-acceptance
defect: T4 kind=stale-pin
defect: T6 kind=contradictory-acceptance
defect: T7 kind=contradictory-acceptance

## P1 fix round — contract changes for T4–T7

The fix round changed `bin/dashboard.py`, `tests/test_dashboard.py` and `docs/PRIVACY.md`
(with its generated mirror) and touched no owner. What follows is the contract later panels
build on. Where it differs from a T4–T7 brief's wording, this section wins, and the brief's
semantics stay the same.

- **Namespace classes say how complete they are (F1).** `model["classes"]` keeps its row lists,
  `mapped` (namespace, checkout, kind, stores) and `unmapped` (namespace, stores), and adds
  four things. `listing` is one of `LISTING_STATES` (`complete | truncated | failed | absent`).
  `counts` maps each of `CLASS_NAMES` to `{"count", "qualifier"}`, with the qualifier drawn
  from `COUNT_QUALIFIERS` (`exact | lower_bound | unknown`). `residue` is now `{"count",
  "qualifier", "sample"}`. `by_checkout` lists, for each checkout, whether its namespace is
  `mapped`, definitively `absent`, or `unknown`. `count` is None exactly when the qualifier is
  `unknown`, and a lower bound of 0 is always `unknown`.
  - Mapped namespaces are looked up by name with `os.lstat`, outside `MAX_NAMESPACES_LISTED`,
    so the mapped rows are complete whenever the lookups succeeded, however the listing went.
  - The listing loop skips every expected name, not only the mapped ones. So an expected name
    is never counted as unmapped or residue, and a link at an expected name is noted once.
  - A data home that cannot be examined (for example, an unsearchable parent) is `unknown`,
    never `absent`.
- **Showing a class count.** Read it only through `class_count(classes, name)`. `len()` of a
  class list is what the listing saw, and that is not the count when the listing was cut or
  failed. T4's residue line takes its number from `class_count(classes, "residue")`: a lower
  bound reads "at least N", and an unknown count renders the word, never a 0. T6 and T7 each
  count the unmapped namespaces whose listing shows their store (review finding S6). That
  count comes from the listing, so it carries the unmapped qualifier: "at least N" when the
  listing was cut, and unknown when it failed.
- **Qualified count cell.** `{"fmt": "count", "value": n, "qualifier": q}` renders as `N`,
  `at least N`, or the styled `unknown`. A `count` cell without a `qualifier` is `exact`, as
  before. `fmt_count` never truncates. A bool renders as `True`/`False`, an int as its
  digits, and a finite float as its own shortest text (`2.0` gives `2`, `0.9` gives `0.9`).
  Anything else, a string included, renders as its own escaped text and is never
  reinterpreted as a number.
- **Sentences that carry a figure or the styled unknown.** A `p` block may carry `parts`
  instead of `text`: a list of plain values and typed cells, each rendered exactly once
  through `_render_cell`. This is how the namespaces counts line holds `at least N` and the
  `unknown` span. It extends the standing rule that a figure lives in a typed cell, never in
  f-string text.
- **Dollars (F2, F7).** A `usd` cell needs a non-blank `basis`. With none, or a blank one, the
  amount renders WITHOUT `$`, followed by the label `basis missing`. `None` still renders as
  `unknown` alone. A known non-zero amount that two decimals would show as `0.00` renders
  its own digits instead (`$0.004`, and `$-0.004` for a negative). Zero stays `$0.00`.
  `_finite_float` now also treats an int too large for a float as not finite, so such a value
  renders as its own text instead of raising.
- **Charts (F6).** Only a finite real number reaches the geometry. NaN and ±Infinity draw
  nothing, break nothing else, and appear in the twin as their own text. `svg_bars` and
  `svg_sparkline`, and their blocks through the same keys, take two optional parameters:
  - `value_header` (default `"value"` for the sparkline; for `svg_bars` the default is
    `value_key`, the header it printed before, which differs from the brief's literal
    `"value"`);
  - `value_cell`, a typed-cell template such as `{"fmt": "usd", "basis": "est."}`. T6's
    dollar sparklines must pass one, so every twin figure carries its basis.
- **Rendering failures are contained per panel (F4).** Two public functions changed:
  - `render_build(model, home)` returns `(page, model)`. A panel whose blocks or chrome raise
    becomes a fallback section: its id, its escaped title and "this panel could not be
    rendered (<ExceptionType>)". That note reaches the page-wide notes, the bounds section
    (whose body is rebuilt by `_bounds_blocks`) and build.json. The panel's `summary`
    becomes "could not be rendered (see notes)".
  - `render_page` wraps `render_build`, and `assemble_build` now builds the receipt after the
    page.

  Malformed block fields render as their own text instead of raising (`_as_list`, `_as_row`,
  `_as_pair`, `_field`). A builder's `notes` given as a bare string is kept as one note.
- **Standing tripwires every later task re-runs.**
  - `PageWideEscapingTests` (F5) fails if a page built from `synthetic_world` holds
    `&lt;span` or `&amp;lt;`. Never store formatter output as a cell, list item or `p` text.
  - The engine source guard (F8) now also bans `webbrowser`, `os.system`, `os.popen`,
    `socket` and `urllib`.
- **The receipt's `classes`, pinned for T8's skill:** `{"listing": …, "mapped": {"count",
  "qualifier"}, "unmapped": {"count", "qualifier"}, "residue": {"count", "qualifier",
  "sample"}}` and nothing else. The terminal summary follows the page's rules: `N`,
  `at least N` or `unknown` for each class, and "data home absent — no namespaces" for an
  absent data home.

- Orchestrator verification of the fix round, run from the repo root:
  - the dashboard suite, the T2 and T3 verify blocks (their shared full-suite step run once
    at the end), the `sum(` grep, and `docs_build`, `copilot_docs`, `sync_codex_surfaces` and
    `release_gate` `check`, then the full suite with an isolated data home: all exit 0;
  - an independent probe through `main(["build", …])`: listing cap 0, data home at mode 0300
    and 0000, an absent data home, basis-less and blank-basis `usd` cells, `fmt_count` on
    floats and bools, sub-cent dollars, NaN and infinity in both charts, a typed `usd` twin,
    and a registered panel whose chart renderer raises a sentinel. The sentinel never
    appears; the fallback section, the bounds line and the receipt note do.

  My first probe run failed on a true statement. With `--no-git` the working directory (the
  real repo) is the primary checkout, and the page rightly said it has no namespace in the
  synthetic data home. Re-run from inside the synthetic checkout, the probe passed.
agent: P1fix id=a224ace9a6e243f0d role=implementer model=opus
reviewer: P1 model=opus findings=10 confirmed=10 result=accepted

## T4 — attempts panel

- No owner-shape delta against `bin/attempt_history.py` or `bin/attempt_ledger.py`: every
  function, field and label the brief and the P1 fix round named (`join_kits`, `summarize`,
  `COST_BASES`, `DURATION_BASES`, `AttemptLedger.events`/`.open_attempts`/`.corrupt`,
  `attempt_ledger.STORE`/`EVENTS_FILE`/`CLAIMS_DIR`, `kit_contract.open_ledger`) matched on
  read. S5's reading (a ledger's `cost_usd`/`cost_source`, basis `estimated` for anything but
  `parsed`) and B3's reading (`open_ledger`'s constructor only validates the name and composes
  a path, so a size check can call it before ever reading the file) both held exactly as
  written; the fixture and the oversize pre-check in `_kits_dir_oversized` and
  `_ledger_fact_rows` rely on that.
- `read_namespaces(ctx)` is the S6 helper: mapped rows (carrying `checkout`/`kind`) first, then
  unmapped rows (carrying only `namespace`/`stores`) by name, each tagged `"mapped": bool`,
  bounded by `MAX_NAMESPACES_READ` with one cap note when cut. T4's ledger facts
  (`_ledger_facts_blocks`) read the whole list; T6 and T7 are told to use only the mapped
  entries.
- The `store` passed to `attempt_history.join_kits` and read directly for ledger facts is the
  same path either way, `<data_home>/<namespace>/attempts` (`attempt_ledger.STORE`), using
  the namespace `classify_namespaces` already resolved for that row -- for a `codex-kits` row
  this is `project_namespace(checkout/"tasks"/"kits")`, which is exactly what
  `kit_contract.open_ledger` resolves to via `attempt_ledger.kit_repo_root` for a kit under
  `tasks/kits/<slug>`. Verified directly: a synthetic kit written under a mapped `tasks/kits`
  namespace shows up as a second "History for ... (tasks/kits)" target
  (`AttemptsHistoryTests.test_codex_kits_root_is_a_second_history_target_with_its_own_label`).
- `synthetic_world` gained, for this task: a second, ledger-less kit `notes-kit` whose
  `NOTES.md` carries one `pass` and one `blocked` outcome line; a third demo-kit ledger record
  (`T3`) whose finished event carries `cost_usd`/`cost_source="estimated"`, so the cost-by-basis
  table has a non-empty basis to show beside the untouched no-cost `T1`; and one corrupt line
  appended to the unmapped namespace's own ledger file, through the same
  `safe_paths.confined_append_bytes` path `AttemptLedger.append` itself uses. The over-size-
  ledger case stayed test-only, per the brief: two dedicated tests
  (`AttemptsHistoryTests.test_oversize_kit_ledger_skips_that_historys_join_and_is_never_opened`,
  `AttemptsLedgerFactsTests.test_oversize_ledger_row_is_skipped_never_read_and_others_still_show`)
  grow a ledger file to `MAX_LEDGER_BYTES + 1` bytes and `chmod 0` it before building, proving
  the skip comes from `os.stat` alone and the file is never opened for read.
- Verify run from the repo root: the `sum(` grep, `tests/test_dashboard.py` alone, the task's
  own `python3 -` probe, and the full suite under an isolated `POLYTROPOS_DATA_HOME` all exited
  0 (exact counts are not quoted here since they change with each retry -- see the run's own
  Verify output for the number that applied to it).

### T4 retry (attempt 2) — red-team and reviewer findings, fixed

- R1 (containment). `_one_ledger_fact` no longer builds its kind histogram from the raw `kind`
  value: every event's `kind` goes through the new `_kind_label` first (below), which is always
  a short, hashable string, so a dict- or list-typed `kind` (a malformed or tampered line) can
  no longer raise `TypeError` from being used bare as a dict key. `ts` goes through the new
  `_safe_ts`, which reads a non-string `ts` as unknown rather than stringifying it into
  something that looks like a real timestamp. `_ledger_fact_rows`'s per-ledger `try/except`
  widened from `(safe_paths.SafePathError, attempt_ledger.LedgerError, OSError)` to a bare
  `Exception`, naming only the exception type -- one bad ledger is a note for that row, every
  other ledger in the table still renders. Inside `build_attempts_panel`, the history section,
  the ledger-facts section and the residue line are now each built through a new
  `_guarded_section` helper with their own `try/except`; a failure in one produces a note
  naming that section and the exception type and leaves a one-line fallback block in its place,
  and the other two sections are unaffected (verified directly: patching each of
  `_ledger_facts_blocks` and `_residue_line_block` to raise a sentinel-text `RuntimeError` left
  the sentinel text off the page and the other two sections rendering their real content, and
  the same repro for the corrupted `kind` line the red-team found -- appending a `{"kind":
  {"n": 1}}` event to the mapped namespace's `demo-kit` ledger -- no longer collapses the panel
  to the "could not be built" stub). Tests: `AttemptsLedgerFactsTests
  .test_a_malformed_kind_in_the_mapped_or_unmapped_ledger_never_blanks_the_panel`,
  `AttemptsPanelSectionGuardTests.test_a_raising_section_is_a_note_naming_the_section_the_others_still_render`.
- R2 (bounded kind rendering). New module constants `KIND_SHAPE_RE` (the dotted-lowercase-words
  shape every kind `attempt_ledger.py` itself writes actually has -- `run.started`,
  `attempt.finished`, `task.projected`, …), `MAX_KIND_CHARS` (40, twice the longest real kind
  with room for one more segment) and `OTHER_KIND_LABEL` ("other kinds (not rendered)"), plus
  `_kind_label(kind)`, which renders a kind only when it matches both, and counts everything
  else -- a non-string, an over-length string, one that does not look like a kind this ledger
  writes -- under the fixed label instead. Test:
  `AttemptsLedgerFactsTests.test_a_long_or_markup_kind_is_counted_under_the_other_kinds_label_and_never_rendered`.
- R3 (absent/empty renders as text, never a zero). Reverted the attempt-1 narrowing of
  `ClassificationCompletenessTests.test_an_absent_data_home_renders_absent_never_zeros` back to
  its original page-and-stdout-wide scope -- that narrowing was the wrong fix; the right one is
  that nothing on the page or in the terminal ever prints "0 mapped"/"0 unmapped"/"0 residue"
  for an absent OR an empty-but-existing data home. `_residue_line_block` now has three
  branches: `classes["listing"] == "absent"` -> "No data home, so no residue namespaces to
  count." (no count at all); an exact `class_count` of zero -> "No residue namespaces
  (heuristic: …)." (no digit); anything else -> the qualified count cell as before, so
  "30 residue namespaces (…)" and "at least 4 residue namespaces (…)" are unchanged. The new
  `_is_exact_zero(entry)` helper is also used by `build_namespaces_panel` (a `complete` listing
  whose mapped/unmapped/residue are all exact zero now renders "Data home <path>: empty — no
  namespaces." instead of the "0 mapped · 0 unmapped · 0 residue." line) and by `summary_lines`
  (the matching "namespaces: data home empty — no namespaces" line) -- a zero for ONE class
  inside a non-empty census (`"1 mapped · 0 unmapped · 30 residue"`) is untouched; only the
  all-zero case takes the new sentence. Tests:
  `ClassificationCompletenessTests.test_an_absent_data_home_renders_absent_never_zeros` (scope
  restored) and the new
  `ClassificationCompletenessTests.test_an_empty_but_existing_data_home_renders_text_never_zeros`.
- R4 (stale citation). This section now cites tests by name only, never by line number, in
  both the original entry above and this one.
agent: T4 id=a354c8e19bbc8cdae role=implementer model=sonnet
agent: T4 id=ac82545e9c21ffbec role=verifier model=sonnet findings=1 confirmed=1 result=accepted
agent: T4 id=ade756007d059b4e8 role=red-team model=sonnet findings=2 confirmed=2 marginal=2 result=accepted

- T4 adjudication. The verifier passed T4, and my own verify run was green. There are four
  findings; together they are T4's one retry.
  - Red-team break 1, confirmed and reproduced by the orchestrator: one ledger line whose
    `kind` is a list or dict makes `_one_ledger_fact` raise `TypeError`. That exception is
    outside the per-row except, so `build_model` replaces the whole attempts panel with its
    "could not be built" stub. On the fixture the panel shrank from about 5.4 KB to 316 bytes,
    healthy primary-checkout history included, and the note names no namespace. The fix
    contains a failure per row and per section.
  - Red-team break 2, confirmed: a raw `kind` string reaches the page verbatim and unbounded.
    It is escaped, but it is free text from a tampered file (GUARDRAILS: free text that is
    not a title, name, label or note stays off the page, and PLAN D5 bounds everything). The
    fix renders only short, name-shaped kinds and counts every other kind without rendering it.
  - Verifier finding, confirmed: a NOTES line cited `tests/test_dashboard.py:1815` for a test
    that sits elsewhere. From now on NOTES cites tests by name, not by line.
  - Orchestrator finding, not on any agent line. The implementer narrowed the P1 fix round's
    absent-data-home guard so that the attempts panel's residue line could print
    "0 residue namespaces" for a data home that does not exist. That runs against GUARDRAILS
    ("absence … never `0`"), the P1 fix-round contract ("absent … the page renders the word")
    and PLAN Done-means 2, whose build over an empty `mktemp -d` data home must render every
    absent state as text. The same probe showed the namespaces panel printing
    "0 mapped · 0 unmapped · 0 residue" for an empty but existing data home. The fix restores
    the guard to page-wide scope, extends it to the empty data home, and renders both states
    as text. A zero count of one class inside a non-empty census stays a count.
agent: T4 id=a354c8e19bbc8cdae role=implementer model=sonnet
outcome: T4 model=sonnet attempts=2 result=retry-pass review=revised run=2026-09-25-7e3a
