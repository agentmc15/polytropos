"""Path-containment tests (step 10).

Every assertion here is about an observed effect on disk -- what survived outside the root,
what the root ended up holding -- rather than about the shape of a path string.
"""

import importlib.util
import os
import stat
import tempfile
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
SPEC = importlib.util.spec_from_file_location("safe_paths_tests", BIN_DIR / "safe_paths.py")
sp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sp)


class IdentifierTests(unittest.TestCase):
    """Identifiers become filenames, so an id that can name a path can leave its directory."""

    def test_ordinary_task_ids_are_accepted(self):
        for good in ("T1", "T17R", "E1", "a.b-c_1", "task-42"):
            self.assertEqual(sp.validate_id(good), good)

    def test_escaping_identifiers_are_refused(self):
        for bad in ("../escape", "..", ".", "a/b", "a\\b", "/abs", "C:\\x", "", "   ",
                    ".hidden", None, "x" * 65):
            with self.assertRaises(sp.SafePathError, msg=f"{bad!r} must be refused"):
                sp.validate_id(bad)

    def test_the_error_is_a_valueerror_for_existing_callers(self):
        self.assertTrue(issubclass(sp.SafePathError, ValueError))


class RelativePathTests(unittest.TestCase):
    def test_traversal_absolute_and_drive_paths_are_refused(self):
        for bad in ("../out", "a/../../out", "/etc/passwd", "C:/x", "", "   "):
            with self.assertRaises(sp.SafePathError, msg=f"{bad!r} must be refused"):
                sp.safe_parts(bad)

    def test_ordinary_relative_paths_decompose(self):
        self.assertEqual(sp.safe_parts("facts/a.md"), ["facts", "a.md"])
        self.assertEqual(sp.safe_parts("a/./b"), ["a", "b"])


@unittest.skipUnless(sp.dir_fd_supported(), "no directory-relative file operations here")
class ContainmentTests(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.root = self.td / "root"
        self.root.mkdir()
        self.outside = self.td / "outside"
        self.outside.mkdir()
        self.target = self.outside / "target.txt"
        self.target.write_text("ORIGINAL\n")

    def test_a_link_at_the_leaf_is_replaced_not_written_through(self):
        (self.root / "leaf").symlink_to(self.target)
        sp.confined_write_bytes(self.root, "leaf", "NEW\n")
        self.assertEqual(self.target.read_text(), "ORIGINAL\n")
        self.assertFalse((self.root / "leaf").is_symlink())
        self.assertEqual((self.root / "leaf").read_text(), "NEW\n")

    def test_a_link_in_a_parent_is_refused(self):
        (self.root / "via").symlink_to(self.outside)
        with self.assertRaises(sp.SafePathError) as caught:
            sp.confined_write_bytes(self.root, "via/x.txt", "NEW")
        self.assertIn("traverses", str(caught.exception))
        self.assertFalse((self.outside / "x.txt").exists())

    def test_reads_do_not_follow_a_link_at_the_leaf(self):
        (self.root / "readme").symlink_to(self.target)
        with self.assertRaises(sp.SafePathError):
            sp.confined_read_bytes(self.root, "readme")

    def test_reads_round_trip_ordinary_files(self):
        sp.confined_write_bytes(self.root, "sub/a.txt", "hello\n")
        self.assertEqual(sp.confined_read_bytes(self.root, "sub/a.txt"), b"hello\n")
        self.assertIsNone(sp.confined_read_bytes(self.root, "absent.txt", missing_ok=True))

    def test_deletion_does_not_follow_a_link_in_a_parent(self):
        (self.root / "via").symlink_to(self.outside)
        self.assertFalse(sp.confined_unlink(self.root, "via/target.txt"))
        self.assertTrue(self.target.exists(), "deleted a file outside the root")

    def test_deletion_removes_only_inside_the_root(self):
        sp.confined_write_bytes(self.root, "gone.txt", "x")
        self.assertTrue(sp.confined_unlink(self.root, "gone.txt"))
        self.assertFalse((self.root / "gone.txt").exists())

    def test_a_directory_at_the_destination_is_a_conflict_not_a_deletion(self):
        (self.root / "occupied").mkdir()
        (self.root / "occupied" / "keep.txt").write_text("keep\n")
        with self.assertRaises(sp.SafePathError):
            sp.confined_write_bytes(self.root, "occupied", "NEW")
        self.assertTrue((self.root / "occupied" / "keep.txt").exists())

    def test_replacement_is_atomic_and_private(self):
        sp.confined_replace(self.root, "sub/state.json", '{"a":1}', mode=0o600)
        path = self.root / "sub" / "state.json"
        self.assertEqual(path.read_text(), '{"a":1}')
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        sp.confined_replace(self.root, "sub/state.json", '{"a":2}', mode=0o600)
        self.assertEqual(path.read_text(), '{"a":2}')
        # no temp files left behind
        self.assertEqual([p.name for p in (self.root / "sub").iterdir()], ["state.json"])

    def test_replacement_does_not_follow_a_linked_parent(self):
        (self.root / "via").symlink_to(self.outside)
        with self.assertRaises(sp.SafePathError):
            sp.confined_replace(self.root, "via/state.json", "{}")
        self.assertFalse((self.outside / "state.json").exists())

    def test_leaf_is_regular_distinguishes_absent_from_occupied(self):
        self.assertFalse(sp.leaf_is_regular(self.root, "nothing.txt"))
        sp.confined_write_bytes(self.root, "real.txt", "x")
        self.assertTrue(sp.leaf_is_regular(self.root, "real.txt"))
        (self.root / "linked.txt").symlink_to(self.target)
        self.assertFalse(sp.leaf_is_regular(self.root, "linked.txt"))
        (self.root / "adir").mkdir()
        self.assertFalse(sp.leaf_is_regular(self.root, "adir"))


if __name__ == "__main__":
    unittest.main()
