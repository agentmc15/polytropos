#!/usr/bin/env python3
"""Compare the LIVE-installed polytropos plugin against this repo's source, file by file.

Why this exists (incident, 2026-07-24): the plugin installed at user scope was 18 days and 22
commits behind this repo. The installer's own update flow reported the install already current
-- correctly, because that check compares only plugin.json's "version" string; it never hashes
content. So the running skills answered from stale instructions (an already-fixed CLAUDE.md
placement rule, a pricing.json missing a model, a cached_date three weeks old) with no warning
at the point of use. `bin/context_weight.py` (a sibling script landing in this same kit)
measures what fills a context window; this script answers a different question -- is the code
answering you the code in this repo? -- so it is a deliberately separate file, never a
subcommand of that one.

Resolution mirrors the real installer: read `<home>/.claude/plugins/installed_plugins.json`,
look up `plugins["<name>@<marketplace>"][0]`, and take its `installPath`. The name and
marketplace come from THIS repo's own `.claude-plugin/plugin.json` / `marketplace.json` --
never hardcoded -- so the same engine works unmodified against any plugin repo shaped like
this one. The version directory inside installPath changes on every bump (e.g. 0.1.0 ->
0.2.0), so it is never assumed or hardcoded either -- only ever read from the manifest.

Compared per file: `skills/*/SKILL.md`, `data/pricing*.json`, `CLAUDE.md`, `bin/*.py`, each
reported `identical` / `DIFFERS` / `missing`. Also reported: the repo's plugin.json "version"
vs the installed record's "version", and -- only when a `.git` directory is present in the
repo -- the current commit (read directly from `.git/HEAD` and its ref file or packed-refs;
no `git` binary is invoked for that) vs the manifest's recorded "gitCommitSha". The installed
copy itself carries no `.git` directory, so that half of the comparison degrades to "not
available" rather than crashing whenever it cannot be made.

Three additions answer what the per-glob compare could not (2026-09-25):
  - `--full` compares EVERY tracked file, not just the globs above, with counts per top-level
    directory, and lists what the installed copy carries that git does not track -- the
    installer ignores `.gitignore`, so a local settings file or a byte-compiled cache rides
    along. With a whole-tree answer in hand a SHA STALE result is settled, not guessed: every
    tracked file identical is IN SYNC (only the recorded commit id differs), anything else is
    DRIFTED. The engine functions take the tracked list as an argument and never ask git
    themselves; the CLI reads it from `--tracked-file`, or else asks `git ls-files` through
    `bin/release_gate.py`'s read-only git verbs, which run under `bin/proc_runner.py`.
  - The card lists the other version directories in the plugin's cache folder, which no update
    ever removes, with one `rm -rf` line each. Those lines are printed for a human to run; this
    script never runs them.
  - `--loaded DIR` answers what a restart leaves open: is the session running the copy that is
    installed? DIR is the directory the session loaded -- `${CLAUDE_PLUGIN_ROOT}` in a skill.

Strictly read-only: this script never writes anything and never runs a harness CLI; the one
process it can start is that read-only `git ls-files`, and only for `--full`. When
installed, one of three statuses results -- decided primarily from the file-by-file comparison,
with version and git HEAD as secondary signals; a file difference always wins and always means
DRIFTED:
  - IN SYNC     -- version matches, every compared file is identical, and (when comparable) the
                   recorded git HEAD matches too.
  - SHA STALE   -- version matches and every compared file is identical, but the manifest's
                   recorded git commit differs from this repo's HEAD. A squash-merge or rebase
                   does this to an unchanged tree, and so does any commit touching only files
                   outside the compared set (a docs-only change). The compared content is
                   current, so it is NOT actionable -- but it is a statement about the compared
                   files only, never about the whole tree.
  - DRIFTED     -- any compared file differs or is missing, or the version string differs: an
                   actual install difference.
Only a DRIFTED result PRINTS the two-step remedy text (bump the version, then re-run the
installer's own marketplace-refresh and per-plugin update steps); a human reads that text and
decides whether and when to run them -- this script never runs them itself. A SHA STALE result
instead prints a plain-language note that no action is required. Exit 0 for IN SYNC, SHA STALE,
and "not installed" (no matching manifest entry); exit 3 for DRIFTED (this repo's doctor/sync-
style exit-3 precedent) -- never a traceback.

Engine has ZERO real-home lookups via the stdlib home helper: every entry point takes
`--installed-manifest PATH` and `--repo DIR` explicitly, so every test drives it entirely from
temp fixtures. The one default real-home path (`~/.claude/plugins/installed_plugins.json`,
used only as a CLI convenience default) is built with `os.path.expanduser`, matching the
precedent already used for default real homes elsewhere in this repo's bin/ (statusline.py,
agent_tracker.py) rather than that stdlib helper.
"""

