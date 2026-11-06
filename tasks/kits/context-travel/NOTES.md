# CT1 execution evidence

## Scope

Authorized on 2026-11-01: CT1 in an isolated workspace, offline verification with
synthetic inputs, temporary fixtures and stubs. No live clients, installations,
provider calls, GitHub mutations, pushes, merges, or deployments.

Baseline: `7671894d2ac9e43f1a6c808d5b31477a107b119e`.
Branch: `codex/context-travel-ct1`.
Workspace: the managed `context-travel-ct1/poly-auto` worktree.

Central policy preview selected worker intent `strong` for implementation. The
preview is not an observed runtime-identity attestation or usage measurement.
Implementation and independent review were performed in the app; no headless
execution driver was run. No attempt ledger or acceptance event was backfilled.

## Verification

- Implementer recorded a failing missing-module test before implementation.
- Coordinator reproduced the initial file-path import failure, then the worker
  corrected sibling loading and removed global test `sys.path` mutation.
- Targeted tests: 9 passed. Independent targeted tests: 9 passed, exit 0.
- Independent review: no concrete contract defect found; full suite and final
  task completion were left to the coordinator.
- Static kit parser/graph/analyzer: no findings with explicit `repo_root`.
- Release documentation generator: passed under network-denying confinement.
- Docs-site generator: 3 written, 97 unchanged. Its check passed.
- Copilot documentation generator: 20 artifacts regenerated, no content diff.
  Its check passed.
- Release check: passed, no findings; its existing package-version note remains.
- First full suite: 6,489 tests, 13 failures, 38 errors, 25 skips. Six documentation
  assertions required page navigation/census updates; three analyzer assertions
  depended on PATH discovery; 42 driver failures/errors came from nested Seatbelt
  interference. This failed run is retained in `full-suite.log`.
- Corrected documentation tests: 374 plus 16 passed. Harness controls: 27 role
  contract tests and 123 analyzer tests passed. Product driver code was unchanged.
- Corrected full suite: 6,489 tests in 645.782 seconds; exit 0, no failures or
  errors, 2 skips. The wrapper completed in 651.681 seconds, without timeout,
  output truncation, or leftover processes. See `full-suite-final.log` and its
  JSON process result.
- Skips: no agent currently carries an excluded configured pin; no frontier pin
  recorded. These are configuration-dependent checks, not CT1 tests.
- Final release check: passed, no findings. Both generated documentation checks
  passed. Reviewed implementation/test/reference digests below are unchanged.

The full-suite command was:

```bash
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct1-checks-_u_zf8ux/run.py full-suite-final -m unittest discover -s tests -v
```

Coordinator acceptance covers CT1's bounded offline contract only. Task status
was updated after the full suite passed. This is a recorded work-session result,
not a fabricated driver acceptance or attempt-ledger event.

Final independent verification returned PASS for CT1 after checking task
completion, its earlier independent 9-test result, the coordinator's full-suite
and documentation results, unchanged source digests, and scope/limitation records.
It does not establish installed-client compatibility or verify CT2.

Python: `/opt/homebrew/bin/python3.12`, with `-B` and stdlib unittest.
Logs and explicit test environment: `/private/tmp/poly-auto-ct1-checks-_u_zf8ux`.
The wrapper `run.py` invokes `bin/proc_runner.py` with a temporary HOME and data
roots, no inherited provider credentials, a bounded wall time/output, stubs for
external clients, and a Python network guard. The `offline.sb` enclosing profile
denies network, real harness-home reads, and user-home writes except the isolated
worktree. It was used for builds and the first suite. Its inability to nest the
repository's own verification sandboxes caused fixture failures, so the corrected
suite uses the temporary environment and Python network guard while allowing
tests to create their own execution boundaries. No whole-parent OS confinement is
claimed for that corrected run. Discovery-only `node`/`uv` stubs replace missing
PATH entries without installing or executing those tools.

Ordinary-shell doc generation first failed because that sandbox did not allow
writes to the new managed worktree. The authorized scoped retry used the explicit
network-denying profile and succeeded. No generated document was hand-edited.

## Reviewed source digests

The independent review and successful full-suite run covered these exact files:

| File | SHA-256 |
| --- | --- |
| `bin/context_travel.py` | `c21aba50bd4b58b9ec5c63783c4f4f562a27f8669ee686a115f226283b339812` |
| `tests/test_context_travel.py` | `784bfb949ad0087383e75391b5bf28e5410f7100ab79225568b5342308e295ce` |
| `docs/CONTEXT-TRAVEL.md` | `46df72a57564719a3df64824434db9f7f3da223fd22b21493c1616d70cffeb2b` |

