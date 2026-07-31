# TASKS — context-rules

Repo root: `/path/to/polytropos`. Run all verify commands from
there unless a task says otherwise (T6 runs from `/path/to/aesop`).
Read `PLAN.md` and `GUARDRAILS.md` (same directory) first — especially decisions D1–D8, the
OUT-OF-SCOPE fence, and risks R1–R6. Status vocabulary: `pending | in-progress | done | blocked`.

Dispatch rule for the orchestrator: pass each task's `model` value as the Agent tool's `model`
parameter when dispatching to `context-rules-implementer` (the parameter overrides the agent's
frontmatter default). `depends:` lists hard ordering. Dispatch `context-rules-reviewer` at each
phase end.

Warm-cluster hints: **T1 → T2 → T3** is a strictly serial chain over the same primary file
(CLAUDE.md + the kit-local script), all `model: sonnet` — one warm implementer may serve all
three. T4 is a fresh spawn (new test file). T5 is `model: opus`, always fresh. T6 is a
different repo, always fresh. The verifier is always a fresh spawn.

Standing rules for every task: Python is stdlib-only (no pip, no pytest); verify commands use
`python3 -m unittest discover -s tests [-p '<file>.py']` (the dotted-module form is broken on
this machine); relocated guardrail text is VERBATIM — never reworded, never "improved"; skill
frontmatter is byte-untouched; never invoke a real `copilot`/`codex`/`claude` CLI; never touch
`~/.claude`, `~/.copilot`, `~/.codex`; aesop-fenced files are never hand-edited; no commit, no
push, in either repo. Where a brief pins content verbatim, reproduce it exactly; if repo
reality contradicts the brief (beyond shifted line numbers), STOP and report — do not
improvise.

---

## Phase 1 — Relocate the 19 kit fences out of CLAUDE.md

### T1 — Migration script `split_guardrails.py` (kit-local, plan/apply/check)
- status: done
- model: sonnet
- depends: (none)

**Brief.** Create `.claude/kits/context-rules/split_guardrails.py` (new file; kit-local on
purpose — it is a one-time migration tool, NOT a `bin/` engine; do not add it to `bin/` or
touch any existing script). Stdlib only, zero `Path.home()`, zero network, zero subprocess.
`main(argv) -> int` + `if __name__ == "__main__": raise SystemExit(main(sys.argv[1:]))`,
argparse with three subcommands. All paths derive from the repo root, computed as
`Path(__file__).resolve().parents[3]` (script sits at `.claude/kits/context-rules/`, three
levels below root — sanity-check by asserting `(root / "CLAUDE.md").is_file()`).

Why (PLAN.md D1/D2): `CLAUDE.md` is 54,377 bytes; lines 82–594 (44,106 bytes) are 19
kit-scoped fence blocks that must move verbatim to `.claude/kits/<slug>/GUARDRAILS.md` so they
load only when that kit runs. A script with a check mode makes "verbatim, zero loss" provable.

**Block detection.** Read `CLAUDE.md` as UTF-8 text, split into lines keeping line endings. A
block starts at a line matching `re.compile(r"^  For `([a-z0-9-]+)` specifically:")` (two-space
indent — pass the backtick literally) and runs to the line before the next match, or EOF for
the last block. Everything before the first match is the HEAD. Expected slugs, in file order
(pin this tuple in the script as `EXPECTED_SLUGS` and hard-fail on mismatch):

```python
EXPECTED_SLUGS = (
    "harden-plugin", "aesop-bridge", "copilot-harness", "copilot-workflow",
    "copilot-costviz", "daily-journal", "fusion-tier1", "fusion-tier2",
    "routing-history", "per-task-dollars", "crossrepo-trend", "codex-harness",
    "journal-augment", "next-day-runbook", "harness-parity", "memory-skill",
    "effort-dial", "copilot-skills-parity", "copilot-model-prefs",
)
```

**Pinned constants** (verbatim in the script):

