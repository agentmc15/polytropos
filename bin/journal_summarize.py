#!/usr/bin/env python3
"""Daily-journal model summarizer (PLAN.md D8/D9/D10).

Reads ``journal/<date>/digest.json`` (written by ``bin/journal_collect.py``) and turns it
into three model-written markdown documents — ``narrative.md`` (the story of the day),
``technical.md`` (sessions, cost, models, repos), ``next-day.md`` (what to start, what to run
and how, to-dos) — plus ``summary-meta.json``, all written NEXT TO the digest.

The model dispatch is an INJECTABLE callable ``runner(argv, prompt) -> (rc, text)``. The
default runner (``default_runner``, the ONLY place a subprocess is created) shells
``claude -p --model <id>`` with the prompt on STDIN — reusing the user's existing Claude Code
auth (no API key, no new dependency, nothing sensitive in ``ps`` output). Routing is
data-driven: the tier ladder is ``("haiku", "sonnet", "opus")`` (structural tier VOCABULARY —
never model ids), the model is the FIRST model of the start tier in ``data/pricing.json`` file
order, with at most ONE escalation to the next tier, capped at the ``opus`` tier (a nightly
journal never auto-escalates to a frontier model). A document is accepted when ``rc == 0`` and
``output_ok(text)`` (non-empty, >= MIN_OK_CHARS, first non-whitespace char ``#``).

``--dry-run`` prints the privacy note, the model ladder, the primary dispatch argv, and all
three prompts — and spawns NOTHING and writes NOTHING.

The technical prompt carries one labeled exception to its unpriced-costs rule: a Codex
``codex_proxy`` figure may be reported as an explicitly-labeled "not a bill" API-equivalent
relative-burn proxy, never folded into a billed total. The next-day prompt conditionally adds
a ``## Harness plan`` section (after ``## How to run``) when ``signals.harness`` is present —
per-to-do harness/model-tier/command/WHY recommendations, advisory only.

Privacy: this step sends the digest — project/repo names, commit subjects, kit task titles,
and inbox text — to the model via the claude CLI.

Read-only over the digest; the only writes are the four output files under the digest's own
directory. No real-home lookups here (paths derive from ``PLUGIN_ROOT`` / explicit flags), no
model-id or price literals (the ladder is computed from pricing tiers at run time), no SQLite.

Usage:
  journal_summarize.py [--date YYYY-MM-DD] [--utc] [--journal-dir DIR] [--digest PATH]
                       [--model ID] [--start-tier haiku|sonnet|opus] [--claude-bin BIN]
                       [--dry-run]
"""

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
PRICING_PATH = PLUGIN_ROOT / "data" / "pricing.json"

# Structural tier VOCABULARY (like cost_report.py's EXPENSIVE_TIERS) — these are pricing-tier
# names, NEVER model ids. The concrete model per tier is looked up from data/pricing.json at
# run time. Capped at "opus": a nightly journal never auto-escalates to a frontier model.
TIER_LADDER = ("haiku", "sonnet", "opus")
DEFAULT_START_TIER = "sonnet"
DEFAULT_CLAUDE_BIN = "claude"
MIN_OK_CHARS = 200

DOCS = ("narrative", "technical", "next_day")
FILENAMES = {
    "narrative": "narrative.md",
    "technical": "technical.md",
    "next_day": "next-day.md",
}

# Disclosed privacy consideration (PLAN.md D9) — verbatim in the docstring, the dry-run
# header, the skill, and the docs.
PRIVACY_NOTE = (
    "Privacy: this step sends the digest — project/repo names, commit subjects, kit task "
    "titles, and inbox text — to the model via the claude CLI."
)


def load_pricing():
    """Load data/pricing.json — mirrors cost_report.load_pricing (the single source of truth)."""
    with open(PRICING_PATH) as f:
        return json.load(f)


def pick_models(pricing, start_tier):
    """The model ladder: FIRST model per tier (pricing file order) from ``start_tier`` onward
    in TIER_LADDER, truncated to 2 (primary + ONE escalation, capped at the ladder end —
    never a frontier model). Empty result or an unknown ``start_tier`` -> ValueError."""
    if start_tier not in TIER_LADDER:
        raise ValueError(f"unknown start tier {start_tier!r} (want one of {TIER_LADDER})")
    models = pricing.get("models", {})
    ladder = []
    for tier in TIER_LADDER[TIER_LADDER.index(start_tier):]:
        for model_id, spec in models.items():
            if isinstance(spec, dict) and spec.get("tier") == tier:
                ladder.append(model_id)
                break  # first model of this tier only
    ladder = ladder[:2]
    if not ladder:
        raise ValueError(
            f"no models at or above tier {start_tier!r} in pricing.json")
    return ladder


def output_ok(text):
    """A document is acceptable when it is non-empty, at least MIN_OK_CHARS after stripping,
    and its first non-whitespace character is ``#`` (i.e. it starts with a markdown heading)."""
    return bool(text) and len(text.strip()) >= MIN_OK_CHARS and text.lstrip().startswith("#")


