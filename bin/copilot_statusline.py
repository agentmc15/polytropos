#!/usr/bin/env python3
"""GitHub Copilot CLI statusline — the Copilot-side parity twin of bin/statusline.py.

Copilot CLI (added ~May 2026, modeled on Claude Code's statusline) can run a command
configured under ``~/.copilot/settings.json``::

    {
      "experimental": true,
      "statusLine": {"type": "command", "command": "python3 /abs/path/to/bin/copilot_statusline.py"}
    }

enabled via the ``/statusline`` slash command inside a session, followed by ``/restart``.
Copilot pipes a JSON payload to the command's stdin once per render; the command prints ONE
line to stdout. See docs/COPILOT-HARNESS.md for the install block and enablement steps.

A real payload has been captured (Copilot CLI v1.0.70) and the schema below is now PINNED to
it. Every field is still read DEFENSIVELY — no malformed/empty/partial payload can crash this
script, and each segment renders only when its own data is present — but the lookups now try
the REAL nested path first, falling back to the older top-level guesses only for tolerance
against future schema drift. Known keys, in lookup order:

  model             ``model.display_name`` (real) | top-level ``display_name`` | ``model`` (a
                     plain string)
  context %         ``context_window.current_context_used_percentage`` (real) |
                     ``context_window.used_percentage`` | derived from
                     ``context_window.current_context_tokens`` /
                     ``context_window.displayed_context_limit`` | derived from
                     ``context_window.total_tokens`` / ``context_window.context_window_size`` |
                     the older top-level equivalents
  session duration  ``cost.total_duration_ms`` (real) | top-level ``total_duration_ms``
  credits (AIC)     ``ai_used.total_nano_aiu`` / 1e9 (real; the nano scale is CONFIRMED — a
                     captured payload had ``total_nano_aiu=17682890000`` alongside
                     ``formatted="17.7"``, i.e. exactly nano/1e9) | the leading number parsed
                     out of ``ai_used.formatted`` as a fallback | top-level ``total_nano_aiu``
                     for older-schema tolerance
  cache/other       ``total_cache_read_tokens``, ``total_cache_write_tokens``,
                     ``total_premium_requests`` (top-level only; not yet pinned to a nested
                     path in the captured payload)

AIC -> USD is derived ONLY from ``data/pricing.copilot.json``'s ``billing_unit.usd_per_credit``
(never hardcoded here), loaded via the repo's ``_load`` importlib pattern (same convention as
``bin/routing_scorecard.py``) to reuse ``bin/copilot_pricing.py``'s ``load_pricing()`` — falling
back to reading the pricing file directly if that import ever fails. Since the nano scale is now
confirmed, the USD gloss is always shown when pricing data is available, labeled with the "AIC"
unit name and the ``~`` (approximate) prefix.

Use ``--capture <path>`` (writes the raw stdin payload verbatim to a file) or ``--debug`` (writes
it to stderr instead) to capture a real payload from a live Copilot session — both still print
the normal status line — so the schema above can be re-pinned if it ever drifts.

``--compact`` (alias ``--slim``): Copilot CLI's own built-in footer (enabled via
``showCustom: true`` alongside a custom ``statusLine`` command) already renders model, context
%, and ``Session: N AIC used`` — so running the full line above alongside it duplicates those
three segments. ``--compact`` makes this script contribute ONLY the value the built-in footer
doesn't have: the USD gloss on that AIC figure, plus session duration, e.g. ``~$0.18 · 25m45s``.
It reuses the exact same ``pick_aic``/``usd_per_credit``/``pick_duration_ms``/``fmt_duration``
helpers the full line uses — never a re-derivation. Degrades in place: duration-only when USD
isn't derivable, and an EMPTY line (never a placeholder) when neither is available, so the
custom widget contributes nothing rather than noise. The default (no ``--compact``) mode is
unchanged.
"""

import importlib.util
import json
import re
import sys
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent
PRICING_PATH = BIN_DIR.parent / "data" / "pricing.copilot.json"

FALLBACK_LINE = "polytropos: no copilot status data"

# Matches the leading number in a preformatted string like "23.4 AIC" or "1,234.5" — commas
# are stripped before float() so thousands-separated figures still parse.
_NUMERIC_RE = re.compile(r"[-+]?[\d,]*\.?\d+")


