# TASKS — copilot-model-prefs

Repo root: `/path/to/polytropos`. Run all verify commands
from there. Read `PLAN.md` (same directory) first — the Ground truth replaces any live
re-derivation (NEVER invoke a real `copilot`/`codex`/`claude` CLI to "check"), then
decisions D1–D10, the OUT-OF-SCOPE fence, and the risks/tripwires. Status vocabulary:
`pending | in-progress | done | blocked`.

Dispatch rule for the orchestrator: pass each task's `model` value as the Agent tool's
`model` parameter when dispatching to `copilot-model-prefs-implementer` (the parameter
overrides the agent's frontmatter default). Dispatch `copilot-model-prefs-reviewer` at each
phase end.

Warm-cluster hints: T1→T2→T3 is a sonnet chain (T2/T3 both depend on T1; file-disjoint but
fine serially) — serve it with ONE warm implementer. T4→T5 is a strictly serial sonnet
chain (both edit `tests/test_copilot_bundle.py`) — a second warm implementer. T6 (haiku),
T7 (sonnet), T8 (haiku) are fresh spawns, as is every verifier dispatch.

Standing rules for every task: NEVER invoke the real `copilot`, `codex`, or `claude` CLI in
any form (command lines you WRITE into bundle bodies are runtime instructions, not commands
you run); nothing outside this repo — `~/.copilot`, `~/.codex`, `~/.claude` included; never
edit `skills/` (Claude side), `codex/`, `data/` (all three pricing files),
`.claude-plugin/`, `README.md`, `copilot/aesop.yaml`,
`copilot/.github/copilot-instructions.md`, `copilot/.github/skills/lessons-loop/`, any
bundle file not named in your brief, any bin engine not named in your brief, or any
completed kit; Python is stdlib-only; zero `Path.home()` in new or edited code; no test or
verify ever creates or reads a real `prefs/copilot.json` at the default path (temp
`--prefs` fixtures or `--no-prefs`, always — and never a test that ASSERTS the default path
is absent); no hardcoded price or real pricing-key model id anywhere new (tier vocabulary,
`PREFS_SCHEMA_VERSION`, the `prefs`/`copilot.json` names, flag-grammar strings, pinned
message text, and synthetic `fake-*` fixture ids are the sanctioned literals); test edits
are ADDITIVE at the seams each brief pins — every other test class/method/constant stays
byte-intact; verify commands use `python3 -m unittest discover -s tests [-p '<file>.py']`
(the dotted-module form is broken on this machine). Where a brief pins content verbatim,
reproduce it exactly; if a pinned anchor is not present verbatim in the target file, STOP
and report the discrepancy.

Shared teaching shape (D8 — used by T4/T5). Every edited bundle surface gets a new section
whose heading is exactly `## User model prefs (pins & excludes)`, inserted BODY-only at the
anchor the task pins (frontmatter byte-intact). The section core (adapt only the tail
sentences per surface as pinned in the task):

```markdown
## User model prefs (pins & excludes)

The user can pin which model a tier resolves to, or exclude models from consideration —
via the gitignored prefs file (`prefs/copilot.json` at the optimizer repo root) or the
driver's per-run flags. Check what is active before recommending anything:

```bash
python3 {{POLYTROPOS_ROOT}}/bin/copilot_pricing.py prefs
```

Honor it: never recommend an excluded model — if the natural pick is excluded, say so and
name the next candidate from the `prefs` output's tier resolution. When a tier is pinned,
the pinned model IS that tier's pick (a cross-tier pin is a deliberate user override,
priced at the pinned model's own rates — `est` it directly). Pins or excludes the user
states in the prompt count the same as the file.
```

No live pricing-key model id may appear in any new paragraph (skills are sweep-tested;
agents follow the same discipline by hand). `prefs/copilot.json`, tier words, and flag
grammar are fine.

---

## Phase 1 — Engine core

### T1 — `bin/copilot_prefs.py` + `tests/test_copilot_prefs.py`
- status: done
- model: sonnet
- depends: (none)
- independent: no (serial chain head)

**Brief.** Create the single home for all prefs logic (PLAN D1–D5), plus its test file.
Read first: `bin/copilot_execute.py` (the `TIER_ORDER` constant, `PRICING_PATH` pattern,
docstring voice), `bin/copilot_pricing.py` (`est_cost`'s unknown-key message shape), and
`tests/test_copilot_execute.py` (the `_load` importlib helper and `PRICING_FIXTURE`).

**New file 1: `bin/copilot_prefs.py`** — stdlib-only, importable module, NO CLI (`main`),
NO `subprocess`, NO `Path.home()`. Module docstring: what prefs are (pins resolve WHICH
model a tier means, excludes remove models from consideration), that the file is gitignored
user data at `prefs/copilot.json`, that flags override the file, and that this module is
the ONLY home for the logic (both engines load it via importlib — never duplicate it).
Constants (exact):

```python
TIER_ORDER = ("cheap", "mid", "strong", "frontier")
PREFS_SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PREFS_PATH = REPO_ROOT / "prefs" / "copilot.json"
```

Functions (exact signatures; behavior per PLAN D1–D5):

1. `empty_prefs()` → `{"pins": {}, "excludes": [], "notes": [], "source": None}`.
2. `load_prefs_file(path)` → `(pins_dict, excludes_list, notes_list)`, raw (NOT yet
   validated against pricing). Absent path → empties, no note (absence is normal).
   Unreadable / invalid JSON / top-level not a dict → empties + one note
   `f"prefs file {path}: malformed ({reason}) — ignoring it"`. `pins` present but not a
   dict of str→str → dropped + note; `excludes` present but not a list of str → dropped +
   note. Unknown top-level keys tolerated silently. An int `schema_version` greater than
   `PREFS_SCHEMA_VERSION` → note
   `f"prefs file {path}: schema_version {v} is newer than {PREFS_SCHEMA_VERSION} — best-effort read"`.
3. `parse_pin_flag(value, pricing)` → `(tier, model_id)`. `ValueError` on: missing `=`
   (`f"invalid --pin {value!r}: expected TIER=MODEL_ID"`); unknown tier
   (`f"unknown tier {tier!r}; valid tiers: {' | '.join(TIER_ORDER)}"`); unknown id
   (`f"unknown model id {model_id!r}; valid choices: {sorted(pricing['models'])}"` — the
   `est_cost` message shape).
4. `validate_exclude_flag(model_id, pricing)` → returns `model_id`; `ValueError` with the
   same unknown-id message if not a live key.
5. `effective_prefs(pricing, prefs_path=None, no_prefs=False, pin_flags=(), exclude_flags=())`
   → the ONE entry point both engines call. Steps: (a) file prefs from
   `Path(prefs_path) if prefs_path else DEFAULT_PREFS_PATH`, skipped entirely when
   `no_prefs` (no notes from the file then); (b) semantic validation of FILE entries —
   a pin whose tier is not in `TIER_ORDER`, or whose id is not a live pricing key, or an
   exclude id not a live key, is SKIPPED with a note naming the entry (roster drift never
   bricks a run); (c) flag pins via `parse_pin_flag` (hard errors propagate) merged
   per-tier over file pins (a flag pin replaces only its own tier's file pin); flag
   excludes via `validate_exclude_flag`, excludes = file-then-flags union, deduped,
   order-preserving; (d) conflict check AFTER the merge — any effective pin whose id is in
   effective excludes raises
   `ValueError(f"pin {tier}={model_id} conflicts with exclude {model_id} — drop one, or use --no-prefs to bypass the prefs file")`;
   (e) for each effective pin whose id's own tier differs from the slot tier, append note
   `f"pin {tier}={model_id} is a cross-tier override (model's own tier: {own_tier})"`.
   Returns `{"pins": ..., "excludes": ..., "notes": ..., "source": ...}` where `source` is
   `str(path)` when `no_prefs` is False and the file exists, else `None`.
6. `resolve_tier(pricing, tier, prefs=None)` → the pinned id when `prefs` carries a pin
   for `tier`; else the first model id in `pricing["models"]` file order whose `tier`
   matches and which is not excluded; else `None`. `ValueError` (the unknown-tier message)
   when `tier` not in `TIER_ORDER`. `prefs=None` behaves as empty prefs.
7. `is_empty(prefs)` → `not prefs["pins"] and not prefs["excludes"]`.

**New file 2: `tests/test_copilot_prefs.py`** — stdlib unittest; the house `_load` helper
(`BIN_DIR = Path(__file__).resolve().parent.parent / "bin"`; copy the helper from
`tests/test_copilot_execute.py`); load the module as `cprefs = _load("copilot_prefs")` and
also `ce = _load("copilot_execute")` for the twin-constant test. Use a module-level
synthetic fixture IDENTICAL in shape to `test_copilot_execute.py`'s `PRICING_FIXTURE`
(models `fake-cheap`/`fake-mid-a`/`fake-mid-b`/`fake-strong`/`fake-front`, tiers
cheap/mid/mid/strong/frontier, round fake rates — copy it; never a real id). Every
file-based test writes its prefs JSON to a `tempfile.TemporaryDirectory()` path passed as
`prefs_path` — NEVER the default path. Test classes (names pinned; cover at least):

- `TierOrderTwinTests` — `cprefs.TIER_ORDER == ce.TIER_ORDER`.
- `LoadPrefsFileTests` — absent path → empties + no notes; malformed JSON → empties + one
  note containing `"malformed"`; top-level list → same; `pins` as a list → dropped + note;
  `excludes` as a dict → dropped + note; newer `schema_version` → note containing
  `"best-effort"`; unknown top-level key → silently tolerated.
- `ParsePinFlagTests` — good `mid=fake-mid-b` parses; no `=` → ValueError containing
  `TIER=MODEL_ID`; unknown tier → message lists all four tier words; unknown id → message
  contains `valid choices`.
- `EffectivePrefsTests` — file pin + flag pin on a DIFFERENT tier → both survive; flag pin
  on the SAME tier → flag replaces file pin only for that tier; excludes union (file +
  flags, deduped, order-preserving); `no_prefs=True` ignores the file but keeps flags;
  file entry with unknown tier / stale id → skipped with a note, run continues; conflict
  (pin id also excluded, any source combination) → ValueError containing `"conflicts with
  exclude"`; cross-tier pin (e.g. `frontier=fake-strong`) → note containing
  `"cross-tier override"`; `source` is the temp path string when the file exists, None
  when absent or `no_prefs`.
- `ResolveTierTests` — pin wins outright over file order; no pin → first in file order
  carrying the tier (`mid` → `fake-mid-a`); exclude `fake-mid-a` → `fake-mid-b`; exclude
  both mids → `None`; exclude `fake-front` with no frontier pin → `None` for frontier;
  frontier pin to `fake-strong` (cross-tier) → returns `fake-strong`; unknown tier word →
  ValueError; `prefs=None` behaves as no prefs.

**Acceptance.**
- Both new files exist; `copilot_prefs.py` contains no `subprocess`, `urllib`,
  `http.client`, `socket`, or `Path.home()` token; no real pricing-key id appears in
  either file; `grep -n 'Path.home' bin/copilot_prefs.py tests/test_copilot_prefs.py` is
  empty.
- All pinned constants, signatures, and message texts exact; verify green; full suite
  still green (nothing pre-existing touched).

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_copilot_prefs.py' -v && python3 -m unittest discover -s tests
```

### T2 — Prefs-aware `bin/copilot_execute.py` (additive) + tests
- status: done
- model: sonnet
- depends: T1
- independent: no

**Brief.** Wire prefs into the driver, strictly additively (PLAN D2–D6). Read first:
`bin/copilot_execute.py` end-to-end and `tests/test_copilot_execute.py` end-to-end (its
`PRICING_FIXTURE`, `STUB_BIN`, `_write_kit`, and the dry-run/end-to-end tests you must NOT
disturb).

**Edits to `bin/copilot_execute.py`** (everything pre-existing stays byte-identical except
the exact seams below):

1. Module-level lazy loader (place after `load_pricing`):
   ```python
   _prefs_mod = None


   def _load_prefs_module():
       """Lazy-load bin/copilot_prefs.py (the single home for prefs logic) via importlib."""
       global _prefs_mod
       if _prefs_mod is None:
           import importlib.util
           path = Path(__file__).resolve().parent / "copilot_prefs.py"
           spec = importlib.util.spec_from_file_location("copilot_prefs", path)
           mod = importlib.util.module_from_spec(spec)
           spec.loader.exec_module(mod)
           _prefs_mod = mod
       return _prefs_mod
   ```
2. `escalation_ladder(pricing, model_id=None, prefs=None)` — additive kwarg; `prefs=None`
   → behavior and code path byte-equivalent to today. With prefs: per tier strictly above
   the start tier, the rung is `prefs["pins"].get(tier)` when set, else the first
   NON-excluded model in file order carrying the tier; a tier yielding nothing is skipped
   (existing behavior); skip any rung equal to `model_id` or an earlier rung (dedupe).
   Update the docstring with one short paragraph on prefs.
3. `run_task(..., prefs=None)` — additive kwarg, appended LAST in the signature. With
   `prefs=None`: byte-equivalent behavior, result dict exactly today's five keys. With
   prefs: if `task["model"]` is set AND in `prefs["excludes"]`, substitute
   `resolve_tier(pricing, own_tier, prefs)` where `own_tier` is
   `pricing["models"][task_model]["tier"]` (if the task model is not a pricing key, no
   substitution — nothing to resolve); a substitution appends
   `f"task pinned {task_model} (excluded) — dispatching {substitute} instead"` to a notes
   list; if the substitute is `None`, raise
   `ValueError(f"task pins {task_model}, which is excluded, and nothing else resolves for tier {own_tier!r} — un-exclude a model or add a --pin for that tier")`.
   The ladder call becomes `escalation_ladder(pricing, effective_model, prefs=prefs)`
   (effective_model = the substituted or original model). Result gains ONE additive key
   `prefs_notes` (the notes list) ONLY when `prefs is not None`.
4. `cmd_run`: after `extra_args = ...`, build prefs:
   - If `args.pin or args.exclude or args.prefs or args.no_prefs` OR
     (`not args.no_prefs` and the module-default prefs file exists — check via
     `_load_prefs_module().DEFAULT_PREFS_PATH.exists()` only when needed): load pricing
     once (`pricing = load_pricing()`), compute
     `prefs = _load_prefs_module().effective_prefs(pricing, prefs_path=args.prefs, no_prefs=args.no_prefs, pin_flags=tuple(args.pin or ()), exclude_flags=tuple(args.exclude or ()))`,
     and treat `is_empty(prefs)` (and no notes) as `prefs = None`.
   - Otherwise `prefs = None` and — crucially — the `--dry-run` path must NOT load
     pricing (today's byte-identical dry-run).
   - Dry-run with `prefs is not None`: before the existing `task:` line print one line
     `prefs: pins=<t>=<id>,... excludes=<id>,...` (render `(none)` for an empty side) and
     one `note: <text>` line per note; the dispatch argv must show the SUBSTITUTED model
     when the task's model was excluded (compute the substitution the same way `run_task`
     does — factor a tiny helper `_effective_task_model(task, pricing, prefs)` returning
     `(model, notes)` and use it in BOTH `run_task` and the dry-run path so the logic
     exists once).
   - Real run: pass `prefs=prefs` to `run_task`; after the existing result print, print
     one `note: <text>` line per entry of `result.get("prefs_notes") or []`.
   - ValueErrors from `effective_prefs` propagate to `main`'s existing handler (exit 2) —
     do not catch locally.
5. Argparse (`build_parser`, `run` subparser only — `status`/`review` untouched), added
   after the `--extra-arg` argument, before `--dry-run`:
   ```python
   p_run.add_argument("--pin", action="append", metavar="TIER=MODEL_ID",
                      help="resolve TIER to MODEL_ID (repeatable; overrides the prefs file's pin for that tier)")
   p_run.add_argument("--exclude", action="append", metavar="MODEL_ID",
                      help="never dispatch this model (repeatable; unions with the prefs file's excludes)")
   p_run.add_argument("--prefs", default=None, metavar="FILE",
                      help="prefs file to read (default: <repo>/prefs/copilot.json)")
   p_run.add_argument("--no-prefs", action="store_true",
                      help="ignore the prefs file entirely (--pin/--exclude flags still apply)")
   ```
   Update the module docstring's `Usage:` run line to include
   `[--pin TIER=MODEL_ID ...] [--exclude MODEL_ID ...] [--prefs FILE] [--no-prefs]`.

**Additive tests in `tests/test_copilot_execute.py`** — appended after the
`StatusSmokeTests` class, immediately before the `if __name__ == "__main__":` block;
NOTHING pre-existing changed. Use the file's existing `PRICING_FIXTURE`, `STUB_BIN`,
`_write_kit`, fixtures. Prefs dicts for pure-function tests may be built literally
(`{"pins": {...}, "excludes": [...], "notes": [], "source": None}`). Classes (pinned
names; cover at least):

- `PrefsAwareLadderTests` — `prefs=None` → identical to the legacy assertions
  (`["fake-strong", "fake-front"]` from `fake-mid-a`); pin `strong=fake-mid-b` → ladder
  from `fake-mid-a` is `["fake-mid-b", "fake-front"]` (pin wins outright, cross-tier
  allowed); exclude `fake-strong` → `["fake-front"]` from `fake-mid-a` (emptied tier
  skipped); exclude `fake-front` with no frontier pin → ladder from `fake-strong` is `[]`
  (tops out lower, honestly empty); pin `frontier=fake-strong` from start `fake-strong` →
  `[]` (rung equal to current model deduped).
- `RunTaskPrefsTests` — task model `fake-mid-a` excluded with pin `mid=fake-mid-b` →
  first dispatch argv carries `fake-mid-b`, `model_used` reflects it on first-try pass,
  `prefs_notes` has one entry containing `"excluded"`; task model excluded, both mids
  excluded, no pin → `ValueError`; `prefs=None` → result has NO `prefs_notes` key.
- `CliPrefsTests` — all via `ce.main([...])` with
  `mock.patch.object(ce, "load_pricing", return_value=PRICING_FIXTURE)` and temp kits;
  every invocation passes `--prefs <temp path>` or `--no-prefs` (never the default path):
  dry-run with `--no-prefs --pin mid=fake-mid-b --exclude fake-mid-a` on the T1-style kit
  → stdout contains a `prefs:` line and a `dispatch:` line whose argv shows `fake-mid-b`,
  and (patch `ce.subprocess` to raise, as the existing dry-run test does) nothing spawns
  and TASKS.md is byte-unchanged; `--pin mid` (no `=`) → SystemExit code 2, stderr
  contains `TIER=MODEL_ID`; `--pin nope=fake-cheap` → exit 2, stderr lists the four tier
  words; `--exclude not-a-model` → exit 2, stderr contains `valid choices`;
  `--pin mid=fake-mid-b --exclude fake-mid-b` → exit 2, stderr contains
  `conflicts with exclude`; a temp prefs FILE with a pin merged with a flag exclude on a
  different id both take effect in the dry-run `prefs:` line.

**Acceptance.**
- All pre-existing functions/flags/outputs byte-stable: the untouched classes in
  `tests/test_copilot_execute.py` pass unmodified; plain `run --dry-run` (no flags, no
  file) output is exactly the three legacy lines; `status`/`review` parsers untouched.
- New behavior per PLAN D2–D6 with the exact pinned messages; substitution logic exists
  ONCE (`_effective_task_model`); zero `Path.home()`; verify green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_copilot_execute.py' -v && python3 -m unittest discover -s tests
```

### T3 — `copilot_pricing.py prefs` subcommand + tests
- status: done
- model: sonnet
- depends: T1
- independent: no (same warm chain as T1/T2; file-disjoint from T2)

**Brief.** Add the ONE new pricing surface (PLAN D7), mirroring the `knobs` additive
precedent. Read first: `bin/copilot_pricing.py` end-to-end (`cmd_knobs` + `build_parser`)
and `tests/test_copilot_pricing.py` end-to-end (`FIXTURE` — note it has NO frontier-tier
model — and `KnobsCmdTests`' `mock.patch.object(cp, "load_pricing", ...)` pattern).

**Edits to `bin/copilot_pricing.py`** (everything pre-existing byte-identical):

1. The same `_load_prefs_module()` lazy loader as T2 pinned (identical body; place after
   `load_pricing`).
2. `cmd_prefs(args, pricing)` — docstring: shows the active pins/excludes and what each
   tier now resolves to; the prefs file is gitignored user data; errors exit 2. Body:
   - `prefs = _load_prefs_module().effective_prefs(pricing, prefs_path=args.prefs, no_prefs=args.no_prefs, pin_flags=tuple(args.pin or ()), exclude_flags=tuple(args.exclude or ()))`
     wrapped in `try/except ValueError as e: print(str(e), file=sys.stderr); sys.exit(2)`.
   - `resolved = {tier: resolve_tier(pricing, tier, prefs) for tier in TIER_ORDER}` and
     `resolved_via = {tier: ("pin" if tier in prefs["pins"] else ("default" if resolved[tier] else None)) for tier in TIER_ORDER}`
     (use the prefs module's `TIER_ORDER` and `resolve_tier`).
   - `--json`: print `json.dumps` of exactly
     `{"source": ..., "pins": ..., "excludes": ..., "resolved": ..., "resolved_via": ..., "notes": ...}`
     with `indent=2`.
   - Text output lines, in order: `source: <path>` — or `source: (no prefs file)` when
     `source` is None and not `args.no_prefs`, or `source: (prefs file ignored: --no-prefs)`
     when `args.no_prefs`; `pins: <t>=<id>, ...` or `pins: (none)`;
     `excludes: <id>, ...` or `excludes: (none)`; `tier resolution:` then one line per
     tier in order, `  <tier padded>  -> <id>` with suffix ` (pinned)` when via is pin and
     additionally ` (model's own tier: <t2>)` when the pinned id's own tier differs, or
     `-> (none — no non-excluded model carries this tier)` when unresolvable; finally one
     `note: <text>` line per note.
3. `build_parser`: after the `knobs` subparser block:
   ```python
   p_prefs = sub.add_parser(
       "prefs", help="active model pins/excludes and what each tier now resolves to"
   )
   p_prefs.add_argument("--pin", action="append", metavar="TIER=MODEL_ID",
                        help="resolve TIER to MODEL_ID (repeatable; overrides the prefs file's pin for that tier)")
   p_prefs.add_argument("--exclude", action="append", metavar="MODEL_ID",
                        help="never recommend this model (repeatable; unions with the prefs file's excludes)")
   p_prefs.add_argument("--prefs", default=None, metavar="FILE",
                        help="prefs file to read (default: <repo>/prefs/copilot.json)")
   p_prefs.add_argument("--no-prefs", action="store_true",
                        help="ignore the prefs file entirely (--pin/--exclude flags still apply)")
   p_prefs.add_argument("--json", action="store_true", help="machine-readable output")
   p_prefs.set_defaults(func=cmd_prefs)
   ```
   Update the module docstring `Usage:` block with the matching `prefs` line.

**Additive tests in `tests/test_copilot_pricing.py`** — ONE class appended after
`CliSmokeTests`, immediately before the `if __name__ == "__main__":` block; nothing
pre-existing changed. `class PrefsCmdTests(unittest.TestCase)` — all via
`cp.main(["prefs", ...])` with `mock.patch.object(cp, "load_pricing", return_value=FIXTURE)`
(deep-copied where mutated) and temp dirs for every prefs file; every invocation passes
`--prefs <temp path>` or `--no-prefs`. Cover at least: no file at the temp path →
`source: (no prefs file)`, `pins: (none)`, per-tier defaults follow FIXTURE file order
(`cheap` → `fake-cheap`, `mid` → `fake-promo`, `strong` → `fake-strong-lc`) and `frontier`
renders the `(none — ...)` line (FIXTURE has no frontier model — the honesty case); a temp
file `{"schema_version": 1, "pins": {"mid": "fake-cheap"}, "excludes": ["fake-strong-lc"]}`
→ mid marked `(pinned)` with the cross-tier annotation, strong unresolvable; a flag
`--pin mid=fake-strong-lc` over that same file → conflict exit 2 (`conflicts with
exclude` in stderr); flag pin replaces only its tier while a file pin on another tier
survives; malformed temp file → note line containing `malformed` and default resolutions;
`--no-prefs` with a populated `--prefs` file → `(prefs file ignored: --no-prefs)` and
default resolutions; `--json` parses and has exactly the six pinned keys with
`resolved["frontier"]` null.

**Acceptance.**
- `models`/`est`/`runway`/`knobs` outputs byte-identical (untouched classes pass
  unmodified); the new subcommand matches the pinned output grammar; exit 2 on
  flag/conflict errors; verify green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_copilot_pricing.py' -v && python3 bin/copilot_pricing.py prefs --no-prefs >/dev/null && python3 -m unittest discover -s tests
```

## Phase 2 — Bundle teaching

### T4 — route + frontier-check teaching (skill AND agent) + contract tests
- status: done
- model: sonnet
- depends: T2, T3
- independent: no (serial chain head for the bundle test file)

**Brief.** Teach pins/excludes on the two decision-aid capabilities, each on BOTH surfaces
(PLAN D8). BODY-only edits — frontmatter byte-intact. Read each target file first. Insert
the Shared teaching shape section (preamble above) at these anchors:

1. `copilot/.github/skills/route/SKILL.md` — insert immediately BEFORE the
   `## Same-named agent` heading. Use the shared core verbatim.
2. `copilot/.github/agents/route.agent.md` — insert immediately BEFORE the
   `## Output shape` heading. Same core verbatim.
3. `copilot/.github/skills/frontier-check/SKILL.md` — insert immediately BEFORE the
   `## Same-named agent` heading. Shared core PLUS this pinned tail sentence appended to
   the final paragraph:
   `When a frontier pin is active, the pinned model IS the frontier candidate you evaluate — est its actual rates and note that it overrides the roster's default frontier pick.`
4. `copilot/.github/agents/frontier-check.agent.md` — insert immediately BEFORE the
   `## Installed?` heading. Same core + the same frontier tail sentence.

No live pricing-key model id anywhere in the new text (`SkillNoModelIdTests` sweeps the
skills; apply the same discipline to the agents). The engine flags/subcommand you mention
exist as of T2/T3 — quote no other flags.

**Additive tests in `tests/test_copilot_bundle.py`** — ONE class appended after the
`ExecuteSkillContractTests` class, immediately before the `if __name__ == "__main__":`
block; nothing pre-existing changed:

```python
class PrefsTeachingDecisionAidTests(unittest.TestCase):
    """Pins/excludes teaching (copilot-model-prefs PLAN.md D8): route + frontier-check,
    skill and agent surfaces."""

    FILES = {
        "route skill": SKILLS_DIR / "route" / "SKILL.md",
        "route agent": AGENTS_DIR / "route.agent.md",
        "frontier-check skill": SKILLS_DIR / "frontier-check" / "SKILL.md",
        "frontier-check agent": AGENTS_DIR / "frontier-check.agent.md",
    }

    def test_each_surface_checks_active_prefs(self):
        for label, path in self.FILES.items():
            with self.subTest(surface=label):
                text = path.read_text()
                self.assertIn("User model prefs", text)
                self.assertIn("copilot_pricing.py", text)
                self.assertIn("prefs", text)
                self.assertIn("exclude", text)

    def test_frontier_check_evaluates_pinned_candidate(self):
        for label in ("frontier-check skill", "frontier-check agent"):
            with self.subTest(surface=label):
                self.assertIn("overrides the roster", self.FILES[label].read_text())
```

**Acceptance.**
- Four files each gain exactly one new section at the pinned anchor; frontmatter and all
  other body text byte-unchanged; the new text is id-free; `copilot/aesop.yaml` untouched;
  verify green (the whole bundle suite, including the YAML-safety and no-model-id sweeps).

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_copilot_bundle.py' -v && python3 -m unittest discover -s tests
```

### T5 — architect + escalate teaching (skill AND agent) + execute sentence + contract tests
- status: done
- model: sonnet
- depends: T4
- independent: no (serial chain)

**Brief.** Teach pins/excludes on the two workflow capabilities plus the execute skill's
one sentence (PLAN D8). BODY-only; frontmatter byte-intact; read each target first.

1. `copilot/.github/skills/architect/SKILL.md` — insert the Shared teaching shape
   immediately BEFORE the `## Same-named agent` heading, PLUS this pinned tail sentence
   appended to the final paragraph:
   `Write every kit task's model: pin consistent with the active prefs — never an excluded id; where a tier is called for, use that tier's resolved id from the prefs output.`
2. `copilot/.github/agents/architect.agent.md` — same core + same tail, inserted
   immediately BEFORE the `## Output shape` heading.
3. `copilot/.github/skills/escalate/SKILL.md` — insert immediately BEFORE the
   `## Same-named agent` heading: the shared core PLUS this pinned tail paragraph (a new
   paragraph after the core's final one):
   `The driver enforces these mechanically: bin/copilot_execute.py run takes repeatable --pin TIER=MODEL_ID and --exclude MODEL_ID flags (flags override the file; --no-prefs ignores the file). On the ladder, excluded models are skipped in favor of the next model in pricing-file order; a tier emptied by exclusion is skipped; if the frontier tier empties and no pin replaces it, the ladder tops out at a lower tier — report that honestly, never invent a rung.`
4. `copilot/.github/agents/escalate.agent.md` — same core + same tail paragraph, inserted
   immediately BEFORE the `## Kit tasks` heading.
5. `copilot/.github/skills/execute/SKILL.md` — in the `## Run a task` section, append this
   pinned sentence as a new paragraph after the paragraph ending `so preview when unsure.`:
   `The driver also honors the user's model prefs — repeatable --pin TIER=MODEL_ID and --exclude MODEL_ID flags override the gitignored prefs/copilot.json file, and --no-prefs ignores it (python3 {{POLYTROPOS_ROOT}}/bin/copilot_pricing.py prefs shows what is active).`

Backtick-format command/flag tokens in the inserted text per the surrounding house style
(`--pin TIER=MODEL_ID`, `--exclude MODEL_ID`, `--no-prefs`, `prefs/copilot.json`,
`bin/copilot_execute.py run`, the `python3 ... prefs` invocation); keep the words
themselves exactly as pinned. No live pricing-key model id anywhere.

**Additive tests in `tests/test_copilot_bundle.py`** — ONE class appended after
`PrefsTeachingDecisionAidTests` (T4's class), immediately before the
`if __name__ == "__main__":` block; nothing else changed:

```python
class PrefsTeachingWorkflowTests(unittest.TestCase):
    """Pins/excludes teaching (copilot-model-prefs PLAN.md D8): architect + escalate
    (skill and agent) and the execute skill's driver-flag sentence."""

    def _skill(self, name):
        return (SKILLS_DIR / name / "SKILL.md").read_text()

    def _agent(self, name):
        return (AGENTS_DIR / f"{name}.agent.md").read_text()

    def test_architect_pins_consistent_with_prefs(self):
        for text in (self._skill("architect"), self._agent("architect")):
            self.assertIn("User model prefs", text)
            self.assertIn("never an excluded id", text)

    def test_escalate_names_driver_flags_and_empty_tier_honesty(self):
        for text in (self._skill("escalate"), self._agent("escalate")):
            self.assertIn("--pin", text)
            self.assertIn("--exclude", text)
            self.assertIn("tops out", text)

    def test_execute_names_driver_flags(self):
        text = self._skill("execute")
        self.assertIn("--pin", text)
        self.assertIn("--exclude", text)
        self.assertIn("--no-prefs", text)
        self.assertIn("prefs/copilot.json", text)
```

**Acceptance.**
- Five files edited exactly as pinned (four new sections + one sentence); frontmatter and
  every other line byte-unchanged; id-free; `copilot/aesop.yaml` and
  `copilot-instructions.md` untouched; verify green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_copilot_bundle.py' -v && python3 -m unittest discover -s tests
```

## Phase 3 — Closeout

### T6 — Gitignore: root-anchored `/prefs/`
- status: done
- model: haiku
- depends: (none)
- independent: yes

**Brief.** Append EXACTLY these two lines to the end of `.gitignore` (which currently ends
with the `/memory/` entry), preceded by nothing else:

```
# copilot model prefs — user pins/excludes (user data — never committed)
/prefs/
```

The leading slash is load-bearing (root-anchored — the `/memory/` lesson: an unanchored
pattern would also ignore any nested `prefs/` dir). Change nothing else in the file. Do
NOT create the `prefs/` directory or any file in it.

**Acceptance.**
- `.gitignore` diff is exactly the two appended lines; no `prefs/` dir exists in the
  working tree.

**Verify.**
```bash
grep -n '^/prefs/$' .gitignore && test "$(git diff --numstat -- .gitignore | cut -f1-2)" = "2	0" && test ! -e prefs && echo OK
```

### T7 — `docs/COPILOT-PINS.md`
- status: done
- model: sonnet
- depends: T5
- independent: no

**Brief.** Write the feature doc (PLAN D9), ~90–140 lines, in the voice of
`docs/EFFORT-DIAL.md`/`docs/COPILOT-PARITY.md` (read both first, plus PLAN.md D1–D8 and
the T2/T3 argparse surfaces — quote no other flags). Required sections:

- **What it is / why** — pin which model a tier resolves to; exclude models from
  consideration; Copilot CLI only; explicitly NOT a force-frontier switch (a pin changes
  WHICH model a tier means, never WHEN a tier is used).
- **The prefs file** — `prefs/copilot.json` at the repo root; gitignored user data
  (root-anchored `/prefs/`), hand-edited, never committed, never auto-created; the JSON
  schema with `schema_version`, `pins`, `excludes` — every example id is a PLACEHOLDER
  (`<model-id>`, `<frontier-model-id>`); tell the reader to list live ids via
  `python3 bin/copilot_pricing.py models --json`. NO real pricing-key id anywhere in this
  doc (the verify enforces it).
- **Per-run flags + precedence** — `--pin TIER=MODEL_ID` / `--exclude MODEL_ID` /
  `--prefs FILE` / `--no-prefs` on `copilot_execute.py run` and `copilot_pricing.py
  prefs`; flag pins merge per-tier over file pins; excludes are the union; `--no-prefs`
  ignores the file but keeps flags; pin-vs-exclude conflict is always a hard error.
- **Semantics** — pinned id wins its tier outright; cross-tier pins are deliberate
  overrides priced at the pinned model's own rates; excluded ids are skipped in tier
  resolution and the escalation ladder; an emptied tier is skipped; an emptied frontier
  with no replacing pin means the ladder tops out lower (stated, never fabricated); a
  task whose own TASKS.md model pin is excluded gets the tier's resolved substitute, or an
  error when nothing resolves; prefs do NOT reach an agent's frontmatter `model:` default
  (Copilot-side resolution the driver never sees).
- **Seeing what's active** — the `prefs` subcommand, text + `--json` shapes.
- **Where it's taught** — the four skills/agents + the execute sentence.
- **Deferred** — Codex/Claude-side parity; a prefs-writing CLI; prefs-aware `models`
  markers (per PLAN's Deferred list).

**Acceptance.**
- Doc exists with all sections; no live pricing-key model id; no invented flag; verify
  green.

**Verify.**
```bash
test -f docs/COPILOT-PINS.md && python3 -c "
import json, pathlib
ids = json.loads(pathlib.Path('data/pricing.copilot.json').read_text())['models']
t = pathlib.Path('docs/COPILOT-PINS.md').read_text()
bad = [i for i in ids if i in t]
assert not bad, f'live model ids in doc: {bad}'
for needle in ('prefs/copilot.json', '--pin', '--exclude', '--no-prefs', 'tops out', 'schema_version'):
    assert needle in t, f'missing: {needle}'
print('ok')
"
```

### T8 — Full-suite + frozen-surface audit
- status: done
- model: haiku
- depends: T5, T6, T7
- independent: no

**Brief.** Mechanical closeout. From the repo root:

1. `python3 -m unittest discover -s tests` — fully green.
2. `python3 bin/copilot_pricing.py prefs --no-prefs` and
   `python3 bin/copilot_pricing.py knobs` and `python3 bin/copilot_pricing.py models --json | python3 -c "import json,sys; json.load(sys.stdin)"` — all exit 0.
3. Frozen surfaces:
   `git diff --quiet -- skills codex data .claude-plugin README.md copilot/aesop.yaml copilot/.github/copilot-instructions.md copilot/.github/skills/lessons-loop` exits 0.
4. `git status --porcelain` — the ONLY modified pre-existing files are
   `bin/copilot_execute.py`, `bin/copilot_pricing.py`, `tests/test_copilot_execute.py`,
   `tests/test_copilot_pricing.py`, `tests/test_copilot_bundle.py`, `.gitignore`,
   `CLAUDE.md`, and the only new files are `bin/copilot_prefs.py`,
   `tests/test_copilot_prefs.py`, `docs/COPILOT-PINS.md`, the
   `.claude/kits/copilot-model-prefs/` kit files, and the three
   `.claude/agents/copilot-model-prefs-*.md` agents. Anything else → report it, change
   nothing.
5. Sweeps: `grep -rn -e 'Path.home' bin/copilot_prefs.py tests/test_copilot_prefs.py`
   empty; `grep -rn 'subprocess' bin/copilot_prefs.py` empty; `test ! -e prefs`;
   `grep -c '^/prefs/$' .gitignore` prints 1; no live pricing-key id in the new
   files/paragraphs — run:
   `python3 -c "import json,pathlib; ids=json.loads(pathlib.Path('data/pricing.copilot.json').read_text())['models']; targets=['bin/copilot_prefs.py','tests/test_copilot_prefs.py','docs/COPILOT-PINS.md']; bad=[(t,i) for t in targets for i in ids if i in pathlib.Path(t).read_text()]; assert not bad, bad; print('ok')"`.

Report every command's outcome. Change nothing — findings go to the orchestrator.

**Acceptance.**
- All commands green/clean as listed, or a faithful report of exactly what deviated.

**Verify.**
```bash
python3 -m unittest discover -s tests && git diff --quiet -- skills codex data .claude-plugin README.md copilot/aesop.yaml copilot/.github/copilot-instructions.md copilot/.github/skills/lessons-loop && test ! -e prefs && echo AUDIT-OK
```