def _match_model(model_id, pricing):
    """Tolerant raw-id -> pricing-key match (mirrors cost_report.match_model)."""
    if not model_id or model_id.startswith("<"):
        return None
    base = model_id.split("[")[0].strip()
    for key in pricing.get("models", {}):
        if base == key or base.startswith(key + "-"):
            return key
    return None


def _next_date(date_str):
    """The next calendar date after ``date_str`` (YYYY-MM-DD). Handles month/year rollover;
    returns the input unchanged if it is not a parseable date."""
    try:
        d = date.fromisoformat(str(date_str))
    except ValueError:
        return str(date_str)
    return (d + timedelta(days=1)).isoformat()


def build_prompts(digest):
    """Build the three model prompts (pure). Each prompt carries a role/instruction header,
    the REQUIRED output contract (pinned headings), the tail
    'Respond with ONLY the markdown document.', and the compact digest JSON in a fenced block.
    No file reads — the digest is embedded verbatim (metadata-only, per D4)."""
    date_str = str(digest.get("date", ""))
    next_date = _next_date(date_str)
    compact = json.dumps(digest, indent=None, separators=(",", ":"))
    digest_block = "Digest (JSON):\n```json\n" + compact + "\n```"
    tail = "Respond with ONLY the markdown document."

    narrative = (
        "You are a technical writer producing a daily work journal from a machine-generated\n"
        "activity digest. Use ONLY the facts present in the digest below — do not invent\n"
        "projects, models, costs, commits, or tasks; if a fact is absent, omit it.\n\n"
        "Write a readable narrative of the day: which projects were worked on, which tools\n"
        "and models were used, and what shipped (commits). Prefer flowing prose over tables.\n\n"
        "The document MUST begin with this exact H1 heading line:\n"
        f"# Work journal — {date_str}\n\n"
        + digest_block + "\n\n"
        + tail + "\n"
    )

    technical = (
        "You are a technical analyst writing a per-source technical summary of a day of\n"
        "AI-assisted work from the digest below. Use ONLY the digest facts. Do NOT guess\n"
        "costs: sources marked unpriced (priced=false) MUST be labeled \"unpriced\" and\n"
        "never assigned a dollar figure — with ONE exception: when\n"
        "sources.codex_cli.extra.codex_proxy exists, report its api_equivalent_usd_total\n"
        "as an API-equivalent relative-burn proxy, explicitly labeled \"not a bill\", and\n"
        "never add it to any billed total.\n\n"
        "The document MUST begin with this exact H1 heading line:\n"
        f"# Technical summary — {date_str}\n\n"
        "and MUST contain these H2 sections, in this order:\n"
        "## Sessions & cost\n"
        "  Per source: session count, token totals, and USD where priced; label unpriced\n"
        "  sources as unpriced.\n"
        "## Models\n"
        "  Per model: which models ran, with their token and cost breakdown.\n"
        "## Repos & commits\n"
        "  Per repo (from the git source): branch, commit count, and commit subjects.\n\n"
        + digest_block + "\n\n"
        + tail + "\n"
    )

    next_day = (
        "You are planning the next working day from today's activity digest and its\n"
        "pre-structured signals (kit_tasks, inbox, wip). Use ONLY the digest facts.\n\n"
        "The document MUST begin with this exact H1 heading line:\n"
        f"# Plan for {next_date}\n\n"
        "and MUST contain these H2 sections, in this order:\n"
        "## Start here\n"
        "  The top 1–3 items to pick up first, each with a one-line WHY.\n"
        "## To-dos\n"
        "  A checklist drawn from signals.kit_tasks, signals.inbox, and signals.wip.\n"
        "## How to run\n"
        "  Concrete commands to resume the work (for example, resume a kit with\n"
        "  `/polytropos:execute <slug>`).\n\n"
        "When signals.harness exists (and only then), ALSO end the document with this H2\n"
        "section:\n"
        "## Harness plan\n"
        "  For each To-do above, recommend a harness (Claude Code / Copilot CLI / Codex\n"
        "  CLI), a model tier, a ready-to-paste command built from that harness's\n"
        "  command_template in signals.harness (fill {model} with the recommended model\n"
        "  id from its est entries), and a one-line WHY grounded in the signals.harness\n"
        "  estimates and today's usage. Advisory only — the user decides and runs it;\n"
        "  nothing auto-executes. Codex dollar figures are API-equivalent relative-burn\n"
        "  proxies, never bills.\n\n"
        + digest_block + "\n\n"
        + tail + "\n"
    )

    return {"narrative": narrative, "technical": technical, "next_day": next_day}


def build_dispatch(model_id, claude_bin=DEFAULT_CLAUDE_BIN):
    """The dispatch argv (PLAN.md D9): exactly ``[claude_bin, "-p", "--model", model_id]``.
    The prompt travels on STDIN — never in argv (no ARG_MAX risk, nothing in ``ps`` output)."""
    return [claude_bin, "-p", "--model", model_id]


