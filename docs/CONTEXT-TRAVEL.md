# Context travel contract

`bin/context_travel.py` defines `polytropos.context-travel/1`, a pure request and briefing
format. It accepts caller supplied data only. It does not read repositories, stores, clocks,
environment variables, or providers, and it does not run commands. `make_request`,
`make_briefing`, `parse_request`, and `parse_briefing` construct and validate the two records.
`canonical_bytes` and `content_sha` expose their deterministic representation.

## Identity and applicability

A request carries `repository_id`, `kit_path`, and the original `task_id`. The stable
`task_identity` is `sha256:` followed by the SHA-256 of the canonical JSON array
`[repository_id, kit_path, task_id]`. The repository ID is supplied explicitly; a path,
remote, or credential never implies repository equivalence. Task IDs are retained byte for
byte as Unicode strings. No case folding, trimming, path resolution, or Unicode normalization
is applied. Unsafe identities are refused.

`checkout_id`, `revision`, and `source_state_ref` describe where the request applies. They
do not change the stable task identity. A revision may be `null`; this means unknown, not
HEAD. `source_state_ref` can identify a dirty worktree snapshot separately from revision;
it may also be `null` when no such reference is known. A caller that does not provide a
source state cannot claim the working tree contents were checked. `assignment_id`,
`assignment_role`, and `question` pin the particular ask. Nullable `acceptance_ref` and
`source_ref` pin relevant input objects when known. All these fields affect `request_sha`.

References use `attempt_ledger.make_ref`'s `{ "id", "sha", "v" }` shape. A missing reference
is an explicit `null`; an unknown digest or referenced contract version is `null` within a
known reference. Nothing is reconstructed from a task, revision, or prose. A reference is
only a pointer to an object owned elsewhere.

## Briefing

A briefing repeats every request field exactly, including its digest. It adds a redacted
`summary`, an ordered nonempty list of redacted `criteria`, an ordered list of `evidence`
entries (`kind` is `source` or `evidence`, `ref` is a ledger shaped reference or `null`,
and `note` is redacted text), all four nullable ledger provenance fields, and
`declared_freshness` (`unknown`, `current`, or `stale`). The freshness label is a caller
declaration; parsing does not check the worktree or referenced objects. The `content_sha`
is SHA-256 over the briefing without that field. Transport timing, provider, token, and
delivery telemetry are outside the briefing body and its digest.

`parse_briefing(request, raw)` validates the supplied request and compares every repeated
request field. A response from a different repository, kit, task, checkout, revision,
source state, assignment, question, or pinned input reference fails even if its own digest
is valid. `make_briefing` copies echoed request fields, so editing its return value does not
change the caller's request. There is no partial response variant in this version.

## Canonical encoding and bounds

Canonical form is UTF-8 JSON with sorted object keys, compact separators, non-ASCII
characters retained, and nonfinite numbers refused. Object insertion order does not
matter. Array order matters, including criteria and evidence order. No whitespace, case,
path, or Unicode normalization is performed. JSON parsing refuses duplicate keys. The
entire encoded record is limited to 32 KiB; individual identifiers and reference parts to
200 characters; text fields to 2,000 characters; and criteria and evidence lists to 32
items. Mandatory criteria that do not fit fail instead of being truncated. Unknown fields
and versions fail.

Free text is processed through `bin/redact.py` without truncation and stored with counts
by redaction kind. Redaction changes the retained content and its digest; any original
source digest remains a separate reference. Machine identifiers containing recognized
credential shapes fail instead of being rewritten. Shape matching cannot detect every
secret, and validation of stored redaction counts cannot prove what was in the source text.

Schema validation and matching SHA-256 digests establish structure and change detection,
not authenticity, correctness, freshness, permission, readiness, or acceptance. The
`kit_contract` module continues to own task parsing, status, readiness, and acceptance.

## Selected source observations

`bin/context_readers.py` adds `polytropos.context-sources/1`. Its keyword-only
`read_sources` call takes explicit repository ID to absolute root bindings, a
repository ID and relative kit path, an ordered selection of known kit filenames,
an optional relative graph path, and optional evidence bindings keyed by the
exact `(repository_id, kit_path)` pair. Each evidence binding names an absolute
root and a selected relative `events_rel` file. No missing binding is guessed
from a kit basename, home directory, Git remote, or default store. The reader
never enumerates a directory, invokes Git, or follows graph nodes into source
files. `kit_files` defaults to `TASKS.md`; it can select `PLAN.md`, `GUARDRAILS.md`,
or `NOTES.md` explicitly. Both `.claude/kits/<slug>` and `tasks/kits/<slug>` are
accepted relative kit layouts.
Caller deny prefixes may have one trailing slash; duplicate slashes and other
noncanonical spellings are refused before any selected file is opened.

