# context-weight — what the columns mean

Read this when you must explain or defend a number in a `session` / `overview` card. Moved
here verbatim from `SKILL.md` — see that file for the commands that print these columns.

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
