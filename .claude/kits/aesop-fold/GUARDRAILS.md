# aesop-fold — kit-scoped guardrails

These fences bind every aesop-fold task, verifier run, reviewer pass, and test-author
dispatch. They are kit-scoped law; the repo `CLAUDE.md` Invariants stay the always-on rules.

## The aesop repo is read-only, always

- `/path/to/aesop` may be READ by any task and copied FROM with
  provenance (the vendored schema, the transcribed model and matrix, TOML translations of its
  fixture manifests). **Nothing is ever written there** — no file, no `git` state change, no
  `npm`/`node`/`tsc` invocation (there is no `tsc` on PATH; do not try to install one). Every
  task, verifier, and reviewer closes with
  `git -C /path/to/aesop status --porcelain` and treats any output
  as its own defect to restore and report.
- Aesop-side changes are proposals in PLAN.md only. Never create a task that edits aesop.

## Scope fences

- **No Cursor implementation.** No `cursor/` directory, no `.cursor/` files, no `.mdc`
  rendering, no Cursor branch in `bin/harness_select.py`, no Cursor skill. The cursor column of
  `primitives/harness-matrix.json` and `plan --harness cursor` are the whole Cursor deliverable.
- **No emitters, no fences, no lockfile, no sync, no federation, no init/detect, no MCP server
  mode.** If a task seems to need one, the brief is wrong — stop and report.
- **Manifests are never written by code.** `bin/primitives.py` has no command that modifies a
  manifest and no TOML serializer; `--json` on stdout is its only machine output. Adding a
  writer "because it was easy" is a defect (PLAN D3).
- **TOML via `tomllib`, no fallback.** New code imports `tomllib` unconditionally. No
  `try/except ImportError`, no `tomli`, no YAML parser of any kind, no regex-parsing of YAML.
  The Python floor is 3.11 (PLAN D2); a runner below it fails `tests/test_python_floor.py` by
  design, and the remedy is an interpreter, never a test edit.
- **Only `copilot/aesop.yaml` is converted.** `anthro-optimizer/copilot/aesop.yaml` and every
  `aesop.yaml` inside the aesop repo are out of scope. Generic references to aesop's root
  `aesop.yaml` concept (`docs/GUIDE.md`, `skills/architect/SKILL.md`, `skills/execute/SKILL.md`,
  `bin/aesop_bridge.py`, `tests/test_codex_bundle.py`) are NOT renamed.
- **Historical records are never rewritten**: nothing under `.claude/kits/<other-slug>/`,
  `tasks/kits/`, or `.claude/agents/<other-slug>-*.md` changes, even when it mentions
  `copilot/aesop.yaml`.
- **`README.md` is not edited by this kit.** **Root `/AGENTS.md` is never created** (gitignored
  Codex install destination). `CLAUDE.md` changes by exactly one line (T9) and must stay
  ≤ 16000 bytes.
- **`data/pricing*.json` are read-nothing surfaces**: not edited, not parsed, never referenced
  by value. No price, ratio, credit value, model id, plan allowance, or cached date is
  hardcoded into `primitives/*.json`, `bin/primitives.py`, `docs/PRIMITIVES.md`, tests, or
  fixtures. Fixture manifests use aesop's abstract tiers (`strong|mid|cheap`) only.

## Engine and test discipline

- `bin/primitives.py` is deterministic, offline, and read-only: no `Path.home`, `subprocess`,
  `urlopen`, `random`, or wall-clock reads (introspection-tested; keep the literal names out of
  comments and docstrings too). It reads only `primitives/*.json` and the manifest path it is
  given.
- Stdlib `unittest` only, discovered by `python3 -m unittest discover -s tests`; no pytest, no
  pip. Fixtures live inline or under `tests/fixtures/primitives/` and contain no home paths.
- Enums and patterns in the validator come from the vendored schema at run time — retyping an
  enum as a Python literal in `bin/primitives.py` is a defect even if the values match today.
- `primitives/aesop.schema.v1.json` is a byte-identical copy of aesop's LOCKED schema (sha256
  pinned in PLAN.md and in `tests/test_primitives_data.py`). Never edit it; if aesop's copy
  changes upstream, that is a new decision for the user, not a silent refresh.
- Never invoke the real `claude`/`copilot`/`codex`/`gh` CLI from any task, test, or verify
  command. Never touch `~/.claude`, `~/.copilot`, `~/.codex`, or anything outside this repo.

## Working-tree discipline (PLAN R1)

- The tree carried unrelated uncommitted modifications at architect time (`README.md`,
  `SETUP.md`, `bin/harness_select.py`, `bin/harness_update.py`, `codex/AGENTS.md`,
  `docs/CODEX-HARNESS.md`, two `docs-site/` Codex pages, two Codex tests). Before editing any
  file, check `git status --porcelain -- <file>`; if it is already modified, make only the
  surgical edit the brief names and say so in the report. Never `git stash`, `git checkout --`,
  `git reset`, `git clean`, or `git add`/`commit`/`push`.
- Record the full-suite baseline in NOTES.md before the first dispatch. "Green" for this kit
  means no NEW failure or error relative to that baseline, and every new test file green.

## Docs discipline (PLAN R3)

- Every task that edits `docs/*.md` or `mkdocs.yml` ends with `python3 bin/docs_build.py
  build` and stages the regenerated pages together; `python3 bin/docs_build.py check` must exit
  0 before "done". Never hand-edit `docs-site/skills/**` or `docs-site/deep-dives/**`.
- T7 and T8 both rebuild the site and are strictly serial — never dispatched concurrently.
- Editing `copilot-docs/manifest.json` ends with `python3 bin/copilot_docs.py check` exit 0.

## Always run before claiming done

- The task's own verify command, from the repo root, with its real output pasted into the
  report. A verify command you did not run is a failed task.
- `python3 -m unittest discover -s tests` — the FULL suite (baseline 3034 tests, ~130 s) after
  any task that touches `bin/`, `tests/`, `copilot/`, `docs/`, `mkdocs.yml`, `SETUP.md`, or
  `CLAUDE.md` — i.e. every task but T1.
- `git status --porcelain` in this repo (list every changed path and account for each against
  the brief) and in the aesop repo (must be empty).

## Safe mutation recipe (verifier / reviewer / test-author)

To prove a guard fires — the floor sweep, the matrix drift test, the schema-hash pin, the
TOML-decode error path — never mutate a tracked file in place. Copy the inputs to a temp dir,
mutate the copy, point the code at the copy (explicit path arguments exist for every loader),
expect the failure, delete the copy:

```bash
TMP="$(mktemp -d)" && cp -R primitives "$TMP/" \
  && python3 - "$TMP/primitives/harness-matrix.json" <<'PY'
import json, sys; p=sys.argv[1]; d=json.load(open(p)); d["harnesses"]["cursor"]["cells"]["skill"]["support"]="native"; json.dump(d, open(p,"w"))
PY
# ...run the check/test against "$TMP/primitives" and expect nonzero...
rm -rf "$TMP"
```

If the tracked tree is touched anyway, restore it byte-for-byte before reporting and say so.
Close every run with `git status --porcelain` and report any unexpected change as YOUR OWN
defect — never the implementer's.
