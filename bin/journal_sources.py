#!/usr/bin/env python3
"""daily-journal source-adapter engine (schema_version 1).

The pluggable ingestion layer for the daily journal: an ordered registry of per-source
adapters, the day-window helpers they share, and the crash-isolating engine that drives
them. Each adapter is a pure-ish function ``collect_<name>(ctx)`` returning the pinned
per-source report shape (PLAN.md D4).

STRICTLY READ-ONLY ingestion. No adapter here ever writes anything under a source root,
ever opens a ``*.db`` / SQLite store (opening a live SQLite file can spawn ``-wal``/``-shm``
side files even read-only — which is exactly why Cursor/VS Code stay deferred), or ever
invokes a ``claude`` / ``copilot`` / ``codex`` CLI to gather data. Every source root and
both pricing dicts arrive through the explicit ``ctx`` argument; this module performs no
home-directory resolution of its own — the four runtime-default roots live in the collector
CLI, always overridden by temp fixtures in tests.

The proven transcript/event parsers are reused verbatim via the importlib pattern from
``bin/session_cost.py`` — ``cost_report`` (as ``cr``) for Claude Code and ``copilot_usage``
(as ``cu``) for Copilot CLI — never re-implemented, never edited.

ctx keys (PLAN.md D2): ``day_start``, ``day_end`` (aware datetimes), ``claude_projects``,
``copilot_home``, ``codex_home`` (Path or None), ``repos`` (list[Path]), ``pricing_claude``,
``pricing_copilot``, ``pricing_codex`` (dict or None -- the last is OPTIONAL: absent/None means
byte-identical legacy Codex behavior). Reports are metadata only (PLAN.md D4): no transcript or
message text ever enters a report.
"""

import importlib.util
import json
import subprocess
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path


def _load(name):
    """Load a sibling ``bin/<name>.py`` module read-only (the session_cost.py pattern)."""
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parent / f"{name}.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cr = _load("cost_report")     # Claude Code transcript parser + pricing (read-only reuse)
cu = _load("copilot_usage")   # Copilot CLI event parser + pricing (read-only reuse)
cxu = _load("codex_usage")    # Codex rollout reader + proxy pricing (read-only reuse)


# --------------------------------------------------------------------------- helpers

def day_window(date_str=None, utc=False):
    """Return ``(day_start, day_end)`` aware datetimes for a calendar day (PLAN.md D5).

    ``date_str`` is ``YYYY-MM-DD`` (ValueError propagates on garbage; the CLI catches it
    later); None -> today. ``utc=False`` uses local midnight; ``utc=True`` uses UTC midnight
    (what tests/verify commands use, so day membership never depends on the machine's
    timezone). ``day_end = day_start + 1 day``.
    """
    if date_str is None:
        d = datetime.now(timezone.utc).date() if utc else date.today()
    else:
        d = date.fromisoformat(date_str)
    if utc:
        day_start = datetime.combine(d, time.min, tzinfo=timezone.utc)
    else:
        day_start = datetime.combine(d, time.min).astimezone()
    return day_start, day_start + timedelta(days=1)


def empty_report(source, priced):
    """The pinned per-source report skeleton (PLAN.md D4, schema_version 1)."""
    return {
        "source": source,
        "available": False,
        "priced": priced,
        "deferred": False,
        "sessions": 0,
        "first_ts": None,
        "last_ts": None,
        "models": {},
        "totals": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0},
        "usd": None,
        "projects": [],
        "tool_uses": 0,
        "errors": [],
        "notes": [],
        "extra": {},
    }


def _model_bucket():
    """Per-model accumulator; ``usd`` stays None until a priced record lands in it."""
    return {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0,
            "messages": 0, "usd": None}


def _span(report, when):
    """Fold one aware datetime into the report's first_ts/last_ts (stored as ISO strings)."""
    if when is None:
        return
    if report["first_ts"] is None or when < datetime.fromisoformat(report["first_ts"]):
        report["first_ts"] = when.isoformat()
    if report["last_ts"] is None or when > datetime.fromisoformat(report["last_ts"]):
        report["last_ts"] = when.isoformat()


