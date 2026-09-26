#!/usr/bin/env python3
"""The observability dashboard: one offline HTML page over the stores the owning engines write.

WHAT THIS IS. A read-only consumer and presentation layer. It lists the per-user data home that
`bin/runtime_data.py` resolves, maps each namespace in it back to a checkout, and renders what
the owning engines already output -- the attempt ledger and its history projection, the routing
scorecard, telemetry envelopes, journal digests, evaluation runs, as their panels land -- into
ONE self-contained `index.html` plus a `build.json` receipt in this engine's own `dashboard`
store. The user opens the file in a browser; refreshing is a rebuild, so the page prints the
moment it was built.

WHAT IT REFUSES.

- To be a second analysis authority. It prices nothing, adds no figures together, ranks nothing
  and classifies no failure. Its own arithmetic is counting what it enumerated, the age between
  two dates, and picking the latest of a set. Owners' labels and notes render verbatim.
- To reach the network. The page carries a Content-Security-Policy that forbids every load, and
  nothing in it references a URL: no script, no external style, no font, no image source. The
  engine spawns nothing but the git verbs of D4 through proc_runner -- `git rev-parse
  --show-toplevel` and `git worktree list --porcelain`, both read-only, both bounded by
  GIT_TIMEOUT_SECONDS, run only in a candidate checkout, both off under `--no-git`, and either
  failing is a note, never an error.
- To write anywhere but its own store. `index.html` and `build.json` land under
  `runtime_data.store_path("dashboard", <primary checkout>)` or `--out-dir`, through
  bin/safe_paths.py, 0700/0600. Nothing in any other store, namespace, harness home or checkout
  is written, moved or deleted -- residue included.
- To open residue beyond one listing, or to delete anything at all.

THE PRIMARY CHECKOUT, AND WHY NEVER PLUGIN_ROOT ON ITS OWN. The page belongs to the checkout
being observed: the git toplevel of the working directory, or the working directory itself when
git is off or cannot say. PLUGIN_ROOT is where this file lives -- under a skill, a plugin cache,
which is not a checkout and must never own a store -- so it is used only to load sibling
modules. It is never added as a candidate and never used as a git working directory in its own
right. A development clone that the working directory, a `--checkout` flag or `config.json`
names is a candidate like any other, even when this file happens to live in it.

THE RESIDUE HEURISTIC, AND ITS LIMIT. Test runs that leaked into the real data home left
namespaces named like a `tempfile` directory plus runtime_data's digest. A namespace counts as
residue when its name matches RESIDUE_NAMESPACE_RE AND one shallow listing of it holds nothing
but an `attempts` store. Residue is counted, sampled by name, excluded from every figure, and
never opened again. It is a heuristic and the page says so: a genuine checkout whose directory
is named like a temp dir, and whose only store is the attempt ledger, is miscounted as residue.

PRIVACY. Every string is HTML-escaped and every path is scrubbed to `~` in the render layer
(`scrub`, with the home directory resolved once in `main` and passed down). No transcript,
prompt, report, tail or inbox text reaches the page: no owner the dashboard calls returns any,
and the ledger's free-text fields are never rendered.
"""

import argparse
import functools
import hashlib
import html
import importlib.util
import json
import math
import os
import re
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------------------------
# Constants. Each bound says why its number is what it is.

# Where this file lives: loads sibling modules only -- never a checkout, never a store owner.
PLUGIN_ROOT = Path(__file__).resolve().parents[1]

# The runtime_data store this engine writes, and the only one.
STORE_NAME = "dashboard"

# build.json's shape: an integer bumped only on an incompatible receipt change, not a contract.
BUILD_SCHEMA_VERSION = 1

# The one page a browser opens from file://.
PAGE_NAME = "index.html"

# The machine-readable receipt beside it -- what `build --json` prints.
RECEIPT_NAME = "build.json"

# Optional and user-authored: extra checkouts to map (the journal/config.json precedent).
CONFIG_NAME = "config.json"

# Nothing may load: no script, fetch, font or frame; inline styles and data: images only.
CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:"

# A tempfile basename (`tmp` + 8 chars) plus runtime_data's 8-hex digest: leaked test runs.
RESIDUE_NAMESPACE_RE = re.compile(r"^tmp[a-z0-9_]{8}-[0-9a-f]{8}$")

# The only store a residue namespace may hold: the leaks came from the attempt ledger alone.
RESIDUE_STORES = frozenset({"attempts"})

# Names quoted when one count stands for many entries: enough to recognise, bounded for a page.
SAMPLE_SIZE = 3

# One shallow listing: ~3x the ~1,500 entries measured when written, so residue stays exact.
MAX_NAMESPACES_LISTED = 5000

# Mapped + unmapped namespaces read in depth (mapped first): a real machine holds a handful.
MAX_NAMESPACES_READ = 32

# AttemptLedger.events() reads a whole file; a ledger past 8 MiB is skipped with a note.
MAX_LEDGER_BYTES = 8 * 1024 * 1024

# Kits parsed per kits dir: a busy checkout holds a few dozen.
MAX_KITS_PER_DIR = 100

# Evaluation runs rendered in full; the rest are counted, not drawn.
MAX_EVAL_RUNS_RENDERED = 10

# Journal days rendered: two months of daily digests is one screen of rows.
MAX_JOURNAL_DAYS = 60

# Telemetry envelopes listed per source: about four months of daily captures.
MAX_TELEMETRY_ENVELOPES_PER_SOURCE = 120

# T5 retry R4: `kit_contract.parse_tasks` reads a whole TASKS.md; the largest real one in this
# repo (`repo-bench`) is about 144 KiB, so 1 MiB leaves roughly 7x headroom for a busy kit
# while still refusing a corrupted or hostile file with no bound at all.
MAX_TASKS_MD_BYTES = 1 * 1024 * 1024

# T6 retry, red-team C: `journal_collect.py` reads a whole `digest.json`. A real one is a few KB
# of numbers and short name lists (`journal_collect.MAX_KIT_TASKS`/`MAX_INBOX_ITEMS` cap its two
# list fields at 100 entries each); 256 KiB leaves two orders of magnitude of headroom while
# still refusing a multi-MB payload with no bound at all.
MAX_DIGEST_BYTES = 256 * 1024

# T6 retry, red-team C: `telemetry_snapshot.read_source_snapshots` reads a whole envelope file.
# A real one's payload is the owner's own already-capped card (`_public_payload` strips the
# uncapped per-session/per-rollout scratch keys before it is ever written); 512 KiB leaves
# generous headroom for the larger cards (`context_overview`'s three sections) while still
# refusing a multi-MB payload with no bound at all.
MAX_ENVELOPE_BYTES = 512 * 1024

# A local git read takes milliseconds; 20 s (attempt_ledger's git probe bound) stops a hung one.
GIT_TIMEOUT_SECONDS = 20

# The two read-only git verbs of PLAN D4 -- the engine's only processes.
GIT_TOPLEVEL_ARGV = ("git", "rev-parse", "--show-toplevel")
GIT_WORKTREES_ARGV = ("git", "worktree", "list", "--porcelain")

# The caps `default_caps()` returns, in the order the bounds panel lists them.
CAP_NAMES = (
    "MAX_NAMESPACES_LISTED",
    "MAX_NAMESPACES_READ",
    "MAX_LEDGER_BYTES",
    "MAX_KITS_PER_DIR",
    "MAX_TASKS_MD_BYTES",
    "MAX_EVAL_RUNS_RENDERED",
    "MAX_JOURNAL_DAYS",
    "MAX_TELEMETRY_ENVELOPES_PER_SOURCE",
    "MAX_DIGEST_BYTES",
    "MAX_ENVELOPE_BYTES",
)

PAGE_TITLE = "polytropos observability dashboard"

# The panel that shows the namespace classes; it carries the classification's own notes.
NAMESPACES_PANEL = "namespaces"

# Synthetic fixture values (`synthetic_world`, `demo`): obviously not a real kit, run or model.
DEMO_KIT = "demo-kit"
DEMO_RUN = "2026-01-01-0001"
SYNTHETIC_MODEL = "fake-cheap"
UNMAPPED_NAMESPACE = "unmapped-cafef00d"
DEMO_TASKS_MD = """# TASKS — demo-kit (synthetic)

## Phase 1 — synthetic

### T1 — a synthetic finished task
- status: done
- model: sonnet

### T2 — a synthetic task whose attempt never finished
- status: in-progress
- model: sonnet
"""
DEMO_NOTES_MD = f"""# NOTES — demo-kit (synthetic)

outcome: T1 model=sonnet attempts=1 result=pass review=clean run={DEMO_RUN}
"""

# T4: a second, ledger-less kit so `notes`-source records exist independent of any ledger join
# (TASKS.md item 5) -- one `pass`, one `blocked`, mirroring `attempt_history.py`'s own demo kit B.
NOTES_KIT = "notes-kit"
NOTES_KIT_TASKS_MD = """# TASKS — notes-kit (synthetic)

## Phase 1 — synthetic

### T1 — a synthetic task recorded only in NOTES.md
- status: done
- model: sonnet

### T2 — a synthetic task recorded only in NOTES.md, blocked
- status: blocked
- model: sonnet
"""
NOTES_KIT_NOTES_MD = f"""# NOTES — notes-kit (synthetic)

outcome: T1 model=sonnet attempts=1 result=pass review=clean run={DEMO_RUN}
outcome: T2 model=sonnet attempts=1 result=blocked review=none run={DEMO_RUN}
"""

# T5: a third kit for the routing scorecard's history card -- three `outcome:` lines across two
# tiers (sonnet, haiku) so the tiers table has more than one row of data.
SCORECARD_KIT = "scorecard-demo"
SCORECARD_TASKS_MD = """# TASKS — scorecard-demo (synthetic)

## Phase 1 — synthetic

### SC1 — a synthetic sonnet task, first try
- status: done
- model: sonnet

### SC2 — a synthetic sonnet task, needing a retry
- status: done
- model: sonnet

### SC3 — a synthetic haiku task, first try
- status: done
- model: haiku
"""
SCORECARD_NOTES_MD = """# NOTES — scorecard-demo (synthetic)

## Outcome ledger
outcome: SC1 model=sonnet attempts=1 result=pass review=clean
outcome: SC2 model=sonnet attempts=2 result=retry-pass review=clean
outcome: SC3 model=haiku attempts=1 result=pass review=clean

## Agent ledger
agent: SC1 id=sc-verif-1 role=verifier model=sonnet findings=2 confirmed=1
agent: SC2 id=sc-verif-2 role=verifier model=sonnet findings=1 confirmed=1
"""

# T5: a Codex planning kit under `tasks/kits/` so the `-codex` scorecard label appears -- one
# task, one `outcome:` line.
CODEX_DEMO_KIT = "codex-demo"
CODEX_DEMO_TASKS_MD = """# TASKS — codex-demo (synthetic)

## Phase 1 — synthetic

### CD1 — a synthetic codex-planned task
- status: done
- model: sonnet
"""
CODEX_DEMO_NOTES_MD = """# NOTES — codex-demo (synthetic)

outcome: CD1 model=sonnet attempts=1 result=pass review=clean
"""


# ---------------------------------------------------------------------------------------------
# Sibling modules -- loaded lazily by absolute path and cached (the telemetry_snapshot shape).
# `bin/` is not a package; every owner is import-and-call, never copied.

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
# Small helpers.

def _plural(count, singular, plural):
    return f"{count} {singular if count == 1 else plural}"


def _sample(names):
    """Up to SAMPLE_SIZE names, and an ellipsis when there were more."""
    names = list(names)
    shown = ", ".join(names[:SAMPLE_SIZE])
    return shown + (", …" if len(names) > SAMPLE_SIZE else "")


def _clean(text):
    """`text` with anything UTF-8 cannot carry (a lone surrogate from an undecodable file name)
    replaced, so writing the page can never fail on a name the filesystem handed back."""
    return text.encode("utf-8", "replace").decode("utf-8")


def _blank(value):
    """A path argument that was given but is empty or whitespace. `Path("")` is `.`, the
    working directory, so a blank path is refused rather than quietly meaning "here"."""
    return value is not None and not str(value).strip()


def _as_list(value):
    """A field that should hold a list -> a list. `None` is empty and a list or tuple is itself;
    a string, a mapping or any other single value is ONE item that renders as its own text; a set
    is sorted (PLAN D9: the same input renders the same bytes) and any other iterable is drained.
    A malformed field renders what is there rather than raising (PLAN D10)."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=str)
    if isinstance(value, (str, bytes, dict)) or not hasattr(value, "__iter__"):
        return [value]
    return list(value)


# ---------------------------------------------------------------------------------------------
# Bounds. Caps travel as a dict so a test can lower one; hitting one leaves a note, and the note
# is the single record of the hit.

def default_caps():
    """Every bound this engine applies, as the dict the builders take."""
    return {
        "MAX_NAMESPACES_LISTED": MAX_NAMESPACES_LISTED,
        "MAX_NAMESPACES_READ": MAX_NAMESPACES_READ,
        "MAX_LEDGER_BYTES": MAX_LEDGER_BYTES,
        "MAX_KITS_PER_DIR": MAX_KITS_PER_DIR,
        "MAX_TASKS_MD_BYTES": MAX_TASKS_MD_BYTES,
        "MAX_EVAL_RUNS_RENDERED": MAX_EVAL_RUNS_RENDERED,
        "MAX_JOURNAL_DAYS": MAX_JOURNAL_DAYS,
        "MAX_TELEMETRY_ENVELOPES_PER_SOURCE": MAX_TELEMETRY_ENVELOPES_PER_SOURCE,
        "MAX_DIGEST_BYTES": MAX_DIGEST_BYTES,
        "MAX_ENVELOPE_BYTES": MAX_ENVELOPE_BYTES,
    }


def cap_value(caps, name):
    """The value of cap `name` in `caps`, falling back to its default."""
    value = (caps or {}).get(name, default_caps()[name])
    return max(0, int(value))


def cap_note(caps, name, detail):
    """The sentence a truncating bound leaves behind. `caps_report` recognises a hit by it."""
    return f"cap {name} ({cap_value(caps, name)}) reached — {detail}"


def caps_report(caps, notes):
    """Every cap with its value and whether this build hit it -> a list of dicts."""
    rows = []
    for name in CAP_NAMES:
        marker = f"cap {name} ("
        rows.append({
            "name": name,
            "value": cap_value(caps, name),
            "hit": any(marker in str(note) for note in notes or ()),
        })
    return rows


# ---------------------------------------------------------------------------------------------
# Checkouts: the primary one and every candidate (PLAN D4).

def _git(runner, argv, cwd, name):
    """One read-only git verb through `runner` -> (stdout, None) or (None, note)."""
    try:
        result = runner(list(argv), cwd=cwd, timeout=GIT_TIMEOUT_SECONDS, name=name)
    except Exception as exc:  # an injected runner is not bound by proc_runner's never-raise promise
        return None, f"{name} in {cwd} could not run ({type(exc).__name__})"
    if not isinstance(result, dict):
        return None, f"{name} in {cwd} returned no result"
    outcome = result.get("outcome")
    if outcome == "timeout":
        return None, (f"{name} in {cwd} exceeded GIT_TIMEOUT_SECONDS ({GIT_TIMEOUT_SECONDS} s) "
                      f"and was stopped")
    if outcome != "ok":
        rc = result.get("rc")
        exit_part = f", exit {rc}" if outcome == "failed" and rc is not None else ""
        return None, f"{name} in {cwd} did not succeed (outcome {outcome or 'unknown'}{exit_part})"
    stdout = result.get("stdout")
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", "replace")
    return (stdout if isinstance(stdout, str) else ""), None


def _primary_checkout(cwd, git, runner):
    """The checkout the page belongs to -> (path, notes). Never PLUGIN_ROOT on its own."""
    cwd = os.fspath(cwd)
    if not git:
        return cwd, [f"git disabled (--no-git): the primary checkout is the working directory "
                     f"{cwd}"]
    stdout, note = _git(runner, GIT_TOPLEVEL_ARGV, cwd, "git rev-parse")
    if note is None:
        lines = stdout.splitlines()
        top = lines[0] if lines else ""
        if top and os.path.isabs(top) and os.path.isdir(top):
            return top, []
        note = f"git rev-parse in {cwd} named no usable toplevel"
    return cwd, [f"{note}; the primary checkout is the working directory {cwd}"]


_C_ESCAPES = {"a": 7, "b": 8, "t": 9, "n": 10, "v": 11, "f": 12, "r": 13, '"': 34, "\\": 92}


def _git_unquote(raw):
    """A porcelain path as git printed it. Git prints paths raw, but may C-quote one holding
    unusual bytes (`core.quotePath`); a quoted one is unquoted, anything else is left alone."""
    if len(raw) < 2 or not (raw.startswith('"') and raw.endswith('"')):
        return raw
    body = raw[1:-1]
    out = bytearray()
    index = 0
    while index < len(body):
        char = body[index]
        if char == "\\" and index + 1 < len(body):
            octal = body[index + 1:index + 4]
            if len(octal) == 3 and all(c in "01234567" for c in octal):
                out.append(int(octal, 8) & 0xFF)
                index += 4
                continue
            if body[index + 1] in _C_ESCAPES:
                out.append(_C_ESCAPES[body[index + 1]])
                index += 2
                continue
        out += char.encode("utf-8", "surrogateescape")
        index += 1
    return out.decode("utf-8", "replace")


def _porcelain_worktrees(text):
    """Every `worktree <path>` line of `git worktree list --porcelain` -> paths, in order."""
    return [_git_unquote(line[len("worktree "):])
            for line in (text or "").splitlines() if line.startswith("worktree ")]


def discover_checkouts(cwd, flags=(), config=(), git=True, runner=None):
    """Every checkout the page maps namespaces for -> (checkouts, notes).

    In order: the PRIMARY checkout (the git toplevel of `cwd`, or `cwd` itself with a note),
    each `--checkout` flag, each `config.json` entry, then the worktrees of every candidate so
    far. Deduplicated by real path, which is also the form returned -- the one
    `runtime_data.project_namespace` hashes. A failed git verb or a candidate that is not a
    directory is a note, never an error; `git=False` spawns nothing at all. PLUGIN_ROOT is
    never added here: only the working directory, the flags and the config name candidates.
    """
    notes = []
    cwd = os.fspath(cwd)
    if git and runner is None:
        runner = _mod("proc_runner").run
    checkouts = []
    seen = set()

    def admit(path, origin):
        text = os.fspath(path) if path is not None else ""
        if not text.strip():
            notes.append(f"an empty checkout path ({origin}) was skipped")
            return
        if not os.path.isabs(text):
            text = os.path.join(cwd, text)
        if not os.path.isdir(text):
            notes.append(f"checkout candidate {text} ({origin}) is not a directory — skipped")
            return
        real = os.path.realpath(text)
        if real not in seen:
            seen.add(real)
            checkouts.append(real)

    primary, primary_notes = _primary_checkout(cwd, git, runner)
    notes.extend(primary_notes)
    admit(primary, "the primary checkout")
    for flag in flags or ():
        admit(flag, "--checkout")
    for entry in config or ():
        admit(entry, CONFIG_NAME)
    if not git:
        notes.append("git disabled (--no-git): no worktrees were listed")
        return checkouts, notes
    for base in list(checkouts):
        stdout, note = _git(runner, GIT_WORKTREES_ARGV, base, "git worktree list")
        if note is not None:
            notes.append(note)
            continue
        for path in _porcelain_worktrees(stdout):
            admit(path, f"a worktree git listed in {base}")
    return checkouts, notes


# ---------------------------------------------------------------------------------------------
# Namespaces: roots, and the three classes (PLAN D4).

# The namespace classes, in the order the page, the summary and the receipt list them.
CLASS_NAMES = ("mapped", "unmapped", "residue")

# How far the one data-home listing got. `absent`: the data home does not exist or is not a
# directory, so there is nothing to list and every count is an exact zero.
LISTING_STATES = ("complete", "truncated", "failed", "absent")

# What a class count claims: every one there is, at least that many, or nothing at all.
COUNT_QUALIFIERS = ("exact", "lower_bound", "unknown")


def namespace_roots(checkout):
    """The roots a checkout's engines namespace the data home by -> [(root, kind)].

    The checkout itself, and `tasks/kits`, because `attempt_ledger.kit_repo_root` maps a
    `tasks/kits/<slug>` kit (the Codex planning kits) to `tasks/kits` -- which is why a real
    data home holds a `kits-<digest>` namespace beside the checkout's own.
    """
    base = Path(checkout)
    return [(base, "checkout"), (base / "tasks" / "kits", "codex-kits")]


def _is_count(value):
    """A non-negative int that is not a bool: the only thing a class count can be."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _qualified(count, qualifier):
    """A class count and what it claims -> {"count", "qualifier"}. `count` is None exactly when
    the qualifier is `unknown`, and a lower bound of 0 is `unknown`: it says nothing (PLAN R3 --
    an unknown is never rendered as a zero)."""
    if qualifier == "lower_bound" and count <= 0:
        qualifier = "unknown"
    if qualifier not in ("exact", "lower_bound"):
        return {"count": None, "qualifier": "unknown"}
    return {"count": count, "qualifier": qualifier}


def class_count(classes, name):
    """The count of class `name` (one of CLASS_NAMES) with its qualifier -> {"count": int|None,
    "qualifier": "exact"|"lower_bound"|"unknown"}. THE way to show a class count: the `len()` of
    a class list is only what was seen, which is not the count when the listing was cut or
    failed. Anything malformed reads as unknown, never as a zero."""
    counts = classes.get("counts") if isinstance(classes, dict) else None
    entry = counts.get(name) if isinstance(counts, dict) else None
    if isinstance(entry, dict) and _is_count(entry.get("count")):
        count, qualifier = entry["count"], entry.get("qualifier")
        if qualifier == "exact" or (qualifier == "lower_bound" and count > 0):
            return {"count": count, "qualifier": qualifier}
    return {"count": None, "qualifier": "unknown"}


def _unknown_classes(checkouts=()):
    """The classes when nothing could be classified (no data home given, or classification
    raised): no rows, every count unknown, every checkout's namespace unknown -- never zeros."""
    unknown = {"count": None, "qualifier": "unknown"}
    return {
        "listing": "failed",
        "mapped": [],
        "unmapped": [],
        "residue": {**unknown, "sample": []},
        "counts": {name: dict(unknown) for name in CLASS_NAMES},
        "by_checkout": [{"checkout": os.fspath(checkout), "state": "unknown"}
                        for checkout in checkouts or ()],
    }