def _load(name):
    """Load a sibling ``bin/<name>.py`` module read-only (the session_cost.py /
    routing_scorecard.py ``_load`` convention). Never raises — callers get ``None`` on any
    failure so a broken/missing sibling module can never crash this statusline."""
    try:
        spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def load_pricing():
    """``data/pricing.copilot.json``, self-located from this file's own path — never via
    ``${CLAUDE_PLUGIN_ROOT}`` or cwd, since Copilot may run this command from anywhere.

    Prefers reusing ``bin/copilot_pricing.py``'s own ``load_pricing()`` (read-only reuse);
    falls back to reading the file directly. Returns ``None`` (never raises) if both fail —
    the credits segment simply omits its USD gloss in that case.
    """
    mod = _load("copilot_pricing")
    if mod is not None:
        try:
            return mod.load_pricing()
        except Exception:
            pass
    try:
        with open(PRICING_PATH) as f:
            return json.load(f)
    except Exception:
        return None


def usd_per_credit(pricing):
    try:
        v = (pricing or {}).get("billing_unit", {}).get("usd_per_credit")
        return float(v) if isinstance(v, (int, float)) else None
    except Exception:
        return None


def pick_model_name(data):
    """``model.id`` (the short model slug, e.g. ``claude-sonnet-5``) first, then
    ``model.display_name`` trimmed at the first `` · `` (Copilot appends
    `` · <effort> · <context>`` there), then the older top-level ``display_name`` guess
    (also trimmed), then a plain-string ``model`` value."""
    model = data.get("model")
    if isinstance(model, dict):
        v = model.get("id")
        if isinstance(v, str) and v.strip():
            return v.strip()
        v = model.get("display_name")
        if isinstance(v, str) and v.strip():
            return v.strip().split(" · ")[0].strip()
    v = data.get("display_name")
    if isinstance(v, str) and v.strip():
        return v.strip().split(" · ")[0].strip()
    if isinstance(model, str) and model.strip():
        return model.strip()
    return None


def pick_context_pct(data):
    """``context_window.current_context_used_percentage`` (the real nested path) first, then
    sibling nested fields/derivations, then the older top-level guesses as a last resort."""
    cw = data.get("context_window")
    if isinstance(cw, dict):
        v = cw.get("current_context_used_percentage")
        if isinstance(v, (int, float)):
            return float(v)
        v = cw.get("used_percentage")
        if isinstance(v, (int, float)):
            return float(v)
        tokens = cw.get("current_context_tokens")
        limit = cw.get("displayed_context_limit")
        if not isinstance(limit, (int, float)) or limit <= 0:
            limit = cw.get("context_window_size")
        if isinstance(tokens, (int, float)) and isinstance(limit, (int, float)) and limit > 0:
            return tokens / limit * 100
        tokens = cw.get("total_tokens")
        limit = cw.get("context_window_size")
        if isinstance(tokens, (int, float)) and isinstance(limit, (int, float)) and limit > 0:
            return tokens / limit * 100

    v = data.get("current_context_used_percentage")
    if isinstance(v, (int, float)):
        return float(v)
    tokens = data.get("current_context_tokens")
    limit = data.get("displayed_context_limit")
    if not isinstance(limit, (int, float)) or limit <= 0:
        limit = data.get("context_window_size")
    if isinstance(tokens, (int, float)) and isinstance(limit, (int, float)) and limit > 0:
        return tokens / limit * 100
    return None


def pick_duration_ms(data):
    """``cost.total_duration_ms`` (the real nested path) first, then the older top-level
    ``total_duration_ms`` guess."""
    cost = data.get("cost")
    if isinstance(cost, dict):
        v = cost.get("total_duration_ms")
        if isinstance(v, (int, float)):
            return v
    v = data.get("total_duration_ms")
    if isinstance(v, (int, float)):
        return v
    return None


def _parse_leading_number(s):
    if not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None
    m = _NUMERIC_RE.search(s)
    if not m:
        return None
    try:
        return float(m.group().replace(",", ""))
    except ValueError:
        return None


def pick_aic(data):
    """The AIC credit figure as a float, or ``None`` if it can't be reliably derived.

    Primary source is ``ai_used.total_nano_aiu / 1e9`` — the nano scale is confirmed (a
    captured payload had ``total_nano_aiu=17682890000`` alongside ``formatted="17.7"``, i.e.
    exactly nano/1e9). Falls back to the leading number in ``ai_used.formatted`` when
    ``total_nano_aiu`` is absent, then to a top-level ``total_nano_aiu`` for tolerance against
    an older/flatter schema. Never fabricates: if none of these yield a number, returns
    ``None``.
    """
    ai_used = data.get("ai_used")
    if isinstance(ai_used, dict):
        nano = ai_used.get("total_nano_aiu")
        if isinstance(nano, (int, float)):
            return nano / 1e9
        aic = _parse_leading_number(ai_used.get("formatted"))
        if aic is not None:
            return aic

    nano = data.get("total_nano_aiu")
    if isinstance(nano, (int, float)):
        return nano / 1e9

    return None


