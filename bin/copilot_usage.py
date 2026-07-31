#!/usr/bin/env python3
"""Historical Copilot CLI usage report (the Copilot-side analogue of cost_report.py).

Walks ``<copilot-home>/session-state/*/events.jsonl`` (one JSON object per line) plus each
session's sibling ``workspace.yaml``, attributes token usage per session/model with honest
granularity, prices it from the plugin's ``data/pricing.copilot.json`` (USD + AI Credits,
both derived from the pricing dict at run time — never hardcoded), and emits markdown.

STRICTLY READ-ONLY. It never writes anything under the target home, and it opens ONLY the two
text files above. It NEVER opens the ``*.db`` session stores (``session.db``, ``data.db``,
``session-store.db``): those read empty without a WAL checkpoint, and opening a live SQLite
file — even "read-only" — can create/modify ``-wal``/``-shm`` side files, which would violate
the read-only contract against the user's live home. It NEVER invokes the ``copilot`` CLI
(that would spend real AI Credits and hit the network); everything here is a pure log reader.

Cost-bearing events (``session.shutdown``) carry cumulative ``total*`` snapshots, so multiple
shutdowns across resumes aggregate by element-wise MAX, never sum (summing would double-count
the cumulative case). The full input/cache_read/cache_write/output split exists at SESSION
granularity only, so a single-model session is priced exactly against its one model while a
multi-model session attributes its whole split to its LAST model and is flagged ``≈`` — the
events do not record per-model input/cache splits and the report never fabricates one. The
exact cross-model view is the per-turn output-tokens table built from ``assistant.message``
events.

Unlike the forecast convention in copilot_pricing.est_cost (which excludes cache writes), this
report prices OBSERVED counts and so includes cache writes wherever the model's pricing row
carries a ``cache_write_per_mtok`` rate — dropping a measured, priced quantity would understate
real spend.

``totalNanoAiu`` (Copilot's own reported "AI Units", nano-scaled) is shown only as a labeled
cross-check; it is NEVER assumed equal to the AIC billing unit and NEVER converted to USD or
AIC. The authoritative estimate is token counts x per-MTok rates -> USD -> AIC via
``billing_unit.usd_per_credit``.

Event format observed on Copilot CLI v1.0.68.

Optional ``--kits-dir`` ledger join (graph-convergence T10): when given, each session row is
checked against every kit's ``NOTES.md`` outcome ledger under that directory for a matching
``run=`` id. A ``run=`` id (PLAN D8) carries no clock — only a UTC DATE plus four random hex
characters — so this is a DATE-level join only, never a time-window match, and the label
riding every annotated row says exactly that. One run id commonly touches many tasks and one
date can hold several kits/runs, so a match lists every candidate rather than guessing a
single one. Absent ``--kits-dir``, or no same-day ledger overlap, output is byte-identical to
today's (D6): nothing is added silently.

Usage: copilot_usage.py [--days N] [--top N] [--copilot-home DIR] [--session-dir DIR]
                         [--kits-dir DIR] [--json]
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
PRICING_PATH = PLUGIN_ROOT / "data" / "pricing.copilot.json"
# Runtime default only; tests always override it via --copilot-home / --session-dir.
DEFAULT_COPILOT_HOME = Path.home() / ".copilot"

# ---- T10: optional --kits-dir ledger join (DATE-level only — see module docstring) --------
#
# The brief's own verbatim label ("ledger join, time-window match") is OVERRIDDEN here per
# graph-convergence NOTES.md T10: the ledger carries no clock, so "time-window" would be a
# false precision claim. This label states the real basis instead.
LEDGER_JOIN_LABEL = "(ledger join, same-day run-id match — not a time-window match)"
RUN_ID_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-[0-9a-f]{4}$")

EXPENSIVE_TIERS = {"strong", "frontier"}
# Report knobs (token/turn counts, NOT prices): a downgrade candidate stays under both.
DOWNGRADE_TOKEN_CEILING = 50_000
# Copilot events carry no tool-use counter, so assistant turns replace cost_report's
# tool-call ceiling.
DOWNGRADE_TURN_CEILING = 15


def load_pricing():
    with open(PRICING_PATH) as f:
        return json.load(f)


def match_model(model_id, pricing):
    """Map a raw model string (may carry a bracketed suffix) to a pricing key, or None."""
    if not model_id or model_id.startswith("<"):
        return None
    base = model_id.split("[")[0].strip()
    for key in pricing["models"]:
        if base == key or base.startswith(key + "-"):
            return key
    return None


def price_tokens(u, key, pricing):
    """USD for one token bundle priced against model `key` (PLAN.md D5).

    Cache writes ARE priced when the model row carries a ``cache_write_per_mtok`` rate
    (observed usage), unlike copilot_pricing.est_cost's forecast convention.
    """
    m = pricing["models"][key]
    return (
        u["input"] * m["input_per_mtok"]
        + u["cache_read"] * m["cached_input_per_mtok"]
        + u["cache_write"] * m.get("cache_write_per_mtok", 0)
        + u["output"] * m["output_per_mtok"]
    ) / 1e6


def usd_to_aic(usd, pricing):
    """USD -> AI Credits via the data's billing unit — never a hardcoded rate."""
    return usd / pricing["billing_unit"]["usd_per_credit"]


