# PLAN — graph-convergence

Kit directory: `.claude/kits/graph-convergence/` in the polytropos repo.
`autonomy: advisory`

## Goal

Converge the three harnesses (Claude Code, Copilot CLI, Codex CLI) toward the same
graph-engineering properties, using the shared kit contract as the substrate:

| Property | Claude today | Copilot today | Codex today | After this kit |
|---|---|---|---|---|
| Node isolation / tool scoping | models pinned, tools unscoped | agents exist, tools unscoped | none (role preambles) | scoped where the harness allows |
| Deterministic verify edge | prose instruction only | in driver code | in driver code | enforced on all three |
| Node attribution (ids) | heuristic transcript matching | none | none | stamped at dispatch, in ledger |
| Lineage (what spawned what) | none | none | none | `parent=` in shared ledger grammar |
| Declared budget | none (Ralph only) | Ralph loop only | none | optional PLAN `budget:` block |
| Headless kit driver | none (interactive skill) | `copilot_execute.py` | `codex_execute.py` | `claude_execute.py` |

**Done looks like:** full test suite green; a demo kit executed under each driver produces
`outcome:` lines carrying `run=`/`parent=`; `routing_scorecard --history` groups escalations
under their parent tasks; scorecard output on a pre-existing kit (no new fields) is
byte-identical to before.

## Constraints & out-of-scope

- **Python stdlib-only. No pip, no requirements file, no Claude Agent SDK dependency** (see D2).
- **Never invoke the real `claude`/`copilot`/`codex` CLI** from tests or verify commands.
  Injectable runners + `--dry-run` + temp fixtures only, per the existing driver seams.
- **Never write `~/.claude/` (or any home dir) without the setup-skill consent pattern.**
- All three pricing files untouched. No hardcoded prices, model ids, or tiers.
- OUT OF SCOPE: LangGraph or any framework port; knowledge-graph layer (deliberately
  rejected — see docs analysis); rewriting the memory store; fan-out / parallel dispatch on
  the Copilot and Codex drivers entirely (considered and rejected: the only speed win in the
  original scope, it raises token spend and the priority is accuracy + cost); Codex agent
  files (surface doesn't exist).

## Architecture & key decisions

- **D1 — The outcome ledger is the graph substrate.** Ids and lineage land once, in the
  shared `outcome:` line grammar that all three harnesses already write and
  `routing_scorecard` already reads. One grammar change propagates everywhere; no new files,
  no new stores. *Rationale:* the kit contract is the only artifact all three drivers agree on.
- **D2 — The Claude driver shells to headless `claude`, not the Agent SDK.** The SDK is a pip
  package; the repo is stdlib-only by invariant. `codex_execute.py` proves the pattern:
  non-interactive CLI dispatch behind an injectable runner. An SDK port remains future work
  and is out of scope. *Rationale:* preserve the invariant; reuse a proven template verbatim.
- **D3 — Verify enforcement is proof-marker based.** The verify runner writes a
  `verify-pass/<task-id>` marker (timestamped, gitignored, kit-local); the hook fires on
  `PostToolUse` for Edit/Write touching TASKS.md and blocks a `→ done` status flip lacking a
  fresh marker. *Rationale:* hooks cannot observe a subagent's internal behavior; a marker
  written only by the actual verify execution is checkable evidence, same philosophy as the
  telemetry store's "never reconstructed from prose".
- **D4 — Tool scoping is structural, not prompted.** Remove the capability instead of
  instructing against its use: verifier = read + Bash only; reviewer = no Write/Edit. Applied
  in Claude kit-agent templates and Copilot `.agent.md` frontmatter. *Rationale:* a verifier
  that cannot patch code cannot be talked into "fixing it while I'm here".
- **D5 — No fan-out on the paid harnesses.** Driver dispatch stays strictly sequential on
  Copilot and Codex. *Rationale:* fan-out only buys wall-clock time and multiplies real
  AIC/quota spend; the kit's priority is accuracy and cost, so the concurrency work was cut
  from scope rather than gated. This also preserves the standing precedent that the drivers
  never import `copilot_pricing`.
- **D6 — Every new grammar field is optional; absent = today's behavior.** Scorecard on a
  field-less kit must be unchanged (extend the existing "no outcome lines" honesty
  precedent). *Rationale:* years of executed kits are the routing-history evidence base;
  never invalidate it.
- **D7 — Copilot frontmatter tool pins are asserted at MEDIUM confidence,** the
  `--model`-precedence precedent: cite the GitHub docs line in the file, assert as kit
  contract, never live-verify (spends AIC). A correction is a one-file change.
- **D8 — Run ids are content-free.** `run=` is `<UTC date>-<4 hex>`; no hostnames, no
  transcript text, nothing private enters the ledger. *Rationale:* NOTES.md is committed
  in consumer repos.
- **D9 — Failure classes ride the ledger.** Blocked/escalated outcomes may carry
  `failure=<execution|coherence|verification>` — the three-class minimum aligned with the
  AgentRx-style trajectory-failure taxonomy. *Rationale:* recent terminal-agent error
  studies attribute 47–60% of frontier failures to the verification class; per-tier
  failure-class evidence lets the architect fix the failing role (verifier pin) instead of
  blanket tier upgrades.
- **D10 — Verify commands must be able to fail (red → green).** The precheck runs the verify
  against the pre-task tree; a pre-task pass is tautological and blocks the pass marker.
  *Rationale:* the repo already tracks `tautological-verify` as a brief-defect kind — this
  makes it structural instead of observed, at the cost of one subprocess call.
- **D11 — Escalation rate is a monitored cost variable.** The trend view alarms on
  escalation-rate spikes vs the trailing baseline; the statusline can surface it.
  *Rationale:* a drifting verifier silently escalates traffic to the most expensive tier
  with nothing erroring — the alarm converts the repo's most expensive silent regression
  into a visible one. Alarm only; never a behavior change.

## Risks & tripwires

- **Hook event surface.** If `PostToolUse` does not deliver the file path + diff needed to
  detect a TASKS.md status flip → STOP, record `defect:` line, fall back to shipping the
  marker convention consumed by `claude_execute.py` (T5) only, and report upstream. Do not
  invent an event.
- **Headless `claude` flag surface.** Dispatch flags for T5 are pinned from current docs at
  MEDIUM confidence (the codex precedent). If reality disagrees: one-constant change in the
  runner builder, never a redesign mid-task.
- **Grammar drift.** Any task touching the outcome grammar must update
  `skills/architect/SKILL.md`, `skills/execute/SKILL.md`, and `routing_scorecard.py`
  together, or the CLAUDE.md sync invariant is violated → reviewer rejects the phase.
- **Scorecard regression.** Tripwire test: golden output on a synthetic legacy kit
  (`--demo`) asserted byte-stable in T2.
