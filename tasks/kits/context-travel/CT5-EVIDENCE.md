# CT5 execution evidence

Date: 2026-11-05

## Authorization and baseline

The user authorized CT5 across all six surfaces, retaining identical private/public
tracked content, offline temporary fixtures and stubs, no installation or GitHub
changes, and an updated full Markdown report. CT1–CT4 are complete; CT6 remains
planned in the original order.

Public implementation baseline: `1424b8c6b4c8647d6f419cec71f204ea2bb9b13b` on
`codex/context-travel-public-sync`. Private baseline:
`09a9f704d9d1e77aa93d4fc7ae631a6f7e486f24` on `codex/context-travel-ct1`.
Both started clean with tree `1415902e7b0b9601c4f518a306d189ab7f4ab601`.
The original public and private critique checkouts are not implementation roots.

CT5 has one production worker, a separate test author, independent read-only
review and coordinator acceptance. The coordinator owns kit/report state,
generated artifacts, final checks, commits and tracked-tree synchronization.
The mid-tier routing preview resolved to a worker unavailable through the app's
host delegation tool; integration and permission-boundary scope supports strong.
The strong preview selected the configured ordinary worker. These host-tool
assignments are outside the central driver's enforcement, not live driver runs
or observed ledger events. No driver evidence is fabricated.

The pricing preview used profile M, 32,000 input tokens and zero cache hits:
burn index 20, $0.45 API-equivalent proxy, billed value null. This is a planning
estimate, not actual usage, a charge or a session total. Data/policy previews are
retained as ct5-mid-preview, ct5-strong-preview and ct5-pricing-preview.

## Offline verification harness

The wrapper `/private/tmp/poly-auto-ct5-checks-3fj45w40/run.py` uses Python 3.12,
the repository process runner, fresh temporary HOME/data/config/TMPDIR, client
stubs, a cleared environment and a Python audit guard. Numeric-loopback fixtures
are allowed; covered external socket and lookup events are denied. No complete
OS confinement is claimed. The full suite may need the outer sandbox lifted so
its own execution-boundary fixtures can run; no product boundary is relaxed.
These raw logs are temporary. Durable summaries/hashes are recorded here.

Before implementation of the dedicated test file, the coordinator ran:

```bash
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct5-checks-3fj45w40/run.py ct5-red tests/test_context_travel_surfaces.py -v
```

It exited 2 because the file did not exist. This proves the admitted command
fails on an absent executable; it is not a behavioral defect reproduction or
completed test coverage. Actual fixture red/green evidence follows separately.

## Scope

Three native skill bundles expose the shared CT4 core. A separate six-surface,
seven-mode catalog distinguishes Claude Desktop chat and Code modes and retains
unknown installed-client evidence. The shared guide is loaded on demand.
Existing architect/routing/execution/assessment/recovery/verification authorities
remain in force. Fixture-only calls to ownership-aware packaging writers are not
actual installations. No MCP registration/config is added.

Status: CT5 is complete within its offline scope. The final full suite and
private candidate checks passed; the reviewed tracked content is synchronized.
The failed and interrupted freezes are retained separately.


## Findings and corrections

The independent initial fixture run (`ct5_tests_red`) executed seven tests with
16 failing subtests and three errors while the new catalog/skills/workflow pointers
were absent or incomplete. Existing CLI/MCP fixture paths were already green.
This is missing-integration evidence, not a live-client failure. The completed
initial integration passed seven tests; independent review expanded coverage to
11 before the final freeze.

Review found that the first guide pointed to a test for the required config shape
instead of providing a complete usable example. It now includes all required
nested config fields, an assignment and an executable command. The test executes
those documented JSON examples in a temporary fixture. Review also corrected a
hardcoded development-machine interpreter in the new test to `sys.executable`.

A held-out probe confirmed CT4 deliberately accepts a structurally valid imported
view for an authorized repository/kit even if it describes an older checkout or
assignment. CT5 initially failed to explain the recipient's applicability check.
The guide now requires comparison of repository, kit, task, checkout, revision,
source-state reference, assignment and role against the destination assignment.
Mismatches are historical/inapplicable; unknown fields remain unknown. A digest
and authorized repo/kit are not freshness, authentication or a current-assignment
check. Changing assignment or role requires an explicit new briefing, never
relabeling an immutable projection. CT4 itself was not changed.

Handoffs carry the complete CT3 `data` object and its subject references, not the
outer query envelope or startup configuration/grants. Each recipient supplies its
own authorized config. If no authorized validator is available, the artifact is
unvalidated advisory data and the native workflow still requires verification.
The catalog is declarative metadata used by the skill instructions; it is not an
automatic client detector, mode gate, dispatcher or new operational authority.

