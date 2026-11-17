"""The reference page carries a snapshot of every pricing file; keep it from going stale quietly.

`docs/REFERENCE.md` is the long-form page that was `README.md` until 2026-09-24. Its model tables
are labeled snapshots of `data/pricing*.json`, each at its file's own `cached_date`. The partner-doc
check in `bin/harness_update.py` (`DOCS_LABEL_MAP`) watches `README.md` and
`docs/COPILOT-HARNESS.md` only, so without this file nothing would notice the reference page
falling behind a pricing refresh. Reads the real tree only -- never writes, never uses a fixture --
in the manner of `tests/test_harness_update.py`'s `LiveTreeFreshnessTests`.

The page makes a second promise this file also holds it to. Its "at a glance" table says "every
count below is one you can re-derive", and for a while nothing did: a route experiment added three
engines and a store, a context-travel merge added a skill to three rosters and six more engines,
and the table, two headings that spell the counts out, the list of stores and the engine family
table all stayed as they were. `ReferenceCensusTests` re-derives each count from the tree, checks
the two headings and the store list against the same numbers, and requires every `bin/*.py` to be
named in the family table. A row it has not been taught to derive is a finding, not a pass.
"""

import importlib.util
import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REFERENCE = REPO_ROOT / "docs" / "REFERENCE.md"
BIN = REPO_ROOT / "bin"
PRICING_FILES = (
    "data/pricing.json",
    "data/pricing.codex.json",
    "data/pricing.copilot.json",
    "data/pricing.cursor.json",
)


def label_dates(text, rel):
    """Every date the page labels `rel` with, from the form '`<rel>`, `cached_date` **YYYY-MM-DD**'."""
    return re.findall(re.escape(f"`{rel}`, `cached_date` **") + r"(\d{4}-\d{2}-\d{2})\*\*", text)


def model_ids(rel):
    models = json.loads((REPO_ROOT / rel).read_text(encoding="utf-8")).get("models") or {}
    return sorted(models) if isinstance(models, dict) else sorted(m["id"] for m in models)


class ReferenceSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.text = REFERENCE.read_text(encoding="utf-8")

    def test_each_pricing_file_is_labeled_once_with_its_own_cached_date(self):
        for rel in PRICING_FILES:
            with self.subTest(file=rel):
                cached = json.loads((REPO_ROOT / rel).read_text(encoding="utf-8"))["cached_date"]
                dates = label_dates(self.text, rel)
                self.assertEqual(
                    len(dates), 1,
                    f"docs/REFERENCE.md labels {rel} {len(dates)} time(s); expected exactly one")
                self.assertEqual(
                    dates[0], cached,
                    f"{rel} is cached {cached} but docs/REFERENCE.md still labels it {dates[0]}: "
                    "regenerate that table in the same edit as the file")

    def test_every_model_id_in_every_pricing_file_appears_on_the_page(self):
        for rel in PRICING_FILES:
            for mid in model_ids(rel):
                with self.subTest(file=rel, model=mid):
                    self.assertTrue(
                        f"`{mid}`" in self.text,
                        f"{rel} carries {mid} but docs/REFERENCE.md does not show it")


# ---------------------------------------------------------------------------
# The census: every count the page states, re-derived from the tree.
# ---------------------------------------------------------------------------

GLANCE_MARKER = "**What is in it, at a glance**"
SKILLS_HEADING = "## Capabilities — the {word} skills"
ENGINES_HEADING = "## Functions — the {word} engines"
ENGINE_TABLE_START = "## Functions"
ENGINE_TABLE_END = "### The single-authority modules"
CLAUDE_SKILLS = "Skills (Claude Code)"
ENGINES = "Engines (`bin/*.py`)"

_GLANCE_ROW = re.compile(r"^\| (?P<surface>[^|]+?) \| (?P<count>[^|]+?) \| .* \|$")
_STORES_SENTENCE = re.compile(r"\*\*(?P<word>[A-Za-z-]+) stores, all outside the tree\.\*\*(?P<rest>[^\n]*)")
_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
         "fifteen sixteen seventeen eighteen nineteen").split()
_TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()


