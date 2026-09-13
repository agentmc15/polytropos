# The NOTES.md ledger — outcome, agent, reviewer, and defect lines

Detail moved out of `skills/execute/SKILL.md` by roadmap step 22 so the entry point carries the mandatory loop; the text below is the binding grammar it points at, unchanged.

## Outcome ledger — one line per finished task

NOTES.md carries SIX machine-read line families — `outcome:`, `agent:`, `reroute:`,
`session:`, `reviewer:`, `defect:` — specified here and in the two sections below. **Always
backtick any of those six tokens when you quote ledger grammar in NOTES.md prose.** A line
that merely *starts* with one of them parses as real data whether it is plain, bulleted, or
indented, so unbackticked grammar in prose becomes fabricated evidence in the scorecard. The
rule is stated once, here, and binds all six families.

The moment a task reaches `done` or `blocked`, append ONE machine-readable line to NOTES.md —
this is the input `bin/routing_scorecard.py` turns into the kit's routing-quality scorecard:

    `outcome: <task-id> model=<model> attempts=<n> result=<result> review=<review>`

- `model` — what the task actually ran on: its `model` pin, or the escalation target when a
  Fable consult did the fixing.
- `attempts` — implementer dispatches, counting retries and escalation (clean first try = 1).
- `result` — exactly one of `pass` (first dispatch, verify passed) | `retry-pass` (passed on
  the retry) | `escalated-pass` (passed only via the escalation valve) | `blocked` |
  `budget-stop` (the run stopped cleanly at a declared **Budget dial** cap before any dispatch
  happened — see below; it carries no verdict about the task and is excluded from first-try/
  escalation-rate signals for exactly that reason).
- `review` — exactly one of `clean` (verifier/reviewer accepted the work unchanged) |
  `revised` (changes were required after the implementer claimed done) | `none` (no
  independent review beyond the verify command).

Three further fields are OPTIONAL and ride that same line. They are execute-owned, and
**absent means today's behavior**: a line without them parses and scores exactly as it always
has, so every kit already executed stays valid routing evidence. Never add them to the task
contract — like the whole ledger, they are a NOTES.md line format, not task fields:

    `outcome: <task-id> model=<model> attempts=<n> result=<result> review=<review> [run=<run-id>] [parent=<task-id>] [failure=<class>]`

- `run` (optional) — the id of the driver invocation that produced this line, formatted
  `<UTC-date>-<4 hex>`, e.g. `run=2026-07-26-9f3a`. ONE id per driver invocation, stamped on
  every outcome line that invocation writes, so a resumed kit's lines separate by run. Run ids
  are CONTENT-FREE by rule: a UTC date plus four hex characters, never a hostname, username,
  path fragment, or transcript text — NOTES.md is committed in consumer repos.
- `parent` (optional) — the task id that SPAWNED this outcome, set ONLY on `result=escalated-pass`
  outcomes and naming the task the consult was spawned for. It records lineage (what spawned
  what) so an escalation can be grouped under its parent task. Ordinary outcomes omit it, and
  a task is never its own parent. **A consult that did NOT succeed carries no `parent=`** — a
  blocked consult writes `result=blocked` and nothing else, because `escalated-pass` is the only
  value in the vocabulary that means "an escalation resolved this". `bin/routing_scorecard.py`
  and all three drivers enforce exactly that: a `parent=` on any other result is dropped with
  an "out of grammar, ignored" note, taking the line's `failure=` class down with it.
- `failure` (optional) — set ONLY on `blocked` or escalated outcomes: exactly one of
  `execution` (the work itself failed — a crash, a bad edit, a tool error) | `coherence` (the
  agent lost the plot — drifted from the brief, contradicted itself, looped) | `verification`
  (the verify step was the failure — it never ran, could not fail, or passed work that was
  wrong). Those three classes are the ENTIRE vocabulary; a finer-grained label stays free text
  in NOTES.md prose and never enters the line, because a coined fourth class aggregates with
  nothing.

