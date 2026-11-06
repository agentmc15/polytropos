# Context travel tasks

## Phase 1 — Contract foundation

### CT1 — Define the context travel contract and identities
- status: done
- model: strong
- depends: (none)
- evidence: red-green

**Brief.** Implement `bin/context_travel.py` as a stdlib-only pure data library,
with offline tests in `tests/test_context_travel.py` and a human-facing contract
reference in `docs/CONTEXT-TRAVEL.md`. Read this kit's PLAN.md and GUARDRAILS.md.
Define versioned, strict request and briefing shapes; explicit repository and
checkout identity; namespaced task identity preserving the original task ID;
bounded evidence/source references; deterministic canonical bytes and SHA-256
references; and request/response correlation. Reuse the existing provenance
reference authority. Validation never evaluates readiness or executes verify
commands. Document limitations and the difference between declared metadata and
demonstrated properties. Register the new contract version with the release gate
and regenerate affected documentation through its generators.

**Acceptance.**
- Identical semantic objects with different dictionary insertion order produce
  identical canonical bytes and references; ordered lists remain ordered.
- Different repository IDs or kit paths cannot share a task identity; original
  task IDs are never normalized or rewritten. Checkout/revision changes affect
  applicability without rewriting stable task identity.
- Missing provenance is explicit and not backfilled. Request/response subject,
  assignment, revision and digest mismatches are refused.
- Unknown schema versions/fields, duplicate JSON keys, non-JSON/nonfinite values,
  unsafe relative paths, traversal, and oversized payloads fail explicitly.
- Mandatory criteria are never silently truncated. Text uses the existing
  redaction engine and reports counts; identifiers are never silently redacted.
- Contract code performs no repository/store reads, writes, subprocesses,
  network calls, clock access, installations, or provider/harness probes.
- Verification is offline, synthetic, and independent of the user's stores.

**Verify.**
```bash
python3 -B -m unittest discover -s tests -p 'test_context_travel.py' -v
```

### CT2 — Read explicit sources through a bounded privacy boundary
- status: done
- model: strong
- depends: CT1
- evidence: red-green

**Brief.** Create `bin/context_readers.py` as a stdlib-only read-only observation
library; create independent tests in `tests/test_context_readers.py` and
`tests/test_safe_paths_context.py`. Add only these shared seams: an additive
`confined_read_stable_bytes` helper in `bin/safe_paths.py`; a pure
`parse_graph_bytes` extracted from `bin/graph_brief.py`; and a pure `parse_events`
extracted from `bin/attempt_ledger.py`. Preserve old reader behavior. Update
`docs/CONTEXT-TRAVEL.md` and the narrow boundary statement in `SECURITY.md` as needed.
The coordinator owns version registration in `bin/release_gate.py`, generated
documentation, this kit and acceptance. CT1 source/tests/schema remain unchanged.

The public entry point is keyword-only `read_sources(repository_bindings,
repository_id, kit_path, kit_files=("TASKS.md",), graph_path=None,
evidence_bindings=None, deny_prefixes=(), limits=None)`. Repository bindings map
explicit IDs to explicit absolute roots. Kit and graph paths are canonical
repository-relative paths. Selected kit filenames are an ordered subset of
PLAN.md, TASKS.md, GUARDRAILS.md and NOTES.md. Evidence bindings map the exact
`(repository_id, kit_path)` to an explicit root and `events_rel` filename. No
default store, inferred root/identity, enumeration, graph traversal into source
files, Git probe or environment lookup. An omitted source is explicitly absent.

Return the version "polytropos.context-sources/1" with subject, ordered selected-source
observations, read accounting, limits and coverage. Omitted graph/evidence sources
are explicitly listed in `coverage.absent`; selected source states distinguish ok,
missing, forbidden, corrupt, inconsistent, over-limit and unavailable. Each source
has a nullable reference, bounded redacted observed facts with redaction counts,
coverage, privacy-safe reason code and separate freshness/consistency metadata.
`freshness` remains unknown/not-assessed; `consistency` can be consistent-at-read
after the stable helper succeeds. Preserve unknown legacy applicability. A consistent file read does
not establish a cross-file snapshot, current graph, accepted work or permission.