Each selected source has a state (`ok`, `missing`, `forbidden`, `corrupt`,
`inconsistent`, `over-limit`, or `unavailable`), a nullable content reference,
bounded observed facts, redaction counts, exclusion counts, a closed reason code,
and coverage. The result measures selected sources, opened file descriptors, and
physical bytes read. `sources[]` contains only selected sources and their outcomes.
Unselected optional graph and evidence sources are listed by kind in
`coverage.absent`, rather than emitted as source observations. `missing` means a
selected file was not present. `forbidden` diagnostics do not echo the
path or offending value. A maximum source count and per-source, total-byte, and
item limits stop work and disclose incomplete coverage; required task text is
not silently trimmed. A corrupt or over-limit source does not become a partial
task or a fabricated evidence record.

The selected file reader in `bin/safe_paths.py` refuses symlink roots and path
components, special files, and regular files with multiple hard links. It opens
the selected leaf in nonblocking mode, performs at most two byte-bounded reads,
checks descriptor metadata before and after, and compares the final path identity.
Its accounting includes bytes consumed before an error. The result reports
`consistency: consistent-at-read` only for a completed stable read. Every source's
semantic `freshness` remains `unknown` with basis `not-assessed`; a consistent
single-file read does not establish a current graph, an atomic multi-file
snapshot, or applicability of legacy attempt records. Hard-link refusal avoids
claiming that a name confined under the selected root establishes the data's
origin when another name outside the root can modify the same inode.

`TASKS.md` facts come from `kit_contract.parse_tasks`; graph JSON comes from the
pure parser shared with `graph_brief.load_graph`; attempt events come from the
pure parser shared with `AttemptLedger.events`. The new reader applies strict
JSON checks and uses `attempt_ledger`'s provenance reference helpers. It neither
computes readiness nor joins attempts to acceptance. Free text in returned
observations is shape-redacted with counts; machine identifiers containing
recognized credential shapes are refused. The checks cannot establish that
ordinary-looking private information is absent.

## Lifecycle projections

`bin/lifecycle_view.py` defines `polytropos.lifecycle-view/1`. Its pure
`compose_view(request, sources, ...)` accepts a validated CT1 request and a
bounded CT2 observation for the same repository ID and kit path. It reads no
files or stores, invokes no process, and does not consult Git, a clock, or the
environment. `compare_views(before, after)` compares two validated projections
for the same stable repository, kit, and task identity. `canonical_bytes` and
`parse_view` provide deterministic encoding and strict version, field, nested
shape, and digest checks. Operational CT2 read counters are not copied into the
projection or its content digest.

A projection echoes the full CT1 request, including checkout, revision,
source-state, assignment, and request digest. It has an overview of recorded
task status and source coverage; a role brief for architect, implementer,
verifier, or reviewer; findings with source-reference selectors or explicit
missing-basis codes; typed relationships; and limitations. All critical
limitations appear in the consumer brief as full objects. Role focus changes
which finding IDs are emphasized and their order; it does not change the
underlying facts. The brief is a **lifecycle-view/1 fragment**, not a CT1 task
briefing. Missing task or acceptance text yields a partial projection with no
fabricated criteria. Mandatory acceptance text is retained in full after
shape redaction. If the complete projection does not fit the caller's bounded
output budget, a refusal with no brief is returned; if even the refusal cannot
fit, the operation fails. No criteria or critical limitation is silently cut.

Optional intent, current-acceptance, and dependency-freshness links are
caller-declared, subject-scoped references. They are shown as declarations,
not verified policy decisions. The CT2 source references identify selected
raw file bytes, not an authenticated repository/kit/event binding. A request
source pin is comparable only to a selected ref with the same ID and version
and known SHA values; a different SHA is a mismatch, while a missing comparable
ref is unknown. Neither case treats one file's SHA as a whole source-bundle
digest. CT2 does not attest the request's checkout, revision, or source-state
fields, so those remain declarations.

CT3 validates the CT2 envelope and every event field it uses for correlation or
claims. Other bounded legacy event fields are opaque and are not exported or
interpreted. Older attempt events may name the same task ID without an intrinsic repository
and kit subject. Their claims remain visible as **unbound** findings; they do
not become task-specific verification or acceptance proof. A meaningful
precheck observation needs a subject-matched passing verification event and an
earlier recorded, non-tautological, failing precheck in the same run. A passing
note alone cannot establish event order. Even with that sequence, the event
record does not establish the precheck command or its independent adequacy;
the view retains a noncritical semantic-adequacy limitation. A done status or
an unrelated precheck alone cannot supply the sequence. Recognized passing
NOTES results include escalated passes; a blocked result contradicts done,
while unfamiliar labels remain recorded with unknown verdict semantics.
Conflicting task, note, and event claims are
kept visible, with uncertainty stated. Dependency freshness is never inferred
from the displayed task graph; a supplied state is labeled caller-declared.
Graph edges are code navigation only, not execution dependencies or permission.
This first projection does not extract standalone lexical paths from task prose,
because CT2 does not include caller deny rules in its returned observation; the
task's full redacted acceptance text is still retained.