def parse_timestamp(raw):
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def parse_events(lines):
    """Reduce one session's event lines to an attribution/pricing summary.

    Robust by construction: blank/malformed JSON lines and non-dict objects are skipped,
    unknown event types ignored, and every ``data`` field access uses ``.get`` with a
    default. Shutdown ``total*`` fields are cumulative snapshots, so they aggregate by
    element-wise MAX across shutdowns (exact for cumulative snapshots; never double-counts).
    """
    tokens = {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0}
    nano_aiu = 0
    premium_requests = 0
    shutdowns = 0
    has_token_details = False
    models = []
    last_model = None
    per_turn_output = {}
    seen_api_calls = set()
    first_seen = None
    last_seen = None

    def note_model(m):
        nonlocal last_model
        if not m:
            return
        if m not in models:
            models.append(m)
        last_model = m

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        etype = obj.get("type")
        data = obj.get("data")
        if not isinstance(data, dict):
            data = {}

        when = parse_timestamp(obj.get("timestamp"))
        if when is not None:
            if first_seen is None or when < first_seen:
                first_seen = when
            if last_seen is None or when > last_seen:
                last_seen = when

        if etype in ("session.start", "session.resume"):
            note_model(data.get("selectedModel"))
        elif etype == "session.model_change":
            note_model(data.get("previousModel"))
            note_model(data.get("newModel"))
        elif etype == "assistant.message":
            m = data.get("model")
            note_model(m)
            api_id = data.get("apiCallId")
            if api_id is not None and api_id in seen_api_calls:
                continue
            if api_id is not None:
                seen_api_calls.add(api_id)
            out = data.get("outputTokens") or 0
            if m:
                entry = per_turn_output.setdefault(m, {"turns": 0, "output_tokens": 0})
                entry["turns"] += 1
                entry["output_tokens"] += out
        elif etype == "session.shutdown":
            shutdowns += 1
            note_model(data.get("currentModel"))
            td = data.get("tokenDetails")
            if isinstance(td, dict):
                has_token_details = True
                for field in ("input", "cache_read", "cache_write", "output"):
                    sub = td.get(field)
                    count = sub.get("tokenCount") or 0 if isinstance(sub, dict) else 0
                    tokens[field] = max(tokens[field], count)
            nano_aiu = max(nano_aiu, data.get("totalNanoAiu") or 0)
            premium_requests = max(premium_requests, data.get("totalPremiumRequests") or 0)

    return {
        "tokens": tokens,
        "nano_aiu": nano_aiu,
        "premium_requests": premium_requests,
        "shutdowns": shutdowns,
        "has_token_details": has_token_details,
        "models": models,
        "last_model": last_model,
        "per_turn_output": per_turn_output,
        "first_seen": first_seen,
        "last_seen": last_seen,
    }


def effective_tokens(parsed):
    """Return (tokens_dict, output_only). With shutdown token details, use them as-is.

    Without any ``tokenDetails`` (crash/still-open session), fall back to output-only: input
    and cache fields are 0 and output is the summed per-turn ``outputTokens`` (an undercount).
    """
    if parsed["has_token_details"]:
        return dict(parsed["tokens"]), False
    output = sum(v["output_tokens"] for v in parsed["per_turn_output"].values())
    return {"input": 0, "cache_read": 0, "cache_write": 0, "output": output}, True


def parse_workspace(text):
    """Tolerant flat ``key: value`` parser (no YAML parser exists in stdlib; nesting ignored).

    First ``:`` splits; both sides stripped; lines without a ``:`` or with an empty key are
    ignored. Empty text -> ``{}``.
    """
    result = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key:
            result[key] = value.strip()
    return result


