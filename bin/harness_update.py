#!/usr/bin/env python3
"""One freshness check (and, in later tasks, one refresh) across all three harnesses this repo
installs into, plus its own generated data surfaces.

CONTRACT (binding for every subcommand this file will ever grow, not just `check`):
  - `check` is strictly read-only. It never writes a byte anywhere -- not under this repo, not
    under any harness home directory, and never under `~/.claude` in particular. It only reads
    files and calls read-only functions on sibling `bin/` modules.
  - This engine never writes under `~/.claude`, in any subcommand, ever. Where a later `apply`
    subcommand exists, the Claude side of it only *prints* the remedy `bin/plugin_staleness.py`
    already computes -- it never runs `claude plugin ...` itself. The user (or the session, on
    the user's explicit go-ahead) runs the printed commands.
  - Home-directory defaults (`~/.claude/...`, `~/.copilot`, `~/.codex`) appear ONLY as argparse
    defaults (built once, at module load, with `os.path.expanduser` -- matching
    `bin/plugin_staleness.py`'s own convention) or inside `cmd_*` handlers that read them off
    `args`. Every function below that -- the "pure layer" -- takes its paths as explicit
    parameters and is introspection-tested to contain none of `Path.home`, `subprocess`, or
    `urlopen`.
  - `bin/` is not a package. Reused sibling modules (`plugin_staleness.py`, and in later tasks
    `harness_select.py`, `sync_pricing_refs.py`, `sync_codex_surfaces.py`) are loaded with
    `importlib.util.spec_from_file_location` via the single `_load_sibling()` helper below --
    the same pattern `tests/test_harness_select.py`'s `_load` uses. Their logic is never copied
    or forked here; this file only calls their functions and reshapes the results for its own
    check card.

T1 wired up the `check` subcommand's `claude` section, reusing `bin/plugin_staleness.py` end to
end: identity, installed-manifest resolution, HEAD-vs-manifest comparison, and IN SYNC / SHA
STALE / DRIFTED classification all come from that module untouched. T2 added the `copilot`
section, reusing `bin/harness_select.py`'s `install_copilot` inventory semantics without ever
writing: required core is `copilot/.github/agents/*.agent.md` (missing/empty is a repo-side
error, mirroring `install_copilot`'s own `FileNotFoundError` contract); `copilot/.github/skills/`
is tolerated missing or empty. T3 added the `codex` section, entirely delegated to
`bin/harness_select.py`'s `doctor_codex` (itself read-only by construction -- it runs
`plan_codex_setup` over every Codex component with `legacy_copy=True, refresh_managed=False` and
never writes): action states (`install`/`up-to-date`/`managed-update`/`unmanaged`/`conflict`) are
summarized as counts, its `ownership_manifest` field and `session_note` are surfaced verbatim.
T5 added the final `data` section (pricing-file ages, generated-mirror staleness via
`bin/sync_pricing_refs.py`'s and `bin/sync_codex_surfaces.py`'s own `check`/`sync(mode="check")`
functions, and the PLAN.md D7 docs-snapshot-label check), the aggregate verdict line on the human
card, and the `demo` subcommand -- a synthetic, self-cleaning smoke that touches no real repo and
no real home.

T6 (this revision) adds `apply`, which is delegation plus reporting and contains ZERO file-write
logic of its own (PLAN.md D3/D4): the Copilot home is refreshed by `harness_select.install_copilot`
(overwrite-in-place, inherited and stated in the report), the Codex home by the LEGACY
`harness_select.install_codex` -- whose two channels differ and are reported separately:
`<home>/prompts/*.md` are plugin-generated deprecated mirrors that it OVERWRITES in place
(every destination that actually differed is pre-scanned, listed, and labeled -- never silent,
never called "preserved"), while `<home>/AGENTS.md` and `<home>/skills/<name>/` are user-editable
and no-clobber (`skip-differs` listed, never forced, never deleted). Project-scope agent TOMLs and
the modern `plugin` component `check` reports on are outside apply's reach; the report names that
coverage limit and prints the `harness_select install --harness codex` remedy instead of claiming
completion over drift it cannot touch. Generated mirrors are refreshed by `sync_pricing_refs.sync` and
`sync_codex_surfaces.sync(root, "build")`. The Claude target of `apply` is print-only forever: it
emits `plugin_staleness.build_remedy(...)`'s string (which already ends "(restart to apply)") and
reports `{"action": "remedy-printed"}`. An absent Copilot or Codex home is "not installed" --
`apply` refreshes homes, it never conjures one. `--dry-run` writes nothing anywhere (both home
writers take a real `dry_run` parameter; the two mirror writers have read-only `check`
counterparts, which dry-run calls instead). `apply` exits 0 on success including "nothing to do",
1 on any writer error -- surfaced verbatim in the report and the `--json` `errors` list, never
swallowed. What `apply` deliberately CANNOT do: edit pricing numbers, edit docs snapshot tables or
labels, or touch the Claude plugin cache.

Exit codes for `check`: 0 when nothing checked reports drift, 3 when any section does (`apply`
uses 0/1 instead -- it makes no freshness verdict). A `SHA
STALE` claude result counts as drift for this engine's exit code, even though
`plugin_staleness.py`'s OWN exit code treats SHA STALE as non-actionable (a squash-merge/rebase
artifact) -- see `build_claude_section()` below for why the two engines disagree on that one
point. Pricing-file AGE is informational only (never drift, even past the 60-day re-verify
threshold) -- only generated-mirror staleness and docs-snapshot-label staleness count toward the
`data` section's drift flag. "not installed" is absence, never failure, and never counts as
drift.
"""

import argparse
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parent.parent

# CLI convenience defaults only -- every pure function below takes its paths as explicit
# arguments; no function beneath the cmd_* handlers ever resolves a real home on its own.
DEFAULT_REPO_ROOT = str(REPO_ROOT)
DEFAULT_INSTALLED_MANIFEST = os.path.expanduser("~/.claude/plugins/installed_plugins.json")
DEFAULT_COPILOT_HOME = os.path.expanduser("~/.copilot")
DEFAULT_CODEX_HOME = os.path.expanduser("~/.codex")

EXIT_OK = 0
# `apply` makes no freshness verdict, so it never uses EXIT_DRIFT: 0 on success (including
# "nothing to do"), EXIT_ERROR on any writer error.
EXIT_ERROR = 1
EXIT_DRIFT = 3


def _load_sibling(name):
    """Load `bin/<name>.py` as a standalone module via importlib -- `bin/` is not a package, so
    this is the repo's established sibling-module loader (mirrors `tests/test_harness_select.py`'s
    `_load`). Used for every reused module in this kit; never edits or monkeypatches what it
    loads, only calls its public functions."""
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_claude_section(repo_root, installed_manifest):
    """The `claude` section of the check card: entirely delegated to
    `bin/plugin_staleness.py.check_staleness()`, which is itself strictly read-only (it reads
    `.claude-plugin/plugin.json`, `marketplace.json`, an installed-manifest JSON file, and
    `.git/HEAD` directly -- never the `git` binary, never a write). This function only reshapes
    that result into this engine's section shape; it never executes the remedy string it carries.

    Drift mapping: `DRIFTED` and `SHA STALE` both count as drift here, `IN SYNC` and "not
    installed" do not. This deliberately widens plugin_staleness's own exit-3 rule (which treats
    SHA STALE as non-actionable, exit 0) because this engine's `check` is meant to catch exactly
    the class of incident that motivated this kit: an installed cache whose recorded commit no
    longer matches HEAD is still something worth surfacing in an aggregate freshness card, even
    when the file content itself has not moved."""
    plugin_staleness = _load_sibling("plugin_staleness")
    result = plugin_staleness.check_staleness(repo_root, installed_manifest)

    if not result.get("installed"):
        status = "not installed"
        drift = False
    else:
        status = result.get("status")
        drift = status in ("DRIFTED", "SHA STALE")

    return {
        "status": status,
        "drift": drift,
        "plugin_key": result.get("plugin_key"),
        "detail": result,
    }


