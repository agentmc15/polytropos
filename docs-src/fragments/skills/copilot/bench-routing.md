### What it does

Answers "should this role move to a new or higher model" from a Copilot angle: ranks the
published benchmark, then says plainly that Copilot has no measured per-role ledger of its
own to check that recommendation against — so unlike its Claude sibling, this page can't
tell you whether an upgrade actually pays off here, only what the benchmark implies.

### When to reach for it

- Deciding whether to move a role to a newer or higher-tier model based on published
  capability data.
- You want the honest caveat about what this repo can and can't measure on this harness.
- Sanity-checking a routing change before writing it into a kit's model pins.
- **Not** for a measured verdict — that only exists on the Claude harness, where the kit
  ledger actually has per-task outcomes to check against.

### Worked example

```bash
python3 bin/bench_routing.py roles --harness copilot
python3 bin/bench_routing.py rank --top 10
```

`roles --harness copilot` derives availability from this harness's own pricing data at run
time — an entry matching no dispatchable model is counted, never silently dropped, and the
text card shows an aggregate `N/M benchmark entries dispatchable` while `--json` lists the
unavailable ones by display name. There is no `compare` verdict to lean on here: the
ledger `compare` joins against is Claude-harness implementer evidence, and `compare` has no
`--harness` flag at all — the benchmark's recommendation stands unchallenged from Copilot.

### Failure modes & fallbacks

- **A recommendation gets presented as measured.** It isn't — say plainly that the ledger
  comparison lives only on the Claude harness, and point the user there for it.
- **The Intelligence Index gets read as an agentic or coding score.** It's a
  general-capability composite; say so before recommending a change for an agentic role.
- **The benchmark file looks old.** It's a screenshot-transcribed snapshot with its own
  recorded date — flag a stale-looking one as re-verify-worthy.

### Cost & safety

Every subcommand here is read-only — no dispatch, nothing spent. `usd_per_task` is a
ranking ratio inside the benchmark's own workload, never a bill and never added to what
[usage](usage.md) reports as real spend. Tier words only on this page, never a specific
model id — the roster behind a tier changes, the tier does not.

### Related

- [route](route.md) — the per-task version of this same tiering judgment, for Copilot's
  own roster.
- [frontier-check](frontier-check.md) — the deeper go/no-go once a benchmark points at the
  top tier.
- [Parity matrix](../index.md) — the Claude sibling, where the ledger comparison actually
  applies.