def collect_sessions(session_dir):
    """Parse every session subdir under `session_dir` that contains an events.jsonl.

    Opens ONLY ``events.jsonl`` and (when present) ``workspace.yaml`` — never globs or opens
    anything else (no ``*.db``). OSErrors are collected into `errors`, never raised.
    """
    sessions = []
    errors = []
    try:
        subdirs = sorted(p for p in session_dir.iterdir() if p.is_dir())
    except OSError as e:
        errors.append(f"{session_dir}: {e}")
        return sessions, errors

    for sub in subdirs:
        events_path = sub / "events.jsonl"
        if not events_path.is_file():
            continue
        try:
            text = events_path.read_text(errors="replace")
        except OSError as e:
            errors.append(f"{events_path}: {e}")
            continue
        parsed = parse_events(text.splitlines())
        workspace = {}
        ws_path = sub / "workspace.yaml"
        if ws_path.is_file():
            try:
                workspace = parse_workspace(ws_path.read_text(errors="replace"))
            except OSError as e:
                errors.append(f"{ws_path}: {e}")
                workspace = {}
        parsed["session_id"] = sub.name
        parsed["workspace"] = workspace
        sessions.append(parsed)
    return sessions, errors


def display_for(raw_model, pricing):
    key = match_model(raw_model, pricing)
    if key:
        return pricing["models"][key]["display"]
    return raw_model


def project_label(workspace):
    cwd = workspace.get("cwd")
    if cwd:
        tail = cwd.rstrip("/").split("/")[-1]
        if tail:
            return tail
    return workspace.get("name", "") or ""


