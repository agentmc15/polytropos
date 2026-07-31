#!/usr/bin/env python3
"""Historical Codex CLI usage report (the Codex-side analogue of copilot_usage.py).

Walks ``<codex-home>/session_index.jsonl``, ``<codex-home>/history.jsonl``, and rollout
files under ``<codex-home>/sessions/YYYY/MM/DD/*.jsonl`` (one JSON object per line each),
extracts token usage and model ids with a tolerant, extend-never-shrink candidate-key
approach, prices what it actually finds from ``data/pricing.codex.json``, and emits an
honesty-ladder report: price tokens when the logs carry them, else count activity, else say
the logs are empty. Never a fabricated or zeroed-out dollar stand-in for missing data.

STRICTLY READ-ONLY. It never writes anything under the target home, and it opens ONLY
``.jsonl`` files (``session_index.jsonl``, ``history.jsonl``, and rollout files under
``sessions/``) — never a ``*.db``/SQLite file (the real ``~/.codex`` has several; opening one
even "read-only" can create/modify WAL/SHM side files) and never ``config.toml``. It NEVER
invokes the ``codex`` CLI (that would spend the user's real subscription usage limits or API
dollars and hit the network); everything here is a pure log reader. ``DEFAULT_CODEX_HOME``
is the ONLY ``Path.home()`` use in this file; tests always override it via ``--codex-home``.

Extraction constants below are a DELIBERATE, DOCUMENTED DUPLICATION of the ``CODEX_*``
candidate-key lists in ``bin/journal_sources.py`` (lines ~307-360), extended with the rollout
candidates surfaced by the sanctioned T1 research peek
(``.claude/kits/codex-harness/RESEARCH.md``). This script does NOT import or edit
``journal_sources.py``: the daily journal's "Codex counted, never priced" invariant stays
frozen there, and THIS reader is the one sanctioned place Codex tokens may be priced — only
against ``data/pricing.codex.json``, never inline.

Cumulative-vs-per-turn rule (the honesty-critical subtlety, mirrors copilot_usage.py's
shutdown-snapshot MAX rule): within one rollout file, a ``total_token_usage`` container is a
CUMULATIVE snapshot (it re-reports the whole session's running total each time it appears),
so multiple occurrences aggregate by element-wise MAX, never sum. Every other usage
container key (``last_token_usage``, ``usage``, ``token_usage``, ``tokens``,
``token_counts``) is PER-TURN and its occurrences are summed. If one file yields containers
of BOTH kinds, the cumulative MAX wins for that whole file — it is never added to the
per-turn sum, which would double-count.

``reasoning_output_tokens`` is deliberately NOT mapped into the ``output`` bucket: OpenAI's
``output_tokens`` field already includes reasoning tokens, so mapping ``reasoning_output_tokens``
as well would double-count output. It is read (so it never falls through to an "unknown
field" surprise) and silently dropped.

Pricing prices only what these logs can observe: input, cache-read (at
``cache_read_multiplier`` from the pricing file — never a hardcoded 0.1), and output tokens.
Cache WRITES are never priced here because these logs do not carry an observable
cache-write count — this is an intentional asymmetry with ``data/pricing.codex.json``'s
``cache_write_multiplier``, which exists only to serve ``codex_pricing.py``'s forecast
estimator, not this observed-usage reader.

Honesty ladder (PLAN.md D8), in order:
  (a) rollout tokens found -> per-model table (tokens by class, est API-USD), the standing
      subscription disclaimer (verbatim, never omitted when tokens are priced):
      "Figures are API-equivalent dollars — a relative-burn proxy. Subscription (ChatGPT-plan)
      usage is usage-limited, not token-billed."
  (b) activity but no tokens anywhere -> sessions/records/models-seen counts plus the
      verbatim line: "no token usage found in these logs — activity counted, unpriced"
  (c) codex-home or all three log surfaces absent -> say so, cleanly, exit 0.
Malformed JSON lines and non-dict records are counted and skipped, never raised.

Optional ``--kits-dir`` ledger join (graph-convergence T10, ported from copilot_usage.py's
approach): when given, each priced rollout row is checked against every kit's ``NOTES.md``
outcome ledger under that directory for a matching ``run=`` id. A ``run=`` id (PLAN D8)
carries no clock — only a UTC DATE plus four random hex characters — so this is a DATE-level
join only, never a time-window match, and the label riding every annotated row says exactly
that. One run id commonly touches many tasks and one date can hold several kits/runs, so a
match lists every candidate rather than guessing a single one. Only the "priced" branch has
per-rollout rows to annotate; the "activity_only" and "absent" branches carry none, so the
join never touches them. Absent ``--kits-dir``, or no same-day ledger overlap, output is
byte-identical to today's (D6): nothing is added silently.

Usage: codex_usage.py [--days N] [--top N] [--codex-home DIR] [--kits-dir DIR] [--json]
"""

