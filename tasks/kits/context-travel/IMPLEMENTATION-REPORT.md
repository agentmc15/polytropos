# Context travel: scope, phased plan, and implementation report

Updated: 2026-11-05 (original plan: 2026-11-01)

## Status and authorization

CT1–CT4 are implemented and accepted within their offline scopes. The latest
full suite passed **6,616 tests with zero failures or errors and two
configuration-dependent skips**. CT4's 48 targeted tests, independent review and
documentation/release checks also passed. Earlier results and failed runs are
retained with their corrections and limits.

The user requested continuation and identified the separate critique branch as
`kit/context-travel`. Its uncommitted draft has now been reviewed read-only.
The [critique reconciliation](CRITIQUE-RECONCILIATION.md) records the exact source
digests, useful corrections, implementation blockers, and a reviewed pilot
alternative. The user chose the original CT1 -> CT2 -> CT3 -> CT4 -> CT5 -> CT6
order. CT2 implements the strengthened read/privacy/evidence requirements;
the alternative pilot sequence is not adopted. No other agent's branch has been
modified. CT4 completed its offline scope on 2026-11-05.
CT5–CT6 remain planned and unimplemented. The user also required the same
codebase in public polytropos and private poly-auto, and selected CT4 completion
followed by reviewed local synchronization. Their private repository exists to
use Copilot workflow capabilities available to private/internal repositories;
the product source, tests, docs, skills, templates and workflow definitions must
remain shared. Publication is still excluded.

[CT2-EVIDENCE.md](CT2-EVIDENCE.md) records the reader implementation, independent
test ownership, observed failing cases, corrections, source digests and checks.
[CT3-EVIDENCE.md](CT3-EVIDENCE.md) records the completed pure lifecycle-view task.
[CT4-EVIDENCE.md](CT4-EVIDENCE.md) records the completed offline transport work.
[PUBLIC-PARITY.md](PUBLIC-PARITY.md) records the local drift assessment and
the prepared local synchronization candidate. Its reviewed tracked tree matches
the private candidate; the original public checkout's concurrent documentation
work remains separate. Existing synchronization runs public-to-private only.
Neither local preparation nor offline tests establish public release or installed
compatibility.

The user authorized Phase 1 implementation beginning with CT1 in an isolated
workspace. Verification must use temporary fixtures and stubs. No live model or
provider runs, installations, GitHub changes, pushes, PR creation, merges,
deployments, or account/configuration changes are authorized.

- Source repository: private `poly-auto`.
- Baseline: `7671894d2ac9e43f1a6c808d5b31477a107b119e`.
- Isolated branch: `codex/context-travel-ct1`.
- Isolated workspace: the managed `context-travel-ct1/poly-auto` worktree.
- Original checkout: untouched by this work; it now holds the separate
  `kit/context-travel` critique draft authored outside this worktree.
- Public candidate: `codex/context-travel-public-sync` in the managed
  `context-travel-public-ct4/polytropos` worktree. The original public checkout's
  concurrent `docs/skills-guide` work is preserved; no publication occurred.

## Intended product outcome

Build a portable, cost-aware delivery system that carries intent, context, and
evidence from conceptualization to deployment and observed outcomes. Issues,
plans, tasks, PRs/MRs, merges, and deployments are connected parts of a continuing
change. PR and merge readiness is the initial bottleneck hypothesis; lifecycle
measurements must establish where automation actually helps.

The lifecycle is:

`intent -> acceptance criteria -> plan -> candidate -> verification and validation -> review/merge -> deployment -> observed outcomes`

Verification asks whether behavior satisfies agreed criteria. Validation asks
whether the criteria and delivered behavior meet the intended need. A passing
check, a task marked done, a successful merge, and a validated outcome are
different records.

Context travel means an agent can obtain a bounded, versioned briefing for its
assignment, inspect the sources behind it, and pass a durable reference or
eligible payload to another agent. The receiving agent checks applicability at
its destination. Conversation transfer, shared credentials, or automatic shared
permissions are not prerequisites and are not implied.

## Existing foundations and gaps

| Area | Existing foundation | Remaining gap |
| --- | --- | --- |
| Plans/tasks | `bin/kit_contract.py`, both kit layouts, acceptance identities | Portable joins from goals through releases and outcomes |
| Repository maps | `bin/graph_ground.py` and `bin/graph_brief.py` | No populated graph found in the assessed checkout; incremental maintenance remains future work |
| Context selection | `bin/decision_context.py`, explicit CT2 readers, CT3 role briefings and CT4 CLI/MCP access | Surface integration, maintained retrieval and measured context savings |
| Evidence | `bin/attempt_ledger.py` and `bin/attempt_history.py` | Lifecycle-wide joins with source completeness and applicability |
| Multiple repos | Cross-repository historical reporting and explicit namespaced CT1 identities | Explicit interface relationships, maintained component views and scale evaluation |
| Skills | Architect, routing, execute, graphify, memory, assessment and reporting workflows | Briefing consumption and contribution through thin adapters |
| Hosting providers | GitHub-specific synchronization and previously inspected advisory automation | Common change record, provider adapters, normalized readiness and authorized execution |
| Measurement | Harness-specific pricing, attempt metadata, scorecards | Comparable lifecycle baselines including maintenance and human effort |

Previously authorized offline reproductions confirmed a Codex precheck gap and
an acceptance-only immediate drift-reporting gap. CT1–CT3 do not fix either. Their
evidence must not be upgraded by a new presentation or schema.

