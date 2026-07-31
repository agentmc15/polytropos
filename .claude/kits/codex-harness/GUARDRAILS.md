# codex-harness — kit guardrails

Relocated verbatim from the global CLAUDE.md by the context-rules kit (2026-07-24).
Kit-scoped: these fences bind this kit's tasks only. Global invariants live in CLAUDE.md.

  For `codex-harness` specifically: NEVER invoke the real `codex` CLI in any form — it spends
  the user's real ChatGPT-subscription usage limits (or API dollars) and hits the network,
  and a live `~/.codex` exists (`bin/codex_execute.py` takes injectable dispatch/verify
  runners, tests stub or mock every dispatch via temp stub executables and `--codex-bin`,
  and `--dry-run` is the only CLI smoke path); the real `~/.codex` is never read or written
  by any test or verify command — the ONE exception is task T1's bounded read-only research
  peek (the exact `ls`/`head -c` command list is pinned in its brief; JSONL/TOML text only,
  never a `*.db`, never a write, findings recorded as key names/shapes/ids only in
  `.claude/kits/codex-harness/RESEARCH.md`) — everything else uses synthetic fixtures in
  temp `--codex-home` dirs, and at run time `bin/codex_usage.py` reads `~/.codex` strictly
  read-only, JSONL only; `data/pricing.codex.json` is created/edited only by its own tasks —
  the THREE pricing files never merge, no harness reads another's, and during that kit the
  journal invariant stood: `bin/journal_*.py` were never edited and Codex stayed
  counted-but-unpriced there (since superseded — the `journal-augment` kit wires
  `pricing.codex.json` into the journal as a clearly-labeled relative-burn proxy, never a
  bill); GPT-5.6 model ids and subscription
  inclusion are UNCONFIRMED — id corrections land only in `data/pricing.codex.json` (via its
  task's sanctioned RESEARCH.md substitution, reported never silent), and no task invents a
  fast/ultra CLI flag, a price multiplier for them, a plan allowance, or a `runway`
  subcommand; subscription runs are never given an unlabeled dollar figure —
  `billed_usd` stays null and every proxy carries its "not a bill" labeling; bundle files
  under `codex/` carry `{{POLYTROPOS_ROOT}}`, never an absolute path; installs run
  only against temp `--codex-home` dirs during the kit, never write `config.toml`, and never
  overwrite a differing `AGENTS.md`; `bin/harness_select.py` is the one existing script the
  kit may extend (claude-code/copilot behavior byte-stable) and pre-existing test files stay
  byte-untouched except T7's single pinned method in `tests/test_harness_select.py` (new
  tests go in the four `tests/test_codex_*.py` files); no edits to `data/pricing.json` or
  `data/pricing.copilot.json`, no new skills, no aesop/node work, no `codex/aesop.yaml`;
  sanctioned existing-file edits are ONLY `bin/harness_select.py`, that one test method,
  README.md's pinned insertion, and CLAUDE.md's pinned insertions.