import argparse
import importlib.util
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
PRICING_PATH = PLUGIN_ROOT / "data" / "pricing.codex.json"
# Runtime default only; tests always override it via --codex-home.
DEFAULT_CODEX_HOME = Path.home() / ".codex"

# ---- T10: optional --kits-dir ledger join (DATE-level only — see module docstring) --------
#
# The brief's own verbatim label ("ledger join, time-window match") is OVERRIDDEN here per
# graph-convergence NOTES.md T10: the ledger carries no clock, so "time-window" would be a
# false precision claim. This label states the real basis instead. Duplicated verbatim from
# copilot_usage.py (same house convention as match_model/price_tokens below).
LEDGER_JOIN_LABEL = "(ledger join, same-day run-id match — not a time-window match)"
RUN_ID_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-[0-9a-f]{4}$")

# --------------------------------------------------------------------- extraction constants
#
# Deliberately duplicated (not imported) from bin/journal_sources.py's CODEX_* lists, extended
# with the rollout-shape candidates from RESEARCH.md's T1 peek (session_meta/turn_context
# payload wrapping, total_token_usage/last_token_usage containers). Extend-never-shrink: if a
# future peek finds a new key name, add it here; never remove an existing candidate.
TS_KEYS = ("timestamp", "ts", "created_at", "updated_at", "time", "datetime")
SESSION_KEYS = ("session_id", "sessionId", "conversation_id", "id")
MODEL_KEYS = ("model", "model_id", "model_slug")
WRAPPER_KEYS = ("payload", "data", "info", "turn_context")
USAGE_CONTAINER_KEYS = (
    "total_token_usage", "last_token_usage", "usage", "token_usage", "tokens", "token_counts",
)
CUMULATIVE_CONTAINER_KEYS = ("total_token_usage",)
TOKEN_FIELD_MAP = {
    "input_tokens": "input", "prompt_tokens": "input",
    "cached_input_tokens": "cache_read", "cache_read_input_tokens": "cache_read",
    "cached_tokens": "cache_read",
    "output_tokens": "output", "completion_tokens": "output",
    # reasoning_output_tokens is deliberately NOT mapped here (see module docstring): OpenAI
    # includes reasoning tokens inside output_tokens already, so mapping it too would
    # double-count output.
}
MAX_WRAPPER_DEPTH = 3  # bounded, tolerant descent through WRAPPER_KEYS (payload -> info -> ...)

PROXY_DISCLAIMER = (
    "Figures are API-equivalent dollars — a relative-burn proxy. Subscription (ChatGPT-plan) "
    "usage is usage-limited, not token-billed."
)
UNPRICED_NOTE = "no token usage found in these logs — activity counted, unpriced"


def load_pricing():
    with open(PRICING_PATH) as f:
        return json.load(f)


# ---- tolerant nested-key search ---------------------------------------------------------------

def _first(obj, keys, wrappers=WRAPPER_KEYS, max_depth=MAX_WRAPPER_DEPTH, _depth=0):
    """First present key at the top level of `obj`, else one-level-at-a-time descent through
    `wrappers` (chained: a wrapper's own value can itself carry another wrapper key, e.g.
    ``payload.info.total_token_usage``), bounded by `max_depth`.
    """
    if not isinstance(obj, dict) or _depth > max_depth:
        return None
    for k in keys:
        if k in obj:
            return obj[k]
    for w in wrappers:
        sub = obj.get(w)
        if isinstance(sub, dict):
            found = _first(sub, keys, wrappers, max_depth, _depth + 1)
            if found is not None:
                return found
    return None


def _find_containers(obj, container_keys, wrappers=WRAPPER_KEYS, max_depth=MAX_WRAPPER_DEPTH,
                      _depth=0):
    """All (key, dict-value) pairs whose key is in `container_keys`, reachable at the top
    level of `obj` or via chained descent through `wrappers`. A single record can legitimately
    carry more than one container (e.g. a cumulative AND a per-turn one).
    """
    found = []
    if not isinstance(obj, dict) or _depth > max_depth:
        return found
    for k in container_keys:
        v = obj.get(k)
        if isinstance(v, dict):
            found.append((k, v))
    for w in wrappers:
        sub = obj.get(w)
        if isinstance(sub, dict):
            found.extend(_find_containers(sub, container_keys, wrappers, max_depth, _depth + 1))
    return found


