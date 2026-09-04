# context-weight — five practices, each tied to a metric this tool reports

Read this when the user asks "so what do I actually change." Moved here verbatim from
`SKILL.md` — see that file for the three levers these practices instantiate and the
priority order between them.

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
   compact` above 60%). See "Checkpoint before compacting" in `SKILL.md` for what to do at that
   top band. Commands: `python3 bin/context_weight.py session --harness claude` and
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
