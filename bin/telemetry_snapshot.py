#!/usr/bin/env python3
"""Durable telemetry store: capture today's analytics into dated JSON envelopes.

THE STORE LAW (telemetry-store PLAN D1/D2/D5 — read those before changing anything here):

* **This module is the ONLY writer under a telemetry store dir.** No other script, test
  helper, or skill snippet ever creates or mutates a file under ``<store>/<source>/``. The
  analytics modules it draws from stay strictly read-only over their own sources.
* **Capture is import-and-call.** Sibling analytics modules are loaded by absolute path with
  the house ``importlib`` helper and their PURE builders are called in-process. This tool
  spawns no processes, invokes no CLI, and touches no network — running it can never spend
  AI Credits (PLAN D3, kit GUARDRAILS).
* **The capture date is ALWAYS the run date, in LOCAL time, matching the journal's
  day-keying; ``captured_at`` remains UTC.** The filename stem and the envelope's
  ``capture_date`` are the same validated ``YYYY-MM-DD`` string, and there is no flag that
  sets it to anything else. The date comes from the naive LOCAL clock (``datetime.now()``)
  because the flow that runs this tool — the daily journal — keys its day on the local date
  (``journal_sources.day_window`` → ``date.today()``); a UTC default would stamp an evening
  run west of Greenwich with tomorrow's date and split one work day across two files. The
  full ``captured_at`` timestamp stays an unambiguous UTC ISO instant, so the exact moment of
  capture is never lost. A 30-day window captured today is stored under today with the window
  recorded separately in ``period`` — so a late capture can never masquerade as a
  contemporaneous one (PLAN D5). The ``date`` argument of :func:`capture` exists for tests
  only and is deliberately NOT exposed on the CLI.
* **An error envelope NEVER replaces an ok envelope.** A same-day re-run whose collector
  raises must not destroy the good payload the earlier run captured — evidence destruction is
  the one failure this store exists to prevent. Before writing a ``status: "error"`` envelope,
  any existing envelope at the same path is read: if it decodes and says ``status: "ok"``, it
  is KEPT and the capture summary carries the note instead. An ok envelope still overwrites
  anything (latest good wins), an error may overwrite an error, and an unreadable/corrupt
  existing file is replaced (with a note) — there is nothing there worth keeping.
* **Late capture is sanctioned; reconstruction is forbidden** (PLAN D5). Capturing a source
  that still exists but is about to rotate away is this tool's whole reason to exist.
  Writing an envelope whose payload was not produced by running a registered collector over
  a still-existing source at capture time — hand-authored, derived from NOTES.md prose, from
  a README table, or from an old report — is forbidden forever. Figures whose source has
  already evaporated are LOST, and the store says so with a coverage/absence label; it never
  papers over them with a fabricated number.
* **Labels are lifted, never authored.** An envelope's ``labels`` come from the payload's own
  ``labels`` list, or are derived mechanically from documented payload fields (the routing
  card's ``dollars`` state, the overview's per-section ``found``). A snapshot must never look
  more authoritative than the live output it captured, so ``est.``, unpriced, API-equivalent
  and partial-coverage caveats survive the round trip into the store.
* **Aggregates and metadata only — never transcript text** (the journal-digest precedent).
  Render-only transport (any ``_``-prefixed top-level payload key, e.g. the usage builders'
  ``_render``) is stripped at capture, so uncapped per-session/per-rollout scratch never
  lands in an envelope. PLAN D7's tripwire: any single envelope over 1 MB means a payload
  started embedding bulk data — that is a schema bug to fix at the source, never a reason to
  add pruning.
* **Absence is data.** An absent source is recorded as a payload-level ``found: false`` plus
  an absence label, never as a missing file and never as a measured zero — so "captured:
  source absent" stays distinguishable from "never ran", forever.

Usage:

    telemetry_snapshot.py [--store-dir DIR] [--projects-dir DIR] [--codex-home DIR]
                          [--copilot-home DIR] [--kits-dir DIR]
                          [--days 30] [--overview-days 7] [--json]
"""

import argparse
import importlib.util
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------------------------
# Constants.

STORE_SCHEMA_VERSION = 1