Of the three, `run=` is invocation provenance, not an escalation signal: it belongs on EVERY
outcome line a driver invocation writes, clean pass included. `parent=` and `failure=` are the
two that are restricted — present only on `escalated-pass` and on blocked/escalated outcomes
respectively — so a clean pass carries `run=` but omits both of those. A fully-loaded line
looks like:

    `outcome: T7 model=fable attempts=3 result=escalated-pass review=clean run=2026-07-26-9f3a parent=T4 failure=verification`

These fields belong to the `outcome:` family, so the backtick rule stated above for the six
machine-read line families binds them too: quote a whole `outcome:` line in NOTES.md prose
without backticks and it parses as real data, run id and lineage included.

Unknown `key=value` pairs are ignored by the parser, and re-running a task just appends a
fresh line — the scorecard takes the LAST line per task id.


## Agent ledger — one line per per-task subagent

Per-task dollar attribution rides on knowing which subagent transcript served which task. The moment any per-task dispatch returns — the implementer (step 2), a retry, the verifier (step 3), or the Fable escalation consult — append ONE machine-readable line to NOTES.md recording the agent id the Agent tool reported:

    `agent: <task-id> id=<agent-id> role=<implementer|verifier|escalation|scout|test-author|second-verifier|red-team|security-auditor|docs-editor|synthesizer> model=<model> [findings=<n> confirmed=<n>] [result=<accepted|revised|blocked>]`

- `id` — the agent id from the Agent tool's result. The subagent's transcript is the `<agent-id>.output` file in the session's tasks scratch dir — the file `--by-task` prices.
- `role` — exactly one of `implementer` (retries included — each retry dispatch appends its own line with its own agent id) | `verifier` | `escalation` (the Fable consult).
- `model` — the alias the dispatch actually ran on: the task's pin, an applied re-route's upgraded alias, or the escalation target.
- `findings` / `confirmed` (optional, only meaningful together, and meaningful only for the finding-producing roles — `verifier`, `test-author`, `second-verifier`, `red-team`, `security-auditor`; an `escalation` line carries `result=` alone, because a consult delivers a fix rather than a verdict and the scorecard reads no escalation precision, and the no-findings roles `scout`, `docs-editor`, and `synthesizer` record no quality counts at all) — the dispatch's ADJUDICATED outcome. `findings` is the number of distinct defects the dispatch's verdict raised: count the verdict's distinct claims exactly as the verdict itself presented them — never re-bundle or split them to flatter the ratio. `confirmed` is how many you, the orchestrator, adjudicated as real, and a finding is real only when it produced a concrete artifact: a code or doc change, a claim reverted, a `defect:` line recorded, a task blocked. A finding you acknowledged but changed nothing for is NOT confirmed, and when you are unsure whether a finding is real it is NOT confirmed. Adjudicate at the moment the verdict is resolved and never revisit that adjudication — appending a later enriched line (below) for evidence that lands afterwards is the sanctioned mechanism and is NOT a backfill; backfilling means altering an adjudication already made.
- `result` (optional) — the fate of the dispatch's product under downstream scrutiny: `accepted` (stood as delivered) | `revised` (materially overturned or corrected) | `blocked`.
- Timing: append the bare line the moment the dispatch returns, exactly as before. When adjudication lands later, append a SECOND full line for the same task id + agent id carrying the quality fields — the scorecard keeps the LAST line per `(task-id, agent-id)`, so the enriched line wins: `agent: T7 id=a1b2c3 role=verifier model=sonnet findings=3 confirmed=1 result=revised`
- Implementer lines normally OMIT the quality fields: implementer quality already lives in the `outcome:` ledger, and the scorecard ignores an implementer `result=` — one number, one home.
- A warm sidekick serving a cluster gets one line PER TASK it serves, all carrying the SAME agent id — the shared id is what lets the scorecard attribute the one shared transcript to the cluster as a unit instead of faking a per-task split.
- Do NOT record ad-hoc scouts or phase reviewers here, and the two exceptions are narrow in DIFFERENT ways. An ad-hoc scout — the "let me look around first" read a lean driver does on its own — stays off the ledger entirely, exactly as before; but a `scout` DECLARED on PLAN.md's `roles:` line is a per-task dispatch and IS recorded, as an `agent:` line with `role=scout` (see `references/roster.md`). A phase REVIEWER is still never an `agent:` line — its verdict is recorded by its own `reviewer:` family, exactly as before; but the declared phase-scoped roster roles (`security-auditor`, `docs-editor`) ARE recorded as `agent:` lines, carrying the phase token in the task slot. What holds for every one of them is the never-split law: a per-phase or per-run transcript deliberately lands in the breakdown's unattributed line and is never split per task — which is why those roles' dollars read n/a in the `--roles` card even though their dispatches are recorded.
- The line is OPTIONAL and execute-owned (precedent: `outcome:`/`reroute:`/`session:` — a NOTES.md line format, not a task field). Unknown `key=value` pairs are ignored, a repeated task-id + agent-id pair takes the LAST line, and a kit with no `agent:` lines simply degrades to whole-kit dollars — never record a guessed agent id.


