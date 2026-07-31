# PLAN — crossrepo-trend

autonomy: advisory

(Executes in advisory posture: re-route recommendations during this run are print-only.)

Two features on top of the shipped `--history` mode of `bin/routing_scorecard.py`, per binding
upstream scope decisions:

1. **Cross-repo `--history`** — `--kits-dir` becomes REPEATABLE. One dir → output BYTE-IDENTICAL
   to today. More than one → each dir is scanned, kit rows are namespaced `<label>/<kit>` so two
   repos' same-named kits don't collide, tiers and re-route tallies aggregate GLOBALLY, and
   dollars keep riding the single `--projects-dir` (`~/.claude/projects` holds every repo's
   transcripts; `sc.find_main_transcript` rglobs, so a kit's `session:` id resolves regardless
   of which repo it ran in) with the coverage/degradation rules UNCHANGED.
2. **Time-series** — `--history --snapshot` writes the history card as a dated JSON file into a
   GITIGNORED snapshot store (the ONE sanctioned real write in the whole script besides
   `--demo`'s temp dirs), and `--history --trend` reads every stored snapshot and renders
   per-tier FIRST-TRY RATE over time as a TEXT TABLE (no charts — deferred by design), with
   dollars-over-time surfaced only where snapshots carry them. A trend needs ≥2 points; with 0
   or 1 it says so — never fabricates.

The #1 crux: **additive-only, a FIFTH time.** Existing flags, function signatures, output
shapes, exit codes, and ALL FOUR prior demos' numbers (`--demo`, `--demo --live`,
`--demo --history`, `--demo --by-task`) stay byte-stable; the FOUR existing scorecard test
files (`tests/test_routing_scorecard.py`, `tests/test_reroute_live.py`,
`tests/test_routing_history.py`, `tests/test_per_task_dollars.py`) stay BYTE-UNTOUCHED
(enforced by `git diff --quiet` in every verify; new tests go in
`tests/test_crossrepo_trend.py`). A lone `--kits-dir` and the `--demo --history` output must be
byte-identical to today. NO skill is edited by this kit — `skills/` stays byte-unchanged
(D10) — so per the CLAUDE.md invariant there is no shared-contract edit at all.

## Goal

Ship, end to end, with the full suite green and `bin/routing_scorecard.py` extended additively
a FIFTH time:

1. **`bin/routing_scorecard.py` extended** (additive only): repeatable `--kits-dir` with
   `label=path` override tokens and repo-basename label derivation (D2/D3/D4); `--snapshot` /
   `--trend` / `--snapshot-dir` flags with the pinned rejections and dispatch (D5/D6/D7); pure
   tested functions (`parse_kits_dir_token`, `derive_repo_label`, `resolve_kits_dirs`,
   `write_snapshot`, `read_snapshots`, `build_trend`, `render_trend_markdown`, `run_trend`);
   one guarded hook in `render_history_markdown`; and a `--demo --history --trend` synthetic
   smoke (`run_trend_demo`) that exercises BOTH features — two synthetic repos, two dated
   snapshots, one text trend table (D8).
2. **`tests/test_crossrepo_trend.py`** — new stdlib unittest file: token/label grammar,
   namespacing and global aggregation, cross-repo dollars, single-dir byte-shape proof,
   snapshot write scope + date-grammar traversal guard, trend degradations (0/1/malformed
   snapshots), pricing-free pure `--trend`, read-only proofs, all four prior demos' regression
   checks, the new demo's pinned card, and the gitignore proof.
3. **`.gitignore`** gains the `/trends/` snapshot-store entry, proven by `git check-ignore`.
4. **`docs/ROUTING-TRENDS.md`** (new) + a pinned pointer paragraph appended to
   `docs/ROUTING-HISTORY.md` (superseding its cross-repo/time-series deferral bullet
   honestly), and one pinned CLAUDE.md run-line.

**Done looks like:** `python3 -m unittest discover -s tests` green (baseline 385 tests, plus
`tests/test_crossrepo_trend.py`); `python3 bin/sync_pricing_refs.py --check` exits 0; the four
prior demos still yield their pinned numbers — `--demo --json` (quality 6/6/3/1/1/1, mix
{haiku 1, sonnet 4, fable 1}, survival 0.75), `--demo --live --json` (one sonnet→opus
recommendation for L5+L6, budget cap 2 / applied 0 / remaining 2, autonomy advisory),
`--demo --history --json` (haiku (3,3,2,1,0,0), sonnet (6,5,2,1,1,1), opus (2,1,1,0,0,0),
frontier (1,0,0,0,0,0), reroutes {1,0,1}, dollars coverage "partial"),
`--demo --by-task --json` (the per-task-dollars D9 card: tasks [P1..P5], ag-warm cluster over
[P3, P4], unattributed ["ag-reviewer"], coverage partial); the new
`python3 bin/routing_scorecard.py --demo --history --trend [--json]` yields the D8 pinned
2-point trend; `git check-ignore -q trends/2026-01-01.json` exits 0; a lone-`--kits-dir`
`--history --json` card has EXACTLY the eight pre-existing top-level keys (no `kits_dirs`) and
unprefixed kit names; `git status` shows changes ONLY to sanctioned targets (edits:
`bin/routing_scorecard.py`, `.gitignore`, `docs/ROUTING-HISTORY.md`, `CLAUDE.md`; new:
`tests/test_crossrepo_trend.py`, `docs/ROUTING-TRENDS.md`, this kit + its agents); and
`git diff --quiet -- tests/test_routing_scorecard.py tests/test_reroute_live.py
tests/test_routing_history.py tests/test_per_task_dollars.py bin/cost_report.py
bin/session_cost.py bin/copilot_execute.py data skills` stays clean throughout — `skills`
covers every skill and the generated mirrors; NO skill edit is part of this kit.