# Same filename grammar as ``routing_scorecard.SNAPSHOT_FILENAME_RE`` — the crossrepo-trend
# kit already sanctioned it for the trends/ store and PLAN D2 extends it per-source here.
TELEMETRY_FILENAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STORE_DIR = PLUGIN_ROOT / "telemetry"

# The capture registry. Order is the write order and the summary order.
SOURCES = (
    "cost_report",
    "codex_usage",
    "copilot_usage",
    "context_overview",
    "routing_history",
)

# The three harnesses' section names inside a context_weight overview, in the order
# ``build_overview`` emits them.
_OVERVIEW_SECTIONS = ("claude", "codex", "copilot")

# The documented per-section scan counters, with the noun each counts. A found section whose
# counter is 0 scanned nothing — a distinct truth from an absent section (see
# :func:`collect_context_overview`). Each section carries exactly one of these keys.
_OVERVIEW_SCAN_COUNTERS = (("sessions_scanned", "sessions"), ("rollouts_scanned", "rollouts"))

# The payload's own caveat fields on a section's ``carry_cost`` dict, in lift order. These are
# the strings ``context_weight`` itself prints beside those dollars (``CARRY_COST_LABEL``,
# ``codex_usage.PROXY_DISCLAIMER``); the store lifts them verbatim, never authoring its own.
_CARRY_COST_CAVEAT_FIELDS = ("caveat", "label", "disclaimer")

# Exact substrings of the routing card's two distinct ``dollars is None`` notes. These are the
# ONLY discriminator: the two states mean opposite things and must never share a label.
_DOLLARS_QUALITY_ONLY_NOTE = "no session: lines found"
_DOLLARS_EVAPORATED_NOTE = "session: lines found but no transcript priced"

_DOLLARS_QUALITY_ONLY_LABEL = "dollars n/a (quality-only history)"
_DOLLARS_EVAPORATED_LABEL = (
    "dollars n/a — sessions recorded but transcripts already evaporated/unpriced"
)
_DOLLARS_UNEXPLAINED_LABEL = "dollars n/a (no coverage note emitted)"

_ROUTING_PERIOD_DESCRIPTION = "cumulative kit ledger as of capture"

ENVELOPE_KEYS = (
    "store_schema_version",
    "source",
    "source_schema_version",
    "captured_at",
    "capture_date",
    "period",
    "status",
    "labels",
    "notes",
    "payload",
)


# ---------------------------------------------------------------------------------------------
# Sibling modules — loaded lazily by absolute path (the house helper, copied from
# bin/bench_routing.py). Lazy because importing every analytics module costs real time and a
# ``--help`` should not pay it; cached because five collectors share four modules.

_MODULES = {}