def _normalize_tokens(raw):
    """Map a raw usage-container dict to `{"input", "cache_read", "output"}` via
    `TOKEN_FIELD_MAP`; unmapped fields (including `reasoning_output_tokens`) are dropped.
    """
    out = {"input": 0, "cache_read": 0, "output": 0}
    for k, v in raw.items():
        field = TOKEN_FIELD_MAP.get(k)
        if field and isinstance(v, (int, float)) and not isinstance(v, bool):
            out[field] += v
    return out


# ---- pricing ------------------------------------------------------------------------------------

def match_model(model_id, pricing):
    """Map a raw model string (may carry a bracketed suffix) to a pricing key, or None
    (copilot_usage.py's `match_model` approach, ported verbatim).
    """
    if not model_id or not isinstance(model_id, str) or model_id.startswith("<"):
        return None
    base = model_id.split("[")[0].strip()
    for key in pricing["models"]:
        if base == key or base.startswith(key + "-"):
            return key
    return None


def price_tokens(u, key, pricing):
    """USD for one observed token bundle priced against model `key`.

    Cache reads are priced at ``input_per_mtok * cache_read_multiplier`` (both read from the
    pricing dict at run time — never a hardcoded 0.1). Cache writes are never priced here:
    these logs carry no observable cache-write count (see module docstring).
    """
    m = pricing["models"][key]
    cache_read_rate = m["input_per_mtok"] * pricing["cache_read_multiplier"]
    return (
        u["input"] * m["input_per_mtok"]
        + u["cache_read"] * cache_read_rate
        + u["output"] * m["output_per_mtok"]
    ) / 1e6


# ---- timestamps ---------------------------------------------------------------------------------

