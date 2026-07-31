#!/usr/bin/env python3
"""Historical Claude Code cost report.

Walks ~/.claude/projects/**/*.jsonl transcripts, extracts per-message usage
(model, input/output/cache tokens), dedupes by message id, and prices
everything from the plugin's data/pricing.json. Emits markdown.

Usage: cost_report.py [--days N] [--mode api|subscription] [--top N]
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
PRICING_PATH = PLUGIN_ROOT / "data" / "pricing.json"


def _default_projects_dir():
    """Transcripts live under ``<config-dir>/projects``. Honor ``CLAUDE_CONFIG_DIR``
    (Claude Code's config-home override) when set, else the stock ``~/.claude``."""
    cfg = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    base = Path(cfg).expanduser() if cfg else Path.home() / ".claude"
    return base / "projects"


PROJECTS_DIR = _default_projects_dir()

DOWNGRADE_TOKEN_CEILING = 50_000
DOWNGRADE_TOOL_CEILING = 10
DOWNGRADE_TARGET = "claude-sonnet-5"
EXPENSIVE_TIERS = {"frontier", "opus"}


def load_pricing():
    with open(PRICING_PATH) as f:
        return json.load(f)


def match_model(model_id, pricing):
    """Map a raw model string (may carry [1m] or date suffixes) to a pricing key."""
    if not model_id or model_id.startswith("<"):
        return None
    base = model_id.split("[")[0].strip()
    for key in pricing["models"]:
        if base == key or base.startswith(key + "-"):
            return key
    return None


def rates_for(key, when, pricing):
    m = pricing["models"][key]
    inp, outp = m["input_per_mtok"], m["output_per_mtok"]
    intro = m.get("intro_pricing")
    if intro and when is not None:
        try:
            if when.date() <= date.fromisoformat(intro["until"]):
                inp, outp = intro["input_per_mtok"], intro["output_per_mtok"]
        except ValueError:
            pass
    return inp, outp


def price(key, u, when, pricing):
    inp, outp = rates_for(key, when, pricing)
    return (
        u["input"] * inp
        + u["output"] * outp
        + u["cache_read"] * inp * pricing["cache_read_multiplier"]
        + u["cache_write"] * inp * pricing["cache_write_multiplier_5m"]
    ) / 1e6


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


def extract_record(obj):
    """Return (model, usage_dict, message_id, tool_uses) or None."""
    if not isinstance(obj, dict):
        return None
    msg = obj.get("message") if isinstance(obj.get("message"), dict) else None
    usage = None
    model = None
    msg_id = None
    tool_uses = 0
    if msg:
        usage = msg.get("usage")
        model = msg.get("model")
        msg_id = msg.get("id")
        content = msg.get("content")
        if isinstance(content, list):
            tool_uses = sum(
                1 for b in content if isinstance(b, dict) and b.get("type") == "tool_use"
            )
    if usage is None and isinstance(obj.get("usage"), dict):
        usage = obj["usage"]
        model = obj.get("model")
    if not isinstance(usage, dict) or not model:
        return None
    u = {
        "input": usage.get("input_tokens") or 0,
        "output": usage.get("output_tokens") or 0,
        "cache_read": usage.get("cache_read_input_tokens") or 0,
        "cache_write": usage.get("cache_creation_input_tokens") or 0,
    }
    if not any(u.values()):
        return None
    return model, u, msg_id, tool_uses


def new_bucket():
    return {
        "input": 0, "output": 0, "cache_read": 0, "cache_write": 0,
        "cost": 0.0, "messages": 0,
    }


def build_report_payload(projects_dir, days=30, top=10, mode=None):
    """Scan/aggregate transcripts into a pure, JSON-serializable payload.

    Never exits, never prints — the sole scan/price/aggregate pass that both
    the markdown renderer and ``--json`` draw from (PLAN D3). ``mode=None``
    resolves from pricing exactly as the CLI does. Missing ``projects_dir``
    yields an honest ``found: False`` payload rather than raising.

    ``found`` means EVIDENCE PRESENT — at least one record priced inside the
    ``days`` window — not merely "the directory exists". A present-but-empty
    transcript dir, or one whose every record falls outside ``--days``, is
    ``found: False`` with a ``no transcripts in window`` label: zeros with no
    measurement behind them are absence, never a measured zero (GUARDRAILS:
    "absence of evidence is written down AS absence"). The two absence causes
    keep two distinct labels so a missing dir stays distinguishable from an
    empty one. ``dir_present`` records the directory's existence on its own,
    which is what the CLI's markdown/exit gate keys off (an empty-but-present
    dir still renders its zero-row markdown report, byte-identical to before).
    """
    projects_dir = Path(projects_dir)
    pricing = load_pricing()
    mode = mode or pricing.get("billing_mode", "api")
    labels = [f"billing mode: {mode}", "API-list estimates, not bills (est.)"]

    if not projects_dir.is_dir():
        labels.insert(0, f"transcript directory absent: {projects_dir}")
        return {
            "schema_version": 1,
            "found": False,
            "dir_present": False,
            "days": days,
            "top": top,
            "mode": mode,
            "projects_dir": str(projects_dir),
            "pricing_cached_date": pricing.get("cached_date"),
            "totals": {"usd": 0.0, "sessions": 0, "tokens": 0},
            "by_model": [],
            "sessions": [],
            "downgrade_candidates": [],
            "downgrade_savings_usd": 0.0,
            "unknown_models": [],
            "parse_errors": 0,
            "parse_error_details": [],
            "labels": labels,
        }

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    seen_ids = set()
    by_model = defaultdict(new_bucket)
    sessions = defaultdict(lambda: {
        "models": set(), "cost": 0.0, "sonnet5_cost": 0.0, "tokens": 0,
        "tool_uses": 0, "last_seen": None, "project": "",
    })
    unknown_models = defaultdict(int)
    parse_errors = []

    for path in sorted(projects_dir.rglob("*.jsonl")):
        project = path.relative_to(projects_dir).parts[0]
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError as e:
            parse_errors.append(f"{path}: {e}")
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            rec = extract_record(obj)
            if rec is None:
                continue
            model, u, msg_id, tool_uses = rec
            when = parse_timestamp(obj.get("timestamp"))
            # Records with no parseable timestamp can't be age-filtered: they are kept
            # regardless of --days and priced at base (non-intro) rates.
            if when is not None and when < cutoff:
                continue
            if msg_id:
                if msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)
            key = match_model(model, pricing)
            if key is None:
                if not model.startswith("<"):
                    unknown_models[model] += sum(u.values())
                continue

            cost = price(key, u, when, pricing)
            b = by_model[key]
            for f in ("input", "output", "cache_read", "cache_write"):
                b[f] += u[f]
            b["cost"] += cost
            b["messages"] += 1

            sid = obj.get("sessionId") or path.stem
            s = sessions[sid]
            s["models"].add(key)
            s["cost"] += cost
            s["sonnet5_cost"] += price(DOWNGRADE_TARGET, u, when, pricing)
            s["tokens"] += u["input"] + u["output"] + u["cache_write"]
            s["tool_uses"] += tool_uses
            s["project"] = project
            if when and (s["last_seen"] is None or when > s["last_seen"]):
                s["last_seen"] = when

    total_cost = sum(b["cost"] for b in by_model.values())
    total_tokens = sum(b["input"] + b["output"] + b["cache_write"] for b in by_model.values())

    by_model_list = [
        {
            "model": key,
            "display": pricing["models"][key]["display"],
            "messages": b["messages"],
            "input": b["input"],
            "output": b["output"],
            "cache_read": b["cache_read"],
            "cache_write": b["cache_write"],
            "usd": b["cost"],
        }
        for key, b in sorted(by_model.items(), key=lambda kv: -kv[1]["cost"])
    ]

    ranked = sorted(sessions.items(), key=lambda kv: -kv[1]["cost"])
    sessions_list = [
        {
            "session_id": sid,
            "project": s["project"],
            "models": sorted(s["models"]),
            "tokens": s["tokens"],
            "usd": s["cost"],
        }
        for sid, s in ranked[:top]
    ]

    candidates = [
        (sid, s) for sid, s in ranked
        if s["models"]
        and all(pricing["models"][k]["tier"] in EXPENSIVE_TIERS for k in s["models"])
        and s["tokens"] < DOWNGRADE_TOKEN_CEILING
        and s["tool_uses"] < DOWNGRADE_TOOL_CEILING
    ]
    downgrade_candidates = [
        {
            "session_id": sid,
            "project": s["project"],
            "tokens": s["tokens"],
            "tool_uses": s["tool_uses"],
            "usd": s["cost"],
            "sonnet5_usd": s["sonnet5_cost"],
            "delta_usd": s["cost"] - s["sonnet5_cost"],
        }
        for sid, s in candidates
    ]
    downgrade_savings_usd = sum(c["delta_usd"] for c in downgrade_candidates)

    unknown_models_list = [
        {"model": m, "tokens": toks}
        for m, toks in sorted(unknown_models.items(), key=lambda kv: -kv[1])
    ]

    # Evidence, not directory existence: at least one record priced inside the window.
    found = bool(by_model_list)
    if not found:
        labels.insert(0, f"no transcripts in window: {projects_dir}")

    if unknown_models_list:
        labels.append("unpriced models present")

    return {
        "schema_version": 1,
        "found": found,
        "dir_present": True,
        "days": days,
        "top": top,
        "mode": mode,
        "projects_dir": str(projects_dir),
        "pricing_cached_date": pricing.get("cached_date"),
        "totals": {
            "usd": total_cost,
            "sessions": len(sessions),
            "tokens": total_tokens,
        },
        "by_model": by_model_list,
        "sessions": sessions_list,
        "downgrade_candidates": downgrade_candidates,
        "downgrade_savings_usd": downgrade_savings_usd,
        "unknown_models": unknown_models_list,
        "parse_errors": len(parse_errors),
        "parse_error_details": parse_errors,
        "labels": labels,
    }