```python
SLIM_TAIL = """  Each kit's own fences live in `.claude/kits/<slug>/GUARDRAILS.md` — read it together with
  that kit's PLAN.md before starting any of its tasks. Those fences are kit-scoped law: they
  bind only while that kit's tasks run and never generalize to other work. The Invariants
  above are the only always-on rules.
"""

HEADER_TEMPLATE = """# {slug} — kit guardrails

Relocated verbatim from the global CLAUDE.md by the context-rules kit (2026-07-24).
Kit-scoped: these fences bind this kit's tasks only. Global invariants live in CLAUDE.md.

"""
```

**Subcommands.**
- `plan` — parse only, write nothing. Print one line per block: `slug  start_line  end_line
  bytes`, then `head_bytes=<n> blocks=<n> blocks_bytes=<n> total=<n>`. Exit 0 on exactly
  `EXPECTED_SLUGS` in order AND every slug's dir `.claude/kits/<slug>/` already existing;
  exit 1 with a clear message otherwise.
- `apply` — run the same parse+validation as `plan` (refuse on any mismatch). Then: (1) copy
  `CLAUDE.md` to `.claude/kits/context-rules/CLAUDE.md.orig` (refuse to overwrite an existing
  backup unless `--force`); (2) for each block write
  `.claude/kits/<slug>/GUARDRAILS.md` = `HEADER_TEMPLATE.format(slug=slug)` + the block's
  original lines byte-verbatim (indentation and trailing newline included); (3) rewrite
  `CLAUDE.md` = HEAD + `SLIM_TAIL`. Idempotence guard: if `CLAUDE.md` contains no block match,
  print `nothing to do` and exit 0 without writing.
- `check` — prove survival using the backup (`CLAUDE.md.orig`; error exit 2 if missing):
  re-extract blocks from the backup and assert (a) each kit's `GUARDRAILS.md` content ==
  header + original block bytes exactly; (b) current `CLAUDE.md` contains no line matching the
  block regex; (c) `SLIM_TAIL` appears verbatim in current `CLAUDE.md`; (d) byte accounting:
  sum of extracted block bytes == backup total − backup head bytes. With `--strict`, also
  assert current `CLAUDE.md` == backup HEAD + `SLIM_TAIL` byte-identical (used immediately
  after apply, before T3's edits land). Print `check ok` / failures listed, exit 0/1.

Gotcha: preserve the file's exact bytes — no `.strip()`, no re-wrapping, no newline
normalization. Read/write with `encoding="utf-8"` and `newline=""` semantics
(`Path.read_text`/`write_text` with default newline handling is fine on this repo — the file
is plain `\n`).

**Acceptance criteria.**
- Script exists at the kit path, stdlib-only, three subcommands as specified.
- `plan` exits 0 and reports 19 blocks, slugs exactly `EXPECTED_SLUGS` in order,
  `head_bytes=10271 blocks_bytes=44106 total=54377` (if these differ, CLAUDE.md drifted since
  kit build — STOP and report, do not adjust the pins).
- No file outside `.claude/kits/context-rules/` is created or modified by this task; `apply`
  has NOT been run.

**Verify.**
```bash
cd /path/to/polytropos && \
python3 .claude/kits/context-rules/split_guardrails.py plan && \
git status --porcelain | grep -v '^?? .claude/kits/context-rules/' | grep -v '^?? .claude/agents/context-rules-' ; \
python3 -m unittest discover -s tests 2>&1 | tail -2
```
(plan exits 0 printing the 19-block table with the pinned byte totals; the grep prints
nothing — no tracked file changed; suite tail shows `OK`.)

### T2 — Run the relocation: apply + strict check
- status: done
- model: sonnet
- depends: T1

**Brief.** Execute the migration built in T1, from the repo root:
1. `python3 .claude/kits/context-rules/split_guardrails.py apply`
2. `python3 .claude/kits/context-rules/split_guardrails.py check --strict`
3. Full suite.

Why: this is the 44 KB cut (PLAN.md Goal 1). The script does all writing; you run and verify.
Expected effects, exactly: `CLAUDE.md` shrinks to 10,271 + len(SLIM_TAIL) bytes (~10.6 KB);
19 new files `.claude/kits/<slug>/GUARDRAILS.md`; one backup
`.claude/kits/context-rules/CLAUDE.md.orig` (54,377 bytes). Nothing else changes —
`git status --porcelain` must show `CLAUDE.md` modified plus only untracked additions under
`.claude/kits/` and `.claude/agents/context-rules-*`. Spot-check the L210 example: the string
"skills/architect/SKILL.md\` is NEVER edited" must now live in
`.claude/kits/per-task-dollars/GUARDRAILS.md` and NOT in `CLAUDE.md`.

Rollback if check or the suite fails: `git checkout -- CLAUDE.md`, delete the 19 generated
GUARDRAILS.md files and the backup, report the failure verbatim. Never hand-patch a
GUARDRAILS.md to make check pass.

**Acceptance criteria.**
- `check --strict` exits 0 printing `check ok`.
- `wc -c CLAUDE.md` ≤ 11000.
- All 19 GUARDRAILS.md files exist; the per-task-dollars spot-check holds both ways.
- Full suite green (1017 tests baseline).

**Verify.**
```bash
cd /path/to/polytropos && \
python3 .claude/kits/context-rules/split_guardrails.py check --strict && \
wc -c CLAUDE.md && \
ls .claude/kits/*/GUARDRAILS.md | wc -l && \
grep -c 'NEVER edited' .claude/kits/per-task-dollars/GUARDRAILS.md && \
! grep -q 'specifically:' CLAUDE.md && \
python3 -m unittest discover -s tests 2>&1 | tail -2
```
(check ok; byte count ≤ 11000; file count ≥ 20 — 19 relocated + this kit's own; grep count
≥ 1; no `specifically:` left; suite `OK`.)

### T3 — Slim-CLAUDE.md contract line: GUARDRAILS.md joins the kit layout
- status: done
- model: sonnet
- depends: T2

**Brief.** One surgical Edit in `CLAUDE.md`, inside the Invariants bullet "**The architect and
execute skills share one kit contract — keep them in sync.**" (near line 27 of the slimmed
file). Replace the layout phrase exactly:

