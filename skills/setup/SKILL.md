---
name: setup
description: Install the polytropos statusline (current model, live session cost, context usage, rate-limit burn) into the user's Claude Code settings. Use when the user asks to set up or enable the cost statusline.
allowed-tools: Bash, Read, Edit, Write, AskUserQuestion
---

# Statusline setup

Wire `bin/statusline.py` (in this plugin) into the user's `~/.claude/settings.json` as the `statusLine` command. This edits user-level settings, so get explicit confirmation before writing.

## Steps

1. Resolve `<abs-path>` — the absolute path to this plugin's `bin` directory — from
   `${CLAUDE_PLUGIN_ROOT}/bin`, the env var Claude Code sets for plugin-executed content; if it is
   unset, fall back to resolving `../../bin` relative to this SKILL.md to an absolute path. Verify
   the script exists and runs:
   ```bash
   echo '{"model":{"id":"claude-fable-5","display_name":"Fable 5"},"cost":{"total_cost_usd":1.23},"context_window":{"used_percentage":42},"rate_limits":{"five_hour":{"used_percentage":12},"seven_day":{"used_percentage":34}}}' | python3 <abs-path>/statusline.py
   ```
   Expected output shape: model | cost | ctx | `5h 12% · 7d 34%` — this exercises the rate-limit
   rendering the skill's description promises.
2. Read `~/.claude/settings.json`. If a `statusLine` key already exists, show the user their current value and warn that proceeding replaces it.
3. Show the exact block to be added and ask for confirmation. The command written into
   `~/.claude/settings.json` must be a literal absolute path — never `${CLAUDE_PLUGIN_ROOT}` —
   because this statusline command runs outside plugin context, where that variable is not set:
   ```json
   "statusLine": {
     "type": "command",
     "command": "python3 <abs-path>/statusline.py"
   }
   ```
4. Only after the user confirms: apply the edit, preserving all other keys in the file.
5. Tell the user the statusline appears after a restart (or new session), and what the fields mean: model (color-coded — red = Fable tier, yellow = Opus tier), estimated session cost, context %, and 5h/7d rate-limit % (subscription sessions only; the cost figure is a client-side estimate, not a bill).

## Optional: kit verify-pass enforcement hook (separate opt-in — never bundled with the statusline step)

`bin/kit_verify_hook.py hook` is a PostToolUse command hook that blocks a `.claude/kits/<slug>/TASKS.md` task's `- status:` line from being edited to `done` unless a verify-pass marker already exists for that task (PLAN D3/D10 of the graph-convergence kit — the marker is written only by `bin/kit_verify_hook.py record`, itself called only from the actual verify path). It never dispatches a real `claude`/`copilot`/`codex` CLI, never writes outside the kit-local, gitignored `.claude/kits/<slug>/verify-pass/` directory, and this skill NEVER installs it without an explicit, separate confirmation from the statusline step above.

1. Resolve `<abs-path>` the same way as the statusline step (`${CLAUDE_PLUGIN_ROOT}/bin`, falling back to `../../bin` relative to this SKILL.md, resolved to an absolute path). Verify the script loads:
   ```bash
   python3 <abs-path>/kit_verify_hook.py --help
   ```
2. Read `~/.claude/settings.json`. If a `hooks.PostToolUse` array already exists, show the user its current matcher groups and explain that this step ADDS a new matcher group to that array rather than replacing anything.
3. Show the exact block to be added and ask for confirmation. As with the statusline command, the command written into `~/.claude/settings.json` must be a literal absolute path — never `${CLAUDE_PLUGIN_ROOT}` — because it runs outside plugin context:
   ```json
   {
     "hooks": {
       "PostToolUse": [
         {
           "matcher": "Edit",
           "hooks": [
             {
               "type": "command",
               "command": "python3 <abs-path>/kit_verify_hook.py hook"
             }
           ]
         }
       ]
     }
   }
   ```
   Merge this matcher group into any existing `hooks` object; preserve every other event, matcher, and top-level key already present in the file.
4. Only after the user confirms: apply the edit.
5. Tell the user precisely what this does and does not cover: it fires only on the `Edit` tool — the tool this repo's own skills and drivers actually use to flip a single `- status:` line — and is a silent no-op on every other file, tool, or edit. A full-file `Write` rewrite of a kit TASKS.md is NOT diff-checked, because Claude Code's PostToolUse payload for `Write` carries only the new file content, never the old (confirmed against `https://code.claude.com/docs/en/hooks`, "PostToolUse input"); a `done` flip performed via `Write` instead of `Edit` is therefore NOT enforced by this hook — it is a silent no-op, not a block. Hook configuration is loaded at session start — changes require restarting Claude Code (`claude --debug` to confirm registration).

   What the marker DOES and DOES NOT prove, on the Edit path it does cover: a marker is written only by `record`, and `precheck` (run at the start of every attempt) deletes any existing marker for that task id before it does anything else — so a marker's mere existence already means "`record` ran after the most recent `precheck`", not just "a pass happened at some point in this kit's history." A task flipped `done` → `in-progress` → `done` again cannot ride the original marker: the second attempt's `precheck` erases it, and the second `done` flip needs its own fresh `record`. The marker also stores the exact verify-command text `record` certified, and the hook compares that text against the task's CURRENT verify command in TASKS.md at flip time — if the verify command was rewritten after the marker was earned, the flip is blocked even though a marker still exists. That comparison reads both dialects kits are written in (a single-line ``- Verify: `cmd``` field, or a `**Verify.**`/`**Verify:**` marker followed by a fenced block), so it binds on the kit formats this repo actually executes. What it still cannot prove: that the recorded pass came from a genuine run of the command against the real post-implementation tree rather than a hand-crafted `record` call; anything about a status flip made outside the Edit tool (per the Write-tool gap above); and, in a kit whose task blocks write the verify command some third way that neither dialect parses, the command-match half specifically is skipped — marker existence plus `precheck` freshness still apply, but a rewritten verify command would not be caught.
