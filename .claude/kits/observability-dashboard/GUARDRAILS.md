# GUARDRAILS — observability-dashboard (kit-scoped fences; read with PLAN.md before any task)

These bind only while observability-dashboard tasks run. The Invariants in `CLAUDE.md` apply
on top, always. `CLAUDE.md` itself is never edited by this kit (it is at its byte ceiling);
everything this kit needs to say lives here.

Absolute rules (money / live tooling / user data / concurrent work — no judgement calls):

- **The page can never reach the network, and nothing reads the HTML into a session.** The
  output carries the CSP meta tag `default-src 'none'; style-src 'unsafe-inline'; img-src
  data:` exactly, no `<script`, no `src=`, no `href` to a URL, no `@import`, no `url(`, no
  webfont, no iframe, no form. The skill relays the path and the plain build's summary lines
  (fixed words plus counts; amended 2026-09-27 — it never runs `--json` and never relays a
  note) and never `cat`s, `Read`s or `grep`s `index.html`; it never pastes, publishes,
  attaches, uploads or opens the page — opening it is the user's own action in their own
  browser.
- **Parse, never import — the engine runs code from one tree only (added 2026-09-27; user
  decision 2026-09-26).** The only Python the dashboard imports is its sibling owners under the
  plugin root its own code runs from (`PLUGIN_ROOT/bin` through `_load`/`_mod`, or the
  `plugin_root` seam a test fills with a fixture tree). A checkout's
  `bin/recursive_improvement.py` — or any other file under a discovered checkout, a
  `--checkout` flag, a `config.json` entry, a namespace or a store — is read as TEXT with
  `ast`, never imported, `exec`'d, compiled to run or followed through a symlink. T11's RSI
  projections therefore call `recursive_improvement` from the plugin tree alone, over
  `attempt_ledger.AttemptLedger` objects, and render its output verbatim; when the plugin tree
  has no engine the page says so and projects nothing. Tests never import the RSI branch's
  engine and never touch the RSI worktree: the owner seam is exercised with a synthetic module
  in the owner's documented shape, plus one `skipUnless`-guarded shape test over this
  checkout's own `bin/recursive_improvement.py` once it exists on `main`.
- **NEVER invoke the real `claude` / `codex` / `copilot` / `agent` CLI** from any code path,
  test, verify probe or role dispatch in this kit. The engine's only subprocesses are two
  read-only git verbs, `git rev-parse --show-toplevel` and `git worktree list --porcelain`,
  run in a candidate checkout (never `PLUGIN_ROOT`) through `bin/proc_runner.py` with a
  timeout, both disabled by `--no-git`, and a note (never an error) when either fails.
- **Tests and probes never touch the real data home, the real harness homes or the real
  store.** Every test module carries the `setUpModule` + `mock.patch.dict(os.environ,
  {"POLYTROPOS_DATA_HOME": tmp})` idiom from `tests/test_copilot_execute.py`, builds synthetic
  namespaces in temp dirs, passes `--out-dir`, `--projects-dir` (an empty temp dir) and
  `--no-git` to every `build` it runs, and contains zero `Path.home()`. Every full-suite
  verify runs as `POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 -m unittest discover -s tests
  -v`. The ONE sanctioned real build is Done-means 3 in PLAN.md, run by the orchestrator at
  the end of Phase 3 and reported faithfully; no task's verify block runs a real build.
- **The engine writes only its own store or `--out-dir`, through `bin/safe_paths.py`, at
  `0700`/`0600`.** It never writes, moves, compacts or deletes anything in any other store,
  any namespace (residue included), any harness home or the checkout. `runtime_data.STORES`
  gains exactly one name, `dashboard`, and `.gitignore` gains the root-anchored
  `/dashboard/` rule in the same task.
