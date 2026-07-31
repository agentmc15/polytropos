"""Stdlib unittest regression suite for bin/copilot_prefs.py.

bin/ is not a package; copilot_prefs.py is loaded via importlib by absolute path computed
from this file's own location, per the repo's `BIN_DIR = Path(__file__).resolve().parent.parent
/ "bin"` convention (same pattern as tests/test_copilot_execute.py).

No test in this file ever creates or reads a real `prefs/copilot.json` at the default path:
every file-based test writes its prefs JSON under a `tempfile.TemporaryDirectory()` and
passes that path explicitly as `prefs_path`. The real user home directory is never looked
up anywhere in this file.

Fixture ids (`fake-cheap`, `fake-mid-a`, `fake-mid-b`, `fake-strong`, `fake-front`) and every
price in `PRICING_FIXTURE` are synthetic and copied from `tests/test_copilot_execute.py` —
never a real id from `data/pricing.copilot.json`.
"""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cprefs = _load("copilot_prefs")
ce = _load("copilot_execute")


# ---- fixtures ---------------------------------------------------------------------------------

# Identical in shape to tests/test_copilot_execute.py's PRICING_FIXTURE: tiers in file order
# cheap, mid (two entries), strong, frontier. Round fake numbers only -- never a real id/rate.
PRICING_FIXTURE = {
    "models": {
        "fake-cheap": {"tier": "cheap", "input_per_mtok": 1.0, "output_per_mtok": 2.0},
        "fake-mid-a": {"tier": "mid", "input_per_mtok": 3.0, "output_per_mtok": 6.0},
        "fake-mid-b": {"tier": "mid", "input_per_mtok": 3.5, "output_per_mtok": 7.0},
        "fake-strong": {"tier": "strong", "input_per_mtok": 8.0, "output_per_mtok": 16.0},
        "fake-front": {"tier": "frontier", "input_per_mtok": 20.0, "output_per_mtok": 40.0},
    }
}


# ---- 1. TIER_ORDER twin -------------------------------------------------------------------------

class TierOrderTwinTests(unittest.TestCase):
    def test_tier_order_matches_copilot_execute(self):
        self.assertEqual(cprefs.TIER_ORDER, ce.TIER_ORDER)


# ---- 2. load_prefs_file --------------------------------------------------------------------------