def _finish_classes(listing, mapped, unmapped, residue_seen, sample, lookups, checkout_names):
    """The classes dict from what the lookups and the listing established.

    mapped is `exact` when every lookup by name succeeded (found, or definitively not there),
    otherwise a lower bound. unmapped and residue come only from the listing: `exact` when it was
    complete (or the data home is absent), a lower bound when it was cut, `unknown` when it
    failed. A checkout is `mapped` when one of its namespaces was found, `absent` when every
    lookup for it definitively found none, and `unknown` otherwise.
    """
    mapped_qualifier = "lower_bound" if "unknown" in lookups.values() else "exact"
    listed_qualifier = {"complete": "exact", "absent": "exact",
                        "truncated": "lower_bound"}.get(listing, "unknown")
    counts = {
        "mapped": _qualified(len(mapped), mapped_qualifier),
        "unmapped": _qualified(len(unmapped), listed_qualifier),
        "residue": _qualified(residue_seen, listed_qualifier),
    }
    by_checkout = []
    for checkout, names in checkout_names:
        states = [lookups.get(name, "unknown") for name in names]
        state = "mapped" if "found" in states else "unknown" if "unknown" in states else "absent"
        by_checkout.append({"checkout": checkout, "state": state})
    return {
        "listing": listing,
        "mapped": mapped,
        "unmapped": unmapped,
        "residue": {**counts["residue"], "sample": list(sample)},
        "counts": counts,
        "by_checkout": by_checkout,
    }


def _examine_data_home(home_text):
    """What the data home is -> ("directory" | "absent" | "unknown", detail).

    A link to a directory is followed here -- the data home is the root the user chose; only the
    entries inside it are never followed. `absent` means it does not exist or is not a
    directory. `unknown` means it could not be examined (the detail is the error type) and is
    never reported as absent: `os.path.isdir` would say False for a permission error, and that
    False would read as "no namespaces".
    """
    try:
        mode = os.stat(home_text).st_mode
    except (FileNotFoundError, NotADirectoryError):
        return "absent", ("is not a directory" if os.path.lexists(home_text) else "does not exist")
    except OSError as exc:
        return "unknown", type(exc).__name__
    if not stat.S_ISDIR(mode):
        return "absent", "is not a directory"
    return "directory", None


def _lookup_namespace(home_text, name):
    """One expected namespace looked up by name, without following a link -> (state, error
    type). `found`: a real directory. `not-a-directory`: a link, file or anything else, which is
    not a namespace. `absent`: definitively nothing by that name. `unknown`: the lookup failed."""
    try:
        mode = os.lstat(os.path.join(home_text, name)).st_mode
    except FileNotFoundError:
        return "absent", None
    except OSError as exc:
        return "unknown", type(exc).__name__
    return ("found" if stat.S_ISDIR(mode) else "not-a-directory"), None


def _list_data_home(home_text, caps, notes):
    """The one bounded `os.scandir` of the data home -> (listing state, [(name, is_dir)])."""
    limit = cap_value(caps, "MAX_NAMESPACES_LISTED")
    entries = []
    listing = "complete"
    try:
        with os.scandir(home_text) as found:
            for entry in found:
                if len(entries) >= limit:
                    listing = "truncated"
                    break
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    is_dir = False
                entries.append((entry.name, is_dir))
    except OSError as exc:
        notes.append(f"data home {home_text} could not be listed ({type(exc).__name__}) — whether "
                     f"it holds unmapped or residue namespaces is unknown")
        return "failed", []
    if listing == "truncated":
        notes.append(cap_note(
            caps, "MAX_NAMESPACES_LISTED",
            f"the data home {home_text} holds more entries than were listed; the unmapped and "
            f"residue figures on this page cover only the entries listed, and the mapped "
            f"namespaces were looked up by name, outside this cap"))
    return listing, entries


def _one_listing(path):
    """The one shallow listing a namespace gets -> (names, None) or (None, error type)."""
    try:
        return os.listdir(path), None
    except OSError as exc:
        return None, type(exc).__name__


def _is_real_dir(path):
    """A directory reached without following a link."""
    try:
        return stat.S_ISDIR(os.lstat(path).st_mode)
    except OSError:
        return False


def _stores(path, namespace, names, error, notes):
    """The known stores present in a namespace's listing -> names in STORES order, or None."""
    if error is not None:
        notes.append(f"namespace {namespace} could not be listed ({error}); its stores are unknown")
        return None
    known = _mod("runtime_data").STORES
    present, other = [], []
    for entry in sorted(names):
        if entry in known and _is_real_dir(os.path.join(path, entry)):
            present.append(entry)
        else:
            other.append(entry)
    present.sort(key=known.index)
    if other:
        notes.append(
            f"namespace {namespace} also holds {_plural(len(other), 'entry', 'entries')} that "
            f"{'is' if len(other) == 1 else 'are'} not a store directory (links are not "
            f"followed): {_sample(other)}"
        )
    return present


def _legacy_notes(checkouts):
    """A note per legacy in-tree store `runtime_data.resolve_store` still resolves to."""
    rd = _mod("runtime_data")
    notes = []
    for checkout in checkouts or ():
        for name in rd.STORES:
            try:
                row = rd.resolve_store(name, checkout)
            except Exception as exc:
                notes.append(f"store {name} of {checkout} could not be resolved "
                             f"({type(exc).__name__})")
                continue
            if row.get("origin") == "legacy-in-tree":
                notes.append(f"legacy in-tree store {name} at {row.get('path')} — not scanned by "
                             f"the dashboard")
    return notes


def classify_namespaces(data_home, checkouts, caps):
    """Sort the data home's namespaces into mapped | unmapped | residue -> (classes, notes).

    Two steps, and the classes say how complete each was (PLAN D5, D7c):

    1. Every expected namespace -- `runtime_data.project_namespace` of each `namespace_roots`
       root, at most two per checkout -- is looked up BY NAME with `os.lstat`, outside the
       listing cap. A real directory is `mapped` and gets its one shallow listing for its
       stores; a link or other non-directory is not a namespace (skipped with a note); a lookup
       that fails is unknown (a note naming the error type). So the mapped class is exact
       whenever the lookups succeeded, however the listing went.
    2. One bounded `os.scandir` of the data home for everything else. An expected name is
       skipped (step 1 decided it); an entry that is not a directory without following links
       is skipped with a note; one `os.listdir` decides residue (RESIDUE_NAMESPACE_RE and
       nothing but an `attempts` store) -- a residue namespace is counted and never opened
       again -- and anything else is `unmapped`.

    `classes["listing"]` is one of LISTING_STATES; `classes["counts"]` gives each class its
    count and qualifier (read them through `class_count`); `classes["by_checkout"]` says per
    checkout whether its namespace is mapped, definitively absent, or unknown. Degraded paths
    are notes, never exceptions and never zeros.
    """
    rd = _mod("runtime_data")
    notes = []
    expected = {}
    checkout_names = []
    for checkout in checkouts or ():
        names = []
        for root, kind in namespace_roots(checkout):
            name = rd.project_namespace(root)
            names.append(name)
            expected.setdefault(name, (os.fspath(checkout), kind))
        checkout_names.append((os.fspath(checkout), names))
    notes.extend(_legacy_notes(checkouts))

    home_text = os.fspath(data_home)
    home_state, detail = _examine_data_home(home_text)
    if home_state == "absent":
        notes.append(f"data home {home_text} {detail} — it holds no namespaces")
        lookups = {name: "absent" for name in expected}
        return _finish_classes("absent", [], [], 0, [], lookups, checkout_names), notes
    if home_state == "unknown":
        notes.append(f"data home {home_text} could not be examined ({detail}) — whether it holds "
                     f"namespaces is unknown")
        lookups = {name: "unknown" for name in expected}
        return _finish_classes("failed", [], [], 0, [], lookups, checkout_names), notes

    mapped, skipped, lookups, failed = [], [], {}, {}
    for name in sorted(expected):
        state, error = _lookup_namespace(home_text, name)
        lookups[name] = state
        if state == "found":
            checkout, kind = expected[name]
            path = os.path.join(home_text, name)
            names, list_error = _one_listing(path)
            mapped.append({"namespace": name, "checkout": checkout, "kind": kind,
                           "stores": _stores(path, name, names, list_error, notes)})
        elif state == "not-a-directory":
            skipped.append(name)
        elif state == "unknown":
            failed[name] = error
    if failed:
        notes.append(
            f"{_plural(len(failed), 'expected namespace', 'expected namespaces')} could not be "
            f"looked up by name ({', '.join(sorted(set(failed.values())))}) — whether "
            f"{'it exists' if len(failed) == 1 else 'they exist'} is unknown: "
            f"{_sample(sorted(failed))}"
        )

    listing, entries = _list_data_home(home_text, caps, notes)
    unmapped, residue_seen, sample = [], 0, []
    for name, is_dir in sorted(entries):
        if name in expected:
            continue  # looked up by name above: mapped, not a namespace, absent or unknown there
        if not is_dir:
            skipped.append(name)
            continue
        path = os.path.join(home_text, name)
        names, error = _one_listing(path)
        if (error is None and RESIDUE_NAMESPACE_RE.fullmatch(name)
                and set(names) <= RESIDUE_STORES):
            residue_seen += 1
            if len(sample) < SAMPLE_SIZE:
                sample.append(name)
        else:
            unmapped.append({"namespace": name,
                             "stores": _stores(path, name, names, error, notes)})
    if skipped:
        notes.append(
            f"{_plural(len(skipped), 'data-home entry', 'data-home entries')} skipped: not a "
            f"directory without following links ({_sample(skipped)})"
        )
    return (_finish_classes(listing, mapped, unmapped, residue_seen, sample, lookups,
                            checkout_names), notes)


# ---------------------------------------------------------------------------------------------
# Scrubbing (PLAN D8). `home` is resolved once, in `main`, and passed down.

@functools.lru_cache(maxsize=8)
def _home_patterns(home):
    """Every spelling of `home` worth replacing, longest first so a realpath spelling that
    CONTAINS the plain one (macOS: /private/var/... around /var/...) is replaced whole."""
    prefixes = []
    if home and os.path.isabs(home):
        for candidate in (home, os.path.normpath(home), os.path.realpath(home)):
            prefix = candidate.rstrip("/")
            if len(prefix) > 1 and prefix not in prefixes:
                prefixes.append(prefix)
    prefixes.sort(key=len, reverse=True)
    # Only a whole path component: /Users/ann must not turn /Users/anna into ~a.
    return tuple(re.compile(re.escape(prefix) + r"(?![\w.\-])") for prefix in prefixes)


def scrub(text, home):
    """`text` with the home prefix (and its realpath, when different) replaced by `~`."""
    if text is None:
        return None
    text = str(text)
    for pattern in _home_patterns(os.fspath(home) if home else ""):
        text = pattern.sub("~", text)
    return text


def _scrub_tree(value, home):
    """A deep copy of `value` in plain JSON types, every string scrubbed and made UTF-8 safe."""
    if isinstance(value, str):
        return _clean(scrub(value, home))
    if isinstance(value, dict):
        return {_scrub_tree(str(key), home): _scrub_tree(item, home) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub_tree(item, home) for item in value]
    if isinstance(value, (set, frozenset)):
        return [_scrub_tree(item, home) for item in sorted(value, key=str)]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _clean(scrub(str(value), home))


# ---------------------------------------------------------------------------------------------
# The model. JSON-serializable; panels append to it in PANELS order.

def _collect_notes(global_notes, panels):
    """The page-wide note list: global notes, then each panel's, prefixed with its id."""
    notes = list(global_notes)
    for entry in panels:
        for note in entry.get("notes") or ():
            notes.append(f"{entry.get('id')}: {note}")
    return notes


def _failed_panel(pid, title, exc):
    return {
        "id": pid, "title": title, "source": "bin/dashboard.py",
        "observed": "not observed — the panel could not be built",
        "notes": [f"panel could not be built ({type(exc).__name__})"],
        "summary": "could not be built (see notes)",
        "blocks": [{"type": "p", "text": "This panel could not be built in this build; its note "
                                         "says why. Nothing is shown in its place."}],
    }


def build_model(data_home, checkouts, opts, caps):
    """The JSON-serializable model every rendering reads -> dict.

    `opts` carries `notes` (discovery and config notes gathered before the build), and what
    later panels consume: `projects_dir`, `no_transcripts`, `git`, and an optional `now`.
    `caps` overrides `default_caps()` key by key. The model's `notes` are the page-wide list:
    the global notes, then every panel's own (the classification's ride on the namespaces
    panel), each prefixed with its panel id -- what the bounds panel and build.json show, and
    what `caps_report` reads a hit from.
    """
    opts = dict(opts or {})
    caps = {**default_caps(), **dict(caps or {})}
    now = opts.get("now") or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    checkouts = [os.fspath(checkout) for checkout in checkouts or ()]
    notes = [str(note) for note in opts.get("notes") or ()]
    data_home = None if data_home is None or _blank(data_home) else Path(data_home)
    if data_home is None:
        classes = _unknown_classes(checkouts)
        class_notes = ["no data home was given — nothing was classified"]
    else:
        try:
            classes, class_notes = classify_namespaces(data_home, checkouts, caps)
        except Exception as exc:
            classes = _unknown_classes(checkouts)
            class_notes = [f"namespace classification failed ({type(exc).__name__}); nothing "
                           f"was classified"]
    model = {
        "schema_version": BUILD_SCHEMA_VERSION,
        "built_at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "primary_checkout": checkouts[0] if checkouts else None,
        "checkouts": checkouts,
        "data_home": None if data_home is None else os.fspath(data_home),
        "classes": classes,
        "panels": [],
        "caps": [],
        "notes": notes,
    }
    ctx = {"model": model, "data_home": data_home, "checkouts": checkouts, "opts": opts,
           "caps": caps, "now": now, "notes": notes}
    for pid, title, builder in PANELS:
        try:
            entry = dict(builder(ctx))
        except Exception as exc:
            entry = _failed_panel(pid, title, exc)
        entry["id"] = pid
        entry.setdefault("title", title)
        # A malformed `notes` (a string, a number) is kept as its text, never a crash (D10).
        entry["notes"] = [str(note) for note in _as_list(entry.get("notes") or None)]
        if pid == NAMESPACES_PANEL:
            # The classification's notes (the listing cap among them) belong to the panel that
            # shows the classes -- attached here, so a builder that raised cannot drop them.
            entry["notes"] = class_notes + [note for note in entry["notes"]
                                            if note not in class_notes]
        entry.setdefault("blocks", [])
        entry.setdefault("refresh_hint", None)  # T3: panel() renders this as a second meta line
        model["panels"].append(entry)
    model["notes"] = _collect_notes(notes, model["panels"])
    model["caps"] = caps_report(caps, model["notes"])
    return model


# ---------------------------------------------------------------------------------------------
# Panels registered by this task: `namespaces` (first) and `bounds` (always last).

RESIDUE_RULE = (
    f"Residue is a heuristic: a namespace whose name matches {RESIDUE_NAMESPACE_RE.pattern} "
    f"(a tempfile directory name plus the runtime_data digest) and whose one listing holds "
    f"nothing but an attempts store. It is counted, sampled by name, excluded from every figure "
    f"on this page, never opened beyond that listing and never deleted. Its limit: a real "
    f"checkout named like a temp directory whose only store is the attempt ledger is miscounted "
    f"as residue."
)


def _stores_text(stores):
    if stores is None:
        return "unknown"
    return ", ".join(stores) if stores else "none"


def _count_cell(entry):
    """A qualified class count as a typed cell: `N`, `at least N`, or the styled `unknown`."""
    return {"fmt": "count", "value": entry.get("count"), "qualifier": entry.get("qualifier")}


def _count_text(entry, noun):
    """A qualified class count as plain text (summaries, the terminal) -> `N noun`, `at least N
    noun`, or `unknown noun`. Anything malformed is `unknown`, never a zero."""
    entry = entry if isinstance(entry, dict) else {}
    count, qualifier = entry.get("count"), entry.get("qualifier")
    if _is_count(count) and qualifier == "exact":
        return f"{count} {noun}"
    if _is_count(count) and qualifier == "lower_bound" and count > 0:
        return f"at least {count} {noun}"
    return f"unknown {noun}"


def _is_exact_zero(entry):
    """Whether a qualified class count is a verified zero -- `{"count": 0, "qualifier":
    "exact"}`. Used to say "empty" in words instead of printing "0" for every class at once
    (R3): GUARDRAILS keeps a zero standing in for an owner's own state off the page, and that
    applies to a genuine zero exactly as it does to an unknown one."""
    return (isinstance(entry, dict) and entry.get("qualifier") == "exact"
            and entry.get("count") == 0)


# Why the listing did not reach everything, said once above the table.
_LISTING_SENTENCES = {
    "truncated": ("The data-home listing stopped at its cap (MAX_NAMESPACES_LISTED), so the "
                  "unmapped and residue figures cover only the entries it reached; the mapped "
                  "namespaces were looked up by name, outside that cap."),
    "failed": ("The data home could not be listed, so whether it holds unmapped or residue "
               "namespaces is unknown (see the notes)."),
}

# The table's empty text says "none found" only when the listing could have found one.
_EMPTY_TABLE_TEXT = {
    "complete": "No namespaces were found in the data home.",
    "absent": "No namespaces were found in the data home.",
    "truncated": ("No namespace was found among the entries the capped listing reached; the data "
                  "home holds more entries than were listed (see the notes)."),
}
_EMPTY_TABLE_UNKNOWN = ("No namespace can be shown: the data home could not be listed, and no "
                        "checkout's namespace was found by name (see the notes).")


def build_namespaces_panel(ctx):
    model = ctx["model"]
    classes = model["classes"]
    listing = classes.get("listing")
    counts = {name: class_count(classes, name) for name in CLASS_NAMES}
    residue = counts["residue"]
    rows = []
    for row in classes.get("mapped") or ():
        rows.append([row["namespace"], "mapped", f"{row['checkout']} ({row['kind']})",
                     _stores_text(row["stores"])])
    for row in classes.get("unmapped") or ():
        rows.append([row["namespace"], "unmapped", "—", _stores_text(row["stores"])])
    if residue["count"]:
        how_many = _plural(residue["count"], "namespace", "namespaces")
        if residue["qualifier"] == "lower_bound":
            how_many = f"at least {how_many}"
        sample = (classes.get("residue") or {}).get("sample") or ()
        rows.append([f"{how_many}, e.g. {_sample(sample)}", "residue (heuristic)", "—",
                     "at most an attempts store — listed once, never opened"])
    checkouts = model["checkouts"]
    across = f"across {_plural(len(checkouts), 'checkout', 'checkouts')}"
    data_home = model["data_home"]
    if listing == "absent":
        blocks = [{"type": "p", "parts": ["Data home ", data_home, ": absent — no namespaces."]}]
        summary = f"data home absent — no namespaces {across}"
    elif listing == "complete" and all(_is_exact_zero(counts[name]) for name in CLASS_NAMES):
        # R3c: a data home that exists but holds nothing is "empty" in words, never "0 mapped ·
        # 0 unmapped · 0 residue" -- a zero for one class inside a non-empty census still reads
        # as a count (the `else` branch below), only the all-zero case gets this sentence.
        blocks = [{"type": "p", "parts": ["Data home ", data_home, ": empty — no namespaces."]}]
        summary = f"data home empty — no namespaces {across}"
    else:
        parts = ["Data home ", data_home, ": "]
        for index, name in enumerate(CLASS_NAMES):
            parts += ([" · "] if index else []) + [_count_cell(counts[name]), f" {name}"]
        blocks = [{"type": "p", "parts": parts + ["."]}]
        summary = " · ".join(_count_text(counts[name], name) for name in CLASS_NAMES)
        summary += f" {across}"
        if listing != "complete":
            summary += f" (data-home listing {listing})"
    if data_home is None:
        blocks.append({"type": "p", "text": "No data home was given, so nothing was listed or "
                                            "looked up."})
    elif listing in _LISTING_SENTENCES:
        blocks.append({"type": "p", "text": _LISTING_SENTENCES[listing]})
    blocks += [
        {"type": "p", "text": RESIDUE_RULE},
        {"type": "table", "headers": ["namespace", "class", "checkout / kind", "stores present"],
         "rows": rows, "empty": _EMPTY_TABLE_TEXT.get(listing, _EMPTY_TABLE_UNKNOWN)},
        {"type": "p", "text": (f"Checkouts mapped by hashing their roots "
                               f"({len(checkouts)}): {', '.join(checkouts) or 'none'}.")},
    ]
    # "No namespace … for X" only when every lookup for X definitively found none; a checkout
    # missing from `by_checkout` is unknown, never absent.
    states = {entry.get("checkout"): entry.get("state")
              for entry in classes.get("by_checkout") or () if isinstance(entry, dict)}
    absent = [checkout for checkout in checkouts if states.get(checkout) == "absent"]
    unknown = [checkout for checkout in checkouts
               if states.get(checkout) not in ("absent", "mapped")]
    if absent:
        blocks.append({"type": "p", "text": ("No namespace in this data home for: "
                                             f"{', '.join(absent)}.")})
    if unknown:
        blocks.append({"type": "p", "text": ("It is unknown whether this data home holds a "
                                             f"namespace for: {', '.join(unknown)} — it could "
                                             "not be looked up (see the notes).")})
    return {
        "source": ("bin/dashboard.py — each checkout's namespaces looked up by name, then one "
                   "shallow listing of the data home, namespaces mapped through "
                   "runtime_data.project_namespace"),
        "observed": "live, at build time",
        "notes": [],
        "summary": summary,
        "blocks": blocks,
    }


####################################################################################################
# T4: namespaces read in depth for ledger facts (item 3), mapped first then unmapped by name
# (PLAN D4, D5; P1 fix round S6). `read_namespaces` is the one bounded, ordered list later panels
# (T6, T7) also read facts from directly: they use only its mapped entries and each notes the
# unmapped count their own store's shallow listing shows (S6); T4's ledger facts use the whole
# list.

def read_namespaces(ctx):
    """Mapped namespaces (as classified), then unmapped ones by name -> (rows, notes), bounded by
    MAX_NAMESPACES_READ. Each row is the classification's own dict for that namespace plus
    `"mapped": bool`, so a caller can tell the two apart without re-deriving it -- a mapped row
    also carries `checkout`/`kind`; an unmapped row carries only `namespace`/`stores`. A note is
    appended, once, when the cap cuts the combined list. The mapped rows are never among the ones
    a cut drops: they are complete-or-a-lower-bound already, from the classification's own
    by-name lookups (PLAN D5), and they are listed first."""
    classes = ctx["model"]["classes"]
    mapped = [dict(row, mapped=True) for row in classes.get("mapped") or ()]
    unmapped = [dict(row, mapped=False) for row in classes.get("unmapped") or ()]
    combined = mapped + unmapped
    limit = cap_value(ctx["caps"], "MAX_NAMESPACES_READ")
    notes = []
    if len(combined) > limit:
        notes.append(cap_note(
            ctx["caps"], "MAX_NAMESPACES_READ",
            f"{len(combined)} namespaces are mapped or unmapped ({len(mapped)} mapped, "
            f"{len(unmapped)} unmapped); only the first {limit} (mapped first, then unmapped by "
            f"name) were read for ledger facts"))
    return combined[:limit], notes


