# CT4 execution evidence

Date: 2026-11-05

## Scope and authorization

The user requested continuation after CT3, then required the same codebase in
private poly-auto and public polytropos. The private repository exists so its
Copilot workflows can use capabilities available to private/internal repos.
They chose to finish CT4 before preparing local synchronization. Publication,
live clients/provider calls, installation and GitHub changes remain excluded.

Baseline: `e47ecbf702265b4129f75454961d6a71dfc52717`, isolated branch
`codex/context-travel-ct1`. CT4 adds a shared query/access boundary, CLI and local
MCP stdio adapters. CT1–CT3 and the existing authorities are frozen. The public
checkout and separate critique checkout are read-only during implementation.

The preliminary mid-tier policy preview resolved to a model unavailable in this
app's worker pool. Transport/access-boundary work meets the routing skill's
strong integration/security category; a fresh strong preview selected the
configured ordinary worker. No frontier recovery or live driver was invoked.
The pricing preview assumed profile M, 32,000 input tokens and zero cache hits.
Its burn index was 20; the $0.45 estimate is an API-equivalent proxy, not a bill
or measured session total. Planned identity is not runtime dispatch evidence.

## Contract and protocol decisions

- One shared core handles overview, brief, explain, changes and capabilities.
  Trusted startup config selects exact repository, kit, files, graph/evidence
  locations, deny rules and limits; tool arguments cannot expand that access.
- Overview/brief can consume a supplied validated CT3 artifact unchanged without
  source reads. Explain/changes also use supplied artifacts. This permits
  cross-client consumption of an immutable payload; no historical server store
  or artifact-reference lookup is claimed.
- Query/config have their own closed versioned schemas. Mandatory criteria and
  critical limitations remain intact through JSON/text or cause explicit refusal.
  Complete/partial/refused retain CT3's projection-only meaning.
- MCP uses the published 2025-11-25 stdio protocol. Initialization and discovery
  are bounded; synchronous queries do not promise active cancellation. No HTTP,
  roots, sampling, mutation, generic command execution or installed-client claim.