Change comparisons validate both input digests and distinguish applicability
changes (checkout, revision, source state) from task status, criteria text,
acceptance-reference, source-reference, and limitation changes. A missing or
partial observation can make a value unavailable; this does not prove a
requirement was removed. A changed SHA or matching digest detects bytes or
representation differences, not authenticity, freshness, readiness, accepted
work, independent review, integration, or user validation.

## Query adapters

`bin/context_travel_query.py` defines a shared read-only query contract:
`polytropos.context-query-config/1` for startup bindings and
`polytropos.context-query/1` for results. A result has exactly `v`, `operation`,
and `data`. The operations are `overview`, `brief`, `explain`, `changes`, and
`capabilities`. CLI and MCP call the same query function and return the same
canonical JSON result for equivalent arguments. The `brief` and `overview`
operations return the full CT3 projection, including all criteria, findings,
source references, and critical limitations.

Startup config names repository IDs with absolute roots and selected kit paths.
Each kit lists zero or more selected kit files, an optional graph path, and an optional
explicit evidence root and event path. It also fixes deny prefixes, CT2 read
limits, and a result limit of 1,024–32,768 bytes. Config is loaded only from an
explicit absolute path through the confined stable reader; the file is capped
at 16 KiB and its physical reads at 32 KiB. A query can name a bound repository
and kit through its CT1 request, but cannot add roots, files, graph/evidence
locations, deny rules, or limits. Unknown config and query fields fail closed.
The result limit covers the entire query envelope. Text rendering refuses
overflow without shortening criteria or critical limitations.

For `overview` or `brief`, supply exactly one of: a plain `assignment`, a sealed
CT1 `request`, or a `view` holding a validated CT3 projection. The first two
forms may also include `intent_links`, `acceptance_links`, and
`dependency_freshness`. An assignment explicitly names repository ID, checkout
ID, revision (nullable), kit path, task ID, assignment ID, role, and question;
it may include source-state, source, and acceptance references. The shared core
uses CT1's request builder to seal the assignment. No repository, kit, or
checkout is guessed. The view form returns the immutable
projection data unchanged, with no source read. `explain` takes a supplied CT3
`view` and a nullable `finding_id`; it returns the selected findings and their
bases, the full criteria, all critical limitations, and source coverage.
`changes` takes supplied `before` and `after` CT3 projections and returns a
validated CT3 comparison. Imported artifacts must name a configured repository
and kit. The adapters do not store or retrieve historical snapshots; callers
carry the artifacts they want to explain or compare. `capabilities` lists only
operations, contract versions, and bounds. It does not list binding roots or
claim live client support.

The CLI accepts `--config ABSOLUTE_PATH`, an operation, and optional `--format
json` or `--format text`. Its arguments are one bounded JSON object on stdin;
`capabilities` also accepts empty stdin. Output is one newline-terminated result
on stdout. The config's result limit covers canonical core JSON; the CLI's
newline is transport framing and the complete CLI line has a separate 128 KiB
hard ceiling. Errors are generic and do not echo input, roots, or config paths.
Both adapter entry points answer `--help` or `-h` with static startup usage
before reading a config. In normal MCP serving mode stdout carries protocol
messages only.

The MCP adapter uses UTF-8, newline-delimited JSON-RPC over stdio and supports
MCP protocol version `2025-11-25`. Initialization returns that supported version
even if the client requested another version; a client that cannot use it should
disconnect. It serves `initialize`, the `notifications/initialized` gate,
`ping`, `tools/list`, and `tools/call`. Ping is available during initialization;
other tools wait for the initialized notification. Valid notifications receive
no response, including unknown notification methods. Tool
names match the five query operations. A successful tool response contains the
canonical query result as one text item. Requests and responses each have a
128 KiB frame ceiling, including their newline framing and JSON-RPC envelope;
a session has at most 256 frames and 256 used request
IDs. Malformed or oversized frames receive bounded errors without input echo.
Calls are synchronous and bounded. A cancellation notification for a completed
or unknown call has no effect; active work is not interruptible. This stdio
adapter offers no HTTP listener, sampling, generic command execution, or
implicit filesystem access. Initialization validates the client roots capability
as an optional boolean `listChanged` field. Other unused client capability
bodies are bounded, opaque input; the adapter does not semantically validate or
use those features and never requests client roots.
