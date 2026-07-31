#!/usr/bin/env python3
"""Claude Code statusline: model | effort | cost·tokens | context% | rate-limit burn | subagents.

Reads the statusline JSON from stdin and prints one or two ANSI-colored lines. The second line
(Fable subagent token/cost usage today) is emitted only for real sessions — payloads that carry a
`session_id`; test/sample payloads omit it and render a single line.

State (running-subagent count, Fable-active flag, daily Fable tally) is written by agent_tracker.py
hooks under ~/.claude/polytropos/state/ and is GLOBAL, not per-session: Claude Code hands the
statusline, the subagent hooks, and SessionStart three different session ids, so per-session keying
can never line up.

T11 (PLAN D11) adds an optional, compact escalation-rate alarm segment. This script NEVER
computes that alarm itself -- it only READS the verdict bin/routing_scorecard.py's
``--history --snapshot --trend`` already persisted to
``<snapshot-dir>/alarm/state.json`` (see write_trend_alarm() there). This is deliberate:
a live cross-kit baseline parses every kit dir's whole NOTES.md (measured at ~3,775 lines
across 27 kits on this repo) against this script's ~15ms render budget, so the statusline
stays read-only over an already-computed, possibly-stale artifact and says nothing when
that artifact does not exist -- never recomputes, never fabricates, never touches
~/.claude for this.

Wire up via ~/.claude/settings.json:
  "statusLine": {"type": "command", "command": "python3 /path/to/statusline.py", "refreshInterval": 1}
"""

import json
import os
import sys
import time

RESET = "\033[0m"
DIM = "\033[2m"
AGENTS = "\033[1;35m"      # bold magenta — live subagent count
FABLE = "\033[1;31m"       # bold red — a Fable subagent is running now
FABLE_IDLE = "\033[2;31m"  # dim red — Fable usage tally when not actively running
ALARM = "\033[1;33m"       # bold yellow — a D11 escalation-rate alarm has tripped
TIER_COLORS = {
    "fable": "\033[31m",   # red — frontier pricing
    "mythos": "\033[31m",
    "opus": "\033[33m",    # yellow
    "sonnet": "\033[32m",  # green
    "haiku": "\033[36m",   # cyan
}

STATE = os.environ.get("POLYTROPOS_STATE_DIR") or os.path.expanduser("~/.claude/polytropos/state")

# T11 (PLAN D11): the SAME gitignored snapshot store bin/routing_scorecard.py already
# uses (its own DEFAULT_SNAPSHOT_DIR is <repo root>/trends) -- computed the same way
# (relative to this script's own location, never a home dir), with a test-only override
# mirroring POLYTROPOS_STATE_DIR above so no test here ever needs the real store.
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT_DIR = os.environ.get("POLYTROPOS_SNAPSHOT_DIR") or os.path.join(PLUGIN_ROOT, "trends")


def pct_color(p):
    if p >= 80:
        return "\033[31m"
    if p >= 60:
        return "\033[33m"
    return "\033[32m"