## Repo facts (confirmed by the architect — trust these, do not re-derive)

- **Suite:** `python3 -m unittest discover -s tests [-p '<file>.py']` — never the dotted-module
  form (broken on this machine). Baseline 385 tests, green. `python3 bin/sync_pricing_refs.py
  --check` must stay exit 0. Python is stdlib-only; no pip/pytest.
- **`bin/routing_scorecard.py` today** (~2200 lines; all reusable in place — extend, never
  fork; NEVER re-implement or edit any of these): `_load(name)` importlib loader with
  `ce = _load("copilot_execute")`, `sc = _load("session_cost")`, `cr = sc.cr`;
  `TASK_MODEL_TIERS = {"fable": "frontier"}` + `tier_for`; `LIVE_TIER_ORDER = ("haiku",
  "sonnet", "opus", "frontier")`; `parse_outcomes` / `parse_reroutes` / `parse_sessions` /
  `parse_agents`; `history_tier_stats(tasks, outcomes, applied_events)`;
  `tally_reroutes(events)`; `scan_kits(kits_dir) -> (records, notes)` (sorted subdirs; records
  `{"kit", "tasks", "outcomes", "events", "sessions", "notes"}`; every top-level note it
  returns is already prefixed `<kit>: `); `kit_cost_summary(session_ids, projects_dir,
  no_subagents, vs, pricing) -> (cost_or_None, transcripts, notes)` (ONE `sc.collect` per
  scope — global message-id dedupe absorbs resumed-transcript overlap);
  `build_history(kits_dir, records, kit_costs, dollars, notes) -> card` (top-level keys
  EXACTLY `schema_version, generated_at, kits_dir, kits, tiers, reroutes, dollars, notes`;
  `kits_dir` is `str(kits_dir)`; kit rows `{"kit", "tasks", "with_outcome", "first_try_pass",
  "retry_pass", "escalated_pass", "blocked", "sessions", "cost"}`; `kit_costs` is looked up by
  `rec["kit"]`); `render_history_markdown(card)` (H1 `# Routing history — cross-kit per-tier
  track record` + five H2s `## Verdict` / `## Per-tier track record` / `## Re-route history` /
  `## Kits` / `## Dollars`, then a `Notes:` block; it never prints `card["kits_dir"]`);
  `HISTORY_SCHEMA_VERSION = 1`; `_rate_pct(rate)` (`"67%"` style, `n/a` on None);
  `_first_model_of_tier(pricing, tier)`; `DEMO_VOLUMES`; `DEMO_HIST_ALPHA_TASKS_MD` /
  `DEMO_HIST_ALPHA_NOTES_MD` (5 tasks, session line `session: hist-alpha-session`) /
  `DEMO_HIST_BETA_TASKS_MD` / `DEMO_HIST_BETA_NOTES_MD` (4 tasks, one advisory reroute, no
  session) / `DEMO_HIST_GAMMA_TASKS_MD` (3 tasks, no NOTES.md); `run_history_demo(as_json)`
  (builds kits + a `projects/-demo/hist-alpha-session.jsonl` transcript — one message per tier,
  ids `demo-hist-<tier>`, model ids via `_first_model_of_tier`, volumes from `DEMO_VOLUMES` —
  then drives `main(["--history", "--kits-dir", …, "--projects-dir", …, "--no-subagents"])`);
  `run_history(args)` (the non-demo `--history` flow: dir check → `scan_kits` → the dollars
  degradation ladder over `session:` ids → `build_history` → print; loads NO pricing when no
  `session:` lines exist anywhere); `_resolve_kit_dir(kit, kits_dir)`; `MD_H2S` (frozen);
  `DEFAULT_KITS_DIR = PLUGIN_ROOT / ".claude" / "kits"`; `main()` argparse with `kit`
  positional, `--kits-dir` (currently `default=str(DEFAULT_KITS_DIR)`, single-valued),
  `--session`, `--projects-dir` (default `str(sc.DEFAULT_PROJECTS_DIR)`), `--tasks-dir`
  (append), `--include` (append), `--no-subagents`, `--vs`, `--json`, `--demo`, `--live`,
  `--history`, `--by-task`, `--live-threshold`, `--live-min-sample`, `--live-max-auto`.
  Existing main() check order: `--live`+`--session` rejection → `--history` guardrails
  (mutually exclusive with `--live`, no `--session`, no kit positional) → `--by-task`
  guardrails → the `--demo` block (`--history` → `run_history_demo`, `--live` →
  `run_live_demo`, `--by-task` → `run_by_task_demo`, else `run_demo`) → the non-demo
  `--history` branch → kit-required check → kit resolution → the `--live` branch → the plain
  path.