The stable read helper returns bytes plus actual bytes_read/opened counts or
raises `SourceReadError` carrying the same accounting and a closed reason code.
Use nofollow directory-relative descent including absolute-root ancestors,
nonblocking regular-file reads, at most two bounded reads, descriptor pre/post
metadata and final nofollow path identity checks. The per-source limit bounds
payload size; the aggregate read budget includes both reads and failed attempts.
Never read max+1 beyond an actual byte budget. Reject unsupported containment
instead of falling back to unchecked paths. Selection count bounds attempts;
not-selected sources do not consume it. Invalid configuration fails explicitly.

Reuse kit_contract's returned task/acceptance facts, graph parsing, ledger event
parsing/provenance and the existing privacy/redaction authorities. Do not add
readiness, evidence joins, new task parsing, implicit historical binding or store
writes. Do not call existing path-loading readers and filter their output later.
Refuse over-limit mandatory data instead of trimming criteria or hiding coverage.

**Acceptance.**
- Both kit layouts and identical kit/task names in distinct roots preserve their
  explicit subjects. Ambiguous or unmatched evidence bindings cannot silently
  attach another subject's history. Missing provenance remains unknown.
- Caller-denied, credential-shaped, traversing, noncanonical, out-of-root and
  symlink paths are refused before content reads. The new helper conservatively
  refuses multiply linked files before content reads. Special files cannot block.
  Forbidden paths/values do not appear in diagnostics.
- Graph-present and graph-absent fixtures prove no implicit freshness-source or
  fallback scan occurs; a selected graph never authorizes reads of its targets.
- Actual opened/read-byte counters include partial failures and rereads. Fixed
  limit ceilings and aggregate remaining budget stop further reads and disclose
  incompleteness. Exact-bound stable files can succeed without a max+1 probe.
- Changes during a selected read return inconsistent/unknown or bounded refusal.
  A multi-file transaction or protection against an adversary restoring all
  observations is not claimed.
- Malformed, nonfinite, duplicate-key, excessive-depth, oversized and over-item
  inputs are refused safely. Free text is redacted with counts, machine identities
  are never silently rewritten, and required task criteria are not truncated.
- Runtime reads perform no writes, processes, Git, network, clock, home/store
  resolution, installation, dispatch or readiness/acceptance mutation.
- Existing safe-path, graph-parser and ledger tests pass without weakening their
  assertions; independent negative verification and the full suite pass.

**Verify.**
```bash
python3 -B -m unittest discover -s tests -p 'test_context_readers.py' -v && python3 -B -m unittest discover -s tests -p 'test_safe_paths_context.py' -v
```

### CT3 — Compose the read-only lifecycle view and role briefings
- status: done
- model: strong
- depends: CT1, CT2
- evidence: red-green

**Brief.** Create `bin/lifecycle_view.py` as a stdlib-only pure projection library,
and independent tests in `tests/test_lifecycle_view.py`. Update
`docs/CONTEXT-TRAVEL.md`. The coordinator owns release registration, generated
documentation and kit evidence. No changes to CT1, CT2 or existing authority
engines are admitted without first reporting a concrete blocking gap.

The library owns the version "polytropos.lifecycle-view/1" and exposes
`compose_view(request, sources, role=..., intent_links=(), acceptance_links=(),
dependency_freshness=(), max_bytes=32768)` with keyword-only options,
`compare_views(before, after, max_bytes=32768)` with keyword-only budget,
canonical encoding and a strict view parser. Malformed input, unknown fields or
versions, inconsistent request/subject/digest and invalid configuration raise a
closed `ViewError(ValueError)`. Bounded output overflow yields a refused view
with a null brief; if the minimal refusal cannot fit, raise ViewError. No output
may exceed its ceiling.

Validate the CT1 request using its authority; require the CT2 observation version
and exact repository/kit subject. Echo the full request, including checkout,
revision and source-state declaration. Validate CT2 input structure and bounded
values, including read counters, but omit operational counters from substantive
output and content identity. The four supported roles are architect, implementer,
verifier and reviewer; role must match request.assignment_role.

