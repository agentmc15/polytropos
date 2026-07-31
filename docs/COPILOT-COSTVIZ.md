# Copilot cost visibility

Phase 3 of the [Copilot harness](COPILOT-HARNESS.md): a usage report over Copilot CLI's own
session logs, pooled-AIC runway math for org plans, and a written proposal for the aesop
compile round-trip.

---

## What this is

Three pieces:

- **A usage report** (`bin/copilot_usage.py`) — reads Copilot CLI's own session logs and prices
  them from `data/pricing.copilot.json`, the same way `/polytropos:cost-report` does for
  Claude Code transcripts.
- **A pooled-AIC runway extension** (`bin/copilot_pricing.py runway --pool-aic`) — lets
  `business`/`enterprise` plans, whose AI Credits are pooled at the org level rather than fixed
  per seat, still get a runway estimate from a user-supplied pool number.
- **A written proposal** for the aesop compile round-trip
  ([AESOP-COMPILE-PROPOSAL.md](AESOP-COMPILE-PROPOSAL.md)) — a spec for a future
  `/polytropos:architect` run inside aesop's own repo, not code executed here.

## The usage report

`bin/copilot_usage.py` reads `~/.copilot/session-state/<uuid>/events.jsonl` — read-only, one
JSON object per line — plus each session's sibling `workspace.yaml` for a project label. The
SQLite session stores under the same home are ignored by design: opening a `*.db` file, even
"read-only," can create `-wal`/`-shm` side files, so the tool never touches one.

```bash
python3 bin/copilot_usage.py --days 30
python3 bin/copilot_usage.py --days 7 --top 5
python3 bin/copilot_usage.py --copilot-home /some/other/home
python3 bin/copilot_usage.py --session-dir /path/shaped/like/session-state
```

`--days` windows the report by each session's last-seen timestamp (sessions with no parseable
timestamp are kept regardless); `--top` bounds the top-sessions table; `--copilot-home` and
`--session-dir` point the reader at a different home or an arbitrary session-state-shaped
directory — the latter is how every test and verify run in this repo points it at a synthetic
fixture instead of a real home.

The emitted markdown has: totals up top; spend by model; an exact per-turn output-tokens table
across models; the top sessions by estimated cost; downgrade candidates (cheap/small sessions
currently running on an expensive tier, priced against what the first mid-tier model would have
cost); the Copilot-reported AIU cross-check; and, only when present, unpriced-model and
read-error sections.

The event shape this parser expects was observed on **Copilot CLI v1.0.68**. The parser is
written to tolerate drift by surfacing what it can't match — unpriced models get their own
section instead of silently dropping — rather than guessing at a shape change.

## Granularity honesty

The full input/cache-read/cache-write/output token split exists at **session** granularity
only, carried in the cumulative snapshot on a `session.shutdown` event's `tokenDetails`. For a
single-model session that split is priced exactly against that one model. A multi-model session
has no per-model breakdown in the event stream, so its whole split is attributed to the
session's **last** model and flagged `≈` in the spend-by-model and top-sessions tables — the
report never fabricates a per-model input/cache split it doesn't have.

The one exact cross-model view is the **per-turn output-tokens table**, built from
`assistant.message` events: output tokens only, because the events carry no per-turn
input/cache split either.

A session with no `session.shutdown` token details at all is marked `†` in the top-sessions
table — its row is an output-tokens-only undercount, since input and cache tokens for that
session were never priced.

Multiple shutdown snapshots across a resumed session aggregate by element-wise **MAX**, never
sum — the snapshots are cumulative totals, and summing them would double-count.

## AIU vs AIC

Copilot reports its own consumption figure per session as `totalNanoAiu` — an "AI Unit," not an
AI Credit. This tool treats AIU strictly as Copilot's own reported number and never assumes
AIU == AIC and never converts an AIU figure into money.

The authoritative cost estimate is computed the other way: observed token counts ×
`data/pricing.copilot.json` per-model rates → USD, then USD → AIC via that file's
`billing_unit.usd_per_credit`. The AIU total is printed as a separate, clearly labeled
cross-check section next to that estimate — useful for sanity-checking the parser against
Copilot's own number, never as an input to the priced total.

## Pooled-AIC runway

`business` and `enterprise` plans pool their AI Credits at the org level, so
`data/pricing.copilot.json` has no fixed `included_aic_per_month` for them — there is no
correct single-seat number to hardcode. `bin/copilot_pricing.py runway` now accepts
`--pool-aic` to supply that number yourself for a given run:

```bash
python3 bin/copilot_pricing.py runway business M <id> --pool-aic 50000
python3 bin/copilot_pricing.py runway pro S <id> --pool-aic 50000   # still an override
```

For a plan with its own fixed `included_aic_per_month` (`free`, `pro`, `pro-plus`, `max`),
`--pool-aic` overrides that fixed allowance rather than requiring it — useful for modeling a
custom org arrangement against a normally-fixed plan. Every runway result carries an
`allowance_source` field, `"plan"` or `"pool"`, so the output always says which number it used
and where it came from; the CLI's plain-text output prints this as `(plan)` or `(user-supplied
pool)` next to the allowance line.

## Cost safety

The usage report and the runway extension spend nothing. `bin/copilot_usage.py` never invokes
the `copilot` CLI, reads only the two text files named above, and writes nothing under
`~/.copilot` under any circumstance. `bin/copilot_pricing.py runway` is pure arithmetic over
`data/pricing.copilot.json` and a number you supply — no I/O against a live home at all. This
repo's test suite for both exercises them exclusively against synthetic `events.jsonl` fixtures
in temporary `--copilot-home` / `--session-dir` directories; the real `~/.copilot` is never read
or written by any test or verify command in this kit.

## Still deferred

Ralph per-tick real-cost feedback is still out of scope: `events.jsonl` is written at session
**shutdown**, not per tick, so there is no live per-tick cost signal to read mid-loop, and the
pricing-fed estimate already in `bin/copilot_ralph.py` remains the loop's runway math by design.

The aesop compile round-trip itself — making the Copilot bundle a real `aesop compile` target —
is written up as a proposal, not executed:
[AESOP-COMPILE-PROPOSAL.md](AESOP-COMPILE-PROPOSAL.md). See
`.claude/kits/copilot-costviz/PLAN.md` for the full reasoning behind both deferrals.
