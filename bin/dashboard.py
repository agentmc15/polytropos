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
    "MAX_EVAL_RUNS_RENDERED",
    "MAX_JOURNAL_DAYS",
    "MAX_TELEMETRY_ENVELOPES_PER_SOURCE",
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
        "MAX_EVAL_RUNS_RENDERED": MAX_EVAL_RUNS_RENDERED,
        "MAX_JOURNAL_DAYS": MAX_JOURNAL_DAYS,
        "MAX_TELEMETRY_ENVELOPES_PER_SOURCE": MAX_TELEMETRY_ENVELOPES_PER_SOURCE,
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

def namespace_roots(checkout):
    """The roots a checkout's engines namespace the data home by -> [(root, kind)].

    The checkout itself, and `tasks/kits`, because `attempt_ledger.kit_repo_root` maps a
    `tasks/kits/<slug>` kit (the Codex planning kits) to `tasks/kits` -- which is why a real
    data home holds a `kits-<digest>` namespace beside the checkout's own.
    """
    base = Path(checkout)
    return [(base, "checkout"), (base / "tasks" / "kits", "codex-kits")]


def _empty_classes():
    return {"mapped": [], "unmapped": [], "residue": {"count": 0, "sample": []}}


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

    One bounded `os.scandir` of the data home; an entry that is not a directory without
    following links is skipped with a note. A namespace named by hashing a checkout root is
    `mapped`; otherwise one `os.listdir` decides residue (RESIDUE_NAMESPACE_RE and nothing but
    an `attempts` store) -- a residue namespace is counted and never opened again -- and
    anything else is `unmapped`. Degraded paths are notes: an absent data home, one that is a
    file, one that cannot be listed.
    """
    rd = _mod("runtime_data")
    classes = _empty_classes()
    notes = []
    expected = {}
    for checkout in checkouts or ():
        for root, kind in namespace_roots(checkout):
            expected.setdefault(rd.project_namespace(root), (os.fspath(checkout), kind))
    notes.extend(_legacy_notes(checkouts))

    home_text = os.fspath(data_home)
    if not os.path.isdir(home_text):
        state = "is not a directory" if os.path.lexists(home_text) else "does not exist"
        notes.append(f"data home {home_text} {state} — no namespaces were classified")
        return classes, notes

    limit = cap_value(caps, "MAX_NAMESPACES_LISTED")
    entries = []
    truncated = False
    try:
        with os.scandir(home_text) as listing:
            for entry in listing:
                if len(entries) >= limit:
                    truncated = True
                    break
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    is_dir = False
                entries.append((entry.name, is_dir))
    except OSError as exc:
        notes.append(f"data home {home_text} could not be listed ({type(exc).__name__}) — no "
                     f"namespaces were classified")
        return _empty_classes(), notes
    if truncated:
        notes.append(cap_note(
            caps, "MAX_NAMESPACES_LISTED",
            f"the data home {home_text} holds more entries than were listed; every namespace "
            f"count on this page is a lower bound"))

    skipped = []
    residue = classes["residue"]
    for name, is_dir in sorted(entries):
        if not is_dir:
            skipped.append(name)
            continue
        path = os.path.join(home_text, name)
        names, error = _one_listing(path)
        if name in expected:
            checkout, kind = expected[name]
            classes["mapped"].append({
                "namespace": name, "checkout": checkout, "kind": kind,
                "stores": _stores(path, name, names, error, notes),
            })
        elif (error is None and RESIDUE_NAMESPACE_RE.fullmatch(name)
              and set(names) <= RESIDUE_STORES):
            residue["count"] += 1
            if len(residue["sample"]) < SAMPLE_SIZE:
                residue["sample"].append(name)
        else:
            classes["unmapped"].append({
                "namespace": name, "stores": _stores(path, name, names, error, notes),
            })
    if skipped:
        notes.append(
            f"{_plural(len(skipped), 'data-home entry', 'data-home entries')} skipped: not a "
            f"directory without following links ({_sample(skipped)})"
        )
    return classes, notes


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
        classes = _empty_classes()
        class_notes = ["no data home was given — nothing was classified"]
    else:
        try:
            classes, class_notes = classify_namespaces(data_home, checkouts, caps)
        except Exception as exc:
            classes = _empty_classes()
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
        entry["notes"] = [str(note) for note in entry.get("notes") or ()]
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


def build_namespaces_panel(ctx):
    model = ctx["model"]
    classes = model["classes"]
    mapped, unmapped, residue = classes["mapped"], classes["unmapped"], classes["residue"]
    rows = []
    for row in mapped:
        rows.append([row["namespace"], "mapped", f"{row['checkout']} ({row['kind']})",
                     _stores_text(row["stores"])])
    for row in unmapped:
        rows.append([row["namespace"], "unmapped", "—", _stores_text(row["stores"])])
    if residue["count"]:
        rows.append([f"{_plural(residue['count'], 'namespace', 'namespaces')}, e.g. "
                     f"{_sample(residue['sample'])}",
                     "residue (heuristic)", "—",
                     "at most an attempts store — listed once, never opened"])
    counts = (f"{len(mapped)} mapped · {len(unmapped)} unmapped · "
              f"{residue['count']} residue")
    checkouts = model["checkouts"]
    with_namespace = {row["checkout"] for row in mapped}
    without = [checkout for checkout in checkouts if checkout not in with_namespace]
    blocks = [
        {"type": "p", "text": f"Data home {model['data_home'] or 'unknown'}: {counts}."},
        {"type": "p", "text": RESIDUE_RULE},
        {"type": "table", "headers": ["namespace", "class", "checkout / kind", "stores present"],
         "rows": rows, "empty": "No namespaces were found in the data home."},
        {"type": "p", "text": (f"Checkouts mapped by hashing their roots "
                               f"({len(checkouts)}): {', '.join(checkouts) or 'none'}.")},
    ]
    if without:
        blocks.append({"type": "p", "text": ("No namespace in this data home for: "
                                             f"{', '.join(without)}.")})
    return {
        "source": ("bin/dashboard.py — one shallow listing of the data home, namespaces mapped "
                   "through runtime_data.project_namespace"),
        "observed": "live, at build time",
        "notes": [],
        "summary": f"{counts} across {_plural(len(checkouts), 'checkout', 'checkouts')}",
        "blocks": blocks,
    }


def build_bounds_panel(ctx):
    notes = _collect_notes(ctx["notes"], ctx["model"]["panels"])
    report = caps_report(ctx["caps"], notes)
    hit = [row["name"] for row in report if row["hit"]]
    blocks = [
        {"type": "p", "text": ("Every scan behind this page is bounded. A cap that was hit cut "
                               "something short and left a note below; “not hit” means nothing "
                               "was cut at that bound in this build.")},
        {"type": "table", "headers": ["cap", "value", "status"],
         "rows": [[row["name"], row["value"], "hit" if row["hit"] else "not hit"]
                  for row in report]},
        {"type": "p", "text": f"Notes from this build, every panel's included ({len(notes)}):"},
        {"type": "list", "items": notes, "empty": "notes: none"},
    ]
    return {
        "source": "bin/dashboard.py — this build's own bounds and notes",
        "observed": "this build",
        "notes": [],
        "summary": f"{len(hit)} of {len(report)} caps hit",
        "blocks": blocks,
    }


# The registry, consumed in order. The panel ids and their page order are PINNED for the whole
# kit (TASKS.md, T2 brief item 5): later tasks insert their builders between these two, under
# exactly those ids; `bounds` stays last because it reports every other panel's notes.
PANELS = [
    (NAMESPACES_PANEL, "Namespaces in the data home", build_namespaces_panel),
    ("bounds", "Bounds and notes", build_bounds_panel),
]


# ---------------------------------------------------------------------------------------------
# Rendering. Every plain string goes through `esc`; the model is scrubbed whole before any of it.

# Text that must never appear in the page even as inert text, because the page is checked for it
# mechanically (PLAN R5). Escaping leaves `=`, `(` and `@` alone, so data text gets these three
# neutralised with character references -- the browser shows the same characters.
_TRIPWIRES = re.compile(r"(?i)(?:src|href)=|url\(|@import")


def _neutralize(match):
    text = match.group(0)
    if text.endswith("="):
        return text[:-1] + "&#61;"
    if text.endswith("("):
        return text[:-1] + "&#40;"
    return "&#64;" + text[1:]


def esc(value):
    """One value as page text -- the ONE escaping path every renderer in this module uses, so
    honesty rendering is written once (PLAN D7). HTML-escaped and tripwire-neutralised; `None`
    is never a blank cell or a silent zero (PLAN R3) -- it is the literal word `unknown`, in a
    span the stylesheet renders italic and muted but never hidden."""
    if value is None:
        return '<span class="unknown">unknown</span>'
    text = _clean(str(value))
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
    number (PLAN R3)."""
    try:
        number = float(v)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def fmt_count(v):
    """An integer count -> its digits, or `unknown` for `None` (PLAN R3). A non-finite or
    unparsable value is not `unknown` (it IS present) -- it renders as its own escaped text."""
    if v is None:
        return esc(None)
    if isinstance(v, int) and not isinstance(v, bool):
        return esc(v)
    number = _finite_float(v)
    return esc(v) if number is None else esc(int(number))