def _bundle_resolved_bytes(harness_select_mod, source, repo_root):
    """The bytes `harness_select.install_copilot` (T2) or `harness_select.install_codex` (T6)
    would write for `source`, computed without writing anything.

    One helper serves both writers because both use the identical mechanism -- the same
    `text.replace(PLACEHOLDER, str(repo_root))` line on the UNRESOLVED repo root (see
    `install_copilot`'s agent/skill loops and `install_codex`'s prompts loop). This file therefore
    contains exactly one placeholder-substitution implementation, never a second copy.

    Delta from the task brief (recorded in NOTES.md's T2 entry): the brief suggested reusing
    `harness_select._resolved_bytes`, but that helper additionally calls
    `Path(repo_root).resolve()` before substituting the placeholder, while `install_copilot`
    itself resolves the placeholder with the *unresolved* `str(repo_root)` it was given (see
    `harness_select.install_copilot`'s `text.replace(PLACEHOLDER, str(repo_root))` line). On a
    symlinked temp path (e.g. macOS `/var` -> `/private/var`) those two produce different bytes.
    Since the reused module is authoritative over the brief's suggested helper name, this
    function matches `install_copilot`'s own mechanism exactly -- byte for byte, including in
    fixtures built from an unresolved `tempfile.TemporaryDirectory()` path -- while still
    reusing `harness_select.PLACEHOLDER` by import rather than defining a second literal
    constant here."""
    raw = source.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw
    return text.replace(harness_select_mod.PLACEHOLDER, str(repo_root)).encode("utf-8")


def _compare_copilot_file(harness_select_mod, rel_path, source, dest, repo_root):
    resolved = _bundle_resolved_bytes(harness_select_mod, source, repo_root)
    if not dest.is_file():
        state = "missing"
    else:
        try:
            state = "up-to-date" if dest.read_bytes() == resolved else "differs"
        except OSError:
            state = "differs"
    return {"path": rel_path, "state": state}


def build_copilot_section(repo_root, copilot_home):
    """The `copilot` section of the check card: a read-only mirror of
    `harness_select.install_copilot`'s inventory. Required core is
    `copilot/.github/agents/*.agent.md` -- missing or empty is a repo-side error state,
    mirroring `install_copilot`'s own `FileNotFoundError` contract, and counts as drift.
    `copilot/.github/skills/` is tolerated missing or empty, exactly as `install_copilot`
    tolerates it. Never writes anything -- only reads bundle source files under `repo_root`
    and destination files under `copilot_home`.

    A `copilot_home` that does not exist at all (or was never given) is "not installed" --
    absence, not failure, exit-0 contribution. Once a home exists, every bundle file is
    classified `missing` (no destination), `up-to-date` (byte-equal to the resolved source),
    or `differs`; any `missing`/`differs` is drift. A destination file the bundle does not
    know about is ignored -- this audits the bundle's own files, not the user's whole home."""
    if copilot_home is None:
        return {"status": "not installed", "drift": False, "counts": {}, "files": []}

    copilot_home = Path(copilot_home)
    if not copilot_home.is_dir():
        return {"status": "not installed", "drift": False, "counts": {}, "files": []}

    harness_select_mod = _load_sibling("harness_select")
    repo_root = Path(repo_root)
    bundle_agents = repo_root / "copilot" / ".github" / "agents"
    bundle_skills = repo_root / "copilot" / ".github" / "skills"

    agent_files = sorted(bundle_agents.glob("*.agent.md")) if bundle_agents.is_dir() else []
    if not agent_files:
        return {
            "status": "error",
            "drift": True,
            "error": (
                f"no *.agent.md files found under {bundle_agents} -- is the Copilot bundle "
                "(copilot/.github/agents/) present?"
            ),
            "counts": {},
            "files": [],
        }

    files = []
    for src in agent_files:
        rel = f"agents/{src.name}"
        dest = copilot_home / "agents" / src.name
        files.append(_compare_copilot_file(harness_select_mod, rel, src, dest, repo_root))

    if bundle_skills.is_dir():
        for src in sorted(p for p in bundle_skills.rglob("*") if p.is_file()):
            rel_from_skills = src.relative_to(bundle_skills)
            rel = f"skills/{rel_from_skills.as_posix()}"
            dest = copilot_home / "skills" / rel_from_skills
            files.append(_compare_copilot_file(harness_select_mod, rel, src, dest, repo_root))

    counts = {"up-to-date": 0, "missing": 0, "differs": 0}
    for entry in files:
        counts[entry["state"]] += 1
    drift = counts["missing"] > 0 or counts["differs"] > 0

    return {
        "status": "drift" if drift else "up-to-date",
        "drift": drift,
        "counts": counts,
        "files": files,
    }


_CODEX_NOT_INSTALLED = {
    "status": "not installed",
    "drift": False,
    "counts": {},
    "ownership_manifest": None,
    "session_note": None,
    "actions": [],
}

# Action states doctor_codex/plan_codex_setup can produce (confirmed by reading
# harness_select.py directly for this task -- no "skip" state is ever actually emitted by
# plan_codex_setup or doctor_codex; it only appears as a defensive filter inside
# apply_codex_plan, which this read-only engine never calls). Any of these three means a write
# is pending or a file needs human attention; "unmanaged" alone is a warning, never drift.
_CODEX_DRIFT_STATES = ("install", "managed-update", "conflict")


def build_codex_section(repo_root, codex_home):
    """The `codex` section of the check card: entirely delegated to
    `harness_select.doctor_codex(repo_root, codex_home)`, which is read-only by construction --
    it runs `plan_codex_setup` over every Codex component (`plugin`, `agents`, `skills`,
    `prompts`, `guidance`) with `legacy_copy=True, refresh_managed=False` and never writes a
    file. This function only reshapes that result into this engine's section shape; it never
    calls `apply_codex_plan`.

    `doctor_codex` itself does not require `codex_home` to already exist -- against a missing
    home it happily computes an all-`install` plan -- so this function checks existence FIRST
    and reports "not installed" without ever calling `doctor_codex` against a home that isn't
    there, matching the same absence-is-not-failure precedent as the claude and copilot
    sections.

    Drift mapping: any `install`, `managed-update`, or `conflict` action counts as drift.
    `unmanaged` (doctor's "managed copy is stale, no refresh requested" / "non-canonical file
    preserved for manual review" state) is reported plainly as a warning but never counted as
    drift -- nothing is broken, only worth a human's attention."""
    if codex_home is None:
        return dict(_CODEX_NOT_INSTALLED)

    codex_home = Path(codex_home)
    if not codex_home.is_dir():
        return dict(_CODEX_NOT_INSTALLED)

    harness_select_mod = _load_sibling("harness_select")
    report = harness_select_mod.doctor_codex(repo_root, codex_home)

    counts = {}
    for action in report.get("actions", []):
        state = action.get("state", "unknown")
        counts[state] = counts.get(state, 0) + 1

    drift = any(counts.get(state, 0) for state in _CODEX_DRIFT_STATES)

    return {
        "status": "drift" if drift else "up-to-date",
        "drift": drift,
        "counts": counts,
        "ownership_manifest": report.get("ownership_manifest"),
        "session_note": report.get("session_note"),
        "actions": report.get("actions", []),
    }