####################################################################################################
# Attempts panel (T4): the ledger and its history projection, through the owners only
# (attempt_history.join_kits/summarize, attempt_ledger.AttemptLedger). No figure here is priced,
# ranked or classified again, and no cell adds two bases, two harnesses or two owners together
# (PLAN D2, D3 row 1, D7a; R4) -- this file has no `sum(` call anywhere in it.

ATTEMPTS_PANEL = "attempts"


def _history_targets(classes):
    """Every mapped (checkout, kind) whose kits dir exists on disk -> a list of `{"label",
    "kits_dir", "namespace"}`, in the classification's own mapped order (PLAN D4: the two
    namespace roots per checkout, `C` and `C/tasks/kits`). A checkout with neither directory
    contributes nothing -- a fact about the checkout, not a degraded scan."""
    targets = []
    for row in classes.get("mapped") or ():
        checkout, namespace, kind = row.get("checkout"), row.get("namespace"), row.get("kind")
        if not checkout or not namespace:
            continue
        if kind == "checkout":
            kits_dir, label = Path(checkout) / ".claude" / "kits", str(checkout)
        elif kind == "codex-kits":
            kits_dir, label = Path(checkout) / "tasks" / "kits", f"{checkout} (tasks/kits)"
        else:
            continue
        if kits_dir.is_dir():
            targets.append({"label": label, "kits_dir": kits_dir, "namespace": namespace})
    return targets


def _kits_dir_oversized(kits_dir, store, caps, kc):
    """The first kit under `kits_dir` whose ledger file exceeds MAX_LEDGER_BYTES ->
    `(kit_name, size)`, or None. Checked before `attempt_history.join_kits` is ever called: that
    owner hands every kit's ledger to `AttemptLedger.events()` in full and has no per-kit size
    guard of its own (P1 fix round B3). `kit_contract.open_ledger`'s constructor only validates
    the name and composes a path -- no file is opened by this check, only stat'd."""
    limit = cap_value(caps, "MAX_LEDGER_BYTES")
    try:
        kit_dirs = sorted((p for p in Path(kits_dir).iterdir() if p.is_dir()),
                          key=lambda p: p.name)
    except OSError:
        return None  # join_kits will meet the same failure and note it itself
    for kit_dir in kit_dirs:
        if not (kit_dir / "TASKS.md").is_file():
            continue
        try:
            ledger = kc.open_ledger(kit_dir, store=store)
            size = os.stat(ledger.events_path).st_size
        except Exception:  # noqa: BLE001 -- an unopenable ledger is join_kits's own note to make
            continue
        if size > limit:
            return kit_dir.name, size
    return None


def _harness_tier_rows(by_harness):
    """`card["by_harness"]` flattened to one row per (harness, tier) -> `[(harness, tier,
    records, results_text)]`, sorted for a deterministic render. `results_text` joins the tier's
    own `results` dict as `result: n` pairs (TASKS.md item 2) as plain text: every value in it is
    a count `summarize` produced by incrementing, never None or NaN, so no typed cell is needed
    to keep it honest."""
    rows = []
    for harness in sorted(by_harness or {}):
        tiers = (by_harness[harness] or {}).get("tiers") or {}
        for tier in sorted(tiers):
            t = tiers[tier] or {}
            results = t.get("results") or {}
            text = ", ".join(f"{result}: {n}" for result, n in sorted(results.items()))
            rows.append((harness, tier, t.get("records", 0), text or "—"))
    return rows


def _cost_rows(by_basis, bases):
    """One row per basis in `attempt_history.COST_BASES` (read the tuple, never retyped) ->
    typed cells only: `n`, then the owner's own `usd`/`credits` through `fmt_usd(value, basis)` /
    `fmt_credits`. Every basis in the tuple gets a row whether or not any record carried it -- a
    basis with nothing recorded is `n=0`, `usd`/`credits` None, which renders `unknown`, never a
    zero standing in for "not observed" (PLAN R3)."""
    rows = []
    for basis in bases:
        t = (by_basis or {}).get(basis) or {}
        rows.append([basis, {"fmt": "count", "value": t.get("n", 0)},
                    {"fmt": "usd", "value": t.get("usd"), "basis": basis},
                    {"fmt": "credits", "value": t.get("credits")}])
    return rows


def _duration_rows(by_basis, bases):
    """One row per basis in `attempt_history.DURATION_BASES` (read the tuple, never retyped) ->
    typed cells only, on the same terms as `_cost_rows`."""
    rows = []
    for basis in bases:
        t = (by_basis or {}).get(basis) or {}
        rows.append([basis, {"fmt": "count", "value": t.get("n", 0)},
                    {"fmt": "seconds", "value": t.get("seconds")}])
    return rows


def _history_card_blocks(card, ah):
    """One history join's card (`attempt_history.summarize`) -> the blocks TASKS.md item 2
    describes, verbatim owner fields only. There is no total row: every basis, harness and tier
    renders on its own row, and the owner's own never-summed note is printed beneath its table."""
    blocks = []
    by_source = card.get("by_source") or {}
    parts = ["records: ", {"fmt": "count", "value": card.get("records", 0)}, "  by source: "]
    for source in sorted(by_source):
        parts += [source, ": ", {"fmt": "count", "value": by_source[source]}, "  "]
    blocks.append({"type": "p", "parts": parts})

    cov = card.get("coverage") or {}
    blocks.append({"type": "p", "parts": [
        "coverage — kits: ", {"fmt": "count", "value": cov.get("kits")},
        "  with ledger: ", {"fmt": "count", "value": cov.get("kits_with_ledger")},
        "  with notes: ", {"fmt": "count", "value": cov.get("kits_with_notes")},
        "  with role-use: ", {"fmt": "count", "value": cov.get("kits_with_role_use")}]})

    ht_rows = _harness_tier_rows(card.get("by_harness"))
    blocks.append({"type": "table", "headers": ["harness", "tier", "records", "results"],
                   "rows": [[h, t, {"fmt": "count", "value": n}, r] for h, t, n, r in ht_rows],
                   "caption": "records by harness and tier",
                   "empty": "no harness or tier recorded a record"})
    blocks.append({"type": "svg_bars", "title": "records by harness/tier",
                  "desc": "one bar per harness and tier; counts only, never a sum across them",
                  "label_key": "label", "value_key": "value", "value_header": "records",
                  "rows": [{"label": f"{h}/{t}", "value": n} for h, t, n, _r in ht_rows],
                  "empty": "no harness or tier recorded a record"})

    unknown_rows = [[field, {"fmt": "count", "value": n}]
                    for field, n in (card.get("unknown") or {}).items()]
    blocks.append({"type": "table", "headers": ["field", "unknown count"], "rows": unknown_rows,
                   "caption": "unknown, counted — never filled in",
                   "empty": "the owner recorded no fields"})

    fc_rows = [[cls, {"fmt": "count", "value": n}]
              for cls, n in sorted((card.get("failure_classes") or {}).items())]
    blocks.append({"type": "table", "headers": ["failure class", "count"], "rows": fc_rows,
                   "caption": "failure classes", "empty": "no failure classes recorded"})

    cost = card.get("cost") or {}
    blocks.append({"type": "table", "headers": ["basis", "n", "usd", "credits"],
                   "rows": _cost_rows(cost.get("by_basis"), ah.COST_BASES),
                   "caption": "cost by basis"})
    blocks.append({"type": "p", "text": cost.get("note") or ""})

    duration = card.get("duration") or {}
    blocks.append({"type": "table", "headers": ["basis", "n", "seconds"],
                   "rows": _duration_rows(duration.get("by_basis"), ah.DURATION_BASES),
                   "caption": "duration by basis"})
    blocks.append({"type": "p", "text": duration.get("note") or ""})

    latest_rows = []
    for key, entry in sorted((card.get("latest") or {}).items()):
        kit, _sep, task = str(key).partition("/")
        latest_rows.append([kit, task, (entry or {}).get("result"), (entry or {}).get("run")])
    blocks.append({"type": "table", "headers": ["kit", "task", "result", "run"],
                   "rows": latest_rows, "caption": "latest per task", "details": True,
                   "empty": "no task has a recorded verdict yet"})

    blocks.append({"type": "p", "parts": [
        "lineage chains: ", {"fmt": "count", "value": len(card.get("lineage") or [])}]})

    blocks.append({"type": "list", "items": list(card.get("notes") or ()),
                  "empty": "no notes from this history join"})
    return blocks


def _history_section_blocks(ctx, ah, al, kc, notes):
    """TASKS.md items 1-2: the history projection per mapped checkout with a kits dir, and its
    rendering -> (blocks, targets found). An owner that raises, or a kits dir this build must not
    open in full (P1 fix round B3), becomes a note -- never a crash and never a guess at the
    numbers it would have shown (PLAN D10)."""
    classes = ctx["model"]["classes"]
    data_home = ctx["data_home"]
    targets = _history_targets(classes)
    blocks = [{"type": "p", "text": (
        "Every figure below is an owner's own return value: attempt_history.join_kits/summarize "
        "per mapped checkout with a kits directory, and attempt_ledger.AttemptLedger read "
        "directly per namespace further down this panel. Nothing here is priced, ranked or "
        "classified again, and no basis, harness or owner is combined with another.")}]
    if data_home is None:
        blocks.append({"type": "p", "text": "No data home was given, so no checkout's history "
                                             "could be joined."})
        return blocks, targets
    if not targets:
        blocks.append({"type": "p", "text": "No mapped checkout has a .claude/kits or "
                                             "tasks/kits directory yet — no history projection "
                                             "to show."})
        return blocks, targets
    for target in targets:
        label, kits_dir, namespace = target["label"], target["kits_dir"], target["namespace"]
        blocks.append({"type": "p", "text": f"History for {label}:"})
        store = Path(data_home) / namespace / al.STORE
        oversized = _kits_dir_oversized(kits_dir, store, ctx["caps"], kc)
        if oversized is not None:
            kit_name, size = oversized
            notes.append(cap_note(
                ctx["caps"], "MAX_LEDGER_BYTES",
                f"history for {label} was not joined this build — kit {kit_name}'s ledger is "
                f"{size} bytes"))
            blocks.append({"type": "p", "text": "not joined this build — see the notes above"})
            continue
        try:
            records, join_notes, coverage = ah.join_kits(kits_dir, store=store)
            card = ah.summarize(records, join_notes, coverage)
        except Exception as exc:  # PLAN D10: an owner that raises is a note, never a crash
            notes.append(f"attempt history unavailable for {label}: {type(exc).__name__}")
            blocks.append({"type": "p", "text": "not available this build — see the notes "
                                                "above"})
            continue
        blocks.extend(_history_card_blocks(card, ah))
    return blocks, targets


# The event kinds `attempt_ledger.py` itself ever writes (`run.started`, `attempt.started`,
# `attempt.finished`, `verify.finished`, `task.projected`, `claim.taken`, `claim.released`,
# `claim.broken`) are always one or more lowercase words joined by dots. A `kind` outside that
# shape is free text from a tampered or corrupted line, and GUARDRAILS keeps free text that is
# not a title, name, label or note off the page -- this is none of those (R2).
KIND_SHAPE_RE = re.compile(r"\A[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)*\Z")

# Twice the longest real kind ("attempt.finished", 17 chars) with room for one more dotted
# segment -- long enough for any kind this ledger writes, far too short for a payload (R2).
MAX_KIND_CHARS = 40

# What every kind failing the shape or length check is counted as -- one fixed label, never the
# value itself, so a 20,000-character or markup-carrying `kind` never reaches the page (R2).
OTHER_KIND_LABEL = "other kinds (not rendered)"


def _kind_label(kind):
    """One event's raw `kind` field -> a safe histogram key: itself when it is a short,
    name-shaped string (`KIND_SHAPE_RE`, `MAX_KIND_CHARS`), else `OTHER_KIND_LABEL` -- never the
    raw value. A non-string `kind` (a dict or list a malformed line can carry, which would also
    be unhashable used bare as a dict key) is counted under the same label rather than raising
    (R1, R2)."""
    if isinstance(kind, str) and 0 < len(kind) <= MAX_KIND_CHARS and KIND_SHAPE_RE.match(kind):
        return kind
    return OTHER_KIND_LABEL


def _safe_ts(value):
    """A ledger event's `ts` field as a date-cell value: itself when it is a string, else None.
    A non-string `ts` (a tampered or malformed line) is unknown, never stringified and shown as
    though it were a real timestamp (R1)."""
    return value if isinstance(value, str) else None


def _one_ledger_fact(attempts_root, ns_name, ledger_name, al):
    """One ledger-facts row (TASKS.md item 3), read through `attempt_ledger.AttemptLedger` only.
    Never raises on a malformed `kind` or `ts` (R1a): each event's `kind` is counted through
    `_kind_label`, which never uses the raw value as a dict key, and `ts` is read through
    `_safe_ts`. Anything else that goes wrong is the caller's job to contain per row (R1b). The
    ledger's `report`, `tail`, `prompt_sha`, `verify_sha` and `note` fields are never read here."""
    ledger = al.AttemptLedger(attempts_root, ledger_name)
    events = ledger.events()
    kinds = {}
    for ev in events:
        label = _kind_label(ev.get("kind") if isinstance(ev, dict) else None)
        kinds[label] = kinds.get(label, 0) + 1
    kinds_text = ", ".join(f"{kind}: {n}" for kind, n in sorted(kinds.items())) or "—"
    open_n = len(ledger.open_attempts())
    claims_dir = attempts_root / ledger_name / al.CLAIMS_DIR
    claim_count = len(os.listdir(claims_dir)) if claims_dir.is_dir() else 0
    first_ts = _safe_ts(events[0].get("ts")) if events else None
    last_ts = _safe_ts(events[-1].get("ts")) if events else None
    return [ns_name, ledger_name, {"fmt": "count", "value": len(events)},
           {"fmt": "count", "value": ledger.corrupt}, kinds_text,
           {"fmt": "count", "value": open_n},
           {"fmt": "date", "value": first_ts}, {"fmt": "date", "value": last_ts},
           {"fmt": "count", "value": claim_count}]


def _ledger_fact_rows(data_home, ns_row, caps, al, notes):
    """Every `attempts/<ledger>` subdir of one namespace -> its rows for the ledger-facts table.
    A namespace with no attempts store contributes nothing -- a fact about the namespace, not a
    degraded scan. A ledger over MAX_LEDGER_BYTES is skipped by its `os.stat` size alone and is
    never opened for read (TASKS.md item 3); anything else that goes wrong reading one ledger is
    a note for that row only."""
    ns_name = ns_row.get("namespace")
    stores = ns_row.get("stores")
    if stores is None:
        notes.append(f"ledger facts for {ns_name}: its store listing failed, so whether it holds "
                     f"an attempts store is unknown")
        return []
    if "attempts" not in stores:
        return []
    attempts_root = Path(data_home) / ns_name / al.STORE
    sub_names, error = _one_listing(attempts_root)
    if error is not None:
        notes.append(f"ledger facts for {ns_name}: its attempts store could not be listed "
                     f"({error})")
        return []
    limit = cap_value(caps, "MAX_LEDGER_BYTES")
    rows = []
    for ledger_name in sorted(sub_names):
        if not _is_real_dir(attempts_root / ledger_name):
            continue
        events_path = attempts_root / ledger_name / al.EVENTS_FILE
        try:
            size = os.stat(events_path).st_size
        except FileNotFoundError:
            continue
        except OSError as exc:
            notes.append(f"ledger facts for {ns_name}/{ledger_name}: could not be stat'd "
                         f"({type(exc).__name__})")
            continue
        if size > limit:
            notes.append(cap_note(
                caps, "MAX_LEDGER_BYTES",
                f"ledger {ns_name}/{ledger_name} is {size} bytes — skipped, never read"))
            continue
        try:
            rows.append(_one_ledger_fact(attempts_root, ns_name, ledger_name, al))
        except Exception as exc:  # PLAN D10, R1b: any failure reading one ledger is a note for
            # that row only, naming the exception TYPE only -- every other ledger still renders.
            notes.append(f"ledger facts for {ns_name}/{ledger_name}: {type(exc).__name__}")
    return rows


def _ledger_facts_blocks(ctx, al, notes):
    """TASKS.md item 3: raw ledger facts for every namespace `read_namespaces` bounds to, mapped
    then unmapped -- the only place an unmapped namespace's own ledger is read at all (PLAN D4)."""
    data_home = ctx["data_home"]
    if data_home is None:
        return [{"type": "p", "text": "No data home was given, so no ledger could be read "
                                       "directly."}]
    ns_rows, cap_notes = read_namespaces(ctx)
    notes.extend(cap_notes)
    rows = []
    for ns_row in ns_rows:
        rows.extend(_ledger_fact_rows(data_home, ns_row, ctx["caps"], al, notes))
    return [
        {"type": "p", "text": ("Ledger facts, read directly from each namespace's attempts "
                               "store (attempt_ledger.AttemptLedger), independent of any "
                               "checkout match above:")},
        {"type": "table",
         "headers": ["namespace", "ledger", "events", "corrupt lines", "kind histogram",
                     "open attempts", "first ts", "last ts", "claim files"],
         "rows": rows, "empty": "no ledger found"},
    ]


_RESIDUE_TEXT = ("residue namespaces (heuristic: tempfile-shaped name holding only an attempts "
                 "store) — counted, not opened, excluded from every figure above")


def _residue_line_block(classes):
    """TASKS.md item 4: the one residue line, its count read only through `class_count`. An
    absent data home gets its own sentence with no count at all; an exact zero (a data home
    that exists and simply has none) is worded without a digit either -- GUARDRAILS: absence
    renders as text, never `0`, and that holds for a verified zero exactly as it does for an
    unknown one (R3b). Anything else (a positive exact count, or a lower bound) is the qualified
    count cell, as before."""
    entry = class_count(classes, "residue")
    if classes.get("listing") == "absent":
        return {"type": "p", "text": "No data home, so no residue namespaces to count."}
    if entry.get("qualifier") == "exact" and entry.get("count") == 0:
        return {"type": "p", "text": f"No {_RESIDUE_TEXT}."}
    return {"type": "p", "parts": [_count_cell(entry), f" {_RESIDUE_TEXT}"]}


def _guarded_section(builder, section_name, notes):
    """Run one Attempts sub-section builder, contained on its own (R1c): a failure becomes one
    fallback block plus a note naming the section and the exception TYPE only (never the
    message, which can carry a path) -- the other sections are built by their own separate call
    and are never affected."""
    try:
        return builder()
    except Exception as exc:  # noqa: BLE001 -- contained per section, never the whole panel
        notes.append(f"{section_name} section could not be built ({type(exc).__name__})")
        return [{"type": "p", "text": f"The {section_name} section could not be built this "
                                      f"build — see the notes above."}]


def build_attempts_panel(ctx):
    ah, al = _mod("attempt_history"), _mod("attempt_ledger")
    kc = _mod("kit_contract")
    notes = []
    targets = []

    def _history():
        nonlocal targets
        blocks, targets = _history_section_blocks(ctx, ah, al, kc, notes)
        return blocks

    history_blocks = _guarded_section(_history, "history", notes)
    ledger_blocks = _guarded_section(
        lambda: _ledger_facts_blocks(ctx, al, notes), "ledger facts", notes)
    residue_blocks = _guarded_section(
        lambda: [_residue_line_block(ctx["model"]["classes"])], "residue", notes)
    blocks = history_blocks + ledger_blocks + residue_blocks
    return {
        "source": ("bin/dashboard.py — attempt_history.join_kits/summarize per mapped checkout's "
                  "kits dir, attempt_ledger.AttemptLedger per namespace read"),
        "observed": "live, at build time",
        "notes": notes,
        "summary": (f"history joined for {len(targets)} checkout target(s); ledger facts read "
                   f"directly per namespace"),
        "blocks": blocks,
    }


####################################################################################################
# Routing scorecard panel (T5): the cross-kit history card and the per-role value card, through
# `routing_scorecard.assemble_history_card`/`scan_kits`/`build_roles_card` only (PLAN D2, D3 row
# 2, D7, D15). No figure here is priced, ranked, classified or re-derived -- a rate/ratio the
# owner computed renders as the owner's own value, never through `fmt_count` (a whole-number
# rate must keep its own decimal shape, not collapse to a bare count).

SCORECARD_PANEL = "scorecard"
KITS_PANEL = "kits"


def _sanitize_label(name):
    """A checkout basename as a token label safe for `routing_scorecard._LABEL_RE`
    (`^[A-Za-z0-9][A-Za-z0-9._-]*$`, TASKS.md item 1): every character outside its class
    becomes `-`, and a result that still would not start with `[A-Za-z0-9]` (an empty name, or
    one starting with `.`/`-`/`_`) is prefixed with `k` so the label always matches."""
    safe = "".join(ch if re.match(r"[A-Za-z0-9._-]", ch) else "-" for ch in name) or "k"
    if not re.match(r"[A-Za-z0-9]", safe[0]):
        safe = "k" + safe
    return safe


def _scorecard_kits_dirs(checkouts):
    """Every kits dir that exists under a discovered checkout -> `[{"label", "path"}]`, in
    checkout order (TASKS.md item 1): `<checkout>/.claude/kits` labelled with the checkout's
    own basename, `<checkout>/tasks/kits` labelled `<basename>-codex`. A checkout with neither
    directory contributes nothing -- a fact about the checkout, not a degraded scan. Duplicate
    labels across checkouts are the owner's own problem to resolve (`resolve_kits_dirs` renames
    and notes); this helper does not dedupe."""
    found = []
    for checkout in checkouts or ():
        base = _sanitize_label(Path(checkout).name or "checkout")
        claude_kits = Path(checkout) / ".claude" / "kits"
        if claude_kits.is_dir():
            found.append({"label": base, "path": claude_kits})
        codex_kits = Path(checkout) / "tasks" / "kits"
        if codex_kits.is_dir():
            found.append({"label": f"{base}-codex", "path": codex_kits})
    return found


_NO_KITS_DIRS_TEXT = "no kits directories found in the discovered checkouts"


def _owner_value_cell(value):
    """One owner-emitted field value as a table cell, generically: a nested dict of small
    counts (a tier's `reroutes`, a role's `results`/`by_kind`/`by_kit`) becomes joined
    `key: n` text; a bool or a plain int becomes a typed count cell; anything else (a rate or
    ratio float, `None`, a string) is a plain cell -- `esc` renders it verbatim, never reshaped
    by `fmt_count`'s float formatting, so a whole-number rate keeps its own decimal shape
    rather than reading like a bare count (PLAN D2: never re-derive a rate)."""
    if isinstance(value, dict):
        return ", ".join(f"{k}: {v}" for k, v in sorted(value.items())) or "—"
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return {"fmt": "count", "value": value}
    return value


def _first_seen_keys(mapping_of_dicts, order):
    """Every key seen across `mapping_of_dicts[k]` for `k` in `order`, first-seen order -- the
    column set for a table whose rows are heterogeneous small dicts (TASKS.md item 2: "every
    key each tier dict carries")."""
    fields = []
    for key in order:
        for field in (mapping_of_dicts.get(key) or {}):
            if field not in fields:
                fields.append(field)
    return fields