def fmt_usd(v, basis_label):
    """`$` with two decimals, plus a REQUIRED basis label in a `<span class="label">` -- a
    dollar can never appear without the basis it was measured under (PLAN D7a/b: no cell ever
    sums two bases, and a basis-less dollar is never printed). `None` -> `unknown`, no `$` at
    all. A non-finite or unparsable value gets no `$` either -- only its own escaped text,
    basis label still beside it. `basis_label` has no default: a caller that forgot it fails
    loudly, at the call site, rather than the page ever showing an unlabelled dollar."""
    if v is None:
        return esc(None)
    number = _finite_float(v)
    amount = esc(v) if number is None else f"${number:,.2f}"
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
# shape, never a pre-rendered string.
CELL_FORMATS = {
    "usd": lambda cell: fmt_usd(cell.get("value"), cell.get("basis")),
    "credits": lambda cell: fmt_credits(cell.get("value")),
    "count": lambda cell: fmt_count(cell.get("value")),
    "seconds": lambda cell: fmt_seconds(cell.get("value")),
    "date": lambda cell: fmt_date(cell.get("value")),
}


def _render_cell(cell):
    """One table cell -> HTML, escaped exactly once. A typed cell's formatter output is already
    escaped HTML and is used as-is; anything else -- including a plain string -- goes through
    `esc`, so a builder cannot pass a pre-rendered `fmt_*` string as a cell (that would be
    escaped a second time) and cannot smuggle raw HTML through a plain string either."""
    if isinstance(cell, dict) and "fmt" in cell:
        renderer = CELL_FORMATS.get(cell.get("fmt"))
        if renderer is not None:
            return renderer(cell)
        return esc(f"cell: unrecognised fmt {cell.get('fmt')!r}")
    return esc(cell)