# The three pricing files this engine ages and checks, relative to --repo-root. Per CLAUDE.md,
# these files are the only numeric sources of truth -- this engine only ever reads their
# `cached_date` field, never a price, and never hardcodes a date of its own outside fixtures.
PRICING_FILES = ("data/pricing.json", "data/pricing.copilot.json", "data/pricing.codex.json")

# PLAN.md D7: which partner doc must carry which pricing file's cached_date string. codex's
# pricing file intentionally has no entry -- its partner doc carries no numeric snapshot by
# design (tests/test_codex_docs.py forbids live numbers there).
DOCS_LABEL_MAP = (
    ("data/pricing.json", "README.md"),
    ("data/pricing.copilot.json", "docs/COPILOT-HARNESS.md"),
)

# The route skill's vendored-snapshot threshold: a flag for "re-verify against source", never
# an auto-refresh, and never drift for this engine's exit-code purposes.
PRICING_AGE_STALE_DAYS = 60

_DOCS_LABEL_STALE_NOTE = (
    "docs snapshot label stale -- update the doc together with the data file (CLAUDE.md rule)"
)
_CODEX_DOCS_NO_SNAPSHOT_NOTE = (
    "codex partner doc carries no numeric snapshot by design -- nothing to check"
)


def _read_cached_date(path):
    """Best-effort `cached_date` string from a pricing JSON file. Returns None on any read or
    parse failure, or if the field is absent/non-string -- never raises."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    value = data.get("cached_date")
    return value if isinstance(value, str) else None


def _pricing_age_entry(repo_root, rel_path, today):
    path = Path(repo_root) / rel_path
    cached_date_str = _read_cached_date(path)
    entry = {"file": rel_path, "cached_date": cached_date_str, "age_days": None, "stale_flag": False}
    if cached_date_str is None:
        entry["note"] = "cached_date unreadable or missing"
        return entry
    try:
        cached_date = date.fromisoformat(cached_date_str)
    except ValueError:
        entry["note"] = "cached_date is not a valid ISO date"
        return entry
    age_days = (today - cached_date).days
    entry["age_days"] = age_days
    if age_days > PRICING_AGE_STALE_DAYS:
        entry["stale_flag"] = True
        entry["note"] = "re-verify against source"
    return entry


def _relativize(path, root):
    try:
        return Path(path).relative_to(Path(root)).as_posix()
    except ValueError:
        return str(path)


def _docs_label_entry(repo_root, file_rel, cached_date_str, doc_rel):
    if cached_date_str is None:
        return {"file": file_rel, "doc": doc_rel, "ok": False, "note": _DOCS_LABEL_STALE_NOTE}
    doc_path = Path(repo_root) / doc_rel
    try:
        text = doc_path.read_text(encoding="utf-8")
    except OSError:
        return {"file": file_rel, "doc": doc_rel, "ok": False, "note": _DOCS_LABEL_STALE_NOTE}
    ok = cached_date_str in text
    entry = {"file": file_rel, "doc": doc_rel, "ok": ok}
    if not ok:
        entry["note"] = _DOCS_LABEL_STALE_NOTE
    return entry


def build_data_section(repo_root, today=None):
    """The `data` section of the check card: pricing-file ages (informational only), generated
    mirror staleness (reused by import: `sync_pricing_refs.check()` and
    `sync_codex_surfaces.sync(mode="check")`), and the PLAN.md D7 docs-snapshot-label check.

    `today` defaults to the real wall-clock date but is always an explicit parameter -- tests
    inject a fixed date instead of mocking global time, per this task's own instruction. This
    is the one place in the pure layer that reads wall-clock time; it still never resolves a
    real home directory, shells out, or opens a network connection.

    Never writes: `sync_pricing_refs.check()` is the read-only counterpart to its `sync()`
    writer (never called here), and `sync_codex_surfaces.sync(mode="check")` is that module's
    own read-only mode (its `"build"` mode, which writes, is never called here either). A
    malformed or absent generated-mirror SOURCE (e.g. a codex skill/agent file
    `sync_codex_surfaces.expected_prompts()` needs) makes that call raise -- caught here and
    surfaced as a section-level error, per this task's brief, rather than crashing `check`.

    Drift mapping: pricing AGE never drifts, even past the 60-day threshold (a flag, never an
    auto-refresh). Any stale generated mirror, any mirror-check error, or any stale docs
    snapshot label (except codex's, which is never checked by design) drifts."""
    if today is None:
        today = date.today()
    repo_root = Path(repo_root)

    pricing_ages = [_pricing_age_entry(repo_root, rel, today) for rel in PRICING_FILES]
    cached_dates = {entry["file"]: entry["cached_date"] for entry in pricing_ages}

    sync_pricing_refs_mod = _load_sibling("sync_pricing_refs")
    sync_codex_surfaces_mod = _load_sibling("sync_codex_surfaces")

    pricing_stale = []
    codex_stale = []
    mirror_errors = []
    try:
        pricing_stale = [_relativize(p, repo_root) for p in sync_pricing_refs_mod.check(repo_root)]
    except OSError as exc:
        mirror_errors.append(f"pricing mirrors: {exc}")

    try:
        codex_stale = list(sync_codex_surfaces_mod.sync(repo_root, "check"))
    except (OSError, RuntimeError, ValueError) as exc:
        mirror_errors.append(f"codex mirrors: {exc}")

    mirrors = {"pricing_stale": pricing_stale, "codex_stale": codex_stale, "errors": mirror_errors}
    mirrors_drift = bool(pricing_stale) or bool(codex_stale) or bool(mirror_errors)

    docs_labels = [
        _docs_label_entry(repo_root, file_rel, cached_dates.get(file_rel), doc_rel)
        for file_rel, doc_rel in DOCS_LABEL_MAP
    ]
    docs_labels.append(
        {"file": "data/pricing.codex.json", "doc": None, "ok": True, "note": _CODEX_DOCS_NO_SNAPSHOT_NOTE}
    )
    labels_drift = any(not entry["ok"] for entry in docs_labels)

    drift = mirrors_drift or labels_drift

    return {
        "status": "drift" if drift else "up-to-date",
        "drift": drift,
        "pricing_ages": pricing_ages,
        "mirrors": mirrors,
        "docs_labels": docs_labels,
    }


def run_check(repo_root, installed_manifest, copilot_home=None, codex_home=None, today=None):
    """The pure aggregation engine behind the `check` subcommand. Builds all four real sections
    and derives the overall `status`/`exit`. `today` is passed straight through to
    `build_data_section` (see its docstring for why it's an explicit parameter, never mocked
    global time)."""
    sections = {
        "claude": build_claude_section(repo_root, installed_manifest),
        "copilot": build_copilot_section(repo_root, copilot_home),
        "codex": build_codex_section(repo_root, codex_home),
        "data": build_data_section(repo_root, today=today),
    }

    any_drift = any(section.get("drift") for section in sections.values())
    status = "drift" if any_drift else "fresh"
    exit_code = EXIT_DRIFT if any_drift else EXIT_OK

    result = dict(sections)
    result["status"] = status
    result["exit"] = exit_code
    return result


def _render_claude_section(section):
    lines = ["## claude", f"status: {section['status']}"]
    detail = section.get("detail") or {}
    if section["status"] == "not installed":
        lines.append(f"not installed -- no entry for `{section.get('plugin_key')}`")
    elif section["status"] == "DRIFTED":
        lines.append(f"remedy: {detail.get('remedy')}")
    elif section["status"] == "SHA STALE":
        lines.append(f"note: {detail.get('note')}")
        lines.append("(flagged as drift by this aggregate check, unlike plugin_staleness alone)")
    else:
        lines.append("in sync")
    return "\n".join(lines)


def _render_copilot_section(section):
    lines = ["## copilot", f"status: {section['status']}"]
    if section["status"] == "not installed":
        lines.append("not installed -- no copilot home directory found")
        return "\n".join(lines)
    if section["status"] == "error":
        lines.append(f"error: {section.get('error')}")
        return "\n".join(lines)
    counts = section.get("counts", {})
    lines.append(
        "up-to-date: {u}  missing: {m}  differs: {d}".format(
            u=counts.get("up-to-date", 0), m=counts.get("missing", 0), d=counts.get("differs", 0)
        )
    )
    problem_paths = [f["path"] for f in section.get("files", []) if f["state"] != "up-to-date"]
    if problem_paths:
        shown = problem_paths[:5]
        lines.append("examples: " + ", ".join(shown))
        remaining = len(problem_paths) - len(shown)
        if remaining > 0:
            lines.append(f"...and {remaining} more")
    return "\n".join(lines)


def _render_codex_section(section):
    lines = ["## codex", f"status: {section['status']}"]
    if section["status"] == "not installed":
        lines.append("not installed -- no codex home directory found")
        return "\n".join(lines)
    counts = section.get("counts", {})
    order = ("install", "up-to-date", "managed-update", "unmanaged", "conflict")
    lines.append("  ".join(f"{state}: {counts.get(state, 0)}" for state in order))
    if counts.get("unmanaged"):
        lines.append(
            f"warning: {counts['unmanaged']} unmanaged file(s) -- non-canonical or "
            "stale-managed, preserved for manual review (not drift)"
        )
    lines.append(f"ownership manifest: {section.get('ownership_manifest')}")
    if section.get("session_note"):
        lines.append(f"note: {section['session_note']}")
    return "\n".join(lines)


def _render_data_section(section):
    lines = ["## data", f"status: {section['status']}"]
    for age in section["pricing_ages"]:
        detail = f"{age['file']}: cached {age['cached_date']}"
        if age["age_days"] is not None:
            detail += f" ({age['age_days']}d old)"
        if age.get("note"):
            detail += f" -- {age['note']}"
        lines.append(detail)
    mirrors = section["mirrors"]
    lines.append(
        f"generated mirrors -- pricing stale: {len(mirrors['pricing_stale'])}  "
        f"codex stale: {len(mirrors['codex_stale'])}"
    )
    for path in mirrors["pricing_stale"]:
        lines.append(f"  stale: {path}")
    for name in mirrors["codex_stale"]:
        lines.append(f"  stale: codex/prompts/{name}")
    for err in mirrors["errors"]:
        lines.append(f"  error: {err}")
    for label in section["docs_labels"]:
        mark = "ok" if label["ok"] else "STALE"
        doc = label["doc"] or "(n/a)"
        line = f"docs label {label['file']} -> {doc}: {mark}"
        if label.get("note"):
            line += f" -- {label['note']}"
        lines.append(line)
    return "\n".join(lines)


def render_card(result):
    """Render a `run_check()` result as a human-readable freshness card, ending with one
    verdict line naming which sections drifted (or that all four are fresh)."""
    lines = [
        "# harness-update check",
        "",
        _render_claude_section(result["claude"]),
        "",
        _render_copilot_section(result["copilot"]),
        "",
        _render_codex_section(result["codex"]),
        "",
        _render_data_section(result["data"]),
        "",
    ]
    drifted = [name for name in ("claude", "copilot", "codex", "data") if result[name].get("drift")]
    if drifted:
        lines.append("verdict: drifted -- " + ", ".join(drifted))
    else:
        lines.append("verdict: all sections fresh")
    lines.append(f"status: {result['status']}")
    lines.append(f"exit: {result['exit']}")
    return "\n".join(lines)


def cmd_check(args):
    result = run_check(args.repo_root, args.installed_manifest, args.copilot_home, args.codex_home)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render_card(result))
    return result["exit"]