Two reader integration requirements were identified: attempt-history reads
must not fall through to an implicit personal store, and privacy exclusions must
be applied before unauthorized file reads. The older context retrieval prevented
some reads and withheld other sensitive paths only after scanning. CT2 adds its
explicit selected-source boundary without replacing those older entry points;
CT3 consumes the resulting observations entirely in memory.

## Phased roadmap

| Phase | Deliverable | Exit evidence |
| --- | --- | --- |
| 1: Context travel and read-only view | Contracts, explicit readers, lifecycle projection, role briefings, CLI/MCP access, surface packaging | Deterministic output, correct source links, honest missing/stale states, bounded read-only behavior, independent offline checks |
| 2: Maintained context at scale | Versioned indexes, incremental updates, component partitions, explicit cross-repository contracts | Incremental results match a rebuilt reference; warm queries avoid unnecessary whole-repository rereads |
| 3: PR/MR readiness and providers | Portable change record, templates, blocker explanations, read-only provider adapters | Equivalent cases retain consistent meaning and provider-specific restrictions; independent readiness judgments |
| 4: Authorized repair and merge | Bounded repair, verification, single operation owner, fresh mutation-time admission | Offline failure scenarios followed by separately authorized provider-specific live evidence |
| 5: Deployment and outcomes | Artifact/environment linkage, rollout/rollback context, observations tied to intent | Traceable released artifact, mismatch detection, operational and user-outcome evidence |

Each phase is a separate promotion decision. Offline tests do not establish a
live integration, universal reliability, or a financial benefit.

### Phase 1 task sequence

| Task | Responsibility | Status in this work |
| --- | --- | --- |
| CT1 | Versioned request/briefing contract, explicit identities, canonical encoding | Complete; full suite and independent review passed |
| CT2 | Explicit, bounded, privacy-aware source readers | Complete; targeted, independent, full-suite and documentation checks passed |
| CT3 | Lifecycle projection and role-specific briefing selection | Complete; targeted, independent, full-suite and documentation checks passed |
| CT4 | CLI and MCP adapters calling the same query core | Complete; targeted, independent, full-suite and documentation checks passed |
| CT5 | Six-surface skill integration and packaging | Pending; planning only |
| CT6 | Independent baseline/control/candidate evaluation | Pending; planning only |

The intended query operations are `overview`, `brief`, `explain`, `changes`, and
`capabilities`. These are design names; CT1 does not implement commands or tools.

## Complete CT1–CT6 task briefs

These six tasks comprise Phase 1. CT1–CT4 are complete.
CT5–CT6 remain planning briefs, not dispatched work.
Proposed new filenames below do not mean those files exist. Final ownership and
verification commands must be checked against the checkout before each task is
admitted. The active executable TASKS.md now contains CT1–CT4.

### CT1 — Define the briefing contract and identities

**Objective:** establish a shared, versioned data contract that survives transfer
between agents without losing its assignment, source references, or applicability.

**Dependencies:** existing task and provenance contracts. Worker intent: strong,
resolved through central policy.

**Scope and files:** `bin/context_travel.py`, `tests/test_context_travel.py`,
`docs/CONTEXT-TRAVEL.md`, version registration in `bin/release_gate.py`, and
generator-owned documentation. The coordinator owns kit state and evidence notes.

**Interfaces:** pure request and briefing builders/parsers, stable namespaced
task identity, canonical bytes and SHA-256 references. Request identity includes
the repository, kit, unchanged task ID, checkout, revision, source-state ref,
assignment, question, and supplied input references. Stable task identity excludes
checkout/revision so it survives relocation; applicability remains separately bound.

**Acceptance:** deterministic round trips; different repository or kit identities
cannot alias; task IDs are preserved; wrong-assignment or stale-request responses
are refused; unknown provenance stays explicit; malformed or oversized data is
refused; criteria are not silently truncated; text is redacted and bounded; runtime
contract operations perform no external I/O or action.

**Offline verification:** targeted synthetic tests, an actual failing baseline,
independent negative review, then repository-required full suite and generated
documentation checks. No real coding clients, graph extraction, or provider calls.
The implemented targeted command is:

```bash
python3 -B -m unittest discover -s tests -p 'test_context_travel.py' -v
```

**Non-goals:** readers, repository mapping, lifecycle inference, transports,
installers, dispatch, acceptance transitions, or provider operations.

**Completion gate:** targeted and integration checks pass, independent findings
are resolved, exact limitations are recorded, and the coordinator accepts the
bounded change. A schema pass never constitutes user validation or merge authority.

### CT2 — Add explicit, bounded, privacy-aware source readers

**Objective:** read only the sources selected for the query and return a bounded
observation with enough provenance to explain both included and missing context.

**Dependencies:** CT1. Worker intent: strong because source access and privacy are
security-sensitive. Implemented files: `bin/context_readers.py`,
`tests/test_context_readers.py`, `tests/test_safe_paths_context.py`, the stable
helper in `safe_paths`, pure parsers in `graph_brief` and `attempt_ledger`, and
contract/security reference updates. The executable TASKS.md specifies ownership.

**Inputs:** explicit repository ID to root bindings; selected kit and graph paths;
explicit evidence-store selection or an explicit absence; caller bounds and deny
rules. No implicit HOME lookup, provider discovery, remote fetch, or default store.

**Reuse:** `kit_contract` for parsing and identities; `safe_paths` for contained
reads; `graph_brief` for parsing the selected graph; `attempt_ledger` for event
parsing and provenance. Existing path-loading `graph_ground` and `attempt_history`
entry points are not invoked because their additional reads bypass this boundary.
Graph semantics and evidence joins remain later work. Avoid duplicating those
authorities; add a reviewed seam or report unavailable when access cannot comply.

