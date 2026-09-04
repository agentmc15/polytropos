"""Content-truth regression suite for T15 of the docs-site kit -- the 13
hand-authored getting-started/concepts/workflows pages plus the landing
rewire (.claude/kits/docs-site/TASKS.md).

These tests are derived from the T15 brief's content contracts and the
Phase 6 dispatch obligations recorded in .claude/kits/docs-site/NOTES.md,
not from reading the hand pages first and reverse-engineering assertions to
match them:

- "the real install commands ... copy commands from the sources, never
  from memory" (T15 brief) -> GettingStartedCommandSourceTests checks each
  getting-started page's install commands are byte-exact substrings of the
  brief-named source (README.md for Claude; docs/COPILOT-HARNESS.md and
  docs/CODEX-HARNESS.md for Copilot/Codex).
- GUARDRAILS.md "Numbers, facts, and honesty": "Every command, flag,
  subcommand, and invocation form shown must exist in the skill's SKILL.md,
  the named bin/ engine source, or the harness docs ... Reading engine
  argparse source is the sanctioned way to learn flags" ->
  HarnessSelectFlagValidityTests confirms every --flag shown alongside a
  `harness_select.py` invocation on a getting-started page is declared in
  that engine's own argparse.
- NOTES.md Phase 6 dispatch obligation 3 / P5 Ruling 2: "concepts/billing-
  modes.md must close the architect asymmetry ... Copilot's card instructs
  a planning-time frontier switch and its agent pins the frontier model;
  Codex's card has no such instruction and locates spend at `codex exec
  --model`" -> ArchitectAsymmetryTests verifies both halves directly against
  the two SKILL.md cards, not against the hand page's own retelling of them.
- GUARDRAILS.md "No fabricated facts in fragments or hand pages" ->
  EffortMechanismSourcingTests checks that concepts/effort-and-context.md's
  claim about how Codex's reasoning-effort level is "actually set" names
  only mechanisms traceable to a sanctioned Codex source.

Every check reads the real committed tree -- no fixtures, no network, no
CLI invocation.
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE = REPO_ROOT / "docs-site"
GETTING_STARTED = SITE / "getting-started"
CONCEPTS = SITE / "concepts"


def _norm(text):
    """Collapse whitespace so a phrase that wraps across a markdown source's
    line-wrapped prose can still be matched as one substring."""
    return re.sub(r"\s+", " ", text)


class GettingStartedCommandSourceTests(unittest.TestCase):
    """T15 brief: 'Getting started, per harness ... copy commands from the
    sources, never from memory.' Each command line shown on a getting-started
    page must be a byte-exact substring of its brief-named source file."""

    def test_claude_marketplace_pair_matches_readme_install_section(self):
        page = (GETTING_STARTED / "claude.md").read_text(encoding="utf-8")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        for line in (
            "/plugin marketplace add /path/to/polytropos",
            "/plugin install polytropos@polytropos-local",
            "claude plugin marketplace add /path/to/polytropos",
            "claude plugin install polytropos@polytropos-local",
            "claude --plugin-dir /path/to/polytropos",
        ):
            self.assertIn(
                line, page,
                f"getting-started/claude.md no longer shows {line!r}",
            )
            self.assertIn(
                line, readme,
                f"README.md's Install section no longer contains {line!r} -- "
                f"getting-started/claude.md has drifted from its brief-named source",
            )

    def test_copilot_install_commands_match_copilot_harness_doc(self):
        page = (GETTING_STARTED / "copilot.md").read_text(encoding="utf-8")
        doc = (REPO_ROOT / "docs" / "COPILOT-HARNESS.md").read_text(encoding="utf-8")
        for line in (
            "python3 bin/harness_select.py detect",
            "python3 bin/harness_select.py install --harness copilot",
        ):
            self.assertIn(line, page)
            self.assertIn(
                line, doc,
                f"docs/COPILOT-HARNESS.md no longer shows {line!r} -- "
                f"getting-started/copilot.md has drifted from its brief-named source",
            )

    def test_codex_install_commands_match_codex_harness_doc(self):
        page = (GETTING_STARTED / "codex.md").read_text(encoding="utf-8")
        doc = (REPO_ROOT / "docs" / "CODEX-HARNESS.md").read_text(encoding="utf-8")
        for line in (
            "python3 bin/harness_select.py install --harness codex --repo-root . "
            "--codex-home <codex-home> --components plugin,agents "
            "--agent-scope project --dry-run",
            "python3 bin/harness_select.py install --harness codex --repo-root . "
            "--codex-home <codex-home> --components plugin,agents "
            "--agent-scope project",
        ):
            self.assertIn(line, page)
            self.assertIn(
                line, doc,
                f"docs/CODEX-HARNESS.md no longer shows this exact invocation -- "
                f"getting-started/codex.md has drifted from its brief-named source",
            )


class HarnessSelectFlagValidityTests(unittest.TestCase):
    """GUARDRAILS.md 'Numbers, facts, and honesty': every flag shown must
    exist in the named bin/ engine source. Extracts every --flag token that
    appears on a line mentioning `harness_select.py` across the four
    getting-started pages and confirms bin/harness_select.py's own
    build_parser() declares it -- catches an invented or renamed flag
    without hardcoding the roster, so it stays valid as the engine evolves."""

    def test_every_harness_select_flag_shown_is_declared_in_the_source(self):
        source = (REPO_ROOT / "bin" / "harness_select.py").read_text(encoding="utf-8")
        declared_flags = set(re.findall(r'"(--[a-z][a-z-]*)"', source))
        self.assertTrue(declared_flags, "expected at least one declared --flag")

        shown_flags = set()
        for name in ("index.md", "claude.md", "copilot.md", "codex.md"):
            text = (GETTING_STARTED / name).read_text(encoding="utf-8")
            for line in text.splitlines():
                if "harness_select.py" in line:
                    shown_flags.update(re.findall(r"(--[a-z][a-z-]*)", line))

        missing = shown_flags - declared_flags
        self.assertEqual(
            missing, set(),
            f"getting-started pages show flag(s) {sorted(missing)} that "
            f"bin/harness_select.py's own argparse does not declare",
        )


class ArchitectAsymmetryTests(unittest.TestCase):
    """NOTES.md Phase 6 dispatch obligation 3 / P5 Ruling 2: billing-modes.md
    must accurately cite the two architect cards' asymmetry -- Copilot
    instructs a frontier-tier switch and its agent frontmatter pins the
    frontier model; Codex has no switch instruction, forbids invoking the
    real CLI, and locates spend at `codex exec --model`. These checks read
    the two cards directly rather than trusting the hand page's retelling,
    then confirm the hand page states both halves."""

    def test_copilot_architect_card_instructs_a_frontier_switch(self):
        card = (
            REPO_ROOT / "copilot" / ".github" / "skills" / "architect" / "SKILL.md"
        ).read_text(encoding="utf-8")
        norm = _norm(card)
        self.assertIn(
            "switch the session to the frontier tier first", norm,
            "copilot architect card no longer instructs a frontier-tier switch "
            "before planning nontrivial work",
        )
        self.assertIn(
            "frontmatter pin carries the frontier model", norm,
            "copilot architect card no longer states that the `architect` "
            "agent's frontmatter pin carries the frontier model",
        )

    def test_codex_architect_card_has_no_switch_and_locates_spend_at_exec(self):
        card = (
            REPO_ROOT / "codex" / "skills" / "architect" / "SKILL.md"
        ).read_text(encoding="utf-8")
        norm = _norm(card)
        self.assertNotIn(
            "switch", norm.lower(),
            "codex architect card now mentions a session-model switch -- the "
            "asymmetry billing-modes.md describes (no switch instruction on "
            "Codex) no longer holds",
        )
        self.assertIn("never invoke the real", norm.lower())
        self.assertIn("codex exec --model", norm)

    def test_billing_modes_page_states_both_halves_of_the_asymmetry(self):
        page = (CONCEPTS / "billing-modes.md").read_text(encoding="utf-8")
        norm = _norm(page)
        self.assertIn(
            "codex exec --model", norm,
            "billing-modes.md no longer locates Codex's architect spend at "
            "`codex exec --model`",
        )
        self.assertRegex(
            norm, r"never invoke the .codex. CLI",
            "billing-modes.md no longer states the Codex architect card's "
            "never-invoke-the-CLI rule",
        )
        self.assertIn(
            "frontier", norm.lower(),
            "billing-modes.md's asymmetry section should name the frontier "
            "tier for the Copilot half of the comparison",
        )


class EffortMechanismSourcingTests(unittest.TestCase):
    """GUARDRAILS.md 'No fabricated facts in fragments or hand pages ...
    every command, flag, subcommand, and invocation form shown must exist
    in the skill's SKILL.md, the named bin/ engine source, or the harness
    docs.' concepts/effort-and-context.md states how each harness's effort
    level is 'actually set'; every mechanism named for Codex beyond the
    confirmed `-c model_reasoning_effort=<level>` per-run override must be
    traceable to a sanctioned Codex source."""

    SANCTIONED_SOURCES = (
        "docs/EFFORT-DIAL.md",
        "docs/CODEX-HARNESS.md",
        "codex/skills/effort/SKILL.md",
        "codex/AGENTS.md",
    )

    def test_codex_effort_setting_mechanism_claim_is_sourced(self):
        page = (CONCEPTS / "effort-and-context.md").read_text(encoding="utf-8")
        norm = _norm(page)
        match = re.search(r"on Codex a per-run[^.]*\.", norm)
        self.assertIsNotNone(
            match,
            "expected concepts/effort-and-context.md to describe how Codex's "
            "reasoning-effort level is actually set (looked for the sentence "
            "starting 'on Codex a per-run ...')",
        )
        claim = match.group(0)
        self.assertIn(
            "model_reasoning_effort", claim,
            "the confirmed per-run override should be named in this sentence",
        )

        sources_text = "\n".join(
            (REPO_ROOT / rel).read_text(encoding="utf-8").lower()
            for rel in self.SANCTIONED_SOURCES
        )
        for extra_term in ("session", "profile"):
            if extra_term in claim.lower():
                self.assertTrue(
                    extra_term in sources_text,
                    f"concepts/effort-and-context.md claims Codex's effort "
                    f"level is also set via {extra_term!r} defaults, but none "
                    f"of the sanctioned Codex sources "
                    f"({', '.join(self.SANCTIONED_SOURCES)}) document that -- "
                    f"this looks fabricated rather than copied from a source",
                )


if __name__ == "__main__":
    unittest.main()
