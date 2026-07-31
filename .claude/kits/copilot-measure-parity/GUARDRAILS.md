# copilot-measure-parity — kit guardrails

Kit-scoped fences. Binding for every task in this kit; they do not generalize to other work.

- **Frozen files.** `bin/context_weight.py`, `bin/bench_routing.py`, `bin/copilot_pricing.py`,
  `bin/harness_select.py`, `data/benchmarks.aa.json`, `data/pricing*.json`, everything under
  `skills/` (Claude side) and `codex/`, and every EXISTING file under `copilot/.github/` —
  EXCEPT the two roster sentences in `copilot/.github/copilot-instructions.md` and their
  mirror in `copilot/aesop.yaml`, unfrozen by PLAN.md D10 for T9 only. Everything else in
  both files, including the doctrine sentence, stays frozen.
  This kit only ADDS four bundle files, edits `copilot/aesop.yaml`'s two list blocks, extends
  `tests/test_copilot_bundle.py`, adds the new names to `EXPECTED_SKILLS`/`EXPECTED_AGENTS` in
  `tests/test_copilot_docs_content.py` (PLAN.md D8 — that file is NOT frozen for those two
  constants, and is frozen for everything else in it), and regenerates `copilot-docs/` output
  via the builder.
- **Atomic wiring (PLAN.md D6).** Any task that creates a bundle file adds its
  `copilot/aesop.yaml` line in the SAME task, and runs `python3 bin/copilot_docs.py build`
  before its full-suite verify. Never leave the manifest and the directory tree disagreeing
  at a task boundary.
- **Skill text is tier-worded and id-free.** No pricing-key model id may appear anywhere in a
  SKILL.md (the sweep test enforces it). Model ids appear exactly once per new agent file, in
  its `model:` frontmatter, and must be live `data/pricing.copilot.json` keys.
- **No invented flags or capabilities.** Every command a new surface teaches must exist on the
  engine's real argparse surface — check with `--help` before writing it down. No prefs
  teaching in these two skills (PLAN.md D4). No growth curve, live watch, or ledger role
  evidence promised on the Copilot side (PLAN.md D3).
- **Never invoke the real `copilot` CLI; never read or write the real `~/.copilot`.** The new
  tests are text-contract tests over repo files only.
- **Docs: authored prose is source; generated blocks and artifacts are not** (PLAN.md D9 —
  this rule REPLACES an earlier, factually wrong "builder-only, never hand-edit anything under
  `copilot-docs/`"). `copilot-docs/SKILLS.md` and `AGENTS.md` are hand-authored guides with a
  single builder-spliced inventory block each. Author the per-surface `## <name>` prose
  section by hand, in alphabetical position, matching the existing sections' voice and their
  four bolded subsections exactly. NEVER hand-edit content between
  `<!-- BEGIN GENERATED: ... -->` / `<!-- END GENERATED: ... -->` markers, and never hand-edit
  a pure artifact (`*.html`, `aic-report.json`) — those come only from
  `python3 bin/copilot_docs.py build`, which every task still runs after its edits.
- **Run the full suite from the repo root before claiming any task done**, and do not commit
  or push.