## Limitations

Freshness, provenance and redaction counts are structurally checked declarations;
their truth is not established here. Unknown source state remains unknown. Hashes
identify content and do not authenticate it. No read-only lifecycle query, index,
CLI/MCP transport, installed-surface compatibility, or provider execution has been
implemented or proven. CT2 and later remain unimplemented. Earlier Codex precheck and
acceptance-only drift gaps are unchanged.

## Continuation and separate critique

The user requested continuation, then identified the separate critique branch as
`kit/context-travel`. It is checked out in the source repository and its draft kit
is uncommitted. Its PLAN, TASKS and GUARDRAILS were read without modification.
CRITIQUE-RECONCILIATION.md records their digests, two read-only reviews, concrete
corrections and a recommended pilot mapping. The all-CT report links that record.
The user chose to keep the original phase order; the pilot alternative is not
adopted. CT2 has since completed under the strengthened reader gates. Its separate
CT2-EVIDENCE.md records implementation, independent test authorship/review, found
and corrected defects, 40 targeted tests, and the successful 6,529-test full suite
(two configuration-dependent skips). The user then requested continuation; CT3
is complete with full-suite acceptance recorded in CT3-EVIDENCE.md.
Do not modify, merge, or cherry-pick the separate branch implicitly.

The reconciliation's independent document review passed after a citation fix.
Both documentation mirrors were regenerated and checked successfully with no
generated-content diff. The draft source hashes were rechecked unchanged. Only
kit documentation changed; the full unit suite was not rerun for this addition.

The complete scope and roadmap are in `IMPLEMENTATION-REPORT.md`.

## CT3 continuation

The original phase order is preserved. CT3 adds the pure lifecycle projection,
role briefings and comparisons, using the existing CT1/CT2 authorities. The
39 independently authored targeted tests, 202 context regressions, held-out
adversarial review and documentation/release checks have passed. The full suite
passed 6,568 tests in 614.587 seconds with two configuration-dependent skips and
zero failures or errors against the reviewed frozen source hashes. The wrapper
exited 0 after 621.040 seconds without timeout, truncation or leftover processes.
CT3-EVIDENCE.md records
the failing baseline, fixture corrections, schema/evidence defects, remedies,
exact commands and remaining semantic limits. No acceptance or attempt ledger
record has been fabricated. CT4–CT6 remain planning briefs.

## CT4 continuation and public parity — 2026-11-05

The user requested continuation, then required the same codebase in public
polytropos and private poly-auto. The private repository supplies access to
private/internal Copilot workflow capabilities; product source and workflow
definitions are to remain shared. They chose CT4 completion first, followed by
reviewed local synchronization. No publication or GitHub changes are authorized.

CT4's shared query, CLI and MCP implementation passed 48 targeted tests and
independent review. The first full run's eight errors
were traced to an overbroad harness guard against a loopback fixture. All 59
boundary-module checks passed after a harness-only correction; the complete
rerun retained frozen source/tests and passed 6,616 tests in 628.690 seconds,
with two skips and no failures or errors. CT4 is complete within its offline
scope. CT4-EVIDENCE.md records frozen
hashes, actual commands, protocol sources, defects and corrections. The earlier
temporary log directory expired; historical summaries are not new test results.
PUBLIC-PARITY.md records exact local drift, gated workflow behavior and the
anonymous-commit requirement for the synchronization candidate. Preserve the
active public checkout and separate critique checkout.

CT4 was committed locally as `7130c69`. The subsequent isolated public candidate
on `codex/context-travel-public-sync` receives the complete tracked content delta
from local public base `ec47d10`, with a new anonymous content-only commit rather
than copied private history. Its initial index tree matched the CT4 commit.
250 context tests, release and both documentation checks passed in the public
workspace with temporary fixtures/stubs. The accepted full suite is reused for
identical frozen runtime/tests, not claimed as a public rerun. Shared final
status/parity documents are copied identically. PUBLIC-PARITY.md and the final
local handoff retain the evidence, commit/tree comparison and publishing limits.
Concurrent `docs/skills-guide` edits in the original public checkout are separate
work and remain untouched. CT5/CT6 are not yet implemented or dispatched.