- **`bin/session_cost.py` reusables:** `find_main_transcript(session_id, projects_dir)` rglobs
  `<session_id>.jsonl` ANYWHERE under projects_dir — transcripts from ANY repo resolve as long
  as projects_dir is the shared store; `discover_task_dirs`; `gather_files`; `collect` (global
  msg-id dedupe); `resolve_counterfactual_model`; `build_report`; `DEFAULT_PROJECTS_DIR`
  (`Path.home() / ".claude" / "projects"` — the ONLY sanctioned home reference, already
  borrowed by the argparse default; new code adds ZERO `Path.home()`).
- **The frozen byte-stability guard already exists:** `tests/test_routing_history.py` (18
  tests, byte-frozen) pins the single-dir `--history` card's top-level key set EXACTLY
  (`schema_version, generated_at, kits_dir, kits, tiers, reroutes, dollars, notes`), the
  per-tier key sets, and the CLI behaviors (empty kits dir, nonexistent kits dir → nonzero
  exit). It runs `--kits-dir` with exactly ONE value everywhere, including one in-process
  `rs.main([...])` call under a monkeypatched `cr.load_pricing` (the pricing-free proof).
  Keeping that file green IS the single-dir byte-stability proof.
- **Pinned prior-demo numbers** (verified on this checkout; every verify below re-asserts
  them): see "Done looks like" above.
- **`.gitignore` today** (5 lines): `.claude/settings.local.json`, `__pycache__/`,
  `.DS_Store`, a comment, `/journal/`. The journal precedent is the model for T3's entry.
- **`docs/ROUTING-HISTORY.md`** ends with the per-task-dollars pointer paragraph; its final
  line is exactly `cluster as a unit, never divided.` — T5's append anchor. Its H2 set is
  `## What it aggregates`, `## Dollars — the optional session: line`, `## Feeding the
  architect`, `## Contract safety`, `## Deliberately not built` (must stay unchanged). Its
  Deliberately-not-built section contains the bullet **Cross-repo or time-series trend
  aggregation** — the deferral this kit ships; the pointer paragraph supersedes it honestly
  (append-only, like the per-task-dollars precedent).
- **CLAUDE.md's "How to run things" block** contains the line
  `python3 bin/routing_scorecard.py --demo --by-task # per-task dollars smoke (synthetic kit; shared warm agent + missing transcript honesty proofs)`
  — T6's insertion anchor. The `For \`crossrepo-trend\` specifically:` fence paragraph was
  already added by the architect — do not touch it.
- **Skills are NOT edited by this kit.** `skills/architect/SKILL.md`'s history-consult bullet
  says run `python3 bin/routing_scorecard.py --history` and `skills/execute/SKILL.md`'s
  End-of-run offers the same command — both invocations are the default single-dir path, which
  stays byte-identical, so both skills remain accurate verbatim. The plugin is installed LIVE;
  `git diff --quiet -- skills` must stay clean after every task.
- **pricing.json tier vocabulary:** `frontier`, `opus`, `sonnet`, `haiku`; alias→tier identity
  except `fable → frontier`. Demo/test transcript model ids are computed from
  `data/pricing.json` at run time via `_first_model_of_tier` — never spelled out.

## Architecture & key decisions

- **D1 — Both features live in `bin/routing_scorecard.py` as additive extensions, not a new
  script.** Same rationale that placed `--live`, `--history`, and `--by-task` there: the
  cross-repo mode consumes exactly what `--history` already consumes (kits dirs, the shared
  projects dir, the `session_cost` pipeline), and the trend consumes `--history`'s own output
  cards; a separate script would importlib-load all of it anyway, and one script keeps ONE
  surface. ADDITIVE means: new constants, new pure functions, three new argparse flags, one
  repeatable-ified existing flag whose single-use behavior is unchanged, one guarded hook in
  `render_history_markdown`, appended (never reshuffled) logic in `run_history`, and one new
  demo combo — zero changes to existing function signatures, outputs, exit codes, or any of
  the FOUR prior demos' numbers, with all FOUR frozen test files byte-untouched.