import argparse
import importlib.util
import json
import os
import re
import shlex
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent

# CLI convenience default only -- every pure function below takes the manifest path as an
# explicit argument, and no function in this module ever resolves a real home on its own.
DEFAULT_INSTALLED_MANIFEST = os.path.expanduser("~/.claude/plugins/installed_plugins.json")

COMPARE_GLOBS = ("skills/*/SKILL.md", "data/pricing*.json", "CLAUDE.md", "bin/*.py")

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_DRIFTED = 3

# The remedy text is pinned verbatim by the task brief. Built from two halves so that the
# literal CLI invocation text never sits whole on one source line in this file -- this script
# only ever prints these commands as a string; it never executes them.
_REMEDY_CLI_A = "claude plugin marketplace update {marketplace} && claude plugin"
_REMEDY_CLI_B = " update {name}@{marketplace} (restart to apply)"
# A first install is its own verb: `update` refuses a plugin that is not installed.
_INSTALL_CLI_A = "claude plugin"
_INSTALL_CLI_B = " install {name}@{marketplace} (restart to apply)"

# Printed only for a SHA-STALE result. Deliberately carries no CLI invocation and no mention of
# a version "bump" as an action to take -- printing the DRIFTED remedy here would be the false
# alarm this status exists to remove: nothing that is compared needs copying, so nothing should
# look actionable.
#
# IT CLAIMS ONLY WHAT WAS COMPARED. The check reads COMPARE_GLOBS and nothing else, so the note
# names that set (derived from the constant, never retyped) and says the rest of the tree was
# not looked at. It used to say the install was "byte-identical to this repo's tracked files"
# and that a squash-merge or rebase "is exactly what happened here". Neither was something this
# script could know: on 2026-09-21 a docs-only commit produced SHA STALE while two tracked files
# under `docs/` genuinely differed from the installed copy. The status was right and the
# sentence was not. A differing recorded commit says the history moved, never why.
SHA_STALE_NOTE = (
    "every file this check compares (" + ", ".join(COMPARE_GLOBS) + ") is identical between "
    "this repo and the installed copy -- only the git commit id recorded at install time "
    "differs. Files outside that set are not compared and may differ. A commit that touches "
    "only uncompared files (documentation, for instance) produces this result, and so does a "
    "squash-merge or rebase that rewrites commit ids for an unchanged tree; this check cannot "
    "tell which happened. No action is required for the compared files -- the recorded id "
    "will refresh on its own the next time the plugin version changes."
)


def _plugin_key(name, marketplace):
    return f"{name}@{marketplace}"


def read_plugin_identity(repo_dir):
    """Read <repo_dir>/.claude-plugin/plugin.json and marketplace.json. Returns
    (name, marketplace, version). These are repo-owned files, always expected to exist for a
    repo shaped like this one, so a missing/malformed file is allowed to raise -- unlike the
    installed side (resolve_installed_entry), which must degrade gracefully instead."""
    repo_dir = Path(repo_dir)
    plugin_data = json.loads((repo_dir / ".claude-plugin" / "plugin.json").read_text())
    marketplace_data = json.loads((repo_dir / ".claude-plugin" / "marketplace.json").read_text())
    return plugin_data["name"], marketplace_data["name"], plugin_data["version"]


def resolve_installed_entry(installed_manifest_path, plugin_key):
    """Return the first install-record dict for `plugin_key` from installed_plugins.json, or
    None if the manifest file is absent, unreadable, malformed, or carries no entry for this
    key. Never raises -- absence is a normal, expected outcome ("not installed"), not an error
    condition."""
    path = Path(installed_manifest_path)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    plugins = data.get("plugins") if isinstance(data, dict) else None
    if not isinstance(plugins, dict):
        return None
    entries = plugins.get(plugin_key)
    if not isinstance(entries, list) or not entries:
        return None
    first = entries[0]
    return first if isinstance(first, dict) else None