A projection contains version, kind, complete/partial/refused status, request,
subject, overview, brief, findings, relationships, limitations and content_sha.
Overview projects recorded task title/status and source coverage. The role brief
contains role, summary, lossless mandatory acceptance text when present, selected
finding IDs and full critical limitations. It is a lifecycle-view fragment, not
a context-travel task briefing; missing task/criteria can therefore be represented
honestly without inventing a CT1 requirement. A missing task/acceptance produces
a partial view with explicit limitations. Complete never means accepted or ready.

Findings carry stable IDs, kind, claim, epistemic classification, applicability,
source references/selectors and criticality. Any missing source reference requires
an explicit missing-basis code. The findings are the explanation trace; every
material conclusion has a basis or is explicitly uncertain. Relationships use
only declared-dependency, code-navigation, task-path-mention, measured-verification
and recorded-outcome types. A path mention or graph edge is not ownership, an
execution dependency or permission. All imported text remains attributed data.

Optional links are bounded caller-declared records with exact repository, kit
and task subject, reference and epistemic label. Intent kinds are goal,
requirement or outcome. At most one current acceptance link is supplied for the
requested task. Dependency declarations name actual declared dependencies and
fresh/stale/unknown state; fresh or stale requires a reference. Mismatched or
duplicate links fail explicitly. Do not infer historical evidence binding from
a matching task ID, compute original acceptance identity from redacted text,
or implement a second freshness/readiness engine. Existing pure kit helpers may
project task structure and recognized outcome records; no store or policy calls.

Comparisons validate both projection schemas and digests, require the same stable
repository/kit/task identity, and separately report applicability changes and
observed task/criteria/reference/finding/limitation changes. Missing observations
do not prove removal of requirements. A changed source-byte digest does not by
itself prove acceptance drift. Comparison output also has its own content digest.

**Acceptance.**
- Deterministic equivalent inputs yield equivalent substantive bytes/digests;
  read counters do not affect them. Echoed mutable data cannot mutate its input.
- Role views share facts and source links, select role-relevant focus, and carry
  every mandatory criterion and unresolved critical limitation. A small budget
  causes explicit refusal, never hidden omission or an oversized response.
- Missing, unselected, corrupt and incomplete sources remain distinguishable.
  No task, criterion, provenance reference or acceptance record is manufactured.
- Same task IDs in different repos/kits cannot join. Legacy events without
  intrinsic repository/kit binding remain visibly unbound even when IDs match.
- Contradictory status, recognized notes outcomes and ledger claims stay visible
  with their bases and scope limits. A done task or passing check cannot establish
  meaningful precheck, independent verification, validation or merge readiness.
- Acceptance-only changes, missing/tautological precheck and declared stale
  dependencies produce appropriate warnings/unknowns using only comparable
  supplied evidence. The underlying precheck/drift driver gaps are not fixed.
- Unknown/nonfinite/deep/oversized inputs and mutated view hashes are refused.
  Machine identities are preserved or rejected; free text uses redaction.
- Operation-time tests prove no filesystem, store, process, network, clock,
  environment, Git, dispatch or mutation seam is called.
- Independent negative verification, existing contract regressions, generated
  documentation checks and the full suite pass before completion.

**Verify.**
```bash
python3 -B -m unittest discover -s tests -p 'test_lifecycle_view.py' -v
```

### CT4 — Expose the shared lifecycle queries through CLI and MCP
- status: done
- model: strong
- depends: CT1, CT2, CT3
- evidence: red-green

**Brief.** Add `bin/context_travel_query.py`, `bin/context_travel_cli.py` and
`bin/context_travel_mcp.py`. The implementer also owns `docs/CONTEXT-TRAVEL.md`.
Independent tests live in `tests/test_context_travel_query.py`,
`tests/test_context_travel_cli.py` and `tests/test_context_travel_mcp.py`.
The coordinator owns kit/evidence, release registration and generated docs.
CT1–CT3 and existing authority engines are unchanged unless a concrete blocker
is first reported. Stdlib only; no installation or live client/provider probing.

