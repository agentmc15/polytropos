#!/usr/bin/env python3
"""polytropos hook: track running subagents + Fable subagent token/cost usage.

Registered in ~/.claude/settings.json against several hook events; dispatches on the
`hook_event_name` field of the JSON delivered on stdin:

  SessionStart   -> reset the live running-subagent count to 0, clear the Fable-active flag
  SubagentStart  -> +1 to the live running-subagent count
  SubagentStop   -> reconcile the live count from the authoritative `background_tasks` list,
                    and (once per agent_id) parse the finished subagent's transcript; if it used
                    Fable, add its tokens+cost to today's running Fable tally
  PreToolUse     -> if it's an `Agent` spawn with model 'fable': log it, set the Fable-active flag,
                    and bump today's Fable dispatch count

State lives under ~/.claude/polytropos/state/ and is read back by statusline.py. Counts are
GLOBAL (not per-session): Claude Code hands the statusline, the subagent hooks, and SessionStart
three different session ids, so per-session keying can never match. All work is best-effort — this
script must NEVER disrupt the session, so every path is guarded and it always exits 0.
"""

import fcntl
import json
import os
import subprocess
import sys
import time

STATE_DIR = os.environ.get("POLYTROPOS_STATE_DIR") or os.path.expanduser("~/.claude/polytropos/state")
LOG_PATH = os.path.expanduser("~/.claude/polytropos/fable-invocations.log")
NOTIFY_FLAG = os.path.expanduser("~/.claude/polytropos/notify-fable")
AGENTS_COUNT = os.path.join(STATE_DIR, "agents.count")          # global live running-subagent count
FABLE_FLAG = os.path.join(STATE_DIR, "fable-active.flag")       # global: a Fable subagent is running
PRICING_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "pricing.json")


def _today():
    return time.strftime("%Y-%m-%d")


def fable_usage_path():
    # Daily rolling Fable tally: dispatches + token components + cost. Resets by date (no event needed).
    return os.path.join(STATE_DIR, f"fable-usage-{_today()}.json")


def processed_path():
    return os.path.join(STATE_DIR, f"fable-processed-{_today()}.txt")


# ---- primitive: atomic integer counter file --------------------------------------------------

def _read_int(path):
    try:
        with open(path) as f:
            return max(0, int(f.read().strip() or 0))
    except Exception:
        return 0


def set_count(n):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(AGENTS_COUNT, "w") as f:
        f.write(str(max(0, int(n))))


def bump_count(delta):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(AGENTS_COUNT, "a+") as fd:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            fd.seek(0)
            try:
                n = int(fd.read().strip())
            except ValueError:
                n = 0
            n = max(0, n + delta)
            fd.seek(0)
            fd.truncate()
            fd.write(str(n))
            fd.flush()
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)


# ---- Fable-active flag -----------------------------------------------------------------------

def set_fable_flag():
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(FABLE_FLAG, "w") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S"))


def clear_fable_flag():
    try:
        os.remove(FABLE_FLAG)
    except FileNotFoundError:
        pass


# ---- Fable usage tally (daily) ---------------------------------------------------------------

def _load_pricing():
    try:
        with open(PRICING_PATH) as f:
            return json.load(f)
    except Exception:
        return None


def _fable_cost(tok, pricing):
    """Price Fable tokens from pricing.json — never hardcode rates (single source of truth)."""
    if not pricing:
        return 0.0
    m = (pricing.get("models") or {}).get("claude-fable-5") or {}
    inp = m.get("input_per_mtok", 0) or 0
    outp = m.get("output_per_mtok", 0) or 0
    cr = pricing.get("cache_read_multiplier", 0.1)
    cw = pricing.get("cache_write_multiplier_5m", 1.25)
    return (tok["in"] * inp + tok["out"] * outp
            + tok["cache_read"] * inp * cr + tok["cache_write"] * inp * cw) / 1_000_000