def _attribute(parsed, pricing):
    """Return (matched_keys, attribution_key, approx) for one session (PLAN.md D4)."""
    matched_keys = []
    for m in parsed["models"]:
        k = match_model(m, pricing)
        if k and k not in matched_keys:
            matched_keys.append(k)
    if not matched_keys:
        return matched_keys, None, False
    if len(matched_keys) == 1:
        return matched_keys, matched_keys[0], False
    last_key = match_model(parsed["last_model"], pricing)
    attribution = last_key if last_key in matched_keys else matched_keys[-1]
    return matched_keys, attribution, True


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
    """T10 DATE-level ledger join index: scan every kit dir's ``NOTES.md`` under `kits_dir`
    for ``outcome:`` lines carrying a ``run=`` id, bucketed by the id's DATE segment only --
    a run id's only temporal content per PLAN D8 (its four hex characters are random, never a
    clock), so a date is the strongest join this format supports.

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


def session_date(s):
    """Best-effort UTC calendar date for a parsed session (`parse_events`'s output), used
    ONLY for the T10 ledger join. Prefers `last_seen` (closer to when the session actually
    ran); falls back to `first_seen`; returns None when neither timestamp is available -- an
    untimestamped session gets no ledger match, which is honest, never a guess.
    """
    when = s.get("last_seen") or s.get("first_seen")
    return when.date().isoformat() if when else None


def build_usage_payload(session_dir, days=30, top=10, kits_dir=None):
    """Pure aggregation builder (PLAN.md D3): session collection -> per-model / per-turn /
    per-session aggregation -> totals, priced from data/pricing.copilot.json (loaded
    internally, exactly like `main` did before this extraction). Never exits and never
    writes anything; a missing `session_dir` returns a `found: False` payload carrying an
    absence label instead of raising or exiting -- absence is data, not a crash.

    `kits_dir` (T10, optional, default None): when given, joins session rows to a ledger by
    DATE only (see module docstring / `build_ledger_index`). A matched `session_rows` /
    `top_sessions` entry gains an optional `ledger_join` key
    (`{"label", "date", "ambiguous", "candidates"}`); nothing is added when `kits_dir` is None
    or no session's date overlaps any kit's ledger -- absent means today's behavior (D6). The
    top-level `kits_dir` key is likewise added ONLY when at least one row actually matched.

    ONE key, `_render`, holds render-only transport: `session_rows`, the UNCAPPED per-session
    view that `top_sessions` is the `top`-capped slice of. It is the only `_`-prefixed
    top-level key; everything outside it is the public card, whose per-session list is
    `top`-capped. `main --json` strips `_render`, and consumers that persist the card (the
    telemetry store) do the same -- so a 900-session home never lands an uncapped session
    list in an envelope.
    """
    session_dir = Path(session_dir)
    pricing = load_pricing()

    if not session_dir.is_dir():
        return {
            "schema_version": 1,
            "found": False,
            "days": days,
            "top": top,
            "session_dir": str(session_dir),
            "cached_date": pricing.get("cached_date"),
            "totals": {
                "usd": 0.0,
                "aic": 0.0,
                "aiu": 0.0,
                "premium_requests": 0,
                "sessions": 0,
            },
            "by_model": [],
            "per_turn_output": [],
            "top_sessions": [],
            "multi_model_sessions": 0,
            "read_errors": 0,
            "read_error_details": [],
            "unpriced_models": [],
            "downgrade_target": None,
            "downgrade_target_display": None,
            "downgrade_candidates": [],
            "downgrade_delta_total": 0.0,
            "downgrade_delta_aic": 0.0,
            "labels": [f"session-state directory absent: {session_dir}"],
            # Render-only transport (see docstring) -- never part of the public card.
            "_render": {"session_rows": []},
        }

    # T10: DATE-level ledger index, built once. None when kits_dir wasn't passed at all
    # (distinct from "built but empty" -- both degrade the same way below, but keeping None
    # distinct is what lets the top-level `kits_dir` key stay unadded when unused).
    ledger_index = build_ledger_index(kits_dir) if kits_dir is not None else None

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    sessions, read_errors = collect_sessions(session_dir)

    # Age filter mirrors cost_report: drop sessions older than the cutoff; sessions with NO
    # parseable timestamp can't be age-filtered, so they are kept regardless of `days`.
    kept = []
    for s in sessions:
        if s["last_seen"] is not None and s["last_seen"] < cutoff:
            continue
        kept.append(s)

    # Downgrade target: FIRST model in pricing-file order with tier == "mid" (computed).
    target_key = next(
        (k for k, v in pricing["models"].items() if v.get("tier") == "mid"), None
    )

    by_model = defaultdict(
        lambda: {
            "input": 0, "cache_read": 0, "cache_write": 0, "output": 0,
            "usd": 0.0, "sessions": 0, "multi": 0,
        }
    )
    per_turn_merged = defaultdict(lambda: {"turns": 0, "output_tokens": 0})
    rows = []  # per-session view for top/downgrade tables
    total_usd = 0.0
    total_aiu = 0.0
    total_premium = 0
    multi_model_sessions = 0

    for s in kept:
        eff, output_only = effective_tokens(s)
        matched_keys, attribution_key, approx = _attribute(s, pricing)

        for raw, entry in s["per_turn_output"].items():
            merged = per_turn_merged[raw]
            merged["turns"] += entry["turns"]
            merged["output_tokens"] += entry["output_tokens"]

        usd = price_tokens(eff, attribution_key, pricing) if attribution_key else 0.0
        turns = sum(v["turns"] for v in s["per_turn_output"].values())
        footprint = eff["input"] + eff["output"] + eff["cache_write"]
        aiu = s["nano_aiu"] / 1e9

        total_usd += usd
        total_aiu += aiu
        total_premium += s["premium_requests"]
        if approx:
            multi_model_sessions += 1

        if attribution_key:
            b = by_model[attribution_key]
            for f in ("input", "cache_read", "cache_write", "output"):
                b[f] += eff[f]
            b["usd"] += usd
            b["sessions"] += 1
            if approx:
                b["multi"] += 1

        rows.append({
            "session_id": s["session_id"],
            "workspace": s["workspace"],
            "models": list(s["models"]),
            "matched_keys": matched_keys,
            "eff": eff,
            "usd": usd,
            "aiu": aiu,
            "turns": turns,
            "footprint": footprint,
            "approx": approx,
            "output_only": output_only,
            "date_str": session_date(s),  # T10 ledger join key only; never rendered directly.
        })

    rows.sort(key=lambda r: -r["usd"])
    total_aic = usd_to_aic(total_usd, pricing)

    by_model_list = []
    for key, b in sorted(by_model.items(), key=lambda kv: -kv[1]["usd"]):
        by_model_list.append({
            "model": key,
            "display": pricing["models"][key]["display"],
            "sessions": b["sessions"],
            "multi": b["multi"],
            "input": b["input"],
            "cache_read": b["cache_read"],
            "cache_write": b["cache_write"],
            "output": b["output"],
            "usd": b["usd"],
            "aic": usd_to_aic(b["usd"], pricing),
        })

    per_turn_list = []
    for raw, entry in sorted(per_turn_merged.items(), key=lambda kv: -kv[1]["output_tokens"]):
        per_turn_list.append({
            "model": raw,
            "display": display_for(raw, pricing),
            "turns": entry["turns"],
            "output_tokens": entry["output_tokens"],
        })

    session_rows = []
    for r in rows:
        session_row = {
            "session_id": r["session_id"],
            "project": project_label(r["workspace"]),
            "models": list(r["models"]),
            "models_display": [display_for(m, pricing) for m in r["models"]],
            "matched_keys": r["matched_keys"],
            "tokens": dict(r["eff"]),
            "footprint": r["footprint"],
            "turns": r["turns"],
            "usd": r["usd"],
            "aic": usd_to_aic(r["usd"], pricing),
            "aiu": r["aiu"],
            "approx": r["approx"],
            "output_only": r["output_only"],
        }
        # T10: optional DATE-level ledger join -- added ONLY on an actual match, never a guess.
        if ledger_index:
            lj_candidates = ledger_index.get(r["date_str"])
            if lj_candidates:
                session_row["ledger_join"] = {
                    "label": LEDGER_JOIN_LABEL,
                    "date": r["date_str"],
                    "ambiguous": len(lj_candidates) > 1,
                    "candidates": lj_candidates,
                }
        session_rows.append(session_row)

    top_sessions = [
        {
            "session_id": row["session_id"],
            "project": row["project"],
            "models": row["models"],
            "models_display": row["models_display"],
            "footprint": row["footprint"],
            "usd": row["usd"],
            "aic": row["aic"],
            "aiu": row["aiu"],
            "approx": row["approx"],
            "output_only": row["output_only"],
            **({"ledger_join": row["ledger_join"]} if "ledger_join" in row else {}),
        }
        for row in session_rows[:top]
    ]

    candidates = [
        r for r in rows
        if target_key
        and r["matched_keys"]
        and all(
            pricing["models"][k]["tier"] in EXPENSIVE_TIERS for k in r["matched_keys"]
        )
        and r["footprint"] < DOWNGRADE_TOKEN_CEILING
        and r["turns"] < DOWNGRADE_TURN_CEILING
    ]
    downgrade_candidates = []
    delta_total = 0.0
    for r in candidates:
        on_target = price_tokens(r["eff"], target_key, pricing)
        delta = r["usd"] - on_target
        delta_total += delta
        downgrade_candidates.append({
            "session_id": r["session_id"],
            "project": project_label(r["workspace"]),
            "footprint": r["footprint"],
            "turns": r["turns"],
            "usd": r["usd"],
            "on_target_usd": on_target,
            "delta_usd": delta,
        })

    unpriced_models = [
        {"model": raw, "output_tokens": entry["output_tokens"]}
        for raw, entry in sorted(
            per_turn_merged.items(), key=lambda kv: -kv[1]["output_tokens"]
        )
        if match_model(raw, pricing) is None
    ]

    labels = ["token-priced estimate (est.) — Copilot bills in premium requests/AIC"]
    if multi_model_sessions:
        labels.append("multi-model sessions attributed to last model (≈)")

    payload = {
        "schema_version": 1,
        "found": True,
        "days": days,
        "top": top,
        "session_dir": str(session_dir),
        "cached_date": pricing.get("cached_date"),
        "totals": {
            "usd": total_usd,
            "aic": total_aic,
            "aiu": total_aiu,
            "premium_requests": total_premium,
            "sessions": len(kept),
        },
        "by_model": by_model_list,
        "per_turn_output": per_turn_list,
        "top_sessions": top_sessions,
        "multi_model_sessions": multi_model_sessions,
        "read_errors": len(read_errors),
        "read_error_details": read_errors,
        "unpriced_models": unpriced_models,
        "downgrade_target": target_key,
        "downgrade_target_display": (
            pricing["models"][target_key]["display"] if target_key else None
        ),
        "downgrade_candidates": downgrade_candidates,
        "downgrade_delta_total": delta_total,
        "downgrade_delta_aic": usd_to_aic(delta_total, pricing),
        "labels": labels,
        # Render-only transport (see docstring): the uncapped per-session view that
        # top_sessions is the top-capped slice of. Never part of the public card.
        "_render": {"session_rows": session_rows},
    }
    # T10: only added when kits_dir was passed AND at least one session actually matched --
    # a passed-but-unmatched kits_dir degrades silently, exactly like an absent one (D6).
    if kits_dir is not None and any("ledger_join" in row for row in session_rows):
        payload["kits_dir"] = str(kits_dir)
    return payload


def render_markdown(payload):
    """Render the exact markdown report from a `build_usage_payload` dict (formatting only —
    no recomputation, no pricing access)."""
    totals = payload["totals"]
    out = []

    # 1. Header + totals.
    out.append(f"# Copilot CLI usage — last {payload['days']} days\n")
    out.append(
        f"**Total priced estimate: ${totals['usd']:,.2f} ({totals['aic']:,.1f} AIC) "
        f"across {totals['sessions']} sessions.**"
    )
    out.append(
        f"Copilot-reported: {totals['aiu']:,.2f} AIU, {totals['premium_requests']:,} premium requests "
        f"(cross-check below).\n"
    )

    # 2. Spend by model.
    out.append("## Spend by model\n")
    out.append("| Model | Sessions | Input | Cache read | Cache write | Output | USD | AIC |")
    out.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for b in payload["by_model"]:
        sessions_cell = f"{b['sessions']:,}" + (" ≈" if b["multi"] else "")
        out.append(
            f"| {b['display']} | {sessions_cell} | {b['input']:,} | {b['cache_read']:,} "
            f"| {b['cache_write']:,} | {b['output']:,} | ${b['usd']:,.2f} "
            f"| {b['aic']:,.1f} |"
        )
    if payload["multi_model_sessions"]:
        out.append(
            f"\n≈ includes {payload['multi_model_sessions']} multi-model session(s) whose whole token "
            "split is attributed to the session's last model — events.jsonl does not record "
            "per-model input/cache splits; see the exact per-turn table below."
        )

    # 3. Output tokens by model (per-turn, exact).
    out.append("\n## Output tokens by model (per-turn, exact)\n")
    out.append(
        "Exact cross-model view built from assistant.message events, but output tokens only "
        "(events.jsonl carries no per-turn input/cache split)."
    )
    out.append("\n| Model | Turns | Output tokens |")
    out.append("|---|---:|---:|")
    for entry in payload["per_turn_output"]:
        out.append(
            f"| {entry['display']} | {entry['turns']:,} "
            f"| {entry['output_tokens']:,} |"
        )

    # 4. Top sessions by estimated cost.
    out.append(f"\n## Top {payload['top']} sessions by estimated cost\n")
    out.append("| Session | Project | Models | Tokens | USD | AIC | Copilot AIU |")
    out.append("|---|---|---|---:|---:|---:|---:|")
    for r in payload["top_sessions"]:
        models_disp = ", ".join(r["models_display"])
        marks = ("" if not r["approx"] else " ≈") + ("" if not r["output_only"] else " †")
        out.append(
            f"| {r['session_id'][:12]}… | {r['project'][:40]} "
            f"| {models_disp}{marks} | {r['footprint']:,} | ${r['usd']:,.2f} "
            f"| {r['aic']:,.1f} | {r['aiu']:,.2f} |"
        )
    out.append(
        "\n`≈` multi-model session attributed to its last model (approximate); "
        "`† no shutdown token details — output tokens only; input/cache unpriced (undercount)`."
    )

    # 4b. T10 ledger join (--kits-dir): rendered ONLY when a session actually matched --
    # otherwise this section is entirely absent, matching today's output byte-for-byte (D6).
    ledger_rows = [r for r in payload["top_sessions"] if "ledger_join" in r]
    if ledger_rows:
        out.append("\n## Ledger join (--kits-dir)\n")
        out.append(LEDGER_JOIN_LABEL)
        out.append(
            "\nA `run=` id carries only a DATE (PLAN D8's four hex characters are random, "
            "never a clock), so sessions are joined to ledger outcomes by same-day match "
            "only — never by time window. One run id commonly touches many tasks, so every "
            "task an outcome line recorded under the matching run is listed as a candidate, "
            "never narrowed to a single guess; more than one kit or run on the same date "
            "lists every candidate as its own row.\n"
        )
        out.append("| Session | Date | Kit | Run | Tasks touched |")
        out.append("|---|---|---|---|---|")
        for r in ledger_rows:
            lj = r["ledger_join"]
            for c in lj["candidates"]:
                out.append(
                    f"| {r['session_id'][:12]}… | {lj['date']} | {c['kit']} | {c['run']} "
                    f"| {', '.join(c['tasks'])} |"
                )
        ambiguous_n = sum(1 for r in ledger_rows if r["ledger_join"]["ambiguous"])
        if ambiguous_n:
            out.append(
                f"\n{ambiguous_n} session(s) above matched more than one kit/run on the "
                "same date — every candidate is listed as its own row, never narrowed to "
                "a single guess."
            )

    # 5. Downgrade candidates.
    out.append("\n## Downgrade candidates\n")
    candidates = payload["downgrade_candidates"]
    if not candidates:
        out.append("None found in this window.")
    else:
        target_disp = payload["downgrade_target_display"]
        out.append(
            f"| Session | Project | Tokens | Turns | USD | On {target_disp} | Delta |"
        )
        out.append("|---|---|---:|---:|---:|---:|---:|")
        for r in candidates:
            out.append(
                f"| {r['session_id'][:12]}… | {r['project'][:40]} "
                f"| {r['footprint']:,} | {r['turns']} | ${r['usd']:,.2f} "
                f"| ${r['on_target_usd']:,.2f} | ${r['delta_usd']:,.2f} |"
            )
        out.append(
            f"\n**Estimated savings on {target_disp}: ${payload['downgrade_delta_total']:,.2f} "
            f"({payload['downgrade_delta_aic']:,.1f} AIC)**"
        )

    # 6. Copilot-reported AIU cross-check.
    out.append("\n## Copilot-reported AIU cross-check\n")
    out.append(
        f"Copilot reports {totals['aiu']:,.2f} AIU and {totals['premium_requests']:,} premium requests, "
        f"next to this tool's estimate of ${totals['usd']:,.2f} ({totals['aic']:,.1f} AIC).\n"
    )
    out.append(
        "AIU is Copilot's own reported consumption unit; it is NOT assumed equal to the AIC "
        "billing unit in data/pricing.copilot.json. The authoritative estimate above is token "
        "counts × per-MTok rates → USD → AIC via billing_unit.usd_per_credit. AIU is never "
        "converted to USD or AIC here."
    )

    # 7. Unpriced models (only when present).
    unpriced = payload["unpriced_models"]
    if unpriced:
        out.append("\n## Unpriced models (not in pricing.copilot.json)\n")
        for u in unpriced:
            out.append(
                f"- `{u['model']}`: {u['output_tokens']:,} output tokens (per-turn; cost not counted)"
            )

    # 8. Read errors (only when present).
    if payload["read_error_details"]:
        out.append("\n## Read errors\n")
        for e in payload["read_error_details"]:
            out.append(f"- {e}")

    # 9. Footer.
    out.append(
        f"\n*Prices cached {payload['cached_date']} from pricing.copilot.json; costs are "
        "token-priced estimates, not bills. Event format observed on Copilot CLI v1.0.68.*"
    )

    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="copilot_usage.py",
        description="Copilot CLI usage report from session-state event logs (read-only).",
    )
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--copilot-home", default=str(DEFAULT_COPILOT_HOME))
    ap.add_argument(
        "--session-dir",
        default=None,
        help="a session-state-shaped directory; overrides <copilot-home>/session-state",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="emit the machine-readable build_usage_payload dict instead of markdown",
    )
    ap.add_argument(
        "--kits-dir",
        default=None,
        help=(
            "T10: optional directory of kit dirs (each holding TASKS.md/NOTES.md) to join "
            "sessions against by same-day run= id match. Never set by default; omitting it "
            "leaves output exactly as before (D6)."
        ),
    )
    args = ap.parse_args(argv)

    if args.session_dir:
        session_dir = Path(args.session_dir)
    else:
        session_dir = Path(args.copilot_home) / "session-state"

    if args.json:
        payload = build_usage_payload(
            session_dir, days=args.days, top=args.top, kits_dir=args.kits_dir
        )
        # The public card only: _render is internal markdown transport, and emitting it
        # would put an uncapped per-session list into machine-readable output.
        print(json.dumps(
            {k: v for k, v in payload.items() if k != "_render"}, indent=2
        ))
        return

    if not session_dir.is_dir():
        sys.exit(f"No session-state directory at {session_dir}")

    payload = build_usage_payload(
        session_dir, days=args.days, top=args.top, kits_dir=args.kits_dir
    )
    print(render_markdown(payload))


if __name__ == "__main__":
    main()
