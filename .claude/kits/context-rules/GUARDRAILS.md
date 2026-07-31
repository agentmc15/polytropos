# context-rules — kit guardrails

Kit-scoped: these fences bind this kit's tasks only. Global invariants live in CLAUDE.md.
(This kit is the first to keep its fences here instead of appending them to global CLAUDE.md —
that relocation is the kit's whole point.)

- **Relocation is verbatim or it is a defect.** Never reword, trim, "modernize", or merge any
  guardrail text protecting real money (live `~/.copilot` AI Credits), live CLIs
  (`~/.codex`, `~/.claude`), or user data — in either repo. The only sanctioned transformation
  is moving bytes unchanged and adding the pinned provenance header.
- **Never hand-edit an aesop-fenced file.** In `/path/to/aesop`,
  everything inside `<!-- aesop:begin -->` fences (`CLAUDE.md`, `AGENTS.md`, `GUARDRAILS.md`,
  `.github/`, `.codex/`, `.cursor/`, `.vscode/`, `.claude/`) is compiled output. Edit
  `aesop.yaml` only, then `node dist/index.js compile`, and `node dist/index.js sync` must
  print `clean: disk matches the manifest.` before the task may claim done.
- **NEVER invoke the real `copilot`/`codex`/`claude` CLI** from any task, test, or verify
  command, and never read or write `~/.claude`, `~/.copilot`, or `~/.codex`. Never re-install
  or refresh the plugin.
- **The plugin is live: skill edits are BODY-only.** YAML frontmatter of every skill stays
  byte-identical. The architect/execute shared kit contract must survive in BOTH files —
  layout, task fields, status vocabulary `pending | in-progress | done | blocked`, phase
  headings, `depends:`/`independent:`, model-overrides-frontmatter. T5 is the only task that
  may touch `skills/`.
- **The migration script stays kit-local.** `split_guardrails.py` lives in this kit dir, never
  in `bin/`; no pre-existing `bin/` or `tests/` file is edited by this kit (the ONE new test
  file is `tests/test_guardrails_layout.py`).
- **Never patch outputs to satisfy checks.** If `split_guardrails.py check` fails, a sentinel
  is missing, or the suite goes red: stop, roll back (`git checkout -- CLAUDE.md` + delete
  generated files; in aesop `git checkout -- .`), and report. Editing a GUARDRAILS.md, a
  sentinel string, or a pinned constant to force green is a defect.
- **Suite green at every task boundary**: `python3 -m unittest discover -s tests` (baseline
  1017 tests OK, 2026-07-24). Verify commands run from the repo root; use the
  `discover -s tests -p '<file>.py'` form (dotted-module form is broken on this machine).
- **No commit, no push, in either repo.** Do not create README/docs files; NOTES.md is
  execute-owned.
