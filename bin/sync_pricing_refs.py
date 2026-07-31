#!/usr/bin/env python3
"""Sync generated pricing.json mirrors for the portable skills.

`data/pricing.json` is the single hand-edited numeric source of truth for this repo. Per
PLAN.md D3 (`.claude/kits/aesop-bridge/PLAN.md`), aesop's `add skill` vendors a whole skill
directory (`readDirRecursive`), so a copy of pricing.json placed at
`skills/<name>/references/pricing.json` survives vendoring into another repo, while the
repo-root `data/pricing.json` does not. This script writes those mirrors — byte-identical
copies, not a json load/dump round-trip — for each portable skill in PORTABLE_SKILLS.

Never edit a mirror by hand: regenerate it by running this script after any change to
data/pricing.json. `tests/test_pricing_refs.py` fails on drift between the source and either
mirror.

Usage:
    sync_pricing_refs.py            # write both mirrors, print what was synced
    sync_pricing_refs.py --check    # verify mirrors are in sync; nonzero exit on drift
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "data" / "pricing.json"
PORTABLE_SKILLS = ("route", "fable-check")


def _mirror_paths(root):
    root = Path(root) if root is not None else REPO_ROOT
    return [root / "skills" / name / "references" / "pricing.json" for name in PORTABLE_SKILLS]


def sync(root=None):
    """Write byte-identical copies of <root>/data/pricing.json to each portable skill's
    references/pricing.json, creating references/ dirs as needed. Returns the list of paths
    written."""
    root = Path(root) if root is not None else REPO_ROOT
    source = root / "data" / "pricing.json"
    data = source.read_bytes()
    written = []
    for mirror in _mirror_paths(root):
        mirror.parent.mkdir(parents=True, exist_ok=True)
        mirror.write_bytes(data)
        written.append(mirror)
    return written


def check(root=None):
    """Return the list of mirror paths that are missing or not byte-identical to the source.
    Never writes anything."""
    root = Path(root) if root is not None else REPO_ROOT
    source = root / "data" / "pricing.json"
    data = source.read_bytes()
    stale = []
    for mirror in _mirror_paths(root):
        if not mirror.exists() or mirror.read_bytes() != data:
            stale.append(mirror)
    return stale


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sync generated pricing.json mirrors for the portable skills.")
    parser.add_argument("--check", action="store_true", help="verify mirrors are in sync without writing")
    args = parser.parse_args(argv)

    if args.check:
        stale = check()
        if not stale:
            print("ok")
            return 0
        for path in stale:
            try:
                rel = path.relative_to(REPO_ROOT)
            except ValueError:
                rel = path
            print(f"stale {rel}", file=sys.stderr)
        return 1

    written = sync()
    for path in written:
        try:
            rel = path.relative_to(REPO_ROOT)
        except ValueError:
            rel = path
        print(f"synced {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