**Outputs:** bounded source observations and references, source-specific freshness,
coverage, exclusions, read failures, and measured read counts/bytes. Raw observations
remain distinct from interpretations. Missing, corrupt, forbidden, and absent
sources have different reasons; forbidden details are not exposed by diagnostics.

**Acceptance:**

- Both kit layouts resolve against an explicit repository root; identical kit names
  in different roots cannot merge evidence silently.
- Sensitive and out-of-scope paths are rejected before opening, including symlinks,
  traversal, credential-shaped filenames, and caller-denied sources.
- Legacy records with missing refs remain unknown; no acceptance or history is
  reconstructed from prose.
- Source changes during a read are detected within the selected coverage and
  returned as inconsistent/unknown, or retried under a finite bound.
- No graph extraction, verification commands, file writes, installations, model
  calls, network calls, or implicit personal-store access occurs.
- A source ceiling stops further reading and discloses incomplete coverage.

**Offline verification:** temporary repos, injected Git observations, temporary
evidence stores, synthetic graphs, denied-read sentinels, corrupt/missing sources,
duplicate kit names, and concurrent-change simulations. Test source-access events,
not merely the final filtered output. The implemented verify commands are:

```bash
python3 -B -m unittest discover -s tests -p 'test_context_readers.py' -v
python3 -B -m unittest discover -s tests -p 'test_safe_paths_context.py' -v
```

**Non-goals:** background watchers, persistent indexes, model-assisted selection,
live provider retrieval, or changing existing acceptance semantics.

**Completion gate:** all mandatory denied-read and identity fixtures pass. A reader
that cannot prove its bounded source policy remains unavailable. Roll back the
new reader integration without modifying historical records.

### CT3 — Compose the lifecycle view and role-specific briefings

**Objective:** answer what the agent needs, why each item was selected, what the
recorded evidence supports, and what remains uncertain.

**Dependencies:** CT1 and CT2. Worker intent: strong. Proposed files:
`bin/lifecycle_view.py`, `tests/test_lifecycle_view.py`, and reference updates.

**Inputs:** validated requests, bounded source observations, explicit intent and
acceptance links when available, selected role, and output budgets.

**Outputs:** an overview, a role-specific briefing, an explanation trace, and a
change comparison. Typed relationships distinguish declared dependencies, code
navigation, task-to-path mentions, measured verification, and recorded outcomes.
Each conclusion names its source and limitations.

**Admitted implementation contract:** the pure `polytropos.lifecycle-view/1`
library composes a validated CT1 request and explicit CT2 observations. Its
`complete`, `partial` and `refused` states describe the projection. A lifecycle
role brief can represent missing criteria; it is deliberately distinct from the
CT1 task-briefing object. The full request is echoed so checkout, revision and
source-state declarations remain visible without implying CT2 attested them.
Operational read counts are validated but excluded from substantive identity.

Intent, current acceptance and dependency-freshness links have explicit subjects
and remain caller declarations. Historical events lacking intrinsic repository
and kit bindings remain unbound even when their task IDs match. A selected source
reference may be compared with the request's same-domain source pin; it cannot
authenticate the sanitized observation or represent the whole source bundle.
Observed acceptance text and explicitly comparable acceptance references are
separate signals. Original acceptance digests are never reconstructed from
redacted text. Every role brief carries full mandatory criteria and all critical
limitation objects, or refuses when they cannot fit.

**Preserved authority:** existing task status/readiness belongs to `kit_contract`.
The view projects facts and existing decisions; it does not introduce a second
acceptance engine. A lexical path mention is not ownership. A graph edge is not
execution dependency or permission. A task marked done is not sufficient evidence
of meaningful precheck, independent review, integration, or user validation.

**Acceptance:**

- Every material finding resolves to source references or is explicitly identified
  as an interpretation with its basis.
- Missing plans and evidence are representable; no invented tasks or acceptance
  records are created to satisfy the CT1 task-briefing shape.
- General overview and partial-response shapes receive their own explicit contract
  or a reviewed version change; CT1 does not silently accept new fields.
- Architect, implementer, verifier, and reviewer views share underlying facts but
  select the context relevant to their different responsibilities.
- Mandatory criteria and unresolved critical limitations remain visible. An
  insufficient budget yields an explicit incomplete/refused briefing.
- Conflicting records remain visible, and stale evidence is not presented as
  current proof. Unknown provider policy cannot become merge readiness.
- Repeated equivalent inputs yield equivalent substantive output. Timing and
  observational telemetry stay outside canonical content identity.

**Offline verification:** independently labeled fixtures for missing criteria,
acceptance-only drift, already-green checks without required baseline evidence,
contradictory notes/ledger records, stale dependencies, and incorrect evidence
joins. Use the existing offline reproductions as negative examples, not as proof
that the underlying drivers have been corrected. Proposed verify command:

```bash
python3 -B tests/test_lifecycle_view.py -v
```

**Non-goals:** accepting work, repairing code, merging, deploying, promoting policy,
or treating a model-written summary as authoritative evidence.

**Completion gate:** mandatory false-readiness cases are correctly explained;
independent review can trace every reported basis. If useful selection cannot be
established, retain a simpler source inventory rather than imply reliable advice.

### CT4 — Expose one read-only core through CLI and MCP

**Objective:** make the same lifecycle questions accessible to terminal and
desktop agents without duplicating business logic.

