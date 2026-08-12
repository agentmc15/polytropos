"""Stdlib unittest regression suite for the context-rules kit's relocation (PLAN.md D4).

This is the kit's permanent eval: no safety string dropped, no re-bloat. It asserts against
the real repo files (committed content, not user data) — no fixtures needed.
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

KIT_FENCE_RE = re.compile(r"^\s*For `[a-z0-9-]+` specifically:")

GLOBAL_SENTINELS = (
    "single numeric source of truth",
    "Never invoke the real `copilot` CLI from tests",
    "read-only ingestion with gitignored output",
    "Python is stdlib-only",
    "pending | in-progress | done | blocked",
    "Never touch `~/.claude/`",
    "Do not commit or push",
    "gitignored user data",
    "${CLAUDE_PLUGIN_ROOT}",
)

KIT_SENTINELS = {
    "harden-plugin": "no pricing.json value edits",
    "aesop-bridge": "only `bin/sync_pricing_refs.py` writes them",
    "copilot-harness": "nothing outside this repo — `~/.copilot` included",
    "copilot-workflow": "NEVER invoke the real `copilot` CLI in any form",
    "copilot-costviz": "nothing reads OR writes the real `~/.copilot`",
    "daily-journal": "ingestion is STRICTLY read-only",
    "fusion-tier1": "never the real `~/.claude`",
    "fusion-tier2": "NEVER auto-routes to frontier/Fable",
    "routing-history": "never a write under `~/.claude`",
    "per-task-dollars": "`skills/architect/SKILL.md` is NEVER edited",
    "crossrepo-trend": "never the real `~/.claude`",
    "codex-harness": "NEVER invoke the real `codex` CLI in any form",
    "journal-augment": "no Graph/OAuth/MCP/network/secrets in any form",
    "next-day-runbook": "NO scheduler and NO unattended dispatch in any form",
    "harness-parity": "`copilot`/`codex`/`claude` CLI from any task, test, or verify command",
    "memory-skill": "gitignored USER DATA",
    "effort-dial": "NEVER invoke the real `copilot`/`codex`/`claude` CLI",
    "graphify-skill": "never invoked by tests, verify commands, or kit execution",
    "copilot-skills-parity": "NEVER invoke the real `copilot`/`codex`/`claude`",
    "copilot-model-prefs": "NEVER invoke the real `copilot`/`codex`/`claude` CLI from any task,",
    "harness-update": "Never a write under `~/.claude` — the remedy is printed, never executed",
}


class KitLayoutTests(unittest.TestCase):
    """Every kit directory that has a PLAN.md must also carry a substantial GUARDRAILS.md."""

    def test_every_plan_has_a_guardrails_file(self):
        kits_dir = REPO_ROOT / ".claude" / "kits"
        kit_dirs = sorted(p for p in kits_dir.iterdir() if p.is_dir())
        self.assertTrue(kit_dirs, "expected at least one kit directory under .claude/kits/")

        for kit_dir in kit_dirs:
            plan = kit_dir / "PLAN.md"
            if not plan.is_file():
                continue
            with self.subTest(kit=kit_dir.name):
                guardrails = kit_dir / "GUARDRAILS.md"
                self.assertTrue(
                    guardrails.is_file(),
                    f"{kit_dir.name} has PLAN.md but no GUARDRAILS.md",
                )
                size = guardrails.stat().st_size
                self.assertGreaterEqual(
                    size,
                    200,
                    f"{kit_dir.name}/GUARDRAILS.md is only {size} bytes (< 200)",
                )


class ClaudeMdBudgetTests(unittest.TestCase):
    """CLAUDE.md stays small after relocation; kit fences never creep back in."""

    def test_claude_md_under_byte_ceiling(self):
        claude_md = REPO_ROOT / "CLAUDE.md"
        size = claude_md.stat().st_size
        self.assertLessEqual(
            size,
            16000,
            f"CLAUDE.md is {size} bytes, exceeds the 16000-byte tripwire ceiling",
        )

    def test_no_kit_specific_fence_lines(self):
        claude_md = REPO_ROOT / "CLAUDE.md"
        text = claude_md.read_text(encoding="utf-8")
        offenders = [line for line in text.splitlines() if KIT_FENCE_RE.match(line)]
        self.assertEqual(
            offenders,
            [],
            f"kit-specific fence line(s) leaked back into CLAUDE.md: {offenders!r}",
        )


class GlobalSentinelTests(unittest.TestCase):
    """The always-on money/CLI/data/contract invariants must remain in CLAUDE.md."""

    def test_global_sentinels_present(self):
        claude_md = REPO_ROOT / "CLAUDE.md"
        text = claude_md.read_text(encoding="utf-8")
        for sentinel in GLOBAL_SENTINELS:
            with self.subTest(sentinel=sentinel):
                self.assertIn(sentinel, text)


class KitSentinelTests(unittest.TestCase):
    """Each relocated kit-scoped fence block kept its distinctive safety line, verbatim."""

    def test_kit_sentinels_present(self):
        for slug, sentinel in KIT_SENTINELS.items():
            with self.subTest(kit=slug, sentinel=sentinel):
                guardrails = REPO_ROOT / ".claude" / "kits" / slug / "GUARDRAILS.md"
                self.assertTrue(
                    guardrails.is_file(),
                    f"missing .claude/kits/{slug}/GUARDRAILS.md",
                )
                text = guardrails.read_text(encoding="utf-8")
                self.assertIn(sentinel, text)


if __name__ == "__main__":
    unittest.main()
