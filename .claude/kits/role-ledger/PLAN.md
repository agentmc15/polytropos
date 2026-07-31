# PLAN — role-ledger: per-role outcome recording for the kit ledger

autonomy: advisory

## Goal

Make verifier, reviewer, escalation, and architect quality measurable from the kit ledger,
the way implementer quality already is. Today all 125+ `outcome:` lines measure tasks —
i.e. implementers — and the `agent:` lines that DO carry `role=` carry no result. The
observed consequence: `bin/bench_routing.py compare` had to invent a `no_role_evidence`
verdict because architect/reviewer/verifier/orchestrator roles have zero ledger evidence.
This kit is the durable fix: it defines where role outcomes are WRITTEN (the execute skill)
and how they are READ (`bin/routing_scorecard.py --history`), so real evidence accrues from
the next kit run onward.

## Done means (checkable)

1. `parse_agents` accepts optional `findings=` / `confirmed=` / `result=` pairs on `agent:`
   lines (tolerantly, per D2 below); old lines parse exactly as before, with the three new
   event keys present as `None`.
2. Two new NOTES.md line families parse: `reviewer:` (per-phase reviewer precision) and
   `defect:` (architect brief defects, recorded by execute). Both are invisible to every
   pre-existing parser and vice versa.
3. `python3 bin/routing_scorecard.py --history` (JSON and markdown) carries a `roles`
   section: verifier/reviewer precision (findings vs confirmed), escalation results, and the
   architect brief-defect floor — with honest `n/a` / explicit no-evidence lines when the
   data is absent (all 21 existing kits: zero role-quality evidence, and the card SAYS so).
4. `skills/execute/SKILL.md` specifies the writer side (grammar + when + adjudication
   honesty rules) and `skills/architect/SKILL.md` is re-synced per the CLAUDE.md shared-kit-
   contract invariant.
5. Full stdlib unittest suite green (`python3 -m unittest discover -s tests -q`), except the
   one known cross-kit tripwire in R1 below if it fires.
6. `--demo --history` demonstrates a populated roles section with pinned synthetic numbers.

## Decisions (each with the why — executors follow these, not their own taste)

**D1 — Hybrid line design: extend `agent:` for per-task roles; new line types for
per-phase/pre-run roles.** `result=`/`findings=`/`confirmed=` go ON the existing `agent:`
line for `verifier` and `escalation` (and are legal-but-ignored for `implementer`).
Rationale: the `agent:` line already binds task id + agent id + role + model, the execute
contract already declares unknown `key=value` pairs ignored (this exact extension was
anticipated), and last-wins on `(task-id, agent-id)` gives adjudication-time re-emission for
free — execute appends a second, enriched line for the same pair once the findings are
adjudicated, and the parser keeps the last. A separate line type here would duplicate the
whole join for no clarity gain. But `reviewer` (per-phase) and `architect` (pre-run) get NEW
line types (`reviewer:`, `defect:`): the agent ledger deliberately excludes phase reviewers
(per-task dollar attribution must never split a per-phase transcript per task — a pinned
per-task-dollars decision this kit must not disturb), and the current shipped parser would
reject `role=reviewer` with a noisy "unrecognized agent line" note in every old scorecard.
A new line family is simply invisible to old parsers — strictly cleaner backward
compatibility. `AGENT_ROLES` stays exactly `("implementer", "verifier", "escalation")`.

**D2 — Tolerant parsing, evidence never fabricated.** New `agent:` pairs: `result=` outside
`accepted|revised|blocked` degrades to `None` with a note; `findings=`/`confirmed=` must
appear together, parse as ints ≥ 0, and satisfy `confirmed <= findings`, else BOTH degrade
to `None` with a note (self-contradictory evidence is worse than none) — the line itself is
never dropped for a bad quality field (keep/skip criteria are unchanged: `id=` present,
`role=` in `AGENT_ROLES`). Precision is `confirmed_sum / findings_sum`, `None` when the
denominator is 0 — never a fabricated 0% or 100%. This mirrors `parse_outcomes`' existing
degradation style exactly.

**D3 — Warm sidekick attribution (open question 2).** No new mechanism. The attribution key
stays `(task-id, agent-id)`: a warm implementer already gets one `agent:` line PER TASK it
serves (same id), so quality fields attach per task-event, and per-task dollars keep
attributing the shared transcript to the cluster as a unit (untouched). Verifiers are never
warmed — the execute contract pins "verification is NEVER warmed" — so verifier precision
never needs splitting across tasks. Nothing to invent; say so and move on.

**D4 — The architect metric is written by EXECUTE, as `defect:` lines (open question 3).**
Grammar: `defect: <task-id-or-dash> kind=<kebab-token>`. The orchestrator appends one the
moment a brief defect is CONFIRMED against repo reality (implementer stop-and-report
verified, a verify clause traced to a brief error, an escalation consult forced a brief
rewrite). Rationale: the executor is the honest recorder — the architect is not present at
run time, self-grading is conflicted, and brief defects manifest precisely as execution
friction the orchestrator witnesses. Kit-level defects (e.g. a stale PLAN decision) use the
task token `-`. The metric measures the architect — including the one who wrote this kit;
that reflexivity is the point.