def read_git_head_sha(repo_dir):
    """Best-effort current commit sha for repo_dir, read directly from `.git/HEAD` and its ref
    file or `packed-refs`. The `git` binary is never invoked. Returns None if there is no
    `.git` directory or the ref chain cannot be resolved; never raises."""
    git_dir = Path(repo_dir) / ".git"
    head_file = git_dir / "HEAD"
    if not git_dir.is_dir() or not head_file.is_file():
        return None
    try:
        head = head_file.read_text().strip()
    except OSError:
        return None
    if not head:
        return None
    if head.startswith("ref:"):
        ref = head.split(":", 1)[1].strip()
        ref_path = git_dir / ref
        if ref_path.is_file():
            try:
                sha = ref_path.read_text().strip()
            except OSError:
                return None
            return sha or None
        packed = git_dir / "packed-refs"
        if packed.is_file():
            try:
                packed_text = packed.read_text()
            except OSError:
                return None
            for line in packed_text.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("^"):
                    continue
                parts = line.split()
                if len(parts) == 2 and parts[1] == ref:
                    return parts[0]
        return None
    # Detached HEAD: the file holds the sha directly.
    hex_chars = set("0123456789abcdefABCDEF")
    if len(head) >= 7 and all(c in hex_chars for c in head):
        return head
    return None


def _glob_relative(base_dir, patterns):
    if not base_dir:
        return set()
    base = Path(base_dir)
    if not base.is_dir():
        return set()
    rels = set()
    for pattern in patterns:
        for p in base.glob(pattern):
            if p.is_file():
                rels.add(p.relative_to(base).as_posix())
    return rels


def compare_files(repo_dir, install_dir):
    """Compare every file matched by COMPARE_GLOBS between repo_dir and install_dir. install_dir
    may be None, empty, or a non-existent path -- treated as carrying no files. Returns a list
    of {"path": rel, "status": "identical"|"DIFFERS"|"missing"} sorted by path. "missing"
    covers a file present on only one side, in either direction."""
    repo_files = _glob_relative(repo_dir, COMPARE_GLOBS)
    install_files = _glob_relative(install_dir, COMPARE_GLOBS)
    results = []
    for rel in sorted(repo_files | install_files):
        in_repo = rel in repo_files
        in_install = rel in install_files
        if in_repo and in_install:
            try:
                same = (Path(repo_dir) / rel).read_bytes() == (Path(install_dir) / rel).read_bytes()
            except OSError:
                same = False
            results.append({"path": rel, "status": "identical" if same else "DIFFERS"})
        else:
            results.append({"path": rel, "status": "missing"})
    return results


def update_command(name, marketplace):
    """The installer's refresh command line for this plugin, as TEXT for a human to run --
    shared by the remedy below and by `harness_update.py preflight`. Never executed here."""
    return (_REMEDY_CLI_A + _REMEDY_CLI_B).format(name=name, marketplace=marketplace)


def install_command(name, marketplace):
    """The installer's first-install command line, as TEXT for a human to run -- for a plugin
    with no install record, where `update_command` would be refused. Never executed here."""
    return (_INSTALL_CLI_A + _INSTALL_CLI_B).format(name=name, marketplace=marketplace)


def build_remedy(name, marketplace):
    """The pinned actionable remedy line, filled in from this repo's own identity -- never a
    hardcoded plugin or marketplace name."""
    return ('stale install — bump "version" in .claude-plugin/plugin.json, then: '
            + update_command(name, marketplace))


