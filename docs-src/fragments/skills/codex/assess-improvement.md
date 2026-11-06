### What it does

Answers "where could this codebase improve?" with evidence instead of taste. The skill reads
the repository, looks for a small recurring pain, and returns a scoped findings report with
task briefs someone else can execute later. It runs inside the Codex session you already
have, changes nothing in the target, and treats "no supported intervention" as a sound
answer.

### When to reach for it

- Use it for evidence-driven improvement planning before anyone writes a patch.
- Use it to assess every supported harness of a Polytropos checkout independently, without
  carrying a pricing, capability, or enforcement claim from one harness to another.
- Use it when a later implementer needs a brief that stands on its own.
- **Not** for implementing or activating a change; the result is planning input, not
  authorization to modify the repository.

### Worked example

```text
$assess-improvement where could verification be strengthened in this repository?
```

The skill restates repository and revision, requested outcome, included components,
allowed evidence, exclusions, and unknown access before it reads anything else. It then
establishes the baseline, maps which component owns each behavior, and tests each candidate
for applicability and no-fit. Every material claim lands in an evidence ledger with a
categorical status — `observed`, `documented`, `inferred`, `unknown` / `unverified`, or
`insufficient-evidence` — and the report closes with zero or more task briefs prepared
from `references/assessment-template.md`.

### Failure modes & fallbacks

- A single observation creates a hypothesis, not recurrence; the report says so.
- Absence, a plan, a stale document, or a schema is not a defect. Expect `unknown`,
  `unverified`, or `insufficient-evidence` where evidence stops.
- The assessment stops when no small recurring signal exists, required evidence is
  unavailable, or the next step needs authorization not already granted.
- A managed copy of the skill may contain `{{POLYTROPOS_ROOT}}`; that placeholder must be
  resolved before bundle-owned material is cited.

### Cost & safety

Target source and configuration are read-only by default; writing the requested report or
briefs to the designated output location is the only sanctioned write. The skill does not
install packages, mine private telemetry, invoke paid or private providers, make network
calls, or change policy or release state because it is active. A test that needs mutation
runs against a temporary copy, with that limitation disclosed. No numeric probability is
invented, and candidates are ranked only within the assessed scope.

### Related

- [architect](architect.md) plans a brief you decide to act on.
- [graphify](graphify.md) maps an unfamiliar repository as advisory evidence.
- [doctor](doctor.md) checks the Codex install itself, which this skill does not assess.
