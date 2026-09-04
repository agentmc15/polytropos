# setup — kit verify-pass hook: what a marker proves

Read this before explaining the verify-pass hook's guarantees to a user: what a marker proves,
what `precheck` freshness and the verify-command match add, and the three things it still
cannot prove. Moved here from `SKILL.md`, which keeps only the two facts a model must state at
install time (fires only on `Edit`; a `Write` flip is a silent no-op).

What the marker DOES and DOES NOT prove, on the Edit path it does cover: a marker is written only
by `record`, and `precheck` (run at the start of every attempt) deletes any existing marker for
that task id before it does anything else — so a marker's mere existence already means "`record`
ran after the most recent `precheck`", not just "a pass happened at some point in this kit's
history." A task flipped `done` → `in-progress` → `done` again cannot ride the original marker:
the second attempt's `precheck` erases it, and the second `done` flip needs its own fresh
`record`. The marker also stores the exact verify-command text `record` certified, and the hook
compares that text against the task's CURRENT verify command in TASKS.md at flip time — if the
verify command was rewritten after the marker was earned, the flip is blocked even though a
marker still exists. That comparison reads both dialects kits are written in (a single-line
``- Verify: `cmd``` field, or a `**Verify.**`/`**Verify:**` marker followed by a fenced block),
so it binds on the kit formats this repo actually executes. What it still cannot prove: that the
recorded pass came from a genuine run of the command against the real post-implementation tree
rather than a hand-crafted `record` call; anything about a status flip made outside the Edit tool
(per the Write-tool gap above); and, in a kit whose task blocks write the verify command some
third way that neither dialect parses, the command-match half specifically is skipped — marker
existence plus `precheck` freshness still apply, but a rewritten verify command would not be
caught.

The Write-tool gap itself — that Claude Code's PostToolUse payload for `Write` carries only the
new file content, never the old — is confirmed against `https://code.claude.com/docs/en/hooks`,
"PostToolUse input". Hook configuration is loaded at session start, so a restart (or new
session) is needed before a newly installed hook takes effect, the same as the statusline change.