# ---- apply: delegation to existing writers, never a new write path -----------------------------
#
# PLAN.md D3/D4. Every byte this subcommand causes to be written is written by a function in a
# reused sibling module (`harness_select.install_copilot`, `harness_select.install_codex`,
# `sync_pricing_refs.sync`, `sync_codex_surfaces.sync(..., "build")`). Nothing below opens a file
# for writing, creates a directory, or deletes anything -- the four `apply_*_target` functions
# only call those writers and reshape what they return.
#
# The Claude target is print-only, always: `apply_claude_target` computes
# `plugin_staleness.build_remedy(...)` from this repo's own identity and returns it as a STRING.
# Deliberately, none of the four functions below (nor `run_apply`, `render_apply_report`, or
# `cmd_apply`) contains the literal substring that names the Claude home directory anywhere --
# not in a path, not in a note -- so a grep over apply's code cannot even find a candidate write
# path to argue about. `ApplyNeverNamesTheClaudeHomeTests` enforces exactly that.

APPLY_TARGETS = ("claude", "copilot", "codex", "mirrors")

_COPILOT_OVERWRITE_NOTE = (
    "copilot installs overwrite in place -- inherited, documented install_copilot behavior "
    "(the bundle's own files are replaced; files the bundle does not know about are untouched)"
)

# PLAN.md D3(b) as CORRECTED at the P2 review. `install_codex` is NOT no-clobber wholesale: its
# prompts loop appends every source as `(dest, "install")` and calls `dest.write_text(...)`
# unconditionally, with no comparison -- a differing `<home>/prompts/<name>.md` is replaced, not
# preserved. Only `AGENTS.md` and `skills/<name>/` compare first and yield `skip-differs`. So this
# engine reports the codex home as TWO channels with different contracts, and never lets the
# no-clobber wording cover the overwrite one.
_CODEX_PROMPTS_OVERWRITE_NOTE = (
    "prompts overwrite in place -- inherited, documented install_codex behavior: "
    "<home>/prompts/*.md are plugin-generated deprecated mirrors, rewritten unconditionally "
    "(every differing destination is listed below, never silently replaced)"
)
_CODEX_PROMPT_OVERWRITE_LABEL = (
    "rewritten -- differing generated mirror replaced (prompts are plugin-owned)"
)
_CODEX_PROMPT_OVERWRITE_LABEL_DRY = (
    "would be rewritten -- differing generated mirror replaced (prompts are plugin-owned)"
)
_CODEX_NO_CLOBBER_NOTE = (
    "AGENTS.md and skills/<name>/ are user-editable and no-clobber -- a differing destination is "
    "reported skip-differs and never overwritten"
)
_CODEX_SKIP_DIFFERS_NOTE = (
    "preserved -- user file differs; resolve via harness_select install --harness codex if intended"
)

