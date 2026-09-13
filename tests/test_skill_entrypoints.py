"""Skill descriptions discriminate, and every reference is loaded on purpose (step 22).

WHAT WAS MEASURED before the split: the three orchestration entry points carried 3060, 6267,
and 6677 words with mandatory workflow, ledger grammar, evidence-reading guidance, and history
interleaved; their descriptions ran to 404, 307, and 681 characters; and a test pinned each
entry point's exact word count. These tests pin the discipline that replaced that: concise
descriptions with a positive trigger and a negative one, no two of the three claiming the
same trigger, and each reference file named from its SKILL.md with a "read when" trigger
(the pointer guard itself lives in tests/test_docs_skill_dispositions.py).
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS = REPO_ROOT / "skills"

DESCRIPTION_CEILING = 460

#: Positive triggers each description must carry, and a phrase it must NOT claim.
TRIGGERS = {
    "architect": {"yes": ("plan", "architect", "review this codebase"),
                  "no": ("Use when the user says to execute",)},
    "execute": {"yes": ("execute", "continue", "resume"),
                "no": ("plan this with Fable",)},
    "repo-bench": {"yes": ("benchmark", "daily driver", "spends nothing"),
                   "no": ("architect this", "resume a kit")},
}


def _description(name):
    text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(r"(?m)^description: (.*)$", text)
    return m.group(1) if m else ""


class DescriptionTests(unittest.TestCase):
    def test_descriptions_are_concise(self):
        for name in TRIGGERS:
            with self.subTest(skill=name):
                desc = _description(name)
                self.assertTrue(desc)
                self.assertLessEqual(len(desc), DESCRIPTION_CEILING,
                                     f"{name} description is {len(desc)} chars")

    def test_descriptions_carry_their_own_triggers_and_disown_the_others(self):
        for name, spec in TRIGGERS.items():
            desc = _description(name).lower()
            for phrase in spec["yes"]:
                with self.subTest(skill=name, expects=phrase):
                    self.assertIn(phrase.lower(), desc)
            for phrase in spec["no"]:
                with self.subTest(skill=name, refuses=phrase):
                    self.assertNotIn(phrase.lower(), desc)

    def test_the_planner_and_the_executor_point_at_each_other_not_at_themselves(self):
        self.assertIn("/polytropos:execute", _description("architect"))
        self.assertIn("/polytropos:architect", _description("execute"))

    def test_every_claude_skill_has_a_description_that_says_when(self):
        # Every skill names its trigger in some form; the three entry points are held to
        # the stricter positive/negative check above.
        for skill_dir in sorted(p for p in SKILLS.iterdir() if p.is_dir()):
            desc = _description(skill_dir.name).lower()
            with self.subTest(skill=skill_dir.name):
                self.assertTrue(desc, "missing description")
                self.assertTrue(any(w in desc for w in ("use when", "reach for this when",
                                                         "when the user", "use it when")),
                                "description names no trigger")


class ReferenceTests(unittest.TestCase):
    def test_the_three_entry_points_point_at_every_reference_with_a_read_when(self):
        for name in TRIGGERS:
            refs_dir = SKILLS / name / "references"
            text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            section = text.split("## References — read when", 1)
            with self.subTest(skill=name):
                self.assertEqual(len(section), 2, f"{name} has no 'References — read when'")
                for ref in sorted(refs_dir.glob("*.md")):
                    line = next((ln for ln in section[1].splitlines()
                                 if f"references/{ref.name}" in ln), None)
                    self.assertIsNotNone(line, f"{name}: {ref.name} is not listed")
                    self.assertIn("read when", line.lower() if "read before" not in line.lower()
                                  else "read when", f"{name}: {ref.name} has no trigger")

    def test_references_are_not_loaded_together_by_default(self):
        # Progressive disclosure: the entry point names a trigger per reference and never
        # tells the reader to load them all up front.
        for name in TRIGGERS:
            text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8").lower()
            with self.subTest(skill=name):
                self.assertNotIn("read all references", text)
                self.assertNotIn("read every reference", text)


if __name__ == "__main__":
    unittest.main()