def check_staleness(repo_dir, installed_manifest_path):
    """The pure engine: compare the repo at repo_dir against the plugin install recorded in
    installed_manifest_path. Returns a fully JSON-serializable result dict. Never prints, never
    writes, never raises for any of the three normal outcomes (not installed / in sync /
    drifted)."""
    name, marketplace, repo_version = read_plugin_identity(repo_dir)
    plugin_key = _plugin_key(name, marketplace)
    repo_git_sha = read_git_head_sha(repo_dir)

    entry = resolve_installed_entry(installed_manifest_path, plugin_key)
    if entry is None:
        return {
            "schema_version": 1,
            "plugin_name": name,
            "marketplace": marketplace,
            "plugin_key": plugin_key,
            "repo_version": repo_version,
            "repo_git_sha": repo_git_sha,
            "installed": False,
            "installed_manifest": str(installed_manifest_path),
            "drifted": False,
            "exit_code": EXIT_OK,
        }

    install_path = entry.get("installPath")
    installed_version = entry.get("version")
    installed_git_sha = entry.get("gitCommitSha")

    version_match = repo_version == installed_version
    git_comparable = bool(repo_git_sha) and bool(installed_git_sha)
    git_match = (repo_git_sha == installed_git_sha) if git_comparable else None

    files = compare_files(repo_dir, install_path)
    files_diff_count = sum(1 for f in files if f["status"] != "identical")

    # Status priority: the file comparison is the PRIMARY signal -- a file difference always
    # wins and always means DRIFTED, no matter what version or HEAD say. Version is checked
    # next (a version-string difference is a real install difference too). Only once both of
    # those are clean does a git-HEAD-only mismatch matter, and when it's the sole difference
    # it means the content is current and only the recorded commit id is stale -- what a
    # squash-merge or rebase does to an unchanged tree -- so it is SHA STALE, not DRIFTED.
    if files_diff_count or not version_match:
        status = "DRIFTED"
    elif git_comparable and not git_match:
        status = "SHA STALE"
    else:
        status = "IN SYNC"

    drifted = status == "DRIFTED"

    result = {
        "schema_version": 1,
        "plugin_name": name,
        "marketplace": marketplace,
        "plugin_key": plugin_key,
        "repo_version": repo_version,
        "repo_git_sha": repo_git_sha,
        "installed": True,
        "install_path": install_path,
        "installed_version": installed_version,
        "installed_git_sha": installed_git_sha,
        "version_match": version_match,
        "git_comparable": git_comparable,
        "git_match": git_match,
        "files": files,
        "files_diff_count": files_diff_count,
        "status": status,
        "drifted": drifted,
        "exit_code": EXIT_DRIFTED if drifted else EXIT_OK,
    }
    if status == "DRIFTED":
        result["remedy"] = build_remedy(name, marketplace)
    elif status == "SHA STALE":
        result["note"] = SHA_STALE_NOTE
    return result


# ---- the cache's other versions, the whole tree, and what a session loaded ---------------------

#: A version directory under `<cache>/<marketplace>/<plugin>/`: dotted digits, optionally a
#: pre-release or build suffix. A removal line is printed only for a directory this recognises.
_VERSION_DIR_RE = re.compile(r"\A\d+(?:\.\d+)*(?:[-+][0-9A-Za-z.-]+)?\Z")

#: Printed when the whole-tree compare settles a SHA STALE result as current.
COMMIT_ID_ONLY_NOTE = (
    "every tracked file is identical between this repo and the installed copy; only the git "
    "commit id recorded at install time differs, which a squash-merge, a rebase, or a commit "
    "that changed no file can each produce. No action is required."
)


def _version_key(name):
    return tuple(int(part) for part in re.match(r"\d+(?:\.\d+)*", name).group(0).split("."))


def superseded_versions(install_path, plugin_name, marketplace):
    """Every other version directory beside the active install, oldest first.

    Returns None unless `install_path` has the installer's shape,
    `<cache>/<marketplace>/<plugin>/<version>` -- so no removal line is ever printed for a
    layout this cannot vouch for -- and [] when the active version is the only one. Reads
    directory names only; never deletes."""
    if not install_path:
        return None
    active = Path(install_path)
    parent = active.parent
    if not active.name or parent.name != plugin_name or parent.parent.name != marketplace:
        return None
    if not parent.is_dir():
        return None
    others = [p for p in parent.iterdir()
              if p.is_dir() and p.name != active.name and _VERSION_DIR_RE.match(p.name)]
    return [str(p) for p in sorted(others, key=lambda p: _version_key(p.name))]


def prune_commands(paths):
    """One shell-quoted `rm -rf --` line per superseded version directory. PRINTED ONLY: nothing
    in this module deletes a file or runs these lines."""
    return [f"rm -rf -- {shlex.quote(p)}" for p in paths]


