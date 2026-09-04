### What it does

Shows how a Codex session's context grew and roughly what kind of record filled it —
but draws a hard line at what rollout logs can prove: they carry token counts and
record types, never which specific prompt, instruction, or tool actually filled the
window, and this skill refuses to guess rather than approximate one.

### When to reach for it

- Wondering why a session's context ballooned, at the level rollout logs can actually
  answer.
- Auditing resident config surfaces in a repo against a token budget.
- Comparing sessions to see whether growth looks routine or unusual for this kind of
  work.
- **Not** for live pruning guidance or a GUARDRAILS.md residency check — `watch` is
  Claude-only outright, and `constraints --harness codex` can only return the honest
  fidelity-limit line instead.

### Worked example

```bash
python3 bin/context_weight.py session --harness codex --codex-home <codex-home>
python3 bin/context_weight.py overview --harness codex --codex-home <codex-home>
python3 bin/context_weight.py audit --project <repo>
```

`session` and `overview` report token-count growth curves and record-type byte
shares — never turn a byte share into a claim about which prompt or tool filled the
window. `audit` checks resident config surfaces against a budget, in tokens only.

### Failure modes & fallbacks

- **`constraints --harness codex`.** It can only return the engine's fidelity-limit
  line — Codex cannot answer live pruning or whether a kit's GUARDRAILS.md is still
  resident; cross-link the Claude page for that story instead of implying Codex has
  it.
- **A byte share gets read as content attribution.** It never is one — say what kind
  of record filled the window, never which instruction or tool did.
- **The plugin root can't be proven.** Stop and point at [doctor](doctor.md) rather
  than guessing a path.

### Cost & safety

Every command here is read-only measurement over local rollout logs — nothing
dispatched, nothing written. The audit is about resident tokens, never dollars, and
every estimated figure carries its label; no context estimate here is a billing
statement.

### Related

- [Deep dive: context weight](../../deep-dives/context-weight.md) — the fuller
  fidelity story and what the Claude harness can additionally support.
- [usage](usage.md) — real historical Codex activity, versus this page's token-weight
  estimate.
- [doctor](doctor.md) — the root-resolution check every Codex skill depends on.
