# Shared public/private codebase

Date: 2026-11-05

## User requirement

Keep the same source, tests, docs, skills, templates, provider interfaces and
workflow definitions in public polytropos and private poly-auto. Private-only
Copilot features explain repository visibility; they do not justify a separate
product implementation. Gate execution by repository capability/visibility where
needed. All CT1–CT6 and subsequent lifecycle phases must reach the public product.

The user chose to finish CT4, then prepare synchronization locally for review.
No push, PR, merge, GitHub action run, installation or live integration is
authorized. Local preparation is not public availability.

## Read-only local assessment

The public checkout was clean at `ec47d10` on `feat/route-experiment`, equal to
its local remote-tracking branch. Local main is older (`1cd9e62`). No fetch was
performed, so these are local observations, not claims about remote freshness.
The private CT3 baseline `e47ecbf` descends from `ec47d10`.

The exact tracked-tree delta at that baseline is 31 files: 18 additions and
13 modifications. The public local tree lacks CT1–CT3's libraries, reference,
tests and kit. Changes include the shared reader seams, release inventory and
generated docs, plus the private sync workflow. CT4 will add to this delta.
No current parity is claimed.

The existing `.github/workflows/sync-upstream.yml` transfers public main toward
private main; it does not promote private CT work to public. Its job is already
gated to the private repository. The same file can therefore be tracked in both
trees without executing private synchronization in the public repository.

The release inventory already recognizes bin, docs, docs-site, tests, tasks,
skills, codex and copilot as package roles. The existing release/privacy process
still applies: tracked runtime/data exclusions, generated docs, fixture tests,
and accurate unknown labels for clients not exercised live. Cached plugin
packaging can copy ignored/untracked checkout content, so a tracked-tree match
alone is not an installation or privacy certification.

A narrow added-line pattern screen found no local user-home paths, session IDs
or email addresses in the baseline delta. Credential-shaped matches were test
fixtures; private-repository references were in the gated workflow. This is not
a proof that all private information is absent; review the final CT4 delta too.

One existing private commit after the common base has nonanonymous author and
committer metadata. Do not transfer that commit into public history or rewrite
private history. Prepare a new anonymous public commit from reviewed tree content
and verify both identities. The identifying values are intentionally not copied.

## Synchronization gates

1. Complete CT4 and freeze its tested tracked tree. Keep its evidence and all
   CT1–CT6 briefs current and distinguish offline checks from live capability.
2. Preserve the active public checkout. Prepare the candidate in an isolated
   public worktree based on the known local common history, using a new codex
   branch and anonymous commit identity. Do not fetch or publish implicitly.
3. Review the full content delta, including workflow gates, fixtures, package
   exclusions and documentation. Transfer the same tracked content rather than
   maintaining provider- or harness-specific private copies of shared logic.
4. Verify exact tracked-tree equality and an empty content diff at the synchronized
   revisions. Record both commit/tree IDs in the final handoff; do not confuse
   equal trees with equal histories, settings, permissions or installations.
5. Run required public release/documentation checks in the candidate and preserve
   the full-suite evidence for the identical tree. Re-run checks where environment,
   changed sources or new failures justify it; do not claim unrun checks passed.
6. Publication remains a later explicit action. Before publication, verify anonymous
   metadata, remote/base freshness, reviewed diff and release gates. Subsequent
   CT5/CT6 work must pass the same parity gate; permanent source exceptions require
   an explicit documented decision rather than silent drift.

Status: CT4 passed its offline gates. An isolated local public candidate is
prepared on `codex/context-travel-public-sync`. Publication remains excluded;
the original public checkout is not the candidate.

Immediately before preparation, the original public checkout still had HEAD
`ec47d10` but another task had switched it to `docs/skills-guide` and begun README
and skill-guide documentation edits. Preserve those tracked/untracked edits.
The isolated candidate uses the unchanged committed base; it does not absorb
or overwrite this concurrent uncommitted work. Exact parity applies to the two
reviewed candidate revisions, not to every active checkout at every moment.

## Final candidate content review

The bounded read-only screen was repeated with CT4's frozen runtime/tests and
current documentation. All eight new CT4 source/test/evidence files are under
recognized bin, tests and tasks package roles. No concrete user-home path,
email address or session identifier was found in the reviewed added content.
Credential-shaped matches were synthetic redaction fixtures. Temporary wrapper
and log paths, plus the observed Python interpreter path, remain in historical
verification commands; they are not portability requirements or durable logs.
The repository-specific workflow gate remains unchanged. This is a scoped
content review, not a general secret-absence or installation certification.

## Prepared local candidate and verification

The managed `context-travel-public-ct4/polytropos` worktree starts at local public
`ec47d10ea5b3dba5f12498ff82bc209784eceab5`. The reviewed content was transferred
with a binary tracked diff from that base to private CT4 implementation commit
`7130c6916aea52925ced948f50a7fa688d4418e3`. No private commits or identifying
history were copied. The initial candidate index tree exactly matched the
implementation commit's tree. The delta contains 39 files: 26 added, 13 modified.
Shared completion/parity notes are maintained identically in both candidates.

The candidate uses the same frozen runtime/test files as CT4's accepted
6,616-test full suite. That full suite was run in the private isolated workspace,
not repeated in the public candidate. Only kit completion/parity documentation
changed after the full-suite freeze; release and generated-doc content did not.
Independent review found no staged-content or packaging blocker. The candidate
has a new content-only anonymous commit, while private history is preserved.
Final commit/tree IDs, equality and identity checks are recorded in the local
synchronization handoff; equal trees do not mean equal histories.

Actual public candidate commands used a separate temporary HOME/data/TMPDIR,
stubbed clients, the same loopback-aware Python audit guard and process runner:

```bash
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct4-checks-jxfg3r97/run-public.py ct4-public-context -m unittest discover -s tests -p 'test_context_*.py' -v
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct4-checks-jxfg3r97/run-public.py ct4-public-release bin/release_gate.py check
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct4-checks-jxfg3r97/run-public.py ct4-public-docs bin/docs_build.py check
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct4-checks-jxfg3r97/run-public.py ct4-public-copilot-docs bin/copilot_docs.py check
```

Observed: **250 context tests passed in 2.639 seconds**, including CT4's 48
tests; wrapper 3.907 seconds. Release check found no findings and retained the
existing package/plugin version note; contracts were resolved, not run live.
Both documentation checks were up to date. All wrappers exited 0 with no timeout,
truncation or leftovers. These temporary paths document the observed checks;
they are not portable commands, required installation paths or durable logs.

Local preparation does not update public remotes or install the plugin. No live
client/provider compatibility, automated reverse synchronization, measured savings
or deployment is established. CT5 and CT6 remain next in the original order and
must retain this exact-source parity requirement. Concurrent public documentation
work must be reconciled separately before eventual publication rather than erased.
