# sdd-docs-refresh — kit-scoped guardrails

These fences bind every task, verifier run, and reviewer pass of this kit. They are kit-scoped
law; the repo `CLAUDE.md` Invariants stay the always-on rules and win on any conflict.

## Scope: Claude Code only

- Read-only to this kit, no exceptions: `copilot/`, `codex/`, `cursor/`, `copilot-docs/`,
  `data/pricing.copilot.json`, `data/pricing.codex.json`, `data/pricing.cursor.json`,
  `docs/COPILOT-*.md`, `docs/CODEX-HARNESS.md`, `docs/CURSOR-HARNESS.md`, `primitives/`,
  `.github/`, `CLAUDE.md`, `SECURITY.md` (read it; do not edit it — nothing here changes the
  three boundary tools). In shared files (`README.md`, `docs/GUIDE.md`, `docs/REFERENCE.md`,
  `docs/HOW-IT-WORKS.md`) only the Claude text moves; `docs/GUIDE.md` §7 "The other three
  harnesses" stays byte-identical. Every verify command in TASKS.md ends with
  `git diff --quiet -- copilot codex cursor copilot-docs data` for a reason.
- `data/pricing.json` is read, never written — not a number, not a note, not row order. The
  Haiku 4.5 / Haiku 5.5 order is a deliberate dispatch-capability decision recorded in the file's
  own notes and in commit `9b5da6d`; flipping it is the user's call, outside this kit (PLAN D2).
  Consequently `python3 bin/sync_pricing_refs.py --check` must stay at exit 0 throughout; if it
  ever reports drift, a fence was crossed.

## Roster facts: derive, gloss, label

- The current default of a tier is the FIRST row of that tier in `data/pricing.json`. Get it
  from the file (`python3 bin/aesop_bridge.py tiers`, or a one-liner over the JSON), never from
  memory or from another doc.
- Skills, agent files, and role templates carry tier words (`haiku`/`sonnet`/`opus`/`fable`).
  A display name ("Sonnet 5.5") may appear as a gloss beside a tier word or a derivation
  command; a model id (`claude-sonnet-5-5`), a price, a ratio, a threshold, or a date may not.
  `tests/test_roster_currency.py` (T2) guards the sonnet/opus display names; the grep
  `grep -rnE "claude-(sonnet|haiku|opus|fable)-[0-9]" skills/*/SKILL.md .claude/agents/sdd-docs-refresh-*.md`
  must show nothing this kit added.
- A docs price table is a labeled snapshot. Its label moves to the file's `cached_date` ONLY in
  the same edit that makes its rows agree with the file, rows derived by the one-liner in T4's
  brief. Moving a label alone, or rows alone, is a defect even if every test passes.
- Haiku 5.5 is described exactly as: priced (with a separate rate for one request over its
  long-context threshold), not the haiku dispatch default until its row leads its tier. Never
  as "the new Haiku" or "the default".
- The quotation "Fable 5 runs once, at the start; its judgment persists as scaffolding" is
  never edited (PLAN D8). Where the current frontier name is needed beside it, add a gloss.

## Skills are runtime behavior

- Additive-first. Before deleting or rewording ANY existing SKILL.md line, run
  `grep -rF '<a distinctive 6+ word phrase from the line>' tests/`. A hit means the line is a
  test-pinned contract: keep it verbatim. Never edit the asserting test to license a skill edit.
- `skills/setup/SKILL.md`'s example statusline JSON (`"claude-fable-5"`, `"Fable 5"`) is
  test-pinned; do not "fix" it.
- Entry-point ceilings (`tests/test_docs_skill_dispositions.py`): architect ≤ 2800 words of body,
  execute ≤ 3200. Only T2 touches `skills/architect/SKILL.md`; nothing touches
  `skills/execute/SKILL.md`. When `skills/architect/SKILL.md` changes, re-read both against the
  shared kit contract listed in `CLAUDE.md` (layout, task fields, status vocabulary, phase
  headings, `depends:`/`independent:`, model-field override) in the same task.
- The string `docs-site` never appears in a SKILL.md (test-enforced). `skills/architect/
  references/roles/*.md` and `references/routing-evidence.md` are not edited by this kit.

## Generated content is rebuilt, never edited

