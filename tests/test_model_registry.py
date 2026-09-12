"""Step 17: bin/model_registry.py -- one read-only answer to "which harness, which tier".

Every id here is a fixture id: the registry is exercised through an injected pricing bundle,
never the repo's real pricing files, so nothing rots when a real roster changes and nothing
here could be mistaken for a real price (the fixture carries no prices at all).
"""

import importlib.util
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mr = _load("model_registry")
rs = _load("routing_scorecard")

BUNDLE = {
    "claude": {"cached_date": "2020-01-01", "models": {
        "fake-haiku": {"tier": "haiku"},
        "fake-opus": {"tier": "opus"},
        "fake-fable": {"tier": "frontier"},
        "shared-id": {"tier": "opus"},
    }},
    "codex": {"cached_date": "2020-02-02", "models": {
        "fake-astra": {"tier": "frontier"},
        "fake-terra": {"tier": "mid"},
    }},
    "copilot": {"cached_date": "2020-03-03", "models": {
        "shared-id": {"tier": "strong"},
        "fake.dotted": {"tier": "cheap", "vendor": "fake"},
    }},
}


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.reg = mr.Registry(pricing_bundle=BUNDLE)

    def test_a_concrete_id_one_harness_knows_resolves_to_it(self):
        hit = self.reg.resolve("fake-astra")
        self.assertEqual((hit["harness"], hit["tier"], hit["kind"]), ("codex", "frontier", "model"))
        self.assertEqual(hit["registry"], {"codex": "2020-02-02"})

    def test_an_id_two_harnesses_know_differently_is_ambiguous_not_guessed(self):
        hit = self.reg.resolve("shared-id")
        self.assertIsNone(hit["harness"])
        self.assertIsNone(hit["tier"])
        self.assertEqual(hit["ambiguous"], ["claude", "copilot"])
        self.assertEqual(hit["tiers"], {"claude": "opus", "copilot": "strong"})
        self.assertEqual(self.reg.tier_of("shared-id", harness="claude"), "opus")
        self.assertEqual(self.reg.tier_of("shared-id", harness="copilot"), "strong")

    def test_a_tier_word_every_harness_agrees_on_keeps_the_tier(self):
        hit = self.reg.resolve("frontier")
        self.assertEqual(hit["tier"], "frontier")
        self.assertIsNone(hit["harness"])
        self.assertEqual(hit["ambiguous"], ["claude", "codex"])

    def test_claude_alias_words_are_claudes_alone(self):
        self.assertEqual(self.reg.resolve("fable", harness="claude")["tier"], "frontier")
        self.assertIsNone(self.reg.resolve("fable", harness="codex"))
        self.assertEqual(self.reg.resolve("haiku")["harness"], "claude")

    def test_dots_and_dashes_join(self):
        self.assertEqual(self.reg.tier_of("fake-dotted"), "cheap")
        self.assertEqual(self.reg.tier_of("FAKE.DOTTED"), "cheap")

    def test_unknown_is_none_never_a_default(self):
        self.assertIsNone(self.reg.resolve("no-such-id"))
        self.assertIsNone(self.reg.resolve(""))
        self.assertIsNone(self.reg.resolve(None))
        self.assertIsNone(self.reg.tier_of("no-such-id"))

    def test_versions_name_each_files_cached_date(self):
        self.assertEqual(self.reg.versions(),
                         {"claude": "2020-01-01", "codex": "2020-02-02", "copilot": "2020-03-03"})

    def test_a_missing_file_is_recorded_as_not_loaded(self):
        reg = mr.Registry(pricing_bundle={"claude": None})
        self.assertFalse(reg.sources["claude"]["loaded"])
        self.assertIsNone(reg.resolve("fake-opus"))


class ScorecardTierForTests(unittest.TestCase):
    """The defect this closes: a concrete id fell off the alias ladder."""

    def setUp(self):
        self._saved = rs._MODEL_REGISTRY
        rs._MODEL_REGISTRY = mr.Registry(pricing_bundle=BUNDLE)

    def tearDown(self):
        rs._MODEL_REGISTRY = self._saved

    def test_alias_words_behave_exactly_as_before(self):
        self.assertEqual(rs.tier_for("fable"), "frontier")
        for alias in ("haiku", "sonnet", "opus", "frontier"):
            self.assertEqual(rs.tier_for(alias), alias)
        self.assertIsNone(rs.tier_for(None))

    def test_a_concrete_claude_id_now_lands_on_its_tier(self):
        self.assertEqual(rs.tier_for("fake-opus"), "opus")
        self.assertEqual(rs.tier_for("fake-fable"), "frontier")

    def test_claudes_own_reading_wins_for_an_id_two_harnesses_share(self):
        self.assertEqual(rs.tier_for("shared-id"), "opus")

    def test_another_harnesses_concrete_id_resolves_to_its_own_tier(self):
        self.assertEqual(rs.tier_for("fake-astra"), "frontier")
        self.assertEqual(rs.tier_for("fake-terra"), "mid")

    def test_an_unknown_id_is_returned_unchanged_so_existing_notes_are_kept(self):
        self.assertEqual(rs.tier_for("not-in-any-file"), "not-in-any-file")


if __name__ == "__main__":
    unittest.main()