class LoadPrefsFileTests(unittest.TestCase):
    def test_absent_path_returns_empties_with_no_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "copilot.json"
            pins, excludes, notes = cprefs.load_prefs_file(path)
            self.assertEqual(pins, {})
            self.assertEqual(excludes, [])
            self.assertEqual(notes, [])

    def test_malformed_json_returns_empties_and_one_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "copilot.json"
            path.write_text("{not valid json")
            pins, excludes, notes = cprefs.load_prefs_file(path)
            self.assertEqual(pins, {})
            self.assertEqual(excludes, [])
            self.assertEqual(len(notes), 1)
            self.assertIn("malformed", notes[0])

    def test_top_level_list_treated_as_malformed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "copilot.json"
            path.write_text(json.dumps(["not", "a", "dict"]))
            pins, excludes, notes = cprefs.load_prefs_file(path)
            self.assertEqual(pins, {})
            self.assertEqual(excludes, [])
            self.assertEqual(len(notes), 1)
            self.assertIn("malformed", notes[0])

    def test_pins_as_list_dropped_with_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "copilot.json"
            path.write_text(json.dumps({"pins": ["not", "a", "dict"]}))
            pins, excludes, notes = cprefs.load_prefs_file(path)
            self.assertEqual(pins, {})
            self.assertTrue(any("pins" in n for n in notes))

    def test_excludes_as_dict_dropped_with_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "copilot.json"
            path.write_text(json.dumps({"excludes": {"a": "b"}}))
            pins, excludes, notes = cprefs.load_prefs_file(path)
            self.assertEqual(excludes, [])
            self.assertTrue(any("excludes" in n for n in notes))

    def test_newer_schema_version_notes_best_effort(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "copilot.json"
            path.write_text(json.dumps({"schema_version": 99}))
            pins, excludes, notes = cprefs.load_prefs_file(path)
            self.assertTrue(any("best-effort" in n for n in notes))

    def test_unknown_top_level_key_tolerated_silently(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "copilot.json"
            path.write_text(json.dumps({"some_future_key": True}))
            pins, excludes, notes = cprefs.load_prefs_file(path)
            self.assertEqual(pins, {})
            self.assertEqual(excludes, [])
            self.assertEqual(notes, [])


# ---- 3. parse_pin_flag ---------------------------------------------------------------------------

class ParsePinFlagTests(unittest.TestCase):
    def test_good_pin_parses(self):
        tier, model_id = cprefs.parse_pin_flag("mid=fake-mid-b", PRICING_FIXTURE)
        self.assertEqual(tier, "mid")
        self.assertEqual(model_id, "fake-mid-b")

    def test_missing_equals_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            cprefs.parse_pin_flag("mid-fake-mid-b", PRICING_FIXTURE)
        self.assertIn("TIER=MODEL_ID", str(ctx.exception))

    def test_unknown_tier_lists_all_tier_words(self):
        with self.assertRaises(ValueError) as ctx:
            cprefs.parse_pin_flag("bogus=fake-mid-b", PRICING_FIXTURE)
        msg = str(ctx.exception)
        for tier_word in cprefs.TIER_ORDER:
            self.assertIn(tier_word, msg)

    def test_unknown_id_message_contains_valid_choices(self):
        with self.assertRaises(ValueError) as ctx:
            cprefs.parse_pin_flag("mid=not-a-real-id", PRICING_FIXTURE)
        self.assertIn("valid choices", str(ctx.exception))


# ---- 4. effective_prefs --------------------------------------------------------------------------

class EffectivePrefsTests(unittest.TestCase):
    @staticmethod
    def _write_prefs(tmp, data):
        path = Path(tmp) / "copilot.json"
        path.write_text(json.dumps(data))
        return path

    def test_file_pin_and_flag_pin_on_different_tiers_both_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_prefs(tmp, {"pins": {"mid": "fake-mid-a"}})
            result = cprefs.effective_prefs(
                PRICING_FIXTURE, prefs_path=path, pin_flags=["strong=fake-strong"]
            )
            self.assertEqual(result["pins"]["mid"], "fake-mid-a")
            self.assertEqual(result["pins"]["strong"], "fake-strong")

    def test_flag_pin_on_same_tier_replaces_file_pin_only_for_that_tier(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_prefs(
                tmp, {"pins": {"mid": "fake-mid-a", "strong": "fake-strong"}}
            )
            result = cprefs.effective_prefs(
                PRICING_FIXTURE, prefs_path=path, pin_flags=["mid=fake-mid-b"]
            )
            self.assertEqual(result["pins"]["mid"], "fake-mid-b")
            self.assertEqual(result["pins"]["strong"], "fake-strong")

    def test_excludes_union_file_and_flags_deduped_order_preserving(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_prefs(tmp, {"excludes": ["fake-mid-a", "fake-strong"]})
            result = cprefs.effective_prefs(
                PRICING_FIXTURE,
                prefs_path=path,
                exclude_flags=["fake-strong", "fake-front"],
            )
            self.assertEqual(
                result["excludes"], ["fake-mid-a", "fake-strong", "fake-front"]
            )

    def test_no_prefs_ignores_file_but_keeps_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_prefs(tmp, {"pins": {"mid": "fake-mid-a"}})
            result = cprefs.effective_prefs(
                PRICING_FIXTURE,
                prefs_path=path,
                no_prefs=True,
                pin_flags=["strong=fake-strong"],
            )
            self.assertNotIn("mid", result["pins"])
            self.assertEqual(result["pins"]["strong"], "fake-strong")
            self.assertIsNone(result["source"])

    def test_file_entry_with_unknown_tier_skipped_with_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_prefs(tmp, {"pins": {"nope": "fake-mid-a"}})
            result = cprefs.effective_prefs(PRICING_FIXTURE, prefs_path=path)
            self.assertNotIn("nope", result["pins"])
            self.assertEqual(result["pins"], {})
            self.assertTrue(result["notes"])

    def test_file_entry_with_stale_id_skipped_with_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_prefs(tmp, {"pins": {"mid": "not-a-real-id"}})
            result = cprefs.effective_prefs(PRICING_FIXTURE, prefs_path=path)
            self.assertEqual(result["pins"], {})
            self.assertTrue(result["notes"])

    def test_conflict_pin_and_exclude_same_id_from_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_prefs(
                tmp, {"pins": {"mid": "fake-mid-a"}, "excludes": ["fake-mid-a"]}
            )
            with self.assertRaises(ValueError) as ctx:
                cprefs.effective_prefs(PRICING_FIXTURE, prefs_path=path)
            self.assertIn("conflicts with exclude", str(ctx.exception))

    def test_conflict_from_mixed_sources_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_prefs(tmp, {"excludes": ["fake-mid-b"]})
            with self.assertRaises(ValueError) as ctx:
                cprefs.effective_prefs(
                    PRICING_FIXTURE, prefs_path=path, pin_flags=["mid=fake-mid-b"]
                )
            self.assertIn("conflicts with exclude", str(ctx.exception))

    def test_conflict_from_flag_pin_and_flag_exclude_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_prefs(tmp, {})
            with self.assertRaises(ValueError) as ctx:
                cprefs.effective_prefs(
                    PRICING_FIXTURE,
                    prefs_path=path,
                    pin_flags=["strong=fake-strong"],
                    exclude_flags=["fake-strong"],
                )
            self.assertIn("conflicts with exclude", str(ctx.exception))

    def test_cross_tier_pin_notes_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_prefs(tmp, {})
            result = cprefs.effective_prefs(
                PRICING_FIXTURE, prefs_path=path, pin_flags=["frontier=fake-strong"]
            )
            self.assertTrue(any("cross-tier override" in n for n in result["notes"]))

    def test_source_is_temp_path_when_file_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_prefs(tmp, {})
            result = cprefs.effective_prefs(PRICING_FIXTURE, prefs_path=path)
            self.assertEqual(result["source"], str(path))

    def test_source_is_none_when_file_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "copilot.json"
            result = cprefs.effective_prefs(PRICING_FIXTURE, prefs_path=path)
            self.assertIsNone(result["source"])

    def test_source_is_none_with_no_prefs_even_if_file_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_prefs(tmp, {"pins": {"mid": "fake-mid-a"}})
            result = cprefs.effective_prefs(PRICING_FIXTURE, prefs_path=path, no_prefs=True)
            self.assertIsNone(result["source"])


# ---- 5. resolve_tier ------------------------------------------------------------------------------

class ResolveTierTests(unittest.TestCase):
    def test_pin_wins_outright_over_file_order(self):
        prefs = {"pins": {"mid": "fake-mid-b"}, "excludes": [], "notes": [], "source": None}
        self.assertEqual(cprefs.resolve_tier(PRICING_FIXTURE, "mid", prefs), "fake-mid-b")

    def test_no_pin_uses_first_in_file_order(self):
        prefs = cprefs.empty_prefs()
        self.assertEqual(cprefs.resolve_tier(PRICING_FIXTURE, "mid", prefs), "fake-mid-a")

    def test_exclude_first_mid_falls_to_second(self):
        prefs = {"pins": {}, "excludes": ["fake-mid-a"], "notes": [], "source": None}
        self.assertEqual(cprefs.resolve_tier(PRICING_FIXTURE, "mid", prefs), "fake-mid-b")

    def test_exclude_both_mids_returns_none(self):
        prefs = {
            "pins": {}, "excludes": ["fake-mid-a", "fake-mid-b"], "notes": [], "source": None
        }
        self.assertIsNone(cprefs.resolve_tier(PRICING_FIXTURE, "mid", prefs))

    def test_exclude_frontier_with_no_pin_returns_none(self):
        prefs = {"pins": {}, "excludes": ["fake-front"], "notes": [], "source": None}
        self.assertIsNone(cprefs.resolve_tier(PRICING_FIXTURE, "frontier", prefs))

    def test_frontier_pin_to_cross_tier_model_returns_it(self):
        prefs = {"pins": {"frontier": "fake-strong"}, "excludes": [], "notes": [], "source": None}
        self.assertEqual(cprefs.resolve_tier(PRICING_FIXTURE, "frontier", prefs), "fake-strong")

    def test_unknown_tier_raises_value_error(self):
        with self.assertRaises(ValueError):
            cprefs.resolve_tier(PRICING_FIXTURE, "not-a-tier", cprefs.empty_prefs())

    def test_prefs_none_behaves_as_no_prefs(self):
        self.assertEqual(cprefs.resolve_tier(PRICING_FIXTURE, "mid", None), "fake-mid-a")


if __name__ == "__main__":
    unittest.main()