# What apply's codex writer does NOT reach. `check`'s codex section runs `doctor_codex`, which
# covers the modern component set; the LEGACY `install_codex` this engine delegates to writes only
# the three channels above. Stating this is the difference between "apply complete" and a claim
# apply cannot support.
_CODEX_COVERS = ("prompts", "AGENTS.md", "skills/<name>/")
_CODEX_NOT_COVERED = ("agents (project-scope <repo>/.codex/agents/*.toml)", "plugin (modern component)")
_CODEX_COVERAGE_NOTE = (
    "coverage limit -- apply refreshes the legacy channels only (prompts, AGENTS.md, "
    "skills/<name>/). Project-scope agent TOMLs and the modern plugin component that check's "
    "doctor_codex reports on are OUTSIDE apply's reach; refresh those yourself with: "
    "python3 bin/harness_select.py install --harness codex   (printed, never executed)"
)

_CLAUDE_CONDITIONAL_FRAMING = (
    "apply makes no freshness determination -- if `check` reported claude drift, refresh with:"
)
_CLAUDE_PRINT_ONLY_NOTE = (
    "printed, never executed -- this engine never writes the Claude plugin cache in any "
    "subcommand; run the remedy yourself"
)
_RESTART_NOTE = "(restart to apply)"
_NOT_INSTALLED_NOTE = "not installed -- nothing to refresh (absence is not failure)"

# apply refreshes three target families; drift can persist in surfaces none of its writers own.
# The verdict says so rather than implying the tree is now clean.
_APPLY_RESIDUAL_DRIFT_CAVEAT = (
    "rerun check; drift outside apply's writers (claude remedy, codex modern components, "
    "docs labels) is reported there"
)


def apply_claude_target(repo_root):
    """The Claude target of `apply`: NEVER a write, in any mode, dry-run or not.

    Reuses `plugin_staleness.read_plugin_identity` + `build_remedy` -- the exact remedy string
    `check` prints for a DRIFTED install, derived from this repo's own plugin/marketplace
    identity, never a hardcoded plugin name. The remedy already ends with the restart note; it is
    appended only if a future edit to `plugin_staleness` ever drops it, so the contract line is
    guaranteed present either way.

    The remedy is framed CONDITIONALLY (`_CLAUDE_CONDITIONAL_FRAMING`): `apply` reads no installed
    manifest and makes no freshness determination of its own, so printing the remedy must not be
    read as an assertion that the install is stale. `check` is what determines that.

    `action` is always the literal "remedy-printed" -- the grep-proof marker that no branch of
    apply writes the Claude plugin cache."""
    plugin_staleness = _load_sibling("plugin_staleness")
    entry = {
        "target": "claude",
        "action": "remedy-printed",
        "wrote": False,
        "framing": _CLAUDE_CONDITIONAL_FRAMING,
        "note": _CLAUDE_PRINT_ONLY_NOTE,
    }
    name, marketplace, _version = plugin_staleness.read_plugin_identity(repo_root)
    remedy = plugin_staleness.build_remedy(name, marketplace)
    if _RESTART_NOTE not in remedy:
        remedy = f"{remedy} {_RESTART_NOTE}"
    entry["remedy"] = remedy
    return entry


def apply_copilot_target(repo_root, copilot_home, dry_run=False):
    """The Copilot target: one delegated call to `harness_select.install_copilot`, which has a
    real parameter-level `dry_run` (verified against its signature for this task) -- so dry-run is
    honored by the writer itself, not simulated here. It returns its full destination list in both
    modes.

    A `copilot_home` that does not exist is "not installed" -- absence, not failure, and never an
    error: refreshing a home is a freshness operation, creating one is
    `harness_select install --harness copilot`'s job (the same absent-home pre-check `check` and
    the codex target apply)."""
    if copilot_home is None or not Path(copilot_home).is_dir():
        return {
            "target": "copilot",
            "action": "not installed",
            "wrote": False,
            "note": _NOT_INSTALLED_NOTE,
            "count": 0,
            "destinations": [],
        }

    harness_select_mod = _load_sibling("harness_select")
    destinations = harness_select_mod.install_copilot(copilot_home, repo_root=repo_root, dry_run=dry_run)
    return {
        "target": "copilot",
        "action": "would-install" if dry_run else "installed",
        "wrote": not dry_run,
        "note": _COPILOT_OVERWRITE_NOTE,
        "count": len(destinations),
        "destinations": [str(dest) for dest in destinations],
    }


def _codex_prompt_overwrites(harness_select_mod, repo_root, codex_home):
    """Read-only pre-scan of the prompts channel: which EXISTING `<codex_home>/prompts/*.md`
    destinations differ from what `install_codex` is about to write over them.

    This must run BEFORE `install_codex`, because that writer destroys the evidence -- its prompts
    loop reports every source as `"install"` whether the destination was absent, identical, or
    materially different, so its return value alone cannot tell a real overwrite from a no-op.

    Placeholder resolution is `_bundle_resolved_bytes` -- the SAME helper the T2 copilot
    comparator uses, because `install_copilot` and `install_codex` share the identical mechanism
    (`text.replace(PLACEHOLDER, str(repo_root))` on the UNRESOLVED repo root). No second
    substitution implementation exists in this file. Writes nothing; never raises on an unreadable
    destination (an unreadable file is reported as differing, the conservative answer)."""
    bundle_prompts = Path(repo_root) / "codex" / "prompts"
    if not bundle_prompts.is_dir():
        return []
    overwritten = []
    for src in sorted(bundle_prompts.glob("*.md")):
        dest = Path(codex_home) / "prompts" / src.name
        if not dest.is_file():
            continue  # absent destination is a fresh install, not an overwrite
        try:
            current = dest.read_bytes()
        except OSError:
            current = None
        if current != _bundle_resolved_bytes(harness_select_mod, src, repo_root):
            overwritten.append(str(dest))
    return overwritten


def apply_codex_target(repo_root, codex_home, dry_run=False):
    """The Codex target: one delegated call to the LEGACY `harness_select.install_codex` (PLAN.md
    D3 -- the modern `--components` / `--refresh-managed` setup surface stays
    `harness_select.py`'s own CLI). It has a real parameter-level `dry_run` and returns
    `(destination, action)` tuples with `action` in {"install", "up-to-date", "skip-differs"}.

    `install_codex`'s two channels have DIFFERENT contracts, and this report states both rather
    than flattening them (PLAN.md D3(b) as corrected at the P2 review):

    - `<home>/prompts/*.md` OVERWRITE IN PLACE. The writer's prompts loop compares nothing: it
      reports every source as `"install"` and calls `write_text` unconditionally. These files are
      plugin-generated deprecated mirrors, so that behavior stays -- but it is never reported as
      preservation. `_codex_prompt_overwrites` pre-scans which existing destinations actually
      differ, and every one of them is listed and labeled in the report.
    - `<home>/AGENTS.md` and `<home>/skills/<name>/` are user-editable and NO-CLOBBER: a differing
      destination yields `skip-differs`, is never overwritten, and is listed with
      `_CODEX_SKIP_DIFFERS_NOTE`. That "preserved" wording is emitted ONLY when something actually
      was preserved.

    Coverage limit (`_CODEX_COVERAGE_NOTE`, reported in both the human card and JSON): project-
    scope agent TOMLs and the modern `plugin` component that `check`'s `doctor_codex` reports on
    are outside this writer's reach entirely, so a clean apply here does not mean a clean codex
    check. The modern remedy is printed, never executed.

    Nothing here forces or deletes anything. Absent home -> "not installed", matching the
    pre-check `check`'s codex section already makes (NOTES.md's T3 entry: nothing in this engine
    plans or performs an install against a home that is not there)."""
    base = {
        "target": "codex",
        "covers": list(_CODEX_COVERS),
        "not_covered": list(_CODEX_NOT_COVERED),
        "coverage_limit": _CODEX_COVERAGE_NOTE,
    }
    if codex_home is None or not Path(codex_home).is_dir():
        return dict(
            base,
            action="not installed",
            wrote=False,
            note=_NOT_INSTALLED_NOTE,
            counts={},
            files=[],
            skip_differs=[],
            prompts_overwritten=[],
        )

    harness_select_mod = _load_sibling("harness_select")
    # Pre-scan first -- install_codex overwrites the evidence.
    prompts_overwritten = _codex_prompt_overwrites(harness_select_mod, repo_root, codex_home)
    results = harness_select_mod.install_codex(codex_home, repo_root=repo_root, dry_run=dry_run)

    counts = {}
    files = []
    skip_differs = []
    for dest, action in results:
        counts[action] = counts.get(action, 0) + 1
        files.append({"path": str(dest), "action": action})
        if action == "skip-differs":
            skip_differs.append(str(dest))

    entry = dict(
        base,
        action="would-install" if dry_run else "installed",
        wrote=not dry_run,
        note=_CODEX_PROMPTS_OVERWRITE_NOTE,
        no_clobber_note=_CODEX_NO_CLOBBER_NOTE,
        counts=counts,
        files=files,
        skip_differs=skip_differs,
        prompts_overwritten=prompts_overwritten,
    )
    # "preserved" is a claim about a real event -- it appears only when one happened.
    if skip_differs:
        entry["preserved_note"] = _CODEX_SKIP_DIFFERS_NOTE
    return entry


