# CT3 execution evidence

Date: 2026-11-01

## Scope and authorization

The user requested continuation after CT2. This admits CT3 in the original
CT1 -> CT2 -> CT3 -> CT4 -> CT5 -> CT6 sequence. The task is a pure read-only
lifecycle projection and role-briefing library over explicit in-memory inputs.
It does not add source reads, CLI/MCP transports, installed skills, provider
operations, dispatch, acceptance mutations or live verification.

Base: `f6dc1e9a4d4740c464cffd9f68a8407972bcec18`.
Branch: `codex/context-travel-ct1`, in the existing isolated worktree.
The separate critique branch and the public checkout are untouched.

Central policy's read-only preview selected the strong implementation worker.
The runtime pricing preview used profile M, 32,000 assumed request input tokens,
and zero cache hits. It is an estimate, not actual usage or a bill. No headless
model client or provider was invoked. Planned assignment and observed runtime
identity are not conflated; no attempt or acceptance event is backfilled.

## Ownership and contract decisions

- Implementer: new `bin/lifecycle_view.py` and the shared contract reference.
- Independent test author: new `tests/test_lifecycle_view.py` only.
- Independent verifier: read-only adversarial review and temporary probes.
- Coordinator: executable kit, version registration, generated docs, full suite,
  evidence/report files and final acceptance.

The new lifecycle-view contract represents projection completeness and partial
context explicitly. Its role brief is not a CT1 task-briefing object; CT1 request,
identity and reference semantics remain authoritative and unchanged. Full request
applicability is echoed, not verified by observations that lack that information.

CT2 output is redacted and projected. Recomputing an original acceptance digest
from that text would create false provenance, so CT3 uses explicit references as
declarations and reports observed text changes separately. Legacy records without
intrinsic repository/kit binding remain unbound. A matching task ID alone is not
a join. Graph links and lexical path mentions remain navigation, not ownership or
execution dependencies. Findings carry source references/selectors or explicit
missing-basis codes.

Critical limitations travel in each role brief. A budget failure refuses instead
of dropping criteria or critical uncertainty. Complete/partial/refused describe
the projection, not acceptance, validation or merge readiness. Read counters are
validated as input but excluded from substantive content identity.

## Observed failing baseline

Before the implementer wrote production code, the coordinator ran:

```bash
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct1-checks-_u_zf8ux/run.py ct3-red -m unittest discover -s tests -p test_lifecycle_view.py -v
```

Observed: missing `lifecycle_view.py` caused one import error, exit 1. This proves
the feature entry point was absent, not a reproduced exploit. The independent
tests then expanded before implementation was complete. Logs and process JSON
are retained under the wrapper directory using the `ct3-red` label.

The existing wrapper uses Python 3.12, temporary homes/stores, client stubs and a
Python network guard. Full-suite verification will use the already-established
environment without an outer Seatbelt profile, so fixture tests can create their
own repository execution boundary. Whole-parent OS confinement is not claimed.

## Status

CT3 is complete within its offline scope. Implementation, targeted verification,
independent held-out review and full-suite acceptance have passed. No live
compatibility, cost savings, or correction of the older driver precheck/drift
gaps is claimed.

## Findings during implementation

The first fixture used an item limit of eight. CT2 counts parsed task-object
fields within that bound, so the observation correctly returned over-limit. The
independent test author raised the fixture limit to sixteen for cases expecting
a usable task; CT2's committed behavior was not changed. This was a fixture
correction, not a production-reader defect.

Early targeted checks exposed omitted graph-navigation relationships and missing
current-acceptance-link changes in comparisons. Integration review also found
that the first draft validated only shallow parts of the input and output
schemas. Nested validation and export redaction require correction before a
matching digest can be treated as a valid view.

An independent in-memory probe found a false join: a same-task-ID legacy ledger
pass was labeled unbound in its finding but still created a subject-specific
measured-verification relationship and pass warning. Unbound records must remain
visible without participating in task-specific proof or contradiction inference.
The implementer corrected these findings, the independent test author added
regressions, and the final checks below reverified them.

A second independent probe found that a precheck from one run could suppress the
missing-precheck limitation for a different run. The corrected implementation
must preserve unknown lineage rather than infer a relationship from task identity.
Rechecks confirmed the unbound-event and cross-run cases were corrected.

Further transport-integrity probes found that a rehashed comparison could carry
an unsupported nested change and that a partial role brief could lose its criteria
without a missing-criteria limitation. A matching content digest does not excuse
schema or internal-consistency failures. The coordinator's initial comparison
probe is retained as `ct3-nested-probes.log/json`; its successful process exit
records that the bad input was accepted, not that the contract passed.