old: ``layout `.claude/kits/<slug>/PLAN.md` + `TASKS.md` (+ `NOTES.md`, owned by execute);``
new: ``layout `.claude/kits/<slug>/PLAN.md` + `TASKS.md` + `GUARDRAILS.md` (kit-scoped fences, architect-owned; execute reads it at setup) (+ `NOTES.md`, owned by execute);``

Nothing else in the file changes. Why: CLAUDE.md:27-33 is the canonical statement of the kit
contract that T5 will mirror into both skills — the three surfaces must agree (PLAN.md D5/D6).
Note: after this edit `check --strict` no longer byte-matches the head — expected and fine;
plain `check` (non-strict) must still pass.

**Acceptance criteria.**
- The new layout phrase present verbatim; old phrase gone; file still ≤ 11,000 bytes.
- `split_guardrails.py check` (non-strict) still exits 0.
- Full suite green.

**Verify.**
```bash
cd /path/to/polytropos && \
grep -c 'GUARDRAILS.md` (kit-scoped fences, architect-owned; execute reads it at setup)' CLAUDE.md && \
python3 .claude/kits/context-rules/split_guardrails.py check && \
wc -c CLAUDE.md && \
python3 -m unittest discover -s tests 2>&1 | tail -2
```

## Phase 2 — Permanent enforcement (code-as-spec)

### T4 — `tests/test_guardrails_layout.py`: layout, budget ceiling, safety sentinels
- status: done
- model: sonnet
- depends: T2

**Brief.** New file `tests/test_guardrails_layout.py` (the ONLY file this task creates or
edits). Match house test style: read `tests/test_pricing_refs.py` first for the repo-root
resolution pattern and docstring tone. Stdlib `unittest`, no fixtures needed — it asserts
against the real repo files (they are committed content, not user data). Repo root =
`Path(__file__).resolve().parents[1]`.

Why (PLAN.md D4): this is the kit's permanent eval — "no safety string dropped, no re-bloat" —
failing loudly forever after.

Test classes/asserts, all pinned:

1. `KitLayoutTests` — every immediate subdirectory of `.claude/kits/` that contains a
   `PLAN.md` also contains a `GUARDRAILS.md` of ≥ 200 bytes.
2. `ClaudeMdBudgetTests` — `CLAUDE.md` is ≤ 16000 bytes (tripwire ceiling, headroom over the
   current ~10.7 KB); and no line matches
   `re.compile(r"^\s*For `[a-z0-9-]+` specifically:")` (kit fences never return).
3. `GlobalSentinelTests` — each of these substrings appears in `CLAUDE.md` (they are the
   always-on money/CLI/data/contract invariants):

```python
GLOBAL_SENTINELS = (
    "single numeric source of truth",
    "Never invoke the real `copilot` CLI from tests",
    "read-only ingestion with gitignored output",
    "Python is stdlib-only",
    "pending | in-progress | done | blocked",
    "Never touch `~/.claude/`",
    "Do not commit or push",
    "gitignored user data",
    "${CLAUDE_PLUGIN_ROOT}",
)
```

4. `KitSentinelTests` — for each (slug, substring) below, the substring appears in
   `.claude/kits/<slug>/GUARDRAILS.md` (one distinctive money/CLI/data line per relocated
   block, taken verbatim from the original CLAUDE.md text):

```python
KIT_SENTINELS = {
    "harden-plugin": "no pricing.json value edits",
    "aesop-bridge": "only `bin/sync_pricing_refs.py` writes them",
    "copilot-harness": "nothing outside this repo — `~/.copilot` included",
    "copilot-workflow": "NEVER invoke the real `copilot` CLI in any form",
    "copilot-costviz": "nothing reads OR writes the real `~/.copilot`",
    "daily-journal": "ingestion is STRICTLY read-only",
    "fusion-tier1": "never the real `~/.claude`",
    "fusion-tier2": "NEVER auto-routes to frontier/Fable",
    "routing-history": "never a write under `~/.claude`",
    "per-task-dollars": "`skills/architect/SKILL.md` is NEVER edited",
    "crossrepo-trend": "never the real `~/.claude`",
    "codex-harness": "NEVER invoke the real `codex` CLI in any form",
    "journal-augment": "no Graph/OAuth/MCP/network/secrets in any form",
    "next-day-runbook": "NO scheduler and NO unattended dispatch in any form",
    "harness-parity": "`copilot`/`codex`/`claude` CLI from any task, test, or verify command",
    "memory-skill": "gitignored USER DATA",
    "effort-dial": "NEVER invoke the real `copilot`/`codex`/`claude` CLI",
    "copilot-skills-parity": "NEVER invoke the real `copilot`/`codex`/`claude`",
    "copilot-model-prefs": "NEVER invoke the real `copilot`/`codex`/`claude` CLI from any task,",
}
```

Gotcha: read files with `encoding="utf-8"`; compare raw substrings (no regex except the block
pattern); use `subTest` per sentinel so one miss doesn't hide others. If any sentinel is
genuinely absent from the relocated file, that is a REAL failure (content was lost) — STOP and
report; never edit a GUARDRAILS.md or weaken a sentinel to go green.

**Acceptance criteria.**
- New test file only; discovers and passes; whole suite green (1017 + new tests).

**Verify.**
```bash
cd /path/to/polytropos && \
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -v 2>&1 | tail -5 && \
python3 -m unittest discover -s tests 2>&1 | tail -2
```

## Phase 3 — Fix the generator (architect + execute together)

### T5 — Kit guardrails go to the kit dir: edit both skills, contract intact
- status: done
- model: opus
- depends: T3

**Brief.** Edit exactly two files, BODY-only (YAML frontmatter byte-untouched — the plugin is
live): `skills/architect/SKILL.md` and `skills/execute/SKILL.md`. Why (PLAN.md D5/D6): the
bloat's source is architect's instruction to append kit guardrails to global CLAUDE.md
(~2.3 KB/kit measured); both skills share one kit contract (CLAUDE.md Invariants, "The
architect and execute skills share one kit contract"), so the layout change lands in both in
one task, and T3 already updated CLAUDE.md's contract line to match.

Edit 1 — `skills/architect/SKILL.md`, section `### Harness guardrails`. Replace ONLY its first
paragraph, currently beginning "Add (or append to) the target project's `CLAUDE.md`:" and
ending "…the Fable-judgment rails the executors run on." with:

> Write the kit's fences to `.claude/kits/<slug>/GUARDRAILS.md` — task-scoped conventions,
> forbidden shortcuts, "always run X before claiming done". Execute reads the file at setup, so
> they load only when this kit runs and never tax other sessions. Add to the target project's
> global `CLAUDE.md` only an invariant that is genuinely permanent and project-wide — true for
> every future session, not just this kit — and sparingly: that file is loaded everywhere,
> forever. Prefer judgement over rules: state the principle and name the signal to read (e.g.
> "match the surrounding file's error-handling style") instead of an absolute — EXCEPT rules
> protecting real money, live CLIs, or user data, which stay absolute and explicit. If a
> procedure is complex enough, make it a project skill (`.claude/skills/<name>/SKILL.md`)
> instead. These are the Fable-judgment rails the executors run on.

The following "**Aesop-managed target?**" paragraph stays byte-verbatim (it already covers the
compiled-file rule; kit dirs are already stated safe to write directly).

Edit 2 — same file, Step 1 or Step 2 kit-layout mentions: in `## Step 2 — The execution kit`,
after the `### TASKS.md` block's heading list is fine as-is; no other architect change is
sanctioned.

Edit 3 — `skills/execute/SKILL.md`, `## Setup` step 2. Replace the sentence beginning
"Read `PLAN.md` (goal, constraints, tripwires) and `TASKS.md`." with:

> Read `PLAN.md` (goal, constraints, tripwires), the kit's `GUARDRAILS.md` when present
> (kit-scoped fences — binding for every task in this kit, and passed along to implementers by
> reference), and `TASKS.md`.

The rest of that step (autonomy-dial text) stays verbatim.

Contract elements that MUST survive verbatim in BOTH files after your edits — re-check each
one before claiming done: kit layout (now PLAN.md + TASKS.md + GUARDRAILS.md + NOTES.md-owned-
by-execute); task fields `id`, `title`, `status`, `model`, brief, acceptance, verify; status
vocabulary exactly `pending | in-progress | done | blocked` (rendered
`pending/in-progress/done/blocked` in architect Step 2 — keep that rendering); phase headings;
`depends:`/`independent:`; model-field-overrides-frontmatter at dispatch; warm-cluster
preamble hints; NOTES.md owned by execute. If any pinned anchor text differs from repo
reality, STOP and report.

**Acceptance criteria.**
- Both files mention `GUARDRAILS.md` in the specified places; no frontmatter change; no other
  section altered; contract checklist verified in both.
- Full suite green (the suite does not test Claude-side skills — greps below are the check).

**Verify.**
```bash
cd /path/to/polytropos && \
grep -c 'GUARDRAILS.md' skills/architect/SKILL.md && \
grep -c 'GUARDRAILS.md' skills/execute/SKILL.md && \
! git diff -- skills/ | grep -qE '^[-+](name:|description:)' && \
grep -c 'Aesop-managed target' skills/architect/SKILL.md && \
grep -c 'pending/in-progress/done/blocked' skills/architect/SKILL.md && \
grep -c 'pending | in-progress | done | blocked' CLAUDE.md && \
git diff --name-only -- skills/ && \
python3 -m unittest discover -s tests 2>&1 | tail -2
```
(both greps ≥ 1; frontmatter grep silent-true; aesop paragraph still present; status vocab
present in architect and CLAUDE.md; changed files are exactly the two skills; suite `OK`.)

