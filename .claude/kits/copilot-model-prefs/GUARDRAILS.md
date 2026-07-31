# copilot-model-prefs — kit guardrails

Relocated verbatim from the global CLAUDE.md by the context-rules kit (2026-07-24).
Kit-scoped: these fences bind this kit's tasks only. Global invariants live in CLAUDE.md.

  For `copilot-model-prefs` specifically: Copilot CLI ONLY — pins/excludes change WHICH
  model a tier resolves to, NEVER WHEN a tier is used (no force-frontier switch, no
  tier-promotion knob, escalation trigger and tier walk-order untouched) and nothing
  under `codex/`, `skills/` (Claude side), or `.claude-plugin/` changes; the prefs file
  `prefs/copilot.json` is gitignored USER DATA (root-anchored `/prefs/` — the leading
  slash is load-bearing) — never committed, never auto-created, no sample file shipped,
  and no task/test/verify ever creates or reads a real prefs file at the default path
  (temp `--prefs` fixtures or `--no-prefs`, always; nothing is applied to the real
  `~/.copilot`); NEVER invoke the real `copilot`/`codex`/`claude` CLI from any task,
  test, or verify command (command lines WRITTEN into bundle bodies are runtime
  instructions the kit never executes); all prefs logic (load, per-tier flag-over-file
  pin merge, exclude union, validation, conflict, `resolve_tier`) lives ONLY in the new
  `bin/copilot_prefs.py`, reused by both engines via the pinned importlib loader — never
  duplicated; engine changes are ADDITIVE only — `escalation_ladder`/`run_task` gain
  default-`None` `prefs` kwargs (result gains only `prefs_notes`, and only when prefs are
  active), `run` gains only `--pin TIER=MODEL_ID`/`--exclude MODEL_ID`/`--prefs`/
  `--no-prefs`, `copilot_pricing.py` gains only the `prefs` subcommand, and with no prefs
  flags and no prefs file every existing flag, signature, output shape, exit code, and
  demo/dry-run byte-stays (`status`/`review` and `models`/`est`/`runway`/`knobs`
  untouched); honesty is absolute — a pin-vs-exclude conflict is a hard exit-2 error from
  any source combination (never a silent winner), a malformed prefs file degrades to a
  note and a stale entry is skipped with a note (never a crash), an exclusion-emptied
  tier is skipped and an emptied frontier means the ladder tops out lower (stated, never
  a fabricated rung), and the initial dispatch errors rather than silently jumping tiers;
  bundle edits are BODY-only to exactly the four skills + four agents
  (`route`/`architect`/`escalate`/`frontier-check`) plus one pinned execute-skill
  sentence — frontmatter byte-intact, no roster change (`copilot/aesop.yaml`,
  `copilot-instructions.md`, `lessons-loop`, and every other bundle file byte-untouched),
  new paragraphs id-free (`SkillNoModelIdTests` sweeps skills; agents follow the same
  discipline) and quoting only the new argparse surfaces; test edits are additive at
  pinned append seams only in `tests/test_copilot_execute.py`,
  `tests/test_copilot_pricing.py`, and `tests/test_copilot_bundle.py` (every pre-existing
  class/method/constant byte-intact; new tests otherwise in
  `tests/test_copilot_prefs.py`); no hardcoded prices or real model ids anywhere new
  (tier vocabulary, `PREFS_SCHEMA_VERSION`, the `prefs`/`copilot.json` names,
  flag-grammar strings, pinned message text, and synthetic `fake-*` fixture ids are the
  sanctioned literals — doc examples use placeholders and point at `models --json`); zero
  `Path.home()` and zero `subprocess`/network imports in `bin/copilot_prefs.py`;
  sanctioned edit targets are ONLY `bin/copilot_execute.py`, `bin/copilot_pricing.py`,
  the three test files above, the nine bundle files above, and `.gitignore` (the pinned
  two-line `/prefs/` append), with new files `bin/copilot_prefs.py`,
  `tests/test_copilot_prefs.py`, and `docs/COPILOT-PINS.md` — CLAUDE.md and README.md are
  NOT executor edit targets (the architect pre-made the run-line and this fence); no
  prefs flags on `review`, no prefs-writing CLI, no `COPILOT_MODEL`/settings.json wiring,
  no prefs-aware `models` row markers, no Codex-/Claude-side prefs parity (future kits);
  no commit, no push.