def apply_mirrors_target(repo_root, dry_run=False):
    """The generated-mirror target: `sync_pricing_refs.sync(root)` (returns every mirror path it
    wrote) and `sync_codex_surfaces.sync(root, "build")` (writes every expected prompt and returns
    the names that were STALE beforehand -- i.e. the set that actually changed).

    Neither writer has a dry-run parameter, so dry-run delegates to their own read-only check
    counterparts instead -- `sync_pricing_refs.check(root)` and
    `sync_codex_surfaces.sync(root, "check")` -- the same two calls `build_data_section` makes.
    Reported counts are therefore honest in both modes: `pricing_written` is what a real run
    rewrites (byte-identical copies included), `codex_refreshed` is what actually differed."""
    sync_pricing_refs_mod = _load_sibling("sync_pricing_refs")
    sync_codex_surfaces_mod = _load_sibling("sync_codex_surfaces")

    if dry_run:
        pricing = [_relativize(p, repo_root) for p in sync_pricing_refs_mod.check(repo_root)]
        codex = list(sync_codex_surfaces_mod.sync(repo_root, "check"))
        return {
            "target": "mirrors",
            "action": "would-rewrite",
            "wrote": False,
            "note": "stale mirrors only -- a real run additionally rewrites in-sync copies byte-identically",
            "pricing_written": pricing,
            "codex_refreshed": codex,
        }

    pricing = [_relativize(p, repo_root) for p in sync_pricing_refs_mod.sync(repo_root)]
    codex = list(sync_codex_surfaces_mod.sync(repo_root, "build"))
    return {
        "target": "mirrors",
        "action": "rewritten",
        "wrote": True,
        "note": "pricing mirrors are rewritten unconditionally; codex prompts listed are the ones that differed",
        "pricing_written": pricing,
        "codex_refreshed": codex,
    }


def resolve_apply_targets(only):
    """Normalize `--only` into the canonical target order. `None`/empty means all four."""
    if not only:
        return list(APPLY_TARGETS)
    requested = set(only)
    return [name for name in APPLY_TARGETS if name in requested]


def run_apply(repo_root, copilot_home=None, codex_home=None, only=None, dry_run=False):
    """The pure engine behind `apply`. Runs each requested target's delegated writer and collects
    one result entry per target.

    Errors are SURFACED, never swallowed: a writer that raises (e.g. `install_copilot`'s
    `FileNotFoundError` for an absent repo bundle) is caught per target only so the remaining
    targets still report, and is recorded verbatim in that target's `error` field and in the
    top-level `errors` list -- which drives `status: "error"` and exit 1. A run in which every
    target had nothing to do is still exit 0."""
    targets = resolve_apply_targets(only)
    results = {}
    errors = []

    for name in targets:
        try:
            if name == "claude":
                results[name] = apply_claude_target(repo_root)
            elif name == "copilot":
                results[name] = apply_copilot_target(repo_root, copilot_home, dry_run=dry_run)
            elif name == "codex":
                results[name] = apply_codex_target(repo_root, codex_home, dry_run=dry_run)
            else:
                results[name] = apply_mirrors_target(repo_root, dry_run=dry_run)
        except Exception as exc:  # surfaced below, never silently dropped
            message = f"{type(exc).__name__}: {exc}"
            results[name] = {"target": name, "action": "error", "wrote": False, "error": message}
            errors.append(f"{name}: {message}")

    return {
        "dry_run": bool(dry_run),
        "targets": targets,
        "results": results,
        "errors": errors,
        "status": "error" if errors else "ok",
        "exit": EXIT_ERROR if errors else EXIT_OK,
    }


def _render_apply_claude(entry):
    lines = ["## claude", f"action: {entry['action']}"]
    if entry.get("error"):
        lines.append(f"error: {entry['error']}")
        return "\n".join(lines)
    lines.append(entry["framing"])
    lines.append(f"remedy: {entry.get('remedy')}")
    lines.append(f"note: {entry['note']}")
    return "\n".join(lines)


def _render_apply_copilot(entry):
    lines = ["## copilot", f"action: {entry['action']}"]
    if entry.get("error"):
        lines.append(f"error: {entry['error']}")
        return "\n".join(lines)
    lines.append(f"note: {entry['note']}")
    lines.append(f"destinations: {entry['count']}")
    for dest in entry["destinations"]:
        lines.append(f"  {dest}")
    return "\n".join(lines)


def _render_apply_codex(entry):
    lines = ["## codex", f"action: {entry['action']}"]
    if entry.get("error"):
        lines.append(f"error: {entry['error']}")
        return "\n".join(lines)
    if entry["action"] == "not installed":
        lines.append(f"note: {entry['note']}")
        lines.append(entry["coverage_limit"])
        return "\n".join(lines)

    counts = entry.get("counts", {})
    order = ("install", "up-to-date", "skip-differs")
    lines.append("  ".join(f"{state}: {counts.get(state, 0)}" for state in order))

    # Channel 1 -- prompts: overwrite in place, every real overwrite named.
    lines.append(f"note: {entry['note']}")
    overwritten = entry.get("prompts_overwritten", [])
    label = _CODEX_PROMPT_OVERWRITE_LABEL if entry["wrote"] else _CODEX_PROMPT_OVERWRITE_LABEL_DRY
    lines.append(f"prompts differing before this run: {len(overwritten)}")
    for path in overwritten:
        lines.append(f"  {path}")
        lines.append(f"    {label}")

    # Channel 2 -- AGENTS.md + skills: no-clobber. The "preserved" wording appears only when
    # something actually was preserved.
    lines.append(f"note: {entry['no_clobber_note']}")
    skip_differs = entry.get("skip_differs", [])
    if skip_differs:
        for path in skip_differs:
            lines.append(f"  {path}")
            lines.append(f"    {_CODEX_SKIP_DIFFERS_NOTE}")

    lines.append(entry["coverage_limit"])
    return "\n".join(lines)