def _tiers_table_and_chart(card, rs):
    """TASKS.md item 2: the `tiers` table, every key each tier dict carries, rendered as-is,
    plus its bar-chart twin (first-try/retry/escalated/blocked per tier). No rate is computed
    here -- `first_try_rate`/`escalation_rate` are the owner's own values (PLAN D2)."""
    tiers = card.get("tiers") or {}
    order = [t for t in rs.LIVE_TIER_ORDER if t in tiers] or sorted(tiers)
    fields = _first_seen_keys(tiers, order)
    rows = [[tier] + [_owner_value_cell(tiers[tier].get(field)) for field in fields]
            for tier in order]
    blocks = [{"type": "table", "headers": ["tier"] + fields, "rows": rows,
              "caption": "tiers", "empty": "no tiers recorded"}]
    if not any(field.endswith("_rate") for field in fields):
        # TASKS.md item 2: a future count-only card gets this note instead of a computed rate
        # -- the dashboard never divides.
        blocks.append({"type": "p",
                       "text": "rates: see `python3 bin/routing_scorecard.py --history`"})
    chart_fields = [f for f in ("first_try", "retry_pass", "escalated_pass", "blocked")
                    if f in fields]
    chart_rows = [{"label": f"{tier}/{field}", "value": tiers[tier].get(field)}
                  for tier in order for field in chart_fields]
    blocks.append({"type": "svg_bars", "title": "first-try/retry/escalated/blocked per tier",
                   "desc": "one bar per tier and result kind; counts only, never summed across "
                           "tiers", "label_key": "label", "value_key": "value",
                   "value_header": "count", "rows": chart_rows,
                   "empty": "no tier result counts to chart"})
    return blocks


def _history_kits_table(card):
    """TASKS.md item 2: the `kits` table. `cost` is the owner's per-kit `kit_cost_summary`
    dict or None; its `actual_usd` renders through a typed `usd` cell, never a bare float."""
    rows = []
    for row in card.get("kits") or ():
        cost = row.get("cost") or {}
        rows.append([
            row.get("kit"), {"fmt": "count", "value": row.get("tasks")},
            {"fmt": "count", "value": row.get("with_outcome")},
            {"fmt": "count", "value": row.get("first_try_pass")},
            {"fmt": "count", "value": row.get("retry_pass")},
            {"fmt": "count", "value": row.get("escalated_pass")},
            {"fmt": "count", "value": row.get("blocked")},
            {"fmt": "count", "value": len(row.get("sessions") or ())},
            {"fmt": "usd", "value": cost.get("actual_usd"), "basis": "actual, priced sessions"},
        ])
    return {"type": "table",
           "headers": ["kit", "tasks", "with outcome", "first-try pass", "retry pass",
                       "escalated pass", "blocked", "sessions", "cost"],
           "rows": rows, "caption": "kits", "empty": "no kits recorded", "details": True}


def _dollars_blocks(card):
    """TASKS.md item 2: the `dollars` block. `None` renders the owner's OWN explanatory note
    from `card["notes"]` (never a fabricated reason); otherwise `actual_usd`/`counterfactual_usd`/
    `delta_usd` each carry the SAME basis label -- the exact wording TASKS.md item 2 pins,
    "actual vs all-<display> counterfactual over priced sessions only — coverage <coverage>" --
    so the coverage and counterfactual-model facts ride beside every dollar figure itself, never
    only in a separate sentence a reader could miss; `ratio` renders as the owner's own value
    (never through `fmt_count`)."""
    dollars = card.get("dollars")
    if dollars is None:
        note = next((n for n in (card.get("notes") or ()) if "dollars n/a" in n), None)
        return [{"type": "p", "text": note or
                "dollars unavailable — the owner recorded no explanatory note"}]
    cf = dollars.get("counterfactual_model") or {}
    label = (f"actual vs all-{cf.get('display')} counterfactual over priced sessions only — "
            f"coverage {dollars.get('coverage')}")
    parts = [
        "actual ", {"fmt": "usd", "value": dollars.get("actual_usd"), "basis": label},
        "  counterfactual ", {"fmt": "usd", "value": dollars.get("counterfactual_usd"),
                              "basis": label},
        "  delta ", {"fmt": "usd", "value": dollars.get("delta_usd"), "basis": label},
        "  ratio ", _owner_value_cell(dollars.get("ratio")),
        "  kits with sessions ", {"fmt": "count", "value": dollars.get("kits_with_sessions")},
        "/", {"fmt": "count", "value": dollars.get("kits_total")},
        "  sessions priced ", {"fmt": "count", "value": dollars.get("sessions_priced")},
        "/", {"fmt": "count", "value": dollars.get("sessions_found")},
        "  pricing cached ", {"fmt": "date", "value": dollars.get("pricing_cached")},
    ]
    return [{"type": "p", "parts": parts}]


def _role_block_rows(d):
    """One `card["roles"][name]` dict -> `[field, value]` rows, every value through
    `_owner_value_cell`. `by_tier` is rendered separately, as its own per-tier table
    (`_role_by_tier_table`) -- V1: it is the per-tier evidence PLAN D14 cites, not a scope
    choice to leave off the page."""
    return [[field, _owner_value_cell(value)] for field, value in (d or {}).items()
           if field != "by_tier"]


def _role_by_tier_table(role_name, by_tier, rs):
    """T5 retry V1: `roles[role_name]["by_tier"]` -- every `LIVE_TIER_ORDER` tier's own
    `{events, with_precision, findings, confirmed, precision}`, rendered verbatim (a `None`
    precision is the styled unknown through `_owner_value_cell`, never a fabricated 0) -- the
    per-tier evidence PLAN D14 cites for the verifier/reviewer model pins."""
    by_tier = by_tier or {}
    order = [t for t in rs.LIVE_TIER_ORDER if t in by_tier] or sorted(by_tier)
    fields = _first_seen_keys(by_tier, order)
    rows = [[tier] + [_owner_value_cell((by_tier[tier] or {}).get(field)) for field in fields]
            for tier in order]
    return {"type": "table", "headers": ["tier"] + fields, "rows": rows,
           "caption": f"role: {role_name} by tier", "empty": "no tiers recorded"}


def _card_roles_blocks(card, rs):
    """TASKS.md item 2: `roles`, the history card's own role-quality block -- one small table
    per role it carries (verifier, escalation, reviewer, architect), including the architect's
    brief-defect kinds (`by_kind`), plus a per-tier table for every role that carries a
    `by_tier` breakdown (verifier, reviewer -- V1)."""
    roles = card.get("roles") or {}
    blocks = [{"type": "p", "text": "Role quality (the history card's own roles block; "
                                    "implementer quality is in the tiers table above):"}]
    for role_name in ("verifier", "escalation", "reviewer", "architect"):
        role_dict = roles.get(role_name) or {}
        blocks.append({"type": "table", "headers": ["field", "value"],
                       "rows": _role_block_rows(role_dict),
                       "caption": f"role: {role_name}", "empty": "no evidence recorded"})
        if "by_tier" in role_dict:
            blocks.append(_role_by_tier_table(role_name, role_dict.get("by_tier"), rs))
    return blocks


def _reroutes_block(card):
    reroutes = card.get("reroutes") or {}
    return {"type": "p", "parts": [
        "reroutes — events: ", {"fmt": "count", "value": reroutes.get("events")},
        "  applied: ", {"fmt": "count", "value": reroutes.get("applied")},
        "  advisory: ", {"fmt": "count", "value": reroutes.get("advisory")}]}


def _routing_history_card_blocks(card, rs):
    # `card["generated_at"]` is the owner's own `datetime.now()` read (routing_scorecard's,
    # not this engine's `--now`-controlled clock) -- rendering it would make the page
    # non-deterministic a second way beyond the dashboard's own build-time line, against PLAN
    # D9 ("deterministic ... except the build-time line"). Left out of the headline for
    # exactly that reason; the kit count is the stable, owner-enumerated field instead.
    blocks = [{"type": "p", "parts": [
        "routing history — ", {"fmt": "count", "value": len(card.get("kits") or ())},
        " kit(s)"]}]
    blocks.extend(_tiers_table_and_chart(card, rs))
    blocks.append(_history_kits_table(card))
    blocks.extend(_dollars_blocks(card))
    blocks.extend(_card_roles_blocks(card, rs))
    blocks.append(_reroutes_block(card))
    blocks.append({"type": "list", "items": list(card.get("notes") or ()),
                  "empty": "no notes from the history card"})
    return blocks


def _history_card_section(ctx, rs, kits_dirs, notes):
    """TASKS.md item 2: one `assemble_history_card` call over every discovered kits dir's
    token together (the owner's own namespacing joins them). `--no-transcripts` prices from an
    empty temp dir created for this build and removed after (never the real projects dir)."""
    tokens = [f"{e['label']}={e['path']}" for e in kits_dirs]
    opts = ctx.get("opts") or {}
    no_transcripts = bool(opts.get("no_transcripts"))
    projects_dir = opts.get("projects_dir")
    tmp_holder = None
    if no_transcripts:
        tmp_holder = tempfile.TemporaryDirectory(prefix="polytropos-dashboard-no-transcripts-")
        projects_dir = tmp_holder.name
        notes.append("transcript pricing skipped (--no-transcripts): dollars render as the "
                     "owner's quality-only label")
    try:
        try:
            card = rs.assemble_history_card(
                tokens, projects_dir=str(projects_dir) if projects_dir else None)
        except ValueError as exc:
            notes.append(f"routing history unavailable: {type(exc).__name__}")
            return [{"type": "p", "text": "not available this build — see the notes above"}]
    finally:
        if tmp_holder is not None:
            tmp_holder.cleanup()
    return _routing_history_card_blocks(card, rs)


def _roles_card_blocks(roles_card):
    """TASKS.md item 3: `aggregate` as a table of the owner's values verbatim (a role's
    dispatch count below `min_dispatches` is labelled the owner's own way, in the role name
    cell -- never a coerced "insufficient sample" cell value), `min_dispatches`, `notes`, and
    the per-kit sections as a `details` table (kit, roster label, roster size)."""
    agg = roles_card.get("aggregate") or {}
    agg_roles = agg.get("roles") or {}
    blocks = [{"type": "p", "parts": [
        "aggregate roster ", agg.get("roster_label"), " (",
        ", ".join(agg.get("roster") or ()) or "none", ")  min dispatches: ",
        {"fmt": "count", "value": roles_card.get("min_dispatches")}]}]
    agg_rows = []
    for role in sorted(agg_roles):
        b = agg_roles[role] or {}
        label = f"{role} (insufficient sample)" if b.get("insufficient_sample") else role
        agg_rows.append([
            label, _owner_value_cell(b.get("dispatches")), _owner_value_cell(b.get("findings")),
            _owner_value_cell(b.get("confirmed")), _owner_value_cell(b.get("precision")),
            _owner_value_cell(b.get("marginal")), _owner_value_cell(b.get("marginal_unmeasured")),
            _owner_value_cell(b.get("marginal_rate")),
            {"fmt": "usd", "value": b.get("dollars_usd"), "basis": "per role"},
        ])
    blocks.append({"type": "table",
                   "headers": ["role", "dispatches", "findings", "confirmed", "precision",
                               "marginal", "marginal unmeasured", "marginal rate", "dollars"],
                   "rows": agg_rows, "caption": "aggregate role value",
                   "empty": "no role-quality evidence recorded"})
    kit_rows = [[k.get("kit"), k.get("roster_label"),
                {"fmt": "count", "value": k.get("roster_size")}]
               for k in roles_card.get("kits") or ()]
    blocks.append({"type": "table", "headers": ["kit", "roster label", "roster size"],
                   "rows": kit_rows, "caption": "per-kit roster", "details": True,
                   "empty": "no kits scanned"})
    blocks.append({"type": "list", "items": list(roles_card.get("notes") or ()),
                  "empty": "no notes from the roles card"})
    return blocks


def _roles_value_section(rs, kits_dirs, notes):
    """TASKS.md item 3: the `run_roles` bare shape, once per kits dir -- `scan_kits` then
    `build_roles_card` with no `dollars_kit` (T5 never passes `--session`)."""
    blocks = [{"type": "p", "text": "Per-role value (routing_scorecard.scan_kits / "
                                    "build_roles_card, the bare shape), once per kits dir:"}]
    for entry in kits_dirs:
        label, path = entry["label"], entry["path"]
        blocks.append({"type": "p", "text": f"Roles for {label}:"})
        try:
            records, scan_notes = rs.scan_kits(path)
            roles_card = rs.build_roles_card(records, path, extra_notes=scan_notes)
        except Exception as exc:  # PLAN D10: an owner that raises is a note, never a crash
            notes.append(f"roles value unavailable for {label}: {type(exc).__name__}")
            blocks.append({"type": "p", "text": "not available this build — see the notes "
                                                "above"})
            continue
        blocks.extend(_roles_card_blocks(roles_card))
    return blocks


def _symlinked_kit_names(path):
    """Every symlinked entry directly under `path` -> a sorted list of names (T5 retry R3): a
    shallow listing only, never followed. `routing_scorecard.scan_kits` walks with
    `Path.iterdir()`/`is_dir()`, which DOES follow a symlink -- unlike the kits-in-flight
    panel, which refuses to (`_is_real_dir`). This is only ever used to NAME that difference in
    a note; the dashboard never reads what a symlink here points to."""
    try:
        return sorted(p.name for p in Path(path).iterdir() if p.is_symlink())
    except OSError:
        return []


def build_scorecard_panel(ctx):
    rs = _mod("routing_scorecard")
    kits_dirs = _scorecard_kits_dirs(ctx["checkouts"])
    source = ("bin/dashboard.py — routing_scorecard.assemble_history_card / scan_kits / "
              "build_roles_card over every discovered checkout's kits dir")
    if not kits_dirs:
        return {"source": source, "observed": "live, at build time", "notes": [],
               "summary": _NO_KITS_DIRS_TEXT,
               "blocks": [{"type": "p", "text": _NO_KITS_DIRS_TEXT}]}
    notes = []
    for entry in kits_dirs:
        symlinked = _symlinked_kit_names(entry["path"])
        if symlinked:
            notes.append(f"{entry['label']}: symlinked kit dir(s) {', '.join(symlinked)} — "
                         f"routing_scorecard follows these, unlike the kits-in-flight panel")
    history_blocks = _guarded_section(
        lambda: _history_card_section(ctx, rs, kits_dirs, notes), "history", notes)
    roles_blocks = _guarded_section(
        lambda: _roles_value_section(rs, kits_dirs, notes), "roles value", notes)
    return {
        "source": source, "observed": "live, at build time", "notes": notes,
        "summary": f"history + roles value over {len(kits_dirs)} kits dir(s)",
        "blocks": history_blocks + roles_blocks,
    }


####################################################################################################
# Kits in flight panel (T5): per checkout's kits dir, through `kit_contract.parse_tasks` /
# `validate_graph` / `graph_state` only (PLAN D2, D3 row 6).

def _kits_panel_dirs(checkouts, rs):
    """T5 retry R2: the kits panel's own kits dirs, labelled through the SAME owner resolution
    `assemble_history_card` uses internally (`routing_scorecard.resolve_kits_dirs`) -- never
    `_scorecard_kits_dirs`'s raw, unresolved list, whose own docstring says it does not dedupe.
    Two checkouts that would otherwise collide on one label are renamed and noted by the owner,
    exactly as the scorecard panel already shows them -> `(entries, notes)`."""
    found = _scorecard_kits_dirs(checkouts)
    if not found:
        return [], []
    tokens = [f"{e['label']}={e['path']}" for e in found]
    return rs.resolve_kits_dirs(tokens)


def build_kits_panel(ctx):
    kc = _mod("kit_contract")
    rs = _mod("routing_scorecard")
    kits_dirs, resolve_notes = _kits_panel_dirs(ctx["checkouts"], rs)
    source = ("bin/dashboard.py — kit_contract.parse_tasks/validate_graph/graph_state per kit "
             "dir under each discovered checkout's kits dir, labelled through "
             "routing_scorecard.resolve_kits_dirs")
    if not kits_dirs:
        return {"source": source, "observed": "live, at build time", "notes": [],
               "summary": _NO_KITS_DIRS_TEXT,
               "blocks": [{"type": "p", "text": _NO_KITS_DIRS_TEXT}]}
    notes = list(resolve_notes)
    rows = []
    for entry in kits_dirs:
        label, path = entry["label"], entry["path"]
        try:
            candidates = sorted(Path(path).iterdir(), key=lambda p: p.name)
        except OSError as exc:
            notes.append(f"kits in flight for {label}: could not be listed "
                         f"({type(exc).__name__})")
            continue
        # R3: a symlinked kit dir is skipped with a note and never read -- the namespace
        # classifier's own `os.lstat`/`is_symlink` convention (`_is_real_dir`), never
        # `Path.is_dir()`, which follows the link.
        kit_dirs = []
        for candidate in candidates:
            if candidate.is_symlink():
                notes.append(f"kits in flight for {label}: {candidate.name} is a symlinked "
                             f"kit dir — skipped, never read")
                continue
            if _is_real_dir(candidate):
                kit_dirs.append(candidate)
        limit = cap_value(ctx["caps"], "MAX_KITS_PER_DIR")
        if len(kit_dirs) > limit:
            notes.append(cap_note(
                ctx["caps"], "MAX_KITS_PER_DIR",
                f"{label} holds more kit dirs than were read; only the first {limit} "
                f"(sorted by name) are shown"))
            kit_dirs = kit_dirs[:limit]
        for kit_dir in kit_dirs:
            tasks_md = kit_dir / "TASKS.md"
            if not tasks_md.is_file():
                continue
            # R4: size-gated by `os.stat` alone, before any read -- an over-cap TASKS.md is
            # skipped and never opened, the same discipline T4 applies to a ledger file.
            try:
                size = os.stat(tasks_md).st_size
            except OSError as exc:
                notes.append(f"kits in flight for {label}/{kit_dir.name}: TASKS.md could not "
                             f"be stat'd ({type(exc).__name__})")
                continue
            if size > cap_value(ctx["caps"], "MAX_TASKS_MD_BYTES"):
                notes.append(cap_note(
                    ctx["caps"], "MAX_TASKS_MD_BYTES",
                    f"{label}/{kit_dir.name}'s TASKS.md is {size} bytes — skipped, never "
                    f"read"))
                continue
            try:
                text = tasks_md.read_text(encoding="utf-8", errors="replace")
                tasks = kc.parse_tasks(text)
            except ValueError as exc:
                notes.append(f"kits in flight for {label}/{kit_dir.name}: "
                             f"{type(exc).__name__}")
                continue
            except OSError as exc:
                notes.append(f"kits in flight for {label}/{kit_dir.name}: could not be read "
                             f"({type(exc).__name__})")
                continue
            counts = {status: 0 for status in kc.STATUSES}
            for t in tasks:
                if t.get("status") in counts:
                    counts[t["status"]] += 1
            try:
                state = kc.graph_state(tasks, kc.validate_graph(tasks)).get("state")
            except Exception as exc:  # PLAN D10: never a crash for one kit's graph
                notes.append(f"kits in flight for {label}/{kit_dir.name}: graph state "
                             f"unavailable ({type(exc).__name__})")
                state = None
            rows.append([label, kit_dir.name]
                       + [{"fmt": "count", "value": counts[s]} for s in kc.STATUSES]
                       + [state])
    return {
        "source": source, "observed": "live, at build time", "notes": notes,
        "summary": f"{len(rows)} kit(s) across {len(kits_dirs)} kits dir(s)",
        "blocks": [{"type": "table",
                   "headers": ["checkout label", "kit"] + list(kc.STATUSES) + ["graph state"],
                   "rows": rows, "empty": "no kits found", "details": True}],
    }


####################################################################################################
# Telemetry snapshots and journal digests panels (T6): telemetry_snapshot.read_source_snapshots
# per mapped namespace's telemetry store, per source (PLAN D3 row 3, D7g) -- T6 retry, red-team
# A: this dashboard packages the per-source table itself from `read_source_snapshots` rather
# than calling `telemetry_snapshot.build_list_summary`, whose own unguarded `list(envelope.get(
# "labels") or [])` raises on a malformed (non-list) `labels` field and would take the whole
# store's summary down with it; journal digests through a version-gated thin adapter over
# <namespace>/journal/<day>/digest.json -- one of PLAN D2's three sanctioned thin adapters,
# because journal_collect.py exposes no reader for this shape (PLAN D3 row 4). Both panels read
# ONLY the MAPPED entries of read_namespaces (P1 fix round S6): an unmapped namespace's
# telemetry/journal store is counted, never opened, with a note saying config.json's checkouts
# list would map it. Every telemetry source dir and envelope file is pre-scanned, no-follow, for
# a link or an oversized file before any owner call (red-team B/C), and every source's/day's own
# part is built by its own contained call (red-team A) -- one excluded, malformed or oversized
# part never drops another.

TELEMETRY_PANEL = "telemetry"
JOURNAL_PANEL = "journal"

TELEMETRY_NEVER_CAPTURED = ("never captured — run `python3 bin/telemetry_snapshot.py` to "
                            "capture")
TELEMETRY_REFRESH_HINT = ("stale or empty? run `python3 bin/telemetry_snapshot.py` to capture "
                          "a fresh snapshot")

# PLAN D7(g): the fixed headline allowlist per registered telemetry source, read ONLY from a
# `status: "ok"` envelope's own dict `payload`. Each path is a tuple of dict keys; a field the
# payload does not carry renders the styled unknown (never guessed, never summed).
# `context_overview` ("each section's found") and `attempts` ("the coverage labels") are not
# fixed paths -- they are every key of a named sub-structure, so a field the owner adds later is
# never silently dropped; both are handled separately in `_headline_rows`.
HEADLINE_PATHS = {
    "cost_report": (("totals", "usd"), ("mode",), ("pricing_cached_date",)),
    "codex_usage": (("branch",), ("priced",)),
    "copilot_usage": (("totals", "usd"), ("totals", "aic")),
    "routing_history": (("dollars", "coverage"),),
}

# Which HEADLINE_PATHS entries are money/credits/date figures -- the only ones PLAN D7a's basis
# rule and the date formatter reach; everything else (a mode string, a branch label, a bool) is
# plain text, `esc`'d like any other owner-emitted word.
_HEADLINE_USD_PATHS = {("cost_report", ("totals", "usd")), ("copilot_usage", ("totals", "usd"))}
_HEADLINE_CREDITS_PATHS = {("copilot_usage", ("totals", "aic"))}
_HEADLINE_DATE_PATHS = {("cost_report", ("pricing_cached_date",))}


def _namespace_label(row):
    """A mapped `read_namespaces` row's checkout, with the `tasks/kits` root named like T4's own
    history-target label -- so a reader sees the same checkout wording across every panel."""
    checkout, kind = row.get("checkout"), row.get("kind")
    return f"{checkout} (tasks/kits)" if kind == "codex-kits" else str(checkout)


