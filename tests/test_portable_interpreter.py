"""A test or engine that spawns a Python child must not name the interpreter by an absolute path.

A literal such as "/opt/homebrew/bin/python3.12" passes on the machine it was written on and
fails everywhere else: `bin/proc_runner.py` reports `missing-executable`, and the test goes red
for a reason that has nothing to do with the code under test. Two context-travel tests shipped
that way. The portable spelling is `sys.executable`, the interpreter already running the suite.

What this refuses is narrow on purpose: a list literal whose FIRST element is a quoted absolute
path ending in a Python executable name, which is what a spawned argv looks like. A fake path
handed to a function as data (a fixture such as python_bin="/fake/bin/python3") is not a spawn
and is left alone.

Stdlib `unittest` only; nothing here spawns a process or reads a home directory.
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNED_DIRS = ("tests", "bin")

_ARGV_STARTING_WITH_AN_INTERPRETER_PATH = re.compile(
    r"""\[\s*["'](/[^"'\s]*/python(?:\d+(?:\.\d+)*)?)["']"""
)


def offenders(text):
    """Absolute interpreter paths that open a list literal in `text`, sorted and de-duplicated."""
    return sorted(set(_ARGV_STARTING_WITH_AN_INTERPRETER_PATH.findall(text)))


class PortableInterpreterTests(unittest.TestCase):
    def test_no_test_or_engine_spawns_an_interpreter_by_absolute_path(self):
        found = {}
        for folder in SCANNED_DIRS:
            for path in sorted((REPO_ROOT / folder).glob("*.py")):
                if path.resolve() == Path(__file__).resolve():
                    continue  # this file quotes the pattern in order to test it
                hits = offenders(path.read_text(encoding="utf-8"))
                if hits:
                    found[f"{folder}/{path.name}"] = hits
        self.assertEqual(found, {}, "spawn the child with sys.executable instead")

    def test_the_scan_actually_reads_the_files_it_claims_to(self):
        # An empty glob would make the test above pass for the wrong reason.
        for folder in SCANNED_DIRS:
            self.assertTrue(any((REPO_ROOT / folder).glob("*.py")), folder)


class GuardCanFailTests(unittest.TestCase):
    """The scan is worth having only if it trips on the thing it is for, and on nothing else."""

    def test_an_absolute_interpreter_path_opening_an_argv_is_reported(self):
        for literal in ("/opt/homebrew/bin/python3.12", "/usr/local/bin/python3", "/usr/bin/python"):
            with self.subTest(literal=literal):
                source = f'result = proc.run(\n    ["{literal}", "-B", script], cwd=root)\n'
                self.assertEqual(offenders(source), [literal])

    def test_single_quotes_are_reported_too(self):
        self.assertEqual(offenders("run(['/opt/python/bin/python3.11', '-c', code])"),
                         ["/opt/python/bin/python3.11"])

    def test_the_portable_spellings_are_not_reported(self):
        source = (
            'proc.run([sys.executable, "-B", script])\n'
            'subprocess_args = ["python3", "bin/tool.py"]\n'
            'schedule = render(python_bin="/fake/bin/python3")\n'
            'shebang = "#!/usr/bin/env python3"\n'
        )
        self.assertEqual(offenders(source), [])


if __name__ == "__main__":
    unittest.main()