**Dependencies:** CT1–CT3. Admitted worker intent: strong for transport/access
boundaries; the preliminary mid-tier model was unavailable in the app's worker
pool. Add `bin/context_travel_query.py` as the one shared config/access/query seam,
plus `bin/context_travel_cli.py`,
`bin/context_travel_mcp.py`, and corresponding `tests/test_context_travel_cli.py`
and `tests/test_context_travel_mcp.py`.

**Admitted design:** the startup config selects explicit repository roots, exact
kit/source selections, evidence binding, deny rules and ceilings. Tool arguments
cannot enlarge those grants. Overview and brief accept a live CT1 request, a
structured assignment sealed by CT1's builder, or an already validated CT3
artifact; explain and changes operate on supplied
artifacts without source reads. Authorized subjects are checked in both paths.
Multiple clients can consume the same immutable payload; the server does not
retain or fetch a historical snapshot by reference. CLI and MCP serialize the
same query envelope. The MCP adapter pins the published 2025-11-25 stdio protocol
and processes bounded synchronous calls; cancellation is acknowledged only as
a notification with no promise of interrupting work. Detailed bounds and exact
offline evidence are in CT4-EVIDENCE.md.

**Interfaces:** `overview`, `brief`, `explain`, `changes`, and `capabilities`, each
mapped to the shared core with strict validated parameters. CLI emits stable JSON
and optionally bounded human-readable text. MCP uses the documented protocol
version selected at implementation time. Preserve the stdlib-only repository
constraint; do not introduce an SDK or dependency installation by implication.

**Acceptance:**

- Equivalent CLI and MCP requests have equivalent content and source references.
- Repository paths resolve through explicit authorized bindings; no arbitrary
  source-root or personal-store expansion is accepted from tool text.
- Protocol initialization, discovery, malformed messages, request correlation,
  unknown methods, output limits, and cancellation receive deterministic handling.
- No mutation tool or generic shell/command execution endpoint is exposed.
- A successful response identifies coverage and applicability, not an approval.
- Multiple clients can retrieve the same immutable briefing without modifying it.
- Missing sources, unsupported schema versions, and unavailable transports have
  explicit errors. Native policies and permissions remain in force.

**Offline verification:** stdio request/response fixtures and temporary CLI
subprocesses invoking only the new local adapters, with mocked core results where
appropriate. Include adversarial path requests, duplicate request IDs, oversized
messages, and unexpected tool names. Proposed verify commands:

```bash
python3 -B tests/test_context_travel_cli.py -v
python3 -B tests/test_context_travel_mcp.py -v
```

**Non-goals:** installed-client probes, real connector authentication, remote
hosting, background daemons, provider mutations, and automatic tool installation.
A remote service requires a separate deployment and access design.

**Completion gate:** protocol and shared-core conformance pass offline. Disable
the adapter if it widens access or diverges from the core; preserve portable
briefing artifacts and the existing standalone workflows.

### CT5 — Integrate existing skills across the six surfaces

**Objective:** make context travel discoverable and usable through existing
Polytropos workflows on every requested surface, preserving native behavior.

**Dependencies:** CT1–CT4. Worker intent: mid; strong review for policy or
installation-boundary changes. Exact existing skill/agent/package paths must be
resolved before implementation. Expected scope includes native Claude skills,
Codex skills, Copilot agent/skill definitions, packaging, compatibility records,
and dedicated temporary-installation fixture tests.

**Surface matrix:** Codex desktop, Codex CLI, Claude Desktop, Claude Code CLI,
GitHub Copilot desktop app, and GitHub Copilot CLI. Claude Desktop chat and Code
mode remain separate entries where capabilities differ. Version, operating
system, local/remote execution mode, and organization policy are part of each
capability record.

**Acceptance:**

- Architect can request bounded context and contribute explicit plan/criteria
  references; route can use task scope while retaining central policy and each
  harness's own pricing source.
- Execute, verification, assessment, and recovery use the appropriate briefing
  without acquiring new authority from it.
- Existing entry points still work without an index under their existing rules.
  Optional context absence does not silently disable mandatory verification.
- Skills load detailed context on demand; no full graph or transcript is added to
  resident instructions.
- Surface-specific wrappers do not duplicate the parser, lifecycle join, routing
  logic, or pricing. No hardcoded provider/model prices or account limits appear.
- Packaging is reversible and never overwrites a differing user-owned file.
- Capability records distinguish documented support, implementation, and actual
  installed-client evidence; one surface's passing test does not certify another.

**Offline verification:** synthetic client capability records, package discovery
fixtures, temporary homes only, no-clobber cases, missing transport cases, and
cross-surface briefing round trips. The test executable(s) must fail if absent;
do not accept a discovery command that silently runs zero tests.

**Later installed-surface gate:** separately authorized, bounded probes must show
discovery, retrieval, source explanation, freshness rejection, permissions, and
handoff in each actual client. Those probes may involve client usage and require
an explicit resource ceiling. They are not authorized in this CT1 run.

**Non-goals:** upgrading/installing clients, modifying personal configuration in
tests, changing billing/settings, reproducing native agent loops, or declaring
desktop parity based solely on CLI evidence.

**Completion gate:** offline packaging and compatibility checks pass for all six
targets. The release report retains unverified installed modes until their own
evidence exists. A failed wrapper is disabled independently of the shared core.

### CT6 — Evaluate cost, quality, and handoff effectiveness independently

**Objective:** establish whether context travel improves correct task completion
and resource use compared with ordinary discovery and a static briefing.