def _guarded_store_dir(data_home, ns_row, store_name):
    """`<data_home>/<namespace>/<store_name>` if it is a real, unlinked directory -> (path,
    None); a symlink there is never followed (T5 retry's own os.lstat convention: a link is
    noted, not followed) -> (None, note); anything else that is not a directory (never captured
    yet, or a plain file) -> (None, None), a fact rather than a degraded scan."""
    path = Path(data_home) / ns_row["namespace"] / store_name
    if path.is_symlink():
        return None, (f"{store_name} store for {ns_row.get('namespace')} is a symlink — not "
                      f"followed, not read")
    if not _is_real_dir(path):
        return None, None
    return path, None


def _unmapped_store_count(classes, store_name):
    """How many UNMAPPED namespaces (P1 fix round S6) show `store_name` in their own one shallow
    listing -> {"count", "qualifier"}, on the same completeness terms as the overall unmapped
    class count (`class_count`): unknown when the data-home listing failed outright; a lower
    bound when the listing was cut OR when at least one unmapped namespace's own listing itself
    failed (`stores` is None there -- it might hold this store and is not counted either way);
    exact only when every unmapped namespace was itself listed and the data-home listing saw all
    of them."""
    overall = class_count(classes, "unmapped")
    if overall.get("qualifier") == "unknown":
        return {"count": None, "qualifier": "unknown"}
    rows = classes.get("unmapped") or ()
    matched = len([row for row in rows if isinstance(row, dict) and row.get("stores")
                  and store_name in row["stores"]])
    unresolved = any(isinstance(row, dict) and row.get("stores") is None for row in rows)
    qualifier = ("lower_bound" if (overall.get("qualifier") == "lower_bound" or unresolved)
                else "exact")
    return _qualified(matched, qualifier)


def _unmapped_store_note(classes, store_name, label):
    """PLAN D4 / P1 fix round S6: the note counting unmapped namespaces whose listing shows this
    panel's store -- they are not read, and config.json's `checkouts` would map them."""
    entry = _unmapped_store_count(classes, store_name)
    count, qualifier = entry.get("count"), entry.get("qualifier")
    if qualifier == "exact" and count == 0:
        lead = f"No unmapped namespace shows a {label} store in its one shallow listing."
    elif qualifier == "exact":
        lead = f"{count} unmapped namespace(s) show a {label} store in their one shallow listing."
    elif qualifier == "lower_bound":
        lead = (f"At least {count} unmapped namespace(s) show a {label} store in their one "
               f"shallow listing.")
    else:
        lead = f"An unknown number of unmapped namespaces may show a {label} store."
    return (f"{lead} They are not read by this panel (PLAN D4); add the checkout's path to this "
           f"dashboard's config.json checkouts list to map it.")


def _dig(payload, path):
    """A nested dict lookup along `path` (a tuple of keys) -> the value, or None the moment a
    key is missing or an intermediate is not a dict -- never a KeyError/TypeError, and never a
    guess at what the owner would have said (PLAN D2, D7g)."""
    current = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _headline_cell(source, path, value):
    """One HEADLINE_PATHS field's value as a cell: a typed usd/credits/date cell for the three
    money-or-date fields the allowlist carries, plain text (or the styled unknown for `None`)
    for everything else."""
    key = (source, path)
    if key in _HEADLINE_USD_PATHS:
        return {"fmt": "usd", "value": value, "basis": f"{source} {'.'.join(path)}, as captured"}
    if key in _HEADLINE_CREDITS_PATHS:
        return {"fmt": "credits", "value": value}
    if key in _HEADLINE_DATE_PATHS:
        return {"fmt": "date", "value": value}
    return value


def _headline_rows(source, payload):
    """The HEADLINE allowlist rows for one `status: "ok"` envelope's dict payload (PLAN D7g) ->
    `[[field, value]]`. `context_overview` and `attempts` are every key of a named
    sub-structure -- dynamic, so a field the owner adds later is never silently dropped; every
    other registered source is the fixed dotted-path allowlist. A field or sub-structure missing
    from the payload renders the styled unknown, never guessed."""
    payload = payload if isinstance(payload, dict) else {}
    if source == "context_overview":
        sections = payload.get("sections")
        sections = sections if isinstance(sections, dict) else {}
        rows = []
        for name in sorted(sections):
            section = sections.get(name)
            found = section.get("found") if isinstance(section, dict) else None
            rows.append([f"{name}.found", _owner_value_cell(found)])
        return rows or [["sections", None]]
    if source == "attempts":
        coverage = payload.get("coverage")
        coverage = coverage if isinstance(coverage, dict) else {}
        rows = [[f"coverage.{field}", _owner_value_cell(coverage.get(field))]
               for field in coverage]
        return rows or [["coverage", None]]
    return [[".".join(path), _headline_cell(source, path, _dig(payload, path))]
           for path in HEADLINE_PATHS.get(source, ())]


def _envelope_list_field(envelope, field, source, label, notes):
    """One envelope's list-shaped field (`labels`, `notes`) -> a list, tolerant of a malformed
    (non-list/tuple) value: a note names the namespace, source and field instead of raising (T6
    retry, red-team A -- extends the attempts panel's `_kind_label`/`_safe_ts` malformed-field
    precedent to telemetry envelopes; a `TypeError` from `list(42 or ())` on an int `labels`
    field is exactly the shape that used to erase every OTHER healthy source in the section)."""
    value = envelope.get(field) if isinstance(envelope, dict) else None
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    notes.append(f"{label}: {source}: envelope {field!r} field is malformed (not a list) and "
                f"was not rendered")
    return []


def _telemetry_prescan(store_dir, caps, notes, label):
    """A no-follow shallow scan of one telemetry store's own layout, run BEFORE any owner call
    (T6 retry, red-team B/C) -> the source names that are safe to read: a real, unlinked
    directory whose own envelope files (`*.json`) are all real, unlinked files no larger than
    MAX_ENVELOPE_BYTES. `read_source_snapshots`/`build_list_summary` themselves follow a link
    and read a whole envelope file with no size check, so a linked source dir, or a source
    holding even one linked or oversized envelope file, is excluded HERE, before the owner ever
    opens it. The owner cannot be told to skip one file, so the WHOLE source is excluded: no
    row, no deep-dive, no sparkline point. Every exclusion is a note naming the source (and, for
    a file, the file and its size)."""
    try:
        entries = sorted(store_dir.iterdir(), key=lambda p: p.name)
    except OSError as exc:
        notes.append(f"{label}: telemetry store could not be listed ({type(exc).__name__})")
        return []
    limit = cap_value(caps, "MAX_ENVELOPE_BYTES")
    safe_sources = []
    for entry in entries:
        name = entry.name
        if entry.is_symlink():
            notes.append(f"{label}: telemetry source {name!r} is a symlinked directory — not "
                         f"followed; its envelopes are never rendered")
            continue
        if not _is_real_dir(entry):
            continue
        try:
            files = sorted(entry.glob("*.json"), key=lambda p: p.name)
        except OSError as exc:
            notes.append(f"{label}: telemetry source {name!r} could not be listed "
                         f"({type(exc).__name__})")
            continue
        excluded = False
        for f in files:
            if f.is_symlink():
                notes.append(f"{label}: telemetry source {name!r} holds a symlinked envelope "
                             f"file ({f.name}) — the whole source is not rendered")
                excluded = True
                break
            try:
                size = f.lstat().st_size
            except OSError as exc:
                notes.append(f"{label}: telemetry source {name!r}'s {f.name} could not be "
                             f"stat'd ({type(exc).__name__})")
                excluded = True
                break
            if size > limit:
                notes.append(cap_note(
                    caps, "MAX_ENVELOPE_BYTES",
                    f"{label}: telemetry source {name!r}'s envelope {f.name} is {size} bytes — "
                    f"the whole source is not rendered"))
                excluded = True
                break
        if not excluded:
            safe_sources.append(name)
    return safe_sources


def _telemetry_source_summary_row(source, registered, dated, notes, label):
    """One source's per-source-table row (TASKS.md item 1), packaged from ALREADY-READ,
    ALREADY-CAPPED `dated` envelopes -- never re-deriving `read_source_snapshots`'s own parsing.
    T6 retry: this dashboard computes the row itself rather than calling
    `telemetry_snapshot.build_list_summary`, whose own `list(latest_envelope.get("labels") or
    [])` raises on exactly the malformed (non-list) `labels` value red-team A found, taking the
    WHOLE store's summary down with it."""
    dates = [d for d, _e in dated]
    if dated:
        _d, latest_env = dated[-1]
        latest_status = latest_env.get("status")
        latest_labels = _envelope_list_field(latest_env, "labels", source, label, notes)
    else:
        latest_status, latest_labels = None, []
    return [
        source, _owner_value_cell(registered), {"fmt": "count", "value": len(dated)},
        {"fmt": "date", "value": dates[0] if dates else None},
        {"fmt": "date", "value": dates[-1] if dates else None},
        latest_status,
        " | ".join(str(item) for item in latest_labels) if latest_labels else "—",
    ]


def _telemetry_deep_dive_blocks(dated, source, notes, label):
    """One registered source's deep-dive blocks (TASKS.md item 1) from ALREADY-READ,
    ALREADY-CAPPED `dated` envelopes. A malformed `labels`/`notes` field on the latest envelope
    is a note, never a crash (T6 retry, red-team A)."""
    if not dated:
        return [{"type": "p", "text": f"{source}: no snapshots to show"}]
    _latest_date, latest = dated[-1]
    blocks = [{"type": "p", "parts": [
        f"{source} — capture_date: ", {"fmt": "date", "value": latest.get("capture_date")},
        "  period: ", _owner_value_cell(latest.get("period")),
        "  status: ", latest.get("status")]}]
    labels = _envelope_list_field(latest, "labels", source, label, notes)
    blocks.append({"type": "list", "items": labels, "empty": f"{source}: no labels recorded"})
    env_notes = _envelope_list_field(latest, "notes", source, label, notes)
    blocks.append({"type": "list", "items": env_notes,
                   "empty": f"{source}: no notes from this envelope"})
    if latest.get("status") == "ok" and isinstance(latest.get("payload"), dict):
        blocks.append({"type": "table", "headers": ["headline field", "value"],
                       "rows": _headline_rows(source, latest.get("payload")),
                       "caption": f"{source} headline (PLAN D7g)",
                       "empty": "the allowlist has no fields for this source"})
    else:
        blocks.append({"type": "p", "parts": [
            f"{source}: no headline fields this build — status ", latest.get("status"),
            " is not ok, or the payload is not a captured object"]})
    return blocks


def _telemetry_unregistered_blocks(dated, source, notes, label):
    """PLAN D7g: a payload of an unregistered source dir renders labels only. A malformed
    `labels` field is a note, never a crash (T6 retry, red-team A)."""
    if not dated:
        labels = []
    else:
        _d, latest = dated[-1]
        labels = _envelope_list_field(latest, "labels", source, label, notes)
    return [
        {"type": "p", "text": f"{source}: unregistered source directory — labels only:"},
        {"type": "list", "items": labels, "empty": "no labels recorded"},
    ]


def _cost_report_sparkline_block(dated, label, notes):
    """TASKS.md item 1's last sentence: one sparkline per namespace of `cost_report`
    `payload["totals"]["usd"]` across the KEPT envelopes, labelled with the latest envelope's
    own labels (never this engine's own word for the billing mode or an estimate). A malformed
    `labels` field is a note, never a crash (T6 retry, red-team A)."""
    if not dated:
        return None
    labels = _envelope_list_field(dated[-1][1], "labels", "cost_report", label, notes)
    basis = " | ".join(str(item) for item in labels) if labels else "no label from cost_report"
    points = []
    for date_str, envelope in dated:
        value = None
        if (isinstance(envelope, dict) and envelope.get("status") == "ok"
                and isinstance(envelope.get("payload"), dict)):
            value = _dig(envelope["payload"], ("totals", "usd"))
        points.append((date_str, value))
    return {"type": "svg_sparkline",
           "title": f"{label}: cost_report totals.usd across kept envelopes",
           "desc": "one point per kept cost_report envelope, oldest first; the owner's own "
                   "totals.usd, never recomputed", "points": points, "value_header": "usd",
           "value_cell": {"fmt": "usd", "basis": basis}}


def _telemetry_one_source(ts, store_dir, source, caps, notes, label):
    """One source's row + deep-dive/unregistered blocks + kept dated envelopes -> (row, blocks,
    dated), each PART contained on its own (T6 retry, red-team A: "as T4 did", the
    `_guarded_section` idiom applied per source and per part): the read itself, the summary row
    and the deep-dive block are each wrapped so a failure in one still leaves the OTHER parts of
    THIS source real, and never touches any OTHER source in the table."""
    try:
        dated, src_notes = ts.read_source_snapshots(store_dir, source)
        notes.extend(f"{label}: {source}: {note}" for note in src_notes)
        limit = cap_value(caps, "MAX_TELEMETRY_ENVELOPES_PER_SOURCE")
        if len(dated) > limit:
            notes.append(cap_note(
                caps, "MAX_TELEMETRY_ENVELOPES_PER_SOURCE",
                f"{label}: {source} holds more envelopes than were kept; only the latest "
                f"{limit} (by date) are kept for this build"))
            dated = dated[-limit:]
    except Exception as exc:  # PLAN D10: the read itself failing drops only this source
        notes.append(f"{label}: {source}: {type(exc).__name__}")
        return ([source, _owner_value_cell(source in ts.SOURCES), None, None, None, None,
                "not available this build — see the notes above"],
               [{"type": "p", "text": f"{source}: not available this build — see the notes "
                                      f"above"}], [])

    registered = source in ts.SOURCES
    if not registered:
        notes.append(f"{label}: unregistered source dir: {source}")

    try:
        row = _telemetry_source_summary_row(source, registered, dated, notes, label)
    except Exception as exc:  # noqa: BLE001 -- this source's row only, never another's
        notes.append(f"{label}: {source} row could not be built ({type(exc).__name__})")
        row = [source, _owner_value_cell(registered), {"fmt": "count", "value": len(dated)},
              None, None, None, "not available — see the notes above"]

    try:
        if registered:
            dive = _telemetry_deep_dive_blocks(dated, source, notes, label)
        else:
            dive = _telemetry_unregistered_blocks(dated, source, notes, label)
    except Exception as exc:  # noqa: BLE001 -- this source's deep-dive only
        notes.append(f"{label}: {source} section could not be built ({type(exc).__name__})")
        dive = [{"type": "p", "text": f"{source}: not available this build — see the notes "
                                      f"above"}]

    return row, dive, dated


def _telemetry_namespace_section(ctx, ts, ns_row, caps, notes):
    """TASKS.md item 1, one mapped namespace -> (blocks, latest_capture_date_or_None). Every
    source is pre-scanned for links and oversized files before any owner call (red-team B/C),
    and every surviving source's row and deep-dive are built by their own contained call
    (red-team A) -- one excluded or malformed source never drops another, or the table itself."""
    label = _namespace_label(ns_row)
    blocks = [{"type": "p", "text": f"Telemetry for {label}:"}]
    store_dir, link_note = _guarded_store_dir(ctx["data_home"], ns_row, "telemetry")
    if link_note:
        notes.append(link_note)
    if store_dir is None:
        blocks.append({"type": "p", "text": TELEMETRY_NEVER_CAPTURED})
        return blocks, None
    source_names = _telemetry_prescan(store_dir, caps, notes, label)
    if not source_names:
        blocks.append({"type": "p", "text": TELEMETRY_NEVER_CAPTURED})
        return blocks, None
    rows, dive_blocks, latest_dates, cost_report_dated = [], [], [], None
    for source in source_names:
        row, dive, dated = _telemetry_one_source(ts, store_dir, source, caps, notes, label)
        rows.append(row)
        dive_blocks.extend(dive)
        if source == "cost_report":
            cost_report_dated = dated
        if dated:
            _d, latest_env = dated[-1]
            capture_date = (latest_env.get("capture_date") if isinstance(latest_env, dict)
                           else None)
            if isinstance(capture_date, str):
                latest_dates.append(capture_date)
    blocks.append({"type": "table",
                  "headers": ["source", "registered", "count", "first", "last",
                              "latest status", "latest labels"],
                  "rows": rows, "caption": "sources in this telemetry store",
                  "empty": "no source subdirectories found"})
    blocks.extend(dive_blocks)
    try:
        spark = _cost_report_sparkline_block(cost_report_dated, label, notes)
    except Exception as exc:  # noqa: BLE001 -- the sparkline only, never the table/dive above
        notes.append(f"{label}: cost_report sparkline could not be built "
                     f"({type(exc).__name__})")
        spark = None
    if spark is not None:
        blocks.append(spark)
    return blocks, (max(latest_dates) if latest_dates else None)


def build_telemetry_panel(ctx):
    ts = _mod("telemetry_snapshot")
    source_text = ("bin/dashboard.py — telemetry_snapshot.read_source_snapshots per source, per "
                  "mapped namespace's telemetry store, pre-scanned no-follow for a link or an "
                  "oversized file (PLAN D3 row 3)")
    if ctx["data_home"] is None:
        # No refresh hint here: with no data home at all there is not yet anything -- not even a
        # store to check -- for `telemetry_snapshot.py` to refresh (PanelDictContractTests pins
        # every panel's refresh_hint to None under exactly this degenerate build).
        return {"source": source_text, "observed": None, "notes": [],
               "summary": "no data home was given",
               "blocks": [{"type": "p", "text": "No data home was given, so no telemetry store "
                                                "could be read."}]}
    ns_rows, cap_notes = read_namespaces(ctx)
    notes = list(cap_notes)
    mapped_rows = [row for row in ns_rows if row.get("mapped")]
    blocks = []
    latest_dates = []
    for ns_row in mapped_rows:
        label = _namespace_label(ns_row)
        try:
            ns_blocks, latest = _telemetry_namespace_section(ctx, ts, ns_row, ctx["caps"], notes)
        except Exception as exc:  # PLAN D10: one namespace's failure never blanks the panel
            notes.append(f"telemetry for {label}: {type(exc).__name__}")
            ns_blocks, latest = ([{"type": "p", "text": f"Telemetry for {label}: not available "
                                                        f"this build — see the notes above"}],
                                 None)
        blocks.extend(ns_blocks)
        if latest:
            latest_dates.append(latest)
    if not mapped_rows:
        blocks.append({"type": "p", "text": "No mapped namespace to read telemetry from."})
    notes.append(_unmapped_store_note(ctx["model"]["classes"], "telemetry", "telemetry"))
    notes = list(dict.fromkeys(notes))  # an exact-duplicate note carries no second fact; every
    # DISTINCT note is kept in full (PLAN D7e)
    return {
        "source": source_text,
        "observed": max(latest_dates) if latest_dates else None,
        "notes": notes,
        "summary": (f"telemetry read for {len(mapped_rows)} mapped namespace(s)" if mapped_rows
                   else "no mapped namespace to read telemetry from"),
        "blocks": blocks,
        "refresh_hint": TELEMETRY_REFRESH_HINT,
    }


# ----- Journal digests (T6 item 2): a thin, version-gated adapter -- one of PLAN D2's three
# sanctioned thin adapters, because journal_collect.py exposes no reader for this shape. Nothing
# but `totals` and `sources` is ever read from a digest: not `signals`, not `inbox` (PLAN D8).

JOURNAL_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

JOURNAL_USD_BASIS = "journal's own priced total: est., priced sources only"


def _journal_day_candidates(journal_dir, caps, notes, label):
    """Subdirectory names matching JOURNAL_DAY_RE, sorted descending (newest first), bounded by
    MAX_JOURNAL_DAYS. A symlinked day directory is never followed (T5 retry's own convention)
    and is noted by name; anything else that is not a directory is silently not a day."""
    try:
        entries = sorted(journal_dir.iterdir(), key=lambda p: p.name, reverse=True)
    except OSError as exc:
        notes.append(f"{label}: journal directory could not be listed ({type(exc).__name__})")
        return []
    days = []
    for entry in entries:
        if not JOURNAL_DAY_RE.match(entry.name):
            continue
        if entry.is_symlink():
            notes.append(f"{label}: {entry.name} is a symlinked day directory — not followed, "
                         f"not read")
            continue
        if _is_real_dir(entry):
            days.append(entry.name)
    limit = cap_value(caps, "MAX_JOURNAL_DAYS")
    if len(days) > limit:
        notes.append(cap_note(
            caps, "MAX_JOURNAL_DAYS",
            f"{label} holds more journal days than were read; only the latest {limit} (by day "
            f"name) are shown"))
        days = days[:limit]
    return days


def _read_journal_digest(sp, jc, journal_dir, day, caps, notes):
    """One day's `digest.json`, size-gated by `os.lstat` against MAX_DIGEST_BYTES BEFORE any
    read (T6 retry, red-team C: `journal_collect.py` itself reads a whole `digest.json`) and
    version-gated on `journal_collect.SCHEMA_VERSION` (read from the module, never hardcoded) ->
    the decoded dict, or None with a note naming why (PLAN D3's thin-adapter rule: load,
    version-check, select fields -- nothing else). `lstat` (never `stat`) so a symlinked leaf's
    own tiny size never lets an oversized LINKED file past this check -- it is `safe_paths`'s
    `O_NOFOLLOW` read below that actually refuses a linked leaf, unchanged from before this
    retry."""
    try:
        size = os.lstat(Path(journal_dir) / day / "digest.json").st_size
    except FileNotFoundError:
        notes.append(f"{day}: no digest.json found")
        return None
    except OSError as exc:
        notes.append(f"{day}: could not be stat'd ({type(exc).__name__})")
        return None
    limit = cap_value(caps, "MAX_DIGEST_BYTES")
    if size > limit:
        notes.append(cap_note(caps, "MAX_DIGEST_BYTES",
                              f"{day}'s digest.json is {size} bytes — skipped, never read"))
        return None
    try:
        raw = sp.confined_read_bytes(journal_dir, f"{day}/digest.json", what="journal digest",
                                     missing_ok=True)
    except (sp.SafePathError, OSError) as exc:
        notes.append(f"{day}: could not be read ({type(exc).__name__})")
        return None
    if raw is None:
        notes.append(f"{day}: no digest.json found")
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        notes.append(f"{day}: undecodable, not rendered")
        return None
    if not isinstance(data, dict):
        notes.append(f"{day}: undecodable, not rendered")
        return None
    if data.get("schema_version") != jc.SCHEMA_VERSION:
        notes.append(f"{day}: unknown digest version, not rendered")
        return None
    return data