def _add_tokens(bucket, totals, u):
    """Accumulate the four token fields into a model bucket and the report totals."""
    for f in ("input", "output", "cache_read", "cache_write"):
        bucket[f] += u[f]
        totals[f] += u[f]


# --------------------------------------------------------------------------- adapters

def collect_claude(ctx):
    """Claude Code adapter (PLAN.md D3/D5): dedupe by message id GLOBALLY, day-filter per
    message, price via the ctx pricing dict, and bucket unmatched models as unpriced.

    Reuses ``cr.extract_record/parse_timestamp/match_model/price`` verbatim.
    """
    report = empty_report("claude_code", True)
    report["extra"]["untimestamped_records"] = 0
    report["extra"]["messages"] = 0
    report["extra"]["unpriced_models"] = []
    root = ctx.get("claude_projects")
    pricing = ctx.get("pricing_claude")
    day_start, day_end = ctx["day_start"], ctx["day_end"]

    if root is None or not root.is_dir():
        report["notes"].append("claude projects dir not found")
        return report
    report["available"] = True
    if pricing is None:
        report["notes"].append("no pricing provided")

    seen_ids = set()
    session_ids = set()
    projects = set()
    unpriced = []
    for path in sorted(root.rglob("*.jsonl")):
        try:
            text = path.read_text(errors="replace")
        except OSError as e:
            report["errors"].append(f"{path}: {e}")
            continue
        for line in text.splitlines():
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
            model, u, msg_id, tool_uses = rec
            # Dedupe message ids GLOBALLY: subagent turns are woven into the main
            # transcript (and duplicated in per-session task files), so a single message
            # can appear more than once across files.
            if msg_id:
                if msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)
            when = cr.parse_timestamp(obj.get("timestamp"))
            # D5 divergence from cost_report's keep-regardless rule: a daily journal must
            # not attribute unknown-day work to today, so records with no parseable
            # timestamp are excluded but counted.
            if when is None:
                report["extra"]["untimestamped_records"] += 1
                continue
            if not (day_start <= when < day_end):
                continue

            report["extra"]["messages"] += 1
            report["tool_uses"] += tool_uses
            _span(report, when)
            session_ids.add(obj.get("sessionId") or path.stem)
            cwd = obj.get("cwd")
            if cwd:
                projects.add(Path(cwd).name)
            else:
                projects.add(path.relative_to(root).parts[0])

            key = cr.match_model(model, pricing) if pricing is not None else None
            if key is not None:
                b = report["models"].setdefault(key, _model_bucket())
                _add_tokens(b, report["totals"], u)
                b["messages"] += 1
                b["usd"] = (b["usd"] or 0.0) + cr.price(key, u, when, pricing)
            else:
                b = report["models"].setdefault(model, _model_bucket())
                _add_tokens(b, report["totals"], u)
                b["messages"] += 1
                if not str(model).startswith("<") and model not in unpriced:
                    unpriced.append(model)

    report["sessions"] = len(session_ids)
    report["projects"] = sorted(projects)
    report["extra"]["unpriced_models"] = sorted(unpriced)
    if pricing is None:
        report["usd"] = None
    else:
        priced = [b["usd"] for b in report["models"].values() if b["usd"] is not None]
        report["usd"] = float(sum(priced)) if priced else 0.0
    return report


