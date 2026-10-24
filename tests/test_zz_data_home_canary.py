"""The second half of the data-home canary: after every other module ran, it must be empty.

`tests/test__data_home_canary.py` pointed the suite's data root at an empty canary dir before any
test ran (read its docstring first). This name sorts last, so by the time this runs every other
module has finished. Anything in the canary now was written by a test that reached a store
through the DEFAULT data root instead of its own temp dir -- which, without the canary, is the
user's real store. The failure names each namespace and the stores inside it. A namespace is the
fixture checkout's basename plus a digest, so it points at a temp dir rather than a module; the
`actor` field of the events in an `attempts` store names the driver that wrote them, which is
usually enough to find the test.

On success the empty canary is removed. On failure it is kept, and the message carries its path.
"""

import importlib.util
import os
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"

CANARY_VAR = "POLYTROPOS_TEST_DATA_HOME_CANARY"

_PASSED = False


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DATA_HOME_VAR = _load("runtime_data").DATA_HOME_VAR


def _canary():
    value = os.environ.get(CANARY_VAR)
    return Path(value) if value else None


def inventory(root):
    """Each entry under the canary as `namespace/store`, or `namespace` when it has no stores."""
    found = []
    for namespace in sorted(root.iterdir()):
        stores = sorted(p.name for p in namespace.iterdir()) if namespace.is_dir() else []
        if stores:
            found.extend(f"{namespace.name}/{store}" for store in stores)
        else:
            found.append(namespace.name)
    return found


class DataHomeCanaryTest(unittest.TestCase):
    def test_no_test_wrote_through_the_default_data_home(self):
        global _PASSED
        canary = _canary()
        if canary is None:
            self.skipTest("canary not armed: tests/test__data_home_canary.py was not imported")
        self.assertEqual(
            os.environ.get(DATA_HOME_VAR), str(canary),
            "a module left POLYTROPOS_DATA_HOME pointed away from the canary, so later writes "
            "went somewhere this check cannot see")
        leaked = inventory(canary)
        self.assertEqual(
            leaked, [],
            f"{len(leaked)} store(s) written through the default data root, which outside this "
            f"suite is the user's real store; isolate the writing module with a setUpModule "
            f"that points POLYTROPOS_DATA_HOME at a temp dir. Canary kept at {canary}")
        _PASSED = True

    def test_this_module_runs_last(self):
        # The check above sees only what ran before it: a module that sorted after this one
        # would still write into the canary, but after the canary was last looked at.
        names = sorted(p.name for p in Path(__file__).resolve().parent.glob("test*.py"))
        self.assertEqual(names[-1], Path(__file__).name)


def tearDownModule():
    canary = _canary()
    if _PASSED and canary is not None and canary.is_dir():
        canary.rmdir()


if __name__ == "__main__":
    unittest.main()
