---
name: context-weight
description: Reach for this when your context is huge, you're near 700K, cache reads are high, or you're asking should I compact — it explains what this skill can and cannot do, ranks prevent/prune/measure in priority order, and gives the checkpoint move before you compact.
allowed-tools: Bash, Read
---

# Context weight

## What this skill cannot do

This skill cannot remove anything from your context window. Skills and agents are text loaded
INTO the window — read-only instructions the model follows — they have no mechanism to mutate the
message array a call submits. Only the harness can do that: `/compact`, auto-compaction, and, for
API callers, context editing (`clear_tool_uses_20250919`, `clear_thinking_20251015`). This skill's
job is to tell you *when* to act and *what* to act on; the harness is the thing that actually acts.
If you install this skill expecting your context to start shrinking on its own, nothing will
happen — that expectation is the single most likely misreading of this whole kit, and everything
below only works once it's corrected.

That limit applies to this kit's own tooling too, honestly stated rather than hidden: measuring
context has mass. `bin/context_weight.py` itself is tens of thousands of estimated tokens
(`wc -c bin/context_weight.py`, chars/4 — check it yourself, the number drifts as the engine
grows). The reason that doesn't defeat the point is the distinction between **on-demand** and
**resident**: the engine and its tests are read on demand — only when you or a subagent actually
runs them — and cost nothing the rest of the time. Only this SKILL.md's frontmatter `description`
sits in the always-loaded skill listing, resident on every single call whether you use it or not.
That is exactly why its rewrite (below, and in the frontmatter above) had to earn its keep with a
trigger a reader would actually type, not a feature summary.

## The reframe

Cache reads showing up as the biggest line item is usually the cache working correctly, not
a misconfiguration — reading previously-seen tokens from cache is far cheaper than resubmitting
them uncached, so a high cache-read total is the cheap path doing its job. The actual cost
driver is **resident context × number of API calls**: every call in a session resubmits the
whole accumulated window, so a large working set repeated over many calls is what drives spend
up, not the cache mechanism. Config surfaces (`CLAUDE.md`, `AGENTS.md`,
`copilot-instructions.md`) are usually a small fraction of that working set — measure with
`audit` before trimming one, because trimming a surface that is already proportionate moves
almost nothing.

## The three levers, in priority order

There are exactly three things you can do about context weight, and they are not
interchangeable — using them in the wrong order sends you to the lossy one first.

1. **PREVENT — free and lossless.** Delegate bulk reads to subagents that return conclusions
   instead of raw dumps, cap tool output before it enters the main window, defer loading a
   file/tool until it's actually needed, favor progressive disclosure over dumping everything
   up front. None of this mass ever enters the window, so there is nothing to lose later.
2. **PRUNE — cheap but lossy.** Compaction and, for API callers, context editing. This is the
   only lever of the three that can cost accuracy: it discards detail, and a summary is not the
   original. Use it, but pay it in full awareness of that cost (see the checkpoint move below).
3. **MEASURE — free.** Knowing when to act and what to act on — `session`, `overview`, `audit`,
   `watch`. Measurement doesn't change anything by itself; it's what tells you whether lever 1 or
   lever 2 is the right move right now.

**Why prevention wins:** a file never read costs nothing and loses nothing. A file that gets read
and later compacted costs three things — the read (tokens spent getting it in), the write (tokens
spent carrying it turn over turn until compaction), and the fidelity (the compacted summary is
lossy by construction). Prevention avoids all three; pruning only ever stops the second one, after
already paying the first.

**Why "just pull the relevant context" isn't a real option once the window is full:** every API
call submits the whole message array — there is no selective re-read of a window that's already
been filled, no way to retroactively un-submit the parts that turned out not to matter. The
retrieval-shaped answer — get only what's relevant — exists only *prospectively*, before the read
happens, and that's exactly what delegation is: a subagent does the wide read, off in its own
context, and returns only the conclusion.

Concrete illustration from a real session: `watch` reported `peak 99% of window (993,900 of
1,000,000 tokens)` with `avoidable (tool-ingested) mass: 74,160 est. of 993,900 (7%) — top source:
Bash`. That 7% is the honest size of the PREVENT opportunity on that session — the slice a capped
or delegated Bash call could have kept out entirely. It's deliberately not most of the window:
assistant output and user input make up the rest, and neither PREVENT nor PRUNE touches those —
which is the same reframe as above, restated at the lever level instead of the cache-read level.

