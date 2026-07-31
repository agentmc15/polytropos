#!/usr/bin/env python3
"""daily-journal launchd scheduler (PLAN.md D12).

This module WRITES a launchd plist under a Launch Agents directory and PRINTS the
``launchctl bootstrap`` / ``launchctl bootout`` commands as INSTRUCTIONS for the USER to run
by hand. It never executes ``launchctl`` and never spawns any other process: this module
imports no process-spawning stdlib module anywhere, and does not.

The ``run`` subcommand is the manual one-shot path — the thing the plist eventually points
at. It calls the collector's and summarizer's ``main(argv)`` IN-PROCESS via ``importlib``
(injectable as ``cmd_run(args, collect_main=None, summarize_main=None)`` so tests never touch
the real modules or spawn anything either).

During development and every test/verify run, the installer only ever targets a temp
``--launch-agents-dir`` — never the user's real ``~/Library/LaunchAgents``. Loading the
schedule (running the printed ``launchctl bootstrap`` command) is the user's later, manual
step, outside this kit.
"""

import argparse
import importlib.util
import plistlib
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
LABEL = "com.polytropos.daily-journal"

# The ONE home-directory lookup in this file — a runtime default for the user's real machine.
# Every test and verify command overrides it with --launch-agents-dir pointed at a temp
# fixture, so execution never writes to a real home directory.
DEFAULT_LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"

DEFAULT_HOUR = 22
DEFAULT_MINUTE = 0


def _load(name):
    """Load a sibling ``bin/<name>.py`` module read-only (the session_cost.py pattern)."""
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parent / f"{name}.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _call_main(fn, argv):
    """Call an injected/loaded ``main(argv)``, normalizing its exit into an int.

    A normal ``return`` value is used as-is (this is how ``journal_summarize.main`` reports
    its accepted/failed doc count — including exit code 3 — without ever raising). A
    ``sys.exit(...)`` raised inside ``fn`` is caught: ``None`` -> 0, an int code is used
    as-is, and a message (str) is printed to stderr and treated as failure (1).
    """
    try:
        rc = fn(argv)
    except SystemExit as e:
        rc = e.code
    if rc is None:
        return 0
    if isinstance(rc, int):
        return rc
    print(str(rc), file=sys.stderr)
    return 1


# --------------------------------------------------------------------------- plist rendering

def render_plist(python_bin, script_path, hour, minute, journal_dir, plugin_root):
    """Render the launchd plist bytes (``plistlib.dumps``) for the daily-journal schedule.

    Validates ``0 <= hour <= 23`` and ``0 <= minute <= 59`` -> ``ValueError`` otherwise. All
    paths in the result are COMPUTED from the caller's arguments, never literal.
    """
    if not (0 <= hour <= 23):
        raise ValueError(f"hour must be 0-23, got {hour}")
    if not (0 <= minute <= 59):
        raise ValueError(f"minute must be 0-59, got {minute}")
    journal_dir = Path(journal_dir)
    plist = {
        "Label": LABEL,
        "ProgramArguments": [str(python_bin), str(script_path), "run"],
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "WorkingDirectory": str(plugin_root),
        "StandardOutPath": str(journal_dir / "logs" / "launchd.out.log"),
        "StandardErrorPath": str(journal_dir / "logs" / "launchd.err.log"),
        "RunAtLoad": False,
    }
    return plistlib.dumps(plist)


def plist_path(launch_agents_dir):
    """The plist's path inside a Launch Agents directory: ``<dir>/<LABEL>.plist``."""
    return Path(launch_agents_dir) / f"{LABEL}.plist"


# --------------------------------------------------------------------------- subcommands

def cmd_install(args):
    """Write the plist into ``--launch-agents-dir`` and print activation instructions.

    Never executes anything — the ``launchctl bootstrap``/``bootout`` lines printed here are
    for the USER to run by hand. Returns 0. Raises ``ValueError`` (caught by ``main``) for an
    out-of-range hour/minute.
    """
    launch_agents_dir = Path(args.launch_agents_dir)
    launch_agents_dir.mkdir(parents=True, exist_ok=True)
    python_bin = sys.executable
    script_path = Path(__file__).resolve()
    data = render_plist(
        python_bin, script_path, args.hour, args.minute, args.journal_dir, PLUGIN_ROOT
    )
    path = plist_path(launch_agents_dir)
    path.write_bytes(data)
    print(f"wrote {path}")
    print(f"To activate:  launchctl bootstrap gui/$(id -u) {path}")
    print(f"To deactivate: launchctl bootout gui/$(id -u)/{LABEL}")
    return 0


