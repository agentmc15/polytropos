# docs-site — kit-scoped guardrails

These fences bind every docs-site task, verifier run, reviewer pass, and declared-role
dispatch. They are kit-scoped law; the repo CLAUDE.md Invariants stay the always-on rules.

## Generated content

- **Never hand-edit a generated page.** Everything under `docs-site/skills/` and
  `docs-site/deep-dives/` is written ONLY by `python3 bin/docs_build.py build`. A wrong
  sentence there is fixed in its source (a SKILL.md, a `docs/*.md`, a
  `docs-src/fragments/**` file, or the renderer in `bin/docs_build.py`) and rebuilt.
  Hand-patching a generated page "to make a test pass" is a defect even if the suite
  goes green.
- The generator is **deterministic and offline**: no `Path.home`, `subprocess`,
  `urlopen`, `random`, or wall-clock reads, ever (introspection-tested). It reads only
  committed repo content — never a home dir, never a gitignored store (`journal/`,
  `memory/`, `telemetry/`, `trends/`, `prefs/`, `benchruns/`). The public site renders
  committed content only.
- Byte-stability is part of the contract: UTF-8, LF, one trailing newline, sorted
  iteration. If two consecutive `build` runs differ, that is a bug to fix before
  anything else.

## Skill files (runtime behavior, not prose)

- **SKILL.md edits are additive-first.** Before deleting or rewording ANY existing
  line, run `grep -rF '<a distinctive 6+ word phrase from the line>' tests/` — a hit
  means the line is a test-pinned contract: keep it verbatim and put the depth
  elsewhere. Never edit the asserting test to license a skill edit.
- Never remove or soften safety/honesty lines: root-resolution proofs, placeholder
  rejects, "read-only" declarations, "never from memory"/"never invent" rules, refusal
  fallbacks, burn-proxy-not-a-bill labels.
- Respect the D1 budgets (PLAN.md): engine-wrapper skills ≤ ~900 words of body;
  `architect`, `execute`, `repo-bench` may only shrink. The string `docs-site` never
  appears in any SKILL.md (test-enforced).
- Never touch the generated mirrors `skills/route/references/pricing.json` and
  `skills/fable-check/references/pricing.json`, nor
  `skills/architect/references/roles/*`.
- Editing any of the seven Codex stems mirrored into `codex/prompts/` (architect,
  effort, escalate, frontier-check, journal, route, usage) requires
  `python3 bin/sync_codex_surfaces.py build` in the same task, staged together.

## Numbers, facts, and honesty

- **No price, ratio, plan allowance, model id, or cached date is ever hardcoded** into
  the generator, a fragment, or a hand-authored site page. Name tiers, link the pricing
  file on GitHub, or show the engine command that prints current numbers. (Deep-dive
  mirrors carry their sources' labeled snapshots — that rides with the source, which
  this kit never edits.)
- **No fabricated facts in fragments or hand pages.** Every command, flag, subcommand,
  and invocation form shown must exist in the skill's SKILL.md, the named `bin/` engine
  source, or the harness docs (`docs/COPILOT-HARNESS.md`, `docs/CODEX-HARNESS.md`,
  README, `docs/GUIDE.md`). Reading engine argparse source is the sanctioned way to
  learn flags — executing engines that read real home dirs is not.
- `data/pricing*.json` are read-nothing surfaces for this kit: not edited, not parsed
  by the generator.

## CLIs, network, and dependencies

- Never invoke the real `claude`/`copilot`/`codex`/`gh` CLI from any task, test, or
  verify command.
- pip is allowed in exactly two places: CI (the workflow) and the T17 throwaway venv in
  a temp dir. Never `pip install` into system Python, never inside the repo tree, and
  never as a dependency of `bin/` or `tests/` code — those stay stdlib-only, unittest
  only, no pytest.
- Only T3 touches `.github/`; the kit creates exactly one workflow file.
- `copilot/aesop.yaml`, `copilot-docs/**`, `.claude-plugin/**`, `.codex-plugin/**`, and
  all `docs/*.md`/`docs/*.html` sources are read-only to this kit (T16's README/SETUP
  insertions are the only pointer edits outside `docs-site/`/`docs-src/`).

## Always run before claiming done

- The task's own verify command, from the repo root, with its real output pasted.
- `python3 -m unittest discover -s tests` — the FULL suite (baseline: 2639 tests, OK,
  ~103s). Dozens of content-contract tests guard skill text; the full run is the only
  honest tripwire.
- After any task that changed a source the generator reads:
  `python3 bin/docs_build.py check` must exit 0.
- CLAUDE.md stays under its 16000-byte ceiling (`tests/test_guardrails_layout.py`) —
  nothing in this kit may add to CLAUDE.md; its docs-site invariant is already placed.

## Safe drift-probe recipe (verifier/reviewer)

To prove the drift guard fires WITHOUT touching tracked files: copy the inputs to a
temp dir, mutate the copy, run check against it, expect nonzero, delete the copy —

```bash
TMP="$(mktemp -d)" && cp -R skills copilot codex docs docs-src docs-site bin "$TMP/" \
  && printf '\nmutation-probe\n' >> "$TMP/skills/route/SKILL.md" \
  && ! python3 bin/docs_build.py check --repo-root "$TMP" && rm -rf "$TMP"
```

Never mutate a tracked file in place to test the guard. Close every verification run
with `git status --porcelain` and treat any unexpected tree change as your own defect
to restore byte-for-byte and report.