def render_markdown(payload):
    """Render the markdown report from a payload built by build_report_payload.
    Prints to stdout; assumes payload["found"] is True (callers check first)."""
    mode = payload["mode"]
    cost_word = "API-equivalent burn" if mode == "subscription" else "spend"
    display_by_key = {b["model"]: b["display"] for b in payload["by_model"]}

    print(f"# Claude Code usage — last {payload['days']} days ({mode} mode)\n")
    print(f"**Total {cost_word}: ${payload['totals']['usd']:,.2f}** across "
          f"{payload['totals']['sessions']} sessions.\n")

    print("## By model\n")
    print("| Model | Messages | Input | Output | Cache read | Cache write | Cost |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for b in payload["by_model"]:
        print(f"| {b['display']} | {b['messages']:,} | {b['input']:,} | {b['output']:,} "
              f"| {b['cache_read']:,} | {b['cache_write']:,} | ${b['usd']:,.2f} |")

    print(f"\n## Top {payload['top']} sessions by cost\n")
    print("| Session | Project | Models | Tokens | Cost |")
    print("|---|---|---|---:|---:|")
    for s in payload["sessions"]:
        models = ", ".join(display_by_key[k] for k in s["models"])
        print(f"| {s['session_id'][:12]}… | {s['project'][:40]} | {models} "
              f"| {s['tokens']:,} | ${s['usd']:,.2f} |")

    print("\n## Downgrade candidates (Fable/Opus sessions with a Sonnet-sized footprint)\n")
    candidates = payload["downgrade_candidates"]
    if not candidates:
        print("None found in this window.")
    else:
        delta_total = payload["downgrade_savings_usd"]
        print("| Session | Project | Tokens | Tool calls | Cost | On Sonnet 5 | Delta |")
        print("|---|---|---:|---:|---:|---:|---:|")
        for c in candidates:
            print(f"| {c['session_id'][:12]}… | {c['project'][:40]} | {c['tokens']:,} "
                  f"| {c['tool_uses']} | ${c['usd']:,.2f} | ${c['sonnet5_usd']:,.2f} "
                  f"| ${c['delta_usd']:,.2f} |")
        if mode == "subscription":
            print(f"\nThese sessions spent rate-limit budget on Fable/Opus for "
                  f"Sonnet-sized work (${delta_total:,.2f} API-equivalent).")
        else:
            print(f"\n**Estimated savings on Sonnet 5: ${delta_total:,.2f}**")

    if payload["unknown_models"]:
        print("\n## Unpriced models (not in pricing.json)\n")
        for u in payload["unknown_models"]:
            print(f"- `{u['model']}`: {u['tokens']:,} tokens (cost not counted)")

    if payload["parse_error_details"]:
        print("\n## Read errors\n")
        for e in payload["parse_error_details"]:
            print(f"- {e}")

    print(f"\n*Prices cached {payload['pricing_cached_date']} from pricing.json; "
          f"costs are API-list estimates, not bills.*")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--mode", choices=["api", "subscription"], default=None)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--projects-dir", default=None)
    args = ap.parse_args(argv)

    projects_dir = Path(args.projects_dir) if args.projects_dir else PROJECTS_DIR

    payload = build_report_payload(projects_dir, days=args.days, top=args.top, mode=args.mode)

    if args.json:
        print(json.dumps(payload, indent=2))
        return

    # The markdown gate is DIRECTORY existence, not evidence: a present-but-empty dir has
    # always rendered its zero-row report and still must, byte for byte. Only a missing
    # directory exits (unchanged message, unchanged exit code).
    if not payload["dir_present"]:
        sys.exit(f"No transcript directory at {projects_dir}")

    render_markdown(payload)


if __name__ == "__main__":
    main()