def collect_copilot(ctx):
    """Copilot CLI adapter (PLAN.md D3/D5): attribute each session to the day of its LAST
    event, price single-model sessions exactly and multi-model sessions against the last
    model (approx, flagged), and surface Copilot's own AIU / AIC cross-checks.

    Reuses ``cu.collect_sessions/effective_tokens/match_model/price_tokens/usd_to_aic``.
    """
    report = empty_report("copilot_cli", True)
    report["extra"]["untimestamped_sessions"] = 0
    report["extra"]["unpriced_models"] = []
    report["extra"]["aiu_reported"] = 0.0
    report["extra"]["turns"] = 0
    home = ctx.get("copilot_home")
    pricing = ctx.get("pricing_copilot")
    day_start, day_end = ctx["day_start"], ctx["day_end"]

    session_dir = home / "session-state" if home is not None else None
    if session_dir is None or not session_dir.is_dir():
        report["notes"].append("copilot session-state dir not found")
        return report
    report["available"] = True
    # Copilot events carry no tool-use counter, so tool_uses stays 0 for this source.
    report["notes"].append("copilot events carry no tool-use counter; tool_uses is 0")

    sessions, errors = cu.collect_sessions(session_dir)
    report["errors"].extend(errors)

    projects = set()
    unpriced = []
    members = 0
    report_usd = 0.0
    for s in sessions:
        # Cumulative session totals are attributed to the day of the LAST event (D5).
        last = s.get("last_seen")
        if last is None:
            report["extra"]["untimestamped_sessions"] += 1
            continue
        if not (day_start <= last < day_end):
            continue
        members += 1
        sid = s.get("session_id") or s.get("id") or "unknown"
        tokens, output_only = cu.effective_tokens(s)

        matched = []
        if pricing is not None:
            for m in (s.get("models") or []):
                k = cu.match_model(m, pricing)
                if k and k not in matched:
                    matched.append(k)
        attribution = None
        if len(matched) == 1:
            attribution = matched[0]
        elif len(matched) > 1:
            last_key = cu.match_model(s.get("last_model"), pricing)
            attribution = last_key if last_key in matched else matched[-1]
            report["notes"].append(
                f"{sid}: multi-model session attributed to last model")

        if attribution is not None:
            b = report["models"].setdefault(attribution, _model_bucket())
            _add_tokens(b, report["totals"], tokens)
            b["messages"] += 1  # sessions, named `messages` for report-shape uniformity
            usd_s = cu.price_tokens(tokens, attribution, pricing)
            b["usd"] = (b["usd"] or 0.0) + usd_s
            report_usd += usd_s
        else:
            raw = s.get("last_model") or "unknown"
            b = report["models"].setdefault(raw, _model_bucket())
            _add_tokens(b, report["totals"], tokens)
            b["messages"] += 1
            if raw not in unpriced:
                unpriced.append(raw)

        if output_only:
            report["notes"].append(
                f"{sid}: output tokens only (no shutdown tokenDetails)")
        report["extra"]["aiu_reported"] += (s.get("nano_aiu") or 0) / 1e9
        report["extra"]["turns"] += sum(
            v.get("turns", 0) for v in (s.get("per_turn_output") or {}).values())
        ws = s.get("workspace") or {}
        if ws.get("cwd"):
            projects.add(Path(ws["cwd"]).name)
        elif ws.get("name"):
            projects.add(ws["name"])
        _span(report, s.get("first_seen"))
        _span(report, s.get("last_seen"))

    report["sessions"] = members
    report["projects"] = sorted(projects)
    report["extra"]["unpriced_models"] = sorted(unpriced)
    if pricing is None:
        report["usd"] = None
    else:
        report["usd"] = report_usd
        report["extra"]["aic"] = cu.usd_to_aic(report_usd, pricing)
    return report


# --------------------------------------------------------------------------- codex adapter
#
# D1-sanctioned research (read-only `head -c 4000` peek at the real ~/.codex/session_index
# .jsonl and ~/.codex/history.jsonl -- nothing else touched, nothing written):
#   session_index.jsonl: {"id": <session-uuid>, "thread_name": <title text>,
#     "updated_at": <ISO-8601 timestamp>} -- no model, no cwd, no usage on this machine.
#     "id" and "updated_at" are already covered by the candidate lists below; "thread_name"
#     is message-like free text and is deliberately NOT harvested (PLAN.md D4 content
#     hygiene -- metadata only).
#   history.jsonl: {"session_id": <session-uuid>, "ts": <epoch-seconds int>,
#     "text": <prompt text>} -- again no model, no cwd, no usage. "session_id" and "ts" are
#     already covered; "text" is prompt content and is deliberately NOT harvested.
# Neither real file exposes model/cwd/usage fields here, so the pinned candidate lists below
# are left unchanged (extend-never-shrink: there was nothing new to add) and the adapter
# degrades gracefully -- activity is still counted (session id + timestamp) even when
# token/model/cwd fields are absent, exactly as D6 requires.

