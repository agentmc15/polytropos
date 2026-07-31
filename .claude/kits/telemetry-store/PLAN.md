# PLAN — telemetry-store: durable snapshots of the repo's analytics before the sources rotate away

autonomy: advisory

## Goal

Every analytic this repo produces is re-derived on demand from transcript stores that ROTATE.
Verified at kit-authoring time (2026-07-25): the oldest surviving Claude transcript is
2026-07-06; only 3 unique session ids were ever ledgered across 22 kits and only one is still
priceable — the cross-kit dollar verdict (`--history` today: $244.69 actual vs $473.56
all-Fable over 9/22 kits, coverage partial) survives only while one 11 MB transcript file
lives. This kit builds the durable store: a gitignored `telemetry/` directory of small, dated,
self-describing JSON envelopes written by ONE new tool, `bin/telemetry_snapshot.py`, which
imports the existing analytics modules and calls their pure builders — shelling out to
nothing — then performs the first real capture so today's still-derivable history stops
evaporating.

## Done means (all checkable from the repo root)

1. `python3 bin/telemetry_snapshot.py --store-dir <tmp> --projects-dir <tmpA> --codex-home
   <tmpB> --copilot-home <tmpC> --kits-dir .claude/kits` exits 0 and writes exactly five
   envelope files `<tmp>/<source>/<YYYY-MM-DD>.json` for sources `cost_report`,
   `codex_usage`, `copilot_usage`, `context_overview`, `routing_history` — empty temp homes
   produce honest absence labels, never fabricated zeros presented as measurements.
2. `python3 bin/telemetry_snapshot.py --list --store-dir <tmp>` renders a per-source summary
   (count, first/last date, latest status) and tolerates a missing dir, rogue filenames, and
   undecodable files with notes — never a crash, never a guess.
3. `python3 bin/cost_report.py --json --days 30` and `python3 bin/copilot_usage.py --json
   --days 30` emit machine-readable payloads (both tools were markdown-only); every
   pre-existing CLI invocation of all four touched tools behaves as before.
4. Full suite green: `python3 -m unittest discover -s tests -q` (baseline 1286 tests; the
   count only grows).
5. The first real capture has run: `telemetry/<source>/<capture-date>.json` exists on disk
   for all five sources, each envelope validates, and `.gitignore` carries a root-anchored
   `/telemetry/` so none of it is committable.
6. `skills/journal/SKILL.md` instructs the daily journal flow to run the snapshot;
   `CLAUDE.md` carries the telemetry invariant bullet and run-lines and stays ≤ 16000 bytes
   (`tests/test_guardrails_layout.py` ceiling).

## Decisions (each with the why — executors follow these, not their own taste)

**D1 — The store is a gitignored local dir: `telemetry/` at the repo root.** Precedent is
unanimous: `journal/`, `memory/`, `trends/`, `prefs/` are all gitignored because they hold
personal or machine-generated data, and telemetry envelopes embed real dollar figures and
absolute machine paths. The always-on "do not commit or push" law also means a committed
store could never actually be populated by kit execution. The durability-across-machine-loss
argument for committing is real but belongs to the user's backup strategy; a future kit may
add a committed, dollar-free aggregate EXPORT — that split is explicitly deferred (see OUT OF
SCOPE), because doubling the schema surface before a single snapshot exists is premature.

**D2 — Layout: one dated file per source per day, `telemetry/<source>/<YYYY-MM-DD>.json`,
wrapped in a self-describing envelope.** This extends the exact filename grammar the
crossrepo-trend kit already sanctioned (`routing_scorecard.SNAPSHOT_FILENAME_RE`,
`^\d{4}-\d{2}-\d{2}\.json$`) per-source rather than inventing a combined daily envelope.
Why per-source: (a) partial-capture days degrade file-by-file instead of poisoning one
combined file; (b) each source tool already carries its own `schema_version` and evolves
independently; (c) a `read_snapshots`-style tolerant reader wants one homogeneous stream per
dir. The envelope (store_schema_version 1):

```json
{
  "store_schema_version": 1,
  "source": "<registry name>",
  "source_schema_version": "<payload's own schema_version, else null>",
  "captured_at": "<UTC ISO, seconds>",
  "capture_date": "<YYYY-MM-DD, equals the filename stem>",
  "period": {"days": 30},
  "status": "ok | error",
  "labels": ["<honesty labels lifted from the payload — est., unpriced, absence, coverage>"],
  "notes": ["<capture-time degradation notes>"],
  "payload": {}
}
```