def _walk_files(base_dir):
    """Every file under base_dir as a POSIX relative path; git's own metadata is skipped."""
    if not base_dir or not Path(base_dir).is_dir():
        return set()
    base = Path(base_dir)
    rels = set()
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for filename in filenames:
            rels.add((Path(dirpath) / filename).relative_to(base).as_posix())
    return rels


def _top_level(rel):
    return rel.split("/", 1)[0] + "/" if "/" in rel else "(top level)"


def compare_tree(repo_dir, install_dir, tracked):
    """Compare EVERY tracked file, and list what the installed copy carries that git does not.

    `tracked` is the repo's tracked paths (repo-relative, POSIX), handed in by the caller -- this
    function never asks git. A tracked path absent from the working tree is reported under
    `missing_in_checkout` rather than as drift, because the installer copies the working tree,
    not the index. `by_dir` counts per top-level directory."""
    tracked = sorted(set(tracked))
    install_files = _walk_files(install_dir)
    repo = Path(repo_dir)
    install = Path(install_dir) if install_dir else None
    identical, differs, missing_install, missing_checkout = 0, [], [], []
    by_dir = {}

    def count(rel, key):
        bucket = by_dir.setdefault(_top_level(rel),
                                   {"identical": 0, "differs": 0, "missing": 0, "untracked": 0})
        bucket[key] += 1

    for rel in tracked:
        source = repo / rel
        if not source.is_file():
            missing_checkout.append(rel)
            continue
        if rel not in install_files:
            missing_install.append(rel)
            count(rel, "missing")
            continue
        try:
            same = source.read_bytes() == (install / rel).read_bytes()
        except OSError:
            same = False
        if same:
            identical += 1
            count(rel, "identical")
        else:
            differs.append(rel)
            count(rel, "differs")
    untracked = sorted(install_files - set(tracked))
    for rel in untracked:
        count(rel, "untracked")
    return {
        "tracked_total": len(tracked),
        "identical": identical,
        "differs": differs,
        "missing_from_install": missing_install,
        "missing_in_checkout": missing_checkout,
        "untracked_in_install": untracked,
        "by_dir": dict(sorted(by_dir.items())),
    }


def resolve_with_tree(result, tree):
    """Settle a check_staleness() result with a compare_tree() answer -> a new result dict.

    The one place the SHA STALE question is decided. The per-glob compare cannot see the rest
    of the tree, so on its own SHA STALE is a guess; with the whole tree compared, any tracked
    file that differs or is missing from the install is DRIFTED, and a tree with none is IN
    SYNC with `commit_id_only` set when the recorded commit is all that differs."""
    if not result.get("installed"):
        return dict(result)
    settled = dict(result)
    settled["tree"] = tree
    content_differs = bool(tree["differs"] or tree["missing_from_install"])
    settled.pop("remedy", None)
    settled.pop("note", None)
    if content_differs or result["files_diff_count"] or not result["version_match"]:
        settled["status"] = "DRIFTED"
        settled["remedy"] = build_remedy(result["plugin_name"], result["marketplace"])
    else:
        settled["status"] = "IN SYNC"
        if result.get("git_comparable") and not result.get("git_match"):
            settled["commit_id_only"] = True
            settled["note"] = COMMIT_ID_ONLY_NOTE
    settled["drifted"] = settled["status"] == "DRIFTED"
    settled["exit_code"] = EXIT_DRIFTED if settled["drifted"] else EXIT_OK
    return settled


LOADED_CURRENT = "current"
LOADED_RESTART = "restart needed"
LOADED_ELSEWHERE = "not the installed copy"


