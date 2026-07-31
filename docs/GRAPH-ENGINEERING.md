# Graph-Engineering Properties in polytropos

The graph-convergence kit (`.claude/kits/graph-convergence/`) implements a shared graph-engineering substrate across three execution harnesses: Claude Code, GitHub Copilot CLI, and OpenAI Codex CLI. This doc maps the kit's outcome to the graph-engineering vocabulary it uses, explains what was deliberately rejected and why, and points to deeper sections of the architecture.

Every behavioral claim below is stated against the code that implements it, and names the file. Where a property is asymmetric across the three harnesses — several are — the asymmetry is stated rather than smoothed over.

## The Convergence Properties

The kit's goal is to converge the three harnesses toward six properties — the scaffolding for building and executing multi-step work reliably. The three "today" columns are the starting state per harness, taken from PLAN.md's own convergence table; they differ, and collapsing them into a single "before" would overstate what this kit delivered on the two harnesses that already had headless drivers and in-driver verify:

| Property | Claude today | Copilot today | Codex today | After this kit |
|---|---|---|---|---|
| Node isolation / tool scoping | models pinned, tools unscoped | agents exist, tools unscoped | none (role preambles) | scoped where the harness allows |
| Deterministic verify edge | prose instruction only | in driver code | in driver code | enforced on all three |
| Node attribution (ids) | heuristic transcript matching | none | none | stamped at dispatch, in ledger |
| Lineage (what spawned what) | none | none | none | `parent=` in shared ledger grammar |
| Declared budget | none (Ralph only) | Ralph loop only | none | optional PLAN `budget:` block |
| Headless kit driver | none (interactive skill) | `copilot_execute.py` | `codex_execute.py` | `claude_execute.py` |

