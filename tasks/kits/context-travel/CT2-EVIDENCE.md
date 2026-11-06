# CT2 execution evidence

Date: 2026-11-01

## Authorization and scope

The user chose the original CT1 -> CT2 -> CT3 -> CT4 -> CT5 -> CT6 sequence after
the separate critique review. CT2 now implements explicit bounded source readers.
It does not implement the proposed Claude-first pilot, a producer/consumer flow,
CLI/MCP transport, installed-surface support, providers, merges or deployment.

Base: `82d34b6ae1af2e7f94c95526b8e675140d7418de`.
Worktree: the existing isolated `context-travel-ct1/poly-auto` worktree.
Branch: `codex/context-travel-ct1`.
The source checkout's separate `kit/context-travel` draft is not modified.

Central policy's read-only preview selected the strong implementation worker.
The pricing preview used profile M, 16,000 assumed input tokens and zero cache
hits; it is an estimate from the harness's current data, not actual usage or a
bill. No headless model driver was run. Implementation and test authorship are
separate assignments, followed by independent verification and coordinator
acceptance. No attempt-ledger or acceptance event is fabricated for this session.

## Files and ownership

- Implementer: new `bin/context_readers.py`; additive stable read helper in
  `bin/safe_paths.py`; pure parser extractions in `bin/graph_brief.py` and
  `bin/attempt_ledger.py`; reference and narrow security documentation.
- Independent test author: new `tests/test_context_readers.py` and
  `tests/test_safe_paths_context.py`.
- Coordinator: executable kit, complete Markdown report, version registration,
  generated documentation, test environment and final acceptance.
- Independent verifier: read-only adversarial review and temporary probes.

CT1 source and tests remain unchanged. The contract reference can expand to
document CT2 without changing CT1's schema or guarantees.

## Recorded failing baseline

Before production edits, the coordinator ran these commands using the existing
temporary isolated wrapper, Python 3.12, temporary homes/stores, client stubs and
the Python network guard:

```bash
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct1-checks-_u_zf8ux/run.py ct2-reader-red -m unittest discover -s tests -p test_context_readers.py -v
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct1-checks-_u_zf8ux/run.py ct2-path-red -m unittest discover -s tests -p test_safe_paths_context.py -v
```

Observed: the reader module was absent (one import error, exit 1); the stable
helper was absent (nine test errors, exit 1). These prove missing feature entry
points, not a newly reproduced exploit. Independent negative cases continued
expanding after this baseline. Logs and process JSON are retained under the
temporary wrapper directory with those labels.

## Decisions retained from critique review

- Explicit evidence selection or absence; no implicit personal-store fallback.
- No graph freshness/search entry point that can bypass the read boundary.
- Both kit layouts use explicit root bindings; no layout inference.
- Physical read budgets include rereads and failures; output limits alone do not
  establish bounded reading.
- Per-source `consistency` records a stable local read. Semantic `freshness`
  remains unknown/not-assessed. Multiple source reads are not a transaction.
- No readiness decision, acceptance reconstruction, model/provider probe or
  directory enumeration. Observations remain advisory data.

## Current verification status

CT2 is complete within its admitted offline reader scope. The coordinator's exact
verify passed: 28 reader tests and 12 stable-path tests. Existing regression
targets passed (17 path, 38 graph, 37 ledger, 9 CT1). Independent held-out findings
were corrected and rechecked; no blocking code gap remains in that bounded review.

The full suite passed: **6,529 tests in 605.153 seconds, zero failures or errors,
two skips, exit 0**. The wrapper completed in 611.126 seconds without timeout,
output truncation or leftover processes. The skips are configuration-dependent:
no agent currently carries an excluded configured pin, and no frontier pin is
recorded. No CT2 test was skipped. The final default-data-home canary passed.
Retained evidence: `ct2-full-suite.log` and `ct2-full-suite.json`.

Release generation passed; docs-site generation wrote 2 pages with 98 unchanged;
Copilot documentation generation completed with no content diff. The release
check and both documentation checks passed. The existing package-version note
is unchanged. Final whitespace check passed. Logs are in the same temporary
directory, with `ct2-accept-*`, `ct2-*-build` and `ct2-*-check` labels.