## How to run it

Use the `${CLAUDE_PLUGIN_ROOT}` env var Claude Code sets for plugin-executed content; if it is
unset, fall back to resolving `../../bin/context_weight.py` relative to this SKILL.md to an
absolute path:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/context_weight.py" session   # this session's per-call weight, growth curve, ranked contributors
python3 "${CLAUDE_PLUGIN_ROOT}/bin/context_weight.py" overview  # cross-session working-set table, one section per harness
python3 "${CLAUDE_PLUGIN_ROOT}/bin/context_weight.py" audit     # resident-surface audit vs a token budget — tokens only, no dollars
python3 "${CLAUDE_PLUGIN_ROOT}/bin/context_weight.py" watch     # live: current % of window, and what's prunable vs load-bearing right now (Claude only)
python3 "${CLAUDE_PLUGIN_ROOT}/bin/context_weight.py" demo      # synthetic smoke across all five cards — no real data touched
```

All five take `--json` for machine-readable output. `session` and `overview` take
`--harness claude|codex|copilot` (default `claude`); each harness is reported at its own honest
fidelity, never at Claude's. `watch` has no `--harness` flag — it is Claude-only by design (see
the Codex/Copilot note at the end of the checkpoint section below); passing `codex` or `copilot`
as its positional argument prints an honest refusal line and exits 0 rather than fabricating a
number those harnesses' logs can't support.

What the columns mean:

- **weight** — `input + cache_read + cache_write` tokens submitted on that one API call (Claude,
  Codex). This is the full prompt actually sent; output tokens are excluded from weight because
  they are generation, not carried context.
- **est.** — a byte-derived estimate (`chars / 4`), used only where the transcript records
  content but not an exact token count (attribution rows, audit surface sizes, Codex's
  record-type byte-share). Estimates are ranks and magnitudes, never priced, and always labeled
  `est.` so they can't be mistaken for measured tokens.
- **measured** — an exact token count taken straight from the transcript's own usage numbers,
  never the byte heuristic. `assistant output (measured)` is the one attribution row that gets
  this label: assistant text, thinking, and tool-call JSON all live inside `output_tokens`, so
  it's counted exactly, not estimated.
- **inferred** — a compaction or clear point on the growth curve, detected as a ≥50% drop in
  weight from the previous call. No harness reliably marks compactions in every transcript, so
  this is inference from the observable signature (a sudden halving of submitted size), and the
  word `inferred` appears next to it rather than a claim of certainty.
- **session-average** — Copilot's only per-session weight figure:
  `(input + cache_read + cache_write) / assistant turns`. Copilot's logs never record a
  per-turn input/cache split, so no growth curve is possible for it — `session-average` is the
  honest substitute, not a curve in disguise.

## Five practices, each tied to a metric this tool reports

1. **Delegate bulk reads to subagents that return conclusions, not raw dumps.** Metric: the
   sidechain-vs-main split `session` prints — `Sidechain (subagents): N call(s), X tokens (Y%
   of session mass)`. That line is the payoff made visible: subagent context never enters the
   main window, so a bigger sidechain share alongside a lower main `avg weight` means delegation
   is working. Command: `python3 bin/context_weight.py session --harness claude`.

2. **Cap what tool output enters the main context.** Metric: the ranked "What filled the window
   (est.)" table `session` prints, grouped by tool name (and by file path for `Read`). Whatever
   sits at the top of that table — a Bash command's raw output, a large file Read in full — is
   the concrete thing to cap, truncate, or route through a subagent instead. Command:
   `python3 bin/context_weight.py session --harness claude --top 10`.

3. **Compact or clear when the growth curve stalls high or jumps.** Metric: `session`'s growth
   curve sparkline plus its inferred-compaction markers (a ≥50% drop between consecutive calls,
   reported as `call N: inferred compaction (before → after)`), or `watch`'s live
   `current weight X of a Y-token window (Z%)` plus its `recommendation` line (`no action` below
   40%, `delegate new bulk reads, do not inline` from 40-60%, `checkpoint decisions to disk, then
   compact` above 60%). See "Checkpoint before compacting" below for what to do at that top band.
   Commands: `python3 bin/context_weight.py session --harness claude` and
   `python3 bin/context_weight.py watch`.

4. **Prefer fewer, denser turns over many small ones.** Metric: `avg weight` × the call count is
   the `total submitted` figure `session` prints directly — that product is the total mass
   resubmitted across the session. `overview` shows the same three columns (`calls`,
   `avg weight`, `total submitted`) side by side across sessions, so a change in habit shows up
   as a lower `total submitted` at a comparable call count. Commands:
   `python3 bin/context_weight.py session --harness claude` and
   `python3 bin/context_weight.py overview --harness claude`.

5. **Keep resident config surfaces lean, but proportionate — don't chase them past where they
   matter.** Metric: `audit`'s per-surface `% of budget` column, and its reframe line. Run
   `audit --session <id>` to see the surfaces sized against that session's real
   `avg weight` (`resident surfaces ≈ N% of this session's avg per-call weight`); without
   `--session` it prints a qualitative version of the same reframe rather than a fabricated
   number. Config surfaces are typically a small fraction of the working set — the audit exists
   so a surface trim isn't mistaken for the fix when the working set is the actual lever.
   Command: `python3 bin/context_weight.py audit --session <id>`.