This is the kit's **own** vocabulary — the framing that the repo's decision-making was built on. Section 9 of [HOW-IT-WORKS.md](HOW-IT-WORKS.md#9-limitations-and-design-notes) elaborates the design tradeoffs.

## Mapping Properties to Implementation

Each property now has live code and structure backing it.

**Node isolation / tool scoping.** There is no shared agent-template directory; each harness scopes tools in its own surface, and the three surfaces are not equivalent.

- **Claude** — a kit-generation rule in `skills/architect/SKILL.md`: every kit the architect generates gives its `<slug>-verifier.md` and `<slug>-reviewer.md` agent files (under the target project's `.claude/agents/`) `tools: Bash, Read, Grep, Glob` — read and search plus Bash, no Write, no Edit. The implementer's tools stay unpinned, because writing is its job. This repo's own `.claude/agents/graph-convergence-{verifier,reviewer}.md` carry that pin.
- **Copilot** — frontmatter pins in the bundle's agent files: `copilot/.github/agents/verifier.agent.md` (`tools: read, execute`) and `copilot/.github/agents/reviewer.agent.md` (`tools: read, search, execute`). The alias vocabulary is GitHub's, not Claude's, so the two sides are not a translation of each other: the reviewer's pin is the equivalent of the Claude one, and the verifier's is narrower — it omits `search`, which the Claude template grants. Both implementers followed their briefs, so the asymmetry is architect-side, not a defect in either file. The alias set is asserted at MEDIUM confidence from GitHub's published "Custom agents configuration" reference and never live-verified, because verifying it would spend real AI Credits (PLAN D7); the provenance comment ships in each agent file.
- **Codex** — no tool-scoping surface exists. The Codex roles are prompt preambles (`codex/prompts/{implementer,verifier,reviewer,…}.md`) whose frontmatter carries a description and nothing else, and PLAN.md's out-of-scope list fences Codex agent files out for exactly that reason. `docs/CODEX-HARNESS.md` does not document tool isolation, and nothing else does either — the property is simply not available on that harness today.

The pin is paired with a stated practice in both read-only Claude roles, and the reason is written into the agent files: Bash alone can delete or rewrite any tracked file, so removing Write/Edit removes the *casual* path, not the capability. Prefer non-mutating checks; mutate a temp copy, never a tracked file in place; restore byte-for-byte and say so; close with `git status --porcelain`.

**Deterministic verify edge.** Two separate mechanisms, and it matters which is which.

*In the drivers.* `bin/claude_execute.py`, `bin/copilot_execute.py`, and `bin/codex_execute.py` each read a task's verify command out of TASKS.md, run it after dispatch, and use its exit code to decide `done` vs. escalate vs. `blocked`. All three parse exactly one dialect (`_extract_verify`): the first ```` ```bash ```` fence following a `**Verify.**` marker. Counted rather than assumed, across this repo's 27 kits and 239 task blocks: 22 kits (188 blocks) use that form, and a driver reads a verify command from every one of them. The other 5 kits (51 blocks) write it differently — 3 use a `**Verify:**` marker (two with a fence, one with a backticked one-liner) and 2 use a single-line `` - Verify: `<cmd>` `` — and a driver reads no verify command from any of their tasks.

*In the hook.* `bin/kit_verify_hook.py` is the proof-marker mechanism (PLAN D3/D10) and has three roles. `precheck` runs the task's verify command against the **pre-task** tree through an injectable runner: a command that already passes before any work starts is tautological, is recorded as a `defect: <id> kind=tautological-verify` ledger line, and blocks the pass marker (red → green only). `record` writes a timestamped, gitignored, kit-local marker under `<kit>/verify-pass/<task-id>` carrying the exact verify-command text it certified, and refuses when precheck flagged that same command tautological. `hook` is the PostToolUse entrypoint that actually *blocks* a `→ done` status flip lacking a fresh, command-matched marker; unlike the drivers it parses **both** verify dialects, so its command-match check binds on 26 of the 27 kits.

Two honest limits on that blocking. It is the **hook's**, not the driver's: `bin/claude_execute.py` deliberately does *not* block the `done` write when `record` refuses — it writes the `defect:` line, prints the refusal to stderr, and exits nonzero, but lets status follow the verify's own exit code, because letting an analysis signal change routing state is the shape PLAN D11 forbids. And the hook is **opt-in**: it is installed into `~/.claude/settings.json` only through the setup skill's separate, explicit confirmation step, nothing in this repo auto-registers it, and it is not registered here. It also fires only on the `Edit` tool — a full-file `Write` rewrite of a TASKS.md is a silent no-op, because PostToolUse's `Write` payload carries no prior content to diff against.

**Node attribution (ids).** Run ids are content-free by rule (PLAN D8): a UTC date plus four random hex characters, never a hostname, username, path fragment, or transcript text — a kit's `NOTES.md` is committed in consumer repos. All three drivers generate one id per invocation and stamp `run=` on every `outcome:` line that invocation writes, clean passes included. Attribution into the *dispatch prompt* is 2-of-3: `copilot_execute.py` and `codex_execute.py` prepend a kit/run/task id preamble to the brief (`build_id_preamble`); `claude_execute.py` stamps the ledger only. Task ids come from TASKS.md (`T1`, `T2`, …) and are immutable once assigned. The outcome line also records the model dispatched to, the attempt count, the result, and the review outcome.

**Lineage (what spawned what).** When a consult spawned to rescue another task succeeds, its outcome line names that task in `parent=`. The field is restricted to `result=escalated-pass` and nothing else: all three drivers gate the write on `PARENT_RESULTS` (a run given `--parent` that ends blocked writes no `parent=`), and `bin/routing_scorecard.py` drops a `parent=` on any other result with an "out of grammar, ignored" note. A task is never its own parent — the drivers reject that at the writer with exit 2, and the reader drops it. `routing_scorecard --history` groups these escalations under their parents; that grouping does not consult the tier ladder, so it works for every kit, unlike the per-tier escalation-rate figures (see the honest limitation below).

**Declared budget.** The `budget:` dial counts **events, not dollars** — no driver does spend tracking of any kind. A kit's PLAN.md may carry one optional line, a PLAN.md line family exactly like `autonomy:` and never a task field:

```
budget: max-dispatches=N max-escalations=N max-consults=N
```

Any subset of the three keys, in any order; absent means unbounded, today's behavior, no check performed. Before dispatching anything, each driver recomputes usage from the kit's **own recorded `outcome:` ledger** in NOTES.md — `attempts=` summed for dispatches, `attempts - 1` per line for escalations, lines carrying `parent=` counted as consults — so the cap holds across resumed sessions rather than within one process. On a cap already reached: nothing is dispatched, the task's status is left exactly as found (pending stays pending — a budget stop is not a verdict on the task), the stop is printed naming which cap was hit and how many tasks are untouched, and ONE `outcome: … result=budget-stop` line is appended. The interactive execute skill honors the same block under the same names, so a kit behaves the same either way.

One case declines even that ledger line: a task that already carries a recorded `result=`. A `budget-stop` is not a verdict and later lines for the same task id normally win, so writing one over a recorded `blocked` would erase that verdict and its `failure=` class from the kit card and from `--history`. The drivers decline the write and say so on stderr; `routing_scorecard.parse_outcomes` independently refuses to be overwritten, keeping the verdict and noting the dropped budget-stop.

**Headless kit driver.** Each harness now has a scriptable dispatcher, and all three share the same shape: `status`, `run`, and `review` subcommands over a `--kit <dir>` path (the Copilot driver adds a fourth, `budget`, for its own separate dollar-savings mode, unrelated to the count-based `budget:` dial above).

- `bin/claude_execute.py` — `run` handles **one task per invocation** (`--task`, else the first eligible pending task) and dispatches it to **one role's** preamble (`--role`, default `implementer`). On a failing verify it walks the escalation ladder computed at run time from `data/pricing.json` — the first model of every tier above the task's own, cheapest first — re-dispatching the same prompt with the failure evidence appended at each rung, and marks the task `blocked` if the ladder is exhausted. It is not a trio dispatcher and there is no one-shot frontier fallback; driving a whole kit means repeated invocations (or the interactive execute skill).
- `bin/copilot_execute.py` — the same loop for Copilot CLI, resolving model ids and its ladder from `data/pricing.copilot.json`.
- `bin/codex_execute.py` — the same loop for Codex CLI, resolving model ids and its ladder from `data/pricing.codex.json`.

No driver hardcodes a model id, a tier, or a price; every one is resolved from its own pricing file at run time, and no driver reads another harness's file. All three take injectable dispatch and verify runners (tests use stub executables and temp fixture directories — never a real `claude`/`copilot`/`codex` invocation), and `--dry-run` prints the dispatch argv and the verify command while spawning and writing nothing.

## What Was Deliberately Rejected

**Driver fan-out (parallel dispatch).** The original scope included concurrent task dispatch on Copilot and Codex to save wall-clock time. This was considered and cut because fan-out multiplies real AI Credits / quota spend across parallel runs while saving only wall-clock time — the kit's priority is accuracy and cost, not speed. The decision is documented in PLAN D5. Sequential dispatch on all three harnesses is the shipped behavior.

**Framework port (LangGraph or similar).** The repo is stdlib-only by invariant (PLAN D2, CLAUDE.md): no pip installs, no external dependencies. Any framework port (LangGraph, CrewAI, or equivalent) would require a `requirements.txt` and an SDK dependency, violating that invariant. The kit builds graph structure from plain Python and the kit contract (PLAN.md + TASKS.md + NOTES.md files) instead. For a graph-aware framework port, consult the architecture section (§4 of [HOW-IT-WORKS.md](HOW-IT-WORKS.md#4-component-architecture)) for the component tree that would need porting.

**Codex agent files.** Fenced out of scope in PLAN.md because the surface does not exist: Codex offers role prompt preambles, not agent definitions with a tool allowlist, so there is nothing to pin.

**Knowledge-graph layer.** The kit records the decision to omit a knowledge graph but does **not** carry its rationale. Inventing one here would be the worst kind of fabrication — it would read as settled history and every later reader would inherit it as fact. An honest gap beats a confident fiction. If a knowledge-graph implementation emerges, it should do its own analysis rather than adopt a retroactive justification.

**Auto-application of promoted lessons.** The evidence-loop kit (`.claude/kits/evidence-loop/`) introduces a promotion tool that clusters recurring defects and lessons across kits, but stops at a human gate: it never edits GUARDRAILS.md, skills, agent files, or anything tracked. The architecture explicitly requires a future kit for auto-application. See [docs/EVIDENCE-LOOP.md](EVIDENCE-LOOP.md#rule-2-taskslessonsmd-is-live-routing-input--promotion-is-read-only) for the read-only contract and why it matters.

## What Actually Landed

Across all three harnesses, the kit delivers:

- **Ids and lineage in the outcome grammar.** The shared `outcome:` ledger line gained three optional fields — `run=`, `parent=`, and `failure=` (one of `execution`, `coherence`, `verification`) — plus a fifth `result=` value, `budget-stop`. Every one is optional and absent-means-today's-behavior: a kit executed before they existed parses and scores exactly as it always did, which the byte-stability goldens in `tests/test_routing_scorecard.py` pin on both the markdown and the JSON surfaces. A kit's `NOTES.md` is the canonical ledger.

- **Three headless drivers.** `bin/claude_execute.py`, `bin/copilot_execute.py`, and `bin/codex_execute.py`: injectable, testable, scriptable, one task per `run` invocation over a `--kit <dir>` path.

- **Tool scoping where the harness allows it.** Claude kit verifiers and reviewers are generated with a read-only-plus-Bash `tools:` pin; the Copilot bundle pins the same two roles with GitHub's own alias vocabulary (equivalent for the reviewer, narrower for the verifier — not a one-to-one translation); Codex has no such surface. The pin is paired with an explicit practice, because Bash alone can still mutate the tree.

- **Verify enforcement with proof markers.** A gitignored, kit-local marker carrying both a timestamp and the verify-command text it certified, written only by `bin/kit_verify_hook.py record` after a real pass, invalidated by the next `precheck`, and refused outright when the command already passed on the pre-task tree. The `→ done` block is the PostToolUse hook's and is opt-in and consent-gated; the drivers record and report the refusal without blocking the status write.

- **An optional count-based budget dial in all three drivers.** `budget: max-dispatches=N max-escalations=N max-consults=N` in a kit's PLAN.md, checked against the kit's own recorded ledger before dispatch. Counts, never dollars.

- **An honest limitation.** The per-tier routing statistics in `routing_scorecard` key on the `model=` field, whose ladder vocabulary is the Claude Agent-tool aliases (`haiku`/`sonnet`/`opus`/`frontier`). All three drivers write the concrete model id from their own pricing file instead, so a driver-executed kit's outcomes fall outside the ladder and contribute nothing to the per-tier track record — the Copilot and Codex tier words have no home in a Claude-only ladder at all. The scorecard says so per line rather than guessing: it notes that the *tier attribution* was skipped, not the outcome, and the same line still parses, still joins to its task, and still groups correctly under `--history`'s escalation lineage. Fixing it is a grammar change and was left to the architect rather than done mid-kit.

## Deeper Reading

- **§1 — The problem.** Why routing matters and the three problems the plugin solves: [HOW-IT-WORKS.md § The problem](HOW-IT-WORKS.md#1-the-problem).
- **§4 — Component architecture.** The full repo tree, the role of each family of scripts, and the plumbing: [HOW-IT-WORKS.md § Component architecture](HOW-IT-WORKS.md#4-component-architecture).
- **§6 — The measurement layer.** How ledger lines feed the routing scorecard and the five modes of cross-kit analysis: [HOW-IT-WORKS.md § The measurement layer](HOW-IT-WORKS.md#6-the-measurement-layer).
- **§9 — Limitations and design notes.** Cost figures as estimates, honest degradation, context isolation, and price staleness: [HOW-IT-WORKS.md § Limitations and design notes](HOW-IT-WORKS.md#9-limitations-and-design-notes).

For the full plan and decision rationale, see `.claude/kits/graph-convergence/PLAN.md` (the architecture chapter D1–D11) and the phase-by-phase review notes in `NOTES.md`.