The final shape clarification retains only selected sources in `sources`;
omitted graph/evidence inputs are explicitly enumerated in `coverage.absent`.
This distinguishes a source not selected from a selected file that is missing,
without manufacturing an observation for an unselected path.

The final independent code review returned PASS for the frozen source hashes
below, bounded to the inspected CT2 behavior. It does not establish live
compatibility. The successful full-suite command was:

```bash
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct1-checks-_u_zf8ux/run.py ct2-full-suite -m unittest discover -s tests -v
```

It uses the temporary environment and Python network guard without an enclosing
outer Seatbelt profile, so tests can create the repository's own execution
boundaries. No whole-parent OS confinement is claimed. Runtime, parser and test
bytes remained frozen during that run; only kit evidence/report prose was updated.
All six recorded implementation/test digests were checked again and matched after
completion. Task status changed to done only after this result. Coordinator
acceptance covers this offline scope; no driver acceptance or ledger record was
backfilled. CT3 is the next task in the original order, and is not implemented.

Final independent evidence/status audit returned PASS after checking the completed
task, actual full-suite/targeted/check process results, six current file digests,
admitted file scope and the recorded limits. Final kit graph/static analysis found
no issues with an explicit repository root. No further tests were needed for the
final evidence-prose edits.

## Frozen implementation and test digests

| File | SHA-256 |
| --- | --- |
| `bin/context_readers.py` | `f4a118f3560e28b77d863153985bafb3648c1e9d6e0f8017347c9ee2ed884245` |
| `bin/safe_paths.py` | `f34578eee5f022af3364fd80613b4831f7cccb0dfe94a2120cda681eb126f36c` |
| `bin/graph_brief.py` | `c734fb8d9b9033a2bd15c6e3cc710efdcc3bddb7aa6e7e59e96729c95e976a0e` |
| `bin/attempt_ledger.py` | `faf798d5fe85ac9dcd31763de34a93789eabc34b25a3bcad5a22f4df7ce31e75` |
| `tests/test_context_readers.py` | `e0bda34508cc15f3007c9646af8f688f2af820d766290923dc01ef7d1719be6e` |
| `tests/test_safe_paths_context.py` | `414b1b91e4f622093b8deadeecfbe06f68d5ebf2b4bc1802426fa69b443939ef` |

CT1's module/test hashes still match NOTES.md. The shared contract reference has
expanded to document CT2; its CT1 schema has not changed.

## Findings during implementation

Independent temporary-file probing found that the first new stable-helper draft
accepted an in-root hardlink to an out-of-root synthetic file. Nofollow traversal
alone provides name containment, not proof of exclusive file ownership. The CT2
boundary was tightened to refuse multiply linked files before reading content;
the implementer and independent test author were assigned the correction and
regression fixture. Existing helpers retain their previous behavior. The
independent test author's corrected targeted helper tests passed.

Further held-out probes confirmed that a partial I/O failure charged bytes
correctly but used the policy-forbidden state. The helper now distinguishes
unavailable I/O from path/policy refusal. A deterministic leaf-inode replacement
was reported inconsistent with the expected accounting.

The integrated candidate passed 25 reader and 12 helper tests, then independent
review found malformed graph node/link containers being projected as empty and
a doubly trailing slash in a deny prefix being normalized. Additional tests also
found unhashable kit-file selections raising TypeError instead of the generic
configuration ValueError. The independent test author reproduced these in a
28-test reader run with three failures and two errors. Corrections passed all
28 reader tests and the independent verifier's held-out recheck. The initial
green target result was not used as final acceptance.

Existing regression checks passed: 17 safe-path tests, 38 graph tests and 9 CT1
tests. The first 37-test ledger run inside the ordinary outer shell sandbox had
one failure/eight errors in driver fixtures. Running the unchanged tests outside
that outer sandbox, with the same temporary homes/stores, client stubs and Python
network guard, passed all 37. This is the same nesting constraint identified in
CT1; no production execution policy was changed. Retained logs use
`ct2-legacy-ledger` and `ct2-legacy-ledger-control` respectively.