def parse_timestamp(raw):
    """Tolerant timestamp parse: ISO-8601 string, or a numeric epoch (int/float/digit-string;
    values > 1e12 are treated as milliseconds). Returns a tz-aware UTC datetime, or None.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return _epoch_to_dt(raw)
    s = str(raw).strip()
    if not s:
        return None
    try:
        ts = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    except ValueError:
        pass
    try:
        return _epoch_to_dt(float(s))
    except ValueError:
        return None


def _epoch_to_dt(num):
    if num > 1e12:  # milliseconds
        num = num / 1000
    try:
        return datetime.fromtimestamp(num, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


# ---- rollout parsing (one rollout file at a time) -------------------------------------------------

def parse_rollout(lines):
    """Reduce one rollout file's lines to a token/model/activity summary.

    Cumulative-vs-per-turn rule (module docstring): if any ``total_token_usage`` container is
    found, the element-wise MAX across all such containers in this file wins as the file's
    token counts (never summed, and never added to any per-turn containers also present in
    the file). Otherwise, if any per-turn container is found, all such containers are summed.
    Otherwise this rollout carries no observable token usage (``tokens`` is None).
    """
    cumulative = None
    per_turn_sum = {"input": 0, "cache_read": 0, "output": 0}
    has_per_turn = False
    models = []
    session_ids = set()
    records = 0
    malformed = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if not isinstance(obj, dict):
            malformed += 1
            continue
        records += 1

        sid = _first(obj, SESSION_KEYS)
        if isinstance(sid, str):
            session_ids.add(sid)

        m = _first(obj, MODEL_KEYS)
        if isinstance(m, str) and m not in models:
            models.append(m)

        for key, container in _find_containers(obj, USAGE_CONTAINER_KEYS):
            norm = _normalize_tokens(container)
            if key in CUMULATIVE_CONTAINER_KEYS:
                if cumulative is None:
                    cumulative = dict(norm)
                else:
                    for f in cumulative:
                        cumulative[f] = max(cumulative[f], norm[f])
            else:
                has_per_turn = True
                for f in per_turn_sum:
                    per_turn_sum[f] += norm[f]

    if cumulative is not None:
        tokens = cumulative
    elif has_per_turn:
        tokens = per_turn_sum
    else:
        tokens = None

    return {
        "tokens": tokens,
        "models": models,
        "session_ids": session_ids,
        "records": records,
        "malformed": malformed,
    }


# ---- file discovery -------------------------------------------------------------------------------

def _mtime_ok(path, cutoff):
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return False
    return mtime >= cutoff


def _walk_mtime_fallback(root, cutoff):
    """Non-date-partitioned layout: fall back to file mtime for pruning."""
    if not root.is_dir():
        return
    try:
        candidates = sorted(root.rglob("*.jsonl"))
    except OSError:
        return
    for f in candidates:
        if _mtime_ok(f, cutoff):
            yield f


def iter_rollout_files(sessions_dir, cutoff):
    """Yield rollout `.jsonl` paths within the `cutoff` window.

    Date-partitioned files (`sessions/YYYY/MM/DD/*.jsonl`) are pruned by DIRECTORY NAME
    before any listing/opening happens under an out-of-window date dir — an unreadable
    out-of-window day directory is never touched. Anything that doesn't match the
    `YYYY/MM/DD` shape falls back to file-mtime pruning.
    """
    if not sessions_dir.is_dir():
        return
    cutoff_date = cutoff.date()

    try:
        year_dirs = sorted(p for p in sessions_dir.iterdir() if p.is_dir())
    except OSError:
        year_dirs = []

    for year_dir in year_dirs:
        if not (year_dir.name.isdigit() and len(year_dir.name) == 4):
            yield from _walk_mtime_fallback(year_dir, cutoff)
            continue
        try:
            month_dirs = sorted(p for p in year_dir.iterdir() if p.is_dir())
        except OSError:
            continue
        for month_dir in month_dirs:
            if not (month_dir.name.isdigit() and len(month_dir.name) == 2):
                yield from _walk_mtime_fallback(month_dir, cutoff)
                continue
            try:
                day_dirs = sorted(p for p in month_dir.iterdir() if p.is_dir())
            except OSError:
                continue
            for day_dir in day_dirs:
                if not (day_dir.name.isdigit() and len(day_dir.name) == 2):
                    yield from _walk_mtime_fallback(day_dir, cutoff)
                    continue
                try:
                    d = datetime(
                        int(year_dir.name), int(month_dir.name), int(day_dir.name)
                    ).date()
                except ValueError:
                    yield from _walk_mtime_fallback(day_dir, cutoff)
                    continue
                if d < cutoff_date:
                    continue  # pruned BEFORE opening/listing anything under this date dir
                try:
                    files = sorted(
                        p for p in day_dir.iterdir() if p.is_file() and p.suffix == ".jsonl"
                    )
                except OSError:
                    continue
                for f in files:
                    yield f

    # Stray .jsonl files directly under sessions_dir (non-date-partitioned): mtime fallback.
    try:
        stray = sorted(
            p for p in sessions_dir.iterdir() if p.is_file() and p.suffix == ".jsonl"
        )
    except OSError:
        stray = []
    for f in stray:
        if _mtime_ok(f, cutoff):
            yield f


def scan_activity_file(path, cutoff):
    """Read a JSONL activity file (`session_index.jsonl` / `history.jsonl`) tolerantly.

    Returns `(session_ids, models, records, malformed)`. Records without a parseable
    timestamp are KEPT regardless of `cutoff` (unknown age is not evidence of staleness —
    mirrors copilot_usage.py's age-filter convention); malformed lines are counted, skipped.
    """
    session_ids = set()
    models = []
    records = 0
    malformed = 0
    if not path.is_file():
        return session_ids, models, records, malformed
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return session_ids, models, records, malformed

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if not isinstance(obj, dict):
            malformed += 1
            continue

        when = parse_timestamp(_first(obj, TS_KEYS))
        if when is not None and when < cutoff:
            continue

        records += 1
        sid = _first(obj, SESSION_KEYS)
        if isinstance(sid, str):
            session_ids.add(sid)
        m = _first(obj, MODEL_KEYS)
        if isinstance(m, str) and m not in models:
            models.append(m)

    return session_ids, models, records, malformed


# ---- T10: optional --kits-dir DATE-level ledger join -----------------------------------------

def _load_scorecard_module():
    """Lazy sibling import of bin/routing_scorecard.py (mirrors
    ``copilot_execute._load_pricing_module``'s established pattern for cross-``bin/`` reuse
    without a package). Used ONLY for its ``parse_outcomes`` ledger-line parser -- the
    outcome-line grammar is never re-implemented here.
    """
    path = Path(__file__).resolve().parent / "routing_scorecard.py"
    spec = importlib.util.spec_from_file_location("routing_scorecard", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_ledger_index(kits_dir):
    """T10 DATE-level ledger join index (ported verbatim from copilot_usage.py): scan every
    kit dir's ``NOTES.md`` under `kits_dir` for ``outcome:`` lines carrying a ``run=`` id,
    bucketed by the id's DATE segment only -- a run id's only temporal content per PLAN D8
    (its four hex characters are random, never a clock), so a date is the strongest join this
    format supports.

    Returns ``{date_str: [{"kit", "run", "tasks"}, ...]}`` -- ``tasks`` is the sorted list of
    task ids whose latest outcome line named that run id in that kit (one run commonly covers
    many tasks; all are listed as candidates, never narrowed to one). Deterministic (kits and
    runs sorted by name) and empty when `kits_dir` is absent or holds no matching kits --
    never raises. Strictly read-only.
    """
    kits_dir = Path(kits_dir)
    index = defaultdict(list)
    if not kits_dir.is_dir():
        return index
    try:
        subdirs = sorted((p for p in kits_dir.iterdir() if p.is_dir()), key=lambda p: p.name)
    except OSError:
        return index

    scorecard = _load_scorecard_module()
    for sub in subdirs:
        notes_path = sub / "NOTES.md"
        if not notes_path.is_file():
            continue
        try:
            text = notes_path.read_text(errors="replace")
        except OSError:
            continue
        outcomes, _notes = scorecard.parse_outcomes(text)
        by_run = defaultdict(set)
        for _task_id, outcome in outcomes.items():
            run = outcome.get("run")
            if not run or not RUN_ID_DATE_RE.match(run):
                continue
            by_run[run].add(_task_id)
        for run, tasks in by_run.items():
            index[run[:10]].append({"kit": sub.name, "run": run, "tasks": sorted(tasks)})

    for date_str in index:
        index[date_str].sort(key=lambda c: (c["kit"], c["run"]))
    return index


def rollout_date(path, sessions_dir):
    """Best-effort UTC calendar date for one rollout file, used ONLY for the T10 ledger join.

    Prefers the date-partitioned `sessions/YYYY/MM/DD/` path segments (mirrors
    `iter_rollout_files`'s own date-partition detection); falls back to the file's mtime for
    non-date-partitioned layouts. Returns None only on an OSError from `stat()` -- an
    undateable rollout gets no ledger match, which is honest, never a guess.
    """
    try:
        rel = path.relative_to(sessions_dir)
        parts = rel.parts
        if len(parts) >= 4:
            y, m, d = parts[0], parts[1], parts[2]
            if (
                y.isdigit() and len(y) == 4
                and m.isdigit() and len(m) == 2
                and d.isdigit() and len(d) == 2
            ):
                try:
                    return datetime(int(y), int(m), int(d)).date().isoformat()
                except ValueError:
                    pass
    except ValueError:
        pass
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).date().isoformat()
    except OSError:
        return None


# ---- unified payload builder (one scan pass; never prints, never exits) --------------------------

def build_usage_payload(codex_home, days=30, top=10, kits_dir=None):
    """Scan `codex_home`'s Codex logs once and return a unified payload dict.

    Superset of the three existing `--json` branch shapes (module docstring's D8 honesty
    ladder): required keys `schema_version` (1), `found` (False only for the absent branch),
    `priced` (True only for the priced branch), `branch`
    (`"absent" | "activity_only" | "priced"`), `days`, `codex_home` (str), `labels` (list),
    plus every field the corresponding existing `--json` branch dict carries today under the
    same names and values.

    ONE key, `_render`, is internal transport for the markdown print helper's full-precision
    formatting: `{"pricing", "by_model", "rows_sorted"}`. It is the ONLY `_`-prefixed
    top-level key and is never surfaced by the CLI's `--json` output; everything OUTSIDE it
    is the public card, and every list there is bounded (`top`-capped). `rows_sorted` inside
    `_render` is itself capped at `top` — the markdown only ever iterates `rows_sorted[:top]`
    — so no uncapped per-rollout list exists anywhere in the payload. Consumers that persist
    the card (the telemetry store) drop `_render` and keep a bounded public payload.

    `kits_dir` (T10, optional, default None): when given, joins PRICED rollout rows to a
    ledger by DATE only (see module docstring / `build_ledger_index`) -- the "activity_only"
    and "absent" branches carry no per-row list, so the join never touches them. A matched
    `top_rollouts` entry gains an optional `ledger_join` key
    (`{"label", "date", "ambiguous", "candidates"}`); nothing is added when `kits_dir` is None
    or no rollout's date overlaps any kit's ledger -- absent means today's behavior (D6). The
    top-level `kits_dir` key is likewise added ONLY when at least one row actually matched.

    This function never prints and never calls `sys.exit`; `main()` is the only caller that
    decides what to print.
    """
    codex_home = Path(codex_home)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    index_path = codex_home / "session_index.jsonl"
    history_path = codex_home / "history.jsonl"
    sessions_dir = codex_home / "sessions"

    idx_ids, idx_models, idx_records, idx_malformed = scan_activity_file(index_path, cutoff)
    hist_ids, hist_models, hist_records, hist_malformed = scan_activity_file(
        history_path, cutoff
    )
    rollout_files = list(iter_rollout_files(sessions_dir, cutoff))

    if not codex_home.is_dir() or (
        not index_path.is_file()
        and not history_path.is_file()
        and not rollout_files
        and not sessions_dir.is_dir()
    ):
        message = (
            f"No Codex usage data found under {codex_home} "
            "(no session_index.jsonl, history.jsonl, or sessions/ directory)."
        )
        return {
            "schema_version": 1,
            "found": False,
            "priced": False,
            "branch": "absent",
            "days": days,
            "top": top,
            "codex_home": str(codex_home),
            "labels": [f"codex home absent: {codex_home}"],
            "message": message,
        }

    session_ids = set(idx_ids) | set(hist_ids)
    models_seen = list(idx_models)
    for m in hist_models:
        if m not in models_seen:
            models_seen.append(m)
    total_records = idx_records + hist_records
    total_malformed = idx_malformed + hist_malformed

    pricing = load_pricing()

    # T10: DATE-level ledger index, built once. None when kits_dir wasn't passed at all
    # (distinct from "built but empty" -- both degrade the same way below, but keeping None
    # distinct is what lets the top-level `kits_dir` key stay unadded when unused).
    ledger_index = build_ledger_index(kits_dir) if kits_dir is not None else None

    by_model = defaultdict(
        lambda: {"input": 0, "cache_read": 0, "output": 0, "rollouts": 0, "usd": 0.0,
                  "approx": False}
    )
    unpriced_models = set()
    rows = []
    total_rollouts = 0
    priced_rollouts = 0
    read_errors = []

    for f in rollout_files:
        try:
            text = f.read_text(errors="replace")
        except OSError as e:
            read_errors.append(f"{f}: {e}")
            continue

        parsed = parse_rollout(text.splitlines())
        total_rollouts += 1
        total_records += parsed["records"]
        total_malformed += parsed["malformed"]
        for sid in parsed["session_ids"]:
            session_ids.add(sid)
        for m in parsed["models"]:
            if m not in models_seen:
                models_seen.append(m)

        if parsed["tokens"] is None:
            continue
        priced_rollouts += 1

        matched = []
        for m in parsed["models"]:
            k = match_model(m, pricing)
            if k and k not in matched:
                matched.append(k)
        if not matched:
            for m in parsed["models"]:
                if match_model(m, pricing) is None:
                    unpriced_models.add(m)
            continue

        approx = len(matched) > 1
        key = matched[-1]
        usd = price_tokens(parsed["tokens"], key, pricing)

        b = by_model[key]
        for field in ("input", "cache_read", "output"):
            b[field] += parsed["tokens"][field]
        b["usd"] += usd
        b["rollouts"] += 1
        if approx:
            b["approx"] = True

        footprint = parsed["tokens"]["input"] + parsed["tokens"]["output"]
        row = {
            "file": f.name, "models": parsed["models"], "usd": usd, "footprint": footprint,
            "approx": approx,
        }
        # T10: optional DATE-level ledger join -- added ONLY on an actual match, never a guess.
        if ledger_index:
            date_str = rollout_date(f, sessions_dir)
            lj_candidates = ledger_index.get(date_str) if date_str else None
            if lj_candidates:
                row["ledger_join"] = {
                    "label": LEDGER_JOIN_LABEL,
                    "date": date_str,
                    "ambiguous": len(lj_candidates) > 1,
                    "candidates": lj_candidates,
                }
        rows.append(row)

    if priced_rollouts == 0:
        return {
            "schema_version": 1,
            "found": True,
            "priced": False,
            "branch": "activity_only",
            "days": days,
            "top": top,
            "codex_home": str(codex_home),
            "labels": ["activity counted, unpriced"],
            "note": UNPRICED_NOTE,
            "sessions": len(session_ids),
            "records": total_records,
            "malformed_lines": total_malformed,
            "models_seen": models_seen,
            "read_errors": read_errors,
        }

    rows_sorted = sorted(rows, key=lambda r: -r["usd"])
    total_usd = sum(b["usd"] for b in by_model.values())

    priced_payload = {
        "schema_version": 1,
        "found": True,
        "priced": True,
        "branch": "priced",
        "days": days,
        "top": top,
        "codex_home": str(codex_home),
        "labels": ["API-price estimate from found tokens (est.) — never a bill"],
        "disclaimer": PROXY_DISCLAIMER,
        "total_usd": round(total_usd, 6),
        "rollouts_scanned": total_rollouts,
        "rollouts_with_tokens": priced_rollouts,
        "by_model": [
            {
                "model_id": key,
                "display": pricing["models"][key]["display"],
                "rollouts": b["rollouts"],
                "input": b["input"],
                "cache_read": b["cache_read"],
                "output": b["output"],
                "usd": round(b["usd"], 6),
                "approx": bool(b["approx"]),
            }
            for key, b in sorted(by_model.items(), key=lambda kv: -kv[1]["usd"])
        ],
        "top_rollouts": [
            {
                "file": r["file"], "models": r["models"], "usd": round(r["usd"], 6),
                "footprint": r["footprint"], "approx": r["approx"],
                **({"ledger_join": r["ledger_join"]} if "ledger_join" in r else {}),
            }
            for r in rows_sorted[:top]
        ],
        "unpriced_models": sorted(unpriced_models),
        "malformed_lines": total_malformed,
        "read_errors": read_errors,
        "cached_date": pricing["cached_date"],
        # Internal transport only (full-precision markdown formatting), consolidated under
        # ONE key so the public payload above stays bounded and card-shaped. Never echoed
        # as-is by the CLI's --json output. rows_sorted is capped at `top` because that is
        # all the markdown ever reads.
        "_render": {
            "pricing": pricing,
            "by_model": dict(by_model),
            "rows_sorted": rows_sorted[:top],
        },
    }
    # T10: only added when kits_dir was passed AND at least one rollout actually matched --
    # a passed-but-unmatched kits_dir degrades silently, exactly like an absent one (D6).
    if kits_dir is not None and any("ledger_join" in r for r in rows):
        priced_payload["kits_dir"] = str(kits_dir)
    return priced_payload


# ---- report rendering -----------------------------------------------------------------------------

def _print_absent(payload, want_json):
    if want_json:
        print(json.dumps(
            {
                "branch": "absent",
                "codex_home": payload["codex_home"],
                "message": payload["message"],
            },
            indent=2,
        ))
    else:
        print(f"# Codex CLI usage\n\n{payload['message']}\n")


def _print_activity_only(payload, want_json):
    if want_json:
        print(json.dumps({
            "branch": "activity_only",
            "days": payload["days"],
            "codex_home": payload["codex_home"],
            "note": payload["note"],
            "sessions": payload["sessions"],
            "records": payload["records"],
            "malformed_lines": payload["malformed_lines"],
            "models_seen": payload["models_seen"],
            "read_errors": payload["read_errors"],
        }, indent=2))
        return

    models_seen = payload["models_seen"]
    out = []
    out.append(f"# Codex CLI usage — last {payload['days']} days\n")
    out.append(UNPRICED_NOTE)
    out.append("\n## Activity\n")
    out.append(f"- Sessions: {payload['sessions']:,}")
    out.append(f"- Records: {payload['records']:,}")
    out.append(f"- Models seen: {', '.join(models_seen) if models_seen else 'none'}")
    if payload["malformed_lines"]:
        out.append(f"- Malformed lines skipped: {payload['malformed_lines']:,}")
    if payload["read_errors"]:
        out.append("\n## Read errors\n")
        for e in payload["read_errors"]:
            out.append(f"- {e}")
    out.append(
        f"\n*Codex home: {payload['codex_home']}. No pricing applied (D8 honesty ladder).*"
    )
    print("\n".join(out))


def _print_priced(payload, want_json):
    if want_json:
        out_obj = {
            "branch": "priced",
            "days": payload["days"],
            "codex_home": payload["codex_home"],
            "disclaimer": payload["disclaimer"],
            "total_usd": payload["total_usd"],
            "rollouts_scanned": payload["rollouts_scanned"],
            "rollouts_with_tokens": payload["rollouts_with_tokens"],
            "by_model": payload["by_model"],
            "top_rollouts": payload["top_rollouts"],
            "unpriced_models": payload["unpriced_models"],
            "malformed_lines": payload["malformed_lines"],
            "read_errors": payload["read_errors"],
            "cached_date": payload["cached_date"],
        }
        if "kits_dir" in payload:  # T10: only present when a ledger match actually occurred.
            out_obj["kits_dir"] = payload["kits_dir"]
        print(json.dumps(out_obj, indent=2))
        return

    render = payload["_render"]
    pricing = render["pricing"]
    by_model = render["by_model"]
    rows_sorted = render["rows_sorted"]
    unpriced_models = payload["unpriced_models"]
    total_usd = sum(b["usd"] for b in by_model.values())
    top = payload["top"]

    out = []
    out.append(f"# Codex CLI usage — last {payload['days']} days\n")
    out.append(
        f"**Total priced estimate: ${total_usd:,.4f}** across "
        f"{payload['rollouts_with_tokens']} rollout(s) with token data "
        f"({payload['rollouts_scanned']} rollout(s) scanned).\n"
    )
    out.append(PROXY_DISCLAIMER)

    out.append("\n## Spend by model\n")
    out.append("| Model | Rollouts | Input | Cache read | Output | USD |")
    out.append("|---|---:|---:|---:|---:|---:|")
    for key, b in sorted(by_model.items(), key=lambda kv: -kv[1]["usd"]):
        disp = pricing["models"][key]["display"]
        rollouts_cell = f"{b['rollouts']:,}" + (" ≈" if b["approx"] else "")
        out.append(
            f"| {disp} | {rollouts_cell} | {b['input']:,} | {b['cache_read']:,} "
            f"| {b['output']:,} | ${b['usd']:,.4f} |"
        )
    if any(b["approx"] for b in by_model.values()):
        out.append(
            "\n≈ this rollout carried more than one model id; its whole token count is "
            "attributed to the last model seen in the file."
        )

    out.append(f"\n## Top {top} rollouts by estimated cost\n")
    out.append("| Rollout | Models | Tokens | USD |")
    out.append("|---|---|---:|---:|")
    for r in rows_sorted[:top]:
        models_disp = ", ".join(r["models"]) if r["models"] else "(unknown)"
        mark = " ≈" if r["approx"] else ""
        out.append(f"| {r['file']} | {models_disp}{mark} | {r['footprint']:,} | ${r['usd']:,.4f} |")

    # T10 ledger join (--kits-dir): rendered ONLY when a rollout actually matched --
    # otherwise this section is entirely absent, matching today's output byte-for-byte (D6).
    ledger_rows = [r for r in rows_sorted[:top] if "ledger_join" in r]
    if ledger_rows:
        out.append("\n## Ledger join (--kits-dir)\n")
        out.append(LEDGER_JOIN_LABEL)
        out.append(
            "\nA `run=` id carries only a DATE (PLAN D8's four hex characters are random, "
            "never a clock), so rollouts are joined to ledger outcomes by same-day match "
            "only — never by time window. One run id commonly touches many tasks, so every "
            "task an outcome line recorded under the matching run is listed as a candidate, "
            "never narrowed to a single guess; more than one kit or run on the same date "
            "lists every candidate as its own row.\n"
        )
        out.append("| Rollout | Date | Kit | Run | Tasks touched |")
        out.append("|---|---|---|---|---|")
        for r in ledger_rows:
            lj = r["ledger_join"]
            for c in lj["candidates"]:
                out.append(
                    f"| {r['file']} | {lj['date']} | {c['kit']} | {c['run']} "
                    f"| {', '.join(c['tasks'])} |"
                )
        ambiguous_n = sum(1 for r in ledger_rows if r["ledger_join"]["ambiguous"])
        if ambiguous_n:
            out.append(
                f"\n{ambiguous_n} rollout(s) above matched more than one kit/run on the "
                "same date — every candidate is listed as its own row, never narrowed to "
                "a single guess."
            )

    if unpriced_models:
        out.append("\n## Unpriced models (not in pricing.codex.json)\n")
        for m in sorted(unpriced_models):
            out.append(f"- `{m}`")
    if payload["malformed_lines"]:
        out.append(f"\nMalformed lines skipped: {payload['malformed_lines']:,}")
    if payload["read_errors"]:
        out.append("\n## Read errors\n")
        for e in payload["read_errors"]:
            out.append(f"- {e}")

    out.append(
        f"\n*Prices cached {payload['cached_date']} from pricing.codex.json. Cache writes "
        f"are never priced here (not observable in these logs). "
        f"Codex home: {payload['codex_home']}.*"
    )
    print("\n".join(out))


# ---- main -----------------------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="codex_usage.py",
        description=(
            "Codex CLI usage report (read-only honesty ladder): prices tokens actually "
            "found in ~/.codex's JSONL logs, else counts activity, unpriced."
        ),
    )
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--codex-home", default=str(DEFAULT_CODEX_HOME))
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument(
        "--kits-dir",
        default=None,
        help=(
            "T10: optional directory of kit dirs (each holding TASKS.md/NOTES.md) to join "
            "priced rollouts against by same-day run= id match. Never set by default; "
            "omitting it leaves output exactly as before (D6)."
        ),
    )
    args = ap.parse_args(argv)

    payload = build_usage_payload(
        args.codex_home, days=args.days, top=args.top, kits_dir=args.kits_dir
    )

    if payload["branch"] == "absent":
        _print_absent(payload, args.json)
    elif payload["branch"] == "activity_only":
        _print_activity_only(payload, args.json)
    else:
        _print_priced(payload, args.json)


if __name__ == "__main__":
    main()