def _journal_day_rows(rendered, notes, label):
    """One row per successfully-read day (TASKS.md item 2), each day contained on its own (T6
    retry, red-team A: "the journal per day... likewise, as T4 did") so a failure reading one
    day's fields never drops another day's row from the table."""
    rows = []
    for day, digest in rendered:
        try:
            totals = digest.get("totals")
            totals = totals if isinstance(totals, dict) else {}
            active = ", ".join(str(s) for s in _as_list(totals.get("sources_active"))) or "none"
            unpriced = (", ".join(str(s) for s in _as_list(totals.get("unpriced_sources")))
                       or "none")
            rows.append([day,
                        {"fmt": "usd", "value": totals.get("usd_priced"),
                         "basis": JOURNAL_USD_BASIS},
                        {"fmt": "count", "value": totals.get("sessions")}, active, unpriced])
        except Exception as exc:  # noqa: BLE001 -- this day's row only, never another day's
            notes.append(f"{label}: {day} row could not be built ({type(exc).__name__})")
            rows.append([day, None, None, "—", "—"])
    return rows


def _journal_sparkline(rendered, label):
    """TASKS.md item 2: a sparkline of `usd_priced` by day, with its table twin."""
    if not rendered:
        return None
    points = []
    for day, digest in reversed(rendered):  # oldest first, a left-to-right trend line
        totals = digest.get("totals")
        totals = totals if isinstance(totals, dict) else {}
        points.append((day, totals.get("usd_priced")))
    return {"type": "svg_sparkline", "title": f"{label}: journal usd_priced by day",
           "desc": "one point per rendered journal day, oldest first; the journal's own "
                   "usd_priced, never recomputed", "points": points, "value_header": "usd",
           "value_cell": {"fmt": "usd", "basis": JOURNAL_USD_BASIS}}


def _journal_latest_source_table(rendered, notes, label):
    """TASKS.md item 2: for the latest day, `available`/`priced`/`sessions`/`usd` per source,
    each source contained on its own (T6 retry, red-team A: "...and per source likewise") so
    one malformed source entry never drops another."""
    if not rendered:
        return {"type": "p", "text": "No successfully-read journal day to show a per-source "
                                     "table for."}
    latest_day, digest = rendered[0]
    sources = digest.get("sources")
    sources = sources if isinstance(sources, dict) else {}
    rows = []
    for name in sorted(sources):
        try:
            report = sources.get(name)
            report = report if isinstance(report, dict) else {}
            priced = report.get("priced")
            usd_cell = ({"fmt": "usd", "value": report.get("usd"), "basis": "est."} if priced
                       else "unpriced")
            rows.append([name, _owner_value_cell(report.get("available")),
                        _owner_value_cell(priced),
                        {"fmt": "count", "value": report.get("sessions")}, usd_cell])
        except Exception as exc:  # noqa: BLE001 -- this source's row only, never another's
            notes.append(f"{label}: {latest_day}: {name}: {type(exc).__name__}")
            rows.append([name, None, None, None, "not available — see the notes above"])
    return {"type": "table", "headers": ["source", "available", "priced", "sessions", "usd"],
           "rows": rows, "caption": f"per-source detail for the latest day ({latest_day})",
           "empty": "the latest digest carries no sources"}


def _journal_namespace_section(ctx, sp, jc, ns_row, caps, notes):
    """TASKS.md item 2, one mapped namespace -> (blocks, latest_rendered_day_or_None)."""
    label = _namespace_label(ns_row)
    blocks = [{"type": "p", "text": f"Journal digests for {label}:"}]
    journal_dir, link_note = _guarded_store_dir(ctx["data_home"], ns_row, "journal")
    if link_note:
        notes.append(link_note)
    if journal_dir is None:
        blocks.append({"type": "p", "text": "No journal store for this namespace."})
        return blocks, None
    days = _journal_day_candidates(journal_dir, caps, notes, label)
    rendered = []
    for day in days:
        try:
            digest = _read_journal_digest(sp, jc, journal_dir, day, caps, notes)
        except Exception as exc:  # noqa: BLE001 -- this day's read only, never another day's
            notes.append(f"{label}: {day}: {type(exc).__name__}")
            digest = None
        if digest is not None:
            rendered.append((day, digest))
    blocks.append({"type": "table",
                  "headers": ["day", "usd priced", "sessions", "sources active",
                              "unpriced sources"],
                  "rows": _journal_day_rows(rendered, notes, label), "details": True,
                  "caption": f"{label}: journal digests by day",
                  "empty": "no journal digest could be read for this namespace"})
    spark = _journal_sparkline(rendered, label)
    if spark is not None:
        blocks.append(spark)
    blocks.append(_journal_latest_source_table(rendered, notes, label))
    blocks.append({"type": "p", "text": "Nothing else from the digest is read this build: not "
                                        "inbox, not signals, not any narrative file."})
    return blocks, (rendered[0][0] if rendered else None)


def build_journal_panel(ctx):
    sp, jc = _mod("safe_paths"), _mod("journal_collect")
    source_text = ("bin/dashboard.py — a thin, version-gated adapter over "
                  "<namespace>/journal/<day>/digest.json, gated on journal_collect."
                  "SCHEMA_VERSION (PLAN D2, D3 row 4); journal_collect.py exposes no reader for "
                  "this shape")
    if ctx["data_home"] is None:
        return {"source": source_text, "observed": None, "notes": [],
               "summary": "no data home was given",
               "blocks": [{"type": "p", "text": "No data home was given, so no journal digest "
                                                "could be read."}]}
    ns_rows, cap_notes = read_namespaces(ctx)
    notes = list(cap_notes)
    mapped_rows = [row for row in ns_rows if row.get("mapped")]
    blocks = []
    latest_days = []
    for ns_row in mapped_rows:
        label = _namespace_label(ns_row)
        try:
            ns_blocks, latest = _journal_namespace_section(ctx, sp, jc, ns_row, ctx["caps"],
                                                            notes)
        except Exception as exc:  # PLAN D10: one namespace's failure never blanks the panel
            notes.append(f"journal for {label}: {type(exc).__name__}")
            ns_blocks, latest = ([{"type": "p", "text": f"Journal digests for {label}: not "
                                                        f"available this build — see the notes "
                                                        f"above"}], None)
        blocks.extend(ns_blocks)
        if latest:
            latest_days.append(latest)
    if not mapped_rows:
        blocks.append({"type": "p", "text": "No mapped namespace to read journal digests from."})
    notes.append(_unmapped_store_note(ctx["model"]["classes"], "journal", "journal"))
    notes = list(dict.fromkeys(notes))
    return {
        "source": source_text,
        "observed": max(latest_days) if latest_days else None,
        "notes": notes,
        "summary": (f"journal digests read for {len(mapped_rows)} mapped namespace(s)"
                   if mapped_rows else "no mapped namespace to read journal digests from"),
        "blocks": blocks,
    }


def _bounds_blocks(notes, report):
    """The bounds panel's body: every cap with hit / not hit, then every note of the build.
    Also how `render_build` rebuilds that body when a panel's rendering fails, so the failure
    note reaches this section too."""
    rows = [[row.get("name"), row.get("value"), "hit" if row.get("hit") else "not hit"]
            for row in report if isinstance(row, dict)]
    return [
        {"type": "p", "text": ("Every scan behind this page is bounded. A cap that was hit cut "
                               "something short and left a note below; “not hit” means nothing "
                               "was cut at that bound in this build.")},
        {"type": "table", "headers": ["cap", "value", "status"], "rows": rows},
        {"type": "p", "text": f"Notes from this build, every panel's included ({len(notes)}):"},
        {"type": "list", "items": list(notes), "empty": "notes: none"},
    ]


def build_bounds_panel(ctx):
    notes = _collect_notes(ctx["notes"], ctx["model"]["panels"])
    report = caps_report(ctx["caps"], notes)
    hit = [row["name"] for row in report if row["hit"]]
    return {
        "source": "bin/dashboard.py — this build's own bounds and notes",
        "observed": "this build",
        "notes": [],
        "summary": f"{len(hit)} of {len(report)} caps hit",
        "blocks": _bounds_blocks(notes, report),
    }


# The panel that lists every cap and every note; always last.
BOUNDS_PANEL = "bounds"

# The registry, consumed in order. The panel ids and their page order are PINNED for the whole
# kit (TASKS.md, T2 brief item 5): later tasks insert their builders between these two, under
# exactly those ids; `bounds` stays last because it reports every other panel's notes.
PANELS = [
    (NAMESPACES_PANEL, "Namespaces in the data home", build_namespaces_panel),
    (ATTEMPTS_PANEL, "Attempts", build_attempts_panel),
    (SCORECARD_PANEL, "Routing scorecard", build_scorecard_panel),
    (KITS_PANEL, "Kits in flight", build_kits_panel),
    (TELEMETRY_PANEL, "Telemetry snapshots", build_telemetry_panel),
    (JOURNAL_PANEL, "Journal digests", build_journal_panel),
    (BOUNDS_PANEL, "Bounds and notes", build_bounds_panel),
]


# ---------------------------------------------------------------------------------------------
# Rendering. Every plain string goes through `esc`; the model is scrubbed whole before any of it.

# Text that must never appear in the page even as inert text, because the page is checked for it
# mechanically (PLAN R5). Escaping leaves `=`, `(` and `@` alone, so data text gets these three
# neutralised with character references -- the browser shows the same characters.
_TRIPWIRES = re.compile(r"(?i)(?:src|href)=|url\(|@import")

# T5 retry R1: Unicode's own bidi-override and directional-formatting characters -- ALM
# (U+061C), LRM/RLM (U+200E/F), the LRE/RLE/PDF/LRO/RLO block (U+202A-U+202E) and the
# LRI/RLI/FSI/PDI block (U+2066-U+2069) -- can make a task title or a kit name DISPLAY
# differently from its actual bytes (PLAN D13's "unicode in a task title" attack; the
# 2026-09-25 red-team's confirmed break: a kit named with U+202E rendered a fabricated
# "<done>" in reverse-written text). Every other C0 (U+0000-U+001F) and C1 (U+0080-U+009F)
# control character is neutralised the same way, except tab and newline, which the page's own
# whitespace handling already carries safely. An ordinary right-to-left LETTER (Arabic,
# Hebrew, ...) or an emoji is untouched -- neither is in this set.
_BIDI_CONTROLS = ("؜‎‏" + "".join(chr(c) for c in range(0x202a, 0x202f))
                 + "".join(chr(c) for c in range(0x2066, 0x206a)))
_OTHER_CONTROLS = ("".join(chr(c) for c in range(0x00, 0x20) if c not in (0x09, 0x0a))
                  + "".join(chr(c) for c in range(0x80, 0xa0)))
NEUTRALISED_CONTROLS = _BIDI_CONTROLS + _OTHER_CONTROLS
_CONTROL_CHARS_RE = re.compile("[" + re.escape(NEUTRALISED_CONTROLS) + "]")


def _neutralize(match):
    text = match.group(0)
    if text.endswith("="):
        return text[:-1] + "&#61;"
    if text.endswith("("):
        return text[:-1] + "&#40;"
    return "&#64;" + text[1:]


def _neutralize_control(match):
    """One bidi-override or other control character -> a visible marker naming its code point
    (R1) -- `⟨U+202E⟩`, never the raw character itself."""
    return f"⟨U+{ord(match.group(0)):04X}⟩"


def esc(value):
    """One value as page text -- the ONE escaping path every renderer in this module uses, so
    honesty rendering is written once (PLAN D7). Every bidi-override or other control
    character is replaced by a visible code-point marker before anything else runs (R1: a raw
    directional override must never reach the page, escaped or not -- escaping alone leaves it
    live). HTML-escaped and tripwire-neutralised; `None` is never a blank cell or a silent zero
    (PLAN R3) -- it is the literal word `unknown`, in a span the stylesheet renders italic and
    muted but never hidden."""
    if value is None:
        return '<span class="unknown">unknown</span>'
    text = _clean(str(value))
    text = _CONTROL_CHARS_RE.sub(_neutralize_control, text)
    return _TRIPWIRES.sub(_neutralize, html.escape(text, quote=True))


# ---------------------------------------------------------------------------------------------
# Formatters (PLAN D7a-d). Each wraps `esc` with one field's semantics; `None` is always
# `unknown` and nothing here ever coerces an absent value into `0` or a blank cell.

def _finite_float(v):
    """`v` as a finite float, or `None` when it is not a number at all OR is NaN/±Infinity --
    a corrupted ledger value (a JSON `NaN`/`Infinity`, or a string such as "nan", "Infinity" or
    an overflowing "1e400", all of which `float()` accepts without raising) is treated exactly
    like an unparsable one: every numeric formatter below falls back to the value's own escaped
    text rather than crashing the panel or printing a unit on something that is not a real
    number (PLAN R3). An int too large for a float (`float()` raises OverflowError on one) is
    not a finite float either."""
    try:
        number = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _float_text(number):
    """A finite float as its own shortest decimal text (`repr`, which round-trips), a trailing
    `.0` dropped so an integral value reads as the integer it is: 2.0 -> `2`, 0.9 -> `0.9`, and
    1e+23 stays `1e+23` rather than growing digits the value never had. Negative zero is `0`."""
    if number == 0:
        return "0"
    text = repr(number)
    return text[:-2] if text.endswith(".0") else text


def fmt_count(v, qualifier="exact"):
    """A count -> text that never truncates (PLAN R3). `None` -> `unknown`; a bool -> `True` /
    `False`; an int -> its digits; a finite float -> its own shortest decimal text (`2.0` ->
    `2`, `0.9` -> `0.9`, never rounded to an int). A non-finite float, a string or anything else
    is not `unknown` (it IS present) and renders as its own escaped text -- a string is never
    reinterpreted as a number.

    `qualifier` (a typed count cell's optional `qualifier` key) says what the count claims:
    `exact` (the default) as above; `lower_bound` -> `at least N` for an int N > 0 (a lower
    bound of 0 says nothing, so it is `unknown`); `unknown`, or anything unrecognised ->
    `unknown` whatever the value, because a count must never claim more than it knows."""
    if qualifier == "lower_bound":
        if isinstance(v, int) and not isinstance(v, bool) and v > 0:
            return esc(f"at least {v}")
        return esc(None)
    if qualifier != "exact" or v is None:
        return esc(None)
    if isinstance(v, bool):
        return esc("True" if v else "False")
    if isinstance(v, int):
        return esc(v)
    if isinstance(v, float) and math.isfinite(v):
        return esc(_float_text(v))
    return esc(v)


# What stands in for the basis when a caller gave none: the amount then gets no `$` at all.
BASIS_MISSING = "basis missing"


def _usd_amount(number):
    """A finite dollar amount as text, without the `$` -> two decimals with thousands separators;
    zero is `0.00`. A known non-zero amount that two decimals would round to `0.00` shows its
    own shortest digits instead (0.004 -> `0.004`, -0.004 -> `-0.004`, 1e-05 -> `1e-05`), so a
    real sub-cent figure never reads as zero, in either direction (PLAN R3)."""
    if number == 0:
        return "0.00"
    text = f"{number:,.2f}"
    if text.lstrip("-") == "0.00":
        return repr(number)
    return text


def fmt_usd(v, basis_label):
    """`$` and the amount, plus the basis label in a `<span class="label">` -- a dollar never
    appears without the basis it was measured under (PLAN D7a/b: no cell ever sums two bases,
    and a basis-less dollar is never printed). Two decimals, except that a known non-zero
    sub-cent amount shows its own digits rather than `0.00` (`_usd_amount`). `None` ->
    `unknown` alone, no `$` and no label. A non-finite or unparsable value gets no `$` either --
    only its own escaped text, basis label still beside it.

    `basis_label` has no default, so a DIRECT call that forgets it raises `TypeError`. That
    guard does not reach a typed `usd` cell, whose missing `basis` arrives here as `None`, so
    the rendering itself carries the rule: a `None` or blank basis prints the amount WITHOUT
    `$`, followed by the label `basis missing`."""
    if v is None:
        return esc(None)
    number = _finite_float(v)
    amount = esc(v) if number is None else esc(_usd_amount(number))
    if basis_label is None or (isinstance(basis_label, str) and not basis_label.strip()):
        return f'{amount} <span class="label">{esc(BASIS_MISSING)}</span>'
    if number is not None:
        amount = f"${amount}"
    return f'{amount} <span class="label">{esc(basis_label)}</span>'


def fmt_credits(v):
    """A credits amount -> two decimals, or `unknown` for `None`. No basis label: unlike a
    dollar figure, a credits count is already one unit with nothing to conflate it with. A
    non-finite or unparsable value renders as its own escaped text, no unit."""
    if v is None:
        return esc(None)
    number = _finite_float(v)
    return esc(v) if number is None else esc(f"{number:,.2f}")


def fmt_seconds(v):
    """A duration in seconds -> `<n>s`, or `unknown` for `None`. A non-finite or unparsable
    value renders as its own escaped text, with no `s` suffix implying a real duration."""
    if v is None:
        return esc(None)
    number = _finite_float(v)
    if number is None:
        return esc(v)
    text = str(int(number)) if number == int(number) else f"{number:.1f}"
    return esc(f"{text}s")


def fmt_date(v):
    """A date or timestamp exactly as the owner recorded it -> text, or `unknown` for `None`.
    Never reformatted: a date string is the owner's own words, and this engine re-derives
    nothing an owner already said (PLAN D2)."""
    return esc(v)


def _parse_date_like(value):
    """A `YYYY-MM-DD` date or an ISO timestamp -> a `date`, or `None` when it is neither."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def age_days(observed, today):
    """Whole days from `observed` to `today` (each a `YYYY-MM-DD` date or an ISO timestamp) ->
    an int, or `None` when either is missing or does not parse. The one date arithmetic this
    engine does (PLAN D2, D7d): the age of an observation relative to the build."""
    start = _parse_date_like(observed)
    end = _parse_date_like(today)
    if start is None or end is None:
        return None
    return (end - start).days


STYLESHEET = """
:root {
  --bg: #ffffff;
  --fg: #1f2328;
  --muted: #59636e;
  --accent: #0969da;
  --line: #d1d9e0;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0d1117;
    --fg: #e6edf3;
    --muted: #9198a1;
    --accent: #4493f8;
    --line: #3d444d;
  }
}
body {
  background: var(--bg);
  color: var(--fg);
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  line-height: 1.45;
  margin: 0;
}
.wrap { max-width: 72rem; margin: 0 auto; padding: 0 16px; }
.table-wrap { overflow-x: auto; }
table { border-collapse: collapse; margin: 8px 0; }
th, td {
  border-bottom: 1px solid var(--line);
  padding: 4px 8px;
  text-align: left;
  vertical-align: top;
}
p, li { overflow-wrap: anywhere; }
a { color: var(--accent); }
nav { padding: 8px 0; border-bottom: 1px solid var(--line); }
section { padding: 8px 0 16px; border-bottom: 1px solid var(--line); }
.meta, .notes { color: var(--muted); }
.label { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color: var(--muted); }
.unknown { font-style: italic; color: var(--muted); }
figure { margin: 16px 0; }
figcaption { color: var(--muted); margin-top: 4px; }
details { margin: 8px 0; }
details > summary { cursor: pointer; }
svg { width: 100%; height: auto; }
.chart-bar { fill: var(--accent); }
.chart-line { fill: none; stroke: var(--accent); stroke-width: 2; }
.chart-label { fill: var(--fg); font-size: 10px; }
"""


# A table cell is either a plain value (through `esc`, so a builder can never smuggle raw HTML
# through a string) or a typed cell -- a dict carrying `fmt` -- dispatched to the matching
# formatter below. `esc`/`fmt_usd`/`fmt_credits`/`fmt_count`/`fmt_seconds`/`fmt_date` already
# return finished, escaped HTML (a styled unknown span, a dollar's basis-label span); running
# THAT through `esc` again would show the span as literal tag soup instead of markup, which is
# exactly the T3 red-team break this vocabulary exists to close. `CELL_FORMATS` is the toolkit
# contract T4-T7 build their `rows` on: a cost/credits/count/seconds/date cell is always this
# shape, never a pre-rendered string. A `count` cell may carry an optional `qualifier`
# (`exact` | `lower_bound` | `unknown`, see `fmt_count`) -- the shape of a class count.
CELL_FORMATS = {
    "usd": lambda cell: fmt_usd(cell.get("value"), cell.get("basis")),
    "credits": lambda cell: fmt_credits(cell.get("value")),
    "count": lambda cell: fmt_count(cell.get("value"), cell.get("qualifier") or "exact"),
    "seconds": lambda cell: fmt_seconds(cell.get("value")),
    "date": lambda cell: fmt_date(cell.get("value")),
}


def _render_cell(cell):
    """One table cell -> HTML, escaped exactly once. A typed cell's formatter output is already
    escaped HTML and is used as-is; anything else -- including a plain string -- goes through
    `esc`, so a builder cannot pass a pre-rendered `fmt_*` string as a cell (that would be
    escaped a second time) and cannot smuggle raw HTML through a plain string either. The same
    dispatch renders each item of a `p` block's `parts`."""
    if isinstance(cell, dict) and "fmt" in cell:
        fmt = cell.get("fmt")
        renderer = CELL_FORMATS.get(fmt) if isinstance(fmt, str) else None
        if renderer is not None:
            return renderer(cell)
        return esc(f"cell: unrecognised fmt {fmt!r}")
    return esc(cell)


def _as_row(row):
    """A table row -> its cells. A row that is not a list or tuple (None, a number, a string, a
    mapping) is ONE cell showing its own text, never an exception and never split into
    characters."""
    return list(row) if isinstance(row, (list, tuple)) else [row]


def html_table(headers, rows, caption=None, details=False):
    """`headers`/`rows` (every cell through `_render_cell`: `esc` for a plain value, or the
    matching formatter for a typed cell -- see `CELL_FORMATS`) -> one `<table>` in a `<div
    class="table-wrap">`, so a wide table scrolls sideways and the PAGE never scrolls
    horizontally at phone width (PLAN D9). `details=True` wraps it again in `<details><summary>
    caption (N rows)</summary>...</details>` for a table too long to want open by default; the
    caption then lives only in the summary, not duplicated as a `<caption>` too. Malformed
    headers or rows render as their own text (`_as_list`, `_as_row`) rather than raising."""
    headers = _as_list(headers)
    rows = [_as_row(row) for row in _as_list(rows)]
    parts = ['<div class="table-wrap">', "<table>"]
    if caption and not details:
        parts.append(f"<caption>{esc(caption)}</caption>")
    parts.append("<thead><tr>" + "".join(f"<th>{esc(cell)}</th>" for cell in headers)
                 + "</tr></thead>")
    parts.append("<tbody>")
    for row in rows:
        parts.append("<tr>" + "".join(f"<td>{_render_cell(cell)}</td>" for cell in row)
                     + "</tr>")
    parts.append("</tbody>")
    parts.append("</table>")
    parts.append("</div>")
    table_html = "\n".join(parts)
    if details:
        summary = f"{caption or 'table'} ({_plural(len(rows), 'row', 'rows')})"
        return f"<details>\n<summary>{esc(summary)}</summary>\n{table_html}\n</details>"
    return table_html


