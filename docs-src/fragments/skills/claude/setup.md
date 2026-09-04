### What it does

Installs a statusline into your Claude Code settings that shows, at a glance, which model
you're on, roughly what the session has cost so far, how full the context window is, and —
on subscription sessions — how much of your 5-hour and 7-day rate-limit windows you've
burned. A separate, optional step can also install a hook that blocks a kit task from being
marked done without a genuine verify pass.

### When to reach for it

- You want the model, cost, and context usage visible without asking for them.
- You're running kits and want a marker-backed guarantee that `done` means verified.
- After noticing the statusline is missing, wrong, or showing another tool's format.
- **Not** something this skill bundles together — the hook is a separate opt-in, offered
  only after the statusline step, never installed alongside it by default.

### Worked example

```bash
echo '{"model":{"id":"...","display_name":"..."},"cost":{"total_cost_usd":0},
"context_window":{"used_percentage":0},
"rate_limits":{"five_hour":{"used_percentage":0},"seven_day":{"used_percentage":0}}}' \
  | python3 <abs-path>/statusline.py
```

Confirms the script runs before touching settings. The written command is always a literal
absolute path, never `${CLAUDE_PLUGIN_ROOT}` — that variable doesn't exist once the
statusline runs outside plugin context. Nothing is written until you confirm the exact
block shown; an existing `statusLine` key is flagged and replaced only with your go-ahead.

### Failure modes & fallbacks

- **The statusline doesn't appear.** It only shows after a restart or new session — say so
  up front rather than let the user assume the write failed.
- **The hook seems inactive.** Hook configuration also loads at session start; `claude
  --debug` is how registration is confirmed.
- **A `done` flip via the `Write` tool isn't blocked.** The hook fires only on `Edit` —
  Claude Code's `Write` payload carries no old content to compare, so this is a silent
  no-op, not a bypass to fix. Read `references/kit-verify-hook.md` before explaining what
  the marker does and doesn't prove.

### Cost & safety

This is the one skill in the roster that writes user-level settings, so every step gets
explicit confirmation before it writes — shown as an exact block first, applied only after
you agree, and merged so other keys in the file survive untouched. The rendered cost figure
is a client-side estimate, never a bill; rate-limit fields render only on subscription
sessions.

### Related

- [update](update.md) — checks and refreshes what's installed across every harness, not
  just this statusline.
- [cost-report](cost-report.md) — the fuller spend analysis behind the number this
  statusline shows live.
- [Deep dive: how it works](../../deep-dives/how-it-works.md) — where the statusline's
  numbers come from.
