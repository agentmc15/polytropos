#!/usr/bin/env python3
"""daily-journal deterministic collector CLI (schema_version 1).

Assembles the day's ``digest.json`` by driving the ``journal_sources`` adapters over the
configured source roots and pre-structuring four next-day signal families — open kit tasks,
the local inbox, uncommitted work (WIP), and advisory harness-routing signals (``harness``,
computed by ``journal_advisor.build_harness_signal``; an advisor crash degrades to a
``harness_error`` string and the run continues). It is cheap, model-free, and ALWAYS runs: the
nightly schedule still produces a complete structured record even when a source is broken (an
adapter error lands IN the digest and the run continues) and the separate summarizer is a pure
consumer of the file this writes.

STRICTLY READ-ONLY ingestion. The ONE and ONLY filesystem WRITE this tool performs is the
digest under ``--journal-dir`` (created with ``mkdir(parents=True)``); nothing is ever written
under a Claude / Copilot / Codex source root, no ``*.db`` / SQLite file is ever opened, and no
``claude`` / ``copilot`` / ``codex`` / ``git`` model or CLI is ever invoked to GATHER (the git
adapter's read-only plumbing lives in ``journal_sources`` and mutates nothing). No model, no
network, ever. ``data/pricing.codex.json`` is now loaded (alongside the Claude and Copilot
pricing files) solely to price the day's Codex rollouts as a clearly-labeled API-equivalent
relative-burn proxy — never a bill.

CONTENT HYGIENE (PLAN.md D4): the digest is METADATA ONLY — no transcript or message text ever
enters it. The only free-text that lands here is commit subjects, kit task TITLES (never task
briefs, never NOTES.md / PLAN.md content), inbox lines (user-authored), project / repo names,
and error strings. This is the no-secrets-in-the-journal guarantee made structural.

The three ``.claude`` / ``.copilot`` / ``.codex`` roots are the ONLY home-directory reads in
this file (the journal and kits roots derive from the plugin root instead). Every test and
verify command overrides every root flag to a synthetic ``tempfile`` fixture — execution never
touches a real home directory.
"""

import argparse
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JOURNAL_DIR = PLUGIN_ROOT / "journal"

# The THREE runtime-default source roots below are the ONLY home-directory reads in this file.
# They are runtime defaults for the user's real machine; every test and verify command
# overrides them with --claude-projects / --copilot-home / --codex-home pointed at temp
# fixtures, so execution never reads a real home directory.
DEFAULT_CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"
DEFAULT_COPILOT_HOME = Path.home() / ".copilot"
DEFAULT_CODEX_HOME = Path.home() / ".codex"

DEFAULT_KITS_DIR = PLUGIN_ROOT / ".claude" / "kits"

MAX_KIT_TASKS = 100
MAX_INBOX_ITEMS = 100
SCHEMA_VERSION = 1

INBOX_MARKERS = ("- ", "* ", "[ ] ")


def _load(name):
    """Load a sibling ``bin/<name>.py`` module read-only (the session_cost.py pattern)."""
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parent / f"{name}.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


js = _load("journal_sources")   # the adapter engine (day_window, run_adapters, ADAPTERS)
cr = _load("cost_report")       # Claude Code pricing (read-only reuse)
cu = _load("copilot_usage")     # Copilot CLI pricing (read-only reuse)
cxu = _load("codex_usage")      # Codex pricing loader (read-only reuse)
ce = _load("copilot_execute")   # kit TASKS.md parser (parse_tasks, read-only reuse)
ja = _load("journal_advisor")   # harness routing signals (advisory-only)


# --------------------------------------------------------------------------- pure helpers

def load_config(path):
    """Read ``journal/config.json`` into ``(config, notes)``.

    Missing file -> ``({}, [])``. Invalid JSON or a non-object top level -> ``({}, [note])``.
    The only recognized key is ``"repos"`` (a list of path strings -> ``Path`` objects);
    every unknown key is ignored (v1 keeps the config surface tiny on purpose).
    """
    path = Path(path)
    if not path.is_file():
        return {}, []
    try:
        raw = json.loads(path.read_text(errors="replace"))
    except (OSError, ValueError) as e:
        return {}, [f"config unreadable: {e}"]
    if not isinstance(raw, dict):
        return {}, ["config unreadable: top-level JSON is not an object"]
    config = {}
    repos = raw.get("repos")
    if isinstance(repos, list):
        config["repos"] = [Path(r) for r in repos if isinstance(r, str)]
    return config, []