The shared core owns versions "polytropos.context-query-config/1" and
"polytropos.context-query/1". Startup config has exact fields v, repositories,
deny_prefixes, limits and max_output_bytes. Repositories contain id, absolute
root and bounded kits; each kit contains canonical path, selected kit_files,
nullable graph_path and nullable evidence with explicit root/events_rel. Reject
duplicate/ambiguous bindings, unsafe paths, invalid limits and unknown fields.
Config payload is capped at 16 KiB, its stable physical read at 32 KiB. Load it
only from an explicit absolute startup path through the existing confined reader.
No default config, root inference, directory scan, home or environment lookup.

`run_query(config, operation, args)` returns a deterministic envelope with v,
operation and data. `overview` and `brief` accept a CT1 request, a structured
assignment, or exclusively a supplied CT3 view. Request/assignment forms can
include optional intent/acceptance/dependency declarations. An assignment has
required repository_id, checkout_id, revision, kit_path, task_id, assignment_id,
assignment_role and plain-text question, plus optional source_state_ref,
source_ref and acceptance_ref. Use CT1's existing make_request authority to seal
it; never require a desktop caller to compute a digest or infer missing identity.
Mixed forms and unknown fields refuse before reads. Live requests use only the
exact configured sources through CT2 and
compose through CT3. Imported views preserve the original validated artifact
without reads. `explain` accepts a supplied view and nullable finding_id, returns
the selected findings, source bases, full mandatory criteria and all critical
limitations with subject/view identity. `changes` compares supplied before/after
projections through CT3. `capabilities` accepts an empty object and returns only
supported operations/versions/bounds and honest unverified-client limitations.
All operations and imported artifact subjects must match authorized repo/kit
bindings. Query text never selects or overrides roots, files, graph/evidence
locations, deny rules or read limits. Validate invalid requests before reads.

The config's max_output_bytes is 1,024–32,768 bytes and bounds the complete core
result. Bounded text rendering preserves all mandatory criteria and critical
caveats or refuses; no unannounced slicing. Imported artifacts and comparisons
are bounded and validated before use, including their nested schema and digest.
No new readiness, acceptance, freshness, identity or provenance authority.
Same supplied immutable artifact can travel between clients without changing its
content identity; this server does not persist or retrieve historical snapshots.

CLI accepts an explicit `--config`, one operation, optional JSON/text format,
and bounded JSON arguments on stdin. MCP accepts only the explicit startup
config and uses the published 2025-11-25 stdio protocol: UTF-8 newline-delimited
JSON-RPC, initialize/version negotiation, initialized gate, ping, tools/list and
tools/call. No HTTP, arbitrary shell endpoint, mutation, roots, sampling or
resource reads. Tool result text serializes the same core JSON as the CLI.
Requests and responses have separate hard frame ceilings of 128 KiB; session
work and used IDs are capped at 256 frames. IDs are bounded strings or integers,
never bool/null, and cannot be reused. Invalid/oversized frames, duplicates,
unknown methods/tools, and startup failures have deterministic bounded errors
without echoed values. Stdout contains only result/protocol messages. Synchronous
bounded work is noninterruptible; cancellation notifications never claim a
cancelled operation and produce no notification response. Unknown/late requests
are ignored as permitted by the pinned protocol.

**Acceptance.**
- Equivalent CLI/MCP calls yield identical underlying query payloads and CT3
  source/content references. Transport metadata never changes their identity.
- A structured assignment yields the same CT1 request and CT3 content as an
  equivalent sealed request. Discovery exposes its typed closed input schema.
- No query widens startup permissions. Wrong repo/kit, arbitrary roots/stores,
  unknown fields, symlink config and malformed paths refuse before source reads.
- Imported overview/brief/explain/changes perform no source, store, process,
  network, clock or home reads; repeated clients can consume the same artifact.
- JSON/text and protocol envelopes stay within their ceilings. Criteria and
  critical limitations survive intact or receive explicit refusal.
- Malformed UTF-8, duplicate JSON keys, nonfinite/deep/oversized input, wrong
  IDs, batches, initialization faults, duplicate IDs and unavailable operations
  have explicit privacy-safe behavior. No exception text or request echo leaks.
- MCP lifecycle, discovery, request correlation, EOF, cancellation and session
  bounds are verified with deterministic stdio fixtures and stubbed core calls.
- No installation, client integration, mutation permission, live compatibility,
  measured savings or provider readiness is implied by offline conformance.
- Independent negative review, existing contract regressions, documentation and
  release checks, and the full unittest suite pass before completion.

