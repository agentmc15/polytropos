# Routing history — the cross-kit per-tier track record

Tier 1 gave every kit an outcome ledger (`outcome:` lines in NOTES.md) and an end-of-run
quality scorecard. Tier 2 added `reroute:` lines and a live, mid-kit per-tier signal. This kit
adds a third additive mode to `bin/routing_scorecard.py` — `--history` — that scans every kit
under the kits dir and folds all of that ledger data into one cross-kit, per-tier routing track
record: quality first, dollars where the data supports them, and one advisory pointer that feeds
the track record back into the architect's initial model pins.

## What it aggregates

`--history` scans every kit directory under the kits dir, parses each kit's TASKS.md (via the
reused `parse_tasks`) and its NOTES.md ledger (the reused `outcome:` and `reroute:` parsers),
and aggregates per pricing tier: pinned tasks (the architect's original `model` pins), outcomes
(first-try / retry / escalated / blocked), the derived first-try and escalation rates, and the
per-tier re-route from/to tallies.

Attribution follows the same rule Tier 2 established for the live signal: `pass`, `retry-pass`,
and `blocked` outcomes attribute to the tier of the ledger's `model=` field — the tier the task
actually ran on. `escalated-pass` is different: it attributes to the reconstructed **dispatch**
tier (the task's pin plus any prior applied re-routes), never to frontier — crediting frontier
with a cheap tier's failure would pollute frontier's stats and hide the struggling tier's real
history.

Usage:

```bash
python3 bin/routing_scorecard.py --history                # cross-kit markdown card
python3 bin/routing_scorecard.py --history --json         # same data, schema_version: 1
python3 bin/routing_scorecard.py --demo --history          # synthetic cross-kit smoke
```

`--history` is read-only, exactly like `--live`: it scans kit directories and (when dollars
apply) transcripts, and never writes to a kit file, NOTES.md, or anywhere else. A kits dir with
no kits still exits cleanly with an empty card and a note — a missing kits dir is the one hard
error.

## Dollars — the optional session: line

Per-kit dollars need a mapping from a kit back to the session(s) that executed it. That channel
is an OPTIONAL, execute-owned NOTES.md line, grammar verbatim:

```
session: <session-id>
```

The line is appended by the `/execute` orchestrator at the end of a run, via a read-only
transcript-stem lookup (the most recently modified transcript file in the project's transcript
directory) — never guessed, and never written by any script. A kit executed across several runs
legitimately carries several `session:` lines; a kit whose orchestrator run couldn't resolve the
lookup unambiguously simply carries none.

Kits that carry at least one `session:` line get their transcript dollars folded in against the
all-frontier counterfactual (computed from `data/pricing.json` at run time — never a hardcoded
price or ratio). Kits with no `session:` line degrade to quality-only: their pins and outcomes
still count toward the per-tier track record, but they contribute nothing to the dollar
aggregate. If a session id is shared across two kits (one session that executed both), that id
is priced exactly once in the aggregate — never double-counted — while each kit's own row still
reports its own full number, and a note flags the overlap.

The aggregate is always labeled with its coverage: `partial` (some kits or some session ids
didn't resolve to a priced transcript) or `full` (every kit has at least one `session:` line and
every id priced). With zero `session:` lines anywhere in the scanned kits, the history is
quality-only end to end and pricing is never loaded — no `$0.00` that looks real, no invented
figure standing in for a missing one.

## Feeding the architect

`/architect` Step 2 now carries one ADVISORY bullet: consult
`python3 bin/routing_scorecard.py --history` when choosing a kit's initial `model` pins. The
history surfaces evidence — first-try rate, escalation rate, upgrade frequency, and dollars
where present — for each tier's track record on prior kits. It is evidence, not an
auto-pin-setter: the architect (human or Fable) weighs that evidence and decides. No automation
anywhere reads the history and rewrites a pin; a tier that keeps needing upgrades on similar
work is an argument the architect can act on, not a rule that acts for them.

## Contract safety

The shared architect/execute kit contract survives this kit byte-intact. The `session:` line is
a third execute-owned NOTES.md line format, following the precedent already set by `outcome:`
(Tier 1) and `reroute:` (Tier 2) — NOTES.md is execute-owned, so a new line shape inside it is
not a contract change. Neither the existing `outcome:` parser nor the `reroute:` parser matches
a `session:` line, so every prior NOTES.md consumer is unaffected. No task field changed shape,
no status vocabulary changed, and `parse_tasks` needed no modification — dollars ride entirely
on the ledger, not on TASKS.md. The `/architect` change is exactly one advisory bullet, adding
guidance and removing nothing. The task's `model` field overriding the implementer agent's
frontmatter at dispatch — including the Tier-2 runtime-override clause — is untouched in both
skills.

## Deliberately not built

- **Auto-pin adjustment** — advisory by design, not merely deferred. The history is evidence for
  a human or Fable to weigh; nothing reads it and rewrites a `model` field automatically.
- **Cross-repo or time-series trend aggregation** — this kit aggregates across kits in one repo
  at one point in time; tracking how a tier's track record trends over time, or pooling history
  across repos, is out of scope.
- **Per-task dollar attribution** — transcripts price sessions, not individual tasks. Splitting
  a session's cost across the tasks it covered would be an estimate presented as a measurement,
  which this kit's dollar rules deliberately avoid.
- **Main-session model switching** — unchanged from Tier 1 and Tier 2; still the upstream ask,
  still tracked in `docs/FUSION-TIER1.md`.

Per-task dollar attribution has since shipped — see
[PER-TASK-DOLLARS.md](PER-TASK-DOLLARS.md). The premise of the deferral bullet above still
holds for the orchestrator's own share (the main transcript is never split per task); what
changed is the data: the execute-owned NOTES.md `agent:` ledger records which subagent
transcript served which task, so DELEGATED cost is now measured per task — via `--by-task`
on the per-kit scorecard — with a warm cluster's shared transcript attributed to the
cluster as a unit, never divided.

Cross-repo and time-series aggregation have since shipped too — see
[ROUTING-TRENDS.md](ROUTING-TRENDS.md). `--kits-dir` is now repeatable on `--history` (kit
rows namespaced `<label>/<kit>`, tiers aggregated globally, dollars through the same single
projects dir under these same degradation rules), and `--history --snapshot` /
`--history --trend` store dated JSON snapshots in a gitignored `trends/` dir and render
per-tier first-try rate over time as a text table — a trend needs at least two snapshots,
and a lone `--kits-dir` still produces output byte-identical to this kit's.