def _load(name):
    spec = importlib.util.spec_from_file_location(name, PLUGIN_ROOT / "bin" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mod(name):
    if name not in _MODULES:
        _MODULES[name] = _load(name)
    return _MODULES[name]


# ---------------------------------------------------------------------------------------------
# Home-dir seams. This module resolves NO home directory of its own — every default is the
# loaded module's own module-level default constant, read only when the corresponding flag was
# not passed. That keeps the one sanctioned home-dir expansion per analytics module and none
# here (kit GUARDRAILS: zero home-dir resolution in new engine code).


def _default_projects_dir():
    """``cost_report``'s own module-level transcript default (``context_weight``'s
    ``DEFAULT_PROJECTS_DIR`` is the identical value from the identical helper)."""
    return Path(_mod("cost_report").PROJECTS_DIR)


def _default_codex_home():
    return Path(_mod("codex_usage").DEFAULT_CODEX_HOME)


def _default_copilot_home():
    return Path(_mod("copilot_usage").DEFAULT_COPILOT_HOME)


def _default_kits_dir():
    return Path(_mod("routing_scorecard").DEFAULT_KITS_DIR)


def resolve_opts(opts=None):
    """Fill an options mapping with the loaded modules' own defaults for anything unset.

    ``None``/absent means "the flag was not passed" — only then is a module default read.
    """
    opts = dict(opts or {})
    resolved = {
        "days": opts.get("days") if opts.get("days") is not None else 30,
        "overview_days": (opts.get("overview_days")
                          if opts.get("overview_days") is not None else 7),
        "projects_dir": (Path(opts["projects_dir"]) if opts.get("projects_dir") is not None
                         else _default_projects_dir()),
        "codex_home": (Path(opts["codex_home"]) if opts.get("codex_home") is not None
                       else _default_codex_home()),
        "copilot_home": (Path(opts["copilot_home"]) if opts.get("copilot_home") is not None
                         else _default_copilot_home()),
        "kits_dir": (Path(opts["kits_dir"]) if opts.get("kits_dir") is not None
                     else _default_kits_dir()),
    }
    return resolved


# ---------------------------------------------------------------------------------------------
# Collectors. Each takes the resolved options mapping and returns
# ``(payload_or_None, period, labels, notes)``. Each calls exactly one pure builder; none
# prints, none writes, none catches — a failure raises and ``capture`` turns it into an
# ``status: "error"`` envelope with the exception in ``notes``.
#
# Labels are LIFTED from the payload's own ``labels`` list, or derived by the mechanical rules
# documented per collector (PLAN D2). Nothing here authors a fresh judgement about the data.


def _period_days(source, opts):
    """The ``period`` a source records, independent of whether its collector succeeded — so an
    error envelope still says which window was attempted."""
    if source == "routing_history":
        return {"description": _ROUTING_PERIOD_DESCRIPTION}
    if source == "context_overview":
        return {"days": opts["overview_days"]}
    return {"days": opts["days"]}


def collect_cost_report(opts):
    cr = _mod("cost_report")
    payload = cr.build_report_payload(opts["projects_dir"], days=opts["days"])
    return payload, _period_days("cost_report", opts), list(payload.get("labels", [])), []


def collect_codex_usage(opts):
    cx = _mod("codex_usage")
    payload = cx.build_usage_payload(opts["codex_home"], days=opts["days"])
    return payload, _period_days("codex_usage", opts), list(payload.get("labels", [])), []


def collect_copilot_usage(opts):
    cp = _mod("copilot_usage")
    payload = cp.build_usage_payload(opts["copilot_home"] / "session-state", days=opts["days"])
    return payload, _period_days("copilot_usage", opts), list(payload.get("labels", [])), []


def _carry_cost_caveats(section):
    """Every caveat string a section's own ``carry_cost`` dict carries, deduped, in lift
    order. Nothing is authored here: a section with no ``carry_cost`` (or one carrying no
    caveat field) contributes nothing — a missing caveat is never invented."""
    carry_cost = section.get("carry_cost")
    if not isinstance(carry_cost, dict):
        return []
    caveats = []
    for field in _CARRY_COST_CAVEAT_FIELDS:
        value = carry_cost.get(field)
        if isinstance(value, str) and value.strip() and value not in caveats:
            caveats.append(value)
    return caveats


def collect_context_overview(opts):
    """The overview builder carries no ``labels`` list of its own, so this collector derives
    them MECHANICALLY (PLAN D2: lift, never author) from three documented payload facts:

    1. A section that is missing or ``found: false`` → ``"<name> section absent"``.
    2. A section that IS found but scanned nothing → ``"<name> section: no sessions in
       window"``. ``context_weight``'s claude section keys ``found`` on the projects DIRECTORY
       existing, so an empty (or entirely out-of-window) home yields ``found: true`` with
       ``sessions_scanned: 0`` — dollars of ``0.00`` next to no label read as a measured zero.
       Absent and empty are two different truths and get two different labels (the T4b
       precedent); the absence label is never substituted for this one. Codex's parallel
       counter is ``rollouts_scanned`` and gets the same treatment in its own words.
    3. Each section's ``carry_cost`` caveat — the payload's OWN string field
       (``label``/``caveat``/``disclaimer``: "API-equivalent dollars — an estimate, not a
       bill.", the Codex subscription proxy disclaimer) — lifted verbatim and prefixed with
       the harness whose dollars it qualifies. Without this, an envelope carrying three
       harnesses' dollar figures showed ZERO labels: the snapshot looked more authoritative
       than the live output it captured, which is exactly what GUARDRAILS forbids. The
       harness prefix is what keeps the three harnesses' caveats distinguishable (identical
       wording for claude and copilot would otherwise dedupe into one unattributed line).
    """
    cw = _mod("context_weight")
    payload = cw.build_overview(
        "all", opts["overview_days"], 10,
        opts["projects_dir"], opts["codex_home"], opts["copilot_home"],
    )
    sections = payload.get("sections") or {}
    labels = []
    for name in _OVERVIEW_SECTIONS:
        section = sections.get(name)
        if not isinstance(section, dict) or not section.get("found"):
            labels.append(f"{name} section absent")
            continue
        for counter, noun in _OVERVIEW_SCAN_COUNTERS:
            if section.get(counter) == 0:
                labels.append(f"{name} section: no {noun} in window")
        for caveat in _carry_cost_caveats(section):
            label = f"{name}: {caveat}"
            if label not in labels:
                labels.append(label)
    return payload, _period_days("context_overview", opts), labels, []


def _routing_dollars_labels(card):
    """The routing card's ``dollars`` state, rendered as labels by a mechanical rule.

    ``dollars is None`` has TWO distinct states discriminated by the card's own note strings,
    and they mean OPPOSITE things:

    * ``no session: lines found …`` — the ledger never recorded a session id, so there was
      never any dollar evidence to lose. Quality-only history.
    * ``session: lines found but no transcript priced …`` — session ids WERE recorded and the
      transcripts behind them are gone. This is the evaporation the whole store exists to
      record; labelling it "quality-only" would be fabricated honesty, so the evaporated state
      is checked FIRST and its label is never substituted.
    """
    dollars = card.get("dollars")
    notes = [n for n in card.get("notes") or [] if isinstance(n, str)]
    if dollars is None:
        if any(_DOLLARS_EVAPORATED_NOTE in n for n in notes):
            return [_DOLLARS_EVAPORATED_LABEL]
        if any(n.startswith(_DOLLARS_QUALITY_ONLY_NOTE) for n in notes):
            return [_DOLLARS_QUALITY_ONLY_LABEL]
        return [_DOLLARS_UNEXPLAINED_LABEL]
    return [f"dollars coverage: {dollars['coverage']} "
            f"({dollars['kits_with_sessions']}/{dollars['kits_total']} kits)"]


def collect_routing_history(opts):
    """``assemble_history_card`` is pinned to RAISE ``ValueError`` where the CLI exits (a
    missing kits dir); that propagates to the error-envelope path like any other collector
    exception, so a vanished kits dir is recorded as ``status: "error"``, never as an empty
    ledger."""
    rs = _mod("routing_scorecard")
    kits_dir = opts.get("kits_dir")
    card = rs.assemble_history_card(
        [str(kits_dir)] if kits_dir else [], projects_dir=str(opts["projects_dir"]))
    return card, _period_days("routing_history", opts), _routing_dollars_labels(card), []


def _collector(source):
    """Resolved by name at call time so tests can monkeypatch a single collector."""
    return globals()[f"collect_{source}"]


# ---------------------------------------------------------------------------------------------
# Capture.


def _now_utc():
    """Single UTC clock seam for ``captured_at`` — tests patch this to make a same-day
    overwrite observable. This is NOT the filename clock (see :func:`_now_local`)."""
    return datetime.now(timezone.utc)


def _now_local():
    """The LOCAL wall clock the filename date is keyed on — deliberately naive, exactly like
    ``journal_sources.day_window``'s ``date.today()``. The journal flow that triggers this
    capture keys its day locally; keying the filename on UTC would file an evening run under
    tomorrow and split one work day across two envelopes."""
    return datetime.now()


def _today_str():
    return _now_local().strftime("%Y-%m-%d")


def _validate_date(date_str):
    """``YYYY-MM-DD`` or nothing. This is the path-traversal guard (``write_snapshot``'s
    precedent) AND the D5 guarantee that a filename stem is a real capture date: it runs
    BEFORE any directory is created or any collector runs."""
    if not isinstance(date_str, str) or not _DATE_RE.match(date_str):
        raise ValueError(f"invalid capture date {date_str!r} (expected YYYY-MM-DD)")
    return date_str


def _public_payload(payload):
    """The stored payload: the builder's card MINUS every ``_``-prefixed top-level key.

    Those keys are render-only transport (``_render`` after the Phase-1 uniformity pass) and
    hold the UNCAPPED per-session/per-rollout views the public card is a ``top``-capped slice
    of. Persisting them would put unbounded scratch in the store (PLAN D7's size tripwire) and
    would let a private, unversioned key masquerade as captured evidence.
    """
    if not isinstance(payload, dict):
        return payload
    return {k: v for k, v in payload.items() if not k.startswith("_")}


def build_envelope(source, date_str, period, status, labels, notes, payload):
    """The pinned PLAN D2 envelope — exactly :data:`ENVELOPE_KEYS`, in that order."""
    public = _public_payload(payload)
    return {
        "store_schema_version": STORE_SCHEMA_VERSION,
        "source": source,
        # The payload's OWN version, when it has one. ``None`` is correct and expected for a
        # payload that versions itself internally (the routing card) or not at all.
        "source_schema_version": (public.get("schema_version")
                                  if isinstance(public, dict) else None),
        "captured_at": _now_utc().isoformat(timespec="seconds"),
        "capture_date": date_str,
        "period": period,
        "status": status,
        "labels": list(labels),
        "notes": list(notes),
        "payload": public,
    }


def envelope_path(store_dir, source, date_str):
    return Path(store_dir) / source / f"{date_str}.json"


def _write_envelope(store_dir, source, date_str, envelope):
    """Write one envelope. Same-day re-run overwrites: latest GOOD wins per day (the
    ``write_snapshot`` semantics, minus the one case that would destroy evidence — see
    :func:`_existing_ok_envelope` and :func:`capture`)."""
    path = envelope_path(store_dir, source, date_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(envelope, indent=2) + "\n")
    return path


def _existing_ok_envelope(path):
    """Classify whatever already sits at ``path`` → ``"ok" | "other" | "unreadable" | None``.

    ``None`` means nothing is there. ``"ok"`` means a decodable JSON object whose ``status``
    is ``"ok"`` — the one state an error envelope may never overwrite. ``"other"`` is a
    decodable envelope that is not ok (an error envelope, which an error may replace).
    ``"unreadable"`` covers an unreadable file, undecodable JSON, or non-object JSON: there is
    no good payload in there to protect, so the new envelope wins — with a note, never
    silently (GUARDRAILS: parsers degrade, they never guess).
    """
    if not path.exists():
        return None
    try:
        existing = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return "unreadable"
    if not isinstance(existing, dict):
        return "unreadable"
    return "ok" if existing.get("status") == "ok" else "other"


def capture(store_dir, date=None, opts=None):
    """Capture every registered source into ``<store_dir>/<source>/<date>.json``.

    ``date`` defaults to the LOCAL run date (``captured_at`` stays UTC) and is validated
    first; it exists as an argument for TESTS ONLY and is not reachable from the CLI — there
    is no backdating flag (PLAN D5). Every collector runs under its own guard, so one source
    failing never costs the other four their envelopes; a failure is recorded as a
    ``status: "error"`` envelope with a ``null`` payload and the exception in ``notes``, never
    as silence.

    An error envelope never REPLACES an ok one: if a same-day ok envelope is already on disk
    for a source whose collector just raised, that envelope is kept and the summary's
    ``notes`` carry ``"kept existing ok envelope for <source>; new collector error: ..."``.
    Such a source counts in ``kept`` (and still in ``errors``, because the collector really
    did fail) and its row's ``path`` points at the envelope that survived.

    Returns the summary dict :func:`main` renders. Raises ``ValueError`` on a bad date and
    lets an ``OSError`` from the store dir itself propagate (``main`` turns that into exit 2).
    """
    date_str = _validate_date(date if date is not None else _today_str())
    resolved = resolve_opts(opts)
    store_dir = Path(store_dir)
    # Fail fast on an unwritable store BEFORE spending a single collector's scan.
    store_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    summary_notes = []
    kept = 0
    for source in SOURCES:
        notes = []
        error_repr = None
        try:
            payload, period, labels, collector_notes = _collector(source)(resolved)
            notes.extend(collector_notes)
            status = "ok"
        except Exception as e:  # noqa: BLE001 — a collector failure is DATA, not a crash.
            payload, period, labels = None, _period_days(source, resolved), []
            error_repr = repr(e)
            notes.append(f"collector failed: {error_repr}")
            status = "error"

        path = envelope_path(store_dir, source, date_str)
        if status == "error":
            existing = _existing_ok_envelope(path)
            if existing == "ok":
                # THE keep-ok guard: a failed re-run must not destroy a good capture.
                summary_notes.append(
                    f"kept existing ok envelope for {source}; "
                    f"new collector error: {error_repr}")
                kept += 1
                rows.append({
                    "source": source,
                    "status": status,
                    "labels": 0,
                    "notes": len(notes),
                    "path": str(path),
                })
                continue
            if existing == "unreadable":
                notes.append(
                    f"replaced unreadable/corrupt existing envelope for {source}")

        envelope = build_envelope(source, date_str, period, status, labels, notes, payload)
        path = _write_envelope(store_dir, source, date_str, envelope)
        rows.append({
            "source": source,
            "status": status,
            "labels": len(envelope["labels"]),
            "notes": len(envelope["notes"]),
            "path": str(path),
        })

    return {
        "store_schema_version": STORE_SCHEMA_VERSION,
        "capture_date": date_str,
        "store_dir": str(store_dir),
        "sources": rows,
        "written": len(rows) - kept,
        "kept": kept,
        "notes": summary_notes,
        "ok": sum(1 for r in rows if r["status"] == "ok"),
        "errors": sum(1 for r in rows if r["status"] == "error"),
    }


# ---------------------------------------------------------------------------------------------
# Read side (PLAN D6): a tolerant reader over the store, modeled directly on
# ``routing_scorecard.read_snapshots``, plus the ``--list`` summary built from it. Nothing here
# writes — the store's one writer is :func:`capture`, above.


def read_source_snapshots(store_dir, source):
    """Read every stored envelope for one source under ``<store_dir>/<source>/`` →
    ``(dated_envelopes, notes)``, tolerant of a missing dir and of malformed/rogue files —
    never a crash, never a guess (PLAN D6, the trend-kit read seam).

    A missing source subdir → ``([], [f"no snapshots for source {source!r} under
    {store_dir}"])``. Otherwise only ``*.json`` files are considered, sorted by name (ISO
    date names sort lexicographically, so survivors come back ascending by date); a name
    failing :data:`TELEMETRY_FILENAME_RE` is skipped with a
    ``f"rogue snapshot file skipped: {source}/{name}"`` note; an unreadable or undecodable
    file is skipped with a note naming it; decoded JSON that is not a dict, or whose
    ``payload`` key is absent or neither a dict nor ``None``, is skipped with a note
    (old/foreign-shaped files are never guessed at). Survivors are returned verbatim as
    ``(date_str, envelope)`` tuples, ``date_str`` being the filename stem — unknown envelope
    keys are IGNORED here (R5 forward-tolerance: a v2 store stays readable by this code).
    """
    source_dir = Path(store_dir) / source
    if not source_dir.is_dir():
        return [], [f"no snapshots for source {source!r} under {store_dir}"]

    dated_envelopes = []
    notes = []
    for path in sorted(source_dir.glob("*.json"), key=lambda p: p.name):
        if not TELEMETRY_FILENAME_RE.match(path.name):
            notes.append(f"rogue snapshot file skipped: {source}/{path.name}")
            continue
        try:
            text = path.read_text()
        except OSError as e:
            notes.append(f"snapshot file unreadable, skipped: {source}/{path.name} ({e})")
            continue
        try:
            envelope = json.loads(text)
        except json.JSONDecodeError as e:
            notes.append(f"snapshot file undecodable, skipped: {source}/{path.name} ({e})")
            continue
        if not isinstance(envelope, dict):
            notes.append(f"snapshot file not a JSON object, skipped: {source}/{path.name}")
            continue
        payload = envelope.get("payload", "__missing__")
        if payload is None or isinstance(payload, dict):
            pass
        else:
            notes.append(
                f"snapshot file missing/invalid payload key, skipped: {source}/{path.name}")
            continue
        dated_envelopes.append((path.stem, envelope))
    return dated_envelopes, notes


def build_list_summary(store_dir):
    """Assemble the ``--list`` summary: for every subdir actually present under
    ``store_dir``, its snapshot count/first date/last date/latest status/latest labels, via
    :func:`read_source_snapshots`. A subdir whose name is not in :data:`SOURCES` is still
    listed, flagged with a ``f"unregistered source dir: {name}"`` note (R5: an unknown
    source subdir degrades with a note, never a crash and never a silent drop).

    Only ever reads envelope-level ``status``/``labels`` metadata — never a payload field.
    That is the actual guard, and it is a guard against AGGREGATION, not against the dollar
    sign: envelope ``labels`` are strings LIFTED from the source's own payload, so a label
    that carries a per-source figure or caveat ("API-equivalent dollars — an estimate, not a
    bill.", a builder's own ``$`` amount) renders here verbatim — and must, because a
    snapshot listing may never look more authoritative than the output it captured. What
    cannot happen is the thing GUARDRAILS actually forbids: because no payload field is ever
    read, this lister can never compute, sum, or merge dollars across the three harnesses —
    every figure it shows arrived attached to exactly one source's own label, with that
    source's own caveat wording intact.

    A missing store dir → ``(None, [f"no telemetry store at {store_dir} — run a capture
    first"])``; the caller renders that friendly line and exits 0.
    """
    store_dir = Path(store_dir)
    if not store_dir.is_dir():
        return None, [f"no telemetry store at {store_dir} — run a capture first"]

    notes = []
    rows = []
    for name in sorted(p.name for p in store_dir.iterdir() if p.is_dir()):
        if name not in SOURCES:
            notes.append(f"unregistered source dir: {name}")
        dated_envelopes, source_notes = read_source_snapshots(store_dir, name)
        notes.extend(source_notes)
        dates = [d for d, _ in dated_envelopes]
        if dated_envelopes:
            _, latest_envelope = dated_envelopes[-1]
            latest_status = latest_envelope.get("status")
            latest_labels = list(latest_envelope.get("labels") or [])
        else:
            latest_status = None
            latest_labels = []
        rows.append({
            "source": name,
            "registered": name in SOURCES,
            "count": len(dated_envelopes),
            "first_date": dates[0] if dates else None,
            "last_date": dates[-1] if dates else None,
            "latest_status": latest_status,
            "latest_labels": latest_labels,
        })
    return {"store_dir": str(store_dir), "sources": rows}, notes


def render_list_markdown(summary, notes):
    lines = [f"# Telemetry store — {summary['store_dir']}", ""]
    if not summary["sources"]:
        lines.append("(no source subdirs found)")
    for row in summary["sources"]:
        tag = "" if row["registered"] else " (unregistered)"
        if row["count"] == 0:
            lines.append(f"- {row['source']}{tag}: no snapshots")
            continue
        labels = ", ".join(row["latest_labels"]) if row["latest_labels"] else "none"
        lines.append(
            f"- {row['source']}{tag}: {row['count']} snapshot(s), "
            f"{row['first_date']}..{row['last_date']}, "
            f"latest status: {row['latest_status']}, labels: {labels}"
        )
    if notes:
        lines.append("")
        lines.append("Notes:")
        for n in notes:
            lines.append(f"- {n}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------
# ``--demo``: fully synthetic, no real data (the repo's house style — every tool ships one).
# Same fixture species as ``routing_scorecard.run_history_demo``'s synthetic kits: a TASKS.md
# with ``done`` tasks and a NOTES.md with ``outcome:`` ledger lines, no ``session:`` line so the
# routing-history collector lands deterministic quality-only history rather than depending on
# any real transcript.

DEMO_KIT_TASKS_MD = """# TASKS — telemetry-demo (synthetic)

## Phase 1 — demo

### D1 — a task
- status: done
- model: sonnet

### D2 — another task
- status: done
- model: haiku
"""

DEMO_KIT_NOTES_MD = """# NOTES — telemetry-demo (synthetic)

## Outcome ledger
outcome: D1 model=sonnet result=pass review=clean
outcome: D2 model=haiku result=pass review=clean
"""


def run_demo(as_json):
    """Capture + ``--list`` end to end against a throwaway temp store — no real home dir or
    real ``telemetry/`` is ever touched. Builds empty synthetic homes plus a tiny one-kit
    kits dir in the same temp dir, runs a real :func:`capture`, then a real
    :func:`build_list_summary` over that same temp store, prints both, and cleans up on
    exit. Deterministic enough to smoke-test statuses, source names, and label presence —
    never timestamps (``captured_at`` is real wall-clock and deliberately not asserted on).
    """
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        store = tmp / "store"
        proj = tmp / "proj"
        codex = tmp / "codex"
        copilot = tmp / "copilot"
        kits = tmp / "kits"
        for d in (proj, codex, copilot):
            d.mkdir(parents=True)
        kit = kits / "telemetry-demo"
        kit.mkdir(parents=True)
        (kit / "TASKS.md").write_text(DEMO_KIT_TASKS_MD)
        (kit / "NOTES.md").write_text(DEMO_KIT_NOTES_MD)

        opts = {
            "projects_dir": proj,
            "codex_home": codex,
            "copilot_home": copilot,
            "kits_dir": kits,
            "days": 30,
            "overview_days": 7,
        }
        summary = capture(store, opts=opts)
        list_summary, list_notes = build_list_summary(store)

        if as_json:
            print(json.dumps(
                {"capture": summary, "list": {**list_summary, "notes": list_notes}},
                indent=2))
        else:
            print(render_summary_markdown(summary))
            print()
            print(render_list_markdown(list_summary, list_notes))
    return 0


# ---------------------------------------------------------------------------------------------
# CLI. Metadata only — stdout carries statuses, label COUNTS, and paths, never payload
# contents: the store is the artifact, this is its receipt.


def render_summary_markdown(summary):
    lines = [
        f"# Telemetry snapshot — {summary['capture_date']}",
        "",
        f"store: {summary['store_dir']}",
        "",
    ]
    for row in summary["sources"]:
        lines.append(
            f"- {row['source']}: {row['status']} — {row['labels']} label(s), "
            f"{row['notes']} note(s) — {row['path']}"
        )
    lines.append("")
    tail = (f"{summary['written']} envelope(s) written — {summary['ok']} ok, "
            f"{summary['errors']} error.")
    if summary.get("kept"):
        tail += f" {summary['kept']} existing ok envelope(s) kept."
    lines.append(tail)
    # Capture-time notes only (kept-ok guards) — never a payload field: this is a receipt.
    if summary.get("notes"):
        lines.append("")
        lines.append("Notes:")
        for n in summary["notes"]:
            lines.append(f"- {n}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Capture this repo's analytics into the durable telemetry store "
                    "(read-only over every source; spawns no processes).")
    ap.add_argument("--store-dir", default=str(DEFAULT_STORE_DIR),
                    help="telemetry store root (default: the repo's gitignored telemetry/)")
    ap.add_argument("--projects-dir", default=None,
                    help="Claude transcript projects dir (default: cost_report's own)")
    ap.add_argument("--codex-home", default=None,
                    help="Codex home dir (default: codex_usage's own)")
    ap.add_argument("--copilot-home", default=None,
                    help="Copilot home dir (default: copilot_usage's own)")
    ap.add_argument("--kits-dir", default=None,
                    help="kits dir for the routing ledger (default: routing_scorecard's own)")
    ap.add_argument("--days", type=int, default=30,
                    help="window in days for the usage/cost sources (default: 30)")
    ap.add_argument("--overview-days", type=int, default=7,
                    help="window in days for the context overview (default: 7)")
    ap.add_argument("--json", action="store_true", help="emit the summary as JSON")
    ap.add_argument("--list", action="store_true",
                    help="list what the store holds per source, instead of capturing")
    ap.add_argument("--demo", action="store_true",
                    help="fully synthetic capture + list smoke against a throwaway temp "
                         "store (no real data, no real store touched)")
    args = ap.parse_args(argv)

    if args.demo:
        return run_demo(args.json)

    if args.list:
        list_summary, list_notes = build_list_summary(args.store_dir)
        if list_summary is None:
            print(list_notes[0])
            return 0
        if args.json:
            print(json.dumps({**list_summary, "notes": list_notes}, indent=2))
        else:
            print(render_list_markdown(list_summary, list_notes))
        return 0

    # NOTE: there is deliberately no --date flag. The filename stem and capture_date are
    # always the run date (PLAN D5); backdating a capture is forbidden, not merely discouraged.
    opts = {
        "projects_dir": args.projects_dir,
        "codex_home": args.codex_home,
        "copilot_home": args.copilot_home,
        "kits_dir": args.kits_dir,
        "days": args.days,
        "overview_days": args.overview_days,
    }
    try:
        summary = capture(args.store_dir, opts=opts)
    except OSError as e:
        print(f"cannot write telemetry store at {args.store_dir}: {e}", file=sys.stderr)
        return 2

    print(json.dumps(summary, indent=2) if args.json else render_summary_markdown(summary))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
