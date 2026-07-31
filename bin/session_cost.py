#!/usr/bin/env python3
"""Per-session Claude Code cost + a model counterfactual.

Aggregates ONE session's transcripts — the main
``~/.claude/projects/<slug>/<session-id>.jsonl`` plus any subagent transcripts
the Task tool writes (per-agent ``*.output`` JSONL files, which do NOT live under
``~/.claude/projects``) — deduped by message id, prices each model from
``data/pricing.json``, and computes a counterfactual: what the SAME token volume
would have cost if every token had run on one model (default: the frontier-tier
model, e.g. Fable 5). This is how you compare "the model-mix workflow" against
"one expensive model as the primary driver."

Pricing and transcript parsing are reused verbatim from ``bin/cost_report.py``
(the single source of truth) — this module adds only session scoping, subagent
aggregation, and the counterfactual.

Read-only: it opens transcript files for reading, never writes anything, and
never invokes any model. The counterfactual holds token VOLUME constant and
prices the counterfactual model at base (non-intro) rates.

Usage:
  session_cost.py [--session ID] [--vs MODEL_ID] [--tasks-dir DIR ...]
                  [--include PATH/GLOB ...] [--no-subagents]
                  [--projects-dir DIR] [--mode api|subscription] [--json]

Default session = the most recently modified transcript under the projects dir.
"""

import argparse
import importlib.util
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_COST_REPORT_PATH = PLUGIN_ROOT / "bin" / "cost_report.py"
def _default_projects_dir():
    """Transcripts live under ``<config-dir>/projects``. Honor ``CLAUDE_CONFIG_DIR``
    (Claude Code's config-home override) when set, else the stock ``~/.claude``. This
    keeps ``--projects-dir`` optional for users running under a non-default config home."""
    cfg = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    base = Path(cfg).expanduser() if cfg else Path.home() / ".claude"
    return base / "projects"


DEFAULT_PROJECTS_DIR = _default_projects_dir()

# Best-effort bases for the Task tool's per-subagent transcript scratchpad
# (`<base>/claude-*/<project-slug>/<session-id>/tasks/*.output`). Explicit
# --tasks-dir / --include is the reliable path; this is only for convenience.
_TMP_BASES = (os.environ.get("TMPDIR"), "/tmp", "/private/tmp")