## Role ledger — reviewer verdicts and brief defects

Two more OPTIONAL, execute-owned NOTES.md line families (same precedent as above:
`outcome:`/`reroute:`/`session:`/`agent:` are line formats, not task fields).

**Phase reviewers** get their own family. After the step-6 reviewer returns and you
adjudicate its findings, append ONE line per phase:

`reviewer: <phase> model=<model> findings=<n> confirmed=<n> [result=<accepted|revised|blocked>]`

for example `reviewer: P1 model=opus findings=2 confirmed=2 result=accepted`. `findings` and
`confirmed` carry exactly the counting and adjudication rules defined for the agent ledger
above. `result` is the fate of the REVIEW itself, never of the phase: `accepted` when the
verdict stood as delivered (you confirmed its findings), `revised` when the verdict was
materially overturned or withdrawn, `blocked` when it could not be adjudicated at all. A
reviewer `result=` therefore never says whether the phase passed — the phase's outcome is
already recorded in its tasks' `outcome:` lines. `model=`, `findings=`, and `confirmed=` are
all MANDATORY here: an incomplete or self-contradictory (`confirmed` > `findings`) reviewer
line is DISCARDED WHOLE with a note, losing that phase's entire review record — unlike an
`agent:` line, where a bad quality field degrades to nothing-recorded in place and the line
itself survives. Re-running a phase review appends a fresh line; the last line per phase
token wins.

**Architect brief defects** are recorded the moment a task brief's defect is CONFIRMED
against repo reality — an implementer stop-and-report you verified, a verify clause that
could never fail or that contradicts its own acceptance, a pinned anchor or line number
proven stale, a helper invoked that no task creates, an escalation consult forced to rewrite
the brief. Append:

`defect: <task-id> kind=<kebab-case-token>`

for example `defect: T3 kind=stale-pin`. Use the task token `-` for kit-level defects (a
stale PLAN decision, say). The kinds: `stale-pin`, `tautological-verify`, `missing-helper`,
`unspecified-path`, `contradictory-acceptance`, `stale-plan-decision`. Reuse an existing kind
whenever one fits and coin a new one ONLY when none does — the architect reads which kinds
RECUR across tasks and kits, and a coined synonym never aggregates with its neighbour. For
the same reason, a second defect of the same kind in the same task repeats that same kind
verbatim on its own line: the scorecard keeps the first and notes the repeat, so one kind
counts once per task, by design. Never suffix a kind (`stale-pin-2`) to force a second
count — a suffix is a new key that hides the very recurrence it was meant to show. This
ledger measures the ARCHITECT, and you, the executor,
are its honest recorder: log the defect even when — especially when — the fix was easy.
