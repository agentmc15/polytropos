#!/usr/bin/env python3
"""Where this machine's runtime data lives, and why it is not in the plugin tree.

THE PROBLEM. Every local store this repo writes -- `memory/`, `telemetry/`, `journal/`,
`benchruns/`, `prefs/`, `trends/` -- defaulted to a directory inside the repository itself.
Being gitignored keeps them out of a commit, and that is the only thing it keeps them out of.
The repository is also a distributable plugin: it gets installed, copied, cached, archived, and
on plenty of machines it sits inside a directory that syncs to somebody's cloud drive. Personal
notes and dollar figures should not ride along with code for any of that, and their permissions
should not depend on the umask that happened to be set when they were created.

WHAT THIS DOES. Resolves each store to a per-user application-data location, namespaced by
project so two checkouts do not share one memory, created 0700 with 0600 files.

WHAT IT DOES NOT DO: MOVE ANYTHING BY ITSELF. If a store already exists in the tree, that is
still where it is read and written from, and the only change is a line saying it could be
migrated. A tool that silently relocated a user's notes the first time they upgraded would be
indistinguishable, from the user's side, from a tool that lost them. `migrate` copies on
request, never overwrites, and never deletes the original -- reversing it is deleting the copy.

PROJECT NAMESPACE. A readable basename plus a short digest of the resolved path. Two checkouts
of the same repository are different projects, because their work is different; the digest is
what tells them apart, and the basename is what makes the directory recognizable to a person
looking at it in a file browser.
"""

import hashlib
import os
import shutil
import sys
from pathlib import Path

#: The stores this repo writes. Named here so `where` can report all of them at once and no
#: caller has to know the list.
STORES = ("memory", "telemetry", "journal", "benchruns", "prefs", "trends")

#: Overrides everything except an explicit per-command directory flag.
DATA_HOME_VAR = "POLYTROPOS_DATA_HOME"

#: Directory name under the OS application-data location.
APP_DIR = "polytropos"

#: Modes for anything created here. Runtime data is private by construction rather than by
#: whatever umask the shell happened to carry.
DIR_MODE = 0o700
FILE_MODE = 0o600


def user_data_home(env=None, platform=None):
    """The per-user application-data directory for this OS, without creating it."""
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    override = env.get(DATA_HOME_VAR)
    if override:
        return Path(override)
    home = Path(env.get("HOME") or Path.home())
    if platform == "darwin":
        return home / "Library" / "Application Support" / APP_DIR
    if platform.startswith("win"):
        base = env.get("LOCALAPPDATA") or env.get("APPDATA")
        return (Path(base) if base else home / "AppData" / "Local") / APP_DIR
    xdg = env.get("XDG_DATA_HOME")
    return (Path(xdg) if xdg else home / ".local" / "share") / APP_DIR


def project_namespace(repo_root):
    """A readable, collision-resistant directory name for one checkout.

    Basename for a person, digest for the machine: two clones of the same repository are
    different projects and must not share a store, but a directory called `a3f1c8d2` tells
    nobody anything.
    """
    resolved = os.path.realpath(str(repo_root))
    digest = hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:8]
    name = Path(resolved).name or "project"
    safe = "".join(ch if (ch.isalnum() or ch in "-_.") else "-" for ch in name)[:40]
    return f"{safe}-{digest}"


def legacy_path(name, repo_root):
    """Where this store used to live: inside the plugin tree."""
    return Path(repo_root) / name


def has_content(path):
    """True when a directory exists and holds anything at all."""
    path = Path(path)
    try:
        return path.is_dir() and any(path.iterdir())
    except OSError:
        return False