def _load_cost_report():
    spec = importlib.util.spec_from_file_location("cost_report", _COST_REPORT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cr = _load_cost_report()


def find_main_transcript(session_id, projects_dir):
    """Locate the main session transcript. If session_id is None, pick the most
    recently modified ``*.jsonl`` under projects_dir."""
    projects_dir = Path(projects_dir)
    if not projects_dir.is_dir():
        return None
    if session_id:
        for p in sorted(projects_dir.rglob(f"{session_id}.jsonl")):
            return p
        return None
    candidates = [p for p in projects_dir.rglob("*.jsonl")]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def discover_task_dirs(session_id, bases=_TMP_BASES):
    """Best-effort discovery of the subagent-transcript ``tasks`` dirs for a
    session id. Returns existing dirs only; empty when nothing matches."""
    if not session_id:
        return []
    found, seen = [], set()
    for base in bases:
        if not base:
            continue
        b = Path(base)
        if not b.is_dir():
            continue
        try:
            matches = b.glob(f"claude-*/*/{session_id}/tasks")
        except OSError:
            continue
        for d in matches:
            rp = d.resolve()
            if d.is_dir() and rp not in seen:
                seen.add(rp)
                found.append(d)
    return found


def gather_files(main_transcript, task_dirs, includes):
    """Build the ordered, de-duplicated list of transcript files to scan."""
    files = []
    if main_transcript:
        files.append(Path(main_transcript))
    for d in task_dirs:
        files.extend(sorted(Path(d).glob("*.output")))
    for item in includes:
        p = Path(item)
        if p.is_dir():
            files.extend(sorted(p.glob("*.output")))
        elif any(ch in str(item) for ch in "*?["):
            files.extend(sorted(Path().glob(str(item))))
        elif p.exists():
            files.append(p)
    out, seen = [], set()
    for f in files:
        try:
            rp = f.resolve()
        except OSError:
            rp = f
        if rp not in seen:
            seen.add(rp)
            out.append(f)
    return out


def _new_bucket():
    return {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0,
            "cost": 0.0, "msgs": 0}


def collect(files, pricing):
    """Stream every transcript file, dedupe records by message id GLOBALLY (so a
    message recorded in both the main transcript and a subagent file counts
    once), and accumulate per-model token totals + priced cost + grand totals."""
    seen_ids = set()
    by_model = defaultdict(_new_bucket)
    grand = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    unpriced = defaultdict(int)
    read_errors = []
    files_read = 0
    for f in files:
        try:
            fh = open(f, errors="replace")
        except OSError as e:
            read_errors.append(f"{f}: {e}")
            continue
        files_read += 1
        with fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rec = cr.extract_record(obj)
                if rec is None:
                    continue
                model, u, msg_id, _tool_uses = rec
                if msg_id:
                    if msg_id in seen_ids:
                        continue
                    seen_ids.add(msg_id)
                key = cr.match_model(model, pricing)
                if key is None:
                    if not str(model).startswith("<"):
                        unpriced[model] += sum(u.values())
                    continue
                when = cr.parse_timestamp(obj.get("timestamp"))
                cost = cr.price(key, u, when, pricing)
                b = by_model[key]
                for fld in ("input", "output", "cache_read", "cache_write"):
                    b[fld] += u[fld]
                    grand[fld] += u[fld]
                b["cost"] += cost
                b["msgs"] += 1
    return {
        "by_model": dict(by_model),
        "grand": grand,
        "unpriced": dict(unpriced),
        "read_errors": read_errors,
        "files_read": files_read,
        "unique_messages": len(seen_ids),
    }


def resolve_counterfactual_model(arg, pricing):
    """The model whose rate the whole volume is repriced at. Explicit id via
    --vs; otherwise the first frontier-tier model in the pricing file."""
    if arg:
        key = cr.match_model(arg, pricing)
        if key is None:
            raise ValueError(f"--vs model {arg!r} is not a model in pricing.json")
        return key
    for k, v in pricing["models"].items():
        if v.get("tier") == "frontier":
            return k
    return max(pricing["models"],
              key=lambda k: pricing["models"][k].get("output_per_mtok", 0))


def build_report(data, cf_key, pricing, mode):
    by_model = data["by_model"]
    grand = data["grand"]
    actual_total = sum(b["cost"] for b in by_model.values())
    cf_total = cr.price(cf_key, grand, None, pricing)
    rows = []
    for key, b in sorted(by_model.items(), key=lambda kv: -kv[1]["cost"]):
        rows.append({
            "key": key,
            "display": pricing["models"][key]["display"],
            "msgs": b["msgs"],
            "tokens": {k: b[k] for k in ("input", "output", "cache_read", "cache_write")},
            "actual_usd": b["cost"],
            "at_counterfactual_usd": cr.price(cf_key, b, None, pricing),
        })
    return {
        "rows": rows,
        "actual_total": actual_total,
        "cf_total": cf_total,
        "cf_key": cf_key,
        "cf_display": pricing["models"][cf_key]["display"],
        "grand": grand,
        "savings": cf_total - actual_total,
        "ratio": (cf_total / actual_total) if actual_total else None,
        "mode": mode,
    }


def render_markdown(rep, data, session_id, subagent_count, pricing):
    g = rep["grand"]
    out = [f"# Session cost — {session_id}\n"]
    src = (f"Scanned {data['files_read']} transcript(s), "
           f"{data['unique_messages']:,} unique priced messages — main session")
    if subagent_count > 0:
        src += f" + {subagent_count} subagent transcript(s)."
    else:
        src += (" only. No subagent transcripts were found, so delegated "
                "subagent work is NOT included — this is a driver-only lower bound "
                "(pass --tasks-dir to fold them in).")
    out.append(src + "\n")

    out.append(f"| Model | Msgs | Input | Cache read | Cache write | Output "
               f"| Actual $ | @ {rep['cf_display']} $ |")
    out.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in rep["rows"]:
        t = r["tokens"]
        out.append(
            f"| {r['display']} | {r['msgs']:,} | {t['input']:,} | {t['cache_read']:,} "
            f"| {t['cache_write']:,} | {t['output']:,} | ${r['actual_usd']:,.2f} "
            f"| ${r['at_counterfactual_usd']:,.2f} |"
        )
    out.append(
        f"| **Total** |  | {g['input']:,} | {g['cache_read']:,} | {g['cache_write']:,} "
        f"| {g['output']:,} | **${rep['actual_total']:,.2f}** | **${rep['cf_total']:,.2f}** |"
    )

    if rep["ratio"]:
        pct = (1 - rep["actual_total"] / rep["cf_total"]) * 100 if rep["cf_total"] else 0
        out.append(
            f"\n**Actual (mixed workflow): ${rep['actual_total']:,.2f}**  ·  "
            f"**All {rep['cf_display']}: ${rep['cf_total']:,.2f}**  ·  "
            f"**Δ ${rep['savings']:,.2f} — {rep['ratio']:.2f}× "
            f"({pct:.0f}% cheaper than {rep['cf_display']}-only)**"
        )
    else:
        out.append(f"\n**Actual: ${rep['actual_total']:,.2f}** (no priced usage to compare).")

    if rep["mode"] == "subscription":
        out.append("\n*Subscription mode: the marginal cost was $0 either way — these "
                   "are API-equivalent dollars (the pay-per-token picture).*")

    if data["unpriced"]:
        out.append("\n## Unpriced models (not in pricing.json)\n")
        for m, toks in sorted(data["unpriced"].items(), key=lambda kv: -kv[1]):
            out.append(f"- `{m}`: {toks:,} tokens (not counted)")
    if data["read_errors"]:
        out.append("\n## Read errors\n")
        for e in data["read_errors"]:
            out.append(f"- {e}")

    out.append(f"\n*Prices cached {pricing['cached_date']} from pricing.json; the "
               f"counterfactual holds token volume constant and prices "
               f"{rep['cf_display']} at base rates. Estimates, not bills.*")
    return "\n".join(out)


def build_json(rep, data, session_id, subagent_count):
    return {
        "session": session_id,
        "mode": rep["mode"],
        "sources": {
            "files_scanned": data["files_read"],
            "unique_messages": data["unique_messages"],
            "subagent_transcripts": subagent_count,
        },
        "counterfactual_model": {"key": rep["cf_key"], "display": rep["cf_display"]},
        "by_model": rep["rows"],
        "totals": {
            "actual_usd": rep["actual_total"],
            "counterfactual_usd": rep["cf_total"],
            "delta_usd": rep["savings"],
            "ratio": rep["ratio"],
            "grand_tokens": rep["grand"],
        },
        "unpriced": data["unpriced"],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Per-session Claude Code cost + a model counterfactual.")
    ap.add_argument("--session", default=None,
                    help="session id (default: most recently modified transcript)")
    ap.add_argument("--vs", default=None,
                    help="counterfactual model id to reprice all tokens at "
                         "(default: the frontier-tier model)")
    ap.add_argument("--projects-dir", default=str(DEFAULT_PROJECTS_DIR))
    ap.add_argument("--tasks-dir", action="append", default=[],
                    help="dir of subagent *.output transcripts (repeatable)")
    ap.add_argument("--include", action="append", default=[],
                    help="extra transcript file/dir/glob to fold in (repeatable)")
    ap.add_argument("--no-subagents", action="store_true",
                    help="analyze only the main transcript")
    ap.add_argument("--mode", choices=["api", "subscription"], default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    pricing = cr.load_pricing()
    mode = args.mode or pricing.get("billing_mode", "api")

    main_transcript = find_main_transcript(args.session, args.projects_dir)
    if main_transcript is None:
        sys.exit(f"No transcript found for session "
                 f"{args.session or '(latest)'} under {args.projects_dir}")
    session_id = args.session or main_transcript.stem

    task_dirs = []
    if not args.no_subagents:
        task_dirs = ([Path(d) for d in args.tasks_dir]
                     or discover_task_dirs(session_id))
    files = gather_files(main_transcript, task_dirs, args.include)
    subagent_count = max(0, len(files) - 1)

    data = collect(files, pricing)
    try:
        cf_key = resolve_counterfactual_model(args.vs, pricing)
    except ValueError as e:
        sys.exit(str(e))
    rep = build_report(data, cf_key, pricing, mode)

    if args.json:
        print(json.dumps(build_json(rep, data, session_id, subagent_count), indent=2))
    else:
        print(render_markdown(rep, data, session_id, subagent_count, pricing))
    return 0


if __name__ == "__main__":
    main()
