"""Offline tests for CT2's bounded, stable confined read boundary."""

import importlib.util
import errno
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


BIN = Path(__file__).resolve().parent.parent / "bin"
SPEC = importlib.util.spec_from_file_location("ct2_safe_paths_tests", BIN / "safe_paths.py")
sp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sp)


@unittest.skipUnless(sp.dir_fd_supported(), "directory-relative operations unavailable")
class StableReadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "repo"
        self.root.mkdir()

    def read(self, relative, *, ceiling=100, budget=200):
        return sp.confined_read_stable_bytes(
            self.root, relative, max_bytes=ceiling, read_budget=budget
        )

    def test_exact_ceiling_stable_file_counts_both_physical_reads(self):
        payload = b"0123456789"
        (self.root / "TASKS.md").write_bytes(payload)
        result = self.read("TASKS.md", ceiling=10, budget=20)
        self.assertEqual(result["data"], payload)
        self.assertEqual(result["bytes_read"], 20)
        self.assertEqual(result["opened"], 2)

    def test_symlink_at_leaf_is_refused_without_opening_target(self):
        outside = self.base / "credential.txt"
        outside.write_bytes(b"synthetic-secret")
        (self.root / "TASKS.md").symlink_to(outside)
        with self.assertRaises(sp.SafePathError) as caught:
            self.read("TASKS.md")
        self.assertEqual(caught.exception.bytes_read, 0)
        self.assertEqual(outside.read_bytes(), b"synthetic-secret")

    def test_fifo_is_refused_without_hanging(self):
        fifo = self.root / "TASKS.md"
        os.mkfifo(fifo)
        with self.assertRaises(sp.SafePathError) as caught:
            self.read("TASKS.md")
        self.assertEqual(caught.exception.bytes_read, 0)

    def test_symlink_in_relative_ancestor_is_refused(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "TASKS.md").write_bytes(b"outside")
        (self.root / "kit").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(sp.SafePathError) as caught:
            self.read("kit/TASKS.md")
        self.assertEqual(caught.exception.bytes_read, 0)

    def test_symlink_in_absolute_root_ancestry_is_refused(self):
        real = self.base / "real"
        real.mkdir()
        (real / "TASKS.md").write_bytes(b"outside")
        alias = self.base / "alias"
        alias.symlink_to(real, target_is_directory=True)
        with self.assertRaises(sp.SafePathError) as caught:
            sp.confined_read_stable_bytes(alias, "TASKS.md", max_bytes=100,
                                          read_budget=200)
        self.assertEqual(caught.exception.bytes_read, 0)

    def test_traversal_is_refused_before_read(self):
        with self.assertRaises(sp.SafePathError) as caught:
            self.read("../private.txt")
        self.assertEqual(caught.exception.bytes_read, 0)

    def test_per_source_ceiling_counts_actual_bytes_on_failure(self):
        (self.root / "TASKS.md").write_bytes(b"1234567890")
        with self.assertRaises(sp.SafePathError) as caught:
            self.read("TASKS.md", ceiling=5, budget=10)
        self.assertGreaterEqual(caught.exception.bytes_read, 0)
        self.assertLessEqual(caught.exception.bytes_read, 10)
        self.assertGreaterEqual(caught.exception.opened, 1)

    def test_budget_covers_bounded_reread(self):
        (self.root / "TASKS.md").write_bytes(b"1234567890")
        with self.assertRaises(sp.SafePathError) as caught:
            self.read("TASKS.md", ceiling=10, budget=15)
        self.assertLessEqual(caught.exception.bytes_read, 15)

    def test_root_leaf_must_be_regular_file(self):
        (self.root / "directory").mkdir()
        with self.assertRaises(sp.SafePathError) as caught:
            self.read("directory")
        self.assertEqual(caught.exception.bytes_read, 0)

    def test_content_change_between_reads_is_inconsistent(self):
        source = self.root / "TASKS.md"
        source.write_bytes(b"original")
        real_read = os.read
        changed = False

        def changing_read(fd, count):
            nonlocal changed
            data = real_read(fd, count)
            if data and not changed:
                changed = True
                source.write_bytes(b"replaced")
            return data

        with mock.patch("os.read", side_effect=changing_read):
            with self.assertRaises(sp.SafePathError) as caught:
                self.read("TASKS.md", ceiling=8, budget=16)
        self.assertTrue(changed)
        self.assertEqual(caught.exception.reason_code, "inconsistent")
        self.assertLessEqual(caught.exception.bytes_read, 16)

    def test_hardlink_to_outside_file_is_refused_before_content_read(self):
        outside = self.base / "outside-private.txt"
        marker = b"synthetic-secret-marker"
        outside.write_bytes(marker)
        os.link(outside, self.root / "TASKS.md")
        with self.assertRaises(sp.SafePathError) as caught:
            self.read("TASKS.md")
        self.assertEqual(caught.exception.bytes_read, 0)
        self.assertEqual(outside.read_bytes(), marker)

    def test_partial_read_then_io_failure_charges_physical_bytes(self):
        (self.root / "TASKS.md").write_bytes(b"1234567890")
        real_read = os.read
        calls = 0
        secret = "synthetic-secret-should-not-be-diagnostic"

        def failing_read(fd, count):
            nonlocal calls
            calls += 1
            if calls == 1:
                return real_read(fd, min(count, 3))
            raise OSError(errno.EIO, secret)

        with mock.patch("os.read", side_effect=failing_read):
            with self.assertRaises(sp.SafePathError) as caught:
                self.read("TASKS.md")
        self.assertEqual(caught.exception.bytes_read, 3)
        self.assertGreaterEqual(caught.exception.opened, 1)
        self.assertEqual(caught.exception.reason_code, "unavailable")
        self.assertNotIn(secret, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