# ---------------------------------------------------------------------------------------------
# Charts (PLAN D9): an inline <svg> that is NEVER the only carrier of a value -- its
# <figcaption> is an html_table of the exact same rows, in the same <figure>. Geometry lives in
# an arbitrary internal coordinate system; the stylesheet's `svg { width: 100%; height: auto; }`
# scales it to the column width, which is what keeps a chart phone-width.

CHART_WIDTH = 400        # arbitrary viewBox units, wide enough for a label column plus bars
BAR_ROW_HEIGHT = 18      # one bar's height
BAR_ROW_GAP = 6          # gap above each bar, and below the last one
BAR_LABEL_WIDTH = 130    # viewBox units reserved for the row label, left of the bars
SPARK_HEIGHT = 60        # a sparkline is short and wide, not a full chart
SPARK_PAD = 6            # inset so the line never touches the viewBox edge

# Reset at the top of every `render_page` call so chart ids are assigned in document order from
# zero every time -- otherwise two renders of the same model would not be byte-identical (D9).
_chart_sequence = {"n": 0}


def _reset_chart_sequence():
    _chart_sequence["n"] = 0


def _chart_ids():
    """A fresh pair of element ids for one chart's <title>/<desc> -> (title_id, desc_id),
    unique within one page render. A direct call (a test, or the Verify probe) just keeps
    counting, which does not affect that one figure's own structure."""
    _chart_sequence["n"] += 1
    n = _chart_sequence["n"]
    return f"chart-{n}-title", f"chart-{n}-desc"


def _chart_value(value):
    """A value the chart geometry may draw -> a finite float, or None to draw nothing. Only a
    real number (never a bool, never a numeric string) that is finite (`_finite_float`): NaN
    and ±Infinity draw nothing and break nothing else, and still read as their own text in the
    table twin (PLAN R3)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return _finite_float(value)


def _field(row, key):
    """`row[key]` for a mapping row, else None -- and None for a key a mapping cannot hold (an
    unhashable key from a malformed block) rather than an exception."""
    if not isinstance(row, dict):
        return None
    try:
        return row.get(key)
    except TypeError:
        return None


def _as_pair(point):
    """A sparkline point -> (label, value). Anything but a two-item list or tuple is its own
    label with an unknown value: shown as text in the twin, drawn as nothing."""
    if isinstance(point, (list, tuple)) and len(point) == 2:
        return point[0], point[1]
    return point, None


def _twin_value(value, value_cell):
    """One value for a chart's table twin: plain, or -- with a typed-cell template such as
    `{"fmt": "usd", "basis": "est."}` -- that template carrying the value, so the twin renders
    it once through `_render_cell` (a dollar twin keeps its basis beside every figure)."""
    return dict(value_cell, value=value) if isinstance(value_cell, dict) else value


def svg_bars(rows, title, desc, label_key, value_key, value_header=None, value_cell=None):
    """A horizontal bar per row of `rows[i][value_key]`, labelled `rows[i][label_key]` -> one
    `<figure>` holding an inline `<svg viewBox=… role="img" aria-labelledby=…>` (title, desc,
    then the bars) and, as its `<figcaption>`, an `html_table` of the same rows -- the chart is
    never the only place a number lives. Only a finite number draws a bar (`_chart_value`); a
    `None` reads `unknown` in the twin and a NaN or infinity reads as its own text there.

    The twin's value column is headed `value_header` (default: `value_key`, as before this
    parameter existed) and, given `value_cell`, each of its cells is that typed-cell template
    carrying the row's value (`_twin_value`). A row that is not a mapping is its own label
    with an unknown value."""
    rows = _as_list(rows)
    title_id, desc_id = _chart_ids()
    labels = [_field(row, label_key) if isinstance(row, dict) else row for row in rows]
    values = [_field(row, value_key) for row in rows]
    drawn = [_chart_value(value) for value in values]
    finite = [value for value in drawn if value is not None]
    max_value = max(finite) if finite else 0
    plot_width = max(CHART_WIDTH - BAR_LABEL_WIDTH - 8, 1)
    height = max(len(rows), 1) * (BAR_ROW_HEIGHT + BAR_ROW_GAP) + BAR_ROW_GAP
    parts = [
        f'<svg viewBox="0 0 {CHART_WIDTH} {height}" role="img" '
        f'aria-labelledby="{title_id} {desc_id}">',
        f'<title id="{title_id}">{esc(title)}</title>',
        f'<desc id="{desc_id}">{esc(desc)}</desc>',
    ]
    for index, label in enumerate(labels):
        value = drawn[index]
        y = BAR_ROW_GAP + index * (BAR_ROW_HEIGHT + BAR_ROW_GAP)
        parts.append(f'<text x="0" y="{y + BAR_ROW_HEIGHT - 5}" class="chart-label">'
                     f'{esc(label)}</text>')
        if value is not None and max_value > 0:
            width = max(round((value / max_value) * plot_width, 1), 0)
            parts.append(f'<rect x="{BAR_LABEL_WIDTH}" y="{y}" width="{width}" '
                         f'height="{BAR_ROW_HEIGHT}" class="chart-bar"></rect>')
    parts.append("</svg>")
    svg = "\n".join(parts)
    header = value_key if value_header is None else value_header
    table_rows = [[label, _twin_value(values[index], value_cell)]
                  for index, label in enumerate(labels)]
    table = html_table([label_key, header], table_rows, caption=title)
    return f"<figure>\n{svg}\n<figcaption>\n{table}\n</figcaption>\n</figure>"


def svg_sparkline(points, title, desc, value_header="value", value_cell=None):
    """A line through `points` (`(label, value)` pairs, oldest first) -> one `<figure>` holding
    an inline `<svg>` (title, desc, then a polyline through the known values) and, as its
    `<figcaption>`, an `html_table` of the same points. Only a finite number is a point
    (`_chart_value`): a `None`, NaN or infinity breaks the line rather than being interpolated
    across, and reads as `unknown` or its own text in the twin. The twin's value column is
    headed `value_header` and, given `value_cell`, each value is that typed-cell template
    carrying it (`_twin_value`) -- how a dollar sparkline keeps its basis on every row."""
    points = [_as_pair(point) for point in _as_list(points)]
    title_id, desc_id = _chart_ids()
    drawn = [_chart_value(value) for _label, value in points]
    finite = [value for value in drawn if value is not None]
    lo = min(finite) if finite else 0.0
    hi = max(finite) if finite else 0.0
    span = (hi - lo) or 1.0
    steps = max(len(points) - 1, 1)
    plot_w = CHART_WIDTH - 2 * SPARK_PAD
    plot_h = SPARK_HEIGHT - 2 * SPARK_PAD
    parts = [
        f'<svg viewBox="0 0 {CHART_WIDTH} {SPARK_HEIGHT}" role="img" '
        f'aria-labelledby="{title_id} {desc_id}">',
        f'<title id="{title_id}">{esc(title)}</title>',
        f'<desc id="{desc_id}">{esc(desc)}</desc>',
    ]
    segment = []
    for index, value in enumerate(drawn):
        x = y = None
        if value is not None:
            x = SPARK_PAD + (plot_w * index / steps)
            y = SPARK_PAD + plot_h - ((value - lo) / span) * plot_h
        if x is not None and math.isfinite(x) and math.isfinite(y):
            segment.append(f"{x:.1f},{y:.1f}")
            continue
        if len(segment) > 1:  # an extreme span can overflow; that point breaks the line too
            parts.append(f'<polyline points="{" ".join(segment)}" class="chart-line">'
                         f'</polyline>')
        segment = []
    if len(segment) > 1:
        parts.append(f'<polyline points="{" ".join(segment)}" class="chart-line"></polyline>')
    parts.append("</svg>")
    svg = "\n".join(parts)
    header = "value" if value_header is None else value_header
    table = html_table(["label", header],
                       [[label, _twin_value(value, value_cell)] for label, value in points],
                       caption=title)
    return f"<figure>\n{svg}\n<figcaption>\n{table}\n</figcaption>\n</figure>"


def _render_block(block):
    """One block dict -> HTML. The vocabulary is `p` / `list` / `table` (T2) plus, from T3,
    `svg_bars` / `svg_sparkline`. A `p` block carries either `text` (one plain value) or
    `parts` (a list of plain values and typed cells, each rendered once through `_render_cell`
    -- how a sentence holds a qualified count or the styled `unknown`). The chart blocks pass
    their optional `value_header` / `value_cell` through. An unrecognised type or shape renders
    a plain sentence, and a malformed list field renders as its own text, rather than raising,
    so one bad block cannot take its whole panel down with it."""
    if not isinstance(block, dict):
        return f"<p>{esc('a block that is not a mapping was not rendered')}</p>"
    kind = block.get("type")
    if kind == "p":
        if "parts" in block:
            return "<p>" + "".join(_render_cell(part)
                                   for part in _as_list(block.get("parts"))) + "</p>"
        return f"<p>{esc(block.get('text'))}</p>"
    if kind == "list":
        items = _as_list(block.get("items") or None)
        if not items:
            return f'<p class="notes">{esc(block.get("empty") or "none")}</p>'
        return ('<ul class="notes">\n' + "\n".join(f"<li>{esc(item)}</li>" for item in items)
                + "\n</ul>")
    if kind == "table":
        rows = _as_list(block.get("rows") or None)
        if not rows and block.get("empty"):
            return f"<p>{esc(block['empty'])}</p>"
        return html_table(block.get("headers") or [], rows, block.get("caption"),
                          details=bool(block.get("details")))
    if kind == "svg_bars":
        rows = _as_list(block.get("rows") or None)
        if not rows and block.get("empty"):
            return f"<p>{esc(block['empty'])}</p>"
        return svg_bars(rows, block.get("title") or "", block.get("desc") or "",
                        block.get("label_key"), block.get("value_key"),
                        value_header=block.get("value_header"),
                        value_cell=block.get("value_cell"))
    if kind == "svg_sparkline":
        points = _as_list(block.get("points") or None)
        if not points and block.get("empty"):
            return f"<p>{esc(block['empty'])}</p>"
        return svg_sparkline(points, block.get("title") or "", block.get("desc") or "",
                             value_header=block.get("value_header"),
                             value_cell=block.get("value_cell"))
    return f"<p>{esc(f'a block of unknown type {kind!r} was not rendered')}</p>"


def panel(pid, title, source, observed, age, notes, body_html, refresh_hint=None):
    """The `<section id=…>` chrome every panel shares (PLAN D7d): an `<h2>`, a meta line
    naming the source, the observed date (or "never captured"), and the age in days (or
    "n/a" when `observed` is not a parseable date -- see `age_days`), an optional refresh
    hint, then the notes -- rendered even when there are none, as "notes: none", so a reader
    can always tell nothing-to-report from not-rendered -- then the body. `None`, an empty
    string or a whitespace-only string all mean the same absence (PLAN D7d/GUARDRAILS: a
    blank line is never how absence renders) and all print "never captured"."""
    observed_absent = observed is None or (isinstance(observed, str) and not observed.strip())
    observed_text = "never captured" if observed_absent else observed
    age_text = _plural(age, "day", "days") if isinstance(age, int) else "n/a"
    meta = f"source: {esc(source)} · observed: {esc(observed_text)} · age: {esc(age_text)}"
    parts = [
        f'<section id="{esc(pid)}">',
        f"<h2>{esc(title or pid)}</h2>",
        f'<p class="meta">{meta}</p>',
    ]
    if refresh_hint:
        parts.append(f'<p class="meta">{esc(refresh_hint)}</p>')
    notes = list(notes or ())
    if notes:
        parts.append('<ul class="notes">\n' + "\n".join(f"<li>{esc(note)}</li>" for note in notes)
                     + "\n</ul>")
    else:
        parts.append(f'<p class="notes">{esc("notes: none")}</p>')
    if body_html:
        parts.append(body_html)
    parts.append("</section>")
    return "\n".join(parts)


def nav(panels):
    """`<nav>` anchors for every registered panel, in order -- the page's only `href`s."""
    links = [f'<a href="#{esc(p.get("id"))}">{esc(p.get("title") or p.get("id"))}</a>'
             for p in panels]
    return '<nav aria-label="panels">' + " · ".join(links) + "</nav>"


# What a panel whose rendering raised leaves behind -- on its fallback section, in the bounds
# section and in build.json -- naming the exception TYPE only: a message can carry a path.
RENDER_FAILURE_NOTE = "this panel could not be rendered ({})"
RENDER_FAILURE_SUMMARY = "could not be rendered (see notes)"


def _render_panel(entry, built_at):
    """One scrubbed panel entry -> its `<section>`. May raise on a malformed entry; the caller
    contains that per panel."""
    body_html = "\n".join(_render_block(block) for block in _as_list(entry.get("blocks")))
    observed = entry.get("observed")
    return panel(entry.get("id"), entry.get("title") or entry.get("id"), entry.get("source"),
                 observed, age_days(observed, built_at), _as_list(entry.get("notes") or None),
                 body_html, entry.get("refresh_hint"))


def _fallback_ident(raw, home):
    """A failed panel's id and title, scrubbed like everything else -> (id, title)."""
    try:
        return _scrub_tree(raw.get("id"), home), _scrub_tree(raw.get("title"), home)
    except Exception:  # the entry is too broken even to scrub its name; say nothing of it
        return None, None


def _fallback_section(pid, title, note):
    """The section a panel whose rendering raised gets instead: its id, its escaped title and
    the one note -- nothing of the panel's own content."""
    return "\n".join([
        f'<section id="{esc("" if pid is None else pid)}">',
        f"<h2>{esc(title or pid)}</h2>",
        f'<p class="notes">{esc(note)}</p>',
        "</section>",
    ])


def _render_view(model, home):
    """One rendering pass -> (page, failed): `failed` lists (index, exception type name) for
    every panel whose rendering raised, the index counting only the mapping entries of
    `model["panels"]`. Each panel is scrubbed and rendered inside its own `try`, so one
    malformed panel becomes a fallback section and never takes the page down (PLAN D10)."""
    _reset_chart_sequence()
    view = _scrub_tree({key: value for key, value in model.items() if key != "panels"}, home)
    entries = [entry for entry in _as_list(model.get("panels")) if isinstance(entry, dict)]
    built_at = view.get("built_at")
    built_text = f"built {built_at or 'unknown'} — a static file: rebuild to refresh"
    primary_text = f"primary checkout: {view.get('primary_checkout') or 'unknown'}"
    data_home_text = f"data home: {view.get('data_home') or 'unknown'}"
    sections, links, failed = [], [], []
    for index, raw in enumerate(entries):
        try:
            entry = _scrub_tree(raw, home)
            sections.append(_render_panel(entry, built_at))
            links.append({"id": entry.get("id"), "title": entry.get("title")})
        except Exception as exc:
            pid, title = _fallback_ident(raw, home)
            sections.append(_fallback_section(
                pid, title, RENDER_FAILURE_NOTE.format(type(exc).__name__)))
            links.append({"id": pid, "title": title})
            failed.append((index, type(exc).__name__))
    lines = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        f'<meta http-equiv="Content-Security-Policy" content="{CSP}">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{esc(PAGE_TITLE)}</title>",
        "<style>",
        STYLESHEET.strip("\n"),
        "</style>",
        "</head>",
        "<body>",
        '<div class="wrap">',
        "<header>",
        f"<h1>{esc(PAGE_TITLE)}</h1>",
        f'<p class="meta" data-built-at="{esc(built_at)}">{esc(built_text)}</p>',
        f'<p class="meta">{esc(primary_text)} · {esc(data_home_text)}</p>',
        "</header>",
        nav(links),
        "<main>",
        *sections,
        "</main>",
        "</div>",
        "</body>",
        "</html>",
        "",
    ]
    return "\n".join(lines), failed


def _with_render_failures(model, failed):
    """A copy of `model` that carries one note per panel whose rendering raised: on the
    page-wide `notes` (which build.json shows), in the bounds panel's rebuilt body, and as that
    panel's `summary`. Idempotent: a note already present is not added twice."""
    model = dict(model)
    panels = [dict(entry) if isinstance(entry, dict) else entry
              for entry in _as_list(model.get("panels"))]
    shown = [entry for entry in panels if isinstance(entry, dict)]
    notes = [str(note) for note in _as_list(model.get("notes"))]
    broken = set()
    for index, type_name in failed:
        entry = shown[index]
        broken.add(index)
        entry["summary"] = RENDER_FAILURE_SUMMARY
        note = f"{entry.get('id')}: {RENDER_FAILURE_NOTE.format(type_name)}"
        if note not in notes:
            notes.append(note)
    for index, entry in enumerate(shown):
        if entry.get("id") == BOUNDS_PANEL and index not in broken:
            entry["blocks"] = _bounds_blocks(notes, _as_list(model.get("caps")))
    model["notes"] = notes
    model["panels"] = panels
    return model


def render_build(model, home):
    """The page for `model` with every rendering failure contained -> (page, model).

    A panel whose rendering raises becomes a fallback section (`_fallback_section`). Its note
    -- the exception type only -- then goes on the page-wide notes, into the bounds section and,
    through the returned model, into build.json: the model is re-derived by
    `_with_render_failures` and rendered once more. The input model is never mutated; with no
    failure it is returned as it came. Both passes are deterministic, so the same model renders
    the same bytes except the build-time line (PLAN D9)."""
    page, failed = _render_view(model, home)
    if not failed:
        return page, model
    model = _with_render_failures(model, failed)
    page, _again = _render_view(model, home)
    return page, model


def render_page(model, home):
    """The whole page as one string (`render_build` without the model). Deterministic for the
    same model except the one line that carries `data-built-at` (chart ids are reset on every
    pass for the same reason: PLAN D9); a panel whose rendering raises is contained."""
    return render_build(model, home)[0]


# ---------------------------------------------------------------------------------------------
# Receipt and summary.

def build_receipt(model, home, out_dir):
    """build.json: what was built, from where, what was cut and every note -> scrubbed dict.

    `classes` is pinned (the skill relays it): `listing` (one of LISTING_STATES), then
    `mapped` / `unmapped` / `residue`, each `{"count": int|null, "qualifier":
    "exact"|"lower_bound"|"unknown"}` -- `count` is null exactly when the qualifier is `unknown`
    -- and residue also carries its `sample`."""
    classes = model.get("classes") or {}
    residue = classes.get("residue") or {}
    caps = model.get("caps") or []
    listing = classes.get("listing")
    receipt = {
        "schema_version": model.get("schema_version"),
        "built_at": model.get("built_at"),
        "page": os.path.join(os.fspath(out_dir), PAGE_NAME),
        "receipt": os.path.join(os.fspath(out_dir), RECEIPT_NAME),
        "primary_checkout": model.get("primary_checkout"),
        "checkouts": list(model.get("checkouts") or ()),
        "data_home": model.get("data_home"),
        "classes": {
            "listing": listing if listing in LISTING_STATES else "failed",
            "mapped": class_count(classes, "mapped"),
            "unmapped": class_count(classes, "unmapped"),
            "residue": {**class_count(classes, "residue"),
                        "sample": list(residue.get("sample") or ())},
        },
        "panels": [{key: entry.get(key) for key in ("id", "title", "source", "observed", "summary")}
                   for entry in model.get("panels") or ()],
        "caps": caps,
        "caps_hit": [row.get("name") for row in caps if row.get("hit")],
        "notes": list(model.get("notes") or ()),
    }
    return _scrub_tree(receipt, home)


def summary_lines(receipt):
    """The one-screen summary `build` prints. Namespace counts follow the page's rules: an
    exact count is `N`, a lower bound `at least N`, anything else `unknown`, and an absent data
    home is the word `absent` -- never a line of zeros."""
    classes = receipt.get("classes") or {}
    listing = classes.get("listing")
    if listing == "absent":
        namespaces = "namespaces: data home absent — no namespaces"
    elif listing == "complete" and all(_is_exact_zero(classes.get(name))
                                       for name in CLASS_NAMES):
        namespaces = "namespaces: data home empty — no namespaces"
    else:
        namespaces = ("namespaces: "
                      + " · ".join(_count_text(classes.get(name), name) for name in CLASS_NAMES)
                      + " (heuristic: counted, never opened)")
        if listing != "complete":
            namespaces += f"; data-home listing {listing or 'unknown'}"
    lines = [
        f"page:       {receipt.get('page')}",
        f"receipt:    {receipt.get('receipt')}",
        f"built at:   {receipt.get('built_at')}",
        namespaces,
        "panels:",
    ]
    for entry in receipt.get("panels") or ():
        lines.append(f"  {str(entry.get('id')):<11} {entry.get('summary') or ''}")
    hit = receipt.get("caps_hit") or []
    lines.append(f"caps hit:   {', '.join(hit) if hit else 'none'}")
    lines.append(f"notes:      {len(receipt.get('notes') or ())} (in the page's bounds section and "
                 f"in {RECEIPT_NAME})")
    return lines


# ---------------------------------------------------------------------------------------------
# Writer and config (PLAN D6).

def default_out_dir(primary_checkout):
    """The dashboard store of the primary checkout. Called at run time, never at import."""
    return _mod("runtime_data").store_path(STORE_NAME, primary_checkout)


def _refuse_irregular_leaf(out_dir, name, what):
    """Refuse a leaf that exists but is not a regular file.

    `safe_paths.confined_replace` never writes THROUGH a link -- its rename replaces the link
    itself -- but replacing a link, directory or special file the user put there is not this
    engine's call either, so it refuses before writing anything.
    """
    sp = _mod("safe_paths")
    if sp.leaf_is_regular(out_dir, name):
        return
    if os.path.lexists(os.path.join(os.fspath(out_dir), name)):
        raise sp.SafePathError(
            f"{what}: {name!r} in the output directory is not a regular file (a link, a "
            f"directory or a special file); refusing to replace it — remove it and rebuild"
        )


def write_page(out_dir, html, receipt):
    """Write the page and its receipt into `out_dir`, 0700/0600 -> {"page", "receipt"} paths.

    Raises `safe_paths.SafePathError` or `OSError` when the directory cannot be written; the
    CLI turns either into exit 2. Both leaves are checked before either is written, and an
    empty `out_dir` is refused outright: it would mean the working directory.
    """
    rd, sp = _mod("runtime_data"), _mod("safe_paths")
    if _blank(out_dir):
        raise sp.SafePathError("dashboard page: the output directory is empty, and an empty path "
                               "would mean the working directory; refusing")
    out_dir = Path(out_dir)
    rd.ensure_private(out_dir)
    _refuse_irregular_leaf(out_dir, PAGE_NAME, "dashboard page")
    _refuse_irregular_leaf(out_dir, RECEIPT_NAME, "dashboard receipt")
    sp.confined_replace(out_dir, PAGE_NAME, html.encode("utf-8"), what="dashboard page",
                        mode=0o600)
    data = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    sp.confined_replace(out_dir, RECEIPT_NAME, data.encode("utf-8"), what="dashboard receipt",
                        mode=0o600)
    return {"page": out_dir / PAGE_NAME, "receipt": out_dir / RECEIPT_NAME}