CODEX_TS_KEYS = ("timestamp", "ts", "created_at", "updated_at", "time", "datetime")
CODEX_SESSION_KEYS = ("session_id", "sessionId", "conversation_id", "id")
CODEX_MODEL_KEYS = ("model", "model_id", "model_slug")
CODEX_CWD_KEYS = ("cwd", "workdir", "working_directory", "dir", "path")
CODEX_USAGE_KEYS = ("usage", "token_usage", "tokens", "token_counts")
CODEX_TOKEN_FIELD_MAP = {
    "input_tokens": "input", "prompt_tokens": "input",
    "output_tokens": "output", "completion_tokens": "output",
    "cached_tokens": "cache_read", "cache_read_input_tokens": "cache_read",
}
CODEX_UNPRICED_NOTE = (
    "Codex activity is counted but unpriced in this run — no Codex pricing was provided to "
    "the adapter."
)
CODEX_UNMATCHED_NOTE = (
    "Codex tokens found but no model matched pricing.codex.json — counted, unpriced."
)


def _codex_get(obj, keys):
    """First present key at the top level, else one level down under a payload/data/info
    wrapper (depth <= 2, defensive) -- tolerant of Codex's unpinned JSONL shape.
    """
    if not isinstance(obj, dict):
        return None
    for k in keys:
        if k in obj:
            return obj[k]
    for wrapper in ("payload", "data", "info"):
        sub = obj.get(wrapper)
        if isinstance(sub, dict):
            for k in keys:
                if k in sub:
                    return sub[k]
    return None