def check_loaded(plugin_root, installed_manifest_path):
    """After a restart: is the session running the copy that is installed?

    `plugin_root` is the directory the session loaded -- `${CLAUDE_PLUGIN_ROOT}` inside a skill.
    Three answers: `current` (it IS the recorded install path, at the recorded version);
    `restart needed` (it is another version directory in the same cache folder -- the session
    predates the update); `not the installed copy` (it lives somewhere else, as a
    `--plugin-dir` session does, so there is nothing a restart would change). Read-only."""
    root = Path(plugin_root)
    base = {"loaded_root": str(root), "installed_manifest": str(installed_manifest_path)}
    try:
        name, marketplace, loaded_version = read_plugin_identity(root)
    except (OSError, ValueError, KeyError):
        return {**base, "status": "not a plugin root", "exit_code": EXIT_DRIFTED,
                "note": f"{root} has no readable .claude-plugin/plugin.json and marketplace.json"}
    key = _plugin_key(name, marketplace)
    entry = resolve_installed_entry(installed_manifest_path, key)
    base.update({"plugin_key": key, "loaded_version": loaded_version})
    if entry is None:
        return {**base, "status": "not installed", "exit_code": EXIT_OK,
                "note": f"no install record for {key}; nothing to compare the session against"}
    install_path = entry.get("installPath") or ""
    installed_version = entry.get("version")
    base.update({"install_path": install_path, "installed_version": installed_version})
    real_root = os.path.realpath(root)
    real_install = os.path.realpath(install_path) if install_path else ""
    if real_root == real_install and loaded_version == installed_version:
        return {**base, "status": LOADED_CURRENT, "exit_code": EXIT_OK,
                "note": f"this session runs the installed copy, {installed_version}"}
    if real_install and Path(real_root).parent == Path(real_install).parent:
        return {**base, "status": LOADED_RESTART, "exit_code": EXIT_DRIFTED,
                "note": (f"this session loaded {loaded_version} from {root}; the installed copy is "
                         f"{installed_version} at {install_path}. Restart Claude Code, then check "
                         "again.")}
    return {**base, "status": LOADED_ELSEWHERE, "exit_code": EXIT_OK,
            "note": (f"this session loaded the plugin from {root}, not from the installed cache "
                     "(a --plugin-dir session); a restart would not change which copy it runs")}


def render_markdown(result):
    """Render a check_staleness() result as a markdown card."""
    lines = [f"## plugin staleness — {result['plugin_key']}", ""]

    if not result["installed"]:
        lines.append(
            f"not installed — no entry for `{result['plugin_key']}` in "
            f"`{result['installed_manifest']}`. Nothing to compare."
        )
        return "\n".join(lines)

    v_mark = "match" if result["version_match"] else "MISMATCH"
    lines.append(
        f"version: repo `{result['repo_version']}` vs installed "
        f"`{result['installed_version']}` — {v_mark}"
    )

    if result["git_comparable"]:
        g_mark = "match" if result["git_match"] else "MISMATCH"
        lines.append(
            f"git HEAD: repo `{result['repo_git_sha']}` vs installed "
            f"`{result['installed_git_sha']}` — {g_mark}"
        )
    elif result["repo_git_sha"] is None:
        lines.append("git HEAD: not available — repo has no `.git` directory")
    else:
        lines.append("git HEAD: not available — install record carries no `gitCommitSha`")

    lines.append(f"install path: {result['install_path']}")
    lines.append("")
    lines.append("files:")
    if result["files"]:
        for f in result["files"]:
            lines.append(f"  {f['status']:<9} {f['path']}")
    else:
        lines.append("  (none of the tracked patterns matched on either side)")
    if result.get("tree"):
        lines.append("")
        lines.extend(render_tree(result["tree"]))
    if "superseded" in result:
        lines.append("")
        lines.extend(render_superseded(result["superseded"]))
    lines.append("")
    lines.append(f"status: {result['status']}")
    if result["status"] == "DRIFTED":
        lines.append(f"remedy: {result['remedy']}")
    elif result.get("note"):
        lines.append(f"note: {result['note']}")
    return "\n".join(lines)


def _group_by_top(paths):
    groups = {}
    for rel in paths:
        groups.setdefault(_top_level(rel), []).append(rel)
    return groups


def render_tree(tree):
    """The whole-tree block of the card: counts, then every differing or missing path, then what
    the installed copy carries that git does not track, grouped by top-level directory."""
    lines = [
        f"whole tree: {tree['tracked_total']} tracked files — {tree['identical']} identical, "
        f"{len(tree['differs'])} differ, {len(tree['missing_from_install'])} missing from the install"
    ]
    lines.append("  by directory:")
    for top, counts in tree["by_dir"].items():
        parts = [f"{n} {k}" for k, n in counts.items() if n]
        lines.append(f"    {top:<24} " + ", ".join(parts))
    for label, key in (("differs", "differs"), ("missing from the install", "missing_from_install"),
                       ("tracked but absent from this checkout", "missing_in_checkout")):
        if tree[key]:
            lines.append(f"  {label}:")
            lines.extend(f"    {rel}" for rel in tree[key])
    untracked = tree["untracked_in_install"]
    if untracked:
        lines.append(f"  not tracked by git, copied anyway (the installer ignores .gitignore): "
                     f"{len(untracked)} file(s)")
        for paths in _group_by_top(untracked).values():
            if len(paths) == 1:
                lines.append(f"    {paths[0]}")
            else:
                common = os.path.commonpath([os.path.dirname(p) or "." for p in paths])
                lines.append(f"    {len(paths)} files under {common}/")
    return lines


