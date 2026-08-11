# GUARDRAILS — repo-bench (kit-scoped fences; read with PLAN.md before any task)

Absolute rules (money / live tooling / user data — no judgment calls):

- **NEVER invoke the real `claude`/`copilot`/`codex`/`gh` CLI from any task, test, or verify
  command** — every dispatch and every `gh` enrichment goes through an injectable runner
  callable, and every test injects a stub (or a temp stub executable via `--claude-bin`).
  `demo`, `plan`, and stub-runner tests are the only sanctioned smokes. No task in this kit
  runs a live benchmark — the tool is built here; its first spend is a user decision later.
- **`run` must be structurally unable to spend without BOTH `--live` and `--max-usd`**, and
  the ceiling is re-checked before EVERY dispatch, judge grades included. Weakening either
  gate — a default ceiling, an implied `--live`, a post-hoc check — is a wrong change even
  if it "works".
- **Target repos are read-only, by construction.** All target access goes through the ONE
  `git_target` choke point with the `READ_ONLY_GIT` allowlist; sandboxes are history-free
  tree extractions under the run dir. Widening the allowlist, bypassing the choke point, or
  building sandboxes any other way (worktree, clone) is forbidden — the rationale is
  PLAN D3, including the solution-leak argument.
- **The solution never reaches the candidate**: no reference-patch or test-blob content in
  any prompt, and fix-test blobs never land in the sandbox the candidate works in (grading
  happens in a copy). The leak tests (T2/T6) are load-bearing — never weaken them to pass.
- **Tests use throwaway fixture repos and temp stores only** — never the real `benchruns/`,
  `prefs/`, any `~/` dir, or a real project checkout. `benchruns/` is written by
  `bin/repo_bench.py` only; envelopes are never hand-authored or backdated (fixture
  `results.json` files in TEMP stores for reader tests are sanctioned — the real store is
  not).
- **Untouchable files:** `bin/claude_execute.py`, `bin/cost_report.py`,
  `bin/routing_scorecard.py`, `bin/bench_routing.py`, `bin/session_cost.py`, their tests,
  every pricing file, every existing skill's YAML frontmatter, `skills/architect/SKILL.md`,
  `skills/execute/SKILL.md`, every existing kit's files. Reuse is importlib-only. If a
  change appears to require touching one, STOP and report.
- No hardcoded prices, price ratios, or real model ids in engine, skill, or tests (fixture
  pricing dicts use obviously-fake ids). Do not commit or push.

Principles with the signal to read (judgment expected, drift is the failure mode):

- **`solved` means tests passed — nothing else, forever.** The signal you've drifted: any
  headline number, ranking, or tie-break that folds judge grades or structural similarity
  into "solved", or a rendering where oracle classes share a column without labels.
  Similarity results always carry their NOT-a-correctness-verdict label; judge results
  always carry their subjective label; an unavailable oracle renders `n/a`, never a zero.
- **Estimates and actuals never blur.** Every dollar carries its basis (`actual` /
  `estimated` / `mixed`); a plan total is "not a bill"; a ceiling stop is stated plainly
  and labels the results `partial (cost-ceiling)`. The signal: a dollar figure printed
  without a basis or label beside it.
- **Below the evidence floor, the verdict says so — loudly, everywhere it renders.** The
  floor can be raised per run, never lowered; `apply` refuses below-floor verdicts
  outright. The signal: any path where a below-floor tier map reaches
  `prefs/repo-bench.json`.
- **Disagreement between the three legs is signal, never noise.** Published prior, observed
  ledger, and this run's measurement stand side by side; when they conflict the card names
  it. The signal you've drifted: an average, a blended score, or a leg silently dropped.
- **Verify commands must be able to fail.** Before claiming done, name the concrete repo
  state that would make each verify clause exit non-zero; if there is none, it is
  decoration — replace it with a content assertion. Never write
  `producer | python3 - <<'PY'` (pipe and heredoc both claim stdin): redirect producer
  output to a file first, then probe the file.