def default_runner(argv, prompt):
    """The default injectable dispatch — the ONLY subprocess in this module. Runs ``argv``
    with ``prompt`` on stdin and returns ``(returncode, stdout)``. A missing binary ->
    ``(127, ...)``; a timeout -> ``(124, ...)`` (never raises to the caller)."""
    try:
        proc = subprocess.run(
            argv, input=prompt, capture_output=True, text=True, timeout=600)
    except FileNotFoundError as e:
        return (127, f"<claude bin not found: {e}>")
    except subprocess.TimeoutExpired as e:
        return (124, f"<claude dispatch timed out: {e}>")
    return (proc.returncode, proc.stdout)


def summarize(digest, models, runner, claude_bin=DEFAULT_CLAUDE_BIN):
    """Produce the accepted documents and a meta record. For each doc in DOCS, walk at most 2
    models (primary + one escalation); accept the first whose ``rc == 0 and output_ok(out)``;
    record every attempt. A doc with no accepted attempt is OMITTED from ``docs`` and marked
    ``failed`` in the meta."""
    prompts = build_prompts(digest)
    docs = {}
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "start_models": list(models),
        "docs": {},
    }
    for doc in DOCS:
        prompt = prompts[doc]
        attempts = []
        accepted = False
        for idx, model_id in enumerate(models[:2]):  # cap: primary + one escalation
            rc, out = runner(build_dispatch(model_id, claude_bin), prompt)
            ok = bool(rc == 0 and output_ok(out))
            attempts.append({"model": model_id, "rc": rc, "ok": ok})
            if ok:
                docs[doc] = out
                meta["docs"][doc] = {
                    "attempts": attempts,
                    "model": model_id,
                    "escalated": idx > 0,
                }
                accepted = True
                break
        if not accepted:
            meta["docs"][doc] = {"attempts": attempts, "failed": True}
    return docs, meta


def _resolve_date_str(date_arg, utc):
    if date_arg is not None:
        try:
            return date.fromisoformat(date_arg).isoformat()
        except ValueError:
            sys.exit(f"invalid --date (want YYYY-MM-DD): {date_arg}")
    if utc:
        return datetime.now(timezone.utc).date().isoformat()
    return date.today().isoformat()


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Summarize a daily-journal digest into three model-written documents.")
    ap.add_argument("--date", default=None,
                    help="YYYY-MM-DD (default: today; matches journal_collect.py)")
    ap.add_argument("--utc", action="store_true",
                    help="resolve the default date in UTC (tests/verifies use it)")
    ap.add_argument("--journal-dir", default=str(PLUGIN_ROOT / "journal"),
                    help="journal root (digest dir is <journal-dir>/<date>)")
    ap.add_argument("--digest", default=None,
                    help="explicit digest.json path (overrides --date/--journal-dir)")
    ap.add_argument("--model", default=None,
                    help="explicit model id (must match into pricing.json; no escalation)")
    ap.add_argument("--start-tier", choices=TIER_LADDER, default=DEFAULT_START_TIER,
                    help="tier to start the model ladder at")
    ap.add_argument("--claude-bin", default=DEFAULT_CLAUDE_BIN,
                    help="claude CLI binary (tests point this at a stub)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the privacy note, models, argv, and prompts; write/spawn nothing")
    args = ap.parse_args(argv)

    if args.digest:
        digest_path = Path(args.digest)
    else:
        date_str = _resolve_date_str(args.date, args.utc)
        digest_path = Path(args.journal_dir) / date_str / "digest.json"

    if not digest_path.is_file():
        sys.exit(f"no digest at {digest_path} — run journal_collect.py first")
    digest = json.loads(digest_path.read_text())

    pricing = load_pricing()
    if args.model:
        matched = _match_model(args.model, pricing)
        if matched is None:
            sys.exit(f"--model {args.model!r} is not a model in pricing.json")
        models = [matched]  # explicit model: no escalation
    else:
        try:
            models = pick_models(pricing, args.start_tier)
        except ValueError as e:
            sys.exit(str(e))

    prompts = build_prompts(digest)

    if args.dry_run:
        print(PRIVACY_NOTE)
        print()
        print(f"Models (ladder): {', '.join(models)}")
        print(f"Primary dispatch argv: {build_dispatch(models[0], args.claude_bin)}")
        print("(dry run — nothing is sent to a model and no files are written)")
        for doc in DOCS:
            print(f"\n=== PROMPT: {doc} ===")
            print(prompts[doc])
        return 0

    docs, meta = summarize(digest, models, default_runner, claude_bin=args.claude_bin)
    out_dir = digest_path.parent
    for doc, text in docs.items():
        (out_dir / FILENAMES[doc]).write_text(text)
    (out_dir / "summary-meta.json").write_text(json.dumps(meta, indent=2))

    for doc in DOCS:
        if doc in docs:
            print(f"written {FILENAMES[doc]} (model {meta['docs'][doc]['model']})")
        else:
            print(f"FAILED {doc}", file=sys.stderr)

    return 0 if all(doc in docs for doc in DOCS) else 3


if __name__ == "__main__":
    sys.exit(main())
