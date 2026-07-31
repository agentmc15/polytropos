# Context weight

`bin/context_weight.py` measures what actually fills the context window on each API call,
across Claude Code, Codex CLI, and Copilot CLI — and, separately, audits the resident config
surfaces each harness always loads. See `skills/context-weight/SKILL.md` for the practices this
tool's numbers point to; this doc covers what the tool measures, at what fidelity, and why.

## The reframe

A high cache-read total is usually the cache working correctly, not a misconfiguration — reading
tokens from cache is cheap relative to resubmitting them uncached. The real cost driver is
**resident context × number of API calls**: every call resubmits the whole accumulated window,
so a large working set carried across many calls is what drives spend, not the cache mechanism
itself. This tool exists to measure that working set directly, per call, per harness — and its
`audit` subcommand exists specifically to stop config-file trimming from being mistaken for the
fix, by showing how small config surfaces usually are next to the real working set.

## What's measured, per harness — the fidelity ladder (D3)

The three harnesses do not log the same things, so this tool never fabricates a number a
harness's own logs don't carry. Each gets its own fidelity, stated plainly rather than padded
to look uniform:

| Harness | Per-call weight | Growth curve | Content attribution | Compaction detection | Delegation split |
|---|---|---|---|---|---|
| **Claude** | full (`input + cache_read + cache_write`) | real, per call | ranked contributors (D4) | inferred (D6) | sidechain vs main (D7) |
| **Codex** | per-turn where per-turn usage containers exist | real per-turn curve, or `cumulative snapshots` where only `total_token_usage` exists (labeled) | not possible — usage containers carry token counts only, no content; a labeled byte-share by rollout record type stands in | not attempted | not applicable |
| **Copilot** | not computable per call | **none** — events never record a per-turn input/cache split | not possible | not attempted | not applicable |

Two verbatim lines this tool prints as a direct consequence of the ladder, never omitted or
paraphrased away:

- Codex: `provenance not recorded in these logs — byte-share of rollout record types shown as a labeled estimate`
- Copilot: `growth curve: not available — Copilot events do not record per-turn input/cache token splits`

Copilot's card instead reports a **session-average weight**:
`(input + cache_read + cache_write) / assistant turns` — an honest single number in place of a
curve that cannot be computed from what Copilot logs.

## Claude attribution — method and limits (D4, corrected by T13)

For Claude sessions, `session` doesn't just report growth — it explains what grew the window.

**Mechanism:** every assistant `tool_use` block is linked to the tool name and a salient piece
of its input (a file path for `Read`/`Edit`/`Write`, the first ~60 characters of a `Bash`
command, the first ~60 characters of an `Agent` prompt). Each following `tool_result`, each
plain user text block, and each `attachment` record is sized by its serialized character length
and converted to an estimated token count at `chars / 4`. These estimates are ranked and grouped
by tool name (and by file path within `Read`), each row labeled `est.`.

**Reconciliation:** the sum of attributed estimates is compared against the session's measured
window growth. Two things happen with the gap:

- **Assistant output is measured, not estimated.** Every assistant reply — its text, its
  thinking, and the JSON of any tool calls it makes — is resubmitted on the next call, so it is
  real growth, and it is already an exact count: the transcript's own `output_tokens`. This shows
  up as its own row, `assistant output (measured)`, labeled `measured`, ranked inline by size
  alongside the `est.` rows rather than appended after them, and subtracted from the remainder
  before that remainder is computed.
- **What's left is `unattributed growth`.** This is genuinely not measurable from the transcript
  — system overhead and tool schemas are not recorded anywhere in it. It is printed as its own
  row rather than silently distributed across the other rows to make the table look complete.

An earlier draft of this project's plan described the unattributed gap as "system overhead,
thinking, schemas — not measurable from the transcript." That was wrong about thinking: thinking
lives inside assistant output and is recorded exactly as `output_tokens`. The corrected line, as
printed by the tool today, is:

> system overhead and tool schemas are not measurable from the transcript; assistant output
> (including thinking) is measured exactly and shown above.

On real sessions this correction moved the majority of what had been misclassified as
"unattributed" into the measured `assistant output` row — for example, from 66.3% unknown down
to 11.4% unknown on one stable session, and from 61.5% down to 26.3% on a large, still-growing
one.

**Limits:** attribution is Claude-only. Estimated figures are byte-derived, not exact
tokenization, so they are ranks and magnitudes — never priced, never merged with measured
tokens.

## Live threshold — `watch` (D15)

`watch` answers the question `session`/`overview` can't: not "what happened," but "where am I
right now, and what should I do about it." It reports the current call's weight as a percent of
the resolved context window (from `data/pricing.json`'s `context_window` for the current model —
never hardcoded), a `recommendation` banded on that percentage, and a three-way split of what's
currently in the window:

- **prunable** — tool results already acted on, superseded file reads (an earlier read of a path
  that was read again later), thinking from a completed step, oversized command output.
- **load-bearing** — unresolved error evidence, the most recent read of a still-relevant path, the
  first user message, and later messages carrying a decision/constraint marker.
- **unknown** — content the classifier can't confidently place either way (an honest third bucket,
  not forced into one side).

Every item in every bucket is labeled `est.` (byte-derived, `chars / 4`) and never priced, same as
the rest of this tool's estimated figures. `watch` never removes anything itself (D13) — it only
classifies what's already there; the classification is advisory, and the harness (`/compact`,
auto-compaction) is the only thing that can act on it.

Recommendation bands: below 40% of the window, `no action` (prevention is still free and there's
no urgency); 40-60%, `delegate new bulk reads, do not inline` (prevention still works but should
start now); above 60%, `checkpoint decisions to disk, then compact` (see
`skills/context-weight/SKILL.md`'s "Checkpoint before compacting" for what that means in practice).

`watch` is Claude-only by design — Codex has no per-call provenance and Copilot has no growth
curve (D3), so neither can support a live threshold. `watch codex` and `watch copilot` print the
verbatim line `watch: Claude sessions only — Codex has no per-call provenance and Copilot has no
growth curve (see audit/session for their honest fidelity)` and exit 0, rather than fabricating a
number those harnesses' logs can't support.

## Resident-surface audit (D10)

`audit` checks a fixed, per-harness lookup of the files each harness always loads, relative to
`--project DIR` (default `.`):

| Harness | Surfaces checked |
|---|---|
| Claude | `CLAUDE.md`, `CLAUDE.local.md`, `.claude/CLAUDE.md` |
| Codex | `AGENTS.md` |
| Copilot | `.github/copilot-instructions.md`, `AGENTS.md` |

`--surface PATH` (repeatable) adds project-specific extras. A missing surface is listed
`absent`, never an error. Each present surface reports bytes, an estimated token count
(`chars / 4`, labeled `est.`), and `% of budget` against `--budget-tokens` (default 5,000).
Each harness section totals its surfaces and adds a `per 100 calls: N tokens re-submitted
(est.)` line — the same small file, resubmitted every call, adds up over a session.

The audit shows **tokens only, never dollars** — its inputs are byte estimates, not measured
usage, and this tool never prices an estimated token.

It also always names what it *can't* measure: `system prompt, tool schemas, plugin skill
listings, MCP definitions — resident but not measurable here; measure their effect with the
session subcommand`.

And it always prints the reframe, unconditionally, at the top:

- With `--session <id>`: a computed percentage against that session's real measured avg weight —
  `resident surfaces ≈ N% of this session's avg per-call weight (X of Y tokens) — the working
  set, not config, is the lever.`
- Without a session (the common, bare-run case): a qualitative version of the same statement,
  naming the lever without inventing a number — `resident surfaces are typically a low
  single-digit % of per-call weight — the working set, not config, is the lever. Run with
  --session <id> to compute this against a real session.`

## `demo` — the pinned regression reference

`python3 bin/context_weight.py demo` builds synthetic fixtures for all three harnesses plus an
audited project, entirely inside one throwaway temp directory, and prints all four cards. These
numbers are hand-derivable from the fixtures and are this tool's standing regression check — if
`demo`'s output ever disagrees with the table below, that's a defect to fix in the code, not a
number to re-pin quietly.

**Claude** (`demo-claude`): 4 main calls, weights `10,000 / 20,000 / 30,000 / 8,000`, avg
`17,000`, peak `30,000`, total submitted `68,000`; one inferred compaction (`30,000 → 8,000`);
sidechain line `1 call(s), 5,000 tokens (7% of session mass)`. Attribution, ranked by magnitude:
`unattributed growth 12,250 est.`, then `Bash` (`ls -la`) `5,000 est.`, then `Read`
(`/workspace/demo.txt`) `2,000 est.`, then `assistant output (measured) 750 measured`.

**Codex** (`rollout-demo`): 3 per-turn calls, weights `3,000 / 8,000 / 13,000`, avg `8,000`; the
verbatim no-provenance line present.

**Copilot** (`demo-copilot-sess`): 2 assistant turns, session-average weight `21,000`
(`= (10,000 + 30,000 + 2,000) / 2`); the verbatim no-curve line present.

**Audit** (synthetic project): `CLAUDE.md` 2,000 chars → `500` est. tokens (10% of a 5,000-token
budget); `AGENTS.md` 1,200 chars → `300` est. tokens (6%); `.github/copilot-instructions.md`
800 chars → `200` est. tokens (4%).

`demo --json` round-trips through `json.loads` — every figure above is also reachable as a JSON
field for scripting.