def html_table(headers, rows, caption=None, details=False):
    """`headers`/`rows` (every cell through `_render_cell`: `esc` for a plain value, or the
    matching formatter for a typed cell -- see `CELL_FORMATS`) -> one `<table>` in a `<div
    class="table-wrap">`, so a wide table scrolls sideways and the PAGE never scrolls
    horizontally at phone width (PLAN D9). `details=True` wraps it again in `<details><summary>
    caption (N rows)</summary>...</details>` for a table too long to want open by default; the
    caption then lives only in the summary, not duplicated as a `<caption>` too."""
    rows = list(rows)
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


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def svg_bars(rows, title, desc, label_key, value_key):
    """A horizontal bar per row of `rows[i][value_key]`, labelled `rows[i][label_key]` -> one
    `<figure>` holding an inline `<svg viewBox=… role="img" aria-labelledby=…>` (title, desc,
    then the bars) and, as its `<figcaption>`, an `html_table` of the same rows -- the chart is
    never the only place a number lives. A `None` value draws no bar and reads `unknown` in the
    table twin."""
    rows = list(rows)
    title_id, desc_id = _chart_ids()
    values = [row.get(value_key) if isinstance(row, dict) else None for row in rows]
    numeric = [v for v in values if _is_number(v)]
    max_value = max(numeric) if numeric else 0
    plot_width = max(CHART_WIDTH - BAR_LABEL_WIDTH - 8, 1)
    height = max(len(rows), 1) * (BAR_ROW_HEIGHT + BAR_ROW_GAP) + BAR_ROW_GAP
    parts = [
        f'<svg viewBox="0 0 {CHART_WIDTH} {height}" role="img" '
        f'aria-labelledby="{title_id} {desc_id}">',
        f'<title id="{title_id}">{esc(title)}</title>',
        f'<desc id="{desc_id}">{esc(desc)}</desc>',
    ]
    for index, row in enumerate(rows):
        label = row.get(label_key) if isinstance(row, dict) else None
        value = values[index]
        y = BAR_ROW_GAP + index * (BAR_ROW_HEIGHT + BAR_ROW_GAP)
        parts.append(f'<text x="0" y="{y + BAR_ROW_HEIGHT - 5}" class="chart-label">'
                     f'{esc(label)}</text>')
        if _is_number(value) and max_value > 0:
            width = max(round((value / max_value) * plot_width, 1), 0)
            parts.append(f'<rect x="{BAR_LABEL_WIDTH}" y="{y}" width="{width}" '
                         f'height="{BAR_ROW_HEIGHT}" class="chart-bar"></rect>')
    parts.append("</svg>")
    svg = "\n".join(parts)
    table_rows = [[row.get(label_key) if isinstance(row, dict) else None,
                  row.get(value_key) if isinstance(row, dict) else None] for row in rows]
    table = html_table([label_key, value_key], table_rows, caption=title)
    return f"<figure>\n{svg}\n<figcaption>\n{table}\n</figcaption>\n</figure>"