def _codex_ts(raw):
    """None-safe tolerant timestamp parse: ISO via ``cr.parse_timestamp``, else a numeric
    epoch (int/float or digit-string; values > 1e12 are milliseconds -> divide by 1000),
    else None.
    """
    if raw is None:
        return None
    when = cr.parse_timestamp(raw)
    if when is not None:
        return when
    try:
        num = float(raw)
    except (TypeError, ValueError):
        return None
    if num > 1e12:
        num = num / 1000.0
    try:
        return datetime.fromtimestamp(num, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def collect_codex(ctx):
    """Codex CLI adapter (PLAN.md D2/D3/D6): a tolerant extractor for Codex's format-unpinned
    JSONL. Reads ``session_index.jsonl`` and ``history.jsonl`` directly under ``codex_home``
    AND, for the digest day ONLY, the rollout files under
    ``codex_home/sessions/YYYY/MM/DD/*.jsonl`` -- the date-partitioned directory name IS the
    day-membership rule, so rollouts under any other date dir are never opened. Each rollout is
    reduced with ``cxu.parse_rollout`` (read-only reuse of ``bin/codex_usage.py`` -- the
    cumulative-vs-per-turn MAX rule is never re-implemented). Never a binary-store subdir,
    never a ``*.db`` file.

    The OPTIONAL ctx key ``pricing_codex`` (a ``data/pricing.codex.json`` dict, or None) drives
    the LABELED proxy: when it is None the adapter behaves exactly as the legacy shallow reader
    plus token bucketing (rollout tokens are still counted, but nothing is priced). When it is
    a dict and a rollout's model matches a pricing key, the day's API-equivalent relative-burn
    proxy is reported ONLY under ``extra["codex_proxy"]`` (``billed_usd`` always None). The D3
    honesty rule is absolute: ``priced`` stays False and ``usd`` stays None on every path, a
    model bucket's ``usd`` stays None (bill semantics), and the proxy is NEVER a bill and never
    flows into any billed total.
    """
    report = empty_report("codex_cli", False)
    report["extra"]["records"] = 0
    report["extra"]["untimestamped_records"] = 0
    report["extra"]["malformed_lines"] = 0
    report["extra"]["rollouts_scanned"] = 0
    report["extra"]["rollouts_with_tokens"] = 0
    report["extra"]["unpriced_models"] = []
    home = ctx.get("codex_home")
    pricing = ctx.get("pricing_codex")
    day_start, day_end = ctx["day_start"], ctx["day_end"]

    if home is None or not home.is_dir():
        report["notes"].append("codex home not found")
        return report
    report["available"] = True

    session_ids = set()
    projects = set()
    unpriced = []
    found_any = False
    for filename in ("session_index.jsonl", "history.jsonl"):
        path = home / filename
        if not path.is_file():
            continue
        found_any = True
        try:
            text = path.read_text(errors="replace")
        except OSError as e:
            report["errors"].append(f"{path}: {e}")
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                report["extra"]["malformed_lines"] += 1
                continue
            if not isinstance(obj, dict):
                report["extra"]["malformed_lines"] += 1
                continue

            when = _codex_ts(_codex_get(obj, CODEX_TS_KEYS))
            if when is None:
                report["extra"]["untimestamped_records"] += 1
                continue
            if not (day_start <= when < day_end):
                continue

            report["extra"]["records"] += 1
            _span(report, when)
            sid = _codex_get(obj, CODEX_SESSION_KEYS)
            if sid:
                session_ids.add(sid)
            model = _codex_get(obj, CODEX_MODEL_KEYS) or "unknown"
            b = report["models"].setdefault(model, _model_bucket())
            usage = _codex_get(obj, CODEX_USAGE_KEYS)
            if isinstance(usage, dict):
                for k, v in usage.items():
                    field = CODEX_TOKEN_FIELD_MAP.get(k)
                    if field is None or not isinstance(v, (int, float)):
                        continue
                    b[field] += v
                    report["totals"][field] += v
            b["messages"] += 1
            cwd = _codex_get(obj, CODEX_CWD_KEYS)
            if cwd:
                projects.add(Path(str(cwd)).name)

    # ---- day-scoped rollout deepening (PLAN.md D2/D3) ------------------------------------
    # The ONE directory scanned is the digest day's date-partitioned rollout dir; its NAME is
    # the day-membership rule (no mtime, never another date dir). Tokens are bucketed whether
    # or not pricing is present; the proxy is priced only when pricing is a dict AND a
    # rollout's model matches a pricing key.
    d = day_start.date()
    day_dir = home / "sessions" / f"{d.year:04d}" / f"{d.month:02d}" / f"{d.day:02d}"
    proxy_total = 0.0
    proxy_by_model = {}
    approx_any = False
    priced_any = False
    tokens_found_any = False
    if day_dir.is_dir():
        try:
            rollout_files = sorted(
                p for p in day_dir.iterdir() if p.is_file() and p.suffix == ".jsonl")
        except OSError as e:
            rollout_files = []
            report["errors"].append(f"{day_dir}: {e}")
        if rollout_files:
            found_any = True
        for path in rollout_files:
            try:
                text = path.read_text(errors="replace")
            except OSError as e:
                report["errors"].append(f"{path}: {e}")
                continue
            parsed = cxu.parse_rollout(text.splitlines())
            report["extra"]["rollouts_scanned"] += 1
            report["extra"]["malformed_lines"] += parsed["malformed"]
            report["extra"]["records"] += parsed["records"]
            session_ids |= parsed["session_ids"]
            if parsed["tokens"] is None:
                continue
            report["extra"]["rollouts_with_tokens"] += 1
            tokens_found_any = True

            # Bucket key: with pricing, map each model through cxu.match_model and take the
            # LAST matched pricing key (multi-match -> approx flag; mirrors codex_usage.py's
            # main). No match (or no pricing) -> the last raw model string ("unknown" if none),
            # and with pricing every unmatched raw id is recorded as unpriced.
            priced_key = None
            if pricing is not None:
                matched = []
                for m in parsed["models"]:
                    k = cxu.match_model(m, pricing)
                    if k and k not in matched:
                        matched.append(k)
                if matched:
                    priced_key = matched[-1]
                    if len(matched) > 1:
                        approx_any = True
                else:
                    for m in parsed["models"]:
                        if m not in unpriced:
                            unpriced.append(m)
            if priced_key is not None:
                key = priced_key
            else:
                key = parsed["models"][-1] if parsed["models"] else "unknown"

            tokens = parsed["tokens"]
            b = report["models"].setdefault(key, _model_bucket())
            for field in ("input", "cache_read", "output"):
                b[field] += tokens[field]
                report["totals"][field] += tokens[field]
            # cache_write stays 0 (rollouts carry no observable cache writes); one bucketed
            # "message" per rollout; bucket usd stays None ALWAYS (bill semantics, D3).
            b["messages"] += 1

            if priced_key is not None:
                usd = cxu.price_tokens(tokens, priced_key, pricing)
                proxy_total += usd
                proxy_by_model[priced_key] = proxy_by_model.get(priced_key, 0.0) + usd
                priced_any = True

    if priced_any:
        report["extra"]["codex_proxy"] = {
            "billed_usd": None,
            "api_equivalent_usd_total": proxy_total,
            "by_model": proxy_by_model,
            "approx_attribution": approx_any,
            "disclaimer": cxu.PROXY_DISCLAIMER,
            "pricing_cached_date": pricing["cached_date"],
        }
        report["notes"].append(cxu.PROXY_DISCLAIMER)

    # Notes ladder (PLAN.md D3), decided AFTER rollout processing -- exactly one path:
    if pricing is None:
        report["notes"].append(CODEX_UNPRICED_NOTE)      # legacy: no pricing provided this run
    elif priced_any:
        pass                                             # cxu.PROXY_DISCLAIMER appended above
    elif tokens_found_any:
        report["notes"].append(CODEX_UNMATCHED_NOTE)     # tokens found, none matched pricing
    else:
        report["notes"].append(cxu.UNPRICED_NOTE)        # pricing present, no rollout tokens

    if not found_any:
        report["notes"].append("no codex JSONL found")

    report["extra"]["unpriced_models"] = sorted(unpriced)
    report["sessions"] = len(session_ids)
    report["projects"] = sorted(projects)
    return report


# --------------------------------------------------------------------------- git adapter
#
# The ONLY subprocess use in this module (PLAN.md D7): read-only git plumbing over the
# repo roots configured in ctx["repos"] -- never a writing git command (no add/commit/
# fetch/push/anything that mutates a repo).

GIT_COMMIT_CAP = 50


def _git(root, *args):
    """Run one read-only git plumbing command inside ``root`` and return the
    ``CompletedProcess``, or the caught exception (``FileNotFoundError`` when the ``git``
    binary itself is missing, ``subprocess.TimeoutExpired`` on a hang, or another ``OSError``)
    so the caller can react without ever crashing the adapter.
    """
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return e


def collect_git(ctx):
    """Git adapter (PLAN.md D7): read-only plumbing (`log`, `status --porcelain`,
    `rev-parse --abbrev-ref HEAD`) over the configured repo roots -- the cheap, high-signal
    "what I shipped" record. Always ``available=True`` (git activity is config-driven, not
    home-dir-driven) and always ``priced=False``/``usd=None`` -- there is no such thing as a
    priced commit.
    """
    report = empty_report("git", False)
    report["available"] = True
    repos = ctx.get("repos") or []
    day_start, day_end = ctx["day_start"], ctx["day_end"]

    if not repos:
        report["notes"].append(
            'no repos configured — set journal/config.json "repos" or pass --repo')
        return report

    repo_entries = []
    projects = []
    for root in repos:
        root = Path(root)
        if not root.is_dir() or not (root / ".git").exists():
            report["notes"].append(f"{root}: not a git repo")
            continue

        proc = _git(
            root, "log",
            "--since", day_start.isoformat(), "--until", day_end.isoformat(),
            "--pretty=format:%h%x1f%aI%x1f%an%x1f%s%x1e", "--no-show-signature",
        )
        if isinstance(proc, FileNotFoundError):
            # git itself is missing -- every further call would fail identically, so stop
            # after ONE report-level error instead of one per repo.
            report["errors"].append(f"git binary not found: {proc}")
            break
        if isinstance(proc, Exception):
            report["errors"].append(f"{root}: {proc}")
            continue
        if proc.returncode != 0:
            report["errors"].append(f"{root}: {proc.stderr.strip() or 'git log failed'}")
            continue

        commits = []
        for record in proc.stdout.split("\x1e"):
            record = record.strip("\n")
            if not record:
                continue
            fields = record.split("\x1f")
            if len(fields) != 4:
                continue
            sha, when_str, author, subject = fields
            commits.append(
                {"sha": sha, "date": when_str, "author": author, "subject": subject})
            _span(report, cr.parse_timestamp(when_str))

        if len(commits) > GIT_COMMIT_CAP:
            commits = commits[:GIT_COMMIT_CAP]
            report["notes"].append(f"{root}: commit list truncated to {GIT_COMMIT_CAP}")

        dirty = untracked = 0
        status_proc = _git(root, "status", "--porcelain")
        if isinstance(status_proc, Exception):
            report["errors"].append(f"{root}: {status_proc}")
        elif status_proc.returncode == 0:
            for line in status_proc.stdout.splitlines():
                if not line:
                    continue
                if line.startswith("??"):
                    untracked += 1
                else:
                    dirty += 1

        branch = ""
        branch_proc = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
        if not isinstance(branch_proc, Exception) and branch_proc.returncode == 0:
            branch = branch_proc.stdout.strip()

        entry = {
            "root": str(root),
            "branch": branch,
            "commits": commits,
            "commit_count": len(commits),
            "dirty_files": dirty,
            "untracked": untracked,
        }
        repo_entries.append(entry)
        if entry["commit_count"] > 0 or dirty > 0 or untracked > 0:
            projects.append(root.name)

    report["extra"]["repos"] = repo_entries
    report["projects"] = sorted(projects)
    return report


# --------------------------------------------------------------------- deferred stubs
#
# Cursor and VS Code Copilot chat usage both live in an undocumented `state.vscdb` store;
# opening it would mean opening a live SQLite file (WAL/SHM side-file risk -- PLAN.md D1),
# so v1 stays JSONL-only and reserves these registry rows without reading anything.

def collect_cursor(ctx):
    """Cursor adapter -- deferred stub (PLAN.md D2 reserves the registry row)."""
    report = empty_report("cursor", False)
    report["deferred"] = True
    report["notes"].append(
        "Deferred: Cursor usage lives in state.vscdb (SQLite, undocumented schema); "
        "v1 is JSONL-only — see docs/DAILY-JOURNAL.md.")
    return report


def collect_vscode(ctx):
    """VS Code Copilot chat adapter -- deferred stub (PLAN.md D2 reserves the registry row)."""
    report = empty_report("vscode", False)
    report["deferred"] = True
    report["notes"].append(
        "Deferred: VS Code Copilot chat usage lives in state.vscdb (SQLite, undocumented "
        "schema); v1 is JSONL-only — see docs/DAILY-JOURNAL.md.")
    return report


# --------------------------------------------------------------------------- engine

def run_adapters(ctx):
    """Drive every registered adapter, crash-isolated (PLAN.md D2): an adapter that raises
    lands its error in that source's report and the nightly run continues — a journal with
    one broken source beats no journal.
    """
    reports = {}
    for name, fn in ADAPTERS:
        try:
            reports[name] = fn(ctx)
        except Exception as e:
            rep = empty_report(name, False)
            rep["errors"] = [f"adapter crashed: {e!r}"]
            reports[name] = rep
    return reports


# Ordered source registry (PLAN.md D2).
ADAPTERS = (
    ("claude_code", collect_claude),
    ("copilot_cli", collect_copilot),
    ("codex_cli", collect_codex),
    ("git", collect_git),
    ("cursor", collect_cursor),
    ("vscode", collect_vscode),
)