def resolve_store(name, repo_root, env=None, platform=None):
    """Where `name` is read and written -> `{"path", "origin", "note"}`.

    Precedence, and the reason for each:

    - `POLYTROPOS_DATA_HOME` wins, because an operator who has said where their data goes has
      said it about every store.
    - AN EXISTING IN-TREE STORE KEEPS BEING USED. Continuity beats tidiness: a user who
      upgrades must not discover their notes are gone. The note says migration is available.
    - Otherwise the per-user application-data location, which is where a fresh install lands.

    A per-command `--memory-dir`/`--store-dir` flag still overrides all of this; those flags
    are how every test points at a temp fixture and nothing here changes them.
    """
    env = os.environ if env is None else env
    if env.get(DATA_HOME_VAR):
        root = user_data_home(env=env, platform=platform) / project_namespace(repo_root) / name
        return {"path": root, "origin": "env", "note": f"{DATA_HOME_VAR} is set"}
    legacy = legacy_path(name, repo_root)
    if has_content(legacy):
        return {
            "path": legacy,
            "origin": "legacy-in-tree",
            "note": (f"still inside the plugin tree; `python3 bin/runtime_data.py migrate "
                     f"--store {name} --apply` copies it out (the original is left in place)"),
        }
    root = user_data_home(env=env, platform=platform) / project_namespace(repo_root) / name
    return {"path": root, "origin": "user-data-root", "note": ""}


def store_path(name, repo_root, env=None, platform=None):
    """`resolve_store`'s path alone -- the form a module's default constant wants."""
    return resolve_store(name, repo_root, env=env, platform=platform)["path"]


def ensure_private(path):
    """Create `path` (and missing parents) 0700, leaving existing ancestors' modes alone.

    Only directories this call actually creates get the mode. Re-permissioning a directory
    somebody else made -- a home directory, a synced folder -- is not this function's business
    and could break unrelated things.
    """
    path = Path(path)
    missing = []
    probe = path
    while not probe.exists():
        missing.append(probe)
        if probe.parent == probe:
            break
        probe = probe.parent
    for directory in reversed(missing):
        directory.mkdir(mode=DIR_MODE, exist_ok=True)
    return path


def plan_migration(name, repo_root, env=None, platform=None):
    """What migrating `name` out of the tree would do, without doing any of it.

    `copy` is what would be written, `conflicts` is what already exists at the destination and
    would NOT be overwritten, `source`/`target` name both ends.
    """
    source = legacy_path(name, repo_root)
    target = user_data_home(env=env, platform=platform) / project_namespace(repo_root) / name
    plan = {"store": name, "source": str(source), "target": str(target),
            "copy": [], "conflicts": [], "present": source.is_dir()}
    if not source.is_dir():
        return plan
    for path in sorted(p for p in source.rglob("*") if p.is_file()):
        relative = path.relative_to(source).as_posix()
        (plan["conflicts"] if (target / relative).exists() else plan["copy"]).append(relative)
    return plan


def migrate(name, repo_root, env=None, platform=None, apply=False):
    """Copy a store out of the plugin tree -> a report of exactly what happened.

    COPIES. The original is left exactly where it is, so this is reversible by deleting the
    copy, and a mistake costs disk rather than data. Removing the original is the user's call
    and is never done here -- nor is anything done about copies that have already been made by
    a backup or a cloud sync, which this cannot see and must not claim to have cleaned up.

    An existing destination file is a CONFLICT: skipped, reported, never overwritten.
    """
    plan = plan_migration(name, repo_root, env=env, platform=platform)
    report = dict(plan, applied=bool(apply), copied=[], failed=[])
    if not apply or not plan["present"]:
        return report
    source = Path(plan["source"])
    target = Path(plan["target"])
    ensure_private(target)
    for relative in plan["copy"]:
        destination = target / relative
        try:
            ensure_private(destination.parent)
            shutil.copyfile(source / relative, destination)
            os.chmod(destination, FILE_MODE)
            report["copied"].append(relative)
        except OSError as exc:
            report["failed"].append({"file": relative, "error": str(exc)})
    return report


def export(name, repo_root, destination, env=None, platform=None):
    """Copy a store to a directory the user names -> a report. Reads only; changes nothing."""
    source = store_path(name, repo_root, env=env, platform=platform)
    out = Path(destination) / name
    report = {"store": name, "source": str(source), "target": str(out), "copied": [],
              "present": Path(source).is_dir()}
    if not report["present"]:
        return report
    ensure_private(out)
    for path in sorted(p for p in Path(source).rglob("*") if p.is_file()):
        relative = path.relative_to(source)
        ensure_private((out / relative).parent)
        shutil.copyfile(path, out / relative)
        os.chmod(out / relative, FILE_MODE)
        report["copied"].append(relative.as_posix())
    return report