def fmt_tokens(n):
    n = int(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def read_agent_count():
    """Global live running-subagent count, maintained by agent_tracker.py hooks."""
    try:
        with open(os.path.join(STATE, "agents.count")) as f:
            return max(0, int(f.read().strip() or 0))
    except Exception:
        return 0


def fable_active():
    """True while a Fable subagent is running (global flag set by agent_tracker.py)."""
    return os.path.exists(os.path.join(STATE, "fable-active.flag"))


def read_fable_usage():
    """Today's Fable subagent tally: dispatch count, work tokens (in+out), priced cost."""
    try:
        with open(os.path.join(STATE, f"fable-usage-{time.strftime('%Y-%m-%d')}.json")) as f:
            d = json.load(f)
    except Exception:
        d = {}
    return {
        "dispatches": int(d.get("dispatches", 0) or 0),
        "tok": int((d.get("in", 0) or 0) + (d.get("out", 0) or 0)),
        "cost": float(d.get("cost", 0.0) or 0.0),
    }


def read_escalation_alarm():
    """PLAN D11: READ (never compute) the escalation-rate alarm bin/routing_scorecard.py
    last persisted to ``<SNAPSHOT_DIR>/alarm/state.json`` via its ``write_trend_alarm``
    (only written from ``--history --snapshot --trend`` — see that function). Absent
    store, absent file, malformed JSON, an un-evaluated verdict (insufficient history),
    or zero tripped kits all degrade to ``None`` -- rendering NOTHING, never a fabricated
    or stale-looking alarm (mirrors the telemetry-store "readers degrade when the store
    is absent" precedent). The verdict is only as fresh as the last snapshot; callers
    must show its date rather than imply live measurement.
    """
    path = os.path.join(SNAPSHOT_DIR, "alarm", "state.json")
    try:
        with open(path) as f:
            alarm = json.load(f)
    except Exception:
        return None
    if not isinstance(alarm, dict) or not alarm.get("evaluated"):
        return None
    tripped = alarm.get("tripped") or []
    if not tripped:
        return None
    top = tripped[0] if isinstance(tripped[0], dict) else {}
    rate = top.get("rate")
    return {
        "kit": top.get("kit") or "?",
        "rate": rate if isinstance(rate, (int, float)) else None,
        "extra": max(0, len(tripped) - 1),
        "date": alarm.get("latest_date") or "?",
    }


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print("polytropos: no status data")
        return

    parts = []

    model = data.get("model") or {}
    model_id = (model.get("id") or "").lower()
    name = model.get("display_name") or model.get("id") or "?"
    color = next((c for t, c in TIER_COLORS.items() if t in model_id), "")
    parts.append(f"{color}⬢ {name}{RESET}")

    effort = (data.get("effort") or {}).get("level")
    if effort:
        parts.append(f"{DIM}{effort}{RESET}")

    cw = data.get("context_window") or {}
    cost = (data.get("cost") or {}).get("total_cost_usd")
    tin = cw.get("total_input_tokens")
    tout = cw.get("total_output_tokens")
    costing = []
    if isinstance(cost, (int, float)):
        costing.append(f"${cost:,.2f}")
    if isinstance(tin, (int, float)) or isinstance(tout, (int, float)):
        costing.append(f"{fmt_tokens((tin or 0) + (tout or 0))} tok")
    if costing:
        parts.append(" · ".join(costing))

    ctx = cw.get("used_percentage")
    if isinstance(ctx, (int, float)):
        parts.append(f"ctx {pct_color(ctx)}{ctx:.0f}%{RESET}")

    limits = data.get("rate_limits") or {}
    burn = []
    for label, key in (("5h", "five_hour"), ("7d", "seven_day")):
        p = (limits.get(key) or {}).get("used_percentage")
        if isinstance(p, (int, float)):
            burn.append(f"{label} {pct_color(p)}{p:.0f}%{RESET}")
    if burn:
        parts.append(" · ".join(burn))

    # Live subagent + Fable-usage + escalation-alarm segments show only for real sessions.
    # Test/sample payloads omit session_id, and the GLOBAL counts must not leak into their
    # deterministic single-line output.
    if data.get("session_id"):
        count = read_agent_count()
        if count > 0:
            parts.append(f"{AGENTS}⚡ {count} agent{'s' if count != 1 else ''}{RESET}")
        fu = read_fable_usage()
        fcolor = FABLE if (fable_active() and count > 0) else FABLE_IDLE
        parts.append(f"{fcolor}🔥 Fable ×{fu['dispatches']}{RESET}")
        # T11 (PLAN D11): compact, and only when a stored alarm is actually tripped —
        # read_escalation_alarm() already returns None for "no store"/"insufficient
        # history"/"nothing tripped", so no separate gate is needed here. The date makes
        # this a snapshot, not a live claim.
        alarm = read_escalation_alarm()
        if alarm:
            rate = f"{alarm['rate'] * 100:.0f}%" if alarm["rate"] is not None else "?"
            extra = f" +{alarm['extra']}" if alarm["extra"] else ""
            parts.append(f"{ALARM}⚠ esc {alarm['kit']} {rate}{extra} "
                        f"(as of {alarm['date']}){RESET}")
        print(" | ".join(parts))
        print(f"{FABLE_IDLE}   ↳ Fable today: {fmt_tokens(fu['tok'])} tok · ${fu['cost']:,.2f}{RESET}")
    else:
        print(" | ".join(parts))


if __name__ == "__main__":
    main()
