"""Two hand-written pages list every skill for a human reader: README.md's "Skills at a glance"
section and docs-site/workflows/choose-a-skill.md. Each row says which harnesses ship the skill,
when to reach for it, and which skills pair well with it.

The parity matrix on the site is generated, so it follows the rosters by itself. These two pages
are not, so nothing would stop them from going quietly wrong the day a skill is added, removed or
ported to another harness. This file is that stop: both tables must name exactly the skills the
three rosters ship, on exactly the harnesses that ship them, paired only with skills that exist
and that at least one harness ships alongside them, and they must agree with each other.

What it cannot judge is whether a pairing is good advice. That stays an editorial call, read
against the skill pages by whoever changes a row.

Stdlib `unittest` only; nothing here reads a home directory or invokes a CLI.
"""

import importlib.util
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"
GUIDE = REPO_ROOT / "docs-site" / "workflows" / "choose-a-skill.md"
MKDOCS = REPO_ROOT / "mkdocs.yml"
SECTION = "## Skills at a glance"
LABELS = {"claude": "Claude", "copilot": "Copilot", "codex": "Codex"}


def _load_docs_build():
    spec = importlib.util.spec_from_file_location(
        "docs_build_for_skills_guide", REPO_ROOT / "bin" / "docs_build.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def live_roster():
    """{skill: {harness label, ...}} from the inventory the parity matrix is generated from."""
    roster = {}
    for record in _load_docs_build().skill_inventory(REPO_ROOT):
        roster.setdefault(record["name"], set()).add(LABELS[record["harness"]])
    return roster


def readme_section(text):
    start = text.index(SECTION)
    end = text.find("\n## ", start + len(SECTION))
    return text[start:end if end != -1 else len(text)]


def parse_rows(text):
    """Every four-cell table row whose first cell names a skill -> [(name, harnesses, pairs)].

    A list, not a dict, so a skill listed twice stays visible to the caller. The header and
    separator rows name no skill and drop out on their own.
    """
    rows = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 4:
            continue
        named = re.match(r"\[([a-z][a-z-]*)\]\(|\*\*([a-z][a-z-]*)\*\*", cells[0])
        if not named:
            continue
        name = named.group(1) or named.group(2)
        harnesses = {label for label in LABELS.values() if re.search(rf"\b{label}\b", cells[1])}
        pairs = set(re.findall(r"\[([a-z][a-z-]*)\]\(", cells[3]))
        pairs |= set(re.findall(r"`([a-z][a-z-]*)`", cells[3]))
        rows.append((name, harnesses, pairs))
    return rows


def problems(rows, roster):
    """Everything wrong with a parsed table against a roster -> a sorted list of findings."""
    found = []
    names = [name for name, _harnesses, _pairs in rows]
    for name in sorted(set(names)):
        if names.count(name) > 1:
            found.append(f"{name}: listed {names.count(name)} times")
    for name in sorted(set(roster) - set(names)):
        found.append(f"{name}: shipped but not listed")
    for name, harnesses, pairs in rows:
        if name not in roster:
            found.append(f"{name}: listed but not shipped")
            continue
        if harnesses != roster[name]:
            found.append(f"{name}: says {sorted(harnesses)}, ships on {sorted(roster[name])}")
        if not pairs:
            found.append(f"{name}: no pairing given")
        for other in sorted(pairs):
            if other == name:
                found.append(f"{name}: paired with itself")
            elif other not in roster:
                found.append(f"{name}: paired with {other}, which is not a shipped skill")
            elif not roster[name] & roster[other]:
                found.append(f"{name}: paired with {other}, but no harness ships both")
    return sorted(found)


class SkillsGuideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roster = live_roster()
        cls.readme_text = readme_section(README.read_text(encoding="utf-8"))
        cls.readme_rows = parse_rows(cls.readme_text)
        cls.guide_rows = parse_rows(GUIDE.read_text(encoding="utf-8"))

    def test_the_readme_table_matches_the_shipped_rosters(self):
        self.assertEqual(problems(self.readme_rows, self.roster), [])

    def test_the_site_page_matches_the_shipped_rosters(self):
        self.assertEqual(problems(self.guide_rows, self.roster), [])

    def test_the_two_tables_say_the_same_thing(self):
        def as_map(rows):
            return {name: (harnesses, pairs) for name, harnesses, pairs in rows}

        self.assertEqual(as_map(self.readme_rows), as_map(self.guide_rows))

    def test_the_site_page_is_in_the_navigation_exactly_once(self):
        self.assertEqual(MKDOCS.read_text(encoding="utf-8").count("workflows/choose-a-skill.md"), 1)

    def test_the_readme_points_at_the_site_page(self):
        self.assertIn("/workflows/choose-a-skill/", self.readme_text)


class GuardCanFailTests(unittest.TestCase):
    """The checks above are worth having only if they trip. Each case is the real site page with
    one fact broken IN MEMORY, or a two-row table built for the purpose; no tracked file is
    touched."""

    def setUp(self):
        self.roster = live_roster()
        self.text = GUIDE.read_text(encoding="utf-8")
        self.assertEqual(problems(parse_rows(self.text), self.roster), [])

    def _row(self, name):
        return next(line for line in self.text.splitlines() if line.startswith(f"| **{name}** |"))

    def test_a_dropped_row_is_reported(self):
        broken = self.text.replace(self._row("route") + "\n", "")
        self.assertIn("route: shipped but not listed", problems(parse_rows(broken), self.roster))

    def test_a_wrong_harness_is_reported(self):
        row = self._row("dashboard")
        cells = row.split("|")
        cells[2] = " [Claude](x) · [Codex](y) "
        found = problems(parse_rows(self.text.replace(row, "|".join(cells))), self.roster)
        self.assertTrue(any(item.startswith("dashboard: says") for item in found), found)

    def test_a_pairing_with_a_skill_that_does_not_exist_is_reported(self):
        row = self._row("setup")
        broken = self.text.replace(row, row.rstrip(" |") + ", [teleport](x) |")
        self.assertIn(
            "setup: paired with teleport, which is not a shipped skill",
            problems(parse_rows(broken), self.roster),
        )

    def test_a_pairing_no_single_harness_can_run_is_reported(self):
        # Built rather than mutated: which real skills share no harness changes whenever one is
        # ported, and this case must keep tripping when that happens.
        roster = {"here": {"Claude"}, "there": {"Copilot"}, "both": {"Claude", "Copilot"}}
        rows = [
            ("here", {"Claude"}, {"there", "both"}),
            ("there", {"Copilot"}, {"both"}),
            ("both", {"Claude", "Copilot"}, {"here"}),
        ]
        self.assertEqual(
            problems(rows, roster), ["here: paired with there, but no harness ships both"]
        )

    def test_a_skill_added_to_a_roster_is_reported_until_the_tables_list_it(self):
        roster = dict(self.roster)
        roster["brand-new"] = {"Claude"}
        self.assertIn("brand-new: shipped but not listed", problems(parse_rows(self.text), roster))


if __name__ == "__main__":
    unittest.main()