def _render_apply_mirrors(entry):
    lines = ["## mirrors", f"action: {entry['action']}"]
    if entry.get("error"):
        lines.append(f"error: {entry['error']}")
        return "\n".join(lines)
    lines.append(f"note: {entry['note']}")
    lines.append(f"pricing mirrors: {len(entry['pricing_written'])}")
    for path in entry["pricing_written"]:
        lines.append(f"  {path}")
    lines.append(f"codex prompt mirrors: {len(entry['codex_refreshed'])}")
    for name in entry["codex_refreshed"]:
        lines.append(f"  codex/prompts/{name}")
    return "\n".join(lines)


_APPLY_RENDERERS = {
    "claude": _render_apply_claude,
    "copilot": _render_apply_copilot,
    "codex": _render_apply_codex,
    "mirrors": _render_apply_mirrors,
}


def render_apply_report(result):
    """Render a `run_apply()` result as a human-readable report."""
    mode = "dry-run -- nothing was written" if result["dry_run"] else "apply"
    lines = [
        "# harness-update apply",
        f"mode: {mode}",
        "targets: " + ", ".join(result["targets"]),
        "",
    ]
    for name in result["targets"]:
        lines.append(_APPLY_RENDERERS[name](result["results"][name]))
        lines.append("")
    if result["errors"]:
        lines.append("verdict: errors -- " + "; ".join(result["errors"]))
    elif result["dry_run"]:
        lines.append(f"verdict: dry-run complete -- nothing written; {_APPLY_RESIDUAL_DRIFT_CAVEAT}")
    else:
        lines.append(f"verdict: apply complete -- {_APPLY_RESIDUAL_DRIFT_CAVEAT}")
    lines.append(f"status: {result['status']}")
    lines.append(f"exit: {result['exit']}")
    return "\n".join(lines)


def cmd_apply(args):
    result = run_apply(
        args.repo_root,
        copilot_home=args.copilot_home,
        codex_home=args.codex_home,
        only=args.only,
        dry_run=args.dry_run,
    )
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render_apply_report(result))
    return result["exit"]


# ---- demo: a synthetic, self-cleaning smoke -- the CLAUDE.md run-line for this engine ----------
#
# Everything below builds and tears down its OWN tempfile.mkdtemp() tree; it never receives or
# derives a real repo path or a real home directory. The canonical Codex agent roster
# (`_DEMO_CODEX_AGENT_ROSTER`) is a literal copy of `harness_select._validate_agent_sources`'s
# hardcoded expected set -- that function exposes no importable constant for it, so any caller
# needing a VALID synthetic codex bundle (this demo, and tests/test_codex_setup.py's own
# fixtures) has to know the four names directly. If harness_select's canonical roster ever
# changes, this fixture needs updating too.

_DEMO_CODEX_AGENT_ROSTER = ("kit-implementer", "kit-verifier", "phase-reviewer", "repo-explorer")

# Fixture-local synthetic dates only -- never a real pricing snapshot date. Deliberately far in
# the past so the "pricing ages" lines in the fresh demo card show a real (>60d) age flag,
# proving that informational path renders without ever counting as drift.
_DEMO_PRICING_DATES = {
    "data/pricing.json": "2020-01-01",
    "data/pricing.copilot.json": "2020-01-02",
    "data/pricing.codex.json": "2020-01-03",
}


def _demo_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _write_demo_repo(root, skill_stems, placeholder):
    """Write every SOURCE file `run_check` (across all four sections) needs to render a
    genuinely fresh card, under `root` only. `skill_stems` is `sync_codex_surfaces.SKILL_STEMS`
    and `placeholder` is `harness_select.PLACEHOLDER` -- both passed in by the caller, reused by
    import, never hardcoded here (this file defines no second `{{`-style placeholder literal)."""
    # Claude plugin identity (T1 shape) -- any name/version works, plugin_staleness has no
    # hardcoded expectation. --installed-manifest is left pointing at a path that is never
    # created, so the claude section renders "not installed" (absence, not drift).
    _demo_write(root / ".claude-plugin" / "plugin.json", json.dumps({"name": "demo-plugin", "version": "0.0.1"}))
    _demo_write(root / ".claude-plugin" / "marketplace.json", json.dumps({"name": "demo-market"}))

    # Copilot bundle (T2 shape).
    _demo_write(
        root / "copilot" / ".github" / "agents" / "demo-route.agent.md",
        f"---\nname: demo-route\ndescription: synthetic demo agent\n---\n\nRepo: {placeholder}\n",
    )

    # Codex plugin identity: harness_select._validate_plugin_metadata hardcodes the expected
    # name "polytropos" for both the manifest and the marketplace entry (no importable
    # constant), so this fixture must use that literal name to validate cleanly -- not a
    # hardcoded price/model-id, just matching the reused module's own fixed expectation (the
    # same convention tests/test_codex_setup.py's own fixture uses).
    _demo_write(
        root / ".codex-plugin" / "plugin.json",
        json.dumps({"name": "polytropos", "version": "0.0.1", "skills": "./codex/skills/"}),
    )
    _demo_write(
        root / ".agents" / "plugins" / "marketplace.json",
        json.dumps({"plugins": [{"name": "polytropos", "source": {"source": "local", "path": "./"}}]}),
    )
    for name in _DEMO_CODEX_AGENT_ROSTER:
        _demo_write(
            root / "codex" / "agents" / f"{name}.toml",
            f'name = "{name}"\n'
            f'description = "Synthetic demo agent {name}"\n'
            'developer_instructions = """Synthetic demo instructions."""\n',
        )
    for stem in skill_stems:
        _demo_write(
            root / "codex" / "skills" / stem / "SKILL.md",
            f"---\nname: {stem}\ndescription: synthetic demo skill {stem}\n---\n\nSynthetic body for {stem}.\n",
        )
    _demo_write(root / "codex" / "AGENTS.md", f"Synthetic demo guidance. Repo: {placeholder}\n")

    # Pricing files + docs snapshot labels (T5 data section).
    for rel, cached_date in _DEMO_PRICING_DATES.items():
        _demo_write(root / rel, json.dumps({"cached_date": cached_date, "models": {}}, indent=2))
    _demo_write(root / "README.md", f"Demo pricing snapshot cached {_DEMO_PRICING_DATES['data/pricing.json']}.\n")
    _demo_write(
        root / "docs" / "COPILOT-HARNESS.md",
        f"Demo copilot pricing snapshot cached {_DEMO_PRICING_DATES['data/pricing.copilot.json']}.\n",
    )

    # skills/route, skills/fable-check: sync_pricing_refs' mirror targets.
    (root / "skills" / "route").mkdir(parents=True, exist_ok=True)
    (root / "skills" / "fable-check").mkdir(parents=True, exist_ok=True)