def read_inbox(path):
    """Parse ``journal/inbox.md`` into the pinned inbox signal dict.

    Blank lines and lines starting ``#`` are skipped; one leading ``- ``/``* ``/``[ ] ``
    marker is stripped. Capped at ``MAX_INBOX_ITEMS`` (``truncated`` set when exceeded). These
    are user-authored lines — the one place a person drops meeting notes / email to-dos today
    (and where a future Graph/MCP connector would land its items).
    """
    path = Path(path)
    result = {"present": False, "path": str(path), "items": [], "truncated": False}
    if not path.is_file():
        return result
    result["present"] = True
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return result
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        for marker in INBOX_MARKERS:
            if line.startswith(marker):
                line = line[len(marker):].strip()
                break
        if len(result["items"]) >= MAX_INBOX_ITEMS:
            result["truncated"] = True
            break
        result["items"].append(line)
    return result


def scan_kit_tasks(kits_dir):
    """Scan every ``<kits_dir>/*/TASKS.md`` for OPEN kit tasks -> ``(items, errors)``.

    Reuses ``ce.parse_tasks`` (the single kit-task format authority). Keeps only tasks whose
    status is ``pending`` or ``in-progress``, as ``{"kit", "id", "title", "status", "model"}``
    — TITLES ONLY, never briefs (content hygiene, PLAN.md D4). A malformed TASKS.md lands one
    error entry naming the kit and the scan continues. Capped at ``MAX_KIT_TASKS`` total.
    """
    kits_dir = Path(kits_dir)
    items = []
    errors = []
    for tasks_path in sorted(kits_dir.glob("*/TASKS.md")):
        kit_name = tasks_path.parent.name
        try:
            tasks = ce.parse_tasks(tasks_path.read_text(errors="replace"))
        except (ValueError, OSError) as e:
            errors.append(f"{kit_name}: {e}")
            continue
        for t in tasks:
            if t.get("status") not in ("pending", "in-progress"):
                continue
            if len(items) >= MAX_KIT_TASKS:
                return items, errors
            items.append({
                "kit": kit_name,
                "id": t.get("id"),
                "title": t.get("title"),
                "status": t.get("status"),
                "model": t.get("model"),
            })
    return items, errors


def build_wip(git_report):
    """Uncommitted-work signal: one entry per repo with dirty and/or untracked files."""
    wip = []
    for r in (git_report.get("extra") or {}).get("repos", []):
        dirty = r.get("dirty_files", 0)
        untracked = r.get("untracked", 0)
        if dirty + untracked > 0:
            wip.append({
                "repo": Path(r.get("root", "")).name,
                "branch": r.get("branch", ""),
                "dirty_files": dirty,
                "untracked": untracked,
            })
    return wip


def _commit_count(report):
    """Total commits recorded across a report's repos (0 for non-git sources)."""
    return sum(r.get("commit_count", 0)
               for r in (report.get("extra") or {}).get("repos", []))


def build_digest(reports, day_start, day_end, date_str, signals):
    """Assemble the pinned schema_version-1 digest (PLAN.md D4).

    ``totals``: ``usd_priced`` sums each source's non-None ``usd``; ``sessions`` sums them;
    ``sources_active`` is every available source with real activity (sessions or git commits);
    ``unpriced_sources`` is every available source with ``priced`` False (Codex + git).
    """
    usd_priced = sum(rep["usd"] for rep in reports.values() if rep.get("usd") is not None)
    sessions = sum(rep.get("sessions", 0) for rep in reports.values())
    sources_active = [
        name for name, rep in reports.items()
        if rep.get("available") and (rep.get("sessions", 0) > 0 or _commit_count(rep) > 0)
    ]
    unpriced_sources = [
        name for name, rep in reports.items()
        if rep.get("available") and not rep.get("priced")
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "date": date_str,
        "generated_at": datetime.now().astimezone().isoformat(),
        "day_start": day_start.isoformat(),
        "day_end": day_end.isoformat(),
        "timezone": str(day_start.tzinfo),
        "sources": reports,
        "totals": {
            "usd_priced": usd_priced,
            "sessions": sessions,
            "sources_active": sources_active,
            "unpriced_sources": unpriced_sources,
        },
        "signals": signals,
    }