(`period` is `{"days": N}` or `{"description": "<str>"}`; `payload` is the source tool's own
JSON card verbatim, or `null` on error.) A snapshot must never look more authoritative than
the live output it captured: `labels` are LIFTED from the payload (the builders themselves
emit a `labels` list — see D3 interfaces) or derived mechanically from documented payload
fields (`routing_history` dollars coverage, `context_overview` per-section `found`), never
authored fresh at capture time. Source absence is payload-level honesty (`found: false` +
an absence label), not a missing file — so "captured: source absent" is distinguishable
forever from "never ran". `status` is `error` only when a collector raised; the envelope is
still written with `payload: null` and the exception in `notes`. Re-running the same day
overwrites that day's file (latest wins per day — the established `write_snapshot`
semantics). The store carries aggregates and metadata ONLY — never transcript text (the
journal digest precedent).

**D3 — Capture is import-and-call of pure builders; the snapshot tool shells out to
NOTHING.** I agree explicitly with the import-and-call shape and reject subprocess: tests
never invoke live CLIs (repo law), the copilot/codex invariants forbid anything that could
spend credits or hit the network, and the house importlib pattern
(`importlib.util.spec_from_file_location` by absolute path — `bin/bench_routing.py` already
loads `routing_scorecard` this way) makes sibling builders directly callable. Where a
builder does not exist yet, the tool grows one (and `--json` rides along for free — closing
the coverage gap for the two markdown-only tools). Pinned cross-task interfaces (Phase 1
builds them, T5 consumes them — do not drift):

- `cost_report.build_report_payload(projects_dir, days=30, top=10, mode=None) -> dict`,
  keys ⊇ `{schema_version, found, days, mode, totals, by_model, sessions, labels}`,
  `schema_version` 1. New CLI flags `--json` and `--projects-dir` (flag default `None`,
  resolved to the module-level `PROJECTS_DIR` inside `main` at call time — existing tests
  monkeypatch that global and must keep working).
- `copilot_usage.build_usage_payload(session_dir, days=30, top=10) -> dict`,
  keys ⊇ `{schema_version, found, days, totals, by_model, labels}`, `schema_version` 1.
  New CLI flag `--json`.
- `codex_usage.build_usage_payload(codex_home, days=30, top=10) -> dict`, one unified dict
  for the absent/unpriced/priced shapes, keys ⊇ `{schema_version, found, priced, days,
  labels}`, `schema_version` 1. CLI (markdown and existing `--json`, including the exact
  `branch` shapes) renders FROM it — one scan path feeds both.
- `routing_scorecard.assemble_history_card(kits_dirs, projects_dir=None, tasks_dir=(),
  include=(), no_subagents=False, vs=None) -> card` — pure extraction of `run_history`'s
  card assembly (scan → dollars ladder → `build_history` → namespaced fixups): no printing,
  no `sys.exit` (raises `ValueError` with the exact current exit messages; `run_history`
  catches and exits identically), and it returns the card BEFORE any `--snapshot` tail note.
  `build_history`'s positional signature is untouchable (`bin/bench_routing.py` calls it
  positionally).
- `context_weight.build_overview(harness, days, top, projects_dir, codex_home,
  copilot_home)` already exists and is consumed as-is — zero changes to that module.

**D4 — Trigger: the manual CLI is the writer; the daily journal SKILL gains one step.** No
harness hooks, no cron, no scheduler (OUT OF SCOPE). The journal wiring is a SKILL-BODY
instruction ("after collecting the digest, run `bin/telemetry_snapshot.py`"), never a
`journal_*.py` code change: that preserves both the journal invariant (its code stays pure
read-only ingestion) and the store law that `bin/telemetry_snapshot.py` is the ONLY writer
under `telemetry/`. The journal step is best-effort — a snapshot failure never blocks the
journal.

**D5 — The backfill line, drawn precisely.** The role-ledger kit's law stands: evidence is
never reconstructed from prose. This kit's first-run capture is NOT reconstruction — it is
late capture of real sources that still exist and are about to rotate; it is sanctioned and
urgent (it is task T9). Forbidden forever: writing any envelope whose payload was not
produced by running a registered collector over a still-existing source at capture time —
no hand-authored envelopes, no envelopes derived from NOTES.md prose, README tables, or old
reports, and specifically no fabricated cost basis for the 18 kits whose transcripts are
already gone; their dollars are lost and the store must say so (partial coverage labels),
not paper over it. Mechanically enforced honesty: the filename date and `capture_date` are
ALWAYS the run date (validated `YYYY-MM-DD`, path-traversal-guarded like `write_snapshot`);
a capture of a 30-day window run today is stored under today, with the window in `period` —
capture-date and data-period are separate fields by construction, so a late capture can
never masquerade as a contemporaneous one. There is no flag to backdate a filename.

**D6 — Trend is deferred; the store is trend-ready.** `build_trend` stays exactly what it
is: the routing-history card's renderer over `trends/`. This kit does not generalize trend
rendering across sources (that is the non-urgent half and a scope trap). What it DOES ship
is the read seam a future trend kit needs: `read_source_snapshots(store_dir, source)` with
`read_snapshots`-grade tolerance (missing dir → note; rogue name / undecodable file /
non-dict → skip with note; survivors ascend by date), plus `--list`. The existing
`routing_scorecard --snapshot`/`trends/` machinery is untouched — the two stores coexist;
converging them is a future decision, not a silent side effect.

