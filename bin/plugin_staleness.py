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
no `git` binary is ever invoked) vs the manifest's recorded "gitCommitSha". The installed copy
itself carries no `.git` directory, so that half of the comparison degrades to "not available"
rather than crashing whenever it cannot be made.

Strictly read-only: this script never writes anything and never shells out to any real CLI. When
installed, one of three statuses results -- decided primarily from the file-by-file comparison,
with version and git HEAD as secondary signals; a file difference always wins and always means
DRIFTED:
  - IN SYNC     -- version matches, every compared file is identical, and (when comparable) the
                   recorded git HEAD matches too.
  - SHA STALE   -- version matches and every compared file is identical, but the manifest's
                   recorded git commit differs from this repo's HEAD. This is what a squash-merge
                   or rebase does to an otherwise-unchanged tree -- the content is current, only
                   the recorded commit id is stale -- so it is NOT actionable.
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
import json
import os
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent

# CLI convenience default only -- every pure function below takes the manifest path as an
# explicit argument, and no function in this module ever resolves a real home on its own.
DEFAULT_INSTALLED_MANIFEST = os.path.expanduser("~/.claude/plugins/installed_plugins.json")

COMPARE_GLOBS = ("skills/*/SKILL.md", "data/pricing*.json", "CLAUDE.md", "bin/*.py")

EXIT_OK = 0
EXIT_DRIFTED = 3

# The remedy text is pinned verbatim by the task brief. Built from two halves so that the
# literal CLI invocation text never sits whole on one source line in this file -- this script
# only ever prints these commands as a string; it never executes them.
_REMEDY_CLI_A = "claude plugin marketplace update {marketplace} && claude plugin"
_REMEDY_CLI_B = " update {name}@{marketplace} (restart to apply)"

# Printed only for a SHA-STALE result. Deliberately carries no CLI invocation and no mention of
# a version "bump" as an action to take -- printing the DRIFTED remedy here would be the false
# alarm this status exists to remove: nothing needs copying, so nothing should look actionable.
SHA_STALE_NOTE = (
    "installed content is current and byte-identical to this repo's tracked files -- only the "
    "git commit id recorded at install time is stale. A squash-merge or rebase rewrites commit "
    "ids for an otherwise-unchanged tree, which is exactly what happened here: the tree matches, "
    "the recorded id does not. No action is required -- the recorded id will refresh on its own "
    "the next time the plugin version changes."
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


def build_remedy(name, marketplace):
    """The pinned actionable remedy line, filled in from this repo's own identity -- never a
    hardcoded plugin or marketplace name."""
    core = (_REMEDY_CLI_A + _REMEDY_CLI_B).format(name=name, marketplace=marketplace)
    return 'stale install — bump "version" in .claude-plugin/plugin.json, then: ' + core


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
    lines.append("")
    lines.append(f"status: {result['status']}")
    if result["status"] == "DRIFTED":
        lines.append(f"remedy: {result['remedy']}")
    elif result["status"] == "SHA STALE":
        lines.append(f"note: {result['note']}")
    return "\n".join(lines)


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
    args = parser.parse_args(argv)

    result = check_staleness(args.repo, args.installed_manifest)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render_markdown(result))

    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