Protocol sources, consulted 2026-11-05: [messages and IDs](https://modelcontextprotocol.io/specification/2025-11-25/basic),
[stdio framing](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports),
[lifecycle/version negotiation](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle),
[tools and errors](https://modelcontextprotocol.io/specification/2025-11-25/server/tools),
and [cancellation](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/cancellation).
These documentation reads were research, not a live transport/client test.

## Ownership and baseline

The implementer owns the three new runtime modules and contract reference. The
independent test author owns the three new test modules. A separate read-only
verifier supplies held-out probes. The coordinator owns kit state, release
registration, generated mirrors, full-suite verification and local synchronization.

The previous temporary CT1–CT3 verification directory had expired when this
continuation began. Its committed summaries/digests remain historical evidence;
the old raw logs are not claimed to be currently available. A new temporary
wrapper was created at `/private/tmp/poly-auto-ct4-checks-jxfg3r97/run.py` using
Python 3.12, explicit temporary homes/stores, client stubs, cleared environment,
the repository process runner, and a Python network audit guard. No whole-parent
OS confinement is claimed. Raw logs here are temporary too; durable results and
reviewed hashes will be recorded in this file before completion.

Before production code was created, the coordinator ran:

```bash
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct4-checks-jxfg3r97/run.py ct4-red -m unittest discover -s tests -p test_context_travel_query.py -v
```

Observed: one import error because context_travel_query.py did not exist, exit 1.
This establishes an absent feature entry point, not an exploit reproduction.
The executable kit's graph and static analysis passed with no findings under
the `ct4-kit-analysis` log label. Implementation and independent tests are complete.

## Findings during implementation

Independent path probes found NUL/control characters accepted in configured
roots, relative kit/graph/evidence paths and deny prefixes. The adapter now
rejects those before reading. Direct config objects enforce the same byte
ceiling as serialized startup config; unsupported roles refuse before source
reads. Empty/no-TASKS source selections remain valid partial-context requests.

Protocol review corrected initial version-negotiation behavior, unknown
notification replies, pre-initialization ping, and clientInfo/initialized
validation. The first unsupported-version test encoded the wrong expectation;
it was corrected against the pinned official specification rather than treating
the initial implementation as the oracle. Identifier credentials/controls are
refused without echo. Independent probes found no I/O in imported artifact
operations and no selected-source calls for structurally invalid live arguments.

Before the final freeze, integration review found a desktop usability gap: an
agent's first query required an already sealed CT1 request with precomputed
digest. A structured assignment form is therefore admitted, using only CT1's
existing make_request builder. Required identity remains explicit; unknown or
mixed forms still refuse before reads. Independent tests establish equivalence
with an already sealed request. This does not change CT1 or create another
identity authority.

The assignment regression was recorded before implementation as
`author-ct4-assignment-red.log`: the 16-test query selection had two expected
errors for the unsupported form. Both forms now match their sealed-request
equivalents. Adapter startup help was added to meet the repository interface
convention and is tested without config reads.

The final independent review reproduced a selected-reader OSError that would
terminate an MCP call without a correlated result. It now becomes a generic tool
error for that request; later ping still succeeds and the private exception text
is not emitted. Actual output-stream failures remain transport failures.
Malformed roots capability booleans also refuse. Other unused client capability
bodies are bounded opaque data, never requested or relied upon.

An exact-bound probe clarified budget scope: the configured ceiling bounds the
core query envelope. CLI's LF and MCP's response wrapper are framing and have a
separate 128 KiB ceiling. Both are now explicit in code and reference. No
criteria or caveat is trimmed to satisfy either ceiling.

Two test-author fixture corrections are distinguished from production defects:
patching os.open before a lazy helper import contaminated that helper's supported
operation detection, so the reader was warmed before the measured interval;
and the exact core-size fixture uses an immutable imported artifact to avoid
confounding live recomposition with framing. Final actual CLI/MCP entry-point
tests use the repository process runner, temporary config/home/data and bounded
stdio, with no installed model clients.

## Frozen targeted verification

The coordinator ran the exact admitted task checks with the temporary wrapper:

```bash
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct4-checks-jxfg3r97/run.py ct4-final-query -m unittest discover -s tests -p test_context_travel_query.py -v
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct4-checks-jxfg3r97/run.py ct4-final-cli -m unittest discover -s tests -p test_context_travel_cli.py -v
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct4-checks-jxfg3r97/run.py ct4-final-mcp -m unittest discover -s tests -p test_context_travel_mcp.py -v
```

Observed **18 query, 9 CLI and 21 MCP tests: all OK**, 48 total; all wrappers
exited 0 without timeout, truncation or leftovers. Independent verification
also passed 48 tests under reviewer-ct4-1/2/3. Held-out probes confirmed adapter
parity, assignment sealing, pre-read and imported-subject authorization,
artifact-only no-I/O, framing/lifecycle/error handling and the corrected paths.

Reviewed SHA-256 digests:

| File | Digest |
| --- | --- |
| `bin/context_travel_query.py` | `dcf4d604cfe74b96afe9b55bebdc392195cdbd68d92500aa5b385291536d46bc` |
| `bin/context_travel_cli.py` | `5371fc94eac79b9fa04ff7b11cf79276245b48359ea1a9ef69b2f9c0514c7f45` |
| `bin/context_travel_mcp.py` | `7d51e56e56339bc9a60565125723563de92a8f4d6d58d11136a3c87e8a1999d1` |
| `docs/CONTEXT-TRAVEL.md` | `f40203d4c6e857502181463cc45226a454467e565b989c735fdf79c5a18999a0` |
| `tests/test_context_travel_query.py` | `129255711275a3091f52e21de5760dfbbaa782defa5866527622a3efc175b6b5` |
| `tests/test_context_travel_cli.py` | `f01f23257d4aae144fec7260c897d8ebd0fb1ff2bbf0c680d73f63466ea3275b` |
| `tests/test_context_travel_mcp.py` | `fa0677b2e8848b88a0d8a3f8817f6ace3ade0328ba70e7cce3276a4a048da3be` |

CT1–CT3 runtime sources and tests have no diff from baseline. Release inventory
registers both new versions. The coordinator ran release_gate build, docs_build
build, copilot_docs build, then each check through the same wrapper, using
ct4-release-*, ct4-docs-* and ct4-copilot-docs-* log labels. All passed; two of
100 docs-site pages changed, and the Copilot generator produced no content diff.
The release check had no findings and retained the existing informational
package/plugin version note. This inventory check does not run live contracts.

## Full-suite acceptance

The first full-suite command was:

```bash
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct4-checks-jxfg3r97/run.py ct4-full-suite -m unittest discover -s tests -v
```

The outer sandbox was lifted for this authorized local command so fixture tests
can create their own execution boundary. Temporary homes/stores, stubbed clients,
cleared environment and the Python network guard remain in force. Source and
test files remained frozen throughout both full-suite runs.

The first full run completed **6,616 tests in 624.866 seconds with eight errors
and two skips**, exit 1. Every error came from the existing protected-profile
sentinel tests' loopback listener. The wrapper took 631.904 seconds without
timeout, truncation or leftovers. A bounded read-only diagnosis found the
recreated audit guard blocked
every socket bind, including the synthetic 127.0.0.1 listener constructed by
exec_policy's loopback control. This was a harness defect, not a CT4 source
change. The original harness remained unchanged for that run.

A separate run-loopback.py wrapper permits numeric loopback bind/connect and
lookup for synthetic fixtures while still denying external network and external
name lookup. No model/provider service is involved. Under that wrapper,
ct4-boundary-control passed **59 tests in 8.601 seconds**, exit 0, without timeout,
truncation or leftovers. A full rerun was required; this control alone was not
full-suite acceptance. Both the failed run and corrected control are retained
separately, and no product execution boundary was relaxed.

The corrected complete run uses the same frozen product/test files:

```bash
/opt/homebrew/bin/python3.12 -B /private/tmp/poly-auto-ct4-checks-jxfg3r97/run-loopback.py ct4-full-suite-corrected -m unittest discover -s tests -v
```

It passed **6,616 tests in 628.690 seconds**, with **two skips and no failures or
errors**. The wrapper exited 0 after 635.934 seconds without timeout, truncation
or leftover processes. This is the accepted full-suite result. No product or test
changes were made between the failed and corrected runs. CT4 is complete within
its offline scope; installed clients, providers and savings remain unverified.

A separate synthetic audit-event control rejected external
bind/connect/send and name lookup while permitting numeric loopback; it attempted
no network operation (`ct4-guard-control`, exit 0).

## Public parity requirement

[PUBLIC-PARITY.md](PUBLIC-PARITY.md) records the local drift assessment and the
reviewed synchronization gates. Exact tracked-content parity is required; repo
visibility, credentials/settings and available GitHub features remain separate.
The user selected CT4 completion first, then isolated local synchronization.
Final independent acceptance review confirmed all seven frozen hashes and the
corrected full-suite summary. The final executable-kit graph and static analysis
also returned no findings (`ct4-final-kit`, exit 0).