**Dependencies:** CT1–CT5 for integrated evaluation; fixture/oracle design begins
earlier so implementation cannot define its own success after seeing results.
Worker intent: strong independent verification. Proposed scope is a bounded
evaluation module, fixture corpus, report schema, and tests; reuse existing
attempt-history and scorecard semantics where applicable.

**Arms:** existing workflow, conventional static briefing, maintained context
travel. Match task, criteria, assurance, allowed sources, and resource ceilings.
Group related variants to prevent leakage; separate calibration from held-out
evaluation. Independent labels identify necessary context and correct outcomes.

**Cohorts:** single repositories with and without kit/graph/evidence artifacts;
linked producer/consumer repositories; monorepos with narrow and wide impact;
provider adapters with different capabilities; all six surfaces and their
supported modes; interrupted, stale, contradictory, or budget-limited handoffs.

**Measures:** read counts and bytes, retrieval calls, briefing size, cold/warm
latency, refresh/storage cost, context omissions, evidence-link accuracy,
false-ready and unnecessary-block outcomes, task completion, retries, human
intervention, and later escaped defects/outcome achievement. Report raw counts,
denominators, exclusions, and unknown telemetry for every cohort.

**Cost accounting:** include unsuccessful attempts and index maintenance in
resources per independently accepted outcome. Separate actual API charges,
provider credits, CI resources, human time, and subscription burn proxies. Derive
estimates from the applicable pricing data at evaluation time with provenance.
Do not infer actual provider billing or cache hits from a local content-cache hit.
Zero accepted outcomes makes cost per accepted outcome undefined.

**Offline verification:** synthetic repositories, supplied provider/client records,
fixed labels, stubs, deterministic replay, and instrumentation checks. Offline
replay can establish invariants and measured local resource use; it cannot
establish live agent quality or provider savings. Exact test commands are pinned
when the evaluation module is admitted, before any run.

**Later live evaluation:** separately authorized cohorts, explicit budgets and
stop conditions, unchanged acceptance requirements, and independently adjudicated
results. No live experiment starts merely because an offline report passes.

**Promotion/no-promotion gate:** mandatory unauthorized-read/action, stale-evidence,
and false-readiness fixtures must pass. Compare efficiency only at matched quality.
If benefit is absent, regressions appear, or sample size is insufficient, report
that result and keep the feature advisory or disabled. Preserve evidence when
rolling back an adapter or configuration. Never claim that stopping an automation
undoes external actions already performed.

### Execution and approval boundaries for the complete task set

- Only CT1 is implemented in this change; its actual verification is recorded below.
- CT2–CT6 require their own implementation admission and scoped task entries before
  execution. Their briefs here are planning output requested by the user.
- Every implemented task uses temporary fixtures/stubs first and preserves the
  existing task, execution, evidence, permission, and pricing authorities.
- Local data-contract or adapter success does not authorize installations, paid
  runs, remote writes, PRs/MRs, merges, or deployments.
- Later lifecycle phases will receive separate execution tasks. No CT7+ task IDs
  or implied deployment authorization are invented by this Phase 1 report.

## Surface and hosting requirements

All six requested surfaces are explicit targets:

| Surface | Intended access | CT1 compatibility evidence |
| --- | --- | --- |
| Codex desktop | Native skills plus read-only context tools | Not exercised |
| Codex CLI | Native skills, CLI queries, MCP | Not exercised |
| Claude Desktop | Code-mode plugin; MCP briefings for chat | Not exercised; modes must be tracked separately |
| Claude Code CLI | Existing plugin, CLI queries, MCP | Not exercised |
| GitHub Copilot desktop | Skills/custom agents and MCP | Not exercised |
| GitHub Copilot CLI | Existing agent workflows, CLI queries, MCP | Not exercised |

One shared core owns data semantics. Surface adapters preserve native discovery,
permissions, model control, and billing. Product support, repository
implementation, and dated installed-client verification remain separate facts.
Offline adapter checks and installed-surface checks are separate completion gates.
Remote sessions need an authorized endpoint or eligible portable bundle to reach
context stored on another machine.

Hosting support is a different axis: GitHub, GitLab, Bitbucket, Azure DevOps, and
plain Git. Enabled native integrations should own their supported operations,
with one execution owner and results returned to the shared evidence view.
Unsupported, disabled, unavailable, and unknown capabilities remain distinct.
Cloud and self-hosted editions require their own conformance evidence. A native
policy rejection must not trigger a permission-bypassing fallback.

## Preserving existing Polytropos skills

- Architect remains responsible for decomposition, decisions, acceptance criteria,
  and task briefs. It will consume relevant maintained context and contribute its
  outputs to the view.
- Route, effort, and frontier-check retain central selection and harness-specific
  pricing. Briefings supply bounded task information; they do not select a model
  or grant a budget.
- Graphify remains an optional external mapping tool. No extraction or install
  is part of CT1.
- Execute and escalate retain execution, verification, and recovery boundaries.
- Memory and context-weight remain relevance and context-budget tools.
- Assessment, usage, and journal workflows can consume connected evidence later.

Existing entry points remain supported. Shared task semantics are not copied
into the new layer. Context is retrieved on demand rather than bulk-loaded into
resident instructions. Index absence needs an explicit fallback under existing
policy. No skill is installed or modified by CT1.

## CT1 implementation

The new `bin/context_travel.py` library defines
`polytropos.context-travel/1`. It accepts caller-supplied data only.

Public operations:

- `make_task_identity`: canonical JSON tuple of explicit repository ID, relative
  kit path, and unchanged task ID, identified by SHA-256.