def svg_sparkline(points, title, desc):
    """A line through `points` (`(label, value)` pairs, oldest first) -> one `<figure>` holding
    an inline `<svg>` (title, desc, then a polyline through the known values) and, as its
    `<figcaption>`, an `html_table` of the same points. A `None` value breaks the line rather
    than being interpolated across, and reads `unknown` in the table twin."""
    points = list(points)
    title_id, desc_id = _chart_ids()
    values = [value for _label, value in points]
    numeric = [v for v in values if _is_number(v)]
    lo = min(numeric) if numeric else 0.0
    hi = max(numeric) if numeric else 0.0
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
    for index, value in enumerate(values):
        if _is_number(value):
            x = SPARK_PAD + (plot_w * index / steps)
            y = SPARK_PAD + plot_h - ((value - lo) / span) * plot_h
            segment.append(f"{x:.1f},{y:.1f}")
        elif segment:
            if len(segment) > 1:
                parts.append(f'<polyline points="{" ".join(segment)}" class="chart-line">'
                             f'</polyline>')
            segment = []
    if len(segment) > 1:
        parts.append(f'<polyline points="{" ".join(segment)}" class="chart-line"></polyline>')
    parts.append("</svg>")
    svg = "\n".join(parts)
    table = html_table(["label", "value"], [[label, value] for label, value in points],
                       caption=title)
    return f"<figure>\n{svg}\n<figcaption>\n{table}\n</figcaption>\n</figure>"


def _render_block(block):
    """One block dict -> HTML. The vocabulary is `p` / `list` / `table` (T2) plus, from T3,
    `svg_bars` / `svg_sparkline`; an unrecognised type or shape renders a plain sentence
    rather than raising, so one bad block cannot take its whole panel down with it."""
    if not isinstance(block, dict):
        return f"<p>{esc('a block that is not a mapping was not rendered')}</p>"
    kind = block.get("type")
    if kind == "p":
        return f"<p>{esc(block.get('text'))}</p>"
    if kind == "list":
        items = block.get("items") or []
        if not items:
            return f'<p class="notes">{esc(block.get("empty") or "none")}</p>'
        return ('<ul class="notes">\n' + "\n".join(f"<li>{esc(item)}</li>" for item in items)
                + "\n</ul>")
    if kind == "table":
        rows = block.get("rows") or []
        if not rows and block.get("empty"):
            return f"<p>{esc(block['empty'])}</p>"
        return html_table(block.get("headers") or [], rows, block.get("caption"),
                          details=bool(block.get("details")))
    if kind == "svg_bars":
        rows = block.get("rows") or []
        if not rows and block.get("empty"):
            return f"<p>{esc(block['empty'])}</p>"
        return svg_bars(rows, block.get("title") or "", block.get("desc") or "",
                        block.get("label_key"), block.get("value_key"))
    if kind == "svg_sparkline":
        points = block.get("points") or []
        if not points and block.get("empty"):
            return f"<p>{esc(block['empty'])}</p>"
        return svg_sparkline(points, block.get("title") or "", block.get("desc") or "")
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


def render_page(model, home):
    """The whole page as one string. Deterministic for the same model except the one line that
    carries `data-built-at` (chart ids are reset here for the same reason: PLAN D9)."""
    _reset_chart_sequence()
    view = _scrub_tree(model, home)
    panels = [entry for entry in view.get("panels") or () if isinstance(entry, dict)]
    built_at = view.get("built_at")
    built_text = f"built {built_at or 'unknown'} — a static file: rebuild to refresh"
    primary_text = f"primary checkout: {view.get('primary_checkout') or 'unknown'}"
    data_home_text = f"data home: {view.get('data_home') or 'unknown'}"
    sections = []
    for entry in panels:
        body_html = "\n".join(_render_block(block) for block in entry.get("blocks") or ())
        observed = entry.get("observed")
        sections.append(panel(entry.get("id"), entry.get("title") or entry.get("id"),
                              entry.get("source"), observed, age_days(observed, built_at),
                              entry.get("notes") or (), body_html, entry.get("refresh_hint")))
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
        nav(panels),
        "<main>",
        *sections,
        "</main>",
        "</div>",
        "</body>",
        "</html>",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------
