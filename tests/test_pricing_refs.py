"""Stdlib unittest regression suite for bin/sync_pricing_refs.py.

bin/ is not a package; sync_pricing_refs.py is loaded via importlib by absolute path
computed from this file's own location, per PLAN.md D2.
"""

import importlib.util
import tempfile
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


spr = _load("sync_pricing_refs")


class LiveTreeMirrorTests(unittest.TestCase):
    """Drift tripwire: fails if source or a mirror is edited without rerunning the sync script."""

    def test_route_mirror_matches_source(self):
        source = REPO_ROOT / "data" / "pricing.json"
        mirror = REPO_ROOT / "skills" / "route" / "references" / "pricing.json"
        self.assertTrue(mirror.exists())
        self.assertEqual(mirror.read_bytes(), source.read_bytes())

    def test_fable_check_mirror_matches_source(self):
        source = REPO_ROOT / "data" / "pricing.json"
        mirror = REPO_ROOT / "skills" / "fable-check" / "references" / "pricing.json"
        self.assertTrue(mirror.exists())
        self.assertEqual(mirror.read_bytes(), source.read_bytes())


class SyncTests(unittest.TestCase):
    def _build_tree(self, tmp):
        tmp = Path(tmp)
        (tmp / "data").mkdir(parents=True, exist_ok=True)
        (tmp / "data" / "pricing.json").write_bytes(b'{"models": {}}')
        (tmp / "skills" / "route").mkdir(parents=True, exist_ok=True)
        (tmp / "skills" / "fable-check").mkdir(parents=True, exist_ok=True)
        return tmp

    def test_sync_writes_byte_identical_mirrors(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = self._build_tree(td)
            written = spr.sync(root=tmp)

            route_mirror = tmp / "skills" / "route" / "references" / "pricing.json"
            fable_mirror = tmp / "skills" / "fable-check" / "references" / "pricing.json"

            self.assertTrue(route_mirror.exists())
            self.assertTrue(fable_mirror.exists())
            source_bytes = (tmp / "data" / "pricing.json").read_bytes()
            self.assertEqual(route_mirror.read_bytes(), source_bytes)
            self.assertEqual(fable_mirror.read_bytes(), source_bytes)

            self.assertEqual(len(written), 2)
            self.assertIn(route_mirror, written)
            self.assertIn(fable_mirror, written)


class CheckTests(unittest.TestCase):
    def _build_tree(self, tmp):
        tmp = Path(tmp)
        (tmp / "data").mkdir(parents=True, exist_ok=True)
        (tmp / "data" / "pricing.json").write_bytes(b'{"models": {}}')
        (tmp / "skills" / "route").mkdir(parents=True, exist_ok=True)
        (tmp / "skills" / "fable-check").mkdir(parents=True, exist_ok=True)
        return tmp

    def test_check_catches_corrupted_mirror(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = self._build_tree(td)
            spr.sync(root=tmp)

            route_mirror = tmp / "skills" / "route" / "references" / "pricing.json"
            fable_mirror = tmp / "skills" / "fable-check" / "references" / "pricing.json"

            with open(route_mirror, "ab") as f:
                f.write(b"x")

            stale = spr.check(root=tmp)
            self.assertEqual(stale, [route_mirror])
            self.assertNotIn(fable_mirror, stale)

    def test_check_catches_missing_mirror(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = self._build_tree(td)
            spr.sync(root=tmp)

            route_mirror = tmp / "skills" / "route" / "references" / "pricing.json"
            fable_mirror = tmp / "skills" / "fable-check" / "references" / "pricing.json"

            fable_mirror.unlink()

            stale = spr.check(root=tmp)
            self.assertIn(fable_mirror, stale)
            self.assertNotIn(route_mirror, stale)


if __name__ == "__main__":
    unittest.main()