- `make_request` / `parse_request`: bounded request with assignment, applicability,
  input references, and validated request digest.
- `make_briefing` / `parse_briefing`: correlated briefing, bounded redacted text,
  ordered criteria/evidence, explicit provenance, and validated content digest.
- `canonical_bytes` / `content_sha`: deterministic encoding and content identity.

Repository identity is never inferred from a directory or remote. Checkout and
revision changes affect applicability without rewriting stable task identity.
`source_state_ref` can distinguish dirty source states sharing the same HEAD;
null means that source-state applicability is unknown. Assignment role/question
and supplied acceptance/source references participate in the request digest.

Every request field is echoed and compared by the briefing parser. Machine
identifiers are preserved or rejected, never silently rewritten. Unknown
references and their missing digest/version parts stay null. Provenance uses
the shape and constructor owned by `attempt_ledger`.

Canonical encoding sorts dictionary keys, preserves meaningful list order, and
rejects nonfinite/non-JSON input. The schema rejects unknown fields/versions,
duplicate JSON keys, excessive nesting and size, unsafe kit paths, mismatched
identities, and changed content under an old digest. Criteria that exceed bounds
are refused rather than truncated. Free text uses the existing redaction engine
and carries counts by kind. Echoed mutable request values are copied so a returned
briefing cannot mutate its caller's request.

Freshness is explicitly declared metadata. Validation does not prove truth,
freshness, authorship, authorization, or acceptance. A content hash is not a
signature. The initial schema represents task briefings; general lifecycle
queries and partial-response forms are not implemented here.

### Files

- `bin/context_travel.py`: new pure contract library.
- `tests/test_context_travel.py`: synthetic contract and negative tests.
- `docs/CONTEXT-TRAVEL.md`: human-facing contract and limitations reference.
- `bin/release_gate.py`: register the version from its owning module.
- `docs/RELEASE.md` and generated documentation: regenerated by their engines.
- `mkdocs.yml` and three documentation-integrity tests: navigation for the added
  page and the corresponding pinned page-count tripwires.
- `tasks/kits/context-travel/`: plan, task, guardrails, evidence notes, and this
  requested report.

## CT2 implementation

`bin/context_readers.py` provides the keyword-only `read_sources` API and the
`polytropos.context-sources/1` observation format. The caller supplies repository
IDs and absolute roots, selects a supported relative kit and known kit filenames,
and optionally selects a graph and explicit evidence-file binding. It performs
no repository walk, Git probe, implicit store resolution or source-file traversal
from graph nodes. An existing graph is used only as a selected artifact.

The output separates selected source outcomes from optional sources not selected,
which appear in `coverage.absent`. Missing, forbidden, corrupt, inconsistent,
over-limit and unavailable states remain distinct. References identify the bytes
read; bounded redacted observations do not confer authority. Graph nodes and edges
with ineligible paths are omitted with counts and incomplete coverage disclosed.
The reader does not join records to tasks or reconstruct acceptance history.

The additive stable reader uses nofollow traversal through absolute-root and
relative-path components, refuses non-regular and multiply linked files, and
performs at most two byte-bounded passes with descriptor/path checks. Actual data
bytes consumed before failure remain charged. `opened` counts selected-leaf opens,
not directory descriptors or every metadata operation. The counters do not measure
total machine cost, OS-cache hits or model savings.

Each source's semantic freshness remains unknown/not-assessed. A separate
`consistency` value can record a stable read. This neither establishes a multi-file
transaction nor proves that a caller-declared evidence binding is historically
correct. Legacy missing provenance remains unknown. New strict parser options
reject malformed JSON while preserving existing callers' tolerant defaults.

The independent test author contributed 28 reader tests and 12 stable-path tests.
Held-out review exposed and drove fixes for hardlinks, I/O-error classification,
malformed graph containers, noncanonical deny prefixes and invalid configuration
types. [CT2-EVIDENCE.md](CT2-EVIDENCE.md) retains the failing and passing observations,
exact commands, source digests, environment limits and final integration result.
The full suite passed 6,529 tests with two configuration-dependent skips; CT2 is
marked done. No CT2 test was skipped, and recorded source digests matched afterward.

## CT3 implementation

`bin/lifecycle_view.py` now implements the pure versioned projection, strict
parser, canonical encoding and comparison API. It consumes explicit in-memory
CT1 requests and CT2 observations, echoes the assignment and applicability, and
returns source-linked findings, typed relationships, a role briefing, limitations
and content identity. It performs no source reads or dispatch. The release
inventory and generated contract reference include its version.

The four roles retain the same facts and mandatory criteria while ordering their
focus differently. Critical limitations are copied into each brief as complete
objects. Exported free text is redacted without trimming criteria; source and
additional output redaction counts remain visible. Oversized output refuses,
including when a minimal refusal cannot fit the requested ceiling. This is
bounded selection and presentation, not measured context or model-cost savings.

Legacy same-task-ID events remain unbound. Subject-matched records still require
an earlier failing non-tautological precheck in the corresponding passing run
before the view can describe that recorded baseline. Semantic adequacy remains
explicitly unknown. Current acceptance references are declarations, compared
separately from observed criterion text. Unknown notes outcome labels are not
invented failures; existing `pass`, `escalated-pass` and `blocked` meanings are
preserved. A standalone lexical task-path extractor is omitted from this version;
graph edges remain navigation over supplied observations.

Independent tests and review found and corrected false legacy-event joins,
cross-run and reverse-order precheck matches, incomplete nested validation,
hidden missing criteria, missing comparison/graph facts, and notes-vocabulary
misclassification. The tests also caught two fixture problems: a source item
limit smaller than a parsed task, and a noncanonical negative-outcome label.
Production authorities were not broadened to fit those fixtures.