def credits_segment(data, pricing):
    """Display string for the credits segment, or ``None`` if no AIC figure is present.

    Always labeled with the "AIC" unit (``billing_unit.name`` in data/pricing.copilot.json).
    The USD gloss (``AIC * usd_per_credit``) is shown whenever pricing data is available;
    it's omitted (but the AIC figure still shown) only if the pricing file can't be loaded.
    """
    aic = pick_aic(data)
    if aic is None:
        return None

    text = f"{aic:,.1f} AIC"
    upc = usd_per_credit(pricing)
    if upc is not None:
        usd = aic * upc
        return f"{text} (~${usd:,.2f})"
    return text


def fmt_tokens(n):
    if not isinstance(n, (int, float)):
        return None
    n = int(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def fmt_duration(ms):
    if not isinstance(ms, (int, float)):
        return None
    try:
        total_s = round(float(ms) / 1000)
    except (TypeError, ValueError):
        return None
    if total_s < 0:
        return None
    h, rem = divmod(total_s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def render(data):
    """Build the one-line status string from an already-parsed payload dict.

    Every segment is independently optional; an empty result (no recognized fields at all)
    renders the same fallback line as unparseable stdin.
    """
    parts = []

    name = pick_model_name(data)
    if name:
        parts.append(name)

    credits = credits_segment(data, load_pricing())
    if credits:
        parts.append(credits)

    ctx = pick_context_pct(data)
    if isinstance(ctx, (int, float)):
        parts.append(f"ctx {ctx:.0f}%")

    dur = fmt_duration(pick_duration_ms(data))
    if dur:
        parts.append(dur)

    cache_bits = []
    cr_raw = data.get("total_cache_read_tokens")
    cw_raw = data.get("total_cache_write_tokens")
    if isinstance(cr_raw, (int, float)) or isinstance(cw_raw, (int, float)):
        cr_s = fmt_tokens(cr_raw) or "0"
        cw_s = fmt_tokens(cw_raw) or "0"
        cache_bits.append(f"cache {cr_s}/{cw_s}")
    pr = data.get("total_premium_requests")
    if isinstance(pr, (int, float)):
        cache_bits.append(f"premium x{int(pr)}")
    if cache_bits:
        parts.append(" ".join(cache_bits))

    if not parts:
        return FALLBACK_LINE
    return " | ".join(parts)


def render_compact(data):
    """Build the ``--compact`` line: ``~$<usd> · <duration>``.

    Complements Copilot's own built-in footer (model/ctx%/AIC), which this script's default
    mode otherwise duplicates. Reuses the exact same ``pick_aic``/``load_pricing``/
    ``usd_per_credit``/``pick_duration_ms``/``fmt_duration`` helpers the full ``render()`` uses
    — no re-derivation. Degrades to duration-only when USD isn't derivable, and to an empty
    string (never a placeholder, never fabricated) when neither figure is available.
    """
    usd = None
    aic = pick_aic(data)
    if aic is not None:
        upc = usd_per_credit(load_pricing())
        if upc is not None:
            usd = aic * upc

    dur = fmt_duration(pick_duration_ms(data))

    parts = []
    if usd is not None:
        parts.append(f"~${usd:,.2f}")
    if dur:
        parts.append(dur)
    return " · ".join(parts)


def _parse_args(argv):
    capture_path = None
    debug = False
    compact = False
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--capture" and i + 1 < len(argv):
            capture_path = argv[i + 1]
            i += 2
            continue
        if arg == "--debug":
            debug = True
            i += 1
            continue
        if arg in ("--compact", "--slim"):
            compact = True
            i += 1
            continue
        i += 1
    return capture_path, debug, compact


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    capture_path, debug, compact = _parse_args(argv)

    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""

    if capture_path:
        try:
            Path(capture_path).write_text(raw)
        except Exception:
            pass
    if debug:
        try:
            print(raw, file=sys.stderr)
        except Exception:
            pass

    data = None
    if raw and raw.strip():
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            data = parsed

    if compact:
        # Unparseable/absent stdin degrades the same as a field-free payload: an empty line,
        # never the (placeholder-ish) FALLBACK_LINE — the whole point of --compact is to
        # contribute nothing when it has nothing worth adding.
        try:
            line = render_compact(data if data is not None else {})
        except Exception:
            line = ""
        print(line)
        return

    if data is None:
        print(FALLBACK_LINE)
        return

    try:
        line = render(data)
    except Exception:
        line = FALLBACK_LINE
    print(line)


if __name__ == "__main__":
    main()