def _load(name):
    spec = importlib.util.spec_from_file_location(f"reference_doc_{name}", BIN / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _directories(rel):
    """What `ls -d <rel>/*/` counts: the visible directories directly under `rel`."""
    return sum(1 for p in (REPO_ROOT / rel).iterdir() if p.is_dir() and not p.name.startswith("."))


def number_word(n):
    """17 -> 'seventeen', 79 -> 'seventy-nine'. The headings spell their counts; past 99 they
    would have to change style, so that is an error here rather than a guess."""
    if type(n) is not int or not 0 <= n <= 99:
        raise ValueError(f"no heading word for {n!r}")
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens - 2] + (f"-{_ONES[ones]}" if ones else "")


def glance_rows(text):
    """The 'at a glance' table -> {surface: count exactly as written}. Only that table is read:
    it starts after the marker line and ends at the first line that is not a table row."""
    rows, in_table = {}, False
    for line in text[text.index(GLANCE_MARKER):].splitlines()[1:]:
        if not line.startswith("|"):
            if in_table:
                break
            continue
        in_table = True
        match = _GLANCE_ROW.match(line)  # the |---|---:|---| separator matches nothing
        if match and match.group("surface") != "Surface":
            rows[match.group("surface")] = match.group("count")
    return rows


def derived_counts():
    """Each surface the table names -> what the tree actually holds, by the table's own method."""
    registry = json.loads(
        (REPO_ROOT / "primitives" / "harness-capabilities.json").read_text(encoding="utf-8"))
    plugin = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    return {
        CLAUDE_SKILLS: _directories("skills"),
        "Skills (Copilot bundle)": _directories("copilot/.github/skills"),
        "Skills (Codex bundle)": _directories("codex/skills"),
        "Skills (Cursor bundle)": _directories("cursor/skills"),
        ENGINES: len(list(BIN.glob("*.py"))),
        "Pricing files (one per harness, never merged)":
            len(list((REPO_ROOT / "data").glob("pricing*.json"))),
        "Runtime stores, all outside the tree": len(_load("runtime_data").STORES),
        "Capability rows in the operational registry":
            sum(len(harness["capabilities"]) for harness in registry["harnesses"].values()),
        "Pipeline roles in the kit contract": len(_load("kit_contract").PIPELINE_ORDER),
        "Plugin version": plugin["version"],
    }


def count_problems(rows, derived):
    """Everything wrong with the table against the tree -> a sorted list of findings."""
    found = [f"{surface}: no row in the table" for surface in set(derived) - set(rows)]
    for surface, written in rows.items():
        if surface not in derived:
            found.append(f"{surface}: a row this test cannot re-derive; teach derived_counts() how")
        elif written != str(derived[surface]):
            found.append(f"{surface}: the page says {written}, the tree has {derived[surface]}")
    return sorted(found)


def heading_problems(text, derived):
    """The two headings that spell a count out must spell the count the tree has."""
    lines = text.splitlines()
    wanted = (
        SKILLS_HEADING.format(word=number_word(derived[CLAUDE_SKILLS])),
        ENGINES_HEADING.format(word=number_word(derived[ENGINES])),
    )
    return [f"missing heading: {heading}" for heading in wanted if heading not in lines]


def unnamed_engines(text, engines):
    """Engines the family table never names. The table is a map, and a map with a hole in it
    is how nine engines went undocumented."""
    table = text[text.index(ENGINE_TABLE_START):text.index(ENGINE_TABLE_END)]
    named = set(re.findall(r"`([a-z_0-9]+)`", table))
    return sorted(engine for engine in engines if engine not in named)


def store_problems(text, stores):
    """The '<N> stores, all outside the tree' paragraph must count and name every store."""
    match = _STORES_SENTENCE.search(text)
    if not match:
        return ["no '<N> stores, all outside the tree' paragraph"]
    found = []
    if match.group("word").lower() != number_word(len(stores)):
        found.append(f"the page says {match.group('word')} stores, the engine has {len(stores)}")
    found.extend(f"store `{name}` is not named" for name in sorted(stores)
                 if f"`{name}`" not in match.group("rest"))
    return found


class ReferenceCensusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = REFERENCE.read_text(encoding="utf-8")
        cls.derived = derived_counts()
        cls.engines = sorted(p.stem for p in BIN.glob("*.py"))
        cls.stores = sorted(_load("runtime_data").STORES)

    def test_every_count_in_the_table_matches_the_tree(self):
        self.assertEqual(count_problems(glance_rows(self.text), self.derived), [])

    def test_the_two_headings_spell_the_counts_the_tree_has(self):
        self.assertEqual(heading_problems(self.text, self.derived), [])

    def test_every_engine_is_named_in_the_family_table(self):
        self.assertEqual(unnamed_engines(self.text, self.engines), [])

    def test_every_runtime_store_is_counted_and_named(self):
        self.assertEqual(store_problems(self.text, self.stores), [])


class CensusGuardCanFailTests(unittest.TestCase):
    """The census is worth having only if it trips. Each case breaks one fact on the real page
    IN MEMORY, or hands the check a tree that has moved on; no tracked file is touched."""

    @classmethod
    def setUpClass(cls):
        cls.text = REFERENCE.read_text(encoding="utf-8")
        cls.derived = derived_counts()
        cls.engines = sorted(p.stem for p in BIN.glob("*.py"))
        cls.stores = sorted(_load("runtime_data").STORES)

    def _swap(self, old, new):
        self.assertEqual(self.text.count(old), 1, f"expected exactly one {old!r} on the page")
        return self.text.replace(old, new)

    def test_a_stale_count_is_reported(self):
        have = self.derived[ENGINES]
        broken = self._swap(f"| {ENGINES} | {have} |", f"| {ENGINES} | {have - 9} |")
        self.assertEqual(
            count_problems(glance_rows(broken), self.derived),
            [f"{ENGINES}: the page says {have - 9}, the tree has {have}"])

    def test_a_plugin_version_row_left_behind_by_a_bump_is_reported(self):
        version = self.derived["Plugin version"]
        broken = self._swap(f"| Plugin version | {version} |", "| Plugin version | 0.0.0 |")
        self.assertEqual(
            count_problems(glance_rows(broken), self.derived),
            [f"Plugin version: the page says 0.0.0, the tree has {version}"])

    def test_a_dropped_row_is_reported(self):
        row = next(line for line in self.text.splitlines()
                   if line.startswith("| Pipeline roles in the kit contract |"))
        self.assertEqual(
            count_problems(glance_rows(self._swap(row + "\n", "")), self.derived),
            ["Pipeline roles in the kit contract: no row in the table"])

    def test_a_row_nobody_taught_the_test_to_derive_is_reported(self):
        row = next(line for line in self.text.splitlines() if line.startswith("| Plugin version |"))
        broken = self._swap(row + "\n", row + "\n| Widgets | 3 | `ls widgets/` |\n")
        self.assertEqual(
            count_problems(glance_rows(broken), self.derived),
            ["Widgets: a row this test cannot re-derive; teach derived_counts() how"])

    def test_a_heading_that_spells_the_old_count_is_reported(self):
        now = SKILLS_HEADING.format(word=number_word(self.derived[CLAUDE_SKILLS]))
        before = SKILLS_HEADING.format(word=number_word(self.derived[CLAUDE_SKILLS] - 1))
        self.assertEqual(heading_problems(self._swap(now, before), self.derived),
                         [f"missing heading: {now}"])

    def test_an_engine_the_family_table_does_not_name_is_reported(self):
        self.assertEqual(unnamed_engines(self.text, self.engines + ["brand_new_engine"]),
                         ["brand_new_engine"])
        self.assertEqual(unnamed_engines(self._swap("`context_travel_mcp`", "the MCP adapter"),
                                         self.engines),
                         ["context_travel_mcp"])

    def test_a_store_the_page_neither_counts_nor_names_is_reported(self):
        found = store_problems(self.text, self.stores + ["brandnew"])
        self.assertEqual(len(found), 2, found)
        self.assertIn("store `brandnew` is not named", found)
        self.assertTrue(found[0].endswith(f"the engine has {len(self.stores) + 1}"), found)

    def test_number_words(self):
        for n, word in ((0, "zero"), (16, "sixteen"), (17, "seventeen"), (20, "twenty"),
                        (70, "seventy"), (79, "seventy-nine"), (99, "ninety-nine")):
            with self.subTest(n=n):
                self.assertEqual(number_word(n), word)
        for bad in (-1, 100, "17", 17.0, True):
            with self.subTest(bad=bad):
                self.assertRaises(ValueError, number_word, bad)


if __name__ == "__main__":
    unittest.main()