# --------------------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Assemble the daily-journal digest.json (deterministic, model-free, "
                    "strictly read-only ingestion).")
    ap.add_argument("--date", default=None,
                    help="day to collect, YYYY-MM-DD (default: today)")
    ap.add_argument("--utc", action="store_true",
                    help="compute the day window in UTC (tests/verifies always use this)")
    ap.add_argument("--journal-dir", default=str(DEFAULT_JOURNAL_DIR),
                    help="output root (the ONLY thing this tool writes)")
    ap.add_argument("--claude-projects", default=str(DEFAULT_CLAUDE_PROJECTS))
    ap.add_argument("--copilot-home", default=str(DEFAULT_COPILOT_HOME))
    ap.add_argument("--codex-home", default=str(DEFAULT_CODEX_HOME))
    ap.add_argument("--repo", action="append", default=[],
                    help="a git repo root to scan (repeatable; adds to config repos)")
    ap.add_argument("--config", default=None,
                    help="config.json path (default: <journal-dir>/config.json)")
    ap.add_argument("--inbox", default=None,
                    help="inbox.md path (default: <journal-dir>/inbox.md)")
    ap.add_argument("--kits-dir", default=str(DEFAULT_KITS_DIR))
    ap.add_argument("--print", action="store_true",
                    help="also dump the digest JSON to stdout")
    args = ap.parse_args(argv)

    try:
        day_start, day_end = js.day_window(args.date, utc=args.utc)
    except ValueError as e:
        sys.exit(f"invalid --date (want YYYY-MM-DD): {e}")
    date_str = day_start.date().isoformat()

    pricing_claude = cr.load_pricing()
    pricing_copilot = cu.load_pricing()
    pricing_codex = cxu.load_pricing()

    journal_dir = Path(args.journal_dir)
    config_path = Path(args.config) if args.config else journal_dir / "config.json"
    config, config_notes = load_config(config_path)

    # repos = config repos + --repo values, deduped, order preserved.
    repos = []
    seen = set()
    for raw in list(config.get("repos", [])) + list(args.repo):
        p = Path(raw)
        if str(p) not in seen:
            seen.add(str(p))
            repos.append(p)

    ctx = {
        "day_start": day_start,
        "day_end": day_end,
        "claude_projects": Path(args.claude_projects),
        "copilot_home": Path(args.copilot_home),
        "codex_home": Path(args.codex_home),
        "repos": repos,
        "pricing_claude": pricing_claude,
        "pricing_copilot": pricing_copilot,
        "pricing_codex": pricing_codex,
    }
    reports = js.run_adapters(ctx)

    inbox_path = Path(args.inbox) if args.inbox else journal_dir / "inbox.md"
    inbox = read_inbox(inbox_path)
    kit_tasks, kit_errors = scan_kit_tasks(args.kits_dir)
    wip = build_wip(reports.get("git", {}))

    signals = {"kit_tasks": kit_tasks, "inbox": inbox, "wip": wip}
    try:
        signals["harness"] = ja.build_harness_signal(
            reports, pricing_claude, pricing_copilot, pricing_codex)
    except Exception as e:  # advisory must never break the nightly collect
        signals["harness_error"] = f"advisor failed: {e!r}"
    if kit_errors:
        signals["kit_errors"] = kit_errors
    if config_notes:
        signals["config_notes"] = config_notes

    digest = build_digest(reports, day_start, day_end, date_str, signals)

    out_dir = journal_dir / date_str
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        sys.exit(f"cannot create journal dir {out_dir}: {e}")
    digest_path = out_dir / "digest.json"
    try:
        digest_path.write_text(json.dumps(digest, indent=2))
    except OSError as e:
        sys.exit(f"cannot write digest {digest_path}: {e}")

    totals = digest["totals"]
    print(
        f"digest written: {digest_path} — "
        f"{len(totals['sources_active'])}/{len(reports)} sources active, "
        f"${totals['usd_priced']:,.2f} priced, "
        f"{len(kit_tasks)} kit tasks open, "
        f"{len(inbox['items'])} inbox items"
    )
    if args.print:
        print(json.dumps(digest, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