def _fable_tokens_in_transcript(path):
    """Sum token usage attributed to a Fable model across a subagent transcript. None if no Fable."""
    tot = {"in": 0, "out": 0, "cache_read": 0, "cache_write": 0}
    found = False
    try:
        with open(path) as f:
            for line in f:
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                msg = o.get("message") or {}
                u = msg.get("usage") or o.get("usage") or {}
                mid = str(msg.get("model") or o.get("model") or "")
                if u and "fable" in mid.lower():
                    found = True
                    tot["in"] += u.get("input_tokens", 0) or 0
                    tot["out"] += u.get("output_tokens", 0) or 0
                    tot["cache_read"] += u.get("cache_read_input_tokens", 0) or 0
                    tot["cache_write"] += u.get("cache_creation_input_tokens", 0) or 0
    except Exception:
        return None
    return tot if found else None


def _load_usage():
    try:
        with open(fable_usage_path()) as f:
            d = json.load(f)
    except Exception:
        d = {}
    for k in ("dispatches", "in", "out", "cache_read", "cache_write"):
        d.setdefault(k, 0)
    d.setdefault("cost", 0.0)
    return d


def _save_usage(d):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(fable_usage_path(), "w") as f:
        json.dump(d, f)


def bump_dispatch():
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(fable_usage_path() + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            d = _load_usage()
            d["dispatches"] += 1
            _save_usage(d)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _already_processed(agent_id):
    if not agent_id:
        return True
    try:
        with open(processed_path()) as f:
            return agent_id in f.read().split()
    except Exception:
        return False


def _mark_processed(agent_id):
    if not agent_id:
        return
    with open(processed_path(), "a") as f:
        f.write(agent_id + "\n")


def accumulate_fable(agent_id, transcript_path):
    """Once per agent_id, add a finished Fable subagent's tokens+cost to today's tally."""
    if not transcript_path or not os.path.exists(transcript_path):
        return
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(fable_usage_path() + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            if _already_processed(agent_id):
                return
            tok = _fable_tokens_in_transcript(transcript_path)
            _mark_processed(agent_id)  # mark even if non-Fable, so multi-fire won't re-parse
            if not tok:
                return
            d = _load_usage()
            for k in ("in", "out", "cache_read", "cache_write"):
                d[k] += tok[k]
            d["cost"] += _fable_cost(tok, _load_pricing())
            _save_usage(d)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


# ---- Fable invocation log --------------------------------------------------------------------

def log_fable(data):
    tool_input = data.get("tool_input") or {}
    if "fable" not in str(tool_input.get("model") or "").lower():
        return
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    label = tool_input.get("description") or tool_input.get("subagent_type") or "subagent"
    with open(LOG_PATH, "a") as f:
        f.write(f"[{ts}] Fable subagent launched: {label} (session {data.get('session_id') or '?'})\n")
    if os.path.exists(NOTIFY_FLAG):
        try:
            subprocess.Popen(
                ["osascript", "-e",
                 f'display notification "Fable subagent: {label}" with title "polytropos"'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass


# ---- helpers -----------------------------------------------------------------------------------

def running_count_from_background(data):
    """Authoritative live count from the `background_tasks` snapshot in a SubagentStop payload."""
    bt = data.get("background_tasks")
    if isinstance(bt, list):
        return sum(1 for t in bt if isinstance(t, dict)
                   and t.get("type") == "subagent" and t.get("status") == "running")
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    event = data.get("hook_event_name") or ""
    try:
        if event == "SessionStart":
            set_count(0)
            clear_fable_flag()
        elif event == "SubagentStart":
            bump_count(1)
        elif event == "SubagentStop":
            n = running_count_from_background(data)
            if n is not None:
                set_count(n)
                if n == 0:
                    clear_fable_flag()
            else:
                bump_count(-1)
                if _read_int(AGENTS_COUNT) == 0:
                    clear_fable_flag()
            accumulate_fable(data.get("agent_id"), data.get("agent_transcript_path"))
        elif event == "PreToolUse" and data.get("tool_name") == "Agent":
            log_fable(data)
            if "fable" in str((data.get("tool_input") or {}).get("model") or "").lower():
                set_fable_flag()
                bump_dispatch()
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