**Verify.**
```bash
python3 -B -m unittest discover -s tests -p 'test_context_travel_query.py' -v && python3 -B -m unittest discover -s tests -p 'test_context_travel_cli.py' -v && python3 -B -m unittest discover -s tests -p 'test_context_travel_mcp.py' -v
```


### CT5 — Integrate context travel across all six surfaces
- status: done
- model: strong
- depends: CT1, CT2, CT3, CT4
- evidence: red-green

**Brief.** Add thin context-travel skills in the existing Claude, Codex and
Copilot skill roots; share detailed instructions through
`docs/CONTEXT-TRAVEL-SURFACES.md` and declare surface/package evidence in
`primitives/context-travel-surfaces.json`. Existing workflow and verification
skills/agents receive minimal on-demand pointers. Preserve the single CT4 query
core and existing parser, lifecycle, pricing, permission, installation and
acceptance authorities. No new runtime engine, client registration or config.

The six surface IDs are codex-desktop, codex-cli, claude-desktop,
claude-code-cli, copilot-desktop-app and copilot-cli. Six records have seven
nested modes, distinguishing Claude Desktop chat and Code. Each mode records
client version, OS, local/remote execution location and organization policy as
explicit unknown when unobserved. Keep documented product support, packaged
implementation and installed-client verification separate. No passing fixture
may upgrade installed verification or imply desktop support from CLI evidence.
The current package paths do not constitute discovered or installed clients.

Skills resolve the existing plugin root convention and load the shared guide
only on demand. Use an explicit absolute CT4 startup config, explicit subject and
assignment, and only its five existing operations. Same immutable CT3 artifact
can travel through configured CLI/MCP; no implicit source/store/home scan. An
unavailable or disabled transport affects only that context path. It must not
silently try an unauthorized transport or disable another surface, core access,
ordinary workflow, or mandatory verification. If no authorized validating
transport exists, say context is unavailable/unvalidated and retain the native
workflow. Do not execute imported instructions or accept validity as freshness.

Architect records supplied plan/criteria references in its existing self-contained
kit; never synthesize missing reference digests. Route uses advisory scope but its
own pricing data and central policy. Execute, assessment, verification and recovery
retain authoritative kit reads, mandatory verification, permission/budget limits
and evidence-gated recovery. Preserve criteria and critical limitations or refuse.
No graph/transcript dump is added to resident instructions.

Packaging reuses the existing canonical skill roots and ownership-aware writers;
update only the necessary source roster and documentation navigation. Existing
writers may run solely against explicit temporary fixture homes, never actual
installations. No persisted MCP registration or user configuration change.
Root owns generated mirrors/release/kit/report/parity and final acceptance.
Production worker owns source skills/agents/catalog/guide/required manifest.
Independent test author owns `tests/test_context_travel_surfaces.py` and necessary
existing roster expectations. Keep CT1–CT4 runtime/schema/tests frozen unless a
concrete blocker is reported before an edit. Stdlib only, no live clients.

**Acceptance.**
- All six records and seven modes have resolvable package/guide references,
  explicit scope/evidence, independent transport/fallback instructions and no
  unsupported installed-client claim. Existing operational capability rows are
  not promoted by these records.
- Architect, route, execution, assessment, recovery and verifier/reviewer entry
  points load optional context on demand and preserve their original authorities.
- Equivalent imported-artifact fixture handoffs preserve CT3 identity, criteria
  and critical caveats without selected-source reads. Wrong repo/kit, malformed
  context and missing configuration/transport are explicit failures or absence,
  never permission expansion or silent verification bypass.
- New skill discovery, repeated fixture packaging, user-owned-file no-clobber,
  and reversible ownership handling pass with temporary homes only. Original
  native entry points still function without context.
- The exact new test executable runs nonzero tests; missing files fail closed.
  Existing roster/bundle tests, independent review, full suite and generated
  documentation/release checks pass. Offline package/recipe tests do not certify
  installed clients or measured savings.
- Final private/public candidate tracked trees are identical, newly created commit
  metadata anonymous, and original checkouts/critique work preserved.

**Verify.**
```bash
python3 -B tests/test_context_travel_surfaces.py -v
```