Event-order review then demonstrated that a precheck appended after a passing
event in the same run could suppress the baseline limitation. A matching run ID
is insufficient without a preceding recorded check. Even an ordered failing,
non-tautological baseline cannot prove semantic adequacy, independent validation,
or correction of the earlier driver gaps.

Notes-vocabulary review caught a false conflict for the existing `escalated-pass`
outcome. Existing positive outcomes remain distinct from unknown future labels;
the negative fixture uses the authority's `blocked` label rather than adding a
new `fail` meaning to production code merely to satisfy a test.

The reference also documents a deliberate narrow scope: this version does not
extract standalone lexical task-path relationships. Graph links remain navigation
over the supplied graph observation. CT2 does not remove every path mention from
free-text briefs; this omission is not a claim of comprehensive path redaction.

## Frozen implementation and verification

The coordinator independently ran the executable task verification after the
worker's and test author's checks:

```bash
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct1-checks-_u_zf8ux/run.py ct3-final-targeted -m unittest discover -s tests -p test_lifecycle_view.py -v
```

Result: **39 tests, OK**, 0.223 seconds of unittest time; wrapper exit 0,
0.509 seconds, no timeout, output truncation or surviving process tree reported.
The broader `test_context*.py` regression selection passed **202 tests** in
0.410 seconds (`ct3-contract-regressions`). This selection includes the existing
context-weight checks as well as CT1 and CT2 reader tests.

The independent verifier did not read the new test file. Its held-out probes
confirmed that unbound events create no measured-verification relationship;
cross-run and reverse-order baseline records retain the precheck limitation;
properly ordered records still disclose unknown semantic adequacy; and
rehashed malformed freshness, missing criteria and inconsistent completeness
cannot bypass validation. Read-counter changes preserve substantive identity;
mandatory criteria survive, and an undersized budget refuses. Operation-time
file, process, socket, clock, environment and lazy-import seams were patched to
raise while compose, parse and compare succeeded.

Frozen SHA-256 digests:

| File | Digest |
| --- | --- |
| `bin/lifecycle_view.py` | `72c6e7811a762bc0fc11e0ebc343f87020e0b8a670afd17aedb85b4232c9862d` |
| `tests/test_lifecycle_view.py` | `6d4e276ff4db7a6d4642ef70345c5a0c540941d9f8d592a733428510a9ba7d75` |
| `docs/CONTEXT-TRAVEL.md` | `598d2a777c5a4b80c539a9a37c32626e5709479cda67c7f3a3970e44b2c68d12` |

The CT1/CT2 sources and their tests have no diff from the CT2 baseline. The new
contract is registered in the release contract inventory. The coordinator ran
the following with the same temporary offline wrapper, using the corresponding
`ct3-release-*`, `ct3-docs-*` and `ct3-copilot-docs-*` log labels:

```bash
python3 -B bin/release_gate.py build
python3 -B bin/docs_build.py build
python3 -B bin/copilot_docs.py build
python3 -B bin/release_gate.py check
python3 -B bin/docs_build.py check
python3 -B bin/copilot_docs.py check
```

All passed. The docs-site generator updated two of 100 pages; the Copilot mirror
had no resulting content diff. Release check reports no findings and preserves
the existing informational package/plugin version note. It resolves contract IDs
without running live contract commands; it is not a substitute for the full suite.

## Full-suite acceptance

The frozen implementation passed:

```bash
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct1-checks-_u_zf8ux/run.py ct3-full-suite -m unittest discover -s tests -v
```

Observed result: **6,568 tests in 614.587 seconds, OK (skipped=2)**, zero failures
or errors. The wrapper exited 0 after 621.040 seconds and reported no timeout,
output truncation or surviving process tree. The two skips are configuration
dependent: no excluded configured agent pin and no recorded frontier pin. The
default-data-home canary passed. CT3 tests were not skipped.

The outer sandbox was lifted for this authorized local test command so fixture
tests could establish their own execution sandbox. The wrapper still pinned
temporary homes/stores and stubbed clients, cleared the inherited environment
and installed its Python network guard. Whole-parent OS confinement is not
claimed. Retained full results are `ct3-full-suite.log` and
`ct3-full-suite.json` alongside the runner.

All source and test digests remained frozen throughout the full-suite run.
Task completion records the observed offline checks; no driver acceptance or
attempt ledger was created or reconstructed. CT4 is next in the original order.

Final kit parsing, graph validation and static analysis passed with CT1–CT3 done
and no findings (`ct3-final-kit-analysis.log/json`). An independent final audit
confirmed the completed status, full-suite result, retained hashes and scope
statements. The coordinator rechecked the frozen hashes and whitespace; no
runtime or test edits followed the successful suite.