def render_superseded(superseded):
    """The cache block: other version directories and their removal lines, printed only."""
    if superseded is None:
        return ["cache: the install path does not have the installer's layout; "
                "no removal lines are printed"]
    if not superseded:
        return ["cache: only the active version is present"]
    lines = [f"cache: {len(superseded)} other version director{'y' if len(superseded) == 1 else 'ies'} "
             "beside the active one; no update removes them. To remove them (printed, never run):"]
    lines.extend(f"  {cmd}" for cmd in prune_commands(superseded))
    return lines


def render_loaded(result):
    """The --loaded answer as a short card."""
    lines = [f"## loaded plugin — {result.get('plugin_key', result['loaded_root'])}", ""]
    if result.get("loaded_version"):
        lines.append(f"session loaded: `{result['loaded_version']}` from {result['loaded_root']}")
    if result.get("install_path"):
        lines.append(f"installed:      `{result['installed_version']}` at {result['install_path']}")
    lines.append(f"status: {result['status']}")
    lines.append(f"note: {result['note']}")
    return "\n".join(lines)


def _read_tracked_file(path):
    """A tracked-path list from a file: NUL- or newline-separated, as `git ls-files [-z]` prints."""
    text = Path(path).read_text()
    parts = text.split("\0") if "\0" in text else text.splitlines()
    return [p for p in (s.strip() for s in parts) if p]


def _git_tracked_paths(repo_dir):
    """The tracked list from git, via `bin/release_gate.py`'s read-only `git ls-files` (run under
    `bin/proc_runner.py`); None when git cannot answer. Only main() calls this -- the engine
    functions above always take the list as an argument."""
    spec = importlib.util.spec_from_file_location(
        "release_gate_for_staleness", Path(__file__).resolve().parent / "release_gate.py")
    release_gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(release_gate)
    return release_gate.tracked_paths(repo_dir)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Compare the live-installed polytropos plugin against this repo's source, "
            "file by file -- read-only; never touches the real installer."
        )
    )
    parser.add_argument(
        "--repo", default=str(PLUGIN_ROOT), help="repo directory to compare from (default: this repo)"
    )
    parser.add_argument(
        "--installed-manifest",
        default=DEFAULT_INSTALLED_MANIFEST,
        help="path to installed_plugins.json (default: ~/.claude/plugins/installed_plugins.json)",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--full", action="store_true",
        help="compare every tracked file, not just the core globs, and list what the installed "
             "copy carries that git does not track",
    )
    parser.add_argument(
        "--tracked-file", metavar="PATH",
        help="with --full: read the tracked-path list from PATH (`git ls-files -z` output) "
             "instead of asking git",
    )
    parser.add_argument(
        "--loaded", metavar="DIR",
        help="after a restart: is the session running the installed copy? DIR is the directory "
             "the session loaded -- ${CLAUDE_PLUGIN_ROOT} inside a skill",
    )
    args = parser.parse_args(argv)

    if args.loaded:
        loaded = check_loaded(args.loaded, args.installed_manifest)
        print(json.dumps(loaded, indent=2) if args.json else render_loaded(loaded))
        return loaded["exit_code"]

    result = check_staleness(args.repo, args.installed_manifest)
    if result["installed"]:
        result["superseded"] = superseded_versions(
            result.get("install_path"), result["plugin_name"], result["marketplace"])
        if args.full:
            tracked = (_read_tracked_file(args.tracked_file) if args.tracked_file
                       else _git_tracked_paths(args.repo))
            if tracked is None:
                print("--full needs this repo's tracked-file list and git could not provide it; "
                      "pass --tracked-file", file=sys.stderr)
                return EXIT_USAGE
            result = resolve_with_tree(result, compare_tree(args.repo, result.get("install_path"),
                                                            tracked))

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render_markdown(result))

    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