## Phase 4 — aesop repo: progressive disclosure via the compiler

### T6 — Rewrite the session-start reading block in `aesop.yaml`, recompile, prove no drift
- status: done
- model: sonnet
- depends: (none — independent of Phases 1–3, but keep it last so the reviewer sees both repos)

**Brief.** Repo: `/path/to/aesop` (run everything from there).
This repo is AESOP-MANAGED: `CLAUDE.md`, `AGENTS.md`, `GUARDRAILS.md`, `.github/`, `.codex/`,
`.cursor/`, `.vscode/`, `.claude/` are compiled output inside `<!-- aesop:begin -->` fences —
NEVER hand-edit them. The ONLY file you edit is `aesop.yaml`.

Why (PLAN.md aesop audit): `aesop.yaml` line ~50 compiles to `AGENTS.md:161-162`, mandating
"Read `PLAN.md` first, then `docs/01–08`" — 24 KB of historical build plan + eight chapters as
session-start reading for a completed build (v0.1.0; last phase closed 2026-06-11). The fix is
the article's shift 3: point at need, load on demand.

In `aesop.yaml`, under `primitives.instructions.blocks`, the block is a `content: |` literal
scalar whose lines carry a 10-space indent in the file (the fences below show the content with
that indent stripped to 10 spaces exactly as on disk). It currently reads:

```
          ## Working in this repo
          - Read `PLAN.md` first, then `docs/01–08`. The build is phase-gated
            (`docs/08-roadmap.md`): one reviewable change per phase, gated by its Goal line.
          - The golden fixtures under `fixtures/compile/*/expected/` are the compiler's contract —
            regenerate them deliberately, never by reflex, and read the diff.
```

Replace ONLY the first bullet so the block becomes:

```
          ## Working in this repo
          - The build is phase-gated (`docs/08-roadmap.md`): one reviewable change per phase,
            gated by its Goal line. Check the roadmap for current status, then read only the
            `docs/` chapter your change actually touches. `PLAN.md` is the original build plan —
            historical reference, not session-start reading.
          - The golden fixtures under `fixtures/compile/*/expected/` are the compiler's contract —
            regenerate them deliberately, never by reflex, and read the diff.
```

(The fixtures bullet is byte-verbatim untouched. Keep the YAML literal-block style and the
existing 10-space content indentation exactly as found.)

Then: `node dist/index.js compile` (regenerates the fenced files with new hashes), then
`node dist/index.js sync` — it must print `clean: disk matches the manifest.` (baseline
verified clean 2026-07-24, so any drift is yours), then `npm test` (runs tsc build + node
tests; 54+ tests, all green; no network).

Tripwire (PLAN.md R4): `git diff --name-only` after compile may list only `aesop.yaml` and
instruction-derived compiled files (`AGENTS.md`, `CLAUDE.md`, `GUARDRAILS.md`,
`.github/copilot-instructions.md`, files under `.codex/`, `.cursor/`, `.vscode/`, `.claude/`).
If anything under `src/`, `schemas/`, `fixtures/`, `registry/`, or `docs/` changes:
`git checkout -- .`, STOP, report. Do not commit or push.

**Acceptance criteria.**
- `aesop.yaml` carries the new bullet; no other aesop.yaml change.
- `AGENTS.md` (compiled) now contains "historical reference, not session-start reading" and no
  longer contains "Read `PLAN.md` first"; the fixtures bullet survives verbatim.
- `sync` prints `clean: disk matches the manifest.`; `npm test` green; tripwire diff clean.

**Verify.**
```bash
cd /path/to/aesop && \
grep -c 'historical reference, not session-start reading' AGENTS.md && \
! grep -q 'Read `PLAN.md` first' AGENTS.md && \
grep -c "regenerate them deliberately, never by reflex" AGENTS.md && \
node dist/index.js sync && \
git diff --name-only | sort && \
npm test 2>&1 | tail -3
```