The coordinator's final targeted run passed **39 tests**; the context regression
selection passed **202 tests**. Independent held-out review and both documentation
mirror checks passed. The full suite passed **6,568 tests in 614.587 seconds**, with
two configuration-dependent skips and no failures or errors. Its wrapper exited
0 after 621.040 seconds with no timeout, truncation or leftover processes.
[CT3-EVIDENCE.md](CT3-EVIDENCE.md) contains commands, retained log labels,
corrections, reviewed source hashes and the final acceptance status.

## CT4 implementation

The shared query/config boundary and CLI/MCP adapters passed their offline
acceptance gates. They expose overview, brief, explain, changes
and capabilities over explicit startup bindings. A first-call structured
assignment uses CT1's request builder; presealed requests and imported CT3
artifacts remain supported. Artifact-only operations reuse validated content
without a source scan or server-side historical store.

Configuration and query fields, paths, identities, ceilings and authorized
subjects are validated before permitted reads. JSON/text preserves mandatory
criteria and critical caveats or refuses. The core envelope has its configured
size ceiling; transport framing has a separate hard ceiling. The MCP session
implements the pinned stdio lifecycle and bounded synchronous tools, with honest
limits on cancellation and unused client capabilities. CLI/MCP startup help
requires no config read. Source errors produce bounded correlated tool errors.

The coordinator and independent verifier each passed **48 targeted tests**:
18 query, 9 CLI and 21 MCP. These include actual local script entry points with
temporary config/homes/stores, plus protocol fixtures. Held-out probes covered
parity, assignment sealing, source/import authorization, artifact-only no-I/O,
path/ID hygiene, lifecycle/framing and error handling. Both documentation
generators and the release inventory have been rebuilt and checked. No installed
client or provider has been tested, and no savings claim is made.

The first CT4 full run executed 6,616 tests with eight errors and two skips. All
errors came from the recreated harness blocking a synthetic loopback listener in
existing execution-boundary tests. A separate corrected harness passed all 59
affected-module checks; it allows numeric loopback fixtures while denying external
network access. The full rerun passed **6,616 tests in 628.690 seconds**, with
two skips and no failures or errors, using unchanged product/test files. Its
wrapper exited 0 after 635.934 seconds without timeout, truncation or leftovers.
The failed run remains recorded separately and is not counted as acceptance.

[CT4-EVIDENCE.md](CT4-EVIDENCE.md) records the absent-module and assignment-form
baselines, corrected protocol/path/error defects, fixture corrections, exact
commands and frozen hashes. The previous temporary CT1–CT3 log directory has
expired; committed summaries/digests remain, and the new CT4 logs are also
temporary. Public synchronization follows the full-suite gate and must preserve
exact tracked content across both repositories.

## Local public synchronization

After CT4, the reviewed tracked delta was applied to a separate public worktree
from the known local common base. It contains the same source, tests, skills,
templates, docs and workflow definitions. The private sync job already has a
repository gate, so no public-only source exception is needed. A new anonymous
content-only commit avoids transferring identifying private commit history.

The candidate passed **250 context tests**, the release check and both generated
documentation checks with separate temporary fixtures and stubbed clients. The
6,616-test full suite is evidence from the identical frozen runtime/tests in the
private workspace; it was not rerun in public. Later edits only record completion
and parity. [PUBLIC-PARITY.md](PUBLIC-PARITY.md) records commands, exact scope,
content review and remaining release gates. The final local handoff records both
candidate commits and the shared Git tree identity.

The original public checkout acquired concurrent documentation work during CT4;
it was left separate and must be reconciled before a future publication. Source
parity is established between the reviewed candidate revisions, not every active
checkout. No remote was fetched or changed, and no plugin was installed.

## CT1 verification approach and evidence

All verification uses Python stdlib and synthetic inputs. No dependencies were
installed. The primary checkout is not the verification workspace.

Temporary verification support lives at:

`/private/tmp/poly-auto-ct1-checks-_u_zf8ux`

Its runner invokes the repository process runner with a temporary HOME, data and
config roots, a reduced environment, external-client stubs, bounded execution,
and retained logs. A Python audit guard refuses networking. Integration builds
and the first full-suite attempt additionally ran under a Seatbelt profile denying network,
reads of real harness homes, and writes under the user's home except the isolated
worktree. The worktree itself is file isolation, not a security boundary.

That enclosing profile prevented existing tests from creating their own Seatbelt
verification sandboxes. The corrected suite runs without a nested outer profile,
retaining temporary homes/stores, credential-free environment, client stubs and
the Python network guard; verification commands use the repository's own execution
boundary. This does not claim whole-process OS confinement for the corrected test
parent. Analyzer discovery uses non-executing `node` and `uv` stubs; neither a
runtime nor an installer was installed or invoked.

Personal home-directory paths are intentionally omitted from committed records.
The app's final handoff links directly to the local report and implementation.

### Commands and results