def forget(name, repo_root, older_than_days=None, env=None, platform=None, apply=False):
    """List (and with `apply`, delete) files in a store -> a report.

    Dry run by default and scoped by age, because a retention command whose default is
    "delete everything now" is one that will eventually be run by accident.
    """
    import time

    source = Path(store_path(name, repo_root, env=env, platform=platform))
    report = {"store": name, "path": str(source), "applied": bool(apply),
              "older_than_days": older_than_days, "matched": [], "removed": [], "failed": []}
    if not source.is_dir():
        return report
    cutoff = None if older_than_days is None else time.time() - (older_than_days * 86400)
    for path in sorted(p for p in source.rglob("*") if p.is_file()):
        try:
            if cutoff is not None and path.stat().st_mtime > cutoff:
                continue
        except OSError:
            continue
        relative = path.relative_to(source).as_posix()
        report["matched"].append(relative)
        if not apply:
            continue
        try:
            path.unlink()
            report["removed"].append(relative)
        except OSError as exc:
            report["failed"].append({"file": relative, "error": str(exc)})
    return report


def _repo_root():
    return Path(__file__).resolve().parent.parent


def _cli(argv=None):
    """`runtime_data.py where|migrate|export|forget` -- see and move this machine's data."""
    import argparse
    import json

    parser = argparse.ArgumentParser(
        prog="runtime_data.py",
        description="Where this machine's polytropos runtime data lives, and how to move it.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    for verb in ("where", "migrate", "export", "forget"):
        node = sub.add_parser(verb)
        node.add_argument("--repo-root", default=str(_repo_root()))
        node.add_argument("--json", action="store_true")
        if verb != "where":
            node.add_argument("--store", choices=STORES, default=None,
                              help="one store (default: all of them)")
        if verb in ("migrate", "forget"):
            node.add_argument("--apply", action="store_true",
                              help="do it; without this the command only reports")
        if verb == "export":
            node.add_argument("--to", required=True, help="directory to copy into")
        if verb == "forget":
            node.add_argument("--older-than-days", type=int, default=None)

    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    root = Path(args.repo_root)
    names = STORES if getattr(args, "store", None) is None else (args.store,)

    if args.cmd == "where":
        rows = {name: resolve_store(name, root) for name in STORES}
        if args.json:
            print(json.dumps({k: dict(v, path=str(v["path"])) for k, v in rows.items()},
                             indent=2, sort_keys=True))
            return 0
        for name, row in rows.items():
            print(f"{name:11s} {row['origin']:16s} {row['path']}")
            if row["note"]:
                print(f"{'':11s} {'':16s} — {row['note']}")
        return 0

    reports = []
    for name in names:
        if args.cmd == "migrate":
            reports.append(migrate(name, root, apply=args.apply))
        elif args.cmd == "export":
            reports.append(export(name, root, args.to))
        else:
            reports.append(forget(name, root, older_than_days=args.older_than_days,
                                  apply=args.apply))
    if args.json:
        print(json.dumps(reports, indent=2, sort_keys=True))
        return 0
    for report in reports:
        if args.cmd == "migrate":
            verb = "copied" if report["applied"] else "would copy"
            print(f"{report['store']}: {verb} {len(report.get('copied') or report['copy'])} "
                  f"file(s) → {report['target']}")
            if report["conflicts"]:
                print(f"  {len(report['conflicts'])} already present, left untouched")
            if not report["applied"]:
                print("  (nothing written; re-run with --apply. The original is never removed.)")
        elif args.cmd == "export":
            print(f"{report['store']}: copied {len(report['copied'])} file(s) → {report['target']}")
        else:
            verb = "removed" if report["applied"] else "would remove"
            print(f"{report['store']}: {verb} {len(report['matched'])} file(s) from {report['path']}")
            if not report["applied"]:
                print("  (nothing deleted; re-run with --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