- **D2 — `--kits-dir` becomes `action="append", default=None`; main() normalizes.** Right
  after `parse_args`: `args.kits_dir = args.kits_dir or [str(DEFAULT_KITS_DIR)]` (a list of
  raw tokens from here on). Then the new rejection (inserted with the other new rejections per
  D6): more than one token while NOT in `--history` mode →
  `sys.exit("multiple --kits-dir values are a --history affordance — pass one dir")`.
  Non-history modes use `args.kits_dir[0]` VERBATIM as the path (no `label=` parsing there —
  a plain-mode path containing `=` keeps working exactly as today, and `_resolve_kit_dir` is
  untouched). The frozen tests all pass `--kits-dir` at most once, so append semantics leave
  every frozen behavior identical.
- **D3 — Labels and the namespacing rule (pinned).** Token grammar: `LABEL=PATH` where LABEL
  matches `_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")` and contains no path
  separator; any token not matching that shape (no `=`, or a pre-`=` prefix failing the
  grammar) is ENTIRELY a path. `parse_kits_dir_token(token) -> (label_or_None, path_str)`.
  `derive_repo_label(path_str) -> str`: pure path logic (no filesystem access) — for a
  conventional `<repo>/.claude/kits` dir (i.e. `Path(path).name == "kits"` and
  `.parent.name == ".claude"`) the label is the repo directory's basename
  (`.parent.parent.name`); otherwise the dir's own basename; an empty result falls back to
  `"kits"`. `resolve_kits_dirs(tokens) -> (entries, notes)`: entries
  `{"label", "path", "explicit"}` in the given order; explicit labels win; the same resolved
  path twice keeps the first entry + a note; duplicate labels get deterministic `-2`, `-3`
  suffixes in occurrence order + a note (never a silent merge of two repos). **Namespaced mode
  ⇔ more than one resolved dir OR any explicit `label=` token.** Rationale for the explicit-
  label-on-a-lone-dir exception: today that exact token dies with `kits dir not found:
  label=path`, so giving it prefixed-output meaning breaks nothing byte-frozen — and it gives
  tests/users a one-dir way to exercise namespacing. Plain mode (exactly one dir, no explicit
  label — including the no-flag default and every existing invocation) → today's flow, kit
  names UNPREFIXED, the JSON card's key set EXACTLY today's eight keys, no `- scanned` lines:
  byte-identical. This is the pinned answer to single-dir-vs-always-prefixed: conditional,
  keyed on an input shape that cannot occur today.
