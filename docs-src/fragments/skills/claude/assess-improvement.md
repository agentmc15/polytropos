### What it does

You suspect a codebase could be better and want more than an opinion. This skill reads the
repository as it stands, looks for a small pain that keeps recurring, and writes a findings
report plus task briefs a later implementer can pick up cold. Nothing in the target changes,
and "no supported intervention" is a legitimate result.

### When to reach for it

- Someone asks where a codebase could be improved and you want every claim tied to cited
  evidence.
- Before committing to a broad redesign, an incident remedy, or a provider proposal, to get
  a scoped conclusion first — including `no-fit`.
- Assessing polytropos itself or another harness ecosystem, one surface at a time.
- **Not** for implementing, activating, or promoting a change: the report authorizes
  nothing, and the skill grants no new authority to spend, fetch, or write.

### Worked example

```
/polytropos:assess-improvement where could retry handling in this service be improved?
```

The reply opens by restating the scope: repository and revision, components and harnesses,
allowed evidence, and exclusions. The report rests on an evidence ledger, one row per
material claim, each carrying one of the card's statuses:

| Status | What it means |
|---|---|
| `observed` | directly supported by current source, a fixture, a record, or an authorized measurement |
| `documented` | stated in maintained material, not independently verified here |
| `inferred` | a bounded interpretation, with its reasoning and alternatives given |
| `unknown` / `unverified` | evidence is absent or could not be checked |
| `insufficient-evidence` | cannot support an expected-benefit or promotion claim |

Zero or more self-contained task briefs follow, each with its scope, the authorities to
preserve, acceptance criteria, offline verification, and a rollback condition.

### Failure modes & fallbacks

- **One failure is not a pattern.** A single observation creates a hypothesis; it cannot
  establish recurrence or an expected benefit.
- **Evidence is missing or off limits.** The state is labeled `unknown`, `unverified`, or
  `insufficient-evidence`, and the assessment stops when the next step needs authorization
  that is not already present.
- **A candidate needs something gated** — a new permission boundary, private data, a paid
  provider. That is recorded as a prerequisite, never assumed.
- **Broad executable policy languages and autonomous self-modification** are `no-fit` or
  deferred by default.

### Cost & safety

Target source and configuration are read-only; the one sanctioned write is the report and
its briefs at the output location you name. The skill does not install packages, mine
private telemetry, invoke paid or private providers, make network calls, or change policy
or release state because it is in use. A test that needs mutation runs against a temporary
copy and says so. No probability is invented: a supplied number is recorded with its
target, provenance, and validation status.

### Related

- [architect](architect.md) — turns a brief you decide to act on into an execution kit.
- [graphify](graphify.md) — a structural map of an unfamiliar repo, as advisory evidence
  for the baseline.
- [Parity matrix](../index.md) — where else this card ships, and why Cursor carries it
  outside the matrix.