def build_demo_tree():
    """Build a synthetic `tempfile.mkdtemp()` tree with everything `run_check` needs to render a
    genuinely fresh four-section card: Claude plugin identity, a Copilot bundle installed into
    its own fake home, a Codex bundle installed into its own fake home, and pricing files +
    docs snapshot labels + generated mirrors all in sync. Every write in this function and
    everything it calls lands under the `root` this function creates or a fake home created as
    a subdirectory of it -- never a real repo path, never a real home directory. The caller owns
    cleanup (`shutil.rmtree(root)`). Returns `(root, copilot_home, codex_home,
    installed_manifest)`; `installed_manifest` is a path that is never created.

    The root is `.resolve()`d (T6). `tempfile.mkdtemp()` hands back a symlinked path on macOS
    (`/var` -> `/private/var`), and the two Codex writers disagree about which form to substitute
    for the placeholder: the modern `plan_codex_setup` path resolves the repo root first
    (`harness_select._resolved_bytes`) while the legacy `install_codex` substitutes the
    unresolved `str(repo_root)` it was handed. Handing both a root that is already resolved makes
    them produce identical bytes, which is what lets `apply`'s legacy codex writer leave a tree
    that `check`'s modern `doctor_codex` still calls up-to-date. The real repo root
    (`Path(__file__).resolve()...`) is resolved for the same reason, so this matches production."""
    root = Path(tempfile.mkdtemp(prefix="harness-update-demo-")).resolve()
    copilot_home = root / "copilot-home"
    codex_home = root / "codex-home"
    installed_manifest = root / "installed_plugins.json"

    harness_select_mod = _load_sibling("harness_select")
    sync_pricing_refs_mod = _load_sibling("sync_pricing_refs")
    sync_codex_surfaces_mod = _load_sibling("sync_codex_surfaces")

    _write_demo_repo(root, sync_codex_surfaces_mod.SKILL_STEMS, harness_select_mod.PLACEHOLDER)

    # Materialize every generated mirror and install both harness homes fully -- all delegated
    # to the reused modules' own writers, exactly as apply() will do in a later task.
    sync_pricing_refs_mod.sync(root)
    sync_codex_surfaces_mod.sync(root, "build")
    harness_select_mod.install_copilot(copilot_home, repo_root=root)
    plan = harness_select_mod.plan_codex_setup(
        root,
        codex_home,
        components=harness_select_mod.CODEX_COMPONENTS,
        agent_scope="project",
        legacy_copy=True,
        refresh_managed=False,
    )
    harness_select_mod.apply_codex_plan(plan)

    return root, copilot_home, codex_home, installed_manifest


def seed_demo_drift(root, copilot_home):
    """Mutate a `build_demo_tree()` result IN PLACE to introduce drift of both kinds:

    - drift `apply` CAN fix, because a delegated writer owns it -- an edited Copilot destination
      file (`install_copilot` overwrites it) and a corrupted generated pricing mirror
      (`sync_pricing_refs.sync` rewrites it);
    - drift `apply` deliberately CANNOT fix -- a stale docs snapshot label (README.md no longer
      names `data/pricing.json`'s `cached_date`). Pricing NUMBERS and docs snapshot TABLES are
      never auto-edited by this engine (PLAN.md out-of-scope fence, CLAUDE.md's "update them only
      together" rule): they need a human refresh from the source.

    Only ever writes under `root` / `copilot_home`, both demo-owned temp paths."""
    readme = root / "README.md"
    readme.write_text(readme.read_text().replace(_DEMO_PRICING_DATES["data/pricing.json"], "0000-00-00"))
    installed_agent = copilot_home / "agents" / "demo-route.agent.md"
    installed_agent.write_text(installed_agent.read_text() + "\n# tampered by demo\n")
    mirror = root / "skills" / "route" / "references" / "pricing.json"
    mirror.write_text('{"corrupted-by-demo": true}\n')


def run_demo():
    """CLAUDE.md run-line smoke (`python3 bin/harness_update.py demo`): from one synthetic,
    self-cleaning temp tree, render a genuinely fresh four-section card, a drifted card, a
    `--dry-run` apply report, a real apply report, and the follow-up check card. Touches no real
    repo and no real home directory. Exit code is always 0 -- this is a smoke demonstrating every
    render path, not a real freshness verdict.

    The final card deliberately still reports `data` drift: the seeded stale docs snapshot label
    is exactly the class of staleness `apply` refuses to auto-fix."""
    root, copilot_home, codex_home, installed_manifest = build_demo_tree()
    try:
        fresh_card = render_card(run_check(root, installed_manifest, copilot_home=copilot_home, codex_home=codex_home))
        seed_demo_drift(root, copilot_home)
        drifted_card = render_card(
            run_check(root, installed_manifest, copilot_home=copilot_home, codex_home=codex_home)
        )
        dry_run_report = render_apply_report(
            run_apply(root, copilot_home=copilot_home, codex_home=codex_home, dry_run=True)
        )
        apply_report = render_apply_report(
            run_apply(root, copilot_home=copilot_home, codex_home=codex_home)
        )
        after_card = render_card(
            run_check(root, installed_manifest, copilot_home=copilot_home, codex_home=codex_home)
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("=== demo: fresh synthetic tree ===")
    print(fresh_card)
    print()
    print("=== demo: seeded drift ===")
    print(drifted_card)
    print()
    print("=== demo: apply --dry-run (writes nothing) ===")
    print(dry_run_report)
    print()
    print("=== demo: apply ===")
    print(apply_report)
    print()
    print("=== demo: check after apply (docs snapshot label is never auto-fixed) ===")
    print(after_card)
    print()
    print(
        "demo process exit: 0 -- this smoke always exits 0. Any `exit:` line above is the value "
        "that CARD would have returned, not this process's exit code."
    )
    return EXIT_OK


def cmd_demo(args):
    return run_demo()


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Check and refresh this repo's Claude/Copilot/Codex installs and generated data "
            "mirrors -- read-only unless the apply subcommand is invoked, and never a write "
            "under ~/.claude in any subcommand (that remedy is printed, never executed)."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser(
        "check", help="read-only freshness check across claude/copilot/codex/data"
    )
    check_parser.add_argument(
        "--repo-root", default=DEFAULT_REPO_ROOT, help="repo directory to check from (default: this repo)"
    )
    check_parser.add_argument(
        "--installed-manifest",
        default=DEFAULT_INSTALLED_MANIFEST,
        help="path to installed_plugins.json (default: ~/.claude/plugins/installed_plugins.json)",
    )
    check_parser.add_argument(
        "--copilot-home", default=DEFAULT_COPILOT_HOME, help="Copilot home directory (default: ~/.copilot)"
    )
    check_parser.add_argument(
        "--codex-home", default=DEFAULT_CODEX_HOME, help="Codex home directory (default: ~/.codex)"
    )
    check_parser.add_argument("--json", action="store_true", help="machine-readable output")
    check_parser.set_defaults(func=cmd_check)

    apply_parser = subparsers.add_parser(
        "apply",
        help=(
            "refresh the writable targets only -- Copilot home, Codex home (prompts overwrite in place; "
            "AGENTS.md/skills no-clobber), repo "
            "generated mirrors. The Claude remedy is printed, never executed."
        ),
    )
    apply_parser.add_argument(
        "--repo-root", default=DEFAULT_REPO_ROOT, help="repo directory to apply from (default: this repo)"
    )
    apply_parser.add_argument(
        "--copilot-home", default=DEFAULT_COPILOT_HOME, help="Copilot home directory (default: ~/.copilot)"
    )
    apply_parser.add_argument(
        "--codex-home", default=DEFAULT_CODEX_HOME, help="Codex home directory (default: ~/.codex)"
    )
    apply_parser.add_argument(
        "--dry-run", action="store_true", help="print the would-do plan; no target writes anything"
    )
    apply_parser.add_argument(
        "--only",
        action="append",
        choices=list(APPLY_TARGETS),
        help="restrict apply to the named target(s) (repeatable; default: all four)",
    )
    apply_parser.add_argument("--json", action="store_true", help="machine-readable output")
    apply_parser.set_defaults(func=cmd_apply)

    demo_parser = subparsers.add_parser(
        "demo", help="synthetic check/apply smoke -- temp tree only, no real repo or home, exit 0 always"
    )
    demo_parser.set_defaults(func=cmd_demo)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