def cmd_uninstall(args):
    """Remove the plist if present. Prints what happened either way. Always returns 0."""
    path = plist_path(Path(args.launch_agents_dir))
    if path.is_file():
        path.unlink()
        print(f"removed {path}")
        print(f"To deactivate (if loaded): launchctl bootout gui/$(id -u)/{LABEL}")
    else:
        print(f"nothing installed at {path}")
    return 0


def cmd_status(args):
    """Print whether the schedule is installed, and its label/time/program if so."""
    path = plist_path(Path(args.launch_agents_dir))
    if not path.is_file():
        print(f"not installed ({path})")
        return 0
    with open(path, "rb") as f:
        data = plistlib.load(f)
    label = data.get("Label", LABEL)
    interval = data.get("StartCalendarInterval", {})
    hour = interval.get("Hour", 0)
    minute = interval.get("Minute", 0)
    program_args = data.get("ProgramArguments", [])
    program = program_args[1] if len(program_args) > 1 else "?"
    print(f"{label}: {hour:02d}:{minute:02d}  program={program}")
    return 0


def cmd_run(args, collect_main=None, summarize_main=None):
    """The manual one-shot: run the collector then (unless --collect-only) the summarizer,
    IN-PROCESS. ``collect_main``/``summarize_main`` are injectable for tests; when ``None``
    the real ``journal_collect``/``journal_summarize`` modules are loaded via ``_load``.

    The digest matters most: a nonzero collector code returns immediately, never invoking the
    summarizer. The summarizer's own exit code (including 3 for partial failure) is returned
    as-is — never swallowed.
    """
    if collect_main is None:
        collect_main = _load("journal_collect").main
    if summarize_main is None:
        summarize_main = _load("journal_summarize").main

    passthrough = []
    if getattr(args, "date", None):
        passthrough += ["--date", args.date]
    if getattr(args, "utc", False):
        passthrough.append("--utc")
    if getattr(args, "journal_dir", None):
        passthrough += ["--journal-dir", args.journal_dir]

    rc = _call_main(collect_main, list(passthrough))
    if rc != 0:
        return rc

    if getattr(args, "collect_only", False):
        return 0

    summarize_argv = list(passthrough)
    if getattr(args, "dry_run", False):
        summarize_argv.append("--dry-run")

    return _call_main(summarize_main, summarize_argv)


# --------------------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="journal_schedule.py",
        description="Write/inspect a launchd schedule for the daily journal. Never executes "
                    "launchctl; only writes a plist and prints the commands to load it.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_install = sub.add_parser("install", help="write the launchd plist (never loads it)")
    p_install.add_argument("--launch-agents-dir", default=str(DEFAULT_LAUNCH_AGENTS_DIR))
    p_install.add_argument("--hour", type=int, default=DEFAULT_HOUR)
    p_install.add_argument("--minute", type=int, default=DEFAULT_MINUTE)
    p_install.add_argument("--journal-dir", default=str(PLUGIN_ROOT / "journal"))

    p_uninstall = sub.add_parser("uninstall", help="remove the launchd plist if present")
    p_uninstall.add_argument("--launch-agents-dir", default=str(DEFAULT_LAUNCH_AGENTS_DIR))

    p_status = sub.add_parser("status", help="show whether the schedule is installed")
    p_status.add_argument("--launch-agents-dir", default=str(DEFAULT_LAUNCH_AGENTS_DIR))

    p_run = sub.add_parser("run", help="run the collector then the summarizer, in-process")
    p_run.add_argument("--date", default=None)
    p_run.add_argument("--utc", action="store_true")
    p_run.add_argument("--journal-dir", default=str(PLUGIN_ROOT / "journal"))
    p_run.add_argument("--collect-only", action="store_true")
    p_run.add_argument("--dry-run", action="store_true")

    args = ap.parse_args(argv)

    if args.cmd == "install":
        try:
            return cmd_install(args)
        except ValueError as e:
            p_install.error(str(e))  # prints usage + message, exits 2
    elif args.cmd == "uninstall":
        return cmd_uninstall(args)
    elif args.cmd == "status":
        return cmd_status(args)
    elif args.cmd == "run":
        return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