## Checkpoint before compacting

PRUNE is the only lever that costs accuracy (above), so protect against that cost before you pull
it: **write decisions, constraints, and open questions to a file — `NOTES.md`, `tasks/todo.md` —
before compaction runs**, not after. A compaction summary written after the fact can only
summarize what survived; a note written before it runs is an anchor the summary cannot lose, and
the full detail behind it stays re-readable on demand (open the file) even once the transcript
it came from has been folded away. This repo already does exactly this move at the kit level —
every `.claude/kits/<slug>/NOTES.md` is precisely "write it down before the context that produced
it goes away." Applying the same habit to a session, not just a kit, is the whole of this
practice.

Not everything in the window is equally safe to lose, and `watch` reports the split rather than
leaving it to guesswork:

- **Safe to drop:** tool results already acted on and summarized, a superseded file read (read
  v1 → edited → read v2 — only v2 still matters), thinking from a completed step, verbose output
  whose conclusion is already recorded elsewhere.
- **Dangerous to drop:** the original task statement, decisions and their rationale, anything
  that would have to be re-derived from scratch if lost, unresolved error evidence, and early
  constraints that still bind late (e.g. "never push to main").

Auto-compaction is a timer, not a policy — it cannot tell these two classes apart, which is
exactly why the checkpoint file matters: it's how the dangerous-to-drop class survives a lossy
step that has no way to distinguish it from the safe-to-drop class on its own. Command:
`python3 bin/context_weight.py watch` — its `recommendation` line turns to
`checkpoint decisions to disk, then compact` once the current call passes ~60% of the window, and
its safe/dangerous breakdown is printed alongside it, each item labeled `est.`.

**Codex and Copilot:** `watch` is Claude-only — Codex has no per-call provenance and Copilot has
no growth curve (D3), so neither can support a live threshold; `watch codex` / `watch copilot`
print an honest refusal rather than a fabricated one. There is no substitute live check for those
two harnesses — use `session` / `overview` after the fact (their own honest fidelity, per the
table above) and apply the same three levers and the same checkpoint-before-compacting habit
manually, on a schedule, instead of on a threshold.

## Honesty rules this tool holds, and this skill repeats

- Every estimated figure is labeled `est.`; it is a rank and a magnitude, never an exact token
  count, and it is never priced.
- Copilot never gets a growth curve — its logs carry no per-turn input/cache split, so `session`
  prints the verbatim line naming that instead of approximating one.
- Codex never gets content attribution — its usage containers carry token counts only, no
  content provenance, so `session` prints a labeled byte-share by record type and the verbatim
  line naming why, instead of a fabricated tool ranking.
- Dollar figures everywhere in this tool are API-equivalent estimates, not a bill — they price
  measured usage tokens (never estimated ones) through that harness's own pricing file, and each
  harness's dollars stay inside its own section. There is no cross-harness dollar total anywhere
  in this tool's output.