# Receipt and summary.

def build_receipt(model, home, out_dir):
    """build.json: what was built, from where, what was cut and every note -> scrubbed dict."""
    classes = model.get("classes") or {}
    residue = classes.get("residue") or {}
    caps = model.get("caps") or []
    receipt = {
        "schema_version": model.get("schema_version"),
        "built_at": model.get("built_at"),
        "page": os.path.join(os.fspath(out_dir), PAGE_NAME),
        "receipt": os.path.join(os.fspath(out_dir), RECEIPT_NAME),
        "primary_checkout": model.get("primary_checkout"),
        "checkouts": list(model.get("checkouts") or ()),
        "data_home": model.get("data_home"),
        "classes": {
            "mapped": {"count": len(classes.get("mapped") or ())},
            "unmapped": {"count": len(classes.get("unmapped") or ())},
            "residue": {"count": residue.get("count"), "sample": list(residue.get("sample") or ())},
        },
        "panels": [{key: entry.get(key) for key in ("id", "title", "source", "observed", "summary")}
                   for entry in model.get("panels") or ()],
        "caps": caps,
        "caps_hit": [row.get("name") for row in caps if row.get("hit")],
        "notes": list(model.get("notes") or ()),
    }
    return _scrub_tree(receipt, home)


def summary_lines(receipt):
    """The one-screen summary `build` prints."""
    classes = receipt.get("classes") or {}

    def count(name):
        return (classes.get(name) or {}).get("count")

    lines = [
        f"page:       {receipt.get('page')}",
        f"receipt:    {receipt.get('receipt')}",
        f"built at:   {receipt.get('built_at')}",
        (f"namespaces: {count('mapped')} mapped · {count('unmapped')} unmapped · "
         f"{count('residue')} residue (heuristic: counted, never opened)"),
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
    receipt = build_receipt(model, home, out_dir)
    page = render_page(model, home)
    return out_dir, model, receipt, page


# ---------------------------------------------------------------------------------------------
# The one fixture builder, shared by `demo` and the tests.

def synthetic_world(root, residue=30):
    """A synthetic data home and checkout under `root` -> dict of paths.

    `root/checkout` holds `.claude/kits/demo-kit/{TASKS,NOTES}.md` and an empty `tasks/kits/`;
    `root/data-home` holds the checkout's mapped namespace with a ledger (a finished, verified,
    projected attempt and one started attempt that never finished), `residue` residue
    namespaces each holding only `attempts/kit/events.jsonl` with one event, and one unmapped
    namespace with a ledger. Every value is synthetic; nothing outside `root` is touched.
    """
    rd, al, sp = _mod("runtime_data"), _mod("attempt_ledger"), _mod("safe_paths")
    root = Path(root)
    data_home = root / "data-home"
    checkout = root / "checkout"
    kits_dir = checkout / ".claude" / "kits"
    kit_dir = kits_dir / DEMO_KIT
    for directory in (data_home, kit_dir, checkout / "tasks" / "kits"):
        rd.ensure_private(directory)
    sp.confined_write_bytes(kit_dir, "TASKS.md", DEMO_TASKS_MD, what="synthetic kit")
    sp.confined_write_bytes(kit_dir, "NOTES.md", DEMO_NOTES_MD, what="synthetic kit")

    namespace = rd.project_namespace(checkout)
    ledger = al.AttemptLedger(data_home / namespace / al.STORE, DEMO_KIT)
    first = ledger.record_started(DEMO_RUN, "T1", "initial", SYNTHETIC_MODEL,
                                  prompt="synthetic prompt", verify_cmd="synthetic verify")
    ledger.record_finished(DEMO_RUN, "T1", first, "ok", 0, "synthetic report", duration_s=1.0)
    ledger.record_verify(DEMO_RUN, "T1", first, 0, "Ran 1 test in 0.01s\n\nOK\n")
    ledger.record_projected(DEMO_RUN, "T1", "done", result="pass", outcome_line=True)
    ledger.record_started(DEMO_RUN, "T2", "initial", SYNTHETIC_MODEL,
                          prompt="synthetic prompt", verify_cmd="synthetic verify")

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

    return {
        "root": root,
        "data_home": data_home,
        "checkout": checkout,
        "kits_dir": kits_dir,
        "kit_dir": kit_dir,
        "namespace": namespace,
        "ledger": ledger.events_path,
        "residue": residue_names,
        "unmapped": UNMAPPED_NAMESPACE,
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