- **D4 — Multi assembly (inside `run_history`, appended logic only).** After normalizing
  tokens: `entries, dir_notes = resolve_kits_dirs(args.kits_dir)`; every entry's path must be
  a dir, else `sys.exit(f"kits dir not found: {path}")` (today's message, per dir). Plain mode
  proceeds through today's body using `entries[0]["path"]` — the ONLY line that changes in the
  existing body is the one reading `args.kits_dir` (now a token). Namespaced mode: for each
  entry in GIVEN order, `scan_kits(path)`; namespace each record with
  `{**rec, "kit": f"{label}/{rec['kit']}"}`; re-emit that dir's scan notes as
  `f"{label}/{note}"` (every scan_kits note starts `<kit>: `, so this reads
  `<label>/<kit>: …`); a dir contributing zero records notes
  `f"{label}: no kits with a TASKS.md found under {path}"` (the existing global empty-note is
  guarded to plain mode only). The merged record list then flows through the EXISTING dollars
  degradation ladder verbatim (quality-only when no `session:` lines anywhere — no pricing
  load; per-kit `kit_cost_summary` keyed by the NAMESPACED kit name; ordered-unique union of
  session ids priced ONCE in the aggregate; shared-id note uses namespaced names; coverage
  `full` iff every kit has ≥1 session id AND every unique id priced, else `partial`) and ONE
  `build_history(entries[0]["path"], records, kit_costs, dollars, notes)` call — then
  post-process the returned dict: `card["kits_dir"] = None` and
  `card["kits_dirs"] = [{"label": e["label"], "path": e["path"]} for e in entries]`. Why
  post-processing instead of editing `build_history`: the function is frozen-by-policy and the
  single-dir card must keep `kits_dir` as a string with no ninth key. Markdown: ONE guarded
  hook in `render_history_markdown`, immediately after the Verdict bold line's append —
  `if card.get("kits_dirs"):` emit one line per entry, exactly `- scanned {label}: {path}`,
  then an empty line. Old cards never carry the key → every existing output byte-identical.
  Cross-repo dollars honesty: `find_main_transcript` rglobs the ONE `--projects-dir`, so ids
  recorded in any repo resolve from the shared store; a missing transcript is noted and
  skipped (never invented), exactly as today — the multi path adds NO new dollar arithmetic,
  it reuses the same ladder over a longer record list.
- **D5 — The snapshot store (the ONE sanctioned real write).** `DEFAULT_SNAPSHOT_DIR =
  PLUGIN_ROOT / "trends"` — a NEW top-level gitignored dir (T3 adds `/trends/` to
  `.gitignore`; `git check-ignore` proves it). Why not reuse `/journal/`: the fence forbids
  journal coupling — a disjoint store keeps the features independently ignorable and avoids
  any suggestion the journal pipeline reads or writes it. Filenames: `<YYYY-MM-DD>.json`, the
  date being UTC today (`datetime.now(timezone.utc).strftime("%Y-%m-%d")`) — latest-wins per
  day by plain overwrite (re-snapshotting the same day replaces that day's file; deliberate).
  `write_snapshot(card, snapshot_dir, date_str=None) -> Path`: validates `date_str` (when
  given) against `^\d{4}-\d{2}-\d{2}$` and raises `ValueError` otherwise — the path-traversal
  guard that makes escaping the snapshot dir impossible; `mkdir(parents=True, exist_ok=True)`
  on the dir; writes `json.dumps(card, indent=2) + "\n"`. This function is the ONLY writer in
  the whole script outside the demo family's own temp dirs; every non-`--snapshot` mode stays
  read-only (proven by tree-delta tests), and `--snapshot` writes ONLY under the snapshot dir
  — never a kit dir, never NOTES.md, never source. The STORED card is pure history data: the
  `snapshot written: <path>` note is appended to the PRINTED card's notes only AFTER the write,
  so it never appears inside a stored snapshot.
- **D6 — CLI wiring (pinned).** New argparse flags: `--snapshot` (store_true; help: write the
  history card as a dated JSON snapshot under --snapshot-dir — requires --history), `--trend`
  (store_true; help: render per-tier first-try rate over stored snapshots as a text table —
  requires --history; with --snapshot, snapshots first), `--snapshot-dir`
  (default `str(DEFAULT_SNAPSHOT_DIR)`; help: snapshot store dir (runtime default; override in
  tests)). `--kits-dir` help updated to note it is repeatable with `--history` and accepts
  `label=path` tokens. Rejections, inserted AFTER the existing `--by-task` guardrails and
  BEFORE the `--demo` block (so every existing combo keeps its existing message):
  `--snapshot` without `--history` → `sys.exit("--snapshot rides --history — pass --history")`;
  `--trend` without `--history` → `sys.exit("--trend rides --history — pass --history")`;
  `--snapshot` with `--demo` → `sys.exit("--demo takes no --snapshot — the demo writes only to
  its own temp dir")`; the D2 multiple-`--kits-dir`-outside-`--history` rejection. Because
  `--trend`/`--snapshot` require `--history`, they inherit ALL its mutual exclusions
  (`--live`, `--session`, kit positional, `--by-task`) with today's messages. Dispatch: in the
  `--demo` block, `--demo --history --trend` → `run_trend_demo(args.json)` (checked before the
  plain `--history` demo dispatch; `--demo --history` alone still →`run_history_demo`).
  Non-demo: `args.history and args.trend and not args.snapshot` → `return run_trend(args)`
  (scans NO kits, loads NO pricing — mirrors `--live`'s pricing-free guarantee); otherwise
  `run_history(args)`, whose tail gains: after the card is fully assembled —
  `if args.snapshot: path = write_snapshot(card, args.snapshot_dir)`; then
  `if args.trend: return run_trend(args, extra_notes=[f"snapshot written: {path}"])` (the
  trend re-reads the store, now including today's file, and the printed output is the TREND
  card ONLY); else `if args.snapshot: card["notes"].append(f"snapshot written: {path}")` and
  the normal history print. `run_trend(args, extra_notes=())`: appends the existing
  `--tasks-dir/--include are ignored…` note when those are passed, and a
  `--kits-dir is ignored by --trend without --snapshot (the trend reads stored snapshots)`
  note when `--kits-dir` was explicitly passed to a pure trend (detectable: pre-normalization
  `None` means not passed — capture the flag before normalizing); reads + builds + prints;
  exit 0 for every degraded shape.
- **D7 — The trend card and rendering (pinned).** `read_snapshots(snapshot_dir) ->
  (dated_cards, notes)`: a missing dir → `([], ["snapshot dir not found: <dir>"])`; otherwise
  consider `*.json` files only, sorted by name; a `*.json` whose name fails
  `SNAPSHOT_FILENAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")` → skipped +
  `rogue snapshot file skipped: <name>` note; an unreadable/undecodable file → skipped +
  note naming it; decoded JSON that is not a dict or lacks a dict `tiers` key → skipped +
  note; survivors returned as `(date_str, card)` ascending by date (ISO names sort
  lexicographically). `build_trend(snapshot_dir, dated_cards, notes) -> card` with the pinned
  key set `{"schema_version" (TREND_SCHEMA_VERSION = 1), "generated_at", "snapshot_dir",
  "points", "notes"}`. Each point: `{"date", "kits" (len of the stored card's kits list, 0
  when absent), "tiers": {tier: {"with_outcome", "first_try", "first_try_rate"} for tier in
  LIVE_TIER_ORDER}, "dollars"}` — tier cells read tolerantly from the stored card's
  `tiers[tier]` (an absent tier → zeros + rate None, no note: old-schema tolerance);
  `dollars` is `{"actual_usd", "delta_usd"}` when the stored card's `dollars` is a dict,
  else `None` (dollars-over-time surfaces ONLY where snapshots carry it — never recomputed,
  never fabricated). The ≥2-points rule: zero points → append
  `no snapshots found under <dir> — nothing to trend`; exactly one → append
  `one snapshot — no trend yet (a trend needs at least 2 points)` and still render the single
  point (data shown, trend claim withheld). `render_trend_markdown(card)`: H1
  `# Routing trend — per-tier first-try rate over time`; zero points → the line
  `no snapshots — n/a`; otherwise ONE table, rows = dates ascending (dates grow unboundedly;
  the four tiers are fixed — dates-as-rows keeps the table narrow), header
  `| Date | haiku | sonnet | opus | frontier | Kits | Actual $ |` with the tier columns
  generated from `LIVE_TIER_ORDER` (never retyped), tier cells
  `{first_try}/{with_outcome} ({_rate_pct(rate)})` or `n/a` when `with_outcome` is 0,
  `Actual $` cells `$x.xx` or `n/a` when the point's dollars is None; then the `Notes:` block
  (the existing pattern). JSON via the existing `--json` flag prints the trend card.
- **D8 — The demo contract (pinned): ONE new demo combo exercises BOTH features.**
  `--demo --history --trend` → `run_trend_demo(as_json)`. Rationale: the cross-repo feature
  has no flag of its own (it IS repeatable `--kits-dir`), so its smoke rides the trend demo's
  day-2 card — one sanctioned demo instead of two keeps the CLI surface additive-minimal.
  In ONE `tempfile.TemporaryDirectory`: build `repo-a/.claude/kits/hist-alpha` (existing
  `DEMO_HIST_ALPHA_TASKS_MD` + `DEMO_HIST_ALPHA_NOTES_MD`, read-only reuse) and
  `repo-a/.claude/kits/hist-beta` (beta constants), `repo-b/.claude/kits/hist-gamma` (gamma
  TASKS.md only — no NOTES.md by design), and the projects dir with
  `projects/-demo/hist-alpha-session.jsonl` built exactly like `run_history_demo`'s (one
  message per tier, ids `demo-hist-<tier>`, model ids via `_first_model_of_tier`, volumes from
  `DEMO_VOLUMES`). The conventional `<repo>/.claude/kits` layout makes the derived labels
  exactly `repo-a` / `repo-b`. Capture two history cards by calling `main([...])` in-process
  with stdout redirected (`io.StringIO` + `contextlib.redirect_stdout`), both with
  `--no-subagents` and `--json`: day 1 = `--history --kits-dir <repo-a kits> --projects-dir …`
  (a PLAIN single-dir card), day 2 = the same plus a second `--kits-dir <repo-b kits>` (a
  NAMESPACED multi card). `json.loads` each and write them with
  `write_snapshot(card, snap_dir, "2026-01-01")` / `"2026-01-02"` (pinned synthetic fixture
  dates — same species as the demo transcripts' pinned timestamps, not pricing dates). Then
  `return main(["--history", "--trend", "--snapshot-dir", str(snap_dir)] + (["--json"] if
  as_json else []))`. Pinned expectations (the T2 verify asserts): exit 0; JSON
  `schema_version == 1`; exactly 2 points, dates `["2026-01-01", "2026-01-02"]`; point-1
  `kits == 2`, point-2 `kits == 3`; BOTH points' tiers: haiku `{with_outcome 3, first_try 2}`,
  sonnet `{with_outcome 5, first_try 2}`, opus `{with_outcome 1, first_try 1}`, frontier
  `{with_outcome 0, first_try 0, rate None}`; both points' `dollars["actual_usd"] > 0`
  (VALUES computed from pricing.json at run time — deliberately NOT pinned); no `no trend yet`
  note. Markdown contains `# Routing trend — per-tier first-try rate over time`,
  `| Date | haiku | sonnet | opus | frontier | Kits | Actual $ |`, `| 2026-01-01 |`,
  `| 2026-01-02 |`, `2/3 (67%)`, `2/5 (40%)`, `1/1 (100%)`. (Why the tier numbers are equal
  across the two days: gamma has no outcome ledger — day 2 adds its PINS and a third kit row,
  which is exactly the honest scope-growth story the `Kits` column exists to show.)
- **D9 — Sanctioned literals.** `TREND_SCHEMA_VERSION = 1` (same species as the other four
  schema versions), `SNAPSHOT_FILENAME_RE` + the `^\d{4}-\d{2}-\d{2}$` date grammar +
  `_LABEL_RE` (structural grammar, same species as the ledger regexes), `DEFAULT_SNAPSHOT_DIR
  = PLUGIN_ROOT / "trends"` (a repo-relative dir name, like `DEFAULT_KITS_DIR`), the two
  pinned demo snapshot dates `2026-01-01` / `2026-01-02` (synthetic fixture dates), the tier
  vocabulary + `TASK_MODEL_TIERS`, and synthetic fixture ids/values in tests and the demo. NO
  new policy constants — the multi history and the trend DESCRIBE and judge nothing. No
  hardcoded prices, price ratios, real model ids, or pricing dates anywhere in new or edited
  files; every demo/test transcript model id is computed from `data/pricing.json` at run time
  via `_first_model_of_tier`.
- **D10 — The skill surface: NO skill edit, and why.** The cross-repo and trend flags are CLI
  mechanics, not kit-runtime behavior: `/architect`'s history-consult bullet and `/execute`'s
  End-of-run offer both name `python3 bin/routing_scorecard.py --history`, which remains valid
  and byte-identical (the default single-dir invocation is untouched); nothing in the kit
  contract (task fields, statuses, NOTES.md line formats, dispatch rules) changes; discovery
  of the new flags rides `--help`, `docs/ROUTING-TRENDS.md`, and the CLAUDE.md run-line. Zero
  skill edits = zero contract risk: per the CLAUDE.md invariant (which triggers only when a
  skill is TOUCHED), no shared-contract re-check edit is needed — instead, every task's verify
  carries `git diff --quiet -- skills` so an accidental skill edit fails loudly and
  immediately. If any executor believes a skill edit is needed, that is a STOP-and-report,
  not a change.
- **D11 — Degradation summary (never fabricate).** Cross-repo dollars degrade EXACTLY as
  today: quality-only (no pricing load) with zero `session:` lines; missing transcripts noted
  + skipped; coverage labeled; a lone unpriceable id never becomes a number. The trend: zero
  snapshots → n/a + note, exit 0; one snapshot → the point + the pinned `no trend yet` note,
  exit 0 (a trend needs ≥2 points — a single point is data, not a trend); malformed/rogue
  snapshot files skipped + noted, the survivors still trend; a stored card without dollars
  contributes an `n/a` dollars cell, never a recomputed figure; zero-denominator rates render
  None/`n/a`, never a fabricated 0%.

## Constraints and OUT-OF-SCOPE fence

Executors must NOT:

- **Edit any skill.** `skills/` (including `skills/architect/SKILL.md`,
  `skills/execute/SKILL.md`, and the generated `references/` mirrors) stays byte-unchanged —
  `git diff --quiet -- skills` in every verify; any diff there is a defect. No shared-contract
  edit of any kind (D10). If a brief seems to require a skill change, STOP and report.
- **Break `bin/routing_scorecard.py`'s existing behavior.** Additive only, a FIFTH time:
  existing flags, function signatures, output shapes, exit codes, and ALL FOUR prior demos'
  numbers stay byte-stable; a lone `--kits-dir` (or none) keeps `--history` output
  byte-identical to today — kit names unprefixed, the JSON key set exactly the eight
  pre-existing keys, no `kits_dirs` key, no `- scanned` lines; `MD_H2S`,
  `HISTORY_SCHEMA_VERSION`, `build_history`, `scan_kits`, `history_tier_stats`,
  `tally_reroutes`, `kit_cost_summary`, and `render_history_markdown`'s existing lines are
  untouched (the render hook is guarded and additive); the four frozen test files
  (`tests/test_routing_scorecard.py`, `tests/test_reroute_live.py`,
  `tests/test_routing_history.py`, `tests/test_per_task_dollars.py`) are never edited — new
  tests go in `tests/test_crossrepo_trend.py`. Never edit `bin/cost_report.py`,
  `bin/session_cost.py`, `bin/copilot_execute.py`, any other existing `bin/`/`tests/` file,
  `data/` (either pricing file), `.claude-plugin/`, `copilot/`, `README.md`, or the completed
  kits and their agents. Never re-implement the reused pipeline — call it.
- **Write anywhere except the snapshot dir (and demo/test temp dirs).** The ONLY new runtime
  write is `write_snapshot` under `--snapshot-dir` (default the gitignored `trends/`);
  `write_snapshot` must reject any `date_str` outside the pinned grammar (ValueError) so the
  write cannot escape its dir; every other mode stays read-only — never a write into a kit
  dir, NOTES.md, source, or the real `~/.claude`. `--snapshot` is rejected alongside `--demo`.
- **Fabricate.** No trend from <2 points (say so instead); no invented dollars (missing
  transcripts skipped + noted; snapshot cards without dollars render n/a); no silent skip of
  a malformed snapshot (note it); no silent merge of two repos under one label (suffix +
  note); zero-denominator rates render null/`n/a`.
- **Couple to the journal.** The snapshot store is self-contained: nothing under `journal/`
  is read or written; no `bin/journal_*.py` import; the store is `trends/`.
- **Add charts/plots** (text table only — explicitly deferred), dependencies, or tooling.
  Python stdlib-only; no pip/pytest; no network; no Copilot-side changes; no changes to
  `/route`/`/escalate`/`/fable-check`; no new skills; no README changes.
- **Read the real `~/.claude` (or write outside the repo + temp dirs) from any test or verify
  command.** Every test/verify passes explicit temp `--kits-dir`(s)/`--projects-dir`/
  `--snapshot-dir` fixtures; the snapshot WRITE in tests goes to a temp `--snapshot-dir` only.
  `Path.home()` count in `tests/test_crossrepo_trend.py` and in the `bin/routing_scorecard.py`
  diff: ZERO (the runtime projects default stays the borrowed `str(sc.DEFAULT_PROJECTS_DIR)`).
- **Build past this kit's scope.** No auto-snapshot scheduling (launchd/cron — the user runs
  `--snapshot` when they choose); no per-task or per-agent trend aggregation; no
  scorecard-over-time beyond per-tier first-try + carried dollars; no auto-anything (no
  auto-pin, no auto-downgrade); no main-session model switching (still the upstream ask).
- **Commit or push.**

Sanctioned edit targets among existing files: `bin/routing_scorecard.py` (T1/T2, additive),
`.gitignore` (T3, pinned entry only), `docs/ROUTING-HISTORY.md` (T5, pinned pointer paragraph
only), `CLAUDE.md` (T6, pinned run-line only — the crossrepo-trend fence paragraph was already
added by the architect). Sanctioned new files: `tests/test_crossrepo_trend.py`,
`docs/ROUTING-TRENDS.md`.

## Risks & tripwires

- **Single-dir/demo byte-drift — THE #1 RISK.** The argparse `append` change ripples into
  every consumer of `args.kits_dir` (`run_history`, `_resolve_kit_dir` in the plain path).
  TRIPWIRES: any of the FOUR prior demos' numbers shifting; the frozen
  `tests/test_routing_history.py` key-set test failing; a lone-dir `--history --json` card
  carrying `kits_dirs` or a non-string `kits_dir`; a `- scanned` line in single-dir markdown;
  `git diff --quiet` failing on any frozen file. Any hit → stop, fix before proceeding.
- **The snapshot write escaping its dir, or the store not being gitignored.** TRIPWIRES: a
  `write_snapshot` accepting `../`-bearing or otherwise non-`YYYY-MM-DD` date strings; any
  write outside `--snapshot-dir` in the tree-delta tests; `git check-ignore trends/…` failing;
  a stored snapshot carrying the `snapshot written:` note (stored cards are pure data); a
  non-snapshot mode writing anything at all.
- **A 1-snapshot "trend".** TRIPWIRE: any output that renders a single point without the
  pinned `no trend yet` note, or that interpolates/extrapolates anything from it.
- **Namespacing collisions.** TRIPWIRES: two dirs deriving the same label without the `-2`
  suffix + note; the same dir scanned twice; a same-named kit in two repos producing one
  merged row instead of two namespaced rows; kit_costs keyed by the UN-namespaced name
  (dollars would silently detach from their kit rows).
- **Multi-dir dollars double count or fabrication.** TRIPWIRE: any dollar arithmetic that is
  not the existing ladder (one `collect()` per scope, union ids priced once, missing → note +
  skip) applied to the longer record list.
- **`--trend` loading pricing.** Pure `--trend` must never call `cr.load_pricing()` (the
  monkeypatch test is the tripwire) — it re-renders stored numbers only.
- **Anchor drift in prose edits.** T5/T6 pin exact anchors. TRIPWIRE: an anchor not found
  verbatim — report, never fuzzy-match; duplicated content from re-running an edit (grep
  counts in verifies guard this).
- **Suite/path quirks.** Verify with `python3 -m unittest discover -s tests
  [-p '<file>.py']` — never the dotted-module form. Paths via `Path(__file__).resolve()`,
  never `$PWD`. No `/private/tmp/` session path in any deliverable. Run
  `python3 bin/sync_pricing_refs.py --check` after every code task.

## Still deferred after this kit (named, not built)

1. **Charts/plots of the trend** — text table only; a rendering layer is a possible future
   kit, the data contract (the snapshot store) is now stable for it.
2. **Auto-snapshot scheduling** — the user runs `--history --snapshot` when they choose;
   wiring it into launchd/cron (the daily-journal precedent) is deliberately not done.
3. **Per-task / per-agent trend aggregation** — the trend tracks per-tier first-try rate and
   carried dollars; folding `--by-task` breakdowns into the time series is out of scope.
4. **Auto-pin adjustment / auto-downgrade** — unchanged; advisory by design.
5. **Main-session model switching at compaction boundaries** — unchanged; still the upstream
   ask, tracked in `docs/FUSION-TIER1.md`.
