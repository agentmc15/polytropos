"""Hidden oracle for T1 (statusline K->M rollover). Never shown to a candidate.

Runs from a grading sandbox's `tests/` directory; imports the candidate's `bin/statusline.py`.
"""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("route_oracle_statusline",
                                                  ROOT / "bin" / "statusline.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sl = _load()


class RolloverFixed(unittest.TestCase):
    def test_999_500_is_one_million(self):
        self.assertEqual(sl.fmt_tokens(999_500), "1.0M")

    def test_999_999_is_one_million(self):
        self.assertEqual(sl.fmt_tokens(999_999), "1.0M")

    def test_no_value_near_the_boundary_renders_four_digit_k(self):
        for n in range(998_000, 1_000_001, 7):
            out = sl.fmt_tokens(n)
            if out.endswith("K"):
                self.assertLess(int(out[:-1]), 1000, (n, out))

    def test_string_and_float_inputs_rollover_too(self):
        self.assertEqual(sl.fmt_tokens("999999"), "1.0M")
        self.assertEqual(sl.fmt_tokens(999_999.9), "1.0M")


class UnchangedBehaviour(unittest.TestCase):
    def test_below_one_thousand(self):
        for n in (0, 1, 7, 999):
            self.assertEqual(sl.fmt_tokens(n), str(n))

    def test_negative_values_are_plain(self):
        self.assertEqual(sl.fmt_tokens(-5), "-5")
        self.assertEqual(sl.fmt_tokens(-5_000_000), "-5000000")

    def test_thousands(self):
        self.assertEqual(sl.fmt_tokens(1_000), "1K")
        self.assertEqual(sl.fmt_tokens(12_345), "12K")
        self.assertEqual(sl.fmt_tokens(999_499), "999K")
        self.assertEqual(sl.fmt_tokens(1_500), "2K")
        self.assertEqual(sl.fmt_tokens(2_500), "2K")

    def test_millions(self):
        self.assertEqual(sl.fmt_tokens(1_000_000), "1.0M")
        self.assertEqual(sl.fmt_tokens(1_500_000), "1.5M")
        self.assertEqual(sl.fmt_tokens(12_340_000), "12.3M")

    def test_no_new_units(self):
        self.assertEqual(sl.fmt_tokens(2_000_000_000), "2000.0M")

    def test_matches_original_everywhere_outside_the_bug(self):
        def original(n):
            n = int(n)
            if n >= 1_000_000:
                return f"{n / 1_000_000:.1f}M"
            if n >= 1_000:
                return f"{n / 1_000:.0f}K"
            return str(n)

        for n in list(range(-50, 5_000, 13)) + list(range(5_000, 999_000, 997)) + \
                list(range(1_000_000, 50_000_000, 99_991)):
            self.assertEqual(sl.fmt_tokens(n), original(n), n)


if __name__ == "__main__":
    unittest.main()
