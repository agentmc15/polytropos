# Routing trends — cross-repo history and the snapshot time series

Routing history (`docs/ROUTING-HISTORY.md`) gave `bin/routing_scorecard.py` a `--history` mode
that folds one repo's kits into a per-tier track record at one point in time. This kit adds two
more additive things on top of the same script: `--kits-dir` becomes repeatable so `--history`
can aggregate across repos, and a snapshot store plus a `--trend` view turn that one-point-in-time
card into a per-tier first-try-rate time series. Both pieces stay read-only except for one
narrow, sanctioned write.

## Cross-repo history — repeatable --kits-dir

`--kits-dir` is now repeatable on `--history`. With more than one `--kits-dir` (or any explicit
`label=path` token), kit rows are namespaced `<label>/<kit>` so two repos' same-named kits don't
collide in the aggregate. Labels derive from the path: a conventional `<repo>/.claude/kits` dir
resolves to the repo directory's basename; anything else falls back to the dir's own basename.
An explicit override is spelled `label=path` — pass it as the `--kits-dir` value itself, e.g.
`aesop=/path/to/aesop/.claude/kits`. An explicit label on an otherwise-lone dir still namespaces,
because that invocation is new (a single plain `--kits-dir` never was).

Duplicate labels — two dirs that derive or are given the same label — get deterministic
suffixes `-2`, `-3`, … in occurrence order, each with a note naming the rename. Two `--kits-dir`
values that resolve to the same directory dedupe to one entry, also noted. Nothing is ever
silently merged.

Once namespaced, tiers and re-route tallies aggregate globally across every scanned dir — one
combined per-tier track record, not one per repo. Dollars ride the same single
`--projects-dir`: the shared transcript store is expected to hold every repo's sessions (each
under its own project slug), and the existing degradation ladder applies unchanged — a missing
transcript is noted and skipped, the aggregate's coverage is labeled `full` or `partial`, and a
session id shared across kits from different repos is still priced exactly once.

With a LONE plain `--kits-dir` (or none passed at all, the repo-local default) the output stays
byte-identical to before this kit: kit names unprefixed, the JSON card's top-level key set
exactly the eight pre-existing keys, no `- scanned` markdown lines. Namespacing only activates
with more than one dir or an explicit label.

Example command:

```bash
python3 bin/routing_scorecard.py --history --kits-dir <repo-a>/.claude/kits --kits-dir <repo-b>/.claude/kits
```

## The snapshot store

```bash
python3 bin/routing_scorecard.py --history --snapshot
```

writes the history card as `<YYYY-MM-DD>.json` (UTC date, latest-wins per day if run more than
once on the same day) under `--snapshot-dir` — default the gitignored `trends/` dir at the
repo root. This is the ONE sanctioned real write in the whole script. Every other mode —
`--history` alone, `--live`, `--by-task`, `--trend` without `--snapshot` — stays strictly
read-only: no write into a kit dir, NOTES.md, source, or anywhere outside the snapshot dir.

The write is bounded by a validated date grammar (`^\d{4}-\d{2}-\d{2}$`), so a filename cannot
escape the snapshot dir — a malformed date string raises rather than resolving to some other
path. The stored card is pure history data: it never carries the `snapshot written:` note that
only decorates the copy printed to stdout, appended after the write completes.

`--snapshot` is rejected alongside `--demo` — the demo family writes only inside its own
`tempfile.TemporaryDirectory`, never into the real snapshot store.

## Reading the trend

```bash
python3 bin/routing_scorecard.py --history --trend [--json]
```

reads every stored snapshot and renders the per-tier first-try rate over time as a text table:
rows are dates, columns are the pricing tiers, plus a kit count column and an `Actual $` column
filled only where a given snapshot's card carried dollars.

`--history --snapshot --trend` snapshots first, then renders the trend including today's new
point. The combined smoke is:

```bash
python3 bin/routing_scorecard.py --demo --history --trend
```

which builds two synthetic repos and writes two dated snapshots before rendering the trend
across both.

Pure `--trend` (no `--snapshot`) scans no kits and loads no pricing — it only reads whatever is
already sitting in the snapshot store.

## The honesty rules

- A trend needs at least 2 snapshots. Zero stored snapshots renders `n/a` plus a note; exactly
  one renders that single point plus a `no trend yet` note — never an extrapolation from a
  single data point.
- Malformed or rogue snapshot files (a name that doesn't match the dated-filename grammar,
  unreadable or undecodable JSON, or JSON missing a dict `tiers`) are skipped and noted; the
  surviving well-formed snapshots still trend.
- Dollars-over-time are surfaced only where a stored snapshot's card already carried them —
  never recomputed from transcripts at trend-read time.
- A lone plain `--kits-dir` (or none) still produces `--history` output byte-identical to
  before this kit.
- Label collisions across `--kits-dir` values are suffixed and noted, never silently merged.
- Every degraded shape — empty store, one-point store, rogue files present, missing tier in an
  old card — exits 0. A trend command failing outright would be its own kind of dishonesty
  about data that's merely thin.

## Deliberately not built

- **Charts or plots of the trend** — the rendering is a text table; the snapshot store is meant
  as a stable, plain-JSON data contract that a future charting layer could read, not a reason to
  build one now.
- **Auto-snapshot scheduling** — nothing cron-like triggers `--snapshot` on its own; the user
  runs it when they choose to record a point.
- **Per-task or per-agent trend aggregation** — the trend is per-tier, matching `--history`'s
  own grain; splitting it finer is out of scope here.
- **Auto-pin or auto-downgrade off the trend** — unchanged from routing history: the trend is
  evidence for a human or Fable to weigh, advisory by design, not a rule that rewrites a `model`
  pin automatically.
- **Main-session model switching** — unchanged from every prior kit in this line; still the
  upstream ask, still tracked in `docs/FUSION-TIER1.md`.