| Check | Observed result |
| --- | --- |
| Targeted missing-module baseline | Implementer recorded expected failure before library creation |
| Targeted unittest discovery for `test_context_travel.py` | 9 tests passed |
| Independent targeted discovery in isolated environment | 9 tests passed; no concrete review defect found |
| Static kit parsing/graph validation with explicit repository root | Passed; no graph or analysis findings |
| `python3 -B bin/release_gate.py build` | Passed in network-denying sandbox |
| `python3 -B bin/docs_build.py build` | Passed; 3 written, 97 unchanged |
| `python3 -B bin/copilot_docs.py build` | Passed; 20 artifacts regenerated |
| First full-suite attempt | 6,489 tests; 13 failures, 38 errors, 25 skips; retained as failed evidence |
| Documentation integration correction | 374 docs tests and 16 primitives-doc tests passed |
| Role-contract control without nested outer sandbox | 27 passed |
| Analyzer control with discovery-only PATH stubs | 123 passed |
| Corrected full-suite run | 6,489 tests in 645.782 seconds; exit 0, no failures/errors, 2 skips |
| Final documentation/release checks | Passed; no release findings, both documentation mirrors current |

The exact corrected full-suite wrapper command was:

```bash
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct1-checks-_u_zf8ux/run.py full-suite-final -m unittest discover -s tests -v
```

It invoked Python 3.12's `-B -m unittest discover -s tests -v` in the isolated
worktree and completed in 651.681 seconds with no timeout, truncated output, or
leftover processes. The two skips are configuration-dependent: no agent currently
carries an excluded configured pin, and no frontier pin is recorded. CT1 tests
were not skipped. Retained results are `full-suite-final.log` and
`full-suite-final.json` beside the temporary runner. Reviewed source digests are
recorded in NOTES.md. Task completion records this observed work, without creating
an execution-driver acceptance event or reconstructing an attempt ledger.

The implementation review found and corrected a real sibling-import issue:
loading the new module by file path originally required adding `bin/` to
`sys.path`. It now follows the repository's sibling-loader pattern; tests no
longer mutate global `sys.path`.

The first full suite also found six documentation assertions requiring the new
page's navigation and census updates, three PATH-dependent analyzer assertions,
and 42 failures/errors in driver fixtures unable to create nested Seatbelt
sandboxes. Documentation assertions were updated to the actual source/page counts
without weakening the tripwires. Targeted controls confirmed the harness remedies.
Product execution and verification policies were not relaxed or changed.

The first generation attempts could not write into the app-created worktree
under the initial shell sandbox. Retrying with scoped access and a network-denying
sandbox succeeded. No generator was bypassed or replaced by hand editing.

The static kit CLI initially inferred the wrong repository root for the native
kit layout. Calling the existing analyzer with its explicit `repo_root` seam
produced no findings. Correcting that general root inference is outside CT1.

## Cost and quality measurement plan

The offline routing preview selected the configured strong worker under central
Codex policy. It is an assignment preview, not proof of observed model identity
or measured usage. Pricing was read from `data/pricing.codex.json`; no provider
call was made by that preview. Subscription figures are usage/burn proxies, never
actual token bills. No actual usage or savings baseline was measured here.

Compare three arms later: existing discovery, a conventional static briefing,
and maintained context travel. Keep tasks, acceptance, assurance, and resource
ceilings comparable. Separate cold indexing, warm retrieval, and refresh cost.
Independent labels and held-out task variants are required before claiming
quality or causal gains.

| Dimension | Measures |
| --- | --- |
| Context | Files/bytes reread, retrieval calls, briefing size, eligible cache reuse, fallback frequency |
| Quality | Missed requirements, wrong evidence links, stale context, false readiness, unnecessary blocking |
| Flow | Queue versus active time per stage, repeated reviews, human intervention |
| Resources | Model usage, retries, CI/compute, indexing/storage, provider usage, human effort |
| Outcomes | Independently accepted work, escaped regressions, deployment recovery, intended user outcome |
| Integrity | Sample sizes, exclusions, missing telemetry, unverified capabilities, synthetic versus live scope |

Include failed attempts and maintenance in resources per accepted outcome. If
there are no accepted outcomes, that ratio is undefined. Keep provider credits,
API money, subscription burn proxies, CI resources, and human time separate.
Timing/usage telemetry does not enter canonical briefing identity.

Evaluation cohorts must include single repos with missing artifacts, linked
producer/consumer repos, monorepos with local and broad-impact changes, provider
capability differences, and interrupted or stale cross-surface handoffs.
Forbidden actions, unauthorized reads, and false-ready results in mandatory
negative fixtures block promotion within the tested scope. Small samples remain
insufficient evidence for broad reliability claims.

## Remaining limits and next boundary

CT1 provides the portable data contract; CT2 adds selected-source observations;
CT3 composes the read-only lifecycle view and role briefings entirely in memory;
CT4 exposes these through bounded CLI/MCP adapters. All four have passed their
offline gates. They do not provide a maintained repository index, graph refresh,
skill wiring, provider
integration, automation, repair, merge, deployment or verified six-surface
compatibility. The earlier driver precheck and acceptance-drift gaps remain
unchanged. No cost saving or reliability rate has been measured by these tests.

CT4 is complete in the original order chosen by the user. CT5 adds surface
integration, and CT6 the independent cost/quality comparison. The provider and
incremental-scaling phases remain later milestones. Existing architect, routing
and execution authorities remain in place.

Every CT and later lifecycle phase must also pass the public/private parity gate.
The prepared local public candidate has the same tracked content and reviewed
anonymous metadata, preserving the current public checkout. Repository
settings/visibility and enabled Copilot capabilities are distinct from source
parity. No published availability is claimed until the separate release occurs.

[CRITIQUE-RECONCILIATION.md](CRITIQUE-RECONCILIATION.md) retains the reviewed pilot
alternative and useful corrections. The alternate phase order was not adopted.
Its render and evaluation API findings remain requirements for the later affected
tasks, not claims that their implementations have been fixed or tested already.
