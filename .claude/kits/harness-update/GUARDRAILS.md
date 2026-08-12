# harness-update — kit-scoped fences

These bind only while harness-update tasks run. The repo Invariants in CLAUDE.md apply on
top, always.

- **Never a write under `~/.claude` — the remedy is printed, never executed.** That is
  the Claude side of this engine, whole: not in `check`, not in `apply`, not in any test,
  not behind any flag. The standing repo rule ("repo code never touches `~/.claude`") has no kit
  exception here; the sanctioned refresh path is the user (or the session, on the user's
  explicit go-ahead) running the printed `claude plugin ...` commands themselves.
- **Never invoke the real `claude` / `copilot` / `codex` / `gh` CLI** from any code path,
  test, or verify command in this kit. The engine's writers are Python function calls into
  `harness_select.py` and the sync modules — never a shelled-out harness binary.
- **Tests and demos touch temp fixture trees only.** Every home dir in a test is a
  `tempfile.TemporaryDirectory()` passed through an explicit flag; `Path.home()` /
  `expanduser` may appear only in argparse defaults and `cmd_*` handlers (the
  `codex_usage.py` seam convention), and the source-introspection test enforces the pure
  layer stays clean of `Path.home`, `subprocess`, and `urlopen`.
- **Reuse, never fork.** `bin/plugin_staleness.py`, `bin/harness_select.py`,
  `bin/sync_pricing_refs.py`, and `bin/sync_codex_surfaces.py` are read-only to this kit —
  call them via the sibling-module loader. If a signature or return shape disagrees with a
  brief, the module is authoritative: stop, adapt the summary layer only, and record the
  delta in NOTES.md.
- **No hardcoded prices, model ids, credit values, or dates** in the engine, the skill, or
  the tests beyond fixture-local synthetic values. The three pricing files stay the only
  numeric sources of truth; `cached_date` is always read from the data file at run time.
  T4 edits the docs snapshot by deriving every cell from `data/pricing.copilot.json` — a
  number that cannot be traced to a data-file field is a stop-and-report, never a guess.
- **Codex no-clobber is law on the user-editable channels.** `AGENTS.md` and
  `codex/skills/<name>/` are never force-overwritten: `skip-differs` results are surfaced
  verbatim and preserved, and nothing in this kit deletes anything under a home dir.
  `~/.codex/prompts/*.md` are plugin-generated deprecated mirrors — an overwrite-in-place
  channel exactly like Copilot's files: every rewrite of a differing destination must be
  listed and labeled in apply's output, never silent, and the "preserved" wording may only
  appear when something actually was. Copilot's inherited overwrite-in-place semantics
  must be stated in apply's output, not hidden. [Amended at P2 review — the original
  blanket fence mis-stated `install_codex`'s prompts semantics; `defect:`
  kind=stale-plan-decision logged in NOTES.md.]
- **Honesty labels are load-bearing.** "not installed" is absence, not failure; pricing
  age > 60 days is "re-verify against source", never an auto-refresh; the codex partner
  doc's missing snapshot is by-design, never drift. Softening or dropping any of these
  labels is a defect even if tests stay green.