**D5 — Retroactive capture is a trap: rejected (open question 4).** No task backfills role
lines into the 21 existing kits' NOTES.md. The confirmed/not-confirmed adjudication was
never made at the time; reconstructing it from prose ("adversarial coverage check → FAIL"
comments and the like) is fabricating evidence with the ledger's authority. The repo's own
precedent is binding: "never record a guessed id", "never a fabricated 0%". Existing kits
contribute zero role evidence forever, and the history card states that honestly — which is
exactly the honesty `bench_routing compare` was missing. (A human who personally adjudicated
a past run may append lines by hand; no task in this kit does.)

**D6 — Read surface: the `--history` card, nothing else.** `build_history` gains one
top-level `roles` key (shape pinned in T4's brief); `HISTORY_SCHEMA_VERSION` bumps 1 → 2;
markdown gains one `## Role quality` H2 between `## Per-tier track record` and
`## Re-route history`, ALWAYS rendered — zero evidence prints an explicit
implementer-only-history line rather than omitting the section (silent absence is what
produced the bench compare fiasco). No new CLI flags, no changes to the per-kit scorecard,
`--live`, or `--by-task` cards. `bench_routing compare` is the downstream consumer and reads
the card later, in its own kit — it reads only `history["tiers"]` today, so the additive key
is safe, and the trend snapshot reader is `.get`-tolerant (verified).

**D7 — Implementer quality is never double-counted.** The roles section does NOT restate
implementer stats from `agent:` lines; the `outcome:` ledger remains the single implementer
source (the per-tier track record). A `result=` on a `role=implementer` agent line is
parsed but ignored by the roles aggregation. One number, one home.

**D8 — Orchestrator quality stays out of scope.** The motivating 8-false-findings datum came
from an orchestrator, but the orchestrator is not a dispatched agent with a ledger line —
measuring it needs a different instrument. `compare`'s orchestrator verdict legitimately
stays `no_role_evidence`. Fence it rather than half-build it.

## Constraints

- Additive and backward compatible: old kits keep parsing byte-for-byte in meaning;
  degraded (field-absent) paths everywhere; stdlib only; no pytest.
- The CLAUDE.md invariant binds: `skills/architect/SKILL.md` and `skills/execute/SKILL.md`
  share ONE kit contract — T6 and T7 must leave both consistent (task fields, status
  vocabulary, layout, `depends:`/`independent:` marking are all UNCHANGED by this kit; only
  execute-owned NOTES.md line families grow).
- Do not commit or push. Never touch `~/.claude/` or anything outside this repo.

## OUT OF SCOPE — executors must NOT

- Touch `bin/bench_routing.py`, `tests/test_bench_routing.py`, or
  `skills/bench-routing/SKILL.md` — a concurrent agent owns them RIGHT NOW. Not even to fix
  a red test (see R1). Reference bench compare in prose only.
- Backfill or edit any existing kit's NOTES.md (all 21 of them) — per D5.
- Edit `CLAUDE.md`, `data/pricing*.json`, or any generated mirror.
- Add CLI flags, change `--live`/`--by-task`/per-kit scorecard behavior, extend
  `AGENT_ROLES`, or alter per-task dollar attribution semantics.
- Invent role-based re-routing or thresholds — the roles card DESCRIBES, it judges nothing.
- Rename or renumber any existing card key, note string, or schema constant beyond what T4
  pins (`HISTORY_SCHEMA_VERSION` 1→2 is the only version change).

## Risks and tripwires

- **R1 — the pinned real-ledger test in `tests/test_bench_routing.py`.** As of kit-writing
  it asserts the repo's LIVE aggregate tier counts (sonnet 86 with_outcome etc.). Executing
  THIS kit appends fresh `outcome:` lines to this kit's own NOTES.md, which will change
  those aggregates and may redden that untouchable test at T8's full-suite run. Tripwire:
  if the full suite fails ONLY there, and the failure is the ledger-count pin, report it as
  a known cross-kit seam (name this PLAN section) and stop — do NOT edit the fenced file,
  do NOT delete ledger lines to appease it. The concurrent agent's in-flight changes may
  also have already removed or relaxed it.
- **R2 — grammar collision with prose.** A NOTES.md prose line starting `reviewer:` or
  `defect:` would silently become data. Verified zero such lines exist today; T8 re-proves
  it across all pre-existing kits. If a collision appears mid-run, stop and report.
- **R3 — pinned-key-set tests.** `set(card)` and `schema_version == 1` pins live in
  `tests/test_routing_history.py` AND `tests/test_crossrepo_trend.py`; T4 must update every
  HISTORY-card pin in both, and must NOT touch trend-card pins (`TREND_SCHEMA_VERSION`
  stays 1) or per-kit/live-card pins (their schemas stay 1).
- **R4 — the "frozen-by-policy" comment.** `run_history` carries a comment saying
  `build_history` keeps "no ninth key"; T4's additive `roles` key supersedes that recorded
  decision — update the comment so it doesn't lie, and say why (schema v2).
- **R5 — self-affirming tests.** Each parser task writes its own tests; every verify
  command therefore also carries an independent `python3 -` behavioral probe pinned in this
  kit, and the kit verifier re-runs those probes adversarially.