Existing roster expectations were updated for the new native skills and the
104-page generated documentation set. A Codex source-document inventory omission
was corrected, then all six Codex documentation tests passed. Two docs-builder
fixture failures before regeneration were stale-output findings; after generation,
all 16 tests passed. No test oracle was weakened to conceal missing client support.

## Initial targeted verification

Coordinator exact task command:

```bash
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct5-checks-3fj45w40/run.py ct5-frozen-targeted tests/test_context_travel_surfaces.py -v
```

Observed: **11 tests passed in 1.409 seconds**, wrapper exit 0 in 1.606 seconds,
without timeout, truncation or leftovers. The independent reviewer ran the same
executable under `ct5-independent-final`: **11 passed in 1.422 seconds**, wrapper
exit 0 in 1.566 seconds with the same clean execution limits.

Coverage includes six surface/seven mode records, native package discovery,
Codex/Copilot temporary fixture packaging, idempotence, user-owned-file no-clobber,
ownership rollback, executable guide examples, CLI/MCP identity equivalence,
criteria and nonempty caveat retention after removing the selected source,
imported tamper/unbound-subject refusal, and missing config failure. The tests
also demonstrate that imported structural validation alone does not reject old
assignment data. Agent-followed applicability instructions are not a runtime gate.
These checks exercise package/recipe/core behavior, not seven installed clients.

Additional observed checks: 87 Copilot bundle tests, 44 Codex bundle tests,
19 Codex skill/metadata/onboarding tests, six Codex docs tests and 16 docs-builder
CLI tests passed. Existing ownership tests in the full suite remain separate
regression coverage; no actual user-home installation occurred.

Generators were run through the same wrapper, then checked: sync_codex_surfaces
build rewrote six existing deprecated prompt mirrors (no new legacy prompt);
release_gate build found its generated block current; docs_build wrote 25 pages
and left 79 unchanged (104 total); copilot_docs built 20 artifacts. All checks
exited 0. The release check found no findings and retained the existing
package/plugin version note; it resolved contracts without live execution.
Kit admission graph/static analysis returned no findings (`ct5-kit-admission`).

The first full-suite command, run against the initial frozen source/tests, was:

```bash
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct5-checks-3fj45w40/run.py ct5-full-suite -m unittest discover -s tests -v
```

It completed **6,627 tests in 680.091 seconds**, with **13 failures and two
skips**, exit 1. The wrapper took 687.089 seconds without timeout, capture
truncation or leftovers. This failed run is not acceptance. CT1–CT4 runtime,
schema and tests remained unchanged from baseline.

## Initial reviewed source digests (failed full-suite freeze)

| File | SHA-256 |
| --- | --- |
| `skills/context-travel/SKILL.md` | `77b67cfbe44a9f83ab99a321369217cc80291798d70db50bd01b79cc21f9f711` |
| `codex/skills/context-travel/SKILL.md` | `deeb08cf79a3e75e130d5b62a238ce165c1e777583a1fe088f0929f1024de0f7` |
| `codex/skills/context-travel/agents/openai.yaml` | `ab92a8bb0e59141c928bf1426c0b75fd1d6f7b389094dff08335a700f97cd8b7` |
| `copilot/.github/skills/context-travel/SKILL.md` | `d7a8e2150b551870be4685b623b07f63a2f55be4a5c5b6e07b48d56a38eec15f` |
| `docs/CONTEXT-TRAVEL-SURFACES.md` | `6279768d9c727bfcc74191e7a42f33b4a00cb612dad6073409761facebe60f45` |
| `primitives/context-travel-surfaces.json` | `e57c026ff45a0c2fe8d52cad7bef716593d3ee41e072d0a16fa2d58088b69b3e` |
| `tests/test_context_travel_surfaces.py` | `65003f61d03d89370c76e6a3e52a7e02f2519eefdd2e3ed86bd35f955c55121a` |

The initial temporary `frozen-files.json` records 77 changed non-kit source,
test, package, reference and generated files for that failed run. It is retained
as historical evidence, not the current corrected freeze.


## Full-suite findings and corrected freeze

The 13 failures exposed four integration omissions:

- The common Claude assessment card was changed without its canonical staged
  prototype and Cursor copy. The same conditional context paragraph now lives in
  all three, preserving the existing exact-body and one-extra-Cursor-line checks.
  It requires the current surface to expose context travel; it does not package
  a new Cursor skill or claim Cursor context support.
