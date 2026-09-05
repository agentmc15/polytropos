"""Make the Python floor loud (PLAN.md D2, aesop-fold kit).

polytropos's stdlib TOML parser (``tomllib``) is only available from the interpreter
version where it was added to the standard library, so the documented floor in
SETUP.md must match what the shipped code already requires. This module fails loudly
on an interpreter below that floor and sweeps the tracked tree for any doc, script,
or config file that still claims an older, superseded floor.
"""

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SETUP_MD = REPO_ROOT / "SETUP.md"

REQUIRED_FLOOR = (3, 11)

# Escaped so the pattern text itself never spells out a contiguous stale-floor
# string in this module's source.
STALE_FLOOR_RE = re.compile(r"3\.8\+|Python 3\.8\b|3\.10\+|python_requires\s*=")

SWEEP_ROOTS = (
    "README.md",
    "SETUP.md",
    "CLAUDE.md",
    "docs",
    "docs-src",
    "docs-site",
    "skills",
    "copilot",
    "codex",
    "copilot-docs",
    "bin",
    "tests",
)
SWEEP_SUFFIXES = {".md", ".py", ".toml", ".yaml", ".yml", ".json", ".txt"}


def _sweep_candidates():
    this_file = Path(__file__).resolve()
    for root_name in SWEEP_ROOTS:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        paths = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file()]
        for path in paths:
            resolved = path.resolve()
            if resolved == this_file:
                continue
            if "__pycache__" in resolved.parts:
                continue
            if resolved.suffix not in SWEEP_SUFFIXES:
                continue
            yield resolved


class PythonFloorTests(unittest.TestCase):
    def test_interpreter_meets_documented_floor(self):
        self.assertGreaterEqual(
            sys.version_info,
            REQUIRED_FLOOR,
            "This interpreter (%s) is below the floor SETUP.md documents; "
            "polytropos needs stdlib tomllib, which is not available before "
            "that floor. Install a newer python3." % (sys.version,),
        )

    def test_tomllib_importable(self):
        try:
            import tomllib  # noqa: F401
        except ImportError as exc:
            self.fail(
                "tomllib is not importable on this interpreter (%s): %s. "
                "See SETUP.md for the documented Python floor." % (sys.version, exc)
            )

    def test_setup_md_declares_311_floor(self):
        content = SETUP_MD.read_text(encoding="utf-8")
        self.assertIn("`python3` (3.11+)", content)
        self.assertIsNone(
            re.search(r"\(3\.8\+\)", content),
            "SETUP.md still contains a superseded interpreter-floor claim",
        )

    def test_no_stale_floor_claims(self):
        offenders = []
        for path in sorted(_sweep_candidates()):
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            match = STALE_FLOOR_RE.search(text)
            if match:
                offenders.append("%s: %r" % (path.relative_to(REPO_ROOT), match.group(0)))
        self.assertFalse(
            offenders,
            "stale Python-floor claims found (fix or update SETUP.md instead):\n"
            + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