- `docs-site/skills/**` and `docs-site/deep-dives/**` are written only by
  `python3 bin/docs_build.py build`; `copilot-docs/**` only by `bin/copilot_docs.py build`; the
  marked block of `docs/RELEASE.md` only by `bin/release_gate.py build`; the two pricing mirrors
  only by `bin/sync_pricing_refs.py`. Fix the source, rebuild, stage both together. A wrong
  sentence patched in a generated page is a defect even if the suite is green.
- Tasks that rebuild the site (T2, T4, T5, T7, T8) run strictly serially.
- Hand pages under `docs-site/{index.md,concepts,getting-started,workflows}` are editable but
  must contain no model display name (`tests/test_docs_site_skeleton.py`).

## Docs may not outrun the code

- A sentence of the form "the skill does X" must match the SKILL.md. Known trap: no Claude
  skill states a Fable "refusal fallback"; the docs that claim one are rewritten as operator
  practice or dropped (T4/T5). A claim in `docs/SPEC-DRIVEN.md` or the pitch without a file or
  command behind it is a finding, always.
- Numbers that rot (kit counts, task tallies, test counts, percentages, "N of N") never enter
  new prose. Name the command that prints them. Reviewer grep: `\b\d+ (kits|tasks|tests)\b`,
  `\d+%`.

## CLIs, homes, network

- Never invoke the real `claude`, `codex`, `copilot`, Cursor `agent`, or `gh` CLI from any
  task, test, or verify command. The dispatchability of Haiku 5.5 is NOT re-checked by this kit.
- Never read or write `~/.claude`, `~/.copilot`, `~/.codex`; never re-install the plugin. The
  one home-reading command allowed is `python3 bin/harness_update.py check` in T11 — read-only
  by construction, and its install-drift findings are reported, never acted on.
- New tests are stdlib `unittest`, live-tree, write nothing into the repo, and each carries a
  synthetic negative fixture proving its assertion can fail.

## Commits

- One commit per phase (T6, T10, T11), on `feat/route-experiment`, only after the FULL suite and
  all generator checks exited 0 in that task's own run. Never on `main`; never push; never
  `--amend` a prior commit; never `git add -A` — add the named paths.
- Subject `type(scope): outcome` (≤ ~80 chars, imperative, lowercase after the colon); body in
  prose paragraphs wrapped at 80 columns (why the old state was wrong with evidence; what proves
  the new state; what is deliberately unfinished); verbatim command listings indented two
  spaces; no test counts. Trailer: exactly the attribution the executing session's harness
  mandates (its system reminder states it) — do not invent, do not copy one from an old commit.

## Always run before claiming done

- The task's own verify command, from the repo root, with its real output pasted.
- After any task that edits a skill, a `docs/*.md`, `mkdocs.yml`, or a test:
  `python3 bin/docs_build.py check` (exit 0) and the named test modules.
- Before each commit task: `python3 -m unittest discover -s tests` (full suite),
  `python3 bin/docs_build.py check`, `python3 bin/copilot_docs.py check`,
  `python3 bin/sync_pricing_refs.py --check`, `python3 bin/release_gate.py check`.
- Close every verifier/reviewer run with `git status --porcelain`.

## Safe mutation-probe recipe (verifier/reviewer)

To prove a guard fires WITHOUT touching tracked files, copy the inputs to a temp dir, mutate
the copy, run the check against the copy, expect non-zero, delete the copy:

```bash
TMP="$(mktemp -d)" && cp -R skills copilot codex docs docs-src docs-site bin data "$TMP/" \
  && printf '\nmutation-probe\n' >> "$TMP/skills/route/SKILL.md" \
  && ! python3 bin/docs_build.py check --repo-root "$TMP" && rm -rf "$TMP"
```

For the live-tree tests this kit adds, use their own `NegativeFixtureTests` as the proof, or run
the module against a temp copy of the tree with `python3 -m unittest` from inside the copy.
Never mutate a tracked file in place to watch a test fail. If the tree is touched anyway,
restore it byte-for-byte before reporting, say so, and record it as your own defect — in this
repo a read-only-pinned verifier once destroyed an authored docs section during exactly such a
probe and misreported it as the implementer's.
