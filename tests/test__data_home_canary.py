"""The first half of the data-home canary: point the whole suite's data root at an empty dir.

WHY. Every personal store this repo writes resolves through `bin/runtime_data.py` to a per-user
data root, and a test that reaches a writer without pointing `POLYTROPOS_DATA_HOME` at a temp dir
writes into the REAL one. Two modules did exactly that on every run: by the time anyone looked,
the real root held 1,496 `tmp*` namespaces of attempt-ledger events from test fixtures. Isolating
each module is the rule (the `setUpModule` in `tests/test_copilot_execute.py`), and a rule that
nothing checks is a rule the next module forgets.

HOW. Discovery imports every test module before it runs any test, in sorted filename order, and
this name sorts first. At import it points the data root at a fresh, empty canary dir and records
that dir in `POLYTROPOS_TEST_DATA_HOME_CANARY`. From then on, a module that isolates itself
patches the root to its own temp dir and restores the canary afterwards; a module that forgets
writes into the canary instead of the user's store. `tests/test_zz_data_home_canary.py` sorts
last and fails if the canary is not still empty, naming each namespace that landed in it.

WHAT IT DOES NOT COVER. A run that never imports this module -- `discover -p` for one file --
gets neither the canary nor the check; per-module isolation is what protects those runs. And the
canary sees only writes that resolve the root through `POLYTROPOS_DATA_HOME`. A writer that built
its own path from `HOME` would bypass it; none does today (the full suite with the variable
redirected left the real root untouched), and nothing here proves none ever will.
"""

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"

#: Names the canary dir for the last module; set only by this module.
CANARY_VAR = "POLYTROPOS_TEST_DATA_HOME_CANARY"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# The variable's name comes from its owner, so a rename there cannot leave the canary pointing
# a variable nothing reads.
DATA_HOME_VAR = _load("runtime_data").DATA_HOME_VAR

_CANARY = tempfile.mkdtemp(prefix="polytropos-test-canary-")
os.environ[DATA_HOME_VAR] = _CANARY
os.environ[CANARY_VAR] = _CANARY


class DataHomeCanaryArmedTest(unittest.TestCase):
    def test_canary_is_the_data_root_and_empty_before_any_test_runs(self):
        # Every module is imported by now, so this also catches a write made at import time.
        self.assertEqual(os.environ.get(DATA_HOME_VAR), _CANARY)
        self.assertEqual(sorted(os.listdir(_CANARY)), [])

    def test_this_module_is_imported_first(self):
        # Every test runs after discovery, so all of them see the canary whatever the order;
        # sorting first extends that to a write a module makes while it is being imported.
        names = sorted(p.name for p in Path(__file__).resolve().parent.glob("test*.py"))
        self.assertEqual(names[0], Path(__file__).name)


if __name__ == "__main__":
    unittest.main()