**D7 — Retention: keep everything, forever; size is bounded by arithmetic, not pruning.**
Five sources × one file/day; the largest envelope today is the routing-history card
(~40 KB with 22 kits), the rest 2–15 KB — call it ≤ 100 KB/day worst case, so a full year
is ≤ ~37 MB and realistically under 15 MB. That needs no pruning code and no rotation.
Tripwire: any single envelope over 1 MB means a payload started embedding bulk data
(transcript text, per-message detail) — that is a schema bug to fix at the source, never a
reason to add pruning.

**D8 — The value-report generator stays OUT of this kit.** The scratchpad script lives in
the originating conversation, which executors (and this architect) cannot see into; a brief
for a file nobody at execution time can read is a brief-defect factory. The urgent half is
persistence. The store's envelopes wrap each tool's full JSON card verbatim, so a follow-up
kit can move the generator into `bin/` and point it at the store with zero schema work —
hand it the scratchpad script as reference material then.

## Constraints

- Python stdlib only; no pip, no pytest. Every test uses temp dirs/fixtures through
  injectable seams (`--store-dir`, `--projects-dir`, `--codex-home`, `--copilot-home`,
  `--kits-dir`, direct function args) — never the real home dirs. Zero `Path.home()` in new
  engine code beyond the module-level `DEFAULT_*` precedent.
- The store is written by `bin/telemetry_snapshot.py` ONLY. Analytics tools stay read-only
  over their sources. Nothing bulk-injects the store into a session's context.
- Backward compatible: nothing existing breaks when `telemetry/` is absent; every reader
  degrades with a note, never a guess.
- All changes to the four existing tools are additive: no existing flag, exit code, or
  markdown output changes for existing invocations; `bin/bench_routing.py` and its tests are
  untouchable and their live-ledger PROPERTY assertions stay property-based (never
  reintroduce a pinned live count).
- Do not commit or push.

## OUT OF SCOPE — executors must NOT

- Build or relocate the value-report generator, or any HTML/report rendering.
- Generalize `build_trend`, alter `routing_scorecard`'s `--snapshot`/`--trend`/`trends/`
  machinery, or migrate/merge the `trends/` store.
- Add harness hooks, cron, schedulers, or any unattended dispatch; touch
  `bin/journal_*.py` code (the journal wiring is skill-body only).
- Write any committed aggregate/export of telemetry, or commit anything at all.
- Reconstruct, estimate, or backfill any figure whose source is gone (D5) — no envelope for
  any date before the first capture ever exists.
- Touch `bin/bench_routing.py`, `tests/test_bench_routing.py`,
  `skills/bench-routing/SKILL.md`, `bin/context_weight.py`, any pricing file, any skill
  YAML frontmatter, or any existing kit's NOTES.md.
- Merge dollars across the three harnesses anywhere — not in envelopes, not in `--list`
  output. One harness, one pricing file, one dollar column; the store preserves that law.

## Risks and tripwires

- **R1 — `cost_report.py` refactor vs its 20 pinned tests.** Tests monkeypatch the
  module-level `PROJECTS_DIR` global; the new `--projects-dir` flag must default to `None`
  and resolve the global inside `main` at call time, or every patched test silently reads
  the flag's parse-time default. Tripwire: any `test_cost_report.py` failure → re-read T1's
  seam note before touching test expectations.
- **R2 — `routing_scorecard.py` extraction blast radius.** ~3000 lines, heavy pinned tests,
  and `bench_routing` imports it. The extraction is a pure re-org of `run_history`: same
  card, same notes order, same exit messages, `--history --json` byte-identical. Tripwire:
  any diff in `tests/test_routing_history.py` / `test_crossrepo_trend.py` /
  `test_bench_routing.py` results → the extraction changed behavior; revert and re-cut, do
  not adjust those tests.
- **R3 — First capture runs on the real machine (T9 only).** Home-dir state varies; the
  verify asserts what the evidence guarantees (Claude transcripts exist → `cost_report`
  payload `found` true) and only envelope-validity for the rest. Any other task touching
  real home dirs or the real `telemetry/` is a fence violation.
- **R4 — CLAUDE.md byte ceiling.** 11108 bytes today; `test_guardrails_layout.py` fails at
  16000. T7's additions are ~1 KB of exact text — if you find yourself writing more, stop.
- **R5 — Schema drift.** `store_schema_version` bumps only for envelope-shape changes;
  payload evolution is the source tool's business (`source_schema_version` records it).
  Readers must tolerate unknown envelope keys and unknown source subdirs (note, list,
  never crash) so v2 stores remain readable by v1-era code.
