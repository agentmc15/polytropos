### What it does

You already have a routing ledger, a scorecard, telemetry snapshots, journal digests, and
evaluation runs scattered across every checkout on this machine — each honest alone, but
nowhere together. This skill builds one offline HTML page over them: it reads what those
engines reported and lays it out panel by panel, pricing, ranking, and summarizing nothing.

### When to reach for it

- A whole-machine view before deciding what to check next: ledger, scorecard, and telemetry,
  side by side.
- After a stretch of kit work: status, cost bases, and cap hits together, not several engines.
- The telemetry panel looks stale and you want a fresh page.
- **Not** for analysis or a routing change — it renders what the owning engines computed; reach
  for `bench-routing` or `repo-bench` instead.
- **Not** something to paste, publish, or open on this skill's behalf — that step is always
  yours, in your own browser.

### Worked example

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/dashboard.py" build --checkout "$(git rev-parse --show-toplevel)"
```

It writes `index.html` and a `build.json` receipt, then prints the page path, receipt path,
build time, namespace counts, one line per panel, caps hit, and a bare count of notes — never
the notes. It only runs plain `build`; asked for the receipt, it gives that path, not the
contents. `where` shows the destination without building; `demo` builds once from synthetic
data, removed on exit.

### Failure modes & fallbacks

- **Nothing to show.** It says so — "no ledger found", "never captured", "no evaluation runs"
  — never a zero.
- **A cap was hit.** Named in the page's bounds section, not hidden by showing less.
- **A record fails to load** (an unrecognized version, an undecodable file). Noted, not
  rendered; the build does not fail.
- **Dollars need real transcripts.** Pass `--no-transcripts`; the panel gives the owner's
  reason, or says plainly it recorded none.
- **Not inside a checkout.** An empty `--checkout` makes the engine refuse; the skill checks
  first, builds nothing, and asks for `--checkout <path>` instead.

### Cost & safety

Reading is the whole job: every store touched is opened read-only; its only subprocesses are
two read-only git commands, skippable with `--no-git`. Writing is confined to its own dashboard
store or `--out-dir`. The page carries no script, stylesheet, image source, or font; its
Content-Security-Policy forbids every network load. No dollar figure is this skill's own —
each is an owning engine's, verbatim.

### Related

- [journal](journal.md) — one of the digests this page reads, written and dated by that skill.
- [cost-report](cost-report.md) — the deeper transcript-spend analysis behind the scorecard's
  dollar figures.
- [update](update.md) — freshness across harness installs, versus this page's freshness across
  stores.
- [Deep dive: privacy](../../deep-dives/privacy.md) — the privacy model this page's scrubbing
  follows.