def read_config(out_dir):
    """`config.json`'s extra checkouts -> (checkouts, notes). Absent is empty, not a note.

    The file must be a JSON object whose `checkouts` is a list of strings. A malformed file is
    one note and adds nothing; an entry that is not a string, contains `..`, is not absolute,
    or is not a directory is one note and is skipped.
    """
    sp = _mod("safe_paths")
    checkouts, notes = [], []
    if _blank(out_dir):
        notes.append(f"no output directory was given — {CONFIG_NAME} was not read")
        return checkouts, notes
    out_dir = Path(out_dir)
    if not out_dir.is_dir():
        return checkouts, notes
    try:
        raw = sp.confined_read_bytes(out_dir, CONFIG_NAME, what="dashboard config",
                                     missing_ok=True)
    except (sp.SafePathError, OSError) as exc:
        notes.append(f"{CONFIG_NAME} in {out_dir} could not be read ({type(exc).__name__}) — "
                     f"ignored")
        return checkouts, notes
    if raw is None:
        return checkouts, notes
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError:
        notes.append(f"{CONFIG_NAME} in {out_dir} is not UTF-8 JSON — ignored")
        return checkouts, notes
    if not isinstance(data, dict):
        notes.append(f"{CONFIG_NAME} in {out_dir} is not a JSON object — ignored")
        return checkouts, notes
    entries = data.get("checkouts")
    if not isinstance(entries, list):
        notes.append(f"{CONFIG_NAME} in {out_dir} has no `checkouts` list — nothing added")
        return checkouts, notes
    for entry in entries:
        if not isinstance(entry, str):
            notes.append(f"{CONFIG_NAME}: a checkouts entry of type {type(entry).__name__} is not "
                         f"a string — skipped")
            continue
        shown = entry if len(entry) <= 200 else entry[:200] + "…"
        if ".." in Path(entry).parts:
            notes.append(f"{CONFIG_NAME}: checkout {shown} contains '..' — skipped")
        elif not os.path.isabs(entry):
            notes.append(f"{CONFIG_NAME}: checkout {shown} is not an absolute path — skipped")
        elif not os.path.isdir(entry):
            notes.append(f"{CONFIG_NAME}: checkout {shown} is not a directory — skipped")
        else:
            checkouts.append(entry)
    return checkouts, notes


# ---------------------------------------------------------------------------------------------
# The one build path `build` and `demo` share.

def _cached_runner(runner):
    """`runner` answering a repeated (argv, cwd) from memory, so one verb runs once per build."""
    cache = {}

    def run(argv, cwd, **kwargs):
        key = (tuple(argv), os.fspath(cwd))
        if key not in cache:
            cache[key] = runner(argv, cwd=cwd, **kwargs)
        return cache[key]

    return run


def _scorecard_projects_dir():
    """The routing scorecard's own transcripts default -> (path or None, notes)."""
    try:
        return str(_mod("routing_scorecard").sc.DEFAULT_PROJECTS_DIR), []
    except Exception as exc:
        return None, [f"the routing scorecard's default projects dir could not be resolved "
                      f"({type(exc).__name__})"]


def assemble_build(cwd, data_home=None, out_dir=None, flags=(), git=True, projects_dir=None,
                   no_transcripts=False, home=None, runner=None):
    """Everything a build decides before writing -> (out_dir, model, receipt, page). Never
    raises for a degraded input: every one of those is a note in the model. An EMPTY path
    argument is not degraded input but a mistake that would silently mean the working
    directory, so it raises `safe_paths.SafePathError` before anything is read."""
    for name, value in (("out_dir", out_dir), ("data_home", data_home),
                        ("projects_dir", projects_dir)):
        if _blank(value):
            raise _mod("safe_paths").SafePathError(
                f"dashboard: {name} is empty, and an empty path would mean the working "
                f"directory; refusing")
    if git and runner is None:
        runner = _cached_runner(_mod("proc_runner").run)
    if out_dir is None:
        primary, _ = _primary_checkout(cwd, git, runner)
        out_dir = default_out_dir(primary)
    out_dir = Path(out_dir)
    config, config_notes = read_config(out_dir)
    checkouts, notes = discover_checkouts(cwd, flags=flags, config=config, git=git, runner=runner)
    notes.extend(config_notes)
    if data_home is None:
        data_home = _mod("runtime_data").user_data_home()
    if projects_dir is None:
        projects_dir, projects_notes = _scorecard_projects_dir()
        notes.extend(projects_notes)
    opts = {"notes": notes,
            "projects_dir": None if projects_dir is None else os.fspath(projects_dir),
            "no_transcripts": bool(no_transcripts), "git": bool(git)}
    model = build_model(data_home, checkouts, opts, default_caps())
    # The page first: a panel whose rendering fails adds a note to the model, and the receipt
    # built after it carries that note too.
    page, model = render_build(model, home)
    receipt = build_receipt(model, home, out_dir)
    return out_dir, model, receipt, page


# ---------------------------------------------------------------------------------------------
# The one fixture builder, shared by `demo` and the tests.

def synthetic_world(root, residue=30):
    """A synthetic data home and checkout under `root` -> dict of paths.

    `root/checkout` holds `.claude/kits/demo-kit/{TASKS,NOTES}.md`,
    `.claude/kits/notes-kit/{TASKS,NOTES}.md` (a second, ledger-less kit -- T4 item 5) and an
    empty `tasks/kits/`; `root/data-home` holds the checkout's mapped namespace with a ledger (a
    finished, verified, projected attempt; a second finished attempt carrying an `estimated`
    cost; and one started attempt that never finished), a telemetry store (two dated envelopes
    per `telemetry_snapshot.SOURCES` entry, a rogue `cost_report/notes.json` file and an
    unregistered `mystery/2026-01-01.json` source -- T6 item 3) and a journal store (two
    schema-1 digest days, one schema-99 day, and a canary string
    `CANARY-INBOX-TEXT-DO-NOT-RENDER` planted in one digest's never-read `inbox` -- T6 item 3);
    `residue` residue namespaces each holding only `attempts/kit/events.jsonl` with one event,
    and one unmapped namespace with a ledger carrying one corrupt line. Every value is
    synthetic; nothing outside `root` is touched, and nothing here is oversized -- an over-size
    ledger is a T4-test-only fixture, not a `demo`/`synthetic_world` one (TASKS.md item 5).
    """
    rd, al, sp = _mod("runtime_data"), _mod("attempt_ledger"), _mod("safe_paths")
    ts, jc = _mod("telemetry_snapshot"), _mod("journal_collect")
    root = Path(root)
    data_home = root / "data-home"
    checkout = root / "checkout"
    kits_dir = checkout / ".claude" / "kits"
    kit_dir = kits_dir / DEMO_KIT
    notes_kit_dir = kits_dir / NOTES_KIT
    scorecard_kit_dir = kits_dir / SCORECARD_KIT
    codex_kits_dir = checkout / "tasks" / "kits"
    codex_demo_dir = codex_kits_dir / CODEX_DEMO_KIT
    for directory in (data_home, kit_dir, notes_kit_dir, scorecard_kit_dir, codex_kits_dir,
                      codex_demo_dir):
        rd.ensure_private(directory)
    sp.confined_write_bytes(kit_dir, "TASKS.md", DEMO_TASKS_MD, what="synthetic kit")
    sp.confined_write_bytes(kit_dir, "NOTES.md", DEMO_NOTES_MD, what="synthetic kit")
    sp.confined_write_bytes(notes_kit_dir, "TASKS.md", NOTES_KIT_TASKS_MD, what="synthetic kit")
    sp.confined_write_bytes(notes_kit_dir, "NOTES.md", NOTES_KIT_NOTES_MD, what="synthetic kit")
    # T5 item 5: a third `.claude/kits` kit (tiers table data) and a `tasks/kits/codex-demo`
    # kit (the `-codex` scorecard label).
    sp.confined_write_bytes(scorecard_kit_dir, "TASKS.md", SCORECARD_TASKS_MD,
                            what="synthetic kit")
    sp.confined_write_bytes(scorecard_kit_dir, "NOTES.md", SCORECARD_NOTES_MD,
                            what="synthetic kit")
    sp.confined_write_bytes(codex_demo_dir, "TASKS.md", CODEX_DEMO_TASKS_MD,
                            what="synthetic kit")
    sp.confined_write_bytes(codex_demo_dir, "NOTES.md", CODEX_DEMO_NOTES_MD,
                            what="synthetic kit")

    namespace = rd.project_namespace(checkout)
    ledger = al.AttemptLedger(data_home / namespace / al.STORE, DEMO_KIT)
    first = ledger.record_started(DEMO_RUN, "T1", "initial", SYNTHETIC_MODEL,
                                  prompt="synthetic prompt", verify_cmd="synthetic verify")
    ledger.record_finished(DEMO_RUN, "T1", first, "ok", 0, "synthetic report", duration_s=1.0)
    ledger.record_verify(DEMO_RUN, "T1", first, 0, "Ran 1 test in 0.01s\n\nOK\n")
    ledger.record_projected(DEMO_RUN, "T1", "done", result="pass", outcome_line=True)
    ledger.record_started(DEMO_RUN, "T2", "initial", SYNTHETIC_MODEL,
                          prompt="synthetic prompt", verify_cmd="synthetic verify")
    # T4 item 5: a record whose finished event carries a cost (`attempt_history.ledger_records`
    # derives basis `estimated` for any `cost_source` other than `parsed`, per the P1 fix round's
    # S5 reading) -- T1 above stays the record with no cost at all.
    third = ledger.record_started(DEMO_RUN, "T3", "initial", SYNTHETIC_MODEL,
                                  prompt="synthetic prompt", verify_cmd="synthetic verify")
    ledger.record_finished(DEMO_RUN, "T3", third, "ok", 0, "synthetic report", duration_s=2.0,
                           cost_usd=0.05, cost_source="estimated")

    residue_names = []
    for index in range(residue):
        digest = hashlib.sha256(f"synthetic-residue-{index}".encode("utf-8")).hexdigest()
        name = f"tmp{digest[:8]}-{digest[8:16]}"
        al.AttemptLedger(data_home / name / al.STORE, "kit").record_started(
            "synthetic-residue", "T1", "initial", SYNTHETIC_MODEL)
        residue_names.append(name)

    other = al.AttemptLedger(data_home / UNMAPPED_NAMESPACE / al.STORE, "other-kit")
    started = other.record_started(DEMO_RUN, "T1", "initial", SYNTHETIC_MODEL)
    other.record_finished(DEMO_RUN, "T1", started, "ok", 0, "synthetic report")
    # T4 item 5: one corrupt line in an unmapped namespace's ledger, appended beside the ledger's
    # own valid writes through the same confined-append path `AttemptLedger.append` uses.
    sp.confined_append_bytes(other.root, f"{other.namespace}/{al.EVENTS_FILE}",
                             b"not-json-at-all\n", what="synthetic corrupt ledger line")

    # T6 item 3: telemetry -- two dated envelopes per registered source, obviously-fake headline
    # numbers (PLAN D7g), a rogue file inside a registered source's own dir, and an unregistered
    # source dir. Only `cost_report`'s LATEST envelope omits `mode` on purpose, so a headline
    # field genuinely absent from a real payload has a fixture to prove it renders `unknown`.
    telemetry_dir = data_home / namespace / "telemetry"
    rd.ensure_private(telemetry_dir)
    telemetry_days = ("2026-01-01", "2026-01-02")
    telemetry_payloads = {
        "cost_report": (
            ({"totals": {"usd": 12.34}, "mode": "synthetic-mode",
              "pricing_cached_date": "2026-01-01"}, ["synthetic cost_report day 1"]),
            ({"totals": {"usd": 15.0}, "pricing_cached_date": "2026-01-02"},  # "mode" omitted
             ["synthetic cost_report day 2", "billing-mode: synthetic-flat"]),
        ),
        "codex_usage": (
            ({"branch": "priced", "priced": True}, ["synthetic codex_usage day 1"]),
            ({"branch": "priced", "priced": True}, ["synthetic codex_usage day 2"]),
        ),
        "copilot_usage": (
            ({"totals": {"usd": 3.0, "aic": 30.0}}, ["synthetic copilot_usage day 1"]),
            ({"totals": {"usd": 4.5, "aic": 45.0}}, ["synthetic copilot_usage day 2"]),
        ),
        "context_overview": (
            ({"sections": {"claude": {"found": True}, "codex": {"found": False},
                          "copilot": {"found": True}}},
             ["claude section: no sessions in window"]),
            ({"sections": {"claude": {"found": True}, "codex": {"found": True},
                          "copilot": {"found": True}}}, ["synthetic context_overview day 2"]),
        ),
        "routing_history": (
            ({"dollars": {"coverage": "partial"}},
             ["dollars coverage: partial (1/2 kits)"]),
            ({"dollars": {"coverage": "full"}}, ["dollars coverage: full (2/2 kits)"]),
        ),
        "attempts": (
            ({"coverage": {"kits": 3, "kits_with_ledger": 2, "kits_with_notes": 1,
                          "kits_with_role_use": 0}},
             ["2 of 3 kit(s) carry an attempt ledger"]),
            ({"coverage": {"kits": 3, "kits_with_ledger": 3, "kits_with_notes": 1,
                          "kits_with_role_use": 1}},
             ["3 of 3 kit(s) carry an attempt ledger"]),
        ),
    }
    for source in ts.SOURCES:
        for date_str, (payload, labels) in zip(telemetry_days, telemetry_payloads[source]):
            envelope = ts.build_envelope(source, date_str, {"days": 30}, "ok", labels, [],
                                         payload)
            sp.confined_write_bytes(telemetry_dir, f"{source}/{date_str}.json",
                                    json.dumps(envelope), what="synthetic telemetry envelope")
    sp.confined_write_bytes(telemetry_dir, "cost_report/notes.json", "not an envelope\n",
                            what="synthetic rogue telemetry file")
    mystery_envelope = ts.build_envelope("mystery", "2026-01-01", {"days": 1}, "ok",
                                         ["mystery label"], [], {"note": "unregistered source"})
    sp.confined_write_bytes(telemetry_dir, "mystery/2026-01-01.json",
                            json.dumps(mystery_envelope),
                            what="synthetic unregistered telemetry source")

    # T6 item 3: journal -- two schema-1 digest days (the first carrying the canary string in
    # its `signals.inbox.items`, which this kit's panel never reads) and one schema-99 day.
    journal_dir = data_home / namespace / "journal"
    rd.ensure_private(journal_dir)

    def _synthetic_digest(date_str, usd_priced, sessions, canary=False):
        items = ["a synthetic inbox line"]
        if canary:
            items.append("CANARY-INBOX-TEXT-DO-NOT-RENDER")
        return {
            "schema_version": jc.SCHEMA_VERSION,
            "date": date_str,
            "generated_at": f"{date_str}T00:00:00+00:00",
            "day_start": f"{date_str}T00:00:00+00:00",
            "day_end": f"{date_str}T23:59:59+00:00",
            "timezone": "UTC",
            "sources": {
                "cost_report": {"available": True, "priced": True, "sessions": sessions,
                                "usd": usd_priced, "extra": {}},
                "codex_usage": {"available": True, "priced": False, "sessions": 0, "usd": None,
                                "extra": {}},
            },
            "totals": {
                "usd_priced": usd_priced,
                "sessions": sessions,
                "sources_active": ["cost_report"],
                "unpriced_sources": ["codex_usage"],
            },
            "signals": {
                "kit_tasks": [],
                "inbox": {"present": True, "path": "synthetic", "items": items,
                          "truncated": False, "redactions": {}, "redaction_note": ""},
                "wip": [],
            },
        }

    journal_days = ("2026-01-01", "2026-01-02", "2026-01-03")
    sp.confined_write_bytes(
        journal_dir, f"{journal_days[0]}/digest.json",
        json.dumps(_synthetic_digest(journal_days[0], 1.23, 2, canary=True)),
        what="synthetic journal digest")
    sp.confined_write_bytes(
        journal_dir, f"{journal_days[1]}/digest.json",
        json.dumps(_synthetic_digest(journal_days[1], 2.5, 4)),
        what="synthetic journal digest")
    sp.confined_write_bytes(
        journal_dir, f"{journal_days[2]}/digest.json",
        # Obviously-fake, distinctive numbers (never plausible elsewhere on the page) so a test
        # can prove none of them rendered anywhere -- this whole digest must be unreadable.
        json.dumps({"schema_version": 99, "date": journal_days[2],
                   "totals": {"usd_priced": 54321.99, "sessions": 54321, "sources_active": [],
                              "unpriced_sources": []}}),
        what="synthetic journal digest")

    return {
        "root": root,
        "data_home": data_home,
        "checkout": checkout,
        "kits_dir": kits_dir,
        "kit_dir": kit_dir,
        "notes_kit_dir": notes_kit_dir,
        "scorecard_kit_dir": scorecard_kit_dir,
        "codex_kits_dir": codex_kits_dir,
        "codex_demo_dir": codex_demo_dir,
        "namespace": namespace,
        "ledger": ledger.events_path,
        "residue": residue_names,
        "unmapped": UNMAPPED_NAMESPACE,
        "telemetry_dir": telemetry_dir,
        "telemetry_days": telemetry_days,
        "journal_dir": journal_dir,
        "journal_days": journal_days,
    }


# ---------------------------------------------------------------------------------------------
# CLI.

# Every `build` flag that takes a path. An empty or blank value is refused with exit 2, never
# collapsed to `.`: a page written into the working directory sits one `git add -A` from
# history (PLAN D8). A new path-taking flag joins this tuple in the same change.
BUILD_PATH_FLAGS = ("--data-home", "--out-dir", "--checkout", "--projects-dir")


def _blank_path_flag(args):
    """The first path flag given an empty or blank value -> its name, or None."""
    for flag in BUILD_PATH_FLAGS:
        value = getattr(args, flag[2:].replace("-", "_"), None)
        for item in value if isinstance(value, list) else [value]:
            if _blank(item):
                return flag
    return None


def _parser():
    parser = argparse.ArgumentParser(
        prog="dashboard.py",
        description=("Build one offline HTML page over this machine's polytropos stores. Reads "
                     "only; writes only its own dashboard store (or --out-dir)."),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    build = sub.add_parser("build", help="build index.html and build.json")
    build.add_argument("--data-home", default=None,
                       help="data home to scan (default: runtime_data.user_data_home(), which "
                            "honours POLYTROPOS_DATA_HOME)")
    build.add_argument("--out-dir", default=None,
                       help="write the page and receipt here (default: the primary checkout's "
                            "dashboard store)")
    build.add_argument("--checkout", action="append", default=[], metavar="PATH",
                       help="another checkout to map namespaces for (repeatable)")
    build.add_argument("--projects-dir", default=None,
                       help="Claude transcripts dir for the scorecard's dollars (default: the "
                            "scorecard's own default)")
    build.add_argument("--no-transcripts", action="store_true",
                       help="price no transcripts: the scorecard reads an empty directory")
    build.add_argument("--no-git", action="store_true",
                       help="run no git verb: the primary checkout is the working directory")
    build.add_argument("--json", action="store_true", help="print the receipt as JSON")
    where = sub.add_parser("where", help="print where the page would be written, and why")
    where.add_argument("--no-git", action="store_true",
                       help="run no git verb: the primary checkout is the working directory")
    where.add_argument("--json", action="store_true", help="print the answer as JSON")
    sub.add_parser("demo", help="build from synthetic data in a temp dir; reads and writes "
                                "nothing real, spawns nothing")
    return parser


def _working_directory():
    try:
        return os.getcwd(), None
    except OSError as exc:
        return None, f"dashboard: the working directory cannot be read ({type(exc).__name__})"


def _cmd_build(args, home):
    flag = _blank_path_flag(args)
    if flag:
        print(f"dashboard: {flag} needs a path, not an empty value — an empty path would mean "
              f"the working directory; nothing was read or written", file=sys.stderr)
        return 2
    sp = _mod("safe_paths")
    cwd, error = _working_directory()
    if error:
        print(error, file=sys.stderr)
        return 2
    out_dir, _model, receipt, page = assemble_build(
        cwd, data_home=args.data_home, out_dir=args.out_dir, flags=args.checkout,
        git=not args.no_git, projects_dir=args.projects_dir,
        no_transcripts=args.no_transcripts, home=home)
    try:
        write_page(out_dir, page, receipt)
    except (sp.SafePathError, OSError) as exc:
        # States the out dir and the error, and does not claim which directory caused it:
        # `safe_paths.confined_replace` reserves its temp name in the WORKING directory.
        print(f"dashboard: the page was not written (out dir: {scrub(os.fspath(out_dir), home)}): "
              f"{scrub(str(exc), home)}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print("\n".join(summary_lines(receipt)))
    return 0


def _cmd_where(args, home):
    cwd, error = _working_directory()
    if error:
        print(error, file=sys.stderr)
        return 2
    git = not args.no_git
    runner = _mod("proc_runner").run if git else None
    primary, notes = _primary_checkout(cwd, git, runner)
    row = _mod("runtime_data").resolve_store(STORE_NAME, primary)
    info = _scrub_tree({"store": STORE_NAME, "path": row.get("path"), "origin": row.get("origin"),
                        "note": row.get("note") or "", "primary_checkout": primary,
                        "notes": notes}, home)
    if args.json:
        print(json.dumps(info, indent=2, sort_keys=True))
        return 0
    print(f"{info['store']:11s} {str(info['origin']):16s} {info['path']}")
    if info["note"]:
        print(f"{'':11s} {'':16s} — {info['note']}")
    print(f"primary checkout: {info['primary_checkout']}")
    for note in info["notes"]:
        print(f"note: {note}")
    return 0


def _cmd_demo(home):
    sp = _mod("safe_paths")
    with tempfile.TemporaryDirectory(prefix="polytropos-dashboard-demo-") as tmp:
        root = Path(tmp)
        world = synthetic_world(root)
        projects = root / "projects"
        _mod("runtime_data").ensure_private(projects)
        out_dir, _model, receipt, page = assemble_build(
            world["checkout"], data_home=world["data_home"], out_dir=root / "out", flags=(),
            git=False, projects_dir=projects, no_transcripts=False, home=home)
        try:
            write_page(out_dir, page, receipt)
        except (sp.SafePathError, OSError) as exc:
            print(f"dashboard demo: the page was not written (out dir: "
                  f"{scrub(os.fspath(out_dir), home)}): {scrub(str(exc), home)}", file=sys.stderr)
            return 2
        print("dashboard demo — synthetic data in a temporary directory; nothing real is read or "
              "written, and nothing is spawned")
        print("\n".join(summary_lines(receipt)))
        print(f"page (removed when the demo exits): {scrub(os.fspath(out_dir / PAGE_NAME), home)}")
    return 0


def main(argv=None):
    args = _parser().parse_args(argv)
    home = os.path.expanduser("~")
    if args.cmd == "where":
        return _cmd_where(args, home)
    if args.cmd == "demo":
        return _cmd_demo(home)
    return _cmd_build(args, home)


if __name__ == "__main__":
    raise SystemExit(main())