- The Copilot skill manifest grew but the historical roster oracle and authored
  guide section did not. The old 13-name sequence is still pinned, with one
  explicit context-travel insertion. The authored SKILLS.md source now has its
  own when/how/safety section; generated blocks and HTML were rebuilt by the
  existing documentation engine.
- The documentation audit lacked the three new skill entries, and four census
  tests still expected the old tree. Three current scoped audit addenda were
  added without backdating original review. Counts now pin 17 Claude, 14 Copilot
  and 18 Codex skills, 41 Markdown deep dives/43 map keys, and 104 site pages.
  The deliberate extra-file drift test still fails on an extra fixture document.
- The new Claude skill description lacked its required positive invocation
  trigger. All three new skills now use a concise `Use when` description.

No assertion was removed to hide a missing feature, and no new test was skipped.
Production code in bin/ and CT1–CT4 tests stayed unchanged. Source changes were
made only after the first full run completed. Existing documentation generators
were rerun: Codex mirrors were current, docs_build changed seven pages and left
97 unchanged, and copilot_docs rebuilt its 20 artifacts.

The coordinator reran the eight affected test modules together (`ct5-correction-affected`):
**361 tests in 2.712 seconds, OK with two skips**, wrapper exit 0 in 3.008 seconds.
The exact module selection was:

```python
import unittest
names = ["test_assessment_skill", "test_copilot_bundle_adversarial",
         "test_copilot_docs_content", "test_docs_audit", "test_docs_build",
         "test_docs_build_adversarial", "test_primitives_doc_adversarial",
         "test_skill_entrypoints"]
suite = unittest.TestSuite(unittest.defaultTestLoader.discover("tests", pattern=n+".py")
                           for n in names)
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
```

The direct CT5 executable passed **11 tests in 1.956 seconds**
(`ct5-correction-targeted`, wrapper 2.125 seconds). Independent corrected review
passed the same **11 in 2.256 seconds** (`ct5-independent-corrected`, wrapper
2.437 seconds). Both exited 0 without timeout, truncation or leftovers.
Final documentation checks are current; release check retains its existing
informational version note and makes no live-client claim.

The corrected full-suite command is:

```bash
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct5-checks-3fj45w40/run.py ct5-full-suite-corrected -m unittest discover -s tests -v
```

This second run was interrupted after a distinct legacy test-guard failure;
it is not a completed suite or acceptance. Its runner recorded **408.123 seconds,
rc -2 (SIGINT)**, without timeout, truncation or leftovers. The coordinator
identified the owned wrapper/child process group before interrupting only that
run. The traceback at interruption is expected termination, not another product
defect. The 85-file `corrected-frozen-files.json` remains the source snapshot
for this interrupted attempt.

The failing `test_kits_dir_unchanged_by_import` imported routing_scorecard then
asserted the entire `.claude/kits` Git status was clean, except one old kit. The
legitimate CT5 audit addenda made that assumption false even before import. The
initial suggestion that concurrent report editing caused it was incorrect;
inspection established the clean-tree assumption. The replacement guard must
compare actual before/after tree state, preserve pre-existing edits, detect real
writes and add/delete changes, and avoid following symlinks. It must not exempt
the current audit/kit or delete the assertion. That test correction and its
fixture negative checks are recorded below before the final full run.

Final parity compares the entire tracked Git tree, including unchanged files
and modes. The final acceptance run freezes the entire checkout, including kit
status/evidence/report files, until it finishes.

## Corrected reviewed source digests

| File | SHA-256 |
| --- | --- |
| `skills/context-travel/SKILL.md` | `31277d42d8a9e87d046ec3d863020d0839fc53a1644ea1c36296d41048312fa7` |
| `codex/skills/context-travel/SKILL.md` | `cf97b2eac6819ca5f26dbe97f34da2cf131ddf5f0ff87085efccd3f510b43196` |
| `copilot/.github/skills/context-travel/SKILL.md` | `5ab5139062cef2ea0a3a14f3a44b31cf54f92f542820bace04009e7a8a5bf258` |
| `skills/assess-improvement/SKILL.md` | `f16a6619946fdb6661b7cb88d10319ba73e6e1206da2cb6936dbdb5fa001d91d` |
| `tasks/kits/decision-improvement/skills/assess-improvement/SKILL.md` | `9b8309216cc160c9ed5652e7e0cb04fe0ad95eebe66dd538f6fb62675ba698f3` |
| `cursor/skills/assess-improvement/SKILL.md` | `4778b41da081a253878455d715e2c7650a9f34d1f8b40aafbf969e75e1d25a10` |
| `docs/CONTEXT-TRAVEL-SURFACES.md` | `6279768d9c727bfcc74191e7a42f33b4a00cb612dad6073409761facebe60f45` |
| `primitives/context-travel-surfaces.json` | `e57c026ff45a0c2fe8d52cad7bef716593d3ee41e072d0a16fa2d58088b69b3e` |
| `tests/test_context_travel_surfaces.py` | `65003f61d03d89370c76e6a3e52a7e02f2519eefdd2e3ed86bd35f955c55121a` |


