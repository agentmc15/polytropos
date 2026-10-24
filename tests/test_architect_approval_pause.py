"""The architect skill stops for the user's approval of the spec before any design.

The pause is a skill instruction, not a mechanism: nothing in bin/ can observe that it happened.
What this suite can hold is the instruction itself, so a later edit cannot drop the pause, let
the draft land on disk as a half-written kit, or leave dispatch mode as one hop that has no way
to ask the user anything.
"""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL = REPO_ROOT / "skills" / "architect" / "SKILL.md"


def _section(text, heading):
    start = text.index(heading)
    end = text.find("\n## ", start + len(heading))
    return text[start:] if end == -1 else text[start:end]


class ArchitectApprovalPauseTests(unittest.TestCase):
    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")

    def test_step_one_pauses_after_the_spec_and_before_the_design(self):
        step1 = _section(self.text, "## Step 1 — The plan")
        goal = step1.index("**Goal**")
        fence = step1.index("**Constraints**")
        pause = step1.index("**Approval pause")
        design = step1.index("**Architecture & key decisions")
        self.assertLess(goal, pause)
        self.assertLess(fence, pause)
        self.assertLess(pause, design, "the pause must come before any design section")

    def test_the_draft_never_lands_in_the_kit_directory_before_approval(self):
        step1 = _section(self.text, "## Step 1 — The plan")
        self.assertIn("write nothing into `.claude/kits/<slug>/` before approval", step1)
        self.assertIn("Continue only on the user's approval in this conversation", step1)

    def test_a_skipped_pause_is_disclosed_at_handoff(self):
        step1 = _section(self.text, "## Step 1 — The plan")
        self.assertIn("explicitly says to plan straight through", step1)
        self.assertIn("the spec was not approved separately", step1)

    def test_dispatch_mode_runs_as_two_hops_around_the_pause(self):
        step0 = _section(self.text, "## Step 0")
        self.assertIn("two hops around Step 1's approval pause", step0)
        self.assertIn("SendMessage", step0)
        self.assertIn("earlier exploration was not carried over", step0)


if __name__ == "__main__":
    unittest.main()