- **Untouchable files.** `bin/attempt_ledger.py`, `bin/attempt_history.py`,
  `bin/recursive_improvement.py`, everything under `tasks/kits/` (Codex edits these
  concurrently on `feat/rsi-evidence-foundation`; that worktree is never opened or run —
  the branch is read only via `git show feat/rsi-evidence-foundation:<path>` and `git log
  main..feat/rsi-evidence-foundation`); `bin/routing_scorecard.py`, `bin/telemetry_snapshot.py`,
  `bin/workflow_eval.py`, `bin/training_data.py`, `bin/journal_*.py`, `bin/kit_contract.py`,
  `bin/safe_paths.py`, `bin/proc_runner.py`, `bin/redact.py`, `bin/runtime_data.py` beyond
  the one `STORES` append, every `data/pricing*.json`, every generated mirror
  (`docs-site/`, `copilot-docs/`, `codex/prompts/`, `skills/*/references/pricing.json`, the
  marked block of `docs/RELEASE.md`), every existing kit's `NOTES.md`, every skill's YAML
  frontmatter except the new skill's own, and `CLAUDE.md`. A change that seems to require
  one of these is a STOP and report, never an edit.
- **Never fabricate, sum, or soften a figure.** No cell adds two cost bases, two harnesses or
  two owners; no basis-less dollar is printed; a Codex subscription figure always carries
  the owner's "API-equivalent relative-burn proxy, never a bill" label; unknown renders as
  the word `unknown`, absence as the owner's absence label, never `0`, `$0.00` or blank.
  Owners' `labels` and `notes` render verbatim and in full — shortening or dropping one to
  make a table fit is a defect even when every test stays green.
- **Never render transcript, prompt, report, tail or inbox text, and never an unscrubbed home
  path.** The ledger's bounded `report`/`tail` fields, the journal's `inbox` and `signals`
  prose, and any free text that is not a task title, kit name, label or note stay off the
  page; every absolute path under the user's home renders as `~/…`.
- **Residue is counted, labelled as a heuristic, excluded from totals, and never opened
  beyond one shallow listing or deleted.** The leak fix is a separate PR; this kit only
  survives what the leak left behind.
- Do not commit, push, merge or branch from a task.

Principles with the signal to read (judgement expected; drift is the failure mode):

- **The dashboard renders, it does not decide.** The signal you have drifted: a new
  percentage, rate, ranking, classification or "verdict" word on the page that no owner's
  output contains. If a number the page wants does not exist in an owner's card, the page
  says the owner does not report it — it does not compute it.
- **Absent, stale and truncated are first-class states, rendered as text.** The signal: an
  `if not data: return ""` that hides a panel, a `try/except: pass`, or a cap that silently
  drops rows. Every degraded path ends in a note on the panel, in the page's bounds section
  and in `build.json`.
- **Reuse by import; the owner is authoritative.** Sibling modules load through the
  `importlib.util.spec_from_file_location` loader (`bin/` is not a package). When a brief's
  named function, key or label disagrees with the module, adapt the dashboard's adapter
  layer, keep the semantics, and record the delta in NOTES.md — never copy the owner's logic
  into `bin/dashboard.py` and never edit the owner.
- **Bounded means a named constant with a reason.** The signal: a bare number in a loop
  condition, or a scan whose cost grows with something the user did not choose (residue
  count, ledger size). Every cap is a module constant with a comment, and hitting it is
  visible.
- **Generated documentation is regenerated, never edited.** After a source edit
  (`docs/*.md`, a fragment, `README.md`, `SECURITY.md`, the `STORES` tuple), run the
  generator that owns the mirror (`python3 bin/docs_build.py build`, `python3
  bin/release_gate.py build`) in the same task, and confirm each `check` exits 0. A merge
  conflict in a generated file is resolved by regenerating, never by hand.
- **Verify commands must be able to fail.** Before claiming done, name the repo state that
  would make each verify clause exit non-zero; a clause with none is decoration — replace it
  with a content assertion. Never write `producer | python3 - <<'PY'` (pipe and heredoc both
  claim stdin): redirect the producer to a file, then probe the file.
