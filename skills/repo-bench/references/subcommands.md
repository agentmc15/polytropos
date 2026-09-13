# Subcommands and every flag

Detail moved out of `skills/repo-bench/SKILL.md` by roadmap step 22 so the entry point carries the spend law and the relay requirements; the text below is unchanged.

- **`plan`** — `--repo`, `--models` (comma-separated ids or tier words, required), `--mode
  auto|issue-replay|general` (default `auto`), `--limit` (max tasks to mine), `--test-cmd`
  (required for general mode), `--setup-cmd` (build/install step run once per grade template —
  see above; never run by `plan` itself), `--setup-key` (repeatable path whose content keys those
  templates), `--judge` (override the default judge selection), `--commit`
  (base commit; defaults to the repo's current HEAD), `--exclude-subject` (repeatable regex,
  drop matching commit subjects from mining), `--with-gh` (opt-in `gh api` issue-vs-PR-aware
  statement enrichment — see above), `--gh-repo OWNER/NAME` (REQUIRED with `--with-gh`; refuses
  otherwise — see above), `--store-dir` (read-only source for the calibration line above —
  point it at the store your `run`s write to; omitted means the plan card's `## calibration`
  section reports no data rather than reading a default location), `--json`. Prices the whole
  matrix and stops — no `--live`, no spend, ever, on this subcommand.
- **`run`** — same mining flags as `plan` (including `--exclude-subject`, `--with-gh`,
  `--gh-repo`, `--setup-cmd` and `--setup-key`), plus
  `--store-dir` (where the run lands; defaults to a `benchruns/` store), `--live` and
  `--max-usd` (BOTH required to spend anything), `--claude-bin` (the dispatch binary — point it
  at a stub in any test context), `--keep-work` (keep the per-cell sandboxes instead of
  deleting them after grading, useful for inspecting a run by hand), `--no-full-patch-check`
  (switch off the full-patch diagnostic described above — it is on by default, dispatches no
  model, and costs one extra `--test-cmd` run per false-negative-suspect cell). Without
  `--live --max-usd` it prints the plan and refuses with a non-zero exit.
- **`regrade`** — `--run` (required), `--store-dir`, `--live` and `--max-usd` (BOTH required to
  spend anything, exactly as on `run`; the ceiling is this invocation's own, fresh from $0.00),
  `--claude-bin`, `--judge-seed` (pin the blind slot assignment for every grade in this
  invocation — omit it, which is the default, to keep PLAN D6's per-grade randomization).
  Re-dispatches only the judge grades a cost ceiling stranded, merges them into the run's own
  `results.json` in place, and records this invocation in a `regrades` entry with its own
  ceiling, spend and basis. Without `--live --max-usd` it refuses with a non-zero exit. See the
  section above before ever constructing the `--live` form.
- **`verdict`** — `--run` (required), `--store-dir`, `--goal tiers|daily-driver|both` (default
  `both`), `--min-tasks` (raise the evidence floor for this render only), `--benchmarks`
  (override the published-index file for the D10 published leg), `--kits-dir` (override the
  observed-ledger source; defaults to the target repo's own `.claude/kits` when present),
  `--json`. Renders the tier map and/or daily-driver pick, the per-oracle measurement table,
  and the three-legs comparison — including the below-floor stamp when it applies.
- **`apply`** — `--run` (required), `--store-dir`, `--prefs-path` (override the default
  gitignored prefs location). Reads the named run's verdict, prints exactly what it will write,
  and writes it — or refuses per the rules above.
- **`list`** — `--store-dir`, `--prefs-path`, `--json`. Enumerates the store tolerantly: a
  missing store prints a friendly line, a rogue or malformed run directory gets a note instead
  of a crash, and no dollar figure is invented for a run with no recorded spend (shown as
  `n/a`). Shows, per run: id, repo, mode, candidates, spend and its basis, whether a verdict
  exists, whether it's below-floor, and whether it's the run currently applied to prefs.
- **`demo`** — a fully synthetic end-to-end smoke: fixture git repos, stub dispatch, both
  acquisition modes (issue-replay and general/mutation-repair, each run end to end), all four
  oracles, a rendered verdict including a below-floor example, and a demonstration that
  rewriting the test harness cannot earn `solved` — no network, no real CLI, nothing written
  outside a temp directory. Use this to sanity-check the tool itself, or to show a user what
  the output actually looks like before running anything real.