## Import guard correction and final acceptance run

The focused pre-fix test failed on the already edited audit path
(`ct5_defect_red`, exit 1). `tests/test_defect_vocabulary.py` now snapshots the
explicit repository kit directory before/after its first module-level imports
and around reimport. Paths, file types/modes, sizes, mtimes and regular-file
content digests are compared; static symlink targets are recorded without
traversal. No current-kit or audit exemption remains, and the old bare subprocess
call was removed. This tests actual mutation rather than unrelated checkout
cleanliness. It is not an adversarial concurrent path-swap security boundary.

Temporary negative fixtures prove an already edited file changing again, an added
file and a deleted file all change the snapshot; changing an external symlink
target does not. The corrected module passed **19 tests** in the test-author run
and coordinator run. Coordinator command:

```bash
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct5-checks-3fj45w40/run.py ct5-final-guard -m unittest discover -s tests -p test_defect_vocabulary.py -v
```

Observed coordinator result: **19 tests in 0.393 seconds, OK**, wrapper exit 0
in 0.724 seconds with no timeout, truncation or leftovers. The read-only independent
review accepted the first-import and dirty-baseline protections. Production
source was not changed for this correction. The exact CT5 executable also passed
again under `ct5-final-entrypoint`.

The final full-suite command is:

```bash
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct5-checks-3fj45w40/run.py ct5-full-suite-final -m unittest discover -s tests -v
```

Observed result: **6,629 tests in 675.587 seconds, OK with two skips**, no
failures or errors. Wrapper exit 0 in **683.255 seconds**, no timeout, truncated
output or leftovers. `final-frozen-files.json` recorded all **93 changed files**,
including context-travel kit documents. Every hash still matched after completion.
Earlier 77-file and 85-file manifests remain historical snapshots. Only the seven
kit completion/evidence/parity records were updated after this accepted run;
production source, tests and generated packages remained frozen.

Final guard SHA-256: `e670b994fcb7e4dd1111014b474f3dbef62fbc950310069138af06c64d4f2fe2`.
The last edit only corrected a docstring that overstated resource bounding; the
helper snapshots an explicit directory and has no hard file/byte cap. No behavior
changed after the 19-test verification. Final CT5 entry-point verification was
11 tests in 2.452 seconds, wrapper exit 0 in 2.725 seconds.

## Private candidate verification and final parity

The reviewed CT5 delta was transferred as content from the public candidate to the
private candidate, without copying commit history. Before completion-record edits,
both indexes had tree `d4b3061a88de1d4c2ba8772f7ea7eeaea7c42929`. The same seven
completion records are maintained identically before the final commit boundary.
Final commit/tree IDs, clean status and recursive path/mode/blob comparison are
recorded in the local CT5 handoff; equal trees do not imply equal histories.

These commands used the private candidate's separate temporary fixture homes,
client stubs and the same audit guard through `run-private.py`:

```bash
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct5-checks-3fj45w40/run-private.py ct5-private-entrypoint tests/test_context_travel_surfaces.py -v
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct5-checks-3fj45w40/run-private.py ct5-private-guard -m unittest discover -s tests -p test_defect_vocabulary.py -v
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct5-checks-3fj45w40/run-private.py ct5-private-release bin/release_gate.py check
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct5-checks-3fj45w40/run-private.py ct5-private-docs bin/docs_build.py check
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct5-checks-3fj45w40/run-private.py ct5-private-copilot bin/copilot_docs.py check
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct5-checks-3fj45w40/run-private.py ct5-private-mirrors bin/sync_codex_surfaces.py check
```

Observed: **11 CT5 tests in 1.808 seconds** and **19 guard tests in 0.131 seconds**,
both OK. Release inventory had no findings (contract IDs resolved, not executed);
the existing package/plugin version note remains. Documentation and Codex mirrors
were up to date. All six wrappers exited 0 with no timeout, truncation or leftovers.
The accepted full suite ran in public and was not repeated in private: exact
source/test parity supports reuse, and these private results remain separately
attributed. No installed client or provider compatibility, installation, remote
publication, deployment or measured cost saving is established. CT6 remains planned.
