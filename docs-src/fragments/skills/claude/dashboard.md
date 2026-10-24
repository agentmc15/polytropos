### What it does

You already have a routing ledger, a scorecard, telemetry snapshots, journal digests, and
evaluation runs scattered across this machine's checkouts — each honest alone, but nowhere
together. This skill builds one offline HTML page over them, panel by panel, reading what those
engines reported and pricing, ranking, and summarizing nothing.

### When to reach for it

- A whole-machine view before deciding what to check next: ledger, scorecard, and telemetry,
  side by side.
- After kit work: status, cost bases, and cap hits together, not several engines.
- The telemetry panel looks stale and you want a fresh page.
- **Not** for analysis or a routing change — it renders what the owning engines computed; reach
  for `bench-routing` or `repo-bench` instead.
- **Not** something to paste, publish, or open on this skill's behalf — that step is always
  yours.

### Worked example

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/dashboard.py" build --checkout "$(git rev-parse --show-toplevel)"
```

It writes `index.html` and a `build.json` receipt, then prints the page path, receipt path,
build time, namespace counts, one line per panel, caps hit, and a bare count of notes — never
the notes. It only runs plain `build`; asked for the receipt, it gives its path. `where` shows
the destination without building; `demo` builds once from synthetic data, removed on exit.

### Failure modes & fallbacks

- **Nothing to show.** It says so — "no ledger found", "never captured", "no evaluation runs"
  — never a zero.
- **A cap was hit.** Named in the page's bounds section, not hidden by showing less.
- **A record fails to load** (an unrecognized version, an undecodable file, a linked
  telemetry, journal or evals entry). Noted, not rendered; the build does not fail.
- **Dollars come from your transcripts.** Priced by default; `--no-transcripts` opts out, and
  the scorecard shows its own "dollars n/a" note instead.
- **Not inside a checkout.** An empty `--checkout` makes the engine refuse; the skill checks
  first, builds nothing, and asks for `--checkout <path>` instead.

### Cost & safety

The build reads every other store read-only and runs just two read-only git commands,
skippable with `--no-git`; it writes only its own dashboard store or `--out-dir`. A refresh's
snapshot writes the telemetry engine's own store. The page carries no script, external
stylesheet, image source, or font; its Content-Security-Policy forbids every network load. No
dollar figure is this skill's own — each is an owning engine's, verbatim.

### Related

- [journal](journal.md) — one of the digests this page reads, written and dated by that skill.
- [cost-report](cost-report.md) — the deeper transcript-spend analysis behind the scorecard's
  dollar figures.
- [update](update.md) — freshness across harness installs, versus this page's freshness across
  stores.
- [Deep dive: privacy](../../deep-dives/privacy.md) — the privacy model this page's scrubbing
  follows.
