# TASKS — copilot-budget-mode

Repo root: `/path/to/polytropos`. Run all verify commands
from there. Read `PLAN.md` and `GUARDRAILS.md` (same directory) first — the Ground truth
replaces any live re-derivation (NEVER invoke a real `copilot`/`codex`/`claude` CLI to
"check" anything), then decisions D1–D9, the OUT-OF-SCOPE fence, and the risks/tripwires.
Status vocabulary: `pending | in-progress | done | blocked`.

Dispatch rule for the orchestrator: pass each task's `model` value as the Agent tool's
`model` parameter when dispatching to `copilot-budget-mode-implementer` (the parameter
overrides the agent's frontmatter default). Dispatch `copilot-budget-mode-verifier` after
each task and `copilot-budget-mode-reviewer` at each phase end (per PLAN D7, do not skip a
phase review in this kit).

Warm-cluster hints: T1→T2→T3 is a strictly serial sonnet chain sharing the same two primary
files (`bin/copilot_execute.py` + `tests/test_copilot_budget.py`) — serve it with ONE warm
implementer. T4 (sonnet) is a fresh spawn. T5 (haiku) and T6 (haiku) are fresh spawns, as is
every verifier dispatch.

Standing rules for every task: NEVER invoke the real `copilot`, `codex`, or `claude` CLI in
any form (command lines you WRITE into skill/docs bodies are runtime instructions, not
commands you run); nothing outside this repo — `~/.copilot`, `~/.codex`, `~/.claude`
included; Python is stdlib-only; zero `Path.home()` in new or edited code; every `main()`
invocation in tests passes `--no-prefs` (or a temp `--prefs` file) and patches
`ce.load_pricing` to the fixture — never a bare run that could read the real prefs file or
flake on live-roster changes; no hardcoded price or live pricing-key model id anywhere new
(tier vocabulary, the profile letter `M` as a validated flag default, flag-grammar strings,
pinned message text, and synthetic `fake-*` fixture ids are the sanctioned literals); frozen
files per GUARDRAILS stay byte-intact; verify commands use
`python3 -m unittest discover -s tests [-p '<file>.py']` (the dotted-module form is broken on
this machine). Where a brief pins content verbatim, reproduce it exactly; if a pinned anchor
is not present verbatim in the target file, STOP and report the discrepancy — do not
improvise.

---

## Phase 1 — Driver core

### T1 — `budget_demote` + `--budget` flags + dispatch wiring + dry-run lines
- status: done
- model: sonnet
- depends: (none)

**Brief.** Files: `bin/copilot_execute.py` (edit) and `tests/test_copilot_budget.py` (NEW).
All engine changes are additive; without `--budget` every output/result/exit code is
byte-identical to today.

In `bin/copilot_execute.py`:

1. Add a pure function `budget_demote(pricing, model_id=None, prefs=None)` directly below
   `escalation_ladder`. It returns a dict
   `{"standard_model", "standard_tier", "target_tier", "dispatched_model", "demoted", "notes"}`
   with these pinned semantics (PLAN D3/D6 — tier→model resolution is ONLY ever
   `_load_prefs_module().resolve_tier(pricing, target_tier, prefs)`, never a re-implemented
   scan):
   - `model_id is None` (pin-less task): `standard_tier = DEFAULT_ESCALATION_START`,
     `standard_model = None`, note
     `f"task has no model pin — standard tier assumed {DEFAULT_ESCALATION_START} (agent default)"`,
     then proceed to demotion from that tier.
   - `model_id` not a key of `pricing["models"]`, or its `tier` not in `TIER_ORDER`: no
     demotion — `dispatched_model = model_id`, `demoted = False`, `target_tier = None`, note
     `f"cannot demote {model_id} — not a live pricing id; dispatching as pinned"` (or
     `"...has no recognized tier..."` for the tier case).
   - `standard_tier == TIER_ORDER[0]`: no demotion, note
     `f"already at the {TIER_ORDER[0]} floor — no demotion"`.
   - Otherwise `target_tier = TIER_ORDER[TIER_ORDER.index(standard_tier) - 1]`;
     `candidate = resolve_tier(pricing, target_tier, prefs)`.
     - `candidate is None`: no demotion (dispatch at the standard model), note
       `f"tier {target_tier!r} resolves to nothing (empty or fully excluded) — no demotion, never a two-rung jump"`.
     - `candidate == model_id`: no demotion, note
       `f"tier {target_tier!r} resolves back to {model_id} — no demotion"`.
     - Else: `dispatched_model = candidate`, `demoted = True`, note
       `f"demoted {standard_tier} -> {target_tier}: {candidate}"`.
   - In every no-demotion case except the unknown-id case, `dispatched_model` is `model_id`
     (which may be `None` → dispatch without `--model`, agent default).
2. `run` subparser gains `--budget` (`action="store_true"`, help:
   `"dispatch one tier lower than the task's pin (floor: cheapest tier) and report est. actual-vs-standard cost"`)
   and `--budget-profile` (`metavar="PROFILE"`, `default="M"`, help:
   `"task profile for the budget cost estimate (a task_profiles key in data/pricing.copilot.json)"`).
3. In `cmd_run`: when `args.budget`, ALWAYS load pricing (even for dry-run; keep the existing
   lazy behavior when budget is off). Validate the profile up front:
   `if args.budget_profile not in pricing.get("task_profiles", {}):` raise
   `ValueError(f"unknown task profile {args.budget_profile!r}; valid choices: {sorted(pricing.get('task_profiles', {}))}")`
   (flows to the existing exit-2 handler in `main`). Compute
   `binfo = budget_demote(pricing, effective_model, prefs)` where `effective_model` comes
   from the existing `_effective_task_model` call (composition order per PLAN D3).
4. Dry-run path with budget active: after the existing optional `prefs:`/`note:` lines and
   before the `task:` line, print exactly one budget line —
   `f"budget: demoted {standard_tier} -> {target_tier} — dispatching {dispatched_model} (standard: {standard_label})"`
   when `demoted`, else `f"budget: no demotion — {'; '.join(notes)}"` — where
   `standard_label = standard_model or f"agent default (assumed {DEFAULT_ESCALATION_START})"`.
   Build the dispatch argv with `binfo["dispatched_model"]`. Still spawns and writes nothing.
5. `run_task` gains a keyword-only-style trailing kwarg `budget=False`. When `True`: after
   the existing `_effective_task_model` call, apply
   `binfo = budget_demote(pricing, model, prefs)`, dispatch initially at
   `binfo["dispatched_model"]`, compute the ladder as
   `escalation_ladder(pricing, binfo["dispatched_model"], prefs=prefs)` (so the first rung up
   is the standard tier), and add ONE additive result key `"budget": binfo`. When `False`
   (default): byte-identical behavior and result keys to today.
6. Real-run path in `cmd_run`: pass `budget=args.budget` into `run_task`; when budget was
   active, print the same single `budget:` line (format from step 4) immediately after the
   existing `task {id}: ...` summary line. (The est verdict line is T2's job — do NOT print
   dollars in this task.)

NEW `tests/test_copilot_budget.py` — stdlib unittest, importlib-loads `copilot_execute` (and
`copilot_prefs` where needed) by absolute path per the house pattern in
`tests/test_copilot_execute.py`; open with a safety-contract docstring mirroring that file's
(no real CLI, no real `~/.copilot`, injected runners / temp stubs only, no `Path.home()`).
Module-level fixture (pinned — richer than the execute-test one because `est_cost` needs
`cached_input_per_mtok`, `task_profiles`, and `billing_unit`; T2 reuses it):

```python
BUDGET_PRICING_FIXTURE = {
    "billing_unit": {"usd_per_credit": 0.01},
    "task_profiles": {"M": {"label": "fixture profile", "input_tokens": 100000, "output_tokens": 10000}},
    "models": {
        "fake-cheap": {"tier": "cheap", "input_per_mtok": 1.0, "cached_input_per_mtok": 0.1, "output_per_mtok": 2.0},
        "fake-mid-a": {"tier": "mid", "input_per_mtok": 3.0, "cached_input_per_mtok": 0.3, "output_per_mtok": 6.0},
        "fake-mid-b": {"tier": "mid", "input_per_mtok": 3.5, "cached_input_per_mtok": 0.35, "output_per_mtok": 7.0},
        "fake-strong": {"tier": "strong", "input_per_mtok": 8.0, "cached_input_per_mtok": 0.8, "output_per_mtok": 16.0},
        "fake-front": {"tier": "frontier", "input_per_mtok": 20.0, "cached_input_per_mtok": 2.0, "output_per_mtok": 40.0},
    },
}
```

Test classes to land in T1 (T2/T3 append more classes to this file):
- `BudgetDemoteTests`: mid→cheap (`fake-mid-a` → dispatched `fake-cheap`, demoted True);
  strong→mid (first-in-file-order `fake-mid-a`); frontier→strong; cheap floor no-op;
  unknown-id no-op with the pinned note substring; `model_id=None` → assumed-mid note +
  dispatched `fake-cheap`; prefs pin on the target tier wins
  (`prefs={"pins": {"cheap": "fake-mid-b"}, "excludes": [], "notes": [], "source": None}` →
  dispatched `fake-mid-b`); target tier emptied by excludes
  (`excludes=["fake-cheap"]`, demoting from mid) → no demotion + the never-two-rung note.
- `BudgetRunTaskTests` (fake runner/verify_runner recording argvs): budget run of a task
  pinned `fake-mid-a` whose verify passes first try → first dispatch argv contains
  `fake-cheap`, result `status=="done"`, `escalations==[]`, `result["budget"]["demoted"]` is
  True; budget run whose verify fails once then passes → `escalations == ["fake-mid-a"]`
  (the ladder from the demoted cheap model climbs back to the standard tier first) and
  `model_used == "fake-mid-a"`.
- `BudgetByteStabilityTests`: `run_task(..., budget=False)` (and with the kwarg omitted)
  returns exactly the key set `{"id","status","model_used","escalations","verify_rc"}`;
  `main(["run", "--kit", tmp, "--task", "T1", "--dry-run", "--no-prefs"])` output contains no
  line starting `budget:`.
- `BudgetDryRunTests`: with `mock.patch.object(ce, "load_pricing", return_value=BUDGET_PRICING_FIXTURE)`
  and a temp kit dir (reuse the TASKS fixture shape from `tests/test_copilot_execute.py`,
  task pinned `fake-mid-a`),
  `main(["run", "--kit", tmp, "--task", "T1", "--dry-run", "--budget", "--no-prefs"])` prints
  the pinned `budget: demoted mid -> cheap — dispatching fake-cheap (standard: fake-mid-a)`
  line and a `dispatch:` line containing `fake-cheap`; TASKS.md bytes unchanged after the
  call; additionally patch `subprocess` in the loaded module to raise if touched (mirror the
  existing dry-run negative-proof pattern).
- `BudgetProfileFlagTests`: `--budget --budget-profile ZZ` exits 2 and stderr contains
  `unknown task profile 'ZZ'`.

**Acceptance.**
- `budget_demote` exists with the pinned semantics; the only tier→model resolution it does is
  via `copilot_prefs.resolve_tier`.
- `run --help` lists `--budget` and `--budget-profile`; `review --help` and `status --help`
  do not.
- Without `--budget`, dry-run output, `run_task` result keys, and NOTES writes are
  byte-identical to before this task.
- All new tests pass; `tests/test_copilot_execute.py` is byte-unchanged and green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_copilot_budget.py' -v && python3 bin/copilot_execute.py run --help | grep -q -- '--budget-profile' && ! python3 bin/copilot_execute.py review --help | grep -q -- '--budget' && git diff --quiet -- tests/test_copilot_execute.py && python3 -m unittest discover -s tests -p 'test_copilot_execute.py'
```

### T2 — Honest est. cost report: `budget_report`, verdict lines, NOTES record
- status: done
- model: sonnet
- depends: T1

**Brief.** Files: `bin/copilot_execute.py` (edit) and `tests/test_copilot_budget.py`
(append-only — every T1 class/method stays byte-intact). This is PLAN D5: estimates only,
labeled, allowed to condemn the feature; a report failure never flips a task's status.

In `bin/copilot_execute.py`:

1. Add `_load_pricing_module()` mirroring `_load_prefs_module()` byte-for-byte in pattern
   (module-global `_pricing_mod`, importlib by absolute path to `bin/copilot_pricing.py`).
   Cost math is ONLY ever `_load_pricing_module().est_cost(...)` — never re-implemented.
2. Add a pure function `budget_report(pricing, binfo, escalations, profile, prefs=None)`
   below `budget_demote`. Semantics:
   - Actual chain = `[binfo["dispatched_model"]] + list(escalations)`. If any chain entry is
     `None` → unpriced with reason `"dispatched at agent default — model unknown to the driver"`.
   - Standard side: `standard = binfo["standard_model"]`; when that is `None`, substitute
     `resolve_tier(pricing, binfo["standard_tier"], prefs)` (via `_load_prefs_module()`) and
     label it `assumed-mid` style: label string is `f"assumed-{binfo['standard_tier']}"`;
     if that resolves to `None` → unpriced with reason
     `f"no model resolves for the assumed standard tier {binfo['standard_tier']!r}"`.
   - Price each leg with `est_cost(pricing, profile, model_id)` (defaults for
     `cache_hit`/`today`); catch `KeyError` → unpriced with the caught message as reason.
   - Priced result dict:
     `{"priced": True, "standard_label", "standard_usd", "standard_aic", "actual_usd", "actual_aic", "dispatches": len(chain), "delta_usd": standard_usd - actual_usd, "profile": profile}`.
     Unpriced: `{"priced": False, "reason", "profile": profile}`. Never both shapes at once;
     never a fabricated number.
3. Pinned stdout lines, printed by `cmd_run` right after the T1 `budget:` line on real budget
   runs (`delta_usd >= 0` → first form):
   - `f"budget est.: saved ${delta_usd:.4f} — actual ${actual_usd:.4f} ({actual_aic:.1f} AIC) across {dispatches} dispatch(es) vs standard ${standard_usd:.4f} ({standard_aic:.1f} AIC, single dispatch, assumes first-try) [profile {profile} estimate — not a bill]"`
   - `f"budget est.: BACKFIRED — overspent ${-delta_usd:.4f} — actual ${actual_usd:.4f} ({actual_aic:.1f} AIC) across {dispatches} dispatch(es) vs standard ${standard_usd:.4f} ({standard_aic:.1f} AIC, single dispatch, assumes first-try) [profile {profile} estimate — not a bill]"`
   - `f"budget est.: unpriced — {reason} (no dollars fabricated)"`
4. Wire into `cmd_run`'s real path only (NOT dry-run — dry-run keeps T1's single demotion
   line): after `run_task` returns with budget active, compute
   `report = budget_report(pricing, result["budget"], result["escalations"], args.budget_profile, prefs)`,
   store it as `result["budget_report"]`, print the verdict line. Wrap the call so ANY
   exception degrades to the unpriced line with the exception text as reason — the task's
   status/exit code are already decided by the verify outcome and must not change.
5. `append_note`: when `result` carries `"budget"` and `"budget_report"`, append ONE line to
   the block, directly after the `- verify: exit {rc}` line and before any
   `lesson-candidate` line. Pinned format (single line, tokens contain no spaces; chain
   joined with `+`; `delta_usd` carries an explicit sign):
   - priced: `f"- budget: standard={standard_token} actual={chain_token} profile={profile} est_standard_usd={standard_usd:.4f} est_actual_usd={actual_usd:.4f} delta_usd={delta_usd:+.4f}"`
     where `standard_token` is the standard model id or `f"assumed-{tier}"`, and
     `chain_token = "+".join(chain)` or `agent-default`.
   - unpriced: `f"- budget: standard={standard_token} actual={chain_token} profile={profile} est_standard_usd=unpriced est_actual_usd=unpriced delta_usd=unpriced"`.
   No budget keys in `result` → `append_note` output is byte-identical to today.

Tests to append (`tests/test_copilot_budget.py`):
- `BudgetReportTests`: derive expected dollars by calling
  `copilot_pricing.est_cost(BUDGET_PRICING_FIXTURE, "M", ...)` in the test itself (importlib
  load), never hand-copied constants — plus ONE hand-computed spot check:
  `est_cost(fixture, "M", "fake-cheap")["usd"]` equals `0.048` within 1e-9
  (0.1M × (0.2×1.0 + 0.8×0.1)/1e6-scaled + 0.01M × 2.0). Cover: first-try budget run →
  `saved`, `delta_usd > 0`; escalated run (chain cheap+mid vs standard mid) →
  `delta_usd < 0` and the printed line contains `BACKFIRED` and `not a bill`; agent-default
  chain → unpriced with the pinned reason; unknown profile at report time → unpriced (no
  crash, status unchanged).
- `BudgetNotesTests`: run a stubbed budget run against a temp kit; NOTES.md block contains
  exactly one `- budget: ` line matching the regex
  `^- budget: standard=\S+ actual=\S+ profile=M est_standard_usd=(\d+\.\d{4}|unpriced) est_actual_usd=(\d+\.\d{4}|unpriced) delta_usd=([+-]\d+\.\d{4}|unpriced)$`;
  a non-budget run writes a block with NO `- budget:` line.

**Acceptance.**
- Every dollar the driver prints for budget mode carries the `estimate — not a bill` label;
  the backfire case prints `BACKFIRED` verbatim; unpriced cases print the pinned unpriced
  line and fabricate nothing.
- Cost math exists nowhere in `copilot_execute.py` — only `est_cost` calls through the lazy
  loader (no `input_per_mtok` arithmetic in the diff).
- A report exception cannot change a task's status or exit code.
- T1 test classes byte-intact; full new-file suite green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_copilot_budget.py' -v && grep -q 'BACKFIRED' bin/copilot_execute.py && grep -q 'not a bill' bin/copilot_execute.py && ! grep -n 'input_per_mtok' bin/copilot_execute.py && python3 -m unittest discover -s tests -p 'test_copilot_execute.py'
```

### T3 — `budget --kit` ledger subcommand
- status: done
- model: sonnet
- depends: T2

**Brief.** Files: `bin/copilot_execute.py` (edit) and `tests/test_copilot_budget.py`
(append-only). Kit-level self-measurement (PLAN D5): total the per-run NOTES records and say
plainly whether budget mode is winning on this kit. Read-only over the kit dir; zero
dispatch, zero pricing math (the dollars were already recorded).

1. New subparser: `budget` with `--kit` (required, help:
   `"kit directory (reads NOTES.md; no dispatch, no spend)"`), handler `cmd_budget`.
2. `cmd_budget(args)`: read `Path(args.kit) / "NOTES.md"`.
   - File absent → print `f"no NOTES.md under kit dir {args.kit} — no budget runs recorded."`
     and return (exit 0).
   - Parse blocks by the existing heading convention (`## <ts>{EM_DASH}<task_id>` — reuse
     `EM_DASH`, take the LAST heading token split as in `append_note`); within each block
     collect lines starting `- budget: `; parse the remainder as whitespace-separated
     `key=value` tokens. A line whose tokens don't include all six pinned keys is skipped
     with `f"note: skipped malformed budget line: {line}"` printed to stdout.
   - No budget lines found → print
     `f"no budget runs recorded in {notes_path} — nothing to report."` and return (exit 0).
   - Output (pinned shape) — AMENDED by T7/B2 (`grep -c 'not a bill'` on rendered output was 0
     and a zero-priced ledger fabricated `est. net $+0.0000`; both are honesty defects and the
     fix below is load-bearing, not optional), by T7/A4 (a blocked run must never be credited
     with a saving), and by T9 (a NEW pure helper
     `_render_money(total, n_priced, n_total)` — `n_priced == 0` -> `"no priced runs to total"`
     with no `$` at all; `n_priced == n_total` -> `f"est. net ${total:+.4f} [estimates — not a
     bill]"`; `0 < n_priced < n_total` -> `f"est. net ${total:+.4f} over {n_priced} of
     {n_total} priced [estimates — not a bill]"` — is the ONLY place in `cmd_budget` a `$`
     format string may appear; every dollar-bearing line renders through it, so "no data" and
     "data that sums to zero" can never print the same figure again):
     - header `f"# Budget ledger — {args.kit}"`, then a caveat line directly under it —
       `"All figures are labeled estimates recorded at run time — not a bill."` — blank line;
     - one row per budget line, in file order:
       `f"{task_id}  delta_usd={delta}  standard={standard}  actual={actual}  status={status}"`
       (values verbatim from the tokens, including `unpriced`; `status` reads `unknown` when
       an older-format line carries no `status=` token);
     - blank line, then: a row whose `delta_usd` token is the literal `not-counted` (T8 item
       2 — the run made no demotion) is skipped from EVERY total — priced, unpriced, and
       excluded alike — and counted on its own `f"not-counted runs: {p}"` line. Of the
       remaining rows, those whose `status` token is not `done` are EXCLUDED from the
       headline net entirely — never counted as priced OR unpriced — but their OWN net is
       computed from whichever excluded rows' `delta_usd` parses as a float
       (`excluded_total`, over `excluded_n_priced` of `excluded_n_total` excluded rows), and
       printed on a MANDATORY line whenever `k > 0`:
       `f"excluded runs: {k} (not done — {', '.join(ids)}); their recorded net: {_render_money(excluded_total, excluded_n_priced, excluded_n_total)}"`
       (T8 item 1, BLOCKING — a blocked run is the maximum-cost case; symmetrically excluding
       its overspend along with its status would bias the ledger toward optimism; T9 — routed
       through `_render_money` so an all-unpriced excluded bucket prints no `$` at all rather
       than a fabricated `$+0.0000`). Of the remaining `done` rows, those whose `delta_usd`
       parses as a float are PRICED (`done_n_priced`), the rest are unpriced
       (`done_n_unpriced`); `done_n_total = done_n_priced + done_n_unpriced`:
       `f"priced runs: {done_n_priced} — {_render_money(done_total, done_n_priced, done_n_total)}"`
       — followed by `f"unpriced runs: {u} (excluded from the total)"` where `u` counts
       unpriced rows across EVERY status, not only `done` (T9 item 2 — pre-fix, an unpriced
       BLOCKED row was reported nowhere and the count was simply false) — then
       `f"not-counted runs: {p}"`;
     - final verdict line, exactly one of:
       `"verdict: budget mode is SAVING money on this kit"` (`done_total > 0` and
       `done_total + excluded_total >= 0`),
       `"verdict: budget mode is SAVING on completed work but LOSING overall once blocked runs are counted — consider dropping --budget"`
       (T8 item 1 — `done_total >= 0` and `done_total + excluded_total < 0`, and
       `done_total > 0`),
       `"verdict: budget mode is break-even on completed work but LOSING overall once blocked runs are counted — consider dropping --budget"`
       (T9 item 3 — same guard, but `done_total == 0`; the guard is `>= 0`, not `> 0`, because
       a `done` net of exactly 0.0 beside a large excluded overspend must not read as a bare
       break-even),
       `"verdict: budget mode is LOSING money on this kit — consider dropping --budget"`
       (`done_total < 0`),
       `"verdict: break-even"` (`done_total == 0`, `done_n_priced > 0`, combined net `>= 0`),
       `f"verdict: no priced budget runs — nothing to total (unpriced runs: {u})"`
       (`done_n_priced == 0`);
       whichever of the above is chosen, when `excluded_n_unpriced > 0` (T9 item 4 — an
       unpriceable excluded overspend contributes nothing to `excluded_total`, so it can never
       trip the suppression guard above on its own) append verbatim:
       `" (some blocked runs are unpriced — the overall figure is incomplete)"`.
3. `status`/`run`/`review` parsers untouched.

Tests to append: `BudgetLedgerTests` — temp kit with a hand-written NOTES.md containing two
priced budget lines (one positive, one negative delta), one unpriced line, one malformed
line, and one non-budget block: assert row count, the `+`-signed net total equals the sum,
the malformed-skip note, and the correct verdict for saving/losing/break-even/no-priced
variants (separate NOTES fixtures per variant); absent-file and no-budget-lines degradations
exit 0 with the pinned messages (use `contextlib.redirect_stdout` + `SystemExit` guards per
the house pattern).

**Acceptance.**
- `python3 bin/copilot_execute.py budget --kit <tempdir>` never dispatches, never writes,
  never loads prefs, and exits 0 on every degradation path.
- Verdict wording matches the pinned strings exactly (T9 adds a break-even two-halves variant
  and an unpriced-excluded qualifier suffix — see T9); the headline net covers `done` rows
  only, with excluded and not-counted rows reported on their own labeled lines.
- All prior test classes byte-intact; new-file suite and frozen execute suite green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_copilot_budget.py' -v && python3 bin/copilot_execute.py budget --help | grep -q -- '--kit' && grep -q 'LOSING money on this kit' bin/copilot_execute.py && python3 -m unittest discover -s tests -p 'test_copilot_execute.py'
```

## Phase 2 — Teaching surfaces

### T4 — The `budget` skill + all roster surfaces (four coordinated edits + docs build)
- status: done
- model: sonnet
- depends: T3

**Brief.** This task lands ALL roster-coupled edits together — doing only some leaves the
suite red (a prior kit shipped exactly that defect). Files: NEW
`copilot/.github/skills/budget/SKILL.md`; `copilot/aesop.yaml`;
`copilot/.github/copilot-instructions.md`; `tests/test_copilot_docs_content.py`;
`copilot-docs/SKILLS.md`; then regenerate with `python3 bin/copilot_docs.py build` (which may
rewrite `copilot-docs/*.html`, the spliced inventory blocks, `manifest.json` hashes, and
`aic-report.*` — never hand-edit any generated content).

1. **Skill** (`copilot/.github/skills/budget/SKILL.md`, ~45–65 lines): frontmatter is
   `name: budget` + a `description:` ONLY (any `model:` line fails the bundle suite;
   `SkillNoModelIdTests` sweeps the whole file for live model ids — tier words only,
   everywhere). Description (one line):
   `Run an execution kit on a cheaper ladder of models when the AI-Credits budget is tight — one-tier-lower dispatch with honest actual-vs-standard cost reporting. Use when the user says budget mode, run this cheaply, low on credits, or wants the savings measured.`
   Body sections (headings pinned, wording yours except where quoted):
   - `## The budget ladder` — table in tier words only: architect frontier→strong (taught —
     the driver never dispatches the planner), implementer mid→cheap (enforced by the
     driver), verifier cheap (unchanged — already the floor), reviewer strong→strong
     (**deliberately unchanged**). One sentence: savings come from exactly two moves; the
     strong reviewer is preserved because it is the defect net that catches what cheap tiers
     miss — and the instrument that would detect budget mode backfiring.
   - `## Run a kit in budget mode` — fenced bash:
     `python3 {{POLYTROPOS_ROOT}}/bin/copilot_execute.py run --kit <dir> --task <id> --budget [--budget-profile M]`
     plus: preview with `--dry-run` first (real runs spend real AI Credits); the demotion is
     exactly one tier, floor cheapest; escalation still climbs the normal ladder on a
     verified failure, so the first rung up is the tier the task would have started at; do
     not combine `--budget` with `--max-escalations 0` (failures would go straight to
     blocked).
   - `## Read the measurement — it can say budget mode failed` — the `budget est.:` line is
     a labeled estimate (task profile, single-dispatch first-try counterfactual), never a
     bill; `BACKFIRED` means the escalations cost more than the demotion saved; fenced bash
     `python3 {{POLYTROPOS_ROOT}}/bin/copilot_execute.py budget --kit <dir>` totals the
     kit; if the verdict says LOSING, drop `--budget` for the rest of that kit — believe the
     ledger, not the theory. With only two roles downgraded, a single escalation can erase a
     whole run's saving.
   - `## Reviews run at full strength — use them more, not less` — `review` takes no budget
     flag by design; budget mode's cheap implementer makes the phase review MORE valuable, so
     run one at every phase boundary (it is priced per phase, not per task).
   - `## The planner under budget` — the architect drop (frontier→strong) is taught, not
     enforced: pick a strong-tier model for `/architect` runs via the `/model` picker or
     `--model`, choosing a candidate from
     `python3 {{POLYTROPOS_ROOT}}/bin/copilot_pricing.py models` — never from memory.
   - `## Same-named agent` — verbatim: `There is no budget agent — budget mode is a
     skill-only capability in this bundle. The driver still dispatches the existing
     implementer and reviewer custom agents; --budget changes which tier the implementer
     dispatch runs on, never which agent runs it.`
   - `## Installed?` — copy the two-sentence paragraph byte-for-byte from
     `copilot/.github/skills/usage/SKILL.md`.
2. **`copilot/aesop.yaml`**: append `    - budget` as the last entry of the `skills:` list
   (set-equality is what is tested; keep the doctrine sentence byte-intact). In the
   instructions block, replace the substring
   `/effort, /architect, or /execute in the prompt` with
   `/effort, /architect, /execute, or /budget in the prompt` (single occurrence).
3. **`copilot/.github/copilot-instructions.md`**: the same single substring replacement
   (`/effort, /architect, or /execute in the prompt` →
   `/effort, /architect, /execute, or /budget in the prompt`). Nothing else changes.
4. **`tests/test_copilot_docs_content.py`**: in `EXPECTED_SKILLS` (lines ~62–65), change the
   first entry line from
   `    "architect", "bench-routing", "context-weight", "effort", "escalate", "execute",` to
   `    "architect", "bench-routing", "budget", "context-weight", "effort", "escalate", "execute",`.
   No other byte in the file changes. (`EXPECTED_AGENTS` is untouched — no budget agent,
   PLAN D8.)
5. **`copilot-docs/SKILLS.md`**: insert an authored `## budget` section between
   `## bench-routing` and `## context-weight` (headings are set-compared; keep alphabetical
   order for humans). It MUST contain the literal phrases `**When to use it.**`,
   `**How to request it.**`, and `**Safety and cost notes.**` (the test lowercases the body
   and searches for them), a `**Same-named agent.** No — budget is a skill-only capability in
   this bundle.` line, zero live model ids, and — pinned honesty rule — never write the
   phrase "slash command" in the new section (any sentence containing both "slash" and
   "command" must carry a negation; avoiding the phrase avoids the trap; bare `/budget` is
   safe). Content: when (kit run under AIC pressure), how (type `/budget` or ask to run the
   kit cheaply), what it does (one-tier-lower dispatch, unchanged escalation ladder, strong
   reviews preserved), safety/cost (estimates never bills, BACKFIRED honesty, the
   `budget --kit` ledger, dry-run first).
6. Run `python3 bin/copilot_docs.py build` from the repo root, then the full test suite.

**Acceptance.**
- All four roster surfaces agree: skill dir, aesop.yaml list, `EXPECTED_SKILLS`, SKILLS.md
  `##` headings.
- The skill has no `model:` frontmatter line and no live pricing-key model id anywhere.
- Doctrine sentence unchanged in both files; both files carry the updated `/budget` sentence.
- `copilot-docs` generated blocks/html/aic-report were produced by the builder, not by hand.
- FULL suite green (this is the task most likely to break a distant test — prove it didn't).

**Verify.**
```bash
python3 -m unittest discover -s tests && test -f copilot/.github/skills/budget/SKILL.md && grep -q '^## budget' copilot-docs/SKILLS.md && grep -q -- '- budget' copilot/aesop.yaml && grep -q '/budget' copilot/.github/copilot-instructions.md && ! grep -q 'model:' copilot/.github/skills/budget/SKILL.md
```

### T5 — One pinned budget paragraph in the `execute` skill
- status: done
- model: haiku
- depends: T3

**Brief.** File: `copilot/.github/skills/execute/SKILL.md` ONLY (BODY-only edit; frontmatter
byte-intact; file-disjoint from T4). Insert the following paragraph verbatim, as its own
block, directly AFTER the existing paragraph that ends
`shows what is active).` (the prefs paragraph under "## Run a task") and BEFORE the
`## Verify independently` heading:

```markdown
Budget mode: add `--budget` to `run` to dispatch one tier lower than the task's pin (floor:
the cheapest tier) and print an honest estimated actual-vs-standard comparison afterwards —
escalation still climbs the normal ladder on a verified failure, and
`python3 {{POLYTROPOS_ROOT}}/bin/copilot_execute.py budget --kit <dir>` totals what
budget mode saved or overspent on the kit so far. `review` takes no budget flag: phase
reviews deliberately stay at full strength. See the `budget` skill.
```

If the pinned anchor paragraph is not found verbatim, STOP and report — do not guess a
placement. No other line in the file changes; no model id appears in the new text.

**Acceptance.**
- The paragraph appears once, verbatim, at the pinned location; frontmatter and every other
  line byte-intact (`git diff` shows only the insertion).
- Bundle suite green (covers the no-model-id sweep over the edited skill).

**Verify.**
```bash
grep -q -- '--budget` to `run`' copilot/.github/skills/execute/SKILL.md && grep -c 'budget --kit' copilot/.github/skills/execute/SKILL.md | grep -qx '1' && python3 -m unittest discover -s tests -p 'test_copilot_bundle.py'
```

## Phase 3 — Proof

### T6 — Full-suite + docs-vs-engine honesty cross-check + fence sweep
- status: done
- model: haiku
- depends: T4, T5, T7

**Brief.** No file edits. This task exists because a prior kit shipped documentation that
contradicted what the engine actually printed — you re-derive, from the real engines, that
every teaching claim is true, then prove the fences held. Checklist (each item maps to a
clause of the verify block; if ANY fails, report `blocked` with the failing clause — do NOT
fix anything):
1. Full test suite green.
2. Every flag the budget skill names exists on the real argparse surface: `--budget`,
   `--budget-profile`, `--dry-run`, `--max-escalations` in `run --help`; `--kit` in
   `budget --help`.
3. Fence proofs: `review --help` shows no budget flag; the frozen files are byte-clean in
   git; no test or engine invokes a real `copilot` binary (the only `copilot` executions in
   the new test file are stub paths/fake runners — grep proves no bare `copilot -p` /
   `copilot --agent` strings outside docstrings).
4. Honesty spot-check: `grep` shows the pinned labels (`not a bill`, `BACKFIRED`,
   `no dollars fabricated`) present in `bin/copilot_execute.py`, and `Path.home` absent from
   both `bin/copilot_execute.py` and `tests/test_copilot_budget.py`.

**Acceptance.**
- All verify clauses pass from a clean run; discrepancies reported verbatim, not patched.

**Verify.**
```bash
python3 -m unittest discover -s tests && python3 bin/copilot_execute.py run --help | grep -q -- '--budget' && python3 bin/copilot_execute.py run --help | grep -q -- '--budget-profile' && python3 bin/copilot_execute.py budget --help | grep -q -- '--kit' && ! python3 bin/copilot_execute.py review --help | grep -q -- '--budget' && git diff --quiet -- data skills codex bin/copilot_prefs.py bin/copilot_pricing.py tests/test_copilot_execute.py tests/test_copilot_prefs.py tests/test_copilot_pricing.py copilot-docs/WORKFLOWS.md && python3 -c "import ast,sys;bad=[f for f in ('bin/copilot_execute.py','tests/test_copilot_budget.py') if [n for n in ast.walk(ast.parse(open(f).read())) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='home']];sys.exit(1 if bad else 0)" && grep -q 'no dollars fabricated' bin/copilot_execute.py
```

## Phase 4 — Review remediation (added mid-run 2026-07-25 by the orchestrator)

### T7 — Fix the two blocking review findings and the six advisories
- status: done
- model: sonnet
- depends: T5
- independent: no

**Brief.** The Phase 1 opus review found 2 BLOCKING and 6 ADVISORY defects, all confirmed
against running code by both the reviewer and the orchestrator. Full detail with repro
commands is in `NOTES.md` under "Phase 1 review". Fix all eight. Files:
`bin/copilot_execute.py`, `tests/test_copilot_budget.py`, and this `TASKS.md` (T3's pinned
strings — see B2). Standing rules from the preamble bind.

**B1 (blocking) — restore PLAN D4's standard+1 bound.** `run_task` computes
`ladder = escalation_ladder(pricing, model, prefs=prefs)` from the DEMOTED model. Because
`escalation_ladder` seeds `seen = {model_id}`, the standard model is absent from the dedup
set under budget, so it can reappear AND the tier scan may resolve a different model than the
task's own pin — with a legal cross-tier pin the chain grows by TWO. Fix: when budget is
active, the first rung must be the task's OWN standard model. Prepend
`binfo["standard_model"]` (when non-None and not already the head) and dedupe the
tier-scanned rungs against it, so the chain is exactly
`[demoted] + [standard_model] + <standard ladder above standard_tier>`. Do NOT edit
`escalation_ladder` itself — it is shared with the non-budget path and must stay
byte-behavioural. Two properties to prove by test: (a) for every task pin, budget chain
length <= standard chain length + 1; (b) the escalate-back rung is the model the task pinned,
not merely a model of that tier (use a non-first-in-file-order pin such as a second model of
the mid tier in the fixture).

**B2 (blocking) — label every dollar the ledger prints, and stop fabricating a zero.**
`cmd_budget` prints `priced runs: N — est. net $X` and per-row `delta_usd=` values with no
`estimate — not a bill` label; PLAN's tripwire is unconditional. Also, with zero priced rows
it prints `est. net $+0.0000`, a number invented from nothing. Fix all three:
- totals line becomes
  `f"priced runs: {n} — est. net ${total:+.4f} (positive = saved) [estimates — not a bill]"`
- add a header caveat line directly under the `# Budget ledger — <kit>` header:
  `"All figures are labeled estimates recorded at run time — not a bill."`
- when `n == 0`, print NO net figure at all: emit `"priced runs: 0 — no priced runs to total"`
  followed by the existing unpriced count and the existing `no priced budget runs` verdict.
- ALSO amend T3's brief in this same file so the pinned strings match the fix — the defect
  originates there (`defect: T3 kind=contradictory-acceptance`), and leaving the brief
  contradicting the code would re-introduce it on any replay.

**A3 — a cross-tier pin must not claim a demotion it did not make.** When
`resolve_tier(target_tier)` returns a candidate whose OWN tier is not strictly below
`standard_tier`, treat it as no-demotion: `demoted = False`, `dispatched_model = model_id`,
note `f"tier {target_tier!r} is pinned to {candidate} (tier {cand_tier}) — not below {standard_tier}; no demotion"`.

**A4 — never credit a blocked run with a saving.** Add `status=<status>` to the `- budget:`
NOTES line (append it as a seventh token; the ledger's six-key validity check must still
pass, so treat unknown extra tokens as allowed). In `cmd_budget`, add a `status=` column to
each row and EXCLUDE non-`done` rows from the net, printing
`f"excluded runs: {k} (not done — {', '.join(ids)})"` when k > 0.

**A5 — render the agent-default leg instead of dropping it.** `append_note`'s
`dispatch_chain = [m for m in (...) if m]` silently shortens the chain. Replace the filter
with an in-place substitution: `None` renders as `agent-default`, so a three-dispatch chain
reads `agent-default+<m2>+<m3>`.

**A6 — cover the `assumed` marker.** Two mutations currently survive green: replacing
`f"assumed-{...}"` in `append_note` with a literal, and dropping `(assumed {tier})` from
`_format_budget_line`. Add tests that pin BOTH strings, plus a test of `budget_report`'s
PRICED `assumed-<tier>` branch (currently only the unpriced path is covered).

**A7 — regression-test the report-exception guard.** Narrowing `except Exception` in
`cmd_run`'s report wrapper survives green today. Add a test that patches `ce.budget_report`
to raise and asserts the task's `status`, `verify_rc`, and the process exit code are
unchanged, and that the unpriced line is printed.

**A8 — close the live-roster fence hole.** The two `main()`-invoking tests at roughly lines
231–243 (`test_dry_run_without_budget_flag_prints_no_budget_line`) and 402–420
(`test_non_budget_run_has_no_budget_line`) read the real `data/pricing.copilot.json`. Patch
`ce.load_pricing` to `BUDGET_PRICING_FIXTURE` in both.

**Acceptance.**
- Budget chain length never exceeds standard + 1 for any pin combination in the fixture, and
  the escalate-back rung is the task's own pinned model — both proven by test.
- `python3 bin/copilot_execute.py budget --kit <any>` output contains `not a bill`; a
  zero-priced ledger prints no net dollar figure.
- T3's brief in TASKS.md matches the shipped ledger strings.
- All six advisories fixed, each with a test that FAILS when the fix is reverted.
- Byte-stability without `--budget` still holds; full suite green.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_copilot_budget.py' -v && T=$(mktemp -d) && printf '## 2026-01-01T00:00:00 — T1\n\n- verify: exit 0\n- budget: standard=a actual=b profile=M est_standard_usd=1.0000 est_actual_usd=0.5000 delta_usd=+0.5000 status=done\n' > "$T/NOTES.md" && python3 bin/copilot_execute.py budget --kit "$T" | grep -q 'not a bill' && grep -q 'estimates — not a bill' bin/copilot_execute.py && grep -q 'agent-default' bin/copilot_execute.py && ! grep -q 'if m\]' bin/copilot_execute.py && python3 -m unittest discover -s tests
```

### T8 — Close the final review: un-bias the ledger, stop mis-attributing BACKFIRED, correct the docs
- status: done
- model: sonnet
- depends: T7
- independent: no

**Brief.** The final opus review found 1 BLOCKING and 5 advisories after T7. Full detail with
repro commands is in NOTES.md. Fix items 1–4 below; 5 and 6 are decisions, recorded not coded.
Files: `bin/copilot_execute.py`, `tests/test_copilot_budget.py`,
`copilot-docs/SKILLS.md`, `copilot/.github/skills/budget/SKILL.md`,
`copilot/.github/skills/execute/SKILL.md`, and T3's block in this `TASKS.md`. Standing rules bind.

**1 (BLOCKING) — the ledger must not report SAVING on a kit that lost money.** T7's A4 fix
excludes non-`done` rows SYMMETRICALLY, so a blocked run's overspend vanishes from the net.
A blocked run is the maximum-cost case (it climbed the whole ladder), so the exclusion is
biased toward optimism and defeats PLAN's kill-switch tripwire. Verified: a ledger whose rows
net −$1.6380 currently prints `verdict: budget mode is SAVING money on this kit`.
Fix: keep the headline net over `done` rows (that part is right — you should not credit or
debit work that did not land against budget mode's effectiveness), but ALSO compute the
excluded rows' own net and print it as a mandatory labeled line whenever any row is excluded
(exact rendering later routed through T9's `_render_money` helper — see T9 and the current T3
block, which is the up-to-date pinned shape):
`f"excluded runs: {k} (not done — {ids}); their recorded net: ${x:+.4f} [estimates — not a bill]"`.
Then SUPPRESS an optimistic verdict when the combined net is negative: if
`done_net > 0` but `done_net + excluded_net < 0`, print
`"verdict: budget mode is SAVING on completed work but LOSING overall once blocked runs are counted — consider dropping --budget"`.
Leave the other three verdicts unchanged (T9 later widens this guard from `> 0` to `>= 0` and
adds an unpriced-excluded qualifier suffix — see T9). Amend T3's block in this TASKS.md to
match.

**2 (advisory) — a run that made NO demotion must not report BACKFIRED.** For a floor-pinned,
unknown-id, or empty-target-tier task, budget mode dispatches the identical chain standard
would, then prices it against a single first-try dispatch and blames itself. `budget_report`,
`_format_budget_report_line`, and `append_note` never consult `binfo["demoted"]`. Fix: when
`binfo["demoted"]` is false, print
`"budget est.: no demotion this run — budget mode changed nothing; not counted"` and write the
`- budget:` line with `delta_usd=not-counted` so `cmd_budget` skips it from every total (count
it on a new `not-counted runs: N` line). Add a test: a floor-pinned escalating budget run
prints no `BACKFIRED`.

**3 (advisory) — `copilot-docs/SKILLS.md` claims escalation stops at the standard tier.** The
`## budget` section says a verified failure "climbs back to the tier the task would have
started at, **never further**." False — the engine climbs the full standard ladder above that
rung (real run: `escalations=['claude-sonnet-4.6','claude-opus-4.8','claude-fable-5']`). Delete
the `never further` clause; the preceding clause is already correct. Note both SKILL.md
surfaces are correct here — only the docs section is wrong.

**4 (advisory) — three surfaces describe the ledger as totalling everything.** Post-fix that is
untrue. `copilot-docs/SKILLS.md` says "totals every recorded run"; the execute-skill paragraph
says it "totals what budget mode saved or overspent on the kit so far". State the real rule in
one sentence on all three surfaces (docs section, `budget/SKILL.md`, `execute/SKILL.md`):
the headline net covers completed runs, with blocked and not-counted runs reported separately
on their own labeled lines. Then run `python3 bin/copilot_docs.py build`.

**5 / 6 — decisions, no code.** (5b) A `- budget:` line with no `status=` token renders
`status=unknown` and is treated as not-done; that is the safe default and stays. (6) A3's
cross-tier guard is deliberately one-directional: a pin resolving BELOW the target tier still
dispatches, because PLAN D3 sanctions prefs shaping tiers, the prefs layer prints its own
cross-tier disclosure, and the direction is cost-safe. Both are recorded in NOTES, not changed.

**Acceptance.**
- A ledger with a `done` +row and a `blocked` −row that net negative does NOT print a bare
  `SAVING` verdict, and prints the excluded rows' own labeled net.
- A no-demotion budget run prints no `BACKFIRED` and contributes nothing to the net.
- Neither `never further` nor `totals every recorded run` appears in the docs section; all
  three surfaces describe the exclusion rule.
- Every new behaviour has a test that FAILS when the fix is reverted (prove on a scratchpad
  copy, never destructively in the repo).
- Byte-stability without `--budget` still holds; full suite green; docs `up to date`.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_copilot_budget.py' && L=$(mktemp -d) && printf '## a — T1\n\n- budget: standard=m actual=c profile=M est_standard_usd=0.3510 est_actual_usd=0.1170 delta_usd=+0.2340 status=done\n\n## b — T2\n\n- budget: standard=m actual=c profile=M est_standard_usd=0.3510 est_actual_usd=2.2230 delta_usd=-1.8720 status=blocked\n' > "$L/NOTES.md" && ! python3 bin/copilot_execute.py budget --kit "$L" | grep -qx 'verdict: budget mode is SAVING money on this kit' && python3 bin/copilot_execute.py budget --kit "$L" | grep -q 'their recorded net' && ! grep -q 'never further' copilot-docs/SKILLS.md && ! grep -q 'totals every recorded run' copilot-docs/SKILLS.md && python3 bin/copilot_docs.py build >/dev/null && python3 bin/copilot_docs.py check && python3 -m unittest discover -s tests
```

### T9 — Make fabricating a dollar STRUCTURALLY impossible (root-cause fix)
- status: done
- model: sonnet
- depends: T8
- independent: no

**Brief.** THIS IS A ROOT-CAUSE TASK, not another point patch. Three consecutive rounds of this
kit have shipped the same defect: a dollar figure printed from zero priced data. B2 fixed it on
the totals line; T8's A4 fix reintroduced it on the `excluded runs:` line it wrote to fix a
different optimism bias. Each round added a NEW dollar-printing path with its own ad-hoc
accumulator initialised to `0.0`, so "no data" and "data that sums to zero" render identically.
Patch the shape, not the symptom.

**1. One money renderer, used by every dollar line.** Add a single pure helper to
`bin/copilot_execute.py`:

```python
def _render_money(total, n_priced, n_total):
    """Render an estimates figure, or say plainly that there is nothing to total.

    Returns a string that NEVER contains a currency figure when n_priced == 0, and that
    discloses partial coverage when 0 < n_priced < n_total. The label is unconditional.
    """
```
Contract, pinned:
- `n_priced == 0` -> `"no priced runs to total"` (no `$`, no number, at all).
- `n_priced == n_total` -> `f"est. net ${total:+.4f} [estimates — not a bill]"`.
- `0 < n_priced < n_total` -> `f"est. net ${total:+.4f} over {n_priced} of {n_total} priced [estimates — not a bill]"`.

EVERY dollar-bearing line in `cmd_budget` must be produced by this helper — the headline
totals line and the `excluded runs:` line both. Grep your own diff: if any `$` format string
survives outside `_render_money`, the task is not done.

**2. Count unpriced rows wherever they occur, not only among `done` rows.** `unpriced runs:`
currently tallies only `done` rows, so an unpriced BLOCKED row is reported nowhere and the
count is simply false (verified: a ledger with one unpriced blocked row prints
`unpriced runs: 0`). Count unpriced rows across every status; keep the existing
`(excluded from the total)` wording.

**3. Suppression must not be escapable via break-even.** The guard is
`elif total > 0 and (total + excluded_net) < 0:`. With `done` rows netting exactly 0.0 and a
blocked row at −$5, the ledger prints `verdict: break-even` on a kit that lost money. Widen to
`total >= 0`, and word the break-even case in the same two-halves style:
`"verdict: budget mode is break-even on completed work but LOSING overall once blocked runs are counted — consider dropping --budget"`.

**4. The suppression must not be defeatable by unpriceable overspend.** Because `excluded_net`
silently skips unpriced rows, a blocked run whose cost could not be priced can never trigger
suppression. When ANY excluded row is unpriced, the verdict must not claim an unqualified
positive outcome: append ` (some blocked runs are unpriced — the overall figure is incomplete)`
to whichever verdict is chosen.

**5. Amend the pinned strings in T3 and T8 in this TASKS.md** to match, exactly as B2 required —
the architect's pinned strings are the origin of this defect family, and leaving them stale
guarantees a fourth recurrence on replay.

**Acceptance.**
- No `$` format string anywhere in `cmd_budget` outside `_render_money`.
- A ledger whose only excluded row is unpriced prints NO dollar figure on the excluded line and
  reports `unpriced runs: 1`.
- A ledger with 2 excluded rows where 1 prices discloses `over 1 of 2 priced`.
- `done` net exactly 0.0 plus a blocked −$5 does NOT print a bare `break-even`.
- A verdict qualified when any excluded row is unpriced.
- Tests for each, each proven to fail on revert (scratchpad copy only, never destructive here).
- Byte-stability without `--budget` holds; full suite green; docs `up to date`.

**Verify.**
```bash
python3 -m unittest discover -s tests -p 'test_copilot_budget.py' && A=$(mktemp -d) && printf '## a — T1\n\n- budget: standard=m actual=c profile=M est_standard_usd=unpriced est_actual_usd=unpriced delta_usd=unpriced status=blocked\n' > "$A/NOTES.md" && ! python3 bin/copilot_execute.py budget --kit "$A" | grep -q '\$' && python3 bin/copilot_execute.py budget --kit "$A" | grep -q 'unpriced runs: 1' && B=$(mktemp -d) && printf '## a — T1\n\n- budget: standard=m actual=c profile=M est_standard_usd=1.0 est_actual_usd=0.5 delta_usd=+0.5000 status=done\n\n## b — T2\n\n- budget: standard=m actual=c profile=M est_standard_usd=1.0 est_actual_usd=1.5 delta_usd=-0.5000 status=done\n\n## c — T3\n\n- budget: standard=m actual=c profile=M est_standard_usd=1.0 est_actual_usd=6.0 delta_usd=-5.0000 status=blocked\n' > "$B/NOTES.md" && ! python3 bin/copilot_execute.py budget --kit "$B" | grep -qx 'verdict: break-even' && python3 -m unittest discover -s tests
```
